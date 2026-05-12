"""
k1.concierge.adapters.recall_memory -- Production adapter for IMemoryPort.

Wraps the recall_fn closure built by ``build_recall_fn()`` (P5.2) into the
``IMemoryPort`` Protocol surface.

MS-3c: the closure now talks to K0 through the typed paired-contract
surface ``runtime.query.recall_request_v1`` (or, equivalently, the
``recall_request_v1`` slot on :class:`bridge.client.HttpBridgeClient`).
The legacy hand-written ``QueryEnvelope`` / ``RecallBundle`` shape that
previously lived under ``bridge.ports.query_port_protocol`` was deleted
in MS-3c.2; this adapter is the single seam where the contract-bound
recall response is flattened back into the ``list[dict]`` shape that
concierge tools consume.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RecallMemoryAdapter:
    """Production adapter for IMemoryPort -- wraps the recall_fn closure.

    ``build_recall_fn(...)`` returns:
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


def _resolve_recall_client(source: Any) -> Any | None:
    """Pull the typed ``recall.request.v1`` client out of a recall source.

    Accepted shapes (checked in order):

    * ``None``                                          -> offline
    * a typed client (has ``request`` + ``__topic__``)  -> used directly
    * an :class:`bridge.client.HttpBridgeClient`        -> ``.recall_request_v1``
    * a :class:`bridge.runtime.BridgeRuntime` instance  -> ``.query.recall_request_v1``

    Returns ``None`` when no recall surface is reachable; the caller
    short-circuits to an empty list in that case (offline-graceful).
    """
    if source is None:
        return None
    # Direct typed client.
    if hasattr(source, "request") and hasattr(source, "__topic__"):
        return source
    # HttpBridgeClient slot.
    client = getattr(source, "recall_request_v1", None)
    if client is not None and hasattr(client, "request"):
        return client
    # BridgeRuntime.query namespace bag.
    query_bag = getattr(source, "query", None)
    if query_bag is not None:
        client = getattr(query_bag, "recall_request_v1", None)
        if client is not None and hasattr(client, "request"):
            return client
    return None


def _hits_to_dicts(hits: Any) -> list[dict[str, Any]]:
    """Flatten ``RecallResponseV1.hits`` into the shape concierge tools expect."""
    out: list[dict[str, Any]] = []
    for hit in hits or []:
        if isinstance(hit, dict):
            content = hit.get("content", {})
            score = hit.get("score", 0.0)
            source = hit.get("source", "k0")
            selector_type = hit.get("selector_type")
        else:
            content = getattr(hit, "content", {})
            score = getattr(hit, "score", 0.0)
            source = getattr(hit, "source", "k0")
            selector_type = getattr(hit, "selector_type", None)
        out.append(
            {
                "selector_type": selector_type or "semantic",
                "content": dict(content) if isinstance(content, dict) else {"value": content},
                "score": float(score or 0.0),
                "source": str(source or "k0"),
            }
        )
    return out


def build_recall_fn(
    recall_source: Any | None,
    *,
    space_id: str = "default",
) -> Callable[..., Any]:
    """P5.2 / MS-3c: Build a recall closure that talks to K0 through the
    typed ``recall.request.v1`` paired contract.

    Args:
        recall_source: One of

            * ``None`` -- offline mode; closure always returns ``[]``.
            * ``HttpBridgeClient`` -- composite client whose
              ``recall_request_v1`` slot carries the typed client.
            * ``BridgeRuntime`` -- runtime whose ``query.recall_request_v1``
              attribute carries the typed client.
            * The typed ``RecallRequestV1Client`` itself.

            Anything that is not a recognised recall surface is treated
            as offline (returns ``[]``).
        space_id: Tenant space identifier passed into every
            ``RecallRequestV1`` payload. K0 filters its WAL / index by this
            field, so the value must match the space under which atoms
            were written (e.g. ``family:smith``) or recall returns no
            hits. Defaults to ``"default"`` so unit tests with synthetic
            bridges keep working.

    Returns:
        ``async def _recall(query, memory_types, max_results) -> list[dict]``

    Failure mode: any exception (bridge unavailable, malformed response,
    etc.) is logged and surfaced as an empty list -- the recall path
    must never block a turn.
    """

    recall_client = _resolve_recall_client(recall_source)
    target_space = space_id or "default"

    async def _recall(
        query: str,
        memory_types: list[str] | None = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        if recall_client is None:
            return []
        try:
            from bridge._generated.k1.models.recall_request_v1 import (
                RecallRequestV1,
                RecallSelector,
            )
            from bridge._generated.k1.models.recall_request_v1 import Type as SelectorType

            limit = max(1, int(max_results))
            requested_types = memory_types or ["semantic"]

            def _coerce_type(value: str) -> SelectorType:
                try:
                    return SelectorType(value)
                except ValueError:
                    # ``procedural`` (and any other non-enum value) maps
                    # to ``semantic`` so the LLM's default tool-call
                    # (episodic+semantic+procedural) still produces a
                    # well-formed K0 recall request.
                    return SelectorType.semantic

            selectors = [
                RecallSelector(type=_coerce_type(t), limit=limit, query=query)
                for t in requested_types
            ]
            payload = RecallRequestV1(
                selectors=selectors,
                space_id=target_space,
                max_results=limit,
                vector_query=query,
            )
            response = await recall_client.request(payload)
            return _hits_to_dicts(getattr(response, "hits", []))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("recall_memory closure failed: %s", exc, exc_info=False)
            return []

    return _recall
