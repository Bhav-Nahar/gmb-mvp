from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

# Categories accepted by the GBP Media API's locationAssociation.category.
GBP_PHOTO_CATEGORIES = {
    "LOGO", "COVER", "PROFILE", "EXTERIOR", "INTERIOR", "PRODUCT",
    "AT_WORK", "FOOD_AND_DRINK", "MENU", "COMMON_AREA", "ROOMS",
    "TEAMS", "ADDITIONAL",
}


class LocationMediaCreate(BaseModel):
    # The already-uploaded asset (from POST /media/upload) to publish to the gallery.
    source_media_id: int
    category: str = "ADDITIONAL"

    @field_validator("category")
    @classmethod
    def _valid_category(cls, v: str) -> str:
        v = (v or "").upper()
        if v not in GBP_PHOTO_CATEGORIES:
            raise ValueError(
                f"Invalid category '{v}'. Allowed: {', '.join(sorted(GBP_PHOTO_CATEGORIES))}"
            )
        return v


class LocationMediaResponse(BaseModel):
    id: int
    location_id: int
    organization_id: int
    source_media_id: Optional[int]
    gbp_category: str
    media_format: str
    gbp_resource_name: Optional[str]
    media_key: Optional[str]
    source_url: str
    thumbnail_url: Optional[str]
    publish_status: str
    failure_reason: Optional[str]
    google_error_code: Optional[str]
    publish_attempts: int
    is_deleted: bool
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
