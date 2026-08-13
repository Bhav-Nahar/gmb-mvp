"""Celery tasks for WhatsApp review collection: bulk sending and account sync.

Bulk sending is paced on purpose. A new WhatsApp number starts on a low daily
tier and earns its way up on quality, so firing a 5,000-row CSV at Meta as fast
as the API accepts it does not deliver 5,000 messages — it collects blocks,
drops the quality rating, and throttles the tenant's number for everyone. The
throttle here is therefore a feature, not politeness.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import func

# Import for the side effect of configuring the Celery app, NOT for the symbol.
# @shared_task binds to whatever app is *current* when .delay() is called, and
# with no configured app loaded that default is amqp://localhost — which fails
# as "[Errno 111] Connection refused" and looks like Redis being down. main.py
# happens to import app.worker before the routers, but anything importing these
# tasks directly (a script, a test) would not.
import app.worker  # noqa: F401

from app.db.session import SessionLocal
from app.models.location import Location
from app.models.review_request import ReviewRequest
from app.models.whatsapp_account import WhatsAppAccount
from app.services import app_settings, whatsapp_service
from app.services.review_request_service import send_review_request
from app.services.whatsapp_service import WhatsAppError

logger = logging.getLogger(__name__)

# Kill switch. A flag rather than an env var so it can be flipped from the
# super-admin panel mid-incident, without a deploy — which is the only speed
# that matters when a tenant is burning their number.
FEATURE_FLAG = "whatsapp_review_collection_enabled"

# Seconds between sends. Slow enough to look like a business messaging its
# customers rather than a broadcast, and it keeps a long batch well inside any
# per-second limit without needing to model one.
SEND_INTERVAL_SECONDS = 2.0

# Fallback when Meta has not told us the tier yet. Matches the entry tier for a
# fresh number, so a first-day campaign cannot overrun it by assuming better.
DEFAULT_DAILY_CAP = 250


def _sent_today(db, organization_id: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return db.query(func.count(ReviewRequest.id)).filter(
        ReviewRequest.organization_id == organization_id,
        ReviewRequest.created_at >= since,
        ReviewRequest.status.in_([
            ReviewRequest.STATUS_SENT, ReviewRequest.STATUS_DELIVERED,
            ReviewRequest.STATUS_READ, ReviewRequest.STATUS_CLICKED,
        ]),
    ).scalar() or 0


@shared_task(name="app.tasks_whatsapp.send_review_batch_task")
def send_review_batch_task(organization_id: int, location_id: int,
                           recipients: list[dict], batch_id: str,
                           source: str = "csv") -> dict:
    """Send a batch of review requests, paced and capped.

    `recipients` is [{"phone": "...", "name": "..."}]. Every row produces a
    ReviewRequest — including skips — so the campaign view can account for every
    number that was uploaded.
    """
    db = SessionLocal()
    result = {"sent": 0, "skipped": 0, "failed": 0, "stopped": None}
    try:
        if not app_settings.get_flag(db, FEATURE_FLAG, default=True):
            result["stopped"] = "feature_disabled"
            return result

        account = db.query(WhatsAppAccount).filter(
            WhatsAppAccount.organization_id == organization_id,
        ).first()
        if not account or not account.can_send:
            result["stopped"] = f"whatsapp_not_ready:{account.status if account else 'missing'}"
            return result

        cap = account.daily_send_limit or DEFAULT_DAILY_CAP
        already = _sent_today(db, organization_id)

        for row in recipients:
            # Re-read the account every iteration: a RED quality webhook can
            # land mid-batch, and continuing to send after Meta has flagged the
            # number is exactly how a throttle becomes a ban.
            db.refresh(account)
            if not account.can_send:
                result["stopped"] = f"paused_mid_batch:{account.status}"
                break
            if already + result["sent"] >= cap:
                result["stopped"] = "daily_cap_reached"
                break

            try:
                request = send_review_request(
                    db,
                    organization_id=organization_id,
                    location_id=location_id,
                    phone_raw=row.get("phone", ""),
                    customer_name=row.get("name"),
                    source=source,
                    batch_id=batch_id,
                )
            except (ValueError, WhatsAppError) as err:
                logger.warning("[wa-batch] %s: %s", batch_id, err)
                result["failed"] += 1
                continue

            if request.status == ReviewRequest.STATUS_SENT:
                result["sent"] += 1
                time.sleep(SEND_INTERVAL_SECONDS)
            elif request.status == ReviewRequest.STATUS_SKIPPED:
                result["skipped"] += 1      # suppressed / capped / unusable number
            else:
                result["failed"] += 1

        logger.info("[wa-batch] %s org=%s %s", batch_id, organization_id, result)
        return result
    finally:
        db.close()


# Reminder policy. Two reminders, roughly a day apart, and never after a click.
# Someone who tapped the link has done what was asked; messaging them again is
# how a review request becomes spam.
MAX_REMINDERS = 2
REMINDER_AFTER_HOURS = 24


@shared_task(name="app.tasks_whatsapp.send_review_reminders_task")
def send_review_reminders_task() -> dict:
    """Nudge customers who were messaged but haven't opened the review link.

    Reuses the original row and its token, so the link already sitting in the
    customer's chat stays valid and a click is still attributed to the first ask.
    """
    db = SessionLocal()
    summary = {"reminded": 0, "failed": 0}
    try:
        if not app_settings.get_flag(db, FEATURE_FLAG, default=True):
            return summary

        now = datetime.now(timezone.utc)
        rows = db.query(ReviewRequest).filter(
            ReviewRequest.status.in_([
                ReviewRequest.STATUS_SENT, ReviewRequest.STATUS_DELIVERED,
                ReviewRequest.STATUS_READ,
            ]),
            ReviewRequest.clicked_at.is_(None),
            ReviewRequest.reminder_count < MAX_REMINDERS,
            ReviewRequest.sent_at.isnot(None),
            # Space each reminder a day from the LAST contact, not from the
            # original send, or both reminders would fire in the same hour.
            func.coalesce(ReviewRequest.last_reminder_at, ReviewRequest.sent_at)
            <= now - timedelta(hours=REMINDER_AFTER_HOURS),
            # Nothing older than a week: a review ask that stale reads as a
            # random message from a business the customer has forgotten.
            ReviewRequest.sent_at >= now - timedelta(days=7),
        ).order_by(ReviewRequest.id).limit(500).all()

        for row in rows:
            account = db.query(WhatsAppAccount).filter(
                WhatsAppAccount.organization_id == row.organization_id).first()
            if not account or not account.can_send:
                continue
            location = db.query(Location).filter(Location.id == row.location_id).first()
            if not location:
                continue
            try:
                wamid = whatsapp_service.send_template(
                    account,
                    to=row.phone,
                    template_name=account.template_name,
                    body_params=[row.customer_name or "there", location.location_name],
                    button_url_param=row.token,
                )
            except WhatsAppError as err:
                summary["failed"] += 1
                logger.warning("[wa-reminder] row=%s code=%s", row.id, err.code)
                # Burn the attempt anyway. Retrying a failing number every hour
                # is how an account gets rate-limited.
                row.reminder_count += 1
                row.last_reminder_at = now
                db.commit()
                continue

            row.wamid = wamid
            row.reminder_count += 1
            row.last_reminder_at = now
            row.status = ReviewRequest.STATUS_SENT   # a fresh send, awaiting delivery again
            db.commit()
            summary["reminded"] += 1
            time.sleep(SEND_INTERVAL_SECONDS)

        logger.info("[wa-reminder] %s", summary)
        return summary
    finally:
        db.close()


@shared_task(name="app.tasks_whatsapp.sync_whatsapp_accounts_task")
def sync_whatsapp_accounts_task() -> dict:
    """Refresh template approval, quality rating and send tier for every account.

    The webhook reports these changes in real time, but only for events that fire
    while we are subscribed and reachable. This is the backstop that repairs the
    state after a deploy, an outage, or a missed callback — without it an account
    whose approval webhook was dropped stays "pending" forever and the tenant
    concludes the product is broken.
    """
    db = SessionLocal()
    summary = {"checked": 0, "became_ready": 0, "errors": 0}
    try:
        accounts = db.query(WhatsAppAccount).filter(
            WhatsAppAccount.status.notin_([
                WhatsAppAccount.STATUS_PENDING, WhatsAppAccount.STATUS_DISABLED,
            ]),
        ).all()

        for account in accounts:
            summary["checked"] += 1
            try:
                info = whatsapp_service.get_phone_number_info(account)
                if info:
                    account.quality_rating = info.get("quality_rating") or account.quality_rating
                    account.messaging_tier = info.get("messaging_limit_tier") or account.messaging_tier
                    account.display_phone_number = (info.get("display_phone_number")
                                                    or account.display_phone_number)
                    account.verified_name = info.get("verified_name") or account.verified_name
                    account.daily_send_limit = _tier_to_cap(account.messaging_tier)

                if account.template_name and account.template_status != "APPROVED":
                    status = whatsapp_service.get_template_status(account, account.template_name)
                    if status:
                        account.template_status = status
                        if (status == "APPROVED"
                                and account.status == WhatsAppAccount.STATUS_TEMPLATE_PENDING):
                            account.status = WhatsAppAccount.STATUS_READY
                            account.status_detail = None
                            summary["became_ready"] += 1

                account.last_synced_at = datetime.now(timezone.utc)
                db.commit()
            except WhatsAppError as err:
                summary["errors"] += 1
                logger.warning("[wa-sync] org %s: %s", account.organization_id, err)
                db.rollback()

        logger.info("[wa-sync] %s", summary)
        return summary
    finally:
        db.close()


def _tier_to_cap(tier: str | None) -> int | None:
    """Meta's tier name -> messages per 24h.

    Reported as a name, not a number, so the mapping lives here. An unknown tier
    returns None rather than a guess — the caller then falls back to the entry
    cap, which errs on the side of sending too few.
    """
    return {
        "TIER_50": 50,
        "TIER_250": 250,
        "TIER_1K": 1_000,
        "TIER_10K": 10_000,
        "TIER_100K": 100_000,
        "TIER_UNLIMITED": 1_000_000,
    }.get((tier or "").upper())
