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

Search uses local semantic embeddings (no API, no cloud). Falls back to keyword search if embeddings aren't available.

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
rememb mcp      # Start MCP server for AI agent integration
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
