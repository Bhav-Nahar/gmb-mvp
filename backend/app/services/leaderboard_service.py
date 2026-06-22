import datetime
import math
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from app.models.location import Location
from app.models.review import Review
from app.models.location_health_score import LocationHealthScore
from app.models.location_daily_insights import LocationDailyInsight
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.enums import IneligibilityReason
from app.core import leaderboard_config


class LeaderboardService:
    @staticmethod
    def _get_prior_period_label(period_label: str) -> str:
        """Returns the immediate prior calendar month. E.g. '2026-06' -> '2026-05'"""
        try:
            year, month = map(int, period_label.split('-'))
            if month == 1:
                return f"{year - 1}-12"
            return f"{year}-{month - 1:02d}"
        except ValueError:
            # Fallback if label format is unexpected
            return ""

    @staticmethod
    def normalize_review_volume(review_count: int) -> float:
        if review_count <= 0:
            return 0.0
        # log10(count+1) / log10(cap+1) * 100  (see config doc)
        cap_log = math.log10(leaderboard_config.REVIEW_VOLUME_LOG_CAP + 1)
        val_log = math.log10(review_count + 1)
        if val_log >= cap_log:
            return 100.0
        return (val_log / cap_log) * 100.0

    @staticmethod
    def normalize_engagement_growth(growth_percent: float) -> float:
        cap = leaderboard_config.ENGAGEMENT_GROWTH_CAP_PERCENT
        floor = leaderboard_config.ENGAGEMENT_GROWTH_FLOOR_PERCENT
        if math.isinf(growth_percent):
            # Zero prior-period baseline: neutral, not a free max score.
            # ponytail: 50 = neutral; revisit if new locations should be rewarded.
            return 50.0 if growth_percent > 0 else 0.0
        
        # Clamp
        clamped = max(floor, min(cap, growth_percent))
        
        # Map [floor, cap] to [0, 100]
        # range = cap - floor
        # score = (clamped - floor) / range * 100
        rng = cap - floor
        if rng == 0:
            return 50.0 # fallback if cap == floor
        
        return ((clamped - floor) / rng) * 100.0

    @staticmethod
    def normalize_review_velocity(velocity: int) -> float:
        if velocity <= 0:
            return 0.0
        cap = leaderboard_config.REVIEW_VELOCITY_CAP
        if velocity >= cap:
            return 100.0
        return (velocity / cap) * 100.0

    @staticmethod
    def calculate_metric_contributions(snapshot: LeaderboardSnapshot) -> Dict[str, float]:
        """Helper to get actual point contributions from raw scores and weights."""
        if snapshot.composite_score is None:
            return {}
            
        w = leaderboard_config.LEADERBOARD_METRIC_WEIGHTS
        return {
            "rating_contribution": (snapshot.rating_score or 0) * w.get("average_rating", 0),
            "health_score_contribution": (snapshot.health_score_input or 0) * w.get("health_score", 0),
            "review_volume_contribution": (snapshot.review_volume_score or 0) * w.get("review_volume", 0),
            "review_velocity_contribution": (snapshot.review_velocity_score or 0) * w.get("review_velocity", 0),
            "engagement_growth_contribution": (snapshot.engagement_growth_score or 0) * w.get("engagement_growth", 0)
        }

    @staticmethod
    def generate_snapshots_for_period(
        db: Session,
        organization_id: int,
        period_label: str,
        period_start: datetime.date,
        period_end: datetime.date,
        force: bool = False
    ) -> List[LeaderboardSnapshot]:
        # 1. Idempotency Check
        existing_count = db.query(LeaderboardSnapshot).filter(
            LeaderboardSnapshot.organization_id == organization_id,
            LeaderboardSnapshot.period_label == period_label
        ).count()
        
        if existing_count > 0:
            if not force:
                return []
            db.query(LeaderboardSnapshot).filter(
                LeaderboardSnapshot.organization_id == organization_id,
                LeaderboardSnapshot.period_label == period_label
            ).delete()
            db.commit()

        # 2. Fetch all locations for the org
        locations = db.query(Location).filter(
            Location.organization_id == organization_id,
            Location.billing_status == 'active'
        ).all()
        
        if not locations:
            return []
            
        location_ids = [loc.id for loc in locations]

        # 3. Bulk Fetch Data (N+1 Prevention)
        
        # 3a. Health Scores
        health_scores = {
            hs.location_id: hs.score for hs in db.query(LocationHealthScore).filter(
                LocationHealthScore.location_id.in_(location_ids)
            ).all()
        }
        
        # 3b. Reviews (for Response Rate and Total Volume fallback if needed)
        review_stats = db.query(
            Review.location_id,
            func.count(Review.id).label("total_revs"),
            func.count(func.nullif(Review.is_replied, False)).label("replied_revs")
        ).filter(
            Review.location_id.in_(location_ids),
            Review.is_deleted == False
        ).group_by(Review.location_id).all()
        
        review_map = {row.location_id: row for row in review_stats}

        # 3c. Insights (for Engagement Growth)
        length_days = (period_end - period_start).days + 1
        prior_end = period_start - datetime.timedelta(days=1)
        prior_start = prior_end - datetime.timedelta(days=length_days - 1)
        
        insight_stats = db.query(
            LocationDailyInsight.location_id,
            func.sum(
                case(
                    (LocationDailyInsight.date.between(period_start, period_end), 
                     LocationDailyInsight.search_impressions + LocationDailyInsight.maps_views),
                    else_=0
                )
            ).label("current_engagement"),
            func.sum(
                case(
                    (LocationDailyInsight.date.between(prior_start, prior_end), 
                     LocationDailyInsight.search_impressions + LocationDailyInsight.maps_views),
                    else_=0
                )
            ).label("prior_engagement")
        ).filter(
            LocationDailyInsight.location_id.in_(location_ids),
            LocationDailyInsight.date.between(prior_start, period_end)
        ).group_by(LocationDailyInsight.location_id).all()
        
        insight_map = {row.location_id: row for row in insight_stats}
        
        # 3d. Previous Period Snapshots
        prior_period_label = LeaderboardService._get_prior_period_label(period_label)
        prior_snapshots = {
            snap.location_id: snap for snap in db.query(LeaderboardSnapshot).filter(
                LeaderboardSnapshot.organization_id == organization_id,
                LeaderboardSnapshot.period_label == prior_period_label
            ).all()
        }

        # 3e. Review Velocity
        velocity_stats = db.query(
            Review.location_id,
            func.count(Review.id).label("velocity")
        ).filter(
            Review.location_id.in_(location_ids),
            Review.is_deleted == False,
            Review.review_created_at >= period_start,
            Review.review_created_at <= period_end
        ).group_by(Review.location_id).all()
        
        velocity_map = {row.location_id: row for row in velocity_stats}

        # 4. Process each location
        snapshots = []
        eligible_snapshots = []
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        for loc in locations:
            # Eligibility
            is_eligible = True
            ineligibility_reason = None
            
            insufficient_reviews = (loc.total_reviews or 0) < leaderboard_config.MIN_REVIEWS_FOR_ELIGIBILITY
            
            insufficient_sync = False
            if loc.created_at:
                created_at = loc.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=datetime.timezone.utc)
                days_synced = (now_utc - created_at).days
                if days_synced < leaderboard_config.MIN_DAYS_SYNCED_FOR_ELIGIBILITY:
                    insufficient_sync = True
                    
            if insufficient_reviews and insufficient_sync:
                is_eligible = False
                ineligibility_reason = IneligibilityReason.INSUFFICIENT_REVIEWS_AND_SYNC_HISTORY
            elif insufficient_reviews:
                is_eligible = False
                ineligibility_reason = IneligibilityReason.INSUFFICIENT_REVIEWS
            elif insufficient_sync:
                is_eligible = False
                ineligibility_reason = IneligibilityReason.INSUFFICIENT_SYNC_HISTORY

            # Raw Inputs
            avg_rating_raw = loc.average_rating or 0.0
            health_score_raw = health_scores.get(loc.id, 0.0)
            
            # Response Rate
            r_stat = review_map.get(loc.id)
            total_revs = r_stat.total_revs if r_stat else 0
            replied_revs = r_stat.replied_revs if r_stat else 0
            response_rate_raw = (replied_revs / total_revs * 100.0) if total_revs > 0 else 0.0
            
            review_volume_raw = loc.total_reviews or 0
            
            # Review Velocity
            v_stat = velocity_map.get(loc.id)
            review_velocity_raw = v_stat.velocity if v_stat else 0
            
            # Engagement Growth
            i_stat = insight_map.get(loc.id)
            current_eng = float(i_stat.current_engagement or 0) if i_stat else 0.0
            prior_eng = float(i_stat.prior_engagement or 0) if i_stat else 0.0
            
            if prior_eng == 0:
                engagement_growth_raw = 0.0 if current_eng == 0 else float('inf')
            else:
                engagement_growth_raw = ((current_eng - prior_eng) / prior_eng) * 100.0

            # Normalization
            rating_score = avg_rating_raw * 20.0
            response_rate_score = response_rate_raw
            health_score_input = float(health_score_raw)
            review_volume_score = LeaderboardService.normalize_review_volume(review_volume_raw)
            engagement_growth_score = LeaderboardService.normalize_engagement_growth(engagement_growth_raw)
            review_velocity_score = LeaderboardService.normalize_review_velocity(review_velocity_raw)

            # Composite Score (only if eligible)
            composite_score = None
            if is_eligible:
                w = leaderboard_config.LEADERBOARD_METRIC_WEIGHTS
                composite_score = (
                    (rating_score * w.get("average_rating", 0)) +
                    (health_score_input * w.get("health_score", 0)) +
                    (review_volume_score * w.get("review_volume", 0)) +
                    (review_velocity_score * w.get("review_velocity", 0)) +
                    (engagement_growth_score * w.get("engagement_growth", 0))
                )

            # Previous Rank & Streaks
            prior_snap = prior_snapshots.get(loc.id)
            previous_rank = prior_snap.rank if prior_snap else None
            
            streak_count = 0
            # Will be set later after ranking if loc becomes #1

            snap = LeaderboardSnapshot(
                organization_id=organization_id,
                location_id=loc.id,
                period_label=period_label,
                period_start=period_start,
                period_end=period_end,
                snapshot_version=leaderboard_config.LEADERBOARD_SCORING_VERSION,
                
                is_eligible=is_eligible,
                ineligibility_reason=ineligibility_reason,
                
                composite_score=composite_score,
                rank=None,
                previous_rank=previous_rank,
                rank_movement=None,
                streak_count=streak_count,
                most_improved_flag=False,
                
                average_rating_raw=avg_rating_raw,
                response_rate_raw=response_rate_raw,
                health_score_raw=health_score_raw,
                review_volume_raw=review_volume_raw,
                engagement_growth_raw=engagement_growth_raw,
                review_velocity_raw=review_velocity_raw,
                
                rating_score=rating_score,
                response_rate_score=response_rate_score,
                health_score_input=health_score_input,
                review_volume_score=review_volume_score,
                engagement_growth_score=engagement_growth_score,
                review_velocity_score=review_velocity_score
            )
            snapshots.append(snap)
            if is_eligible:
                eligible_snapshots.append(snap)

        # 5. Ranking (4-level deterministic tie-breaker)
        # 1. composite_score (DESC)
        # 2. rating_score (DESC)
        # 3. review_volume_raw (DESC)
        # 4. location_id (ASC)
        eligible_snapshots.sort(key=lambda s: (
            s.composite_score or 0.0,
            s.rating_score or 0.0,
            s.review_volume_raw or 0,
            -s.location_id
        ), reverse=True)

        # Assign Ranks and calculate rank movement
        best_improvement = 0
        most_improved_candidates = []
        
        for i, snap in enumerate(eligible_snapshots):
            snap.rank = i + 1
            if snap.previous_rank is not None:
                snap.rank_movement = snap.previous_rank - snap.rank
                if snap.rank_movement > 0:
                    if snap.rank_movement > best_improvement:
                        best_improvement = snap.rank_movement
                        most_improved_candidates = [snap]
                    elif snap.rank_movement == best_improvement:
                        most_improved_candidates.append(snap)
            
            # Streaks
            if snap.rank == 1:
                prior_snap = prior_snapshots.get(snap.location_id)
                if prior_snap and prior_snap.rank == 1:
                    snap.streak_count = (prior_snap.streak_count or 1) + 1
                else:
                    snap.streak_count = 1
            else:
                snap.streak_count = 0

        # Most Improved Tie-breaker
        if most_improved_candidates and best_improvement > 0:
            most_improved_candidates.sort(key=lambda s: (
                s.composite_score or 0.0,
                s.rating_score or 0.0,
                s.review_volume_raw or 0,
                -s.location_id
            ), reverse=True)
            most_improved_candidates[0].most_improved_flag = True

        # Insert All
        db.add_all(snapshots)
        db.commit()
        
        return snapshots
