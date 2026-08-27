"""Meta's webhook: delivery receipts, inbound replies, template + quality updates.

ONE callback URL receives events for EVERY WABA subscribed to our app, so the
first job of every event is routing: `phone_number_id -> organization`. An event
for a number we don't know is ignored rather than guessed at.

Unauthenticated in the session sense — Meta has no cookie to send — and instead
verified by the X-Hub-Signature-256 HMAC over the raw body using the app secret.

Three things arrive here that nothing else can tell us:
  * delivery truth      — a send call returning 200 only means Meta accepted it;
                          whether it reached anyone shows up minutes later
  * opt-outs            — the legal obligation. A STOP reply or a marketing
                          opt-out must suppress the number permanently
  * template approval   — flips an account from "pending" to able to send
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.review_request import ReviewRequest
from app.models.review_suppression import ReviewSuppression
from app.models.whatsapp_account import WhatsAppAccount
from app.models.whatsapp_message import WhatsAppMessage
from app.services import whatsapp_errors
from app.services.review_request_service import suppress
from app.services.whatsapp_onboarding_service import REVIEW_TEMPLATE_NAME

logger = logging.getLogger(__name__)
router = APIRouter()

# Anything a person plausibly types to make messages stop. Matched on the whole
# trimmed message, not a substring: "please don't stop sending offers" is not an
# opt-out, and treating it as one silently loses a customer.
OPT_OUT_WORDS = {"stop", "unsubscribe", "opt out", "optout", "cancel", "quit", "band karo", "बंद करो"}


@router.get("")
def verify(request: Request):
    """Meta's one-time subscription handshake."""
    params = request.query_params
    expected = (settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN or "").strip()
    if params.get("hub.mode") == "subscribe" and expected and params.get("hub.verify_token") == expected:
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=status.HTTP_403_FORBIDDEN)


def _signature_ok(raw: bytes, header: Optional[str]) -> bool:
    """Verify Meta signed this exact body with our app secret.

    Fails CLOSED, including when the secret is simply missing. This endpoint is
    unauthenticated by necessity, and what arrives on it suppresses phone
    numbers, disables accounts and marks messages failed — so an unset
    environment variable must not turn it into an open one. In development,
    where there is often no app at all, it stays permissive and says so.
    """
    secret = (settings.FACEBOOK_APP_SECRET or "").strip()
    if not secret:
        if settings.APP_ENV == "development":
            logger.warning("[wa-webhook] FACEBOOK_APP_SECRET unset — accepting UNVERIFIED "
                           "webhook (development only)")
            return True
        logger.error("[wa-webhook] FACEBOOK_APP_SECRET unset in %s — REJECTING webhook. "
                     "Delivery receipts and opt-outs are being lost.", settings.APP_ENV)
        return False
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


@router.post("")
async def receive(request: Request, db: Session = Depends(get_db)):
    """Always answers 200 quickly. Meta disables webhooks that respond slowly or
    with errors, and a payload we cannot process is not something a retry fixes."""
    raw = await request.body()
    if not _signature_ok(raw, request.headers.get("x-hub-signature-256")):
        logger.warning("[wa-webhook] rejected: bad signature")
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        return {"ok": True}

    try:
        _handle(db, payload)
    except Exception:                      # noqa: BLE001 — never fail Meta's delivery
        logger.exception("[wa-webhook] processing failed")
    return {"ok": True}


def _handle(db: Session, payload: dict[str, Any]) -> None:
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            field = change.get("field")
            value = change.get("value") or {}

            if field == "message_template_status_update":
                _template_update(db, entry.get("id"), value)
                continue
            if field in ("phone_number_quality_update", "account_update"):
                _quality_update(db, entry.get("id"), value)
                continue
            if field == "user_preferences":
                _preferences(db, value)
                continue

            # Default: messages field — statuses and inbound messages.
            account = _account_for(db, (value.get("metadata") or {}).get("phone_number_id"))
            if not account:
                continue
            for st in value.get("statuses") or []:
                _status_update(db, account, st)
            for msg in value.get("messages") or []:
                _inbound(db, account, msg)


def _account_for(db: Session, phone_number_id: Optional[str]) -> Optional[WhatsAppAccount]:
    if not phone_number_id:
        return None
    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.phone_number_id == str(phone_number_id),
    ).first()
    if not account:
        # Expected in normal operation: one app callback receives events for
        # every WABA it is subscribed to, including numbers we no longer hold.
        logger.info("[wa-webhook] ignoring event for unknown phone_number_id %s", phone_number_id)
    return account


def _status_update(db: Session, account: WhatsAppAccount, st: dict[str, Any]) -> None:
    """Patch the request this receipt refers to.

    Meta reuses the ORIGINAL message id here, so this must update the existing
    row — writing it as a new record would overwrite the send with a status.
    """
    wamid = st.get("id")
    state = (st.get("status") or "").lower()
    if not wamid or state not in ("sent", "delivered", "read", "failed"):
        return

    # An inbox reply and a review request are both outbound messages that get
    # receipts, but they live in different tables. Try the inbox first: it is
    # the smaller, hotter table, and a wamid belongs to exactly one of the two.
    if _message_status(db, wamid, state, st):
        return

    row = db.query(ReviewRequest).filter(ReviewRequest.wamid == wamid).first()
    if not row:
        return

    at = _ts(st.get("timestamp"))
    if state == "delivered":
        row.delivered_at = row.delivered_at or at
        # Never walk a request backwards: a click already proves delivery, and
        # receipts can arrive out of order.
        if row.status in (ReviewRequest.STATUS_QUEUED, ReviewRequest.STATUS_SENT):
            row.status = ReviewRequest.STATUS_DELIVERED
    elif state == "read":
        row.read_at = row.read_at or at
        if row.status in (ReviewRequest.STATUS_QUEUED, ReviewRequest.STATUS_SENT,
                          ReviewRequest.STATUS_DELIVERED):
            row.status = ReviewRequest.STATUS_READ
    elif state == "failed":
        err = (st.get("errors") or [{}])[0]
        code = err.get("code")
        row.status = ReviewRequest.STATUS_FAILED
        row.error_code = str(code) if code is not None else None
        row.error_detail = (
            (err.get("error_data") or {}).get("details")
            or err.get("title")
            or whatsapp_errors.explain(code).message
        )[:1000]
        db.commit()
        # A permanent failure means this number can never receive from us.
        if whatsapp_errors.is_permanent(code):
            suppress(db, account.organization_id, row.phone,
                     ReviewSuppression.REASON_FAILED, note=f"Meta error {code}")
        # An auth failure is not about this recipient at all — our access is gone,
        # and every other send will fail the same way until the tenant reconnects.
        elif whatsapp_errors.is_reauth(code, row.error_detail or ""):
            account.status = WhatsAppAccount.STATUS_REAUTH_REQUIRED
            account.status_detail = whatsapp_errors.explain(190).message
            db.commit()
        logger.info("[wa-webhook] %s failed: %s", wamid, row.error_detail)
        return

    db.commit()


def _message_status(db: Session, wamid: str, state: str, st: dict[str, Any]) -> bool:
    """Patch an inbox message's delivery status. Returns True if it was ours.

    Statuses arrive out of order (a `read` can beat its `delivered`), so the
    status only ever moves forward through the ladder — otherwise a late
    receipt would downgrade a message the tenant already saw marked read.
    """
    row = db.query(WhatsAppMessage).filter(WhatsAppMessage.wamid == wamid).first()
    if not row:
        return False

    ladder = [WhatsAppMessage.STATUS_SENT, WhatsAppMessage.STATUS_DELIVERED,
              WhatsAppMessage.STATUS_READ]
    if state == "failed":
        err = (st.get("errors") or [{}])[0]
        row.status = WhatsAppMessage.STATUS_FAILED
        row.error_detail = (
            (err.get("error_data") or {}).get("details")
            or err.get("title")
            or whatsapp_errors.explain(err.get("code")).message
        )[:1000]
    elif row.status != WhatsAppMessage.STATUS_FAILED and state in ladder:
        current = ladder.index(row.status) if row.status in ladder else -1
        if ladder.index(state) > current:
            row.status = state
    db.commit()
    return True


def _inbound(db: Session, account: WhatsAppAccount, msg: dict[str, Any]) -> None:
    """Store the customer's message, then handle opt-outs.

    Storing comes first and is never skipped. An opt-out is still a message the
    tenant should be able to see in the thread — silently dropping it is how
    "why did they stop replying?" becomes a support ticket.
    """
    phone = str(msg.get("from") or "")
    wamid = msg.get("id")
    text = ((msg.get("text") or {}).get("body") or "").strip()
    button = ((msg.get("button") or {}).get("text") or "").strip()

    if phone:
        _store_inbound(db, account, msg, phone, wamid, text or button)

    # Opt-out matching is on the whole trimmed message, lowercased.
    said = (text or button).lower()
    if said and said in OPT_OUT_WORDS and phone:
        suppress(db, account.organization_id, phone,
                 ReviewSuppression.REASON_OPT_OUT, note=f'Replied "{said}"')
        logger.info("[wa-webhook] opt-out from %s (org %s)", phone, account.organization_id)


def _store_inbound(db: Session, account: WhatsAppAccount, msg: dict[str, Any],
                   phone: str, wamid: Optional[str], body: str) -> None:
    """Write one inbound message, ignoring Meta's retries.

    Meta re-delivers any webhook it did not get a fast 200 for, so the same
    reply arrives more than once. `wamid` is unique in the table; we check first
    (cheap, indexed) and still catch the race, because two retries can land in
    parallel workers and the check alone would let both through.
    """
    if wamid and db.query(WhatsAppMessage.id).filter(
            WhatsAppMessage.wamid == str(wamid)).first():
        return

    kind = str(msg.get("type") or "text")
    if not body and kind != "text":
        # Media, location, contacts, stickers — we don't render them yet, but an
        # empty bubble reads as a bug, so the thread says what arrived.
        body = f"[{kind}]"

    row = WhatsAppMessage(
        organization_id=account.organization_id,
        phone=phone,
        direction=WhatsAppMessage.DIRECTION_IN,
        body=body or None,
        message_type=kind,
        wamid=str(wamid) if wamid else None,
        status=WhatsAppMessage.STATUS_RECEIVED,
        created_at=_ts(msg.get("timestamp")),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # Lost the race against a parallel retry. The message is stored either
        # way, which is all we wanted.
        db.rollback()


def _preferences(db: Session, value: dict[str, Any]) -> None:
    """Meta's own marketing opt-out toggle, which never appears as a message."""
    for pref in value.get("user_preferences") or []:
        if (pref.get("category") == "marketing_messages"
                and (pref.get("value") or "").lower() == "stop"):
            phone = str(pref.get("wa_id") or "")
            account = _account_for(db, (value.get("metadata") or {}).get("phone_number_id"))
            if phone and account:
                suppress(db, account.organization_id, phone,
                         ReviewSuppression.REASON_OPT_OUT, note="Marketing opt-out")


def _template_update(db: Session, waba_id: Optional[str], value: dict[str, Any]) -> None:
    """Template approval is what unblocks sending, so it is applied the moment
    Meta says so rather than waiting for the next poll."""
    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.waba_id == str(waba_id),
    ).first() if waba_id else None
    if not account:
        return

    name = value.get("message_template_name")
    event = (value.get("event") or "").upper()

    # A template we submitted but did not switch to yet — the case where a tenant
    # re-created the template while an approved one was still in service. Adopt
    # it once Meta approves, which is what the create endpoint promised would
    # happen; before this, that newer version was orphaned.
    if name != account.template_name:
        if event == "APPROVED" and name and str(name).startswith(REVIEW_TEMPLATE_NAME):
            account.template_name = name
            account.template_status = event
            db.commit()
            logger.info("[wa-webhook] adopted newly approved template %s (org %s)",
                        name, account.organization_id)
        return

    account.template_status = event
    if event == "APPROVED" and account.status == WhatsAppAccount.STATUS_TEMPLATE_PENDING:
        account.status = WhatsAppAccount.STATUS_READY
        account.status_detail = None
    elif event == "REJECTED":
        account.status_detail = (
            f"Meta rejected the review template: {value.get('reason') or 'no reason given'}")
    db.commit()
    logger.info("[wa-webhook] template %s -> %s (org %s)",
                account.template_name, event, account.organization_id)


def _quality_update(db: Session, waba_id: Optional[str], value: dict[str, Any]) -> None:
    """Quality and tier changes.

    A RED rating disables sending immediately. This is the safety valve agreed
    up front: a tenant mid-blast on a bad list will otherwise keep sending until
    Meta bans the number, and that is not recoverable by us or by them.
    """
    account = None
    if value.get("display_phone_number") or value.get("phone_number"):
        account = db.query(WhatsAppAccount).filter(
            WhatsAppAccount.display_phone_number == (
                value.get("display_phone_number") or value.get("phone_number")),
        ).first()
    if not account and waba_id:
        account = db.query(WhatsAppAccount).filter(
            WhatsAppAccount.waba_id == str(waba_id)).first()
    if not account:
        return

    rating = (value.get("current_limit") or value.get("event") or "").upper() or None
    quality = (value.get("quality_rating") or value.get("current_quality_rating") or "").upper()
    if quality:
        account.quality_rating = quality
    if rating and rating.startswith("TIER"):
        account.messaging_tier = rating

    if quality == "RED" and account.status == WhatsAppAccount.STATUS_READY:
        account.status = WhatsAppAccount.STATUS_DISABLED
        account.status_detail = (
            "Sending is paused because WhatsApp rated this number's quality as low. "
            "This usually follows recipients blocking or reporting messages. It recovers "
            "on its own after a period of good sending — contact support before resuming."
        )
        logger.warning("[wa-webhook] org %s paused on RED quality", account.organization_id)

    db.commit()


def _ts(raw: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
