from datetime import date, timedelta
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

class ComparisonAggregationService:
    @staticmethod
    def aggregate_group_insights(db: Session, target_date: date, org_id: Optional[int] = None):
        """
        Calculates and upserts GroupDailyInsight records for both REGION and CUSTOM_GROUP
        for the specified date by aggregating from location_daily_insights.
        If org_id is provided, it restricts aggregation to that organization only.
        """
        org_filter = "AND r.organization_id = :org_id" if org_id is not None else ""
        
        # 1. Aggregate for REGIONS
        region_sql = f"""
            INSERT INTO group_daily_insights (
                organization_id, group_type, group_id, date, provider,
                profile_views, search_impressions, maps_views,
                desktop_search_impressions, mobile_search_impressions,
                desktop_maps_impressions, mobile_maps_impressions,
                phone_calls, website_clicks, direction_requests,
                searches_direct, searches_indirect, searches_chain,
                reviews_received, avg_rating, positive_review_count,
                neutral_review_count, negative_review_count, avg_sentiment_score,
                response_rate, avg_response_time_hours,
                click_through_rate, call_conversion_rate, direction_conversion_rate
            )
            SELECT 
                r.organization_id,
                'REGION',
                r.id,
                :date,
                'gbp',
                COALESCE(SUM(ldi.profile_views), 0),
                COALESCE(SUM(ldi.search_impressions), 0),
                COALESCE(SUM(ldi.maps_views), 0),
                COALESCE(SUM(ldi.desktop_search_impressions), 0),
                COALESCE(SUM(ldi.mobile_search_impressions), 0),
                COALESCE(SUM(ldi.desktop_maps_impressions), 0),
                COALESCE(SUM(ldi.mobile_maps_impressions), 0),
                COALESCE(SUM(ldi.phone_calls), 0),
                COALESCE(SUM(ldi.website_clicks), 0),
                COALESCE(SUM(ldi.direction_requests), 0),
                COALESCE(SUM(ldi.searches_direct), 0),
                COALESCE(SUM(ldi.searches_indirect), 0),
                COALESCE(SUM(ldi.searches_chain), 0),
                COALESCE(SUM(ldi.reviews_received), 0),
                
                -- avg_rating
                CASE WHEN SUM(ldi.reviews_received) > 0 THEN 
                    SUM(ldi.avg_rating * ldi.reviews_received) / SUM(ldi.reviews_received)
                ELSE NULL END,

                COALESCE(SUM(ldi.positive_review_count), 0),
                COALESCE(SUM(ldi.neutral_review_count), 0),
                COALESCE(SUM(ldi.negative_review_count), 0),

                -- avg_sentiment
                CASE WHEN SUM(ldi.reviews_received) > 0 THEN 
                    SUM(ldi.avg_sentiment_score * ldi.reviews_received) / SUM(ldi.reviews_received)
                ELSE NULL END,

                -- response_rate
                CASE WHEN SUM(ldi.reviews_received) > 0 THEN
                    SUM(ldi.response_rate * ldi.reviews_received) / SUM(ldi.reviews_received)
                ELSE 0.0 END,

                -- avg_response_time
                CASE WHEN SUM(ldi.reviews_received) > 0 THEN
                    SUM(ldi.avg_response_time_hours * ldi.reviews_received) / SUM(ldi.reviews_received)
                ELSE NULL END,

                -- derived rates
                CASE WHEN SUM(ldi.profile_views) > 0 THEN (CAST(SUM(ldi.website_clicks) AS float) / SUM(ldi.profile_views)) * 100 ELSE NULL END,
                CASE WHEN SUM(ldi.profile_views) > 0 THEN (CAST(SUM(ldi.phone_calls) AS float) / SUM(ldi.profile_views)) * 100 ELSE NULL END,
                CASE WHEN SUM(ldi.profile_views) > 0 THEN (CAST(SUM(ldi.direction_requests) AS float) / SUM(ldi.profile_views)) * 100 ELSE NULL END
                
            FROM regions r
            JOIN region_locations rl ON r.id = rl.region_id
            JOIN location_daily_insights ldi ON rl.location_id = ldi.location_id AND ldi.date = :date
                AND ldi.organization_id = r.organization_id
            WHERE 1=1 {org_filter}
            GROUP BY r.organization_id, r.id
            ON CONFLICT (group_type, group_id, date, provider) DO UPDATE SET
                profile_views = EXCLUDED.profile_views,
                search_impressions = EXCLUDED.search_impressions,
                maps_views = EXCLUDED.maps_views,
                desktop_search_impressions = EXCLUDED.desktop_search_impressions,
                mobile_search_impressions = EXCLUDED.mobile_search_impressions,
                desktop_maps_impressions = EXCLUDED.desktop_maps_impressions,
                mobile_maps_impressions = EXCLUDED.mobile_maps_impressions,
                phone_calls = EXCLUDED.phone_calls,
                website_clicks = EXCLUDED.website_clicks,
                direction_requests = EXCLUDED.direction_requests,
                searches_direct = EXCLUDED.searches_direct,
                searches_indirect = EXCLUDED.searches_indirect,
                searches_chain = EXCLUDED.searches_chain,
                reviews_received = EXCLUDED.reviews_received,
                avg_rating = EXCLUDED.avg_rating,
                positive_review_count = EXCLUDED.positive_review_count,
                neutral_review_count = EXCLUDED.neutral_review_count,
                negative_review_count = EXCLUDED.negative_review_count,
                avg_sentiment_score = EXCLUDED.avg_sentiment_score,
                response_rate = EXCLUDED.response_rate,
                avg_response_time_hours = EXCLUDED.avg_response_time_hours,
                click_through_rate = EXCLUDED.click_through_rate,
                call_conversion_rate = EXCLUDED.call_conversion_rate,
                direction_conversion_rate = EXCLUDED.direction_conversion_rate;
        """

        # 2. Aggregate for CUSTOM_GROUPS
        custom_group_sql = region_sql.replace("regions r", "custom_groups r") \
                                     .replace("region_locations rl", "custom_group_locations rl") \
                                     .replace("rl.region_id", "rl.custom_group_id") \
                                     .replace("'REGION'", "'CUSTOM_GROUP'")

        params = {"date": target_date}
        if org_id is not None:
            params["org_id"] = org_id

        db.execute(text(region_sql), params)
        db.execute(text(custom_group_sql), params)
        
        # 3. Update avg_rank and solv for the date by joining local_rank_scans
        rank_org_filter_regions = "AND r.organization_id = :org_id" if org_id is not None else ""
        rank_org_filter_custom = "AND cg.organization_id = :org_id" if org_id is not None else ""

        rank_sql = f"""
            WITH group_ranks AS (
                SELECT
                    rl.region_id as group_id,
                    'REGION' as group_type,
                    AVG(lrs.avg_rank) as avg_rank,
                    AVG(lrs.solv) as solv
                FROM region_locations rl
                JOIN regions r ON rl.region_id = r.id {rank_org_filter_regions}
                JOIN local_rank_scans lrs ON rl.location_id = lrs.location_id 
                WHERE lrs.created_at >= :date AND lrs.created_at < (:date::date + INTERVAL '1 day') AND lrs.status = 'Completed'
                GROUP BY rl.region_id
                
                UNION ALL
                
                SELECT
                    cgl.custom_group_id as group_id,
                    'CUSTOM_GROUP' as group_type,
                    AVG(lrs.avg_rank) as avg_rank,
                    AVG(lrs.solv) as solv
                FROM custom_group_locations cgl
                JOIN custom_groups cg ON cgl.custom_group_id = cg.id {rank_org_filter_custom}
                JOIN local_rank_scans lrs ON cgl.location_id = lrs.location_id 
                WHERE lrs.created_at >= :date AND lrs.created_at < (:date::date + INTERVAL '1 day') AND lrs.status = 'Completed'
                GROUP BY cgl.custom_group_id
            )
            UPDATE group_daily_insights gdi
            SET 
                avg_rank = gr.avg_rank,
                solv = gr.solv
            FROM group_ranks gr
            WHERE gdi.group_id = gr.group_id 
              AND gdi.group_type = gr.group_type
              AND gdi.date = :date;
        """
        db.execute(text(rank_sql), params)
        db.commit()

    @staticmethod
    def backfill_group_insights(db: Session, start_date: date, end_date: date, org_id: Optional[int] = None):
        """
        Backfills the specified date range. If org_id is provided, it only processes that org.
        """
        delta = end_date - start_date
        for i in range(delta.days + 1):
            target_date = start_date + timedelta(days=i)
            ComparisonAggregationService.aggregate_group_insights(db, target_date, org_id)
