from typing import List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update, func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import get_current_user, admin_required
from app.models.user import User
from app.models.organization import Organization
from app.models.review import Review
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
    }

@router.post("/auto-reply/enable", status_code=status.HTTP_200_OK)
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
