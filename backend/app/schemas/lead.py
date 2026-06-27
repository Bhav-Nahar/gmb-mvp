from typing import Optional
from datetime import datetime
from pydantic import BaseModel, field_validator
from app.schemas.base import ORMBase


class LeadCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    message: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Name is required")
        return v[:120]

    @field_validator("phone", "email", "message")
    @classmethod
    def trim(cls, v):
        if v is None:
            return v
        return str(v).strip()[:2000] or None


class LeadResponse(ORMBase):
    id: int
    location_id: int
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    message: Optional[str] = None
    status: str
    source: str
    created_at: datetime
