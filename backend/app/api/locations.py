from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import get_current_user, staff_required, admin_required, get_user_location_ids, verify_location_access
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.models.location import Location
from app.models.sync_log import SyncLog
from app.schemas.schemas import LocationOut, SyncLogOut
from app.schemas.location import LocationSyncStatus
from app.worker import celery

router = APIRouter()

@router.get("/", response_model=List[LocationOut])
def get_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch all synced Google Business Profile locations for the user's organization."""
    query = db.query(Location).filter(Location.organization_id == current_user.organization_id)
    
    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None:
        query = query.filter(Location.id.in_(allowed_location_ids))
        
    return query.all()

@router.get("/sync-logs", response_model=List[SyncLogOut])
def get_sync_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch the history of synchronization attempts for the organization."""
    query = db.query(SyncLog).filter(SyncLog.organization_id == current_user.organization_id)
    
    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None:
        query = query.filter(SyncLog.location_id.in_(allowed_location_ids))
        
    return query.order_by(SyncLog.created_at.desc()).limit(50).all()

@router.get("/{location_id}", response_model=LocationOut)
def get_location(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch a specific location by ID."""
    # Ensure they have access to this location
    verify_access = verify_location_access(location_id)
    # verify_location_access returns a dependency function, so we must call it manually here or use it in the path
    # Actually, verify_location_access is designed as a dependency. Let's do it in the path instead... wait, we can just call the closure since we have db and current_user? No, it requires a request.
    # We will do it the manual way since we need db and user, let's just check get_user_location_ids.
    
    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None and location_id not in allowed_location_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this location")
        
    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id
    ).first()
    
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
        
    return location

@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def trigger_sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """
    Manually trigger Google Business Profile location synchronization.
    Looks up the Admin user who has a connected OAuthAccount for this organization.
    Restricted to Owner/Admin.
    """
    admin_user = (
        db.query(User)
        .join(OAuthAccount, OAuthAccount.user_id == User.id)
        .filter(
            User.organization_id == current_user.organization_id,
            User.role.in_(["Owner", "Admin"]),
            User.is_active == True
        )
        .order_by(OAuthAccount.expires_at.desc(), User.id.asc())
        .first()
    )
    
    if not admin_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No connected Google Account found for this organization. Please reconnect via Google."
        )

    task = celery.send_task("app.tasks.sync_locations_task", args=[current_user.organization_id, admin_user.id, "Manual"])
    
    return {"message": "Sync task has been queued in the background.", "task_id": task.id}

@router.get("/{location_id}/sync-status", response_model=LocationSyncStatus)
def get_location_sync_status(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """
    Get the sync status of a specific location.
    Enforces that the location belongs to the user's organization.
    """
    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None and location_id not in allowed_location_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this location")

    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id
    ).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    latest_log = db.query(SyncLog).filter(
        SyncLog.location_id == location_id,
        SyncLog.organization_id == current_user.organization_id
    ).order_by(SyncLog.created_at.desc()).first()

    if not latest_log:
        return LocationSyncStatus(
            location_id=location_id,
            status="Pending",
            last_synced_at=None,
            error_message=None,
            run_type="Manual"
        )

    last_synced_at = None
    if latest_log.status == "Success":
        last_synced_at = latest_log.created_at
    else:
        last_success_log = db.query(SyncLog).filter(
            SyncLog.location_id == location_id,
            SyncLog.status == "Success"
        ).order_by(SyncLog.created_at.desc()).first()
        if last_success_log:
            last_synced_at = last_success_log.created_at

    return LocationSyncStatus(
        location_id=location_id,
        status=latest_log.status,
        last_synced_at=last_synced_at,
        error_message=latest_log.error_message,
        run_type=latest_log.run_type
    )
