"""Email + password login for ONE account: the Meta App Review reviewer.

Pinzo authenticates with Google. This exists solely because Meta's reviewers
cannot complete a Google sign-in (unfamiliar-device challenges, no access to
the account's 2FA), and a review that cannot log in is a rejected review.

It is deliberately the narrowest thing that solves that:

  * OFF by default. `DEMO_LOGIN_ENABLED=false` makes the endpoint 404 —
    not 401, so its existence isn't advertised when it isn't in use.
  * EXACTLY ONE email may use it, set in DEMO_LOGIN_EMAIL. Every other
    address is refused before any password work happens.
  * The password is never stored anywhere in plaintext, and never in the
    database: DEMO_LOGIN_PASSWORD_HASH holds a scrypt hash, generated with
    scripts/hash_demo_password.py.
  * Rate limited per IP, so it cannot be ground down.
  * Issues the SAME cookies as the Google callback — no parallel session
    scheme to diverge or to reason about separately.

Turn it off (`DEMO_LOGIN_ENABLED=false`) the day App Review completes. It is a
temporary door, and doors left open get used.
"""
import hashlib
import hmac
import logging
import secrets
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.db.session import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

# scrypt parameters. Deliberately slow: the whole point is that a leaked hash
# is expensive to attack. Must match scripts/hash_demo_password.py.
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 16384, 8, 1, 64

MAX_ATTEMPTS = 8
WINDOW_SECONDS = 15 * 60
_attempts: dict[str, tuple[int, float]] = {}


class DemoLogin(BaseModel):
    email: EmailStr
    password: str


def hash_password(plain: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(plain.encode(), salt=salt.encode(), n=SCRYPT_N,
                         r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_LEN).hex()
    return f"scrypt${salt}${key}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        scheme, salt, key = stored.split("$")
        if scheme != "scrypt":
            return False
    except ValueError:
        return False
    calc = hashlib.scrypt(plain.encode(), salt=salt.encode(), n=SCRYPT_N,
                          r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_LEN).hex()
    # Constant-time: a timing difference here leaks how much of the hash matched.
    return hmac.compare_digest(calc, key)


def _throttled(ip: str) -> bool:
    count, reset_at = _attempts.get(ip, (0, 0.0))
    now = time.time()
    if now > reset_at:
        _attempts[ip] = (0, now + WINDOW_SECONDS)
        return False
    return count >= MAX_ATTEMPTS


def _record_failure(ip: str) -> None:
    count, reset_at = _attempts.get(ip, (0, time.time() + WINDOW_SECONDS))
    _attempts[ip] = (count + 1, reset_at)


@router.post("/demo-login")
def demo_login(payload: DemoLogin, request: Request, db: Session = Depends(get_db)):
    if not settings.DEMO_LOGIN_ENABLED:
        # 404, not 403: when the flag is off this endpoint should look like it
        # does not exist.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    allowed_email = (settings.DEMO_LOGIN_EMAIL or "").strip().lower()
    stored_hash = (settings.DEMO_LOGIN_PASSWORD_HASH or "").strip()
    if not allowed_email or not stored_hash:
        logger.error("[demo-login] enabled but DEMO_LOGIN_EMAIL / _PASSWORD_HASH are not set")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Demo login is not configured")

    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() \
        or (request.client.host if request.client else "unknown")
    if _throttled(ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Too many attempts. Try again later.")

    email = payload.email.strip().lower()
    # One address only. Checked before the password so an attacker cannot use
    # this endpoint to test passwords against arbitrary accounts.
    if not hmac.compare_digest(email, allowed_email) or not verify_password(payload.password, stored_hash):
        _record_failure(ip)
        logger.warning("[demo-login] failed attempt for %s from %s", email[:40], ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid email or password")

    user = db.query(User).filter(User.email == allowed_email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="The demo account does not exist yet. Sign in with Google once to create it.")

    _attempts.pop(ip, None)

    # Identical session to the Google callback's — same tokens, same cookie
    # names, same lifetimes. Anything else would mean two auth paths to keep
    # in step, and they would drift.
    access = create_access_token(subject=user.email, token_version=user.token_version)
    refresh = create_refresh_token(subject=user.email, token_version=user.token_version)
    session_csrf = secrets.token_urlsafe(32)

    is_localhost = "localhost" in settings.FRONTEND_URL or "127.0.0.1" in settings.FRONTEND_URL
    secure_cookie = settings.FRONTEND_URL.startswith("https://") and not is_localhost
    samesite_val = "none" if secure_cookie else "lax"
    domain = (settings.COOKIE_DOMAIN or None)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie("gmb_auth_token", access, httponly=True, secure=secure_cookie,
                        samesite=samesite_val, max_age=15 * 60, domain=domain)
    response.set_cookie("gmb_refresh_token", refresh, httponly=True, secure=secure_cookie,
                        samesite=samesite_val, max_age=3600 * 24 * 7, domain=domain)
    response.set_cookie("gmb_csrf_token", session_csrf, httponly=False, secure=secure_cookie,
                        samesite=samesite_val, max_age=3600 * 24 * 7, domain=domain)
    logger.info("[demo-login] reviewer session issued for %s", allowed_email)
    return response
