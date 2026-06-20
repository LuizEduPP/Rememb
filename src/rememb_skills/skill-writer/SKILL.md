---
name: skill-writer
description: Guide users through creating portable AI skills. Use when the user wants to create, write, author, or redesign a skill, or needs help with SKILL.md files, frontmatter, portability, or skill structure.
---

# Skill Writer

## Overview

Use this skill to create or refactor skills that stay focused, portable, and easy to discover. The primary workflow should work across assistants, IDEs, CLIs, and chat applications without assuming a specific host.

## When to Use

Use this skill when:

- Creating a new skill from scratch
- Updating or redesigning an existing `SKILL.md`
- Fixing frontmatter, structure, or discovery quality
- Converting a prompt or workflow into a reusable skill
- Making an existing skill more host-agnostic

## Core Workflow

### 1. Define the skill boundary

First determine the exact capability the skill should provide.

- What outcome should the skill produce?
- When should the skill activate?
- What inputs, files, or tools does it rely on?
- Which parts are universal, and which are host-specific?

Keep the scope narrow. One skill should solve one coherent problem.

### 2. Choose the skill root

Pick a concrete `<skill-root>` that matches the current environment. The skill itself should not assume whether that root is user-level, workspace-level, registry-managed, or tool-managed.

Install the skill under:

```text
<skill-root>/skill-name/
```

If the environment supports multiple installation scopes, choose the scope that matches the user's intent and team-sharing needs.

### 3. Create the file layout

Every skill needs `SKILL.md`. Add supporting files only when they improve clarity or reuse.

```text
skill-name/
├── SKILL.md
├── reference.md
├── examples.md
├── scripts/
└── templates/
```

Use supporting files for progressive disclosure. Keep the main `SKILL.md` readable without hiding core behavior in references.

### 4. Write minimal, valid frontmatter

Use YAML frontmatter with stable, discovery-friendly fields.

```yaml
---
name: skill-name
description: Brief description of what this does and when to use it
---
```

Frontmatter rules:

- `name` should be lowercase, stable, and directory-aligned
- `description` should explain both capability and activation context
- Optional metadata should be added only when the host actually uses it
- Tool restrictions should be explicit when they improve safety or focus

### 5. Write discovery-friendly descriptions

Use this formula:

```text
[what it does] + [when to use it] + [common triggers]
```

Good descriptions usually include:

- concrete operations
- file types or domains
- user phrases the assistant is likely to see
- activation cues such as "Use when..."

Avoid vague descriptions such as "helps with documents" or "useful for coding".

### 6. Structure the content consistently

Use these sections when they fit the skill:

- `Overview`
- `When to Use`
- `Core Workflow`
- `Inputs / Assumptions`
- `Examples`
- `Optional Host Notes`
- `Validation Checklist`

Keep the primary workflow portable. Put environment-specific behavior in `Optional Host Notes` or a reference file.

## Inputs / Assumptions

- The skill directory name should match the frontmatter `name`
- Core instructions should remain valid without a specific IDE or assistant
- English should be used consistently unless the skill explicitly targets multilingual output
- Examples should use placeholders for paths, secrets, and host-specific values

## Examples

### Example frontmatter

```yaml
---
name: pdf-processor
description: Extract text and tables from PDF files, fill forms, merge documents, and OCR scanned pages. Use when working with PDFs, forms, or document extraction tasks.
---
```

### Example read-only skill

```yaml
---
name: code-reader
description: Read and analyze code without making changes. Use for code review, code comprehension, and architecture walkthroughs.
allowed-tools: Read, Grep, Glob
---
```

### Example skill layout

```text
api-designer/
├── SKILL.md
├── reference.md
└── templates/
    └── openapi.yaml
```

## Optional Host Notes

- Some hosts support user-level and workspace-level skill roots. Treat those as deployment choices, not required behavior.
- Some hosts cache skills and require reload, reindex, or restart before a newly installed skill is visible.
- Some hosts support extra metadata such as tool restrictions or invocation flags. Keep those additions optional and avoid making the main flow depend on them.

## Validation Checklist

- `SKILL.md` exists at `<skill-root>/skill-name/SKILL.md`
- The directory name matches frontmatter `name`
- YAML frontmatter opens and closes correctly with `---`
- The description clearly states what the skill does and when to use it
- The main workflow works without assuming a specific host
- Supporting files are referenced only when they exist
- Any host-specific setup is isolated to optional notes or references

## Best Practices

- Keep one skill focused on one capability
- Make the description specific enough to trigger on real user language
- Write instructions for the model, not as marketing copy for humans
- Prefer concrete examples over abstract guidance
- Use progressive disclosure when detailed references improve clarity
- Keep host-specific behavior optional and clearly isolated

## Troubleshooting

**Skill does not activate:**
- Make the description more specific with concrete trigger words
- Mention file types, domains, or operations directly in the description
- Add an explicit `Use when...` activation clause

**Multiple skills conflict:**
- Narrow the scope of each skill
- Differentiate descriptions with clearer triggers
- Remove overlapping examples or generic wording

**Skill has structural errors:**
- Verify YAML syntax and closing frontmatter markers
- Check that referenced files actually exist
- Confirm paths use forward slashes and portable placeholders
- Keep optional metadata only where the host can use it

## Output Format

When creating or refactoring a skill, produce:

1. A valid `SKILL.md` with clean frontmatter
2. A portable workflow that does not depend on one host
3. Concrete examples that match likely user requests
4. Optional supporting files only when they add clear value
5. A short validation pass for structure, discovery, and portability
## References

Use any linked scripts, assets, reference files, and companion resources mentioned in this document.

