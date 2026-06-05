from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.db.session import Base

class OrganizationSyncState(Base):
    __tablename__ = "organization_sync_states"

    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    last_location_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_review_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_insights_sync_at = Column(DateTime(timezone=True), nullable=True)

    insights_sync_in_progress = Column(Boolean, nullable=False, server_default=text("false"))
    last_insights_sync_status = Column(String(50), nullable=True)  # e.g., 'success', 'failed', 'in_progress'
    last_insights_sync_error = Column(String, nullable=True)
    last_insights_sync_started_at = Column(DateTime(timezone=True), nullable=True)
    last_insights_sync_completed_at = Column(DateTime(timezone=True), nullable=True)

    sync_in_progress = Column(Boolean, nullable=False, server_default=text("false"))
    # Timestamp of the last time sync_in_progress was set to True.
    # Used to detect orphaned "stuck" states after a Celery worker crash:
    # if sync_in_progress=True but sync_started_at is >2h ago, the lock has
    # definitely expired and the state is safe to reset.
    sync_started_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_status = Column(String(50), nullable=True)  # e.g., 'Success', 'Failed', 'Pending'
    last_sync_error = Column(String, nullable=True)

    organization = relationship("Organization", backref="sync_state")
    location_sync_metadata = Column(JSONB, nullable=False, server_default=text("'{}'"))
