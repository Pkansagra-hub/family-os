"""
k1.concierge.orchestrator -- Concierge-local POC orchestrator types and routing.

P4B.4: OrchestratorStub, HIGH-tier interfaces, port protocols, and the
per-tier CircuitBreaker have been removed. CircuitBreaker now lives in
``k1.orchestrator.degradation``. What remains here is the POC type system
and routing helpers still used by the FSM controller.

Remaining submodules:
  - types.py   -> POC TaskEnvelope, Budget, AggregatedResult, etc.
  - routing.py -> route_task / route_task_sync / DispatchRecord.
"""

from k1.concierge.orchestrator.routing import DispatchRecord, route_task, route_task_sync
from k1.concierge.orchestrator.types import (
    AggregatedResult,
    Budget,
    CannedResponse,
    CapabilityRequest,
    CapabilityResult,
    CommittedPlan,
    PlanRequest,
    PlanStep,
    StepResult,
    TaskEnvelope,
)

__all__ = [
    "AggregatedResult",
    "Budget",
    "CannedResponse",
    "CapabilityRequest",
    "CapabilityResult",
    "CommittedPlan",
    "PlanRequest",
    "PlanStep",
    "StepResult",
    "TaskEnvelope",
    "DispatchRecord",
    "route_task",
    "route_task_sync",
]
