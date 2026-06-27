from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.base import ORMBase

from app.schemas.reply_template import ReplyTemplateResponse

class ReviewResponse(ORMBase):
    id: int
    organization_id: int
    location_id: int
    provider: str
    provider_review_id: str
    reviewer_name: str
    reviewer_profile_photo: Optional[str] = None
    rating: Optional[int] = None
    comment: Optional[str] = None
    is_replied: bool
    reply_text: Optional[str] = None
    reply_created_at: Optional[datetime] = None
    review_created_at: datetime
    review_updated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    is_deleted: bool
    deleted_at: Optional[datetime] = None
    sentiment: Optional[str] = None
    issue_category: Optional[str] = None
    sentiment_tagged_at: Optional[datetime] = None
    location_name: str
    suggested_templates: List[ReplyTemplateResponse] = []

class ReviewListResponse(BaseModel):
    reviews: List[ReviewResponse]
    total: int
    page: int
    pages: int

class ReviewReplyRequest(BaseModel):
    reply_text: str = Field(..., min_length=1, max_length=4000)
    template_id: Optional[int] = None

class GenerateReplyResponse(BaseModel):
    review_id: int
    generated_reply: str  # = recommended variant, kept for back-compat
    recommended_reply: str
    short_reply: str
    warm_or_professional_reply: str
    topics: List[str] = []
    tone: str
    manual_review_required: bool = False
    risk_level: str = "low"
