from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Text, UniqueConstraint
from app.db.session import Base


class ReviewSuppression(Base):
    """Numbers this organization must never message again.

    Separate from `review_requests` deliberately: a suppression outlives the
    request that caused it, and must be checked even for a number that has
    never been messaged (a tenant pasting their own do-not-contact list).

    Honouring this is not optional. WhatsApp marketing opt-out arrives on the
    webhook as a `user_preferences` event, and continuing to message someone
    after it is both a policy breach and the fastest route to a quality-rating
    collapse — which throttles the tenant's number for everyone, not just the
    person who complained.
    """

    __tablename__ = "review_suppressions"

    REASON_OPT_OUT = "opt_out"        # Meta marketing opt-out, or replied STOP
    REASON_FAILED = "failed"          # not a WhatsApp user / permanently undeliverable
    REASON_MANUAL = "manual"          # added by the tenant
    REASON_COMPLAINT = "complaint"    # blocked/reported us

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)

    # E.164 without '+', same normalisation as ReviewRequest.phone so the
    # lookup is a straight equality match and can never miss on formatting.
    phone = Column(String, nullable=False, index=True)

    reason = Column(String, nullable=False, default=REASON_MANUAL)
    note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        # Suppression is per-organization, not global: one tenant's customer
        # opting out says nothing about another tenant's relationship with the
        # same person.
        UniqueConstraint("organization_id", "phone", name="uq_review_suppressions_org_phone"),
    )
