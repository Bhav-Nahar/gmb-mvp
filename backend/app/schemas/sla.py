from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class LocationSLAMetrics(BaseModel):
    location_id: int
    sla_enabled: bool
    sla_tracking_started_at: Optional[datetime]
    total_replied: int
    avg_response_hours: Optional[float]
    best_response_hours: Optional[float]
    worst_response_hours: Optional[float]
    tier_best_count: int
    tier_good_count: int
    tier_average_count: int
    tier_poor_count: int
    avg_sla_tier: Optional[str]
    pending_count: int
    overdue_count: int

class LocationSLASummary(BaseModel):
    location_id: int
    location_name: str
    sla_enabled: bool
    sla_tracking_started_at: Optional[datetime]
    avg_response_hours: Optional[float]
    avg_sla_tier: Optional[str]
    total_replied: int
    overdue_count: int
    pending_count: int
