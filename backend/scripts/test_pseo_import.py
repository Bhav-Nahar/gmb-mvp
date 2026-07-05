"""Smoke test for the pSEO import -> publish -> public-read flow.

Run inside the backend container:
    docker exec gmb_backend python scripts/test_pseo_import.py

Overrides the superadmin + CSRF gates (we're testing the pSEO logic, not auth),
imports one fully-populated doctors/Mumbai row via the real multipart endpoint,
then asserts the public payload contains every section.
"""
from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import superadmin_required, check_csrf

app.dependency_overrides[superadmin_required] = lambda: None
app.dependency_overrides[check_csrf] = lambda: None

client = TestClient(app)

CSV = """industry_label,city_label,status,badge,hero_sub,why_matters_body,why_matters_points,problems,solutions,gbp_categories,gbp_services,gbp_attributes,reviews_body,review_themes,example_review,example_reply,post_ideas,photo_checklist,city_visibility_body,neighborhoods,single_points,multi_points,monthly_workflow,faqs,final_heading,final_sub
Doctors & Clinics,Mumbai,published,GBP management for clinics,Keep every clinic profile complete and answer patient reviews with AI.,Patients pick clinics from Maps and reviews before they ever call.,Patients check reviews before booking | Maps drives walk-in appointments | Wrong timings lose patients,Missing services :: Google cannot match you to treatment searches | Unanswered reviews :: Patients read the silence,AI review replies :: Drafted in your tone and you approve | Profile audits :: Every missing field flagged per branch,Medical clinic | General practitioner,General consultation | Vaccination | Health checkup,Wheelchair accessible | Accepts new patients,Patient trust is built review by review. Pinzo drafts compliant replies you approve.,waiting time | staff behaviour | cleanliness,Very professional doctors and short waiting time.,Thank you for trusting our clinic. We are glad the visit was quick and smooth.,Health camp announcements | Seasonal vaccination drives | New doctor introductions,Clinic exterior with signage | Reception and waiting area | Consultation rooms,Mumbai patients compare 3-4 clinics on Maps before calling.,Andheri | Bandra | Powai,One dashboard for your profile and reviews | AI replies save an hour a day,Branch-wise health scores | Bulk posts across clinics,Audit :: Run the branch health audit | Fix :: Push missing services and photos | Reply :: Clear the review queue with AI | Report :: Send the monthly visibility report,Is Pinzo compliant for clinics? :: Yes. Replies never disclose patient information.,Grow your clinic visibility in Mumbai,See your clinic health score in minutes.
"""

# 0. Clean slate — drop the page if a previous run left it behind
existing = client.get("/api/v1/admin/pseo?q=doctors-clinics-in-mumbai").json()["pages"]
for p in existing:
    client.delete(f"/api/v1/admin/pseo/{p['id']}")

# 1. Import (create)
r = client.post("/api/v1/admin/pseo/import", files={"file": ("test.csv", CSV, "text/csv")})
assert r.status_code == 200, r.text
body = r.json()
assert body["created"] == 1 and body["failed"] == 0, body
slug = body["results"][0]["slug"]
assert slug == "doctors-clinics-in-mumbai", f"leaf slug scheme changed: {slug}"
print("imported:", slug)

# 2. Re-import same file -> update, not duplicate
r = client.post("/api/v1/admin/pseo/import", files={"file": ("test.csv", CSV, "text/csv")})
assert r.json()["updated"] == 1, r.json()
print("re-import updates in place: ok")

# 3. Public read
r = client.get(f"/api/v1/public/pseo/{slug}")
assert r.status_code == 200, r.text
page = r.json()
c = page["content"]
assert page["h1"].startswith("Google Business Profile Management for Doctors")
assert page["country"] == "in" and page["locale"] == "en-in", (page["country"], page["locale"])
assert page["index_status"] == "index"
assert len(c["problems"]) == 2 and c["problems"][0]["title"] == "Missing services"
assert len(c["faqs"]) == 1 and c["faqs"][0]["q"].startswith("Is Pinzo compliant")
assert c["monthly_workflow"][0] == {"title": "Audit", "detail": "Run the branch health audit"}
assert c["neighborhoods"] == ["Andheri", "Bandra", "Powai"]
print("public payload sections: ok")

# 4. Listing (sitemap source) + industry filter (hub source)
r = client.get("/api/v1/public/pseo")
assert any(p["slug"] == slug for p in r.json()["pages"])
r = client.get("/api/v1/public/pseo?industry=doctors-clinics")
hub = r.json()["pages"]
assert hub and all(p["industry_slug"] == "doctors-clinics" for p in hub), hub
print("public list + industry hub filter: ok")

# 5. Admin list + unpublish -> public 404
r = client.get("/api/v1/admin/pseo")
pid = next(p["id"] for p in r.json()["pages"] if p["slug"] == slug)
client.post(f"/api/v1/admin/pseo/{pid}/unpublish")
r = client.get(f"/api/v1/public/pseo/{slug}")
assert r.status_code == 404, "unpublished page must 404 publicly"
client.post(f"/api/v1/admin/pseo/{pid}/publish")
print("publish/unpublish gating: ok")

print("ALL PSEO TESTS PASSED —", slug)
