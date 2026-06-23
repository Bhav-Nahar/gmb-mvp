from unittest.mock import MagicMock, patch
from datetime import date
from app.services.comparison_snapshot_service import ComparisonSnapshotService

@patch("app.services.comparison_snapshot_service.ComparisonCacheService")
def test_get_summary_city(mock_cache):
    mock_cache.get_cached_comparison.return_value = None
    
    db = MagicMock()
    # Mock db.execute().fetchone() return value
    mock_row = MagicMock()
    mock_row.profile_views = 100
    mock_row.search_impressions = 200
    mock_row.website_clicks = 10
    mock_row.phone_calls = 5
    mock_row.direction_requests = 12
    mock_row.avg_rating = 4.5
    mock_row.response_rate = 80.0
    db.execute.return_value.fetchone.return_value = mock_row

    filters = {
        "group_type": "CITY",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        "group_ids": ["Mumbai", "Delhi"]
    }
    
    result = ComparisonSnapshotService.get_summary(db, 1, filters)
    
    # Assert query was executed and results parsed correctly
    assert result["profile_views"] == 100
    assert result["avg_rating"] == 4.5
    assert db.execute.called
    
    # Verify cache write was called
    assert mock_cache.set_cached_comparison.called

@patch("app.services.comparison_snapshot_service.ComparisonCacheService")
def test_get_trends_region(mock_cache):
    mock_cache.get_cached_comparison.return_value = None
    
    db = MagicMock()
    # Mock db.execute().fetchall() return value
    mock_row1 = MagicMock()
    mock_row1.date = date(2026, 6, 1)
    mock_row1.views = 50
    mock_row2 = MagicMock()
    mock_row2.date = date(2026, 6, 2)
    mock_row2.views = 60
    db.execute.return_value.fetchall.return_value = [mock_row1, mock_row2]

    filters = {
        "group_type": "REGION",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        "group_ids": ["12", "34"]
    }
    
    result = ComparisonSnapshotService.get_trends(db, 1, filters)
    
    assert len(result) == 2
    assert result[0]["date"] == date(2026, 6, 1)
    assert result[0]["views"] == 50
    assert db.execute.called

@patch("app.services.comparison_snapshot_service.ComparisonCacheService")
def test_get_leaderboard_state(mock_cache):
    mock_cache.get_cached_comparison.return_value = None
    
    db = MagicMock()
    mock_row1 = MagicMock()
    mock_row1.name = "California"
    mock_row1.score = 500.0
    mock_row2 = MagicMock()
    mock_row2.name = "Texas"
    mock_row2.score = 450.0
    db.execute.return_value.fetchall.return_value = [mock_row1, mock_row2]

    filters = {
        "group_type": "STATE",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        "group_ids": []
    }
    
    result = ComparisonSnapshotService.get_leaderboard(db, 1, filters)
    
    assert len(result) == 2
    assert result[0]["name"] == "California"
    assert result[0]["score"] == 500.0
    assert db.execute.called
