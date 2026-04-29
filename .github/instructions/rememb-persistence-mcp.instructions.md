---
name: "Rememb Persistence And MCP Guardrails"
description: "Use when changing rememb storage, entries.json or meta.json handling, file locking, cache invalidation, semantic search internals, MCP tools, tool schemas, or public memory contracts."
applyTo: "src/rememb/**/*.py"
---
# Rememb Persistence And MCP Guardrails

- Preserve the local-first contract centered on .rememb, especially entries.json, meta.json, config.json, section names, and 8-character entry ids.
- Route persistence-sensitive changes through the existing helpers and store layers instead of duplicating write, lock, sanitization, initialization, or cache logic elsewhere.
- Keep atomic writes, cross-platform file locking, corruption handling, and cache validation intact when changing storage code.
- Treat MCP tool names, schemas, defaults, response shapes, and safety guards as compatibility-sensitive public contracts.
- When MCP behavior changes, keep store.py and mcp_server.py aligned in argument names, defaults, validation, and returned messages.
- Prefer additive or backward-compatible changes; if a migration or contract break is unavoidable, make it explicit in code and update user-facing docs.
- Do not introduce remote services, background daemons, or alternative persistence backends unless the task explicitly requires that architecture change.
- Validate persistence and MCP edits with the narrowest executable check available, and use python -m py_compile src/rememb/*.py when a focused behavior test is not available.