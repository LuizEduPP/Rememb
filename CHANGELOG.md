# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.9] - 2026-05-22

### Added
- Entry versioning support.
- Soft delete support for entries.

### Changed
- Search scoring now includes stronger token and tag boosting.
- Delete operations now preserve entries through soft delete instead of removing them outright.

### Fixed
- Search relevance is improved for exact token and tag matches.

## [0.4.8] - 2026-05-22

### Added
- MCP tools `rememb_write`, `rememb_edit`, and `rememb_delete` now support batch payloads alongside the existing single-entry mode.
- Store-level batch helpers were added for atomic multi-entry write, edit, and delete operations while preserving the existing JSON-backed storage flow.

### Changed
- MCP tool documentation was updated to describe the new batch payload fields while keeping the existing documentation style.
- Release metadata was aligned to version `0.4.8` across the Python package, Docker image install target, and MCP registry metadata.

### Fixed
- The runtime MemoryStore protocol assertion in `store.py` now includes the newly added batch methods, preventing the MCP server from failing during import.

## [0.4.7] - 2026-05-21

### Added
- Skills page added to the Web UI, listing all bundled skills available in the installed rememb package; screenshot added at `assets/web-ui-skills.png`.
- README now documents the Skills page with a screenshot and includes it in the top-level navigation description and feature list.

### Changed
- CHANGELOG retroactively includes the missing v0.4.3 entry that documented the TUI removal and Web UI introduction.
- CONTRIBUTING.md project structure table updated: `tui.py` replaced by `web.py`.
- COMPATIBILITY.md updated: all "TUI" interface references replaced with "Web UI (FastAPI + SPA)".
- `.github/agents/rememb-maintainer.agent.md` updated: all Textual/TUI references replaced with Web UI/`web.py` equivalents across `description`, scope, constraints, working rules, and approach sections.

## [0.4.6] - 2026-05-21

### Changed
- Package and release metadata were aligned to version `0.4.7` across the Python package, Docker image install target, and MCP registry metadata.
- README was refreshed to reflect the current Web UI and now includes real screenshots for the main memories view, stats view, and settings view.

### Fixed
- Semantic embedding cache persistence now avoids being overwritten by filtered or section-scoped operations, preventing stale subset embeddings from poisoning the shared on-disk cache.
- Store edit and delete operations now require an initialized root before mutating state, avoiding partially initialized `.rememb/` directories.
- Entry formatting now distinguishes summary output from full output correctly, and the Web UI settings flow now falls back safely when numeric pagination inputs parse to invalid values.

## [0.4.5] - 2026-05-11

### Fixed
- Write locks now treat all mutating file modes, including `r+`, as exclusive, preventing concurrent writers from corrupting `.rememb/entries.json` during large delete or consolidation operations.
- Added a regression test that verifies a second process cannot acquire a writable lock while another `r+` operation is still in progress.

## [0.4.3] - 2026-05-03

### Added
- Web UI (`src/rememb/web.py`) built with FastAPI and a vanilla-JS SPA served from `src/rememb/static/index.html` — zero build step, zero external JS dependencies.
- Web UI features: section sidebar with live entry counts and per-section consolidate action, card grid with pagination, modal CRUD flows (create, inspect, edit, delete), semantic search from the header, sort controls (recent, oldest, storage, reversed), Stats page, and Settings page.
- CLI flags `--host`, `--port`, and `--no-browser` for the default `rememb` command.
- `/api/skills` and `/api/skills/{skill_id}` read-only routes in the Web UI for listing packaged skills.
- `fastapi>=0.100.0` and `uvicorn>=0.20.0` added as required dependencies.

### Changed
- `rememb` with no arguments now launches the Web UI in the browser (replaces the former TUI launch).
- `run_web()` helper in `web.py` takes over the launch responsibility previously handled by `tui.py`.

### Removed
- `tui.py` and its Textual-based terminal interface removed from the package.
- `textual` removed from the dependency list.

## [0.4.4] - 2026-05-05

### Added
- GitHub Actions CI now validates the project on Python 3.10, 3.11, and 3.12.
- GitHub release workflow and Trusted Publishing documentation were added to support a reproducible release process.
- Initial compatibility matrix and explicit public metadata links for documentation and changelog were added.

### Changed
- Installation and packaging docs were aligned to the current mandatory dependency model.
- Declared Python support now matches the real MCP constraint: Python 3.10+.

### Fixed
- Glama now discovers all 9 MCP tools (`rememb_consolidate` and `rememb_init` were missing from the published package).
- CLI test handling now strips ANSI formatting before assertions, avoiding false negatives in CI.

## [0.4.2] - 2026-04-30

### Added
- Unified configuration management in `.rememb/config.json`, consolidating tunable limits, dynamic sections, section icons/colors, semantic model settings, and TUI paging controls in one persisted file.
- Full TUI configuration screen (`F2`) for editing dynamic sections, section icons, semantic model selection, and paging limits.
- Per-section appearance config with icon selection and automatic random colors for new custom sections.
- Exact tag filtering in the TUI by clicking tag pills, combined with the active text search and current section.
- Optional `tag` filter for the `rememb_search` MCP tool.
- Helper support for configuration persistence and normalization, including atomic config saves plus normalization/validation of section names, icons, and colors.
- Persistent local SSE transport for `rememb mcp`, with configurable host and port for reusing one MCP process across multiple local clients.

### Changed
- CLI help text and command descriptions now reflect the transport split between stdio and persistent SSE, and the model download command follows the configuration-driven semantic model default.
- README expanded to document persistent SSE usage, the richer `.rememb/config.json` format, and environment overrides for semantic model settings.
- Workspace agent/instruction surfaces under `.github/` were aligned with the newer TUI/MCP/config toolset.
- `MemoryStore` protocol now reflects configuration management and paginated reads used by the current TUI and store implementation.
- Card rendering now caps visible tags and collapses the remainder into a `+N` indicator to prevent oversized cards.
- Section updates are normalized more aggressively: case-insensitive duplicates collapse to a single normalized section name.
- Removing a section with existing entries now migrates those entries to `uncategorized` instead of rejecting the config update.

### Fixed
- `meta.json` section metadata is now kept in sync automatically when the effective section list changes.

### Documentation
- README and release notes were updated to describe the unified configuration system, MCP SSE transport, dynamic section customization, and tag-aware search/filter behavior more accurately.

## [0.4.1] - 2026-04-28

### Added
- `rememb_consolidate` MCP tool and `consolidate_entries()` store API with two modes: `exact` (default, normalized content) and `semantic` (configurable `similarity_threshold`) to merge near-duplicates and metadata (tags/access stats).
- `semantic_scope` option in `write_entry()` and MCP `rememb_write` to choose semantic duplicate guard scope: `global` (default) or `section`.
- TUI action for consolidation (`Ctrl+D` shortcut and sidebar button), running semantic deduplication for the current section context.

## [0.4.0] - 2026-04-21

### Added
- `rememb fetch-model` CLI command to download the `all-MiniLM-L6-v2` (~80MB) embedding model with a progress bar, preventing offline cold-start timeouts.
- **Semantic Bodyguard:** Prevents duplicate or highly similar memories from polluting the store by blocking saves with >88% semantic overlap and responding with `RemembValidationError`.
- **Muscular Memory (Read-Boosting):** Automatically bumps the `access_count` and `last_accessed` timestamp whenever an entry is retrieved, giving priority to frequently used active memories.
- **Hybrid Search & Time Decay:** Semantic search now combines exact phrase hits (Lexical Boost) and applies a time-decay factor (older unused memories organically drop to 70% relevance after 90 days).

### Changed
- Translated all internal localized error and validation messages to pure English.

### Removed
- Stripped all inline comments from source code to enforce self-documenting code practices (`no-comments` rule).

## [0.3.9] - 2026-04-18

### Added
- Full TUI built with Textual — launched by default with `rememb`
- Sidebar navigation with section filters and entry counts
- Grid of memory cards with per-section color coding and icons
- Inline search (`/`) across all entries
- Side panel for creating and editing entries without leaving the screen
- Dynamic grid layout — 1 to 4 columns based on terminal width
- `Select` widget for section field in new/edit forms
- `flat=True` buttons throughout for clean borderless styling
- Keyboard bindings: `Ctrl+N` new, `Ctrl+R` refresh, `/` search, `Q` quit

### Changed
- CLI simplified to two commands: `rememb` (TUI) and `rememb mcp`
- `rememb` with no arguments now launches the TUI instead of showing help
- All CLI sub-commands (`write`, `read`, `search`, `edit`, `delete`, `clear`, `import`, `rules`) removed from CLI — available via MCP and Python API
- Delete confirmation kept as modal; new/edit moved to inline side panel

### Fixed
- `DuplicateIds` error when refreshing the entry grid — replaced `query("*").remove()` with `remove_children()`
- `NoMatches` error on `EntryCard` internal elements — switched from class selectors to UUID-based IDs per instance
- `EmptySelectError` on `Select` widget initialized with empty options list


### Removed
- Hardcoded constants (MAX_CONTENT_LENGTH, MAX_TAG_LENGTH, MAX_TAGS_PER_ENTRY, MAX_ENTRIES)
- Fallbacks (find_root→global_root, search_entries→keyword_search, etc.)
- Thresholds (len(content.strip())<<10, score>0)
- Magic numbers (0x7FFFFFFF, 1e-9, 300, 500, 80, 10)
- Unused import re from validation.py

## [0.3.8] - 2026-04-13

### Added
- Glama registry integration
- Dockerfile for container deployment
- logo.png and rememb-chat.gif assets
- LinkedIn article v2 (Context Drift continuation)
- `rememb_stats` MCP tool

### Changed
- Improved tool descriptions for Glama score A
- Updated README with Glama badge

### Fixed
- Version synchronization (was showing 0.3.6, corrected to 0.3.8)

## [0.3.7] - 2026-04-13

### Added
- `rememb stats` CLI command

## [0.3.6] - 2026-04-13

### Added
- MCP server support with 8 tools
- Glama registry submission
- PR #4583 to awesome-mcp-servers

### Changed
- Improved error messages
- Enhanced tool descriptions

## [0.3.5] - 2026-04-13

### Added
- Semantic search with sentence-transformers
- Embedding cache with hash validation
- Keyword search fallback

## [0.3.4] - 2026-04-13

### Added
- MCP Registry metadata for official registry submission

### Fixed
- Version mismatch between files
- Dead code cleanup
- JSON corruption handling
- mcp_init functionality
- Performance cache issues
- Repository URL capitalization in README

## [0.3.3] - 2026-04-13

### Added
- Rich styled UI with custom help, panels, and improved formatting

### Changed
- Simplified rules command to output generic instructions only
- Removed roadmap section from README

### Fixed
- __version__ attribute
- Dead code cleanup
- JSON corruption handling
- mcp_init functionality
- Gitignore check per-line exact match
- Clear command exit code
- CustomTyper traceback removal

## [0.3.2] - 2026-04-12

### Added
- MCP JSON config block to `rememb rules` output
- `--version` / `-V` flag to CLI
- File locking cross-platform (Windows/Unix)
- Atomic modify for read-modify-write operations
- Backup and recovery for corrupted JSON

### Changed
- Consolidated format_entries() with include_id parameter
- Removed Markdown import
- Removed duplicate import re
- Improved error handling and data integrity across store and MCP server
- Wrapped all MCP tool operations in asyncio.to_thread for non-blocking I/O
- Removed all comments and docstrings from source files
- Simplified roadmap — remove completed and future items
- Reorganized README — cleaner structure
- Removed redundant title from README (already in cover image)
- Fixed deprecated license format in pyproject.toml

### Fixed
- Atomic write operations
- File lock handling
- delete_entry functionality
- Content sanitization
- MCP validation
- Keyword search improvements
- init_cmd decorator

## [0.3.1] - 2026-04-12

### Added
- Cover image and reorganized demo placement in README
- Corrected repository name capitalization in cover image URL

## [0.3.0] - 2026-04-12

### Added
- MCP server for native IDE integration

### Changed
- Restructured README to prioritize MCP integration over CLI
- Simplified command descriptions for clarity
- Moved quickstart section below agent integration in README
- Capitalized project name in README title

### Fixed
- Added remaining medium and low priority gaps

## [0.2.1] - 2026-04-12

### Added
- New demo GIF

### Changed
- Updated documentation

## [0.2.0] - 2026-04-12

### Added
- Smart language-agnostic import summary extraction

## [0.1.9] - 2026-04-12

### Fixed
- Escape Rich markup in table to prevent MarkupError

## [0.1.8] - 2026-04-12

### Added
- `delete` and `edit` commands
- Updated rules and README

## [0.1.7] - 2026-04-12

### Fixed
- show_lines in table for better readability

## [0.1.6] - 2026-04-12

### Fixed
- Sanitize surrogates in import to prevent UnicodeEncodeError

## [0.1.5] - 2026-04-12

### Added
- Importing files instructions in rules and CLI
- Global memory documentation in quickstart
- PDF install option documentation

### Changed
- Synced rules files with CLI commands
- Updated quickstart with all commands

## [0.1.4] - 2026-04-12

### Added
- `rememb import` command (.md/.txt/.pdf files)
- Semantic install option in README

### Changed
- Updated roadmap with coming soon and planned sections

## [0.1.2] - 2026-04-12

### Changed
- sentence-transformers now optional for faster install

## [0.1.0] - 2026-04-12

### Added
- Initial release
- Core storage with JSON persistence
- CLI with 11 commands
- MCP server with 7 tools
- Semantic search with embeddings
