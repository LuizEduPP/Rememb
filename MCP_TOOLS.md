# MCP Tools

This file documents the current public MCP tools exposed by src/rememb/mcp_server.py.

## Recommended agent rules

No extra rules are required to make rememb work. If you want the workstream-first flow to be used consistently, use the same strict rules block documented in the README:

```text
When using rememb, always use the workstream-first flow. Do not fall back to broad entry-first usage when a workstream flow is available.

Critical override: if a workstream flow is available, do not skip it or replace it with broad entry-first reads.

1. At the start of a session, if a workstream is already known, call rememb_workstream_resume before any broad rememb_read, rememb_read_page, or rememb_search.
2. If the workstream is not known yet, first inspect available workstreams with rememb_workstream_list. If no suitable workstream exists, create one with rememb_workstream_open and immediately start an execution anchor with rememb_execution_start.
3. When you need the factual aggregated state of a workstream, use rememb_workstream_state_get exclusively. When you need the operational continuation context, use rememb_workstream_resume.
4. Persist meaningful progress with rememb_workstream_state_update. Use rememb_write only for genuinely standalone entries that do not belong to an active workstream or execution lifecycle.
5. End or pause an execution anchor with rememb_execution_close or rememb_handoff_write_structured. Use rememb_handoff_generate only when you want a simpler handoff entry rather than the full structured handoff flow.
6. When a handoff already exists, inspect it with rememb_handoff_read_structured, rememb_handoff_restore_context, or rememb_handoff_list before falling back to broader reads.
7. Use rememb_edit to update an existing fact instead of creating duplicates with rememb_write. Use rememb_delete for targeted soft deletion, rememb_restore to recover a deleted entry or prior version, rememb_versions to inspect revision history, and rememb_diff to compare revisions.
8. Use rememb_read, rememb_read_page, or rememb_search only when the workstream is unknown, when broader context is explicitly required, or when you are intentionally inspecting raw entries outside the workstream flow.
9. Use rememb_stats to inspect store size and section totals, and rememb_consolidate when you are intentionally cleaning duplicate memory rather than adding new workstream progress.
10. Treat rememb_init as compatibility or recovery only. Do not use it as a normal step in the session flow when rememb is already running in MCP mode.
11. Use rememb_list_skills and rememb_use_skill only when you need bundled rememb skill instructions. Do not substitute them for core memory, workstream, execution, handoff, versioning, or recovery tools.
12. Before executing any memory-related tool, perform a silent internal check: does this action strictly follow the workstream-first flow? If not, pivot to the correct rememb tool first.
13. When you want to close an execution anchor and persist the next-goal handoff in one step, use rememb_execution_close_and_handoff instead of manually chaining separate close and handoff calls.
14. When you need a compact anti-context-switch restore package without writing a new handoff entry, use rememb_handoff_package.
15. When you need the review backlog, use rememb_review_queue.
16. When you need the review context for one execution anchor, use rememb_review_execution_get. When you need the review context for a full workstream, use rememb_review_workstream_get.
17. When you need the operational queue of workstreams, use rememb_workstream_queue.
18. When you need to compare two execution anchors in the same workstream, use rememb_compare_executions. When you need to compare two workstreams, use rememb_compare_workstreams.
19. When you need to record a review decision, use rememb_review_update.
20. When you intentionally need raw entry inspection outside the workstream flow, use rememb_read, rememb_read_page, or rememb_search.
21. When you intentionally need direct low-level entry creation or maintenance outside the workstream flow, use rememb_write, rememb_edit, rememb_delete, or rememb_clear.
22. When you need entry history or recovery, use rememb_versions to inspect revisions, rememb_restore to recover a deleted entry or prior version, and rememb_diff to compare revisions.
23. When you need store-level maintenance, use rememb_stats to inspect totals and rememb_consolidate only for intentional duplicate cleanup.
24. Use rememb_init only for compatibility or recovery when explicit initialization is really needed.
25. When you need bundled skill instructions, use rememb_list_skills to discover them and rememb_use_skill to load one.
26. Keep the memory flow anchored in rememb from start to finish: discovery, open, state, resume, execution lifecycle, handoffs, review, comparisons, raw entry operations, recovery, maintenance, initialization, and skill lookup should all go through rememb tools rather than ad hoc prompt-only memory.
```

These rules tell the agent which public tools to prefer first. They do not remove the rest of the public rememb surface documented below.

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

Create one entry or a batch of entries. Supports operational metadata for workstream-first usage.

Key parameters:
- content
- entries
- section
- tags
- semantic_scope
- meta_schema_version
- workstream_id
- session_id
- entry_kind
- entry_role
- actor_type
- actor_id
- parent_entry_id
- supersedes_entry_id
- related_entry_ids
- structured

### rememb_edit

Update one entry or multiple entries in batch. This is non-destructive and creates a new head revision.

Key parameters:
- entry_id
- updates
- content
- section
- tags
- meta_schema_version
- workstream_id
- session_id
- entry_kind
- entry_role
- actor_type
- actor_id
- parent_entry_id
- supersedes_entry_id
- related_entry_ids
- structured

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

### rememb_init

Explicitly initialize storage. Usually optional because home-first MCP mode auto-initializes when needed.

Status:
- deprecated for normal day-to-day MCP usage
- kept intentionally for compatibility, explicit recovery, and clients that still call it directly

Key parameters:
- project_name

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

## Handoff tools

### rememb_handoff_generate

Generate and save a normal handoff entry, optionally linked to a workstream or session.

Key parameters:
- goal (required)
- summary
- current_state
- open_loops
- next_steps
- related_entries
- restore_section
- restore_query
- include_deleted
- tags
- workstream_id
- session_id

### rememb_handoff_list

List recent handoff entries.

Key parameters:
- limit
- include_deleted

### rememb_handoff_restore_context

Read a stored handoff and return its restore hints and related entries.

Key parameters:
- entry_id (required)
- include_deleted

### rememb_handoff_write_structured

Write a structured, agent-first handoff for a workstream or session while preserving the normal handoff entry format.

Key parameters:
- workstream_id (required)
- session_id
- goal (required)
- summary
- current_state
- decisions
- open_loops
- next_steps
- essential_context
- optional_context
- related_entries
- risk_flags
- restore_section
- restore_query
- include_deleted
- tags

### rememb_handoff_read_structured

Read the structured payload of a handoff by entry id or by latest handoff in a workstream.

Key parameters:
- entry_id
- workstream_id
- session_id
- include_deleted

### rememb_handoff_package

Build a minimal anti-context-switch handoff package for a workstream without writing a new entry.

Key parameters:
- workstream_id (required)
- session_id
- next_goal
- include_deleted

Returns a next_execution package with goal, compressed context tiers, restore hints, related entries and operational handoff state.

### rememb_workstream_switch_package

Build an anti-context-switch package to freeze one workstream and resume another with explicit context gap analysis.

Key parameters:
- current_workstream_id (required)
- target_workstream_id (required)
- current_execution_id
- target_execution_id
- include_deleted

Returns the current freeze package, the target resume package and a state_gap object showing what is needed now, what is optional to load and what is risky to carry.

## Workstream and execution tools

### rememb_workstream_list

List aggregated workstreams derived from existing entries.

Key parameters:
- limit
- include_deleted

### rememb_workstream_open

Create or reopen a logical workstream using a checkpoint entry.

Key parameters:
- goal (required)
- workstream_id
- summary
- tags

### rememb_workstream_state_get

Aggregate the current state of a workstream and its execution history.

Key parameters:
- workstream_id (required)
- session_id
- include_deleted

### rememb_workstream_state_update

Write a structured state checkpoint for a workstream.

Key parameters:
- workstream_id (required)
- session_id
- goal
- summary
- current_state
- decisions
- open_loops
- next_steps
- essential_context
- optional_context
- risk_flags
- related_entry_ids
- merge

### rememb_workstream_resume

Return a compact operational resume for a workstream, combining the latest relevant state and handoff.

Key parameters:
- workstream_id (required)
- session_id
- include_deleted

### rememb_execution_start

Start a new execution anchor inside a workstream.

Key parameters:
- workstream_id (required)
- goal
- summary
- execution_id
- tags

### rememb_execution_close

Close the active or selected execution anchor with a structured review entry.

Key parameters:
- workstream_id (required)
- execution_id
- outcome (required)
- status
- next_steps
- open_loops
- related_entry_ids

### rememb_execution_close_and_handoff

Close an execution anchor and persist the next-goal handoff in one operation.

Key parameters:
- workstream_id (required)
- execution_id
- outcome (required)
- next_goal (required)
- status
- summary
- open_loops
- next_steps
- essential_context
- optional_context
- archived_context
- risk_flags
- obsolete_context
- related_entry_ids
- include_deleted
- audience

### rememb_workstream_queue

List workstreams as an operational queue with explicit statuses.

Key parameters:
- status
- include_deleted
- limit

## Review and comparison tools

### rememb_review_queue

List entries that require review with diff context when available.

Key parameters:
- workstream_id
- session_id
- actor_type
- actor_id
- entry_kind
- review_status
- include_deleted
- pending_only
- limit

### rememb_review_execution_get

Aggregate review context for one execution anchor inside a workstream.

Key parameters:
- workstream_id (required)
- execution_id (required)
- include_deleted

### rememb_review_workstream_get

Aggregate review context for a workstream across its execution history.

Key parameters:
- workstream_id (required)
- include_deleted

### rememb_compare_executions

Compare two execution anchors inside the same workstream.

Key parameters:
- workstream_id (required)
- base_execution_id (required)
- target_execution_id (required)
- include_deleted

### rememb_compare_workstreams

Compare the operational state of two workstreams.

Key parameters:
- left_workstream_id (required)
- right_workstream_id (required)
- include_deleted

### rememb_review_update

Update the review status for a single entry.

Key parameters:
- entry_id (required)
- review_status (required)
- review_notes
- review_reason
- validation_notes
- source_context_entry_ids

## Skill tools

### rememb_list_skills

List bundled rememb skills.

### rememb_use_skill

Load one bundled rememb skill by identifier or exact declared name.

Key parameters:
- skill (required)