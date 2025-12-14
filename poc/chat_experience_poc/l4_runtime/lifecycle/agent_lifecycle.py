"""
Agent Lifecycle States and Transitions

Defines the 6-state FSM for agent lifecycle management.
Based on Actor Model (Hewitt 1973) and ADR-0005 + ADR-0073.

States:
- PENDING: Agent created, not yet ready
- WARMING: Resource validation and model loading (<35s P95)
- ACTIVE: Processing tasks, accepting bids
- IDLE: No tasks, waiting (pooled for reuse, TTL 10min)
- DRAINING: Finishing tasks, no new work (max 30s timeout)
- TERMINATED: Agent shut down, resources freed (final state)

Transitions:
- PENDING → WARMING → ACTIVE
- ACTIVE ↔ IDLE (bidirectional)
- ACTIVE/IDLE → DRAINING → TERMINATED

Performance Targets:
- WARMING: <35s P95
- Pool reactivation: <1ms
- State transition: <10ms

Related ADRs:
- ADR-0005: Agent Architecture and Lifecycle FSM
- ADR-0073: WARMING/IDLE/DRAINING enhancements with TTL and pooling
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    """
    Agent lifecycle states.

    Each state has specific entry/exit behaviors and allowed transitions.
    """

    PENDING = "PENDING"  # Agent created, not yet ready
    WARMING = "WARMING"  # Resource validation and model loading
    ACTIVE = "ACTIVE"  # Processing tasks, accepting bids
    IDLE = "IDLE"  # No tasks, waiting (pooled for reuse)
    DRAINING = "DRAINING"  # Finishing tasks, no new work
    TERMINATED = "TERMINATED"  # Agent shut down, resources freed (final)


@dataclass
class StateTransition:
    """
    Represents a state transition with metadata.

    Used for state history tracking and debugging.
    """

    from_state: AgentState
    to_state: AgentState
    timestamp: datetime
    reason: Optional[str] = None
    triggered_by: Optional[str] = None  # "timeout", "manual", "health_check", etc.


# ============================================================================
# State Transition Rules
# ============================================================================

# Allowed state transitions (directed graph)
ALLOWED_TRANSITIONS: Dict[AgentState, Set[AgentState]] = {
    AgentState.PENDING: {AgentState.WARMING},
    AgentState.WARMING: {AgentState.ACTIVE, AgentState.TERMINATED},  # Can fail during warming
    AgentState.ACTIVE: {AgentState.IDLE, AgentState.DRAINING},
    AgentState.IDLE: {AgentState.ACTIVE, AgentState.DRAINING},  # Bidirectional with ACTIVE
    AgentState.DRAINING: {AgentState.TERMINATED},
    AgentState.TERMINATED: set(),  # Final state, no outgoing transitions
}


def is_valid_transition(from_state: AgentState, to_state: AgentState) -> bool:
    """
    Check if a state transition is allowed.

    Args:
        from_state: Current state
        to_state: Target state

    Returns:
        True if transition is allowed, False otherwise
    """
    return to_state in ALLOWED_TRANSITIONS.get(from_state, set())


def get_allowed_transitions(state: AgentState) -> Set[AgentState]:
    """
    Get all allowed transitions from a given state.

    Args:
        state: Current state

    Returns:
        Set of allowed target states
    """
    return ALLOWED_TRANSITIONS.get(state, set())


# ============================================================================
# State Behaviors
# ============================================================================


@dataclass
class StateBehaviors:
    """
    Entry and exit behaviors for each state.

    These are templates - actual implementations override these in agents.
    """

    # Entry behaviors (called when entering state)
    on_enter_pending: List[str] = field(
        default_factory=lambda: [
            "Initialize mailbox",
            "Register with MailboxManager",
            "Set initial metrics",
        ]
    )

    on_enter_warming: List[str] = field(
        default_factory=lambda: [
            "Check resources (memory, CPU)",
            "Load model (if applicable)",
            "Bind capabilities",
            "Verify configuration",
            "Start timeout timer (35s)",
        ]
    )

    on_enter_active: List[str] = field(
        default_factory=lambda: [
            "Add to agent roster (SessionState)",
            "Mark as ready for bids",
            "Start processing mailbox",
            "Reset idle timer",
        ]
    )

    on_enter_idle: List[str] = field(
        default_factory=lambda: [
            "Start TTL timer (10 minutes default)",
            "Add to agent pool (if eligible)",
            "Schedule health check (every 30s)",
            "Pause mailbox processing",
        ]
    )

    on_enter_draining: List[str] = field(
        default_factory=lambda: [
            "Stop accepting new bids",
            "Track in-flight tasks",
            "Start drain timeout (30s max)",
            "Remove from agent roster",
        ]
    )

    on_enter_terminated: List[str] = field(
        default_factory=lambda: [
            "Unload model (if applicable)",
            "Revoke capabilities",
            "Delete mailbox",
            "Remove from pool (if pooled)",
            "Final cleanup",
        ]
    )

    # Exit behaviors (called when leaving state)
    on_exit_pending: List[str] = field(default_factory=list)  # No exit behaviors

    on_exit_warming: List[str] = field(
        default_factory=lambda: [
            "Stop timeout timer",
            "Log warming duration",
        ]
    )

    on_exit_active: List[str] = field(
        default_factory=lambda: [
            "Pause mailbox processing",
            "Log active duration",
        ]
    )

    on_exit_idle: List[str] = field(
        default_factory=lambda: [
            "Stop TTL timer",
            "Cancel health checks",
            "Remove from pool (if reactivating)",
        ]
    )

    on_exit_draining: List[str] = field(
        default_factory=lambda: [
            "Stop drain timeout",
            "Log drain duration",
            "Log tasks completed vs dropped",
        ]
    )

    on_exit_terminated: List[str] = field(default_factory=list)  # Final state, no exit


# Default behavior instance
DEFAULT_BEHAVIORS = StateBehaviors()


# ============================================================================
# State Timeout Configuration
# ============================================================================


@dataclass
class StateTimeouts:
    """
    Timeout configuration for each state.

    States with timeouts auto-transition when exceeded.
    """

    warming_timeout_seconds: int = 35  # ADR-0073: <35s P95
    idle_ttl_seconds: int = 600  # ADR-0073: 10 minutes
    draining_timeout_seconds: int = 30  # ADR-0073: max 30s
    health_check_interval_seconds: int = 30  # ADR-0073: every 30s for IDLE


# Default timeout instance
DEFAULT_TIMEOUTS = StateTimeouts()


# ============================================================================
# State Metadata
# ============================================================================


@dataclass
class StateMetadata:
    """
    Metadata for each state (documentation, constraints, etc.).
    """

    name: str
    description: str
    entry_actions: List[str]
    exit_actions: List[str]
    timeout_seconds: Optional[int] = None
    is_final: bool = False
    allows_pooling: bool = False


# State metadata registry
STATE_METADATA: Dict[AgentState, StateMetadata] = {
    AgentState.PENDING: StateMetadata(
        name="PENDING",
        description="Agent created, not yet ready",
        entry_actions=DEFAULT_BEHAVIORS.on_enter_pending,
        exit_actions=DEFAULT_BEHAVIORS.on_exit_pending,
        timeout_seconds=None,
        is_final=False,
        allows_pooling=False,
    ),
    AgentState.WARMING: StateMetadata(
        name="WARMING",
        description="Resource validation and model loading",
        entry_actions=DEFAULT_BEHAVIORS.on_enter_warming,
        exit_actions=DEFAULT_BEHAVIORS.on_exit_warming,
        timeout_seconds=DEFAULT_TIMEOUTS.warming_timeout_seconds,
        is_final=False,
        allows_pooling=False,
    ),
    AgentState.ACTIVE: StateMetadata(
        name="ACTIVE",
        description="Processing tasks, accepting bids",
        entry_actions=DEFAULT_BEHAVIORS.on_enter_active,
        exit_actions=DEFAULT_BEHAVIORS.on_exit_active,
        timeout_seconds=None,
        is_final=False,
        allows_pooling=False,
    ),
    AgentState.IDLE: StateMetadata(
        name="IDLE",
        description="No tasks, waiting (pooled for reuse)",
        entry_actions=DEFAULT_BEHAVIORS.on_enter_idle,
        exit_actions=DEFAULT_BEHAVIORS.on_exit_idle,
        timeout_seconds=DEFAULT_TIMEOUTS.idle_ttl_seconds,
        is_final=False,
        allows_pooling=True,  # IDLE agents can be pooled
    ),
    AgentState.DRAINING: StateMetadata(
        name="DRAINING",
        description="Finishing tasks, no new work",
        entry_actions=DEFAULT_BEHAVIORS.on_enter_draining,
        exit_actions=DEFAULT_BEHAVIORS.on_exit_draining,
        timeout_seconds=DEFAULT_TIMEOUTS.draining_timeout_seconds,
        is_final=False,
        allows_pooling=False,
    ),
    AgentState.TERMINATED: StateMetadata(
        name="TERMINATED",
        description="Agent shut down, resources freed (final state)",
        entry_actions=DEFAULT_BEHAVIORS.on_enter_terminated,
        exit_actions=DEFAULT_BEHAVIORS.on_exit_terminated,
        timeout_seconds=None,
        is_final=True,
        allows_pooling=False,
    ),
}


def get_state_metadata(state: AgentState) -> StateMetadata:
    """
    Get metadata for a given state.

    Args:
        state: Agent state

    Returns:
        StateMetadata instance
    """
    return STATE_METADATA[state]


# ============================================================================
# Validation Helpers
# ============================================================================


def validate_state_transition(
    from_state: AgentState, to_state: AgentState, reason: Optional[str] = None
) -> tuple[bool, Optional[str]]:
    """
    Validate a state transition and return error message if invalid.

    Args:
        from_state: Current state
        to_state: Target state
        reason: Optional reason for transition

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check if transition is allowed
    if not is_valid_transition(from_state, to_state):
        allowed = get_allowed_transitions(from_state)
        allowed_str = ", ".join([s.value for s in allowed]) if allowed else "none"
        error_msg = (
            f"Invalid transition: {from_state.value} → {to_state.value}. "
            f"Allowed transitions from {from_state.value}: {allowed_str}"
        )
        return False, error_msg

    # Cannot transition from final state
    if STATE_METADATA[from_state].is_final:
        return False, f"Cannot transition from final state {from_state.value}"

    return True, None


# ============================================================================
# Logging Helpers
# ============================================================================


def log_state_transition(
    agent_id: str,
    from_state: AgentState,
    to_state: AgentState,
    reason: Optional[str] = None,
    duration_ms: Optional[float] = None,
) -> None:
    """
    Log a state transition with metadata.

    Args:
        agent_id: Agent ID
        from_state: Previous state
        to_state: New state
        reason: Optional reason for transition
        duration_ms: Optional duration in previous state (milliseconds)
    """
    msg_parts = [
        f"[AgentLifecycle] {agent_id}:",
        f"{from_state.value} → {to_state.value}",
    ]

    if reason:
        msg_parts.append(f"(reason: {reason})")

    if duration_ms is not None:
        msg_parts.append(f"[duration: {duration_ms:.2f}ms]")

    logger.info(" ".join(msg_parts))
