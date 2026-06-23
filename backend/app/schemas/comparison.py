from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any
from datetime import date
from enum import Enum

class GroupByType(str, Enum):
    CITY = "city"
    STATE = "state"
    REGION = "region"
    CUSTOM = "custom"

class BaseComparisonRequest(BaseModel):
    group_by: GroupByType
    start_date: date
    end_date: date
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
    sort_by: Optional[str] = None
    sort_order: Optional[str] = "desc" # asc or desc
    
    # Optional filters
    location_ids: Optional[List[int]] = None
    region_ids: Optional[List[int]] = None
    custom_group_ids: Optional[List[int]] = None
    cities: Optional[List[str]] = None  # Added for Compare Mode
    states: Optional[List[str]] = None  # Added for Compare Mode

class ComparisonSummaryRequest(BaseComparisonRequest):
    pass

class ComparisonSummaryItem(BaseModel):
    group_name: str
    group_id: Optional[str] = None # String to support both int IDs and string names (City/State)
    locations_count: int
    
    # Metrics
    profile_views: int = 0
    search_impressions: int = 0
    maps_views: int = 0
    phone_calls: int = 0
    website_clicks: int = 0
    direction_requests: int = 0
    reviews_received: int = 0
    avg_rating: Optional[float] = None
    avg_rank: Optional[float] = None
    solv: Optional[float] = None
    
    # Benchmark averages
    state_avg_calls: Optional[float] = None
    state_avg_website_clicks: Optional[float] = None
    state_avg_direction_requests: Optional[float] = None
    national_avg_calls: Optional[float] = None
    national_avg_website_clicks: Optional[float] = None
    national_avg_direction_requests: Optional[float] = None

class ComparisonSummaryResponse(BaseModel):
    data: List[ComparisonSummaryItem]
    total_count: int

class ComparisonTrendRequest(BaseComparisonRequest):
    metrics: List[str] # e.g., ["phone_calls", "website_clicks"]

class TrendDataPoint(BaseModel):
    date: date
    metrics: dict[str, Any]

class ComparisonTrendItem(BaseModel):
    group_name: str
    group_id: Optional[str] = None
    trends: List[TrendDataPoint]

class ComparisonTrendResponse(BaseModel):
    data: List[ComparisonTrendItem]

class ComparisonLeaderboardRequest(BaseComparisonRequest):
    metric: str # e.g., "phone_calls" or "solv"

class ComparisonLeaderboardItem(BaseModel):
    rank: int
    group_name: str
    group_id: Optional[str] = None
    score: float
    locations_count: int
    
    # Contextual Benchmark Data
    state_average_score: Optional[float] = None
    national_average_score: Optional[float] = None

class ComparisonLeaderboardResponse(BaseModel):
    data: List[ComparisonLeaderboardItem]

# Export request is similar but needs format
class ComparisonExportFormat(str, Enum):
    CSV = "csv"
    XLSX = "xlsx"

class ComparisonExportRequest(BaseComparisonRequest):
    format: ComparisonExportFormat
    selected_metrics: List[str]

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

