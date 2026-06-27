import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.session import Base, get_db
from app.api.deps import get_current_user, require_location_access, admin_required, staff_required, check_billing_lock, check_csrf
from app.models.organization import Organization
from app.models.user import User
from app.models.location import Location
from app.models.microsite import Microsite
from app.core.roles import Role

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

def _create_user(db: Session, org_id: int, role: Role, email: str) -> User:
    u = User(email=email, name="Test", google_id=email, role=role, is_active=True, organization_id=org_id)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

@pytest.fixture
def auth_setup(client, db):
    org = Organization(name="Test Org", plan_tier="pro")  # microsite is a Pro-tier feature
    db.add(org)
    db.commit()
    db.refresh(org)

    org2 = Organization(name="Other Org")
    db.add(org2)
    db.commit()
    db.refresh(org2)

    admin_user = _create_user(db, org.id, Role.ADMIN, "admin@test.com")
    other_user = _create_user(db, org2.id, Role.ADMIN, "other@test.com")

    loc = Location(organization_id=org.id, google_location_id="123", location_name="Test Loc")
    loc2 = Location(organization_id=org2.id, google_location_id="456", location_name="Other Loc")
    db.add_all([loc, loc2])
    db.commit()
    db.refresh(loc)
    db.refresh(loc2)

    def override_current_user():
        return admin_user

    def override_noop():
        return None

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[admin_required] = override_current_user
    app.dependency_overrides[staff_required] = override_current_user
    # require_location_access is NOT overridden — the real dependency runs against
    # the test DB (org-scoped lookup + scope check), so it enforces real tenancy.
    app.dependency_overrides[check_billing_lock] = override_noop
    app.dependency_overrides[check_csrf] = override_noop

    return {
        "org": org,
        "org2": org2,
        "admin_user": admin_user,
        "other_user": other_user,
        "loc": loc,
        "loc2": loc2
    }

def test_generate_microsite_fresh(client, auth_setup, db):
    loc_id = auth_setup["loc"].id
    
    # Generate
    response = client.post(f"/api/v1/locations/{loc_id}/microsite/generate")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    assert data["org_slug"] == "test-org"
    assert data["location_slug"] == "test-loc"
    assert data["public_url"].endswith("/test-loc")
    assert data["published_at"] is None

    # Check that org slug was populated
    org = auth_setup["org"]
    db.refresh(org)
    assert org.slug == "test-org"

def test_generate_microsite_idempotent(client, auth_setup, db):
    loc_id = auth_setup["loc"].id
    
    # First generate
    res1 = client.post(f"/api/v1/locations/{loc_id}/microsite/generate")
    data1 = res1.json()

    # Second generate
    res2 = client.post(f"/api/v1/locations/{loc_id}/microsite/generate")
    data2 = res2.json()

    assert data1["id"] == data2["id"]
    assert data1["org_slug"] == data2["org_slug"]

def test_publish_microsite(client, auth_setup, db):
    loc_id = auth_setup["loc"].id
    client.post(f"/api/v1/locations/{loc_id}/microsite/generate")

    response = client.post(f"/api/v1/locations/{loc_id}/microsite/publish")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "published"
    assert data["published_at"] is not None

    # GET to confirm
    res_get = client.get(f"/api/v1/locations/{loc_id}/microsite")
    assert res_get.status_code == 200
    assert res_get.json()["status"] == "published"
    assert res_get.json()["published_at"] == data["published_at"]

def test_unpublish_microsite(client, auth_setup, db):
    loc_id = auth_setup["loc"].id
    client.post(f"/api/v1/locations/{loc_id}/microsite/generate")
    client.post(f"/api/v1/locations/{loc_id}/microsite/publish")

    response = client.post(f"/api/v1/locations/{loc_id}/microsite/unpublish")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unpublished"
    assert data["unpublished_at"] is not None
    assert data["org_slug"] == "test-org"  # Slugs unchanged

def test_republish_microsite(client, auth_setup, db):
    loc_id = auth_setup["loc"].id
    client.post(f"/api/v1/locations/{loc_id}/microsite/generate")
    client.post(f"/api/v1/locations/{loc_id}/microsite/publish")
    client.post(f"/api/v1/locations/{loc_id}/microsite/unpublish")

    response = client.post(f"/api/v1/locations/{loc_id}/microsite/publish")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "published"
    assert data["org_slug"] == "test-org"

def test_publish_not_found(client, auth_setup):
    loc_id = auth_setup["loc"].id
    # Clear any generated microsites for this loc
    # (actually db is rolled back per test thanks to fixture, so it's clean)
    response = client.post(f"/api/v1/locations/{loc_id}/microsite/publish")
    assert response.status_code == 404
    assert response.json()["detail"] == "Microsite not found for this location."

def test_tenancy_check(client, auth_setup):
    # Try to access a location from org2 while logged in as org1 (admin_user)
    loc2_id = auth_setup["loc2"].id
    
    # generate
    response = client.post(f"/api/v1/locations/{loc2_id}/microsite/generate")
    assert response.status_code == 404
    
    # publish
    response = client.post(f"/api/v1/locations/{loc2_id}/microsite/publish")
    assert response.status_code == 404
    
    # GET
    response = client.get(f"/api/v1/locations/{loc2_id}/microsite")
    assert response.status_code == 404
