"""Web UI server for rememb."""

from rememb.web.app import app, run_web
from rememb.web.deps import get_root

__all__ = [
    "app",
    "run_web",
    "get_root",
]
