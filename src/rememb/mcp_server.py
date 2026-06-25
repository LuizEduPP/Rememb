from __future__ import annotations

import asyncio
import warnings
from pathlib import Path
from typing import Any

from rememb.config import DEFAULT_SECTIONS
from rememb.store import (
    agent_summarize_hint,
    clear_entries,
    get_entry,
    list_entry_tags,
    read_recent_entries,
    consolidate_entries,
    diff_entry_versions,
    delete_entries,
    delete_entry,
    edit_entries,
    edit_entry,
    format_entries,
    get_config,
    get_stats,
    init,
    list_entry_versions,
    read_entries,
    read_entries_page,
    restore_deleted_entry,
    restore_entry_version,
    search_entries,
    write_entries,
    write_entry,
)
from rememb.exceptions import RemembError, rememb_error_response_text
from rememb.utils import (
    _validate_entry_id,
    ensure_global_root,
    global_root,
    is_initialized,
    list_skill_definitions,
    load_skill_definition,
)


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
                    "Install with: pip install rememb"
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
    """Get global root path with cache invalidation.

    Returns:
        Global root path
    """
    root = global_root()

    if not is_initialized(root):
        init(root, project_name="global", global_mode=True)

    if not is_initialized(root):
        raise RemembError("Global rememb not initialized.")

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
        return list(get_config(root)["sections"])
    except Exception:
        return list(DEFAULT_SECTIONS)


def _get_default_mcp_section() -> str:
    sections = _get_mcp_sections()
    if "context" in sections:
        return "context"
    return sections[0]


def _tool_error_text(exc: Exception) -> str:
    if isinstance(exc, RemembError):
        return f"Error: {rememb_error_response_text(exc)}"
    return f"Unexpected error: {exc}"


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

    async def rememb_get():
        entry_id = arguments["entry_id"]
        if not _validate_entry_id(entry_id):
            return [TextContent(type="text", text=f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")]
        include_deleted = arguments.get("include_deleted", False)
        max_chars = arguments.get("max_chars")
        entry = await asyncio.to_thread(get_entry, root, entry_id, include_deleted=include_deleted)
        if entry is None:
            return [TextContent(type="text", text=f"Entry {entry_id} not found")]
        body = format_entries([entry], include_id=True, max_chars=max_chars)
        return [TextContent(type="text", text=body)]

    async def rememb_recent():
        limit = arguments.get("limit", 10)
        section = arguments.get("section")
        include_deleted = arguments.get("include_deleted", False)
        max_chars = arguments.get("max_chars")
        entries = await asyncio.to_thread(
            read_recent_entries,
            root,
            limit=limit,
            section=section,
            include_deleted=include_deleted,
        )
        body = format_entries(entries, include_id=True, max_chars=max_chars)
        hint = agent_summarize_hint(len(entries))
        return [TextContent(type="text", text=f"{body}{hint}")]

    async def rememb_list_tags():
        limit = arguments.get("limit", 50)
        include_deleted = arguments.get("include_deleted", False)
        tags = await asyncio.to_thread(list_entry_tags, root, include_deleted=include_deleted, limit=limit)
        if not tags:
            return [TextContent(type="text", text="No tags found.")]
        lines = ["Tags (count):"]
        lines.extend(f"- {item['tag']}: {item['count']}" for item in tags)
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_read():
        section = arguments.get("section")
        include_deleted = arguments.get("include_deleted", False)
        max_chars = arguments.get("max_chars")
        entries = await asyncio.to_thread(read_entries, root, section, include_deleted=include_deleted)
        body = format_entries(entries, include_id=True, max_chars=max_chars)
        hint = agent_summarize_hint(len(entries))
        return [TextContent(type="text", text=f"{body}{hint}")]

    async def rememb_read_page():
        section = arguments.get("section")
        tag = arguments.get("tag")
        include_deleted = arguments.get("include_deleted", False)
        offset = arguments.get("offset", 0)
        limit = arguments.get("limit", 100)
        sort_by = arguments.get("sort_by", "storage")
        descending = arguments.get("descending", False)
        max_chars = arguments.get("max_chars")
        page = await asyncio.to_thread(
            read_entries_page,
            root,
            section,
            tag=tag,
            include_deleted=include_deleted,
            offset=offset,
            limit=limit,
            sort_by=sort_by,
            descending=descending,
        )
        header = (
            f"Page {page['offset']}..{page['next_offset']} of {page['total']} "
            f"(limit={page['limit']}, has_more={page['has_more']})"
        )
        body = format_entries(page["items"], include_id=True, max_chars=max_chars)
        hint = agent_summarize_hint(len(page["items"]), has_more=page["has_more"])
        return [TextContent(type="text", text=f"{header}\n\n{body}{hint}")]

    async def rememb_search():
        query = arguments["query"]
        top_k = arguments.get("top_k", 5)
        section = arguments.get("section")
        tag = arguments.get("tag")
        include_deleted = arguments.get("include_deleted", False)
        max_chars = arguments.get("max_chars")
        entries = await asyncio.to_thread(search_entries, root, query, top_k, section, tag, include_deleted=include_deleted)
        body = format_entries(entries, include_id=True, include_score=True, max_chars=max_chars)
        hint = agent_summarize_hint(len(entries))
        return [TextContent(type="text", text=f"{body}{hint}")]

    async def rememb_versions():
        entry_id = arguments["entry_id"]
        if not _validate_entry_id(entry_id):
            return [TextContent(type="text", text=f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")]
        include_deleted = arguments.get("include_deleted", True)
        versions = await asyncio.to_thread(list_entry_versions, root, entry_id, include_deleted=include_deleted)
        if not versions:
            return [TextContent(type="text", text=f"Entry {entry_id} not found")]
        lines = [f"Versions for {entry_id} ({len(versions)} total):"]
        for revision in versions:
            deleted_marker = " [deleted]" if str(revision.get("deleted_at", "")).strip() else ""
            tags = ", ".join(revision.get("tags", [])) if isinstance(revision.get("tags"), list) else ""
            lines.append(
                f"- v{revision['version']} section={revision.get('section', '')}{deleted_marker}"
                f" tags=[{tags}] updated={revision.get('updated_at', '')}"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_restore():
        entry_id = arguments["entry_id"]
        if not _validate_entry_id(entry_id):
            return [TextContent(type="text", text=f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")]
        version = arguments.get("version")
        if version is None:
            restored = await asyncio.to_thread(restore_deleted_entry, root, entry_id)
            if restored is None:
                return [TextContent(type="text", text=f"Deleted entry {entry_id} not found")]
            return [TextContent(type="text", text=f"Restored deleted entry {entry_id} (now v{restored['version']})")]
        restored = await asyncio.to_thread(restore_entry_version, root, entry_id, version)
        if restored is None:
            return [TextContent(type="text", text=f"Entry {entry_id} or version {version} not found")]
        return [TextContent(type="text", text=f"Restored {entry_id} to version {version} (now v{restored['version']})")]

    async def rememb_diff():
        entry_id = arguments["entry_id"]
        if not _validate_entry_id(entry_id):
            return [TextContent(type="text", text=f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")]
        from_version = arguments["from_version"]
        to_version = arguments["to_version"]
        result = await asyncio.to_thread(diff_entry_versions, root, entry_id, from_version, to_version)
        if result is None:
            return [TextContent(type="text", text=f"Entry {entry_id} or requested versions not found")]
        diff_text = result["diff"] or "(no content changes)"
        return [TextContent(type="text", text=f"Diff {entry_id} v{from_version} -> v{to_version}\n\n{diff_text}")]

    async def rememb_write():
        entries = arguments.get("entries")
        if entries is not None:
            if not isinstance(entries, list) or not entries:
                return [TextContent(type="text", text="Provide a non-empty entries array.")]
            default_section = _get_default_mcp_section()
            prepared_entries: list[dict[str, Any]] = []
            for item in entries:
                if not isinstance(item, dict):
                    return [TextContent(type="text", text="Each batch entry must be an object.")]
                if item.get("content") is None:
                    return [TextContent(type="text", text="Each batch entry must include content.")]
                prepared_entries.append(
                    {
                        "content": item["content"],
                        "section": item.get("section", default_section),
                        "tags": item.get("tags", []),
                    }
                )
            created = await asyncio.to_thread(write_entries, root, prepared_entries, True)
            summary = "\n".join(f"- Saved [{entry['section']}] id={entry['id']}" for entry in created)
            return [TextContent(type="text", text=f"Saved {len(created)} entries\n{summary}")]

        content = arguments.get("content")
        if content is None:
            return [TextContent(type="text", text="Provide content for a single entry or entries for batch write.")]
        section = arguments.get("section", _get_default_mcp_section())
        tags = arguments.get("tags", [])
        entry = await asyncio.to_thread(
            write_entry,
            root,
            section,
            content,
            tags,
            True,
        )
        return [TextContent(type="text", text=f"Saved [{entry['section']}] id={entry['id']}")]

    async def rememb_edit():
        updates = arguments.get("updates")
        if updates is not None:
            if not isinstance(updates, list) or not updates:
                return [TextContent(type="text", text="Provide a non-empty updates array.")]
            for update in updates:
                if not isinstance(update, dict):
                    return [TextContent(type="text", text="Each batch update must be an object.")]
                entry_id = update.get("entry_id")
                if entry_id is None or not _validate_entry_id(entry_id):
                    return [TextContent(type="text", text=f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")]
                if update.get("content") is None and update.get("section") is None and update.get("tags") is None:
                    return [TextContent(type="text", text=f"Provide at least one field to update for {entry_id}: content, section, or tags.")]
            results = await asyncio.to_thread(edit_entries, root, updates)
            lines = []
            updated_count = 0
            for update, result in zip(updates, results):
                if result:
                    updated_count += 1
                    lines.append(f"- Updated {update['entry_id']}")
                else:
                    lines.append(f"- Entry {update['entry_id']} not found")
            return [TextContent(type="text", text=f"Processed {len(updates)} updates ({updated_count} updated)\n" + "\n".join(lines))]

        entry_id = arguments["entry_id"]
        if not _validate_entry_id(entry_id):
            return [TextContent(type="text", text=f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")]
        content = arguments.get("content")
        section = arguments.get("section")
        tags = arguments.get("tags")
        if content is None and section is None and tags is None:
            return [TextContent(type="text", text="Provide at least one field to update: content, section, or tags.")]
        result = await asyncio.to_thread(
            edit_entry,
            root,
            entry_id,
            content,
            section,
            tags,
        )
        if result:
            return [TextContent(type="text", text=f"Updated {entry_id}")]
        return [TextContent(type="text", text=f"Entry {entry_id} not found")]

    async def rememb_delete():
        entry_ids = arguments.get("entry_ids")
        if entry_ids is not None:
            if not isinstance(entry_ids, list) or not entry_ids:
                return [TextContent(type="text", text="Provide a non-empty entry_ids array.")]
            for entry_id in entry_ids:
                if not _validate_entry_id(entry_id):
                    return [TextContent(type="text", text=f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")]
            deleted_ids = await asyncio.to_thread(delete_entries, root, entry_ids)
            deleted_set = set(deleted_ids)
            lines = []
            for entry_id in entry_ids:
                if entry_id in deleted_set:
                    lines.append(f"- Deleted {entry_id}")
                else:
                    lines.append(f"- Entry {entry_id} not found")
            return [TextContent(type="text", text=f"Processed {len(entry_ids)} deletions ({len(deleted_ids)} deleted)\n" + "\n".join(lines))]

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
            f"Deleted entries: {stats.get('deleted_total', 0)}",
            f"Memory size: {stats['size_kb']} KB",
            f"Oldest entry: {stats['oldest']}",
            f"Newest entry: {stats['newest']}",
            "",
        ] + [f"{sec}: {count}" for sec, count in stats["by_section"].items()]
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_consolidate():
        section = arguments.get("section")
        result = await asyncio.to_thread(
            consolidate_entries,
            root,
            section,
        )
        target = result["section"] if result["section"] else "all sections"
        return [TextContent(
            type="text",
            text=(
                f"Consolidation completed for {target}. "
                f"Using mode=exact. "
                f"Removed {result['removed_count']} duplicate entries "
                f"({result['total_before']} -> {result['total_after']})."
            ),
        )]


    async def rememb_list_skills():
        skills = await asyncio.to_thread(list_skill_definitions)
        if not skills:
            return [TextContent(type="text", text="No bundled rememb skills found in the installed package.")]

        lines = []
        for skill in skills:
            lines.append(
                f"- {skill['name']} (id={skill['id']})\n"
                f"  path: {skill['path']}\n"
                f"  description: {skill['description']}"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_use_skill():
        skill = arguments["skill"]
        loaded = await asyncio.to_thread(load_skill_definition, skill)
        if not loaded:
            return [TextContent(type="text", text=f"Skill '{skill}' not found or is ambiguous. Use rememb_list_skills to inspect available local skills.")]

        body = loaded.get("content", "").strip()
        return [TextContent(
            type="text",
            text=(
                f"Skill: {loaded['name']}\n"
                f"ID: {loaded['id']}\n"
                f"Path: {loaded['path']}\n"
                f"Description: {loaded['description']}\n\n"
                f"{body}"
            ).strip(),
        )]

    tool_handlers = {
        "rememb_get": rememb_get,
        "rememb_recent": rememb_recent,
        "rememb_list_tags": rememb_list_tags,
        "rememb_read": rememb_read,
        "rememb_read_page": rememb_read_page,
        "rememb_search": rememb_search,
        "rememb_versions": rememb_versions,
        "rememb_restore": rememb_restore,
        "rememb_diff": rememb_diff,
        "rememb_write": rememb_write,
        "rememb_edit": rememb_edit,
        "rememb_delete": rememb_delete,
        "rememb_clear": rememb_clear,
        "rememb_stats": rememb_stats,
        "rememb_consolidate": rememb_consolidate,
        "rememb_list_skills": rememb_list_skills,
        "rememb_use_skill": rememb_use_skill,
    }

    handler = tool_handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    try:
        return await handler()
    except RemembError as e:
        return [TextContent(type="text", text=_tool_error_text(e))]
    except Exception as e:
        return [TextContent(type="text", text=_tool_error_text(e))]


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
            name="rememb_get",
            description="Fetch one memory entry by ID with full content. Safe, read-only. Use after rememb_search or rememb_recent when you already know the entry ID.",
            properties={
                "entry_id": {
                    "type": "string",
                    "description": "Entry ID (8 hex characters)",
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include the entry even if it is soft-deleted",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Optional mechanical cap on content characters",
                },
            },
            required=["entry_id"],
        ),
        _tool(
            name="rememb_recent",
            description="Return recently updated entries, newest first. Safe, read-only. Useful for catching up on what changed since the last session.",
            properties={
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of entries to return",
                },
                "section": {
                    "type": "string",
                    "enum": sections,
                    "description": f"Optional section filter: {', '.join(sections)}",
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include soft-deleted entries",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Optional mechanical cap on content characters per entry",
                },
            },
        ),
        _tool(
            name="rememb_list_tags",
            description="List tags used in the store with usage counts. Safe, read-only. Use to discover filters before rememb_search or rememb_read_page.",
            properties={
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Maximum number of tags to return",
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include tags from soft-deleted entries",
                },
            },
        ),
        _tool(
            name="rememb_read",
            description="Read all memory entries or filter by section. Safe, read-only operation with no side effects. Returns full entry content; summarize task-relevant facts in your working context after large reads.",
            properties={
                "section": {
                    "type": "string",
                    "enum": sections,
                    "description": f"Filter by section: {', '.join(sections)}",
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include soft-deleted entries in the response",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Optional mechanical cap on content characters per entry",
                },
            },
        ),
        _tool(
            name="rememb_read_page",
            description="Read a paginated slice of entries with optional section or tag filtering. Returns full entry content; summarize task-relevant facts in your working context after each page.",
            properties={
                "section": {
                    "type": "string",
                    "enum": sections,
                    "description": f"Optional section filter: {', '.join(sections)}",
                },
                "tag": {
                    "type": "string",
                    "description": "Optional exact tag filter applied before pagination",
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include soft-deleted entries in the response",
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "description": "Zero-based page offset",
                },
                "limit": {
                    "type": "integer",
                    "default": 100,
                    "description": "Maximum entries to return",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["storage", "recent"],
                    "default": "storage",
                    "description": "Sort order before pagination",
                },
                "descending": {
                    "type": "boolean",
                    "default": False,
                    "description": "Reverse the selected sort order",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Optional mechanical cap on content characters per entry",
                },
            },
        ),
        _tool(
            name="rememb_search",
            description="Keyword and token search over memory entries. Safe, read-only operation. Returns top_k lexical matches with full entry content; summarize task-relevant facts in your working context.",
            properties={
                "query": {
                    "type": "string",
                    "description": "Search query - keywords or short phrases",
                },
                "section": {
                    "type": "string",
                    "enum": sections,
                    "description": f"Optional section filter: {', '.join(sections)}",
                },
                "tag": {
                    "type": "string",
                    "description": "Optional exact tag filter applied before keyword search",
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include soft-deleted entries in the search corpus and results",
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "Maximum number of results",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Optional mechanical cap on content characters per entry",
                },
            },
            required=["query"],
        ),
        _tool(
            name="rememb_versions",
            description="List all revisions known for an entry, including prior content snapshots and deleted states when requested. Safe, read-only operation.",
            properties={
                "entry_id": {
                    "type": "string",
                    "description": "Entry ID (8 hex characters)",
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": True,
                    "description": "Keep deleted revisions visible when the current entry is soft-deleted",
                },
            },
            required=["entry_id"],
        ),
        _tool(
            name="rememb_restore",
            description="Restore a soft-deleted entry, or restore a specific prior version as the new current head. Restores are non-destructive: they append a new head revision rather than rewriting history.",
            properties={
                "entry_id": {
                    "type": "string",
                    "description": "Entry ID (8 hex characters)",
                },
                "version": {
                    "type": "integer",
                    "description": "Optional historical version to restore. If omitted, restores the current soft-deleted entry.",
                },
            },
            required=["entry_id"],
        ),
        _tool(
            name="rememb_diff",
            description="Show a unified diff between two revisions of the same entry. Safe, read-only operation.",
            properties={
                "entry_id": {
                    "type": "string",
                    "description": "Entry ID (8 hex characters)",
                },
                "from_version": {
                    "type": "integer",
                    "description": "Older or source version",
                },
                "to_version": {
                    "type": "integer",
                    "description": "Newer or target version",
                },
            },
            required=["entry_id", "from_version", "to_version"],
        ),
        _tool(
            name="rememb_write",
            description="Save a new memory entry or multiple entries in one call. Existing entries are never overwritten. Use rememb_edit to update an existing entry by ID.",
            properties={
                "content": {
                    "type": "string",
                    "description": "Content to remember (1-3 sentences)",
                },
                "entries": {
                    "type": "array",
                    "description": "Batch write payloads. Each item accepts content and optional section/tags.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "Content to remember (1-3 sentences)",
                            },
                            "section": {
                                "type": "string",
                                "enum": sections,
                                "description": f"Section: {', '.join(sections)}",
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Tags to categorize this entry",
                            },
                        },
                        "required": ["content"],
                    },
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
            },
        ),
        _tool(
            name="rememb_edit",
            description="Update one existing memory entry by ID or multiple entries in one call via updates[]. Modifies only the fields provided (content, section, or tags) — omitted fields are unchanged. Non-destructive: entries are updated, not deleted and recreated. Use rememb_write to create new entries, rememb_delete to permanently remove them.",
            properties={
                "entry_id": {
                    "type": "string",
                    "description": "Entry ID (8 hex characters)",
                },
                "updates": {
                    "type": "array",
                    "description": "Batch update payloads. Each item requires entry_id and at least one of content, section, or tags.",
                    "items": {
                        "type": "object",
                        "properties": {
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
                        "required": ["entry_id"],
                    },
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
        ),
        _tool(
            name="rememb_delete",
            description="Soft-delete one memory entry by its ID or multiple entries via entry_ids[]. Deleted entries are hidden by default from reads and search, but can be restored later. Use rememb_restore to undo a deletion. Use rememb_clear to permanently delete all entries at once.",
            properties={
                "entry_id": {
                    "type": "string",
                    "description": "Entry ID to delete",
                },
                "entry_ids": {
                    "type": "array",
                    "description": "Batch deletion IDs.",
                    "items": {
                        "type": "string",
                    },
                }
            },
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
            description="Consolidate literal duplicate entries and merge metadata (tags and access data). Exact normalized-content match only; review near-duplicates with the agent before consolidating.",
            properties={
                "section": {
                    "type": "string",
                    "enum": sections,
                    "description": f"Optional section filter: {', '.join(sections)}",
                },
            },
        ),
        _tool(
            name="rememb_list_skills",
            description="List bundled rememb skills discovered from the installed package contents. Safe, read-only operation.",
            properties={},
        ),
        _tool(
            name="rememb_use_skill",
            description="Load one bundled rememb skill by identifier or exact declared name and return its instructions. Safe, read-only operation. Use rememb_list_skills first to inspect available skills.",
            properties={
                "skill": {
                    "type": "string",
                    "description": "Skill identifier (directory name) or exact declared skill name",
                }
            },
            required=["skill"],
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
