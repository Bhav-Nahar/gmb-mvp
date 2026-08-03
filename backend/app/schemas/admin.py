from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class OrgUpdate(BaseModel):
    """Super-admin edits to an organization's plan/billing state.

    All fields optional — only the ones provided are applied. `reason` is recorded
    in the audit trail alongside the before/after values.
    """
    # Unlocks the white-label branding settings for this org's report exports.
    is_agency: Optional[bool] = None
    # Forgive the one-trial-per-Google-account/phone guard for this org (wrong-account signup).
    allow_extra_trial: Optional[bool] = None
    plan_tier: Optional[str] = None
    subscription_status: Optional[str] = None
    location_quota: Optional[int] = Field(default=None, ge=0)
    monthly_ai_credits_balance: Optional[int] = Field(default=None, ge=0)
    topup_ai_credits_balance: Optional[int] = Field(default=None, ge=0)
    trial_ends_at: Optional[datetime] = None
    grace_period_ends_at: Optional[datetime] = None
    # Enterprise custom pricing: negotiated per-location MONTHLY rate PER TIER, in paise
    # — {"basic": 79900}. Replaces the map wholesale (the panel sends every tier), so a
    # tier omitted here bills standard price. Tiers absent = standard, which is what keeps
    # a Basic-rate deal from discounting Pro. {} clears all per-tier rates.
    custom_prices: Optional[Dict[str, int]] = None
    custom_credits_per_location: Optional[int] = Field(default=None, ge=0)
    # Set true to REMOVE custom pricing (back to standard tiers) — the fields above can't
    # express "clear" via null, since null means "leave unchanged".
    clear_custom_pricing: bool = False
    reason: Optional[str] = None


class AdminUserUpdate(BaseModel):
    """Super-admin edits to a single user (cross-org)."""
    role: Optional[str] = None
    is_active: Optional[bool] = None
    force_logout: bool = False  # bump token_version to invalidate active sessions
    reason: Optional[str] = None


class LocationUpdate(BaseModel):
    """Super-admin edit to a single location's billing gate (cross-org)."""
    billing_status: str  # 'active' | 'pending_payment'
    reason: Optional[str] = None


class FlagsUpdate(BaseModel):
    """Global runtime feature-flag overrides (stored in app_settings). Send only the
    flag(s) being changed; omitted flags keep their current value."""
    india_phone_trial: Optional[bool] = None
    row_phone_trial: Optional[bool] = None
    reason: Optional[str] = None


class AdminActionBody(BaseModel):
    """Optional body carrying an audit reason for action endpoints (sync/reset)."""
    reason: Optional[str] = None
