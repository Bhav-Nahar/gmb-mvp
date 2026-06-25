from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.organization import Organization
from app.models.location import Location
from app.models.microsite import Microsite, MicrositeStatus
from app.services.slug_service import generate_org_slug, generate_location_slug

def generate_microsite(db: Session, organization: Organization, location: Location) -> Microsite:
    """
    Idempotent: if a Microsite already exists for this location_id, return it
    unchanged.

    Steps:
    1. If organization.slug is None, call generate_org_slug() to populate it.
    2. Call generate_location_slug() to get a location_slug scoped to org_slug.
    3. Create Microsite row with status=DRAFT, org_slug, location_slug.
    4. Does NOT set published_at — draft status only.
    """
    # Check if microsite already exists
    existing = db.query(Microsite).filter(Microsite.location_id == location.id).first()
    if existing:
        return existing

    if not organization.slug:
        generate_org_slug(db, organization)

    # Re-fetch organization to ensure slug is available
    org_slug = organization.slug

    loc_slug = generate_location_slug(db, location, organization.id)

    microsite = Microsite(
        organization_id=organization.id,
        location_id=location.id,
        org_slug=org_slug,
        location_slug=loc_slug,
        status=MicrositeStatus.DRAFT.value
    )
    
    db.add(microsite)
    db.commit()
    db.refresh(microsite)

    return microsite

def publish_microsite(db: Session, microsite: Microsite) -> Microsite:
    """
    Sets status=PUBLISHED, published_at=now(). Does not touch unpublished_at.
    Idempotent: publishing an already-published microsite just refreshes
    published_at (we update the timestamp to reflect the most recent "publish" action).
    Clears unpublished_at so a republished site doesn't carry a stale "offline" timestamp.
    Cache revalidation is triggered by the API layer (microsites.py), not here.
    """
    microsite.status = MicrositeStatus.PUBLISHED.value
    microsite.published_at = datetime.now(timezone.utc)
    microsite.unpublished_at = None
    
    db.add(microsite)
    db.commit()
    db.refresh(microsite)
    
    return microsite

def unpublish_microsite(db: Session, microsite: Microsite) -> Microsite:
    """
    Sets status=UNPUBLISHED, unpublished_at=now().
    Does NOT delete the row or clear slugs.
    """
    microsite.status = MicrositeStatus.UNPUBLISHED.value
    microsite.unpublished_at = datetime.now(timezone.utc)
    
    db.add(microsite)
    db.commit()
    db.refresh(microsite)
    
    return microsite
