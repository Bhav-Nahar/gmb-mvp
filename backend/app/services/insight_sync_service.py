import datetime
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func, text, case
from app.models.location import Location
from app.models.review import Review
from app.models.location_daily_insights import LocationDailyInsight
from app.providers.factory import ProviderFactory
from app.providers.base.models import DailyInsightMetric
from app.constants.attention import AttentionThresholds

class InsightSyncService:
    @staticmethod
    async def sync_location_insights(db: Session, location_id: int, start_date: datetime.date, end_date: datetime.date, run_type: str = "Scheduled") -> str:
        """
        Synchronize performance and reputation metrics for a location across a date range.
        Ensures sparse date gaps are resolved, merges reviews aggregates, calculates conversion rates,
        and performs an idempotent bulk UPSERT.
        """
        location = db.query(Location).filter(Location.id == location_id).first()
        if not location:
            raise Exception(f"Location with ID {location_id} not found.")

        organization_id = location.organization_id

        # 1. Resolve Provider and Fetch Performance Insights
        provider_name = "gbp"
        provider = ProviderFactory.get_provider(provider_name, organization_id, db)
        provider_insights = await provider.get_insights(
            location_id=location.google_location_id,
            start_date=start_date,
            end_date=end_date,
            account_id=location.google_account_id
        )
        
        # Build map of date -> performance metrics
        perf_map = {insight.date: insight for insight in provider_insights}

        # 2. Query Review Metrics Aggregations from the local database
        if "sqlite" in db.bind.dialect.name:
            review_agg_query = text("""
                SELECT
                    DATE(review_created_at) AS date,
                    COUNT(*) AS reviews_received,
                    AVG(rating) AS avg_rating,
                    SUM(CASE WHEN LOWER(sentiment) = 'positive' THEN 1 ELSE 0 END) AS positive_review_count,
                    SUM(CASE WHEN LOWER(sentiment) = 'neutral' THEN 1 ELSE 0 END) AS neutral_review_count,
                    SUM(CASE WHEN LOWER(sentiment) IN ('negative', 'angry') THEN 1 ELSE 0 END) AS negative_review_count,
                    CAST(SUM(CASE WHEN is_replied = 1 THEN 1 ELSE 0 END) AS float) / NULLIF(COUNT(*), 0) * 100 AS response_rate,
                    AVG((julianday(reply_created_at) - julianday(review_created_at)) * 24) AS avg_response_time_hours,
                    AVG(CASE
                        WHEN LOWER(sentiment) = 'positive' THEN 1.0
                        WHEN LOWER(sentiment) = 'neutral' THEN 0.0
                        WHEN LOWER(sentiment) IN ('negative', 'angry') THEN -1.0
                        ELSE NULL
                    END) AS avg_sentiment_score
                FROM reviews
                WHERE location_id = :location_id
                  AND DATE(review_created_at) BETWEEN :start_date AND :end_date
                  AND is_deleted = 0
                GROUP BY DATE(review_created_at)
            """)
        else:
            review_agg_query = text("""
                SELECT
                    DATE(review_created_at) AS date,
                    COUNT(*) AS reviews_received,
                    AVG(rating) AS avg_rating,
                    COUNT(*) FILTER (WHERE LOWER(sentiment) = 'positive') AS positive_review_count,
                    COUNT(*) FILTER (WHERE LOWER(sentiment) = 'neutral') AS neutral_review_count,
                    COUNT(*) FILTER (WHERE LOWER(sentiment) IN ('negative', 'angry')) AS negative_review_count,
                    CAST(COUNT(*) FILTER (WHERE is_replied = TRUE) AS float) / NULLIF(COUNT(*), 0) * 100 AS response_rate,
                    AVG(EXTRACT(EPOCH FROM (reply_created_at - review_created_at)) / 3600) FILTER (
                        WHERE is_replied = TRUE AND reply_created_at IS NOT NULL
                    ) AS avg_response_time_hours,
                    AVG(CASE
                        WHEN LOWER(sentiment) = 'positive' THEN 1.0
                        WHEN LOWER(sentiment) = 'neutral' THEN 0.0
                        WHEN LOWER(sentiment) IN ('negative', 'angry') THEN -1.0
                        ELSE NULL
                    END) AS avg_sentiment_score
                FROM reviews
                WHERE location_id = :location_id
                  AND DATE(review_created_at) BETWEEN :start_date AND :end_date
                  AND is_deleted = FALSE
                GROUP BY DATE(review_created_at)
            """)
        
        res = db.execute(review_agg_query, {
            "location_id": location_id, 
            "start_date": start_date, 
            "end_date": end_date
        }).fetchall()
        
        # In SQLite DATE() returns a string date 'YYYY-MM-DD', we need to convert it to datetime.date object.
        review_map = {}
        for row in res:
            row_date = row.date
            if isinstance(row_date, str):
                row_date = datetime.date.fromisoformat(row_date)
            review_map[row_date] = row

        # 3. Generate Complete Date Array to fill gaps
        insert_values = []
        curr_date = start_date
        while curr_date <= end_date:
            perf = perf_map.get(curr_date)
            rev = review_map.get(curr_date)

            if isinstance(perf, DailyInsightMetric):
                search_impressions = perf.search_views
                maps_views = perf.map_views
                desktop_search_impressions = perf.desktop_search_impressions
                mobile_search_impressions = perf.mobile_search_impressions
                desktop_maps_impressions = perf.desktop_maps_impressions
                mobile_maps_impressions = perf.mobile_maps_impressions
                profile_views = search_impressions + maps_views
                phone_calls = perf.phone_calls
                website_clicks = perf.website_clicks
                direction_requests = perf.direction_requests
                searches_direct = perf.search_queries_direct
                searches_indirect = perf.search_queries_indirect
                searches_chain = perf.search_queries_chain
            else:
                profile_views = search_impressions = maps_views = phone_calls = website_clicks = direction_requests = 0
                searches_direct = searches_indirect = searches_chain = 0
                desktop_search_impressions = mobile_search_impressions = 0
                desktop_maps_impressions = mobile_maps_impressions = 0

            # Calculations with safety guards
            click_through_rate = (website_clicks / float(profile_views)) * 100.0 if profile_views > 0 else None
            call_conversion_rate = (phone_calls / float(profile_views)) * 100.0 if profile_views > 0 else None
            direction_conversion_rate = (direction_requests / float(profile_views)) * 100.0 if profile_views > 0 else None

            val = {
                "organization_id": organization_id,
                "location_id": location_id,
                "date": curr_date,
                "provider": provider_name,
                
                # Visibility Metrics
                "profile_views": profile_views,
                "search_impressions": search_impressions,
                "maps_views": maps_views,
                "desktop_search_impressions": desktop_search_impressions,
                "mobile_search_impressions": mobile_search_impressions,
                "desktop_maps_impressions": desktop_maps_impressions,
                "mobile_maps_impressions": mobile_maps_impressions,

                # Engagement Metrics
                "phone_calls": phone_calls,
                "website_clicks": website_clicks,
                "direction_requests": direction_requests,
                
                # Search Intent Metrics
                "searches_direct": searches_direct,
                "searches_indirect": searches_indirect,
                "searches_chain": searches_chain,
                
                # Reviews Metrics
                "reviews_received": rev.reviews_received if rev else 0,
                "avg_rating": float(rev.avg_rating) if rev and rev.avg_rating is not None else None,
                "positive_review_count": rev.positive_review_count if rev else 0,
                "neutral_review_count": rev.neutral_review_count if rev else 0,
                "negative_review_count": rev.negative_review_count if rev else 0,
                "avg_sentiment_score": float(rev.avg_sentiment_score) if rev and rev.avg_sentiment_score is not None else None,
                
                # Response & SLA Metrics
                "response_rate": float(rev.response_rate) if rev and rev.response_rate is not None else 0.0,
                "avg_response_time_hours": float(rev.avg_response_time_hours) if rev and rev.avg_response_time_hours is not None else None,
                
                # Derived Conversion Rate Metrics
                "click_through_rate": click_through_rate,
                "call_conversion_rate": call_conversion_rate,
                "direction_conversion_rate": direction_conversion_rate
            }
            insert_values.append(val)
            curr_date += datetime.timedelta(days=1)

        # 4. Perform idempotent bulk upsert
        if insert_values:
            stmt = insert(LocationDailyInsight).values(insert_values)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_location_daily_provider",
                set_={
                    "profile_views": stmt.excluded.profile_views,
                    "search_impressions": stmt.excluded.search_impressions,
                    "maps_views": stmt.excluded.maps_views,
                    "desktop_search_impressions": stmt.excluded.desktop_search_impressions,
                    "mobile_search_impressions": stmt.excluded.mobile_search_impressions,
                    "desktop_maps_impressions": stmt.excluded.desktop_maps_impressions,
                    "mobile_maps_impressions": stmt.excluded.mobile_maps_impressions,
                    "phone_calls": stmt.excluded.phone_calls,
                    "website_clicks": stmt.excluded.website_clicks,
                    "direction_requests": stmt.excluded.direction_requests,
                    "searches_direct": stmt.excluded.searches_direct,
                    "searches_indirect": stmt.excluded.searches_indirect,
                    "searches_chain": stmt.excluded.searches_chain,
                    "reviews_received": stmt.excluded.reviews_received,
                    "avg_rating": stmt.excluded.avg_rating,
                    "positive_review_count": stmt.excluded.positive_review_count,
                    "neutral_review_count": stmt.excluded.neutral_review_count,
                    "negative_review_count": stmt.excluded.negative_review_count,
                    "avg_sentiment_score": stmt.excluded.avg_sentiment_score,
                    "response_rate": stmt.excluded.response_rate,
                    "avg_response_time_hours": stmt.excluded.avg_response_time_hours,
                    "click_through_rate": stmt.excluded.click_through_rate,
                    "call_conversion_rate": stmt.excluded.call_conversion_rate,
                    "direction_conversion_rate": stmt.excluded.direction_conversion_rate,
                }
            )
            db.execute(stmt)

        # 5. Update last insights sync timestamp
        location.last_insights_sync_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
        return f"Successfully synchronized insights for location {location_id}."

    @staticmethod
    def evaluate_attention_flags(db: Session, organization_id: int) -> None:
        """
        Evaluate and update attention flags for all locations under an organization based on predefined thresholds.
        Uses a single batch aggregation query to eliminate N+1 database operations.
        """
        locations = db.query(Location).filter(Location.organization_id == organization_id).all()
        if not locations:
            return

        today = datetime.date.today()
        
        # Calculate date boundaries
        last_30_start = today - datetime.timedelta(days=AttentionThresholds.EVALUATION_WINDOW_DAYS)
        prior_30_start = last_30_start - datetime.timedelta(days=AttentionThresholds.EVALUATION_WINDOW_DAYS)
        last_60_start = today - datetime.timedelta(days=AttentionThresholds.NO_REVIEWS_DAYS)
        
        min_date = min(prior_30_start, last_60_start)

        # Build cases for current 30 days
        case_last_30_reviews = case((LocationDailyInsight.date >= last_30_start, LocationDailyInsight.reviews_received), else_=0)
        case_last_30_negative = case((LocationDailyInsight.date >= last_30_start, LocationDailyInsight.negative_review_count), else_=0)
        case_last_30_replied = case(
            (LocationDailyInsight.date >= last_30_start, LocationDailyInsight.reviews_received * (LocationDailyInsight.response_rate / 100.0)),
            else_=0.0
        )
        case_last_30_calls = case((LocationDailyInsight.date >= last_30_start, LocationDailyInsight.phone_calls), else_=0)
        case_last_30_clicks = case((LocationDailyInsight.date >= last_30_start, LocationDailyInsight.website_clicks), else_=0)

        # Build cases for prior 30 days (MoM comparison)
        case_prior_30_calls = case(
            ((LocationDailyInsight.date >= prior_30_start) & (LocationDailyInsight.date < last_30_start), LocationDailyInsight.phone_calls),
            else_=0
        )
        case_prior_30_clicks = case(
            ((LocationDailyInsight.date >= prior_30_start) & (LocationDailyInsight.date < last_30_start), LocationDailyInsight.website_clicks),
            else_=0
        )

        # Build cases for last 60 days
        case_60_reviews = case((LocationDailyInsight.date >= last_60_start, LocationDailyInsight.reviews_received), else_=0)

        # Single batch aggregation query returning lightweight rows (no ORM hydration)
        agg_results = (
            db.query(
                LocationDailyInsight.location_id,
                func.coalesce(func.sum(case_last_30_reviews), 0).label("total_reviews"),
                func.coalesce(func.sum(case_last_30_negative), 0).label("total_negative"),
                func.coalesce(func.sum(case_last_30_replied), 0.0).label("replied_reviews"),
                func.coalesce(func.sum(case_last_30_calls), 0).label("total_calls"),
                func.coalesce(func.sum(case_last_30_clicks), 0).label("total_clicks"),
                func.coalesce(func.sum(case_prior_30_calls), 0).label("prior_calls"),
                func.coalesce(func.sum(case_prior_30_clicks), 0).label("prior_clicks"),
                func.coalesce(func.sum(case_60_reviews), 0).label("total_reviews_60")
            )
            .filter(
                LocationDailyInsight.organization_id == organization_id,
                LocationDailyInsight.date >= min_date
            )
            .group_by(LocationDailyInsight.location_id)
            .all()
        )

        # Map results to location_id
        agg_map = {row.location_id: row for row in agg_results}

        for loc in locations:
            reasons = []
            
            # Fetch aggregates from map, or default to zero values if no daily insights exist
            metrics = agg_map.get(loc.id)
            if metrics:
                total_reviews = metrics.total_reviews
                total_negative = metrics.total_negative
                replied_reviews = metrics.replied_reviews
                total_calls = metrics.total_calls
                total_clicks = metrics.total_clicks
                prior_calls = metrics.prior_calls
                prior_clicks = metrics.prior_clicks
                total_reviews_60 = metrics.total_reviews_60
            else:
                total_reviews = 0
                total_negative = 0
                replied_reviews = 0.0
                total_calls = 0
                total_clicks = 0
                prior_calls = 0
                prior_clicks = 0
                total_reviews_60 = 0

            # Check rule 1: Negative Sentiment Spike (> 40% of received reviews)
            if total_reviews > 0 and (total_negative / total_reviews) > AttentionThresholds.NEGATIVE_SENTIMENT_SPIKE_THRESHOLD:
                neg_pct = (total_negative / total_reviews) * 100
                reasons.append(f"Negative sentiment spike: {neg_pct:.1f}% of reviews were negative")

            # Check rule 2: Response rate (< 50% response rate)
            if total_reviews > 0 and (replied_reviews / total_reviews) < (AttentionThresholds.RESPONSE_RATE_THRESHOLD / 100.0):
                resp_pct = (replied_reviews / total_reviews) * 100
                reasons.append(f"Response rate warning: only {resp_pct:.1f}% of reviews replied to (threshold is {AttentionThresholds.RESPONSE_RATE_THRESHOLD}%)")

            # Check rule 3: No reviews received in the last 60 days
            if total_reviews_60 == 0:
                reasons.append(f"No customer reviews received in the last {AttentionThresholds.NO_REVIEWS_DAYS} days")

            # Check rule 4: Call volume drop (> 30% MoM drop)
            if prior_calls > 0:
                call_drop = (prior_calls - total_calls) / prior_calls
                if call_drop > AttentionThresholds.CALL_DROP_PERCENTAGE / 100.0:
                    reasons.append(f"Phone calls volume dropped by {call_drop * 100:.1f}% MoM (prior: {prior_calls}, current: {total_calls})")

            # Check rule 5: Website clicks drop (> 30% MoM drop)
            if prior_clicks > 0:
                click_drop = (prior_clicks - total_clicks) / prior_clicks
                if click_drop > AttentionThresholds.WEBSITE_CLICK_DROP_PERCENTAGE / 100.0:
                    reasons.append(f"Website clicks volume dropped by {click_drop * 100:.1f}% MoM (prior: {prior_clicks}, current: {total_clicks})")

            # Update database status
            if reasons:
                loc.attention_needed = True
                loc.attention_reason = " | ".join(reasons)
            else:
                loc.attention_needed = False
                loc.attention_reason = None
            loc.attention_updated_at = datetime.datetime.now(datetime.timezone.utc)

        db.commit()
