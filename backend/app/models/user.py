from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Boolean
from sqlalchemy.orm import relationship
from app.db.session import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    avatar = Column(String, nullable=True)
    google_id = Column(String, unique=True, index=True, nullable=False)
    role = Column(String, default="Viewer", nullable=False)  # Owner, Admin, Regional Manager, Store Manager, Viewer
    is_active = Column(Boolean, default=True, nullable=False)
    token_version = Column(Integer, default=1, nullable=False)
    viewer_scope = Column(String, default="assigned", nullable=True) # "assigned" or "organization"
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="users")
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")
    created_campaigns = relationship("Campaign", back_populates="created_by", cascade="all, delete-orphan")
    created_posts = relationship("Post", back_populates="created_by", cascade="all, delete-orphan")
