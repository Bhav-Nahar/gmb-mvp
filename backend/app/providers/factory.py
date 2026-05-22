from sqlalchemy.orm import Session
from app.providers.base.provider import BaseProvider
from app.providers.base.auth import AuthContext
from app.providers.registry import ProviderRegistry
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.core.security import decrypt_token

# Make sure all providers are imported so they register themselves!
from app.providers.gbp.provider import GBPProvider

# Register GBP explicitly if decorator isn't used
ProviderRegistry.register(GBPProvider)

class ProviderFactory:
    @staticmethod
    def get_oauth_url(provider_name: str, state: str) -> str:
        provider_class = ProviderRegistry.get(provider_name)
        return provider_class.get_oauth_url(state)

    @staticmethod
    def exchange_code_for_tokens(provider_name: str, code: str) -> dict:
        provider_class = ProviderRegistry.get(provider_name)
        return provider_class.exchange_code_for_tokens(code)

    @staticmethod
    def get_provider(provider_name: str, organization_id: int, db: Session) -> BaseProvider:
        """
        Looks up the OAuth credentials for the organization, decrypts them,
        constructs the AuthContext, and returns the instantiated provider.
        """
        # We need the OAuth account for this organization.
        # Assuming one connected account per organization for simplicity (e.g., via the Admin).
        oauth_account = db.query(OAuthAccount).join(User).filter(User.organization_id == organization_id).first()
        
        if not oauth_account:
            raise Exception(f"No connected OAuth account found for organization {organization_id}")
            
        try:
            access_token = decrypt_token(oauth_account.access_token)
        except Exception:
            raise Exception("Failed to decrypt access token.")
            
        refresh_token = None
        if oauth_account.refresh_token:
            try:
                refresh_token = decrypt_token(oauth_account.refresh_token)
            except Exception:
                pass
                
        auth_context = AuthContext(
            organization_id=organization_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=oauth_account.expires_at
        )
        
        provider_class = ProviderRegistry.get(provider_name)
        return provider_class(auth_context=auth_context, db=db)
