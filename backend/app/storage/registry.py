from typing import Dict, Type
from app.storage.base.provider import BaseStorageProvider

class StorageRegistry:
    _registry: Dict[str, Type[BaseStorageProvider]] = {}

    @classmethod
    def register(cls, provider_class: Type[BaseStorageProvider]):
        """Decorator or method to register a provider class."""
        cls._registry[provider_class.provider_name] = provider_class
        return provider_class

    @classmethod
    def get(cls, name: str) -> Type[BaseStorageProvider]:
        if name not in cls._registry:
            raise ValueError(f"Storage provider '{name}' not found in registry.")
        return cls._registry[name]
