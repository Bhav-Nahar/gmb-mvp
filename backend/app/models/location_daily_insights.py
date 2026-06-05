from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.db.session import Base

class LocationDailyInsight(Base):
    __tablename__ = "location_daily_insights"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    provider = Column(String, nullable=False, default="gbp")

    # Visibility Metrics
    profile_views = Column(Integer, default=0, nullable=False)
    search_impressions = Column(Integer, default=0, nullable=False)
    maps_views = Column(Integer, default=0, nullable=False)

    # Engagement Metrics
    phone_calls = Column(Integer, default=0, nullable=False)
    website_clicks = Column(Integer, default=0, nullable=False)
    direction_requests = Column(Integer, default=0, nullable=False)

    # Search Intent Metrics
    searches_direct = Column(Integer, default=0, nullable=False)
    searches_indirect = Column(Integer, default=0, nullable=False)
    searches_chain = Column(Integer, default=0, nullable=False)

    # Reviews & Sentiment Metrics
    reviews_received = Column(Integer, default=0, nullable=False)
    avg_rating = Column(Float, nullable=True)
    positive_review_count = Column(Integer, default=0, nullable=False)
    neutral_review_count = Column(Integer, default=0, nullable=False)
    negative_review_count = Column(Integer, default=0, nullable=False)
    avg_sentiment_score = Column(Float, nullable=True)  # Range: -1.0 (all negative) to 1.0 (all positive)

    # Response & SLA Metrics
    response_rate = Column(Float, default=0.0, nullable=False)  # Percentage of reviews replied to (0.0 to 100.0)
    avg_response_time_hours = Column(Float, nullable=True)      # Average time to reply in hours

    # Derived Rate Metrics
    click_through_rate = Column(Float, nullable=True)          # (website_clicks / profile_views) * 100
    call_conversion_rate = Column(Float, nullable=True)        # (phone_calls / profile_views) * 100
    direction_conversion_rate = Column(Float, nullable=True)   # (direction_requests / profile_views) * 100

    # Relationships
    location = relationship("Location", back_populates="daily_insights")
    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint("location_id", "date", "provider", name="uq_location_daily_provider"),
        Index("idx_insights_org_date", "organization_id", "date"),
        Index("idx_insights_location_date", "location_id", "date"),
        Index("idx_insights_org_date_loc", "organization_id", "date", "location_id"),
        Index("idx_insights_provider", "provider"),
    )
