from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class GBPLocationRaw(BaseModel):
    # extra="allow" so any GBP field we haven't explicitly modelled is still
    # preserved on the instance and captured verbatim into the raw payload —
    # nothing Google returns is ever silently dropped.
    model_config = ConfigDict(extra="allow")

    name: str  # e.g. "locations/12345"
    languageCode: Optional[str] = None
    storeCode: Optional[str] = None
    title: Optional[str] = None
    categories: Optional[Dict[str, Any]] = None
    storefrontAddress: Optional[Dict[str, Any]] = None
    phoneNumbers: Optional[Dict[str, Any]] = None
    websiteUri: Optional[str] = None
    regularHours: Optional[Dict[str, Any]] = None
    specialHours: Optional[Dict[str, Any]] = None
    moreHours: Optional[List[Dict[str, Any]]] = None
    serviceArea: Optional[Dict[str, Any]] = None
    serviceItems: Optional[List[Dict[str, Any]]] = None
    labels: Optional[List[str]] = None
    openInfo: Optional[Dict[str, Any]] = None
    latlng: Optional[Dict[str, Any]] = None
    adWordsLocationExtensions: Optional[Dict[str, Any]] = None
    relationshipData: Optional[Dict[str, Any]] = None
    profile: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    locationState: Optional[Dict[str, Any]] = None

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
