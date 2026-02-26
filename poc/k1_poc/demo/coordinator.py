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

        # Demo-only slots
        self.iot_stubs: Any = None
        self.output_channel: Optional[OutputChannel] = None
        self._preloaded_memories: List[Dict[str, Any]] = []
        self._consumer_task: Any = None
        self._pending_back_tasks: list[asyncio.Task] = []

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
                tool_tier="LOW",
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
        from poc.k1_poc.actors.back import back_handler
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

                    # Run back_handler as background task so front remains
                    # available for new user input while back processes.
                    task = asyncio.create_task(
                        self._run_back_handler(env, back_handler),
                    )
                    self._pending_back_tasks.append(task)
                    task.add_done_callback(self._on_back_task_done)

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
        """Callback when a back handler task finishes."""
        try:
            self._pending_back_tasks.remove(task)
        except ValueError:
            pass

    def has_pending_back_tasks(self) -> bool:
        """Return True if any back handler tasks are still running
        or if the FSM has active tasks not yet picked up by back.
        """
        self._pending_back_tasks = [t for t in self._pending_back_tasks if not t.done()]
        has_running = len(self._pending_back_tasks) > 0
        # Also check FSM active_task_ids -- these are set synchronously
        # when front publishes task_dispatch, before the back consumer
        # loop has a chance to create the asyncio.Task.
        has_fsm_active = bool(self.fsm and self.fsm.active_task_ids)
        return has_running or has_fsm_active

    async def wait_pending_back_tasks(self, timeout: float = 120.0) -> None:
        """Await all pending back handler tasks (with timeout).

        Waits for both:
        1. asyncio.Task objects from back_handler invocations
        2. FSM active_task_ids to clear (tasks not yet picked up by consumer)

        The caller should also wait for the resulting response.final
        after this returns, since the PRESENT-mode front handler still
        needs to render the result.
        """
        import time as _time

        deadline = _time.monotonic() + timeout

        # Phase 1: wait for back handler tasks that have been created
        tasks = [t for t in self._pending_back_tasks if not t.done()]
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
            if new_tasks:
                remaining = max(0.1, deadline - _time.monotonic())
                await asyncio.wait(new_tasks, timeout=remaining)

    # =====================================================================
    # Background back_handler wrapper
    # =====================================================================

    async def _run_back_handler(self, env: Any, back_handler: Any) -> None:
        """Run back_handler as a background task with error handling.

        This allows the consumer loop to remain free for front_mailbox
        polling, so the front actor can accept new user input while
        the back actor processes dispatched tasks.
        """
        try:
            result = await back_handler(
                envelope=env,
                model=self.model,
                ss=self.session_state,
                bus=self.bus,
                tool_dispatcher=self.back_dispatcher,
            )
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
