"""Web UI server for rememb."""

from rememb.web.app import app, run_web
from rememb.web.deps import get_root

_get_root = get_root

__all__ = [
    "app",
    "run_web",
    "_get_root",
    "get_root",
]
