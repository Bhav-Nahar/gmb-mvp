from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field, AnyHttpUrl, computed_field
from app.constants.posts import PostType, PostStatus, CallToActionType, MediaType, PublishJobStatus, CampaignStatus

# -----------------
# Responses
# -----------------

class CampaignResponse(BaseModel):
    id: int
    organization_id: int
    created_by_user_id: Optional[int]
    name: str
    description: Optional[str]
    status: str
    total_locations: int
    total_pending: int
    total_published: int
    total_failed: int
    total_rejected: int
    total_shadow_banned: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CampaignListResponse(BaseModel):
    campaigns: List[CampaignResponse]
    total: int
    page: int
    pages: int

class CampaignProgressResponse(BaseModel):
    id: int
    status: str
    total_locations: int
    total_pending: int
    total_published: int
    total_failed: int
    total_rejected: int
    total_shadow_banned: int

class PostResponse(BaseModel):
    id: int
    organization_id: int
    campaign_id: Optional[int]
    created_by_user_id: Optional[int]
    title: Optional[str]
    summary: str
    language_code: str
    post_type: str
    status: str
    cta_type: Optional[str]
    cta_url: Optional[str]
    is_bulk_post: bool
    scheduled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class PostListResponse(BaseModel):
    posts: List[PostResponse]
    total: int
    page: int
    pages: int

class PostVariantResponse(BaseModel):
    id: int
    organization_id: int
    post_id: int
    location_id: int
    rendered_summary: str
    rendered_cta_url: Optional[str]
    rendering_variables: Optional[Any]
    created_at: datetime

    class Config:
        from_attributes = True

class PostMediaResponse(BaseModel):
    id: int
    organization_id: int
    post_id: Optional[int] = None
    storage_provider: str
    storage_key: str
    media_type: str
    original_filename: Optional[str]
    mime_type: Optional[str]
    file_size: Optional[int]
    width: Optional[int]
    height: Optional[int]
    sha256_hash: str
    cdn_url: str
    thumbnail_url: Optional[str] = None
    optimized_url: Optional[str] = None
    upload_status: str
    validation_status: str
    is_deleted: bool
    deleted_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @computed_field
    @property
    def is_ready(self) -> bool:
        return self.upload_status == "Optimized" and self.validation_status == "Valid" and self.optimized_url is not None

class PublishJobResponse(BaseModel):
    id: int
    organization_id: int
    campaign_id: Optional[int]
    post_id: int
    location_id: int
    provider: str
    status: str
    retry_count: int
    last_error: Optional[str]
    google_post_id: Optional[str]
    provider_response: Optional[Any]
    idempotency_key: Optional[str]
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class PostAuditLogResponse(BaseModel):
    id: int
    organization_id: int
    post_id: int
    actor_user_id: Optional[int]
    action: str
    previous_status: Optional[str]
    new_status: Optional[str]
    log_metadata: Optional[Any]
    created_at: datetime

    class Config:
        from_attributes = True

class CampaignAuditLogResponse(BaseModel):
    id: int
    organization_id: int
    campaign_id: int
    actor_user_id: Optional[int]
    action: str
    previous_status: Optional[str]
    new_status: Optional[str]
    log_metadata: Optional[Any]
    created_at: datetime

    class Config:
        from_attributes = True

class CampaignDetailResponse(CampaignProgressResponse):
    jobs: List[PublishJobResponse]
    audit_logs: List[CampaignAuditLogResponse]

class BatchPublishJobCreateResponse(BaseModel):
    successful_jobs: List[PublishJobResponse]

class CampaignLaunchRequest(BaseModel):
    location_ids: List[int] = Field(..., min_length=1)

# -----------------
# Requests
# -----------------

class PostCreateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=100)
    summary: str = Field(..., max_length=1500)
    language_code: str = "en-US"
    post_type: PostType
    cta_type: Optional[CallToActionType] = None
    cta_url: Optional[AnyHttpUrl] = None
    is_bulk_post: bool = False
    campaign_id: Optional[int] = None
    scheduled_at: Optional[datetime] = None

class PostUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=100)
    summary: Optional[str] = Field(None, max_length=1500)
    language_code: Optional[str] = None
    post_type: Optional[PostType] = None
    status: Optional[PostStatus] = None
    cta_type: Optional[CallToActionType] = None
    cta_url: Optional[AnyHttpUrl] = None
    scheduled_at: Optional[datetime] = None

class CampaignCreateRequest(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    total_locations: int = 0

class PostMediaCreateRequest(BaseModel):
    storage_provider: str
    storage_key: Optional[str] = None
    media_type: MediaType = MediaType.PHOTO
    original_filename: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    sha256_hash: str
    cdn_url: AnyHttpUrl
