"""
k1.concierge.orchestrator.interfaces -- HIGH tier deferred interface contracts.

V2 Design Ref: Section 11.4 (HIGH tier deferred interfaces)
V2 Design Ref: Section 11.5 (event flow: Planner 4-stage -> DAG execution)

These interfaces are NOT IMPLEMENTED in the POC. They exist so HIGH tier
can plug in without refactoring the Orchestrator. Each interface defines
the contract that the production implementation must fulfill.

Deferred Components:
  - DAGExecutor: Topological execution of plan steps
  - Planner: 4-stage planning pipeline (SKETCH -> EXPAND -> VALIDATE -> COMMIT)
  - WorkflowEngine: Multi-step workflow execution
  - ConnectorManager: MCP server registration
  - ConstraintResolver: Runtime parameter resolution
  - SagaRecovery: Rollback on partial failure

Production Reference: k1/orchestrator/orchestration/ (DAGExecutor, guards)
Production Reference: k1/planner/ (Planner 4-stage pipeline)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List

from k1.concierge.orchestrator.types import AggregatedResult, CommittedPlan, PlanRequest, PlanStep


class IDAGExecutor(ABC):
    """Interface for topological execution of plan steps.

    V2 Design Ref: Section 11.4.1

    The DAGExecutor receives a CommittedPlan with dependency graph,
    organizes steps into waves (topological sort), and executes each
    wave sequentially. Within each wave, steps are executed in parallel
    via Fabric.

    Production reference: k1/orchestrator/orchestration/dag_executor.py

    Event flow:
      CommittedPlan -> waves (topological sort)
      Per wave: CapabilityRequest -> Fabric -> CapabilityResult
      Per wave: k1.orchestration.delta.v1 -> Concierge PROGRESSING
      All waves: AggregatedResult -> k1.orchestration.dag.completed
    """

    @abstractmethod
    async def execute(self, plan: CommittedPlan) -> AggregatedResult:
        """Execute a committed plan via topological wave execution.

        Args:
            plan: CommittedPlan with steps and dependency graph.

        Returns:
            AggregatedResult aggregating all step outcomes.
        """
        ...


class IPlannerService(ABC):
    """Interface for the 4-stage planning pipeline.

    V2 Design Ref: Section 11.4.1, 11.5

    Planner stages:
      1. SKETCH: Rough step decomposition
      2. EXPAND: Full parameter resolution + Fabric contract lookup
      3. VALIDATE: Constraint checking + safety band verification
      4. COMMIT: Freeze plan + build dependency graph

    Event flow:
      PlanRequest -> Planner Mailbox
      Planner: SKETCH -> EXPAND -> VALIDATE -> COMMIT
      Emits: k1.planner.plan.ready.v1 (CommittedPlan)
    """

    @abstractmethod
    async def request_plan(self, request: PlanRequest) -> str:
        """Submit a plan request. Returns request_id.

        Result arrives async via k1.planner.plan.ready.v1 event.
        """
        ...

    @abstractmethod
    async def cancel_plan(self, request_id: str) -> None:
        """Cancel a pending plan request."""
        ...


class IWorkflowEngine(ABC):
    """Interface for multi-step workflow execution.

    V2 Design Ref: Section 11.4.1 (WorkflowEngine)
    """

    @abstractmethod
    async def run(self, request: Any) -> Any:
        """Execute a saved workflow.

        Args:
            request: WorkflowRunRequest with workflow_id and parameters.

        Returns:
            WorkflowResult (success/failure + step results).
        """
        ...


class IConnectorManager(ABC):
    """Interface for MCP server registration.

    V2 Design Ref: Section 11.4.1 (ConnectorManager)
    """

    @abstractmethod
    async def register(self, mcp_server: dict) -> None:
        """Register an MCP server with the connector manager.

        Args:
            mcp_server: Server configuration dict with url, capabilities, etc.
        """
        ...


class IConstraintResolver(ABC):
    """Interface for runtime parameter resolution.

    V2 Design Ref: Section 11.4.1 (ConstraintResolver)
    """

    @abstractmethod
    async def resolve(self, step: PlanStep, context: dict) -> dict:
        """Resolve runtime parameters for a plan step.

        Args:
            step: PlanStep with potentially unresolved $ref params.
            context: Current execution context (prior step results, SS).

        Returns:
            Resolved parameters dict.
        """
        ...


class ISagaRecovery(ABC):
    """Interface for saga compensation on partial failure.

    V2 Design Ref: Section 11.4.1 (Saga Recovery)
    """

    @abstractmethod
    async def compensate(
        self,
        failed_step: PlanStep,
        completed_steps: List[PlanStep],
    ) -> None:
        """Compensate (rollback) after a step failure.

        Executes the compensation capability for each completed step
        that has side effects and a defined compensation action.

        Args:
            failed_step: The step that failed.
            completed_steps: Steps that completed before the failure.
        """
        ...


# =========================================================================
# HIGH tier event topics (documented contract)
# =========================================================================

HIGH_TIER_EVENTS = {
    "plan_request": "k1.planner.plan.request.v1",
    "plan_ready": "k1.planner.plan.ready.v1",
    "dag_started": "k1.orchestration.dag.started",
    "dag_wave_completed": "k1.orchestration.delta.v1",
    "dag_completed": "k1.orchestration.dag.completed",
    "hil_required": "k1.orchestration.hil.required.v1",
    "hil_response": "k1.orchestration.hil.response.v1",
}
"""Event topics for HIGH tier execution flow (Section 11.5).

These topics are documented here for interface completeness.
The POC does not emit or consume these events for HIGH tier
(only MEDIUM tier events are implemented).
"""
