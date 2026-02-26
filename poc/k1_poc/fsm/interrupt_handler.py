"""
poc.k1_poc.fsm.interrupt_handler -- Interrupt, Cancel & Proactive Wake logic.

V2 Design Ref: Section 4 (INTERRUPTING state), Section 7.2 (cancellation),
               Section 7.1 (proactive wake)

This module extracts the interrupt/cancel/proactive logic from the controller
into testable standalone classes. The controller delegates to these handlers.

Interrupt flow (V2 Section 7.2):
  COMPANIONING (Front idle, Back working)
       |
  user.input arrives (interrupt)
       |
  INTERRUPT_HANDLING
    /       \\
  just chat  cancel!
     |         |
  respond   CANCELLING
     |      (emit cancel to Back)
     |         |
     |    task.failed(cancelled)
     |         |
     +----+----+
          |
     DELIVERING (if results pending)
     or LISTENING (if no results)

Cancel vs Complete race (V2 Section 10.3):
  If task.complete arrives AFTER task.cancel but BEFORE task.failed(cancelled):
    - FSM checks cancelled_tasks set -> task_id is there -> discard result.
    - Cancellation wins. Delivering late result after cancel would be confusing.

Proactive Wake (V2 Section 7.1):
  When task.complete arrives while LISTENING (user idle):
    - No weave needed. Direct presentation.
    - LISTENING -> PROACTIVE_WAKE -> DELIVERING.
"""

from __future__ import annotations

import logging

from poc.k1_poc.config import get_config

logger = logging.getLogger(__name__)


class InterruptClassifier:
    """Classifies whether an interrupt is a chat continuation or a cancel.

    In the POC, this is keyword-based. Production would use Phase 1 intent
    classification to determine if the interrupt contains cancel intent.

    The FSM calls classify() on every user.input during COMPANIONING/PROGRESSING.
    The result determines whether the FSM routes to CANCELLING or continues
    normal conversation flow (respond while Back continues independently).
    """

    # Kept as class constant for backward compatibility; runtime reads from config
    CANCEL_KEYWORDS = frozenset(
        {
            "cancel",
            "stop",
            "abort",
            "nevermind",
            "never mind",
            "don't bother",
            "forget it",
            "skip it",
            "call it off",
        }
    )

    def __init__(self) -> None:
        self._classify_count: int = 0
        self._last_classification: str = ""
        self._cancel_keywords: frozenset[str] = frozenset(get_config().fsm.cancel_keywords)
        logger.info(
            "InterruptClassifier initialized (%d cancel keywords)",
            len(self._cancel_keywords),
        )

    @property
    def classify_count(self) -> int:
        """Number of classifications performed."""
        return self._classify_count

    @property
    def last_classification(self) -> str:
        """Result of last classification: 'cancel' or 'chat'."""
        return self._last_classification

    def classify(self, text: str) -> str:
        """Classify an interrupt as 'cancel' or 'chat'.

        Args:
            text: The user's input text during interrupt.

        Returns:
            'cancel' if cancel intent detected, 'chat' otherwise.
        """
        self._classify_count += 1
        lower = text.lower().strip()

        for keyword in self._cancel_keywords:
            if keyword in lower:
                self._last_classification = "cancel"
                logger.debug("InterruptClassifier: cancel intent in '%s'", text[:50])
                return "cancel"

        self._last_classification = "chat"
        logger.debug("InterruptClassifier: chat continuation for '%s'", text[:50])
        return "chat"

    def reset(self) -> None:
        """Reset classifier state."""
        self._classify_count = 0
        self._last_classification = ""


class ProactiveWakeHandler:
    """Handles task completion while user is idle (LISTENING state).

    When a task completes and the FSM is in LISTENING (no active conversation):
      1. No weave needed -- direct presentation.
      2. FSM transitions: LISTENING -> PROACTIVE_WAKE -> DELIVERING.
      3. Front presents result proactively.

    Example: User asked to search hotels 5 minutes ago, then went idle.
    Hotel search completes. Front says: "Hey! I just heard back about those
    hotels -- here are 5 options in Napa..."

    This is the simplest delivery path (no FrontLock contention, no weave).
    """

    def __init__(self) -> None:
        self._wake_count: int = 0
        self._last_task_id: str = ""
        logger.info("ProactiveWakeHandler initialized")

    @property
    def wake_count(self) -> int:
        """Number of proactive wakes triggered."""
        return self._wake_count

    @property
    def last_task_id(self) -> str:
        """Task ID that triggered the last proactive wake."""
        return self._last_task_id

    def should_wake(self, fsm_state_name: str) -> bool:
        """Check if proactive wake should trigger.

        Args:
            fsm_state_name: Current FSM state name.

        Returns:
            True if FSM is LISTENING (eligible for proactive wake).
        """
        return fsm_state_name == "LISTENING"

    def record_wake(self, task_id: str) -> None:
        """Record that a proactive wake was triggered.

        Args:
            task_id: The completing task that triggered the wake.
        """
        self._wake_count += 1
        self._last_task_id = task_id
        logger.info("ProactiveWakeHandler: wake triggered by task %s", task_id)

    def reset(self) -> None:
        """Reset state."""
        self._wake_count = 0
        self._last_task_id = ""
