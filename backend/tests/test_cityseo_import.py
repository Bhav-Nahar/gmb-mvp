"""City pillar import. The interesting parts are the cell format this package uses
(JSON arrays and JSON objects packed inside single cells, not the "|" / "::" scheme
every other package ships), the identity columns it does NOT ship at all, and the
three things the importer deliberately refuses to obey: schema_json, form_destination
and robots_status.
"""
import csv
import io
import json
import re
from html import unescape
from pathlib import Path

import pytest

from app.api import cityseo as cityseo_api
from app.api.cityseo import PAGE_TYPE, admin_import, parse_city_row
from app.models.lpseo_page import LpseoPage, LpseoPageStatus

PACKAGE_DIR = (Path(__file__).resolve().parents[2] / "pinzo-local-seo-city-pillar-mumbai")
PACKAGE_CSV = PACKAGE_DIR / "pinzo-local-seo-city-pillar-import-ready.csv"
PACKAGE_HTML = PACKAGE_DIR / "pinzo-local-seo-city-pillar-mumbai.html"

# The 25 columns the package originally shipped. None of them names the city, the
# city slug or the country: all three have to be derived.
ORIGINAL_COLUMNS = [
    "page_id", "page_type", "locale", "canonical_url", "primary_keyword",
    "secondary_keywords", "meta_title", "meta_description", "h1", "hero_copy",
    "direct_question", "direct_answer", "industry_search_journeys", "industry_entities",
    "city_context", "service_matrix", "ai_entity_plan", "proof_asset_type",
    "proof_asset_url", "internal_links", "schema_json", "primary_cta",
    "form_destination", "quality_score", "robots_status",
]

FORBIDDEN_DASHES = ["–", "—", "‑", "−"]


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


def _run(db, header, rows, monkeypatch):
    monkeypatch.setattr(cityseo_api, "trigger_lpseo_page_flush", lambda *a, **k: None)
    return admin_import(file=_FakeUpload(_csv_bytes(header, rows)), db=db, _=None)


@pytest.fixture
def package_row() -> dict:
    csv.field_size_limit(10 ** 7)
    with PACKAGE_CSV.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    return rows[0]


# ── The real package file ─────────────────────────────────────────────────────

def test_enriched_package_csv_is_a_strict_superset_of_the_original(package_row):
    # The enriched file overwrote the original in place. It may only ADD columns.
    for col in ORIGINAL_COLUMNS:
        assert col in package_row, f"enrichment dropped the original column {col}"
    assert package_row["page_id"] == "LSEO-000021"
    assert package_row["robots_status"] == "index,follow"
    assert package_row["quality_score"] == "90"

    # Superset in width AND in content: every recovered column must still hold copy.
    added = [c for c in package_row if c not in ORIGINAL_COLUMNS]
    assert len(package_row) == len(ORIGINAL_COLUMNS) + len(added) == 77
    blank = [c for c in added if not (package_row[c] or "").strip()]
    assert blank == [], f"recovered columns went blank: {blank}"
    # proof_asset_url is the package's one deliberate blank, and it is an ORIGINAL
    # column: there is no verified screenshot yet, so the proof section renders no
    # image at all rather than a placeholder.
    assert package_row["proof_asset_url"].strip() == ""

    # Every column the enriched file adds is a column the importer knows how to read.
    # An added column the importer ignores is copy that never reaches the page.
    assert not set(added) - set(cityseo_api.ALL_COLS)


def test_every_visible_block_of_the_reference_html_reaches_the_imported_page(db, monkeypatch):
    """The audit, as an assertion. Take every heading, paragraph, list item and table
    cell out of the reference HTML and require each one to survive the import.

    Chrome is excluded, and only chrome: <nav>, <header>, <footer> and <form> are the
    shared MarketingHeader, MarketingFooter and LpseoLeadForm, none of which the CSV
    describes. Everything else is page copy, and page copy that reaches the CSV but
    not `content` is stranded just as surely as copy that never left the HTML.
    """
    monkeypatch.setattr(cityseo_api, "trigger_lpseo_page_flush", lambda *a, **k: None)
    admin_import(file=_FakeUpload(PACKAGE_CSV.read_bytes()), db=db, _=None)
    p = db.query(LpseoPage).one()
    stored = json.dumps(p.content, ensure_ascii=False) + json.dumps(
        [p.h1, p.meta_title, p.meta_description], ensure_ascii=False)

    markup = PACKAGE_HTML.read_text(encoding="utf-8")
    markup = re.sub(r"<(script|style|nav|header|footer|form)\b.*?</\1>", "", markup, flags=re.S)
    blocks = re.findall(r"<(h1|h2|h3|p|li|td|th)\b[^>]*>(.*?)</\1>", markup, flags=re.S)
    assert len(blocks) > 100, "the reference HTML did not parse; the guard would pass vacuously"

    stranded = []
    for _tag, inner in blocks:
        text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", inner))).strip()
        if not text:
            continue
        # Compare JSON-escaped, so an apostrophe in "searcher's location" matches the
        # escaping the stored JSON uses rather than failing on it.
        if json.dumps(text, ensure_ascii=False)[1:-1] not in stored:
            stranded.append(text)
    assert not stranded, f"{len(stranded)} block(s) of reference copy never reach the page: {stranded[:3]}"


def test_package_csv_imports_as_one_draft_noindex_city_pillar(db, monkeypatch, package_row):
    monkeypatch.setattr(cityseo_api, "trigger_lpseo_page_flush", lambda *a, **k: None)
    res = admin_import(file=_FakeUpload(PACKAGE_CSV.read_bytes()), db=db, _=None)
    assert (res["created"], res["updated"], res["failed"]) == (1, 0, 0), res["results"]

    p = db.query(LpseoPage).one()
    assert p.slug == "mumbai" and p.city_slug == "mumbai" and p.city_label == "Mumbai"
    assert p.country == "in"
    assert p.h1 == "Local SEO Services in Mumbai"
    assert p.canonical_url == "https://www.pinzo.io/en-in/local-seo-services/mumbai/"
    # robots_status says index,follow. It is not obeyed: launch QA is a separate step.
    assert p.status == LpseoPageStatus.DRAFT.value
    assert p.index_status == "noindex"
    assert p.quality_score == 90
    # The row lives in lpseo_pages, so industry_slug must be non-null. It mirrors the
    # slug so no OTHER URL can list this page as an industry hub. See below.
    assert p.industry_slug == "mumbai" == p.slug
    # Discriminator in both places: the column (so the drip scheduler skips it) and
    # content (the only one the public payload serialises to the frontend).
    assert p.content["page_type"] == PAGE_TYPE == "city_pillar"
    assert getattr(p, "page_type", PAGE_TYPE) == PAGE_TYPE


def test_recovered_html_sections_survive_the_import(db, monkeypatch):
    """Copy that only existed in the reference HTML now reaches the page. Each of
    these was stranded before the CSV was enriched."""
    monkeypatch.setattr(cityseo_api, "trigger_lpseo_page_flush", lambda *a, **k: None)
    admin_import(file=_FakeUpload(PACKAGE_CSV.read_bytes()), db=db, _=None)
    c = db.query(LpseoPage).one().content

    assert len(c["catchment_areas"]) == 6
    assert c["catchment_areas"][0]["name"] == "South Mumbai"
    # service_matrix shipped nine bare titles; service_scope carries the descriptions.
    assert len(c["service_matrix"]) == 9 and len(c["service_scope"]) == 9
    assert all(s["detail"] for s in c["service_scope"])
    assert len(c["ranking_factors"]) == 3
    assert len(c["roadmap_phases"]) == 3 and len(c["roadmap_phases"][0]["steps"]) == 4
    assert len(c["partner_questions"]) == 4
    assert len(c["ai_entity_signals"]) == 6
    assert len(c["proof_metrics"]) == 4
    assert len(c["faqs"]) == 12
    assert c["direct_answer_support"].startswith("For Mumbai, this also requires")


def test_three_column_table_keeps_all_three_columns(db, monkeypatch):
    # The single-vs-multi table is the one place a flattening bug loses half the copy.
    monkeypatch.setattr(cityseo_api, "trigger_lpseo_page_flush", lambda *a, **k: None)
    admin_import(file=_FakeUpload(PACKAGE_CSV.read_bytes()), db=db, _=None)
    c = db.query(LpseoPage).one().content

    assert c["operating_model_columns"] == ["Area", "Single location business", "Multi location brand"]
    rows = c["operating_model_rows"]
    assert len(rows) == 5
    assert [r["area"] for r in rows] == ["Strategy", "Google profiles", "Website", "Reviews", "Reporting"]
    assert all(r["single"] and r["multi"] and r["single"] != r["multi"] for r in rows)


def test_no_forbidden_dash_characters_reach_the_page(db, monkeypatch):
    monkeypatch.setattr(cityseo_api, "trigger_lpseo_page_flush", lambda *a, **k: None)
    admin_import(file=_FakeUpload(PACKAGE_CSV.read_bytes()), db=db, _=None)
    p = db.query(LpseoPage).one()
    blob = json.dumps(p.content, ensure_ascii=False) + p.h1 + p.meta_title + p.meta_description
    for dash in FORBIDDEN_DASHES:
        assert dash not in blob, f"{dash!r} survived the import"


# ── What the importer refuses to obey ─────────────────────────────────────────

def test_schema_json_and_form_destination_are_never_imported(db, monkeypatch):
    monkeypatch.setattr(cityseo_api, "trigger_lpseo_page_flush", lambda *a, **k: None)
    admin_import(file=_FakeUpload(PACKAGE_CSV.read_bytes()), db=db, _=None)
    c = db.query(LpseoPage).one().content

    # Schema is generated server-side from the visible FAQ copy, so a packaged
    # schema block can never drift from what a visitor reads.
    assert "schema_json" not in c
    assert "form_destination" not in c
    assert "formsubmit.co" not in json.dumps(c)


def test_faqs_come_from_the_visible_copy_column_not_from_schema_json(db, monkeypatch, package_row):
    monkeypatch.setattr(cityseo_api, "trigger_lpseo_page_flush", lambda *a, **k: None)
    admin_import(file=_FakeUpload(PACKAGE_CSV.read_bytes()), db=db, _=None)
    imported = db.query(LpseoPage).one().content["faqs"]
    assert imported == json.loads(package_row["faqs"])
    assert all(set(f) == {"q", "a"} and f["q"] and f["a"] for f in imported)


def test_robots_status_index_is_ignored_on_reimport_too(db, monkeypatch):
    header = ["h1", "locale", "canonical_url", "robots_status"]
    row = ["Local SEO Services in Pune", "en-in",
           "https://www.pinzo.io/en-in/local-seo-services/pune/", "index,follow"]
    _run(db, header, [row], monkeypatch)
    p = db.query(LpseoPage).one()
    p.status, p.index_status = LpseoPageStatus.PUBLISHED.value, "index"
    db.commit()

    res = _run(db, header, [row], monkeypatch)
    assert res["updated"] == 1
    p = db.query(LpseoPage).one()
    assert p.status == LpseoPageStatus.DRAFT.value and p.index_status == "noindex"


# ── Identity derivation ───────────────────────────────────────────────────────

def test_identity_is_derived_when_the_csv_names_no_city_or_country():
    data = parse_city_row({
        "h1": "Local SEO Services in Mumbai",
        "locale": "en-in",
        "canonical_url": "https://www.pinzo.io/en-in/local-seo-services/mumbai/",
    })
    assert data.city_label == "Mumbai"
    assert data.city_slug == "mumbai" and data.slug == "mumbai"
    assert data.country == "in"


def test_canonical_url_wins_over_the_label_when_they_disagree():
    # "Bengaluru" the label, "bangalore" the published slug: the URL is the authority.
    data = parse_city_row({
        "h1": "Local SEO Services in Bengaluru",
        "locale": "en-in",
        "canonical_url": "https://www.pinzo.io/en-in/local-seo-services/bangalore/",
    })
    assert data.city_label == "Bengaluru" and data.city_slug == "bangalore"


def test_explicit_columns_beat_derivation():
    data = parse_city_row({
        "h1": "Local SEO Services in Dubai", "locale": "en-in",
        "city_label": "Dubai", "city_slug": "dubai", "country": "AE",
    })
    assert data.city_slug == "dubai" and data.country == "ae"
    assert data.canonical_url == "https://www.pinzo.io/en-ae/local-seo-services/dubai/"


def test_a_row_with_no_h1_and_no_city_is_an_error_not_a_guess(db, monkeypatch):
    res = _run(db, ["locale", "hero_copy"], [["en-in", "Some copy"]], monkeypatch)
    assert res["created"] == 0 and res["failed"] == 1
    assert "city_label is required" in res["results"][0]["error"]
    assert db.query(LpseoPage).count() == 0


# ── Cell format ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cell", ["", "City Pillar", "leaf"])
def test_page_type_is_normalised_whatever_the_cell_says(cell):
    # The frontend branches on page_type. The package writes the human label
    # "City Pillar"; the stored value must be the shared "city_pillar" vocabulary,
    # and a blank or wrong cell must not fall through to the industry template.
    data = parse_city_row({"h1": "Local SEO Services in Nagpur", "locale": "en-in", "page_type": cell})
    assert data.content["page_type"] == PAGE_TYPE == "city_pillar"


def test_malformed_json_in_a_cell_fails_that_row_with_a_named_column(db, monkeypatch):
    res = _run(db, ["h1", "locale", "catchment_areas"],
               [["Local SEO Services in Surat", "en-in", "[{not json"]], monkeypatch)
    assert res["failed"] == 1
    assert "catchment_areas" in res["results"][0]["error"]
    assert db.query(LpseoPage).count() == 0


def test_object_list_missing_a_key_fails_rather_than_half_filling_a_section(db, monkeypatch):
    # One rule: a section is filled entirely by imported content or not rendered.
    # A row missing "multi" would render a table with an empty column.
    res = _run(db, ["h1", "locale", "operating_model_rows"],
               [["Local SEO Services in Kochi", "en-in",
                 json.dumps([{"area": "Strategy", "single": "Focus one catchment."}])]], monkeypatch)
    assert res["failed"] == 1
    assert "missing multi" in res["results"][0]["error"]


def test_json_array_of_strings_is_read_as_a_list_not_a_string():
    data = parse_city_row({
        "h1": "Local SEO Services in Jaipur", "locale": "en-in",
        "secondary_keywords": '["local SEO Jaipur", "local SEO agency in Jaipur"]',
    })
    assert data.content["secondary_keywords"] == ["local SEO Jaipur", "local SEO agency in Jaipur"]


def test_a_list_column_holding_a_bare_string_is_rejected(db, monkeypatch):
    res = _run(db, ["h1", "locale", "secondary_keywords"],
               [["Local SEO Services in Indore", "en-in", '"just one keyword"']], monkeypatch)
    assert res["failed"] == 1
    assert "expected a JSON array" in res["results"][0]["error"]


# ── Slug safety ───────────────────────────────────────────────────────────────

def test_import_refuses_to_overwrite_an_industry_leaf_that_owns_the_slug(db, monkeypatch):
    db.add(LpseoPage(
        slug="mumbai", industry_label="Dentists", industry_slug="dentists",
        city_label="Mumbai", city_slug="mumbai", country="in",
        meta_title="t", meta_description="d", h1="h",
        index_status="index", content={}, status=LpseoPageStatus.PUBLISHED.value,
    ))
    db.commit()

    res = _run(db, ["h1", "locale", "canonical_url"],
               [["Local SEO Services in Mumbai", "en-in",
                 "https://www.pinzo.io/en-in/local-seo-services/mumbai/"]], monkeypatch)
    assert res["failed"] == 1 and res["created"] == 0
    assert "refusing to overwrite" in res["results"][0]["error"]
    survivor = db.query(LpseoPage).one()
    assert survivor.industry_slug == "dentists" and survivor.status == LpseoPageStatus.PUBLISHED.value


def test_industry_slug_mirrors_the_slug_so_no_phantom_hub_url_exists(db, monkeypatch):
    """/{locale}/local-seo-services/{seg} falls back to "industry hub listing every
    published page with industry_slug == seg" when no page owns {seg}. A shared
    sentinel industry ("city-pillar") is therefore a live, indexable URL the moment a
    pillar is published. industry_slug == slug means the only segment that reaches the
    hub branch is the pillar's own, which resolves to the pillar first."""
    header = ["h1", "locale", "canonical_url"]
    _run(db, header, [
        ["Local SEO Services in Mumbai", "en-in", "https://www.pinzo.io/en-in/local-seo-services/mumbai/"],
        ["Local SEO Services in Pune", "en-in", "https://www.pinzo.io/en-in/local-seo-services/pune/"],
    ], monkeypatch)

    pages = db.query(LpseoPage).order_by(LpseoPage.slug).all()
    assert [p.slug for p in pages] == ["mumbai", "pune"]
    for p in pages:
        assert p.industry_slug == p.slug == p.city_slug
    # No industry_slug is shared between two pillars, so no segment can ever collect
    # them into a hub, and none of them is a segment without a page behind it.
    slugs = {p.slug for p in pages}
    assert all(p.industry_slug in slugs for p in pages)
    assert len({p.industry_slug for p in pages}) == len(pages)


def test_reimport_rewrites_a_row_that_still_carries_the_old_sentinel_industry(db, monkeypatch):
    # Rows imported before the fix hold industry_slug="city-pillar". Re-importing has
    # to repair them, otherwise the phantom hub URL stays live.
    db.add(LpseoPage(
        slug="mumbai", industry_label="City Pillar", industry_slug="city-pillar",
        city_label="Mumbai", city_slug="mumbai", country="in",
        meta_title="t", meta_description="d", h1="Local SEO Services in Mumbai",
        index_status="noindex", content={"page_type": PAGE_TYPE}, page_type=PAGE_TYPE,
        status=LpseoPageStatus.DRAFT.value,
    ))
    db.commit()

    res = _run(db, ["h1", "locale", "canonical_url"],
               [["Local SEO Services in Mumbai", "en-in",
                 "https://www.pinzo.io/en-in/local-seo-services/mumbai/"]], monkeypatch)
    assert (res["created"], res["updated"], res["failed"]) == (0, 1, 0), res["results"]
    assert db.query(LpseoPage).one().industry_slug == "mumbai"


def test_reimporting_the_same_city_updates_in_place(db, monkeypatch):
    header = ["h1", "locale", "canonical_url", "hero_copy"]
    url = "https://www.pinzo.io/en-in/local-seo-services/mumbai/"
    _run(db, header, [["Local SEO Services in Mumbai", "en-in", url, "First"]], monkeypatch)
    res = _run(db, header, [["Local SEO Services in Mumbai", "en-in", url, "Second"]], monkeypatch)
    assert (res["created"], res["updated"]) == (0, 1)
    assert db.query(LpseoPage).count() == 1
    assert db.query(LpseoPage).one().content["hero_copy"] == "Second"
