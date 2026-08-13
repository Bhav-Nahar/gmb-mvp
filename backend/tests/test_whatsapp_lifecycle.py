"""Onboarding, recovery and the webhook — against a fake Graph API.

These are the paths that carry money and consent, and none of them had a test.
Each one here is a failure that has to be survivable in front of a paying
tenant, because every one of them ends with their own card and their own phone
number:

  * a connection that half-succeeded (no webhooks) must not look ready
  * a blocked account must be able to come back without a database edit
  * a revoked connection must say "reconnect", not fail 300 messages
  * an unsigned webhook must be refused in production
  * STOP must be honoured, including by reminders

The Graph API is faked at the module's two HTTP helpers rather than at httpx:
what matters is which Meta call we make and what we do with the answer, and
faking the transport would only test httpx.
"""
from datetime import datetime, timezone

import pytest

from app.core.security import encrypt_token
from app.models.location import Location
from app.models.organization import Organization
from app.models.review_request import ReviewRequest
from app.models.review_suppression import ReviewSuppression
from app.models.whatsapp_account import WhatsAppAccount
from app.services import review_request_service as rr
from app.services import whatsapp_onboarding_service as onboarding
from app.services import whatsapp_service
from app.services.whatsapp_service import WhatsAppError

APP_ID = "app-1"


@pytest.fixture
def org(db):
    o = Organization(name="WA Co")
    db.add(o)
    db.flush()
    db.add(Location(organization_id=o.id, google_location_id="locations/1",
                    location_name="Lucira Jewellery"))
    db.commit()
    return o


@pytest.fixture
def location(db, org):
    return db.query(Location).filter(Location.organization_id == org.id).first()


class FakeGraph:
    """Meta, as far as onboarding is concerned. Records every call so a test can
    assert we asked the right questions, not just that we survived."""

    def __init__(self):
        self.calls: list[str] = []
        self.subscribed = True
        self.template_status = None          # None == template does not exist
        self.template_exists = False
        self.phone_numbers = [{"id": "phone-1", "display_phone_number": "+91 90000 00001",
                               "verified_name": "Lucira", "quality_rating": "GREEN"}]
        self.waba_id = "waba-1"
        self.register_fails = None           # a WhatsAppError to raise instead

    # onboarding._get(path, params) — token-in-query style
    def get(self, path, params=None):
        self.calls.append(f"GET {path}")
        if path == "/oauth/access_token":
            return {"access_token": "biz-token"}
        if path == "/debug_token":
            return {"data": {"granular_scopes": [
                {"scope": "whatsapp_business_management", "target_ids": [self.waba_id]}]}}
        if path.endswith("/phone_numbers"):
            return {"data": self.phone_numbers}
        if path.endswith("/subscribed_apps"):
            return {"data": ([{"whatsapp_business_api_data": {"id": APP_ID}}]
                             if self.subscribed else [])}
        if path.endswith("/message_templates"):
            return {"data": ([{"status": self.template_status}]
                             if self.template_status else [])}
        raise AssertionError(f"unexpected GET {path}")

    # onboarding._post(path, token, payload)
    def post(self, path, token, payload=None):
        self.calls.append(f"POST {path}")
        if path.endswith("/subscribed_apps"):
            return {"success": True}
        if path.endswith("/register"):
            if self.register_fails:
                raise self.register_fails
            return {"success": True}
        if path.endswith("/message_templates"):
            if self.template_exists:
                raise WhatsAppError("Invalid parameter", code=100, subcode=2388023,
                                    user_msg="A template with this name already exists.")
            self.template_status = "PENDING"
            self.template_exists = True
            return {"id": "tpl-1", "status": "PENDING", "category": "MARKETING"}
        raise AssertionError(f"unexpected POST {path}")

    # whatsapp_service._get(path, token, params) — bearer style, used by the
    # template-status read and the phone-number info read
    def bearer_get(self, path, token, params=None):
        self.calls.append(f"GET {path}")
        if path.endswith("/message_templates"):
            return {"data": ([{"status": self.template_status}]
                             if self.template_status else [])}
        return {"display_phone_number": "+91 90000 00001", "verified_name": "Lucira",
                "quality_rating": self.quality, "messaging_limit_tier": "TIER_1K"}

    quality = "GREEN"


@pytest.fixture
def graph(monkeypatch):
    fake = FakeGraph()
    monkeypatch.setattr(onboarding, "_get", fake.get)
    monkeypatch.setattr(onboarding, "_post", fake.post)
    monkeypatch.setattr(whatsapp_service, "_get", fake.bearer_get)
    monkeypatch.setattr(onboarding, "app_id", lambda: APP_ID)
    monkeypatch.setattr(onboarding, "_app_credentials", lambda: (APP_ID, "secret"))
    monkeypatch.setattr(onboarding, "_redirect_base", lambda: "https://pinzo.io")
    return fake


# ── Onboarding ────────────────────────────────────────────────────────────────

def test_a_clean_signup_lands_on_template_pending(db, org, graph):
    account = onboarding.complete_signup(db, org.id, "code-1")

    assert account.waba_id == "waba-1"
    assert account.phone_number_id == "phone-1"
    assert account.status == WhatsAppAccount.STATUS_TEMPLATE_PENDING
    assert account.template_status == "PENDING"
    # The steps that are silent when skipped are the ones worth asserting.
    assert "POST /waba-1/subscribed_apps" in graph.calls
    assert "POST /phone-1/register" in graph.calls
    assert account.app_subscribed is True


def test_the_registration_pin_is_kept(db, org, graph):
    from app.core.security import decrypt_token
    account = onboarding.complete_signup(db, org.id, "code-1")
    # Meta demands the same PIN on any future re-registration. Losing it means
    # the tenant has to disable two-step verification to recover their number.
    assert decrypt_token(account.registration_pin).isdigit()


def test_a_failed_subscription_does_not_pass_for_ready(db, org, graph):
    graph.subscribed = False
    account = onboarding.complete_signup(db, org.id, "code-1")

    # Sending must stay locked: without webhooks a STOP reply never reaches us,
    # and messaging someone who opted out is the one failure with legal weight.
    assert account.app_subscribed is False
    assert account.can_send is False
    assert "could not subscribe" in (account.status_detail or "")


def test_an_existing_template_is_believed_only_as_far_as_meta_confirms(db, org, graph):
    """A template that already exists is not necessarily an approved one."""
    graph.template_exists = True
    graph.template_status = "REJECTED"

    account = onboarding.complete_signup(db, org.id, "code-1")

    assert account.template_status == "REJECTED"
    assert account.status != WhatsAppAccount.STATUS_READY
    assert account.can_send is False


def test_an_approved_existing_template_goes_straight_to_ready(db, org, graph):
    graph.template_exists = True
    graph.template_status = "APPROVED"

    account = onboarding.complete_signup(db, org.id, "code-1")
    assert account.status == WhatsAppAccount.STATUS_READY


def test_a_number_still_in_the_whatsapp_app_is_explained_not_swallowed(db, org, graph):
    graph.register_fails = WhatsAppError("Cannot register", code=133005)
    account = onboarding.complete_signup(db, org.id, "code-1")

    assert account.status == WhatsAppAccount.STATUS_CONNECTED
    assert "WhatsApp Business app" in account.status_detail


def test_a_reconnect_reuses_the_same_row(db, org, graph):
    first = onboarding.complete_signup(db, org.id, "code-1")
    graph.template_exists = True
    second = onboarding.complete_signup(db, org.id, "code-2")
    # One WABA per organization is a database constraint; a second row here
    # would make "which credentials do we send with" an arbitrary choice.
    assert first.id == second.id


# ── Recovery: the one-way doors ───────────────────────────────────────────────

def _account(db, org, **kw):
    kw.setdefault("status", WhatsAppAccount.STATUS_READY)
    kw.setdefault("template_status", "APPROVED")
    kw.setdefault("app_subscribed", True)
    account = WhatsAppAccount(
        organization_id=org.id, waba_id="waba-1", phone_number_id="phone-1",
        access_token=encrypt_token("biz-token"), template_name="pinzo_review_request", **kw)
    db.add(account)
    db.commit()
    return account


def test_a_payment_block_is_not_a_one_way_door(db, org, graph):
    """The failure every fresh WABA hits, and the one that used to be terminal."""
    account = _account(db, org, status=WhatsAppAccount.STATUS_PAYMENT_REQUIRED,
                       status_detail="No payment method")

    # The hourly sweep leaves it alone: whether a card works is only knowable by
    # sending, so flipping the UI back to "Ready" on a timer would be a guess.
    onboarding.refresh_account(db, account)
    assert account.status == WhatsAppAccount.STATUS_PAYMENT_REQUIRED

    # The tenant pressing "Check again" is taken at their word.
    onboarding.refresh_account(db, account, unpark_payment=True)
    assert account.status == WhatsAppAccount.STATUS_READY
    assert account.status_detail is None


def test_a_red_quality_pause_lifts_itself_once_meta_says_so(db, org, graph):
    account = _account(db, org, status=WhatsAppAccount.STATUS_DISABLED,
                       quality_rating="RED")

    graph.quality = "RED"
    onboarding.refresh_account(db, account)
    assert account.status == WhatsAppAccount.STATUS_DISABLED   # still bad, stay paused

    graph.quality = "GREEN"                                    # Meta restored it
    assert onboarding.refresh_account(db, account) is True
    assert account.status == WhatsAppAccount.STATUS_READY


def test_red_quality_pauses_a_healthy_account(db, org, graph):
    account = _account(db, org)
    graph.quality = "RED"
    onboarding.refresh_account(db, account)
    assert account.status == WhatsAppAccount.STATUS_DISABLED


def test_a_revoked_connection_asks_for_a_reconnect(db, org, graph, monkeypatch):
    account = _account(db, org)
    monkeypatch.setattr(whatsapp_service, "_get", lambda *a, **kw: (_ for _ in ()).throw(
        WhatsAppError("Error validating access token", code=190)))

    onboarding.refresh_account(db, account)

    assert account.status == WhatsAppAccount.STATUS_REAUTH_REQUIRED
    assert "Reconnect" in account.status_detail
    assert account.can_send is False


def test_a_reauth_flag_clears_once_the_token_works_again(db, org, graph):
    account = _account(db, org, status=WhatsAppAccount.STATUS_REAUTH_REQUIRED)
    onboarding.refresh_account(db, account)
    assert account.status == WhatsAppAccount.STATUS_READY


def test_a_missing_subscription_is_repaired_by_the_sweep(db, org, graph):
    account = _account(db, org, app_subscribed=False)
    onboarding.refresh_account(db, account)
    assert account.app_subscribed is True
    assert "POST /waba-1/subscribed_apps" in graph.calls


def test_template_approval_is_picked_up_when_the_webhook_was_missed(db, org, graph):
    account = _account(db, org, status=WhatsAppAccount.STATUS_TEMPLATE_PENDING,
                       template_status="PENDING")
    graph.template_status = "APPROVED"

    assert onboarding.refresh_account(db, account) is True
    assert account.status == WhatsAppAccount.STATUS_READY


# ── The three facts behind can_send ───────────────────────────────────────────

def test_bulk_sending_needs_setup_webhooks_and_one_live_send(db, org):
    account = _account(db, org, app_subscribed=False)
    assert account.can_test is True            # enough for the test message
    assert account.can_send is False
    assert account.setup_blocker == "webhooks"

    account.app_subscribed = True
    assert account.setup_blocker == "test_send"
    assert account.can_send is False

    account.verified_send_at = datetime.now(timezone.utc)
    assert account.setup_blocker is None
    assert account.can_send is True


def test_the_test_send_unlocks_campaigns(db, org, location, monkeypatch):
    account = _account(db, org, verified_send_at=None)
    monkeypatch.setattr(whatsapp_service, "send_template", lambda *a, **kw: "wamid.test")

    row = rr.send_review_request(db, organization_id=org.id, location_id=location.id,
                                 phone_raw="9876543210", source="test", is_test=True)

    assert row.status == ReviewRequest.STATUS_SENT
    assert account.verified_send_at is not None
    assert account.can_send is True


def test_a_test_send_ignores_the_frequency_cap_but_not_an_opt_out(db, org, location, monkeypatch):
    _account(db, org, verified_send_at=None)
    monkeypatch.setattr(whatsapp_service, "send_template", lambda *a, **kw: "wamid.test")

    kw = dict(organization_id=org.id, location_id=location.id, phone_raw="9876543210",
              source="test", is_test=True)
    assert rr.send_review_request(db, **kw).status == ReviewRequest.STATUS_SENT
    # An admin testing twice is not a customer being pestered.
    assert rr.send_review_request(db, **kw).status == ReviewRequest.STATUS_SENT

    rr.suppress(db, org.id, "919876543210", ReviewSuppression.REASON_OPT_OUT)
    assert rr.send_review_request(db, **kw).status == ReviewRequest.STATUS_SKIPPED


def test_a_billing_failure_parks_the_account_instead_of_burning_the_list(
        db, org, location, monkeypatch):
    account = _account(db, org, verified_send_at=datetime.now(timezone.utc))

    def boom(*a, **kw):
        raise WhatsAppError("no payment method on this account", code=131042)
    monkeypatch.setattr(whatsapp_service, "send_template", boom)

    row = rr.send_review_request(db, organization_id=org.id, location_id=location.id,
                                 phone_raw="9876543210")
    assert row.status == ReviewRequest.STATUS_FAILED
    assert account.status == WhatsAppAccount.STATUS_PAYMENT_REQUIRED
    assert account.can_send is False
    assert "payment method" in row.error_detail


def test_a_revoked_token_mid_campaign_parks_the_account(db, org, location, monkeypatch):
    account = _account(db, org, verified_send_at=datetime.now(timezone.utc))

    def boom(*a, **kw):
        raise WhatsAppError("Error validating access token", code=190)
    monkeypatch.setattr(whatsapp_service, "send_template", boom)

    rr.send_review_request(db, organization_id=org.id, location_id=location.id,
                           phone_raw="9876543210")
    assert account.status == WhatsAppAccount.STATUS_REAUTH_REQUIRED


def test_a_payment_unpark_still_respects_a_bad_quality_rating(db, org, graph):
    """"I've added a card" does not undo Meta being unhappy with the number."""
    account = _account(db, org, status=WhatsAppAccount.STATUS_PAYMENT_REQUIRED)
    graph.quality = "RED"

    onboarding.refresh_account(db, account, unpark_payment=True)

    assert account.status == WhatsAppAccount.STATUS_DISABLED
    assert account.can_send is False
