"""Canonical Rememb Memory Rules written by `rememb install`."""

from __future__ import annotations

RULES_BEGIN = "<!-- rememb-rules -->"
RULES_END = "<!-- /rememb-rules -->"

AGENT_RULES = """# Rememb Memory Rules

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
"""


def marked_rules(body: str = AGENT_RULES) -> str:
    return f"{RULES_BEGIN}\n{body.strip()}\n{RULES_END}\n"
