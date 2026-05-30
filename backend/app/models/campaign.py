from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.constants.posts import CampaignStatus

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default=CampaignStatus.DRAFT.value, nullable=False)
    total_locations = Column(Integer, default=0, nullable=False)
    total_pending = Column(Integer, default=0, nullable=False)
    total_published = Column(Integer, default=0, nullable=False)
    total_failed = Column(Integer, default=0, nullable=False)
    total_rejected = Column(Integer, default=0, nullable=False)
    total_shadow_banned = Column(Integer, default=0, nullable=False)
    
    primary_post_id = Column(Integer, ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="campaigns")
    created_by = relationship("User", back_populates="created_campaigns")
    posts = relationship("Post", back_populates="campaign", cascade="all, delete-orphan", foreign_keys="[Post.campaign_id]")
    primary_post = relationship("Post", foreign_keys=[primary_post_id], post_update=True)
    publish_jobs = relationship("PublishJob", back_populates="campaign", cascade="all, delete-orphan")
    audit_logs = relationship("CampaignAuditLog", back_populates="campaign", cascade="all, delete-orphan")

