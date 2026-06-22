import datetime
import pytest
from app.services.leaderboard_service import LeaderboardService
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.enums import IneligibilityReason
from app.core import leaderboard_config

def test_normalize_review_volume():
    # Log scale up to cap
    assert LeaderboardService.normalize_review_volume(0) == 0.0
    assert LeaderboardService.normalize_review_volume(-5) == 0.0
    
    cap = leaderboard_config.REVIEW_VOLUME_LOG_CAP
    assert LeaderboardService.normalize_review_volume(cap) == 100.0
    assert LeaderboardService.normalize_review_volume(cap * 2) == 100.0
    
    # 10 is less than 100
    score_10 = LeaderboardService.normalize_review_volume(10)
    score_100 = LeaderboardService.normalize_review_volume(100)
    assert 0 < score_10 < score_100 <= 100.0

def test_normalize_review_velocity():
    # Below floor for ineligible locations
    assert LeaderboardService.normalize_review_velocity(0, 1) == 0.0
    # Zero-floor logic for established locations
    assert LeaderboardService.normalize_review_velocity(0, 10) == 35.0
    
    cap = leaderboard_config.REVIEW_VELOCITY_CAP
    assert LeaderboardService.normalize_review_velocity(cap, 10) == 100.0
    assert LeaderboardService.normalize_review_velocity(cap * 2, 10) == 100.0
    
    # Sqrt curve check
    # if cap is 41, sqrt(cap) is ~6.4.
    # We just ensure it's > 0 and <= 100
    score_mid = LeaderboardService.normalize_review_velocity(cap // 2, 10)
    assert 0.0 < score_mid < 100.0

def test_effective_weights_renormalizes_without_health():
    full = LeaderboardService.effective_weights(True)
    assert full == leaderboard_config.LEADERBOARD_METRIC_WEIGHTS  # no-op when health present
    assert abs(sum(full.values()) - 1.0) < 1e-9

    no_health = LeaderboardService.effective_weights(False)
    assert "health_score" not in no_health
    assert abs(sum(no_health.values()) - 1.0) < 1e-9  # still sums to 1
    # rating keeps its proportional share, scaled up since health's weight is redistributed
    assert no_health["average_rating"] > full["average_rating"]

def test_assign_cohort():
    assert LeaderboardService.assign_cohort(0) == "Emerging"
    assert LeaderboardService.assign_cohort(49) == "Emerging"
    assert LeaderboardService.assign_cohort(50) == "Growing"
    assert LeaderboardService.assign_cohort(199) == "Growing"
    assert LeaderboardService.assign_cohort(200) == "Established"
    assert LeaderboardService.assign_cohort(1000) == "Flagship"
    assert LeaderboardService.assign_cohort(None) == "Emerging"

def test_compute_next_action():
    # Eligible location weak on response_rate; peer is strong -> response_rate is top action.
    me = LeaderboardSnapshot(
        location_id=1, is_eligible=True, composite_score=60.0, cohort="Growing", cohort_rank=2,
        rating_score=90.0, health_score_input=90.0, review_volume_score=90.0,
        review_velocity_score=90.0, response_rate_score=20.0, engagement_growth_score=90.0,
        review_volume_raw=100, response_rate_raw=20.0,
    )
    peer = LeaderboardSnapshot(
        location_id=2, is_eligible=True, composite_score=80.0, cohort="Growing", cohort_rank=1,
        rating_score=90.0, health_score_input=90.0, review_volume_score=90.0,
        review_velocity_score=90.0, response_rate_score=95.0, engagement_growth_score=90.0,
    )
    action = LeaderboardService.compute_next_action(me, [me, peer])
    assert action["metric"] == "response_rate"
    assert action["projected_composite_gain"] > 0
    assert "80" in action["headline"] or "unanswered" in action["headline"]
    assert action["current_cohort_rank"] == 2

    # Ineligible -> no action
    bad = LeaderboardSnapshot(location_id=3, is_eligible=False, composite_score=None)
    assert LeaderboardService.compute_next_action(bad, []) is None

def test_calculate_metric_contributions():
    snap = LeaderboardSnapshot(
        composite_score=50.0,
        rating_score=100.0,
        response_rate_score=100.0,
        health_score_input=100.0,
        review_volume_score=100.0,
        engagement_growth_score=100.0,
        review_velocity_score=100.0
    )
    
    contribs = LeaderboardService.calculate_metric_contributions(snap)
    w = leaderboard_config.LEADERBOARD_METRIC_WEIGHTS
    
    assert contribs["rating_contribution"] == 100.0 * w.get("average_rating", 0)
    assert contribs["health_score_contribution"] == 100.0 * w.get("health_score", 0)
    assert contribs["review_volume_contribution"] == 100.0 * w.get("review_volume", 0)
    assert contribs["review_velocity_contribution"] == 100.0 * w.get("review_velocity", 0)
    
def test_prior_period_label():
    assert LeaderboardService._get_prior_period_label("2026-06") == "2026-05"
    assert LeaderboardService._get_prior_period_label("2026-01") == "2025-12"
    assert LeaderboardService._get_prior_period_label("2025-10") == "2025-09"

def test_generate_snapshots_for_period(db):
    from app.models.organization import Organization
    from app.models.location import Location
    from app.models.location_health_score import LocationHealthScore
    from app.models.location_daily_insights import LocationDailyInsight
    from app.models.review import Review
    
    # 1. Setup Organization
    org = Organization(id=1, name="Test Org")
    db.add(org)
    db.commit()
    
    # 2. Setup Locations
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    old_date = now_utc - datetime.timedelta(days=30)
    recent_date = now_utc - datetime.timedelta(days=5)
    
    # Eligible A
    loc_a = Location(
        id=10, organization_id=1, google_location_id="loc_a", location_name="Loc A",
        average_rating=4.5, total_reviews=10, created_at=old_date, billing_status="active"
    )
    # Eligible B (higher reviews -> tie breaker)
    loc_b = Location(
        id=20, organization_id=1, google_location_id="loc_b", location_name="Loc B",
        average_rating=4.5, total_reviews=20, created_at=old_date, billing_status="active"
    )
    # Ineligible C: Insufficient reviews (total_reviews < 3)
    loc_c = Location(
        id=30, organization_id=1, google_location_id="loc_c", location_name="Loc C",
        average_rating=5.0, total_reviews=1, created_at=old_date, billing_status="active"
    )
    # Ineligible D: Insufficient sync history (days < 14)
    loc_d = Location(
        id=40, organization_id=1, google_location_id="loc_d", location_name="Loc D",
        average_rating=5.0, total_reviews=10, created_at=recent_date, billing_status="active"
    )
    # Ineligible E: Both
    loc_e = Location(
        id=50, organization_id=1, google_location_id="loc_e", location_name="Loc E",
        average_rating=5.0, total_reviews=1, created_at=recent_date, billing_status="active"
    )
    
    db.add_all([loc_a, loc_b, loc_c, loc_d, loc_e])
    db.commit()
    
    # 3. Add Health Scores
    db.add(LocationHealthScore(location_id=10, score=80, potential_score=100, label="Good", breakdown={}, recommendations=[], last_recalculated_reason="test"))
    db.add(LocationHealthScore(location_id=20, score=80, potential_score=100, label="Good", breakdown={}, recommendations=[], last_recalculated_reason="test"))
    db.commit()
    
    # 4. Generate snapshots
    period_start = datetime.date(2026, 6, 1)
    period_end = datetime.date(2026, 6, 30)
    
    snapshots = LeaderboardService.generate_snapshots_for_period(
        db, organization_id=1, period_label="2026-06",
        period_start=period_start, period_end=period_end
    )
    
    assert len(snapshots) == 5
    snap_map = {s.location_id: s for s in snapshots}
    
    # Check Eligibility and Reasons
    assert snap_map[10].is_eligible is True
    assert snap_map[20].is_eligible is True
    
    assert snap_map[30].is_eligible is False
    assert snap_map[30].ineligibility_reason == IneligibilityReason.INSUFFICIENT_REVIEWS
    
    assert snap_map[40].is_eligible is False
    assert snap_map[40].ineligibility_reason == IneligibilityReason.INSUFFICIENT_SYNC_HISTORY
    
    assert snap_map[50].is_eligible is False
    assert snap_map[50].ineligibility_reason == IneligibilityReason.INSUFFICIENT_REVIEWS_AND_SYNC_HISTORY
    
    # Check Ranks
    assert snap_map[20].rank == 1  # 20 total reviews vs 10 total reviews (tie-breaker)
    assert snap_map[10].rank == 2
    assert snap_map[30].rank is None

    # Cohort ranking: both eligible locs are <50 reviews -> "Emerging" cohort of size 2
    assert snap_map[20].cohort == "Emerging"
    assert snap_map[20].cohort_rank == 1
    assert snap_map[20].cohort_size == 2
    assert snap_map[10].cohort_rank == 2
    assert snap_map[30].cohort_rank is None  # ineligible
    
    # Check not-null constraint columns
    assert snap_map[10].period_start.date() == period_start
    assert snap_map[10].period_end.date() == period_end
    assert snap_map[10].most_improved_flag is False

def test_generate_snapshots_idempotency(db):
    from app.models.organization import Organization
    from app.models.location import Location
    
    org = Organization(id=1, name="Test Org")
    db.add(org)
    loc = Location(
        id=10, organization_id=1, google_location_id="loc_a", location_name="Loc A",
        average_rating=4.5, total_reviews=10, created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30),
        billing_status="active"
    )
    db.add(loc)
    db.commit()
    
    period_start = datetime.date(2026, 6, 1)
    period_end = datetime.date(2026, 6, 30)
    
    # Initial generation
    snaps1 = LeaderboardService.generate_snapshots_for_period(
        db, organization_id=1, period_label="2026-06",
        period_start=period_start, period_end=period_end
    )
    assert len(snaps1) == 1
    
    # Second generation with force=False -> no-op, returns empty
    snaps2 = LeaderboardService.generate_snapshots_for_period(
        db, organization_id=1, period_label="2026-06",
        period_start=period_start, period_end=period_end,
        force=False
    )
    assert len(snaps2) == 0
    
    # Third generation with force=True -> deletes and regenerates
    snaps3 = LeaderboardService.generate_snapshots_for_period(
        db, organization_id=1, period_label="2026-06",
        period_start=period_start, period_end=period_end,
        force=True
    )
    assert len(snaps3) == 1

def test_most_improved_and_streaks(db):
    from app.models.organization import Organization
    from app.models.location import Location
    from app.models.location_health_score import LocationHealthScore
    
    org = Organization(id=1, name="Test Org")
    db.add(org)
    
    old_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=100)
    # Loc A and Loc B
    loc_a = Location(
        id=10, organization_id=1, google_location_id="loc_a", location_name="Loc A",
        average_rating=4.0, total_reviews=10, created_at=old_date, billing_status="active"
    )
    loc_b = Location(
        id=20, organization_id=1, google_location_id="loc_b", location_name="Loc B",
        average_rating=4.5, total_reviews=10, created_at=old_date, billing_status="active"
    )
    db.add_all([loc_a, loc_b])
    db.commit()
    
    # Health scores
    db.add(LocationHealthScore(location_id=10, score=80, potential_score=100, label="Good", breakdown={}, recommendations=[], last_recalculated_reason="test"))
    db.add(LocationHealthScore(location_id=20, score=90, potential_score=100, label="Good", breakdown={}, recommendations=[], last_recalculated_reason="test"))
    db.commit()
    
    # --- Period 1 (2026-05) ---
    # Loc B (rank 1), Loc A (rank 2)
    snaps1 = LeaderboardService.generate_snapshots_for_period(
        db, organization_id=1, period_label="2026-05",
        period_start=datetime.date(2026, 5, 1), period_end=datetime.date(2026, 5, 31)
    )
    snap_map1 = {s.location_id: s for s in snaps1}
    assert snap_map1[20].rank == 1
    assert snap_map1[20].streak_count == 1
    assert snap_map1[10].rank == 2
    assert snap_map1[10].streak_count == 0
    assert snap_map1[10].most_improved_flag is False
    assert snap_map1[20].most_improved_flag is False
    
    # --- Period 2 (2026-06) ---
    # We swap health scores to swap ranks: Loc A gets 90, Loc B gets 80
    hs_a = db.query(LocationHealthScore).filter_by(location_id=10).first()
    hs_b = db.query(LocationHealthScore).filter_by(location_id=20).first()
    hs_a.score = 95
    hs_b.score = 70
    db.commit()
    
    snaps2 = LeaderboardService.generate_snapshots_for_period(
        db, organization_id=1, period_label="2026-06",
        period_start=datetime.date(2026, 6, 1), period_end=datetime.date(2026, 6, 30)
    )
    snap_map2 = {s.location_id: s for s in snaps2}
    
    # Loc A should now be rank 1
    assert snap_map2[10].rank == 1
    assert snap_map2[10].streak_count == 1  # newly rank 1
    assert snap_map2[10].previous_rank == 2
    assert snap_map2[10].rank_movement == 1
    
    # Loc B should now be rank 2
    assert snap_map2[20].rank == 2
    assert snap_map2[20].streak_count == 0  # streak broken
    assert snap_map2[20].previous_rank == 1
    assert snap_map2[20].rank_movement == -1
    
    # Loc A improved from 2 to 1. Loc B dropped from 1 to 2. Loc A is most improved.
    assert snap_map2[10].most_improved_flag is True
    assert snap_map2[20].most_improved_flag is False
    
    # --- Period 3 (2026-07) ---
    # Keep ranks the same, Loc A remains rank 1
    snaps3 = LeaderboardService.generate_snapshots_for_period(
        db, organization_id=1, period_label="2026-07",
        period_start=datetime.date(2026, 7, 1), period_end=datetime.date(2026, 7, 31)
    )
    snap_map3 = {s.location_id: s for s in snaps3}
    
    assert snap_map3[10].rank == 1
    assert snap_map3[10].streak_count == 2  # streak continues!
    assert snap_map3[20].rank == 2
    assert snap_map3[20].streak_count == 0

