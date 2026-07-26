"""Drip-feed indexing: the schedule maths and the hourly release sweep.

The failure this guards against is a whole corpus going indexable at once, so the
assertions are mostly about spread and about which pages are eligible at all.
"""
from datetime import datetime, time, timedelta, timezone

from app.models.lpseo_page import LpseoPage, LpseoPageStatus
from app.services import lpseo_drip

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)

# SQLite drops tzinfo on read where Postgres keeps it, so normalise before comparing
# a stored value against an aware datetime.
def utc(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


_seq = [0]


def _pages(db, n, *, status=LpseoPageStatus.PUBLISHED.value, index_status="noindex", score=90):
    """Slugs are globally unique, so each call gets its own block of city numbers."""
    made = []
    for _ in range(n):
        _seq[0] += 1
        i = _seq[0]
        p = LpseoPage(
            slug=f"dentists-in-city{i}", country="in", industry_label="Dentists",
            industry_slug="dentists", city_label=f"City{i}", city_slug=f"city{i}",
            meta_title="t", meta_description="d", h1="h",
            status=status, index_status=index_status, quality_score=score,
        )
        db.add(p)
        made.append(p)
    db.commit()
    return made


def test_arm_spreads_pages_over_days_within_the_window(db):
    _pages(db, 100)
    res = lpseo_drip.arm(db, min_per_day=20, max_per_day=30, start=NOW, seed=1)

    assert res["scheduled"] == 100
    assert 4 <= res["days"] <= 5  # 100 pages at 20-30/day
    rows = db.query(LpseoPage).all()
    assert all(p.index_at is not None for p in rows)

    # A full day's notice before anything goes live, so a mistaken arm is always
    # cancellable. Calendar-day-only would give ~7h when armed late evening IST.
    assert min(utc(p.index_at) for p in rows) >= NOW + lpseo_drip.MIN_LEAD

    lo, hi = lpseo_drip.DEFAULT_WINDOW
    for p in rows:
        assert lo <= p.index_at.timetz().replace(tzinfo=None) <= hi, p.index_at

    # No day may exceed the cap, which is the whole point of the feature.
    per_day = {}
    for p in rows:
        per_day[p.index_at.date()] = per_day.get(p.index_at.date(), 0) + 1
    assert all(20 <= n <= 30 or n == min(per_day.values()) for n in per_day.values())
    assert max(per_day.values()) <= 30


def test_arm_times_are_irregular_not_evenly_spaced(db):
    _pages(db, 60)
    lpseo_drip.arm(db, start=NOW, seed=7)
    day = sorted(p.index_at for p in db.query(LpseoPage).all())[:20]
    gaps = {int((b - a).total_seconds()) for a, b in zip(day, day[1:])}
    assert len(gaps) > 5  # evenly spaced would collapse to one or two distinct gaps


def test_arm_skips_ineligible_pages(db):
    _pages(db, 3)                                                    # eligible
    _pages(db, 2, status=LpseoPageStatus.DRAFT.value)                # not published
    _pages(db, 2, index_status="index")                              # already live
    _pages(db, 2, score=50)                                          # under the QA gate
    res = lpseo_drip.arm(db, start=NOW, seed=1)
    assert res["scheduled"] == 3
    assert db.query(LpseoPage).filter(LpseoPage.index_at.isnot(None)).count() == 3


def test_arm_again_appends_after_the_existing_plan(db):
    first = _pages(db, 25)
    lpseo_drip.arm(db, start=NOW, seed=1)
    last_of_first = max(p.index_at for p in first)

    _pages(db, 25)  # a second import lands later
    lpseo_drip.arm(db, start=NOW, seed=2)

    # The original 25 keep their slots, and the new batch queues after them.
    assert all(p.index_at is not None for p in db.query(LpseoPage).all())
    added = [p for p in db.query(LpseoPage).all() if p.index_at > last_of_first]
    assert len(added) == 25


def test_release_due_flips_only_what_has_matured(db):
    _pages(db, 40)
    lpseo_drip.arm(db, min_per_day=20, max_per_day=20, start=NOW, seed=3)
    rows = sorted(db.query(LpseoPage).all(), key=lambda p: p.index_at)

    # Halfway through day one.
    cutoff = rows[9].index_at
    released = lpseo_drip.release_due(db, now=cutoff)
    assert len(released) == 10
    assert {r["slug"] for r in released} == {p.slug for p in rows[:10]}

    live = db.query(LpseoPage).filter(LpseoPage.index_status == "index").all()
    assert len(live) == 10
    assert all(p.index_at is None for p in live)  # schedule consumed
    assert db.query(LpseoPage).filter(LpseoPage.index_status == "noindex").count() == 30


def test_release_is_idempotent(db):
    _pages(db, 20)
    lpseo_drip.arm(db, start=NOW, seed=4)
    later = NOW + timedelta(days=30)
    assert len(lpseo_drip.release_due(db, now=later)) == 20
    assert lpseo_drip.release_due(db, now=later) == []  # nothing left to do


def test_release_unschedules_a_page_that_fell_below_the_gate(db):
    pages = _pages(db, 2)
    lpseo_drip.arm(db, start=NOW, seed=5)
    pages[0].quality_score = 40  # re-scored after being scheduled
    db.commit()

    released = lpseo_drip.release_due(db, now=NOW + timedelta(days=30))
    assert [r["slug"] for r in released] == [pages[1].slug]
    db.refresh(pages[0])
    # Not published, and not left dangling to retry on every future tick.
    assert pages[0].index_status == "noindex" and pages[0].index_at is None


def test_release_caps_blast_radius(db):
    _pages(db, 300)
    lpseo_drip.arm(db, min_per_day=500, max_per_day=500, start=NOW, seed=6)
    released = lpseo_drip.release_due(db, now=NOW + timedelta(days=30), limit=200)
    assert len(released) == 200  # the rest bleed out on later ticks


def test_cancel_clears_pending_but_leaves_live_pages(db):
    _pages(db, 30)
    lpseo_drip.arm(db, min_per_day=10, max_per_day=10, start=NOW, seed=8)
    # End of whichever day the plan actually starts: past its window close, before
    # the next day opens. Derived from the plan so the notice period can change.
    day_one = min(utc(p.index_at) for p in db.query(LpseoPage).all()).date()
    lpseo_drip.release_due(db, now=datetime.combine(day_one, time(20, 0), tzinfo=timezone.utc))

    live_before = db.query(LpseoPage).filter(LpseoPage.index_status == "index").count()
    assert live_before == 10
    assert lpseo_drip.cancel(db)["cancelled"] == 20
    assert db.query(LpseoPage).filter(LpseoPage.index_at.isnot(None)).count() == 0
    assert db.query(LpseoPage).filter(LpseoPage.index_status == "index").count() == live_before


def test_status_reports_the_plan(db):
    _pages(db, 50)
    _pages(db, 5, index_status="index")
    lpseo_drip.arm(db, min_per_day=25, max_per_day=25, start=NOW, seed=9)
    s = lpseo_drip.status(db)
    assert s["scheduled"] == 50 and s["live"] == 5 and s["eligible_unscheduled"] == 0
    assert s["next_at"] < s["last_at"]


def test_drip_never_schedules_or_releases_a_pillar(db):
    """Pillars share lpseo_pages with the leaves but must go live on their own
    index toggle, not in the 20-30/day trickle meant for generated pages."""
    leaves = _pages(db, 5)
    pillar = _pages(db, 1)[0]
    pillar.page_type = "industry_pillar"
    pillar.index_at = None
    db.commit()

    res = lpseo_drip.arm(db, start=NOW, seed=11)
    assert res["scheduled"] == len(leaves)          # the pillar is not counted
    db.refresh(pillar)
    assert pillar.index_at is None                  # and never gets a slot

    # Even a schedule set by hand (or by a pre-filter build) must not be swept.
    pillar.index_at = NOW - timedelta(days=1)
    db.commit()
    released = lpseo_drip.release_due(db, now=NOW + timedelta(days=60))
    assert pillar.slug not in {r["slug"] for r in released}
    db.refresh(pillar)
    assert pillar.index_status == "noindex"

    assert lpseo_drip.status(db)["eligible_unscheduled"] == 0  # pillar not "awaiting"


def test_release_purges_the_backend_cache(db, monkeypatch):
    """A released page must stop being served as noindex immediately.

    The public endpoint caches its payload for an hour. If the release only pinged
    the frontend to revalidate, the frontend would refetch, receive the STALE
    noindex payload, cache that for its own full TTL, and the drip would have
    already spent its single revalidation. The page would stay noindex on the live
    site indefinitely, silently defeating the whole feature.
    """
    from app import tasks
    purged, revalidated = [], []

    class _FakeRedis:
        def delete(self, *keys): purged.extend(keys)

    monkeypatch.setattr("app.core.redis_client.get_redis", lambda: _FakeRedis())
    monkeypatch.setattr("app.services.revalidation_service.trigger_bulk_lpseo_revalidation",
                        lambda entries: revalidated.extend(e["slug"] for e in entries))
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    pages = _pages(db, 3)
    lpseo_drip.arm(db, start=NOW, seed=2)
    # The task reads the real clock, so the due time must be genuinely in the past.
    for p in pages:
        p.index_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    result = tasks.release_lpseo_index_batch_task()

    assert result["released"] == 3
    # Cache purge and revalidation must cover exactly the released slugs...
    assert sorted(purged) == sorted(f"public_lpseo:{p.slug}" for p in pages)
    assert sorted(revalidated) == sorted(p.slug for p in pages)
