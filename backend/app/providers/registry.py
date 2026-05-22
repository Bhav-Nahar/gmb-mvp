from typing import Dict, Type
from .base.provider import BaseProvider

class ProviderRegistry:
    _registry: Dict[str, Type[BaseProvider]] = {}

    @classmethod
    def register(cls, provider_class: Type[BaseProvider]):
        """Decorator to register a provider class."""
        cls._registry[provider_class.provider_name] = provider_class
        return provider_class

    @classmethod
    def get(cls, name: str) -> Type[BaseProvider]:
        if name not in cls._registry:
            raise ValueError(f"Provider '{name}' not found in registry.")
        return cls._registry[name]
