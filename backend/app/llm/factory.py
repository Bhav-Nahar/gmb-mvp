from app.core.config import settings
from app.llm.base import BaseLLMProvider
from app.llm.groq import GroqLLMProvider
from app.llm.gemini import GeminiLLMProvider

def get_llm_provider(provider: str | None = None, model: str | None = None) -> BaseLLMProvider:
    # Pass provider + model together for a per-feature override (e.g. sentiment on
    # Groq while the global is Gemini); omit both to use the global settings.
    provider = provider or settings.LLM_PROVIDER
    if provider == "groq":
        return GroqLLMProvider(model=model)
    if provider == "gemini":
        return GeminiLLMProvider(model=model)
    raise ValueError(f"Unknown LLM provider: {provider}")
