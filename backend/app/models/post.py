from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func, Index
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.constants.posts import PostStatus, PostType

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    title = Column(String, nullable=True)
    summary = Column(String, nullable=False) # max 1500 chars limit handled at service/schema level
    language_code = Column(String, default="en-US", nullable=False)
    post_type = Column(String, default=PostType.UPDATE.value, nullable=False)
    status = Column(String, default=PostStatus.DRAFT.value, nullable=False)
    cta_type = Column(String, nullable=True)
    cta_url = Column(String, nullable=True)
    is_bulk_post = Column(Boolean, default=False, nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="posts")
    campaign = relationship("Campaign", back_populates="posts", foreign_keys=[campaign_id])
    created_by = relationship("User", back_populates="created_posts")
    
    variants = relationship("PostVariant", back_populates="post", cascade="all, delete-orphan")
    media = relationship("PostMedia", back_populates="post", cascade="all, delete-orphan")
    publish_jobs = relationship("PublishJob", back_populates="post", cascade="all, delete-orphan")
    audit_logs = relationship("PostAuditLog", back_populates="post", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_posts_org_status", "organization_id", "status"),
    )
