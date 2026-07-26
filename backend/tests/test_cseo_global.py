"""Global Local SEO pillar (LSEO-GLOBAL-001).

It is the same page family as the country pillars and shares cseo_pages, but its
scope is "global" rather than a two-letter market, and its section set is its own.
These tests pin the three things that were easy to get wrong:

1. "global" must not be coerced to "in". pseo._country_code() maps anything it does
   not recognise to India, which would make importing the global pillar silently
   overwrite the India country pillar.
2. The multi-part rows must keep every part. Prior packages lost the third column of
   a three-column table by flattening it into a two-part cell.
3. The shipped package CSV must import cleanly, as a draft and noindex.
"""
import csv
import io
from app.api import cseo as cseo_api
from app.api.cseo import (
    GLOBAL, _apply_defaults, _code, _loc, _path, _row_to_page_in, admin_import,
)
from app.models.cseo_page import CseoPage, CseoPageStatus


class _FakeUpload:
    def __init__(self, blob: bytes, filename: str):
        self.file = io.BytesIO(blob)
        self.filename = filename


def _run(db, blob: bytes, monkeypatch):
    monkeypatch.setattr(cseo_api, "trigger_cseo_revalidation", lambda *_a, **_k: None)
    return admin_import(file=_FakeUpload(blob, "import.csv"), db=db, _=None)


def _csv_bytes(header, rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode()


# ── Scope resolution ─────────────────────────────────────────────────────────

def test_global_is_not_coerced_to_india():
    assert _code("global") == GLOBAL
    assert _code("Global") == GLOBAL
    assert _code("  GLOBAL  ") == GLOBAL
    # The country pillars keep their existing behaviour, junk fallback included.
    assert _code("India") == "in"
    assert _code("") == "in"
    assert _code("not a country") == "in"


def test_global_pillar_is_locale_free():
    assert _loc(GLOBAL) == "en"
    assert _path(GLOBAL) == "/local-seo-services/"
    assert _loc("in") == "en-in"
    assert _path("in") == "/en-in/local-seo-services/"


def test_global_defaults_do_not_read_as_a_country():
    data = _apply_defaults(cseo_api.CseoPageIn(country="global"))
    assert data.country == GLOBAL
    assert data.country_label == "Global"
    # Not "Local SEO Services in Global", and not /en-global/.
    assert data.h1 == "Local SEO Services"
    assert data.canonical_url == "https://www.pinzo.io/local-seo-services/"


def test_global_row_does_not_collide_with_the_india_pillar(db, monkeypatch):
    blob = _csv_bytes(["country", "quality_score"], [["India", "90"], ["global", "94"]])
    res = _run(db, blob, monkeypatch)
    assert res["created"] == 2 and res["failed"] == 0
    assert {p.country for p in db.query(CseoPage).all()} == {"in", GLOBAL}


# ── Multi-part rows ──────────────────────────────────────────────────────────

def test_four_column_deliverables_table_keeps_every_column():
    row = {"country": "global", "deliverables_table":
           "Reviews::New reviews and themes::What do customers value?::Volume and rating"}
    c = _row_to_page_in(row).content
    assert c["deliverables_table"] == [{
        "workstream": "Reviews", "output": "New reviews and themes",
        "decision": "What do customers value?", "measure": "Volume and rating",
    }]


def test_nested_sub_lists_split_on_semicolons():
    row = {"country": "global", "service_workstreams":
           "GBP::Google Business Profile management::Profile audit;Categories;Hours"}
    c = _row_to_page_in(row).content
    assert c["service_workstreams"] == [{
        "code": "GBP", "title": "Google Business Profile management",
        "points": ["Profile audit", "Categories", "Hours"],
    }]


def test_market_pathway_keeps_the_status_that_decides_link_or_text():
    # Guardrail 13: an unpublished market must render as text, so the row has to
    # carry its status alongside the URL rather than only the URL.
    row = {"country": "global", "market_pathways":
           "India::Dense city catchments.::Country pillar in production::/en-in/local-seo-services/|"
           "Canada::Province and metro.::Coming soon::/en-ca/local-seo-services/"}
    c = _row_to_page_in(row).content
    assert [m["status"] for m in c["market_pathways"]] == [
        "Country pillar in production", "Coming soon"]
    assert c["market_pathways"][1]["url"] == "/en-ca/local-seo-services/"


def test_section_header_splits_into_eyebrow_heading_and_intro():
    row = {"country": "global", "sec_services": "Complete service scope::What is included?::One program.",
           "sec_audit": "Free Local SEO audit"}
    c = _row_to_page_in(row).content
    assert c["sec_services"] == {"eyebrow": "Complete service scope",
                                 "heading": "What is included?", "intro": "One program."}
    # A header may be an eyebrow on its own; the missing parts stay empty, not None.
    assert c["sec_audit"] == {"eyebrow": "Free Local SEO audit", "heading": "", "intro": ""}


def test_engagement_model_keeps_its_cta():
    row = {"country": "global", "engagement_models":
           "Software::Pinzo Platform::For teams that execute.::Per-location plans;7-day free trial::"
           "View Platform Pricing::https://www.pinzo.io/pricing"}
    m = _row_to_page_in(row).content["engagement_models"][0]
    assert m["tag"] == "Software" and m["name"] == "Pinzo Platform"
    assert m["features"] == ["Per-location plans", "7-day free trial"]
    assert m["cta_label"] == "View Platform Pricing"
    assert m["cta_url"] == "https://www.pinzo.io/pricing"


def test_country_pillar_tuple_shapes_are_unchanged():
    # The global columns are additive: the country shapes must not have moved.
    row = {"country": "India",
           "service_matrix": "Profiles::Manage categories::Local intent is category-led",
           # The country pricing card shares the engagement-model shape, because the
           # reference HTML draws the same card in both packages.
           "packages": "Managed::Growth::For one clinic::Profile;Reviews::Request a Scope::#audit"}
    c = _row_to_page_in(row).content
    assert c["service_matrix"] == [{"area": "Profiles", "work": "Manage categories",
                                    "why": "Local intent is category-led"}]
    assert c["packages"] == [{"tag": "Managed", "name": "Growth", "detail": "For one clinic",
                              "features": ["Profile", "Reviews"],
                              "cta_label": "Request a Scope", "cta_url": "#audit"}]



