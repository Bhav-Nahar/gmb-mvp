import enum
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    UniqueConstraint, Index, Enum
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

class LocationEditStatus(str, enum.Enum):
    DRAFT = "Draft"
    PENDING = "Pending"
    APPROVED = "Approved"
    PUBLISHING = "Publishing"
    PUBLISHED = "Published"
    FAILED = "Failed"
    REJECTED = "Rejected"

class LocationEdit(Base):
    __tablename__ = "location_edits"

    id = Column(Integer, primary_key=True, index=True)

    # ── Tenancy & ownership ───────────────────────────────────────────────────
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_id = Column(
        Integer,
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submitted_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Field being changed ───────────────────────────────────────────────────
    field_name = Column(String, nullable=False)
    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=False)

    # ── State machine ─────────────────────────────────────────────────────────
    status = Column(
        Enum(LocationEditStatus),
        nullable=False,
        default=LocationEditStatus.DRAFT,
        index=True
    )
    rejection_note = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)

    # ── Retry & Operational Metadata ──────────────────────────────────────────
    publish_attempts = Column(Integer, nullable=False, default=0)
    google_error_code = Column(String, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    
    warning_acknowledged = Column(Boolean, nullable=False, default=False)

    # ── Timestamps ────────────────────────────────────────────────────────────
    requested_publish_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    location = relationship("Location", back_populates="edits")
    submitted_by = relationship("User", foreign_keys=[submitted_by_user_id])
    approved_by = relationship("User", foreign_keys=[approved_by_user_id])

    __table_args__ = (
        Index("idx_location_edits_location_status", "location_id", "status"),
        Index("idx_location_edits_org_created", "organization_id", "created_at"),
    )
