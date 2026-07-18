from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Float, Index, Boolean, Text, text
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
    city = Column(String, index=True, nullable=True)
    state = Column(String, index=True, nullable=True)
    country = Column(String, nullable=True)
    postal_code = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    website = Column(String, nullable=True)
    description = Column(String, nullable=True)
    business_hours = Column(JSONB, nullable=True)
    average_rating = Column(Float, nullable=True) # Average rating out of 5 (e.g. 4.5)
    total_reviews = Column(Integer, nullable=True)
    
    # Billing state for per-location quota enforcement.
    #   'active'          -> counts against location_quota, fully processed
    #   'pending_payment' -> locked: visible but excluded from all paid processing
    #                        until a prorated mid-cycle charge unlocks it.
    # Existing rows are backfilled to 'active' (grandfathered); only newly detected
    # over-quota locations are ever inserted as 'pending_payment'.
    billing_status = Column(String, default="active", server_default=text("'active'"), nullable=False)

    sync_status = Column(String, default="Pending", nullable=False)  # Pending, Synced, Failed
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    last_insights_sync_at = Column(DateTime(timezone=True), nullable=True)
    google_attributes = Column(JSONB, default=list, server_default='[]', nullable=False)
    draft_attributes = Column(JSONB, default=list, server_default='[]', nullable=False)
    last_google_sync = Column(DateTime(timezone=True), nullable=True)
    google_category_resource_name = Column(String, nullable=True) # Example: "categories/gcid:jewelry_store"
    # Secondary/additional categories: list of {"name": "categories/gcid:x", "displayName": "X"}
    additional_categories = Column(JSONB, default=list, server_default='[]', nullable=False)
    # Owner/Admin-added custom queries to track for AI Visibility (AEO), on top of
    # the auto-generated category+city ones. List of plain strings.
    aeo_queries = Column(JSONB, default=list, server_default='[]', nullable=False)
    # When False, a scan runs ONLY the custom queries above (no auto-generated ones),
    # giving the owner exact control over query count and therefore cost.
    aeo_auto_enabled = Column(Boolean, default=True, server_default=text("true"), nullable=False)
    # Additional rich GBP fields — captured for full parity with what Google returns.
    additional_phones = Column(JSONB, default=list, server_default='[]', nullable=False)  # list of strings
    special_hours = Column(JSONB, nullable=True)      # holiday / one-off hours
    more_hours = Column(JSONB, nullable=True)         # extra hour types (e.g. delivery, kitchen)
    service_area = Column(JSONB, nullable=True)       # service-area business coverage
    service_items = Column(JSONB, nullable=True)      # structured/free-form service list
    labels = Column(JSONB, default=list, server_default='[]', nullable=False)  # list of strings
    open_info = Column(JSONB, nullable=True)          # open/closed status + opening date
    latlng = Column(JSONB, nullable=True)             # {latitude, longitude}
    store_code = Column(String, nullable=True)
    language_code = Column(String, nullable=True)
    # Full, verbatim GBP location payload so nothing Google sends is ever lost.
    gbp_raw = Column(JSONB, nullable=True)
    google_attributes_stale = Column(Boolean, default=False, nullable=False)
    last_publish_hash = Column(String(64), nullable=True)
    last_published_at = Column(DateTime(timezone=True), nullable=True)
    attention_needed = Column(Boolean, default=False, nullable=False)
    attention_reason = Column(Text, nullable=True)
    attention_updated_at = Column(DateTime(timezone=True), nullable=True)
    sla_tracking_started_at = Column(DateTime(timezone=True), nullable=True)
    # Optional extra recipient for microsite lead-form notifications (besides org admins).
    lead_email = Column(String, nullable=True)
    
    # State tracking
    is_verified = Column(Boolean, nullable=True)
    is_suspended = Column(Boolean, nullable=True)
    is_duplicate = Column(Boolean, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="locations")
    sync_logs = relationship("SyncLog", back_populates="location", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="location", cascade="all, delete-orphan")
    post_variants = relationship("PostVariant", back_populates="location", cascade="all, delete-orphan")
    publish_jobs = relationship("PublishJob", back_populates="location", cascade="all, delete-orphan")
    edits = relationship("LocationEdit", back_populates="location", cascade="all, delete-orphan")
    media_items = relationship("LocationMedia", back_populates="location", cascade="all, delete-orphan")
    daily_insights = relationship("LocationDailyInsight", back_populates="location", cascade="all, delete-orphan")
    keyword_metrics = relationship("KeywordMonthlyMetric", back_populates="location", cascade="all, delete-orphan")
    # Named *_record to avoid colliding with the LocationOut.health_score (int)
    # schema field, which breaks LocationOut.model_validate(location).
    health_score_record = relationship("LocationHealthScore", back_populates="location", uselist=False, cascade="all, delete-orphan")
    leaderboard_snapshots = relationship("LeaderboardSnapshot", back_populates="location", cascade="all, delete-orphan")
    microsite = relationship("Microsite", back_populates="location", uselist=False, cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_locations_sla_tracking_started_at", "sla_tracking_started_at"),
        Index("ix_locations_org_billing_status", "organization_id", "billing_status"),
        Index("ix_locations_org_city", "organization_id", "city"),
        Index("ix_locations_org_state", "organization_id", "state"),
    )
