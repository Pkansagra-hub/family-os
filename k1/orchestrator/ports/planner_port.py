"""
k1.orchestrator.ports.planner_port -- IPlannerPort port (1.4.3).

Async interface to the Planner module for plan creation and micro-replan.

Design:
  - SOFT CONSTRAINT: Planner is not yet implemented. These method
    signatures define Orchestrator's requirements that Planner will
    satisfy. Exact API can be adjusted when building Planner.
  - All methods ASYNC.
  - request_plan() is fire-and-forget: CommittedPlan arrives via
    event bus (k1.planner.plan.ready.v1), per ADR-1.1.12.
  - micro_replan() is SYNCHRONOUS with 10s timeout (PROTOCOL-3):
    happens mid-DAG while DAGExecutor is parked.
  - No await_plan() method (event-driven model).

Consumers:
  - OrchestratorService.dispatch_high() (2.1.4) -- request_plan
  - MicroReplanCheckpoint (3.2.5) -- micro_replan
  - OrchestratorService._reap_stale_contexts() -- cancel_plan

Production adapter: PlannerAdapter (6.1.3) in adapters/planner_adapter.py
Test adapter: MockPlannerAdapter (6.1.10) in adapters/mock_planner_adapter.py

References:
  - ADR ORCH-012 (event-driven plan delivery)
  - PROTOCOL-3 (micro-replan synchronous 10s timeout)
  - docs/whiteboard/schema_whiteboard.md (S10.1-10.6)

Exports:
  IPlannerPort
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from k1.orchestrator.types import CommittedPlan, MicroReplanRequest, PlanAck, PlanRequest

# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IPlannerPort(Protocol):
    """
    Async interface to the Planner module.

    Provides plan creation (fire-and-forget), plan cancellation,
    and synchronous micro-replan during DAG execution.

    The request_plan() -> PlanAck flow is phase 1 of the two-phase
    protocol. Phase 2 is the CommittedPlan arriving via event bus
    on topic ``k1.planner.plan.ready.v1``.

    Thread safety:
      Implementations MUST support concurrent calls from multiple
      asyncio tasks. In practice, only one request_plan() is active
      per session at a time, but cancel_plan() may overlap.
    """

    async def request_plan(
        self,
        request: PlanRequest,
    ) -> PlanAck:
        """
        Submit a plan request to the Planner (fire-and-forget).

        The Planner acknowledges receipt immediately with PlanAck.
        The actual CommittedPlan arrives asynchronously via the event
        bus on topic ``k1.planner.plan.ready.v1``.

        Args:
            request: The plan request containing intent, constraints,
                context snapshot, and trace_id.

        Returns:
            PlanAck with status ``ACCEPTED`` or ``REJECTED``.
            ``ACCEPTED`` means the Planner will produce a plan.
            ``REJECTED`` means the Planner cannot handle this request.

        Raises:
            AdapterError: With severity DEGRADED if Planner is
                unreachable.
        """
        ...  # pragma: no cover

    async def cancel_plan(
        self,
        request_id: str,
    ) -> None:
        """
        Cancel an in-progress planning request.

        Best-effort: the Planner may have already committed the plan.
        If the plan was already delivered via event bus, cancel has
        no effect.

        Args:
            request_id: The request_id from the original PlanRequest.

        Raises:
            AdapterError: With severity RECOVERABLE if Planner is
                temporarily unreachable.
        """
        ...  # pragma: no cover

    async def micro_replan(
        self,
        request: MicroReplanRequest,
    ) -> Optional[CommittedPlan]:
        """
        Request a synchronous micro-replan during DAG execution.

        Unlike request_plan(), this call blocks until the Planner
        responds (with a 10s timeout per PROTOCOL-3). Returns the
        new CommittedPlan or None on timeout/failure.

        Rationale: micro-replan happens mid-DAG while DAGExecutor
        is already parked waiting. The 10s blocking wait is acceptable.

        ORCH-13: max 1 micro-replan per DAG execution (enforced by
        MicroReplanCheckpoint, not by this port).

        Args:
            request: MicroReplanRequest with completed results,
                remaining steps, and optional discoveries.

        Returns:
            New CommittedPlan replacing remaining steps, or ``None``
            if the Planner times out or cannot produce a replan.

        Raises:
            AdapterError: With severity DEGRADED if Planner is
                unreachable (distinct from timeout returning None).
        """
        ...  # pragma: no cover
