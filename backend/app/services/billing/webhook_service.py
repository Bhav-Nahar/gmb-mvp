import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
import razorpay
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.models.organization import Organization
from app.models.billing_webhook_event import BillingWebhookEvent
from app.models.billing_transaction import BillingTransaction
from app.services.billing.pricing_service import PricingService

logger = logging.getLogger(__name__)


class WebhookService:
    """Handles Razorpay webhooks with idempotency."""

    @staticmethod
    def verify_signature(body: bytes, signature: str) -> bool:
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            logger.error("RAZORPAY_WEBHOOK_SECRET is not set")
            return False
        try:
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            client.utility.verify_webhook_signature(
                body.decode("utf-8"), signature, settings.RAZORPAY_WEBHOOK_SECRET
            )
            return True
        except razorpay.errors.SignatureVerificationError:
            return False
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False

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
            elif event_type == "subscription.cancelled":
                WebhookService._handle_subscription_cancelled(db, payload)
            elif event_type == "payment.captured":
                WebhookService._handle_payment_captured(db, payload)
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
        WebhookService.apply_subscription_charged(db, org, subscription, payment)

    @staticmethod
    def apply_subscription_charged(
        db: Session,
        org: Organization,
        subscription: Dict[str, Any],
        payment: Dict[str, Any] | None = None,
    ) -> None:
        """Grant the entitlements for an active/charged subscription and record the
        charge. Shared by the webhook and the reconciliation path so both apply
        identical state. The caller is responsible for locking `org` and committing.

        If a charge for this payment id has already been recorded, the ledger row is
        skipped so reconciliation after a delivered webhook (or vice-versa) does not
        double-count."""
        payment = payment or {}
        notes = subscription.get("notes", {})
        location_count = int(notes.get("location_count", "0") or 0)

        current_end = subscription.get("current_end")
        if current_end:
            org.ai_credits_reset_date = datetime.fromtimestamp(current_end, tz=timezone.utc)

        org.plan = "active"
        org.subscription_status = "active"
        org.grace_period_ends_at = None
        org.trial_ends_at = None
        org.subscription_ends_at = None
        org.razorpay_subscription_id = subscription.get("id")

        # Grant the entitlements that were paid for.
        if location_count > 0:
            org.location_quota = location_count
            org.monthly_ai_credits_balance = PricingService.get_credits_for_locations(location_count)

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
        ))

    @staticmethod
    def _handle_subscription_halted(db: Session, payload: Dict[str, Any]) -> None:
        org, _ = WebhookService._locked_org(db, payload, "subscription")
        if org:
            org.subscription_status = "past_due"
            org.grace_period_ends_at = datetime.now(timezone.utc) + timedelta(days=3)

    @staticmethod
    def _handle_subscription_cancelled(db: Session, payload: Dict[str, Any]) -> None:
        org, subscription = WebhookService._locked_org(db, payload, "subscription")
        if org:
            # Cancelled but still valid until the end of the paid period: stays
            # "active" with subscription_ends_at set; the periodic sweep locks it
            # once that date passes. A re-charge clears subscription_ends_at.
            org.subscription_status = "active"
            current_end = subscription.get("current_end")
            if current_end:
                org.subscription_ends_at = datetime.fromtimestamp(current_end, tz=timezone.utc)

    @staticmethod
    def _handle_payment_captured(db: Session, payload: Dict[str, Any]) -> None:
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        notes = payment.get("notes", {})
        if notes.get("type") != "topup":
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
        if payment_id:
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
