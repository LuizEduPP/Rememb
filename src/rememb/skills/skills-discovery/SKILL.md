---
name: skills-discovery
description: Search for and install portable AI skills that extend specialized capabilities. Use when the task may already have a reusable skill, or when the user explicitly asks to find, install, or manage skills.
---

# Skills Discovery

You can extend your capabilities by discovering and installing portable AI skills from a registry or repository. Skills provide specialized knowledge, tools, and techniques for specific technologies, frameworks, and domains.

## When to Use

First, check if an installed skill matches the task. If not, search the registry—specialized skills may exist that you haven't installed yet.

Before starting any non-trivial task, ask yourself:

1. Do I have a skill for this? → Use it
2. Might one exist that I don't have? → Search the registry

Search proactively when:

- The task involves specific technologies, frameworks, or file formats
- You're about to do something where best practices matter (testing, deployment, APIs, documentation)
- The domain is specialized (PDF processing, data pipelines, ML workflows)
- You notice yourself about to give generic advice where expert patterns would help

Also search when users explicitly ask to find, install, or manage skills.

## Discovery Workflow

Use the registry API for search when one is available:

```bash
curl "<registry-url>/api/skills?q=QUERY&limit=20&offset=0"
```

**Parameters:**

- `q`: Search query (e.g., "frontend", "python", "pdf")
- `limit`: Results per page (max 100)
- `offset`: Pagination offset

**Response structure:**

```json
{
  "skills": [
    {
      "id": "...",
      "name": "skill-name",
      "namespace": "@owner/repo/skill-name",
      "sourceUrl": "https://github.com/...",
      "description": "...",
      "author": "...",
      "installs": 123,
      "stars": 45
    }
  ],
  "total": 100,
  "limit": 10,
  "offset": 0
}
```

## Search Strategies

The registry indexes skill names, descriptions, and tags. Construct queries that match how skill authors describe their work.

**Query construction:**

- Use 1-3 specific terms (too broad = noise, too narrow = misses)
- Prefer widely-used terminology over project-specific jargon
- Technology + task often outperforms either alone
- If results are poor, broaden or try synonyms

## Installation

Determine which host environment the user is working in before installing. If unclear, ask.

Capture these variables before installation:

- Host application or assistant
- Global or project-local scope
- Installation root used by that host
- Any required reload, restart, or reindex step

If the registry exposes a host selector, use the value that matches the user's environment.

Example host-aware installation command:

```bash
npx skills-installer install @owner/repo/skill-name --client <host-id>
```

Example scope selection:

```bash
npx skills-installer install @owner/repo/skill-name  # global (default)
npx skills-installer install @owner/repo/skill-name --local  # project-specific
```

Combined example:

```bash
npx skills-installer install @owner/repo/skill-name --client <host-id> --local
```

## Management

```bash
# List installed skills
npx skills-installer list

# Uninstall a skill
npx skills-installer uninstall @owner/repo/skill-name
```

## Presenting Results to Users

When you find relevant skills:

1. Show 3-5 most relevant results maximum
2. Include: name, namespace, description, stars, installs
3. Explain how each skill helps with their _specific_ task
4. Prioritize those with high installs
5. Always ask for confirmation before installing
6. Offer to help directly if no good skill exists or user declines

## Examples

**Example: Proactive suggestion**

User: "I need to create a Django REST API"

```bash
curl "<registry-url>/api/skills?q=django&limit=10"
```

Present suggestion:

```
I found some skills that could help:

1. django-rest-framework-expert (@vendor/framework/django-rest-framework-expert)
   Description: Django REST API development with best practices
   ⭐ 234 stars • 1,567 installs

Would you like me to install this, or help you directly without installing a skill?
```

**Example: Explicit search request**

User: "find skills for Python"

```bash
curl "<registry-url>/api/skills?q=python&limit=10"
```

Present results and ask which to install.

## API Reference

| Endpoint                                 | Description       |
| ---------------------------------------- | ----------------- |
| `GET /api/skills/search?q=QUERY`         | Search skills     |
| `GET /api/skills/@owner/repo/skill-name` | Get skill details |

**Registry example:** `<registry-url>/skills`

## Troubleshooting

**No results found:**

- Try broader search terms
- Browse the web registry at `<registry-url>/skills`

**Installation fails:**

- Verify namespace format: `@owner/repo/skill-name`
- Check skill exists in registry
- Verify directory permissions
- Confirm the chosen host id and installation scope are correct

**Skill not activating:**

- The user may need to restart or reload the host
- Verify the correct installation directory for that host
- Confirm SKILL.md exists in the installed skill path
## Overview

Use this skill for the capability described in this document.

## Core Workflow

Follow the primary workflow, commands, and decision points documented in the sections below.

## Best Practices

Follow the constraints, conventions, and cautions documented below, and prefer the documented path over improvisation.

## References

Use any linked scripts, assets, reference files, and companion resources mentioned in this document.

