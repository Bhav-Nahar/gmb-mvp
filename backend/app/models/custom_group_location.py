from sqlalchemy import Column, Integer, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.db.session import Base

class CustomGroupLocation(Base):
    __tablename__ = "custom_group_locations"

    custom_group_id = Column(Integer, ForeignKey("custom_groups.id", ondelete="CASCADE"), primary_key=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True)

    custom_group = relationship("CustomGroup", back_populates="locations")
    location = relationship("Location")

    __table_args__ = (
        Index("ix_custom_group_locations_location_id", "location_id"),
    )
