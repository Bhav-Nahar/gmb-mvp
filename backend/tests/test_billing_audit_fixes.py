"""Tests for the billing audit remediations (subscription stress-test fixes).

Each test pins one fix so a regression fails loudly:
  1. Annual subs get a monthly credit refill (not just yearly).
  2. Failed plan-amount upgrade is retried (card -> upgraded; UPI -> needs_remandate).
  3. Re-mandate reuses/cancels the pending mandate instead of stacking duplicates.
  4. Add-ons are blocked while a re-mandate is pending.
  5. An add-on capture that unlocks fewer locations than billed is flagged for refund.
  6. Refunds accumulate and lock on a chunked full refund; full refund cancels the mandate.
  7. Pending trials are capped at created_at + PENDING_TRIAL_MAX_DAYS.
  8. CreditService.reserve debits atomically up front; refund returns credits.

Mirrors the in-memory SQLite + mocked-Razorpay setup of test_billing_fixes.py.
"""
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

# Stub the Celery app so tests that exercise enqueue paths don't pull the heavy
# worker/task import graph. `from app.worker import celery` resolves to this.
import app as _app_pkg
try:
    import app.worker  # real celery app; also sets the app.worker attribute for patch()
except Exception:
    if "app.worker" not in sys.modules:
        _fw = types.ModuleType("app.worker"); _fw.celery = MagicMock()
        sys.modules["app.worker"] = _fw
    _app_pkg.worker = sys.modules["app.worker"]

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from fastapi import HTTPException

from app.db.session import Base
from app.models.organization import Organization
from app.models.location import Location
from app.models.billing_transaction import BillingTransaction
from app.services.billing.webhook_service import WebhookService
from app.services.billing.subscription_service import SubscriptionService
from app.services.billing.credit_service import CreditService
from app.services.billing.entitlement_service import EntitlementService
from app.core import plan_config


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"


# StaticPool: share ONE in-memory connection across threads so the TestClient's request
# thread sees the tables the fixture created (otherwise each thread gets its own empty DB).
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


def _mk_org(db, **kw):
    org = Organization(name=kw.pop("name", "Org"), **kw)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


# --- Fix 1: annual monthly credit refill ------------------------------------

def test_annual_credits_refilled_monthly_but_not_monthly_subs(db):
    annual = _mk_org(db, name="Annual", subscription_status="active", billing_cycle="annual",
                     location_quota=3, plan_tier="basic", monthly_ai_credits_balance=0)
    monthly = _mk_org(db, name="Monthly", subscription_status="active", billing_cycle="monthly",
                      location_quota=3, plan_tier="basic", monthly_ai_credits_balance=0)

    import app.tasks as tasks_mod
    fake_redis = MagicMock()
    fake_redis.lock.return_value.acquire.return_value = True
    with patch.object(tasks_mod, "SessionLocal", return_value=db), \
         patch.object(tasks_mod, "_get_redis", return_value=fake_redis), \
         patch.object(db, "close"):
        tasks_mod.refill_annual_monthly_credits_task()

    db.refresh(annual)
    db.refresh(monthly)
    assert annual.monthly_ai_credits_balance == 90   # 3 * 30, refilled
    assert monthly.monthly_ai_credits_balance == 0   # untouched — refills via charge webhook


# --- Fix 2: failed plan-amount upgrade is retried ---------------------------

def test_reconcile_plan_amount_card_upgrades(db):
    org = _mk_org(db, subscription_status="active", razorpay_subscription_id="sub_d",
                  location_quota=6, paid_location_quota=4, billing_cycle="monthly",
                  plan_tier="basic", subscription_needs_remandate=False)
    fake = MagicMock()
    fake.subscription.edit.return_value = {}
    with patch.object(SubscriptionService, "_get_or_create_plan", return_value="plan_x"), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        result = SubscriptionService.reconcile_plan_amount(db, org.id)
    db.refresh(org)
    assert result == "upgraded"
    assert org.paid_location_quota == 6           # drift closed
    assert org.subscription_payment_mode == "card"


def test_reconcile_plan_amount_upi_needs_remandate(db):
    org = _mk_org(db, subscription_status="active", razorpay_subscription_id="sub_u",
                  location_quota=6, paid_location_quota=4, billing_cycle="monthly",
                  plan_tier="basic", subscription_needs_remandate=False,
                  ai_credits_reset_date=datetime(2026, 8, 1, tzinfo=timezone.utc))
    fake = MagicMock()
    fake.subscription.edit.side_effect = Exception("The payment mode is upi for this subscription")
    with patch.object(SubscriptionService, "_get_or_create_plan", return_value="plan_x"), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        result = SubscriptionService.reconcile_plan_amount(db, org.id)
    db.refresh(org)
    assert result == "needs_remandate"
    assert org.subscription_needs_remandate is True
    assert org.paid_location_quota == 4           # stays frozen at mandate level
    assert org.remandate_due_at is not None


def test_reconcile_plan_amount_noop_when_no_drift(db):
    org = _mk_org(db, subscription_status="active", razorpay_subscription_id="sub_n",
                  location_quota=4, paid_location_quota=4, subscription_needs_remandate=False)
    assert SubscriptionService.reconcile_plan_amount(db, org.id) == "noop"


# --- Fix 3: re-mandate reuse / cancel instead of stacking -------------------

def test_remandate_reuses_pending_mandate(db):
    org = _mk_org(db, subscription_status="active", razorpay_subscription_id="sub_old",
                  pending_remandate_subscription_id="sub_pending", subscription_needs_remandate=True,
                  location_quota=5, billing_cycle="monthly", plan_tier="basic")
    fake = MagicMock()
    fake.subscription.fetch.return_value = {"id": "sub_pending", "status": "created",
                                            "notes": {"location_count": "5"}}
    with patch.object(SubscriptionService, "ensure_razorpay_customer", return_value="cust_1"), \
         patch.object(SubscriptionService, "_get_or_create_plan", return_value="plan_5"), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        sub = SubscriptionService.create_remandate_subscription(db, org.id, "Org", "e@e.com")
    assert sub["id"] == "sub_pending"
    fake.subscription.create.assert_not_called()   # reused, did not stack a new mandate


def test_remandate_cancels_stale_mandate_and_creates_new(db):
    org = _mk_org(db, subscription_status="active", razorpay_subscription_id="sub_old",
                  pending_remandate_subscription_id="sub_stale", subscription_needs_remandate=True,
                  location_quota=5, billing_cycle="monthly", plan_tier="basic")
    fake = MagicMock()
    # Stale: still pending but quota no longer matches -> cancel + recreate.
    fake.subscription.fetch.return_value = {"id": "sub_stale", "status": "created",
                                            "notes": {"location_count": "3"}}
    fake.subscription.create.return_value = {"id": "sub_new"}
    with patch.object(SubscriptionService, "ensure_razorpay_customer", return_value="cust_1"), \
         patch.object(SubscriptionService, "_get_or_create_plan", return_value="plan_5"), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        sub = SubscriptionService.create_remandate_subscription(db, org.id, "Org", "e@e.com")
    db.refresh(org)
    assert sub["id"] == "sub_new"
    fake.subscription.cancel.assert_called_once()
    assert org.pending_remandate_subscription_id == "sub_new"


# --- Fix 4: add-ons blocked while a re-mandate is pending --------------------

def test_addon_blocked_during_pending_remandate(db):
    org = _mk_org(db, subscription_status="active", razorpay_subscription_id="sub_x",
                  location_quota=3, paid_location_quota=3, billing_cycle="monthly",
                  plan_tier="basic", subscription_needs_remandate=True)
    loc = Location(organization_id=org.id, google_location_id="loc_p",
                   location_name="Pending", sync_status="Synced", billing_status="pending_payment")
    db.add(loc)
    db.commit()
    db.refresh(loc)
    with pytest.raises(HTTPException) as exc:
        SubscriptionService.create_location_addon_order(db, org.id, "Org", "e@e.com", [loc.id])
    assert exc.value.status_code == 409
    assert "remandate_pending" in exc.value.detail


# --- Fix 5: partial unlock flagged for refund review ------------------------

def test_addon_partial_unlock_flagged_for_refund(db):
    org = _mk_org(db, subscription_status="active", razorpay_subscription_id="sub_a",
                  location_quota=4, monthly_ai_credits_balance=120, billing_cycle="monthly",
                  plan_tier="basic")
    loc = Location(organization_id=org.id, google_location_id="loc_p1",
                   location_name="Pending", sync_status="Synced", billing_status="pending_payment")
    db.add(loc)
    db.commit()
    db.refresh(loc)

    # Billed for 2 (added="2") but only one id is actually pending -> granted=1 < 2.
    payload = {"payload": {"payment": {"entity": {
        "id": "pay_partial", "amount": 250000, "currency": "INR", "order_id": "order_p",
        "notes": {"organization_id": str(org.id), "type": "location_addon",
                  "added": "2", "location_ids": f"{loc.id},99999"},
    }}}}
    with patch.object(SubscriptionService, "update_subscription_plan_for_quota"), \
         patch("app.worker.celery.send_task"):
        WebhookService._handle_payment_captured(db, payload)
        db.commit()

    txn = db.query(BillingTransaction).filter_by(razorpay_payment_id="pay_partial").first()
    assert txn.status == "needs_refund_review"
    db.refresh(loc)
    assert loc.billing_status == "active"


# --- Fix 6: cumulative refund lock + full-refund cancels the mandate --------

def test_chunked_full_refund_locks_and_cancels(db):
    org = _mk_org(db, subscription_status="active", razorpay_subscription_id="sub_r",
                  location_quota=5)
    db.add(BillingTransaction(organization_id=org.id, transaction_type="location_addon",
                              amount_paise=10000, currency="INR", status="success",
                              razorpay_payment_id="pay_r", razorpay_order_id="order_r",
                              razorpay_subscription_id="sub_r"))
    db.commit()

    fake = MagicMock()
    with patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        # First partial 6000 of 10000 -> not full, no lock.
        WebhookService._handle_refund(db, {"payload": {"refund": {"entity": {
            "id": "rfnd_1", "payment_id": "pay_r", "amount": 6000, "currency": "INR"}}}})
        db.commit()
        db.refresh(org)
        assert org.subscription_status == "active"
        fake.subscription.cancel.assert_not_called()

        # Second 4000 -> cumulative 10000 == original -> full -> lock + cancel mandate.
        WebhookService._handle_refund(db, {"payload": {"refund": {"entity": {
            "id": "rfnd_2", "payment_id": "pay_r", "amount": 4000, "currency": "INR"}}}})
        db.commit()
        db.refresh(org)
        assert org.subscription_status == "locked"
        fake.subscription.cancel.assert_called_once_with("sub_r", {"cancel_at_cycle_end": 0})

        # Re-delivery of rfnd_2 is a no-op (idempotent): no further cancel, amount unchanged.
        WebhookService._handle_refund(db, {"payload": {"refund": {"entity": {
            "id": "rfnd_2", "payment_id": "pay_r", "amount": 4000, "currency": "INR"}}}})
        db.commit()

    reversal = db.query(BillingTransaction).filter_by(
        razorpay_payment_id="pay_r", transaction_type="refund_reversal").one()
    assert reversal.amount_paise == 10000          # cumulative, not double-counted
    assert fake.subscription.cancel.call_count == 1


def test_topup_refund_claws_credits_proportionally(db):
    org = _mk_org(db, subscription_status="active", topup_ai_credits_balance=500)
    db.add(BillingTransaction(organization_id=org.id, transaction_type="topup_charge",
                              credits=500, amount_paise=49900, currency="INR", status="success",
                              razorpay_payment_id="pay_t", razorpay_order_id="order_t"))
    db.commit()
    fake = MagicMock()
    with patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        WebhookService._handle_refund(db, {"payload": {"refund": {"entity": {
            "id": "rfnd_t1", "payment_id": "pay_t", "amount": 24950, "currency": "INR"}}}})
        db.commit()
    db.refresh(org)
    assert org.topup_ai_credits_balance == 250     # half refunded -> half the credits clawed


# --- Fix 7: pending trial cap ------------------------------------------------

def test_pending_trial_locked_after_cap():
    now = datetime.now(timezone.utc)
    cap = plan_config.PENDING_TRIAL_MAX_DAYS
    fresh = Organization(name="fresh", subscription_status="trial", trial_ends_at=None,
                         created_at=now - timedelta(days=cap - 1))
    stale = Organization(name="stale", subscription_status="trial", trial_ends_at=None,
                         created_at=now - timedelta(days=cap + 1))
    assert EntitlementService.is_org_locked(fresh) is False
    assert EntitlementService.is_org_locked(stale) is True


# --- Fix 8: credit reserve / refund -----------------------------------------

def test_reserve_debits_and_blocks_overspend(db):
    org = _mk_org(db, subscription_status="active", monthly_ai_credits_balance=2,
                  topup_ai_credits_balance=1)
    CreditService.reserve(db, org.id, 2)           # debits 2 from monthly
    db.refresh(org)
    assert org.monthly_ai_credits_balance == 0
    assert org.topup_ai_credits_balance == 1

    with pytest.raises(HTTPException) as exc:      # only 1 left, can't afford 2
        CreditService.reserve(db, org.id, 2)
    assert exc.value.status_code == 402

    CreditService.refund(db, org.id, 2)            # work failed -> give them back
    db.refresh(org)
    assert org.monthly_ai_credits_balance == 2


def test_reserve_blocks_locked_org(db):
    org = _mk_org(db, subscription_status="locked", monthly_ai_credits_balance=100)
    with pytest.raises(HTTPException) as exc:
        CreditService.reserve(db, org.id, 1)
    assert exc.value.status_code == 402


# --- Owner chooses which locations fill the paid slots (free within quota) ---

import pytest as _pytest  # noqa: E402


@_pytest.fixture(name="client")
def fixture_client(db):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _admin_client(db, client, org):
    from app.models.user import User
    from app.core.security import create_access_token
    user = User(email=f"admin{org.id}@t.com", name="Admin", google_id=f"g{org.id}",
                role="Admin", is_active=True, organization_id=org.id)
    db.add(user)
    db.commit()
    db.refresh(user)
    client.cookies.set("gmb_auth_token", create_access_token(user.email, token_version=user.token_version))
    return client


def _loc(db, org, name, status="active"):
    loc = Location(organization_id=org.id, google_location_id=f"g_{name}",
                   location_name=name, sync_status="Synced", billing_status=status)
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


def test_set_active_locations_lets_owner_choose_within_quota(db, client):
    org = _mk_org(db, subscription_status="active", location_quota=2)
    a = _loc(db, org, "A", "active")
    b = _loc(db, org, "B", "active")
    c = _loc(db, org, "C", "active")   # 3 active but quota is 2
    _admin_client(db, client, org)

    # Owner keeps A and C (not the oldest-two the system would have picked).
    resp = client.post("/api/v1/billing/locations/active", json={"location_ids": [a.id, c.id]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["active_location_count"] == 2
    assert body["pending_location_count"] == 1
    for loc in (a, b, c):
        db.refresh(loc)
    assert a.billing_status == "active"
    assert c.billing_status == "active"
    assert b.billing_status == "pending_payment"   # the one they didn't choose


def test_set_active_locations_reactivates_a_pending_one_free(db, client):
    org = _mk_org(db, subscription_status="active", location_quota=1)
    a = _loc(db, org, "A", "active")
    b = _loc(db, org, "B", "pending_payment")
    _admin_client(db, client, org)

    # Swap: activate B (currently pending), which drops A to pending — net count unchanged.
    with patch("app.worker.celery.send_task") as send:
        resp = client.post("/api/v1/billing/locations/active", json={"location_ids": [b.id]})
    assert resp.status_code == 200, resp.text
    db.refresh(a)
    db.refresh(b)
    assert b.billing_status == "active"
    assert a.billing_status == "pending_payment"
    assert send.called   # freshly-activated location is queued for sync


def test_set_active_locations_cooldown_blocks_rapid_swaps(db, client):
    org = _mk_org(db, subscription_status="active", location_quota=2)
    a = _loc(db, org, "A", "active")
    b = _loc(db, org, "B", "active")
    c = _loc(db, org, "C", "active")   # 3 active, quota 2
    _admin_client(db, client, org)

    with patch("app.worker.celery.send_task"):
        first = client.post("/api/v1/billing/locations/active", json={"location_ids": [a.id, b.id]})
        assert first.status_code == 200, first.text
        # A different selection immediately after is throttled.
        second = client.post("/api/v1/billing/locations/active", json={"location_ids": [a.id, c.id]})
    assert second.status_code == 429
    assert "reassign_cooldown" in second.json()["detail"]


def test_set_active_resaving_same_selection_is_free_noop(db, client):
    org = _mk_org(db, subscription_status="active", location_quota=2)
    a = _loc(db, org, "A", "active")
    b = _loc(db, org, "B", "active")
    c = _loc(db, org, "C", "pending_payment")
    _admin_client(db, client, org)

    with patch("app.worker.celery.send_task"):
        # Saving the current set (A,B) changes nothing -> must NOT start a cooldown.
        noop = client.post("/api/v1/billing/locations/active", json={"location_ids": [a.id, b.id]})
        assert noop.status_code == 200, noop.text
        db.refresh(org)
        assert org.last_location_reassign_at is None   # no cooldown consumed
        # A real change right after is therefore still allowed.
        real = client.post("/api/v1/billing/locations/active", json={"location_ids": [a.id, c.id]})
    assert real.status_code == 200, real.text
    db.refresh(org)
    assert org.last_location_reassign_at is not None


def test_set_active_locations_over_quota_rejected(db, client):
    org = _mk_org(db, subscription_status="active", location_quota=1)
    a = _loc(db, org, "A", "active")
    b = _loc(db, org, "B", "active")
    _admin_client(db, client, org)

    resp = client.post("/api/v1/billing/locations/active", json={"location_ids": [a.id, b.id]})
    assert resp.status_code == 409
    assert "exceeds_quota" in resp.json()["detail"]
