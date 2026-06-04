from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.providers.base.provider import BaseProvider
from app.providers.base.models import LocationModel, ReviewModel, ReviewReplyModel, PostModel, DailyInsightMetric
from app.providers.base.exceptions import ProviderAPIError, ProviderError
from app.providers.base.auth import AuthContext
from app.core.config import settings
from app.core.gbp_client import http_request_with_retry
from .auth import GBPAuthManager
from .client import GBPAsyncClient
from .schemas import GBPLocationRaw, GBPReviewRaw
from .mapper import GBPLocationMapper, GBPReviewMapper
import datetime
from datetime import timezone
import httpx

class GBPProvider(BaseProvider):
    provider_name = "gbp"

    @classmethod
    def get_oauth_url(cls, state: str) -> str:
        base_url = "https://accounts.google.com/o/oauth2/v2/auth"
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/business.manage openid email profile",
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
                        "readMask": "name,title,categories,storefrontAddress,phoneNumbers,websiteUri,regularHours,profile,metadata",
                        "pageSize": 100
                    }
                    if next_page_token:
                        params["pageToken"] = next_page_token
                        
                    loc_resp = await client.request("GET", locations_url, headers=headers, params=params)
                    data = loc_resp.json()
                    batch = data.get("locations", [])
                    
                    for loc_dict in batch:
                        loc_name = loc_dict["name"]
                        
                        try:
                            raw_model = GBPLocationRaw(**loc_dict)
                            all_locations.append(GBPLocationMapper.to_model(raw_model, account_name=account_name))
                        except Exception as e:
                            import logging
                            logging.error(f"Failed to map location {loc_name}: {str(e)}")
                            continue
                    
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
            # 1. Try to find the account_name from the database first
            from app.models.location import Location
            loc_record = self.db.query(Location).filter(
                Location.google_location_id == google_location_id,
                Location.organization_id == self.auth_context.organization_id
            ).first()
            
            target_account_name = loc_record.google_account_id if loc_record else None
            
            # 2. If not in DB or if google_account_id is null, perform discovery
            if not target_account_name:
                accounts_url = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
                acc_resp = await client.request("GET", accounts_url, headers=headers)
                accounts = acc_resp.json().get("accounts", [])
                
                for account in accounts:
                    locations_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{account['name']}/locations"
                    try:
                        # We request with readMask=name and a larger pageSize to find it efficiently
                        loc_resp = await client.request("GET", locations_url, headers=headers, params={"readMask": "name", "pageSize": 100})
                        data = loc_resp.json()
                        batch = data.get("locations", [])
                        if any(loc.get("name") == google_location_id for loc in batch):
                            target_account_name = account["name"]
                            # Cache the discovered account name back to the database to bypass discovery in the future
                            if loc_record:
                                loc_record.google_account_id = target_account_name
                                self.db.commit()
                            break
                    except Exception:
                        continue
            
            if not target_account_name:
                raise Exception(f"Location {google_location_id} could not be found in any connected Google accounts. Please re-sync locations.")

            # 3. Fetch reviews from the target account
            next_page_token = None
            while True:
                url = f"https://mybusiness.googleapis.com/v4/{target_account_name}/{google_location_id}/reviews"
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
                    logging.error(f"Failed to fetch reviews for {google_location_id} in account {target_account_name}. Error: {str(e)}")
                    raise e
                        
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
        # Validate/refresh token (will raise PermanentAuthError if credentials are revoked)
        access_token = await self._auth.get_valid_token()
        
        # Sandbox mode
        if "mock_access_token" in access_token:
            return PostModel(
                id=f"simulated_gmb_post_{int(datetime.datetime.now(timezone.utc).timestamp())}",
                location_id=location_id,
                title="Mock Post",
                body=payload.get("summary", ""),
                state="PUBLISHED",
                provider="gbp"
            )

        # 1. Resolve Account ID from DB (Bug Fix: V4 requires accounts/{accId}/locations/{locId}/localPosts)
        from app.models.location import Location
        loc_record = self.db.query(Location).filter(
            Location.google_location_id == location_id,
            Location.organization_id == self.auth_context.organization_id
        ).first()
        
        account_id = loc_record.google_account_id if loc_record else None
        
        if not account_id:
            # Fallback discovery if not in DB
            async with GBPAsyncClient(self.auth_context.organization_id) as client:
                accounts_url = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
                acc_resp = await client.request("GET", accounts_url, headers={"Authorization": f"Bearer {access_token}"})
                accounts = acc_resp.json().get("accounts", [])
                for account in accounts:
                    account_id = account["name"]
                    break # Just use first for now if discovery is needed
        
        if not account_id:
             raise Exception(f"Could not resolve account ID for location {location_id}")

        # Google API: POST https://mybusiness.googleapis.com/v4/{account_id}/{location_id}/localPosts
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://mybusiness.googleapis.com/v4/{account_id}/{location_id}/localPosts"
        
        async with GBPAsyncClient(self.auth_context.organization_id) as client:
            resp = await client.request("POST", url, headers=headers, json=payload)
            
        if resp.status_code not in [200, 201]:
            # Raise exception containing raw text and status code so Celery backoff retry can parse it
            raise httpx.HTTPStatusError(
                message=f"Google API publish failed with status {resp.status_code}: {resp.text}",
                request=resp.request,
                response=resp
            )
            
        resp_data = resp.json()
        return PostModel(
            id=resp_data.get("name", f"gmb_post_{int(datetime.datetime.now(timezone.utc).timestamp())}"),
            location_id=location_id,
            title="GMB Post",
            body=payload.get("summary", ""),
            state="PUBLISHED",
            provider="gbp",
            provider_metadata=resp_data
        )

    async def patch_location(self, google_location_id: str, payload: Dict[str, Any], update_mask: str) -> Dict[str, Any]:
        access_token = await self._auth.get_valid_token()
        
        # Sandbox mode
        if "mock_access_token" in access_token:
            return {"name": google_location_id, "status": "simulated_success"}

        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{google_location_id}"
        
        async with GBPAsyncClient(self.auth_context.organization_id) as client:
            resp = await client.request(
                "PATCH", 
                url, 
                headers=headers, 
                json=payload, 
                params={"updateMask": update_mask}
            )
            
        if resp.status_code not in [200, 201]:
            raise httpx.HTTPStatusError(
                message=f"Google API patch failed with status {resp.status_code}: {resp.text}",
                request=resp.request,
                response=resp
            )
            
        return resp.json()

    async def get_insights(self, location_id: str, start_date: datetime.date, end_date: datetime.date, account_id: Optional[str] = None) -> List[DailyInsightMetric]:
        """
        Fetch performance metrics from Google Business Profile Performance API v1.
        Uses POST fetchMultiDailyMetricsTimeSeries.
        """
        from typing import Optional
        access_token = await self._auth.get_valid_token()
        
        expected_dates = []
        curr_date = start_date
        while curr_date <= end_date:
            expected_dates.append(curr_date)
            curr_date += datetime.timedelta(days=1)
            
        if "mock_access_token" in access_token:
            import random
            insights = []
            for dt in expected_dates:
                profile_views = random.randint(150, 450)
                search_views = int(profile_views * random.uniform(0.6, 0.8))
                map_views = profile_views - search_views
                phone_calls = random.randint(5, 25)
                website_clicks = random.randint(10, 50)
                direction_requests = random.randint(15, 60)
                search_queries_direct = int(search_views * random.uniform(0.25, 0.35))
                search_queries_indirect = int(search_views * random.uniform(0.50, 0.60))
                search_queries_chain = search_views - search_queries_direct - search_queries_indirect
                insights.append(DailyInsightMetric(
                    date=dt, search_views=search_views, map_views=map_views,
                    website_clicks=website_clicks, phone_calls=phone_calls,
                    direction_requests=direction_requests, search_queries_direct=search_queries_direct,
                    search_queries_indirect=search_queries_indirect, search_queries_chain=search_queries_chain
                ))
            return insights

        METRIC_COLUMN_MAP = {
            "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH": "search_views",
            "BUSINESS_IMPRESSIONS_MOBILE_SEARCH": "search_views",
            "BUSINESS_IMPRESSIONS_DESKTOP_MAPS": "map_views",
            "BUSINESS_IMPRESSIONS_MOBILE_MAPS": "map_views",
            "WEBSITE_CLICKS": "website_clicks",
            "CALL_CLICKS": "phone_calls",
            "BUSINESS_DIRECTION_REQUESTS": "direction_requests",
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        loc_path = location_id.strip("/")
        if not loc_path.startswith("locations/"):
            loc_path = f"locations/{loc_path}"

        # FALLBACK STRATEGY: Try full path then short path
        # 1. Full Path (accounts/ACC/locations/LOC)
        full_path = loc_path
        if account_id:
            acc_clean = account_id.strip("/")
            if not acc_clean.startswith("accounts/"):
                acc_clean = f"accounts/{acc_clean}"
            full_path = f"{acc_clean}/{loc_path}"

        import logging
        logger = logging.getLogger(__name__)

        params = []
        for metric in METRIC_COLUMN_MAP.keys():
            params.append(("dailyMetrics", metric))
        
        params.extend([
            ("dailyRange.startDate.year", str(start_date.year)),
            ("dailyRange.startDate.month", str(start_date.month)),
            ("dailyRange.startDate.day", str(start_date.day)),
            ("dailyRange.endDate.year", str(end_date.year)),
            ("dailyRange.endDate.month", str(end_date.month)),
            ("dailyRange.endDate.day", str(end_date.day)),
        ])

        async def _try_fetch(target_path):
            url = f"https://businessprofileperformance.googleapis.com/v1/{target_path}:fetchMultiDailyMetricsTimeSeries"
            logger.info(f"Attempting insights fetch via: {url}")
            async with GBPAsyncClient(self.auth_context.organization_id) as client:
                return await client.request("GET", url, headers=headers, params=params)

        try:
            try:
                resp = await _try_fetch(full_path)
            except ProviderError as e:
                if e.status_code == 404 and account_id:
                    logger.warning(f"Performance API full path failed (404) for {full_path}. Retrying with short path: {loc_path}")
                    resp = await _try_fetch(loc_path)
                else:
                    raise e
        except ProviderError as e:
            if e.status_code == 404:
                raise ProviderAPIError(
                    self.provider_name, 404, 
                    f"Performance API returned 404. Ensure 'Business Profile Performance API' is enabled and location {loc_path} is verified."
                )
            raise e
        except Exception as e:
            logger.error(f"Network error during insights fetch: {str(e)}")
            raise ProviderAPIError(self.provider_name, 500, f"Network error during insights fetch: {str(e)}")
            
        if resp.status_code != 200:
            logger.error(f"GBP Performance API call failed: {resp.status_code} - {resp.text}")
            raise ProviderAPIError(self.provider_name, resp.status_code, resp.text)
            
        resp_data = resp.json()
        day_data = {dt: DailyInsightMetric(date=dt) for dt in expected_dates}
        
        multi_series = resp_data.get("multiDailyMetricTimeSeries", [])
        for entry in multi_series:
            series_list = entry.get("dailyMetricTimeSeries", [])
            for ts in series_list:
                metric_name = ts.get("dailyMetric")
                col_name = METRIC_COLUMN_MAP.get(metric_name)
                
                if not col_name:
                    import logging
                    logging.warning(f"Unmapped metric '{metric_name}' received from GBP Performance API.")
                    continue
                    
                time_series = ts.get("timeSeries", {})
                dated_values = time_series.get("datedValues", [])
                
                for dv in dated_values:
                    d_dict = dv.get("date", {})
                    if not d_dict:
                        continue
                    try:
                        dt = datetime.date(d_dict.get("year"), d_dict.get("month"), d_dict.get("day"))
                        val = int(dv.get("value", 0))
                        
                        if dt in day_data:
                            # Accumulate metric values (handles desktop/mobile searches aggregation)
                            current_val = getattr(day_data[dt], col_name)
                            setattr(day_data[dt], col_name, current_val + val)
                    except Exception as ex:
                        import logging
                        logging.error(f"Error parsing dated value {dv} for metric {metric_name}: {str(ex)}")
                        continue
                        
        return sorted(day_data.values(), key=lambda x: x.date)

