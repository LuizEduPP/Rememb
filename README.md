# rememb

> **Persistent memory for AI agents — local, portable, zero config.**

![rememb demo](demo/demo.gif)

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
git clone https://github.com/LuizEduPP/rememb.git
cd rememb
pip install -e .
```

---

## Quickstart

```bash
# Initialize in your project
rememb init

# Write memories
rememb write "Project uses FastAPI + PostgreSQL + async patterns" --section project
rememb write "User prefers direct answers, no filler text" --section user
rememb write "Auth module lives at src/auth/, JWT-based" --section systems

# Read everything (for the agent)
rememb read --agent

# Search semantically
rememb search "authentication"

# Get ready-to-use rules for your editor
rememb rules windsurf
rememb rules cursor
rememb rules claude
rememb rules continue
rememb rules vscode
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
rememb init              Initialize .rememb/ in current project
rememb write <text>      Write a memory entry (--section, --tags)
rememb read              Read all entries (--section, --agent, --raw)
rememb search <query>    Semantic search (falls back to keyword)
rememb rules [editor]    Print agent rules for windsurf/cursor/claude/continue
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

## Roadmap

- [ ] MCP server (`rememb mcp`) for native IDE integration
- [ ] `rememb sync` — optional encrypted remote backup
- [ ] `rememb export` — export to Markdown, Obsidian, Notion
- [ ] VS Code / Windsurf extension

---

## Contributing

```bash
git clone https://github.com/yourusername/rememb
cd rememb
pip install -e ".[dev]"
```

PRs welcome. Issues welcome. Stars welcome. 🌟

---

## License

MIT
