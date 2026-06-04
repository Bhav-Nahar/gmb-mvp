import datetime
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func, text
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
                    SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) AS positive_review_count,
                    SUM(CASE WHEN sentiment = 'neutral' THEN 1 ELSE 0 END) AS neutral_review_count,
                    SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) AS negative_review_count,
                    CAST(SUM(CASE WHEN is_replied = 1 THEN 1 ELSE 0 END) AS float) / NULLIF(COUNT(*), 0) * 100 AS response_rate,
                    AVG((julianday(reply_created_at) - julianday(review_created_at)) * 24) AS avg_response_time_hours,
                    AVG(CASE 
                        WHEN sentiment = 'positive' THEN 1.0 
                        WHEN sentiment = 'neutral' THEN 0.0 
                        WHEN sentiment = 'negative' THEN -1.0 
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
                    COUNT(*) FILTER (WHERE sentiment = 'positive') AS positive_review_count,
                    COUNT(*) FILTER (WHERE sentiment = 'neutral') AS neutral_review_count,
                    COUNT(*) FILTER (WHERE sentiment = 'negative') AS negative_review_count,
                    CAST(COUNT(*) FILTER (WHERE is_replied = TRUE) AS float) / NULLIF(COUNT(*), 0) * 100 AS response_rate,
                    AVG(EXTRACT(EPOCH FROM (reply_created_at - review_created_at)) / 3600) FILTER (
                        WHERE is_replied = TRUE AND reply_created_at IS NOT NULL
                    ) AS avg_response_time_hours,
                    AVG(CASE 
                        WHEN sentiment = 'positive' THEN 1.0 
                        WHEN sentiment = 'neutral' THEN 0.0 
                        WHEN sentiment = 'negative' THEN -1.0 
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
        """
        locations = db.query(Location).filter(Location.organization_id == organization_id).all()
        today = datetime.date.today()
        
        for loc in locations:
            reasons = []
            
            # Retrieve metrics for the last 30 days
            last_30_start = today - datetime.timedelta(days=AttentionThresholds.EVALUATION_WINDOW_DAYS)
            curr_insights = db.query(LocationDailyInsight).filter(
                LocationDailyInsight.location_id == loc.id,
                LocationDailyInsight.date >= last_30_start
            ).all()

            # Retrieve metrics for the prior 30 days (MoM comparison window)
            prior_30_start = last_30_start - datetime.timedelta(days=AttentionThresholds.EVALUATION_WINDOW_DAYS)
            prior_insights = db.query(LocationDailyInsight).filter(
                LocationDailyInsight.location_id == loc.id,
                LocationDailyInsight.date >= prior_30_start,
                LocationDailyInsight.date < last_30_start
            ).all()

            # Aggregate current window
            total_reviews = sum(i.reviews_received for i in curr_insights)
            total_negative = sum(i.negative_review_count for i in curr_insights)
            replied_reviews = sum(int(i.reviews_received * (i.response_rate / 100.0)) for i in curr_insights)
            
            total_calls = sum(i.phone_calls for i in curr_insights)
            total_clicks = sum(i.website_clicks for i in curr_insights)

            # Aggregate prior window
            prior_calls = sum(i.phone_calls for i in prior_insights)
            prior_clicks = sum(i.website_clicks for i in prior_insights)

            # Check rule 1: Negative Sentiment Spike (> 40% of received reviews)
            if total_reviews > 0 and (total_negative / total_reviews) > AttentionThresholds.NEGATIVE_SENTIMENT_SPIKE_THRESHOLD:
                neg_pct = (total_negative / total_reviews) * 100
                reasons.append(f"Negative sentiment spike: {neg_pct:.1f}% of reviews were negative")

            # Check rule 2: Response rate (< 50% response rate)
            if total_reviews > 0 and (replied_reviews / total_reviews) < (AttentionThresholds.RESPONSE_RATE_THRESHOLD / 100.0):
                resp_pct = (replied_reviews / total_reviews) * 100
                reasons.append(f"Response rate warning: only {resp_pct:.1f}% of reviews replied to (threshold is {AttentionThresholds.RESPONSE_RATE_THRESHOLD}%)")

            # Check rule 3: No reviews received in the last 60 days
            last_60_start = today - datetime.timedelta(days=AttentionThresholds.NO_REVIEWS_DAYS)
            total_reviews_60 = db.query(func.sum(LocationDailyInsight.reviews_received)).filter(
                LocationDailyInsight.location_id == loc.id,
                LocationDailyInsight.date >= last_60_start
            ).scalar() or 0
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
