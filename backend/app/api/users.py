from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import get_current_user, admin_required, RoleChecker, get_user_location_ids
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.models.sync_log import SyncLog
from app.models.location import Location
from app.models.user_location_access import UserLocationAccess
from app.models.audit_log import AuditLog
from app.schemas.schemas import UserOut, RoleUpdate, LocationsUpdate, TransferOwnershipRequest
from app.schemas.invite import InviteCreate, InviteURLResponse, InviteVerificationOut, InviteOut, InviteWithTokenOut
from app.models.invite import Invite
from app.services.invite_service import invite_service
from app.core.config import settings
from app.core.authorization import validate_location_access, validate_user_access, validate_org_resource

router = APIRouter()

team_viewer_required = RoleChecker(["Owner", "Admin", "Regional Manager"])
regional_manager_plus = RoleChecker(["Owner", "Admin", "Regional Manager"])

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
    oauth_account = (
        db.query(OAuthAccount)
        .join(User)
        .filter(
            User.organization_id == current_user.organization_id,
            User.role.in_(["Owner", "Admin"]),
            User.is_active == True,
            OAuthAccount.provider.in_(["gbp", "google"])
        )
        .order_by(OAuthAccount.expires_at.desc(), User.id.asc())
        .first()
    )
    
    if not oauth_account:
        return {"status": "disconnected", "message": "No Google Account connected"}
        
    now = datetime.now(timezone.utc)
    token_expiry = oauth_account.expires_at
    if token_expiry and token_expiry.tzinfo is None:
        token_expiry = token_expiry.replace(tzinfo=timezone.utc)
    
    if not token_expiry or token_expiry <= now:
        if oauth_account.refresh_token:
            return {
                "status": "requires_refresh",
                "message": "Access token expired. Ready to auto-refresh.",
                "google_email": oauth_account.user.email
            }
        else:
            return {
                "status": "expired",
                "message": "Google authentication expired. Please reconnect.",
                "google_email": oauth_account.user.email
            }
            
    time_remaining = token_expiry - now
    return {
        "status": "active",
        "expires_in_seconds": int(time_remaining.total_seconds()),
        "google_email": oauth_account.user.email
    }

@router.get("/", response_model=List[UserOut])
def get_organization_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(team_viewer_required)
):
    """Retrieve all workspace users."""
    users = db.query(User).filter(User.organization_id == current_user.organization_id).all()
    return users

@router.post("/disconnect-google")
def disconnect_google(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Disconnect organization Google Business Profile integration."""
    oauth_accounts = (
        db.query(OAuthAccount)
        .join(User)
        .filter(
            User.organization_id == current_user.organization_id,
            User.role.in_(["Owner", "Admin"]),
            OAuthAccount.provider.in_(["gbp", "google"])
        )
        .all()
    )
    for oa in oauth_accounts:
        db.delete(oa)
        
    # Invalidate active administrator sessions immediately upon GBP disconnect
    current_user.token_version += 1
    
    db.add(AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        action="google_disconnected",
        details=f"Disconnected Google Business Profile Account: {current_user.email}"
    ))
    
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
    current_user: User = Depends(regional_manager_plus)
):
    """
    Invite a new team member to join the active organization.
    """
    if current_user.role == "Regional Manager":
        if invite_in.role != "Store Manager":
            raise HTTPException(status_code=403, detail="Regional Managers can only invite Store Managers.")
        # Ensure assigned locations are within the Regional Manager's own scope
        rm_locs = get_user_location_ids(current_user, db)
        if not invite_in.location_ids or any(loc not in rm_locs for loc in invite_in.location_ids):
            raise HTTPException(status_code=403, detail="You can only assign locations you have access to.")

    if invite_in.role == "Store Manager" and (not invite_in.location_ids or len(invite_in.location_ids) != 1):
        raise HTTPException(status_code=400, detail="Store Manager must be assigned exactly one location.")

    if invite_in.role == "Regional Manager" and not invite_in.location_ids:
        raise HTTPException(status_code=400, detail="Regional Manager must be assigned at least one location.")

    # Enforce organization ownership and access controls (Anti-IDOR)
    if invite_in.location_ids:
        validate_location_access(db, current_user, invite_in.location_ids)

    invite = invite_service.create_invite(
        db=db,
        email=invite_in.email,
        role=invite_in.role,
        invited_by=current_user,
        location_ids=invite_in.location_ids,
        viewer_scope=invite_in.viewer_scope
    )
    
    db.add(AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        actor_user_id=current_user.id,
        target_user_id=None,
        action="user_invited",
        details=f"Invited user: {invite_in.email} with role {invite_in.role}"
    ))
    db.commit()
    
    invite_url = f"{settings.FRONTEND_URL}/invite/{invite.token}"
    return {"invite_url": invite_url}

@router.get("/invite/{token}", response_model=InviteVerificationOut)
def verify_invite_token(
    token: str,
    db: Session = Depends(get_db)
):
    """Verify an invitation token (Public endpoint)."""
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

def _check_regional_manager_invite_access(invite: Invite, current_user: User, db: Session):
    if current_user.role == "Regional Manager":
        if invite.role != "Store Manager":
            raise HTTPException(status_code=403, detail="Regional Managers can only manage invitations for Store Managers.")
        rm_locs = get_user_location_ids(current_user, db)
        if not invite.location_ids or any(loc not in rm_locs for loc in invite.location_ids):
            raise HTTPException(status_code=403, detail="You can only manage invitations for locations you have access to.")

@router.get("/invites", response_model=List[InviteOut])
def list_invites(
    db: Session = Depends(get_db),
    current_user: User = Depends(regional_manager_plus)
):
    """List pending/expired/revoked/accepted invites for the organization.
    Regional Managers only see Store Manager invites for their assigned locations."""
    all_invites = invite_service.list_organization_invites(db, current_user.organization_id)

    if current_user.role == "Regional Manager":
        rm_locs = set(get_user_location_ids(current_user, db) or [])
        return [
            inv for inv in all_invites
            if inv.role == "Store Manager"
            and inv.location_ids
            and any(loc in rm_locs for loc in inv.location_ids)
        ]

    return all_invites

@router.delete("/invites/{invite_id}")
def revoke_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(regional_manager_plus)
):
    """Revoke a pending invite."""
    invite = db.query(Invite).filter(Invite.id == invite_id, Invite.organization_id == current_user.organization_id).first()
    if invite:
        _check_regional_manager_invite_access(invite, current_user, db)
    invite_service.revoke_invite(db, invite_id, current_user.organization_id)
    return {"message": "Invite revoked successfully"}

@router.post("/invites/{invite_id}/resend", response_model=InviteWithTokenOut)
def resend_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(regional_manager_plus)
):
    """Resend/regenerate an invite."""
    invite = db.query(Invite).filter(Invite.id == invite_id, Invite.organization_id == current_user.organization_id).first()
    if invite:
        _check_regional_manager_invite_access(invite, current_user, db)
    return invite_service.resend_invite(db, invite_id, current_user.organization_id, current_user)

@router.put("/{user_id}/role")
def update_user_role(
    user_id: int,
    role_update: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    user = validate_user_access(db, current_user, user_id)
        
    if user.role == "Owner":
        raise HTTPException(status_code=403, detail="Cannot modify Owner role through this endpoint.")

    if role_update.role == "Owner":
        raise HTTPException(status_code=403, detail="Use ownership transfer to assign a new Owner.")

    user.role = role_update.role
    if role_update.role == "Viewer":
        user.viewer_scope = role_update.viewer_scope
    else:
        user.viewer_scope = "assigned"

    user.token_version += 1
    
    # Audit log
    db.add(AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        actor_user_id=current_user.id,
        target_user_id=user.id,
        action="role_change",
        details=f"Changed {user.email} role to {user.role}"
    ))
    
    db.commit()
    return {"message": "Role updated successfully"}

@router.put("/{user_id}/locations")
def update_user_locations(
    user_id: int,
    loc_update: LocationsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(regional_manager_plus)
):
    user = validate_user_access(db, current_user, user_id)
        
    if user.role in ["Owner", "Admin"]:
        raise HTTPException(status_code=400, detail="Cannot assign specific locations to Owner or Admin.")
        
    if current_user.role == "Regional Manager":
        if user.role != "Store Manager":
            raise HTTPException(status_code=403, detail="Regional Managers can only modify Store Managers.")
        rm_locs = get_user_location_ids(current_user, db)
        if any(loc not in rm_locs for loc in loc_update.location_ids):
            raise HTTPException(status_code=403, detail="You can only assign locations you have access to.")

    if user.role == "Store Manager" and len(loc_update.location_ids) != 1:
        raise HTTPException(status_code=400, detail="Store Manager must have exactly one location.")

    # Enforce organization ownership and access controls (Anti-IDOR)
    validate_location_access(db, current_user, loc_update.location_ids)

    # Atomic swap
    db.query(UserLocationAccess).filter(UserLocationAccess.user_id == user.id).delete()
    for loc_id in loc_update.location_ids:
        db.add(UserLocationAccess(user_id=user.id, location_id=loc_id))

    user.token_version += 1
    
    db.add(AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        actor_user_id=current_user.id,
        target_user_id=user.id,
        action="locations_reassigned",
        details=f"Updated location access for {user.email}: {loc_update.location_ids}"
    ))
    
    db.commit()
    return {"message": "Locations updated successfully"}

@router.post("/transfer-ownership")
def transfer_ownership(
    req: TransferOwnershipRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Owner"]))
):
    new_owner = db.query(User).filter(User.id == req.new_owner_id, User.organization_id == current_user.organization_id).first()
    if not new_owner:
        raise HTTPException(status_code=404, detail="User not found")
        
    if new_owner.id == current_user.id:
        raise HTTPException(status_code=400, detail="You are already the owner.")
        
    # Demote old owner
    current_user.role = "Admin"
    current_user.token_version += 1
    
    # Promote new owner
    new_owner.role = "Owner"
    new_owner.viewer_scope = "assigned"
    new_owner.token_version += 1
    
    db.add(AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        actor_user_id=current_user.id,
        target_user_id=new_owner.id,
        action="ownership_transfer",
        details=f"Transferred ownership from {current_user.email} to {new_owner.email}"
    ))
    
    db.commit()
    return {"message": "Ownership transferred successfully"}

@router.put("/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    user = validate_user_access(db, current_user, user_id)
        
    if user.role == "Owner":
        raise HTTPException(status_code=403, detail="Cannot deactivate the organization owner.")
        
    user.is_active = False
    user.token_version += 1
    
    db.add(AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        actor_user_id=current_user.id,
        target_user_id=user.id,
        action="user_deactivated",
        details=f"Deactivated user: {user.email}"
    ))
    db.commit()
    return {"message": "User deactivated"}

@router.put("/{user_id}/reactivate")
def reactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    user = validate_user_access(db, current_user, user_id)
        
    user.is_active = True
    user.token_version += 1
    
    db.add(AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        actor_user_id=current_user.id,
        target_user_id=user.id,
        action="user_reactivated",
        details=f"Reactivated user: {user.email}"
    ))
    db.commit()
    return {"message": "User reactivated"}

@router.delete("/me")
def delete_my_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Permanently delete the authenticated user's account and related records.
    If the user is the ONLY Owner in the organization, deletes the local organization and all its data.
    """
    is_owner = current_user.role == "Owner"
    
    owners_count = db.query(User).filter(
        User.organization_id == current_user.organization_id,
        User.role == "Owner"
    ).count()
    
    # Create audit log entry before deletion
    db.add(AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="account_deletion",
        details=f"User {current_user.email} (role: {current_user.role}) requested permanent account deletion."
    ))
    db.flush()
    
    if is_owner and owners_count == 1:
        # Delete entire organization
        organization = current_user.organization
        db.delete(organization)
    else:
        # Delete only user-specific records manually where cascade is missing or just to be safe
        db.query(UserLocationAccess).filter(UserLocationAccess.user_id == current_user.id).delete()
        db.query(Invite).filter(Invite.email == current_user.email).delete()
        # OAuthAccount cascades, but explicit is fine
        db.query(OAuthAccount).filter(OAuthAccount.user_id == current_user.id).delete()
        db.delete(current_user)
        
    db.commit()
    return {"message": "Account successfully deleted"}
