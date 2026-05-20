from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import get_current_user, admin_required
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.models.sync_log import SyncLog
from app.schemas.schemas import UserOut
from app.schemas.invite import InviteCreate, InviteURLResponse, InviteVerificationOut
from app.services.invite_service import invite_service
from app.core.config import settings

router = APIRouter()

@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """Retrieve currently authenticated Google user profile details."""
    return current_user

@router.get("/me/token-status")
def get_token_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check active Google OAuth connection status.
    Determines if credentials are valid, expired, or require re-auth alerts.
    """
    oauth_account = db.query(OAuthAccount).filter(OAuthAccount.user_id == current_user.id).first()
    
    if not oauth_account:
        return {"status": "disconnected", "message": "No Google Account connected"}
        
    now = datetime.utcnow()
    token_expiry = oauth_account.expires_at.replace(tzinfo=None) if oauth_account.expires_at else None
    
    if not token_expiry or token_expiry <= now:
        # Check if we have a refresh token to perform automatic sync recovery
        if oauth_account.refresh_token:
            return {
                "status": "requires_refresh",
                "message": "Access token expired. Ready to auto-refresh.",
                "google_email": current_user.email
            }
        else:
            return {
                "status": "expired",
                "message": "Google authentication expired. Please reconnect.",
                "google_email": current_user.email
            }
            
    time_remaining = token_expiry - now
    return {
        "status": "active",
        "expires_in_seconds": int(time_remaining.total_seconds()),
        "google_email": current_user.email
    }

@router.get("/", response_model=List[UserOut])
def get_organization_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Retrieve all workspace users (Admin only)."""
    users = db.query(User).filter(User.organization_id == current_user.organization_id).all()
    return users

@router.post("/disconnect-google")
def disconnect_google(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Disconnect organization Google Business Profile integration."""
    # Delete the OAuthAccount record for this user
    oauth_account = db.query(OAuthAccount).filter(OAuthAccount.user_id == current_user.id).first()
    if oauth_account:
        db.delete(oauth_account)
        
    # Log disconnection
    log = SyncLog(
        organization_id=current_user.organization_id,
        status="Success",
        run_type="Manual",
        error_message=f"Disconnected Google Business Profile Account: {current_user.email}"
    )
    db.add(log)
    db.commit()
    
    return {"message": "Successfully disconnected Google Account"}

@router.post("/invite", response_model=InviteURLResponse)
def invite_user(
    invite_in: InviteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """
    Invite a new team member to join the active organization (Admin only).
    Generates a secure link for registration.
    """
    invite = invite_service.create_invite(
        db=db,
        email=invite_in.email,
        role=invite_in.role,
        invited_by=current_user
    )
    
    # Construct the invite landing URL
    invite_url = f"{settings.FRONTEND_URL}/invite/{invite.token}"
    return {"invite_url": invite_url}

@router.get("/invite/{token}", response_model=InviteVerificationOut)
def verify_invite_token(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Verify an invitation token (Public endpoint).
    Returns non-sensitive metadata for display on landing page.
    """
    invite = invite_service.get_valid_invite_by_token(db=db, token=token)
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The invitation link is invalid, expired, or has already been accepted."
        )
    
    return {
        "email": invite.email,
        "role": invite.role,
        "organization_name": invite.organization.name
    }
