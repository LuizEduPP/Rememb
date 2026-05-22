---
name: skill-lookup
description:
  Search, retrieve, and install Agent Skills from a registry using MCP tools.
  Use when the user asks to find skills, browse skill catalogs, install a skill for an AI assistant,
  or extend AI capabilities with reusable AI agent components.
license: MIT
---

# Skill Lookup

## Overview

Use this skill to search a skill registry, inspect candidate skills, and install selected skills into a concrete `<skill-root>` without assuming a specific assistant or editor.

## When to Use

Use this skill when the user wants to:

- find an existing skill before building one
- browse a registry by topic, category, or tag
- inspect the files included in a skill
- install a skill into a local or project skill directory

## Core Workflow

1. Search the registry with `search_skills` using the user's task, domain, and likely triggers.
2. Present concise results with title, description, author, and file summary.
3. If the user selects a candidate, fetch the full package with `get_skill`.
4. Ask for or infer the target `<skill-root>` for installation.
5. Save `SKILL.md` and any companion files under `<skill-root>/{slug}/`.
6. Verify that the saved `SKILL.md` is present and that the frontmatter is intact.
7. Explain what the installed skill does and when it should activate.

## Available Tools

- `search_skills`: Search for skills by keyword, category, or tag
- `get_skill`: Retrieve one skill with all files and metadata

## Inputs / Assumptions

- `query` should reflect the user's actual problem, not just a generic domain label
- `limit` should stay small enough to review meaningfully
- `category` and `tag` filters are optional refinements, not mandatory inputs
- Installation should use a real `<skill-root>` chosen for the current environment

## Examples

### Example search

```text
search_skills({"query": "code review", "limit": 5, "category": "coding"})
```

### Example retrieval

```text
get_skill({"id": "abc123"})
```

### Example installation layout

```text
<skill-root>/skill-slug/
├── SKILL.md
├── reference.md
└── scripts/
```

## Optional Host Notes

- Some environments expose separate user-level and workspace-level skill roots. Treat that as a deployment choice rather than a requirement of the skill itself.
- Some environments refresh skills automatically, while others need reload, reindex, or restart before a new installation becomes visible.
- If the user explicitly asks for host-specific installation steps, provide them after the generic workflow is clear.

## Validation Checklist

- Search results were shown before proposing custom skill creation
- The selected skill was fetched with full file contents
- Files were saved under a concrete `<skill-root>/{slug}/`
- `SKILL.md` exists after installation
- The frontmatter remained intact after saving
- The user was told what the skill does and when it should activate
## Best Practices

Follow the constraints, conventions, and cautions documented below, and prefer the documented path over improvisation.

## References

Use any linked scripts, assets, reference files, and companion resources mentioned in this document.

