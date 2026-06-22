from app.core import leaderboard_config

def test_leaderboard_config_weights():
    # If the file imports successfully, the assertion inside it 
    # (sum of LEADERBOARD_METRIC_WEIGHTS == 1.0) has passed.
    weights = leaderboard_config.LEADERBOARD_METRIC_WEIGHTS
    assert "average_rating" in weights
    assert "response_rate" in weights
    assert "health_score" in weights
    assert "review_volume" in weights
    assert "engagement_growth" in weights
    assert sum(weights.values()) == 1.0
