from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date, datetime

class InsightsMetricDelta(BaseModel):
    current: float
    prior: float
    percentage_change: Optional[float] = None  # None if division by zero

class OverviewKPIs(BaseModel):
    profile_views: InsightsMetricDelta
    search_impressions: InsightsMetricDelta
    maps_views: InsightsMetricDelta
    phone_calls: InsightsMetricDelta
    website_clicks: InsightsMetricDelta
    direction_requests: InsightsMetricDelta

class DailyMetricPoint(BaseModel):
    date: date
    profile_views: int
    search_impressions: int
    maps_views: int
    phone_calls: int
    website_clicks: int
    direction_requests: int
    searches_direct: int
    searches_indirect: int
    searches_chain: int
    reviews_received: int
    avg_rating: Optional[float] = None

class LeaderboardLocation(BaseModel):
    location_id: int
    location_name: str
    profile_views: int
    search_impressions: int
    reviews_count: int
    avg_rating: Optional[float] = None

class InsightsOverviewResponse(BaseModel):
    kpis: OverviewKPIs
    trends: List[DailyMetricPoint]
    leaderboard: List[LeaderboardLocation]
    attention_locations_count: int

class IssueCategorySummary(BaseModel):
    category: str
    count: int

class SentimentBreakdown(BaseModel):
    positive: int
    neutral: int
    negative: int
    positive_percentage: float
    neutral_percentage: float
    negative_percentage: float

class SLAMetricsSummary(BaseModel):
    total_reviews: int
    replied_reviews: int
    response_rate: float
    avg_response_time_hours: Optional[float] = None

class LocationInsightsResponse(BaseModel):
    location_id: int
    location_name: str
    attention_needed: bool
    attention_reason: Optional[str] = None
    last_insights_sync_at: Optional[datetime] = None
    kpis: OverviewKPIs
    trends: List[DailyMetricPoint]
    sentiment: SentimentBreakdown
    sla: SLAMetricsSummary
    top_issue_categories: List[IssueCategorySummary]

class InsightsSyncPostResponse(BaseModel):
    task_id: str
    status: str
