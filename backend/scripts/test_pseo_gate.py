"""Regression test for the pSEO quality-score index gate (audit item 6).

Run inside the backend container:
    docker exec gmb_backend python scripts/test_pseo_gate.py

Imports one published page at several quality scores and asserts the public
payload's index_status AND its sitemap-list membership both follow the >=80
approval gate. Busts the per-slug Redis cache between phases (bulk import does
not invalidate it) so each read is fresh.
"""
from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import superadmin_required, check_csrf
from app.api.pseo import _cache_key
from app.core.redis_client import get_redis

app.dependency_overrides[superadmin_required] = lambda: None
app.dependency_overrides[check_csrf] = lambda: None

client = TestClient(app)
SLUG = "gate-test-clinic-in-testcity"


def _import(quality_score):
    csv = (
        "industry_label,city_label,status,quality_score\n"
        f"Gate Test Clinic,TestCity,published,{quality_score}\n"
    )
    r = client.post("/api/v1/admin/pseo/import", files={"file": ("g.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    get_redis().delete(_cache_key(SLUG))  # import doesn't invalidate the per-slug cache


def _served_index_status():
    r = client.get(f"/api/v1/public/pseo/{SLUG}")
    assert r.status_code == 200, r.text
    return r.json()["index_status"]


def _in_sitemap_list():
    r = client.get("/api/v1/public/pseo")
    return any(p["slug"] == SLUG for p in r.json()["pages"])


def _cleanup():
    for p in client.get(f"/api/v1/admin/pseo?q={SLUG}").json()["pages"]:
        client.delete(f"/api/v1/admin/pseo/{p['id']}")


_cleanup()  # clean slate

_import(85)  # approved
assert _served_index_status() == "index"
assert _in_sitemap_list() is True
print("score 85  -> index + in sitemap   ok")

_import(70)  # below gate
assert _served_index_status() == "noindex"
assert _in_sitemap_list() is False
print("score 70  -> noindex + out of sitemap   ok")

_import("")  # no score -> ungated, stays live
assert _served_index_status() == "index"
assert _in_sitemap_list() is True
print("no score  -> ungated index   ok")

_import(80)  # boundary is inclusive
assert _served_index_status() == "index"
print("score 80  -> boundary index   ok")

_cleanup()
print("ALL PSEO GATE TESTS PASSED")
