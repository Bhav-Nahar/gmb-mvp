import secrets
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db.session import get_db
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token_payload,
    encrypt_token
)
from app.models.user import User
from app.core.roles import Role
from app.models.organization import Organization
from app.models.oauth_account import OAuthAccount
from app.models.sync_log import SyncLog
from app.models.audit_log import AuditLog
from app.models.organization_sync_state import OrganizationSyncState
from app.providers.factory import ProviderFactory
from app.core.redis_client import get_redis
from app.worker import celery

# Server-side OAuth CSRF state. The cookie-based approach failed for users whose
# browsers block third-party cookies (frontend and backend are on different
# domains), so the oauth_state cookie was never stored and every callback raised
# "Invalid CSRF state token". Storing the state in Redis keyed by the CSRF token
# removes any dependency on browser cookie behaviour.
OAUTH_STATE_TTL = 600  # 10 minutes — ample for an interactive consent screen


def _parse_oauth_state(state: str) -> tuple[str, str | None, bool]:
    """Split the OAuth `state` into (csrf_token, invite_token, consent_retried).

    Format: "<csrf>:<invite_token>[:c]". The optional trailing "c" marks a round that
    was already retried with prompt=consent, so that retry fires at most once and can
    never loop. Invite tokens are secrets.token_urlsafe, which never contains a colon.
    """
    parts = state.split(":", 2)
    return (
        parts[0],
        parts[1] if len(parts) > 1 and parts[1] else None,
        len(parts) > 2 and parts[2] == "c",
    )


def _oauth_state_key(csrf_token: str) -> str:
    return f"oauth_state:{csrf_token}"


def _cookie_domain() -> str | None:
    """Shared parent domain for auth cookies, or None for host-only cookies.

    Set COOKIE_DOMAIN (e.g. ".pinzo.io") when the frontend and API live on
    sibling subdomains so cookies are first-party to both and survive browsers
    that block third-party cookies.
    """
    return settings.COOKIE_DOMAIN or None

# If sync_in_progress=True but sync_started_at is older than this threshold,
# the Celery worker almost certainly crashed (Redis lock TTL is 1h).
# It is safe to treat this as a stuck state and reset it.
SYNC_STUCK_THRESHOLD = timedelta(hours=2)


router = APIRouter()

@router.get("/google/login")
def google_login(response: Response, invite_token: str | None = None, prompt: str = "select_account"):
    """
    Initiate Google-first OAuth login.
    Generates a secure random state for CSRF protection and returns the redirect URL.
    """
    csrf_token = secrets.token_urlsafe(32)
    state = f"{csrf_token}:{invite_token or ''}"
    oauth_url = ProviderFactory.get_oauth_url("gbp", state=state, prompt=prompt)

    # Primary CSRF store: server-side in Redis. Works regardless of the user's
    # browser third-party-cookie policy (frontend/backend are cross-domain).
    try:
        get_redis().set(_oauth_state_key(csrf_token), b"1", ex=OAUTH_STATE_TTL)
    except Exception:
        # Don't block login if Redis is briefly unavailable; the cookie below
        # still provides CSRF protection for same-site / first-party browsers.
        logging.exception("Failed to store OAuth state in Redis")

    # Secondary CSRF store: cookie (back-compat / first-party browsers).
    # Secure cookie only over HTTPS (production/proxy) to avoid local development CSRF block
    secure_cookie = settings.FRONTEND_URL.startswith("https://")
    samesite_val = "none" if secure_cookie else "lax"

    response.set_cookie(
        key="oauth_state",
        value=csrf_token,
        httponly=True,
        secure=secure_cookie,
        samesite=samesite_val,
        max_age=3600,
        domain=_cookie_domain()
    )
    return {"url": oauth_url}

@router.get("/google/callback")
def google_callback(request: Request, code: str, state: str, db: Session = Depends(get_db)):
    """
    Google OAuth Callback.
    1. Exchanges auth code for credentials.
    2. Fetches Google User Profile.
    3. Auto-creates Workspace (Organization), User, and OAuthAccount on first login.
    4. Auto-triggers Celery task to synchronize locations.
    5. Generates local JWT and redirects to frontend success hook.
    """
    try:
        csrf_token, invite_token, consent_retried = _parse_oauth_state(state)
        
        # Validate CSRF state. Prefer the server-side Redis record (single-use,
        # independent of browser cookie policy); fall back to the cookie for
        # back-compat with logins started before this change rolled out.
        state_valid = False
        try:
            # Atomic single-use check: delete returns the number of keys removed.
            state_valid = get_redis().delete(_oauth_state_key(csrf_token)) == 1
        except Exception:
            logging.exception("Failed to validate OAuth state in Redis")

        if not state_valid:
            cookie_state = request.cookies.get("oauth_state")
            state_valid = bool(cookie_state) and secrets.compare_digest(csrf_token, cookie_state)

        if not state_valid:
            raise ValueError("Invalid CSRF state token. Please try logging in again.")
            
        # 1. Exchange authorization code for tokens
        token_data = ProviderFactory.exchange_code_for_tokens("gbp", code)
        
        # Determine the user info using mock or real client
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        email = token_data["email"]

        # 2. Fetch User Profile from Google info or mock
        google_id = "mock_google_id_999888777"
        name = "Google User"
        avatar = None
        # Only Google's own verified-email claim may relink an existing account below.
        # Stays False if the userinfo call fails, where google_id is still the placeholder.
        email_verified = False

        if settings.APP_ENV == "development" and "mock_access_token" in access_token:
            # Formulate friendly mock profile details based on email prefix
            logging.warning("Mock auth bypass used for email: %s — only permitted in development", email)
            name = email.split("@")[0].title().replace("-", " ")
            google_id = f"google_id_{email.split('@')[0]}"
            email_verified = True
        else:
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
                email_verified = bool(profile.get("email_verified", False))

        email = email.strip().lower()

        # 3. Check if user already exists in our system
        user = db.query(User).filter(User.google_id == google_id).first()
        if not user and email_verified:
            # `users.email` is UNIQUE, but the lookup above is by google_id alone: a row
            # whose google_id no longer matches — recreated by hand, or a re-issued Google
            # `sub` — fell through to the create path and died on an IntegrityError instead
            # of logging in. Relink it to the id Google just gave us. Gated on Google's
            # verified-email claim so an unverified address can never adopt an account.
            user = db.query(User).filter(User.email == email).first()
            if user:
                logging.warning("Relinking user %s to a new google_id", user.id)
                user.google_id = google_id
        is_new_user = False

        if not user:
            # Check if there is a pending, non-expired invite for this email (case-insensitive)
            from app.models.invite import Invite
            from app.models.user_location_access import UserLocationAccess
            
            invite = None
            if invite_token:
                invite = db.query(Invite).filter(
                    Invite.token == invite_token,
                    Invite.email == email,
                    Invite.status.in_(["pending", "in_progress"]),
                    Invite.expires_at > datetime.now(timezone.utc)
                ).first()
                if not invite:
                    raise ValueError("The provided invitation is invalid, expired, or the Google account email does not match the invited email.")
            else:
                pending_invite = db.query(Invite).filter(
                    Invite.email == email,
                    Invite.status.in_(["pending", "in_progress"]),
                    Invite.expires_at > datetime.now(timezone.utc)
                ).first()
                if pending_invite:
                    raise ValueError("You have a pending invitation. Please use the invite link sent to your email to join the workspace.")

            if invite:
                if invite.role == Role.STORE_MANAGER:
                    if not invite.location_ids or len(invite.location_ids) != 1:
                        raise ValueError(f"Corrupt invite: Store Manager must have exactly 1 location, got {invite.location_ids}")

                # User has a valid invite: join the existing organization with correct role
                user = User(
                    email=email,
                    name=name,
                    avatar=avatar,
                    google_id=google_id,
                    role=invite.role,
                    organization_id=invite.organization_id,
                    viewer_scope=invite.viewer_scope
                )
                db.add(user)
                db.flush()

                # Assign locations if provided
                if invite.location_ids:
                    for loc_id in invite.location_ids:
                        db.add(UserLocationAccess(user_id=user.id, location_id=loc_id))
                    
                # Mark invite as accepted
                invite.status = "accepted"

                # Create OAuth Account record
                oauth_account = OAuthAccount(
                    user_id=user.id,
                    provider="gbp",
                    provider_account_id=google_id,
                    access_token=encrypt_token(access_token),
                    refresh_token=encrypt_token(refresh_token) if refresh_token else None,
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                )
                db.add(oauth_account)
                
                db.add(AuditLog(
                    organization_id=invite.organization_id,
                    user_id=user.id,
                    actor_user_id=user.id,
                    target_user_id=user.id,
                    action="invite_accepted",
                    details=f"User joined via invite. Role: {invite.role}"
                ))
                
                # Log connection
                log = SyncLog(
                    organization_id=invite.organization_id,
                    status="Success",
                    run_type="Manual",
                    error_message=f"Invited user joined workspace and logged in via Google: {email}"
                )
                db.add(log)
                db.commit()
                db.refresh(user)
            else:
                is_new_user = True
                # Create a brand new workspace Organization
                org = Organization(name=f"{name}'s Workspace")
                db.add(org)
                db.flush()

                # Auto-create User record
                user = User(
                    email=email,
                    name=name,
                    avatar=avatar,
                    google_id=google_id,
                    role=Role.OWNER,  # First owner is Owner
                    viewer_scope="assigned",
                    organization_id=org.id
                )
                db.add(user)
                db.flush()

                # Create OAuth Account record
                oauth_account = OAuthAccount(
                    user_id=user.id,
                    provider="gbp",
                    provider_account_id=google_id,
                    access_token=encrypt_token(access_token),
                    refresh_token=encrypt_token(refresh_token) if refresh_token else None,
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                )
                db.add(oauth_account)
                
                db.add(AuditLog(
                    organization_id=org.id,
                    user_id=user.id,
                    actor_user_id=user.id,
                    target_user_id=user.id,
                    action="google_connected",
                    details=f"Connected Google Business Profile integration for Owner: {email}"
                ))
                
                # Log connection
                log = SyncLog(
                    organization_id=org.id,
                    status="Success",
                    run_type="Manual",
                    error_message=f"Created workspace and logged in via Google Account: {email}"
                )
                db.add(log)
                db.commit()
                db.refresh(user)

                # Nudge the super-admins to follow up on a fresh signup. Queued after
                # the commit so the row is visible to the worker, and never allowed to
                # break a login that has already succeeded.
                try:
                    celery.send_task("app.tasks.notify_superadmin_signup_task", args=[user.id])
                except Exception:
                    logging.getLogger(__name__).warning(
                        "could not queue signup notification for user %s", user.id, exc_info=True)
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
                    provider="gbp",
                    provider_account_id=google_id,
                    access_token=encrypt_token(access_token),
                    refresh_token=encrypt_token(refresh_token) if refresh_token else None,
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                )
                db.add(oauth_account)
            else:
                oauth_account.provider = "gbp"  # Ensure it is migrated/standardized to "gbp"
                oauth_account.access_token = encrypt_token(access_token)
                if refresh_token:
                    oauth_account.refresh_token = encrypt_token(refresh_token)
                oauth_account.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            db.commit()

            # Batch AuditLog + SyncLog in one commit (was previously 3 separate commits)
            db.add(AuditLog(
                organization_id=user.organization_id,
                user_id=user.id,
                actor_user_id=user.id,
                target_user_id=user.id,
                action="google_connected",
                details=f"Connected Google Business Profile integration for existing user: {email}"
            ))
            db.add(SyncLog(
                organization_id=user.organization_id,
                status="Success",
                run_type="Manual",
                error_message=f"Logged in via Google Account: {email}"
            ))
            db.commit()


        # 4. State-Aware Background Synchronization check
        sync_state = db.query(OrganizationSyncState).filter(
            OrganizationSyncState.organization_id == user.organization_id
        ).first()

        # Only show the "Syncing Workspace..." onboarding preloader when we actually
        # kick off the org's FIRST-EVER onboarding sync. A returning user (or anyone
        # whose org already has a sync state) has onboarded before and must not see it.
        triggered_onboarding = False

        if not sync_state:
            # First-time onboarding sync: create the state record and immediately trigger.
            # Guard against a rare race condition (two simultaneous first-logins for the
            # same brand-new org) by catching a PK conflict gracefully.
            try:
                sync_state = OrganizationSyncState(
                    organization_id=user.organization_id,
                    sync_in_progress=True,
                    sync_started_at=datetime.now(timezone.utc),
                    last_sync_status="Pending"
                )
                db.add(sync_state)
                db.commit()
                triggered_onboarding = True
                celery.send_task(
                    "app.tasks.sync_locations_task",
                    args=[user.organization_id, user.id, "Onboarding"]
                )
            except IntegrityError:
                # Another concurrent login already created the record. Roll back
                # and continue — login itself must still succeed.
                db.rollback()
                sync_state = db.query(OrganizationSyncState).filter(
                    OrganizationSyncState.organization_id == user.organization_id
                ).first()
                if not sync_state:
                    logging.error(
                        "OrganizationSyncState missing after IntegrityError rollback for org %s",
                        user.organization_id
                    )
        else:
            # Check if last sync is stale (older than 12h) and a sync isn't safely in flight.
            threshold_time = datetime.now(timezone.utc) - timedelta(hours=12)
            is_stale = False
            if sync_state.last_location_sync_at is None:
                is_stale = True
            else:
                last_sync_dt = sync_state.last_location_sync_at
                if last_sync_dt.tzinfo is None:
                    last_sync_dt = last_sync_dt.replace(tzinfo=timezone.utc)
                if last_sync_dt < threshold_time:
                    is_stale = True

            # Detect orphaned stuck state: sync_in_progress=True but the worker
            # crashed (Redis lock TTL has passed) so the flag was never cleared.
            _started_at = sync_state.sync_started_at
            if _started_at is not None and _started_at.tzinfo is None:
                _started_at = _started_at.replace(tzinfo=timezone.utc)
            is_stuck = (
                sync_state.sync_in_progress
                and _started_at is not None
                and (datetime.now(timezone.utc) - _started_at) > SYNC_STUCK_THRESHOLD
            )

            # Trigger only when stale AND (not currently syncing OR stuck/orphaned)
            if is_stale and (not sync_state.sync_in_progress or is_stuck):
                sync_state.sync_in_progress = True
                sync_state.sync_started_at = datetime.now(timezone.utc)
                sync_state.last_sync_status = "Pending"
                db.commit()
                celery.send_task(
                    "app.tasks.sync_locations_task",
                    args=[user.organization_id, user.id, "Auto-Refresh"]
                )


        # 4b. Guarantee offline access. Every background sync (insights, reviews, posts)
        # authenticates with the refresh token, but Google only issues one when consent is
        # actually GRANTED — a repeat authorization with prompt=select_account returns an
        # access token and nothing else. An account could therefore look connected while
        # every scheduled sync failed with "Refresh token missing". If no refresh token is
        # stored for this user, bounce them through the consent screen once.
        if not consent_retried:
            stored_oauth = db.query(OAuthAccount).filter(OAuthAccount.user_id == user.id).first()
            if stored_oauth is None or not stored_oauth.refresh_token:
                logging.warning(
                    "No Google refresh token for user %s after OAuth; re-requesting consent.", user.id
                )
                retry_csrf = secrets.token_urlsafe(32)
                try:
                    get_redis().set(_oauth_state_key(retry_csrf), b"1", ex=OAUTH_STATE_TTL)
                except Exception:
                    logging.exception("Failed to store OAuth consent-retry state in Redis")
                retry_response = RedirectResponse(
                    url=ProviderFactory.get_oauth_url(
                        "gbp", state=f"{retry_csrf}:{invite_token or ''}:c", prompt="consent"
                    )
                )
                # Mirror the cookie fallback the login endpoint sets, so the retry validates
                # even when Redis is unavailable.
                _secure = settings.FRONTEND_URL.startswith("https://")
                retry_response.set_cookie(
                    key="oauth_state", value=retry_csrf, httponly=True, secure=_secure,
                    samesite="none" if _secure else "lax", max_age=3600, domain=_cookie_domain(),
                )
                return retry_response

        # 5. Generate local JWT access token and refresh token
        local_token = create_access_token(subject=user.email, token_version=user.token_version)
        refresh_token = create_refresh_token(subject=user.email, token_version=user.token_version)
        
        # Generate new session CSRF token
        session_csrf = secrets.token_urlsafe(32)
        
        # Redirect to frontend success page
        redirect_url = f"{settings.FRONTEND_URL}/login/success?onboarding={'true' if triggered_onboarding else 'false'}"
        response = RedirectResponse(url=redirect_url)
        
        # Force insecure cookies for localhost development even if FRONTEND_URL is https
        is_localhost = "localhost" in settings.FRONTEND_URL or "127.0.0.1" in settings.FRONTEND_URL
        secure_cookie = settings.FRONTEND_URL.startswith("https://") and not is_localhost
        samesite_val = "none" if secure_cookie else "lax"
        
        # Set short-lived access cookie (15 mins)
        response.set_cookie(
            key="gmb_auth_token",
            value=local_token,
            httponly=True,
            secure=secure_cookie,
            samesite=samesite_val,
            max_age=15 * 60,  # 15 minutes
            domain=_cookie_domain()
        )

        # Set long-lived refresh cookie (7 days)
        response.set_cookie(
            key="gmb_refresh_token",
            value=refresh_token,
            httponly=True,
            secure=secure_cookie,
            samesite=samesite_val,
            max_age=3600 * 24 * 7,  # 7 days
            domain=_cookie_domain()
        )

        # Set long-lived CSRF cookie (7 days)
        response.set_cookie(
            key="gmb_csrf_token",
            value=session_csrf,
            httponly=False,
            secure=secure_cookie,
            samesite=samesite_val,
            max_age=3600 * 24 * 7,  # 7 days
            domain=_cookie_domain()
        )
        return response
        
    except ValueError as e:
        db.rollback()
        logging.exception("Validation/CSRF error during Google OAuth callback")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=oauth_validation_failed")
    except Exception as e:
        db.rollback()
        logging.exception("Unhandled exception during Google OAuth callback")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=oauth_failed")

@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Refresh the access token using the long-lived refresh token cookie.
    """
    refresh_token = request.cookies.get("gmb_refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing"
        )
        
    payload = decode_access_token_payload(refresh_token)
    if payload is None or payload.get("sub") is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
        
    email = payload.get("sub")
    token_version = payload.get("ver", 1)
    
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active or user.token_version != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User session invalidated"
        )
        
    # Generate new access token
    new_access_token = create_access_token(subject=user.email, token_version=user.token_version)
    
    # Force insecure cookies for localhost development even if FRONTEND_URL is https
    is_localhost = "localhost" in settings.FRONTEND_URL or "127.0.0.1" in settings.FRONTEND_URL
    secure_cookie = settings.FRONTEND_URL.startswith("https://") and not is_localhost
    samesite_val = "none" if secure_cookie else "lax"
    
    response.set_cookie(
        key="gmb_auth_token",
        value=new_access_token,
        httponly=True,
        secure=secure_cookie,
        samesite=samesite_val,
        max_age=15 * 60,  # 15 minutes
        domain=_cookie_domain()
    )

    # Generate and set new CSRF cookie on refresh
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        key="gmb_csrf_token",
        value=csrf_token,
        httponly=False,
        secure=secure_cookie,
        samesite=samesite_val,
        max_age=3600 * 24 * 7,  # 7 days
        domain=_cookie_domain()
    )
    return {"status": "success", "message": "Token refreshed successfully", "csrf_token": csrf_token}

@router.post("/logout")
def logout(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Clear all secure auth and CSRF cookies and invalidate session on server.
    """
    # Invalidate all existing tokens for this user (security hardening)
    current_user.token_version += 1
    db.commit()
    
    secure_cookie = settings.FRONTEND_URL.startswith("https://")
    samesite_val = "none" if secure_cookie else "lax"
    
    cookie_params = {
        "path": "/",
        "httponly": True,
        "secure": secure_cookie,
        "samesite": samesite_val,
        "domain": _cookie_domain()
    }
    
    response.delete_cookie(key="gmb_auth_token", **cookie_params)
    response.delete_cookie(key="gmb_refresh_token", **cookie_params)
    
    # CSRF cookie is not httponly
    cookie_params["httponly"] = False
    response.delete_cookie(key="gmb_csrf_token", **cookie_params)
    
    return {"message": "Successfully logged out"}
