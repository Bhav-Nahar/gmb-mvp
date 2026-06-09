from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class AddressModel(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None

class LocationModel(BaseModel):
    id: Optional[str] = None
    google_account_id: Optional[str] = None
    provider_location_id: str
    name: str
    category: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    business_hours: Optional[Any] = None
    provider: str
    provider_metadata: Dict[str, Any] = {}
    synced_at: datetime
    google_category_resource_name: Optional[str] = None
    
    # State tracking
    is_verified: Optional[bool] = None
    is_suspended: Optional[bool] = None
    is_duplicate: Optional[bool] = None
    
    # Extensions for task parity
    average_rating: Optional[float] = None
    total_reviews: Optional[int] = None

class ReviewModel(BaseModel):
    id: str
    location_id: str
    reviewer_name: str
    reviewer_profile_photo: Optional[str] = None
    rating: Optional[int] = None
    body: Optional[str] = None
    reply: Optional[str] = None
    reply_created_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    provider: str
    provider_metadata: Dict[str, Any] = {}

class ReviewReplyModel(BaseModel):
    review_id: str
    reply_text: str
    created_at: datetime
    provider: str

class PostModel(BaseModel):
    id: str
    location_id: str
    title: str
    body: str
    call_to_action: Optional[str] = None
    media_url: Optional[str] = None
    state: str
    published_at: Optional[datetime] = None
    provider: str
    provider_metadata: Dict[str, Any] = {}

from datetime import date

class DailyInsightMetric(BaseModel):
    date: date
    search_views: int = 0
    map_views: int = 0
    website_clicks: int = 0
    phone_calls: int = 0
    direction_requests: int = 0
    search_queries_direct: int = 0
    search_queries_indirect: int = 0
    search_queries_chain: int = 0

