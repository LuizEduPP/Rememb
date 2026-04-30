<!-- mcp-name: io.github.LuizEduPP/rememb -->
![rememb cover](https://raw.githubusercontent.com/LuizEduPP/Rememb/main/assets/cover.png)

[![Rememb MCP server](https://glama.ai/mcp/servers/LuizEduPP/Rememb/badges/score.svg)](https://glama.ai/mcp/servers/LuizEduPP/Rememb)

AI agents forget everything between sessions. `rememb` gives them persistent memory — local, portable, and works with any agent.

![rememb chat demo](https://raw.githubusercontent.com/LuizEduPP/Rememb/main/assets/rememb-chat.gif)

---

## The problem

Every dev using AI professionally hits this wall:

```
Session 1: "We're using PostgreSQL, auth at src/auth/, prefer async patterns."
Session 2: Agent starts from zero. You explain everything again.
Session 3: Same thing.
```

Existing solutions (Mem0, Zep, Letta) require servers, API keys, and cloud accounts.  
You just want the agent to **remember your project**.

---

## Install

```bash
pip install rememb
```

---

## Quick Start

### With MCP (recommended)

Zero friction. No CLI commands. Native IDE integration.

**1. Add to your IDE's MCP config:**

```json
{
  "mcpServers": {
    "rememb": {
      "command": "rememb",
      "args": ["mcp"]
    }
  }
}
```

**2. Restart your IDE.**

The agent now automatically reads memory at session start, writes when learning something new, and searches when needed.

If you want multiple MCP clients on the same machine to reuse one already-running rememb process, start a persistent local SSE transport:

```bash
rememb mcp --transport sse --host 127.0.0.1 --port 8765
```

This keeps one MCP process alive, so repeated clients can hit the same loaded embedding model through `http://127.0.0.1:8765/sse` and `http://127.0.0.1:8765/messages/`.

### Without MCP

```bash
rememb rules   # Print generic rules for AI agents
```

Copy the output to your editor's rules file (`.windsurfrules`, `.cursorrules`, `CLAUDE.md`, etc.)

---

## How it works

```
.rememb/
  entries.json   ← structured memory (project, actions, systems, user, context)
  meta.json      ← project metadata
```

A JSON file in your project. Your agent reads it at the start of every session.

```
User: "We're using PostgreSQL, auth at src/auth/, async patterns"
Agent: [rememb_write] → Saved

[New session]
Agent: [rememb_read]  → Context loaded
Agent: "I see you're using PostgreSQL with auth at src/auth/..."
```

Search uses local semantic embeddings (no API, no cloud). The embedding model is unloaded after a short idle window by default, so the process does not keep the full model resident forever.

rememb now writes the full configuration set to .rememb/config.json during initialization, so all supported knobs live in one place:

```json
{
  "max_content_length": 1000000,
  "max_tag_length": 500,
  "max_tags_per_entry": 100,
  "max_entries": 100000,
  "semantic_model_idle_ttl_seconds": 15,
  "semantic_model_name": "paraphrase-MiniLM-L3-v2"
}
```

Set semantic_model_idle_ttl_seconds to 0 to unload the model immediately after each semantic operation. If you want a smaller model, you can switch semantic_model_name to another SentenceTransformers model such as paraphrase-MiniLM-L3-v2.

Environment overrides are also available: REMEMB_SEMANTIC_MODEL_IDLE_TTL_SECONDS and REMEMB_SEMANTIC_MODEL_NAME.

---

## Memory sections

| Section | What to store |
|---------|---------------|
| `project` | Tech stack, architecture, goals |
| `actions` | What was done, decisions made |
| `systems` | Services, modules, integrations |
| `requests` | User preferences, recurring asks |
| `user` | Name, style, expertise, preferences |
| `context` | Anything else relevant |

---

## TUI

`rememb` includes a full terminal UI built with [Textual](https://textual.textualize.io/).

```bash
rememb          # Open the TUI
```

Features:
- **Grid of memory cards** — browse all entries organized by section
- **Sidebar navigation** — filter by section with entry counts
- **Inline search** — press `/` to search across all entries
- **Side panel** — create or edit entries without leaving the screen
- **Dynamic layout** — grid adapts to terminal width (1–4 columns)
- **Keyboard shortcuts** — `Ctrl+N` new, `Ctrl+R` refresh, `/` search, `Q` quit

---

## CLI

```bash
rememb          # Open the TUI
rememb mcp      # Start MCP server for AI agent integration over stdio
rememb mcp --transport sse --host 127.0.0.1 --port 8765   # Start one persistent local MCP process
rememb --version, -v    # Show version
rememb --help, -h       # Show help
```

---

## Design

- **Local first** — plain JSON file in your project
- **Portable** — copy `.rememb/` anywhere, it works
- **Agnostic** — any agent, any IDE (MCP or CLI)
- **No lock-in** — no servers, no API keys, no accounts

---

## Contributing

```bash
git clone https://github.com/LuizEduPP/Rememb
cd rememb
pip install -e ".[dev]"
```

PRs welcome. Issues welcome. Stars welcome. 🌟

---

## License

MIT
