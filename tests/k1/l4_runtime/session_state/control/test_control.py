"""
WARD Tests for SessionState Control (RwLock + Delta Batching)

Test Coverage:
    - Lock acquisition (read/write, concurrent access)
    - Delta computation correctness
    - Batching behavior (250ms interval, 100 delta limit)
    - K0 flush integration
    - Performance budgets validation
    - Error handling and recovery
    - Metrics emission

Performance Validation:
    - Lock acquire: <0.1ms P95
    - Delta computation: <5ms P95
    - K0 flush: <100ms P95

Related ADRs:
    - ADR-0038b: K0 WAL Integration (flush behavior)
    - ADR-0045a: K1 Event Bus (session updates)
    - ADR-0061: Backpressure Cascade (watermark monitoring)

Test Framework: WARD (https://ward.readthedocs.io/)
Run: python -m ward test --path tests/k1/l4_runtime/session_state/
"""

import asyncio
import time
from typing import List
from unittest.mock import AsyncMock, Mock, patch

from ward import fixture, test

# System under test
from k1.l4_runtime.session_state.control.control import SessionStateControl
from k1.l4_runtime.session_state.model.wrapper import (
    SessionStateDelta,
    SessionStateWrapper,
)
from k1.l5_infrastructure.bridge_k0.batch_client import BatchClient

# ============================================================================
# Fixtures
# ============================================================================


@fixture
def mock_batch_client():
    """Fixture: Mock BatchClient for testing"""
    client = Mock(spec=BatchClient)
    client.add_delta = AsyncMock(return_value=None)
    client.flush = AsyncMock(return_value=None)
    return client


@fixture
def session_state_control(mock_batch_client=mock_batch_client):
    """Fixture: SessionStateControl instance"""
    control = SessionStateControl(
        session_id="test_session_001",
        batch_client=mock_batch_client,
        flush_interval_ms=250,
        max_pending_deltas=100,
        enable_auto_flush=False,  # Disable for deterministic testing
        cognitive_trace_id="test_trace_001",
    )
    return control


@fixture
async def started_control(session_state_control=session_state_control):
    """Fixture: Started SessionStateControl"""
    await session_state_control.start()
    yield session_state_control
    await session_state_control.stop(flush_pending=False)


# ============================================================================
# Test Suite: Initialization & Lifecycle
# ============================================================================


@test("SessionStateControl initializes with default state")
async def _(control=session_state_control):
    """Verify control initializes with empty SessionState"""
    assert control.session_id == "test_session_001"
    assert control.flush_interval_ms == 250
    assert control.max_pending_deltas == 100
    assert control.get_pending_delta_count() == 0
    assert not control._running


@test("SessionStateControl starts and stops cleanly")
async def _(control=session_state_control):
    """Verify start/stop lifecycle"""
    # Start control
    await control.start()
    assert control._running

    # Stop control
    await control.stop(flush_pending=False)
    assert not control._running


@test("SessionStateControl double-start is safe (idempotent)")
async def _(control=session_state_control):
    """Verify calling start() twice doesn't fail"""
    await control.start()
    await control.start()  # Should log warning, not crash
    assert control._running

    await control.stop(flush_pending=False)


# ============================================================================
# Test Suite: Read Operations (Concurrent Access)
# ============================================================================


@test("SessionStateControl read_state returns current state")
async def _(control=started_control):
    """Verify read_state returns SessionStateWrapper"""
    state = await control.read_state()
    assert isinstance(state, SessionStateWrapper)
    assert state.get_session_id() == "test_session_001"


@test("SessionStateControl concurrent reads don't block (<0.1ms each)")
async def _(control=started_control):
    """Verify 100 concurrent reads complete quickly"""
    start_time = time.perf_counter()

    # Launch 100 concurrent reads
    read_tasks = [control.read_state() for _ in range(100)]
    states = await asyncio.gather(*read_tasks)

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    # Verify all reads succeeded
    assert len(states) == 100
    assert all(isinstance(s, SessionStateWrapper) for s in states)

    # Verify performance (<10ms total for 100 reads)
    assert elapsed_ms < 10.0, f"100 reads took {elapsed_ms:.2f}ms (expected <10ms)"


@test("SessionStateControl read_state lock acquisition is fast (<0.1ms P95)")
async def _(control=started_control):
    """Verify lock acquisition meets performance budget"""
    latencies_ms: List[float] = []

    # Sample 100 read operations
    for _ in range(100):
        start_time = time.perf_counter()
        await control.read_state()
        latency_ms = (time.perf_counter() - start_time) * 1000
        latencies_ms.append(latency_ms)

    # Compute P95 latency
    latencies_ms.sort()
    p95_latency_ms = latencies_ms[int(len(latencies_ms) * 0.95)]

    # Verify P95 <0.1ms
    assert (
        p95_latency_ms < 0.1
    ), f"P95 read latency {p95_latency_ms:.4f}ms exceeds 0.1ms budget"


# ============================================================================
# Test Suite: Write Operations (Delta Tracking)
# ============================================================================


@test("SessionStateControl update_state marks section dirty")
async def _(control=started_control):
    """Verify update_state tracks changes"""
    # Update beliefs section
    delta = await control.update_state({"beliefs.facts[0].key": "user.name"})

    assert isinstance(delta, SessionStateDelta)
    assert control.get_pending_delta_count() == 1


@test("SessionStateControl update_state computes delta correctly")
async def _(control=started_control):
    """Verify delta computation identifies changed sections"""
    # Update control section
    delta = await control.update_state({"control.current_flow": "flow_abc123"})

    # Verify delta includes control section
    changed_sections = delta.get_changed_section_names()
    assert "control" in changed_sections


@test("SessionStateControl update_state delta computation is fast (<5ms P95)")
async def _(control=started_control):
    """Verify delta computation meets performance budget"""
    latencies_ms: List[float] = []

    # Sample 100 update operations
    for i in range(100):
        start_time = time.perf_counter()
        await control.update_state({f"beliefs.fact_{i}": f"value_{i}"})
        latency_ms = (time.perf_counter() - start_time) * 1000
        latencies_ms.append(latency_ms)

    # Compute P95 latency
    latencies_ms.sort()
    p95_latency_ms = latencies_ms[int(len(latencies_ms) * 0.95)]

    # Verify P95 <5ms
    assert (
        p95_latency_ms < 5.0
    ), f"P95 update latency {p95_latency_ms:.2f}ms exceeds 5ms budget"


@test("SessionStateControl multiple updates accumulate pending deltas")
async def _(control=started_control):
    """Verify multiple updates queue deltas"""
    # Make 5 updates
    for i in range(5):
        await control.update_state({f"beliefs.fact_{i}": f"value_{i}"})

    # Verify 5 pending deltas
    assert control.get_pending_delta_count() == 5


# ============================================================================
# Test Suite: Batching Behavior
# ============================================================================


@test("SessionStateControl flush_to_k0 sends deltas to batch client")
async def _(control=started_control, mock_batch_client=mock_batch_client):
    """Verify flush sends deltas to K0 batch client"""
    # Queue some deltas
    await control.update_state({"beliefs.fact_0": "value_0"})
    await control.update_state({"control.current_flow": "flow_abc"})

    # Flush to K0
    receipt = await control.flush_to_k0()

    # Verify batch client was called
    assert mock_batch_client.add_delta.called
    assert receipt.success
    assert receipt.batch_size > 0


@test("SessionStateControl flush clears pending deltas")
async def _(control=started_control):
    """Verify flush empties pending delta queue"""
    # Queue deltas
    await control.update_state({"beliefs.fact_0": "value_0"})
    assert control.get_pending_delta_count() == 1

    # Flush
    await control.flush_to_k0()

    # Verify queue cleared
    assert control.get_pending_delta_count() == 0


@test("SessionStateControl flush with empty queue returns empty receipt")
async def _(control=started_control):
    """Verify flushing empty queue is safe"""
    receipt = await control.flush_to_k0()

    assert receipt.success
    assert receipt.batch_size == 0
    assert receipt.receipt_id == "empty"


@test("SessionStateControl auto-flush triggers at max_pending_deltas")
async def _(control=started_control):
    """Verify flush triggers when delta count reaches limit"""
    # Set max to 3 for testing
    control.max_pending_deltas = 3

    # Queue 2 deltas (below threshold)
    await control.update_state({"beliefs.fact_0": "value_0"})
    await control.update_state({"beliefs.fact_1": "value_1"})
    assert control.get_pending_delta_count() == 2

    # Queue 3rd delta (triggers flush)
    await control.update_state({"beliefs.fact_2": "value_2"})

    # Verify flush triggered (queue cleared)
    assert control.get_pending_delta_count() == 0


@test("SessionStateControl periodic flush works (250ms interval)")
async def _(mock_batch_client=mock_batch_client):
    """Verify periodic flush task flushes at intervals"""
    control = SessionStateControl(
        session_id="test_periodic_flush",
        batch_client=mock_batch_client,
        flush_interval_ms=100,  # 100ms for fast test
        enable_auto_flush=True,
    )

    await control.start()

    try:
        # Queue a delta
        await control.update_state({"beliefs.fact_0": "value_0"})
        assert control.get_pending_delta_count() == 1

        # Wait for flush interval (100ms + buffer)
        await asyncio.sleep(0.15)

        # Verify flush triggered
        assert control.get_pending_delta_count() == 0

    finally:
        await control.stop(flush_pending=False)


# ============================================================================
# Test Suite: K0 Integration
# ============================================================================


@test("SessionStateControl flush_to_k0 latency is acceptable (<100ms P95)")
async def _(control=started_control):
    """Verify flush meets performance budget"""
    latencies_ms: List[float] = []

    # Sample 20 flush operations
    for i in range(20):
        await control.update_state({f"beliefs.fact_{i}": f"value_{i}"})

        start_time = time.perf_counter()
        await control.flush_to_k0()
        latency_ms = (time.perf_counter() - start_time) * 1000
        latencies_ms.append(latency_ms)

    # Compute P95 latency
    latencies_ms.sort()
    p95_latency_ms = latencies_ms[int(len(latencies_ms) * 0.95)]

    # Verify P95 <100ms
    assert (
        p95_latency_ms < 100.0
    ), f"P95 flush latency {p95_latency_ms:.2f}ms exceeds 100ms budget"


@test("SessionStateControl flush error handling returns error receipt")
async def _(mock_batch_client=mock_batch_client):
    """Verify flush handles K0 errors gracefully"""
    # Configure mock to raise exception
    mock_batch_client.add_delta = AsyncMock(
        side_effect=Exception("K0 connection error")
    )

    control = SessionStateControl(
        session_id="test_error_handling",
        batch_client=mock_batch_client,
        enable_auto_flush=False,
    )
    await control.start()

    try:
        # Queue delta
        await control.update_state({"beliefs.fact_0": "value_0"})

        # Flush (should handle error)
        receipt = await control.flush_to_k0()

        # Verify error receipt
        assert not receipt.success
        assert receipt.error is not None
        assert "K0 connection error" in receipt.error

    finally:
        await control.stop(flush_pending=False)


# ============================================================================
# Test Suite: Utility Methods
# ============================================================================


@test("SessionStateControl get_pending_delta_count returns correct count")
async def _(control=started_control):
    """Verify delta count tracking"""
    assert control.get_pending_delta_count() == 0

    await control.update_state({"beliefs.fact_0": "value_0"})
    assert control.get_pending_delta_count() == 1

    await control.update_state({"control.current_flow": "flow_abc"})
    assert control.get_pending_delta_count() == 2


@test("SessionStateControl get_time_since_last_flush_ms tracks time")
async def _(control=started_control):
    """Verify time tracking since last flush"""
    # Initial time should be small (just initialized)
    time_since_flush = control.get_time_since_last_flush_ms()
    assert time_since_flush < 100  # <100ms since init

    # Wait and check again
    await asyncio.sleep(0.05)  # 50ms
    time_since_flush = control.get_time_since_last_flush_ms()
    assert time_since_flush >= 50  # At least 50ms elapsed


@test("SessionStateControl is_flush_needed detects flush triggers")
async def _(control=started_control):
    """Verify flush detection logic"""
    # Initially not needed
    assert not control.is_flush_needed()

    # Queue deltas (not enough to trigger)
    control.max_pending_deltas = 10
    await control.update_state({"beliefs.fact_0": "value_0"})
    assert not control.is_flush_needed()  # Only 1 delta

    # Queue more deltas (just under limit to avoid auto-flush)
    for i in range(1, 9):  # Queue 8 more (total 9 < 10)
        await control.update_state({f"beliefs.fact_{i}": f"value_{i}"})
    # Should have 9 pending (not auto-flushed yet)
    assert control.get_pending_delta_count() == 9
    assert not control.is_flush_needed()  # 9 < 10, so False (correct behavior)


@test("SessionStateControl force_flush bypasses triggers")
async def _(control=started_control):
    """Verify force_flush works immediately"""
    # Queue 1 delta (below threshold)
    await control.update_state({"beliefs.fact_0": "value_0"})
    assert control.get_pending_delta_count() == 1

    # Force flush
    receipt = await control.force_flush()

    # Verify flush succeeded
    assert receipt.success
    assert control.get_pending_delta_count() == 0


# ============================================================================
# Test Suite: Concurrency & Race Conditions
# ============================================================================


@test("SessionStateControl concurrent reads during write don't corrupt state")
async def _(control=started_control):
    """Verify read safety during concurrent write"""

    async def writer():
        """Writer task: Update state continuously"""
        for i in range(50):
            await control.update_state({f"beliefs.fact_{i}": f"value_{i}"})
            await asyncio.sleep(0.001)  # 1ms between writes

    async def reader():
        """Reader task: Read state continuously"""
        states = []
        for _ in range(100):
            state = await control.read_state()
            states.append(state)
            await asyncio.sleep(0.0005)  # 0.5ms between reads
        return states

    # Run writer and readers concurrently
    writer_task = asyncio.create_task(writer())
    reader_tasks = [asyncio.create_task(reader()) for _ in range(5)]

    # Wait for completion
    await writer_task
    reader_results = await asyncio.gather(*reader_tasks)

    # Verify all reads succeeded (no exceptions)
    assert len(reader_results) == 5
    for states in reader_results:
        assert len(states) == 100
        assert all(isinstance(s, SessionStateWrapper) for s in states)


@test("SessionStateControl multiple concurrent updates serialize correctly")
async def _(control=started_control):
    """Verify write serialization (no race conditions)"""

    async def updater(id_prefix: str, count: int):
        """Update task: Make multiple updates"""
        for i in range(count):
            await control.update_state({f"beliefs.{id_prefix}_{i}": f"value_{i}"})

    # Launch 10 concurrent updaters (9 updates each = 90 total, under 100 limit)
    tasks = [asyncio.create_task(updater(f"task_{i}", 9)) for i in range(10)]
    await asyncio.gather(*tasks)

    # Verify all deltas queued (90 total, no auto-flush triggered)
    assert control.get_pending_delta_count() == 90
    assert control.get_pending_delta_count() < control.max_pending_deltas


# ============================================================================
# Test Suite: Metrics Emission (Prometheus)
# ============================================================================


@test("SessionStateControl emits lock acquisition metrics")
async def _(control=started_control):
    """Verify lock metrics are emitted"""
    with patch(
        "k1.l4_runtime.session_state.control.control.session_state_lock_acquire_ms"
    ) as mock_metric:
        # Perform read operation
        await control.read_state()

        # Verify metric observed
        assert mock_metric.labels.called
        assert mock_metric.labels.return_value.observe.called


@test("SessionStateControl emits delta merge metrics")
async def _(control=started_control):
    """Verify delta computation metrics are emitted"""
    with patch(
        "k1.l4_runtime.session_state.control.control.session_state_delta_merge_ms"
    ) as mock_metric:
        # Perform update operation
        await control.update_state({"beliefs.fact_0": "value_0"})

        # Verify metric observed
        assert mock_metric.labels.called
        assert mock_metric.labels.return_value.observe.called


@test("SessionStateControl emits flush metrics")
async def _(control=started_control):
    """Verify flush metrics are emitted"""
    with patch(
        "k1.l4_runtime.session_state.control.control.session_state_flush_latency_ms"
    ) as mock_flush_metric, patch(
        "k1.l4_runtime.session_state.control.control.session_state_flush_batch_size"
    ) as mock_batch_metric:
        # Queue delta and flush
        await control.update_state({"beliefs.fact_0": "value_0"})
        await control.flush_to_k0()

        # Verify metrics observed
        assert mock_flush_metric.labels.called
        assert mock_batch_metric.labels.called


# ============================================================================
# Test Suite: Performance Budget Validation
# ============================================================================


@test("SessionStateControl meets all performance budgets under load")
async def _(mock_batch_client=mock_batch_client):
    """Comprehensive performance test: 1000 operations"""
    control = SessionStateControl(
        session_id="perf_test",
        batch_client=mock_batch_client,
        flush_interval_ms=250,
        max_pending_deltas=100,
        enable_auto_flush=False,
    )
    await control.start()

    try:
        read_latencies_ms = []
        write_latencies_ms = []
        flush_latencies_ms = []

        # Perform 1000 mixed operations
        for i in range(1000):
            # Read operation
            start_time = time.perf_counter()
            await control.read_state()
            read_latencies_ms.append((time.perf_counter() - start_time) * 1000)

            # Write operation
            start_time = time.perf_counter()
            await control.update_state({f"beliefs.fact_{i}": f"value_{i}"})
            write_latencies_ms.append((time.perf_counter() - start_time) * 1000)

            # Flush every 100 writes
            if (i + 1) % 100 == 0:
                start_time = time.perf_counter()
                await control.flush_to_k0()
                flush_latencies_ms.append((time.perf_counter() - start_time) * 1000)

        # Compute P95 latencies
        read_latencies_ms.sort()
        write_latencies_ms.sort()
        flush_latencies_ms.sort()

        p95_read = read_latencies_ms[int(len(read_latencies_ms) * 0.95)]
        p95_write = write_latencies_ms[int(len(write_latencies_ms) * 0.95)]
        p95_flush = flush_latencies_ms[int(len(flush_latencies_ms) * 0.95)]

        # Verify performance budgets
        assert p95_read < 0.1, f"P95 read {p95_read:.4f}ms exceeds 0.1ms budget"
        assert p95_write < 5.0, f"P95 write {p95_write:.2f}ms exceeds 5ms budget"
        assert p95_flush < 100.0, f"P95 flush {p95_flush:.2f}ms exceeds 100ms budget"

    finally:
        await control.stop(flush_pending=False)


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    # Run with: python -m ward test --path tests/k1/l4_runtime/session_state/control/
    import sys

    sys.exit(0)
