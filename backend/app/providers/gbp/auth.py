import datetime
from datetime import timezone
from typing import Optional
import logging
import time
import random
import asyncio
import httpx
from sqlalchemy.orm import Session
from app.providers.base.auth import AuthContext
from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token
from app.models.oauth_account import OAuthAccount
from app.core.roles import ADMIN_ROLES

logger = logging.getLogger(__name__)

# Metrics hooks for future instrumentation
def track_refresh_metric(metric_name: str, labels: dict = None, value: float = 1.0):
    """
    Extension point for metrics (e.g. Prometheus, StatsD).
    metric_name can be:
        - "oauth_refresh_latency_seconds"
        - "oauth_refresh_failures_total"
        - "oauth_refresh_success_total"
        - "oauth_refresh_contention_total"
        - "oauth_refresh_skipped_total"
    """
    pass

class PermanentAuthError(Exception):
    """Exception raised when OAuth connections are permanently invalid or revoked."""
    pass

class GBPAuthManager:
    def __init__(self, auth_context: AuthContext, db: Session):
        self.auth_context = auth_context
        self.db = db

    async def get_valid_token(self) -> str:
        """
        Checks if the current token is expired (or close to expiring).
        If so, refreshes the token, re-encrypts it, persists to DB, and updates AuthContext.
        Returns the valid plaintext access token.
        """
        now = datetime.datetime.now(timezone.utc)
        token_expiry = self.auth_context.expires_at
        if token_expiry and token_expiry.tzinfo is None:
            token_expiry = token_expiry.replace(tzinfo=timezone.utc)

        # Proactive Refresh: if expiring within 5 minutes
        if not token_expiry or token_expiry <= now + datetime.timedelta(minutes=5):
            await self._refresh_token()
            
        return self.auth_context.access_token

    async def _refresh_token(self):
        from app.models.user import User
        from app.db.session import SessionLocal
        import redis.asyncio as aioredis

        org_id = self.auth_context.organization_id

        # 1. Quick check without database lock or transaction
        # Check if the DB token is already fresh to avoid even checking Redis
        with SessionLocal() as db_check:
            oauth_account = db_check.query(OAuthAccount).join(User).filter(
                User.organization_id == org_id,
                User.role.in_(ADMIN_ROLES),
                OAuthAccount.provider.in_(["gbp", "google"])
            ).first()

            if oauth_account:
                db_expiry = oauth_account.expires_at
                if db_expiry and db_expiry.tzinfo is None:
                    db_expiry = db_expiry.replace(tzinfo=timezone.utc)
                
                now = datetime.datetime.now(timezone.utc)
                if db_expiry and db_expiry > now + datetime.timedelta(minutes=5):
                    # Database already has a fresh token (e.g., updated by another worker)
                    decrypted_access = decrypt_token(oauth_account.access_token)
                    decrypted_refresh = decrypt_token(oauth_account.refresh_token) if oauth_account.refresh_token else None
                    
                    self.auth_context.access_token = decrypted_access
                    if decrypted_refresh:
                        self.auth_context.refresh_token = decrypted_refresh
                    self.auth_context.expires_at = db_expiry
                    
                    logger.info({
                        "event": "oauth_refresh_skipped_already_fresh",
                        "organization_id": org_id,
                        "expiry": db_expiry.isoformat()
                    })
                    track_refresh_metric("oauth_refresh_skipped_total", {"reason": "already_fresh", "org_id": str(org_id)})
                    return

        # 2. Acquire Redis lock to prevent multiple concurrent HTTP requests to Google
        r = aioredis.from_url(settings.REDIS_URL)
        lock_key = f"lock:oauth_refresh:{org_id}"
        lock = r.lock(lock_key, timeout=60)

        # Wait up to 10 seconds for any concurrent refresh tasks to complete
        start_lock_time = time.monotonic()
        if not await lock.acquire(blocking=True, blocking_timeout=10):
            track_refresh_metric("oauth_refresh_contention_total", {"org_id": str(org_id)})
            logger.warning({
                "event": "oauth_refresh_lock_timeout",
                "organization_id": org_id,
                "duration_seconds": time.monotonic() - start_lock_time
            })
            raise Exception("Could not acquire token refresh lock. Concurrency limit exceeded.")

        try:
            # 3. Inside the lock: Double-check DB again to see if another worker refreshed it
            # while we were waiting for the Redis lock
            with SessionLocal() as db_check:
                oauth_account = db_check.query(OAuthAccount).join(User).filter(
                    User.organization_id == org_id,
                    User.role.in_(ADMIN_ROLES),
                    OAuthAccount.provider.in_(["gbp", "google"])
                ).first()

                if not oauth_account:
                    raise Exception("Google credentials expired or invalid. OAuthAccount not found in database.")

                db_expiry = oauth_account.expires_at
                if db_expiry and db_expiry.tzinfo is None:
                    db_expiry = db_expiry.replace(tzinfo=timezone.utc)
                
                now = datetime.datetime.now(timezone.utc)
                if db_expiry and db_expiry > now + datetime.timedelta(minutes=5):
                    # Succeeded! Another worker refreshed it. Sync in-memory context.
                    decrypted_access = decrypt_token(oauth_account.access_token)
                    decrypted_refresh = decrypt_token(oauth_account.refresh_token) if oauth_account.refresh_token else None
                    
                    self.auth_context.access_token = decrypted_access
                    if decrypted_refresh:
                        self.auth_context.refresh_token = decrypted_refresh
                    self.auth_context.expires_at = db_expiry
                    
                    logger.info({
                        "event": "oauth_refresh_skipped_after_lock",
                        "organization_id": org_id,
                        "expiry": db_expiry.isoformat()
                    })
                    track_refresh_metric("oauth_refresh_skipped_total", {"reason": "after_lock", "org_id": str(org_id)})
                    return

                # Get decrypted refresh token for the HTTP call
                refresh_token = decrypt_token(oauth_account.refresh_token) if oauth_account.refresh_token else self.auth_context.refresh_token

            # 4. We are the first: proceed to refresh via Google OUTSIDE database transactions/locks
            if not refresh_token:
                raise PermanentAuthError("Google credentials expired or invalid. Refresh token missing. Re-authentication required.")

            logger.info({
                "event": "oauth_refresh_start",
                "organization_id": org_id
            })

            # Sandbox / Mock Token handling
            if "mock_refresh_token" in refresh_token:
                new_access_token = "mock_access_token_refreshed_" + str(int(datetime.datetime.now(timezone.utc).timestamp()))
                expires_in = 3600
                new_refresh_token = refresh_token
                refresh_duration = 0.0
            else:
                url = "https://oauth2.googleapis.com/token"
                data = {
                    "refresh_token": refresh_token,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "grant_type": "refresh_token"
                }
                
                # HTTP Call with Exponential Backoff and Jitter
                new_access_token, new_refresh_token, expires_in, refresh_duration = await self._call_google_refresh_with_retry(url, data, refresh_token)

            new_expiry = datetime.datetime.now(timezone.utc) + datetime.timedelta(seconds=expires_in)

            # 5. Open short DB transaction to save the new credentials and double-check
            with SessionLocal() as write_db:
                # SELECT ... FOR UPDATE to lock the row
                oauth_account_write = write_db.query(OAuthAccount).join(User).filter(
                    User.organization_id == org_id,
                    User.role.in_(ADMIN_ROLES),
                    OAuthAccount.provider.in_(["gbp", "google"])
                ).with_for_update().first()

                if not oauth_account_write:
                    raise Exception("OAuthAccount row missing during write phase.")

                # Final validation: check if another worker somehow committed since our check
                db_expiry_write = oauth_account_write.expires_at
                if db_expiry_write and db_expiry_write.tzinfo is None:
                    db_expiry_write = db_expiry_write.replace(tzinfo=timezone.utc)

                if db_expiry_write and db_expiry_write > now + datetime.timedelta(minutes=5):
                    # Discard newly fetched token, another worker got there first
                    decrypted_access = decrypt_token(oauth_account_write.access_token)
                    decrypted_refresh = decrypt_token(oauth_account_write.refresh_token) if oauth_account_write.refresh_token else None
                    
                    self.auth_context.access_token = decrypted_access
                    if decrypted_refresh:
                        self.auth_context.refresh_token = decrypted_refresh
                    self.auth_context.expires_at = db_expiry_write
                    
                    logger.info({
                        "event": "oauth_refresh_discarded_post_lock",
                        "organization_id": org_id,
                        "expiry": db_expiry_write.isoformat()
                    })
                    track_refresh_metric("oauth_refresh_skipped_total", {"reason": "discarded_post_lock", "org_id": str(org_id)})
                    return

                # Update DB record
                oauth_account_write.provider = "gbp"
                oauth_account_write.access_token = encrypt_token(new_access_token)
                if new_refresh_token:
                    oauth_account_write.refresh_token = encrypt_token(new_refresh_token)
                oauth_account_write.expires_at = new_expiry
                write_db.commit()

            # 6. Sync in-memory context
            self.auth_context.access_token = new_access_token
            if new_refresh_token:
                self.auth_context.refresh_token = new_refresh_token
            self.auth_context.expires_at = new_expiry

            logger.info({
                "event": "oauth_refresh_success",
                "organization_id": org_id,
                "duration_seconds": refresh_duration,
                "expiry": new_expiry.isoformat()
            })
            track_refresh_metric("oauth_refresh_success_total", {"org_id": str(org_id)})
            track_refresh_metric("oauth_refresh_latency_seconds", {"org_id": str(org_id)}, refresh_duration)

        except Exception as e:
            track_refresh_metric("oauth_refresh_failures_total", {"org_id": str(org_id)})
            logger.error({
                "event": "oauth_refresh_failure",
                "organization_id": org_id,
                "error": str(e)
            })
            raise
        finally:
            try:
                await lock.release()
            except Exception:
                pass

    async def _call_google_refresh_with_retry(self, url: str, data: dict, fallback_refresh_token: str, max_attempts: int = 3):
        base_backoff = 1.0
        async with httpx.AsyncClient() as client:
            for attempt in range(1, max_attempts + 1):
                try:
                    start_time = time.monotonic()
                    response = await client.post(url, data=data, timeout=10.0)
                    duration = time.monotonic() - start_time
                    
                    if response.status_code == 200:
                        token_data = response.json()
                        new_access = token_data["access_token"]
                        new_refresh = token_data.get("refresh_token", fallback_refresh_token)
                        expires_in = token_data.get("expires_in", 3600)
                        return new_access, new_refresh, expires_in, duration
                    
                    # Handle non-retryable status codes
                    if response.status_code in [400, 401, 403, 404, 409]:
                        err_text = response.text
                        if "invalid_grant" in err_text.lower() or "revoke" in err_text.lower():
                            raise PermanentAuthError(f"Google credentials permanently revoked or invalid: {err_text}")
                        raise Exception(f"Failed to refresh token (non-retryable status {response.status_code}): {err_text}")
                    
                    raise httpx.HTTPStatusError(f"HTTP status {response.status_code}", request=response.request, response=response)
                    
                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    if attempt == max_attempts:
                        raise Exception(f"Failed to refresh token after {max_attempts} attempts. Last error: {str(exc)}")
                    
                    # Capped exponential backoff with jitter
                    sleep_time = min(base_backoff * (2 ** (attempt - 1)) + random.uniform(0.1, 0.5), 10.0)
                    logger.warning({
                        "event": "oauth_refresh_retry",
                        "organization_id": self.auth_context.organization_id,
                        "attempt": attempt,
                        "next_retry_delay": sleep_time,
                        "error": str(exc)
                    })
                    await asyncio.sleep(sleep_time)
