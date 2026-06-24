import enum
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint, func, Index
from sqlalchemy.orm import relationship
from app.db.session import Base

class MicrositeStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"

class Microsite(Base):
    __tablename__ = "microsites"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, unique=True)
    org_slug = Column(String, nullable=False)
    location_slug = Column(String, nullable=False)
    status = Column(String, nullable=False, default=MicrositeStatus.DRAFT.value)
    published_at = Column(DateTime(timezone=True), nullable=True)
    unpublished_at = Column(DateTime(timezone=True), nullable=True)
    
    # Analytics field. Do NOT increment synchronously per request on the public
    # page — that would hit the DB on every page view. Future implementation
    # should aggregate in Redis and periodically flush to this column.
    view_count = Column(Integer, nullable=False, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("location_id", name="uq_microsite_location"),
        UniqueConstraint("org_slug", "location_slug", name="uq_microsite_org_slug"),
        Index("ix_microsites_status", "status"),
    )

    organization = relationship("Organization", back_populates="microsites")
    location = relationship("Location", back_populates="microsite", uselist=False)
