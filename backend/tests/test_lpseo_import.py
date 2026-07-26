"""Covers the lpSEO bulk-import upsert path — the money/SEO logic hardened in this
work: preload dedup, cross-country slug protection, and revalidating any row that
IS or WAS published. Drives the endpoint function directly against the in-memory
SQLite `db` fixture; revalidation is stubbed so nothing hits the network.
"""
import csv
import io
from app.api import lpseo as lpseo_api
from app.api.lpseo import admin_import_pages
from app.models.lpseo_page import LpseoPage, LpseoPageStatus


class _FakeUpload:
    """Minimal stand-in for FastAPI's UploadFile: .file.read() + .filename."""
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


def _run_import(db, header, rows, monkeypatch):
    """Run the import, returning (result, touched) where touched is the list of
    entries handed to revalidation (stubbed to capture, never POSTs)."""
    captured = {"touched": []}
    monkeypatch.setattr(lpseo_api, "trigger_bulk_lpseo_revalidation",
                        lambda entries: captured.__setitem__("touched", entries))
    result = admin_import_pages(file=_FakeUpload(_csv_bytes(header, rows), "import.csv"), db=db, _=None)
    return result, captured["touched"]


def _seed(db, **kw):
    page = LpseoPage(
        industry_slug=kw.get("industry_slug", "x"), city_slug=kw.get("city_slug", "y"),
        industry_label=kw.get("industry_label", "X"), city_label=kw.get("city_label", "Y"),
        meta_title="t", meta_description="d", h1="h", **{k: v for k, v in kw.items()
        if k in ("slug", "country", "status")},
    )
    db.add(page)
    db.commit()
    return page


def test_import_creates_with_defaults_and_revalidates(db, monkeypatch):
    # quality_score is required to import a NEW page as published (publish gate).
    result, touched = _run_import(
        db, ["industry_label", "city_label", "country", "status", "quality_score"],
        [["Plumbers", "Delhi", "in", "published", "85"]], monkeypatch,
    )
    assert result["created"] == 1 and result["updated"] == 0 and result["failed"] == 0
    page = db.query(LpseoPage).filter(LpseoPage.slug == "plumbers-in-delhi").one()
    assert page.country == "in" and page.status == LpseoPageStatus.PUBLISHED.value
    assert page.h1 and page.meta_title  # auto-filled defaults
    assert any(t["slug"] == "plumbers-in-delhi" for t in touched)  # published -> revalidated


def test_import_new_published_page_requires_quality_score(db, monkeypatch):
    # An unscored row can't create a page straight to published — null quality_score
    # would bypass the >=80 index gate and put a thin page in front of Google.
    result, touched = _run_import(
        db, ["industry_label", "city_label", "country", "status"],
        [["Plumbers", "Delhi", "in", "published"]], monkeypatch,
    )
    assert result["failed"] == 1 and result["created"] == 0
    assert touched == []


def test_import_rejects_cross_country_slug(db, monkeypatch):
    # A US page already owns the country-agnostic slug dentists-in-springfield.
    _seed(db, slug="dentists-in-springfield", country="us", status=LpseoPageStatus.PUBLISHED.value,
          industry_label="Dentists", industry_slug="dentists", city_label="Springfield", city_slug="springfield")
    result, _touched = _run_import(
        db, ["industry_label", "city_label", "country"],
        [["Dentists", "Springfield", "in"]], monkeypatch,  # same slug, different market
    )
    assert result["failed"] == 1 and result["created"] == 0 and result["updated"] == 0
    # Two guards now cover this and either may fire first: the city/country drift
    # check (parse phase) and the cross-market slug check (upsert phase). The
    # contract is that the row is REFUSED, not which message explains it.
    err = next(r for r in result["results"] if r["action"] == "error")["error"]
    assert "across markets" in err or "already published under country" in err
    # The live US page must be untouched, not silently repointed to India.
    assert db.query(LpseoPage).filter(LpseoPage.slug == "dentists-in-springfield").one().country == "us"


def test_import_unpublish_flip_still_revalidates(db, monkeypatch):
    _seed(db, slug="cafes-in-pune", country="in", status=LpseoPageStatus.PUBLISHED.value,
          industry_label="Cafes", industry_slug="cafes", city_label="Pune", city_slug="pune")
    result, touched = _run_import(
        db, ["industry_label", "city_label", "country", "status"],
        [["Cafes", "Pune", "in", "draft"]], monkeypatch,
    )
    assert result["updated"] == 1
    assert db.query(LpseoPage).filter(LpseoPage.slug == "cafes-in-pune").one().status == LpseoPageStatus.DRAFT.value
    # WAS published -> must revalidate so the stale indexable HTML gets purged.
    assert any(t["slug"] == "cafes-in-pune" for t in touched)


def test_import_in_file_duplicate_upserts_last_wins(db, monkeypatch):
    result, touched = _run_import(
        db, ["industry_label", "city_label", "country", "status"],
        [["Salons", "Jaipur", "in", "draft"], ["Salons", "Jaipur", "in", "published"]], monkeypatch,
    )
    assert result["created"] == 1 and result["updated"] == 1 and result["failed"] == 0
    pages = db.query(LpseoPage).filter(LpseoPage.slug == "salons-in-jaipur").all()
    assert len(pages) == 1 and pages[0].status == LpseoPageStatus.PUBLISHED.value
    assert any(t["slug"] == "salons-in-jaipur" for t in touched)


def test_import_accepts_content_package_header(db, monkeypatch):
    """The industry x city content package ships its CSV on the GBP-management
    header. It must import unedited: aliased columns land on the keys the template
    renders, and the package's `ready_for_upload_noindex` state means draft+noindex
    rather than a hard row failure."""
    header = ["slug", "country", "industry_label", "city_label", "index_status",
              "quality_score", "status", "why_matters_body", "why_matters_points",
              "city_visibility_body", "solutions", "problems", "monthly_workflow",
              "gbp_services", "gbp_categories", "faqs", "url", "schema_type"]
    row = [
        "dentists-in-mumbai", "India", "Dentists", "Mumbai", "noindex", "96",
        "ready_for_upload_noindex",
        "Patients use a mix of location, treatment and urgency queries.",
        "Locality searches::Patients search dentist near me|Treatment searches::Patients compare implants",
        "Mumbai searches are shaped by locality and travel time.",
        "Google Maps and GBP::Improve categories, services and photos|Technical SEO::Fix crawlability",
        "Weak Maps coverage::Only part of the catchment is reached",
        "Week 1::Review rankings and profiles|Week 2::Complete GBP and website actions",
        "Dental implants|Root canal treatment",
        "Dentist|Dental Clinic",  # GBP-only column: parses, intentionally not stored
        "What is local SEO?::It helps nearby patients find the clinic.",
        "/en-in/local-seo-services/dentists-in-mumbai", "Organization,FAQPage",
    ]
    result, touched = _run_import(db, header, [row], monkeypatch)

    assert result["created"] == 1 and result["failed"] == 0
    page = db.query(LpseoPage).filter(LpseoPage.slug == "dentists-in-mumbai").one()
    assert page.country == "in"
    # Publishing-workflow status is read as the launch gate it is.
    assert page.status == LpseoPageStatus.DRAFT.value and page.index_status == "noindex"
    assert not touched  # never published -> no live URL to purge

    c = page.content
    assert c["intent_body"].startswith("Patients use a mix")
    assert c["search_intents"][0] == {"title": "Locality searches", "detail": "Patients search dentist near me"}
    assert len(c["search_intents"]) == 2
    assert c["city_body"].startswith("Mumbai searches")
    assert c["services"][0]["channel"] == "Google Maps and GBP"
    assert c["services"][0]["work"].startswith("Improve categories")
    assert c["audit_checklist"] == [{"title": "Weak Maps coverage", "detail": "Only part of the catchment is reached"}]
    assert [w["title"] for w in c["workflow_weeks"]] == ["Week 1", "Week 2"]
    assert c["topics"] == ["Dental implants", "Root canal treatment"]
    assert c["faqs"] == [{"q": "What is local SEO?", "a": "It helps nearby patients find the clinic."}]
    # Aliased source names never leak into the stored content, and GBP-listing
    # columns this page renders no section for are dropped rather than stored.
    for dead in ("why_matters_points", "solutions", "problems", "gbp_categories", "url"):
        assert dead not in c


def test_import_lpseo_native_columns_win_over_aliases(db, monkeypatch):
    # A purpose-built lpSEO CSV must never be shadowed by an alias in the same row.
    result, _touched = _run_import(
        db, ["industry_label", "city_label", "city_body", "city_visibility_body"],
        [["Cafes", "Pune", "Native copy", "Package copy"]], monkeypatch,
    )
    assert result["created"] == 1
    page = db.query(LpseoPage).filter(LpseoPage.slug == "cafes-in-pune").one()
    assert page.content["city_body"] == "Native copy"


# ── The shipped dentists x Mumbai leaf package ───────────────────────────────


def test_admin_create_syncs_page_type_column_with_content(db, monkeypatch):
    """POST /admin/lpseo used to leave page_type at its "leaf" default, so a pillar
    hand-created in the admin UI became a drip candidate the moment it was published."""
    from app.api.lpseo import LpseoPageIn, admin_create_page
    monkeypatch.setattr(lpseo_api, "trigger_bulk_lpseo_revalidation", lambda *_a, **_k: None)

    admin_create_page(body=LpseoPageIn(industry_label="Dentists", city_label="",
                                       country="in", content={"page_type": "industry_pillar"}),
                      db=db, _=None)
    admin_create_page(body=LpseoPageIn(industry_label="Dentists", city_label="Mumbai",
                                       country="in", content={}), db=db, _=None)

    assert db.query(LpseoPage).filter(LpseoPage.slug == "dentists").one().page_type == "industry_pillar"
    assert db.query(LpseoPage).filter(LpseoPage.slug == "dentists-in-mumbai").one().page_type == "leaf"


def test_import_new_draft_is_not_revalidated(db, monkeypatch):
    result, touched = _run_import(
        db, ["industry_label", "city_label", "country", "status"],
        [["Gyms", "Surat", "in", "draft"]], monkeypatch,
    )
    assert result["created"] == 1
    # Never published, no live URL to purge -> stays out of the revalidation set.
    assert not any(t["slug"] == "gyms-in-surat" for t in touched)


def test_import_rejects_a_city_from_the_wrong_country(db, monkeypatch):
    """The bug this exists for: 1,034 pages for Bangkok, Jakarta, Riyadh and friends
    shipped under country='in', so they served on India's locale and hreflang for
    months. Nothing validated it."""
    result, _ = _run_import(
        db, ["industry_label", "city_label", "city_slug", "country"],
        [["Cafes", "Bangkok", "bangkok", "in"]], monkeypatch,
    )
    assert result["failed"] == 1 and result["created"] == 0
    err = next(r for r in result["results"] if r["action"] == "error")["error"]
    assert "'th'" in err and "'in'" in err
    # ...and the same row lands fine once the country is right.
    ok, _ = _run_import(
        db, ["industry_label", "city_label", "city_slug", "country"],
        [["Cafes", "Bangkok", "bangkok", "th"]], monkeypatch,
    )
    assert ok["created"] == 1


def test_import_rejects_a_city_another_market_already_owns(db, monkeypatch):
    """The general check: no gazetteer needed. The first import defines the truth."""
    first, _ = _run_import(db, ["industry_label", "city_label", "country"],
                           [["Cafes", "Springfield", "us"]], monkeypatch)
    assert first["created"] == 1

    drift, _ = _run_import(db, ["industry_label", "city_label", "country"],
                           [["Salons", "Springfield", "gb"]], monkeypatch)
    assert drift["failed"] == 1
    assert "already published under country 'us'" in \
        next(r for r in drift["results"] if r["action"] == "error")["error"]


def test_guard_lets_a_pillar_through(db, monkeypatch):
    """An industry pillar's city_label is the COUNTRY name ("India"), which is not a
    city at all. It must not be caught by the city check."""
    res, _ = _run_import(
        db, ["industry_label", "city_label", "country", "page_type", "quality_score"],
        [["Dentists", "", "in", "industry_pillar", "100"]], monkeypatch,
    )
    assert res["created"] == 1 and res["failed"] == 0
