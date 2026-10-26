"""Write MCP, Memory Rules, and host hooks. Dry-run unless --apply."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from rememb.agent_rules import RULES_BEGIN, RULES_END, marked_rules
from rememb.helpers import _json_text


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
CONTINUE_YAML = (
    "name: rememb\n"
    "version: 1.0.0\n"
    "schema: v1\n"
    "mcpServers:\n"
    "  - name: rememb\n"
    f"    command: {MCP_COMMAND}\n"
    "    args:\n"
    "      - mcp\n"
)
MDC_ONLY_FRONTMATTER = "---\ndescription: Rememb memory rules\nalwaysApply: true\n---"


@dataclass(frozen=True)
class FileChange:
    path: Path
    before: str
    after: str

    @property
    def changed(self) -> bool:
        return self.before != self.after


@dataclass(frozen=True)
class HostSpec:
    id: str
    mcp_kind: str
    project_mcp: str | None = None
    user_mcp: str | None = None
    project_rules: str | None = None
    user_rules: str | None = None
    rules_kind: str = "marked"
    rules_owned: bool = False
    hooks_kind: str | None = None
    project_hooks: str | None = None
    user_hooks: str | None = None


HOST_SPECS: dict[str, HostSpec] = {
    "cursor": HostSpec(
        id="cursor",
        mcp_kind="mcpServers",
        project_mcp=".cursor/mcp.json",
        user_mcp=".cursor/mcp.json",
        project_rules=".cursor/rules/rememb.mdc",
        user_rules=".cursor/rules/rememb.mdc",
        rules_kind="mdc",
        rules_owned=True,
        hooks_kind="cursor",
        project_hooks=".cursor/hooks.json",
        user_hooks=".cursor/hooks.json",
    ),
    "claude": HostSpec(
        id="claude",
        mcp_kind="mcpServers",
        project_mcp=".mcp.json",
        user_mcp=".claude.json",
        project_rules="CLAUDE.md",
        user_rules=".claude/CLAUDE.md",
        hooks_kind="claude",
        project_hooks=".claude/settings.json",
        user_hooks=".claude/settings.json",
    ),
    "codex": HostSpec(
        id="codex",
        mcp_kind="toml",
        project_mcp=".codex/config.toml",
        user_mcp=".codex/config.toml",
        project_rules="AGENTS.md",
        user_rules=".codex/AGENTS.md",
    ),
    "vscode": HostSpec(
        id="vscode",
        mcp_kind="servers",
        project_mcp=".vscode/mcp.json",
        project_rules="AGENTS.md",
    ),
    "copilot": HostSpec(
        id="copilot",
        mcp_kind="mcpServers",
        project_mcp=".mcp.json",
        user_mcp=".copilot/mcp-config.json",
        project_rules=".github/copilot-instructions.md",
        user_rules=".copilot/copilot-instructions.md",
    ),
    "windsurf": HostSpec(
        id="windsurf",
        mcp_kind="mcpServers",
        user_mcp=".codeium/windsurf/mcp_config.json",
        project_rules=".windsurf/rules/rememb.md",
        user_rules=".codeium/windsurf/memories/global_rules.md",
    ),
    "continue": HostSpec(
        id="continue",
        mcp_kind="yaml-file",
        project_mcp=".continue/mcpServers/rememb.yaml",
        user_mcp=".continue/mcpServers/rememb.yaml",
        project_rules=".continue/rules/rememb.md",
        user_rules=".continue/rules/rememb.md",
        rules_owned=True,
    ),
    "gemini": HostSpec(
        id="gemini",
        mcp_kind="mcpServers",
        project_mcp=".gemini/settings.json",
        user_mcp=".gemini/settings.json",
        project_rules="GEMINI.md",
        user_rules=".gemini/GEMINI.md",
    ),
    "opencode": HostSpec(
        id="opencode",
        mcp_kind="opencode",
        project_mcp="opencode.json",
        user_mcp=".config/opencode/opencode.json",
        project_rules="AGENTS.md",
        user_rules=".config/opencode/AGENTS.md",
    ),
    "zed": HostSpec(
        id="zed",
        mcp_kind="zed",
        project_mcp=".zed/settings.json",
        project_rules="AGENTS.md",
    ),
    "cline": HostSpec(
        id="cline",
        mcp_kind="mcpServers",
        project_mcp=".cline/mcp.json",
        user_mcp=".cline/mcp.json",
        project_rules=".clinerules/rememb.md",
        user_rules=".agents/AGENTS.md",
    ),
}
HOSTS = tuple(HOST_SPECS)


def _vscode_user_mcp(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library/Application Support/Code/User/mcp.json"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData/Roaming"
        return base / "Code/User/mcp.json"
    return home / ".config/Code/User/mcp.json"


def _zed_user_settings(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library/Application Support/Zed/settings.json"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData/Roaming"
        return base / "Zed/settings.json"
    return home / ".config/zed/settings.json"


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


def _upsert_mapping(data: dict[str, Any], key: str, value: dict[str, Any]) -> dict[str, Any]:
    next_data = dict(data)
    mapping = dict(next_data.get(key) or {})
    mapping["rememb"] = value
    next_data[key] = mapping
    return next_data


def _remove_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    next_data = dict(data)
    mapping = dict(next_data.get(key) or {})
    mapping.pop("rememb", None)
    if mapping:
        next_data[key] = mapping
    else:
        next_data.pop(key, None)
    return next_data


def upsert_mcp_servers(data: dict[str, Any]) -> dict[str, Any]:
    return _upsert_mapping(data, "mcpServers", _mcp_server_block())


def remove_mcp_servers(data: dict[str, Any]) -> dict[str, Any]:
    return _remove_mapping(data, "mcpServers")


def upsert_vscode_servers(data: dict[str, Any]) -> dict[str, Any]:
    return _upsert_mapping(data, "servers", _mcp_server_block())


def remove_vscode_servers(data: dict[str, Any]) -> dict[str, Any]:
    return _remove_mapping(data, "servers")


def upsert_opencode_mcp(data: dict[str, Any]) -> dict[str, Any]:
    return _upsert_mapping(
        data,
        "mcp",
        {"type": "local", "command": [MCP_COMMAND, *MCP_ARGS], "enabled": True},
    )


def remove_opencode_mcp(data: dict[str, Any]) -> dict[str, Any]:
    return _remove_mapping(data, "mcp")


def upsert_zed_servers(data: dict[str, Any]) -> dict[str, Any]:
    return _upsert_mapping(data, "context_servers", {"command": MCP_COMMAND, "args": list(MCP_ARGS), "env": {}})


def remove_zed_servers(data: dict[str, Any]) -> dict[str, Any]:
    return _remove_mapping(data, "context_servers")


JSON_MUTATORS: dict[str, tuple[Callable[[dict[str, Any]], dict[str, Any]], Callable[[dict[str, Any]], dict[str, Any]]]] = {
    "mcpServers": (upsert_mcp_servers, remove_mcp_servers),
    "servers": (upsert_vscode_servers, remove_vscode_servers),
    "opencode": (upsert_opencode_mcp, remove_opencode_mcp),
    "zed": (upsert_zed_servers, remove_zed_servers),
}


def _has_hook_command(entries: object, command: str) -> bool:
    if not isinstance(entries, list):
        return False
    for item in entries:
        if isinstance(item, dict) and str(item.get("command") or "") == command:
            return True
        if isinstance(item, dict) and _has_hook_command(item.get("hooks"), command):
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


HOOK_MUTATORS = {
    "cursor": (upsert_cursor_hooks, remove_cursor_hooks),
    "claude": (upsert_claude_hooks, remove_claude_hooks),
}


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
    spec = HOST_SPECS.get(host)
    if spec is None:
        raise ValueError(f"Unknown host: {host}")
    root = cwd if project else home
    paths: dict[str, Path] = {}

    if project and spec.project_mcp:
        paths["mcp"] = cwd / spec.project_mcp
    elif not project and host == "vscode":
        paths["mcp"] = _vscode_user_mcp(home)
    elif not project and host == "zed":
        paths["mcp"] = _zed_user_settings(home)
    elif not project and spec.user_mcp:
        paths["mcp"] = home / spec.user_mcp

    rules = spec.project_rules if project else spec.user_rules
    if rules:
        paths["rules"] = root / rules

    hooks = spec.project_hooks if project else spec.user_hooks
    if spec.hooks_kind and hooks:
        paths["hooks"] = root / hooks
    return paths


def _json_change(path: Path, mutate, *, uninstall: bool) -> FileChange:
    before = _read_text(path)
    data = _parse_json_object(before) if before.strip() else {}
    after_data = mutate(data)
    if uninstall and after_data == {}:
        return FileChange(path, before, "")
    return FileChange(path, before, _json_file(after_data) if after_data or before.strip() else "")


def _rules_change(spec: HostSpec, path: Path, *, uninstall: bool) -> FileChange:
    before = _read_text(path)
    prefix = MDC_FRONTMATTER if spec.rules_kind == "mdc" else ""
    owned = spec.rules_owned or path.name.startswith("rememb.")
    if uninstall:
        after = remove_marked_rules(before)
        if owned and after.strip() in {"", MDC_ONLY_FRONTMATTER}:
            after = ""
    elif spec.rules_kind == "mdc" and not before.strip():
        after = upsert_marked_rules("", prefix=prefix)
    else:
        after = upsert_marked_rules(before, prefix=prefix)
    return FileChange(path, before, after)


def plan_host(host: str, *, project: bool, cwd: Path, home: Path, uninstall: bool) -> list[FileChange]:
    spec = HOST_SPECS[host]
    paths = host_paths(host, project=project, cwd=cwd, home=home)
    changes: list[FileChange] = []

    mcp_path = paths.get("mcp")
    if mcp_path is not None:
        if spec.mcp_kind == "toml":
            before = _read_text(mcp_path)
            after = remove_codex_mcp(before) if uninstall else upsert_codex_mcp(before)
            changes.append(FileChange(mcp_path, before, after))
        elif spec.mcp_kind == "yaml-file":
            before = _read_text(mcp_path)
            after = "" if uninstall else CONTINUE_YAML
            changes.append(FileChange(mcp_path, before, after))
        else:
            upsert, remove = JSON_MUTATORS[spec.mcp_kind]
            changes.append(_json_change(mcp_path, remove if uninstall else upsert, uninstall=uninstall))

    rules_path = paths.get("rules")
    if rules_path is not None:
        changes.append(_rules_change(spec, rules_path, uninstall=uninstall))

    hooks_path = paths.get("hooks")
    if hooks_path is not None and spec.hooks_kind:
        upsert, remove = HOOK_MUTATORS[spec.hooks_kind]
        changes.append(_json_change(hooks_path, remove if uninstall else upsert, uninstall=uninstall))

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
        if host not in HOST_SPECS:
            raise ValueError(f"Unknown host: {host}. Use {', '.join(HOSTS)}.")
    cwd = Path(cwd or Path.cwd()).resolve()
    home = Path(home or Path.home()).resolve()
    changes: list[FileChange] = []
    seen: set[Path] = set()
    for host in selected:
        for change in plan_host(host, project=project, cwd=cwd, home=home, uninstall=uninstall):
            if change.path in seen:
                continue
            seen.add(change.path)
            changes.append(change)
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
    pending = [change for change in changes if change.changed]
    if not pending:
        return "Already installed. Nothing to change." if not uninstall else "Nothing rememb-owned to remove."
    return "\n".join(
        f"{verb} [{'delete' if change.after == '' else 'update' if change.before else 'create'}] {change.path}"
        for change in pending
    )


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
