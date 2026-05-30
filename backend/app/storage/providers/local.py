import os
from app.storage.base.provider import BaseStorageProvider
from app.storage.base.models import StorageFileMetadata
from app.storage.base.exceptions import FileNotFoundStorageError, StorageError
from app.core.config import settings

class LocalStorageProvider(BaseStorageProvider):
    provider_name = "local"

    def __init__(self):
        # Resolve static uploads directory relative to this file
        # C:\...\backend\app\storage\providers\local.py -> go up 3 directories to C:\...\backend\app\
        self.base_dir = os.path.normpath(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                settings.LOCAL_STORAGE_DIR
            )
        )
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_absolute_path(self, key: str) -> str:
        # Prevent directory traversal attacks
        # Normalize the key and strip leading separators
        clean_key = os.path.normpath(key).lstrip("\\/").replace("..", "")
        return os.path.join(self.base_dir, clean_key)

    async def upload_file(self, file_data: bytes, key: str, mime_type: str) -> str:
        try:
            filepath = self._get_absolute_path(key)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(file_data)
            return await self.generate_public_url(key)
        except Exception as e:
            raise StorageError(f"Failed to upload local file: {str(e)}")

    async def read_file(self, key: str) -> bytes:
        filepath = self._get_absolute_path(key)
        if not os.path.exists(filepath):
            raise FileNotFoundStorageError(f"File not found: {key}")
        try:
            with open(filepath, "rb") as f:
                return f.read()
        except Exception as e:
            raise StorageError(f"Failed to read local file: {str(e)}")

    async def delete_file(self, key: str) -> None:
        filepath = self._get_absolute_path(key)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                raise StorageError(f"Failed to delete local file: {str(e)}")
        else:
            raise FileNotFoundStorageError(f"File not found: {key}")

    async def generate_public_url(self, key: str) -> str:
        # Convert path separators to standard URL forward slashes
        clean_key = key.replace("\\", "/").lstrip("/")
        return f"{settings.BACKEND_URL.rstrip('/')}/static/uploads/{clean_key}"

    async def file_exists(self, key: str) -> bool:
        filepath = self._get_absolute_path(key)
        return os.path.exists(filepath)

    async def get_metadata(self, key: str) -> StorageFileMetadata:
        filepath = self._get_absolute_path(key)
        if not os.path.exists(filepath):
            raise FileNotFoundStorageError(f"File not found: {key}")
        
        try:
            size = os.path.getsize(filepath)
            import mimetypes
            mime, _ = mimetypes.guess_type(filepath)
            if not mime:
                mime = "application/octet-stream"
                
            return StorageFileMetadata(
                key=key,
                size_bytes=size,
                mime_type=mime
            )
        except Exception as e:
            raise StorageError(f"Failed to read local file metadata: {str(e)}")
