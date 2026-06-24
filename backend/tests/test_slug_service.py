import pytest
from sqlalchemy.orm import Session
from app.services.slug_service import slugify, generate_org_slug, generate_location_slug
from app.models.organization import Organization
from app.models.location import Location
from app.models.microsite import Microsite

def test_slugify_normal():
    assert slugify("Normal Name") == "normal-name"

def test_slugify_apostrophe():
    assert slugify("Tony's Pizza") == "tonys-pizza"

def test_slugify_non_ascii():
    assert slugify("Café Münchén") == "cafe-munchen"

def test_slugify_all_numeric():
    assert slugify("123 456") == "123-456"

def test_slugify_empty():
    slug = slugify("")
    assert slug.startswith("id-")

def test_slugify_non_alphanumeric():
    slug = slugify("!!! ???")
    assert slug.startswith("id-")

def test_slugify_with_row_id():
    slug = slugify("", fallback_prefix="org", row_id=42)
    assert slug == "org-42"

def test_generate_org_slug_creates_slug(db: Session):
    org = Organization(name="Test Org")
    db.add(org)
    db.commit()
    db.refresh(org)
    
    slug = generate_org_slug(db, org)
    assert slug == "test-org"
    assert org.slug == "test-org"
    
def test_generate_org_slug_idempotent(db: Session):
    org = Organization(name="Idempotent Org", slug="already-set")
    db.add(org)
    db.commit()
    db.refresh(org)
    
    slug = generate_org_slug(db, org)
    assert slug == "already-set"

def test_generate_org_slug_collision(db: Session):
    org1 = Organization(name="Collision Org")
    org2 = Organization(name="Collision Org")
    db.add_all([org1, org2])
    db.commit()
    db.refresh(org1)
    db.refresh(org2)
    
    slug1 = generate_org_slug(db, org1)
    slug2 = generate_org_slug(db, org2)
    
    assert slug1 == "collision-org"
    assert slug2 == "collision-org-2"
    
def test_generate_org_slug_reserved_word(db: Session):
    org = Organization(name="Admin")
    db.add(org)
    db.commit()
    db.refresh(org)
    
    slug = generate_org_slug(db, org)
    assert slug == "admin-org"

def test_generate_location_slug_no_collision(db: Session):
    org = Organization(name="Loc Org", slug="loc-org")
    db.add(org)
    db.commit()
    db.refresh(org)
    
    loc = Location(organization_id=org.id, google_location_id="123", location_name="Downtown Branch")
    db.add(loc)
    db.commit()
    db.refresh(loc)
    
    slug = generate_location_slug(db, loc, org.id)
    assert slug == "downtown-branch"

def test_generate_location_slug_collision(db: Session):
    org = Organization(name="Loc Org Col", slug="loc-org-col")
    db.add(org)
    db.commit()
    db.refresh(org)
    
    loc1 = Location(organization_id=org.id, google_location_id="123", location_name="Uptown Branch")
    loc2 = Location(organization_id=org.id, google_location_id="456", location_name="Uptown Branch")
    db.add_all([loc1, loc2])
    db.commit()
    db.refresh(loc1)
    db.refresh(loc2)
    
    # We must insert a microsite for loc1 to simulate collision
    slug1 = generate_location_slug(db, loc1, org.id)
    assert slug1 == "uptown-branch"
    
    ms = Microsite(
        organization_id=org.id, 
        location_id=loc1.id, 
        org_slug=org.slug, 
        location_slug=slug1
    )
    db.add(ms)
    db.commit()
    
    slug2 = generate_location_slug(db, loc2, org.id)
    assert slug2 == f"uptown-branch-{loc2.id}"
