from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Boolean, UniqueConstraint, Index, func
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.enums import IneligibilityReason

class LeaderboardSnapshot(Base):
    __tablename__ = "leaderboard_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    period_label = Column(String, nullable=False, index=True)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    
    snapshot_version = Column(String(20), nullable=False)
    
    # Raw pre-normalization metrics
    average_rating_raw = Column(Float, nullable=True)
    response_rate_raw = Column(Float, nullable=True)
    health_score_raw = Column(Float, nullable=True)
    review_volume_raw = Column(Integer, nullable=True)
    engagement_growth_raw = Column(Float, nullable=True)
    review_velocity_raw = Column(Integer, nullable=True)
    
    # Normalized scores
    rating_score = Column(Float, nullable=True)
    response_rate_score = Column(Float, nullable=True)
    health_score_input = Column(Float, nullable=True)
    review_volume_score = Column(Float, nullable=True)
    engagement_growth_score = Column(Float, nullable=True)
    review_velocity_score = Column(Float, nullable=True)
    
    # Final composite score and ranking
    composite_score = Column(Float, nullable=True)
    rank = Column(Integer, nullable=True)
    previous_rank = Column(Integer, nullable=True)
    rank_movement = Column(Integer, nullable=True)
    
    # Eligibility and status
    is_eligible = Column(Boolean, nullable=False, default=True)
    ineligibility_reason = Column(String, nullable=True)  # Populated with values from IneligibilityReason enum
    
    streak_count = Column(Integer, nullable=False, default=0)
    most_improved_flag = Column(Boolean, nullable=False, default=False)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    organization = relationship("Organization", back_populates="leaderboard_snapshots")
    location = relationship("Location", back_populates="leaderboard_snapshots")

    __table_args__ = (
        UniqueConstraint("organization_id", "location_id", "period_label", name="uq_leaderboard_snapshot_period"),
        Index("idx_leaderboard_org_period_rank", "organization_id", "period_label", "rank"),
    )
