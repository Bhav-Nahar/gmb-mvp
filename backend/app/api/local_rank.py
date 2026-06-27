import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import require_location_access, staff_required
from app.core.authorization import assert_location_active
from app.core.roles import Role
from app.models.user import User
from app.models.location import Location
from app.models.organization import Organization
from app.models.local_rank_scan import LocalRankScan
from app.schemas.local_rank import RunScanRequest, ScanOut, ScanSummaryOut
from app.services.billing.credit_service import CreditService
from app.services.local_rank_service import scan_price
from app.core import plan_config

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/locations/{location_id}/local-rank/scan", response_model=ScanOut)
def start_local_rank_scan(
    body: RunScanRequest,
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    """Queue a geo-grid rank scan. Charged on completion (in the Celery task), so a
    scan that fails to fetch never costs credits. Returns the Pending scan to poll."""
    location_id = location.id
    if current_user.role == Role.VIEWER:
        raise HTTPException(status_code=403, detail="Viewers cannot run rank scans")

    # Feature gate: Local Rank is a Pro-tier feature. Checked BEFORE any credit/spend.
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org or not plan_config.plan_has_feature(org.plan_tier, "local_rank"):
        raise HTTPException(status_code=402,
                            detail="Local Rank is available on the Pro plan. Upgrade to unlock it.")

    assert_location_active(db, location_id)

    latlng = location.latlng if isinstance(location.latlng, dict) else {}
    has_coords = latlng.get("latitude") is not None and latlng.get("longitude") is not None
    has_address = bool(location.address) or (
        isinstance(location.gbp_raw, dict) and bool(location.gbp_raw.get("storefrontAddress")))
    if not has_coords and not has_address:
        raise HTTPException(status_code=400,
                            detail="This location has no coordinates or address yet. Sync it from Google first.")

    price = scan_price(body.grid_size)
    # Guard real money: refuse to queue a scan the org can't afford / is locked.
    CreditService.precheck(db, current_user.organization_id, price)

    scan = LocalRankScan(
        organization_id=current_user.organization_id,
        location_id=location_id,
        user_id=current_user.id,
        keyword=body.keyword.strip(),
        grid_size=body.grid_size,
        radius_miles=body.radius_miles,
        status="Pending",
        cells=[],
        found_count=0,
        total_cells=body.grid_size ** 2,
        credits_charged=0,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    # Enqueue via the configured Celery app (Redis broker), matching every other
    # route. A bare task.delay() binds to Celery's DEFAULT app (AMQP) and fails.
    from app.worker import celery
    try:
        celery.send_task("app.tasks.run_local_rank_scan_task", args=[scan.id])
    except Exception as e:
        # Never leave a Pending row the worker will never pick up (it would spin
        # forever in the UI). Mark it Failed and surface a retryable error.
        logger.error("Failed to enqueue local rank scan %s: %s", scan.id, e)
        scan.status = "Failed"
        scan.error = "Could not queue the scan (broker unavailable). Please try again."
        db.commit()
        raise HTTPException(status_code=502, detail="Could not start the scan. Please try again.")
    return scan


@router.get("/locations/{location_id}/local-rank/scans", response_model=list[ScanSummaryOut])
def list_local_rank_scans(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
    limit: int = 20,
):
    """History list — lightweight (no cells). Each item carries a precomputed centre
    (mean of the grid points) so the UI can draw a live preview without the full cells."""
    location_id = location.id
    rows = (
        db.query(LocalRankScan)
        .filter(LocalRankScan.location_id == location_id)
        .order_by(LocalRankScan.created_at.desc())
        .limit(min(max(limit, 1), 50))
        .all()
    )
    out = []
    for s in rows:
        pts = [c for c in (s.cells or []) if c.get("lat") is not None and c.get("lng") is not None]
        out.append(ScanSummaryOut(
            id=s.id, keyword=s.keyword, grid_size=s.grid_size, radius_miles=s.radius_miles,
            status=s.status, avg_rank=s.avg_rank, solv=s.solv, found_count=s.found_count,
            total_cells=s.total_cells, credits_charged=s.credits_charged, error=s.error,
            created_at=s.created_at,
            center_lat=(sum(c["lat"] for c in pts) / len(pts)) if pts else None,
            center_lng=(sum(c["lng"] for c in pts) / len(pts)) if pts else None,
        ))
    return out


@router.get("/locations/{location_id}/local-rank/scans/{scan_id}", response_model=ScanOut)
def get_local_rank_scan(
    scan_id: int,
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    location_id = location.id
    scan = db.query(LocalRankScan).filter(
        LocalRankScan.id == scan_id,
        LocalRankScan.location_id == location_id,
    ).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan
