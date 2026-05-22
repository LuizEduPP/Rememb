---
name: experience-record
description: Record lessons learned and implementation experiences for future reuse. Use when a task reveals a durable pattern, important decision, or debugging lesson worth preserving.
---

# Record Experience

Capture valuable lessons for future reference.

## Categories

| Tag | Use For |
|-----|---------|
| `[BUG]` | Bug solutions |
| `[PATTERN]` | Successful patterns |
| `[PITFALL]` | Things to avoid |
| `[DECISION]` | Important choices |
| `[PERF]` | Optimizations |

## Template

```markdown
# [CATEGORY] Title

## TL;DR
[One sentence]

## Problem
[What was the issue]

## Solution
[How it was solved]

## Code Example
```language
// Before (bad)
...

// After (good)
...
```

## Prevention
[How to avoid in future]

## Tags
#tag1 #tag2
```

## Example

```markdown
# [BUG] Null Pointer in User Query

## TL;DR
Check for null before accessing user properties.

## Problem
API crashed on non-existent user.

## Solution
Added null check and 404 response.

## Prevention
- Unit tests for null cases
- Use Optional types
```

## Storage

```
/experience/
├── bugs/
├── patterns/
└── decisions/
```

## Tips
- Write while context is fresh
- Include code examples
- Add searchable tags
## Overview

Use this skill for the capability described in this document.

## When to Use

Use this skill when the request matches the capability, constraints, and activation cues described below.

## Core Workflow

Follow the primary workflow, commands, and decision points documented in the sections below.

## Examples

Use the examples and snippets already present in this document whenever they apply to the task.

## Best Practices

Follow the constraints, conventions, and cautions documented below, and prefer the documented path over improvisation.

## References

Use any linked scripts, assets, reference files, and companion resources mentioned in this document.

