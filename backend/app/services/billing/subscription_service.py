import razorpay
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException
from app.core.config import settings
from app.models.organization import Organization
from app.services.billing.pricing_service import PricingService


_plan_id_cache: dict = {}


class SubscriptionService:
    """Handles Razorpay subscriptions, orders, and customer management.

    Pricing is computed server-side from the location count — the client only
    chooses how many locations and the billing interval, never the amount."""

    @staticmethod
    def get_razorpay_client() -> razorpay.Client:
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise HTTPException(status_code=500, detail="Razorpay is not configured")
        return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    @staticmethod
    def ensure_razorpay_customer(db: Session, org_id: int, org_name: str, user_email: str) -> str:
        """Get-or-create the org's Razorpay customer id under a row lock."""
        stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        if org.razorpay_customer_id:
            return org.razorpay_customer_id

        client = SubscriptionService.get_razorpay_client()
        try:
            customer = client.customer.create(data={
                "name": org_name,
                "email": user_email,
                "notes": {"organization_id": str(org_id)},
            })
            org.razorpay_customer_id = customer["id"]
            db.commit()
            return org.razorpay_customer_id
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to create Razorpay customer: {str(e)}")

    @staticmethod
    def _get_or_create_plan(location_count: int, interval: str) -> str:
        """Get-or-create a Razorpay plan for this (location_count, interval) pair.

        Plans are cached in-process so repeated checkout attempts (e.g. the user
        toggling monthly/annual or retrying) reuse the same plan instead of
        creating orphan plans on every call."""
        cache_key = (location_count, interval)
        if cache_key in _plan_id_cache:
            return _plan_id_cache[cache_key]

        client = SubscriptionService.get_razorpay_client()
        amount = PricingService.compute_price_paise(location_count, interval)
        period = "yearly" if interval == "annual" else "monthly"
        try:
            plan = client.plan.create(data={
                "period": period,
                "interval": 1,
                "item": {
                    "name": f"GMB {location_count} location(s) ({interval})",
                    "amount": amount,
                    "currency": "INR",
                },
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create plan: {str(e)}")

        _plan_id_cache[cache_key] = plan["id"]
        return plan["id"]

    @staticmethod
    def create_subscription_checkout(
        db: Session,
        org_id: int,
        org_name: str,
        user_email: str,
        location_count: int,
        interval: str = "monthly",
    ) -> Dict[str, Any]:
        PricingService.validate_location_count(location_count)
        if interval not in ("monthly", "annual"):
            raise HTTPException(status_code=400, detail="interval must be 'monthly' or 'annual'")

        customer_id = SubscriptionService.ensure_razorpay_customer(db, org_id, org_name, user_email)
        plan_id = SubscriptionService._get_or_create_plan(location_count, interval)
        client = SubscriptionService.get_razorpay_client()
        credits = PricingService.get_credits_for_locations(location_count)

        try:
            subscription = client.subscription.create(data={
                "plan_id": plan_id,
                "customer_id": customer_id,
                "quantity": 1,
                "total_count": plan_config_total_count(interval),
                "notes": {
                    "organization_id": str(org_id),
                    "type": "subscription",
                    "location_count": str(location_count),
                    "interval": interval,
                    "credits": str(credits),
                },
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create subscription: {str(e)}")

        # Persist the subscription id so we can reconcile / cancel later. Entitlements
        # (quota, credits) are granted by the subscription.charged webhook.
        stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = db.scalars(stmt).first()
        if org:
            org.razorpay_subscription_id = subscription["id"]
            org.billing_cycle = interval
            db.commit()

        return subscription

    @staticmethod
    def create_topup_order(db: Session, org_id: int, org_name: str, user_email: str, pack_key: str) -> Dict[str, Any]:
        customer_id = SubscriptionService.ensure_razorpay_customer(db, org_id, org_name, user_email)
        client = SubscriptionService.get_razorpay_client()
        pack = PricingService.get_topup_pack(pack_key)

        try:
            return client.order.create(data={
                "amount": pack["price_paise"],
                "currency": "INR",
                "receipt": f"topup_org_{org_id}",
                "notes": {
                    "organization_id": str(org_id),
                    "type": "topup",
                    "credits": str(pack["credits"]),
                },
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create top-up order: {str(e)}")


    @staticmethod
    def reconcile_subscription(db: Session, org_id: int) -> bool:
        """Pull the org's subscription straight from Razorpay and apply entitlements
        if it is active but our record says otherwise. This is the safety net for a
        missed/delayed `subscription.charged` webhook — called both on the user's
        return from checkout and by a periodic sweep.

        Returns True if the org is active after reconciliation."""
        from app.services.billing.webhook_service import WebhookService

        stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            return False
        if not org.razorpay_subscription_id:
            return org.subscription_status == "active"
        if org.subscription_status == "active":
            return True

        client = SubscriptionService.get_razorpay_client()
        try:
            subscription = client.subscription.fetch(org.razorpay_subscription_id)
        except Exception:
            return False

        # Razorpay marks a paid subscription "active"; "authenticated" means the
        # mandate is set up but the first charge hasn't landed yet.
        if subscription.get("status") not in ("active", "authenticated"):
            return False

        WebhookService.apply_subscription_charged(db, org, subscription, payment=None)
        db.commit()
        return True

    @staticmethod
    def reconcile_topup_payment(db: Session, org_id: int, payment_id: str) -> bool:
        """Apply a top-up credit grant from a captured payment, verifying with
        Razorpay. Safety net for a missed `payment.captured` webhook."""
        from app.services.billing.webhook_service import WebhookService

        client = SubscriptionService.get_razorpay_client()
        try:
            payment = client.payment.fetch(payment_id)
        except Exception:
            return False

        if payment.get("status") != "captured":
            return False

        # The top-up notes (type, credits, organization_id) live on the ORDER, not
        # necessarily on the payment, so fetch the order for the authoritative notes.
        notes = payment.get("notes") or {}
        order_id = payment.get("order_id")
        if order_id:
            try:
                order = client.order.fetch(order_id)
                notes = order.get("notes") or notes
            except Exception:
                pass

        # Refuse to grant against a payment that isn't this org's top-up.
        if notes.get("type") != "topup" or str(notes.get("organization_id")) != str(org_id):
            return False

        payment_with_notes = {**payment, "notes": notes}
        WebhookService._handle_payment_captured(
            db, {"payload": {"payment": {"entity": payment_with_notes}}}
        )
        db.commit()
        return True


def plan_config_total_count(interval: str) -> int:
    # 10 years of billing cycles, a conventional "until cancelled" horizon.
    return 10 if interval == "annual" else 120
