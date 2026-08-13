"""Create and send one review request.

The order of checks here is the compliance story, not an optimisation: a number
is normalised, then checked against suppression, then against the frequency
cap, and only then does a message get sent. Every skip is recorded as a row so
"why didn't this customer get it" is answerable months later.
"""
import logging
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

# Meta error codes that mean "this number will never work", as opposed to a
# transient failure. These get suppressed permanently: retrying them burns
# quality score for a delivery that cannot happen.
PERMANENT_FAILURE_CODES = {
    131026,   # message undeliverable — not a WhatsApp user
    131047,   # re-engagement required (outside the window with no valid template)
}


def new_token() -> str:
    """16 random bytes, URL-safe. This is the only thing protecting a
    recipient's link, so it must not be derived from the row id or the phone."""
    return secrets.token_urlsafe(16)


def is_suppressed(db: Session, organization_id: int, phone: str) -> bool:
    return db.query(ReviewSuppression.id).filter(
        ReviewSuppression.organization_id == organization_id,
        ReviewSuppression.phone == phone,
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
) -> ReviewRequest:
    """Send one review request. Always returns a row — including for skips, so
    the campaign view can show exactly what happened to every number uploaded.
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

    if recently_messaged(db, organization_id, phone):
        return _record(db, organization_id, location_id, phone, customer_name, source, batch_id,
                       ReviewRequest.STATUS_SKIPPED, error_code="frequency_cap",
                       error_detail=_cooldown_message())

    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.organization_id == organization_id,
    ).first()
    if not account or not account.can_send:
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
        row.error_detail = (err.detail or str(err))[:1000]
        db.commit()
        # A billing failure is not this recipient's fault and will hit every
        # remaining number identically. Park the account so the batch loop stops
        # on its next iteration and the tenant is told what to fix, instead of
        # grinding through the list collecting the same error 500 times.
        if whatsapp_errors.is_billing(err.code, f"{err.detail or ''} {err}"):
            account.status = WhatsAppAccount.STATUS_PAYMENT_REQUIRED
            account.status_detail = whatsapp_errors.explain(err.code).message
            db.commit()
            logger.error("[review-request] org=%s parked: payment required (code=%s)",
                         organization_id, err.code)
            return row

        if err.code in PERMANENT_FAILURE_CODES:
            suppress(db, organization_id, phone, ReviewSuppression.REASON_FAILED,
                     note=f"Meta error {err.code}")
        logger.warning("[review-request] send failed org=%s phone=%s code=%s",
                       organization_id, phone, err.code)
        return row

    row.status = ReviewRequest.STATUS_SENT
    row.wamid = wamid
    row.sent_at = datetime.now(timezone.utc)
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
