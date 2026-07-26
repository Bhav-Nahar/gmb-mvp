import json
import uuid
from typing import Any, List, Optional
from datetime import date

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app import models
from app.api import deps
from app.core.redis_client import get_redis
from app.services.comparison_snapshot_service import ComparisonSnapshotService
from app.schemas.comparison import (
    ComparisonSummary,
    ComparisonTrendDataPoint,
    ComparisonLeaderboardItemRefined,
    ComparisonGroupItem,
)

router = APIRouter()

VALID_GROUP_TYPES = ("CITY", "STATE", "REGION", "CUSTOM_GROUP")


def _validate(group_type: str, start_date: date, end_date: date) -> None:
    if group_type not in VALID_GROUP_TYPES:
        raise HTTPException(status_code=422, detail=f"group_type must be one of {VALID_GROUP_TYPES}")
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")


def _scope(current_user: models.User, db: Session, group_type: str) -> Optional[List[int]]:
    """Resolve the caller's location scope.

    Returns None for org-wide roles (no restriction). For location-restricted users,
    returns their allowed location ids — applied to CITY/STATE/REGION queries (all
    location-level). CUSTOM_GROUP reads org-wide rollups that can't be sub-filtered per
    location, so a restricted user is denied that mode rather than shown unscoped data.
    """
    allowed = deps.get_user_location_ids(current_user, db)
    if allowed is not None and group_type == "CUSTOM_GROUP":
        raise HTTPException(status_code=403, detail="Custom-group comparison requires org-wide access")
    return allowed


def _filters(group_type, start_date, end_date, group_ids) -> dict:
    return {
        "group_type": group_type,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "group_ids": group_ids,
    }


@router.get("/summary", response_model=ComparisonSummary)
def get_comparison_summary(
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
    group_type: str = Query("CITY", description="CITY | STATE | REGION | CUSTOM_GROUP"),
    start_date: date = Query(...),
    end_date: date = Query(...),
    group_ids: Optional[List[str]] = Query(None, description="List of IDs or names to compare"),
) -> Any:
    org_id = current_user.organization_id
    _validate(group_type, start_date, end_date)
    allowed = _scope(current_user, db, group_type)
    return ComparisonSnapshotService.get_summary(
        db, org_id, _filters(group_type, start_date, end_date, group_ids), allowed
    )


@router.get("/trends", response_model=List[ComparisonTrendDataPoint])
def get_comparison_trends(
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
    group_type: str = Query("CITY"),
    start_date: date = Query(...),
    end_date: date = Query(...),
    group_ids: Optional[List[str]] = Query(None),
) -> Any:
    org_id = current_user.organization_id
    _validate(group_type, start_date, end_date)
    allowed = _scope(current_user, db, group_type)
    return ComparisonSnapshotService.get_trends(
        db, org_id, _filters(group_type, start_date, end_date, group_ids), allowed
    )


@router.get("/leaderboard", response_model=List[ComparisonLeaderboardItemRefined])
def get_comparison_leaderboard(
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
    group_type: str = Query("CITY"),
    start_date: date = Query(...),
    end_date: date = Query(...),
    group_ids: Optional[List[str]] = Query(None),
) -> Any:
    org_id = current_user.organization_id
    _validate(group_type, start_date, end_date)
    allowed = _scope(current_user, db, group_type)
    return ComparisonSnapshotService.get_leaderboard(
        db, org_id, _filters(group_type, start_date, end_date, group_ids), allowed
    )


@router.get("/breakdown")
def get_comparison_breakdown(
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
    group_type: str = Query("CITY"),
    start_date: date = Query(...),
    end_date: date = Query(...),
    group_ids: Optional[List[str]] = Query(None),
) -> Any:
    """Per-group rows: all metrics + previous-period values for deltas."""
    org_id = current_user.organization_id
    _validate(group_type, start_date, end_date)
    allowed = _scope(current_user, db, group_type)
    return ComparisonSnapshotService.get_breakdown(
        db, org_id, _filters(group_type, start_date, end_date, group_ids), allowed
    )


@router.get("/series")
def get_comparison_series(
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
    group_type: str = Query("CITY"),
    metric: str = Query("profile_views"),
    start_date: date = Query(...),
    end_date: date = Query(...),
    group_ids: Optional[List[str]] = Query(None),
) -> Any:
    """One date-series per group for the chosen metric (multi-line chart)."""
    org_id = current_user.organization_id
    _validate(group_type, start_date, end_date)
    allowed = _scope(current_user, db, group_type)
    return ComparisonSnapshotService.get_series(
        db, org_id, _filters(group_type, start_date, end_date, group_ids), metric, allowed
    )


@router.get("/groups", response_model=List[ComparisonGroupItem])
def get_comparison_groups(
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
    group_type: str = Query("CITY"),
) -> Any:
    org_id = current_user.organization_id
    allowed = deps.get_user_location_ids(current_user, db)

    if group_type == "CUSTOM_GROUP":
        if allowed is not None:
            return []
        cgs = db.query(models.CustomGroup).filter(models.CustomGroup.organization_id == org_id).all()
        return [{"id": str(cg.id), "name": cg.name} for cg in cgs]
    elif group_type in ("CITY", "STATE", "REGION"):
        # REGION groups by the state's derived India zone; CITY/STATE by the raw column.
        col = models.Location.city if group_type == "CITY" else models.Location.state
        q = db.query(col).filter(models.Location.organization_id == org_id, col.isnot(None))
        if allowed is not None:
            q = q.filter(models.Location.id.in_(allowed))
        rows = q.distinct().all()
        if group_type == "REGION":
            from app.services.comparison_snapshot_service import INDIA_ZONES
            state_to_zone = {s: z for z, states in INDIA_ZONES.items() for s in states}
            zones = sorted({state_to_zone[r[0]] for r in rows if r[0] in state_to_zone})
            return [{"id": z, "name": z} for z in zones]
        return [{"id": r[0], "name": r[0]} for r in rows if r[0]]

    return []


@router.post("/refresh")
def refresh_comparison_cache(
    current_user: models.User = Depends(deps.get_current_user),
) -> Any:
    """Bust this org's cached comparison results so the next load is recomputed from
    the latest daily insights (e.g. after new locations are added/unlocked)."""
    from app.services.comparison_cache_service import ComparisonCacheService
    ComparisonCacheService.invalidate_comparison_cache(current_user.organization_id)
    return {"status": "refreshed"}


@router.post("/export")
def request_comparison_export(
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
    group_type: str = Query("CITY"),
    start_date: date = Query(...),
    end_date: date = Query(...),
    group_ids: Optional[List[str]] = Query(None),
) -> Any:
    org_id = current_user.organization_id
    _validate(group_type, start_date, end_date)
    allowed = _scope(current_user, db, group_type)  # enforce same access rules as the data endpoints
    from app.tasks_comparison import generate_comparison_export_task

    export_id = str(uuid.uuid4())
    filters = _filters(group_type, start_date, end_date, group_ids)

    # Bind the export to its org so /export/{id} can verify ownership (no IDOR).
    get_redis().setex(f"export:{export_id}", 86400, json.dumps({
        "status": "processing", "download_url": None, "org_id": org_id,
    }))
    generate_comparison_export_task.delay(export_id, org_id, filters, allowed)
    return {"export_id": export_id, "status": "processing"}


@router.get("/export/{export_id}")
def get_comparison_export_status(
    export_id: str,
    current_user: models.User = Depends(deps.get_current_user),
) -> Any:
    data = get_redis().get(f"export:{export_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Export not found or expired")
    payload = json.loads(data)
    if payload.get("org_id") != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Export not found or expired")
    return payload
