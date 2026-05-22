---
name: subagent-driven-development
description: Execute a written implementation plan through independent task workers in the current session. Use when the plan can be split into isolated tasks with explicit review gates.
---

# Subagent-Driven Development

## Overview

Use this skill to execute a written implementation plan through isolated workers with explicit review gates. If the current environment supports subagents, use them. If it does not, use the closest equivalent isolated-task workflow while keeping the same control pattern.

## When to Use

Use this skill when:

- a plan already exists
- tasks are mostly independent
- you want to preserve coordinator context while delegating implementation
- you want spec compliance and code quality checked separately

Prefer a simpler inline workflow when tasks are tightly coupled or when the environment cannot isolate task execution meaningfully.

## Core Workflow

1. Read the implementation plan once and extract the full text for each task.
2. Create a tracking list for all tasks before dispatching workers.
3. For each task, dispatch one isolated implementer worker with the full task text and required context.
4. If the implementer requests clarification, answer it before implementation continues.
5. After implementation, run a spec-compliance review.
6. Only after spec compliance passes, run a code-quality review.
7. If either review finds issues, return the task to the implementer and repeat the relevant review.
8. Mark the task complete only when both reviews pass.
9. After all tasks are complete, run one final end-to-end review and verification pass.

## Inputs / Assumptions

- The plan is already written and broken into actionable tasks.
- Each worker receives the task text directly rather than discovering it indirectly.
- The coordinator keeps authority for sequencing, context, and approval.
- Isolation matters more than raw speed for this workflow.

## Worker Status Model

Implementers should report one of these statuses:

- `DONE`: implementation completed and ready for review
- `DONE_WITH_CONCERNS`: implementation completed, but there are correctness or scope concerns to inspect first
- `NEEDS_CONTEXT`: missing information blocks safe completion
- `BLOCKED`: the task cannot proceed under current assumptions or current worker capability

When a worker is blocked:

1. provide missing context if the problem is informational
2. re-dispatch with a more capable worker if the task needs more reasoning
3. split the task if it is too large or too entangled
4. escalate to the user if the plan or requirement is wrong

Do not force repeated retries without changing the context, worker, or task shape.

## Review Order

Always keep this order:

1. implement
2. spec review
3. code quality review
4. final verification

Spec review prevents overbuilding and underbuilding. Code-quality review happens only after the task is confirmed to match the requested behavior.

## Examples

### Example task loop

```text
Read plan
Extract Task 1
Dispatch implementer
Resolve questions
Receive DONE
Run spec review
Fix issues if needed
Run code-quality review
Fix issues if needed
Mark Task 1 complete
```

### Example coordinator decision

```text
Worker status: NEEDS_CONTEXT
Resolution: provide the missing configuration path and re-dispatch the same task
```

## Optional Host Notes

- Some environments call isolated workers `subagents`. Others expose them as tasks, workers, or separate agent runs.
- Some environments support automatic reviewer dispatch. Others require the coordinator to invoke those reviews manually.
- If prompt templates exist next to this skill, use them as accelerators rather than hard dependencies.

## Validation Checklist

- The plan existed before execution started
- Tasks were extracted and tracked explicitly
- Each task used isolated implementation context
- Spec review happened before code-quality review
- Review findings triggered fixes and re-review when necessary
- Final verification ran after all tasks completed
## Best Practices

Follow the constraints, conventions, and cautions documented below, and prefer the documented path over improvisation.

## References

Use any linked scripts, assets, reference files, and companion resources mentioned in this document.

