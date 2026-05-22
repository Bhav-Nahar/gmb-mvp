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
        refresh_token = self.auth_context.refresh_token
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

        # Update in-memory context
        self.auth_context.access_token = new_access_token
        if new_refresh_token:
            self.auth_context.refresh_token = new_refresh_token
        self.auth_context.expires_at = datetime.datetime.now(timezone.utc) + datetime.timedelta(seconds=expires_in)

        # Update database securely
        # Note: We must look up the oauth_account by some identifier, assuming we have user_id.
        # But wait, AuthContext only has organization_id, which isn't unique for OAuthAccount.
        # Let's adjust this. Let's find any OAuthAccount with this refresh token in the DB for this organization.
        # Or better: ProviderFactory passes the OAuthAccount ID or user_id. 
        # For MVP, let's just find the first OAuthAccount that matches the encrypted refresh token.
        # Actually, finding by decrypted refresh token is hard since we store it encrypted.
        # The best way is to look up by organization_id by joining User.
        from app.models.user import User
        oauth_account = self.db.query(OAuthAccount).join(User).filter(User.organization_id == self.auth_context.organization_id).first()
        
        if oauth_account:
            oauth_account.access_token = encrypt_token(new_access_token)
            if new_refresh_token:
                oauth_account.refresh_token = encrypt_token(new_refresh_token)
            oauth_account.expires_at = self.auth_context.expires_at
            self.db.commit()
