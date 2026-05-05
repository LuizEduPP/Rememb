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
| TUI via `rememb` | Documented | Primary local interface |
| CLI version/help output | Tested | Covered by pytest |
| `rememb fetch-model` | Documented | Not covered by automated tests yet |

## MCP Transport Surfaces

| Surface | Status | Notes |
|---------|--------|-------|
| stdio MCP via `rememb mcp` | Documented and partially tested | CLI contract and tool schema are covered by pytest |
| SSE MCP via `rememb mcp --transport sse` | Documented | Repository documents and exposes this path, but no end-to-end automated client test exists yet |
| MCP tool set (9 tools) | Tested at schema level | pytest verifies the public tool list and key schema defaults |

## Registry and Packaging Surfaces

| Surface | Status | Notes |
|---------|--------|-------|
| PyPI package `rememb` | Active | Public package metadata maintained in `pyproject.toml` |
| MCP registry metadata in `server.json` | Documented | Public metadata file exists in repository |
| Docker container for MCP | Documented | Dockerfile exists; not covered by automated tests yet |

## Compatibility by Client Type

| Client type | Status | Notes |
|-------------|--------|-------|
| IDEs or tools that support local stdio MCP servers | Expected | Use the documented `command: rememb` and `args: ["mcp"]` configuration |
| Clients that support HTTP/SSE MCP endpoints | Expected | Use the separate persistent SSE process documented in README |
| Tools without MCP support | Partial | Use the local TUI and CLI surfaces instead |

## Current Gaps

These surfaces are not yet validated by automated end-to-end coverage in this repository:

- real MCP client interoperability matrix by product name
- end-to-end SSE integration tests
- Docker-based runtime validation
- cross-platform smoke tests outside the GitHub Actions Linux runner

## Reading This Matrix Correctly

This file is not a marketing claim. It is a living statement of what the repository currently proves, documents, or still needs to validate.