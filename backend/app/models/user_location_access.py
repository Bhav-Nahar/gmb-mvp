from sqlalchemy import Column, Integer, DateTime, ForeignKey, Index, func
from app.db.session import Base

class UserLocationAccess(Base):
    __tablename__ = "user_location_access"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_user_location_pair", "user_id", "location_id"),
    )
