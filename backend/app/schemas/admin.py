from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OrgUpdate(BaseModel):
    """Super-admin edits to an organization's plan/billing state.

    All fields optional — only the ones provided are applied. `reason` is recorded
    in the audit trail alongside the before/after values.
    """
    plan_tier: Optional[str] = None
    subscription_status: Optional[str] = None
    location_quota: Optional[int] = Field(default=None, ge=0)
    monthly_ai_credits_balance: Optional[int] = Field(default=None, ge=0)
    topup_ai_credits_balance: Optional[int] = Field(default=None, ge=0)
    trial_ends_at: Optional[datetime] = None
    grace_period_ends_at: Optional[datetime] = None
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


class AdminActionBody(BaseModel):
    """Optional body carrying an audit reason for action endpoints (sync/reset)."""
    reason: Optional[str] = None
