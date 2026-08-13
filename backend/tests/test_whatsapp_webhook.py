"""Meta's webhook — the only source of delivery truth and of opt-outs.

Unauthenticated by necessity (Meta has no session to present) and therefore the
one endpoint where a signature check is the whole security model. What arrives
here suppresses phone numbers, disables accounts and flips template approval, so
each of those is tested from the raw payload inwards.
"""
import hashlib
import hmac
import json

import pytest

from app.api import whatsapp_webhook as wh
from app.core.security import encrypt_token
from app.models.organization import Organization
from app.models.location import Location
from app.models.review_request import ReviewRequest
from app.models.whatsapp_account import WhatsAppAccount
from app.services import review_request_service as rr

SECRET = "app-secret"


@pytest.fixture
def account(db):
    org = Organization(name="Webhook Co")
    db.add(org)
    db.flush()
    db.add(Location(organization_id=org.id, google_location_id="locations/1",
                    location_name="Store"))
    acc = WhatsAppAccount(
        organization_id=org.id, waba_id="waba-1", phone_number_id="phone-1",
        display_phone_number="+91 90000 00001", access_token=encrypt_token("t"),
        template_name="pinzo_review_request", template_status="APPROVED",
        status=WhatsAppAccount.STATUS_READY, app_subscribed=True)
    db.add(acc)
    db.commit()
    return acc


def _post(db, payload: dict, *, signed=True, secret=SECRET, env="production"):
    """Drive the endpoint the way Meta does: a raw signed body."""
    import asyncio
    from app.core.config import settings

    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()

    class FakeRequest:
        headers = {"x-hub-signature-256": sig} if signed else {}

        async def body(self):
            return raw

    old_secret, old_env = settings.FACEBOOK_APP_SECRET, settings.APP_ENV
    settings.FACEBOOK_APP_SECRET, settings.APP_ENV = secret, env
    try:
        return asyncio.run(wh.receive(FakeRequest(), db))
    finally:
        settings.FACEBOOK_APP_SECRET, settings.APP_ENV = old_secret, old_env


def _messages(account, **value):
    return {"entry": [{"id": account.waba_id, "changes": [
        {"field": "messages",
         "value": {"metadata": {"phone_number_id": account.phone_number_id}, **value}}]}]}


# ── Authentication ────────────────────────────────────────────────────────────

def test_an_unsigned_payload_is_refused(db, account):
    res = _post(db, _messages(account), signed=False)
    assert getattr(res, "status_code", None) == 401


def test_a_missing_app_secret_fails_closed_in_production(db, account):
    """The env var was optional once, which quietly made this endpoint open: it
    can suppress numbers and disable accounts for any org whose ids are known."""
    res = _post(db, _messages(account), secret="", env="production")
    assert getattr(res, "status_code", None) == 401


def test_a_missing_app_secret_is_tolerated_in_development(db, account):
    res = _post(db, _messages(account), secret="", env="development")
    assert res == {"ok": True}


def test_a_wrong_signature_is_refused(db, account, monkeypatch):
    res = _post(db, _messages(account), secret="a-different-secret")
    assert getattr(res, "status_code", None) == 401


# ── Delivery truth ────────────────────────────────────────────────────────────

def _request(db, account, **kw):
    kw.setdefault("status", ReviewRequest.STATUS_SENT)
    row = ReviewRequest(
        organization_id=account.organization_id,
        location_id=db.query(Location).first().id,
        phone="919876543210", token=rr.new_token(), wamid="wamid.1", **kw)
    db.add(row)
    db.commit()
    return row


def test_a_delivery_receipt_patches_the_existing_row(db, account):
    row = _request(db, account)
    _post(db, _messages(account, statuses=[
        {"id": "wamid.1", "status": "delivered", "timestamp": "1700000000"}]))
    db.refresh(row)
    assert row.status == ReviewRequest.STATUS_DELIVERED
    assert row.delivered_at is not None


def test_a_receipt_never_walks_a_request_backwards(db, account):
    row = _request(db, account, status=ReviewRequest.STATUS_CLICKED)
    _post(db, _messages(account, statuses=[
        {"id": "wamid.1", "status": "delivered", "timestamp": "1700000000"}]))
    db.refresh(row)
    # A click already proves delivery, and receipts arrive out of order.
    assert row.status == ReviewRequest.STATUS_CLICKED


def test_a_permanent_failure_suppresses_the_number(db, account):
    row = _request(db, account)
    _post(db, _messages(account, statuses=[
        {"id": "wamid.1", "status": "failed", "timestamp": "1700000000",
         "errors": [{"code": 131026, "title": "Not a WhatsApp user"}]}]))
    db.refresh(row)
    assert row.status == ReviewRequest.STATUS_FAILED
    assert rr.is_suppressed(db, account.organization_id, "919876543210")


def test_an_ordinary_failure_does_not_suppress(db, account):
    _request(db, account)
    _post(db, _messages(account, statuses=[
        {"id": "wamid.1", "status": "failed", "timestamp": "1700000000",
         "errors": [{"code": 131000, "title": "Something went wrong"}]}]))
    assert not rr.is_suppressed(db, account.organization_id, "919876543210")


def test_an_auth_failure_asks_the_tenant_to_reconnect(db, account):
    _request(db, account)
    _post(db, _messages(account, statuses=[
        {"id": "wamid.1", "status": "failed", "timestamp": "1700000000",
         "errors": [{"code": 190, "title": "Error validating access token"}]}]))
    db.refresh(account)
    assert account.status == WhatsAppAccount.STATUS_REAUTH_REQUIRED


def test_an_event_for_an_unknown_number_is_ignored(db, account):
    payload = {"entry": [{"id": "other", "changes": [
        {"field": "messages", "value": {"metadata": {"phone_number_id": "not-ours"},
                                        "statuses": []}}]}]}
    assert _post(db, payload) == {"ok": True}


# ── Opt-outs ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said", ["STOP", "stop", " Unsubscribe ", "band karo"])
def test_a_stop_reply_suppresses_that_number(db, account, said):
    _post(db, _messages(account, messages=[
        {"from": "919876543210", "text": {"body": said}}]))
    assert rr.is_suppressed(db, account.organization_id, "919876543210")


def test_a_sentence_containing_stop_is_not_an_opt_out(db, account):
    _post(db, _messages(account, messages=[
        {"from": "919876543210", "text": {"body": "please don't stop sending offers"}}]))
    # Treating this as an opt-out silently loses a customer who wanted the opposite.
    assert not rr.is_suppressed(db, account.organization_id, "919876543210")


def test_metas_own_marketing_opt_out_is_honoured(db, account):
    payload = {"entry": [{"id": account.waba_id, "changes": [{
        "field": "user_preferences",
        "value": {"metadata": {"phone_number_id": account.phone_number_id},
                  "user_preferences": [{"wa_id": "919876543210",
                                        "category": "marketing_messages",
                                        "value": "stop"}]}}]}]}
    _post(db, payload)
    assert rr.is_suppressed(db, account.organization_id, "919876543210")


def test_an_opt_out_reaches_reminders_too(db, account, monkeypatch):
    """The reminder loop used to skip this check, which made STOP a suggestion."""
    from datetime import datetime, timedelta, timezone
    import app.tasks_whatsapp as tasks
    from app.services import whatsapp_service

    account.verified_send_at = datetime.now(timezone.utc)
    row = _request(db, account, status=ReviewRequest.STATUS_DELIVERED,
                   sent_at=datetime.now(timezone.utc) - timedelta(hours=30))
    db.commit()

    sent = []
    monkeypatch.setattr(whatsapp_service, "send_template",
                        lambda *a, **kw: sent.append(kw["to"]) or "wamid.2")
    monkeypatch.setattr(tasks, "SEND_INTERVAL_SECONDS", 0)
    # Inside quiet hours: this test is about STOP, not about the send window.
    monkeypatch.setattr(tasks, "seconds_until_send_window", lambda *a, **kw: 0)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    _post(db, _messages(account, messages=[
        {"from": row.phone, "text": {"body": "STOP"}}]))

    summary = tasks.send_review_reminders_task()
    assert sent == []
    assert summary["suppressed"] == 1
    db.refresh(row)
    # And it stops being reconsidered every hour from now on.
    assert row.reminder_count == tasks.MAX_REMINDERS


# ── Template and quality ──────────────────────────────────────────────────────

def test_template_approval_unlocks_sending(db, account):
    account.status = WhatsAppAccount.STATUS_TEMPLATE_PENDING
    account.template_status = "PENDING"
    db.commit()

    _post(db, {"entry": [{"id": account.waba_id, "changes": [{
        "field": "message_template_status_update",
        "value": {"message_template_name": account.template_name, "event": "APPROVED"}}]}]})

    db.refresh(account)
    assert account.status == WhatsAppAccount.STATUS_READY
    assert account.status_detail is None


def test_a_newly_approved_version_is_adopted(db, account):
    """A tenant who re-created the template keeps the working one until the new
    one is approved — at which point somebody has to switch over to it."""
    _post(db, {"entry": [{"id": account.waba_id, "changes": [{
        "field": "message_template_status_update",
        "value": {"message_template_name": "pinzo_review_request_v2",
                  "event": "APPROVED"}}]}]})
    db.refresh(account)
    assert account.template_name == "pinzo_review_request_v2"


def test_an_unrelated_template_is_left_alone(db, account):
    _post(db, {"entry": [{"id": account.waba_id, "changes": [{
        "field": "message_template_status_update",
        "value": {"message_template_name": "their_own_promo", "event": "APPROVED"}}]}]})
    db.refresh(account)
    assert account.template_name == "pinzo_review_request"


def test_red_quality_pauses_sending_immediately(db, account):
    _post(db, {"entry": [{"id": account.waba_id, "changes": [{
        "field": "phone_number_quality_update",
        "value": {"display_phone_number": account.display_phone_number,
                  "quality_rating": "RED"}}]}]})
    db.refresh(account)
    # The safety valve: a tenant mid-blast on a bad list otherwise keeps sending
    # until Meta bans the number, which nobody can undo.
    assert account.status == WhatsAppAccount.STATUS_DISABLED
    assert account.can_send is False
