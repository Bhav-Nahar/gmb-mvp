from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class LocationSyncStatus(BaseModel):
    location_id: int
    status: str          # "Success", "Failed", "Pending"
    last_synced_at: Optional[datetime] = None
    error_message: Optional[str] = None
    run_type: str         # "Scheduled" or "Manual"

    class Config:
        from_attributes = True

class HealthScoreBreakdown(BaseModel):
    score: int
    max_score: int

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

class HealthScoreRecommendation(BaseModel):
    title: str
    description: str
    potential_gain: int
    target_tab: str

class LocationHealthScoreOut(BaseModel):
    location_id: int
    score: int
    potential_score: int
    label: str
    breakdown: HealthScoreBreakdowns
    recommendations: list[HealthScoreRecommendation]
    last_recalculated_reason: str
    calculated_at: datetime

    class Config:
        from_attributes = True

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
