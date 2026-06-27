from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from app.schemas.base import ORMBase


class RunScanRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=120)
    grid_size: Literal[3, 5, 7, 9] = 5
    radius_miles: float = Field(default=1.5, gt=0, le=25)


class ResultRow(BaseModel):
    rank: int
    name: str
    rating: Optional[float] = None
    reviews: Optional[int] = None
    category: Optional[str] = None
    additional_categories: List[str] = []
    total_photos: Optional[int] = None
    price_level: Optional[str] = None
    is_claimed: Optional[bool] = None
    domain: Optional[str] = None
    address: Optional[str] = None
    image: Optional[str] = None


class CellOut(BaseModel):
    row: int
    col: int
    lat: float
    lng: float
    rank: Optional[int] = None             # business rank at this point, None = not in top results
    top_competitor: Optional[str] = None   # who ranked #1 here (blank if that's us)
    top_results: List[ResultRow] = []      # top ~10 businesses at this point for the pin popup


class ScanOut(ORMBase):
    id: int
    keyword: str
    grid_size: int
    radius_miles: float
    status: str
    avg_rank: Optional[float] = None
    solv: Optional[float] = None
    found_count: int
    total_cells: int
    cells: List[CellOut] = []
    credits_charged: int
    error: Optional[str] = None
    created_at: datetime


class ScanSummaryOut(BaseModel):
    """Lightweight scan for the history list — omits the (potentially large) cells.
    Carries a precomputed centre so the UI can draw a live preview grid."""
    id: int
    keyword: str
    grid_size: int
    radius_miles: float
    status: str
    avg_rank: Optional[float] = None
    solv: Optional[float] = None
    found_count: int
    total_cells: int
    credits_charged: int
    error: Optional[str] = None
    created_at: datetime
    center_lat: Optional[float] = None
    center_lng: Optional[float] = None
