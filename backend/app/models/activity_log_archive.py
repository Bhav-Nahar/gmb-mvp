from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db.session import Base


class ActivityLogArchive(Base):
    __tablename__ = "activity_log_archive"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, index=True)
    location_id = Column(Integer, nullable=True, index=True)
    actor_user_id = Column(Integer, nullable=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=True)
    action = Column(String, nullable=False)
    payload = Column(JSONB, nullable=True)
    
    correlation_id = Column(String, nullable=True, index=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False)
    archived_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_activity_archive_org", "organization_id", "created_at"),
        Index("idx_activity_archive_location", "location_id", "created_at"),
    )
