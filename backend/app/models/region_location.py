from sqlalchemy import Column, Integer, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.db.session import Base

class RegionLocation(Base):
    __tablename__ = "region_locations"

    region_id = Column(Integer, ForeignKey("regions.id", ondelete="CASCADE"), primary_key=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True)

    region = relationship("Region", back_populates="locations")
    location = relationship("Location")

    __table_args__ = (
        Index("ix_region_locations_location_id", "location_id"),
    )
