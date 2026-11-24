"""Host hooks: write on tool/stop, inject on session start / pre-compact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rememb.config import (
    CANONICAL_TAG,
    DEFAULT_RECENT_LIMIT,
    DEFAULT_TAG_LIMIT,
    HANDOFF_TAG,
    HOOK_AUTO_TAG,
    HOOK_FAILED_TAG,
    HOOK_FIELD_CHARS,
    HOOK_KEEP_AUTO,
    HOOK_OUTPUT_MAX_BYTES,
    HOOK_RECORD_TOOLS,
    HOOK_SECTION,
    HOOK_SKIP_TOOLS,
    HOOK_TAG,
    PROHIBITION_TAG,
    SEARCH_EXCERPT_CHARS,
    SESSION_PRIORITY_SECTIONS,
    SESSION_START_CANONICAL_LIMIT,
    SESSION_START_MAX_BYTES,
)
from rememb.exceptions import RemembValidationError
from rememb.store import (
    format_entries,
    get_stats,
    init,
    list_entry_tags,
    prune_entries,
    read_entries,
    read_recent_entries,
    write_entry,
)
from rememb.store.crud import _entry_stamp
from rememb.utils import clip_text, ensure_global_root, global_root, is_initialized

HOOK_EVENTS = ("post-tool", "stop", "session-start", "pre-compact", "session-end")
_INJECT_EVENTS = frozenset({"session-start", "pre-compact"})
_STOP_EVENTS = frozenset({"stop", "session-end"})
_TOOL_NAME_KEYS = ("tool_name", "toolName", "tool")
_CWD_KEYS = ("cwd", "working_directory")
_INPUT_KEYS = ("tool_input", "input", "arguments")
_OUTPUT_KEYS = ("tool_output", "tool_response", "output", "result")
_ERROR_KEYS = ("is_error", "isError", "error")
_FAIL_STATUS = frozenset({"error", "failed", "failure"})
_PRIORITY_TAGS = frozenset({CANONICAL_TAG, PROHIBITION_TAG})


def resolve_hook_root(cwd: Path | None = None) -> Path:
    start = Path(cwd or Path.cwd()).expanduser().resolve()
    home = global_root().resolve()
    current = start
    while True:
        if current != home and is_initialized(current):
            return current
        if current.parent == current:
            break
        current = current.parent
    return ensure_global_root(init)


def parse_hook_payload(raw: str | bytes | None) -> dict[str, Any]:
    if raw is None:
        return {}
    text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    text = text.strip()
    if not text:
        return {}
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _first(payload: dict[str, Any], keys: tuple[str, ...], default: object = "") -> object:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return default


def _field_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def _clip_field(value: object) -> str:
    text = _field_text(value)
    encoded = text.encode("utf-8")
    if len(encoded) > HOOK_OUTPUT_MAX_BYTES:
        text = encoded[:HOOK_OUTPUT_MAX_BYTES].decode("utf-8", errors="ignore")
    return clip_text(text, HOOK_FIELD_CHARS)


def _tool_name(payload: dict[str, Any]) -> str:
    return str(_first(payload, _TOOL_NAME_KEYS)).strip()


def _tool_bare_name(payload: dict[str, Any]) -> str:
    name = _tool_name(payload)
    if not name:
        return ""
    return name.lower().split(":")[-1]


def _cwd_from_payload(payload: dict[str, Any], fallback: Path | None = None) -> Path:
    raw = _first(payload, _CWD_KEYS)
    if raw:
        return Path(str(raw)).expanduser().resolve()
    return Path(fallback or Path.cwd()).expanduser().resolve()


def _tool_failed(payload: dict[str, Any]) -> bool:
    if any(payload.get(key) for key in _ERROR_KEYS):
        return True
    if str(payload.get("status") or "").strip().lower() in _FAIL_STATUS:
        return True
    for key in _OUTPUT_KEYS:
        value = payload.get(key)
        if isinstance(value, dict) and any(value.get(item) for item in _ERROR_KEYS):
            return True
    return False


def should_skip_tool(payload: dict[str, Any]) -> bool:
    name = _tool_name(payload)
    if not name:
        return True
    bare = _tool_bare_name(payload)
    if bare.startswith("rememb_") or name.lower().startswith("rememb_"):
        return True
    if _tool_failed(payload):
        return False
    if bare in HOOK_SKIP_TOOLS:
        return True
    if HOOK_RECORD_TOOLS and bare not in HOOK_RECORD_TOOLS:
        return True
    return False


def format_post_tool_entry(payload: dict[str, Any], *, cwd: Path | None = None) -> str:
    workdir = _cwd_from_payload(payload, cwd)
    failed = _tool_failed(payload)
    status = "failed" if failed else "ok"
    return (
        f"tool: {_tool_name(payload) or 'unknown'}\n"
        f"status: {status}\n"
        f"cwd: {workdir}\n"
        f"in: {_clip_field(_first(payload, _INPUT_KEYS))}\n"
        f"out: {_clip_field(_first(payload, _OUTPUT_KEYS))}"
    )


def format_stop_entry(payload: dict[str, Any], *, cwd: Path | None = None) -> str:
    workdir = _cwd_from_payload(payload, cwd)
    stopped = _first(payload, ("reason", "status", "stopped"), f"session stopped in {workdir}")
    opened = _first(payload, ("open", "pending"), "none")
    return (
        f"stopped: {_clip_field(stopped)}\n"
        f"failed: {_clip_field(_first(payload, ('failed', 'error'), 'none'))}\n"
        f"open: {_clip_field(opened)}\n"
        f"cwd: {workdir}"
    )


def _post_tool_tags(payload: dict[str, Any]) -> list[str]:
    tags = [HOOK_TAG, HOOK_AUTO_TAG]
    if _tool_failed(payload):
        tags.append(HOOK_FAILED_TAG)
    return tags


def _write_hook_entry(root: Path, content: str, tags: list[str]) -> dict[str, Any] | None:
    try:
        return write_entry(root, HOOK_SECTION, content, tags, skip_duplicates=True)
    except RemembValidationError as exc:
        if str(exc).startswith("Duplicate entry"):
            return None
        raise


def _prune_auto_hooks(root: Path) -> None:
    try:
        prune_entries(
            root,
            tags=[HOOK_TAG, HOOK_AUTO_TAG],
            section=HOOK_SECTION,
            keep=HOOK_KEEP_AUTO,
            require_all_tags=True,
        )
    except RemembValidationError:
        return


def _priority_entries(root: Path) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for section in SESSION_PRIORITY_SECTIONS:
        try:
            section_entries = read_entries(root, section)
        except RemembValidationError:
            continue
        ranked = [
            entry
            for entry in section_entries
            if _PRIORITY_TAGS.intersection(entry.get("tags", []))
        ]
        ranked.sort(key=_entry_stamp, reverse=True)
        for entry in ranked:
            entry_id = str(entry.get("id", ""))
            if not entry_id or entry_id in seen:
                continue
            seen.add(entry_id)
            selected.append(entry)
            if len(selected) >= SESSION_START_CANONICAL_LIMIT:
                return selected
    return selected


def _session_entries(root: Path) -> list[dict[str, Any]]:
    handoffs = [entry for entry in read_entries(root) if HANDOFF_TAG in entry.get("tags", [])]
    handoffs.sort(key=_entry_stamp, reverse=True)
    priority = _priority_entries(root)
    recent = read_recent_entries(root, limit=DEFAULT_RECENT_LIMIT)
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for group in (handoffs, priority, recent):
        for entry in group:
            entry_id = str(entry.get("id", ""))
            if not entry_id or entry_id in seen:
                continue
            seen.add(entry_id)
            ordered.append(entry)
    return ordered


def _store_lines(root: Path) -> list[str]:
    home = global_root().resolve()
    current = root.resolve()
    lines = [
        "stores:",
        f"- global path={home} initialized={is_initialized(home)}",
    ]
    if current != home:
        lines.append(f"- project path={current} initialized={is_initialized(current)}")
    return lines


def build_session_start_block(root: Path) -> str:
    stats = get_stats(root)
    tags = list_entry_tags(root, limit=DEFAULT_TAG_LIMIT)
    sections = ", ".join(
        f"{name}={count}" for name, count in sorted(stats.get("by_section", {}).items()) if count
    )
    tag_line = (
        "tags: (none)"
        if not tags
        else "tags: " + ", ".join(f"{item['tag']} ({item['count']})" for item in tags)
    )
    header = "\n".join(
        [
            *_store_lines(root),
            f"stats: total={stats.get('total', 0)} backend={stats.get('storage_backend', '')}"
            + (f" sections={sections}" if sections else ""),
            tag_line,
        ]
    )
    entries = _session_entries(root)
    while True:
        block = f"{header}\n\n{format_entries(entries, include_id=True, max_chars=SEARCH_EXCERPT_CHARS)}"
        if len(block.encode("utf-8")) <= SESSION_START_MAX_BYTES or not entries:
            return block if entries else header
        drop_at = next(
            (
                index
                for index in range(len(entries) - 1, -1, -1)
                if HANDOFF_TAG not in entries[index].get("tags", [])
                and not _PRIORITY_TAGS.intersection(entries[index].get("tags", []))
            ),
            -1,
        )
        entries.pop(drop_at)


def format_session_start_output(block: str, payload: dict[str, Any] | None = None) -> str:
    data = payload or {}
    event = str(_first(data, ("hook_event_name", "hookEventName"))).strip().lower()
    if event in {"sessionstart", "precompact"}:
        hook_name = "PreCompact" if event == "precompact" else "SessionStart"
        return json.dumps(
            {"hookSpecificOutput": {"hookEventName": hook_name, "additionalContext": block}},
            ensure_ascii=False,
        )
    if any(key in data for key in ("composer_mode", "is_background_agent", "cursor_version")):
        return json.dumps({"additional_context": block}, ensure_ascii=False)
    return block


def run_hook(event: str, raw: str | bytes | None = None, *, cwd: Path | None = None) -> tuple[int, str, str]:
    name = event.strip().lower().replace("_", "-")
    if name not in HOOK_EVENTS:
        return 1, "", f"Unknown hook event: {event}. Use {', '.join(HOOK_EVENTS)}.\n"
    payload = parse_hook_payload(raw)
    workdir = _cwd_from_payload(payload, cwd)
    try:
        root = resolve_hook_root(workdir)
        if name == "post-tool":
            if not should_skip_tool(payload):
                _write_hook_entry(
                    root,
                    format_post_tool_entry(payload, cwd=workdir),
                    _post_tool_tags(payload),
                )
            return 0, "", ""
        if name in _STOP_EVENTS:
            _write_hook_entry(root, format_stop_entry(payload, cwd=workdir), [HANDOFF_TAG, HOOK_TAG])
            _prune_auto_hooks(root)
            return 0, "", ""
        if name in _INJECT_EVENTS:
            return 0, format_session_start_output(build_session_start_block(root), payload), ""
        return 1, "", f"Unhandled hook event: {event}\n"
    except Exception as exc:
        return 1, "", f"{exc}\n"
