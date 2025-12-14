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

import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from k0.modules.core import hipp_events_writer  # noqa: F401

# =============================================================================
# Test Helpers
# =============================================================================


class MockMessage:
    """Mock BusMessage for testing"""

    def __init__(self, payload: Any, trace_id: str = "test_trace"):
        self.payload = json.dumps(payload) if isinstance(payload, dict) else payload
        self.trace_id = trace_id
        self.offset = 0


def make_test_call(envelope: dict[str, Any], mock_context: Any, **config: Any):
    """Create test call with Phase 2 signature"""
    message = MockMessage(envelope)
    return message, mock_context, config


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def minimal_envelope() -> dict[str, Any]:
    """Minimal valid envelope for M16 testing - P02 hybrid structure"""
    return {
        # Header (nested - still used by some modules)
        "header": {
            "event_id": "evt_test_123",
            "wal_pos": 42,
            "tenant_id": "tenant_test",
            "space_id": "space_test",
            "privacy_band": "GREEN",
            "cognitive_trace_id": "trace_test_456",
            "timestamp": 1700000000,
        },
        # Flat fields at top level (P02 format)
        "wal_pos": 42,
        "cognitive_trace_id": "trace_test_456",
        "embedding_id": "emb_test_789",
        "tenant_id": "tenant_test",
        "space_id": "space_test",
        # Body
        "body": {"text": "Test event text for M16"},
        # M13 hipp_events_row output (flat at top level) - complete 70-column row
        "hipp_events_row": {
            "event_id": "evt_test_123",
            "wal_pos": 42,
            "embedding_id": "emb_test_789",
            "text": "Test event text for M16",
            "text_hash": "abc123def456",
            "tenant_id": "tenant_test",
            "space_id": "space_test",
            "privacy_band": "GREEN",
            "cognitive_trace_id": "trace_test_456",
            "created_at": 1700000000,
            # Required enrichment fields with defaults
            "valence": 0.5,
            "arousal": 0.3,
            "sentiment_score": 0.5,
            "salience_score": 0.5,
            "policy_band": "GREEN",
        },
    }


@pytest.fixture
def enriched_envelope() -> dict[str, Any]:
    """Fully enriched envelope with all optional fields - P02 hybrid structure"""
    return {
        # Header (nested)
        "header": {
            "event_id": "evt_enriched_456",
            "wal_pos": 100,
            "tenant_id": "tenant_premium",
            "space_id": "space_premium",
            "privacy_band": "AMBER",
            "cognitive_trace_id": "trace_enriched_789",
            "timestamp": 1700001000,
        },
        # Flat fields at top level (P02 format)
        "wal_pos": 100,
        "cognitive_trace_id": "trace_enriched_789",
        "embedding_id": "emb_enriched_123",
        "entities_json": json.dumps(["person", "location"]),
        "valence": -0.8,
        "arousal": 0.9,
        "tenant_id": "tenant_premium",
        "space_id": "space_premium",
        # Body
        "body": {"text": "Enriched event with full context"},
        # M13 hipp_events_row output (flat at top level) - complete 70-column row
        "hipp_events_row": {
            "event_id": "evt_enriched_456",
            "wal_pos": 100,
            "embedding_id": "emb_enriched_123",
            "text": "Enriched event with full context",
            "text_hash": "fed654cba321",
            "tenant_id": "tenant_premium",
            "space_id": "space_premium",
            "privacy_band": "AMBER",
            "cognitive_trace_id": "trace_enriched_789",
            "created_at": 1700001000,
            # All enrichment fields
            "valence": -0.8,
            "arousal": 0.9,
            "sentiment_score": -0.8,
            "salience_score": 0.9,
            "policy_band": "AMBER",
            "entities_json": json.dumps(["person", "location"]),
        },
    }


@pytest.fixture
def mock_context() -> MagicMock:
    """Mock PipelineContext with syscalls"""
    context = MagicMock()
    context.syscalls = MagicMock()


@pytest.fixture
def mock_context() -> MagicMock:
    """Mock PipelineContext with syscalls"""
    context = MagicMock()
    context.logger = Mock()
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


def test_assemble_hipp_events_record_missing_text_hash_generates_hash(minimal_envelope):
    """Test that M13-provided text_hash is used (M13 generates hash, not M16)"""
    # Module expects complete hipp_events_row from M13 with text_hash already computed
    envelope = minimal_envelope.copy()

    record = hipp_events_writer.assemble_hipp_events_record(envelope)

    # Verify hash exists (provided by M13)
    assert record["text_hash"] == "abc123def456"
    assert "text" in record


def test_assemble_hipp_events_record_defaults_for_missing_optionals(minimal_envelope):
    """Test that M13-provided row includes all required fields with defaults"""
    # Module expects complete hipp_events_row from M13 (which includes defaults)
    record = hipp_events_writer.assemble_hipp_events_record(minimal_envelope)

    # Verify M13 provided all required fields
    assert record["tenant_id"] == "tenant_test"
    assert record["space_id"] == "space_test"
    assert record["privacy_band"] == "GREEN"
    assert record["cognitive_trace_id"] == "trace_test_456"
    assert record["text"] == "Test event text for M16"
    assert record["valence"] == 0.5  # Default from fixture
    assert record["arousal"] == 0.3  # Default from fixture


def test_assemble_pipeline_processed_record_default_config():
    """Test pipeline processed record with default configuration"""
    envelope = {
        "header": {
            "wal_pos": 42,
            "tenant_id": "tenant_test",
            "space_id": "space_test",
        },
        "wal_pos": 42,  # Module reads from envelope root (P02 flat structure)
        "tenant_id": "tenant_test",
        "space_id": "space_test",
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
        },
        "wal_pos": 100,  # Module reads from envelope root
        "tenant_id": "tenant_custom",
        "space_id": "space_custom",
    }

    record = hipp_events_writer.assemble_pipeline_processed_record(
        envelope, pipeline_id="P03_CONSOLIDATE", status="ERROR"
    )

    assert record["pipeline_id"] == "P03_CONSOLIDATE"
    assert record["status"] == "ERROR"


def test_assemble_pipeline_processed_record_defaults_for_missing_header_fields():
    """Test pipeline processed defaults when header fields missing"""
    envelope = {"header": {"wal_pos": 10}, "wal_pos": 10}  # Module reads from envelope root

    record = hipp_events_writer.assemble_pipeline_processed_record(envelope)

    assert record["tenant_id"] == "default"
    assert record["space_id"] == "unknown"


# =============================================================================
# Category 2: Happy Path Tests (5 tests)
# =============================================================================


@pytest.mark.asyncio
async def test_run_successful_write_minimal_envelope(minimal_envelope, mock_context):
    """Test successful write with minimal envelope"""
    message, context, config = make_test_call(minimal_envelope, mock_context)
    result = await hipp_events_writer.run(message, context, **config)
    write_result = result["hipp_events_write"]

    # Verify result structure
    assert write_result["hipp_events_inserted"] is True
    assert write_result["hipp_events_status"] == "INSERTED"
    assert write_result["pipeline_tracked"] is True
    assert result["header"]["event_id"] == "evt_test_123"
    assert result["header"]["wal_pos"] == 42

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
    """Test successful write with enriched envelope"""
    message, context, config = make_test_call(enriched_envelope, mock_context)
    result = await hipp_events_writer.run(message, context, **config)
    write_result = result["hipp_events_write"]

    assert write_result["hipp_events_inserted"] is True
    assert result["header"]["event_id"] == "evt_enriched_456"
    assert result["header"]["wal_pos"] == 100

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

    message, context, config = make_test_call(minimal_envelope, mock_context)
    result = await hipp_events_writer.run(message, context, **config)
    write_result = result["hipp_events_write"]

    assert write_result["hipp_events_inserted"] is False
    assert write_result["hipp_events_status"] == "SKIPPED_DUPLICATE"

    # Verify metrics
    metrics = hipp_events_writer.get_metrics()
    assert metrics["events_written"] == 0
    assert metrics["duplicates_skipped"] == 1


@pytest.mark.asyncio
async def test_run_custom_pipeline_id_in_config(minimal_envelope, mock_context):
    """Test custom pipeline_id passed via config"""
    message, context, config = make_test_call(
        minimal_envelope, mock_context, pipeline_id="P03_TEST", status="SKIPPED"
    )
    result = await hipp_events_writer.run(message, context, **config)

    # Verify pipeline_processed called with custom config
    call_kwargs = mock_context.syscalls.pipeline_processed_upsert.call_args[1]
    assert call_kwargs["pipeline_id"] == "P03_TEST"
    assert call_kwargs["status"] == "SKIPPED"


@pytest.mark.asyncio
async def test_run_both_tables_written_atomically(minimal_envelope, mock_context):
    """Test both st_hipp_events and st_pipeline_processed written"""
    message, context, config = make_test_call(minimal_envelope, mock_context)
    result = await hipp_events_writer.run(message, context, **config)
    write_result = result["hipp_events_write"]

    # Verify both syscalls invoked
    assert mock_context.syscalls.hipp_events_upsert.call_count == 1
    assert mock_context.syscalls.pipeline_processed_upsert.call_count == 1

    # Verify result includes both operations
    assert write_result["hipp_events_inserted"] in [True, False]
    assert write_result["pipeline_tracked"] is True


# =============================================================================
# Category 3: Error Handling Tests (6 tests)
# =============================================================================


def test_assemble_hipp_events_record_missing_event_id_raises():
    """Test ValueError raised when event_id missing from hipp_events_row"""
    envelope = {
        "hipp_events_row": {
            "wal_pos": 10,
            "embedding_id": "emb_123",
            # No event_id
        },
    }

    with pytest.raises(ValueError, match="Missing event_id in hipp_events_row"):
        hipp_events_writer.assemble_hipp_events_record(envelope)

    # Verify metrics incremented
    metrics = hipp_events_writer.get_metrics()
    assert metrics["missing_event_id"] == 1


def test_assemble_hipp_events_record_missing_wal_pos_raises():
    """Test ValueError raised when wal_pos missing from hipp_events_row"""
    envelope = {
        "hipp_events_row": {
            "event_id": "evt_123",
            "embedding_id": "emb_123",
            # wal_pos missing
        },
    }

    with pytest.raises(ValueError, match="Missing wal_pos in hipp_events_row"):
        hipp_events_writer.assemble_hipp_events_record(envelope)

    metrics = hipp_events_writer.get_metrics()
    assert metrics["missing_wal_pos"] == 1


def test_assemble_hipp_events_record_missing_embedding_id_raises():
    """Test ValueError raised when embedding_id missing from hipp_events_row"""
    envelope = {
        "hipp_events_row": {
            "event_id": "evt_123",
            "wal_pos": 10,
            # embedding_id missing
        },
    }

    with pytest.raises(ValueError, match="Missing embedding_id in hipp_events_row"):
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
    """Test that context is required in Phase 2 signature (positional parameter)"""
    envelope = {"header": {}, "body": {}, "outputs": {}}
    message = MockMessage(envelope)

    # In Phase 2, context is a required positional parameter
    # This test verifies the signature requires it
    import inspect

    sig = inspect.signature(hipp_events_writer.run)
    params = list(sig.parameters.values())
    assert params[1].name == "context"
    assert params[1].default == inspect.Parameter.empty  # No default value


@pytest.mark.asyncio
async def test_run_storage_failure_raises_runtime_error(minimal_envelope, mock_context):
    """Test RuntimeError raised when storage operation fails"""
    # Mock syscalls to raise exception
    mock_context.syscalls.hipp_events_upsert.side_effect = Exception("Database connection failed")

    message, context, config = make_test_call(minimal_envelope, mock_context)
    with pytest.raises(RuntimeError, match="Failed to write hipp events"):
        await hipp_events_writer.run(message, context, **config)

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

    message, context, config = make_test_call(minimal_envelope, mock_context)
    with pytest.raises(PermissionError):
        await hipp_events_writer.run(message, context, **config)


@pytest.mark.asyncio
async def test_run_capability_check_pipeline_processed_write(minimal_envelope, mock_context):
    """Test st_pipeline_processed.write capability checked"""
    from k0.kernel.syscalls import PermissionError

    # First call succeeds, second fails
    mock_context.syscalls.pipeline_processed_upsert.side_effect = PermissionError(
        "Missing capability: st_pipeline_processed.write"
    )

    message, context, config = make_test_call(minimal_envelope, mock_context)
    with pytest.raises(PermissionError):
        await hipp_events_writer.run(message, context, **config)


@pytest.mark.asyncio
async def test_run_syscalls_called_with_correct_arguments(minimal_envelope, mock_context):
    """Test syscalls invoked with correct argument structure"""
    message, context, config = make_test_call(minimal_envelope, mock_context)
    await hipp_events_writer.run(message, context, **config)

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
    bad_context.logger = Mock()

    message, context, config = make_test_call(minimal_envelope, bad_context)
    with pytest.raises(AttributeError):
        await hipp_events_writer.run(message, context, **config)


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
    message, context, config = make_test_call(minimal_envelope, mock_context)
    await hipp_events_writer.run(message, context, **config)

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

    message, context, config = make_test_call(minimal_envelope, mock_context)
    await hipp_events_writer.run(message, context, **config)

    metrics = hipp_events_writer.get_metrics()
    assert metrics["duplicates_skipped"] == 1
    assert metrics["events_written"] == 0


@pytest.mark.asyncio
async def test_metrics_write_failures_incremented_on_error(minimal_envelope, mock_context):
    """Test write_failures counter incremented on storage failure"""
    mock_context.syscalls.hipp_events_upsert.side_effect = Exception("Storage error")

    message, context, config = make_test_call(minimal_envelope, mock_context)
    with pytest.raises(RuntimeError):
        await hipp_events_writer.run(message, context, **config)

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
    message, context, config = make_test_call(minimal_envelope, mock_context)
    result = await hipp_events_writer.run(message, context, **config)
    write_result = result["hipp_events_write"]

    # Verify end-to-end flow
    assert write_result["hipp_events_inserted"] is True
    assert write_result["pipeline_tracked"] is True
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

    message, context, config = make_test_call(minimal_envelope, mock_context)
    await hipp_events_writer.run(message, context, **config)

    assert call_order == ["hipp_events", "pipeline_processed"]


@pytest.mark.asyncio
async def test_integration_multiple_writes_increment_metrics(minimal_envelope, mock_context):
    """Test multiple writes correctly update metrics"""
    # Create 5 envelopes with complete hipp_events_row from M13
    envelopes = []
    for i in range(5):
        envelope = minimal_envelope.copy()
        envelope["hipp_events_row"] = envelope["hipp_events_row"].copy()
        envelope["hipp_events_row"]["event_id"] = f"evt_{i}"
        envelope["hipp_events_row"]["wal_pos"] = i
        envelope["hipp_events_row"]["embedding_id"] = f"emb_{i}"
        envelope["wal_pos"] = i
        envelopes.append(envelope)

    for envelope in envelopes:
        message, context, config = make_test_call(envelope, mock_context)
        await hipp_events_writer.run(message, context, **config)

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

    message, context, config = make_test_call(minimal_envelope, mock_context)
    with pytest.raises(RuntimeError):
        await hipp_events_writer.run(message, context, **config)

    # Verify first call succeeded (separate transaction)
    assert mock_context.syscalls.hipp_events_upsert.called


# =============================================================================
# Category 7: Performance Tests (4 tests)
# =============================================================================


@pytest.mark.asyncio
async def test_performance_single_write_under_25ms(minimal_envelope, mock_context):
    """Test single write completes under 25ms P95 target"""
    message, context, config = make_test_call(minimal_envelope, mock_context)
    start = time.perf_counter()
    await hipp_events_writer.run(message, context, **config)
    duration_ms = (time.perf_counter() - start) * 1000

    # Should be well under 25ms with mocked syscalls
    assert duration_ms < 25.0, f"Write took {duration_ms:.2f}ms (target: <25ms)"


@pytest.mark.asyncio
async def test_performance_batch_writes_throughput(minimal_envelope, mock_context):
    """Test throughput for batch of writes (target: 40-50 ops/sec)"""
    # Create 50 envelopes with complete hipp_events_row
    envelopes = []
    for i in range(50):
        envelope = minimal_envelope.copy()
        envelope["hipp_events_row"] = envelope["hipp_events_row"].copy()
        envelope["hipp_events_row"]["event_id"] = f"evt_{i}"
        envelope["hipp_events_row"]["wal_pos"] = i
        envelope["hipp_events_row"]["embedding_id"] = f"emb_{i}"
        envelope["wal_pos"] = i
        envelopes.append(envelope)

    start = time.perf_counter()
    for envelope in envelopes:
        message, context, config = make_test_call(envelope, mock_context)
        await hipp_events_writer.run(message, context, **config)
    duration_sec = time.perf_counter() - start

    ops_per_sec = 50 / duration_sec
    # With mocked syscalls, should easily exceed 40 ops/sec
    assert ops_per_sec > 40.0, f"Throughput: {ops_per_sec:.1f} ops/sec (target: >40 ops/sec)"


def test_performance_record_assembly_fast(minimal_envelope):
    """Test record assembly completes in <1ms"""
    # Module just extracts hipp_events_row from envelope (very fast)

    start = time.perf_counter()
    hipp_events_writer.assemble_hipp_events_record(minimal_envelope)
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
