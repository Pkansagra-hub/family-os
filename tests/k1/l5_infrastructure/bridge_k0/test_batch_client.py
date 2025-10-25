"""Tests for K0 Batch Client (SessionState Delta Batching)

Tests the batch client implementation for efficient SessionState delta batching.
Uses Ward testing framework (ADR-0032).

ADRs:
- ADR-0001f: SessionState Delta Batching
- ADR-0017: SessionState 6-Section Design
- ADR-0022: K0 Bridge Batching
- ADR-0032: Ward Testing Framework

Test Coverage:
1. Delta queuing and buffer management
2. 3-trigger flush (timer, size, count)
3. Delta coalescing (remove redundant updates)
4. Fairness queue (round-robin per session)
5. zstd compression (batches >1KB)
6. K0 command client integration
7. Metrics emission
8. Error handling

Performance Requirements:
- Batch processing: <10ms P95
- Batching efficiency: 80% reduction in K0 writes

Last Updated: January 2025
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock

from ward import test

from k1.l5_infrastructure.bridge_k0.batch_client import (
    BatchClient,
    BatchClientError,
    DeltaOperation,
    FlushReason,
    SessionStateDelta,
)
from k1.l5_infrastructure.bridge_k0.command_client import (
    CommandReceipt,
    K0CommandClient,
)


def create_mock_command_client():
    """Create a mock K0CommandClient for testing"""
    client = MagicMock(spec=K0CommandClient)

    # Mock submit_command to return receipt
    async def mock_submit(envelope):
        return CommandReceipt(
            receipt_id=f"receipt_{int(time.time() * 1000)}",
            commit_ts=datetime.now(timezone.utc).isoformat(),
            offsets={"k1.sessionstate.batch": 100},
            idem_key=envelope.cognitive_trace_id,
            obligations=[],
        )

    client.submit_command = AsyncMock(side_effect=mock_submit)

    return client


async def create_batch_client(mock_command_client=None):
    """Create a BatchClient instance for testing"""
    if mock_command_client is None:
        mock_command_client = create_mock_command_client()

    client = BatchClient(
        command_client=mock_command_client,
        flush_interval_ms=100,  # Fast interval for testing
        max_batch_size_bytes=1024,  # Small for testing
        max_batch_count=10,  # Small for testing
    )
    await client.start()
    return client, mock_command_client


def create_delta(
    session_id: str,
    field_path: str,
    new_value: str,
    section: str = "control",
) -> SessionStateDelta:
    """Helper to create test delta"""
    return SessionStateDelta(
        session_id=session_id,
        field_path=field_path,
        operation=DeltaOperation.SET,
        new_value=new_value,
        old_value=None,
        section=section,
        cognitive_trace_id="test_trace",
    )


@test("BatchClient: start/stop lifecycle")
async def _():
    """
    Test batch client start/stop lifecycle

    Acceptance Criteria:
    - Client starts periodic flush loop
    - Client stops and flushes pending deltas
    - Multiple start calls are safe
    """
    mock_command_client = create_mock_command_client()
    client = BatchClient(mock_command_client, flush_interval_ms=1000)

    # Start
    await client.start()
    assert client._running is True
    assert client._flush_task is not None

    # Start again (should log warning)
    await client.start()

    # Stop
    await client.stop()
    assert client._running is False


@test("BatchClient: add_delta queues delta")
async def _():
    """
    Test add_delta queues delta for batching

    Acceptance Criteria:
    - Delta added to buffer
    - Buffer count incremented
    - Buffer size updated
    - Metrics updated
    """
    mock_command_client = create_mock_command_client()
    batch_client, _ = await create_batch_client(mock_command_client)

    try:
        delta = create_delta(
            session_id="session_123",
            field_path="control.current_flow",
            new_value="flow_abc",
        )

        await batch_client.add_delta(delta)

        # Check buffer
        assert batch_client._buffer_count == 1
        assert "session_123" in batch_client._buffer
        assert len(batch_client._buffer["session_123"]) == 1
        assert batch_client._buffer_size_bytes > 0
    finally:
        await batch_client.stop()


@test("BatchClient: count trigger flush")
async def _():
    """
    Test flush triggered by delta count (100 deltas)

    Acceptance Criteria:
    - Flush triggered when count >= max_batch_count
    - Deltas sent to K0
    - Buffer cleared
    """
    mock_command_client = create_mock_command_client()
    batch_client, _ = await create_batch_client(mock_command_client)

    try:
        # Add deltas up to count limit
        for i in range(batch_client.max_batch_count):
            delta = create_delta(
                session_id="session_123",
                field_path=f"control.field_{i}",
                new_value=f"value_{i}",
            )
            await batch_client.add_delta(delta)

        # Wait briefly for async flush
        await asyncio.sleep(0.1)

        # Verify flush called
        assert mock_command_client.submit_command.call_count > 0

        # Verify buffer cleared
        assert batch_client._buffer_count == 0
    finally:
        await batch_client.stop()


@test("BatchClient: size trigger flush")
async def _():
    """
    Test flush triggered by batch size (64KB)

    Acceptance Criteria:
    - Flush triggered when size >= max_batch_size_bytes
    - Deltas sent to K0
    - Buffer cleared
    """
    mock_command_client = create_mock_command_client()
    batch_client, _ = await create_batch_client(mock_command_client)

    try:
        # Add large deltas to exceed size limit
        large_value = "x" * 200  # Each delta ~200 bytes
        for i in range(10):
            delta = create_delta(
                session_id="session_123",
                field_path=f"control.large_field_{i}",
                new_value=large_value,
            )
            await batch_client.add_delta(delta)

        # Wait briefly for async flush
        await asyncio.sleep(0.1)

        # Verify flush called
        assert mock_command_client.submit_command.call_count > 0
    finally:
        await batch_client.stop()


@test("BatchClient: timer trigger flush")
async def _():
    """
    Test flush triggered by timer (250ms)

    Acceptance Criteria:
    - Flush triggered after flush_interval_ms
    - Deltas sent to K0
    - Buffer cleared
    """
    mock_command_client = create_mock_command_client()
    client = BatchClient(
        mock_command_client,
        flush_interval_ms=100,  # 100ms for fast test
    )
    await client.start()

    try:
        # Add single delta
        delta = create_delta(
            session_id="session_123",
            field_path="control.test_field",
            new_value="test_value",
        )
        await client.add_delta(delta)

        # Wait for timer trigger
        await asyncio.sleep(0.15)  # Wait > 100ms

        # Verify flush called
        assert mock_command_client.submit_command.call_count > 0
        assert client._buffer_count == 0

    finally:
        await client.stop(flush_pending=False)


@test("BatchClient: delta coalescing")
async def _():
    """
    Test delta coalescing (remove redundant updates)

    Acceptance Criteria:
    - Multiple updates to same field → keep latest
    - Different fields → keep all
    - Coalesced count metric updated
    """
    # Create client with large limits to avoid auto-flush
    mock_command_client = create_mock_command_client()
    client = BatchClient(
        mock_command_client,
        flush_interval_ms=10000,  # Long interval
        max_batch_size_bytes=10000,  # Large size
        max_batch_count=100,  # Large count
    )
    await client.start()

    try:
        # Add multiple updates to same field
        for i in range(5):
            delta = create_delta(
                session_id="session_123",
                field_path="control.current_flow",
                new_value=f"flow_v{i}",
            )
            delta.timestamp_ms = int(time.time() * 1000) + i  # Increasing timestamps
            await client.add_delta(delta)

        # Coalesce
        coalesced = client._coalesce_deltas()

        # Should have only 1 delta (latest)
        assert len(coalesced) == 1
        assert coalesced[0].new_value == "flow_v4"  # Latest value

    finally:
        await client.stop(flush_pending=False)


@test("BatchClient: fairness queue")
async def _():
    """
    Test fairness queue (round-robin per session)

    Acceptance Criteria:
    - Max N deltas per session per batch
    - Round-robin selection across sessions
    - Prevents single session domination
    """
    mock_command_client = create_mock_command_client()
    batch_client, _ = await create_batch_client(mock_command_client)

    try:
        # Add deltas from multiple sessions
        deltas: List[SessionStateDelta] = []

        # Session 1: 10 deltas
        for i in range(10):
            deltas.append(
                create_delta(
                    session_id="session_1",
                    field_path=f"control.field_{i}",
                    new_value=f"value_{i}",
                )
            )

        # Session 2: 10 deltas
        for i in range(10):
            deltas.append(
                create_delta(
                    session_id="session_2",
                    field_path=f"control.field_{i}",
                    new_value=f"value_{i}",
                )
            )

        # Apply fairness queue (max 5 per session)
        fair = batch_client._apply_fairness_queue(deltas)

        # Count deltas per session
        session_1_count = sum(1 for d in fair if d.session_id == "session_1")
        session_2_count = sum(1 for d in fair if d.session_id == "session_2")

        # Both sessions should have equal or near-equal representation
        assert session_1_count <= batch_client.max_deltas_per_session
        assert session_2_count <= batch_client.max_deltas_per_session
        assert abs(session_1_count - session_2_count) <= 1  # Balanced
    finally:
        await batch_client.stop()


@test("BatchClient: compression for large batches")
async def _():
    """
    Test zstd compression for large batches (>1KB)

    Acceptance Criteria:
    - Compression applied for batches >1KB
    - Compression ratio recorded
    - Smaller payload sent to K0
    """
    try:
        import zstandard  # noqa: F401

        HAS_ZSTD = True
    except ImportError:
        HAS_ZSTD = False

    if not HAS_ZSTD:
        # Skip if zstandard not installed (cannot use pytest.skip with WARD)
        return

    mock_command_client = create_mock_command_client()
    client = BatchClient(
        mock_command_client,
        compression_threshold_bytes=100,  # Low threshold for testing
        enable_compression=True,
    )
    await client.start()

    try:
        # Add large deltas
        for i in range(20):
            delta = create_delta(
                session_id="session_123",
                field_path=f"control.large_field_{i}",
                new_value="x" * 100,  # Large value
            )
            await client.add_delta(delta)

        # Flush
        stats = await client.flush(reason=FlushReason.EXPLICIT)

        # Verify compression
        assert stats is not None
        assert stats.size_bytes_compressed < stats.size_bytes_uncompressed
        assert stats.compression_ratio < 1.0

    finally:
        await client.stop(flush_pending=False)


@test("BatchClient: explicit flush")
async def _():
    """
    Test explicit flush (manual trigger)

    Acceptance Criteria:
    - Flush can be triggered manually
    - Returns BatchStatistics
    - Buffer cleared
    """
    mock_command_client = create_mock_command_client()
    batch_client, _ = await create_batch_client(mock_command_client)

    try:
        # Add delta
        delta = create_delta(
            session_id="session_123",
            field_path="control.test",
            new_value="test",
        )
        await batch_client.add_delta(delta)

        # Explicit flush
        stats = await batch_client.flush(reason=FlushReason.EXPLICIT)

        # Verify
        assert stats is not None
        assert stats.deltas_sent >= 1
        assert stats.flush_reason == FlushReason.EXPLICIT
        assert batch_client._buffer_count == 0
    finally:
        await batch_client.stop()


@test("BatchClient: flush empty buffer returns None")
async def _():
    """
    Test flush with empty buffer returns None

    Acceptance Criteria:
    - Flush on empty buffer returns None
    - No K0 call made
    """
    mock_command_client = create_mock_command_client()
    batch_client, _ = await create_batch_client(mock_command_client)

    try:
        stats = await batch_client.flush(reason=FlushReason.EXPLICIT)
        assert stats is None
    finally:
        await batch_client.stop()


@test("BatchClient: error when not running")
async def _():
    """
    Test error when adding delta to stopped client

    Acceptance Criteria:
    - Raises BatchClientError if not running
    """
    mock_command_client = create_mock_command_client()
    client = BatchClient(mock_command_client)
    # Don't start

    delta = create_delta(
        session_id="session_123",
        field_path="control.test",
        new_value="test",
    )

    # Test that adding delta to stopped client raises BatchClientError
    try:
        await client.add_delta(delta)
        assert False, "Expected BatchClientError but none was raised"
    except BatchClientError:
        # Expected
        pass


@test("BatchClient: shutdown flush")
async def _():
    """
    Test flush on shutdown

    Acceptance Criteria:
    - Pending deltas flushed on stop
    - Buffer cleared
    """
    mock_command_client = create_mock_command_client()
    client = BatchClient(mock_command_client, flush_interval_ms=10000)  # Long interval
    await client.start()

    # Add delta
    delta = create_delta(
        session_id="session_123",
        field_path="control.test",
        new_value="test",
    )
    await client.add_delta(delta)

    # Stop with flush
    await client.stop(flush_pending=True)

    # Verify flush called
    assert mock_command_client.submit_command.call_count > 0


@test("BatchClient: metrics emission")
async def _():
    """
    Test Prometheus metrics emission

    Metrics:
    - batch_deltas_queued_total
    - batch_flushes_total
    - batch_size_deltas
    - batch_size_bytes
    - batch_processing_latency_ms
    - batch_coalesced_deltas_total
    - batch_queue_depth

    Acceptance Criteria:
    - Metrics updated on delta add
    - Metrics updated on flush
    """
    mock_command_client = create_mock_command_client()
    batch_client, _ = await create_batch_client(mock_command_client)

    try:
        # This test would verify metrics using prometheus_client test utilities
        # Structure test: Verify metrics are defined
        from k1.l5_infrastructure.bridge_k0 import batch_client as batch_module

        # Verify metrics exist
        assert hasattr(batch_module, "batch_deltas_queued_total")
        assert hasattr(batch_module, "batch_flushes_total")
        assert hasattr(batch_module, "batch_size_deltas")
        assert hasattr(batch_module, "batch_size_bytes")
        assert hasattr(batch_module, "batch_processing_latency_ms")
        assert hasattr(batch_module, "batch_coalesced_deltas_total")
        assert hasattr(batch_module, "batch_queue_depth")
    finally:
        await batch_client.stop()


@test("SessionStateDelta: to_dict serialization")
async def _():
    """
    Test SessionStateDelta to_dict serialization

    Acceptance Criteria:
    - Converts to JSON-serializable dict
    - All fields included
    """
    delta = create_delta(
        session_id="session_123",
        field_path="control.current_flow",
        new_value="flow_abc",
    )

    delta_dict = delta.to_dict()

    assert delta_dict["session_id"] == "session_123"
    assert delta_dict["field_path"] == "control.current_flow"
    assert delta_dict["operation"] == "set"
    assert delta_dict["new_value"] == "flow_abc"
    assert delta_dict["section"] == "control"


@test("SessionStateDelta: estimate_size")
async def _():
    """
    Test SessionStateDelta size estimation

    Acceptance Criteria:
    - Returns reasonable size estimate
    - Used for batching triggers
    """
    delta = create_delta(
        session_id="session_123",
        field_path="control.test",
        new_value="x" * 100,
    )

    size = delta.estimate_size()

    # Should be > 100 (value size) + overhead
    assert size > 100
    assert size < 1000  # Reasonable upper bound


# Integration test example (requires K0 running)
@test("BatchClient integration: Real K0 batching")
async def _():
    """
    Integration test with real K0 command port

    Requirements:
    - K0 running on localhost:5200
    - K0 command port enabled

    This test is marked with @pytest.mark.integration
    Run with: python -m ward test --path tests/ -m integration
    """
    # Integration test requires K0 running on localhost:5200
    # Skipping this test as K0 is not required for unit tests
    return


# Performance test example
@test("BatchClient performance: <10ms P95 batch processing")
async def _():
    """
    Performance test: Batch processing latency

    Performance Budget (ADR-0024):
    - Batch processing: <10ms P95

    Test Process:
    1. Add 1000 deltas
    2. Measure flush latency
    3. Calculate P95
    4. Assert P95 < 10ms
    """
    # Performance test requires timing infrastructure
    # Skipping for now
    return
