import asyncio
import httpx
from typing import Optional, Any
from .exceptions import map_google_error
import time

class GBPAsyncClient:
    def __init__(self, organization_id: int):
        self.organization_id = organization_id
        self.client = None
        
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def request(self, method: str, url: str, headers: Optional[dict] = None, **kwargs) -> httpx.Response:
        base_delay = 1.0
        max_retries = 5
        
        for attempt in range(max_retries):
            start_time = time.time()
            try:
                response = await self.client.request(method, url, headers=headers, **kwargs)
                latency_ms = int((time.time() - start_time) * 1000)
                
                print(f"[GBPClient] org={self.organization_id} method={method} url={url} status={response.status_code} latency={latency_ms}ms attempt={attempt+1}")
                
                if response.status_code == 429:
                    if attempt == max_retries - 1:
                        raise map_google_error(response.status_code, response.text, response.headers)
                    delay = base_delay * (2 ** attempt)
                    print(f"[GBPClient] Rate limited. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                    
                if response.status_code >= 400:
                    raise map_google_error(response.status_code, response.text, response.headers)
                    
                return response
                
            except httpx.RequestError as exc:
                latency_ms = int((time.time() - start_time) * 1000)
                print(f"[GBPClient] org={self.organization_id} network error url={url} exc={str(exc)} latency={latency_ms}ms attempt={attempt+1}")
                if attempt == max_retries - 1:
                    raise map_google_error(503, str(exc))
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
        
        raise map_google_error(500, "Max retries exceeded")
