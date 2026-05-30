from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.db.session import Base

class PostVariant(Base):
    __tablename__ = "post_variants"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    
    rendered_summary = Column(String, nullable=False)
    rendered_cta_url = Column(String, nullable=True)
    rendering_variables = Column(JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    post = relationship("Post", back_populates="variants")
    location = relationship("Location", back_populates="post_variants")
    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint("post_id", "location_id", name="uq_post_variant_location"),
    )
