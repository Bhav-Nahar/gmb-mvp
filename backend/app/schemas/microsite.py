from typing import Optional
from datetime import datetime
from pydantic import computed_field
from app.core.config import settings
from app.schemas.base import ORMBase

class MicrositeResponse(ORMBase):
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
