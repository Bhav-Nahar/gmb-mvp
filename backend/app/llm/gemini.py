from openai import AsyncOpenAI
from app.core.config import settings
from app.llm.base import BaseLLMProvider
from app.llm.exceptions import LLMProviderError

class GeminiLLMProvider(BaseLLMProvider):
    # ponytail: Gemini speaks OpenAI's API at its compat endpoint, so this is the
    # groq provider with a different base_url + key. No new SDK.
    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.LLM_MODEL
        self.client = AsyncOpenAI(
            api_key=settings.GEMINI_API_KEY or "dummy_key_to_prevent_crash",
            base_url=settings.GEMINI_BASE_URL,
        )

    async def complete(self, system_prompt: str, user_message: str, max_tokens: int = 200, temperature: float = 0.7) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                # Gemini 2.5 models "think" by default, and thinking tokens share the
                # output budget — leaving our reply truncated. Disable it (review replies
                # don't need reasoning) and keep headroom in case the model ignores it.
                max_tokens=max(max_tokens, 1024),
                temperature=temperature,
                timeout=20.0,
                extra_body={"extra_body": {"google": {"thinking_config": {"thinking_budget": 0}}}},
            )
            if not response.choices or not response.choices[0].message.content:
                raise LLMProviderError("No response content from Gemini provider.")
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise LLMProviderError(f"Gemini AI service temporarily unavailable: {str(e)}")
