from abc import ABC, abstractmethod

class BaseLLMProvider(ABC):
    @abstractmethod
    async def complete(self, system_prompt: str, user_message: str, max_tokens: int = 200, temperature: float = 0.7) -> str:
        """Send a prompt and return the completion text."""
        pass
