---
name: "Review Rememb Storage Contracts"
description: "Review changes that touch rememb storage, locking, cache invalidation, MCP compatibility, or public memory contracts."
argument-hint: "What change, diff, file, or feature should be reviewed?"
agent: "agent"
tools: [read, search]
---
Review the requested change with a code-review mindset focused on rememb's storage and compatibility boundaries.

Prioritize findings about:
- atomic persistence and corruption risk
- file locking behavior on Unix and Windows
- embedding cache invalidation and stale-data risks
- compatibility of entries.json, meta.json, config.json, section names, and entry ids
- MCP tool names, schemas, defaults, safety guards, and response strings
- public API consistency across helpers.py, store.py, mcp_server.py, cli.py, utils.py, and tui.py when relevant

Review rules:
- Findings first, ordered by severity.
- Focus on bugs, regressions, missing validation, compatibility breaks, and untested risky changes.
- Keep summaries brief and secondary.
- If no findings are discovered, state that explicitly and mention residual risks or testing gaps.

Output format:
- Findings: each item with severity, impacted file, and why it matters.
- Open questions or assumptions.
- Brief change summary only after findings.