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

```bash
pip install rememb
```

For semantic search support:

```bash
pip install rememb[semantic]
```

For PDF import support:

```bash
pip install rememb[pdf]
```

---

## Agent integration

**Configure once. Works forever.**

Run `rememb rules <editor>` to get the instructions for your editor, then paste them once. From that point on, your agent automatically reads and writes memory on every session.

```bash
rememb rules windsurf   # Windsurf / Cascade
rememb rules cursor     # Cursor
rememb rules claude     # Claude Code
rememb rules continue   # Continue.dev
rememb rules vscode     # VS Code + Copilot
```

| Editor | Where to paste |
|--------|---------------|
| **Windsurf / Cascade** | `.windsurfrules` at project root — or Settings → Cascade → Custom Instructions |
| **Cursor** | `.cursorrules` at project root — or Settings → Rules for AI |
| **Claude Code** | `CLAUDE.md` at project root (auto-read every session) |
| **Continue.dev** | `config.json` → `models[].systemMessage` |
| **VS Code + Copilot** | `.github/copilot-instructions.md` at project root (auto-read by Copilot) |

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

## How search works

`rememb search` uses `sentence-transformers` for semantic similarity search locally.  
No API calls. No embeddings sent to the cloud. Falls back to keyword search if the model isn't available.

---

## Design principles

- **Local first** — everything is a JSON file in your project
- **Portable** — copy `.rememb/` and it works anywhere
- **Agnostic** — works with any agent that can run CLI commands
- **Zero config** — `pip install rememb && rememb init` and you're done
- **No lock-in** — plain JSON, read it with anything

---

## MCP Server (Native IDE Integration)

For **zero-friction** integration, use the MCP server. No CLI commands required.

```bash
# Install with MCP support
pip install rememb[mcp]

# Run the server
rememb mcp
```

The MCP server provides native tools that agents can call directly:

| Tool | Purpose |
|------|---------|
| `rememb_read` | Load all memory at session start |
| `rememb_search` | Find relevant context |
| `rememb_write` | Save new memories |
| `rememb_edit` | Update existing entries |
| `rememb_delete` | Remove entries |
| `rememb_clear` | Delete all (with confirmation) |

### Configure your IDE

**Windsurf / Cascade:**
Add to `~/.codeium/windsurf/mcp_config.json`:
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

**Claude Desktop:**
Add to `claude_desktop_config.json`:
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

**Cursor:**
Add to `.cursor/mcp.json`:
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
