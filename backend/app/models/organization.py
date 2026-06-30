from sqlalchemy import Column, Integer, String, DateTime, Boolean, func, Index, text
from sqlalchemy.orm import relationship
from app.db.session import Base

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=True, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Billing Fields
    plan = Column(String, nullable=True, default="trial", server_default=text("'trial'"))
    # Product tier (basic | pro | ...) — gates premium features (see plan_config.PLANS).
    # Distinct from `plan` above, which is the trial/active billing-state flag.
    plan_tier = Column(String, nullable=False, default="basic", server_default=text("'basic'"))
    billing_cycle = Column(String, nullable=True)
    # States: trial (trial_ends_at NULL = not yet activated), active
    # (subscription_ends_at set = cancelled but still valid), past_due, locked.
    subscription_status = Column(String, nullable=True, default="trial", server_default=text("'trial'"))
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    grace_period_ends_at = Column(DateTime(timezone=True), nullable=True)
    location_quota = Column(Integer, nullable=True, default=3, server_default=text("3"))
    monthly_ai_credits_balance = Column(Integer, nullable=True, default=10, server_default=text("10"))
    topup_ai_credits_balance = Column(Integer, nullable=True, default=0, server_default=text("0"))
    ai_credits_reset_date = Column(DateTime(timezone=True), nullable=True)
    # When set, newly-synced reviews (rating >= 4) received AFTER this timestamp are
    # auto-replied from a reply template, across all of the org's active locations.
    # NULL = off. Timestamp (not bool) so enabling never machine-guns the backlog.
    auto_reply_enabled_at = Column(DateTime(timezone=True), nullable=True)
    razorpay_customer_id = Column(String, index=True, nullable=True)
    razorpay_subscription_id = Column(String, nullable=True)
    subscription_ends_at = Column(DateTime(timezone=True), nullable=True)

    # UPI re-mandate flow: Razorpay forbids changing the amount of a UPI Autopay
    # subscription, so raising the recurring charge (after a location add-on) needs a
    # brand-new mandate the user must approve. While that is pending:
    #   - subscription_payment_mode: 'upi' | 'card' | None (how the active mandate pays)
    #   - subscription_needs_remandate: True when location_quota outgrew what the
    #     current mandate pays for and a new mandate is required (UPI only)
    #   - paid_location_quota: how many locations the CURRENT mandate actually bills
    #     (the surplus above this is locked if the user never re-authorizes)
    #   - remandate_due_at: deadline (renewal date + 3 days) after which the surplus
    #     locations are re-locked to 'pending_payment'
    subscription_payment_mode = Column(String, nullable=True)
    subscription_needs_remandate = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    paid_location_quota = Column(Integer, nullable=True)
    remandate_due_at = Column(DateTime(timezone=True), nullable=True)
    # The re-mandate subscription awaiting the user's approval. Tracked so a repeated
    # /remandate call reuses the outstanding mandate (or cancels a stale one) instead
    # of stacking a second mandate that would double-bill. Cleared at cutover.
    pending_remandate_subscription_id = Column(String, nullable=True)

    # Marketing attribution, captured first-touch from the browser at signup and used
    # for server-side conversions (Meta CAPI / Google Ads). First-touch wins: a column
    # is only written if currently NULL (see /users/me/attribution).
    utm_source = Column(String, nullable=True)
    utm_medium = Column(String, nullable=True)
    utm_campaign = Column(String, nullable=True)
    utm_content = Column(String, nullable=True)
    utm_term = Column(String, nullable=True)
    gclid = Column(String, nullable=True)
    gbraid = Column(String, nullable=True)
    wbraid = Column(String, nullable=True)
    fbclid = Column(String, nullable=True)
    fbp = Column(String, nullable=True)
    fbc = Column(String, nullable=True)
    landing_page = Column(String, nullable=True)
    # Customer IP + user-agent from the most recent /billing/confirm request, used as
    # Meta CAPI match keys (the webhook itself only sees Razorpay's IP).
    conv_client_ip = Column(String, nullable=True)
    conv_user_agent = Column(String, nullable=True)
    attribution_captured_at = Column(DateTime(timezone=True), nullable=True)

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
    brand_terms = relationship("OrganizationBrandTerm", back_populates="organization", cascade="all, delete-orphan")
    leaderboard_snapshots = relationship("LeaderboardSnapshot", back_populates="organization", cascade="all, delete-orphan")
    microsites = relationship("Microsite", back_populates="organization", cascade="all, delete-orphan")
