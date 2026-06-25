# Compatibility Matrix

This document describes the compatibility surface that is explicitly documented or validated in this repository.

It is intentionally conservative. Anything listed here should be read as one of these states:

- tested in automated checks
- documented and expected to work based on the current public contract
- not yet verified in this repository

## Python Versions

| Surface | Status | Notes |
|---------|--------|-------|
| Python 3.10 | CI target | Covered by `.github/workflows/ci.yml` |
| Python 3.11 | CI target | Covered by `.github/workflows/ci.yml` |
| Python 3.12 | CI target | Covered by `.github/workflows/ci.yml` |

## Local Interfaces

| Interface | Status | Notes |
|-----------|--------|-------|
| Web UI via `rememb` | Documented | FastAPI + SPA; default `http://127.0.0.1:18181` |
| CLI version/help output | Tested | Covered by pytest |
| `rememb fetch-model` | Disabled | Hidden CLI command; exits with guidance (keyword search since v0.4.12) |
| JSON storage backend | Tested | Default `~/.rememb/entries.json` (home-first) |
| SQLite storage backend | Tested | Optional `storage_backend: sqlite`; auto-migrates from JSON |

## MCP Transport Surfaces

| Surface | Status | Notes |
|---------|--------|-------|
| stdio MCP via `rememb mcp` | Documented and partially tested | CLI contract and tool schema covered by pytest |
| SSE MCP via `rememb mcp --transport sse` | Tested at app level | pytest verifies SSE route wiring; default port `8765` |
| MCP tool set (17 tools) | Tested at schema level | pytest verifies the public tool list and key schema defaults |

Public tools: `rememb_get`, `rememb_recent`, `rememb_list_tags`, `rememb_read`, `rememb_read_page`, `rememb_search`, `rememb_versions`, `rememb_restore`, `rememb_diff`, `rememb_write`, `rememb_edit`, `rememb_delete`, `rememb_clear`, `rememb_stats`, `rememb_consolidate`, `rememb_list_skills`, `rememb_use_skill`.

## Registry and Packaging Surfaces

| Surface | Status | Notes |
|---------|--------|-------|
| PyPI package `rememb` | Active | Public package metadata maintained in `pyproject.toml` |
| Bundled skills in `rememb_skills` | Active | 60 skills shipped inside the core `rememb` wheel |
| MCP registry metadata in `server.json` | Documented | Public metadata file exists in repository |
| Docker container for MCP | Tested | Dockerfile build and `rememb mcp --help` smoke test covered in CI |

## Compatibility by Client Type

| Client type | Status | Notes |
|-------------|--------|-------|
| IDEs or tools that support local stdio MCP servers | Expected | Use `command: rememb` and `args: ["mcp"]` |
| Clients that support HTTP/SSE MCP endpoints | Expected | Start `rememb mcp --transport sse` separately; connect to `/sse` and `/messages/` |
| Tools without MCP support | Partial | Use the local Web UI and CLI surfaces instead |

## Current Gaps

These surfaces are not yet validated by automated end-to-end coverage in this repository:

- real MCP client interoperability matrix by product name
- full end-to-end SSE client session tests against a live MCP consumer
- cross-platform smoke tests outside the GitHub Actions Linux runner

## Reading This Matrix Correctly

This file is not a marketing claim. It is a living statement of what the repository currently proves, documents, or still needs to validate.
