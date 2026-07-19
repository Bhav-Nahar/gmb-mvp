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
    result, touched = _run_import(
        db, ["industry_label", "city_label", "country", "status"],
        [["Plumbers", "Delhi", "in", "published"]], monkeypatch,
    )
    assert result["created"] == 1 and result["updated"] == 0 and result["failed"] == 0
    page = db.query(LpseoPage).filter(LpseoPage.slug == "plumbers-in-delhi").one()
    assert page.country == "in" and page.status == LpseoPageStatus.PUBLISHED.value
    assert page.h1 and page.meta_title  # auto-filled defaults
    assert any(t["slug"] == "plumbers-in-delhi" for t in touched)  # published -> revalidated


def test_import_rejects_cross_country_slug(db, monkeypatch):
    # A US page already owns the country-agnostic slug dentists-in-springfield.
    _seed(db, slug="dentists-in-springfield", country="us", status=LpseoPageStatus.PUBLISHED.value,
          industry_label="Dentists", industry_slug="dentists", city_label="Springfield", city_slug="springfield")
    result, _touched = _run_import(
        db, ["industry_label", "city_label", "country"],
        [["Dentists", "Springfield", "in"]], monkeypatch,  # same slug, different market
    )
    assert result["failed"] == 1 and result["created"] == 0 and result["updated"] == 0
    err = next(r for r in result["results"] if r["action"] == "error")
    assert "across markets" in err["error"]
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


def test_import_new_draft_is_not_revalidated(db, monkeypatch):
    result, touched = _run_import(
        db, ["industry_label", "city_label", "country", "status"],
        [["Gyms", "Surat", "in", "draft"]], monkeypatch,
    )
    assert result["created"] == 1
    # Never published, no live URL to purge -> stays out of the revalidation set.
    assert not any(t["slug"] == "gyms-in-surat" for t in touched)
