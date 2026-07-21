from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, defer, load_only
from sqlalchemy import select, func, update
from app.db.session import get_db
from app.api.deps import get_current_user, staff_required, admin_required, get_user_location_ids, require_location_access, require_premium
from app.core.config import settings
from app.services.billing.entitlement_service import EntitlementService
from app.models.user import User
from app.models.organization import Organization
from app.models.oauth_account import OAuthAccount
from app.models.location import Location
from app.core.roles import ADMIN_ROLES
from app.models.sync_log import SyncLog
from app.schemas.schemas import LocationOut, LocationListOut, SyncLogOut, SyncLogPaginated
from app.schemas.location import LocationSyncStatus, LocationHealthScoreOut, OrganizationHealthSummaryOut
from app.schemas.sla import LocationSLAMetrics, LocationSLASummary
from app.services.sla_service import get_location_sla_metrics, get_organization_sla_summary
from app.services.health_score_service import HealthScoreService
from app.models.location_health_score import LocationHealthScore
from app.models.microsite import Microsite
from app.worker import celery
from app.api.posts import get_redis
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_model=List[LocationListOut])
def get_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch all synced locations, embedding the latest sync-log status so the
    frontend needs only this one request (no per-location /sync-status calls)."""

    # Correlated subquery: for each location, find the id of its most recent SyncLog.
    latest_log_id_sq = (
        select(func.max(SyncLog.id))
        .where(SyncLog.location_id == Location.id)
        .correlate(Location)
        .scalar_subquery()
    )

    query = (
        db.query(
            Location,
            SyncLog.status.label("latest_sync_status"),
            SyncLog.error_message.label("latest_sync_error"),
            LocationHealthScore.score.label("health_score"),
            LocationHealthScore.label.label("health_score_label"),
            Microsite.status.label("microsite_status"),
        )
        .outerjoin(SyncLog, SyncLog.id == latest_log_id_sq)
        .outerjoin(LocationHealthScore, LocationHealthScore.location_id == Location.id)
        .outerjoin(Microsite, Microsite.location_id == Location.id)
        .filter(Location.organization_id == current_user.organization_id)
        # Load only what LocationListOut serializes. The JSONB/detail columns
        # (gbp_raw, hours, service_items, description, ...) were ~90% of both the
        # Supabase->app transfer (the old full SELECT killed the pooler connection:
        # "SSL SYSCALL error: EOF detected") and the app->browser egress.
        .options(
            load_only(
                Location.id, Location.google_location_id, Location.location_name,
                Location.primary_category, Location.address, Location.phone,
                Location.website, Location.average_rating, Location.total_reviews,
                Location.sync_status, Location.billing_status, Location.last_synced_at,
                Location.sla_tracking_started_at, Location.created_at,
                Location.is_verified, Location.is_suspended, Location.is_duplicate,
            )
        )
    )

    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None:
        query = query.filter(Location.id.in_(allowed_location_ids))

    results = query.all()

    # A pre-payment onboarding org may see the locations list (name/rating/sync status)
    # but NOT premium health scores / microsite status — those are gated with the rest of
    # the premium surface. is_premium_unlocked is True for legacy trial/active orgs, so
    # this only strips for the new onboarding state (flag-gated to keep legacy identical).
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    hide_premium = settings.CARD_REQUIRED_ONBOARDING and org is not None and not EntitlementService.is_premium_unlocked(org)

    out = []
    for location, latest_sync_status, latest_sync_error, health_score, health_score_label, microsite_status in results:
        loc_out = LocationListOut.model_validate(location)
        loc_out.latest_sync_status = latest_sync_status
        loc_out.latest_sync_error = latest_sync_error
        if not hide_premium:
            loc_out.health_score = health_score
            loc_out.health_score_label = health_score_label
            loc_out.microsite_status = microsite_status
        out.append(loc_out)
    return out

@router.get("/sync-logs", response_model=SyncLogPaginated)
def get_sync_logs(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch the history of synchronization attempts for the organization."""
    query = db.query(SyncLog).filter(SyncLog.organization_id == current_user.organization_id)

    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None:
        query = query.filter(SyncLog.location_id.in_(allowed_location_ids))

    total = query.count()
    logs = query.order_by(SyncLog.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return {"items": logs, "total": total, "page": page, "size": size}

# NOTE: declared before the "/{location_id}" routes so the literal path isn't captured
# as a location_id.
@router.get("/sync-status")
def get_org_sync_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Org-level sync progress that drives the live 'Syncing…' UI.

    `sync_in_progress` reflects the LOCATION phase (what the Sync button kicks off);
    reviews, attributes and media sync as separate background tasks AFTER it, so once
    `sync_in_progress` is False the user can use the dashboard while those finish.
    Read-only; any org member may poll it."""
    from app.models.organization_sync_state import OrganizationSyncState
    org_id = current_user.organization_id
    state = db.query(OrganizationSyncState).filter(
        OrganizationSyncState.organization_id == org_id
    ).first()
    total = db.query(func.count(Location.id)).filter(
        Location.organization_id == org_id
    ).scalar() or 0
    synced = db.query(func.count(Location.id)).filter(
        Location.organization_id == org_id, Location.sync_status == "Synced"
    ).scalar() or 0
    failed = db.query(func.count(Location.id)).filter(
        Location.organization_id == org_id, Location.sync_status == "Failed"
    ).scalar() or 0
    return {
        "sync_in_progress": bool(state.sync_in_progress) if state else False,
        "last_sync_status": state.last_sync_status if state else None,
        "last_sync_error": state.last_sync_error if state else None,
        "sync_started_at": state.sync_started_at if state else None,
        "last_location_sync_at": state.last_location_sync_at if state else None,
        # Locations discovered/imported so far (total grows as the first sync creates them).
        "locations_total": total,
        "locations_synced": synced,
        "locations_failed": failed,
        "ever_synced": bool(state and state.last_location_sync_at),
    }

@router.get("/sla-summary", response_model=List[LocationSLASummary], dependencies=[Depends(require_premium)])
async def get_locations_sla_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch SLA summary for all locations in the organization."""
    return await get_organization_sla_summary(current_user.organization_id, db)

@router.get("/{location_id}/sla", response_model=LocationSLAMetrics, dependencies=[Depends(require_premium)])
async def get_location_sla(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch SLA metrics for a specific location."""
        
    location_id = location.id
    return await get_location_sla_metrics(location_id, current_user.organization_id, db)

@router.post("/{location_id}/sla/enable", status_code=status.HTTP_200_OK)
def enable_location_sla(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Enable SLA tracking for a specific location."""
        
    location_id = location.id
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(Location)
        .where(Location.id == location_id)
        .where(Location.sla_tracking_started_at.is_(None))
        .values(sla_tracking_started_at=now)
    )
    if result.rowcount == 0:
        # Already enabled — re-fetch to return the existing value
        db.refresh(location)
        return {"status": "already_enabled", "sla_tracking_started_at": location.sla_tracking_started_at}

    db.commit()
    db.refresh(location)
    return {"status": "enabled", "sla_tracking_started_at": location.sla_tracking_started_at}

# NOTE: This static-path route MUST be declared before the dynamic
# "/{location_id}" route below, otherwise FastAPI matches "/{location_id}"
# first (location_id="health-score-summary") and returns a 422.
@router.get("/health-score-summary", response_model=OrganizationHealthSummaryOut, dependencies=[Depends(require_premium)])
def get_organization_health_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch health score summary for the organization.

    total_locations counts every location the user can see, so locations that
    don't yet have a calculated score are reported via not_calculated_count
    rather than silently skewing the average."""
    allowed_location_ids = get_user_location_ids(current_user, db)

    loc_filter = [Location.organization_id == current_user.organization_id]
    if allowed_location_ids is not None:
        loc_filter.append(Location.id.in_(allowed_location_ids))

    total_locations = db.query(func.count(Location.id)).filter(*loc_filter).scalar() or 0

    scores = (
        db.query(LocationHealthScore)
        # summary only needs score+label, not the breakdown/recommendations JSONB
        .options(load_only(LocationHealthScore.score, LocationHealthScore.label))
        .join(Location, Location.id == LocationHealthScore.location_id)
        .filter(*loc_filter)
        .all()
    )

    scored = len(scores)
    not_calculated = total_locations - scored

    avg_score = (sum(s.score for s in scores) // scored) if scored else 0
    excellent = sum(1 for s in scores if s.label == "Excellent")
    good = sum(1 for s in scores if s.label == "Good")
    average = sum(1 for s in scores if s.label == "Average")
    poor = sum(1 for s in scores if s.label == "Poor")
    critical = sum(1 for s in scores if s.label == "Critical")

    return OrganizationHealthSummaryOut(
        average_score=avg_score,
        total_locations=total_locations,
        excellent_count=excellent,
        good_count=good,
        average_count=average,
        poor_count=poor,
        critical_count=critical,
        not_calculated_count=not_calculated,
    )

@router.get("/{location_id}", response_model=LocationOut)
def get_location(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch a specific location by ID."""
    return location

@router.get("/categories/search")
async def search_categories(
    query: str = Query("", min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    """
    Search the Google Business Profile categories API dynamically.
    """
    from app.providers.factory import ProviderFactory
    from app.providers.gbp.client import GBPAsyncClient
    
    provider = ProviderFactory.get_provider("gbp", current_user.organization_id, db)
    access_token = await provider._auth.get_valid_token()
    
    # Sandbox mode fallback
    if "mock_access_token" in access_token:
        mock_cats = [
            {"name": "categories/gcid:jewelry_store", "displayName": "Jewellery Store"},
            {"name": "categories/gcid:jeweler", "displayName": "Jeweller"},
            {"name": "categories/gcid:gemstone_jeweler", "displayName": "Gemstone Jeweler"},
            {"name": "categories/gcid:goldsmith", "displayName": "Goldsmith"},
            {"name": "categories/gcid:gold_dealer", "displayName": "Gold dealer"},
            {"name": "categories/gcid:silversmith", "displayName": "Silversmith"}
        ]
        return [c for c in mock_cats if query.lower() in c["displayName"].lower()]
        
    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://mybusinessbusinessinformation.googleapis.com/v1/categories"
    
    params = {
        "regionCode": "IN",
        "languageCode": "en",
        "filter": f"displayName={query}",
        "view": "BASIC",
        "pageSize": 20
    }
    
    async with GBPAsyncClient(current_user.organization_id) as client:
        resp = await client.request("GET", url, headers=headers, params=params)
        if resp.status_code != 200:
            logger.warning(
                "GBP category search returned non-200 status %s for query %r: %s",
                resp.status_code, query, resp.text
            )
            cats = []
        else:
            cats = resp.json().get("categories", [])
            
    return [
        {
            "name": c.get("name"),
            "displayName": c.get("displayName")
        }
        for c in cats
    ]

@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def trigger_sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """
    Manually trigger Google Business Profile location synchronization.
    Looks up the Admin user who has a connected OAuthAccount for this organization.
    Restricted to Owner/Admin.
    """
    admin_user = (
        db.query(User)
        .join(OAuthAccount, OAuthAccount.user_id == User.id)
        .filter(
            User.organization_id == current_user.organization_id,
            User.role.in_(ADMIN_ROLES),
            User.is_active == True,
            User.deleted_at.is_(None),
        )
        .order_by(OAuthAccount.expires_at.desc(), User.id.asc())
        .first()
    )
    
    if not admin_user:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="No connected Google Account found for this organization. Please reconnect via Google."
        )

    try:
        task = celery.send_task("app.tasks.sync_locations_task", args=[current_user.organization_id, admin_user.id, "Manual"])
    except Exception as e:
        logger.error(f"Failed to queue sync task (Celery/Redis unavailable?): {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sync service is temporarily unavailable. Please try again in a moment."
        )

    # Invalidate cache for all locations belonging to the organization
    try:
        r = get_redis()
        locations = db.query(Location.id).filter(Location.organization_id == current_user.organization_id).all()
        for (loc_id,) in locations:
            cache_key = f"location:attributes_schema:{loc_id}"
            r.delete(cache_key)
            logger.info(f"Invalidated form schema cache for location {loc_id} on manual sync")
    except Exception as e:
        logger.error(f"Failed to invalidate attributes schema cache on manual sync: {e}")

    return {"message": "Sync task has been queued in the background.", "task_id": task.id}

@router.get("/{location_id}/sync-status", response_model=LocationSyncStatus)
def get_location_sync_status(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """
    Get the sync status of a specific location.
    Enforces that the location belongs to the user's organization.
    """
    location_id = location.id
    latest_log = db.query(SyncLog).filter(
        SyncLog.location_id == location_id,
        SyncLog.organization_id == current_user.organization_id
    ).order_by(SyncLog.created_at.desc()).first()

    if not latest_log:
        return LocationSyncStatus(
            location_id=location_id,
            status="Pending",
            last_synced_at=None,
            error_message=None,
            run_type="Manual"
        )

    # Single subquery to find last-success timestamp — avoids a second round-trip
    last_success_sq = (
        select(func.max(SyncLog.created_at))
        .where(SyncLog.location_id == location_id)
        .where(SyncLog.status == "Success")
        .scalar_subquery()
    )
    last_synced_at = db.execute(select(last_success_sq)).scalar_one_or_none()

    return LocationSyncStatus(
        location_id=location_id,
        status=latest_log.status,
        last_synced_at=last_synced_at,
        error_message=latest_log.error_message,
        run_type=latest_log.run_type
    )

@router.get("/{location_id}/health-score", response_model=LocationHealthScoreOut, dependencies=[Depends(require_premium)])
def get_location_health_score(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch the health score for a specific location. If it doesn't exist, calculate it."""
    location_id = location.id
    # Tenant boundary AND per-user location scope are both enforced by the
    # require_location_access dependency, so location_id is guaranteed to belong
    # to current_user's organization here (prevents the cross-tenant IDOR where an
    # admin could read/recalculate another org's location by raw id).
    score = db.query(LocationHealthScore).filter(LocationHealthScore.location_id == location_id).first()
    
    if not score:
        # Calculate on the fly if missing
        score = HealthScoreService.recalculate_health_score(db, location_id, "manual")
        if not score:
            raise HTTPException(status_code=404, detail="Location not found for scoring")
        db.commit()

    return score
