"""
poc.k1_poc.orchestrator.stub -- OrchestratorStub for MEDIUM tier execution.

V2 Design Ref: Section 11.3 (OrchestratorStub: Fabric integration, AggregatedResult)

Production Reference: k1/orchestrator/orchestration/ (full Orchestrator service)

The OrchestratorStub is a minimal Orchestrator for MEDIUM tier tasks.
It receives a TaskEnvelope, makes 1-2 Fabric calls, and returns an
AggregatedResult. It enforces hard invariants:

    ORCH-01: No Session State writes (IStateReadPort only, no write port)
    ORCH-02: No LLM calls (no IConciergeModelPort dependency)
    ORCH-03: No tool execution (no ToolDispatcher dependency)
    ORCH-04: Every step goes through Fabric (IFabricGatewayPort.execute())
    ORCH-10: Max 2 Fabric calls per task (Budget enforcement)

Enforcement is STRUCTURAL -- the OrchestratorStub constructor accepts only
three ports. It is physically impossible to violate these invariants because
the required dependencies are not injected.
"""

from __future__ import annotations

import time

from poc.k1_poc.orchestrator.ports import (
    IDeltaEmitPort,
    IFabricGatewayPort,
    IStateReadPort,
)
from poc.k1_poc.orchestrator.types import (
    AggregatedResult,
    CapabilityRequest,
    CapabilityResult,
    TaskEnvelope,
)


class BudgetExceededError(Exception):
    """Raised when a task exceeds its Fabric call budget (ORCH-10)."""

    def __init__(self, max_calls: int, attempted: int) -> None:
        self.max_calls = max_calls
        self.attempted = attempted
        super().__init__(
            f"ORCH-10 violation: attempted {attempted} Fabric calls, " f"budget allows {max_calls}"
        )


class OrchestratorStub:
    """Minimal Orchestrator for MEDIUM tier.

    V2 Design Ref: Section 11.3

    Receives TaskEnvelope, makes 1-2 Fabric calls, returns AggregatedResult.
    NO LLM. NO tools. NO DAG. NO planning.

    Constructor takes exactly 3 ports -- structural enforcement of ORCH-01
    through ORCH-03:
      - fabric_gateway: IFabricGatewayPort -- Fabric execution (ORCH-04)
      - state_read: IStateReadPort -- read-only SS access (ORCH-01)
      - delta_emit: IDeltaEmitPort -- event emission

    Production reference: k1/orchestrator/orchestration/orchestrator_service.py
    uses the same port injection pattern but with 9+ ports for the full
    Orchestrator. The stub is a simplified version.
    """

    def __init__(
        self,
        fabric_gateway: IFabricGatewayPort,
        state_read: IStateReadPort,
        delta_emit: IDeltaEmitPort,
    ) -> None:
        self.fabric = fabric_gateway
        self.state = state_read
        self.delta = delta_emit
        self._fabric_call_count: int = 0

    async def handle_task(self, envelope: TaskEnvelope) -> AggregatedResult:
        """Handle a MEDIUM tier task.

        V2 Design Ref: Section 11.3 (6-step flow)

        Steps:
          1. Emit acceptance event
          2. Read context snapshot (read-only, ORCH-01)
          3. Resolve capability (known at MEDIUM tier, no discovery)
          4. Execute via Fabric (ORCH-04, ORCH-10)
          5. Aggregate result (AggregatedResult)
          6. Emit completion event (k1.orchestration.dag.completed)

        Returns:
            AggregatedResult with success/failure status.

        Raises:
            BudgetExceededError: If more than max_fabric_calls attempted.
        """
        self._fabric_call_count = 0
        start_ms = _now_ms()

        # 1. Emit acceptance
        await self.delta.emit(
            "k1.orchestration.task.accepted",
            {"task_id": envelope.task_id, "tier": "MEDIUM"},
            trace_id=envelope.trace_id,
        )

        # 2. Read context snapshot (ORCH-01: read-only, no writes)
        context = await self.state.snapshot(["beliefs_active", "task_artifacts"])

        # 3. Resolve capability (known at MEDIUM tier, no discovery needed)
        cap_request = CapabilityRequest(
            name=envelope.intent,
            params=envelope.context.get("params", {}),
            session_id=envelope.session_id,
            trace_id=envelope.trace_id,
        )

        # 4. Execute via Fabric (ORCH-04: only path, ORCH-10: max 2 calls)
        self._check_budget(envelope)
        result = await self.fabric.execute(cap_request)
        self._fabric_call_count += 1

        # 5. Aggregate result
        duration_ms = _now_ms() - start_ms
        aggregated = AggregatedResult.from_medium(
            capability_result=result,
            trace_id=envelope.trace_id,
            duration_ms=duration_ms,
        )

        # 6. Emit completion (same event as HIGH tier -- FSM is tier-agnostic)
        completion_payload = aggregated.to_dict()
        completion_payload["task_id"] = envelope.task_id
        await self.delta.emit(
            "k1.orchestration.dag.completed",
            completion_payload,
            trace_id=envelope.trace_id,
        )

        return aggregated

    async def handle_multi_step(
        self, envelope: TaskEnvelope, capability_names: list[str]
    ) -> AggregatedResult:
        """Handle a MEDIUM tier task with multiple Fabric calls (max 2).

        V2 Design Ref: Section 11.3, ORCH-10

        For tasks that need 2 coordinated Fabric calls. If more than 2 are
        needed, the task should be classified as HIGH tier.

        Args:
            envelope: TaskEnvelope with intent and context
            capability_names: List of capability names to execute (max 2)

        Returns:
            AggregatedResult aggregating all step results.

        Raises:
            BudgetExceededError: If len(capability_names) > max_fabric_calls.
        """
        if len(capability_names) > envelope.budget.max_fabric_calls:
            raise BudgetExceededError(envelope.budget.max_fabric_calls, len(capability_names))

        self._fabric_call_count = 0
        start_ms = _now_ms()

        # 1. Emit acceptance
        await self.delta.emit(
            "k1.orchestration.task.accepted",
            {"task_id": envelope.task_id, "tier": "MEDIUM"},
            trace_id=envelope.trace_id,
        )

        # 2. Read context snapshot
        context = await self.state.snapshot(["beliefs_active", "task_artifacts"])

        # 3-4. Execute each capability via Fabric
        results: list[CapabilityResult] = []
        for cap_name in capability_names:
            self._check_budget(envelope)
            cap_request = CapabilityRequest(
                name=cap_name,
                params=envelope.context.get("params", {}),
                session_id=envelope.session_id,
                trace_id=envelope.trace_id,
            )
            result = await self.fabric.execute(cap_request)
            self._fabric_call_count += 1
            results.append(result)

        # 5. Aggregate results
        duration_ms = _now_ms() - start_ms
        aggregated = AggregatedResult.from_multi_step(
            capability_results=results,
            trace_id=envelope.trace_id,
            duration_ms=duration_ms,
        )

        # 6. Emit completion
        completion_payload = aggregated.to_dict()
        completion_payload["task_id"] = envelope.task_id
        await self.delta.emit(
            "k1.orchestration.dag.completed",
            completion_payload,
            trace_id=envelope.trace_id,
        )

        return aggregated

    def _check_budget(self, envelope: TaskEnvelope) -> None:
        """Enforce ORCH-10: max Fabric calls per budget.

        Raises BudgetExceededError if calling Fabric would exceed budget.
        """
        if self._fabric_call_count >= envelope.budget.max_fabric_calls:
            raise BudgetExceededError(
                envelope.budget.max_fabric_calls,
                self._fabric_call_count + 1,
            )

    @property
    def fabric_call_count(self) -> int:
        """Number of Fabric calls made during current task."""
        return self._fabric_call_count


def _now_ms() -> int:
    """Current time in milliseconds."""
    return int(time.monotonic() * 1000)
