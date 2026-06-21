from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, EmailStr

# Organization schemas
class OrganizationBase(BaseModel):
    name: str

class OrganizationOut(OrganizationBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# OAuthAccount schemas
class OAuthAccountOut(BaseModel):
    id: int
    provider: str
    provider_account_id: str
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True

# User schemas
class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    avatar: Optional[str] = None
    google_id: str
    role: str
    is_active: bool
    viewer_scope: Optional[str] = None
    organization_id: int
    created_at: datetime

    # True when the user's email is in the platform super-admin allowlist
    # (settings.SUPERADMIN_EMAILS). Computed per-request in /users/me, not stored.
    is_superuser: bool = False

    # We can include active accounts
    oauth_accounts: List[OAuthAccountOut] = []

    class Config:
        from_attributes = True

class RoleUpdate(BaseModel):
    role: str
    viewer_scope: Optional[str] = None

class LocationsUpdate(BaseModel):
    location_ids: List[int]

class TransferOwnershipRequest(BaseModel):
    new_owner_id: int

# Token schemas
class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

# Location schemas
class LocationOut(BaseModel):
    id: int
    google_location_id: str
    location_name: str
    primary_category: Optional[str] = None
    # Secondary/additional categories: list of {name, displayName}
    additional_categories: Optional[List[Any]] = None
    # Rich GBP fields captured for full parity
    additional_phones: Optional[List[Any]] = None
    special_hours: Optional[Any] = None
    more_hours: Optional[Any] = None
    service_area: Optional[Any] = None
    service_items: Optional[Any] = None
    labels: Optional[List[Any]] = None
    open_info: Optional[Any] = None
    latlng: Optional[Any] = None
    store_code: Optional[str] = None
    language_code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    business_hours: Optional[Any] = None
    average_rating: Optional[float] = None
    total_reviews: Optional[int] = None
    sync_status: str
    billing_status: str = "active"  # 'active' | 'pending_payment' (locked over-quota)
    last_synced_at: Optional[datetime] = None
    sla_tracking_started_at: Optional[datetime] = None
    created_at: datetime
    # Embedded from latest SyncLog — avoids N+1 sync-status requests
    latest_sync_status: Optional[str] = None
    latest_sync_error: Optional[str] = None
    
    # State tracking
    is_verified: Optional[bool] = None
    is_suspended: Optional[bool] = None
    is_duplicate: Optional[bool] = None

    # Embedded Health Score
    health_score: Optional[int] = None
    health_score_label: Optional[str] = None

    class Config:
        from_attributes = True

# SyncLog schemas
class SyncLogOut(BaseModel):
    id: int
    location_id: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    run_type: str
    created_at: datetime

    class Config:
        from_attributes = True

class SyncLogPaginated(BaseModel):
    items: List[SyncLogOut]
    total: int
    page: int
    size: int
