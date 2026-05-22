from typing import Optional

class ProviderError(Exception):
    """Base exception for all provider-related errors."""
    def __init__(self, provider: str, status_code: int, detail: str, retry_after: Optional[int] = None):
        self.provider = provider
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after
        super().__init__(f"[{provider}] {status_code}: {detail}")

class ProviderAuthError(ProviderError):
    """Raised when authentication fails (401, 403, invalid_grant)."""
    pass

class ProviderRateLimitError(ProviderError):
    """Raised when the provider rate limit is exceeded (429)."""
    pass

class ProviderValidationError(ProviderError):
    """Raised when the provider rejects the request as malformed (400)."""
    pass

class ProviderTemporaryError(ProviderError):
    """Raised on 500, 503, or network timeouts."""
    pass
