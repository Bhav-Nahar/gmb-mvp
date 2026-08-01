from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text
from app.db.session import Base


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True, index=True)

    # ── Tenancy & actor ───────────────────────────────────────────────────────
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_id = Column(
        Integer,
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Event classification ──────────────────────────────────────────────────
    entity_type = Column(String, nullable=False, index=True)
    entity_id = Column(Integer, nullable=True)
    action = Column(String, nullable=False)

    # ── Payload ───────────────────────────────────────────────────────────────
    payload = Column(JSONB, nullable=True)
    
    # ── Operational Tracing ───────────────────────────────────────────────────
    correlation_id = Column(String, nullable=True, index=True)

    # ── Timestamp ─────────────────────────────────────────────────────────────
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    actor = relationship("User", foreign_keys=[actor_user_id])

    # ── Indices ───────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("idx_activity_log_location_created", "location_id", "created_at"),
        Index("idx_activity_log_org_created", "organization_id", "created_at"),
        Index("idx_activity_log_entity", "entity_type", "entity_id"),
        # The Unauthorised Changes list and its sidebar badge are org-wide and always
        # filter entity_type='ProfileChange'; partial keeps it small next to the rest
        # of the log (every sync, post, review and edit writes here).
        Index(
            "idx_activity_log_profile_change",
            "organization_id",
            text("created_at DESC"),
            postgresql_where=text("entity_type = 'ProfileChange'"),
        ),
    )
