"""The guards that decide whether a customer gets messaged at all.

Every one of these is a compliance rule, not an optimisation: suppression is a
withdrawn consent, the frequency cap is what stops a second ask turning into a
block, and a block is what destroys the tenant's ability to message anyone.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.organization import Organization
from app.models.location import Location
from app.models.review_request import ReviewRequest
from app.models.review_suppression import ReviewSuppression
from app.services import review_request_service as svc
from app.services.whatsapp_errors import explain, is_permanent
from app.tasks_whatsapp import _tier_to_cap


@pytest.fixture
def org_and_location(db):
    org = Organization(name="Test Org")
    db.add(org)
    db.flush()
    location = Location(
        organization_id=org.id,
        google_location_id="locations/123",
        location_name="Lucira Jewellery",
    )
    db.add(location)
    db.commit()
    return org, location


def _sent_request(db, org_id, location_id, phone, created_at=None):
    row = ReviewRequest(
        organization_id=org_id, location_id=location_id, phone=phone,
        token=svc.new_token(), status=ReviewRequest.STATUS_SENT,
    )
    db.add(row)
    db.commit()
    if created_at:                       # override the server default for cap tests
        row.created_at = created_at
        db.commit()
    return row


def test_suppressed_number_is_never_sent_to(db, org_and_location):
    org, location = org_and_location
    svc.suppress(db, org.id, "919876543210", ReviewSuppression.REASON_OPT_OUT)

    row = svc.send_review_request(
        db, organization_id=org.id, location_id=location.id, phone_raw="9876543210",
    )

    assert row.status == ReviewRequest.STATUS_SKIPPED
    assert row.error_code == "suppressed"


def test_suppress_is_idempotent(db, org_and_location):
    org, _ = org_and_location
    svc.suppress(db, org.id, "919876543210", ReviewSuppression.REASON_OPT_OUT)
    svc.suppress(db, org.id, "919876543210", ReviewSuppression.REASON_MANUAL)

    assert db.query(ReviewSuppression).count() == 1


def test_suppression_is_per_organization(db, org_and_location):
    """One tenant's opt-out says nothing about another tenant's relationship
    with the same person — treating it globally would silently censor a
    customer who never opted out of anything."""
    org, _ = org_and_location
    other = Organization(name="Other Org")
    db.add(other)
    db.commit()

    svc.suppress(db, org.id, "919876543210", ReviewSuppression.REASON_OPT_OUT)

    assert svc.is_suppressed(db, org.id, "919876543210") is True
    assert svc.is_suppressed(db, other.id, "919876543210") is False


def test_recent_send_blocks_a_second_ask(db, org_and_location):
    org, location = org_and_location
    _sent_request(db, org.id, location.id, "919876543210")

    row = svc.send_review_request(
        db, organization_id=org.id, location_id=location.id, phone_raw="919876543210",
    )

    assert row.status == ReviewRequest.STATUS_SKIPPED
    assert row.error_code == "frequency_cap"


def test_cap_expires_after_the_window(db, org_and_location):
    org, location = org_and_location
    old = datetime.now(timezone.utc) - timedelta(hours=svc.cooldown_hours() + 1)
    _sent_request(db, org.id, location.id, "919876543210", created_at=old)

    # No WhatsApp account is connected, so this must get PAST the cap and fail
    # on readiness instead — which is what proves the cap released.
    with pytest.raises(ValueError, match="WhatsApp is not ready"):
        svc.send_review_request(
            db, organization_id=org.id, location_id=location.id, phone_raw="919876543210",
        )


def test_skipped_rows_do_not_consume_the_cap(db, org_and_location):
    """A skip is not a message anyone received. If it counted, one suppressed
    attempt would silently block that number for 90 days."""
    org, location = org_and_location
    db.add(ReviewRequest(
        organization_id=org.id, location_id=location.id, phone="919876543210",
        token=svc.new_token(), status=ReviewRequest.STATUS_SKIPPED,
    ))
    db.commit()

    assert svc.recently_messaged(db, org.id, "919876543210") is False


def test_cooldown_of_zero_disables_the_cap(db, org_and_location, monkeypatch):
    """0 is the escape hatch for testing. It must genuinely disable the check,
    not fall through to a default."""
    org, location = org_and_location
    _sent_request(db, org.id, location.id, "919876543210")
    monkeypatch.setattr(svc, "cooldown_hours", lambda: 0)

    assert svc.recently_messaged(db, org.id, "919876543210") is False


def test_cooldown_message_reads_in_human_units(monkeypatch):
    monkeypatch.setattr(svc, "cooldown_hours", lambda: 24)
    assert svc._cooldown_message() == "Already asked within the last 1 day"
    monkeypatch.setattr(svc, "cooldown_hours", lambda: 2160)
    assert svc._cooldown_message() == "Already asked within the last 90 days"
    monkeypatch.setattr(svc, "cooldown_hours", lambda: 6)
    assert svc._cooldown_message() == "Already asked within the last 6 hours"


def test_unusable_phone_is_recorded_not_dropped(db, org_and_location):
    """The upload said something; the campaign view has to be able to explain
    what happened to it."""
    org, location = org_and_location

    row = svc.send_review_request(
        db, organization_id=org.id, location_id=location.id, phone_raw="not-a-number",
    )

    assert row.status == ReviewRequest.STATUS_SKIPPED
    assert row.error_code == "invalid_phone"


def test_location_from_another_org_is_refused(db, org_and_location):
    """Tenant scoping. A location id is a plain integer from a request body."""
    org, location = org_and_location
    other = Organization(name="Other Org")
    db.add(other)
    db.commit()

    with pytest.raises(ValueError, match="not found"):
        svc.send_review_request(
            db, organization_id=other.id, location_id=location.id, phone_raw="919876543210",
        )


def test_tokens_are_unique_per_request(db, org_and_location):
    assert len({svc.new_token() for _ in range(200)}) == 200


@pytest.mark.parametrize("code,permanent", [
    (131026, True),    # not on WhatsApp — retrying can never work
    (131047, True),    # needs a template; free-form will keep failing
    (131049, False),   # Meta pacing — worth retrying later
    (132001, False),   # template missing — fix the template, not the number
    (None, False),
    ("garbage", False),
])
def test_permanent_failures_are_the_ones_worth_suppressing(code, permanent):
    assert is_permanent(code) is permanent
    assert explain(code).message          # every code yields something readable


@pytest.mark.parametrize("tier,cap", [
    ("TIER_250", 250), ("TIER_1K", 1_000), ("tier_10k", 10_000), (None, None), ("TIER_WAT", None),
])
def test_unknown_tier_returns_none_rather_than_guessing(tier, cap):
    # The caller falls back to the entry cap, erring towards sending too few.
    assert _tier_to_cap(tier) == cap
