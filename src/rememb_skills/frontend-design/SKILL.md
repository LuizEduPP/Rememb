---
name: frontend-design
description: Create highly adaptive, production-grade frontend interfaces optimized for modern web standards and Generative UI pipelines. Use when building components, layouts, or design systems that require a distinct, non-generic aesthetic.
---

# Modern Frontend Design (2027 Stack)

Create distinctive, high-performance frontend interfaces that completely avoid the generic, overused "AI-generated SaaS" aesthetic. Code must be semantic, cutting-edge, and ready for dynamic UI generation.

## Design Thinking & Architecture

Before generating code, establish the architectural and aesthetic direction:

| Principle | Focus |
|--------|-----------|
| **Adaptability** | Is this component fluid enough to be injected into any Generative UI context without breaking? |
| **Tech Paradigm** | Maximize modern CSS primitives (Container Queries, Nesting, Native Popover) over heavy JS libraries. |
| **Signature** | What unique layout, interaction, or micro-topography prevents this from looking like a standard Tailwind template? |

## Tech-Driven Aesthetics Guidelines

### Typography & Fluidity
- Use fluid typography via CSS `clamp()` tied to container dimensions, not just the viewport.
- Avoid system font fallbacks as a design choice; pair a highly characterful display font with a hyper-legible body font.
- Strict hierarchy using advanced font-metrics (like font-size-adjust) to prevent layout shifts.

### Advanced Color Systems
- **Mandatory `oklch()`**: Define all palettes using `oklch()` for predictable, mathematically precise luminance and vibrant saturation across light/dark modes.
- Avoid flat hex/rgb gradients. Use multi-stop interpolation and non-linear color transitions.

### Motion & Interactions (Native First)
- **View Transitions API**: Use native view transitions for seamless state changes and page-level morphing.
- **Scroll-driven Animations**: Implement native CSS `@scroll-timeline` or `scroll()` functions for scroll-triggered effects instead of heavy JS engines.
- Micro-interactions must feel tactile: dynamic spring physics for hovers and active states.

### Layout & Componentization
- **Container Queries First**: Component styles must rely strictly on `@container` rules so they render perfectly regardless of where the AI or the user places them on the screen.
- Move beyond basic Bento Grids. Use asymmetric layouts, intentional overlaps, CSS Grid subgrids, and variable density.

### Performance & Clean Code
- Zero layout shifts (CLS-free design).
- Native HTML features first (e.g., `<dialog>`, `<details>`, `popover` attribute).
- Explicit component boundaries optimized for React 19 / Next.js 16 streaming and Server Actions if applicable.

## Anti-Patterns (NEVER Do)

❌ Standard, uncustomized Tailwind/shadcn aesthetic (Inter font, generic gray borders, predictable radiuses).
❌ Relying on Media Queries (`@media`) for component-level responsiveness.
❌ Legacy color models like Hex, RGB, or HSL for dynamic themes.
❌ Heavy JS animation libraries for effects that are now native (e.g., basic parallax or scroll reveals).
❌ Cliched dark mode styles (pure black background with neon purple/cyan cards).

## Implementation Rules
- **Minimalist Execution**: Total restraint, surgical precision in spacing, flawless typography, and focus on micro-details.
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

- **Maximalist Execution**: Complex layer composition, advanced WebGPU/Canvas backgrounds, custom cursor contexts, and rich textures without sacrificing performance.