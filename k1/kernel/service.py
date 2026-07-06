"""KernelService — central lifecycle manager for K1 kernel (Issue 2.1.1).

Composition root that owns:
  - 8-phase Tier 1 startup  (S1→S7 + S6b cross-wire)
  - Per-session create/destroy  (P1→P7 / reverse)
  - Aggregated health check
  - Reverse-order shutdown

Implements ``ILifecyclePort`` + ``ISessionManagerPort`` so consumers
can depend on the abstract protocols.

Issue 2.4.3: Error recovery for partial startup / session creation,
health_check implementation, shutdown timeouts, idempotency, structured
error reporting, planner watchdog, graceful drain.

See: ADR-0095, 09_wiring_plan Issue 2.1.1
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bridge.bus_guard import BridgeAwareLocalBus

# Issue 2.3.5: MemoryWriter factory + adapters (per-session)
from k1.bus.adapters.fabric_adapter import FabricBusAdapter
from k1.bus.async_bridge import AsyncBusBridge
from k1.bus.factory import BusFactory
from k1.bus.ports.bus import IBus
from k1.bus.ports.mailbox import IMailboxRouter

# Issue 2.3.4: Concierge factory + adapters (per-session)
from k1.concierge.adapters.bus_input import BusInputAdapter
from k1.concierge.adapters.bus_output import BusOutputAdapter
from k1.concierge.adapters.fabric_dispatch import FabricDispatchAdapter
from k1.concierge.adapters.recall_memory import RecallMemoryAdapter, build_recall_fn
from k1.concierge.adapters.ssm_state import SSMStateAdapter
from k1.concierge.config.concierge import ConciergeConfig
from k1.concierge.config.kernel import KernelConfig
from k1.concierge.factory import ConciergeFactory, PortBundle
from k1.concierge.section_update import (
    DeterministicSectionUpdateClassifier,
    LLMSectionUpdateClassifier,
    SectionUpdateBackgroundWorker,
    SectionUpdateWorkerConfig,
)
from k1.fabric.adapters.bridge_connection import BridgeConnectionAdapter
from k1.fabric.adapters.delta_bus_prod import DeltaBusProdAdapter
from k1.fabric.adapters.event_port_prod import EventPortProdAdapter
from k1.fabric.adapters.model_gateway_bridge import ModelGatewayBridgeAdapter
from k1.fabric.adapters.prompt_system_prod import PromptSystemProdAdapter

# Issue 2.3.ic.adapters.sessionstate_reader import SessionStateReaderAdapter
from k1.fabric.adapters.sessionstate_reader import SessionStateReaderAdapter
from k1.fabric.circuit_breaker.breaker import CircuitBreaker, CircuitBreakerConfig
from k1.fabric.factory import FabricFactory
from k1.grounding.kernel.bootstrap import GroundingServiceBundle, build_grounding_bundle
from k1.grounding.kernel.handle import GroundingHandle, build_grounding_handle

# E7.M1.1: Unified HIL service + adapters
from k1.hil.adapters import KernelHILEventAdapter
from k1.hil.config import HILConfig
from k1.hil.ledger import HILLedgerAdapter
from k1.hil.safety import SafetyBandPolicy
from k1.hil.service import HumanInTheLoopService
from k1.kernel.adapters.bridge_adapter import OfflineBridgeAdapter, SinkBridgeAdapter
from k1.kernel.adapters.device_context import InMemoryDeviceContextPort

# Slice 1: kernel.db chat session persistence
from k1.kernel.adapters.kernel_db import KernelDB

# Issue 2.2.6: Planner adapters + factory
from k1.kernel.adapters.model_hub_llm_bus import ModelHubRequestBus

# Issue P1.1: Session-routing state reader for shared Tier 1 components
from k1.kernel.adapters.session_routing_reader import SessionRoutingStateReader
from k1.kernel.ports import HealthStatus
from k1.kernel.session import SessionInstance
from k1.memory_writer.adapters.bridge_command_adapter import BridgeCommandAdapter
from k1.memory_writer.adapters.event_subscription_adapter import (
    EventSubscriptionAdapter as MWEventSubscriptionAdapter,
)
from k1.memory_writer.adapters.health_adapter import HealthAdapter

# Issue 2.1.5: MW ModelHubAdapter — anti-corruption layer.
# MW's IModelHubPort.chat() ≠ K1's IModelHubPort.execute().
from k1.memory_writer.adapters.model_hub_adapter import ModelHubAdapter
from k1.memory_writer.adapters.session_read_adapter import SessionReadAdapter
from k1.memory_writer.config import MWConfig
from k1.memory_writer.factory import MemoryWriterFactory
from k1.memory_writer.health.circuit_breaker import CircuitBreaker as MWCircuitBreaker
from k1.model_hub.adapters.config_adapter import ConfigAdapter
from k1.model_hub.adapters.credential_store_adapter import CredentialStoreAdapter
from k1.model_hub.adapters.event_bus_adapter import EventBusAdapter as MHEventBusAdapter
from k1.model_hub.adapters.health_report_adapter import HealthReportAdapter as MHHealthReportAdapter
from k1.model_hub.adapters.prometheus_adapter import PrometheusAdapter
from k1.model_hub.adapters.session_state_prod import SessionStateProdAdapter
from k1.model_hub.factory import ModelHubFactory
from k1.model_hub.loader import ProviderConfig

# Issue 2.2.5: Orchestrator adapters + factory
from k1.orchestrator.adapters.bridge_client_shim import BridgeClientShim
from k1.orchestrator.adapters.bridge_write_adapter import BridgeWriteAdapter
from k1.orchestrator.adapters.delta_emit_adapter import DeltaEmitAdapter
from k1.orchestrator.adapters.event_subscription_adapter import EventSubscriptionAdapter
from k1.orchestrator.adapters.fabric_gateway_adapter import FabricGatewayAdapter
from k1.orchestrator.adapters.mailbox_adapter import MailboxAdapter
from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter
from k1.orchestrator.adapters.planner_adapter import PlannerAdapter
from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter
from k1.orchestrator.adapters.workflow_storage_adapter import WorkflowStorageAdapter
from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.workflows.persistence import SQLiteWorkflowAdapter
from k1.planner.adapters.bridge_adapter import BridgeAdapter as PlannerBridgeAdapter
from k1.planner.adapters.delta_bus_adapter import DeltaBusAdapter as PlannerDeltaBusAdapter
from k1.planner.adapters.event_bus_adapter import EventBusAdapter as PlannerEventBusAdapter
from k1.planner.adapters.fabric_registry_adapter import FabricRegistryAdapter
from k1.planner.adapters.fabric_retrieval_adapter import FabricRetrievalAdapter
from k1.planner.adapters.llm_gateway_adapter import LLMGatewayAdapter
from k1.planner.adapters.mailbox_adapter import MailboxAdapter as PlannerMailboxAdapter
from k1.planner.adapters.session_state_adapter import SessionStateReadAdapter as PlannerStateAdapter
from k1.planner.factory import PlannerFactory

# M5.E3.I2 + I3: k1.selfmodel kernel wiring (S2.6 + P3.5).
from k1.selfmodel.kernel import (
    SelfModelHandle,
    SelfModelServiceBundle,
    build_self_model_bundle,
    build_self_model_handle,
)

# Issue 2.3.2: SessionState adapters + factory
from k1.sessionstate.adapters.direct_writer import DirectWriterAdapter
from k1.sessionstate.adapters.local_events import LocalEventAdapter
from k1.sessionstate.adapters.sqlite_storage import SQLiteStorageAdapter
from k1.sessionstate.adapters.standalone_lifecycle import StandaloneLifecycle
from k1.sessionstate.async_bridge import AsyncSSMBridge
from k1.sessionstate.factory import SessionStateFactory
from k1.spatial.adapters import SpatialDeviceContextAdapter
from k1.spatial.kernel.bootstrap import SpatialServiceBundle, build_spatial_bundle
from k1.spatial.kernel.handle import SpatialHandle, build_spatial_handle
from k1.temporal.adapters.device_context_adapter import DeviceContextAdapter
from k1.temporal.kernel.bootstrap import TemporalServiceBundle, build_temporal_bundle
from k1.temporal.kernel.handle import TemporalHandle, build_temporal_handle

# Issue 2.4.3: Default timeout for component teardown (seconds).
_TEARDOWN_TIMEOUT: float = 10.0

logger = logging.getLogger(__name__)


# ── Slice 7: auto-title helper (module-level, pure function) ──
def _auto_title(text: str, max_len: int = 50) -> str:
    """Generate a session title from the first user message."""
    title = text.strip()
    if len(title) > max_len:
        title = title[:max_len].rstrip() + "..."
    return title if title else "New Chat"


class _NullSSMShim:
    """3.1.2: Explicit null SSM shim for ModelHub's ``state_read_port``.

    Replaces the prior ``_FirstSessionSSMShim`` which returned the *first*
    active session's data regardless of which session triggered the
    request -- an actively-wrong behaviour the moment multiple sessions
    coexist (M01-C / 3.1.x).

    Until per-request session_id is threaded through ``IStateReadPort``
    (a larger refactor than M3 needs since ``RequestRouter`` has no
    state-driven consumer today), this shim returns ``None`` for every
    section and logs a single WARNING so the degradation is visible.
    ``SessionStateProdAdapter.read()`` already tolerates ``None`` and
    yields an empty ``StateSnapshot``.
    """

    __slots__ = ("_warned",)

    def __init__(self) -> None:
        self._warned: bool = False

    def get_section(self, name: str) -> Any | None:
        if not self._warned:
            logger.warning(
                "ModelHub state_read_port is bound to _NullSSMShim -- "
                "SessionState reads return None. Per-session wiring "
                "requires threading HubRequest.session_id through "
                "IStateReadPort (3.1.x follow-up)."
            )
            self._warned = True
        return None


class KernelService:
    """Central lifecycle manager for the K1 kernel.

    Plain class (not dataclass) — has mutable lifecycle state.
    Satisfies both ``ILifecyclePort`` and ``ISessionManagerPort``.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, config: KernelConfig) -> None:
        # configuration
        self._config: KernelConfig = config

        # Tier 1 shared components (populated during startup)
        # Fields stay ``Any | None`` to keep partial-startup cleanup paths
        # type-clean. Real enforcement happens at runtime in
        # ``_validate_ports()`` via ``isinstance(...)`` against the bus
        # subsystem Protocols and structural ``hasattr`` checks for the
        # subsystems that have no Protocol surface here yet.
        self._bus: Any | None = None  # IBus (sync LocalBus / RustBusAdapter)
        # Issue 2.1.4: async wrapper for direct async bus access.
        # Layer 1 adapters (FabricBusAdapter, SessionBusAdapter) get _bus (sync).
        # _async_bus is for components needing direct async bus operations.
        self._async_bus: Any | None = None  # AsyncBusBridge
        self._router: Any | None = None  # IMailboxRouter
        self._model_hub: Any | None = None  # ModelHub
        self._shared_fabric: Any | None = None  # Fabric
        self._prompt_system: Any | None = None  # PromptSystemProdAdapter
        self._bridge: Any | None = None  # IBridgeClient | None
        self._tool_sse_task: asyncio.Task[Any] | None = None
        self._orchestrator: Any | None = None  # OrchestratorService
        self._orch_storage: Any | None = None  # WorkflowStorageAdapter
        self._planner: Any | None = None  # PlannerAgent
        self._planner_task: asyncio.Task[Any] | None = None

        # E7.M1.1: Unified HIL service. Constructed at S2.5 (after S2 ModelHub
        # and before S3 Fabric, so all four downstream subsystems can receive
        # the same instance). ``None`` when ``KernelConfig.enable_hil_service``
        # is False, in which case each factory falls back to its internal
        # ``_NullHILAdapter``.
        self._hil_service: Any | None = None  # HumanInTheLoopService

        # M5.E3.I2: Shared k1.selfmodel bundle. Built at S2.6 when
        # ``KernelConfig.enable_self_model`` is True. Per-session
        # ``SelfModelHandle`` instances (built at P3.5) reference this
        # bundle so every session shares one constitution / projection
        # store / signature validator.
        self._self_model_bundle: SelfModelServiceBundle | None = None

        # M1: shared temporal bundle. Built at S2.7 when
        # ``KernelConfig.enable_temporal`` is True. Per-session
        # ``TemporalHandle`` instances (built at P3.6) bind the shared
        # clock/policy stack to session-local state.
        self._temporal_bundle: TemporalServiceBundle | None = None
        self._device_context_port: Any | None = None

        # M3: shared spatial bundle. Built at S2.8 when
        # ``KernelConfig.enable_spatial`` is True, after Bridge exists
        # and before Grounding so grounding can consume a real handle.
        self._spatial_bundle: SpatialServiceBundle | None = None

        # M1.5: shared grounding bundle. Built at transitional S2.9 when
        # ``KernelConfig.enable_grounding`` is True. Per-session
        # ``GroundingHandle`` instances (built at P3.8) bind the bundle to
        # session-local temporal/spatial/identity/state surfaces.
        self._grounding_bundle: GroundingServiceBundle | None = None

        # M15: Family-tools bundle (k1.tools.family). Built at S8 of
        # _startup_tier1 when KernelConfig.enable_family_tools is True.
        # Owns the K1FamilyStore SQLite connection, ToolRegistry,
        # IdempotencyStore, and NativeToolProvider registered into the
        # shared Fabric. Closed during shutdown / cleanup.
        self._family_tools: Any | None = None

        # Phase 1 Fabric (Epic 7.3): shared GlobalProjectionStore +
        # IdempotencyStore. Created at S2.10 when
        # ``KernelConfig.enable_fabric_stores`` is True, passed to the
        # shared Fabric (factory step 21), and closed during shutdown.
        # ``None`` when the flag is off (default).
        self._global_projection_store: Any | None = None
        self._idempotency_store: Any | None = None

        # Slice 1: kernel.db (chat session persistence)
        self._kernel_db: KernelDB | None = None

        # Slice 3: session registry (stable IDs + CRUD)
        self._session_registry: Any | None = None

        # Phase 2: live registry snapshot queried from GPS after S8, injected
        # into Back's prompt as domain + resource_family hint lists.
        self._registry_hints: dict[str, Any] | None = None

        # M4: optional hidden per-session SectionUpdateBackgroundWorker.
        # The worker is disabled by default in KernelConfig and receives an
        # injected classifier before sessions are created in shadow/apply mode.
        self._section_update_classifier: Any | None = None

        # P1.1: Shared routing reader (resolves session_id → SSM)
        self._session_routing_reader: SessionRoutingStateReader | None = None

        # Tier 2 per-session components
        self._sessions: dict[str, SessionInstance] = {}

        # lifecycle flag
        self._running: bool = False

        # Diagnostics: append-only log of lifecycle phase transitions.
        # Written by _log_lifecycle(); read by lifecycle_events() probes.
        # Never read by production code.
        self._lifecycle_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Whether the kernel has completed startup."""
        return self._running

    @property
    def session_count(self) -> int:
        """Number of active sessions."""
        return len(self._sessions)

    @property
    def config(self) -> KernelConfig:
        """The kernel configuration."""
        return self._config

    def set_section_update_classifier(self, classifier: Any | None) -> None:
        """Inject the classifier used by future per-session background workers."""
        self._section_update_classifier = classifier

    @property
    def async_bus(self) -> Any | None:
        """The async bus bridge (``AsyncBusBridge``), or ``None`` before startup."""
        return self._async_bus

    @property
    def orchestrator(self) -> Any | None:
        """Shared OrchestratorService instance, or ``None`` before S5.

        Public accessor for the Tier-1 orchestrator. Replaces external
        reads of the ``_orchestrator`` private slot (e.g. the
        ``start_kernel`` backward-compat facade in ``bootstrap.py``).
        """
        return self._orchestrator

    @property
    def hil_service(self) -> Any | None:
        """Shared ``HumanInTheLoopService`` instance, or ``None`` if disabled.

        Populated at S2.5 when ``KernelConfig.enable_hil_service`` is True.
        The same instance is wired into Fabric, Concierge, Planner, and
        Orchestrator so they all share one set of pending HIL requests,
        round budgets, and safety policy decisions.
        """
        return self._hil_service

    @property
    def family_tools(self) -> Any | None:
        """The :class:`FamilyToolsBundle` built at S8, or ``None`` if disabled.

        Populated when ``KernelConfig.enable_family_tools`` is True. Exposes
        the registered ``ToolRegistry`` (used by the web UI to mount per-
        adapter REST routers) and the ``NativeToolProvider`` registered
        into the shared Fabric.
        """
        return self._family_tools

    @property
    def self_model_bundle(self) -> SelfModelServiceBundle | None:
        """Shared :class:`SelfModelServiceBundle`, or ``None`` if disabled.

        Populated at S2.6 when ``KernelConfig.enable_self_model`` is
        True. Every per-session :class:`SelfModelHandle` references
        this bundle.
        """
        return self._self_model_bundle

    @property
    def temporal_bundle(self) -> TemporalServiceBundle | None:
        """Shared :class:`TemporalServiceBundle`, or ``None`` if disabled."""
        return self._temporal_bundle

    @property
    def device_context_port(self) -> Any | None:
        """Shared installed-device context port used by temporal grounding."""
        return self._device_context_port

    @property
    def spatial_bundle(self) -> SpatialServiceBundle | None:
        """Shared :class:`SpatialServiceBundle`, or ``None`` if disabled."""
        return self._spatial_bundle

    @property
    def grounding_bundle(self) -> GroundingServiceBundle | None:
        """Shared :class:`GroundingServiceBundle`, or ``None`` if disabled."""
        return self._grounding_bundle

    # ------------------------------------------------------------------
    # Diagnostics API (observability-only; no production code reads these)
    # ------------------------------------------------------------------

    def describe_wiring(self) -> dict[str, Any]:
        """Return a read-only snapshot of the live kernel wiring graph.

        Intended exclusively for PORT-IDENTITY probes in
        ``tests/integration/k1/live/``.  Never call from production code.

        Returns a plain dict with keys:
            tier1:          names→type of shared Tier-1 components.
            tier1_ports:    selected shared port adapter types.
            port_identities: selected PORT-IDENTITY boolean claims.
            sessions:       per-session component class names.
            running:        whether the kernel has completed startup.
            bridge_mode:    "LIVE" | "SINK" | "OFFLINE".
            planner_task:   asyncio.Task name or None.
        """
        tier1: dict[str, str | None] = {
            "bus": type(self._bus).__name__ if self._bus is not None else None,
            "async_bus": type(self._async_bus).__name__ if self._async_bus is not None else None,
            "router": type(self._router).__name__ if self._router is not None else None,
            "model_hub": type(self._model_hub).__name__ if self._model_hub is not None else None,
            "shared_fabric": (
                type(self._shared_fabric).__name__ if self._shared_fabric is not None else None
            ),
            "prompt_system": (
                type(self._prompt_system).__name__ if self._prompt_system is not None else None
            ),
            "bridge": type(self._bridge).__name__ if self._bridge is not None else None,
            "orchestrator": (
                type(self._orchestrator).__name__ if self._orchestrator is not None else None
            ),
            "planner": type(self._planner).__name__ if self._planner is not None else None,
            "hil_service": (
                type(self._hil_service).__name__ if self._hil_service is not None else None
            ),
            "self_model_bundle": (
                type(self._self_model_bundle).__name__
                if self._self_model_bundle is not None
                else None
            ),
            "temporal_bundle": (
                type(self._temporal_bundle).__name__ if self._temporal_bundle is not None else None
            ),
            "spatial_bundle": (
                type(self._spatial_bundle).__name__ if self._spatial_bundle is not None else None
            ),
            "grounding_bundle": (
                type(self._grounding_bundle).__name__
                if self._grounding_bundle is not None
                else None
            ),
        }

        sessions: dict[str, dict[str, str | None]] = {}
        for sid, sess in self._sessions.items():
            sessions[sid] = {
                "bus": type(sess.bus).__name__ if sess.bus is not None else None,
                "session_state": (
                    type(sess.session_state).__name__ if sess.session_state is not None else None
                ),
                "fabric": type(sess.fabric).__name__ if sess.fabric is not None else None,
                "concierge": type(sess.concierge).__name__ if sess.concierge is not None else None,
                "memory_writer": (
                    type(sess.memory_writer).__name__ if sess.memory_writer is not None else None
                ),
                "temporal": type(sess.temporal).__name__ if sess.temporal is not None else None,
                "spatial": type(sess.spatial).__name__ if sess.spatial is not None else None,
                "grounding": type(sess.grounding).__name__ if sess.grounding is not None else None,
            }

        # Determine bridge mode from the runtime bridge object type name.
        bridge_type = type(self._bridge).__name__ if self._bridge is not None else "None"
        if "Live" in bridge_type or "Http" in bridge_type:
            bridge_mode = "LIVE"
        elif "Sink" in bridge_type or "Outbox" in bridge_type:
            bridge_mode = "SINK"
        else:
            bridge_mode = "OFFLINE"

        planner_port = (
            getattr(self._orchestrator, "_planner_port", None)
            if self._orchestrator is not None
            else None
        )
        get_planner_mailbox = (
            getattr(self._planner, "get_mailbox", None) if self._planner is not None else None
        )
        planner_mailbox = get_planner_mailbox() if callable(get_planner_mailbox) else None
        planner_port_mailbox = getattr(planner_port, "_mailbox", None)

        tier1_ports: dict[str, Any] = {
            "orchestrator.planner_port": (
                type(planner_port).__name__ if planner_port is not None else None
            ),
            "orchestrator.planner_port.mailbox": (
                type(planner_port_mailbox).__name__ if planner_port_mailbox is not None else None
            ),
            "planner.mailbox": (
                type(planner_mailbox).__name__ if planner_mailbox is not None else None
            ),
            "prompt_system.template_count": (
                getattr(self._prompt_system, "template_count", None)
                if self._prompt_system is not None
                else None
            ),
        }
        port_identities: dict[str, bool | None] = {
            "orchestrator.planner_port_is_real_planner_adapter": (
                isinstance(planner_port, PlannerAdapter) if planner_port is not None else None
            ),
            "orchestrator.planner_port_is_mock": (
                isinstance(planner_port, MockPlannerAdapter) if planner_port is not None else None
            ),
            "orchestrator.planner_port_mailbox_is_planner_mailbox": (
                planner_port_mailbox is planner_mailbox
                if planner_port_mailbox is not None and planner_mailbox is not None
                else None
            ),
        }

        return {
            "tier1": tier1,
            "tier1_ports": tier1_ports,
            "port_identities": port_identities,
            "sessions": sessions,
            "running": self._running,
            "bridge_mode": bridge_mode,
            "planner_task": (
                self._planner_task.get_name() if self._planner_task is not None else None
            ),
        }

    def lifecycle_events(self) -> list[dict[str, Any]]:
        """Return the append-only log of lifecycle phase transitions.

        Each entry is ``{"phase": str, "component": str, "ts": float}``
        where ``ts`` is ``time.monotonic()`` at the moment the event was
        recorded.  Intended for LIFECYCLE-ORDER probes.
        """
        return list(self._lifecycle_log)

    def _log_lifecycle(self, phase: str, component: str) -> None:
        """Append a lifecycle event to the internal log (diagnostics only)."""
        self._lifecycle_log.append({"phase": phase, "component": component, "ts": time.monotonic()})

    def _log_grounding_feature_flags(self) -> None:
        """Log the current temporal/spatial/grounding feature gates."""
        logger.info(
            "grounding feature flags: temporal=%s spatial=%s grounding=%s",
            bool(getattr(self._config, "enable_temporal", False)),
            bool(getattr(self._config, "enable_spatial", False)),
            bool(getattr(self._config, "enable_grounding", False)),
        )

    def _close_orchestrator_storage(self) -> None:
        """Close S5 workflow storage owned by the kernel construction root."""
        storage = self._orch_storage
        if storage is None:
            return
        close = getattr(storage, "close", None)
        if callable(close):
            close()
        self._orch_storage = None

    # ------------------------------------------------------------------
    # ILifecyclePort
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Execute the 8-phase Tier 1 bootstrap (S1→S7 + S6b).

        Issue 2.4.3: If _startup_tier1() fails partway through, any
        already-created components are cleaned up before re-raising.
        ``_running`` is never set to True on failure.

        Raises:
            RuntimeError: If already running, or if startup fails
                (original exception is re-raised after cleanup).
        """
        if self._running:
            raise RuntimeError("Already running")
        self._log_grounding_feature_flags()
        try:
            await self._startup_tier1()
        except Exception:
            # Partial startup — clean up whatever was created.
            await self._cleanup_tier1_partial()
            raise

    async def shutdown(self) -> None:
        """Reverse teardown: destroy all sessions, then shared components.

        Issue 2.4.3 enhancements:
            - Idempotency guard: no-op if already shut down (#6).
            - Per-step timeouts: each async teardown step has a
              ``_TEARDOWN_TIMEOUT`` second deadline (#7).
            - Structured error reporting: raises ``RuntimeError`` with
              aggregated messages when teardown has failures (#8).

        Sequence (reverse of startup):
            1. Destroy all active sessions (reverse P6→P1 each)
            2. Reverse S7: Stop Planner agent + cancel background task
            3. Reverse S6b: (cross-wire cleanup — no action needed)
            4. Reverse S5: Shutdown Orchestrator
            5. Reverse S4: Disconnect Bridge
            6. Reverse S3: Shutdown Fabric
            7. Reverse S2: (ModelHub has no teardown)
            8. Reverse S1: Close shared Bus + Router

        Each step is individually guarded — teardown continues even if
        one step fails.  ``_running`` is always set to ``False`` at the end.
        """
        # Issue 2.4.3 #6: Idempotency — early return if not running.
        if not self._running:
            return

        errors: list[Exception] = []

        # ── 1. Destroy all sessions ──────────────────────────
        for sid in list(self._sessions):
            try:
                await asyncio.wait_for(
                    self.destroy_session(sid),
                    timeout=_TEARDOWN_TIMEOUT,
                )
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: destroy_session(%s) failed: %s", sid, exc)
        self._log_lifecycle("sessions_destroyed", "SessionInstance")

        # ── Reverse S7: Stop Planner + cancel task ────────────
        if self._planner is not None:
            try:
                await asyncio.wait_for(
                    self._planner.stop(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
                self._log_lifecycle("S7_shutdown_complete", "PlannerAgent")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: Planner stop failed: %s", exc)

        if self._planner_task is not None:
            try:
                self._planner_task.cancel()
                try:
                    await self._planner_task
                except (asyncio.CancelledError, Exception):
                    pass  # expected after cancel
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: Planner task cancel failed: %s", exc)
            self._planner_task = None

        # ── Reverse S6b: (no action needed) ───────────────────

        # ── Reverse S5: Shutdown Orchestrator ─────────────────
        if self._orchestrator is not None:
            try:
                await asyncio.wait_for(
                    self._orchestrator.shutdown(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
                self._log_lifecycle("S5_shutdown_complete", "OrchestratorService")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: Orchestrator shutdown failed: %s", exc)

        if self._orch_storage is not None:
            try:
                self._close_orchestrator_storage()
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: Orchestrator storage close failed: %s", exc)

        # ── Reverse S2.5: Shutdown HIL service (E7.M1.1) ──────
        # Cancels every pending HIL future and unsubscribes from the bus.
        # Run after orchestrator/planner so they cannot create new HIL
        # requests after their teardown completes.
        if self._hil_service is not None:
            try:
                await asyncio.wait_for(
                    self._hil_service.shutdown(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
                self._log_lifecycle("S2.5_shutdown_complete", "HumanInTheLoopService")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: HIL service shutdown failed: %s", exc)

        # ── Reverse S2.6: Shutdown selfmodel bundle (M5.E3.I2) ──
        # Closes the SQLite projection store handle when the bundle
        # owns one. Sessions have already been destroyed (each
        # destroy_session uninstalled its handle), so the bundle has
        # no live consumers at this point.
        if self._self_model_bundle is not None:
            try:
                self._self_model_bundle.shutdown()
                self._log_lifecycle("S2.6_shutdown_complete", "SelfModelServiceBundle")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: selfmodel bundle shutdown failed: %s", exc)
            self._self_model_bundle = None

        if self._grounding_bundle is not None:
            try:
                self._grounding_bundle.shutdown()
                self._log_lifecycle("S2.9_shutdown_complete", "GroundingServiceBundle")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: grounding bundle shutdown failed: %s", exc)
            self._grounding_bundle = None

        if self._spatial_bundle is not None:
            try:
                self._spatial_bundle.shutdown()
                self._log_lifecycle("S2.8_shutdown_complete", "SpatialServiceBundle")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: spatial bundle shutdown failed: %s", exc)
            self._spatial_bundle = None

        if self._temporal_bundle is not None:
            try:
                self._temporal_bundle.shutdown()
                self._log_lifecycle("S2.7_shutdown_complete", "TemporalServiceBundle")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: temporal bundle shutdown failed: %s", exc)
            self._temporal_bundle = None
        self._device_context_port = None

        if self._tool_sse_task is not None:
            try:
                self._tool_sse_task.cancel()
                try:
                    await self._tool_sse_task
                except (asyncio.CancelledError, Exception):
                    pass
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: tool SSE task cancel failed: %s", exc)
            self._tool_sse_task = None

        # ── Reverse S4: Disconnect Bridge ─────────────────────
        if self._bridge is not None:
            try:
                await asyncio.wait_for(
                    self._bridge.disconnect(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
                self._log_lifecycle("S4_shutdown_complete", type(self._bridge).__name__)
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: Bridge disconnect failed: %s", exc)

        # ── Reverse S3: Shutdown Fabric ───────────────────────
        if self._shared_fabric is not None:
            try:
                await asyncio.wait_for(
                    self._shared_fabric.shutdown(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
                self._log_lifecycle("S3_shutdown_complete", "CapabilityFabric")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: Fabric shutdown failed: %s", exc)

        # ── Reverse S8: Close FamilyToolsBundle (M15) ─────────
        if self._family_tools is not None:
            try:
                self._family_tools.close()
                self._log_lifecycle("S8_shutdown_complete", "FamilyToolsBundle")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: FamilyToolsBundle close failed: %s", exc)
            self._family_tools = None

        # ── Reverse S2.10: Close Phase 1 Fabric stores ────────
        if self._global_projection_store is not None:
            try:
                self._global_projection_store.close()
                self._log_lifecycle("Phase1_store_closed", "GlobalProjectionStore")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: GlobalProjectionStore close failed: %s", exc)
            self._global_projection_store = None

        if self._idempotency_store is not None:
            try:
                self._idempotency_store.close()
                self._log_lifecycle("Phase1_store_closed", "IdempotencyStore")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: IdempotencyStore close failed: %s", exc)
            self._idempotency_store = None

        # ── Reverse S2.12: Close kernel.db + registry ───────
        if self._session_registry is not None:
            self._session_registry = None
        if self._kernel_db is not None:
            try:
                self._kernel_db.close()
                self._log_lifecycle("S2.12_closed", "KernelDB")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: KernelDB close failed: %s", exc)
            self._kernel_db = None

        # ── Reverse S2: ModelHub plugin drain (P2.3) ──────────
        if self._model_hub is not None:
            try:
                await asyncio.wait_for(
                    self._model_hub.shutdown(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
                self._log_lifecycle("S2_shutdown_complete", "ModelHub")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: ModelHub shutdown failed: %s", exc)

        # ── Reverse S1: Close shared Bus + Router ─────────────
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: Bus close failed: %s", exc)

        if self._router is not None:
            try:
                self._router.close()
                self._log_lifecycle("S1_shutdown_complete", "Bus+Router")
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: Router close failed: %s", exc)

        # ── Always mark as not running ────────────────────────
        self._running = False
        self._log_lifecycle("shutdown_complete", "KernelService")

        # Issue 2.4.3 #8: Structured error reporting.
        if errors:
            msg = f"shutdown: {len(errors)} error(s) during teardown"
            logger.error(msg)
            raise RuntimeError(f"{msg}: {'; '.join(str(e) for e in errors)}")

    async def health_check(self) -> HealthStatus:
        """Aggregate health from all Tier 1 components.

        Issue 2.4.3 #4: Real implementation replacing stub.

        Checks:
            - ``_running`` flag
            - ``_bus`` not closed
            - ``_router`` not closed
            - ``_model_hub`` exists
            - ``_shared_fabric`` exists
            - ``_bridge`` exists
            - ``_orchestrator`` exists
            - ``_planner`` exists
            - ``_planner_task`` alive (not done/cancelled)

        Returns:
            ``HealthStatus`` with per-component breakdown.
        """
        components: dict[str, bool] = {}
        details: dict[str, str] = {}

        # Core lifecycle flag
        components["running"] = self._running
        if not self._running:
            details["running"] = "Kernel not running"

        # S1: Bus
        if self._bus is not None:
            bus_closed = bool(getattr(self._bus, "is_closed", False))
            components["bus"] = not bus_closed
            if bus_closed:
                details["bus"] = "Bus is closed"
        else:
            components["bus"] = False
            details["bus"] = "Bus not initialised"

        # S1: Router
        if self._router is not None:
            router_closed = bool(getattr(self._router, "is_closed", False))
            components["router"] = not router_closed
            if router_closed:
                details["router"] = "Router is closed"
        else:
            components["router"] = False
            details["router"] = "Router not initialised"

        # S2: ModelHub
        components["model_hub"] = self._model_hub is not None
        if self._model_hub is None:
            details["model_hub"] = "ModelHub not initialised"

        # S3: Fabric
        components["shared_fabric"] = self._shared_fabric is not None
        if self._shared_fabric is None:
            details["shared_fabric"] = "Shared Fabric not initialised"

        # S4: Bridge
        components["bridge"] = self._bridge is not None
        if self._bridge is None:
            details["bridge"] = "Bridge not initialised"

        # S5: Orchestrator
        components["orchestrator"] = self._orchestrator is not None
        if self._orchestrator is None:
            details["orchestrator"] = "Orchestrator not initialised"

        # S6: Planner
        components["planner"] = self._planner is not None
        if self._planner is None:
            details["planner"] = "Planner not initialised"

        # S7: Planner task
        if self._planner_task is not None:
            task_alive = not self._planner_task.done()
            components["planner_task"] = task_alive
            if not task_alive:
                exc = self._planner_task.exception() if not self._planner_task.cancelled() else None
                detail = f"crashed: {exc}" if exc else "stopped"
                details["planner_task"] = f"Planner task {detail}"
        else:
            components["planner_task"] = False
            details["planner_task"] = "Planner task not started"

        # Sessions
        components["sessions"] = True  # sessions existing is OK
        session_count = len(self._sessions)
        if session_count > 0:
            details["sessions"] = f"{session_count} active session(s)"

        section_update_enabled = bool(
            getattr(self._config, "enable_section_update_worker", False)
        ) and str(
            getattr(self._config, "section_update_worker_mode", "off") or "off"
        ).strip().lower() not in {
            "",
            "off",
            "disabled",
            "none",
        }
        if section_update_enabled:
            missing: list[str] = []
            stopped: list[str] = []
            for sid, session in self._sessions.items():
                worker = getattr(session, "section_update_worker", None)
                if worker is None:
                    missing.append(sid)
                elif not bool(getattr(worker, "is_running", False)):
                    stopped.append(sid)
            components["section_update_workers"] = not missing and not stopped
            details["section_update_workers"] = (
                f"active={session_count - len(missing) - len(stopped)} "
                f"missing={len(missing)} stopped={len(stopped)}"
            )
        else:
            components["section_update_workers"] = True

        healthy = all(components.values())
        return HealthStatus(
            healthy=healthy,
            components=components,
            details=details,
        )

    # ------------------------------------------------------------------
    # ISessionManagerPort
    # ------------------------------------------------------------------

    async def create_session(
        self,
        session_id: str = "",
        device_id: str | None = None,
    ) -> SessionInstance:
        """Create a new session with all Tier 2 components (P1→P6).

        Slice 3: If ``session_id`` is empty and ``_session_registry``
        exists, the ID is generated via ``registry.create()``.
        Explicit ``session_id`` values (CLI, tests) bypass the registry.

        Issue 2.4.3 #5: If ``_validate_session()`` fails after the session
        is registered, the zombie session is destroyed before re-raising.

        Args:
            session_id: Unique identifier for the session (empty = auto).
            device_id: Optional device identifier.

        Returns:
            The newly created ``SessionInstance``.

        Raises:
            RuntimeError: If the kernel is not running.
            ValueError: If a session with the given ID already exists.
            TypeError: If the session fails port validation (after cleanup).
        """
        # ── Slice 5 / Slice 3: resolve session ID from registry ──
        # Slice 5: restore most-recent session on reboot so session_id
        #          stays stable across restarts. Falls back to create
        #          when no prior sessions exist (first boot / deleted).
        if not session_id and self._session_registry is not None:
            most_recent = self._session_registry.get_most_recent()
            if most_recent is not None:
                session_id = most_recent["session_id"]
                self._session_registry.touch(session_id)  # G3: update last_active on restore
                logger.info(
                    "create_session: restoring session %s (title=%r, turns=%d)",
                    session_id,
                    most_recent.get("title"),
                    most_recent.get("turn_count", 0),
                )
            else:
                session_id = self._session_registry.create(title="New Chat", origin="web")
                logger.info(
                    "create_session: new session %s (first boot or all sessions deleted)",
                    session_id,
                )
        elif not session_id:
            # Fallback: no registry available (kernel.db disabled / test mode)
            session_id = f"kernel-{uuid.uuid4().hex[:8]}"
            logger.warning("create_session: no registry — using random session_id=%s", session_id)

        # ── existing guards (unchanged) ──
        if not self._running:
            raise RuntimeError("Kernel not running")
        if session_id in self._sessions:
            raise ValueError(f"Session '{session_id}' already exists")
        if len(self._sessions) >= self._config.max_sessions:
            raise RuntimeError(
                f"Maximum session limit reached ({self._config.max_sessions}). "
                "Destroy an existing session before creating a new one."
            )
        session = await self._create_session_tier2(session_id, device_id)
        try:
            self._validate_session(session)
        except Exception:
            # Issue 2.4.3 #5: Zombie session cleanup.
            try:
                await self.destroy_session(session_id)
            except Exception:
                logger.warning(
                    "create_session(%s): cleanup after validation failure also failed",
                    session_id,
                )
            raise
        return session

    async def destroy_session(self, session_id: str) -> None:
        """Destroy a session, tearing down Tier 2 components in reverse order.

        Issue 2.4.3 enhancements:
            - #7: Per-step timeouts on async teardown operations.
            - #10: Short drain period before closing the session bus.

        Sequence (reverse P6→P1):
            1. Remove from registry (``_sessions.pop``) → logs ``P6_teardown_start``
            2. Reverse P3.5: Uninstall SelfModel handle
            3. Reverse P5: Stop MemoryWriter → logs ``P5_teardown_complete``
            4. Reverse P4: Stop Concierge (FSM + consumer tasks) → logs ``P4_teardown_complete``
            5. Reverse P1.5: Shutdown per-session HIL service
            6. Reverse P3: ``Fabric.shutdown()`` (health_checker + module_loader) → logs ``P3_teardown_complete``
            7. Reverse P2: Checkpoint + stop SessionState → logs ``P2_teardown_complete``
            8. Reverse P1: Close per-session Bus + Router → logs ``P1_teardown_complete``

        Each step is individually guarded — teardown continues even if
        one step fails.  All errors are collected and logged.

        Args:
            session_id: The session to destroy.

        Raises:
            KeyError: If no session with that ID exists.
        """
        session = self._sessions.pop(session_id)  # KeyError if missing
        self._log_lifecycle("P6_teardown_start", f"session:{session_id}")
        errors: list[Exception] = []

        # Reverse P3.5: uninstall selfmodel handle (M5.E3.I3).
        # Done first so the gate is removed from dispatchers before
        # Concierge is stopped, preventing in-flight calls from
        # hitting a half-torn-down handle.
        sm_handle = getattr(session, "self_model", None)
        if sm_handle is not None:
            try:
                sm_handle.uninstall_from_session()
            except Exception as exc:
                errors.append(exc)
                logger.warning(
                    "destroy_session(%s): selfmodel uninstall failed: %s",
                    session_id,
                    exc,
                )

        grounding_handle = getattr(session, "grounding", None)
        if grounding_handle is not None:
            try:
                grounding_handle.uninstall_from_session()
            except Exception as exc:
                errors.append(exc)
                logger.warning(
                    "destroy_session(%s): grounding uninstall failed: %s",
                    session_id,
                    exc,
                )
            try:
                await asyncio.wait_for(
                    grounding_handle.shutdown(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
            except Exception as exc:
                errors.append(exc)
                logger.warning(
                    "destroy_session(%s): grounding shutdown failed: %s",
                    session_id,
                    exc,
                )

        spatial_handle = getattr(session, "spatial", None)
        if spatial_handle is not None:
            try:
                spatial_handle.uninstall_from_session()
            except Exception as exc:
                errors.append(exc)
                logger.warning(
                    "destroy_session(%s): spatial uninstall failed: %s",
                    session_id,
                    exc,
                )
            try:
                await asyncio.wait_for(
                    spatial_handle.shutdown(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
            except Exception as exc:
                errors.append(exc)
                logger.warning(
                    "destroy_session(%s): spatial shutdown failed: %s",
                    session_id,
                    exc,
                )

        temporal_handle = getattr(session, "temporal", None)
        if temporal_handle is not None:
            try:
                temporal_handle.uninstall_from_session()
            except Exception as exc:
                errors.append(exc)
                logger.warning(
                    "destroy_session(%s): temporal uninstall failed: %s",
                    session_id,
                    exc,
                )
            try:
                await asyncio.wait_for(
                    temporal_handle.shutdown(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
            except Exception as exc:
                errors.append(exc)
                logger.warning(
                    "destroy_session(%s): temporal shutdown failed: %s",
                    session_id,
                    exc,
                )

        # Reverse P5.5: stop section-update worker before MemoryWriter so any
        # queued background apply cannot call writer_port during teardown.
        section_update_worker = getattr(session, "section_update_worker", None)
        if section_update_worker is not None and hasattr(section_update_worker, "stop"):
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        section_update_worker.stop,
                        timeout_s=_TEARDOWN_TIMEOUT,
                    ),
                    timeout=_TEARDOWN_TIMEOUT,
                )
            except Exception as exc:
                errors.append(exc)
                logger.warning(
                    "destroy_session(%s): SectionUpdateBackgroundWorker stop failed: %s",
                    session_id,
                    exc,
                )
            self._log_lifecycle("P5_5_teardown_complete", f"session:{session_id}")

        # Reverse P5: Stop MemoryWriter
        try:
            await asyncio.wait_for(
                session.memory_writer.stop(),
                timeout=_TEARDOWN_TIMEOUT,
            )
        except Exception as exc:
            errors.append(exc)
            logger.warning("destroy_session(%s): MemoryWriter stop failed: %s", session_id, exc)
        self._log_lifecycle("P5_teardown_complete", f"session:{session_id}")

        # Reverse P4: Stop Concierge
        try:
            await asyncio.wait_for(
                session.concierge.stop(),
                timeout=_TEARDOWN_TIMEOUT,
            )
        except Exception as exc:
            errors.append(exc)
            logger.warning("destroy_session(%s): Concierge stop failed: %s", session_id, exc)
        self._log_lifecycle("P4_teardown_complete", f"session:{session_id}")

        # Reverse P1.5: Shutdown per-session HIL service (cancels pending
        # futures and unsubscribes from session_bus). Run AFTER Concierge
        # stop so the FSM cannot create new HIL requests, and BEFORE
        # session_bus.close so the unsubscribe call has a live bus.
        session_hil = getattr(session, "hil_port", None)
        if session_hil is not None and hasattr(session_hil, "shutdown"):
            try:
                await asyncio.wait_for(
                    session_hil.shutdown(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
            except Exception as exc:
                errors.append(exc)
                logger.warning(
                    "destroy_session(%s): HIL service shutdown failed: %s",
                    session_id,
                    exc,
                )

        # 3.3.3: Cancel any in-flight DeltaAggregator batch timer.
        # ``flush()`` cancels ``_timer`` and emits any pending batch.
        try:
            agg = getattr(session, "delta_aggregator", None)
            if agg is not None and hasattr(agg, "flush"):
                await asyncio.wait_for(agg.flush(), timeout=_TEARDOWN_TIMEOUT)
        except Exception as exc:
            errors.append(exc)
            logger.warning("destroy_session(%s): DeltaAggregator flush failed: %s", session_id, exc)

        # 3.3.4: Explicitly unsubscribe DeadLetterConsumer before bus.close()
        # so the subscription handle is released cleanly.
        try:
            dlc = getattr(session, "dead_letter_consumer", None)
            if dlc is not None and hasattr(dlc, "stop"):
                dlc.stop()
        except Exception as exc:
            errors.append(exc)
            logger.warning(
                "destroy_session(%s): DeadLetterConsumer stop failed: %s", session_id, exc
            )

        # 3.3.1: Reverse P3 -- shutdown per-session Fabric (was previously
        # documented as "no explicit teardown"; Fabric.shutdown() exists and
        # stops the health checker + module loader).
        try:
            fabric = getattr(session, "fabric", None)
            if fabric is not None and hasattr(fabric, "shutdown"):
                await asyncio.wait_for(fabric.shutdown(), timeout=_TEARDOWN_TIMEOUT)
        except Exception as exc:
            errors.append(exc)
            logger.warning("destroy_session(%s): Fabric shutdown failed: %s", session_id, exc)
        self._log_lifecycle("P3_teardown_complete", f"session:{session_id}")

        # 3.3.2: Reverse P2 -- Stop SessionState. ``stop()`` is synchronous and
        # performs SQLite WAL checkpoint writes; offload to a worker thread
        # with a timeout so it cannot block the event loop (and freeze every
        # other active session's I/O) during shutdown.
        try:
            await asyncio.wait_for(
                asyncio.to_thread(session.session_state.stop),
                timeout=_TEARDOWN_TIMEOUT,
            )
        except Exception as exc:
            errors.append(exc)
            logger.warning("destroy_session(%s): SessionState stop failed: %s", session_id, exc)
        self._log_lifecycle("P2_teardown_complete", f"session:{session_id}")

        # Issue 2.4.3 #10: Graceful drain — yield to event loop so any
        # in-flight bus callbacks complete before closing the bus.
        await asyncio.sleep(0)

        # Reverse P1: Close per-session Bus + Router
        try:
            session.bus.close()
        except Exception as exc:
            errors.append(exc)
            logger.warning("destroy_session(%s): Bus close failed: %s", session_id, exc)

        try:
            session.router.close()
        except Exception as exc:
            errors.append(exc)
            logger.warning("destroy_session(%s): Router close failed: %s", session_id, exc)
        self._log_lifecycle("P1_teardown_complete", f"session:{session_id}")

        # Slice 6: registry.delete is NOT called here — destroy_session is a
        # runtime teardown (switch, shutdown, zombie cleanup).  Persistent
        # deletion of st_sessions + st_chat_messages only happens via
        # delete_session_permanently() or the REST DELETE endpoint.

        if errors:
            logger.error(
                "destroy_session(%s): %d error(s) during teardown",
                session_id,
                len(errors),
            )

    async def delete_session_permanently(self, session_id: str) -> None:
        """Tear down runtime AND delete persistent record from kernel.db.

        Slice 6: Called from the REST DELETE endpoint when a user
        explicitly deletes a chat.  Unlike ``destroy_session`` (which
        only tears down runtime components), this method also removes
        the ``st_sessions`` row and cascade-deletes all
        ``st_chat_messages`` rows.

        If the session is currently active, ``destroy_session`` is
        called first to stop the bus, SSM, concierge, and workers.
        """
        if session_id in self._sessions:
            await self.destroy_session(session_id)
        if self._session_registry is not None:
            self._session_registry.delete(session_id)

    async def replace_session(self, old_session_id: str, new_session_id: str) -> SessionInstance:
        """Stage a new session, hand off, then destroy old.  Create-before-destroy.

        Slice 6: Staged activation for session switch.  The new session
        is fully created and validated BEFORE the old session is torn
        down.  If new-session creation or validation fails, the old
        session is untouched and the caller receives an error.

        Phases:
            A. Deferred — old SSM stays fully alive.  Checkpoint happens
               inside destroy_session() during Phase D, AFTER new is validated.
            B. Create new session via ``_create_session_tier2``.
            C. Validate new session.
               → FAIL: destroy new (rollback), old untouched → RuntimeError.
               → PASS: continue.
            D. Destroy old session (only after new is proven valid).
            E. Touch registry on new session.

        Args:
            old_session_id: Currently active session to checkpoint and retire.
            new_session_id: Target session to activate (must exist in registry).

        Returns:
            The newly created ``SessionInstance``.

        Raises:
            KeyError: If ``old_session_id`` is not active.
            ValueError: If old == new.
            RuntimeError: If kernel is not running, or new session creation
                          or validation fails.
        """
        if not self._running:
            raise RuntimeError("Kernel not running")
        if old_session_id == new_session_id:
            raise ValueError(f"Already active: {new_session_id}")
        if old_session_id not in self._sessions:
            raise KeyError(f"Old session not active: {old_session_id}")

        logger.info("replace_session: staging switch %s → %s", old_session_id, new_session_id)

        # ── Phase A: Deferred — old SSM is NOT stopped here. ──
        # The old session stays fully alive (bus, SSM, concierge, MW, worker
        # all running) until Phase D when new is proven valid.  If Phase A
        # checkpointed the old SSM and Phase B/C failed, the coordinator
        # would still point to a stopped SSM — a half-dead session.
        #
        # Instead, SSM.stop() (which checkpoints) happens inside
        # destroy_session() during Phase D, AFTER new is validated.
        old_session = self._sessions[old_session_id]

        # ── Phase B: Create new session in staging ──
        new_session = None
        try:
            new_session = await self._create_session_tier2(new_session_id)
        except Exception:
            logger.error("replace_session: new session creation failed, old intact", exc_info=True)
            raise RuntimeError(
                f"Failed to create session '{new_session_id}'. "
                f"Current session '{old_session_id}' is still active."
            ) from None

        # ── Phase C: Validate new session ──
        try:
            self._validate_session(new_session)
        except Exception:
            logger.error(
                "replace_session: new session validation failed, rolling back",
                exc_info=True,
            )
            try:
                await self.destroy_session(new_session_id)
            except Exception:
                logger.warning("replace_session: rollback destroy failed", exc_info=True)
            raise RuntimeError(
                f"Session '{new_session_id}' failed validation. "
                f"Current session '{old_session_id}' is still active."
            ) from None

        # ── Phase D: Hand-off — destroy old, commit new ──
        logger.info("replace_session: new session valid, retiring old %s", old_session_id)
        await self.destroy_session(old_session_id)

        # ── Phase E: Touch registry ──
        if self._session_registry is not None:
            self._session_registry.touch(new_session_id)

        logger.info("replace_session: switch complete %s → %s", old_session_id, new_session_id)
        return new_session

    def get_session(self, session_id: str) -> SessionInstance | None:
        """Look up a session by ID."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[str]:
        """Return all active session IDs."""
        return list(self._sessions.keys())

    # ------------------------------------------------------------------
    # M5.E3.I3: per-session selfmodel helpers
    # ------------------------------------------------------------------
    def _derive_session_actor(
        self,
        ssm: Any,
        session_id: str,
        device_id: str | None,
    ) -> tuple[str, str]:
        """Resolve ``(actor_id, device_id)`` for selfmodel binding.

        Reads ``MetaSection.identity`` from the session's
        ``SessionStateManager`` for the canonical user/device pair.
        Falls back to:

        * ``actor_id``: ``meta.user_id`` -> ``"actor:{session_id}"``.
        * ``device_id``: caller-provided ``device_id`` ->
          ``meta.device_id`` -> ``""``.

        Failures are swallowed so a missing meta section never blocks
        session creation.
        """
        actor_id = f"actor:{session_id}"
        device_resolved = device_id or ""
        # Prefer the explicitly-resolved member id supplied via KernelConfig.
        config_member_id = getattr(self._config, "active_member_id", "") or ""
        if config_member_id:
            actor_id = config_member_id
        try:
            meta = ssm.get_section("meta")
        except Exception:
            meta = None
        if meta is None:
            return actor_id, device_resolved
        try:
            identity = meta.identity
        except Exception:
            return actor_id, device_resolved
        if identity is not None:
            user = getattr(identity, "user_id", "") or ""
            if user:
                actor_id = user
            if not device_resolved:
                device_resolved = getattr(identity, "device_id", "") or ""
        return actor_id, device_resolved

    # ------------------------------------------------------------------
    # Private helpers (stubs)
    # ------------------------------------------------------------------

    def _validate_ports(self) -> None:
        """Validate Tier 1 shared components satisfy their port protocols.

        Issue 2.1.6: construction-time port type validation.
        Collects ALL failures and reports them together.

        Real ``isinstance()`` enforcement is used for components that
        already publish a ``@runtime_checkable`` Protocol
        (``IBus``, ``IMailboxRouter``). Components without a single
        consolidated subsystem Protocol (ModelHub has 4 distinct
        consumer-side Protocols, Fabric/Orchestrator/Planner are
        concrete classes) fall back to structural ``hasattr`` checks
        on the public methods the kernel itself calls.

        Raises:
            TypeError: If any component fails validation.  Message lists
                every failing component.
        """
        failures: list[str] = []

        # Strict isinstance() against published bus subsystem Protocols.
        if self._bus is not None and not isinstance(self._bus, IBus):
            failures.append(
                f"Port validation failed: _bus ({type(self._bus).__name__}) "
                f"does not satisfy k1.bus.ports.bus.IBus"
            )
        if self._router is not None and not isinstance(self._router, IMailboxRouter):
            failures.append(
                f"Port validation failed: _router "
                f"({type(self._router).__name__}) does not satisfy "
                f"k1.bus.ports.mailbox.IMailboxRouter"
            )

        # Structural checks for components without a unified Protocol.
        # Each tuple is (field_name, value, required_attr).
        #
        # K8: ``k1.kernel.ports`` defines lifecycle Protocols (startup/
        # shutdown/get_hub, get_service, start) for KernelService's *intended*
        # hexagonal boundary. The production objects returned by the factories
        # expose a different runtime surface (execute/stream_execute for
        # ModelHub, process for Orchestrator, start for Planner). Until the
        # Protocols are updated to match the factory outputs, we use structural
        # ``hasattr`` checks against the methods that KernelService itself
        # invokes, rather than isinstance against the kernel port Protocols.
        structural_checks: list[tuple[str, object, str]] = [
            ("_model_hub", self._model_hub, "execute"),
            ("_shared_fabric", self._shared_fabric, "execute"),
            ("_bridge", self._bridge, "is_connected"),
            ("_orchestrator", self._orchestrator, "process"),
            ("_planner", self._planner, "start"),
        ]
        for field_name, value, attr in structural_checks:
            if value is not None and not hasattr(value, attr):
                failures.append(
                    f"Port validation failed: {field_name} "
                    f"({type(value).__name__}) missing required "
                    f"attribute '{attr}'"
                )
        if failures:
            raise TypeError("KernelService port validation failed:\n" + "\n".join(failures))

    def _validate_session(self, session: SessionInstance) -> None:
        """Validate a Tier 2 SessionInstance's components.

        Called after ``_create_session_tier2()`` to ensure all per-session
        adapters satisfy their expected interfaces.

        Args:
            session: The newly created ``SessionInstance`` to validate.

        Raises:
            TypeError: If any session component fails validation.
        """
        checks: list[tuple[str, object, str]] = [
            ("bus", session.bus, "publish"),
            ("bus", session.bus, "subscribe"),
            ("router", session.router, "register"),
            ("session_state", session.session_state, "get_section"),
            ("fabric", session.fabric, "execute"),
        ]
        failures: list[str] = []
        for field_name, value, attr in checks:
            if value is not None and not hasattr(value, attr):
                failures.append(
                    f"Session port validation failed: {field_name} "
                    f"({type(value).__name__}) missing required "
                    f"attribute '{attr}'"
                )
        if failures:
            raise TypeError(
                f"SessionInstance '{session.session_id}' validation "
                f"failed:\n" + "\n".join(failures)
            )

    def _verify_orchestrator_monitor_binding(self) -> None:
        """Verify ExecutionMonitor is wired into the DAG guard pipeline.

        E6 removed the legacy ``_service_ref`` late-binding (the
        OrchestratorService no longer reaps pending HIL requests, so
        ExecutionMonitor needs only its ``hil_port`` injected via the
        factory's ``_build_guards`` step). This method now checks only
        that the guard pipeline is present and includes a 4th guard slot
        that exposes a ``decide()`` method (the ExecutionMonitor surface).

        Raises:
            RuntimeError: If ``_orchestrator`` is None or the guard
                pipeline is missing its monitor entry.
        """
        if self._orchestrator is None:
            raise RuntimeError(
                "Cannot verify ExecutionMonitor: _orchestrator is None. "
                "Tier 1 startup (Issue 2.2.5) must run first."
            )
        dag_executor = getattr(self._orchestrator, "_dag_executor", None)
        if dag_executor is None:
            raise RuntimeError(
                "Cannot verify ExecutionMonitor: " "_orchestrator._dag_executor is None."
            )
        guards = getattr(dag_executor, "_guards", None)
        if not guards or len(guards) < 4:
            raise RuntimeError(
                "Cannot verify ExecutionMonitor: "
                f"_dag_executor._guards has {len(guards) if guards else 0} "
                f"entries, expected >= 4."
            )
        monitor = guards[3]
        if not callable(getattr(monitor, "after_step", None)):
            raise RuntimeError(
                "ExecutionMonitor (guard slot 3) does not expose after_step(); "
                "guard pipeline wiring failed."
            )

    def _verify_planner_mailbox_binding(self) -> None:
        """Verify PlannerAgent's mailbox has its PipelineController bound.

        ``PlannerFactory._wire()`` (Step 8b) calls
        ``mailbox_port.set_pipeline_controller(pipeline)`` so this verification
        normally passes by construction. Kept as a defensive post-wire check
        in case a custom factory or test harness builds the agent without
        going through the standard wire path.

        Uses the public ``mailbox`` property on ``PlannerAgent`` and
        ``has_pipeline_controller()`` if available, otherwise duck-types
        for ``_pipeline_controller`` attribute existence.

        Raises:
            RuntimeError: If ``_planner`` is None or the controller is
                not bound on the mailbox.
        """
        if self._planner is None:
            raise RuntimeError(
                "Cannot verify MailboxAdapter binding: _planner is None. "
                "Tier 1 startup (Issue 2.2.6) must run first."
            )
        mailbox = self._planner.mailbox
        bound = False
        if hasattr(mailbox, "has_pipeline_controller"):
            bound = bool(mailbox.has_pipeline_controller())
        else:
            bound = getattr(mailbox, "_pipeline_controller", None) is not None
        if not bound:
            raise RuntimeError(
                "MailboxAdapter pipeline controller not bound after "
                "Planner construction. PlannerFactory._wire() Step 8b "
                "should have called set_pipeline_controller()."
            )

    def _verify_planner_task_running(self) -> None:
        """Issue 2.1.9: Verify PlannerAgent background task is alive.

        PL-B1: ``PlannerFactory.create_production()`` returns a fully wired
        but **IDLE** agent.  The factory explicitly does NOT call
        ``agent.start()`` (confirmed by code audit — factory comments state
        "Caller must invoke ``asyncio.create_task(agent.start())``").

        ``KernelService._startup_tier1()`` **MUST**::

            self._planner_task = asyncio.create_task(
                planner.start(), name="planner-agent"
            )

        ``start()`` (``planner_agent.py`` L569) is a long-running coroutine:
        INIT → subscribe 4 event topics → ``pipeline.reset()`` → set
        ``_running = True`` → CRASH_RECOVERY (V1 no-op) → ``_run_loop()``
        (infinite ``while _running`` dequeue loop).

        GOTCHA: ``start()`` MUST be wrapped in ``asyncio.create_task()``,
        **NOT** awaited directly — that would block startup forever.

        Graceful shutdown uses ``PlannerAgent.stop()`` (L654):
        sets ``_running = False``, drains mailbox, unsubscribes events.
        Alternatively, ``task.cancel()`` raises ``CancelledError`` in the
        dequeue/execute await.

        Raises:
            RuntimeError: If ``_planner_task`` is None, done, or cancelled.
        """
        if self._planner_task is None:
            raise RuntimeError(
                "Planner background task not started: _planner_task is None. "
                "Call asyncio.create_task(planner.start()) in _startup_tier1()."
            )
        if self._planner_task.done():
            exc = self._planner_task.exception() if not self._planner_task.cancelled() else None
            detail = f" (exception: {exc})" if exc else ""
            raise RuntimeError(
                f"Planner background task is no longer running{detail}. "
                "PL-B1: agent.start() should run indefinitely."
            )

    def _verify_activity_prompt_system(self, prompt_system: Any, *, scope: str) -> int:
        """Log and optionally enforce activity prompt inventory visibility."""
        raw_count = getattr(prompt_system, "template_count", 0)
        try:
            template_count = int(raw_count)
        except (TypeError, ValueError):
            template_count = 0

        template_names: list[str] = []
        list_names = getattr(prompt_system, "list_names", None)
        if callable(list_names):
            try:
                template_names = [str(name) for name in list_names()]
            except Exception:
                logger.debug(
                    "Activity profile prompt inventory name listing failed (scope=%s)",
                    scope,
                    exc_info=True,
                )

        enabled = bool(getattr(self._config, "enable_activity_profiles", True))
        strict = bool(getattr(self._config, "enable_activity_profiles_strict", False))
        if not enabled:
            logger.info(
                "Activity profiles disabled by config (scope=%s, templates=%d)",
                scope,
                template_count,
            )
            return template_count

        if template_count <= 0:
            message = (
                "Activity profile prompt store is empty "
                f"(scope={scope}, strict={strict}). Native family tools remain available."
            )
            if strict:
                raise RuntimeError(message)
            logger.warning(message)
            return template_count

        logger.info(
            "Activity profile prompt store ready (scope=%s, templates=%d, names=%s)",
            scope,
            template_count,
            template_names[:20],
        )
        return template_count

    def _verify_planner_orchestrator_crosswire(self) -> None:
        """Issue 2.1.9 (S6b): Verify Orchestrator↔Planner cross-wire.

        ``OrchestratorFactory`` defaults to ``MockPlannerAdapter()`` as the
        planner port (``k1/orchestrator/adapters/mock_planner_adapter.py``).
        After both Orchestrator and Planner are created, ``_startup_tier1()``
        must replace it with a real ``PlannerAdapter``::

            from k1.orchestrator.adapters.planner_adapter import PlannerAdapter
            orchestrator._planner_port = PlannerAdapter(
                planner.get_mailbox(), cb_planner=circuit_breaker
            )

        ``PlannerAdapter.__slots__`` = ``("_mailbox", "_cb")`` — no setter,
        but ``OrchestratorService._planner_port`` is in ``__slots__`` and
        reassignable via direct attribute assignment.

        NOTE: Plan said constructor kwarg is ``circuit_breaker``.  Actual
        constructor parameter name is ``cb_planner``.

        Raises:
            RuntimeError: If ``_orchestrator`` is None or ``_planner_port``
                is still a ``MockPlannerAdapter``.
        """
        if self._orchestrator is None:
            raise RuntimeError(
                "Cannot verify Planner cross-wire: _orchestrator is None. "
                "Tier 1 startup (Issue 2.2.5) must run first."
            )
        planner_port = getattr(self._orchestrator, "_planner_port", None)
        if planner_port is None:
            raise RuntimeError(
                "Cannot verify Planner cross-wire: " "_orchestrator._planner_port is None."
            )
        # MockPlannerAdapter is the factory default — must be replaced.
        port_type_name = type(planner_port).__name__
        if port_type_name == "MockPlannerAdapter":
            raise RuntimeError(
                "Orchestrator still has MockPlannerAdapter as _planner_port. "
                "S6b cross-wire not completed — replace with real "
                "PlannerAdapter(planner.get_mailbox(), cb_planner=cb)."
            )

    async def _startup_tier1(self) -> None:
        """Execute S1→S7 + S6b shared component bootstrap.

        Issue 2.4.3 #1: Each phase is wrapped so that failure at step N
        triggers reverse-order cleanup of steps 1..N-1.  ``_running`` is
        never set to True on failure.

        Issue 2.4.3 #9: Planner task gets a done-callback watchdog that
        logs if the task crashes after startup.

        Boot order enforced by data dependency:
        S1 → S2 → S3 → S4 → S5 → S6 → S6b → S7
        """
        # ── S1: Bus + AsyncBusBridge + MailboxRouter ──────────
        # W2: Optionally wire a SQLite WAL outbox for durable topics.
        bus_outbox = None
        durable_topics = None
        if self._config.bus_outbox_path and self._config.bus_durable_topics:
            from k1.bus.outbox import BusOutbox

            bus_outbox = BusOutbox(self._config.bus_outbox_path)
            durable_topics = set(self._config.bus_durable_topics)
        bus = BusFactory.create_local_ordered(
            capture=self._config.capture_bus,
            outbox=bus_outbox,
            durable_topics=durable_topics,
        )
        self._bus = bus
        self._router = BusFactory.create_mailbox_router()
        self._async_bus = AsyncBusBridge(bus)
        self._log_lifecycle("S1_complete", "Bus+Router+AsyncBusBridge")

        # ── S2: ModelHub (with auxiliary ports + declarative provider load) ──
        # P2.3: replaces the prior ``create_with_ports`` + private
        # ``_register_model_hub_plugins_from_env`` two-step with the single
        # declarative ``ModelHubFactory.from_config`` entry point. The
        # ``model_mode == "hub"`` gate is preserved at the call site so
        # non-hub modes still construct the hub without loading plugins.
        try:
            mh_ports = {
                "credential_port": CredentialStoreAdapter(),
                # P5.4: bind ModelHub IEventPort to K1 bus.
                "event_port": MHEventBusAdapter(bus=self._bus),
                # P5.5: real per-session SS via shim. ModelHub reads
                # 3.1.2: Replace _FirstSessionSSMShim (which silently
                # returned an arbitrary session's data when multiple
                # sessions exist) with an explicit null shim. Logs WARNING
                # once so the degradation is visible. Real per-session
                # wiring requires threading HubRequest.session_id through
                # IStateReadPort -- deferred since RequestRouter has no
                # state-driven consumer today.
                "state_read_port": SessionStateProdAdapter(
                    manager=_NullSSMShim(),
                ),
                "metrics_port": PrometheusAdapter(),
                "config_port": ConfigAdapter(),
                # M01-B: health adapter injected so the kernel can inspect
                # hub health and so the factory uses this instance rather
                # than constructing a fresh HealthReportAdapter internally.
                "health_port": MHHealthReportAdapter(),
            }
            if self._config.model_mode == "hub":
                self._model_hub, load_result = await ModelHubFactory.from_config(
                    ProviderConfig.from_env(),
                    ports=mh_ports,
                )
                logger.info(
                    "ModelHub provider load: registered=%s skipped=%s failed=%s",
                    load_result.registered,
                    load_result.skipped,
                    load_result.failed,
                )
            elif self._config.model_mode == "test":
                # ── TEST-ONLY PATH ─────────────────────────────────────
                # Hub starts with zero providers; register an in-process
                # StubProviderPlugin so the Concierge ReAct loop has a
                # provider that satisfies every capability (TOOL_CALL,
                # CHAT, ...). Without this, the router throws
                # NoEligibleProviderError on the first turn and the FSM
                # jams in DISPATCHING. NEVER select model_mode="test"
                # for production deployments — the stub returns a
                # canned "OK" string and does no real reasoning.
                self._model_hub = ModelHubFactory.create_with_ports(ports=mh_ports)
                from k1.model_hub.plugins.stub_plugin import (
                    StubProviderPlugin,
                    build_stub_manifest,
                )

                stub_manifest = build_stub_manifest()
                stub_plugin = StubProviderPlugin()
                await stub_plugin.initialize(stub_manifest)
                self._model_hub.register_plugin(stub_manifest, stub_plugin)
                logger.warning(
                    "ModelHub: TEST MODE — registered StubProviderPlugin "
                    "(provider=%s, model=%s). This is NOT a production "
                    "configuration.",
                    stub_manifest.provider_id,
                    stub_manifest.models[0].id,
                )
            else:
                # Fail loudly on unknown modes rather than silently
                # booting with no providers and dying on the first turn.
                raise ValueError(
                    f"KernelConfig.model_mode must be 'hub' or 'test', "
                    f"got {self._config.model_mode!r}"
                )
        except Exception:
            # S1 created — clean up.
            self._bus.close()
            self._router.close()
            raise
        self._log_lifecycle("S2_complete", "ModelHub")

        # ── S2.5: Unified HIL service (E7.M1.1) ───────────────
        # Constructed after S2 (ModelHub) and before S4 (Bridge) so all four
        # downstream subsystems (Fabric/Concierge/Planner/Orchestrator)
        # receive the SAME instance via their factories. If
        # ``enable_hil_service`` is False the factories receive ``None`` and
        # each falls back to its internal _NullHILAdapter — preserving
        # pre-E7 behaviour for tests that cannot reply to HIL requests.
        if self._config.enable_hil_service:
            try:
                hil_event_port = KernelHILEventAdapter(bus, loop=asyncio.get_running_loop())
                hil_config = HILConfig(
                    max_clarification_rounds=self._config.hil_max_clarification_rounds,
                    clarification_timeout_ms=self._config.hil_clarification_timeout_ms,
                    approval_timeout_ms=self._config.hil_approval_timeout_ms,
                    needs_human_timeout_ms=self._config.hil_needs_human_timeout_ms,
                    override_timeout_ms=self._config.hil_override_timeout_ms,
                    capability_gate_timeout_ms=self._config.hil_capability_gate_timeout_ms,
                    enable_audit_topic=self._config.hil_enable_audit_topic,
                    enable_llm_synthesis=self._config.hil_enable_llm_synthesis,
                )
                self._hil_service = HumanInTheLoopService(
                    event_port=hil_event_port,
                    ledger=HILLedgerAdapter(None),
                    suspension_mgr=None,
                    safety_policy=SafetyBandPolicy(),
                    config=hil_config,
                    llm_port=None,
                )
                logger.info(
                    "HIL: HumanInTheLoopService constructed (clarification_rounds=%d)",
                    hil_config.max_clarification_rounds,
                )
            except Exception:
                self._bus.close()
                self._router.close()
                raise
        else:
            self._hil_service = None
            logger.info("HIL: enable_hil_service=False — subsystems get None hil_port")
            self._log_lifecycle("S2.5_skipped", "HumanInTheLoopService")
        if self._hil_service is not None:
            self._log_lifecycle("S2.5_complete", "HumanInTheLoopService")

        # ── S2.6: k1.selfmodel bundle (M5.E3.I2) ──────────────
        # Constructed after S2.5 HIL and before S4 Bridge so the
        # shared HIL service is available to per-session handles
        # (P3.5). When ``enable_self_model`` is False, the field stays
        # ``None`` and ``create_session`` skips P3.5 entirely.
        if self._config.enable_self_model:
            try:
                self._self_model_bundle = build_self_model_bundle(
                    bus=self._async_bus,
                    hil_service=self._hil_service,
                    projection_db_path=self._config.selfmodel_projection_db_path,
                    space_id=self._config.selfmodel_space_id,
                )
                logger.info(
                    "selfmodel: bundle ready (db=%s, space=%s, safe_mode=%s)",
                    self._config.selfmodel_projection_db_path or "<memory>",
                    self._config.selfmodel_space_id,
                    self._self_model_bundle.safe_mode,
                )
            except Exception:
                # S2.6 failure: tear down everything created above.
                if self._hil_service is not None:
                    try:
                        await self._hil_service.shutdown()
                    except Exception:
                        pass
                self._bus.close()
                self._router.close()
                raise
        else:
            self._self_model_bundle = None
            logger.debug("selfmodel: enable_self_model=False; skipping S2.6")
            self._log_lifecycle("S2.6_skipped", "SelfModelServiceBundle")
        if self._self_model_bundle is not None:
            self._log_lifecycle("S2.6_complete", "SelfModelServiceBundle")

        self._device_context_port = InMemoryDeviceContextPort()

        # ── S2.7: Temporal bundle (M1) ───────────────────────
        if self._config.enable_temporal:
            try:
                self._temporal_bundle = build_temporal_bundle(
                    bus=self._bus,
                    device_context_port=DeviceContextAdapter(self._device_context_port),
                )
                logger.info("temporal: bundle ready")
            except Exception:
                if self._self_model_bundle is not None:
                    try:
                        self._self_model_bundle.shutdown()
                    except Exception:
                        pass
                    self._self_model_bundle = None
                if self._hil_service is not None:
                    try:
                        await self._hil_service.shutdown()
                    except Exception:
                        pass
                self._bus.close()
                self._router.close()
                raise
        else:
            self._temporal_bundle = None
            logger.debug("temporal: enable_temporal=False; skipping S2.7")
            self._log_lifecycle("S2.7_skipped", "TemporalServiceBundle")
        if self._temporal_bundle is not None:
            self._log_lifecycle("S2.7_complete", "TemporalServiceBundle")

        # ── S4: Bridge (kernel-level IBridgePort) ─────────
        # S4 before S3 because Fabric needs a bridge adapter.
        # Three modes:
        #   k0_endpoint set    → LiveBridgeAdapter (HttpBridgeClient via BridgeRuntime)
        #   bridge_enabled     → SinkBridgeAdapter (offline outbox, default)
        #   neither            → OfflineBridgeAdapter (null object)
        try:
            if self._config.k0_endpoint:
                from k1.kernel.adapters.live_bridge_adapter import LiveBridgeAdapter

                live_adapter = LiveBridgeAdapter(
                    endpoint=self._config.k0_endpoint,
                    default_space_id=getattr(self._config, "selfmodel_space_id", "")
                    or "family:default",
                    default_actor=getattr(self._config, "active_member_id", "") or "",
                )
                await live_adapter.connect()
                self._bridge = live_adapter
                logger.info(
                    "K1 Kernel S4: bridge=LIVE (HttpBridgeClient → %s).",
                    self._config.k0_endpoint,
                )
                # E15.10: subscribe to tool_state.changed.v1 on K0 and
                # forward to the K1 bus so the web shell can push
                # "tool_refresh" to the browser.
                self._tool_sse_task = asyncio.create_task(
                    self._consume_tool_sse(),
                    name="k1-tool-sse-consumer",
                )
            elif self._config.bridge_enabled:
                self._bridge = SinkBridgeAdapter(
                    outbox_path=self._config.bridge_outbox_path,
                )
                logger.info(
                    "K1 Kernel S4: bridge=OFFLINE (SinkBridgeClient / outbox mode). "
                    "K0 ops will queue to %s. Live K0 requires HttpBridgeClient.",
                    self._config.bridge_outbox_path,
                )
            else:
                self._bridge = OfflineBridgeAdapter()
                logger.info("K1 Kernel S4: bridge=DISABLED (OfflineBridgeAdapter).")
        except Exception:
            self._bus.close()
            self._router.close()
            raise
        self._log_lifecycle("S4_complete", type(self._bridge).__name__)

        # ── S2.8: Spatial bundle (M3) ───────────────────────
        if self._config.enable_spatial:
            try:
                bridge_client = None
                get_client = getattr(self._bridge, "get_client", None)
                if callable(get_client):
                    bridge_client = get_client()
                self._spatial_bundle = build_spatial_bundle(
                    bus=self._bus,
                    device_context_port=SpatialDeviceContextAdapter(self._device_context_port),
                    bridge_client=bridge_client,
                )
                logger.info("spatial: bundle ready")
            except Exception:
                await self._bridge.disconnect()
                self._bus.close()
                self._router.close()
                raise
        else:
            self._spatial_bundle = None
            logger.debug("spatial: enable_spatial=False; skipping S2.8")
            self._log_lifecycle("S2.8_skipped", "SpatialServiceBundle")
        if self._spatial_bundle is not None:
            self._log_lifecycle("S2.8_complete", "SpatialServiceBundle")

        # ── S2.9: Grounding bundle (M1.5 transitional) ─────
        if self._config.enable_grounding:
            try:
                self._grounding_bundle = build_grounding_bundle(bus=self._bus)
                logger.info("grounding: bundle ready")
            except Exception:
                await self._bridge.disconnect()
                self._bus.close()
                self._router.close()
                raise
        else:
            self._grounding_bundle = None
            logger.debug("grounding: enable_grounding=False; skipping S2.9")
            self._log_lifecycle("S2.9_skipped", "GroundingServiceBundle")
        if self._grounding_bundle is not None:
            self._log_lifecycle("S2.9_complete", "GroundingServiceBundle")

        # ── P1.1/P1.4: SessionRoutingStateReader (shared by S3, S5, S6) ──
        session_routing_reader = SessionRoutingStateReader(
            session_lookup=lambda sid: (
                self._sessions[sid].session_state if sid in self._sessions else None
            ),
        )
        self._session_routing_reader = session_routing_reader

        # ── S2.10: Phase 1 Fabric stores (before S3) ──────────
        # Created BEFORE the shared Fabric so the factory can wire them
        # (step 21).  Standalone SQLite files — no bus/bridge/model-hub
        # dependency.  Gated behind enable_fabric_stores (default False).
        if self._config.enable_fabric_stores:
            try:
                from k1.fabric.stores.global_projection_store import (
                    GlobalProjectionStore,
                )
                from k1.fabric.stores.idempotency_store import IdempotencyStore

                gps = GlobalProjectionStore(self._config.global_projection_db_path or ":memory:")
                gps.open()
                self._global_projection_store = gps

                # Eager-warm the MiniLM embedding index so the first
                # resolve_situation call doesn't pay ~30s lazy-load cost.
                try:
                    gps.warmup_embedding_index()
                    self._log_lifecycle("S2.10_embedding_warm", "MiniLM-L6 index built")
                except Exception:
                    logger.warning(
                        "GPS embedding warmup failed — will lazy-load on first use",
                        exc_info=True,
                    )

                idem = IdempotencyStore(self._config.idempotency_db_path or ":memory:")
                idem.open()
                self._idempotency_store = idem
                self._log_lifecycle("S2.10_complete", "GlobalProjectionStore+IdempotencyStore")
            except Exception:
                await self._bridge.disconnect()
                self._bus.close()
                self._router.close()
                raise

        # ── S2.12: KernelDB (chat session persistence, Slice 1) ──
        if self._config.enable_kernel_db:
            try:
                from k1.kernel.adapters.kernel_db import KernelDB
                from k1.kernel.session_registry import SessionRegistry

                self._kernel_db = KernelDB(self._config.kernel_db_path)
                self._kernel_db.open()
                self._session_registry = SessionRegistry(self._kernel_db)
                self._log_lifecycle("S2.12_complete", "KernelDB+SessionRegistry")
            except Exception:
                await self._cleanup_tier1_partial()
                raise

        # ── S3: Shared Fabric ─────────────────────────────
        try:
            event_port = EventPortProdAdapter(bus)
            delta_bus = DeltaBusProdAdapter(bus)
            model_gateway = ModelGatewayBridgeAdapter(hub=self._model_hub)
            prompt_system = PromptSystemProdAdapter(prompts_dir="k1/contracts/prompts")
            self._verify_activity_prompt_system(prompt_system, scope="shared")
            self._prompt_system = prompt_system
            bridge_client = self._bridge.get_client()
            bridge_adapter = BridgeConnectionAdapter(client=bridge_client)

            self._shared_fabric = FabricFactory.create_shared(
                event_port=event_port,
                bridge=bridge_adapter,
                model_gateway=model_gateway,
                prompt_system=prompt_system,
                delta_bus=delta_bus,
                state_reader=session_routing_reader,
                hil_port=self._hil_service,  # E7.M1.1
                # Phase 1 (Epic 7.3): None when enable_fabric_stores is off,
                # which keeps factory step 21 inert (backward compatible).
                global_projection_store=self._global_projection_store,
                idempotency_store=self._idempotency_store,
            )
            # W8: opt-in module loader hot-reload watcher. Off by default
            # (factory called start(watch=False)); flip on for prod
            # profiles via KernelConfig.module_loader_watch=True. Stop is
            # already wired through Fabric.shutdown() → module_loader.stop().
            if self._config.module_loader_watch:
                ml = getattr(self._shared_fabric, "module_loader", None)
                if ml is not None and not ml.is_running:
                    try:
                        ml.start_watching()
                        logger.info("ModuleLoader watcher started (W8)")
                    except Exception:
                        logger.warning(
                            "ModuleLoader watcher failed to start",
                            exc_info=True,
                        )
        except Exception:
            await self._bridge.disconnect()
            self._bus.close()
            self._router.close()
            raise
        self._log_lifecycle("S3_complete", "CapabilityFabric")

        # ── S5: Orchestrator ─────────────────────────────
        try:
            orch_config = OrchestratorConfig.from_dict(
                {
                    "workflow_db_path": self._config.workflow_db_path,
                    "admin_enabled": False,
                }
            )
            orch_mailbox = MailboxAdapter()
            orch_fabric = FabricGatewayAdapter(fabric=self._shared_fabric)
            orch_planner = MockPlannerAdapter()
            # P1.2: Reuse shared SessionRoutingStateReader (created before S3)
            orch_state = StateReadAdapter(state_reader=session_routing_reader)
            orch_delta = DeltaEmitAdapter(
                event_port=event_port,
                delta_bus=delta_bus,
            )
            orch_bridge_client = self._bridge.get_client()
            orch_bridge = (
                BridgeWriteAdapter(
                    bridge_client=BridgeClientShim(orch_bridge_client),
                )
                if orch_bridge_client is not None
                else MockBridgeAdapter()
            )
            orch_event = EventSubscriptionAdapter(event_port=event_port)
            orch_storage = WorkflowStorageAdapter(
                storage=SQLiteWorkflowAdapter(db_path=self._config.workflow_db_path),
            )
            self._orch_storage = orch_storage

            self._orchestrator = await OrchestratorFactory.create_production(
                config=orch_config,
                mailbox=orch_mailbox,
                fabric=orch_fabric,
                planner=orch_planner,
                state=orch_state,
                delta=orch_delta,
                bridge=orch_bridge,
                event=orch_event,
                storage=orch_storage,
                hil_port=self._hil_service,  # E7.M1.1
            )
        except Exception:
            try:
                self._close_orchestrator_storage()
            except Exception:
                pass
            await self._shared_fabric.shutdown()
            await self._bridge.disconnect()
            self._bus.close()
            self._router.close()
            raise
        self._log_lifecycle("S5_complete", "OrchestratorService")

        # ── S6: Planner ──────────────────────────────────
        try:
            pl_llm = LLMGatewayAdapter(
                llm_request_bus=ModelHubRequestBus(self._model_hub),
            )
            pl_fabric = FabricRetrievalAdapter(
                fabric_retrieval=self._shared_fabric.retrieval,
            )
            # P03 fix: deterministic exact-name capability lookup for
            # ToolCallRouter.get_schema() in EXPAND. Wraps the same Fabric
            # facade the orchestrator and concierge use; <5ms in-process call.
            pl_fabric_registry = FabricRegistryAdapter(
                registry=self._shared_fabric,
            )
            # 3.2.2: Bind the real per-session routing reader. Now that
            # IStateReadPort.read_sections() accepts session_id per call,
            # the Planner singleton can serve all sessions correctly. The
            # pre-bound session_id is kept as an empty fallback for
            # legacy fixtures only; production callers thread session_id
            # via PlanRequest.context.session_id -> ToolCallRouter ->
            # SessionStateReadAdapter.read_sections(..., session_id=...).
            pl_state = PlannerStateAdapter(
                reader=self._session_routing_reader,
                session_id="",
            )
            pl_bridge = PlannerBridgeAdapter(bridge_port=bridge_adapter)
            pl_delta = PlannerDeltaBusAdapter(delta_bus=delta_bus)
            pl_event = PlannerEventBusAdapter(event_port=event_port)
            pl_mailbox = PlannerMailboxAdapter()

            self._planner = await PlannerFactory.create_production(
                llm_port=pl_llm,
                fabric_port=pl_fabric,
                state_port=pl_state,
                bridge_port=pl_bridge,
                delta_port=pl_delta,
                event_port=pl_event,
                mailbox_port=pl_mailbox,
                hil_port=self._hil_service,  # E7.M1.1
                fabric_registry_port=pl_fabric_registry,  # P03 fix
            )
        except Exception:
            await self._orchestrator.shutdown()
            try:
                self._close_orchestrator_storage()
            except Exception:
                pass
            await self._shared_fabric.shutdown()
            await self._bridge.disconnect()
            self._bus.close()
            self._router.close()
            raise
        self._log_lifecycle("S6_complete", "PlannerAgent")

        # ── S6b: Cross-wire Orchestrator↔Planner ─────────
        planner_cb = CircuitBreaker(
            provider_id="planner",
            config=CircuitBreakerConfig(),
        )
        self._orchestrator.bind_planner(
            PlannerAdapter(
                planner_mailbox=self._planner.get_mailbox(),
                cb_planner=planner_cb,
            )
        )
        self._log_lifecycle("S6b_complete", "Orchestrator↔Planner")

        # ── S7: Start Planner Background Task ─────────────
        # Note: PlannerFactory now wires mailbox.set_pipeline_controller()
        # internally (Step 8b). Kernel only needs to spawn the task.
        try:
            self._planner_task = asyncio.create_task(
                self._planner.start(),
                name="planner-agent",
            )

            # Issue 2.4.3 #9: Planner task crash watchdog.
            self._planner_task.add_done_callback(self._on_planner_task_done)

            # ── Final: Post-wire verifications ────────────────
            self._validate_ports()
            self._verify_orchestrator_monitor_binding()
            self._verify_planner_orchestrator_crosswire()
            self._verify_planner_mailbox_binding()
            self._verify_planner_task_running()
            self._log_lifecycle("S7_complete", "planner-agent")

            # ── S8: Family-tools (M15) ───────────────────────
            # Bootstrap the FamilyToolsBundle when enabled. Registers
            # the NativeToolProvider with the shared Fabric and creates
            # the K1FamilyStore SQLite WAL connection. Off by default.
            if getattr(self._config, "enable_family_tools", False):
                self._family_tools = self._bootstrap_family_tools()
                self._log_lifecycle("S8_complete", "FamilyToolsBundle")
            else:
                self._log_lifecycle("S8_skipped", "FamilyToolsBundle")

            # ── Post-S8: Phase 1 domain catalog + verifier ───
            # Load the 50-connector domain catalog into the shared
            # GlobalProjectionStore so resolve_situation can discover it,
            # and wire the VerificationPlanRunner (which needs the native
            # provider registered during S8).  Best-effort: a failure here
            # must never break boot — resolve_situation simply has fewer
            # connectors / no verifier.  Gated behind enable_fabric_stores.
            if self._config.enable_fabric_stores and self._global_projection_store is not None:
                self._load_phase1_catalog_and_verifier()
                # Phase 2: snapshot live registry metadata (domains + resource
                # families) from GPS so Back's prompt can teach the LLM what
                # categories are currently registered.  Queried once at boot —
                # the lists are small (10s of values) and stable across sessions.
                self._registry_hints = self._build_registry_hints(self._global_projection_store)
                _domains = len((self._registry_hints or {}).get("domains", []))
                _rfs = len((self._registry_hints or {}).get("resource_families", []))
                self._log_lifecycle(
                    "PostS8_registry_hints",
                    f"domains={_domains} resource_families={_rfs}",
                )
        except Exception:
            # S7 or verification failed — tear down S6 through S1.
            if self._planner_task is not None:
                self._planner_task.cancel()
                try:
                    await self._planner_task
                except (asyncio.CancelledError, Exception):
                    pass
                self._planner_task = None
            await self._planner.stop()
            await self._orchestrator.shutdown()
            try:
                self._close_orchestrator_storage()
            except Exception:
                pass
            await self._shared_fabric.shutdown()
            await self._bridge.disconnect()
            self._bus.close()
            self._router.close()
            if self._family_tools is not None:
                try:
                    self._family_tools.close()
                except Exception:
                    pass
                self._family_tools = None
            raise

        self._running = True
        self._log_lifecycle("startup_complete", "KernelService")
        logger.info("Tier 1 startup complete — all shared components wired")

    async def _consume_tool_sse(self) -> None:
        """E15.10: Stream ``tool_state.changed.v1`` from K0 and publish to K1 bus.

        Runs as a background ``asyncio.create_task``.  Only started when the
        bridge is a :class:`LiveBridgeAdapter` (i.e. ``K0_ENDPOINT`` is set).
        Each SSE data frame is published to the K1 bus under
        ``TOPIC_TOOL_STATE_CHANGED`` so :class:`UiCoordinator` can forward a
        ``tool_refresh`` event to the browser over the WebSocket.

        The loop exits cleanly on :class:`asyncio.CancelledError` (shutdown).
        Transient errors (network blips) are caught and retried after 5 s.
        """
        import json

        from k1.bus.envelope import Envelope
        from k1.concierge.bus.topics import TOPIC_TOOL_STATE_CHANGED

        space_id = getattr(self._config, "selfmodel_space_id", "") or "family:default"
        logger.info("E15.10: starting tool-SSE consumer (space=%s)", space_id)

        while True:
            try:
                from k1.kernel.adapters.live_bridge_adapter import LiveBridgeAdapter

                if not isinstance(self._bridge, LiveBridgeAdapter):
                    return  # bridge swapped out; stop silently
                async for event in self._bridge.subscribe_sse(
                    topics=["tool_state.changed.v1"],
                    space_id=space_id,
                ):
                    payload: dict = event if isinstance(event, dict) else {"raw": str(event)}
                    env = Envelope(
                        topic=TOPIC_TOOL_STATE_CHANGED,
                        payload=json.dumps(payload).encode(),
                    )
                    try:
                        self._bus.publish(env)
                    except Exception:
                        logger.debug("_consume_tool_sse: bus.publish failed", exc_info=True)
            except asyncio.CancelledError:
                logger.info("E15.10: tool-SSE consumer cancelled — shutting down")
                return
            except Exception:
                logger.warning("E15.10: tool-SSE consumer error; retrying in 5 s", exc_info=True)
                await asyncio.sleep(5)

    def _load_phase1_catalog_and_verifier(self) -> None:
        """Post-S8: admit the Phase 1 domain catalog into the shared store.

        Loads the 50-connector domain catalog (Epic 2) into the shared
        ``GlobalProjectionStore`` via ``ManifestAdmissionService`` (Epic 4.3)
        so ``resolve_situation`` can discover those connectors.

        Best-effort: any failure is logged and swallowed — a catalog-load
        failure must never break kernel boot.

        Note on the verifier: ``VerificationPlanRunner`` (Epic 4.2) requires a
        ``NativeReadbackPort``.  The S8 ``NativeToolProvider`` does not
        implement that port, and no readback adapter exists in Phase 1, so the
        verifier is intentionally left unwired (``fabric.verification_runner``
        stays ``None``) rather than wired to an incompatible provider.
        """
        gps = self._global_projection_store
        if gps is None:
            return
        try:
            from k1.fabric.manifest_admission import ManifestAdmissionService

            admission = ManifestAdmissionService(gps)
            # Phase 2.6: skip ALL domain-catalog connectors.  The explicit
            # family-tools bootstrap (S8) is the ONLY source of capabilities.
            # The Phase 1 domain catalog is legacy scaffolding — it populated
            # generic CRUD placeholders that shadowed explicit, contract-backed
            # capabilities and polluted the resolver with irrelevant connectors
            # (healthcare.appointments, agriculture.shipment, etc.).
            # When a domain needs connectors that don't have explicit
            # ToolDefinitions, add them via the family-tools bootstrap path,
            # not through the domain catalog.
            logger.info(
                "Phase 1 catalog: SKIPPED (family-tools bootstrap is the sole " "capability source)"
            )
            self._log_lifecycle("Phase1_catalog_skipped", "DomainCatalog")
        except Exception:
            logger.warning(
                "Phase 1 domain catalog load failed (resolve_situation will have "
                "fewer connectors)",
                exc_info=True,
            )

    def _bootstrap_family_tools(self) -> Any:
        """Build the FamilyToolsBundle (M15) and register it with Fabric.

        Resolves ``KernelConfig.family_tool_service_paths`` (each entry
        ``"package.module:ClassName"``) into ``BaseToolService`` subclasses
        and hands them to :func:`k1.tools.family.bootstrap_family_tools`.

        Failures here are surfaced to ``_startup_tier1`` and trigger the
        standard reverse-order cleanup chain.
        """
        from importlib import import_module

        from k1.tools.family import bootstrap_family_tools

        service_classes: list[type] = []
        for path in getattr(self._config, "family_tool_service_paths", ()) or ():
            if ":" not in path:
                raise ValueError(
                    f"family_tool_service_paths entry {path!r} must be "
                    "'package.module:ClassName'"
                )
            mod_name, cls_name = path.split(":", 1)
            mod = import_module(mod_name)
            cls = getattr(mod, cls_name)
            service_classes.append(cls)

        # E15.10: wire BusSsePublisher so every family-tool write publishes
        # k1.tool_state.changed.v1 to the K1 bus.  The coordinator
        # subscribes that topic and broadcasts a "tool_refresh" WebSocket
        # message so the browser reloads the affected adapter view.
        from k1.concierge.bus.topics import TOPIC_TOOL_STATE_CHANGED
        from k1.tools.family.sse_adapters import BusSsePublisher

        def _sse_forward(topic: str, payload: dict) -> None:  # type: ignore[type-arg]
            import json

            from k1.bus.envelope import Envelope

            env = Envelope(
                topic=TOPIC_TOOL_STATE_CHANGED,
                payload=json.dumps(payload).encode(),
            )
            try:
                self._bus.publish(env)
            except Exception:
                logger.debug("BusSsePublisher bus.publish failed", exc_info=True)

        sse_pub = BusSsePublisher(forward=_sse_forward)

        bundle = bootstrap_family_tools(
            fabric=self._shared_fabric,
            sse_publisher=sse_pub,
            db_path=getattr(self._config, "family_tools_db_path", "./data/k1_family.db"),
            service_classes=tuple(service_classes),
            default_space_id=getattr(self._config, "selfmodel_space_id", "") or "",
        )
        logger.info(
            "S8: family-tools bundle ready (adapters=%s)",
            bundle.tool_registry.adapter_ids(),
        )
        return bundle

    @staticmethod
    def _build_registry_hints(gps: Any) -> dict[str, Any]:
        """Query GPS for live registry metadata — domains + resource families.

        Called once at kernel boot after S8 (family tools bootstrap).
        The returned dict is injected into Back's system prompt so the
        LLM can frame intents with domain-aware hints that match the
        actually-registered connectors.

        Returns a dict with keys:
        * ``domains`` — list of {domain_id, label, description} dicts.
          Falls back to flat strings when taxonomy tables are absent.
        * ``resource_families`` — list of {domain_id, label,
          families: [{family_id, label, description}]} grouped by domain.
          Falls back to flat strings when taxonomy tables are absent.
        """
        hints: dict[str, Any] = {"domains": [], "resource_families": []}
        try:
            # Phase 2.6: query ONLY domains that have admitted connectors.
            # The taxonomy has 16 domains seeded; showing all of them to the
            # Back LLM is a 9,750-char dump.  Filter to active-only.
            rows = gps._db.execute(
                "SELECT d.domain_id, d.label, d.description "
                "FROM domains d "
                "WHERE d.domain_id IN ("
                "  SELECT DISTINCT c.domain_id FROM connectors c"
                "  WHERE c.admission_verdict = 'admitted' AND c.domain_id != ''"
                ") ORDER BY d.domain_id"
            ).fetchall()
            hints["domains"] = [
                {"domain_id": r[0], "label": r[1], "description": r[2]} for r in rows
            ]
        except Exception:
            # Pre-Epic-22 GPS: fall back to connector_id prefix extraction
            try:
                rows = gps._db.execute(
                    "SELECT DISTINCT "
                    "  CASE WHEN instr(connector_id, '.') > 0 "
                    "    THEN substr(connector_id, 1, instr(connector_id, '.') - 1) "
                    "    ELSE connector_id END AS domain "
                    "FROM connectors ORDER BY domain"
                ).fetchall()
                hints["domains"] = [r[0] for r in rows if r[0]]
            except Exception:
                pass
        try:
            # Phase 2.6: per-domain family lists, filtered to families that
            # have at least one admitted connector registered via
            # connector_resource_families.  Only include a family under a
            # domain when that domain has an active connector using it.
            # The full taxonomy has 130+ domain→family mappings; showing
            # all of them is 9,750 chars of prompt bloat.
            rows = gps._db.execute("""SELECT d.domain_id, d.label as domain_label,
                          rf.family_id, rf.label as family_label, rf.description
                   FROM domains d
                   JOIN domain_resource_families drf ON d.domain_id = drf.domain_id
                   JOIN resource_families rf ON drf.family_id = rf.family_id
                   WHERE (d.domain_id, rf.family_id) IN (
                     SELECT DISTINCT c.domain_id, crf.family_id
                     FROM connector_resource_families crf
                     JOIN connectors c ON crf.connector_id = c.connector_id
                     WHERE c.admission_verdict = 'admitted'
                       AND c.domain_id != ''
                   )
                   ORDER BY d.domain_id, rf.family_id""").fetchall()
            # Group families by domain
            by_domain: dict[str, dict[str, Any]] = {}
            for row in rows:
                did, dlabel, fid, flabel, fdesc = row
                if did not in by_domain:
                    by_domain[did] = {
                        "domain_id": did,
                        "label": dlabel or did.title(),
                        "families": [],
                    }
                by_domain[did]["families"].append(
                    {
                        "family_id": fid,
                        "label": flabel or fid,
                        "description": fdesc or "",
                    }
                )
            hints["resource_families"] = list(by_domain.values())
        except Exception:
            # Pre-Epic-22 GPS: fall back to flat resource_kind list
            try:
                rows = gps._db.execute(
                    "SELECT DISTINCT resource_kind FROM capabilities "
                    "WHERE resource_kind IS NOT NULL AND resource_kind != '' "
                    "ORDER BY resource_kind"
                ).fetchall()
                hints["resource_families"] = [r[0] for r in rows if r[0]]
            except Exception:
                pass
        return hints

    def _build_shared_phase1_pipeline(self) -> Any:
        """Deprecated -- Phase 1 has been removed (returns None).

        Kept as a no-op shim to avoid breaking out-of-tree callers during
        the deprecation window. Will be removed in a future release.
        """
        return None

    async def _cleanup_tier1_partial(self) -> None:
        """Issue 2.4.3 #3: Clean up any Tier 1 components assigned to self.

        Called by ``startup()`` when ``_startup_tier1()`` fails partway.
        Uses the same reverse order as ``shutdown()`` but checks each
        field for None before attempting teardown.  Swallows all errors
        to ensure every component gets a cleanup attempt.
        """
        if self._planner_task is not None:
            try:
                self._planner_task.cancel()
                try:
                    await self._planner_task
                except (asyncio.CancelledError, Exception):
                    pass
            except Exception:
                pass
            self._planner_task = None

        if self._tool_sse_task is not None:
            try:
                self._tool_sse_task.cancel()
                try:
                    await self._tool_sse_task
                except (asyncio.CancelledError, Exception):
                    pass
            except Exception:
                pass
            self._tool_sse_task = None

        if self._planner is not None:
            try:
                await self._planner.stop()
            except Exception:
                pass

        if self._orchestrator is not None:
            try:
                await self._orchestrator.shutdown()
            except Exception:
                pass

        if self._orch_storage is not None:
            try:
                self._close_orchestrator_storage()
            except Exception:
                pass

        # E7.M1.1: HIL service constructed at S2.5.
        if self._hil_service is not None:
            try:
                await self._hil_service.shutdown()
            except Exception:
                pass

        # M5.E3.I2: selfmodel bundle constructed at S2.6.
        if self._self_model_bundle is not None:
            try:
                self._self_model_bundle.shutdown()
            except Exception:
                pass

        if self._grounding_bundle is not None:
            try:
                self._grounding_bundle.shutdown()
            except Exception:
                pass

        if self._spatial_bundle is not None:
            try:
                self._spatial_bundle.shutdown()
            except Exception:
                pass

        if self._temporal_bundle is not None:
            try:
                self._temporal_bundle.shutdown()
            except Exception:
                pass

        if self._shared_fabric is not None:
            try:
                await self._shared_fabric.shutdown()
            except Exception:
                pass

        # M15: Close FamilyToolsBundle (S8) if it was constructed.
        if self._family_tools is not None:
            try:
                self._family_tools.close()
            except Exception:
                pass
            self._family_tools = None

        # Slice 1+3: close kernel.db + registry on partial startup failure
        if self._session_registry is not None:
            self._session_registry = None
        if self._kernel_db is not None:
            try:
                self._kernel_db.close()
            except Exception:
                pass
            self._kernel_db = None

        # P2.3: drain ModelHub plugin connections before nulling the field.
        # Pre-P2.2 there was no shutdown() to call; post-P2.2 omitting this
        # leaks aiohttp ClientSessions on partial-boot recovery. Errors are
        # swallowed because we are already in error-recovery flow.
        if self._model_hub is not None:
            try:
                await asyncio.wait_for(
                    self._model_hub.shutdown(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
            except Exception as exc:
                logger.warning("_cleanup_tier1_partial: ModelHub shutdown failed: %s", exc)

        if self._bridge is not None:
            try:
                await self._bridge.disconnect()
            except Exception:
                pass

        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass

        if self._router is not None:
            try:
                self._router.close()
            except Exception:
                pass

        # Reset all fields so the instance is clean for a retry.
        self._bus = None
        self._async_bus = None
        self._router = None
        self._model_hub = None
        self._shared_fabric = None
        self._prompt_system = None
        self._bridge = None
        self._tool_sse_task = None
        self._orchestrator = None
        self._orch_storage = None
        self._planner = None
        self._hil_service = None  # E7.M1.1
        self._self_model_bundle = None  # M5.E3.I2
        self._temporal_bundle = None  # M1
        self._device_context_port = None
        self._spatial_bundle = None  # M3
        self._grounding_bundle = None  # M1.5

    def _on_planner_task_done(self, task: asyncio.Task[Any]) -> None:
        """Issue 2.4.3 #9: Watchdog callback for planner background task.

        Attached via ``task.add_done_callback()``.  Fires when the planner
        task finishes — normally only during shutdown (via cancel).  If it
        finishes unexpectedly (crash), log an error.
        """
        if task.cancelled():
            return  # Normal shutdown path.
        exc = task.exception()
        if exc is not None:
            logger.error(
                "Planner background task crashed: %s: %s",
                type(exc).__name__,
                exc,
            )
        else:
            logger.warning("Planner background task exited unexpectedly (no exception)")

    def _create_memory_writer_hub_adapter(self) -> ModelHubAdapter:
        """Issue 2.1.5: Build MW's ModelHubAdapter (anti-corruption layer).

        K1 ModelHub exposes ``execute(HubRequest) → HubResponse``.
        MemoryWriter expects ``chat(messages, budget, hint) → ChatResponse``.
        ``ModelHubAdapter`` bridges the two: translates ``chat()`` calls into
        ``execute(HubRequest(CHAT, ChatPayload))`` calls.

        Adapter chain:
            MemoryWriter → MW.IModelHubPort.chat()
            → ModelHubAdapter → K1.ModelHub.execute(HubRequest)
            → LLM provider

        WRONG wiring: passing ``self._model_hub`` directly to
        ``MemoryWriterFactory.create(model_hub_port=...)`` — K1 ModelHub
        lacks ``chat()`` and would fail at MW's isinstance() validation.

        Returns:
            A ``ModelHubAdapter`` wrapping ``self._model_hub``.

        Raises:
            RuntimeError: If ``_model_hub`` is not yet initialised (Tier 1
                startup must run first — depends on Issue 2.2.2).
        """
        if self._model_hub is None:
            raise RuntimeError(
                "Cannot create MW ModelHubAdapter: _model_hub is None. "
                "Tier 1 startup (Issue 2.2.2) must run first."
            )
        return ModelHubAdapter(hub=self._model_hub)

    # ------------------------------------------------------------------
    # Slice 2: Chat message persistence (turn.completed → kernel.db)
    # ------------------------------------------------------------------

    def _wire_chat_persistence(self, session_bus: Any, session_id: str) -> None:
        """Subscribe to turn.completed.v1 and persist user + assistant messages.

        Called once per session from ``_create_session_tier2()`` after
        the session is fully assembled and registered in ``_sessions``.

        The handler is fire-and-forget — it never raises to the bus.
        kernel.db guard: silently no-ops if the db is not open.
        """
        if self._kernel_db is None or not self._kernel_db.is_open:
            return

        from k1.concierge.bus.topics import TOPIC_TURN_COMPLETED

        def _on_turn_completed(envelope: Any) -> None:
            # NOTE: the local bus calls handlers synchronously:
            #   handler(envelope)  — NOT  await handler(envelope)
            # So this MUST be a plain `def`, never `async def`.
            # All DB writes + bus publishes inside are synchronous.
            try:
                # Envelope payload is compact JSON bytes.
                import json as _json

                raw = envelope.payload
                if isinstance(raw, (bytes, bytearray, memoryview)):
                    payload = _json.loads(raw)
                elif isinstance(raw, str):
                    payload = _json.loads(raw)
                elif isinstance(raw, dict):
                    payload = raw
                else:
                    return

                user_msg: str = str(payload.get("user_message", "") or "")
                asst_msg: str = str(payload.get("assistant_response", "") or "")
                turn_num: int = int(payload.get("turn_number", 0))
                ts: int = int(payload.get("timestamp_ms", 0))

                if user_msg:
                    self._kernel_db.insert_message(session_id, turn_num, "user", user_msg, ts)
                if asst_msg:
                    self._kernel_db.insert_message(session_id, turn_num, "assistant", asst_msg, ts)

                # Slice 3: increment turn_count + touch last_active
                if self._session_registry is not None:
                    self._session_registry.increment_turn(session_id)

                # ── Slice 7: auto-title on turn 1 ──
                if turn_num == 1 and user_msg and self._session_registry is not None:
                    title = _auto_title(user_msg)
                    updated = self._session_registry.update_title(session_id, title)
                    if updated:
                        logger.info("Auto-title: session=%s title=%r", session_id, title)
                        try:
                            from k1.bus.envelope import Envelope
                            from k1.concierge.bus.topics import (
                                TOPIC_SESSION_TITLE_UPDATED,
                            )

                            session_bus.publish(
                                Envelope(
                                    topic=TOPIC_SESSION_TITLE_UPDATED,
                                    payload=_json.dumps(
                                        {
                                            "session_id": session_id,
                                            "title": title,
                                        }
                                    ).encode(),
                                )
                            )
                        except Exception:
                            logger.debug("Auto-title: bus publish failed", exc_info=True)
            except Exception:
                logger.warning(
                    "chat_persistence: turn.completed handler failed (session=%s)",
                    session_id,
                    exc_info=True,
                )

        session_bus.subscribe(TOPIC_TURN_COMPLETED, _on_turn_completed)

    async def _create_session_tier2(
        self,
        session_id: str,
        device_id: str | None = None,
    ) -> SessionInstance:
        """Execute P1→P7 per-session component creation.

        Issue 2.4.3 #2: Each phase is wrapped so that failure at step N
        triggers reverse-order cleanup of steps 1..N-1.  The session is
        NOT added to ``_sessions`` until fully assembled.

        Steps:
            P1: Per-session Bus (BridgeAwareLocalBus-wrapped) + MailboxRouter + front/back Mailboxes
            P2–P7: Remaining session components (Epic 2.3 issues)
        """
        # ── P1: Per-session Bus + Mailboxes ───────────────────
        # R10 mitigation (I2.7.5 / I2.7.11): wrap the raw bus with
        # BridgeAwareLocalBus so any direct publish on a cross-kernel
        # bridge topic raises UnknownContractError instead of silently
        # bypassing the bridge registry.
        _raw_session_bus = BusFactory.create_local_ordered(capture=False)
        session_bus = BridgeAwareLocalBus(_raw_session_bus)
        session_router = BusFactory.create_mailbox_router()
        # Use canonical ACTOR_FRONT / ACTOR_BACK constants: the router is
        # already per-session (so names don't need a session_id suffix),
        # and ConciergeController._deliver_to_{front,back} hard-codes
        # these names via k1.concierge.bus.setup.
        from k1.concierge.bus.setup import ACTOR_BACK, ACTOR_FRONT

        front_mailbox = session_router.register(ACTOR_FRONT)
        back_mailbox = session_router.register(ACTOR_BACK)
        self._log_lifecycle("P1_complete", f"session:{session_id}")

        # ── P1.5: Per-session HIL service ─────────────────────
        # HIL events (k1.hil.request.v1 / k1.hil.response.v1) are scoped to
        # a conversation. The Concierge FSM, per-session Fabric, SelfModel
        # handle and UI coordinator all subscribe on ``session_bus``. The
        # kernel-level HIL service (S2.5) is bound to the kernel bus and
        # serves kernel-level callers (Orchestrator, Planner, shared
        # Fabric); it MUST NOT be used by session-scoped subsystems or
        # their HIL requests will be published on the kernel bus where
        # nothing is listening (root cause of the silent HIL-never-reaches-
        # UI bug).
        session_hil_service: Any | None = None
        if self._config.enable_hil_service:
            try:
                session_hil_event_port = KernelHILEventAdapter(
                    session_bus,
                    loop=asyncio.get_running_loop(),
                )
                session_hil_service = HumanInTheLoopService(
                    event_port=session_hil_event_port,
                    ledger=HILLedgerAdapter(None),
                    suspension_mgr=None,
                    safety_policy=SafetyBandPolicy(),
                    config=HILConfig(
                        max_clarification_rounds=self._config.hil_max_clarification_rounds,
                        clarification_timeout_ms=self._config.hil_clarification_timeout_ms,
                        approval_timeout_ms=self._config.hil_approval_timeout_ms,
                        needs_human_timeout_ms=self._config.hil_needs_human_timeout_ms,
                        override_timeout_ms=self._config.hil_override_timeout_ms,
                        capability_gate_timeout_ms=self._config.hil_capability_gate_timeout_ms,
                        enable_audit_topic=self._config.hil_enable_audit_topic,
                        enable_llm_synthesis=self._config.hil_enable_llm_synthesis,
                    ),
                    llm_port=None,
                )
                logger.info(
                    "HIL (session=%s): HumanInTheLoopService bound to session_bus",
                    session_id,
                )
            except Exception:
                session_bus.close()
                session_router.close()
                raise

        # ── P2: SessionState (per-session) ─────────────────────
        ssm = None
        try:
            ss_storage = SQLiteStorageAdapter(db_path=self._config.sessionstate_db_path)
            ss_events = LocalEventAdapter(capture_mode=False)
            ss_writer = DirectWriterAdapter(writer_id="direct")
            ss_lifecycle = StandaloneLifecycle()
            ssm = SessionStateFactory.create_with_ports(
                session_id=session_id,
                storage=ss_storage,
                events=ss_events,
                writer=ss_writer,
                lifecycle=ss_lifecycle,
                k0_sync=None,
                db_path=Path(self._config.sessionstate_db_path),
            )
            ss_writer.bind_manager(ssm, ssm.mutation_guard)
            ss_lifecycle.bind_manager(ssm)
            ssm.start()
            async_ssm = AsyncSSMBridge(ssm)
            self._log_lifecycle("P2_complete", f"session:{session_id}")
        except Exception:
            session_bus.close()
            session_router.close()
            raise

        # ── P3: Per-session Fabric ────────────────────────────
        try:
            session_state_reader = SessionStateReaderAdapter(ssm, session_id)
            session_event_port = EventPortProdAdapter(session_bus)
            session_delta_bus = DeltaBusProdAdapter(session_bus)
            session_model_gw = ModelGatewayBridgeAdapter(hub=self._model_hub)
            session_prompt_sys = self._prompt_system or PromptSystemProdAdapter(
                prompts_dir="k1/contracts/prompts"
            )
            self._verify_activity_prompt_system(
                session_prompt_sys,
                scope=f"session:{session_id}",
            )
            session_bridge_client = self._bridge.get_client()
            session_bridge_adapter = BridgeConnectionAdapter(client=session_bridge_client)

            # Pass shared_fabric.registry so the per-session Fabric reuses the
            # same CapabilityRegistry that already has all 41 family-tool
            # contracts registered.  ModuleLoader will attempt to re-add the
            # 24 k1\contracts files but DuplicateCapabilityError is silently
            # swallowed, so this is safe.
            _shared_registry = (
                getattr(self._shared_fabric, "registry", None)
                if self._shared_fabric is not None
                else None
            )
            # Phase 1 (Epic 7.3): per-session LocalProjectionStore over the
            # shared GlobalProjectionStore + IdempotencyStore.  Created only
            # when enable_fabric_stores is on; otherwise all three are None
            # and create_with_ports behaves exactly as before (inert).
            session_local_store = None
            if self._config.enable_fabric_stores and self._global_projection_store is not None:
                from k1.fabric.stores.local_projection_store import (
                    LocalProjectionStore,
                )

                session_local_store = LocalProjectionStore(":memory:")
                session_local_store.open()

            session_fabric = FabricFactory.create_with_ports(
                state_reader=session_state_reader,
                event_port=session_event_port,
                bridge=session_bridge_adapter,
                model_gateway=session_model_gw,
                prompt_system=session_prompt_sys,
                delta_bus=session_delta_bus,
                production_mode=True,
                hil_port=session_hil_service,  # P1.5: session-bus-bound HIL
                capability_registry=_shared_registry,
                global_projection_store=self._global_projection_store,
                local_projection_store=session_local_store,
                idempotency_store=self._idempotency_store,
            )

            # P3.1: Re-register the singleton NativeToolProvider with this
            # per-session fabric.  FabricFactory only registers the seven
            # built-in handlers (MCP/WASM/BRIDGE/AGENT/WORKFLOW/CONCIERGE/
            # LOCAL_STUB) on the new provider_factory.  The ``LOCAL``
            # handler (k1 native family-tools, provider_type=NATIVE_PROVIDER_TYPE)
            # is created during S8 family-tools bootstrap and only registered
            # on the SHARED fabric's provider_factory.  Without this hook
            # every capability resolving to ``provider=k1_native_tools``
            # fails with ``UnsupportedProviderTypeError: LOCAL`` at execute
            # time, so the actual tool effects never happen (root cause of
            # the "task says added but never appears in UI" bug).
            if self._family_tools is not None:
                native_provider = getattr(self._family_tools, "native_provider", None)
                if native_provider is not None:
                    from k1.tools.family.bootstrap import register_provider_with_fabric

                    logger.info(
                        "P3.1: registering NativeToolProvider on session fabric (session=%s)",
                        session_id,
                    )
                    register_provider_with_fabric(session_fabric, native_provider)
            self._log_lifecycle("P3_complete", f"session:{session_id}")
        except Exception:
            ssm.stop()
            session_bus.close()
            session_router.close()
            raise

        actor_id, device_meta = self._derive_session_actor(ssm, session_id, device_id)

        # ── P3.5: k1.selfmodel handle (M5.E3.I3) ──────────────
        # Built after P3 (per-session Fabric) and before P4 (Concierge)
        # so the Concierge factory can attach the handle's gate +
        # capsule renderer at construction time. When
        # ``enable_self_model`` is False (or the bundle failed to
        # build at S2.6) the handle stays None and the session runs
        # the pre-M5 baseline.
        session_self_model: SelfModelHandle | None = None
        if self._self_model_bundle is not None:
            try:
                risk_catalog = None
                risk_registry = getattr(session_fabric, "registry", None) or _shared_registry
                if risk_registry is not None:
                    from k1.selfmodel.adapters.fabric_risk_catalog import (
                        FabricRiskCatalog,
                    )

                    risk_catalog = FabricRiskCatalog(risk_registry, bus=session_bus)
                session_self_model = build_self_model_handle(
                    self._self_model_bundle,
                    session_id=session_id,
                    actor_id=actor_id,
                    device_id=device_meta,
                    situation_kind=self._config.selfmodel_situation_kind,
                    hil_service=session_hil_service,
                    risk_catalog=risk_catalog,
                )
                logger.debug(
                    "selfmodel P3.5 wired session=%s actor=%s device=%s",
                    session_id,
                    actor_id,
                    device_meta,
                )
            except Exception:
                # P3.5 failure must not abort session creation —
                # selfmodel is an opt-in overlay. Log + continue.
                logger.warning(
                    "selfmodel P3.5 build failed for session=%s; continuing without handle",
                    session_id,
                    exc_info=True,
                )
                session_self_model = None

        # ── P3.6: Temporal handle (M1) ───────────────────────
        session_temporal: TemporalHandle | None = None
        if self._temporal_bundle is not None:
            session_temporal = build_temporal_handle(
                self._temporal_bundle,
                session_id=session_id,
                principal_id=actor_id,
                device_id=device_meta or None,
                installation_id=device_meta or None,
                state_manager=ssm,
            )
            session_temporal.install_into_session()
            try:
                await session_temporal.refresh_turn(
                    session_id,
                    device_id=device_meta or None,
                    installation_id=device_meta or None,
                )
            except Exception:
                logger.warning(
                    "temporal P3.6 refresh failed for session=%s; continuing with bound handle",
                    session_id,
                    exc_info=True,
                )

        # ── P3.7: Spatial handle (M3) ───────────────────────
        session_spatial: SpatialHandle | None = None
        if self._spatial_bundle is not None:
            try:
                session_spatial = build_spatial_handle(
                    self._spatial_bundle,
                    session_id=session_id,
                    principal_id=actor_id,
                    actor_id=actor_id,
                    device_id=device_meta or None,
                    installation_id=device_meta or None,
                    state_manager=ssm,
                    selfmodel_handle=session_self_model,
                )
                session_spatial.install_into_session()
                try:
                    await session_spatial.refresh_turn(
                        session_id,
                        consumer="front",
                        device_id=device_meta or None,
                        installation_id=device_meta or None,
                    )
                except Exception:
                    logger.warning(
                        "spatial P3.7 refresh failed for session=%s; continuing with bound handle",
                        session_id,
                        exc_info=True,
                    )
            except Exception:
                logger.warning(
                    "spatial P3.7 build failed for session=%s; continuing without handle",
                    session_id,
                    exc_info=True,
                )
                session_spatial = None

        # ── P3.8: Grounding handle (M1.5 transitional) ──────
        session_grounding: GroundingHandle | None = None
        if self._grounding_bundle is not None:
            try:
                session_grounding = build_grounding_handle(
                    self._grounding_bundle,
                    session_id=session_id,
                    principal_id=actor_id,
                    actor_id=actor_id,
                    device_id=device_meta or None,
                    installation_id=device_meta or None,
                    state_manager=ssm,
                    temporal_handle=session_temporal,
                    spatial_handle=session_spatial,
                    selfmodel_handle=session_self_model,
                )
                session_grounding.install_into_session()
                try:
                    await session_grounding.refresh_turn(
                        session_id,
                        consumer="front",
                        device_id=device_meta or None,
                        installation_id=device_meta or None,
                    )
                except Exception:
                    logger.warning(
                        "grounding P3.8 refresh failed for session=%s; continuing with bound handle",
                        session_id,
                        exc_info=True,
                    )
                try:
                    fabric_context_builder = getattr(session_fabric, "context_builder", None)
                    if fabric_context_builder is None:
                        fabric_context_builder = getattr(
                            getattr(session_fabric, "facade", None),
                            "_context_builder",
                            None,
                        )
                    setter = getattr(fabric_context_builder, "set_grounding_port", None)
                    if callable(setter):
                        setter(session_grounding)
                except Exception:
                    logger.warning(
                        "grounding P3.8 Fabric context binding failed for session=%s",
                        session_id,
                        exc_info=True,
                    )
            except Exception:
                logger.warning(
                    "grounding P3.8 build failed for session=%s; continuing without handle",
                    session_id,
                    exc_info=True,
                )
                session_grounding = None

        # ── P4: Concierge (per-session) ──────────────────────
        session_concierge = None
        try:
            concierge_config = ConciergeConfig.from_kernel_config(self._config)
            session_input = BusInputAdapter(session_bus)
            session_output = BusOutputAdapter(session_bus)
            session_state_port = SSMStateAdapter(ssm)
            # M17.E1.I3 -- forward workflow.* dispatch from concierge to the
            # production WorkflowEngine. ``_workflow_engine`` is a private
            # slot on OrchestratorService; we read it via getattr so older
            # orchestrator stubs (which lack the engine) still boot.
            workflow_engine = getattr(self._orchestrator, "_workflow_engine", None)
            session_dispatch = FabricDispatchAdapter(
                fabric_port=session_fabric,
                orchestrator=self._orchestrator,
                bus=session_bus,
                workflow_engine=workflow_engine,
            )
            port_bundle = PortBundle(
                delta=session_bus,
                input_=session_input,
                output=session_output,
                state=session_state_port,
                llm=self._model_hub,
                dispatch=session_dispatch,
                temporal=session_temporal,
                spatial=session_spatial,
                grounding=session_grounding,
                registry_hints=self._registry_hints,  # Phase 2: live GPS registry snapshot
                # P5.2 / MS-3c: Wire recall through the typed paired-contract
                # surface (``recall.request.v1`` / ``recall.response.v1``).
                # ``build_recall_fn`` resolves the typed client out of the
                # bridge composite client (or returns an offline-graceful
                # ``[]`` when no recall surface is bound).
                memory=RecallMemoryAdapter(
                    build_recall_fn(
                        self._bridge.get_client(),
                        space_id=getattr(self._config, "selfmodel_space_id", "") or "default",
                    )
                ),
                # P4B.6: pass IWriterPort explicitly (was reach-through in factory step 7)
                writer=ss_writer,
            )
            session_concierge = ConciergeFactory.create_with_ports(
                bus=session_bus,
                router=session_router,
                front_mailbox=front_mailbox,
                back_mailbox=back_mailbox,
                ports=port_bundle,
                config=concierge_config,
                hil_port=session_hil_service,  # P1.5: session-bus-bound HIL
            )
            self._log_lifecycle("P4_complete", f"session:{session_id}")
        except Exception:
            # P3 Fabric has no teardown; clean up P2 + P1.
            ssm.stop()
            session_bus.close()
            session_router.close()
            raise

        # ── P5: MemoryWriter (per-session) ─────────────────────
        session_memory_writer = None
        try:
            mw_config = MWConfig()
            mw_session_read = SessionReadAdapter(
                manager=ssm,
                cold_archive=ssm.get_local_cold_archive(),
            )
            mw_model_hub = self._create_memory_writer_hub_adapter()
            mw_bridge = BridgeCommandAdapter(command_port=self._bridge.get_client())
            mw_bus_adapter = FabricBusAdapter(session_bus)
            mw_events = MWEventSubscriptionAdapter(bus_adapter=mw_bus_adapter)
            mw_cb = MWCircuitBreaker(
                failure_threshold=mw_config.circuit_breaker_failure_threshold,
                recovery_probe_seconds=mw_config.circuit_breaker_recovery_probe_seconds,
            )
            mw_health = HealthAdapter(
                circuit_breaker=mw_cb,
                get_pending_count=lambda: 0,
                # P5.3: forward-reference; service is assigned right below.
                # Reflects actual MW lifecycle state instead of constant False.
                get_started=lambda: (
                    session_memory_writer.is_started if session_memory_writer is not None else False
                ),
                get_last_extraction_ms=lambda: (  # MW-05-C
                    session_memory_writer.last_extraction_ms
                    if session_memory_writer is not None
                    else 0.0
                ),
            )
            session_memory_writer = MemoryWriterFactory.create(
                session_read_port=mw_session_read,
                model_hub_port=mw_model_hub,
                bridge_command_port=mw_bridge,
                event_subscription_port=mw_events,
                health_port=mw_health,
                config=mw_config,
            )
            self._log_lifecycle("P5_complete", f"session:{session_id}")
        except Exception:
            # P4 Concierge not started yet — no stop needed.
            # P3 Fabric no teardown.  Clean up P2 + P1.
            ssm.stop()
            session_bus.close()
            session_router.close()
            raise

        # ── P3.5 (pre-start install): wire gate + recall wrapper ──
        # M15.E1.I5 — install BEFORE ``session_concierge.start()`` so
        # the policy gate is in place before the mailbox consumer can
        # accept the first turn (closes the install/start race window).
        # Dispatchers + per-side contexts are constructed in
        # ``ConciergeRuntime.__init__`` and are therefore already
        # available on the instance prior to ``start``.
        if session_self_model is not None:
            try:
                session_self_model.install_into_session(
                    front_dispatcher=getattr(session_concierge, "front_dispatcher", None),
                    back_dispatcher=getattr(session_concierge, "back_dispatcher", None),
                    front_ctx=getattr(session_concierge, "front_ctx", None),
                    back_ctx=getattr(session_concierge, "back_ctx", None),
                )
            except Exception:
                logger.warning(
                    "selfmodel P3.5 install failed for session=%s",
                    session_id,
                    exc_info=True,
                )

            # M5.E4: also attach the handle to ConciergeRuntime so
            # ``front_handler`` can pull ``render_capsule()`` per turn
            # and inject it into ``DynamicPromptBuilder.build(stage 9.5)``.
            setter = getattr(session_concierge, "set_self_model", None)
            if callable(setter):
                try:
                    setter(session_self_model)
                except Exception:
                    logger.warning(
                        "selfmodel: set_self_model failed for session=%s",
                        session_id,
                        exc_info=True,
                    )

        # ── P6: Assemble SessionInstance + Start Lifecycle ────
        try:
            await session_concierge.start()
        except Exception:
            # Concierge start failed — clean up P2 + P1.
            ssm.stop()
            session_bus.close()
            session_router.close()
            raise

        try:
            await session_memory_writer.start()
        except Exception:
            # MW start failed — stop Concierge, then P2 + P1.
            await session_concierge.stop()
            ssm.stop()
            session_bus.close()
            session_router.close()
            raise

        section_update_worker: SectionUpdateBackgroundWorker | None = None
        section_update_mode = (
            str(getattr(self._config, "section_update_worker_mode", "off") or "off").strip().lower()
        )
        section_update_enabled = bool(
            getattr(self._config, "enable_section_update_worker", False)
        ) and section_update_mode not in {"", "off", "disabled", "none"}
        logger.info(
            "P5.5: section_update worker gate session=%s enable_flag=%s mode=%s -> %s",
            session_id,
            bool(getattr(self._config, "enable_section_update_worker", False)),
            section_update_mode,
            "STARTING" if section_update_enabled else "SKIPPED",
        )
        if section_update_enabled:
            try:
                classifier = self._section_update_classifier
                if classifier is None:
                    # No external classifier wired. Production default is
                    # the LLM-backed classifier (vertex/gemini by config).
                    # Only fall back to the deterministic stub if the
                    # ModelHub is unavailable, in which case the worker
                    # will publish noop plans rather than crashing.
                    if self._model_hub is not None:
                        # Env var takes priority over config default (so
                        # LLM_PROVIDER=deepseek overrides config's "vertex").
                        _env_provider = os.environ.get("LLM_PROVIDER", "")
                        _cfg_provider = str(
                            getattr(self._config, "section_update_provider", "") or ""
                        )
                        provider_id = _env_provider or _cfg_provider or "vertex"
                        _env_model_ds = os.environ.get("DEEPSEEK_MODEL", "")
                        _env_model_vx = os.environ.get("VERTEX_MODEL", "")
                        _env_model_goog = os.environ.get("GOOGLE_MODEL", "")
                        _cfg_model = str(getattr(self._config, "section_update_model", "") or "")
                        model_id = (
                            _env_model_ds
                            or _env_model_vx
                            or _env_model_goog
                            or _cfg_model
                            or "gemini-2.5-flash-lite"
                        )
                        timeout_ms = int(
                            getattr(self._config, "section_update_worker_timeout_ms", 75_000)
                            or 75_000
                        )
                        classifier = LLMSectionUpdateClassifier(
                            model_hub=self._model_hub,
                            provider_id=provider_id,
                            model_id=model_id,
                            timeout_ms=timeout_ms,
                        )
                        logger.info(
                            "P5.5: section_update classifier resolved: "
                            "LLM_PROVIDER=%s DEEPSEEK_MODEL=%s VERTEX_MODEL=%s → "
                            "provider=%s model=%s",
                            os.environ.get("LLM_PROVIDER", "<unset>"),
                            os.environ.get("DEEPSEEK_MODEL", "<unset>"),
                            os.environ.get("VERTEX_MODEL", "<unset>"),
                            provider_id,
                            model_id,
                        )
                        logger.info(
                            "P5.5: no external section_update classifier wired; "
                            "auto-wired LLMSectionUpdateClassifier "
                            "(session=%s, mode=%s, provider=%s, model=%s, timeout_ms=%d)",
                            session_id,
                            section_update_mode,
                            provider_id,
                            model_id,
                            timeout_ms,
                        )
                    else:
                        classifier = DeterministicSectionUpdateClassifier()
                        logger.warning(
                            "P5.5: no external section_update classifier wired and "
                            "ModelHub is unavailable; falling back to "
                            "DeterministicSectionUpdateClassifier (session=%s, mode=%s) -- "
                            "section updates will be no-ops",
                            session_id,
                            section_update_mode,
                        )
                section_update_worker = SectionUpdateBackgroundWorker(
                    session_id=session_id,
                    bus=session_bus,
                    state_manager=ssm,
                    writer_port=ss_writer,
                    classifier=classifier,
                    config=SectionUpdateWorkerConfig(
                        mode=section_update_mode,
                        timeout_ms=int(
                            getattr(self._config, "section_update_worker_timeout_ms", 75_000)
                            or 75_000
                        ),
                        queue_max=int(
                            getattr(self._config, "section_update_worker_queue_max", 128) or 128
                        ),
                        classifier_version=str(
                            getattr(
                                self._config,
                                "section_update_classifier_version",
                                "section-update-v0",
                            )
                            or "section-update-v0"
                        ),
                        provider_id=provider_id,
                        model_id=model_id,
                    ),
                )
                section_update_worker.start()
                logger.info(
                    "P5.5: SectionUpdateBackgroundWorker started session=%s mode=%s classifier=%s timeout_ms=%s queue_max=%s",
                    session_id,
                    section_update_mode,
                    type(classifier).__name__ if classifier is not None else "None",
                    getattr(self._config, "section_update_worker_timeout_ms", 75_000),
                    getattr(self._config, "section_update_worker_queue_max", 128),
                )
                self._log_lifecycle("P5_5_complete", f"session:{session_id}")
            except Exception:
                logger.exception(
                    "P5.5: SectionUpdateBackgroundWorker start FAILED session=%s mode=%s",
                    session_id,
                    section_update_mode,
                )
                if section_update_worker is not None:
                    await asyncio.to_thread(section_update_worker.stop)
                await session_memory_writer.stop()
                await session_concierge.stop()
                ssm.stop()
                session_bus.close()
                session_router.close()
                raise

        session = SessionInstance(
            session_id=session_id,
            member_id=None,
            bus=session_bus,
            router=session_router,
            front_mailbox=front_mailbox,
            back_mailbox=back_mailbox,
            session_state=ssm,
            fabric=session_fabric,
            concierge=session_concierge,
            memory_writer=session_memory_writer,
            front_dispatcher=session_concierge.front_dispatcher,
            back_dispatcher=session_concierge.back_dispatcher,
            experience_layer=session_concierge.experience_layer,
            delta_aggregator=session_concierge.delta_aggregator,
            delta_applicator=session_concierge.delta_applicator,
            hil_port=session_concierge.hil_port,
            consumer_task=session_concierge.consumer_task,
            dead_letter_consumer=session_concierge.dead_letter_consumer,
            created_at=datetime.now(timezone.utc),
            section_update_worker=section_update_worker,
            front_ctx=session_concierge.front_ctx,
            back_ctx=session_concierge.back_ctx,
            ledger=session_concierge.ledger,
            ledger_store=session_concierge.ledger_store,
            concierge_task=session_concierge.consumer_task,
            self_model=session_self_model,
            temporal=session_temporal,
            spatial=session_spatial,
            grounding=session_grounding,
        )
        self._sessions[session_id] = session

        # Slice 2: wire chat message persistence (turn.completed → kernel.db)
        self._wire_chat_persistence(session_bus, session_id)

        self._log_lifecycle("P6_complete", f"session:{session_id}")
        return session
