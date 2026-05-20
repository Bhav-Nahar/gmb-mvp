import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.config import settings
from app.core.security import (
    create_access_token,
    encrypt_token
)
from app.models.user import User
from app.models.organization import Organization
from app.models.oauth_account import OAuthAccount
from app.models.sync_log import SyncLog
from app.core.gbp_client import GBPClient
from app.worker import celery

router = APIRouter()

@router.get("/google/login")
def google_login():
    """
    Initiate Google-first OAuth login.
    Generates a secure random state for CSRF protection and returns the redirect URL.
    """
    state = secrets.token_urlsafe(32)
    oauth_url = GBPClient.get_oauth_url(state=state)
    return {"url": oauth_url}

@router.get("/google/callback")
def google_callback(code: str, state: str, db: Session = Depends(get_db)):
    """
    Google OAuth Callback.
    1. Exchanges auth code for credentials.
    2. Fetches Google User Profile.
    3. Auto-creates Workspace (Organization), User, and OAuthAccount on first login.
    4. Auto-triggers Celery task to synchronize locations.
    5. Generates local JWT and redirects to frontend success hook.
    """
    try:
        # 1. Exchange authorization code for tokens
        token_data = GBPClient.exchange_code_for_tokens(code)
        
        # Determine the user info using mock or real client
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        email = token_data["email"]

        # 2. Fetch User Profile from Google info or mock
        google_id = "mock_google_id_999888777"
        name = "Google User"
        avatar = None

        if "mock_access_token" not in access_token:
            # Real Google User Info call
            import httpx
            user_info_url = "https://www.googleapis.com/oauth2/v3/userinfo"
            headers = {"Authorization": f"Bearer {access_token}"}
            user_response = httpx.get(user_info_url, headers=headers)
            if user_response.status_code == 200:
                profile = user_response.json()
                google_id = profile.get("sub")
                name = profile.get("name", "Google User")
                avatar = profile.get("picture")
                email = profile.get("email", email)
        else:
            # Formulate friendly mock profile details based on email prefix
            name = email.split("@")[0].title().replace("-", " ")
            google_id = f"google_id_{email.split('@')[0]}"

        # 3. Check if user already exists in our system
        user = db.query(User).filter(User.google_id == google_id).first()
        is_new_user = False

        if not user:
            # Check if there is a pending, non-expired invite for this email (case-insensitive)
            from app.models.invite import Invite
            invite = db.query(Invite).filter(
                Invite.email == email.strip().lower(),
                Invite.status == "pending",
                Invite.expires_at > datetime.utcnow()
            ).first()

            if invite:
                # User has a valid invite: join the existing organization with correct role
                user = User(
                    email=email,
                    name=name,
                    avatar=avatar,
                    google_id=google_id,
                    role=invite.role,
                    organization_id=invite.organization_id
                )
                db.add(user)
                db.commit()
                db.refresh(user)

                # Mark invite as accepted
                invite.status = "accepted"
                db.commit()

                # Create OAuth Account record
                oauth_account = OAuthAccount(
                    user_id=user.id,
                    provider="google",
                    provider_account_id=google_id,
                    access_token=encrypt_token(access_token),
                    refresh_token=encrypt_token(refresh_token) if refresh_token else None,
                    expires_at=datetime.utcnow() + timedelta(seconds=expires_in)
                )
                db.add(oauth_account)
                db.commit()
                
                # Log connection
                log = SyncLog(
                    organization_id=invite.organization_id,
                    status="Success",
                    run_type="Manual",
                    error_message=f"Invited user joined workspace and logged in via Google: {email}"
                )
                db.add(log)
                db.commit()
            else:
                is_new_user = True
                # Create a brand new workspace Organization
                org = Organization(name=f"{name}'s Workspace")
                db.add(org)
                db.commit()
                db.refresh(org)

                # Auto-create User record
                user = User(
                    email=email,
                    name=name,
                    avatar=avatar,
                    google_id=google_id,
                    role="Admin",  # First owner is Admin
                    organization_id=org.id
                )
                db.add(user)
                db.commit()
                db.refresh(user)

                # Create OAuth Account record
                oauth_account = OAuthAccount(
                    user_id=user.id,
                    provider="google",
                    provider_account_id=google_id,
                    access_token=encrypt_token(access_token),
                    refresh_token=encrypt_token(refresh_token) if refresh_token else None,
                    expires_at=datetime.utcnow() + timedelta(seconds=expires_in)
                )
                db.add(oauth_account)
                db.commit()
                
                # Log connection
                log = SyncLog(
                    organization_id=org.id,
                    status="Success",
                    run_type="Manual",
                    error_message=f"Created workspace and logged in via Google Account: {email}"
                )
                db.add(log)
                db.commit()
        else:
            # Existing user - Update profile details
            user.name = name
            user.avatar = avatar
            user.email = email
            
            # Check or update OAuth Account record
            oauth_account = db.query(OAuthAccount).filter(OAuthAccount.user_id == user.id).first()
            if not oauth_account:
                oauth_account = OAuthAccount(
                    user_id=user.id,
                    provider="google",
                    provider_account_id=google_id,
                    access_token=encrypt_token(access_token),
                    refresh_token=encrypt_token(refresh_token) if refresh_token else None,
                    expires_at=datetime.utcnow() + timedelta(seconds=expires_in)
                )
                db.add(oauth_account)
            else:
                oauth_account.access_token = encrypt_token(access_token)
                if refresh_token:
                    oauth_account.refresh_token = encrypt_token(refresh_token)
                oauth_account.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            db.commit()

            # Log login
            log = SyncLog(
                organization_id=user.organization_id,
                status="Success",
                run_type="Manual",
                error_message=f"Logged in via Google Account: {email}"
            )
            db.add(log)
            db.commit()

        # 4. Trigger Celery Task to sync locations immediately!
        celery.send_task("app.tasks.sync_locations_task", args=[user.organization_id, user.id, "Manual"])

        # 5. Generate local JWT access token
        local_token = create_access_token(subject=user.email)
        
        # Redirect to frontend success page that will save credentials
        redirect_url = f"{settings.FRONTEND_URL}/login/success?token={local_token}&onboarding={'true' if is_new_user else 'false'}"
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        db.rollback()
        # Redirect back to login page with error
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=google_auth_failed&detail={str(e)}")
