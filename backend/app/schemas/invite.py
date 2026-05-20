from datetime import datetime
from pydantic import BaseModel, EmailStr

class InviteCreate(BaseModel):
    email: EmailStr
    role: str = "Staff"

class InviteOut(BaseModel):
    id: int
    email: EmailStr
    role: str
    token: str
    expires_at: datetime
    created_at: datetime
    invited_by_user_id: int
    status: str

    class Config:
        from_attributes = True

class InviteURLResponse(BaseModel):
    invite_url: str

class InviteVerificationOut(BaseModel):
    email: EmailStr
    role: str
    organization_name: str
