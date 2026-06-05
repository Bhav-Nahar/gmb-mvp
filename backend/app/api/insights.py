import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import List, Optional

from app.api import deps
from app.db.session import SessionLocal
from app.models.user import User
from app.models.location import Location
from app.models.location_daily_insights import LocationDailyInsight
from app.models.review import Review
from app.schemas.insights import (
    InsightsOverviewResponse,
    LocationInsightsResponse,
    InsightsSyncPostResponse,
    OverviewKPIs,
    InsightsMetricDelta,
    DailyMetricPoint,
    LeaderboardLocation,
    SentimentBreakdown,
    SLAMetricsSummary,
    IssueCategorySummary
)
from app.worker import celery

router = APIRouter()

def calculate_delta(curr: float, prior: float) -> Optional[float]:
    if prior == 0:
        return None
    return ((curr - prior) / prior) * 100.0

@router.get("/overview", response_model=InsightsOverviewResponse)
def get_insights_overview(
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get organization-wide aggregate metrics, trend lines, and a locations leaderboard.
    """
    # Enforce multi-tenancy locations access
    allowed_ids = deps.get_user_location_ids(current_user, db)
    
    # 1. Setup date ranges (default to last 30 days)
    if not end_date:
        end_date = datetime.date.today() - datetime.timedelta(days=1)
    if not start_date:
        start_date = end_date - datetime.timedelta(days=29)
        
    duration = (end_date - start_date).days + 1
    prior_end_date = start_date - datetime.timedelta(days=1)
    prior_start_date = prior_end_date - datetime.timedelta(days=duration - 1)

    # 2. Query location ID filters
    loc_filter_clause = ""
    loc_params = {"org_id": current_user.organization_id}
    if allowed_ids is not None:
        if not allowed_ids:
            # User has no access to any locations
            return InsightsOverviewResponse(
                kpis=OverviewKPIs(
                    profile_views=InsightsMetricDelta(current=0, prior=0),
                    search_impressions=InsightsMetricDelta(current=0, prior=0),
                    maps_views=InsightsMetricDelta(current=0, prior=0),
                    phone_calls=InsightsMetricDelta(current=0, prior=0),
                    website_clicks=InsightsMetricDelta(current=0, prior=0),
                    direction_requests=InsightsMetricDelta(current=0, prior=0)
                ),
                trends=[],
                leaderboard=[],
                attention_locations_count=0
            )
        loc_filter_clause = "AND location_id IN :allowed_ids"
        loc_params["allowed_ids"] = tuple(allowed_ids)

    # 3. Retrieve Current and Prior Aggregates for KPIs
    kpi_query = text(f"""
        SELECT 
            COALESCE(SUM(profile_views), 0) AS profile_views,
            COALESCE(SUM(search_impressions), 0) AS search_impressions,
            COALESCE(SUM(maps_views), 0) AS maps_views,
            COALESCE(SUM(phone_calls), 0) AS phone_calls,
            COALESCE(SUM(website_clicks), 0) AS website_clicks,
            COALESCE(SUM(direction_requests), 0) AS direction_requests
        FROM location_daily_insights
        WHERE organization_id = :org_id
          AND date BETWEEN :start AND :end
          {loc_filter_clause}
    """)
    
    curr_res = db.execute(kpi_query, {**loc_params, "start": start_date, "end": end_date}).fetchone()
    prior_res = db.execute(kpi_query, {**loc_params, "start": prior_start_date, "end": prior_end_date}).fetchone()

    kpis = OverviewKPIs(
        profile_views=InsightsMetricDelta(
            current=curr_res.profile_views,
            prior=prior_res.profile_views,
            percentage_change=calculate_delta(curr_res.profile_views, prior_res.profile_views)
        ),
        search_impressions=InsightsMetricDelta(
            current=curr_res.search_impressions,
            prior=prior_res.search_impressions,
            percentage_change=calculate_delta(curr_res.search_impressions, prior_res.search_impressions)
        ),
        maps_views=InsightsMetricDelta(
            current=curr_res.maps_views,
            prior=prior_res.maps_views,
            percentage_change=calculate_delta(curr_res.maps_views, prior_res.maps_views)
        ),
        phone_calls=InsightsMetricDelta(
            current=curr_res.phone_calls,
            prior=prior_res.phone_calls,
            percentage_change=calculate_delta(curr_res.phone_calls, prior_res.phone_calls)
        ),
        website_clicks=InsightsMetricDelta(
            current=curr_res.website_clicks,
            prior=prior_res.website_clicks,
            percentage_change=calculate_delta(curr_res.website_clicks, prior_res.website_clicks)
        ),
        direction_requests=InsightsMetricDelta(
            current=curr_res.direction_requests,
            prior=prior_res.direction_requests,
            percentage_change=calculate_delta(curr_res.direction_requests, prior_res.direction_requests)
        )
    )

    # 4. Get Time Series Trends (aggregating by date)
    trend_query = text(f"""
        SELECT 
            date,
            SUM(profile_views) AS profile_views,
            SUM(search_impressions) AS search_impressions,
            SUM(maps_views) AS maps_views,
            SUM(phone_calls) AS phone_calls,
            SUM(website_clicks) AS website_clicks,
            SUM(direction_requests) AS direction_requests,
            SUM(searches_direct) AS searches_direct,
            SUM(searches_indirect) AS searches_indirect,
            SUM(searches_chain) AS searches_chain,
            SUM(reviews_received) AS reviews_received,
            AVG(avg_rating) AS avg_rating
        FROM location_daily_insights
        WHERE organization_id = :org_id
          AND date BETWEEN :start AND :end
          {loc_filter_clause}
        GROUP BY date
        ORDER BY date ASC
    """)
    trend_res = db.execute(trend_query, {**loc_params, "start": start_date, "end": end_date}).fetchall()
    
    trends = [
        DailyMetricPoint(
            date=row.date,
            profile_views=row.profile_views,
            search_impressions=row.search_impressions,
            maps_views=row.maps_views,
            phone_calls=row.phone_calls,
            website_clicks=row.website_clicks,
            direction_requests=row.direction_requests,
            searches_direct=row.searches_direct,
            searches_indirect=row.searches_indirect,
            searches_chain=row.searches_chain,
            reviews_received=row.reviews_received,
            avg_rating=float(row.avg_rating) if row.avg_rating is not None else None
        )
        for row in trend_res
    ]

    # 5. Leaderboard of Top Locations
    leaderboard_query = text(f"""
        SELECT 
            l.id AS location_id,
            l.location_name,
            COALESCE(SUM(i.profile_views), 0) AS profile_views,
            COALESCE(SUM(i.search_impressions), 0) AS search_impressions,
            COALESCE(SUM(i.reviews_received), 0) AS reviews_count,
            AVG(i.avg_rating) AS avg_rating
        FROM locations l
        LEFT JOIN location_daily_insights i ON l.id = i.location_id AND i.date BETWEEN :start AND :end
        WHERE l.organization_id = :org_id
          {"" if allowed_ids is None else "AND l.id IN :allowed_ids"}
        GROUP BY l.id, l.location_name
        ORDER BY profile_views DESC
        LIMIT 10
    """)
    leaderboard_res = db.execute(leaderboard_query, {**loc_params, "start": start_date, "end": end_date}).fetchall()
    
    leaderboard = [
        LeaderboardLocation(
            location_id=row.location_id,
            location_name=row.location_name,
            profile_views=row.profile_views,
            search_impressions=row.search_impressions,
            reviews_count=row.reviews_count,
            avg_rating=float(row.avg_rating) if row.avg_rating is not None else None
        )
        for row in leaderboard_res
    ]

    # 6. Count locations needing attention
    attention_query = db.query(func.count(Location.id)).filter(
        Location.organization_id == current_user.organization_id,
        Location.attention_needed == True
    )
    if allowed_ids is not None:
        attention_query = attention_query.filter(Location.id.in_(allowed_ids))
    attention_count = attention_query.scalar() or 0

    # Auto-trigger synchronization if stale (cached-first logic)
    try:
        check_and_trigger_stale_insights_sync(current_user.organization_id, db)
    except Exception as e:
        # Prevent sync errors from blocking data display
        import logging
        logging.getLogger(__name__).error(f"Failed to check/trigger insights sync on overview load: {str(e)}")

    return InsightsOverviewResponse(
        kpis=kpis,
        trends=trends,
        leaderboard=leaderboard,
        attention_locations_count=attention_count
    )


@router.get("/locations/{id}", response_model=LocationInsightsResponse)
def get_location_insights(
    id: int,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get detailed metrics, daily trend lines, sentiment breakdowns, SLA statuses,
    and top issue categories for a specific location.
    """
    # Enforce organization boundaries
    location = db.query(Location).filter(
        Location.id == id,
        Location.organization_id == current_user.organization_id
    ).first()
    
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found or access denied."
        )

    # Enforce granular UserLocationAccess checks
    allowed_ids = deps.get_user_location_ids(current_user, db)
    if allowed_ids is not None and id not in allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this location's insights."
        )

    # Setup ranges (default to last 30 days)
    if not end_date:
        end_date = datetime.date.today() - datetime.timedelta(days=1)
    if not start_date:
        start_date = end_date - datetime.timedelta(days=29)

    duration = (end_date - start_date).days + 1
    prior_end_date = start_date - datetime.timedelta(days=1)
    prior_start_date = prior_end_date - datetime.timedelta(days=duration - 1)

    # 1. KPI delta comparisons
    kpi_query = text("""
        SELECT 
            COALESCE(SUM(profile_views), 0) AS profile_views,
            COALESCE(SUM(search_impressions), 0) AS search_impressions,
            COALESCE(SUM(maps_views), 0) AS maps_views,
            COALESCE(SUM(phone_calls), 0) AS phone_calls,
            COALESCE(SUM(website_clicks), 0) AS website_clicks,
            COALESCE(SUM(direction_requests), 0) AS direction_requests
        FROM location_daily_insights
        WHERE location_id = :location_id
          AND date BETWEEN :start AND :end
    """)
    
    curr_res = db.execute(kpi_query, {"location_id": id, "start": start_date, "end": end_date}).fetchone()
    prior_res = db.execute(kpi_query, {"location_id": id, "start": prior_start_date, "end": prior_end_date}).fetchone()

    kpis = OverviewKPIs(
        profile_views=InsightsMetricDelta(
            current=curr_res.profile_views,
            prior=prior_res.profile_views,
            percentage_change=calculate_delta(curr_res.profile_views, prior_res.profile_views)
        ),
        search_impressions=InsightsMetricDelta(
            current=curr_res.search_impressions,
            prior=prior_res.search_impressions,
            percentage_change=calculate_delta(curr_res.search_impressions, prior_res.search_impressions)
        ),
        maps_views=InsightsMetricDelta(
            current=curr_res.maps_views,
            prior=prior_res.maps_views,
            percentage_change=calculate_delta(curr_res.maps_views, prior_res.maps_views)
        ),
        phone_calls=InsightsMetricDelta(
            current=curr_res.phone_calls,
            prior=prior_res.phone_calls,
            percentage_change=calculate_delta(curr_res.phone_calls, prior_res.phone_calls)
        ),
        website_clicks=InsightsMetricDelta(
            current=curr_res.website_clicks,
            prior=prior_res.website_clicks,
            percentage_change=calculate_delta(curr_res.website_clicks, prior_res.website_clicks)
        ),
        direction_requests=InsightsMetricDelta(
            current=curr_res.direction_requests,
            prior=prior_res.direction_requests,
            percentage_change=calculate_delta(curr_res.direction_requests, prior_res.direction_requests)
        )
    )

    # 2. Get Daily Trends
    insights = db.query(LocationDailyInsight).filter(
        LocationDailyInsight.location_id == id,
        LocationDailyInsight.date >= start_date,
        LocationDailyInsight.date <= end_date
    ).order_by(LocationDailyInsight.date.asc()).all()

    trends = [
        DailyMetricPoint(
            date=item.date,
            profile_views=item.profile_views,
            search_impressions=item.search_impressions,
            maps_views=item.maps_views,
            phone_calls=item.phone_calls,
            website_clicks=item.website_clicks,
            direction_requests=item.direction_requests,
            searches_direct=item.searches_direct,
            searches_indirect=item.searches_indirect,
            searches_chain=item.searches_chain,
            reviews_received=item.reviews_received,
            avg_rating=item.avg_rating
        )
        for item in insights
    ]

    # 3. Sentiment breakdown (aggregate counts)
    pos_count = sum(i.positive_review_count for i in insights)
    neu_count = sum(i.neutral_review_count for i in insights)
    neg_count = sum(i.negative_review_count for i in insights)
    total_rev = pos_count + neu_count + neg_count
    
    if total_rev > 0:
        pos_pct = (pos_count / total_rev) * 100.0
        neu_pct = (neu_count / total_rev) * 100.0
        neg_pct = (neg_count / total_rev) * 100.0
    else:
        pos_pct = neu_pct = neg_pct = 0.0

    sentiment = SentimentBreakdown(
        positive=pos_count,
        neutral=neu_count,
        negative=neg_count,
        positive_percentage=pos_pct,
        neutral_percentage=neu_pct,
        negative_percentage=neg_pct
    )

    # 4. SLA Summary details
    reviews_count = sum(i.reviews_received for i in insights)
    total_replied = sum(int(i.reviews_received * (i.response_rate / 100.0)) for i in insights)
    
    sla_resp_rate = (total_replied / reviews_count) * 100.0 if reviews_count > 0 else 0.0
    
    # Calculate weighted average response time in hours
    total_time_hours = 0.0
    reviews_with_time = 0
    for i in insights:
        if i.avg_response_time_hours is not None and i.reviews_received > 0:
            replies_in_day = int(i.reviews_received * (i.response_rate / 100.0))
            if replies_in_day > 0:
                total_time_hours += i.avg_response_time_hours * replies_in_day
                reviews_with_time += replies_in_day

    avg_time = (total_time_hours / reviews_with_time) if reviews_with_time > 0 else None

    sla = SLAMetricsSummary(
        total_reviews=reviews_count,
        replied_reviews=total_replied,
        response_rate=sla_resp_rate,
        avg_response_time_hours=avg_time
    )

    # 5. Top issue categories aggregated directly via SQL (using existing sentiment reviews tagging)
    issue_query = text("""
        SELECT issue_category, COUNT(*) AS count
        FROM reviews
        WHERE location_id = :location_id
          AND issue_category IS NOT NULL
          AND is_deleted = FALSE
          AND DATE(review_created_at) BETWEEN :start AND :end
        GROUP BY issue_category
        ORDER BY count DESC
        LIMIT 10
    """)
    issues_res = db.execute(issue_query, {"location_id": id, "start": start_date, "end": end_date}).fetchall()
    
    top_issues = [
        IssueCategorySummary(category=row.issue_category, count=row.count)
        for row in issues_res
    ]

    # Auto-trigger synchronization if stale (cached-first logic)
    try:
        check_and_trigger_stale_insights_sync(current_user.organization_id, db)
    except Exception as e:
        # Prevent sync errors from blocking data display
        import logging
        logging.getLogger(__name__).error(f"Failed to check/trigger insights sync on location load: {str(e)}")

    return LocationInsightsResponse(
        location_id=location.id,
        location_name=location.location_name,
        attention_needed=location.attention_needed,
        attention_reason=location.attention_reason,
        last_insights_sync_at=location.last_insights_sync_at,
        kpis=kpis,
        trends=trends,
        sentiment=sentiment,
        sla=sla,
        top_issue_categories=top_issues
    )


@router.get("/sync-status")
def get_insights_sync_status(
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Get the synchronization status for the user's organization insights.
    """
    from app.models.organization_sync_state import OrganizationSyncState
    state = db.query(OrganizationSyncState).filter(
        OrganizationSyncState.organization_id == current_user.organization_id
    ).first()
    
    if not state:
        return {
            "insights_sync_in_progress": False,
            "last_insights_sync_status": "never_synced",
            "last_insights_sync_at": None,
            "last_insights_sync_started_at": None,
            "last_insights_sync_completed_at": None,
            "last_insights_sync_error": None
        }
        
    return {
        "insights_sync_in_progress": state.insights_sync_in_progress,
        "last_insights_sync_status": state.last_insights_sync_status,
        "last_insights_sync_at": state.last_insights_sync_at,
        "last_insights_sync_started_at": state.last_insights_sync_started_at,
        "last_insights_sync_completed_at": state.last_insights_sync_completed_at,
        "last_insights_sync_error": state.last_insights_sync_error
    }


def check_and_trigger_stale_insights_sync(organization_id: int, db: Session, force: bool = False) -> dict:
    """
    Evaluate organization-level insights freshness and trigger background sync if stale or forced.
    Returns a dict with 'triggered' bool and 'reason' string.
    """
    import datetime
    from app.models.organization_sync_state import OrganizationSyncState

    state = db.query(OrganizationSyncState).filter(
        OrganizationSyncState.organization_id == organization_id
    ).first()

    stale = False
    run_type = "State-Aware (On-Load)"
    if force:
        stale = True
        run_type = "Manual"
    elif not state or not state.last_insights_sync_at:
        stale = True
    else:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
        sync_time = state.last_insights_sync_at
        if sync_time.tzinfo is None:
            sync_time = sync_time.replace(tzinfo=datetime.timezone.utc)
        if sync_time < cutoff:
            stale = True

    # Do not trigger if already syncing and not stuck
    if state and state.insights_sync_in_progress:
        stale = False
        # Stuck state detection (e.g. >2 hours since start)
        if state.last_insights_sync_started_at:
            started_time = state.last_insights_sync_started_at
            if started_time.tzinfo is None:
                started_time = started_time.replace(tzinfo=datetime.timezone.utc)
            stuck_cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
            if started_time < stuck_cutoff:
                stale = True  # It's stuck, override and trigger
                run_type = "Stuck Recovery"

    if stale:
        # Default start date is last 90 days, end date is yesterday
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        start_date = yesterday - datetime.timedelta(days=90)

        celery.send_task(
            "app.tasks.sync_organization_insights_task",
            args=[organization_id, start_date.isoformat(), yesterday.isoformat(), run_type, force]
        )
        return {"triggered": True, "reason": run_type}

    return {"triggered": False, "reason": "sync_already_in_progress" if (state and state.insights_sync_in_progress) else "data_is_fresh"}


@router.post("/locations/{id}/sync", response_model=InsightsSyncPostResponse)
def trigger_insights_sync(
    id: int,
    start_date: Optional[datetime.date] = Query(None),
    end_date: Optional[datetime.date] = Query(None),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Manually trigger performance and reputation insights synchronization for a location (now invokes organization-wide sync).
    """
    result = check_and_trigger_stale_insights_sync(current_user.organization_id, db, force=True)
    return InsightsSyncPostResponse(
        task_id="org-orchestrated",
        status="Queued" if result["triggered"] else "AlreadyRunning"
    )


@router.post("/sync-all", response_model=InsightsSyncPostResponse)
def trigger_global_insights_sync(
    force: bool = Query(True),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Manually trigger performance and reputation insights synchronization for ALL locations of the organization.
    """
    result = check_and_trigger_stale_insights_sync(current_user.organization_id, db, force=force)
    return InsightsSyncPostResponse(
        task_id="org-orchestrated",
        status="Queued" if result["triggered"] else "AlreadyRunning"
    )
