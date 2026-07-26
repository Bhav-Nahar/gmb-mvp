"""Org-level /locations/sync-status endpoint that drives the live sync progress UI."""
import sys
import types
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base, get_db
from app.core.security import create_access_token
from app.models.organization import Organization
from app.models.user import User
from app.models.location import Location
from app.models.organization_sync_state import OrganizationSyncState



@compiles(JSONB, "sqlite")
def _jsonb(el, comp, **kw):
    return "TEXT"


_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(name="db")
def fixture_db():
    Base.metadata.create_all(bind=_engine)
    db = _Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture(name="client")
def fixture_client(db):
    from fastapi.testclient import TestClient
    from app.main import app

    def _o():
        yield db
    app.dependency_overrides[get_db] = _o
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(db, client, org):
    u = User(email="u@t.com", name="U", google_id="g_u", role="Owner", is_active=True, organization_id=org.id)
    db.add(u)
    db.commit()
    db.refresh(u)
    client.cookies.set("gmb_auth_token", create_access_token(u.email, token_version=u.token_version))


def _loc(db, org, name, status):
    db.add(Location(organization_id=org.id, google_location_id=f"g_{name}", location_name=name,
                    sync_status=status, billing_status="active"))
    db.commit()


def test_sync_status_reports_progress(db, client):
    org = Organization(name="Org", subscription_status="active")
    db.add(org)
    db.commit()
    db.refresh(org)
    db.add(OrganizationSyncState(organization_id=org.id, sync_in_progress=True, last_sync_status="Pending"))
    _loc(db, org, "A", "Synced")
    _loc(db, org, "B", "Synced")
    _loc(db, org, "C", "Pending")
    db.commit()
    _auth(db, client, org)

    r = client.get("/api/v1/locations/sync-status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sync_in_progress"] is True
    assert body["locations_total"] == 3
    assert body["locations_synced"] == 2
    assert body["last_sync_status"] == "Pending"


def test_sync_status_idle_when_no_state(db, client):
    org = Organization(name="Fresh", subscription_status="trial")
    db.add(org)
    db.commit()
    db.refresh(org)
    _auth(db, client, org)

    r = client.get("/api/v1/locations/sync-status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sync_in_progress"] is False
    assert body["locations_total"] == 0
    assert body["ever_synced"] is False
