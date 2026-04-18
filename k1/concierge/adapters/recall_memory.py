"""
k1.concierge.adapters.recall_memory -- Production adapter for IMemoryPort.

Wraps the recall_fn closure built by ``build_recall_fn()`` (P5.2) into the
``IMemoryPort`` Protocol surface.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RecallMemoryAdapter:
    """Production adapter for IMemoryPort — wraps the recall_fn closure.

    ``build_recall_fn(bridge_client)`` returns:
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


def build_recall_fn(bridge_client: Any | None) -> Callable[..., Any]:
    """P5.2: Build a recall closure that talks to K0 via the Bridge client.

    Args:
        bridge_client: A ``SinkBridgeClient`` (or any object with an
            ``async query(envelope) -> RecallBundle`` method). If ``None``,
            the returned closure always yields ``[]`` (offline mode).

    Returns:
        ``async def _recall(query, memory_types, max_results) -> list[dict]``

    Mapping:
        ``memory_types`` → one ``RecallSelector`` per type (defaults to a
        single ``"semantic"`` selector). ``query`` is forwarded as the
        selector ``query`` text. Returned ``RecallItem`` instances are
        flattened into plain dicts so tools can consume them without
        importing bridge contracts.

    Failure mode: any exception (bridge unavailable, malformed bundle, etc.)
    is logged and surfaced as an empty list — the recall path must never
    block a turn.
    """

    async def _recall(
        query: str,
        memory_types: list[str] | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        if bridge_client is None:
            return []
        try:
            from bridge.ports.query_port_protocol import QueryEnvelope, RecallSelector

            types = memory_types or ["semantic"]
            selectors = [
                RecallSelector(type=t, limit=max(1, int(max_results)), query=query) for t in types
            ]
            envelope = QueryEnvelope(selectors=selectors)
            bundle = await bridge_client.query(envelope)
            return [
                {
                    "selector_type": item.selector_type,
                    "content": dict(item.content),
                    "score": float(item.score),
                    "source": item.source,
                }
                for item in (bundle.items or [])
            ]
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("recall_memory closure failed: %s", exc, exc_info=False)
            return []

    return _recall
