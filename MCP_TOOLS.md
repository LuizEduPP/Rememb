# MCP Tools

This file documents the current public MCP tools exposed by src/rememb/mcp_server.py.

## Recommended agent rules

If you want rememb to run as a strictly agent-driven system, use this exact rules block in your IDE instructions or MCP wrapper prompt. The goal is to force the agent to route continuity, handoff, review, recovery and audit through rememb instead of falling back to ad hoc memory behavior:

```text
# Rememb Operating Rules

Always use a workstream-first, execution-anchored Rememb flow.

Never replace Rememb continuity with:

* ad hoc prompt memory
* manual summaries
* broad entry-first reads
* external continuity systems
  when an appropriate Rememb workstream flow exists.

## Core Routing Priority

Follow this order strictly:

1. Workstream
2. Execution
3. Handoff
4. State
5. Raw memory entries

Do not skip upward in the hierarchy.

---

# Primary Flow

## 1. Known Workstream

If the workstream is already known:

* call `rememb_workstream_resume`
* do this BEFORE any:

  * `rememb_read`
  * `rememb_read_page`
  * `rememb_search`

## 2. Unknown Workstream

If the workstream is not known:

1. call `rememb_workstream_list`
2. select an existing workstream if suitable
3. otherwise:

   * call `rememb_workstream_open`
   * immediately call `rememb_execution_start`

---

# Context Retrieval Rules

## Operational Continuation

Use:

* `rememb_workstream_resume`

for:

* active execution continuity
* next actions
* execution recovery
* continuation context

## Aggregated Factual State

Use:

* `rememb_workstream_state_get`

for:

* canonical workstream facts
* consolidated project state
* durable structured state

Do not use broad reads when workstream state is sufficient.

---

# Persistence Rules

## Preferred Persistence

Persist meaningful progress with:

* `rememb_workstream_state_update`

## Raw Entry Writes

Use:

* `rememb_write`

ONLY when the information:

* is standalone
* is not tied to an execution lifecycle
* does not belong to an active workstream

## Editing Existing Facts

Prefer:

* `rememb_edit`

instead of duplicating memory with new writes.

---

# Execution Lifecycle

## Start

Use:

* `rememb_execution_start`

when beginning active work.

## Pause / End

Use:

* `rememb_execution_close`
* `rememb_handoff_write_structured`

or preferably:

* `rememb_execution_close_and_handoff`

when both actions are needed.

---

# Handoff Rules

If a handoff exists:

* inspect it first with:

  * `rememb_handoff_read_structured`

before broader reads.

For compact execution restore packages without creating a new handoff:

* use `rememb_handoff_package`

For workstream switching:

* use `rememb_workstream_switch_package`

---

# Raw Memory Access

Use:

* `rememb_read`
* `rememb_read_page`
* `rememb_search`

ONLY when:

* the workstream is unknown
* broad inspection is explicitly required
* raw entries are intentionally being inspected

Do not use raw reads as the default continuity mechanism.

---

# Recovery & Versioning

Use:

* `rememb_versions`
* `rememb_restore`
* `rememb_diff`

for:

* history inspection
* recovery
* revision comparison

Use:

* `rememb_delete`

for targeted soft deletion.

---

# Review & Comparison

## Review Queue

Use:

* `rememb_review_queue`

## Execution Review Context

Use:

* `rememb_review_execution_get`

## Workstream Review Context

Use:

* `rememb_review_workstream_get`

## Comparisons

Use:

* `rememb_compare_executions`
* `rememb_compare_workstreams`

## Recording Review Decisions

Use:

* `rememb_review_update`

---

# Maintenance

Use:

* `rememb_stats`

for store inspection.

Use:

* `rememb_consolidate`

ONLY for intentional duplicate cleanup.

Do not consolidate during normal execution flow.

---

# Skills

Use:

* `rememb_list_skills`
* `rememb_use_skill`

ONLY when bundled Rememb operational instructions are needed.

Do not substitute skills for core workstream flow.

---

# Critical Behavioral Rules

Before any Rememb tool call, perform an internal check:

"Am I following the workstream-first hierarchy?"

If not:

* pivot to the correct workstream or execution tool first.

Never invent manual supervision, routing, continuity, escalation, review, or handoff systems outside Rememb when an official Rememb tool exists.

Treat the full Rememb MCP surface as authoritative and always available.

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