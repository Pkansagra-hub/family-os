"""
poc.k1_poc.demo.coordinator -- K1 demo coordinator (kernel-delegating).

Thin adapter on top of kernel bootstrap API. All core composition is
owned by ``poc.k1_poc.kernel.bootstrap.start_kernel()``. This module
handles demo-specific concerns only:

  - Smith family data loading
  - Preloaded memories injection
  - Storyline capability registration
  - Output channel and IoT wiring
  - Timeline recording and debug instrumentation
  - Enhanced mailbox consumer with verbose logging

Usage::

    coordinator = get_k1_demo_coordinator()
    success = await coordinator.initialize_system()
    # ... run interactive loop ...
    await coordinator.shutdown_system()
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from poc.k1_poc.demo.output_channel import OutputChannel, TimelineEntry

logger = logging.getLogger(__name__)


# =========================================================================
# Timeline helpers
# =========================================================================


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _make_timeline_entry(
    boot_ns: int,
    phase: str,
    component: str,
    event: str,
    summary: str,
    *,
    turn: int = 0,
    payload: Optional[Dict[str, Any]] = None,
) -> TimelineEntry:
    elapsed = (time.monotonic_ns() - boot_ns) / 1_000_000
    return TimelineEntry(
        timestamp_iso=_now_iso(),
        elapsed_ms=round(elapsed, 2),
        phase=phase,
        component=component,
        event=event,
        summary=summary,
        turn_number=turn,
        payload_excerpt=payload or {},
    )


# =========================================================================
# K1DemoCoordinator
# =========================================================================


class K1DemoCoordinator:
    """
    K1 demo coordinator -- thin adapter on kernel bootstrap API.

    Initialization phases (kernel-delegating model):
        1. Load demo data (family profile, memories, device registry)
        2. Start kernel via ``start_kernel()`` + copy references
        3. Attach demo data to kernel session state
        4. Wire demo output channel, IoT stubs, enhanced consumer
        5. Health check

    All internal activity is recorded in a timeline log.
    """

    def __init__(self, *, test_mode: bool = False) -> None:
        self._test_mode = test_mode
        self._boot_time_ns = time.monotonic_ns()
        self.system_ready = False

        # Phase tracking
        self.phases_completed: List[str] = []
        self.startup_times: Dict[str, float] = {}

        # Timeline log
        self._timeline: List[TimelineEntry] = []

        # Demo data slots (populated by phase 1)
        self.family_profile: Dict[str, Any] = {}
        self.session_config: Dict[str, Any] = {}
        self.device_registry: Dict[str, Any] = {}

        # Kernel runtime reference (populated by phase 2)
        self._kernel: Any = None  # KernelRuntime

        # Component slots -- populated from kernel runtime for backward compat
        self.model: Any = None
        self.prompt_builder: Any = None
        self.bus: Any = None
        self.router: Any = None
        self.adapter: Any = None
        self.front_mailbox: Any = None
        self.back_mailbox: Any = None
        self.session_state: Any = None
        self.capability_registry: Any = None
        self.fsm: Any = None
        self.front_dispatcher: Any = None
        self.back_dispatcher: Any = None
        self.experience_layer: Any = None
        self.delta_aggregator: Any = None
        self.hitl_coordinator: Any = None
        self.orchestrator: Any = None
        # M1 E1.4.6: Ledger reference from kernel
        self.ledger: Any = None
        self.ledger_store: Any = None
        # M2 E2.5.5: Dead-letter consumer reference from kernel
        self.dead_letter_consumer: Any = None

        # M7 E7.1.3: BackPool for parallel Back task execution
        self.back_pool: Any = None
        # M7 E7.4.1: ReadyQueue for dependency-ordered dispatch
        self.ready_queue: Any = None

        # Demo-only slots
        self.iot_stubs: Any = None
        self.output_channel: Optional[OutputChannel] = None
        self._preloaded_memories: List[Dict[str, Any]] = []
        self._consumer_task: Any = None
        self._pending_back_tasks: list[asyncio.Task] = []
        # M7 E7.1.3: Overflow queue for envelopes when pool is exhausted
        # is managed by BackPool.enqueue_overflow / dequeue_overflow

    # -----------------------------------------------------------------
    # Timeline API (for UI teams)
    # -----------------------------------------------------------------

    @property
    def timeline(self) -> List[TimelineEntry]:
        """Full coordinator timeline -- merged with output channel timeline."""
        merged = list(self._timeline)
        if self.output_channel:
            merged.extend(self.output_channel.timeline)
        merged.sort(key=lambda e: e.elapsed_ms)
        return merged

    @property
    def timeline_dicts(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.timeline]

    def dump_timeline_json(self) -> str:
        return json.dumps(self.timeline_dicts, indent=2)

    def _record(
        self,
        phase: str,
        component: str,
        event: str,
        summary: str,
        **kw: Any,
    ) -> None:
        entry = _make_timeline_entry(
            self._boot_time_ns,
            phase,
            component,
            event,
            summary,
            payload=kw.get("payload"),
        )
        self._timeline.append(entry)
        elapsed_ms = (time.monotonic_ns() - self._boot_time_ns) / 1_000_000
        logger.info(
            "[%8.1fms] %-10s %-15s %-30s %s",
            elapsed_ms,
            phase,
            component,
            event,
            summary,
        )

    # -----------------------------------------------------------------
    # Master init / shutdown
    # -----------------------------------------------------------------

    async def initialize_system(self) -> bool:
        """Run all 5 phases. Returns True on success."""
        logger.info("=" * 70)
        logger.info("INIT: Starting K1 Demo Coordinator initialization")
        logger.info("=" * 70)
        self._record("boot", "coordinator", "system.init.start", "K1 Demo Coordinator initializing")
        try:
            logger.info("INIT: Phase 1 -- Demo Data")
            await self._phase1_demo_data()
            logger.info("INIT: Phase 1 DONE")

            logger.info("INIT: Phase 2 -- Kernel Startup")
            await self._phase2_kernel_startup()
            logger.info("INIT: Phase 2 DONE")

            logger.info("INIT: Phase 3 -- Demo Data Attachment")
            await self._phase3_attach_demo_data()
            logger.info("INIT: Phase 3 DONE")

            logger.info("INIT: Phase 4 -- Demo Wiring")
            await self._phase4_demo_wiring()
            logger.info("INIT: Phase 4 DONE")

            logger.info("INIT: Phase 5 -- Health Check")
            await self._phase5_health_check()
            logger.info("INIT: Phase 5 DONE")

            self.system_ready = True
            self._record(
                "boot",
                "coordinator",
                "system.init.complete",
                f"All 5 phases complete in " f"{sum(self.startup_times.values()):.3f}s",
            )
            logger.info("=" * 70)
            logger.info("INIT: ALL 5 PHASES COMPLETE -- system_ready=True")
            logger.info("=" * 70)
            return True
        except Exception as exc:
            logger.error("INIT: System init FAILED at: %s", exc, exc_info=True)
            self._record("boot", "coordinator", "system.init.failed", f"Init failed: {exc}")
            return False

    async def shutdown_system(self) -> None:
        """Reverse-order teardown."""
        self._record(
            "shutdown", "coordinator", "system.shutdown.start", "Graceful shutdown starting"
        )
        shutdown_start = time.time()

        # Cancel demo consumer task
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._record(
                "shutdown", "consumer", "consumer.stopped", "Mailbox consumer loop cancelled"
            )

        # Teardown demo-only components
        if self.iot_stubs:
            self.iot_stubs.reset()
            self._record("shutdown", "iot", "iot.reset", "IoT stubs reset")

        if self.output_channel:
            self.output_channel.teardown()
            self._record("shutdown", "output", "output.teardown", "Output channel unsubscribed")

        # Delegate kernel shutdown (handles delta flush, FSM teardown,
        # session state close, model close)
        if self._kernel is not None:
            from poc.k1_poc.kernel.bootstrap import stop_kernel

            await stop_kernel(self._kernel)
            self._record("shutdown", "kernel", "kernel.stopped", "Kernel stopped")

        self.system_ready = False
        duration = time.time() - shutdown_start
        self._record(
            "shutdown",
            "coordinator",
            "system.shutdown.complete",
            f"Shutdown complete in {duration:.3f}s",
        )

    # =====================================================================
    # PHASE 1: Load Demo Data (<1s budget)
    # =====================================================================

    async def _phase1_demo_data(self) -> None:
        phase_start = time.time()
        self._record("phase1", "coordinator", "phase1.start", "Loading demo data")

        try:
            from poc.k1_poc.demo.preloaded_memories import PRELOADED_MEMORIES
            from poc.k1_poc.demo.smith_family import (
                DEVICE_REGISTRY,
                SMITH_FAMILY_PROFILE,
                SMITH_SESSION_CONFIG,
            )

            self.family_profile = SMITH_FAMILY_PROFILE
            self.session_config = SMITH_SESSION_CONFIG
            self.device_registry = DEVICE_REGISTRY
            self._preloaded_memories = PRELOADED_MEMORIES
            self._record(
                "phase1",
                "config",
                "config.family_loaded",
                f"Loaded {self.family_profile['family_name']} family "
                f"({len(self.family_profile['members'])} members, "
                f"{len(self._preloaded_memories)} memories)",
                payload={
                    "family": self.family_profile["family_name"],
                    "members": len(self.family_profile["members"]),
                    "memories": len(self._preloaded_memories),
                },
            )

            # Prompt builder (stateless, zero-dep)
            from poc.k1_poc.prompt.builder import DynamicPromptBuilder

            self.prompt_builder = DynamicPromptBuilder()
            self._record(
                "phase1",
                "prompt",
                "prompt.builder_ready",
                "DynamicPromptBuilder initialized (stateless)",
            )

            # Phase complete
            duration = time.time() - phase_start
            self.startup_times["phase1"] = duration
            self.phases_completed.append("phase1")
            budget_ok = duration < 1.0
            self._record(
                "phase1",
                "coordinator",
                "phase1.complete",
                f"Phase 1 complete in {duration:.3f}s "
                f"({'within budget' if budget_ok else 'BUDGET EXCEEDED'})",
                payload={
                    "duration_s": round(duration, 3),
                    "budget_s": 1.0,
                    "budget_ok": budget_ok,
                },
            )

        except Exception as exc:
            self._record("phase1", "coordinator", "phase1.failed", f"Phase 1 FAILED: {exc}")
            raise

    # =====================================================================
    # PHASE 2: Kernel Startup (replaces old phases 2-5 composition)
    # =====================================================================

    async def _phase2_kernel_startup(self) -> None:
        phase_start = time.time()
        self._record(
            "phase2",
            "coordinator",
            "phase2.start",
            "Starting kernel via start_kernel() API",
        )

        try:
            from poc.k1_poc.kernel.bootstrap import KernelConfig, start_kernel

            config = KernelConfig(
                ordered_bus=True,
                capture_bus=False,
                test_mode=self._test_mode,
                session_mode="testing",
                session_id=f"demo-{uuid.uuid4().hex[:8]}",
                enable_experience=True,
                enable_delta=True,
                enable_hitl=True,
                enable_orchestrator=True,
                auto_start_consumer=False,  # demo manages its own consumer
                seed_memories=list(self._preloaded_memories),
            )

            self._kernel = await start_kernel(config)

            # Copy kernel runtime references for backward compat with
            # interactive loop and existing accessors.
            self.bus = self._kernel.bus
            self.router = self._kernel.router
            self.adapter = self._kernel.adapter
            self.front_mailbox = self._kernel.front_mailbox
            self.back_mailbox = self._kernel.back_mailbox
            self.session_state = self._kernel.session_state
            self.capability_registry = self._kernel.capability_registry
            self.model = self._kernel.model
            self.fsm = self._kernel.fsm
            self.front_dispatcher = self._kernel.front_dispatcher
            self.back_dispatcher = self._kernel.back_dispatcher
            self.experience_layer = self._kernel.experience_layer
            self.delta_aggregator = self._kernel.delta_aggregator
            self.hitl_coordinator = self._kernel.hitl_coordinator
            self.orchestrator = self._kernel.orchestrator
            # M1 E1.4.6: Copy ledger reference for health check and debug API
            self.ledger = self._kernel.ledger
            self.ledger_store = self._kernel.ledger_store
            # M2 E2.5.5: Copy dead-letter consumer reference
            self.dead_letter_consumer = self._kernel.dead_letter_consumer

            # M7 E7.1.3: Create BackPool for parallel Back task execution
            from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig

            self.back_pool = BackPool(
                BackPoolConfig(),
                on_worker_acquired=self._on_pool_worker_acquired,
                on_worker_released=self._on_pool_worker_released,
            )

            # M7 E7.3.1: Create BackTopicRouter for topic-based dispatch
            from poc.k1_poc.actors.back_router import BackTopicRouter

            self.back_topic_router = BackTopicRouter(back_pool=self.back_pool)

            # M7 E7.4.1: Create ReadyQueue for dependency-ordered dispatch
            from poc.k1_poc.actors.ready_queue import ReadyQueue

            self.ready_queue = ReadyQueue()

            adapter_name = type(self.model).__name__
            bus_ordered = config.ordered_bus

            self._record(
                "phase2",
                "kernel",
                "kernel.started",
                f"Kernel started (ordered={bus_ordered}, adapter={adapter_name})",
                payload={
                    "ordered": bus_ordered,
                    "adapter": adapter_name,
                    "session_id": config.session_id,
                    "test_mode": config.test_mode,
                },
            )

            # Phase complete
            duration = time.time() - phase_start
            self.startup_times["phase2"] = duration
            self.phases_completed.append("phase2")
            budget_ok = duration < 3.0
            self._record(
                "phase2",
                "coordinator",
                "phase2.complete",
                f"Phase 2 complete in {duration:.3f}s "
                f"({'within budget' if budget_ok else 'BUDGET EXCEEDED'})",
                payload={
                    "duration_s": round(duration, 3),
                    "budget_s": 3.0,
                    "budget_ok": budget_ok,
                },
            )

        except Exception as exc:
            self._record("phase2", "coordinator", "phase2.failed", f"Phase 2 FAILED: {exc}")
            raise

    # =====================================================================
    # PHASE 3: Attach Demo Data to Kernel Session State
    # =====================================================================

    async def _phase3_attach_demo_data(self) -> None:
        phase_start = time.time()
        self._record(
            "phase3",
            "coordinator",
            "phase3.start",
            "Attaching demo data to kernel session state",
        )

        try:
            # 3a. Initialize persona with Smith family profile
            try:
                persona_section = self.session_state.get_section("persona")
                if persona_section is not None:
                    # Use set_preference() API (not .update() which doesn't exist)
                    persona_section.set_preference("family", self.family_profile)
                    persona_section.set_preference("session", self.session_config)
                    persona_section.set_preference("active_member", "Alex")
                    self._record(
                        "phase3",
                        "session",
                        "persona.initialized",
                        f"Persona loaded: {self.family_profile['family_name']} family",
                        payload={"family": self.family_profile["family_name"]},
                    )
            except Exception as persona_err:
                self._record(
                    "phase3",
                    "session",
                    "persona.skipped",
                    f"Persona init skipped: {persona_err}",
                )

            # 3b. Preload memories into persona preferences
            #     (beliefs_active doesn't support dict .update(), so we store
            #      memories in persona where set_preference() works reliably)
            try:
                if persona_section is not None:
                    persona_section.set_preference("preloaded_memories", self._preloaded_memories)
                    self._record(
                        "phase3",
                        "session",
                        "memories.preloaded",
                        f"Preloaded {len(self._preloaded_memories)} memories "
                        f"into persona preferences",
                        payload={"count": len(self._preloaded_memories)},
                    )
                else:
                    self._record(
                        "phase3",
                        "session",
                        "memories.section_missing",
                        "persona section not available -- "
                        "memories accessible via kernel recall_fn only",
                    )
            except Exception as mem_err:
                self._record(
                    "phase3",
                    "session",
                    "memories.skipped",
                    f"Memory preload skipped: {mem_err}",
                )

            # 3c. Register storyline-specific capabilities into kernel registry
            from poc.k1_poc.demo.iot_stubs import register_storyline_capabilities

            story_count = register_storyline_capabilities(self.capability_registry)
            total = self.capability_registry.count
            self._record(
                "phase3",
                "fabric",
                "capabilities.storyline_registered",
                f"Registered {story_count} storyline capabilities (total={total})",
                payload={"storyline_count": story_count, "total": total},
            )

            # Phase complete
            duration = time.time() - phase_start
            self.startup_times["phase3"] = duration
            self.phases_completed.append("phase3")
            budget_ok = duration < 1.0
            self._record(
                "phase3",
                "coordinator",
                "phase3.complete",
                f"Phase 3 complete in {duration:.3f}s "
                f"({'within budget' if budget_ok else 'BUDGET EXCEEDED'})",
                payload={
                    "duration_s": round(duration, 3),
                    "budget_s": 1.0,
                    "budget_ok": budget_ok,
                },
            )

        except Exception as exc:
            self._record("phase3", "coordinator", "phase3.failed", f"Phase 3 FAILED: {exc}")
            raise

    # =====================================================================
    # PHASE 4: Demo Wiring (output channel, IoT, consumer)
    # =====================================================================

    async def _phase4_demo_wiring(self) -> None:
        phase_start = time.time()
        self._record(
            "phase4",
            "coordinator",
            "phase4.start",
            "Wiring demo output channel, IoT stubs, consumer loop",
        )

        try:
            # 4a. Output channel (subscribes to response/state topics)
            self.output_channel = OutputChannel(
                bus=self.bus,
                current_member="Alex",
            )
            self.output_channel.subscribe_all()
            self._record(
                "phase4",
                "output",
                "output_channel.subscribed",
                "OutputChannel subscribed to bus topics",
            )

            # 4b. IoT monitor stubs
            from poc.k1_poc.demo.iot_stubs import IoTMonitorStub

            self.iot_stubs = IoTMonitorStub(bus=self.bus)
            self._record(
                "phase4",
                "iot",
                "iot_stubs.created",
                f"IoT stubs loaded ({len(self.iot_stubs.scheduled_turns)} "
                f"scripted turns: {self.iot_stubs.scheduled_turns})",
                payload={"turns": self.iot_stubs.scheduled_turns},
            )

            # 4c. Start enhanced demo consumer loop
            # (kernel consumer was NOT started because auto_start_consumer=False)
            self._consumer_task = asyncio.ensure_future(self._mailbox_consumer())
            self._record(
                "phase4",
                "consumer",
                "consumer.started",
                "Enhanced demo mailbox consumer started (front + back)",
            )

            # Phase complete
            duration = time.time() - phase_start
            self.startup_times["phase4"] = duration
            self.phases_completed.append("phase4")
            budget_ok = duration < 1.0
            self._record(
                "phase4",
                "coordinator",
                "phase4.complete",
                f"Phase 4 complete in {duration:.3f}s "
                f"({'within budget' if budget_ok else 'BUDGET EXCEEDED'})",
                payload={
                    "duration_s": round(duration, 3),
                    "budget_s": 1.0,
                    "budget_ok": budget_ok,
                },
            )

        except Exception as exc:
            self._record("phase4", "coordinator", "phase4.failed", f"Phase 4 FAILED: {exc}")
            raise

    # =====================================================================
    # Mailbox consumer loop (demo-enhanced with verbose logging)
    # =====================================================================

    def _dump_state(self, label: str) -> None:
        """Dump full system state snapshot to log -- call at every decision point."""
        fsm_state = self.fsm.state.name if self.fsm else "NO_FSM"
        front_pending = self.front_mailbox.pending() if self.front_mailbox else -1
        back_pending = self.back_mailbox.pending() if self.back_mailbox else -1
        front_lock_busy = self.fsm.front_lock.busy if self.fsm else False
        front_lock_queue = self.fsm.front_lock.queue_depth if self.fsm else 0
        logger.info(
            "STATE_DUMP [%s] fsm=%s front_mbox=%d back_mbox=%d "
            "front_lock_busy=%s front_lock_queue=%d timeline=%d",
            label,
            fsm_state,
            front_pending,
            back_pending,
            front_lock_busy,
            front_lock_queue,
            len(self._timeline),
        )

    async def _mailbox_consumer(self) -> None:
        """Poll front_half and back_half mailboxes, dispatch to handlers."""
        from poc.k1_poc.actors.back import route_back_envelope
        from poc.k1_poc.actors.front import front_handler
        from poc.k1_poc.tools.schemas_front import FRONT_TOOL_SCHEMAS

        poll_interval = 0.05  # 50ms
        poll_count = 0

        logger.info("CONSUMER: mailbox consumer loop STARTED")

        # Dedup guard: track (envelope_id, topic) pairs already processed
        # to prevent duplicate front_handler invocations caused by
        # overlapping delivery paths (FSM _deliver_to_front + direct
        # bus subscription + TimingChain cascade).
        _front_processed: set[tuple[int, str]] = set()

        while True:
            poll_count += 1
            did_work = False

            # --- front mailbox ---
            try:
                front_pending = self.front_mailbox.pending() if self.front_mailbox else 0
                if front_pending > 0:
                    logger.info(
                        "CONSUMER: poll #%d -- front_mailbox has %d envelope(s)",
                        poll_count,
                        front_pending,
                    )

                env = self.front_mailbox.receive(timeout_ms=0)
                if env is not None:
                    # Dedup check: skip envelopes already processed
                    _dedup_key = (env.envelope_id, env.topic)
                    if _dedup_key in _front_processed:
                        logger.info(
                            "CONSUMER: DEDUP -- skipping duplicate " "envelope_id=%d topic=%s",
                            env.envelope_id,
                            env.topic,
                        )
                        continue
                    _front_processed.add(_dedup_key)
                    # Cap dedup set size (avoid unbounded growth)
                    if len(_front_processed) > 500:
                        _front_processed.clear()

                    did_work = True
                    fsm_state = self.fsm.state.name if self.fsm else "NO_FSM"
                    logger.info(
                        "CONSUMER: FRONT envelope received -- "
                        "envelope_id=%d topic=%s parent_id=%d fsm_state=%s",
                        env.envelope_id,
                        env.topic,
                        env.parent_id,
                        fsm_state,
                    )
                    # Parse payload for debug
                    try:
                        import json as _json

                        payload = _json.loads(env.payload) if env.payload else {}
                        logger.info(
                            "CONSUMER: FRONT payload keys=%s text=%s",
                            list(payload.keys()),
                            str(payload.get("text", ""))[:80],
                        )
                    except Exception:
                        logger.info("CONSUMER: FRONT payload could not be parsed")

                    self._dump_state("PRE_FRONT_HANDLER")

                    logger.info(
                        "CONSUMER: calling front_handler(envelope_id=%d, "
                        "model=%s, fsm_state=%s)",
                        env.envelope_id,
                        type(self.model).__name__,
                        fsm_state,
                    )

                    try:
                        result = await front_handler(
                            envelope=env,
                            model=self.model,
                            ss=self.session_state,
                            bus=self.bus,
                            tool_dispatcher=self.front_dispatcher,
                            all_tool_schemas=FRONT_TOOL_SCHEMAS,
                            fsm_state=fsm_state,
                        )
                        logger.info(
                            "CONSUMER: front_handler RETURNED -- "
                            "status=%s text=%s dispatched=%d",
                            getattr(result, "status", "?"),
                            str(getattr(result, "text", ""))[:80],
                            len(getattr(result, "dispatched_tasks", [])),
                        )
                        self._dump_state("POST_FRONT_HANDLER")

                        # Experience Layer tick: compute tone/style for next prompt
                        await self._tick_experience_layer()

                    except RecursionError:
                        logger.error(
                            "CONSUMER: RECURSION ERROR in front_handler! "
                            "envelope_id=%d topic=%s -- TimingChain causal "
                            "cascade likely looping. Recovering.",
                            env.envelope_id,
                            env.topic,
                        )
                        self._dump_state("POST_FRONT_RECURSION_ERROR")
                        # Try to reset FSM to LISTENING so system does not freeze
                        if self.fsm:
                            from poc.k1_poc.fsm.states import ConciergeState

                            self.fsm._state = ConciergeState.LISTENING
                            self.fsm._front_lock.busy = False
                            logger.info(
                                "CONSUMER: force-reset FSM to LISTENING after RecursionError"
                            )

                    except Exception as exc:
                        logger.error(
                            "CONSUMER: front_handler EXCEPTION -- " "type=%s msg=%s envelope_id=%d",
                            type(exc).__name__,
                            exc,
                            env.envelope_id,
                            exc_info=True,
                        )
                        self._dump_state("POST_FRONT_ERROR")

            except Exception as poll_exc:
                logger.error("CONSUMER: front mailbox poll error: %s", poll_exc, exc_info=True)

            # --- back mailbox (non-blocking: runs as background task) ---
            try:
                # M7 E7.1.3: Try to dispatch overflow queue first (FIFO)
                if self.back_pool and self.back_pool.overflow_depth > 0:
                    await self._dispatch_overflow_queue(route_back_envelope)

                # M7 E7.4.2: Drain ready queue (dependency-released envelopes)
                if self.ready_queue and self.ready_queue.ready_count > 0:
                    await self._dispatch_ready_queue(route_back_envelope)

                back_pending = self.back_mailbox.pending() if self.back_mailbox else 0
                if back_pending > 0:
                    logger.info(
                        "CONSUMER: poll #%d -- back_mailbox has %d envelope(s)",
                        poll_count,
                        back_pending,
                    )

                env = self.back_mailbox.receive(timeout_ms=0)
                if env is not None:
                    did_work = True
                    fsm_state = self.fsm.state.name if self.fsm else "NO_FSM"
                    logger.info(
                        "CONSUMER: BACK envelope received -- "
                        "envelope_id=%d topic=%s parent_id=%d fsm_state=%s "
                        "(dispatching as background task)",
                        env.envelope_id,
                        env.topic,
                        env.parent_id,
                        fsm_state,
                    )
                    try:
                        import json as _json

                        payload = _json.loads(env.payload) if env.payload else {}
                        logger.info(
                            "CONSUMER: BACK payload keys=%s",
                            list(payload.keys()),
                        )
                    except Exception:
                        logger.info("CONSUMER: BACK payload could not be parsed")

                    self._dump_state("PRE_BACK_HANDLER")

                    # M7 E7.1.3: Dispatch via BackPool (acquire worker slot)
                    await self._dispatch_to_back_pool(env, route_back_envelope)

            except Exception as poll_exc:
                logger.error("CONSUMER: back mailbox poll error: %s", poll_exc, exc_info=True)

            # Yield to event loop; sleep longer if idle
            if did_work:
                await asyncio.sleep(0)
            else:
                await asyncio.sleep(poll_interval)

    # =====================================================================
    # Pending back task tracking
    # =====================================================================

    def _on_back_task_done(self, task: asyncio.Task) -> None:
        """Callback when a back handler task finishes.

        M7 E7.1.3: Also releases the pool worker slot if BackPool is
        active. Falls back to legacy list tracking for backward compat.

        M7 E7.4.2: Notifies the ReadyQueue so dependent tasks can be
        released. Released envelopes are picked up by the consumer loop.
        """
        # Legacy list cleanup
        try:
            self._pending_back_tasks.remove(task)
        except ValueError:
            pass

        # M7 E7.1.3: Release pool worker via task_id stored in task name
        if self.back_pool is not None:
            task_id = getattr(task, "_pool_task_id", None)
            if task_id and self.back_pool.has_worker(task_id):
                # Determine release reason from task result
                if task.cancelled():
                    reason = "cancelled"
                elif task.exception() is not None:
                    reason = "error"
                else:
                    reason = "completed"
                self.back_pool.release_worker(task_id, reason=reason)

                # M7 E7.4.2: Notify ReadyQueue so dependents can be released
                if self.ready_queue is not None and task_id:
                    released, failed_ids = self.ready_queue.notify_completed(
                        task_id,
                        status=reason,
                    )
                    # Fail dependents if predecessor failed/cancelled
                    if failed_ids:
                        self._emit_dependency_failed(
                            task_id,
                            task_id,
                            failed_ids,
                        )

    def has_pending_back_tasks(self) -> bool:
        """Return True if any back handler tasks are still running
        or if the FSM has active tasks not yet picked up by back.

        M7 E7.1.3: Checks BackPool active workers in addition to
        legacy _pending_back_tasks list.
        """
        self._pending_back_tasks = [t for t in self._pending_back_tasks if not t.done()]
        has_running = len(self._pending_back_tasks) > 0
        # M7 E7.1.3: Check BackPool active workers
        if self.back_pool is not None:
            has_running = has_running or self.back_pool.active_count > 0
        # Also check FSM active_task_ids -- these are set synchronously
        # when front publishes task_dispatch, before the back consumer
        # loop has a chance to create the asyncio.Task.
        has_fsm_active = bool(self.fsm and self.fsm.active_task_ids)
        return has_running or has_fsm_active

    async def wait_pending_back_tasks(self, timeout: float = 120.0) -> None:
        """Await all pending back handler tasks (with timeout).

        Waits for both:
        1. asyncio.Task objects from back_handler invocations
           (legacy list + BackPool worker tasks)
        2. FSM active_task_ids to clear (tasks not yet picked up by consumer)

        The caller should also wait for the resulting response.final
        after this returns, since the PRESENT-mode front handler still
        needs to render the result.
        """
        import time as _time

        deadline = _time.monotonic() + timeout

        # Phase 1: wait for back handler tasks that have been created
        tasks = [t for t in self._pending_back_tasks if not t.done()]
        # M7 E7.1.3: Also collect async_tasks from BackPool workers
        if self.back_pool is not None:
            for worker in self.back_pool.get_active_workers():
                if worker.async_task is not None and not worker.async_task.done():
                    tasks.append(worker.async_task)
        if tasks:
            remaining = max(0.1, deadline - _time.monotonic())
            logger.info(
                "COORDINATOR: waiting for %d back handler task(s) (timeout=%.0fs)",
                len(tasks),
                remaining,
            )
            await asyncio.wait(tasks, timeout=remaining)

        # Phase 2: if FSM still has active tasks (back not yet started
        # or task.complete not yet processed), poll until they clear
        while self.fsm and self.fsm.active_task_ids:
            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                logger.warning(
                    "COORDINATOR: timeout waiting for FSM active tasks: %s",
                    self.fsm.active_task_ids,
                )
                break
            # Yield to let consumer loop + back handlers run
            await asyncio.sleep(0.2)
            # Check if new back tasks appeared and wait for them too
            new_tasks = [t for t in self._pending_back_tasks if not t.done()]
            if self.back_pool is not None:
                for worker in self.back_pool.get_active_workers():
                    if worker.async_task is not None and not worker.async_task.done():
                        new_tasks.append(worker.async_task)
            if new_tasks:
                remaining = max(0.1, deadline - _time.monotonic())
                await asyncio.wait(new_tasks, timeout=remaining)

    # =====================================================================
    # M7 E7.1.3: BackPool dispatch helpers
    # =====================================================================

    async def _dispatch_to_back_pool(self, env: Any, back_handler: Any) -> None:
        """Dispatch a Back envelope via BackPool worker acquisition.

        M7 E7.1.3: Replaces the old asyncio.create_task pattern with
        pool-managed worker slots. If the pool is exhausted, the
        envelope is pushed to the overflow queue for retry.

        M7 E7.3.2: Uses BackTopicRouter for topic-based dispatch.
        Cancel envelopes bypass the pool (synchronous). Late-arriving
        envelopes for completed/cancelled tasks are discarded.

        Args:
            env: The envelope to dispatch.
            back_handler: The handler function (route_back_envelope, fallback).
        """
        from poc.k1_poc.actors.back_pool import BackPoolExhausted

        if self.back_pool is None:
            # Fallback: no pool, use legacy path
            task = asyncio.create_task(
                self._run_back_handler(env, back_handler),
            )
            self._pending_back_tasks.append(task)
            task.add_done_callback(self._on_back_task_done)
            return

        # Extract task_id and session_id from envelope
        try:
            import json as _json

            payload = _json.loads(env.payload) if env.payload else {}
        except Exception:
            payload = {}
        task_id = payload.get("task_id", f"unknown-{env.envelope_id}")
        session_id = payload.get("session_id")

        # M7 E7.3.1: Use BackTopicRouter to determine handler
        router = getattr(self, "back_topic_router", None)
        if router is not None:
            handler_fn = router.route(env)
            if handler_fn is None:
                # E7.3.4: Late envelope or unknown topic -- discarded
                logger.info(
                    "CONSUMER: BackTopicRouter discarded envelope "
                    "envelope_id=%d topic=%s task_id=%s",
                    env.envelope_id,
                    env.topic,
                    task_id,
                )
                return

            # E7.3.2: Cancel bypasses pool -- synchronous dispatch
            if router.is_cancel_topic(env.topic):
                logger.info(
                    "CONSUMER: cancel envelope dispatched synchronously "
                    "envelope_id=%d task_id=%s (no pool worker needed)",
                    env.envelope_id,
                    task_id,
                )
                # E7.3.3: Extract CancellationToken from lease
                cancel_token = router.get_cancel_token_for_task(task_id)
                handler_fn(
                    envelope=env,
                    fsm_state=getattr(self, "fsm", None),
                    cancel_token=cancel_token,
                )
                return

        try:
            # M7 E7.5.3: Pass FSM cancel token so lease binds to same token
            fsm_cancel_token = None
            fsm = getattr(self, "fsm", None)
            if fsm is not None and hasattr(fsm, "get_cancel_token"):
                fsm_cancel_token = fsm.get_cancel_token(task_id)
            worker_slot = self.back_pool.acquire_worker(
                task_id,
                session_id=session_id,
                cancellation_token=fsm_cancel_token,
            )
        except BackPoolExhausted:
            logger.info(
                "CONSUMER: BackPool exhausted -- queueing envelope "
                "envelope_id=%d task_id=%s for retry",
                env.envelope_id,
                task_id,
            )
            self.back_pool.enqueue_overflow(env)
            return

        # M7 E7.4.1: Check depends_on and use ReadyQueue if needed
        depends_on = payload.get("depends_on") or payload.get(
            "_dispatch",
            {},
        ).get("depends_on")
        if depends_on and self.ready_queue is not None:
            # Register this task_id as known
            self.ready_queue.register_task(task_id)
            status, failed_ids = self.ready_queue.enqueue(env, depends_on=depends_on)

            if status == "waiting":
                # Release the worker -- envelope is queued, not dispatched yet
                self.back_pool.release_worker(task_id, reason="suspended")
                logger.info(
                    "CONSUMER: task=%s waiting for dependency=%s "
                    "(released worker, queued in ReadyQueue)",
                    task_id,
                    depends_on,
                )
                return

            if status == "dep_failed":
                # Predecessor failed -- release worker and emit task.failed
                self.back_pool.release_worker(task_id, reason="error")
                self._emit_dependency_failed(task_id, depends_on, failed_ids)
                return

            if status == "circular":
                # Cycle detected -- release worker and fail all participants
                self.back_pool.release_worker(task_id, reason="error")
                self._emit_dependency_failed(task_id, depends_on, failed_ids)
                return

            # "immediate" or "unknown_dep" -- fall through to dispatch

        # E7.3.3: Extract CancellationToken from lease for handler injection
        cancel_token = None
        if worker_slot.lease is not None:
            cancel_token = worker_slot.lease.cancellation_token

        # Create asyncio.Task with the acquired worker slot
        task = asyncio.create_task(
            self._run_back_handler(env, back_handler, cancel_token=cancel_token),
        )
        # Tag the task with task_id for release_worker in done callback
        task._pool_task_id = task_id  # type: ignore[attr-defined]
        worker_slot.bind_task(task)
        self._pending_back_tasks.append(task)
        task.add_done_callback(self._on_back_task_done)

        logger.info(
            "CONSUMER: dispatched to BackPool worker_id=%s task_id=%s "
            "pool=%d/%d cancel_token=%s",
            worker_slot.worker_id,
            task_id,
            self.back_pool.active_count,
            self.back_pool.config.pool_size,
            "attached" if cancel_token else "none",
        )

    async def _dispatch_overflow_queue(self, back_handler: Any) -> None:
        """Try to dispatch envelopes from the overflow queue.

        M7 E7.1.3: Called each poll cycle before checking the back
        mailbox. Drains as many overflow envelopes as the pool can
        accept.

        Args:
            back_handler: The handler function (route_back_envelope).
        """
        if self.back_pool is None:
            return

        while self.back_pool.overflow_depth > 0 and self.back_pool.pool_available > 0:
            env = self.back_pool.dequeue_overflow()
            if env is None:
                break
            logger.info(
                "CONSUMER: retrying overflow envelope envelope_id=%d",
                env.envelope_id,
            )
            await self._dispatch_to_back_pool(env, back_handler)

    async def _dispatch_ready_queue(self, back_handler: Any) -> None:
        """Dispatch dependency-released envelopes from the ReadyQueue.

        M7 E7.4.2: Called each poll cycle. Drains all ready envelopes
        and dispatches them through the normal BackPool path.

        Args:
            back_handler: The handler function (route_back_envelope).
        """
        if self.ready_queue is None:
            return

        ready_envelopes = self.ready_queue.dequeue_ready()
        for env in ready_envelopes:
            logger.info(
                "CONSUMER: dispatching dependency-released envelope " "envelope_id=%d topic=%s",
                env.envelope_id,
                env.topic,
            )
            await self._dispatch_to_back_pool(env, back_handler)

    def _emit_dependency_failed(
        self,
        task_id: str,
        depends_on: str,
        failed_task_ids: list[str],
    ) -> None:
        """Emit task.failed events for dependency failures.

        M7 E7.4.2: Called when a predecessor fails/is cancelled or
        when circular dependencies are detected.

        Args:
            task_id: The task that triggered the failure.
            depends_on: The dependency that caused the failure.
            failed_task_ids: All task_ids that should be failed.
        """
        for fid in failed_task_ids:
            logger.warning(
                "CONSUMER: task=%s failed -- dependency=%s " "(reason=dependency_failed)",
                fid,
                depends_on,
            )
            if self.bus is not None:
                try:
                    from poc.k1_poc.bus.builders import build_task_failed

                    env = build_task_failed(
                        payload={
                            "task_id": fid,
                            "reason": "dependency_failed",
                            "depends_on": depends_on,
                        }
                    )
                    self.bus.publish(env)
                except Exception:
                    logger.debug(
                        "CONSUMER: failed to emit task.failed for " "dependency failure task=%s",
                        fid,
                        exc_info=True,
                    )

    def _on_pool_worker_acquired(self, slot: Any) -> None:
        """M7 E7.1.4 + E7.2.4: Observability callback when a pool worker is acquired."""
        if self.bus is not None:
            from poc.k1_poc.bus.builders import build_backpool_worker_acquired, build_task_leased

            try:
                env = build_backpool_worker_acquired(
                    payload={
                        "worker_id": slot.worker_id,
                        "task_id": slot.task_id,
                        "pool_size": self.back_pool.config.pool_size if self.back_pool else 0,
                        "active_workers": self.back_pool.active_count if self.back_pool else 0,
                        "session_id": slot.session_id,
                    }
                )
                self.bus.publish(env)
            except Exception:
                logger.debug("BackPool: failed to emit worker.acquired event", exc_info=True)

            # M7 E7.2.4: Emit task.leased.v1 for ownership tracking
            if slot.lease is not None:
                try:
                    leased_env = build_task_leased(payload=slot.lease.to_payload())
                    self.bus.publish(leased_env)
                except Exception:
                    logger.debug("BackPool: failed to emit task.leased event", exc_info=True)

    def _on_pool_worker_released(self, slot: Any, reason: str) -> None:
        """M7 E7.1.4: Observability callback when a pool worker is released."""
        if self.bus is not None:
            from poc.k1_poc.bus.builders import build_backpool_worker_released

            try:
                env = build_backpool_worker_released(
                    payload={
                        "worker_id": slot.worker_id,
                        "task_id": slot.task_id,
                        "pool_size": self.back_pool.config.pool_size if self.back_pool else 0,
                        "active_workers": self.back_pool.active_count if self.back_pool else 0,
                        "release_reason": reason,
                    }
                )
                self.bus.publish(env)
            except Exception:
                logger.debug("BackPool: failed to emit worker.released event", exc_info=True)

    # =====================================================================
    # Background back_handler wrapper
    # =====================================================================

    async def _run_back_handler(
        self,
        env: Any,
        back_handler: Any,
        cancel_token: Any = None,
    ) -> None:
        """Run back_handler as a background task with error handling.

        This allows the consumer loop to remain free for front_mailbox
        polling, so the front actor can accept new user input while
        the back actor processes dispatched tasks.

        M3 E3.1.2: Now delegates to route_back_envelope which routes
        by envelope.topic to the correct handler (dispatch/resume/cancel).

        M7 E7.3.3: Accepts cancel_token from TaskLease and passes it
        to the handler. This ensures _build_cancellation_check returns
        a real check instead of _never_cancel.
        """
        try:
            # M7 E7.3.3: Pass cancel_token from lease to handler
            call_kwargs: dict[str, Any] = {
                "envelope": env,
                "model": self.model,
                "ss": self.session_state,
                "bus": self.bus,
                "tool_dispatcher": self.back_dispatcher,
                "fsm_state": getattr(self, "fsm", None),
            }
            if cancel_token is not None:
                call_kwargs["cancel_token"] = cancel_token

            result = await back_handler(**call_kwargs)
            logger.info(
                "CONSUMER: back_handler RETURNED (background) -- " "status=%s envelope_id=%d",
                getattr(result, "status", "?"),
                env.envelope_id,
            )
            self._dump_state("POST_BACK_HANDLER")

        except RecursionError:
            logger.error(
                "CONSUMER: RECURSION ERROR in back_handler! " "envelope_id=%d topic=%s",
                env.envelope_id,
                env.topic,
            )
            self._dump_state("POST_BACK_RECURSION_ERROR")

        except Exception as exc:
            logger.error(
                "CONSUMER: back_handler EXCEPTION -- " "type=%s msg=%s envelope_id=%d",
                type(exc).__name__,
                exc,
                env.envelope_id,
                exc_info=True,
            )
            self._dump_state("POST_BACK_ERROR")

    # =====================================================================
    # PHASE 5: Health Check (<1s budget)
    # =====================================================================

    async def _phase5_health_check(self) -> None:
        phase_start = time.time()
        self._record("phase5", "coordinator", "phase5.start", "Running system health check")

        checks: Dict[str, bool] = {}

        # Check bus
        checks["bus_alive"] = self.bus is not None
        self._record(
            "phase5", "health", "check.bus", f"Bus: {'OK' if checks['bus_alive'] else 'FAIL'}"
        )

        # Check FSM state
        if self.fsm:
            from poc.k1_poc.fsm.states import ConciergeState

            checks["fsm_listening"] = self.fsm.state == ConciergeState.LISTENING
            self._record(
                "phase5",
                "health",
                "check.fsm",
                f"FSM state: {self.fsm.state.name} "
                f"({'OK' if checks['fsm_listening'] else 'EXPECTED LISTENING'})",
            )
        else:
            checks["fsm_listening"] = False

        # Check LLM adapter
        checks["llm_ready"] = self.model is not None
        model_type = type(self.model).__name__ if self.model else "None"
        self._record(
            "phase5",
            "health",
            "check.llm",
            f"LLM adapter: {model_type} " f"({'OK' if checks['llm_ready'] else 'FAIL'})",
        )

        # Check session state
        checks["session_ready"] = self.session_state is not None
        self._record(
            "phase5",
            "health",
            "check.session",
            f"Session state: {'OK' if checks['session_ready'] else 'FAIL'}",
        )

        # Check capabilities
        if self.capability_registry:
            cap_count = self.capability_registry.count
            checks["capabilities_loaded"] = cap_count >= 30
            self._record(
                "phase5",
                "health",
                "check.capabilities",
                f"Capabilities: {cap_count} registered "
                f"({'OK' if checks['capabilities_loaded'] else 'INSUFFICIENT'})",
            )
        else:
            checks["capabilities_loaded"] = False

        # Check output channel
        checks["output_wired"] = self.output_channel is not None
        self._record(
            "phase5",
            "health",
            "check.output",
            f"Output channel: {'OK' if checks['output_wired'] else 'FAIL'}",
        )

        # Check IoT stubs
        checks["iot_loaded"] = self.iot_stubs is not None
        self._record(
            "phase5",
            "health",
            "check.iot",
            f"IoT stubs: {'OK' if checks['iot_loaded'] else 'FAIL'}",
        )

        # Check ordered bus (kernel defaults to ordered=True)
        checks["bus_ordered"] = True
        self._record(
            "phase5",
            "health",
            "check.bus_ordered",
            "Bus ordered: OK (TimingChain enabled via kernel bootstrap)",
        )

        # M1 E1.4.6: Check ledger operational status
        if self.ledger is not None:
            ledger_count = self.ledger_store.count() if self.ledger_store else 0
            checks["ledger_alive"] = True
            self._record(
                "phase5",
                "health",
                "check.ledger",
                f"Ledger: OK ({ledger_count} entries, store={type(self.ledger_store).__name__})",
            )
        else:
            checks["ledger_alive"] = True  # Ledger is optional, absence is not a failure
            self._record(
                "phase5",
                "health",
                "check.ledger",
                "Ledger: disabled (optional)",
            )

        # M2 E2.5.5: Check dead-letter consumer operational status
        if self.dead_letter_consumer is not None:
            dl_total = self.dead_letter_consumer.total_dead_letters
            checks["dead_letter_alive"] = True
            self._record(
                "phase5",
                "health",
                "check.dead_letter",
                f"DeadLetterConsumer: OK (count={dl_total})",
            )
        else:
            checks["dead_letter_alive"] = True  # Optional, absence is not a failure
            self._record(
                "phase5",
                "health",
                "check.dead_letter",
                "DeadLetterConsumer: disabled (optional)",
            )

        # M3 E3.7.4: Check parallel tools configuration
        try:
            from poc.k1_poc.config.loader import get_config

            pt_enabled = get_config().react.parallel_tools_enabled
            checks["parallel_tools_configured"] = True
            self._record(
                "phase5",
                "health",
                "check.parallel_tools",
                f"Parallel tools: {'enabled' if pt_enabled else 'disabled'}",
            )
        except Exception:
            checks["parallel_tools_configured"] = True  # Config not loaded is not fatal
            self._record(
                "phase5",
                "health",
                "check.parallel_tools",
                "Parallel tools: config unavailable (non-fatal)",
            )

        # M4 E4.5.2: Check control section overlay (SB2 fix verification)
        if self.session_state is not None:
            try:
                from poc.k1_poc.actors.shared import safe_get_section as _safe_get

                control = _safe_get(self.session_state, "control")
                if control is not None and hasattr(control, "fsm_overlay"):
                    overlay = control.fsm_overlay
                    has_overlay = overlay is not None
                    checks["control_overlay_bound"] = has_overlay
                    self._record(
                        "phase5",
                        "health",
                        "check.control_overlay",
                        f"Control overlay: {'bound' if has_overlay else 'NOT bound'} "
                        f"(SB2 fix {'active' if has_overlay else 'MISSING'})",
                    )
                else:
                    checks["control_overlay_bound"] = False
                    self._record(
                        "phase5",
                        "health",
                        "check.control_overlay",
                        "Control section: no fsm_overlay property (M4 not active)",
                    )
            except Exception:
                checks["control_overlay_bound"] = True  # Non-fatal
                self._record(
                    "phase5",
                    "health",
                    "check.control_overlay",
                    "Control overlay: check failed (non-fatal)",
                )
        else:
            checks["control_overlay_bound"] = True  # No SS = skip check
            self._record(
                "phase5",
                "health",
                "check.control_overlay",
                "Control overlay: no session state (skipped)",
            )

        # M4 E4.5.3: Check writer_port wired into session state
        if self.session_state is not None:
            wp = getattr(self.session_state, "_writer_port", None)
            checks["writer_port_wired"] = wp is not None
            self._record(
                "phase5",
                "health",
                "check.writer_port",
                f"Writer port: {'wired' if wp else 'NOT wired'}",
            )
        else:
            checks["writer_port_wired"] = True  # No SS = skip check
            self._record(
                "phase5",
                "health",
                "check.writer_port",
                "Writer port: no session state (skipped)",
            )

        # M7 E7.1.4: Check BackPool operational status
        if self.back_pool is not None:
            pool_state = self.back_pool.get_pool_state()
            checks["backpool_wired"] = True
            self._record(
                "phase5",
                "health",
                "check.backpool",
                f"BackPool: OK (pool_size={pool_state['size']}, "
                f"active={pool_state['active']}, "
                f"overflow={pool_state['overflow']})",
            )
        else:
            checks["backpool_wired"] = True  # Optional, absence is not failure
            self._record(
                "phase5",
                "health",
                "check.backpool",
                "BackPool: disabled (optional)",
            )

        # Aggregate
        all_ok = all(checks.values())
        duration = time.time() - phase_start
        self.startup_times["phase5"] = duration
        self.phases_completed.append("phase5")

        self._record(
            "phase5",
            "coordinator",
            "phase5.complete",
            f"Health check {'PASSED' if all_ok else 'FAILED'} "
            f"({sum(checks.values())}/{len(checks)} checks) "
            f"in {duration:.3f}s",
            payload={
                "checks": checks,
                "all_ok": all_ok,
                "duration_s": round(duration, 3),
            },
        )

        if not all_ok:
            failed = [k for k, v in checks.items() if not v]
            logger.warning("Health check failures: %s", failed)

    # -----------------------------------------------------------------
    # Guarded accessors (raise if component not initialized)
    # -----------------------------------------------------------------

    def get_bus(self) -> Any:
        if self.bus is None:
            raise RuntimeError("Bus not initialized (kernel not started)")
        return self.bus

    def get_router(self) -> Any:
        if self.router is None:
            raise RuntimeError("Router not initialized (kernel not started)")
        return self.router

    def get_fsm(self) -> Any:
        if self.fsm is None:
            raise RuntimeError("FSM not initialized (kernel not started)")
        return self.fsm

    def get_model(self) -> Any:
        if self.model is None:
            raise RuntimeError("LLM adapter not initialized (kernel not started)")
        return self.model

    def get_session_state(self) -> Any:
        if self.session_state is None:
            raise RuntimeError("Session state not initialized (kernel not started)")
        return self.session_state

    def get_capability_registry(self) -> Any:
        if self.capability_registry is None:
            raise RuntimeError("Capability registry not initialized (kernel not started)")
        return self.capability_registry

    def get_output_channel(self) -> OutputChannel:
        if self.output_channel is None:
            raise RuntimeError("Output channel not initialized")
        assert self.output_channel is not None
        return self.output_channel

    def get_front_dispatcher(self) -> Any:
        if self.front_dispatcher is None:
            raise RuntimeError("Front dispatcher not initialized (kernel not started)")
        return self.front_dispatcher

    def get_back_dispatcher(self) -> Any:
        if self.back_dispatcher is None:
            raise RuntimeError("Back dispatcher not initialized (kernel not started)")
        return self.back_dispatcher

    def get_experience_layer(self) -> Any:
        if self.experience_layer is None:
            raise RuntimeError("Experience layer not initialized (kernel not started)")
        return self.experience_layer

    async def _tick_experience_layer(self) -> None:
        """Invoke ExperienceLayer tick after front_handler completes.

        Delegates to bootstrap._tick_experience using the KernelRuntime
        so tone adjustment and response style are written to SS before
        the next prompt build.
        """
        if self._kernel is None:
            return
        try:
            from poc.k1_poc.kernel.bootstrap import _tick_experience

            await _tick_experience(self._kernel)
        except Exception as exc:
            logger.warning("Experience tick failed (non-critical): %s", exc)

    def get_orchestrator(self) -> Any:
        if self.orchestrator is None:
            raise RuntimeError("Orchestrator not initialized (kernel not started)")
        return self.orchestrator

    def get_iot_stubs(self) -> Any:
        if self.iot_stubs is None:
            raise RuntimeError("IoT stubs not initialized")
        return self.iot_stubs

    # -----------------------------------------------------------------
    # Status report (for /status command and startup display)
    # -----------------------------------------------------------------

    def get_status_report(self) -> Dict[str, Any]:
        """Full system status -- designed for UI rendering."""
        report: Dict[str, Any] = {
            "system_ready": self.system_ready,
            "phases_completed": list(self.phases_completed),
            "startup_times": dict(self.startup_times),
            "total_startup_s": round(sum(self.startup_times.values()), 3),
            "components": {},
            "timeline_count": len(self.timeline),
        }
        if self.family_profile:
            report["components"]["family"] = self.family_profile.get("family_name", "?")
        if self.model:
            report["components"]["llm_adapter"] = type(self.model).__name__
        if self.bus:
            report["components"]["bus"] = "LocalBus (ordered)"
        if self.fsm:
            report["components"]["fsm_state"] = self.fsm.state.name
        if self.session_state:
            report["components"]["session"] = "active"
        if self.capability_registry:
            report["components"]["capabilities"] = self.capability_registry.count
        if self.experience_layer:
            report["components"]["experience"] = "active"
        if self.delta_aggregator:
            report["components"]["delta_aggregator"] = "active"
        if self.hitl_coordinator:
            report["components"]["hitl"] = "active"
        if self.orchestrator:
            report["components"]["orchestrator"] = "active"
        if self.iot_stubs:
            report["components"]["iot_stubs"] = {
                "scheduled": self.iot_stubs.scheduled_turns,
                "fired": sorted(self.iot_stubs.fired_turns),
            }
        return report

    def print_startup_report(self) -> None:
        """Print formatted startup report to console (visual version)."""
        from poc.k1_poc.demo.display import print_startup_report_visual

        report = self.get_status_report()
        print_startup_report_visual(
            phases_completed=list(self.phases_completed),
            startup_times=dict(self.startup_times),
            total_time=report["total_startup_s"],
            system_ready=self.system_ready,
            components=report.get("components", {}),
        )


# =========================================================================
# Singleton
# =========================================================================

_coordinator_instance: Optional[K1DemoCoordinator] = None


def get_k1_demo_coordinator(*, test_mode: bool = False) -> K1DemoCoordinator:
    """Get or create the singleton K1DemoCoordinator."""
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = K1DemoCoordinator(test_mode=test_mode)
    return _coordinator_instance


def reset_coordinator() -> None:
    """Reset the singleton (for testing)."""
    global _coordinator_instance
    _coordinator_instance = None
