---
name: code-commit
description: Commit code changes with well-structured messages following Conventional Commits. Use when ready to commit after implementation or bug fix.
---

# Code Commit

Create well-structured git commits with meaningful messages.

## Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

## Types

| Type | Use For |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation |
| `refactor` | Code restructuring |
| `test` | Adding tests |
| `chore` | Maintenance |

## Examples

```bash
feat(auth): add user login functionality

Implement JWT-based authentication with:
- Login endpoint
- Token validation

Closes #123
```

```bash
fix(api): handle null response in user query
```

## Rules

1. **Atomic** - One logical change per commit
2. **Present tense** - "add" not "added"
3. **50/72** - Subject ≤50, body wrapped at 72
4. **Reference issues** - `Closes #123` or `Fixes #456`

## Overview

Use this skill for the capability described in this document.

## When to Use

Use this skill when the request matches the capability, constraints, and activation cues described below.

## Core Workflow

Follow the primary workflow, commands, and decision points documented in the sections below.

## Best Practices

Follow the constraints, conventions, and cautions documented below, and prefer the documented path over improvisation.

## References

Use any linked scripts, assets, reference files, and companion resources mentioned in this document.

