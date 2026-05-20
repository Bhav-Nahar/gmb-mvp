import datetime
import time
import httpx
from typing import Dict, List, Any, Optional
from app.core.config import settings
from app.core.security import decrypt_token

def http_request_with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    """Send an HTTP request with exponential backoff on 429 Too Many Requests and network errors."""
    base_delay = 1.0
    max_retries = 5
    client = kwargs.pop("client", None)
    
    for attempt in range(max_retries):
        try:
            if client:
                resp = client.request(method, url, **kwargs)
            else:
                resp = httpx.request(method, url, **kwargs)
                
            if resp.status_code == 429:
                if attempt == max_retries - 1:
                    return resp
                delay = base_delay * (2 ** attempt)
                print(f"Rate limited (429) on {url}. Retrying in {delay:.2f} seconds (attempt {attempt + 1}/{max_retries})...")
                time.sleep(delay)
            else:
                return resp
        except httpx.RequestError as exc:
            if attempt == max_retries - 1:
                raise exc
            delay = base_delay * (2 ** attempt)
            print(f"Network error on {url}: {exc}. Retrying in {delay:.2f} seconds (attempt {attempt + 1}/{max_retries})...")
            time.sleep(delay)
    
    # Fallback to empty response or raise if unreachable
    raise httpx.RequestError("Max retries exceeded on connection errors or rate limits")

class GBPClient:
    def __init__(self, access_token: str, refresh_token: Optional[str] = None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=30.0
        )

    @staticmethod
    def get_oauth_url(state: str) -> str:
        """Generate Google OAuth login URL."""
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

    @staticmethod
    def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
        """Exchange authorization code for credentials."""
        # Standard OAuth Token exchange
        # If client credentials are placeholder, return a sandbox mock
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

    @staticmethod
    def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
        """Refresh Google Access Token."""
        if "mock_refresh_token" in refresh_token:
            return {
                "access_token": "mock_access_token_refreshed_" + datetime.datetime.now().strftime("%s"),
                "expires_in": 3600
            }

        url = "https://oauth2.googleapis.com/token"
        data = {
            "refresh_token": refresh_token,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token"
        }
        
        response = http_request_with_retry("POST", url, data=data)
        if response.status_code != 200:
            raise Exception(f"Failed to refresh token: {response.text}")
            
        return response.json()

    def fetch_locations(self) -> List[Dict[str, Any]]:
        """Fetch list of GBP locations."""
        # Sandbox logic if using mock tokens
        if "mock_access_token" in self.access_token:
            return [
                {
                    "name": "locations/mock-loc-1",
                    "title": "Sleek Coffee Roasters",
                    "categories": {"primaryCategory": {"displayName": "Coffee Shop"}},
                    "storefrontAddress": {"addressLines": ["123 Espresso Way"], "locality": "Seattle", "administrativeArea": "WA"},
                    "phoneNumbers": {"primaryPhone": "+1 206 555 0199"},
                    "websiteUri": "https://sleekcoffeeroasters.com"
                },
                {
                    "name": "locations/mock-loc-2",
                    "title": "Zenith Fitness Studio",
                    "categories": {"primaryCategory": {"displayName": "Gym"}},
                    "storefrontAddress": {"addressLines": ["456 Pilates Blvd"], "locality": "Austin", "administrativeArea": "TX"},
                    "phoneNumbers": {"primaryPhone": "+1 512 555 0288"},
                    "websiteUri": "https://zenithfitness.com"
                }
            ]

        # 1. Fetch Google Business Accounts
        accounts_url = "https://mybusinessbusinessinformation.googleapis.com/v1/accounts"
        acc_resp = http_request_with_retry("GET", accounts_url, client=self.client)
        if acc_resp.status_code != 200:
            raise Exception(f"Failed to fetch accounts: {acc_resp.text}")
            
        accounts_data = acc_resp.json()
        accounts = accounts_data.get("accounts", [])
        if not accounts:
            return []

        # Find first PERSONAL or LOCATION_GROUP account
        account_name = accounts[0]["name"]

        # 2. Fetch locations under this account
        locations_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{account_name}/locations"
        params = {
            "readMask": "name,title,categories,storefrontAddress,phoneNumbers,websiteUri"
        }
        loc_resp = http_request_with_retry("GET", locations_url, params=params, client=self.client)
        if loc_resp.status_code != 200:
            raise Exception(f"Failed to fetch locations: {loc_resp.text}")
            
        return loc_resp.json().get("locations", [])
