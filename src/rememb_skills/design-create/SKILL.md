---
name: design-create
description: Create design documents for features or systems. Use when architecture planning, API design, or technical decisions are needed before implementation.
---

# Create Design Document

Create comprehensive design documents that guide implementation.

## Core Workflow

1. **Analyze** - Understand the requirement
2. **Research** - Check existing patterns
3. **Design** - Create architecture
4. **Document** - Write design doc
5. **Review** - Get approval

## Template

```markdown
# Design: [Feature Name]

## Overview
[What this covers]

## Goals
- Goal 1
- Goal 2

## Non-Goals
- What this does NOT cover

## Architecture

### Components
| Component | Responsibility |
|-----------|----------------|
| A | Does X |
| B | Does Y |

### API Design (if applicable)
#### POST /api/example
- Request: `{ "field": "value" }`
- Response: `{ "result": "value" }`

## Alternatives Considered
| Option | Pros | Cons |
|--------|------|------|
| A | ... | ... |

## Risks
| Risk | Mitigation |
|------|------------|
| Risk 1 | How to handle |
```

## Storage
Save to `design/[feature-name].md`

## When to Use

Use this skill when the request matches the capability, constraints, and activation cues described below.

## Examples

Use the examples and snippets already present in this document whenever they apply to the task.

## Best Practices

Follow the constraints, conventions, and cautions documented below, and prefer the documented path over improvisation.

## References

Use any linked scripts, assets, reference files, and companion resources mentioned in this document.

