import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.invite import Invite
from app.models.user import User
from app.models.organization import Organization

class InviteService:
    @staticmethod
    def create_invite(
        db: Session,
        email: str,
        role: str,
        invited_by: User
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
            Invite.status == "pending"
        ).first()

        if existing_invite:
            # Check if it has expired; if so, update status to expired and proceed, else raise error
            if existing_invite.expires_at.replace(tzinfo=None) < datetime.utcnow():
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
    def get_valid_invite_by_token(db: Session, token: str) -> Optional[Invite]:
        invite = db.query(Invite).filter(Invite.token == token).first()
        if not invite:
            return None

        # Check status
        if invite.status != "pending":
            return None

        # Check expiry
        if invite.expires_at.replace(tzinfo=None) < datetime.utcnow():
            invite.status = "expired"
            db.commit()
            return None

        return invite

    @staticmethod
    def accept_invite(db: Session, invite: Invite) -> None:
        invite.status = "accepted"
        db.commit()

invite_service = InviteService()
