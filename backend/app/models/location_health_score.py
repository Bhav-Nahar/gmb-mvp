from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.db.session import Base

class LocationHealthScore(Base):
    __tablename__ = "location_health_scores"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    
    score = Column(Integer, nullable=False)
    potential_score = Column(Integer, nullable=False)
    label = Column(String, nullable=False)
    score_version = Column(String(20), default="HEALTH_V1", server_default="HEALTH_V1", nullable=False)
    
    breakdown = Column(JSONB, nullable=False)
    recommendations = Column(JSONB, nullable=False)
    last_recalculated_reason = Column(String, nullable=False)
    
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    location = relationship("Location", back_populates="health_score_record")
