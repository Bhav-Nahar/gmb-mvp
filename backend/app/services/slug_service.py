import os
import re
import unicodedata
from sqlalchemy.orm import Session
from app.models.organization import Organization
from app.models.microsite import Microsite
from app.models.location import Location

# Based on frontend/app top-level directories
RESERVED_SLUGS = {
    "admin", "contact", "dashboard", "invite", "login", 
    "privacy", "refund", "terms", "api", "static", "_next", "public"
}

def slugify(value: str, fallback_prefix: str = "id", row_id: int | str | None = None) -> str:
    """
    Lowercase, ASCII-transliterate, replace whitespace/non-alphanumeric runs with single hyphens, 
    and strip leading/trailing hyphens.
    
    Empty or fully-non-alphanumeric input falls back to a suffix based on row_id or a random string.
    """
    if not value:
        value = ""
    # Transliterate to ascii
    slug = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    # Lowercase
    slug = slug.lower()
    # Remove apostrophes
    slug = slug.replace("'", "").replace("’", "")
    # Replace non-alphanumeric runs with hyphens
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    # Strip leading/trailing hyphens
    slug = slug.strip('-')
    
    if not slug:
        suffix = str(row_id) if row_id is not None else os.urandom(3).hex()
        return f"{fallback_prefix}-{suffix}"
    return slug

def generate_org_slug(db: Session, organization: Organization) -> str:
    """
    Generates a unique slug for the organization and persists it to the database.
    This function has a side effect: it writes to the `organization.slug` attribute 
    and commits/flushes the session.
    
    If organization.slug is already set, this will be skipped and return the existing slug.
    """
    if organization.slug:
        return organization.slug

    base_slug = slugify(organization.name, fallback_prefix="org", row_id=organization.id)
    
    if base_slug in RESERVED_SLUGS:
        base_slug = f"{base_slug}-org"

    slug = base_slug
    counter = 1
    
    # Loop to ensure uniqueness across organizations.slug
    while True:
        existing = db.query(Organization).filter(Organization.slug == slug).first()
        if not existing:
            break
        counter += 1
        slug = f"{base_slug}-{counter}"
        
    organization.slug = slug
    db.add(organization)
    db.commit()
    db.refresh(organization)
    
    return slug

def generate_location_slug(db: Session, location: Location, org_id: int = None) -> str:
    """
    Generates a GLOBALLY-unique, single-segment SEO slug for a location.

    The public URL is single-level (e.g. pinzo.io/{location_slug}), so uniqueness
    is global across all microsites — NOT org-scoped. (org_id is kept for call-site
    compatibility but no longer used for scoping.)

    Slug = slugify(location_name), with city appended only if the name doesn't
    already contain it (so "Rupesh Jewellers in Malad, Mumbai" + city "Mumbai"
    yields "rupesh-jewellers-in-malad-mumbai", not "...-mumbai-mumbai").

    Does NOT persist; returns the string for the caller to store on the Microsite.
    """
    base_slug = slugify(location.location_name, fallback_prefix="location", row_id=location.id)

    if location.city:
        city_slug = slugify(location.city)
        if city_slug and city_slug not in base_slug:
            base_slug = f"{base_slug}-{city_slug}"

    # Single-segment URL shares the root namespace with top-level routes; never
    # let a slug collide with one (e.g. a location literally named "Dashboard").
    if base_slug in RESERVED_SLUGS:
        base_slug = f"{base_slug}-{location.id}"

    # Global uniqueness across every microsite (exclude this location's own row
    # so re-generation is stable).
    existing = db.query(Microsite).filter(
        Microsite.location_slug == base_slug,
        Microsite.location_id != location.id,
    ).first()

    if existing:
        # Deterministic one-step disambiguation.
        return f"{base_slug}-{location.id}"

    return base_slug
