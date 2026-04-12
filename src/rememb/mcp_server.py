from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from rememb.store import (
    SECTIONS,
    clear_entries,
    delete_entry,
    edit_entry,
    find_root,
    global_root,
    init,
    is_initialized,
    read_entries,
    search_entries,
    write_entry,
)


_mcp_modules = None


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
    root = find_root()
    if not is_initialized(root):
        root = global_root()
        if not is_initialized(root):
            init(root, project_name="global", global_mode=True)
    return root


def _format_entries(entries: list[dict]) -> str:
    if not entries:
        return "No memory entries found."
    
    by_section: dict[str, list] = {}
    for e in entries:
        by_section.setdefault(e["section"], []).append(e)
    
    lines = ["# Memory Context (rememb)\n"]
    for section, items in by_section.items():
        lines.append(f"## {section.capitalize()}")
        for item in items:
            tags = f" [{', '.join(item['tags'])}]" if item.get("tags") else ""
            lines.append(f"- [{item['id']}] {item['content']}{tags}")
        lines.append("")
    
    return "\n".join(lines)


async def _handle_tool(name: str, arguments: dict[str, Any], TextContent):
    root = await asyncio.to_thread(_get_root)
    
    try:
        if name == "rememb_read":
            section = arguments.get("section")
            entries = await asyncio.to_thread(read_entries, root, section)
            return [TextContent(type="text", text=_format_entries(entries))]
        
        elif name == "rememb_search":
            query = arguments["query"]
            top_k = arguments.get("top_k", 5)
            try:
                entries = await asyncio.to_thread(search_entries, root, query, top_k)
            except RuntimeError:
                from rememb.store import _keyword_search
                all_entries = await asyncio.to_thread(read_entries, root)
                entries = await asyncio.to_thread(_keyword_search, all_entries, query, top_k)
            return [TextContent(type="text", text=_format_entries(entries))]
        
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
            content = arguments.get("content")
            section = arguments.get("section")
            tags = arguments.get("tags")
            result = await asyncio.to_thread(edit_entry, root, entry_id, content, section, tags)
            if result:
                return [TextContent(type="text", text=f"Updated {entry_id}")]
            return [TextContent(type="text", text=f"Entry {entry_id} not found")]
        
        elif name == "rememb_delete":
            entry_id = arguments["entry_id"]
            if await asyncio.to_thread(delete_entry, root, entry_id):
                return [TextContent(type="text", text=f"Deleted {entry_id}")]
            return [TextContent(type="text", text=f"Entry {entry_id} not found")]
        
        elif name == "rememb_clear":
            confirm = arguments.get("confirm", False)
            if not confirm:
                return [TextContent(type="text", text="Clear cancelled. Set confirm=true to proceed.")]
            count = await asyncio.to_thread(lambda: clear_entries(root, confirm=True))
            return [TextContent(type="text", text=f"Cleared {count} entries")]
        
        elif name == "rememb_init":
            if await asyncio.to_thread(is_initialized, root):
                return [TextContent(type="text", text=f"Already initialized at {root / '.rememb'}")]
            project_name = arguments.get("project_name", "")
            rememb_path = await asyncio.to_thread(init, root, project_name)
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
            description="Read all memory entries or filter by section. Use this at the start of every session to load context.",
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
            description="Search memory entries by content or tags using semantic similarity.",
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
            description="Save a new memory entry. Use this when you learn something worth remembering.",
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
            description="Modify an existing memory entry by ID.",
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
            description="Remove a memory entry by ID.",
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
            description="Delete ALL memory entries. Use with caution.",
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
            name="rememb_init",
            description="Initialize rememb memory store in current directory.",
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
