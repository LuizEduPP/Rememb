"""Custom exceptions for rememb error handling."""

from __future__ import annotations


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


def rememb_error_http_status(error: RemembError, *, default_status: int = 422) -> int:
    """Map a rememb domain error to an HTTP status code."""
    if isinstance(error, (RemembValidationError, RemembConfigError)):
        return 422
    if isinstance(error, RemembStorageError):
        return 500
    if isinstance(error, RemembNotInitializedError):
        return 503
    return default_status


def rememb_error_response_text(error: RemembError) -> str:
    """Render a rememb domain error for adapters."""
    return str(error)
