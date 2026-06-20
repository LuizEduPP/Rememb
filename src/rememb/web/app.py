"""FastAPI application factory for the rememb web UI."""

from __future__ import annotations

import hashlib
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from rememb.web.routes import entries, system

_STATIC_DIR = Path(__file__).parent.parent / "static"
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _asset_version(filename: str) -> str:
    path = _STATIC_DIR / filename
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest[:12]


class DevStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


def create_app() -> FastAPI:
    app = FastAPI(title="rememb", docs_url=None, redoc_url=None)
    app.mount("/static", DevStaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/")
    async def index() -> HTMLResponse:
        html_path = _STATIC_DIR / "index.html"
        html = html_path.read_text(encoding="utf-8")
        html = (
            html.replace("{{STYLE_VERSION}}", _asset_version("style.css"))
            .replace("{{APP_VERSION}}", _asset_version("app.js"))
        )
        return HTMLResponse(content=html, headers=_NO_CACHE_HEADERS)

    app.include_router(entries.router)
    app.include_router(system.router)

    return app


app = create_app()


def run_web(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    """Start the rememb web UI server."""
    import uvicorn

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")
