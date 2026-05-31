"""FastAPI application factory for the rememb web UI."""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from rememb.web.routes import entries, review, system, workstreams

_STATIC_DIR = Path(__file__).parent.parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="rememb", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        html_path = _STATIC_DIR / "index.html"
        return html_path.read_text(encoding="utf-8")

    app.include_router(entries.router)
    app.include_router(workstreams.router)
    app.include_router(review.router)
    app.include_router(system.router)

    return app


app = create_app()


def run_web(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    """Start the rememb web UI server."""
    import uvicorn

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")
