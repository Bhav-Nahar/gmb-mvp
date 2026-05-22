from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.providers.base.provider import BaseProvider
from app.providers.base.models import LocationModel, ReviewModel, ReviewReplyModel, PostModel
from app.providers.base.auth import AuthContext
from app.core.config import settings
from app.core.gbp_client import http_request_with_retry
from .auth import GBPAuthManager
from .client import GBPAsyncClient
from .schemas import GBPLocationRaw, GBPReviewRaw
from .mapper import GBPLocationMapper, GBPReviewMapper
import datetime

class GBPProvider(BaseProvider):
    provider_name = "gbp"

    @classmethod
    def get_oauth_url(cls, state: str) -> str:
        base_url = "https://accounts.google.com/o/oauth2/v2/auth"
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/business.manage",
            "access_type": "offline",
            "prompt": "consent",
            "state": state
        }
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{base_url}?{query_string}"

    @classmethod
    def exchange_code_for_tokens(cls, code: str) -> Dict[str, Any]:
        if "YOUR_GOOGLE_CLIENT_ID" in settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            print("WARNING: Google Client Credentials are placeholders. Using Sandbox Mock Tokens.")
            return {
                "access_token": "mock_access_token_" + code[:10],
                "refresh_token": "mock_refresh_token_xyz123abc",
                "expires_in": 3600,
                "email": "sandbox-user@example.com"
            }

        url = "https://oauth2.googleapis.com/token"
        data = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        
        response = http_request_with_retry("POST", url, data=data)
        if response.status_code != 200:
            raise Exception(f"Failed to exchange code: {response.text}")
        
        tokens = response.json()
        
        # Fetch user email using access token
        user_info_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        user_response = http_request_with_retry("GET", user_info_url, headers=headers)
        email = None
        if user_response.status_code == 200:
            email = user_response.json().get("email")
            
        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "expires_in": tokens["expires_in"],
            "email": email or "connected-account@google.com"
        }

    def __init__(self, auth_context: AuthContext, db: Session):
        self.auth_context = auth_context
        self.db = db
        self._auth = GBPAuthManager(auth_context, db)

    async def get_locations(self) -> List[LocationModel]:
        # Validate/refresh token
        access_token = await self._auth.get_valid_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Sandbox logic if using mock tokens
        if "mock_access_token" in access_token:
            mock_raw_1 = GBPLocationRaw(
                name="locations/mock-loc-1",
                title="Sleek Coffee Roasters",
                categories={"primaryCategory": {"displayName": "Coffee Shop"}},
                storefrontAddress={"addressLines": ["123 Espresso Way"], "locality": "Seattle", "administrativeArea": "WA"},
                phoneNumbers={"primaryPhone": "+1 206 555 0199"},
                websiteUri="https://sleekcoffeeroasters.com",
                rating=4.8,
                reviewCount=124
            )
            mock_raw_2 = GBPLocationRaw(
                name="locations/mock-loc-2",
                title="Zenith Fitness Studio",
                categories={"primaryCategory": {"displayName": "Gym"}},
                storefrontAddress={"addressLines": ["456 Pilates Blvd"], "locality": "Austin", "administrativeArea": "TX"},
                phoneNumbers={"primaryPhone": "+1 512 555 0288"},
                websiteUri="https://zenithfitness.com",
                rating=4.5,
                reviewCount=89
            )
            return [GBPLocationMapper.to_model(mock_raw_1), GBPLocationMapper.to_model(mock_raw_2)]

        all_locations = []
        
        async with GBPAsyncClient(self.auth_context.organization_id) as client:
            # 1. Fetch accounts
            accounts_url = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
            acc_resp = await client.request("GET", accounts_url, headers=headers)
            accounts_data = acc_resp.json()
            accounts = accounts_data.get("accounts", [])
            
            for account in accounts:
                account_name = account["name"]
                
                # 2. Fetch locations with pagination
                next_page_token = None
                while True:
                    locations_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{account_name}/locations"
                    params = {
                        "readMask": "name,title,categories,storefrontAddress,phoneNumbers,websiteUri,metadata",
                        "pageSize": 100
                    }
                    if next_page_token:
                        params["pageToken"] = next_page_token
                        
                    loc_resp = await client.request("GET", locations_url, headers=headers, params=params)
                    data = loc_resp.json()
                    batch = data.get("locations", [])
                    
                    for loc_dict in batch:
                        loc_name = loc_dict["name"]
                        
                        # 3. Fetch summary ratings (this endpoint doesn't require pagination for summaries)
                        metadata = loc_dict.get("metadata", {})
                        
                        # Check Verification Status: Only attempt to fetch reviews if the location metadata shows it is verified.
                        is_verified = metadata.get("hasVoiceOfMerchant", False) or metadata.get("isVerified", False)
                        
                        if is_verified:
                            reviews_url = f"https://mybusiness.googleapis.com/v4/{account_name}/{loc_name}/reviews"
                            try:
                                rev_resp = await client.request("GET", reviews_url, headers=headers)
                                rev_data = rev_resp.json()
                                loc_dict["rating"] = rev_data.get("averageRating")
                                loc_dict["reviewCount"] = rev_data.get("totalReviewCount")
                            except Exception as e:
                                import logging
                                logging.error(f"Failed to fetch reviews for {loc_name}. Error: {str(e)}")
                                continue  # Log the error but continue syncing other locations
                            
                        raw_model = GBPLocationRaw(**loc_dict)
                        all_locations.append(GBPLocationMapper.to_model(raw_model))
                    
                    next_page_token = data.get("nextPageToken")
                    if not next_page_token:
                        break
                        
        return all_locations

    async def get_reviews(self, google_location_id: str) -> List[ReviewModel]:
        # google_location_id is like "locations/12345"
        access_token = await self._auth.get_valid_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Sandbox mode
        if "mock_access_token" in access_token:
            # Return some mock reviews
            import uuid
            mock_reviews = [
                GBPReviewRaw(
                    reviewId=f"mock-rev-{i}",
                    reviewer={
                        "displayName": name,
                        "profilePhotoUrl": f"https://lh3.googleusercontent.com/a-/mock-photo-{i}"
                    },
                    starRating=rating,
                    comment=comment,
                    reviewReply={"comment": reply} if reply else None,
                    createTime=(datetime.datetime.utcnow() - datetime.timedelta(days=i)).isoformat() + "Z"
                )
                for i, (name, rating, comment, reply) in enumerate([
                    ("Jane Doe", "FIVE", "Excellent service and cozy atmosphere!", "Thank you for the support Jane!"),
                    ("John Smith", "FOUR", "Good coffee but service was a bit slow.", None),
                    ("Alice Brown", "THREE", "Average experience.", None),
                    ("Bob Martin", "FIVE", "Absolutely loved it! Best place in town.", "We are thrilled Bob!"),
                    ("Charlie Green", "ONE", "Disappointing experience. Not clean.", None)
                ], 1)
            ]
            return [GBPReviewMapper.to_model(raw, google_location_id) for raw in mock_reviews]
            
        all_reviews = []
        async with GBPAsyncClient(self.auth_context.organization_id) as client:
            accounts_url = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
            acc_resp = await client.request("GET", accounts_url, headers=headers)
            accounts = acc_resp.json().get("accounts", [])
            
            for account in accounts:
                account_name = account["name"]
                next_page_token = None
                
                while True:
                    url = f"https://mybusiness.googleapis.com/v4/{account_name}/{google_location_id}/reviews"
                    params = {"pageSize": 50}
                    if next_page_token:
                        params["pageToken"] = next_page_token
                        
                    try:
                        resp = await client.request("GET", url, headers=headers, params=params)
                        data = resp.json()
                        batch = data.get("reviews", [])
                        
                        for rev_dict in batch:
                            raw = GBPReviewRaw(**rev_dict)
                            model = GBPReviewMapper.to_model(raw, google_location_id)
                            model.provider_metadata = rev_dict
                            all_reviews.append(model)
                            
                        next_page_token = data.get("nextPageToken")
                        if not next_page_token:
                            break
                    except Exception as e:
                        import logging
                        logging.error(f"Failed to fetch reviews for {google_location_id} in account {account_name}. Error: {str(e)}")
                        break
                        
        return all_reviews

    async def reply_to_review(self, google_location_id: str, review_id: str, reply_text: str) -> ReviewReplyModel:
        access_token = await self._auth.get_valid_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Sandbox mode
        if "mock_access_token" in access_token:
            return ReviewReplyModel(
                review_id=review_id,
                reply_text=reply_text,
                created_at=datetime.datetime.utcnow(),
                provider="gbp"
            )
            
        async with GBPAsyncClient(self.auth_context.organization_id) as client:
            accounts_url = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
            acc_resp = await client.request("GET", accounts_url, headers=headers)
            accounts = acc_resp.json().get("accounts", [])
            
            if not accounts:
                raise Exception("No GBP accounts found")
            account_name = accounts[0]["name"]
            
            url = f"https://mybusiness.googleapis.com/v4/{account_name}/{google_location_id}/reviews/{review_id}/reply"
            payload = {"comment": reply_text}
            resp = await client.request("PUT", url, headers=headers, json=payload)
            
            return ReviewReplyModel(
                review_id=review_id,
                reply_text=reply_text,
                created_at=datetime.datetime.utcnow(),
                provider="gbp"
            )

    async def reply_review(self, review_id: str, reply_text: str) -> ReviewReplyModel:
        from app.models.review import Review
        from app.models.location import Location
        
        review = self.db.query(Review).filter(Review.provider_review_id == review_id).first()
        if not review:
            raise Exception(f"Review {review_id} not found in database to resolve location")
            
        location = self.db.query(Location).filter(Location.id == review.location_id).first()
        if not location:
            raise Exception(f"Location not found for review {review_id}")
            
        return await self.reply_to_review(location.google_location_id, review_id, reply_text)

    async def create_post(self, location_id: str, payload: Dict[str, Any]) -> PostModel:
        # Implementation for creating a post
        return PostModel(
            id="mock-post-1",
            location_id=location_id,
            title="Mock Post",
            body="Mock body",
            state="PUBLISHED",
            provider="gbp"
        )
