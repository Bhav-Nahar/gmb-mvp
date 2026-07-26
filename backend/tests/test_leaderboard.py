"""Tests for the Leaderboard API endpoints."""
import datetime
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
from app.api.deps import get_current_user
import app.api.deps as deps_module
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.location import Location
from app.models.organization import Organization

@pytest.fixture
def client(fake_admin_user, db, monkeypatch):
    # Patch RBAC
    monkeypatch.setattr(deps_module, "get_user_location_ids", lambda user, db: None)
    
    from app.api.deps import check_csrf, check_billing_lock
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: fake_admin_user
    app.dependency_overrides[check_csrf] = lambda: None
    app.dependency_overrides[check_billing_lock] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()

def _setup_org_and_locations(db):
    # active: these tests exercise leaderboard logic and must not trip the
    # env-dependent onboarding/billing gates (CARD_REQUIRED_ONBOARDING).
    org = Organization(id=1, name="Test Org", subscription_status="active")
    loc1 = Location(id=1, organization_id=1, google_location_id="loc_1", location_name="Loc 1", billing_status="active")
    loc2 = Location(id=2, organization_id=1, google_location_id="loc_2", location_name="Loc 2", billing_status="active")
    loc3 = Location(id=3, organization_id=1, google_location_id="loc_3", location_name="Loc 3", billing_status="active")
    db.add(org)
    db.add_all([loc1, loc2, loc3])
    db.commit()

def _add_snapshot(db, loc_id, period, rank=None, rating_raw=4.5, is_eligible=True):
    snap = LeaderboardSnapshot(
        organization_id=1,
        location_id=loc_id,
        period_label=period,
        period_start=datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc),
        period_end=datetime.datetime(2026, 6, 30, tzinfo=datetime.timezone.utc),
        snapshot_version="v1",
        is_eligible=is_eligible,
        composite_score=90.0 if is_eligible else None,
        rank=rank,
        average_rating_raw=rating_raw,
        rating_score=90.0,
        streak_count=1 if rank == 1 else 0
    )
    db.add(snap)
    db.commit()
    return snap

def test_get_leaderboard_no_data(client, db):
    _setup_org_and_locations(db)
    resp = client.get("/api/v1/leaderboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_data"] is False
    assert len(data["eligible_locations"]) == 0

def test_get_leaderboard_with_data(client, db):
    _setup_org_and_locations(db)
    _add_snapshot(db, 1, "2026-06", rank=1, rating_raw=5.0)
    _add_snapshot(db, 2, "2026-06", rank=2, rating_raw=4.0)
    _add_snapshot(db, 3, "2026-06", rank=None, is_eligible=False)
    
    resp = client.get("/api/v1/leaderboard?period=2026-06")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_data"] is True
    assert data["period"] == "2026-06"
    assert len(data["eligible_locations"]) == 2
    assert len(data["ineligible_locations"]) == 1
    
    # Benchmarks
    assert data["organization_benchmark"]["average_rating_raw"] == 4.5
    
    # Awards
    assert data["awards"]["top_performer"]["location_id"] == 1
    assert data["awards"]["highest_rated"]["location_id"] == 1

def test_get_leaderboard_rbac(client, db, monkeypatch):
    _setup_org_and_locations(db)
    _add_snapshot(db, 1, "2026-06", rank=1)
    _add_snapshot(db, 2, "2026-06", rank=2)
    
    # Restrict access to location 1 only
    monkeypatch.setattr(deps_module, "get_user_location_ids", lambda user, db: [1])
    
    resp = client.get("/api/v1/leaderboard?period=2026-06")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["eligible_locations"]) == 1
    assert data["eligible_locations"][0]["location_id"] == 1

def test_get_periods(client, db):
    _setup_org_and_locations(db)
    _add_snapshot(db, 1, "2026-05", rank=1)
    _add_snapshot(db, 1, "2026-06", rank=1)
    
    resp = client.get("/api/v1/leaderboard/periods")
    assert resp.status_code == 200
    assert resp.json() == ["2026-06", "2026-05"]

def test_get_history(client, db):
    _setup_org_and_locations(db)
    _add_snapshot(db, 1, "2026-05", rank=2)
    _add_snapshot(db, 1, "2026-06", rank=1)
    
    resp = client.get("/api/v1/leaderboard/1/history")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["period_label"] == "2026-05"
    assert data[1]["period_label"] == "2026-06"

def test_get_explain_first_period(client, db):
    _setup_org_and_locations(db)
    _add_snapshot(db, 1, "2026-06", rank=1)
    
    resp = client.get("/api/v1/leaderboard/1/explain")
    assert resp.status_code == 200
    data = resp.json()
    assert data["previous_period"] is None
    assert data["deltas"] is None

def test_get_explain_with_history(client, db):
    _setup_org_and_locations(db)
    # Previous
    snap_prev = _add_snapshot(db, 1, "2026-05", rank=2, rating_raw=4.0)
    snap_prev.rating_score = 80.0
    db.commit()
    
    # Current
    snap_curr = _add_snapshot(db, 1, "2026-06", rank=1, rating_raw=4.5)
    snap_curr.rating_score = 90.0
    snap_curr.rank_movement = 1
    db.commit()
    
    resp = client.get("/api/v1/leaderboard/1/explain")
    assert resp.status_code == 200
    data = resp.json()
    assert data["previous_period"] == "2026-05"
    assert data["from_rank"] == 2
    assert data["to_rank"] == 1
    assert data["deltas"]["average_rating_raw"]["change"] == 0.5
    
    # 90.0 - 80.0 = 10.0 change. average_rating weight is 0.30
    # 10.0 * 0.30 = 3.0 contribution
    assert data["score_contribution_deltas"]["average_rating"] == 3.0

def test_export_csv(client, db):
    _setup_org_and_locations(db)
    _add_snapshot(db, 1, "2026-06", rank=1)
    
    resp = client.get("/api/v1/leaderboard/export?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "Location Name" in resp.text
    assert "Loc 1" in resp.text

def test_get_history_forbidden(client, db, monkeypatch):
    _setup_org_and_locations(db)
    _add_snapshot(db, 1, "2026-06", rank=1)
    
    monkeypatch.setattr(deps_module, "get_user_location_ids", lambda user, db: [2])
    
    resp = client.get("/api/v1/leaderboard/1/history")
    assert resp.status_code == 403

def test_get_history_not_found(client, db):
    _setup_org_and_locations(db)
    
    resp = client.get("/api/v1/leaderboard/999/history")
    assert resp.status_code == 404

def test_get_explain_forbidden(client, db, monkeypatch):
    _setup_org_and_locations(db)
    _add_snapshot(db, 1, "2026-06", rank=1)
    
    monkeypatch.setattr(deps_module, "get_user_location_ids", lambda user, db: [2])
    
    resp = client.get("/api/v1/leaderboard/1/explain")
    assert resp.status_code == 403

def test_get_explain_not_found(client, db):
    _setup_org_and_locations(db)
    
    resp = client.get("/api/v1/leaderboard/999/explain")
    assert resp.status_code == 404

def test_generate_leaderboard_success(client, db):
    _setup_org_and_locations(db)
    from unittest.mock import patch
    with patch("app.services.leaderboard_service.LeaderboardService.generate_snapshots_for_period") as mock_gen:
        mock_gen.return_value = []
        resp = client.post("/api/v1/leaderboard/generate?period=2026-06")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        mock_gen.assert_called_once()

def test_generate_leaderboard_forbidden(client, db, fake_admin_user):
    from types import SimpleNamespace
    from app.api.deps import get_current_user
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        email="viewer@example.com",
        organization_id=1,
        role="Viewer",
        is_active=True,
        viewer_scope=None
    )
    try:
        resp = client.post("/api/v1/leaderboard/generate?period=2026-06")
        assert resp.status_code == 403
    finally:
        # Restore fixture overrides
        app.dependency_overrides[get_current_user] = lambda: fake_admin_user



