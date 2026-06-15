from typing import List, Dict, Any, Optional
import time
import logging
import asyncio
from sqlalchemy.orm import Session
from app.providers.base.provider import BaseProvider
from app.providers.base.models import LocationModel, ReviewModel, ReviewReplyModel, PostModel, DailyInsightMetric, KeywordInsightMetric, MediaItemModel, PostInsightMetric
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

logger = logging.getLogger(__name__)

# Module-level account ID cache: maps google_location_id -> (account_name, resolved_at_epoch)
_account_id_cache: Dict[str, tuple] = {}
_ACCOUNT_ID_CACHE_TTL = 3600  # seconds

# Module-level set of already-warned unmapped metric names
_warned_metrics: set = set()

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

    async def _resolve_account_id(self, google_location_id: str, access_token: str) -> str:
        from app.models.location import Location

        # Check module-level TTL cache first
        cached = _account_id_cache.get(google_location_id)
        if cached:
            account_name, resolved_at = cached
            if time.time() - resolved_at < _ACCOUNT_ID_CACHE_TTL:
                return account_name
            else:
                del _account_id_cache[google_location_id]

        loc_record = self.db.query(Location).filter(
            Location.google_location_id == google_location_id,
            Location.organization_id == self.auth_context.organization_id
        ).first()

        target_account_name = loc_record.google_account_id if loc_record else None

        if not target_account_name:
            async with GBPAsyncClient(self.auth_context.organization_id) as client:
                accounts_url = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
                headers = {"Authorization": f"Bearer {access_token}"}
                acc_resp = await client.request("GET", accounts_url, headers=headers)
                accounts = acc_resp.json().get("accounts", [])
                
                discovery_errors = []
                for account in accounts:
                    locations_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{account['name']}/locations"
                    next_loc_token = None
                    while True:
                        try:
                            params = {"readMask": "name", "pageSize": 100}
                            if next_loc_token:
                                params["pageToken"] = next_loc_token
                            loc_resp = await client.request("GET", locations_url, headers=headers, params=params)
                            data = loc_resp.json()
                            batch = data.get("locations", [])
                            if any(loc.get("name") == google_location_id for loc in batch):
                                target_account_name = account["name"]
                                # Cache the discovered account name back to the database to bypass discovery in the future
                                if loc_record:
                                    loc_record.google_account_id = target_account_name
                                    self.db.commit()
                                break
                            
                            next_loc_token = data.get("nextPageToken")
                            if not next_loc_token:
                                break
                        except Exception as e:
                            logger.warning(f"Error fetching locations during discovery for account {account['name']}: {str(e)}")
                            discovery_errors.append(e)
                            break
                    if target_account_name:
                        break

            if not target_account_name:
                if discovery_errors:
                    raise ProviderAPIError(
                        provider_name=self.provider_name,
                        status_code=502,
                        message=str(discovery_errors[0])
                    )
                raise ProviderAPIError(
                    provider_name=self.provider_name,
                    status_code=404,
                    message=f"Location {google_location_id} could not be found in any connected Google accounts. Please re-sync locations."
                )

        # Store resolved account in module-level cache
        _account_id_cache[google_location_id] = (target_account_name, time.time())
        return target_account_name

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
                reviewCount=124,
                locationState={"isVerified": True, "isSuspended": False, "isDuplicate": False}
            )
            mock_raw_2 = GBPLocationRaw(
                name="locations/mock-loc-2",
                title="Zenith Fitness Studio",
                categories={"primaryCategory": {"displayName": "Gym"}},
                storefrontAddress={"addressLines": ["456 Pilates Blvd"], "locality": "Austin", "administrativeArea": "TX"},
                phoneNumbers={"primaryPhone": "+1 512 555 0288"},
                websiteUri="https://zenithfitness.com",
                rating=4.5,
                reviewCount=89,
                locationState={"isVerified": False, "isSuspended": False, "isDuplicate": False}
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
                        "readMask": (
                            "name,languageCode,storeCode,title,categories,storefrontAddress,"
                            "phoneNumbers,websiteUri,regularHours,specialHours,moreHours,"
                            "serviceArea,serviceItems,labels,openInfo,latlng,"
                            "adWordsLocationExtensions,relationshipData,profile,metadata"
                        ),
                        "pageSize": 100
                    }
                    if next_page_token:
                        params["pageToken"] = next_page_token
                        
                    loc_resp = await client.request("GET", locations_url, headers=headers, params=params)
                    data = loc_resp.json()
                    batch = data.get("locations", [])
                    
                    async def fetch_vom_state(loc_dict):
                        loc_name = loc_dict["name"]
                        try:
                            vom_url = f"https://mybusinessverifications.googleapis.com/v1/{loc_name}/VoiceOfMerchantState"
                            vom_resp = await client.request("GET", vom_url, headers=headers)
                            if vom_resp.status_code == 200:
                                vom_data = vom_resp.json()
                                is_verified = vom_data.get("hasVoiceOfMerchant", False)
                                is_duplicate = "resolveOwnershipConflict" in vom_data
                                is_suspended = None
                                
                                # Merge flags from location metadata if present
                                loc_metadata = loc_dict.get("metadata", {})
                                if loc_metadata.get("isSuspended") is True:
                                    is_suspended = True
                                elif loc_metadata.get("isSuspended") is False:
                                    is_suspended = False
                                    
                                if loc_metadata.get("isDuplicate") is True:
                                    is_duplicate = True
                                if loc_metadata.get("isVerified") is True:
                                    is_verified = True
                                    
                                loc_dict["locationState"] = {
                                    "isVerified": is_verified,
                                    "isSuspended": is_suspended,
                                    "isDuplicate": is_duplicate
                                }
                            else:
                                logger.warning(f"Failed to fetch VoiceOfMerchantState for {loc_name}: {vom_resp.status_code} {vom_resp.text}")
                        except Exception as e:
                            logger.error(f"Error fetching VoiceOfMerchantState for {loc_name}: {str(e)}")

                    if batch:
                        await asyncio.gather(*(fetch_vom_state(loc) for loc in batch))

                    for loc_dict in batch:
                        loc_name = loc_dict["name"]
                        try:
                            raw_model = GBPLocationRaw(**loc_dict)
                            all_locations.append(GBPLocationMapper.to_model(raw_model, account_name=account_name))
                        except Exception as e:
                            logger.error(f"Failed to map location {loc_name}: {str(e)}")
                            continue
                    
                    next_page_token = data.get("nextPageToken")
                    if not next_page_token:
                        break
                        
        return all_locations

    async def get_reviews(self, google_location_id: str, safe_cutoff_time: datetime.datetime = None) -> List[ReviewModel]:
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
            target_account_name = await self._resolve_account_id(google_location_id, access_token)
            # 3. Fetch reviews from the target account
            next_page_token = None
            stop_fetching = False
            # Note: Google My Business Reviews API remains on v4 (mybusiness.googleapis.com/v4)
            # because Google has not migrated review management resources to v1.
            # Reference: https://developers.google.com/my-business/reference/rest/v4/accounts.locations.reviews
            while True:
                url = f"https://mybusiness.googleapis.com/v4/{target_account_name}/{google_location_id}/reviews"
                params = {"pageSize": 50}
                if next_page_token:
                    params["pageToken"] = next_page_token
                    
                try:
                    resp = await client.request("GET", url, headers=headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    batch = data.get("reviews", [])
                    
                    for rev_dict in batch:
                        raw = GBPReviewRaw(**rev_dict)
                        model = GBPReviewMapper.to_model(raw, google_location_id)
                        model.provider_metadata = rev_dict
                        all_reviews.append(model)
                        
                        # Early exit based on safe_cutoff_time
                        rev_updated_at = model.updated_at or model.created_at
                        if safe_cutoff_time and rev_updated_at and rev_updated_at < safe_cutoff_time:
                            stop_fetching = True
                            
                    next_page_token = data.get("nextPageToken")
                    if not next_page_token or stop_fetching:
                        break
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error fetching reviews for {google_location_id} in account {target_account_name}: {e.response.status_code} {e.response.text}")
                    raise ProviderAPIError(
                        provider_name=self.provider_name,
                        status_code=e.response.status_code,
                        message=f"Failed to fetch reviews: {e.response.text}"
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch reviews for {google_location_id} in account {target_account_name}. Error: {str(e)}")
                    raise ProviderAPIError(
                        provider_name=self.provider_name,
                        status_code=500,
                        message=str(e)
                    )
                        
        return all_reviews

    async def reply_to_review(self, google_location_id: str, review_id: str, reply_text: str) -> ReviewReplyModel:
        access_token = await self._auth.get_valid_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Sandbox mode
        if "mock_access_token" in access_token:
            return ReviewReplyModel(
                review_id=review_id,
                reply_text=reply_text,
                created_at=datetime.datetime.now(timezone.utc),
                provider="gbp"
            )
            
        async with GBPAsyncClient(self.auth_context.organization_id) as client:
            target_account_name = await self._resolve_account_id(google_location_id, access_token)
            
            # Note: Google My Business Reviews API remains on v4 for reply management
            # because Google has not migrated review reply resources to v1.
            # Reference: https://developers.google.com/my-business/reference/rest/v4/accounts.locations.reviews
            url = f"https://mybusiness.googleapis.com/v4/{target_account_name}/{google_location_id}/reviews/{review_id}/reply"
            payload = {"comment": reply_text}
            resp = await client.request("PUT", url, headers=headers, json=payload)
            
            return ReviewReplyModel(
                review_id=review_id,
                reply_text=reply_text,
                created_at=datetime.datetime.now(timezone.utc),
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
        account_id = await self._resolve_account_id(location_id, access_token)

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
                    if metric_name not in _warned_metrics:
                        _warned_metrics.add(metric_name)
                        logger.warning(f"Unmapped metric '{metric_name}' received from GBP Performance API.")
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
                        logger.error(f"Error parsing dated value {dv} for metric {metric_name}: {str(ex)}")
                        continue
                        
        return sorted(day_data.values(), key=lambda x: x.date)

    async def get_search_keyword_insights(self, location_id: str, start_date: datetime.date, end_date: datetime.date, account_id: Optional[str] = None) -> List[KeywordInsightMetric]:
        """
        Fetch monthly search keyword impressions from GBP Performance API.
        Uses GET locations.searchkeywords.impressions.monthly.list
        """
        access_token = await self._auth.get_valid_token()
        
        if "mock_access_token" in access_token:
            import random
            insights = []
            
            curr_date = start_date.replace(day=1)
            while curr_date <= end_date.replace(day=1):
                mock_keywords = [
                    ("coffee near me", random.randint(100, 500)),
                    ("best espresso", random.randint(50, 200)),
                    ("cafe with wifi", random.randint(20, 100)),
                    ("latte art", random.randint(10, 50))
                ]
                for kw, imp in mock_keywords:
                    insights.append(KeywordInsightMetric(
                        keyword=kw, impressions=imp, period_start=curr_date
                    ))
                
                # Move to next month
                next_month = curr_date.month % 12 + 1
                next_year = curr_date.year + (1 if curr_date.month == 12 else 0)
                curr_date = curr_date.replace(year=next_year, month=next_month, day=1)
                
            return insights

        headers = {
            "Authorization": f"Bearer {access_token}"
        }

        loc_path = location_id.strip("/")
        if not loc_path.startswith("locations/"):
            loc_path = f"locations/{loc_path}"

        full_path = loc_path
        if account_id:
            acc_clean = account_id.strip("/")
            if not acc_clean.startswith("accounts/"):
                acc_clean = f"accounts/{acc_clean}"
            full_path = f"{acc_clean}/{loc_path}"

        # The GBP monthly search-keywords endpoint aggregates impressions over the
        # *entire* requested monthlyRange and does NOT break results down by month.
        # To get a true per-month series we request one month at a time and stamp
        # each keyword with that month's period_start. (Requesting a multi-month
        # range in one call and labelling everything start_date's month silently
        # collapses/overwrites months under the UPSERT key.)
        def _month_starts(s, e):
            cur = s.replace(day=1)
            last = e.replace(day=1)
            months = []
            while cur <= last:
                months.append(cur)
                if cur.month == 12:
                    cur = cur.replace(year=cur.year + 1, month=1)
                else:
                    cur = cur.replace(month=cur.month + 1)
            return months

        async def _fetch_month(target_path, month_start):
            results = []
            page_token = None
            url = f"https://businessprofileperformance.googleapis.com/v1/{target_path}/searchkeywords/impressions/monthly"
            while True:
                params = {
                    "monthlyRange.startMonth.year": month_start.year,
                    "monthlyRange.startMonth.month": month_start.month,
                    "monthlyRange.endMonth.year": month_start.year,
                    "monthlyRange.endMonth.month": month_start.month,
                    "pageSize": 100,
                }
                if page_token:
                    params["pageToken"] = page_token
                async with GBPAsyncClient(self.auth_context.organization_id) as client:
                    resp = await client.request("GET", url, headers=headers, params=params)
                if resp.status_code != 200:
                    logger.error(f"GBP Keyword Performance API call failed: {resp.status_code} - {resp.text}")
                    raise ProviderAPIError(self.provider_name, resp.status_code, resp.text)
                data = resp.json()
                for item in data.get("searchKeywordsCounts", []):
                    kw = item.get("searchKeyword")
                    val_obj = item.get("insightsValue", {}) or {}
                    # Google returns a `threshold` instead of an exact `value` for
                    # very low-volume keywords; fall back to it as a lower bound.
                    val = val_obj.get("value")
                    if val is None:
                        val = val_obj.get("threshold")
                    if kw and val is not None:
                        results.append(KeywordInsightMetric(
                            keyword=kw,
                            impressions=int(val),
                            period_start=month_start,
                        ))
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
            return results

        insights = []
        for month_start in _month_starts(start_date, end_date):
            try:
                insights.extend(await _fetch_month(full_path, month_start))
            except ProviderError as e:
                if getattr(e, "status_code", None) == 404 and account_id and full_path != loc_path:
                    logger.warning(f"Keyword Performance API full path failed (404). Retrying with short path: {loc_path}")
                    insights.extend(await _fetch_month(loc_path, month_start))
                elif getattr(e, "status_code", None) == 404:
                    raise ProviderAPIError(
                        self.provider_name, 404,
                        f"Performance API returned 404. Ensure 'Business Profile Performance API' is enabled and location {loc_path} is verified."
                    )
                else:
                    raise
            except ProviderAPIError:
                raise
            except Exception as e:
                logger.error(f"Network error during keyword insights fetch: {str(e)}")
                raise ProviderAPIError(self.provider_name, 500, f"Network error during keyword insights fetch: {str(e)}")

        return insights

    async def get_location(self, google_location_id: str) -> Dict[str, Any]:
        access_token = await self._auth.get_valid_token()
        
        if "mock_access_token" in access_token:
            return {"name": google_location_id, "categories": {"primaryCategory": {"name": "categories/gcid:mock_category"}}}
            
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{google_location_id}"
        params = {"readMask": "name,title,categories,metadata"}
        async with GBPAsyncClient(self.auth_context.organization_id) as client:
            resp = await client.request("GET", url, headers=headers, params=params)
            if resp.status_code != 200:
                raise httpx.HTTPStatusError(f"Failed to fetch location {google_location_id}: {resp.text}", request=resp.request, response=resp)
            return resp.json()

    async def get_location_attributes(self, google_location_id: str) -> Dict[str, Any]:
        access_token = await self._auth.get_valid_token()
        
        if "mock_access_token" in access_token:
            return {"name": f"{google_location_id}/attributes", "attributes": []}
            
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{google_location_id}/attributes"
        async with GBPAsyncClient(self.auth_context.organization_id) as client:
            resp = await client.request("GET", url, headers=headers)
            # Attributes API might return 404 if no attributes are set, but usually returns 200 with empty list.
            if resp.status_code not in [200, 404]:
                raise httpx.HTTPStatusError(f"Failed to fetch attributes for {google_location_id}: {resp.text}", request=resp.request, response=resp)
            if resp.status_code == 404:
                return {"name": f"{google_location_id}/attributes", "attributes": []}
            return resp.json()

    @staticmethod
    def _media_key_from_name(name: Optional[str]) -> Optional[str]:
        # Media resource name is accounts/{a}/locations/{l}/media/{mediaKey}
        if not name:
            return None
        return name.split("/media/")[-1] if "/media/" in name else name

    async def create_location_media(self, location_id: str, source_url: str, category: str = "ADDITIONAL", media_format: str = "PHOTO") -> MediaItemModel:
        # Note: Media management remains on the legacy v4 surface
        # (mybusiness.googleapis.com/v4) — like reviews and local posts —
        # because Google has not migrated media resources to v1.
        access_token = await self._auth.get_valid_token()

        if "mock_access_token" in access_token:
            mock_name = f"{location_id}/media/mock-{int(datetime.datetime.now(timezone.utc).timestamp())}"
            return MediaItemModel(
                resource_name=mock_name,
                media_key=self._media_key_from_name(mock_name),
                category=category,
                source_url=source_url,
                view_count=0,
                provider="gbp",
            )

        account_id = await self._resolve_account_id(location_id, access_token)
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://mybusiness.googleapis.com/v4/{account_id}/{location_id}/media"
        payload = {
            "mediaFormat": media_format,
            "sourceUrl": source_url,
            "locationAssociation": {"category": category},
        }

        async with GBPAsyncClient(self.auth_context.organization_id) as client:
            resp = await client.request("POST", url, headers=headers, json=payload)

        if resp.status_code not in [200, 201]:
            raise httpx.HTTPStatusError(
                message=f"Google API media create failed with status {resp.status_code}: {resp.text}",
                request=resp.request,
                response=resp,
            )

        data = resp.json()
        name = data.get("name")
        return MediaItemModel(
            resource_name=name,
            media_key=self._media_key_from_name(name),
            category=(data.get("locationAssociation", {}) or {}).get("category", category),
            media_format=data.get("mediaFormat") or media_format,
            source_url=source_url,
            thumbnail_url=data.get("thumbnailUrl"),
            view_count=(data.get("insights", {}) or {}).get("viewCount"),
            provider="gbp",
            provider_metadata=data,
        )

    async def list_location_media(self, location_id: str) -> List[MediaItemModel]:
        access_token = await self._auth.get_valid_token()

        if "mock_access_token" in access_token:
            return []

        account_id = await self._resolve_account_id(location_id, access_token)
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://mybusiness.googleapis.com/v4/{account_id}/{location_id}/media"

        items: List[MediaItemModel] = []
        next_page_token = None
        async with GBPAsyncClient(self.auth_context.organization_id) as client:
            while True:
                params = {"pageSize": 100}
                if next_page_token:
                    params["pageToken"] = next_page_token
                resp = await client.request("GET", url, headers=headers, params=params)
                data = resp.json()
                for item in data.get("mediaItems", []):
                    name = item.get("name")
                    items.append(MediaItemModel(
                        resource_name=name,
                        media_key=self._media_key_from_name(name),
                        category=(item.get("locationAssociation", {}) or {}).get("category"),
                        media_format=item.get("mediaFormat") or "PHOTO",
                        source_url=item.get("sourceUrl") or item.get("googleUrl"),
                        thumbnail_url=item.get("thumbnailUrl"),
                        view_count=(item.get("insights", {}) or {}).get("viewCount"),
                        provider="gbp",
                        provider_metadata=item,
                    ))
                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break
        return items

    async def delete_location_media(self, location_id: str, media_key: str) -> bool:
        access_token = await self._auth.get_valid_token()

        if "mock_access_token" in access_token:
            return True

        account_id = await self._resolve_account_id(location_id, access_token)
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://mybusiness.googleapis.com/v4/{account_id}/{location_id}/media/{media_key}"

        async with GBPAsyncClient(self.auth_context.organization_id) as client:
            resp = await client.request("DELETE", url, headers=headers)

        # 200 (deleted) or 404 (already gone) are both acceptable end-states.
        if resp.status_code not in [200, 204, 404]:
            raise httpx.HTTPStatusError(
                message=f"Google API media delete failed with status {resp.status_code}: {resp.text}",
                request=resp.request,
                response=resp,
            )
        return True

    async def get_post_insights(self, location_id: str, post_names: List[str], start_date: datetime.date, end_date: datetime.date) -> List[PostInsightMetric]:
        # Local post insights via legacy v4 localPosts:reportInsights.
        access_token = await self._auth.get_valid_token()

        if "mock_access_token" in access_token:
            import random
            return [
                PostInsightMetric(
                    post_name=pn,
                    view_count=random.randint(20, 200),
                    cta_click_count=random.randint(0, 30),
                )
                for pn in post_names
            ]

        if not post_names:
            return []

        account_id = await self._resolve_account_id(location_id, access_token)
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        url = f"https://mybusiness.googleapis.com/v4/{account_id}/{location_id}/localPosts:reportInsights"

        # Map Google's metric enum -> our flat fields.
        VIEW_METRICS = {"LOCAL_POST_VIEWS_SEARCH"}
        CTA_METRICS = {"LOCAL_POST_ACTIONS_CALL_TO_ACTION"}

        payload = {
            "localPostNames": post_names,
            "basicRequest": {
                "metricRequests": [
                    {"metric": "LOCAL_POST_VIEWS_SEARCH"},
                    {"metric": "LOCAL_POST_ACTIONS_CALL_TO_ACTION"},
                ],
                "timeRange": {
                    "startTime": f"{start_date.isoformat()}T00:00:00Z",
                    "endTime": f"{end_date.isoformat()}T00:00:00Z",
                },
            },
        }

        async with GBPAsyncClient(self.auth_context.organization_id) as client:
            resp = await client.request("POST", url, headers=headers, json=payload)

        if resp.status_code != 200:
            raise ProviderAPIError(self.provider_name, resp.status_code, resp.text)

        data = resp.json()
        results: List[PostInsightMetric] = []
        for entry in data.get("localPostMetrics", []):
            post_name = entry.get("localPostName")
            views = 0
            ctas = 0
            for mv in entry.get("metricValues", []):
                metric = mv.get("metric")
                total = (mv.get("totalValue", {}) or {}).get("value", 0)
                try:
                    total = int(total)
                except (TypeError, ValueError):
                    total = 0
                if metric in VIEW_METRICS:
                    views += total
                elif metric in CTA_METRICS:
                    ctas += total
            results.append(PostInsightMetric(post_name=post_name, view_count=views, cta_click_count=ctas))
        return results
