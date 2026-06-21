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
from app.core import plan_config
import redis
from app.core.config import settings
from app.core.roles import Role, ADMIN_ROLES, STAFF_ROLES, TEAM_VIEWER_ROLES
from sqlalchemy import select

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
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
        
    return user

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

def verify_location_access(location_id: int):
    def _verify(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        if current_user.role in ADMIN_ROLES:
            # Optionally check if location belongs to org here, but usually done at query level
            return location_id

        if current_user.role == Role.VIEWER:
            if request.method not in ["GET", "OPTIONS", "HEAD"]:
                raise HTTPException(status_code=403, detail="Viewers cannot perform mutations")
            if current_user.viewer_scope == "organization":
                return location_id
        
        # Check mapping
        mapping = db.query(UserLocationAccess).filter(
            UserLocationAccess.user_id == current_user.id,
            UserLocationAccess.location_id == location_id
        ).first()
        
        if not mapping:
            raise HTTPException(status_code=403, detail="You do not have access to this location")
            
        return location_id
    return _verify

def require_location_access(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> int:
    """FastAPI dependency enforcing BOTH tenant (org) boundary AND per-user
    location scope for a path's location_id.

    Declare a route's path param as `location_id: int = Depends(require_location_access)`
    so both checks run automatically before the handler — making it structurally
    impossible to forget either one.

    1. Tenant boundary: the location must exist within the caller's organization.
       This runs for ALL roles (Owner/Admin included), so an endpoint can never
       leak or mutate another org's location by forgetting its own org filter
       (the class of bug that caused the health-score IDOR).
    2. Location scope: org-wide roles (Owner/Admin and org-scoped Viewer) pass;
       location-restricted roles must have the location in their assigned set.

    Returns the validated location_id for inline use.
    """
    # Tenant boundary first — a cross-org id is "not found", regardless of role.
    location_exists = (
        db.query(Location.id)
        .filter(
            Location.id == location_id,
            Location.organization_id == current_user.organization_id,
        )
        .first()
    )
    if location_exists is None:
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
    return location_id


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

def get_redis_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)

def check_billing_lock(request: Request, db: Session = Depends(get_db)):
    """Global dependency to block write operations if organization is locked."""
    if request.method in ["GET", "OPTIONS", "HEAD"]:
        return

    # The platform super-admin panel acts cross-org as staff; never gate it on the
    # acting admin's own organization lock.
    if request.url.path.startswith("/api/v1/admin/"):
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

    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if org and EntitlementService.is_org_locked(org):
        raise HTTPException(status_code=402, detail="Organization is locked. Please update your subscription.")


def check_location_quota(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Dependency to check if the organization has reached its location quota.

    NOTE: Authoritative quota enforcement lives in the location sync Celery task
    (app.tasks), which marks over-quota locations 'pending_payment' at insert time —
    an HTTP dependency cannot gate a background task. This dependency is retained only
    for any future *manual* add-location endpoint and is currently unused.
    """
    if not current_user.organization_id:
        return

    org_id = current_user.organization_id
    
    redis_client = get_redis_client()
    lock = redis_client.lock(f"lock:add_location:{org_id}", timeout=10)
    
    if not lock.acquire(blocking=True, blocking_timeout=5):
        raise HTTPException(status_code=429, detail="Too many concurrent requests. Please try again.")

    try:
        stmt = select(Organization).where(Organization.id == org_id).with_for_update()
        org = db.scalars(stmt).first()
        
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        # location_quota reflects what the org has actually paid for (set on
        # subscription.charged). Falls back to the trial quota before activation.
        quota = org.location_quota if org.location_quota is not None else plan_config.TRIAL_LOCATION_QUOTA

        current_count = db.query(Location).filter(Location.organization_id == org_id).count()
        if current_count >= quota:
            raise HTTPException(status_code=402, detail=f"location_quota_exceeded: limit {quota} reached.")
            
    finally:
        lock.release()
