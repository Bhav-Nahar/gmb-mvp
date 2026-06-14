from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.db.session import Base

class BillingTransaction(Base):
    __tablename__ = "billing_transactions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_type = Column(String, nullable=False)  # e.g., 'monthly_reset', 'topup', 'usage'
    credits = Column(Integer, nullable=True)
    amount_paise = Column(Integer, nullable=True)
    currency = Column(String, nullable=True)
    status = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)
    razorpay_order_id = Column(String, nullable=True)
    razorpay_subscription_id = Column(String, nullable=True)
    # Hosted Razorpay invoice URL (invoice.short_url), captured from the webhook when
    # present. Nullable: reconciliation-path rows and add-ons may not carry one.
    invoice_url = Column(String, nullable=True)
    source = Column(String, nullable=True)  # e.g., 'razorpay_event_id', 'admin', 'system'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization", backref="billing_transactions")

