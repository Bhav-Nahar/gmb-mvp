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


def _revalidate_url() -> str:
    """FRONTEND_URL is the public-facing URL (also used to build indexed page URLs
    for GSC lookups elsewhere) — must stay untouched there. But a backend container
    calling `localhost` reaches itself, not the frontend container, so only this
    internal POST swaps to the docker-compose service name. Mirrors the frontend's
    own localhost->backend swap for its SSR fetches."""
    url = settings.FRONTEND_URL.rstrip('/')
    if 'localhost' in url:
        url = url.replace('localhost', 'frontend')
    return f"{url}/api/revalidate"


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

    url = _revalidate_url()

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


async def _post_revalidate(payload: dict) -> None:
    """POST a payload to the frontend revalidate route. Fire-and-forget."""
    secret = settings.REVALIDATE_SECRET
    if not secret:
        logger.warning("REVALIDATE_SECRET is not set, skipping pSEO revalidation call.")
        return
    url = _revalidate_url()
    headers = {"x-revalidate-secret": secret, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            logger.info(f"Revalidated pSEO: {payload}")
    except Exception as e:
        logger.warning(f"pSEO revalidation failed for {payload}: {e}")


def _run_revalidate(payload: dict) -> None:
    """Run one revalidate POST on a fresh event loop (Celery/API threads have none)."""
    try:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_post_revalidate(payload))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"pSEO revalidation encountered an error: {str(e)}")


# pSEO/lpSEO fetches are tagged PER PAGE ('{type}:{slug}') for the leaf. There is
# deliberately NO global '{type}' tag. The list fetch is tagged TWO ways:
#   - '{type}-list'                    — corpus-wide callers (sitemap, root/country hubs)
#   - '{type}-list:{country}:{industry}' — industry-scoped, embedded by every LEAF
#     (its sibling links) and by the industry hub.
# Every leaf embeds an industry-scoped list fetch, so a single edit busts only its
# own industry's leaves via the scoped tag — NOT the whole corpus. Using the bare
# '{type}-list' tag on leaves was the original blowup: one edit re-rendered all N
# pages on their next crawl (Vercel invocations + backend hits + Redis reads).

def _seo_revalidation_payload(entries: List[dict], segment: str, tag_prefix: str) -> dict:
    """Build a {tags, paths} payload for the frontend revalidate route.

    Busts the shared '{tag_prefix}-list' tag (hubs + sitemap reflect the new
    published set) plus, per entry, the per-slug data tag and the leaf/hub/root
    paths. Callers pass country explicitly so deleted rows (already gone from the
    DB) still resolve the right locale."""
    # Global list tag covers corpus-wide callers only (sitemap, root/country hubs).
    # Leaf pages embed an INDUSTRY-scoped list fetch for their siblings, tagged
    # '{prefix}-list:{country}:{industry}' — so per-industry busts here re-render just
    # that industry's leaves on next crawl, not the entire corpus. Keep the tag string
    # in sync with listPseoPages/listLpseoPages in the frontend libs.
    tags = {f"{tag_prefix}-list"}
    paths = set()
    for e in entries:
        slug = e.get("slug")
        if not slug:
            continue
        country = e.get("country") or "in"
        locale = f"en-{country}"
        base = f"/{locale}/{segment}"
        tags.add(f"{tag_prefix}:{slug}")
        paths.add(base)                      # locale root hub
        paths.add(f"{base}/{slug}")          # leaf
        if e.get("industry_slug"):
            tags.add(f"{tag_prefix}-list:{country}:{e['industry_slug']}")
            paths.add(f"{base}/{e['industry_slug']}")  # industry hub
    return {"tags": sorted(tags), "paths": sorted(paths)}


def trigger_pseo_page_flush(slug: str, country: str) -> None:
    """Flush ONE pSEO page's ISR cache (HTML + data) without touching the rest."""
    _run_revalidate(_seo_revalidation_payload([{"slug": slug, "country": country}], "gbp-management", "pseo"))


def trigger_bulk_pseo_revalidation(entries: List[dict]) -> None:
    """Revalidate pSEO pages after admin edits, publishes, or bulk imports. Each
    entry is {"slug", "country", "industry_slug"}. Fire-and-forget: never raises,
    never blocks; a miss falls back to the daily ISR cycle. Callers batch large
    sets (see the admin bulk-status flow) so one POST never carries thousands of
    paths into a single Vercel invocation."""
    entries = [e for e in (entries or []) if e and e.get("slug")]
    if not entries:
        return
    _run_revalidate(_seo_revalidation_payload(entries, "gbp-management", "pseo"))


# ── lpSEO (local-SEO managed pages, /local-seo-services) ─────────────────────
# Identical contract; the only difference is the URL segment and tag prefix.

def trigger_lpseo_page_flush(slug: str, country: str) -> None:
    """Flush ONE local-SEO page's ISR cache (HTML + data) without touching others."""
    _run_revalidate(_seo_revalidation_payload([{"slug": slug, "country": country}], "local-seo-services", "lpseo"))


def trigger_bulk_lpseo_revalidation(entries: List[dict]) -> None:
    """Revalidate local-SEO pages after admin edits/publishes/imports. Each entry is
    {"slug", "country", "industry_slug"}; revalidates the leaf, its industry hub and
    the locale root hub, plus the shared 'lpseo-list' tag."""
    entries = [e for e in (entries or []) if e and e.get("slug")]
    if not entries:
        return
    _run_revalidate(_seo_revalidation_payload(entries, "local-seo-services", "lpseo"))
