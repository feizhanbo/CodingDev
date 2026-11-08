"""Bounded result cache. Deliberately performs no filesystem I/O."""

from collections import OrderedDict

from devpilot.tools.context import ToolResult


class ReadFileCache:
    def __init__(self, capacity: int = 16) -> None:
        self.capacity = capacity
        self._cache: OrderedDict[tuple, ToolResult] = OrderedDict()

    def get(self, key: tuple) -> ToolResult | None:
        result = self._cache.get(key)
        if result is not None:
            self._cache.move_to_end(key)
            return result.model_copy(deep=True)
        return None

    def put(self, key: tuple, result: ToolResult) -> None:
        self._cache[key] = result.model_copy(deep=True)
        self._cache.move_to_end(key)
        while len(self._cache) > self.capacity:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()
