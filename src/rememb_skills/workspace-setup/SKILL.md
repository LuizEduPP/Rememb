---
name: workspace-setup
description: Initialize development environment for a project. Use when setting up a new project, onboarding a developer, or configuring dependencies.
---

# Workspace Setup

Set up a consistent development environment.

## Overview

Use this skill to bootstrap a predictable local environment for a project, teammate, or fresh workstation.

## When to Use

- Setting up a new repository locally
- Onboarding a developer into an existing project
- Recreating dependencies after environment drift
- Writing down a minimal, repeatable local setup flow

## Quick Start

### Node.js
```bash
npm install
npm run dev
```

### Python
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Rust
```bash
cargo build
cargo test
```

### Docker
```bash
docker-compose up -d
```

## Checklist

- [ ] Dependencies installed
- [ ] `.env` configured (from `.env.example`)
- [ ] Dev server starts
- [ ] Tests pass

## Environment Template

```bash
# .env.example
DATABASE_URL=postgresql://user:pass@localhost:5432/db
API_KEY=your-key
DEBUG=true
```

## Best Practices
- Document setup in README
- Use `.env.example` as template
- Record issues in `experience/`
## Core Workflow

Follow the primary workflow, commands, and decision points documented in the sections below.

## Examples

Use the examples and snippets already present in this document whenever they apply to the task.

## References

Use any linked scripts, assets, reference files, and companion resources mentioned in this document.

