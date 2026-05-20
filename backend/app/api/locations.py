from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import get_current_user, staff_required
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.models.location import Location
from app.models.sync_log import SyncLog
from app.schemas.schemas import LocationOut, SyncLogOut
from app.worker import celery

router = APIRouter()

@router.get("/", response_model=List[LocationOut])
def get_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch all synced Google Business Profile locations for the user's organization."""
    locations = db.query(Location).filter(
        Location.organization_id == current_user.organization_id
    ).all()
    return locations

@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def trigger_sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """
    Manually trigger Google Business Profile location synchronization.
    Looks up the Admin user who has a connected OAuthAccount for this organization.
    """
    # Find any Admin user in the org who has an active OAuthAccount
    admin_user = (
        db.query(User)
        .join(OAuthAccount, OAuthAccount.user_id == User.id)
        .filter(User.organization_id == current_user.organization_id)
        .first()
    )
    
    if not admin_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No connected Google Account found for this organization. Please reconnect via Google."
        )

    # Use the explicit celery instance
    task = celery.send_task("app.tasks.sync_locations_task", args=[current_user.organization_id, admin_user.id, "Manual"])
    
    return {"message": "Sync task has been queued in the background.", "task_id": task.id}

@router.get("/sync-logs", response_model=List[SyncLogOut])
def get_sync_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch the history of synchronization attempts for the organization."""
    logs = db.query(SyncLog).filter(
        SyncLog.organization_id == current_user.organization_id
    ).order_by(SyncLog.created_at.desc()).limit(50).all()
    return logs
