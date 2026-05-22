# MCP Tools

This file documents the public MCP tools defined in src/rememb/mcp_server.py.

## rememb_read

Description: Read all memory entries or filter by section. This is a safe, read-only operation with no side effects. Use it at the start of each session to load context. Prefer rememb_search when you need to find specific information by keyword or topic.

Parameters:

| Name | Type | Required | Default | Allowed values | Description |
|------|------|----------|---------|----------------|-------------|
| section | string | no | - | sections configured in .rememb/config.json | Filters by section |
| summary_only | boolean | no | false | true, false | Renders a compact one-line summary per entry |
| max_chars | integer | no | - | any integer | Maximum number of content characters to include per entry |

## rememb_read_page

Description: Read a paginated slice of entries with server-side truncation. This is better for browsing large stores without flooding the context window.

Parameters:

| Name | Type | Required | Default | Allowed values | Description |
|------|------|----------|---------|----------------|-------------|
| section | string | no | - | sections configured in .rememb/config.json | Optional section filter |
| tag | string | no | - | any string | Optional exact tag filter applied before pagination |
| offset | integer | no | 0 | integer >= 0 | Zero-based page offset |
| limit | integer | no | 100 | integer > 0 | Maximum number of entries to return |
| sort_by | string | no | storage | storage, recent | Sort order used before pagination |
| descending | boolean | no | false | true, false | Reverses the selected order |
| summary_only | boolean | no | true | true, false | Renders a compact one-line summary per entry |
| max_chars | integer | no | - | any integer | Maximum number of content characters to include per entry |

## rememb_search

Description: Search memory entries by content or tags using semantic similarity. This is a safe, read-only operation with no side effects. Use it instead of rememb_read when you need to find specific entries by topic rather than loading everything. It returns the top_k most relevant results ranked by similarity.

Parameters:

| Name | Type | Required | Default | Allowed values | Description |
|------|------|----------|---------|----------------|-------------|
| query | string | yes | - | any string | Search query in natural language or keywords |
| section | string | no | - | sections configured in .rememb/config.json | Optional section filter |
| tag | string | no | - | any string | Optional exact tag filter applied before semantic search |
| top_k | integer | no | 5 | integer > 0 | Maximum number of results |
| summary_only | boolean | no | true | true, false | Renders a compact one-line summary per entry |
| max_chars | integer | no | - | any integer | Maximum number of content characters to include per entry |

## rememb_write

Description: Save a new memory entry. It creates a new entry and returns its ID without overwriting existing entries. Use it when you learn something new worth persisting across sessions. Use rememb_edit to update an existing entry by ID. semantic_scope controls whether semantic duplicate checks run globally or only inside the target section.

Parameters:

| Name | Type | Required | Default | Allowed values | Description |
|------|------|----------|---------|----------------|-------------|
| content | string | yes | - | any string | Content to remember, typically 1 to 3 sentences |
| section | string | no | context | sections configured in .rememb/config.json | Target section |
| tags | array[string] | no | - | list of strings | Tags used to categorize the entry |
| semantic_scope | string | no | global | global, section | Scope of semantic duplicate protection |

## rememb_edit

Description: Update an existing memory entry in place by ID. It modifies only the fields you provide, such as content, section, or tags; omitted fields stay unchanged. This is non-destructive: the entry is updated, not deleted and recreated. Use rememb_write to create new entries and rememb_delete to permanently remove one.

Parameters:

| Name | Type | Required | Default | Allowed values | Description |
|------|------|----------|---------|----------------|-------------|
| entry_id | string | yes | - | 8 hexadecimal characters | Entry ID |
| content | string | no | - | any string | New content |
| section | string | no | - | sections configured in .rememb/config.json | Moves the entry to a different section |
| tags | array[string] | no | - | list of strings | Replaces the tags |

## rememb_delete

Description: Permanently delete a single memory entry by ID. Deletion is irreversible and the entry cannot be recovered. There are no cascading side effects. Use rememb_edit to update an entry and rememb_clear to delete all entries at once.

Parameters:

| Name | Type | Required | Default | Allowed values | Description |
|------|------|----------|---------|----------------|-------------|
| entry_id | string | yes | - | 8 hexadecimal characters | Entry ID to remove |

## rememb_clear

Description: Permanently delete ALL memory entries at once. This is irreversible and there is no recovery after the operation. It requires confirm=true as a safety guard. Use rememb_delete to remove a single entry by ID instead. Use it only to fully reset the store.

Parameters:

| Name | Type | Required | Default | Allowed values | Description |
|------|------|----------|---------|----------------|-------------|
| confirm | boolean | yes | - | true | Must be true to confirm deletion |

## rememb_stats

Description: Return memory usage statistics, including total entries, size in KB, oldest entry, newest entry, and count by section. This is a safe, read-only operation with no side effects. Use it to get an overview of the store or decide whether cleanup is needed.

Parameters: none.

## rememb_consolidate

Description: Consolidate duplicate entries and merge metadata such as tags and access data. It supports exact mode, which is the default and uses normalized content comparison, and semantic mode, which uses a cosine similarity threshold. This operation mutates the store by removing redundant entries and keeping one consolidated record per duplicate group.

Parameters:

| Name | Type | Required | Default | Allowed values | Description |
|------|------|----------|---------|----------------|-------------|
| section | string | no | - | sections configured in .rememb/config.json | Optional section filter |
| mode | string | no | exact | exact, semantic | Consolidation mode |
| similarity_threshold | number | no | 0.88 | number > 0 and <= 1 | Similarity threshold used in semantic mode |

## rememb_init

Description: Initialize rememb memory storage. It is useful for explicit setup and recovery flows. Home-first resolution also auto-initializes ~/.rememb when needed, and this tool remains idempotent and safe to call repeatedly.

Parameters:

| Name | Type | Required | Default | Allowed values | Description |
|------|------|----------|---------|----------------|-------------|
| project_name | string | no | - | any string | Optional project name |

## rememb_list_skills

Description: List bundled rememb skills discovered from the installed package contents. This is a safe, read-only operation.

Parameters: none.

## rememb_use_skill

Description: Load one bundled rememb skill by identifier or exact declared name and return its instructions. This is a safe, read-only operation. Use rememb_list_skills first to inspect available skills.

Parameters:

| Name | Type | Required | Default | Allowed values | Description |
|------|------|----------|---------|----------------|-------------|
| skill | string | yes | - | skill identifier or exact name | Skill identifier, usually the directory name, or the exact declared name |