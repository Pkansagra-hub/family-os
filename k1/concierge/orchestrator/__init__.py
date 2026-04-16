"""
k1.concierge.orchestrator -- Orchestrator package for tier routing and execution.

V2 Design Ref: Section 11

Exports all types, ports, the OrchestratorStub, routing functions,
degradation cascade, and HIGH tier interfaces.

Module inventory:
  - types.py        -> TaskEnvelope, Budget, AggregatedResult, CapabilityRequest,
                       CapabilityResult, StepResult, CannedResponse,
                       PlanRequest, CommittedPlan, PlanStep
  - ports.py        -> IFabricGatewayPort, IStateReadPort, IDeltaEmitPort,
                       IDispatchPort, IPlannerPort, IWorkflowPort,
                       IConnectorPort, IConstraintPort, ISagaPort
  - stub.py         -> OrchestratorStub, BudgetExceededError
  - routing.py      -> route_task, DispatchRecord
  - degradation.py  -> route_task_with_degradation, CircuitBreaker,
                       cb_planner, cb_orchestrator, cb_fabric, get_effective_tier
  - interfaces.py   -> IDAGExecutor, IPlannerService, IWorkflowEngine,
                       IConnectorManager, IConstraintResolver, ISagaRecovery,
                       HIGH_TIER_EVENTS
"""

# Degradation
from k1.concierge.orchestrator.degradation import (
    CircuitBreaker,
    cb_fabric,
    cb_orchestrator,
    cb_planner,
    get_effective_tier,
    route_task_with_degradation,
)

# HIGH tier interfaces
from k1.concierge.orchestrator.interfaces import (
    HIGH_TIER_EVENTS,
    IConnectorManager,
    IConstraintResolver,
    IDAGExecutor,
    IPlannerService,
    ISagaRecovery,
    IWorkflowEngine,
)

# Ports
from k1.concierge.orchestrator.ports import (
    IConnectorPort,
    IConstraintPort,
    IDeltaEmitPort,
    IDispatchPort,
    IFabricGatewayPort,
    IPlannerPort,
    ISagaPort,
    IStateReadPort,
    IWorkflowPort,
)

# Routing
from k1.concierge.orchestrator.routing import DispatchRecord, route_task

# OrchestratorStub
from k1.concierge.orchestrator.stub import BudgetExceededError, OrchestratorStub

# Types
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
from k1.fabric.circuit_breaker import CircuitBreakerState

__all__ = [
    # Types
    "AggregatedResult",
    "Budget",
    "BudgetExceededError",
    "CannedResponse",
    "CapabilityRequest",
    "CapabilityResult",
    "CommittedPlan",
    "PlanRequest",
    "PlanStep",
    "StepResult",
    "TaskEnvelope",
    # Ports
    "IConnectorPort",
    "IConstraintPort",
    "IDeltaEmitPort",
    "IDispatchPort",
    "IFabricGatewayPort",
    "IPlannerPort",
    "ISagaPort",
    "IStateReadPort",
    "IWorkflowPort",
    # Stub
    "OrchestratorStub",
    # Routing
    "DispatchRecord",
    "route_task",
    # Degradation
    "CircuitBreaker",
    "CircuitBreakerState",
    "cb_fabric",
    "cb_orchestrator",
    "cb_planner",
    "get_effective_tier",
    "route_task_with_degradation",
    # HIGH tier interfaces
    "HIGH_TIER_EVENTS",
    "IConnectorManager",
    "IConstraintResolver",
    "IDAGExecutor",
    "IPlannerService",
    "ISagaRecovery",
    "IWorkflowEngine",
]
