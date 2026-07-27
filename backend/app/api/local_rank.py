import logging
from datetime import datetime, timezone, timedelta

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

    # Reuse a fresh identical scan: same keyword/grid/radius within the TTL returns
    # the existing scan (Pending → client polls it, Completed → instant results)
    # instead of paying DataForSEO grid_size² tasks again for the same answer.
    RESCAN_TTL_HOURS = 6  # ponytail: fixed TTL; make it a setting if plans ever differ
    keyword = body.keyword.strip()
    recent = db.query(LocalRankScan).filter(
        LocalRankScan.location_id == location_id,
        LocalRankScan.keyword == keyword,
        LocalRankScan.grid_size == body.grid_size,
        LocalRankScan.radius_miles == body.radius_miles,
        LocalRankScan.status.in_(["Pending", "Completed"]),
        LocalRankScan.created_at >= datetime.now(timezone.utc) - timedelta(hours=RESCAN_TTL_HOURS),
    ).order_by(LocalRankScan.id.desc()).first()
    if recent:
        return recent

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
    """History list — lightweight (no cells). Grids are odd (3x3/5x5/...), so the middle
    JSONB element is the exact centre cell; extracting it in SQL keeps the big cells
    payload inside the database."""
    from sqlalchemy import Float, Integer, cast, func
    location_id = location.id
    mid_cell = LocalRankScan.cells[cast(func.jsonb_array_length(LocalRankScan.cells) / 2, Integer)]
    center_lat = cast(mid_cell["lat"].astext, Float)
    center_lng = cast(mid_cell["lng"].astext, Float)
    rows = (
        db.query(
            LocalRankScan.id, LocalRankScan.keyword, LocalRankScan.grid_size,
            LocalRankScan.radius_miles, LocalRankScan.status, LocalRankScan.avg_rank,
            LocalRankScan.solv, LocalRankScan.found_count, LocalRankScan.total_cells,
            LocalRankScan.credits_charged, LocalRankScan.error, LocalRankScan.created_at,
            center_lat.label("center_lat"), center_lng.label("center_lng"),
        )
        .filter(LocalRankScan.location_id == location_id)
        .order_by(LocalRankScan.created_at.desc())
        .limit(min(max(limit, 1), 50))
        .all()
    )
    return [ScanSummaryOut(
        id=s.id, keyword=s.keyword, grid_size=s.grid_size, radius_miles=s.radius_miles,
        status=s.status, avg_rank=s.avg_rank, solv=s.solv, found_count=s.found_count,
        total_cells=s.total_cells, credits_charged=s.credits_charged, error=s.error,
        created_at=s.created_at, center_lat=s.center_lat, center_lng=s.center_lng,
    ) for s in rows]


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


# --- Competitor tracking (free: harvested from geo-grid scan results) ---

from pydantic import BaseModel

from app.models.competitor import TrackedCompetitor, CompetitorSnapshot
from app.services import competitor_service


class AddCompetitorRequest(BaseModel):
    place_id: str
    name: str
    category: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None


def _competitor_limit(db: Session, org_id: int) -> int:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    return plan_config.plan_limit(org.plan_tier if org else None, plan_config.LIMIT_COMPETITORS, 3) or 3


def _is_pro(db: Session, org_id: int) -> bool:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    return bool(org and org.plan_tier == "pro")


def _own_place_id(location: Location) -> str | None:
    meta = location.gbp_raw.get("metadata") if isinstance(location.gbp_raw, dict) else None
    return meta.get("placeId") if isinstance(meta, dict) else None


@router.get("/locations/{location_id}/competitors/suggestions")
def competitor_suggestions(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    """Businesses that appear in this location's recent rank scans — candidates to track."""
    return competitor_service.suggestions(db, location.id, _own_place_id(location), own_name=location.location_name)


@router.get("/locations/{location_id}/competitors")
def list_competitors(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    """Tracked competitors with their latest snapshot and full snapshot history."""
    own_lat = own_lng = None
    if isinstance(location.latlng, dict):
        own_lat, own_lng = location.latlng.get("latitude"), location.latlng.get("longitude")
    competitors = (db.query(TrackedCompetitor)
                   .filter(TrackedCompetitor.location_id == location.id)
                   .order_by(TrackedCompetitor.created_at.asc()).all())
    facts = competitor_service.latest_profile_facts(db, location.id) if competitors else {}
    # One batched query for all snapshots instead of one per competitor.
    snaps_by_comp: dict[int, list[CompetitorSnapshot]] = {}
    if competitors:
        all_snaps = (db.query(CompetitorSnapshot)
                     .filter(CompetitorSnapshot.competitor_id.in_([c.id for c in competitors]))
                     .order_by(CompetitorSnapshot.captured_at.asc()).all())
        for s in all_snaps:
            snaps_by_comp.setdefault(s.competitor_id, []).append(s)
    out = []
    for comp in competitors:
        snaps = snaps_by_comp.get(comp.id, [])
        dist = (competitor_service.distance_km(own_lat, own_lng, comp.lat, comp.lng)
                if None not in (own_lat, own_lng, comp.lat, comp.lng) else None)
        fact = facts.get(comp.place_id, {})
        out.append({
            "id": comp.id, "place_id": comp.place_id, "name": comp.name,
            "category": comp.category, "address": comp.address,
            "lat": comp.lat, "lng": comp.lng, "distance_km": dist,
            "is_claimed": fact.get("is_claimed"), "domain": fact.get("domain"),
            "price_level": fact.get("price_level"),
            "snapshots": [{
                "captured_at": s.captured_at, "keyword": s.keyword,
                "rating": s.rating, "review_count": s.review_count,
                "photo_count": s.photo_count, "best_rank": s.best_rank,
                "avg_rank": s.avg_rank, "appearances": s.appearances,
                "total_cells": s.total_cells,
            } for s in snaps],
        })
    is_pro = _is_pro(db, current_user.organization_id)
    # Own visibility per completed scan — feeds the share-of-voice trend.
    own_trend = [
        {"captured_at": created_at, "keyword": keyword, "solv": solv}
        for created_at, keyword, solv in db.query(
            LocalRankScan.created_at, LocalRankScan.keyword, LocalRankScan.solv)
        .filter(LocalRankScan.location_id == location.id,
                LocalRankScan.status == "Completed", LocalRankScan.solv.isnot(None))
        .order_by(LocalRankScan.created_at.asc()).limit(30).all()
    ]
    return {"own": {"name": location.location_name, "lat": own_lat, "lng": own_lng,
                    "rating": location.average_rating, "reviews": location.total_reviews},
            "own_trend": own_trend,
            "competitors": out,
            "limit": _competitor_limit(db, current_user.organization_id),
            "is_pro": is_pro,
            # Pro-only insight: per-keyword leader from the latest scans
            "keyword_winners": competitor_service.keyword_winners(db, location.id) if is_pro else [],
            # Pro-only: full local pack from the latest scan for rank-correlation charts
            "market": competitor_service.market_scatter(db, location.id, _own_place_id(location),
                                                        location.location_name) if is_pro else []}


@router.post("/locations/{location_id}/competitors", status_code=201)
def add_competitor(
    body: AddCompetitorRequest,
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    if current_user.role == Role.VIEWER:
        raise HTTPException(status_code=403, detail="Viewers cannot manage competitors")
    limit = _competitor_limit(db, current_user.organization_id)
    count = db.query(TrackedCompetitor).filter(TrackedCompetitor.location_id == location.id).count()
    if count >= limit:
        raise HTTPException(status_code=409, detail=f"Your plan allows tracking up to {limit} competitors per location. Upgrade to Pro for more.")
    exists = db.query(TrackedCompetitor).filter(
        TrackedCompetitor.location_id == location.id,
        TrackedCompetitor.place_id == body.place_id).first()
    if exists:
        raise HTTPException(status_code=409, detail="Already tracking this competitor.")
    comp = TrackedCompetitor(
        organization_id=current_user.organization_id, location_id=location.id,
        place_id=body.place_id, name=body.name, category=body.category, address=body.address,
        lat=body.lat, lng=body.lng)
    db.add(comp)
    db.flush()
    # Backfill snapshots from recent completed scans so the row isn't empty on day one.
    # Bounded to the newest 20 — a daily-scanning location would otherwise pull hundreds
    # of heavy cells payloads into memory on one click.
    scans = (db.query(LocalRankScan)
             .filter(LocalRankScan.location_id == location.id, LocalRankScan.status == "Completed")
             .order_by(LocalRankScan.created_at.desc()).limit(20).all())[::-1]
    for scan in scans:
        agg = competitor_service._aggregate(scan, comp.place_id, comp.name)
        if agg:
            db.add(CompetitorSnapshot(competitor_id=comp.id, scan_id=scan.id, keyword=scan.keyword,
                                      captured_at=scan.created_at, **agg))
    db.commit()
    return {"id": comp.id}


@router.get("/locations/{location_id}/competitors/{competitor_id}/heatmap")
def competitor_heatmap(
    competitor_id: int,
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    """The competitor's per-cell grid ranks from the latest scan, plus your own cells."""
    comp = db.query(TrackedCompetitor).filter(
        TrackedCompetitor.id == competitor_id,
        TrackedCompetitor.location_id == location.id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competitor not found")
    result = competitor_service.competitor_heatmap(db, location.id, comp)
    if not result:
        raise HTTPException(status_code=404, detail="No completed scans yet")
    return result


@router.delete("/locations/{location_id}/competitors/{competitor_id}", status_code=204)
def remove_competitor(
    competitor_id: int,
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    if current_user.role == Role.VIEWER:
        raise HTTPException(status_code=403, detail="Viewers cannot manage competitors")
    comp = db.query(TrackedCompetitor).filter(
        TrackedCompetitor.id == competitor_id,
        TrackedCompetitor.location_id == location.id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competitor not found")
    db.delete(comp)
    db.commit()
