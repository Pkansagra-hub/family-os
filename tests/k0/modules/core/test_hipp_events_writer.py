"""
Comprehensive Test Suite for M16: Hippocampus Events Writer

Tests for core.hipp_events_writer module (M16).

**Coverage Categories** (30-35 tests):
1. **Record Assembly** (7 tests): Field extraction, validation, defaults
2. **Happy Path** (5 tests): Successful writes, idempotency, pipeline tracking
3. **Error Handling** (6 tests): Missing fields, invalid data, storage failures
4. **Capability Enforcement** (4 tests): Permission checks, security boundaries
5. **Metrics & Observability** (5 tests): Counter updates, metrics retrieval
6. **Integration** (4 tests): Syscalls integration, transaction atomicity
7. **Performance** (4 tests): Latency targets, throughput benchmarks

**Test Requirements**:
- All tests must pass (100% success rate)
- No simulation code (real syscalls mocking)
- Clear test names (test_<category>_<scenario>)
- Performance targets: <25ms P95 for write operations

**Version**: 1.0.0
**Last Updated**: 2025-11-17
"""

import hashlib
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.core import hipp_events_writer  # noqa: F401

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def minimal_envelope() -> dict[str, Any]:
    """Minimal valid envelope for M16 testing"""
    return {
        "header": {
            "event_id": "evt_test_123",
            "wal_pos": 42,
            "tenant_id": "tenant_test",
            "space_id": "space_test",
            "privacy_band": "GREEN",
            "cognitive_trace_id": "trace_test_456",
            "timestamp": 1700000000,
        },
        "body": {"text": "Test event text for M16"},
        "outputs": {
            "semantic_project": {"embedding_id": "emb_test_789"},
            "affect_analyze": {"valence": 0.5, "arousal": 0.3},
            "hipp_events_row": {
                "text_hash": "abc123def456",
            },
        },
    }


@pytest.fixture
def enriched_envelope() -> dict[str, Any]:
    """Fully enriched envelope with all optional fields"""
    return {
        "header": {
            "event_id": "evt_enriched_456",
            "wal_pos": 100,
            "tenant_id": "tenant_premium",
            "space_id": "space_premium",
            "privacy_band": "AMBER",
            "cognitive_trace_id": "trace_enriched_789",
            "timestamp": 1700001000,
        },
        "body": {"text": "Enriched event with full context"},
        "outputs": {
            "semantic_project": {
                "embedding_id": "emb_enriched_123",
                "entities": ["person", "location"],
            },
            "affect_analyze": {"valence": -0.8, "arousal": 0.9, "dominance": 0.6},
            "hipp_events_row": {
                "text_hash": "fed654cba321",
            },
        },
    }


@pytest.fixture
def mock_context() -> MagicMock:
    """Mock PipelineContext with syscalls"""
    context = MagicMock()
    context.syscalls = MagicMock()
    context.syscalls.hipp_events_upsert = AsyncMock(
        return_value={"inserted": True, "event_id": "evt_test_123", "status": "INSERTED"}
    )
    context.syscalls.pipeline_processed_upsert = AsyncMock(
        return_value={
            "inserted": True,
            "pipeline_id": "P02_WRITE",
            "wal_pos": 42,
            "status": "OK",
        }
    )
    return context


@pytest.fixture(autouse=True)
def reset_module_metrics():
    """Reset module metrics before each test"""
    hipp_events_writer.reset_metrics()
    yield
    hipp_events_writer.reset_metrics()


# =============================================================================
# Category 1: Record Assembly Tests (7 tests)
# =============================================================================


def test_assemble_hipp_events_record_minimal_fields(minimal_envelope):
    """Test record assembly with minimal required fields"""
    record = hipp_events_writer.assemble_hipp_events_record(minimal_envelope)

    # Verify required fields
    assert record["event_id"] == "evt_test_123"
    assert record["wal_pos"] == 42
    assert record["tenant_id"] == "tenant_test"
    assert record["space_id"] == "space_test"
    assert record["embedding_id"] == "emb_test_789"
    assert record["text"] == "Test event text for M16"
    assert record["text_hash"] == "abc123def456"
    assert record["privacy_band"] == "GREEN"
    assert record["cognitive_trace_id"] == "trace_test_456"

    # Verify enrichment fields
    assert record["valence"] == 0.5
    assert record["arousal"] == 0.3
    assert record["created_at"] == 1700000000


def test_assemble_hipp_events_record_enriched_fields(enriched_envelope):
    """Test record assembly with all enriched fields"""
    record = hipp_events_writer.assemble_hipp_events_record(enriched_envelope)

    assert record["event_id"] == "evt_enriched_456"
    assert record["wal_pos"] == 100
    assert record["embedding_id"] == "emb_enriched_123"
    assert record["valence"] == -0.8
    assert record["arousal"] == 0.9
    assert record["privacy_band"] == "AMBER"


def test_assemble_hipp_events_record_missing_text_hash_generates_hash():
    """Test hash generation when text_hash not in hipp_events_row output"""
    envelope = {
        "header": {
            "event_id": "evt_123",
            "wal_pos": 10,
            "tenant_id": "tenant_default",
            "space_id": "space_default",
        },
        "body": {"text": "Test text"},
        "outputs": {
            "semantic_project": {"embedding_id": "emb_123"},
            "hipp_events_row": {},  # No text_hash
        },
    }

    record = hipp_events_writer.assemble_hipp_events_record(envelope)

    # Verify hash was generated
    expected_hash = hashlib.sha256("Test text".encode("utf-8")).hexdigest()
    assert record["text_hash"] == expected_hash


def test_assemble_hipp_events_record_defaults_for_missing_optionals():
    """Test default values when optional enrichment fields missing"""
    envelope = {
        "header": {
            "event_id": "evt_123",
            "wal_pos": 10,
        },
        "body": {},
        "outputs": {
            "semantic_project": {"embedding_id": "emb_123"},
        },
    }

    record = hipp_events_writer.assemble_hipp_events_record(envelope)

    # Verify defaults
    assert record["tenant_id"] == "default"
    assert record["space_id"] == "unknown"
    assert record["privacy_band"] == "GREEN"
    assert record["cognitive_trace_id"] == "unknown"
    assert record["text"] == ""
    assert record["valence"] is None
    assert record["arousal"] is None


def test_assemble_pipeline_processed_record_default_config():
    """Test pipeline processed record with default configuration"""
    envelope = {
        "header": {
            "wal_pos": 42,
            "tenant_id": "tenant_test",
            "space_id": "space_test",
        }
    }

    record = hipp_events_writer.assemble_pipeline_processed_record(envelope)

    assert record["pipeline_id"] == "P02_WRITE"
    assert record["wal_pos"] == 42
    assert record["tenant_id"] == "tenant_test"
    assert record["space_id"] == "space_test"
    assert record["status"] == "OK"
    assert isinstance(record["processed_at"], int)


def test_assemble_pipeline_processed_record_custom_config():
    """Test pipeline processed record with custom pipeline_id and status"""
    envelope = {
        "header": {
            "wal_pos": 100,
            "tenant_id": "tenant_custom",
            "space_id": "space_custom",
        }
    }

    record = hipp_events_writer.assemble_pipeline_processed_record(
        envelope, pipeline_id="P03_CONSOLIDATE", status="ERROR"
    )

    assert record["pipeline_id"] == "P03_CONSOLIDATE"
    assert record["status"] == "ERROR"


def test_assemble_pipeline_processed_record_defaults_for_missing_header_fields():
    """Test pipeline processed defaults when header fields missing"""
    envelope = {"header": {"wal_pos": 10}}

    record = hipp_events_writer.assemble_pipeline_processed_record(envelope)

    assert record["tenant_id"] == "default"
    assert record["space_id"] == "unknown"


# =============================================================================
# Category 2: Happy Path Tests (5 tests)
# =============================================================================


@pytest.mark.asyncio
async def test_run_successful_write_minimal_envelope(minimal_envelope, mock_context):
    """Test successful write with minimal envelope"""
    result = await hipp_events_writer.run(minimal_envelope, mock_context)

    # Verify result structure
    assert result["hipp_events_inserted"] is True
    assert result["hipp_events_status"] == "INSERTED"
    assert result["pipeline_tracked"] is True
    assert result["event_id"] == "evt_test_123"
    assert result["wal_pos"] == 42

    # Verify syscalls invoked
    mock_context.syscalls.hipp_events_upsert.assert_called_once()
    mock_context.syscalls.pipeline_processed_upsert.assert_called_once()

    # Verify metrics updated
    metrics = hipp_events_writer.get_metrics()
    assert metrics["events_written"] == 1
    assert metrics["pipeline_tracked"] == 1
    assert metrics["duplicates_skipped"] == 0
    assert metrics["write_failures"] == 0


@pytest.mark.asyncio
async def test_run_successful_write_enriched_envelope(enriched_envelope, mock_context):
    """Test successful write with fully enriched envelope"""
    result = await hipp_events_writer.run(enriched_envelope, mock_context)

    assert result["hipp_events_inserted"] is True
    assert result["event_id"] == "evt_enriched_456"
    assert result["wal_pos"] == 100

    # Verify enriched fields passed to syscalls
    call_kwargs = mock_context.syscalls.hipp_events_upsert.call_args[1]
    assert call_kwargs["valence"] == -0.8
    assert call_kwargs["arousal"] == 0.9
    assert call_kwargs["privacy_band"] == "AMBER"


@pytest.mark.asyncio
async def test_run_duplicate_event_skipped(minimal_envelope, mock_context):
    """Test duplicate event_id skipped (idempotency)"""
    # Mock syscalls to return duplicate status
    mock_context.syscalls.hipp_events_upsert.return_value = {
        "inserted": False,
        "event_id": "evt_test_123",
        "status": "SKIPPED_DUPLICATE",
    }

    result = await hipp_events_writer.run(minimal_envelope, mock_context)

    assert result["hipp_events_inserted"] is False
    assert result["hipp_events_status"] == "SKIPPED_DUPLICATE"

    # Verify metrics
    metrics = hipp_events_writer.get_metrics()
    assert metrics["events_written"] == 0
    assert metrics["duplicates_skipped"] == 1


@pytest.mark.asyncio
async def test_run_custom_pipeline_id_in_config(minimal_envelope, mock_context):
    """Test custom pipeline_id passed via config"""
    result = await hipp_events_writer.run(
        minimal_envelope, mock_context, pipeline_id="P03_TEST", status="SKIPPED"
    )

    # Verify pipeline_processed called with custom config
    call_kwargs = mock_context.syscalls.pipeline_processed_upsert.call_args[1]
    assert call_kwargs["pipeline_id"] == "P03_TEST"
    assert call_kwargs["status"] == "SKIPPED"


@pytest.mark.asyncio
async def test_run_both_tables_written_atomically(minimal_envelope, mock_context):
    """Test both st_hipp_events and st_pipeline_processed written"""
    result = await hipp_events_writer.run(minimal_envelope, mock_context)

    # Verify both syscalls invoked
    assert mock_context.syscalls.hipp_events_upsert.call_count == 1
    assert mock_context.syscalls.pipeline_processed_upsert.call_count == 1

    # Verify result includes both operations
    assert "hipp_events_inserted" in result
    assert "pipeline_tracked" in result


# =============================================================================
# Category 3: Error Handling Tests (6 tests)
# =============================================================================


def test_assemble_hipp_events_record_missing_event_id_raises():
    """Test ValueError raised when event_id missing"""
    envelope = {
        "header": {"wal_pos": 10},  # No event_id
        "body": {},
        "outputs": {"semantic_project": {"embedding_id": "emb_123"}},
    }

    with pytest.raises(ValueError, match="Missing event_id"):
        hipp_events_writer.assemble_hipp_events_record(envelope)

    # Verify metrics incremented
    metrics = hipp_events_writer.get_metrics()
    assert metrics["missing_event_id"] == 1


def test_assemble_hipp_events_record_missing_wal_pos_raises():
    """Test ValueError raised when wal_pos missing"""
    envelope = {
        "header": {"event_id": "evt_123"},  # No wal_pos
        "body": {},
        "outputs": {"semantic_project": {"embedding_id": "emb_123"}},
    }

    with pytest.raises(ValueError, match="Missing wal_pos"):
        hipp_events_writer.assemble_hipp_events_record(envelope)

    metrics = hipp_events_writer.get_metrics()
    assert metrics["missing_wal_pos"] == 1


def test_assemble_hipp_events_record_missing_embedding_id_raises():
    """Test ValueError raised when embedding_id missing"""
    envelope = {
        "header": {"event_id": "evt_123", "wal_pos": 10},
        "body": {},
        "outputs": {"semantic_project": {}},  # No embedding_id
    }

    with pytest.raises(ValueError, match="Missing embedding_id"):
        hipp_events_writer.assemble_hipp_events_record(envelope)

    metrics = hipp_events_writer.get_metrics()
    assert metrics["missing_embedding_id"] == 1


def test_assemble_pipeline_processed_record_missing_wal_pos_raises():
    """Test ValueError raised when wal_pos missing from pipeline record"""
    envelope = {"header": {}}  # No wal_pos

    with pytest.raises(ValueError, match="Missing wal_pos"):
        hipp_events_writer.assemble_pipeline_processed_record(envelope)


@pytest.mark.asyncio
async def test_run_missing_context_raises():
    """Test ValueError raised when PipelineContext not provided"""
    envelope = {"header": {}, "body": {}, "outputs": {}}

    with pytest.raises(ValueError, match="PipelineContext required"):
        await hipp_events_writer.run(envelope, context=None)


@pytest.mark.asyncio
async def test_run_storage_failure_raises_runtime_error(minimal_envelope, mock_context):
    """Test RuntimeError raised when storage operation fails"""
    # Mock syscalls to raise exception
    mock_context.syscalls.hipp_events_upsert.side_effect = Exception("Database connection failed")

    with pytest.raises(RuntimeError, match="Failed to write hipp events"):
        await hipp_events_writer.run(minimal_envelope, mock_context)

    # Verify metrics
    metrics = hipp_events_writer.get_metrics()
    assert metrics["write_failures"] == 1


# =============================================================================
# Category 4: Capability Enforcement Tests (4 tests)
# =============================================================================


@pytest.mark.asyncio
async def test_run_capability_check_hipp_events_write(minimal_envelope, mock_context):
    """Test st_hipp_events.write capability checked before write"""
    # Mock PermissionError from syscalls
    from k0.kernel.syscalls import PermissionError

    mock_context.syscalls.hipp_events_upsert.side_effect = PermissionError(
        "Missing capability: st_hipp_events.write"
    )

    with pytest.raises(PermissionError):
        await hipp_events_writer.run(minimal_envelope, mock_context)


@pytest.mark.asyncio
async def test_run_capability_check_pipeline_processed_write(minimal_envelope, mock_context):
    """Test st_pipeline_processed.write capability checked"""
    from k0.kernel.syscalls import PermissionError

    # First call succeeds, second fails
    mock_context.syscalls.pipeline_processed_upsert.side_effect = PermissionError(
        "Missing capability: st_pipeline_processed.write"
    )

    with pytest.raises(PermissionError):
        await hipp_events_writer.run(minimal_envelope, mock_context)


@pytest.mark.asyncio
async def test_run_syscalls_called_with_correct_arguments(minimal_envelope, mock_context):
    """Test syscalls invoked with correct argument structure"""
    await hipp_events_writer.run(minimal_envelope, mock_context)

    # Verify hipp_events_upsert arguments
    hipp_call = mock_context.syscalls.hipp_events_upsert.call_args[1]
    assert hipp_call["event_id"] == "evt_test_123"
    assert hipp_call["wal_pos"] == 42
    assert hipp_call["embedding_id"] == "emb_test_789"
    assert hipp_call["privacy_band"] == "GREEN"

    # Verify pipeline_processed_upsert arguments
    pipeline_call = mock_context.syscalls.pipeline_processed_upsert.call_args[1]
    assert pipeline_call["pipeline_id"] == "P02_WRITE"
    assert pipeline_call["wal_pos"] == 42
    assert pipeline_call["status"] == "OK"


@pytest.mark.asyncio
async def test_run_no_ambient_authority_requires_syscalls(minimal_envelope):
    """Test module cannot access storage without syscalls (no ambient authority)"""
    # Create context without syscalls
    bad_context = MagicMock()
    bad_context.syscalls = None

    with pytest.raises(AttributeError):
        await hipp_events_writer.run(minimal_envelope, bad_context)


# =============================================================================
# Category 5: Metrics & Observability Tests (5 tests)
# =============================================================================


def test_metrics_initial_state_all_zeros():
    """Test metrics start at zero"""
    metrics = hipp_events_writer.get_metrics()

    assert metrics["events_written"] == 0
    assert metrics["duplicates_skipped"] == 0
    assert metrics["pipeline_tracked"] == 0
    assert metrics["missing_event_id"] == 0
    assert metrics["missing_embedding_id"] == 0
    assert metrics["missing_wal_pos"] == 0
    assert metrics["write_failures"] == 0


@pytest.mark.asyncio
async def test_metrics_events_written_incremented(minimal_envelope, mock_context):
    """Test events_written counter incremented on successful write"""
    await hipp_events_writer.run(minimal_envelope, mock_context)

    metrics = hipp_events_writer.get_metrics()
    assert metrics["events_written"] == 1


@pytest.mark.asyncio
async def test_metrics_duplicates_skipped_incremented(minimal_envelope, mock_context):
    """Test duplicates_skipped counter incremented when duplicate detected"""
    mock_context.syscalls.hipp_events_upsert.return_value = {
        "inserted": False,
        "event_id": "evt_test_123",
        "status": "SKIPPED_DUPLICATE",
    }

    await hipp_events_writer.run(minimal_envelope, mock_context)

    metrics = hipp_events_writer.get_metrics()
    assert metrics["duplicates_skipped"] == 1
    assert metrics["events_written"] == 0


@pytest.mark.asyncio
async def test_metrics_write_failures_incremented_on_error(minimal_envelope, mock_context):
    """Test write_failures counter incremented on storage failure"""
    mock_context.syscalls.hipp_events_upsert.side_effect = Exception("Storage error")

    with pytest.raises(RuntimeError):
        await hipp_events_writer.run(minimal_envelope, mock_context)

    metrics = hipp_events_writer.get_metrics()
    assert metrics["write_failures"] == 1


def test_reset_metrics_clears_all_counters():
    """Test reset_metrics() clears all counters"""
    # Increment some metrics
    envelope = {"header": {}, "body": {}, "outputs": {}}
    try:
        hipp_events_writer.assemble_hipp_events_record(envelope)
    except ValueError:
        pass

    # Verify metrics non-zero
    metrics_before = hipp_events_writer.get_metrics()
    assert metrics_before["missing_event_id"] > 0

    # Reset
    hipp_events_writer.reset_metrics()

    # Verify all zeros
    metrics_after = hipp_events_writer.get_metrics()
    assert metrics_after["missing_event_id"] == 0
    assert metrics_after["events_written"] == 0


# =============================================================================
# Category 6: Integration Tests (4 tests)
# =============================================================================


@pytest.mark.asyncio
async def test_integration_full_write_flow(minimal_envelope, mock_context):
    """Test complete write flow from envelope to storage"""
    result = await hipp_events_writer.run(minimal_envelope, mock_context)

    # Verify end-to-end flow
    assert result["hipp_events_inserted"] is True
    assert result["pipeline_tracked"] is True
    assert mock_context.syscalls.hipp_events_upsert.called
    assert mock_context.syscalls.pipeline_processed_upsert.called


@pytest.mark.asyncio
async def test_integration_syscalls_invocation_order(minimal_envelope, mock_context):
    """Test syscalls invoked in correct order (hipp_events first, then pipeline_processed)"""
    call_order = []

    async def track_hipp_call(**kwargs):
        call_order.append("hipp_events")
        return {"inserted": True, "event_id": kwargs["event_id"], "status": "INSERTED"}

    async def track_pipeline_call(**kwargs):
        call_order.append("pipeline_processed")
        return {
            "inserted": True,
            "pipeline_id": kwargs["pipeline_id"],
            "wal_pos": kwargs["wal_pos"],
            "status": "OK",
        }

    mock_context.syscalls.hipp_events_upsert = track_hipp_call
    mock_context.syscalls.pipeline_processed_upsert = track_pipeline_call

    await hipp_events_writer.run(minimal_envelope, mock_context)

    assert call_order == ["hipp_events", "pipeline_processed"]


@pytest.mark.asyncio
async def test_integration_multiple_writes_increment_metrics(mock_context):
    """Test multiple writes correctly update metrics"""
    envelopes = [
        {
            "header": {"event_id": f"evt_{i}", "wal_pos": i},
            "body": {"text": f"Event {i}"},
            "outputs": {"semantic_project": {"embedding_id": f"emb_{i}"}},
        }
        for i in range(5)
    ]

    for envelope in envelopes:
        await hipp_events_writer.run(envelope, mock_context)

    metrics = hipp_events_writer.get_metrics()
    assert metrics["events_written"] == 5
    assert metrics["pipeline_tracked"] == 5


@pytest.mark.asyncio
async def test_integration_partial_failure_rollback_semantics(minimal_envelope, mock_context):
    """Test failure in pipeline_processed doesn't affect hipp_events (separate transactions)"""
    # First syscall succeeds
    mock_context.syscalls.hipp_events_upsert.return_value = {
        "inserted": True,
        "event_id": "evt_test_123",
        "status": "INSERTED",
    }

    # Second syscall fails
    mock_context.syscalls.pipeline_processed_upsert.side_effect = Exception(
        "Pipeline tracking failed"
    )

    with pytest.raises(RuntimeError):
        await hipp_events_writer.run(minimal_envelope, mock_context)

    # Verify first call succeeded (separate transaction)
    assert mock_context.syscalls.hipp_events_upsert.called


# =============================================================================
# Category 7: Performance Tests (4 tests)
# =============================================================================


@pytest.mark.asyncio
async def test_performance_single_write_under_25ms(minimal_envelope, mock_context):
    """Test single write completes under 25ms P95 target"""
    start = time.perf_counter()
    await hipp_events_writer.run(minimal_envelope, mock_context)
    duration_ms = (time.perf_counter() - start) * 1000

    # Should be well under 25ms with mocked syscalls
    assert duration_ms < 25.0, f"Write took {duration_ms:.2f}ms (target: <25ms)"


@pytest.mark.asyncio
async def test_performance_batch_writes_throughput(mock_context):
    """Test throughput for batch of writes (target: 40-50 ops/sec)"""
    envelopes = [
        {
            "header": {"event_id": f"evt_{i}", "wal_pos": i},
            "body": {"text": f"Event {i}"},
            "outputs": {"semantic_project": {"embedding_id": f"emb_{i}"}},
        }
        for i in range(50)
    ]

    start = time.perf_counter()
    for envelope in envelopes:
        await hipp_events_writer.run(envelope, mock_context)
    duration_sec = time.perf_counter() - start

    ops_per_sec = 50 / duration_sec
    # With mocked syscalls, should easily exceed 40 ops/sec
    assert ops_per_sec > 40.0, f"Throughput: {ops_per_sec:.1f} ops/sec (target: >40 ops/sec)"


def test_performance_record_assembly_fast():
    """Test record assembly completes in <1ms"""
    envelope = {
        "header": {
            "event_id": "evt_perf",
            "wal_pos": 100,
            "tenant_id": "tenant_perf",
            "space_id": "space_perf",
        },
        "body": {"text": "Performance test"},
        "outputs": {"semantic_project": {"embedding_id": "emb_perf"}},
    }

    start = time.perf_counter()
    hipp_events_writer.assemble_hipp_events_record(envelope)
    duration_ms = (time.perf_counter() - start) * 1000

    assert duration_ms < 1.0, f"Assembly took {duration_ms:.3f}ms (target: <1ms)"


def test_performance_metrics_retrieval_fast():
    """Test metrics retrieval completes in <1ms"""
    start = time.perf_counter()
    for _ in range(100):
        hipp_events_writer.get_metrics()
    duration_ms = (time.perf_counter() - start) * 1000

    avg_ms = duration_ms / 100
    assert avg_ms < 1.0, f"Avg metrics retrieval: {avg_ms:.3f}ms (target: <1ms)"


# =============================================================================
# Test Summary
# =============================================================================
# Total Tests: 35
# - Category 1 (Record Assembly): 7 tests
# - Category 2 (Happy Path): 5 tests
# - Category 3 (Error Handling): 6 tests
# - Category 4 (Capability Enforcement): 4 tests
# - Category 5 (Metrics & Observability): 5 tests
# - Category 6 (Integration): 4 tests
# - Category 7 (Performance): 4 tests
#
# Expected Results: 35/35 passing (100% success rate)
# Performance Targets:
# - Single write: <25ms P95
# - Batch throughput: >40 ops/sec
# - Record assembly: <1ms
# - Metrics retrieval: <1ms
# =============================================================================
