"""
poc.k1_poc.fsm.controller -- ConciergeController (FSM event router).

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
from typing import Any

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import IBus
from k1.bus.ports.mailbox import IMailboxRouter
from poc.k1_poc.bus.builders import (
    build_state_updated,
    build_task_complete,
    build_task_dispatch,
    build_task_failed,
    build_turn_completed,
    build_turn_started,
)
from poc.k1_poc.bus.topics import (
    TOPIC_AFFECT_UPDATE,
    TOPIC_ARTIFACT_CREATED,
    TOPIC_CLARIFICATION_REQUEST,
    TOPIC_CLARIFICATION_RESPONSE,
    TOPIC_DAG_COMPLETED,
    TOPIC_FINAL_RESPONSE,
    TOPIC_FINDINGS_READY,
    TOPIC_PROACTIVE_FILL,
    TOPIC_TASK_CANCEL,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_RESUME,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TOOL_COMPLETED,
    TOPIC_TOOL_STARTED,
    TOPIC_USER_INPUT,
    TOPIC_WEAVE_BATCH,
)
from poc.k1_poc.config import get_config
from poc.k1_poc.fsm.control_extension import ConciergeControlExtension
from poc.k1_poc.fsm.errors import IllegalTransitionError
from poc.k1_poc.fsm.front_lock import FrontLock
from poc.k1_poc.fsm.interrupt_handler import InterruptClassifier, ProactiveWakeHandler
from poc.k1_poc.fsm.phase1 import Phase1Result, StubPhase1Pipeline, TurnLock
from poc.k1_poc.fsm.states import ConciergeState
from poc.k1_poc.fsm.task_bridge import TaskBridge
from poc.k1_poc.fsm.transition_table import (
    TRIGGER_INTERRUPT_ROUTED,
    TRIGGER_PENDING_RESULTS_NON_EMPTY,
    TRIGGER_PROACTIVE_ROUTED,
    TRIGGER_SAME_TURN_COMPLETE,
    is_legal,
    target_state,
)
from poc.k1_poc.fsm.turn_state import FSMTurnState
from poc.k1_poc.orchestrator.routing import route_task_sync
from poc.k1_poc.protocols.cancel_handler import CancellationHandler
from poc.k1_poc.protocols.hitl_wiring import build_resume_context
from poc.k1_poc.protocols.suspension_manager import SuspensionManager
from poc.k1_poc.protocols.weave_batcher import WEAVE_BATCH_WINDOW_MS
from poc.k1_poc.task.complexity import ComplexityTier
from poc.k1_poc.task.dispatch import TaskDispatch
from poc.k1_poc.task.intent import TaskIntent

logger = logging.getLogger(__name__)


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
        self._turn_state = FSMTurnState()
        self._front_lock = FrontLock()
        self._cancel_handler = CancellationHandler()
        self._suspension_manager = SuspensionManager()
        self._control_ext = ConciergeControlExtension()
        self._task_bridge = TaskBridge()
        self._phase1_pipeline = StubPhase1Pipeline()
        self._turn_lock = TurnLock()
        self._interrupt_classifier = InterruptClassifier()
        self._proactive_wake = ProactiveWakeHandler()
        self._history: list[TypedHistoryEntry] = []
        self._active_task_ids: set[str] = set()
        self._task_dispatch_turns: dict[str, int] = {}  # task_id -> turn dispatched
        self._orchestrator: Any | None = None
        self._hil_coordinator: Any | None = None  # HILCoordinator for HITL orchestration
        self._weave_batcher: Any | None = None  # WeaveBatcher for queue mgmt
        self._subscription_handles: list[Any] = []
        self._seen_user_input_ids: set[int] = set()
        self._weave_flush_task: asyncio.Task[None] | None = None
        self._history_sink: Any | None = None  # Optional SS history_active section
        self._ss: Any | None = None  # Optional SessionStateManager for SS reads
        self._current_turn_user_text: str = ""  # Tracks user text for turn pairing
        logger.info(
            "ConciergeController.__init__: assembling sub-components "
            "(FrontLock, CancelHandler, SuspensionManager, ControlExtension, "
            "TaskBridge, Phase1Pipeline, TurnLock, InterruptClassifier, ProactiveWake)",
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
    def phase1_pipeline(self) -> StubPhase1Pipeline:
        """Phase 1 classification pipeline (Epic 3.1)."""
        return self._phase1_pipeline

    @property
    def turn_lock(self) -> TurnLock:
        """TurnLock -- sequencing gate for Phase 1 (Epic 3.1)."""
        return self._turn_lock

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

    def set_history_sink(self, section: Any) -> None:
        """Attach SS history_active section for turn persistence.

        When set, the FSM pushes completed turns (user text + final
        response) to the section at response.final boundaries so
        the front handler's build_chat_history reads real context.
        """
        self._history_sink = section
        logger.info("ConciergeController.set_history_sink: attached")

    def set_hitl_coordinator(self, coordinator: Any) -> None:
        """Attach HILCoordinator for suspension limit enforcement, safety
        band escalation, L2 defense-in-depth, and crash recovery.

        When set, _on_task_suspended delegates to the coordinator for
        limit checks instead of using bare SuspensionManager directly.
        The coordinator's internal SuspensionManager replaces the
        controller's bare one.
        """
        self._hil_coordinator = coordinator
        # Use the coordinator's SuspensionManager so store/pop/get
        # context calls go through the same instance.
        if hasattr(coordinator, "_suspension_mgr"):
            self._suspension_manager = coordinator._suspension_mgr
        logger.info(
            "ConciergeController.set_hitl_coordinator: attached %s",
            type(coordinator).__name__,
        )

    def set_session_state(self, ss: Any) -> None:
        """Attach SessionStateManager for SS reads (scoreboard, narrative).

        Used to inject scoreboard referents into dispatch payloads and
        read narrative_active for context enrichment.
        """
        self._ss = ss
        logger.info("ConciergeController.set_session_state: attached")

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
            ("k1.orchestration.dag.completed", self._on_dag_completed),
            (TOPIC_TASK_COMPLETE, self._on_task_complete),
            (TOPIC_TASK_FAILED, self._on_task_failed),
            (TOPIC_TASK_CANCEL, self._on_task_cancel),
            (TOPIC_TASK_SUSPENDED, self._on_task_suspended),
            (TOPIC_TASK_RESUME, self._on_task_resume),
            (TOPIC_FINDINGS_READY, self._on_findings_ready),
            (TOPIC_CLARIFICATION_REQUEST, self._on_clarification_request),
            (TOPIC_CLARIFICATION_RESPONSE, self._on_clarification_response),
            (TOPIC_ARTIFACT_CREATED, self._on_artifact_created),
            (TOPIC_AFFECT_UPDATE, self._on_affect_update),
            (TOPIC_PROACTIVE_FILL, self._on_proactive_fill),
            (TOPIC_TOOL_STARTED, self._on_tool_started),
            (TOPIC_TOOL_COMPLETED, self._on_tool_completed),
            (TOPIC_WEAVE_BATCH, self._on_weave_batch),
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
        if expected_target != to_state:
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
        """
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
        env_id = envelope.envelope_id
        if env_id and env_id in self._seen_user_input_ids:
            logger.debug(
                "FSM._on_user_input: DEDUP drop envelope_id=%d (already processed)",
                env_id,
            )
            return
        if env_id:
            self._seen_user_input_ids.add(env_id)
            # Bound the set size to avoid unbounded growth
            if len(self._seen_user_input_ids) > 200:
                self._seen_user_input_ids.clear()

        # Topic guard: TimingChain _cascade_causal can dispatch
        # child envelopes through the parent's handler chain.  A
        # state.updated or turn.started child of a user.input must
        # NOT be processed as user input.
        if envelope.topic != TOPIC_USER_INPUT:
            logger.debug(
                "FSM._on_user_input: TOPIC GUARD -- ignoring topic=%s "
                "envelope_id=%d (expected %s)",
                envelope.topic,
                envelope.envelope_id,
                TOPIC_USER_INPUT,
            )
            return

        payload = _parse_payload(envelope)
        text = payload.get("text", "")
        logger.info(
            "FSM._on_user_input: state=%s envelope_id=%d text=%s",
            self._state.name,
            envelope.envelope_id,
            text[:60],
        )

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

        if self._state == ConciergeState.COMPANIONING:
            # Interrupt -- classify as cancel or chat continuation (Epic 3)
            self._interrupt_classifier.classify(text)
            self._turn_number += 1
            self._write_history(
                entry_type="user",
                role="user",
                text=text,
                source="user",
                envelope=envelope,
            )
            self._transition(
                ConciergeState.INTERRUPT_HANDLING,
                TOPIC_USER_INPUT,
                envelope,
            )
            # Route interrupt to DISPATCHING
            self._transition(
                ConciergeState.DISPATCHING,
                TRIGGER_INTERRUPT_ROUTED,
                envelope,
            )
            # Emit turn.started
            self._bus.publish(
                build_turn_started(
                    payload={
                        "turn_number": self._turn_number,
                        "trigger": "interrupt",
                    },
                    parent_id=envelope.envelope_id,
                )
            )
            # Phase 1 -> DISPATCHING
            self._run_phase1(envelope)
            return

        if self._state == ConciergeState.PROGRESSING:
            # Interrupt during tool execution -- classify intent (Epic 3)
            self._interrupt_classifier.classify(text)
            self._turn_number += 1
            self._write_history(
                entry_type="user",
                role="user",
                text=text,
                source="user",
                envelope=envelope,
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
            self._run_phase1(envelope)
            return

        if self._state in (
            ConciergeState.LISTENING,
            ConciergeState.CLARIFYING_USER,
        ):
            # Normal turn start or clarification answer
            self._turn_number += 1
            self._current_turn_user_text = text
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
            # Phase 1 -> DISPATCHING
            self._run_phase1(envelope)
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

        # Any other state (DISPATCHING): genuinely re-entrant.
        # TimingChain causal cascade can re-deliver user.input to this
        # handler while the FSM is already processing the original.
        # Safe to drop because the original envelope is already being
        # processed.
        logger.debug(
            "user.input arrived in state %s -- dropping (original already processing)",
            self._state.name,
        )

    def _run_phase1(self, envelope: Envelope) -> None:
        """Run Phase 1 (deterministic classification) within DISPATCHING.

        Phase 1 writes scoreboard, affective_now, control to SessionState.
        Uses TurnLock to guarantee writes complete before Front LLM reads.
        Delegates to StubPhase1Pipeline for classification (Epic 3.1).
        """
        logger.info(
            "FSM._run_phase1: envelope_id=%d state=%s",
            envelope.envelope_id,
            self._state.name,
        )
        payload = _parse_payload(envelope)
        text = payload.get("text", "")

        # Acquire TurnLock -- Phase 1 must complete before Front reads
        self._turn_lock.acquire("phase1")

        # Run Phase 1 classification
        result: Phase1Result = self._phase1_pipeline.classify(text)

        # Update ConciergeControlExtension with complexity tier
        self._control_ext.set_complexity_tier(result.complexity_tier)

        # Attach Phase 1 metadata to the user history entry (last entry)
        if self._history:
            last = self._history[-1]
            if last.entry_type == "user":
                last.metadata.update(result.to_metadata())

        # Release TurnLock -- Phase 1 writes committed
        self._turn_lock.release()

        # Already in DISPATCHING -- deliver to Front via FrontLock
        if self._front_lock.try_deliver(envelope):
            self._deliver_to_front(envelope)

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
            self._router.deliver("front_half", envelope)
        except Exception:
            logger.exception(
                "Failed to deliver to front_half: topic=%s, envelope_id=%d",
                envelope.topic,
                envelope.envelope_id,
            )

    def _deliver_to_back(self, envelope: Envelope) -> None:
        """Deliver an envelope to the Back LLM actor via MailboxRouter."""
        logger.info(
            "FSM._deliver_to_back: envelope_id=%d topic=%s state=%s",
            envelope.envelope_id,
            envelope.topic,
            self._state.name,
        )
        try:
            self._router.deliver("back_half", envelope)
        except Exception:
            logger.exception(
                "Failed to deliver to back_half: topic=%s, envelope_id=%d",
                envelope.topic,
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
        payload = _parse_payload(envelope)
        dispatch = _task_dispatch_from_payload(payload)
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

        if record.tier == ComplexityTier.HIGH:
            logger.warning(
                "FSM._route_via_orchestrator: HIGH tier not implemented, failing task_id=%s",
                dispatch.task_id,
            )
            env = build_task_failed(
                payload={
                    "task_id": dispatch.task_id,
                    "reason": "HIGH tier not implemented in POC",
                    "error_code": "TIER_NOT_IMPLEMENTED",
                },
                parent_id=envelope.envelope_id,
            )
            self._bus.publish(env)
            # Clean up registration since task won't execute
            self._active_task_ids.discard(dispatch.task_id)
            self._control_ext.remove_active_task(dispatch.task_id)
            return

        # Build a canonical dispatch envelope with task_id guaranteed
        canonical_payload = dispatch.to_dict()
        canonical_payload["task_id"] = dispatch.task_id

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

        if record.tier == ComplexityTier.MEDIUM:
            if self._orchestrator is None or record.envelope is None:
                logger.warning(
                    "FSM._route_via_orchestrator: MEDIUM tier fallback to Back (orchestrator unavailable), task_id=%s",
                    dispatch.task_id,
                )
                self._deliver_to_back(canonical_env)
                return

            logger.info(
                "FSM._route_via_orchestrator: routing MEDIUM tier task_id=%s via OrchestratorStub",
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

        Behavior depends on FSM state (Weave Protocol, V2 Section 4):
          LISTENING     -> PROACTIVE_WAKE -> DELIVERING (direct presentation)
          COMPANIONING  -> Queue in pending_results, transition to DELIVERING
          PROGRESSING   -> Queue or transition to DELIVERING
          DISPATCHING   -> Queue in pending_results
          DELIVERING    -> Queue in pending_results
        """
        # Guard: TimingChain _cascade_causal can dispatch child envelopes
        # through the parent's handler chain (same bug as _on_response_final).
        if envelope.topic != TOPIC_TASK_COMPLETE:
            logger.debug(
                "FSM._on_task_complete: TOPIC GUARD -- ignoring topic=%s envelope_id=%d",
                envelope.topic,
                envelope.envelope_id,
            )
            return

        payload = _parse_payload(envelope)
        task_id = payload.get("task_id", "")
        logger.info(
            "FSM._on_task_complete: state=%s envelope_id=%d task_id=%s",
            self._state.name,
            envelope.envelope_id,
            task_id,
        )

        # Check cancel dedup via CancellationHandler (SOT)
        if self._cancel_handler.is_cancelled(task_id):
            logger.info("task.complete for cancelled task %s -- discarding", task_id)
            self._cancel_handler.handle_late_completion(task_id)
            self._active_task_ids.discard(task_id)
            self._task_dispatch_turns.pop(task_id, None)
            self._control_ext.remove_active_task(task_id)
            return

        # Remove from active tasks
        self._active_task_ids.discard(task_id)
        self._control_ext.remove_active_task(task_id)
        self._task_bridge.complete_task(task_id)
        dispatch_turn = self._task_dispatch_turns.pop(task_id, 0)

        # Skip PRESENT-mode delivery for tasks that were dispatched AND
        # completed in the same turn.  The Front STANDARD response already
        # told the user about these tasks ("I've set a reminder..."), so
        # re-presenting them via PRESENT mode produces a duplicate box.
        # Only PRESENT when the task completes in a LATER turn (proactive).
        if dispatch_turn == self._turn_number and self._state == ConciergeState.COMPANIONING:
            logger.info(
                "FSM._on_task_complete: same-turn completion for task_id=%s "
                "(dispatched_turn=%d, current_turn=%d) -- skipping PRESENT "
                "(Front STANDARD already covered this task)",
                task_id,
                dispatch_turn,
                self._turn_number,
            )
            # If no more active tasks, transition to LISTENING
            if not self._active_task_ids:
                self._transition(
                    ConciergeState.LISTENING,
                    TRIGGER_SAME_TURN_COMPLETE,
                    envelope,
                )
                self._emit_turn_completed(envelope)
                self._drain_front_lock_queue()
            return

        if self._state == ConciergeState.LISTENING:
            # Proactive wake -- task completed while idle
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
            # Deliver directly to Front
            if self._front_lock.try_deliver(envelope):
                self._deliver_to_front(envelope)
            return

        if self._state in (
            ConciergeState.COMPANIONING,
            ConciergeState.PROGRESSING,
        ):
            # Normal completion -- transition to DELIVERING
            self._transition(
                ConciergeState.DELIVERING,
                TOPIC_TASK_COMPLETE,
                envelope,
            )
            # Deliver to Front for result presentation
            if self._front_lock.try_deliver(envelope):
                self._deliver_to_front(envelope)
            else:
                # Front busy -- queue result for later
                self._turn_state.enqueue_result(task_id, payload, envelope)
            return

        # DISPATCHING or DELIVERING -- queue for later
        self._turn_state.enqueue_result(task_id, payload, envelope)
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

        self._write_history(
            entry_type="error" if reason != "cancelled" else "cancel_confirmed",
            role="system",
            text=payload.get("error_message", ""),
            source="back",
            task_id=task_id,
            envelope=envelope,
        )

    def _on_task_cancel(self, envelope: Envelope) -> None:
        """Handle k1.orchestration.task.cancel.v1.

        Cancel request from Front. Register in FSMTurnState, transition
        to CANCELLING, deliver cancel to Back.
        """
        payload = _parse_payload(envelope)
        task_id = payload.get("task_id", "")
        logger.info(
            "FSM._on_task_cancel: state=%s envelope_id=%d task_id=%s",
            self._state.name,
            envelope.envelope_id,
            task_id,
        )

        self._cancel_handler.request_cancel(task_id)

        # Only transition to CANCELLING from valid states
        if self._state in (
            ConciergeState.COMPANIONING,
            ConciergeState.PROGRESSING,
            ConciergeState.DISPATCHING,
        ):
            # Force transition -- CANCELLING is an override
            from_state = self._state
            self._state = ConciergeState.CANCELLING
            logger.info(
                "FSM %s -> CANCELLING on task.cancel [task_id=%s]",
                from_state.name,
                task_id,
            )
            self._bus.publish(
                build_state_updated(
                    payload={
                        "from_state": from_state.name,
                        "to_state": "CANCELLING",
                        "trigger": TOPIC_TASK_CANCEL,
                        "turn_number": self._turn_number,
                        "task_id": task_id,
                    },
                    parent_id=envelope.envelope_id,
                )
            )

        # Deliver cancel to Back
        self._deliver_to_back(envelope)

    def _on_task_suspended(self, envelope: Envelope) -> None:
        """Handle k1.orchestration.task.suspended.v1 (HITL entry point).

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
        # Guard: TimingChain _cascade_causal can dispatch child envelopes
        # through the parent's handler chain (same pattern as _on_task_complete).
        if envelope.topic != TOPIC_TASK_SUSPENDED:
            logger.debug(
                "FSM._on_task_suspended: TOPIC GUARD -- ignoring topic=%s envelope_id=%d",
                envelope.topic,
                envelope.envelope_id,
            )
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

        # -- HILCoordinator path: limit enforcement + safety band -----
        if self._hil_coordinator is not None:
            hil_count = self._hil_coordinator.get_hil_count(task_id) + 1
            max_rounds = self._hil_coordinator._config.max_rounds
            if hil_count > max_rounds:
                logger.warning(
                    "FSM._on_task_suspended: task_id=%s exceeded max HITL "
                    "rounds %d/%d — blocking suspension",
                    task_id,
                    hil_count,
                    max_rounds,
                )
                return
            # Track the count in the coordinator
            self._hil_coordinator._hil_counts[task_id] = hil_count

        # Store suspension context via SuspensionManager (SOT) regardless
        self._suspension_manager.store_context(task_id, payload)
        self._task_bridge.suspend_task(task_id)

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

        Front relayed user's HITL answer. Build structured ResumeContext
        from the stored suspension state, enrich the envelope, deliver
        resume to Back, and transition to COMPANIONING.
        """
        payload = _parse_payload(envelope)
        task_id = payload.get("task_id", "")
        logger.info(
            "FSM._on_task_resume: state=%s envelope_id=%d task_id=%s",
            self._state.name,
            envelope.envelope_id,
            task_id,
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

        # Pop stored suspension context and build structured resume
        stored_context = self._suspension_manager.pop_context(task_id)
        self._task_bridge.resume_task(task_id)

        # Build ResumeContext when we have stored suspension state
        if stored_context is not None:
            hil_type = stored_context.get("hil_type", "clarification")
            resume_ctx = build_resume_context(
                task_id=task_id,
                hil_type=hil_type,
                resolution=resolution if isinstance(resolution, dict) else {},
                findings_so_far=stored_context.get("react_history", []),
                original_task=stored_context.get("original_task", {}),
                last_iteration=stored_context.get("iteration", 0),
                total_budget=stored_context.get("total_budget", 10),
            )
            # Inject resume context into the envelope payload for Back
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
                "FSM._on_task_resume: built ResumeContext for task_id=%s "
                "hil_type=%s findings=%d remaining_budget=%d",
                task_id,
                hil_type,
                len(resume_ctx.findings_so_far),
                resume_ctx.remaining_budget,
            )

        # Notify coordinator of user response (sync bookkeeping)
        if self._hil_coordinator is not None:
            self._hil_coordinator._pending_requests.pop(task_id, None)

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

    def _on_response_final(self, envelope: Envelope) -> None:
        """Handle k1.response.final.v1 -- the turn exit point.

        Front delivered its final response. Check pending_results for
        Weave, then transition to LISTENING or WEAVING.
        """
        # Guard: TimingChain _cascade_causal can dispatch child envelopes
        # (e.g. state.updated.v1) through the parent's handler chain.
        # Only process envelopes with the correct topic.
        if envelope.topic != TOPIC_FINAL_RESPONSE:
            logger.debug(
                "FSM._on_response_final: TOPIC GUARD -- ignoring topic=%s envelope_id=%d",
                envelope.topic,
                envelope.envelope_id,
            )
            return

        payload = _parse_payload(envelope)
        text = payload.get("text", "")
        logger.info(
            "FSM._on_response_final: state=%s envelope_id=%d text=%s",
            self._state.name,
            envelope.envelope_id,
            text[:60],
        )

        # Determine history entry type based on state.
        # For DELIVERING/WEAVING states (proactive/weave responses),
        # detect fallback text and exclude it from chat history to
        # prevent LLM context pollution.
        _budget_fb = get_config().react.front_budget_fallback
        _degen_fb = get_config().react.front_degenerate_fallback
        is_fallback = text in (_budget_fb, _degen_fb)

        if self._state == ConciergeState.WEAVING:
            entry_type = "weave"
        elif self._state == ConciergeState.DELIVERING and is_fallback:
            # Fallback text from proactive PRESENT mode -- don't
            # pollute history as 'final' (which build_chat_history
            # includes). Use a distinct type so it's excluded.
            entry_type = "proactive_fallback"
        elif self._state == ConciergeState.DELIVERING:
            entry_type = "proactive"  # genuine proactive response
        else:
            entry_type = "final"

        self._write_history(
            entry_type=entry_type,
            role="assistant",
            text=text,
            source="front",
            envelope=envelope,
        )

        # Push completed turn to SS history_active if sink is wired.
        # Skip fallback text -- it's not a meaningful response.
        if self._history_sink and text and self._current_turn_user_text and not is_fallback:
            try:
                self._history_sink.add_turn(
                    user_message=self._current_turn_user_text,
                    assistant_response=text,
                )
            except Exception:
                logger.debug("FSM: failed to push turn to history_sink", exc_info=True)

        # Release FrontLock -- strategy depends on next state:
        # WEAVING path: set busy=False so weave flush can try_deliver.
        # LISTENING path: call release() to drain queued user input.
        # Defer the actual release to after state transition decision.
        # Signal WeaveBatcher that Front is idle (moves queued -> pending)
        if self._weave_batcher is not None:
            self._weave_batcher.set_front_busy(False)

        if self._state == ConciergeState.DISPATCHING:
            # Check for pending back results before transitioning.
            # Back may have completed tasks while front was processing
            # the user turn -- those results are queued and must be
            # flushed via WEAVING, not orphaned.
            if self._turn_state.has_pending_results:
                self._front_lock.busy = False  # free for weave flush
                self._transition(
                    ConciergeState.WEAVING,
                    TRIGGER_PENDING_RESULTS_NON_EMPTY,
                    envelope,
                )
                self._schedule_weave_flush(envelope)
                return
            # Active back tasks dispatched but not yet completed --
            # transition to COMPANIONING and wait for task.complete
            # (V2 Section 4: COMPANIONING waits for task.complete).
            if self._active_task_ids:
                logger.info(
                    "FSM._on_response_final: DISPATCHING with %d active "
                    "task(s) -- transitioning to COMPANIONING",
                    len(self._active_task_ids),
                )
                self._transition(
                    ConciergeState.COMPANIONING,
                    TOPIC_TASK_DISPATCH,
                    envelope,
                )
                self._front_lock.busy = False
                return
            # No pending results AND no active tasks -- conversational-only turn
            self._transition(
                ConciergeState.LISTENING,
                TOPIC_FINAL_RESPONSE,
                envelope,
            )
            self._emit_turn_completed(envelope)
            self._drain_front_lock_queue()
            return

        if self._turn_state.has_pending_results:
            self._front_lock.busy = False  # free for weave flush
            # Pending results exist -- transition to WEAVING
            if self._state == ConciergeState.DELIVERING:
                self._transition(
                    ConciergeState.WEAVING,
                    TRIGGER_PENDING_RESULTS_NON_EMPTY,
                    envelope,
                )
            elif self._state == ConciergeState.WEAVING:
                # More pending after a weave cycle -- stay in WEAVING.
                # But skip if a weave flush is already scheduled to
                # avoid re-transition loops (the flush will drain them).
                if self._weave_flush_task and not self._weave_flush_task.done():
                    logger.debug(
                        "FSM._on_response_final: WEAVING flush already scheduled, "
                        "skipping re-transition (pending=%d)",
                        len(self._turn_state.pending_results),
                    )
                    return
                self._transition(
                    ConciergeState.WEAVING,
                    TRIGGER_PENDING_RESULTS_NON_EMPTY,
                    envelope,
                )
            self._schedule_weave_flush(envelope)
            return

        # No pending results -- transition to LISTENING
        if self._state in (
            ConciergeState.DELIVERING,
            ConciergeState.WEAVING,
        ):
            self._transition(
                ConciergeState.LISTENING,
                TOPIC_FINAL_RESPONSE,
                envelope,
            )
        elif self._state == ConciergeState.COMPANIONING:
            if self._active_task_ids:
                # Back tasks still running. Stay in COMPANIONING so
                # task.complete triggers DELIVERING -> PRESENT mode
                # (V2 Section 4: COMPANIONING waits for task.complete).
                # Release FrontLock so front can accept the PRESENT
                # envelope when back completes.
                logger.info(
                    "FSM._on_response_final: COMPANIONING with %d active "
                    "task(s) -- staying in COMPANIONING (not LISTENING)",
                    len(self._active_task_ids),
                )
                self._front_lock.busy = False
                return
            # No active tasks -- purely conversational turn that
            # happened to pass through COMPANIONING (e.g. dispatch +
            # immediate completion race).  Safe to go to LISTENING.
            self._transition(
                ConciergeState.LISTENING,
                TOPIC_FINAL_RESPONSE,
                envelope,
            )
        elif self._state == ConciergeState.CLARIFYING_WORKER:
            # HITL relay response delivered. Transition out of
            # CLARIFYING_WORKER so the FSM can continue processing
            # remaining back tasks or return to idle.
            if self._active_task_ids:
                # Back tasks still running. Go to COMPANIONING so
                # task.complete can trigger DELIVERING -> PRESENT mode.
                logger.info(
                    "FSM._on_response_final: CLARIFYING_WORKER -> COMPANIONING "
                    "with %d active task(s)",
                    len(self._active_task_ids),
                )
                self._transition(
                    ConciergeState.COMPANIONING,
                    TOPIC_FINAL_RESPONSE,
                    envelope,
                )
                self._front_lock.busy = False
                return
            # No active tasks. Go to LISTENING.
            logger.info(
                "FSM._on_response_final: CLARIFYING_WORKER -> LISTENING " "(no active tasks)",
            )
            self._transition(
                ConciergeState.LISTENING,
                TOPIC_FINAL_RESPONSE,
                envelope,
            )
        elif self._state == ConciergeState.LISTENING:
            # Already LISTENING -- spurious FINAL_RESPONSE (e.g. from
            # an observability event that mistakenly triggered front).
            # Do NOT emit turn.completed to avoid a feedback loop:
            #   front -> FINAL_RESPONSE -> turn.completed -> front -> ...
            logger.warning(
                "FSM._on_response_final: ignoring in LISTENING state "
                "(envelope_id=%d) -- no turn.completed emitted",
                envelope.envelope_id,
            )
            return

        self._emit_turn_completed(envelope)

        # Drain FrontLock queue -- handles user input that arrived
        # during DELIVERING/WEAVING states.
        self._drain_front_lock_queue()

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

    def _emit_turn_completed(self, envelope: Envelope) -> None:
        """Emit turn.completed observability event, advance narrative arc, and check deferred HITL."""
        self._bus.publish(
            build_turn_completed(
                payload={
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
            from poc.k1_poc.bus.builders import build_task_suspended

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
            self._transition(
                ConciergeState.CLARIFYING_WORKER,
                TOPIC_TASK_SUSPENDED,
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
        """Build a synthetic weave batch envelope for Front delivery."""
        from poc.k1_poc.bus.builders import build_weave_batch

        return build_weave_batch(
            payload={
                "results": results,
                "count": len(results),
                "current_thread": "",
            },
            parent_id=parent_id,
        )

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
        results = self._turn_state.drain_results()
        if not results:
            return
        weave_envelope = self._build_weave_envelope(results, parent_id)
        if self._front_lock.try_deliver(weave_envelope):
            self._deliver_to_front(weave_envelope)

    # ------------------------------------------------------------------
    # Observability / passthrough handlers
    # ------------------------------------------------------------------

    def _on_tool_started(self, envelope: Envelope) -> None:
        """Handle k1.tool.started.v1 -- observability: track tool execution."""
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
        # Deliver to Front via FrontLock (informational)
        if self._front_lock.try_deliver(envelope):
            self._deliver_to_front(envelope)

    def _on_clarification_request(self, envelope: Envelope) -> None:
        """Handle k1.orchestration.clarification.request.v1."""
        # Routed through task.suspended in most cases.
        # Direct clarification requests are forwarded to Front.
        if self._front_lock.try_deliver(envelope):
            self._deliver_to_front(envelope)

    def _on_clarification_response(self, envelope: Envelope) -> None:
        """Handle k1.orchestration.clarification.response.v1."""
        # Front -> Back clarification response. Forward to Back.
        self._deliver_to_back(envelope)

    def _on_artifact_created(self, envelope: Envelope) -> None:
        """Handle k1.session.artifact.created.v1."""
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
        logger.debug("Affect update received (RELAXED)")

    def _on_proactive_fill(self, envelope: Envelope) -> None:
        """Handle k1.proactive.fill.v1 -- RELAXED, observability only."""
        logger.debug("Proactive fill received (RELAXED)")

    def _on_weave_batch(self, envelope: Envelope) -> None:
        """Handle k1.internal.weave.batch.v1 -- weave timer fired."""
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
        for handle in self._subscription_handles:
            self._bus.unsubscribe(handle)
        self._subscription_handles.clear()
        if self._weave_flush_task and not self._weave_flush_task.done():
            self._weave_flush_task.cancel()
        self._weave_flush_task = None
        self._turn_state.reset()
        self._front_lock.clear()
        self._cancel_handler.reset()
        self._control_ext.reset()
        self._task_bridge.reset()
        self._turn_lock.reset()
        self._interrupt_classifier.reset()
        self._hil_coordinator = None
        self._weave_batcher = None
        self._proactive_wake.reset()
        self._history.clear()
        self._active_task_ids.clear()
        self._task_dispatch_turns.clear()
        self._state = ConciergeState.LISTENING
        self._turn_number = 0
