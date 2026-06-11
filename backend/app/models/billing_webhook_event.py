from sqlalchemy import Column, Integer, String, DateTime, func, JSON
from app.db.session import Base

class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    razorpay_event_id = Column(String, unique=True, index=True, nullable=False)
    event_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

