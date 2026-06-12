import pytest
from sqlalchemy.orm import Session
from app.models.location import Location
from app.models.review import Review
from app.services.health_score_service import HealthScoreService
from datetime import datetime, timezone, timedelta

def test_health_score_perfect_profile(db: Session):
    # Setup perfect profile
    location = Location(
        organization_id=1,
        google_location_id="google_loc_123",
        location_name="Perfect Location",
        address="123 Main St",
        phone="555-1234",
        website="https://example.com",
        business_hours={"periods": []},
        description="A great place.",
        average_rating=4.8,
        total_reviews=150,
        last_published_at=datetime.now(timezone.utc) - timedelta(days=2)
    )
    db.add(location)
    db.commit()
    db.refresh(location)

    # Add 10 reviews, 10 replied (100% response rate)
    for i in range(10):
        db.add(Review(
            organization_id=1,
            location_id=location.id,
            google_review_id=f"r_{i}",
            reviewer_name="John",
            rating=5,
            is_replied=True
        ))
    db.commit()

    # We skip photos for this basic test, meaning max photo_score = 0.
    # Total potential without photos = 30(prof) + 25(rev) + 10(resp) + 20(post) = 85
    score = HealthScoreService.recalculate_health_score(db, location.id)
    
    assert score is not None
    assert score.score == 85
    assert score.potential_score == 100
    assert score.label == "Good" # 85 >= 75
    
    breakdown = score.breakdown
    assert breakdown["profile_completeness"]["score"] == 30
    assert breakdown["reviews_rating"]["score"] == 25
    assert breakdown["response_rate"]["score"] == 10
    assert breakdown["post_activity"]["score"] == 20
    assert breakdown["photos_media"]["score"] == 0

def test_health_score_critical_profile(db: Session):
    # Setup poor profile
    location = Location(
        organization_id=1,
        google_location_id="google_loc_456",
        location_name="Bad Location",
        # Missing most profile attributes
    )
    db.add(location)
    db.commit()
    db.refresh(location)

    score = HealthScoreService.recalculate_health_score(db, location.id)

    assert score is not None
    # 5 points for name + 10 points for response rate (full credit awarded when a
    # location has zero reviews, so new locations are not penalised).
    assert score.score == 15
    assert score.label == "Critical"
    
    # Recommendations should prioritize address and website
    recs = score.recommendations
    assert len(recs) > 0
    assert recs[0]["title"] in ["Add Website", "Add Address"]
