"""Local-SEO programmatic landing pages (industry x city), served under
/{locale}/local-seo-services/. Sibling of app/api/pseo.py — same machinery, a
separate table (lpseo_pages) and a richer, managed-local-SEO content schema.

Three routers:
- public_router  -> /api/v1/public/lpseo   (unauthenticated, Redis-cached, published only)
- admin_router   -> /api/v1/admin/lpseo    (superadmin CRUD + CSV/XLSX bulk import)
- lead_router    -> /api/v1/public/lpseo   (public lead form -> emails superadmins)

Reuses the pure parse helpers from pseo.py (slugify, country, list/pair/tuple splits,
CSV reader) so only the content-column shape and the template differ.
"""
import html as html_mod
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session, defer

from app.db.session import get_db
from app.api.deps import superadmin_required
from app.core.config import settings
from app.core.rate_limit import rate_limiter
from app.core.redis_client import get_redis
from app.models.lpseo_page import LpseoPage, LpseoPageStatus
from app.models.user import User
from app.services import gsc_service
from app.services.email_service import send_email
from app.services.revalidation_service import (
    trigger_bulk_lpseo_revalidation, trigger_lpseo_page_flush,
)
# Pure, page-type-agnostic helpers — reused verbatim from pseo.
from app.api.pseo import (
    _slugify, _country_code, _locale, _split_list, _split_pairs, _split_tuples, _read_rows,
)

logger = logging.getLogger(__name__)

public_router = APIRouter()
admin_router = APIRouter()
lead_router = APIRouter()

_CACHE_TTL = 60 * 60  # matches the frontend's hourly ISR backstop
_QUALITY_GATE = 80
_GSC_PREFIX = "/local-seo-services/"

_lead_rate_limit = rate_limiter("lpseo_lead", limit=8, window_seconds=60)


def _cache_key(slug: str) -> str:
    return f"public_lpseo:{slug}"


def _effective_index_status(p: LpseoPage) -> str:
    if (p.index_status or "index") != "index":
        return "noindex"
    if p.quality_score is not None and p.quality_score < _QUALITY_GATE:
        return "noindex"
    return "index"


def _public_payload(p: LpseoPage) -> dict:
    return {
        "slug": p.slug,
        "country": p.country,
        "locale": _locale(p.country),
        "industry_label": p.industry_label,
        "industry_slug": p.industry_slug,
        "city_label": p.city_label,
        "city_slug": p.city_slug,
        "meta_title": p.meta_title,
        "meta_description": p.meta_description,
        "h1": p.h1,
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
    """Slim list for the sitemap / hub links. Excludes noindex pages."""
    query = (
        db.query(
            LpseoPage.slug, LpseoPage.country, LpseoPage.industry_label, LpseoPage.industry_slug,
            LpseoPage.city_label, LpseoPage.city_slug, LpseoPage.updated_at,
        )
        .filter(
            LpseoPage.status == LpseoPageStatus.PUBLISHED.value,
            LpseoPage.index_status == "index",
            or_(LpseoPage.quality_score.is_(None), LpseoPage.quality_score >= _QUALITY_GATE),
        )
    )
    if industry:
        query = query.filter(LpseoPage.industry_slug == industry)
    if country:
        query = query.filter(LpseoPage.country == _country_code(country))
    rows = query.order_by(LpseoPage.country, LpseoPage.industry_slug, LpseoPage.city_slug).all()
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
        pass

    page = (
        db.query(LpseoPage)
        .filter(LpseoPage.slug == slug, LpseoPage.status == LpseoPageStatus.PUBLISHED.value)
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


# ── Public lead capture ───────────────────────────────────────────────────────

class LpseoLeadIn(BaseModel):
    name: str
    clinic: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    locations: Optional[str] = None
    message: Optional[str] = None
    page: Optional[str] = None  # slug or URL the form was submitted from, for context

    @field_validator("name")
    @classmethod
    def _name_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Name is required")
        return v[:120]

    @field_validator("clinic", "phone", "email", "website", "locations", "message", "page")
    @classmethod
    def _trim(cls, v):
        if v is None:
            return v
        return str(v).strip()[:2000] or None


@lead_router.post("/leads", status_code=201, dependencies=[Depends(_lead_rate_limit)])
def create_lead(payload: LpseoLeadIn):
    """Public local-SEO lead form. Email-only (no DB row): notifies the platform
    super-admins via Resend. Never blocks — a missing key just logs and returns ok."""
    recipients = sorted(settings.superadmin_email_set)
    if recipients:
        esc = lambda s: html_mod.escape(s) if s else "-"  # lead input goes into email HTML
        html = f"""
        <h2>New Local SEO lead</h2>
        <p><strong>Name:</strong> {esc(payload.name)}</p>
        <p><strong>Clinic / business:</strong> {esc(payload.clinic)}</p>
        <p><strong>Phone / WhatsApp:</strong> {esc(payload.phone)}</p>
        <p><strong>Email:</strong> {esc(payload.email)}</p>
        <p><strong>Website / Maps link:</strong> {esc(payload.website)}</p>
        <p><strong>Locations:</strong> {esc(payload.locations)}</p>
        <p><strong>Message:</strong><br>{esc(payload.message)}</p>
        <p style="color:#888"><strong>Submitted from:</strong> {esc(payload.page)}</p>
        """
        try:
            send_email(recipients, "New Local SEO lead — Pinzo", html)
        except Exception as e:
            logger.warning("lpSEO lead email failed: %s", e)
    else:
        logger.warning("lpSEO lead received but SUPERADMIN_EMAILS is empty — not emailed.")
    return {"ok": True}


# ── Admin ─────────────────────────────────────────────────────────────────────

class LpseoPageIn(BaseModel):
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
    status: Optional[str] = None


def _apply_defaults(data: LpseoPageIn) -> LpseoPageIn:
    data.country = _country_code(data.country)
    data.industry_slug = data.industry_slug or _slugify(data.industry_label)
    data.city_slug = data.city_slug or _slugify(data.city_label)
    data.slug = data.slug or f"{data.industry_slug}-in-{data.city_slug}"
    data.h1 = data.h1 or f"Local SEO Services for {data.industry_label} in {data.city_label}"
    data.meta_title = data.meta_title or f"Local SEO Services for {data.industry_label} in {data.city_label} | Pinzo"
    data.meta_description = data.meta_description or (
        f"Grow {data.industry_label.lower()} visibility across Google Maps, local search and AI "
        f"recommendations with managed local SEO services from Pinzo in {data.city_label}. Free audit."
    )
    data.index_status = "noindex" if (data.index_status or "").strip().lower() == "noindex" else "index"
    return data


def _invalidate(slug: str, country: str, industry_slug: str) -> None:
    try:
        get_redis().delete(_cache_key(slug))
    except Exception:
        pass
    trigger_bulk_lpseo_revalidation([{"slug": slug, "country": country, "industry_slug": industry_slug}])


def _admin_row(p: LpseoPage) -> dict:
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
def admin_stats(db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    total = db.query(LpseoPage).count()
    published = db.query(LpseoPage).filter(LpseoPage.status == LpseoPageStatus.PUBLISHED.value).count()
    noindex = db.query(LpseoPage).filter(LpseoPage.index_status == "noindex").count()
    return {"total": total, "published": published, "draft": total - published, "noindex": noindex}


@admin_router.get("/gsc-metrics")
def admin_gsc_metrics(days: int = 28, _: User = Depends(superadmin_required)):
    if not gsc_service.is_configured():
        return {"configured": False, "metrics": {}}
    raw = gsc_service.fetch_page_metrics(_GSC_PREFIX, days=days)
    by_slug = {url.rstrip("/").rsplit("/", 1)[-1]: m for url, m in raw.items()}
    return {"configured": True, "metrics": by_slug}


@admin_router.get("/{page_id:int}/gsc-queries")
def admin_gsc_queries(page_id: int, days: int = 28, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    page = db.query(LpseoPage).get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if not gsc_service.is_configured():
        return {"configured": False, "queries": []}
    url = f"{settings.FRONTEND_URL.rstrip('/')}/{_locale(page.country)}/local-seo-services/{page.slug}"
    return {"configured": True, "queries": gsc_service.fetch_top_queries(url, days=days)}


def _filtered_query(db: Session, q: Optional[str], status: Optional[str]):
    query = db.query(LpseoPage)
    if status in (LpseoPageStatus.DRAFT.value, LpseoPageStatus.PUBLISHED.value):
        query = query.filter(LpseoPage.status == status)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            (LpseoPage.slug.ilike(like))
            | (LpseoPage.industry_label.ilike(like))
            | (LpseoPage.city_label.ilike(like))
        )
    return query


@admin_router.get("")
def admin_list_pages(
    q: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: Optional[str] = None,
    sort_dir: str = "desc",
    gsc_days: int = 28,
    db: Session = Depends(get_db),
    _: User = Depends(superadmin_required),
):
    # Admin rows never render the fat `content` JSON — defer it so neither the
    # paginated list nor the sort-everything path drags every page's body out of
    # Supabase (egress + memory) just to build slim rows.
    query = _filtered_query(db, q, status).options(defer(LpseoPage.content))
    total = query.count()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    if sort_by in ("clicks", "impressions"):
        raw = gsc_service.fetch_page_metrics(_GSC_PREFIX, days=gsc_days)
        by_slug = {url.rstrip("/").rsplit("/", 1)[-1]: m for url, m in raw.items()}
        all_rows = query.all()
        all_rows.sort(key=lambda p: by_slug.get(p.slug, {}).get(sort_by, 0), reverse=(sort_dir != "asc"))
        rows = all_rows[(page - 1) * page_size: page * page_size]
    else:
        rows = query.order_by(LpseoPage.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

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
    ids = [row.id for row in _filtered_query(db, q, status).with_entities(LpseoPage.id).order_by(LpseoPage.id).all()]
    return {"ids": ids}


class BulkStatusIn(BaseModel):
    ids: list[int] = Field(default_factory=list)
    select_all: bool = False
    q: Optional[str] = None
    filter_status: Optional[str] = None
    status: Optional[str] = None
    index_status: Optional[str] = None


@admin_router.post("/bulk-status")
def admin_bulk_status(body: BulkStatusIn, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    if body.status is not None and body.status not in (LpseoPageStatus.DRAFT.value, LpseoPageStatus.PUBLISHED.value):
        raise HTTPException(status_code=400, detail=f"invalid status: {body.status}")
    if body.index_status is not None and body.index_status not in ("index", "noindex"):
        raise HTTPException(status_code=400, detail=f"invalid index_status: {body.index_status}")
    if body.status is None and body.index_status is None:
        return {"updated": 0}
    # The admin UI batches 'select all matching' into small explicit-id calls (see
    # /ids), so this handler now sees at most a page-sized batch. select_all stays
    # as an API-only fallback, still capped, with content deferred (never read here).
    if body.select_all:
        pages = _filtered_query(db, body.q, body.filter_status).options(defer(LpseoPage.content)).limit(5000).all()  # ponytail: hard cap, raise if a real run ever needs more
    else:
        if not body.ids:
            return {"updated": 0}
        pages = db.query(LpseoPage).options(defer(LpseoPage.content)).filter(LpseoPage.id.in_(body.ids)).all()
    touched = []
    skipped_unscored = 0
    for page in pages:
        if body.status == LpseoPageStatus.PUBLISHED.value and page.quality_score is None:
            skipped_unscored += 1  # same publish gate as _set_status
            continue
        if body.status is not None:
            page.status = body.status
            if body.status == LpseoPageStatus.PUBLISHED.value:
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
    trigger_bulk_lpseo_revalidation(touched)
    return {"updated": len(pages) - skipped_unscored, "skipped_unscored": skipped_unscored}


@admin_router.get("/{page_id:int}")
def admin_get_page(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    page = db.query(LpseoPage).get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return {**_admin_row(page), "meta_description": page.meta_description, "h1": page.h1,
            "canonical_url": page.canonical_url, "industry_slug": page.industry_slug,
            "city_slug": page.city_slug, "content": page.content or {}}


@admin_router.post("")
def admin_create_page(body: LpseoPageIn, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    body = _apply_defaults(body)
    if db.query(LpseoPage).filter(LpseoPage.slug == body.slug).first():
        raise HTTPException(status_code=409, detail=f"Slug already exists: {body.slug}")
    page = LpseoPage(
        slug=body.slug, country=body.country, industry_label=body.industry_label, industry_slug=body.industry_slug,
        city_label=body.city_label, city_slug=body.city_slug,
        meta_title=body.meta_title, meta_description=body.meta_description, h1=body.h1,
        canonical_url=body.canonical_url or None, index_status=body.index_status, quality_score=body.quality_score,
        content=body.content, status=body.status or LpseoPageStatus.DRAFT.value,
        published_at=datetime.now(timezone.utc) if body.status == LpseoPageStatus.PUBLISHED.value else None,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    if page.status == LpseoPageStatus.PUBLISHED.value:
        _invalidate(page.slug, page.country, page.industry_slug)
    return _admin_row(page)


@admin_router.patch("/{page_id}")
def admin_update_page(page_id: int, body: LpseoPageIn, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    page = db.query(LpseoPage).get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    body = _apply_defaults(body)
    if body.slug != page.slug and db.query(LpseoPage).filter(LpseoPage.slug == body.slug).first():
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
    if body.status in (LpseoPageStatus.DRAFT.value, LpseoPageStatus.PUBLISHED.value):
        if body.status == LpseoPageStatus.PUBLISHED.value and page.status != LpseoPageStatus.PUBLISHED.value:
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
    trigger_bulk_lpseo_revalidation(entries)
    return _admin_row(page)


@admin_router.post("/{page_id}/publish")
def admin_publish_page(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    return _set_status(page_id, LpseoPageStatus.PUBLISHED.value, db)


@admin_router.post("/{page_id}/unpublish")
def admin_unpublish_page(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    return _set_status(page_id, LpseoPageStatus.DRAFT.value, db)


def _set_status(page_id: int, new_status: str, db: Session) -> dict:
    page = db.query(LpseoPage).get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    # Same publish gate as pSEO: null quality_score bypasses the >=80 index gate.
    if new_status == LpseoPageStatus.PUBLISHED.value and page.quality_score is None:
        raise HTTPException(status_code=422, detail="quality_score is required before publishing (>=80 to be indexable)")
    page.status = new_status
    if new_status == LpseoPageStatus.PUBLISHED.value:
        page.published_at = datetime.now(timezone.utc)
    db.commit()
    _invalidate(page.slug, page.country, page.industry_slug)
    return _admin_row(page)


@admin_router.post("/{page_id:int}/flush-cache")
def admin_flush_page_cache(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    page = db.query(LpseoPage).get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    try:
        get_redis().delete(_cache_key(page.slug))
    except Exception:
        pass
    trigger_lpseo_page_flush(page.slug, page.country)
    return {"flushed": True, "slug": page.slug, "path": f"/{_locale(page.country)}/local-seo-services/{page.slug}"}


@admin_router.delete("/{page_id}")
def admin_delete_page(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    page = db.query(LpseoPage).get(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    slug, country, industry = page.slug, page.country, page.industry_slug
    db.delete(page)
    db.commit()
    _invalidate(slug, country, industry)
    return {"deleted": True}


# ── Bulk import (CSV / XLSX) ─────────────────────────────────────────────────
#
# One row per page. List cells are `|`-separated; two-part items use `A :: B`.
# Tuple cells split on every `::`; a few sub-fields hold a `;`-separated list
# (workflow steps, plan features).

IDENTITY_COLS = ["slug", "country", "industry_label", "industry_slug", "city_label", "city_slug",
                 "meta_title", "meta_description", "h1", "canonical_url", "index_status",
                 "quality_score", "status"]
CONTENT_TEXT_COLS = [
    "badge", "hero_sub", "primary_cta", "secondary_cta",
    "answer_heading", "answer_block", "strategy_heading", "strategy_body",
    "maps_body", "city_body", "audit_summary_title", "audit_summary_body",
    "lead_heading", "lead_sub", "final_heading", "final_sub", "final_button",
    "gbp_url", "primary_keyword", "region", "last_updated", "page_type", "template_version",
]
CONTENT_LIST_COLS = [
    "strategy_points", "topics", "maps_signals", "neighborhoods", "city_requirements",
    "single_points", "multi_points", "secondary_keywords",
]
# {"title","detail"}
CONTENT_PAIR_COLS = ["value_props", "proof_points", "deliverables"]
# {"q","a"}
CONTENT_QA_COLS = ["faqs", "answer_units"]
# Typed dicts, see _map_tuple.
CONTENT_TUPLE_COLS = [
    "search_intents", "services", "comparison", "workflow_phases",
    "audit_bars", "plans", "related_pages", "internal_links",
]
IGNORED_COLS = ["url", "schema_type"]
ALL_COLS = (IDENTITY_COLS + CONTENT_TEXT_COLS + CONTENT_LIST_COLS + CONTENT_PAIR_COLS
            + CONTENT_QA_COLS + CONTENT_TUPLE_COLS + IGNORED_COLS)


def _subsplit(cell: str) -> list[str]:
    """`;`-separated sub-list inside one tuple field (workflow steps, plan features)."""
    return [s.strip() for s in (cell or "").split(";") if s.strip()]


def _map_tuple(col: str, parts: list[str]) -> dict:
    g = lambda i: parts[i] if i < len(parts) else ""
    if col == "search_intents":
        return {"title": g(0), "detail": g(1), "example": g(2)}
    if col == "services":
        return {"channel": g(0), "work": g(1), "outcome": g(2)}
    if col == "comparison":
        return {"point": g(0), "agency": g(1), "software": g(2), "pinzo": g(3)}
    if col == "workflow_phases":
        return {"days": g(0), "title": g(1), "steps": _subsplit(g(2))}
    if col == "audit_bars":
        try:
            pct = max(0, min(100, int(float(g(1)))))
        except ValueError:
            pct = 0
        return {"label": g(0), "percent": pct}
    if col == "plans":
        return {"tag": g(0), "name": g(1), "desc": g(2), "features": _subsplit(g(3)),
                "cta_label": g(4), "cta_href": g(5), "featured": g(6).strip().lower() in ("1", "true", "yes")}
    if col == "internal_links":
        return {"anchor": g(0), "url": g(1), "section": g(2)}
    return {"anchor": g(0), "url": g(1)}  # related_pages


def _row_to_page_in(row: dict[str, str]) -> LpseoPageIn:
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
    for col in CONTENT_QA_COLS:
        if (row.get(col) or "").strip():
            content[col] = [{"q": p["title"], "a": p["detail"]} for p in _split_pairs(row[col])]
    for col in CONTENT_TUPLE_COLS:
        if (row.get(col) or "").strip():
            content[col] = [_map_tuple(col, parts) for parts in _split_tuples(row[col])]

    qs = (row.get("quality_score") or "").strip()
    try:
        quality_score = int(float(qs)) if qs else None
    except ValueError:
        quality_score = None

    return LpseoPageIn(
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


@admin_router.get("/import/columns")
def admin_import_columns(_: User = Depends(superadmin_required)):
    return {
        "columns": ALL_COLS,
        "required": ["industry_label", "city_label"],
        "list_separator": "|",
        "pair_separator": "::",
        "subfield_separator": ";",
        "pair_columns": CONTENT_PAIR_COLS + CONTENT_QA_COLS,
        "list_columns": CONTENT_LIST_COLS,
        "tuple_columns": CONTENT_TUPLE_COLS,
    }


@admin_router.post("/import")
def admin_import_pages(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(superadmin_required),
):
    # Sync `def` on purpose (see pseo import) — FastAPI runs it in a threadpool so
    # the thousands of blocking DB calls never freeze the event loop.
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
    parsed = []  # (idx, LpseoPageIn)
    for idx, row in enumerate(rows, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        try:
            data = _apply_defaults(_row_to_page_in(row))
            if not data.industry_label or not data.city_label:
                raise ValueError("industry_label and city_label are required")
            if data.status and data.status not in (LpseoPageStatus.DRAFT.value, LpseoPageStatus.PUBLISHED.value):
                raise ValueError(f"invalid status: {data.status}")
            parsed.append((idx, data))
        except Exception as e:
            failed += 1
            results.append({"row": idx, "slug": (row.get("slug") or "").strip() or None, "action": "error", "error": str(e)})

    # One SELECT for every slug in the file. content is deferred — we overwrite it,
    # so there's no reason to drag the old JSON bodies across the wire.
    slugs = list({d.slug for _, d in parsed})
    existing: dict[str, LpseoPage] = {}
    if slugs:
        for p in db.query(LpseoPage).options(defer(LpseoPage.content)).filter(LpseoPage.slug.in_(slugs)).all():
            existing[p.slug] = p

    # Pass 2: upsert from the in-memory map. Savepoint per row still isolates a bad
    # row; the only DB hit inside the loop is the flush (constraint check / PK).
    for idx, data in parsed:
        try:
            with db.begin_nested():
                page = existing.get(data.slug)
                if page is not None:
                    # Slug is globally unique but country-agnostic ({industry}-in-{city}),
                    # so the same slug can legitimately collide across markets. Refuse to
                    # silently repoint a live page to a different country (would 404 the
                    # old locale URL and drop it from Google).
                    if page.country != data.country:
                        raise ValueError(
                            f"slug '{data.slug}' already exists for country '{page.country}' — refusing to overwrite across markets"
                        )
                    was_published = page.status == LpseoPageStatus.PUBLISHED.value
                    page.industry_label, page.industry_slug = data.industry_label, data.industry_slug
                    page.city_label, page.city_slug = data.city_label, data.city_slug
                    page.meta_title, page.meta_description, page.h1 = data.meta_title, data.meta_description, data.h1
                    page.canonical_url = data.canonical_url or None
                    page.index_status = data.index_status
                    page.quality_score = data.quality_score
                    page.content = data.content
                    if data.status:
                        if data.status == LpseoPageStatus.PUBLISHED.value and page.status != LpseoPageStatus.PUBLISHED.value:
                            page.published_at = datetime.now(timezone.utc)
                        page.status = data.status
                    action = "updated"
                    updated += 1
                else:
                    was_published = False
                    # New pages can't import straight to published without a score (same
                    # gate as _set_status); existing pages are left alone.
                    if (data.status or "") == LpseoPageStatus.PUBLISHED.value and data.quality_score is None:
                        raise ValueError("new page needs quality_score to import as published — import as draft, score it, then publish")
                    page = LpseoPage(
                        slug=data.slug, country=data.country, industry_label=data.industry_label, industry_slug=data.industry_slug,
                        city_label=data.city_label, city_slug=data.city_slug,
                        meta_title=data.meta_title, meta_description=data.meta_description, h1=data.h1,
                        canonical_url=data.canonical_url or None, index_status=data.index_status, quality_score=data.quality_score,
                        content=data.content, status=data.status or LpseoPageStatus.DRAFT.value,
                        published_at=datetime.now(timezone.utc) if data.status == LpseoPageStatus.PUBLISHED.value else None,
                    )
                    db.add(page)
                    existing[data.slug] = page  # so a duplicate slug later in the file updates this row
                    action = "created"
                    created += 1
                db.flush()
            # Revalidate any row that IS or WAS published — so a flip to draft/noindex
            # purges the stale live HTML instead of serving an indexable page for 24h.
            if page.status == LpseoPageStatus.PUBLISHED.value or was_published:
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
    trigger_bulk_lpseo_revalidation(touched)
    return {"created": created, "updated": updated, "failed": failed, "results": results}
