from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from rememb.store import (
    SECTIONS,
    clear_entries,
    delete_entry,
    edit_entry,
    format_entries,
    get_stats,
    init,
    read_entries,
    search_entries,
    write_entry,
)
from rememb.exceptions import RemembError, RemembNotInitializedError
from rememb.utils import _validate_entry_id, find_root, is_initialized
from rememb.helpers import _assert_initialized


class MCPContext:
    """Encapsulates MCP-specific cache and state.
    
    Manages MCP module imports and root cache for MCP server operations.
    """
    def __init__(self):
        self._mcp_modules = None
        self._root_cache: dict = {}
    
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
    
    def get_root_cache(self) -> dict:
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
    # Clear cache if root changed
    if "root" in root_cache and root_cache["root"] != root:
        _mcp_context.clear_root_cache()
        root_cache = _mcp_context.get_root_cache()
    
    root_cache["root"] = root
    return root


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
        section = arguments.get("section", "context")
        tags = arguments.get("tags", [])
        entry = await asyncio.to_thread(write_entry, root, section, content, tags)
        return [TextContent(
            type="text",
            text=f"Saved [{entry['section']}] id={entry['id']}"
        )]
    
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
        s = await asyncio.to_thread(get_stats, root)
        lines = [
            f"Total entries: {s['total']}",
            f"Memory size: {s['size_kb']} KB",
            f"Oldest entry: {s['oldest']}",
            f"Newest entry: {s['newest']}",
            "",
        ] + [f"{sec}: {s['by_section'][sec]}" for sec in SECTIONS]
        return [TextContent(type="text", text="\n".join(lines))]
    
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


async def run_server():
    """Run MCP stdio server.
    
    Starts the MCP server and handles stdio communication.
    """
    mcp = _mcp_context.get_mcp_modules()
    Server = mcp["Server"]
    stdio_server = mcp["stdio_server"]
    Tool = mcp["Tool"]
    TextContent = mcp["TextContent"]
    
    server = Server("rememb")
    
    tools = [
        Tool(
            name="rememb_read",
            description="Read all memory entries or filter by section. Safe, read-only operation with no side effects. Use this at the start of every session to load context. Prefer rememb_search when looking for specific information by keyword or topic.",
            inputSchema={
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "enum": SECTIONS,
                        "description": f"Filter by section: {', '.join(SECTIONS)}"
                    }
                }
            }
        ),
        Tool(
            name="rememb_search",
            description="Search memory entries by content or tags using semantic similarity with keyword fallback. Safe, read-only operation with no side effects. Use instead of rememb_read when you need to find specific entries by topic rather than loading all entries. Returns the top_k most relevant results ranked by similarity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query - natural language or keywords"
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "description": "Maximum number of results"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="rememb_write",
            description="Save a new memory entry. Creates a new entry and returns its ID — does not overwrite existing entries. Use when you learn something new worth remembering across sessions. Use rememb_edit instead to update an existing entry by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Content to remember (1-3 sentences)"
                    },
                    "section": {
                        "type": "string",
                        "enum": SECTIONS,
                        "default": "context",
                        "description": f"Section: {', '.join(SECTIONS)}"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to categorize this entry"
                    }
                },
                "required": ["content"]
            }
        ),
        Tool(
            name="rememb_edit",
            description="Update an existing memory entry in-place by its ID. Modifies only the fields provided (content, section, or tags) — omitted fields are unchanged. Non-destructive: the entry is updated, not deleted and recreated. Use rememb_write to create new entries, rememb_delete to permanently remove one.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entry_id": {
                        "type": "string",
                        "description": "Entry ID (8 hex characters)"
                    },
                    "content": {
                        "type": "string",
                        "description": "New content"
                    },
                    "section": {
                        "type": "string",
                        "enum": SECTIONS,
                        "description": "Move to different section"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Replace tags"
                    }
                },
                "required": ["entry_id"]
            }
        ),
        Tool(
            name="rememb_delete",
            description="Permanently delete a single memory entry by its ID. Deletion is irreversible — the entry cannot be recovered. No cascading side effects. Use rememb_edit to update instead. Use rememb_clear to delete all entries at once.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entry_id": {
                        "type": "string",
                        "description": "Entry ID to delete"
                    }
                },
                "required": ["entry_id"]
            }
        ),
        Tool(
            name="rememb_clear",
            description="Permanently delete ALL memory entries at once. Irreversible — no recovery is possible after this operation. Requires confirm=true as a safety guard. Use rememb_delete to remove a single entry by ID instead. Only use this to fully reset the memory store.",
            inputSchema={
                "type": "object",
                "properties": {
                    "confirm": {
                        "type": "boolean",
                        "description": "Must be true to confirm deletion"
                    }
                },
                "required": ["confirm"]
            }
        ),
        Tool(
            name="rememb_stats",
            description="Return memory usage statistics: total entries, size in KB, oldest and newest entry dates, and count per section. Safe, read-only operation with no side effects. Use to give the user an overview of their memory store or to decide if cleanup is needed.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="rememb_init",
            description="Initialize a local rememb memory store in the current directory, creating a .rememb/ folder. Idempotent — safe to call even if already initialized (returns status without overwriting). Call this once per project before using other tools. Falls back to ~/.rememb/ globally if not initialized.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Optional project name"
                    }
                }
            }
        ),
    ]
    
    @server.list_tools()
    async def list_tools():
        return tools
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]):
        return await _handle_tool(name, arguments, TextContent)
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
