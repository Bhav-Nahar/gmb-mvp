import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.location import Location
from app.models.review import Review
from app.models.reply_template import ReplyTemplate
from app.services.reply_template_service import ReplyTemplateService
from app.services.review_auto_reply_service import ReviewAutoReplyService


class _FakeProvider:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def reply_review(self, provider_review_id, reply_text):
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append((provider_review_id, reply_text))


def _seed(db: Session, enabled_at):
    org = Organization(id=1, name="Org", subscription_status="active",
                       auto_reply_enabled_at=enabled_at)
    db.add(org)
    loc = Location(
        id=1, organization_id=1, google_location_id="locations/1",
        location_name="Acme Cafe", billing_status="active", sync_status="Synced",
    )
    db.add(loc)
    db.add(ReplyTemplate(id=10, organization_id=1, star_rating=5,
                         title="t5", body="Thanks {{customer}} for visiting {{business}}!"))
    db.commit()


def _make_review(rid, rating, created_at, **kw):
    return Review(
        organization_id=1, location_id=1, provider="gbp",
        provider_review_id=f"pr_{rid}", reviewer_name="Sam", rating=rating,
        is_replied=kw.get("is_replied", False), review_created_at=created_at,
        auto_reply_attempts=kw.get("auto_reply_attempts", 0),
    )


def _run(db, provider, monkeypatch):
    monkeypatch.setattr(ReviewAutoReplyService, "_get_provider",
                        lambda self, name, org_id: provider)
    return asyncio.run(ReviewAutoReplyService(db).run(1, 1))


def test_only_eligible_reviews_are_replied(db: Session, monkeypatch):
    t0 = datetime.now(timezone.utc) - timedelta(days=1)
    _seed(db, enabled_at=t0)
    after, before = t0 + timedelta(hours=1), t0 - timedelta(hours=1)

    eligible = _make_review("ok", 5, after)
    db.add_all([
        eligible,
        _make_review("low", 3, after),                       # rating too low
        _make_review("old", 5, before),                      # before enabled_at
        _make_review("done", 5, after, is_replied=True),     # already replied
        _make_review("dead", 5, after, auto_reply_attempts=5),  # exhausted attempts
    ])
    db.commit()

    provider = _FakeProvider()
    result = _run(db, provider, monkeypatch)

    assert result["replied"] == 1
    assert [c[0] for c in provider.calls] == ["pr_ok"]
    db.refresh(eligible)
    assert eligible.is_replied is True
    assert eligible.reply_text == "Thanks Sam for visiting Acme Cafe!"  # alias resolution
    assert eligible.reply_template_id == 10
    tpl = db.query(ReplyTemplate).get(10)
    assert tpl.usage_count == 1


def test_failed_post_increments_attempts_and_leaves_unreplied(db: Session, monkeypatch):
    t0 = datetime.now(timezone.utc) - timedelta(days=1)
    _seed(db, enabled_at=t0)
    r = _make_review("ok", 5, t0 + timedelta(hours=1))
    db.add(r)
    db.commit()

    result = _run(db, _FakeProvider(fail=True), monkeypatch)

    assert result["failed"] == 1
    db.refresh(r)
    assert r.is_replied is False
    assert r.auto_reply_attempts == 1


def test_disabled_location_is_skipped(db: Session, monkeypatch):
    _seed(db, enabled_at=None)
    db.add(_make_review("ok", 5, datetime.now(timezone.utc)))
    db.commit()
    result = _run(db, _FakeProvider(), monkeypatch)
    assert result["status"] == "skipped"


def test_resolve_variables_aliases_and_rating():
    body = "{{customer}} / {{reviewer_name}} / {{business}} / {{location}} / {{rating}} stars"
    out = ReplyTemplateService.resolve_variables(body, "Sam", "Acme", rating=5)
    assert out == "Sam / Sam / Acme / Acme / 5 stars"


def test_delete_below_threshold_turns_auto_reply_off(db: Session):
    org = Organization(id=1, name="Org", subscription_status="active",
                       auto_reply_enabled_at=datetime.now(timezone.utc))
    db.add(org)
    t4 = ReplyTemplate(id=1, organization_id=1, star_rating=4, title="a", body="hi")
    t5 = ReplyTemplate(id=2, organization_id=1, star_rating=5, title="b", body="hi")
    db.add_all([t4, t5])
    db.commit()

    # Two positive templates -> deleting one drops to 1 (< MIN), so auto-reply must turn off.
    disabled = ReplyTemplateService.delete_template(db, 1, t5.id)
    assert disabled is True
    db.refresh(org)
    assert org.auto_reply_enabled_at is None


def test_delete_non_positive_template_keeps_auto_reply_on(db: Session):
    org = Organization(id=1, name="Org", subscription_status="active",
                       auto_reply_enabled_at=datetime.now(timezone.utc))
    db.add(org)
    db.add_all([
        ReplyTemplate(id=1, organization_id=1, star_rating=5, title="a", body="hi"),
        ReplyTemplate(id=2, organization_id=1, star_rating=5, title="b", body="hi"),
        ReplyTemplate(id=3, organization_id=1, star_rating=2, title="c", body="sorry"),
    ])
    db.commit()

    # Deleting a 2★ template doesn't touch 4-5★ coverage.
    disabled = ReplyTemplateService.delete_template(db, 1, 3)
    assert disabled is False
    db.refresh(org)
    assert org.auto_reply_enabled_at is not None


def test_resolve_variables_first_name_and_location_fields():
    body = "Hi {{first_name}}! Visit {{business}} in {{city}}, call {{phone}} or {{website}}."
    out = ReplyTemplateService.resolve_variables(
        body, "Sam Smith", "Acme", city="Pune", phone="123", website="acme.com"
    )
    assert out == "Hi Sam! Visit Acme in Pune, call 123 or acme.com."
    # Unsupplied fields render empty, not the literal token.
    assert ReplyTemplateService.resolve_variables("[{{city}}]", "Sam", "Acme") == "[]"
