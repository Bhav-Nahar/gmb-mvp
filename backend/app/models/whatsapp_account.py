from sqlalchemy import (Column, Integer, String, DateTime, Boolean, ForeignKey, func, Text,
                        UniqueConstraint, text)
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
    # The tenant revoked our access at Meta (or the token was invalidated some
    # other way). Distinct from `disabled` because the fix is different and only
    # they can do it: reconnect. Without this state a revoked token looks like
    # every message failing for no reason, on an account still reporting "ready".
    STATUS_REAUTH_REQUIRED = "reauth_required"

    # States we can leave on our own once Meta's answer changes, versus the ones
    # that need the tenant to do something. Used by the recovery sweep so a
    # tenant is never permanently stuck in a state they have already fixed.
    RECOVERABLE_STATUSES = (STATUS_PAYMENT_REQUIRED, STATUS_DISABLED, STATUS_REAUTH_REQUIRED)

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)

    # Meta identifiers. Not secret — they appear in webhook payloads and API
    # paths — so they are stored in the clear and are safe to log.
    waba_id = Column(String, nullable=True, index=True)
    # Indexed because the inbound webhook routes by it: one callback URL
    # receives events for EVERY subscribed WABA, so `phone_number_id -> org`
    # is the lookup on every single incoming event. UNIQUE for the same reason:
    # that lookup takes .first(), so two rows sharing a number id would route
    # one tenant's delivery receipts and opt-outs to another tenant at random.
    phone_number_id = Column(String, nullable=True, index=True, unique=True)
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

    # The PIN used to register the number for Cloud API sending. Meta asks for
    # this same PIN again on any re-registration, so throwing it away means the
    # number can only be recovered by the tenant turning off two-step at Meta.
    # Encrypted: it is a second factor on their phone number.
    registration_pin = Column(Text, nullable=True)

    # Whether our app is actually subscribed to their WABA's webhooks. Stored
    # rather than assumed: the subscribe call can fail while everything else
    # succeeds, and the result is a tenant who sends fine but silently receives
    # no delivery receipts and — the part that matters — no opt-outs.
    app_subscribed = Column(Boolean, nullable=False, server_default=text("false"), default=False)

    # When a real, billed message last went out successfully from this account.
    # Bulk sending stays locked until this is set, so the first message a tenant
    # ever pays for is a test to their own phone rather than 300 failures to
    # their customers — the failure modes that only appear on a live send
    # (no payment method, template not really approved, number not registered)
    # surface at setup, with someone watching.
    verified_send_at = Column(DateTime(timezone=True), nullable=True)

    # Per-tenant ceiling on messages Meta may bill them for in a calendar month.
    # Meta's own limit is a throughput tier, not a spend limit, so without this
    # one bad upload is an unbounded charge on the tenant's card. NULL means the
    # application default applies.
    monthly_message_limit = Column(Integer, nullable=True)

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
    def can_test(self) -> bool:
        """Ready as far as Meta's setup goes — enough to send ONE test message."""
        return self.status == self.STATUS_READY

    @property
    def can_send(self) -> bool:
        """Ready for real campaigns.

        Three separate facts, because each one has burned a real onboarding:
        Meta says the account is set up, webhooks reach us (or opt-outs go in a
        bin), and one live message has actually been delivered and paid for.
        """
        return (self.status == self.STATUS_READY
                and self.app_subscribed
                and self.verified_send_at is not None)

    @property
    def setup_blocker(self) -> str | None:
        """Which of the three `can_send` facts is missing, for the UI to act on."""
        if self.status != self.STATUS_READY:
            return "status"
        if not self.app_subscribed:
            return "webhooks"
        if self.verified_send_at is None:
            return "test_send"
        return None
