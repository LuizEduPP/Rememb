<!-- mcp-name: io.github.LuizEduPP/rememb -->
![rememb cover](http://raw.githubusercontent.com/LuizEduPP/Rememb/refs/heads/main/assets/cover.png)

[![Rememb MCP server](https://glama.ai/mcp/servers/LuizEduPP/Rememb/badges/score.svg)](https://glama.ai/mcp/servers/LuizEduPP/Rememb)
[![MCP Badge](https://lobehub.com/badge/mcp/luizedupp-rememb)](https://lobehub.com/mcp/luizedupp-rememb)

Operate AI agents without losing context between sessions. `rememb` is a local-first persistent memory layer: structured entries, keyword search, versioning, diff, restore, and audit trail — no cloud service required.

![rememb chat demo](http://raw.githubusercontent.com/LuizEduPP/Rememb/refs/heads/main/assets/rememb-chat.gif)
---

## The problem

Teams using agents at real velocity rarely fail because they lack generation. They fail because operating agents every day creates context debt:

- too much re-explaining project facts every session
- too little durable memory outside the chat window
- too little audit trail for why something changed
- too much noise when recalling the right context

Every team or solo developer operating agents professionally hits this wall:

```
Session 1: "We're using PostgreSQL, auth at src/auth/, prefer async patterns."
Session 2: Agent starts from zero. You explain everything again.
Session 3: Same thing.
```

Existing solutions often center on hosted memory layers, API keys, or opaque context pipelines.
What you actually need is to **resume the next session with the minimum correct context and a trail you can inspect**.

`rememb` is built around four memory problems:

- durable facts and decisions instead of session-only chat memory
- keyword search instead of rereading everything (agents judge relevance)
- non-destructive versioning instead of silent overwrites
- local-first audit trail for AI work, not opaque cloud logs

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

The agent can read stored context at session start, write durable memory when something changes, and search only when targeted recall is needed.

If you want rememb usage to stay consistent, add a rememb-specific instruction block in your IDE custom instructions or in the MCP client prompt that wraps the agent. The point is to make the agent route reads, writes, search, recovery, and maintenance through rememb instead of ad hoc prompt memory.

You can place that block in either of these places:

- IDE-level custom instructions
- the system prompt or instruction field of the MCP client that is calling rememb

In both cases, keep the scope explicit: these rules are about how the agent should use rememb, not about replacing the rest of your coding instructions.

For the exact copy-paste block, use the canonical rules section in [MCP_TOOLS.md](MCP_TOOLS.md#recommended-agent-rules).

No extra storage setup, server config, or schema migration is required. In MCP mode, rememb resolves storage home-first and auto-initializes `~/.rememb` when needed.

For the current public MCP tool list (17 tools) and descriptions, see [MCP_TOOLS.md](MCP_TOOLS.md).

If you want multiple MCP clients on the same machine to reuse one already-running rememb process, start a persistent local SSE transport:

```bash
rememb mcp --transport sse --host 127.0.0.1 --port 8765
```

This keeps one MCP process alive, so repeated clients can connect through `http://127.0.0.1:8765/sse` and `http://127.0.0.1:8765/messages/`.

Do not put `--transport sse` inside a stdio MCP client config. `stdio` clients expect JSON-RPC on stdin/stdout; the SSE mode exposes an HTTP endpoint and must be started separately.

### Local usage without MCP

```bash
rememb                    # Open the web UI (http://localhost:18181)
rememb --port 9000        # Custom port
```

---

## How it works

```
~/.rememb/                 ← default store location (MCP and Web UI)
  entries.json             ← default JSON backend (or entries.db with SQLite)
  meta.json                ← project metadata
  config.json              ← limits, sections, storage backend, UI paging
```

A local store on disk. Your agent can read prior decisions, search by keywords and tokens, update entries without losing history, and restore previous versions without depending on a cloud memory service. Copy `~/.rememb/` anywhere to move the store.

```
User: "We're using PostgreSQL, auth at src/auth/, async patterns"
Agent: [rememb_write] → Saved

[New session]
Agent: [rememb_read]  → Context loaded
Agent: "I see you're using PostgreSQL with auth at src/auth/..."
```

These map to `rememb_write`, `rememb_edit`, and `rememb_delete`. For the full MCP surface, see [MCP_TOOLS.md](MCP_TOOLS.md).

Search uses **keyword and token matching** over entry content and tags. rememb returns full matches; the agent applies semantic relevance judgment. No API keys, no cloud, no embedding model download at runtime.

`config.json` is written during initialization with all supported knobs:

```json
{
  "max_content_length": 1000000,
  "max_tag_length": 500,
  "max_tags_per_entry": 100,
  "max_entries": 100000,
  "sections": ["project", "actions", "systems", "requests", "user", "context"],
  "section_colors": {
    "project": "#d84848",
    "actions": "#d08020",
    "systems": "#d4c430",
    "requests": "#40c040",
    "user": "#20d4c4",
    "context": "#c060f0"
  },
  "entry_batch_size": 24,
  "entry_load_threshold": 6,
  "storage_backend": "json"
}
```

Set `storage_backend` to `sqlite` for larger stores. The Web UI and MCP migrate existing JSON entries automatically when you switch backends.

`entry_batch_size` and `entry_load_threshold` control pagination in the web UI — how many cards load at once and when to trigger "load more".

Section names are normalized to lowercase, duplicates are ignored after normalization, and removing a section with existing entries automatically migrates those entries to `uncategorized`. `meta.json` is kept in sync with the current effective section list.

Older stores may still contain legacy embedding-related config keys; they are dropped the next time configuration is loaded or saved.

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

## Web UI

`rememb` includes a local web interface for **supervision** — browse memory, inspect history, and tune runtime settings. Entry writes and edits go through MCP; the Web UI does not expose create/edit/delete controls for entries.

```bash
rememb                       # Open the web UI (http://localhost:18181)
rememb --host 0.0.0.0        # Bind to all interfaces
rememb --port 9000           # Custom port
rememb --no-browser          # Start server without opening the browser
```

![rememb web UI](http://raw.githubusercontent.com/LuizEduPP/Rememb/refs/heads/main/assets/web-ui.png)

Overview with entry totals and recent memory activity.

![rememb stats view](http://raw.githubusercontent.com/LuizEduPP/Rememb/refs/heads/main/assets/web-ui-stats.png)

Stats with totals, section breakdown, date range, and recent entries.

![rememb settings view](http://raw.githubusercontent.com/LuizEduPP/Rememb/refs/heads/main/assets/web-ui-settings.png)

Settings for limits, storage backend, section colors, and maintenance actions.

![rememb skills view](http://raw.githubusercontent.com/LuizEduPP/Rememb/refs/heads/main/assets/web-ui-skills.png)

Skills browser for bundled agent skills included with rememb.

Views:

- **Overview** — entry totals, deleted count, store size, and recent memory
- **Memory** — browse, keyword search, filter by section, sort, and include deleted entries
- **Stats** — totals, backend, section bars, oldest/newest timestamps, and recent entries
- **Settings** — edit limits, storage backend, section colors, consolidate duplicates, and save runtime config
- **Skills** — browse bundled agent skills (60 skills shipped in the package)

Entry inspection from the UI includes version history and side-by-side diff. Restore is available through MCP (`rememb_restore`); the Web UI is read-only for entry mutations.

`rememb_search` accepts an optional exact `tag` filter, so IDE clients can restrict keyword matches before ranking.

---

## CLI

```bash
rememb                                                      # Open the web UI (http://localhost:18181)
rememb --host 0.0.0.0 --port 18181 --no-browser            # Custom bind, no auto-open
rememb mcp                                                  # Start MCP server over stdio
rememb mcp --transport sse --host 127.0.0.1 --port 8765    # One persistent local MCP process
rememb --version, -v                                        # Show version
rememb --help, -h                                           # Show help
```

---

## Compatibility

The current compatibility surface is tracked explicitly in [COMPATIBILITY.md](COMPATIBILITY.md).

Short version:

- Python 3.10 to 3.12 are covered by CI
- CLI contract and MCP tool schema (17 tools) have automated test coverage
- stdio MCP is the primary documented integration path
- SSE MCP is documented and partially tested at the route level
- release automation and Trusted Publishing are documented in [RELEASE.md](RELEASE.md)

---

## Design

- **Local first** — plain JSON or SQLite on disk
- **Portable** — copy `~/.rememb/` anywhere, it works
- **Agnostic** — any agent, any IDE (MCP or CLI)
- **No lock-in** — no servers, no API keys, no accounts

Core capabilities:

- structured memory with sections and tags
- keyword search with agent-side relevance judgment
- non-destructive versioning, diff, restore, and soft delete
- duplicate consolidation (exact content) and store stats
- config and maintenance via Web UI (settings only; entry writes via MCP)
- 60 bundled agent skills via Web UI and MCP

---

## Contributing

```bash
git clone https://github.com/LuizEduPP/Rememb
cd Rememb
pip install -e ".[dev]"
```

PRs welcome. Issues welcome. Stars welcome. 🌟

---

## License

MIT
