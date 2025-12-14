"""
Test P02 Pipeline Parallel Execution - Real World Verification

Tests the actual P02 Write pipeline YAML to verify:
1. DAG is correctly parsed and levels computed
2. Parallel execution groups are identified
3. Expected performance characteristics

Related:
- k0/contracts/pipelines/p02_write.v1.yaml: Production pipeline spec
- k0/runtime/pipeline_runner.py: Parallel execution implementation
- k0/runtime/dag_builder.py: Level computation
"""

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from k0.bus.core import BusMessage
from k0.pipelines.protocol import PipelineContext
from k0.runtime.module_registry import ModuleRegistry
from k0.runtime.pipeline_runner import PipelineRunner
from k0.runtime.schemas import PipelineSpec


@pytest.fixture
def p02_spec():
    """Load actual P02 pipeline specification."""
    spec_path = Path("d:/familyos/k0/contracts/pipelines/p02_write.v1.yaml")
    return PipelineSpec.load(spec_path)


@pytest.fixture
def mock_p02_registry():
    """
    Create mock registry for P02 modules with realistic timing.

    Timing based on module contracts (latency_budget_ms):
    - Pattern separate: 15ms
    - Semantic project: 30ms
    - Affect analyze: 20ms
    - Space resolve: 15ms
    - Social resolve: 25ms
    - Temporal profile: 10ms
    - Device profile: 5ms
    - Ingress classify: 10ms
    - Geo metadata: 15ms
    - Spatial minimal: 5ms
    - Retention lookup: 10ms
    - Salience score: 15ms
    - Row builder: 20ms
    - Embedding queue: 10ms
    - Atomic writer: 25ms
    - Event emitter: 10ms
    """
    registry = MagicMock(spec=ModuleRegistry)

    # Track execution order and timing
    execution_log = []

    def mock_module(module_id: str, delay_ms: int):
        """Mock module that records execution timing."""

        async def run(**kwargs):
            start = time.time()
            execution_log.append(
                {
                    "module_id": module_id,
                    "stage_id": (
                        kwargs.get("context", MagicMock()).logger.name
                        if hasattr(kwargs.get("context", MagicMock()), "logger")
                        else "unknown"
                    ),
                    "start_time": start,
                }
            )
            await asyncio.sleep(delay_ms / 1000.0)
            end = time.time()
            execution_log[-1]["end_time"] = end
            execution_log[-1]["duration_ms"] = (end - start) * 1000
            # Return enrichment (module_id as key for tracking)
            return {module_id.replace(".", "_").replace(":", "_"): f"enriched_by_{module_id}"}

        return run

    # Register all P02 modules with realistic timings
    modules = {
        "hippocampus.pattern_separate:v1": 15,
        "hippocampus.semantic_project:v1": 30,
        "affect.analyze:v1": 20,
        "space.resolve_visibility:v1": 15,
        "social.family_graph_resolve:v1": 25,
        "context.temporal_profile:v1": 10,
        "context.device_profile:v1": 5,
        "context.ingress_classify:v1": 10,
        "context.geo_metadata:v1": 15,
        "context.spatial_minimal:v1": 5,
        "context.retention_lookup:v1": 10,
        "salience.score:v1": 15,
        "builders.hipp_events_row:v1": 20,
        "builders.embedding_queue_write:v1": 10,
        "core.hipp_events_writer:v1": 25,
        "core.event_emitter:v1": 10,
    }

    registry.get = MagicMock(
        side_effect=lambda module_id: mock_module(module_id, modules[module_id])
    )
    registry.execution_log = execution_log
    return registry


@pytest.fixture
def mock_context():
    """Create mock pipeline context."""
    context = MagicMock(spec=PipelineContext)
    context.logger = MagicMock()
    return context


def test_p02_dag_structure(p02_spec):
    """
    Test that P02 DAG is correctly parsed and structured.

    Expected structure:
    - 13 stages total
    - Multiple execution levels
    - Parallel groups identified (stages 30-33, 40-43)
    """
    from k0.runtime.dag_builder import build_dag

    dag = build_dag(p02_spec)

    # Verify stage count
    assert len(dag) == 16, f"Expected 16 stages, got {len(dag)}"

    # Get level groups for parallel execution
    level_groups = dag.get_level_groups()

    # Verify we have multiple levels
    assert len(level_groups) > 5, f"Expected multiple levels, got {len(level_groups)}"

    # Verify Level 0: stage_10 (pattern separation)
    level_0 = [s.id for s in level_groups[0]]
    assert "stage_10_dg_pattern_separate" in level_0
    assert len(level_0) == 1

    # Verify Level 1: stage_20 (semantic projection)
    level_1 = [s.id for s in level_groups[1]]
    assert "stage_20_ca1_semantic_project" in level_1
    assert len(level_1) == 1

    # Verify Level 2: parallel stages (9 stages that depend on stage_20)
    # These all depend on stage_20 and can run in parallel
    level_2 = [s.id for s in level_groups[2]]
    # Note: Actual count may vary based on P02 YAML updates
    # Key point: multiple stages can run in parallel
    assert len(level_2) >= 8, f"Expected at least 8 parallel stages in Level 2, got {len(level_2)}"

    # Verify some known parallel stages are in Level 2
    expected_in_level_2 = {
        "stage_30_affect_analyze",
        "stage_31_space_resolve",
        "stage_32_social_resolve",
        "stage_33_temporal_profile",
        "stage_40_device_profile",
    }
    assert expected_in_level_2.issubset(
        set(level_2)
    ), f"Missing expected stages in Level 2: {level_2}"

    # Verify stages 50, 55 are in subsequent levels (depend on Level 2)
    all_stage_ids = {s.id for level in level_groups for s in level}
    assert "stage_50_retention_lookup" in all_stage_ids
    assert "stage_55_salience_score" in all_stage_ids

    # Verify final stages (60, 61, 70, 80) exist
    assert "stage_60_build_hipp_events_row" in all_stage_ids
    assert "stage_61_build_embedding_queue_job" in all_stage_ids
    assert "stage_70_atomic_writer" in all_stage_ids
    assert "stage_80_event_emitter" in all_stage_ids


@pytest.mark.asyncio
async def test_p02_parallel_execution_timing(p02_spec, mock_p02_registry, mock_context):
    """
    Test P02 pipeline executes with parallel optimization.

    Expected timing:
    - Sequential: ~240ms (sum of all stages)
    - Parallel: ~150ms (Level 2 runs in max(8 stages) = 25ms instead of sum)
    """
    runner = PipelineRunner(p02_spec, mock_p02_registry)
    await runner.on_startup(mock_context)

    # Verify level groups computed correctly
    assert len(runner._level_groups) >= 6, "Expected at least 6 execution levels"

    # Verify max parallelism (Level 2 has multiple parallel stages)
    assert (
        runner._max_parallelism >= 8
    ), f"Expected max parallelism >= 8, got {runner._max_parallelism}"

    # Execute pipeline
    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=b'{"event_type": "memory_write", "content": "test memory"}',
        offset=1,
        trace_id="test-p02-trace-001",
    )

    start_time = time.time()
    await runner.handle(message)
    total_duration_ms = (time.time() - start_time) * 1000

    # Verify parallel execution performance
    # Sequential would take: ~240ms (sum of all stages)
    # Parallel should take: ~140-150ms (max per level)

    # Allow some overhead (async scheduling, etc.) but verify significant speedup
    # With 16 stages and async overhead, allow up to 210ms (still much faster than 240ms sequential)
    assert total_duration_ms < 220, (
        f"P02 took {total_duration_ms:.1f}ms, expected ~140-150ms with parallel execution. "
        f"Sequential would be ~240ms. Check if stages are actually running in parallel."
    )

    assert (
        total_duration_ms > 130
    ), f"P02 took {total_duration_ms:.1f}ms, suspiciously fast. Expected ~150ms."

    # Verify Level 2 stages executed in parallel (start times close together)
    level_2_stage_ids = [
        "affect.analyze:v1",
        "space.resolve_visibility:v1",
        "social.family_graph_resolve:v1",
        "context.temporal_profile:v1",
        "context.device_profile:v1",
        "context.ingress_classify:v1",
        "context.geo_metadata:v1",
        "context.spatial_minimal:v1",
    ]

    level_2_executions = [
        entry
        for entry in mock_p02_registry.execution_log
        if entry["module_id"] in level_2_stage_ids
    ]

    assert (
        len(level_2_executions) >= 8
    ), f"Expected at least 8 Level 2 stages to execute, got {len(level_2_executions)}"

    # Verify parallel execution: start times should be within 10ms of each other
    start_times = [e["start_time"] for e in level_2_executions]
    max_start_delta = max(start_times) - min(start_times)
    assert (
        max_start_delta < 0.01
    ), f"Level 2 stages should start concurrently, but delta was {max_start_delta * 1000:.1f}ms"


@pytest.mark.asyncio
async def test_p02_metrics_exposure(p02_spec, mock_p02_registry, mock_context):
    """Test that P02 runner exposes correct parallelism metrics."""
    runner = PipelineRunner(p02_spec, mock_p02_registry)
    await runner.on_startup(mock_context)

    metrics = runner.get_metrics()

    assert metrics["pipeline_id"] == "P02_WRITE"
    assert metrics["stage_count"] == 16
    assert metrics["execution_levels"] >= 6
    assert metrics["max_parallelism"] >= 8, "Level 2 has multiple parallel stages"


def test_p02_dependency_validation(p02_spec):
    """
    Verify P02 dependencies are correct and allow maximum parallelism.

    This test documents the expected parallel groups:
    - Group 1 (Level 2): stages 30-43+ (8+ stages, all depend only on stage_20)
    - Group 2 (later level): stages 60-61 (2 stages, builders can run in parallel)
    """
    from k0.runtime.dag_builder import build_dag

    dag = build_dag(p02_spec)

    # Verify stage_30-43 only depend on stage_20 (allowing parallelism)
    parallel_stage_ids = [
        "stage_30_affect_analyze",
        "stage_31_space_resolve",
        "stage_32_social_resolve",
        "stage_33_temporal_profile",
        "stage_40_device_profile",
        "stage_41_ingress_classify",
        "stage_42_geo_metadata",
        "stage_43_spatial_minimal",
    ]

    for stage_id in parallel_stage_ids:
        deps = dag.get_dependencies(stage_id)
        assert "stage_20_ca1_semantic_project" in deps, f"{stage_id} should depend on stage_20"
        # Most should only depend on stage_20 (allowing parallel execution)
        if stage_id not in ["stage_50_retention_lookup", "stage_55_salience_score"]:
            assert len(deps) == 1, (
                f"{stage_id} should only depend on stage_20 for max parallelism, "
                f"but has deps: {deps}"
            )

    # Verify stage_60 (row builder) depends on ALL enrichment stages
    # This is intentional - it needs complete enriched envelope
    stage_60_deps = dag.get_dependencies("stage_60_build_hipp_events_row")
    assert (
        len(stage_60_deps) == 12
    ), f"stage_60 should depend on 12 stages (all enrichments), got {len(stage_60_deps)}"

    # Verify stage_61 (embedding queue) only depends on stage_20
    # This allows it to potentially run in parallel with other stages
    stage_61_deps = dag.get_dependencies("stage_61_build_embedding_queue_job")
    assert stage_61_deps == {
        "stage_20_ca1_semantic_project"
    }, f"stage_61 should only depend on stage_20, got {stage_61_deps}"


@pytest.mark.asyncio
async def test_p02_envelope_enrichment(p02_spec, mock_p02_registry, mock_context):
    """
    Test that P02 parallel stages correctly enrich the envelope.

    Each module should contribute its fields to the shared envelope.
    """
    runner = PipelineRunner(p02_spec, mock_p02_registry)
    await runner.on_startup(mock_context)

    message = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=b'{"event_type": "memory_write", "content": "test memory"}',
        offset=1,
        trace_id="test-p02-trace-002",
    )

    await runner.handle(message)

    # Verify enriched envelope contains contributions from all modules
    enriched = runner._enriched_envelope
    assert enriched is not None, "Envelope should be enriched"

    # Verify some Level 2 modules contributed
    expected_level_2_modules = [
        "affect_analyze_v1",
        "space_resolve_visibility_v1",
        "social_family_graph_resolve_v1",
        "context_temporal_profile_v1",
        "context_device_profile_v1",
    ]

    for module_key in expected_level_2_modules:
        assert module_key in enriched, (
            f"Expected {module_key} to enrich envelope, but not found. "
            f"Available keys: {list(enriched.keys())}"
        )


def test_p02_expected_performance_characteristics(p02_spec):
    """
    Document expected P02 performance characteristics.

    This test serves as documentation for performance expectations.
    """
    from k0.runtime.dag_builder import build_dag

    dag = build_dag(p02_spec)
    level_groups = dag.get_level_groups()

    # Calculate theoretical timing (based on module latency budgets)
    # Sequential: sum of all modules
    # Parallel: sum of max(level) for each level

    module_timings = {
        "stage_10_dg_pattern_separate": 15,
        "stage_20_ca1_semantic_project": 30,
        "stage_30_affect_analyze": 20,
        "stage_31_space_resolve": 15,
        "stage_32_social_resolve": 25,
        "stage_33_temporal_profile": 10,
        "stage_40_device_profile": 5,
        "stage_41_ingress_classify": 10,
        "stage_42_geo_metadata": 15,
        "stage_43_spatial_minimal": 5,
        "stage_50_retention_lookup": 10,
        "stage_55_salience_score": 15,
        "stage_60_build_hipp_events_row": 20,
        "stage_61_build_embedding_queue_job": 10,
        "stage_70_atomic_writer": 25,
        "stage_80_event_emitter": 10,
    }

    # Sequential timing
    sequential_total = sum(module_timings.values())

    # Parallel timing (max per level)
    parallel_total = 0
    for level in level_groups:
        level_max = max(module_timings.get(s.id, 0) for s in level)
        parallel_total += level_max

    print("\nP02 Performance Characteristics:")
    print(f"  Total stages: {len(dag)}")
    print(f"  Execution levels: {len(level_groups)}")
    print(f"  Max parallelism: {max(len(level) for level in level_groups)}")
    print(f"  Sequential timing: {sequential_total}ms")
    print(f"  Parallel timing: {parallel_total}ms")
    print(f"  Speedup: {sequential_total / parallel_total:.2f}x")
    print(f"  Time saved: {sequential_total - parallel_total}ms")

    # Verify we get significant speedup
    assert (
        parallel_total < sequential_total * 0.7
    ), "Parallel execution should be at least 30% faster than sequential"

    # Document expected values
    assert 140 <= parallel_total <= 160, f"Expected parallel timing ~150ms, got {parallel_total}ms"
