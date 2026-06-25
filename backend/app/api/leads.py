from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import require_location_access, staff_required, admin_required
from app.models.user import User
from app.models.lead import Lead
from app.models.location import Location
from app.schemas.lead import LeadResponse
from pydantic import BaseModel

router = APIRouter()


class LeadEmailUpdate(BaseModel):
    lead_email: str | None = None


@router.get("/{location_id}/lead-email")
def get_lead_email(
    location_id: int = Depends(require_location_access),
    current_user: User = Depends(staff_required),
    db: Session = Depends(get_db),
):
    loc = db.query(Location).filter(Location.id == location_id).first()
    return {"lead_email": loc.lead_email if loc else None}


@router.put("/{location_id}/lead-email")
def set_lead_email(
    payload: LeadEmailUpdate,
    location_id: int = Depends(require_location_access),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    loc = db.query(Location).filter(
        Location.id == location_id, Location.organization_id == current_user.organization_id
    ).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    val = (payload.lead_email or "").strip() or None
    if val and "@" not in val:
        raise HTTPException(status_code=400, detail="Invalid email")
    loc.lead_email = val
    db.commit()
    return {"lead_email": val}


@router.get("/{location_id}/leads", response_model=List[LeadResponse])
def list_leads(
    location_id: int = Depends(require_location_access),
    current_user: User = Depends(staff_required),
    db: Session = Depends(get_db),
):
    return (
        db.query(Lead)
        .filter(Lead.location_id == location_id, Lead.organization_id == current_user.organization_id)
        .order_by(Lead.created_at.desc())
        .limit(500)
        .all()
    )


@router.patch("/{location_id}/leads/{lead_id}", response_model=LeadResponse)
def update_lead_status(
    lead_id: int,
    status_value: str,
    location_id: int = Depends(require_location_access),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    if status_value not in ("new", "contacted", "closed"):
        raise HTTPException(status_code=400, detail="Invalid status")
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.location_id == location_id,
        Lead.organization_id == current_user.organization_id,
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.status = status_value
    db.commit()
    db.refresh(lead)
    return lead
