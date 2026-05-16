"""k1.kernel.adapters.live_bridge_adapter — LiveBridgeAdapter for real/pseudo K0.

Wraps ``BridgeRuntime.from_registry()`` to obtain the typed ``HttpBridgeClient``
slots (``recall_request_v1``, etc.) and additionally exposes a thin
:class:`LiveBridgeClient` shim that implements the *generic* surface used
elsewhere in the kernel (``submit_command``, ``submit_command_batch``,
``emit_obs``, ``execute_connector``).

This is the S4 bridge adapter used when ``KernelConfig.k0_endpoint`` is set.

Memory-writer end-to-end path
-----------------------------

    MW DeltaAggregator.flush()
      → BatchEmitter.emit(envelopes)
      → BridgeCommandAdapter.submit_batch(envelopes)
      → LiveBridgeClient.submit_command_batch(envelopes)   ← this module
      → HttpTransport.post_command(envelope_bytes)
      → POST {endpoint}/k0/command.submit
      → pseudo-K0 FastAPI ``/k0/command.submit``
      → SQLiteK0Store.write_envelope(...) → WAL row.

Each MW envelope has the shape::

    {"topic": "memory.delta",
     "schema_uri": "schema://memory.delta",
     "body": {...},
     "trace_id": "...",
     "headers": {"space_id": "...", "actor": "...", "tenant_id": "...",
                 "device_id": "...", "band": "GREEN", ...}}

``LiveBridgeClient`` flattens ``headers`` up to the K0 envelope top-level so
pseudo-K0's :class:`scripts.pseudo_k0.models.K0Envelope` (``extra='ignore'``)
parses it cleanly and the WAL row gets ``space_id`` / ``actor_id`` populated.

Bridge integration (typed contract surface)
-------------------------------------------

For paired-contract calls (currently ``recall.request.v1``) we honour the
canonical bridge path:

    k1 caller
      → IMemoryPort (RecallMemoryAdapter)
      → build_recall_fn closure
      → http_bridge_client.recall_request_v1.request(RecallRequestV1)
      → HttpTransport.publish(...)
      → EnvelopeBuilder.build(...) (signs envelope)
      → HttpTransport.post_command(envelope_bytes)
      → POST /k0/command.submit
      → K0 → SQLiteK0Store.recall(...) → RecallResponseV1

To make the typed publish path work, :meth:`LiveBridgeAdapter.connect`
constructs an :class:`bridge.core.envelope_builder.EnvelopeBuilder` (with a
dev :class:`bridge.core.signing.HmacSigning` signer) and binds it onto the
:class:`bridge.core.transport.HttpTransport` at construction time. Pseudo-K0
does not verify ``sig`` / ``envelope_sha256`` in dev mode, but the signed
envelope is also accepted unchanged by real K0 — so this single wiring
covers both targets.

The MW write path continues to use ``submit_command_batch`` →
``post_command`` because pseudo-K0 returns a generic ``{ok, wal_row_id}``
ack for ``memory.write.v1`` rather than the typed ``memory.write.response.v1``
body the generated client would try to validate; that conversion belongs
in a follow-up that aligns pseudo-K0's write-ack shape with the contract.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Bridge contracts directory — relative to workspace root.
_CONTRACTS_PATH = Path("bridge/contracts")


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class LiveBridgeClient:
    """Generic-surface shim over :class:`bridge.core.transport.HttpTransport`.

    Mirrors the subset of :class:`bridge.client.SinkBridgeClient` that the
    kernel currently consumes (``submit_command``, ``submit_command_batch``,
    ``emit_obs``, ``execute_connector``, ``is_connected``, ``connect``,
    ``disconnect``) and delegates each call to a raw HTTP POST against the
    pseudo-K0 / real-K0 endpoints.

    The typed per-contract slots (``memory_write_v1`` / ``recall_request_v1``
    / ``query`` / ``sse``) are copied across from the underlying
    :class:`bridge.client.HttpBridgeClient` so callers that read them
    (e.g. ``k1.concierge.adapters.recall_memory.build_recall_fn``) keep
    working.
    """

    def __init__(
        self,
        *,
        transport: Any,
        http_bridge_client: Any | None = None,
        default_space_id: str = "",
        default_actor: str = "",
        default_tenant_id: str = "",
        default_device_id: str = "",
        default_band: str = "GREEN",
    ) -> None:
        self._transport = transport
        self._http_client = getattr(transport, "http_client", None) or getattr(
            transport, "_client", None
        )
        self._base_url = getattr(getattr(transport, "config", None), "base_url", "")
        self._default_space_id = default_space_id
        self._default_actor = default_actor
        self._default_tenant_id = default_tenant_id
        self._default_device_id = default_device_id
        self._default_band = default_band
        # Forward typed slots from the runtime-built client. The
        # ``recall_request_v1`` typed client now works end-to-end because
        # :meth:`LiveBridgeAdapter.connect` wires an ``EnvelopeBuilder``
        # onto the transport before constructing the runtime — see this
        # module's docstring for the integration map.
        self.memory_write_v1 = getattr(http_bridge_client, "memory_write_v1", None)
        self.recall_request_v1 = getattr(http_bridge_client, "recall_request_v1", None)
        self.query = getattr(http_bridge_client, "query", None)
        self.sse = getattr(http_bridge_client, "sse", None)
        self.obs = getattr(http_bridge_client, "obs", None)
        self.gateway = getattr(http_bridge_client, "gateway", None)

    # ------------------------------------------------------------------
    # Lifecycle (parity with SinkBridgeClient duck-type used by Fabric)
    # ------------------------------------------------------------------
    def is_connected(self) -> bool:
        return self._transport is not None

    async def connect(self) -> None:  # pragma: no cover - trivial
        return None

    async def disconnect(self) -> None:  # pragma: no cover - trivial
        return None

    # ------------------------------------------------------------------
    # Generic command surface (MW path)
    # ------------------------------------------------------------------
    async def submit_command(
        self,
        topic: str,
        body: dict[str, Any],
        *,
        schema_uri: str | None = None,
        band: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        """POST a single envelope to ``/k0/command.submit``."""
        envelope = self._build_envelope(
            topic=topic,
            body=body,
            schema_uri=schema_uri,
            band=band,
            trace_id=trace_id,
        )
        await self._post_envelope(envelope, topic)

    async def submit_command_batch(self, envelopes: list[Any]) -> None:
        """POST each envelope in the batch to ``/k0/command.submit``.

        Accepts the MW envelope dict shape::

            {"topic", "schema_uri", "body", "trace_id", "headers"}

        ``headers`` (when present) is flattened up to the K0 envelope so
        pseudo-K0 records the correct ``space_id`` / ``actor`` / ``band``.
        """
        if not envelopes:
            return
        errors: list[str] = []
        for env in envelopes:
            try:
                topic, payload = self._normalise_envelope(env)
                await self._post_envelope(payload, topic)
            except Exception as exc:  # noqa: BLE001 — collect and continue
                errors.append(f"{getattr(env, 'topic', 'unknown')}: {exc!r}")
                logger.warning("LiveBridgeClient: submit failed: %s", exc, exc_info=True)
        if errors:
            logger.warning(
                "LiveBridgeClient: submit_command_batch had %d failure(s)",
                len(errors),
            )

    # ------------------------------------------------------------------
    # Observability + IFL
    # ------------------------------------------------------------------
    async def emit_obs(
        self,
        kind: str,
        body: dict[str, Any],
        *,
        priority: str = "NORMAL",
        trace_id: str | None = None,
    ) -> None:
        """POST to ``/k0/obs.emit``. Fire-and-forget; errors are logged."""
        client = self._http_client
        if client is None:
            logger.debug("LiveBridgeClient: emit_obs dropped (no http client)")
            return
        try:
            payload = {"kind": kind, "body": body, "trace_id": trace_id}
            await client.post("/k0/obs.emit", json=payload)
        except Exception:
            logger.warning("LiveBridgeClient: emit_obs failed", exc_info=True)

    async def execute_connector(
        self,
        adapter_id: str,
        action: str,
        params: dict[str, Any],
        *,
        trace_id: str | None = None,
        timeout_ms: int = 30_000,
    ) -> dict[str, Any]:
        """Route a connector call through ``/k0/command.submit``.

        Pseudo-K0 dispatches connector calls by topic prefix on the same
        command-ingest endpoint as the rest of the bridge contracts.
        """
        topic = f"connector.execute.{adapter_id}.{action}"
        envelope = self._build_envelope(
            topic=topic,
            schema_uri="bridge://contracts/schemas/connector.execute.v1.json",
            band=None,
            trace_id=trace_id,
            body={
                "adapter_id": adapter_id,
                "action": action,
                "params": params,
                "timeout_ms": timeout_ms,
            },
        )
        result = await self._post_envelope(envelope, topic)
        if 200 <= getattr(result, "status_code", 0) < 300:
            return result.body or {}
        return {
            "ok": False,
            "status_code": getattr(result, "status_code", 0),
            "error": getattr(result, "error", None),
            "body": getattr(result, "body", None),
            "trace_id": trace_id,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _normalise_envelope(self, env: Any) -> tuple[str, dict[str, Any]]:
        """Translate an MW (or generic) envelope into a K0 envelope dict."""
        if isinstance(env, dict):
            topic = str(env.get("topic", "unknown"))
            body = env.get("body") or {}
            schema_uri = env.get("schema_uri")
            trace_id = env.get("trace_id")
            headers = env.get("headers") or {}
            band = env.get("band") or headers.get("band")
            payload = self._build_envelope(
                topic=topic,
                body=body if isinstance(body, dict) else {"value": body},
                schema_uri=schema_uri,
                band=band,
                trace_id=trace_id,
                headers=headers,
            )
            return topic, payload
        # CommandEnvelope-like duck-type.
        topic = str(getattr(env, "topic", "unknown"))
        payload = self._build_envelope(
            topic=topic,
            body=getattr(env, "body", {}) or {},
            schema_uri=getattr(env, "schema_uri", None),
            band=getattr(env, "band", None),
            trace_id=getattr(env, "trace_id", None),
        )
        return topic, payload

    def _build_envelope(
        self,
        *,
        topic: str,
        body: dict[str, Any],
        schema_uri: str | None,
        band: str | None,
        trace_id: str | None,
        headers: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        h = headers or {}
        envelope: dict[str, Any] = {
            "topic": topic,
            "body": body,
            "schema_uri": schema_uri or h.get("schema_uri") or "",
            "schema_version": h.get("schema_version", "1.0"),
            "cognitive_trace_id": (trace_id or h.get("cognitive_trace_id") or uuid.uuid4().hex),
            "tenant_id": h.get("tenant_id") or self._default_tenant_id,
            "space_id": h.get("space_id") or self._default_space_id or "default",
            "actor": h.get("actor") or self._default_actor,
            "device_id": h.get("device_id") or self._default_device_id,
            "band": band or h.get("band") or self._default_band,
            "ts": _utc_iso_now(),
        }
        return envelope

    async def _post_envelope(self, envelope: dict[str, Any], topic: str) -> Any:
        envelope_bytes = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        result = await self._transport.post_command(envelope_bytes)
        status = getattr(result, "status_code", 0)
        if 200 <= status < 300:
            logger.debug("LiveBridgeClient: K0 accepted topic=%s status=%d", topic, status)
            return result
        body = getattr(result, "body", None)
        error = getattr(result, "error", None)
        logger.warning(
            "LiveBridgeClient: K0 rejected topic=%s status=%d body=%r error=%r",
            topic,
            status,
            body,
            error,
        )
        return result


class LiveBridgeAdapter:
    """Real-HTTP bridge adapter using ``BridgeRuntime`` → ``HttpBridgeClient``.

    Used at S4 when ``KernelConfig.k0_endpoint`` is non-empty. ``get_client()``
    returns a :class:`LiveBridgeClient` shim that exposes both the typed
    contract slots (from the runtime-built client) and the generic
    ``submit_command`` / ``submit_command_batch`` / ``emit_obs`` surface
    consumed by the kernel and memory-writer.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        contracts_path: Path | str = _CONTRACTS_PATH,
        connect_timeout_s: float = 5.0,
        tls_verify: bool = False,
        default_space_id: str = "",
        default_actor: str = "",
        default_tenant_id: str = "",
        default_device_id: str = "",
        default_band: str = "GREEN",
    ) -> None:
        self._endpoint = endpoint
        self._contracts_path = Path(contracts_path)
        self._connect_timeout_s = connect_timeout_s
        self._tls_verify = tls_verify
        self._default_space_id = default_space_id
        self._default_actor = default_actor
        self._default_tenant_id = default_tenant_id
        self._default_device_id = default_device_id
        self._default_band = default_band
        self._transport: Any = None
        self._runtime: Any = None
        self._http_bridge_client: Any = None
        self._client: LiveBridgeClient | None = None
        self._connected = False

    async def connect(self) -> None:
        """Open HTTP transport and build ``LiveBridgeClient`` over it."""
        if self._connected:
            return

        from bridge.core.envelope_builder import BridgeConfig, EnvelopeBuilder
        from bridge.core.signing import HmacSigning
        from bridge.core.transport import HttpTransport, TransportConfig
        from bridge.runtime import BridgeRuntime, Role

        config = TransportConfig(
            base_url=self._endpoint,
            connect_timeout_s=self._connect_timeout_s,
            tls_verify=self._tls_verify,
        )
        # Wire an EnvelopeBuilder onto the transport so the generated typed
        # clients (``recall_request_v1.request``, ``memory_write_v1.publish``,
        # …) which dispatch through ``HttpTransport.publish(...)`` can build
        # and sign envelopes. Pseudo-K0 ignores the signature in dev mode;
        # real K0 verifies it. The HMAC secret here is a dev-only zero-key
        # used solely to make the canonical path runnable until a key-manager
        # backed signer is threaded through ``KernelConfig``.
        envelope_builder = EnvelopeBuilder(
            config=BridgeConfig(
                tenant_id=self._default_tenant_id or "dev",
                space_id=self._default_space_id or "default",
                device_id=self._default_device_id or "dev-device",
                actor=self._default_actor or "bridge",
                default_band=self._default_band,
            ),
            signer=HmacSigning(secret=b"\x00" * 32, key_id="dev:livebridge"),
        )
        transport = HttpTransport(config=config, envelope_builder=envelope_builder)
        await transport.open()
        self._transport = transport

        runtime = BridgeRuntime.from_registry(
            contracts_path=self._contracts_path,
            role=Role.K1,
            transport=transport,
        )
        await runtime.start()
        self._runtime = runtime
        self._http_bridge_client = getattr(runtime, "client", None)

        self._client = LiveBridgeClient(
            transport=transport,
            http_bridge_client=self._http_bridge_client,
            default_space_id=self._default_space_id,
            default_actor=self._default_actor,
            default_tenant_id=self._default_tenant_id,
            default_device_id=self._default_device_id,
            default_band=self._default_band,
        )
        self._connected = True

        typed_slots = [
            s
            for s in ("memory_write_v1", "recall_request_v1", "query", "sse", "obs")
            if getattr(self._http_bridge_client, s, None) is not None
        ]
        logger.info(
            "LiveBridgeAdapter: connected to %s (typed_slots=%r, space_id=%r)",
            self._endpoint,
            typed_slots,
            self._default_space_id,
        )

    async def disconnect(self) -> None:
        """Tear down runtime and transport."""
        if self._runtime is not None:
            try:
                await self._runtime.stop()
            except Exception:
                logger.exception("LiveBridgeAdapter: runtime.stop() failed")
            self._runtime = None
        if self._transport is not None:
            close = getattr(self._transport, "close", None) or getattr(
                self._transport, "aclose", None
            )
            if close is not None:
                try:
                    await close()
                except Exception:
                    logger.exception("LiveBridgeAdapter: transport close failed")
            self._transport = None
        self._http_bridge_client = None
        self._client = None
        self._connected = False
        logger.info("LiveBridgeAdapter: disconnected from %s", self._endpoint)

    def is_connected(self) -> bool:
        return self._connected

    def get_client(self) -> Any:
        return self._client

    async def subscribe_sse(
        self,
        topics: list[str],
        space_id: str = "",
    ) -> Any:
        """E15.10: Async-generator that yields parsed SSE data frames from K0.

        Streams ``GET /k0/sse/<topic>`` for the **first** topic in *topics*
        (pseudo-K0 exposes one endpoint per topic).  Each line that starts
        with ``data: `` is JSON-parsed and yielded; heartbeat comment lines
        (``:``) are silently dropped.

        Yields a ``dict`` per event frame.  The caller (``_consume_tool_sse``)
        publishes each dict to the K1 bus.

        Exits on :class:`asyncio.CancelledError`.  Network errors propagate
        so the caller can implement retry logic.
        """
        import json as _json

        if not topics:
            return
        topic = topics[0]
        url = f"{self._endpoint.rstrip('/')}/k0/sse/{topic}"
        params: dict = {}
        if space_id:
            params["space_id"] = space_id

        import httpx

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url, params=params) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        # heartbeat comment — skip
                        continue
                    if line.startswith("data: "):
                        raw = line[6:].strip()
                        if not raw:
                            continue
                        try:
                            yield _json.loads(raw)
                        except _json.JSONDecodeError:
                            yield {"raw": raw}
