"""Shared dependencies for the rememb web UI."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

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


def missing_or_404(result: Any, *, detail: str, missing: Any = None) -> Any:
    is_missing = result == [] if missing == [] else result is missing
    if is_missing:
        raise HTTPException(status_code=404, detail=detail)
    return result


async def call_store(
    fn: Callable[..., Any],
    *args: Any,
    default_status: int = 422,
    not_found: str | None = None,
    missing: Any = None,
    **kwargs: Any,
) -> Any:
    root = await asyncio.to_thread(get_root)
    try:
        result = await asyncio.to_thread(fn, root, *args, **kwargs)
    except Exception as exc:
        raise_http_error(exc, default_status=default_status)
    if not_found is not None:
        return missing_or_404(result, detail=not_found, missing=missing)
    return result
