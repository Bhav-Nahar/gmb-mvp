"""Super-admin support actions and the trial-ending reminder.

These cover the operations support previously had to do by hand in the Razorpay
dashboard or with a SQL edit: reconcile a payment, cancel a mandate, extend a trial,
find a customer, and forgive the one-trial-per-identity guard.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.billing_transaction import BillingTransaction
from app.models.organization import Organization
from app.models.user import User
from app.services.billing.subscription_service import SubscriptionService

SUPER_EMAIL = "root@pinzo.io"
NOW = datetime.now(timezone.utc)


@pytest.fixture(name="client")
def fixture_client(db):
    from fastapi.testclient import TestClient
    from app.main import app

    def _o():
        yield db
    app.dependency_overrides[get_db] = _o
    yield TestClient(app)
    app.dependency_overrides.clear()


def _as_super(db, client):
    org = Organization(name="Pinzo HQ")
    db.add(org)
    db.commit()
    db.refresh(org)
    u = User(email=SUPER_EMAIL, name="root", google_id="g_root", role="Owner",
             is_active=True, organization_id=org.id)
    db.add(u)
    db.commit()
    db.refresh(u)
    client.cookies.set("gmb_auth_token", create_access_token(u.email, token_version=u.token_version))


def _org(db, **kw):
    base = dict(name="Client Co", subscription_status="active", location_quota=2,
                plan_tier="basic", billing_cycle="monthly")
    base.update(kw)
    org = Organization(**base)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _audit_actions(db, org_id):
    from app.models.audit_log import AuditLog
    return [a.action for a in db.query(AuditLog).filter(AuditLog.organization_id == org_id).all()]


# --- "I paid but I'm still locked" -------------------------------------------

def test_reconcile_applies_a_charge_razorpay_confirms(db, client):
    org = _org(db, subscription_status="locked", razorpay_subscription_id="sub_paid")
    fake = MagicMock()
    fake.subscription.fetch.return_value = {
        "id": "sub_paid", "status": "active",
        "current_end": int((NOW + timedelta(days=30)).timestamp()),
        "notes": {"organization_id": str(org.id), "location_count": "2",
                  "plan_tier": "basic", "credits": "60"},
    }
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        _as_super(db, client)
        r = client.post(f"/api/v1/admin/organizations/{org.id}/reconcile", json={"reason": "support"})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True
    db.refresh(org)
    assert org.subscription_status == "active"
    assert "superadmin.reconcile" in _audit_actions(db, org.id)


def test_reconcile_reports_honestly_when_nothing_was_charged(db, client):
    org = _org(db, subscription_status="locked", razorpay_subscription_id="sub_auth")
    fake = MagicMock()
    fake.subscription.fetch.return_value = {
        "id": "sub_auth", "status": "authenticated", "notes": {"organization_id": str(org.id)},
    }
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        _as_super(db, client)
        r = client.post(f"/api/v1/admin/organizations/{org.id}/reconcile", json={})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False
    db.refresh(org)
    assert org.subscription_status == "locked"          # nothing invented


def test_reconcile_without_a_subscription_is_a_400(db, client):
    org = _org(db, razorpay_subscription_id=None)
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL):
        _as_super(db, client)
        r = client.post(f"/api/v1/admin/organizations/{org.id}/reconcile", json={})
    assert r.status_code == 400


# --- cancellation ------------------------------------------------------------

def test_cancel_at_cycle_end_keeps_the_paid_period(db, client):
    org = _org(db, razorpay_subscription_id="sub_live")
    paid_through = int((NOW + timedelta(days=12)).timestamp())
    fake = MagicMock()
    fake.subscription.cancel.return_value = {"id": "sub_live", "status": "active",
                                             "current_end": paid_through}
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        _as_super(db, client)
        r = client.post(f"/api/v1/admin/organizations/{org.id}/cancel-subscription",
                        json={"reason": "customer asked"})
    assert r.status_code == 200, r.text
    assert fake.subscription.cancel.call_args[0][1] == {"cancel_at_cycle_end": 1}
    db.refresh(org)
    assert org.subscription_status == "active"           # still theirs until it lapses
    assert org.subscription_ends_at is not None
    assert "superadmin.cancel_subscription" in _audit_actions(db, org.id)


def test_cancel_immediately_locks_the_org(db, client):
    org = _org(db, razorpay_subscription_id="sub_live")
    fake = MagicMock()
    fake.subscription.cancel.return_value = {"id": "sub_live", "status": "cancelled"}
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        _as_super(db, client)
        r = client.post(f"/api/v1/admin/organizations/{org.id}/cancel-subscription",
                        json={"immediate": True, "reason": "refund"})
    assert r.status_code == 200, r.text
    assert fake.subscription.cancel.call_args[0][1] == {"cancel_at_cycle_end": 0}
    db.refresh(org)
    assert org.subscription_status == "locked"


def test_cancel_without_a_mandate_is_a_400(db, client):
    org = _org(db, razorpay_subscription_id=None)
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL):
        _as_super(db, client)
        r = client.post(f"/api/v1/admin/organizations/{org.id}/cancel-subscription", json={})
    assert r.status_code == 400


# --- extending a trial -------------------------------------------------------

def test_extend_trial_moves_the_clock_and_rearms_the_reminder(db, client):
    ends = NOW + timedelta(days=2)
    org = _org(db, subscription_status="trial", trial_ends_at=ends,
               razorpay_subscription_id=None)
    org.trial_reminder_sent_at = NOW
    db.commit()
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL):
        _as_super(db, client)
        r = client.post(f"/api/v1/admin/organizations/{org.id}/extend-trial",
                        json={"days": 7, "reason": "onboarding help"})
    assert r.status_code == 200, r.text
    db.refresh(org)
    assert org.trial_ends_at.replace(tzinfo=None) > ends.replace(tzinfo=None)
    assert org.trial_reminder_sent_at is None            # they get warned about the new date
    assert "superadmin.extend_trial" in _audit_actions(db, org.id)


def test_extend_trial_refuses_when_a_mandate_will_debit_anyway(db, client):
    """The trap this closes: Razorpay debits on the mandate's original schedule, so
    moving only our clock would charge the customer mid-'extension'."""
    org = _org(db, subscription_status="trial", trial_ends_at=NOW + timedelta(days=2),
               razorpay_subscription_id="sub_trial")
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL):
        _as_super(db, client)
        r = client.post(f"/api/v1/admin/organizations/{org.id}/extend-trial", json={"days": 7})
    assert r.status_code == 409
    assert "cannot be moved" in r.json()["detail"]


def test_extend_trial_refuses_a_non_trial(db, client):
    org = _org(db, subscription_status="active")
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL):
        _as_super(db, client)
        r = client.post(f"/api/v1/admin/organizations/{org.id}/extend-trial", json={})
    assert r.status_code == 409


# --- finding the customer ----------------------------------------------------

@pytest.mark.parametrize("term", ["client@acme.com", "9876543210", "+919876543210", "sub_findme"])
def test_search_finds_an_org_by_email_phone_or_subscription_id(db, client, term):
    org = _org(db, name="Findable Co", razorpay_subscription_id="sub_findme")
    db.add(User(email="client@acme.com", name="C", google_id="g_c", role="Owner",
                is_active=True, organization_id=org.id, phone="+919876543210"))
    db.commit()
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL):
        _as_super(db, client)
        r = client.get("/api/v1/admin/organizations", params={"q": term})
    assert r.status_code == 200, r.text
    assert org.id in [o["id"] for o in r.json()["items"]], f"{term} did not find the org"


# --- overrides and metrics ---------------------------------------------------

def test_allow_extra_trial_waives_the_abuse_guard(db):
    from app.models.oauth_account import OAuthAccount

    burned = _org(db, name="First go", subscription_status="locked")
    u1 = User(email="a@x.com", name="A", google_id="g_same", role="Owner",
              is_active=True, organization_id=burned.id, phone="+919999999999")
    db.add(u1)
    db.commit()
    db.add(OAuthAccount(user_id=u1.id, provider="google", provider_account_id="google-123",
                        access_token="tok1", expires_at=NOW + timedelta(days=30)))
    db.commit()

    second = _org(db, name="Second go", subscription_status="trial", trial_ends_at=None)
    u2 = User(email="b@x.com", name="B", google_id="g_new", role="Owner",
              is_active=True, organization_id=second.id, phone="+919999999999")
    db.add(u2)
    db.commit()
    db.add(OAuthAccount(user_id=u2.id, provider="google", provider_account_id="google-123",
                        access_token="tok2", expires_at=NOW + timedelta(days=30)))
    db.commit()

    with patch.object(settings, "CARD_REQUIRED_ONBOARDING", True):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            SubscriptionService.assert_trial_not_abused(db, second.id, "+919999999999")
        assert exc.value.status_code == 409

        second.allow_extra_trial = True
        db.commit()
        SubscriptionService.assert_trial_not_abused(db, second.id, "+919999999999")  # no raise


def test_metrics_report_mrr_and_conversion(db, client):
    paid = _org(db, name="Payer", subscription_status="active", location_quota=2,
                paid_location_quota=2)
    db.add(BillingTransaction(
        organization_id=paid.id, transaction_type="subscription_charge",
        amount_paise=471764, currency="INR", status="success",
        razorpay_payment_id="pay_metrics"))
    _org(db, name="Triallist", subscription_status="trial", trial_ends_at=NOW + timedelta(hours=20))
    db.commit()
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL):
        _as_super(db, client)
        r = client.get("/api/v1/admin/metrics")
    assert r.status_code == 200, r.text
    m = r.json()
    # Plan prices are stored GST-INCLUSIVE, so MRR is the sticker price, not price x1.18.
    assert m["mrr_paise"] == 2 * 199_900
    assert m["trials_ending_48h"] == 1
    assert m["ever_paid_organizations"] == 1
    assert m["trial_to_paid_pct"] > 0


# --- the trial-ending reminder ----------------------------------------------

def _run_reminders(db):
    """Run the sweep against the test database (the task opens its own session)."""
    from app import tasks
    maker = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    sent = []
    with patch.object(tasks, "SessionLocal", maker), \
         patch("app.services.email_service.send_email",
               side_effect=lambda to, subject, html: sent.append((to, subject, html)) or True):
        result = tasks.send_trial_ending_reminders_task()
    return result, sent


def test_trial_ending_reminder_is_sent_once_to_the_admins(db):
    org = _org(db, subscription_status="trial", trial_ends_at=NOW + timedelta(hours=20),
               razorpay_subscription_id=None)
    db.add(User(email="owner@acme.com", name="O", google_id="g_o", role="Owner",
                is_active=True, organization_id=org.id))
    db.add(User(email="viewer@acme.com", name="V", google_id="g_v", role="Viewer",
                is_active=True, organization_id=org.id))
    db.commit()

    result, sent = _run_reminders(db)
    assert "1 sent" in result
    to, subject, html = sent[0]
    assert to == ["owner@acme.com"]                      # admins only, not the Viewer
    assert "ends tomorrow" in subject
    assert "Add payment method" in html                  # no mandate → they must come pay
    db.refresh(org)
    assert org.trial_reminder_sent_at is not None

    # Hourly beat: must not send again.
    result2, sent2 = _run_reminders(db)
    assert sent2 == []
    assert "0 sent" in result2


def test_reminder_copy_differs_when_a_mandate_will_auto_charge(db):
    org = _org(db, subscription_status="trial", trial_ends_at=NOW + timedelta(hours=10),
               razorpay_subscription_id="sub_card")
    db.add(User(email="card@acme.com", name="C", google_id="g_card", role="Admin",
                is_active=True, organization_id=org.id))
    db.commit()
    _, sent = _run_reminders(db)
    assert "charged automatically" in sent[0][2]
    assert "View billing" in sent[0][2]


def test_reminder_skips_trials_that_are_not_due_yet(db):
    org = _org(db, subscription_status="trial", trial_ends_at=NOW + timedelta(days=5))
    db.add(User(email="early@acme.com", name="E", google_id="g_e", role="Owner",
                is_active=True, organization_id=org.id))
    db.commit()
    _, sent = _run_reminders(db)
    assert sent == []
    db.refresh(org)
    assert org.trial_reminder_sent_at is None


def test_reminder_escapes_agency_brand_fields(db):
    org = _org(db, subscription_status="trial", trial_ends_at=NOW + timedelta(hours=5),
               is_agency=True, brand_name='Evil"><script>alert(1)</script>')
    db.add(User(email="ag@acme.com", name="A", google_id="g_ag", role="Owner",
                is_active=True, organization_id=org.id))
    db.commit()
    _, sent = _run_reminders(db)
    assert "<script>" not in sent[0][2]
    assert "&lt;script&gt;" in sent[0][2]


# --- double-billing guard ----------------------------------------------------

def test_checkout_refuses_when_the_previous_mandate_is_already_charging(db):
    """Pay in one tab, and a second checkout starting before /confirm lands used to mint
    a second mandate while the first — already active at Razorpay — was left live and
    untracked, billing the customer twice every month."""
    from fastapi import HTTPException

    org = _org(db, subscription_status="trial", trial_ends_at=NOW + timedelta(days=3),
               razorpay_subscription_id="sub_first", subscription_ends_at=None)
    fake = MagicMock()
    fake.subscription.fetch.return_value = {"id": "sub_first", "status": "active",
                                            "notes": {"organization_id": str(org.id)}}
    with patch.object(SubscriptionService, "ensure_razorpay_customer", return_value="cust_1"), \
         patch.object(SubscriptionService, "_get_or_create_plan", return_value="plan_1"), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        with pytest.raises(HTTPException) as exc:
            SubscriptionService.create_subscription_checkout(
                db, org.id, "Client Co", "c@x.com", location_count=2, interval="monthly")
    assert exc.value.status_code == 409
    assert "already went through" in exc.value.detail
    fake.subscription.create.assert_not_called()          # no second mandate was minted
    db.refresh(org)
    assert org.razorpay_subscription_id == "sub_first"     # the live one is still tracked


def test_a_winding_down_org_may_still_resubscribe(db):
    """Cancelled at cycle end: Razorpay keeps the mandate 'active' until the period ends,
    so the guard above must not trap an org that is legitimately re-subscribing."""
    org = _org(db, subscription_status="active", razorpay_subscription_id="sub_old",
               subscription_ends_at=NOW + timedelta(days=5))
    fake = MagicMock()
    fake.subscription.fetch.return_value = {"id": "sub_old", "status": "active",
                                            "notes": {"organization_id": str(org.id)}}
    fake.subscription.create.return_value = {"id": "sub_new"}
    with patch.object(SubscriptionService, "ensure_razorpay_customer", return_value="cust_1"), \
         patch.object(SubscriptionService, "_get_or_create_plan", return_value="plan_1"), \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        out = SubscriptionService.create_subscription_checkout(
            db, org.id, "Client Co", "c@x.com", location_count=2, interval="monthly")
    assert out["id"] == "sub_new"
    db.refresh(org)
    assert org.razorpay_subscription_id == "sub_new"


def test_admin_location_override_warns_when_it_exceeds_the_paid_quota(db, client):
    from app.models.location import Location as Loc

    org = _org(db, location_quota=1)
    db.add_all([
        Loc(organization_id=org.id, google_location_id="l1", location_name="A", billing_status="active"),
        Loc(organization_id=org.id, google_location_id="l2", location_name="B", billing_status="pending_payment"),
    ])
    db.commit()
    over = db.query(Loc).filter(Loc.google_location_id == "l2").first()
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL):
        _as_super(db, client)
        r = client.patch(f"/api/v1/admin/locations/{over.id}",
                         json={"billing_status": "active", "reason": "goodwill"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active_locations"] == 2 and body["location_quota"] == 1
    assert "lock the surplus back" in body["message"]


# --- the onboarding gate must never spin forever ------------------------------

def test_status_reports_a_crashed_sync_as_failed_not_syncing(db, client):
    """A worker that dies mid-sync leaves sync_in_progress set forever, and the gate
    rendered "Building your audit" indefinitely with no retry. Past the stale window
    /billing/status must say failed, which is the screen that offers recovery."""
    from app.core import plan_config
    from app.models.organization_sync_state import OrganizationSyncState

    org = _org(db, subscription_status="trial", trial_ends_at=None)
    u = User(email="stuck@x.com", name="S", google_id="g_stuck", role="Owner",
             is_active=True, organization_id=org.id)
    db.add(u)
    db.add(OrganizationSyncState(
        organization_id=org.id, sync_in_progress=True,
        sync_started_at=NOW - timedelta(minutes=1)))
    db.commit()
    client.cookies.set("gmb_auth_token", create_access_token(u.email, token_version=u.token_version))

    r = client.get("/api/v1/billing/status")
    assert r.status_code == 200, r.text
    assert r.json()["onboarding_sync_status"] == "syncing"     # still plausibly running

    state = db.query(OrganizationSyncState).filter(
        OrganizationSyncState.organization_id == org.id).first()
    state.sync_started_at = NOW - timedelta(minutes=plan_config.ONBOARDING_SYNC_STALE_MINUTES + 5)
    db.commit()

    r2 = client.get("/api/v1/billing/status")
    assert r2.json()["onboarding_sync_status"] == "failed"     # dead: show the way out


def test_status_reports_idle_when_no_sync_ever_ran(db, client):
    """No sync-state row means the initial task never ran. The gate uses this to start
    one instead of polling against nothing (which is how an org with locations but no
    sync state sat on the spinner permanently)."""
    org = _org(db, subscription_status="trial", trial_ends_at=None)
    u = User(email="never@x.com", name="N", google_id="g_never", role="Owner",
             is_active=True, organization_id=org.id)
    db.add(u)
    db.commit()
    client.cookies.set("gmb_auth_token", create_access_token(u.email, token_version=u.token_version))

    r = client.get("/api/v1/billing/status")
    assert r.status_code == 200, r.text
    assert r.json()["onboarding_sync_status"] == "idle"


def test_metrics_survive_an_org_whose_quota_cannot_be_priced(db, client):
    """Seen in production: one active org with a quota above MAX_LOCATIONS made
    compute_monthly_price_paise raise its request-input HTTPException, so /admin/metrics
    returned 400 and the whole Accounts page broke. Report the rest, name the skipped."""
    from app.core import plan_config

    fine = _org(db, name="Priceable", subscription_status="active", location_quota=2)
    broken = _org(db, name="Unpriceable", subscription_status="active",
                  location_quota=plan_config.MAX_LOCATIONS + 50)
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL):
        _as_super(db, client)
        r = client.get("/api/v1/admin/metrics")
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["mrr_paise"] == 2 * 199_900          # the healthy org still counted
    assert m["mrr_skipped_org_ids"] == [broken.id]
    assert fine.id not in m["mrr_skipped_org_ids"]
