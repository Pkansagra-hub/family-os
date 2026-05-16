"""
k1.concierge.factory -- ConciergeFactory for port-injected session wiring.

Composition root for the Concierge subsystem.  Uses ``@classmethod`` pattern
(per whiteboard SIM-D-09) -- no instance state, no constructor.

The factory is the SESSION TIER of the two-tier bootstrap (SIM-D-39).
It receives shared components from the STARTUP TIER (KernelService) and
wires the Concierge-specific subsystem graph using 8 hexagonal ports.

Factory Methods:
  create_with_ports(bus, router, ports, ...)  -- caller provides all ports
  create_standalone()                         -- all test adapters, zero deps
  create_for_testing(overrides)               -- test adapters + real overrides

Private Helpers:
  _build_test_adapters()                      -- 8 test adapter dict
  _construct_concierge(...)                   -- 16-step dependency wiring

Design constraints (SIM-D-09, SIM-D-10, SIM-D-12):
  - @classmethod pattern -- no instance state
  - Returns ConciergeRuntime (clean lifecycle wrapper)
  - 8 external ports = hexagonal boundary
  - Bus + Router are infrastructure (not ports), passed separately
  - Sync construction in factory, async startup in session.start()
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from k1.bus.ports.bus import IBus
from k1.bus.ports.mailbox import IMailbox, IMailboxRouter
from k1.concierge.config.concierge import ConciergeConfig  # canonical location
from k1.concierge.ports import (
    IDeltaPort,
    IDispatchPort,
    IInputPort,
    ILLMPort,
    IMemoryPort,
    IOutputPort,
    IStatePort,
)
from k1.concierge.session import ConciergeRuntime, ConciergeSession
from k1.sessionstate.ports.writer import IWriterPort

if TYPE_CHECKING:
    from k1.kernel.ports.hil_port import IHILPort

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PortBundle -- frozen dataclass holding 8 hexagonal ports
# ---------------------------------------------------------------------------

_ALL_PORT_KEYS = frozenset(
    {
        "input_",
        "output",
        "llm",
        "state",
        "dispatch",
        "delta",
        "memory",
    }
)


@dataclass(frozen=True)
class PortBundle:
    """The 8 hexagonal ports that define the Concierge boundary.

    5 required (factory raises if None), 3 optional (default to null adapters).
    Matches ports.py Protocol definitions exactly.
    """

    # REQUIRED -- factory raises ValueError if None
    delta: IDeltaPort
    input_: IInputPort
    output: IOutputPort
    state: IStatePort
    llm: ILLMPort
    # OPTIONAL -- default to null/test adapters for two-tier boot
    dispatch: IDispatchPort | None = None
    memory: IMemoryPort | None = None
    # P4B.6: writer is passed explicitly (was reach-through into ssm._writer_port)
    writer: IWriterPort | None = None

    def validate_required(self) -> None:
        """Raise ValueError if any required port is None."""
        required = {
            "delta": self.delta,
            "input_": self.input_,
            "output": self.output,
            "state": self.state,
            "llm": self.llm,
        }
        missing = [name for name, port in required.items() if port is None]
        if missing:
            raise ValueError(f"Required ports missing: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# HITL callback helpers (extracted from bootstrap.py lines 270-310)
# ---------------------------------------------------------------------------


def _make_suspended_cb(bus: IBus):
    """Create HITL on_suspended callback that publishes to bus."""
    from k1.concierge.bus.builders import build_task_suspended

    async def _on_suspended(request: Any) -> None:
        env = build_task_suspended(
            payload={
                "task_id": getattr(request, "task_id", ""),
                "hil_type": getattr(request, "hil_type", "clarification"),
                "question": getattr(request, "question", ""),
                "options": getattr(request, "options", []),
                "side_effects": getattr(request, "side_effects", []),
                "timeout_s": int(getattr(request, "timeout_ms", 60_000) / 1000),
            }
        )
        bus.publish(env)

    return _on_suspended


def _make_resume_cb(bus: IBus):
    """Create HITL on_resume callback that publishes to bus."""
    from k1.concierge.bus.builders import build_task_resume

    async def _on_resume(response: Any) -> None:
        env = build_task_resume(
            payload={
                "task_id": getattr(response, "task_id", ""),
                "decision": getattr(response, "decision", "answered"),
                "resolution": getattr(response, "resolution", {}),
                "answer": getattr(response, "raw_user_text", ""),
            }
        )
        bus.publish(env)

    return _on_resume


def _make_timeout_cb(bus: IBus):
    """Create HITL on_timeout callback that publishes to bus."""
    from k1.concierge.bus.builders import build_task_failed

    async def _on_timeout(task_id: str) -> None:
        env = build_task_failed(
            payload={
                "task_id": task_id,
                "reason": "timeout",
                "error_code": "HITL_TIMEOUT",
            }
        )
        bus.publish(env)

    return _on_timeout


# ---------------------------------------------------------------------------
# _build_delta_applicator -- moved from bootstrap.py to break circular import
# ---------------------------------------------------------------------------


def _build_delta_applicator(session_state: Any, bus: IBus) -> Any:
    """Build a DeltaApplicator wired to session state and bus notification."""
    from k1.concierge.delta.applicator import DeltaApplicator
    from k1.concierge.delta.topics import STATE_UPDATED

    def _preflight(section: str, operation: str, estimated_size: int) -> Any:
        if hasattr(session_state, "guard"):
            return session_state.guard.preflight(section, operation, estimated_size)

        class _Approved:
            approved = True
            reason = "no guard"

        return _Approved()

    async def _write(section: str, key: str, operation: str, data: dict) -> None:
        try:
            sec = session_state.get_section(section)
            if sec is None:
                logger.warning("Delta write: section '%s' not found", section)
                return
            if operation == "set":
                if hasattr(sec, "__setitem__"):
                    sec[key] = data
                elif hasattr(sec, "update"):
                    sec.update({key: data})
            elif operation == "update":
                if hasattr(sec, "update"):
                    sec.update({key: data})
                elif hasattr(sec, "__setitem__"):
                    sec[key] = data
            elif operation == "append":
                if hasattr(sec, "append"):
                    sec.append({key: data})
                elif hasattr(sec, "update"):
                    existing = sec.get(key, []) if hasattr(sec, "get") else []
                    if isinstance(existing, list):
                        existing.append(data)
                        sec.update({key: existing})
                    else:
                        sec.update({key: data})
            elif operation == "delete":
                if hasattr(sec, "__delitem__"):
                    try:
                        del sec[key]
                    except (KeyError, IndexError):
                        pass
            logger.debug("Delta applied: section=%s key=%s op=%s", section, key, operation)
        except Exception as exc:
            logger.warning(
                "Delta write failed: section=%s key=%s op=%s err=%s",
                section,
                key,
                operation,
                exc,
            )

    async def _notify(batch_id: str, applied_count: int) -> None:
        import json

        from k1.bus.envelope import Envelope, PayloadFormat, Priority

        payload = json.dumps(
            {"batch_id": batch_id, "applied": applied_count},
            separators=(",", ":"),
        ).encode("utf-8")
        env = Envelope(
            topic=STATE_UPDATED,
            priority=Priority.BACKGROUND,
            payload=payload,
            payload_format=PayloadFormat.JSON,
        )
        bus.publish(env)
        logger.info(
            "Delta notification: batch=%s applied=%d topic=%s",
            batch_id,
            applied_count,
            STATE_UPDATED,
        )

    return DeltaApplicator(
        preflight_fn=_preflight,
        write_fn=_write,
        notify_fn=_notify,
    )


# ---------------------------------------------------------------------------
# Private adapters for OrchestratorStub wiring
# ---------------------------------------------------------------------------


class _DispatchPortFSMAdapter:
    """Adapts IDispatchPort to the handle_task() interface expected by FSM.

    P4B.2: The FSM calls ``self._orchestrator.handle_task(envelope)`` for
    MEDIUM-tier dispatch.  This adapter translates to
    ``IDispatchPort.dispatch_envelope(envelope)``.
    """

    def __init__(self, dispatch: Any) -> None:
        self._dispatch = dispatch

    async def handle_task(self, envelope: Any) -> Any:
        return await self._dispatch.dispatch_envelope(envelope)


# P4B.5: _DeltaEmitAdapter deleted. It was only used by the deleted
# OrchestratorStub trinity (alongside _FabricGatewayAdapter / _StateReadAdapter,
# both removed in P4B.4). Concierge now emits deltas through the
# DeltaAggregator + DeltaApplicator path wired in factory step 10, and
# external dispatch goes through IDispatchPort (P4B.2 / P4B.3).


# ---------------------------------------------------------------------------
# ConciergeFactory
# ---------------------------------------------------------------------------


class ConciergeFactory:
    """Factory that wires a ConciergeRuntime from injected ports.

    Uses @classmethod pattern (SIM-D-09) -- no instance state.
    Returns ConciergeRuntime (SIM-D-12) with clean start/stop lifecycle.

    Public API:
      create_with_ports(...)           -- production: caller provides all ports
      create_standalone()              -- test: all test adapters, zero deps
      create_for_testing(...)          -- test: test adapters with real overrides
      create_request_scope(runtime, ..)-- per-request ConciergeSession wrapper
    """

    def __init__(self) -> None:
        raise TypeError(
            "ConciergeFactory uses @classmethod pattern -- do not instantiate. "
            "Use ConciergeFactory.create_with_ports() etc."
        )

    # ------------------------------------------------------------------
    # Public factory methods
    # ------------------------------------------------------------------

    @classmethod
    def create_with_ports(
        cls,
        *,
        bus: IBus,
        router: IMailboxRouter,
        front_mailbox: IMailbox,
        back_mailbox: IMailbox,
        ports: PortBundle,
        config: ConciergeConfig | None = None,
        hil_port: "IHILPort | None" = None,
    ) -> ConciergeRuntime:
        """Create a fully-wired ConciergeRuntime from explicit ports.

        Args:
            bus: Per-session IBus instance (created by KernelService).
            router: Per-session IMailboxRouter (created by KernelService).
            front_mailbox: Front mailbox from router.
            back_mailbox: Back mailbox from router.
            ports: PortBundle with 8 hexagonal ports.
            config: ConciergeConfig (defaults to all-enabled).
            hil_port: Unified HIL service handle (E4.M1.6).  When provided
                it is attached to the FSM via ``set_hil_port``; when None
                the controller's HIL gates no-op (test ergonomics + the
                pre-E7 kernel boot path).

        Returns:
            ConciergeRuntime -- wired but NOT started. Call ``await runtime.start()``.
        """
        ports.validate_required()
        config = config or ConciergeConfig()
        return cls._construct_concierge(
            bus=bus,
            router=router,
            front_mailbox=front_mailbox,
            back_mailbox=back_mailbox,
            ports=ports,
            config=config,
            hil_port=hil_port,
        )

    @classmethod
    def create_standalone(cls) -> ConciergeRuntime:
        """Create a ConciergeRuntime with all test adapters.

        Zero external deps, < 10ms, suitable for unit tests.
        Returns un-started runtime.
        """
        adapters = cls._build_test_adapters()
        bus = adapters["delta"]
        router = adapters["_router"]
        front_mailbox = adapters["_front_mailbox"]
        back_mailbox = adapters["_back_mailbox"]

        ports = PortBundle(
            delta=bus,
            input_=adapters["input_"],
            output=adapters["output"],
            state=adapters["state"],
            llm=adapters["llm"],
            dispatch=adapters["dispatch"],
            memory=adapters["memory"],
        )

        return cls._construct_concierge(
            bus=bus,
            router=router,
            front_mailbox=front_mailbox,
            back_mailbox=back_mailbox,
            ports=ports,
            config=ConciergeConfig.for_testing(),
        )

    @classmethod
    def create_for_testing(
        cls,
        *,
        overrides: dict[str, Any] | None = None,
        config: ConciergeConfig | None = None,
        hil_port: "IHILPort | None" = None,
    ) -> ConciergeRuntime:
        """Create a ConciergeRuntime with test adapters + optional overrides.

        Use for integration tests needing 1-2 real adapters::

            runtime = ConciergeFactory.create_for_testing(
                overrides={"state": real_ssm, "delta": real_bus}
            )

        Returns un-started runtime.
        """
        adapters = cls._build_test_adapters()
        overrides = overrides or {}

        for key, value in overrides.items():
            if key in adapters:
                adapters[key] = value
            else:
                raise ValueError(
                    f"Unknown override key '{key}'. "
                    f"Valid keys: {sorted(k for k in adapters if not k.startswith('_'))}"
                )

        bus = adapters["delta"]
        router = adapters.get("_router")
        front_mailbox = adapters.get("_front_mailbox")
        back_mailbox = adapters.get("_back_mailbox")

        ports = PortBundle(
            delta=bus,
            input_=adapters["input_"],
            output=adapters["output"],
            state=adapters["state"],
            llm=adapters["llm"],
            dispatch=adapters.get("dispatch"),
            memory=adapters.get("memory"),
        )

        return cls._construct_concierge(
            bus=bus,
            router=router,
            front_mailbox=front_mailbox,
            back_mailbox=back_mailbox,
            ports=ports,
            config=config or ConciergeConfig.for_testing(),
            hil_port=hil_port,
        )

    # ------------------------------------------------------------------
    # Per-request scope
    # ------------------------------------------------------------------

    @staticmethod
    def create_request_scope(
        runtime: ConciergeRuntime,
        *,
        trace_id: str | None = None,
        device_id: str | None = None,
        task_id: str | None = None,
    ) -> ConciergeSession:
        """Create a per-request ConciergeSession from a long-lived runtime.

        Each session gets scoped ToolContext copies with fresh
        ``cognitive_trace_id``, ``bundle_idempotency_cache``, ``active_device_id``,
        ``active_task_id``, and ``capability_cache``.  Shared fields
        (``session_manager``, ``actor``, ``writer_port``, ``hil_coordinator``,
        ``dispatch``, ``recall_fn``) reference the runtime's ToolContext.

        Args:
            runtime: Long-lived ConciergeRuntime (must already be started
                     or at least constructed).
            trace_id: Per-request trace ID.  Auto-generated if None.
            device_id: Device that triggered this request.
            task_id: Task context for this request.

        Returns:
            ConciergeSession -- per-request scope. Call ``await session.close()``
            when the turn is complete.
        """
        from copy import copy as _shallow_copy

        tid = trace_id or uuid.uuid4().hex

        def _scope_ctx(base_ctx: Any) -> Any:
            if base_ctx is None:
                return None
            ctx = _shallow_copy(base_ctx)
            ctx.cognitive_trace_id = tid
            ctx.bundle_idempotency_cache = {}
            ctx.active_device_id = device_id
            ctx.active_task_id = task_id
            ctx.capability_cache = None
            return ctx

        return ConciergeSession(
            runtime=runtime,
            trace_id=tid,
            front_ctx=_scope_ctx(runtime.front_ctx),
            back_ctx=_scope_ctx(runtime.back_ctx),
            active_device_id=device_id,
            active_task_id=task_id,
        )

    # ------------------------------------------------------------------
    # Private: test adapter builder
    # ------------------------------------------------------------------

    @classmethod
    def _build_test_adapters(cls) -> dict[str, Any]:
        """Build all 8 test adapters + bus infrastructure for standalone boot."""
        from k1.concierge.adapters import (
            InMemoryStateAdapter,
            MockDispatchAdapter,
            MockMemoryAdapter,
            TestInputAdapter,
            TestOutputAdapter,
            create_test_bus,
        )
        from k1.concierge.adapters.test_llm import TestModelHubBridge

        bus = create_test_bus()

        router: Any = None
        front_mailbox: Any = None
        back_mailbox: Any = None
        if hasattr(bus, "router"):
            router = bus.router
        if router is not None and hasattr(router, "get_or_create"):
            front_mailbox = router.get_or_create("front_half")
            back_mailbox = router.get_or_create("back_half")

        state = InMemoryStateAdapter()
        # Seed minimal sections required by ConciergeController.set_session_state:
        # task_state (get_suspended), task_artifacts (rebind), control (bind_control)
        cls._seed_minimal_state(state)

        return {
            "input_": TestInputAdapter(),
            "output": TestOutputAdapter(),
            "llm": TestModelHubBridge(),
            "state": state,
            "dispatch": MockDispatchAdapter(),
            "delta": bus,
            "memory": MockMemoryAdapter(),
            "_router": router,
            "_front_mailbox": front_mailbox,
            "_back_mailbox": back_mailbox,
        }

    @staticmethod
    def _seed_minimal_state(state: Any) -> None:
        """Seed InMemoryStateAdapter with stub sections for FSM binding."""
        from k1.sessionstate.public_types import TaskArtifactsSection, TaskStateSection
        from k1.sessionstate.sections.control import ControlSection

        state.seed("task_state", TaskStateSection())
        state.seed("task_artifacts", TaskArtifactsSection())
        state.seed("control", ControlSection(session_id="test-standalone"))

    # ------------------------------------------------------------------
    # Private: 16-step construction sequence (SIM-D-10, Phases B-H)
    # ------------------------------------------------------------------

    @classmethod
    def _construct_concierge(
        cls,
        *,
        bus: IBus,
        router: Any,
        front_mailbox: Any,
        back_mailbox: Any,
        ports: PortBundle,
        config: ConciergeConfig,
        hil_port: "IHILPort | None" = None,
    ) -> ConciergeRuntime:
        """16-step wiring sequence -- returns un-started ConciergeRuntime."""
        from k1.concierge.fsm.controller import ConciergeController
        from k1.concierge.tools.dispatcher import (
            create_back_dispatcher,
            create_front_dispatcher,
        )
        from k1.concierge.tools.implementations import ToolContext

        # Step 1: Create FSM
        fsm = ConciergeController(bus=bus, router=router)

        # Step 3: Wire ledger (optional)
        ledger = None
        ledger_store = None
        if config.enable_ledger:
            from k1.concierge.ledger.store import InMemoryLedgerStore
            from k1.concierge.ledger.writer import LedgerWriter

            session_id = config.session_id or f"k-{uuid.uuid4().hex[:8]}"
            ledger_store = InMemoryLedgerStore()
            ledger = LedgerWriter(store=ledger_store, session_id=session_id)
            fsm.set_ledger(ledger)
            logger.info("Ledger created for session=%s", session_id)

        # Step 4: Wire history sink from state_port
        try:
            history_section = ports.state.get_section("history_active")
            if history_section and hasattr(history_section, "add_turn"):
                fsm.set_history_sink(history_section)
        except Exception:
            pass

        # Step 5: Wire session state
        fsm.set_session_state(ports.state)

        # Step 6: Recall function from memory_port
        recall_fn = ports.memory.recall if ports.memory is not None else _null_recall

        # Step 7: ToolContext for front + back
        # P4B.6: writer is now an explicit port on PortBundle (no more reach-through
        # into the IStatePort adapter's private _writer_port attribute).
        # M17.E1.I1: ``allow_dispatch_passthrough`` controls whether back tools
        # silently return ``{"_poc": True}`` when ctx.dispatch is None. Default
        # False -- production must have a real IDispatchPort or get a clear
        # ``dispatch_not_wired`` error.
        writer_port = ports.writer
        allow_dispatch_passthrough = bool(getattr(config, "allow_dispatch_passthrough", False))
        _ctx_session_id = getattr(config, "session_id", "") or ""
        front_ctx = ToolContext(
            session_manager=ports.state,
            cognitive_trace_id=f"k-front-{uuid.uuid4().hex[:6]}",
            actor="front",
            recall_fn=recall_fn,
            dispatch=ports.dispatch,
            writer_port=writer_port,
            allow_dispatch_passthrough=allow_dispatch_passthrough,
            session_id=_ctx_session_id,
        )
        back_ctx = ToolContext(
            session_manager=ports.state,
            cognitive_trace_id=f"k-back-{uuid.uuid4().hex[:6]}",
            actor="back",
            recall_fn=recall_fn,
            dispatch=ports.dispatch,
            writer_port=writer_port,
            allow_dispatch_passthrough=allow_dispatch_passthrough,
            session_id=_ctx_session_id,
        )

        # Step 8: Tool dispatchers (P3.4c: defaults to 'simple'; back actor
        # rebinds per-task via _maybe_rebind_back_dispatcher).
        front_dispatcher = create_front_dispatcher(
            tier="simple",
            ctx=front_ctx,
            bus=bus,
        )
        back_dispatcher = create_back_dispatcher(
            tier="simple",
            ctx=back_ctx,
            bus=bus,
        )

        # Step 9: ExperienceLayer (optional)
        experience = None
        if config.enable_experience:
            from k1.concierge.experience.layer import ExperienceLayer

            experience = ExperienceLayer()

        # Step 10: Delta aggregator + applicator (optional)
        delta_aggregator = None
        delta_applicator = None
        if config.enable_delta:
            from k1.concierge.delta.aggregator import DeltaAggregator

            delta_applicator = _build_delta_applicator(ports.state, bus)
            delta_aggregator = DeltaAggregator(
                flush_fn=delta_applicator.apply,
                batch_window_ms=config.delta_batch_window_ms,
            )

        # Step 11: HITL coordinator (optional)
        # E4.M1.6: when the kernel constructs a unified HumanInTheLoopService
        # and passes it through ``hil_port=``, attach it to the FSM here.
        # Until E7 wires real construction, callers may pass ``None`` and
        # the FSM HIL gates remain inert.
        # E7.M1.1: also surface the unified port on the runtime as
        # ``hil_port`` so KernelService.SessionInstance and
        # KernelRuntime can reach it without crawling into the FSM.
        hitl = hil_port
        if hil_port is not None:
            fsm.set_hil_port(hil_port)
            logger.info(
                "ConciergeFactory: attached unified HIL port %s to FSM",
                type(hil_port).__name__,
            )
        elif config.enable_hitl:
            logger.warning(
                "ConciergeFactory: enable_hitl=True but no hil_port provided; "
                "HITL gates will no-op until kernel wires HumanInTheLoopService",
            )

        # Step 12: Weave + Activity tracker
        if hasattr(fsm, "set_weave_batcher"):
            from k1.concierge.protocols.weave_batcher import WeaveBatcher

            async def _weave_flush(results: list) -> None:  # type: ignore[type-arg]
                logger.info("WeaveBatcher flush: %d results", len(results))

            batcher = WeaveBatcher(flush_fn=_weave_flush)
            fsm.set_weave_batcher(batcher)

        if hasattr(fsm, "set_weave_policy"):
            from k1.concierge.protocols.weave_policy import WeavePolicy

            fsm.set_weave_policy(WeavePolicy())

        if hasattr(fsm, "set_activity_tracker"):
            from k1.concierge.protocols.weave_policy import UserActivityTracker

            fsm.set_activity_tracker(UserActivityTracker())

        # Step 13: Dead letter consumer (optional)
        dead_letter = None
        if config.enable_dead_letter_consumer and config.dead_letter_enabled:
            from k1.concierge.fsm.dead_letter_consumer import DeadLetterConsumer

            dead_letter = DeadLetterConsumer(bus=bus)
            logger.info("DeadLetterConsumer attached to bus")

        # Step 14: Orchestrator wiring via IDispatchPort (P4B.2)
        orchestrator = None
        if ports.dispatch is not None and config.enable_orchestrator:
            orchestrator = _DispatchPortFSMAdapter(ports.dispatch)
            fsm.set_orchestrator(orchestrator)

        # M16.E1.I3: propagate the passthrough-stub gate to the FSM so
        # HIGH-tier dispatch with no orchestrator surfaces loudly when
        # the deployment did not opt into the legacy fallback.
        if hasattr(fsm, "set_allow_planner_passthrough"):
            fsm.set_allow_planner_passthrough(
                bool(getattr(config, "allow_planner_passthrough", False))
            )

        # Step 15: Subscribe front events
        front_subs: list[Any] = []
        if router is not None:
            from k1.concierge.actors.front import subscribe_front_events

            def _route_front(envelope: Any) -> None:
                try:
                    router.deliver("front_half", envelope)
                except Exception:
                    logger.exception(
                        "Front subscription routing failed: topic=%s",
                        envelope.topic,
                    )

            front_subs = subscribe_front_events(bus, _route_front)

        # Step 16: Build and return ConciergeRuntime
        return ConciergeRuntime(
            bus=bus,
            router=router,
            front_mailbox=front_mailbox,
            back_mailbox=back_mailbox,
            fsm=fsm,
            model=ports.llm,
            input_port=ports.input_,
            output_port=ports.output,
            dispatch_port=ports.dispatch,
            session_state=ports.state,
            front_dispatcher=front_dispatcher,
            back_dispatcher=back_dispatcher,
            front_subscriptions=front_subs,
            front_ctx=front_ctx,
            back_ctx=back_ctx,
            experience_layer=experience,
            delta_aggregator=delta_aggregator,
            delta_applicator=delta_applicator,
            hil_port=hitl,
            orchestrator=orchestrator,
            ledger=ledger,
            ledger_store=ledger_store,
            dead_letter_consumer=dead_letter,
        )


# ---------------------------------------------------------------------------
# Null recall (used when no IMemoryPort is provided)
# ---------------------------------------------------------------------------


async def _null_recall(
    query: str,
    memory_types: list[str] | None = None,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """No-op recall for when IMemoryPort is not provided."""
    return []
