from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.db.session import Base
from app.constants.posts import PublishJobStatus

class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    
    provider = Column(String, default="gbp", nullable=False)
    status = Column(String, default=PublishJobStatus.PENDING.value, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    last_error = Column(String, nullable=True)
    google_post_id = Column(String, nullable=True)
    provider_response = Column(JSONB, nullable=True)
    
    idempotency_key = Column(String, unique=True, index=True, nullable=True)
    
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="publish_jobs")
    campaign = relationship("Campaign", back_populates="publish_jobs")
    post = relationship("Post", back_populates="publish_jobs")
    location = relationship("Location", back_populates="publish_jobs")

    __table_args__ = (
        UniqueConstraint("post_id", "location_id", name="uq_publish_job_post_location"),
        Index("idx_publish_jobs_post_status", "post_id", "status"),
        Index("idx_publish_jobs_loc_status", "location_id", "status"),
        Index("idx_publish_jobs_campaign_status", "campaign_id", "status"),
        Index("idx_publish_jobs_org_status", "organization_id", "status"),
    )
