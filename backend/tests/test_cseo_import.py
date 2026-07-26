"""Country pillar import. The interesting parts are the separator scheme the package
uses (guardrail 14: "||" between FAQ items, "|" between list items, "::" between a
label and its value), the three-part rows, and the staging state mapping.
"""
import csv
import io
import os

from app.api import cseo as cseo_api
from app.api.cseo import admin_import, _row_to_page_in, _apply_defaults
from app.models.cseo_page import CseoPage, CseoPageStatus


PACKAGE_CSV = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "pinzo-india-country-pillar-package",
    "pinzo-india-country-pillar-import-ready.csv",
)


class _FakeUpload:
    def __init__(self, blob: bytes, filename: str):
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
    monkeypatch.setattr(cseo_api, "trigger_cseo_revalidation", lambda *_a, **_k: None)
    return admin_import(file=_FakeUpload(_csv_bytes(header, rows), "import.csv"), db=db, _=None)


def test_import_maps_staging_state_to_draft_and_noindex(db, monkeypatch):
    # The package ships robots_status "noindex,nofollow" and status "staging",
    # neither of which is a DB value. Both mean: not live yet.
    res = _run(db, ["country", "robots_status", "status", "quality_score"],
               [["India", "noindex,nofollow", "staging", "100"]], monkeypatch)
    assert res["created"] == 1 and res["failed"] == 0
    p = db.query(CseoPage).one()
    assert p.country == "in" and p.country_label == "India"
    assert p.status == CseoPageStatus.DRAFT.value and p.index_status == "noindex"
    assert p.quality_score == 100
    assert p.canonical_url == "https://www.pinzo.io/en-in/local-seo-services/"


def test_faqs_split_on_double_pipe_not_single(db, monkeypatch):
    # An answer containing a single pipe must not be torn into two FAQs.
    faqs = ("What is it?::A service.||How long?::It depends on competition.")
    res = _run(db, ["country", "faqs"], [["India", faqs]], monkeypatch)
    assert res["created"] == 1
    c = db.query(CseoPage).one().content
    assert c["faqs"] == [
        {"q": "What is it?", "a": "A service."},
        {"q": "How long?", "a": "It depends on competition."},
    ]


def test_three_part_rows_keep_their_third_column(db, monkeypatch):
    # Guardrail 6: every service row states what Pinzo manages AND why it matters
    # in that country. A two-part row would silently drop the "why".
    sm = "Google Business Profile::Categories and photos::Customers act from Maps|Technical SEO::Crawling and schema::Pages can be understood"
    bc = "Location-level audit::Specific gaps::A generic PDF"
    res = _run(db, ["country", "service_matrix", "buyer_checklist"], [["India", sm, bc]], monkeypatch)
    assert res["created"] == 1
    c = db.query(CseoPage).one().content
    assert c["service_matrix"][0] == {
        "area": "Google Business Profile", "work": "Categories and photos",
        "why": "Customers act from Maps"}
    assert len(c["service_matrix"]) == 2
    assert c["buyer_checklist"][0] == {
        "ask": "Location-level audit", "good": "Specific gaps", "warning": "A generic PDF"}


def test_packages_keep_their_tag_and_cta(db, monkeypatch):
    # The reference pricing card has a tag above the name and a CTA below the
    # features. A three-part row dropped both.
    pk = "Software::Pinzo Platform::For internal teams::Audits;Rank tracking;AI checks::View Current Pricing::https://www.pinzo.io/#pricing"
    _run(db, ["country", "packages"], [["India", pk]], monkeypatch)
    c = db.query(CseoPage).one().content
    assert c["packages"] == [{
        "tag": "Software", "name": "Pinzo Platform", "detail": "For internal teams",
        "features": ["Audits", "Rank tracking", "AI checks"],
        "cta_label": "View Current Pricing", "cta_url": "https://www.pinzo.io/#pricing"}]


def test_link_columns_keep_an_optional_descriptor(db, monkeypatch):
    # City and industry cards carry a one-line descriptor; plain link lists do
    # not. The descriptor must never leak into the href.
    links = ("Local SEO Services in Mumbai::/en-in/local-seo-services/mumbai/::Locality-led visibility.|"
             "Local SEO for Dentists::/en-in/local-seo-services/dentists/")
    _run(db, ["country", "city_hubs"], [["India", links]], monkeypatch)
    c = db.query(CseoPage).one().content
    assert c["city_hubs"] == [
        {"anchor": "Local SEO Services in Mumbai", "url": "/en-in/local-seo-services/mumbai/",
         "detail": "Locality-led visibility."},
        {"anchor": "Local SEO for Dentists", "url": "/en-in/local-seo-services/dentists/",
         "detail": ""},
    ]


def test_reimport_updates_the_same_country(db, monkeypatch):
    _run(db, ["country", "h1"], [["India", "First"]], monkeypatch)
    res = _run(db, ["country", "h1"], [["India", "Second"]], monkeypatch)
    assert res["created"] == 0 and res["updated"] == 1
    # One pillar per market, enforced by the unique country column.
    assert db.query(CseoPage).count() == 1
    assert db.query(CseoPage).one().h1 == "Second"


def test_new_published_pillar_requires_quality_score(db, monkeypatch):
    res = _run(db, ["country", "status"], [["India", "published"]], monkeypatch)
    assert res["failed"] == 1 and res["created"] == 0
    assert db.query(CseoPage).count() == 0


def test_country_is_required(db, monkeypatch):
    res = _run(db, ["country", "h1"], [["", "No country"]], monkeypatch)
    assert res["failed"] == 1 and res["created"] == 0


def test_index_status_defaults_to_noindex(db):
    # Opposite default to a leaf page: a pillar stays out of the index until the
    # launch checklist passes (guardrail 3).
    data = _apply_defaults(_row_to_page_in({"country": "India"}))
    assert data.index_status == "noindex"
    data = _apply_defaults(_row_to_page_in({"country": "India", "robots_status": "index,follow"}))
    assert data.index_status == "index"


def test_index_toggle_enforces_the_quality_gate(db, monkeypatch):
    """Guardrail 16 ends with "change robots only after final QA". The toggle is
    that switch, so it must refuse a pillar that has not cleared the score gate."""
    from fastapi import HTTPException
    from app.api.cseo import admin_set_index_status, IndexStatusIn

    monkeypatch.setattr(cseo_api, "trigger_cseo_revalidation", lambda *_a, **_k: None)
    _run(db, ["country", "quality_score"], [["India", "60"]], monkeypatch)
    p = db.query(CseoPage).one()

    try:
        admin_set_index_status(p.id, IndexStatusIn(index_status="index"), db=db, _=None)
        raise AssertionError("a sub-gate pillar must not become indexable")
    except HTTPException as e:
        assert e.status_code == 422
    assert db.query(CseoPage).one().index_status == "noindex"

    p.quality_score = 95
    db.commit()
    assert admin_set_index_status(p.id, IndexStatusIn(index_status="index"), db=db, _=None)["index_status"] == "index"
    # And back again, with no gate on removing a page from the index.
    assert admin_set_index_status(p.id, IndexStatusIn(index_status="noindex"), db=db, _=None)["index_status"] == "noindex"


def test_index_toggle_rejects_junk(db, monkeypatch):
    from fastapi import HTTPException
    from app.api.cseo import admin_set_index_status, IndexStatusIn

    _run(db, ["country", "quality_score"], [["India", "95"]], monkeypatch)
    p = db.query(CseoPage).one()
    try:
        admin_set_index_status(p.id, IndexStatusIn(index_status="follow"), db=db, _=None)
        raise AssertionError("expected a 400")
    except HTTPException as e:
        assert e.status_code == 400


# ── The shipped India package ────────────────────────────────────────────────
#
# CseoPillar renders a section only when its content arrived, so a column the
# package forgot is an invisible hole rather than a failure. These tests pin the
# copy recovered from the reference HTML during the package audit so a future
# regeneration of the CSV cannot quietly drop it again.

def _import_package(db, monkeypatch):
    monkeypatch.setattr(cseo_api, "trigger_cseo_revalidation", lambda *_a, **_k: None)
    with open(PACKAGE_CSV, "rb") as f:
        res = admin_import(file=_FakeUpload(f.read(), "import.csv"), db=db, _=None)
    assert res["failed"] == 0, res["results"]
    return db.query(CseoPage).one()


def test_india_package_imports_as_a_draft_and_noindex(db, monkeypatch):
    p = _import_package(db, monkeypatch)
    assert p.country == "in" and p.country_label == "India"
    # robots_status "noindex,nofollow" and status "staging": not live yet.
    assert p.status == CseoPageStatus.DRAFT.value and p.index_status == "noindex"
    assert p.quality_score == 100
    assert p.canonical_url == "https://www.pinzo.io/en-in/local-seo-services/"


def test_india_package_carries_every_section_the_reference_html_has(db, monkeypatch):
    c = _import_package(db, monkeypatch).content
    for key, n in [("search_behaviour", 4), ("service_matrix", 10), ("ranking_factors", 3),
                   ("city_hubs", 6), ("industry_hubs", 6), ("single_location_points", 4),
                   ("multi_location_points", 4), ("ai_entity_plan", 4), ("safeguards", 4),
                   ("monthly_deliverables", 8), ("roadmap_90_days", 3), ("buyer_checklist", 4),
                   ("packages", 3), ("proof_assets", 2), ("audit_checklist", 5),
                   ("faqs", 10)]:
        assert len(c.get(key, [])) == n, f"{key}: expected {n}, got {len(c.get(key, []))}"
    for key in ["hero_copy", "direct_question", "direct_answer", "package_copy", "package_note"]:
        assert c.get(key), key
    # Guardrail 8: at least 15 contextual internal links, nav and footer excluded.
    assert len(c["internal_links"]) >= 15


def test_india_multi_column_tables_are_not_flattened(db, monkeypatch):
    """Every rendered table column needs its own part in the cell. A two-part row
    leaves a header with an empty column under it."""
    c = _import_package(db, monkeypatch).content
    assert all(r["area"] and r["work"] and r["why"] for r in c["service_matrix"])
    assert all(r["ask"] and r["good"] and r["warning"] for r in c["buyer_checklist"])
    assert all(p["tag"] and p["name"] and p["detail"] and p["features"]
               and p["cta_label"] and p["cta_url"] for p in c["packages"])
    assert all(r["title"] and r["detail"] for r in c["search_behaviour"])
    assert all(r["title"] and r["detail"] for r in c["ai_entity_plan"])
    # The descriptor is a third part, so the href must stay a bare path.
    for l in c["city_hubs"] + c["industry_hubs"]:
        assert l["detail"] and l["url"].startswith("/en-in/") and "::" not in l["url"]
    # ...while the plain link list keeps two parts and an empty descriptor.
    assert all(l["anchor"] and l["url"] and not l["detail"] for l in c["internal_links"])


def test_india_package_has_no_forbidden_dash_characters(db, monkeypatch):
    """Guardrail 5: no U+2013, U+2014, U+2011 or U+2212 in visible copy."""
    p = _import_package(db, monkeypatch)

    def walk(v):
        if isinstance(v, str):
            yield v
        elif isinstance(v, dict):
            for x in v.values():
                yield from walk(x)
        elif isinstance(v, list):
            for x in v:
                yield from walk(x)

    for s in walk([p.content, p.h1, p.meta_title, p.meta_description]):
        assert not (set(s) & set("–—‑−")), repr(s)


def test_india_faq_text_survives_for_the_schema(db, monkeypatch):
    """The FAQPage schema is generated from the visible copy, so the answers must
    arrive intact: no "::" left over, and the primary keyword in one question."""
    faqs = _import_package(db, monkeypatch).content["faqs"]
    assert faqs[0]["q"] == "What are Local SEO services in India?"
    assert all(f["q"] and f["a"] and "::" not in f["a"] for f in faqs)
    assert sum("local SEO services in India" in f["q"] or "Local SEO services in India" in f["q"]
               for f in faqs) >= 1
