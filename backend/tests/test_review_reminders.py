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
        template_status="APPROVED", status=WhatsAppAccount.STATUS_READY))
    db.commit()

    sent: list[str] = []
    monkeypatch.setattr(whatsapp_service, "send_template",
                        lambda *a, **kw: sent.append(kw["to"]) or "wamid.x")
    monkeypatch.setattr(tasks, "SEND_INTERVAL_SECONDS", 0)
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
