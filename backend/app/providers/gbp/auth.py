import datetime
from datetime import timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.providers.base.auth import AuthContext
from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token
from app.models.oauth_account import OAuthAccount
import httpx

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

        # TODO:
        # Replace with Redis distributed lock if refresh concurrency grows.
        with SessionLocal() as new_db:
            # 1. Pessimistic lock on the DB row BEFORE calling Google API
            oauth_account = new_db.query(OAuthAccount).join(User).filter(
                User.organization_id == self.auth_context.organization_id,
                User.role.in_(["Owner", "Admin"]),
                OAuthAccount.provider.in_(["gbp", "google"])
            ).with_for_update().first()

            if not oauth_account:
                raise Exception("Google credentials expired or invalid. OAuthAccount not found in database.")

            # 2. Check if another concurrent task already completed the refresh
            now = datetime.datetime.now(timezone.utc)
            db_expiry = oauth_account.expires_at
            if db_expiry and db_expiry.tzinfo is None:
                db_expiry = db_expiry.replace(tzinfo=timezone.utc)

            if db_expiry and db_expiry > now + datetime.timedelta(minutes=5):
                # Success! Another task refreshed it. Load the newly persisted token.
                decrypted_access = decrypt_token(oauth_account.access_token)
                decrypted_refresh = decrypt_token(oauth_account.refresh_token) if oauth_account.refresh_token else None
                
                self.auth_context.access_token = decrypted_access
                if decrypted_refresh:
                    self.auth_context.refresh_token = decrypted_refresh
                self.auth_context.expires_at = db_expiry
                return

            # 3. We are the first: proceed to refresh via Google
            refresh_token = decrypt_token(oauth_account.refresh_token) if oauth_account.refresh_token else self.auth_context.refresh_token
            if not refresh_token:
                raise Exception("Google credentials expired or invalid. Refresh token missing. Re-authentication required.")

            # Sandbox / Mock Token handling
            if "mock_refresh_token" in refresh_token:
                new_access_token = "mock_access_token_refreshed_" + str(int(datetime.datetime.now(timezone.utc).timestamp()))
                expires_in = 3600
                new_refresh_token = refresh_token
            else:
                url = "https://oauth2.googleapis.com/token"
                data = {
                    "refresh_token": refresh_token,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "grant_type": "refresh_token"
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, data=data)
                    
                if response.status_code != 200:
                    raise Exception(f"Failed to refresh token: {response.text}")
                    
                token_data = response.json()
                new_access_token = token_data["access_token"]
                new_refresh_token = token_data.get("refresh_token", refresh_token)
                expires_in = token_data.get("expires_in", 3600)

            new_expiry = datetime.datetime.now(timezone.utc) + datetime.timedelta(seconds=expires_in)

            # 4. Save and release lock
            oauth_account.provider = "gbp"
            oauth_account.access_token = encrypt_token(new_access_token)
            if new_refresh_token:
                oauth_account.refresh_token = encrypt_token(new_refresh_token)
            oauth_account.expires_at = new_expiry
            new_db.commit()

            # 5. Sync in-memory context
            self.auth_context.access_token = new_access_token
            if new_refresh_token:
                self.auth_context.refresh_token = new_refresh_token
            self.auth_context.expires_at = new_expiry
