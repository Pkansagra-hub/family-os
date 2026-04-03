"""
k1.concierge.adapters.recall_memory -- Production adapter for IMemoryPort.

Wraps the recall_fn closure built by _build_recall_fn() in bootstrap.py.
Converts the bare Callable into the IMemoryPort Protocol surface.
"""

from __future__ import annotations

from typing import Any, Callable


class RecallMemoryAdapter:
    """Production adapter for IMemoryPort — wraps the recall_fn closure.

    bootstrap._build_recall_fn() returns:
        async def _recall_memory(query, memory_types=None, max_results=5) -> list[dict]

    This adapter exposes that closure as the IMemoryPort.recall() method.
    """

    def __init__(self, recall_fn: Callable[..., Any]) -> None:
        self._recall_fn = recall_fn

    async def recall(
        self,
        query: str,
        memory_types: list[str] | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        return await self._recall_fn(query, memory_types=memory_types, max_results=max_results)
