<!-- mcp-name: io.github.LuizEduPP/rememb -->
![rememb cover](https://raw.githubusercontent.com/LuizEduPP/Rememb/main/assets/cover.png)

[![Rememb MCP server](https://glama.ai/mcp/servers/LuizEduPP/Rememb/badges/score.svg)](https://glama.ai/mcp/servers/LuizEduPP/Rememb)
[![MCP Badge](https://lobehub.com/badge/mcp/luizedupp-rememb)](https://lobehub.com/mcp/luizedupp-rememb)

Operate AI agents without losing context, focus, or control. `rememb` is a local-first anti-context-switch layer: workstreams, goal-based handoffs, agent supervision, restore and audit trail across execution cycles.

![rememb chat demo](https://raw.githubusercontent.com/LuizEduPP/Rememb/main/assets/rememb-chat.gif)
---

## The problem

Teams using agents at real velocity rarely fail because they lack generation. They fail because operating agents every day creates context debt:

- too much context switching between workstreams
- too much review overhead after agent output
- too little continuity between execution cycles
- too little audit trail for why something changed

Every team or solo developer operating agents professionally hits this wall:

```
Session 1: "We're using PostgreSQL, auth at src/auth/, prefer async patterns."
Session 2: Agent starts from zero. You explain everything again.
Session 3: Same thing.
```

Existing solutions often center on hosted memory layers, API keys, or opaque context pipelines.
What you actually need is to **resume the next execution with the minimum correct context and a trail you can inspect**.

`rememb` is built around four operating problems:

- goal-based handoff instead of generic session summary
- anti-context-switch workstream switching instead of raw recall
- memory for agent supervision, not just memory for facts
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

The agent now automatically restores operational context at session start, writes durable state when something changes, and searches only when broader recall is actually needed.

If you want the new workstream-first flow to be followed consistently, add a strict rememb-specific instruction block in your IDE custom instructions or in the MCP client prompt that wraps the agent. The point is not to add generic workflow rules; the point is to make the agent route continuity, review, handoff and recovery through rememb every time.

You can place that block in either of these places:

- IDE-level custom instructions
- the system prompt or instruction field of the MCP client that is calling rememb

In both cases, keep the scope explicit: these rules are about how the agent should use rememb, not about replacing the rest of your coding instructions.

For the exact copy-paste block, use the canonical rules section in [MCP_TOOLS.md](MCP_TOOLS.md#recommended-agent-rules).

That is enough for the new flow. You do not need extra storage setup, extra server config, or a custom schema migration.

The `rememb_init` MCP tool is optional/deprecated for day-to-day usage: in MCP mode, rememb resolves storage home-first and auto-initializes `~/.rememb` when needed. The tool remains available for compatibility and explicit recovery workflows.

For the current public MCP tool list and descriptions, see [MCP_TOOLS.md](MCP_TOOLS.md).

If you want multiple MCP clients on the same machine to reuse one already-running rememb process, start a persistent local SSE transport:

```bash
rememb mcp --transport sse --host 127.0.0.1 --port 8765
```

This keeps one MCP process alive, so repeated clients can hit the same loaded embedding model through `http://127.0.0.1:8765/sse` and `http://127.0.0.1:8765/messages/`.

Do not put `--transport sse` inside a stdio MCP client config. `stdio` clients expect JSON-RPC on stdin/stdout; the SSE mode exposes an HTTP endpoint and must be started separately.

### Local usage without MCP

```bash
rememb                    # Open the web UI (http://localhost:8080)
rememb --port 9000        # Custom port
rememb fetch-model        # Download the local embedding model for semantic search
```

---

## How it works

```
.rememb/
  entries.json   ← structured memory (project, actions, systems, user, context)
  meta.json      ← project metadata
  config.json    ← limits, sections, web UI behavior, semantic model settings
```

A local JSON-backed store in your project. Your agent can resume workstreams, freeze one thread and resume another, inspect prior decisions, and hand off the next execution without depending on a cloud memory service.

```
User: "We're using PostgreSQL, auth at src/auth/, async patterns"
Agent: [rememb_write] → Saved

[New session]
Agent: [rememb_read]  → Context loaded
Agent: "I see you're using PostgreSQL with auth at src/auth/..."
```
These map to rememb_write, rememb_edit, and rememb_delete respectively. For the current public MCP tool list and descriptions, see [MCP_TOOLS.md](MCP_TOOLS.md).

Search uses local semantic embeddings (no API, no cloud). The embedding model is unloaded after a short idle window by default, so the process does not keep the full model resident forever.

rememb now writes the full configuration set to .rememb/config.json during initialization, so all supported knobs live in one place:

```json
{
  "max_content_length": 1000000,
  "max_tag_length": 500,
  "max_tags_per_entry": 100,
  "max_entries": 100000,
  "sections": ["project", "actions", "systems", "requests", "user", "context"],
  "section_colors": {
    "project": "#d84848",
    "actions": "#d08020"
  },
  "entry_batch_size": 24,
  "entry_load_threshold": 6,
  "semantic_model_idle_ttl_seconds": 15,
  "semantic_model_name": "paraphrase-multilingual-MiniLM-L12-v2",
  "semantic_conflict_threshold": 0.88
}
```

Set semantic_model_idle_ttl_seconds to 0 to unload the model immediately after each semantic operation. If you want a smaller model, you can switch semantic_model_name to another SentenceTransformers model such as intfloat/multilingual-e5-small or all-MiniLM-L6-v2.

entry_batch_size and entry_load_threshold control pagination in the web UI — how many cards load at once and when to trigger "load more".

Section names are normalized to lowercase, duplicates are ignored after normalization, and removing a section with existing entries automatically migrates those entries to `uncategorized`. `meta.json` is kept in sync with the current effective section list.

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

## Web UI

`rememb` includes a local web interface for an agent-driven operating loop.

```bash
rememb                       # Open the web UI (http://localhost:8080)
rememb --host 0.0.0.0        # Bind to all interfaces
rememb --port 9000           # Custom port
rememb --no-browser          # Start server without opening the browser
```

![rememb web UI](https://raw.githubusercontent.com/LuizEduPP/Rememb/main/assets/web-ui.png)

The screenshot above shows the actual local web UI running with demo data.

![rememb stats view](https://raw.githubusercontent.com/LuizEduPP/Rememb/main/assets/web-ui-stats.png)

Stats view with totals, section breakdown, date range, and recent entries.

![rememb settings view](https://raw.githubusercontent.com/LuizEduPP/Rememb/main/assets/web-ui-settings.png)

Settings view with limits, semantic search controls, section colors, and maintenance actions.

![rememb skills view](https://raw.githubusercontent.com/LuizEduPP/Rememb/main/assets/web-ui-skills.png)

Skills view listing all bundled skills available in the installed rememb package.

Features:
- **Agent-driven dashboard** — dashboard, workstreams, handoffs and review stay centered on continuity, escalation and audit trail
- **Goal-based handoff** — the next execution package carries goal, essential context, optional context, risky context and restore hints
- **Anti-context-switch switching** — compare the current thread against the target thread and expose what must load now versus what is risky to carry
- **Agent review surface** — inspect risk, confidence, priority, rationale, provenance and resulting validation state in one place
- **Execution snapshots** — each execution can expose inputs, context used, outputs produced and resulting review state
- **Workstream-first view** — inspect the selected workstream in a persistent detail panel with current state, next execution package, switch package, review and timeline
- **Structured handoffs** — write and inspect handoffs linked to workstreams and executions, then restore context from Web or MCP
- **Runtime control surface** — stats, settings and raw memory maintenance remain available as system controls without becoming the primary operating loop
- **Settings page** — edit limits, semantic search options, section colors and maintenance actions
- **Skills page** — browse all bundled skills available in the installed rememb package

The semantic search MCP tool also accepts an optional exact `tag` filter, so IDE clients can restrict semantic matches before ranking.

---

## CLI

```bash
rememb                                                      # Open the web UI (http://localhost:8080)
rememb --host 0.0.0.0 --port 8080 --no-browser             # Custom bind, no auto-open
rememb mcp                                                  # Start MCP server over stdio
rememb mcp --transport sse --host 127.0.0.1 --port 8765    # One persistent local MCP process
rememb fetch-model                                          # Download the local embedding model
rememb --version, -v                                        # Show version
rememb --help, -h                                           # Show help
```

---

## Compatibility

The current compatibility surface is tracked explicitly in [COMPATIBILITY.md](COMPATIBILITY.md).

Short version:

- Python 3.10 to 3.12 are covered by CI
- CLI contract and MCP tool schema have automated test coverage
- stdio MCP is the primary documented integration path
- SSE MCP is documented, but not yet covered by end-to-end automated client tests
- release automation and Trusted Publishing are documented in [RELEASE.md](RELEASE.md)

---

## Design

- **Local first** — plain JSON file in your project
- **Portable** — copy `.rememb/` anywhere, it works
- **Agnostic** — any agent, any IDE (MCP or CLI)
- **No lock-in** — no servers, no API keys, no accounts

### Current feature direction: Anti-fatigue agent operations

`rememb` remains the product.
The current feature direction is workstream-first memory with structured execution handoff.

This feature slice is meant to solve one concrete problem:
reduce the operational fatigue of running agents by keeping continuity, supervision and audit trail grouped under one logical workstream.

The intended shape is deliberately small and compatible with the current architecture:

- keep entries as the storage unit and add workstream and execution as logical metadata
- store handoffs as normal entries instead of creating a new storage system
- use stable markdown sections so handoffs stay human-readable and auditable
- tag handoffs consistently so they are easy to search and filter
- expose workstream open, state update, resume, execution lifecycle, switch package and structured handoff through the existing store, Web UI, and MCP surfaces
- restore context from a handoff through related entries, revisions, and search hints
- keep settings, maintenance and stats available as runtime controls without framing the product as a human-operated workflow

The current implementation already covers:

- opening and listing workstreams
- starting and closing sessions
- writing workstream state checkpoints
- generating and reading structured handoffs
- resuming a workstream from the latest relevant state and handoff
- browsing the same flow in the Web UI

This keeps the feature aligned with rememb's core constraints:

- local-first JSON storage
- no external services
- additive MCP and Web changes
- compatibility with the existing `.rememb` layout

Why this direction matters now:

- AI adoption is high, but trust and enthusiasm are not rising at the same pace
- teams are feeling more review overhead, more supervision work, and more cognitive load
- context switching across parallel workstreams is still expensive
- session handoff and context resumption are still poorly solved end to end
- auditability is becoming a real product need, not a nice-to-have

The strongest product opportunity for rememb is not more text generation.
It is reducing the operational fatigue of working with agents.

That points rememb toward four concrete strengths:

- goal-oriented handoff between sessions
- workstream resumption with minimal relevant context
- supervision and review of agent output, not just fact recall
- local-first audit trail with versions, diffs, restore, and history

The near-term product adjustments follow directly from that:

- explicit handoff flows such as ending a session, opening the next one, and generating a handoff for a specific goal
- stronger workstream views around task, session, and resumption instead of isolated entries only
- review-oriented inspection for agent changes, with before/after and related decision context
- smarter context compression, separating essential context from optional or risky carry-over
- distinct output modes for human handoff and agent handoff

In product terms, the less obvious but stronger bet is this:
help small teams reduce the fatigue of operating agents across real work.

That means rememb should keep pushing on the package formed by:

- handoff
- resumption
- compression
- diff
- audit trail
- restore
- goal-focused context

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
