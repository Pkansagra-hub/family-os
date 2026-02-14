"""Performance benchmarks for Orchestrator critical paths (Epic 7.7.1).

Benchmarks use wall-clock timing via ``time.perf_counter_ns()`` and compute
P50/P95/P99 over exactly 100 iterations, per implementation plan guidance.

Notes:
  - These tests isolate Orchestrator overhead with zero-latency mock adapters.
  - Planner/Fabric external latency is excluded by design of test adapters.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import tracemalloc
from typing import Dict, List, Tuple

import pytest

from k1.fabric.types import CapabilityResult
from k1.orchestrator.orchestration.dag_executor import DAGExecutor
from k1.orchestrator.orchestration.guards.conditional_eval import evaluate_condition
from k1.orchestrator.orchestration.guards.micro_replan import _check_param_overlap
from k1.orchestrator.types import (
    ConditionExpr,
    InterruptRequest,
    ProcessingContext,
    ProcessResult,
    StepResult,
    StepStatus,
    WaveResult,
)
from tests.k1.orchestrator.helpers import (
    make_plan,
    make_step,
    orchestrator_for_testing,
    process_plan,
    register_capabilities,
)

ITERATIONS = 100

# 7.7.1 targets from orchestrator-implementation-plan.md
TOTAL_OVERHEAD_P99_NS = 18_000_000  # 18ms
WAVE_BUILD_P99_NS = 5_000_000  # 5ms
PARAM_RESOLUTION_P99_NS = 1_000_000  # 1ms per step
CONSTRAINT_VALIDATION_P99_NS = 5_000_000  # 5ms
MAILBOX_ROUTING_P99_NS = 1_000_000  # 1ms
CAPREQ_BUILD_P99_NS = 1_000_000  # 1ms per step
SCHEMA_VALIDATION_P99_NS = 1_000_000  # 1ms per step
CONDITIONAL_EVAL_P99_NS = 1_000_000  # 1ms per wave
DISCOVERY_HEURISTIC_P99_NS = 1_000_000  # 1ms per wave
RESULT_AGGREGATION_P99_NS = 2_000_000  # 2ms
PROGRESS_EMIT_P99_NS = 1_000_000  # 1ms

# 7.7.2 targets from orchestrator-implementation-plan.md
ITERATIONS_772 = 50
WAVE_BUILD_P99_BY_SIZE_NS = {
    10: 5_000_000,  # 5ms
    25: 10_000_000,  # 10ms
    50: 20_000_000,  # 20ms
}
WAVE_DISPATCH_OVERHEAD_P99_NS = 1_000_000  # 1ms
MEMORY_50_STEP_MAX_BYTES = 1_000_000  # 1MB

# 7.7.3 default targets (new): end-to-end orchestrator execution scaling
ITERATIONS_773 = 50
E2E_OVERHEAD_P99_BY_SIZE_NS = {
    10: 25_000_000,  # 25ms
    25: 40_000_000,  # 40ms
    50: 70_000_000,  # 70ms
}
E2E_REALWORLD_P99_NS = 50_000_000  # 50ms


def _percentiles_from_100(samples_ns: List[int]) -> Tuple[int, int, int]:
    """Return (p50, p95, p99) for exactly 100 sorted samples."""
    assert len(samples_ns) == ITERATIONS, f"Expected {ITERATIONS} samples, got {len(samples_ns)}"
    ordered = sorted(samples_ns)
    return ordered[49], ordered[94], ordered[98]


def _percentiles(samples_ns: List[int]) -> Tuple[int, int, int]:
    """Return (p50, p95, p99) for variable-length sample sets."""
    assert samples_ns, "samples cannot be empty"
    ordered = sorted(samples_ns)
    n = len(ordered)

    def _idx(p: float) -> int:
        return min(max(int(n * p) - 1, 0), n - 1)

    return ordered[_idx(0.50)], ordered[_idx(0.95)], ordered[_idx(0.99)]


def _make_10_step_plan(*, plan_id: str, request_id: str, trace_id: str):
    """Construct deterministic 10-step, 3-wave plan for benchmark stability."""
    steps = [
        make_step("s1", "cap.perf.1"),
        make_step("s2", "cap.perf.2"),
        make_step("s3", "cap.perf.3"),
        make_step("s4", "cap.perf.4"),
        make_step("s5", "cap.perf.5"),
        make_step("s6", "cap.perf.6"),
        make_step("s7", "cap.perf.7"),
        make_step("s8", "cap.perf.8"),
        make_step("s9", "cap.perf.9"),
        make_step("s10", "cap.perf.10"),
    ]
    deps: Dict[str, List[str]] = {
        "s4": ["s1"],
        "s5": ["s2"],
        "s6": ["s3"],
        "s7": ["s4", "s5"],
        "s8": ["s5", "s6"],
        "s9": ["s4"],
        "s10": ["s6"],
    }
    return make_plan(
        steps,
        deps=deps,
        plan_id=plan_id,
        request_id=request_id,
        trace_id=trace_id,
        intent="performance benchmark",
    )


def _make_random_dag_plan(
    *,
    step_count: int,
    seed: int,
    max_deps: int = 3,
):
    """Create deterministic random DAG plans for size-scaling benchmarks."""
    rng = random.Random(seed)
    steps = [make_step(f"s{i}", f"cap.perf.{i}") for i in range(1, step_count + 1)]
    deps: Dict[str, List[str]] = {}
    for i in range(2, step_count + 1):
        if rng.random() < 0.55:
            prior = [f"s{j}" for j in range(1, i)]
            dep_count = min(max_deps, len(prior))
            k = rng.randint(1, dep_count)
            deps[f"s{i}"] = sorted(rng.sample(prior, k=k))
    return make_plan(
        steps,
        deps=deps,
        plan_id=f"plan-rand-{step_count}-{seed}",
        request_id=f"req-rand-{step_count}-{seed}",
        trace_id=f"trace-rand-{step_count}-{seed}",
        intent="7.7.2 random DAG benchmark",
    )


def _make_realworld_fanout_fanin_plan(
    *,
    plan_id: str = "plan-real-fanout-fanin",
    request_id: str = "req-real-fanout-fanin",
    trace_id: str = "trace-real-fanout-fanin",
) -> object:
    """Create a realistic multi-stage ETL-like fan-out/fan-in DAG (25 steps)."""
    steps = [make_step(f"s{i}", f"cap.real.{i}") for i in range(1, 26)]
    deps: Dict[str, List[str]] = {
        "s2": ["s1"],
        "s3": ["s1"],
        "s4": ["s1"],
        "s5": ["s2"],
        "s6": ["s2"],
        "s7": ["s3"],
        "s8": ["s3"],
        "s9": ["s4"],
        "s10": ["s4"],
        "s11": ["s5", "s7"],
        "s12": ["s6", "s8"],
        "s13": ["s9", "s10"],
        "s14": ["s11"],
        "s15": ["s11"],
        "s16": ["s12"],
        "s17": ["s12"],
        "s18": ["s13"],
        "s19": ["s13"],
        "s20": ["s14", "s16", "s18"],
        "s21": ["s15", "s17", "s19"],
        "s22": ["s20"],
        "s23": ["s20"],
        "s24": ["s21"],
        "s25": ["s22", "s23", "s24"],
    }
    return make_plan(
        steps,
        deps=deps,
        plan_id=plan_id,
        request_id=request_id,
        trace_id=trace_id,
        intent="7.7.2 real-world fanout-fanin",
    )


def _make_layered_execution_plan(
    *,
    step_count: int,
    layer_size: int = 5,
    plan_id: str | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
):
    """Create execution-friendly layered DAG for deterministic end-to-end runs."""
    steps = [make_step(f"e{i}", f"cap.exec.{i}") for i in range(1, step_count + 1)]
    deps: Dict[str, List[str]] = {}

    for start in range(layer_size + 1, step_count + 1, layer_size):
        prev_start = max(1, start - layer_size)
        prev_ids = [
            f"e{j}" for j in range(prev_start, min(prev_start + layer_size, step_count + 1))
        ]
        for j in range(start, min(start + layer_size, step_count + 1)):
            deps[f"e{j}"] = prev_ids

    return make_plan(
        steps,
        deps=deps,
        plan_id=plan_id or f"plan-layered-{step_count}",
        request_id=request_id or f"req-layered-{step_count}",
        trace_id=trace_id or f"trace-layered-{step_count}",
        intent="7.7.3 e2e layered execution benchmark",
    )


# ---------------------------------------------------------------------------
# Epic 7.7.1 - Orchestrator overhead benchmark
# ---------------------------------------------------------------------------


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_771_orchestrator_total_overhead_p99_under_18ms() -> None:
    """Validate total Orchestrator overhead target (<18ms P99, 100 iterations)."""
    service, adapters = await orchestrator_for_testing()
    fabric = adapters["fabric"]

    # Zero-latency mock fabric: no scripted timeout; default execute() is immediate.
    caps = [f"cap.perf.{i}" for i in range(1, 11)]
    register_capabilities(fabric, *caps)

    durations_ns: List[int] = []
    for i in range(ITERATIONS):
        plan = _make_10_step_plan(
            plan_id=f"plan-perf-{i}",
            request_id=f"req-perf-{i}",
            trace_id=f"trace-perf-{i}",
        )
        start_ns = time.perf_counter_ns()
        result = await process_plan(service, plan)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert result == ProcessResult.COMPLETED
        durations_ns.append(elapsed_ns)

    p50, p95, p99 = _percentiles_from_100(durations_ns)
    assert p50 <= p95 <= p99
    assert p99 < TOTAL_OVERHEAD_P99_NS, (
        "Orchestrator overhead P99 exceeded target: "
        f"p50={p50 / 1_000_000:.3f}ms, "
        f"p95={p95 / 1_000_000:.3f}ms, "
        f"p99={p99 / 1_000_000:.3f}ms, "
        f"target<{TOTAL_OVERHEAD_P99_NS / 1_000_000:.1f}ms"
    )


@pytest.mark.performance
@pytest.mark.benchmark
def test_771_dag_wave_construction_p99_under_5ms_for_10_step_plan() -> None:
    """Validate Kahn sort + wave grouping target for 10-step plan (<5ms P99)."""
    plan = _make_10_step_plan(
        plan_id="plan-wave",
        request_id="req-wave",
        trace_id="trace-wave",
    )

    samples_ns: List[int] = []
    for _ in range(ITERATIONS):
        start_ns = time.perf_counter_ns()
        waves = DAGExecutor.build_waves(plan.steps, plan.dependencies)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert len(waves) == 3
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles_from_100(samples_ns)
    assert p99 < WAVE_BUILD_P99_NS, (
        f"Wave construction P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{WAVE_BUILD_P99_NS / 1_000_000:.1f}ms"
    )


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_771_param_resolution_p99_under_1ms_per_step() -> None:
    """Validate ParamResolver per-step latency target (<1ms P99)."""
    from k1.fabric.types import CapabilityResult

    # Reuse concrete resolver instance from wired executor.
    # This keeps benchmark aligned with production wiring.
    service, _ = await orchestrator_for_testing()
    resolver = service._dag_executor._param_resolver

    step = make_step(
        "s2",
        "cap.perf.resolve",
        params={
            "title": "$s1.result.title",
            "nested": {"value": "$s1.result.meta.score"},
            "pair": {
                "left": "$s1.result.meta.left",
                "right": "$s1.result.meta.right",
            },
        },
    )
    prior = {
        "s1": CapabilityResult.success_result(
            request_id="req-resolve",
            data={
                "title": "ok",
                "meta": {"score": 7, "left": "a", "right": "b"},
            },
            provider_id="mock",
            trace_id="trace-resolve",
        )
    }

    samples_ns: List[int] = []
    for _ in range(ITERATIONS):
        start_ns = time.perf_counter_ns()
        params, resolved_capability = resolver.resolve(step, prior)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert params["title"] == "ok"
        assert params["nested"]["value"] == 7
        assert params["pair"] == {"left": "a", "right": "b"}
        assert resolved_capability is None
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles_from_100(samples_ns)
    assert p99 < PARAM_RESOLUTION_P99_NS, (
        f"Param resolution P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{PARAM_RESOLUTION_P99_NS / 1_000_000:.1f}ms"
    )


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_771_constraint_validation_p99_under_5ms() -> None:
    """Validate ConstraintResolver pass target (<5ms P99)."""
    service, adapters = await orchestrator_for_testing()
    fabric = adapters["fabric"]
    register_capabilities(fabric, "cap.constraint.a", "cap.constraint.b")

    plan = make_plan(
        [
            make_step("s1", "cap.constraint.a"),
            make_step("s2", "cap.constraint.b"),
        ],
        deps={"s2": ["s1"]},
        plan_id="plan-constraint",
        request_id="req-constraint",
        trace_id="trace-constraint",
        intent="constraint benchmark",
    )

    samples_ns: List[int] = []
    resolver = service._constraint_resolver
    for _ in range(ITERATIONS):
        start_ns = time.perf_counter_ns()
        validation = await resolver.validate(plan)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert validation.valid is True
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles_from_100(samples_ns)
    assert p99 < CONSTRAINT_VALIDATION_P99_NS, (
        f"Constraint validation P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{CONSTRAINT_VALIDATION_P99_NS / 1_000_000:.1f}ms"
    )


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_771_mailbox_routing_p99_under_1ms() -> None:
    """Validate mailbox dispatch/routing baseline target (<1ms P99)."""
    service, _ = await orchestrator_for_testing()

    orchestrator_logger = logging.getLogger("k1.orchestrator.orchestration.orchestrator_service")
    prior_level = orchestrator_logger.level
    orchestrator_logger.setLevel(logging.CRITICAL)
    try:
        samples_ns: List[int] = []
        for i in range(ITERATIONS):
            req = InterruptRequest(
                interrupt_type="CANCEL_DAG",
                trace_id=f"trace-route-{i}",
                reason="bench",
            )
            start_ns = time.perf_counter_ns()
            result = await service.process(req)
            elapsed_ns = time.perf_counter_ns() - start_ns
            assert result in (
                ProcessResult.COMPLETED,
                ProcessResult.FAILED,
                ProcessResult.CANCELLED,
            )
            samples_ns.append(elapsed_ns)
    finally:
        orchestrator_logger.setLevel(prior_level)

    _, _, p99 = _percentiles_from_100(samples_ns)
    assert p99 < MAILBOX_ROUTING_P99_NS, (
        f"Mailbox/routing P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{MAILBOX_ROUTING_P99_NS / 1_000_000:.1f}ms"
    )


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_771_capreq_construction_p99_under_1ms_per_step() -> None:
    """Validate CapabilityRequest construction target (<1ms P99 per step)."""
    service, _ = await orchestrator_for_testing()
    runner = service._dag_executor._step_runner
    step = make_step(
        "s-capreq",
        "cap.perf.req",
        params={"x": 1, "y": "z"},
    )

    samples_ns: List[int] = []
    for _ in range(ITERATIONS):
        start_ns = time.perf_counter_ns()
        req = runner._build_request(step, step.params, "trace-capreq")
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert req.capability_name == "cap.perf.req"
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles_from_100(samples_ns)
    assert p99 < CAPREQ_BUILD_P99_NS, (
        f"CapReq build P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{CAPREQ_BUILD_P99_NS / 1_000_000:.1f}ms"
    )


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_771_output_schema_validation_p99_under_1ms_per_step() -> None:
    """Validate output schema validation target (<1ms P99 per step)."""
    service, _ = await orchestrator_for_testing()
    runner = service._dag_executor._step_runner
    result = CapabilityResult.success_result(
        request_id="req-schema",
        data={"summary": "ok", "score": 1},
        provider_id="mock",
        trace_id="trace-schema",
    )
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "score": {"type": "number"},
        },
        "required": ["summary", "score"],
    }

    samples_ns: List[int] = []
    for _ in range(ITERATIONS):
        start_ns = time.perf_counter_ns()
        sv = runner.validate_output_schema(result, schema)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert sv.valid is True
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles_from_100(samples_ns)
    assert p99 < SCHEMA_VALIDATION_P99_NS, (
        f"Output schema validation P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{SCHEMA_VALIDATION_P99_NS / 1_000_000:.1f}ms"
    )


@pytest.mark.performance
@pytest.mark.benchmark
def test_771_conditional_edge_eval_p99_under_1ms_per_wave() -> None:
    """Validate conditional edge evaluation target (<1ms P99 per wave)."""
    condition = ConditionExpr(type="EQ", path="s1.result.data.value", literal=42)
    merged_results = {
        "s1": CapabilityResult.success_result(
            request_id="req-cond",
            data={"value": 42},
            provider_id="mock",
            trace_id="trace-cond",
        )
    }

    samples_ns: List[int] = []
    for _ in range(ITERATIONS):
        start_ns = time.perf_counter_ns()
        ok = evaluate_condition(condition, merged_results)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert ok is True
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles_from_100(samples_ns)
    assert p99 < CONDITIONAL_EVAL_P99_NS, (
        f"Conditional eval P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{CONDITIONAL_EVAL_P99_NS / 1_000_000:.1f}ms"
    )


@pytest.mark.performance
@pytest.mark.benchmark
def test_771_discovery_heuristic_p99_under_1ms_per_wave() -> None:
    """Validate ORCH-13 discovery overlap heuristic target (<1ms P99)."""
    from k1.orchestrator.types import Discovery

    discoveries = [Discovery(field="venue_type", value="indoor", source_step_id="s1")]
    remaining_steps = [
        make_step("s2", "cap.next", params={"venue_type": "outdoor", "size": 10}),
        make_step("s3", "cap.next2", params={"budget": 100}),
    ]

    samples_ns: List[int] = []
    for _ in range(ITERATIONS):
        start_ns = time.perf_counter_ns()
        overlap = _check_param_overlap(discoveries, remaining_steps)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert overlap is True
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles_from_100(samples_ns)
    assert p99 < DISCOVERY_HEURISTIC_P99_NS, (
        f"Discovery heuristic P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{DISCOVERY_HEURISTIC_P99_NS / 1_000_000:.1f}ms"
    )


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_771_result_aggregation_p99_under_2ms() -> None:
    """Validate AggregatedResult merge target (<2ms P99)."""
    service, _ = await orchestrator_for_testing()
    steps = [
        StepResult(step_id=f"s{i}", capability_name=f"cap.{i}", status=StepStatus.COMPLETED)
        for i in range(10)
    ]

    samples_ns: List[int] = []
    for _ in range(ITERATIONS):
        start_ns = time.perf_counter_ns()
        agg = service.aggregate(steps, "plan-agg", [], "trace-agg", 10)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert agg.total_steps == 10
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles_from_100(samples_ns)
    assert p99 < RESULT_AGGREGATION_P99_NS, (
        f"Result aggregation P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{RESULT_AGGREGATION_P99_NS / 1_000_000:.1f}ms"
    )


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_771_progress_delta_emission_p99_under_1ms() -> None:

    # ---------------------------------------------------------------------------
    # Epic 7.7.2 - DAG wave construction benchmark
    # ---------------------------------------------------------------------------
    """Validate progress delta construction/emission target (<1ms P99)."""
    service, _ = await orchestrator_for_testing()
    monitor = service._dag_executor._guards[3]
    ctx = ProcessingContext(trace_id="trace-progress", request_id="req-progress", tier="HIGH")
    ctx.dag_id = "dag-progress"
    wave_result = WaveResult(
        wave_index=0,
        step_results=[
            StepResult(
                step_id="s1",
                capability_name="cap.progress",
                status=StepStatus.COMPLETED,
                result=CapabilityResult.success_result(
                    request_id="req-progress-step",
                    data={"ok": True},
                    provider_id="mock",
                    trace_id="trace-progress",
                ),
            )
        ],
        duration_ms=50,
    )

    samples_ns: List[int] = []
    for _ in range(ITERATIONS):
        start_ns = time.perf_counter_ns()
        decision = await monitor.after_wave(wave_result, ctx)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert decision.action.value == "CONTINUE"
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles_from_100(samples_ns)
    assert p99 < PROGRESS_EMIT_P99_NS, (
        f"Progress emission P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{PROGRESS_EMIT_P99_NS / 1_000_000:.1f}ms"
    )


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.parametrize("step_count", [10, 25, 50])
def test_772_wave_construction_scaling_p99_targets(step_count: int) -> None:
    """7.7.2: Validate DAG wave build scales within per-size P99 thresholds."""
    samples_ns: List[int] = []
    for i in range(ITERATIONS_772):
        plan = _make_random_dag_plan(step_count=step_count, seed=10_000 + i)
        start_ns = time.perf_counter_ns()
        waves = DAGExecutor.build_waves(plan.steps, plan.dependencies)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert len(waves) >= 1
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles(samples_ns)
    target_ns = WAVE_BUILD_P99_BY_SIZE_NS[step_count]
    assert p99 < target_ns, (
        f"Wave build P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{target_ns / 1_000_000:.1f}ms for {step_count}-step plan"
    )


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.asyncio
@pytest.mark.parametrize("step_count", [10, 25, 50])
async def test_772_param_resolution_scaling_p99_under_1ms_per_step(step_count: int) -> None:
    """7.7.2: Validate per-step param resolution remains <1ms at scale."""
    service, _ = await orchestrator_for_testing()
    resolver = service._dag_executor._param_resolver

    ref_sid = f"s{step_count}"
    step = make_step(
        "s_target",
        "cap.resolve.scaled",
        params={
            "title": f"${ref_sid}.result.title",
            "meta": {
                "score": f"${ref_sid}.result.meta.score",
                "owner": f"${ref_sid}.result.meta.owner",
            },
            "nested": {"deep": {"flag": f"${ref_sid}.result.meta.flags.ok"}},
        },
    )

    prior = {
        f"s{i}": CapabilityResult.success_result(
            request_id=f"req-prior-{i}",
            data={
                "title": f"doc-{i}",
                "meta": {"score": i, "owner": "ops", "flags": {"ok": True}},
            },
            provider_id="mock",
            trace_id="trace-param-scale",
        )
        for i in range(1, step_count + 1)
    }

    samples_ns: List[int] = []
    for _ in range(ITERATIONS_772):
        start_ns = time.perf_counter_ns()
        params, resolved_capability = resolver.resolve(step, prior)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert params["title"] == f"doc-{step_count}"
        assert params["meta"]["score"] == step_count
        assert params["nested"]["deep"]["flag"] is True
        assert resolved_capability is None
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles(samples_ns)
    assert p99 < PARAM_RESOLUTION_P99_NS, (
        f"Param resolution P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{PARAM_RESOLUTION_P99_NS / 1_000_000:.1f}ms at {step_count} steps"
    )


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.asyncio
@pytest.mark.parametrize("width", [4, 8, 10])
async def test_772_wave_dispatch_overhead_p99_under_1ms(width: int) -> None:
    """7.7.2: Validate asyncio gather setup overhead remains <1ms P99."""

    async def _noop() -> int:
        return 1

    samples_ns: List[int] = []
    for _ in range(ITERATIONS_772):
        start_ns = time.perf_counter_ns()
        results = await asyncio.gather(*[_noop() for _ in range(width)])
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert sum(results) == width
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles(samples_ns)
    assert p99 < WAVE_DISPATCH_OVERHEAD_P99_NS, (
        f"Wave dispatch overhead P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{WAVE_DISPATCH_OVERHEAD_P99_NS / 1_000_000:.1f}ms (width={width})"
    )


@pytest.mark.performance
@pytest.mark.benchmark
def test_772_dag_memory_50_step_under_1mb() -> None:
    """7.7.2: Validate 50-step DAG build memory footprint stays <1MB."""
    plan = _make_random_dag_plan(step_count=50, seed=777, max_deps=3)

    tracemalloc.start()
    try:
        _ = DAGExecutor.build_waves(plan.steps, plan.dependencies)
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < MEMORY_50_STEP_MAX_BYTES, (
        f"50-step DAG peak memory {peak} bytes exceeds " f"{MEMORY_50_STEP_MAX_BYTES} bytes"
    )


@pytest.mark.performance
@pytest.mark.benchmark
def test_772_wave_construction_edge_cases_sparse_and_dense_50_step() -> None:
    """7.7.2 edge cases: sparse-chain and dense-near-limit DAG shapes."""
    chain_steps = [make_step(f"s{i}", f"cap.chain.{i}") for i in range(1, 51)]
    # Sparse ladder: 3 interleaved chains (keeps wave count <= MAX_WAVES=20).
    chain_deps = {f"s{i}": [f"s{i-3}"] for i in range(4, 51)}
    chain_plan = make_plan(
        chain_steps,
        deps=chain_deps,
        plan_id="plan-chain-50",
        request_id="req-chain-50",
        trace_id="trace-chain-50",
        intent="edge-case sparse chain",
    )

    dense_steps = [make_step(f"d{i}", f"cap.dense.{i}") for i in range(1, 51)]
    dense_deps: Dict[str, List[str]] = {}
    # Dense layered graph: 10 layers × 5 steps, each layer depends on all 5
    # steps from the previous layer (high edge count, bounded wave count).
    layer_size = 5
    for layer in range(1, 10):
        prev_start = (layer - 1) * layer_size + 1
        prev_ids = [f"d{j}" for j in range(prev_start, prev_start + layer_size)]
        cur_start = layer * layer_size + 1
        for j in range(cur_start, cur_start + layer_size):
            dense_deps[f"d{j}"] = prev_ids
    dense_plan = make_plan(
        dense_steps,
        deps=dense_deps,
        plan_id="plan-dense-50",
        request_id="req-dense-50",
        trace_id="trace-dense-50",
        intent="edge-case dense near-limit",
    )

    samples_chain: List[int] = []
    samples_dense: List[int] = []
    for _ in range(ITERATIONS_772):
        t0 = time.perf_counter_ns()
        chain_waves = DAGExecutor.build_waves(chain_plan.steps, chain_plan.dependencies)
        samples_chain.append(time.perf_counter_ns() - t0)
        assert 15 <= len(chain_waves) <= 20

        t1 = time.perf_counter_ns()
        dense_waves = DAGExecutor.build_waves(dense_plan.steps, dense_plan.dependencies)
        samples_dense.append(time.perf_counter_ns() - t1)
        assert 9 <= len(dense_waves) <= 12

    _, _, p99_chain = _percentiles(samples_chain)
    _, _, p99_dense = _percentiles(samples_dense)
    target_ns = WAVE_BUILD_P99_BY_SIZE_NS[50]
    assert p99_chain < target_ns
    assert p99_dense < target_ns


@pytest.mark.performance
@pytest.mark.benchmark
def test_772_wave_construction_realworld_fanout_fanin_p99_under_10ms() -> None:
    """7.7.2 real-life usage: ETL-style fan-out/fan-in orchestration graph."""
    plan = _make_realworld_fanout_fanin_plan()

    samples_ns: List[int] = []
    for _ in range(ITERATIONS_772):
        start_ns = time.perf_counter_ns()
        waves = DAGExecutor.build_waves(plan.steps, plan.dependencies)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert len(waves) >= 7
        assert len(waves[0].steps) == 1
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles(samples_ns)
    assert p99 < WAVE_BUILD_P99_BY_SIZE_NS[25], (
        f"Real-world fanout/fanin wave-build P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{WAVE_BUILD_P99_BY_SIZE_NS[25] / 1_000_000:.1f}ms"
    )


# ---------------------------------------------------------------------------
# Epic 7.7.3 - End-to-end DAG execution benchmark
# ---------------------------------------------------------------------------


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.asyncio
@pytest.mark.parametrize("step_count", [10, 25, 50])
async def test_773_e2e_overhead_scaling_p99_targets(step_count: int) -> None:
    """7.7.3: End-to-end Orchestrator overhead scaling on layered DAGs."""
    service, adapters = await orchestrator_for_testing()
    fabric = adapters["fabric"]

    register_capabilities(fabric, *[f"cap.exec.{i}" for i in range(1, 51)])

    samples_ns: List[int] = []
    for i in range(ITERATIONS_773):
        plan = _make_layered_execution_plan(
            step_count=step_count,
            layer_size=5,
            plan_id=f"plan-773-layered-{step_count}-{i}",
            request_id=f"req-773-layered-{step_count}-{i}",
            trace_id=f"trace-773-layered-{step_count}-{i}",
        )

        start_ns = time.perf_counter_ns()
        result = await process_plan(service, plan)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert result == ProcessResult.COMPLETED
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles(samples_ns)
    target_ns = E2E_OVERHEAD_P99_BY_SIZE_NS[step_count]
    assert p99 < target_ns, (
        f"7.7.3 e2e overhead P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{target_ns / 1_000_000:.1f}ms for {step_count}-step layered DAG"
    )


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_773_e2e_realworld_fanout_fanin_p99_under_50ms() -> None:
    """7.7.3 real-life usage: complete orchestration of fanout/fanin workflow."""
    service, adapters = await orchestrator_for_testing()
    fabric = adapters["fabric"]
    register_capabilities(fabric, *[f"cap.real.{i}" for i in range(1, 26)])

    samples_ns: List[int] = []
    for i in range(ITERATIONS_773):
        plan = _make_realworld_fanout_fanin_plan(
            plan_id=f"plan-773-real-{i}",
            request_id=f"req-773-real-{i}",
            trace_id=f"trace-773-real-{i}",
        )

        start_ns = time.perf_counter_ns()
        result = await process_plan(service, plan)
        elapsed_ns = time.perf_counter_ns() - start_ns
        assert result == ProcessResult.COMPLETED
        samples_ns.append(elapsed_ns)

    _, _, p99 = _percentiles(samples_ns)
    assert p99 < E2E_REALWORLD_P99_NS, (
        f"7.7.3 real-world e2e P99 {p99 / 1_000_000:.3f}ms exceeds "
        f"{E2E_REALWORLD_P99_NS / 1_000_000:.1f}ms"
    )
