from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime

class LocationEditCreate(BaseModel):
    field_name: str
    new_value: Any  # Accepts string or dict/list for complex fields like business_hours
    warning_acknowledged: bool = False

class LocationEditSubmitRequest(BaseModel):
    version: int = Field(..., description="Optimistic concurrency version check")

class LocationEditApproveRequest(BaseModel):
    version: int = Field(..., description="Optimistic concurrency version check")

class LocationEditRejectRequest(BaseModel):
    version: int = Field(..., description="Optimistic concurrency version check")
    rejection_note: Optional[str] = None

class LocationEditResponse(BaseModel):
    id: int
    location_id: int
    organization_id: int
    submitted_by_user_id: Optional[int]
    approved_by_user_id: Optional[int]
    field_name: str
    old_value: Optional[Any]
    new_value: Any
    status: str
    rejection_note: Optional[str]
    failure_reason: Optional[str]
    google_error_code: Optional[str]
    publish_attempts: int
    version: int
    warning_acknowledged: bool
    requested_publish_at: Optional[datetime]
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class ActivityLogResponse(BaseModel):
    id: int
    organization_id: int
    location_id: Optional[int]
    actor_user_id: Optional[int]
    entity_type: str
    entity_id: Optional[int]
    action: str
    payload: Optional[dict[str, Any]]
    correlation_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
