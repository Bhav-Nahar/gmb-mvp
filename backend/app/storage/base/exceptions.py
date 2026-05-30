class StorageError(Exception):
    """Base exception for all storage providers."""
    pass

class FileNotFoundStorageError(StorageError):
    """Raised when the requested file does not exist in storage."""
    pass

class StorageConnectionError(StorageError):
    """Raised when there is a connection issue with the storage provider."""
    pass
