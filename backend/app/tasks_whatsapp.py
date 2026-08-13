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

from app.db.session import SessionLocal
from app.models.location import Location
from app.models.review_request import ReviewRequest
from app.models.whatsapp_account import WhatsAppAccount
from app.services import app_settings, review_request_service as rr, whatsapp_service
from app.services import whatsapp_onboarding_service as onboarding
from app.services.review_request_service import send_review_request
from app.services.whatsapp_service import WhatsAppError
# The CONFIGURED Celery app, both to re-enqueue chunks and for the import side
# effect: @shared_task binds to whatever app is *current* when the task is
# published, and with no configured app loaded that default is amqp://localhost,
# which fails as "[Errno 111] Connection refused" and looks like Redis is down.
from app.worker import celery

logger = logging.getLogger(__name__)

# Kill switch. A flag rather than an env var so it can be flipped from the
# super-admin panel mid-incident, without a deploy — which is the only speed
# that matters when a tenant is burning their number.
FEATURE_FLAG = "whatsapp_review_collection_enabled"

# Pacing. A batch used to sleep between every message inside one task, which
# meant a 2,000-row campaign held a worker thread for over an hour — ten of those
# and the pool is gone, taking billing, syncs and every other queued job with it.
# So a task now sends a small CHUNK and re-enqueues itself with a countdown: the
# same average rate (one message every couple of seconds, which is what keeps a
# tenant looking like a business rather than a broadcaster), a thread held for
# seconds instead of hours.
#
# Chunked rather than one-message-per-task on purpose: production Redis is billed
# per command, and 2,000 round trips per campaign is a cost with nothing to show
# for it.
CHUNK_SIZE = 10
CHUNK_INTERVAL_SECONDS = 20

# Kept for the reminder loop, which sends a handful of messages at a time.
SEND_INTERVAL_SECONDS = 2.0

# Quiet hours. A review ask is MARKETING-category, and a marketing WhatsApp at
# 1am does not get read — it gets reported. Enough reports and Meta pauses the
# template or throttles the number, which costs the tenant every OTHER customer
# too. So a campaign uploaded at midnight waits for morning instead of sending.
#
# ponytail: hardcoded IST, because every tenant is in India today (rupee pricing,
# GST, AEO_LOCATION_CODE=2356). When a tenant lands outside it, take the tz from
# the location rather than adding a setting nobody in India would ever change.
IST = timezone(timedelta(hours=5, minutes=30))
SEND_WINDOW_START_HOUR = 9    # 09:00 IST, inclusive
SEND_WINDOW_END_HOUR = 20     # 20:00 IST, exclusive — 19:59 sends, 20:00 waits


def seconds_until_send_window(now: datetime | None = None) -> int:
    """0 when it's fine to send right now, else seconds until the window opens."""
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    if SEND_WINDOW_START_HOUR <= now.hour < SEND_WINDOW_END_HOUR:
        return 0
    opens = now.replace(hour=SEND_WINDOW_START_HOUR, minute=0, second=0, microsecond=0)
    if now.hour >= SEND_WINDOW_END_HOUR:
        opens += timedelta(days=1)      # tonight -> tomorrow morning
    # Never return 0 from this branch: a 0 countdown would re-run immediately and
    # spin the queue until 09:00.
    return max(int((opens - now).total_seconds()), 60)

# Fallback when Meta has not told us the tier yet. Matches the entry tier for a
# fresh number, so a first-day campaign cannot overrun it by assuming better.
DEFAULT_DAILY_CAP = 250

# Default ceiling on messages Meta may bill one tenant for in a calendar month,
# overridable per account. Meta enforces a throughput tier, never a spend limit,
# so without this a mistaken upload is an unbounded charge on the tenant's card —
# and it is their card, which makes it our problem to bound.
DEFAULT_MONTHLY_LIMIT = 3000


def _sent_today(db, organization_id: int) -> int:
    """Messages Meta accepted from this org in the last 24h.

    Reminders reuse their original row, so they are counted by their reminder
    timestamps rather than by row creation — otherwise a day of reminders is
    invisible to the cap and quietly overruns the tenant's Meta tier.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    delivered = [
        ReviewRequest.STATUS_SENT, ReviewRequest.STATUS_DELIVERED,
        ReviewRequest.STATUS_READ, ReviewRequest.STATUS_CLICKED,
    ]
    first_sends = db.query(func.count(ReviewRequest.id)).filter(
        ReviewRequest.organization_id == organization_id,
        ReviewRequest.created_at >= since,
        ReviewRequest.status.in_(delivered),
    ).scalar() or 0
    reminders = db.query(func.count(ReviewRequest.id)).filter(
        ReviewRequest.organization_id == organization_id,
        ReviewRequest.last_reminder_at >= since,
    ).scalar() or 0
    return first_sends + reminders


def billable_this_month(db, organization_id: int) -> int:
    """Messages Meta will bill this org for, this calendar month.

    Every reminder is a separate billed marketing message, so `reminder_count` is
    added rather than ignored: counting rows alone under-reports the tenant's bill
    by up to three times, which is worse than not showing a number at all.
    """
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.query(
        func.count(ReviewRequest.id),
        func.coalesce(func.sum(ReviewRequest.reminder_count), 0),
    ).filter(
        ReviewRequest.organization_id == organization_id,
        ReviewRequest.created_at >= start,
        ReviewRequest.status.in_([
            ReviewRequest.STATUS_SENT, ReviewRequest.STATUS_DELIVERED,
            ReviewRequest.STATUS_READ, ReviewRequest.STATUS_CLICKED,
        ]),
    ).first()
    return int(rows[0] or 0) + int(rows[1] or 0)


def monthly_limit(account: WhatsAppAccount) -> int:
    return account.monthly_message_limit or DEFAULT_MONTHLY_LIMIT


@shared_task(name="app.tasks_whatsapp.send_review_batch_task")
def send_review_batch_task(organization_id: int, location_id: int,
                           recipients: list[dict], batch_id: str,
                           source: str = "csv") -> dict:
    """Send up to CHUNK_SIZE review requests, then re-enqueue the rest.

    `recipients` is [{"phone": "...", "name": "..."}]. Every row produces a
    ReviewRequest — including skips — so the campaign view can account for every
    number that was uploaded. The returned counts are for THIS chunk; the
    campaign total is the `batch_id` rows in the database, which is the only
    number that survives a worker restart anyway.
    """
    db = SessionLocal()
    result = {"sent": 0, "skipped": 0, "failed": 0, "stopped": None, "remaining": 0}
    try:
        if not app_settings.get_flag(db, FEATURE_FLAG, default=True):
            result["stopped"] = "feature_disabled"
            return result

        # Outside quiet hours the whole chunk waits — deferred, NOT dropped, so
        # no ReviewRequest rows are written and the campaign resumes intact at
        # 09:00. (`stopped` is deliberately left None: that path records every
        # remaining recipient as skipped, which is the opposite of waiting.)
        delay = seconds_until_send_window()
        if delay:
            celery.send_task(
                "app.tasks_whatsapp.send_review_batch_task",
                kwargs={"organization_id": organization_id, "location_id": location_id,
                        "recipients": recipients, "batch_id": batch_id, "source": source},
                countdown=delay,
            )
            result["deferred_seconds"] = delay
            result["remaining"] = len(recipients)
            logger.info("[wa-batch] %s org=%s outside send window, %s recipients wait %ss",
                        batch_id, organization_id, len(recipients), delay)
            return result

        account = db.query(WhatsAppAccount).filter(
            WhatsAppAccount.organization_id == organization_id,
        ).first()
        if not account or not account.can_send:
            result["stopped"] = f"whatsapp_not_ready:{account.status if account else 'missing'}"
            return result

        cap = account.daily_send_limit or DEFAULT_DAILY_CAP
        already = _sent_today(db, organization_id)
        month_cap = monthly_limit(account)
        month_used = billable_this_month(db, organization_id)

        chunk, rest = recipients[:CHUNK_SIZE], recipients[CHUNK_SIZE:]

        unreached: list[dict] = []
        for position, row in enumerate(chunk):
            # Re-read the account every iteration: a RED quality webhook can
            # land mid-batch, and continuing to send after Meta has flagged the
            # number is exactly how a throttle becomes a ban.
            db.refresh(account)
            if not account.can_send:
                result["stopped"] = f"paused_mid_batch:{account.status}"
            elif already + result["sent"] >= cap:
                result["stopped"] = "daily_cap_reached"
            # The tenant's own money. Stopping is the only safe direction here:
            # an overrun cannot be refunded by us, and Meta bills their card.
            elif month_used + result["sent"] >= month_cap:
                result["stopped"] = "monthly_cap_reached"
            if result["stopped"]:
                # Everything from here on, in this chunk and after it.
                unreached = chunk[position:]
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
            elif request.status == ReviewRequest.STATUS_SKIPPED:
                result["skipped"] += 1      # suppressed / capped / unusable number
            else:
                result["failed"] += 1

        # A stop reason applies to the whole campaign, not just this chunk — the
        # account is paused, the day is spent, or the month is. Dropping the
        # remainder is deliberate: re-queueing it would spin until midnight.
        if rest and not result["stopped"]:
            result["remaining"] = len(rest)
            celery.send_task(
                "app.tasks_whatsapp.send_review_batch_task",
                kwargs={
                    "organization_id": organization_id,
                    "location_id": location_id,
                    "recipients": rest,
                    "batch_id": batch_id,
                    "source": source,
                },
                countdown=CHUNK_INTERVAL_SECONDS,
            )
        elif result["stopped"]:
            # Every uploaded number gets a row, including the ones we never
            # reached — otherwise "you said 2,000 and I see 340" has no answer.
            dropped = unreached + rest
            if dropped:
                _record_dropped(db, organization_id, location_id, dropped, batch_id, source,
                                result["stopped"])
                result["skipped"] += len(dropped)
                logger.warning("[wa-batch] %s org=%s dropped %s recipients: %s",
                               batch_id, organization_id, len(dropped), result["stopped"])

        logger.info("[wa-batch] %s org=%s %s", batch_id, organization_id, result)
        return result
    finally:
        db.close()


STOP_REASON_COPY = {
    "daily_cap_reached": "Not sent — your WhatsApp daily send limit was reached. "
                         "Upload these again tomorrow.",
    "monthly_cap_reached": "Not sent — this month's message limit for your account was reached.",
    "paused_mid_batch": "Not sent — sending was paused partway through this campaign.",
}


def _record_dropped(db, organization_id: int, location_id: int, rest: list[dict],
                    batch_id: str, source: str, reason: str) -> None:
    detail = STOP_REASON_COPY.get(reason.split(":")[0], f"Not sent — {reason}.")
    rows = []
    for row in rest:
        raw = str(row.get("phone") or "")
        rows.append(ReviewRequest(
            organization_id=organization_id,
            location_id=location_id,
            phone=whatsapp_service.normalize_phone(raw) or raw[:32],
            customer_name=row.get("name"),
            token=rr.new_token(),
            status=ReviewRequest.STATUS_SKIPPED,
            source=source,
            batch_id=batch_id,
            error_code=reason.split(":")[0],
            error_detail=detail,
        ))
    db.bulk_save_objects(rows)
    db.commit()


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
    summary = {"reminded": 0, "failed": 0, "suppressed": 0, "capped": 0}
    try:
        if not app_settings.get_flag(db, FEATURE_FLAG, default=True):
            return summary

        # Same quiet hours as a campaign. No re-enqueue needed: beat runs this
        # again shortly, and the rows stay eligible — a reminder is defined by
        # "24h since last contact", not by which tick noticed it.
        if seconds_until_send_window():
            summary["deferred"] = True
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

            # THE opt-out check. A customer who replied STOP after the first ask
            # is suppressed by the webhook, and a reminder to them is both a
            # policy breach and the fastest route to a block — which costs the
            # tenant every other customer too. This is why reminders read the
            # suppression list rather than trusting the original send.
            if rr.is_suppressed(db, row.organization_id, row.phone):
                summary["suppressed"] += 1
                # Burn the reminders so this row stops being picked up hourly.
                row.reminder_count = MAX_REMINDERS
                db.commit()
                continue

            # Reminders are billed and throttled exactly like first sends, so they
            # answer to the same two ceilings. Checked per row because a long
            # reminder run can cross the line partway through.
            if _sent_today(db, row.organization_id) >= (account.daily_send_limit
                                                        or DEFAULT_DAILY_CAP):
                summary["capped"] += 1
                continue
            if billable_this_month(db, row.organization_id) >= monthly_limit(account):
                summary["capped"] += 1
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
        # `disabled` and `reauth_required` are INCLUDED. They used to be skipped,
        # which meant a number whose quality Meta had already restored, or a
        # connection that started working again, stayed switched off forever —
        # nothing else in the system was ever going to notice. Only `pending` is
        # skipped, because it has no token or ids to check yet.
        accounts = db.query(WhatsAppAccount).filter(
            WhatsAppAccount.status != WhatsAppAccount.STATUS_PENDING,
        ).all()

        for account in accounts:
            summary["checked"] += 1
            try:
                # `unpark_payment` stays off here: whether a card works is only
                # knowable by sending, so unparking on a timer would show a
                # tenant "Ready" while they still cannot send. That recovery is
                # driven by the tenant pressing "Check again" instead.
                if onboarding.refresh_account(db, account):
                    summary["became_ready"] += 1
                account.daily_send_limit = _tier_to_cap(account.messaging_tier)
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
