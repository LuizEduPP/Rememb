from __future__ import annotations

import json
from pathlib import Path

from rememb.config import HANDOFF_TAG, HOOK_SECTION
from rememb.hooks import run_hook
from rememb.store import init, read_entries, write_entry


def _entries(root: Path) -> list[dict]:
    return read_entries(root, HOOK_SECTION)


def test_post_tool_writes_one_entry(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    init(root)

    payload = {
        "tool_name": "Write",
        "cwd": str(root),
        "tool_input": {"path": "app.py", "contents": "print(1)"},
        "tool_output": "wrote app.py",
    }
    code, out, err = run_hook("post-tool", json.dumps(payload), cwd=root)

    assert code == 0
    assert out == ""
    assert err == ""
    entries = _entries(root)
    assert len(entries) == 1
    assert "tool: Write" in entries[0]["content"]
    assert str(root.resolve()) in entries[0]["content"]
    assert {"hook", "auto"} <= set(entries[0]["tags"])


def test_rememb_tool_is_skipped(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    init(root)

    code, _, err = run_hook(
        "post-tool",
        json.dumps({"tool_name": "rememb_write", "cwd": str(root), "tool_input": {"content": "x"}}),
        cwd=root,
    )

    assert code == 0
    assert err == ""
    assert _entries(root) == []


def test_noisy_read_is_skipped_unless_error(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    init(root)

    skipped = run_hook(
        "post-tool",
        json.dumps({"tool_name": "Read", "cwd": str(root), "tool_output": "ok"}),
        cwd=root,
    )
    failed = run_hook(
        "post-tool",
        json.dumps({"tool_name": "grep", "cwd": str(root), "is_error": True, "tool_output": "boom"}),
        cwd=root,
    )

    assert skipped[0] == 0
    assert failed[0] == 0
    contents = [entry["content"] for entry in _entries(root)]
    assert contents == [contents[0]]
    assert "tool: grep" in contents[0]


def test_duplicate_post_tool_is_rejected(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    payload = json.dumps({"tool_name": "Write", "cwd": str(root), "tool_input": "a", "tool_output": "b"})

    first = run_hook("post-tool", payload, cwd=root)
    second = run_hook("post-tool", payload, cwd=root)

    assert first[0] == 0
    assert second[0] == 0
    assert len(_entries(root)) == 1


def test_session_start_prints_recent_tags_and_stats(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    write_entry(root, "project", "Auth lives in src/auth.", ["auth"])

    code, out, err = run_hook("session-start", cwd=root)

    assert code == 0
    assert err == ""
    assert "Auth lives in src/auth." in out
    assert "auth (1)" in out
    assert "total=1" in out
    assert "backend=json" in out


def test_stop_writes_handoff_and_session_start_puts_it_first(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    write_entry(root, "project", "Older project fact.", ["stack"])
    code, _, err = run_hook(
        "stop",
        json.dumps({"cwd": str(root), "reason": "paused on auth", "failed": "none", "open": ["src/auth.py"]}),
        cwd=root,
    )
    assert code == 0
    assert err == ""

    handoff = [entry for entry in read_entries(root) if HANDOFF_TAG in entry["tags"]]
    assert len(handoff) == 1
    assert "stopped: paused on auth" in handoff[0]["content"]
    assert "cwd:" in handoff[0]["content"]

    _, out, _ = run_hook("session-start", cwd=root)
    assert out.index("paused on auth") < out.index("Older project fact.")


def test_session_start_claude_envelope(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    write_entry(root, "project", "Keep this.", ["keep"])

    code, out, err = run_hook("session-start", json.dumps({"hook_event_name": "SessionStart", "cwd": str(root)}), cwd=root)
    payload = json.loads(out)

    assert code == 0
    assert err == ""
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Keep this." in payload["hookSpecificOutput"]["additionalContext"]


def test_long_output_is_clipped(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    init(root)
    huge = "x" * 20_000
    run_hook(
        "post-tool",
        json.dumps({"tool_name": "Write", "cwd": str(root), "tool_output": huge}),
        cwd=root,
    )

    content = _entries(root)[0]["content"]
    assert huge not in content
    assert len(content) < 1000
