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
    provider_location_id: str
    name: str
    category: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    provider: str
    provider_metadata: Dict[str, Any] = {}
    synced_at: datetime
    
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
