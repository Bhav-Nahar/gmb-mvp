from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone, timedelta

from app.api.deps import get_db, get_current_user, admin_required, staff_required, require_location_access
from app.core.roles import Role
from app.core.authorization import assert_location_access
from app.models.user import User
from app.models.location_edit import LocationEdit
from app.models.activity_log import ActivityLog
from app.schemas.listing_edits import (
    LocationEditCreate,
    LocationEditResponse,
    LocationEditSubmitRequest,
    LocationEditApproveRequest,
    LocationEditRejectRequest,
    ActivityLogResponse,
)
from app.services.listing_edit_service import ListingEditService
from app.core.listing_fields import LISTING_FIELDS, FIELD_MAP
from app.core.exceptions import PermissionDeniedError, ConflictError, NotFoundError
from app.core.config import settings
import app.tasks as tasks

router = APIRouter(tags=["listing-edits"])

@router.get("/fields")
def get_field_config(current_user: User = Depends(get_current_user)):
    """Returns the full field permission matrix for the frontend."""
    return [
        {
            "name": f.name,
            "label": f.label,
            "is_staff_editable": f.is_staff_editable,
            "is_admin_editable": f.is_admin_editable,
            "is_critical": f.is_critical,
            "is_read_only": f.is_read_only,
            "warning_title": f.warning_title,
            "warning_body": f.warning_body,
            # The frontend FieldRenderer picks its view/editor from these. Without
            # them it fell back to a hardcoded name->component map, and any field
            # not in that map silently degraded to a raw-JSON textarea (where a
            # user could submit malformed data). Send the backend's real intent.
            "field_type": f.field_type,
            "ui_component": f.ui_component,
            "supports_bulk_edit": f.supports_bulk_edit,
        }
        for f in LISTING_FIELDS
        if not f.is_read_only or current_user.role == Role.ADMIN
    ]

@router.post("/locations/{location_id}/edits", response_model=LocationEditResponse, status_code=201)
def create_edit(
    payload: LocationEditCreate,
    location_id: int = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Staff: creates a Draft. Admin: creates and auto-advances to Pending."""
    from app.core.authorization import assert_location_active
    assert_location_active(db, location_id)
    try:
        edit = ListingEditService.create_draft(
            db,
            organization_id=current_user.organization_id,
            location_id=location_id,
            actor_user_id=current_user.id,
            actor_role=current_user.role,
            field_name=payload.field_name,
            new_value=payload.new_value,
            warning_acknowledged=payload.warning_acknowledged,
        )
        db.commit()
        db.refresh(edit)
        return edit
    except (PermissionDeniedError, ConflictError, NotFoundError) as e:
        db.rollback()
        status_code = status.HTTP_409_CONFLICT if isinstance(e, ConflictError) else (
            status.HTTP_403_FORBIDDEN if isinstance(e, PermissionDeniedError) else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(status_code=status_code, detail=str(e))

@router.get("/locations/{location_id}/edits", response_model=list[LocationEditResponse])
def list_edits(
    location_id: int = Depends(require_location_access),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns edits for a location. Enforces stale Publishing recovery.
    """
    # ── Stale Publishing Recovery Rule ────────────────────────────────────────
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.EDIT_STALE_TIMEOUT_MINUTES)
    stale_edits = db.query(LocationEdit).filter(
        LocationEdit.location_id == location_id,
        LocationEdit.organization_id == current_user.organization_id,
        LocationEdit.status == "Publishing",
        LocationEdit.updated_at < stale_cutoff
    ).all()
    
    if stale_edits:
        for edit in stale_edits:
            ListingEditService.mark_failed(
                db,
                edit_id=edit.id,
                organization_id=current_user.organization_id,
                failure_reason="Publishing timeout: stale recovery triggered. The Celery worker likely crashed or network disconnected.",
                google_error_code="STALE_RECOVERY"
            )
        db.commit()

    # ── Regular Fetch ─────────────────────────────────────────────────────────
    query = db.query(LocationEdit).filter(
        LocationEdit.location_id == location_id,
        LocationEdit.organization_id == current_user.organization_id,
    )
    # Location scope is enforced by the require_location_access dependency.
    # Store Managers additionally only see edits they personally submitted.
    if current_user.role == Role.STORE_MANAGER:
        query = query.filter(LocationEdit.submitted_by_user_id == current_user.id)
    if status_filter:
        query = query.filter(LocationEdit.status == status_filter)
    return query.order_by(LocationEdit.created_at.desc()).all()

@router.post("/edits/{edit_id}/submit", response_model=LocationEditResponse)
def submit_draft(
    edit_id: int,
    body: LocationEditSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        # First, ensure the edit exists and user has access to its location
        edit_lookup = db.query(LocationEdit).filter(
            LocationEdit.id == edit_id,
            LocationEdit.organization_id == current_user.organization_id
        ).first()
        if not edit_lookup:
            raise HTTPException(status_code=404, detail="Edit not found.")
            
        # Resource-indirect endpoint (no location_id in the URL), so enforce scope
        # against the location this edit targets via the central helper.
        assert_location_access(db, current_user, edit_lookup.location_id)

        edit = ListingEditService.submit_draft(
            db,
            edit_id=edit_id,
            organization_id=current_user.organization_id,
            actor_user_id=current_user.id,
            expected_version=body.version,
        )
        db.commit()
        db.refresh(edit)
        return edit
    except (ConflictError, NotFoundError) as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT if isinstance(e, ConflictError) else status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@router.post("/edits/{edit_id}/approve", response_model=LocationEditResponse)
def approve_edit(
    edit_id: int,
    body: LocationEditApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    try:
        edit = ListingEditService.approve(
            db,
            edit_id=edit_id,
            organization_id=current_user.organization_id,
            actor_user_id=current_user.id,
            expected_version=body.version,
        )
        db.commit()
        db.refresh(edit)
        return edit
    except (ConflictError, NotFoundError) as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT if isinstance(e, ConflictError) else status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@router.post("/edits/{edit_id}/reject", response_model=LocationEditResponse)
def reject_edit(
    edit_id: int,
    body: LocationEditRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    try:
        edit = ListingEditService.reject(
            db,
            edit_id=edit_id,
            organization_id=current_user.organization_id,
            actor_user_id=current_user.id,
            expected_version=body.version,
            rejection_note=body.rejection_note,
        )
        db.commit()
        db.refresh(edit)
        return edit
    except (ConflictError, NotFoundError) as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT if isinstance(e, ConflictError) else status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@router.post("/edits/{edit_id}/publish", response_model=LocationEditResponse)
def publish_edit(
    edit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    try:
        edit = ListingEditService.mark_publishing(
            db,
            edit_id=edit_id,
            organization_id=current_user.organization_id,
        )
        from app.worker import celery as celery_app
        try:
            celery_app.send_task("app.tasks.publish_listing_edit_task", args=[edit_id, current_user.organization_id])
        except Exception as dispatch_err:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Task dispatch failed: {str(dispatch_err)}"
            )
        db.commit()
        db.refresh(edit)
        return edit
    except (ConflictError, NotFoundError) as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT if isinstance(e, ConflictError) else status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@router.get("/locations/{location_id}/activity", response_model=list[ActivityLogResponse])
def get_activity_log(
    location_id: int = Depends(require_location_access),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    entity_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Location scope is enforced by the require_location_access dependency.
    query = db.query(ActivityLog).filter(
        ActivityLog.location_id == location_id,
        ActivityLog.organization_id == current_user.organization_id,
    )
    if entity_type:
        query = query.filter(ActivityLog.entity_type == entity_type)
    return (
        query.order_by(ActivityLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
