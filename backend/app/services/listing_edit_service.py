from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional, Any
from datetime import datetime, timezone

from app.models.location_edit import LocationEdit
from app.models.location import Location
from app.core.listing_fields import FIELD_MAP
from app.services.activity_log_service import ActivityLogService
from app.core.exceptions import PermissionDeniedError, ConflictError, NotFoundError
from app.core.roles import Role

# =============================================================================
# LOCK ACQUISITION ORDER — MUST BE FOLLOWED BY ALL METHODS IN THIS MODULE
# =============================================================================
# To prevent deadlocks, any method that needs to lock both Location and
# LocationEdit rows MUST always acquire the locks in this fixed order:
#
#   1. Location  (acquire first)
#   2. LocationEdit  (acquire second)
#
# Acquiring locks in any other order when two concurrent transactions each
# need both rows will produce a circular wait → deadlock.
# =============================================================================

# Valid state transitions. Key = current status, value = set of allowed next statuses.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "Draft":      {"Pending", "Rejected"},   # submit for approval, or admin discards
    "Pending":    {"Approved", "Rejected"},
    "Approved":   {"Publishing"},
    "Publishing": {"Published", "Failed"},
    # Terminal states — no transitions out, except Failed allowing retry
    "Published":  set(),
    "Failed":     {"Pending"}, # Allows admins to retry a transient failure
    "Rejected":   set(),
}

TERMINAL_STATUSES = {"Published", "Failed", "Rejected"}
ACTIVE_STATUSES = {"Draft", "Pending", "Approved", "Publishing"}

class ListingEditService:

    @staticmethod
    def assert_field_permission(field_name: str, actor_role: str) -> None:
        """Raises PermissionDeniedError if the actor cannot edit this field."""
        config = FIELD_MAP.get(field_name)
        if not config:
            raise NotFoundError(f"Unknown field: {field_name}")
        if config.is_read_only:
            raise PermissionDeniedError(f"'{config.label}' is read-only and cannot be edited.")
        is_admin_or_owner = actor_role in (Role.ADMIN, "admin", Role.OWNER, "owner")
        if not is_admin_or_owner and not config.is_staff_editable:
            raise PermissionDeniedError(
                f"Staff cannot edit '{config.label}'. Submit a request to your admin."
            )
        if is_admin_or_owner and not config.is_admin_editable:
            raise PermissionDeniedError(f"'{config.label}' cannot be edited.")

    @staticmethod
    def assert_no_active_edit(db: Session, location_id: int, field_name: str) -> None:
        """Raises ConflictError if there is already an active edit for this field."""
        existing = db.query(LocationEdit).filter(
            and_(
                LocationEdit.location_id == location_id,
                LocationEdit.field_name == field_name,
                LocationEdit.status.notin_(TERMINAL_STATUSES),
            )
        ).first()
        if existing:
            raise ConflictError(
                f"A '{field_name}' edit is already {existing.status.lower()}. "
                f"Resolve it before submitting a new one."
            )

    @staticmethod
    def create_draft(
        db: Session,
        *,
        organization_id: int,
        location_id: int,
        actor_user_id: int,
        actor_role: str,
        field_name: str,
        new_value: Any, # Accepts Any to support JSON payloads
        warning_acknowledged: bool = False,
    ) -> LocationEdit:
        ListingEditService.assert_field_permission(field_name, actor_role)
        config = FIELD_MAP[field_name]
        
        from app.services.validators import validate_field_value
        if not validate_field_value(config.field_type, new_value):
            raise ConflictError(f"Invalid value provided for '{config.label}'.")
        
        # Strict Backend Warning Enforcement
        if config.is_critical and not warning_acknowledged:
            raise ConflictError(
                f"Critical warning for '{config.label}' must be acknowledged before submitting this edit."
            )

        ListingEditService.assert_no_active_edit(db, location_id, field_name)

        # Snapshot the current value from the locations table
        location = db.query(Location).filter(
            Location.id == location_id,
            Location.organization_id == organization_id,
        ).first()
        if not location:
            raise NotFoundError("Location not found.")

        old_value = getattr(location, field_name, None)
        # Ensure it's JSONB serializable.
        if not isinstance(old_value, (dict, list, str, int, float, bool, type(None))):
             old_value = str(old_value)

        # Admins and Owners skip Draft → go straight to Pending (they can self-approve)
        is_admin_or_owner = actor_role in (Role.ADMIN, "admin", Role.OWNER, "owner")
        initial_status = "Pending" if is_admin_or_owner else "Draft"

        edit = LocationEdit(
            organization_id=organization_id,
            location_id=location_id,
            submitted_by_user_id=actor_user_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            status=initial_status,
            warning_acknowledged=warning_acknowledged,
            version=1
        )
        db.add(edit)
        db.flush()

        action = "draft_created" if initial_status == "Draft" else "submitted_for_approval"
        ActivityLogService.log(
            db,
            organization_id=organization_id,
            location_id=location_id,
            actor_user_id=actor_user_id,
            entity_type="listing_edit",
            entity_id=edit.id,
            action=action,
            payload={
                "field_name": field_name,
                "field_label": config.label,
                "old_value": old_value,
                "new_value": new_value,
                "is_critical": config.is_critical,
                "warning_acknowledged": warning_acknowledged,
            },
        )
        return edit

    @staticmethod
    def submit_draft(
        db: Session,
        *,
        edit_id: int,
        organization_id: int,
        actor_user_id: int,
        expected_version: int,
    ) -> LocationEdit:
        """Staff submits their Draft → Pending."""
        edit = ListingEditService._get_edit_locked(db, edit_id, organization_id)
        ListingEditService._check_version(edit, expected_version)
        ListingEditService._transition(edit, "Pending")
        ActivityLogService.log(
            db,
            organization_id=organization_id,
            location_id=edit.location_id,
            actor_user_id=actor_user_id,
            entity_type="listing_edit",
            entity_id=edit.id,
            action="submitted_for_approval",
            payload={"field_name": edit.field_name, "new_value": edit.new_value},
        )
        db.flush()
        return edit

    @staticmethod
    def approve(
        db: Session,
        *,
        edit_id: int,
        organization_id: int,
        actor_user_id: int,
        expected_version: int,
    ) -> LocationEdit:
        """Admin approves a Pending edit → Approved."""
        edit = ListingEditService._get_edit_locked(db, edit_id, organization_id)
        ListingEditService._check_version(edit, expected_version)
        ListingEditService._transition(edit, "Approved")
        edit.approved_by_user_id = actor_user_id
        ActivityLogService.log(
            db,
            organization_id=organization_id,
            location_id=edit.location_id,
            actor_user_id=actor_user_id,
            entity_type="listing_edit",
            entity_id=edit.id,
            action="approved",
            payload={"field_name": edit.field_name, "new_value": edit.new_value},
        )
        db.flush()
        return edit

    @staticmethod
    def reject(
        db: Session,
        *,
        edit_id: int,
        organization_id: int,
        actor_user_id: int,
        expected_version: int,
        rejection_note: Optional[str] = None,
    ) -> LocationEdit:
        """Admin rejects an edit → Rejected."""
        edit = ListingEditService._get_edit_locked(db, edit_id, organization_id)
        ListingEditService._check_version(edit, expected_version)
        ListingEditService._transition(edit, "Rejected")
        edit.rejection_note = rejection_note
        ActivityLogService.log(
            db,
            organization_id=organization_id,
            location_id=edit.location_id,
            actor_user_id=actor_user_id,
            entity_type="listing_edit",
            entity_id=edit.id,
            action="rejected",
            payload={"field_name": edit.field_name, "rejection_note": rejection_note},
        )
        db.flush()
        return edit

    @staticmethod
    def mark_publishing(db: Session, *, edit_id: int, organization_id: int) -> LocationEdit:
        """System transitions to Publishing before Celery dispatch."""
        edit = ListingEditService._get_edit_locked(db, edit_id, organization_id)
        # Note: No version check here as this is system-driven
        ListingEditService._transition(edit, "Publishing")
        db.flush()
        return edit

    @staticmethod
    def mark_published(
        db: Session,
        *,
        edit_id: int,
        organization_id: int,
    ) -> LocationEdit:
        """System marks Published on GBP success."""
        # Lock order: Location -> LocationEdit (must be consistent to prevent deadlocks)
        # We need the location_id before we can lock Location, so fetch the edit
        # without a lock first, then acquire both locks in the correct order.
        edit_row = db.query(LocationEdit).filter(
            LocationEdit.id == edit_id,
            LocationEdit.organization_id == organization_id,
        ).first()
        if not edit_row:
            raise NotFoundError("Edit not found.")
        location_id_for_lock = edit_row.location_id

        # Step 1: Lock Location first (correct lock order)
        location = db.query(Location).filter(
            Location.id == location_id_for_lock
        ).with_for_update().first()

        # Step 2: Lock LocationEdit second (correct lock order)
        edit = ListingEditService._get_edit_locked(db, edit_id, organization_id)

        ListingEditService._transition(edit, "Published")
        edit.published_at = datetime.now(timezone.utc)

        # location was already locked above in Step 1 (Lock order: Location -> LocationEdit).
        # Both mutations are staged here and committed together in a single transaction.
        if location:
            final_value = edit.new_value
            if edit.field_name == "primary_category":
                if isinstance(edit.new_value, dict):
                    final_value = edit.new_value.get("displayName")
                    resource_name = edit.new_value.get("name")
                    if resource_name:
                        location.google_category_resource_name = resource_name
                # Mark attributes stale when category changes
                location.google_attributes_stale = True
                
            setattr(location, edit.field_name, final_value)
            location.last_synced_at = datetime.now(timezone.utc)

        ActivityLogService.log(
            db,
            organization_id=organization_id,
            location_id=edit.location_id,
            actor_user_id=None,
            entity_type="listing_edit",
            entity_id=edit.id,
            action="published",
            payload={
                "field_name": edit.field_name,
                "new_value": edit.new_value,
                "gbp_field_mask": FIELD_MAP[edit.field_name].gbp_field_mask,
            },
        )
        db.flush()
        return edit

    @staticmethod
    def mark_failed(
        db: Session,
        *,
        edit_id: int,
        organization_id: int,
        failure_reason: str,
        google_error_code: Optional[str] = None,
    ) -> LocationEdit:
        """System marks Failed on GBP failure."""
        edit = ListingEditService._get_edit_locked(db, edit_id, organization_id)
        ListingEditService._transition(edit, "Failed")
        edit.failure_reason = failure_reason
        if google_error_code:
            edit.google_error_code = google_error_code
            
        ActivityLogService.log(
            db,
            organization_id=organization_id,
            location_id=edit.location_id,
            actor_user_id=None,
            entity_type="listing_edit",
            entity_id=edit.id,
            action="publish_failed",
            payload={
                "field_name": edit.field_name, 
                "failure_reason": failure_reason,
                "google_error_code": google_error_code
            },
        )
        db.flush()
        return edit

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _get_edit_locked(db: Session, edit_id: int, organization_id: int) -> LocationEdit:
        # Pessimistic Row Locking ensures no concurrent read/writes during transition.
        # Lock order: Location -> LocationEdit (must be consistent to prevent deadlocks).
        # Callers that also need to lock Location MUST acquire Location lock first,
        # then call this method to acquire the LocationEdit lock second.
        edit = db.query(LocationEdit).filter(
            LocationEdit.id == edit_id,
            LocationEdit.organization_id == organization_id,
        ).with_for_update().first()
        if not edit:
            raise NotFoundError("Edit not found.")
        return edit

    @staticmethod
    def _check_version(edit: LocationEdit, expected_version: int) -> None:
        """Optimistic Concurrency: ensures the record hasn't been mutated since fetch.

        IMPORTANT: This must always be called AFTER the row lock has been acquired
        via with_for_update() (i.e., after _get_edit_locked). Checking the version
        before acquiring the lock creates a TOCTOU race — another transaction could
        mutate the row between the version read and the lock acquisition.
        """
        if edit.version != expected_version:
            raise ConflictError(
                f"The edit has been modified by someone else. Please refresh and try again."
            )
            
    @staticmethod
    def _transition(edit: LocationEdit, new_status: str) -> None:
        current = edit.status
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        
        # Idempotency safety
        if current == new_status:
            return
            
        if new_status not in allowed:
            raise ConflictError(
                f"Cannot transition from '{current}' to '{new_status}'."
            )
        edit.status = new_status
        edit.version += 1  # Increment version on every successful state change
