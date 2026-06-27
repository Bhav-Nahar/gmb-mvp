from pydantic import BaseModel, Field
from app.schemas.base import ORMBase
from typing import Optional
from datetime import datetime

class ReplyTemplateCreate(BaseModel):
    star_rating: int = Field(..., ge=1, le=5)
    title: str = Field(..., min_length=1, max_length=100)
    # Capped below the 4000-char reply limit to leave headroom for variable
    # expansion ({{reviewer_name}}/{{location_name}}) at reply time.
    body: str = Field(..., min_length=1, max_length=3500)
    display_order: int = Field(default=0, ge=0)

class ReplyTemplateUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    body: Optional[str] = Field(None, min_length=1, max_length=3500)
    display_order: Optional[int] = Field(None, ge=0)

class ReplyTemplateResponse(ORMBase):
    id: int
    organization_id: int
    star_rating: int
    title: str
    body: str
    display_order: int
    created_by_user_id: Optional[int]
    usage_count: int
    created_at: datetime
    updated_at: datetime
