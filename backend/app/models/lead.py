from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class Lead(Base):
    """A lead captured from a public microsite contact form."""
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    message = Column(Text, nullable=True)

    # "new" | "contacted" | "closed" — simple lifecycle for the dashboard.
    status = Column(String, nullable=False, default="new")
    source = Column(String, nullable=False, default="microsite")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    location = relationship("Location")
