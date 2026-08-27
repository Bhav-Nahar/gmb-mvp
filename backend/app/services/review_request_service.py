"""Create and send one review request.

The order of checks here is the compliance story, not an optimisation: a number
is normalised, then checked against suppression, then against the frequency
cap, and only then does a message get sent. Every skip is recorded as a row so
"why didn't this customer get it" is answerable months later.
"""
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.location import Location
from app.models.review_request import ReviewRequest
from app.models.review_suppression import ReviewSuppression
from app.models.whatsapp_account import WhatsAppAccount
from app.services import whatsapp_service
from app.services.whatsapp_service import WhatsAppError, normalize_phone
from app.services import whatsapp_errors

logger = logging.getLogger(__name__)

# Never ask the same person for a review twice within this window. Someone who
# ignored the first ask will not be persuaded by a second one — they will block
# the sender, and blocks are what destroy a tenant's quality rating and with it
# their ability to message anyone.
#
# Configurable because the right value differs between testing (short) and
# production (long). Read through a function rather than captured at import, so
# a change in .env takes effect on restart and tests can monkeypatch it.
def cooldown_hours() -> int:
    return max(0, int(getattr(settings, "REVIEW_REQUEST_COOLDOWN_HOURS", 24)))

# Which failures are permanent lives in whatsapp_errors and nowhere else. A
# second copy here drifted from it once already — the webhook suppressed a code
# this path did not — and "is this number dead" must not depend on which code
# path noticed.


def new_token() -> str:
    """16 random bytes, URL-safe. This is the only thing protecting a
    recipient's link, so it must not be derived from the row id or the phone."""
    return secrets.token_urlsafe(16)


def is_suppressed(db: Session, organization_id: int, phone: str) -> bool:
    """Has this number opted out — on any plausible formatting of it?

    Exact match first, then the last 8 digits. The suffix test exists because
    the two sides of this comparison come from different places: the number we
    hold was typed or uploaded by the tenant, while an opt-out is recorded
    against the `wa_id` Meta reports on the inbound message, and those are not
    guaranteed to be the same string. Trunk-prefix zeros and country quirks
    (Argentina's 9, Mexico's 1) are the usual causes.

    Getting this wrong is not a cosmetic bug: a STOP recorded under one
    spelling and a campaign sent to the other means messaging someone who
    withdrew consent. So the check is deliberately loose — a false positive
    costs one unsent review request, a false negative is a policy breach.

    Last 8 digits, not fewer: 8 is short enough to survive a country-code or
    trunk difference and long enough that two real customers of one tenant
    colliding is not a practical concern.
    """
    if db.query(ReviewSuppression.id).filter(
        ReviewSuppression.organization_id == organization_id,
        ReviewSuppression.phone == phone,
    ).first() is not None:
        return True

    digits = re.sub(r"\D", "", str(phone or ""))
    if len(digits) < 8:
        return False
    # Suffix match. A trailing LIKE cannot use the btree index, but this scans
    # one organization's suppression list — hundreds of rows, not the table.
    return db.query(ReviewSuppression.id).filter(
        ReviewSuppression.organization_id == organization_id,
        ReviewSuppression.phone.like(f"%{digits[-8:]}"),
    ).first() is not None


def recently_messaged(db: Session, organization_id: int, phone: str) -> bool:
    hours = cooldown_hours()
    if hours <= 0:                       # 0 disables the cap entirely (testing)
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return db.query(ReviewRequest.id).filter(
        ReviewRequest.organization_id == organization_id,
        ReviewRequest.phone == phone,
        ReviewRequest.created_at >= cutoff,
        # A skipped row is not a message anyone received, so it must not block
        # a later genuine send.
        ReviewRequest.status != ReviewRequest.STATUS_SKIPPED,
    ).first() is not None


def suppress(db: Session, organization_id: int, phone: str, reason: str,
             note: Optional[str] = None) -> None:
    """Idempotent — the unique constraint on (org, phone) is the real guard."""
    if is_suppressed(db, organization_id, phone):
        return
    db.add(ReviewSuppression(
        organization_id=organization_id, phone=phone, reason=reason, note=note,
    ))
    db.commit()


def send_review_request(
    db: Session,
    *,
    organization_id: int,
    location_id: int,
    phone_raw: str,
    customer_name: Optional[str] = None,
    source: str = "manual",
    batch_id: Optional[str] = None,
    default_country_code: str = "91",
    is_test: bool = False,
) -> ReviewRequest:
    """Send one review request. Always returns a row — including for skips, so
    the campaign view can show exactly what happened to every number uploaded.

    `is_test` is the setup smoke test an admin sends to their own phone. It is
    the one send allowed before the account is fully unlocked — that is the whole
    point of it — and it ignores the frequency cap, because an admin testing
    twice in a day is not a customer being pestered. Suppression is still
    honoured: if that number has opted out, it has opted out.
    """
    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == organization_id,   # tenant scoping, not decoration
    ).first()
    if not location:
        raise ValueError(f"Location {location_id} not found for organization {organization_id}")

    phone = normalize_phone(phone_raw, default_country_code=default_country_code)
    if not phone:
        return _record(db, organization_id, location_id, str(phone_raw)[:32], customer_name,
                       source, batch_id, ReviewRequest.STATUS_SKIPPED,
                       error_code="invalid_phone",
                       error_detail=f"Could not read a phone number from {phone_raw!r}")

    if is_suppressed(db, organization_id, phone):
        return _record(db, organization_id, location_id, phone, customer_name, source, batch_id,
                       ReviewRequest.STATUS_SKIPPED, error_code="suppressed",
                       error_detail="This number has opted out or is on the do-not-contact list")

    if not is_test and recently_messaged(db, organization_id, phone):
        return _record(db, organization_id, location_id, phone, customer_name, source, batch_id,
                       ReviewRequest.STATUS_SKIPPED, error_code="frequency_cap",
                       error_detail=_cooldown_message())

    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.organization_id == organization_id,
    ).first()
    ready = account is not None and (account.can_test if is_test else account.can_send)
    if not ready:
        state = account.status if account else "not connected"
        raise ValueError(f"WhatsApp is not ready for this organization ({state})")

    row = _record(db, organization_id, location_id, phone, customer_name, source, batch_id,
                  ReviewRequest.STATUS_QUEUED)

    try:
        wamid = whatsapp_service.send_template(
            account,
            to=phone,
            template_name=account.template_name,
            # Index-matched to the approved template:
            #   {{1}} customer first name, {{2}} the business/location name
            body_params=[customer_name or "there", location.location_name],
            # The dynamic URL button suffix — turns the fixed https://pinzo.io/r/
            # base into this recipient's own link.
            button_url_param=row.token,
        )
    except WhatsAppError as err:
        row.status = ReviewRequest.STATUS_FAILED
        row.error_code = str(err.code) if err.code is not None else None
        # Prefer our plain-English mapping over Meta's prose: this string is read
        # by the tenant in the campaign history, and "131026" explains nothing.
        row.error_detail = (whatsapp_errors.explain(err.code).message
                            if whatsapp_errors.is_known(err.code)
                            else (err.detail or str(err)))[:1000]
        db.commit()
        # A billing failure is not this recipient's fault and will hit every
        # remaining number identically. Park the account so the batch loop stops
        # on its next iteration and the tenant is told what to fix, instead of
        # grinding through the list collecting the same error 500 times.
        text = f"{err.detail or ''} {err.user_msg or ''} {err}"
        if whatsapp_errors.is_billing(err.code, text):
            account.status = WhatsAppAccount.STATUS_PAYMENT_REQUIRED
            account.status_detail = whatsapp_errors.explain(err.code).message
            db.commit()
            logger.error("[review-request] org=%s parked: payment required (code=%s)",
                         organization_id, err.code)
            return row

        # Access revoked. Park it the same way — every remaining number in the
        # batch will fail identically, and the tenant needs to reconnect, not to
        # wonder why 400 messages failed.
        if whatsapp_errors.is_reauth(err.code, text):
            account.status = WhatsAppAccount.STATUS_REAUTH_REQUIRED
            account.status_detail = whatsapp_errors.explain(190).message
            db.commit()
            logger.error("[review-request] org=%s parked: reconnect required", organization_id)
            return row

        if whatsapp_errors.is_permanent(err.code):
            suppress(db, organization_id, phone, ReviewSuppression.REASON_FAILED,
                     note=f"Meta error {err.code}")
        logger.warning("[review-request] send failed org=%s phone=%s code=%s",
                       organization_id, phone, err.code)
        return row

    row.status = ReviewRequest.STATUS_SENT
    row.wamid = wamid
    row.sent_at = datetime.now(timezone.utc)
    # A send Meta accepted is the only available proof that this account can
    # actually be billed — which is what the pre-campaign test send is for. Any
    # successful send counts, so an account that was already working keeps
    # working after this gate was introduced.
    account.verified_send_at = account.verified_send_at or row.sent_at
    db.commit()
    return row


def _record(db: Session, organization_id: int, location_id: int, phone: str,
            customer_name: Optional[str], source: str, batch_id: Optional[str],
            status: str, error_code: Optional[str] = None,
            error_detail: Optional[str] = None) -> ReviewRequest:
    row = ReviewRequest(
        organization_id=organization_id,
        location_id=location_id,
        phone=phone,
        customer_name=customer_name,
        token=new_token(),
        status=status,
        source=source,
        batch_id=batch_id,
        error_code=error_code,
        error_detail=error_detail,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _cooldown_message() -> str:
    """Say the window in the unit a human would — "2 days", not "48 hours"."""
    hours = cooldown_hours()
    if hours % 24 == 0 and hours >= 24:
        days = hours // 24
        return f"Already asked within the last {days} day{'s' if days != 1 else ''}"
    return f"Already asked within the last {hours} hour{'s' if hours != 1 else ''}"
