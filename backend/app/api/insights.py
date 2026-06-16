import datetime
import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from sqlalchemy import func, text, or_, case, and_
from sqlalchemy.exc import IntegrityError
from typing import List, Optional

logger = logging.getLogger(__name__)

from app.api import deps
from app.api.posts import get_redis
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
    IssueCategorySummary,
    PlatformDeviceBreakdown,
    ReputationVelocity,
    InsightsSummaryResponse,
    KeywordMetricsResponse,
    BrandTermResponse,
    BrandTermCreate,
    SearchKeywordMetric,
    KeywordKpis,
    KeywordTrendPoint,
    KeywordLocationComparison,
    KeywordSummaryResponse,
)
from app.models.keyword_monthly_metrics import KeywordMonthlyMetric
from app.models.organization_brand_terms import OrganizationBrandTerm
import io
import csv
from fastapi.responses import StreamingResponse
from app.worker import celery

router = APIRouter()

def calculate_delta(curr: float, prior: float) -> Optional[float]:
    if prior == 0:
        return None
    return ((curr - prior) / prior) * 100.0


def _review_velocity_delta(db, org_id, location_ids, start, end, prior_start, prior_end) -> InsightsMetricDelta:
    """Reviews received per day over a range, with a vs-prior-period delta.

    location_ids: None = whole org (no extra filter); a list = restrict to those
    locations; an int = a single location.
    """
    def _sum(s, e):
        q = db.query(func.coalesce(func.sum(LocationDailyInsight.reviews_received), 0)).filter(
            LocationDailyInsight.organization_id == org_id,
            LocationDailyInsight.date >= s,
            LocationDailyInsight.date <= e,
        )
        if isinstance(location_ids, int):
            q = q.filter(LocationDailyInsight.location_id == location_ids)
        elif location_ids is not None:
            q = q.filter(LocationDailyInsight.location_id.in_(location_ids))
        return q.scalar() or 0

    cur_days = (end - start).days + 1
    prior_days = (prior_end - prior_start).days + 1
    cur_rate = round(_sum(start, end) / cur_days, 2) if cur_days > 0 else 0.0
    prior_rate = round(_sum(prior_start, prior_end) / prior_days, 2) if prior_days > 0 else 0.0
    return InsightsMetricDelta(
        current=cur_rate, prior=prior_rate, percentage_change=calculate_delta(cur_rate, prior_rate)
    )


def _avg_rating_simple(db, org_id, location_ids):
    """Simple mean of each accessible location's standing average_rating.

    Range-independent: reflects the current GBP rating, weighting every location
    equally. Returns (avg_rating_or_None, rated_location_count).
    """
    q = db.query(Location.average_rating).filter(
        Location.organization_id == org_id,
        Location.average_rating.isnot(None),
    )
    if isinstance(location_ids, int):
        q = q.filter(Location.id == location_ids)
    elif location_ids is not None:
        q = q.filter(Location.id.in_(location_ids))
    ratings = [float(r[0]) for r in q.all()]
    if not ratings:
        return None, 0
    return round(sum(ratings) / len(ratings), 2), len(ratings)


def _response_rate_all_time(db, org_id, location_ids):
    """All-time review response rate (%): replied reviews ÷ total reviews.

    Computed directly from the reviews table over the full history (not a 30-day
    window), excluding deleted reviews. Returns None when there are no reviews.
    """
    # Filter Review.organization_id directly (not via a Location join) so the
    # query can use the ix_reviews_sla_lookup index that leads on organization_id.
    q = db.query(
        func.count().label("total"),
        func.coalesce(func.sum(case((Review.is_replied == True, 1), else_=0)), 0).label("replied"),  # noqa: E712
    ).filter(
        Review.organization_id == org_id,
        Review.is_deleted == False,  # noqa: E712
    )
    if isinstance(location_ids, int):
        q = q.filter(Review.location_id == location_ids)
    elif location_ids is not None:
        q = q.filter(Review.location_id.in_(location_ids))
    row = q.one()
    total = int(row.total or 0)
    if total == 0:
        return None
    return round(int(row.replied or 0) / total * 100.0, 1)


# Whitelist of sortable columns for keyword endpoints — never pass raw user
# input to getattr()/order_by() (could resolve a relationship/method -> 500).
KEYWORD_SORT_COLUMNS = {"impressions", "keyword", "period_start"}


def _brand_terms_lower(db: Session, organization_id: int) -> list:
    """Lowercased brand terms for case-insensitive substring matching."""
    rows = db.query(OrganizationBrandTerm.term).filter(
        OrganizationBrandTerm.organization_id == organization_id
    ).all()
    return [r.term.lower() for r in rows if r.term]


def _is_branded(keyword: str, brand_terms_lower: list) -> bool:
    """A keyword is branded if it contains any brand term (case-insensitive)."""
    kw = (keyword or "").lower()
    return any(term in kw for term in brand_terms_lower)


def _branded_condition(brand_terms_lower: list):
    """SQL boolean expression that is true when a keyword contains a brand term."""
    if not brand_terms_lower:
        return text("1=0")
    return or_(*[KeywordMonthlyMetric.keyword.ilike(f"%{t}%") for t in brand_terms_lower])


def _month_floor(d: datetime.date) -> datetime.date:
    return d.replace(day=1)


def _add_months(d: datetime.date, n: int) -> datetime.date:
    """Add n (can be negative) months to a month-start date."""
    m = d.month - 1 + n
    year = d.year + m // 12
    month = m % 12 + 1
    return datetime.date(year, month, 1)


def _branded_filter(brand_terms_lower: list, is_brand: bool):
    """SQLAlchemy condition: keyword contains (or not) any brand term.

    Brand classification is substring + case-insensitive (e.g. brand term
    "lucira" tags "lucira jewellery"). Exact-equality IN(...) would miss those
    and is case-sensitive against how terms are stored.
    """
    if not brand_terms_lower:
        # No brand terms => nothing is branded.
        return text("1=0") if is_brand else text("1=1")
    contains = or_(*[KeywordMonthlyMetric.keyword.ilike(f"%{t}%") for t in brand_terms_lower])
    return contains if is_brand else ~contains


def _csv_safe(value):
    """Neutralise CSV/spreadsheet formula injection.

    Keyword data originates from Google search terms (externally influenced); a
    cell beginning with = + - @ (or tab/CR) can execute as a formula in Excel/
    Sheets. Prefix such values with a single quote.
    """
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value

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

    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be on or before end_date."
        )
    if (end_date - start_date).days > 366:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Date range must not exceed 366 days."
        )

    duration = (end_date - start_date).days + 1
    prior_end_date = start_date - datetime.timedelta(days=1)
    prior_start_date = prior_end_date - datetime.timedelta(days=duration - 1)

    # 2. Query location ID filters
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

    # 2.5 Cache Check
    allowed_ids_key = ",".join(map(str, sorted(allowed_ids))) if allowed_ids is not None else "all"
    # v2: response shape gained reputation aggregates + conversion-rate trend
    # fields; bump the namespace so pre-deploy cached payloads are bypassed.
    cache_key = f"insights:overview:v4:{current_user.organization_id}:{start_date.isoformat()}:{end_date.isoformat()}:{allowed_ids_key}"
    
    redis_client = None
    try:
        redis_client = get_redis()
        cached_data = redis_client.get(cache_key)
        if cached_data:
            logger.info(f"Serving cached insights overview for org {current_user.organization_id}")
            return InsightsOverviewResponse(**json.loads(cached_data))
    except Exception as e:
        logger.error(f"Redis cache lookup failed: {e}")

    # 3. Retrieve Current and Prior Aggregates for KPIs using ORM
    def _kpi_base_query(start, end):
        q = db.query(
            func.coalesce(func.sum(LocationDailyInsight.profile_views), 0).label("profile_views"),
            func.coalesce(func.sum(LocationDailyInsight.search_impressions), 0).label("search_impressions"),
            func.coalesce(func.sum(LocationDailyInsight.maps_views), 0).label("maps_views"),
            func.coalesce(func.sum(LocationDailyInsight.phone_calls), 0).label("phone_calls"),
            func.coalesce(func.sum(LocationDailyInsight.website_clicks), 0).label("website_clicks"),
            func.coalesce(func.sum(LocationDailyInsight.direction_requests), 0).label("direction_requests"),
            func.coalesce(func.sum(LocationDailyInsight.desktop_search_impressions), 0).label("desktop_search"),
            func.coalesce(func.sum(LocationDailyInsight.mobile_search_impressions), 0).label("mobile_search"),
            func.coalesce(func.sum(LocationDailyInsight.desktop_maps_impressions), 0).label("desktop_maps"),
            func.coalesce(func.sum(LocationDailyInsight.mobile_maps_impressions), 0).label("mobile_maps"),
        ).filter(
            LocationDailyInsight.organization_id == current_user.organization_id,
            LocationDailyInsight.date >= start,
            LocationDailyInsight.date <= end,
        )
        if allowed_ids is not None:
            q = q.filter(LocationDailyInsight.location_id.in_(allowed_ids))
        return q.one()

    curr_res = _kpi_base_query(start_date, end_date)
    prior_res = _kpi_base_query(prior_start_date, prior_end_date)

    platform_device = PlatformDeviceBreakdown(
        desktop_search=curr_res.desktop_search,
        mobile_search=curr_res.mobile_search,
        desktop_maps=curr_res.desktop_maps,
        mobile_maps=curr_res.mobile_maps,
    )

    avg_rating, rated_count = _avg_rating_simple(db, current_user.organization_id, allowed_ids)
    reputation = ReputationVelocity(
        avg_rating=avg_rating,
        rated_location_count=rated_count,
        review_velocity_per_day=_review_velocity_delta(
            db, current_user.organization_id, allowed_ids,
            start_date, end_date, prior_start_date, prior_end_date,
        ),
    )

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

    # 4. Get Time Series Trends (aggregating by date) using ORM
    trend_q = db.query(
        LocationDailyInsight.date,
        func.sum(LocationDailyInsight.profile_views).label("profile_views"),
        func.sum(LocationDailyInsight.search_impressions).label("search_impressions"),
        func.sum(LocationDailyInsight.maps_views).label("maps_views"),
        func.sum(LocationDailyInsight.phone_calls).label("phone_calls"),
        func.sum(LocationDailyInsight.website_clicks).label("website_clicks"),
        func.sum(LocationDailyInsight.direction_requests).label("direction_requests"),
        func.sum(LocationDailyInsight.searches_direct).label("searches_direct"),
        func.sum(LocationDailyInsight.searches_indirect).label("searches_indirect"),
        func.sum(LocationDailyInsight.searches_chain).label("searches_chain"),
        func.sum(LocationDailyInsight.reviews_received).label("reviews_received"),
        func.avg(LocationDailyInsight.avg_rating).label("avg_rating"),
        func.avg(LocationDailyInsight.avg_sentiment_score).label("avg_sentiment_score"),
    ).filter(
        LocationDailyInsight.organization_id == current_user.organization_id,
        LocationDailyInsight.date >= start_date,
        LocationDailyInsight.date <= end_date,
    )
    if allowed_ids is not None:
        trend_q = trend_q.filter(LocationDailyInsight.location_id.in_(allowed_ids))
    trend_res = trend_q.group_by(LocationDailyInsight.date).order_by(LocationDailyInsight.date.asc()).all()

    def _rate(numer, denom):
        # Conversion rates are recomputed from the day's summed totals (a ratio
        # of sums), never an average of per-location ratios.
        return round(numer / denom * 100.0, 2) if denom else None

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
            avg_rating=float(row.avg_rating) if row.avg_rating is not None else None,
            click_through_rate=_rate(row.website_clicks, row.profile_views),
            call_conversion_rate=_rate(row.phone_calls, row.profile_views),
            direction_conversion_rate=_rate(row.direction_requests, row.profile_views),
            avg_sentiment_score=float(row.avg_sentiment_score) if row.avg_sentiment_score is not None else None,
        )
        for row in trend_res
    ]

    # 5. Leaderboard of Top Locations using ORM
    profile_views_sum = func.coalesce(func.sum(LocationDailyInsight.profile_views), 0).label("profile_views")
    leaderboard_q = db.query(
        Location.id.label("location_id"),
        Location.location_name,
        profile_views_sum,
        func.coalesce(func.sum(LocationDailyInsight.search_impressions), 0).label("search_impressions"),
        func.coalesce(func.sum(LocationDailyInsight.reviews_received), 0).label("reviews_count"),
    ).outerjoin(
        LocationDailyInsight,
        (Location.id == LocationDailyInsight.location_id) &
        (LocationDailyInsight.date >= start_date) &
        (LocationDailyInsight.date <= end_date),
    ).filter(
        Location.organization_id == current_user.organization_id,
    )
    if allowed_ids is not None:
        leaderboard_q = leaderboard_q.filter(Location.id.in_(allowed_ids))
    leaderboard_res = (
        leaderboard_q
        .group_by(Location.id, Location.location_name)
        .order_by(profile_views_sum.desc())
        .limit(10)
        .all()
    )

    # avg_rating is a cumulative standing rating reported each day, so the
    # representative value for a range is the latest day's rating per location —
    # NOT AVG() across days (which double-counts unchanged ratings and is
    # weighted by how many days were synced).
    rating_rn = func.row_number().over(
        partition_by=LocationDailyInsight.location_id,
        order_by=LocationDailyInsight.date.desc(),
    ).label("rn")
    rating_sq = db.query(
        LocationDailyInsight.location_id.label("lid"),
        LocationDailyInsight.avg_rating.label("avg_rating"),
        rating_rn,
    ).filter(
        LocationDailyInsight.organization_id == current_user.organization_id,
        LocationDailyInsight.date >= start_date,
        LocationDailyInsight.date <= end_date,
        LocationDailyInsight.avg_rating.isnot(None),
    )
    if allowed_ids is not None:
        rating_sq = rating_sq.filter(LocationDailyInsight.location_id.in_(allowed_ids))
    rating_sq = rating_sq.subquery()
    latest_rating = {
        r.lid: float(r.avg_rating)
        for r in db.query(rating_sq.c.lid, rating_sq.c.avg_rating).filter(rating_sq.c.rn == 1).all()
    }

    leaderboard = [
        LeaderboardLocation(
            location_id=row.location_id,
            location_name=row.location_name,
            profile_views=row.profile_views,
            search_impressions=row.search_impressions,
            reviews_count=row.reviews_count,
            avg_rating=latest_rating.get(row.location_id)
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

    # 7. Organization-wide reputation aggregates (sentiment / SLA / themes),
    #    so the "All Locations" view has the same reputation snapshot the
    #    single-location view already shows.
    rep_base = db.query(LocationDailyInsight).filter(
        LocationDailyInsight.organization_id == current_user.organization_id,
        LocationDailyInsight.date >= start_date,
        LocationDailyInsight.date <= end_date,
    )
    if allowed_ids is not None:
        rep_base = rep_base.filter(LocationDailyInsight.location_id.in_(allowed_ids))

    # Weight each day's avg_sentiment_score by that day's review volume so the
    # org-wide score is the true mean over reviews, not a mean of daily means.
    sentiment_score_weighted = func.sum(
        LocationDailyInsight.avg_sentiment_score * LocationDailyInsight.reviews_received
    )
    sentiment_score_weight = func.sum(
        case((LocationDailyInsight.avg_sentiment_score.isnot(None), LocationDailyInsight.reviews_received), else_=0)
    )
    sentiment_agg = rep_base.with_entities(
        func.coalesce(func.sum(LocationDailyInsight.positive_review_count), 0).label("pos"),
        func.coalesce(func.sum(LocationDailyInsight.neutral_review_count), 0).label("neu"),
        func.coalesce(func.sum(LocationDailyInsight.negative_review_count), 0).label("neg"),
        sentiment_score_weighted.label("score_sum"),
        sentiment_score_weight.label("score_wt"),
    ).one()
    pos_c, neu_c, neg_c = sentiment_agg.pos, sentiment_agg.neu, sentiment_agg.neg
    total_rev = pos_c + neu_c + neg_c
    avg_sent_score = (
        float(sentiment_agg.score_sum) / float(sentiment_agg.score_wt)
        if sentiment_agg.score_wt else None
    )
    if total_rev > 0:
        sentiment = SentimentBreakdown(
            positive=pos_c, neutral=neu_c, negative=neg_c,
            positive_percentage=pos_c / total_rev * 100.0,
            neutral_percentage=neu_c / total_rev * 100.0,
            negative_percentage=neg_c / total_rev * 100.0,
            avg_sentiment_score=avg_sent_score,
        )
    else:
        sentiment = SentimentBreakdown(
            positive=0, neutral=0, negative=0,
            positive_percentage=0.0, neutral_percentage=0.0, negative_percentage=0.0,
            avg_sentiment_score=avg_sent_score,
        )

    # SLA: response rate and reply time weighted by replies (not a flat mean of
    # per-day rates), aggregated across every accessible location. Computed as a
    # single SQL aggregate rather than summing per-day rows in Python — for a
    # large org over a long range that row set is locations × days (tens of
    # thousands of rows). FLOOR(reviews * rate / 100) reproduces the previous
    # per-day int() truncation exactly so the numbers are unchanged.
    _replies_expr = func.floor(
        LocationDailyInsight.reviews_received * LocationDailyInsight.response_rate / 100.0
    )
    _time_ok = and_(
        LocationDailyInsight.avg_response_time_hours.isnot(None),
        _replies_expr > 0,
    )
    sla_agg = rep_base.with_entities(
        func.coalesce(func.sum(LocationDailyInsight.reviews_received), 0).label("total_reviews"),
        func.coalesce(func.sum(_replies_expr), 0).label("total_replied"),
        func.coalesce(
            func.sum(case((_time_ok, LocationDailyInsight.avg_response_time_hours * _replies_expr), else_=0.0)),
            0.0,
        ).label("time_sum"),
        func.coalesce(func.sum(case((_time_ok, _replies_expr), else_=0)), 0).label("time_weight"),
    ).one()
    total_reviews = int(sla_agg.total_reviews or 0)
    total_replied = int(sla_agg.total_replied or 0)
    sla_resp_rate = (total_replied / total_reviews * 100.0) if total_reviews > 0 else 0.0
    sla = SLAMetricsSummary(
        total_reviews=total_reviews,
        replied_reviews=total_replied,
        response_rate=sla_resp_rate,
        avg_response_time_hours=(float(sla_agg.time_sum) / float(sla_agg.time_weight)) if sla_agg.time_weight else None,
    )

    # Top recurring issue categories across all accessible locations.
    issues_q = db.query(
        Review.issue_category.label("category"),
        func.count().label("count"),
    ).join(Location, Location.id == Review.location_id).filter(
        Location.organization_id == current_user.organization_id,
        Review.issue_category.isnot(None),
        Review.is_deleted == False,  # noqa: E712
        # Sargable range (no func.date wrapper) so the review_created_at index is usable.
        Review.review_created_at >= start_date,
        Review.review_created_at < end_date + datetime.timedelta(days=1),
    )
    if allowed_ids is not None:
        issues_q = issues_q.filter(Review.location_id.in_(allowed_ids))
    issues_res = issues_q.group_by(Review.issue_category).order_by(func.count().desc()).limit(10).all()
    top_issues = [IssueCategorySummary(category=row.category, count=row.count) for row in issues_res]

    # Auto-trigger synchronization if stale (cached-first logic). These are the
    # daily-metrics surfaces, so only refresh daily insights here; keyword data
    # is refreshed from the Search Intelligence page or the nightly beat.
    try:
        check_and_trigger_stale_insights_sync(current_user.organization_id, db, scope="daily")
    except Exception as e:
        # Prevent sync errors from blocking data display
        logger.error(f"Failed to check/trigger insights sync on overview load: {str(e)}")

    response_data = InsightsOverviewResponse(
        kpis=kpis,
        trends=trends,
        leaderboard=leaderboard,
        attention_locations_count=attention_count,
        sentiment=sentiment,
        sla=sla,
        top_issue_categories=top_issues,
        platform_device=platform_device,
        reputation=reputation
    )

    # Only cache when we actually have synced data for this range. The insights
    # sync is triggered asynchronously above, so the first request for a range
    # can legitimately return empty; caching that empty result for 6h would pin
    # the range to "no data" even after the sync populates it (this is why a
    # freshly-loaded default range could stay empty while other ranges worked).
    if redis_client and trends:
        try:
            redis_client.setex(
                cache_key,
                21600, # 6 hours
                json.dumps(jsonable_encoder(response_data))
            )
        except Exception as e:
            logger.error(f"Redis cache write failed: {e}")

    return response_data


@router.get("/summary", response_model=InsightsSummaryResponse)
def get_insights_summary(
    location_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """Lightweight reputation snapshot for the dashboard and reviews KPI cards.

    Returns the simple-mean average rating, total reviews, review velocity
    (reviews/day with vs-prior delta) and response rate (%) over the last 30
    days. Org-wide by default; pass `location_id` to scope to one location.
    Intentionally cheap — no trends, leaderboard, or sync triggering.
    """
    allowed_ids = deps.get_user_location_ids(current_user, db)
    if allowed_ids is not None and not allowed_ids:
        return InsightsSummaryResponse()

    # Resolve the scope: a single location (access-checked) or all accessible ones.
    if location_id is not None:
        if allowed_ids is not None and location_id not in allowed_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to location.")
        scope = location_id
        scope_key = f"loc:{location_id}"
    else:
        scope = allowed_ids
        scope_key = "all" if allowed_ids is None else "ids:" + ",".join(map(str, sorted(allowed_ids)))

    # This endpoint runs 6 small queries and is hit on every dashboard + reviews
    # load, so cache it briefly (short TTL — the underlying data only moves when a
    # sync runs). Keyed by org + the exact access scope to avoid cross-user bleed.
    cache_key = f"insights:summary:v1:{current_user.organization_id}:{scope_key}"
    redis_client = None
    try:
        redis_client = get_redis()
        cached = redis_client.get(cache_key)
        if cached:
            return InsightsSummaryResponse(**json.loads(cached))
    except Exception as e:
        logger.error(f"Redis cache lookup failed for insights summary: {e}")

    end_date = datetime.date.today() - datetime.timedelta(days=1)
    start_date = end_date - datetime.timedelta(days=29)
    prior_end_date = start_date - datetime.timedelta(days=1)
    prior_start_date = prior_end_date - datetime.timedelta(days=29)

    avg_rating, rated_count = _avg_rating_simple(db, current_user.organization_id, scope)
    velocity = _review_velocity_delta(
        db, current_user.organization_id, scope,
        start_date, end_date, prior_start_date, prior_end_date,
    )
    response_rate = _response_rate_all_time(db, current_user.organization_id, scope)

    total_reviews_q = db.query(func.coalesce(func.sum(LocationDailyInsight.reviews_received), 0)).filter(
        LocationDailyInsight.organization_id == current_user.organization_id,
        LocationDailyInsight.date >= start_date,
        LocationDailyInsight.date <= end_date,
    )
    if isinstance(scope, int):
        total_reviews_q = total_reviews_q.filter(LocationDailyInsight.location_id == scope)
    elif scope is not None:
        total_reviews_q = total_reviews_q.filter(LocationDailyInsight.location_id.in_(scope))
    total_reviews = total_reviews_q.scalar() or 0

    # All-time review count from each location's standing total_reviews (GBP figure).
    all_time_q = db.query(func.coalesce(func.sum(Location.total_reviews), 0)).filter(
        Location.organization_id == current_user.organization_id,
    )
    if isinstance(scope, int):
        all_time_q = all_time_q.filter(Location.id == scope)
    elif scope is not None:
        all_time_q = all_time_q.filter(Location.id.in_(scope))
    total_reviews_all_time = all_time_q.scalar() or 0

    result = InsightsSummaryResponse(
        avg_rating=avg_rating,
        rated_location_count=rated_count,
        total_reviews=total_reviews,
        total_reviews_all_time=total_reviews_all_time,
        review_velocity_per_day=velocity,
        response_rate=response_rate,
    )

    # Cache only when there's some data — never pin an empty snapshot for a
    # freshly-onboarded org whose first sync hasn't landed yet.
    if redis_client and (rated_count > 0 or total_reviews_all_time > 0 or total_reviews > 0):
        try:
            redis_client.setex(cache_key, 600, json.dumps(jsonable_encoder(result)))  # 10 min
        except Exception as e:
            logger.error(f"Redis cache write failed for insights summary: {e}")

    return result


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

    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be on or before end_date."
        )
    if (end_date - start_date).days > 366:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Date range must not exceed 366 days."
        )

    duration = (end_date - start_date).days + 1
    prior_end_date = start_date - datetime.timedelta(days=1)
    prior_start_date = prior_end_date - datetime.timedelta(days=duration - 1)

    # Cache Check
    cache_key = f"insights:location:v4:{current_user.organization_id}:{id}:{start_date.isoformat()}:{end_date.isoformat()}"
    
    redis_client = None
    try:
        redis_client = get_redis()
        cached_data = redis_client.get(cache_key)
        if cached_data:
            logger.info(f"Serving cached location insights for location {id} in org {current_user.organization_id}")
            return LocationInsightsResponse(**json.loads(cached_data))
    except Exception as e:
        logger.error(f"Redis cache lookup failed for location insights: {e}")

    # 1. KPI delta comparisons
    kpi_query = text("""
        SELECT 
            COALESCE(SUM(profile_views), 0) AS profile_views,
            COALESCE(SUM(search_impressions), 0) AS search_impressions,
            COALESCE(SUM(maps_views), 0) AS maps_views,
            COALESCE(SUM(phone_calls), 0) AS phone_calls,
            COALESCE(SUM(website_clicks), 0) AS website_clicks,
            COALESCE(SUM(direction_requests), 0) AS direction_requests,
            COALESCE(SUM(desktop_search_impressions), 0) AS desktop_search,
            COALESCE(SUM(mobile_search_impressions), 0) AS mobile_search,
            COALESCE(SUM(desktop_maps_impressions), 0) AS desktop_maps,
            COALESCE(SUM(mobile_maps_impressions), 0) AS mobile_maps
        FROM location_daily_insights
        WHERE location_id = :location_id
          AND date BETWEEN :start AND :end
    """)

    curr_res = db.execute(kpi_query, {"location_id": id, "start": start_date, "end": end_date}).fetchone()
    prior_res = db.execute(kpi_query, {"location_id": id, "start": prior_start_date, "end": prior_end_date}).fetchone()

    _loc_avg_rating, _loc_rated_count = _avg_rating_simple(db, current_user.organization_id, id)
    reputation = ReputationVelocity(
        avg_rating=_loc_avg_rating,
        rated_location_count=_loc_rated_count,
        review_velocity_per_day=_review_velocity_delta(
            db, current_user.organization_id, id,
            start_date, end_date, prior_start_date, prior_end_date,
        ),
    )

    platform_device = PlatformDeviceBreakdown(
        desktop_search=curr_res.desktop_search,
        mobile_search=curr_res.mobile_search,
        desktop_maps=curr_res.desktop_maps,
        mobile_maps=curr_res.mobile_maps,
    )

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
            avg_rating=item.avg_rating,
            click_through_rate=item.click_through_rate,
            call_conversion_rate=item.call_conversion_rate,
            direction_conversion_rate=item.direction_conversion_rate,
            avg_sentiment_score=item.avg_sentiment_score,
        )
        for item in insights
    ]

    # 3. Sentiment breakdown (aggregate counts via SQL). The sentiment score is
    #    weighted by each day's review volume (true mean over reviews).
    sentiment_agg = db.query(
        func.coalesce(func.sum(LocationDailyInsight.positive_review_count), 0).label("pos_count"),
        func.coalesce(func.sum(LocationDailyInsight.neutral_review_count), 0).label("neu_count"),
        func.coalesce(func.sum(LocationDailyInsight.negative_review_count), 0).label("neg_count"),
        func.sum(LocationDailyInsight.avg_sentiment_score * LocationDailyInsight.reviews_received).label("score_sum"),
        func.sum(case((LocationDailyInsight.avg_sentiment_score.isnot(None), LocationDailyInsight.reviews_received), else_=0)).label("score_wt"),
    ).filter(
        LocationDailyInsight.location_id == id,
        LocationDailyInsight.date >= start_date,
        LocationDailyInsight.date <= end_date,
    ).one()
    pos_count = sentiment_agg.pos_count
    neu_count = sentiment_agg.neu_count
    neg_count = sentiment_agg.neg_count
    total_rev = pos_count + neu_count + neg_count
    avg_sent_score = (
        float(sentiment_agg.score_sum) / float(sentiment_agg.score_wt)
        if sentiment_agg.score_wt else None
    )

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
        negative_percentage=neg_pct,
        avg_sentiment_score=avg_sent_score
    )

    # 4. SLA Summary details (aggregate counts via SQL)
    sla_agg = db.query(
        func.coalesce(func.sum(LocationDailyInsight.reviews_received), 0).label("reviews_count"),
    ).filter(
        LocationDailyInsight.location_id == id,
        LocationDailyInsight.date >= start_date,
        LocationDailyInsight.date <= end_date,
    ).one()
    reviews_count = sla_agg.reviews_count
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
    # Sargable range (no DATE() wrapper) so the review_created_at index is usable.
    issue_query = text("""
        SELECT issue_category, COUNT(*) AS count
        FROM reviews
        WHERE location_id = :location_id
          AND issue_category IS NOT NULL
          AND is_deleted = FALSE
          AND review_created_at >= :start
          AND review_created_at < :end_excl
        GROUP BY issue_category
        ORDER BY count DESC
        LIMIT 10
    """)
    issues_res = db.execute(
        issue_query,
        {"location_id": id, "start": start_date, "end_excl": end_date + datetime.timedelta(days=1)},
    ).fetchall()
    
    top_issues = [
        IssueCategorySummary(category=row.issue_category, count=row.count)
        for row in issues_res
    ]

    # Auto-trigger synchronization if stale (cached-first logic). These are the
    # daily-metrics surfaces, so only refresh daily insights here; keyword data
    # is refreshed from the Search Intelligence page or the nightly beat.
    try:
        check_and_trigger_stale_insights_sync(current_user.organization_id, db, scope="daily")
    except Exception as e:
        # Prevent sync errors from blocking data display
        logger.error(f"Failed to check/trigger insights sync on location load: {str(e)}")

    response_data = LocationInsightsResponse(
        location_id=location.id,
        location_name=location.location_name,
        attention_needed=location.attention_needed,
        attention_reason=location.attention_reason,
        last_insights_sync_at=location.last_insights_sync_at,
        kpis=kpis,
        trends=trends,
        sentiment=sentiment,
        sla=sla,
        top_issue_categories=top_issues,
        platform_device=platform_device,
        reputation=reputation
    )

    # Don't cache an empty (not-yet-synced) range for 6h — see overview endpoint.
    if redis_client and trends:
        try:
            redis_client.setex(
                cache_key,
                21600, # 6 hours
                json.dumps(jsonable_encoder(response_data))
            )
        except Exception as e:
            logger.error(f"Redis cache write failed: {e}")

    return response_data


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


def check_and_trigger_stale_insights_sync(organization_id: int, db: Session, force: bool = False, scope: str = "all") -> dict:
    """
    Evaluate organization-level insights freshness and trigger background sync if stale or forced.
    Returns a dict with 'triggered' bool and 'reason' string.

    `scope` ("daily" | "keywords" | "all") limits which data is synced so the
    Performance Insights and Search Intelligence pages refresh independently.
    """
    if scope not in ("daily", "keywords", "all"):
        scope = "all"
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
            args=[organization_id, start_date.isoformat(), yesterday.isoformat(), run_type, force, scope]
        )
        return {"triggered": True, "reason": run_type}

    return {"triggered": False, "reason": "sync_already_in_progress" if (state and state.insights_sync_in_progress) else "data_is_fresh"}


@router.post("/locations/{location_id}/sync", response_model=InsightsSyncPostResponse)
def trigger_insights_sync(
    location_id: int = Depends(deps.require_location_access),
    start_date: Optional[datetime.date] = Query(None),
    end_date: Optional[datetime.date] = Query(None),
    scope: str = Query("all", regex="^(daily|keywords|all)$"),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Manually trigger performance and reputation insights synchronization for a location (now invokes organization-wide sync).
    """
    # Location scope is enforced by the require_location_access dependency.
    result = check_and_trigger_stale_insights_sync(current_user.organization_id, db, force=True, scope=scope)
    return InsightsSyncPostResponse(
        task_id="org-orchestrated",
        status="Queued" if result["triggered"] else "AlreadyRunning"
    )


@router.post("/sync-all", response_model=InsightsSyncPostResponse)
def trigger_global_insights_sync(
    force: bool = Query(True),
    scope: str = Query("all", regex="^(daily|keywords|all)$"),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Manually trigger performance and reputation insights synchronization for ALL locations of the organization.
    """
    # An org-wide sync touches every location; only users with org-wide access may
    # trigger it. Location-restricted roles (Regional/Store Manager, restricted Viewer)
    # get a non-None allow-list and are forbidden.
    if deps.get_user_location_ids(current_user, db) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to sync all organization locations.",
        )
    result = check_and_trigger_stale_insights_sync(current_user.organization_id, db, force=force, scope=scope)
    return InsightsSyncPostResponse(
        task_id="org-orchestrated",
        status="Queued" if result["triggered"] else "AlreadyRunning"
    )

@router.get("/keywords/summary", response_model=KeywordSummaryResponse)
def get_search_keywords_summary(
    location_id: Optional[int] = Query(None),
    start_period: Optional[datetime.date] = Query(None),
    end_period: Optional[datetime.date] = Query(None),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """KPIs, monthly branded/non-branded trend, and per-location comparison.

    `start_period`/`end_period` are month dates; the prior window of equal month
    length immediately before `start_period` is used for MoM growth.
    """
    allowed_ids = deps.get_user_location_ids(current_user, db)
    empty = KeywordSummaryResponse(
        kpis=KeywordKpis(
            total_impressions=0, total_impressions_prior=0, impressions_mom=None,
            keywords_tracked=0, branded_impressions=0, branded_pct=0.0,
            non_branded_impressions=0, non_branded_pct=0.0,
        ),
        trends=[], location_comparison=[],
    )
    if allowed_ids is not None and not allowed_ids:
        return empty

    # Default to the last 3 complete months ending last month.
    if not end_period:
        end_period = _add_months(_month_floor(datetime.date.today()), -1)
    else:
        end_period = _month_floor(end_period)
    if not start_period:
        start_period = _add_months(end_period, -2)
    else:
        start_period = _month_floor(start_period)
    if start_period > end_period:
        raise HTTPException(status_code=422, detail="start_period must be <= end_period")

    n_months = (end_period.year - start_period.year) * 12 + (end_period.month - start_period.month) + 1
    prior_end = _add_months(start_period, -1)
    prior_start = _add_months(start_period, -n_months)

    brand_terms_lower = _brand_terms_lower(db, current_user.organization_id)
    branded_case = func.sum(
        case((_branded_condition(brand_terms_lower), KeywordMonthlyMetric.impressions), else_=0)
    )

    def _scoped(q):
        q = q.join(Location, Location.id == KeywordMonthlyMetric.location_id).filter(
            Location.organization_id == current_user.organization_id
        )
        if allowed_ids is not None:
            q = q.filter(KeywordMonthlyMetric.location_id.in_(allowed_ids))
        if location_id is not None:
            if allowed_ids is not None and location_id not in allowed_ids:
                raise HTTPException(status_code=403, detail="Access denied to location.")
            q = q.filter(KeywordMonthlyMetric.location_id == location_id)
        return q

    def _window(q, start, end):
        return q.filter(
            KeywordMonthlyMetric.period_start >= start,
            KeywordMonthlyMetric.period_start <= end,
        )

    # KPI aggregates for current window
    cur = _window(_scoped(db.query(
        func.coalesce(func.sum(KeywordMonthlyMetric.impressions), 0),
        branded_case,
        func.count(func.distinct(KeywordMonthlyMetric.keyword)),
    )), start_period, end_period).one()
    total_impressions = int(cur[0] or 0)
    branded_impressions = int(cur[1] or 0)
    keywords_tracked = int(cur[2] or 0)
    non_branded_impressions = max(total_impressions - branded_impressions, 0)

    prior_total = int(_window(_scoped(db.query(
        func.coalesce(func.sum(KeywordMonthlyMetric.impressions), 0)
    )), prior_start, prior_end).scalar() or 0)

    kpis = KeywordKpis(
        total_impressions=total_impressions,
        total_impressions_prior=prior_total,
        impressions_mom=calculate_delta(total_impressions, prior_total),
        keywords_tracked=keywords_tracked,
        branded_impressions=branded_impressions,
        branded_pct=round(branded_impressions / total_impressions * 100, 1) if total_impressions else 0.0,
        non_branded_impressions=non_branded_impressions,
        non_branded_pct=round(non_branded_impressions / total_impressions * 100, 1) if total_impressions else 0.0,
    )

    # Monthly trend (branded vs non-branded)
    trend_rows = _window(_scoped(db.query(
        KeywordMonthlyMetric.period_start.label("month"),
        func.coalesce(func.sum(KeywordMonthlyMetric.impressions), 0).label("total"),
        branded_case.label("branded"),
    )), start_period, end_period).group_by(KeywordMonthlyMetric.period_start).all()
    by_month = {r.month: (int(r.total or 0), int(r.branded or 0)) for r in trend_rows}

    # Gap-fill: emit every month in the selected window, zero where no data, so
    # the chart axis matches the chosen range instead of collapsing to months
    # that happen to have data.
    trends = []
    m = start_period
    while m <= end_period:
        total, branded = by_month.get(m, (0, 0))
        trends.append(KeywordTrendPoint(month=m, branded=branded, non_branded=max(total - branded, 0), total=total))
        m = _add_months(m, 1)

    # Per-location comparison (only meaningful when not filtered to one location)
    location_comparison = []
    if location_id is None:
        cur_by_loc = dict(_window(_scoped(db.query(
            KeywordMonthlyMetric.location_id,
            func.coalesce(func.sum(KeywordMonthlyMetric.impressions), 0),
        )), start_period, end_period).group_by(KeywordMonthlyMetric.location_id).all())
        prior_by_loc = dict(_window(_scoped(db.query(
            KeywordMonthlyMetric.location_id,
            func.coalesce(func.sum(KeywordMonthlyMetric.impressions), 0),
        )), prior_start, prior_end).group_by(KeywordMonthlyMetric.location_id).all())
        names = dict(db.query(Location.id, Location.location_name).filter(Location.id.in_(list(cur_by_loc.keys()) or [-1])).all())
        for loc_id, impr in sorted(cur_by_loc.items(), key=lambda kv: kv[1], reverse=True):
            location_comparison.append(KeywordLocationComparison(
                location_id=loc_id,
                location_name=names.get(loc_id, f"Location {loc_id}"),
                impressions=int(impr or 0),
                mom_growth=calculate_delta(int(impr or 0), int(prior_by_loc.get(loc_id, 0) or 0)),
            ))

    return KeywordSummaryResponse(kpis=kpis, trends=trends, location_comparison=location_comparison)


@router.get("/keywords", response_model=KeywordMetricsResponse)
def get_search_keywords(
    location_id: Optional[int] = Query(None),
    start_period: Optional[datetime.date] = Query(None),
    end_period: Optional[datetime.date] = Query(None),
    period_start: Optional[datetime.date] = Query(None),  # legacy single-month alias
    search: Optional[str] = Query(None),
    is_brand: Optional[bool] = Query(None),
    sort_by: str = Query("impressions", regex="^(impressions|keyword)$"),
    sort_desc: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """Top keywords aggregated across a month window (impressions summed per
    keyword). `start_period`/`end_period` are month dates; `period_start` is a
    legacy single-month alias."""
    allowed_ids = deps.get_user_location_ids(current_user, db)
    if allowed_ids is not None and not allowed_ids:
        return KeywordMetricsResponse(items=[], total=0, page=page, page_size=page_size)

    # Resolve the month window.
    if period_start and not start_period and not end_period:
        start_period = end_period = period_start
    if not end_period:
        end_period = _add_months(_month_floor(datetime.date.today()), -1)
    else:
        end_period = _month_floor(end_period)
    if not start_period:
        start_period = end_period
    else:
        start_period = _month_floor(start_period)
    if start_period > end_period:
        start_period, end_period = end_period, start_period

    impr_sum = func.coalesce(func.sum(KeywordMonthlyMetric.impressions), 0).label("impressions")
    query = db.query(
        KeywordMonthlyMetric.keyword.label("keyword"),
        impr_sum,
    ).join(
        Location, Location.id == KeywordMonthlyMetric.location_id
    ).filter(
        Location.organization_id == current_user.organization_id,
        KeywordMonthlyMetric.period_start >= start_period,
        KeywordMonthlyMetric.period_start <= end_period,
    )

    if allowed_ids is not None:
        query = query.filter(KeywordMonthlyMetric.location_id.in_(allowed_ids))

    if location_id is not None:
        if allowed_ids is not None and location_id not in allowed_ids:
            raise HTTPException(status_code=403, detail="Access denied to location.")
        query = query.filter(KeywordMonthlyMetric.location_id == location_id)

    if search:
        query = query.filter(KeywordMonthlyMetric.keyword.ilike(f"%{search}%"))

    brand_terms_lower = _brand_terms_lower(db, current_user.organization_id)
    if is_brand is not None:
        query = query.filter(_branded_filter(brand_terms_lower, is_brand))

    query = query.group_by(KeywordMonthlyMetric.keyword)

    # Count distinct keywords (group count) for pagination.
    total = query.order_by(None).count()

    if sort_by == "keyword":
        order = KeywordMonthlyMetric.keyword
    else:
        order = func.sum(KeywordMonthlyMetric.impressions)
    order = order.desc() if sort_desc else order.asc()
    query = query.order_by(order)

    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    # Per-keyword MoM: sum impressions for the same keywords over the prior
    # window of equal month length immediately before start_period. Only the
    # current page's keywords are looked up, so this stays a single bounded query.
    page_keywords = [r.keyword for r in rows]
    prior_by_keyword: dict = {}
    if page_keywords:
        n_months = (end_period.year - start_period.year) * 12 + (end_period.month - start_period.month) + 1
        prior_end = _add_months(start_period, -1)
        prior_start = _add_months(start_period, -n_months)
        prior_q = db.query(
            KeywordMonthlyMetric.keyword.label("keyword"),
            func.coalesce(func.sum(KeywordMonthlyMetric.impressions), 0).label("impressions"),
        ).join(
            Location, Location.id == KeywordMonthlyMetric.location_id
        ).filter(
            Location.organization_id == current_user.organization_id,
            KeywordMonthlyMetric.period_start >= prior_start,
            KeywordMonthlyMetric.period_start <= prior_end,
            KeywordMonthlyMetric.keyword.in_(page_keywords),
        )
        if allowed_ids is not None:
            prior_q = prior_q.filter(KeywordMonthlyMetric.location_id.in_(allowed_ids))
        if location_id is not None:
            prior_q = prior_q.filter(KeywordMonthlyMetric.location_id == location_id)
        prior_by_keyword = {
            r.keyword: int(r.impressions or 0)
            for r in prior_q.group_by(KeywordMonthlyMetric.keyword).all()
        }

    result_items = [
        SearchKeywordMetric(
            keyword=r.keyword,
            impressions=int(r.impressions or 0),
            impressions_prior=prior_by_keyword.get(r.keyword, 0),
            mom_growth=calculate_delta(int(r.impressions or 0), prior_by_keyword.get(r.keyword, 0)),
            is_brand_term=_is_branded(r.keyword, brand_terms_lower)
        )
        for r in rows
    ]

    return KeywordMetricsResponse(
        items=result_items,
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/keywords/export")
def export_search_keywords(
    location_id: Optional[int] = Query(None),
    start_period: Optional[datetime.date] = Query(None),
    end_period: Optional[datetime.date] = Query(None),
    period_start: Optional[datetime.date] = Query(None),  # legacy single-month alias
    search: Optional[str] = Query(None),
    is_brand: Optional[bool] = Query(None),
    sort_by: str = Query("impressions"),
    sort_desc: bool = Query(True),
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Export search keywords (per-month rows) to CSV.
    """
    allowed_ids = deps.get_user_location_ids(current_user, db)
    if allowed_ids is not None and not allowed_ids:
        # No accessible locations -> empty export rather than leaking other orgs.
        return StreamingResponse(iter(["Keyword,Impressions,Period Start,Is Brand Term\n"]),
                                 media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=search_keywords.csv"})

    if period_start and not start_period and not end_period:
        start_period = end_period = period_start
    if not end_period:
        end_period = _add_months(_month_floor(datetime.date.today()), -1)
    else:
        end_period = _month_floor(end_period)
    if not start_period:
        start_period = end_period
    else:
        start_period = _month_floor(start_period)
    if start_period > end_period:
        start_period, end_period = end_period, start_period

    query = db.query(KeywordMonthlyMetric).join(
        Location, Location.id == KeywordMonthlyMetric.location_id
    ).filter(
        Location.organization_id == current_user.organization_id,
        KeywordMonthlyMetric.period_start >= start_period,
        KeywordMonthlyMetric.period_start <= end_period,
    )

    if allowed_ids is not None:
        query = query.filter(KeywordMonthlyMetric.location_id.in_(allowed_ids))

    if location_id is not None:
        if allowed_ids is not None and location_id not in allowed_ids:
            raise HTTPException(status_code=403, detail="Access denied to location.")
        query = query.filter(KeywordMonthlyMetric.location_id == location_id)

    if search:
        query = query.filter(KeywordMonthlyMetric.keyword.ilike(f"%{search}%"))

    brand_terms_lower = _brand_terms_lower(db, current_user.organization_id)

    if is_brand is not None:
        query = query.filter(_branded_filter(brand_terms_lower, is_brand))

    if sort_by not in KEYWORD_SORT_COLUMNS:
        sort_by = "impressions"
    sort_col = getattr(KeywordMonthlyMetric, sort_by)
    if sort_desc:
        sort_col = sort_col.desc()
    query = query.order_by(sort_col)

    # Cap export size and stream row-by-row so a large org can't OOM the worker.
    MAX_EXPORT_ROWS = 50000

    def _row_iter():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Keyword", "Impressions", "Period Start", "Is Brand Term"])
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)
        for item in query.yield_per(1000).limit(MAX_EXPORT_ROWS):
            writer.writerow([
                _csv_safe(item.keyword),
                item.impressions,
                item.period_start.isoformat() if item.period_start else "",
                _is_branded(item.keyword, brand_terms_lower),
            ])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    return StreamingResponse(
        _row_iter(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=search_keywords.csv"}
    )

@router.get("/brand-terms", response_model=List[BrandTermResponse])
def list_brand_terms(
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    List brand terms for the organization.
    """
    terms = db.query(OrganizationBrandTerm).filter(
        OrganizationBrandTerm.organization_id == current_user.organization_id
    ).order_by(OrganizationBrandTerm.created_at.asc()).all()
    return terms

@router.post("/brand-terms", response_model=BrandTermResponse)
def create_brand_term(
    term_in: BrandTermCreate,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Add a new brand term for the organization.
    """
    term_val = term_in.term.strip()
    if not term_val:
        raise HTTPException(status_code=400, detail="Brand term cannot be empty")
        
    existing = db.query(OrganizationBrandTerm).filter(
        OrganizationBrandTerm.organization_id == current_user.organization_id,
        func.lower(OrganizationBrandTerm.term) == term_val.lower()
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Brand term already exists")
        
    term = OrganizationBrandTerm(
        organization_id=current_user.organization_id,
        term=term_val
    )
    db.add(term)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent insert of the same term hit the unique index.
        db.rollback()
        raise HTTPException(status_code=400, detail="Brand term already exists")
    db.refresh(term)
    return term

@router.delete("/brand-terms/{id}")
def delete_brand_term(
    id: int,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    """
    Delete a brand term.
    """
    term = db.query(OrganizationBrandTerm).filter(
        OrganizationBrandTerm.id == id,
        OrganizationBrandTerm.organization_id == current_user.organization_id
    ).first()
    
    if not term:
        raise HTTPException(status_code=404, detail="Brand term not found")
        
    db.delete(term)
    db.commit()
    return {"status": "success"}
