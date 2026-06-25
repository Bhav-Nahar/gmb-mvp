import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.session import Base, get_db
from app.models.organization import Organization
from app.models.location import Location
from app.models.microsite import Microsite

@pytest.fixture(scope="module")
def engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

@pytest.fixture(scope="module")
def setup_db(engine):
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)

@pytest.fixture
def db(engine, setup_db):
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_public_microsite_missing(client):
    response = client.get("/api/v1/public/microsites/non-existent-loc")
    assert response.status_code == 404

def test_public_microsite_draft(client, db):
    org = Organization(name="Test Org")
    db.add(org)
    db.commit()
    
    loc = Location(organization_id=org.id, google_location_id="123", location_name="Test Loc")
    db.add(loc)
    db.commit()
    
    ms = Microsite(organization_id=org.id, location_id=loc.id, org_slug="test-org", location_slug="test-loc", status="draft")
    db.add(ms)
    db.commit()

    response = client.get("/api/v1/public/microsites/test-loc")
    assert response.status_code == 404

def test_public_microsite_unpublished(client, db):
    org = Organization(name="Test Org 2")
    db.add(org)
    db.commit()
    
    loc = Location(organization_id=org.id, google_location_id="1234", location_name="Test Loc 2")
    db.add(loc)
    db.commit()
    
    ms = Microsite(organization_id=org.id, location_id=loc.id, org_slug="test-org-2", location_slug="test-loc-2", status="unpublished")
    db.add(ms)
    db.commit()

    response = client.get("/api/v1/public/microsites/test-loc-2")
    assert response.status_code == 410

def test_public_microsite_published(client, db):
    org = Organization(name="Test Org 3")
    db.add(org)
    db.commit()
    
    loc = Location(organization_id=org.id, google_location_id="12345", location_name="Test Loc 3", city="San Francisco", address="123 Main St", primary_category="Bakery")
    db.add(loc)
    db.commit()
    
    ms = Microsite(organization_id=org.id, location_id=loc.id, org_slug="test-org-3", location_slug="test-loc-3", status="published")
    db.add(ms)
    db.commit()

    response = client.get("/api/v1/public/microsites/test-loc-3")
    assert response.status_code == 200
    data = response.json()
    assert data["location_name"] == "Test Loc 3"
    assert data["city"] == "San Francisco"
    assert data["address"] == "123 Main St"
    assert data["status"] == "published"
    assert data["photos"] == []
    assert data["reviews"] == []
    assert data["service_items"] == []
