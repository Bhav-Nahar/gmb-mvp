"""Card-required trial: activation (#2) and mandate-revoke safeguards (#3).

Uses the same in-memory sqlite + mocked-Razorpay harness as test_billing_fixes.
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
from app.models.oauth_account import OAuthAccount
from app.models.location import Location
from app.models.review import Review
from app.services.onboarding_audit import compute_audit_summary
from app.services.billing.subscription_service import SubscriptionService, normalize_phone
from app.services.billing.webhook_service import WebhookService
from app.services.billing.entitlement_service import EntitlementService
from app.services.billing.credit_service import CreditService
from app.core.security import create_access_token
from app.db.session import get_db


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(element, compiler, **kw):
    return "TEXT"


engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

NOW = datetime.now(timezone.utc)


@pytest.fixture(name="db")
def fixture_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(name="client")
def fixture_client(db):
    from fastapi.testclient import TestClient
    from app.main import app

    def _o():
        yield db
    app.dependency_overrides[get_db] = _o
    yield TestClient(app)
    app.dependency_overrides.clear()


def _mk_org(db, status="trial", trial_ends_at=None, sub_id=None, quota=1):
    org = Organization(
        name="t", subscription_status=status, plan="trial", plan_tier="basic",
        trial_ends_at=trial_ends_at, razorpay_subscription_id=sub_id,
        location_quota=quota, billing_cycle="monthly",
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _sub_payload(org, **entity):
    entity.setdefault("notes", {"organization_id": str(org.id)})
    return {"payload": {"subscription": {"entity": entity}}}


# ---- #2 activation ----------------------------------------------------------

def test_activate_trial_authenticated_starts_clock(db):
    org = _mk_org(db, status="trial", trial_ends_at=None, sub_id="sub_1")
    charge_at = int((NOW + timedelta(days=7)).timestamp())
    sub = {"status": "authenticated", "payment_method": "upi", "charge_at": charge_at,
           "notes": {"organization_id": str(org.id)}}

    assert SubscriptionService.activate_trial(db, org, sub) is True
    db.commit()

    assert org.subscription_status == "trial"          # still a trial, not charged
    assert org.trial_ends_at is not None
    # sqlite drops tzinfo (prod is tz-aware); compare on the naive wall-clock value.
    expected = datetime.fromtimestamp(charge_at, tz=timezone.utc).replace(tzinfo=None)
    assert abs((org.trial_ends_at.replace(tzinfo=None) - expected).total_seconds()) < 2
    assert org.subscription_payment_mode == "upi"
    # (premium-unlock semantics for a running trial are asserted in
    # test_onboarding_entitlement.py, which uses tz-aware datetimes — sqlite here
    # stores naive values, which would false-fail the is_org_locked comparison.)


def test_activate_trial_is_idempotent(db):
    ends = NOW + timedelta(days=7)
    org = _mk_org(db, status="trial", trial_ends_at=ends, sub_id="sub_1")
    # Re-delivery / confirm+webhook race: clock already set -> no-op, still True.
    assert SubscriptionService.activate_trial(db, org, {"status": "authenticated"}) is True
    # unchanged (sqlite stores naive; compare wall-clock)
    assert org.trial_ends_at.replace(tzinfo=None) == ends.replace(tzinfo=None)


def test_activate_trial_ignores_unapproved_mandate(db):
    org = _mk_org(db, status="trial", trial_ends_at=None, sub_id="sub_1")
    # Mandate not approved yet -> don't start the trial.
    assert SubscriptionService.activate_trial(db, org, {"status": "created"}) is False
    assert org.trial_ends_at is None


def test_activate_trial_from_subscription_fetches_and_starts(db):
    org = _mk_org(db, status="trial", trial_ends_at=None, sub_id="sub_1")
    fake = MagicMock()
    fake.subscription.fetch.return_value = {
        "id": "sub_1", "status": "authenticated", "payment_method": "card",
        "charge_at": int((NOW + timedelta(days=7)).timestamp()),
        "notes": {"organization_id": str(org.id)},
    }
    with patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        assert SubscriptionService.activate_trial_from_subscription(db, org.id) is True
    db.refresh(org)
    assert org.trial_ends_at is not None
    assert org.subscription_payment_mode == "card"


# ---- #3 mandate-revoke safeguards ------------------------------------------

def test_cancel_mid_trial_locks(db):
    org = _mk_org(db, status="trial", trial_ends_at=NOW + timedelta(days=5), sub_id="sub_1")
    with patch.object(settings, "CARD_REQUIRED_ONBOARDING", True):
        WebhookService._handle_subscription_cancelled(db, _sub_payload(org, id="sub_1"))
    db.commit()
    db.refresh(org)
    assert org.subscription_status == "locked"
    assert org.trial_ends_at is None
    assert EntitlementService.is_premium_unlocked(org) is False


def test_cancel_while_active_keeps_paid_period(db):
    org = _mk_org(db, status="active", sub_id="sub_1")
    current_end = int((NOW + timedelta(days=10)).timestamp())
    WebhookService._handle_subscription_cancelled(db, _sub_payload(org, id="sub_1", current_end=current_end))
    db.commit()
    db.refresh(org)
    # Unchanged legacy behavior: stays active until the paid period ends.
    assert org.subscription_status == "active"
    assert org.subscription_ends_at is not None


class _FakeLock:
    def acquire(self, blocking=False):
        return True

    def release(self):
        pass


class _FakeRedis:
    def lock(self, *a, **kw):
        return _FakeLock()


def test_expired_trial_reconciles_before_locking(db):
    """A card-backed trial whose first charge landed (but whose webhook was missed)
    must reconcile to active on expiry sweep — never get locked."""
    paid = _mk_org(db, status="trial", trial_ends_at=NOW - timedelta(days=1), sub_id="sub_paid")
    unpaid = _mk_org(db, status="trial", trial_ends_at=NOW - timedelta(days=1), sub_id=None)

    fake = MagicMock()
    fake.subscription.fetch.return_value = {
        "id": "sub_paid", "status": "active",
        "current_end": int((NOW + timedelta(days=29)).timestamp()),
        "notes": {"organization_id": str(paid.id), "location_count": "1", "plan_tier": "basic"},
    }
    with patch("app.services.billing.entitlement_service.get_redis", return_value=_FakeRedis()), \
         patch.object(settings, "CARD_REQUIRED_ONBOARDING", True), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        EntitlementService.transition_expired_subscriptions(db)

    db.refresh(paid)
    db.refresh(unpaid)
    assert paid.subscription_status == "active"      # reconciled, NOT locked
    assert unpaid.subscription_status == "past_due"  # no mandate -> normal grace path


def test_expired_trial_reconciles_before_locking_without_card_onboarding(db):
    """Regression: the reconcile-before-lock safeguard used to be gated on
    CARD_REQUIRED_ONBOARDING, so with that flag off a subscriber whose
    subscription.charged webhook was missed got locked without Razorpay ever being
    asked. Whether the card was taken up front says nothing about whether the charge
    landed, so the safeguard must hold with the flag off too."""
    paid = _mk_org(db, status="trial", trial_ends_at=NOW - timedelta(days=1), sub_id="sub_paid_nocard")

    fake = MagicMock()
    fake.subscription.fetch.return_value = {
        "id": "sub_paid_nocard", "status": "active",
        "current_end": int((NOW + timedelta(days=29)).timestamp()),
        "notes": {"organization_id": str(paid.id), "location_count": "1", "plan_tier": "basic"},
    }
    with patch("app.services.billing.entitlement_service.get_redis", return_value=_FakeRedis()), \
         patch.object(settings, "CARD_REQUIRED_ONBOARDING", False), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        EntitlementService.transition_expired_subscriptions(db)

    db.refresh(paid)
    assert paid.subscription_status == "active"  # reconciled, NOT locked


def test_stuck_onboarding_with_mandate_gets_activated_by_sweep(db):
    """Fix #3: both /confirm and the authenticated webhook were missed, so the org sits
    onboarding (trial_ends_at NULL) with an authenticated mandate. The sweep must start
    its trial, not leave it blurred until the day-7 charge."""
    org = _mk_org(db, status="trial", trial_ends_at=None, sub_id="sub_auth")
    fake = MagicMock()
    fake.subscription.fetch.return_value = {
        "id": "sub_auth", "status": "authenticated", "payment_method": "card",
        "charge_at": int((NOW + timedelta(days=7)).timestamp()),
        "notes": {"organization_id": str(org.id)},
    }
    with patch("app.services.billing.entitlement_service.get_redis", return_value=_FakeRedis()), \
         patch.object(settings, "CARD_REQUIRED_ONBOARDING", True), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        EntitlementService.transition_expired_subscriptions(db)
    db.refresh(org)
    assert org.trial_ends_at is not None          # trial started
    assert org.subscription_status == "trial"     # not charged, not locked


# ---- #4 premium/AI gating ---------------------------------------------------

def test_credit_reserve_blocked_during_onboarding(db):
    org = _mk_org(db, status="trial", trial_ends_at=None)  # onboarding, pre-payment
    org.monthly_ai_credits_balance = 100
    db.commit()
    # is_org_locked patched False to isolate the onboarding gate from sqlite's tz-naive
    # datetime comparison (prod columns are tz-aware); onboarding-vs-not is what we assert.
    with patch.object(settings, "CARD_REQUIRED_ONBOARDING", True), \
         patch.object(EntitlementService, "is_org_locked", return_value=False):
        with pytest.raises(HTTPException) as ei:
            CreditService.reserve(db, org.id, 1)
    assert ei.value.status_code == 402
    assert "trial_required" in ei.value.detail
    db.refresh(org)
    assert org.monthly_ai_credits_balance == 100  # nothing spent


def test_credit_reserve_allowed_during_active_trial(db):
    org = _mk_org(db, status="trial", trial_ends_at=NOW + timedelta(days=7))
    org.monthly_ai_credits_balance = 100
    db.commit()
    with patch.object(settings, "CARD_REQUIRED_ONBOARDING", True), \
         patch.object(EntitlementService, "is_org_locked", return_value=False):
        CreditService.reserve(db, org.id, 1)   # running trial -> allowed
    db.refresh(org)
    assert org.monthly_ai_credits_balance == 99


# ---- #5 trial-abuse guard ---------------------------------------------------

def _add_owner(db, org, email, google_id, phone=None):
    # User.google_id is unique per user (use email); the SHARED identity the abuse guard
    # dedupes on is OAuthAccount.provider_account_id (google_id arg).
    u = User(email=email, name="o", google_id=email, role="Owner",
             organization_id=org.id, phone=phone)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(OAuthAccount(user_id=u.id, provider="google", provider_account_id=google_id,
                        access_token="x", expires_at=NOW + timedelta(days=1)))
    db.commit()
    return u


def test_abuse_guard_blocks_repeat_google_account(db):
    # Org A already consumed a trial with google id G.
    used = _mk_org(db, status="trial", trial_ends_at=NOW + timedelta(days=3))
    _add_owner(db, used, "a@x.com", "G-123")
    # Org B (fresh onboarding) with the SAME google id tries to start a trial.
    fresh = _mk_org(db, status="trial", trial_ends_at=None)
    _add_owner(db, fresh, "b@x.com", "G-123")
    with patch.object(settings, "CARD_REQUIRED_ONBOARDING", True):
        with pytest.raises(HTTPException) as ei:
            SubscriptionService.assert_trial_not_abused(db, fresh.id)
    assert ei.value.status_code == 409


def test_abuse_guard_blocks_repeat_phone(db):
    used = _mk_org(db, status="active", trial_ends_at=NOW - timedelta(days=1))
    _add_owner(db, used, "a2@x.com", "G-A", phone="+919000000000")
    fresh = _mk_org(db, status="trial", trial_ends_at=None)
    _add_owner(db, fresh, "b2@x.com", "G-B")
    with patch.object(settings, "CARD_REQUIRED_ONBOARDING", True):
        with pytest.raises(HTTPException) as ei:
            SubscriptionService.assert_trial_not_abused(db, fresh.id, phone="+919000000000")
    assert ei.value.status_code == 409


def test_audit_summary_counts_real_findings(db):
    org = _mk_org(db, status="trial", trial_ends_at=None)
    # One active location missing a website (profile gap), rating 3.5 (below floor).
    loc = Location(organization_id=org.id, google_location_id="loc/1", location_name="A",
                   billing_status="active", sync_status="Synced",
                   average_rating=3.5, total_reviews=3, website=None,
                   description="d", business_hours={"x": 1})
    db.add(loc)
    db.commit()
    db.refresh(loc)

    def _rev(rid, rating, replied):
        return Review(organization_id=org.id, location_id=loc.id, provider="google",
                      provider_review_id=rid, reviewer_name="r", rating=rating,
                      is_replied=replied, review_created_at=NOW, is_deleted=False)
    db.add_all([_rev("r1", 5, False), _rev("r2", 1, False), _rev("r3", 4, True)])
    db.commit()

    s = compute_audit_summary(db, org.id)
    assert s["locations"] == 1
    assert s["unanswered_reviews"] == 2          # r1, r2
    assert s["negative_unanswered"] == 1         # r2
    assert s["profile_gaps"] == 1                # missing website
    assert s["avg_rating"] == 3.5
    # 4 categories triggered: negative-unanswered, unanswered, profile gap, low rating.
    assert s["critical_issues"] == 4
    assert len(s["issues"]) == 4


def test_audit_summary_clean_profile_has_no_issues(db):
    org = _mk_org(db, status="trial", trial_ends_at=None)
    loc = Location(organization_id=org.id, google_location_id="loc/2", location_name="B",
                   billing_status="active", sync_status="Synced",
                   average_rating=4.8, total_reviews=1, website="w", description="d",
                   business_hours={"x": 1})
    db.add(loc)
    db.commit()
    db.refresh(loc)
    db.add(Review(organization_id=org.id, location_id=loc.id, provider="google",
                  provider_review_id="ok", reviewer_name="r", rating=5,
                  is_replied=True, review_created_at=NOW, is_deleted=False))
    db.commit()
    s = compute_audit_summary(db, org.id)
    assert s["critical_issues"] == 0
    assert s["issues"] == []


def test_normalize_phone_canonicalizes_all_formats():
    for raw in ["9876543210", "98765 43210", "+91-9876543210", "+919876543210",
                "091 98765 43210", "0919876543210"]:
        assert normalize_phone(raw) == "+919876543210", raw
    assert normalize_phone("123") is None
    assert normalize_phone(None) is None
    assert normalize_phone("") is None


def test_abuse_guard_blocks_repeat_phone_across_formats(db):
    """Fix: formatting must not defeat the phone dedup. Org A consumed a trial with the
    canonical +91 number; a fresh org submitting the SAME number differently formatted
    must still be blocked."""
    used = _mk_org(db, status="active", trial_ends_at=NOW - timedelta(days=1))
    _add_owner(db, used, "fmt-a@x.com", "G-FA", phone="+919876543210")  # stored canonical
    fresh = _mk_org(db, status="trial", trial_ends_at=None)
    _add_owner(db, fresh, "fmt-b@x.com", "G-FB")
    with patch.object(settings, "CARD_REQUIRED_ONBOARDING", True):
        with pytest.raises(HTTPException) as ei:
            SubscriptionService.assert_trial_not_abused(db, fresh.id, phone="98765 43210")
    assert ei.value.status_code == 409


def test_abuse_guard_allows_first_trial(db):
    fresh = _mk_org(db, status="trial", trial_ends_at=None)
    _add_owner(db, fresh, "new@x.com", "G-NEW", phone="+919111111111")
    with patch.object(settings, "CARD_REQUIRED_ONBOARDING", True):
        SubscriptionService.assert_trial_not_abused(db, fresh.id, phone="+919111111111")  # no raise


# ---- paying early must activate on /confirm, not wait for the webhook -------

def test_early_payment_during_trial_activates_immediately(db, client):
    """A trial org that pays before day 7 must be ACTIVE the moment /confirm returns.

    /confirm used to route every status=='trial' org into activate_trial_from_subscription,
    which early-returns for a running clock without contacting Razorpay — so the charge
    stayed unapplied until the subscription.charged webhook (or the 30-min sweep)."""
    org = _mk_org(db, status="trial", trial_ends_at=NOW + timedelta(days=5), sub_id="sub_paid")
    u = User(email="early@x.com", name="e", google_id="g_early", role="Owner",
             is_active=True, organization_id=org.id)
    db.add(u)
    db.commit()
    db.refresh(u)
    client.cookies.set("gmb_auth_token", create_access_token(u.email, token_version=u.token_version))

    fake = MagicMock()
    fake.utility.verify_subscription_payment_signature.return_value = True
    # Razorpay charged the first cycle straight away (no start_at on an early payment).
    fake.subscription.fetch.return_value = {
        "id": "sub_paid", "status": "active", "payment_method": "card",
        "current_end": int((NOW + timedelta(days=30)).timestamp()),
        "notes": {"organization_id": str(org.id), "location_count": "2",
                  "plan_tier": "basic", "credits": "60"},
    }
    fake.payment.fetch.return_value = {"id": "pay_1", "amount": 471764, "currency": "INR"}
    with patch.object(settings, "CARD_REQUIRED_ONBOARDING", True), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        r = client.post("/api/v1/billing/confirm", json={
            "razorpay_payment_id": "pay_1", "razorpay_signature": "sig",
            "razorpay_subscription_id": "sub_paid",
        })
    assert r.status_code == 200, r.text
    assert r.json()["activated"] is True
    db.refresh(org)
    assert org.subscription_status == "active"   # immediately, not on the webhook
    assert org.trial_ends_at is None             # trial replaced by the paid cycle
    assert org.location_quota == 2               # entitlements from the subscription notes


def test_onboarding_confirm_still_starts_the_trial(db, client):
    """The onboarding path must be untouched: mandate approved, nothing charged yet."""
    org = _mk_org(db, status="trial", trial_ends_at=None, sub_id="sub_onb")
    u = User(email="onb@x.com", name="o", google_id="g_onb", role="Owner",
             is_active=True, organization_id=org.id)
    db.add(u)
    db.commit()
    db.refresh(u)
    client.cookies.set("gmb_auth_token", create_access_token(u.email, token_version=u.token_version))

    fake = MagicMock()
    fake.utility.verify_subscription_payment_signature.return_value = True
    fake.subscription.fetch.return_value = {
        "id": "sub_onb", "status": "authenticated", "payment_method": "card",
        "charge_at": int((NOW + timedelta(days=7)).timestamp()),
        "notes": {"organization_id": str(org.id)},
    }
    with patch.object(settings, "CARD_REQUIRED_ONBOARDING", True), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        r = client.post("/api/v1/billing/confirm", json={
            "razorpay_payment_id": "pay_2", "razorpay_signature": "sig",
            "razorpay_subscription_id": "sub_onb",
        })
    assert r.status_code == 200, r.text
    db.refresh(org)
    assert org.subscription_status == "trial"
    assert org.trial_ends_at is not None         # clock started, no charge applied


def test_upi_early_payment_activates_before_the_debit_lands(db, client):
    """Pay-now with UPI Autopay: the bank approves instantly, the debit lands later.
    The customer must be active immediately — a failed debit is caught later by the
    subscription.halted / .pending webhooks (past_due + grace)."""
    org = _mk_org(db, status="trial", trial_ends_at=NOW + timedelta(days=4), sub_id="sub_upi")
    u = User(email="upi@x.com", name="u", google_id="g_upi", role="Owner",
             is_active=True, organization_id=org.id)
    db.add(u)
    db.commit()
    db.refresh(u)
    client.cookies.set("gmb_auth_token", create_access_token(u.email, token_version=u.token_version))

    fake = MagicMock()
    fake.utility.verify_subscription_payment_signature.return_value = True
    fake.subscription.fetch.return_value = {
        "id": "sub_upi", "status": "authenticated", "payment_method": "upi",
        "notes": {"organization_id": str(org.id), "location_count": "1",
                  "plan_tier": "basic", "credits": "30"},
    }
    fake.payment.fetch.return_value = {"id": "pay_upi", "amount": 235882, "currency": "INR"}
    with patch.object(settings, "CARD_REQUIRED_ONBOARDING", True), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        r = client.post("/api/v1/billing/confirm", json={
            "razorpay_payment_id": "pay_upi", "razorpay_signature": "sig",
            "razorpay_subscription_id": "sub_upi",
        })
    assert r.status_code == 200, r.text
    assert r.json()["activated"] is True
    db.refresh(org)
    assert org.subscription_status == "active"
    # ...and the charge shows in billing history right away, not only on the webhook.
    from app.models.billing_transaction import BillingTransaction
    row = db.query(BillingTransaction).filter(
        BillingTransaction.razorpay_payment_id == "pay_upi").first()
    assert row is not None and row.amount_paise == 235882


def test_scheduled_trial_mandate_does_not_grant_paid_access(db, client):
    """Guard: an authenticated mandate whose first debit is days out (a trial) must NOT
    be treated as a payment, even on the pay-now path."""
    org = _mk_org(db, status="past_due", trial_ends_at=None, sub_id="sub_sched")
    org.grace_period_ends_at = NOW + timedelta(days=2)
    db.commit()
    fake = MagicMock()
    fake.subscription.fetch.return_value = {
        "id": "sub_sched", "status": "authenticated",
        "start_at": int((NOW + timedelta(days=7)).timestamp()),
        "notes": {"organization_id": str(org.id)},
    }
    with patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        assert SubscriptionService.activate_paid_now(db, org.id, "pay_x") is False
    db.refresh(org)
    assert org.subscription_status == "past_due"


def test_upi_pay_now_is_not_mistaken_for_a_deferred_trial_mandate(db, client):
    """Regression, seen live: a real UPI pay-now subscription comes back 'authenticated'
    with charge_at set to the NEXT billing date (a month out) and start_at = now. Reading
    charge_at made that look like a scheduled trial mandate, so the payer stayed on their
    trial with no receipt until a webhook arrived — which never came in dev at all."""
    org = _mk_org(db, status="trial", trial_ends_at=NOW + timedelta(days=6), sub_id="sub_upi_now")
    u = User(email="upinow@x.com", name="u", google_id="g_upinow", role="Owner",
             is_active=True, organization_id=org.id)
    db.add(u)
    db.commit()
    db.refresh(u)
    client.cookies.set("gmb_auth_token", create_access_token(u.email, token_version=u.token_version))

    fake = MagicMock()
    fake.utility.verify_subscription_payment_signature.return_value = True
    fake.subscription.fetch.return_value = {
        "id": "sub_upi_now", "status": "authenticated", "payment_method": "upi",
        "start_at": int(NOW.timestamp()),                                  # billed from now
        "charge_at": int((NOW + timedelta(days=31)).timestamp()),           # NEXT cycle
        "current_end": int((NOW + timedelta(days=31)).timestamp()),
        "notes": {"organization_id": str(org.id), "location_count": "2",
                  "plan_tier": "basic", "credits": "60"},
    }
    fake.payment.fetch.return_value = {"id": "pay_upi_now", "amount": 399800, "currency": "INR"}
    with patch.object(settings, "CARD_REQUIRED_ONBOARDING", True), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        r = client.post("/api/v1/billing/confirm", json={
            "razorpay_payment_id": "pay_upi_now", "razorpay_signature": "sig",
            "razorpay_subscription_id": "sub_upi_now",
        })
    assert r.status_code == 200, r.text
    assert r.json()["activated"] is True
    db.refresh(org)
    assert org.subscription_status == "active"
    assert org.trial_ends_at is None


def test_a_paid_count_of_one_activates_whatever_the_status_says(db):
    """Belt and braces: if Razorpay has debited at least once, the customer is paid."""
    org = _mk_org(db, status="trial", trial_ends_at=NOW + timedelta(days=3), sub_id="sub_paid_once")
    fake = MagicMock()
    fake.subscription.fetch.return_value = {
        "id": "sub_paid_once", "status": "authenticated", "paid_count": 1,
        "start_at": int((NOW + timedelta(days=7)).timestamp()),   # would otherwise be refused
        "notes": {"organization_id": str(org.id), "location_count": "1",
                  "plan_tier": "basic", "credits": "30"},
    }
    fake.payment.fetch.return_value = {"id": "pay_once", "amount": 235882, "currency": "INR"}
    with patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        assert SubscriptionService.activate_paid_now(db, org.id, "pay_once") is True
    db.refresh(org)
    assert org.subscription_status == "active"


def test_trial_length_is_capped_even_if_razorpay_reports_a_far_future_charge(db):
    """Same field confusion as the pay-now bug, other direction: if charge_at points at
    the next monthly cycle, the trial must still be TRIAL_DAYS, not a free month."""
    from app.core import plan_config

    org = _mk_org(db, status="trial", trial_ends_at=None, sub_id="sub_far")
    ok = SubscriptionService.activate_trial(db, org, {
        "status": "authenticated", "payment_method": "card",
        "charge_at": int((NOW + timedelta(days=31)).timestamp()),
    })
    assert ok is True
    cap = NOW + timedelta(days=plan_config.TRIAL_DAYS)
    assert org.trial_ends_at.replace(tzinfo=None) <= cap.replace(tzinfo=None) + timedelta(minutes=1)
