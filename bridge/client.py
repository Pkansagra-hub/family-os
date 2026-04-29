"""Bridge client facade — unified interface to all K1↔K0 bridge ports.

E-2.9: IBridgeClient Protocol + concrete production implementation:

  SinkBridgeClient — queues commands to LocalOutbox, empty recall,
                     empty SSE, drops obs.  Used when K0 is OFFLINE
                     until a real HTTP client is wired (MS-3+).

Note (P7.6): ``StubBridgeClient`` was relocated to
``bridge/testing/stub_client.py``.  Test code should import it from
``bridge.testing`` rather than this module.

Design:
  IBridgeClient composes the 5 port protocols into a single entry-point
  so the Kernel bootstrap only needs one dependency.

  Each K1 component adapter (Fabric, Planner, Orchestrator, MW) wraps
  IBridgeClient and delegates to the relevant port methods.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from .core.envelope_builder import CommandEnvelope
from .core.health import DegradedModeManager, K0HealthChecker, K0HealthSnapshot
from .ports.obs_port_protocol import FeedbackEnvelope
from .ports.query_port_protocol import QueryEnvelope, RecallBundle, RecallSelector
from .ports.sse_port_protocol import SSETraceEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IBridgeClient protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IBridgeClient(Protocol):
    """Unified facade over all K1↔K0 bridge ports.

    Kernel bootstrap wires a single IBridgeClient, and per-component
    adapters narrow it to their local port Protocol.
    """

    # -- Command (fire-and-forget) -----------------------------------------

    async def submit_command(
        self,
        topic: str,
        body: dict[str, Any],
        *,
        schema_uri: str | None = None,
        band: str | None = None,
        trace_id: str | None = None,
    ) -> None: ...

    async def submit_command_batch(
        self,
        envelopes: list[CommandEnvelope | dict[str, Any]],
    ) -> None: ...

    # -- Query (request / response) ----------------------------------------

    async def query(self, envelope: QueryEnvelope) -> RecallBundle: ...

    async def query_single(
        self,
        selector: RecallSelector,
        *,
        trace_id: str | None = None,
    ) -> RecallBundle: ...

    # -- SSE (K0 → K1 streaming) -------------------------------------------

    async def subscribe(
        self,
        topics: list[str],
        *,
        cursor: str | None = None,
    ) -> AsyncIterator[SSETraceEvent]: ...

    async def ack(self, topic: str, cursor: str) -> None: ...

    async def close_sse(self) -> None: ...

    # -- Observability (K1 → K0 telemetry) ---------------------------------

    async def emit_obs(
        self,
        kind: str,
        body: dict[str, Any],
        *,
        priority: str = "NORMAL",
        trace_id: str | None = None,
    ) -> None: ...

    async def emit_feedback(self, envelope: FeedbackEnvelope) -> None: ...

    # -- Connector Gateway (IFL — MS-3+) -----------------------------------

    async def execute_connector(
        self,
        adapter_id: str,
        action: str,
        params: dict[str, Any],
        *,
        trace_id: str | None = None,
        timeout_ms: int = 30_000,
    ) -> dict[str, Any]: ...

    # -- Health ------------------------------------------------------------

    def health(self) -> K0HealthSnapshot: ...


# ---------------------------------------------------------------------------
# SinkBridgeClient (offline-first / pre-MS-3)
# ---------------------------------------------------------------------------


class SinkBridgeClient:
    """Offline-first bridge client that sinks commands to LocalOutbox.

    Behaviour per port:
      Command  → enqueue to LocalOutbox (deferred delivery)
      Query    → RecallBundle.empty()  (no K0 available)
      SSE      → empty async iterator  (no stream)
      Obs      → drop LOW priority; log NORMAL/HIGH
      IFL      → NotImplementedError   (MS-3)

    Parameters:
        outbox: LocalOutbox instance for command queueing.
        health_checker: K0HealthChecker for status tracking.
        degraded_manager: DegradedModeManager for policy decisions.
    """

    def __init__(
        self,
        outbox: Any,  # LocalOutbox (avoid circular import)
        health_checker: K0HealthChecker | None = None,
        degraded_manager: DegradedModeManager | None = None,
    ) -> None:
        self._outbox = outbox
        self._health_checker = health_checker or K0HealthChecker()
        self._degraded = degraded_manager or DegradedModeManager(self._health_checker)
        # Force OFFLINE since Sink is the offline implementation
        self._health_checker.force_offline("SinkBridgeClient: K0 not connected")

    async def submit_command(
        self,
        topic: str,
        body: dict[str, Any],
        *,
        schema_uri: str | None = None,
        band: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Queue command to LocalOutbox for deferred delivery."""
        import json

        envelope = {
            "topic": topic,
            "body": body,
            "schema_uri": schema_uri,
            "band": band,
            "trace_id": trace_id or uuid.uuid4().hex,
        }
        envelope_json = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
        self._outbox.enqueue(
            envelope_json=envelope_json,
            topic=topic,
            priority=0,
        )
        logger.debug("SinkBridgeClient: enqueued command topic=%s", topic)

    async def submit_command_batch(self, envelopes: list[CommandEnvelope | dict[str, Any]]) -> None:
        """Queue each envelope individually."""
        for env in envelopes:
            if isinstance(env, CommandEnvelope):
                await self.submit_command(
                    topic=env.topic,
                    body=env.body,
                    schema_uri=env.schema_uri,
                    band=env.band,
                    trace_id=env.trace_id,
                )
                continue
            await self.submit_command(
                topic=env.get("topic", "unknown"),
                body=env.get("body", {}),
                schema_uri=env.get("schema_uri"),
                band=env.get("band"),
                trace_id=env.get("trace_id"),
            )

    async def query(self, envelope: QueryEnvelope) -> RecallBundle:
        """Return empty recall — K0 not available."""
        logger.debug("SinkBridgeClient: query → empty (offline)")
        return RecallBundle.empty()

    async def query_single(
        self,
        selector: RecallSelector,
        *,
        trace_id: str | None = None,
    ) -> RecallBundle:
        """Return empty recall — K0 not available."""
        return RecallBundle.empty()

    async def subscribe(
        self,
        topics: list[str],
        *,
        cursor: str | None = None,
    ) -> AsyncIterator[SSETraceEvent]:
        """Return empty stream — no SSE connection."""
        logger.debug("SinkBridgeClient: subscribe → empty stream (offline)")
        return _empty_async_iter()

    async def ack(self, topic: str, cursor: str) -> None:
        """No-op — nothing to acknowledge."""

    async def close_sse(self) -> None:
        """No-op — no stream to close."""

    async def emit_obs(
        self,
        kind: str,
        body: dict[str, Any],
        *,
        priority: str = "NORMAL",
        trace_id: str | None = None,
    ) -> None:
        """Drop LOW priority; log NORMAL/HIGH for later replay."""
        if self._degraded.should_drop_obs(priority):
            return
        logger.info(
            "SinkBridgeClient: obs %s/%s dropped (offline, no telemetry sink)",
            kind,
            priority,
        )

    async def emit_feedback(self, envelope: FeedbackEnvelope) -> None:
        """Drop feedback — no telemetry sink."""
        logger.debug("SinkBridgeClient: feedback dropped (offline)")

    async def execute_connector(
        self,
        adapter_id: str,
        action: str,
        params: dict[str, Any],
        *,
        trace_id: str | None = None,
        timeout_ms: int = 30_000,
    ) -> dict[str, Any]:
        """IFL not available until MS-3."""
        raise NotImplementedError("IFL connector gateway: MS-3")

    def health(self) -> K0HealthSnapshot:
        """Return current health snapshot."""
        return self._health_checker.snapshot


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _empty_async_iter() -> AsyncIterator[SSETraceEvent]:
    """Yield nothing — empty async iterator for SSE stubs."""
    return
    yield  # noqa: E, RET504 — makes this an async generator
