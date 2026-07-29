"""Authorization on the auto-reply endpoints: tenant boundary and per-user location
scope. The per-location toggle carries a location_id, so it must go through
require_location_access — a hand-rolled org filter is the shape that caused the
health-score IDOR."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from fastapi import HTTPException

from app.db.session import Base
from app.models.organization import Organization
from app.models.user import User
from app.models.location import Location
from app.models.user_location_access import UserLocationAccess


@compiles(JSONB, "sqlite")
def _jsonb(el, comp, **kw):
    return "TEXT"


_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
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


def _org(db, name):
    o = Organization(name=name, plan_tier="basic", subscription_status="active", location_quota=5)
    db.add(o)
    db.commit()
    return o


def _user(db, org, role="Owner", email=None):
    u = User(email=email or f"{role}@{org.name}.com", name=role, google_id=f"g_{role}_{org.id}",
             role=role, is_active=True, organization_id=org.id)
    db.add(u)
    db.commit()
    return u


def _location(db, org, name):
    loc = Location(organization_id=org.id, google_location_id=f"locations/{name}",
                   location_name=name, billing_status="active")
    db.add(loc)
    db.commit()
    return loc


def test_toggle_rejects_another_orgs_location(db):
    from app.api.deps import require_location_access

    mine, theirs = _org(db, "mine"), _org(db, "theirs")
    owner = _user(db, mine)
    victim = _location(db, theirs, "theirs-1")

    with pytest.raises(HTTPException) as exc:
        require_location_access(location_id=victim.id, db=db, current_user=owner)
    assert exc.value.status_code == 404  # cross-org id is "not found", never touched

    db.refresh(victim)
    assert victim.auto_reply_enabled is True  # untouched


def test_toggle_rejects_a_location_the_manager_is_not_assigned(db):
    from app.api.deps import require_location_access

    org = _org(db, "org")
    mgr = _user(db, org, role="Store Manager")
    assigned = _location(db, org, "assigned")
    other = _location(db, org, "other")
    db.add(UserLocationAccess(user_id=mgr.id, location_id=assigned.id))
    db.commit()

    assert require_location_access(location_id=assigned.id, db=db, current_user=mgr).id == assigned.id
    with pytest.raises(HTTPException) as exc:
        require_location_access(location_id=other.id, db=db, current_user=mgr)
    assert exc.value.status_code == 403


def test_toggle_route_uses_the_location_access_dependency(db):
    """Structural: the route must resolve its location through require_location_access,
    not its own query — otherwise the checks above can be bypassed by the handler."""
    from app.api import reply_templates
    from app.api.deps import require_location_access
    import inspect

    sig = inspect.signature(reply_templates.set_location_auto_reply)
    dep = sig.parameters["location"].default
    assert dep.dependency is require_location_access
