# memdir

> **Persistent memory for AI agents — local, portable, zero config.**

![memdir demo](demo/demo.gif)

AI agents (Windsurf, Cursor, Claude, Continue) forget everything between sessions.  
`memdir` gives them a structured memory that lives in your project, belongs to you, and works with any agent.

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
.memdir/
  entries.json   ← structured memory (project, actions, systems, user, context)
  meta.json      ← project metadata
```

That's it. A JSON file in your project. Your agent reads it at the start of every session.

---

## Install

```bash
pip install memdir
```

---

## Quickstart

```bash
# Initialize in your project
memdir init

# Write memories
memdir write "Project uses FastAPI + PostgreSQL + async patterns" --section project
memdir write "User prefers direct answers, no filler text" --section user
memdir write "Auth module lives at src/auth/, JWT-based" --section systems

# Read everything (for the agent)
memdir read --agent

# Search semantically
memdir search "authentication"

# Get ready-to-use rules for your editor
memdir rules windsurf
memdir rules cursor
memdir rules claude
```

---

## Agent integration

### Windsurf / Cascade

Add to `.windsurfrules` in your project root:

```
At the START of every conversation:
1. Run: `memdir read --agent` and absorb the memory context

At the END of every conversation:
1. Run: `memdir write "<summary>" --section <section>`
   Sections: project | actions | systems | requests | user | context
```

Or run `memdir rules windsurf` to get the full rules.

### Cursor

Add to `.cursorrules`:

```
At the START of every conversation:
1. Run: `memdir read --agent` and absorb the memory context
...
```

Run `memdir rules cursor` for the full text.

### Claude Code

Add to `CLAUDE.md` at your project root. Run `memdir rules claude`.

### Continue.dev

Run `memdir rules continue` and paste into your config.

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
memdir init              Initialize .memdir/ in current project
memdir write <text>      Write a memory entry (--section, --tags)
memdir read              Read all entries (--section, --agent, --raw)
memdir search <query>    Semantic search (falls back to keyword)
memdir rules [editor]    Print agent rules for windsurf/cursor/claude/continue
```

---

## How search works

`memdir search` uses `sentence-transformers` for semantic similarity search locally.  
No API calls. No embeddings sent to the cloud. Falls back to keyword search if the model isn't available.

---

## Design principles

- **Local first** — everything is a JSON file in your project
- **Portable** — copy `.memdir/` and it works anywhere
- **Agnostic** — works with any agent that can run CLI commands
- **Zero config** — `pip install memdir && memdir init` and you're done
- **No lock-in** — plain JSON, read it with anything

---

## Roadmap

- [ ] MCP server (`memdir mcp`) for native IDE integration
- [ ] `memdir sync` — optional encrypted remote backup
- [ ] `memdir export` — export to Markdown, Obsidian, Notion
- [ ] VS Code / Windsurf extension

---

## Contributing

```bash
git clone https://github.com/yourusername/memdir
cd memdir
pip install -e ".[dev]"
```

PRs welcome. Issues welcome. Stars welcome. 🌟

---

## License

MIT
