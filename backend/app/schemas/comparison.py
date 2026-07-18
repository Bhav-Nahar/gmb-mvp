from pydantic import BaseModel
from typing import Optional
from datetime import date

# Refined Response Models for frontend integration
class ComparisonSummary(BaseModel):
    profile_views: int = 0
    search_impressions: int = 0
    website_clicks: int = 0
    phone_calls: int = 0
    direction_requests: int = 0
    avg_rating: Optional[float] = None
    response_rate: float = 0.0

class ComparisonTrendDataPoint(BaseModel):
    date: date
    views: int = 0

class ComparisonLeaderboardItemRefined(BaseModel):
    name: str
    score: float

class ComparisonGroupItem(BaseModel):
    id: str
    name: str
