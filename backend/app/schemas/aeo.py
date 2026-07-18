from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from app.schemas.base import ORMBase


class AEOQueriesOut(BaseModel):
    """What a scan will run: auto-generated (category+city) queries the user can't
    edit, plus the Owner/Admin's custom additions. `auto_enabled` False => only the
    custom queries run."""
    auto: list[str]
    custom: list[str]
    auto_enabled: bool
    max_custom: int


class AEOQueriesUpdate(BaseModel):
    custom: list[str] = Field(default_factory=list)
    auto_enabled: bool = True


class AEOScanOut(ORMBase):
    id: int
    location_id: int
    tier: str
    status: str
    ai_visibility_score: Optional[int] = None
    score_delta: Optional[int] = None
    queries_tracked: int
    result: dict[str, Any] = {}
    error: Optional[str] = None
    created_at: datetime


class AEOScanSummaryOut(ORMBase):
    """History list — omits the (large) result blob."""
    id: int
    tier: str
    status: str
    ai_visibility_score: Optional[int] = None
    score_delta: Optional[int] = None
    queries_tracked: int
    error: Optional[str] = None
    created_at: datetime


class AEOQuotaOut(BaseModel):
    """Drives the Run-sync button: how many syncs are left this month, when the
    allowance refills, and whether the org is still on trial (AEO is locked
    until the subscription is activated)."""
    per_month: int
    used_this_month: bool
    tier: Optional[str] = None          # "google" | "full" | None (plan lacks AEO)
    in_trial: bool = False              # True => blocked until subscription activates
    resets_on: datetime
