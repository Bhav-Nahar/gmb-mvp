"""Programmatic SEO (industry x city) landing pages.

Two routers:
- public_router  -> /api/v1/public/pseo   (unauthenticated, Redis-cached, published only)
- admin_router   -> /api/v1/admin/pseo    (superadmin CRUD + CSV/XLSX bulk import)

Content model: identity/meta live as columns; every template section lives in the
`content` JSON blob (see CONTENT_LIST_COLS / CONTENT_PAIR_COLS for the import shape).
"""
import csv
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session, defer

from app.db.session import get_db
from app.api.deps import superadmin_required
from app.core.config import settings
from app.core.redis_client import get_redis
from app.models.pseo_page import PseoPage, PseoPageStatus
from app.models.user import User
from app.services import gsc_service
from app.services.revalidation_service import trigger_bulk_pseo_revalidation, trigger_pseo_page_flush

logger = logging.getLogger(__name__)

public_router = APIRouter()
admin_router = APIRouter()

_CACHE_TTL = 60 * 60  # backstop matching the frontend's hourly ISR cycle


def _cache_key(slug: str) -> str:
    return f"public_pseo:{slug}"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


# Accept common country spellings on import and normalize to an ISO-3166 alpha-2
# lowercase code. Unknown 2-letter inputs pass through; anything else -> "in".
_COUNTRY_ALIASES = {
    "in": "in", "india": "in", "ind": "in",
    "us": "us", "usa": "us", "united states": "us", "united states of america": "us", "america": "us",
    "gb": "gb", "uk": "gb", "united kingdom": "gb", "england": "gb", "britain": "gb",
    "ca": "ca", "canada": "ca",
    "au": "au", "australia": "au",
    "ae": "ae", "uae": "ae", "united arab emirates": "ae",
    "sg": "sg", "singapore": "sg",
    "za": "za", "south africa": "za",
    "ie": "ie", "ireland": "ie",
    "nz": "nz", "new zealand": "nz",
}


def _country_code(raw: str) -> str:
    key = (raw or "").strip().lower()
    if not key:
        return "in"
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    if len(key) == 2 and key.isalpha():
        return key
    return "in"


def _locale(country: str) -> str:
    """URL/hreflang locale. English content only for now -> en-{country}."""
    return f"en-{country}"


# Approval gate: a page is served/listed as indexable only if not manually flagged
# noindex AND its QA score clears 80. A null score is treated as ungated (existing
# live pages don't get silently deindexed); set a score below 80 to auto-noindex.
_QUALITY_GATE = 80


def _effective_index_status(p: PseoPage) -> str:
    if (p.index_status or "index") != "index":
        return "noindex"
    if p.quality_score is not None and p.quality_score < _QUALITY_GATE:
        return "noindex"
    return "index"


def _public_payload(p: PseoPage) -> dict:
    locale = _locale(p.country)
    return {
        "slug": p.slug,
        "country": p.country,
        "locale": locale,
        "industry_label": p.industry_label,
        "industry_slug": p.industry_slug,
        "city_label": p.city_label,
        "city_slug": p.city_slug,
        "meta_title": p.meta_title,
        "meta_description": p.meta_description,
        "h1": p.h1,
        # Explicit admin override only; the frontend builds the default self-canonical
        # from its own public NEXT_PUBLIC_APP_URL when this is null.
        "canonical_url": p.canonical_url or None,
        "index_status": _effective_index_status(p),
        "quality_score": p.quality_score,
        "content": p.content or {},
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ── Public ────────────────────────────────────────────────────────────────────

@public_router.get("")
def list_published_pages(
    industry: Optional[str] = None,
    country: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Slim list for the sitemap / hub links (no content bodies). Filters:
    ?country={cc} for a per-market hub, ?industry={slug} for an industry hub.
    Excludes noindex pages so they never enter the sitemap or hub listings."""
    query = (
        db.query(
            PseoPage.slug, PseoPage.country, PseoPage.industry_label, PseoPage.industry_slug,
            PseoPage.city_label, PseoPage.city_slug, PseoPage.updated_at,
        )
        .filter(
            PseoPage.status == PseoPageStatus.PUBLISHED.value,
            PseoPage.index_status == "index",
            or_(PseoPage.quality_score.is_(None), PseoPage.quality_score >= _QUALITY_GATE),
        )
    )
    if industry:
        query = query.filter(PseoPage.industry_slug == industry)
    if country:
        query = query.filter(PseoPage.country == _country_code(country))
    rows = query.order_by(PseoPage.country, PseoPage.industry_slug, PseoPage.city_slug).all()
    return {
        "pages": [
            {
                "slug": r.slug,
                "country": r.country,
                "locale": _locale(r.country),
                "industry_label": r.industry_label,
                "industry_slug": r.industry_slug,
                "city_label": r.city_label,
                "city_slug": r.city_slug,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
    }


@public_router.get("/{slug}")
def get_published_page(slug: str, db: Session = Depends(get_db)):
    r = get_redis()
    try:
        cached = r.get(_cache_key(slug))
        if cached:
            return json.loads(cached)
    except Exception:
        pass  # cache down -> serve from DB

    page = (
        db.query(PseoPage)
        .filter(PseoPage.slug == slug, PseoPage.status == PseoPageStatus.PUBLISHED.value)
        .first()
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    payload = _public_payload(page)
    try:
        r.setex(_cache_key(slug), _CACHE_TTL, json.dumps(payload))
    except Exception:
        pass
    return payload


# ── Admin ─────────────────────────────────────────────────────────────────────

class PseoPageIn(BaseModel):
    slug: Optional[str] = None
    country: Optional[str] = None
    industry_label: str
    industry_slug: Optional[str] = None
    city_label: str
    city_slug: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    h1: Optional[str] = None
    canonical_url: Optional[str] = None
    index_status: Optional[str] = None
    quality_score: Optional[int] = None
    content: dict[str, Any] = Field(default_factory=dict)
    status: Optional[str] = None  # draft | published


def _apply_defaults(data: PseoPageIn) -> PseoPageIn:
    """Fill identity/meta gaps from the industry+city+country so an import row only
    needs labels. Slug stays country-agnostic ({industry}-in-{city}); the country
    lives in the URL prefix (/en-us/gbp-management/{slug}), so US and India versions
    of the same city would still get distinct slugs via the city (new-york-ny vs mumbai)."""
    data.country = _country_code(data.country)
    data.industry_slug = data.industry_slug or _slugify(data.industry_label)
    data.city_slug = data.city_slug or _slugify(data.city_label)
    data.slug = data.slug or f"{data.industry_slug}-in-{data.city_slug}"
    data.h1 = data.h1 or f"Google Business Profile Management for {data.industry_label} in {data.city_label}"
    data.meta_title = data.meta_title or f"GBP Management for {data.industry_label} in {data.city_label} | Pinzo"
    data.meta_description = data.meta_description or (
        f"Manage and optimize Google Business Profiles for {data.industry_label.lower()} in {data.city_label}. "
        "Reviews, posts, local SEO and AI visibility from one dashboard. Free audit, no card required."
    )
    data.index_status = "noindex" if (data.index_status or "").strip().lower() == "noindex" else "index"
    return data


def _invalidate(slug: str, country: str, industry_slug: str) -> None:
    """Drop the Redis copy and ask the frontend to re-render the page + its hubs
    for the right locale. Never raises. Passing country/industry explicitly means
    deletes (row already gone) still revalidate the correct paths."""
    try:
        get_redis().delete(_cache_key(slug))
    except Exception:
        pass
    trigger_bulk_pseo_revalidation([{"slug": slug, "country": country, "industry_slug": industry_slug}])


def _admin_row(p: PseoPage) -> dict:
    return {
        "id": p.id,
        "slug": p.slug,
        "country": p.country,
        "locale": _locale(p.country),
        "industry_label": p.industry_label,
        "city_label": p.city_label,
        "status": p.status,
        "index_status": p.index_status or "index",
        "quality_score": p.quality_score,
        "meta_title": p.meta_title,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@admin_router.get("/stats")
def admin_pseo_stats(db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    total = db.query(PseoPage).count()
    published = db.query(PseoPage).filter(PseoPage.status == PseoPageStatus.PUBLISHED.value).count()
    noindex = db.query(PseoPage).filter(PseoPage.index_status == "noindex").count()
    return {"total": total, "published": published, "draft": total - published, "noindex": noindex}


@admin_router.get("/gsc-metrics")
def admin_pseo_gsc_metrics(days: int = 28, _: User = Depends(superadmin_required)):
    """Clicks/impressions/CTR/position for every pSEO page, keyed by slug.
    Empty + configured=False until GSC_SERVICE_ACCOUNT_JSON/GSC_PROPERTY_URL are set."""
    if not gsc_service.is_configured():
        return {"configured": False, "metrics": {}}
    raw = gsc_service.fetch_page_metrics("/gbp-management/", days=days)
    by_slug = {url.rstrip("/").rsplit("/", 1)[-1]: m for url, m in raw.items()}
    return {"configured": True, "metrics": by_slug}


@admin_router.get("/{page_id:int}/gsc-queries")
def admin_pseo_gsc_queries(page_id: int, days: int = 28, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    """Top search queries driving one page — used in the editor to show which
    keywords are actually working."""
    page = db.query(PseoPage).get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if not gsc_service.is_configured():
        return {"configured": False, "queries": []}
    url = f"{settings.FRONTEND_URL.rstrip('/')}/{_locale(page.country)}/gbp-management/{page.slug}"
    return {"configured": True, "queries": gsc_service.fetch_top_queries(url, days=days)}


def _filtered_query(db: Session, q: Optional[str], status: Optional[str]):
    query = db.query(PseoPage)
    if status in (PseoPageStatus.DRAFT.value, PseoPageStatus.PUBLISHED.value):
        query = query.filter(PseoPage.status == status)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            (PseoPage.slug.ilike(like))
            | (PseoPage.industry_label.ilike(like))
            | (PseoPage.city_label.ilike(like))
        )
    return query


@admin_router.get("")
def admin_list_pages(
    q: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: Optional[str] = None,  # None (default: updated_at desc) | "clicks" | "impressions"
    sort_dir: str = "desc",
    gsc_days: int = 28,
    db: Session = Depends(get_db),
    _: User = Depends(superadmin_required),
):
    # Admin rows never render the fat `content` JSON — defer it so neither the
    # paginated list nor the sort-everything path drags every page's body out of
    # Supabase (egress + memory) just to build slim rows.
    query = _filtered_query(db, q, status).options(defer(PseoPage.content))
    total = query.count()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    if sort_by in ("clicks", "impressions"):
        # GSC metrics live in Redis/Google, not Postgres, so this sort happens in Python
        # against the (cached) metrics map rather than as a DB ORDER BY. Fine at pSEO's
        # current scale (thousands of rows) — revisit if it grows into the tens of thousands.
        raw = gsc_service.fetch_page_metrics("/gbp-management/", days=gsc_days)
        by_slug = {url.rstrip("/").rsplit("/", 1)[-1]: m for url, m in raw.items()}
        all_rows = query.all()
        all_rows.sort(key=lambda p: by_slug.get(p.slug, {}).get(sort_by, 0), reverse=(sort_dir != "asc"))
        rows = all_rows[(page - 1) * page_size: page * page_size]
    else:
        rows = query.order_by(PseoPage.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {"pages": [_admin_row(p) for p in rows], "total": total, "page": page, "page_size": page_size}


@admin_router.get("/ids")
def admin_list_ids(
    q: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(superadmin_required),
):
    """Every page ID matching the current filter, so the admin UI can slice a big
    'select all N matching' set into small batches and drive bulk-status one batch
    at a time (with progress) instead of one giant, event-loop-freezing request."""
    ids = [row.id for row in _filtered_query(db, q, status).with_entities(PseoPage.id).order_by(PseoPage.id).all()]
    return {"ids": ids}


class BulkStatusIn(BaseModel):
    ids: list[int] = Field(default_factory=list)
    # When set, applies to every page matching this filter instead of `ids`
    # (same q/status semantics as the list endpoint) — powers "select all N matching".
    select_all: bool = False
    q: Optional[str] = None
    filter_status: Optional[str] = None
    status: Optional[str] = None  # draft | published — target status to set
    index_status: Optional[str] = None  # index | noindex — target index_status to set


@admin_router.post("/bulk-status")
def admin_bulk_status(body: BulkStatusIn, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    if body.status is not None and body.status not in (PseoPageStatus.DRAFT.value, PseoPageStatus.PUBLISHED.value):
        raise HTTPException(status_code=400, detail=f"invalid status: {body.status}")
    if body.index_status is not None and body.index_status not in ("index", "noindex"):
        raise HTTPException(status_code=400, detail=f"invalid index_status: {body.index_status}")
    if body.status is None and body.index_status is None:
        return {"updated": 0}
    # The admin UI batches 'select all matching' into small explicit-id calls (see
    # /ids), so this handler now sees at most a page-sized batch. select_all stays
    # as an API-only fallback, still capped, with content deferred (never read here).
    if body.select_all:
        pages = _filtered_query(db, body.q, body.filter_status).options(defer(PseoPage.content)).limit(5000).all()  # ponytail: hard cap, raise if a real run ever needs more
    else:
        if not body.ids:
            return {"updated": 0}
        pages = db.query(PseoPage).options(defer(PseoPage.content)).filter(PseoPage.id.in_(body.ids)).all()
    touched = []
    skipped_unscored = 0
    for page in pages:
        if body.status == PseoPageStatus.PUBLISHED.value and page.quality_score is None:
            skipped_unscored += 1  # same publish gate as _set_status
            continue
        if body.status is not None:
            page.status = body.status
            if body.status == PseoPageStatus.PUBLISHED.value:
                page.published_at = datetime.now(timezone.utc)
        if body.index_status is not None:
            page.index_status = body.index_status
        touched.append({"slug": page.slug, "country": page.country, "industry_slug": page.industry_slug})
    db.commit()
    if touched:
        try:
            get_redis().delete(*[_cache_key(t["slug"]) for t in touched])  # one Redis command, not one per page
        except Exception:
            pass
    trigger_bulk_pseo_revalidation(touched)
    return {"updated": len(pages) - skipped_unscored, "skipped_unscored": skipped_unscored}


# :int converter so GET /import/columns below isn't swallowed by this route.
@admin_router.get("/{page_id:int}")
def admin_get_page(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    page = db.query(PseoPage).get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return {**_admin_row(page), "meta_description": page.meta_description, "h1": page.h1,
            "canonical_url": page.canonical_url, "industry_slug": page.industry_slug,
            "city_slug": page.city_slug, "content": page.content or {}}


@admin_router.post("")
def admin_create_page(body: PseoPageIn, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    body = _apply_defaults(body)
    if db.query(PseoPage).filter(PseoPage.slug == body.slug).first():
        raise HTTPException(status_code=409, detail=f"Slug already exists: {body.slug}")
    page = PseoPage(
        slug=body.slug, country=body.country, industry_label=body.industry_label, industry_slug=body.industry_slug,
        city_label=body.city_label, city_slug=body.city_slug,
        meta_title=body.meta_title, meta_description=body.meta_description, h1=body.h1,
        canonical_url=body.canonical_url or None, index_status=body.index_status, quality_score=body.quality_score,
        content=body.content, status=body.status or PseoPageStatus.DRAFT.value,
        published_at=datetime.now(timezone.utc) if body.status == PseoPageStatus.PUBLISHED.value else None,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    if page.status == PseoPageStatus.PUBLISHED.value:
        _invalidate(page.slug, page.country, page.industry_slug)
    return _admin_row(page)


@admin_router.patch("/{page_id}")
def admin_update_page(page_id: int, body: PseoPageIn, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    page = db.query(PseoPage).get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    body = _apply_defaults(body)
    if body.slug != page.slug and db.query(PseoPage).filter(PseoPage.slug == body.slug).first():
        raise HTTPException(status_code=409, detail=f"Slug already exists: {body.slug}")
    old_slug, old_country, old_industry = page.slug, page.country, page.industry_slug
    page.slug = body.slug
    page.country = body.country
    page.industry_label, page.industry_slug = body.industry_label, body.industry_slug
    page.city_label, page.city_slug = body.city_label, body.city_slug
    page.meta_title, page.meta_description, page.h1 = body.meta_title, body.meta_description, body.h1
    page.canonical_url = body.canonical_url or None
    page.index_status = body.index_status
    page.quality_score = body.quality_score
    page.content = body.content
    if body.status in (PseoPageStatus.DRAFT.value, PseoPageStatus.PUBLISHED.value):
        if body.status == PseoPageStatus.PUBLISHED.value and page.status != PseoPageStatus.PUBLISHED.value:
            page.published_at = datetime.now(timezone.utc)
        page.status = body.status
    db.commit()
    # One revalidation pass covering the old URL/hubs and — on a slug/country change
    # — the new one, in a single Redis delete + single frontend POST rather than two
    # blocking round-trips back to back.
    entries = [{"slug": old_slug, "country": old_country, "industry_slug": old_industry}]
    if page.slug != old_slug or page.country != old_country:
        entries.append({"slug": page.slug, "country": page.country, "industry_slug": page.industry_slug})
    try:
        get_redis().delete(*[_cache_key(e["slug"]) for e in entries])
    except Exception:
        pass
    trigger_bulk_pseo_revalidation(entries)
    return _admin_row(page)


@admin_router.post("/{page_id}/publish")
def admin_publish_page(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    return _set_status(page_id, PseoPageStatus.PUBLISHED.value, db)


@admin_router.post("/{page_id}/unpublish")
def admin_unpublish_page(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    return _set_status(page_id, PseoPageStatus.DRAFT.value, db)


def _set_status(page_id: int, new_status: str, db: Session) -> dict:
    page = db.query(PseoPage).get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    # Unscored pages must not publish: null quality_score bypasses the >=80 index
    # gate (_effective_index_status treats null as index), so an unscored thin page
    # would go straight to Google. Score it first, then publish.
    if new_status == PseoPageStatus.PUBLISHED.value and page.quality_score is None:
        raise HTTPException(status_code=422, detail="quality_score is required before publishing (>=80 to be indexable)")
    page.status = new_status
    if new_status == PseoPageStatus.PUBLISHED.value:
        page.published_at = datetime.now(timezone.utc)
    db.commit()
    _invalidate(page.slug, page.country, page.industry_slug)
    return _admin_row(page)


@admin_router.post("/{page_id:int}/flush-cache")
def admin_flush_page_cache(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    """Flush the ISR + backend caches for ONE page so its data changes go live now,
    without busting any other pSEO page (unlike publish, which uses the global tag)."""
    page = db.query(PseoPage).get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    try:
        get_redis().delete(_cache_key(page.slug))
    except Exception:
        pass
    trigger_pseo_page_flush(page.slug, page.country)
    return {"flushed": True, "slug": page.slug, "path": f"/{_locale(page.country)}/gbp-management/{page.slug}"}


@admin_router.delete("/{page_id}")
def admin_delete_page(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    page = db.query(PseoPage).get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    slug, country, industry = page.slug, page.country, page.industry_slug
    db.delete(page)
    db.commit()
    _invalidate(slug, country, industry)
    return {"deleted": True}


# ── Bulk import (CSV / XLSX) ─────────────────────────────────────────────────
#
# One row per page. List cells are `|`-separated; two-part items (problems,
# solutions, workflow steps, FAQs) use `Title :: detail` inside each `|` item.

# Real columns set directly on the row (not stashed in content JSON).
IDENTITY_COLS = ["slug", "country", "industry_label", "industry_slug", "city_label", "city_slug",
                 "meta_title", "meta_description", "h1", "canonical_url", "index_status",
                 "quality_score", "status"]
CONTENT_TEXT_COLS = [
    "badge", "hero_sub", "primary_cta", "secondary_cta", "answer_block",
    "why_matters_body", "reviews_body", "example_review", "example_reply",
    "city_visibility_body", "final_heading", "final_sub", "final_button",
    # Softer SEO/meta fields — stored in content JSON, rendered where relevant.
    "primary_keyword", "page_type", "template_version", "region", "last_updated",
]
CONTENT_LIST_COLS = [
    "why_matters_points", "gbp_categories", "gbp_services", "gbp_attributes",
    "review_themes", "post_ideas", "photo_checklist", "neighborhoods",
    "single_points", "multi_points", "secondary_keywords",
]
# Pair cells: "Title :: detail" per item.
CONTENT_PAIR_COLS = ["problems", "solutions", "monthly_workflow", "faqs"]
# Tuple cells: split on every "::" into typed dicts per item.
#   review_examples: "review :: reply"
#   related_pages:   "anchor :: url"  (optional editorial cross-links)
# CSV holds only per-page content. Excluded on purpose because the template
# auto-generates them or renders a near-constant default (override via admin JSON
# if ever needed): internal_links, comparison, audit_checklist, og_image.
CONTENT_TUPLE_COLS = ["review_examples", "related_pages"]
# `url` and `schema_type` are accepted in the header but ignored: url is derived from
# locale+slug, schema_type is generated server-side to keep structured data valid.
IGNORED_COLS = ["url", "schema_type"]
ALL_COLS = IDENTITY_COLS + CONTENT_TEXT_COLS + CONTENT_LIST_COLS + CONTENT_PAIR_COLS + CONTENT_TUPLE_COLS + IGNORED_COLS


def _split_list(cell: str) -> list[str]:
    return [s.strip() for s in (cell or "").split("|") if s.strip()]


def _split_pairs(cell: str) -> list[dict]:
    out = []
    for item in _split_list(cell):
        title, _, detail = item.partition("::")
        out.append({"title": title.strip(), "detail": detail.strip()})
    return out


def _split_tuples(cell: str) -> list[list[str]]:
    """Each '|'-separated item split on every '::' into stripped parts."""
    return [[p.strip() for p in item.split("::")] for item in _split_list(cell)]


def _map_tuple(col: str, parts: list[str]) -> dict:
    g = lambda i: parts[i] if i < len(parts) else ""  # parts already stripped
    if col == "review_examples":
        return {"review": g(0), "reply": g(1)}
    return {"anchor": g(0), "url": g(1)}  # related_pages


def _row_to_page_in(row: dict[str, str]) -> PseoPageIn:
    content: dict[str, Any] = {}
    for col in CONTENT_TEXT_COLS:
        if (row.get(col) or "").strip():
            content[col] = row[col].strip()
    for col in CONTENT_LIST_COLS:
        if (row.get(col) or "").strip():
            content[col] = _split_list(row[col])
    for col in CONTENT_PAIR_COLS:
        if (row.get(col) or "").strip():
            content[col] = _split_pairs(row[col])
    # FAQs read better as q/a.
    if "faqs" in content:
        content["faqs"] = [{"q": f["title"], "a": f["detail"]} for f in content["faqs"]]
    for col in CONTENT_TUPLE_COLS:
        if (row.get(col) or "").strip():
            content[col] = [_map_tuple(col, parts) for parts in _split_tuples(row[col])]

    qs = (row.get("quality_score") or "").strip()
    try:
        quality_score = int(float(qs)) if qs else None
    except ValueError:
        quality_score = None

    return PseoPageIn(
        slug=(row.get("slug") or "").strip() or None,
        country=(row.get("country") or "").strip() or None,
        industry_label=(row.get("industry_label") or "").strip(),
        industry_slug=(row.get("industry_slug") or "").strip() or None,
        city_label=(row.get("city_label") or "").strip(),
        city_slug=(row.get("city_slug") or "").strip() or None,
        meta_title=(row.get("meta_title") or "").strip() or None,
        meta_description=(row.get("meta_description") or "").strip() or None,
        h1=(row.get("h1") or "").strip() or None,
        canonical_url=(row.get("canonical_url") or "").strip() or None,
        index_status=(row.get("index_status") or "").strip().lower() or None,
        quality_score=quality_score,
        content=content,
        status=(row.get("status") or "").strip().lower() or None,
    )


def _read_rows(filename: str, blob: bytes) -> list[dict[str, str]]:
    """Parse CSV or XLSX into a list of {header: cell-string} dicts."""
    if filename.lower().endswith(".xlsx"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise HTTPException(status_code=400, detail="XLSX support not installed on server; upload CSV instead.")
        wb = load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            headers = [str(h or "").strip().lower() for h in next(rows_iter)]
        except StopIteration:
            return []
        return [
            {headers[i]: ("" if v is None else str(v)) for i, v in enumerate(vals) if i < len(headers)}
            for vals in rows_iter
        ]
    text = blob.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return [{(k or "").strip().lower(): (v or "") for k, v in r.items()} for r in reader]


@admin_router.get("/import/columns")
def admin_import_columns(_: User = Depends(superadmin_required)):
    """Column reference the admin UI uses to build the downloadable template."""
    return {
        "columns": ALL_COLS,
        "required": ["industry_label", "city_label"],
        "list_separator": "|",
        "pair_separator": "::",
        "pair_columns": CONTENT_PAIR_COLS,
        "list_columns": CONTENT_LIST_COLS,
        # Multi-field cells: "a :: b [:: c]" per item, items joined by "|".
        "tuple_columns": CONTENT_TUPLE_COLS,
    }


@admin_router.post("/import")
def admin_import_pages(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(superadmin_required),
):
    # Plain `def`, not `async def`: this loop makes thousands of synchronous DB
    # calls with no `await` in sight. As an async route that runs directly on the
    # event loop that serves every concurrent request — including login — freezing
    # the whole app for the import's duration. A sync route makes FastAPI dispatch
    # it to a threadpool instead, keeping the event loop free.
    blob = file.file.read()
    if len(blob) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")
    rows = _read_rows(file.filename or "import.csv", blob)

    results = []
    created = updated = failed = 0
    touched = []

    # Pass 1: parse + apply defaults for every non-blank row up front. Pure Python,
    # no DB — lets us gather all slugs and preload existing rows in ONE query below
    # instead of a per-row SELECT (thousands of round-trips on a remote DB was slow
    # enough to blow past the proxy timeout mid-upload).
    parsed = []  # (idx, PseoPageIn)
    for idx, row in enumerate(rows, start=2):  # 1-based + header row
        if not any((v or "").strip() for v in row.values()):
            continue
        try:
            data = _apply_defaults(_row_to_page_in(row))
            if not data.industry_label or not data.city_label:
                raise ValueError("industry_label and city_label are required")
            if data.status and data.status not in (PseoPageStatus.DRAFT.value, PseoPageStatus.PUBLISHED.value):
                raise ValueError(f"invalid status: {data.status}")
            parsed.append((idx, data))
        except Exception as e:
            failed += 1
            results.append({"row": idx, "slug": (row.get("slug") or "").strip() or None, "action": "error", "error": str(e)})

    # One SELECT for every slug in the file. content is deferred — we overwrite it,
    # so there's no reason to drag the old JSON bodies across the wire.
    slugs = list({d.slug for _, d in parsed})
    existing: dict[str, PseoPage] = {}
    if slugs:
        for p in db.query(PseoPage).options(defer(PseoPage.content)).filter(PseoPage.slug.in_(slugs)).all():
            existing[p.slug] = p

    # Pass 2: upsert from the in-memory map. SAVEPOINT per row still isolates a bad
    # row; the only DB hit inside the loop is the flush (constraint check / PK), so
    # the whole file needs far fewer round-trips than the old select-then-flush.
    for idx, data in parsed:
        try:
            with db.begin_nested():
                page = existing.get(data.slug)
                if page is not None:
                    # Slug is globally unique but country-agnostic ({industry}-in-{city}),
                    # so the same slug can collide across markets. Refuse to silently
                    # repoint a live page to a different country (would 404 the old
                    # locale URL and drop it from Google).
                    if page.country != data.country:
                        raise ValueError(
                            f"slug '{data.slug}' already exists for country '{page.country}' — refusing to overwrite across markets"
                        )
                    was_published = page.status == PseoPageStatus.PUBLISHED.value
                    page.industry_label, page.industry_slug = data.industry_label, data.industry_slug
                    page.city_label, page.city_slug = data.city_label, data.city_slug
                    page.meta_title, page.meta_description, page.h1 = data.meta_title, data.meta_description, data.h1
                    page.canonical_url = data.canonical_url or None
                    page.index_status = data.index_status
                    page.quality_score = data.quality_score
                    page.content = data.content
                    if data.status:
                        if data.status == PseoPageStatus.PUBLISHED.value and page.status != PseoPageStatus.PUBLISHED.value:
                            page.published_at = datetime.now(timezone.utc)
                        page.status = data.status
                    action = "updated"
                    updated += 1
                else:
                    was_published = False
                    # New pages can't import straight to published without a score —
                    # same gate as _set_status. Existing pages are left alone so
                    # re-imports of the current catalog keep working.
                    if (data.status or "") == PseoPageStatus.PUBLISHED.value and data.quality_score is None:
                        raise ValueError("new page needs quality_score to import as published — import as draft, score it, then publish")
                    page = PseoPage(
                        slug=data.slug, country=data.country, industry_label=data.industry_label, industry_slug=data.industry_slug,
                        city_label=data.city_label, city_slug=data.city_slug,
                        meta_title=data.meta_title, meta_description=data.meta_description, h1=data.h1,
                        canonical_url=data.canonical_url or None, index_status=data.index_status, quality_score=data.quality_score,
                        content=data.content, status=data.status or PseoPageStatus.DRAFT.value,
                        published_at=datetime.now(timezone.utc) if data.status == PseoPageStatus.PUBLISHED.value else None,
                    )
                    db.add(page)
                    existing[data.slug] = page  # so a duplicate slug later in the file updates this row
                    action = "created"
                    created += 1
                db.flush()  # assign PK / hit unique-slug constraint now, still inside the savepoint
            # Revalidate any row that IS or WAS published — so a flip to draft/noindex
            # purges the stale live HTML instead of serving an indexable page for 24h.
            if page.status == PseoPageStatus.PUBLISHED.value or was_published:
                touched.append({"slug": page.slug, "country": page.country, "industry_slug": page.industry_slug})
            results.append({"row": idx, "slug": page.slug, "action": action, "status": page.status})
        except Exception as e:
            failed += 1
            results.append({"row": idx, "slug": data.slug, "action": "error", "error": str(e)})

    db.commit()

    # Import was the one mutation path that skipped the backend cache, leaving
    # unpublished/edited pages served from Redis for up to _CACHE_TTL.
    if touched:
        try:
            get_redis().delete(*[_cache_key(t["slug"]) for t in touched])  # one Redis command, not one per page
        except Exception:
            pass
    trigger_bulk_pseo_revalidation(touched)
    return {"created": created, "updated": updated, "failed": failed, "results": results}
