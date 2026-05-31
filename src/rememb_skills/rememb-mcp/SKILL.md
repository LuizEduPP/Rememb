---
name: rememb-mcp
description: Work safely on rememb MCP tools, schemas, and compatibility-sensitive server behavior. Use when the task changes MCP contracts, tool definitions, response formats, or backward-compatibility-sensitive server logic.
---

# Rememb MCP Skill

## Overview

Use this skill when working on rememb MCP tools, schemas, response strings, and backward-compatible server behavior.

## When to Use

Apply this skill when a task changes MCP contracts, tool definitions, response formats, or compatibility-sensitive server logic.

## Core Workflow

1. Identify the MCP-facing contract being changed.
2. Keep store and MCP layers aligned in arguments, validation, and returned messages.
3. Preserve existing tool names and defaults unless the change is explicitly additive.
4. Run a narrow contract-focused validation after the change.

## Examples

- Updating a tool schema in `mcp_server.py`
- Adjusting MCP response strings without breaking clients
- Verifying compatibility-sensitive handler changes

## Best Practices

- Preserve existing MCP tool names and defaults unless the change is explicitly additive.
- Keep store and MCP layers aligned in arguments, validation, and returned messages.
- Prefer narrow tests on the MCP contract after changing tool registration or handlers.

## References

- See the repository MCP instructions and adjacent MCP server handlers for contract details.