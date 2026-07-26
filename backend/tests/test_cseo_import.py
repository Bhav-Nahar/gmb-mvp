"""Country pillar import. The interesting parts are the separator scheme the package
uses (guardrail 14: "||" between FAQ items, "|" between list items, "::" between a
label and its value), the three-part rows, and the staging state mapping.
"""
import csv
import io
from app.api import cseo as cseo_api
from app.api.cseo import admin_import, _row_to_page_in, _apply_defaults
from app.models.cseo_page import CseoPage, CseoPageStatus


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


