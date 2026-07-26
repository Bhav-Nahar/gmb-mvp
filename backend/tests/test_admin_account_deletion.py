"""Super-admin soft-delete + 14-day restore + hard-purge of accounts.

Covers: org/user soft-delete & restore endpoints, the last-Owner guard, immediate
access cutoff for a deleted account, and the daily purge task (past-grace vs within-grace).
Mirrors the in-memory SQLite + StaticPool setup used by the other suites.
"""
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base, get_db
from app.core.config import settings
from app.core.security import create_access_token
from app.models.organization import Organization
from app.models.user import User



@compiles(JSONB, "sqlite")
def _jsonb(el, comp, **kw):
    return "TEXT"


_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

SUPER_EMAIL = "root@t.com"


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

    def _override():
        yield db
    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _org(db, name="Org", **kw):
    o = Organization(name=name, **kw)
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def _user(db, org, email, role="Owner"):
    u = User(email=email, name=email, google_id=f"g_{email}", role=role,
             is_active=True, organization_id=org.id)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _as_super(db, client):
    org = _org(db, "SuperOrg")
    u = _user(db, org, SUPER_EMAIL, role="Owner")
    client.cookies.set("gmb_auth_token", create_access_token(u.email, token_version=u.token_version))
    return u


def _superpatch():
    return patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL)


def test_org_soft_delete_and_restore(db, client):
    target = _org(db, "Target", subscription_status="active")
    with _superpatch():
        _as_super(db, client)
        r = client.request("DELETE", f"/api/v1/admin/organizations/{target.id}", json={"reason": "spam"})
        assert r.status_code == 200, r.text
        assert r.json()["purge_after"] is not None
        db.refresh(target)
        assert target.deleted_at is not None

        # already deleted -> 409
        r2 = client.request("DELETE", f"/api/v1/admin/organizations/{target.id}", json={})
        assert r2.status_code == 409

        # restore
        r3 = client.post(f"/api/v1/admin/organizations/{target.id}/restore", json={"reason": "oops"})
        assert r3.status_code == 200, r3.text
        db.refresh(target)
        assert target.deleted_at is None


def test_deleted_org_blocks_member_access(db, client):
    target = _org(db, "Target", subscription_status="active")
    member = _user(db, target, "member@t.com", role="Admin")
    client.cookies.set("gmb_auth_token", create_access_token(member.email, token_version=member.token_version))

    # Works while live.
    assert client.get("/api/v1/billing/status").status_code == 200
    # Soft-delete the org -> member is locked out immediately.
    target.deleted_at = datetime.now(timezone.utc)
    db.commit()
    resp = client.get("/api/v1/billing/status")
    assert resp.status_code == 403
    assert "deleted" in resp.json()["detail"].lower()


def test_cannot_delete_only_owner(db, client):
    target = _org(db, "Target", subscription_status="active")
    owner = _user(db, target, "owner@t.com", role="Owner")
    with _superpatch():
        _as_super(db, client)
        r = client.request("DELETE", f"/api/v1/admin/users/{owner.id}", json={})
    assert r.status_code == 409
    assert "only Owner" in r.json()["detail"]


def test_delete_user_soft_deletes_and_invalidates_session(db, client):
    target = _org(db, "Target", subscription_status="active")
    _user(db, target, "owner@t.com", role="Owner")            # keeps an owner
    member = _user(db, target, "member@t.com", role="Admin")
    before = member.token_version
    with _superpatch():
        _as_super(db, client)
        r = client.request("DELETE", f"/api/v1/admin/users/{member.id}", json={})
    assert r.status_code == 200, r.text
    db.refresh(member)
    assert member.deleted_at is not None
    assert member.token_version == before + 1   # live sessions invalidated


def test_purge_task_removes_past_grace_keeps_recent(db):
    from app.core import plan_config
    grace = plan_config.ACCOUNT_PURGE_GRACE_DAYS
    now = datetime.now(timezone.utc)
    old = _org(db, "Old", deleted_at=now - timedelta(days=grace + 1))
    recent = _org(db, "Recent", deleted_at=now - timedelta(days=grace - 1))
    live = _org(db, "Live")

    import app.tasks as tasks_mod
    fake_redis = MagicMock()
    fake_redis.lock.return_value.acquire.return_value = True
    with patch.object(tasks_mod, "SessionLocal", return_value=db), \
         patch.object(tasks_mod, "_get_redis", return_value=fake_redis), \
         patch.object(db, "close"):
        tasks_mod.purge_soft_deleted_accounts_task()

    assert db.query(Organization).filter(Organization.id == old.id).first() is None      # purged
    assert db.query(Organization).filter(Organization.id == recent.id).first() is not None  # within grace
    assert db.query(Organization).filter(Organization.id == live.id).first() is not None    # never deleted


def test_purge_cancels_razorpay_sub_before_deleting(db):
    from app.core import plan_config
    grace = plan_config.ACCOUNT_PURGE_GRACE_DAYS
    now = datetime.now(timezone.utc)
    paid = _org(db, "Paid", deleted_at=now - timedelta(days=grace + 1),
                razorpay_subscription_id="sub_ABC123")

    import app.tasks as tasks_mod
    from app.services.billing.subscription_service import SubscriptionService
    fake_redis = MagicMock()
    fake_redis.lock.return_value.acquire.return_value = True
    fake_client = MagicMock()
    with patch.object(tasks_mod, "SessionLocal", return_value=db), \
         patch.object(tasks_mod, "_get_redis", return_value=fake_redis), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake_client), \
         patch.object(db, "close"):
        tasks_mod.purge_soft_deleted_accounts_task()

    fake_client.subscription.cancel.assert_called_once_with("sub_ABC123", {"cancel_at_cycle_end": 0})
    assert db.query(Organization).filter(Organization.id == paid.id).first() is None  # still purged


def test_org_user_count_is_live_seats_only(db, client):
    """user_count drives the 'orphaned' badge, so it must exclude soft-deleted seats.

    Counting them made an unreachable workspace — the one a hard DELETE on `users`
    leaves behind, before the owner's next sign-in mints a second org — look occupied.
    """
    ghost = _org(db, "Ghost")           # user row deleted straight from the DB
    stale = _org(db, "Stale")           # only seat is soft-deleted
    dead = _user(db, stale, "gone@t.com")
    dead.deleted_at = datetime.now(timezone.utc)
    live = _org(db, "Live")
    _user(db, live, "here@t.com")
    db.commit()

    with _superpatch():
        _as_super(db, client)
        items = {o["name"]: o for o in client.get("/api/v1/admin/organizations").json()["items"]}
        assert items["Ghost"]["user_count"] == 0
        assert items["Stale"]["user_count"] == 0
        assert items["Live"]["user_count"] == 1
        # Detail view counts live seats too, not just the current page.
        detail = client.get(f"/api/v1/admin/organizations/{stale.id}").json()
        assert detail["organization"]["user_count"] == 0
        assert detail["users_total"] == 1  # the soft-deleted seat is still listed, badged
