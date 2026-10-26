"""Host hooks: write on tool/stop, inject on session start."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from rememb.config import (
    HANDOFF_TAG,
    HOOK_AUTO_TAG,
    HOOK_FIELD_CHARS,
    HOOK_OUTPUT_MAX_BYTES,
    HOOK_SECTION,
    HOOK_SKIP_TOOLS,
    HOOK_TAG,
    SEARCH_EXCERPT_CHARS,
    SESSION_START_MAX_BYTES,
    SESSION_START_RECENT_LIMIT,
    SESSION_START_TAG_LIMIT,
)
from rememb.exceptions import RemembError, RemembValidationError
from rememb.store import (
    format_entries,
    get_stats,
    init,
    list_entry_tags,
    read_entries,
    read_recent_entries,
    write_entry,
)
from rememb.utils import ensure_global_root, global_root, is_initialized


HOOK_EVENTS = ("post-tool", "stop", "session-start")


def resolve_hook_root(cwd: Path | None = None) -> Path:
    """Use a project store when cwd (or a parent) has one; otherwise global."""
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


def _clip_chars(value: str, limit: int) -> str:
    text = " ".join(value.split()).strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def _clip_output(value: str) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) > HOOK_OUTPUT_MAX_BYTES:
        value = encoded[:HOOK_OUTPUT_MAX_BYTES].decode("utf-8", errors="ignore")
    return _clip_chars(value, HOOK_FIELD_CHARS)


def _json_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def _tool_name(payload: dict[str, Any]) -> str:
    raw = payload.get("tool_name") or payload.get("toolName") or payload.get("tool") or ""
    return str(raw).strip()


def _cwd_from_payload(payload: dict[str, Any], fallback: Path | None = None) -> Path:
    raw = payload.get("cwd") or payload.get("working_directory")
    if raw:
        return Path(str(raw)).expanduser().resolve()
    return Path(fallback or Path.cwd()).expanduser().resolve()


def _tool_failed(payload: dict[str, Any]) -> bool:
    if payload.get("is_error") or payload.get("isError"):
        return True
    status = str(payload.get("status") or "").strip().lower()
    if status in {"error", "failed", "failure"}:
        return True
    for key in ("tool_response", "tool_output", "output"):
        value = payload.get(key)
        if isinstance(value, dict) and (value.get("is_error") or value.get("isError") or value.get("error")):
            return True
    return False


def _is_rememb_tool(name: str) -> bool:
    lowered = name.lower()
    bare = lowered.split(":")[-1]
    return bare.startswith("rememb_") or lowered.startswith("rememb_")


def should_skip_tool(payload: dict[str, Any]) -> bool:
    name = _tool_name(payload)
    if not name:
        return True
    if _is_rememb_tool(name):
        return True
    bare = name.lower().split(":")[-1]
    if bare in HOOK_SKIP_TOOLS and not _tool_failed(payload):
        return True
    return False


def format_post_tool_entry(payload: dict[str, Any], *, cwd: Path | None = None) -> str:
    name = _tool_name(payload) or "unknown"
    workdir = _cwd_from_payload(payload, cwd)
    incoming = _clip_chars(
        _json_text(payload.get("tool_input") or payload.get("input") or payload.get("arguments") or ""),
        HOOK_FIELD_CHARS,
    )
    outgoing = _clip_output(
        _json_text(
            payload.get("tool_output")
            or payload.get("tool_response")
            or payload.get("output")
            or payload.get("result")
            or ""
        )
    )
    return f"tool: {name}\ncwd: {workdir}\nin: {incoming}\nout: {outgoing}"


def format_stop_entry(payload: dict[str, Any], *, cwd: Path | None = None) -> str:
    workdir = _cwd_from_payload(payload, cwd)
    stopped = payload.get("reason") or payload.get("status") or payload.get("stopped")
    if not stopped:
        stopped = f"session stopped in {workdir}"
    failed = payload.get("failed") or payload.get("error") or "none"
    opened = payload.get("open") or payload.get("pending") or "none"
    if isinstance(opened, list):
        opened = ", ".join(str(item) for item in opened)
    return (
        f"stopped: {_clip_chars(str(stopped), HOOK_FIELD_CHARS)}\n"
        f"failed: {_clip_chars(str(failed), HOOK_FIELD_CHARS)}\n"
        f"open: {_clip_chars(str(opened), HOOK_FIELD_CHARS)}\n"
        f"cwd: {workdir}"
    )


def _write_hook_entry(root: Path, content: str, tags: list[str]) -> dict[str, Any] | None:
    try:
        return write_entry(root, HOOK_SECTION, content, tags, skip_duplicates=True)
    except RemembValidationError as exc:
        if "Duplicate entry" in str(exc):
            return None
        raise


def write_post_tool(root: Path, payload: dict[str, Any], *, cwd: Path | None = None) -> dict[str, Any] | None:
    if should_skip_tool(payload):
        return None
    return _write_hook_entry(
        root,
        format_post_tool_entry(payload, cwd=cwd),
        [HOOK_TAG, HOOK_AUTO_TAG],
    )


def write_stop(root: Path, payload: dict[str, Any] | None = None, *, cwd: Path | None = None) -> dict[str, Any] | None:
    return _write_hook_entry(
        root,
        format_stop_entry(payload or {}, cwd=cwd),
        [HANDOFF_TAG, HOOK_TAG],
    )


def _stamp(entry: dict[str, Any]) -> str:
    return str(entry.get("updated_at") or entry.get("created_at") or "")


def _session_entries(root: Path) -> list[dict[str, Any]]:
    handoffs = [entry for entry in read_entries(root) if HANDOFF_TAG in entry.get("tags", [])]
    handoffs.sort(key=_stamp, reverse=True)
    recent = read_recent_entries(root, limit=SESSION_START_RECENT_LIMIT)
    seen = {entry["id"] for entry in handoffs}
    return handoffs + [entry for entry in recent if entry["id"] not in seen]


def _stats_line(stats: dict[str, Any]) -> str:
    sections = ", ".join(f"{name}={count}" for name, count in sorted(stats.get("by_section", {}).items()) if count)
    return (
        f"total={stats.get('total', 0)} backend={stats.get('storage_backend', '')}"
        + (f" sections={sections}" if sections else "")
    )


def _tags_line(tags: list[dict[str, Any]]) -> str:
    if not tags:
        return "tags: (none)"
    return "tags: " + ", ".join(f"{item['tag']} ({item['count']})" for item in tags)


def _store_lines(root: Path) -> list[str]:
    home = global_root().resolve()
    current = root.resolve()
    lines = ["stores:"]
    lines.append(f"- global path={home} initialized={is_initialized(home)}")
    if current != home:
        lines.append(f"- project path={current} initialized={is_initialized(current)}")
    return lines


def build_session_start_block(root: Path) -> str:
    stats = get_stats(root)
    tags = list_entry_tags(root, limit=SESSION_START_TAG_LIMIT)
    header = "\n".join(
        [
            *_store_lines(root),
            f"stats: {_stats_line(stats)}",
            _tags_line(tags),
        ]
    )
    entries = _session_entries(root)
    while True:
        formatted = format_entries(entries, include_id=True, max_chars=SEARCH_EXCERPT_CHARS)
        block = f"{header}\n\n{formatted}"
        if len(block.encode("utf-8")) <= SESSION_START_MAX_BYTES:
            return block
        if not entries:
            return header
        dropped = False
        for index in range(len(entries) - 1, -1, -1):
            if HANDOFF_TAG not in entries[index].get("tags", []):
                entries.pop(index)
                dropped = True
                break
        if not dropped:
            entries.pop()


def _session_start_host(payload: dict[str, Any]) -> str:
    event = str(payload.get("hook_event_name") or payload.get("hookEventName") or "").strip().lower()
    if event == "sessionstart":
        return "claude"
    if any(key in payload for key in ("composer_mode", "is_background_agent", "cursor_version")):
        return "cursor"
    return "text"


def format_session_start_output(block: str, payload: dict[str, Any] | None = None) -> str:
    host = _session_start_host(payload or {})
    if host == "claude":
        return json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": block,
                }
            },
            ensure_ascii=False,
        )
    if host == "cursor":
        return json.dumps({"additional_context": block}, ensure_ascii=False)
    return block


def run_hook(event: str, raw: str | bytes | None = None, *, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a hook event. Returns (exit_code, stdout, stderr). Never raises to the host."""
    name = event.strip().lower().replace("_", "-")
    if name not in HOOK_EVENTS:
        return 1, "", f"Unknown hook event: {event}. Use {', '.join(HOOK_EVENTS)}.\n"
    payload = parse_hook_payload(raw)
    workdir = _cwd_from_payload(payload, cwd)
    try:
        root = resolve_hook_root(workdir)
        if name == "post-tool":
            write_post_tool(root, payload, cwd=workdir)
            return 0, "", ""
        if name == "stop":
            write_stop(root, payload, cwd=workdir)
            return 0, "", ""
        block = build_session_start_block(root)
        return 0, format_session_start_output(block, payload), ""
    except RemembError as exc:
        return 1, "", f"{exc}\n"
    except Exception as exc:
        return 1, "", f"{exc}\n"


def main(event: str, raw: str | bytes | None = None, *, cwd: Path | None = None) -> int:
    code, stdout, stderr = run_hook(event, raw, cwd=cwd)
    if stdout:
        sys.stdout.write(stdout if stdout.endswith("\n") else stdout + "\n")
    if stderr:
        sys.stderr.write(stderr if stderr.endswith("\n") else stderr + "\n")
    return code
