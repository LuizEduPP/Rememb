---
name: executing-plans
description: Execute a written implementation plan in a separate session with explicit review checkpoints. Use when the user already has a plan and wants focused implementation against it.
---

# Executing Plans

## Overview

Load plan, review critically, execute all tasks, report when complete.

## When to Use

Use this skill when you already have a written implementation plan and want to execute it in a separate session with explicit review checkpoints.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

**Note:** This workflow is stronger in environments with isolated-task support. If the current environment offers a more advanced worker-based execution workflow, prefer that option over this linear fallback.

## Core Workflow

### Step 1: Load and Review Plan
1. Read plan file
2. Review critically - identify any questions or concerns about the plan
3. If concerns: Raise them with your human partner before starting
4. If no concerns: Create TodoWrite and proceed

### Step 2: Execute Tasks

For each task:
1. Mark as in_progress
2. Follow each step exactly (plan has bite-sized steps)
3. Run verifications as specified
4. Mark as completed

### Step 3: Complete Development

After all tasks complete and verified:
- Announce that you are moving into final verification and delivery
- Run the project's normal finish workflow: tests, validation, summary, and delivery options
- If the current host provides a dedicated finishing workflow, use it

## When to Stop and Ask for Help

**STOP executing immediately when:**
- Hit a blocker (missing dependency, test fails, instruction unclear)
- Plan has critical gaps preventing starting
- You don't understand an instruction
- Verification fails repeatedly

**Ask for clarification rather than guessing.**

## When to Revisit Earlier Steps

**Return to Review (Step 1) when:**
- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

**Don't force through blockers** - stop and ask.

## Remember
- Review plan critically first
- Follow plan steps exactly
- Don't skip verifications
- Reference skills when plan says to
- Stop when blocked, don't guess
- Never start implementation on main/master branch without explicit user consent

## Integration

**Related workflow skills or processes:**
- An isolated workspace workflow, if your host or team uses one
- A planning workflow that creates the written plan this skill executes
- A finishing workflow for tests, validation, and delivery
## Examples

Use the examples and snippets already present in this document whenever they apply to the task.

## Best Practices

Follow the constraints, conventions, and cautions documented below, and prefer the documented path over improvisation.

## References

Use any linked scripts, assets, reference files, and companion resources mentioned in this document.

