"""City pillar import. The interesting parts are the cell format this package uses
(JSON arrays and JSON objects packed inside single cells, not the "|" / "::" scheme
every other package ships), the identity columns it does NOT ship at all, and the
three things the importer deliberately refuses to obey: schema_json, form_destination
and robots_status.
"""
import csv
import io
import json
from html import unescape
import pytest

from app.api import cityseo as cityseo_api
from app.api.cityseo import PAGE_TYPE, admin_import, parse_city_row
from app.models.lpseo_page import LpseoPage, LpseoPageStatus



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



# ── What the importer refuses to obey ─────────────────────────────────────────


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
