"""
Agent Lifecycle Management

6-state FSM for agent lifecycle management with pooling and health checks.

States: PENDING → WARMING → ACTIVE ↔ IDLE → DRAINING → TERMINATED

Related ADRs:
- ADR-0005: Agent Lifecycle FSM
- ADR-0073: WARMING/IDLE/DRAINING enhancements
"""

from .agent_lifecycle import AgentState, StateTransition
from .agent_pool import AgentPool, PooledAgent, PoolMetrics
from .lifecycle_fsm import LifecycleFSM, StateCallbacks

__all__ = [
    "AgentState",
    "StateTransition",
    "LifecycleFSM",
    "StateCallbacks",
    "AgentPool",
    "PooledAgent",
    "PoolMetrics",
]
