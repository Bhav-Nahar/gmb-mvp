LEADERBOARD_SCORING_VERSION = "v2"
# Bump this string whenever weights/caps change meaningfully. Snapshots store the
# version active at calculation time (see snapshot_version column) so historical
# ranks remain explainable even after the formula changes.

# NOTE: Health score already includes review response rate (up to 10 points of the
# total health score). To avoid overweighting response behavior, the response_rate
# weight is set to 10% and health_score to 30%. Re-evaluate after 60-90 days of
# production data.
LEADERBOARD_METRIC_WEIGHTS = {
    "average_rating": 0.30,
    "health_score": 0.25,
    "review_volume": 0.15,
    "review_velocity": 0.15,
    "engagement_growth": 0.15,
}

ENGAGEMENT_GROWTH_CAP_PERCENT = 50
ENGAGEMENT_GROWTH_FLOOR_PERCENT = -100
# Growth % is clamped to [floor, cap] before normalization. -100% -> score 0,
# +50% (the cap) -> score 100, linear between.

REVIEW_VOLUME_LOG_CAP = 500
# Review counts are log-scaled, not linear (the jump from 5 to 50 reviews matters far
# more than 500 to 545). Locations at or above this count receive the max volume score
# of 100. Formula: score = min(log(total_reviews + 1) / log(REVIEW_VOLUME_LOG_CAP + 1), 1.0) * 100

REVIEW_VELOCITY_CAP = 30
# V1 assumption: ~30 reviews/month is considered maximum velocity.
# Used for Monthly Review Velocity score normalization.

MIN_REVIEWS_FOR_ELIGIBILITY = 3
MIN_DAYS_SYNCED_FOR_ELIGIBILITY = 14
# Locations below these thresholds are excluded from ranking.
# NOTE: these are deliberately low starting thresholds tuned for small-to-mid franchise
# chains (5-50 locations). Large chains (500+ locations) may need to raise these quickly
# after seeing real data, to avoid a fluke 3-review location ranking artificially high.

LEADERBOARD_SNAPSHOT_PERIOD = "monthly"
# Reserved for future weekly support. Keep as a string constant.

# Startup validations
assert abs(sum(LEADERBOARD_METRIC_WEIGHTS.values()) - 1.0) < 0.001, "Weights must sum to 1.0"
assert ENGAGEMENT_GROWTH_CAP_PERCENT > 0, "Growth cap must be positive"
assert REVIEW_VOLUME_LOG_CAP > 0, "Review volume log cap must be positive"
