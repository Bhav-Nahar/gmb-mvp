from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, computed_field
from app.core.config import settings

class MicrositeResponse(BaseModel):
    id: int
    location_id: int
    organization_id: int
    org_slug: str
    location_slug: str
    status: str  # "draft" | "published" | "unpublished"
    published_at: Optional[datetime] = None
    unpublished_at: Optional[datetime] = None
    view_count: int
    created_at: datetime
    updated_at: datetime

    @computed_field
    def public_url(self) -> str:
        # Single-level public URL, e.g. "https://pinzo.io/rupesh-jewellers-in-malad-mumbai"
        base = settings.FRONTEND_URL.rstrip('/')
        return f"{base}/{self.location_slug}"

    model_config = ConfigDict(from_attributes=True)
