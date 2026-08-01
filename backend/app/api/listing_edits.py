from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone, timedelta

from app.api.deps import get_db, get_current_user, admin_required, staff_required, require_location_access, get_user_location_ids
from app.core.roles import Role
from app.core.authorization import assert_location_access
from app.models.user import User
from app.models.location import Location
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
from sqlalchemy import false as sa_false
from sqlalchemy.orm.attributes import flag_modified
from app.models.organization import Organization
from app.core import plan_config
from app.services import google_update_resolver
from app.services.listing_edit_service import ListingEditService
from app.core.listing_fields import LISTING_FIELDS, FIELD_MAP, GBP_MASK_TO_FIELD
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
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Staff: creates a Draft. Admin: creates and auto-advances to Pending."""
    location_id = location.id
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
    location: Location = Depends(require_location_access),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns edits for a location. Enforces stale Publishing recovery.
    """
    location_id = location.id
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
        # Commit the Publishing state BEFORE dispatch, else the worker can read the
        # row while it's still Approved and skip ("Edit not in Publishing state").
        db.commit()
        db.refresh(edit)
        from app.worker import celery as celery_app
        try:
            celery_app.send_task("app.tasks.publish_listing_edit_task", args=[edit_id, current_user.organization_id])
        except Exception as dispatch_err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Task dispatch failed: {str(dispatch_err)}"
            )
        return edit
    except (ConflictError, NotFoundError) as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT if isinstance(e, ConflictError) else status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

CHANGES_RECENT_DAYS = 7


def _profile_changes_query(db: Session, user: User):
    """ProfileChange rows visible to `user`, joined to their location's name.

    Org scoping alone is not enough: staff and assigned-scope viewers may only see
    the locations they are assigned to, which every location-level route enforces via
    require_location_access. These org-wide routes have no location_id to hang that
    off, so the same restriction is applied here.
    """
    query = (
        db.query(ActivityLog, Location.location_name)
        .join(Location, Location.id == ActivityLog.location_id)
        .filter(
            ActivityLog.organization_id == user.organization_id,
            ActivityLog.entity_type == "ProfileChange",
        )
    )
    allowed = get_user_location_ids(user, db)  # None = unrestricted (admins/org-scope viewers)
    if allowed is not None:
        if not allowed:
            return query.filter(sa_false())
        query = query.filter(ActivityLog.location_id.in_(allowed))
    return query


@router.get("/profile-changes")
def list_profile_changes(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    source: Optional[str] = Query(None, description="google | attribute | profile"),
    location_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every detected change across the org's locations, newest first."""
    query = _profile_changes_query(db, current_user)
    if location_id:
        # Org scoping is already applied above, so this can't reach another tenant.
        query = query.filter(ActivityLog.location_id == location_id)
    if source == "profile":
        # Our own diff of the merchant's listing writes no `source` key.
        query = query.filter(ActivityLog.payload["source"].astext.is_(None))
    elif source:
        query = query.filter(ActivityLog.payload["source"].astext == source)

    rows = (
        # id breaks the tie: created_at is the transaction timestamp, so one sync writes
        # a whole block of rows with the same value. Ordering by it alone makes a page
        # boundary inside that block non-deterministic — rows repeat or go missing.
        query.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
        .offset(offset).limit(limit).all()
    )
    return [
        {
            "id": log.id,
            "location_id": log.location_id,
            "location_name": location_name,
            "action": log.action,
            "payload": log.payload,
            "created_at": log.created_at,
        }
        for log, location_name in rows
    ]


@router.get("/profile-changes/count")
def count_profile_changes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sidebar badge: changes in the last week. Decays on its own, so it never
    becomes a permanent number nobody can clear."""
    since = datetime.now(timezone.utc) - timedelta(days=CHANGES_RECENT_DAYS)
    count = (
        _profile_changes_query(db, current_user)
        .filter(ActivityLog.created_at >= since)
        .count()
    )
    return {"count": count, "days": CHANGES_RECENT_DAYS}


@router.post("/locations/{location_id}/google-updates/{activity_id}/{action}", response_model=LocationEditResponse)
def resolve_google_update(
    activity_id: int,
    action: str,
    acknowledge: bool = Query(False, description="Confirms the warning on a critical field"),
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accept or reject a change Google made to the live listing.

    Google has no accept/reject endpoint — both are just a locations.patch, and the
    only difference is which value you send (Google's, or your own). So this creates
    an ordinary LocationEdit and lets the existing approve/publish pipeline do the
    PATCH; nothing about publishing needed to be rebuilt.
    """
    if action not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'accept' or 'reject'")

    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org or not plan_config.plan_has_feature(org.plan_tier, plan_config.FEATURE_GOOGLE_UPDATES):
        raise HTTPException(
            status_code=403,
            detail="upgrade_required: Google Updates are available on the Basic and Pro plans.",
        )

    entry = db.query(ActivityLog).filter(
        ActivityLog.id == activity_id,
        ActivityLog.location_id == location.id,
        ActivityLog.organization_id == current_user.organization_id,
    ).first()
    payload = (entry.payload or {}) if entry else {}
    if not entry or payload.get("source") != "google":
        raise HTTPException(status_code=404, detail="Google update not found.")
    if payload.get("resolved"):
        raise HTTPException(status_code=409, detail=f"This update was already {payload['resolved']}.")

    field_name = GBP_MASK_TO_FIELD.get(payload.get("field"))
    if not field_name:
        raise HTTPException(status_code=400, detail=f"'{payload.get('field')}' is not an editable field.")

    # Google's shape and our stored shape both differ from what the edit pipeline
    # validates, per field — see google_update_resolver for why this is explicit.
    try:
        if action == "accept":
            new_value = google_update_resolver.from_google(payload["field"], payload.get("new"))
        else:
            # Rejecting re-asserts what we already have, pushing our value back over Google's.
            new_value = google_update_resolver.from_stored(field_name, location)
    except google_update_resolver.Unresolvable as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        edit = ListingEditService.create_draft(
            db,
            organization_id=current_user.organization_id,
            location_id=location.id,
            actor_user_id=current_user.id,
            actor_role=current_user.role,
            field_name=field_name,
            new_value=new_value,
            # Accepting adopts a value already live on the listing, so the critical-field
            # warning has nothing to add. Rejecting *changes* the live listing and can
            # trigger re-verification, so it still needs an explicit acknowledgement.
            warning_acknowledged=(action == "accept" or acknowledge),
        )
        entry.payload = {**payload, "resolved": f"{action}ed", "edit_id": edit.id}
        flag_modified(entry, "payload")
        db.commit()
        db.refresh(edit)
        return edit
    except (PermissionDeniedError, ConflictError, NotFoundError) as e:
        db.rollback()
        status_code = status.HTTP_409_CONFLICT if isinstance(e, ConflictError) else (
            status.HTTP_403_FORBIDDEN if isinstance(e, PermissionDeniedError) else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(status_code=status_code, detail=str(e))


@router.get("/locations/{location_id}/activity", response_model=list[ActivityLogResponse])
def get_activity_log(
    location: Location = Depends(require_location_access),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    entity_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    location_id = location.id
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
