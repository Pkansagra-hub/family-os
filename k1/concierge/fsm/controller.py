"""
k1.concierge.fsm.controller -- ConciergeController (FSM event router).

V2 Design Ref: Section 4 (FSM: Event Router & State Machine)

The ConciergeController is the event router for the Concierge POC.
It is NOT a loop driver. It subscribes to bus topics, determines the
system's cognitive state, routes events to the correct handler, manages
concurrency between Front and Back, and controls history writes.

It owns:
  - State transitions (ConciergeState enum)
  - FrontLock (concurrency gate for Front LLM)
  - FSMTurnState (ephemeral turn tracking)
  - History writes (sole writer to history_active)
  - Phase 1 invocation sequencing
  - Cancel/interrupt routing

Bus components used:
  - IBus: subscribe to all topics, publish events
  - IMailboxRouter: deliver to front-llm / back-llm actor mailboxes
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # E4.M1.1 -- unified HIL service contract. Imported under TYPE_CHECKING to
    # avoid a runtime cycle (k1.kernel.ports -> k1.hil.types pulls async stack).
    from k1.kernel.ports.hil_port import IHILPort

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.bus.ports.bus import IBus
from k1.bus.ports.mailbox import IMailboxRouter
from k1.concierge.acking.write_elision import WriteElisionGate
from k1.concierge.bus.builders import (
    build_dead_letter,
    build_final_response,
    build_hitl_requested,
    build_hitl_resolved,
    build_intent_arbitrated,
    build_state_updated,
    build_task_cancel,
    build_task_complete,
    build_task_dispatch,
    build_task_failed,
    build_turn_completed,
    build_turn_started,
)
from k1.concierge.bus.setup import ACTOR_BACK, ACTOR_FRONT
from k1.concierge.bus.topics import (
    TOPIC_AFFECT_UPDATE,
    TOPIC_ARTIFACT_CREATED,
    TOPIC_CONCIERGE_CONFIG_UPDATE,
    TOPIC_DAG_COMPLETED,
    TOPIC_FINAL_RESPONSE,
    TOPIC_FINDINGS_READY,
    TOPIC_HIL_REQUEST,
    TOPIC_PROACTIVE_FILL,
    TOPIC_TASK_CANCEL,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_RESUME,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TOOL_COMPLETED,
    TOPIC_TOOL_STARTED,
    TOPIC_UI_TYPING,
    TOPIC_USER_INPUT,
    TOPIC_WEAVE_BATCH,
)
from k1.concierge.config import get_config
from k1.concierge.fsm.arbiter import (
    ArbiterDecision,
    ArbiterInput,
    ArbiterResult,
    ConversationArbiter,
    build_inflight_context,
)
from k1.concierge.fsm.control_extension import ConciergeControlExtension
from k1.concierge.fsm.dead_letter import DeadLetterPayload
from k1.concierge.fsm.errors import IllegalTransitionError
from k1.concierge.fsm.front_lock import FrontLock
from k1.concierge.fsm.idempotency import IdempotencyLedger
from k1.concierge.fsm.interrupt_handler import InterruptClassifier, ProactiveWakeHandler
from k1.concierge.fsm.response_final_table import (
    ResponseFinalAction,
    ResponseFinalDecision,
    decide_response_final,
)
from k1.concierge.fsm.states import ConciergeState
from k1.concierge.fsm.task_bridge import TaskBridge
from k1.concierge.fsm.transition_table import (
    TRIGGER_INTERRUPT_ROUTED,
    TRIGGER_PENDING_RESULTS_NON_EMPTY,
    TRIGGER_PROACTIVE_ROUTED,
    TRIGGER_SAME_TURN_COMPLETE,
    GuardAction,
    get_guard_action,
    is_legal,
    target_state,
)
from k1.concierge.fsm.turn_state import FSMTurnState
from k1.concierge.orchestrator.routing import route_task_sync
from k1.concierge.protocols.cancel_handler import CancellationHandler
from k1.concierge.protocols.cancellation import CancellationToken
from k1.concierge.protocols.hitl_persistence import (
    HILStateRecord,
    HILSubTask,
    scan_for_recovery,
)
from k1.concierge.protocols.hitl_wiring import build_resume_context
from k1.concierge.protocols.weave_batcher import WEAVE_BATCH_WINDOW_MS
from k1.concierge.protocols.weave_policy import (
    EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
    UserActivityTracker,
    WeaveDecision,
    WeaveDecisionResult,
    WeaveFallbackHandler,
    WeavePolicy,
    WeaveSignal,
    sort_results_for_delivery,
)
from k1.concierge.react.control import BackControlEvent
from k1.concierge.task.complexity import ComplexityTier
from k1.concierge.task.dispatch import TaskDispatch
from k1.concierge.task.intent import TaskIntent

# E4.M1.5: SuspensionManager relocated to k1.hil.suspension.
from k1.hil.suspension import SuspensionManager
from k1.sessionstate.public_types import (
    PrivacyBand,
    compute_temporal_anchor,
)

logger = logging.getLogger(__name__)

_INLINE_HIL_WIDGET_KINDS = frozenset({"capability_gate", "approval", "override"})


def _correlate_envelope(env: Envelope, source: Envelope) -> Envelope:
    """Copy source correlation headers onto an FSM-emitted envelope."""
    return replace(
        env,
        cognitive_trace_id=source.cognitive_trace_id,
        session_id=source.session_id,
        request_id=source.request_id,
    )


def _hil_requested_payload(
    *,
    hil_request_id: str,
    kind: str,
    task_id: str,
    inner: dict[str, Any],
    envelope: Envelope,
) -> dict[str, Any]:
    contract_payload = inner.get("contract")
    contract = contract_payload if isinstance(contract_payload, dict) else {}
    return {
        "pending_hil_id": hil_request_id,
        "hil_type": kind,
        "parent_task_id": task_id,
        "safety_band": contract.get("safety_band_min", "AMBER"),
        "hil_deadline_ms": int(_parse_payload(envelope).get("timeout_ms", 0) or 0),
        "resume_token": hil_request_id,
        "device_id": "",
        "task_id": task_id,
    }


class OrchestratorNotWired(RuntimeError):
    """Raised when HIGH-tier dispatch has no orchestrator and the
    legacy ``PassthroughPlannerStub`` fallback is disabled.

    M16.E1.I3: production must surface this loudly instead of silently
    degrading a HIGH-tier task into a 1-step MEDIUM plan. Test/dev
    contexts that intentionally run without an orchestrator should set
    ``ConciergeConfig.allow_planner_passthrough=True`` to keep the
    legacy stub.
    """


# ---------------------------------------------------------------------------
# Helper: parse JSON payload from Envelope bytes
# ---------------------------------------------------------------------------


def _parse_payload(envelope: Envelope) -> dict[str, Any]:
    """Extract dict payload from Envelope.payload bytes."""
    if not envelope.payload:
        return {}
    try:
        return json.loads(envelope.payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning(
            "Failed to parse payload for envelope %d on topic %s",
            envelope.envelope_id,
            envelope.topic,
        )
        return {}


def _coerce_tier(raw_tier: Any) -> ComplexityTier:
    """Convert string-like tier to ComplexityTier with LOW fallback."""
    if isinstance(raw_tier, ComplexityTier):
        return raw_tier
    try:
        return ComplexityTier(str(raw_tier).upper())
    except (TypeError, ValueError):
        return ComplexityTier.LOW


def _task_dispatch_from_payload(payload: dict[str, Any]) -> TaskDispatch:
    """Build canonical TaskDispatch from bus payload.

    Accepts both canonical payloads (intents as dicts) and legacy payloads
    (intents/actions as strings) to preserve compatibility with older tests.
    """
    tier = _coerce_tier(payload.get("tier", "LOW"))
    intents_raw = payload.get("intents", [])
    intents: list[TaskIntent] = []

    if isinstance(intents_raw, list):
        for item in intents_raw:
            if isinstance(item, dict) and item.get("action"):
                intents.append(TaskIntent.from_dict(item))
            elif isinstance(item, str) and item.strip():
                intents.append(TaskIntent(action=item.strip(), params={}))

    if not intents:
        action = str(payload.get("action") or "task")
        intents = [TaskIntent(action=action, params={})]

    kwargs: dict[str, Any] = {
        "intents": intents,
        "tier": tier,
        "budget_hint": payload.get("budget_hint"),
        "reference_context": payload.get("reference_context"),
        "safety_band": payload.get("safety_band", "AMBER"),
        "depends_on": payload.get("depends_on"),
        "context_snapshot": payload.get("context_snapshot"),
    }

    # Gracefully strip bad depends_on (LLM may pass a description string)
    dep = kwargs.get("depends_on")
    if dep is not None and not dep.startswith("task-"):
        logger.warning(
            "_task_dispatch_from_payload: depends_on is not a task ID, ignoring: %s",
            dep,
        )
        kwargs["depends_on"] = None

    task_id = payload.get("task_id")
    if task_id:
        kwargs["task_id"] = task_id

    return TaskDispatch(**kwargs)


# ---------------------------------------------------------------------------
# V3 M1 E1.2.3: Canonical event builders for ledger emission
# ---------------------------------------------------------------------------


def _build_canonical_event(
    entry_type: str,
    text: str,
    meta: dict[str, Any],
    metadata: dict[str, Any] | None,
) -> Any:
    """Build a canonical event from history entry_type and metadata.

    Returns None if the entry_type has no canonical mapping.
    Lazy imports to avoid circular dependencies.
    """
    from k1.concierge.events.conversation import UserInputReceived
    from k1.concierge.events.hitl import (
        HILRequested,
        HILResolved,
        TaskResumed,
        TaskSuspended,
    )
    from k1.concierge.events.task import (
        TaskCancelled,
        TaskCompleted,
        TaskCreated,
        TaskFailed,
    )
    from k1.concierge.events.weave import WeaveEmitted

    if entry_type == "user":
        return UserInputReceived(text=text, **meta)
    if entry_type == "task_dispatch":
        return TaskCreated(action=text, **meta)
    if entry_type == "task_complete":
        return TaskCompleted(action=text, **meta)
    if entry_type == "error":
        return TaskFailed(reason=text, **meta)
    if entry_type == "cancel_confirmed":
        return TaskCancelled(reason=text, **meta)
    if entry_type == "task_suspended":
        return TaskSuspended(suspension_type=text, **meta)
    if entry_type == "task_resumed":
        return TaskResumed(resume_instruction=text, **meta)
    if entry_type in ("hil_request", "hitl_request"):
        md = metadata or {}
        return HILRequested(
            question=text,
            hil_request_id=str(md.get("hil_request_id", "")),
            kind=str(md.get("kind", md.get("hil_type", ""))),
            caller_key=str(md.get("caller_key", "")),
            created_at_ms=int(md.get("created_at_ms", 0) or 0),
            timeout_ms=int(md.get("timeout_ms", 0) or 0),
            hil_type=str(md.get("hil_type", md.get("kind", ""))),
            options=list(md.get("options", []) or []),
            context=dict(md.get("context", {}) or {}),
            side_effects=list(md.get("side_effects", []) or []),
            safety_band=str(md.get("safety_band", "GREEN")),
            **meta,
        )
    if entry_type in ("hil_response", "hitl_response"):
        md = metadata or {}
        return HILResolved(
            raw_user_text=text,
            hil_request_id=str(md.get("hil_request_id", "")),
            kind=str(md.get("kind", md.get("hil_type", ""))),
            resolution=dict(md.get("resolution", {}) or {}),
            resolution_type=str(md.get("resolution_type", "selection")),
            **meta,
        )
    if entry_type == "assistant_response":
        return WeaveEmitted(response_text_preview=text, **meta)
    return None


# ---------------------------------------------------------------------------
# RunningTaskHandle -- M5 E5.5.4: inter-iteration injection handle
# ---------------------------------------------------------------------------


class RunningTaskHandle:
    """Handle to a running Back task for inter-iteration control events.

    The controller creates a handle when dispatching a task. The Back handler
    consumes ``control_queue`` between ReAct iterations so the FSM does not
    mutate Back's live message list directly.
    """

    __slots__ = ("task_id", "messages", "control_queue", "dispatch_payload", "started_at")

    def __init__(
        self,
        task_id: str,
        messages: list[Any] | None,
        control_queue: asyncio.Queue[BackControlEvent] | None,
        dispatch_payload: dict[str, Any],
        started_at: float,
    ) -> None:
        self.task_id = task_id
        self.messages = messages  # None until Back registers
        self.control_queue = control_queue or asyncio.Queue()
        self.dispatch_payload = dispatch_payload
        self.started_at = started_at


# ---------------------------------------------------------------------------
# TypedHistoryEntry
# ---------------------------------------------------------------------------


class TypedHistoryEntry:
    """A single entry in the FSM-managed history_active section.

    V2 Design Ref: Section 4 (History Write Protocol)

    Entries are written by the FSM at event boundaries. Each carries
    the turn number for timeline reconstruction.
    """

    __slots__ = (
        "turn_number",
        "entry_type",
        "role",
        "text",
        "timestamp_ms",
        "source",
        "task_id",
        "metadata",
    )

    def __init__(
        self,
        turn_number: int,
        entry_type: str,
        role: str,
        text: str = "",
        timestamp_ms: int = 0,
        source: str = "",
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.turn_number = turn_number
        self.entry_type = entry_type
        self.role = role
        self.text = text
        self.timestamp_ms = timestamp_ms or int(time.time() * 1000)
        self.source = source
        self.task_id = task_id
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "turn": self.turn_number,
            "type": self.entry_type,
            "role": self.role,
            "text": self.text,
            "timestamp_ms": self.timestamp_ms,
            "source": self.source,
        }
        if self.task_id is not None:
            d["task_id"] = self.task_id
        if self.metadata:
            d["metadata"] = self.metadata
        return d


# ---------------------------------------------------------------------------
# ConciergeController
# ---------------------------------------------------------------------------


class ConciergeController:
    """FSM Controller -- the event router for the Concierge POC.

    Subscribes to all POC bus topics and routes events to the correct
    handler based on current state. Manages state transitions, concurrency
    (FrontLock), turn tracking (FSMTurnState), and history writes.

    Args:
        bus: IBus for pub/sub event delivery.
        router: IMailboxRouter for point-to-point actor delivery.
    """

    def __init__(
        self,
        bus: IBus,
        router: IMailboxRouter,
    ) -> None:
        self._bus = bus
        self._router = router
        self._state = ConciergeState.LISTENING
        self._turn_number = 0
        # MW-dedup guard: track turn_ids for which `_emit_turn_completed`
        # has already published `k1.session.turn.completed.v1`.  Without
        # this, same-turn dispatch+complete followed by proactive
        # delivery emits the same turn_id twice and MW's
        # SessionBatchDispatcher logs a noisy duplicate-skip.
        self._emitted_turn_ids: set[str] = set()
        cfg = get_config().fsm
        self._turn_state = FSMTurnState(
            max_depth=cfg.pending_results_max_depth,
            ttl_seconds=cfg.pending_results_ttl_seconds,
        )
        self._front_lock = FrontLock()
        self._cancel_handler = CancellationHandler()
        self._suspension_manager = SuspensionManager()
        self._control_ext = ConciergeControlExtension()
        self._task_bridge = TaskBridge()
        self._interrupt_classifier = InterruptClassifier()
        self._arbiter = ConversationArbiter()
        self._proactive_wake = ProactiveWakeHandler()
        self._history: list[TypedHistoryEntry] = []
        self._active_task_ids: set[str] = set()
        self._task_dispatch_turns: dict[str, int] = {}  # task_id -> turn dispatched
        self._orchestrator: Any | None = None
        # M16.E1.I3: gate for the legacy PassthroughPlannerStub. Default
        # is False (production-strict): HIGH-tier dispatch with no
        # orchestrator wired raises OrchestratorNotWired. Tests/dev set
        # this to True via set_allow_planner_passthrough().
        self._allow_planner_passthrough: bool = False
        # E4.M1.4: legacy `_hil_coordinator` field removed alongside the
        # `HILCoordinator` class. The unified HIL service is wired via
        # `_hil_port` (set by `set_hil_port`) and the factory in E4.M1.6.
        self._hil_port: "IHILPort | None" = None
        self._weave_batcher: Any | None = None  # WeaveBatcher for queue mgmt
        self._subscription_handles: list[Any] = []
        self._idempotency = IdempotencyLedger(
            max_entries=get_config().fsm.idempotency_ledger_max_entries,
        )
        self._weave_flush_task: asyncio.Task[None] | None = None
        self._history_sink: Any | None = None  # Optional SS history_active section
        self._ss: Any | None = None  # Optional SessionStateManager for SS reads
        self._current_turn_user_text: str = ""  # Tracks user text for turn pairing
        self._current_turn_assistant_response: str = ""
        self._ledger: Any = None  # V3 M1 E1.2: Optional LedgerWriter for event sourcing
        self._hitl_responded_tasks: dict[str, str] = {}  # M5 E5.4.4: task_id -> device_id dedup
        self._pending_hil_subtasks: dict[str, HILSubTask] = (
            {}
        )  # M6 E6.1.2: task_id -> HILSubTask (single SOT for HITL context)
        self._running_tasks: dict[str, RunningTaskHandle] = (
            {}
        )  # M5 E5.5.4: inter-iteration injection
        self._current_turn_device_id: str | None = None  # M5 E5.5.6: device_id for current turn
        self._back_pool: Any | None = None  # M7 E7.5.6: BackPool for capacity-aware arbiter
        # M8 E8.5.2: Adaptive weave policy wiring
        self._weave_policy: WeavePolicy | None = None
        self._activity_tracker: UserActivityTracker | None = None
        self._weave_fallback = WeaveFallbackHandler()
        self._digest_flush_task: asyncio.Task[None] | None = None
        self._async_results_context: str = ""  # M8 E8.5.4: deferred results for STANDARD injection
        self._deferred_proactive_task: asyncio.Task[None] | None = (
            None  # Proactive delivery timer for same-turn completions
        )
        self._proactive_fill_last_by_key: dict[str, int] = {}
        self._write_elision_gate = WriteElisionGate()
        # OPP Pipeline: wires all 8 OPP primitives into lifecycle hooks
        self._opp_pipeline: Any | None = None
        logger.info(
            "ConciergeController.__init__: assembling sub-components "
            "(FrontLock, CancelHandler, SuspensionManager, ControlExtension, "
            "TaskBridge, InterruptClassifier, ProactiveWake)",
        )
        self._subscribe_all()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> ConciergeState:
        """Current FSM state."""
        return self._state

    @property
    def turn_number(self) -> int:
        """Current turn number."""
        return self._turn_number

    @property
    def turn_state(self) -> FSMTurnState:
        """Ephemeral turn state."""
        return self._turn_state

    @property
    def front_lock(self) -> FrontLock:
        """FrontLock concurrency gate."""
        return self._front_lock

    @property
    def cancel_handler(self) -> CancellationHandler:
        """CancellationHandler -- SOT for cancel tracking (Epic 2.1)."""
        return self._cancel_handler

    def get_cancel_token(self, task_id: str) -> CancellationToken | None:
        """Return the CancellationToken for *task_id* (M7 E7.5.3).

        Used by the coordinator consumer to bind the FSM's per-task
        token to a TaskLease so that all cancel paths (FSM, arbiter,
        HITL timeout, lease expiry) share a single token object.

        Args:
            task_id: The dispatched task ID.

        Returns:
            CancellationToken if registered, else None.
        """
        return self._cancel_handler.get_token(task_id)

    @property
    def suspension_manager(self) -> SuspensionManager:
        """SuspensionManager -- SOT for HITL suspensions (Epic 2.2)."""
        return self._suspension_manager

    @property
    def control_ext(self) -> ConciergeControlExtension:
        """ConciergeControlExtension -- SOT for FSM state tracking (Epic 3)."""
        return self._control_ext

    @property
    def task_bridge(self) -> TaskBridge:
        """TaskBridge -- SOT for task lifecycle in SessionState (Epic 3)."""
        return self._task_bridge

    @property
    def interrupt_classifier(self) -> InterruptClassifier:
        """InterruptClassifier -- SOT for interrupt classification (Epic 3)."""
        return self._interrupt_classifier

    @property
    def proactive_wake(self) -> ProactiveWakeHandler:
        """ProactiveWakeHandler -- SOT for proactive wake logic (Epic 3)."""
        return self._proactive_wake

    @property
    def history(self) -> list[TypedHistoryEntry]:
        """History entries written by the FSM."""
        return self._history

    @property
    def active_task_ids(self) -> set[str]:
        """Currently active task IDs."""
        return self._active_task_ids

    def set_orchestrator(self, orchestrator: Any) -> None:
        """Attach orchestrator runtime dependency (MEDIUM/HIGH dispatch path)."""
        self._orchestrator = orchestrator
        logger.info(
            "ConciergeController.set_orchestrator: attached %s",
            type(orchestrator).__name__,
        )

    def set_allow_planner_passthrough(self, allow: bool) -> None:
        """M16.E1.I3: enable/disable the legacy PassthroughPlannerStub.

        When False (production default), HIGH-tier dispatch with no
        orchestrator wired raises ``OrchestratorNotWired`` instead of
        silently collapsing the task into a 1-step MEDIUM plan.
        """
        self._allow_planner_passthrough = bool(allow)
        logger.info(
            "ConciergeController.set_allow_planner_passthrough: %s",
            self._allow_planner_passthrough,
        )

    def set_history_sink(self, section: Any) -> None:
        """Attach SS history_active section for turn persistence.

        When set, the FSM pushes completed turns (user text + final
        response) to the section at response.final boundaries so
        the front handler's build_chat_history reads real context.
        """
        self._history_sink = section
        logger.info("ConciergeController.set_history_sink: attached")

    def set_hil_port(self, hil_port: "IHILPort") -> None:
        """Attach the unified HIL service (E4.M1.1).

        Wired by the kernel via :class:`ConciergeFactory` in E4.M1.6.
        Replaces the deleted ``set_hitl_coordinator`` API; the unified
        service owns round budget, suspension persistence, and bus
        emission internally, so the FSM no longer patches private
        coordinator callbacks.
        """
        self._hil_port = hil_port
        logger.info(
            "ConciergeController.set_hil_port: attached %s",
            type(hil_port).__name__,
        )

    def set_session_state(self, ss: Any) -> None:
        """Attach SessionStateManager for SS reads and FSM/SS binding.

        Used to inject scoreboard referents into dispatch payloads and
        read narrative_active for context enrichment.

        M4 E4.1: rebinds TaskBridge to real SS task_state/task_artifacts
        sections and binds ConciergeControlExtension to real SS control
        section so that Front/Back actors see FSM state.
        """
        self._ss = ss

        # M4 E4.1.1: rebind TaskBridge to real SS sections
        ts = ss.get_section("task_state")
        ta = ss.get_section("task_artifacts")
        self._task_bridge.rebind(ts, ta)

        # M4 E4.1.2: bind ControlExtension to real SS control section
        control = ss.get_section("control")
        self._control_ext.bind_control_section(control)

        # M6 E6.4.2: Recover pending HITL suspensions from previous session
        self._recover_hitl_on_startup()

        logger.info("ConciergeController.set_session_state: attached + M4 binding complete")

    def set_weave_batcher(self, batcher: Any) -> None:
        """Attach WeaveBatcher for Front-busy queue management.

        When set, _deliver_to_front and _on_response_final call
        set_front_busy(True/False) so the WeaveBatcher can queue
        results arriving while Front LLM is generating.
        """
        self._weave_batcher = batcher
        logger.info(
            "ConciergeController.set_weave_batcher: attached %s",
            type(batcher).__name__,
        )

    def set_ledger(self, ledger: Any) -> None:
        """Attach LedgerWriter for V3 event sourcing (M1 E1.2).

        When set, _write_history() emits canonical events to the ledger
        BEFORE writing the in-memory history entry. This is the M1
        incremental migration: both ledger write and in-memory write happen.
        """
        self._ledger = ledger
        logger.info(
            "ConciergeController.set_ledger: attached for session=%s",
            getattr(ledger, "session_id", "unknown"),
        )

    def set_back_pool(self, back_pool: Any) -> None:
        """Attach BackPool for capacity-aware arbiter decisions (M7 E7.5.6).

        When set, build_inflight_context includes pool utilization and
        lease deadlines in the InflightContext snapshot.
        """
        self._back_pool = back_pool
        logger.info(
            "ConciergeController.set_back_pool: attached pool_size=%d",
            getattr(getattr(back_pool, "config", None), "pool_size", 0),
        )

    def set_weave_policy(self, policy: WeavePolicy) -> None:
        """Attach WeavePolicy for adaptive weave decisions (M8 E8.5.2).

        Replaces static get_weave_action() with context-aware adaptive
        policy.  When set, _on_task_complete uses WeavePolicy.decide()
        instead of hardcoded state-based routing.
        """
        self._weave_policy = policy
        logger.info("ConciergeController.set_weave_policy: attached")

    def set_activity_tracker(self, tracker: UserActivityTracker) -> None:
        """Attach UserActivityTracker for typing/idle signals (M8 E8.5.2).

        Provides user_typing and user_idle_ms signals to WeaveSignal
        collected inside _on_task_complete.
        """
        self._activity_tracker = tracker
        logger.info("ConciergeController.set_activity_tracker: attached")

    def set_opp_pipeline(self, pipeline: Any) -> None:
        """Attach OppPipeline to wire all 8 OPP primitives into lifecycle hooks.

        The pipeline is called at:
          - _on_task_complete_adaptive (OPP-8 delivery strategy)
          - _deliver_weave_immediate (OPP-1 pacing)
          - on_user_input (OPP-2 classify enrichment)
          - pre-LLM call (OPP-3 affect hard caps)
          - HITL resolution (OPP-4 trust accumulator)
          - idle tick (OPP-5 proactive scheduler)
          - prompt build (OPP-6 compression, OPP-7 identity)
        """
        self._opp_pipeline = pipeline
        logger.info(
            "ConciergeController.set_opp_pipeline: attached, status=%s",
            pipeline.status() if hasattr(pipeline, "status") else "unknown",
        )

    # ------------------------------------------------------------------
    # M8 E8.5.3: HITL pending check for WeaveSignal
    # ------------------------------------------------------------------

    def _has_pending_hitl(self) -> bool:
        """True if any task has a PENDING HILSubTask (M8 E8.5.3).

        Queries _pending_hil_subtasks (M6 SOT) for active HITL requests.
        Used by WeaveSignal.from_runtime() to set hitl_pending.
        """
        if self._pending_hil_subtasks:
            return True
        try:
            for entry in self._task_bridge.get_suspended_tasks():
                data = getattr(entry, "pending_hil_data", None)
                if isinstance(data, dict) and (
                    data.get("hil_request_id") or data.get("pending_hil_id")
                ):
                    return True
                if getattr(entry, "pending_hil", False):
                    return True
        except Exception:
            logger.debug("_has_pending_hitl: task bridge check failed", exc_info=True)
        try:
            for entry in self._task_bridge.task_state.get_all():
                data = getattr(entry, "pending_hil_data", None)
                if isinstance(data, dict) and getattr(entry, "status", "") not in {
                    "completed",
                    "failed",
                    "cancelled",
                }:
                    if data.get("hil_request_id") or data.get("pending_hil_id"):
                        return True
        except Exception:
            logger.debug("_has_pending_hitl: task_state scan failed", exc_info=True)
        return False

    def rebuild_history_from_projection(self, history: list[dict[str, Any]]) -> int:
        """Replace the runtime history cache from ledger projection data."""
        self._history.clear()
        for item in history:
            self._history.append(
                TypedHistoryEntry(
                    turn_number=int(item.get("turn", 0) or 0),
                    entry_type=str(item.get("type", "")),
                    role=str(item.get("role", "")),
                    text=str(item.get("text", "")),
                    timestamp_ms=int(item.get("timestamp_ms", 0) or 0),
                    source=str(item.get("source", "")),
                    task_id=item.get("task_id"),
                    metadata=dict(item.get("metadata", {}) or {}),
                )
            )
        return len(self._history)

    def rebuild_pending_hil_from_projection(self, records: dict[str, HILStateRecord]) -> int:
        """Rebuild pending-HIL mirrors from normalized ledger projection records."""
        self._pending_hil_subtasks.clear()
        restored = 0
        for task_id, record in records.items():
            data = record.to_pending_hil_data()
            if self._task_bridge.get_task(task_id) is None:
                try:
                    from k1.sessionstate.sections.task_state import TaskStatus

                    self._task_bridge.task_state.add_task(
                        action=f"hil:{record.kind or record.hil_type}",
                        task_id=task_id,
                        status=TaskStatus.SUSPENDED,
                    )
                except Exception:
                    logger.debug(
                        "rebuild_pending_hil_from_projection: could not create task %s",
                        task_id,
                        exc_info=True,
                    )
            try:
                self._task_bridge.set_pending_hil_data(task_id, data)
            except Exception:
                logger.debug(
                    "rebuild_pending_hil_from_projection: set pending data failed for %s",
                    task_id,
                    exc_info=True,
                )
            if record.pending_hil_id and record.react_snapshot and not task_id.startswith("hil:"):
                try:
                    self._pending_hil_subtasks[task_id] = HILSubTask.from_persistence(data)
                except Exception:
                    logger.debug(
                        "rebuild_pending_hil_from_projection: HILSubTask rebuild skipped for %s",
                        task_id,
                        exc_info=True,
                    )
            restored += 1
        return restored

    def _check_hil_state_coherence(
        self,
        *,
        task_id: str = "",
        hil_request_id: str = "",
        context: str = "",
    ) -> list[str]:
        """Log non-fatal divergence between pending-HIL mirrors."""
        anomalies: list[str] = []

        def _add(message: str) -> None:
            anomalies.append(message)
            logger.error(
                "hil_state_coherence anomaly=%s context=%s task_id=%s hil_request_id=%s",
                message,
                context,
                task_id,
                hil_request_id,
            )

        try:
            for pending_task_id, subtask in list(self._pending_hil_subtasks.items()):
                entry = self._task_bridge.get_task(pending_task_id)
                if entry is None:
                    _add(f"pending_subtask_without_task:{pending_task_id}")
                    continue
                if getattr(entry, "status", "") in {"completed", "failed", "cancelled"}:
                    _add(f"terminal_task_has_pending_subtask:{pending_task_id}")
                if not getattr(entry, "pending_hil", False) and not getattr(
                    entry, "pending_hil_data", None
                ):
                    _add(f"pending_subtask_without_task_pending_data:{pending_task_id}")
                if hil_request_id and pending_task_id == task_id:
                    expected = getattr(subtask, "pending_hil_id", "")
                    if expected and expected != hil_request_id:
                        _add(f"hil_request_id_mismatch:{expected}!={hil_request_id}")

            for entry in self._task_bridge.task_state.get_all():
                entry_task_id = getattr(entry, "task_id", "")
                data = getattr(entry, "pending_hil_data", None)
                if isinstance(data, dict) and (
                    data.get("hil_request_id") or data.get("pending_hil_id")
                ):
                    if not self._has_pending_hitl():
                        _add(f"pending_data_invisible_to_has_pending_hitl:{entry_task_id}")
                    if hil_request_id and entry_task_id == task_id:
                        data_id = str(
                            data.get("hil_request_id") or data.get("pending_hil_id") or ""
                        )
                        if data_id and data_id != hil_request_id:
                            _add(f"task_pending_hil_id_mismatch:{data_id}!={hil_request_id}")
                if getattr(entry, "status", "") in {"completed", "failed", "cancelled"}:
                    if entry_task_id in self._pending_hil_subtasks:
                        _add(f"terminal_task_in_pending_subtasks:{entry_task_id}")
                    if entry_task_id in getattr(self._suspension_manager, "_contexts", {}):
                        _add(f"terminal_task_in_suspension_contexts:{entry_task_id}")
                    if entry_task_id in getattr(self._suspension_manager, "_active", {}):
                        _add(f"terminal_task_in_suspension_active:{entry_task_id}")
        except Exception:
            logger.debug("_check_hil_state_coherence failed", exc_info=True)
        return anomalies

    def _collect_weave_signal(self, task_id: str = "") -> WeaveSignal:
        """Collect the pure weave signal snapshot for a candidate task."""
        tracker = self._activity_tracker or UserActivityTracker()
        return WeaveSignal.from_runtime(
            fsm_state=self._state,
            turn_state=self._turn_state,
            back_pool=self._back_pool,
            ss=self._ss,
            activity_tracker=tracker,
            hitl_pending=self._has_pending_hitl(),
        )

    def _decide_weave(self, signal: WeaveSignal) -> WeaveDecisionResult:
        """Return a weave decision with fallback handling."""
        decision, _fallback_used = self._decide_weave_with_fallback(signal)
        return decision

    def _decide_weave_with_fallback(
        self,
        signal: WeaveSignal,
    ) -> tuple[WeaveDecisionResult, bool]:
        """Return a weave decision plus whether static fallback was used."""
        policy = self._weave_policy
        if policy is None:
            return self._weave_fallback.fallback_decide(self._state), True
        try:
            return policy.decide(signal), False
        except Exception:
            logger.warning("WeavePolicy.decide() raised -- using fallback", exc_info=True)
            return self._weave_fallback.fallback_decide(self._state), True

    def _apply_weave_decision(
        self,
        decision: WeaveDecisionResult,
        task_id: str,
        envelope: Envelope,
    ) -> None:
        """Apply side effects for a pure weave decision."""
        if decision.decision == WeaveDecision.IMMEDIATE:
            self._deliver_weave_immediate(envelope)
        elif decision.decision == WeaveDecision.BATCH:
            self._schedule_weave_flush_adaptive(envelope, decision.window_ms)
        elif decision.decision == WeaveDecision.DEFER:
            self._mark_results_deferred(envelope)
        elif decision.decision == WeaveDecision.DIGEST:
            self._schedule_digest_flush(envelope, decision.window_ms)
        elif decision.decision == WeaveDecision.SUPPRESS:
            self._suppress_result(task_id, decision.reasoning)

    def _discard_task_result_ownership(self, task_id: str) -> bool:
        """Remove a task result from every queue that can own it."""
        removed = self._turn_state.discard_task(task_id)
        batcher = self._weave_batcher
        if batcher is not None and hasattr(batcher, "discard_task"):
            try:
                removed = bool(batcher.discard_task(task_id)) or removed
            except Exception:
                logger.warning(
                    "WeaveBatcher.discard_task failed for %s",
                    task_id,
                    exc_info=True,
                )
        return removed

    def _try_chain_into_current_response(
        self,
        task_id: str,
        payload: dict[str, Any],
        envelope: Envelope,
    ) -> bool:
        """Try to chain a same-turn result into Front's current response."""
        if not self._front_lock.is_accepting_context():
            return False
        return False

    # ------------------------------------------------------------------
    # M8 E8.5.6: Task urgency retrieval from TaskBridge
    # ------------------------------------------------------------------

    def _get_task_urgency(self, task_id: str) -> str:
        """Read urgency from the dispatch payload stored on TaskStateEntry.

        M8 E8.5.6: Falls back to "normal" if urgency not found.
        """
        entry = self._task_bridge.get_task(task_id)
        if entry and isinstance(entry, dict):
            return entry.get("urgency", "normal")
        return "normal"

    # ------------------------------------------------------------------
    # M5 E5.5.4: RunningTaskHandle management
    # ------------------------------------------------------------------

    def register_running_task_messages(self, task_id: str, messages: list[Any]) -> None:
        """Register the mutable messages list from Back's react_loop.

        Called by back_handler after building its messages list so that
        ``_handle_arbiter_modify()`` can inject a synthetic PARAMETER
        UPDATE message between iterations.

        Args:
            task_id: The task whose messages list to register.
            messages: The **same** list object used by react_loop.
        """
        handle = self._running_tasks.get(task_id)
        if handle is not None:
            handle.messages = messages
            logger.info(
                "FSM.register_running_task_messages: task_id=%s messages_len=%d",
                task_id,
                len(messages),
            )
        else:
            logger.warning(
                "FSM.register_running_task_messages: no handle for task_id=%s "
                "(task may have completed before registration)",
                task_id,
            )

    def get_running_task_control_queue(
        self,
        task_id: str,
    ) -> asyncio.Queue[BackControlEvent] | None:
        """Return the control queue for a running Back task, if present."""
        handle = self._running_tasks.get(task_id)
        return handle.control_queue if handle is not None else None

    def register_running_task_control_queue(
        self,
        task_id: str,
        queue: asyncio.Queue[BackControlEvent],
    ) -> None:
        """Register a Back-owned control queue for compatibility callers."""
        handle = self._running_tasks.get(task_id)
        if handle is not None:
            handle.control_queue = queue
            logger.info("FSM.register_running_task_control_queue: task_id=%s", task_id)
        else:
            self._running_tasks[task_id] = RunningTaskHandle(
                task_id=task_id,
                messages=None,
                control_queue=queue,
                dispatch_payload={},
                started_at=time.monotonic(),
            )

    def _remove_running_task(self, task_id: str) -> None:
        """Remove RunningTaskHandle when a task completes or is cancelled."""
        removed = self._running_tasks.pop(task_id, None)
        if removed:
            logger.debug(
                "FSM._remove_running_task: task_id=%s (ran %.1fs)",
                task_id,
                time.monotonic() - removed.started_at,
            )

    @property
    def ledger(self) -> Any:
        """Optional LedgerWriter for event sourcing (V3 M1 E1.2)."""
        return self._ledger

    def _try_deserialize(self, envelope: Envelope) -> Any | None:
        """Attempt to deserialize envelope payload to a canonical event.

        M1 E1.4.3: Dual-mode bridge. Returns a typed CanonicalEventMeta
        subclass if the payload contains event_type, or None if the payload
        is legacy (no event_type field) or deserialization fails.

        In M1, this is available for handlers but NOT mandatory. Handlers
        continue using raw dict destructuring. Full migration to typed
        events happens incrementally in M2-M5.
        """
        try:
            from k1.concierge.bus.deserialize import deserialize_envelope

            return deserialize_envelope(envelope)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Subscription wiring (Epic 8.1.2)
    # ------------------------------------------------------------------

    def _subscribe_all(self) -> None:
        """Subscribe to all POC topics on IBus."""
        logger.info("ConciergeController._subscribe_all: wiring FSM event handlers")
        subscriptions = [
            (TOPIC_USER_INPUT, self._on_user_input),
            (TOPIC_FINAL_RESPONSE, self._on_response_final),
            (TOPIC_TASK_DISPATCH, self._on_task_dispatch),
            (TOPIC_DAG_COMPLETED, self._on_dag_completed),
            # M2 E2.1.5: Removed bare string "k1.orchestration.dag.completed"
            # duplicate — TOPIC_DAG_COMPLETED already covers this topic.
            (TOPIC_TASK_COMPLETE, self._on_task_complete),
            (TOPIC_TASK_FAILED, self._on_task_failed),
            (TOPIC_TASK_CANCEL, self._on_task_cancel),
            (TOPIC_TASK_SUSPENDED, self._on_task_suspended),
            (TOPIC_TASK_RESUME, self._on_task_resume),
            # HIL Unification (E4): unified HIL request topic delivered to FSM,
            # which sets pending_hil_data + transitions to CLARIFYING_WORKER
            # + delivers to Front for HITL_RELAY rendering.
            (TOPIC_HIL_REQUEST, self._on_hil_request),
            (TOPIC_FINDINGS_READY, self._on_findings_ready),
            (TOPIC_ARTIFACT_CREATED, self._on_artifact_created),
            (TOPIC_AFFECT_UPDATE, self._on_affect_update),
            (TOPIC_PROACTIVE_FILL, self._on_proactive_fill),
            (TOPIC_TOOL_STARTED, self._on_tool_started),
            (TOPIC_TOOL_COMPLETED, self._on_tool_completed),
            (TOPIC_WEAVE_BATCH, self._on_weave_batch),
            # M8 E8.5.1: UI typing signal for weave suppression
            (TOPIC_UI_TYPING, self._on_ui_typing),
            # M6 E6.4 (C06): runtime concierge config updates
            (TOPIC_CONCIERGE_CONFIG_UPDATE, self._on_concierge_config_update),
        ]
        for topic, handler in subscriptions:
            handle = self._bus.subscribe(topic, handler)
            self._subscription_handles.append(handle)
            logger.debug("  FSM subscribed -> %s (%s)", topic, handler.__name__)
        logger.info(
            "ConciergeController._subscribe_all: complete (%d handlers wired, initial_state=%s)",
            len(self._subscription_handles),
            self._state.name,
        )

    # ------------------------------------------------------------------
    # Transition engine (Epic 8.1.3)
    # ------------------------------------------------------------------

    def _transition(
        self,
        to_state: ConciergeState,
        trigger: str,
        envelope: Envelope,
    ) -> None:
        """Transition FSM to a new state with validation and observability.

        Args:
            to_state: Target state.
            trigger: Event topic or synthetic trigger that caused transition.
            envelope: The envelope that triggered this transition.

        Raises:
            IllegalTransitionError: If the transition is not in TRANSITION_TABLE.

        Side effects:
            1. Validates transition is legal.
            2. Updates self._state.
            3. Publishes state.updated observability event.
            4. Logs transition.
        """
        if not is_legal(self._state, trigger):
            error = IllegalTransitionError(self._state.name, trigger)
            logger.warning(str(error))
            raise error

        expected_target = target_state(self._state, trigger)
        if expected_target is not None and expected_target != to_state:
            error = IllegalTransitionError(
                self._state.name,
                f"{trigger} -> {to_state.name} (expected {expected_target.name if expected_target else 'None'})",
            )
            logger.warning(str(error))
            raise error

        from_state = self._state
        self._state = to_state
        # Sync ConciergeControlExtension (Epic 3)
        self._control_ext.set_fsm_state(to_state)
        logger.info(
            "FSM %s -> %s on %s [envelope_id=%d]",
            from_state.name,
            to_state.name,
            trigger,
            envelope.envelope_id,
        )

        # Emit observability event
        self._bus.publish(
            build_state_updated(
                payload={
                    "from_state": from_state.name,
                    "to_state": to_state.name,
                    "trigger": trigger,
                    "turn_number": self._turn_number,
                    "envelope_id": envelope.envelope_id,
                },
                parent_id=envelope.envelope_id,
            )
        )

    # ------------------------------------------------------------------
    # M2 E2.3.3: Topic guard helper (replaces 4 copy-pasted blocks)
    # ------------------------------------------------------------------

    def _topic_guard(self, envelope: Envelope, expected_topic: str) -> bool:
        """Return True if envelope matches expected topic.

        Logs and returns False otherwise. Defence against TimingChain
        _cascade_causal dispatching child envelopes through the
        parent's handler chain.
        """
        if envelope.topic == expected_topic:
            return True
        logger.debug(
            "FSM topic guard: handler expects %s, got %s (envelope_id=%d)",
            expected_topic,
            envelope.topic,
            envelope.envelope_id,
        )
        return False

    # ------------------------------------------------------------------
    # M2 E2.3.4: Finalize turn helper (replaces 3 emit+drain combos)
    # ------------------------------------------------------------------

    def _finalize_turn(self, envelope: Envelope) -> None:
        """Emit turn.completed and drain FrontLock queue. Always called together."""
        self._emit_turn_completed(envelope)
        self._drain_front_lock_queue()

    # ------------------------------------------------------------------
    # M2 E2.1.2: Guard dispatch gate
    # ------------------------------------------------------------------

    def _guard_dispatch(self, envelope: Envelope) -> GuardAction:
        """Look up the guard action for this envelope in the current state.

        Returns the GuardAction that the handler should obey.
        """
        action, _ = get_guard_action(self._state, envelope.topic)
        return action

    def _publish_dead_letter(self, envelope: Envelope, reason: str) -> None:
        """Publish a dead-letter event for a rejected envelope.

        M2 E2.2.2: Uses TOPIC_DEAD_LETTER and DeadLetterPayload schema
        so dead-letter consumers can classify, count, and optionally retry.
        Respects fsm.dead_letter_enabled config flag.
        """
        if not get_config().fsm.dead_letter_enabled:
            return

        # BUG-8 FIX: Parse payload once instead of twice.
        payload_summary = ""
        task_id = ""
        try:
            raw = json.loads(envelope.payload) if envelope.payload else {}
            payload_summary = json.dumps(raw, default=str)[:500]
            task_id = raw.get("task_id", "")
        except Exception:
            payload_summary = "(unparseable)"

        dl = DeadLetterPayload(
            original_topic=envelope.topic,
            original_envelope_id=envelope.envelope_id,
            reason=reason,
            fsm_state_at_rejection=self._state.name,
            turn_number=self._turn_number,
            task_id=task_id,
            original_payload_summary=payload_summary,
        )

        logger.warning(
            "FSM DEAD-LETTER: state=%s topic=%s reason=%s envelope_id=%d",
            self._state.name,
            envelope.topic,
            reason,
            envelope.envelope_id,
        )

        # M2 E2.5.2: Record dead-letter in ledger before bus publish
        if self._ledger is not None:
            from k1.concierge.events.base import from_envelope
            from k1.concierge.events.conversation import DeadLettered

            meta = from_envelope(envelope, "fsm", causation_id=str(envelope.envelope_id))
            meta["task_id"] = task_id
            dl_event = DeadLettered(
                original_event={"payload_summary": payload_summary},
                reason=reason,
                fsm_state_at_rejection=self._state.name,
                original_topic=envelope.topic,
                **meta,
            )
            self._ledger.append_sync(dl_event)

        self._bus.publish(
            build_dead_letter(
                payload=dl.to_dict(),
                parent_id=envelope.envelope_id,
            )
        )

    # ------------------------------------------------------------------
    # History write helpers
    # ------------------------------------------------------------------

    def _write_history(
        self,
        entry_type: str,
        role: str,
        text: str = "",
        source: str = "",
        task_id: str | None = None,
        envelope: Envelope | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TypedHistoryEntry:
        """Write a TypedHistoryEntry to history_active.

        The FSM is the sole writer to history_active (V2 Section 4).

        V3 M1 E1.2.3: When ledger is attached, emits the corresponding
        canonical event BEFORE the in-memory history write. The ledger
        write is the commitment point.
        """
        # V3 M1 E1.2.3: Emit canonical event to ledger before in-memory write
        if self._ledger is not None:
            self._emit_ledger_event(entry_type, text, source, task_id, envelope, metadata)

        timestamp_ms = 0
        if envelope:
            timestamp_ms = envelope.created_ns // 1_000_000 if envelope.created_ns else 0
        entry = TypedHistoryEntry(
            turn_number=self._turn_number,
            entry_type=entry_type,
            role=role,
            text=text,
            timestamp_ms=timestamp_ms,
            source=source,
            task_id=task_id,
            metadata=metadata,
        )
        self._history.append(entry)
        return entry

    def _emit_ledger_event(
        self,
        entry_type: str,
        text: str,
        source: str,
        task_id: str | None,
        envelope: Envelope | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Construct and append a canonical event to the ledger.

        V3 M1 E1.2.3: Maps history entry_type to canonical event class,
        constructs the event with available metadata, and appends to ledger.

        Entry types without a canonical mapping are silently skipped.
        """
        from k1.concierge.events.base import from_envelope

        if metadata and metadata.get("ledger_event_already_emitted"):
            return

        # Build metadata kwargs from envelope
        meta: dict[str, Any] = {}
        if envelope is not None:
            meta = from_envelope(envelope, source or "fsm")
        else:
            meta["actor"] = source or "fsm"
            meta["session_id"] = getattr(self._ledger, "session_id", "")
        meta["task_id"] = task_id or ""

        # Map entry_type to canonical event construction
        event = _build_canonical_event(entry_type, text, meta, metadata)
        if event is None:
            return

        self._ledger.append_sync(event)

    def _emit_intent_arbitrated_ledger(
        self,
        arbiter_result: Any,
        inflight: Any,
        envelope: Envelope,
        device_id: str = "",
    ) -> None:
        """M5 E5.5.1: Record IntentArbitrated canonical event in ledger.

        Called immediately after bus.publish(intent.arbitrated) in both
        _handle_interrupt and the normal-turn router.
        """
        if self._ledger is None:
            return
        try:
            import uuid

            from k1.concierge.events.base import from_envelope
            from k1.concierge.events.conversation import IntentArbitrated

            meta = from_envelope(envelope, "fsm") if envelope else {"actor": "fsm"}
            meta["session_id"] = getattr(self._ledger, "session_id", "")
            inputs = arbiter_result.inputs
            event = IntentArbitrated(
                event_id=meta.get("event_id", "") or str(uuid.uuid4()),
                session_id=meta.get("session_id", ""),
                correlation_id=meta.get("correlation_id", ""),
                causation_id=meta.get("causation_id", ""),
                parent_event_id=meta.get("parent_event_id", ""),
                actor="fsm",
                intent_class=arbiter_result.decision.value,
                confidence=arbiter_result.confidence,
                target_task_id=arbiter_result.target_task_id or "",
                routing_metadata={
                    "domain": inputs.domain_context,
                    "safety_band": inputs.safety_band,
                    "inflight_task_count": len(inflight.tasks),
                    "device_id": device_id or "",
                    **(arbiter_result.routing_metadata or {}),
                },
            )
            self._ledger.append_sync(event)
        except Exception:
            logger.debug(
                "_emit_intent_arbitrated_ledger: failed",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Event handlers (Epic 8.2)
    # ------------------------------------------------------------------

    def _on_user_input(self, envelope: Envelope) -> None:
        """Handle k1.session.user.input.v1 -- the turn entry point.

        Behavior depends on current state (V2 Section 4):
          LISTENING        -> Normal turn start, DISPATCHING
          COMPANIONING     -> Interrupt, INTERRUPT_HANDLING -> DISPATCHING
          CLARIFYING_USER  -> User answered clarification, DISPATCHING
          CLARIFYING_WORKER -> User answering HITL (same turn, no increment)
          Other            -> Queue in FrontLock
        """
        # Dedup: TimingChain causal cascade can re-enter this handler
        # for the same envelope_id multiple times within a single
        # bus.publish() call. Drop duplicates.
        # M2 E2.3.2/E2.3.5: Uses IdempotencyLedger with LRU eviction.
        env_id = envelope.envelope_id
        if env_id and not self._idempotency.check_and_mark(env_id, self._turn_number):
            logger.debug(
                "FSM._on_user_input: DEDUP drop envelope_id=%d (already processed)",
                env_id,
            )
            return

        # M2 E2.3.3: Topic guard
        if not self._topic_guard(envelope, TOPIC_USER_INPUT):
            return

        payload = _parse_payload(envelope)
        text = payload.get("text", "")
        device_id = payload.get("device_id", "")  # M5 E5.4.1
        self._current_turn_device_id = device_id or None  # M5 E5.5.6: track for TurnMutationSummary
        logger.info(
            "FSM._on_user_input: state=%s envelope_id=%d text=%s device=%s",
            self._state.name,
            envelope.envelope_id,
            text[:60],
            device_id or "none",
        )

        # M5 E5.4.1: Track device in SS meta section
        if device_id and self._ss is not None:
            try:
                meta = self._ss.get_section("meta")
                if meta is not None and hasattr(meta, "set_active_device"):
                    meta.set_active_device(device_id)
            except Exception:
                pass

        # M2 E2.1.2: Guard gate (after dedup + topic guard)
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "user_input_invalid_state")
            return

        if self._state == ConciergeState.CLARIFYING_WORKER:
            # HITL response -- same turn, no increment.
            # Front will build task.resume. Stay in CLARIFYING_WORKER.
            # Find the suspended task_id for history linkage
            suspended = self._task_bridge.get_suspended_tasks()
            hitl_task_id = suspended[0].task_id if suspended else None
            self._write_history(
                entry_type="user",
                role="user",
                text=text,
                source="user",
                task_id=hitl_task_id,
                envelope=envelope,
            )
            self._transition(
                ConciergeState.CLARIFYING_WORKER,
                TOPIC_USER_INPUT,
                envelope,
            )
            # Deliver to Front via FrontLock
            if self._front_lock.try_deliver(envelope):
                self._deliver_to_front(envelope)
            return

        if self._state in (ConciergeState.COMPANIONING, ConciergeState.PROGRESSING):
            # M2 E2.1.4: Deduplicated interrupt path for COMPANIONING/PROGRESSING
            self._handle_interrupt(envelope, text, device_id=device_id)
            return

        if self._state in (
            ConciergeState.LISTENING,
            ConciergeState.CLARIFYING_USER,
        ):
            # Normal turn start or clarification answer
            self._turn_number += 1
            self._current_turn_user_text = text
            self._current_turn_assistant_response = ""
            self._write_history(
                entry_type="user",
                role="user",
                text=text,
                source="user",
                envelope=envelope,
            )
            self._transition(
                ConciergeState.DISPATCHING,
                TOPIC_USER_INPUT,
                envelope,
            )
            # Emit turn.started
            self._bus.publish(
                build_turn_started(
                    payload={
                        "turn_number": self._turn_number,
                        "trigger": "user_input",
                    },
                    parent_id=envelope.envelope_id,
                )
            )
            # M8 E8.5.4: Check deferred results from previous weave DEFER decisions
            self._check_deferred_results_on_input(envelope)
            # Update activity tracker on user input
            if self._activity_tracker is not None:
                self._activity_tracker.on_user_input()
            # Route normal turn through Arbiter -> DISPATCHING (M5 E5.3.1)
            self._route_user_turn(envelope, text, device_id=device_id)
            return

        # States where user input should be queued, not dropped.
        # DELIVERING/WEAVING: Front is presenting a Back result or weave.
        # Queue the user input in FrontLock (URGENT priority) so it's
        # processed after the current delivery cycle completes.
        if self._state in (
            ConciergeState.DELIVERING,
            ConciergeState.WEAVING,
            ConciergeState.PROACTIVE_WAKE,
        ):
            logger.info(
                "user.input arrived in state %s -- queueing in FrontLock (envelope_id=%d)",
                self._state.name,
                envelope.envelope_id,
            )
            # FrontLock.try_deliver returns False when busy, which queues it
            self._front_lock.try_deliver(envelope)
            return

        # Guard matrix should have caught all invalid states above.
        # If we reach here, log for diagnostics.
        logger.warning(
            "user.input arrived in state %s -- unhandled by guard matrix (envelope_id=%d)",
            self._state.name,
            envelope.envelope_id,
        )

    def _handle_interrupt(self, envelope: Envelope, text: str, *, device_id: str = "") -> None:
        """M5 E5.2.1: Arbiter-based interrupt handler for COMPANIONING/PROGRESSING.

        Builds a minimal ArbiterInput (with safety_band derived from cheap
        crisis-keyword check) and routes through the deterministic Arbiter.
        Steps:
          1. Build ArbiterInput (crisis check -> safety_band)
          2. Snapshot inflight context
          3. Arbiter classifies user intent against inflight work
          4. Emit intent.arbitrated event BEFORE acting
          5. Branch on Arbiter decision (4 paths)
        """
        inputs = self._build_arbiter_input(text)

        # Build inflight context from M4-bound SS sections (M5 E5.4.1: device_id)
        inflight = build_inflight_context(
            ss=self._ss,
            suspension_manager=self._suspension_manager,
            cancel_handler=self._cancel_handler,
            turn_state=self._turn_state,
            current_turn=self._turn_number,
            device_id=device_id or None,
            back_pool=self._back_pool,
        )

        # Arbiter classification (deterministic, no LLM)
        arbiter_result = self._arbiter.classify(text, inputs, inflight)
        logger.info(
            "FSM._handle_interrupt: arbiter=%s conf=%.2f target=%s (envelope_id=%d)",
            arbiter_result.decision.value,
            arbiter_result.confidence,
            arbiter_result.target_task_id or "none",
            envelope.envelope_id,
        )

        # Emit intent.arbitrated BEFORE acting (5.1.5 / 5.2.1 contract)
        self._bus.publish(
            build_intent_arbitrated(
                payload={
                    "decision": arbiter_result.decision.value,
                    "confidence": arbiter_result.confidence,
                    "target_task_id": arbiter_result.target_task_id,
                    "intent_class": inputs.intent_classification,
                    "domain": inputs.domain_context,
                    "safety_band": inputs.safety_band,
                    "inflight_task_count": len(inflight.tasks),
                    "routing_metadata": arbiter_result.routing_metadata,
                },
                parent_id=envelope.envelope_id,
            )
        )

        # M5 E5.5.1: Record IntentArbitrated in ledger
        self._emit_intent_arbitrated_ledger(
            arbiter_result,
            inflight,
            envelope,
            device_id,
        )

        # Branch on decision
        if arbiter_result.decision == ArbiterDecision.CANCEL:
            self._handle_arbiter_cancel(envelope, text, arbiter_result)
        elif arbiter_result.decision == ArbiterDecision.MODIFY_INFLIGHT:
            self._handle_arbiter_modify(envelope, text, arbiter_result)
        elif arbiter_result.decision == ArbiterDecision.DEFER:
            self._handle_arbiter_defer(envelope, text, arbiter_result)
        else:  # PARALLEL_NEW
            self._handle_arbiter_parallel_new(envelope, text, arbiter_result)

    # ------------------------------------------------------------------
    # M5 E5.2.2: Arbiter CANCEL handler
    # ------------------------------------------------------------------

    def _handle_arbiter_cancel(
        self,
        envelope: Envelope,
        text: str,
        arbiter_result: Any,
    ) -> None:
        """Handle CANCEL decision from Arbiter.

        Deterministic cancel routing -- no LLM call needed.
        Sets cancel flags on CancellationHandler, transitions to CANCELLING,
        then emits task.cancel events for observability.

        Transition happens BEFORE bus.publish(task.cancel) because the bus
        is synchronous: publishing would trigger _on_task_cancel which tries
        the same transition. By transitioning first, _on_task_cancel harmlessly
        dead-letters from CANCELLING state.

        Back's ReAct loop sees the cancel flag on the next iteration
        boundary (Constraint C2: latency up to 1 LLM call duration).
        """
        target = arbiter_result.target_task_id

        # Write history with cancel metadata
        self._turn_number += 1
        self._write_history(
            entry_type="user",
            role="user",
            text=text,
            source="user",
            envelope=envelope,
            metadata={
                "arbiter_decision": "cancel",
                "target_task_id": target,
            },
        )

        # Set cancel flags FIRST (direct, not bus-mediated)
        # M5 E5.5.3: Ledger BEFORE mutation (M1 1.4.2 pattern)
        task_ids_to_cancel = [target] if target else list(self._active_task_ids)
        for task_id in task_ids_to_cancel:
            if self._ledger is not None:
                try:
                    from k1.concierge.events.base import from_envelope
                    from k1.concierge.events.task import TaskCancelled

                    meta = from_envelope(envelope, "fsm") if envelope else {"actor": "fsm"}
                    meta["session_id"] = getattr(self._ledger, "session_id", "")
                    meta["task_id"] = task_id
                    cancel_event = TaskCancelled(
                        event_id=meta.get("event_id", ""),
                        session_id=meta.get("session_id", ""),
                        correlation_id=meta.get("correlation_id", ""),
                        causation_id=meta.get("causation_id", ""),
                        parent_event_id=meta.get("parent_event_id", ""),
                        task_id=task_id,
                        actor="fsm",
                        reason="arbiter_cancel",
                        cancel_reason="arbiter",
                    )
                    self._ledger.append_sync(cancel_event)
                except Exception:
                    logger.debug("_handle_arbiter_cancel: ledger write failed", exc_info=True)
            self._cancel_handler.request_cancel(task_id)
            self._suspension_manager.cleanup_task(task_id)

        # Transition to CANCELLING BEFORE publishing events
        self._transition(
            ConciergeState.CANCELLING,
            TOPIC_TASK_CANCEL,
            envelope,
        )

        # Publish task.cancel events for observability (bus capture / ledger).
        # _on_task_cancel will dead-letter these from CANCELLING state -- harmless.
        for task_id in task_ids_to_cancel:
            self._bus.publish(
                build_task_cancel(
                    payload={"task_id": task_id},
                    parent_id=envelope.envelope_id,
                )
            )

    # ------------------------------------------------------------------
    # M5 E5.2.3: Arbiter MODIFY_INFLIGHT handler
    # ------------------------------------------------------------------

    def _handle_arbiter_modify(
        self,
        envelope: Envelope,
        text: str,
        arbiter_result: Any,
    ) -> None:
        """Handle MODIFY_INFLIGHT decision from Arbiter.

        Emits task.modify for observability. If a RunningTaskHandle with
        a registered messages list exists for the target task, injects a
        synthetic PARAMETER UPDATE message into the mutable list so that
        the next ReAct iteration sees the modification.

        If the task completed before the modify arrives, falls back to
        PARALLEL_NEW (dispatch a new task with the modified intent).

        Does NOT increment turn number or change FSM state when injection
        succeeds. Stays in COMPANIONING.

        Constraint C3: Back reads SS snapshot ONCE at task start.
        Inter-iteration message injection via mutable messages list
        is the correct mechanism -- it does not violate the snapshot
        contract because the modification targets task parameters,
        not beliefs/safety context.
        """
        task_id = arbiter_result.target_task_id
        mods = arbiter_result.modification_params or {}

        # M5 E5.5.4: Check RunningTaskHandle for inter-iteration injection
        handle = self._running_tasks.get(task_id) if task_id else None

        if task_id not in self._active_task_ids:
            # Task completed before modify arrived -- fall back to PARALLEL_NEW
            logger.info(
                "FSM._handle_arbiter_modify: task_id=%s not active, "
                "falling back to PARALLEL_NEW",
                task_id,
            )
            self._handle_arbiter_parallel_new(envelope, text, arbiter_result)
            return

        # Write history (not a turn increment)
        self._write_history(
            entry_type="modify",
            role="user",
            text=text,
            source="user",
            envelope=envelope,
            metadata={
                "arbiter_decision": "modify_inflight",
                "target_task_id": task_id,
                "modifications": mods,
            },
        )

        accepted = False
        if handle is not None and handle.control_queue is not None:
            handle.control_queue.put_nowait(
                BackControlEvent(
                    event_type="parameter_update",
                    task_id=task_id,
                    payload={
                        "source": "arbiter",
                        "modifications": mods,
                        "user_text": text,
                    },
                )
            )
            accepted = True
            logger.info(
                "FSM._handle_arbiter_modify: queued PARAMETER_UPDATE "
                "for task_id=%s (queue_size=%d)",
                task_id,
                handle.control_queue.qsize(),
            )
        else:
            logger.warning(
                "FSM._handle_arbiter_modify: no control queue for task_id=%s; "
                "parameter update could not be accepted",
                task_id,
            )

        # Emit task.modify event for observability/ledger
        from k1.concierge.bus.builders import build_task_modify

        self._bus.publish(
            build_task_modify(
                payload={
                    "task_id": task_id,
                    "modifications": mods,
                    "source": "arbiter",
                    "injected": accepted,
                    "accepted": accepted,
                },
                parent_id=envelope.envelope_id,
            )
        )

        # Stay in COMPANIONING -- no state transition, no turn increment
        logger.info(
            "FSM._handle_arbiter_modify: task_id=%s mods=%s (staying COMPANIONING)",
            task_id,
            list(mods.keys()),
        )

    # ------------------------------------------------------------------
    # M5 E5.2.4: Arbiter DEFER handler
    # ------------------------------------------------------------------

    def _handle_arbiter_defer(
        self,
        envelope: Envelope,
        text: str,
        arbiter_result: Any,
    ) -> None:
        """Handle DEFER decision from Arbiter.

        No LLM call. No turn increment. No state transition. The user's
        input is recorded in history but does not trigger cognitive
        processing. Optionally emits a lightweight ack response.
        """
        # Write history (acknowledgment, not a turn)
        self._write_history(
            entry_type="defer",
            role="user",
            text=text,
            source="user",
            envelope=envelope,
            metadata={"arbiter_decision": "defer"},
        )

        # Optional ack: emit lightweight response.final with is_ack=True
        if self._should_ack_defer():
            self._bus.publish(
                build_final_response(
                    payload={"text": "", "is_ack": True},
                    parent_id=envelope.envelope_id,
                )
            )

        # Stay in COMPANIONING -- no state transition, no turn increment
        logger.info(
            "FSM._handle_arbiter_defer: acknowledged (staying COMPANIONING, envelope_id=%d)",
            envelope.envelope_id,
        )

    def _should_ack_defer(self) -> bool:
        """Check if defer should emit an ack response.

        Returns False by default. Override via config or test injection.
        Emitting an ack while in COMPANIONING would trigger _on_response_final
        which expects specific state transitions, so we default to silent defer.
        """
        return False

    # ------------------------------------------------------------------
    # M5 E5.2.1: Arbiter PARALLEL_NEW handler (preserves current behavior)
    # ------------------------------------------------------------------

    def _handle_arbiter_parallel_new(
        self,
        envelope: Envelope,
        text: str,
        arbiter_result: Any,
    ) -> None:
        """Handle PARALLEL_NEW decision from Arbiter.

        This is the equivalent of the old "chat" path: increment turn,
        write history, INTERRUPT_HANDLING -> DISPATCHING, emit turn.started,
        deliver to Front. Arbiter classification has already run.
        """
        self._turn_number += 1
        self._current_turn_user_text = text
        self._current_turn_assistant_response = ""
        self._write_history(
            entry_type="user",
            role="user",
            text=text,
            source="user",
            envelope=envelope,
            metadata={
                "arbiter_decision": "parallel_new",
                "arbiter_inputs": arbiter_result.inputs.to_metadata(),
            },
        )
        self._transition(
            ConciergeState.INTERRUPT_HANDLING,
            TOPIC_USER_INPUT,
            envelope,
        )
        self._transition(
            ConciergeState.DISPATCHING,
            TRIGGER_INTERRUPT_ROUTED,
            envelope,
        )
        self._bus.publish(
            build_turn_started(
                payload={
                    "turn_number": self._turn_number,
                    "trigger": "interrupt",
                },
                parent_id=envelope.envelope_id,
            )
        )

        # Annotate the user history entry with the arbiter input snapshot.
        if self._history:
            last = self._history[-1]
            if last.entry_type == "user":
                last.metadata.update(arbiter_result.inputs.to_metadata())

        # Enrich envelope with arbiter metadata + interrupt origin marker
        # so determine_mode() can detect the interrupt even though
        # INTERRUPT_HANDLING is a transient state (already DISPATCHING by
        # the time Front reads SS).
        arbiter_result.routing_metadata["interrupt_origin"] = True
        enriched = self._enrich_envelope_with_arbiter(envelope, arbiter_result)

        # Deliver to Front via FrontLock
        if self._front_lock.try_deliver(enriched):
            self._deliver_to_front(enriched)

    # ------------------------------------------------------------------
    # Crisis safety keyword check (replaces UltraBERT RED-band detection)
    # ------------------------------------------------------------------

    # Lightweight regex keywords for life-safety escalation. Matches the
    # former Phase1 `_RED_SAFETY_KEYWORDS` set. Lowercased substring match.
    _CRISIS_KEYWORDS: tuple[str, ...] = (
        "suicide",
        "kill myself",
        "kill yourself",
        "end my life",
        "hurt myself",
        "hurt someone",
        "self-harm",
        "self harm",
        "want to die",
    )

    # Safety band string -> PrivacyBand mapping (used for CRISIS escalation
    # on the Control SessionState section).
    _SAFETY_BAND_MAP: dict[str, PrivacyBand] = {
        "GREEN": PrivacyBand.GREEN,
        "AMBER": PrivacyBand.AMBER,
        "RED": PrivacyBand.RED,
        "CRISIS": PrivacyBand.RED,  # CRISIS maps to RED (highest PrivacyBand)
    }

    def _check_crisis_keywords(self, text: str) -> bool:
        """Return True if ``text`` contains any life-safety crisis keyword."""
        if not text:
            return False
        lower = text.lower()
        return any(kw in lower for kw in self._CRISIS_KEYWORDS)

    def _build_arbiter_input(self, text: str) -> ArbiterInput:
        """Construct a minimal ArbiterInput for the deterministic Arbiter.

        Safety band is derived from the cheap crisis-keyword scan; richer
        semantic signals (intent/domain/affect/entities) are owned by the
        Front LLM via its cognitive tools.
        """
        safety_band = "RED" if self._check_crisis_keywords(text) else "GREEN"
        return ArbiterInput(safety_band=safety_band)

    def _write_session_context_to_ss(self, envelope: Envelope) -> None:
        """Write per-turn session context (temporal anchor + safety band).

        Replaces the former ``_write_phase1_to_ss``. Carries only the
        clock-derived temporal anchor and (when CRISIS keywords match) a
        safety-band escalation on the Control section. All richer
        intent/affect/entity writes are owned by Front LLM cognitive tools.
        """
        if self._ss is None:
            return
        try:
            control = self._ss.get_section("control")
        except Exception:
            logger.debug("_write_session_context_to_ss: control unavailable", exc_info=True)
            return
        if control is None:
            return

        payload = _parse_payload(envelope)
        text = payload.get("text", "") or ""
        safety_band = "RED" if self._check_crisis_keywords(text) else "GREEN"
        prior_safety_band = "GREEN"
        try:
            safety = control.get_safety() if hasattr(control, "get_safety") else None
            band = getattr(safety, "band", "GREEN")
            prior_safety_band = str(getattr(band, "value", band) or "GREEN")
        except Exception:
            prior_safety_band = "GREEN"
        decision = self._write_elision_gate.evaluate(
            {
                "intent_class": (
                    "backchannel"
                    if text.strip().lower() in {"ok", "okay", "thanks", "thank you"}
                    else "general"
                ),
                "safety_band": safety_band,
                "prior_safety_band": prior_safety_band,
                "beliefs": [],
                "affect_label": "neutral",
                "affect_detected": False,
                "temporal_anchor": True,
            }
        )
        if decision.elided_sections:
            logger.debug(
                "_write_session_context_to_ss: elided_sections=%s reason=%s",
                sorted(decision.elided_sections),
                decision.reason,
            )

        # Temporal anchor (skeleton.mmd -> TIME_RESOLUTION). Reads tz from
        # Persona preferences if available, falls back to UTC.
        tz_name = "UTC"
        try:
            persona = self._ss.get_section("persona")
            if persona is not None and hasattr(persona, "get_all_preferences"):
                prefs = persona.get_all_preferences()
                tz_name = prefs.get("timezone", "UTC") or "UTC"
        except Exception:
            pass
        try:
            anchor = compute_temporal_anchor(tz_name)
            if hasattr(control, "set_temporal_anchor"):
                control.set_temporal_anchor(anchor.to_dict())
        except Exception:
            logger.debug("_write_session_context_to_ss: temporal anchor failed", exc_info=True)

        # Crisis-band escalation (kernel keyword check; LLM-derived nuance
        # comes via cognitive tools later in the turn).
        if self._check_crisis_keywords(text):
            try:
                control.escalate_safety(
                    band=PrivacyBand.RED,
                    reason="crisis_keyword_match",
                )
            except Exception:
                logger.debug(
                    "_write_session_context_to_ss: crisis escalation failed",
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # M5 E5.3.1/5.3.2: Route normal user turn via Arbiter
    # ------------------------------------------------------------------

    def _route_user_turn(self, envelope: Envelope, text: str, *, device_id: str = "") -> None:
        """Route LISTENING/CLARIFYING_USER turns through the Arbiter.

        Replaces the former ``_run_phase1`` + ``_run_phase1_with_arbiter``
        pair. The Arbiter receives a minimal ArbiterInput (safety band
        only); richer semantics are derived by the Front LLM in-loop.

        Steps:
          1. Write session context (temporal anchor, crisis escalation)
          2. Build ArbiterInput (crisis -> RED)
          3. Short-circuit on crisis (canned response, no LLM)
          4. Build inflight context snapshot
          5. Arbiter classify
          6. Emit intent.arbitrated
          7. Record ledger entry
          8. Enrich envelope; deliver to Front
        """
        logger.info(
            "FSM._route_user_turn: envelope_id=%d state=%s",
            envelope.envelope_id,
            self._state.name,
        )

        # 1. Session context writes (temporal anchor; crisis-band escalation)
        self._write_session_context_to_ss(envelope)

        # 2/3. Crisis short-circuit (cheap regex match, no LLM dispatch)
        inputs = self._build_arbiter_input(text)
        if inputs.safety_band == "RED":
            logger.critical(
                "Crisis keyword detected, skipping LLM dispatch (envelope_id=%d)",
                envelope.envelope_id,
            )
            self._deliver_crisis_response(envelope)
            return

        # 4. Build inflight context (M5 E5.4.1: device_id)
        inflight = build_inflight_context(
            ss=self._ss,
            suspension_manager=self._suspension_manager,
            cancel_handler=self._cancel_handler,
            turn_state=self._turn_state,
            current_turn=self._turn_number,
            device_id=device_id or None,
            back_pool=self._back_pool,
        )

        # 5. Arbiter classification (deterministic, no LLM)
        arbiter_result = self._arbiter.classify(text, inputs, inflight)

        # Annotate user history entry with arbiter snapshot
        if self._history:
            last = self._history[-1]
            if last.entry_type == "user":
                last.metadata.update(inputs.to_metadata())
                last.metadata["arbiter"] = arbiter_result.to_dict()

        # 6. Emit intent.arbitrated BEFORE delivering to Front
        self._bus.publish(
            build_intent_arbitrated(
                payload={
                    "decision": arbiter_result.decision.value,
                    "confidence": arbiter_result.confidence,
                    "target_task_id": arbiter_result.target_task_id,
                    "intent_class": inputs.intent_classification,
                    "domain": inputs.domain_context,
                    "safety_band": inputs.safety_band,
                    "inflight_task_count": len(inflight.tasks),
                    "routing_metadata": arbiter_result.routing_metadata,
                },
                parent_id=envelope.envelope_id,
            )
        )

        # 7. Record IntentArbitrated in ledger
        self._emit_intent_arbitrated_ledger(
            arbiter_result,
            inflight,
            envelope,
            device_id,
        )

        # 8. Enrich envelope with arbiter metadata; deliver via FrontLock
        enriched = self._enrich_envelope_with_arbiter(envelope, arbiter_result)
        if self._front_lock.try_deliver(enriched):
            self._deliver_to_front(enriched)

    def _enrich_envelope_with_arbiter(
        self, envelope: Envelope, arbiter_result: ArbiterResult
    ) -> Envelope:
        """Build a new envelope with Arbiter metadata merged into payload.

        M5 E5.3.2: Front can read arbiter_decision, routing_metadata,
        and safety_band from the enriched payload.

        M8 E8.5.4: Injects async_results_context from deferred results
        so the Front STANDARD prompt can weave background task results
        into the conversational response.
        """
        payload = _parse_payload(envelope)
        payload["arbiter_decision"] = arbiter_result.decision.value
        payload["routing_metadata"] = arbiter_result.routing_metadata
        payload["safety_band"] = arbiter_result.inputs.safety_band

        # M8 E8.5.4: Inject deferred async results context so Front LLM
        # can weave background task results into conversational response.
        if self._async_results_context:
            payload["async_results_context"] = self._async_results_context
            self._async_results_context = ""  # Clear after injection
        return Envelope(
            topic=envelope.topic,
            envelope_id=envelope.envelope_id,
            priority=envelope.priority,
            sequence=envelope.sequence,
            cognitive_trace_id=envelope.cognitive_trace_id,
            session_id=envelope.session_id,
            request_id=envelope.request_id,
            parent_id=envelope.parent_id,
            created_ns=envelope.created_ns,
            payload=json.dumps(payload).encode(),
            ttl_ms=envelope.ttl_ms,
            payload_format=1,  # JSON
        )

    def _deliver_to_front(self, envelope: Envelope) -> None:
        """Deliver an envelope to the Front LLM actor via MailboxRouter.

        This is point-to-point delivery, not pub/sub.
        """
        logger.info(
            "FSM._deliver_to_front: envelope_id=%d topic=%s state=%s",
            envelope.envelope_id,
            envelope.topic,
            self._state.name,
        )
        # Signal WeaveBatcher that Front is busy (queues arrivals)
        if self._weave_batcher is not None:
            self._weave_batcher.set_front_busy(True)
        try:
            self._router.deliver(ACTOR_FRONT, envelope)
        except Exception:
            logger.exception(
                "Failed to deliver to front_half: topic=%s, envelope_id=%d",
                envelope.topic,
                envelope.envelope_id,
            )

    def _deliver_to_back(self, envelope: Envelope) -> None:
        """Deliver an envelope to the Back LLM actor via MailboxRouter.

        M3 E3.1.4: The envelope.topic MUST be preserved so that
        route_back_envelope can dispatch to the correct handler.
        """
        # M3 E3.1.4 guard: topic must be set for route_back_envelope routing
        if not getattr(envelope, "topic", None):
            logger.error(
                "FSM._deliver_to_back: envelope has NO topic! envelope_id=%d -- "
                "route_back_envelope will drop this envelope",
                envelope.envelope_id,
            )
        logger.info(
            "FSM._deliver_to_back: envelope_id=%d topic=%s state=%s",
            envelope.envelope_id,
            envelope.topic,
            self._state.name,
        )
        try:
            self._router.deliver(ACTOR_BACK, envelope)
        except Exception:
            logger.exception(
                "Failed to deliver to back_half: topic=%s, envelope_id=%d",
                envelope.topic,
                envelope.envelope_id,
            )

    def _drop_queued_front_hitl_for_task(self, task_id: str) -> int:
        """Remove stale queued Front HIL events for a task that moved on."""
        if not task_id or not self._front_lock.event_queue:
            return 0
        kept: deque[tuple[int, Envelope]] = deque()
        dropped = 0
        for priority, queued in self._front_lock.event_queue:
            should_drop = False
            if queued.topic in (TOPIC_TASK_SUSPENDED, TOPIC_HIL_REQUEST):
                payload = _parse_payload(queued)
                if queued.topic == TOPIC_TASK_SUSPENDED:
                    should_drop = str(payload.get("task_id", "") or "") == task_id
                else:
                    inner_payload = payload.get("payload")
                    inner = inner_payload if isinstance(inner_payload, dict) else {}
                    hil_request_id = str(payload.get("hil_request_id", "") or "")
                    bound_task_id = str(inner.get("task_id", "") or "")
                    synthetic_task_id = f"hil:{hil_request_id}" if hil_request_id else ""
                    should_drop = task_id in {bound_task_id, synthetic_task_id}
            if should_drop:
                dropped += 1
                continue
            kept.append((priority, queued))
        if dropped:
            self._front_lock.event_queue = kept
            logger.info(
                "FSM: dropped %d stale queued HIL Front events for task_id=%s",
                dropped,
                task_id,
            )
        return dropped

    def _cleanup_terminal_hitl_state(self, task_id: str) -> None:
        """Clear pending HIL presentation state once a task is terminal."""
        if not task_id:
            return
        self._pending_hil_subtasks.pop(task_id, None)
        self._hitl_responded_tasks.pop(task_id, None)
        self._drop_queued_front_hitl_for_task(task_id)
        try:
            self._task_bridge.set_pending_hil_data(task_id, None)
        except Exception:
            logger.debug("FSM: pending HIL cleanup skipped for %s", task_id, exc_info=True)

    def _deliver_crisis_response(self, envelope: Envelope) -> None:
        """Emit a canned safety-protocol response without invoking Front LLM.

        M10 E10.3.3: CRISIS safety band detected by Phase 1. We skip
        the LLM entirely and return a hard-coded crisis-response message.
        """
        crisis_text = (
            "I noticed something in your message that concerns me. "
            "If you or someone you know is in immediate danger, please "
            "call emergency services (911) or the 988 Suicide & Crisis "
            "Lifeline (call or text 988). I am here to listen whenever "
            "you are ready."
        )
        final_env = build_final_response(
            payload={
                "text": crisis_text,
                "source": "crisis_protocol",
                "safety_band": "CRISIS",
            },
            parent_id=envelope.envelope_id,
        )
        final_env = _correlate_envelope(final_env, envelope)
        self._bus.publish(final_env)
        logger.info(
            "FSM._deliver_crisis_response: canned response emitted (envelope_id=%d)",
            envelope.envelope_id,
        )

    def _on_task_dispatch(self, envelope: Envelope) -> None:
        """Handle k1.orchestration.task.dispatch.v1 emitted by Front LLM.

        Front dispatched a task for Back LLM. Register task, transition
        to COMPANIONING, and route through the single dispatch authority
        based on complexity tier (Epic 6.1, V2 Section 11.2).

        Routing:
            LOW    -> deliver to Back directly (ReAct loop)
            MEDIUM -> deliver to Back with expanded budget/tools
            HIGH   -> emit task.failed (not implemented in POC)
        """
        # M2 E2.1.2: Guard gate
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "task_dispatch_invalid_state")
            return

        payload = _parse_payload(envelope)
        dispatch = _task_dispatch_from_payload(payload)
        trace_id = envelope.cognitive_trace_id or str(payload.get("trace_id", "") or "")
        session_id = envelope.session_id or str(payload.get("session_id", "") or "")
        setattr(dispatch, "trace_id", trace_id)
        setattr(dispatch, "session_id", session_id)
        task_id = dispatch.task_id
        tier = dispatch.tier
        logger.info(
            "FSM._on_task_dispatch: state=%s envelope_id=%d task_id=%s tier=%s",
            self._state.name,
            envelope.envelope_id,
            task_id,
            tier.value,
        )

        # Register task
        self._active_task_ids.add(task_id)
        self._task_dispatch_turns[task_id] = self._turn_number
        self._cancel_handler.register_task(task_id)
        self._control_ext.add_active_task(task_id)
        action = dispatch.intents[0].action if dispatch.intents else ""
        self._task_bridge.dispatch_task(task_id, action)
        self._running_tasks[task_id] = RunningTaskHandle(
            task_id=task_id,
            messages=None,
            control_queue=None,
            dispatch_payload=payload,
            started_at=time.monotonic(),
        )

        # Transition to COMPANIONING (idempotent: skip if already there)
        if self._state != ConciergeState.COMPANIONING:
            self._transition(
                ConciergeState.COMPANIONING,
                TOPIC_TASK_DISPATCH,
                envelope,
            )
        else:
            logger.info(
                "FSM._on_task_dispatch: already COMPANIONING, skipping "
                "transition for task_id=%s (multi-dispatch in same turn)",
                task_id,
            )

        # Route by tier via authoritative orchestrator router (Section 11.2)
        self._route_via_orchestrator(envelope, dispatch)

        logger.info(
            "Task dispatched: task_id=%s tier=%s active_tasks=%d",
            task_id,
            tier.value,
            len(self._active_task_ids),
        )

    def _route_via_orchestrator(self, envelope: Envelope, dispatch: TaskDispatch) -> None:
        """Route task via orchestrator.router single dispatch authority.

        Uses `route_task_sync()` (shared logic with async route_task) so FSM,
        tests, and orchestrator module all follow one routing decision path.

        Builds a fresh dispatch envelope with the canonical task_id so the
        back handler always receives a clean payload regardless of
        TimingChain re-entrant delivery order.
        """
        record = route_task_sync(dispatch, dispatch.tier)

        # M10 E10.3.2: HIGH tier path.
        #
        # When a real Orchestrator is wired (production / kernel-managed
        # sessions), keep the HIGH tier and let the orchestrator drive
        # the planner via _dispatch_high. The orchestrator translates
        # the envelope and the planner pipeline (SKETCH/EXPAND/VALIDATE/
        # COMMIT) produces a CommittedPlan that the orchestrator then
        # executes via DAGExecutor.
        #
        # Without an orchestrator (legacy/test contexts), fall back to
        # the PassthroughPlannerStub: wrap the single intent as a
        # 1-step plan and re-route as MEDIUM so the existing direct
        # fabric path can serve it.
        if record.tier == ComplexityTier.HIGH and self._orchestrator is None:
            if not self._allow_planner_passthrough:
                # M16.E1.I3: production-strict path. Surface the missing
                # orchestrator loudly instead of silently collapsing the
                # HIGH task into a 1-step MEDIUM plan via the legacy
                # PassthroughPlannerStub. Publish task.failed so the
                # FSM/Front observe a deterministic failure, then raise
                # so boot smoke tests catch the misconfiguration.
                logger.error(
                    "FSM._route_via_orchestrator: HIGH tier requested but no "
                    "orchestrator is wired and allow_planner_passthrough=False; "
                    "task_id=%s",
                    dispatch.task_id,
                )
                try:
                    fail_env = build_task_failed(
                        payload={
                            "task_id": dispatch.task_id,
                            "reason": "orchestrator_not_wired",
                            "error_code": "ORCH_NOT_WIRED",
                            "error_message": (
                                "HIGH-tier dispatch requires an OrchestratorService; "
                                "none is attached and PassthroughPlannerStub fallback "
                                "is disabled (allow_planner_passthrough=False)."
                            ),
                        },
                        parent_id=envelope.envelope_id,
                    )
                    self._bus.publish(fail_env)
                except Exception:  # pragma: no cover - defensive
                    logger.exception("FSM._route_via_orchestrator: failed to publish task.failed")
                raise OrchestratorNotWired(
                    f"HIGH-tier dispatch task_id={dispatch.task_id!r} has no "
                    "orchestrator wired and allow_planner_passthrough=False"
                )
            logger.info(
                "FSM._route_via_orchestrator: HIGH tier -> PassthroughPlannerStub for task_id=%s",
                dispatch.task_id,
            )
            # Wrap single intent as 1-step plan (real Planner is a later milestone)
            plan_step = {
                "intent": dispatch.intents[0].to_dict() if dispatch.intents else {},
                "step_id": f"step-{dispatch.task_id}",
            }
            dispatch_dict = dispatch.to_dict()
            dispatch_dict["committed_plan"] = {
                "task_id": dispatch.task_id,
                "steps": [plan_step],
            }
            dispatch_dict["original_tier"] = "HIGH"
            # Fall through to MEDIUM routing logic by re-routing
            record = route_task_sync(dispatch, ComplexityTier.MEDIUM)

        # Build a canonical dispatch envelope with task_id guaranteed
        canonical_payload = dispatch.to_dict()
        canonical_payload["task_id"] = dispatch.task_id
        if getattr(dispatch, "trace_id", ""):
            canonical_payload["trace_id"] = getattr(dispatch, "trace_id")
        if getattr(dispatch, "session_id", ""):
            canonical_payload["session_id"] = getattr(dispatch, "session_id")

        # Inject scoreboard referents if Front didn't include them.
        # This is the fallback mechanism (Section 6.2): even if the LLM
        # didn't populate reference_context, Back gets the resolved
        # pronoun map so "do it" / "the cheaper one" can be resolved.
        if not canonical_payload.get("reference_context") and self._ss:
            try:
                scoreboard = self._ss.get_section("scoreboard")
                if scoreboard and hasattr(scoreboard, "list_referents"):
                    referents = scoreboard.list_referents()
                    if referents:
                        canonical_payload["reference_context"] = {
                            r.text: r.entity_id for r in referents if r.text and r.entity_id
                        }
            except Exception:
                logger.debug("FSM: failed to inject scoreboard referents", exc_info=True)

        # Inject narrative thread name so Back knows the conversation
        # context (Gap 5, Section 5.1). Helps Back avoid topic drift.
        if not canonical_payload.get("narrative_thread") and self._ss:
            try:
                narrative = self._ss.get_section("narrative_active")
                if narrative and hasattr(narrative, "get_active_thread_name"):
                    thread_name = narrative.get_active_thread_name()
                    if thread_name:
                        canonical_payload["narrative_thread"] = thread_name
            except Exception:
                logger.debug("FSM: failed to inject narrative thread", exc_info=True)

        canonical_env = build_task_dispatch(
            payload=canonical_payload,
            parent_id=envelope.envelope_id,
        )
        canonical_env = _correlate_envelope(canonical_env, envelope)

        if record.tier in (ComplexityTier.MEDIUM, ComplexityTier.HIGH):
            if self._orchestrator is None or record.envelope is None:
                logger.warning(
                    "FSM._route_via_orchestrator: %s tier fallback to Back (orchestrator unavailable), task_id=%s",
                    record.tier.value,
                    dispatch.task_id,
                )
                self._deliver_to_back(canonical_env)
                return

            logger.info(
                "FSM._route_via_orchestrator: routing %s tier task_id=%s via OrchestratorStub",
                record.tier.value,
                dispatch.task_id,
            )
            asyncio.create_task(
                self._run_medium_orchestration(record.envelope, envelope.envelope_id)
            )
            return

        # LOW tier: deliver canonical envelope to Back via MailboxRouter.
        logger.info(
            "FSM._route_via_orchestrator: routing %s tier task_id=%s to Back",
            record.tier.value,
            dispatch.task_id,
        )
        self._deliver_to_back(canonical_env)

    async def _run_medium_orchestration(
        self,
        task_envelope: Any,
        parent_envelope_id: int,
    ) -> None:
        """Execute MEDIUM-tier task through OrchestratorStub.

        Orchestrator emits acceptance/completion events. If orchestration raises,
        emit task.failed so the FSM and Front present a deterministic failure.
        """
        if self._orchestrator is None:
            return

        try:
            await self._orchestrator.handle_task(task_envelope)
        except Exception as exc:
            logger.exception(
                "FSM._run_medium_orchestration: orchestrator failed for task_id=%s",
                getattr(task_envelope, "task_id", ""),
            )
            env = build_task_failed(
                payload={
                    "task_id": getattr(task_envelope, "task_id", ""),
                    "reason": "orchestrator_error",
                    "error_code": "ORCH_MEDIUM_FAILED",
                    "error_message": str(exc),
                },
                parent_id=parent_envelope_id,
            )
            self._bus.publish(env)

    def _on_dag_completed(self, envelope: Envelope) -> None:
        """Normalize orchestrator dag-complete event into task.complete.v1.

        Supports both topic variants:
          - k1.orchestration.dag.completed.v1
          - k1.orchestration.dag.completed
        """
        # M2 E2.1.2: Guard gate
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "dag_completed_invalid_state")
            return

        payload = _parse_payload(envelope)
        task_id = payload.get("task_id", "")
        if not task_id:
            logger.warning(
                "FSM._on_dag_completed: missing task_id in payload for envelope_id=%d",
                envelope.envelope_id,
            )
            return

        success = bool(payload.get("success", True))
        if success:
            env = build_task_complete(
                payload={
                    "task_id": task_id,
                    "result_type": "complete",
                    "final_answer": payload.get("summary", ""),
                    "results": payload.get("step_results", []),
                    "artifacts_created": payload.get("artifacts_created", []),
                },
                parent_id=envelope.envelope_id,
            )
            self._bus.publish(env)
            return

        env = build_task_failed(
            payload={
                "task_id": task_id,
                "reason": "orchestrator_failed",
                "error_code": "ORCH_DAG_FAILED",
                "partial_results": payload.get("step_results", []),
            },
            parent_id=envelope.envelope_id,
        )
        self._bus.publish(env)

    def _on_task_complete(self, envelope: Envelope) -> None:
        """Handle k1.orchestration.task.complete.v1 emitted by Back LLM.

        M8 E8.5.2: Canonical 12-step ordering replacing static state-based
        routing with WeavePolicy adaptive decisions.

        Steps:
            1. Cancel dedup
            2. Same-turn suppression
            3. M7: Release worker + lease (BackPool)
            4. M4: TaskBridge sync
            5. M7: ReadyQueue notification
            6. M5: Remove RunningTaskHandle
            7. M8: Enqueue result with urgency metadata
            8. M8: Collect WeaveSignal (reads pool AFTER release)
            9. M8: WeavePolicy decision (with fallback)
            10. M8: Emit weave.decided.v1 event
            11. M8: Branch on decision (IMMEDIATE/BATCH/DEFER/DIGEST/SUPPRESS)
            12. M7: Auto-dispatch dependent tasks from ReadyQueue

        Critical: BackPool.release_worker (step 3) runs BEFORE WeaveSignal
        collection (step 8) to ensure signal sees post-completion pool state.

        Falls back to pre-M8 state-based routing when _weave_policy is None.
        """
        # M2 E2.3.3: Topic guard
        if not self._topic_guard(envelope, TOPIC_TASK_COMPLETE):
            return

        # M2 E2.3.2: Idempotency check for task lifecycle
        if not self._idempotency.check_and_mark(envelope.envelope_id, self._turn_number):
            logger.debug("Duplicate envelope_id=%d, skipping", envelope.envelope_id)
            return

        payload = _parse_payload(envelope)
        task_id = payload.get("task_id", "")
        logger.info(
            "FSM._on_task_complete: state=%s envelope_id=%d task_id=%s",
            self._state.name,
            envelope.envelope_id,
            task_id,
        )

        # M2 E2.1.2: Guard gate (after topic guard)
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "task_complete_invalid_state")
            return

        # === Step 1: Cancel dedup via CancellationHandler (SOT) ===
        if self._cancel_handler.is_cancelled(task_id):
            logger.info("task.complete for cancelled task %s -- discarding", task_id)
            self._cancel_handler.handle_late_completion(task_id)
            self._discard_task_result_ownership(task_id)
            self._active_task_ids.discard(task_id)
            self._task_dispatch_turns.pop(task_id, None)
            self._control_ext.remove_active_task(task_id)
            self._remove_running_task(task_id)  # M5 E5.5.4
            return

        dispatch_turn = self._task_dispatch_turns.get(task_id, 0)

        # === Step 2: Same-turn suppression ===
        # When a task completes in the same turn it was dispatched, the
        # Front STANDARD response already covered the user's request.
        # Instead of discarding the result, we store it as a deferred
        # proactive result so the next user input will include it as
        # background context (via _check_deferred_results_on_input).
        if dispatch_turn == self._turn_number and self._state == ConciergeState.COMPANIONING:
            logger.info(
                "FSM._on_task_complete: same-turn completion for task_id=%s "
                "(dispatched_turn=%d, current_turn=%d) -- deferring result "
                "for proactive delivery on next user input",
                task_id,
                dispatch_turn,
                self._turn_number,
            )
            self._active_task_ids.discard(task_id)
            self._task_dispatch_turns.pop(task_id, None)
            self._control_ext.remove_active_task(task_id)
            self._remove_running_task(task_id)
            self._task_bridge.complete_task(task_id)
            self._suspension_manager.cleanup_task(task_id)
            self._cleanup_terminal_hitl_state(task_id)

            # BUG-1 FIX: Release BackPool worker on same-turn completion.
            # Without this, the worker slot leaks permanently.
            if self._back_pool is not None and hasattr(self._back_pool, "release_worker"):
                try:
                    self._back_pool.release_worker(task_id, reason="completed")
                except Exception:
                    logger.warning("BackPool.release_worker failed for %s", task_id, exc_info=True)

            if not self._try_chain_into_current_response(task_id, payload, envelope):
                # Store result as deferred so proactive delivery can happen
                # on the next user interaction via _check_deferred_results_on_input.
                deferred_item = {
                    "task_id": task_id,
                    "result": payload,
                    "envelope_id": envelope.envelope_id,
                    "urgency": self._get_task_urgency(task_id),
                    "defer_count": 0,
                    "source": "same_turn_completion",
                }
                evicted = self._turn_state.defer_result(deferred_item)
                if evicted is not None:
                    self._turn_state.pending_results.append(evicted)
                logger.info(
                    "FSM._on_task_complete: stored deferred proactive result "
                    "for task_id=%s (deferred_count=%d)",
                    task_id,
                    len(self._turn_state.deferred_results),
                )

            if not self._active_task_ids:
                self._transition(
                    ConciergeState.LISTENING,
                    TRIGGER_SAME_TURN_COMPLETE,
                    envelope,
                )
                self._finalize_turn(envelope)
                # BUG-6 FIX: Schedule proactive delivery for deferred results.
                # Without this, deferred same-turn completions sit silently
                # until the user sends a new message.  The 2-second delay
                # gives time for any additional tasks to complete and batch.
                self._schedule_deferred_proactive_delivery(envelope)
            return

        # === Step 3: M7 BackPool release (BEFORE signal collection) ===
        # Releasing before signal ensures signal.backpool_utilization
        # reflects post-completion pool state.
        if self._back_pool is not None and hasattr(self._back_pool, "release_worker"):
            try:
                self._back_pool.release_worker(task_id, reason="completed")
            except Exception:
                logger.warning("BackPool.release_worker failed for %s", task_id, exc_info=True)

        # === Step 4: M4 TaskBridge sync ===
        self._active_task_ids.discard(task_id)
        self._control_ext.remove_active_task(task_id)
        self._write_history(
            entry_type="task_complete",
            role="system",
            text=payload.get("action", ""),
            source="back",
            task_id=task_id,
            envelope=envelope,
            metadata={
                "result_type": payload.get("result_type", "complete"),
                "tool_calls": payload.get("tool_call_summaries", []),
            },
        )
        self._task_bridge.complete_task(task_id)
        self._suspension_manager.cleanup_task(task_id)
        self._cleanup_terminal_hitl_state(task_id)
        self._task_dispatch_turns.pop(task_id, None)

        # === Step 5: M7 ReadyQueue notification ===
        # (ReadyQueue integration is M7 -- placeholder for dependency ordering)

        # === Step 6: M5 Remove RunningTaskHandle ===
        self._remove_running_task(task_id)

        # === M8 Adaptive Path (when WeavePolicy is wired) ===
        if self._weave_policy is not None:
            self._on_task_complete_adaptive(envelope, payload, task_id)
            return

        # === Pre-M8 fallback: state-based routing (unchanged) ===
        self._on_task_complete_legacy(envelope, payload, task_id)

    def _on_task_complete_adaptive(
        self,
        envelope: Envelope,
        payload: dict[str, Any],
        task_id: str,
    ) -> None:
        """M8 E8.5.2 steps 7-12: Adaptive weave policy path.

        Called from _on_task_complete when _weave_policy is wired.
        """
        # === Step 7: Enqueue result with urgency metadata (8.1.4) ===
        urgency = self._get_task_urgency(task_id)
        evicted = self._turn_state.enqueue_result(task_id, payload, envelope, urgency=urgency)
        if evicted:
            self._publish_dead_letter(envelope, "overflow")

        # === Step 8: Collect WeaveSignal (reads pool AFTER release) ===
        signal = self._collect_weave_signal(task_id)

        # === Step 9: WeavePolicy decision (with fallback) ===
        decision, fallback_used = self._decide_weave_with_fallback(signal)

        # === Step 10: Emit weave.decided.v1 event (8.2.4) ===
        self._emit_weave_decided(decision, envelope, signal, fallback_used=fallback_used)

        # === Step 10b: OPP-8 Delivery Strategy (natural flow) ===
        delivery_decision = None
        if self._opp_pipeline is not None:
            dispatch_turn = self._task_dispatch_turns.get(task_id, 0)
            delivery_decision = self._opp_pipeline.on_task_complete(
                result=payload,
                fsm_state=self._state.name,
                active_dispatch_task_ids=frozenset(self._active_task_ids),
                current_turn=self._turn_number,
                dispatch_turn=dispatch_turn,
                has_expiry=bool(payload.get("expiry")),
                is_chained=bool(payload.get("depends_on")),
                ss=self._ss,
                result_domain=payload.get("domain", ""),
                emotional_gate=(
                    signal.emotional_gate if hasattr(signal, "emotional_gate") else "open"
                ),
                weave_decision=decision,
            )
            logger.info(
                "FSM._on_task_complete_adaptive: OPP-8 delivery=%s class=%s reason=%s",
                delivery_decision.delivery_mode,
                delivery_decision.result_class,
                delivery_decision.reasoning[:60] if delivery_decision.reasoning else "",
            )

        # === Step 11: Branch on decision ===
        logger.info(
            "FSM._on_task_complete_adaptive: task=%s decision=%s window=%dms reason=%s",
            task_id,
            decision.decision.name,
            decision.window_ms,
            decision.reasoning[:80],
        )

        self._apply_weave_decision(decision, task_id, envelope)

        # === Step 12: M7 auto-dispatch dependent tasks ===
        # (ReadyQueue dependency ordering -- M7 wiring placeholder)

    def _on_task_complete_legacy(
        self,
        envelope: Envelope,
        payload: dict[str, Any],
        task_id: str,
    ) -> None:
        """Pre-M8 state-based routing fallback (unchanged behavior)."""
        if self._state == ConciergeState.LISTENING:
            self._proactive_wake.record_wake(task_id)
            self._transition(
                ConciergeState.PROACTIVE_WAKE,
                TOPIC_TASK_COMPLETE,
                envelope,
            )
            self._transition(
                ConciergeState.DELIVERING,
                TRIGGER_PROACTIVE_ROUTED,
                envelope,
            )
            if self._front_lock.try_deliver(envelope):
                self._deliver_to_front(envelope)
            return

        if self._state in (
            ConciergeState.COMPANIONING,
            ConciergeState.PROGRESSING,
        ):
            self._transition(
                ConciergeState.DELIVERING,
                TOPIC_TASK_COMPLETE,
                envelope,
            )
            if self._front_lock.try_deliver(envelope):
                self._deliver_to_front(envelope)
            else:
                evicted = self._turn_state.enqueue_result(
                    task_id,
                    payload,
                    envelope,
                )
                if evicted:
                    self._publish_dead_letter(envelope, "overflow")
            return

        evicted = self._turn_state.enqueue_result(task_id, payload, envelope)
        if evicted:
            self._publish_dead_letter(envelope, "overflow")
        logger.debug(
            "task.complete queued in pending_results: task_id=%s, state=%s",
            task_id,
            self._state.name,
        )

    def _on_task_failed(self, envelope: Envelope) -> None:
        """Handle k1.orchestration.task.failed.v1 emitted by Back LLM.

        Payload: task_id, reason ("error"|"timeout"|"cancelled"),
        error_message, duration_ms.
        """
        # M2 E2.3.2: Idempotency check for task lifecycle
        if not self._idempotency.check_and_mark(envelope.envelope_id, self._turn_number):
            logger.debug("Duplicate envelope_id=%d, skipping", envelope.envelope_id)
            return

        # M2 E2.1.2: Guard gate
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "task_failed_invalid_state")
            return

        payload = _parse_payload(envelope)
        task_id = payload.get("task_id", "")
        reason = payload.get("reason", "error")
        logger.info(
            "FSM._on_task_failed: state=%s envelope_id=%d task_id=%s reason=%s",
            self._state.name,
            envelope.envelope_id,
            task_id,
            reason,
        )

        self._active_task_ids.discard(task_id)
        self._task_dispatch_turns.pop(task_id, None)
        self._control_ext.remove_active_task(task_id)
        self._remove_running_task(task_id)  # M5 E5.5.4
        # M3 E3.3.5: Clean up suspension context on terminal state
        self._suspension_manager.cleanup_task(task_id)

        # M4 E4.5.1: Ledger write BEFORE TaskBridge mutation
        self._write_history(
            entry_type="error" if reason != "cancelled" else "cancel_confirmed",
            role="system",
            text=payload.get("error_message", ""),
            source="back",
            task_id=task_id,
            envelope=envelope,
        )

        if reason == "cancelled":
            was_expected = self._cancel_handler.confirm_cancel(task_id)
            self._task_bridge.cancel_task(task_id)
            if was_expected:
                logger.info("Cancel confirmed for task %s", task_id)
            else:
                logger.warning(
                    "task.failed(cancelled) for unknown cancel: task %s",
                    task_id,
                )
        else:
            self._task_bridge.fail_task(task_id)

        # Guard: only transition to DELIVERING from states where
        # task.failed is a legal trigger (COMPANIONING, PROGRESSING,
        # CANCELLING).  If the FSM moved on (e.g. DISPATCHING for the
        # next turn), queue the failure for later presentation.
        if self._state in (
            ConciergeState.COMPANIONING,
            ConciergeState.PROGRESSING,
            ConciergeState.CANCELLING,
        ):
            self._transition(
                ConciergeState.DELIVERING,
                TOPIC_TASK_FAILED,
                envelope,
            )
            # Deliver to Front for presentation
            if self._front_lock.try_deliver(envelope):
                self._deliver_to_front(envelope)
        else:
            logger.warning(
                "FSM._on_task_failed: state=%s not compatible for "
                "DELIVERING transition, queuing failure for task_id=%s",
                self._state.name,
                task_id,
            )
            self._turn_state.enqueue_result(task_id, payload, envelope)
            # M2 E2.2.3: no overflow check needed -- task_failed is rare

    def _on_task_cancel(self, envelope: Envelope) -> None:
        """Handle k1.orchestration.task.cancel.v1.

        Cancel request from Front. Register in FSMTurnState, transition
        to CANCELLING, deliver cancel to Back.
        """
        # M2 E2.1.2: Guard gate
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "task_cancel_invalid_state")
            return

        payload = _parse_payload(envelope)
        task_id = payload.get("task_id", "")
        logger.info(
            "FSM._on_task_cancel: state=%s envelope_id=%d task_id=%s",
            self._state.name,
            envelope.envelope_id,
            task_id,
        )

        self._cancel_handler.request_cancel(task_id)
        self._discard_task_result_ownership(task_id)

        # M3 E3.3.5: Clean up suspension context on cancel
        self._suspension_manager.cleanup_task(task_id)

        # M2 E2.1.3: Use _transition() instead of forced state assignment.
        # TASK_CANCEL transitions are now in TRANSITION_TABLE for
        # COMPANIONING, PROGRESSING, and DISPATCHING -> CANCELLING.
        if self._state in (
            ConciergeState.COMPANIONING,
            ConciergeState.PROGRESSING,
            ConciergeState.DISPATCHING,
        ):
            self._transition(
                ConciergeState.CANCELLING,
                TOPIC_TASK_CANCEL,
                envelope,
            )

        # Deliver cancel to Back
        self._deliver_to_back(envelope)

    def _on_task_suspended(self, envelope: Envelope) -> None:
        """Handle k1.orchestration.task.suspended.v1 (HITL entry point).

        **E4 HIL Unification — crash-recovery / legacy path only.**
        Live `needs_human` requests are now resolved in-process inside
        `back_handler` via `IHILPort.needs_human()` (see
        `_resolve_needs_human_in_process`). This handler exists to
        service the residual flows:

        - Kernel-restart crash recovery: HumanInTheLoopService.needs_human
          persists the suspension to SQLite BEFORE publishing the request
          envelope; on restart the suspension is replayed and
          back_resume_handler picks up via TOPIC_TASK_RESUME.
        - Legacy tests / fixtures that still publish TOPIC_TASK_SUSPENDED
          directly.
        - Back fallbacks when no `_hil_port` is wired or `needs_human`
          times out / hits round budget — back_handler falls back to
          publishing TOPIC_TASK_SUSPENDED so observers still see a
          suspended trail.

        Back needs human input. Transition to CLARIFYING_WORKER and
        deliver to Front for natural language translation of the HIL request.

        When an HILCoordinator is wired, this handler delegates limit
        enforcement (max_rounds) and safety-band escalation to it.
        Otherwise falls back to bare SuspensionManager.store_context.

        Guard: if FSM is not in COMPANIONING or PROGRESSING, the back
        task finished while the FSM moved on to a new turn. Store the
        suspension context but skip the transition — the HITL question
        will be surfaced when the FSM returns to a compatible state.
        """
        # M2 E2.3.3: Topic guard
        if not self._topic_guard(envelope, TOPIC_TASK_SUSPENDED):
            return

        # M2 E2.3.2: Idempotency check for task lifecycle
        if not self._idempotency.check_and_mark(envelope.envelope_id, self._turn_number):
            logger.debug("Duplicate envelope_id=%d, skipping", envelope.envelope_id)
            return

        payload = _parse_payload(envelope)
        task_id = payload.get("task_id", "")
        logger.info(
            "FSM._on_task_suspended: state=%s envelope_id=%d task_id=%s question=%s",
            self._state.name,
            envelope.envelope_id,
            task_id,
            str(payload.get("question", ""))[:60],
        )

        # M2 E2.1.2: Guard gate (after topic guard)
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "task_suspended_invalid_state")
            return

        # E4.M1.2: legacy `_hil_coordinator` round-budget enforcement removed.
        # Round budget per caller_key now lives in the unified HIL service
        # (HumanInTheLoopService) and is enforced at the call-site that
        # initiates a `needs_human` request -- that responsibility moves to
        # Back/Planner via IHILPort in E5/E6. The FSM's `_on_task_suspended`
        # is a *reactive* handler that routes the suspension event to Front
        # for UI rendering; it no longer counts rounds itself.

        # M6 E6.1.2: Create HILSubTask as single source of truth.
        # Replaces dual-store: SuspensionManager.store_context + FSMTurnState.
        # Captures react_snapshot from Back's ReactResult for zero-waste resume.
        timeout_s = payload.get("timeout_s", 60)
        timeout_ms = int(timeout_s * 1000)
        react_history = payload.get("react_history", [])
        react_checkpoint = payload.get("react_checkpoint", {})
        # Estimate iteration count from tool call messages in history
        tool_call_count = sum(
            1 for msg in react_history if isinstance(msg, dict) and msg.get("role") == "tool"
        )
        react_snapshot = {
            "prior_messages": react_history,
            "react_checkpoint": react_checkpoint if isinstance(react_checkpoint, dict) else {},
            "tool_history": [
                msg
                for msg in react_history
                if isinstance(msg, dict) and msg.get("role") in ("assistant", "tool")
            ],
            "last_iteration": max(1, tool_call_count),
        }
        device_id = payload.get("device_id", self._current_turn_device_id or "")
        hil_subtask = HILSubTask(
            hil_type=payload.get("hil_type", "clarification"),
            parent_task_id=task_id,
            question=payload.get("question", ""),
            options=payload.get("options", []),
            side_effects=payload.get("side_effects", []),
            safety_band=payload.get("safety_band", "GREEN"),
            timeout_ms=timeout_ms,
            react_snapshot=react_snapshot,
            device_id=device_id,
            context=payload.get("context", {}),
        )
        self._pending_hil_subtasks[task_id] = hil_subtask
        logger.info(
            "FSM._on_task_suspended: created HILSubTask id=%s type=%s "
            "task=%s resume_token=%s timeout=%dms snapshot_msgs=%d",
            hil_subtask.pending_hil_id[:8],
            hil_subtask.hil_type,
            task_id,
            hil_subtask.resume_token[:8],
            timeout_ms,
            len(react_history),
        )

        # Still use SuspensionManager for timeout watcher lifecycle
        # M6 E6.3.3: Start timeout watcher for hitl.timed_out.v1 emission
        self._suspension_manager.store_context(task_id, payload)
        timeout_s = timeout_ms / 1000.0
        self._suspension_manager._timeout_tasks[task_id] = asyncio.create_task(
            self._hitl_timeout_watcher(task_id, timeout_s, hil_subtask)
        )
        self._task_bridge.suspend_task(task_id)
        # M6 E6.4.1: Persist serialized HILSubTask for crash recovery
        compat_hil_envelope = {
            "hil_request_id": hil_subtask.pending_hil_id,
            "kind": "needs_human",
            "caller_key": f"legacy:{task_id}",
            "trace_id": envelope.cognitive_trace_id or str(payload.get("trace_id", "")),
            "created_at_ms": int(time.time() * 1000),
            "timeout_ms": timeout_ms,
            "payload": {
                "task_id": task_id,
                "hil_type": hil_subtask.hil_type,
                "question": hil_subtask.question,
                "options": list(hil_subtask.options),
                "side_effects": list(hil_subtask.side_effects),
                "safety_band": hil_subtask.safety_band,
                "legacy_bridge": True,
            },
            "legacy_bridge": True,
        }
        pending_hil_data = hil_subtask.to_persistence()
        pending_hil_data.update(
            {
                "hil_request_id": hil_subtask.pending_hil_id,
                "envelope": compat_hil_envelope,
                "compat_hil_envelope": compat_hil_envelope,
                "legacy_bridge": True,
            }
        )
        self._task_bridge.set_pending_hil_data(task_id, pending_hil_data)

        # M6 E6.3.1: Emit hitl.requested.v1 lifecycle event (observability)
        self._bus.publish(
            build_hitl_requested(
                payload={
                    "pending_hil_id": hil_subtask.pending_hil_id,
                    "hil_type": hil_subtask.hil_type,
                    "parent_task_id": task_id,
                    "safety_band": hil_subtask.safety_band,
                    "hil_deadline_ms": hil_subtask.hil_deadline,
                    "resume_token": hil_subtask.resume_token,
                    "device_id": hil_subtask.device_id,
                    "task_id": task_id,
                },
                parent_id=envelope.envelope_id,
            )
        )

        # Guard: only transition if FSM is in a compatible state
        if self._state not in (
            ConciergeState.COMPANIONING,
            ConciergeState.PROGRESSING,
        ):
            logger.warning(
                "FSM._on_task_suspended: state=%s not compatible for "
                "CLARIFYING_WORKER transition, deferring HITL for task_id=%s",
                self._state.name,
                task_id,
            )
            return

        # Transition to CLARIFYING_WORKER
        self._transition(
            ConciergeState.CLARIFYING_WORKER,
            TOPIC_TASK_SUSPENDED,
            envelope,
        )

        # Write history BEFORE delivery so entry order is correct:
        # [final] -> [hitl_request] -> [user/hitl_response] -> [final]
        self._write_history(
            entry_type="hitl_request",
            role="assistant",
            text=payload.get("question", ""),
            source="front",
            task_id=task_id,
            envelope=envelope,
            metadata={
                "hil_type": payload.get("hil_type", "clarification"),
            },
        )

        # Deliver to Front for HITL presentation
        if self._front_lock.try_deliver(envelope):
            self._deliver_to_front(envelope)

    def _on_task_resume(self, envelope: Envelope) -> None:
        """Handle k1.orchestration.task.resume.v1 (HITL exit point).

        **E4 HIL Unification — crash-recovery / legacy path only.**
        Live `needs_human` resolutions are injected into the React loop
        in-process inside `back_handler` (see
        `_resolve_needs_human_in_process`); they never round-trip through
        TOPIC_TASK_RESUME. This handler runs only for:

        - Kernel-restart crash recovery (replays stored suspension).
        - Front fallback when an incoming HITL envelope is absent
          (legacy `emit_task_resume` in `actors/front.py`).

        Front relayed user's HITL answer. Build structured ResumeContext
        from the stored suspension state, enrich the envelope, deliver
        resume to Back, and transition to COMPANIONING.

        M5 E5.4.4: Multi-device guard -- if multiple HITL responses arrive
        for the same task_id from different devices, accept first, discard
        duplicates with warning log.
        """
        # M2 E2.3.2: Idempotency check for task lifecycle
        if not self._idempotency.check_and_mark(envelope.envelope_id, self._turn_number):
            logger.debug("Duplicate envelope_id=%d, skipping", envelope.envelope_id)
            return

        # M2 E2.1.2: Guard gate
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "task_resume_invalid_state")
            return

        payload = _parse_payload(envelope)
        task_id = payload.get("task_id", "")
        self._drop_queued_front_hitl_for_task(task_id)

        pending_entry = self._task_bridge.get_task(task_id) if task_id else None
        pending_hil_data = getattr(pending_entry, "pending_hil_data", None)
        if isinstance(pending_hil_data, dict):
            pending_envelope = pending_hil_data.get("envelope") or pending_hil_data.get(
                "compat_hil_envelope"
            )
            if isinstance(pending_envelope, dict):
                from k1.concierge.actors.front_hil_envelope import (
                    is_legacy_bridge_envelope,
                )

                if not is_legacy_bridge_envelope(pending_envelope):
                    logger.warning(
                        "FSM._on_task_resume: dropping legacy task.resume for unified HIL "
                        "task_id=%s hil_request_id=%s",
                        task_id,
                        pending_envelope.get("hil_request_id", ""),
                    )
                    return

        # M5 E5.4.4: Multi-device dedup for HITL responses
        resume_device_id = payload.get("device_id", "")
        if task_id:
            prev_device = self._hitl_responded_tasks.get(task_id)
            if prev_device is not None:
                # Already responded to -- discard duplicate
                logger.warning(
                    "FSM._on_task_resume: DUPLICATE HITL response for task_id=%s "
                    "from device=%s (already responded by device=%s). Discarding.",
                    task_id,
                    resume_device_id or "unknown",
                    prev_device,
                )
                return
            self._hitl_responded_tasks[task_id] = resume_device_id or "unknown"

        # M6 E6.1.4: Validate resume_token before dispatching to Back.
        # Prevents stale/replayed resume events from restarting a Back loop
        # with wrong context for a task that already completed or was cancelled.
        resume_token = payload.get("resume_token")
        pending_subtask = self._pending_hil_subtasks.get(task_id)
        if pending_subtask is not None and resume_token is not None:
            if resume_token != pending_subtask.resume_token:
                logger.warning(
                    "FSM._on_task_resume: resume_token mismatch task_id=%s "
                    "expected=%s got=%s -- rejecting stale resume",
                    task_id,
                    pending_subtask.resume_token[:8],
                    str(resume_token)[:8],
                )
                return

        logger.info(
            "FSM._on_task_resume: state=%s envelope_id=%d task_id=%s device=%s",
            self._state.name,
            envelope.envelope_id,
            task_id,
            resume_device_id or "none",
        )
        resolution = payload.get("resolution")
        response_text = ""
        if isinstance(resolution, dict):
            response_text = str(
                resolution.get("answer")
                or resolution.get("additional_info")
                or resolution.get("target")
                or resolution.get("decision")
                or ""
            )
        elif payload.get("answer"):
            response_text = str(payload.get("answer"))

        # M6 E6.2.2: Read context from HILSubTask (single SOT), fall back
        # to SuspensionManager for backward compatibility with pre-M6 code.
        hil_subtask = self._pending_hil_subtasks.pop(task_id, None)
        stored_context = self._suspension_manager.pop_context(task_id)
        self._task_bridge.resume_task(task_id)

        # M6 E6.3.3: Cancel timeout watcher since user responded
        timeout_task = self._suspension_manager._timeout_tasks.pop(task_id, None)
        if timeout_task is not None and not timeout_task.done():
            timeout_task.cancel()

        # M6 E6.2.2: Resolve HILSubTask and build ResumeContext from it
        if hil_subtask is not None:
            hil_subtask.resolve(
                decision_branch=payload.get("decision_branch", "clarified"),
            )
            snapshot = hil_subtask.react_snapshot
            hil_type = hil_subtask.hil_type
            resume_ctx = build_resume_context(
                task_id=task_id,
                hil_type=hil_type,
                resolution=resolution if isinstance(resolution, dict) else {},
                findings_so_far=snapshot.get("prior_messages", []),
                original_task=stored_context.get("original_task", {}) if stored_context else {},
                last_iteration=snapshot.get("last_iteration", 0),
                total_budget=stored_context.get("total_budget", 10) if stored_context else 10,
                recovery=stored_context.get("recovery", {}) if stored_context else {},
                react_checkpoint=snapshot.get("react_checkpoint", {}),
            )
            # Inject resume context + resume_token into the envelope
            enriched = dict(payload)
            enriched["resume_context"] = resume_ctx.to_back_context()
            enriched["resume_token"] = hil_subtask.resume_token
            envelope = Envelope(
                topic=envelope.topic,
                payload=json.dumps(enriched).encode(),
                parent_id=envelope.parent_id,
                cognitive_trace_id=envelope.cognitive_trace_id,
                session_id=envelope.session_id,
                request_id=envelope.request_id,
            )
            logger.info(
                "FSM._on_task_resume: built ResumeContext from HILSubTask "
                "task_id=%s hil_type=%s prior_msgs=%d remaining_budget=%d",
                task_id,
                hil_type,
                len(snapshot.get("prior_messages", [])),
                resume_ctx.remaining_budget,
            )

            # M6 E6.3.2: Emit hitl.resolved.v1 lifecycle event
            decision_branch = payload.get("decision_branch", "clarified")
            self._bus.publish(
                build_hitl_resolved(
                    payload={
                        "pending_hil_id": hil_subtask.pending_hil_id,
                        "hil_type": hil_type,
                        "parent_task_id": task_id,
                        "decision_branch": decision_branch,
                        "has_merged_params": bool(resume_ctx.merged_params),
                        "device_id": resume_device_id or "",
                        "task_id": task_id,
                    },
                    parent_id=envelope.parent_id,
                )
            )
        elif stored_context is not None:
            # Legacy fallback: pre-M6 SuspensionManager path
            hil_type = stored_context.get("hil_type", "clarification")
            resume_ctx = build_resume_context(
                task_id=task_id,
                hil_type=hil_type,
                resolution=resolution if isinstance(resolution, dict) else {},
                findings_so_far=stored_context.get("react_history", []),
                original_task=stored_context.get("original_task", {}),
                last_iteration=stored_context.get("iteration", 0),
                total_budget=stored_context.get("total_budget", 10),
                recovery=stored_context.get("recovery", {}),
                react_checkpoint=stored_context.get("react_checkpoint", {}),
            )
            enriched = dict(payload)
            enriched["resume_context"] = resume_ctx.to_back_context()
            envelope = Envelope(
                topic=envelope.topic,
                payload=json.dumps(enriched).encode(),
                parent_id=envelope.parent_id,
                cognitive_trace_id=envelope.cognitive_trace_id,
                session_id=envelope.session_id,
                request_id=envelope.request_id,
            )
            logger.info(
                "FSM._on_task_resume: built ResumeContext (legacy) for task_id=%s "
                "hil_type=%s findings=%d remaining_budget=%d",
                task_id,
                hil_type,
                len(resume_ctx.findings_so_far),
                resume_ctx.remaining_budget,
            )

        # E4.M1.2: legacy `_hil_coordinator._pending_requests.pop` removed.
        # The unified HIL service owns the pending-request lifecycle
        # internally; clearing per-task state on resume is its responsibility,
        # not the FSM's.

        # OPP-4: Record HITL outcome in trust accumulator
        if self._opp_pipeline is not None:
            decision_branch = payload.get("decision_branch", "clarified")
            event_map = {
                "approved": "approve",
                "rejected": "reject",
                "cancelled": "cancel",
                "modified": "modify",
                "clarified": "approve",
            }
            self._opp_pipeline.on_hitl_outcome(
                event_type=event_map.get(decision_branch, "approve"),
                task_id=task_id,
            )

        # Transition to COMPANIONING
        self._transition(
            ConciergeState.COMPANIONING,
            TOPIC_TASK_RESUME,
            envelope,
        )

        # Deliver resume to Back via MailboxRouter
        self._deliver_to_back(envelope)

        self._write_history(
            entry_type="hitl_response",
            role="user",
            text=response_text,
            source="user",
            task_id=task_id,
            envelope=envelope,
        )
        self._check_hil_state_coherence(task_id=task_id, context="task_resume")

    def _recover_hitl_on_startup(self) -> None:
        """M6 E6.4.2-6.4.4: Recover pending HITL suspensions after crash/restart.

        Called from set_session_state after SS binding is complete.
        Scans task_state for SUSPENDED tasks with pending_hil_data:
            - Expired: emit hitl.timed_out.v1 + auto-cancel
            - Recoverable: reconstruct HILSubTask + restart timeout watcher
        """
        suspended = self._task_bridge.get_suspended_tasks()
        if not suspended:
            return

        # Build the dict shape that scan_for_recovery expects:
        # {task_id: {"status": ..., "pending_hil": <data_dict>}}
        task_state_dict: dict[str, dict] = {}
        for entry in suspended:
            if entry.pending_hil_data is not None:
                task_state_dict[entry.task_id] = {
                    "status": entry.status,
                    "pending_hil": entry.pending_hil_data,
                }

        if not task_state_dict:
            return

        report = scan_for_recovery(task_state_dict)
        logger.info(
            "HITL recovery scan: scanned=%d recovered=%d timed_out=%d skipped=%d",
            report.total_scanned,
            report.recovered_count,
            report.timed_out_count,
            report.skipped_count,
        )

        # 6.4.4: Auto-cancel expired suspensions
        from k1.concierge.bus.builders import build_hitl_timed_out

        for task_id in report.timed_out_task_ids:
            data = task_state_dict[task_id].get("pending_hil", {})
            suspended_at = data.get("suspended_at_ms", 0)
            timeout_ms = data.get("timeout_ms", 60_000)
            now_ms = int(time.monotonic_ns() / 1_000_000)
            elapsed_ms = now_ms - suspended_at if suspended_at > 0 else timeout_ms

            self._bus.publish(
                build_hitl_timed_out(
                    payload={
                        "pending_hil_id": data.get("pending_hil_id", ""),
                        "hil_type": data.get("hil_type", "clarification"),
                        "parent_task_id": task_id,
                        "timeout_ms": timeout_ms,
                        "elapsed_ms": elapsed_ms,
                        "task_id": task_id,
                        "recovery": True,
                    },
                    parent_id=0,
                )
            )
            # Transition task to CANCELLED
            try:
                self._task_bridge.cancel_task(task_id)
            except (KeyError, ValueError):
                logger.warning("Recovery: could not cancel task %s", task_id)
            self._active_task_ids.discard(task_id)
            self._suspension_manager.cleanup_task(task_id)
            logger.info("Recovery: auto-cancelled expired task %s", task_id)

        # 6.4.3: Re-present recoverable suspensions
        for task_id in report.recovered_task_ids:
            data = task_state_dict[task_id].get("pending_hil", {})
            hil_subtask = HILSubTask.from_persistence(data)
            self._pending_hil_subtasks[task_id] = hil_subtask

            # Calculate remaining timeout
            suspended_at = data.get("suspended_at_ms", 0)
            timeout_ms = data.get("timeout_ms", 60_000)
            now_ms = int(time.monotonic_ns() / 1_000_000)
            elapsed_ms = now_ms - suspended_at if suspended_at > 0 else 0
            remaining_ms = max(1000, timeout_ms - elapsed_ms)
            remaining_s = remaining_ms / 1000.0

            # Restart timeout watcher with adjusted deadline
            self._suspension_manager.store_context(task_id, data)
            self._suspension_manager._timeout_tasks[task_id] = asyncio.create_task(
                self._hitl_timeout_watcher(task_id, remaining_s, hil_subtask)
            )
            self._active_task_ids.add(task_id)
            logger.info(
                "Recovery: re-presented task %s (remaining=%.1fs hil_id=%s)",
                task_id,
                remaining_s,
                hil_subtask.pending_hil_id[:8],
            )

    async def _hitl_timeout_watcher(
        self, task_id: str, timeout_s: float, hil_subtask: HILSubTask
    ) -> None:
        """M6 E6.3.3: Watch for HITL suspension timeout.

        If the user does not respond within timeout_s, emits
        hitl.timed_out.v1, sets HILSubTask to TIMED_OUT, cancels
        the task, and cleans up in-memory state.
        """
        try:
            await asyncio.sleep(timeout_s)
        except asyncio.CancelledError:
            return

        # Check if still pending (user may have answered already)
        if task_id not in self._pending_hil_subtasks:
            return

        subtask = self._pending_hil_subtasks.pop(task_id, None)
        if subtask is None:
            return

        subtask.time_out()
        logger.warning(
            "HITL timeout for task_id=%s after %.1fs  pending_hil_id=%s",
            task_id,
            timeout_s,
            subtask.pending_hil_id[:8],
        )

        # Emit hitl.timed_out.v1 lifecycle event
        from k1.concierge.bus.builders import build_hitl_timed_out

        self._bus.publish(
            build_hitl_timed_out(
                payload={
                    "pending_hil_id": subtask.pending_hil_id,
                    "hil_type": subtask.hil_type,
                    "parent_task_id": task_id,
                    "timeout_ms": subtask.timeout_ms,
                    "elapsed_ms": int(timeout_s * 1000),
                    "task_id": task_id,
                },
                parent_id=0,
            )
        )

        # Auto-cancel the task
        self._task_bridge.cancel_task(task_id)
        self._active_task_ids.discard(task_id)
        self._remove_running_task(task_id)
        self._control_ext.remove_active_task(task_id)
        self._suspension_manager.cleanup_task(task_id)
        self._hitl_responded_tasks.pop(task_id, None)
        self._check_hil_state_coherence(task_id=task_id, context="hitl_timeout")

    def _on_hil_request(self, envelope: Envelope) -> None:
        """Handle k1.hil.request.v1 (HIL Unification E4 unified entry point).

        This is the unified successor to ``_on_task_suspended``.  Any
        subsystem -- Fabric (capability_gate), Back (needs_human),
        Planner (clarification/approval), Orchestrator (override) --
        that needs a human decision publishes a ``HILEnvelope`` on this
        topic via ``HumanInTheLoopService``.  The FSM owns the session
        state side of the flow:

          1. Parse the envelope (kind-agnostic; ``front_hil_envelope``
             unwraps kind-specific payloads inside Front).
          2. Determine the task slot.  When the envelope carries a
             back-task ``task_id`` (NEEDS_HUMAN), bind to that task.
             Otherwise (CAPABILITY_GATE / CLARIFICATION / APPROVAL /
             OVERRIDE) synthesise a transient SUSPENDED slot keyed by
             ``hil:{hil_request_id}`` so Front's existing pending-HIL
             lookup keeps working.
          3. Persist ``pending_hil_data`` containing the full envelope
             dict; Front reads it back via ``pending_hil.envelope`` and
             builds the correlated ``HILResponseEnvelope``.
          4. Transition to CLARIFYING_WORKER when state-compatible and
             deliver the envelope to Front for HITL_RELAY rendering.

        Timeout + Future resolution are owned by
        ``HumanInTheLoopService`` itself, so this handler does NOT start
        a watcher.  Crash recovery is owned by the service's
        ``SuspensionManager``.  Legacy ``HILSubTask`` lifecycle stays
        bound to ``_on_task_suspended`` until E4 Back migration retires
        ``TOPIC_TASK_SUSPENDED`` for live requests.
        """
        # Topic + idempotency guards (mirrors _on_task_suspended).
        if not self._topic_guard(envelope, TOPIC_HIL_REQUEST):
            return
        if not self._idempotency.check_and_mark(envelope.envelope_id, self._turn_number):
            logger.debug(
                "FSM._on_hil_request: duplicate envelope_id=%d skipped",
                envelope.envelope_id,
            )
            return

        env_payload = _parse_payload(envelope)
        hil_request_id = str(env_payload.get("hil_request_id") or "")
        kind = str(env_payload.get("kind") or "")
        caller_key = str(env_payload.get("caller_key") or "")
        inner = env_payload.get("payload") or {}
        if not hil_request_id or not kind:
            logger.warning(
                "FSM._on_hil_request: malformed envelope id=%d kind=%s hil_id=%s",
                envelope.envelope_id,
                kind,
                hil_request_id,
            )
            return

        flat: dict[str, Any] = {}
        try:
            from k1.concierge.actors.front_hil_envelope import (
                unwrap_hil_request_payload,
            )

            flat = unwrap_hil_request_payload(env_payload)
        except Exception:
            flat = dict(inner) if isinstance(inner, dict) else {}

        if self._ledger is not None:
            try:
                from k1.concierge.events.base import from_envelope
                from k1.concierge.events.hitl import HILRequested

                meta = from_envelope(envelope, "fsm")
                meta["session_id"] = getattr(self._ledger, "session_id", "")
                self._ledger.append_sync(
                    HILRequested(
                        task_id=str(inner.get("task_id") or f"hil:{hil_request_id}"),
                        hil_request_id=hil_request_id,
                        kind=kind,
                        caller_key=caller_key,
                        hil_type=str(flat.get("hil_type", kind) or kind),
                        question=str(flat.get("question", "") or ""),
                        options=list(flat.get("options", []) or []),
                        side_effects=list(flat.get("side_effects", []) or []),
                        context=dict(inner.get("context", {}) or {}),
                        safety_band=str(inner.get("safety_band") or "GREEN"),
                        created_at_ms=int(env_payload.get("created_at_ms", 0) or 0),
                        timeout_ms=int(env_payload.get("timeout_ms", 0) or 0),
                        **meta,
                    )
                )
            except Exception:
                logger.debug("FSM._on_hil_request: canonical ledger write failed", exc_info=True)

        if kind in _INLINE_HIL_WIDGET_KINDS:
            task_id = str(inner.get("task_id") or f"hil:{hil_request_id}")
            logger.info(
                "FSM._on_hil_request: hil_id=%s kind=%s uses direct UI widget; "
                "skipping Front HITL_RELAY",
                hil_request_id[:8],
                kind,
            )
            try:
                self._bus.publish(
                    build_hitl_requested(
                        payload=_hil_requested_payload(
                            hil_request_id=hil_request_id,
                            kind=kind,
                            task_id=task_id,
                            inner=inner,
                            envelope=envelope,
                        ),
                        parent_id=envelope.envelope_id,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("FSM._on_hil_request: observability emit failed err=%s", exc)
            return

        # Bind to an existing back task when present (NEEDS_HUMAN path);
        # otherwise synthesise a transient slot so Front's suspended-task
        # lookup finds the pending HIL.
        bound_task_id = str(inner.get("task_id") or "")
        synthetic = False
        task_id = bound_task_id or f"hil:{hil_request_id}"
        task_state = self._ss.get_section("task_state") if self._ss else None
        if task_state is not None and not bound_task_id:
            # Synthesise a SUSPENDED entry; Front reads pending_hil.envelope
            # off it and `determine_mode` resolves to HITL_RELAY via topic.
            try:
                from k1.sessionstate.sections.task_state import TaskStatus

                task_state.add_task(
                    action=f"hil:{kind}",
                    task_id=task_id,
                    status=TaskStatus.SUSPENDED,
                )
                synthetic = True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "FSM._on_hil_request: synthetic task creation failed hil=%s err=%s",
                    hil_request_id,
                    exc,
                )

        # Persist the full envelope so Front can build a correlated
        # HILResponseEnvelope via build_hil_response_envelope_dict.
        pending_hil_data = {
            "envelope": dict(env_payload),
            "hil_request_id": hil_request_id,
            "kind": kind,
            "synthetic": synthetic,
        }
        try:
            self._task_bridge.set_pending_hil_data(task_id, pending_hil_data)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "FSM._on_hil_request: set_pending_hil_data failed task=%s err=%s",
                task_id,
                exc,
            )

        logger.info(
            "FSM._on_hil_request: hil_id=%s kind=%s task=%s synthetic=%s state=%s",
            hil_request_id[:8],
            kind,
            task_id,
            synthetic,
            self._state.name,
        )

        # Observability: emit hitl.requested.v1 so dashboards / ledger
        # see a unified lifecycle entry alongside k1.hil.audit.v1.
        try:
            self._bus.publish(
                build_hitl_requested(
                    payload=_hil_requested_payload(
                        hil_request_id=hil_request_id,
                        kind=kind,
                        task_id=task_id,
                        inner=inner,
                        envelope=envelope,
                    ),
                    parent_id=envelope.envelope_id,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("FSM._on_hil_request: observability emit failed err=%s", exc)

        # Only transition when in a compatible state; otherwise the
        # envelope is still delivered below so Front can render whenever
        # the lock allows it (mirrors _on_task_suspended semantics).
        #
        # CLARIFYING_WORKER models a free-text clarification dialog with
        # the user (kinds: needs_human / clarification).  For inline
        # approval gates (capability_gate / approval / override) the
        # resolution is consumed in-process by Fabric (gate future) and
        # NO task.resume envelope is ever emitted -- so transitioning
        # into CLARIFYING_WORKER would strand the FSM there and cause
        # downstream tool.completed.v1 events to dead-letter.  Stay in
        # the current state for inline gates; determine_mode still routes
        # the hil.request envelope to Front via HITL_RELAY by topic.
        _INLINE_GATE_KINDS = ("capability_gate", "approval", "override")
        if kind not in _INLINE_GATE_KINDS and self._state in (
            ConciergeState.COMPANIONING,
            ConciergeState.PROGRESSING,
        ):
            self._transition(
                ConciergeState.CLARIFYING_WORKER,
                TOPIC_HIL_REQUEST,
                envelope,
            )

        # History entry (BEFORE delivery so order is final -> hitl_request -> resolve).
        try:
            self._write_history(
                entry_type="hitl_request",
                role="assistant",
                text=flat.get("question", "") or "",
                source="front",
                task_id=task_id,
                envelope=envelope,
                metadata={
                    "hil_type": flat.get("hil_type", kind),
                    "kind": kind,
                    "hil_request_id": hil_request_id,
                    "caller_key": caller_key,
                    "created_at_ms": int(env_payload.get("created_at_ms", 0) or 0),
                    "timeout_ms": int(env_payload.get("timeout_ms", 0) or 0),
                    "options": list(flat.get("options", []) or []),
                    "side_effects": list(flat.get("side_effects", []) or []),
                    "context": dict(inner.get("context", {}) or {}),
                    "safety_band": str(inner.get("safety_band") or "GREEN"),
                    "ledger_event_already_emitted": True,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("FSM._on_hil_request: history write skipped err=%s", exc)

        self._check_hil_state_coherence(
            task_id=task_id,
            hil_request_id=hil_request_id,
            context="hil_request",
        )

        if self._front_lock.try_deliver(envelope):
            self._deliver_to_front(envelope)

    def _on_response_final(self, envelope: Envelope) -> None:
        """Handle k1.response.final.v1 -- the turn exit point.

        M2 E2.3.1: Uses decide_response_final() pure function for all
        branching logic. The 13-branch decision table is externalized
        to response_final_table.py.
        """
        # M2 E2.3.3: Topic guard
        if not self._topic_guard(envelope, TOPIC_FINAL_RESPONSE):
            return

        payload = _parse_payload(envelope)
        text = payload.get("text", "")
        if text:
            self._current_turn_assistant_response = text
        logger.info(
            "FSM._on_response_final: state=%s envelope_id=%d text=%s",
            self._state.name,
            envelope.envelope_id,
            text[:60],
        )

        # M2 E2.1.2: Guard gate (after topic guard)
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "response_final_invalid_state")
            return

        # Detect fallback text for entry_type resolution
        _budget_fb = get_config().react.front_budget_fallback
        _degen_fb = get_config().react.front_degenerate_fallback
        is_fallback = text in (_budget_fb, _degen_fb)

        # M2 E2.3.1: Pure decision function -- no side effects
        decision = decide_response_final(
            fsm_state=self._state,
            has_pending_results=self._turn_state.has_pending_results,
            has_active_tasks=bool(self._active_task_ids),
            is_fallback=is_fallback,
            weave_flush_running=bool(self._weave_flush_task and not self._weave_flush_task.done()),
        )

        # M2 E2.5.4: Record response-final decision in ledger for audit trail
        if self._ledger is not None:
            from k1.concierge.events.base import from_envelope
            from k1.concierge.events.conversation import ResponseFinalDecided

            _meta = from_envelope(envelope, "fsm")
            rf_event = ResponseFinalDecided(
                decision_action=decision.action.value,
                target_state=decision.target_state.name if decision.target_state else "",
                has_pending_results=self._turn_state.has_pending_results,
                has_active_tasks=bool(self._active_task_ids),
                emit_turn_completed=decision.emit_turn_completed,
                schedule_weave=decision.schedule_weave,
                entry_type=decision.entry_type,
                **_meta,
            )
            self._ledger.append_sync(rf_event)

        # M6 E6.3 (C04): ResponseDelivered marker -- crash-recovery duplicate
        # delivery guard.  Written AFTER the decision is committed but BEFORE
        # the side-effecting `_execute_response_final_decision` (which routes
        # through weave-flush + Front delivery).  On replay, recovery treats
        # this event as proof that delivery already happened and avoids
        # re-emitting the response.
        if (
            self._ledger is not None
            and decision.action != ResponseFinalAction.IGNORE
            and decision.action != ResponseFinalAction.DEAD_LETTER
        ):
            from k1.concierge.events.base import from_envelope
            from k1.concierge.events.conversation import ResponseDelivered

            _meta_d = from_envelope(envelope, "fsm")
            rd_event = ResponseDelivered(
                text_preview=text[:200],
                entry_type=decision.entry_type,
                is_fallback=is_fallback,
                **_meta_d,
            )
            self._ledger.append_sync(rd_event)

        # Write history with decision-resolved entry_type
        self._write_history(
            entry_type=decision.entry_type,
            role="assistant",
            text=text,
            source="front",
            envelope=envelope,
        )

        # Push completed turn to SS history_active if sink is wired.
        if self._history_sink and text and self._current_turn_user_text and not is_fallback:
            try:
                self._history_sink.add_turn(
                    user_message=self._current_turn_user_text,
                    assistant_response=text,
                )
            except Exception:
                logger.debug("FSM: failed to push turn to history_sink", exc_info=True)

        # Signal WeaveBatcher that Front is idle
        if self._weave_batcher is not None:
            self._weave_batcher.set_front_busy(False)

        # Execute decision -- dispatch on action
        self._execute_response_final_decision(decision, envelope)

    def _execute_response_final_decision(
        self,
        decision: ResponseFinalDecision,
        envelope: Envelope,
    ) -> None:
        """Execute a ResponseFinalDecision produced by decide_response_final().

        M2 E2.3.1: Side-effect executor. Translates the pure decision
        into FSM transitions, FrontLock releases, weave scheduling, and
        turn finalization.
        """
        action = decision.action

        if action == ResponseFinalAction.IGNORE:
            logger.warning(
                "FSM._on_response_final: ignoring in %s state "
                "(envelope_id=%d) -- no turn.completed emitted",
                self._state.name,
                envelope.envelope_id,
            )
            return

        if action == ResponseFinalAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "response_final_invalid_state")
            return

        # Determine transition trigger
        trigger = TOPIC_FINAL_RESPONSE
        if decision.schedule_weave:
            trigger = TRIGGER_PENDING_RESULTS_NON_EMPTY
        elif (
            decision.target_state == ConciergeState.COMPANIONING
            and self._state == ConciergeState.DISPATCHING
        ):
            trigger = TOPIC_TASK_DISPATCH

        # State transition
        if decision.target_state is not None:
            self._transition(decision.target_state, trigger, envelope)

        # FrontLock release
        if decision.release_front_lock:
            self._front_lock.busy = False

        # Weave scheduling
        if decision.schedule_weave:
            self._schedule_weave_flush(envelope)
            return

        # Turn finalization
        if decision.emit_turn_completed and decision.drain_front_lock:
            self._finalize_turn(envelope)

    def _drain_front_lock_queue(self) -> None:
        """Release FrontLock and deliver any queued event.

        Called after FSM transitions to LISTENING. Uses release() to
        pop the next highest-priority event from the FrontLock queue.
        If a user.input was queued during DELIVERING/WEAVING, it gets
        processed here as a new turn.
        """
        next_env = self._front_lock.release()
        if next_env is None:
            return
        logger.info(
            "FSM._drain_front_lock_queue: delivering queued envelope topic=%s envelope_id=%d",
            next_env.topic,
            next_env.envelope_id,
        )
        if next_env.topic == TOPIC_USER_INPUT:
            # Re-dispatch through _on_user_input so FSM transitions happen
            self._on_user_input(next_env)
        else:
            self._deliver_to_front(next_env)

    # ------------------------------------------------------------------
    # M4 E4.5.4: Turn mutation summary
    # ------------------------------------------------------------------

    def _emit_turn_mutation_summary(self, envelope: Envelope) -> None:
        """Snapshot writer_port mutation stats and append to ledger.

        Called at turn boundary before turn.completed. If no writer_port
        or no ledger, silently returns. If the turn had zero mutations,
        skips emission to keep the ledger lean.
        """
        if self._ledger is None or self._ss is None:
            return
        writer_port = getattr(self._ss, "_writer_port", None)
        if writer_port is None or not hasattr(writer_port, "snapshot_turn_stats"):
            return

        stats = writer_port.snapshot_turn_stats()
        total = stats["approved_count"] + stats["rejected_count"] + stats["failed_count"]
        if total == 0:
            return

        from k1.concierge.events.mutation import TurnMutationSummary

        event = TurnMutationSummary(
            session_id=getattr(self._ledger, "session_id", ""),
            correlation_id=getattr(envelope, "cognitive_trace_id", ""),
            causation_id=str(getattr(envelope, "envelope_id", 0)),
            actor="fsm",
            turn_number=self._turn_number,
            approved_count=stats["approved_count"],
            rejected_count=stats["rejected_count"],
            failed_count=stats["failed_count"],
            by_section=stats["by_section"],
            by_rejection_reason=stats["by_rejection_reason"],
            total_bytes_delta=stats["total_bytes_delta"],
            total_duration_ms=stats["total_duration_ms"],
            device_id=self._current_turn_device_id,  # M5 E5.5.6
        )
        self._ledger.append_sync(event)
        logger.debug(
            "TurnMutationSummary: turn=%d approved=%d rejected=%d",
            self._turn_number,
            stats["approved_count"],
            stats["rejected_count"],
        )

    def _emit_turn_completed(self, envelope: Envelope) -> None:
        """Emit turn.completed observability event, advance narrative arc, and check deferred HITL."""
        # M4 E4.5.4: Emit TurnMutationSummary to ledger at turn boundary
        self._emit_turn_mutation_summary(envelope)

        # ── Build a payload that MemoryWriter's SessionBatchDispatcher
        # can actually consume. Without these fields the MW dispatcher
        # logs "missing turn_id" and drops every turn.
        ledger_session_id = getattr(self._ledger, "session_id", "") if self._ledger else ""
        envelope_session_id = getattr(envelope, "session_id", "") or ""
        session_id = ledger_session_id or envelope_session_id
        cognitive_trace_id = getattr(envelope, "cognitive_trace_id", "") or ""

        if not session_id:
            logger.warning(
                "FSM._emit_turn_completed: refusing publish without session-scoped id "
                "(ledger missing or empty, envelope_id=%d)",
                envelope.envelope_id,
            )
            self._publish_dead_letter(envelope, "turn_completed_missing_session_id")
            return

        # Extract assistant text from the response_final envelope payload.
        assistant_response = ""
        try:
            raw = envelope.payload
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="replace")
            if isinstance(raw, str) and raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    assistant_response = str(parsed.get("text", "") or "")
            elif isinstance(raw, dict):
                assistant_response = str(raw.get("text", "") or "")
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
            assistant_response = ""
        if not assistant_response:
            assistant_response = self._current_turn_assistant_response

        # Stable, dedup-friendly turn_id (session-scoped, monotonic).
        turn_id = f"{session_id}:{self._turn_number}"

        # MW-dedup guard: skip publishing if we already emitted this
        # turn_id (same-turn dispatch+complete followed by proactive
        # delivery would otherwise publish the same turn_id twice).
        # Narrative arc + deferred-HITL still run below.
        already_emitted = turn_id in self._emitted_turn_ids
        if already_emitted:
            logger.debug(
                "FSM._emit_turn_completed: already emitted turn_id=%s, skipping publish",
                turn_id,
            )
        else:
            self._emitted_turn_ids.add(turn_id)
            self._bus.publish(
                build_turn_completed(
                    payload={
                        "turn_id": turn_id,
                        "session_id": session_id,
                        "cognitive_trace_id": cognitive_trace_id,
                        "user_message": self._current_turn_user_text,
                        "assistant_response": assistant_response,
                        "timestamp_ms": int(time.time() * 1000),
                        "turn_number": self._turn_number,
                    },
                    parent_id=envelope.envelope_id,
                )
            )
        # Advance narrative arc position for this turn (Gap 5, Section 5.1).
        # record_turn updates primary_thread.last_active_turn and the arc
        # position so the Front LLM's narrative context stays current.
        if self._ss:
            try:
                narrative = self._ss.get_section("narrative_active")
                if narrative and hasattr(narrative, "record_turn"):
                    narrative.record_turn(self._turn_number)
            except Exception:
                logger.debug("FSM: failed to record narrative turn", exc_info=True)
        # Check for deferred HITL suspensions (Gap 1, Section 9):
        # If task.suspended arrived while FSM was in an incompatible state,
        # the HITL question was stored but never presented. Now that we're
        # back to LISTENING, surface the first pending HITL question.
        self._surface_deferred_hitl(envelope)

    def _surface_deferred_hitl(self, envelope: Envelope) -> None:
        """Surface deferred HITL suspensions after reaching LISTENING state.

        When task.suspended arrives in an incompatible FSM state (e.g.
        DISPATCHING), the context is stored but the HITL question is not
        presented. This method checks for pending suspensions and
        transitions to CLARIFYING_WORKER to present the first one.
        """
        if self._state != ConciergeState.LISTENING:
            return

        suspended_tasks = self._task_bridge.get_suspended_tasks()
        if not suspended_tasks:
            return

        for task_entry in suspended_tasks:
            task_id = task_entry.task_id
            context = self._suspension_manager.pop_context(task_id)
            if not context:
                # Already surfaced or no stored context
                continue

            logger.info(
                "FSM._surface_deferred_hitl: surfacing deferred HITL " "for task_id=%s question=%s",
                task_id,
                str(context.get("question", ""))[:60],
            )

            # Build a synthetic suspension envelope for Front
            from k1.concierge.bus.builders import build_task_suspended

            hitl_env = build_task_suspended(
                payload=context,
                parent_id=envelope.envelope_id,
            )

            # Write history entry for the deferred HITL question
            self._write_history(
                entry_type="hitl_request",
                role="assistant",
                text=context.get("question", ""),
                source="front",
                task_id=task_id,
                envelope=hitl_env,
                metadata={
                    "hil_type": context.get("hil_type", "clarification"),
                    "deferred": True,
                },
            )

            # Transition and deliver
            from k1.concierge.fsm.transition_table import TRIGGER_DEFERRED_HITL

            self._transition(
                ConciergeState.CLARIFYING_WORKER,
                TRIGGER_DEFERRED_HITL,
                hitl_env,
            )

            if self._front_lock.try_deliver(hitl_env):
                self._deliver_to_front(hitl_env)

            # Only surface one at a time -- next one after this resolves
            break

    def _build_weave_envelope(
        self,
        results: list[dict[str, Any]],
        parent_id: int,
    ) -> Envelope:
        """Build a synthetic weave batch envelope for Front delivery.

        Assigns a unique negative envelope_id to avoid dedup collisions
        (synthetic envelopes bypass the bus and would otherwise all have
        envelope_id=0, causing the coordinator dedup guard to drop them).
        """
        from dataclasses import replace as _dc_replace

        from k1.concierge.bus.builders import (
            build_weave_batch,
            next_synthetic_envelope_id,
        )

        env = build_weave_batch(
            payload={
                "results": results,
                "count": len(results),
                "current_thread": "",
            },
            parent_id=parent_id,
        )
        return _dc_replace(env, envelope_id=next_synthetic_envelope_id())

    def _prepare_weave_results_for_delivery(
        self,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Sort results and run the OPP weave-flush hook once."""
        sorted_results = sort_results_for_delivery(results)
        if self._opp_pipeline is not None:
            pacing = self._opp_pipeline.on_weave_flush(
                results=sorted_results,
                batch_count=len(sorted_results),
            )
            if getattr(pacing, "use_pacing", False):
                logger.info(
                    "FSM._prepare_weave_results_for_delivery: OPP-1 pacing strategy=%s groups=%d",
                    getattr(pacing, "strategy", "unknown"),
                    getattr(pacing, "group_count", 0),
                )
        return sorted_results

    # ------------------------------------------------------------------
    # BUG-6 FIX: Proactive delivery for same-turn deferred results
    # ------------------------------------------------------------------

    _DEFERRED_PROACTIVE_DELAY_S: float = 2.0

    def _schedule_deferred_proactive_delivery(self, envelope: Envelope) -> None:
        """Schedule proactive delivery of deferred same-turn results.

        When a task completes in the same turn it was dispatched, results
        are stored in deferred_results. Without this timer, results sit
        silently until the user sends a new message -- making the bot
        appear unresponsive.

        After a short delay (2s for batching), this method transitions
        to DELIVERING and flushes deferred results via the PRESENT/WEAVE
        path so results arrive proactively.

        Sync test path (no event loop): delivers immediately.
        """
        if self._deferred_proactive_task and not self._deferred_proactive_task.done():
            return  # Timer already running

        if not self._turn_state.has_deferred_results:
            return  # Nothing to deliver

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Sync path (tests): deliver immediately
            self._flush_deferred_proactive(envelope)
            return

        _saved_envelope = envelope

        async def _delayed_proactive() -> None:
            await asyncio.sleep(self._DEFERRED_PROACTIVE_DELAY_S)
            # Only deliver if still LISTENING and deferred results exist.
            # If the user spoke during the delay, _check_deferred_results_on_input
            # already handled it and we should not double-deliver.
            if self._state == ConciergeState.LISTENING and self._turn_state.has_deferred_results:
                self._flush_deferred_proactive(_saved_envelope)

        self._deferred_proactive_task = loop.create_task(_delayed_proactive())

    def _flush_deferred_proactive(self, envelope: Envelope) -> None:
        """Proactively deliver deferred results without waiting for user input.

        Moves deferred results into pending_results, then uses the existing
        weave delivery pipeline (IMMEDIATE path) to push results to Front.
        """
        deferred = self._turn_state.drain_deferred()
        if not deferred:
            return

        signal = self._collect_weave_signal()
        if (
            signal.user_typing
            or signal.hitl_pending
            or signal.emotional_gate == EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY
        ):
            for item in deferred:
                evicted = self._turn_state.defer_result(item)
                if evicted is not None:
                    self._turn_state.pending_results.append(evicted)
            logger.debug("FSM._flush_deferred_proactive: gated, re-deferred results")
            return

        logger.info(
            "FSM._flush_deferred_proactive: delivering %d deferred results proactively",
            len(deferred),
        )

        # Move deferred items into the pending_results queue
        for item in deferred:
            self._turn_state.pending_results.append(item)

        # Deliver via the immediate weave path
        self._deliver_weave_immediate(envelope)

    def _schedule_weave_flush(self, parent_envelope: Envelope) -> None:
        """Schedule (or immediately execute) a weave flush for pending results.

        Runtime path: starts a 500ms batch window to collect closely-arriving
        completions before invoking Front in WEAVE mode.
        Sync test path (no running event loop): flushes immediately.
        """
        logger.debug(
            "FSM._schedule_weave_flush: pending=%d parent_id=%d",
            len(self._turn_state.pending_results),
            parent_envelope.envelope_id,
        )
        if self._weave_flush_task and not self._weave_flush_task.done():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._flush_weave_now(parent_envelope.envelope_id)
            return

        self._weave_flush_task = loop.create_task(
            self._flush_weave_after_delay(parent_envelope.envelope_id)
        )

    async def _flush_weave_after_delay(self, parent_id: int) -> None:
        await asyncio.sleep(WEAVE_BATCH_WINDOW_MS / 1000)
        self._flush_weave_now(parent_id)

    def _flush_weave_now(self, parent_id: int) -> None:
        results, expired = self._turn_state.drain_results()
        # M2 E2.2.3: Dead-letter expired results
        for exp in expired:
            stub = Envelope(
                topic=TOPIC_TASK_COMPLETE,
                priority=Priority.INTERACTIVE,
                payload=json.dumps(exp, default=str).encode("utf-8"),
                parent_id=parent_id,
                payload_format=PayloadFormat.JSON,
            )
            self._publish_dead_letter(stub, "expired")
        if not results:
            return

        prepared_results = self._prepare_weave_results_for_delivery(results)
        weave_envelope = self._build_weave_envelope(prepared_results, parent_id)
        if self._front_lock.try_deliver(weave_envelope):
            self._deliver_to_front(weave_envelope)
        else:
            # BUG-4a FIX: Re-enqueue results when FrontLock rejects delivery
            # so they are not permanently lost.
            for item in prepared_results:
                self._turn_state.pending_results.append(item)
            logger.debug(
                "FSM._flush_weave_now: FrontLock busy, re-enqueued %d results",
                len(prepared_results),
            )

    # ------------------------------------------------------------------
    # M8 E8.5.2: Adaptive weave delivery methods
    # ------------------------------------------------------------------

    def _deliver_weave_immediate(self, envelope: Envelope) -> None:
        """M8 E8.5.2 step 11 IMMEDIATE: Deliver weave results with 0ms delay.

        Transitions to DELIVERING and delivers directly to Front.
        """
        if self._state == ConciergeState.LISTENING:
            payload = _parse_payload(envelope)
            task_id = payload.get("task_id", "")
            self._proactive_wake.record_wake(task_id)
            self._transition(ConciergeState.PROACTIVE_WAKE, TOPIC_TASK_COMPLETE, envelope)
            self._transition(ConciergeState.DELIVERING, TRIGGER_PROACTIVE_ROUTED, envelope)
        elif self._state in (ConciergeState.COMPANIONING, ConciergeState.PROGRESSING):
            self._transition(ConciergeState.DELIVERING, TOPIC_TASK_COMPLETE, envelope)

        results, expired = self._turn_state.drain_results()
        for exp in expired:
            self._publish_dead_letter(
                Envelope(
                    topic=TOPIC_TASK_COMPLETE,
                    priority=Priority.INTERACTIVE,
                    payload=json.dumps(exp, default=str).encode("utf-8"),
                    parent_id=envelope.envelope_id,
                    payload_format=PayloadFormat.JSON,
                ),
                "expired",
            )
        if results:
            sorted_results = self._prepare_weave_results_for_delivery(results)
            weave_env = self._build_weave_envelope(sorted_results, envelope.envelope_id)
            if self._front_lock.try_deliver(weave_env):
                self._deliver_to_front(weave_env)
            else:
                # BUG-4b FIX: Re-enqueue results when FrontLock rejects delivery.
                for item in sorted_results:
                    self._turn_state.pending_results.append(item)
                logger.debug(
                    "FSM._deliver_weave_immediate: FrontLock busy, re-enqueued %d results",
                    len(sorted_results),
                )

    def _schedule_weave_flush_adaptive(self, envelope: Envelope, window_ms: int) -> None:
        """M8 E8.5.2 step 11 BATCH: Schedule weave flush with dynamic window.

        Uses the WeavePolicy's computed window_ms instead of fixed 500ms.
        Falls back to sync flush when no event loop is running (tests).
        """
        logger.debug(
            "FSM._schedule_weave_flush_adaptive: pending=%d window=%dms",
            len(self._turn_state.pending_results),
            window_ms,
        )
        if self._weave_flush_task and not self._weave_flush_task.done():
            return

        # BUG-5 FIX: Do NOT transition to DELIVERING here. The transition
        # happens prematurely (before the delayed flush fires), blocking
        # other events during the batch window. Instead, defer the
        # transition to when the flush actually executes.

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if self._state in (ConciergeState.COMPANIONING, ConciergeState.PROGRESSING):
                self._transition(ConciergeState.DELIVERING, TOPIC_TASK_COMPLETE, envelope)
            self._flush_weave_now(envelope.envelope_id)
            return

        _saved_envelope = envelope

        async def _delayed_flush() -> None:
            if self._state in (ConciergeState.COMPANIONING, ConciergeState.PROGRESSING):
                self._transition(ConciergeState.DELIVERING, TOPIC_TASK_COMPLETE, _saved_envelope)
            await asyncio.sleep(window_ms / 1000)
            self._flush_weave_now(_saved_envelope.envelope_id)

        self._weave_flush_task = loop.create_task(_delayed_flush())

    def _mark_results_deferred(self, envelope: Envelope | None = None) -> None:
        """M8 E8.5.4: Move pending results to deferred_results.

        Results will be re-evaluated and injected into the next STANDARD
        prompt via async_results_context on user input.
        """
        force_deliver = self._turn_state.mark_deferred()
        if force_deliver:
            logger.info(
                "FSM._mark_results_deferred: %d results exceeded max_consecutive_defers -- force delivering",
                len(force_deliver),
            )
            # BUG-2 FIX: Actually deliver force-deliver results instead of
            # silently dropping them.  Re-enqueue into pending_results so
            # the next weave flush picks them up for BATCH delivery.
            for item in force_deliver:
                self._turn_state.pending_results.append(item)
            if envelope is not None:
                self._schedule_weave_flush_adaptive(envelope, WEAVE_BATCH_WINDOW_MS)
            else:
                self._schedule_weave_flush(
                    Envelope(
                        topic=TOPIC_TASK_COMPLETE,
                        priority=Priority.INTERACTIVE,
                        payload=b"{}",
                        parent_id=0,
                        payload_format=PayloadFormat.JSON,
                    )
                )

    def _schedule_digest_flush(self, envelope: Envelope, window_ms: int) -> None:
        """M8 E8.5.5: Accumulate results for digest_window_ms then compress.

        If a digest timer is already running, results just accumulate.
        When the timer fires, all accumulated results are compressed into
        a DigestPayload and delivered through the Front WEAVE pipeline.
        """
        if self._digest_flush_task and not self._digest_flush_task.done():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._flush_digest_now(envelope.envelope_id)
            return

        async def _delayed_digest() -> None:
            await asyncio.sleep(window_ms / 1000)
            self._flush_digest_now(envelope.envelope_id)

        self._digest_flush_task = loop.create_task(_delayed_digest())

    def _flush_digest_now(self, parent_id: int) -> None:
        """M8 E8.5.5: Compress accumulated results into a digest payload."""
        from k1.concierge.protocols.weave_policy import DigestPayload

        results, expired = self._turn_state.drain_results()
        for exp in expired:
            stub = Envelope(
                topic=TOPIC_TASK_COMPLETE,
                priority=Priority.INTERACTIVE,
                payload=json.dumps(exp, default=str).encode("utf-8"),
                parent_id=parent_id,
                payload_format=PayloadFormat.JSON,
            )
            self._publish_dead_letter(stub, "expired")
        if not results:
            return

        digest = DigestPayload.from_results(results)
        from k1.concierge.bus.builders import build_weave_batch

        digest_envelope = build_weave_batch(
            payload={
                "results": [
                    {
                        "digest_summary": digest.summary_text,
                        "digest_count": digest.result_count,
                        "is_digest": True,
                    }
                ],
                "count": digest.result_count,
                "current_thread": "",
                "is_digest": True,
            },
            parent_id=parent_id,
        )
        if self._front_lock.try_deliver(digest_envelope):
            self._deliver_to_front(digest_envelope)
        else:
            # BUG-4c FIX: Re-enqueue results when FrontLock rejects digest delivery.
            for item in results:
                self._turn_state.pending_results.append(item)
            logger.debug(
                "FSM._flush_digest_now: FrontLock busy, re-enqueued %d results",
                len(results),
            )

    def _suppress_result(self, task_id: str, reason: str) -> None:
        """M8 E8.5.2 step 11 SUPPRESS: Discard result, log for audit."""
        logger.info(
            "FSM._suppress_result: task=%s suppressed (reason=%s)",
            task_id,
            reason[:80],
        )
        removed = self._discard_task_result_ownership(task_id)
        if removed:
            logger.debug("FSM._suppress_result: discarded queued result for task=%s", task_id)

    def _emit_weave_decided(
        self,
        decision: WeaveDecisionResult,
        envelope: Envelope,
        signal: WeaveSignal,
        *,
        fallback_used: bool = False,
    ) -> None:
        """M8 E8.5.2 step 10: Emit weave.decided.v1 event to bus and ledger.

        Publishes a WeaveDecisionMade event for observability and replay.
        """
        from k1.concierge.bus.builders import build_weave_decided

        decided_payload = {
            "candidate_event_id": str(envelope.envelope_id),
            "decision": decision.decision.name,
            "reason": decision.reasoning,
            "window_ms": decision.window_ms,
            "fsm_state": self._state.name,
            "signal_snapshot": signal.to_dict(),
            "urgency_override": decision.urgency_override,
            "emotional_gate_applied": decision.emotional_gate_applied,
            "fallback_used": fallback_used,
        }

        self._bus.publish(
            build_weave_decided(
                payload=decided_payload,
                parent_id=envelope.envelope_id,
            )
        )

        # Ledger write
        if self._ledger is not None:
            from k1.concierge.events.weave import WeaveDecisionMade

            event = WeaveDecisionMade(
                candidate_event_id=str(envelope.envelope_id),
                decision=decision.decision.name,
                reason=decision.reasoning,
                batch_window_ms=decision.window_ms,
                fsm_state=self._state.name,
                signal_snapshot=signal.to_dict(),
                urgency_override=decision.urgency_override,
                emotional_gate_applied=decision.emotional_gate_applied,
                fallback_used=fallback_used,
            )
            self._ledger.append_sync(event)

    # ------------------------------------------------------------------
    # M8 E8.5.4: Deferred results injection on user input
    # ------------------------------------------------------------------

    def _check_deferred_results_on_input(self, envelope: Envelope) -> None:
        """M8 E8.5.4: On user input, re-evaluate deferred results.

        If deferred results exist, re-evaluate the policy.  Results
        that are no longer DEFER are formatted as async_results_context
        and injected into the STANDARD prompt.

        OPP-8: Also consults DeliveryStrategyEngine.on_natural_pause()
        to determine which deferred results should now be surfaced.
        """
        if not self._turn_state.has_deferred_results:
            return

        deferred = self._turn_state.drain_deferred()
        if not deferred:
            return

        # OPP-8: Natural pause delivery strategy for deferred results
        if self._opp_pipeline is not None:
            opp_decisions = self._opp_pipeline.on_natural_pause(
                deferred_results=deferred,
            )
            if opp_decisions:
                logger.info(
                    "FSM._check_deferred: OPP-8 natural pause re-evaluated %d deferred, "
                    "%d ready to deliver",
                    len(deferred),
                    len(opp_decisions),
                )

        deliver_now: list[dict[str, Any]] = []
        still_deferred: list[dict[str, Any]] = []

        signal = self._collect_weave_signal()

        for item in deferred:
            defer_count = item.get("defer_count", 0)
            max_defers = 5
            if self._weave_policy is not None and hasattr(
                self._weave_policy, "_max_consecutive_defers"
            ):
                max_defers = self._weave_policy._max_consecutive_defers

            if defer_count >= max_defers:
                deliver_now.append(item)
                continue

            if self._weave_policy is not None:
                try:
                    re_decision = self._weave_policy.decide(signal)
                except Exception:
                    re_decision = self._weave_fallback.fallback_decide(self._state)
                if re_decision.decision == WeaveDecision.DEFER:
                    item["defer_count"] = defer_count + 1
                    still_deferred.append(item)
                    continue

            deliver_now.append(item)

        # Re-add still-deferred items
        if still_deferred:
            self._turn_state.deferred_results.extend(still_deferred)

        # Build async_results_context for STANDARD injection
        if deliver_now:
            lines: list[str] = [
                "== BACKGROUND UPDATES ==",
                f"While you were away, {len(deliver_now)} background task(s) completed:",
            ]
            sorted_results = sort_results_for_delivery(deliver_now)
            for item in sorted_results:
                tid = item.get("task_id", "unknown")
                result_data = item.get("result", {})
                urg = item.get("urgency", "normal")
                if isinstance(result_data, dict):
                    # Task complete payloads use final_answer (from Back LLM
                    # submit_result), which contains the actionable summary.
                    # Fall through to summary/description for other event types.
                    summary = (
                        result_data.get("final_answer")
                        or result_data.get("summary")
                        or result_data.get("description")
                        or f"Task {tid} completed"
                    )
                    # Include structured results so Front can present actual
                    # data (search results, names, URLs) to the user.
                    inner_results = result_data.get("results", [])
                    if isinstance(inner_results, list) and inner_results:
                        for ritem in inner_results[:10]:
                            if isinstance(ritem, dict):
                                title = ritem.get("title") or ritem.get("name", "")
                                url = ritem.get("url") or ritem.get("href", "")
                                snippet = ritem.get("snippet") or ritem.get("body", "")
                                if title:
                                    detail = f"  * {title}"
                                    if url:
                                        detail += f" -- {url}"
                                    if snippet:
                                        detail += f"\n    {snippet[:120]}"
                                    lines.append(detail)
                else:
                    summary = str(result_data)[:120] if result_data else f"Task {tid} completed"
                prefix = "[URGENT] " if urg in ("critical", "urgent") else ""
                lines.append(f"- {prefix}{summary}")
            lines.append(
                "Weave these updates naturally into your response. "
                "Address the user's message first."
            )
            self._async_results_context = "\n".join(lines)
            logger.info(
                "FSM._check_deferred_results_on_input: injecting %d deferred results",
                len(deliver_now),
            )

    # ------------------------------------------------------------------
    # Observability / passthrough handlers
    # ------------------------------------------------------------------

    def _on_tool_started(self, envelope: Envelope) -> None:
        """Handle k1.tool.started.v1 -- observability: track tool execution."""
        # M2 E2.1.2: Guard gate
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "tool_started_invalid_state")
            return

        payload = _parse_payload(envelope)
        task_id = payload.get("task_id", "")
        tool_name = payload.get("tool_name", "")
        logger.info(
            "FSM._on_tool_started: state=%s envelope_id=%d task_id=%s tool=%s",
            self._state.name,
            envelope.envelope_id,
            task_id,
            tool_name,
        )
        if task_id:
            self._task_bridge.activate_task(task_id)
        if self._state == ConciergeState.COMPANIONING:
            self._transition(
                ConciergeState.PROGRESSING,
                TOPIC_TOOL_STARTED,
                envelope,
            )

    def _on_tool_completed(self, envelope: Envelope) -> None:
        """Handle k1.tool.completed.v1 -- return to COMPANIONING."""
        # M2 E2.1.2: Guard gate
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "tool_completed_invalid_state")
            return

        payload = _parse_payload(envelope)
        logger.info(
            "FSM._on_tool_completed: state=%s envelope_id=%d tool=%s duration_ms=%s success=%s",
            self._state.name,
            envelope.envelope_id,
            payload.get("tool_name", ""),
            payload.get("duration_ms", ""),
            payload.get("success", ""),
        )
        if self._state == ConciergeState.PROGRESSING:
            self._transition(
                ConciergeState.COMPANIONING,
                TOPIC_TOOL_COMPLETED,
                envelope,
            )

    def _on_findings_ready(self, envelope: Envelope) -> None:
        """Handle k1.orchestration.findings.ready.v1 -- partial results."""
        # M2 E2.1.2: Guard gate
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "findings_ready_invalid_state")
            return

        # Deliver to Front via FrontLock (informational)
        if self._front_lock.try_deliver(envelope):
            self._deliver_to_front(envelope)

    def _on_artifact_created(self, envelope: Envelope) -> None:
        """Handle k1.session.artifact.created.v1."""
        # M2 E2.1.2: Guard gate
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "artifact_created_invalid_state")
            return

        payload = _parse_payload(envelope)
        task_id = payload.get("task_id", "")
        self._write_history(
            entry_type="artifact",
            role="system",
            text=payload.get("artifact_type", ""),
            source="back",
            task_id=task_id,
            envelope=envelope,
        )

    def _on_affect_update(self, envelope: Envelope) -> None:
        """Handle k1.affect.update.v1 -- RELAXED, observability only."""
        # M2 E2.1.2: Guard gate
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "affect_update_invalid_state")
            return
        logger.debug("Affect update received (RELAXED)")

    def _on_proactive_fill(self, envelope: Envelope) -> None:
        """Handle k1.proactive.fill.v1 by routing safe fills to Front."""
        # M2 E2.1.2: Guard gate
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "proactive_fill_invalid_state")
            return
        payload = _parse_payload(envelope)
        if not self._should_deliver_proactive_fill(payload):
            return
        logger.debug("Proactive fill received (RELAXED), delivering to Front")
        if self._front_lock.try_deliver(envelope):
            self._deliver_to_front(envelope)

    def _should_deliver_proactive_fill(self, payload: dict[str, Any]) -> bool:
        """Return True when a proactive fill can safely reach Front."""
        message = str(payload.get("message") or payload.get("text") or "").strip()
        if not message:
            logger.debug("Proactive fill suppressed: empty message")
            return False
        if self._state == ConciergeState.CLARIFYING_WORKER or self._has_pending_hitl():
            logger.debug("Proactive fill suppressed: HITL active")
            return False
        signal = self._collect_weave_signal()
        if signal.user_typing:
            logger.debug("Proactive fill suppressed: user typing")
            return False
        if signal.emotional_gate == EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY:
            logger.debug("Proactive fill suppressed: crisis/safety gate")
            return False

        task_state_payload = payload.get("task_state")
        task_state = task_state_payload if isinstance(task_state_payload, dict) else {}
        task_id = str(
            payload.get("task_id") or payload.get("task") or task_state.get("task_id") or "session"
        ).strip()
        fill_kind = str(payload.get("kind") or payload.get("style") or "wait_status")
        key = f"{task_id}:{fill_kind}"
        now_ns = time.monotonic_ns()
        cooldown_ms = int(getattr(get_config().experience, "proactive_fill_cooldown_ms", 15_000))
        last_ns = self._proactive_fill_last_by_key.get(key, 0)
        if last_ns and (now_ns - last_ns) / 1_000_000 < cooldown_ms:
            logger.debug("Proactive fill suppressed: cooldown key=%s", key)
            return False
        self._proactive_fill_last_by_key[key] = now_ns
        return True

    def _on_ui_typing(self, envelope: Envelope) -> None:
        """Handle k1.ui.typing.v1 -- user typing signal (M8 E8.5.1).

        Updates UserActivityTracker with typing start/stop events.
        Typing signals are in-memory only (not written to ledger).
        """
        if self._activity_tracker is None:
            return
        payload = _parse_payload(envelope)
        typing = payload.get("typing", False)
        if typing:
            self._activity_tracker.on_typing_start()
        else:
            self._activity_tracker.on_typing_stop()

    def _on_concierge_config_update(self, envelope: Envelope) -> None:
        """Handle k1.internal.concierge.config.update.v1 -- runtime config toggle (M6 E6.4 C06).

        Payload schema: {"weave_policy": {"enabled": bool}, ...}

        Currently supported toggles:
            weave_policy.enabled -- WeavePolicy.set_enabled(bool)

        Unknown keys are logged at debug and ignored (forward-compatible).
        Malformed payloads are logged at warning and dropped.
        """
        try:
            payload = _parse_payload(envelope)
        except Exception:
            logger.warning(
                "FSM._on_concierge_config_update: malformed payload envelope_id=%d",
                envelope.envelope_id,
            )
            return

        wp = payload.get("weave_policy")
        if isinstance(wp, dict) and "enabled" in wp and self._weave_policy is not None:
            new_enabled = bool(wp["enabled"])
            self._weave_policy.set_enabled(new_enabled)
            logger.info(
                "FSM._on_concierge_config_update: weave_policy.enabled=%s",
                new_enabled,
            )

    def _on_weave_batch(self, envelope: Envelope) -> None:
        """Handle k1.internal.weave.batch.v1 -- weave timer fired."""
        # M2 E2.1.2: Guard gate
        guard = self._guard_dispatch(envelope)
        if guard == GuardAction.DEAD_LETTER:
            self._publish_dead_letter(envelope, "weave_batch_invalid_state")
            return

        logger.info(
            "FSM._on_weave_batch: state=%s envelope_id=%d",
            self._state.name,
            envelope.envelope_id,
        )
        if self._front_lock.try_deliver(envelope):
            self._deliver_to_front(envelope)

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def teardown(self) -> None:
        """Unsubscribe from all topics and reset state."""
        logger.info(
            "ConciergeController.teardown: unsubscribing %d handles, resetting state",
            len(self._subscription_handles),
        )

        # Unsubscribe from all topics
        for handle in self._subscription_handles:
            self._bus.unsubscribe(handle)
        self._subscription_handles.clear()

        # Cancel weave flush task if running
        if self._weave_flush_task and not self._weave_flush_task.done():
            self._weave_flush_task.cancel()
        self._weave_flush_task = None

        # BUG-6 FIX: Cancel digest flush task if running (was missing).
        if self._digest_flush_task and not self._digest_flush_task.done():
            self._digest_flush_task.cancel()
        self._digest_flush_task = None

        if self._deferred_proactive_task and not self._deferred_proactive_task.done():
            self._deferred_proactive_task.cancel()
        self._deferred_proactive_task = None

        # Reset all components to initial state
        self._reset_all_components()

    def _reset_all_components(self) -> None:
        """Reset all components to their initial state."""
        if self._weave_batcher is not None and hasattr(self._weave_batcher, "reset"):
            try:
                self._weave_batcher.reset()
            except Exception:
                logger.warning("WeaveBatcher.reset failed during controller reset", exc_info=True)

        # Reset control and coordination components
        self._turn_state.reset()
        self._front_lock.clear()
        self._cancel_handler.reset()
        self._control_ext.reset()
        self._task_bridge.reset()
        self._interrupt_classifier.reset()
        self._proactive_wake.reset()

        # Clear collection data
        self._history.clear()
        self._active_task_ids.clear()
        self._task_dispatch_turns.clear()
        self._proactive_fill_last_by_key.clear()

        # Reset to None attributes
        self._hil_port = None  # E4.M1.4: unified HIL service handle
        self._weave_batcher = None

        # Reset state variables (BUG-7 FIX: removed duplicate block)
        self._state = ConciergeState.LISTENING
        self._turn_number = 0
        self._front_lock.clear()
        self._cancel_handler.reset()
        self._control_ext.reset()
        self._task_bridge.reset()
        self._interrupt_classifier.reset()
        self._proactive_wake.reset()

        # Clear collection data
        self._history.clear()
        self._active_task_ids.clear()
        self._task_dispatch_turns.clear()
        self._proactive_fill_last_by_key.clear()

        # Reset to None attributes
        self._hil_port = None  # E4.M1.4: unified HIL service handle
        self._weave_batcher = None

        # Reset state variables (BUG-7 FIX: removed duplicate block)
        self._state = ConciergeState.LISTENING
        self._turn_number = 0
        self._hil_port = None  # E4.M1.4: unified HIL service handle
        self._weave_batcher = None

        # Reset state variables (BUG-7 FIX: removed duplicate block)
        self._state = ConciergeState.LISTENING
        self._turn_number = 0
