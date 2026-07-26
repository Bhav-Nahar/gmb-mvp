"""City pillar pages for the Local SEO universe, served at
/{locale}/local-seo-services/{city-slug} (for example /en-in/local-seo-services/mumbai).

Storage deliberately reuses `lpseo_pages`. A city pillar is a leaf in the same URL
namespace as the industry x city pages, so giving it its own table would mean two
tables racing for one slug and a second resolver on the hot public route. Instead the
row lands in lpseo_pages with slug == industry_slug == city_slug (see
PLACEHOLDER_INDUSTRY_LABEL for why the industry mirrors the slug), and the EXISTING
/public/lpseo/{slug} endpoint serves it unchanged. `content["page_type"]`
is the discriminator the frontend branches on. No new table, no migration.

Why this module exists at all, rather than more columns in lpseo.py: the city-pillar
package ships a genuinely different content schema. Its CSV packs JSON arrays and
JSON objects inside single cells instead of the "|" / "::" separator scheme every
other package uses, and its sections (catchments, operating-model table, 90 day plan,
partner questions) have no counterpart on an industry x city leaf. Duplicating the
importer keeps that difference explicit instead of overloading a shared parser.

Deliberate omissions:
- `schema_json` is IGNORED. Schema is generated server-side from the visible copy, so
  the FAQPage block cannot drift from the FAQs a visitor actually sees, and a package
  that ships stale or invalid JSON-LD cannot publish it straight to production.
- `form_destination` is IGNORED. The package points at formsubmit.co, which neither
  stores the lead nor survives QA. The rendered page reuses the shared lead form,
  which posts to /public/lpseo/leads and persists before emailing.
- `robots_status` is READ BUT NOT OBEYED. Every import lands draft + noindex; going
  live is a separate, deliberate admin action once launch QA passes.
"""
import json
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import superadmin_required
from app.core.redis_client import get_redis
from app.models.lpseo_page import LpseoPage, LpseoPageStatus
from app.models.user import User
from app.services.revalidation_service import trigger_lpseo_page_flush
# Page-type-agnostic file reader, reused verbatim from pseo.
from app.api.pseo import _read_rows

logger = logging.getLogger(__name__)

admin_router = APIRouter()

SITE_URL = "https://www.pinzo.io"

# Shared vocabulary with lpseo_pages.page_type ("leaf" / "industry_pillar" /
# "city_pillar"). Written in two places on purpose:
#   - the COLUMN, so the drip scheduler can say "leaves only" and never trickle a
#     hand-authored pillar into the index;
#   - content["page_type"], because the public payload serialises `content` but not
#     the column, and the frontend needs the discriminator to pick a template.
PAGE_TYPE = "city_pillar"

# A city pillar has no industry, but lpseo_pages.industry_slug is NOT NULL and indexed
# with city_slug, so it needs a value.
#
# That value is the CITY SLUG, i.e. the row's own slug, and that choice is load-bearing.
# /{locale}/local-seo-services/{seg} resolves a page by slug first and only falls back
# to "industry hub listing every published page with industry_slug == seg" when no page
# owns the slug. A shared sentinel like "city-pillar" is therefore a live URL:
# /en-in/local-seo-services/city-pillar owns no page, so a published + indexed pillar
# would make it render an indexable phantom hub titled "City Pillar", and the sitemap
# (which emits one hub URL per distinct industry_slug) would advertise it. Setting
# industry_slug == slug makes the only URL that can reach the hub branch the pillar's
# own URL, which always resolves to the pillar itself first. It also makes the shared
# isLpseoPillar() check (slug === industry_slug) true, which is what keeps the pillar
# out of the country hub's industry cards and out of the sitemap's leaf list.
#
# The label stays a constant: it is admin-facing only. With industry_slug == slug the
# frontend never renders it, because every path that would have is now unreachable.
PLACEHOLDER_INDUSTRY_LABEL = "City Pillar"

# lpseo_pages.page_type is arriving alongside this module. Set it when the model has
# it, so neither change has to land before the other to keep imports working.
_HAS_PAGE_TYPE_COLUMN = hasattr(LpseoPage, "page_type")


# ── Column schema ─────────────────────────────────────────────────────────────
#
# This package packs JSON inside cells. A list column holds a JSON array of strings,
# an object-list column a JSON array of objects, an object column a JSON object. That
# is the package's own convention and the enriched CSV keeps it.

IDENTITY_COLS = [
    "locale", "canonical_url", "meta_title", "meta_description", "h1",
    "city_label", "city_slug", "country", "quality_score", "robots_status",
]

TEXT_COLS = [
    "page_id", "page_type", "primary_keyword", "hero_eyebrow", "hero_copy",
    "hero_image_alt", "hero_image_caption", "primary_cta", "secondary_cta",
    "direct_question", "direct_answer", "direct_answer_support",
    "city_context", "catchment_heading", "catchment_intro",
    "service_scope_heading", "ranking_heading",
    "operating_model_heading", "roadmap_heading", "roadmap_note",
    "proof_heading", "proof_intro", "proof_image_alt", "proof_asset_url",
    "ai_heading", "ai_signals_heading", "ai_entity_plan",
    "industry_links_heading", "industry_links_intro", "partner_heading",
    "faq_heading", "lead_eyebrow", "lead_heading", "lead_intro", "lead_consent_note",
    "og_title", "og_description", "og_image", "og_image_alt", "hreflang_x_default",
    "country_label", "state_region", "parent_url",
]

# JSON array of strings.
LIST_COLS = [
    "secondary_keywords", "industry_search_journeys", "industry_entities",
    "service_matrix", "proof_asset_type", "hero_trust_points", "ranking_intro",
    "ai_intro", "ai_entity_signals", "operating_model_columns", "lead_points",
]

# JSON array of objects. The value is the expected key set: a row missing a key is a
# broken import, not a half-filled section, because one rule for this page type is
# that a section is filled entirely by imported content or not rendered at all.
OBJECT_LIST_COLS: dict[str, tuple[str, ...]] = {
    "internal_links": ("anchor", "url"),
    "catchment_areas": ("name", "detail"),
    "service_scope": ("title", "detail"),
    "ranking_factors": ("title", "detail"),
    "operating_model_rows": ("area", "single", "multi"),
    "roadmap_phases": ("days", "title", "steps"),
    "proof_metrics": ("label", "detail"),
    "industry_link_groups": ("title", "links"),
    "partner_questions": ("title", "detail"),
    "faqs": ("q", "a"),
}

# JSON object.
OBJECT_COLS = ["section_eyebrows"]

# Read for context but never applied. See the module docstring.
IGNORED_COLS = ["schema_json", "form_destination"]

ALL_COLS = (IDENTITY_COLS + TEXT_COLS + LIST_COLS
            + list(OBJECT_LIST_COLS) + OBJECT_COLS + IGNORED_COLS)


# ── Cell parsing ──────────────────────────────────────────────────────────────

def _loads(col: str, cell: str) -> Any:
    try:
        return json.loads(cell)
    except json.JSONDecodeError as e:
        raise ValueError(f"{col}: cell is not valid JSON ({e.msg} at char {e.pos})")


def _json_list(col: str, cell: str) -> list[str]:
    val = _loads(col, cell)
    if not isinstance(val, list):
        raise ValueError(f"{col}: expected a JSON array, got {type(val).__name__}")
    return [str(v).strip() for v in val if str(v).strip()]


def _json_object_list(col: str, cell: str, keys: tuple[str, ...]) -> list[dict]:
    val = _loads(col, cell)
    if not isinstance(val, list):
        raise ValueError(f"{col}: expected a JSON array, got {type(val).__name__}")
    out = []
    for i, item in enumerate(val):
        if not isinstance(item, dict):
            raise ValueError(f"{col}[{i}]: expected an object, got {type(item).__name__}")
        missing = [k for k in keys if k not in item]
        if missing:
            raise ValueError(f"{col}[{i}]: missing {', '.join(missing)}")
        out.append({k: item[k] for k in keys})
    return out


def _json_object(col: str, cell: str) -> dict:
    val = _loads(col, cell)
    if not isinstance(val, dict):
        raise ValueError(f"{col}: expected a JSON object, got {type(val).__name__}")
    return val


# ── Identity derivation ───────────────────────────────────────────────────────
#
# The package CSV carries no city_label, city_slug or country column. Rather than
# make an operator hand-add three columns to every city package, derive them and let
# an explicit column win when one is present.

_H1_CITY_RE = re.compile(r"^\s*Local SEO Services in\s+(.+?)\s*$", re.IGNORECASE)


def _slugify(value: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", value.strip().lower())).strip("-")


def _derive_city_label(row: dict[str, str]) -> str:
    explicit = (row.get("city_label") or "").strip()
    if explicit:
        return explicit
    m = _H1_CITY_RE.match(row.get("h1") or "")
    if m:
        return m.group(1)
    raise ValueError("city_label is required (and could not be derived from h1)")


def _derive_city_slug(row: dict[str, str], city_label: str) -> str:
    explicit = (row.get("city_slug") or "").strip().lower()
    if explicit:
        return explicit
    # The canonical URL is the authority on the published slug; the label is only a
    # fallback, because a label and a slug can legitimately differ ("Bengaluru").
    canonical = (row.get("canonical_url") or "").strip().rstrip("/")
    if canonical:
        last = canonical.rsplit("/", 1)[-1]
        if last and last != "local-seo-services":
            return last.lower()
    return _slugify(city_label)


def _derive_country(row: dict[str, str]) -> str:
    explicit = (row.get("country") or "").strip().lower()
    if len(explicit) == 2:
        return explicit
    locale = (row.get("locale") or "").strip().lower()
    if re.fullmatch(r"[a-z]{2}-[a-z]{2}", locale):
        return locale.split("-")[1]
    return "in"


# ── Row -> page ───────────────────────────────────────────────────────────────

class CityPageIn(BaseModel):
    slug: str
    country: str
    city_label: str
    city_slug: str
    meta_title: str
    meta_description: str
    h1: str
    canonical_url: Optional[str] = None
    quality_score: Optional[int] = None
    content: dict[str, Any] = Field(default_factory=dict)


def parse_city_row(row: dict[str, str]) -> CityPageIn:
    """Turn one enriched-CSV row into the page we will store. Pure: no DB, no IO."""
    row = {(k or "").strip().lower(): (v or "") for k, v in row.items()}

    content: dict[str, Any] = {}
    for col in TEXT_COLS:
        if row.get(col, "").strip():
            content[col] = row[col].strip()
    for col in LIST_COLS:
        if row.get(col, "").strip():
            content[col] = _json_list(col, row[col])
    for col, keys in OBJECT_LIST_COLS.items():
        if row.get(col, "").strip():
            content[col] = _json_object_list(col, row[col], keys)
    for col in OBJECT_COLS:
        if row.get(col, "").strip():
            content[col] = _json_object(col, row[col])

    # The discriminator the public route branches on. Stamped unconditionally so a
    # row whose page_type cell was blank or misspelled still renders as a city pillar
    # rather than silently falling through to the industry template.
    content["page_type"] = PAGE_TYPE

    city_label = _derive_city_label(row)
    city_slug = _derive_city_slug(row, city_label)
    country = _derive_country(row)
    locale = f"en-{country}"

    qs = row.get("quality_score", "").strip()
    try:
        quality_score = int(float(qs)) if qs else None
    except ValueError:
        quality_score = None

    h1 = row.get("h1", "").strip() or f"Local SEO Services in {city_label}"
    return CityPageIn(
        slug=city_slug,
        country=country,
        city_label=city_label,
        city_slug=city_slug,
        meta_title=row.get("meta_title", "").strip() or f"Local SEO Services in {city_label} | Pinzo",
        meta_description=row.get("meta_description", "").strip() or (
            f"Local SEO services in {city_label} for stronger Google Maps visibility, "
            f"local rankings, reviews and leads."
        ),
        h1=h1,
        canonical_url=row.get("canonical_url", "").strip() or f"{SITE_URL}/{locale}/local-seo-services/{city_slug}/",
        quality_score=quality_score,
        content=content,
    )


# ── Cache invalidation ────────────────────────────────────────────────────────
#
# The row is served by /public/lpseo/{slug}, so it sits under that endpoint's Redis
# key. Keep this string in sync with lpseo._cache_key; it is duplicated rather than
# imported so a refactor there cannot silently reach into this module's behaviour.
def _invalidate(slug: str, country: str) -> None:
    try:
        get_redis().delete(f"public_lpseo:{slug}")
    except Exception:
        pass
    # Narrow flush: a city pillar owns one path and busts no list tag.
    trigger_lpseo_page_flush(slug, country)


# ── Admin ─────────────────────────────────────────────────────────────────────

@admin_router.get("/import/columns")
def admin_import_columns(_: User = Depends(superadmin_required)):
    return {
        "columns": ALL_COLS,
        "required": ["h1"],
        "cell_format": "JSON inside cells: list columns hold a JSON array of strings, "
                       "object-list columns a JSON array of objects, object columns a JSON object.",
        "identity_columns": IDENTITY_COLS,
        "text_columns": TEXT_COLS,
        "list_columns": LIST_COLS,
        "object_list_columns": {k: list(v) for k, v in OBJECT_LIST_COLS.items()},
        "object_columns": OBJECT_COLS,
        "ignored_columns": IGNORED_COLS,
        "derived_columns": ["city_label (from h1)", "city_slug (from canonical_url)", "country (from locale)"],
        "notes": [
            "schema_json is ignored; JSON-LD is generated from the visible copy.",
            "form_destination is ignored; the page uses the stored /public/lpseo/leads form.",
            "robots_status is ignored; every import lands draft + noindex until launch QA passes.",
        ],
    }


@admin_router.post("/import")
def admin_import(file: UploadFile = File(...), db: Session = Depends(get_db),
                 _: User = Depends(superadmin_required)):
    """Import city pillars from the package CSV/XLSX into lpseo_pages.

    Always draft + noindex, whatever robots_status says. An imported pillar is
    unreviewed content: publishing and indexing are separate admin actions taken
    after the launch checklist passes.
    """
    blob = file.file.read()
    if len(blob) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")
    rows = _read_rows(file.filename or "import.csv", blob)

    results, created, updated, failed, touched = [], 0, 0, 0, []
    for idx, row in enumerate(rows, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        try:
            data = parse_city_row(row)
            page = db.query(LpseoPage).filter(LpseoPage.slug == data.slug).first()
            if page is not None:
                # Refuse to overwrite a real industry x city leaf that happens to own
                # this slug. Silently converting /dentists-in-mumbai into a city
                # pillar would take a live page down.
                existing_type = (getattr(page, "page_type", None)
                                 or (page.content or {}).get("page_type") or "")
                if str(existing_type).strip().lower() != PAGE_TYPE:
                    raise ValueError(
                        f"slug '{data.slug}' already belongs to a non-city-pillar page "
                        f"({page.industry_slug or 'unknown'}); refusing to overwrite"
                    )
                was_published = page.status == LpseoPageStatus.PUBLISHED.value
                # Rewritten on every update, not only on create: a row imported before
                # industry_slug became the city slug still carries the old sentinel,
                # and leaving it there leaves the phantom hub URL live.
                page.industry_label = PLACEHOLDER_INDUSTRY_LABEL
                page.industry_slug = data.city_slug
                page.city_label, page.city_slug, page.country = data.city_label, data.city_slug, data.country
                page.meta_title, page.meta_description, page.h1 = data.meta_title, data.meta_description, data.h1
                page.canonical_url = data.canonical_url or None
                page.quality_score, page.content = data.quality_score, data.content
                page.index_status = "noindex"
                page.status = LpseoPageStatus.DRAFT.value
                if _HAS_PAGE_TYPE_COLUMN:
                    page.page_type = PAGE_TYPE
                action = "updated"
                updated += 1
            else:
                was_published = False
                page = LpseoPage(
                    slug=data.slug,
                    industry_label=PLACEHOLDER_INDUSTRY_LABEL,
                    industry_slug=data.city_slug,
                    city_label=data.city_label, city_slug=data.city_slug, country=data.country,
                    meta_title=data.meta_title, meta_description=data.meta_description, h1=data.h1,
                    canonical_url=data.canonical_url or None,
                    index_status="noindex", quality_score=data.quality_score,
                    content=data.content, status=LpseoPageStatus.DRAFT.value,
                    **({"page_type": PAGE_TYPE} if _HAS_PAGE_TYPE_COLUMN else {}),
                )
                db.add(page)
                action = "created"
                created += 1
            db.flush()
            if was_published:
                touched.append((page.slug, page.country))
            results.append({"row": idx, "slug": page.slug, "action": action,
                            "status": page.status, "index_status": page.index_status})
        except Exception as e:
            db.rollback()
            failed += 1
            results.append({"row": idx, "slug": (row.get("city_slug") or "").strip() or None,
                            "action": "error", "error": str(e)})
    db.commit()
    for slug, country in set(touched):
        _invalidate(slug, country)
    return {"created": created, "updated": updated, "failed": failed, "results": results}
