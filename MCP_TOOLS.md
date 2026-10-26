# MCP Tools

This file documents the **18 public MCP tools** exposed by `src/rememb/mcp_server.py`.

## Multi-store

The MCP process always includes the **global** store (`~/.rememb`). Extra project stores can be added with repeatable CLI args:

```bash
rememb mcp --project /path/to/project-a --project /path/to/project-b
```

Memory tools accept optional `store` (default `global`) except `rememb_list_stores`, `rememb_list_skills`, and `rememb_use_skill`. Project store ids are derived from the project directory name. Use `rememb_list_stores` to list ids and paths.

## Host door

`rememb install --apply` writes the MCP block, the Memory Rules below, and SessionStart / PostToolUse / Stop hooks when the host has them (Cursor and Claude). Other hosts get MCP and rules only. `--project` writes into the current directory. See the README CLI section.

## Recommended agent rules

`rememb install` writes this block from `src/rememb/agent_rules.py`. Paste the same text by hand if you skip the installer. The goal is to route reads, writes, search, recovery, and maintenance through rememb instead of ad hoc prompt memory:

```text
# Rememb Memory Rules

Use rememb as the authoritative local memory layer for this project.

SessionStart already injects recent entries, tags, and a short stats block. Call rememb_recent, rememb_list_tags, or rememb_stats only when that block is not enough.

## Targeted Reads

* Use `rememb_get` when you already know an entry ID from search or the injected block.
* Use `rememb_list_stores` when multiple `--project` stores are configured; pass `store` on memory tools (`global` by default).
* Use `rememb_read` for broad section loads or when you need full entry content.
* Use `rememb_read_page` when browsing large stores without flooding the context window.

## Read vs Search

* `rememb_search` is an index: id, score, tags, date, and a short excerpt.
* Use `rememb_get` or `rememb_read` for the full body of the ids you picked.
* Apply your own semantic relevance judgment after keyword search.

## Write vs Edit

* Use `rememb_write` for new facts, decisions, or context.
* Use `rememb_edit` to update existing entries instead of duplicating memory with new writes.
* Review near-duplicates yourself with `rememb_search` / `rememb_read`; rememb only blocks exact duplicate content in the same section.

## Recovery & Versioning

* Use `rememb_versions`, `rememb_diff`, and `rememb_restore` for history inspection, comparison, and recovery.
* Use `rememb_delete` for targeted soft deletion.

## Maintenance

* Use `rememb_stats` for store inspection when the injected block is not enough.
* Use `rememb_consolidate` only for intentional literal duplicate cleanup (exact content match).
* Use `rememb_clear` only when the user explicitly requests a full reset.

## Skills

* Use `rememb_list_skills` and `rememb_use_skill` when bundled rememb operational instructions are needed.
* Do not substitute skills for core memory read/write/search behavior.

## Handoff

One `~/.rememb` (or the project `.rememb`). Any IDE. Stop already wrote where we stopped / what failed / what is open. SessionStart already injected it.

## Critical Behavioral Rules

Before any rememb tool call, ask: "Should this be a search, a targeted read, or a write/edit?"

Never invent parallel memory systems outside rememb when an official rememb tool exists.

Treat the full rememb MCP surface as authoritative and always available.
```

This is the same text `rememb install` writes. The tools below are the public surface those rules treat as available.

## Core memory tools

### rememb_list_stores

List configured stores for this MCP process (global plus any `--project` stores). Safe and read-only.

### rememb_get

Fetch one entry by ID with full content. Safe and read-only.

Key parameters:
- entry_id (required)
- include_deleted
- max_chars

### rememb_recent

Recently updated entries, newest first. Safe and read-only.

Key parameters:
- limit
- section
- include_deleted
- max_chars

### rememb_list_tags

Tag inventory with usage counts. Safe and read-only.

Key parameters:
- limit
- include_deleted

### rememb_read

Read all entries or filter by section. Safe and read-only.

Key parameters:
- section
- include_deleted
- max_chars (optional mechanical cap)

### rememb_read_page

Read a paginated slice of entries with optional section or tag filtering. Safe and read-only. Returns full content; agent summarizes semantically.

Key parameters:
- section
- tag
- include_deleted
- offset
- limit
- sort_by
- descending
- max_chars (optional mechanical cap)

### rememb_search

Keyword and token search over entries with optional section or tag filtering. Safe and read-only. Search is an index: it returns id, score, tags, date, and a short excerpt. Use `rememb_get` / `rememb_read` / `rememb_read_page` for the full body.

Key parameters:
- query (required)
- section
- tag
- include_deleted
- top_k
- max_chars (default `search_excerpt_chars` / 160; `0` returns the full body)

### rememb_write

Create one entry or a batch of entries. Existing entries are never overwritten.

Key parameters:
- content
- entries
- section
- tags

### rememb_edit

Update one entry or multiple entries in batch. Non-destructive: creates a new head revision.

Key parameters:
- entry_id
- updates
- content
- section
- tags

### rememb_delete

Soft-delete one entry or multiple entries. Deleted entries are hidden by default and can be restored later.

Key parameters:
- entry_id
- entry_ids

### rememb_clear

Delete all entries after explicit confirmation.

Key parameters:
- confirm (required)

### rememb_stats

Return totals, size, oldest/newest timestamps, and count by section.

### rememb_consolidate

Consolidate literal duplicate entries in exact mode.

Key parameters:
- section

## Versioning and recovery tools

### rememb_versions

List revisions for a single entry.

Key parameters:
- entry_id (required)
- include_deleted

### rememb_restore

Restore a soft-deleted entry or restore a specific previous version as the new head.

Key parameters:
- entry_id (required)
- version

### rememb_diff

Show a unified diff between two revisions of the same entry.

Key parameters:
- entry_id (required)
- from_version (required)
- to_version (required)

## Skill tools

### rememb_list_skills

List bundled rememb skills.

### rememb_use_skill

Load one bundled rememb skill by identifier or exact declared name.

Key parameters:
- skill (required)
