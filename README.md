# Rememb

> **Persistent memory for AI agents — local, portable, zero config.**

![rememb demo](https://raw.githubusercontent.com/LuizEduPP/rememb/main/demo/demo.gif)

AI agents (Windsurf, Cursor, Claude, Continue) forget everything between sessions.  
`rememb` gives them a structured memory that lives in your project, belongs to you, and works with any agent.

---

## The problem

Every developer using AI agents hits this wall:

```
Session 1: "We're using PostgreSQL, the auth module is at src/auth/, prefer async patterns."
Session 2: Agent starts from zero. You explain everything again.
Session 3: Same thing.
```

Existing solutions (Mem0, Zep, Letta) require servers, API keys, cloud accounts, and framework lock-in.  
You just want the agent to **remember your project**.

---

## The solution

```
.rememb/
  entries.json   ← structured memory (project, actions, systems, user, context)
  meta.json      ← project metadata
```

That's it. A JSON file in your project. Your agent reads it at the start of every session.

---

## Install

**Recommended (with MCP support):**
```bash
pip install rememb[mcp]
```

**Minimal (CLI only):**
```bash
pip install rememb
```

**All features:**
```bash
pip install rememb[mcp,semantic,pdf]
```

---

## Quick Start (MCP — Recommended)

**Zero friction. No CLI commands. Native IDE integration.**

### 1. Install with MCP
```bash
pip install rememb[mcp]
```

### 2. Add to your IDE config

Add this to your IDE's MCP config:

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

| Editor | Config file |
|--------|-------------|
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` |
| **Cursor** | `.cursor/mcp.json` |
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` |

### 3. Restart your IDE

The agent now automatically:
- **Reads** memory at session start
- **Writes** memories when learning something new
- **Searches** context when needed

No configuration needed. No commands to remember.

---

## Alternative: CLI Integration

If your editor doesn't support MCP yet, use CLI-based integration:

```bash
rememb rules windsurf   # Get rules for your editor
```

Copy the output to your editor's rules file. See `rememb rules --help` for all options.

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

## Commands

```
rememb init              Initialize memory store
rememb write <text>      Add new entry (--section, --tags)
rememb read              List all entries (--section, --raw, --agent)
rememb search <query>    Search by content or tags (--top, --agent)
rememb delete <id>       Remove single entry (--yes)
rememb edit <id>         Modify existing entry (--content, --section, --tags)
rememb clear             Delete ALL entries (requires --yes)
rememb import <folder>   Import .md/.txt/.pdf files (--section, --recursive, --dry-run)
rememb rules [editor]    Show AI editor integration rules
```

---

## How it works

With MCP enabled, the agent automatically manages memory:

```
User: "We're using PostgreSQL, auth at src/auth/, async patterns"
Agent: [calls rememb_write] → Saved to memory

[New session starts]
Agent: [calls rememb_read]  → Loads all context automatically
Agent: "I see you're using PostgreSQL with auth at src/auth/..."
```

### Search

`rememb search` uses local semantic search (no API calls, no cloud). Falls back to keyword search if embeddings aren't available.

---

## Design principles

- **Local first** — everything is a JSON file in your project
- **Portable** — copy `.rememb/` and it works anywhere
- **Agnostic** — works with any agent (MCP or CLI)
- **Zero config** — `pip install rememb[mcp]` and add to IDE
- **No lock-in** — plain JSON, read it with anything

---

## CLI Reference

For scripting or manual management:

```bash
rememb init                    # Initialize memory store
rememb write "text"            # Add memory (--section, --tags)
rememb read                    # List all entries
rememb search "query"          # Semantic search
rememb delete <id>             # Remove entry
rememb edit <id> --content "x" # Update entry
rememb clear --yes             # Delete all
rememb import <folder>         # Import .md/.txt/.pdf
```

---

## Roadmap

### Done ✓
- [x] MCP server (`rememb mcp`) — native IDE integration, no CLI required

### Planned
- [ ] `rememb sync` — sync `~/.rememb/` across machines via private git
- [ ] `rememb web` — local browser UI to manage memories visually
- [ ] VS Code / Windsurf extension
- [ ] `rememb export` — export memory to Markdown / Obsidian / Notion

---

## Contributing

```bash
git clone https://github.com/LuizEduPP/rememb
cd rememb
pip install -e ".[dev]"
```

PRs welcome. Issues welcome. Stars welcome. 🌟

---

## License

MIT
