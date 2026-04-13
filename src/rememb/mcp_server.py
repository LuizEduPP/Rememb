from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from rememb.store import (
    SECTIONS,
    clear_entries,
    delete_entry,
    edit_entry,
    find_root,
    format_entries,
    global_root,
    init,
    is_initialized,
    read_entries,
    search_entries,
    write_entry,
)


_mcp_modules = None
_root_cache: dict = {}


def _load_mcp():
    global _mcp_modules
    if _mcp_modules is None:
        try:
            from mcp.server import Server
            from mcp.server.stdio import stdio_server
            from mcp.types import Tool, TextContent
            _mcp_modules = {
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
    return _mcp_modules


def _get_root() -> Path:
    if "root" not in _root_cache:
        root = find_root()
        if not is_initialized(root):
            root = global_root()
            if not is_initialized(root):
                try:
                    init(root, project_name="global", global_mode=True)
                except PermissionError as e:
                    raise RuntimeError(f"Cannot create ~/.rememb/ directory: {e}") from e
                except OSError as e:
                    raise RuntimeError(f"Cannot initialize rememb storage: {e}") from e
        _root_cache["root"] = root
    return _root_cache["root"]


async def _handle_tool(name: str, arguments: dict[str, Any], TextContent):
    root = await asyncio.to_thread(_get_root)
    
    try:
        if name == "rememb_read":
            section = arguments.get("section")
            entries = await asyncio.to_thread(read_entries, root, section)
            return [TextContent(type="text", text=format_entries(entries, include_id=True))]
        
        elif name == "rememb_search":
            query = arguments["query"]
            top_k = arguments.get("top_k", 5)
            entries = await asyncio.to_thread(search_entries, root, query, top_k)
            return [TextContent(type="text", text=format_entries(entries, include_id=True))]
        
        elif name == "rememb_write":
            content = arguments["content"]
            section = arguments.get("section", "context")
            tags = arguments.get("tags", [])
            entry = await asyncio.to_thread(write_entry, root, section, content, tags)
            return [TextContent(
                type="text",
                text=f"Saved [{entry['section']}] id={entry['id']}"
            )]
        
        elif name == "rememb_edit":
            entry_id = arguments["entry_id"]
            if not re.match(r"^[a-f0-9]{8}$", entry_id, re.IGNORECASE):
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
        
        elif name == "rememb_delete":
            entry_id = arguments["entry_id"]
            if not re.match(r"^[a-f0-9]{8}$", entry_id, re.IGNORECASE):
                return [TextContent(type="text", text=f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")]
            if await asyncio.to_thread(delete_entry, root, entry_id):
                return [TextContent(type="text", text=f"Deleted {entry_id}")]
            return [TextContent(type="text", text=f"Entry {entry_id} not found")]
        
        elif name == "rememb_clear":
            confirm = arguments.get("confirm", False)
            if not confirm:
                return [TextContent(type="text", text="Clear cancelled. Set confirm=true to proceed.")]
            count = await asyncio.to_thread(lambda: clear_entries(root, confirm=True))
            return [TextContent(type="text", text=f"Cleared {count} entries")]
        
        elif name == "rememb_stats":
            entries = await asyncio.to_thread(read_entries, root)
            total = len(entries)
            by_section = {s: 0 for s in SECTIONS}
            for e in entries:
                sec = e.get("section", "context")
                if sec in by_section:
                    by_section[sec] += 1
            entries_path = root / ".rememb" / "entries.json"
            size_kb = round(entries_path.stat().st_size / 1024, 1) if entries_path.exists() else 0
            timestamps = sorted(e.get("created_at", "") for e in entries if e.get("created_at"))
            oldest = timestamps[0][:10] if timestamps else "—"
            newest = timestamps[-1][:10] if timestamps else "—"
            lines = [
                f"Total entries: {total}",
                f"Memory size: {size_kb} KB",
                f"Oldest entry: {oldest}",
                f"Newest entry: {newest}",
                "",
            ] + [f"{s}: {by_section[s]}" for s in SECTIONS]
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "rememb_init":
            project_name = arguments.get("project_name", "")
            init_root = find_root(local=True)
            if await asyncio.to_thread(is_initialized, init_root):
                return [TextContent(type="text", text=f"Already initialized at {init_root / '.rememb'}")]
            _root_cache.clear()
            rememb_path = await asyncio.to_thread(init, init_root, project_name)
            return [TextContent(type="text", text=f"Initialized at {rememb_path}")]
        
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def run_server():
    mcp = _load_mcp()
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
