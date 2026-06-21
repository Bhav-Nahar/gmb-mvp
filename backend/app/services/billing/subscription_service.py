import logging
import razorpay
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.core.config import settings
from app.core import plan_config
from app.models.organization import Organization
from app.models.location import Location
from app.services.billing.pricing_service import PricingService

logger = logging.getLogger(__name__)

# Approximate cycle lengths used for proration when we don't fetch the exact
# current_start from Razorpay. Conventional billing-month / billing-year.
_DAYS_IN_CYCLE = {"monthly": 30, "annual": 365}
# Razorpay rejects orders below ₹1. Floor tiny prorated amounts to this.
_MIN_ORDER_PAISE = 100


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
    def _current_mode() -> str:
        """'test' or 'live' for the configured keys. Cached Razorpay customer/plan ids
        are namespaced by this because a test id is invalid under live keys (and vice
        versa); guarded against an unset key id (would otherwise AttributeError → 500)."""
        return "test" if (settings.RAZORPAY_KEY_ID or "").startswith("rzp_test_") else "live"

    @staticmethod
    def ensure_razorpay_customer(db: Session, org_id: int, org_name: str, user_email: str) -> str:
        """Get-or-create the org's Razorpay customer id under a row lock."""
        stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        current_mode = SubscriptionService._current_mode()

        if org.razorpay_customer_id:
            stored_id = org.razorpay_customer_id
            if ":" in stored_id:
                mode, cust_id = stored_id.split(":", 1)
                if mode == current_mode:
                    return cust_id
            else:
                # Legacy check: if in test mode, trust it. In live mode, ignore/re-verify.
                if current_mode == "test":
                    return stored_id

        client = SubscriptionService.get_razorpay_client()
        try:
            # fail_existing=0 tells Razorpay to return the existing customer for this
            # email instead of throwing "already exists". This makes the call idempotent
            # and avoids extra list API calls (which were causing rate-limit 429s).
            customer = client.customer.create(data={
                "name": org_name,
                "email": user_email,
                "fail_existing": "0",
                "notes": {"organization_id": str(org_id)},
            })
            cust_id = customer["id"]
            org.razorpay_customer_id = f"{current_mode}:{cust_id}"
            db.commit()
            return cust_id
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create Razorpay customer for org {org_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create Razorpay customer: {str(e)}")

    @staticmethod
    def _get_or_create_plan(db: Session, location_count: int, interval: str, plan_tier: str = "basic") -> str:
        """Get-or-create a Razorpay plan for this (location_count, interval, amount).

        Plan ids are cached durably in the razorpay_plans table so repeated/cold
        checkouts reuse the same plan instead of creating an orphan plan on every
        call (which caused plan sprawl and rate-limiting). The amount is
        part of the key so a pricing change yields a new plan, never a stale one.
        Tier + GST both feed the amount, so basic/pro (and pre/post-GST) never collide
        on a stale cached plan."""
        from app.models.razorpay_plan import RazorpayPlan

        base = PricingService.compute_price_paise(location_count, interval, plan_tier)
        amount = plan_config.price_with_gst(base)["total_paise"]  # GST-inclusive: what Razorpay bills
        current_mode = SubscriptionService._current_mode()

        existing_plans = db.query(RazorpayPlan).filter(
            RazorpayPlan.location_count == location_count,
            RazorpayPlan.interval == interval,
            RazorpayPlan.amount_paise == amount,
        ).all()

        for plan in existing_plans:
            stored_id = plan.razorpay_plan_id
            if ":" in stored_id:
                mode, plan_id = stored_id.split(":", 1)
                if mode == current_mode:
                    return plan_id
            else:
                # Legacy check: if in test mode, trust it.
                if current_mode == "test":
                    return stored_id

        client = SubscriptionService.get_razorpay_client()
        period = "yearly" if interval == "annual" else "monthly"
        try:
            plan = client.plan.create(data={
                "period": period,
                "interval": 1,
                "item": {
                    "name": f"GMB {plan_tier} {location_count} location(s) ({interval})",
                    "amount": amount,
                    "currency": "INR",
                },
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create plan: {str(e)}")

        plan_id = plan["id"]
        prefixed_plan_id = f"{current_mode}:{plan_id}"

        db.add(RazorpayPlan(
            location_count=location_count,
            interval=interval,
            amount_paise=amount,
            razorpay_plan_id=prefixed_plan_id,
            mode=current_mode,
        ))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing_plans = db.query(RazorpayPlan).filter(
                RazorpayPlan.location_count == location_count,
                RazorpayPlan.interval == interval,
                RazorpayPlan.amount_paise == amount,
            ).all()
            for plan in existing_plans:
                stored_id = plan.razorpay_plan_id
                if ":" in stored_id:
                    mode, plan_id = stored_id.split(":", 1)
                    if mode == current_mode:
                        return plan_id
            return plan_id
        return plan_id

    @staticmethod
    def create_subscription_checkout(
        db: Session,
        org_id: int,
        org_name: str,
        user_email: str,
        location_count: int,
        interval: str = "monthly",
        plan_tier: str = "basic",
    ) -> Dict[str, Any]:
        PricingService.validate_location_count(location_count)
        if interval not in ("monthly", "annual"):
            raise HTTPException(status_code=400, detail="interval must be 'monthly' or 'annual'")
        if plan_tier not in plan_config.PLANS:
            raise HTTPException(status_code=400, detail="Unknown plan tier")

        customer_id = SubscriptionService.ensure_razorpay_customer(db, org_id, org_name, user_email)
        plan_id = SubscriptionService._get_or_create_plan(db, location_count, interval, plan_tier)
        client = SubscriptionService.get_razorpay_client()
        credits = PricingService.get_credits_for_locations(location_count, plan_tier)

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
                    "plan_tier": plan_tier,
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
    def create_remandate_subscription(
        db: Session, org_id: int, org_name: str, user_email: str
    ) -> Dict[str, Any]:
        """Create a NEW subscription at the plan matching the org's current
        location_quota, for a UPI org that needs a higher mandate. Unlike
        create_subscription_checkout this does NOT overwrite org.razorpay_subscription_id
        — the old mandate keeps billing until the new one's first charge triggers the
        cutover (apply_subscription_charged), so there is never a coverage gap."""
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        if not org.subscription_needs_remandate:
            raise HTTPException(status_code=409, detail="No re-mandate is pending for this organization.")

        location_count = org.location_quota or 0
        interval = org.billing_cycle or "monthly"
        plan_tier = org.plan_tier or "basic"
        PricingService.validate_location_count(location_count)

        customer_id = SubscriptionService.ensure_razorpay_customer(db, org_id, org_name, user_email)
        plan_id = SubscriptionService._get_or_create_plan(db, location_count, interval, plan_tier)
        client = SubscriptionService.get_razorpay_client()
        credits = PricingService.get_credits_for_locations(location_count, plan_tier)

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
                    "plan_tier": plan_tier,
                    "remandate": "1",
                },
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create re-mandate subscription: {str(e)}")

        return subscription

    @staticmethod
    def reconcile_remandate(db: Session, org_id: int, new_subscription_id: str) -> bool:
        """Fast path for re-mandate: pull the freshly-approved subscription from Razorpay
        and, if it's active/authenticated, apply the cutover (cancel old, switch over,
        grant full quota). The webhook is the backstop; both are idempotent."""
        stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            return False
        # Already switched over (webhook beat us to it).
        if org.razorpay_subscription_id == new_subscription_id and not org.subscription_needs_remandate:
            return True

        client = SubscriptionService.get_razorpay_client()
        try:
            subscription = client.subscription.fetch(new_subscription_id)
        except Exception:
            return False
        if str(subscription.get("notes", {}).get("organization_id")) != str(org_id):
            return False
        # Require the new mandate to have actually CHARGED before cutting over — an
        # 'authenticated' mandate is approved but unpaid; cancelling the old one then
        # would leave a coverage gap. The subscription.charged webhook handles that case.
        if subscription.get("status") != "active":
            return False

        from app.services.billing.webhook_service import WebhookService
        WebhookService.apply_subscription_charged(db, org, subscription, payment=None)
        db.commit()
        return True

    @staticmethod
    def create_topup_order(db: Session, org_id: int, org_name: str, user_email: str, pack_key: str) -> Dict[str, Any]:
        customer_id = SubscriptionService.ensure_razorpay_customer(db, org_id, org_name, user_email)
        client = SubscriptionService.get_razorpay_client()
        pack = PricingService.get_topup_pack(pack_key)
        amount = plan_config.price_with_gst(pack["price_paise"])["total_paise"]  # GST-inclusive

        try:
            return client.order.create(data={
                "amount": amount,
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
    def _cycle_days_remaining(org: Organization, interval: str) -> tuple[int, int]:
        """(days_left, days_in_cycle) for the org's current billing cycle.

        Uses ai_credits_reset_date (the Razorpay current_end we persist) as the cycle
        end. Falls back to a full cycle if we don't have a reset date yet."""
        days_in_cycle = _DAYS_IN_CYCLE.get(interval, 30)
        reset = org.ai_credits_reset_date
        if not reset:
            return days_in_cycle, days_in_cycle
        now = datetime.now(timezone.utc)
        days_left = (reset - now).days
        return max(0, min(days_left, days_in_cycle)), days_in_cycle

    @staticmethod
    def quote_location_unlock(db: Session, org_id: int, location_ids: List[int]) -> Dict[str, Any]:
        """Compute the prorated charge to unlock the given pending locations. Read-only."""
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        pending = db.query(Location.id).filter(
            Location.organization_id == org_id,
            Location.id.in_(location_ids),
            Location.billing_status == "pending_payment",
        ).all()
        pending_ids = [row[0] for row in pending]
        added = len(pending_ids)

        interval = org.billing_cycle or "monthly"
        tier = org.plan_tier or "basic"
        current_quota = org.location_quota if org.location_quota is not None else plan_config.TRIAL_LOCATION_QUOTA
        days_left, days_in_cycle = SubscriptionService._cycle_days_remaining(org, interval)

        base_amount = PricingService.prorated_addon_paise(current_quota, added, interval, days_left, days_in_cycle, tier)
        if added > 0:
            base_amount = max(base_amount, _MIN_ORDER_PAISE)
        gst = plan_config.price_with_gst(base_amount)

        return {
            "location_ids": pending_ids,
            "added": added,
            "interval": interval,
            "days_left": days_left,
            "days_in_cycle": days_in_cycle,
            "amount_paise": gst["total_paise"],   # GST-inclusive — what the order charges
            "base_paise": gst["base_paise"],
            "gst_paise": gst["gst_paise"],
            "credits_granted": added * plan_config.get_plan(tier)["credits_per_location"],
        }

    @staticmethod
    def create_location_addon_order(db: Session, org_id: int, org_name: str,
                                    user_email: str, location_ids: List[int]) -> Dict[str, Any]:
        """Create a one-time Razorpay order for the prorated cost of unlocking the
        given pending locations. The actual unlock happens on payment.captured."""
        quote = SubscriptionService.quote_location_unlock(db, org_id, location_ids)
        if quote["added"] == 0:
            raise HTTPException(status_code=400, detail="No pending locations to unlock.")

        # A subscription must exist to add to (trial users should subscribe instead).
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org or not org.razorpay_subscription_id or org.subscription_status != "active":
            raise HTTPException(
                status_code=409,
                detail="no_active_subscription: subscribe to a plan before adding locations.",
            )

        customer_id = SubscriptionService.ensure_razorpay_customer(db, org_id, org_name, user_email)
        client = SubscriptionService.get_razorpay_client()
        try:
            order = client.order.create(data={
                "amount": quote["amount_paise"],
                "currency": "INR",
                "receipt": f"addon_org_{org_id}",
                "notes": {
                    "organization_id": str(org_id),
                    "type": "location_addon",
                    "added": str(quote["added"]),
                    "location_ids": ",".join(map(str, quote["location_ids"])),
                    "interval": quote["interval"],
                    "credits": str(quote["credits_granted"]),
                },
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create add-on order: {str(e)}")

        return {"order": order, "quote": quote}

    @staticmethod
    def update_subscription_plan_for_quota(db: Session, org_id: int) -> str:
        """Raise the recurring subscription amount to match the org's (post-unlock)
        location_quota, effective at the next cycle.

        Returns one of:
          - "upgraded": the plan change was scheduled (card mandates).
          - "needs_remandate": Razorpay refuses because the mandate is UPI; the amount
            can only rise via a brand-new mandate the user must approve. Caller should
            flag the org and start the re-mandate flow.
          - "noop": no subscription, or nothing to do.
          - "error": a transient failure; safe to retry. Never blocks the unlock.

        Entitlements remain the ORG's responsibility (see apply_subscription_charged)."""
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org or not org.razorpay_subscription_id:
            return "noop"
        interval = org.billing_cycle or "monthly"
        try:
            new_plan_id = SubscriptionService._get_or_create_plan(db, org.location_quota, interval, org.plan_tier or "basic")
            client = SubscriptionService.get_razorpay_client()
            # The razorpay SDK exposes the PATCH /subscriptions/{id} call as `edit`
            # (there is no `update` method) — using the wrong name silently raised
            # AttributeError, so the plan change was never scheduled and renewals kept
            # billing the old amount. See cancel_scheduled_changes to undo if needed.
            client.subscription.edit(org.razorpay_subscription_id, {
                "plan_id": new_plan_id,
                "schedule_change_at": "cycle_end",
            })
            org.subscription_payment_mode = "card"
            return "upgraded"
        except Exception as e:
            # Razorpay rejects amount changes on UPI Autopay mandates outright. That is
            # not a transient error — it needs a new mandate, so signal the caller
            # instead of just logging and moving on.
            if "payment mode is upi" in str(e).lower():
                org.subscription_payment_mode = "upi"
                logger.warning(
                    "Org %s subscription is UPI; plan upgrade needs a new mandate.", org_id
                )
                return "needs_remandate"
            logger.error(
                "Failed to update subscription plan for org %s after unlock (next renewal "
                "may bill the old amount): %s", org_id, e, exc_info=True
            )
            return "error"

    @staticmethod
    def reconcile_location_addon_payment(db: Session, org_id: int, payment_id: str) -> bool:
        """Safety net for a missed payment.captured on a location add-on, mirroring
        reconcile_topup_payment."""
        from app.services.billing.webhook_service import WebhookService

        client = SubscriptionService.get_razorpay_client()
        try:
            payment = client.payment.fetch(payment_id)
        except Exception:
            return False
        if payment.get("status") != "captured":
            return False

        notes = payment.get("notes") or {}
        order_id = payment.get("order_id")
        if order_id:
            try:
                order = client.order.fetch(order_id)
                notes = order.get("notes") or notes
            except Exception:
                pass

        if notes.get("type") != "location_addon" or str(notes.get("organization_id")) != str(org_id):
            return False

        payment_with_notes = {**payment, "notes": notes}
        WebhookService._handle_payment_captured(
            db, {"payload": {"payment": {"entity": payment_with_notes}}}
        )
        db.commit()
        return True

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

        # Require a real charge before granting entitlements. Razorpay marks a paid
        # subscription "active"; "authenticated" means the mandate is set up but the
        # first charge hasn't landed — granting then would hand out a free cycle if that
        # first charge later fails. The subscription.charged webhook activates the org
        # the moment the debit actually succeeds.
        if subscription.get("status") != "active":
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
