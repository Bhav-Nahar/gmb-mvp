LEADERBOARD_SCORING_VERSION = "v6"
# Bump this string whenever weights/caps change meaningfully. Snapshots store the
# version active at calculation time (see snapshot_version column) so historical
# ranks remain explainable even after the formula changes.

LEADERBOARD_METRIC_WEIGHTS = {
    "average_rating": 0.30,
    "health_score": 0.25,
    "review_volume": 0.15,
    "review_velocity": 0.15,
    "response_rate": 0.15,
}
# engagement_growth (calls + website clicks + direction requests) was dropped in v5: it is
# driven by external demand/seasonality, not operator action, and is too noisy month-to-month
# to rank on. The snapshot columns are kept (nullable, unpopulated) to avoid a destructive
# migration. Every weighted metric here maps to a controllable action.

REVIEW_VOLUME_LOG_CAP = 500
# Review counts are log-scaled, not linear (the jump from 5 to 50 reviews matters far
# more than 500 to 545). Locations at or above this count receive the max volume score
# of 100. Formula: score = min(log(total_reviews + 1) / log(REVIEW_VOLUME_LOG_CAP + 1), 1.0) * 100

REVIEW_VELOCITY_CAP = 41
# P90 value derived from normalized database review counts.
# Used for Monthly Review Velocity score normalization (square-root diminishing returns curve).

MIN_REVIEWS_FOR_ELIGIBILITY = 3
MIN_DAYS_SYNCED_FOR_ELIGIBILITY = 14
# Locations below these thresholds are excluded from ranking.
# NOTE: these are deliberately low starting thresholds tuned for small-to-mid franchise
# chains (5-50 locations). Large chains (500+ locations) may need to raise these quickly
# after seeing real data, to avoid a fluke 3-review location ranking artificially high.

LEADERBOARD_SNAPSHOT_PERIOD = "monthly"
# Reserved for future weekly support. Keep as a string constant.

# Cohort ranking: locations are ranked within review-volume bands so a fluke 3-review
# location isn't ranked against a 5,000-review one. Global rank is kept too; cohort_rank
# is the fair within-peer-group position. (min_reviews_inclusive, label), descending.
COHORT_VOLUME_BANDS = [
    (1000, "Flagship"),
    (200, "Established"),
    (50, "Growing"),
    (0, "Emerging"),
]

# Startup validations
assert abs(sum(LEADERBOARD_METRIC_WEIGHTS.values()) - 1.0) < 0.001, "Weights must sum to 1.0"
assert REVIEW_VOLUME_LOG_CAP > 0, "Review volume log cap must be positive"
assert COHORT_VOLUME_BANDS[-1][0] == 0, "Lowest cohort band must start at 0 to catch all"
assert COHORT_VOLUME_BANDS == sorted(COHORT_VOLUME_BANDS, reverse=True), "Bands must be descending"
