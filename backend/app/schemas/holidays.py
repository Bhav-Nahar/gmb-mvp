from datetime import date as date_type, datetime
from typing import Optional, List
from pydantic import BaseModel, field_validator
from app.schemas.base import ORMBase


class HolidayOut(ORMBase):
    id: int
    date: date_type
    name: str
    category: str
    region: Optional[str] = None
    country: str
    source: str


class HolidayListResponse(BaseModel):
    holidays: List[HolidayOut]
    total: int


class HolidayCreate(BaseModel):
    date: date_type
    name: str
    category: str = "festival"
    region: Optional[str] = None
    country: str = "IN"

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name is required")
        return v.strip()


class HolidaySeedRequest(BaseModel):
    """Seed national + state festivals from the open-source `holidays` package."""
    year: int
    # Indian state subdivisions to include (e.g. ["TN", "KL", "MH"]); empty = national only.
    subdivisions: List[str] = []


class HolidayImportResult(BaseModel):
    created: int
    skipped: int   # duplicates / blank rows
    errors: List[str] = []
