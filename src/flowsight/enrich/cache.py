"""Per-function enrichment cache (decision 04).

Keyed by (node_id, code_hash): a code change changes the hash, which invalidates
only that one entry - re-enriched lazily on next view. Stored as a JSON file in
``<project>/.flowsight/enrich-cache.json`` so it survives re-indexing.
"""

from __future__ import annotations

import json
import os
from typing import Any


class EnrichCache:
    def __init__(self, path: str | None = None):
        self.path = path
        self._data: dict[str, dict[str, Any]] = {}  # node_id -> {code_hash, payload}
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def get(self, node_id: str, code_hash: str) -> dict | None:
        entry = self._data.get(node_id)
        if not entry:
            return None
        # hash mismatch = code changed = invalidated
        if entry.get("code_hash") != code_hash:
            return None
        return entry.get("payload")

    def put(self, node_id: str, code_hash: str, payload: dict) -> None:
        self._data[node_id] = {"code_hash": code_hash, "payload": payload}

    def save(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def __len__(self) -> int:
        return len(self._data)
