from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import admin_required, staff_required, require_location_access
from app.models.user import User
from app.models.location import Location
from app.models.microsite import Microsite
from app.schemas.microsite import MicrositeResponse
from app.services import microsite_service

router = APIRouter()

def _get_location_or_404(db: Session, location_id: int, organization_id: int) -> Location:
    """Helper to verify location exists and belongs to the requesting org."""
    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == organization_id
    ).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location

def _get_microsite_or_404(db: Session, location_id: int, organization_id: int) -> Microsite:
    """Helper to get microsite and verify tenancy."""
    microsite = db.query(Microsite).filter(
        Microsite.location_id == location_id,
        Microsite.organization_id == organization_id
    ).first()
    if not microsite:
        raise HTTPException(status_code=404, detail="Microsite not found for this location.")
    return microsite

@router.post("/{location_id}/microsite/generate", response_model=MicrositeResponse, status_code=status.HTTP_200_OK)
def generate_microsite(
    location_id: int = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """
    Generate or retrieve a draft microsite for a location.
    Idempotent.
    """
    location = _get_location_or_404(db, location_id, current_user.organization_id)
    return microsite_service.generate_microsite(db, current_user.organization, location)

@router.post("/{location_id}/microsite/publish", response_model=MicrositeResponse, status_code=status.HTTP_200_OK)
def publish_microsite(
    location_id: int = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """
    Publish a microsite, making it publicly accessible.
    """
    # Defensive check: ensure location exists
    _get_location_or_404(db, location_id, current_user.organization_id)
    microsite = _get_microsite_or_404(db, location_id, current_user.organization_id)
    
    if not microsite.org_slug or not microsite.location_slug:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot publish a microsite missing slug values."
        )

    res = microsite_service.publish_microsite(db, microsite)
    from app.services.revalidation_service import trigger_bulk_microsite_revalidation
    trigger_bulk_microsite_revalidation([location_id])
    return res

@router.post("/{location_id}/microsite/unpublish", response_model=MicrositeResponse, status_code=status.HTTP_200_OK)
def unpublish_microsite(
    location_id: int = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """
    Unpublish a microsite, taking it offline but preserving its slugs.
    """
    _get_location_or_404(db, location_id, current_user.organization_id)
    microsite = _get_microsite_or_404(db, location_id, current_user.organization_id)
    res = microsite_service.unpublish_microsite(db, microsite)
    from app.services.revalidation_service import trigger_bulk_microsite_revalidation
    trigger_bulk_microsite_revalidation([location_id])
    return res

@router.get("/{location_id}/microsite", response_model=MicrositeResponse, status_code=status.HTTP_200_OK)
def get_microsite(
    location_id: int = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """
    Get the current microsite status. Used by the dashboard to show status.
    """
    _get_location_or_404(db, location_id, current_user.organization_id)
    return _get_microsite_or_404(db, location_id, current_user.organization_id)
