from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.location import Location

def validate_location_access(db: Session, user: User, location_ids: list[int]) -> list[int]:
    """
    Validates that:
    1. The locations exist and belong to the active user's organization.
    2. If the user has restricted access (e.g. Regional/Store Manager), they possess access to these locations.
    """
    if not location_ids:
        return []
        
    # Verify organization boundaries (Anti-IDOR)
    valid_locations = db.query(Location.id).filter(
        Location.organization_id == user.organization_id,
        Location.id.in_(location_ids)
    ).all()
    valid_location_ids = {loc[0] for loc in valid_locations}
    
    if len(valid_location_ids) != len(set(location_ids)):
        raise HTTPException(status_code=403, detail="One or more locations do not belong to your organization.")

    # Verify role-based boundaries
    if user.role not in ["Owner", "Admin"]:
        from app.api.deps import get_user_location_ids
        allowed_locs = get_user_location_ids(user, db) or []
        if any(loc_id not in allowed_locs for loc_id in location_ids):
            raise HTTPException(status_code=403, detail="You do not have access to one or more of these locations.")
            
    return location_ids

def assert_location_active(db: Session, location_id: int) -> None:
    """Guard paid features against locations that are locked pending payment.

    A location in 'pending_payment' state is visible but excluded from all paid
    processing (AI replies, posts, listing edits, etc.) until a prorated mid-cycle
    charge unlocks it. Raises 402 so the frontend can prompt the unlock flow.

    Assumes org-boundary/RBAC checks have already run for `location_id`.
    """
    billing_status = db.query(Location.billing_status).filter(Location.id == location_id).scalar()
    if billing_status is not None and billing_status != "active":
        raise HTTPException(
            status_code=402,
            detail="location_locked: this location is pending payment. Unlock it to use this feature.",
        )


def assert_locations_active(db: Session, location_ids: list[int]) -> None:
    """Bulk variant of assert_location_active for multi-location actions (campaigns,
    batch publish). Raises 402 if ANY target location is locked pending payment."""
    if not location_ids:
        return
    locked = db.query(Location.id).filter(
        Location.id.in_(location_ids),
        Location.billing_status != "active",
    ).first()
    if locked is not None:
        raise HTTPException(
            status_code=402,
            detail="location_locked: one or more locations are pending payment. Unlock them to use this feature.",
        )


def validate_user_access(db: Session, current_user: User, target_user_id: int) -> User:
    """
    Validates that the target user exists and belongs to the same organization.
    Ensures Owners cannot be mutated by Admins, etc.
    """
    target = db.query(User).filter(User.id == target_user_id, User.organization_id == current_user.organization_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
        
    if current_user.role == "Admin" and target.role == "Owner":
        raise HTTPException(status_code=403, detail="Admins cannot mutate the organization owner.")
        
    if current_user.role == "Regional Manager":
        if target.role != "Store Manager":
            raise HTTPException(status_code=403, detail="Regional Managers can only mutate Store Managers.")
        # Ensure target's locations are a subset of RM's locations
        from app.api.deps import get_user_location_ids
        rm_locs = get_user_location_ids(current_user, db) or []
        target_locs = get_user_location_ids(target, db) or []
        if any(loc not in rm_locs for loc in target_locs):
            raise HTTPException(status_code=403, detail="You do not have access to manage this user.")
            
    return target

def validate_org_resource(current_user: User, resource_org_id: int):
    """Checks that a generic model resource org ID matches the user's active tenant org ID."""
    if current_user.organization_id != resource_org_id:
        raise HTTPException(status_code=403, detail="Resource tenant boundary mismatch.")
