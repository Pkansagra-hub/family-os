"""MS-3c — concierge-side typed recall service.

Thin façade over the bridge's typed paired-contract recall surface. Wraps
the generated ``recall.request.v1`` client so concierge call sites
(planner stages, tools, etc.) speak in domain language
(``RecallService(query=runtime.query).recall(...)``) rather than poking
through the bridge runtime / client slots directly.

Per :doc:`docs/architecture/whiteboard_k1/bridge_system_design.md` MS-3c:

* the only legitimate K1 recall path is
  ``runtime.query.recall_request_v1.request(payload) -> RecallResponseV1``
* ``RecallService`` is the one place that knows how to build a
  ``RecallRequestV1`` from the concierge's loosely-typed args.

Failure mode: any underlying transport error is surfaced as an empty
``RecallResponseV1`` so callers don't have to special-case offline /
DEGRADED mode at every call site.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RecallService:
    """Domain-level recall façade backed by the typed ``recall.request.v1`` client.

    Parameters
    ----------
    query:
        Either the ``BridgeRuntime.query`` namespace bag (which exposes a
        ``recall_request_v1`` attribute) or the typed
        ``RecallRequestV1Client`` itself. ``None`` is accepted and yields
        an empty response on every call (offline-graceful).
    """

    __slots__ = ("_client",)

    def __init__(self, query: Any) -> None:
        self._client = self._resolve_client(query)

    @staticmethod
    def _resolve_client(source: Any) -> Any | None:
        if source is None:
            return None
        if hasattr(source, "request") and hasattr(source, "__topic__"):
            return source
        client = getattr(source, "recall_request_v1", None)
        if client is not None and hasattr(client, "request"):
            return client
        return None

    async def recall(
        self,
        prompt: str,
        *,
        space_id: str = "default",
        tenant_id: str | None = None,
        memory_types: list[str] | None = None,
        max_results: int = 5,
        max_latency_ms: int = 250,
        fail_fast: bool = False,
        trace_id: str | None = None,
    ) -> Any:
        """Run a recall request and return the typed ``RecallResponseV1``.

        When no client was bound (offline), returns an empty response so
        callers can branch on ``response.hits`` without try/except noise.
        """
        from bridge._generated.k1.models.recall_request_v1 import (
            RecallRequestV1,
            RecallSelector,
        )
        from bridge._generated.k1.models.recall_request_v1 import Type as SelectorType
        from bridge._generated.k1.models.recall_response_v1 import RecallResponseV1

        if self._client is None:
            return RecallResponseV1(
                hits=[], total=0, latency_ms=0, truncated=False, trace_id=trace_id
            )

        limit = max(1, int(max_results))
        requested_types = memory_types or ["semantic"]

        def _coerce(value: str) -> SelectorType:
            try:
                return SelectorType(value)
            except ValueError:
                return SelectorType.semantic

        selectors = [
            RecallSelector(type=_coerce(t), limit=limit, query=prompt) for t in requested_types
        ]
        payload = RecallRequestV1(
            selectors=selectors,
            space_id=space_id,
            tenant_id=tenant_id,
            max_results=limit,
            max_latency_ms=max_latency_ms,
            fail_fast=fail_fast,
            vector_query=prompt,
            trace_id=trace_id,
        )
        try:
            return await self._client.request(payload)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("RecallService.recall failed: %s", exc, exc_info=False)
            return RecallResponseV1(
                hits=[], total=0, latency_ms=0, truncated=False, trace_id=trace_id
            )


__all__ = ["RecallService"]
