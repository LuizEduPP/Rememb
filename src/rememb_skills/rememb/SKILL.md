---
name: rememb
description: Persist facts, decisions, and handoffs in local rememb memory so the next session starts with context. Use when something must survive this chat, when search/get/write/edit is needed, or when handing off across IDEs.
---

# Rememb

Use rememb when the next session needs this: a fact, a decision, a handoff, or an open failure. One local store. Any IDE.

This skill does not replace the bundled operational skills. Those cover coding workflows. rememb covers durable memory.

## Search then get

`rememb_search` is an index. It returns id, score, tags, date, and a short excerpt.

Call `rememb_get` (or `rememb_read`) for the full body of the ids you picked.

## Write vs edit

- `rememb_write` for a new fact, decision, or context
- `rememb_edit` to update an existing id
- Do not duplicate the same content in the same section

## Session start and stop

SessionStart already injects recent entries, tags, and a short stats block. Use `rememb_recent` / `rememb_stats` only when that block is not enough.

Stop already wrote where we stopped / what failed / what is open, tagged `handoff`. You do not need to brief the next agent.

## Handoff

One `~/.rememb`, or the project `.rememb` when the cwd has a store. Any host that can run `rememb` reads the same files. No claim, no owner, no extra server.
