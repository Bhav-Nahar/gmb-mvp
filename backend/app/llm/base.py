from abc import ABC, abstractmethod

class BaseLLMProvider(ABC):
    @abstractmethod
    async def complete(self, system_prompt: str, user_message: str, max_tokens: int = 200, temperature: float = 0.7) -> str:
        """Send a prompt and return the completion text."""
        pass

    async def aclose(self) -> None:
        """Release the HTTP pool. Every caller builds its own provider (auto-reply
        builds one per review), so without this each one leaks its connections until
        garbage collection — which in a Celery task happens after asyncio.run() has
        closed the loop, and httpx then logs a "Event loop is closed" traceback for
        every batch. Callers use try/finally, so this must also run on the error path."""
        client = getattr(self, "client", None)
        if client is not None:
            await client.close()
