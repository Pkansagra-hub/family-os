"""
C1 Issue 3.6 — Memory adapter behavioural tests.

Covers MockMemoryAdapter + RecallMemoryAdapter behaviour.
"""

from __future__ import annotations

import asyncio

# ===================================================================
# MockMemoryAdapter
# ===================================================================


class TestMockMemoryAdapterBehaviour:
    def test_recall_empty(self) -> None:
        from k1.concierge.adapters.test_memory import MockMemoryAdapter

        adapter = MockMemoryAdapter()
        result = asyncio.run(adapter.recall("anything"))
        assert result == []

    def test_recall_returns_seeded(self) -> None:
        from k1.concierge.adapters.test_memory import MockMemoryAdapter

        memories = [
            {"type": "fact", "content": "sky is blue", "tags": ["sky"]},
            {"type": "event", "content": "birthday", "tags": ["family"]},
        ]
        adapter = MockMemoryAdapter(memories=memories)
        result = asyncio.run(adapter.recall("query"))
        assert len(result) == 2

    def test_recall_filters_by_type(self) -> None:
        from k1.concierge.adapters.test_memory import MockMemoryAdapter

        memories = [
            {"type": "fact", "content": "sky is blue"},
            {"type": "event", "content": "birthday"},
        ]
        adapter = MockMemoryAdapter(memories=memories)
        result = asyncio.run(
            adapter.recall("query", memory_types=["fact"])
        )
        assert len(result) == 1
        assert result[0]["type"] == "fact"

    def test_recall_max_results(self) -> None:
        from k1.concierge.adapters.test_memory import MockMemoryAdapter

        memories = [{"type": "fact", "content": f"item {i}"} for i in range(10)]
        adapter = MockMemoryAdapter(memories=memories)
        result = asyncio.run(adapter.recall("query", max_results=3))
        assert len(result) == 3

    def test_recall_records_calls(self) -> None:
        from k1.concierge.adapters.test_memory import MockMemoryAdapter

        adapter = MockMemoryAdapter()
        asyncio.run(
            adapter.recall("q", memory_types=["fact"], max_results=2)
        )
        assert len(adapter.recall_calls) == 1
        assert adapter.recall_calls[0] == ("q", ["fact"], 2)


# ===================================================================
# RecallMemoryAdapter (production)
# ===================================================================


class TestRecallMemoryAdapterBehaviour:
    def test_delegates_to_closure(self) -> None:
        from k1.concierge.adapters.recall_memory import RecallMemoryAdapter

        calls: list = []

        async def tracked_recall(query, memory_types=None, max_results=5):
            calls.append((query, memory_types, max_results))
            return [{"type": "fact", "content": "result"}]

        adapter = RecallMemoryAdapter(tracked_recall)
        result = asyncio.run(adapter.recall("test query"))
        assert len(calls) == 1
        assert calls[0][0] == "test query"
        assert len(result) == 1

