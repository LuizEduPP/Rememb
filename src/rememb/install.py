"""Write MCP, Memory Rules, and host hooks. Dry-run unless --apply."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rememb.agent_rules import RULES_BEGIN, RULES_END, marked_rules
from rememb.helpers import _json_text


HOSTS = ("cursor", "claude", "codex")
MCP_COMMAND = "rememb"
MCP_ARGS = ["mcp"]
HOOK_COMMANDS = {
    "session-start": "rememb hook session-start",
    "post-tool": "rememb hook post-tool",
    "stop": "rememb hook stop",
}
CURSOR_HOOK_EVENTS = {
    "sessionStart": HOOK_COMMANDS["session-start"],
    "postToolUse": HOOK_COMMANDS["post-tool"],
    "stop": HOOK_COMMANDS["stop"],
}
CLAUDE_HOOK_EVENTS = {
    "SessionStart": HOOK_COMMANDS["session-start"],
    "PostToolUse": HOOK_COMMANDS["post-tool"],
    "Stop": HOOK_COMMANDS["stop"],
}
CODEX_MCP_BEGIN = "# rememb-mcp"
CODEX_MCP_END = "# /rememb-mcp"
MDC_FRONTMATTER = "---\ndescription: Rememb memory rules\nalwaysApply: true\n---\n\n"


@dataclass(frozen=True)
class FileChange:
    path: Path
    before: str
    after: str

    @property
    def changed(self) -> bool:
        return self.before != self.after


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _parse_json_object(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError("JSON root must be an object")
    return loaded


def _json_file(data: dict[str, Any]) -> str:
    return _json_text(data) + "\n"


def _mcp_server_block() -> dict[str, Any]:
    return {"command": MCP_COMMAND, "args": list(MCP_ARGS)}


def _is_rememb_mcp(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    command = str(entry.get("command") or "")
    args = entry.get("args") or []
    return command.endswith("rememb") and list(args)[:1] == ["mcp"]


def upsert_mcp_servers(data: dict[str, Any]) -> dict[str, Any]:
    next_data = dict(data)
    servers = dict(next_data.get("mcpServers") or {})
    servers["rememb"] = _mcp_server_block()
    next_data["mcpServers"] = servers
    return next_data


def remove_mcp_servers(data: dict[str, Any]) -> dict[str, Any]:
    next_data = dict(data)
    servers = dict(next_data.get("mcpServers") or {})
    servers.pop("rememb", None)
    if servers:
        next_data["mcpServers"] = servers
    else:
        next_data.pop("mcpServers", None)
    return next_data


def _has_hook_command(entries: object, command: str) -> bool:
    if not isinstance(entries, list):
        return False
    for item in entries:
        if isinstance(item, dict) and str(item.get("command") or "") == command:
            return True
        if isinstance(item, dict):
            nested = item.get("hooks")
            if _has_hook_command(nested, command):
                return True
    return False


def upsert_cursor_hooks(data: dict[str, Any]) -> dict[str, Any]:
    next_data = dict(data)
    next_data.setdefault("version", 1)
    hooks = dict(next_data.get("hooks") or {})
    for event, command in CURSOR_HOOK_EVENTS.items():
        entries = list(hooks.get(event) or [])
        if not _has_hook_command(entries, command):
            entries.append({"command": command})
        hooks[event] = entries
    next_data["hooks"] = hooks
    return next_data


def remove_cursor_hooks(data: dict[str, Any]) -> dict[str, Any]:
    next_data = dict(data)
    hooks = dict(next_data.get("hooks") or {})
    commands = set(CURSOR_HOOK_EVENTS.values())
    for event, entries in list(hooks.items()):
        if not isinstance(entries, list):
            continue
        kept = [
            item
            for item in entries
            if not (isinstance(item, dict) and str(item.get("command") or "") in commands)
        ]
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    if hooks:
        next_data["hooks"] = hooks
    else:
        next_data.pop("hooks", None)
    return next_data


def upsert_claude_hooks(data: dict[str, Any]) -> dict[str, Any]:
    next_data = dict(data)
    hooks = dict(next_data.get("hooks") or {})
    for event, command in CLAUDE_HOOK_EVENTS.items():
        groups = list(hooks.get(event) or [])
        if not _has_hook_command(groups, command):
            groups.append({"hooks": [{"type": "command", "command": command}]})
        hooks[event] = groups
    next_data["hooks"] = hooks
    return next_data


def remove_claude_hooks(data: dict[str, Any]) -> dict[str, Any]:
    next_data = dict(data)
    hooks = dict(next_data.get("hooks") or {})
    commands = set(CLAUDE_HOOK_EVENTS.values())

    def _keep_handler(item: object) -> bool:
        if not isinstance(item, dict):
            return True
        if str(item.get("command") or "") in commands:
            return False
        nested = item.get("hooks")
        if isinstance(nested, list):
            item = dict(item)
            item["hooks"] = [handler for handler in nested if _keep_handler(handler)]
            return bool(item["hooks"]) or "command" in item
        return True

    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue
        kept = [item for item in groups if _keep_handler(item)]
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    if hooks:
        next_data["hooks"] = hooks
    else:
        next_data.pop("hooks", None)
    return next_data


def upsert_marked_rules(text: str, *, prefix: str = "") -> str:
    block = marked_rules()
    if RULES_BEGIN in text and RULES_END in text:
        start = text.index(RULES_BEGIN)
        end = text.index(RULES_END) + len(RULES_END)
        return text[:start] + block.strip() + text[end:]
    if not text.strip():
        return f"{prefix}{block}"
    if text.endswith("\n"):
        return f"{text}\n{block}"
    return f"{text}\n\n{block}"


def remove_marked_rules(text: str) -> str:
    if RULES_BEGIN not in text or RULES_END not in text:
        return text
    start = text.index(RULES_BEGIN)
    end = text.index(RULES_END) + len(RULES_END)
    cleaned = (text[:start] + text[end:]).strip()
    return f"{cleaned}\n" if cleaned else ""


def _codex_mcp_block() -> str:
    return (
        f"{CODEX_MCP_BEGIN}\n"
        "[mcp_servers.rememb]\n"
        f'command = "{MCP_COMMAND}"\n'
        f"args = {json.dumps(MCP_ARGS)}\n"
        f"{CODEX_MCP_END}\n"
    )


def upsert_codex_mcp(text: str) -> str:
    if CODEX_MCP_BEGIN in text and CODEX_MCP_END in text:
        start = text.index(CODEX_MCP_BEGIN)
        end = text.index(CODEX_MCP_END) + len(CODEX_MCP_END)
        return text[:start] + _codex_mcp_block().rstrip() + text[end:]
    if "[mcp_servers.rememb]" in text:
        return text
    if not text.strip():
        return _codex_mcp_block()
    if text.endswith("\n"):
        return f"{text}\n{_codex_mcp_block()}"
    return f"{text}\n\n{_codex_mcp_block()}"


def remove_codex_mcp(text: str) -> str:
    if CODEX_MCP_BEGIN in text and CODEX_MCP_END in text:
        start = text.index(CODEX_MCP_BEGIN)
        end = text.index(CODEX_MCP_END) + len(CODEX_MCP_END)
        return (text[:start] + text[end:]).strip() + ("\n" if text[:start].strip() or text[end:].strip() else "")
    return text


def host_paths(host: str, *, project: bool, cwd: Path, home: Path) -> dict[str, Path]:
    if host == "cursor":
        base = cwd / ".cursor" if project else home / ".cursor"
        return {
            "mcp": base / "mcp.json",
            "rules": base / "rules" / "rememb.mdc",
            "hooks": base / "hooks.json",
        }
    if host == "claude":
        if project:
            return {
                "mcp": cwd / ".mcp.json",
                "rules": cwd / "CLAUDE.md",
                "hooks": cwd / ".claude" / "settings.json",
            }
        return {
            "mcp": home / ".claude.json",
            "rules": home / ".claude" / "CLAUDE.md",
            "hooks": home / ".claude" / "settings.json",
        }
    if host == "codex":
        if project:
            return {
                "mcp": cwd / ".codex" / "config.toml",
                "rules": cwd / "AGENTS.md",
            }
        return {
            "mcp": home / ".codex" / "config.toml",
            "rules": home / "AGENTS.md",
        }
    raise ValueError(f"Unknown host: {host}")


def _json_change(path: Path, mutate, *, uninstall: bool) -> FileChange:
    before = _read_text(path)
    data = _parse_json_object(before) if before.strip() else {}
    after_data = mutate(data)
    if uninstall and after_data == {}:
        return FileChange(path, before, "")
    return FileChange(path, before, _json_file(after_data) if after_data or before.strip() else "")


def plan_host(host: str, *, project: bool, cwd: Path, home: Path, uninstall: bool) -> list[FileChange]:
    paths = host_paths(host, project=project, cwd=cwd, home=home)
    changes: list[FileChange] = []

    if host == "codex":
        before = _read_text(paths["mcp"])
        after = remove_codex_mcp(before) if uninstall else upsert_codex_mcp(before)
        changes.append(FileChange(paths["mcp"], before, after))
    elif host == "claude" and not project:
        changes.append(
            _json_change(paths["mcp"], remove_mcp_servers if uninstall else upsert_mcp_servers, uninstall=uninstall)
        )
    else:
        changes.append(
            _json_change(paths["mcp"], remove_mcp_servers if uninstall else upsert_mcp_servers, uninstall=uninstall)
        )

    rules_before = _read_text(paths["rules"])
    if host == "cursor" and not uninstall and not rules_before.strip():
        rules_after = upsert_marked_rules("", prefix=MDC_FRONTMATTER)
    elif uninstall:
        rules_after = remove_marked_rules(rules_before)
        if host == "cursor" and rules_after.strip() in {"", "---\ndescription: Rememb memory rules\nalwaysApply: true\n---"}:
            rules_after = ""
    else:
        rules_after = upsert_marked_rules(rules_before, prefix=MDC_FRONTMATTER if host == "cursor" else "")
    changes.append(FileChange(paths["rules"], rules_before, rules_after))

    hooks_path = paths.get("hooks")
    if hooks_path is not None:
        if host == "cursor":
            mutate = remove_cursor_hooks if uninstall else upsert_cursor_hooks
        else:
            mutate = remove_claude_hooks if uninstall else upsert_claude_hooks
        changes.append(_json_change(hooks_path, mutate, uninstall=uninstall))

    return changes


def plan_install(
    hosts: list[str] | None = None,
    *,
    project: bool = False,
    uninstall: bool = False,
    cwd: Path | None = None,
    home: Path | None = None,
) -> list[FileChange]:
    selected = list(hosts or HOSTS)
    for host in selected:
        if host not in HOSTS:
            raise ValueError(f"Unknown host: {host}. Use {', '.join(HOSTS)}.")
    cwd = Path(cwd or Path.cwd()).resolve()
    home = Path(home or Path.home()).resolve()
    changes: list[FileChange] = []
    for host in selected:
        changes.extend(plan_host(host, project=project, cwd=cwd, home=home, uninstall=uninstall))
    return changes


def apply_changes(changes: list[FileChange]) -> list[FileChange]:
    written: list[FileChange] = []
    for change in changes:
        if not change.changed:
            continue
        if change.after == "":
            if change.path.exists():
                change.path.unlink()
            written.append(change)
            continue
        change.path.parent.mkdir(parents=True, exist_ok=True)
        change.path.write_text(change.after, encoding="utf-8")
        written.append(change)
    return written


def format_plan(changes: list[FileChange], *, apply: bool, uninstall: bool) -> str:
    verb = "Removed" if uninstall and apply else "Wrote" if apply else "Would write"
    lines = []
    pending = [change for change in changes if change.changed]
    if not pending:
        return "Already installed. Nothing to change." if not uninstall else "Nothing rememb-owned to remove."
    for change in pending:
        action = "delete" if change.after == "" else "update" if change.before else "create"
        lines.append(f"{verb} [{action}] {change.path}")
    return "\n".join(lines)


def run_install(
    hosts: list[str] | None = None,
    *,
    apply: bool = False,
    project: bool = False,
    uninstall: bool = False,
    cwd: Path | None = None,
    home: Path | None = None,
) -> str:
    changes = plan_install(hosts, project=project, uninstall=uninstall, cwd=cwd, home=home)
    if apply:
        apply_changes(changes)
    return format_plan(changes, apply=apply, uninstall=uninstall)
