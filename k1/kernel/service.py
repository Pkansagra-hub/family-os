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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Issue 2.4.3: Default timeout for component teardown (seconds).
_TEARDOWN_TIMEOUT: float = 10.0
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
from k1.fabric.adapters.bridge_connection import BridgeConnectionAdapter
from k1.fabric.adapters.delta_bus_prod import DeltaBusProdAdapter
from k1.fabric.adapters.event_port_prod import EventPortProdAdapter
from k1.fabric.adapters.model_gateway_bridge import ModelGatewayBridgeAdapter
from k1.fabric.adapters.prompt_system_prod import PromptSystemProdAdapter

# Issue 2.3.ic.adapters.sessionstate_reader import SessionStateReaderAdapter
from k1.fabric.adapters.sessionstate_reader import SessionStateReaderAdapter
from k1.fabric.circuit_breaker.breaker import CircuitBreaker, CircuitBreakerConfig
from k1.fabric.factory import FabricFactory

# E7.M1.1: Unified HIL service + adapters
from k1.hil.adapters import KernelHILEventAdapter
from k1.hil.config import HILConfig
from k1.hil.ledger import HILLedgerAdapter
from k1.hil.safety import SafetyBandPolicy
from k1.hil.service import HumanInTheLoopService
from k1.kernel.adapters.bridge_adapter import OfflineBridgeAdapter, SinkBridgeAdapter

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

logger = logging.getLogger(__name__)


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
        self._bridge: Any | None = None  # IBridgeClient | None
        self._orchestrator: Any | None = None  # OrchestratorService
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

        # P4B.8: Shared Phase1 (UltraBERT) classification pipeline.
        # Built once during _startup_tier1, reused across every session.
        # familyos_ultrabert.Client is loaded lazily on first analyze() call
        # so process boot does not pay the ~20s model load cost.
        self._phase1_pipeline: Any | None = None

        # M15: Family-tools bundle (k1.tools.family). Built at S8 of
        # _startup_tier1 when KernelConfig.enable_family_tools is True.
        # Owns the K1FamilyStore SQLite connection, ToolRegistry,
        # IdempotencyStore, and NativeToolProvider registered into the
        # shared Fabric. Closed during shutdown / cleanup.
        self._family_tools: Any | None = None

        # P1.1: Shared routing reader (resolves session_id → SSM)
        self._session_routing_reader: SessionRoutingStateReader | None = None

        # Tier 2 per-session components
        self._sessions: dict[str, SessionInstance] = {}

        # lifecycle flag
        self._running: bool = False

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

        # ── Reverse S7: Stop Planner + cancel task ────────────
        if self._planner is not None:
            try:
                await asyncio.wait_for(
                    self._planner.stop(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
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
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: Orchestrator shutdown failed: %s", exc)

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
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: selfmodel bundle shutdown failed: %s", exc)
            self._self_model_bundle = None

        # ── Reverse S4: Disconnect Bridge ─────────────────────
        if self._bridge is not None:
            try:
                await asyncio.wait_for(
                    self._bridge.disconnect(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
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
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: Fabric shutdown failed: %s", exc)

        # ── Reverse S8: Close FamilyToolsBundle (M15) ─────────
        if self._family_tools is not None:
            try:
                self._family_tools.close()
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: FamilyToolsBundle close failed: %s", exc)
            self._family_tools = None

        # ── Reverse S2: ModelHub plugin drain (P2.3) ──────────
        if self._model_hub is not None:
            try:
                await asyncio.wait_for(
                    self._model_hub.shutdown(),
                    timeout=_TEARDOWN_TIMEOUT,
                )
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
            except Exception as exc:
                errors.append(exc)
                logger.warning("shutdown: Router close failed: %s", exc)

        # ── Always mark as not running ────────────────────────
        self._running = False

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
        session_id: str,
        device_id: str | None = None,
    ) -> SessionInstance:
        """Create a new session with all Tier 2 components (P1→P6).

        Issue 2.4.3 #5: If ``_validate_session()`` fails after the session
        is registered, the zombie session is destroyed before re-raising.

        Args:
            session_id: Unique identifier for the session.
            device_id: Optional device identifier.

        Returns:
            The newly created ``SessionInstance``.

        Raises:
            RuntimeError: If the kernel is not running.
            ValueError: If a session with the given ID already exists.
            TypeError: If the session fails port validation (after cleanup).
        """
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
            1. Remove from registry (``_sessions.pop``)
            2. Reverse P5: Stop MemoryWriter
            3. Reverse P4: Stop Concierge (FSM + consumer tasks)
            4. Reverse P3: (per-session Fabric has no explicit teardown)
            5. Reverse P2: Checkpoint + stop SessionState
            6. Reverse P1: Close per-session Bus + Router

        Each step is individually guarded — teardown continues even if
        one step fails.  All errors are collected and logged.

        Args:
            session_id: The session to destroy.

        Raises:
            KeyError: If no session with that ID exists.
        """
        session = self._sessions.pop(session_id)  # KeyError if missing
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

        # Reverse P5: Stop MemoryWriter
        try:
            await asyncio.wait_for(
                session.memory_writer.stop(),
                timeout=_TEARDOWN_TIMEOUT,
            )
        except Exception as exc:
            errors.append(exc)
            logger.warning("destroy_session(%s): MemoryWriter stop failed: %s", session_id, exc)

        # Reverse P4: Stop Concierge
        try:
            await asyncio.wait_for(
                session.concierge.stop(),
                timeout=_TEARDOWN_TIMEOUT,
            )
        except Exception as exc:
            errors.append(exc)
            logger.warning("destroy_session(%s): Concierge stop failed: %s", session_id, exc)

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

        if errors:
            logger.error(
                "destroy_session(%s): %d error(s) during teardown",
                session_id,
                len(errors),
            )

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
                    ProviderConfig.default(),
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

        # ── P1.1/P1.4: SessionRoutingStateReader (shared by S3, S5, S6) ──
        session_routing_reader = SessionRoutingStateReader(
            session_lookup=lambda sid: (
                self._sessions[sid].session_state if sid in self._sessions else None
            ),
        )
        self._session_routing_reader = session_routing_reader

        # ── S3: Shared Fabric ─────────────────────────────
        try:
            event_port = EventPortProdAdapter(bus)
            delta_bus = DeltaBusProdAdapter(bus)
            model_gateway = ModelGatewayBridgeAdapter(hub=self._model_hub)
            prompt_system = PromptSystemProdAdapter(prompts_dir="k1/contracts/prompts")
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
            await self._shared_fabric.shutdown()
            await self._bridge.disconnect()
            self._bus.close()
            self._router.close()
            raise

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
            await self._shared_fabric.shutdown()
            await self._bridge.disconnect()
            self._bus.close()
            self._router.close()
            raise

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

            # ── P4B.8: Shared Phase1 pipeline ────────────────
            # Built after S7 because it does not depend on any earlier
            # tier 1 component. Construction is cheap (lazy_load defers
            # the ~20s familyos_ultrabert model load to first analyze()).
            self._phase1_pipeline = self._build_shared_phase1_pipeline()

            # ── S8: Family-tools (M15) ───────────────────────
            # Bootstrap the FamilyToolsBundle when enabled. Registers
            # the NativeToolProvider with the shared Fabric and creates
            # the K1FamilyStore SQLite WAL connection. Off by default.
            if getattr(self._config, "enable_family_tools", False):
                self._family_tools = self._bootstrap_family_tools()
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
        logger.info("Tier 1 startup complete — all shared components wired")

    def _bootstrap_family_tools(self) -> Any:
        """Build the FamilyToolsBundle (M15) and register it with Fabric.

        Resolves ``KernelConfig.family_tool_service_paths`` (each entry
        ``"package.module:ClassName"``) into ``BaseToolService`` subclasses
        and hands them to :func:`k1.tools.family.bootstrap_family_tools`.

        Failures here are surfaced to ``_startup_tier1`` and trigger the
        standard reverse-order cleanup chain.
        """
        from importlib import import_module

        from k1.tools.family import NullSsePublisher, bootstrap_family_tools

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

        bundle = bootstrap_family_tools(
            fabric=self._shared_fabric,
            sse_publisher=NullSsePublisher(),
            db_path=getattr(self._config, "family_tools_db_path", "./data/k1_family.db"),
            service_classes=tuple(service_classes),
        )
        logger.info(
            "S8: family-tools bundle ready (adapters=%s)",
            bundle.tool_registry.adapter_ids(),
        )
        return bundle

    def _build_shared_phase1_pipeline(self) -> Any:
        """Build the process-wide Phase1 classification pipeline (P4B.8).

        Called once from ``_startup_tier1``. The returned pipeline is shared
        across every session via ``PortBundle.classification``.

        Selection by ``KernelConfig.phase1_pipeline``:
          * ``"stub"``  → ``StubPhase1Pipeline`` (keyword-based, no model load)
          * ``"ultrabert"`` → ``UltraBERTPhase1Pipeline`` wrapping the
            singleton ``K1UltraBERTAdapter``. The adapter forwards
            ``lazy_load=True`` (default) to ``familyos_ultrabert.Client`` so
            the ~20s model load happens on first ``analyze()`` call, not at
            boot. ``warmup_on_startup=True`` triggers the (cheap, in-process)
            warmup path that ``Client`` runs after first load.
        """
        from k1.concierge.config.loader import get_config
        from k1.concierge.fsm.phase1 import KeywordPhase1Pipeline, StubPhase1Pipeline

        pipeline_kind = getattr(self._config, "phase1_pipeline", "stub").lower()
        if pipeline_kind != "ultrabert":
            logger.info("Phase1 pipeline: stub (keyword-based)")
            return StubPhase1Pipeline()

        # ultrabert path
        from k1.concierge.fsm.ultrabert_adapter import K1UltraBERTAdapter
        from k1.concierge.fsm.ultrabert_phase1 import UltraBERTPhase1Pipeline

        phase1_cfg = get_config().phase1
        adapter = K1UltraBERTAdapter.get_instance(
            warmup=bool(getattr(self._config, "phase1_warmup_on_startup", False))
            or phase1_cfg.warmup_on_startup,
            warmup_rounds=phase1_cfg.warmup_rounds,
            lazy_load=phase1_cfg.lazy_load,
            backend=phase1_cfg.backend,
            device=phase1_cfg.device,
            cache_size=phase1_cfg.cache_size,
            cache_ttl_s=phase1_cfg.cache_ttl_s,
        )
        # 4.3.2: Availability gate. If the UltraBERT model failed to
        # load (missing weights, unsupported backend, GPU OOM, etc.),
        # fall back to the richer KeywordPhase1Pipeline rather than the
        # minimal StubPhase1Pipeline. Surface that we degraded so ops
        # has a clear signal in logs.
        if not adapter.is_available():
            logger.warning(
                "Phase1 pipeline: ultrabert requested but adapter unavailable; "
                "falling back to KeywordPhase1Pipeline (richer keyword baseline)"
            )
            return KeywordPhase1Pipeline()

        pipeline = UltraBERTPhase1Pipeline(
            adapter=adapter,
            fallback=KeywordPhase1Pipeline() if phase1_cfg.degradation_fallback_enabled else None,
            config=phase1_cfg,
        )
        logger.info(
            "Phase1 pipeline: ultrabert (singleton, lazy_load=%s, warmup=%s, "
            "adapter_available=%s)",
            phase1_cfg.lazy_load,
            phase1_cfg.warmup_on_startup,
            adapter.is_available(),
        )
        return pipeline

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
        self._bridge = None
        self._orchestrator = None
        self._planner = None
        self._phase1_pipeline = None
        self._hil_service = None  # E7.M1.1
        self._self_model_bundle = None  # M5.E3.I2

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
            P1: Per-session Bus + MailboxRouter + front/back Mailboxes
            P2–P7: Remaining session components (Epic 2.3 issues)
        """
        # ── P1: Per-session Bus + Mailboxes ───────────────────
        session_bus = BusFactory.create_local_ordered(capture=False)
        session_router = BusFactory.create_mailbox_router()
        # Use canonical ACTOR_FRONT / ACTOR_BACK constants: the router is
        # already per-session (so names don't need a session_id suffix),
        # and ConciergeController._deliver_to_{front,back} hard-codes
        # these names via k1.concierge.bus.setup.
        from k1.concierge.bus.setup import ACTOR_BACK, ACTOR_FRONT

        front_mailbox = session_router.register(ACTOR_FRONT)
        back_mailbox = session_router.register(ACTOR_BACK)

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
            session_prompt_sys = PromptSystemProdAdapter(prompts_dir="k1/contracts/prompts")
            session_bridge_client = self._bridge.get_client()
            session_bridge_adapter = BridgeConnectionAdapter(client=session_bridge_client)

            session_fabric = FabricFactory.create_with_ports(
                state_reader=session_state_reader,
                event_port=session_event_port,
                bridge=session_bridge_adapter,
                model_gateway=session_model_gw,
                prompt_system=session_prompt_sys,
                delta_bus=session_delta_bus,
                production_mode=True,
                hil_port=self._hil_service,  # E7.M1.1: per-session fabric gate
            )
        except Exception:
            ssm.stop()
            session_bus.close()
            session_router.close()
            raise

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
                actor_id, device_meta = self._derive_session_actor(ssm, session_id, device_id)
                session_self_model = build_self_model_handle(
                    self._self_model_bundle,
                    session_id=session_id,
                    actor_id=actor_id,
                    device_id=device_meta,
                    situation_kind=self._config.selfmodel_situation_kind,
                    hil_service=self._hil_service,
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
                classification=self._phase1_pipeline,
                dispatch=session_dispatch,
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
                hil_port=self._hil_service,  # E7.M1.1
            )
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
            front_ctx=session_concierge.front_ctx,
            back_ctx=session_concierge.back_ctx,
            ledger=session_concierge.ledger,
            ledger_store=session_concierge.ledger_store,
            concierge_task=session_concierge.consumer_task,
            self_model=session_self_model,
        )
        self._sessions[session_id] = session
        return session
