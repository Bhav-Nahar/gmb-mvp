"""Who gets a reminder, and who must not.

Every case here is a way to annoy a customer into blocking the tenant's number,
which costs them the ability to message anyone at all.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.location import Location
from app.models.organization import Organization
from app.models.review_request import ReviewRequest
from app.models.whatsapp_account import WhatsAppAccount


@pytest.fixture
def wired(db, monkeypatch):
    """One org with a ready WhatsApp account, and a captured sender."""
    from app.core.security import encrypt_token
    from app.services import whatsapp_service
    import app.tasks_whatsapp as tasks

    org = Organization(name="Reminder Co")
    db.add(org)
    db.flush()
    loc = Location(organization_id=org.id, google_location_id="locations/x",
                   location_name="Test Store")
    db.add(loc)
    db.add(WhatsAppAccount(
        organization_id=org.id, waba_id="w", phone_number_id="p",
        access_token=encrypt_token("t"), template_name="review",
        template_status="APPROVED", status=WhatsAppAccount.STATUS_READY,
        # A fully unlocked account: Meta setup done, webhooks proven, one live
        # send already paid for. All three are required to send for real.
        app_subscribed=True, verified_send_at=datetime.now(timezone.utc)))
    db.commit()

    sent: list[str] = []
    monkeypatch.setattr(whatsapp_service, "send_template",
                        lambda *a, **kw: sent.append(kw["to"]) or "wamid.x")
    monkeypatch.setattr(tasks, "SEND_INTERVAL_SECONDS", 0)
    # Inside quiet hours, or every one of these no-ops when the suite runs at night.
    monkeypatch.setattr(tasks, "seconds_until_send_window", lambda *a, **kw: 0)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)   # the task closes its session
    return org, loc, sent


def _request(db, org, loc, **kw):
    kw.setdefault("status", ReviewRequest.STATUS_DELIVERED)
    kw.setdefault("sent_at", datetime.now(timezone.utc) - timedelta(hours=30))
    row = ReviewRequest(organization_id=org.id, location_id=loc.id, phone="919999900001",
                        token=f"tok{kw.pop('n', 1)}", **kw)
    db.add(row)
    db.commit()
    return row


def test_unclicked_request_is_reminded(wired, db):
    from app.tasks_whatsapp import send_review_reminders_task
    org, loc, sent = wired
    row = _request(db, org, loc)

    assert send_review_reminders_task()["reminded"] == 1
    assert sent == ["919999900001"]
    db.refresh(row)
    assert row.reminder_count == 1
    # The token is reused, so the link already in the customer's chat still works.
    assert row.token == "tok1"


def test_a_customer_who_clicked_is_left_alone(wired, db):
    from app.tasks_whatsapp import send_review_reminders_task
    org, loc, sent = wired
    _request(db, org, loc, clicked_at=datetime.now(timezone.utc),
             status=ReviewRequest.STATUS_CLICKED)

    assert send_review_reminders_task()["reminded"] == 0
    assert sent == []


def test_reminders_stop_at_two(wired, db):
    from app.tasks_whatsapp import send_review_reminders_task, MAX_REMINDERS
    org, loc, sent = wired
    _request(db, org, loc, reminder_count=MAX_REMINDERS)

    assert send_review_reminders_task()["reminded"] == 0
    assert sent == []


def test_a_recent_send_waits_its_turn(wired, db):
    from app.tasks_whatsapp import send_review_reminders_task
    org, loc, sent = wired
    row = _request(db, org, loc)
    row.sent_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db.commit()

    assert send_review_reminders_task()["reminded"] == 0


def test_the_gap_counts_from_the_last_reminder_not_the_first_send(wired, db):
    """Otherwise both reminders fire in the same hour, which reads as spam."""
    from app.tasks_whatsapp import send_review_reminders_task
    org, loc, sent = wired
    row = _request(db, org, loc)
    row.last_reminder_at = datetime.now(timezone.utc) - timedelta(hours=1)
    row.reminder_count = 1
    db.commit()

    assert send_review_reminders_task()["reminded"] == 0


def test_a_stale_request_is_dropped_rather_than_reminded(wired, db):
    from app.tasks_whatsapp import send_review_reminders_task
    org, loc, sent = wired
    row = _request(db, org, loc)
    row.sent_at = datetime.now(timezone.utc) - timedelta(days=20)
    db.commit()

    assert send_review_reminders_task()["reminded"] == 0


def test_unsendable_rows_do_not_block_the_ones_behind_them(wired, db, monkeypatch):
    """The chunk is capped at REMINDER_CHUNK rows ordered by id. Without a cursor
    a row this run cannot send is left untouched and picked first again next run,
    so a handful of dead rows starve every reminder behind them for a week."""
    import app.tasks_whatsapp as tasks
    org, loc, sent = wired
    monkeypatch.setattr(tasks, "REMINDER_CHUNK", 2)

    # Two rows whose location is gone — skipped, and never mutated.
    dead = _request(db, org, loc, n=1), _request(db, org, loc, n=2)
    for row in dead:
        row.location_id = 999999
    live = _request(db, org, loc, n=3)
    db.commit()

    enqueued: list[dict] = []
    monkeypatch.setattr(tasks.celery, "send_task",
                        lambda name, **kw: enqueued.append(kw))

    # First chunk sends nothing but must still hand the cursor forward.
    first = tasks.send_review_reminders_task()
    assert first["reminded"] == 0
    assert enqueued and enqueued[0]["kwargs"]["after_id"] == dead[1].id

    # The chunk it enqueued reaches the row the dead ones were sitting in front of.
    assert tasks.send_review_reminders_task(after_id=dead[1].id)["reminded"] == 1
    assert sent == ["919999900001"]
    db.refresh(live)
    assert live.reminder_count == 1
