# rememb

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

## Quickstart

```bash
# Memory is global by default (~/.rememb/) — no init needed
# Use --local to keep memory in the current project

# Write memories
rememb write "Project uses FastAPI + PostgreSQL + async patterns" --section project
rememb write "User prefers direct answers, no filler text" --section user
rememb write "Auth module lives at src/auth/, JWT-based" --section systems --tags auth,jwt

# Read everything (for the agent)
rememb read --agent

# Filter by section
rememb read --section project

# Search semantically
rememb search "authentication"
rememb search "authentication" --agent   # agent-friendly output

# Import files into memory
rememb import ~/notes/ --section context --dry-run   # preview first
rememb import ~/notes/ --section context             # then import
rememb import ~/notes/ --recursive --section context # include subfolders

# Edit and delete entries
rememb read --section actions                       # find the ID
rememb edit a1b2c3d4 --section systems              # move to another section
rememb edit a1b2c3d4 --content "Updated text"       # update content
rememb delete a1b2c3d4                              # delete (asks confirmation)
rememb delete a1b2c3d4 --yes                        # delete without confirmation

# Get ready-to-use rules for your editor
rememb rules          # list available editors
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
rememb delete <id>       Delete a memory entry by ID (--yes to skip confirmation)
rememb edit <id>         Edit a memory entry (--content, --section, --tags)
rememb import <folder>   Import .md/.txt/.pdf files into memory (--section, --recursive, --dry-run)
rememb rules [editor]    Print agent rules for windsurf/cursor/claude/continue/vscode
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

### Planned
- [ ] MCP server (`rememb mcp`) — native IDE integration, no CLI required
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
