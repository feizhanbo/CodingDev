"""Cache for read_file results to avoid re-reading unchanged files."""

from __future__ import annotations

import hashlib
from pathlib import Path

from devpilot.tools.context import ToolResult


class ReadFileCache:
    """Caches read_file results by path+range+content_hash."""

    def __init__(self) -> None:
        self._cache: dict[str, ToolResult] = {}

    @staticmethod
    def _make_key(
        path: str,
        start_line: int | None,
        end_line: int | None,
        content_hash: str,
    ) -> str:
        return f"{path}:{start_line or 0}:{end_line or 0}:{content_hash}"

    def get(
        self,
        path: str,
        start_line: int | None,
        end_line: int | None,
    ) -> ToolResult | None:
        """Get cached result if file content hasn't changed."""
        p = Path(path)
        if not p.exists():
            return None
        current_hash = hashlib.md5(p.read_bytes()).hexdigest()
        key = self._make_key(path, start_line, end_line, current_hash)
        return self._cache.get(key)

    def put(
        self,
        path: str,
        start_line: int | None,
        end_line: int | None,
        result: ToolResult,
    ) -> None:
        """Cache a read_file result keyed by content hash."""
        p = Path(path)
        if p.exists():
            content_hash = hashlib.md5(p.read_bytes()).hexdigest()
            key = self._make_key(path, start_line, end_line, content_hash)
            self._cache[key] = result

    def invalidate(self, path: str) -> None:
        """Invalidate all cache entries for a given path (after patch)."""
        prefix = f"{path}:"
        keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del self._cache[k]

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
