import logging
from typing import Generator, Optional, List

logger = logging.getLogger(__name__)
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import decode_access_token_payload
from app.models.user import User
from app.models.user_location_access import UserLocationAccess
from app.models.organization import Organization
from app.models.location import Location
from app.services.billing.entitlement_service import EntitlementService
from app.core.config import settings
from app.core.roles import Role, ADMIN_ROLES, STAFF_ROLES, TEAM_VIEWER_ROLES
from sqlalchemy.orm.attributes import set_committed_value

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    # Per-request cache: check_billing_lock (global dep) resolves the user
    # manually before the route's Depends(get_current_user) runs, which FastAPI's
    # dependency cache can't dedupe — without this every mutating request paid
    # the User + Organization queries twice.
    cached = getattr(request.state, "current_user", None)
    if cached is not None:
        return cached

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Try reading from httpOnly cookie first
    token = request.cookies.get("gmb_auth_token")
    if not token:
        # Fallback to Authorization header for API clients
        auth_header = request.headers.get("Authorization")
        if auth_header:
            parts = auth_header.split(" ", 1)
            if len(parts) != 2 or parts[0].lower() != "bearer":
                raise HTTPException(status_code=401, detail="Invalid authorization header")
            token = parts[1]
            
    if not token:
        raise credentials_exception
    
    payload = decode_access_token_payload(token)
    if payload is None or payload.get("sub") is None or payload.get("type") == "refresh":
        raise credentials_exception
        
    email = payload.get("sub")
    token_version = payload.get("ver", 1)
        
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
        
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    if user.token_version != token_version:
        raise credentials_exception

    # Soft-deleted accounts lose access immediately (a super-admin can still restore them
    # within the grace window). Check the user, then their org (one indexed PK lookup) so
    # deleting an org locks out every member without stamping each user row.
    if user.deleted_at is not None:
        raise HTTPException(status_code=403, detail="This account has been deleted.")
    org_deleted = db.query(Organization.deleted_at).filter(
        Organization.id == user.organization_id
    ).scalar()
    if org_deleted is not None:
        raise HTTPException(status_code=403, detail="This account has been deleted.")

    # Super-admin workspace impersonation: a super-admin may operate inside another
    # org by sending X-Acting-Org. We override organization_id at the source so every
    # downstream query (which all read current_user.organization_id) follows along —
    # no per-endpoint changes. set_committed_value writes it as if loaded from the DB,
    # so the change is NOT dirty and can never be flushed back onto the admin's own
    # row, while the user stays bound to the session (lazy relationships still load).
    acting_org = request.headers.get("X-Acting-Org")
    if acting_org and settings.is_superadmin(user.email):
        try:
            target_org_id = int(acting_org)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid X-Acting-Org")
        if target_org_id != user.organization_id:
            logger.warning(
                "SUPERADMIN_IMPERSONATION admin=%s acting_org=%s path=%s method=%s",
                user.email, target_org_id, request.url.path, request.method,
            )
            set_committed_value(user, "organization_id", target_org_id)

    request.state.current_user = user
    return user


def _get_request_org(request: Request, db: Session, organization_id: int) -> Optional[Organization]:
    """Per-request Organization cache shared by check_billing_lock and
    require_feature so a gated mutating request loads the org row once."""
    org = getattr(request.state, "org", None)
    if org is None or org.id != organization_id:
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        request.state.org = org
    return org

class RoleChecker:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have enough permissions to access this resource"
            )
        return current_user

def require_feature(feature: str):
    """Dependency factory: 403 unless the caller's plan tier includes `feature`.
    Central gate for tier-limited capabilities (scheduler, team, templates, auto_reply,
    leaderboard, comparison, local_rank, microsite) — see plan_config.PLANS."""
    from app.core import plan_config

    def _dep(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> None:
        org = _get_request_org(request, db, current_user.organization_id)
        if not org or not plan_config.plan_has_feature(org.plan_tier, feature):
            raise HTTPException(
                status_code=403,
                detail=f"upgrade_required: your plan does not include {feature.replace('_', ' ')}.",
            )
    return _dep


# Predefined role dependencies
admin_required = RoleChecker(list(ADMIN_ROLES))
staff_required = RoleChecker(list(STAFF_ROLES))
team_viewer_required = RoleChecker(list(TEAM_VIEWER_ROLES))
regional_manager_plus = RoleChecker(list(TEAM_VIEWER_ROLES))


def superadmin_required(current_user: User = Depends(get_current_user)) -> User:
    """Platform super-admin gate for the cross-org /admin panel.

    Membership is an env allowlist (settings.SUPERADMIN_EMAILS), not a DB role — so
    granting access needs no migration and the first admin needs no manual DB edit.
    """
    if not settings.is_superadmin(current_user.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super-admin access required",
        )
    return current_user

def get_user_location_ids(user: User, db: Session) -> Optional[List[int]]:
    if user.role in ADMIN_ROLES:
        return None
    if user.role == Role.VIEWER and user.viewer_scope == "organization":
        return None
    
    # Fetch assigned locations
    mappings = db.query(UserLocationAccess).filter(UserLocationAccess.user_id == user.id).all()
    return [mapping.location_id for mapping in mappings]

def require_location_access(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Location:
    """FastAPI dependency enforcing BOTH tenant (org) boundary AND per-user
    location scope for a path's location_id.

    Declare a route's param as `location: Location = Depends(require_location_access)`
    so both checks run automatically before the handler — making it structurally
    impossible to forget either one — and use the returned row directly (no re-fetch).
    Bodies that still need the id use `location_id = location.id`.

    1. Tenant boundary: the location must exist within the caller's organization.
       This runs for ALL roles (Owner/Admin included), so an endpoint can never
       leak or mutate another org's location by forgetting its own org filter
       (the class of bug that caused the health-score IDOR).
    2. Location scope: org-wide roles (Owner/Admin and org-scoped Viewer) pass;
       location-restricted roles must have the location in their assigned set.

    Returns the validated Location row for inline use.
    """
    # Tenant boundary first — a cross-org id is "not found", regardless of role.
    location = (
        db.query(Location)
        .filter(
            Location.id == location_id,
            Location.organization_id == current_user.organization_id,
        )
        .first()
    )
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        )

    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None and location_id not in allowed_location_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this location",
        )
    return location


def check_csrf(request: Request):
    """
    Stateless Double-Submit Cookie CSRF Defense.
    Validates X-CSRF-Token header against gmb_csrf_token cookie for mutating requests.
    """
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return
        
    # Skip CSRF check in development to avoid localhost port-mismatch issues
    from app.core.config import settings
    if settings.APP_ENV == "development":
        return
        
    # Exclude OAuth and Refresh endpoints (exact path match, O(1) frozenset lookup)
    _CSRF_EXCLUDED_PATHS: frozenset = frozenset({
        "/api/v1/auth/google/callback",
        "/api/v1/auth/google/login",
        "/api/v1/auth/refresh",
        "/api/v1/webhooks/razorpay",
        "/api/v1/",
        "/",
    })
    path = request.url.path
    if path in _CSRF_EXCLUDED_PATHS:
        return

    # Public microsite endpoints are unauthenticated by design — anonymous
    # visitors have no CSRF cookie/header. They're safe: no session, rate-limited.
    if path.startswith("/api/v1/public/"):
        return
        
    csrf_cookie = request.cookies.get("gmb_csrf_token")
    csrf_header = request.headers.get("X-CSRF-Token")
    
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        detail_msg = "CSRF validation failed: "
        if not csrf_cookie:
            detail_msg += "Cookie 'gmb_csrf_token' is missing. "
        if not csrf_header:
            detail_msg += "Header 'X-CSRF-Token' is missing. "
        if csrf_cookie and csrf_header and csrf_cookie != csrf_header:
            # Mask tokens in logs for security but show if they match
            logger.warning(f"CSRF Mismatch: cookie={csrf_cookie[:4]}... header={csrf_header[:4]}...")
            detail_msg += "Cookie and Header tokens do not match. "
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail_msg.strip()
        )

def check_billing_lock(request: Request, db: Session = Depends(get_db)):
    """Global dependency to block write operations if organization is locked."""
    if request.method in ["GET", "OPTIONS", "HEAD"]:
        return

    # The platform super-admin panel acts cross-org as staff; never gate it on the
    # acting admin's own organization lock.
    if request.url.path.startswith("/api/v1/admin/"):
        return

    # Public, unauthenticated endpoints (e.g. microsite lead capture) have no user
    # and must never be gated by org billing lock.
    if request.url.path.startswith("/api/v1/public/"):
        return

    _WHITELIST = frozenset({
        "/api/v1/auth/google/callback",
        "/api/v1/auth/google/login",
        "/api/v1/auth/refresh",
        "/api/v1/billing/checkout-subscription",
        "/api/v1/billing/buy-credits",
        "/api/v1/billing/confirm",
        "/api/v1/webhooks/razorpay"
    })
    
    if request.url.path in _WHITELIST:
        return

    # Manually resolve get_current_user only when not on whitelisted/public endpoints
    current_user = get_current_user(request=request, db=db)

    if not current_user.organization_id:
        return

    org = _get_request_org(request, db, current_user.organization_id)
    if org and EntitlementService.is_org_locked(org):
        raise HTTPException(status_code=402, detail="Organization is locked. Please update your subscription.")
