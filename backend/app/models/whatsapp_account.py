from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, func, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.session import Base


class WhatsAppAccount(Base):
    """One organization's own WhatsApp Business Account (WABA), connected via
    Meta's Embedded Signup.

    Pinzo is a Meta *Tech Provider*: the client owns the WABA and the phone
    number, the client's own payment method is billed by Meta for every
    message, and Pinzo only acts on their behalf. So credentials are per-org
    and there is no shared/global WhatsApp config anywhere in the codebase —
    a global one is exactly what would let one tenant's sending behaviour
    damage every other tenant's delivery.

    `status` is a state machine, not a flag. Onboarding has several steps that
    each fail independently and each need a different message to the user, and
    a single boolean cannot say *which* one is outstanding — which is how a
    stuck tenant becomes a support ticket instead of a self-service fix.
    """

    __tablename__ = "whatsapp_accounts"

    # Onboarding states, in order. Anything other than `ready` means sending is
    # blocked, and `status_detail` carries the human explanation.
    STATUS_PENDING = "pending"                    # row created, signup not finished
    STATUS_CONNECTED = "connected"                # token + ids received from Embedded Signup
    STATUS_NUMBER_REGISTERED = "number_registered"  # phone registered against the WABA
    STATUS_PAYMENT_REQUIRED = "payment_required"  # Meta needs a payment method on THEIR account
    STATUS_TEMPLATE_PENDING = "template_pending"  # review template submitted, awaiting Meta
    STATUS_READY = "ready"                        # can send
    STATUS_DISABLED = "disabled"                  # switched off by admin, or quality too low

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)

    # Meta identifiers. Not secret — they appear in webhook payloads and API
    # paths — so they are stored in the clear and are safe to log.
    waba_id = Column(String, nullable=True, index=True)
    # Indexed because the inbound webhook routes by it: one callback URL
    # receives events for EVERY subscribed WABA, so `phone_number_id -> org`
    # is the lookup on every single incoming event.
    phone_number_id = Column(String, nullable=True, index=True)
    display_phone_number = Column(String, nullable=True)
    verified_name = Column(String, nullable=True)

    # The client's business token from Embedded Signup. Encrypted at rest with
    # the same Fernet helpers as OAuth tokens (app/core/security.py) — this
    # grants send-on-behalf-of rights, so it is at least as sensitive as a
    # Google refresh token.
    access_token = Column(Text, nullable=True)

    status = Column(String, nullable=False, default=STATUS_PENDING, index=True)
    # Why the current status exists, in words fit to show the user.
    status_detail = Column(Text, nullable=True)

    # Mirrored from Meta so the UI can explain a throttle instead of the tenant
    # discovering it as "my upload stopped for no reason". GREEN/YELLOW/RED and
    # the 24h send limit of the current tier.
    quality_rating = Column(String, nullable=True)
    messaging_tier = Column(String, nullable=True)
    daily_send_limit = Column(Integer, nullable=True)

    # The review-request template on THIS WABA. Templates are per-WABA, so each
    # tenant gets their own copy created and approved at onboarding.
    template_name = Column(String, nullable=True)
    template_status = Column(String, nullable=True)   # PENDING | APPROVED | REJECTED

    connected_at = Column(DateTime(timezone=True), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)

    organization = relationship("Organization")

    __table_args__ = (
        # One WABA per organization. A second row would make "which credentials
        # do we send with" ambiguous, and the answer must never be arbitrary.
        UniqueConstraint("organization_id", name="uq_whatsapp_accounts_org"),
    )

    @property
    def can_send(self) -> bool:
        return self.status == self.STATUS_READY
