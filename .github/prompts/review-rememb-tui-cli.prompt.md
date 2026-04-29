---
name: "Review Rememb TUI And CLI"
description: "Review changes that touch rememb TUI flows, Textual widgets, keyboard bindings, or CLI commands and help output."
argument-hint: "What TUI or CLI change should be reviewed?"
agent: "agent"
tools: [read, search]
---
Review the requested change with a code-review mindset focused only on rememb's TUI and CLI behavior, not persistence internals.

Prioritize findings about:
- broken Textual widget flow, query usage, or event wiring
- regressions in keyboard shortcuts, navigation, modal behavior, or section filtering
- mismatches between CLI help, command entrypoints, and actual behavior
- risky changes to output formatting that would confuse terminal users
- inconsistencies between cli.py, tui.py, utils.py, and user-facing docs when relevant

Review rules:
- Findings first, ordered by severity.
- Focus on bugs, regressions, UX breakage, incorrect command behavior, and missing validation.
- Do not spend review attention on persistence internals unless the TUI or CLI change directly breaks them.
- If no findings are discovered, state that explicitly and mention residual risks or testing gaps.

Output format:
- Findings: each item with severity, impacted file, and why it matters.
- Open questions or assumptions.
- Brief change summary only after findings.