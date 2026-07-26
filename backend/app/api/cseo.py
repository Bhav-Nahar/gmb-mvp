"""Country pillar pages for the Local SEO universe, served at
/{locale}/local-seo-services/. Third sibling of pseo.py and lpseo.py: same
machinery, its own table (cseo_pages) and its own content schema.

Two routers:
- public_router -> /api/v1/public/cseo   (unauthenticated, Redis-cached, published only)
- admin_router  -> /api/v1/admin/cseo    (superadmin CRUD + CSV/XLSX import)

Lead capture is NOT duplicated here: the pillar's audit form posts to the existing
/public/lpseo/leads endpoint, which already stores the lead before emailing and
surfaces it in the admin Leads tab. The package CSV ships a formsubmit.co
destination, which guardrail 12 rules out (it must be an endpoint that stores).
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, defer

from app.db.session import get_db
from app.api.deps import superadmin_required
from app.core.config import settings
from app.core.redis_client import get_redis
from app.models.cseo_page import CseoPage, CseoPageStatus
from app.models.user import User
from app.services import gsc_service
from app.services.revalidation_service import trigger_cseo_revalidation
# Pure, page-type-agnostic helpers, reused verbatim from pseo.
from app.api.pseo import _country_code, _locale, _split_list, _read_rows

logger = logging.getLogger(__name__)

public_router = APIRouter()
admin_router = APIRouter()

_CACHE_TTL = 60 * 60
_QUALITY_GATE = 80

# The global pillar is the same page family with a wider scope: one row, country
# "global", served locale-free at the bare /local-seo-services.
GLOBAL = "global"


def _code(raw: str) -> str:
    """_country_code() coerces anything it does not recognise to "in", so "global"
    has to be resolved before it is asked. Without this the global pillar would
    silently overwrite the India country pillar on import."""
    return GLOBAL if (raw or "").strip().lower() == GLOBAL else _country_code(raw)


def _loc(country: str) -> str:
    """The global pillar has no market locale; it is the x-default page."""
    return "en" if country == GLOBAL else _locale(country)


def _path(country: str) -> str:
    return "/local-seo-services/" if country == GLOBAL else f"/{_loc(country)}/local-seo-services/"


def _cache_key(country: str) -> str:
    return f"public_cseo:{country}"


def _effective_index_status(p: CseoPage) -> str:
    if (p.index_status or "noindex") != "index":
        return "noindex"
    if p.quality_score is not None and p.quality_score < _QUALITY_GATE:
        return "noindex"
    return "index"


def _public_payload(p: CseoPage) -> dict:
    return {
        "country": p.country,
        "country_label": p.country_label,
        "locale": _loc(p.country),
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

@public_router.get("/{country}")
def get_published_pillar(country: str, db: Session = Depends(get_db)):
    cc = _code(country)
    r = get_redis()
    try:
        cached = r.get(_cache_key(cc))
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    page = (db.query(CseoPage)
            .filter(CseoPage.country == cc, CseoPage.status == CseoPageStatus.PUBLISHED.value)
            .first())
    if not page:
        raise HTTPException(status_code=404, detail="Country pillar not found")

    payload = _public_payload(page)
    try:
        r.setex(_cache_key(cc), _CACHE_TTL, json.dumps(payload))
    except Exception:
        pass
    return payload


# ── Admin ─────────────────────────────────────────────────────────────────────

class CseoPageIn(BaseModel):
    country: str
    country_label: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    h1: Optional[str] = None
    canonical_url: Optional[str] = None
    index_status: Optional[str] = None
    quality_score: Optional[int] = None
    content: dict[str, Any] = Field(default_factory=dict)
    status: Optional[str] = None


SITE_URL = "https://www.pinzo.io"


def _apply_defaults(data: CseoPageIn) -> CseoPageIn:
    data.country = _code(data.country)
    is_global = data.country == GLOBAL
    # "GLOBAL" reads as shouting in a breadcrumb and an H1, and the CSV ships the
    # country cell lowercase, so the global row gets its label spelled properly.
    label = data.country_label or data.country.upper()
    if is_global:
        label = "Global" if label.lower() == GLOBAL else label
    data.country_label = label
    scope = "" if is_global else f" in {label}"
    data.h1 = data.h1 or f"Local SEO Services{scope}"
    data.meta_title = data.meta_title or f"Local SEO Services{scope} | Pinzo"
    data.meta_description = data.meta_description or (
        f"Grow your Google Maps and local search visibility with Pinzo's Local SEO "
        f"services{scope}. Built for single-location businesses and multi-location brands."
    )
    data.canonical_url = data.canonical_url or f"{SITE_URL}{_path(data.country)}"
    # A pillar defaults to noindex: guardrail 3 keeps it out of the index until the
    # launch checklist passes, the opposite default to a leaf page.
    data.index_status = "index" if (data.index_status or "").strip().lower() == "index" else "noindex"
    return data


def _admin_row(p: CseoPage) -> dict:
    return {
        "id": p.id, "country": p.country, "country_label": p.country_label,
        "locale": _loc(p.country), "status": p.status,
        "index_status": p.index_status or "noindex", "quality_score": p.quality_score,
        "meta_title": p.meta_title,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _invalidate(country: str) -> None:
    try:
        get_redis().delete(_cache_key(country))
    except Exception:
        pass
    trigger_cseo_revalidation(country)


_GSC_PREFIX = "/local-seo-services/"


def _page_url(p: CseoPage) -> str:
    """The pillar's live URL, used to join Search Console rows back to the row."""
    return f"{settings.FRONTEND_URL.rstrip('/')}{_path(p.country)}"


@admin_router.get("/gsc-metrics")
def admin_gsc_metrics(days: int = 28, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    """Clicks/impressions per pillar. The prefix also matches every leaf under
    /local-seo-services/, so match the exact country URL rather than a suffix:
    the pillar IS the directory root, and a suffix match would scoop up leaves."""
    if not gsc_service.is_configured():
        return {"configured": False, "metrics": {}}
    raw = gsc_service.fetch_page_metrics(_GSC_PREFIX, days=days)
    norm = {url.rstrip("/"): m for url, m in raw.items()}
    rows = db.query(CseoPage).options(defer(CseoPage.content)).all()
    return {"configured": True,
            "metrics": {p.country: norm[_page_url(p).rstrip("/")]
                        for p in rows if _page_url(p).rstrip("/") in norm}}


@admin_router.get("/{page_id:int}/gsc-queries")
def admin_gsc_queries(page_id: int, days: int = 28, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    p = db.query(CseoPage).get(page_id)
    if not p:
        raise HTTPException(status_code=404, detail="Page not found")
    if not gsc_service.is_configured():
        return {"configured": False, "queries": []}
    return {"configured": True, "queries": gsc_service.fetch_top_queries(_page_url(p), days=days)}


class IndexStatusIn(BaseModel):
    index_status: str


@admin_router.post("/{page_id:int}/index-status")
def admin_set_index_status(page_id: int, body: IndexStatusIn, db: Session = Depends(get_db),
                           _: User = Depends(superadmin_required)):
    """Flip robots without a re-import. This is the final step of the launch
    checklist (guardrail 16), so it needs to be one deliberate click."""
    if body.index_status not in ("index", "noindex"):
        raise HTTPException(status_code=400, detail=f"invalid index_status: {body.index_status}")
    p = db.query(CseoPage).get(page_id)
    if not p:
        raise HTTPException(status_code=404, detail="Page not found")
    if body.index_status == "index" and (p.quality_score is None or p.quality_score < _QUALITY_GATE):
        raise HTTPException(status_code=422,
                            detail=f"quality_score must be >= {_QUALITY_GATE} before this pillar can be indexed")
    p.index_status = body.index_status
    db.commit()
    _invalidate(p.country)
    return _admin_row(p)


@admin_router.post("/{page_id:int}/flush-cache")
def admin_flush_cache(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    p = db.query(CseoPage).get(page_id)
    if not p:
        raise HTTPException(status_code=404, detail="Page not found")
    _invalidate(p.country)
    return {"flushed": True, "country": p.country, "path": _path(p.country)}


@admin_router.get("")
def admin_list(db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    rows = (db.query(CseoPage).options(defer(CseoPage.content))
            .order_by(CseoPage.country).all())
    return {"pages": [_admin_row(p) for p in rows], "total": len(rows)}


@admin_router.get("/{page_id:int}")
def admin_get(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    p = db.query(CseoPage).get(page_id)
    if not p:
        raise HTTPException(status_code=404, detail="Page not found")
    return {**_admin_row(p), "meta_description": p.meta_description, "h1": p.h1,
            "canonical_url": p.canonical_url, "content": p.content or {}}


@admin_router.patch("/{page_id:int}")
def admin_update(page_id: int, body: CseoPageIn, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    p = db.query(CseoPage).get(page_id)
    if not p:
        raise HTTPException(status_code=404, detail="Page not found")
    body = _apply_defaults(body)
    if body.country != p.country and db.query(CseoPage).filter(CseoPage.country == body.country).first():
        raise HTTPException(status_code=409, detail=f"A pillar already exists for {body.country}")
    old_country = p.country
    p.country, p.country_label = body.country, body.country_label
    p.meta_title, p.meta_description, p.h1 = body.meta_title, body.meta_description, body.h1
    p.canonical_url = body.canonical_url or None
    p.index_status, p.quality_score, p.content = body.index_status, body.quality_score, body.content
    if body.status in (CseoPageStatus.DRAFT.value, CseoPageStatus.PUBLISHED.value):
        if body.status == CseoPageStatus.PUBLISHED.value and p.status != CseoPageStatus.PUBLISHED.value:
            p.published_at = datetime.now(timezone.utc)
        p.status = body.status
    db.commit()
    _invalidate(old_country)
    if p.country != old_country:
        _invalidate(p.country)
    return _admin_row(p)


def _set_status(page_id: int, new_status: str, db: Session) -> dict:
    p = db.query(CseoPage).get(page_id)
    if not p:
        raise HTTPException(status_code=404, detail="Page not found")
    # Same publish gate as the leaf pages: an unscored pillar cannot go live.
    if new_status == CseoPageStatus.PUBLISHED.value and p.quality_score is None:
        raise HTTPException(status_code=422, detail="quality_score is required before publishing (>=80 to be indexable)")
    p.status = new_status
    if new_status == CseoPageStatus.PUBLISHED.value:
        p.published_at = datetime.now(timezone.utc)
    db.commit()
    _invalidate(p.country)
    return _admin_row(p)


@admin_router.post("/{page_id:int}/publish")
def admin_publish(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    return _set_status(page_id, CseoPageStatus.PUBLISHED.value, db)


@admin_router.post("/{page_id:int}/unpublish")
def admin_unpublish(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    return _set_status(page_id, CseoPageStatus.DRAFT.value, db)


@admin_router.delete("/{page_id:int}")
def admin_delete(page_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    p = db.query(CseoPage).get(page_id)
    if not p:
        raise HTTPException(status_code=404, detail="Page not found")
    country = p.country
    db.delete(p)
    db.commit()
    _invalidate(country)
    return {"deleted": True}


# ── Bulk import (CSV / XLSX) ─────────────────────────────────────────────────
#
# Guardrail 14 separators: "||" between FAQ items, "|" between list items,
# "::" between a label and its value. The FAQ separator differs from the leaf
# packages because answers are long prose where a lone "|" is easy to type.

IDENTITY_COLS = ["country", "country_code", "meta_title", "meta_description", "h1",
                 "canonical_url", "robots_status", "quality_score", "status"]
CONTENT_TEXT_COLS = [
    "page_id", "page_type", "template_version", "locale", "slug", "url", "parent_url",
    "primary_keyword", "badge", "hero_copy", "primary_cta", "secondary_cta",
    "direct_question", "direct_answer", "package_copy", "package_note",
    "proof_asset_url", "form_destination", "last_updated", "source_keyword_file",
]
CONTENT_LIST_COLS = [
    "secondary_keywords", "single_location_points", "multi_location_points",
    "monthly_deliverables", "schema_types", "launch_blockers", "proof_asset_type",
]
# {"title","detail"}
CONTENT_PAIR_COLS = [
    "search_behaviour", "ranking_factors", "ai_entity_plan", "safeguards",
    "roadmap_90_days", "proof_assets", "audit_checklist",
]
# {"anchor","url"}
CONTENT_LINK_COLS = ["city_hubs", "industry_hubs", "internal_links"]
# Multi-part rows, see _map_tuple.
CONTENT_TUPLE_COLS = ["service_matrix", "buyer_checklist", "packages"]
CONTENT_QA_COLS = ["faqs"]

# ── Global pillar columns ────────────────────────────────────────────────────
#
# The global package (LSEO-GLOBAL-001) is the same page family with a wider scope,
# so it shares this table and this importer, but its sections are its own and its
# CSV names them differently. Every column below is additive: a country CSV simply
# has no cell for them, and the "is the cell non-empty" guard in _row_to_page_in
# skips them, so country imports behave exactly as before.
#
# Columns whose copy the reference HTML carried but the shipped CSV had no home for
# were recovered into the enriched package CSV; the groups below are what reads them.
CONTENT_TEXT_COLS += [
    "region", "hero_sub", "answer_block", "answer_note", "why_matters_body",
    "reviews_body", "example_review", "example_reply", "city_visibility_body",
    "proof_note", "audit_note", "final_heading", "final_sub", "final_button",
]
CONTENT_LIST_COLS += [
    "hero_trust", "why_matters_points", "gbp_categories", "gbp_services",
    "gbp_attributes", "review_themes", "post_ideas", "photo_checklist",
    "neighborhoods", "single_points", "multi_points", "ai_signals", "audit_points",
]
CONTENT_PAIR_COLS += [
    "problems", "solutions", "monthly_workflow", "review_examples",
    "why_pillars", "ai_surfaces", "ai_approach",
]
CONTENT_LINK_COLS += ["answer_links", "policy_links", "related_pages"]
CONTENT_TUPLE_COLS += [
    "journey_stages", "service_workstreams", "business_models", "roadmap_phases",
    "deliverables_table", "proof_cases", "engagement_models", "market_pathways",
    "related_cards",
]
# One "label::value" cell rather than a list of them: {"title","detail"}.
CONTENT_SOLO_PAIR_COLS = ["cost_drivers", "policy"]
# "eyebrow::heading::intro" -> the approved header of one section. The heading and
# the eyebrow are approved copy too, so they are imported rather than hardcoded.
CONTENT_SECTION_COLS = [
    "sec_answer", "sec_why", "sec_services", "sec_ai", "sec_models", "sec_process",
    "sec_deliverables", "sec_proof", "sec_pricing", "sec_comparison", "sec_markets",
    "sec_faq", "sec_audit", "sec_related",
]

ALL_COLS = (IDENTITY_COLS + CONTENT_TEXT_COLS + CONTENT_LIST_COLS + CONTENT_PAIR_COLS
            + CONTENT_LINK_COLS + CONTENT_TUPLE_COLS + CONTENT_SOLO_PAIR_COLS
            + CONTENT_SECTION_COLS + CONTENT_QA_COLS)


def _split_pairs(cell: str) -> list[dict]:
    out = []
    for item in _split_list(cell):
        title, _, detail = item.partition("::")
        out.append({"title": title.strip(), "detail": detail.strip()})
    return out


def _split_links(cell: str) -> list[dict]:
    """"anchor::url" or "anchor::url::detail". The country package's city and
    industry cards carry a one-line descriptor in the reference HTML, so the third
    part is optional and empty for the plain link lists (internal_links,
    answer_links, policy_links). Splitting on every "::" rather than partitioning
    matters: a partition would leave "::detail" glued onto the href."""
    out = []
    for item in _split_list(cell):
        parts = [p.strip() for p in item.split("::")]
        anchor, url, detail = (parts + ["", ""])[:3]
        out.append({"anchor": anchor, "url": url, "detail": detail})
    return out


def _split_faqs(cell: str) -> list[dict]:
    """FAQ items are separated by "||" (guardrail 14), not the single pipe used by
    every other list, because an answer is long prose."""
    out = []
    for item in [s.strip() for s in (cell or "").split("||") if s.strip()]:
        q, _, a = item.partition("::")
        out.append({"q": q.strip(), "a": a.strip()})
    return out


def _sub(cell: str) -> list[str]:
    """";" separates the items of a sub-list nested inside one "::" part."""
    return [s.strip() for s in (cell or "").split(";") if s.strip()]


def _map_tuple(col: str, parts: list[str]) -> dict:
    g = lambda i: parts[i].strip() if i < len(parts) else ""
    if col == "service_matrix":
        # Guardrail 6: every row states what Pinzo manages AND why it matters here.
        return {"area": g(0), "work": g(1), "why": g(2)}
    if col == "buyer_checklist":
        return {"ask": g(0), "good": g(1), "warning": g(2)}
    # ── Global pillar shapes ──
    if col == "journey_stages":
        return {"stage": g(0), "label": g(1), "detail": g(2)}
    if col == "service_workstreams":
        return {"code": g(0), "title": g(1), "points": _sub(g(2))}
    if col in ("business_models", "roadmap_phases"):
        return {"title": g(0), "detail": g(1), "points": _sub(g(2))}
    if col == "deliverables_table":
        # The reference HTML table has four columns; a three-part row would drop
        # "decision" and leave the table ragged.
        return {"workstream": g(0), "output": g(1), "decision": g(2), "measure": g(3)}
    if col == "proof_cases":
        return {"region": g(0), "name": g(1), "detail": g(2), "focus": g(3), "url": g(4)}
    if col in ("engagement_models", "packages"):
        # The country pillar's pricing cards are the same card as the global
        # pillar's engagement models: a tag, a lead-in, features and a CTA. A
        # three-part row dropped the tag and the CTA the reference HTML carries.
        return {"tag": g(0), "name": g(1), "detail": g(2), "features": _sub(g(3)),
                "cta_label": g(4), "cta_url": g(5)}
    if col == "market_pathways":
        # "status" decides link vs plain text: guardrail 13 forbids a crawlable
        # link to a country pillar that is not published yet.
        return {"country": g(0), "detail": g(1), "status": g(2), "url": g(3)}
    if col == "related_cards":
        return {"anchor": g(0), "url": g(1), "detail": g(2)}
    # Fallback for a tuple column added without a shape: name, description, bullets.
    return {"name": g(0), "desc": g(1), "features": _sub(g(2))}


def _row_to_page_in(row: dict[str, str]) -> CseoPageIn:
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
    for col in CONTENT_LINK_COLS:
        if (row.get(col) or "").strip():
            content[col] = _split_links(row[col])
    for col in CONTENT_TUPLE_COLS:
        if (row.get(col) or "").strip():
            content[col] = [_map_tuple(col, item.split("::")) for item in _split_list(row[col])]
    for col in CONTENT_SOLO_PAIR_COLS:
        if (row.get(col) or "").strip():
            title, _, detail = row[col].partition("::")
            content[col] = {"title": title.strip(), "detail": detail.strip()}
    for col in CONTENT_SECTION_COLS:
        if (row.get(col) or "").strip():
            eyebrow, heading, intro = (row[col].split("::", 2) + ["", ""])[:3]
            content[col] = {"eyebrow": eyebrow.strip(), "heading": heading.strip(),
                            "intro": intro.strip()}
    for col in CONTENT_QA_COLS:
        if (row.get(col) or "").strip():
            content[col] = _split_faqs(row[col])

    qs = (row.get("quality_score") or "").strip()
    try:
        quality_score = int(float(qs)) if qs else None
    except ValueError:
        quality_score = None

    # The packages ship robots_status ("noindex,nofollow") and a publishing-workflow
    # status ("staging", "ready") rather than DB values. Read both as the launch gate
    # they are.
    #
    # The global package ships "index_status,index" instead, and that column is
    # deliberately NOT read here: a pillar arrives as a draft and noindex, and a
    # human flips robots through POST /{id}/index-status once launch QA passes. A
    # spreadsheet cell must not be able to put an unreviewed page into the index.
    robots = (row.get("robots_status") or "").strip().lower()
    index_status = "index" if robots.startswith("index") else "noindex"
    status = (row.get("status") or "").strip().lower() or None
    if status in ("staging", "ready", "ready_for_upload", "ready_for_upload_noindex"):
        status = CseoPageStatus.DRAFT.value

    return CseoPageIn(
        country=(row.get("country") or row.get("country_code") or "").strip(),
        country_label=(row.get("country") or "").strip() or None,
        meta_title=(row.get("meta_title") or "").strip() or None,
        meta_description=(row.get("meta_description") or "").strip() or None,
        h1=(row.get("h1") or "").strip() or None,
        canonical_url=(row.get("canonical_url") or "").strip() or None,
        index_status=index_status,
        quality_score=quality_score,
        content=content,
        status=status,
    )


@admin_router.get("/import/columns")
def admin_import_columns(_: User = Depends(superadmin_required)):
    return {"columns": ALL_COLS, "required": ["country"], "list_separator": "|",
            "faq_separator": "||", "pair_separator": "::", "subfield_separator": ";",
            "pair_columns": CONTENT_PAIR_COLS + CONTENT_SOLO_PAIR_COLS,
            "link_columns": CONTENT_LINK_COLS,
            "tuple_columns": CONTENT_TUPLE_COLS + CONTENT_SECTION_COLS,
            "list_columns": CONTENT_LIST_COLS}


@admin_router.post("/import")
def admin_import(file: UploadFile = File(...), db: Session = Depends(get_db),
                 _: User = Depends(superadmin_required)):
    blob = file.file.read()
    if len(blob) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")
    rows = _read_rows(file.filename or "import.csv", blob)

    results, created, updated, failed, touched = [], 0, 0, 0, []
    for idx, row in enumerate(rows, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        try:
            # Validate BEFORE defaults: _code() falls back to "in" for junk
            # input, so a row with a blank country would silently overwrite the
            # India pillar instead of failing.
            if not (row.get("country") or row.get("country_code") or "").strip():
                raise ValueError("country is required")
            data = _apply_defaults(_row_to_page_in(row))
            if data.status and data.status not in (CseoPageStatus.DRAFT.value, CseoPageStatus.PUBLISHED.value):
                raise ValueError(f"invalid status: {data.status}")
            page = db.query(CseoPage).filter(CseoPage.country == data.country).first()
            if page is not None:
                was_published = page.status == CseoPageStatus.PUBLISHED.value
                page.country_label = data.country_label
                page.meta_title, page.meta_description, page.h1 = data.meta_title, data.meta_description, data.h1
                page.canonical_url = data.canonical_url or None
                page.index_status, page.quality_score, page.content = data.index_status, data.quality_score, data.content
                if data.status:
                    if data.status == CseoPageStatus.PUBLISHED.value and not was_published:
                        page.published_at = datetime.now(timezone.utc)
                    page.status = data.status
                action = "updated"
                updated += 1
            else:
                was_published = False
                if (data.status or "") == CseoPageStatus.PUBLISHED.value and data.quality_score is None:
                    raise ValueError("new pillar needs quality_score to import as published")
                page = CseoPage(
                    country=data.country, country_label=data.country_label,
                    meta_title=data.meta_title, meta_description=data.meta_description, h1=data.h1,
                    canonical_url=data.canonical_url or None, index_status=data.index_status,
                    quality_score=data.quality_score, content=data.content,
                    status=data.status or CseoPageStatus.DRAFT.value,
                    published_at=datetime.now(timezone.utc) if data.status == CseoPageStatus.PUBLISHED.value else None,
                )
                db.add(page)
                action = "created"
                created += 1
            db.flush()
            if page.status == CseoPageStatus.PUBLISHED.value or was_published:
                touched.append(page.country)
            results.append({"row": idx, "country": page.country, "action": action, "status": page.status})
        except Exception as e:
            db.rollback()
            failed += 1
            results.append({"row": idx, "country": (row.get("country") or "").strip() or None,
                            "action": "error", "error": str(e)})
    db.commit()
    for cc in set(touched):
        _invalidate(cc)
    return {"created": created, "updated": updated, "failed": failed, "results": results}
