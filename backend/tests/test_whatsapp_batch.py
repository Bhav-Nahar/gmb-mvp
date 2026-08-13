"""Bulk sending: pacing, the two ceilings, and stopping when told to.

Every limit here protects something that cannot be undone afterwards — the
tenant's Meta bill, their number's quality rating, and a worker pool that the
rest of the product shares.
"""
from datetime import datetime, timezone

import pytest

import app.tasks_whatsapp as tasks
from app.core.security import encrypt_token
from app.models.location import Location
from app.models.organization import Organization
from app.models.review_request import ReviewRequest
from app.models.whatsapp_account import WhatsAppAccount
from app.services import whatsapp_service
from app.services.whatsapp_service import WhatsAppError


@pytest.fixture
def wired(db, monkeypatch):
    """A ready org, a captured sender, and re-enqueues run inline."""
    org = Organization(name="Batch Co")
    db.add(org)
    db.flush()
    loc = Location(organization_id=org.id, google_location_id="locations/1",
                   location_name="Store")
    db.add(loc)
    account = WhatsAppAccount(
        organization_id=org.id, waba_id="waba-1", phone_number_id="phone-1",
        access_token=encrypt_token("t"), template_name="pinzo_review_request",
        template_status="APPROVED", status=WhatsAppAccount.STATUS_READY,
        app_subscribed=True, verified_send_at=datetime.now(timezone.utc),
        daily_send_limit=250)
    db.add(account)
    db.commit()

    # Pin the clock inside the send window. These tests are about the caps and the
    # pacing; without this they pass by day and recurse forever at night, because
    # the deferral re-enqueues and this fixture runs re-enqueues inline. Quiet
    # hours have their own suite (test_whatsapp_send_window.py).
    monkeypatch.setattr(tasks, "seconds_until_send_window", lambda *a, **kw: 0)

    sent: list[str] = []
    monkeypatch.setattr(whatsapp_service, "send_template",
                        lambda *a, **kw: sent.append(kw["to"]) or f"wamid.{len(sent)}")
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    # The chunk re-enqueue, run inline so a test sees the whole campaign. The
    # countdown is what matters in production and it is asserted separately.
    countdowns: list[int] = []

    def run_now(name, kwargs=None, countdown=None, **_):
        countdowns.append(countdown)
        return tasks.send_review_batch_task(**(kwargs or {}))
    monkeypatch.setattr(tasks.celery, "send_task", run_now)

    return org, loc, account, sent, countdowns


def _people(n, start=9000000001):
    return [{"phone": str(start + i), "name": f"C{i}"} for i in range(n)]


def test_a_batch_larger_than_one_chunk_still_sends_everyone(wired, db):
    org, loc, _, sent, countdowns = wired
    people = _people(tasks.CHUNK_SIZE * 2 + 3)

    tasks.send_review_batch_task(org.id, loc.id, people, "b1")

    assert len(sent) == len(people)
    # Paced by re-enqueue, not by sleeping: the old version held one worker
    # thread for the whole campaign, and ten of those emptied the pool.
    assert countdowns == [tasks.CHUNK_INTERVAL_SECONDS] * 2


def test_a_night_upload_waits_instead_of_sending(wired, db, monkeypatch):
    """Outside the window the campaign is DEFERRED, not dropped and not sent.

    The distinction that matters: no message goes out at 1am, and no recipient is
    written off as skipped either — the same list runs at 09:00.
    """
    org, loc, _, sent, _ = wired
    enqueued: list[dict] = []
    monkeypatch.setattr(tasks, "seconds_until_send_window", lambda *a, **kw: 4200)
    monkeypatch.setattr(tasks.celery, "send_task",
                        lambda name, kwargs=None, countdown=None, **_:
                        enqueued.append({"kwargs": kwargs, "countdown": countdown}))

    people = _people(5)
    result = tasks.send_review_batch_task(org.id, loc.id, people, "night")

    assert sent == []                                   # nobody messaged at 1am
    assert db.query(ReviewRequest).count() == 0         # and nobody burned as skipped
    assert result["stopped"] is None                    # deferred is not stopped
    assert result["deferred_seconds"] == 4200
    assert len(enqueued) == 1
    assert enqueued[0]["countdown"] == 4200
    assert enqueued[0]["kwargs"]["recipients"] == people   # the whole list, intact
    assert enqueued[0]["kwargs"]["batch_id"] == "night"


def test_one_chunk_does_not_re_enqueue(wired, db):
    org, loc, _, sent, countdowns = wired
    tasks.send_review_batch_task(org.id, loc.id, _people(3), "b1")
    assert countdowns == []
    assert len(sent) == 3


def test_the_daily_tier_cap_stops_the_campaign(wired, db):
    org, loc, account, sent, _ = wired
    account.daily_send_limit = 4
    db.commit()

    result = tasks.send_review_batch_task(org.id, loc.id, _people(12), "b1")

    assert len(sent) == 4
    assert result["stopped"] == "daily_cap_reached"


def test_the_monthly_ceiling_stops_the_campaign(wired, db, monkeypatch):
    """Meta enforces throughput, never spend. Without this, one bad upload is an
    unbounded charge on the tenant's own card."""
    org, loc, _, sent, _ = wired
    monkeypatch.setattr(tasks, "DEFAULT_MONTHLY_LIMIT", 5)

    result = tasks.send_review_batch_task(org.id, loc.id, _people(9), "b1")

    assert len(sent) == 5
    assert result["stopped"] == "monthly_cap_reached"


def test_a_per_account_limit_overrides_the_default(wired, db, monkeypatch):
    org, loc, account, sent, _ = wired
    monkeypatch.setattr(tasks, "DEFAULT_MONTHLY_LIMIT", 5)
    account.monthly_message_limit = 2
    db.commit()

    tasks.send_review_batch_task(org.id, loc.id, _people(9), "b1")
    assert len(sent) == 2


def test_numbers_we_never_reached_are_still_accounted_for(wired, db):
    """"You said 2,000 and I can see 340" has to have an answer."""
    org, loc, account, _, _ = wired
    account.daily_send_limit = 2
    db.commit()

    tasks.send_review_batch_task(org.id, loc.id, _people(9), "b1")

    rows = db.query(ReviewRequest).filter(ReviewRequest.batch_id == "b1").all()
    assert len(rows) == 9
    dropped = [r for r in rows if r.error_code == "daily_cap_reached"]
    assert len(dropped) == 7
    assert "daily send limit" in dropped[0].error_detail


def test_a_mid_batch_pause_stops_sending(wired, db):
    """A RED-quality webhook can land mid-campaign. Continuing past it is how a
    throttle becomes a ban, which neither we nor the tenant can reverse."""
    org, loc, account, sent, _ = wired
    real_send = whatsapp_service.send_template

    def pause_after_two(*args, **kwargs):
        if len(sent) == 2:
            account.status = WhatsAppAccount.STATUS_DISABLED
            db.commit()
        return real_send(*args, **kwargs)
    whatsapp_service.send_template = pause_after_two
    try:
        result = tasks.send_review_batch_task(org.id, loc.id, _people(8), "b1")
    finally:
        whatsapp_service.send_template = real_send

    assert len(sent) == 3
    assert result["stopped"].startswith("paused_mid_batch")


def test_an_account_that_cannot_send_never_starts(wired, db):
    org, loc, account, sent, _ = wired
    account.verified_send_at = None          # no live test send yet
    db.commit()

    result = tasks.send_review_batch_task(org.id, loc.id, _people(3), "b1")
    assert sent == []
    assert result["stopped"].startswith("whatsapp_not_ready")


def test_the_kill_switch_stops_everything(wired, db, monkeypatch):
    org, loc, _, sent, _ = wired
    monkeypatch.setattr(tasks.app_settings, "get_flag", lambda *a, **kw: False)

    result = tasks.send_review_batch_task(org.id, loc.id, _people(3), "b1")
    assert sent == []
    assert result["stopped"] == "feature_disabled"


def test_one_bad_number_does_not_stop_the_rest(wired, db):
    org, loc, _, sent, _ = wired
    real_send = whatsapp_service.send_template
    attempts = []

    def fail_the_second(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 2:
            raise WhatsAppError("not a whatsapp user", code=131026)
        return real_send(*args, **kwargs)
    whatsapp_service.send_template = fail_the_second
    try:
        result = tasks.send_review_batch_task(org.id, loc.id, _people(4), "b1")
    finally:
        whatsapp_service.send_template = real_send

    assert result["sent"] == 3
    assert result["failed"] == 1


# ── Message accounting ────────────────────────────────────────────────────────

def test_reminders_count_towards_the_bill(wired, db):
    """Each reminder is a separately billed marketing message. Counting rows
    alone under-reported a tenant's Meta bill by up to three times."""
    org, loc, _, _, _ = wired
    row = ReviewRequest(organization_id=org.id, location_id=loc.id, phone="919999900001",
                        token="tok-a", status=ReviewRequest.STATUS_DELIVERED,
                        reminder_count=2)
    db.add(row)
    db.commit()

    assert tasks.billable_this_month(db, org.id) == 3


def test_reminders_count_towards_the_daily_cap(wired, db):
    org, loc, _, _, _ = wired
    now = datetime.now(timezone.utc)
    row = ReviewRequest(organization_id=org.id, location_id=loc.id, phone="919999900001",
                        token="tok-b", status=ReviewRequest.STATUS_DELIVERED,
                        reminder_count=1, last_reminder_at=now)
    db.add(row)
    db.commit()
    # One first send plus one reminder: invisible to the cap before, which meant
    # a day of reminders quietly overran the tenant's Meta tier.
    assert tasks._sent_today(db, org.id) == 2


def test_skipped_rows_are_not_billable(wired, db):
    org, loc, _, _, _ = wired
    db.add(ReviewRequest(organization_id=org.id, location_id=loc.id, phone="919999900002",
                         token="tok-c", status=ReviewRequest.STATUS_SKIPPED))
    db.commit()
    assert tasks.billable_this_month(db, org.id) == 0
