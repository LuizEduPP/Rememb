from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from rememb.config import DEFAULT_SECTIONS
from rememb.store import (
    clear_entries,
    consolidate_entries,
    delete_entry,
    edit_entry,
    format_entries,
    get_config,
    get_stats,
    init,
    read_entries,
    search_entries,
    write_entry,
)
from rememb.exceptions import RemembError, RemembNotInitializedError
from rememb.utils import _validate_entry_id, find_root, is_initialized
from rememb.helpers import _assert_initialized


DEFAULT_SSE_HOST = "127.0.0.1"
DEFAULT_SSE_PORT = 8765
DEFAULT_SSE_PATH = "/sse"
DEFAULT_MESSAGE_PATH = "/messages/"


class MCPContext:
    """Encapsulates MCP-specific cache and state.

    Manages MCP module imports and root cache for MCP server operations.
    """

    def __init__(self):
        self._mcp_modules = None
        self._root_cache: dict[str, Any] = {}

    def get_mcp_modules(self):
        """Get or load MCP modules.

        Returns:
            Dictionary with Server, stdio_server, Tool, TextContent classes

        Raises:
            ImportError: If mcp package not installed
        """
        if self._mcp_modules is None:
            try:
                from mcp.server import Server
                from mcp.server.stdio import stdio_server
                from mcp.types import Tool, TextContent
                self._mcp_modules = {
                    "Server": Server,
                    "stdio_server": stdio_server,
                    "Tool": Tool,
                    "TextContent": TextContent,
                }
            except ImportError as e:
                raise ImportError(
                    "MCP server requires: pip install mcp>=1.0.0\n"
                    "Install with: pip install rememb[mcp]"
                ) from e
        return self._mcp_modules

    def get_root_cache(self) -> dict[str, Any]:
        """Get root cache dictionary.
        
        Returns:
            Root cache dictionary
        """
        return self._root_cache

    def clear_root_cache(self):
        """Clear root cache dictionary."""
        self._root_cache.clear()


_mcp_context = MCPContext()


def _get_root() -> Path:
    """Get root path with cache invalidation.

    Returns:
        Project root path

    Raises:
        RemembNotInitializedError: If rememb not initialized
    """
    root = find_root()
    _assert_initialized(root)

    root_cache = _mcp_context.get_root_cache()
    if "root" in root_cache and root_cache["root"] != root:
        _mcp_context.clear_root_cache()
        root_cache = _mcp_context.get_root_cache()

    root_cache["root"] = root
    return root


def _get_mcp_sections() -> list[str]:
    """Return the current section list for MCP schemas, with safe fallback."""
    try:
        root = _get_root()
        return list(get_config(root).get("sections", DEFAULT_SECTIONS))
    except Exception:
        return list(DEFAULT_SECTIONS)


def _get_default_mcp_section() -> str:
    sections = _get_mcp_sections()
    if "context" in sections:
        return "context"
    return sections[0]


async def _handle_tool(name: str, arguments: dict[str, Any], TextContent):
    """Handle MCP tool invocation.

    Args:
        name: Tool name (e.g., 'rememb_read', 'rememb_write')
        arguments: Tool arguments dictionary
        TextContent: TextContent class for responses

    Returns:
        List of TextContent responses
    """
    root = await asyncio.to_thread(_get_root)

    async def rememb_read():
        section = arguments.get("section")
        entries = await asyncio.to_thread(read_entries, root, section)
        return [TextContent(type="text", text=format_entries(entries, include_id=True))]

    async def rememb_search():
        query = arguments["query"]
        top_k = arguments.get("top_k", 5)
        entries = await asyncio.to_thread(search_entries, root, query, top_k)
        return [TextContent(type="text", text=format_entries(entries, include_id=True))]

    async def rememb_write():
        content = arguments["content"]
        section = arguments.get("section", _get_default_mcp_section())
        tags = arguments.get("tags", [])
        semantic_scope = arguments.get("semantic_scope", "global")
        entry = await asyncio.to_thread(write_entry, root, section, content, tags, True, semantic_scope)
        return [TextContent(type="text", text=f"Saved [{entry['section']}] id={entry['id']}")]

    async def rememb_edit():
        entry_id = arguments["entry_id"]
        if not _validate_entry_id(entry_id):
            return [TextContent(type="text", text=f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")]
        content = arguments.get("content")
        section = arguments.get("section")
        tags = arguments.get("tags")
        if content is None and section is None and tags is None:
            return [TextContent(type="text", text="Provide at least one field to update: content, section, or tags.")]
        result = await asyncio.to_thread(edit_entry, root, entry_id, content, section, tags)
        if result:
            return [TextContent(type="text", text=f"Updated {entry_id}")]
        return [TextContent(type="text", text=f"Entry {entry_id} not found")]

    async def rememb_delete():
        entry_id = arguments["entry_id"]
        if not _validate_entry_id(entry_id):
            return [TextContent(type="text", text=f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")]
        if await asyncio.to_thread(delete_entry, root, entry_id):
            return [TextContent(type="text", text=f"Deleted {entry_id}")]
        return [TextContent(type="text", text=f"Entry {entry_id} not found")]

    async def rememb_clear():
        confirm = arguments.get("confirm", False)
        if not confirm:
            return [TextContent(type="text", text="Clear cancelled. Set confirm=true to proceed.")]
        count = await asyncio.to_thread(clear_entries, root, confirm=True)
        return [TextContent(type="text", text=f"Cleared {count} entries")]

    async def rememb_stats():
        stats = await asyncio.to_thread(get_stats, root)
        lines = [
            f"Total entries: {stats['total']}",
            f"Memory size: {stats['size_kb']} KB",
            f"Oldest entry: {stats['oldest']}",
            f"Newest entry: {stats['newest']}",
            "",
        ] + [f"{sec}: {count}" for sec, count in stats["by_section"].items()]
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_consolidate():
        section = arguments.get("section")
        mode = arguments.get("mode", "exact")
        similarity_threshold = arguments.get("similarity_threshold", 0.88)
        result = await asyncio.to_thread(
            consolidate_entries,
            root,
            section,
            mode,
            similarity_threshold,
        )
        target = result["section"] if result["section"] else "all sections"
        mode_info = f" mode={result['mode']}"
        if result["mode"] == "semantic":
            mode_info += f" threshold={result['similarity_threshold']}"
        return [TextContent(
            type="text",
            text=(
                f"Consolidation completed for {target}. "
                f"Using{mode_info}. "
                f"Removed {result['removed_count']} duplicate entries "
                f"({result['total_before']} -> {result['total_after']})."
            ),
        )]

    async def rememb_init():
        project_name = arguments.get("project_name", "")
        init_root = find_root(local=True)
        if await asyncio.to_thread(is_initialized, init_root):
            return [TextContent(type="text", text=f"Already initialized at {init_root / '.rememb'}")]
        _mcp_context.clear_root_cache()
        rememb_path = await asyncio.to_thread(init, init_root, project_name)
        return [TextContent(type="text", text=f"Initialized at {rememb_path}")]

    tool_handlers = {
        "rememb_read": rememb_read,
        "rememb_search": rememb_search,
        "rememb_write": rememb_write,
        "rememb_edit": rememb_edit,
        "rememb_delete": rememb_delete,
        "rememb_clear": rememb_clear,
        "rememb_stats": rememb_stats,
        "rememb_consolidate": rememb_consolidate,
        "rememb_init": rememb_init,
    }

    handler = tool_handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    try:
        return await handler()
    except RemembError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Unexpected error: {e}")]


def _build_tools(Tool):
    """Run MCP stdio server.
    
    Starts the MCP server and handles stdio communication.
    """
    def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema

    def _tool(
        name: str,
        description: str,
        properties: dict[str, Any] | None = None,
        required: list[str] | None = None,
    ):
        return Tool(
            name=name,
            description=description,
            inputSchema=_schema(properties or {}, required),
        )

    sections = _get_mcp_sections()
    default_section = _get_default_mcp_section()

    return [
        _tool(
            name="rememb_read",
            description="Read all memory entries or filter by section. Safe, read-only operation with no side effects. Use this at the start of every session to load context. Prefer rememb_search when looking for specific information by keyword or topic.",
            properties={
                "section": {
                    "type": "string",
                    "enum": sections,
                    "description": f"Filter by section: {', '.join(sections)}",
                }
            },
        ),
        _tool(
            name="rememb_search",
            description="Search memory entries by content or tags using semantic similarity with keyword fallback. Safe, read-only operation with no side effects. Use instead of rememb_read when you need to find specific entries by topic rather than loading all entries. Returns the top_k most relevant results ranked by similarity.",
            properties={
                "query": {
                    "type": "string",
                    "description": "Search query - natural language or keywords",
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "Maximum number of results",
                },
            },
            required=["query"],
        ),
        _tool(
            name="rememb_write",
            description="Save a new memory entry. Creates a new entry and returns its ID — does not overwrite existing entries. Use when you learn something new worth remembering across sessions. Use rememb_edit instead to update an existing entry by ID. semantic_scope controls whether semantic duplicate blocking checks globally or only inside the target section.",
            properties={
                "content": {
                    "type": "string",
                    "description": "Content to remember (1-3 sentences)",
                },
                "section": {
                    "type": "string",
                    "enum": sections,
                    "default": default_section,
                    "description": f"Section: {', '.join(sections)}",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to categorize this entry",
                },
                "semantic_scope": {
                    "type": "string",
                    "enum": ["global", "section"],
                    "default": "global",
                    "description": "Semantic duplicate guard scope: global (all sections) or section (target section only)",
                },
            },
            required=["content"],
        ),
        _tool(
            name="rememb_edit",
            description="Update an existing memory entry in-place by its ID. Modifies only the fields provided (content, section, or tags) — omitted fields are unchanged. Non-destructive: the entry is updated, not deleted and recreated. Use rememb_write to create new entries, rememb_delete to permanently remove one.",
            properties={
                "entry_id": {
                    "type": "string",
                    "description": "Entry ID (8 hex characters)",
                },
                "content": {
                    "type": "string",
                    "description": "New content",
                },
                "section": {
                    "type": "string",
                    "enum": sections,
                    "description": "Move to different section",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Replace tags",
                },
            },
            required=["entry_id"],
        ),
        _tool(
            name="rememb_delete",
            description="Permanently delete a single memory entry by its ID. Deletion is irreversible — the entry cannot be recovered. No cascading side effects. Use rememb_edit to update instead. Use rememb_clear to delete all entries at once.",
            properties={
                "entry_id": {
                    "type": "string",
                    "description": "Entry ID to delete",
                }
            },
            required=["entry_id"],
        ),
        _tool(
            name="rememb_clear",
            description="Permanently delete ALL memory entries at once. Irreversible — no recovery is possible after this operation. Requires confirm=true as a safety guard. Use rememb_delete to remove a single entry by ID instead. Only use this to fully reset the memory store.",
            properties={
                "confirm": {
                    "type": "boolean",
                    "description": "Must be true to confirm deletion",
                }
            },
            required=["confirm"],
        ),
        _tool(
            name="rememb_stats",
            description="Return memory usage statistics: total entries, size in KB, oldest and newest entry dates, and count per section. Safe, read-only operation with no side effects. Use to give the user an overview of their memory store or to decide if cleanup is needed.",
            properties={},
        ),
        _tool(
            name="rememb_consolidate",
            description="Consolidate duplicate entries and merge metadata (tags and access data). Supports exact mode (default, normalized content match) and semantic mode (cosine similarity threshold). This mutates storage by removing redundant entries and keeping one consolidated record per duplicate group.",
            properties={
                "section": {
                    "type": "string",
                    "enum": sections,
                    "description": f"Optional section filter: {', '.join(sections)}",
                },
                "mode": {
                    "type": "string",
                    "enum": ["exact", "semantic"],
                    "default": "exact",
                    "description": "Consolidation mode: exact (normalized content) or semantic (similarity threshold)",
                },
                "similarity_threshold": {
                    "type": "number",
                    "default": 0.88,
                    "description": "Cosine similarity threshold used when mode is semantic (>0 and <=1)",
                },
            },
        ),
        _tool(
            name="rememb_init",
            description="Initialize a local rememb memory store in the current directory, creating a .rememb/ folder. Idempotent — safe to call even if already initialized (returns status without overwriting). Call this once per project before using other tools. Falls back to ~/.rememb/ globally if not initialized.",
            properties={
                "project_name": {
                    "type": "string",
                    "description": "Optional project name",
                }
            },
        ),
    ]


def _create_server(Server, Tool, TextContent):
    """Create an MCP server instance with all rememb tools registered."""
    server = Server("rememb")

    @server.list_tools()
    async def list_tools():
        return _build_tools(Tool)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]):
        return await _handle_tool(name, arguments, TextContent)

    return server


def _build_sse_app(server, sse_path: str, message_path: str):
    """Build a Starlette app that exposes the MCP server over SSE."""
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.responses import Response
    from starlette.routing import Mount, Route

    sse = SseServerTransport(message_path)

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )
        return Response()

    return Starlette(routes=[
        Route(sse_path, endpoint=handle_sse, methods=["GET"]),
        Mount(message_path, app=sse.handle_post_message),
    ])


async def _run_stdio_server(server, stdio_server):
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def _run_sse_server(server, host: str, port: int, sse_path: str, message_path: str):
    """Run the MCP server over a persistent local SSE transport."""
    import uvicorn

    app = _build_sse_app(server, sse_path, message_path)
    uvicorn_server = uvicorn.Server(
        uvicorn.Config(app, host=host, port=port, log_level="info")
    )
    await uvicorn_server.serve()


async def run_server(
    transport: str = "stdio",
    host: str = DEFAULT_SSE_HOST,
    port: int = DEFAULT_SSE_PORT,
):
    """Run the MCP server over stdio or a persistent local SSE transport."""
    mcp = _mcp_context.get_mcp_modules()
    Server = mcp["Server"]
    stdio_server = mcp["stdio_server"]
    Tool = mcp["Tool"]
    TextContent = mcp["TextContent"]
    server = _create_server(Server, Tool, TextContent)

    normalized_transport = transport.lower().strip()
    if normalized_transport == "stdio":
        await _run_stdio_server(server, stdio_server)
        return
    if normalized_transport == "sse":
        await _run_sse_server(server, host, port, DEFAULT_SSE_PATH, DEFAULT_MESSAGE_PATH)
        return

    raise ValueError(f"Unsupported MCP transport: {transport}. Use 'stdio' or 'sse'.")
