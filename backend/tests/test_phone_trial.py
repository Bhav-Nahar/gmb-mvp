"""India phone-only trial start (no card/UPI mandate): SubscriptionService.start_phone_trial.

Same in-memory sqlite + mocked-Razorpay/Redis harness as the other billing tests.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from fastapi import HTTPException

from app.core.config import settings
from app.db.session import Base
from app.models.organization import Organization
from app.models.user import User
from app.models.location import Location
from app.models.app_setting import AppSetting
from app.services.billing.subscription_service import SubscriptionService
from app.services.billing.entitlement_service import EntitlementService


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(element, compiler, **kw):
    return "TEXT"


engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

NOW = datetime.now(timezone.utc)
INDIA_PHONE = "+919876543210"


@pytest.fixture(name="db")
def fixture_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def _mk_org(db, status="trial", trial_ends_at=None, sub_id=None, locations=1):
    org = Organization(
        name="t", subscription_status=status, plan="trial", plan_tier="basic",
        trial_ends_at=trial_ends_at, razorpay_subscription_id=sub_id,
        location_quota=1, billing_cycle="monthly",
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    for i in range(locations):
        db.add(Location(
            organization_id=org.id, google_location_id=f"loc_{org.id}_{i}",
            location_name="Branch", sync_status="Synced", billing_status="active",
        ))
    db.commit()
    return org


def _start(db, org_id, phone, razorpay_client=None):
    fake_redis = MagicMock()
    fake_redis.lock.return_value.acquire.return_value = True
    with patch("app.services.billing.subscription_service.get_redis", return_value=fake_redis), \
         patch.object(SubscriptionService, "get_razorpay_client",
                      return_value=razorpay_client or MagicMock()), \
         patch.object(settings, "CARD_REQUIRED_ONBOARDING", True):
        return SubscriptionService.start_phone_trial(db, org_id, phone)


def test_india_phone_starts_trial(db):
    org = _mk_org(db)
    ends = _start(db, org.id, INDIA_PHONE)
    if ends.tzinfo is None:  # sqlite drops tzinfo on the post-commit refresh; Postgres keeps it
        ends = ends.replace(tzinfo=timezone.utc)
    db.refresh(org)
    assert org.subscription_status == "trial"
    assert org.trial_ends_at is not None
    assert abs((ends - (NOW + timedelta(days=7))).total_seconds()) < 3600
    assert org.razorpay_subscription_id is None
    if org.trial_ends_at.tzinfo is None:  # sqlite-only naive round-trip
        org.trial_ends_at = org.trial_ends_at.replace(tzinfo=timezone.utc)
    assert EntitlementService.is_premium_unlocked(org)


def test_non_india_phone_rejected(db):
    org = _mk_org(db)
    with pytest.raises(HTTPException) as e:
        _start(db, org.id, "+14155552671")
    assert e.value.status_code == 400 and "card_required" in e.value.detail
    db.refresh(org)
    assert org.trial_ends_at is None  # still onboarding


def test_missing_phone_rejected(db):
    org = _mk_org(db)
    with pytest.raises(HTTPException) as e:
        _start(db, org.id, None)
    assert e.value.status_code == 400 and "phone_required" in e.value.detail


def test_phone_reuse_blocked(db):
    prior = _mk_org(db, trial_ends_at=NOW + timedelta(days=3))  # consumed a trial
    db.add(User(email="a@b.c", name="A", google_id="g_prior", role="Owner",
                is_active=True, organization_id=prior.id, phone=INDIA_PHONE))
    db.commit()
    org = _mk_org(db)
    with pytest.raises(HTTPException) as e:
        _start(db, org.id, "+91 98765-43210")  # formatting must not bypass dedup
    assert e.value.status_code == 409 and "trial_already_used" in e.value.detail


def test_already_started_or_paid_rejected(db):
    started = _mk_org(db, trial_ends_at=NOW + timedelta(days=3))
    active = _mk_org(db, status="active")
    for org in (started, active):
        with pytest.raises(HTTPException) as e:
            _start(db, org.id, INDIA_PHONE)
        assert e.value.status_code == 400 and "not_onboarding" in e.value.detail


def test_toggle_off_requires_card_even_for_india(db):
    # Super-admin DB override OFF -> India must use the card checkout.
    org = _mk_org(db)
    db.add(AppSetting(key="india_phone_trial", value="false"))
    db.commit()
    with pytest.raises(HTTPException) as e:
        _start(db, org.id, INDIA_PHONE)
    assert e.value.status_code == 400 and "card_required" in e.value.detail
    db.refresh(org)
    assert org.trial_ends_at is None  # still onboarding, must use checkout


def test_toggle_env_default_and_db_override(db):
    org = _mk_org(db)
    with patch.object(settings, "INDIA_PHONE_TRIAL", False):
        # No DB row -> env default (off) applies.
        with pytest.raises(HTTPException) as e:
            _start(db, org.id, INDIA_PHONE)
        assert "card_required" in e.value.detail
        # DB override ON beats the env default.
        db.add(AppSetting(key="india_phone_trial", value="true"))
        db.commit()
        assert _start(db, org.id, INDIA_PHONE) is not None


def test_row_toggle_lets_non_india_start_phone_trial(db):
    # Default: rest of world needs a card (covered by test_non_india_phone_rejected).
    # DB override ON -> a non-+91 phone starts the trial with no mandate.
    org = _mk_org(db)
    db.add(AppSetting(key="row_phone_trial", value="true"))
    db.commit()
    assert _start(db, org.id, "+14155552671") is not None
    db.refresh(org)
    assert org.trial_ends_at is not None and org.razorpay_subscription_id is None


def test_no_locations_rejected(db):
    org = _mk_org(db, locations=0)
    with pytest.raises(HTTPException) as e:
        _start(db, org.id, INDIA_PHONE)
    assert e.value.status_code == 400 and "no_locations" in e.value.detail


def test_abandoned_mandate_cancelled(db):
    org = _mk_org(db, sub_id="sub_abandoned")
    client = MagicMock()
    client.subscription.fetch.return_value = {"status": "created"}
    _start(db, org.id, INDIA_PHONE, razorpay_client=client)
    client.subscription.cancel.assert_called_once_with("sub_abandoned", {"cancel_at_cycle_end": 0})
    db.refresh(org)
    assert org.razorpay_subscription_id is None
    assert org.trial_ends_at is not None
