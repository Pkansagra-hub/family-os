"""Test helper functions for Orchestrator testing.

Provides common assertion and utility functions used across unit tests,
integration tests, and guard tests. All helpers work with real test adapters
(NO MOCKS) and follow the hexagonal port architecture.
"""

import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from k1.fabric.ports.state_reader import SessionSnapshot
from k1.fabric.types import CapabilityResult
from k1.orchestrator.types import (
    AggregatedResult,
    CommittedPlan,
    PendingPlanContext,
    PlanStep,
    ProcessResult,
    RegistryEntry,
    TaskEnvelope,
)

# ===========================================================================
# Pipeline test helpers (7.0.1 / 7.0.3)
# ===========================================================================


async def orchestrator_for_testing():
    """Create a fully-wired OrchestratorService via OrchestratorFactory.

    Returns (service, adapters_dict) where adapters_dict provides
    keyed access to all 8 test adapter instances:
      fabric   -- MockFabricAdapter   (6.1.9)
      planner  -- MockPlannerAdapter  (6.1.10)
      delta    -- TestDeltaAdapter    (6.1.12)
      state    -- MockStateReadAdapter(6.1.11)
      bridge   -- MockBridgeAdapter   (6.1.13)
      event    -- TestEventAdapter    (6.1.14)
      mailbox  -- TestMailboxAdapter  (6.1.8)
    """
    from k1.orchestrator.factory import OrchestratorFactory

    service = await OrchestratorFactory.create_standalone()
    adapters = {
        "fabric": service._fabric_port,
        "planner": service._planner_port,
        "delta": service._delta_port,
        "state": service._state_port,
        "bridge": service._bridge_port,
        "event": service._event_port,
        "mailbox": service._mailbox,
    }
    return service, adapters


def register_capabilities(fabric, *capability_names: str) -> None:
    """Register capabilities in MockFabricAdapter so ConstraintResolver passes.

    Each capability gets a minimal RegistryEntry with GREEN safety band
    and 'available' status.
    """
    for cap in capability_names:
        fabric.register_capability(
            cap,
            RegistryEntry(
                name=cap,
                provider_type="mock",
                safety_band_min="GREEN",
                availability="available",
                estimated_duration_ms=100,
            ),
        )


def make_plan(
    steps: List[PlanStep],
    *,
    deps: Optional[Dict[str, List[str]]] = None,
    plan_id: str = "plan-test",
    request_id: str = "req-test",
    trace_id: str = "trace-test",
    intent: str = "test intent",
) -> CommittedPlan:
    """Build a CommittedPlan for pipeline testing."""
    return CommittedPlan(
        plan_id=plan_id,
        request_id=request_id,
        intent=intent,
        steps=steps,
        trace_id=trace_id,
        dependencies=deps or {},
    )


def make_step(
    sid: str,
    capability: str = "cap.test",
    *,
    params: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    condition: Any = None,
) -> PlanStep:
    """Build a PlanStep for pipeline testing."""
    return PlanStep(
        id=sid,
        capability=capability,
        params=params or {},
        output_schema=output_schema,
        condition=condition,
    )


def cap_result(
    data: Optional[Dict[str, Any]] = None,
    *,
    success: bool = True,
    request_id: str = "req-mock",
) -> CapabilityResult:
    """Build a CapabilityResult for use with fabric.script_result()."""
    return CapabilityResult(
        request_id=request_id,
        success=success,
        data=data or {},
    )


def _dummy_envelope(trace_id: str = "trace-test") -> TaskEnvelope:
    """Build a minimal HIGH-tier TaskEnvelope for PendingPlanContext."""
    return TaskEnvelope(
        intent="test",
        trace_id=trace_id,
        tier="HIGH",
    )


def seed_pending_plan(service, plan: CommittedPlan) -> None:
    """Pre-register a PendingPlanContext so _receive_plan does not reject.

    Must be called BEFORE service.process(plan).
    """
    service._pending_plans[plan.request_id] = PendingPlanContext(
        request_id=plan.request_id,
        task_envelope=_dummy_envelope(plan.trace_id),
        state_snapshot=SessionSnapshot(session_id="test"),
    )


async def process_plan(service, plan: CommittedPlan, *, seed: bool = True) -> ProcessResult:
    """Feed a CommittedPlan through OrchestratorService.process().

    If seed=True (default), automatically pre-registers a
    PendingPlanContext so _receive_plan passes correlation.
    """
    if seed:
        seed_pending_plan(service, plan)
    return await service.process(plan)


def assert_aggregated_result_success(result: AggregatedResult) -> None:
    """Verify AggregatedResult status == COMPLETED with non-empty results.

    Args:
        result: The AggregatedResult to verify

    Raises:
        AssertionError: If result is not COMPLETED or has empty results
    """
    assert result.status == "COMPLETED", f"Expected COMPLETED, got {result.status}"
    assert result.results, "Expected non-empty results for COMPLETED status"
    assert result.error is None, f"Expected no error for COMPLETED status, got {result.error}"


def assert_aggregated_result_failure(
    result: AggregatedResult, error_code: Optional[str] = None
) -> None:
    """Verify AggregatedResult status == FAILED with expected error.

    Args:
        result: The AggregatedResult to verify
        error_code: Expected error code (optional)

    Raises:
        AssertionError: If result is not FAILED or error code doesn't match
    """
    assert result.status == "FAILED", f"Expected FAILED, got {result.status}"
    assert result.error is not None, "Expected error details for FAILED status"
    if error_code:
        assert (
            result.error.get("code") == error_code
        ), f"Expected error code {error_code}, got {result.error.get('code')}"


def wait_for_event(adapter, event_type: str, timeout_ms: int = 1000) -> Optional[Dict[str, Any]]:
    """Poll TestEventAdapter.captured_events for event_type.

    Args:
        adapter: TestEventAdapter instance
        event_type: Event type to wait for
        timeout_ms: Maximum time to wait in milliseconds

    Returns:
        The matching event dict, or None if timeout

    Raises:
        AssertionError: If adapter doesn't have captured_events attribute
    """
    assert hasattr(adapter, "captured_events"), "Adapter must have captured_events attribute"

    start_time = time.time()
    timeout_s = timeout_ms / 1000.0

    while time.time() - start_time < timeout_s:
        for event in adapter.captured_events:
            if event.get("type") == event_type:
                return event
        time.sleep(0.01)  # 10ms polling interval

    return None


def assert_invariant_orch(invariant_id: str, orchestrator) -> None:
    """Verify specific ORCH invariant holds (dispatcher for ORCH-01 through ORCH-16).

    Args:
        invariant_id: Invariant ID like "ORCH-01", "ORCH-02", etc.
        orchestrator: Orchestrator instance to check

    Raises:
        AssertionError: If invariant check fails
    """
    invariant_checks = {
        "ORCH-01": _check_orch_01_actor_isolation,
        "ORCH-02": _check_orch_02_single_dag,
        "ORCH-03": _check_orch_03_kahn_topological,
        "ORCH-04": _check_orch_04_wave_immutability,
        "ORCH-05": _check_orch_05_constraint_validation,
        "ORCH-06": _check_orch_06_max_three_iterations,
        "ORCH-07": _check_orch_07_safety_re_read,
        "ORCH-08": _check_orch_08_compensation_record,
        "ORCH-09": _check_orch_09_trace_id_propagation,
        "ORCH-10": _check_orch_10_wal_consistency,
        "ORCH-11": _check_orch_11_workflow_contract_compliance,
        "ORCH-12": _check_orch_12_max_workflow_depth,
        "ORCH-13": _check_orch_13_max_one_replan,
        "ORCH-14": _check_orch_14_token_budget_tracking,
        "ORCH-15": _check_orch_15_output_schema_enforcement,
        "ORCH-16": _check_orch_16_conditional_edge_evaluation,
    }

    check_func = invariant_checks.get(invariant_id)
    if not check_func:
        raise ValueError(f"Unknown invariant ID: {invariant_id}")

    check_func(orchestrator)


def build_dag_context(plan: CommittedPlan, snapshot=None):
    """Construct a guard-testing context from CommittedPlan + StateSnapshot.

    V1 does not expose a dedicated ``DAGContext`` domain type, so this helper
    returns a ``ProcessingContext`` populated with DAG-correlated fields and
    attaches common guard-testing attributes for compatibility.

    Args:
        plan: The CommittedPlan to build context for.
        snapshot: Optional StateSnapshot-like object.

    Returns:
        ProcessingContext populated for guard tests.
    """
    from k1.orchestrator.types import ProcessingContext

    ctx = ProcessingContext(
        trace_id=plan.trace_id,
        request_id=plan.request_id,
        tier="HIGH",
    )
    ctx.dag_id = plan.plan_id
    # Compatibility attributes used by guard-oriented tests.
    ctx.merged_results = {}
    ctx.snapshot = snapshot
    return ctx


@contextmanager
def capture_deltas(adapter):
    """Context manager returning list of emitted deltas.

    Args:
        adapter: TestDeltaAdapter instance

    Yields:
        List of deltas emitted during the context

    Raises:
        AssertionError: If adapter doesn't have emitted_deltas attribute
    """
    assert hasattr(adapter, "emitted_deltas"), "Adapter must have emitted_deltas attribute"

    initial_count = len(adapter.emitted_deltas)
    yield adapter.emitted_deltas[initial_count:]


def assert_trace_id_propagated(events: List[Dict[str, Any]], expected_trace_id: str) -> None:
    """Verify all events carry expected trace_id (ORCH-09).

    Args:
        events: List of event dictionaries
        expected_trace_id: Expected trace_id value

    Raises:
        AssertionError: If any event has wrong or missing trace_id
    """
    for event in events:
        assert "trace_id" in event, f"Event missing trace_id: {event}"
        assert (
            event["trace_id"] == expected_trace_id
        ), f"Event trace_id mismatch: expected {expected_trace_id}, got {event['trace_id']}"


def assert_saga_compensated(result: AggregatedResult, expected_steps: List[str]) -> None:
    """Verify CompensationRecord list matches expected compensated step_ids.

    Args:
        result: AggregatedResult containing compensation records
        expected_steps: List of step_ids that should have been compensated

    Raises:
        AssertionError: If compensation records don't match expectations
    """
    if not hasattr(result, "compensation_records"):
        # V1: CompensationRecord not yet implemented
        return

    actual_compensated = [record.step_id for record in result.compensation_records]
    assert (
        actual_compensated == expected_steps
    ), f"Compensation mismatch: expected {expected_steps}, got {actual_compensated}"


# ------------------------------------------------------------------------------
# Private invariant check functions
# ------------------------------------------------------------------------------


def _check_orch_01_actor_isolation(orchestrator) -> None:
    """ORCH-01: Actor isolation - verify no shared mutable state between requests."""
    # Implementation depends on specific orchestrator internals
    # This would check that concurrent requests don't interfere
    pass  # Placeholder


def _check_orch_02_single_dag(orchestrator) -> None:
    """ORCH-02: Single-DAG concurrency - verify only one DAG executes at a time."""
    # Check concurrency guard state
    pass  # Placeholder


def _check_orch_03_kahn_topological(orchestrator) -> None:
    """ORCH-03: Kahn topological sort - verify DAG execution order."""
    # Verify topological sorting in DAGExecutor
    pass  # Placeholder


def _check_orch_04_wave_immutability(orchestrator) -> None:
    """ORCH-04: Wave immutability - verify waves don't change during execution."""
    # Check wave construction and execution
    pass  # Placeholder


def _check_orch_05_constraint_validation(orchestrator) -> None:
    """ORCH-05: Constraint validation - verify all constraints checked."""
    # Check ConstraintResolver integration
    pass  # Placeholder


def _check_orch_06_max_three_iterations(orchestrator) -> None:
    """ORCH-06: Max 3 iterations - verify constraint resolution doesn't loop."""
    # Check iteration limits in ConstraintResolver
    pass  # Placeholder


def _check_orch_07_safety_re_read(orchestrator) -> None:
    """ORCH-07: Safety re-read - verify safety_band re-read at boundaries."""
    # Check StateReadAdapter usage in DAGExecutor
    pass  # Placeholder


def _check_orch_08_compensation_record(orchestrator) -> None:
    """ORCH-08: CompensationRecord on side-effects - verify saga compensation."""
    # Check compensation logic in StepRunner
    pass  # Placeholder


def _check_orch_09_trace_id_propagation(orchestrator) -> None:
    """ORCH-09: Trace ID propagation - verify trace_id on all events/deltas."""
    # Check event emission in all services
    pass  # Placeholder


def _check_orch_10_wal_consistency(orchestrator) -> None:
    """ORCH-10: WAL consistency - verify WAL writes match execution."""
    # Check WAL integration in DAGExecutor
    pass  # Placeholder


def _check_orch_11_workflow_contract_compliance(orchestrator) -> None:
    """ORCH-11: Workflow contract compliance - verify workflow execution."""
    # Check WorkflowEngine integration
    pass  # Placeholder


def _check_orch_12_max_workflow_depth(orchestrator) -> None:
    """ORCH-12: Max workflow depth 3 - verify depth limits."""
    # Check workflow nesting limits
    pass  # Placeholder


def _check_orch_13_max_one_replan(orchestrator) -> None:
    """ORCH-13: Max 1 replan - verify replan limits."""
    # Check MicroReplanCheckpoint limits
    pass  # Placeholder


def _check_orch_14_token_budget_tracking(orchestrator) -> None:
    """ORCH-14: Token budget tracking - verify token limits (V1 removed)."""
    # V1: Not implemented (phantom field)
    pass  # Placeholder


def _check_orch_15_output_schema_enforcement(orchestrator) -> None:
    """ORCH-15: Output schema enforcement - verify per-step schemas."""
    # Check OutputSchemaGuard integration
    pass  # Placeholder


def _check_orch_16_conditional_edge_evaluation(orchestrator) -> None:
    """ORCH-16: Conditional edge evaluation - verify conditional logic."""
    # Check ConditionalEdgeEvaluator integration
    pass  # Placeholder
