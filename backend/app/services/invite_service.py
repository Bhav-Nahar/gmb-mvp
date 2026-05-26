import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from app.models.invite import Invite
from app.models.user import User
from app.models.organization import Organization

class InviteService:
    @staticmethod
    def create_invite(
        db: Session,
        email: str,
        role: str,
        invited_by: User,
        location_ids: Optional[list[int]] = None,
        viewer_scope: Optional[str] = "assigned"
    ) -> Invite:
        # Normalize email
        email = email.strip().lower()
        
        # 1. Prevent inviting existing users (since email is globally unique in users table)
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            if existing_user.organization_id == invited_by.organization_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User with this email is already a member of your organization."
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User with this email is already registered in another organization."
                )

        # 2. Prevent duplicate pending invites in the organization
        existing_invite = db.query(Invite).filter(
            Invite.email == email,
            Invite.organization_id == invited_by.organization_id,
            Invite.status.in_(["pending", "in_progress"])
        ).first()

        if existing_invite:
            # Check if it has expired; if so, update status to expired and proceed, else raise error
            expires_at_utc = existing_invite.expires_at
            if expires_at_utc.tzinfo is None:
                expires_at_utc = expires_at_utc.replace(tzinfo=timezone.utc)
                
            if expires_at_utc < datetime.now(timezone.utc):
                existing_invite.status = "expired"
                db.commit()
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A pending invitation already exists for this email address."
                )

        # 3. Generate secure token & set expiry (7 days)
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=7)

        # 4. Create and persist invite record
        invite = Invite(
            email=email,
            organization_id=invited_by.organization_id,
            role=role,
            location_ids=location_ids,
            viewer_scope=viewer_scope,
            token=token,
            expires_at=expires_at,
            invited_by_user_id=invited_by.id,
            status="pending"
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)
        return invite

    @staticmethod
    def list_organization_invites(db: Session, organization_id: int) -> list[Invite]:
        invites = db.query(Invite).filter(Invite.organization_id == organization_id).order_by(Invite.created_at.desc()).all()
        now = datetime.now(timezone.utc)
        updated = False
        
        for invite in invites:
            if invite.status in ["pending", "in_progress"]:
                expires_at_utc = invite.expires_at
                if expires_at_utc.tzinfo is None:
                    expires_at_utc = expires_at_utc.replace(tzinfo=timezone.utc)
                if expires_at_utc < now:
                    invite.status = "expired"
                    updated = True
                    
        if updated:
            db.commit()
            
        return invites

    @staticmethod
    def revoke_invite(db: Session, invite_id: int, organization_id: int) -> Invite:
        invite = db.query(Invite).filter(
            Invite.id == invite_id,
            Invite.organization_id == organization_id
        ).first()
        
        if not invite:
            raise HTTPException(status_code=404, detail="Invitation not found.")
            
        if invite.status == "accepted":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot revoke an already accepted invitation."
            )
            
        invite.status = "revoked"
        db.commit()
        db.refresh(invite)
        return invite

    @staticmethod
    def resend_invite(db: Session, invite_id: int, organization_id: int, current_user: User) -> Invite:
        invite = db.query(Invite).filter(
            Invite.id == invite_id,
            Invite.organization_id == organization_id
        ).first()
        
        if not invite:
            raise HTTPException(status_code=404, detail="Invitation not found.")
            
        if invite.status == "accepted":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invitation has already been accepted."
            )
            
        # Check if user is already registered
        existing_user = db.query(User).filter(User.email == invite.email).first()
        if existing_user:
            if existing_user.organization_id == organization_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User with this email is already a member of your organization."
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User with this email is already registered in another organization."
                )
                
        # Check if another active invite exists for the same email
        another_active = db.query(Invite).filter(
            Invite.email == invite.email,
            Invite.organization_id == organization_id,
            Invite.status.in_(["pending", "in_progress"]),
            Invite.id != invite.id
        ).first()
        
        if another_active:
            expires_at_utc = another_active.expires_at
            if expires_at_utc.tzinfo is None:
                expires_at_utc = expires_at_utc.replace(tzinfo=timezone.utc)
            if expires_at_utc < datetime.now(timezone.utc):
                another_active.status = "expired"
                db.commit()
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A pending invitation already exists for this email address."
                )
                
        invite.token = secrets.token_urlsafe(32)
        invite.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        invite.status = "pending"
        invite.invited_by_user_id = current_user.id
        db.commit()
        db.refresh(invite)
        return invite

    @staticmethod
    def get_valid_invite_by_token(db: Session, token: str) -> Optional[Invite]:
        invite = db.query(Invite).options(joinedload(Invite.organization)).filter(Invite.token == token).first()
        if not invite:
            return None

        # Check status
        if invite.status not in ["pending", "in_progress"]:
            return None

        # Check expiry
        expires_at_utc = invite.expires_at
        if expires_at_utc.tzinfo is None:
            expires_at_utc = expires_at_utc.replace(tzinfo=timezone.utc)
            
        if expires_at_utc < datetime.now(timezone.utc):
            invite.status = "expired"
            db.commit()
            return None

        # Update tracking fields
        invite.last_opened_at = datetime.now(timezone.utc)
        if invite.status == "pending":
            invite.status = "in_progress"
        db.commit()
        db.refresh(invite)

        return invite

    @staticmethod
    def accept_invite(db: Session, invite: Invite) -> None:
        invite.status = "accepted"
        db.commit()

invite_service = InviteService()
