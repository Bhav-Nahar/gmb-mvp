from typing import List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update, func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import (get_current_user, admin_required, require_feature,
                          require_location_access, get_user_location_ids)
from app.core import plan_config
from app.models.user import User
from app.models.organization import Organization
from app.models.review import Review
from app.models.location import Location
from app.models.activity_log import ActivityLog
from app.schemas.reply_template import ReplyTemplateCreate, ReplyTemplateUpdate, ReplyTemplateResponse
from app.services.reply_template_service import ReplyTemplateService, MIN_TEMPLATES_FOR_AUTO_REPLY
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_model=List[ReplyTemplateResponse])
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """List all reply templates for the current organization."""
    try:
        return ReplyTemplateService.list_templates(db, current_user.organization_id)
    except Exception as e:
        logger.error(f"Failed to list templates: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.get("/auto-reply", status_code=status.HTTP_200_OK)
def get_auto_reply_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Org-wide auto-reply state + whether enough 4-5★ templates exist to enable it."""
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    count = ReplyTemplateService.count_positive_templates(db, current_user.organization_id)
    return {
        "enabled_at": org.auto_reply_enabled_at if org else None,
        "mode": org.auto_reply_mode if org else "template",
        "positive_template_count": count,
        "min_required": MIN_TEMPLATES_FOR_AUTO_REPLY,
        # AI mode spends a credit per reply and silently stops at zero — show the
        # balance on the same screen as the toggle.
        "ai_credits": ((org.monthly_ai_credits_balance or 0) + (org.topup_ai_credits_balance or 0)) if org else 0,
    }

@router.post("/auto-reply/enable", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_feature(plan_config.FEATURE_AUTO_REPLY))])
def enable_auto_reply(
    mode: str = "template",
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Turn on org-wide auto-reply for 4-5★ reviews.

    mode=template: reply from the org's saved templates, future reviews only.
    mode=ai: generate each reply with the LLM (1 credit each) and drip 10-20 per
    location per day, newest reviews first, then a random sample of the backlog.
    """
    if mode not in ("template", "ai"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mode must be 'template' or 'ai'")
    if mode == "template":
        count = ReplyTemplateService.count_positive_templates(db, current_user.organization_id)
        if count < MIN_TEMPLATES_FOR_AUTO_REPLY:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Add at least {MIN_TEMPLATES_FOR_AUTO_REPLY} reply templates for 4-5★ reviews before enabling auto-reply."
            )
    now = datetime.now(timezone.utc)
    db.execute(
        update(Organization)
        .where(Organization.id == current_user.organization_id)
        .where(Organization.auto_reply_enabled_at.is_(None))
        .values(auto_reply_enabled_at=now)
    )
    # Mode is switchable while already enabled, so it is set unconditionally.
    db.execute(
        update(Organization)
        .where(Organization.id == current_user.organization_id)
        .values(auto_reply_mode=mode)
    )
    db.commit()
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    return {"status": "enabled", "enabled_at": org.auto_reply_enabled_at, "mode": org.auto_reply_mode}

@router.post("/auto-reply/disable", status_code=status.HTTP_200_OK)
def disable_auto_reply(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Turn off org-wide auto-reply. Past auto-replies stay; no new ones are posted."""
    db.execute(
        update(Organization)
        .where(Organization.id == current_user.organization_id)
        .values(auto_reply_enabled_at=None)
    )
    db.commit()
    return {"status": "disabled"}

@router.get("/auto-reply/locations", status_code=status.HTTP_200_OK)
def list_auto_reply_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Per-location auto-reply state + how much it actually did in the last 30 days."""
    org_id = current_user.organization_id
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    counts = dict(
        db.query(ActivityLog.location_id, func.count(ActivityLog.id))
        .filter(
            ActivityLog.organization_id == org_id,
            ActivityLog.action == "review_auto_replied",
            ActivityLog.created_at >= cutoff,
        ).group_by(ActivityLog.location_id).all()
    )
    last_run = dict(
        db.query(ActivityLog.location_id, func.max(ActivityLog.created_at))
        .filter(
            ActivityLog.organization_id == org_id,
            ActivityLog.action == "review_auto_reply_run",
        ).group_by(ActivityLog.location_id).all()
    )
    # What the automation would actually have to work on. Without this, "0 replies"
    # is ambiguous between broken and nothing-to-do — the case that had us auditing.
    from app.services.review_auto_reply_service import (
        MIN_AI_AUTO_REPLY_RATING, MIN_AUTO_REPLY_RATING, MAX_AUTO_REPLY_ATTEMPTS,
    )
    org = db.query(Organization).filter(Organization.id == org_id).first()
    min_rating = MIN_AI_AUTO_REPLY_RATING if (org and org.auto_reply_mode == "ai") else MIN_AUTO_REPLY_RATING
    waiting = dict(
        db.query(Review.location_id, func.count(Review.id))
        .filter(
            Review.organization_id == org_id,
            Review.is_deleted == False,  # noqa: E712
            Review.is_replied == False,  # noqa: E712
            Review.rating >= min_rating,
            Review.auto_reply_attempts < MAX_AUTO_REPLY_ATTEMPTS,
        ).group_by(Review.location_id).all()
    )

    q = db.query(Location).filter(
        Location.organization_id == org_id,
        Location.billing_status == "active",
    )
    allowed = get_user_location_ids(current_user, db)   # None = org-wide role
    if allowed is not None:
        q = q.filter(Location.id.in_(allowed))
    locations = q.order_by(Location.location_name).all()
    return [
        {
            "id": loc.id,
            "location_name": loc.location_name,
            "city": loc.city,
            "enabled": loc.auto_reply_enabled,
            "replies_30d": counts.get(loc.id, 0),
            "waiting": waiting.get(loc.id, 0),
            "last_run_at": last_run.get(loc.id),
        }
        for loc in locations
    ]


@router.post("/auto-reply/locations/{location_id}", status_code=status.HTTP_200_OK)
def set_location_auto_reply(
    enabled: bool,
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Include/exclude one location from the org's auto-reply automation.

    location comes from require_location_access, which enforces BOTH the org boundary
    and the caller's location scope — the codebase convention for any route carrying a
    location_id. A hand-rolled org filter here would pass today (admin-only) and become
    an authz hole the moment this page opens to a location-restricted role.
    """
    db.execute(
        update(Location)
        .where(Location.id == location.id)
        .values(auto_reply_enabled=enabled)
    )
    db.commit()
    return {"id": location.id, "enabled": enabled}


@router.get("/auto-reply/logs", status_code=status.HTTP_200_OK)
def get_auto_reply_logs(
    location_id: int | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Recent auto-reply activity — one row per run, plus each posted reply.

    This is the 'is the automation actually running' view: runs that replied,
    failed, skipped for human review, or stopped for want of credits.
    """
    q = db.query(ActivityLog).filter(
        ActivityLog.organization_id == current_user.organization_id,
        ActivityLog.action.in_(["review_auto_reply_run", "review_auto_replied"]),
    )
    if location_id is not None:
        q = q.filter(ActivityLog.location_id == location_id)
    allowed = get_user_location_ids(current_user, db)   # None = org-wide role
    if allowed is not None:
        q = q.filter(ActivityLog.location_id.in_(allowed))
    rows = q.order_by(ActivityLog.created_at.desc()).limit(min(limit, 200)).all()

    names = dict(
        db.query(Location.id, Location.location_name)
        .filter(Location.organization_id == current_user.organization_id).all()
    )
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "action": r.action,
            "location_id": r.location_id,
            "location_name": names.get(r.location_id),
            "review_id": r.entity_id if r.action == "review_auto_replied" else None,
            "payload": r.payload or {},
        }
        for r in rows
    ]


@router.get("/analytics", status_code=status.HTTP_200_OK)
def get_template_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Per-template last-used dates + a recent auto-reply activity count.

    `usage_count` (total uses) already lives on each template; this adds the
    two things the customer asks about: 'when was this last used' and 'is
    auto-reply actually doing anything'.
    """
    org_id = current_user.organization_id

    rows = db.query(
        Review.reply_template_id, func.max(Review.reply_created_at)
    ).filter(
        Review.organization_id == org_id,
        Review.reply_template_id.isnot(None),
    ).group_by(Review.reply_template_id).all()
    last_used = {str(tid): ts.isoformat() for tid, ts in rows if tid is not None and ts is not None}

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    auto_replies_30d = db.query(func.count(ActivityLog.id)).filter(
        ActivityLog.organization_id == org_id,
        ActivityLog.action == "review_auto_replied",
        ActivityLog.created_at >= cutoff,
    ).scalar() or 0

    return {"last_used": last_used, "auto_replies_30d": auto_replies_30d}

@router.post("/", response_model=ReplyTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    data: ReplyTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Create a new reply template."""
    try:
        return ReplyTemplateService.create_template(
            db, 
            organization_id=current_user.organization_id, 
            user_id=current_user.id, 
            data=data
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to create template: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.put("/{template_id}", response_model=ReplyTemplateResponse)
def update_template(
    template_id: int,
    data: ReplyTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Update an existing reply template."""
    try:
        return ReplyTemplateService.update_template(
            db, 
            organization_id=current_user.organization_id, 
            template_id=template_id, 
            data=data
        )
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to update template: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.delete("/{template_id}", status_code=status.HTTP_200_OK)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Delete a reply template. May turn auto-reply off if coverage drops below the minimum."""
    try:
        auto_reply_disabled = ReplyTemplateService.delete_template(db, current_user.organization_id, template_id)
        return {"auto_reply_disabled": auto_reply_disabled}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete template: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")
