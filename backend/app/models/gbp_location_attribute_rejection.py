from sqlalchemy import Column, Integer, String, DateTime, func, Text, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from app.db.session import Base

class GbpLocationAttributeRejection(Base):
    __tablename__ = "gbp_location_attribute_rejections"
    
    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, nullable=False, index=True)
    attribute_id = Column(String(255), nullable=False, index=True)
    rejection_reason = Column(Text, nullable=True)
    rejected_value = Column(JSONB, nullable=True)
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    rejection_count = Column(Integer, default=1)
    suppressed = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint('location_id', 'attribute_id', name='uq_gbp_location_attribute_rejections_loc_attr'),
    )
