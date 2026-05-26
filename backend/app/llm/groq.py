from openai import AsyncOpenAI
from app.core.config import settings
from app.llm.base import BaseLLMProvider
from app.llm.exceptions import LLMProviderError

class GroqLLMProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY or "dummy_key_to_prevent_crash",
            base_url="https://api.groq.com/openai/v1"
        )

    async def complete(self, system_prompt: str, user_message: str, max_tokens: int = 200, temperature: float = 0.7) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=15.0
            )
            
            if not response.choices or not response.choices[0].message.content:
                raise LLMProviderError("No response content from Groq provider.")
            
            result = response.choices[0].message.content
            return result.strip()
        except Exception as e:
            raise LLMProviderError(f"Groq AI service temporarily unavailable: {str(e)}")
