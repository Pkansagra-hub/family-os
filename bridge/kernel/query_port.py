"""Concrete IKernelQueryPort — Bridge transport to K0 query endpoint.

Implements multi-selector recall queries with per-request error handling
and automatic offline fallback (returns empty RecallBundle).

Issue 3.9.3 (MS-3): Scaffold adapter — transport calls are wired but
K0 query endpoint does not exist yet.  Offline path fully functional.

References:
  - bridge/ports/query_port_protocol.py (IKernelQueryPort)
  - bridge/client.py (IBridgeClient.query / query_single)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..core.transport import HttpTransport
from ..ports.query_port_protocol import QueryEnvelope, RecallBundle, RecallItem, RecallSelector

logger = logging.getLogger(__name__)

# K0 query endpoint (MS-3+: not yet deployed on K0 side)
_QUERY_PATH = "/k0/query.recall"


class KernelQueryPort:
    """Bridge-side query port for recall queries against K0.

    Offline behaviour:
        Returns ``RecallBundle.empty()`` when transport is unavailable
        or K0 returns a non-200 status.  K1 continues with local-only
        context.

    Parameters
    ----------
    transport : HttpTransport
        HTTP client for K0 communication.  Must be opened before use.
    """

    __slots__ = ("_transport",)

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def query(self, envelope: QueryEnvelope) -> RecallBundle:
        """Execute a multi-selector recall query against K0.

        Returns empty bundle on any transport/K0 failure.
        """
        request_body = {
            "selectors": [
                {
                    "type": s.type,
                    "topic": s.topic,
                    "limit": s.limit,
                    "cursor": s.cursor,
                    "after": s.after,
                    "query": s.query,
                }
                for s in envelope.selectors
            ],
            "space_id": envelope.space_id,
            "tenant_id": envelope.tenant_id,
            "max_latency_ms": envelope.max_latency_ms,
            "fail_fast": envelope.fail_fast,
            "trace_id": envelope.trace_id,
        }

        try:
            client = self._transport._ensure_client()
            response = await client.post(
                _QUERY_PATH,
                content=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
        except Exception:
            logger.warning(
                "KernelQueryPort.query: transport error, returning empty bundle",
                exc_info=True,
            )
            return RecallBundle.empty(trace_id=envelope.trace_id)

        if response.status_code != 200:
            logger.warning(
                "KernelQueryPort.query: K0 returned status=%d, returning empty bundle",
                response.status_code,
            )
            return RecallBundle.empty(trace_id=envelope.trace_id)

        try:
            body = response.json()
        except Exception:
            return RecallBundle.empty(trace_id=envelope.trace_id)

        return self._parse_bundle(body, trace_id=envelope.trace_id)

    async def query_single(
        self,
        selector: RecallSelector,
        *,
        trace_id: str = "",
    ) -> RecallBundle:
        """Convenience: query with a single selector."""
        envelope = QueryEnvelope(
            selectors=[selector],
            trace_id=trace_id,
        )
        return await self.query(envelope)

    @staticmethod
    def _parse_bundle(
        body: dict[str, Any] | None,
        *,
        trace_id: str = "",
    ) -> RecallBundle:
        """Parse K0 response body into RecallBundle."""
        if not body:
            return RecallBundle.empty(trace_id=trace_id)

        items = [
            RecallItem(
                selector_type=item.get("selector_type", ""),
                content=item.get("content", {}),
                score=float(item.get("score", 0.0)),
                source=item.get("source", ""),
                cursor=item.get("cursor", ""),
            )
            for item in body.get("items", [])
        ]

        return RecallBundle(
            items=items,
            total_count=int(body.get("total_count", len(items))),
            latency_ms=int(body.get("latency_ms", 0)),
            partial=bool(body.get("partial", False)),
            trace_id=trace_id,
        )
