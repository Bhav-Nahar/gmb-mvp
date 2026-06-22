import datetime
import math
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from app.models.location import Location
from app.models.review import Review
from app.models.location_health_score import LocationHealthScore
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
        cap_log = math.log(leaderboard_config.REVIEW_VOLUME_LOG_CAP + 1)
        val_log = math.log(review_count + 1)
        if val_log >= cap_log:
            return 100.0
        return (val_log / cap_log) * 100.0

    @staticmethod
    def normalize_review_velocity(monthly_count: int, total_reviews: int) -> float:
        if monthly_count == 0 and total_reviews >= leaderboard_config.MIN_REVIEWS_FOR_ELIGIBILITY:
            return 35.0  # Neutral floor for established locations
        cap = leaderboard_config.REVIEW_VELOCITY_CAP
        return round(min(math.sqrt(monthly_count) / math.sqrt(cap), 1.0) * 100.0, 2)

    @staticmethod
    def _month_date_range(period_label: str) -> Optional[Tuple[datetime.date, datetime.date]]:
        """First and last calendar day of a 'YYYY-MM' label. None if unparseable."""
        try:
            year, month = map(int, period_label.split('-'))
            start = datetime.date(year, month, 1)
            if month == 12:
                next_start = datetime.date(year + 1, 1, 1)
            else:
                next_start = datetime.date(year, month + 1, 1)
            return start, next_start - datetime.timedelta(days=1)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def assign_cohort(review_volume_raw: int) -> str:
        """Maps a review count to its volume-band cohort label."""
        count = review_volume_raw or 0
        for min_inclusive, label in leaderboard_config.COHORT_VOLUME_BANDS:
            if count >= min_inclusive:
                return label
        return leaderboard_config.COHORT_VOLUME_BANDS[-1][1]

    @staticmethod
    def period_to_range(period_label: str) -> Tuple[datetime.date, datetime.date]:
        """Strict 'YYYY-MM' -> (first_day, last_day). Raises ValueError on bad input."""
        rng = LeaderboardService._month_date_range(period_label)
        if rng is None:
            raise ValueError("Invalid period format. Expected YYYY-MM.")
        return rng

    @staticmethod
    def effective_weights(has_health: bool) -> Dict[str, float]:
        """Metric weights renormalized to sum to 1.0. When a location has no health score
        yet, health is dropped and its weight is spread proportionally across the others, so
        a missing profile scan doesn't silently cost ~25 pts of composite."""
        w = dict(leaderboard_config.LEADERBOARD_METRIC_WEIGHTS)
        if not has_health:
            w.pop("health_score", None)
        total = sum(w.values()) or 1.0
        return {k: v / total for k, v in w.items()}

    @staticmethod
    def calculate_metric_contributions(snapshot: LeaderboardSnapshot) -> Dict[str, float]:
        """Helper to get actual point contributions from raw scores and weights."""
        if snapshot.composite_score is None:
            return {}
            
        w = LeaderboardService.effective_weights(snapshot.health_score_input is not None)
        return {
            "rating_contribution": (snapshot.rating_score or 0) * w.get("average_rating", 0),
            "health_score_contribution": (snapshot.health_score_input or 0) * w.get("health_score", 0),
            "review_volume_contribution": (snapshot.review_volume_score or 0) * w.get("review_volume", 0),
            "review_velocity_contribution": (snapshot.review_velocity_score or 0) * w.get("review_velocity", 0),
            "response_rate_contribution": (snapshot.response_rate_score or 0) * w.get("response_rate", 0)
        }

    @staticmethod
    def compute_next_action(snapshot: LeaderboardSnapshot, cohort_peers: List[LeaderboardSnapshot]) -> Optional[Dict]:
        """Highest-leverage action to climb the leaderboard: the metric whose gap to the
        cohort benchmark, weighted, yields the most composite points. Returns None for
        ineligible locations. Projected rank is computed against cohort_peers."""
        if not snapshot.is_eligible or snapshot.composite_score is None:
            return None

        w = leaderboard_config.LEADERBOARD_METRIC_WEIGHTS
        # (weight_key, score_attr) for each scored metric.
        metrics = [
            ("average_rating", "rating_score"),
            ("health_score", "health_score_input"),
            ("review_volume", "review_volume_score"),
            ("review_velocity", "review_velocity_score"),
            ("response_rate", "response_rate_score"),
        ]

        # Cohort benchmark = mean of each metric's score across eligible peers (the realistic
        # target). Leaders who already beat peers everywhere fall back to gap-to-100.
        peers = [p for p in cohort_peers if p.is_eligible] or [snapshot]
        best = None
        for weight_key, attr in metrics:
            weight = w.get(weight_key, 0)
            if weight <= 0:
                continue
            current = getattr(snapshot, attr) or 0.0
            benchmark = sum((getattr(p, attr) or 0.0) for p in peers) / len(peers)
            target = benchmark if benchmark > current else 100.0
            leverage = max(0.0, target - current) * weight
            if best is None or leverage > best["leverage"]:
                best = {"weight_key": weight_key, "current": current, "target": target,
                        "leverage": leverage, "weight": weight}

        if best is None or best["leverage"] <= 0:
            return None

        projected = round(snapshot.composite_score + best["leverage"], 2)
        # Projected cohort rank if this location reaches the projected composite.
        better = sum(1 for p in peers if p.location_id != snapshot.location_id
                     and (p.composite_score or 0.0) > projected)
        projected_cohort_rank = better + 1

        headline, detail = LeaderboardService._action_copy(best["weight_key"], snapshot)
        return {
            "metric": best["weight_key"],
            "headline": headline,
            "detail": detail,
            "current_score": round(best["current"], 2),
            "target_score": round(best["target"], 2),
            "weight": best["weight"],
            "projected_composite_gain": round(best["leverage"], 2),
            "projected_composite_score": projected,
            "current_cohort_rank": snapshot.cohort_rank,
            "projected_cohort_rank": projected_cohort_rank,
        }

    @staticmethod
    def _action_copy(metric: str, s: LeaderboardSnapshot) -> Tuple[str, str]:
        """Concrete, human action text per metric, with real numbers from the snapshot so
        the advice is specific ('reach 50 reviews → +12 pts'), not generic."""
        w = leaderboard_config.LEADERBOARD_METRIC_WEIGHTS

        def pct(key):  # metric weight as a whole-number percent, e.g. "15%"
            return f"{round(w.get(key, 0) * 100)}%"

        if metric == "response_rate":
            vol = s.review_volume_raw or 0
            rate = s.response_rate_raw or 0.0
            unanswered = round(vol * (1 - rate / 100.0))
            return (f"Reply to your {unanswered} unanswered review(s)",
                    f"You've replied to {round(rate)}% of reviews. Replies are fully in your control "
                    f"and worth {pct('response_rate')} of the score — clear the backlog to climb fast.")

        if metric == "average_rating":
            cur = round(s.average_rating_raw or 0, 2)
            return ("Lift your average star rating",
                    f"You're at {cur}★. Rating is the single biggest lever ({pct('average_rating')}); "
                    f"prioritise service recovery on recent 1–2★ reviews and ask happy customers to rate.")

        if metric == "review_volume":
            current = s.review_volume_raw or 0
            # Next milestone; volume score is log-scaled so low counts gain the most.
            target = next((m for m in (25, 50, 100, 200, 500) if m > current), current + 50)
            gain = (LeaderboardService.normalize_review_volume(target)
                    - LeaderboardService.normalize_review_volume(current)) * w.get("review_volume", 0)
            return (f"Collect {target - current} more reviews (reach {target})",
                    f"You have {current} reviews. Because volume is log-scaled, getting to {target} adds "
                    f"about {gain:.1f} pts — early reviews move the needle most.")

        if metric == "review_velocity":
            v = s.review_velocity_raw or 0
            return ("Bring in fresh reviews every month",
                    f"You logged {v} review(s) this period. Velocity rewards a steady recent flow "
                    f"({pct('review_velocity')} of the score), so send review requests to this month's customers.")

        if metric == "health_score":
            cur = round(s.health_score_raw or 0, 1)
            return ("Complete your business profile",
                    f"Your profile health is {cur}/100 ({pct('health_score')} of the score). "
                    f"Open your health-score recommendations for the exact fields to fill in.")

        return ("Keep improving", "")

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
            # ponytail: delete without committing — stays in the same transaction as the
            # insert below, so a failure mid-generation rolls back and keeps the old snapshots.
            db.query(LeaderboardSnapshot).filter(
                LeaderboardSnapshot.organization_id == organization_id,
                LeaderboardSnapshot.period_label == period_label
            ).delete(synchronize_session=False)

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
            has_health = loc.id in health_scores
            health_score_raw = health_scores.get(loc.id)  # None if no scan yet
            
            # Response Rate
            r_stat = review_map.get(loc.id)
            total_revs = r_stat.total_revs if r_stat else 0
            replied_revs = r_stat.replied_revs if r_stat else 0
            response_rate_raw = (replied_revs / total_revs * 100.0) if total_revs > 0 else 0.0
            
            review_volume_raw = loc.total_reviews or 0
            
            # Review Velocity
            v_stat = velocity_map.get(loc.id)
            review_velocity_raw = v_stat.velocity if v_stat else 0
            
            # Normalization
            rating_score = avg_rating_raw * 20.0
            response_rate_score = response_rate_raw
            health_score_input = float(health_score_raw) if health_score_raw is not None else None
            review_volume_score = LeaderboardService.normalize_review_volume(review_volume_raw)
            review_velocity_score = LeaderboardService.normalize_review_velocity(review_velocity_raw, review_volume_raw)

            # engagement_growth dropped in v5 (uncontrollable + noisy); columns left null.
            engagement_growth_raw = None
            engagement_growth_score = None

            # Composite Score (only if eligible). Weights renormalize if health is missing.
            composite_score = None
            if is_eligible:
                w = LeaderboardService.effective_weights(has_health)
                composite_score = (
                    (rating_score * w.get("average_rating", 0)) +
                    ((health_score_input or 0.0) * w.get("health_score", 0)) +
                    (review_volume_score * w.get("review_volume", 0)) +
                    (review_velocity_score * w.get("review_velocity", 0)) +
                    (response_rate_score * w.get("response_rate", 0))
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
                cohort=LeaderboardService.assign_cohort(review_volume_raw),
                cohort_rank=None,
                cohort_size=None,
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

        # 5b. Cohort ranking — eligible_snapshots is already globally sorted by the same
        # tie-breakers, so a per-cohort counter over that order gives the within-band rank.
        cohort_counter: Dict[str, int] = {}
        for snap in eligible_snapshots:
            cohort_counter[snap.cohort] = cohort_counter.get(snap.cohort, 0) + 1
            snap.cohort_rank = cohort_counter[snap.cohort]
        for snap in eligible_snapshots:
            snap.cohort_size = cohort_counter[snap.cohort]

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
