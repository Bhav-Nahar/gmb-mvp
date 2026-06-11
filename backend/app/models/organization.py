from sqlalchemy import Column, Integer, String, DateTime, func, Index, text
from sqlalchemy.orm import relationship
from app.db.session import Base

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Billing Fields
    plan = Column(String, nullable=True, default="trial", server_default=text("'trial'"))
    billing_cycle = Column(String, nullable=True)
    subscription_status = Column(String, nullable=True, default="trial_pending_activation", server_default=text("'trial_pending_activation'"))
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    grace_period_ends_at = Column(DateTime(timezone=True), nullable=True)
    location_quota = Column(Integer, nullable=True, default=5, server_default=text("5"))
    monthly_ai_credits_balance = Column(Integer, nullable=True, default=200, server_default=text("200"))
    topup_ai_credits_balance = Column(Integer, nullable=True, default=0, server_default=text("0"))
    ai_credits_reset_date = Column(DateTime(timezone=True), nullable=True)
    razorpay_customer_id = Column(String, index=True, nullable=True)
    razorpay_subscription_id = Column(String, nullable=True)
    subscription_ends_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_org_subscription_status_ends_at", "subscription_status", "subscription_ends_at"),
    )

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    locations = relationship("Location", back_populates="organization", cascade="all, delete-orphan")
    sync_logs = relationship("SyncLog", back_populates="organization", cascade="all, delete-orphan")
    invites = relationship("Invite", back_populates="organization", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="organization", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="organization", cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="organization", cascade="all, delete-orphan")
    publish_jobs = relationship("PublishJob", back_populates="organization", cascade="all, delete-orphan")
