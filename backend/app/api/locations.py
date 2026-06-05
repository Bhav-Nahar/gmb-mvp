from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func, outerjoin
from app.db.session import get_db
from app.api.deps import get_current_user, staff_required, admin_required, get_user_location_ids, verify_location_access
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.models.location import Location
from app.models.sync_log import SyncLog
from app.schemas.schemas import LocationOut, SyncLogOut
from app.schemas.location import LocationSyncStatus
from app.schemas.sla import LocationSLAMetrics, LocationSLASummary
from app.services.sla_service import get_location_sla_metrics, get_organization_sla_summary
from app.worker import celery
from sqlalchemy import func

router = APIRouter()

@router.get("/", response_model=List[LocationOut])
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
        )
        .outerjoin(SyncLog, SyncLog.id == latest_log_id_sq)
        .filter(Location.organization_id == current_user.organization_id)
    )

    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None:
        query = query.filter(Location.id.in_(allowed_location_ids))

    results = query.all()

    out = []
    for location, latest_sync_status, latest_sync_error in results:
        loc_out = LocationOut.model_validate(location)
        loc_out.latest_sync_status = latest_sync_status
        loc_out.latest_sync_error = latest_sync_error
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

@router.get("/sla-summary", response_model=List[LocationSLASummary])
async def get_locations_sla_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch SLA summary for all locations in the organization."""
    return await get_organization_sla_summary(current_user.organization_id, db)

@router.get("/{location_id}/sla", response_model=LocationSLAMetrics)
async def get_location_sla(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch SLA metrics for a specific location."""
    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None and location_id not in allowed_location_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this location")
        
    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id
    ).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    return await get_location_sla_metrics(location_id, current_user.organization_id, db)

@router.post("/{location_id}/sla/enable", status_code=status.HTTP_200_OK)
def enable_location_sla(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Enable SLA tracking for a specific location."""
    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None and location_id not in allowed_location_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this location")
        
    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id
    ).first()
    
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    if location.sla_tracking_started_at is not None:
        return {"status": "already_enabled", "sla_tracking_started_at": location.sla_tracking_started_at}
        
    location.sla_tracking_started_at = func.now()
    db.commit()
    db.refresh(location)
    
    return {"status": "enabled", "sla_tracking_started_at": location.sla_tracking_started_at}

@router.get("/{location_id}", response_model=LocationOut)
def get_location(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch a specific location by ID."""
    # Ensure they have access to this location
    verify_access = verify_location_access(location_id)
    # verify_location_access returns a dependency function, so we must call it manually here or use it in the path
    # Actually, verify_location_access is designed as a dependency. Let's do it in the path instead... wait, we can just call the closure since we have db and current_user? No, it requires a request.
    # We will do it the manual way since we need db and user, let's just check get_user_location_ids.
    
    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None and location_id not in allowed_location_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this location")
        
    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id
    ).first()
    
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
        
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
            User.role.in_(["Owner", "Admin"]),
            User.is_active == True
        )
        .order_by(OAuthAccount.expires_at.desc(), User.id.asc())
        .first()
    )
    
    if not admin_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No connected Google Account found for this organization. Please reconnect via Google."
        )

    task = celery.send_task("app.tasks.sync_locations_task", args=[current_user.organization_id, admin_user.id, "Manual"])
    
    return {"message": "Sync task has been queued in the background.", "task_id": task.id}

@router.get("/{location_id}/sync-status", response_model=LocationSyncStatus)
def get_location_sync_status(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """
    Get the sync status of a specific location.
    Enforces that the location belongs to the user's organization.
    """
    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None and location_id not in allowed_location_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this location")

    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id
    ).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

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

    last_synced_at = None
    if latest_log.status == "Success":
        last_synced_at = latest_log.created_at
    else:
        last_success_log = db.query(SyncLog).filter(
            SyncLog.location_id == location_id,
            SyncLog.status == "Success"
        ).order_by(SyncLog.created_at.desc()).first()
        if last_success_log:
            last_synced_at = last_success_log.created_at

    return LocationSyncStatus(
        location_id=location_id,
        status=latest_log.status,
        last_synced_at=last_synced_at,
        error_message=latest_log.error_message,
        run_type=latest_log.run_type
    )
