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
from app.api import lpseo as lpseo_api
from app.api.lpseo import admin_import_pages
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
