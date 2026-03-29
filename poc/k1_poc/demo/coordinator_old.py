"""
poc.k1_poc.demo.coordinator -- 6-phase K1 demo bootstrap.

Modeled after chat_experience_poc/system_coordinator.py but adapted
for the K1 bus-driven, fully in-process architecture.

Every phase emits structured timeline entries so that UI teams can
render a live internal-components view showing exactly what each
subsystem is doing, when, and how long it takes.

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
import os
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
    payload: Dict[str, Any] | None = None,
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
    Centralized K1 demo startup and shutdown coordinator.

    6-phase initialization order:
        1. Config & LLM adapter
        2. Bus infrastructure (reuses existing boot())
        3. Session State & Capability Registry
        4. FSM Controller & Actor wiring
        5. Support systems (Experience, Delta, HITL, Orchestrator, IoT)
        6. Health check & startup report

    All internal activity is recorded in a timeline log that UI teams
    can consume to visualize the system as it boots and runs.
    """

    def __init__(self, *, test_mode: bool = False) -> None:
        self._test_mode = test_mode
        self._boot_time_ns = time.monotonic_ns()
        self.system_ready = False

        # Phase tracking (SystemCoordinator pattern)
        self.phases_completed: List[str] = []
        self.startup_times: Dict[str, float] = {}

        # Timeline log -- every notable internal event
        self._timeline: List[TimelineEntry] = []

        # Component slots (populated by phases)
        self.family_profile: Dict[str, Any] = {}
        self.session_config: Dict[str, Any] = {}
        self.device_registry: Dict[str, Any] = {}
        self.model: Any = None  # IConciergeModelPort
        self.prompt_builder: Any = None  # DynamicPromptBuilder
        self.bus: Any = None  # IBus
        self.router: Any = None  # IMailboxRouter
        self.adapter: Any = None  # SessionBusAdapter
        self.front_mailbox: Any = None
        self.back_mailbox: Any = None
        self.session_state: Any = None  # SessionStateManager
        self.capability_registry: Any = None  # CapabilityRegistry
        self.fsm: Any = None  # ConciergeController
        self.front_dispatcher: Any = None  # ToolDispatcher
        self.back_dispatcher: Any = None  # ToolDispatcher
        self.experience_layer: Any = None
        self.delta_aggregator: Any = None
        self.hitl_coordinator: Any = None
        self.orchestrator: Any = None
        self.iot_stubs: Any = None
        self.output_channel: Optional[OutputChannel] = None
        self._preloaded_memories: List[Dict[str, Any]] = []
        self._consumer_task: Any = None  # asyncio.Task for mailbox consumer

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
        """Run all 6 phases.  Returns True on success."""
        logger.info("=" * 70)
        logger.info("INIT: Starting K1 Demo Coordinator initialization")
        logger.info("=" * 70)
        self._record("boot", "coordinator", "system.init.start", "K1 Demo Coordinator initializing")
        try:
            logger.info("INIT: Phase 1 -- Config & LLM")
            await self._phase1_config_and_llm()
            logger.info("INIT: Phase 1 DONE")

            logger.info("INIT: Phase 2 -- Bus Infrastructure")
            await self._phase2_bus_infrastructure()
            logger.info("INIT: Phase 2 DONE")

            logger.info("INIT: Phase 3 -- Session & Capabilities")
            await self._phase3_session_and_capabilities()
            logger.info("INIT: Phase 3 DONE")

            logger.info("INIT: Phase 4 -- FSM & Actor Wiring")
            await self._phase4_fsm_and_actors()
            logger.info("INIT: Phase 4 DONE")

            logger.info("INIT: Starting mailbox consumer loop")
            self._start_consumer_loop()
            logger.info("INIT: Consumer loop started")

            logger.info("INIT: Phase 5 -- Support Systems")
            await self._phase5_support_systems()
            logger.info("INIT: Phase 5 DONE")

            logger.info("INIT: Phase 6 -- Health Check")
            await self._phase6_health_check()
            logger.info("INIT: Phase 6 DONE")

            self.system_ready = True
            self._record(
                "boot",
                "coordinator",
                "system.init.complete",
                f"All 6 phases complete in " f"{sum(self.startup_times.values()):.3f}s",
            )
            logger.info("=" * 70)
            logger.info("INIT: ALL 6 PHASES COMPLETE -- system_ready=True")
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

        # Cancel mailbox consumer task
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._record(
                "shutdown", "consumer", "consumer.stopped", "Mailbox consumer loop cancelled"
            )

        # Phase 5 teardown: IoT, delta, experience
        if self.iot_stubs:
            self.iot_stubs.reset()
            self._record("shutdown", "iot", "iot.reset", "IoT stubs reset")

        if self.delta_aggregator:
            try:
                await self.delta_aggregator.flush()
                self._record("shutdown", "delta", "delta.flush", "Final delta flush")
            except Exception:
                pass

        # Phase 4 teardown: FSM, output channel
        if self.output_channel:
            self.output_channel.teardown()
            self._record("shutdown", "output", "output.teardown", "Output channel unsubscribed")

        if self.fsm:
            self.fsm.teardown()
            self._record("shutdown", "fsm", "fsm.teardown", "FSM unsubscribed and reset")

        # Phase 3 teardown: session state
        if self.session_state:
            try:
                await self.session_state.close()
            except Exception:
                pass
            self._record("shutdown", "session", "session.close", "Session state closed")

        # Phase 1 teardown: LLM adapter
        if hasattr(self.model, "close"):
            try:
                await self.model.close()
            except Exception:
                pass
            self._record("shutdown", "llm", "llm.close", "LLM adapter closed")

        self.system_ready = False
        duration = time.time() - shutdown_start
        self._record(
            "shutdown",
            "coordinator",
            "system.shutdown.complete",
            f"Shutdown complete in {duration:.3f}s",
        )

    # =====================================================================
    # PHASE 1: Config & LLM (<2s budget)
    # =====================================================================

    async def _phase1_config_and_llm(self) -> None:
        phase_start = time.time()
        self._record("phase1", "coordinator", "phase1.start", "Loading config and LLM adapter")

        try:
            # 1a. Load family profile
            from poc.k1_poc.demo.smith_family import (
                DEVICE_REGISTRY,
                PRELOADED_MEMORIES,
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
                f"({len(self.family_profile['members'])} members)",
                payload={
                    "family": self.family_profile["family_name"],
                    "members": len(self.family_profile["members"]),
                },
            )

            # 1b. Init LLM adapter
            if self._test_mode:
                from poc.k1_poc.llm.test_adapter import TestConciergeAdapter

                self.model = TestConciergeAdapter()
                adapter_name = "TestConciergeAdapter"
                self._record(
                    "phase1",
                    "llm",
                    "llm.test_adapter",
                    "Using test adapter (deterministic responses)",
                )
            else:
                api_key = os.getenv("GOOGLE_API_KEY")
                if api_key:
                    from poc.k1_poc.llm.gemini_adapter import GeminiConciergeAdapter

                    self.model = GeminiConciergeAdapter(api_key=api_key)
                    adapter_name = "GeminiConciergeAdapter"
                    self._record(
                        "phase1",
                        "llm",
                        "llm.gemini_adapter",
                        "Using Gemini adapter (GOOGLE_API_KEY found)",
                    )
                else:
                    from poc.k1_poc.llm.test_adapter import TestConciergeAdapter

                    self.model = TestConciergeAdapter()
                    adapter_name = "TestConciergeAdapter"
                    self._record(
                        "phase1",
                        "llm",
                        "llm.fallback_test",
                        "No GOOGLE_API_KEY -- falling back to test adapter",
                    )

            # 1c. Prompt builder (stateless, zero-dep)
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
            budget_ok = duration < 2.0
            self._record(
                "phase1",
                "coordinator",
                "phase1.complete",
                f"Phase 1 complete in {duration:.3f}s "
                f"({'within budget' if budget_ok else 'BUDGET EXCEEDED'})",
                payload={
                    "duration_s": round(duration, 3),
                    "budget_s": 2.0,
                    "adapter": adapter_name,
                    "budget_ok": budget_ok,
                },
            )

        except Exception as exc:
            self._record("phase1", "coordinator", "phase1.failed", f"Phase 1 FAILED: {exc}")
            raise

    # =====================================================================
    # PHASE 2: Bus Infrastructure (<1s budget)
    # =====================================================================

    async def _phase2_bus_infrastructure(self) -> None:
        phase_start = time.time()
        self._record("phase2", "coordinator", "phase2.start", "Initializing bus infrastructure")

        try:
            from poc.k1_poc.main import boot

            infra = boot(ordered=False)
            self.bus = infra["bus"]
            self.router = infra["router"]
            self.adapter = infra["adapter"]
            self.front_mailbox = infra["front_mailbox"]
            self.back_mailbox = infra["back_mailbox"]

            self._record(
                "phase2",
                "bus",
                "bus.created",
                "LocalBus created (UNORDERED -- no TimingChain)",
                payload={"capture": False, "ordered": False},
            )
            self._record("phase2", "bus", "router.created", "LocalMailboxRouter created")
            self._record("phase2", "bus", "adapter.created", "SessionBusAdapter wired to bus")
            self._record(
                "phase2",
                "bus",
                "mailboxes.registered",
                "front_half and back_half mailboxes registered",
                payload={
                    "actors": ["front_half", "back_half"],
                    "capacity": 64,
                    "priority_wfq": True,
                },
            )

            # Phase complete
            duration = time.time() - phase_start
            self.startup_times["phase2"] = duration
            self.phases_completed.append("phase2")
            budget_ok = duration < 1.0
            self._record(
                "phase2",
                "coordinator",
                "phase2.complete",
                f"Phase 2 complete in {duration:.3f}s "
                f"({'within budget' if budget_ok else 'BUDGET EXCEEDED'})",
                payload={"duration_s": round(duration, 3), "budget_s": 1.0, "budget_ok": budget_ok},
            )

        except Exception as exc:
            self._record("phase2", "coordinator", "phase2.failed", f"Phase 2 FAILED: {exc}")
            raise

    # =====================================================================
    # PHASE 3: Session State & Capabilities (<3s budget)
    # =====================================================================

    async def _phase3_session_and_capabilities(self) -> None:
        phase_start = time.time()
        self._record(
            "phase3", "coordinator", "phase3.start", "Initializing session state and capabilities"
        )

        try:
            # 3a. Session State
            from poc.k1_poc.sessionstate.factory import SessionStateFactory

            session_id = f"demo-{uuid.uuid4().hex[:8]}"
            self.session_state = SessionStateFactory.create_for_testing(
                session_id=session_id,
            )
            self._record(
                "phase3",
                "session",
                "session.created",
                f"SessionStateManager created (id={session_id})",
                payload={"session_id": session_id, "mode": "testing"},
            )

            # 3b. Initialize persona with Smith family profile
            try:
                persona_section = self.session_state.get_section("persona")
                if persona_section is not None:
                    persona_section.update(
                        {
                            "family": self.family_profile,
                            "session": self.session_config,
                            "active_member": "Alex",
                        }
                    )
                    self._record(
                        "phase3",
                        "session",
                        "persona.initialized",
                        f"Persona loaded: {self.family_profile['family_name']} family",
                        payload={"family": self.family_profile["family_name"]},
                    )
            except Exception as persona_err:
                self._record(
                    "phase3", "session", "persona.skipped", f"Persona init skipped: {persona_err}"
                )

            # 3c. Preload K0 memories into session state
            try:
                beliefs_section = self.session_state.get_section("beliefs")
                if beliefs_section is not None:
                    for mem in self._preloaded_memories:
                        beliefs_section.update(
                            {
                                "preloaded_memories": self._preloaded_memories,
                            }
                        )
                    self._record(
                        "phase3",
                        "session",
                        "memories.preloaded",
                        f"Preloaded {len(self._preloaded_memories)} K0 memories",
                        payload={"count": len(self._preloaded_memories)},
                    )
            except Exception as mem_err:
                self._record(
                    "phase3", "session", "memories.skipped", f"Memory preload skipped: {mem_err}"
                )

            # 3d. Capability Registry (7 demo + 8 storyline)
            from poc.k1_poc.fabric.capability_registry import create_demo_registry

            self.capability_registry = create_demo_registry()
            demo_count = self.capability_registry.count
            self._record(
                "phase3",
                "fabric",
                "capabilities.demo_registered",
                f"Registered {demo_count} demo capabilities",
                payload={"count": demo_count},
            )

            # 3e. Register storyline-specific capabilities
            from poc.k1_poc.demo.iot_stubs import register_storyline_capabilities

            story_count = register_storyline_capabilities(self.capability_registry)
            total = self.capability_registry.count
            self._record(
                "phase3",
                "fabric",
                "capabilities.storyline_registered",
                f"Registered {story_count} storyline capabilities " f"(total={total})",
                payload={"storyline_count": story_count, "total": total},
            )

            # Phase complete
            duration = time.time() - phase_start
            self.startup_times["phase3"] = duration
            self.phases_completed.append("phase3")
            budget_ok = duration < 3.0
            self._record(
                "phase3",
                "coordinator",
                "phase3.complete",
                f"Phase 3 complete in {duration:.3f}s "
                f"({'within budget' if budget_ok else 'BUDGET EXCEEDED'})",
                payload={"duration_s": round(duration, 3), "budget_s": 3.0, "budget_ok": budget_ok},
            )

        except Exception as exc:
            self._record("phase3", "coordinator", "phase3.failed", f"Phase 3 FAILED: {exc}")
            raise

    # =====================================================================
    # PHASE 4: FSM Controller & Actor Wiring (<1s budget)
    # =====================================================================

    async def _phase4_fsm_and_actors(self) -> None:
        phase_start = time.time()
        self._record(
            "phase4", "coordinator", "phase4.start", "Wiring FSM controller and actor handlers"
        )

        try:
            # 4a. ConciergeController -- auto-subscribes to 18 bus topics
            from poc.k1_poc.fsm.controller import ConciergeController

            self.fsm = ConciergeController(bus=self.bus, router=self.router)
            self._record(
                "phase4",
                "fsm",
                "fsm.created",
                f"ConciergeController created (state={self.fsm.state.name})",
                payload={"initial_state": self.fsm.state.name, "subscriptions": 18},
            )

            # 4b. ToolContext for both dispatchers
            from poc.k1_poc.tools.implementations import ToolContext

            front_ctx = ToolContext(
                session_manager=self.session_state,
                cognitive_trace_id=f"demo-front-{uuid.uuid4().hex[:6]}",
                actor="front",
                recall_fn=self._recall_memory_stub,
                capability_fn=self._capability_discover,
                invoke_fn=self._capability_invoke,
            )
            back_ctx = ToolContext(
                session_manager=self.session_state,
                cognitive_trace_id=f"demo-back-{uuid.uuid4().hex[:6]}",
                actor="back",
                recall_fn=self._recall_memory_stub,
                capability_fn=self._capability_discover,
                invoke_fn=self._capability_invoke,
            )
            self._record(
                "phase4",
                "tools",
                "tool_context.created",
                "Front + Back ToolContexts created with capability wiring",
            )

            # 4c. ToolDispatchers
            from poc.k1_poc.tools.dispatcher import create_back_dispatcher, create_front_dispatcher

            self.front_dispatcher = create_front_dispatcher(tier="LOW", ctx=front_ctx)
            self.back_dispatcher = create_back_dispatcher(tier="LOW", ctx=back_ctx)
            self._record(
                "phase4",
                "tools",
                "dispatchers.created",
                "Front + Back ToolDispatchers created (tier=LOW)",
                payload={
                    "front_budget": self.front_dispatcher.budget_remaining,
                    "back_budget": self.back_dispatcher.budget_remaining,
                },
            )

            # 4d. Output channel (subscribes to response/state topics)
            self.output_channel = OutputChannel(
                bus=self.bus,
                current_member="Alex",
            )
            self.output_channel.subscribe_all()
            self._record(
                "phase4",
                "output",
                "output_channel.subscribed",
                "OutputChannel subscribed to 17 bus topics",
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
                payload={"duration_s": round(duration, 3), "budget_s": 1.0, "budget_ok": budget_ok},
            )

        except Exception as exc:
            self._record("phase4", "coordinator", "phase4.failed", f"Phase 4 FAILED: {exc}")
            raise

    # =====================================================================
    # Mailbox consumer loop (connects FSM -> front/back handlers)
    # =====================================================================

    def _start_consumer_loop(self) -> None:
        """Start a background asyncio task that polls both actor mailboxes
        and invokes front_handler / back_handler when envelopes arrive.

        Without this, the FSM pushes envelopes into the mailboxes but
        nobody drains them, so the handlers never run and no response is
        ever published.
        """
        self._consumer_task = asyncio.ensure_future(self._mailbox_consumer())
        self._record(
            "phase4", "consumer", "consumer.started", "Mailbox consumer loop started (front + back)"
        )

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
                        # Try to reset FSM to LISTENING so system doesn't freeze
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

            # --- back mailbox ---
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
                        "envelope_id=%d topic=%s parent_id=%d fsm_state=%s",
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

                    try:
                        result = await back_handler(
                            envelope=env,
                            model=self.model,
                            ss=self.session_state,
                            bus=self.bus,
                            tool_dispatcher=self.back_dispatcher,
                        )
                        logger.info(
                            "CONSUMER: back_handler RETURNED -- " "status=%s envelope_id=%d",
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

            except Exception as poll_exc:
                logger.error("CONSUMER: back mailbox poll error: %s", poll_exc, exc_info=True)

            # Yield to event loop; sleep longer if idle
            if did_work:
                await asyncio.sleep(0)
            else:
                await asyncio.sleep(poll_interval)

    # =====================================================================
    # PHASE 5: Support Systems (<1s budget)
    # =====================================================================

    async def _phase5_support_systems(self) -> None:
        phase_start = time.time()
        self._record("phase5", "coordinator", "phase5.start", "Initializing support systems")

        try:
            # 5a. Experience Layer (zero-dep)
            from poc.k1_poc.experience.layer import ExperienceLayer

            self.experience_layer = ExperienceLayer()
            self._record(
                "phase5",
                "experience",
                "experience.created",
                "ExperienceLayer created (6 sub-components)",
            )

            # 5b. DeltaAggregator
            from poc.k1_poc.delta.aggregator import DeltaAggregator

            async def _delta_flush(batch: Any) -> None:
                self._record(
                    "runtime",
                    "delta",
                    "delta.flushed",
                    f"Delta batch flushed ({len(batch.deltas)} deltas)",
                    payload={"batch_id": batch.batch_id, "delta_count": len(batch.deltas)},
                )

            self.delta_aggregator = DeltaAggregator(
                flush_fn=_delta_flush,
                batch_window_ms=500,
            )
            self._record(
                "phase5",
                "delta",
                "delta_aggregator.created",
                "DeltaAggregator created (500ms batch window)",
            )

            # 5c. HITL Coordinator
            from poc.k1_poc.protocols.hitl_coordinator import HILCoordinator

            async def _on_suspended(request: Any) -> None:
                self._record(
                    "runtime",
                    "hitl",
                    "hitl.suspended",
                    f"Task suspended for HITL: {request.task_id}",
                    payload={"task_id": request.task_id, "hil_type": request.hil_type},
                )

            async def _on_resume(response: Any) -> None:
                self._record(
                    "runtime",
                    "hitl",
                    "hitl.resumed",
                    f"HITL resolved: {response.task_id}",
                    payload={"task_id": response.task_id},
                )

            self.hitl_coordinator = HILCoordinator(
                on_emit_suspended=_on_suspended,
                on_emit_resume=_on_resume,
            )
            self._record(
                "phase5", "hitl", "hitl.created", "HILCoordinator created with bus callbacks"
            )

            # 5d. Orchestrator stub
            try:
                from poc.k1_poc.orchestrator.stub import OrchestratorStub

                # Create lightweight port adapters
                fabric_gw = _FabricGatewayAdapter(self.capability_registry)
                state_read = _StateReadAdapter(self.session_state)
                delta_emit = _DeltaEmitAdapter(self.bus, self._record)

                self.orchestrator = OrchestratorStub(
                    fabric_gateway=fabric_gw,
                    state_read=state_read,
                    delta_emit=delta_emit,
                )
                self._record(
                    "phase5",
                    "orchestrator",
                    "orchestrator.created",
                    "OrchestratorStub created with 3 port adapters",
                )
            except Exception as orch_err:
                self._record(
                    "phase5",
                    "orchestrator",
                    "orchestrator.skipped",
                    f"Orchestrator init skipped: {orch_err}",
                )

            # 5e. IoT monitor stubs
            from poc.k1_poc.demo.iot_stubs import IoTMonitorStub

            self.iot_stubs = IoTMonitorStub(bus=self.bus)
            self._record(
                "phase5",
                "iot",
                "iot_stubs.created",
                f"IoT stubs loaded ({len(self.iot_stubs.scheduled_turns)} "
                f"scripted turns: {self.iot_stubs.scheduled_turns})",
                payload={"turns": self.iot_stubs.scheduled_turns},
            )

            # Phase complete
            duration = time.time() - phase_start
            self.startup_times["phase5"] = duration
            self.phases_completed.append("phase5")
            budget_ok = duration < 1.0
            self._record(
                "phase5",
                "coordinator",
                "phase5.complete",
                f"Phase 5 complete in {duration:.3f}s "
                f"({'within budget' if budget_ok else 'BUDGET EXCEEDED'})",
                payload={"duration_s": round(duration, 3), "budget_s": 1.0, "budget_ok": budget_ok},
            )

        except Exception as exc:
            self._record("phase5", "coordinator", "phase5.failed", f"Phase 5 FAILED: {exc}")
            raise

    # =====================================================================
    # PHASE 6: Health Check (<1s budget)
    # =====================================================================

    async def _phase6_health_check(self) -> None:
        phase_start = time.time()
        self._record("phase6", "coordinator", "phase6.start", "Running system health check")

        checks: Dict[str, bool] = {}

        # Check bus
        checks["bus_alive"] = self.bus is not None
        self._record(
            "phase6", "health", "check.bus", f"Bus: {'OK' if checks['bus_alive'] else 'FAIL'}"
        )

        # Check FSM state
        if self.fsm:
            from poc.k1_poc.fsm.states import ConciergeState

            checks["fsm_listening"] = self.fsm.state == ConciergeState.LISTENING
            self._record(
                "phase6",
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
            "phase6",
            "health",
            "check.llm",
            f"LLM adapter: {model_type} " f"({'OK' if checks['llm_ready'] else 'FAIL'})",
        )

        # Check session state
        checks["session_ready"] = self.session_state is not None
        self._record(
            "phase6",
            "health",
            "check.session",
            f"Session state: {'OK' if checks['session_ready'] else 'FAIL'}",
        )

        # Check capabilities
        if self.capability_registry:
            cap_count = self.capability_registry.count
            checks["capabilities_loaded"] = cap_count >= 7
            self._record(
                "phase6",
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
            "phase6",
            "health",
            "check.output",
            f"Output channel: {'OK' if checks['output_wired'] else 'FAIL'}",
        )

        # Check IoT stubs
        checks["iot_loaded"] = self.iot_stubs is not None
        self._record(
            "phase6",
            "health",
            "check.iot",
            f"IoT stubs: {'OK' if checks['iot_loaded'] else 'FAIL'}",
        )

        # Aggregate
        all_ok = all(checks.values())
        duration = time.time() - phase_start
        self.startup_times["phase6"] = duration
        self.phases_completed.append("phase6")

        self._record(
            "phase6",
            "coordinator",
            "phase6.complete",
            f"Health check {'PASSED' if all_ok else 'FAILED'} "
            f"({sum(checks.values())}/{len(checks)} checks) "
            f"in {duration:.3f}s",
            payload={"checks": checks, "all_ok": all_ok, "duration_s": round(duration, 3)},
        )

        if not all_ok:
            failed = [k for k, v in checks.items() if not v]
            logger.warning("Health check failures: %s", failed)

    # -----------------------------------------------------------------
    # Guarded accessors (raise if phase not completed)
    # -----------------------------------------------------------------

    def get_bus(self) -> Any:
        if "phase2" not in self.phases_completed:
            raise RuntimeError("Bus not initialized (Phase 2 not completed)")
        return self.bus

    def get_router(self) -> Any:
        if "phase2" not in self.phases_completed:
            raise RuntimeError("Router not initialized (Phase 2 not completed)")
        return self.router

    def get_fsm(self) -> Any:
        if "phase4" not in self.phases_completed:
            raise RuntimeError("FSM not initialized (Phase 4 not completed)")
        return self.fsm

    def get_model(self) -> Any:
        if "phase1" not in self.phases_completed:
            raise RuntimeError("LLM adapter not initialized (Phase 1 not completed)")
        return self.model

    def get_session_state(self) -> Any:
        if "phase3" not in self.phases_completed:
            raise RuntimeError("Session state not initialized (Phase 3 not completed)")
        return self.session_state

    def get_capability_registry(self) -> Any:
        if "phase3" not in self.phases_completed:
            raise RuntimeError("Capability registry not initialized (Phase 3 not completed)")
        return self.capability_registry

    def get_output_channel(self) -> OutputChannel:
        if "phase4" not in self.phases_completed:
            raise RuntimeError("Output channel not initialized (Phase 4 not completed)")
        assert self.output_channel is not None
        return self.output_channel

    def get_front_dispatcher(self) -> Any:
        if "phase4" not in self.phases_completed:
            raise RuntimeError("Front dispatcher not initialized (Phase 4 not completed)")
        return self.front_dispatcher

    def get_back_dispatcher(self) -> Any:
        if "phase4" not in self.phases_completed:
            raise RuntimeError("Back dispatcher not initialized (Phase 4 not completed)")
        return self.back_dispatcher

    def get_experience_layer(self) -> Any:
        if "phase5" not in self.phases_completed:
            raise RuntimeError("Experience layer not initialized (Phase 5 not completed)")
        return self.experience_layer

    def get_orchestrator(self) -> Any:
        if "phase5" not in self.phases_completed:
            raise RuntimeError("Orchestrator not initialized (Phase 5 not completed)")
        return self.orchestrator

    def get_iot_stubs(self) -> Any:
        if "phase5" not in self.phases_completed:
            raise RuntimeError("IoT stubs not initialized (Phase 5 not completed)")
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
            report["components"]["bus"] = "LocalBus"
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
        """Print formatted startup report to console."""
        report = self.get_status_report()

        print("\n" + "=" * 70)
        print("  K1 Demo Coordinator -- Startup Report")
        print("=" * 70)

        for phase_num, phase_key in enumerate(
            ["phase1", "phase2", "phase3", "phase4", "phase5", "phase6"], 1
        ):
            dur = self.startup_times.get(phase_key, 0)
            status = "OK" if phase_key in self.phases_completed else "FAIL"
            labels = {
                "phase1": "Config & LLM",
                "phase2": "Bus Infrastructure",
                "phase3": "Session & Capabilities",
                "phase4": "FSM & Actors",
                "phase5": "Support Systems",
                "phase6": "Health Check",
            }
            print(f"\n  [{phase_num}/6] {labels[phase_key]}")
            print(f"        Status:   {status}")
            print(f"        Duration: {dur:.3f}s")

        print(f"\n  Total startup: {report['total_startup_s']:.3f}s")
        print(f"  System ready:  {report['system_ready']}")
        print("\n  Components:")
        for name, val in report.get("components", {}).items():
            print(f"    {name}: {val}")

        print(f"\n  Timeline entries: {report['timeline_count']}")
        print("=" * 70)

    # -----------------------------------------------------------------
    # Capability wiring callbacks (injected into ToolContext)
    # -----------------------------------------------------------------

    async def _recall_memory_stub(
        self,
        query: str,
        memory_types: list | None = None,
        max_results: int = 5,
    ) -> list[dict]:
        """Recall from preloaded memories using keyword matching."""
        results = []
        query_lower = query.lower()
        for mem in self._preloaded_memories:
            tags = mem.get("tags", [])
            content_lower = mem.get("content", "").lower()
            if any(t in query_lower for t in tags) or any(
                word in content_lower for word in query_lower.split()
            ):
                results.append(mem)
                if len(results) >= max_results:
                    break

        if memory_types:
            results = [r for r in results if r.get("type") in memory_types]

        self._record(
            "runtime",
            "memory",
            "recall_memory",
            f"Recalled {len(results)} memories for '{query[:40]}'",
            payload={"query": query[:60], "count": len(results)},
        )
        return results

    async def _capability_discover(
        self,
        intent: str,
        domain: str | None = None,
        constraints: dict | None = None,
    ) -> list[dict]:
        """Discover capabilities via the registry."""
        if self.capability_registry is None:
            return []
        result = await self.capability_registry.discover(intent, domain, constraints)
        matches = result.get("matches", [])
        self._record(
            "runtime",
            "fabric",
            "capability.discover",
            f"Discovered {len(matches)} capabilities for '{intent[:40]}'",
            payload={"intent": intent[:60], "count": len(matches)},
        )
        return matches

    async def _capability_invoke(
        self,
        name: str,
        params: dict,
        session_id: str | None = None,
    ) -> dict:
        """Invoke a capability via the registry."""
        if self.capability_registry is None:
            return {"status": "error", "message": "No capability registry"}
        result = await self.capability_registry.invoke(name, params, session_id)
        self._record(
            "runtime",
            "fabric",
            "capability.invoke",
            f"Invoked capability: {name}",
            payload={"name": name, "status": result.get("status", "?")},
        )
        return result


# =========================================================================
# Port adapters for OrchestratorStub
# =========================================================================


class _FabricGatewayAdapter:
    """Wraps CapabilityRegistry to satisfy IFabricGatewayPort."""

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    async def execute(self, request: Any) -> Any:
        from poc.k1_poc.orchestrator.types import CapabilityResult

        if self._registry is None:
            return CapabilityResult(
                capability_name=request.capability_name,
                success=False,
                error="No registry",
            )
        result = await self._registry.invoke(
            request.capability_name,
            request.params or {},
        )
        return CapabilityResult(
            capability_name=request.capability_name,
            success=result.get("status", "ok") == "ok",
            data=result,
        )

    async def execute_batch(self, requests: list) -> list:
        return [await self.execute(r) for r in requests]


class _StateReadAdapter:
    """Wraps SessionStateManager to satisfy IStateReadPort."""

    def __init__(self, ss: Any) -> None:
        self._ss = ss

    async def snapshot(self, sections: list[str] | None = None) -> dict:
        if self._ss is None:
            return {}
        try:
            return self._ss.snapshot(sections)
        except Exception:
            return {}

    async def read_section(self, session_id: str, section: str) -> dict | None:
        if self._ss is None:
            return None
        try:
            return self._ss.get_section(section)
        except Exception:
            return None


class _DeltaEmitAdapter:
    """Wraps bus + timeline for IDeltaEmitPort."""

    def __init__(self, bus: Any, record_fn: Any) -> None:
        self._bus = bus
        self._record = record_fn

    async def emit(self, event_topic: str, payload: Any, trace_id: str = "") -> None:
        self._record(
            "runtime",
            "orchestrator",
            f"delta.emit.{event_topic}",
            f"Orchestrator delta emitted: {event_topic}",
            payload={"topic": event_topic},
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
