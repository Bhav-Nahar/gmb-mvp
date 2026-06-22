import datetime
import io
import csv
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.api import deps
from app.db.session import SessionLocal
from app.models.user import User
from app.models.location import Location
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.core import leaderboard_config

logger = logging.getLogger(__name__)

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

router = APIRouter()

def get_scoped_snapshots(db: Session, org_id: int, period: str, allowed_ids: Optional[List[int]]) -> List[LeaderboardSnapshot]:
    query = db.query(LeaderboardSnapshot).join(
        Location, Location.id == LeaderboardSnapshot.location_id
    ).options(
        joinedload(LeaderboardSnapshot.location)
    ).filter(
        LeaderboardSnapshot.organization_id == org_id,
        LeaderboardSnapshot.period_label == period
    )
    if allowed_ids is not None:
        query = query.filter(LeaderboardSnapshot.location_id.in_(allowed_ids))
    return query.all()

@router.get("")
def get_leaderboard(
    period: Optional[str] = Query(None),
    sort_by: str = Query("composite_score"),
    sort_order: str = Query("desc"),
    limit: int = Query(1000, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    allowed_ids = deps.get_user_location_ids(current_user, db)
    
    if not period:
        latest_period = db.query(LeaderboardSnapshot.period_label).filter(
            LeaderboardSnapshot.organization_id == current_user.organization_id
        ).order_by(LeaderboardSnapshot.period_label.desc()).first()
        if latest_period:
            period = latest_period[0]
        else:
            return {
                "has_data": False,
                "period": None,
                "snapshot_version": leaderboard_config.LEADERBOARD_SCORING_VERSION,
                "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "organization_benchmark": {},
                "awards": {},
                "eligible_locations": [],
                "ineligible_locations": []
            }
            
    snapshots = get_scoped_snapshots(db, current_user.organization_id, period, allowed_ids)
    
    if not snapshots:
        return {
            "has_data": False,
            "period": period,
            "snapshot_version": leaderboard_config.LEADERBOARD_SCORING_VERSION,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "organization_benchmark": {},
            "awards": {},
            "eligible_locations": [],
            "ineligible_locations": []
        }
        
    generated_at = snapshots[0].created_at.isoformat() if snapshots[0].created_at else None
    snapshot_version = snapshots[0].snapshot_version
        
    eligible = []
    ineligible = []
    for s in snapshots:
        contribs = {}
        if s.is_eligible:
            from app.services.leaderboard_service import LeaderboardService
            w = LeaderboardService.effective_weights(s.health_score_input is not None)
            contribs = {
                "average_rating": round((s.rating_score or 0) * w.get("average_rating", 0), 2),
                "health_score": round((s.health_score_input or 0) * w.get("health_score", 0), 2),
                "review_volume": round((s.review_volume_score or 0) * w.get("review_volume", 0), 2),
                "review_velocity": round((s.review_velocity_score or 0) * w.get("review_velocity", 0), 2),
                "response_rate": round((s.response_rate_score or 0) * w.get("response_rate", 0), 2),
            }
        
        item = {
            "location_id": s.location_id,
            "location_name": s.location.location_name,
            "period_label": s.period_label,
            "is_eligible": s.is_eligible,
            "ineligibility_reason": s.ineligibility_reason,
            "composite_score": round(s.composite_score, 2) if s.composite_score is not None else None,
            "rank": s.rank,
            "previous_rank": s.previous_rank,
            "rank_movement": s.rank_movement,
            "cohort": s.cohort,
            "cohort_rank": s.cohort_rank,
            "cohort_size": s.cohort_size,
            "streak_count": s.streak_count,
            "most_improved_flag": s.most_improved_flag,
            "average_rating_raw": round(s.average_rating_raw, 2) if s.average_rating_raw is not None else None,
            "response_rate_raw": round(s.response_rate_raw, 2) if s.response_rate_raw is not None else None,
            "health_score_raw": round(s.health_score_raw, 2) if s.health_score_raw is not None else None,
            "review_volume_raw": s.review_volume_raw,
            "engagement_growth_raw": round(s.engagement_growth_raw, 2) if s.engagement_growth_raw is not None else None,
            "review_velocity_raw": s.review_velocity_raw,
            "rating_score": round(s.rating_score, 2) if s.rating_score is not None else None,
            "response_rate_score": round(s.response_rate_score, 2) if s.response_rate_score is not None else None,
            "health_score_input": round(s.health_score_input, 2) if s.health_score_input is not None else None,
            "review_volume_score": round(s.review_volume_score, 2) if s.review_volume_score is not None else None,
            "engagement_growth_score": round(s.engagement_growth_score, 2) if s.engagement_growth_score is not None else None,
            "review_velocity_score": round(s.review_velocity_score, 2) if s.review_velocity_score is not None else None,
            "score_contributions": contribs
        }
        if s.is_eligible:
            eligible.append(item)
        else:
            ineligible.append(item)
            
    reverse = sort_order.lower() == "desc"
    # Whitelist numeric sort fields only — sorting on a string field (e.g. location_name)
    # mixed with the `or 0.0` fallback would compare str vs float and 500.
    SORTABLE = {
        "composite_score", "rank", "cohort_rank", "average_rating_raw", "health_score_raw",
        "review_volume_raw", "review_velocity_raw", "response_rate_raw", "streak_count",
    }
    sort_key = sort_by if sort_by in SORTABLE else "composite_score"
    eligible.sort(key=lambda x: x.get(sort_key) or 0.0, reverse=reverse)
    
    avg_rating = 0
    total_reviews = 0
    health = 0
    if eligible:
        valid_rating = [e.get("average_rating_raw") for e in eligible if e.get("average_rating_raw") is not None]
        valid_health = [e.get("health_score_raw") for e in eligible if e.get("health_score_raw") is not None]
        
        avg_rating = sum(valid_rating) / len(valid_rating) if valid_rating else 0
        total_reviews = sum(e.get("review_volume_raw") or 0 for e in eligible)
        health = sum(valid_health) / len(valid_health) if valid_health else 0
        
    benchmark = {
        "average_rating_raw": round(avg_rating, 2) if eligible else None,
        "total_reviews": total_reviews if eligible else None,
        "health_score_raw": round(health, 2) if eligible else None
    }
    
    top_performer = next((e for e in eligible if e["rank"] == 1), None)
    most_improved = next((e for e in eligible if e.get("most_improved_flag")), None)
    highest_rated = max(eligible, key=lambda x: x.get("average_rating_raw") or 0.0, default=None) if eligible else None
    highest_review_velocity = max(eligible, key=lambda x: x.get("review_velocity_raw") or 0, default=None) if eligible else None

    def _format_award(loc, value_key=None):
        if not loc: return None
        res = {"location_id": loc["location_id"], "location_name": loc["location_name"]}
        if value_key:
            res[value_key] = loc.get(value_key)
        return res
        
    awards = {
        "top_performer": _format_award(top_performer, "composite_score"),
        "most_improved": _format_award(most_improved, "rank_movement"),
        "highest_rated": _format_award(highest_rated, "average_rating_raw"),
        "highest_review_velocity": _format_award(highest_review_velocity, "review_velocity_raw")
    }
    
    # Awards/benchmark above are computed over the full set; only the returned rows are
    # paged so the payload stays bounded for large orgs (top-1000 cap, offset to page).
    total_eligible = len(eligible)
    total_ineligible = len(ineligible)
    eligible_page = eligible[offset:offset + limit]
    ineligible_page = ineligible[offset:offset + limit]

    return {
        "has_data": True,
        "period": period,
        "snapshot_version": snapshot_version,
        "generated_at": generated_at,
        "organization_benchmark": benchmark,
        "awards": awards,
        "eligible_locations": eligible_page,
        "ineligible_locations": ineligible_page,
        "total_eligible": total_eligible,
        "total_ineligible": total_ineligible,
        "has_more": (offset + limit) < max(total_eligible, total_ineligible),
    }

@router.get("/periods")
def get_periods(
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    periods = db.query(LeaderboardSnapshot.period_label).filter(
        LeaderboardSnapshot.organization_id == current_user.organization_id
    ).distinct().order_by(LeaderboardSnapshot.period_label.desc()).all()
    return [p[0] for p in periods]

@router.get("/{location_id}/history")
def get_history(
    location_id: int = Depends(deps.require_location_access),
    limit: int = Query(12, ge=1, le=24),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    history = db.query(LeaderboardSnapshot).filter(
        LeaderboardSnapshot.organization_id == current_user.organization_id,
        LeaderboardSnapshot.location_id == location_id
    ).order_by(LeaderboardSnapshot.period_label.desc()).limit(limit).all()
    
    history.reverse()
    
    return [
        {
            "period_label": h.period_label,
            "composite_score": round(h.composite_score, 2) if h.composite_score is not None else None,
            "rank": h.rank,
            "is_eligible": h.is_eligible
        }
        for h in history
    ]

@router.get("/{location_id}/explain")
def get_explain(
    location_id: int = Depends(deps.require_location_access),
    period: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    if not period:
        latest_period = db.query(LeaderboardSnapshot.period_label).filter(
            LeaderboardSnapshot.organization_id == current_user.organization_id,
            LeaderboardSnapshot.location_id == location_id
        ).order_by(LeaderboardSnapshot.period_label.desc()).first()
        if not latest_period:
            return {"has_data": False}
        period = latest_period[0]
        
    current = db.query(LeaderboardSnapshot).filter(
        LeaderboardSnapshot.organization_id == current_user.organization_id,
        LeaderboardSnapshot.location_id == location_id,
        LeaderboardSnapshot.period_label == period
    ).first()
    
    if not current:
        return {"has_data": False}
        
    try:
        year, month = map(int, period.split('-'))
        if month == 1:
            prior_period = f"{year - 1}-12"
        else:
            prior_period = f"{year}-{month - 1:02d}"
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid period format. Expected YYYY-MM.")
        
    previous = db.query(LeaderboardSnapshot).filter(
        LeaderboardSnapshot.organization_id == current_user.organization_id,
        LeaderboardSnapshot.location_id == location_id,
        LeaderboardSnapshot.period_label == prior_period
    ).first()
    
    if not previous or not previous.is_eligible:
        return {
            "location_id": location_id,
            "current_period": period,
            "previous_period": None,
            "rank_movement": None,
            "from_rank": None,
            "to_rank": current.rank,
            "deltas": None,
            "score_contribution_deltas": None
        }
        
    def _delta(key):
        fr = getattr(previous, key) or 0
        to = getattr(current, key) or 0
        return {"from": round(fr, 2), "to": round(to, 2), "change": round(to - fr, 2)}
        
    deltas = {
        "average_rating_raw": _delta("average_rating_raw"),
        "health_score_raw": _delta("health_score_raw"),
        "review_volume_raw": _delta("review_volume_raw"),
        "review_velocity_raw": _delta("review_velocity_raw"),
        "response_rate_raw": _delta("response_rate_raw")
    }
    
    w = leaderboard_config.LEADERBOARD_METRIC_WEIGHTS
    def _score_delta(key, weight_key):
        fr_score = getattr(previous, key) or 0
        to_score = getattr(current, key) or 0
        return round(((to_score - fr_score) * w.get(weight_key, 0)), 2)
        
    contrib_deltas = {
        "average_rating": _score_delta("rating_score", "average_rating"),
        "health_score": _score_delta("health_score_input", "health_score"),
        "review_volume": _score_delta("review_volume_score", "review_volume"),
        "review_velocity": _score_delta("review_velocity_score", "review_velocity"),
        "response_rate": _score_delta("response_rate_score", "response_rate")
    }
    
    return {
        "location_id": location_id,
        "current_period": period,
        "previous_period": prior_period,
        "rank_movement": current.rank_movement,
        "from_rank": previous.rank,
        "to_rank": current.rank,
        "deltas": deltas,
        "score_contribution_deltas": contrib_deltas
    }

@router.get("/{location_id}/next-action")
def get_next_action(
    location_id: int = Depends(deps.require_location_access),
    period: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    if not period:
        latest = db.query(LeaderboardSnapshot.period_label).filter(
            LeaderboardSnapshot.organization_id == current_user.organization_id,
            LeaderboardSnapshot.location_id == location_id
        ).order_by(LeaderboardSnapshot.period_label.desc()).first()
        if not latest:
            return {"has_data": False, "next_action": None}
        period = latest[0]

    current = db.query(LeaderboardSnapshot).filter(
        LeaderboardSnapshot.organization_id == current_user.organization_id,
        LeaderboardSnapshot.location_id == location_id,
        LeaderboardSnapshot.period_label == period
    ).first()
    if not current:
        return {"has_data": False, "next_action": None}

    from app.services.leaderboard_service import LeaderboardService
    # Cohort peers = same org/period/cohort (the within-band group used for projected rank).
    peers = db.query(LeaderboardSnapshot).filter(
        LeaderboardSnapshot.organization_id == current_user.organization_id,
        LeaderboardSnapshot.period_label == period,
        LeaderboardSnapshot.cohort == current.cohort
    ).all()

    return {
        "has_data": True,
        "location_id": location_id,
        "period": period,
        "cohort": current.cohort,
        "is_eligible": current.is_eligible,
        "ineligibility_reason": current.ineligibility_reason,
        "next_action": LeaderboardService.compute_next_action(current, peers)
    }

@router.get("/export")
def export_leaderboard(
    period: Optional[str] = Query(None),
    format: str = Query("csv"),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    allowed_ids = deps.get_user_location_ids(current_user, db)
    
    if not period:
        latest_period = db.query(LeaderboardSnapshot.period_label).filter(
            LeaderboardSnapshot.organization_id == current_user.organization_id
        ).order_by(LeaderboardSnapshot.period_label.desc()).first()
        if latest_period:
            period = latest_period[0]
        else:
            period = ""
            
    query = db.query(LeaderboardSnapshot).join(
        Location, Location.id == LeaderboardSnapshot.location_id
    ).options(
        joinedload(LeaderboardSnapshot.location)
    ).filter(
        LeaderboardSnapshot.organization_id == current_user.organization_id,
        LeaderboardSnapshot.period_label == period
    )

    if allowed_ids is not None:
        query = query.filter(LeaderboardSnapshot.location_id.in_(allowed_ids))
        
    query = query.order_by(
        LeaderboardSnapshot.is_eligible.desc(),
        LeaderboardSnapshot.rank.asc()
    )

    # ponytail: hard cap on export size; if an org ever exceeds this, raise the cap or paginate.
    EXPORT_ROW_CAP = 50000
    if query.count() > EXPORT_ROW_CAP:
        logger.warning(
            f"Leaderboard export for org {current_user.organization_id} period {period} "
            f"exceeds {EXPORT_ROW_CAP} rows; output truncated."
        )
    
    headers = [
        "Location Name", "Period", "Eligible", "Rank", "Composite Score", 
        "Rating (Raw)", "Response Rate (Raw)", "Health Score (Raw)", 
        "Review Volume (Raw)", "Ineligibility Reason"
    ]
    
    if format == "xlsx" and HAS_OPENPYXL:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Leaderboard"
        ws.append(headers)
        
        for s in query.yield_per(1000).limit(EXPORT_ROW_CAP):
            ws.append([
                s.location.location_name,
                s.period_label,
                "Yes" if s.is_eligible else "No",
                s.rank if s.is_eligible else "",
                round(s.composite_score, 2) if s.composite_score is not None else "",
                round(s.average_rating_raw, 2) if s.average_rating_raw is not None else "",
                round(s.response_rate_raw, 2) if s.response_rate_raw is not None else "",
                round(s.health_score_raw, 2) if s.health_score_raw is not None else "",
                s.review_volume_raw if s.review_volume_raw is not None else "",                s.ineligibility_reason or ""
            ])
            
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=leaderboard_{period}.xlsx"}
        )
    else:
        def _row_iter():
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(headers)
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)
            
            for s in query.yield_per(1000).limit(EXPORT_ROW_CAP):
                writer.writerow([
                    s.location.location_name,
                    s.period_label,
                    "Yes" if s.is_eligible else "No",
                    s.rank if s.is_eligible else "",
                    round(s.composite_score, 2) if s.composite_score is not None else "",
                    round(s.average_rating_raw, 2) if s.average_rating_raw is not None else "",
                    round(s.response_rate_raw, 2) if s.response_rate_raw is not None else "",
                    round(s.health_score_raw, 2) if s.health_score_raw is not None else "",
                    s.review_volume_raw if s.review_volume_raw is not None else "",                    s.ineligibility_reason or ""
                ])
                yield buf.getvalue()
                buf.seek(0); buf.truncate(0)
                
        return StreamingResponse(
            _row_iter(), 
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=leaderboard_{period}.csv"}
        )

@router.post("/generate")
def generate_leaderboard(
    period: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    if current_user.role not in ["Owner", "Admin"]:
        raise HTTPException(status_code=403, detail="Only admins can generate snapshots.")
        
    if not period:
        now = datetime.datetime.now(datetime.timezone.utc)
        period = f"{now.year}-{now.month:02d}"

    from app.services.leaderboard_service import LeaderboardService
    try:
        period_start, period_end = LeaderboardService.period_to_range(period)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Same lock the monthly beat task uses, so a manual "Sync Now" can't race another
    # admin or the scheduled run (concurrent delete+insert would hit the unique constraint).
    from app.tasks import _get_redis
    lock = _get_redis().lock(
        f"lock:leaderboard_snapshot:{current_user.organization_id}:{period}", timeout=600
    )
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A generation for this period is already running. Try again shortly.")

    try:
        snapshots = LeaderboardService.generate_snapshots_for_period(
            db,
            organization_id=current_user.organization_id,
            period_label=period,
            period_start=period_start,
            period_end=period_end,
            force=True
        )
        return {
            "status": "success",
            "message": f"Generated {len(snapshots)} snapshots for period {period}",
            "period": period,
            "count": len(snapshots)
        }
    except Exception as e:
        logger.error(f"Failed to force generate snapshots: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Snapshot generation failed.")
    finally:
        try:
            lock.release()
        except Exception:
            pass
