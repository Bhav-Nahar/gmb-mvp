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
    click_through_rate: Optional[float] = None
    call_conversion_rate: Optional[float] = None
    direction_conversion_rate: Optional[float] = None
    avg_sentiment_score: Optional[float] = None

class LeaderboardLocation(BaseModel):
    location_id: int
    location_name: str
    profile_views: int
    search_impressions: int
    reviews_count: int
    avg_rating: Optional[float] = None

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
    avg_sentiment_score: Optional[float] = None  # -1.0 (all negative) .. 1.0 (all positive)

class SLAMetricsSummary(BaseModel):
    total_reviews: int
    replied_reviews: int
    response_rate: float
    avg_response_time_hours: Optional[float] = None

class InsightsOverviewResponse(BaseModel):
    kpis: OverviewKPIs
    trends: List[DailyMetricPoint]
    leaderboard: List[LeaderboardLocation]
    attention_locations_count: int
    # Organization-wide reputation aggregates (across all accessible locations).
    sentiment: Optional[SentimentBreakdown] = None
    sla: Optional[SLAMetricsSummary] = None
    top_issue_categories: List[IssueCategorySummary] = Field(default_factory=list)

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

class SearchKeywordMetric(BaseModel):
    keyword: str
    impressions: int
    impressions_prior: int = 0
    mom_growth: Optional[float] = None  # None when prior is 0 (no baseline)
    is_brand_term: bool = False

class KeywordMetricsResponse(BaseModel):
    items: List[SearchKeywordMetric]
    total: int
    page: int
    page_size: int
    
class BrandTermResponse(BaseModel):
    id: int
    term: str
    created_at: datetime

class BrandTermCreate(BaseModel):
    term: str


class KeywordKpis(BaseModel):
    total_impressions: int
    total_impressions_prior: int
    impressions_mom: Optional[float] = None
    keywords_tracked: int
    branded_impressions: int
    branded_pct: float
    non_branded_impressions: int
    non_branded_pct: float


class KeywordTrendPoint(BaseModel):
    month: date
    branded: int
    non_branded: int
    total: int


class KeywordLocationComparison(BaseModel):
    location_id: int
    location_name: str
    impressions: int
    mom_growth: Optional[float] = None


class KeywordSummaryResponse(BaseModel):
    kpis: KeywordKpis
    trends: List[KeywordTrendPoint]
    location_comparison: List[KeywordLocationComparison]
