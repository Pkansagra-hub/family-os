"""
k1.concierge.adapters.test_memory -- Test adapter for IMemoryPort.

Scripted recall results. No FAISS, no embedding -- pure in-memory for unit tests.
"""

from __future__ import annotations

from typing import Any


class MockMemoryAdapter:
    """Test adapter for IMemoryPort — scripted recall results."""

    def __init__(self, memories: list[dict[str, Any]] | None = None) -> None:
        self._memories: list[dict[str, Any]] = memories or []
        self.recall_calls: list[tuple[str, list[str] | None, int]] = []

    async def recall(
        self,
        query: str,
        memory_types: list[str] | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        self.recall_calls.append((query, memory_types, max_results))
        filtered = self._memories
        if memory_types:
            filtered = [m for m in filtered if m.get("type") in memory_types]
        return filtered[:max_results]

    # -- Test helpers ----------------------------------------------------------

    def seed(self, memories: list[dict[str, Any]]) -> None:
        """Replace all memories."""
        self._memories = list(memories)

    def clear(self) -> None:
        """Clear all memories and call log."""
        self._memories.clear()
        self.recall_calls.clear()
