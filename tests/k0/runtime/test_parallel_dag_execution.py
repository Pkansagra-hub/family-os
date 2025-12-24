"""
Test Parallel DAG Execution - Verify Level-Based Concurrency

Tests that pipeline_runner correctly executes stages in parallel within levels
and sequentially across levels based on DAG dependencies.

Related:
- k0/runtime/pipeline_runner.py: Parallel execution implementation
- k0/runtime/dag_builder.py: Level computation
"""

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from k0.bus.core import BusMessage
from k0.pipelines.protocol import PipelineContext
from k0.runtime.module_registry import ModuleRegistry
from k0.runtime.pipeline_runner import PipelineRunner
from k0.runtime.schemas import PipelineSpec, StageSpec


@pytest.fixture
def mock_registry():
    """Create mock module registry with timing instrumentation."""
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
                    "start_time": start,
                    "thread_id": id(asyncio.current_task()),
                }
            )
            await asyncio.sleep(delay_ms / 1000.0)
            end = time.time()
            execution_log[-1]["end_time"] = end
            execution_log[-1]["duration_ms"] = (end - start) * 1000
            return {"enriched_by": module_id}

        return run

    # Register mock modules with known delays
    registry.get = MagicMock(
        side_effect=lambda module_id: {
            "test.stage_a:v1": mock_module("stage_a", 50),
            "test.stage_b:v1": mock_module("stage_b", 50),
            "test.stage_c:v1": mock_module("stage_c", 50),
            "test.stage_d:v1": mock_module("stage_d", 50),
            "test.stage_e:v1": mock_module("stage_e", 50),
        }[module_id]
    )

    registry.execution_log = execution_log
    return registry


@pytest.fixture
def mock_context():
    """Create mock pipeline context."""
    context = MagicMock(spec=PipelineContext)
    context.logger = MagicMock()
    return context


@pytest.mark.asyncio
async def test_parallel_execution_within_level(mock_registry, mock_context):
    """
    Test that stages within same level execute in parallel.

    DAG:
        stage_a (Level 0)
           |
           +---> stage_b (Level 1)
           +---> stage_c (Level 1)
           +---> stage_d (Level 1)
           |
        stage_e (Level 2)

    Expected:
    - Level 0: stage_a (50ms)
    - Level 1: stage_b, stage_c, stage_d (50ms in parallel)
    - Level 2: stage_e (50ms)
    - Total: ~150ms (not 250ms if sequential)
    """
    spec = PipelineSpec(
        pipeline_id="P99_TEST_PARALLEL",
        version="v1",
        entry_topic="test.parallel.v1",
        dag=[
            StageSpec(id="stage_a", module="test.stage_a:v1", after=[]),
            StageSpec(id="stage_b", module="test.stage_b:v1", after=["stage_a"]),
            StageSpec(id="stage_c", module="test.stage_c:v1", after=["stage_a"]),
            StageSpec(id="stage_d", module="test.stage_d:v1", after=["stage_a"]),
            StageSpec(
                id="stage_e", module="test.stage_e:v1", after=["stage_b", "stage_c", "stage_d"]
            ),
        ],
    )

    runner = PipelineRunner(spec, mock_registry)
    await runner.on_startup(mock_context)

    # Verify level computation
    assert len(runner._level_groups) == 3
    assert len(runner._level_groups[0]) == 1  # stage_a
    assert len(runner._level_groups[1]) == 3  # stage_b, stage_c, stage_d
    assert len(runner._level_groups[2]) == 1  # stage_e

    # Execute pipeline
    message = BusMessage(
        topic="test.parallel.v1",
        payload=b'{"test": "data"}',
        offset=1,
        trace_id="test-trace-001",
    )

    start_time = time.time()
    await runner.handle(message)
    total_duration_ms = (time.time() - start_time) * 1000

    # Verify parallel execution by checking timing
    # Sequential would take: 50 + 50 + 50 + 50 + 50 = 250ms
    # Parallel should take: 50 + 50 + 50 = ~150ms (with some overhead)
    assert (
        total_duration_ms < 280
    ), f"Execution took {total_duration_ms}ms, expected ~150ms (parallel)"
    assert total_duration_ms > 140, f"Execution took {total_duration_ms}ms, seems too fast"

    # Verify execution order
    log = mock_registry.execution_log
    assert len(log) == 5

    # Verify Level 1 stages (b, c, d) executed in parallel
    # Their start times should be very close (within 10ms)
    level_1_stages = [
        entry for entry in log if entry["module_id"] in ["stage_b", "stage_c", "stage_d"]
    ]
    assert len(level_1_stages) == 3

    start_times = [s["start_time"] for s in level_1_stages]
    max_start_delta = max(start_times) - min(start_times)
    assert (
        max_start_delta < 0.01
    ), f"Level 1 stages should start concurrently, but delta was {max_start_delta * 1000}ms"


@pytest.mark.asyncio
async def test_sequential_execution_across_levels(mock_registry, mock_context):
    """
    Test that stages in different levels execute sequentially.

    DAG:
        stage_a (Level 0)
           |
        stage_b (Level 1)
           |
        stage_c (Level 2)

    Expected:
    - Level 0: stage_a (50ms)
    - Wait for completion
    - Level 1: stage_b (50ms)
    - Wait for completion
    - Level 2: stage_c (50ms)
    - Total: ~150ms
    """
    spec = PipelineSpec(
        pipeline_id="P98_TEST_SEQUENTIAL",
        version="v1",
        entry_topic="test.sequential.v1",
        dag=[
            StageSpec(id="stage_a", module="test.stage_a:v1", after=[]),
            StageSpec(id="stage_b", module="test.stage_b:v1", after=["stage_a"]),
            StageSpec(id="stage_c", module="test.stage_c:v1", after=["stage_b"]),
        ],
    )

    runner = PipelineRunner(spec, mock_registry)
    await runner.on_startup(mock_context)

    # Verify level computation
    assert len(runner._level_groups) == 3
    assert len(runner._level_groups[0]) == 1  # stage_a
    assert len(runner._level_groups[1]) == 1  # stage_b
    assert len(runner._level_groups[2]) == 1  # stage_c

    # Execute pipeline
    message = BusMessage(
        topic="test.sequential.v1",
        payload=b'{"test": "data"}',
        offset=1,
        trace_id="test-trace-002",
    )

    await runner.handle(message)

    # Verify execution order
    log = mock_registry.execution_log
    assert len(log) == 3

    # Verify stages executed in order: a -> b -> c
    # Each stage should start AFTER previous stage ends
    for i in range(len(log) - 1):
        current_end = log[i]["end_time"]
        next_start = log[i + 1]["start_time"]
        assert next_start >= current_end, f"Stage {i+1} started before stage {i} completed"


@pytest.mark.asyncio
async def test_envelope_enrichment_across_parallel_stages(mock_registry, mock_context):
    """
    Test that parallel stages can independently enrich the envelope.

    DAG:
        stage_a (sets base)
           |
           +---> stage_b (adds field_b)
           +---> stage_c (adds field_c)

    Expected:
    - After execution, envelope should have contributions from all stages
    """

    # Override mock to return specific enrichments
    async def mock_stage_a(**kwargs):
        return {"base": "from_a", "stage_a_ran": True}

    async def mock_stage_b(**kwargs):
        envelope = kwargs.get("envelope", {})
        return {**envelope, "field_b": "from_b", "stage_b_ran": True}

    async def mock_stage_c(**kwargs):
        envelope = kwargs.get("envelope", {})
        return {**envelope, "field_c": "from_c", "stage_c_ran": True}

    mock_registry.get = MagicMock(
        side_effect=lambda module_id: {
            "test.stage_a:v1": mock_stage_a,
            "test.stage_b:v1": mock_stage_b,
            "test.stage_c:v1": mock_stage_c,
        }[module_id]
    )

    spec = PipelineSpec(
        pipeline_id="P97_TEST_ENRICHMENT",
        version="v1",
        entry_topic="test.enrichment.v1",
        dag=[
            StageSpec(id="stage_a", module="test.stage_a:v1", after=[]),
            StageSpec(id="stage_b", module="test.stage_b:v1", after=["stage_a"]),
            StageSpec(id="stage_c", module="test.stage_c:v1", after=["stage_a"]),
        ],
    )

    runner = PipelineRunner(spec, mock_registry)
    await runner.on_startup(mock_context)

    message = BusMessage(
        topic="test.enrichment.v1",
        payload=b'{"original": "data"}',
        offset=1,
        trace_id="test-trace-003",
    )

    await runner.handle(message)

    # Verify enriched envelope contains contributions from all stages
    enriched = runner._enriched_envelope
    assert enriched is not None
    assert enriched.get("base") == "from_a"
    assert enriched.get("field_b") == "from_b"
    assert enriched.get("field_c") == "from_c"
    assert enriched.get("stage_a_ran") is True
    assert enriched.get("stage_b_ran") is True
    assert enriched.get("stage_c_ran") is True


@pytest.mark.asyncio
async def test_metrics_include_parallelism_info(mock_registry, mock_context):
    """Test that metrics expose parallelism information."""
    spec = PipelineSpec(
        pipeline_id="P96_TEST_METRICS",
        version="v1",
        entry_topic="test.metrics.v1",
        dag=[
            StageSpec(id="stage_a", module="test.stage_a:v1", after=[]),
            StageSpec(id="stage_b", module="test.stage_b:v1", after=["stage_a"]),
            StageSpec(id="stage_c", module="test.stage_c:v1", after=["stage_a"]),
            StageSpec(id="stage_d", module="test.stage_d:v1", after=["stage_a"]),
        ],
    )

    runner = PipelineRunner(spec, mock_registry)
    await runner.on_startup(mock_context)

    metrics = runner.get_metrics()

    assert metrics["execution_levels"] == 2
    assert metrics["max_parallelism"] == 3  # Level 1 has 3 stages
    assert metrics["stage_count"] == 4
