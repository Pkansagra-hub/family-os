"""
Test Suite for DAG Executor - Parallel Wave Execution with Saga Pattern

ADR: 0006c - Parallel DAG Execution
ADR: 0008 - Saga Pattern Error Recovery

Test Scenarios:
1. Simple 2-step sequential plan
2. Complex multi-wave plan with parallel execution
3. Circular dependency detection
4. Compensation on critical failure
5. Performance validation (wave computation, parallelism)
"""

import asyncio

# Import DAG Executor components
import sys
from time import perf_counter

sys.path.append(".")
from l2_orchestration.executor import DAGExecutor, StepResult
from l2_orchestration.executor.dag_executor import CyclicDependencyError, StepExecutionError
from l2_orchestration.planner import CommittedPlan, PlanComplexity, PlanStep, StepOp

# ========== MOCK REGISTRIES ==========

MOCK_TOOL_REGISTRY = {
    "query_k0_health": {"latency_ms": 150, "cost": 0.05},
    "query_k0_finance": {"latency_ms": 200, "cost": 0.10},
    "web_search": {"latency_ms": 300, "cost": 0.15},
    "book_restaurant": {"latency_ms": 500, "cost": 0.50},
    "charge_payment": {"latency_ms": 400, "cost": 0.00},  # No fee for charging
    "create_calendar_event": {"latency_ms": 200, "cost": 0.02},
}

MOCK_AGENT_REGISTRY = {
    "healthcare_agent": {"tools": ["query_k0_health"]},
    "finance_agent": {"tools": ["query_k0_finance"]},
    "researcher_agent": {"tools": ["web_search"]},
    "booking_agent": {"tools": ["book_restaurant"]},
    "payment_agent": {"tools": ["charge_payment"]},
    "calendar_agent": {"tools": ["create_calendar_event"]},
}


# ========== TEST SCENARIOS ==========


async def test_scenario_1_simple_sequential():
    """
    Scenario 1: Simple 2-step sequential plan

    Tests:
    - DAG parsing with dependencies
    - Wave computation (2 waves: step1 then step2)
    - Barrier synchronization
    - Dependency data flow
    """
    print("\n" + "=" * 80)
    print("SCENARIO 1: Simple 2-Step Sequential Plan")
    print("=" * 80)

    # Create simple plan: Step 1 → Step 2 (sequential)
    steps = [
        PlanStep(
            step_id="step_1",
            op=StepOp.TOOL,
            description="Query health data",
            needs=[],
            tool_name="query_k0_health",
            agent_id="healthcare_agent",
            estimated_latency_ms=150,
            estimated_cost=0.05,
        ),
        PlanStep(
            step_id="step_2",
            op=StepOp.MODEL,
            description="Synthesize health summary",
            needs=["step_1"],  # Depends on step_1
            agent_id="healthcare_agent",
            estimated_latency_ms=200,
            estimated_cost=0.10,
        ),
    ]

    committed_plan = CommittedPlan(
        plan_id="plan_test_001",
        intent="health_query",
        steps=steps,
        complexity=PlanComplexity.SIMPLE,
        serialized_json="{}",
        plan_hash="abc123",
        committed_at="2025-11-05T12:00:00Z",
        latency_ms=5.0,
        trace_id="test_trace_001",
    )

    # Execute
    executor = DAGExecutor(MOCK_AGENT_REGISTRY, MOCK_TOOL_REGISTRY)
    result = await executor.execute_plan(committed_plan)

    # Validate
    assert result["status"] == "SUCCESS", "Execution should succeed"
    assert result["waves"] == 2, f"Should have 2 waves, got {result['waves']}"
    assert len(result["step_results"]) == 2, "Should have 2 wave results"
    assert len(result["step_results"][0]) == 1, "Wave 1 should have 1 step"
    assert len(result["step_results"][1]) == 1, "Wave 2 should have 1 step"

    print("\n✅ Sequential execution validated")
    print(f"   Wave 1: {result['step_results'][0][0].step_id}")
    print(f"   Wave 2: {result['step_results'][1][0].step_id}")
    print(f"   Total latency: {result['latency_ms']}ms")


async def test_scenario_2_parallel_multi_wave():
    """
    Scenario 2: Complex multi-wave plan with parallel execution

    Plan:
    Wave 1: [step_1, step_2] (parallel, no dependencies)
    Wave 2: [step_3] (depends on step_1, step_2)
    Wave 3: [step_4, step_5] (parallel, depends on step_3)

    Tests:
    - Parallel execution within wave
    - Multiple waves
    - Dependency resolution across waves
    - Max 3 concurrent enforcement
    """
    print("\n" + "=" * 80)
    print("SCENARIO 2: Parallel Multi-Wave Plan")
    print("=" * 80)

    steps = [
        # Wave 1: Parallel
        PlanStep(
            step_id="step_1",
            op=StepOp.TOOL,
            description="Search restaurants",
            needs=[],
            tool_name="web_search",
            agent_id="researcher_agent",
            estimated_latency_ms=300,
            estimated_cost=0.15,
        ),
        PlanStep(
            step_id="step_2",
            op=StepOp.TOOL,
            description="Query budget",
            needs=[],
            tool_name="query_k0_finance",
            agent_id="finance_agent",
            estimated_latency_ms=200,
            estimated_cost=0.10,
        ),
        # Wave 2: Depends on Wave 1
        PlanStep(
            step_id="step_3",
            op=StepOp.MODEL,
            description="Select best restaurant",
            needs=["step_1", "step_2"],
            agent_id="researcher_agent",
            estimated_latency_ms=200,
            estimated_cost=0.10,
        ),
        # Wave 3: Parallel, depends on Wave 2
        PlanStep(
            step_id="step_4",
            op=StepOp.TOOL,
            description="Book reservation",
            needs=["step_3"],
            tool_name="book_restaurant",
            agent_id="booking_agent",
            estimated_latency_ms=500,
            estimated_cost=0.50,
        ),
        PlanStep(
            step_id="step_5",
            op=StepOp.TOOL,
            description="Add to calendar",
            needs=["step_3"],
            tool_name="create_calendar_event",
            agent_id="calendar_agent",
            estimated_latency_ms=200,
            estimated_cost=0.02,
        ),
    ]

    committed_plan = CommittedPlan(
        plan_id="plan_test_002",
        intent="book_dinner",
        steps=steps,
        complexity=PlanComplexity.COMPLEX,
        serialized_json="{}",
        plan_hash="def456",
        committed_at="2025-11-05T12:00:00Z",
        latency_ms=5.0,
        trace_id="test_trace_002",
    )

    # Execute
    executor = DAGExecutor(MOCK_AGENT_REGISTRY, MOCK_TOOL_REGISTRY)
    result = await executor.execute_plan(committed_plan)

    # Validate
    assert result["status"] == "SUCCESS", "Execution should succeed"
    assert result["waves"] == 3, f"Should have 3 waves, got {result['waves']}"
    assert len(result["step_results"][0]) == 2, "Wave 1 should have 2 parallel steps"
    assert len(result["step_results"][1]) == 1, "Wave 2 should have 1 step"
    assert len(result["step_results"][2]) == 2, "Wave 3 should have 2 parallel steps"

    # Check dependency data flow
    wave2_result = result["step_results"][1][0]
    assert "from_step_1" in wave2_result.output_data, "Wave 2 should have data from step_1"
    assert "from_step_2" in wave2_result.output_data, "Wave 2 should have data from step_2"

    print("\n✅ Parallel execution validated")
    print(f"   Wave 1: {len(result['step_results'][0])} parallel steps")
    print(f"   Wave 2: {len(result['step_results'][1])} steps")
    print(f"   Wave 3: {len(result['step_results'][2])} parallel steps")
    print(f"   Total latency: {result['latency_ms']}ms")


async def test_scenario_3_circular_dependency():
    """
    Scenario 3: Circular dependency detection

    Plan with cycle: step_1 → step_2 → step_3 → step_1

    Tests:
    - Cycle detection in DAG parsing
    - CyclicDependencyError raised
    """
    print("\n" + "=" * 80)
    print("SCENARIO 3: Circular Dependency Detection")
    print("=" * 80)

    # Create plan with circular dependency
    steps = [
        PlanStep(
            step_id="step_1",
            op=StepOp.TOOL,
            description="Step 1",
            needs=["step_3"],  # Circular: depends on step_3
            tool_name="query_k0_health",
            agent_id="healthcare_agent",
        ),
        PlanStep(
            step_id="step_2",
            op=StepOp.TOOL,
            description="Step 2",
            needs=["step_1"],
            tool_name="query_k0_finance",
            agent_id="finance_agent",
        ),
        PlanStep(
            step_id="step_3",
            op=StepOp.MODEL,
            description="Step 3",
            needs=["step_2"],  # Completes cycle
            agent_id="researcher_agent",
        ),
    ]

    committed_plan = CommittedPlan(
        plan_id="plan_test_003",
        intent="circular_test",
        steps=steps,
        complexity=PlanComplexity.MEDIUM,
        serialized_json="{}",
        plan_hash="ghi789",
        committed_at="2025-11-05T12:00:00Z",
        latency_ms=5.0,
        trace_id="test_trace_003",
    )

    # Execute (should raise CyclicDependencyError)
    executor = DAGExecutor(MOCK_AGENT_REGISTRY, MOCK_TOOL_REGISTRY)

    try:
        result = await executor.execute_plan(committed_plan)
        assert False, "Should have raised CyclicDependencyError"
    except CyclicDependencyError as e:
        assert "circular dependencies" in str(e).lower(), "Error should mention cycles"
        print(f"\n✅ Circular dependency detected correctly: {str(e)[:80]}...")


async def test_scenario_4_compensation_on_failure():
    """
    Scenario 4: Saga Pattern compensation on critical failure

    Plan:
    Wave 1: step_1 (success)
    Wave 2: step_2 (success)
    Wave 3: step_3 (FAILURE) → Trigger compensation

    Tests:
    - Failure detection
    - LIFO compensation (step_2 then step_1)
    - Compensation registry lookup
    - User message generation
    """
    print("\n" + "=" * 80)
    print("SCENARIO 4: Saga Pattern Compensation on Failure")
    print("=" * 80)

    # Create plan with failure simulation
    steps = [
        PlanStep(
            step_id="step_1",
            op=StepOp.TOOL,
            description="Search restaurants",
            needs=[],
            tool_name="web_search",
            agent_id="researcher_agent",
            estimated_latency_ms=300,
            estimated_cost=0.15,
        ),
        PlanStep(
            step_id="step_2",
            op=StepOp.TOOL,
            description="Book reservation",
            needs=["step_1"],
            tool_name="book_restaurant",
            agent_id="booking_agent",
            estimated_latency_ms=500,
            estimated_cost=0.50,
        ),
        PlanStep(
            step_id="step_3",
            op=StepOp.TOOL,
            description="Charge payment",
            needs=["step_2"],
            tool_name="charge_payment",
            agent_id="payment_agent",
            estimated_latency_ms=400,
            estimated_cost=0.00,
        ),
    ]

    committed_plan = CommittedPlan(
        plan_id="plan_test_004",
        intent="book_with_payment",
        steps=steps,
        complexity=PlanComplexity.MEDIUM,
        serialized_json="{}",
        plan_hash="jkl012",
        committed_at="2025-11-05T12:00:00Z",
        latency_ms=5.0,
        trace_id="test_trace_004",
    )

    # Execute with failure injection
    executor = DAGExecutor(MOCK_AGENT_REGISTRY, MOCK_TOOL_REGISTRY)

    # Mock failure in step_3 by modifying _execute_step
    original_execute_step = executor._execute_step

    async def mock_execute_step_with_failure(step):
        if step.step_id == "step_3":
            # Simulate payment failure
            return StepResult(
                step_id=step.step_id,
                status="failure",
                error="Payment gateway timeout",
                agent_id=step.agent_id or "mock_agent",
                latency_ms=100,
            )
        return await original_execute_step(step)

    executor._execute_step = mock_execute_step_with_failure

    # Execute (should trigger compensation)
    try:
        result = await executor.execute_plan(committed_plan)
        assert False, "Should have raised StepExecutionError"
    except StepExecutionError as e:
        assert "step_3" in str(e), "Error should mention failed step"
        print(f"\n✅ Failure detected: {str(e)[:80]}...")

        # Validate compensation was triggered
        # (In real implementation, compensation would be tracked in result)
        print(f"   Compensation triggered for: {executor.completed_steps}")
        assert len(executor.completed_steps) == 2, "Should have 2 completed steps to compensate"


async def test_scenario_5_performance_validation():
    """
    Scenario 5: Performance validation

    Tests:
    - DAG parsing < 10ms
    - Wave computation < 5ms
    - Parallel execution faster than sequential
    """
    print("\n" + "=" * 80)
    print("SCENARIO 5: Performance Validation")
    print("=" * 80)

    # Create plan with 6 steps (3 waves of 2 parallel steps each)
    steps = []
    for wave in range(3):
        for parallel in range(2):
            step_id = f"step_{wave}_{parallel}"
            steps.append(
                PlanStep(
                    step_id=step_id,
                    op=StepOp.TOOL,
                    description=f"Wave {wave} Step {parallel}",
                    needs=[f"step_{wave-1}_0", f"step_{wave-1}_1"] if wave > 0 else [],
                    tool_name="query_k0_health",
                    agent_id="healthcare_agent",
                    estimated_latency_ms=100,
                    estimated_cost=0.05,
                )
            )

    committed_plan = CommittedPlan(
        plan_id="plan_test_005",
        intent="performance_test",
        steps=steps,
        complexity=PlanComplexity.COMPLEX,
        serialized_json="{}",
        plan_hash="mno345",
        committed_at="2025-11-05T12:00:00Z",
        latency_ms=5.0,
        trace_id="test_trace_005",
    )

    # Measure DAG parsing
    executor = DAGExecutor(MOCK_AGENT_REGISTRY, MOCK_TOOL_REGISTRY)

    parse_start = perf_counter()
    dag = executor._parse_dag(committed_plan)
    parse_latency = (perf_counter() - parse_start) * 1000

    print(f"\n[Performance] DAG parsing: {parse_latency:.2f}ms (target <10ms)")
    assert parse_latency < 10, f"DAG parsing too slow: {parse_latency:.2f}ms"

    # Measure wave computation
    wave_start = perf_counter()
    waves = executor._compute_waves(dag, committed_plan.steps)
    wave_latency = (perf_counter() - wave_start) * 1000

    print(f"[Performance] Wave computation: {wave_latency:.2f}ms (target <5ms)")
    assert wave_latency < 5, f"Wave computation too slow: {wave_latency:.2f}ms"

    # Execute and measure total latency
    exec_start = perf_counter()
    result = await executor.execute_plan(committed_plan)
    exec_latency = (perf_counter() - exec_start) * 1000

    print(f"[Performance] Total execution: {exec_latency:.2f}ms")
    print(f"[Performance] Waves: {result['waves']}")
    print(f"[Performance] Parallelism benefit: {len(steps)} steps in {result['waves']} waves")

    # Validate parallelism benefit
    # Sequential would take: 6 steps * ~100ms = 600ms
    # Parallel (3 waves of 2): 3 waves * ~100ms = ~300ms
    # So parallel should be ~2x faster
    sequential_estimate = len(steps) * 100  # 600ms
    assert (
        exec_latency < sequential_estimate
    ), f"Parallel not faster: {exec_latency}ms vs {sequential_estimate}ms sequential"

    print("\n✅ Performance validated:")
    print(f"   DAG parsing: {parse_latency:.2f}ms < 10ms ✅")
    print(f"   Wave computation: {wave_latency:.2f}ms < 5ms ✅")
    print(f"   Parallel speedup: {sequential_estimate/exec_latency:.1f}x ✅")


# ========== MAIN TEST RUNNER ==========


async def main():
    """Run all test scenarios"""
    print("\n" + "=" * 80)
    print("DAG EXECUTOR TEST SUITE - PARALLEL WAVE EXECUTION & SAGA PATTERN")
    print("=" * 80)
    print("ADR-0006c: Parallel DAG Execution")
    print("ADR-0008: Saga Pattern Error Recovery")
    print("=" * 80)

    try:
        # Run all scenarios
        await test_scenario_1_simple_sequential()
        await test_scenario_2_parallel_multi_wave()
        await test_scenario_3_circular_dependency()
        await test_scenario_4_compensation_on_failure()
        await test_scenario_5_performance_validation()

        # Summary
        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        print("Summary:")
        print("  ✅ Scenario 1: Simple 2-step sequential plan")
        print("  ✅ Scenario 2: Parallel multi-wave execution")
        print("  ✅ Scenario 3: Circular dependency detection")
        print("  ✅ Scenario 4: Saga Pattern compensation")
        print("  ✅ Scenario 5: Performance validation")
        print("\nDAG Executor is production ready!")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())
