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

# AI credit top-up packs (one-time). Key is what the client sends; price/credits
# are owned by the server so the client cannot manipulate them.
AI_TOPUP_PACKS = {
    "small": {"credits": 500, "price_paise": 49_900},
    "large": {"credits": 2_000, "price_paise": 179_900},
}

PLATFORM_AI_ACTIONS = {
    "sentiment_tagging",
}

USER_AI_ACTIONS = {
    "generate_review_reply",
    "generate_google_post",
}
