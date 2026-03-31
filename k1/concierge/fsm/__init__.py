"""
k1.concierge.fsm -- FSM package for the Concierge POC.

Re-exports:
  - ConciergeState      12 FSM states
  - ConciergeController Event router / FSM controller
  - FSMTurnState         Ephemeral turn tracking (pending_results, cancelled_tasks)
  - FrontLock            Concurrency gate for Front LLM
  - TypedHistoryEntry    History entry written at event boundaries
  - TRANSITION_TABLE     Legal state transitions
  - IllegalTransitionError
  - FrontLockOverflowError

V2 Design Ref: Section 4 (FSM: Event Router & State Machine)
"""

# --- Epics 8.9-8.11 ---
from k1.concierge.fsm.control_extension import ConciergeControlExtension  # noqa: F401
from k1.concierge.fsm.controller import ConciergeController, TypedHistoryEntry  # noqa: F401
from k1.concierge.fsm.dead_letter import DeadLetterPayload, build_dead_letter_payload  # noqa: F401
from k1.concierge.fsm.dead_letter_consumer import DeadLetterConsumer  # noqa: F401
from k1.concierge.fsm.errors import FrontLockOverflowError, IllegalTransitionError  # noqa: F401
from k1.concierge.fsm.front_lock import (  # noqa: F401
    DEFAULT_MAX_QUEUE_DEPTH,
    PRIORITY_ERROR,
    PRIORITY_INFO,
    PRIORITY_INTERACTIVE,
    PRIORITY_RESULT,
    PRIORITY_URGENT,
    TOPIC_PRIORITY,
    FrontLock,
)
from k1.concierge.fsm.history_writer import (  # noqa: F401
    ASSISTANT_ENTRY_TYPES,
    BACK_HISTORY_WINDOW,
    BACK_RELEVANT_TYPES,
    FRONT_HISTORY_WINDOW,
    USER_ENTRY_TYPES,
    HistoryWriter,
    history_to_back_context,
    history_to_front_messages,
)
from k1.concierge.fsm.idempotency import IdempotencyLedger  # noqa: F401
from k1.concierge.fsm.interrupt_handler import InterruptClassifier, ProactiveWakeHandler  # noqa: F401
from k1.concierge.fsm.phase1 import (  # noqa: F401
    Phase1Pipeline,
    Phase1Result,
    StubPhase1Pipeline,
    TurnLock,
)
from k1.concierge.fsm.response_final_table import (  # noqa: F401
    ResponseFinalAction,
    ResponseFinalDecision,
    decide_response_final,
)
from k1.concierge.fsm.states import ConciergeState  # noqa: F401
from k1.concierge.fsm.task_bridge import (  # noqa: F401
    EVICT_ARTIFACTS_AFTER_TURNS,
    PRUNE_COMPLETED_AFTER_TURNS,
    TaskBridge,
)
from k1.concierge.fsm.transition_table import (  # noqa: F401
    TRANSITION_TABLE,
    TRIGGER_CLARIFICATION_DETECTED,
    TRIGGER_INTERRUPT_ROUTED,
    TRIGGER_PENDING_RESULTS_NON_EMPTY,
    TRIGGER_PHASE1_COMPLETE,
    TRIGGER_PROACTIVE_ROUTED,
    is_legal,
    target_state,
)
from k1.concierge.fsm.turn_state import FSMTurnState  # noqa: F401
