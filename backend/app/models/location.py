from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Float, Index, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.db.session import Base

class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    google_account_id = Column(String, nullable=True) # Example: "accounts/12345"
    google_location_id = Column(String, index=True, nullable=False)  # Example: "locations/12345"
    location_name = Column(String, nullable=False)
    primary_category = Column(String, nullable=True)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    website = Column(String, nullable=True)
    description = Column(String, nullable=True)
    business_hours = Column(JSONB, nullable=True)
    average_rating = Column(Float, nullable=True) # Average rating out of 5 (e.g. 4.5)
    total_reviews = Column(Integer, nullable=True)
    
    sync_status = Column(String, default="Pending", nullable=False)  # Pending, Synced, Failed
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    last_insights_sync_at = Column(DateTime(timezone=True), nullable=True)
    google_attributes = Column(JSONB, default=list, server_default='[]', nullable=False)
    draft_attributes = Column(JSONB, default=list, server_default='[]', nullable=False)
    last_google_sync = Column(DateTime(timezone=True), nullable=True)
    google_category_resource_name = Column(String, nullable=True) # Example: "categories/gcid:jewelry_store"
    google_attributes_stale = Column(Boolean, default=False, nullable=False)
    last_publish_hash = Column(String(64), nullable=True)
    last_published_at = Column(DateTime(timezone=True), nullable=True)
    attention_needed = Column(Boolean, default=False, nullable=False)
    attention_reason = Column(Text, nullable=True)
    attention_updated_at = Column(DateTime(timezone=True), nullable=True)
    sla_tracking_started_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="locations")
    sync_logs = relationship("SyncLog", back_populates="location", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="location", cascade="all, delete-orphan")
    post_variants = relationship("PostVariant", back_populates="location", cascade="all, delete-orphan")
    publish_jobs = relationship("PublishJob", back_populates="location", cascade="all, delete-orphan")
    edits = relationship("LocationEdit", back_populates="location", cascade="all, delete-orphan")
    daily_insights = relationship("LocationDailyInsight", back_populates="location", cascade="all, delete-orphan")
    __table_args__ = (
        Index("ix_locations_sla_tracking_started_at", "sla_tracking_started_at"),
    )
