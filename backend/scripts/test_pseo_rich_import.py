"""Test CSV import of the per-page content fields the importer supports:
answer_block (text) and the tuple cells review_examples + related_pages.

Auto-generated / near-constant-default fields (internal_links, comparison,
audit_checklist, og_image) are intentionally NOT CSV columns.

Run inside the backend container:
    docker exec -e PYTHONPATH=/app -w /app gmb_backend python scripts/test_pseo_rich_import.py
"""
from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import superadmin_required, check_csrf

app.dependency_overrides[superadmin_required] = lambda: None
app.dependency_overrides[check_csrf] = lambda: None
client = TestClient(app)
SLUG = "rich-test-in-testville"

CSV = (
    "industry_label,city_label,status,quality_score,answer_block,review_examples,related_pages\n"
    "Rich Test,Testville,published,90,"
    "This is the answer block.,"
    "Great designs and honest pricing :: Thank you for trusting us | Fast resizing :: Glad it was quick,"
    "Jewellery in Delhi :: /en-in/gbp-management/jewellery-stores-in-delhi | Pricing :: /pricing\n"
)

# clean slate
for p in client.get(f"/api/v1/admin/pseo?q={SLUG}").json()["pages"]:
    client.delete(f"/api/v1/admin/pseo/{p['id']}")

r = client.post("/api/v1/admin/pseo/import", files={"file": ("rich.csv", CSV, "text/csv")})
assert r.status_code == 200, r.text
assert r.json()["created"] == 1 and r.json()["failed"] == 0, r.json()

c = client.get(f"/api/v1/public/pseo/{SLUG}").json()["content"]

assert c["answer_block"] == "This is the answer block.", c.get("answer_block")
assert c["review_examples"] == [
    {"review": "Great designs and honest pricing", "reply": "Thank you for trusting us"},
    {"review": "Fast resizing", "reply": "Glad it was quick"},
], c.get("review_examples")
assert c["related_pages"] == [
    {"anchor": "Jewellery in Delhi", "url": "/en-in/gbp-management/jewellery-stores-in-delhi"},
    {"anchor": "Pricing", "url": "/pricing"},
], c.get("related_pages")
# excluded fields must NOT come from CSV
for excluded in ("internal_links", "comparison", "audit_checklist", "og_image"):
    assert excluded not in c, f"{excluded} should not be importable via CSV"

# cleanup
for p in client.get(f"/api/v1/admin/pseo?q={SLUG}").json()["pages"]:
    client.delete(f"/api/v1/admin/pseo/{p['id']}")
print("ALL RICH IMPORT TESTS PASSED")
