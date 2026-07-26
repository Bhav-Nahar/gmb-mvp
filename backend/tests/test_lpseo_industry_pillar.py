from datetime import datetime, timezone

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
"""Industry pillar (/{locale}/local-seo-services/{industry-slug}) on the lpSEO table.

The pillar reuses lpseo_pages and the lpSEO template verbatim; the only structural
difference is that it has NO city while city_label and city_slug are NOT NULL. These
tests pin the compromise that avoids a migration (the COUNTRY stands in for the city),
prove the blank-city relaxation is scoped to pillars only, and import the real shipped
package CSV end to end so a content-side regression fails here rather than in prod.
"""
import csv
import io
from pathlib import Path

from app.api import lpseo as lpseo_api
from app.api.lpseo import admin_import_pages
from app.models.lpseo_page import LpseoPage, LpseoPageStatus

PACKAGE_CSV = (
    Path(__file__).resolve().parents[2]
    / "pinzo-local-seo-industry-pillar-dentists-india-bundle"
    / "pinzo-local-seo-industry-pillar-dentists-india-import-ready.csv"
)

# Guardrail 9: prohibited in every generated field and in the HTML.
BANNED_CHARS = {
    "–": "en dash", "—": "em dash",
    "‑": "non-breaking hyphen", "−": "minus sign",
}


class _FakeUpload:
    def __init__(self, blob: bytes, filename: str = "import.csv"):
        self.file = io.BytesIO(blob)
        self.filename = filename


def _csv_bytes(header, rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode()


def _run(db, monkeypatch, blob: bytes):
    captured = {"touched": []}
    monkeypatch.setattr(lpseo_api, "trigger_bulk_lpseo_revalidation",
                        lambda entries: captured.__setitem__("touched", entries))
    result = admin_import_pages(file=_FakeUpload(blob), db=db, _=None)
    return result, captured["touched"]


def _run_rows(db, monkeypatch, header, rows):
    return _run(db, monkeypatch, _csv_bytes(header, rows))


# ── The blank-city compromise ────────────────────────────────────────────────

def test_pillar_row_imports_with_no_city(db, monkeypatch):
    """page_type=industry_pillar is what makes a blank city_label legal. The country
    fills the NOT NULL columns, which also produces the label the pillar wants."""
    result, _ = _run_rows(
        db, monkeypatch,
        ["slug", "country", "industry_label", "city_label", "page_type", "quality_score"],
        [["dentists", "India", "Dentists", "", "industry_pillar", "100"]],
    )
    assert result["created"] == 1 and result["failed"] == 0

    page = db.query(LpseoPage).filter(LpseoPage.slug == "dentists").one()
    assert page.country == "in"
    assert page.industry_slug == "dentists"
    # Country stands in for the missing city, so nothing downstream sees a blank.
    assert page.city_label == "India" and page.city_slug == "india"
    # slug == industry_slug is the discriminator the frontend reads off list rows.
    assert page.slug == page.industry_slug
    assert page.h1 == "Local SEO Services for Dentists in India"
    assert page.content["page_type"] == "industry_pillar"


def test_pillar_defaults_to_draft_and_noindex(db, monkeypatch):
    """A pillar must not be indexed before its child and product links are verified,
    so it lands noindex even when the row says nothing about indexing."""
    result, touched = _run_rows(
        db, monkeypatch,
        ["industry_label", "city_label", "country", "page_type"],
        [["Dentists", "", "India", "industry_pillar"]],
    )
    assert result["created"] == 1
    page = db.query(LpseoPage).filter(LpseoPage.slug == "dentists").one()
    assert page.status == LpseoPageStatus.DRAFT.value and page.index_status == "noindex"
    assert touched == []  # never published, no live URL to purge


def test_pillar_can_still_be_imported_indexable(db, monkeypatch):
    # The noindex default is a default, not a lock: publishing later must stay possible.
    _run_rows(
        db, monkeypatch,
        ["industry_label", "city_label", "country", "page_type", "index_status"],
        [["Dentists", "", "India", "industry_pillar", "index"]],
    )
    assert db.query(LpseoPage).filter(LpseoPage.slug == "dentists").one().index_status == "index"


def test_leaf_row_with_blank_city_still_fails(db, monkeypatch):
    """The relaxation is scoped to pillars. A city page with a missing city is a
    typo, and must not silently become '<industry> in India' on slug -in-india."""
    result, _ = _run_rows(
        db, monkeypatch,
        ["industry_label", "city_label", "country"],
        [["Dentists", "", "India"]],
    )
    assert result["failed"] == 1 and result["created"] == 0
    err = next(r for r in result["results"] if r["action"] == "error")
    assert "city_label" in err["error"]
    assert db.query(LpseoPage).count() == 0


def test_pillar_and_its_city_children_coexist(db, monkeypatch):
    # Same industry, same market, different slugs: no collision with the leaf corpus.
    result, _ = _run_rows(
        db, monkeypatch,
        ["industry_label", "city_label", "country", "page_type"],
        [["Dentists", "", "India", "industry_pillar"],
         ["Dentists", "Mumbai", "India", ""],
         ["Dentists", "Pune", "India", ""]],
    )
    assert result["created"] == 3 and result["failed"] == 0
    slugs = {p.slug for p in db.query(LpseoPage).all()}
    assert slugs == {"dentists", "dentists-in-mumbai", "dentists-in-pune"}


# ── The shipped package ──────────────────────────────────────────────────────

def test_shipped_package_csv_imports(db, monkeypatch):
    """The enriched dentists/India package must import unedited, with the canonical
    columns added by the audit winning over the package's lossier aliases."""
    result, touched = _run(db, monkeypatch, PACKAGE_CSV.read_bytes())
    assert result["created"] == 1 and result["failed"] == 0, result["results"]
    assert touched == []  # draft, so nothing live to revalidate

    page = db.query(LpseoPage).filter(LpseoPage.slug == "dentists").one()
    assert page.country == "in" and page.city_label == "India"
    assert page.status == LpseoPageStatus.DRAFT.value and page.index_status == "noindex"
    assert page.canonical_url == "https://www.pinzo.io/en-in/local-seo-services/dentists"
    c = page.content

    # Recovered from the reference HTML: the service matrix is 10 rows and keeps its
    # third "why it matters" column, which the 2-part `solutions` cell had dropped.
    assert len(c["services"]) == 10
    assert all(s["channel"] and s["work"] and s["outcome"] for s in c["services"])
    assert c["services"][0]["channel"] == "Google Maps and GBP"

    # Canonical column beats the package alias for the same section.
    assert len(c["search_intents"]) == 4
    assert c["search_intents"][0]["title"] == "Locality and near-me searches"
    assert all(i["detail"] for i in c["search_intents"])

    # Sections that had no CSV column at all before the audit.
    assert [j["title"] for j in c["journey_stages"]] == ["Search", "Compare", "Evaluate", "Contact", "Book"]
    assert len(c["proof_points"]) == 4
    assert len(c["value_props"]) == 3
    assert len(c["deliverables"]) == 9
    assert len(c["comparison"]) == 6
    assert all(r["point"] and r["agency"] and r["software"] and r["pinzo"] for r in c["comparison"])
    assert [p["days"] for p in c["workflow_phases"]] == ["Days 1 to 30", "Days 31 to 60", "Days 61 to 90"]
    assert all(len(p["steps"]) == 3 for p in c["workflow_phases"])
    assert [p["name"] for p in c["plans"]] == ["Pinzo Platform", "Pinzo Managed Local SEO", "Pinzo for Dental Groups"]
    assert [p["featured"] for p in c["plans"]] == [False, True, False]
    assert all(len(p["features"]) == 3 for p in c["plans"])
    assert c["answer_heading"].startswith("What are Local SEO services for dentists")
    assert c["strategy_heading"] and c["strategy_body"] and c["lead_heading"] and c["lead_sub"]

    # The pillar's routing job: six city names that the template turns into links.
    assert c["neighborhoods"] == ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Pune", "Chennai"]
    assert len(c["city_factors"]) == 7  # six markets plus the doorway-page warning

    # 8 to 12 visible FAQs (guardrail 5.18); the template renders these verbatim into
    # both the accordion and the FAQPage schema, so parsing must not mangle them.
    assert 8 <= len(c["faqs"]) <= 12
    assert all(f["q"].endswith("?") and f["a"] for f in c["faqs"])

    # Package columns describing GBP-listing work render no section here and are dropped.
    for dead in ("gbp_categories", "gbp_attributes", "post_ideas", "photo_checklist",
                 "solutions", "why_matters_points", "url", "schema_type"):
        assert dead not in c


def test_shipped_package_csv_is_a_strict_superset_of_the_50_column_header(db):
    """The audit enriched the file in place. It must still carry every original
    package column, in the original order, before the recovered ones."""
    with PACKAGE_CSV.open(encoding="utf-8-sig", newline="") as fh:
        cols = list(csv.DictReader(fh).fieldnames)
    original = [
        "slug", "country", "industry_label", "industry_slug", "city_label", "city_slug",
        "meta_title", "meta_description", "h1", "canonical_url", "index_status",
        "quality_score", "status", "badge", "hero_sub", "primary_cta", "secondary_cta",
        "answer_block", "why_matters_body", "reviews_body", "example_review", "example_reply",
        "city_visibility_body", "final_heading", "final_sub", "final_button", "primary_keyword",
        "page_type", "template_version", "region", "last_updated", "why_matters_points",
        "gbp_categories", "gbp_services", "gbp_attributes", "review_themes", "post_ideas",
        "photo_checklist", "neighborhoods", "single_points", "multi_points", "secondary_keywords",
        "problems", "solutions", "monthly_workflow", "faqs", "review_examples", "related_pages",
        "url", "schema_type",
    ]
    assert cols[:50] == original
    assert len(cols) > 50  # enrichment actually happened


def test_shipped_package_copy_has_no_prohibited_dashes(db, monkeypatch):
    _run(db, monkeypatch, PACKAGE_CSV.read_bytes())
    page = db.query(LpseoPage).filter(LpseoPage.slug == "dentists").one()

    def walk(node):
        if isinstance(node, str):
            for ch, name in BANNED_CHARS.items():
                assert ch not in node, f"{name} in imported copy: {node[:80]}"
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(page.content)
    walk([page.h1, page.meta_title, page.meta_description])


def test_import_syncs_page_type_column_with_content(db, monkeypatch):
    """content["page_type"] is what the frontend reads; the COLUMN is what the drip
    scheduler filters on. If they drift, a pillar gets drip-released."""
    from app.services import lpseo_drip
    monkeypatch.setattr(lpseo_api, "trigger_bulk_lpseo_revalidation", lambda *_a, **_k: None)

    _run_rows(db, monkeypatch,
              ["industry_label", "city_label", "country", "page_type", "quality_score",
               "status", "index_status"],
              # Both noindex, so both would be drip candidates but for the type filter.
              [["Dentists", "", "in", "industry_pillar", "100", "published", "noindex"],
               ["Dentists", "Mumbai", "in", "", "96", "published", "noindex"]])

    pillar = db.query(LpseoPage).filter(LpseoPage.slug == "dentists").one()
    leaf = db.query(LpseoPage).filter(LpseoPage.slug == "dentists-in-mumbai").one()
    assert pillar.page_type == "industry_pillar" and pillar.content["page_type"] == "industry_pillar"
    assert leaf.page_type == "leaf"

    # The whole point: the drip must see one eligible page, not two.
    assert lpseo_drip.arm(db, start=NOW, seed=1)["scheduled"] == 1
    db.refresh(pillar)
    assert pillar.index_at is None
