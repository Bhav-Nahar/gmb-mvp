from typing import List, Optional, Literal
from pydantic import BaseModel


class GenerateDescriptionRequest(BaseModel):
    mode: Literal["generate_new", "improve_existing"] = "generate_new"
    tone: str = "professional"
    language: str = "english"
    usp: Optional[str] = None
    services: Optional[List[str]] = None
    audience: Optional[str] = None
    nudge: Optional[str] = None  # regen control: premium|local|shorter|warmer|clinic_safe|seo
    # The text to refine when regenerating (the on-screen draft). Falls back to the
    # location's saved description when omitted.
    base_text: Optional[str] = None


class PolicyFlags(BaseModel):
    hard: List[str] = []
    soft: List[str] = []


class DescriptionResponse(BaseModel):
    charged: bool
    credits_charged: int
    is_valid: bool                 # False here means: even after one rewrite, hard flags remain → not charged
    description: str
    char_count: int
    status: str
    policy_flags: PolicyFlags
    improvement_notes: List[str] = []
    seo_terms: List[str] = []
    category_mentioned: str = ""
    locality_used: str = ""


class ValidateDescriptionRequest(BaseModel):
    text: str


class ValidateDescriptionResponse(BaseModel):
    is_valid: bool
    hard_flags: List[str]
    soft_flags: List[str]
    char_count: int
