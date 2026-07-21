# ---------------------------------------------------------------------------
# Single pricing model: per-location, graduated (volume) tiers.
# There are no separate "starter / growth / enterprise" SKUs. A subscription is
# simply N locations, priced per the bands below, and what you get scales with N.
# ---------------------------------------------------------------------------

# Graduated price bands. Each tuple is (upper_bound_inclusive, price_paise_per_location).
# The last band uses None as an open-ended upper bound.
#   locations  1-10  -> ₹2,500 each
#   locations 11-25  -> ₹2,000 each
#   locations  26+   -> ₹1,500 each
LOCATION_PRICE_TIERS = [
    (10, 250_000),
    (25, 200_000),
    (None, 150_000),
]

# Annual billing: pay for 12 months at a 20% discount.
ANNUAL_MONTHS = 12
ANNUAL_DISCOUNT = 0.20

# Entitlements that scale with the number of locations purchased.
CREDITS_PER_LOCATION = 30

# Bounds for a single subscription.
MIN_LOCATIONS = 1
MAX_LOCATIONS = 500

# Trial defaults (used before any subscription is active). Kept in sync with the
# organizations.location_quota / monthly_ai_credits_balance column defaults, which
# are what actually grant the trial entitlement at signup.
TRIAL_LOCATION_QUOTA = 3
TRIAL_AI_CREDITS = 10

# The trial clock (trial_ends_at) only starts on the first successful location sync,
# so an org that signs up but never connects Google would stay an unexpiring trial
# forever. Cap that: a trial still pending (trial_ends_at NULL) this many days after
# signup is treated as expired.
PENDING_TRIAL_MAX_DAYS = 14

# Length of the free trial, in days. In the legacy frictionless flow the clock starts
# on first sync; in the card-required flow it starts when the payment mandate is set up
# and the first real debit is scheduled for TRIAL_DAYS later.
TRIAL_DAYS = 7

# Owners can reassign WHICH locations fill their paid slots for free, but only this
# often. Without a limit, an org could cycle its active locations daily and farm
# per-location value (syncs, posts, profile management) for far more locations than it
# pays for. 30 days = "about once a month", which fits genuine reorganisation while
# killing the daily-swap loophole. Re-saving the SAME selection is a no-op (no cooldown).
LOCATION_REASSIGN_COOLDOWN_DAYS = 30

# When a super-admin deletes an account (org or user), it's a SOFT delete: access is cut
# off immediately but the data is kept this many days so it can be restored. After that a
# daily task hard-purges it (cascade). "Bring it back within 14 days, else gone."
ACCOUNT_PURGE_GRACE_DAYS = 14

# AI credit top-up packs (one-time). Key is what the client sends; price/credits
# are owned by the server so the client cannot manipulate them.
AI_TOPUP_PACKS = {
    "small": {"credits": 500, "price_paise": 49_900},
    "large": {"credits": 2_000, "price_paise": 179_900},
}

# GST added on top of every price. Change the rate here and it applies everywhere
# prices are quoted/charged (all stored prices are GST-exclusive base amounts).
GST_RATE = 0.18

# ---------------------------------------------------------------------------
# Plan tiers. The `plan_tier` column on the organization selects one.
#   features: capability flags this tier unlocks (gated across the app).
#   limits:   numeric caps for this tier (None/absent = unlimited).
#   price_tiers / credits_per_location: how the tier charges / grants.
# NOTE: kept separate from the `plan` column, which remains the trial/active
# billing-STATE flag — `plan_tier` is the product TIER, so neither overloads the other.
# ---------------------------------------------------------------------------
# Capability flags (a tier's `features` list unlocks these).
FEATURE_SCHEDULER = "scheduler"        # scheduling posts for the future (else post-now only)
FEATURE_TEAM = "team"                  # inviting team members / RBAC beyond the owner
FEATURE_TEMPLATES = "reply_templates"  # saved reply templates
FEATURE_AUTO_REPLY = "auto_reply"      # automated review replies + their email notifications
FEATURE_LEADERBOARD = "leaderboard"    # monthly leaderboard / rankings
FEATURE_COMPARISON = "comparison"      # competitor / location comparison
FEATURE_LOCAL_RANK = "local_rank"      # geo-grid rank scans
FEATURE_MICROSITE = "microsite"        # published microsite
FEATURE_AEO = "aeo"                    # AI-search visibility (AEO) scans
FEATURE_GOOGLE_UPDATES = "google_updates"  # detect + accept/reject Google's own edits

# AEO: both Basic and Pro get one manual sync per location per calendar month.
# The tier differs by DEPTH, not count — Basic covers Google AI surfaces only;
# Pro adds the third-party LLMs + brand share-of-voice.
AEO_SYNCS_PER_MONTH = 1

# Limit keys (a tier's `limits` dict caps these; absent = unlimited).
LIMIT_MAX_LOCATIONS = "max_locations"
LIMIT_MAX_SEATS = "max_seats"
LIMIT_SEARCH_QUERIES = "search_query_limit"  # Search Intelligence rows shown
LIMIT_INSIGHTS_DAYS = "insights_days"        # how far back insights may look

# Full-tier feature sets (Basic/Pro keep everything they have today so they never regress).
_STANDARD_FEATURES = [FEATURE_SCHEDULER, FEATURE_TEAM, FEATURE_TEMPLATES, FEATURE_AUTO_REPLY,
                      FEATURE_LEADERBOARD, FEATURE_COMPARISON, FEATURE_GOOGLE_UPDATES]

PLANS = {
    "lite": {
        "name": "Lite",
        "price_tiers": [(None, 99_900)],   # flat ₹999 / location
        "credits_per_location": 10,
        "features": [],                    # none of the premium capabilities
        "limits": {
            LIMIT_MAX_LOCATIONS: 1,        # single-location small business (anti-cannibalization)
            LIMIT_MAX_SEATS: 1,            # owner only
            LIMIT_SEARCH_QUERIES: 10,      # top 10 search-intelligence queries
            LIMIT_INSIGHTS_DAYS: 7,        # last 7 days of insights
        },
    },
    "basic": {
        "name": "Basic",
        "price_tiers": LOCATION_PRICE_TIERS,            # current graduated pricing
        "credits_per_location": CREDITS_PER_LOCATION,   # 30
        "features": _STANDARD_FEATURES + [FEATURE_AEO],
        "limits": {},
    },
    "pro": {
        "name": "Pro",
        "price_tiers": [(10, 300_000), (25, 250_000), (None, 200_000)],  # ~₹500/loc more
        "credits_per_location": 45,
        "features": _STANDARD_FEATURES + [FEATURE_LOCAL_RANK, FEATURE_MICROSITE, FEATURE_AEO],
        "limits": {},
    },
}
DEFAULT_PLAN_TIER = "basic"


def get_plan(plan_tier: str | None) -> dict:
    return PLANS.get(plan_tier or DEFAULT_PLAN_TIER, PLANS[DEFAULT_PLAN_TIER])


def plan_has_feature(plan_tier: str | None, feature: str) -> bool:
    return feature in get_plan(plan_tier).get("features", [])


def plan_limit(plan_tier: str | None, key: str, default=None):
    """Numeric cap for a tier (None/absent = unlimited)."""
    return get_plan(plan_tier).get("limits", {}).get(key, default)


def aeo_tier_for_plan(plan_tier: str | None) -> str | None:
    """AEO scan depth for a plan: 'full' on Pro, 'google' on any other tier that
    has the feature, None if the tier doesn't include AEO at all (e.g. Lite)."""
    if not plan_has_feature(plan_tier, FEATURE_AEO):
        return None
    return "full" if plan_tier == "pro" else "google"


def price_with_gst(price_paise: int) -> dict:
    """base / gst / total (paise) for a price, applying GST_RATE."""
    gst = round(price_paise * GST_RATE)
    return {"base_paise": price_paise, "gst_paise": gst, "total_paise": price_paise + gst}


PLATFORM_AI_ACTIONS = {
    "sentiment_tagging",
}

USER_AI_ACTIONS = {
    "generate_review_reply",
    "generate_google_post",
    "generate_business_description",     # first description for a location: 5 credits
    "regenerate_business_description",   # subsequent regenerations: 2 credits
    "run_local_grid_scan",               # geo-grid local rank scan: 1–6 credits by grid size
}
