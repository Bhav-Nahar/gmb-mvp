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

    return {
        "plan": org.plan,
        "subscription_status": org.subscription_status,
        "monthly_ai_credits_balance": org.monthly_ai_credits_balance,
        "topup_ai_credits_balance": org.topup_ai_credits_balance,
        "location_quota": org.location_quota,
        "is_org_locked": EntitlementService.is_org_locked(org),
        "ai_credits_reset_date": org.ai_credits_reset_date,
        "current_period_end": org.ai_credits_reset_date,
        "trial_ends_at": org.trial_ends_at,
        "grace_period_ends_at": org.grace_period_ends_at,
        "subscription_ends_at": org.subscription_ends_at,
    }


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
        entity_id = None
        for key in contains:
            entity_id = payload.get("payload", {}).get(key, {}).get("entity", {}).get("id")
            if entity_id:
                break
        if not entity_id:
            raise HTTPException(status_code=400, detail="Cannot determine event id")
        event_id = f"{event_type}:{entity_id}"

    # Process webhook
    WebhookService.process_webhook(db, event_id, event_type, payload)

    return {"status": "ok"}
