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


def _run(db, provider, monkeypatch, backlog=False):
    monkeypatch.setattr(ReviewAutoReplyService, "_get_provider",
                        lambda self, name, org_id: provider)
    return asyncio.run(ReviewAutoReplyService(db).run(1, 1, backlog=backlog))


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


def test_location_opt_out_is_skipped_and_a_run_is_logged(db: Session, monkeypatch):
    from app.models.activity_log import ActivityLog

    t0 = datetime.now(timezone.utc) - timedelta(days=1)
    _seed(db, enabled_at=t0)
    db.add(_make_review("ok", 5, t0 + timedelta(hours=1)))
    loc = db.query(Location).get(1)
    loc.auto_reply_enabled = False
    db.commit()

    provider = _FakeProvider()
    assert _run(db, provider, monkeypatch)["reason"] == "auto-reply off for this location"
    assert provider.calls == []

    loc.auto_reply_enabled = True
    db.commit()
    assert _run(db, provider, monkeypatch)["replied"] == 1
    run_logs = db.query(ActivityLog).filter(ActivityLog.action == "review_auto_reply_run").all()
    assert len(run_logs) == 1 and run_logs[0].payload["replied"] == 1


def test_waiting_count_matches_what_template_mode_would_actually_reply_to(db: Session,
                                                                         fake_admin_user):
    """The 'waiting' column exists to tell a stalled automation from an idle one, so it
    must count the same rows _find_targets does. Template mode ignores anything created
    before auto-reply was switched on; counting those made the number never drain."""
    from app.api.reply_templates import list_auto_reply_locations

    t0 = datetime.now(timezone.utc) - timedelta(days=1)
    _seed(db, enabled_at=t0)
    db.add_all([
        _make_review("after", 5, t0 + timedelta(hours=1)),   # eligible
        _make_review("before", 5, t0 - timedelta(days=30)),  # predates enablement
    ])
    db.commit()

    rows = list_auto_reply_locations(db=db, current_user=fake_admin_user)
    assert [r["waiting"] for r in rows] == [1]


def test_review_id_filter_is_scoped_to_the_callers_org(db: Session, fake_admin_user):
    """The activity log links to /reviews?review=<id>. The id is a raw DB id straight off
    an ActivityLog row, so the filter must never widen the org boundary."""
    from app.api.reviews import get_reviews

    _seed(db, enabled_at=None)
    db.add(Organization(id=2, name="Other", subscription_status="active"))
    db.add(Location(id=2, organization_id=2, google_location_id="locations/2",
                    location_name="Rival", billing_status="active"))
    db.commit()
    mine = _make_review("mine", 5, datetime.now(timezone.utc))
    theirs = _make_review("theirs", 5, datetime.now(timezone.utc))
    theirs.organization_id, theirs.location_id = 2, 2
    db.add_all([mine, theirs])
    db.commit()

    assert get_reviews(review_id=mine.id, db=db, current_user=fake_admin_user).total == 1
    # Another tenant's id resolves to nothing, not to their review.
    assert get_reviews(review_id=theirs.id, db=db, current_user=fake_admin_user).total == 0


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


# ── AI mode ───────────────────────────────────────────────────────────────────

def _ai_seed(db: Session, credits=50, mode="ai"):
    org = Organization(id=1, name="Org", subscription_status="active",
                       auto_reply_enabled_at=datetime.now(timezone.utc) - timedelta(days=30),
                       auto_reply_mode=mode, monthly_ai_credits_balance=credits,
                       topup_ai_credits_balance=0)
    db.add(org)
    db.add(Location(id=1, organization_id=1, google_location_id="locations/1",
                    location_name="Acme Cafe", primary_category="Cafe",
                    billing_status="active", sync_status="Synced"))
    db.commit()


def _ai_review(rid, rating, created_at, **kw):
    """Like _make_review but with review text, so AI mode takes the LLM path rather
    than the no-comment canned reply."""
    r = _make_review(rid, rating, created_at, **kw)
    r.comment = "Lovely coffee and the staff were friendly, the seating is comfortable too."
    return r


def _stub_ai(monkeypatch, text="Thank you so much for the kind words about our cafe, we are "
                              "really glad the coffee and the seating worked out well for you "
                              "and we hope to see you here again soon."):
    import app.services.ai_reply_service as ai

    async def fake(review, location, db=None):
        return {"generated_reply": text, "variants": {"recommended": text, "short": text,
                                                      "warm_or_professional": text},
                "topics": [], "tone": "grateful", "sensitive": False}
    monkeypatch.setattr(ai, "generate_reply", fake)


def test_ai_mode_replies_to_backlog_without_templates(db: Session, monkeypatch):
    """The whole point of AI mode: old reviews get answered, and no template is needed."""
    _ai_seed(db)
    _stub_ai(monkeypatch)
    old = datetime.now(timezone.utc) - timedelta(days=200)
    db.add_all([_ai_review(f"b{i}", 5, old) for i in range(30)])
    db.commit()

    provider = _FakeProvider()
    monkeypatch.setattr(ReviewAutoReplyService, "_backlog_room", lambda self, loc: 12)
    result = _run(db, provider, monkeypatch, backlog=True)

    assert result["replied"] == 12, result          # this slice of the drip, not all 30
    assert len(provider.calls) == 12
    replied = db.query(Review).filter(Review.is_replied == True).all()  # noqa: E712
    assert all(r.reply_template_id is None for r in replied)
    org = db.query(Organization).filter(Organization.id == 1).first()
    assert org.monthly_ai_credits_balance == 50 - 12  # one credit per generated reply


def test_ai_mode_prioritises_new_reviews_over_backlog(db: Session, monkeypatch):
    _ai_seed(db)
    _stub_ai(monkeypatch)
    fresh = _ai_review("fresh", 5, datetime.now(timezone.utc) - timedelta(hours=2))
    db.add(fresh)
    db.add_all([_ai_review(f"b{i}", 5, datetime.now(timezone.utc) - timedelta(days=100))
                for i in range(5)])
    db.commit()

    provider = _FakeProvider()
    result = _run(db, provider, monkeypatch)   # the sync-triggered run

    assert result["replied"] == 1               # only the fresh one; backlog waits for the drip
    db.refresh(fresh)
    assert fresh.is_replied is True


def test_ai_mode_never_posts_a_reply_that_needs_a_human(db: Session, monkeypatch):
    _ai_seed(db)
    _stub_ai(monkeypatch, text="We are the best cafe in town and you deserve nothing less "
                               "than perfection from us every single time you drop by here.")
    db.add(_ai_review("x", 5, datetime.now(timezone.utc) - timedelta(hours=1)))
    db.commit()

    provider = _FakeProvider()
    result = _run(db, provider, monkeypatch)

    assert result["replied"] == 0 and result["needs_human"] == 1, result
    assert provider.calls == []  # banned superlative never reached Google


def test_ai_mode_stops_the_run_when_credits_run_out(db: Session, monkeypatch):
    _ai_seed(db, credits=3)
    _stub_ai(monkeypatch)
    db.add_all([_ai_review(f"b{i}", 5, datetime.now(timezone.utc) - timedelta(days=50))
                for i in range(10)])
    db.commit()

    monkeypatch.setattr(ReviewAutoReplyService, "_backlog_room", lambda self, loc: 10)
    provider = _FakeProvider()
    result = _run(db, provider, monkeypatch, backlog=True)

    assert result["replied"] == 3, result  # stopped at the balance, no 402 storm
    assert len(provider.calls) == 3


def test_daily_quota_is_stable_within_a_day_and_in_range(db: Session):
    svc = ReviewAutoReplyService(db)
    q = svc._daily_quota(7)
    assert 10 <= q <= 20
    assert svc._daily_quota(7) == q          # same day, same number across runs


def test_backlog_drip_is_paced_across_business_hours(db: Session):
    """Nothing due before 9am IST, whole quota due by 9pm IST, monotonic in between."""
    due = ReviewAutoReplyService._due_by_now
    utc = lambda h, m=0: datetime(2026, 7, 26, h, m, tzinfo=timezone.utc)
    assert due(20, utc(0)) == 0          # 05:30 IST — before the window
    assert due(20, utc(3, 29)) == 0      # 08:59 IST
    assert due(20, utc(9, 30)) == 10     # 15:00 IST — halfway through 9am-9pm
    assert due(20, utc(15, 30)) == 20    # 21:00 IST — window closed, all due
    assert due(10, utc(9, 30)) == 5
    window = [due(15, utc(h)) for h in range(4, 16)]   # 09:30-20:30 IST
    assert window == sorted(window) and max(window) <= 15
    assert due(20, utc(19)) == 0         # 00:30 IST — never drips overnight


def test_backlog_run_is_ai_mode_only(db: Session, monkeypatch):
    """A template-mode org must never have its backlog machine-gunned by the drip."""
    _ai_seed(db, mode="template")
    db.add_all([_ai_review(f"b{i}", 5, datetime.now(timezone.utc) - timedelta(days=90))
                for i in range(5)])
    db.commit()

    provider = _FakeProvider()
    result = _run(db, provider, monkeypatch, backlog=True)

    assert result["status"] == "skipped", result
    assert provider.calls == []


def test_ai_mode_skips_entirely_when_the_org_has_no_credits(db: Session, monkeypatch):
    """No balance = no LLM call at all, not one 402 per review."""
    _ai_seed(db, credits=0)
    calls = []

    import app.services.ai_reply_service as ai
    async def boom(review, location, db=None):
        calls.append(review.id)
        raise AssertionError("must not reach the LLM with no credits")
    monkeypatch.setattr(ai, "generate_reply", boom)

    db.add_all([_ai_review(f"b{i}", 5, datetime.now(timezone.utc) - timedelta(hours=1))
                for i in range(4)])
    db.commit()

    provider = _FakeProvider()
    result = _run(db, provider, monkeypatch)

    assert result == {"status": "skipped", "reason": "no AI credits"}, result
    assert calls == [] and provider.calls == []


def test_ai_mode_answers_3_star_but_never_1_or_2(db: Session, monkeypatch):
    _ai_seed(db)
    _stub_ai(monkeypatch)
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    three, two, one = (_ai_review("t3", 3, recent), _ai_review("t2", 2, recent),
                       _ai_review("t1", 1, recent))
    db.add_all([three, two, one])
    db.commit()

    provider = _FakeProvider()
    result = _run(db, provider, monkeypatch)

    assert result["replied"] == 1, result
    for r, expected in ((three, True), (two, False), (one, False)):
        db.refresh(r)
        assert r.is_replied is expected, (r.rating, r.is_replied)


def test_template_mode_still_stops_at_4_star(db: Session, monkeypatch):
    """Lowering the AI floor must not change the template automation."""
    t0 = datetime.now(timezone.utc) - timedelta(days=1)
    _seed(db, enabled_at=t0)
    db.add(_make_review("t3", 3, t0 + timedelta(hours=1)))
    db.commit()

    provider = _FakeProvider()
    result = _run(db, provider, monkeypatch)

    assert result["status"] == "skipped", result
    assert provider.calls == []


def test_rating_only_low_star_does_not_thank_them_for_the_stars(db: Session):
    from app.services.ai_reply_service import empty_review_reply
    for _ in range(20):
        low = empty_review_reply(3)
        assert 'stars' not in low.lower() and 'support' not in low.lower(), low
        assert empty_review_reply(5)  # positive pool still works


def test_ai_mode_skipped_for_onboarding_org(db: Session, monkeypatch):
    """Pre-payment org (trial with no clock started) must not spend credits."""
    _ai_seed(db)
    org = db.query(Organization).filter(Organization.id == 1).first()
    org.subscription_status, org.trial_ends_at = "trial", None   # onboarding state
    db.commit()
    db.add(_ai_review("x", 5, datetime.now(timezone.utc) - timedelta(hours=1)))
    db.commit()

    provider = _FakeProvider()
    result = _run(db, provider, monkeypatch)

    assert result == {"status": "skipped", "reason": "AI features locked for this org"}, result
    assert provider.calls == []


def test_fresh_burst_is_capped(db: Session, monkeypatch):
    """First sync after enabling must not turn a day of reviews into a 100-credit burst."""
    from app.services.review_auto_reply_service import AI_DAILY_MAX
    _ai_seed(db, credits=500)
    _stub_ai(monkeypatch)
    db.add_all([_ai_review(f"f{i}", 5, datetime.now(timezone.utc) - timedelta(hours=3))
                for i in range(40)])
    db.commit()

    provider = _FakeProvider()
    result = _run(db, provider, monkeypatch)

    assert result["replied"] == AI_DAILY_MAX, result


def test_has_backlog_is_false_once_the_old_reviews_are_answered(db: Session, monkeypatch):
    """The hourly beat job uses this to avoid enqueueing a task per location per hour
    when there is nothing left to drip."""
    _ai_seed(db)
    _stub_ai(monkeypatch)
    loc = db.query(Location).filter(Location.id == 1).first()
    svc = ReviewAutoReplyService(db)
    assert svc.has_backlog(loc) is False              # nothing seeded yet

    db.add(_ai_review("old", 5, datetime.now(timezone.utc) - timedelta(days=60)))
    db.add(_ai_review("fresh", 5, datetime.now(timezone.utc) - timedelta(hours=2)))
    db.commit()
    assert svc.has_backlog(loc) is True               # the old one counts
    assert ReviewAutoReplyService(db)._find_backlog_targets(loc)

    provider = _FakeProvider()
    monkeypatch.setattr(ReviewAutoReplyService, "_backlog_room", lambda self, l: 5)
    _run(db, provider, monkeypatch, backlog=True)
    assert ReviewAutoReplyService(db).has_backlog(loc) is False  # drained, stop polling


def test_a_failed_post_is_not_paid_for_twice(db: Session, monkeypatch):
    """The generation costs a credit before the Google call. If that call fails, the
    retry must reuse the banked text instead of buying a second generation."""
    _ai_seed(db, credits=10)
    calls = []
    text = ("Thank you so much for the kind words about our cafe, we are really glad the "
            "coffee and the seating worked out well for you and we hope to see you again.")

    import app.services.ai_reply_service as ai
    async def counting(review, location, db=None):
        calls.append(review.id)
        return {"generated_reply": text, "variants": {"recommended": text, "short": text,
                                                     "warm_or_professional": text},
                "topics": [], "tone": "grateful", "sensitive": False}
    monkeypatch.setattr(ai, "generate_reply", counting)

    r = _ai_review("x", 5, datetime.now(timezone.utc) - timedelta(hours=1))
    db.add(r)
    db.commit()

    # 1st run: Google is down.
    failing = _FakeProvider(fail=True)
    assert _run(db, failing, monkeypatch)["failed"] == 1
    db.refresh(r)
    org = db.query(Organization).filter(Organization.id == 1).first()
    assert len(calls) == 1
    assert org.monthly_ai_credits_balance == 9          # charged once
    assert r.ai_reply_draft == text                     # and banked
    assert r.reply_text is None and r.is_replied is False  # nothing shown to customers
    assert r.auto_reply_attempts == 1

    # 2nd run: Google is back.
    ok = _FakeProvider()
    assert _run(db, ok, monkeypatch)["replied"] == 1
    db.refresh(r)
    org = db.query(Organization).filter(Organization.id == 1).first()
    assert len(calls) == 1, "regenerated a reply that was already paid for"
    assert org.monthly_ai_credits_balance == 9          # still one charge total
    assert ok.calls == [("pr_x", text)]                 # the banked text went live
    assert r.is_replied is True and r.reply_text == text
    assert r.ai_reply_draft is None                     # draft released


def test_backlog_targets_are_a_random_slice_not_the_same_rows_every_tick(db: Session, monkeypatch):
    """No ORDER BY random(), but the drip must still not answer the same reviews
    (or the oldest N) every single tick."""
    _ai_seed(db)
    old = datetime.now(timezone.utc) - timedelta(days=90)
    db.add_all([_ai_review(f"b{i}", 5, old + timedelta(minutes=i)) for i in range(60)])
    db.commit()

    loc = db.query(Location).filter(Location.id == 1).first()
    monkeypatch.setattr(ReviewAutoReplyService, "_backlog_room", lambda self, l: 5)
    svc = ReviewAutoReplyService(db)
    picks = [tuple(sorted(r.id for r in svc._find_backlog_targets(loc))) for _ in range(25)]

    assert all(len(p) == 5 for p in picks)          # always exactly the room
    assert len(set(picks)) > 1                      # not the same slice every time
    # and the ordering inside a batch is shuffled, not ascending by id
    assert any([r.id for r in svc._find_backlog_targets(loc)] !=
               sorted(r.id for r in svc._find_backlog_targets(loc)) for _ in range(5))


def test_backlog_returns_everything_when_it_fits_in_the_room(db: Session, monkeypatch):
    _ai_seed(db)
    old = datetime.now(timezone.utc) - timedelta(days=90)
    db.add_all([_ai_review(f"b{i}", 5, old) for i in range(3)])
    db.commit()
    loc = db.query(Location).filter(Location.id == 1).first()
    monkeypatch.setattr(ReviewAutoReplyService, "_backlog_room", lambda self, l: 10)
    assert len(ReviewAutoReplyService(db)._find_backlog_targets(loc)) == 3
