from app.core.config import settings
from app.llm.base import BaseLLMProvider
from app.llm.groq import GroqLLMProvider

def get_llm_provider() -> BaseLLMProvider:
    provider = settings.LLM_PROVIDER
    if provider == "groq":
        return GroqLLMProvider()
    raise ValueError(f"Unknown LLM provider: {provider}")
