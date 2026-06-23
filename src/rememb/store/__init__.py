from __future__ import annotations

from rememb.helpers import MemoryStore, _store_context

from rememb.store.crud import (
    agent_summarize_hint,
    clear_entries,
    consolidate_entries,
    delete_entries,
    delete_entry,
    diff_entry_versions,
    edit_entries,
    edit_entry,
    format_entries,
    get_config,
    get_stats,
    init,
    list_entry_versions,
    read_entries,
    read_entries_page,
    restore_deleted_entry,
    restore_entry_version,
    search_entries,
    update_config,
    write_entries,
    write_entry,
)

__all__ = [
    "init",
    "get_config",
    "update_config",
    "write_entry",
    "write_entries",
    "consolidate_entries",
    "read_entries",
    "read_entries_page",
    "search_entries",
    "delete_entry",
    "delete_entries",
    "list_entry_versions",
    "restore_entry_version",
    "diff_entry_versions",
    "restore_deleted_entry",
    "edit_entry",
    "edit_entries",
    "clear_entries",
    "format_entries",
    "agent_summarize_hint",
    "get_stats",
]

_store_instance = type('StoreModule', (), {
    'get_config': get_config,
    'update_config': update_config,
    'write_entry': write_entry,
    'write_entries': write_entries,
    'consolidate_entries': consolidate_entries,
    'read_entries': read_entries,
    'read_entries_page': read_entries_page,
    'search_entries': search_entries,
    'delete_entry': delete_entry,
    'delete_entries': delete_entries,
    'edit_entry': edit_entry,
    'edit_entries': edit_entries,
    'clear_entries': clear_entries,
})()
assert isinstance(_store_instance, MemoryStore), "store.py must implement MemoryStore Protocol"
