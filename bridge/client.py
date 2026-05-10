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
from typing import Any, Protocol, runtime_checkable

from .core.envelope_builder import CommandEnvelope
from .core.health import DegradedModeManager, K0HealthChecker, K0HealthSnapshot
from .ports.obs_port_protocol import FeedbackEnvelope

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
    #
    # MS-3c: the legacy hand-written ``query`` / ``query_single`` Protocol
    # methods (and their ``QueryEnvelope`` / ``RecallBundle`` types) were
    # deleted in favour of the typed paired-contract surface exposed by
    # ``BridgeRuntime.query.recall_request_v1.request(...)``. Callers reach
    # through ``runtime.query`` directly; the bridge client no longer
    # carries a hand-rolled query facade.

    # -- SSE (K0 → K1 streaming) -------------------------------------------
    #
    # MS-3d: the legacy hand-written ``subscribe`` / ``ack`` / ``close_sse``
    # Protocol methods (and their ``SSETraceEvent`` type) were removed in
    # favour of the typed per-contract subscriber surface exposed by
    # ``BridgeRuntime.sse.<topic>.subscribe(handler)``. Callers reach
    # through ``runtime.sse`` directly; the bridge client no longer
    # carries a hand-rolled SSE facade.

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
      Query    → not exposed here; recall is request/response and lives
                 on the typed paired-contract surface
                 ``runtime.query.recall_request_v1`` instead. ``recall``
                 attribute is set to ``None`` so adapter wiring can
                 detect the offline case and yield an empty bundle.
      SSE      → not exposed here; subscription lives on the typed
                 per-contract surface
                 ``runtime.sse.<topic>.subscribe(...)``. Offline
                 subscribers detect the absent surface and yield no
                 events themselves (MS-3d).
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

    def is_connected(self) -> bool:
        """Always False — SinkBridgeClient is the offline/outbox implementation."""
        return False

    def connect(self) -> None:  # noqa: D401
        """No-op — SinkBridgeClient queues commands to LocalOutbox; no live K0 TCP.\n\n        Callers (e.g. BridgeConnectionAdapter._probe_connection) will see
        ``is_connected() == False`` and correctly mark the bridge as offline.
        """
        logger.warning(
            "SinkBridgeClient.connect() called — bridge is OFFLINE (outbox mode)."
            " Live K0 requires HttpBridgeClient via BridgeRuntime.from_registry()."
        )

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

    # MS-3c: ``query``/``query_single`` removed — recall is now reachable
    # only through the typed paired-contract surface
    # ``runtime.query.recall_request_v1.request(...)``. Offline callers
    # detect the missing surface and return an empty list themselves.
    recall_request_v1: Any = None

    # MS-3d: ``subscribe``/``ack``/``close_sse`` removed — SSE is now
    # reachable only through the typed per-contract surface
    # ``runtime.sse.<topic>.subscribe(...)``. Offline callers detect the
    # missing surface and yield no events themselves.
    sse: Any = None

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
# HttpBridgeClient (MS-3a — real HTTP, contract-bound)
# ---------------------------------------------------------------------------


_RUNTIME_CONSTRUCTION_TOKEN: object = object()
"""Sentinel that ``BridgeRuntime.from_registry`` passes when constructing
:class:`HttpBridgeClient`. Direct callers cannot fabricate this value
(it is a private module-level object), so the class enforces "constructed
via the runtime" at runtime *and* via the
``bridge_client_construction_via_runtime_only`` CI gate at build-time
(belt-and-braces per the bridge implementation plan §3a.1)."""


class HttpBridgeClient:
    """Real-HTTP composite bridge client — contract-bound port surface.

    MS-3a wires the **command** slot (currently exposing the generated
    ``memory_write_v1`` client). Subsequent milestones populate the
    remaining slots:

    * ``query`` — MS-3b query port surface
    * ``sse`` — MS-3b SSE port surface
    * ``obs`` — MS-3b observability port surface
    * ``gateway`` — MS-3c connector gateway

    The ``memory_write_v1`` slot is exposed at the top level (not nested
    under ``command``) so callers can write
    ``client.memory_write_v1.publish(payload)`` — the natural shape that
    falls out of per-contract code generation.

    Construction is restricted to :meth:`BridgeRuntime.from_registry`
    via the ``_runtime_token`` sentinel. The matching CI gate
    ``bridge_client_construction_via_runtime_only`` AST-walks ``bridge/``,
    ``k0/``, and ``k1/`` (excluding this module + ``bridge/runtime.py``)
    and fails the build on any direct ``HttpBridgeClient(...)`` call.
    """

    __slots__ = (
        "memory_write_v1",
        "recall_request_v1",
        "query",
        "sse",
        "obs",
        "gateway",
    )

    def __init__(
        self,
        *,
        _runtime_token: object,
        memory_write_v1: Any = None,
        recall_request_v1: Any = None,
        query: Any = None,
        sse: Any = None,
        obs: Any = None,
        gateway: Any = None,
    ) -> None:
        if _runtime_token is not _RUNTIME_CONSTRUCTION_TOKEN:
            raise RuntimeError(
                "HttpBridgeClient may only be constructed via "
                "BridgeRuntime.from_registry(). Direct construction is "
                "rejected at runtime and by the "
                "bridge_client_construction_via_runtime_only CI gate."
            )
        self.memory_write_v1 = memory_write_v1
        self.recall_request_v1 = recall_request_v1
        self.query = query
        self.sse = sse
        self.obs = obs
        self.gateway = gateway

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        slots = [s for s in self.__slots__ if getattr(self, s) is not None]
        return f"HttpBridgeClient(active_slots={slots})"


# ---------------------------------------------------------------------------
# Public factory - MS-3b Epic 3b.5
# ---------------------------------------------------------------------------


def create_sink_bridge_client(outbox_path: Any) -> "SinkBridgeClient":
    """Construct a fully wired offline ``SinkBridgeClient``.

    Used by the kernel ``SinkBridgeAdapter`` so it never has to import
    ``bridge.sync.local_outbox`` directly. The seam keeps the
    bridge/kernel wall (enforced by
    ``tooling.ci.gates.bridge_not_imported_from_kernels``) intact: the
    kernel depends only on the public ``bridge.client`` module.

    Parameters
    ----------
    outbox_path:
        Path-like to the SQLite outbox database file.

    Returns
    -------
    SinkBridgeClient
        Ready-to-use client backed by a fresh ``LocalOutbox`` instance.
    """
    from .sync.local_outbox import LocalOutbox

    return SinkBridgeClient(outbox=LocalOutbox(db_path=outbox_path))
