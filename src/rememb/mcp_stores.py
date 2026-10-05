"""MCP multi-store registry: global (~/.rememb) plus optional project stores."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rememb.config import REMEMB_DIR
from rememb.exceptions import RemembError, RemembNotInitializedError
from rememb.store import init
from rememb.utils import global_root, is_initialized


GLOBAL_STORE_ID = "global"


@dataclass(frozen=True)
class McpStore:
    id: str
    root: Path
    kind: str
    label: str


def normalize_project_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.name == REMEMB_DIR:
        resolved = resolved.parent
    return resolved


def _slug_store_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-_")
    return slug or "project"


def _unique_store_id(base: str, used: set[str]) -> str:
    candidate = base
    if candidate == GLOBAL_STORE_ID:
        candidate = f"project-{candidate}"
    index = 2
    while candidate in used:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


class StoreRegistry:
    def __init__(self) -> None:
        self._stores: dict[str, McpStore] = {}
        self._configured = False

    @property
    def configured(self) -> bool:
        return self._configured

    def configure(self, projects: list[Path] | None = None) -> None:
        stores: dict[str, McpStore] = {
            GLOBAL_STORE_ID: McpStore(
                id=GLOBAL_STORE_ID,
                root=global_root(),
                kind="global",
                label="global",
            )
        }
        used_ids = {GLOBAL_STORE_ID}
        seen_roots = {stores[GLOBAL_STORE_ID].root.resolve()}

        for raw in projects or []:
            root = normalize_project_root(Path(raw))
            if root in seen_roots:
                continue
            if root == global_root().resolve():
                continue
            store_id = _unique_store_id(_slug_store_id(root.name), used_ids)
            used_ids.add(store_id)
            seen_roots.add(root)
            stores[store_id] = McpStore(
                id=store_id,
                root=root,
                kind="project",
                label=root.name,
            )

        self._stores = stores
        self._configured = True

    def ensure_configured(self) -> None:
        if not self._configured:
            self.configure([])

    def get(self, store_id: str | None) -> McpStore:
        self.ensure_configured()
        sid = (store_id or GLOBAL_STORE_ID).strip() or GLOBAL_STORE_ID
        store = self._stores.get(sid)
        if store is None:
            known = ", ".join(self.ids())
            raise RemembError(f"Unknown store '{sid}'. Known stores: {known}")
        return store

    def ids(self) -> list[str]:
        self.ensure_configured()
        return list(self._stores.keys())

    def all(self) -> list[McpStore]:
        self.ensure_configured()
        return list(self._stores.values())

    def __len__(self) -> int:
        self.ensure_configured()
        return len(self._stores)


def ensure_store_root(store: McpStore) -> Path:
    root = store.root
    if store.kind == "global":
        if not is_initialized(root):
            init(root, project_name="global", global_mode=True)
        if not is_initialized(root):
            raise RemembNotInitializedError("Global rememb not initialized.")
        return root

    if not root.exists():
        raise RemembError(f"Project store '{store.id}' path does not exist: {root}")
    if not root.is_dir():
        raise RemembError(f"Project store '{store.id}' path is not a directory: {root}")
    if not is_initialized(root):
        init(root, project_name=root.name, global_mode=False)
    if not is_initialized(root):
        raise RemembNotInitializedError(f"Project rememb not initialized at {root}")
    return root
