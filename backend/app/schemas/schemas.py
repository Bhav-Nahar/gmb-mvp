from datetime import datetime
from typing import Optional, List
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
    organization_id: int
    created_at: datetime
    
    # We can include active accounts
    oauth_accounts: List[OAuthAccountOut] = []

    class Config:
        from_attributes = True

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
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    average_rating: Optional[float] = None
    total_reviews: Optional[int] = None
    sync_status: str
    last_synced_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

# SyncLog schemas
class SyncLogOut(BaseModel):
    id: int
    status: str
    error_message: Optional[str] = None
    run_type: str
    created_at: datetime

    class Config:
        from_attributes = True
