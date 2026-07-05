from abc import ABC, abstractmethod

class BaseStorageProvider(ABC):
    @abstractmethod
    async def upload_file(self, file_data: bytes, key: str, mime_type: str) -> str:
        """
        Uploads a file to the storage provider and returns its public HTTPS CDN/access URL.
        """
        pass

    @abstractmethod
    async def read_file(self, key: str) -> bytes:
        """
        Reads a file from the storage provider and returns its binary contents as bytes.
        """
        pass

    @abstractmethod
    async def delete_file(self, key: str) -> None:
        """
        Deletes a file from the storage provider.
        """
        pass

    @abstractmethod
    async def generate_public_url(self, key: str) -> str:
        """
        Generates a publicly accessible HTTPS URL for the given file key.
        """
        pass

    @abstractmethod
    async def file_exists(self, key: str) -> bool:
        """
        Checks if a file exists under the given storage key.
        """
        pass
