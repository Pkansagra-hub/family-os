"""
FSM State Constraints
=====================

Fix 2: Make FSM states RESTRICTIVE, not just observational.

Each state has ALLOWED and FORBIDDEN actions.
The FSM enforces these - it's not just observing, it's CONTROLLING.

ACKING:
  - ALLOWED: Classify intent, update beliefs, compress state
  - FORBIDDEN: Ask new questions, make tool calls

EXECUTING:
  - ALLOWED: Execute tools, update plan state
  - FORBIDDEN: Replan, change intent, ask questions

DELIVERING:
  - ALLOWED: Format response, record turn
  - FORBIDDEN: Make tool calls, change state

RECOVERY:
  - ALLOWED: Restore state, re-establish context
  - FORBIDDEN: Detect new intents, start new plans
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Set

from poc.session_state_demo.concierge.states import ConciergeState

logger = logging.getLogger(__name__)


class ActionCategory(Enum):
    """Categories of actions the FSM can take."""

    # Classification actions
    CLASSIFY_INTENT = "classify_intent"
    DETECT_GAPS = "detect_gaps"

    # State mutation actions
    UPDATE_BELIEFS = "update_beliefs"
    UPDATE_PERSONA = "update_persona"
    COMPRESS_STATE = "compress_state"  # Meaningful ACK compression

    # Tool actions
    EXECUTE_TOOL = "execute_tool"
    SPAWN_AGENT = "spawn_agent"

    # Plan actions
    UPDATE_PLAN = "update_plan"
    LOCK_PLAN_ITEM = "lock_plan_item"
    REPLAN = "replan"

    # Conversation actions
    ASK_QUESTION = "ask_question"
    DELIVER_RESPONSE = "deliver_response"
    RECORD_TURN = "record_turn"

    # Context actions
    RESOLVE_REFERENCES = "resolve_references"
    RESTORE_STATE = "restore_state"
    DETECT_NEW_INTENT = "detect_new_intent"


@dataclass
class StateConstraints:
    """Constraints for a specific FSM state."""

    state: ConciergeState
    allowed: Set[ActionCategory]
    forbidden: Set[ActionCategory]
    description: str = ""

    def is_allowed(self, action: ActionCategory) -> bool:
        """Check if an action is allowed in this state."""
        if action in self.forbidden:
            return False
        if action in self.allowed:
            return True
        # Default: allowed if not explicitly forbidden
        return True

    def validate_action(self, action: ActionCategory) -> tuple[bool, str]:
        """Validate an action and return (allowed, reason)."""
        if action in self.forbidden:
            return False, f"{action.value} is FORBIDDEN in {self.state.name} state"
        if action in self.allowed:
            return True, f"{action.value} is allowed in {self.state.name} state"
        return True, f"{action.value} is implicitly allowed (not forbidden)"


# Define constraints for each state
STATE_CONSTRAINTS = {
    ConciergeState.LISTENING: StateConstraints(
        state=ConciergeState.LISTENING,
        description="Waiting for user input - minimal actions allowed",
        allowed={
            ActionCategory.RECORD_TURN,
        },
        forbidden={
            ActionCategory.EXECUTE_TOOL,
            ActionCategory.SPAWN_AGENT,
            ActionCategory.ASK_QUESTION,
            ActionCategory.DELIVER_RESPONSE,
            ActionCategory.REPLAN,
        },
    ),
    ConciergeState.ACKING: StateConstraints(
        state=ConciergeState.ACKING,
        description="Processing input - classify and compress, DO NOT ask questions",
        allowed={
            ActionCategory.CLASSIFY_INTENT,
            ActionCategory.RESOLVE_REFERENCES,
            ActionCategory.UPDATE_BELIEFS,
            ActionCategory.UPDATE_PERSONA,
            ActionCategory.COMPRESS_STATE,  # Meaningful ACK compression
        },
        forbidden={
            ActionCategory.ASK_QUESTION,  # NO asking new questions in ACKING!
            ActionCategory.EXECUTE_TOOL,  # Tools happen in EXECUTING
            ActionCategory.SPAWN_AGENT,  # Agents happen in EXECUTING
            ActionCategory.REPLAN,  # No replanning - accept what we got
        },
    ),
    ConciergeState.CLARIFYING: StateConstraints(
        state=ConciergeState.CLARIFYING,
        description="Asking for missing info - only question-related actions",
        allowed={
            ActionCategory.ASK_QUESTION,
            ActionCategory.DETECT_GAPS,
        },
        forbidden={
            ActionCategory.EXECUTE_TOOL,
            ActionCategory.SPAWN_AGENT,
            ActionCategory.REPLAN,
            ActionCategory.LOCK_PLAN_ITEM,
        },
    ),
    ConciergeState.DISPATCHING: StateConstraints(
        state=ConciergeState.DISPATCHING,
        description="Routing to execution - no actions, just routing",
        allowed={
            ActionCategory.CLASSIFY_INTENT,  # Determine routing
        },
        forbidden={
            ActionCategory.EXECUTE_TOOL,
            ActionCategory.SPAWN_AGENT,
            ActionCategory.ASK_QUESTION,
            ActionCategory.DELIVER_RESPONSE,
            ActionCategory.REPLAN,
        },
    ),
    ConciergeState.EXECUTING: StateConstraints(
        state=ConciergeState.EXECUTING,
        description="Executing tools/LLM - NO replanning, NO questions",
        allowed={
            ActionCategory.EXECUTE_TOOL,
            ActionCategory.SPAWN_AGENT,
            ActionCategory.UPDATE_PLAN,
            ActionCategory.LOCK_PLAN_ITEM,
            ActionCategory.UPDATE_BELIEFS,  # Beliefs from tool results
        },
        forbidden={
            ActionCategory.REPLAN,  # NO replanning during execution!
            ActionCategory.ASK_QUESTION,  # NO questions during execution!
            ActionCategory.DETECT_NEW_INTENT,  # NO changing what we're doing
        },
    ),
    ConciergeState.DELIVERING: StateConstraints(
        state=ConciergeState.DELIVERING,
        description="Delivering response - format and send ONLY",
        allowed={
            ActionCategory.DELIVER_RESPONSE,
            ActionCategory.RECORD_TURN,
            ActionCategory.COMPRESS_STATE,  # Final state compression
        },
        forbidden={
            ActionCategory.EXECUTE_TOOL,  # NO more tools in DELIVERING!
            ActionCategory.SPAWN_AGENT,  # NO more agents!
            ActionCategory.ASK_QUESTION,  # NO questions!
            ActionCategory.REPLAN,  # NO replanning!
            ActionCategory.UPDATE_PLAN,  # Plan already updated in EXECUTING
        },
    ),
}


class FSMConstraintEnforcer:
    """
    Enforces FSM state constraints.

    This is the GOVERNOR - it prevents forbidden actions.
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize enforcer.

        Args:
            strict_mode: If True, raise exceptions on violations.
                        If False, log warnings and continue.
        """
        self.strict_mode = strict_mode
        self._violations: List[tuple[ConciergeState, ActionCategory, str]] = []

    def check_action(
        self,
        state: ConciergeState,
        action: ActionCategory,
        context: str = "",
    ) -> bool:
        """
        Check if an action is allowed in the current state.

        Args:
            state: Current FSM state
            action: Action being attempted
            context: Optional context for logging

        Returns:
            True if allowed, False if forbidden

        Raises:
            FSMConstraintViolation: If strict_mode and action forbidden
        """
        constraints = STATE_CONSTRAINTS.get(state)
        if not constraints:
            logger.warning(f"No constraints defined for state {state.name}")
            return True

        allowed, reason = constraints.validate_action(action)

        if not allowed:
            violation = (state, action, f"{reason} - {context}")
            self._violations.append(violation)

            if self.strict_mode:
                raise FSMConstraintViolation(reason)
            else:
                logger.warning(f"FSM CONSTRAINT VIOLATION: {reason}")
                if context:
                    logger.warning(f"  Context: {context}")

        return allowed

    def get_violations(self) -> List[tuple[ConciergeState, ActionCategory, str]]:
        """Get list of constraint violations."""
        return self._violations.copy()

    def clear_violations(self) -> None:
        """Clear violation history."""
        self._violations.clear()

    def get_allowed_actions(self, state: ConciergeState) -> Set[ActionCategory]:
        """Get actions explicitly allowed in a state."""
        constraints = STATE_CONSTRAINTS.get(state)
        return constraints.allowed if constraints else set()

    def get_forbidden_actions(self, state: ConciergeState) -> Set[ActionCategory]:
        """Get actions explicitly forbidden in a state."""
        constraints = STATE_CONSTRAINTS.get(state)
        return constraints.forbidden if constraints else set()


class FSMConstraintViolation(Exception):
    """Raised when an FSM constraint is violated in strict mode."""

    pass


# Singleton enforcer for global use
_enforcer: FSMConstraintEnforcer | None = None


def get_enforcer(strict_mode: bool = False) -> FSMConstraintEnforcer:
    """Get or create the global FSM constraint enforcer."""
    global _enforcer
    if _enforcer is None:
        _enforcer = FSMConstraintEnforcer(strict_mode=strict_mode)
    return _enforcer


def check_action(
    state: ConciergeState,
    action: ActionCategory,
    context: str = "",
) -> bool:
    """Convenience function to check an action against constraints."""
    return get_enforcer().check_action(state, action, context)


def reset_enforcer() -> None:
    """Reset the global enforcer (for testing)."""
    global _enforcer
    _enforcer = None
