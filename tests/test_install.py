from __future__ import annotations

import json
from pathlib import Path

from rememb.agent_rules import RULES_BEGIN, RULES_END
from rememb.install import apply_changes, plan_install, run_install


def test_install_apply_writes_mcp_rules_and_hooks(tmp_path: Path):
    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    home.mkdir()
    cwd.mkdir()

    first = run_install(["cursor"], apply=True, project=True, cwd=cwd, home=home)
    mcp = json.loads((cwd / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    rules = (cwd / ".cursor" / "rules" / "rememb.mdc").read_text(encoding="utf-8")
    hooks = json.loads((cwd / ".cursor" / "hooks.json").read_text(encoding="utf-8"))

    assert "Wrote" in first
    assert mcp["mcpServers"]["rememb"] == {"command": "rememb", "args": ["mcp"]}
    assert RULES_BEGIN in rules and RULES_END in rules
    assert "SessionStart already injects" in rules
    assert hooks["hooks"]["sessionStart"][0]["command"] == "rememb hook session-start"
    assert hooks["hooks"]["postToolUse"][0]["command"] == "rememb hook post-tool"
    assert hooks["hooks"]["stop"][0]["command"] == "rememb hook stop"

    second = run_install(["cursor"], apply=True, project=True, cwd=cwd, home=home)
    assert second == "Already installed. Nothing to change."
    assert list(json.loads((cwd / ".cursor" / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]) == ["rememb"]
    assert rules.count(RULES_BEGIN) == 1
    assert json.dumps(hooks).count("rememb hook session-start") == 1


def test_install_dry_run_does_not_write(tmp_path: Path):
    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    home.mkdir()
    cwd.mkdir()

    message = run_install(["claude"], apply=False, project=True, cwd=cwd, home=home)

    assert "Would write" in message
    assert not (cwd / ".mcp.json").exists()
    assert not (cwd / "CLAUDE.md").exists()


def test_install_uninstall_removes_only_rememb_owned(tmp_path: Path):
    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    home.mkdir()
    cwd.mkdir()
    claude_md = cwd / "CLAUDE.md"
    claude_md.write_text("# Project\n\nKeep this.\n", encoding="utf-8")
    mcp_path = cwd / ".mcp.json"
    mcp_path.write_text(json.dumps({"mcpServers": {"other": {"command": "echo"}}}), encoding="utf-8")

    run_install(["claude"], apply=True, project=True, cwd=cwd, home=home)
    assert RULES_BEGIN in claude_md.read_text(encoding="utf-8")
    run_install(["claude"], apply=True, project=True, uninstall=True, cwd=cwd, home=home)

    remaining_rules = claude_md.read_text(encoding="utf-8")
    remaining_mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert "Keep this." in remaining_rules
    assert RULES_BEGIN not in remaining_rules
    assert "rememb" not in remaining_mcp.get("mcpServers", {})
    assert remaining_mcp["mcpServers"]["other"]["command"] == "echo"


def test_plan_install_covers_codex_without_hooks(tmp_path: Path):
    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    home.mkdir()
    cwd.mkdir()

    apply_changes(plan_install(["codex"], project=True, cwd=cwd, home=home))
    config = (cwd / ".codex" / "config.toml").read_text(encoding="utf-8")
    agents = (cwd / "AGENTS.md").read_text(encoding="utf-8")

    assert "[mcp_servers.rememb]" in config
    assert "command = \"rememb\"" in config
    assert RULES_BEGIN in agents
    assert not (cwd / ".codex" / "hooks.json").exists()
