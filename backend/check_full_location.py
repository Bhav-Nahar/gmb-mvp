
from app.db.session import SessionLocal
from app.models.location import Location
from app.providers.factory import ProviderFactory
import asyncio
import json

async def run():
    db = SessionLocal()
    try:
        loc = db.query(Location).filter(Location.id == 110).first()
        from app.providers.gbp.auth import GBPAuthManager
        from app.providers.base.auth import AuthContext
        from app.core.security import decrypt_token
        from app.models.oauth_account import OAuthAccount
        from app.models.user import User

        oauth_account = db.query(OAuthAccount).join(User).filter(
            User.organization_id == loc.organization_id,
            User.role.in_(["Owner", "Admin"]),
            OAuthAccount.provider.in_(["gbp", "google"])
        ).first()

        auth_context = AuthContext(
            organization_id=loc.organization_id,
            access_token=decrypt_token(oauth_account.access_token),
            refresh_token=decrypt_token(oauth_account.refresh_token) if oauth_account.refresh_token else None,
            expires_at=oauth_account.expires_at
        )
        auth_manager = GBPAuthManager(auth_context, db)
        access_token = await auth_manager.get_valid_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{loc.google_location_id}"
        
        from app.providers.gbp.client import GBPAsyncClient
        async with GBPAsyncClient(loc.organization_id) as client:
            resp = await client.request("GET", url, headers=headers, params={"readMask": "name,title,categories"})
            print("FULL LOCATION DATA:")
            print(json.dumps(resp.json(), indent=2))
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run())
