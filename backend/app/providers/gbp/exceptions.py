from typing import Optional, Dict, Any
import httpx
from app.providers.base.exceptions import (
    ProviderError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderValidationError,
    ProviderTemporaryError
)

def map_google_error(status_code: int, response_text: str, headers: Optional[httpx.Headers] = None) -> ProviderError:
    """Maps Google HTTP errors to base ProviderError types."""
    provider = "gbp"
    
    # Try parsing retry-after if available
    retry_after = None
    if headers and "Retry-After" in headers:
        try:
            retry_after = int(headers["Retry-After"])
        except ValueError:
            pass

    if status_code in (401, 403):
        return ProviderAuthError(provider, status_code, f"Authentication failed: {response_text}")
    elif status_code == 429:
        return ProviderRateLimitError(provider, status_code, f"Rate limit exceeded: {response_text}", retry_after=retry_after)
    elif status_code == 400:
        return ProviderValidationError(provider, status_code, f"Validation error: {response_text}")
    elif status_code in (500, 502, 503, 504):
        return ProviderTemporaryError(provider, status_code, f"Temporary Google API error: {response_text}", retry_after=retry_after)
    
    return ProviderError(provider, status_code, f"Unknown error: {response_text}")
