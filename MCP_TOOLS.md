# MCP Tools

This file documents the current public MCP tools exposed by `src/rememb/mcp_server.py`.

## Recommended agent rules

If you want rememb to run as a strictly agent-driven memory layer, use this rules block in your IDE instructions or MCP wrapper prompt. The goal is to route reads, writes, search, recovery, and maintenance through rememb instead of ad hoc prompt memory:

```text
# Rememb Memory Rules

Use rememb as the authoritative local memory layer for this project.

## Read vs Search

* Use `rememb_search` when looking for specific information by topic or keyword.
* Use `rememb_read` for broad section loads or when you need full entry content.
* Use `rememb_read_page` when browsing large stores without flooding the context window.

## Write vs Edit

* Use `rememb_write` for new facts, decisions, or context.
* Use `rememb_edit` to update existing entries instead of duplicating memory with new writes.

## Recovery & Versioning

* Use `rememb_versions`, `rememb_diff`, and `rememb_restore` for history inspection, comparison, and recovery.
* Use `rememb_delete` for targeted soft deletion.

## Maintenance

* Use `rememb_stats` for store inspection.
* Use `rememb_consolidate` only for intentional duplicate cleanup.
* Use `rememb_clear` only when the user explicitly requests a full reset.

## Skills

* Use `rememb_list_skills` and `rememb_use_skill` when bundled rememb operational instructions are needed.
* Do not substitute skills for core memory read/write/search behavior.

## Critical Behavioral Rules

Before any rememb tool call, ask: "Should this be a search, a targeted read, or a write/edit?"

Never invent parallel memory systems outside rememb when an official rememb tool exists.

Treat the full rememb MCP surface as authoritative and always available.
```

These rules are the canonical agent-driven routing contract. The documented tools below are the same public surface the agent rules must treat as available.

## Core memory tools

### rememb_read

Read all entries or filter by section. Safe and read-only.

Key parameters:
- section
- include_deleted
- summary_only
- max_chars

### rememb_read_page

Read a paginated slice of entries with optional section or tag filtering. Safe and read-only.

Key parameters:
- section
- tag
- include_deleted
- offset
- limit
- sort_by
- descending
- summary_only
- max_chars

### rememb_search

Semantic search over entries with optional section or tag filtering. Safe and read-only.

Key parameters:
- query (required)
- section
- tag
- include_deleted
- top_k
- summary_only
- max_chars

### rememb_write

Create one entry or a batch of entries. Existing entries are never overwritten.

Key parameters:
- content
- entries
- section
- tags
- semantic_scope

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

Consolidate duplicate entries in exact or semantic mode.

Key parameters:
- section
- mode
- similarity_threshold

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
