"""Regression tests for GET /api/v1/locations/{id}/health-score.

These guard against the dependency-factory misuse bug where the endpoint called
`verify_location_access(location_id, current_user, db)` directly. Because
`verify_location_access` is a factory that accepts only `location_id` and returns
an inner dependency, that call raised `TypeError` and every request returned 500
(the frontend then fell back to a misleading "0 / doing great" state).

The tests mock the DB session and auth so they run without a live Postgres.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
from app.api.deps import staff_required, get_current_user, require_location_access, require_premium
import app.api.deps as deps_module
from app.services.health_score_service import HealthScoreService


def _stub_health_score(location_id: int = 42):
    return SimpleNamespace(
        location_id=location_id,
        # Current version, so the endpoint returns this row instead of recalculating
        # against the MagicMock db. Stale-version recalculation is its own concern.
        score_version=HealthScoreService.SCORE_VERSION,
        score=72,
        potential_score=100,
        label="Average",
        breakdown={
            "profile_completeness": {"score": 20, "max_score": 30},
            "reviews_rating": {"score": 20, "max_score": 25},
            "response_rate": {"score": 10, "max_score": 10},
            "post_activity": {"score": 15, "max_score": 20},
            "photos_media": {"score": 7, "max_score": 15},
        },
        recommendations=[
            {"title": "Add Website", "description": "Missing.", "potential_gain": 5, "target_tab": "profile"},
        ],
        last_recalculated_reason="manual",
        calculated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def client(fake_admin_user, monkeypatch):
    mock_db = MagicMock()
    # A precomputed row exists, so the endpoint returns it directly.
    mock_db.query.return_value.filter.return_value.first.return_value = _stub_health_score()

    # Location scope now runs in the require_location_access dependency, which calls
    # get_user_location_ids from the deps module. None => "no restriction".
    monkeypatch.setattr(deps_module, "get_user_location_ids", lambda user, db: None)

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[staff_required] = lambda: fake_admin_user
    app.dependency_overrides[get_current_user] = lambda: fake_admin_user
    # The endpoint reads location.id from the require_location_access dependency.
    app.dependency_overrides[require_location_access] = lambda: SimpleNamespace(id=42)
    # Billing gate is env-dependent (CARD_REQUIRED_ONBOARDING) and the MagicMock db
    # would feed it the health-score stub as an "org" — not what this test exercises.
    app.dependency_overrides[require_premium] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health_score_endpoint_returns_200_not_typeerror(client):
    """Before the fix this raised TypeError -> 500. It must now return 200."""
    resp = client.get("/api/v1/locations/42/health-score")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["location_id"] == 42
    assert body["score"] == 72
    assert body["label"] == "Average"
    assert body["breakdown"]["response_rate"]["score"] == 10
    assert body["recommendations"][0]["title"] == "Add Website"


def test_health_score_endpoint_forbidden_for_unscoped_location(fake_admin_user, monkeypatch):
    """A user whose location scope excludes the id must get 403, not a score."""
    mock_db = MagicMock()
    # Restrict the user to other locations only (42 excluded).
    monkeypatch.setattr(deps_module, "get_user_location_ids", lambda user, db: [1, 2, 3])

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[staff_required] = lambda: fake_admin_user
    app.dependency_overrides[get_current_user] = lambda: fake_admin_user
    try:
        resp = TestClient(app).get("/api/v1/locations/42/health-score")
        assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides.clear()
