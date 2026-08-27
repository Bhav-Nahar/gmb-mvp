from sqlalchemy import (Column, Integer, String, DateTime, ForeignKey, func, Text,
                        Index, text)

from app.db.session import Base


class WhatsAppMessage(Base):
    """One WhatsApp message, inbound or outbound, in a tenant's inbox.

    A "conversation" is not a row anywhere — it is just (organization_id, phone).
    Pinzo has no contacts table and does not need one: the customer is identified
    by the number Meta gives us, and inventing an entity to wrap it would mean
    reconciling it with locations, leads and review requests for no gain.

    Review requests are NOT copied in here. They already live in `review_requests`
    with their own delivery lifecycle, and duplicating them would create two
    sources of truth for the same message plus a backfill. The inbox merges the
    two tables on read instead — see api/whatsapp_inbox.py.
    """

    __tablename__ = "whatsapp_messages"

    DIRECTION_IN = "in"
    DIRECTION_OUT = "out"

    STATUS_SENT = "sent"
    STATUS_DELIVERED = "delivered"
    STATUS_READ = "read"
    STATUS_FAILED = "failed"
    STATUS_RECEIVED = "received"   # inbound; there is nothing to deliver

    id = Column(Integer, primary_key=True, index=True)
    # No index=True on either column: the composite indexes below lead on
    # organization_id and cover every query. A standalone index on each is one
    # more thing to write on every inbound webhook for nothing.
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False)

    # E.164 without the leading '+', matching review_requests.phone and Meta's
    # `to` field, so the two tables join and merge without reformatting.
    phone = Column(String, nullable=False)

    direction = Column(String, nullable=False)
    body = Column(Text, nullable=True)

    # What Meta called it: text / image / audio / button / interactive / ...
    # We only compose text, but a customer can send anything, and showing
    # "[image]" beats showing an empty bubble that looks like a bug.
    message_type = Column(String, nullable=False, default="text")

    # Meta's message id. UNIQUE because it is the whole dedupe mechanism: Meta
    # re-delivers a webhook it did not get a fast 200 for, and without this the
    # same customer reply appears two or three times in the thread.
    wamid = Column(String, nullable=True, unique=True, index=True)

    status = Column(String, nullable=False, default=STATUS_SENT)
    error_detail = Column(Text, nullable=True)

    # The user who typed the reply. NULL for inbound and for anything the system
    # sent on its own.
    sent_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                             nullable=True)

    # When the message happened, not when we wrote the row — for inbound this is
    # Meta's timestamp, which can lag the insert by minutes on a retry.
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    __table_args__ = (
        # The two queries the inbox makes: list a thread, and find the most
        # recent inbound per number (both the conversation list ordering and the
        # 24-hour window check).
        Index("ix_wa_messages_org_phone_created", "organization_id", "phone", "created_at"),
        Index("ix_wa_messages_org_direction_created", "organization_id", "direction", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<WhatsAppMessage {self.direction} {self.phone} {self.status}>"
