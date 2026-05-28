from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint, Index, func, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.db.session import Base

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), index=True, nullable=False)
    provider = Column(String, nullable=False)
    provider_review_id = Column(String, index=True, nullable=False)
    reviewer_name = Column(String, nullable=False)
    reviewer_profile_photo = Column(String, nullable=True)
    rating = Column(Integer, nullable=True)
    comment = Column(Text, nullable=True)
    is_replied = Column(Boolean, default=False, nullable=False)
    reply_text = Column(Text, nullable=True)
    reply_created_at = Column(DateTime(timezone=True), nullable=True)
    review_created_at = Column(DateTime(timezone=True), nullable=False)
    review_updated_at = Column(DateTime(timezone=True), nullable=True)
    raw_payload = Column(JSON().with_variant(JSONB, 'postgresql'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # AI Sentiment tagging columns
    # sentiment_tagged_at IS NULL means this review has not been processed yet.
    # It is set to datetime.utcnow() after successful tagging — the sole signal for "needs processing".
    # TODO (future): During ReviewSyncService upsert, if review_updated_at > sentiment_tagged_at,
    # reset sentiment_tagged_at to NULL so the review is automatically re-queued for reclassification.
    # This handles cases where review text changes after initial tagging.
    sentiment           = Column(String,                  nullable=True, index=True)
    issue_category      = Column(String,                  nullable=True, index=True)
    sentiment_tagged_at = Column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="reviews")
    location = relationship("Location", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint("location_id", "provider", "provider_review_id", name="uq_review_provider_id"),
        Index("idx_reviews_location_created_at_desc", "location_id", review_created_at.desc()),
        Index("ix_reviews_sla_lookup", "organization_id", "location_id", "is_deleted", "is_replied", "review_created_at"),
        Index("ix_reviews_reply_created_at", "reply_created_at"),
    )
