---
name: brainstorming
description: Mandatory architectural and intent-alignment phase before code generation, feature modification, or stack scaffolding. Use when the task needs constraint mapping, design clarification, or explicit architecture approval before implementation.
---

# Agentic Brainstorming & Architecture Design (2027 Workflow)

Bridge the gap between raw intent and high-performance execution. This skill maps project constraints, prevents architectural drift, and ensures total alignment before a single line of code is written.

<HARD-GATE>
Do NOT invoke any implementation skill, write functional code, scaffold files, or execute state changes until the technical architecture is explicitly approved by the user. The ONLY valid transition from this state is to the implementation planning phase (`writing-plans`).
</HARD-GATE>

## The 2027 Anti-Pattern: "Context Blindness"

Assuming a feature is too simple for a design doc is why codebases rot. In automated and AI-assisted repositories, minor unvetted assumptions break semantic indexes, corrupt component boundaries, and cause infinite loops of code refactoring. Every structural change requires a fast, high-density alignment cycle.

## Core Checklist

Execute these phases sequentially. Do not skip steps:

1. **Context & Semantic Analysis** — Deep dive into active code graphs, MCP tools, configuration scopes, and active project rules.
2. **Dynamic UI/UX Evaluation** — Assess if the feature dictates visual interaction (Generative UI, component layouts). If yes, offer the interactive visual companion immediately as a standalone option.
3. **High-Density Clarification** — Ask precise, high-signal questions. Group options into structured multiple-choice matrices rather than loose text loops to save token context.
4. **Multi-Architecture Trade-offs** — Present 2-3 technical approaches (e.g., edge vs. centralized, native vs. polymorphic components) highlighting performance, complexity, and scalable boundaries.
5. **Incremental Specification** — Present the system architecture in isolated, logical blocks (Data Flow, API Contracts, State, Error Boundaries).
6. **Spec File Generation & Commit** — Write the approved architecture directly to `docs/specs/YYYY-MM-DD-<topic>-design.md`.
7. **Automated Spec Review** — Scan the final document for placeholders, structural contradictions, or coupling leaks before transition to planning.

## Architectural Guidelines for AI-Native Environments

### Extreme Isolation & Loose Coupling
- Design components and modules as black boxes with deterministic inputs/outputs.
- If a file or component requires an LLM to hold more than 400 lines of active code in context to understand its side effects, reject the architecture and decompose it.
- Explicitly define boundaries so that subsequent autonomous agent runs can edit internal logic without cascading breaks across the codebase.

### Working with Modern Stacks
- Standardize on native platform capabilities first (native Web APIs, Container Queries, native state isolation).
- Avoid proposing external architectural dependencies unless absolutely required by performance limits.
- Integrate smoothly with existing code patterns. If an existing architecture is flawed and impacts the task, include a targeted, scoped refactoring step within the proposal.

## The Visual Companion Protocol

When a task involves interface layout, generative UI modules, or complex spatial flows, isolate the visual proposal:

> "Some of what we're working on might be easier to explain if I can show it to you in a web browser. I can put together mockups, diagrams, comparisons, and other visuals as we go. This feature is still new and can be token-intensive. Want to try it? (Requires opening a local URL)"

*Note: This prompt must be sent standalone, clean of other technical text, allowing the user to opt-in or continue via terminal constraints.*

## Transition to Execution

Once the architecture is fully approved:
1. Write and save the specification file.
2. Run the spec review checklist to purge any "TODO" or "TBD" tags.
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

3. **Invoke the `writing-plans` skill.** Do not slide into implementation, file writing, or style tasks here. The transition to planning is strict.