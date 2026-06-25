from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class PublicReviewSchema(BaseModel):
    reviewer_name: str
    reviewer_profile_photo: Optional[str] = None
    rating: Optional[int] = None
    comment: Optional[str] = None
    review_created_at: datetime
    reply_text: Optional[str] = None
    reply_created_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class PublicMicrositeSchema(BaseModel):
    # Core identifying fields
    location_name: str
    primary_category: Optional[str] = None
    average_rating: Optional[float] = None
    total_reviews: Optional[int] = None
    description: Optional[str] = None
    
    # Contact info
    logo: Optional[str] = None  # Brand logo (GBP LOGO/PROFILE photo) for header + JSON-LD
    cover: Optional[str] = None  # Hero background image (GBP COVER/EXTERIOR/INTERIOR/first photo)
    address: Optional[str] = None
    city: Optional[str] = None  # Needed for title/description metadata + breadcrumbs
    state: Optional[str] = None  # For breadcrumb hierarchy (Home > State > City > Business)
    phone: Optional[str] = None
    # Social/contact links sourced from GBP URL attributes; [] if the business set none.
    social_links: List[Dict[str, str]] = []
    website: Optional[str] = None
    business_hours: Optional[Dict[str, Any]] = None
    latlng: Optional[Dict[str, Any]] = None
    maps_url: Optional[str] = None    # GBP canonical maps link (exact business pin)
    review_url: Optional[str] = None  # GBP "write a review" deep link
    
    # Rich fields
    service_items: List[Any] = []
    photos: List[str] = []
    reviews: List[PublicReviewSchema] = []
    
    # Status to confirm routing
    status: str

    model_config = ConfigDict(from_attributes=True)
