"""Guards added by the LLM cost audit: atomic credit consume + sentiment attempts cap."""
import pytest

from app.models.organization import Organization
from app.models.location import Location
from app.models.review import Review
from app.services.billing.credit_service import CreditService
from app.services.sentiment_service import MAX_SENTIMENT_ATTEMPTS, _bump_attempts


def _org(db, credits=3):
    org = Organization(name="CostGuard Org", subscription_status="active",
                       monthly_ai_credits_balance=credits, topup_ai_credits_balance=0)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def test_consume_ai_credit_debits_before_work_and_keeps_charge_on_success(db):
    org = _org(db, credits=3)
    with CreditService.consume_ai_credit(db, org.id, "generate_review_reply", 1):
        db.refresh(org)
        assert org.monthly_ai_credits_balance == 2  # debited BEFORE the work, not after
    db.refresh(org)
    assert org.monthly_ai_credits_balance == 2


def test_consume_ai_credit_refunds_when_work_fails(db):
    org = _org(db, credits=3)
    with pytest.raises(RuntimeError):
        with CreditService.consume_ai_credit(db, org.id, "generate_review_reply", 1):
            raise RuntimeError("provider blew up")
    db.refresh(org)
    assert org.monthly_ai_credits_balance == 3  # failed work is never charged


def test_platform_actions_bypass_credits(db):
    org = _org(db, credits=1)
    with CreditService.consume_ai_credit(db, org.id, "sentiment_tagging", 1):
        pass
    db.refresh(org)
    assert org.monthly_ai_credits_balance == 1


def test_bump_attempts_reaches_terminal_state(db):
    org = _org(db)
    loc = Location(organization_id=org.id, google_location_id="loc-1", location_name="L1")
    db.add(loc)
    db.commit()
    r = Review(organization_id=org.id, location_id=loc.id, provider="google",
               provider_review_id="r1", reviewer_name="A", rating=5,
               review_created_at=__import__("datetime").datetime(2026, 1, 1))
    db.add(r)
    db.commit()

    for _ in range(MAX_SENTIMENT_ATTEMPTS):
        _bump_attempts(db, [r])
    db.refresh(r)
    assert r.sentiment_attempts == MAX_SENTIMENT_ATTEMPTS
    # the beat/entry filters exclude reviews at the cap
    assert not (r.sentiment_tagged_at is None and r.sentiment_attempts < MAX_SENTIMENT_ATTEMPTS)
