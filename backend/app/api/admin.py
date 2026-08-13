"""Cross-org super-admin control panel API.

Gated by `superadmin_required` (env email allowlist — see config.SUPERADMIN_EMAILS).
Every mutating endpoint records an AuditLog row (actor = the super-admin, org =
the affected organization) so manual overrides are never silent.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
import re

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.db.session import get_db
from app.api.deps import superadmin_required
from app.core import plan_config
from app.core.config import settings
from app.core.roles import Role
from app.worker import celery
from app.models.user import User
from app.models.organization import Organization
from app.models.location import Location
from app.models.audit_log import AuditLog
from app.models.sync_log import SyncLog
from app.models.organization_sync_state import OrganizationSyncState
from app.models.billing_transaction import BillingTransaction
from app.models.billing_webhook_event import BillingWebhookEvent
from app.schemas.admin import OrgUpdate, AdminUserUpdate, LocationUpdate, AdminActionBody, FlagsUpdate
from app.services.app_settings import india_phone_trial_enabled, row_phone_trial_enabled, set_flag

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_SUBSCRIPTION_STATUSES = {"trial", "active", "past_due", "locked"}
VALID_ROLES = {Role.OWNER, Role.ADMIN, Role.REGIONAL_MANAGER, Role.STORE_MANAGER, Role.VIEWER}

# Org columns a super-admin may set directly (validated below where applicable).
_ORG_EDITABLE = [
    "is_agency",
    "plan_tier",
    "subscription_status",
    "location_quota",
    "monthly_ai_credits_balance",
    "topup_ai_credits_balance",
    "trial_ends_at",
    "grace_period_ends_at",
    "custom_credits_per_location",
    "allow_extra_trial",
]


def _audit(db, *, actor, organization_id, action, changes, reason, target_user_id=None):
    db.add(AuditLog(
        organization_id=organization_id,
        user_id=actor.id,
        actor_user_id=actor.id,
        target_user_id=target_user_id,
        action=action,
        details=json.dumps({"changes": changes, "reason": reason}, default=str),
    ))


def _org_row(org, user_count, location_count):
    return {
        "id": org.id,
        "name": org.name,
        "plan": org.plan,
        "plan_tier": org.plan_tier,
        "subscription_status": org.subscription_status,
        "location_quota": org.location_quota,
        "location_count": location_count,
        "user_count": user_count,
        "monthly_ai_credits_balance": org.monthly_ai_credits_balance,
        "topup_ai_credits_balance": org.topup_ai_credits_balance,
        "trial_ends_at": org.trial_ends_at,
        "grace_period_ends_at": org.grace_period_ends_at,
        "subscription_ends_at": org.subscription_ends_at,
        "created_at": org.created_at,
        "deleted_at": org.deleted_at,
        "is_agency": org.is_agency,
        # "Active" with no Razorpay mandate = a comped/manually-activated account. It is
        # never re-checked by any sweep, so it stays free forever unless someone notices.
        "is_comped": org.subscription_status == "active" and not org.razorpay_subscription_id,
        "razorpay_subscription_id": org.razorpay_subscription_id,
    }


def _effective_flags(db: Session) -> dict:
    return {
        "india_phone_trial": india_phone_trial_enabled(db),
        "row_phone_trial": row_phone_trial_enabled(db),
    }


@router.get("/flags")
def get_flags(db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    """Global runtime feature flags (effective value: DB override or env default)."""
    return _effective_flags(db)


@router.patch("/flags")
def update_flags(
    body: FlagsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    """Flip global feature flags live. Phone-trial flags: ON = that region starts the
    trial with a phone number only; OFF = it goes through the Razorpay checkout."""
    changes = {k: v for k, v in body.model_dump(exclude={"reason"}).items() if v is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="no_flags: provide at least one flag to update.")
    for key, value in changes.items():
        set_flag(db, key, value)
    # Global flags, but AuditLog.organization_id is NOT NULL — log against the actor's
    # own org so the override is still never silent.
    if admin.organization_id:
        _audit(db, actor=admin, organization_id=admin.organization_id,
               action="flags.update", changes=changes,
               reason=body.reason or "super-admin toggle")
    db.commit()
    return _effective_flags(db)


@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    status_counts = dict(
        db.query(Organization.subscription_status, func.count())
        .group_by(Organization.subscription_status)
        .all()
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    failed_syncs_7d = (
        db.query(func.count(SyncLog.id))
        .filter(SyncLog.status.in_(["Failed", "ProviderError"]), SyncLog.created_at >= cutoff)
        .scalar()
    )
    needs_remandate = (
        db.query(func.count(Organization.id))
        .filter(Organization.subscription_needs_remandate.is_(True))
        .scalar()
    )
    credits_in_circulation = db.query(
        func.coalesce(func.sum(Organization.monthly_ai_credits_balance), 0)
        + func.coalesce(func.sum(Organization.topup_ai_credits_balance), 0)
    ).scalar()
    # Split the 'trial' status the same way the tabs do: never-started (onboarding) vs
    # a running clock. One lumped "Trial" number hid how many signups never converted.
    onboarding = (
        db.query(func.count(Organization.id))
        .filter(Organization.subscription_status == "trial", Organization.trial_ends_at.is_(None))
        .scalar()
    )
    # Money and funnel, not just row counts. MRR is derived from what the mandates
    # actually bill (paid_location_quota falling back to location_quota) at each org's own
    # rate, so a custom-priced enterprise deal is counted at its real price.
    from app.services.billing.pricing_service import PricingService
    mrr_paise = 0
    mrr_skipped = []
    for org in db.query(Organization).filter(
        Organization.subscription_status == "active", Organization.deleted_at.is_(None)
    ).all():
        # No Razorpay mandate = nothing is being billed, so this org contributes nothing.
        # These are the comped/internal accounts (typically quota 9999) that a super-admin
        # flipped to active by hand; pricing them would both inflate MRR and, since 9999 is
        # far above the sellable ceiling, trip the range guard below. NOTE: this assumes
        # Razorpay is the only way money arrives — an offline/invoiced customer would need
        # counting separately.
        if not org.razorpay_subscription_id:
            continue
        qty = org.paid_location_quota or org.location_quota or 0
        if qty <= 0:
            continue
        tier = org.plan_tier or "basic"
        try:
            monthly = PricingService.compute_monthly_price_paise(
                qty, tier, PricingService.custom_rate(org, tier))
        except Exception:
            # compute_monthly_price_paise runs validate_location_count, which is a guard on
            # REQUEST input (1..MAX_LOCATIONS) and raises HTTPException. A single org whose
            # quota sits outside that range — a manual override, a legacy row — turned this
            # whole dashboard into a 400 and took the Accounts page down with it. A reporting
            # endpoint must never fail on one bad row: skip it and say which, so the number
            # is visibly incomplete rather than quietly wrong.
            logger.warning("MRR: skipped org %s (quota=%s tier=%s)", org.id, qty, tier)
            mrr_skipped.append(org.id)
            continue
        mrr_paise += plan_config.price_with_gst(monthly)["total_paise"]

    trials_ending_48h = (
        db.query(func.count(Organization.id))
        .filter(Organization.subscription_status == "trial",
                Organization.trial_ends_at.isnot(None),
                Organization.trial_ends_at > datetime.now(timezone.utc),
                Organization.trial_ends_at <= datetime.now(timezone.utc) + timedelta(hours=48),
                Organization.deleted_at.is_(None))
        .scalar()
    )
    # Everyone who ever started a clock, vs everyone who ever paid — the honest
    # denominator for "does the trial convert?".
    started_trial = (
        db.query(func.count(Organization.id))
        .filter(or_(Organization.trial_ends_at.isnot(None),
                    Organization.subscription_status.in_(["active", "past_due", "locked"])))
        .scalar()
    )
    ever_paid = (
        db.query(func.count(func.distinct(BillingTransaction.organization_id)))
        .filter(BillingTransaction.transaction_type == "subscription_charge",
                BillingTransaction.status == "success")
        .scalar()
    )
    # If this goes quiet, Razorpay webhook delivery is broken and every activation is
    # riding on the /confirm fast path plus the 30-minute reconcile sweep.
    last_webhook = db.query(func.max(BillingWebhookEvent.processed_at)).scalar()

    return {
        "mrr_paise": mrr_paise,
        # Non-empty means MRR excludes these orgs (unpriceable quota) — surfaced so the
        # figure is never silently understated.
        "mrr_skipped_org_ids": mrr_skipped,
        "trials_ending_48h": trials_ending_48h,
        "trial_to_paid_pct": round(ever_paid / started_trial * 100) if started_trial else 0,
        "ever_paid_organizations": ever_paid,
        "last_webhook_at": last_webhook,
        "total_organizations": db.query(func.count(Organization.id)).scalar(),
        "total_users": db.query(func.count(User.id)).scalar(),
        "total_locations": db.query(func.count(Location.id)).scalar(),
        "by_status": {(k or "unknown"): v for k, v in status_counts.items()},
        "active_organizations": status_counts.get("active", 0),
        "onboarding_organizations": onboarding,
        "trial_organizations": status_counts.get("trial", 0) - onboarding,   # running clocks only
        "past_due_organizations": status_counts.get("past_due", 0),
        "locked_organizations": status_counts.get("locked", 0),
        "needs_remandate": needs_remandate,
        "failed_syncs_7d": failed_syncs_7d,
        "credits_in_circulation": credits_in_circulation,
    }


@router.get("/organizations")
def list_organizations(
    db: Session = Depends(get_db),
    _: User = Depends(superadmin_required),
    q: Optional[str] = None,
    subscription_status: Optional[str] = None,
    deleted: str = Query("exclude", pattern="^(exclude|only|include)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    query = db.query(Organization)
    if q:
        # Support conversations arrive as an email, a phone number or a Razorpay id —
        # name-only search meant none of them could be looked up.
        term = q.strip()
        digits = re.sub(r"[^\d]", "", term)
        conditions = [
            Organization.name.ilike(f"%{term}%"),
            Organization.razorpay_subscription_id == term,
            Organization.razorpay_customer_id.ilike(f"%{term}%"),
            Organization.id.in_(
                db.query(User.organization_id).filter(User.email.ilike(f"%{term}%"))
            ),
        ]
        if len(digits) >= 6:
            # Match a phone however it was typed: +919876543210, 9876543210, 09876…
            conditions.append(Organization.id.in_(
                db.query(User.organization_id).filter(User.phone.ilike(f"%{digits[-10:]}%"))
            ))
        query = query.filter(or_(*conditions))
    # Tabs. 'onboarding' and 'trial' split the DB's single 'trial' status: an onboarding
    # org has connected Google but never started a clock (no payment method / phone yet),
    # a trial org is counting down. 'paid' = a live paying subscription.
    if subscription_status == "onboarding":
        query = query.filter(Organization.subscription_status == "trial",
                             Organization.trial_ends_at.is_(None))
    elif subscription_status == "trial":
        query = query.filter(Organization.subscription_status == "trial",
                             Organization.trial_ends_at.isnot(None))
    elif subscription_status == "paid":
        query = query.filter(Organization.subscription_status == "active")
    elif subscription_status:
        query = query.filter(Organization.subscription_status == subscription_status)
    # Trash handling: hide soft-deleted by default; 'only' = the trash view, 'include' = both.
    if deleted == "exclude":
        query = query.filter(Organization.deleted_at.is_(None))
    elif deleted == "only":
        query = query.filter(Organization.deleted_at.isnot(None))

    total = query.count()
    orgs = query.order_by(Organization.created_at.desc()).limit(limit).offset(offset).all()
    org_ids = [o.id for o in orgs]

    # Grouped counts (avoids N+1) — empty IN() is invalid, so guard on org_ids.
    # Live users only: counting soft-deleted seats inflated the number, and it hid the
    # orphaned workspaces (0 live users, unreachable — nobody can log into them) that
    # a hard DELETE on `users` leaves behind. The UI badges those.
    user_counts = dict(
        db.query(User.organization_id, func.count())
        .filter(User.organization_id.in_(org_ids), User.deleted_at.is_(None))
        .group_by(User.organization_id).all()
    ) if org_ids else {}
    loc_counts = dict(
        db.query(Location.organization_id, func.count())
        .filter(Location.organization_id.in_(org_ids))
        .group_by(Location.organization_id).all()
    ) if org_ids else {}

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_org_row(o, user_counts.get(o.id, 0), loc_counts.get(o.id, 0)) for o in orgs],
    }


@router.get("/organizations/{org_id}")
def get_organization(
    org_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(superadmin_required),
    user_limit: int = Query(25, ge=1, le=200),
    user_offset: int = Query(0, ge=0),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Paged: an agency org can have hundreds of seats, and this endpoint previously
    # serialized every one of them on every page load.
    users_query = db.query(User).filter(User.organization_id == org_id)
    users_total = users_query.count()
    users = (
        users_query.order_by(User.created_at.asc())
        .limit(user_limit).offset(user_offset).all()
    )
    locations = db.query(Location).filter(Location.organization_id == org_id).all()
    transactions = (
        db.query(BillingTransaction)
        .filter(BillingTransaction.organization_id == org_id)
        .order_by(BillingTransaction.created_at.desc()).limit(20).all()
    )
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.organization_id == org_id)
        .order_by(AuditLog.created_at.desc()).limit(25).all()
    )
    sync_state = db.query(OrganizationSyncState).filter(
        OrganizationSyncState.organization_id == org_id
    ).first()

    # Count live seats, not the current page: len(users) reported "25 users" for any org
    # past the first page, and counted soft-deleted seats as live.
    users_live = db.query(func.count(User.id)).filter(
        User.organization_id == org_id, User.deleted_at.is_(None)
    ).scalar()
    org_detail = _org_row(org, users_live, len(locations))
    org_detail.update({
        "billing_cycle": org.billing_cycle,
        "ai_credits_reset_date": org.ai_credits_reset_date,
        "razorpay_customer_id": org.razorpay_customer_id,
        "razorpay_subscription_id": org.razorpay_subscription_id,
        "subscription_needs_remandate": org.subscription_needs_remandate,
        "paid_location_quota": org.paid_location_quota,
        "remandate_due_at": org.remandate_due_at,
        "allow_extra_trial": org.allow_extra_trial,
        "trial_reminder_sent_at": org.trial_reminder_sent_at,
        "custom_prices": org.custom_prices or {},
        "custom_credits_per_location": org.custom_credits_per_location,
        # Every tier's standard rate, so the panel can show what a negotiated rate is
        # being discounted FROM without hardcoding the price sheet in the frontend.
        "standard_prices": {
            tier: plan_config.get_plan(tier)["price"] for tier in plan_config.PLANS
        },
    })

    return {
        "organization": org_detail,
        "users_total": users_total,
        "users_limit": user_limit,
        "users_offset": user_offset,
        "users": [
            {
                "id": u.id, "email": u.email, "name": u.name, "role": u.role,
                "phone": u.phone, "is_active": u.is_active, "viewer_scope": u.viewer_scope,
                "created_at": u.created_at, "deleted_at": u.deleted_at,
            }
            for u in users
        ],
        "locations": [
            {
                "id": l.id, "location_name": l.location_name,
                "billing_status": l.billing_status, "sync_status": l.sync_status,
                "average_rating": l.average_rating, "total_reviews": l.total_reviews,
                "last_synced_at": l.last_synced_at,
            }
            for l in locations
        ],
        # BillingTransaction field names vary across the codebase; getattr keeps this
        # robust whether the column is `transaction_type`/`type`, `credits`, etc.
        "transactions": [
            {
                "id": t.id,
                "type": getattr(t, "transaction_type", None) or getattr(t, "type", None),
                "amount_paise": t.amount_paise,
                "credits": getattr(t, "credits", None),
                "status": t.status,
                "source": getattr(t, "source", None),
                "invoice_url": getattr(t, "invoice_url", None),
                "created_at": t.created_at,
            }
            for t in transactions
        ],
        "audit": [
            {
                "id": a.id, "action": a.action, "details": a.details,
                "actor_user_id": a.actor_user_id, "target_user_id": a.target_user_id,
                "created_at": a.created_at,
            }
            for a in audit
        ],
        "sync_state": {
            "sync_in_progress": sync_state.sync_in_progress if sync_state else False,
            "sync_started_at": sync_state.sync_started_at if sync_state else None,
            "last_sync_status": sync_state.last_sync_status if sync_state else None,
            "last_sync_error": sync_state.last_sync_error if sync_state else None,
            "last_review_sync_at": sync_state.last_review_sync_at if sync_state else None,
        },
    }


@router.patch("/organizations/{org_id}")
def update_organization(
    org_id: int,
    payload: OrgUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if payload.plan_tier is not None and payload.plan_tier not in plan_config.PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan_tier. Allowed: {list(plan_config.PLANS)}")
    if payload.subscription_status is not None and payload.subscription_status not in VALID_SUBSCRIPTION_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid subscription_status. Allowed: {sorted(VALID_SUBSCRIPTION_STATUSES)}")

    if payload.custom_prices is not None:
        bad_tiers = sorted(set(payload.custom_prices) - set(plan_config.PLANS))
        if bad_tiers:
            raise HTTPException(status_code=400,
                                detail=f"Unknown tier(s) in custom_prices: {bad_tiers}. "
                                       f"Allowed: {list(plan_config.PLANS)}")
        if any(v < 0 for v in payload.custom_prices.values()):
            raise HTTPException(status_code=400, detail="custom_prices rates must be >= 0 (paise).")

    # The rate this org is billed at TODAY, so the reschedule below only fires when the
    # money actually moved — editing the Pro rate for a Basic client changes nothing yet.
    from app.services.billing.pricing_service import PricingService
    current_tier = payload.plan_tier or org.plan_tier or "basic"
    rate_before = PricingService.custom_rate(org, current_tier)

    changes = {}
    # Clearing custom pricing wins over any per-field values in the same request. The
    # legacy single-rate column is cleared too, so a rollback can't resurrect an old deal.
    if payload.clear_custom_pricing:
        for field in ("custom_prices", "custom_credits_per_location", "custom_price_paise"):
            if getattr(org, field) is not None:
                changes[field] = {"old": getattr(org, field), "new": None}
                setattr(org, field, None)
    else:
        for field in _ORG_EDITABLE:
            new = getattr(payload, field)
            if new is None:
                continue
            old = getattr(org, field)
            if old != new:
                changes[field] = {"old": old, "new": new}
                setattr(org, field, new)
        if payload.custom_prices is not None:
            # Replace wholesale: the panel always sends every tier, so an omitted tier
            # means "no deal on that tier" (standard price), not "leave as-is".
            new_prices = payload.custom_prices or None
            if (org.custom_prices or None) != new_prices:
                changes["custom_prices"] = {"old": org.custom_prices, "new": new_prices}
                org.custom_prices = new_prices

    if not changes:
        raise HTTPException(status_code=400, detail="No changes provided")

    _audit(db, actor=admin, organization_id=org.id, action="superadmin.org_update",
           changes=changes, reason=payload.reason)
    db.commit()

    # If the per-location PRICE changed and the org is already on an active subscription,
    # schedule the new amount on their Razorpay plan at CYCLE END — so it takes effect at
    # the next renewal, never mid-cycle. (New clients with no subscription yet just get
    # billed the custom rate when they check out; credits-only changes need no plan edit —
    # they apply on the next charge.)
    price_moved = PricingService.custom_rate(org, current_tier) != rate_before
    plan_change = None
    if price_moved and org.razorpay_subscription_id \
            and org.subscription_status == "active" and (org.location_quota or 0) >= 1:
        from app.services.billing.subscription_service import SubscriptionService
        try:
            plan_change = SubscriptionService.update_subscription_plan_for_quota(db, org.id)
            db.commit()
        except Exception as e:
            logger.error("Custom-price plan reschedule failed for org %s: %s", org.id, e)
            plan_change = "error"

    msg = "Organization updated"
    if "custom_prices" in changes and not price_moved:
        # A rate was set for a tier this org isn't on — it only bills if they switch to it.
        msg = (f"Organization updated. This org is on the {current_tier} tier, so the rate you "
               f"changed applies only if they move to that tier.")
    elif price_moved and plan_change is None:
        # Price changed but no live subscription reschedule ran (not active, no Razorpay
        # sub, or no quota). Say so — otherwise it looks like the save silently no-op'd.
        msg = ("Organization updated. No active card subscription to reschedule — the custom "
               "rate will be billed when this org next checks out.")
    if plan_change == "upgraded":
        msg = "Organization updated — new price takes effect at the next renewal."
    elif plan_change == "needs_remandate":
        msg = ("Organization updated, but this client pays via UPI Autopay — Razorpay can't "
               "change the amount automatically. They must approve a new mandate for the new "
               "price; the old amount keeps billing until they do.")
    elif plan_change == "error":
        msg = ("Organization updated, but scheduling the new price on their subscription failed "
               "(transient Razorpay error). Re-save to retry.")
    return {"message": msg, "changes": changes, "plan_change": plan_change}


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changes = {}

    if payload.role is not None and payload.role != user.role:
        if payload.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role. Allowed: {sorted(VALID_ROLES)}")
        changes["role"] = {"old": user.role, "new": payload.role}
        user.role = payload.role
        # Viewer is the only role with org-wide vs assigned scope; normalise the rest.
        # ponytail: super-admin role change skips the Store-Manager single-location
        # invariant — location assignments stay managed via the normal Team UI.
        user.viewer_scope = "organization" if payload.role == Role.VIEWER else "assigned"
        user.token_version += 1

    if payload.is_active is not None and payload.is_active != user.is_active:
        changes["is_active"] = {"old": user.is_active, "new": payload.is_active}
        user.is_active = payload.is_active
        user.token_version += 1

    if payload.force_logout:
        user.token_version += 1
        changes["force_logout"] = True

    if not changes:
        raise HTTPException(status_code=400, detail="No changes provided")

    _audit(db, actor=admin, organization_id=user.organization_id, action="superadmin.user_update",
           changes=changes, reason=payload.reason, target_user_id=user.id)
    db.commit()
    return {"message": "User updated", "changes": changes}


# --- Account deletion (soft delete + restore; hard purge runs on a daily task) -------

def _purge_date(deleted_at):
    return deleted_at + timedelta(days=plan_config.ACCOUNT_PURGE_GRACE_DAYS) if deleted_at else None


@router.delete("/organizations/{org_id}")
def delete_organization(
    org_id: int,
    body: AdminActionBody = AdminActionBody(),
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    """Soft-delete an org and everything under it. Members lose access immediately; the
    data is kept for ACCOUNT_PURGE_GRACE_DAYS so it can be restored, then hard-purged
    (cascade) by the daily purge task."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if org.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Organization is already deleted.")
    # Stop billing now, not at purge — a live mandate would otherwise keep charging the
    # customer through the 14-day grace window. Trade-off: restore can't revive billing,
    # a restored org must re-authorize a fresh mandate.
    from app.services.billing.subscription_service import SubscriptionService
    SubscriptionService.cancel_active_subscriptions(org)
    org.deleted_at = datetime.now(timezone.utc)
    _audit(db, actor=admin, organization_id=org.id, action="superadmin.org_delete",
           changes={"deleted_at": {"old": None, "new": org.deleted_at}}, reason=body.reason)
    db.commit()
    return {"message": "Organization deleted", "deleted_at": org.deleted_at,
            "purge_after": _purge_date(org.deleted_at)}


@router.post("/organizations/{org_id}/restore")
def restore_organization(
    org_id: int,
    body: AdminActionBody = AdminActionBody(),
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    """Undo a soft-delete before the purge window elapses."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if org.deleted_at is None:
        raise HTTPException(status_code=409, detail="Organization is not deleted.")
    org.deleted_at = None
    _audit(db, actor=admin, organization_id=org.id, action="superadmin.org_restore",
           changes={"deleted_at": {"old": "set", "new": None}}, reason=body.reason)
    db.commit()
    return {"message": "Organization restored"}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    body: AdminActionBody = AdminActionBody(),
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    """Soft-delete a single team member. They lose access immediately and are hard-purged
    after the grace window; org data (posts, audit trails) survives with their references
    nulled. Refuses to delete the org's last remaining Owner (would orphan the account)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.deleted_at is not None:
        raise HTTPException(status_code=409, detail="User is already deleted.")
    if settings.is_superadmin(user.email):
        raise HTTPException(status_code=403, detail="Cannot delete a super-admin account.")
    # Don't orphan an org by removing its last active Owner.
    if user.role == Role.OWNER:
        other_owners = db.query(User).filter(
            User.organization_id == user.organization_id,
            User.role == Role.OWNER,
            User.id != user.id,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        ).count()
        if other_owners == 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete the organization's only Owner. Delete the organization instead.",
            )
    user.deleted_at = datetime.now(timezone.utc)
    user.token_version += 1  # invalidate any live sessions
    _audit(db, actor=admin, organization_id=user.organization_id, action="superadmin.user_delete",
           changes={"deleted_at": {"old": None, "new": user.deleted_at}}, reason=body.reason,
           target_user_id=user.id)
    db.commit()
    return {"message": "User deleted", "deleted_at": user.deleted_at,
            "purge_after": _purge_date(user.deleted_at)}


@router.post("/users/{user_id}/restore")
def restore_user(
    user_id: int,
    body: AdminActionBody = AdminActionBody(),
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.deleted_at is None:
        raise HTTPException(status_code=409, detail="User is not deleted.")
    user.deleted_at = None
    _audit(db, actor=admin, organization_id=user.organization_id, action="superadmin.user_restore",
           changes={"deleted_at": {"old": "set", "new": None}}, reason=body.reason,
           target_user_id=user.id)
    db.commit()
    return {"message": "User restored"}


@router.patch("/locations/{location_id}")
def update_location(
    location_id: int,
    payload: LocationUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    if payload.billing_status not in {"active", "pending_payment"}:
        raise HTTPException(status_code=400, detail="billing_status must be 'active' or 'pending_payment'")
    if loc.billing_status == payload.billing_status:
        raise HTTPException(status_code=400, detail="No change")

    changes = {"billing_status": {"old": loc.billing_status, "new": payload.billing_status}}
    loc.billing_status = payload.billing_status
    _audit(db, actor=admin, organization_id=loc.organization_id, action="superadmin.location_update",
           changes={**changes, "location_id": location_id}, reason=payload.reason)
    db.commit()

    # This endpoint deliberately skips the quota ceiling and the reassign cooldown that
    # the customer-facing /billing/locations/active enforces — a super-admin override
    # should not be blocked by them. But going over quota is not free: the next charge
    # re-applies the paid quota and locks the surplus back to pending_payment, which reads
    # to the customer as us silently switching their locations off. Say so here.
    msg = "Location updated"
    org = db.query(Organization).filter(Organization.id == loc.organization_id).first()
    quota = (org.location_quota or 0) if org else 0
    active_now = db.query(func.count(Location.id)).filter(
        Location.organization_id == loc.organization_id,
        Location.billing_status == "active",
    ).scalar() or 0
    if quota and active_now > quota:
        msg = (f"Location updated, but this org now has {active_now} active locations against a "
               f"paid quota of {quota}. The next renewal will lock the surplus back to "
               f"pending_payment — raise the quota (or sell the add-on) to make it stick.")
    return {"message": msg, "changes": changes, "active_locations": active_now, "location_quota": quota}


@router.post("/organizations/{org_id}/sync")
def force_review_sync(
    org_id: int,
    body: Optional[AdminActionBody] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    """Queue an org-wide review re-sync, mirroring the user-facing /reviews/sync."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    loc_ids = [lid for (lid,) in db.query(Location.id).filter(Location.organization_id == org_id).all()]
    if not loc_ids:
        raise HTTPException(status_code=400, detail="Organization has no locations to sync")

    chunk_size = getattr(settings, "REVIEW_SYNC_CHUNK_SIZE", 20)
    task_ids = []
    for i in range(0, len(loc_ids), chunk_size):
        chunk = loc_ids[i:i + chunk_size]
        # actor user_id=None: the acting super-admin belongs to a different org, so
        # don't attribute this sync to a cross-org user in the target org's logs.
        task = celery.send_task(
            "app.tasks.sync_reviews_chunk_task",
            args=[chunk, org_id, "Manual", None],
        )
        task_ids.append(task.id)

    reason = body.reason if body else None
    _audit(db, actor=admin, organization_id=org_id, action="superadmin.force_review_sync",
           changes={"locations": len(loc_ids), "batches": len(task_ids)}, reason=reason)
    db.commit()
    return {"message": f"Queued review sync for {len(loc_ids)} locations in {len(task_ids)} batches", "task_ids": task_ids}


@router.post("/organizations/{org_id}/reset-sync")
def reset_stuck_sync(
    org_id: int,
    body: Optional[AdminActionBody] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    """Clear an orphaned in-progress sync lock (e.g. after a worker crash)."""
    state = db.query(OrganizationSyncState).filter(OrganizationSyncState.organization_id == org_id).first()
    if not state:
        raise HTTPException(status_code=404, detail="No sync state for this organization")

    before = {"sync_in_progress": state.sync_in_progress, "insights_sync_in_progress": state.insights_sync_in_progress}
    state.sync_in_progress = False
    state.insights_sync_in_progress = False
    state.last_sync_status = "Reset by super-admin"

    reason = body.reason if body else None
    _audit(db, actor=admin, organization_id=org_id, action="superadmin.reset_sync",
           changes={"before": before}, reason=reason)
    db.commit()
    return {"message": "Sync state reset"}


@router.get("/audit")
def list_audit(
    db: Session = Depends(get_db),
    _: User = Depends(superadmin_required),
    action: Optional[str] = None,
    organization_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Cross-org operator action trail. Filter by action substring / org / actor."""
    base = db.query(AuditLog)
    if action:
        base = base.filter(AuditLog.action.ilike(f"%{action}%"))
    if organization_id is not None:
        base = base.filter(AuditLog.organization_id == organization_id)
    if actor_user_id is not None:
        base = base.filter(AuditLog.actor_user_id == actor_user_id)

    total = base.count()

    Actor = aliased(User)
    rows = (
        base.add_columns(Organization.name.label("org_name"), Actor.email.label("actor_email"))
        .outerjoin(Organization, Organization.id == AuditLog.organization_id)
        .outerjoin(Actor, Actor.id == AuditLog.actor_user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit).offset(offset)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": log.id,
                "action": log.action,
                "details": log.details,
                "organization_id": log.organization_id,
                "org_name": org_name,
                "actor_user_id": log.actor_user_id,
                "actor_email": actor_email,
                "target_user_id": log.target_user_id,
                "created_at": log.created_at,
            }
            for (log, org_name, actor_email) in rows
        ],
    }


# --- support actions on a live subscription ----------------------------------

@router.post("/organizations/{org_id}/reconcile")
def reconcile_subscription(
    org_id: int,
    body: Optional[AdminActionBody] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    """Pull this org's subscription state from Razorpay and apply it now.

    The answer to "I paid but I'm still locked". The periodic sweep does this every 30
    minutes; before this endpoint existed, support's only option in the panel was to
    hand-edit subscription_status, which then drifted from what Razorpay actually says.
    """
    from app.services.billing.subscription_service import SubscriptionService

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not org.razorpay_subscription_id:
        raise HTTPException(status_code=400, detail="This organization has no Razorpay subscription to reconcile.")

    before = org.subscription_status
    try:
        active = SubscriptionService.reconcile_subscription(db, org.id)
    except Exception as e:
        logger.error("Manual reconcile failed for org %s: %s", org_id, e)
        raise HTTPException(status_code=502, detail=f"Razorpay call failed: {e}")

    db.refresh(org)
    _audit(db, actor=admin, organization_id=org.id, action="superadmin.reconcile",
           changes={"subscription_status": {"old": before, "new": org.subscription_status}},
           reason=body.reason if body else None)
    db.commit()
    msg = ("Razorpay confirms this subscription is paid — entitlements applied."
           if active else
           "Razorpay does not report this subscription as active (no charge landed yet). "
           "Nothing was changed.")
    return {"message": msg, "active": active, "subscription_status": org.subscription_status}


class CancelBody(AdminActionBody):
    immediate: bool = False  # default: let the paid period run out


@router.post("/organizations/{org_id}/cancel-subscription")
def cancel_subscription(
    org_id: int,
    body: CancelBody = CancelBody(),
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    """Cancel the org's Razorpay mandate.

    Default is at cycle end: the customer keeps what they paid for and simply stops
    renewing (subscription_ends_at carries the paid-through date, and the lifecycle sweep
    locks them once it passes). `immediate` stops it now — use that for a refund case.
    Until this existed, cancelling meant someone doing it by hand in the Razorpay
    dashboard after a WhatsApp message, with nothing recorded on our side.
    """
    from app.services.billing.subscription_service import SubscriptionService

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    sub_id = org.razorpay_subscription_id
    if not sub_id:
        raise HTTPException(status_code=400, detail="This organization has no active mandate to cancel.")

    client = SubscriptionService.get_razorpay_client()
    try:
        sub = client.subscription.cancel(sub_id, {"cancel_at_cycle_end": 0 if body.immediate else 1})
    except Exception as e:
        logger.error("Cancel failed for org %s sub %s: %s", org_id, sub_id, e)
        raise HTTPException(status_code=502, detail=f"Razorpay refused the cancellation: {e}")

    before = {"subscription_status": org.subscription_status, "subscription_ends_at": org.subscription_ends_at}
    if body.immediate:
        org.subscription_status = "locked"
        org.subscription_ends_at = datetime.now(timezone.utc)
    else:
        # Stays 'active' until the paid period elapses; the sweep locks it after that.
        current_end = sub.get("current_end") or sub.get("charge_at")
        org.subscription_ends_at = (datetime.fromtimestamp(current_end, tz=timezone.utc)
                                    if current_end else datetime.now(timezone.utc))
    _audit(db, actor=admin, organization_id=org.id, action="superadmin.cancel_subscription",
           changes={"before": before, "immediate": body.immediate,
                    "subscription_ends_at": org.subscription_ends_at,
                    "razorpay_subscription_id": sub_id},
           reason=body.reason)
    db.commit()
    return {
        "message": ("Mandate cancelled immediately — the org is locked now."
                    if body.immediate else
                    f"Mandate cancelled. Access continues until {org.subscription_ends_at:%d %b %Y}, "
                    "then the org locks automatically."),
        "subscription_ends_at": org.subscription_ends_at,
    }


class ExtendTrialBody(AdminActionBody):
    days: int = Field(default=7, ge=1, le=90)


@router.post("/organizations/{org_id}/extend-trial")
def extend_trial(
    org_id: int,
    body: ExtendTrialBody = ExtendTrialBody(),
    db: Session = Depends(get_db),
    admin: User = Depends(superadmin_required),
):
    """Push a running trial's clock out by N days, and move the Razorpay debit with it.

    Editing trial_ends_at alone was a trap: for a card trial the first debit is pinned to
    the mandate's start_at, so "I gave them another week" still charged them on day 7,
    mid-extension. Razorpay cannot reschedule an existing mandate's first charge, so when
    one exists this refuses rather than quietly lying about what the customer will be
    charged — cancel and re-checkout instead.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if org.subscription_status != "trial" or org.trial_ends_at is None:
        raise HTTPException(
            status_code=409,
            detail="Only a running trial can be extended (this org has no trial clock).",
        )
    if org.razorpay_subscription_id:
        raise HTTPException(
            status_code=409,
            detail="This trial has a payment mandate attached: Razorpay debits it on the "
                   "originally scheduled date and the first charge cannot be moved. Cancel "
                   "the mandate and have them check out again to change the date.",
        )

    before = org.trial_ends_at
    org.trial_ends_at = before + timedelta(days=body.days)
    # Let the new deadline warn them again — they were already told the old date.
    org.trial_reminder_sent_at = None
    _audit(db, actor=admin, organization_id=org.id, action="superadmin.extend_trial",
           changes={"trial_ends_at": {"old": before, "new": org.trial_ends_at}, "days": body.days},
           reason=body.reason)
    db.commit()
    return {"message": f"Trial extended by {body.days} day(s) to {org.trial_ends_at:%d %b %Y}.",
            "trial_ends_at": org.trial_ends_at}
