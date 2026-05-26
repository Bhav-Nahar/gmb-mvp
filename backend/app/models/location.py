from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Float
from sqlalchemy.orm import relationship
from app.db.session import Base

class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    google_account_id = Column(String, nullable=True) # Example: "accounts/12345"
    google_location_id = Column(String, index=True, nullable=False)  # Example: "locations/12345"
    location_name = Column(String, nullable=False)
    primary_category = Column(String, nullable=True)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    website = Column(String, nullable=True)
    average_rating = Column(Float, nullable=True) # Average rating out of 5 (e.g. 4.5)
    total_reviews = Column(Integer, nullable=True)
    
    sync_status = Column(String, default="Pending", nullable=False)  # Pending, Synced, Failed
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="locations")
    sync_logs = relationship("SyncLog", back_populates="location", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="location", cascade="all, delete-orphan")
