"""Custom exceptions for rememb error handling."""


class RemembError(RuntimeError):
    """Base exception for rememb errors."""
    pass


class RemembNotInitializedError(RemembError):
    """Raised when rememb is not initialized."""
    pass


class RemembValidationError(RemembError):
    """Raised when input validation fails."""
    pass


class RemembStorageError(RemembError):
    """Raised when storage operations fail."""
    pass


class RemembConfigError(RemembError):
    """Raised when configuration is invalid."""
    pass
