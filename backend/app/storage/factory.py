from app.storage.base.provider import BaseStorageProvider
from app.storage.registry import StorageRegistry
from app.core.config import settings

# Explicitly import and register all providers
from app.storage.providers.local import LocalStorageProvider
from app.storage.providers.r2 import R2StorageProvider

StorageRegistry.register(LocalStorageProvider)
StorageRegistry.register(R2StorageProvider)

class StorageProviderFactory:
    @staticmethod
    def get_provider(provider_name: str = None) -> BaseStorageProvider:
        """
        Instantiates and returns the configured storage provider.
        If no provider_name is passed, defaults to the STORAGE_PROVIDER environment setting.
        """
        name = provider_name or settings.STORAGE_PROVIDER
        provider_class = StorageRegistry.get(name)
        return provider_class()
