from pydantic import BaseModel
from typing import Optional, Dict, Any

class StorageFileMetadata(BaseModel):
    key: str
    size_bytes: int
    mime_type: str
    sha256_hash: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    custom_metadata: Dict[str, Any] = {}
