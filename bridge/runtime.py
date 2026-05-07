"""BridgeRuntime — symmetric per-kernel runtime built from the contract registry.

K0 and K1 each construct one ``BridgeRuntime`` via :meth:`BridgeRuntime.from_registry`.
The runtime owns:

* the loaded manifest list (filtered to this kernel's role),
* the transport binding chosen for each contract,
* the generated port / client / handler-registry surfaces (vendored under
  ``bridge/_generated/``).

In MS-2.5 this is a *skeleton*: the slots are present, ``from_registry`` parses
the registry and validates manifests, but no contracts are wired yet (Epic
2.5.5 lands ``memory.write.v1``). The public shape is frozen here so MS-3a/b/c
can fill it in without API churn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from bridge.runtime_errors import ManifestValidationError


class Role(str, Enum):
    """Which kernel this runtime serves."""

    K0 = "k0"
    K1 = "k1"


class Transport:
    """Marker base class for bridge transports.

    Concrete impls live under :mod:`bridge.core.transport`. Kept as a bare
    base in MS-2.5 — the protocol shape locks in MS-3a once the first
    contract demands it.
    """


@dataclass
class HandlerEntry:
    """One row in the runtime's handler dispatch table."""

    topic: str
    model: Any
    impl: Any


class HandlerRegistry:
    """Mutable dispatch table held inside the frozen :class:`BridgeRuntime`.

    Generated handler modules call ``runtime.register_handler(topic=...,
    model=..., impl=...)`` to wire the consumer-side function. The runtime
    looks up by exact topic on receipt and validates the body against
    ``model`` before invoking ``impl``.
    """

    def __init__(self) -> None:
        self._entries: dict[str, HandlerEntry] = {}

    def register(self, *, topic: str, model: Any, impl: Any) -> None:
        if topic in self._entries:
            raise ValueError(f"HandlerRegistry: topic {topic!r} already has a handler")
        self._entries[topic] = HandlerEntry(topic=topic, model=model, impl=impl)

    def lookup(self, topic: str) -> HandlerEntry | None:
        return self._entries.get(topic)

    def topics(self) -> list[str]:
        return sorted(self._entries.keys())


@dataclass(frozen=True)
class BridgeRuntime:
    """Symmetric per-kernel bridge runtime.

    Attributes:
        role: Which kernel this runtime instance serves.
        contracts_path: Absolute path to ``bridge/contracts/``.
        command: Command-port surface (populated MS-3a).
        query: Query-port surface (populated MS-3a).
        sse: SSE-port surface (populated MS-3b).
        obs: Obs-port surface (populated MS-3b).
        gateway: Connector-gateway surface (populated MS-3c).
        transport: Selected transport, or ``None`` for in-process default.
        manifests: Loaded + validated manifests for this role's traffic.
    """

    role: Role
    contracts_path: Path
    command: Any = None
    query: Any = None
    sse: Any = None
    obs: Any = None
    gateway: Any = None
    transport: Transport | None = None
    manifests: tuple[Any, ...] = field(default_factory=tuple)
    handlers: HandlerRegistry = field(default_factory=HandlerRegistry)
    client: Any = None
    event_bus: Any = None
    """Event bus shared by health checker, drain worker, DEGRADED matrix
    (MS-3b). Populated by :meth:`from_registry` for k1 runtimes; ``None``
    on k0 (k0 owns its receiver-side liveness signal directly)."""
    health: Any = None
    """K0 health checker (MS-3b epic 3b.1). ``None`` until a transport
    with a base URL is bound. The runtime owns its lifecycle via
    :meth:`start` / :meth:`stop`."""
    """Composite bridge client (MS-3a: ``HttpBridgeClient`` for k1).

    Populated by :meth:`from_registry` when ``role == K1`` and a real
    ``HttpTransport`` is bound. Direct callers should reach into
    ``runtime.client.<contract>.publish(...)`` rather than building
    envelopes by hand.
    """

    def register_handler(self, *, topic: str, model: Any, impl: Any) -> None:
        """Add a consumer-side handler binding.

        Generated handler modules call this exactly once at boot. The
        runtime is frozen at the dataclass level but the handler registry
        is internally mutable so the dispatch table can be populated.
        """
        self.handlers.register(topic=topic, model=model, impl=impl)

    async def dispatch(self, *, topic: str, payload: dict) -> Any:
        """Validate ``payload`` against the handler's model and invoke it.

        MS-3a: topic aliasing was removed (the ``memory.write`` →
        ``memory.write.v1`` shim served only the brief MS-2.5 cut-over
        window). Callers must supply the canonical versioned topic.

        Raises :class:`KeyError` when no handler is registered for the
        topic; raises ``pydantic.ValidationError`` when the payload
        does not conform to the contract schema.
        """
        entry = self.handlers.lookup(topic)
        if entry is None:
            raise KeyError(f"BridgeRuntime.dispatch: no handler for topic {topic!r}")
        validated = entry.model.model_validate(payload)
        result = entry.impl(validated)
        # Handlers may be sync or async; await iff coroutine.
        import inspect

        if inspect.isawaitable(result):
            result = await result
        return result

    @classmethod
    def from_registry(
        cls,
        *,
        contracts_path: Path | str,
        role: Role,
        transport: Transport | None = None,
    ) -> "BridgeRuntime":
        """Construct a runtime by loading the contract registry from disk.

        Validates every manifest against the meta-schema. Raises
        :class:`bridge.runtime_errors.ManifestValidationError` on the first
        invalid manifest.
        """
        path = Path(contracts_path).resolve()
        # Lazy import to keep tooling out of runtime import graph at import-time.
        from tooling.contracts.manifest_loader import ManifestValidationError as ToolingError
        from tooling.contracts.manifest_loader import (
            load_manifests,
        )

        try:
            manifests = load_manifests(path)
        except ToolingError as exc:
            # Re-raise as the runtime-side error so callers `except` once.
            raise ManifestValidationError(str(exc)) from exc

        # Filter to manifests this role participates in.
        relevant = tuple(
            m for m in manifests if role.value in {m.producer_kernel, m.consumer_kernel}
        )
        runtime = cls(
            role=role,
            contracts_path=path,
            transport=transport,
            manifests=relevant,
        )
        # MS-3a: build the producer-side client for k1 once a transport
        # is bound. K0-side dispatch lives in ``BridgeRuntime.dispatch``
        # and uses the ``handlers`` registry, not ``client``.
        if role is Role.K1 and transport is not None:
            from bridge.core.events import EventBus
            from bridge.core.health import K0HealthChecker

            event_bus = EventBus()
            base_url = getattr(getattr(transport, "config", None), "base_url", None)
            health = K0HealthChecker(event_bus=event_bus, target_url=base_url)
            object.__setattr__(runtime, "event_bus", event_bus)
            object.__setattr__(runtime, "health", health)
            client = _build_k1_client(runtime, relevant)
            object.__setattr__(runtime, "client", client)
            object.__setattr__(runtime, "command", client)
        return runtime

    async def start(self) -> None:
        """Start owned async tasks (health poll). Idempotent.

        K0 runtimes are receivers and own no async tasks here; for them
        this is a no-op kept for API symmetry. K1 runtimes start the
        health poll loop so the DEGRADED matrix and drain worker can
        observe transitions.
        """
        if self.health is not None:
            await self.health.start()

    async def stop(self) -> None:
        """Tear down owned async tasks. Safe to call when never started."""
        if self.health is not None:
            await self.health.stop()
        sse_client = getattr(self, "_sse_client", None)
        if sse_client is not None:
            await sse_client.aclose()
        obs_emitter = getattr(self, "_obs_emitter", None)
        if obs_emitter is not None:
            close = getattr(obs_emitter, "aclose", None)
            if close is not None:
                await close()

    def bind_sse_emitter(self, emitter: Any) -> None:
        """Attach a K0 SSE emitter to this runtime (MS-3d Epic 3d.3).

        Called by K0 deployment code after constructing
        :class:`k0.sse.emitter.K0SSEEmitter` (or any object with the same
        ``async emit(*, topic, schema_uri, payload)`` shape). The
        generated K0-side ``<Topic>Client.emit`` reaches through
        ``runtime._sse_emitter`` so this method is the supported seam.
        """
        if self.role is not Role.K0:
            raise RuntimeError("bind_sse_emitter: only K0-role runtimes may bind an SSE emitter")
        object.__setattr__(self, "_sse_emitter", emitter)


def _build_k1_client(runtime: "BridgeRuntime", manifests: tuple[Any, ...]) -> Any:
    """Construct the ``HttpBridgeClient`` for a k1 runtime.

    Walks ``manifests`` and instantiates the generated K1 client for each
    contract with ``status == 'active'``. Currently the only active
    contract is ``memory.write.v1``; new contracts are picked up here as
    they ship via MS-3b/c/d/e by adding new attribute slots in
    :class:`bridge.client.HttpBridgeClient` and a matching branch below.
    """
    # Local imports keep ``bridge.runtime`` import-cycle-free.
    from bridge.client import _RUNTIME_CONSTRUCTION_TOKEN, HttpBridgeClient

    slots: dict[str, Any] = {}
    query_bag: dict[str, Any] = {}
    sse_manifests: list[Any] = []
    obs_manifests: list[Any] = []
    for manifest in manifests:
        topic = getattr(manifest, "topic", None)
        status = getattr(manifest, "status", "active")
        if status != "active":
            continue
        transport_kind = (
            manifest.raw.get("delivery", {}).get("transport") if hasattr(manifest, "raw") else None
        )
        if transport_kind == "sse":
            sse_manifests.append(manifest)
            continue
        if transport_kind == "obs":
            obs_manifests.append(manifest)
            continue
        if topic == "memory.write.v1" and runtime.role is Role.K1:
            from bridge._generated.k1.clients.memory_write_v1 import MemoryWriteV1Client

            slots["memory_write_v1"] = MemoryWriteV1Client(runtime=runtime)
        elif topic == "recall.request.v1" and runtime.role is Role.K1:
            from bridge._generated.k1.clients.recall_request_v1 import (
                RecallRequestV1Client,
            )

            recall_client = RecallRequestV1Client(runtime=runtime)
            slots["recall_request_v1"] = recall_client
            query_bag["recall_request_v1"] = recall_client
    if query_bag:
        # Per MS-3c design: ``runtime.query`` is the typed read-side
        # namespace exposing every active recall/query contract by
        # generated-client attribute name. K1 callers reach through
        # ``runtime.query.recall_request_v1.request(...)`` rather than
        # building envelopes by hand.
        from types import SimpleNamespace

        object.__setattr__(runtime, "query", SimpleNamespace(**query_bag))

    # ------------------------------------------------------------------
    # MS-3d Epic 3d.4: SSE wiring. Build a shared ``SSEClient`` keyed off
    # the bound transport's base URL and call each generated handler
    # module's ``register_subscriber(runtime)`` so ``runtime.sse.<topic>``
    # is populated with a typed subscriber.
    # ------------------------------------------------------------------
    if sse_manifests and runtime.role is Role.K1:
        base_url = getattr(getattr(runtime.transport, "config", None), "base_url", None)
        if base_url is not None:
            from bridge.core.transport.sse_client import SSEClient, SSEClientConfig

            sse_http_client = getattr(runtime.transport, "http_client", None)
            sse_client = SSEClient(
                SSEClientConfig(base_url=base_url),
                http_client=sse_http_client,
            )
            object.__setattr__(runtime, "_sse_client", sse_client)
            for manifest in sse_manifests:
                module_name = manifest.topic.replace(".", "_")
                from importlib import import_module

                handler_mod = import_module(f"bridge._generated.k1.handlers.{module_name}")
                handler_mod.register_subscriber(runtime)

    # ------------------------------------------------------------------
    # MS-3e Epic 3e.2: obs/feedback wiring. Build a single shared
    # ``ObsHttpEmitter`` keyed off the bound transport's base URL and
    # populate ``runtime.obs.<topic>`` with the per-contract generated
    # clients. The generated obs clients reach through ``runtime._obs_emitter``
    # to POST ``{kind, body}`` to ``/k0/obs.emit``.
    # ------------------------------------------------------------------
    if obs_manifests and runtime.role is Role.K1:
        base_url = getattr(getattr(runtime.transport, "config", None), "base_url", None)
        if base_url is not None:
            from types import SimpleNamespace

            from bridge.core.transport.obs_emitter import ObsHttpEmitter

            obs_http_client = getattr(runtime.transport, "http_client", None)
            obs_emitter = ObsHttpEmitter(base_url=base_url, http_client=obs_http_client)
            object.__setattr__(runtime, "_obs_emitter", obs_emitter)

            obs_bag: dict[str, Any] = {}
            for manifest in obs_manifests:
                module_name = manifest.topic.replace(".", "_")
                from importlib import import_module

                client_mod = import_module(f"bridge._generated.k1.clients.{module_name}")
                # Convention: codegen emits exactly one ``<Topic>Client`` per file.
                client_cls = next(
                    v
                    for k, v in vars(client_mod).items()
                    if k.endswith("Client") and getattr(v, "__topic__", None) == manifest.topic
                )
                obs_bag[module_name] = client_cls(runtime=runtime)
            object.__setattr__(runtime, "obs", SimpleNamespace(**obs_bag))
    return HttpBridgeClient(_runtime_token=_RUNTIME_CONSTRUCTION_TOKEN, **slots)
