"""The inbox: storing customer replies, and the 24-hour rule that governs answering.

Three things here are worth pinning down, because each one is invisible until a
customer notices it:

  * Meta re-delivers a webhook it did not get a fast 200 for, so the same reply
    arrives twice. Without dedupe the thread shows it twice.
  * An opt-out is still a message. Storing it and suppressing the number are two
    separate obligations, and an earlier version did only the second.
  * Free-form text is legal for 24 hours after the customer's last message. Send
    it late and Meta rejects it, so the refusal has to happen here, with an
    explanation, not there, as an opaque 400.
"""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.api import whatsapp_inbox as inbox
from app.api import whatsapp_webhook as wh
from app.core.security import encrypt_token
from app.models.location import Location
from app.models.organization import Organization
from app.models.review_request import ReviewRequest
from app.models.review_suppression import ReviewSuppression
from app.models.user import User
from app.models.whatsapp_account import WhatsAppAccount
from app.models.whatsapp_message import WhatsAppMessage

SECRET = "app-secret"
CUSTOMER = "919000000009"


@pytest.fixture
def account(db):
    org = Organization(name="Inbox Co")
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


@pytest.fixture
def user(db, account):
    u = User(email="owner@inbox.test", name="Owner", google_id="g_inbox_owner",
             role="Owner", organization_id=account.organization_id)
    db.add(u)
    db.commit()
    return u


def _deliver(db, account, *, wamid="wamid.1", body="hello", ts=None, kind="text"):
    """Drive the real webhook the way Meta does: a raw signed body."""
    import asyncio
    from app.core.config import settings

    msg = {"from": CUSTOMER, "id": wamid, "type": kind,
           "timestamp": str(int((ts or datetime.now(timezone.utc)).timestamp()))}
    if kind == "text":
        msg["text"] = {"body": body}

    payload = {"entry": [{"id": account.waba_id, "changes": [
        {"field": "messages", "value": {
            "metadata": {"phone_number_id": account.phone_number_id},
            "messages": [msg]}}]}]}

    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()

    class FakeRequest:
        headers = {"x-hub-signature-256": sig}

        async def body(self):
            return raw

    old = settings.FACEBOOK_APP_SECRET
    settings.FACEBOOK_APP_SECRET = SECRET
    try:
        return asyncio.run(wh.receive(FakeRequest(), db))
    finally:
        settings.FACEBOOK_APP_SECRET = old


def _count(db, account):
    return db.query(WhatsAppMessage).filter(
        WhatsAppMessage.organization_id == account.organization_id).count()


# ── Storing what arrives ──────────────────────────────────────────────────────

def test_a_customer_reply_is_stored(db, account):
    _deliver(db, account, body="is the store open on sunday?")
    row = db.query(WhatsAppMessage).one()
    assert row.direction == WhatsAppMessage.DIRECTION_IN
    assert row.body == "is the store open on sunday?"
    assert row.phone == CUSTOMER
    assert row.status == WhatsAppMessage.STATUS_RECEIVED


def test_a_redelivered_webhook_does_not_duplicate_the_message(db, account):
    """Meta retries anything it did not get a fast 200 for."""
    _deliver(db, account, wamid="wamid.same")
    _deliver(db, account, wamid="wamid.same")
    assert _count(db, account) == 1


def test_a_non_text_message_is_stored_with_a_readable_placeholder(db, account):
    """An empty bubble reads as a bug; the tenant should see that a photo came."""
    _deliver(db, account, wamid="wamid.img", kind="image", body="")
    assert db.query(WhatsAppMessage).one().body == "[image]"


def test_an_opt_out_is_both_stored_and_suppressed(db, account):
    """Two separate obligations. Dropping the message loses the tenant's context
    for why the number went quiet."""
    _deliver(db, account, body="STOP")
    assert db.query(WhatsAppMessage).one().body == "STOP"
    assert db.query(ReviewSuppression).filter(
        ReviewSuppression.organization_id == account.organization_id,
        ReviewSuppression.phone == CUSTOMER).count() == 1


# ── Delivery receipts on our own replies ──────────────────────────────────────

def test_a_receipt_never_walks_a_message_backwards(db, account):
    """`read` can arrive before `delivered`; the later receipt must not downgrade."""
    row = WhatsAppMessage(organization_id=account.organization_id, phone=CUSTOMER,
                          direction=WhatsAppMessage.DIRECTION_OUT, body="hi",
                          wamid="wamid.out", status=WhatsAppMessage.STATUS_SENT)
    db.add(row)
    db.commit()

    wh._message_status(db, "wamid.out", "read", {})
    wh._message_status(db, "wamid.out", "delivered", {})
    db.refresh(row)
    assert row.status == WhatsAppMessage.STATUS_READ


# ── The 24-hour window ────────────────────────────────────────────────────────

def test_the_window_is_open_just_inside_24_hours():
    assert inbox._window_open(datetime.now(timezone.utc) - timedelta(hours=23, minutes=59))


def test_the_window_is_shut_just_outside_24_hours():
    assert not inbox._window_open(datetime.now(timezone.utc) - timedelta(hours=24, minutes=1))


def test_the_window_is_shut_when_the_customer_never_wrote():
    """First contact always needs a template — there is no window to be inside."""
    assert not inbox._window_open(None)


def test_replying_after_the_window_is_refused_with_an_explanation(db, account, user):
    _deliver(db, account, ts=datetime.now(timezone.utc) - timedelta(days=2))

    with pytest.raises(HTTPException) as err:
        inbox.reply(CUSTOMER, inbox.ReplyIn(body="sorry for the delay"), db, user)
    assert err.value.status_code == 409
    assert "template" in err.value.detail.lower()


def test_replying_to_an_opted_out_customer_is_refused(db, account, user):
    """Consent outranks an open window: they wrote to say stop."""
    _deliver(db, account, body="STOP")

    with pytest.raises(HTTPException) as err:
        inbox.reply(CUSTOMER, inbox.ReplyIn(body="one more thing"), db, user)
    assert err.value.status_code == 400
    assert "opted out" in err.value.detail.lower()


def test_a_reply_inside_the_window_is_sent_and_stored(db, account, user, monkeypatch):
    _deliver(db, account, body="is the store open?")
    monkeypatch.setattr(inbox.whatsapp_service, "send_text",
                        lambda acc, to, body: "wamid.reply")

    out = inbox.reply(CUSTOMER, inbox.ReplyIn(body="Yes, 10am to 9pm"), db, user)

    assert out.direction == WhatsAppMessage.DIRECTION_OUT
    row = db.query(WhatsAppMessage).filter(
        WhatsAppMessage.wamid == "wamid.reply").one()
    assert row.body == "Yes, 10am to 9pm"
    assert row.sent_by_user_id == user.id


# ── The merged thread ─────────────────────────────────────────────────────────

def test_the_thread_includes_the_review_request_we_sent(db, account, user):
    """Without this the tenant sees a complaint with nothing above it."""
    db.add(ReviewRequest(
        organization_id=account.organization_id,
        location_id=db.query(Location).one().id,
        phone=CUSTOMER, customer_name="Ravi", token="tok-1",
        status=ReviewRequest.STATUS_DELIVERED,
        sent_at=datetime.now(timezone.utc) - timedelta(minutes=5)))
    db.commit()
    _deliver(db, account, body="no it was closed when i came")

    thread = inbox.get_thread(CUSTOMER, db, user)

    assert [m.kind for m in thread] == ["review_request", "message"]
    assert thread[-1].body == "no it was closed when i came"


def test_a_queued_request_is_not_in_the_thread(db, account, user):
    """It never reached the customer, so it is not part of the conversation."""
    db.add(ReviewRequest(
        organization_id=account.organization_id,
        location_id=db.query(Location).one().id,
        phone=CUSTOMER, token="tok-2", status=ReviewRequest.STATUS_QUEUED))
    db.commit()

    assert inbox.get_thread(CUSTOMER, db, user) == []


def test_the_conversation_list_reports_the_window_and_the_name(db, account, user):
    db.add(ReviewRequest(
        organization_id=account.organization_id,
        location_id=db.query(Location).one().id,
        phone=CUSTOMER, customer_name="Ravi", token="tok-3",
        status=ReviewRequest.STATUS_SENT,
        sent_at=datetime.now(timezone.utc) - timedelta(minutes=10)))
    db.commit()
    _deliver(db, account, body="thanks")

    convos = inbox.list_conversations(db, user, limit=100)

    assert len(convos) == 1
    assert convos[0].phone == CUSTOMER
    assert convos[0].customer_name == "Ravi"
    assert convos[0].window_open is True
    assert convos[0].last_message == "thanks"


# ── Cold inbound: the customer wrote first ────────────────────────────────────

def test_a_customer_who_messages_us_first_becomes_a_conversation(db, account, user):
    """No review request, no template, no prior contact — someone found the
    number and wrote. Meta opens the 24-hour window on THEIR message, so this is
    a normal answerable thread and must not depend on us having messaged first.
    """
    _deliver(db, account, body="do you have this in size 8?")

    convos = inbox.list_conversations(db, user, limit=100)

    assert [c.phone for c in convos] == [CUSTOMER]
    assert convos[0].window_open is True
    # Names only ever come from review requests, so a cold contact has none and
    # the UI falls back to the number.
    assert convos[0].customer_name is None


def test_we_can_reply_to_a_cold_inbound_without_ever_sending_a_template(db, account,
                                                                       user, monkeypatch):
    sent: dict = {}

    def fake_send(acc, to, body):
        sent["to"] = to
        return "wamid.cold"

    monkeypatch.setattr(inbox.whatsapp_service, "send_text", fake_send)
    _deliver(db, account, body="are you open now?")

    out = inbox.reply(CUSTOMER, inbox.ReplyIn(body="Yes, till 9pm"), db, user)

    assert out.direction == WhatsAppMessage.DIRECTION_OUT
    assert sent["to"] == CUSTOMER
