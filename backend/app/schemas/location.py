from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.schemas.base import ORMBase

class LocationSyncStatus(ORMBase):
    location_id: int
    status: str          # "Success", "Failed", "Pending"
    last_synced_at: Optional[datetime] = None
    error_message: Optional[str] = None
    run_type: str         # "Scheduled" or "Manual"

class HealthScoreBreakdown(BaseModel):
    score: int
    max_score: int
    # One-line "why this score" explanation (HEALTH_V2).
    detail: Optional[str] = None

class DescriptionBreakdown(BaseModel):
    score: int
    max_score: int
    status: str
    char_count: int
    hard_flags: list[str] = []
    soft_flags: list[str] = []

class HealthScoreBreakdowns(BaseModel):
    profile_completeness: HealthScoreBreakdown
    reviews_rating: HealthScoreBreakdown
    response_rate: HealthScoreBreakdown
    post_activity: HealthScoreBreakdown
    photos_media: HealthScoreBreakdown
    # Optional so older cached scores (pre-enrichment) still serialize.
    description: Optional[DescriptionBreakdown] = None
    # Radar-only dimensions (HEALTH_V2) — present only when the location has data.
    ranking: Optional[HealthScoreBreakdown] = None
    traffic: Optional[HealthScoreBreakdown] = None
    sentiment: Optional[HealthScoreBreakdown] = None
    website: Optional[HealthScoreBreakdown] = None

class HealthScoreRecommendation(BaseModel):
    title: str
    description: str
    potential_gain: int
    target_tab: str

class LocationHealthScoreOut(ORMBase):
    location_id: int
    score: int
    potential_score: int
    label: str
    breakdown: HealthScoreBreakdowns
    recommendations: list[HealthScoreRecommendation]
    last_recalculated_reason: str
    calculated_at: datetime

class OrganizationHealthSummaryOut(BaseModel):
    average_score: int
    total_locations: int
    excellent_count: int
    good_count: int
    average_count: int
    poor_count: int
    critical_count: int
    # Locations in the org that don't yet have a calculated health score. These
    # are counted in total_locations but excluded from average_score.
    not_calculated_count: int = 0
    # Avg per-dimension strength across scored locations, as {breakdown_key: pct 0-100}.
    dimension_averages: dict[str, int] = {}
