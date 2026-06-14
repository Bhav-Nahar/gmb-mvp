import enum
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, Enum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class LocationMediaStatus(str, enum.Enum):
    PENDING = "Pending"
    PUBLISHING = "Publishing"
    PUBLISHED = "Published"
    FAILED = "Failed"
    REJECTED = "Rejected"


class LocationMedia(Base):
    """A photo/video published (or pending publish) to a location's Google
    Business Profile gallery. Distinct from PostMedia, whose lifecycle is
    post-centric and DB-owned; LocationMedia mirrors state that lives in
    Google's gallery (resource name, category, view count, publish status)."""

    __tablename__ = "location_media"

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
    # Reuses the upload/optimize pipeline: the underlying file lives in PostMedia.
    source_media_id = Column(
        Integer,
        ForeignKey("post_media.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Google gallery attributes ─────────────────────────────────────────────
    gbp_category = Column(String, nullable=False, default="ADDITIONAL")  # LOGO/COVER/INTERIOR/...
    media_format = Column(String, nullable=False, default="PHOTO")      # PHOTO or VIDEO
    gbp_resource_name = Column(String, nullable=True)  # accounts/{a}/locations/{l}/media/{key}
    media_key = Column(String, nullable=True)          # trailing {key}, used for delete
    source_url = Column(String, nullable=False)        # public CDN URL sent to Google as sourceUrl
    thumbnail_url = Column(String, nullable=True)      # Google's light poster/thumbnail

    # ── State machine ─────────────────────────────────────────────────────────
    publish_status = Column(
        # The PG enum type was created with the string *values* ("Published"),
        # so use values_callable to store/read those instead of member names.
        Enum(
            LocationMediaStatus,
            name="locationmediastatus",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=LocationMediaStatus.PENDING,
        index=True,
    )
    failure_reason = Column(Text, nullable=True)
    google_error_code = Column(String, nullable=True)
    publish_attempts = Column(Integer, nullable=False, default=0)

    # ── Soft deletion ─────────────────────────────────────────────────────────
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
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
    location = relationship("Location", back_populates="media_items")
    organization = relationship("Organization")
    source_media = relationship("PostMedia")

    __table_args__ = (
        Index("idx_location_media_location_status", "location_id", "publish_status"),
        Index("idx_location_media_org_created", "organization_id", "created_at"),
    )
