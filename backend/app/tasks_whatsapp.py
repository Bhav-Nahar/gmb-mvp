"""Celery tasks for WhatsApp review collection: bulk sending and account sync.

Bulk sending is paced on purpose. A new WhatsApp number starts on a low daily
tier and earns its way up on quality, so firing a 5,000-row CSV at Meta as fast
as the API accepts it does not deliver 5,000 messages — it collects blocks,
drops the quality rating, and throttles the tenant's number for everyone. The
throttle here is therefore a feature, not politeness.
"""
import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import func

from app.core.redis_client import get_redis as _get_redis
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

# No longer used to sleep anywhere — both send paths pace themselves by
# re-enqueuing with a countdown. Kept because tests still patch it to 0.
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


# Statuses that mean Meta accepted the message and will bill for it.
BILLED_STATUSES = [
    ReviewRequest.STATUS_SENT, ReviewRequest.STATUS_DELIVERED,
    ReviewRequest.STATUS_READ, ReviewRequest.STATUS_CLICKED,
]

def _billable_between(db, organization_id: int, since: datetime) -> int:
    """Messages Meta will bill this org for, in the period starting `since`.

    A first send is attributed to when it was SENT, not when its row was
    created. The previous version filtered on `created_at`, which put a request
    uploaded on the 30th and sent on the 1st in the wrong month — and since the
    reminder side was counted separately, such a send landed in NEITHER month's
    total and slipped past the cap entirely.

    `coalesce(sent_at, created_at)` because a handful of rows predate `sent_at`;
    falling back keeps them counted rather than silently free.

    ponytail: a row's reminders are all attributed to the period containing its
    first send, since `reminder_count` is a counter and only the LAST reminder
    has a timestamp. Reminders fire within 7 days, so the skew is bounded and
    only shows up on rows that straddle a boundary. What matters is that every
    message is counted exactly once, which is what was broken. A per-send ledger
    row is the upgrade if exact per-month attribution is ever needed.
    """
    sent_at = func.coalesce(ReviewRequest.sent_at, ReviewRequest.created_at)

    first_sends = db.query(func.count(ReviewRequest.id)).filter(
        ReviewRequest.organization_id == organization_id,
        sent_at >= since,
        ReviewRequest.status.in_(BILLED_STATUSES),
    ).scalar() or 0

    # Every reminder is its own billed marketing message, so the counter is
    # summed rather than counted — counting rows under-reports by up to 2x.
    # Attributed by last_reminder_at, falling back to the send time: a row
    # carrying reminder_count with no timestamp (older data) must still be
    # counted, or its reminders are billed by Meta and invisible here.
    reminded_at = func.coalesce(ReviewRequest.last_reminder_at, sent_at)
    reminders = db.query(
        func.coalesce(func.sum(ReviewRequest.reminder_count), 0),
    ).filter(
        ReviewRequest.organization_id == organization_id,
        reminded_at >= since,
    ).scalar() or 0

    return int(first_sends) + int(reminders)


def _sent_today(db, organization_id: int) -> int:
    """Messages Meta accepted from this org in the last 24h — the tier cap."""
    return _billable_between(db, organization_id,
                             datetime.now(timezone.utc) - timedelta(hours=24))


def billable_this_month(db, organization_id: int) -> int:
    """Messages Meta will bill this org for, this calendar month.

    Every reminder is a separate billed marketing message, so reminders are
    counted alongside first sends. Both are counted by their SEND time: the
    previous version filtered on `created_at` and summed `reminder_count`, which
    attributed a reminder to the month the request was uploaded rather than the
    month Meta billed it — so spend that crossed a month boundary was counted in
    neither month, and the cap let the tenant past it.
    """
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0,
                                               second=0, microsecond=0)
    return _billable_between(db, organization_id, start)


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

# Reminders are chunked and re-enqueued for the same reason campaigns are: this
# loop used to take 500 rows and sleep SEND_INTERVAL_SECONDS between each, which
# held a worker thread for up to 16 minutes every hour. The pacing that matters
# (not firing hundreds of marketing messages in one burst) is preserved by the
# countdown between chunks, not by sleeping inside one.
REMINDER_CHUNK = 20
REMINDER_CHUNK_INTERVAL_SECONDS = 40


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
        ).order_by(ReviewRequest.id).limit(REMINDER_CHUNK).all()

        # Hoisted out of the loop: a chunk is nearly always one or two orgs, and
        # re-querying the account, the location and both spend aggregates per row
        # was ~4 queries a row (two of them COUNTs) for answers that do not change
        # within a chunk. Spend is re-read per org after each send instead.
        accounts: dict[int, WhatsAppAccount | None] = {}
        locations: dict[int, Location | None] = {}
        spend: dict[int, tuple[int, int]] = {}

        def _account_for_org(org_id: int):
            if org_id not in accounts:
                accounts[org_id] = db.query(WhatsAppAccount).filter(
                    WhatsAppAccount.organization_id == org_id).first()
            return accounts[org_id]

        def _location(loc_id: int):
            if loc_id not in locations:
                locations[loc_id] = db.query(Location).filter(
                    Location.id == loc_id).first()
            return locations[loc_id]

        for row in rows:
            account = _account_for_org(row.organization_id)
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
            # answer to the same two ceilings. Read once per org, then advanced
            # locally after each send — a chunk cannot cross a cap unnoticed, and
            # it costs two aggregates per org instead of two per row.
            if row.organization_id not in spend:
                spend[row.organization_id] = (_sent_today(db, row.organization_id),
                                              billable_this_month(db, row.organization_id))
            today, month = spend[row.organization_id]
            if today >= (account.daily_send_limit or DEFAULT_DAILY_CAP):
                summary["capped"] += 1
                continue
            if month >= monthly_limit(account):
                summary["capped"] += 1
                continue

            location = _location(row.location_id)
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
            spend[row.organization_id] = (today + 1, month + 1)

        # A full chunk means there is probably more waiting. Re-enqueue rather
        # than waiting for the next hourly tick, so a large backlog still drains
        # today — the rows stay eligible either way, this only sets the pace.
        if len(rows) >= REMINDER_CHUNK and summary["reminded"]:
            celery.send_task("app.tasks_whatsapp.send_review_reminders_task",
                             countdown=REMINDER_CHUNK_INTERVAL_SECONDS)
            summary["requeued"] = True

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


# Rows deleted per statement. Small enough that the DELETE never holds a lock
# long enough to stall an inbound webhook write, which is the only thing that
# competes with it on this table.
PURGE_BATCH = 5_000


@shared_task(name="app.tasks_whatsapp.purge_old_messages_task")
def purge_old_messages_task() -> str:
    """Delete inbox messages past the retention window.

    These rows are a third party's personal data — a customer's number and what
    they typed — so keeping them indefinitely is a compliance problem long
    before it is a disk problem. Retention is therefore on by default rather
    than something a tenant has to ask for.

    Deleted in batches: one unbounded DELETE over a year of a large tenant's
    messages would hold row locks long enough to make inbound webhooks time
    out, and a webhook Meta cannot deliver fast is a webhook it retries.
    """
    from app.core.config import settings
    from app.models.whatsapp_message import WhatsAppMessage

    days = settings.WHATSAPP_MESSAGE_RETENTION_DAYS
    if not days or days <= 0:
        return "skipped: retention disabled"

    r = _get_redis()
    lock = r.lock("lock:purge_whatsapp_messages", timeout=1800)
    if not lock.acquire(blocking=False):
        return "skipped: another purge in progress"

    db = SessionLocal()
    deleted = 0
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        while True:
            ids = [row[0] for row in db.query(WhatsAppMessage.id).filter(
                WhatsAppMessage.created_at < cutoff,
            ).limit(PURGE_BATCH).all()]
            if not ids:
                break
            db.query(WhatsAppMessage).filter(
                WhatsAppMessage.id.in_(ids),
            ).delete(synchronize_session=False)
            db.commit()
            deleted += len(ids)
            # A batch short of the limit means the table is drained.
            if len(ids) < PURGE_BATCH:
                break
        if deleted:
            logger.info("[wa-purge] deleted %s messages older than %s days", deleted, days)
        return f"deleted {deleted}"
    except Exception as err:  # pragma: no cover - defensive; beat retries tomorrow
        db.rollback()
        logger.exception("[wa-purge] failed: %s", err)
        return f"failed: {err}"
    finally:
        db.close()
        try:
            lock.release()
        except Exception:
            pass
