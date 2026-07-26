"""Drip-feed indexing for the local-SEO corpus.

Importing 4,000 pages is cheap; making 4,000 pages indexable on the same afternoon
is the part that looks machine-generated. This releases them a few dozen a day, at
irregular times, so the corpus grows the way a site that publishes actually grows.

Two moving parts:

- `arm()` assigns every eligible page an `index_at` moment, spread over as many days
  as the rate needs, at random times inside a daily window. The whole plan is written
  to Postgres up front, so it is inspectable, editable and survives restarts.
- `release_due()` runs hourly from Celery beat and flips whatever is due.

The schedule deliberately does NOT live in Redis. Upstash bills per command and a
4k-member sorted set would mean range+remove traffic on every tick, forever, to
replicate a column Postgres already stores for free.
"""
import logging
import random
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, defer

from app.models.lpseo_page import LpseoPage, LpseoPageStatus

logger = logging.getLogger(__name__)

# Matches the publish gate in api/lpseo.py: a page under the QA score is served
# noindex regardless, so scheduling it would burn a slot and change nothing.
QUALITY_GATE = 80

# Only generated leaves are drip-released; pillars are published deliberately.
LEAF_PAGE_TYPE = "leaf"

# Times are UTC. The default window is 03:30-16:30 UTC, roughly 09:00-22:00 IST,
# so pages go live across a normal Indian working day rather than at 3am local.
DEFAULT_WINDOW = (time(3, 30), time(16, 30))
DEFAULT_MIN_PER_DAY = 20
DEFAULT_MAX_PER_DAY = 30

# Guaranteed notice before the first page goes live, so a mistaken arm can always be
# cancelled. "Next calendar day" is not enough: armed late evening IST that can be
# seven hours away and still the same local date.
MIN_LEAD = timedelta(hours=24)


def _eligible(db: Session):
    """Published leaves, currently noindex, past the QA gate.

    LEAVES ONLY. The industry and city pillars share this table but are
    hand-authored one at a time and go live on their own index toggle after a human
    clears their launch checklist. Without this filter, arming the drip would sweep
    a pillar into the 20-30/day trickle built for generated pages."""
    return (
        db.query(LpseoPage)
        .options(defer(LpseoPage.content))
        .filter(
            LpseoPage.page_type == LEAF_PAGE_TYPE,
            LpseoPage.status == LpseoPageStatus.PUBLISHED.value,
            LpseoPage.index_status == "noindex",
            or_(LpseoPage.quality_score.is_(None), LpseoPage.quality_score >= QUALITY_GATE),
        )
    )


def arm(
    db: Session,
    min_per_day: int = DEFAULT_MIN_PER_DAY,
    max_per_day: int = DEFAULT_MAX_PER_DAY,
    start: Optional[datetime] = None,
    window: tuple[time, time] = DEFAULT_WINDOW,
    seed: Optional[int] = None,
) -> dict:
    """Assign an index_at to every eligible unscheduled page. Idempotent in the sense
    that pages already carrying a schedule are left alone, so calling it again only
    picks up newly imported ones and appends them after the existing plan."""
    if min_per_day < 1 or max_per_day < min_per_day:
        raise ValueError("need 1 <= min_per_day <= max_per_day")

    rng = random.Random(seed)
    pages = _eligible(db).filter(LpseoPage.index_at.is_(None)).order_by(LpseoPage.id).all()
    if not pages:
        return {"scheduled": 0, "days": 0, "first": None, "last": None}

    # Append after anything already scheduled so a second arm() does not double up
    # a day that is already full.
    latest = db.query(func.max(LpseoPage.index_at)).filter(
        LpseoPage.index_status == "noindex", LpseoPage.index_at.isnot(None)
    ).scalar()
    now = start or datetime.now(timezone.utc)
    if latest is not None:
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        now = max(now, latest)
    lo, hi = window
    lo_s, hi_s = lo.hour * 3600 + lo.minute * 60, hi.hour * 3600 + hi.minute * 60
    if hi_s <= lo_s:
        raise ValueError("window end must be after window start")

    # Skip forward until a whole day's window sits beyond the notice period.
    earliest = now + MIN_LEAD
    day = earliest.date()
    while datetime.combine(day, time(0, 0), tzinfo=timezone.utc) + timedelta(seconds=lo_s) < earliest:
        day += timedelta(days=1)

    remaining = list(pages)
    rng.shuffle(remaining)  # release order should not mirror import order
    days = 0
    first = last = None
    while remaining:
        # Vary the daily count: a flat 25/day every day is its own pattern.
        take = min(rng.randint(min_per_day, max_per_day), len(remaining))
        batch, remaining = remaining[:take], remaining[take:]
        # Random second-of-day per page, so times are irregular rather than evenly
        # spaced. Sorted only to keep the stored plan readable.
        for page, offset in zip(batch, sorted(rng.sample(range(lo_s, hi_s), take))):
            page.index_at = datetime.combine(day, time(0, 0), tzinfo=timezone.utc) + timedelta(seconds=offset)
            first = page.index_at if first is None else min(first, page.index_at)
            last = page.index_at if last is None else max(last, page.index_at)
        days += 1
        day += timedelta(days=1)

    db.commit()
    logger.info("lpSEO drip armed: %s pages over %s days (%s -> %s)", len(pages), days, first, last)
    return {"scheduled": len(pages), "days": days,
            "first": first.isoformat() if first else None,
            "last": last.isoformat() if last else None}


def cancel(db: Session) -> dict:
    """Clear every pending schedule. Pages already flipped stay indexable."""
    n = (db.query(LpseoPage)
         .filter(LpseoPage.index_at.isnot(None), LpseoPage.index_status == "noindex")
         .update({LpseoPage.index_at: None}, synchronize_session=False))
    db.commit()
    return {"cancelled": n}


def status(db: Session) -> dict:
    pending = db.query(LpseoPage).filter(
        LpseoPage.index_at.isnot(None), LpseoPage.index_status == "noindex")
    total = pending.count()
    nxt = pending.with_entities(func.min(LpseoPage.index_at)).scalar()
    last = pending.with_entities(func.max(LpseoPage.index_at)).scalar()
    return {
        "scheduled": total,
        "eligible_unscheduled": _eligible(db).filter(LpseoPage.index_at.is_(None)).count(),
        "live": db.query(LpseoPage).filter(
            LpseoPage.status == LpseoPageStatus.PUBLISHED.value,
            LpseoPage.index_status == "index").count(),
        "next_at": nxt.isoformat() if nxt else None,
        "last_at": last.isoformat() if last else None,
    }


def release_due(db: Session, now: Optional[datetime] = None, limit: int = 200) -> list[dict]:
    """Flip every page whose moment has passed. Returns revalidation entries.

    `limit` is a blast-radius cap, not a rate limit: at 20-30/day an hourly tick sees
    a handful, so hitting 200 means something upstream is wrong (clock jump, a plan
    written in the past) and we would rather bleed it out over a few ticks than
    publish the whole corpus in one go.
    """
    now = now or datetime.now(timezone.utc)
    due = (db.query(LpseoPage)
           .options(defer(LpseoPage.content))
           .filter(LpseoPage.page_type == LEAF_PAGE_TYPE,
                   LpseoPage.index_status == "noindex",
                   LpseoPage.index_at.isnot(None),
                   LpseoPage.index_at <= now,
                   LpseoPage.status == LpseoPageStatus.PUBLISHED.value)
           .order_by(LpseoPage.index_at)
           .limit(limit)
           .all())
    released = []
    for page in due:
        if page.quality_score is not None and page.quality_score < QUALITY_GATE:
            # Dropped below the gate since it was scheduled: unschedule rather than
            # publish something the API would serve noindex anyway.
            page.index_at = None
            continue
        page.index_status = "index"
        page.index_at = None
        released.append({"slug": page.slug, "country": page.country, "industry_slug": page.industry_slug})
    db.commit()
    if released:
        logger.info("lpSEO drip released %s pages: %s", len(released), [r["slug"] for r in released])
    return released
