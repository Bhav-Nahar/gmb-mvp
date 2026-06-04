class PermissionDeniedError(Exception):
    """Exception raised when an actor does not have permission to perform an action."""
    pass


class ConflictError(Exception):
    """Exception raised when an action conflicts with the current state (e.g. active edit already exists)."""
    pass


class NotFoundError(Exception):
    """Exception raised when a requested resource is not found."""
    pass
