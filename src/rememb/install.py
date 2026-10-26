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
MCP_ID = MCP_COMMAND
HOOK_COMMANDS = {event: f"{MCP_COMMAND} hook {event}" for event in ("session-start", "post-tool", "stop")}
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
CODEX_MCP_BEGIN = f"# {MCP_ID}-mcp"
CODEX_MCP_END = f"# /{MCP_ID}-mcp"
MDC_FRONTMATTER = "---\ndescription: Rememb memory rules\nalwaysApply: true\n---"
CONTINUE_YAML = (
    f"name: {MCP_ID}\n"
    "version: 1.0.0\n"
    "schema: v1\n"
    "mcpServers:\n"
    f"  - name: {MCP_ID}\n"
    f"    command: {MCP_COMMAND}\n"
    "    args:\n"
    + "".join(f"      - {arg}\n" for arg in MCP_ARGS)
)


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
    mcp_kind: str
    project_mcp: str | None = None
    user_mcp: str | None = None
    project_rules: str | None = None
    user_rules: str | None = None
    hooks_kind: str | None = None
    project_hooks: str | None = None
    user_hooks: str | None = None
    user_mcp_resolve: Callable[[Path], Path] | None = None


def _user_config_path(home: Path, *, darwin: str, windows: str, other: str) -> Path:
    if sys.platform == "darwin":
        return home / darwin
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData/Roaming"
        return base / windows
    return home / other


def _vscode_user_mcp(home: Path) -> Path:
    return _user_config_path(
        home,
        darwin="Library/Application Support/Code/User/mcp.json",
        windows="Code/User/mcp.json",
        other=".config/Code/User/mcp.json",
    )


def _zed_user_settings(home: Path) -> Path:
    return _user_config_path(
        home,
        darwin="Library/Application Support/Zed/settings.json",
        windows="Zed/settings.json",
        other=".config/zed/settings.json",
    )


HOST_SPECS: dict[str, HostSpec] = {
    "cursor": HostSpec(
        mcp_kind="mcpServers",
        project_mcp=".cursor/mcp.json",
        user_mcp=".cursor/mcp.json",
        project_rules=".cursor/rules/rememb.mdc",
        user_rules=".cursor/rules/rememb.mdc",
        hooks_kind="cursor",
        project_hooks=".cursor/hooks.json",
        user_hooks=".cursor/hooks.json",
    ),
    "claude": HostSpec(
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
        mcp_kind="toml",
        project_mcp=".codex/config.toml",
        user_mcp=".codex/config.toml",
        project_rules="AGENTS.md",
        user_rules=".codex/AGENTS.md",
    ),
    "vscode": HostSpec(
        mcp_kind="servers",
        project_mcp=".vscode/mcp.json",
        project_rules="AGENTS.md",
        user_mcp_resolve=_vscode_user_mcp,
    ),
    "copilot": HostSpec(
        mcp_kind="mcpServers",
        project_mcp=".mcp.json",
        user_mcp=".copilot/mcp-config.json",
        project_rules=".github/copilot-instructions.md",
        user_rules=".copilot/copilot-instructions.md",
    ),
    "windsurf": HostSpec(
        mcp_kind="mcpServers",
        user_mcp=".codeium/windsurf/mcp_config.json",
        project_rules=".windsurf/rules/rememb.md",
        user_rules=".codeium/windsurf/memories/global_rules.md",
    ),
    "continue": HostSpec(
        mcp_kind="yaml-file",
        project_mcp=".continue/mcpServers/rememb.yaml",
        user_mcp=".continue/mcpServers/rememb.yaml",
        project_rules=".continue/rules/rememb.md",
        user_rules=".continue/rules/rememb.md",
    ),
    "gemini": HostSpec(
        mcp_kind="mcpServers",
        project_mcp=".gemini/settings.json",
        user_mcp=".gemini/settings.json",
        project_rules="GEMINI.md",
        user_rules=".gemini/GEMINI.md",
    ),
    "opencode": HostSpec(
        mcp_kind="opencode",
        project_mcp="opencode.json",
        user_mcp=".config/opencode/opencode.json",
        project_rules="AGENTS.md",
        user_rules=".config/opencode/AGENTS.md",
    ),
    "zed": HostSpec(
        mcp_kind="zed",
        project_mcp=".zed/settings.json",
        project_rules="AGENTS.md",
        user_mcp_resolve=_zed_user_settings,
    ),
    "cline": HostSpec(
        mcp_kind="mcpServers",
        project_mcp=".cline/mcp.json",
        user_mcp=".cline/mcp.json",
        project_rules=".clinerules/rememb.md",
        user_rules=".agents/AGENTS.md",
    ),
}
HOSTS = tuple(HOST_SPECS)


def _mcp_block() -> dict[str, Any]:
    return {"command": MCP_COMMAND, "args": list(MCP_ARGS)}


MCP_JSON_VALUES: dict[str, tuple[str, Callable[[], dict[str, Any]]]] = {
    "mcpServers": ("mcpServers", _mcp_block),
    "servers": ("servers", _mcp_block),
    "opencode": ("mcp", lambda: {"type": "local", "command": [MCP_COMMAND, *MCP_ARGS], "enabled": True}),
    "zed": ("context_servers", lambda: {"command": MCP_COMMAND, "args": list(MCP_ARGS), "env": {}}),
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _parse_json_object(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError("JSON root must be an object")
    return loaded


def _put_mapping(data: dict[str, Any], key: str, value: dict[str, Any] | None) -> dict[str, Any]:
    next_data = dict(data)
    mapping = dict(next_data.get(key) or {})
    if value is None:
        mapping.pop(MCP_ID, None)
    else:
        mapping[MCP_ID] = value
    if mapping:
        next_data[key] = mapping
    else:
        next_data.pop(key, None)
    return next_data


def _has_hook_command(entries: object, command: str) -> bool:
    if not isinstance(entries, list):
        return False
    for item in entries:
        if isinstance(item, dict) and (
            str(item.get("command") or "") == command or _has_hook_command(item.get("hooks"), command)
        ):
            return True
    return False


def _keep_hook_item(item: object, commands: set[str]) -> bool:
    if not isinstance(item, dict):
        return True
    if str(item.get("command") or "") in commands:
        return False
    nested = item.get("hooks")
    if isinstance(nested, list):
        item["hooks"] = [handler for handler in nested if _keep_hook_item(handler, commands)]
        return bool(item["hooks"]) or "command" in item
    return True


def _mutate_hooks(data: dict[str, Any], events: dict[str, str], *, nested: bool, uninstall: bool) -> dict[str, Any]:
    next_data = dict(data)
    hooks = dict(next_data.get("hooks") or {})
    commands = set(events.values())
    if uninstall:
        for event, entries in list(hooks.items()):
            if not isinstance(entries, list):
                continue
            kept = [item for item in entries if _keep_hook_item(dict(item) if isinstance(item, dict) else item, commands)]
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event, None)
    else:
        if not nested:
            next_data.setdefault("version", 1)
        for event, command in events.items():
            entries = list(hooks.get(event) or [])
            if not _has_hook_command(entries, command):
                entry: dict[str, Any] = {"command": command}
                entries.append({"hooks": [{"type": "command", **entry}]} if nested else entry)
            hooks[event] = entries
    if hooks:
        next_data["hooks"] = hooks
    else:
        next_data.pop("hooks", None)
    return next_data


def _replace_marked(text: str, begin: str, end: str, block: str | None) -> str | None:
    if begin not in text or end not in text:
        return None
    start = text.index(begin)
    stop = text.index(end) + len(end)
    if block is None:
        cleaned = (text[:start] + text[stop:]).strip()
        return f"{cleaned}\n" if cleaned else ""
    return text[:start] + block + text[stop:]


def _append_block(text: str, block: str) -> str:
    if not text.strip():
        return block
    return f"{text}\n{block}" if text.endswith("\n") else f"{text}\n\n{block}"


def upsert_marked_rules(text: str, *, prefix: str = "") -> str:
    block = marked_rules()
    replaced = _replace_marked(text, RULES_BEGIN, RULES_END, block.strip())
    if replaced is not None:
        return replaced
    return prefix + block if not text.strip() else _append_block(text, block)


def remove_marked_rules(text: str) -> str:
    return _replace_marked(text, RULES_BEGIN, RULES_END, None) or text


def _codex_mcp_block() -> str:
    return (
        f"{CODEX_MCP_BEGIN}\n"
        f"[mcp_servers.{MCP_ID}]\n"
        f'command = "{MCP_COMMAND}"\n'
        f"args = {json.dumps(MCP_ARGS)}\n"
        f"{CODEX_MCP_END}\n"
    )


def upsert_codex_mcp(text: str) -> str:
    replaced = _replace_marked(text, CODEX_MCP_BEGIN, CODEX_MCP_END, _codex_mcp_block().rstrip())
    if replaced is not None:
        return replaced
    if f"[mcp_servers.{MCP_ID}]" in text:
        return text
    return _append_block(text, _codex_mcp_block()) if text.strip() else _codex_mcp_block()


def remove_codex_mcp(text: str) -> str:
    return _replace_marked(text, CODEX_MCP_BEGIN, CODEX_MCP_END, None) or text


def host_paths(host: str, *, project: bool, cwd: Path, home: Path) -> dict[str, Path]:
    spec = HOST_SPECS.get(host)
    if spec is None:
        raise ValueError(f"Unknown host: {host}. Use {', '.join(HOSTS)}.")
    root = cwd if project else home
    paths: dict[str, Path] = {}
    if project and spec.project_mcp:
        paths["mcp"] = cwd / spec.project_mcp
    elif not project and spec.user_mcp_resolve:
        paths["mcp"] = spec.user_mcp_resolve(home)
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
    after_data = mutate(_parse_json_object(before) if before.strip() else {})
    if uninstall and after_data == {}:
        return FileChange(path, before, "")
    return FileChange(path, before, _json_text(after_data) + "\n" if after_data or before.strip() else "")


def _rules_change(path: Path, *, uninstall: bool) -> FileChange:
    before = _read_text(path)
    prefix = f"{MDC_FRONTMATTER}\n\n" if path.suffix == ".mdc" else ""
    if uninstall:
        after = remove_marked_rules(before)
        if path.name.startswith(f"{MCP_ID}.") and after.strip() in {"", MDC_FRONTMATTER}:
            after = ""
    else:
        after = upsert_marked_rules(before if before.strip() or path.suffix != ".mdc" else "", prefix=prefix)
    return FileChange(path, before, after)


def _mcp_change(spec: HostSpec, path: Path, *, uninstall: bool) -> FileChange:
    if spec.mcp_kind == "toml":
        before = _read_text(path)
        return FileChange(path, before, remove_codex_mcp(before) if uninstall else upsert_codex_mcp(before))
    if spec.mcp_kind == "yaml-file":
        return FileChange(path, _read_text(path), "" if uninstall else CONTINUE_YAML)
    key, factory = MCP_JSON_VALUES[spec.mcp_kind]
    return _json_change(
        path,
        lambda data: _put_mapping(data, key, None if uninstall else factory()),
        uninstall=uninstall,
    )


def plan_host(host: str, *, project: bool, cwd: Path, home: Path, uninstall: bool) -> list[FileChange]:
    spec = HOST_SPECS[host]
    paths = host_paths(host, project=project, cwd=cwd, home=home)
    changes: list[FileChange] = []
    if "mcp" in paths:
        changes.append(_mcp_change(spec, paths["mcp"], uninstall=uninstall))
    if "rules" in paths:
        changes.append(_rules_change(paths["rules"], uninstall=uninstall))
    if "hooks" in paths:
        events = CURSOR_HOOK_EVENTS if spec.hooks_kind == "cursor" else CLAUDE_HOOK_EVENTS
        changes.append(
            _json_change(
                paths["hooks"],
                lambda data: _mutate_hooks(data, events, nested=spec.hooks_kind == "claude", uninstall=uninstall),
                uninstall=uninstall,
            )
        )
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
    unknown = [host for host in selected if host not in HOST_SPECS]
    if unknown:
        raise ValueError(f"Unknown host: {unknown[0]}. Use {', '.join(HOSTS)}.")
    cwd = Path(cwd or Path.cwd()).resolve()
    home = Path(home or Path.home()).resolve()
    seen: set[Path] = set()
    changes: list[FileChange] = []
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
        else:
            change.path.parent.mkdir(parents=True, exist_ok=True)
            change.path.write_text(change.after, encoding="utf-8")
        written.append(change)
    return written


def format_plan(changes: list[FileChange], *, apply: bool, uninstall: bool) -> str:
    pending = [change for change in changes if change.changed]
    if not pending:
        return "Already installed. Nothing to change." if not uninstall else "Nothing rememb-owned to remove."
    verb = "Removed" if uninstall and apply else "Wrote" if apply else "Would write"
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
