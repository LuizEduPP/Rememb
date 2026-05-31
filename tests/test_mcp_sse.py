from __future__ import annotations

import asyncio

import pytest

import rememb.mcp_server as mcp_server


def test_build_sse_app_exposes_expected_routes() -> None:
    mcp = mcp_server._mcp_context.get_mcp_modules()
    server = mcp_server._create_server(mcp["Server"], mcp["Tool"], mcp["TextContent"])
    app = mcp_server._build_sse_app(
        server,
        mcp_server.DEFAULT_SSE_PATH,
        mcp_server.DEFAULT_MESSAGE_PATH,
    )

    paths = {getattr(route, "path", None) for route in app.routes}
    assert mcp_server.DEFAULT_SSE_PATH in paths
    assert mcp_server.DEFAULT_MESSAGE_PATH.rstrip("/") in {
        path.rstrip("/") if isinstance(path, str) else path for path in paths
    }


def test_run_server_rejects_unknown_transport() -> None:
    with pytest.raises(ValueError, match="Unsupported MCP transport"):
        asyncio.run(mcp_server.run_server(transport="websocket"))
