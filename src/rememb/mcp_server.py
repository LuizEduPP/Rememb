from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from rememb.config import (
    DEFAULT_MCP_SECTION,
    DEFAULT_MESSAGE_PATH,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_RECENT_LIMIT,
    DEFAULT_SEARCH_TOP_K,
    DEFAULT_SECTIONS,
    DEFAULT_HOST,
    DEFAULT_SSE_PATH,
    DEFAULT_SSE_PORT,
    DEFAULT_TAG_LIMIT,
    ENTRY_ID_LENGTH,
    SEARCH_EXCERPT_CHARS,
)
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
    list_entry_versions,
    read_entries,
    read_entries_page,
    restore_deleted_entry,
    restore_entry_version,
    search_entries,
    write_entries,
    write_entry,
)
from rememb.exceptions import RemembError, RemembValidationError, rememb_error_response_text
from rememb.mcp_stores import (
    GLOBAL_STORE_ID,
    StoreRegistry,
    ensure_store_root,
)
from rememb.utils import (
    is_initialized,
    list_skill_definitions,
    load_skill_definition,
    parse_int,
    require_entry_id,
)


class MCPContext:
    """Lazy MCP SDK import cache and per-process store registry."""

    def __init__(self):
        self._mcp_modules = None
        self._store_registry = StoreRegistry()

    def get_store_registry(self) -> StoreRegistry:
        return self._store_registry

    def get_mcp_modules(self):
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
                    "MCP server requires: pip install 'mcp>=1.0.0,<2'\n"
                    "Install with: pip install rememb"
                ) from e
        return self._mcp_modules


_mcp_context = MCPContext()


def configure_mcp_stores(projects: list[Path] | None = None) -> StoreRegistry:
    """Configure global + optional project stores for this MCP process."""
    registry = _mcp_context.get_store_registry()
    registry.configure(projects)
    return registry


def _get_root(store_id: str | None = None) -> Path:
    """Resolve and initialize the selected MCP store root."""
    return ensure_store_root(_mcp_context.get_store_registry().get(store_id))


def _get_mcp_sections() -> list[str]:
    """Return the union of section lists across configured stores."""
    try:
        registry = _mcp_context.get_store_registry()
        seen: list[str] = []
        for store in registry.all():
            try:
                if store.kind == "global":
                    root = _get_root(store.id)
                elif is_initialized(store.root):
                    root = store.root
                else:
                    continue
                for section in get_config(root)["sections"]:
                    if section not in seen:
                        seen.append(section)
            except Exception:
                continue
        return seen or list(DEFAULT_SECTIONS)
    except Exception:
        return list(DEFAULT_SECTIONS)


def _get_default_mcp_section() -> str:
    sections = _get_mcp_sections()
    if DEFAULT_MCP_SECTION in sections:
        return DEFAULT_MCP_SECTION
    return sections[0]


def _store_property() -> dict[str, Any]:
    registry = _mcp_context.get_store_registry()
    return {
        "type": "string",
        "enum": registry.ids(),
        "default": GLOBAL_STORE_ID,
        "description": (
            "Memory store id. 'global' is the ~/.rememb store. "
            "Other ids are project stores passed via repeated --project MCP args."
        ),
    }


def _with_store_prefix(store_id: str, text: str) -> str:
    registry = _mcp_context.get_store_registry()
    if len(registry) <= 1:
        return text
    return f"[store={store_id}]\n{text}"


def _tool_error_text(exc: Exception) -> str:
    if isinstance(exc, RemembError):
        return f"Error: {rememb_error_response_text(exc)}"
    return f"Unexpected error: {exc}"


def _text(cls, text: str):
    return [cls(type="text", text=text)]


def _need_id(entry_id, reply):
    try:
        require_entry_id(entry_id)
    except RemembValidationError as exc:
        return reply(str(exc))
    return None


def _memory_text(
    reply,
    entries,
    *,
    include_score: bool = False,
    max_chars=None,
    header: str | None = None,
    has_more: bool = False,
):
    body = format_entries(entries, include_id=True, include_score=include_score, max_chars=max_chars)
    hint = agent_summarize_hint(len(entries), has_more=has_more)
    payload = f"{header}\n\n{body}{hint}" if header else f"{body}{hint}"
    return reply(payload)


def _search_max_chars(root: Path, raw) -> int | None:
    if raw is None:
        return int(get_config(root).get("search_excerpt_chars", SEARCH_EXCERPT_CHARS))
    value = parse_int(raw, name="max_chars", minimum=0)
    if value == 0:
        return None
    return value


def _no_update_fields(content, section, tags) -> bool:
    return content is None and section is None and tags is None


def _batch_status_lines(items, found, *, ok: str, missing: str, key: str | None = None) -> tuple[int, list[str]]:
    lines: list[str] = []
    count = 0
    for item in items:
        item_id = item[key] if key else item
        if item_id in found:
            count += 1
            lines.append(ok.format(item_id))
        else:
            lines.append(missing.format(item_id))
    return count, lines


async def _handle_tool(name: str, arguments: dict[str, Any], TextContent):
    """Handle MCP tool invocation.

    Args:
        name: Tool name (e.g., 'rememb_read', 'rememb_write')
        arguments: Tool arguments dictionary
        TextContent: TextContent class for responses

    Returns:
        List of TextContent responses
    """
    store_id = arguments.get("store", GLOBAL_STORE_ID)
    if isinstance(store_id, str):
        store_id = store_id.strip() or GLOBAL_STORE_ID
    else:
        store_id = GLOBAL_STORE_ID

    reply = lambda text: _text(TextContent, _with_store_prefix(store_id, text))
    arg = arguments.get

    root: Path | None = None
    if name not in {"rememb_list_skills", "rememb_use_skill", "rememb_list_stores"}:
        try:
            root = await asyncio.to_thread(_get_root, store_id)
        except Exception as e:
            return reply(_tool_error_text(e))

    def need_id(entry_id):
        return _need_id(entry_id, reply)

    def memory(entries, **kwargs):
        return _memory_text(reply, entries, **kwargs)

    def not_found(entry_id, extra=""):
        return reply(f"Entry {entry_id}{extra} not found")

    async def rememb_list_stores():
        registry = _mcp_context.get_store_registry()
        lines = ["Stores:"]
        for store in registry.all():
            initialized = await asyncio.to_thread(is_initialized, store.root)
            lines.append(
                f"- {store.id} ({store.kind}) path={store.root} initialized={initialized}"
            )
        return reply("\n".join(lines))

    async def rememb_get():
        entry_id = arguments["entry_id"]
        if err := need_id(entry_id):
            return err
        entry = await asyncio.to_thread(
            get_entry, root, entry_id, include_deleted=arg("include_deleted", False)
        )
        if entry is None:
            return not_found(entry_id)
        return memory([entry], max_chars=arg("max_chars"))

    async def rememb_recent():
        entries = await asyncio.to_thread(
            read_recent_entries,
            root,
            limit=arg("limit", DEFAULT_RECENT_LIMIT),
            section=arg("section"),
            include_deleted=arg("include_deleted", False),
        )
        return memory(entries, max_chars=arg("max_chars"))

    async def rememb_list_tags():
        tags = await asyncio.to_thread(
            list_entry_tags,
            root,
            include_deleted=arg("include_deleted", False),
            limit=arg("limit", DEFAULT_TAG_LIMIT),
        )
        if not tags:
            return reply("No tags found.")
        lines = ["Tags (count):"]
        lines.extend(f"- {item['tag']}: {item['count']}" for item in tags)
        return reply("\n".join(lines))

    async def rememb_read():
        entries = await asyncio.to_thread(
            read_entries, root, arg("section"), include_deleted=arg("include_deleted", False)
        )
        return memory(entries, max_chars=arg("max_chars"))

    async def rememb_read_page():
        page = await asyncio.to_thread(
            read_entries_page,
            root,
            arg("section"),
            tag=arg("tag"),
            include_deleted=arg("include_deleted", False),
            offset=arg("offset", 0),
            limit=arg("limit", DEFAULT_PAGE_LIMIT),
            sort_by=arg("sort_by", "storage"),
            descending=arg("descending", False),
        )
        header = (
            f"Page {page['offset']}..{page['next_offset']} of {page['total']} "
            f"(limit={page['limit']}, has_more={page['has_more']})"
        )
        return memory(page["items"], max_chars=arg("max_chars"), header=header, has_more=page["has_more"])

    async def rememb_search():
        entries = await asyncio.to_thread(
            search_entries,
            root,
            arguments["query"],
            arg("top_k", DEFAULT_SEARCH_TOP_K),
            arg("section"),
            arg("tag"),
            include_deleted=arg("include_deleted", False),
        )
        return memory(entries, include_score=True, max_chars=_search_max_chars(root, arg("max_chars")))

    async def rememb_versions():
        entry_id = arguments["entry_id"]
        if err := need_id(entry_id):
            return err
        versions = await asyncio.to_thread(
            list_entry_versions, root, entry_id, include_deleted=arg("include_deleted", True)
        )
        if not versions:
            return not_found(entry_id)
        lines = [f"Versions for {entry_id} ({len(versions)} total):"]
        for revision in versions:
            deleted_marker = " [deleted]" if str(revision.get("deleted_at", "")).strip() else ""
            tags = ", ".join(revision.get("tags", [])) if isinstance(revision.get("tags"), list) else ""
            lines.append(
                f"- v{revision['version']} section={revision.get('section', '')}{deleted_marker}"
                f" tags=[{tags}] updated={revision.get('updated_at', '')}"
            )
        return reply("\n".join(lines))

    async def rememb_restore():
        entry_id = arguments["entry_id"]
        if err := need_id(entry_id):
            return err
        version = arg("version")
        if version is None:
            restored = await asyncio.to_thread(restore_deleted_entry, root, entry_id)
            if restored is None:
                return reply(f"Deleted entry {entry_id} not found")
            return reply(f"Restored deleted entry {entry_id} (now v{restored['version']})")
        restored = await asyncio.to_thread(restore_entry_version, root, entry_id, version)
        if restored is None:
            return not_found(entry_id, extra=f" or version {version}")
        return reply(f"Restored {entry_id} to version {version} (now v{restored['version']})")

    async def rememb_diff():
        entry_id = arguments["entry_id"]
        if err := need_id(entry_id):
            return err
        from_version = arguments["from_version"]
        to_version = arguments["to_version"]
        result = await asyncio.to_thread(diff_entry_versions, root, entry_id, from_version, to_version)
        if result is None:
            return not_found(entry_id, extra=" or requested versions")
        diff_text = result["diff"] or "(no content changes)"
        return reply(f"Diff {entry_id} v{from_version} -> v{to_version}\n\n{diff_text}")

    async def rememb_write():
        entries = arg("entries")
        default_section = _get_default_mcp_section()
        if entries is not None:
            if not isinstance(entries, list) or not entries:
                return reply("Provide a non-empty entries array.")
            prepared_entries: list[dict[str, Any]] = []
            for item in entries:
                if not isinstance(item, dict):
                    return reply("Each batch entry must be an object.")
                if item.get("content") is None:
                    return reply("Each batch entry must include content.")
                prepared_entries.append(
                    {
                        "content": item["content"],
                        "section": item.get("section", default_section),
                        "tags": item.get("tags", []),
                    }
                )
            created = await asyncio.to_thread(write_entries, root, prepared_entries, True)
            summary = "\n".join(f"- Saved [{entry['section']}] id={entry['id']}" for entry in created)
            return reply(f"Saved {len(created)} entries\n{summary}")

        content = arg("content")
        if content is None:
            return reply("Provide content for a single entry or entries for batch write.")
        entry = await asyncio.to_thread(
            write_entry,
            root,
            arg("section", default_section),
            content,
            arg("tags", []),
            True,
        )
        return reply(f"Saved [{entry['section']}] id={entry['id']}")

    async def rememb_edit():
        updates = arg("updates")
        if updates is not None:
            if not isinstance(updates, list) or not updates:
                return reply("Provide a non-empty updates array.")
            for update in updates:
                if not isinstance(update, dict):
                    return reply("Each batch update must be an object.")
                entry_id = update.get("entry_id")
                if err := need_id(entry_id):
                    return err
                if _no_update_fields(update.get("content"), update.get("section"), update.get("tags")):
                    return reply(f"Provide at least one field to update for {entry_id}: content, section, or tags.")
            results = await asyncio.to_thread(edit_entries, root, updates)
            found = {update["entry_id"] for update, result in zip(updates, results) if result}
            count, lines = _batch_status_lines(
                updates, found, ok="- Updated {}", missing="- Entry {} not found", key="entry_id"
            )
            return reply(f"Processed {len(updates)} updates ({count} updated)\n" + "\n".join(lines))

        entry_id = arguments["entry_id"]
        if err := need_id(entry_id):
            return err
        content, section, tags = arg("content"), arg("section"), arg("tags")
        if _no_update_fields(content, section, tags):
            return reply("Provide at least one field to update: content, section, or tags.")
        result = await asyncio.to_thread(edit_entry, root, entry_id, content, section, tags)
        if result:
            return reply(f"Updated {entry_id}")
        return not_found(entry_id)

    async def rememb_delete():
        entry_ids = arg("entry_ids")
        if entry_ids is not None:
            if not isinstance(entry_ids, list) or not entry_ids:
                return reply("Provide a non-empty entry_ids array.")
            for entry_id in entry_ids:
                if err := need_id(entry_id):
                    return err
            deleted_ids = set(await asyncio.to_thread(delete_entries, root, entry_ids))
            count, lines = _batch_status_lines(
                entry_ids, deleted_ids, ok="- Deleted {}", missing="- Entry {} not found"
            )
            return reply(f"Processed {len(entry_ids)} deletions ({count} deleted)\n" + "\n".join(lines))

        entry_id = arguments["entry_id"]
        if err := need_id(entry_id):
            return err
        if await asyncio.to_thread(delete_entry, root, entry_id):
            return reply(f"Deleted {entry_id}")
        return not_found(entry_id)

    async def rememb_clear():
        if not arg("confirm", False):
            return reply("Clear cancelled. Set confirm=true to proceed.")
        count = await asyncio.to_thread(clear_entries, root, confirm=True)
        return reply(f"Cleared {count} entries")

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
        return reply("\n".join(lines))

    async def rememb_consolidate():
        result = await asyncio.to_thread(consolidate_entries, root, arg("section"))
        target = result["section"] if result["section"] else "all sections"
        return reply(
            f"Consolidation completed for {target}. "
            f"Using mode=exact. "
            f"Removed {result['removed_count']} duplicate entries "
            f"({result['total_before']} -> {result['total_after']})."
        )

    async def rememb_list_skills():
        skills = await asyncio.to_thread(list_skill_definitions)
        if not skills:
            return reply("No bundled rememb skills found in the installed package.")
        lines = [
            f"- {skill['name']} (id={skill['id']})\n"
            f"  path: {skill['path']}\n"
            f"  description: {skill['description']}"
            for skill in skills
        ]
        return reply("\n".join(lines))

    async def rememb_use_skill():
        skill = arguments["skill"]
        loaded = await asyncio.to_thread(load_skill_definition, skill)
        if not loaded:
            return reply(
                f"Skill '{skill}' not found or is ambiguous. Use rememb_list_skills to inspect available local skills."
            )
        body = loaded.get("content", "").strip()
        return reply(
            (
                f"Skill: {loaded['name']}\n"
                f"ID: {loaded['id']}\n"
                f"Path: {loaded['path']}\n"
                f"Description: {loaded['description']}\n\n"
                f"{body}"
            ).strip(),
        )

    tool_handlers = {
        "rememb_list_stores": rememb_list_stores,
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
        return reply(f"Unknown tool: {name}")

    try:
        return await handler()
    except Exception as e:
        return reply(_tool_error_text(e))


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
        *,
        include_store: bool = True,
    ):
        props = dict(properties or {})
        if include_store:
            props = {"store": _store_property(), **props}
        return Tool(
            name=name,
            description=description,
            inputSchema=_schema(props, required),
        )

    sections = _get_mcp_sections()
    default_section = _get_default_mcp_section()
    joined = ", ".join(sections)

    def _entry_id(description: str | None = None) -> dict[str, Any]:
        return {
            "type": "string",
            "description": description or f"Entry ID ({ENTRY_ID_LENGTH} hex characters)",
        }

    def _include_deleted(default: bool = False, description: str = "Include soft-deleted entries") -> dict[str, Any]:
        return {"type": "boolean", "default": default, "description": description}

    def _max_chars(per_entry: bool = True) -> dict[str, Any]:
        suffix = " per entry" if per_entry else ""
        return {"type": "integer", "description": f"Optional mechanical cap on content characters{suffix}"}

    def _section(description: str, *, default: str | None = None) -> dict[str, Any]:
        prop: dict[str, Any] = {"type": "string", "enum": sections, "description": description}
        if default is not None:
            prop["default"] = default
        return prop

    def _limit(default: int, description: str) -> dict[str, Any]:
        return {"type": "integer", "default": default, "description": description}

    def _tag(description: str) -> dict[str, Any]:
        return {"type": "string", "description": description}

    def _tags(description: str) -> dict[str, Any]:
        return {"type": "array", "items": {"type": "string"}, "description": description}

    def _content(description: str) -> dict[str, Any]:
        return {"type": "string", "description": description}

    def _version(description: str) -> dict[str, Any]:
        return {"type": "integer", "description": description}

    def _array(description: str, items: dict[str, Any]) -> dict[str, Any]:
        return {"type": "array", "description": description, "items": items}

    write_content = _content("Content to remember (1-3 sentences)")
    write_section = _section(f"Section: {joined}")
    write_tags = _tags("Tags to categorize this entry")
    edit_content = _content("New content")
    edit_section = _section("Move to different section")
    edit_tags = _tags("Replace tags")
    filter_section = _section(f"Optional section filter: {joined}")

    return [
        _tool(
            name="rememb_list_stores",
            description=(
                "List configured memory stores for this MCP process: global (~/.rememb) "
                "plus any project stores passed via --project. Safe, read-only."
            ),
            properties={},
            include_store=False,
        ),
        _tool(
            name="rememb_get",
            description="Fetch one memory entry by ID with full content. Safe, read-only. Use after rememb_search or rememb_recent when you already know the entry ID.",
            properties={
                "entry_id": _entry_id(),
                "include_deleted": _include_deleted(description="Include the entry even if it is soft-deleted"),
                "max_chars": _max_chars(per_entry=False),
            },
            required=["entry_id"],
        ),
        _tool(
            name="rememb_recent",
            description="Return recently updated entries, newest first. Safe, read-only. Useful for catching up on what changed since the last session.",
            properties={
                "limit": _limit(DEFAULT_RECENT_LIMIT, "Maximum number of entries to return"),
                "section": filter_section,
                "include_deleted": _include_deleted(),
                "max_chars": _max_chars(),
            },
        ),
        _tool(
            name="rememb_list_tags",
            description="List tags used in the store with usage counts. Safe, read-only. Use to discover filters before rememb_search or rememb_read_page.",
            properties={
                "limit": _limit(DEFAULT_TAG_LIMIT, "Maximum number of tags to return"),
                "include_deleted": _include_deleted(description="Include tags from soft-deleted entries"),
            },
        ),
        _tool(
            name="rememb_read",
            description="Read all memory entries or filter by section. Safe, read-only operation with no side effects. Returns full entry content; summarize task-relevant facts in your working context after large reads.",
            properties={
                "section": _section(f"Filter by section: {joined}"),
                "include_deleted": _include_deleted(description="Include soft-deleted entries in the response"),
                "max_chars": _max_chars(),
            },
        ),
        _tool(
            name="rememb_read_page",
            description="Read a paginated slice of entries with optional section or tag filtering. Returns full entry content; summarize task-relevant facts in your working context after each page.",
            properties={
                "section": filter_section,
                "tag": _tag("Optional exact tag filter applied before pagination"),
                "include_deleted": _include_deleted(description="Include soft-deleted entries in the response"),
                "offset": _limit(0, "Zero-based page offset"),
                "limit": _limit(DEFAULT_PAGE_LIMIT, "Maximum entries to return"),
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
                "max_chars": _max_chars(),
            },
        ),
        _tool(
            name="rememb_search",
            description=(
                "Keyword and token search over memory entries. Safe, read-only. "
                "Returns id, score, tags, date, and a short excerpt. Use rememb_get for full body."
            ),
            properties={
                "query": {
                    "type": "string",
                    "description": "Search query - keywords or short phrases",
                },
                "section": filter_section,
                "tag": _tag("Optional exact tag filter applied before keyword search"),
                "include_deleted": _include_deleted(
                    description="Include soft-deleted entries in the search corpus and results"
                ),
                "top_k": _limit(DEFAULT_SEARCH_TOP_K, "Maximum number of results"),
                "max_chars": {
                    "type": "integer",
                    "description": (
                        f"Excerpt length per entry. Default {SEARCH_EXCERPT_CHARS}. "
                        "0 returns the full body."
                    ),
                },
            },
            required=["query"],
        ),
        _tool(
            name="rememb_versions",
            description="List all revisions known for an entry, including prior content snapshots and deleted states when requested. Safe, read-only operation.",
            properties={
                "entry_id": _entry_id(),
                "include_deleted": _include_deleted(
                    default=True,
                    description="Keep deleted revisions visible when the current entry is soft-deleted",
                ),
            },
            required=["entry_id"],
        ),
        _tool(
            name="rememb_restore",
            description="Restore a soft-deleted entry, or restore a specific prior version as the new current head. Restores are non-destructive: they append a new head revision rather than rewriting history.",
            properties={
                "entry_id": _entry_id(),
                "version": _version(
                    "Optional historical version to restore. If omitted, restores the current soft-deleted entry."
                ),
            },
            required=["entry_id"],
        ),
        _tool(
            name="rememb_diff",
            description="Show a unified diff between two revisions of the same entry. Safe, read-only operation.",
            properties={
                "entry_id": _entry_id(),
                "from_version": _version("Older or source version"),
                "to_version": _version("Newer or target version"),
            },
            required=["entry_id", "from_version", "to_version"],
        ),
        _tool(
            name="rememb_write",
            description="Save a new memory entry or multiple entries in one call. Existing entries are never overwritten. Use rememb_edit to update an existing entry by ID.",
            properties={
                "content": write_content,
                "entries": _array(
                    "Batch write payloads. Each item accepts content and optional section/tags.",
                    {
                        "type": "object",
                        "properties": {
                            "content": write_content,
                            "section": write_section,
                            "tags": write_tags,
                        },
                        "required": ["content"],
                    },
                ),
                "section": _section(f"Section: {joined}", default=default_section),
                "tags": write_tags,
            },
        ),
        _tool(
            name="rememb_edit",
            description="Update one existing memory entry by ID or multiple entries in one call via updates[]. Modifies only the fields provided (content, section, or tags) — omitted fields are unchanged. Non-destructive: entries are updated, not deleted and recreated. Use rememb_write to create new entries, rememb_delete to permanently remove them.",
            properties={
                "entry_id": _entry_id(),
                "updates": _array(
                    "Batch update payloads. Each item requires entry_id and at least one of content, section, or tags.",
                    {
                        "type": "object",
                        "properties": {
                            "entry_id": _entry_id(),
                            "content": edit_content,
                            "section": edit_section,
                            "tags": edit_tags,
                        },
                        "required": ["entry_id"],
                    },
                ),
                "content": edit_content,
                "section": edit_section,
                "tags": edit_tags,
            },
        ),
        _tool(
            name="rememb_delete",
            description="Soft-delete one memory entry by its ID or multiple entries via entry_ids[]. Deleted entries are hidden by default from reads and search, but can be restored later. Use rememb_restore to undo a deletion. Use rememb_clear to permanently delete all entries at once.",
            properties={
                "entry_id": _entry_id("Entry ID to delete"),
                "entry_ids": _array("Batch deletion IDs.", {"type": "string"}),
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
                "section": filter_section,
            },
        ),
        _tool(
            name="rememb_list_skills",
            description="List bundled rememb skills discovered from the installed package contents. Safe, read-only operation.",
            properties={},
            include_store=False,
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
            include_store=False,
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
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_SSE_PORT,
    projects: list[Path] | None = None,
):
    """Run the MCP server over stdio or a persistent local SSE transport."""
    if projects is not None:
        configure_mcp_stores(projects)
    else:
        _mcp_context.get_store_registry().ensure_configured()

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
