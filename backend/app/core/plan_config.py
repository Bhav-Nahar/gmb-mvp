# ---------------------------------------------------------------------------
# Single pricing model: flat per-location pricing per plan tier.
# There are no separate "starter / growth / enterprise" SKUs. A subscription is
# simply N locations at the plan's flat rate, and what you get scales with N.
# ---------------------------------------------------------------------------

# Flat per-location price (no volume bands — negotiated volume deals go through
# the admin custom per-location rate instead). All prices GST-INCLUSIVE.
LOCATION_PRICE = 199_900  # ₹1,999 / location

# Annual billing: pay 12 months upfront at the plan's discounted per-month rate.
# Each plan carries its own `annual_price` (≈20% off; Lite ≈25%) so the headline
# numbers stay round — there is no global discount multiplier anymore.
ANNUAL_MONTHS = 12
LOCATION_ANNUAL_PRICE = 159_900  # ₹1,599 / location / mo

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
# How long an onboarding sync may sit flagged in-progress before the gate treats it as
# dead. A crashed worker never clears sync_in_progress, and the customer was left on the
# "Building your audit" screen indefinitely with no retry.
ONBOARDING_SYNC_STALE_MINUTES = 15

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

# All stored prices are GST-INCLUSIVE: the listed price is exactly what is charged.
# GST_RATE is used to carve the tax component out of that total for invoices/quotes.
GST_RATE = 0.18

# ---------------------------------------------------------------------------
# Plan tiers. The `plan_tier` column on the organization selects one.
#   features: capability flags this tier unlocks (gated across the app).
#   limits:   numeric caps for this tier (None/absent = unlimited).
#   price / credits_per_location: how the tier charges / grants.
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
FEATURE_REVIEW_REQUESTS = "review_requests"  # ask customers for Google reviews over WhatsApp

# AEO: both Basic and Pro get one manual sync per location per calendar month.
# The tier differs by DEPTH (Basic covers Google AI surfaces only; Pro adds the
# third-party LLMs + brand share-of-voice) and by PROMPT COUNT per scan below.
AEO_SYNCS_PER_MONTH = 1

# AI-visibility prompts (queries) actually run per scan, keyed by scan depth:
# Basic ('google') 5, Pro ('full') 10. Keeps provider cost per scan bounded.
AEO_QUERIES_BY_DEPTH = {"google": 5, "full": 10}

# Limit keys (a tier's `limits` dict caps these; absent = unlimited).
LIMIT_MAX_LOCATIONS = "max_locations"
LIMIT_MAX_SEATS = "max_seats"
LIMIT_COMPETITORS = "max_competitors"  # tracked competitors per location
LIMIT_SEARCH_QUERIES = "search_query_limit"  # Search Intelligence rows shown
LIMIT_INSIGHTS_DAYS = "insights_days"        # how far back insights may look

# Full-tier feature sets (Basic/Pro keep everything they have today so they never regress).
_STANDARD_FEATURES = [FEATURE_SCHEDULER, FEATURE_TEAM, FEATURE_TEMPLATES, FEATURE_AUTO_REPLY,
                      FEATURE_LEADERBOARD, FEATURE_COMPARISON, FEATURE_GOOGLE_UPDATES]

PLANS = {
    "lite": {
        "name": "Lite",
        "price": 79_900,          # flat ₹799 / location, GST-incl.
        "annual_price": 59_900,   # ₹599/mo on annual (≈25% off)
        "credits_per_location": 10,
        "features": [],                    # none of the premium capabilities
        "limits": {
            # Unlimited locations: Lite is the cheap per-location wedge to undercut
            # RightChoice. Anti-cannibalization now rests entirely on the FEATURE gap
            # (no scheduler/auto-reply/AI-visibility/team) — the upsell to Basic.
            LIMIT_MAX_SEATS: 1,            # owner only (no team feature)
            LIMIT_SEARCH_QUERIES: 10,      # top 10 search-intelligence queries
            LIMIT_INSIGHTS_DAYS: 7,        # last 7 days of insights
        },
    },
    "basic": {
        "name": "Basic",
        "price": LOCATION_PRICE,                # flat ₹1,999 / location, GST-incl.
        "annual_price": LOCATION_ANNUAL_PRICE,  # ₹1,599/mo on annual
        "credits_per_location": CREDITS_PER_LOCATION,   # 30
        "features": _STANDARD_FEATURES + [FEATURE_AEO],
        "limits": {LIMIT_COMPETITORS: 3},
    },
    "pro": {
        "name": "Pro",
        "price": 299_900,          # flat ₹2,999 / location, GST-incl.
        "annual_price": 239_900,   # ₹2,399/mo on annual
        "credits_per_location": 45,
        # WhatsApp review requests are Pro-only: the tenant pays Meta directly for
        # the messages, so this is a reason to be on Pro rather than a cost to us.
        "features": _STANDARD_FEATURES + [FEATURE_LOCAL_RANK, FEATURE_MICROSITE, FEATURE_AEO,
                                          FEATURE_REVIEW_REQUESTS],
        "limits": {LIMIT_COMPETITORS: 10},
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


def aeo_queries_cap(plan_tier: str | None) -> int:
    """Prompts per AI-visibility scan for a plan (0 if the plan has no AEO)."""
    depth = aeo_tier_for_plan(plan_tier)
    return AEO_QUERIES_BY_DEPTH.get(depth, 0) if depth else 0


def price_with_gst(price_paise: int) -> dict:
    """base / gst / total (paise) for a GST-INCLUSIVE listed price: the total charged
    IS the listed price; base and gst are the carve-out for invoices/quotes."""
    base = round(price_paise / (1 + GST_RATE))
    return {"base_paise": base, "gst_paise": price_paise - base, "total_paise": price_paise}


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
