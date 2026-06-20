"""Shared dependencies for the rememb web UI."""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

from fastapi import HTTPException

from rememb.exceptions import RemembError, rememb_error_http_status, rememb_error_response_text
from rememb.store import init
from rememb.utils import ensure_global_root


def get_root() -> Path:
    """Return the global root, auto-initializing if needed."""
    return ensure_global_root(init)


def raise_http_error(exc: Exception, *, default_status: int = 422) -> NoReturn:
    if isinstance(exc, RemembError):
        raise HTTPException(
            status_code=rememb_error_http_status(exc, default_status=default_status),
            detail=rememb_error_response_text(exc),
        ) from exc
    raise HTTPException(status_code=default_status, detail=str(exc)) from exc
