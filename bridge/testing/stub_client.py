"""StubBridgeClient — no-op IBridgeClient for unit tests.

P7.6: relocated from ``bridge/client.py`` (production module) to
``bridge/testing/`` so that production code no longer depends on test
fixtures.  Tests should import ``StubBridgeClient`` from
``bridge.testing`` (or directly from this module).
"""

from __future__ import annotations

from typing import Any

from ..core.envelope_builder import CommandEnvelope
from ..core.health import K0AvailabilityStatus, K0HealthSnapshot
from ..ports.obs_port_protocol import FeedbackEnvelope


class StubBridgeClient:
    """No-op bridge client for unit tests.

    Every method succeeds immediately with empty/default values.
    Records calls for assertion.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self._health = K0HealthSnapshot(status=K0AvailabilityStatus.ONLINE)

    def _record(self, method: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((method, args, kwargs))

    async def submit_command(
        self,
        topic: str,
        body: dict[str, Any],
        *,
        schema_uri: str | None = None,
        band: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        self._record(
            "submit_command", topic, body, schema_uri=schema_uri, band=band, trace_id=trace_id
        )

    async def submit_command_batch(self, envelopes: list[CommandEnvelope | dict[str, Any]]) -> None:
        self._record("submit_command_batch", envelopes)

    # MS-3c: ``query`` / ``query_single`` were removed in favour of the
    # typed paired-contract surface (``runtime.query.recall_request_v1``).
    # Tests that need a stub recall surface should attach a minimal
    # async ``request(payload)`` callable to the ``recall_request_v1``
    # attribute below.
    recall_request_v1: Any = None

    # MS-3d: ``subscribe``/``ack``/``close_sse`` removed — SSE is now
    # reachable only through the typed per-contract surface
    # ``runtime.sse.<topic>.subscribe(...)``. Tests that need a stub SSE
    # surface should attach a minimal ``subscribe(handler)`` async context
    # manager to the ``sse`` attribute below.
    sse: Any = None

    async def emit_obs(
        self,
        kind: str,
        body: dict[str, Any],
        *,
        priority: str = "NORMAL",
        trace_id: str | None = None,
    ) -> None:
        self._record("emit_obs", kind, body, priority=priority, trace_id=trace_id)

    async def emit_feedback(self, envelope: FeedbackEnvelope) -> None:
        self._record("emit_feedback", envelope)

    async def execute_connector(
        self,
        adapter_id: str,
        action: str,
        params: dict[str, Any],
        *,
        trace_id: str | None = None,
        timeout_ms: int = 30_000,
    ) -> dict[str, Any]:
        self._record(
            "execute_connector",
            adapter_id,
            action,
            params,
            trace_id=trace_id,
            timeout_ms=timeout_ms,
        )
        return {"stub": True}

    def health(self) -> K0HealthSnapshot:
        return self._health
