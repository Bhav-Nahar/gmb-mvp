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
from sqlalchemy import func
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
from app.schemas.admin import OrgUpdate, AdminUserUpdate, LocationUpdate, AdminActionBody

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_SUBSCRIPTION_STATUSES = {"trial", "active", "past_due", "locked"}
VALID_ROLES = {Role.OWNER, Role.ADMIN, Role.REGIONAL_MANAGER, Role.STORE_MANAGER, Role.VIEWER}

# Org columns a super-admin may set directly (validated below where applicable).
_ORG_EDITABLE = [
    "plan_tier",
    "subscription_status",
    "location_quota",
    "monthly_ai_credits_balance",
    "topup_ai_credits_balance",
    "trial_ends_at",
    "grace_period_ends_at",
    "custom_price_paise",
    "custom_credits_per_location",
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
    }


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
    return {
        "total_organizations": db.query(func.count(Organization.id)).scalar(),
        "total_users": db.query(func.count(User.id)).scalar(),
        "total_locations": db.query(func.count(Location.id)).scalar(),
        "by_status": {(k or "unknown"): v for k, v in status_counts.items()},
        "active_organizations": status_counts.get("active", 0),
        "trial_organizations": status_counts.get("trial", 0),
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
        query = query.filter(Organization.name.ilike(f"%{q}%"))
    if subscription_status:
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
    user_counts = dict(
        db.query(User.organization_id, func.count())
        .filter(User.organization_id.in_(org_ids))
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
def get_organization(org_id: int, db: Session = Depends(get_db), _: User = Depends(superadmin_required)):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    users = db.query(User).filter(User.organization_id == org_id).order_by(User.created_at.asc()).all()
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

    org_detail = _org_row(org, len(users), len(locations))
    org_detail.update({
        "billing_cycle": org.billing_cycle,
        "ai_credits_reset_date": org.ai_credits_reset_date,
        "razorpay_customer_id": org.razorpay_customer_id,
        "razorpay_subscription_id": org.razorpay_subscription_id,
        "subscription_needs_remandate": org.subscription_needs_remandate,
        "paid_location_quota": org.paid_location_quota,
        "remandate_due_at": org.remandate_due_at,
        "custom_price_paise": org.custom_price_paise,
        "custom_credits_per_location": org.custom_credits_per_location,
    })

    return {
        "organization": org_detail,
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

    changes = {}
    # Clearing custom pricing wins over any per-field values in the same request.
    if payload.clear_custom_pricing:
        for field in ("custom_price_paise", "custom_credits_per_location"):
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
    plan_change = None
    if "custom_price_paise" in changes and org.razorpay_subscription_id \
            and org.subscription_status == "active" and (org.location_quota or 0) >= 1:
        from app.services.billing.subscription_service import SubscriptionService
        try:
            plan_change = SubscriptionService.update_subscription_plan_for_quota(db, org.id)
            db.commit()
        except Exception as e:
            logger.error("Custom-price plan reschedule failed for org %s: %s", org.id, e)
            plan_change = "error"

    msg = "Organization updated"
    if "custom_price_paise" in changes and plan_change is None:
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
    return {"message": "Location updated", "changes": changes}


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
