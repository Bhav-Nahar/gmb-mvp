"""Google Search Console read-only client for pSEO organic performance.

One shared service-account credential covers the whole property (pSEO pages
aren't org-scoped, unlike the per-org GBP OAuth flow). Inert until
GSC_SERVICE_ACCOUNT_JSON / GSC_PROPERTY_URL are configured — every function
returns an empty result rather than raising, so the admin panel just shows
no data until it's set up.
"""
import json
import logging
from datetime import date, timedelta
from typing import Optional

from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
_CACHE_TTL = 6 * 60 * 60  # GSC data itself lags 2-3 days; no need to refetch more than every few hours
# GSC data isn't final for the most recent ~2 days — asking for them just returns zeros.
_REPORTING_LAG_DAYS = 3

_service = None


def is_configured() -> bool:
    return bool(settings.GSC_SERVICE_ACCOUNT_JSON and settings.GSC_PROPERTY_URL)


def _get_service():
    global _service
    if _service is not None:
        return _service
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    info = json.loads(settings.GSC_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
    _service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    return _service


def _date_range(days: int) -> tuple[str, str]:
    end = date.today() - timedelta(days=_REPORTING_LAG_DAYS)
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def fetch_page_metrics(path_prefix: str, days: int = 28) -> dict[str, dict]:
    """Clicks/impressions/CTR/position per page URL under `path_prefix`
    (e.g. "/gbp-management/"). Keyed by the full page URL. Cached in Redis —
    callers join back to their own rows (e.g. by slug) themselves."""
    if not is_configured():
        return {}

    cache_key = f"gsc_page_metrics:{path_prefix}:{days}"
    r = get_redis()
    try:
        cached = r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    start, end = _date_range(days)
    out: dict[str, dict] = {}
    try:
        service = _get_service()
        start_row = 0
        while True:
            resp = service.searchanalytics().query(
                siteUrl=settings.GSC_PROPERTY_URL,
                body={
                    "startDate": start,
                    "endDate": end,
                    "dimensions": ["page"],
                    "dimensionFilterGroups": [{
                        "filters": [{"dimension": "page", "operator": "contains", "expression": path_prefix}]
                    }],
                    "rowLimit": 25000,
                    "startRow": start_row,
                },
            ).execute()
            rows = resp.get("rows", [])
            for row in rows:
                url = row["keys"][0]
                out[url] = {
                    "clicks": row.get("clicks", 0),
                    "impressions": row.get("impressions", 0),
                    "ctr": row.get("ctr", 0.0),
                    "position": row.get("position", 0.0),
                }
            if len(rows) < 25000:
                break
            start_row += 25000
    except Exception as e:
        logger.warning(f"GSC page metrics fetch failed: {e}")
        return {}

    try:
        r.setex(cache_key, _CACHE_TTL, json.dumps(out))
    except Exception:
        pass
    return out


def fetch_top_queries(page_url: str, days: int = 28, limit: int = 10) -> list[dict]:
    """Top search queries driving one exact page URL, by clicks desc."""
    if not is_configured():
        return []

    cache_key = f"gsc_queries:{page_url}:{days}"
    r = get_redis()
    try:
        cached = r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    start, end = _date_range(days)
    out: list[dict] = []
    try:
        service = _get_service()
        resp = service.searchanalytics().query(
            siteUrl=settings.GSC_PROPERTY_URL,
            body={
                "startDate": start,
                "endDate": end,
                "dimensions": ["query"],
                "dimensionFilterGroups": [{
                    "filters": [{"dimension": "page", "operator": "equals", "expression": page_url}]
                }],
                "rowLimit": limit,
            },
        ).execute()
        for row in resp.get("rows", []):
            out.append({
                "query": row["keys"][0],
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": row.get("ctr", 0.0),
                "position": row.get("position", 0.0),
            })
    except Exception as e:
        logger.warning(f"GSC query fetch failed for {page_url}: {e}")
        return []

    try:
        r.setex(cache_key, _CACHE_TTL, json.dumps(out))
    except Exception:
        pass
    return out
