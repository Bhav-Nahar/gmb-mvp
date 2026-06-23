from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Index, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.db.session import Base

class SavedComparisonView(Base):
    __tablename__ = "saved_comparison_views"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    
    group_by = Column(String, nullable=False) # city, state, region, custom
    filters_json = Column(JSONB, nullable=False, default=dict, server_default='{}')
    is_shared = Column(Boolean, default=False, nullable=False, server_default='false')

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    organization = relationship("Organization")
    user = relationship("User")

    __table_args__ = (
        Index("ix_saved_views_org_user", "organization_id", "user_id"),
    )
