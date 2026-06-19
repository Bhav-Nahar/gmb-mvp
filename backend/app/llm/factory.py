from app.core.config import settings
from app.llm.base import BaseLLMProvider
from app.llm.groq import GroqLLMProvider
from app.llm.gemini import GeminiLLMProvider

def get_llm_provider() -> BaseLLMProvider:
    provider = settings.LLM_PROVIDER
    if provider == "groq":
        return GroqLLMProvider()
    if provider == "gemini":
        return GeminiLLMProvider()
    raise ValueError(f"Unknown LLM provider: {provider}")
