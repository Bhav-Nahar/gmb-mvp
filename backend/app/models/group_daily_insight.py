from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint, Index, text
from sqlalchemy.orm import relationship
from app.db.session import Base

class GroupDailyInsight(Base):
    __tablename__ = "group_daily_insights"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Polymorphic group mapping
    group_type = Column(String, nullable=False, index=True)  # REGION | CUSTOM_GROUP
    group_id = Column(Integer, nullable=False, index=True)
    
    date = Column(Date, nullable=False)
    provider = Column(String, nullable=False, default="gbp", server_default=text("'gbp'"))

    # Visibility Metrics
    profile_views = Column(Integer, default=0, nullable=False)
    search_impressions = Column(Integer, default=0, nullable=False)
    maps_views = Column(Integer, default=0, nullable=False)
    desktop_search_impressions = Column(Integer, default=0, nullable=False)
    mobile_search_impressions = Column(Integer, default=0, nullable=False)
    desktop_maps_impressions = Column(Integer, default=0, nullable=False)
    mobile_maps_impressions = Column(Integer, default=0, nullable=False)

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
    avg_sentiment_score = Column(Float, nullable=True)

    # Response & SLA Metrics
    response_rate = Column(Float, default=0.0, nullable=False)
    avg_response_time_hours = Column(Float, nullable=True)

    # Derived Rate Metrics
    click_through_rate = Column(Float, nullable=True)
    call_conversion_rate = Column(Float, nullable=True)
    direction_conversion_rate = Column(Float, nullable=True)
    
    # Ranking metrics
    avg_rank = Column(Float, nullable=True)
    solv = Column(Float, nullable=True)

    # Relationships
    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint("group_type", "group_id", "date", "provider", name="uq_group_daily_provider"),
        Index("idx_group_insights_org_date", "organization_id", "date"),
        Index("idx_group_insights_type_id_date", "group_type", "group_id", "date"),
    )
