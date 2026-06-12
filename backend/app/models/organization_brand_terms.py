from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Index
from sqlalchemy.orm import relationship
from app.db.session import Base

class OrganizationBrandTerm(Base):
    __tablename__ = "organization_brand_terms"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    term = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_org_brand_terms_org_term", "organization_id", "term", unique=True),
    )

    organization = relationship("Organization", back_populates="brand_terms")
