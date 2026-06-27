import logging
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.models.organization import Organization
from app.models.location import Location
from app.models.billing_webhook_event import BillingWebhookEvent
from app.models.billing_transaction import BillingTransaction
from app.services.billing.pricing_service import PricingService
from app.core import plan_config

logger = logging.getLogger(__name__)


class WebhookService:
    """Handles Razorpay webhooks with idempotency."""

    @staticmethod
    def verify_signature(body: bytes, signature: str) -> bool:
        """Verify the Razorpay webhook signature with a pure-local HMAC-SHA256 compare.

        This is exactly what Razorpay's SDK helper does, but without constructing an
        API client — so a transient/unexpected error can never be silently misread as
        'invalid signature' and cause us to drop (and never retry) a real event."""
        secret = settings.RAZORPAY_WEBHOOK_SECRET
        if not secret:
            logger.error("RAZORPAY_WEBHOOK_SECRET is not set")
            return False
        if not signature:
            return False
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def process_webhook(db: Session, event_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """Process a webhook exactly once.

        The idempotency marker and the business changes are committed in a SINGLE
        transaction: either everything lands or nothing does. A duplicate delivery
        hits the unique constraint and is skipped; a genuine failure rolls back the
        marker too, so Razorpay's retry will reprocess cleanly."""
        # Pre-check so a duplicate doesn't waste work (the unique constraint below is
        # the real guarantee against races).
        existing = db.query(BillingWebhookEvent).filter(
            BillingWebhookEvent.razorpay_event_id == event_id
        ).first()
        if existing:
            logger.info(f"Webhook {event_id} already processed. Skipping.")
            return

        try:
            db.add(BillingWebhookEvent(
                razorpay_event_id=event_id,
                event_type=event_type,
                payload=payload,
            ))

            if event_type == "subscription.charged":
                WebhookService._handle_subscription_charged(db, payload)
            elif event_type == "subscription.halted":
                WebhookService._handle_subscription_halted(db, payload)
            elif event_type in ("subscription.pending", "subscription.paused"):
                # A charge failed and Razorpay is retrying. Treat like halted so the org
                # enters the grace window rather than silently staying fully active.
                WebhookService._handle_subscription_halted(db, payload)
            elif event_type == "subscription.cancelled":
                WebhookService._handle_subscription_cancelled(db, payload)
            elif event_type == "subscription.completed":
                # total_count reached — no further charges. Close out the paid period so
                # the periodic sweep locks the org once it lapses.
                WebhookService._handle_subscription_cancelled(db, payload)
            elif event_type == "payment.captured":
                WebhookService._handle_payment_captured(db, payload)
            elif event_type in ("refund.created", "refund.processed"):
                WebhookService._handle_refund(db, payload)
            elif event_type == "payment.failed":
                ent = payload.get("payload", {}).get("payment", {}).get("entity", {})
                logger.warning("payment.failed for order %s payment %s",
                               ent.get("order_id"), ent.get("id"))
            else:
                logger.info(f"Unhandled webhook event type: {event_type}")

            db.commit()
        except IntegrityError:
            # Concurrent delivery beat us to the marker — already processed.
            db.rollback()
            logger.info(f"Webhook {event_id} processed concurrently. Skipping.")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to process webhook {event_id}: {str(e)}")
            # Re-raise so the endpoint returns 500 and Razorpay retries. Nothing was
            # committed (marker included), so the retry reprocesses cleanly.
            raise

    @staticmethod
    def _locked_org(db: Session, payload: Dict[str, Any], entity: str):
        ent = payload.get("payload", {}).get(entity, {}).get("entity", {})
        org_id_str = ent.get("notes", {}).get("organization_id")
        if not org_id_str:
            logger.error(f"No organization_id in {entity} notes")
            return None, ent
        stmt = select(Organization).where(Organization.id == int(org_id_str)).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            logger.error(f"Organization {org_id_str} not found")
        return org, ent

    @staticmethod
    def _handle_subscription_charged(db: Session, payload: Dict[str, Any]) -> None:
        org, subscription = WebhookService._locked_org(db, payload, "subscription")
        if not org:
            return
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        invoice = payload.get("payload", {}).get("invoice", {}).get("entity", {})
        WebhookService.apply_subscription_charged(db, org, subscription, payment, invoice)

    @staticmethod
    def apply_subscription_charged(
        db: Session,
        org: Organization,
        subscription: Dict[str, Any],
        payment: Dict[str, Any] | None = None,
        invoice: Dict[str, Any] | None = None,
    ) -> None:
        """Grant the entitlements for an active/charged subscription and record the
        charge. Shared by the webhook and the reconciliation path so both apply
        identical state. The caller is responsible for locking `org` and committing.

        If a charge for this payment id has already been recorded, the ledger row is
        skipped so reconciliation after a delivered webhook (or vice-versa) does not
        double-count."""
        payment = payment or {}
        notes = subscription.get("notes", {})
        notes_location_count = int(notes.get("location_count", "0") or 0)
        subscription_id = subscription.get("id")

        # UPI re-mandate cutover: the user approved a NEW subscription at the higher
        # amount while a re-mandate was pending. Its first charge arriving (a different
        # subscription id than the one we currently track) is the signal to switch over
        # — cancel the OLD mandate now that the new one is live, and clear the flag so
        # the paid-quota bookkeeping below treats the new mandate as covering everything.
        old_sub_id = org.razorpay_subscription_id
        prev_status = org.subscription_status
        is_cutover = (
            org.subscription_needs_remandate
            and subscription_id
            and old_sub_id
            and subscription_id != old_sub_id
        )
        if is_cutover:
            from app.services.billing.subscription_service import SubscriptionService
            try:
                client = SubscriptionService.get_razorpay_client()
                client.subscription.cancel(old_sub_id, {"cancel_at_cycle_end": 0})
            except Exception as e:
                logger.error("Re-mandate cutover: failed to cancel old subscription %s for org %s: %s",
                             old_sub_id, org.id, e)
            org.subscription_needs_remandate = False
            org.remandate_due_at = None
            org.subscription_payment_mode = "upi"

        current_end = subscription.get("current_end")
        if current_end:
            org.ai_credits_reset_date = datetime.fromtimestamp(current_end, tz=timezone.utc)

        org.plan = "active"
        org.subscription_status = "active"
        org.grace_period_ends_at = None
        org.trial_ends_at = None
        org.subscription_ends_at = None
        org.razorpay_subscription_id = subscription_id

        # Restore the product tier chosen at checkout (carried in the subscription
        # notes, so it survives renewals and webhook-only activation).
        notes_plan_tier = notes.get("plan_tier")
        if notes_plan_tier:
            org.plan_tier = notes_plan_tier

        # Decide the paid location count.
        #
        # The notes carry the count chosen at checkout — authoritative for the FIRST
        # charge of a subscription (initial signup or an upgrade-via-re-checkout, where
        # org.location_quota may still hold the trial default or a previous count).
        #
        # On RENEWALS of a subscription we've already charged, the ORG is the source of
        # truth: mid-cycle location unlocks bump org.location_quota (and the Razorpay
        # plan amount) without touching subscription notes, so we must NOT reset quota
        # back to the stale notes value.
        #
        # A renewal is detected EITHER by a prior subscription_charge ledger row for this
        # subscription id, OR by the org already being active on this same subscription —
        # the latter covers the case where the first charge was applied via the reconcile
        # fast-path (which writes no ledger row): without it, a missed first-charge
        # webhook would make the next renewal look like a first charge and claw back every
        # mid-cycle add-on location.
        prior_charge = None
        if subscription_id:
            prior_charge = db.query(BillingTransaction).filter(
                BillingTransaction.razorpay_subscription_id == subscription_id,
                BillingTransaction.transaction_type == "subscription_charge",
            ).first()
        is_renewal = prior_charge is not None or (
            prev_status == "active" and old_sub_id == subscription_id
        )

        if is_renewal and org.location_quota:
            effective_count = org.location_quota
        else:
            effective_count = notes_location_count or (org.location_quota or 0)

        if effective_count and effective_count > 0:
            org.location_quota = effective_count
            org.monthly_ai_credits_balance = PricingService.get_credits_for_locations(effective_count, org.plan_tier or "basic")

            # Keep paid_location_quota in step with what the mandate actually bills.
            # For a healthy charge that equals the entitled quota, the mandate is paying
            # for everything. While a UPI re-mandate is pending we deliberately DON'T
            # touch it — it stays frozen at the lower (old-mandate) level so the grace
            # sweep knows how far to claw back if the user never re-authorizes.
            if not org.subscription_needs_remandate:
                org.paid_location_quota = effective_count

            # Trial gives every location 'active' for free (up to the trial quota). On
            # the FIRST paid charge the org may convert to a SMALLER paid quota than the
            # number of currently-active locations — the grandfathering rule in the sync
            # task never reclaims those, so the surplus would stay active for free.
            # Enforce the paid quota here: keep the oldest `effective_count` active
            # locations, lock the rest back to 'pending_payment'. Only on conversion
            # (not renewals), so mid-cycle add-ons are never clawed back.
            if not is_renewal:
                active_locs = db.query(Location).filter(
                    Location.organization_id == org.id,
                    Location.billing_status == "active",
                ).order_by(Location.id.asc()).all()
                for loc in active_locs[effective_count:]:
                    loc.billing_status = "pending_payment"

        payment_id = payment.get("id")
        if not payment_id:
            # Reconciliation path (no payment entity): entitlements are applied
            # above; the authoritative ledger row is written by the webhook, which
            # carries the real payment id. Skip writing a phantom null-id row.
            return
        already = db.query(BillingTransaction).filter(
            BillingTransaction.razorpay_payment_id == payment_id
        ).first()
        if already:
            return

        db.add(BillingTransaction(
            organization_id=org.id,
            transaction_type="subscription_charge",
            amount_paise=payment.get("amount", 0),
            currency=payment.get("currency", "INR"),
            status="success",
            razorpay_payment_id=payment_id,
            razorpay_order_id=payment.get("order_id"),
            razorpay_subscription_id=subscription.get("id"),
            invoice_url=(invoice or {}).get("short_url"),
        ))

        # First paid charge = acquisition -> fire server-side ad conversions (Meta CAPI +
        # Google Ads). Renewals are excluded so we don't inflate ad conversions. Enqueued
        # to Celery so external HTTP never runs while we hold the org row lock; best-effort.
        if not is_renewal:
            try:
                from app.models.user import User
                owner = (
                    db.query(User)
                    .filter(User.organization_id == org.id)
                    .order_by(User.id.asc())
                    .first()
                )
                attribution = {
                    k: getattr(org, k) for k in
                    ("gclid", "gbraid", "wbraid", "fbclid", "fbp", "fbc", "landing_page")
                    if getattr(org, k, None)
                }
                from app.worker import celery as celery_app
                celery_app.send_task(
                    "app.tasks.fire_purchase_conversion_task",
                    kwargs={
                        "payment_id": payment_id,
                        "amount_paise": payment.get("amount", 0),
                        "currency": payment.get("currency", "INR"),
                        "email": owner.email if owner else None,
                        "attribution": attribution,
                    },
                )
            except Exception as e:
                logger.error("Failed to enqueue purchase conversion for org %s: %s", org.id, e)

    @staticmethod
    def _is_current_subscription(org: Organization, subscription: Dict[str, Any]) -> bool:
        """Whether this subscription event targets the org's CURRENT mandate. Lifecycle
        events for a superseded subscription — e.g. the old mandate we cancel during a UPI
        re-mandate cutover — must be ignored so they don't corrupt the new mandate's
        state."""
        sub_id = subscription.get("id")
        return not (sub_id and org.razorpay_subscription_id and sub_id != org.razorpay_subscription_id)

    @staticmethod
    def _handle_subscription_halted(db: Session, payload: Dict[str, Any]) -> None:
        org, subscription = WebhookService._locked_org(db, payload, "subscription")
        if org and WebhookService._is_current_subscription(org, subscription):
            org.subscription_status = "past_due"
            org.grace_period_ends_at = datetime.now(timezone.utc) + timedelta(days=3)

    @staticmethod
    def _handle_subscription_cancelled(db: Session, payload: Dict[str, Any]) -> None:
        org, subscription = WebhookService._locked_org(db, payload, "subscription")
        if not org:
            return
        # Ignore cancellation of a superseded subscription (the old mandate retired by a
        # re-mandate cutover).
        if not WebhookService._is_current_subscription(org, subscription):
            return
        # Only downgrade from active; never resurrect a locked/past_due org that a late
        # cancellation event happens to arrive for.
        if org.subscription_status != "active":
            return
        # Cancelled but still valid until the end of the paid period: stays "active" with
        # subscription_ends_at set; the periodic sweep locks it once that date passes.
        current_end = subscription.get("current_end")
        if current_end:
            org.subscription_ends_at = datetime.fromtimestamp(current_end, tz=timezone.utc)

    @staticmethod
    def _handle_refund(db: Session, payload: Dict[str, Any]) -> None:
        """Reverse entitlements for a refunded payment.

        - Top-up credit refunds: credits are clawed back directly.
        - Quota-bearing refunds (subscription/add-on): a FULL refund locks the org
          until it re-subscribes, because we don't track exactly which locations an
          add-on unlocked and reclaiming a specific one is a product decision. Failing
          CLOSED here is what kills the "pay -> consume credits/syncs -> refund ->
          keep all entitlements" abuse path (BE-BILLING-2). Partial refunds are flagged
          for manual reconciliation without locking.

        Idempotent: a `refund_reversal` ledger row keyed on the payment id is written
        exactly once (also backstopped by the partial-unique DB index)."""
        refund = payload.get("payload", {}).get("refund", {}).get("entity", {})
        payment_id = refund.get("payment_id")
        if not payment_id:
            return
        txn = db.query(BillingTransaction).filter(
            BillingTransaction.razorpay_payment_id == payment_id,
            BillingTransaction.transaction_type != "refund_reversal",
        ).first()
        if not txn:
            logger.warning("Refund for unknown payment %s; nothing to reverse.", payment_id)
            return

        # Idempotency: skip if this refund was already reversed.
        already_reversed = db.query(BillingTransaction).filter(
            BillingTransaction.razorpay_payment_id == payment_id,
            BillingTransaction.transaction_type == "refund_reversal",
        ).first()
        if already_reversed:
            logger.info("Refund for payment %s already reversed. Skipping.", payment_id)
            return

        stmt = select(Organization).where(Organization.id == txn.organization_id).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            return

        refund_paise = refund.get("amount") or 0
        original_paise = txn.amount_paise or 0
        is_full_refund = original_paise > 0 and refund_paise >= original_paise

        if txn.transaction_type == "topup_charge" and txn.credits:
            org.topup_ai_credits_balance = max(0, (org.topup_ai_credits_balance or 0) - txn.credits)
            logger.info("Reversed %s top-up credits for org %s on refund of %s",
                        txn.credits, org.id, payment_id)
        elif txn.transaction_type in ("subscription_charge", "location_addon"):
            if is_full_refund:
                # Revoke entitlement by locking the org until it pays again. The exact
                # quota/credit figures are reconciled manually, but the org cannot keep
                # serving paid features for free in the meantime.
                org.subscription_status = "locked"
                org.grace_period_ends_at = None
                org.subscription_ends_at = None
                logger.warning(
                    "FULL refund of %s payment %s for org %s: org LOCKED pending "
                    "re-subscription. Verify quota/credits manually.",
                    txn.transaction_type, payment_id, org.id,
                )
            else:
                logger.warning(
                    "PARTIAL refund (%s of %s paise) of %s payment %s for org %s needs "
                    "MANUAL reconciliation.",
                    refund_paise, original_paise, txn.transaction_type, payment_id, org.id,
                )
        else:
            logger.warning(
                "Refund of payment %s (type=%s) for org %s has no automatic reversal rule; "
                "manual review required.", payment_id, txn.transaction_type, org.id,
            )

        # Record the reversal so a redelivered refund webhook is a no-op.
        db.add(BillingTransaction(
            organization_id=org.id,
            transaction_type="refund_reversal",
            amount_paise=refund_paise,
            currency=refund.get("currency") or txn.currency,
            status="success",
            razorpay_payment_id=payment_id,
            razorpay_order_id=txn.razorpay_order_id,
            razorpay_subscription_id=txn.razorpay_subscription_id,
            source="razorpay_refund",
        ))

    @staticmethod
    def _handle_payment_captured(db: Session, payload: Dict[str, Any]) -> None:
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        notes = payment.get("notes") or {}

        # Razorpay keeps the notes we set at order-creation on the ORDER, not on the
        # payment. The payment.captured webhook's payment entity therefore usually has
        # empty notes, so fetch the order for the authoritative notes — mirroring
        # reconcile_location_addon_payment / reconcile_topup_payment. Without this the
        # webhook silently no-ops and add-on/top-up payments never get applied.
        if not notes.get("type"):
            order_id = payment.get("order_id")
            if order_id:
                try:
                    from app.services.billing.subscription_service import SubscriptionService
                    order = SubscriptionService.get_razorpay_client().order.fetch(order_id)
                    notes = order.get("notes") or notes
                except Exception as e:
                    logger.error("Failed to fetch order %s for payment.captured notes: %s",
                                 order_id, e)

        note_type = notes.get("type")
        if note_type == "location_addon":
            WebhookService._handle_location_addon_captured(db, payment, notes)
            return
        if note_type != "topup":
            # Subscription payments arrive via subscription.charged.
            return

        org_id_str = notes.get("organization_id")
        if not org_id_str:
            return
        stmt = select(Organization).where(Organization.id == int(org_id_str)).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            return

        payment_id = payment.get("id")
        # No payment id = no idempotency key. Granting credits here would double-apply on
        # webhook redelivery, so refuse rather than risk it.
        if not payment_id:
            logger.error("Top-up captured with no payment id for org %s; skipping grant.", org.id)
            return
        already = db.query(BillingTransaction).filter(
            BillingTransaction.razorpay_payment_id == payment_id
        ).first()
        if already:
            return

        credits_str = notes.get("credits", "0")
        credits_to_add = int(credits_str) if str(credits_str).isdigit() else 0
        org.topup_ai_credits_balance += credits_to_add

        db.add(BillingTransaction(
            organization_id=org.id,
            transaction_type="topup_charge",
            credits=credits_to_add,
            amount_paise=payment.get("amount", 0),
            currency=payment.get("currency", "INR"),
            status="success",
            razorpay_payment_id=payment.get("id"),
            razorpay_order_id=payment.get("order_id"),
        ))

    @staticmethod
    def _handle_location_addon_captured(db: Session, payment: Dict[str, Any], notes: Dict[str, Any]) -> None:
        """Unlock locations paid for by a prorated add-on charge: bump quota, grant the
        full per-location credits, flip the locations to 'active', and enqueue their
        deferred sync. Idempotent on the payment id."""
        org_id_str = notes.get("organization_id")
        if not org_id_str:
            return
        stmt = select(Organization).where(Organization.id == int(org_id_str)).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            return

        payment_id = payment.get("id")
        # No payment id = no idempotency key. Unlocking + bumping quota here would
        # double-apply on webhook redelivery, so refuse rather than risk it.
        if not payment_id:
            logger.error("Add-on captured with no payment id for org %s; skipping unlock.", org.id)
            return
        already = db.query(BillingTransaction).filter(
            BillingTransaction.razorpay_payment_id == payment_id
        ).first()
        if already:
            return

        added = int(notes.get("added", "0") or 0)
        loc_ids = [int(x) for x in str(notes.get("location_ids", "")).split(",") if x.strip().isdigit()]

        # Only unlock locations that are still pending and belong to this org.
        unlocked_ids = []
        if loc_ids:
            rows = db.query(Location).filter(
                Location.id.in_(loc_ids),
                Location.organization_id == org.id,
                Location.billing_status == "pending_payment",
            ).all()
            for loc in rows:
                loc.billing_status = "active"
                unlocked_ids.append(loc.id)

        # Grant entitlements for what was actually unlocked (defensive: never grant for
        # already-active or foreign ids). The ORG is the source of truth for quota.
        granted = len(unlocked_ids)
        # Quota the current mandate actually bills, BEFORE this unlock bumps it. If the
        # plan upgrade can't be scheduled (UPI), this is the level we fall back to when
        # the grace period lapses. NULL on legacy orgs = "mandate covers current quota".
        prior_paid_quota = org.paid_location_quota
        if prior_paid_quota is None:
            prior_paid_quota = org.location_quota or 0
        if granted > 0:
            org.location_quota = (org.location_quota or 0) + granted
            org.monthly_ai_credits_balance = (org.monthly_ai_credits_balance or 0) \
                + granted * plan_config.get_plan(org.plan_tier)["credits_per_location"]

        db.add(BillingTransaction(
            organization_id=org.id,
            transaction_type="location_addon",
            amount_paise=payment.get("amount", 0),
            currency=payment.get("currency", "INR"),
            status="success",
            razorpay_payment_id=payment_id,
            razorpay_order_id=payment.get("order_id"),
            razorpay_subscription_id=org.razorpay_subscription_id,
        ))

        # Raise the recurring amount for future cycles (best-effort) and kick off the
        # deferred sync for the freshly-unlocked locations. Both are outside the DB
        # entitlement grant so a transient failure can't undo a paid unlock.
        if granted > 0:
            from app.services.billing.subscription_service import SubscriptionService
            result = SubscriptionService.update_subscription_plan_for_quota(db, org.id)
            if result == "needs_remandate":
                # UPI mandate can't be raised via API — the user must approve a NEW
                # mandate. Keep the locations active for the cycle they just paid for,
                # but start the grace clock: if not re-authorized by the renewal date
                # + 3 days, the surplus above prior_paid_quota gets re-locked.
                org.subscription_needs_remandate = True
                org.paid_location_quota = prior_paid_quota
                # Grace deadline = renewal/next-charge date (tracked as
                # ai_credits_reset_date) + 3 days. Fall back to a full cycle from now when
                # we don't have a reset date yet, so the deadline is NEVER null — a null
                # deadline is excluded by the grace sweep, which would leave the surplus
                # locations active for free indefinitely.
                from app.services.billing.subscription_service import _DAYS_IN_CYCLE
                due_base = org.ai_credits_reset_date
                if not due_base:
                    cycle_days = _DAYS_IN_CYCLE.get(org.billing_cycle or "monthly", 30)
                    due_base = datetime.now(timezone.utc) + timedelta(days=cycle_days)
                org.remandate_due_at = due_base + timedelta(days=3)
            elif result == "upgraded":
                # Card mandate: the plan rises automatically at cycle end; clear any
                # stale re-mandate state and treat the new quota as paid-for.
                org.subscription_needs_remandate = False
                org.remandate_due_at = None
                org.paid_location_quota = org.location_quota
            try:
                from app.worker import celery as celery_app
                celery_app.send_task(
                    "app.tasks.sync_reviews_chunk_task",
                    args=[unlocked_ids, org.id, "Manual", None],
                )
                for loc_id in unlocked_ids:
                    celery_app.send_task("app.tasks.sync_location_attributes_task", args=[loc_id])
            except Exception as e:
                logger.error("Failed to enqueue deferred sync for unlocked locations %s: %s",
                             unlocked_ids, e, exc_info=True)
