from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint, Index, func
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
    review_created_at = Column(DateTime(timezone=True), nullable=False)
    review_updated_at = Column(DateTime(timezone=True), nullable=True)
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="reviews")
    location = relationship("Location", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint("provider", "provider_review_id", name="uq_review_provider_id"),
        Index("idx_reviews_location_created_at_desc", "location_id", review_created_at.desc()),
    )
