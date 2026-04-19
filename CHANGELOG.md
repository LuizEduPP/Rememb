# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
