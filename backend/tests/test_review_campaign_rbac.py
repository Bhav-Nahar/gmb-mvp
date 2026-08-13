"""Per-store RBAC on review campaigns.

A Store Manager may send for their own stores and see only those results. The
read side matters as much as the write side: campaign history carries customer
phone numbers, so an org-wide filter hands one franchisee another's list.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.api.review_campaigns import _guard, _scope
from app.db.session import Base
from app.models.location import Location
from app.models.organization import Organization
from app.models.review_request import ReviewRequest
from app.models.user import User
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


@pytest.fixture
def org_with_two_stores(db):
    org = Organization(name="Two Stores", plan_tier="basic",
                       subscription_status="active", location_quota=5)
    db.add(org)
    db.commit()
    mine = Location(organization_id=org.id, google_location_id="locations/mine",
                    location_name="Mine", billing_status="active")
    theirs = Location(organization_id=org.id, google_location_id="locations/theirs",
                      location_name="Theirs", billing_status="active")
    db.add_all([mine, theirs])
    db.commit()
    mgr = User(email="mgr@x.com", name="Mgr", google_id="g_mgr", role="Store Manager",
               is_active=True, organization_id=org.id)
    owner = User(email="owner@x.com", name="Owner", google_id="g_owner", role="Owner",
                 is_active=True, organization_id=org.id)
    db.add_all([mgr, owner])
    db.commit()
    db.add(UserLocationAccess(user_id=mgr.id, location_id=mine.id))
    db.commit()
    return org, mine, theirs, mgr, owner


def _request(db, org, loc, token):
    db.add(ReviewRequest(organization_id=org.id, location_id=loc.id,
                         phone="919000000000", token=token))
    db.commit()


def test_manager_cannot_send_for_another_store(db, org_with_two_stores):
    _, mine, theirs, mgr, _ = org_with_two_stores

    with pytest.raises(HTTPException) as exc:
        _guard(db, mgr, theirs.id)
    assert exc.value.status_code == 403

    # Their own store clears the access check and only then hits the
    # "WhatsApp isn't connected" 409 — proving the 403 above was about scope.
    with pytest.raises(HTTPException) as exc:
        _guard(db, mgr, mine.id)
    assert exc.value.status_code == 409


def test_history_scope_hides_other_stores(db, org_with_two_stores):
    org, mine, theirs, mgr, owner = org_with_two_stores
    _request(db, org, mine, "tok-mine")
    _request(db, org, theirs, "tok-theirs")

    base = lambda: db.query(ReviewRequest).filter(ReviewRequest.organization_id == org.id)

    seen = _scope(db, mgr, base(), ReviewRequest.location_id, None).all()
    assert [r.token for r in seen] == ["tok-mine"]

    # Owner sees the whole org, with or without a location filter.
    assert len(_scope(db, owner, base(), ReviewRequest.location_id, None).all()) == 2
    assert len(_scope(db, owner, base(), ReviewRequest.location_id, theirs.id).all()) == 1

    # An explicit foreign id is refused outright, not silently emptied.
    with pytest.raises(HTTPException) as exc:
        _scope(db, mgr, base(), ReviewRequest.location_id, theirs.id)
    assert exc.value.status_code == 403
