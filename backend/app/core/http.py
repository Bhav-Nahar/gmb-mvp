import time
import httpx


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

    # Fallback to raise if unreachable
    raise httpx.RequestError("Max retries exceeded on connection errors or rate limits")
