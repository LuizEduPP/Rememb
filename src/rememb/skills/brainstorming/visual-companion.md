---
name: visual-companion
description: "High-fidelity visual feedback loop for Generative UI, architecture mapping, and real-time design validation. Orchestrates a browser-based preview environment to synchronize agent intent with user visual perception."
---

# Agentic Visual Companion (2027 Edition)

This is not a static preview tool; it is a live synchronization bridge between the agent's mental model and the user's visual requirements. Use it to validate layouts, components, and architectures before final implementation.

## Per-Question Protocol

Do not keep the browser open "just because." Evaluate every turn: **"Would a visual representation reduce semantic ambiguity?"**

**Use the Browser for:**
- **Generative UI Validation** — Testing dynamic component states, fluid typography, and `oklch` color scales.
- **Dynamic Architecture Mapping** — Mermaid/Diagrams of data flow, MCP tool relationships, and system boundaries.
- **High-Density Comparisons** — Side-by-side visual diffs of layout approaches (e.g., Grid vs. Flex, Minimalist vs. Maximalist).
- **Interactive State Machines** — Visualizing complex logic transitions or user flows.

**Stay in Terminal for:**
- **Logical Constraints** — "What happens if the API fails?"
- **Textual Specs** — Clarifying naming conventions, file paths, or dependency versions.
- **Conceptual Trade-offs** — Comparing performance metrics or library choices in text.

## Operational Workflow (MCP-Native)

1. **Verify Environment**: Check if the preview server is active in the current project scope (`.brainstorm/server-info`).
2. **Push Fragment**: Write **semantic HTML fragments** using modern CSS (Container Queries, Native Nesting).
   - Use unique filenames per iteration: `nav-v1.html`, `nav-v2-fluid.html`.
   - Never overwrite; always increment to maintain a visual history for the session.
3. **Context Sync**: Read `$STATE_DIR/events` on every turn. The user's clicks and selections are high-signal data points that override terminal ambiguity.

## 2027 Visual Standards (CSS Toolkit)

Utilize the built-in frame template for rapid prototyping:

### Atomic Options & Selections
```html
<div class="options" data-multiselect> <div class="option" data-choice="modern-dark" onclick="toggleSelect(this)">
    <div class="letter">A</div>
    <div class="content">
      <h3>Modern Dark (OKLCH)</h3>
      <p>High-contrast, P3 color gamut optimized.</p>
    </div>
  </div>
</div>