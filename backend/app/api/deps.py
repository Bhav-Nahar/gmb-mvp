from typing import Generator, Optional, List
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import decode_access_token_payload
from app.models.user import User
from app.models.user_location_access import UserLocationAccess

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
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
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
admin_required = RoleChecker(["Owner", "Admin"])
staff_required = RoleChecker(["Owner", "Admin", "Regional Manager", "Store Manager"])

def get_user_location_ids(user: User, db: Session) -> Optional[List[int]]:
    if user.role in ["Owner", "Admin"]:
        return None
    if user.role == "Viewer" and user.viewer_scope == "organization":
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
        if current_user.role in ["Owner", "Admin"]:
            # Optionally check if location belongs to org here, but usually done at query level
            return location_id
            
        if current_user.role == "Viewer":
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

def check_csrf(request: Request):
    """
    Stateless Double-Submit Cookie CSRF Defense.
    Validates X-CSRF-Token header against gmb_csrf_token cookie for mutating requests.
    """
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return
        
    # Exclude OAuth and Refresh endpoints (exact match on trailing part of path)
    path = request.url.path
    if any(path.endswith(p) for p in [
        "/auth/google/callback",
        "/auth/google/login",
        "/auth/refresh",
        "/api/v1/" # health check endpoint might be just / or /api/v1/
    ]) or path == "/":
        return
        
    csrf_cookie = request.cookies.get("gmb_csrf_token")
    csrf_header = request.headers.get("X-CSRF-Token")
    
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed"
        )
