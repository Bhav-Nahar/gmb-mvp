from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class GBPLocationRaw(BaseModel):
    name: str  # e.g. "locations/12345"
    title: Optional[str] = None
    categories: Optional[Dict[str, Any]] = None
    storefrontAddress: Optional[Dict[str, Any]] = None
    phoneNumbers: Optional[Dict[str, Any]] = None
    websiteUri: Optional[str] = None
    regularHours: Optional[Dict[str, Any]] = None
    profile: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    # These fields are fetched separately but appended internally
    rating: Optional[float] = None
    reviewCount: Optional[int] = None

class GBPReviewRaw(BaseModel):
    name: Optional[str] = None
    reviewId: str
    reviewer: Optional[Dict[str, Any]] = None
    starRating: str
    comment: Optional[str] = None
    reviewReply: Optional[Dict[str, Any]] = None
    createTime: Optional[str] = None
    updateTime: Optional[str] = None

class GBPPostRaw(BaseModel):
    name: str
    state: str
    summary: Optional[str] = None
    callToAction: Optional[Dict[str, Any]] = None
    media: Optional[List[Dict[str, Any]]] = None
    createTime: Optional[str] = None
    updateTime: Optional[str] = None
