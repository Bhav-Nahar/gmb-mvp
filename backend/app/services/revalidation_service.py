import logging
import asyncio
from typing import List
import httpx
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.microsite import Microsite
from app.core.config import settings
from app.core.redis_client import get_redis as _get_redis

logger = logging.getLogger(__name__)

# Max concurrent outgoing HTTP calls to the Next.js frontend. The semaphore
# itself is created per-call inside the event loop (see _revalidate_all) — a
# module-level Semaphore binds to the first loop it's used in and would raise
# "future belongs to a different loop" on the next bulk call, since each call
# spins up a fresh loop.
_REVALIDATION_CONCURRENCY = 10

async def trigger_microsite_revalidation(location_slug: str) -> None:
    """
    Fire-and-forget POST to the frontend's /api/revalidate route.
    Single-level URL: revalidates the path /{location_slug}.
    Must NOT raise or block the calling flow if this fails — a failed
    revalidation should log a warning and fall back silently to the
    hourly ISR cycle, never break a review sync, listing publish, or photo sync.
    """
    secret = settings.REVALIDATE_SECRET
    if not secret:
        logger.warning("REVALIDATE_SECRET is not set, skipping revalidation call.")
        return

    frontend_url = settings.FRONTEND_URL.rstrip('/')
    url = f"{frontend_url}/api/revalidate"

    payload = {"slug": location_slug}

    headers = {
        "x-revalidate-secret": secret,
        "Content-Type": "application/json"
    }

    try:
        # Use a short timeout so we never hang the backend tasks
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Successfully revalidated microsite {location_slug}")
    except httpx.HTTPStatusError as e:
        logger.warning(f"Revalidation failed with status {e.response.status_code} for {location_slug}: {e.response.text}")
    except Exception as e:
        logger.warning(f"Revalidation failed for {location_slug}: {str(e)}")


async def _revalidate_all(slugs: List[str]) -> None:
    """Revalidate all location_slugs concurrently, capped by a semaphore created
    inside the running loop."""
    sem = asyncio.Semaphore(_REVALIDATION_CONCURRENCY)

    async def _one(location_slug: str) -> None:
        async with sem:
            await trigger_microsite_revalidation(location_slug)

    await asyncio.gather(*[_one(s) for s in slugs], return_exceptions=True)


def trigger_bulk_microsite_revalidation(location_ids: List[int]) -> None:
    """
    Synchronous wrapper to trigger revalidation for a batch of locations.
    Uses asyncio event loop to execute limited concurrent HTTP calls.
    Includes a Redis-based debounce lock to prevent duplicate revalidation storms
    when multiple decoupled sync tasks complete simultaneously.
    """
    if not location_ids:
        return

    db: Session = SessionLocal()
    try:
        # Fetch published or unpublished microsites for these locations to allow clearing cache on unpublish
        microsites = db.query(Microsite).filter(
            Microsite.location_id.in_(location_ids),
            Microsite.status.in_(["published", "unpublished"])
        ).all()
        
        if not microsites:
            return

        r = _get_redis()
        slugs = []
        for ms in microsites:
            # Drop the backend response cache (api/public_microsites.py) for every
            # affected microsite regardless of the debounce below — a stale cache
            # after an unpublish is a correctness issue, and deletion is cheap.
            try:
                r.delete(f"public_microsite:{ms.location_slug}")
            except Exception:
                pass
            # 60-second debounce lock to prevent double-triggering for the same location
            # (e.g., when review sync and photo sync finish back-to-back). 60s is long
            # enough to absorb rapid successive background task completions, but short
            # enough that a user-triggered publish followed quickly by an unpublish
            # (or vice versa) still fires both revalidations.
            lock_key = f"lock:revalidate_microsite:{ms.location_id}"
            lock = r.lock(lock_key, timeout=60)
            
            if lock.acquire(blocking=False):
                slugs.append(ms.location_slug)
            else:
                logger.info(f"Skipping revalidation for {ms.location_slug} - recently revalidated.")

        if slugs:
            # Always create a fresh event loop. asyncio.get_event_loop() is deprecated
            # in Python 3.10+ and raises a DeprecationWarning (error in 3.12) when
            # called from a thread that has no running loop — exactly the case in
            # Celery workers, which are thread-based.
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_revalidate_all(slugs))
            finally:
                loop.close()
    except Exception as e:
        logger.error(f"Bulk microsite revalidation encountered an error: {str(e)}")
    finally:
        db.close()


async def _post_revalidate_paths(paths: List[str]) -> None:
    """POST a batch of literal paths to the frontend revalidate route. Fire-and-forget."""
    secret = settings.REVALIDATE_SECRET
    if not secret:
        logger.warning("REVALIDATE_SECRET is not set, skipping pSEO revalidation call.")
        return
    url = f"{settings.FRONTEND_URL.rstrip('/')}/api/revalidate"
    headers = {"x-revalidate-secret": secret, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={"paths": paths}, headers=headers)
            resp.raise_for_status()
            logger.info(f"Revalidated pSEO paths: {paths}")
    except Exception as e:
        logger.warning(f"pSEO revalidation failed for {paths}: {e}")


def trigger_bulk_pseo_revalidation(entries: List[dict]) -> None:
    """Revalidate pSEO pages after admin edits, publishes, or bulk imports.

    Each entry is {"slug", "country", "industry_slug"}. For every entry we
    revalidate the locale-prefixed leaf (/{locale}/gbp-management/{slug}), its
    industry hub (/{locale}/gbp-management/{industry_slug}) and that locale's root
    hub (/{locale}/gbp-management) — so a newly published city appears in the hub
    listings immediately, and deletes clear the card + serve a 404. Callers pass
    country explicitly so deleted rows (already gone from the DB) still resolve the
    right locale. Fire-and-forget: never raises, never blocks; a miss falls back to
    the hourly ISR cycle."""
    entries = [e for e in (entries or []) if e and e.get("slug")]
    if not entries:
        return

    paths = set()
    for e in entries:
        locale = f"en-{(e.get('country') or 'in')}"
        base = f"/{locale}/gbp-management"
        paths.add(base)
        paths.add(f"{base}/{e['slug']}")
        if e.get("industry_slug"):
            paths.add(f"{base}/{e['industry_slug']}")

    try:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_post_revalidate_paths(sorted(paths)))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Bulk pSEO revalidation encountered an error: {str(e)}")
