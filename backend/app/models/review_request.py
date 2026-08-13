from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Text, Index, text
from sqlalchemy.orm import relationship
from app.db.session import Base


class ReviewRequest(Base):
    """One "please review us" WhatsApp message to one customer of one location.

    The token is the whole mechanism. Meta's dynamic URL button can only vary
    the SUFFIX of a URL fixed at template-approval time, so the template points
    at `https://pinzo.io/r/` and this token is what identifies the recipient.
    The redirect then looks up the location and 302s to that location's Google
    review page.

    Pointing the button straight at Google would be simpler and is technically
    allowed, but it would mean one template per location (the review URL is
    per-location and the base is immutable), no click signal at all, and no way
    to repoint a link after approval. Hence the hop.
    """

    __tablename__ = "review_requests"

    STATUS_QUEUED = "queued"
    STATUS_SENT = "sent"
    STATUS_DELIVERED = "delivered"
    STATUS_READ = "read"
    STATUS_CLICKED = "clicked"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"     # suppressed / frequency-capped before sending

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"),
                         nullable=False, index=True)

    # E.164 without the leading '+' — the format Meta's `to` field wants, so it
    # is stored the way it is sent rather than reformatted at every call site.
    phone = Column(String, nullable=False, index=True)
    customer_name = Column(String, nullable=True)

    # 16 random bytes, URL-safe. Unguessable on purpose: it is the only thing
    # standing between a stranger and someone else's link.
    token = Column(String, nullable=False, unique=True, index=True)

    status = Column(String, nullable=False, default=STATUS_QUEUED, index=True)

    # Meta's message id (wamid). Indexed because delivery-status webhooks
    # arrive later carrying only this — it is the join key back to this row.
    wamid = Column(String, nullable=True, index=True)

    # 'manual' | 'csv' | 'lead' — where the number came from, kept for the
    # consent audit trail as much as for reporting.
    source = Column(String, nullable=False, default="manual")
    # Groups one upload/send into a campaign so the dashboard can report on it.
    batch_id = Column(String, nullable=True, index=True)

    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    # First click only — a second tap is the same person, not new information.
    clicked_at = Column(DateTime(timezone=True), nullable=True)

    # Meta's own failure reason, kept verbatim. Its codes are opaque to humans
    # (131047 = outside the 24h window, 131026 = not reachable on WhatsApp), so
    # the UI maps them to plain English and this is the raw record behind that.
    error_code = Column(String, nullable=True)
    error_detail = Column(Text, nullable=True)

    # Reminders reuse this row rather than creating a new one: the token, and so
    # the link already in the customer's chat, must keep working. Capped in the
    # task at 2 — a third ask is what earns a block.
    reminder_count = Column(Integer, nullable=False, server_default=text("0"), default=0)
    last_reminder_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    location = relationship("Location")

    __table_args__ = (
        # The frequency cap asks "did we message this number recently?" on every
        # queued row before sending; without this it is a full scan per send.
        Index("ix_review_requests_org_phone_created", "organization_id", "phone", "created_at"),
        # The campaign view: this location's requests, newest first.
        Index("ix_review_requests_location_created", "location_id", "created_at"),
    )
