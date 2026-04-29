---
name: "Rememb MCP Schema And Output Compatibility"
description: "Use when changing mcp_server.py tool definitions, MCP input schemas, tool argument names, output strings, defaults, safety guards, or response formatting exposed to MCP clients."
applyTo: "src/rememb/mcp_server.py"
---
# Rememb MCP Schema And Output Compatibility

- Treat every MCP tool name, inputSchema field, enum, required key, default value, and response string as a compatibility-sensitive surface for clients.
- Keep the MCP contract aligned with the store API: argument names, defaults, validation paths, and success or error messages should remain coherent across layers.
- Do not rename or reshape MCP tools casually; prefer additive evolution and preserve existing behavior unless the task explicitly requires a contract change.
- Preserve safety semantics such as confirm flags, entry id validation, and explicit not-found or invalid-format responses.
- When introducing a new MCP option or changing a response, verify that the wording still matches the actual store behavior and does not imply unsupported guarantees.
- If a contract break is intentional, make it explicit in code and update the relevant docs in the same change.