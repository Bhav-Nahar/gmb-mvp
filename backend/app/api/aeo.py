import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import require_location_access, admin_required
from app.core.authorization import assert_location_active
from app.core import plan_config
from app.models.user import User
from app.models.location import Location
from app.models.aeo_scan import AEOScan
from app.schemas.aeo import AEOScanOut, AEOScanSummaryOut, AEOQuotaOut, AEOQueriesOut, AEOQueriesUpdate
from app.services import aeo_service
from app.core.config import settings

logger = logging.getLogger(__name__)

# admin_required = Owner/Admin only — enforced on EVERY route in this router.
router = APIRouter(dependencies=[Depends(admin_required)])


def _org(db: Session, org_id: int):
    from app.models.organization import Organization
    return db.query(Organization).filter(Organization.id == org_id).first()


@router.get("/aeo/locations/{location_id}/quota", response_model=AEOQuotaOut)
def get_quota(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    org = _org(db, current_user.organization_id)
    tier = plan_config.aeo_tier_for_plan(org.plan_tier if org else None)
    return AEOQuotaOut(
        per_month=plan_config.AEO_SYNCS_PER_MONTH,
        used_this_month=aeo_service.used_this_month(db, location.id),
        tier=tier,
        in_trial=bool(org and org.subscription_status == "trial"),
        resets_on=aeo_service.next_reset(),
    )


@router.get("/aeo/locations/{location_id}/queries", response_model=AEOQueriesOut)
def get_queries(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    return AEOQueriesOut(
        auto=aeo_service.auto_queries(location),
        custom=list(location.aeo_queries or []),
        auto_enabled=bool(location.aeo_auto_enabled),
        max_custom=settings.AEO_MAX_CUSTOM_QUERIES,
    )


@router.put("/aeo/locations/{location_id}/queries", response_model=AEOQueriesOut)
def set_queries(
    body: AEOQueriesUpdate,
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    """Replace this location's custom AEO queries. Auto queries are always added on
    top at scan time, so we only store the user's own list."""
    try:
        cleaned = aeo_service.clean_custom_queries(body.custom, settings.AEO_MAX_CUSTOM_QUERIES)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not body.auto_enabled and not cleaned:
        raise HTTPException(status_code=400,
                            detail="Turn auto queries back on or add at least one custom query — a scan needs something to check.")
    location.aeo_queries = cleaned
    location.aeo_auto_enabled = body.auto_enabled
    db.commit()
    return AEOQueriesOut(
        auto=aeo_service.auto_queries(location),
        custom=cleaned,
        auto_enabled=bool(location.aeo_auto_enabled),
        max_custom=settings.AEO_MAX_CUSTOM_QUERIES,
    )


@router.post("/aeo/locations/{location_id}/scan", response_model=AEOScanOut)
def run_aeo_scan(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    """Run this month's AI-visibility sync for a location. Owner/Admin only, plan-gated,
    blocked during trial, one per location per calendar month. Mock provider fills results
    inline (instant); the real provider (Phase 2) would enqueue a Celery task and poll."""
    org = _org(db, current_user.organization_id)

    # Plan gate — Basic/Pro have AEO, Lite does not. Determines scan depth too.
    tier = plan_config.aeo_tier_for_plan(org.plan_tier if org else None)
    if tier is None:
        raise HTTPException(status_code=402,
                            detail="AI Visibility is available on the Basic and Pro plans. Upgrade to unlock it.")

    # Trial gate — AEO consumes real data credits, so it's locked until the org
    # activates its subscription (trials get the rest of the app, not this).
    if org and org.subscription_status == "trial":
        raise HTTPException(status_code=402,
                            detail="AI Visibility unlocks once your subscription is active. Activate your plan to run a sync.")

    assert_location_active(db, location.id)

    queries = aeo_service.build_queries(location)
    if not queries:
        raise HTTPException(status_code=400,
                            detail="No queries to check. Enable auto queries or add a custom one first.")

    # Monthly quota — one manual sync per location.
    if aeo_service.used_this_month(db, location.id):
        raise HTTPException(
            status_code=429,
            detail=f"This location's monthly AI Visibility sync is already used. "
                   f"It refills on {aeo_service.next_reset().date().isoformat()}.")

    scan = AEOScan(
        organization_id=current_user.organization_id,
        location_id=location.id,
        user_id=current_user.id,
        tier=tier,
        status="Pending",
        queries_tracked=len(queries),
        result={},
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    # Mock is instant + dependency-free → run inline (no worker needed to demo).
    # Real (dataforseo) calls are slow/rate-limited → enqueue so the request returns
    # immediately with a Pending scan the frontend polls, same as geo-grid.
    if settings.AEO_PROVIDER == "mock":
        aeo_service.run_scan(db, scan, location)
    else:
        from app.worker import celery
        try:
            celery.send_task("app.tasks.run_aeo_scan_task", args=[scan.id])
        except Exception as e:
            logger.error("Failed to enqueue AEO scan %s: %s", scan.id, e)
            scan.status = "Failed"
            scan.error = "Could not queue the scan (broker unavailable). Please try again."
            db.commit()
            raise HTTPException(status_code=502, detail="Could not start the scan. Please try again.")
    return scan


@router.get("/aeo/locations/{location_id}/scans", response_model=list[AEOScanSummaryOut])
def list_aeo_scans(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
    limit: int = 20,
):
    return (
        db.query(AEOScan)
        .filter(AEOScan.location_id == location.id)
        .order_by(AEOScan.created_at.desc())
        .limit(min(max(limit, 1), 50))
        .all()
    )


@router.get("/aeo/locations/{location_id}/scans/{scan_id}", response_model=AEOScanOut)
def get_aeo_scan(
    scan_id: int,
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    scan = db.query(AEOScan).filter(
        AEOScan.id == scan_id,
        AEOScan.location_id == location.id,
    ).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan
