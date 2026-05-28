from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, case, select, extract, literal_column
from datetime import datetime

from app.models.location import Location
from app.models.review import Review
from app.constants.sla import get_sla_tier
from app.schemas.sla import LocationSLAMetrics, LocationSLASummary

async def get_location_sla_metrics(
    location_id: int,
    organization_id: int,
    db: Session
) -> LocationSLAMetrics:
    # 1. Fetch location
    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == organization_id
    ).first()

    if not location or not location.sla_tracking_started_at:
        return LocationSLAMetrics(
            location_id=location_id,
            sla_enabled=False,
            sla_tracking_started_at=None,
            total_replied=0,
            avg_response_hours=None,
            best_response_hours=None,
            worst_response_hours=None,
            tier_best_count=0,
            tier_good_count=0,
            tier_average_count=0,
            tier_poor_count=0,
            avg_sla_tier=None,
            pending_count=0,
            overdue_count=0
        )

    started_at = location.sla_tracking_started_at

    # Response hours logic
    response_hours_expr = func.extract('epoch', Review.reply_created_at - Review.review_created_at) / 3600.0

    # 2. Single aggregate query for replied reviews
    replied_stats = db.query(
        func.count(Review.id).label("total_replied"),
        func.avg(response_hours_expr).label("avg_resp"),
        func.min(response_hours_expr).label("best_resp"),
        func.max(response_hours_expr).label("worst_resp"),
        func.sum(case((response_hours_expr <= 12, 1), else_=0)).label("best_count"),
        func.sum(case(((response_hours_expr > 12) & (response_hours_expr <= 24), 1), else_=0)).label("good_count"),
        func.sum(case(((response_hours_expr > 24) & (response_hours_expr <= 72), 1), else_=0)).label("avg_count"),
        func.sum(case((response_hours_expr > 72, 1), else_=0)).label("poor_count")
    ).filter(
        Review.location_id == location_id,
        Review.is_deleted == False,
        Review.review_created_at >= started_at,
        Review.is_replied == True,
        Review.reply_created_at != None
    ).first()

    # 3. Query for unreplied
    age_hours_expr = func.extract('epoch', func.now() - Review.review_created_at) / 3600.0

    unreplied_stats = db.query(
        func.count(Review.id).label("pending_count"),
        func.sum(case((age_hours_expr > 72, 1), else_=0)).label("overdue_count")
    ).filter(
        Review.location_id == location_id,
        Review.is_deleted == False,
        Review.review_created_at >= started_at,
        Review.is_replied == False
    ).first()

    total_replied = replied_stats.total_replied if replied_stats and replied_stats.total_replied else 0
    avg_resp = round(float(replied_stats.avg_resp), 1) if replied_stats and replied_stats.avg_resp is not None else None
    
    avg_tier = get_sla_tier(avg_resp) if avg_resp is not None else None

    return LocationSLAMetrics(
        location_id=location_id,
        sla_enabled=True,
        sla_tracking_started_at=started_at,
        total_replied=total_replied,
        avg_response_hours=avg_resp,
        best_response_hours=float(replied_stats.best_resp) if replied_stats and replied_stats.best_resp is not None else None,
        worst_response_hours=float(replied_stats.worst_resp) if replied_stats and replied_stats.worst_resp is not None else None,
        tier_best_count=int(replied_stats.best_count or 0),
        tier_good_count=int(replied_stats.good_count or 0),
        tier_average_count=int(replied_stats.avg_count or 0),
        tier_poor_count=int(replied_stats.poor_count or 0),
        avg_sla_tier=avg_tier,
        pending_count=int(unreplied_stats.pending_count or 0),
        overdue_count=int(unreplied_stats.overdue_count or 0)
    )


async def get_organization_sla_summary(
    organization_id: int,
    db: Session
) -> List[LocationSLASummary]:
    response_hours_expr = func.extract('epoch', Review.reply_created_at - Review.review_created_at) / 3600.0
    age_hours_expr = func.extract('epoch', func.now() - Review.review_created_at) / 3600.0

    # 1. Fetch all locations for org
    locations = db.query(Location).filter(
        Location.organization_id == organization_id
    ).all()

    if not locations:
        return []

    # 2. Aggregate replied stats for org
    replied_stats = db.query(
        Review.location_id,
        func.count(Review.id).label("total_replied"),
        func.avg(response_hours_expr).label("avg_resp")
    ).join(
        Location, Review.location_id == Location.id
    ).filter(
        Review.organization_id == organization_id,
        Review.is_deleted == False,
        Review.is_replied == True,
        Review.reply_created_at != None,
        Location.sla_tracking_started_at != None,
        Review.review_created_at >= Location.sla_tracking_started_at
    ).group_by(Review.location_id).all()

    # 3. Aggregate unreplied stats for org
    unreplied_stats = db.query(
        Review.location_id,
        func.count(Review.id).label("pending_count"),
        func.sum(case((age_hours_expr > 72, 1), else_=0)).label("overdue_count")
    ).join(
        Location, Review.location_id == Location.id
    ).filter(
        Review.organization_id == organization_id,
        Review.is_deleted == False,
        Review.is_replied == False,
        Location.sla_tracking_started_at != None,
        Review.review_created_at >= Location.sla_tracking_started_at
    ).group_by(Review.location_id).all()

    replied_map = {row.location_id: row for row in replied_stats}
    unreplied_map = {row.location_id: row for row in unreplied_stats}

    results = []
    for loc in locations:
        if not loc.sla_tracking_started_at:
            results.append(LocationSLASummary(
                location_id=loc.id,
                location_name=loc.location_name,
                sla_enabled=False,
                sla_tracking_started_at=None,
                avg_response_hours=None,
                avg_sla_tier=None,
                total_replied=0,
                overdue_count=0,
                pending_count=0
            ))
            continue

        r_stat = replied_map.get(loc.id)
        u_stat = unreplied_map.get(loc.id)

        total_replied = int(r_stat.total_replied) if r_stat else 0
        avg_resp = round(float(r_stat.avg_resp), 1) if r_stat and r_stat.avg_resp is not None else None
        
        pending_count = int(u_stat.pending_count) if u_stat else 0
        overdue_count = int(u_stat.overdue_count) if u_stat else 0

        avg_tier = get_sla_tier(avg_resp) if avg_resp is not None else None

        results.append(LocationSLASummary(
            location_id=loc.id,
            location_name=loc.location_name,
            sla_enabled=True,
            sla_tracking_started_at=loc.sla_tracking_started_at,
            avg_response_hours=avg_resp,
            avg_sla_tier=avg_tier,
            total_replied=total_replied,
            overdue_count=overdue_count,
            pending_count=pending_count
        ))

    enabled = [r for r in results if r.sla_enabled]
    disabled = [r for r in results if not r.sla_enabled]

    def sort_key(x):
        if x.avg_response_hours is None:
            return float('inf')
        return x.avg_response_hours

    enabled.sort(key=sort_key)
    return enabled + disabled
