from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Index, Boolean, JSON
from sqlalchemy.orm import relationship
from app.db.session import Base

class PostMedia(Base):
    __tablename__ = "post_media"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=True)
    
    storage_provider = Column(String, nullable=False) # e.g., 'local', 's3', 'r2'
    storage_key = Column(String, nullable=False) # e.g., 'org_1/media_uuid.png'
    media_type = Column(String, default="PHOTO", nullable=False)
    original_filename = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    sha256_hash = Column(String, index=True, nullable=False)
    
    # URL tracking
    cdn_url = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=True)
    optimized_url = Column(String, nullable=True)
    
    # State tracking
    upload_status = Column(String, default="Pending", nullable=False) # Pending, Uploaded, Failed, Deleted
    validation_status = Column(String, default="Pending", nullable=False) # Pending, Valid, Invalid
    
    # Soft deletion
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Custom metadata logs (width, height, ratio, etc.)
    log_metadata = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    post = relationship("Post", back_populates="media")
    organization = relationship("Organization")

    __table_args__ = (
        Index("idx_post_media_org_sha", "organization_id", "sha256_hash"),
    )
