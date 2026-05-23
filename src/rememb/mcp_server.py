from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from rememb.config import DEFAULT_SECTIONS, DEFAULT_SEMANTIC_CONFLICT_THRESHOLD
from rememb.store import (
    build_handoff_package,
    compare_sessions,
    compare_workstreams,
    clear_entries,
    close_session,
    close_session_with_handoff,
    consolidate_entries,
    diff_entry_versions,
    delete_entries,
    delete_entry,
    edit_entries,
    edit_entry,
    format_entries,
    get_handoff_restore_context,
    get_review_session,
    get_review_workstream,
    get_workstream_state,
    list_handoffs,
    list_review_queue,
    list_workstream_queue,
    list_workstreams,
    open_workstream,
    get_config,
    get_stats,
    init,
    list_entry_versions,
    read_structured_handoff,
    read_entries,
    read_entries_page,
    resume_workstream,
    restore_deleted_entry,
    restore_entry_version,
    search_entries,
    start_session,
    update_review_status,
    update_workstream_state,
    write_handoff,
    write_entries,
    write_entry,
    write_structured_handoff,
    parse_handoff_restore_context,
)


_ENTRY_KIND_VALUES = ["memory", "decision", "state", "handoff", "artifact", "review"]
_ENTRY_ROLE_VALUES = ["essential", "optional", "supporting", "checkpoint", "final"]
_ACTOR_TYPE_VALUES = ["agent", "human", "system"]
_ENTRY_METADATA_PROPERTY_SCHEMAS = {
    "meta_schema_version": {
        "type": "integer",
        "minimum": 1,
        "description": "Optional schema version for structured entry metadata.",
    },
    "workstream_id": {
        "type": "string",
        "description": "Optional logical workstream identifier.",
    },
    "session_id": {
        "type": "string",
        "description": "Optional logical session identifier inside a workstream.",
    },
    "entry_kind": {
        "type": "string",
        "enum": _ENTRY_KIND_VALUES,
        "description": "Optional structured entry kind.",
    },
    "entry_role": {
        "type": "string",
        "enum": _ENTRY_ROLE_VALUES,
        "description": "Optional role of this entry inside the operational flow.",
    },
    "actor_type": {
        "type": "string",
        "enum": _ACTOR_TYPE_VALUES,
        "description": "Optional producer type for this entry.",
    },
    "actor_id": {
        "type": "string",
        "description": "Optional producer identifier for this entry.",
    },
    "parent_entry_id": {
        "type": "string",
        "description": "Optional parent entry ID for chaining related entries.",
    },
    "supersedes_entry_id": {
        "type": "string",
        "description": "Optional entry ID that this entry supersedes.",
    },
    "related_entry_ids": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Optional related entry IDs.",
    },
    "structured": {
        "type": "object",
        "description": "Optional structured payload for agent-first operational context.",
    },
}


def _with_entry_metadata_fields(base_properties: dict[str, Any]) -> dict[str, Any]:
    properties = dict(base_properties)
    properties.update(_ENTRY_METADATA_PROPERTY_SCHEMAS)
    return properties
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

    async def rememb_read():
        section = arguments.get("section")
        include_deleted = arguments.get("include_deleted", False)
        max_chars = arguments.get("max_chars")
        summary_only = arguments.get("summary_only", False)
        entries = await asyncio.to_thread(read_entries, root, section, include_deleted=include_deleted)
        return [TextContent(type="text", text=format_entries(entries, include_id=True, max_chars=max_chars, summary_only=summary_only))]

    async def rememb_read_page():
        section = arguments.get("section")
        tag = arguments.get("tag")
        include_deleted = arguments.get("include_deleted", False)
        offset = arguments.get("offset", 0)
        limit = arguments.get("limit", 100)
        sort_by = arguments.get("sort_by", "storage")
        descending = arguments.get("descending", False)
        max_chars = arguments.get("max_chars")
        summary_only = arguments.get("summary_only", True)
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
        body = format_entries(page["items"], include_id=True, max_chars=max_chars, summary_only=summary_only)
        return [TextContent(type="text", text=f"{header}\n\n{body}")]

    async def rememb_search():
        query = arguments["query"]
        top_k = arguments.get("top_k", 5)
        section = arguments.get("section")
        tag = arguments.get("tag")
        include_deleted = arguments.get("include_deleted", False)
        max_chars = arguments.get("max_chars")
        summary_only = arguments.get("summary_only", True)
        entries = await asyncio.to_thread(search_entries, root, query, top_k, section, tag, include_deleted=include_deleted)
        return [TextContent(type="text", text=format_entries(entries, include_id=True, include_score=True, max_chars=max_chars, summary_only=summary_only))]

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

    async def rememb_handoff_generate():
        goal = arguments.get("goal")
        if not goal or not str(goal).strip():
            return [TextContent(type="text", text="Provide goal for the handoff.")]
        entry = await asyncio.to_thread(
            write_handoff,
            root,
            str(goal),
            summary=arguments.get("summary"),
            current_state=arguments.get("current_state"),
            open_loops=arguments.get("open_loops"),
            next_steps=arguments.get("next_steps"),
            related_entries=arguments.get("related_entries"),
            restore_section=arguments.get("restore_section", "actions"),
            restore_query=arguments.get("restore_query"),
            include_deleted=arguments.get("include_deleted", False),
            tags=arguments.get("tags"),
            workstream_id=arguments.get("workstream_id"),
            session_id=arguments.get("session_id"),
        )
        return [TextContent(type="text", text=f"Saved handoff [{entry['section']}] id={entry['id']}")]

    async def rememb_handoff_list():
        limit = arguments.get("limit")
        include_deleted = arguments.get("include_deleted", False)
        handoffs = await asyncio.to_thread(list_handoffs, root, limit=limit, include_deleted=include_deleted)
        if not handoffs:
            return [TextContent(type="text", text="No handoffs found.")]
        lines = ["Recent handoffs:"]
        for handoff in handoffs:
            parsed = parse_handoff_restore_context(handoff)
            goal = parsed.get("goal") or "(no goal)"
            lines.append(f"- {handoff['id']} goal={goal} section={handoff.get('section', '')}")
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_handoff_restore_context():
        entry_id = arguments["entry_id"]
        if not _validate_entry_id(entry_id):
            return [TextContent(type="text", text=f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")]
        include_deleted = arguments.get("include_deleted", True)
        try:
            parsed = await asyncio.to_thread(get_handoff_restore_context, root, entry_id, include_deleted=include_deleted)
        except RemembError:
            parsed = None
        if parsed is None:
            handoffs = await asyncio.to_thread(list_handoffs, root, limit=None, include_deleted=include_deleted)
            handoff = next((item for item in handoffs if str(item.get("id", "")) == entry_id), None)
            if handoff is not None:
                parsed = parse_handoff_restore_context(handoff)
        if parsed is None:
            return [TextContent(type="text", text=f"Handoff {entry_id} not found")]
        related = ", ".join(item["raw"] for item in parsed["related_entries"]) or "none"
        restore_context = parsed["restore_context"]
        text = (
            f"Handoff {entry_id}\n"
            f"Goal: {parsed.get('goal', '')}\n"
            f"Section: {restore_context.get('section', '')}\n"
            f"Query: {restore_context.get('query', '')}\n"
            f"Include deleted: {restore_context.get('include_deleted', False)}\n"
            f"Related entries: {related}"
        )
        return [TextContent(type="text", text=text)]

    async def rememb_workstream_state_get():
        workstream_id = arguments.get("workstream_id")
        if workstream_id is None or not str(workstream_id).strip():
            return [TextContent(type="text", text="Provide workstream_id.")]
        session_id = arguments.get("session_id")
        include_deleted = arguments.get("include_deleted", False)
        state = await asyncio.to_thread(
            get_workstream_state,
            root,
            str(workstream_id),
            session_id=session_id,
            include_deleted=include_deleted,
        )
        if state is None:
            return [TextContent(type="text", text=f"Workstream {workstream_id} not found")]
        lines = [
            f"Workstream: {state['workstream_id']}",
            f"Session filter: {state.get('session_id') or '(all)'}",
            f"Entries: {state['entry_count']}",
            f"Sessions: {state['session_count']}",
        ]
        latest_entry = state.get("latest_entry")
        if latest_entry:
            lines.append(
                f"Latest entry: {latest_entry.get('id')} kind={latest_entry.get('entry_kind') or ''} session={latest_entry.get('session_id') or ''}"
            )
        latest_handoff = state.get("latest_handoff")
        if latest_handoff:
            lines.append(f"Latest handoff: {latest_handoff.get('id')} session={latest_handoff.get('session_id') or ''}")
        latest_state = state.get("latest_state")
        if latest_state:
            lines.append(f"Latest state: {latest_state.get('id')} session={latest_state.get('session_id') or ''}")
        if state["sessions"]:
            lines.append("")
            lines.append("Sessions:")
            for session in state["sessions"]:
                lines.append(
                    f"- {session.get('session_id') or '(none)'} entries={session['entry_count']} latest={session.get('latest_entry_id') or ''}"
                )
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_workstream_resume():
        workstream_id = arguments.get("workstream_id")
        if workstream_id is None or not str(workstream_id).strip():
            return [TextContent(type="text", text="Provide workstream_id.")]
        session_id = arguments.get("session_id")
        include_deleted = arguments.get("include_deleted", False)
        resume = await asyncio.to_thread(
            resume_workstream,
            root,
            str(workstream_id),
            session_id=session_id,
            include_deleted=include_deleted,
        )
        if resume is None:
            return [TextContent(type="text", text=f"Workstream {workstream_id} not found")]
        lines = [
            f"Workstream: {resume['workstream_id']}",
            f"Session: {resume.get('session_id') or '(none)'}",
            f"Goal: {resume.get('goal') or ''}",
            f"Summary: {resume.get('summary') or ''}",
            f"Latest entry: {resume.get('latest_entry_id') or ''} kind={resume.get('latest_entry_kind') or ''}",
            f"Focus entries: {', '.join(resume.get('focus_entry_ids', [])) or 'none'}",
        ]
        if resume.get("current_state"):
            lines.append("Current state: " + " | ".join(resume["current_state"]))
        if resume.get("open_loops"):
            lines.append("Open loops: " + " | ".join(resume["open_loops"]))
        if resume.get("next_steps"):
            lines.append("Next steps: " + " | ".join(resume["next_steps"]))
        restore_context = resume.get("restore_context") or {}
        if restore_context:
            lines.append(
                "Restore context: "
                f"section={restore_context.get('section', '')} "
                f"query={restore_context.get('query', '')} "
                f"include_deleted={restore_context.get('include_deleted', False)}"
            )
        if resume.get("related_entry_ids"):
            lines.append("Related entries: " + ", ".join(resume["related_entry_ids"]))
        compressed_context = resume.get("compressed_context") or {}
        if compressed_context:
            lines.append(
                "Compressed context: "
                f"essential={len(compressed_context.get('essential', []))} "
                f"optional={len(compressed_context.get('optional', []))} "
                f"archived={len(compressed_context.get('archived', []))} "
                f"risky={len(compressed_context.get('risky', []))} "
                f"obsolete={len(compressed_context.get('obsolete', []))}"
            )
        if resume.get("what_changed"):
            lines.append("What changed: " + " | ".join(item.get("summary") or "" for item in resume["what_changed"]))
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_handoff_package():
        workstream_id = arguments.get("workstream_id")
        if workstream_id is None or not str(workstream_id).strip():
            return [TextContent(type="text", text="Provide workstream_id.")]
        payload = await asyncio.to_thread(
            build_handoff_package,
            root,
            str(workstream_id),
            session_id=arguments.get("session_id"),
            next_goal=arguments.get("next_goal"),
            include_deleted=arguments.get("include_deleted", False),
        )
        if payload is None:
            return [TextContent(type="text", text=f"Workstream {workstream_id} not found")]
        lines = [
            f"Workstream: {payload['workstream_id']}",
            f"Session: {payload.get('session_id') or '(none)'}",
            f"Current goal: {payload.get('current_goal') or ''}",
            f"Next goal: {payload.get('next_goal') or ''}",
            f"Focus entries: {', '.join(payload.get('focus_entry_ids', [])) or 'none'}",
        ]
        if payload.get("what_changed"):
            lines.append("What changed: " + " | ".join(item.get("summary") or "" for item in payload["what_changed"]))
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_workstream_list():
        limit = arguments.get("limit")
        include_deleted = arguments.get("include_deleted", False)
        items = await asyncio.to_thread(list_workstreams, root, limit=limit, include_deleted=include_deleted)
        if not items:
            return [TextContent(type="text", text="No workstreams found.")]
        lines = ["Recent workstreams:"]
        for item in items:
            lines.append(
                f"- {item['workstream_id']} entries={item['entry_count']} sessions={item['session_count']} goal={item.get('goal', '')}"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_workstream_open():
        goal = arguments.get("goal")
        if goal is None or not str(goal).strip():
            return [TextContent(type="text", text="Provide goal for the workstream.")]
        result = await asyncio.to_thread(
            open_workstream,
            root,
            str(goal),
            workstream_id=arguments.get("workstream_id"),
            summary=arguments.get("summary"),
            tags=arguments.get("tags"),
        )
        created = "created" if result.get("created") else "reused"
        return [TextContent(type="text", text=f"Workstream {result['workstream_id']} {created} (entry={result['entry']['id']})")]

    async def rememb_workstream_state_update():
        workstream_id = arguments.get("workstream_id")
        if workstream_id is None or not str(workstream_id).strip():
            return [TextContent(type="text", text="Provide workstream_id.")]
        updated = await asyncio.to_thread(
            update_workstream_state,
            root,
            str(workstream_id),
            session_id=arguments.get("session_id"),
            goal=arguments.get("goal"),
            summary=arguments.get("summary"),
            current_state=arguments.get("current_state"),
            decisions=arguments.get("decisions"),
            open_loops=arguments.get("open_loops"),
            next_steps=arguments.get("next_steps"),
            essential_context=arguments.get("essential_context"),
            optional_context=arguments.get("optional_context"),
            risk_flags=arguments.get("risk_flags"),
            related_entry_ids=arguments.get("related_entry_ids"),
            merge=arguments.get("merge", True),
        )
        if updated is None:
            return [TextContent(type="text", text=f"Workstream {workstream_id} not found")]
        return [TextContent(type="text", text=f"Updated workstream state {workstream_id} (entry={updated['id']})")]

    async def rememb_session_start():
        workstream_id = arguments.get("workstream_id")
        if workstream_id is None or not str(workstream_id).strip():
            return [TextContent(type="text", text="Provide workstream_id.")]
        entry = await asyncio.to_thread(
            start_session,
            root,
            str(workstream_id),
            goal=arguments.get("goal"),
            summary=arguments.get("summary"),
            session_id=arguments.get("session_id"),
            tags=arguments.get("tags"),
        )
        if entry is None:
            return [TextContent(type="text", text=f"Workstream {workstream_id} not found")]
        return [TextContent(type="text", text=f"Started session {entry.get('session_id')} for {workstream_id} (entry={entry['id']})")]

    async def rememb_session_close():
        workstream_id = arguments.get("workstream_id")
        outcome = arguments.get("outcome")
        if workstream_id is None or not str(workstream_id).strip():
            return [TextContent(type="text", text="Provide workstream_id.")]
        if outcome is None or not str(outcome).strip():
            return [TextContent(type="text", text="Provide outcome for the session close.")]
        entry = await asyncio.to_thread(
            close_session,
            root,
            str(workstream_id),
            session_id=arguments.get("session_id"),
            outcome=str(outcome),
            status=arguments.get("status", "paused"),
            next_steps=arguments.get("next_steps"),
            open_loops=arguments.get("open_loops"),
            related_entry_ids=arguments.get("related_entry_ids"),
        )
        if entry is None:
            return [TextContent(type="text", text=f"Workstream {workstream_id} not found")]
        return [TextContent(type="text", text=f"Closed session {entry.get('session_id')} for {workstream_id} (entry={entry['id']})")]

    async def rememb_session_close_and_handoff():
        workstream_id = arguments.get("workstream_id")
        outcome = arguments.get("outcome")
        next_goal = arguments.get("next_goal")
        if workstream_id is None or not str(workstream_id).strip():
            return [TextContent(type="text", text="Provide workstream_id.")]
        if outcome is None or not str(outcome).strip():
            return [TextContent(type="text", text="Provide outcome for the session close.")]
        if next_goal is None or not str(next_goal).strip():
            return [TextContent(type="text", text="Provide next_goal for the follow-up handoff.")]
        result = await asyncio.to_thread(
            close_session_with_handoff,
            root,
            str(workstream_id),
            session_id=arguments.get("session_id"),
            outcome=str(outcome),
            next_goal=str(next_goal),
            status=arguments.get("status", "paused"),
            summary=arguments.get("summary"),
            open_loops=arguments.get("open_loops"),
            next_steps=arguments.get("next_steps"),
            essential_context=arguments.get("essential_context"),
            optional_context=arguments.get("optional_context"),
            archived_context=arguments.get("archived_context"),
            risk_flags=arguments.get("risk_flags"),
            obsolete_context=arguments.get("obsolete_context"),
            related_entry_ids=arguments.get("related_entry_ids"),
            include_deleted=arguments.get("include_deleted", False),
            audience=arguments.get("audience", "agent"),
        )
        if result is None:
            return [TextContent(type="text", text=f"Workstream {workstream_id} not found")]
        review_entry = result["review_entry"]
        handoff_entry = result["handoff_entry"]
        return [TextContent(type="text", text=(
            f"Closed session {review_entry.get('session_id')} for {workstream_id} "
            f"(review={review_entry['id']} handoff={handoff_entry['id']})"
        ))]

    async def rememb_review_queue():
        items = await asyncio.to_thread(
            list_review_queue,
            root,
            workstream_id=arguments.get("workstream_id"),
            session_id=arguments.get("session_id"),
            actor_type=arguments.get("actor_type"),
            actor_id=arguments.get("actor_id"),
            entry_kind=arguments.get("entry_kind"),
            review_status=arguments.get("review_status"),
            include_deleted=arguments.get("include_deleted", False),
            pending_only=arguments.get("pending_only", True),
            limit=arguments.get("limit"),
        )
        if not items:
            return [TextContent(type="text", text="No review items found.")]
        lines = ["Review queue:"]
        for item in items:
            lines.append(
                f"- {item['entry_id']} status={item['review_status']} kind={item.get('entry_kind') or ''} actor={item.get('actor_type') or ''}:{item.get('actor_id') or ''} reasons={','.join(item.get('review_reasons') or [])}"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_review_session_get():
        workstream_id = arguments.get("workstream_id")
        session_id = arguments.get("session_id")
        if workstream_id is None or not str(workstream_id).strip():
            return [TextContent(type="text", text="Provide workstream_id.")]
        if session_id is None or not str(session_id).strip():
            return [TextContent(type="text", text="Provide session_id.")]
        payload = await asyncio.to_thread(
            get_review_session,
            root,
            str(workstream_id),
            str(session_id),
            include_deleted=arguments.get("include_deleted", False),
        )
        if payload is None:
            return [TextContent(type="text", text=f"Session {session_id} not found")]
        lines = [
            f"Review session: {payload['session_id']}",
            f"Workstream: {payload.get('workstream_id') or '(none)'}",
            f"Status: {payload.get('operational_status') or ''}",
            f"Pending review: {payload.get('pending_review_count') or 0}",
            f"Entries: {payload.get('entry_count') or 0}",
        ]
        if payload.get("active_decision_ids"):
            lines.append("Active decisions: " + ", ".join(payload["active_decision_ids"]))
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_review_workstream_get():
        workstream_id = arguments.get("workstream_id")
        if workstream_id is None or not str(workstream_id).strip():
            return [TextContent(type="text", text="Provide workstream_id.")]
        payload = await asyncio.to_thread(
            get_review_workstream,
            root,
            str(workstream_id),
            include_deleted=arguments.get("include_deleted", False),
        )
        if payload is None:
            return [TextContent(type="text", text=f"Workstream {workstream_id} not found")]
        lines = [
            f"Review workstream: {payload['workstream_id']}",
            f"Status: {payload.get('operational_status') or ''}",
            f"Pending review: {payload.get('pending_review_count') or 0}",
            f"Sessions: {len(payload.get('sessions') or [])}",
        ]
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_workstream_queue():
        items = await asyncio.to_thread(
            list_workstream_queue,
            root,
            status=arguments.get("status"),
            include_deleted=arguments.get("include_deleted", False),
            limit=arguments.get("limit"),
        )
        if not items:
            return [TextContent(type="text", text="No workstreams in queue.")]
        lines = ["Workstream queue:"]
        for item in items:
            lines.append(
                f"- {item['workstream_id']} status={item.get('operational_status') or ''} pending_review={item.get('pending_review_count') or 0} sessions={item.get('session_count') or 0}"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_compare_sessions():
        workstream_id = arguments.get("workstream_id")
        base_session_id = arguments.get("base_session_id")
        target_session_id = arguments.get("target_session_id")
        if workstream_id is None or not str(workstream_id).strip():
            return [TextContent(type="text", text="Provide workstream_id.")]
        if base_session_id is None or not str(base_session_id).strip() or target_session_id is None or not str(target_session_id).strip():
            return [TextContent(type="text", text="Provide base_session_id and target_session_id.")]
        payload = await asyncio.to_thread(
            compare_sessions,
            root,
            str(workstream_id),
            str(base_session_id),
            str(target_session_id),
            include_deleted=arguments.get("include_deleted", False),
        )
        if payload is None:
            return [TextContent(type="text", text="Session comparison not available.")]
        delta = payload.get("delta") or {}
        lines = [
            f"Compare sessions in {payload['workstream_id']}",
            f"Base: {base_session_id}",
            f"Target: {target_session_id}",
            f"New open loops: {', '.join(delta.get('new_open_loops') or []) or 'none'}",
            f"Resolved open loops: {', '.join(delta.get('resolved_open_loops') or []) or 'none'}",
        ]
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_compare_workstreams():
        left_workstream_id = arguments.get("left_workstream_id")
        right_workstream_id = arguments.get("right_workstream_id")
        if left_workstream_id is None or not str(left_workstream_id).strip() or right_workstream_id is None or not str(right_workstream_id).strip():
            return [TextContent(type="text", text="Provide left_workstream_id and right_workstream_id.")]
        payload = await asyncio.to_thread(
            compare_workstreams,
            root,
            str(left_workstream_id),
            str(right_workstream_id),
            include_deleted=arguments.get("include_deleted", False),
        )
        if payload is None:
            return [TextContent(type="text", text="Workstream comparison not available.")]
        delta = payload.get("delta") or {}
        lines = [
            f"Compare workstreams: {left_workstream_id} vs {right_workstream_id}",
            f"Status changed: {str(delta.get('operational_status_changed', False)).lower()}",
            f"Left-only open loops: {', '.join(delta.get('left_only_open_loops') or []) or 'none'}",
            f"Right-only open loops: {', '.join(delta.get('right_only_open_loops') or []) or 'none'}",
        ]
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_review_update():
        entry_id = arguments.get("entry_id")
        if entry_id is None or not _validate_entry_id(entry_id):
            return [TextContent(type="text", text=f"Invalid entry ID format: {entry_id}. Expected 8 hex characters.")]
        review_status = arguments.get("review_status")
        if review_status is None or not str(review_status).strip():
            return [TextContent(type="text", text="Provide review_status.")]
        updated = await asyncio.to_thread(
            update_review_status,
            root,
            str(entry_id),
            str(review_status),
            review_notes=arguments.get("review_notes"),
            review_reason=arguments.get("review_reason"),
            validation_notes=arguments.get("validation_notes"),
            source_context_entry_ids=arguments.get("source_context_entry_ids"),
        )
        if updated is None:
            return [TextContent(type="text", text=f"Entry {entry_id} not found")]
        return [TextContent(type="text", text=f"Updated review status for {entry_id} -> {updated.get('structured', {}).get('review_status', '')}")]

    async def rememb_handoff_write_structured():
        workstream_id = arguments.get("workstream_id")
        goal = arguments.get("goal")
        if workstream_id is None or not str(workstream_id).strip():
            return [TextContent(type="text", text="Provide workstream_id.")]
        if goal is None or not str(goal).strip():
            return [TextContent(type="text", text="Provide goal for the handoff.")]
        entry = await asyncio.to_thread(
            write_structured_handoff,
            root,
            str(workstream_id),
            session_id=arguments.get("session_id"),
            goal=str(goal),
            summary=arguments.get("summary"),
            current_state=arguments.get("current_state"),
            decisions=arguments.get("decisions"),
            open_loops=arguments.get("open_loops"),
            next_steps=arguments.get("next_steps"),
            essential_context=arguments.get("essential_context"),
            optional_context=arguments.get("optional_context"),
            related_entries=arguments.get("related_entries"),
            risk_flags=arguments.get("risk_flags"),
            restore_section=arguments.get("restore_section", "actions"),
            restore_query=arguments.get("restore_query"),
            include_deleted=arguments.get("include_deleted", False),
            tags=arguments.get("tags"),
        )
        return [TextContent(type="text", text=f"Saved structured handoff [{entry['section']}] id={entry['id']}")]

    async def rememb_handoff_read_structured():
        entry_id = arguments.get("entry_id")
        workstream_id = arguments.get("workstream_id")
        if entry_id is None and (workstream_id is None or not str(workstream_id).strip()):
            return [TextContent(type="text", text="Provide entry_id or workstream_id.")]
        payload = await asyncio.to_thread(
            read_structured_handoff,
            root,
            entry_id=entry_id,
            workstream_id=str(workstream_id) if workstream_id is not None else None,
            session_id=arguments.get("session_id"),
            include_deleted=arguments.get("include_deleted", True),
        )
        if payload is None:
            target = entry_id or workstream_id
            return [TextContent(type="text", text=f"Structured handoff {target} not found")]
        lines = [
            f"Handoff entry: {payload['entry_id']}",
            f"Workstream: {payload.get('workstream_id') or ''}",
            f"Session: {payload.get('session_id') or ''}",
            f"Goal: {payload.get('goal') or ''}",
            f"Summary: {payload.get('summary') or ''}",
        ]
        if payload.get("next_steps"):
            lines.append("Next steps: " + " | ".join(payload["next_steps"]))
        if payload.get("related_entries"):
            related = []
            for item in payload["related_entries"]:
                if isinstance(item, dict):
                    related.append(str(item.get("raw") or item.get("entry_id") or ""))
            lines.append("Related entries: " + ", ".join(filter(None, related)))
        return [TextContent(type="text", text="\n".join(lines))]

    async def rememb_write():
        entries = arguments.get("entries")
        semantic_scope = arguments.get("semantic_scope", "global")
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
                        "meta_schema_version": item.get("meta_schema_version"),
                        "workstream_id": item.get("workstream_id"),
                        "session_id": item.get("session_id"),
                        "entry_kind": item.get("entry_kind"),
                        "entry_role": item.get("entry_role"),
                        "actor_type": item.get("actor_type"),
                        "actor_id": item.get("actor_id"),
                        "parent_entry_id": item.get("parent_entry_id"),
                        "supersedes_entry_id": item.get("supersedes_entry_id"),
                        "related_entry_ids": item.get("related_entry_ids"),
                        "structured": item.get("structured"),
                    }
                )
            created = await asyncio.to_thread(write_entries, root, prepared_entries, True, semantic_scope)
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
            semantic_scope,
            meta_schema_version=arguments.get("meta_schema_version"),
            workstream_id=arguments.get("workstream_id"),
            session_id=arguments.get("session_id"),
            entry_kind=arguments.get("entry_kind"),
            entry_role=arguments.get("entry_role"),
            actor_type=arguments.get("actor_type"),
            actor_id=arguments.get("actor_id"),
            parent_entry_id=arguments.get("parent_entry_id"),
            supersedes_entry_id=arguments.get("supersedes_entry_id"),
            related_entry_ids=arguments.get("related_entry_ids"),
            structured=arguments.get("structured"),
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
                metadata_present = any(field in update for field in _ENTRY_METADATA_PROPERTY_SCHEMAS)
                if update.get("content") is None and update.get("section") is None and update.get("tags") is None and not metadata_present:
                    return [TextContent(type="text", text=f"Provide at least one field to update for {entry_id}: content, section, tags, or metadata.")]
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
        metadata_present = any(field in arguments for field in _ENTRY_METADATA_PROPERTY_SCHEMAS)
        if content is None and section is None and tags is None and not metadata_present:
            return [TextContent(type="text", text="Provide at least one field to update: content, section, tags, or metadata.")]
        result = await asyncio.to_thread(
            edit_entry,
            root,
            entry_id,
            content,
            section,
            tags,
            meta_schema_version=arguments.get("meta_schema_version"),
            workstream_id=arguments.get("workstream_id"),
            session_id=arguments.get("session_id"),
            entry_kind=arguments.get("entry_kind"),
            entry_role=arguments.get("entry_role"),
            actor_type=arguments.get("actor_type"),
            actor_id=arguments.get("actor_id"),
            parent_entry_id=arguments.get("parent_entry_id"),
            supersedes_entry_id=arguments.get("supersedes_entry_id"),
            related_entry_ids=arguments.get("related_entry_ids"),
            structured=arguments.get("structured"),
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
        mode = arguments.get("mode", "exact")
        _cfg = get_config(root)
        similarity_threshold = arguments.get(
            "similarity_threshold",
            _cfg["semantic_conflict_threshold"],
        )
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
        init_root = global_root()
        if await asyncio.to_thread(is_initialized, init_root):
            return [TextContent(type="text", text=f"Already initialized at {init_root / '.rememb'}")]
        _mcp_context.clear_root_cache()
        effective_project_name = project_name or "global"
        rememb_path = await asyncio.to_thread(init, init_root, effective_project_name, True)
        return [TextContent(type="text", text=f"Initialized at {rememb_path}")]

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
        "rememb_read": rememb_read,
        "rememb_read_page": rememb_read_page,
        "rememb_search": rememb_search,
        "rememb_versions": rememb_versions,
        "rememb_restore": rememb_restore,
        "rememb_diff": rememb_diff,
        "rememb_handoff_generate": rememb_handoff_generate,
        "rememb_handoff_list": rememb_handoff_list,
        "rememb_handoff_restore_context": rememb_handoff_restore_context,
        "rememb_handoff_write_structured": rememb_handoff_write_structured,
        "rememb_handoff_read_structured": rememb_handoff_read_structured,
        "rememb_workstream_list": rememb_workstream_list,
        "rememb_workstream_open": rememb_workstream_open,
        "rememb_workstream_state_get": rememb_workstream_state_get,
        "rememb_workstream_state_update": rememb_workstream_state_update,
        "rememb_workstream_resume": rememb_workstream_resume,
        "rememb_handoff_package": rememb_handoff_package,
        "rememb_session_start": rememb_session_start,
        "rememb_session_close": rememb_session_close,
        "rememb_session_close_and_handoff": rememb_session_close_and_handoff,
        "rememb_review_queue": rememb_review_queue,
        "rememb_review_session_get": rememb_review_session_get,
        "rememb_review_workstream_get": rememb_review_workstream_get,
        "rememb_workstream_queue": rememb_workstream_queue,
        "rememb_compare_sessions": rememb_compare_sessions,
        "rememb_compare_workstreams": rememb_compare_workstreams,
        "rememb_review_update": rememb_review_update,
        "rememb_write": rememb_write,
        "rememb_edit": rememb_edit,
        "rememb_delete": rememb_delete,
        "rememb_clear": rememb_clear,
        "rememb_stats": rememb_stats,
        "rememb_consolidate": rememb_consolidate,
        "rememb_init": rememb_init,
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
            name="rememb_read",
            description="Read all memory entries or filter by section. Safe, read-only operation with no side effects. Use this at the start of every session to load context. Prefer rememb_search when looking for specific information by keyword or topic.",
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
                "summary_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "Render a compact one-line summary per entry",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters of content to include per entry",
                },
            },
        ),
        _tool(
            name="rememb_read_page",
            description="Read a paginated slice of entries with server-side truncation. Best for browsing large stores without flooding the context window.",
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
                "summary_only": {
                    "type": "boolean",
                    "default": True,
                    "description": "Render a compact one-line summary per entry",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters of content to include per entry",
                },
            },
        ),
        _tool(
            name="rememb_search",
            description="Search memory entries by content or tags using semantic similarity. Safe, read-only operation with no side effects. Use instead of rememb_read when you need to find specific entries by topic rather than loading all entries. Returns the top_k most relevant results ranked by similarity.",
            properties={
                "query": {
                    "type": "string",
                    "description": "Search query - natural language or keywords",
                },
                "section": {
                    "type": "string",
                    "enum": sections,
                    "description": f"Optional section filter: {', '.join(sections)}",
                },
                "tag": {
                    "type": "string",
                    "description": "Optional exact tag filter applied before semantic search",
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
                "summary_only": {
                    "type": "boolean",
                    "default": True,
                    "description": "Render a compact one-line summary per entry",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters of content to include per entry",
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
            name="rememb_handoff_generate",
            description="Generate and save a goal-oriented handoff as a normal memory entry in the actions section.",
            properties={
                "goal": {
                    "type": "string",
                    "description": "Goal for the next session",
                },
                "summary": {
                    "type": "string",
                    "description": "Compact summary of the current session state",
                },
                "current_state": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Current state bullets",
                },
                "open_loops": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Open loops that still need work",
                },
                "next_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered next-step list",
                },
                "related_entries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Related entry references such as abcd1234 or deadbeef@v2",
                },
                "restore_section": {
                    "type": "string",
                    "enum": sections,
                    "default": "actions",
                    "description": "Preferred section to restore into context",
                },
                "restore_query": {
                    "type": "string",
                    "description": "Optional restore query hint",
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether restore hints should include deleted entries",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional tags to store alongside the handoff",
                },
                "workstream_id": {
                    "type": "string",
                    "description": "Optional logical workstream identifier for the handoff",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional logical session identifier for the handoff",
                },
            },
            required=["goal"],
        ),
        _tool(
            name="rememb_handoff_list",
            description="List recent stored handoffs. Safe, read-only operation.",
            properties={
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of handoffs to return",
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include soft-deleted handoffs",
                },
            },
        ),
        _tool(
            name="rememb_handoff_restore_context",
            description="Read a stored handoff and return its restore hints and related entry references.",
            properties={
                "entry_id": {
                    "type": "string",
                    "description": "Handoff entry ID (8 hex characters)",
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": True,
                    "description": "Allow reading soft-deleted handoffs",
                },
            },
            required=["entry_id"],
        ),
        _tool(
            name="rememb_handoff_write_structured",
            description="Write a structured, agent-first handoff for a workstream/session while preserving the normal handoff entry format.",
            properties={
                "workstream_id": {"type": "string", "description": "Logical workstream identifier"},
                "session_id": {"type": "string", "description": "Optional logical session identifier"},
                "goal": {"type": "string", "description": "Goal for the next session"},
                "summary": {"type": "string", "description": "Compact summary of the current session state"},
                "current_state": {"type": "array", "items": {"type": "string"}, "description": "Current state bullets"},
                "decisions": {"type": "array", "items": {"type": "string"}, "description": "Recent decisions to preserve"},
                "open_loops": {"type": "array", "items": {"type": "string"}, "description": "Open loops that still need work"},
                "next_steps": {"type": "array", "items": {"type": "string"}, "description": "Ordered next-step list"},
                "essential_context": {"type": "array", "items": {"type": "string"}, "description": "Context that must be restored"},
                "optional_context": {"type": "array", "items": {"type": "string"}, "description": "Context that is useful but not mandatory"},
                "related_entries": {"type": "array", "items": {"type": "string"}, "description": "Related entry references such as abcd1234 or deadbeef@v2"},
                "risk_flags": {"type": "array", "items": {"type": "string"}, "description": "Known risks or caveats"},
                "restore_section": {"type": "string", "enum": sections, "default": "actions", "description": "Preferred section to restore into context"},
                "restore_query": {"type": "string", "description": "Optional restore query hint"},
                "include_deleted": {"type": "boolean", "default": False, "description": "Whether restore hints should include deleted entries"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Additional tags to store alongside the handoff"},
            },
            required=["workstream_id", "goal"],
        ),
        _tool(
            name="rememb_handoff_read_structured",
            description="Read a structured handoff payload by entry id or latest handoff in a workstream. Safe, read-only operation.",
            properties={
                "entry_id": {"type": "string", "description": "Handoff entry ID (8 hex characters)"},
                "workstream_id": {"type": "string", "description": "Logical workstream identifier"},
                "session_id": {"type": "string", "description": "Optional logical session identifier to scope the handoff"},
                "include_deleted": {"type": "boolean", "default": True, "description": "Allow reading soft-deleted handoffs"},
            },
        ),
        _tool(
            name="rememb_handoff_package",
            description="Build a minimal anti-context-switch handoff package for the next session without writing a new entry.",
            properties={
                "workstream_id": {"type": "string", "description": "Logical workstream identifier"},
                "session_id": {"type": "string", "description": "Optional logical session identifier to scope the package"},
                "next_goal": {"type": "string", "description": "Optional next goal override"},
                "include_deleted": {"type": "boolean", "default": False, "description": "Include soft-deleted entries when building the package"},
            },
            required=["workstream_id"],
        ),
        _tool(
            name="rememb_workstream_list",
            description="List aggregated workstreams derived from existing entries. Safe, read-only operation.",
            properties={
                "limit": {"type": "integer", "description": "Maximum number of workstreams to return"},
                "include_deleted": {"type": "boolean", "default": False, "description": "Include soft-deleted entries when listing workstreams"},
            },
        ),
        _tool(
            name="rememb_workstream_open",
            description="Create or reopen a logical workstream using a checkpoint entry in the current local store.",
            properties={
                "workstream_id": {"type": "string", "description": "Optional logical workstream identifier"},
                "goal": {"type": "string", "description": "Goal for the workstream"},
                "summary": {"type": "string", "description": "Optional short summary"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags to store alongside the opening checkpoint"},
            },
            required=["goal"],
        ),
        _tool(
            name="rememb_workstream_state_get",
            description="Aggregate the current state of a workstream and its sessions from existing entries. Safe, read-only operation.",
            properties={
                "workstream_id": {
                    "type": "string",
                    "description": "Logical workstream identifier",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional logical session identifier to scope the aggregation",
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include soft-deleted entries when aggregating workstream state",
                },
            },
            required=["workstream_id"],
        ),
        _tool(
            name="rememb_workstream_state_update",
            description="Write a structured state checkpoint for a workstream. This persists a new entry rather than mutating prior state.",
            properties={
                "workstream_id": {"type": "string", "description": "Logical workstream identifier"},
                "session_id": {"type": "string", "description": "Optional logical session identifier to scope the checkpoint"},
                "goal": {"type": "string", "description": "Optional goal override"},
                "summary": {"type": "string", "description": "Optional compact summary"},
                "current_state": {"type": "array", "items": {"type": "string"}, "description": "Current factual state bullets"},
                "decisions": {"type": "array", "items": {"type": "string"}, "description": "Recent decisions to preserve"},
                "open_loops": {"type": "array", "items": {"type": "string"}, "description": "Outstanding work items"},
                "next_steps": {"type": "array", "items": {"type": "string"}, "description": "Ordered next-step list"},
                "essential_context": {"type": "array", "items": {"type": "string"}, "description": "Context that must be restored"},
                "optional_context": {"type": "array", "items": {"type": "string"}, "description": "Optional context"},
                "risk_flags": {"type": "array", "items": {"type": "string"}, "description": "Known risks or caveats"},
                "related_entry_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional related entry ids"},
                "merge": {"type": "boolean", "default": True, "description": "When true, omitted structured fields inherit from the latest state"},
            },
            required=["workstream_id"],
        ),
        _tool(
            name="rememb_workstream_resume",
            description="Return a compact operational resume for a workstream, combining the latest handoff/state entries when available. Safe, read-only operation.",
            properties={
                "workstream_id": {
                    "type": "string",
                    "description": "Logical workstream identifier",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional logical session identifier to scope the resume",
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include soft-deleted entries when building the workstream resume",
                },
            },
            required=["workstream_id"],
        ),
        _tool(
            name="rememb_session_start",
            description="Start a new logical session inside a workstream by persisting a checkpoint entry.",
            properties={
                "workstream_id": {"type": "string", "description": "Logical workstream identifier"},
                "goal": {"type": "string", "description": "Optional goal override for the new session"},
                "summary": {"type": "string", "description": "Optional compact summary"},
                "session_id": {"type": "string", "description": "Optional explicit session id"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags to store alongside the session start"},
            },
            required=["workstream_id"],
        ),
        _tool(
            name="rememb_session_close",
            description="Close the active or selected session by recording a structured review entry.",
            properties={
                "workstream_id": {"type": "string", "description": "Logical workstream identifier"},
                "session_id": {"type": "string", "description": "Optional logical session identifier"},
                "outcome": {"type": "string", "description": "Outcome summary for the session"},
                "status": {"type": "string", "description": "Session close status such as paused or completed"},
                "next_steps": {"type": "array", "items": {"type": "string"}, "description": "Optional next-step list"},
                "open_loops": {"type": "array", "items": {"type": "string"}, "description": "Optional open loops that remain"},
                "related_entry_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional related entry ids"},
                "next_goal": {"type": "string", "description": "Optional declared next goal for the review record"},
            },
            required=["workstream_id", "outcome"],
        ),
        _tool(
            name="rememb_session_close_and_handoff",
            description="Close a session and persist the next-goal handoff in one operation.",
            properties={
                "workstream_id": {"type": "string", "description": "Logical workstream identifier"},
                "session_id": {"type": "string", "description": "Optional logical session identifier"},
                "outcome": {"type": "string", "description": "Outcome summary for the session"},
                "next_goal": {"type": "string", "description": "Goal for the next session"},
                "status": {"type": "string", "description": "Session close status such as paused or completed"},
                "summary": {"type": "string", "description": "Optional handoff summary override"},
                "open_loops": {"type": "array", "items": {"type": "string"}, "description": "Open loops that remain"},
                "next_steps": {"type": "array", "items": {"type": "string"}, "description": "Ordered next-step list"},
                "essential_context": {"type": "array", "items": {"type": "string"}, "description": "Context that must be restored"},
                "optional_context": {"type": "array", "items": {"type": "string"}, "description": "Optional context"},
                "archived_context": {"type": "array", "items": {"type": "string"}, "description": "Context that can stay archived"},
                "risk_flags": {"type": "array", "items": {"type": "string"}, "description": "Known risks or caveats"},
                "obsolete_context": {"type": "array", "items": {"type": "string"}, "description": "Context that is no longer relevant"},
                "related_entry_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional related entry ids"},
                "include_deleted": {"type": "boolean", "default": False, "description": "Include soft-deleted entries when deriving the handoff package"},
                "audience": {"type": "string", "enum": ["agent", "human"], "default": "agent", "description": "Preferred handoff audience"},
            },
            required=["workstream_id", "outcome", "next_goal"],
        ),
        _tool(
            name="rememb_review_queue",
            description="List entries that require review with diff context when available.",
            properties={
                "workstream_id": {"type": "string", "description": "Optional workstream scope"},
                "session_id": {"type": "string", "description": "Optional session scope"},
                "actor_type": {"type": "string", "enum": _ACTOR_TYPE_VALUES, "description": "Optional actor type filter"},
                "actor_id": {"type": "string", "description": "Optional actor identifier filter"},
                "entry_kind": {"type": "string", "enum": _ENTRY_KIND_VALUES, "description": "Optional entry kind filter"},
                "review_status": {"type": "string", "enum": ["pending", "approved", "needs_revision", "dismissed"], "description": "Optional review status filter"},
                "include_deleted": {"type": "boolean", "default": False, "description": "Include soft-deleted entries"},
                "pending_only": {"type": "boolean", "default": True, "description": "Hide approved or dismissed items by default"},
                "limit": {"type": "integer", "description": "Maximum number of review items"},
            },
        ),
        _tool(
            name="rememb_review_session_get",
            description="Aggregate review context for one session inside a workstream.",
            properties={
                "workstream_id": {"type": "string", "description": "Logical workstream identifier"},
                "session_id": {"type": "string", "description": "Logical session identifier"},
                "include_deleted": {"type": "boolean", "default": False, "description": "Include soft-deleted entries"},
            },
            required=["workstream_id", "session_id"],
        ),
        _tool(
            name="rememb_review_workstream_get",
            description="Aggregate review context for a workstream across its sessions.",
            properties={
                "workstream_id": {"type": "string", "description": "Logical workstream identifier"},
                "include_deleted": {"type": "boolean", "default": False, "description": "Include soft-deleted entries"},
            },
            required=["workstream_id"],
        ),
        _tool(
            name="rememb_workstream_queue",
            description="List workstreams as an operational queue with explicit statuses.",
            properties={
                "status": {"type": "string", "enum": ["active", "frozen", "awaiting_review"], "description": "Optional operational status filter"},
                "include_deleted": {"type": "boolean", "default": False, "description": "Include soft-deleted entries"},
                "limit": {"type": "integer", "description": "Maximum number of workstreams"},
            },
        ),
        _tool(
            name="rememb_compare_sessions",
            description="Compare two sessions inside the same workstream.",
            properties={
                "workstream_id": {"type": "string", "description": "Logical workstream identifier"},
                "base_session_id": {"type": "string", "description": "Base session identifier"},
                "target_session_id": {"type": "string", "description": "Target session identifier"},
                "include_deleted": {"type": "boolean", "default": False, "description": "Include soft-deleted entries"},
            },
            required=["workstream_id", "base_session_id", "target_session_id"],
        ),
        _tool(
            name="rememb_compare_workstreams",
            description="Compare the operational state of two workstreams.",
            properties={
                "left_workstream_id": {"type": "string", "description": "Left workstream identifier"},
                "right_workstream_id": {"type": "string", "description": "Right workstream identifier"},
                "include_deleted": {"type": "boolean", "default": False, "description": "Include soft-deleted entries"},
            },
            required=["left_workstream_id", "right_workstream_id"],
        ),
        _tool(
            name="rememb_review_update",
            description="Update the review status for a single entry.",
            properties={
                "entry_id": {"type": "string", "description": "Entry ID (8 hex characters)"},
                "review_status": {"type": "string", "enum": ["pending", "approved", "needs_revision", "dismissed"], "description": "Review decision"},
                "review_notes": {"type": "string", "description": "Optional review notes"},
                "review_reason": {"type": "string", "description": "Optional review reason summary"},
                "validation_notes": {"type": "string", "description": "Optional validation notes"},
                "source_context_entry_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional source context entry ids"},
            },
            required=["entry_id", "review_status"],
        ),
        _tool(
            name="rememb_write",
            description="Save a new memory entry or multiple entries in one call. Single-entry mode creates one new entry and returns its ID. Batch mode accepts entries[]. Existing entries are never overwritten. Use rememb_edit to update an existing entry by ID. semantic_scope controls whether semantic duplicate blocking checks globally or only inside the target section.",
            properties=_with_entry_metadata_fields({
                "content": {
                    "type": "string",
                    "description": "Content to remember (1-3 sentences)",
                },
                "entries": {
                    "type": "array",
                    "description": "Batch write payloads. Each item accepts content and optional section/tags.",
                    "items": {
                        "type": "object",
                        "properties": _with_entry_metadata_fields({
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
                        }),
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
                "semantic_scope": {
                    "type": "string",
                    "enum": ["global", "section"],
                    "default": "global",
                    "description": "Semantic duplicate guard scope: global (all sections) or section (target section only)",
                },
            }),
        ),
        _tool(
            name="rememb_edit",
            description="Update one existing memory entry by ID or multiple entries in one call via updates[]. Modifies only the fields provided (content, section, or tags) — omitted fields are unchanged. Non-destructive: entries are updated, not deleted and recreated. Use rememb_write to create new entries, rememb_delete to permanently remove them.",
            properties=_with_entry_metadata_fields({
                "entry_id": {
                    "type": "string",
                    "description": "Entry ID (8 hex characters)",
                },
                "updates": {
                    "type": "array",
                    "description": "Batch update payloads. Each item requires entry_id and at least one of content, section, or tags.",
                    "items": {
                        "type": "object",
                        "properties": _with_entry_metadata_fields({
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
                        }),
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
            }),
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
                    "default": DEFAULT_SEMANTIC_CONFLICT_THRESHOLD,
                    "description": "Cosine similarity threshold used when mode is semantic (>0 and <=1)",
                },
            },
        ),
        _tool(
            name="rememb_init",
            description="Initialize rememb memory storage. Useful for explicit setup and recovery flows. Home-first root resolution also auto-initializes ~/.rememb when needed, and this tool remains idempotent and safe to call repeatedly.",
            properties={
                "project_name": {
                    "type": "string",
                    "description": "Optional project name",
                }
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
