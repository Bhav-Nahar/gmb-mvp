import logging
import re
import razorpay
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.core.config import settings
from app.core import plan_config
from app.models.organization import Organization
from app.models.location import Location
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.core.redis_client import get_redis
from app.services.billing.pricing_service import PricingService

logger = logging.getLogger(__name__)

# Approximate cycle lengths used for proration when we don't fetch the exact
# current_start from Razorpay. Conventional billing-month / billing-year.
_DAYS_IN_CYCLE = {"monthly": 30, "annual": 365}
# Razorpay rejects orders below ₹1. Floor tiny prorated amounts to this.
_MIN_ORDER_PAISE = 100


def normalize_phone(raw: str | None) -> str | None:
    """Canonicalize a phone number to standard E.164 format for trial-abuse dedup.
    If the string starts with '+', it preserves the international code while stripping
    other non-digit characters. If no '+' is present, it falls back to +91 and strips
    leading zeroes."""
    if not raw:
        return None
    
    # Strip everything except + and digits
    clean = re.sub(r"[^\d+]", "", raw.strip())
    
    # If no leading +, assume +91
    if not clean.startswith("+"):
        clean = clean.lstrip("0")
        if len(clean) == 12 and clean.startswith("91"):
            clean = clean[2:]  # country code typed without '+' (e.g. "0919876543210")
        clean = "+91" + clean
        
    # Ensure there's only one + and it's at the start
    clean = "+" + clean.replace("+", "")
    
    if len(clean) < 8:  # Arbitrary minimum length for E.164
        return None
    return clean


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
    def cancel_active_subscriptions(org: Organization) -> None:
        """Best-effort cancel of an org's live Razorpay mandate(s). Used when an account
        is deleted so the customer stops being charged. Never raises — a Razorpay failure
        must not block the delete; it's logged loudly so a stuck mandate can be chased."""
        for sub_id in (org.razorpay_subscription_id, org.pending_remandate_subscription_id):
            if not sub_id:
                continue
            try:
                SubscriptionService.get_razorpay_client().subscription.cancel(
                    sub_id, {"cancel_at_cycle_end": 0}
                )
                logger.warning("Cancelled Razorpay sub %s for org %s.", sub_id, org.id)
            except Exception as e:
                logger.error("Failed to cancel Razorpay sub %s for org %s "
                             "(customer may keep being charged): %s", sub_id, org.id, e)

    @staticmethod
    def _current_mode() -> str:
        """'test' or 'live' for the configured keys. Cached Razorpay customer/plan ids
        are namespaced by this because a test id is invalid under live keys (and vice
        versa); guarded against an unset key id (would otherwise AttributeError → 500)."""
        return "test" if (settings.RAZORPAY_KEY_ID or "").startswith("rzp_test_") else "live"

    @staticmethod
    def ensure_razorpay_customer(db: Session, org_id: int, org_name: str, user_email: str,
                                 contact: str | None = None) -> str:
        """Get-or-create the org's Razorpay customer id under a row lock. `contact` (the
        owner's phone) is attached on first create for UPI Autopay / receipts; ignored on
        an existing customer (create is idempotent by email)."""
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
            customer_data = {
                "name": org_name,
                "email": user_email,
                "fail_existing": "0",
                "notes": {"organization_id": str(org_id)},
            }
            if contact:
                customer_data["contact"] = contact
            customer = client.customer.create(data=customer_data)
            cust_id = customer["id"]
            org.razorpay_customer_id = f"{current_mode}:{cust_id}"
            db.commit()
            return cust_id
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create Razorpay customer for org {org_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create Razorpay customer: {str(e)}")

    @staticmethod
    def _get_or_create_plan(db: Session, location_count: int, interval: str, plan_tier: str = "basic",
                            custom_per_location_paise: int | None = None) -> str:
        """Get-or-create a Razorpay plan for this (location_count, interval, amount).

        Plan ids are cached durably in the razorpay_plans table so repeated/cold
        checkouts reuse the same plan instead of creating an orphan plan on every
        call (which caused plan sprawl and rate-limiting). The amount is
        part of the key so a pricing change yields a new plan, never a stale one.
        Tier + GST both feed the amount, so basic/pro (and pre/post-GST) never collide
        on a stale cached plan."""
        from app.models.razorpay_plan import RazorpayPlan

        base = PricingService.compute_price_paise(location_count, interval, plan_tier, custom_per_location_paise)
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
        trial: bool = False,
        contact: str | None = None,
    ) -> Dict[str, Any]:
        PricingService.validate_location_count(location_count)
        if interval not in ("monthly", "annual"):
            raise HTTPException(status_code=400, detail="interval must be 'monthly' or 'annual'")
        if plan_tier not in plan_config.PLANS:
            raise HTTPException(status_code=400, detail="Unknown plan tier")
        # Per-tier location ceiling (e.g. Lite = 1). Keeps a cheap small-business tier from
        # being bought N times to undercut the multi-location tiers.
        tier_max = plan_config.plan_limit(plan_tier, plan_config.LIMIT_MAX_LOCATIONS)
        if tier_max is not None and location_count > tier_max:
            raise HTTPException(
                status_code=400,
                detail=f"tier_location_limit: the {plan_tier} plan supports up to {tier_max} "
                       f"location(s). Choose a higher plan for more.",
            )

        # Enterprise custom pricing (per-location rate / credits) overrides the tier price.
        # Scoped to the tier being bought: a Basic-rate deal doesn't discount Pro.
        _org = db.query(Organization).filter(Organization.id == org_id).first()
        custom_rate = PricingService.custom_rate(_org, plan_tier) if _org else None
        custom_credits = _org.custom_credits_per_location if _org else None

        # Serialize checkouts per org. Without this, a double-submit (two tabs / rapid
        # clicks) races: each creates its OWN Razorpay mandate and only the id-write is
        # locked, orphaning a mandate that still debits real money. A second concurrent
        # call is rejected rather than allowed to mint a second mandate.
        redis_client = get_redis()
        lock = redis_client.lock(f"lock:checkout:org_{org_id}", timeout=90)
        if not lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409,
                detail="A checkout is already in progress. Please wait a moment and try again.",
            )
        try:
            customer_id = SubscriptionService.ensure_razorpay_customer(db, org_id, org_name, user_email, contact)
            plan_id = SubscriptionService._get_or_create_plan(db, location_count, interval, plan_tier, custom_rate)
            client = SubscriptionService.get_razorpay_client()
            credits = PricingService.get_credits_for_locations(location_count, plan_tier, custom_credits)

            # Re-read the prior mandate id UNDER the lock (a sequential re-checkout may have
            # set it since _org was read above).
            _cur = db.query(Organization).filter(Organization.id == org_id).first()
            prior_sub_id = _cur.razorpay_subscription_id if _cur else None
            needs_remandate = bool(_cur.subscription_needs_remandate) if _cur else False

            # A prior mandate that Razorpay says is ALREADY ACTIVE means this org has a
            # live, charging subscription — minting a second one here would orphan the
            # first (org.razorpay_subscription_id is overwritten below) and the customer
            # would be billed twice, forever. The API-level already_subscribed guard
            # misses this window: after an early payment charges at Razorpay but before
            # /confirm flips our row to 'active', the org still looks like a trial.
            # A wind-down (subscription_ends_at set) is exempt — that org is legitimately
            # re-subscribing while its cancelled mandate runs out.
            if prior_sub_id and not needs_remandate and not _cur.subscription_ends_at:
                try:
                    prev_state = client.subscription.fetch(prior_sub_id).get("status")
                except Exception as e:
                    prev_state = None  # fail open: a Razorpay blip must not block checkout
                    logger.warning("Could not check prior mandate %s for org %s: %s",
                                   prior_sub_id, org_id, e)
                if prev_state == "active":
                    raise HTTPException(
                        status_code=409,
                        detail="already_subscribed: this payment already went through. "
                               "Refresh the page — if you are still not activated, contact support.",
                    )

            data = {
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
                    "trial": "1" if trial else "0",
                },
            }
            if trial:
                # Card-required onboarding: register the mandate now but schedule the first
                # real debit TRIAL_DAYS out. Until then the subscription sits 'authenticated'
                # (mandate approved, nothing charged); that gap is the free trial.
                start_at = int(datetime.now(timezone.utc).timestamp()) + plan_config.TRIAL_DAYS * 86400
                data["start_at"] = start_at
            try:
                subscription = client.subscription.create(data=data)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to create subscription: {str(e)}")

            # Now that the NEW mandate exists, cancel a PRIOR UN-CHARGED mandate so we never
            # leave two authenticated mandates that both debit at day 7 (double-charge). Done
            # AFTER creation so a create failure leaves the old mandate intact. Scoped to
            # created/authenticated (un-charged) only — an active recurring mandate is left
            # alone, and a pending re-mandate (separate flow) must not be cancelled here.
            if (prior_sub_id and prior_sub_id != subscription["id"] and not needs_remandate):
                try:
                    prev = client.subscription.fetch(prior_sub_id)
                    if prev.get("status") in ("created", "authenticated"):
                        client.subscription.cancel(prior_sub_id, {"cancel_at_cycle_end": 0})
                except Exception as e:
                    logger.warning("Could not cancel prior un-charged mandate %s for org %s: %s",
                                   prior_sub_id, org_id, e)

            # Persist the subscription id so we can reconcile / cancel later. Entitlements
            # (quota, credits) are granted by the subscription.charged webhook.
            stmt = select(Organization).where(Organization.id == org_id).with_for_update()
            org = db.scalars(stmt).first()
            if org:
                org.razorpay_subscription_id = subscription["id"]
                org.billing_cycle = interval
                db.commit()

            return subscription
        finally:
            try:
                lock.release()
            except Exception:
                pass

    @staticmethod
    def activate_trial(db: Session, org: Organization, subscription: Dict[str, Any]) -> bool:
        """Start the free trial once the payment mandate is authenticated (card/UPI
        approved) but before the first debit. Sets the trial clock to the scheduled
        first-charge date and records the mandate mode. Shared by the /confirm fast path
        and the subscription.authenticated webhook; both are idempotent. Caller locks
        `org` and commits.

        Returns True if the org is in a trial (or already active) afterwards."""
        # Only a pre-payment onboarding org (status 'trial', clock not started) activates
        # here. A re-run once the clock is set — webhook/confirm race, redelivery — is a
        # no-op that still reports success.
        if not (org.subscription_status == "trial" and org.trial_ends_at is None):
            return org.subscription_status in ("trial", "active")

        status = subscription.get("status")
        if status == "active":
            # The first charge already landed (e.g. start_at elapsed before we processed
            # this) — treat as a normal paid activation, not a trial start.
            from app.services.billing.webhook_service import WebhookService
            WebhookService.apply_subscription_charged(db, org, subscription, payment=None)
            return True
        if status != "authenticated":
            return False  # mandate not approved yet — nothing to start

        # Trial ends when the first debit is scheduled (Razorpay charge_at / start_at);
        # fall back to a fixed window if the field is absent.
        #
        # Capped at TRIAL_DAYS. On a mandate that bills immediately, charge_at is the NEXT
        # cycle — a month out — so trusting it unconditionally would hand out a free month.
        # Every mandate that reaches here is supposed to carry start_at = now + TRIAL_DAYS;
        # the cap makes that guarantee instead of assuming it.
        now = datetime.now(timezone.utc)
        limit = now + timedelta(days=plan_config.TRIAL_DAYS)
        charge_at = subscription.get("charge_at") or subscription.get("start_at")
        if charge_at:
            org.trial_ends_at = min(datetime.fromtimestamp(charge_at, tz=timezone.utc), limit)
        else:
            org.trial_ends_at = limit

        mode = subscription.get("payment_method")  # 'card' | 'upi' | 'emandate' | ...
        if mode in ("card", "upi"):
            org.subscription_payment_mode = mode

        # ponytail: premium data prep (deferred expensive tasks — insights/rank/competitor)
        # is wired in step #4; the cheap audit already synced during onboarding, and the
        # scheduled beats backfill until then. Nothing expensive is fired from this hot path.
        return True

    @staticmethod
    def activate_trial_from_subscription(db: Session, org_id: int) -> bool:
        """Fast path: pull the org's subscription from Razorpay and, if the mandate is
        authenticated, start the trial. Called on the user's return from checkout; the
        subscription.authenticated webhook is the backstop. Both idempotent."""
        stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            return False
        if org.subscription_status == "active":
            return True
        if org.subscription_status == "trial" and org.trial_ends_at is not None:
            return True  # trial already started
        if not org.razorpay_subscription_id:
            return False

        client = SubscriptionService.get_razorpay_client()
        try:
            subscription = client.subscription.fetch(org.razorpay_subscription_id)
        except Exception:
            return False
        # Refuse to act on a subscription that isn't this org's.
        if str(subscription.get("notes", {}).get("organization_id")) != str(org_id):
            return False

        ok = SubscriptionService.activate_trial(db, org, subscription)
        db.commit()
        return ok

    @staticmethod
    def activate_paid_now(db: Session, org_id: int, payment_id: str | None = None) -> bool:
        """Start a PAID subscription the moment the user completes checkout.

        Used only for a deliberate pay-now checkout (a trial converting early, or a
        past_due/locked org paying) — never for an onboarding trial mandate, which is
        scheduled to debit on day 7 and must not grant paid entitlements up front.

        Unlike `reconcile_subscription` this also accepts an `authenticated` mandate whose
        first debit is due immediately: with UPI Autopay the bank approves instantly but
        the debit lands later, and the customer must not sit locked out in the meantime.
        The risk that the debit then fails is covered by the subscription.halted /
        .pending webhooks, which drop the org to past_due with its grace window.

        Returns True if the org is paid-active afterwards."""
        from app.services.billing.webhook_service import WebhookService

        stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            return False
        if org.subscription_status == "active" and not org.subscription_ends_at:
            return True
        if not org.razorpay_subscription_id:
            return False

        client = SubscriptionService.get_razorpay_client()
        try:
            subscription = client.subscription.fetch(org.razorpay_subscription_id)
        except Exception:
            return False
        if str(subscription.get("notes", {}).get("organization_id")) != str(org_id):
            return False

        status = subscription.get("status")
        if status not in ("active", "authenticated"):
            return False  # 'created' = mandate never approved; nothing was paid

        # paid_count >= 1 means Razorpay has already debited at least once — whatever the
        # status string says, this customer has paid and must be activated.
        charged = int(subscription.get("paid_count") or 0) >= 1
        if status == "authenticated" and not charged:
            # An authenticated-but-unpaid mandate is only a trial mandate if its FIRST
            # debit was deliberately scheduled into the future, which is exactly what
            # start_at encodes (the trial checkout sets start_at = now + TRIAL_DAYS).
            #
            # Do NOT consult charge_at here: on any normal subscription Razorpay sets
            # charge_at to the NEXT billing date — a month out — so reading it made every
            # pay-now UPI checkout look like a deferred trial and left the payer sitting
            # on their old plan until a webhook arrived.
            start_at = subscription.get("start_at")
            if start_at and start_at > int(datetime.now(timezone.utc).timestamp()) + 60:
                return False

        # Fetch the payment so the charge lands in billing history immediately. Without
        # it the org is active with no receipt until the webhook arrives (and never, if
        # webhook delivery is broken). Best-effort: entitlements matter more than the row.
        payment = None
        if payment_id:
            try:
                payment = client.payment.fetch(payment_id)
            except Exception:
                logger.warning("Could not fetch payment %s for org %s ledger row", payment_id, org_id)

        WebhookService.apply_subscription_charged(db, org, subscription, payment=payment)
        db.commit()
        return True

    @staticmethod
    def assert_trial_not_abused(db: Session, org_id: int, phone: str | None = None) -> None:
        """Block a second free trial for the same person. A card-authorization mandate
        alone doesn't stop someone spinning up N accounts, so we dedupe on the two stable
        identities we hold: the Google account id(s) behind this org, and the owner phone.

        A trial is 'consumed' once its clock has started (trial_ends_at set) or the org
        advanced past onboarding (active/past_due/locked). Raises 409 if a DIFFERENT org
        with a matching identity already consumed one. No-op when the flag is off."""
        if not settings.CARD_REQUIRED_ONBOARDING:
            return

        # Super-admin forgiveness: a customer who trialled on the wrong Google account
        # would otherwise need a DB edit to be let back in.
        this_org = db.query(Organization).filter(Organization.id == org_id).first()
        if this_org is not None and this_org.allow_extra_trial:
            logger.info("Trial-abuse guard waived for org %s (allow_extra_trial)", org_id)
            return

        consumed = or_(
            Organization.trial_ends_at.isnot(None),
            Organization.subscription_status.in_(["active", "past_due", "locked"]),
        )

        google_ids = [
            r[0] for r in db.query(OAuthAccount.provider_account_id)
            .join(User, OAuthAccount.user_id == User.id)
            .filter(User.organization_id == org_id,
                    OAuthAccount.provider.in_(["google", "gbp"]))
            .all()
        ]
        if google_ids:
            dup = (
                db.query(Organization.id)
                .join(User, User.organization_id == Organization.id)
                .join(OAuthAccount, OAuthAccount.user_id == User.id)
                .filter(OAuthAccount.provider_account_id.in_(google_ids),
                        Organization.id != org_id, consumed)
                .first()
            )
            if dup:
                raise HTTPException(status_code=409,
                                    detail="trial_already_used: this Google account has already used a free trial.")

        canon_phone = normalize_phone(phone)
        if canon_phone:
            dup = (
                db.query(Organization.id)
                .join(User, User.organization_id == Organization.id)
                .filter(User.phone == canon_phone, Organization.id != org_id, consumed)
                .first()
            )
            if dup:
                raise HTTPException(status_code=409,
                                    detail="trial_already_used: this phone number has already used a free trial.")

    @staticmethod
    def start_phone_trial(db: Session, org_id: int, phone: str | None) -> datetime:
        """Phone-only trial start: a phone number alone starts the 7-day clock with NO
        card/UPI mandate, gated per region by the runtime flags (super-admin panel /
        env defaults): india_phone_trial for +91 numbers (default on), row_phone_trial
        for the rest of the world (default off = card required). Payment is collected
        via the normal checkout once the trial expires — the expiry sweep already
        handles a mandate-less trial (no razorpay_subscription_id means no reconcile
        step: straight to past_due -> locked). Same abuse guard as the card path: one
        trial per Google account / phone.

        ponytail: the phone is format-checked, not OTP-verified — add OTP if
        fake-number trial farming ever shows up in the funnel."""
        canon = normalize_phone(phone)
        if not canon:
            raise HTTPException(status_code=400, detail="phone_required: add your mobile number to start the trial.")
        from app.services.app_settings import india_phone_trial_enabled, row_phone_trial_enabled
        enabled = india_phone_trial_enabled(db) if canon.startswith("+91") else row_phone_trial_enabled(db)
        if not enabled:
            raise HTTPException(status_code=400, detail="card_required: a payment method is needed to start the trial.")

        SubscriptionService.assert_trial_not_abused(db, org_id, canon)

        # Same per-org lock as checkout so a phone trial and a card checkout can't race
        # each other into a trial WITH a live mandate (or two trials).
        redis_client = get_redis()
        lock = redis_client.lock(f"lock:checkout:org_{org_id}", timeout=30)
        if not lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409,
                detail="A checkout is already in progress. Please wait a moment and try again.",
            )
        try:
            stmt = select(Organization).where(Organization.id == org_id).with_for_update()
            org = db.scalars(stmt).first()
            if not org:
                raise HTTPException(status_code=404, detail="Organization not found")
            if not (settings.CARD_REQUIRED_ONBOARDING
                    and org.subscription_status == "trial"
                    and org.trial_ends_at is None):
                raise HTTPException(status_code=400, detail="not_onboarding: the trial has already started or a subscription exists.")
            active_locations = db.query(Location).filter(
                Location.organization_id == org_id,
                Location.billing_status == "active",
            ).count()
            if active_locations < 1:
                # Don't let a 0-location org consume its one free trial with nothing to audit.
                raise HTTPException(
                    status_code=400,
                    detail="no_locations: connect a Google Business Profile with at least one location first.",
                )

            # An abandoned card checkout may have left an un-charged mandate; cancel it so
            # a later approval can't debit a user who chose the no-card trial.
            if org.razorpay_subscription_id:
                try:
                    client = SubscriptionService.get_razorpay_client()
                    prev = client.subscription.fetch(org.razorpay_subscription_id)
                    if prev.get("status") in ("created", "authenticated"):
                        client.subscription.cancel(org.razorpay_subscription_id, {"cancel_at_cycle_end": 0})
                except Exception as e:
                    logger.warning("Could not cancel abandoned mandate %s for org %s: %s",
                                   org.razorpay_subscription_id, org_id, e)
                org.razorpay_subscription_id = None

            org.trial_ends_at = datetime.now(timezone.utc) + timedelta(days=plan_config.TRIAL_DAYS)
            db.commit()
            return org.trial_ends_at
        finally:
            try:
                lock.release()
            except Exception:
                pass

    @staticmethod
    def create_remandate_subscription(
        db: Session, org_id: int, org_name: str, user_email: str
    ) -> Dict[str, Any]:
        """Create a NEW subscription at the plan matching the org's current
        location_quota, for a UPI org that needs a higher mandate. Unlike
        create_subscription_checkout this does NOT overwrite org.razorpay_subscription_id
        — the old mandate keeps billing until the new one's first charge triggers the
        cutover (apply_subscription_charged), so there is never a coverage gap."""
        stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = db.scalars(stmt).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        if not org.subscription_needs_remandate:
            raise HTTPException(status_code=409, detail="No re-mandate is pending for this organization.")

        location_count = org.location_quota or 0
        interval = org.billing_cycle or "monthly"
        plan_tier = org.plan_tier or "basic"
        PricingService.validate_location_count(location_count)

        customer_id = SubscriptionService.ensure_razorpay_customer(db, org_id, org_name, user_email)
        plan_id = SubscriptionService._get_or_create_plan(db, location_count, interval, plan_tier,
                                                          PricingService.custom_rate(org, plan_tier))
        client = SubscriptionService.get_razorpay_client()
        credits = PricingService.get_credits_for_locations(location_count, plan_tier, org.custom_credits_per_location)

        # Reuse an outstanding pending mandate instead of stacking a second one that
        # would double-bill. A pending mandate is still reusable only while it is
        # 'created'/'authenticated' (not yet charged) AND still matches the current
        # quota; otherwise cancel it (best-effort) and mint a fresh one.
        existing_id = org.pending_remandate_subscription_id
        if existing_id:
            try:
                existing = client.subscription.fetch(existing_id)
            except Exception:
                existing = None
            if existing and existing.get("status") in ("created", "authenticated") \
                    and str(existing.get("notes", {}).get("location_count")) == str(location_count):
                return existing
            if existing and existing.get("status") in ("created", "authenticated"):
                try:
                    client.subscription.cancel(existing_id, {"cancel_at_cycle_end": 0})
                except Exception as e:
                    logger.warning("Failed to cancel stale re-mandate sub %s for org %s: %s",
                                   existing_id, org_id, e)

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

        org.pending_remandate_subscription_id = subscription["id"]
        db.commit()
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

        base_amount = PricingService.prorated_addon_paise(current_quota, added, interval, days_left,
                                                          days_in_cycle, tier, PricingService.custom_rate(org, tier))
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
            "credits_granted": PricingService.get_credits_for_locations(added, tier, org.custom_credits_per_location),
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
        # A pending UPI re-mandate is created at a FIXED quota; adding more locations now
        # would let the cutover charge reset location_quota back down to that snapshot and
        # silently drop (and un-bill) what was added in between. Make the user finish the
        # outstanding re-mandate first.
        if org.subscription_needs_remandate:
            raise HTTPException(
                status_code=409,
                detail="remandate_pending: approve the pending mandate before adding more locations.",
            )
        # Per-tier location ceiling: adding these would exceed what the plan allows.
        tier_max = plan_config.plan_limit(org.plan_tier, plan_config.LIMIT_MAX_LOCATIONS)
        if tier_max is not None and (org.location_quota or 0) + quote["added"] > tier_max:
            raise HTTPException(
                status_code=409,
                detail=f"tier_location_limit: the {org.plan_tier} plan supports up to {tier_max} "
                       f"location(s). Upgrade to add more.",
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
            tier = org.plan_tier or "basic"
            new_plan_id = SubscriptionService._get_or_create_plan(db, org.location_quota, interval, tier,
                                                                 PricingService.custom_rate(org, tier))
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
    def reconcile_plan_amount(db: Session, org_id: int) -> str:
        """Retry a recurring-plan amount change that didn't land at add-on time.

        When a location add-on bumps the quota but `update_subscription_plan_for_quota`
        returned "error" (a transient Razorpay failure), the org keeps the higher quota
        while the mandate still bills the OLD amount, and nothing retries it — a silent
        revenue leak. The drift signature is `paid_location_quota < location_quota` with
        no re-mandate pending. This re-runs the plan change and applies the SAME
        bookkeeping the add-on handler does, so a healthy retry closes the gap and a UPI
        mandate falls into the re-mandate flow. Commits on a definitive outcome; leaves
        the drift for the next sweep on a repeat transient error. The caller locks `org`."""
        org = db.query(Organization).filter(Organization.id == org_id).with_for_update().first()
        if not org or not org.razorpay_subscription_id:
            return "noop"
        if org.subscription_needs_remandate:
            return "noop"  # already in the re-mandate flow; not a stuck upgrade
        prior_paid = org.paid_location_quota
        if prior_paid is None or prior_paid >= (org.location_quota or 0):
            return "noop"  # no drift

        result = SubscriptionService.update_subscription_plan_for_quota(db, org_id)
        if result == "upgraded":
            org.subscription_needs_remandate = False
            org.remandate_due_at = None
            org.paid_location_quota = org.location_quota
            db.commit()
        elif result == "needs_remandate":
            org.subscription_needs_remandate = True
            org.paid_location_quota = prior_paid
            due_base = org.ai_credits_reset_date
            if not due_base:
                cycle_days = _DAYS_IN_CYCLE.get(org.billing_cycle or "monthly", 30)
                due_base = datetime.now(timezone.utc) + timedelta(days=cycle_days)
            org.remandate_due_at = due_base + timedelta(days=3)
            db.commit()
        else:
            db.rollback()  # "error"/"noop": leave drift for the next sweep
        return result

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
