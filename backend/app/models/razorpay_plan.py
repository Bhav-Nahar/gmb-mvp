from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint, func
from app.db.session import Base


class RazorpayPlan(Base):
    """Persisted Razorpay plan ids, keyed by (location_count, interval, amount_paise).

    Plan creation is an external API call and Razorpay plans are immutable, so we
    cache the created plan id durably instead of in-process. This prevents orphan
    plan sprawl and the rate-limiting that came from recreating a plan on every
    cold checkout (the in-process cache was per-process and lost on reload).

    The amount is part of the key so a pricing change creates a NEW plan rather
    than silently reusing one that bills the old amount.

    `mode` ('test' | 'live') is also part of the key: a Razorpay plan id created
    with test keys does not exist under live keys (and vice versa), so the same
    (count, interval, amount) tier legitimately needs one cached row per mode.
    Without it, the first row cached in test mode blocks the live row from ever
    persisting, recreating a fresh live plan on every checkout (sprawl + 429s).
    """
    __tablename__ = "razorpay_plans"

    id = Column(Integer, primary_key=True, index=True)
    location_count = Column(Integer, nullable=False)
    interval = Column(String, nullable=False)  # 'monthly' | 'annual'
    amount_paise = Column(Integer, nullable=False)
    razorpay_plan_id = Column(String, nullable=False)
    mode = Column(String, nullable=False, default="live")  # 'test' | 'live'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "location_count", "interval", "amount_paise", "mode",
            name="uq_razorpay_plan_count_interval_amount_mode",
        ),
    )
