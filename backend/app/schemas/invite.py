from datetime import datetime
from pydantic import BaseModel, EmailStr

class InviteCreate(BaseModel):
    email: EmailStr
    role: str = "Viewer"
    location_ids: list[int] | None = None
    viewer_scope: str | None = "assigned"

class InviteOut(BaseModel):
    id: int
    email: EmailStr
    role: str
    expires_at: datetime
    created_at: datetime
    last_opened_at: datetime | None = None
    invited_by_user_id: int
    status: str
    location_ids: list[int] | None = None
    viewer_scope: str | None = "assigned"

    class Config:
        from_attributes = True

class InviteWithTokenOut(InviteOut):
    token: str

class InviteURLResponse(BaseModel):
    invite_url: str

class InviteVerificationOut(BaseModel):
    email: EmailStr
    role: str
    organization_name: str
