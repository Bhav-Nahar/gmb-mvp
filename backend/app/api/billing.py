import logging
from datetime import timedelta
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel
from app.db.session import get_db
from app.api.deps import get_current_user, admin_required
from app.models.user import User
from app.models.organization import Organization
from app.models.location import Location
from app.models.billing_transaction import BillingTransaction
from app.core import plan_config
from app.core.config import settings
from app.services.billing.pricing_service import PricingService
from app.services.billing.subscription_service import SubscriptionService, normalize_phone
from app.services.billing.webhook_service import WebhookService
from app.services.billing.entitlement_service import EntitlementService
from app.core.rate_limit import rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter()
webhook_router = APIRouter()

# Per-IP throttles. Webhook is generous (legit Razorpay bursts come from few IPs);
# it mainly caps a single-source garbage/replay flood. Mutations are tighter — they
# create Razorpay orders/subscriptions, so a runaway client or abusive admin can't
# spray plan/order sprawl. Both fail open if Redis is down.
_webhook_rate_limit = rate_limiter("razorpay_webhook", limit=1200, window_seconds=60)
_billing_mutation_rate_limit = rate_limiter("billing_mutation", limit=60, window_seconds=60)

class CheckoutRequest(BaseModel):
    location_count: int = 1
    interval: str = "monthly"
    plan_tier: str = "basic"
    # Owner phone, collected at the Start-Trial step (card-required flow). Stored on the
    # user for sales + trial-abuse dedupe, and attached to the Razorpay customer.
    phone: str | None = None

class BuyCreditsRequest(BaseModel):
    pack: str = "small"

class QuoteResponse(BaseModel):
    location_count: int
    interval: str
    plan_tier: str
    price_paise: int        # base (ex-GST)
    gst_paise: int
    total_paise: int        # base + GST — what is actually charged
    gst_rate: float
    monthly_ai_credits: int

class ConfirmRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_signature: str
    razorpay_subscription_id: str | None = None
    razorpay_order_id: str | None = None

@router.get("/quote", response_model=QuoteResponse)
def get_quote(location_count: int, interval: str = "monthly", plan_tier: str = "basic"):
    """Server-authoritative price for a location count + tier (for display).
    Returns base, GST, and the GST-inclusive total that is actually charged.

    PUBLIC (no auth) — the marketing homepage pricing calls this while logged out, so it
    must stay unauthenticated and standard-tier. Enterprise custom pricing is reflected at
    checkout and in /billing/status, not in this public quote."""
    if plan_tier not in plan_config.PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan tier")
    base = PricingService.compute_price_paise(location_count, interval, plan_tier)
    gst = plan_config.price_with_gst(base)
    return QuoteResponse(
        location_count=location_count,
        interval=interval,
        plan_tier=plan_tier,
        price_paise=base,
        gst_paise=gst["gst_paise"],
        total_paise=gst["total_paise"],
        gst_rate=plan_config.GST_RATE,
        monthly_ai_credits=PricingService.get_credits_for_locations(location_count, plan_tier),
    )

@router.post("/checkout-subscription", dependencies=[Depends(_billing_mutation_rate_limit)])
def checkout_subscription(
    request: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(admin_required)
):
    """Creates a Razorpay subscription checkout. Price is computed server-side
    from the location count; the client cannot specify an amount or plan id."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")

    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Card-required onboarding: the FIRST subscription is a trial — register the mandate
    # now, charge nothing for TRIAL_DAYS. Bill for every audited location, counted
    # server-side (not from the client) so the mandate can't be under-priced.
    trial_signup = settings.CARD_REQUIRED_ONBOARDING and EntitlementService.is_onboarding(org)
    eff_phone = None
    if trial_signup:
        # Phone comes from the gate's inline field (or is already on the user). Required
        # for a trial: it is a real identity for the abuse guard, so a missing phone must
        # not fall back to Google-id-only (which a fresh Google account trivially defeats).
        eff_phone = ((request.phone or current_user.phone or "").strip()) or None
        if not eff_phone:
            raise HTTPException(status_code=400, detail="phone_required: add your mobile number to start the trial.")
        # One free trial per Google account / phone.
        SubscriptionService.assert_trial_not_abused(db, org.id, eff_phone)
        location_count = db.query(Location).filter(
            Location.organization_id == org.id,
            Location.billing_status == "active",
        ).count()
        if location_count < 1:
            # Nothing to bill/audit yet — don't create a ₹0/1-location mandate.
            raise HTTPException(
                status_code=400,
                detail="no_locations: connect a Google Business Profile with at least one location first.",
            )
        if request.phone and request.phone.strip() and not current_user.phone:
            current_user.phone = request.phone.strip()
            db.commit()
    else:
        location_count = request.location_count

    subscription = SubscriptionService.create_subscription_checkout(
        db=db,
        org_id=org.id,
        org_name=org.name,
        user_email=current_user.email,
        location_count=location_count,
        interval=request.interval,
        plan_tier=request.plan_tier,
        trial=trial_signup,
        contact=eff_phone,
    )
    return {"subscription": subscription}

class StartPhoneTrialRequest(BaseModel):
    phone: str | None = None  # falls back to the phone already on the user


@router.post("/start-phone-trial", dependencies=[Depends(_billing_mutation_rate_limit)])
def start_phone_trial(
    request: StartPhoneTrialRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(admin_required),
):
    """India-only: start the free trial with just a +91 phone number, no card/UPI
    mandate. Rest of world uses /checkout-subscription. The country is re-derived
    server-side from the number, so the client can't route around the card flow."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")

    eff_phone = ((request.phone or current_user.phone or "").strip()) or None
    # Lead capture before the guards (mirrors the gate's on-blur save): even a
    # failed start leaves a contact for sales follow-up.
    canon = normalize_phone(eff_phone)
    if canon and current_user.phone != canon:
        current_user.phone = canon
        db.commit()

    trial_ends_at = SubscriptionService.start_phone_trial(db, current_user.organization_id, eff_phone)
    return {"activated": True, "trial_ends_at": trial_ends_at.isoformat()}


@router.post("/buy-credits", dependencies=[Depends(_billing_mutation_rate_limit)])
def buy_credits(
    request: BuyCreditsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(admin_required)
):
    """Creates a Razorpay order for an AI credit top-up pack."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")

    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    order = SubscriptionService.create_topup_order(
        db=db,
        org_id=org.id,
        org_name=org.name,
        user_email=current_user.email,
        pack_key=request.pack,
    )
    return {"order": order}

@router.post("/confirm")
def confirm_payment(
    request: ConfirmRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(admin_required),
):
    """Called from the Razorpay checkout success handler. Verifies the payment
    signature and immediately reconciles entitlements from Razorpay, so the user
    is activated right away instead of waiting on the (eventually-consistent)
    webhook. The webhook remains the source of truth; this is a fast path and a
    safety net, and both are idempotent."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")

    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Snapshot the customer's real IP + UA here (this is their browser request); the
    # webhook-fired Meta CAPI conversion can't see them since it runs off Razorpay's call.
    fwd = http_request.headers.get("x-forwarded-for")
    org.conv_client_ip = fwd.split(",")[0].strip() if fwd else (http_request.client.host if http_request.client else None)
    org.conv_user_agent = http_request.headers.get("user-agent")

    client = SubscriptionService.get_razorpay_client()
    try:
        if request.razorpay_subscription_id:
            client.utility.verify_subscription_payment_signature({
                "razorpay_subscription_id": request.razorpay_subscription_id,
                "razorpay_payment_id": request.razorpay_payment_id,
                "razorpay_signature": request.razorpay_signature,
            })
        elif request.razorpay_order_id:
            client.utility.verify_payment_signature({
                "razorpay_order_id": request.razorpay_order_id,
                "razorpay_payment_id": request.razorpay_payment_id,
                "razorpay_signature": request.razorpay_signature,
            })
        else:
            raise HTTPException(status_code=400, detail="Missing subscription or order id")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    if request.razorpay_subscription_id:
        # Only reconcile the subscription we actually own.
        if org.razorpay_subscription_id != request.razorpay_subscription_id:
            raise HTTPException(status_code=400, detail="Subscription does not belong to this organization")
        # Card-required onboarding: the returning subscription is an authenticated (not
        # yet charged) mandate, so START THE TRIAL rather than waiting on a first charge.
        # Once the trial is running (or the org has paid) this falls through to the normal
        # reconcile. subscription.authenticated / subscription.charged webhooks back it up.
        if settings.CARD_REQUIRED_ONBOARDING and org.subscription_status == "trial":
            activated = SubscriptionService.activate_trial_from_subscription(db, org.id)
        else:
            activated = SubscriptionService.reconcile_subscription(db, org.id)
    else:
        # Order payments are either a credit top-up or a location add-on. Try the
        # add-on path first (it no-ops unless the order's notes say location_addon),
        # then fall back to top-up. Both verify the notes belong to this org.
        activated = SubscriptionService.reconcile_location_addon_payment(
            db, org.id, request.razorpay_payment_id
        )
        if not activated:
            activated = SubscriptionService.reconcile_topup_payment(
                db, org.id, request.razorpay_payment_id
            )

    # Persist the IP/UA snapshot set above. The activate/reconcile calls commit on the
    # normal path, but when the webhook already activated the trial they return early
    # without committing, which would silently drop the Meta CAPI match keys.
    try:
        db.commit()
    except Exception:
        db.rollback()

    return {"confirmed": True, "activated": activated}


@router.get("/audit-summary")
def get_audit_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Real, already-synced findings for the pre-payment onboarding gate (the FOMO hook).
    Teaser counts only — no premium insight — so it stays accessible before the trial."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")
    from app.services.onboarding_audit import compute_audit_summary
    return compute_audit_summary(db, current_user.organization_id)


@router.get("/status")
def get_billing_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Returns the billing status of the current organization."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")

    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    active_count = db.query(Location).filter(
        Location.organization_id == org.id, Location.billing_status == "active"
    ).count()
    pending_count = db.query(Location).filter(
        Location.organization_id == org.id, Location.billing_status == "pending_payment"
    ).count()

    # Onboarding sync status, so the (app-wide) paywall gate only appears once the audit
    # is actually ready — never mid-sync with an empty audit. NOTE: last_review_sync_at is
    # unreliable (review tasks don't stamp it), so 'ready' keys off location-sync success.
    from app.models.organization_sync_state import OrganizationSyncState
    ss = db.query(OrganizationSyncState).filter(
        OrganizationSyncState.organization_id == org.id
    ).first()
    if ss is None:
        onboarding_sync_status = "idle"
    elif ss.sync_in_progress:
        onboarding_sync_status = "syncing"
    elif ss.last_sync_status == "Failed":
        onboarding_sync_status = "failed"
    elif ss.last_location_sync_at is not None and ss.last_sync_status == "Success":
        onboarding_sync_status = "ready"
    else:
        onboarding_sync_status = "syncing"  # pending / not yet completed

    from app.services.app_settings import india_phone_trial_enabled, row_phone_trial_enabled

    return {
        "onboarding_sync_status": onboarding_sync_status,
        # Effective runtime flags (super-admin override or env default): tell the
        # onboarding gate which regions get the no-card phone trial UI.
        "india_phone_trial": india_phone_trial_enabled(db),
        "row_phone_trial": row_phone_trial_enabled(db),
        "plan": org.plan,
        "plan_tier": org.plan_tier,
        "features": plan_config.get_plan(org.plan_tier).get("features", []),
        # Numeric caps for this tier (absent/None = unlimited) so the UI can gate accordingly.
        "limits": plan_config.get_plan(org.plan_tier).get("limits", {}),
        "subscription_status": org.subscription_status,
        "monthly_ai_credits_balance": org.monthly_ai_credits_balance,
        # Monthly allowance = the full grant the org gets each cycle, used as the
        # denominator for the usage bar. For a paid org this scales with quota; on
        # the trial it is the flat trial grant.
        "monthly_ai_credits_allowance": (
            PricingService.get_credits_for_locations(org.location_quota, org.plan_tier, org.custom_credits_per_location)
            if org.plan == "active" and org.location_quota
            else plan_config.TRIAL_AI_CREDITS
        ),
        "topup_ai_credits_balance": org.topup_ai_credits_balance,
        "location_quota": org.location_quota,
        "active_location_count": active_count,
        "pending_location_count": pending_count,
        "is_org_locked": EntitlementService.is_org_locked(org),
        "ai_credits_reset_date": org.ai_credits_reset_date,
        "current_period_end": org.ai_credits_reset_date,
        "trial_ends_at": org.trial_ends_at,
        "grace_period_ends_at": org.grace_period_ends_at,
        "subscription_ends_at": org.subscription_ends_at,
        # UPI re-mandate: the banner uses these to prompt the user to approve the new
        # (higher) mandate before the surplus locations are re-locked at the deadline.
        "needs_remandate": bool(org.subscription_needs_remandate),
        "remandate_due_at": org.remandate_due_at,
        "paid_location_quota": org.paid_location_quota,
        # When the owner may next reassign which locations fill their paid slots (free,
        # but rate-limited). NULL = available now.
        "location_reassign_available_at": (
            org.last_location_reassign_at + timedelta(days=plan_config.LOCATION_REASSIGN_COOLDOWN_DAYS)
            if org.last_location_reassign_at else None
        ),
    }


@router.get("/transactions")
def get_transactions(
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(admin_required),
):
    """Paginated payment history for the current org, most recent first. Drives the
    billing history table. Restricted to admins/owners like the rest of the billing
    surface. Returns `total` so the client can render page controls."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    base = db.query(BillingTransaction).filter(
        BillingTransaction.organization_id == current_user.organization_id
    )
    total = base.count()
    rows = (
        base.order_by(BillingTransaction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "transactions": [
            {
                "id": t.id,
                "type": t.transaction_type,
                "credits": t.credits,
                "amount_paise": t.amount_paise,
                "currency": t.currency or "INR",
                "status": t.status,
                "invoice_url": t.invoice_url,
                "created_at": t.created_at,
            }
            for t in rows
        ],
    }


@router.get("/pending-locations")
def get_pending_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List locations locked pending payment, plus the prorated quote to unlock them all."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")

    # Only id, location_name, address are used below — project them to avoid
    # fetching all 44 Location columns (incl. the large gbp_raw JSON) per row.
    pending = db.query(Location.id, Location.location_name, Location.address).filter(
        Location.organization_id == current_user.organization_id,
        Location.billing_status == "pending_payment",
    ).all()

    quote = None
    if pending:
        quote = SubscriptionService.quote_location_unlock(
            db, current_user.organization_id, [loc.id for loc in pending]
        )

    return {
        "pending_locations": [
            {"id": loc.id, "location_name": loc.location_name, "address": loc.address}
            for loc in pending
        ],
        "quote": quote,
    }


class UnlockLocationsRequest(BaseModel):
    location_ids: list[int]


@router.post("/locations/unlock", dependencies=[Depends(_billing_mutation_rate_limit)])
def unlock_locations(
    request: UnlockLocationsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(admin_required),
):
    """Create a Razorpay order for the prorated cost of unlocking the given pending
    locations. The actual unlock is applied on payment.captured (and reconciled on
    /confirm). Price is computed server-side; the client cannot specify an amount."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")

    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Anti-IDOR: ensure every location belongs to the caller's org (and is within
    # their location scope) before creating a paid order against it.
    from app.core.authorization import validate_location_access
    validate_location_access(db, current_user, request.location_ids)

    result = SubscriptionService.create_location_addon_order(
        db=db,
        org_id=org.id,
        org_name=org.name,
        user_email=current_user.email,
        location_ids=request.location_ids,
    )
    return result


class SetActiveLocationsRequest(BaseModel):
    location_ids: list[int]


@router.post("/locations/active", dependencies=[Depends(_billing_mutation_rate_limit)])
def set_active_locations(
    request: SetActiveLocationsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(admin_required),
):
    """Choose WHICH locations occupy the org's paid slots. Free, because the number of
    paid slots (location_quota) doesn't change — the owner is only deciding which
    locations are active. This is what lets an org that paid for fewer locations than it
    has pick the ones to keep, instead of the system silently keeping the oldest by id.

    The submitted set becomes 'active'; every other location in the org is set to
    'pending_payment'. Going ABOVE quota still requires payment (see /locations/unlock)."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")

    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    desired = list(dict.fromkeys(request.location_ids))  # de-dupe, keep order

    # Anti-IDOR + per-user scope: every id must belong to the caller's org.
    from app.core.authorization import validate_location_access
    validate_location_access(db, current_user, desired)

    quota = org.location_quota or 0
    if len(desired) > quota:
        raise HTTPException(
            status_code=409,
            detail=f"exceeds_quota: your plan covers {quota} location(s). "
                   f"Pay to add more before activating them.",
        )

    desired_set = set(desired)
    locs = db.query(Location).filter(Location.organization_id == org.id).all()
    current_active = {loc.id for loc in locs if loc.billing_status == "active"}

    # Re-saving the SAME selection is a no-op — it must not start a cooldown, so a user
    # can hit Save twice harmlessly.
    if desired_set != current_active:
        # Rate-limit real changes so active locations can't be cycled daily to farm
        # per-location value beyond the paid quota. The automatic claw-back/conversion
        # paths don't come through here, so they're naturally exempt.
        from datetime import datetime, timezone, timedelta
        cooldown = timedelta(days=plan_config.LOCATION_REASSIGN_COOLDOWN_DAYS)
        last = org.last_location_reassign_at
        # Normalise a possibly-naive stored timestamp to UTC so the subtraction below can't
        # raise on a naive/aware mismatch (some drivers return naive datetimes).
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if last is not None and (now - last) < cooldown:
            available_at = last + cooldown
            raise HTTPException(
                status_code=429,
                detail=f"reassign_cooldown: you can change your active locations again "
                       f"on {available_at.date().isoformat()}.",
            )
        org.last_location_reassign_at = now

    newly_active: list[int] = []
    for loc in locs:
        if loc.id in desired_set:
            if loc.billing_status != "active":
                loc.billing_status = "active"
                newly_active.append(loc.id)
        elif loc.billing_status != "pending_payment":
            loc.billing_status = "pending_payment"
    db.commit()

    # Sync the freshly-activated locations (parity with the paid unlock path) so their
    # data is fresh when they come back online. Best-effort — never blocks the change.
    if newly_active:
        try:
            from app.worker import celery as celery_app
            celery_app.send_task(
                "app.tasks.sync_reviews_chunk_task",
                args=[newly_active, org.id, "Manual", None],
            )
            for loc_id in newly_active:
                celery_app.send_task("app.tasks.sync_location_attributes_task", args=[loc_id])
        except Exception as e:
            logger.error("Failed to enqueue sync for reactivated locations %s: %s", newly_active, e)

    active_count = sum(1 for loc in locs if loc.billing_status == "active")
    return {
        "active_location_count": active_count,
        "pending_location_count": len(locs) - active_count,
        "location_quota": quota,
        "reactivated": newly_active,
    }


class RemandateConfirmRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_subscription_id: str
    razorpay_signature: str


@router.post("/remandate", dependencies=[Depends(_billing_mutation_rate_limit)])
def start_remandate(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(admin_required),
):
    """Begin a UPI re-mandate: create a NEW subscription at the higher (current-quota)
    plan for the user to approve. The old mandate keeps billing until the new one's
    first charge triggers the cutover, so locations never lose coverage."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    subscription = SubscriptionService.create_remandate_subscription(
        db=db, org_id=org.id, org_name=org.name, user_email=current_user.email,
    )
    return {"subscription": subscription}


@router.post("/remandate/confirm")
def confirm_remandate(
    request: RemandateConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(admin_required),
):
    """Verify the approved re-mandate subscription and apply the cutover immediately
    (fast path). The subscription.charged webhook is the backstop; both idempotent."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User does not belong to an organization")
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    client = SubscriptionService.get_razorpay_client()
    try:
        client.utility.verify_subscription_payment_signature({
            "razorpay_subscription_id": request.razorpay_subscription_id,
            "razorpay_payment_id": request.razorpay_payment_id,
            "razorpay_signature": request.razorpay_signature,
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    activated = SubscriptionService.reconcile_remandate(
        db, org.id, request.razorpay_subscription_id
    )
    return {"confirmed": True, "activated": activated}


@webhook_router.post("/razorpay", dependencies=[Depends(_webhook_rate_limit)])
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Receives Razorpay webhooks."""
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    if not WebhookService.verify_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("event")
    if not event_type:
        raise HTTPException(status_code=400, detail="Missing event type")

    # Derive the idempotency id from the SIGNED body only. We deliberately do NOT use the
    # X-Razorpay-Event-Id header: it is outside the signed content, so a replay of one valid
    # (signed) event body with a varied header would produce a new idempotency key and
    # re-run apply_subscription_charged (re-granting credits/quota). The body-derived id is
    # unique per charge (payment id) and stable, which is exactly what we want.
    contains = payload.get("contains", []) or []
    # Prefer the PAYMENT entity id: it is unique per charge. The subscription id is the SAME
    # every billing cycle, so keying off it would make month-2's subscription.charged
    # collide with month-1's and be skipped as a duplicate — the customer would be charged
    # but never get the credit reset / quota.
    ordered_keys = (["payment"] if "payment" in contains else []) + \
        [k for k in contains if k != "payment"]
    entity_id = None
    for key in ordered_keys:
        entity_id = payload.get("payload", {}).get(key, {}).get("entity", {}).get("id")
        if entity_id:
            break
    if not entity_id:
        raise HTTPException(status_code=400, detail="Cannot determine event id")
    event_id = f"{event_type}:{entity_id}"

    # Process webhook
    WebhookService.process_webhook(db, event_id, event_type, payload)

    return {"status": "ok"}
