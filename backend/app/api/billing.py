import logging
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
from app.services.billing.pricing_service import PricingService
from app.services.billing.subscription_service import SubscriptionService
from app.services.billing.webhook_service import WebhookService
from app.services.billing.entitlement_service import EntitlementService

logger = logging.getLogger(__name__)

router = APIRouter()
webhook_router = APIRouter()

class CheckoutRequest(BaseModel):
    location_count: int = 1
    interval: str = "monthly"

class BuyCreditsRequest(BaseModel):
    pack: str = "small"

class QuoteResponse(BaseModel):
    location_count: int
    interval: str
    price_paise: int
    monthly_ai_credits: int

class ConfirmRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_signature: str
    razorpay_subscription_id: str | None = None
    razorpay_order_id: str | None = None

@router.get("/quote", response_model=QuoteResponse)
def get_quote(location_count: int, interval: str = "monthly"):
    """Server-authoritative price for a given location count (for display)."""
    price = PricingService.compute_price_paise(location_count, interval)
    return QuoteResponse(
        location_count=location_count,
        interval=interval,
        price_paise=price,
        monthly_ai_credits=PricingService.get_credits_for_locations(location_count),
    )

@router.post("/checkout-subscription")
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

    subscription = SubscriptionService.create_subscription_checkout(
        db=db,
        org_id=org.id,
        org_name=org.name,
        user_email=current_user.email,
        location_count=request.location_count,
        interval=request.interval,
    )
    return {"subscription": subscription}

@router.post("/buy-credits")
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

    return {"confirmed": True, "activated": activated}


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

    return {
        "plan": org.plan,
        "subscription_status": org.subscription_status,
        "monthly_ai_credits_balance": org.monthly_ai_credits_balance,
        # Monthly allowance = the full grant the org gets each cycle, used as the
        # denominator for the usage bar. For a paid org this scales with quota; on
        # the trial it is the flat trial grant.
        "monthly_ai_credits_allowance": (
            org.location_quota * plan_config.CREDITS_PER_LOCATION
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


@router.post("/locations/unlock")
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


class RemandateConfirmRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_subscription_id: str
    razorpay_signature: str


@router.post("/remandate")
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


@webhook_router.post("/razorpay")
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

    # Prefer Razorpay's event id header. If absent, derive a stable id from the
    # event type + the primary entity id so distinct events never collide (a
    # constant fallback would make the second event look "already processed").
    event_id = request.headers.get("X-Razorpay-Event-Id")
    if not event_id:
        contains = payload.get("contains", []) or []
        # Prefer the PAYMENT entity id: it is unique per charge. The subscription id
        # is the SAME every billing cycle, so keying off it would make month-2's
        # subscription.charged collide with month-1's and be skipped as a duplicate —
        # the customer would be charged but never get the credit reset / quota.
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
