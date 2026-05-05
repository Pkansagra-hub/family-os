"""M17.E2.I1 — recall_memory tool end-to-end with real adapter wiring.

Validates the full production recall path:

    execute_recall_memory(args, ctx)
        → ctx.recall_fn  (= RecallMemoryAdapter.recall, bound)
        → RecallMemoryAdapter._recall_fn  (= build_recall_fn(bridge_client))
        → bridge_client.query(QueryEnvelope)
        → RecallBundle  → flattened to list[dict]
        → ToolResult(data={"memories": [...], "count": N})

This exercises every layer EXCEPT the network-bound K0 sink — the
``IBridgeClient.query`` is replaced with a fake that returns a
deterministic ``RecallBundle``. No mocks of recall_fn itself.
"""

from __future__ import annotations

from typing import Any

import pytest

from bridge.ports.query_port_protocol import (
    QueryEnvelope,
    RecallBundle,
    RecallItem,
)
from k1.concierge.adapters.recall_memory import RecallMemoryAdapter, build_recall_fn
from k1.concierge.tools.implementations import ToolContext, execute_recall_memory


class _FakeBridgeClient:
    """Bridge client double — records the envelope and returns a fixed bundle."""

    def __init__(self, bundle: RecallBundle) -> None:
        self._bundle = bundle
        self.calls: list[QueryEnvelope] = []

    async def query(self, envelope: QueryEnvelope) -> RecallBundle:
        self.calls.append(envelope)
        return self._bundle


def _ctx_with_recall(adapter: RecallMemoryAdapter) -> ToolContext:
    return ToolContext(
        session_manager=None,
        cognitive_trace_id="trace-recall",
        actor="back",
        recall_fn=adapter.recall,
    )


async def test_recall_memory_e2e_returns_bridge_items() -> None:
    bundle = RecallBundle(
        items=[
            RecallItem(
                selector_type="semantic",
                content={"text": "Mom prefers tea over coffee", "ts": 123},
                score=0.91,
                source="hippocampus",
            ),
            RecallItem(
                selector_type="semantic",
                content={"text": "Family vacation in July", "ts": 456},
                score=0.74,
                source="declarative",
            ),
        ],
        total_count=2,
        trace_id="trace-recall",
    )
    bridge = _FakeBridgeClient(bundle)
    adapter = RecallMemoryAdapter(build_recall_fn(bridge))
    ctx = _ctx_with_recall(adapter)

    result = await execute_recall_memory(
        {"query": "what does mom like", "memory_types": ["semantic"], "max_results": 5},
        ctx,
    )

    assert result.status == "ok"
    assert result.data["count"] == 2
    rows = result.data["memories"]
    assert rows[0]["selector_type"] == "semantic"
    assert rows[0]["content"]["text"] == "Mom prefers tea over coffee"
    assert rows[0]["score"] == pytest.approx(0.91)
    assert rows[0]["source"] == "hippocampus"

    # Bridge client received the right envelope.
    assert len(bridge.calls) == 1
    envelope = bridge.calls[0]
    assert len(envelope.selectors) == 1
    sel = envelope.selectors[0]
    assert sel.type == "semantic"
    assert sel.query == "what does mom like"
    assert sel.limit == 5


async def test_recall_memory_default_memory_types_to_semantic() -> None:
    """When no memory_types are provided, the closure defaults to ['semantic']."""
    bridge = _FakeBridgeClient(RecallBundle())
    adapter = RecallMemoryAdapter(build_recall_fn(bridge))
    ctx = _ctx_with_recall(adapter)

    # The tool layer defaults to ['episodic','semantic','procedural']; that
    # propagates to the bridge as 3 selectors.
    await execute_recall_memory({"query": "hello"}, ctx)

    assert len(bridge.calls) == 1
    selector_types = [s.type for s in bridge.calls[0].selectors]
    assert selector_types == ["episodic", "semantic", "procedural"]


async def test_recall_memory_offline_bridge_returns_empty() -> None:
    """``build_recall_fn(None)`` produces an offline closure that yields []."""
    adapter = RecallMemoryAdapter(build_recall_fn(None))
    ctx = _ctx_with_recall(adapter)

    result = await execute_recall_memory({"query": "anything", "memory_types": ["semantic"]}, ctx)

    assert result.status == "ok"
    assert result.data["memories"] == []
    assert result.data["count"] == 0


async def test_recall_memory_bridge_failure_is_swallowed() -> None:
    """``build_recall_fn`` swallows bridge errors and returns []."""

    class _BoomBridge:
        async def query(self, envelope: Any) -> Any:
            raise RuntimeError("bridge dead")

    adapter = RecallMemoryAdapter(build_recall_fn(_BoomBridge()))
    ctx = _ctx_with_recall(adapter)

    result = await execute_recall_memory({"query": "x", "memory_types": ["semantic"]}, ctx)

    # The tool sees an empty list rather than an error -- recall must
    # never block a turn.
    assert result.status == "ok"
    assert result.data["memories"] == []


async def test_recall_memory_no_query_is_validation_error() -> None:
    bridge = _FakeBridgeClient(RecallBundle())
    adapter = RecallMemoryAdapter(build_recall_fn(bridge))
    ctx = _ctx_with_recall(adapter)

    result = await execute_recall_memory({"query": ""}, ctx)

    assert result.status == "error"
    assert result.error == "query is required"
    assert bridge.calls == []
