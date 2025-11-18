"""
Tests for M17: core.event_emitter (Event Emission Module)

Test Coverage:
- Event Construction: 6 tests (one per event type)
- Happy Path: 5 tests (successful emission, batching, idempotency)
- Error Handling: 6 tests (missing enrichments, syscall failures, validation)
- Capability Enforcement: 3 tests (permission checks)
- Metrics: 5 tests (counter updates, latency tracking)
- Integration: 4 tests (batch emission, ordering, fingerprints)
- Performance: 3 tests (<10ms latency, throughput)

Total: 32 tests

Contract: k0/contracts/modules/core.event_emitter.v1.yaml
Module: k0/modules/core/event_emitter.py
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.core import event_emitter

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_envelope():
    """
    Sample envelope with all required enrichments.
    """
    return {
        "enrichments": {
            "space_resolver": {
                "space_id": "space_test_123",
                "tenant_id": "tenant_test_456",
                "envelope_id": "env_test_789",
                "resolution_method": "direct",
                "visibility": "private",
            },
            "working_memory": {
                "snapshot": {"key1": "value1", "key2": "value2"},
                "timestamp": "2024-12-27T10:00:00Z",
            },
            "affect_analyzer": {
                "valence": 0.8,
                "arousal": 0.6,
                "emotion": "happy",
                "confidence": 0.9,
            },
            "embedding_queue": {
                "embed_event_id": "embed_test_111",
                "text_hash": "hash_test_222",
                "priority": "normal",
            },
            "hipp_events": {
                "hipp_event_id": "hipp_test_333",
                "pattern_type": "episodic",
                "encoding_timestamp": "2024-12-27T10:00:01Z",
            },
        }
    }


@pytest.fixture
def mock_context():
    """
    Mock context with syscalls.
    """
    context = MagicMock()
    context.syscalls = MagicMock()
    context.syscalls.outbox_emit_batch = AsyncMock(
        return_value={
            "events_inserted": 6,
            "batch_size": 6,
            "operation": "outbox_emit_batch",
            "status": "success",
        }
    )
    return context


@pytest.fixture(autouse=True)
def reset_metrics():
    """
    Reset module-level metrics before each test.
    """
    event_emitter.reset_metrics()
    yield
    event_emitter.reset_metrics()


# ============================================================================
# CATEGORY 1: EVENT CONSTRUCTION (6 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_workspace_wm_event_structure(sample_envelope, mock_context):
    """
    Verify workspace.wm.updated event has correct structure.
    """
    result = await event_emitter.run(sample_envelope, mock_context)

    assert result["events_emitted"] == 6
    assert "workspace.wm.updated" in result["topics"]

    # Get emitted events
    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]

    wm_event = next(e for e in events if e["driver"] == "workspace.wm.updated")

    assert wm_event["tenant_id"] == "tenant_test_456"
    assert wm_event["space_id"] == "space_test_123"
    assert wm_event["op_kind"] == "EVENT_EMIT"
    assert "working_memory" in wm_event["payload"]
    assert wm_event["payload"]["envelope_id"] == "env_test_789"
    assert len(wm_event["fingerprint"]) == 64  # SHA256 hex


@pytest.mark.asyncio
async def test_affect_analyzed_event_structure(sample_envelope, mock_context):
    """
    Verify affect.analyzed event has correct structure.
    """
    await event_emitter.run(sample_envelope, mock_context)

    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]

    affect_event = next(e for e in events if e["driver"] == "affect.analyzed")

    assert affect_event["payload"]["valence"] == 0.8
    assert affect_event["payload"]["arousal"] == 0.6
    assert affect_event["payload"]["emotion"] == "happy"
    assert affect_event["payload"]["confidence"] == 0.9


@pytest.mark.asyncio
async def test_space_resolution_event_structure(sample_envelope, mock_context):
    """
    Verify space.resolution event has correct structure.
    """
    await event_emitter.run(sample_envelope, mock_context)

    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]

    space_event = next(e for e in events if e["driver"] == "space.resolution")

    assert space_event["payload"]["space_id"] == "space_test_123"
    assert space_event["payload"]["resolution_method"] == "direct"
    assert space_event["payload"]["visibility"] == "private"


@pytest.mark.asyncio
async def test_embedding_enqueue_event_structure(sample_envelope, mock_context):
    """
    Verify embedding.enqueue event has correct structure.
    """
    await event_emitter.run(sample_envelope, mock_context)

    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]

    embed_event = next(e for e in events if e["driver"] == "embedding.enqueue")

    assert embed_event["payload"]["embed_event_id"] == "embed_test_111"
    assert embed_event["payload"]["text_hash"] == "hash_test_222"
    assert embed_event["payload"]["priority"] == "normal"


@pytest.mark.asyncio
async def test_hippocampus_pattern_separated_event_structure(sample_envelope, mock_context):
    """
    Verify hippocampus.pattern_separated event has correct structure.
    """
    await event_emitter.run(sample_envelope, mock_context)

    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]

    hipp_event = next(e for e in events if e["driver"] == "hippocampus.pattern_separated")

    assert hipp_event["payload"]["hipp_event_id"] == "hipp_test_333"
    assert hipp_event["payload"]["pattern_type"] == "episodic"
    assert hipp_event["payload"]["encoding_timestamp"] == "2024-12-27T10:00:01Z"


@pytest.mark.asyncio
async def test_write_complete_event_structure(sample_envelope, mock_context):
    """
    Verify write.complete event has correct structure.
    """
    await event_emitter.run(sample_envelope, mock_context)

    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]

    complete_event = next(e for e in events if e["driver"] == "write.complete")

    assert complete_event["payload"]["pipeline"] == "p02_write"
    assert "space_resolver" in complete_event["payload"]["modules_executed"]
    assert "working_memory" in complete_event["payload"]["modules_executed"]
    assert "affect_analyzer" in complete_event["payload"]["modules_executed"]


# ============================================================================
# CATEGORY 2: HAPPY PATH (5 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_successful_6_event_emission(sample_envelope, mock_context):
    """
    Verify all 6 events emitted successfully.
    """
    result = await event_emitter.run(sample_envelope, mock_context)

    assert result["status"] == "success"
    assert result["events_emitted"] == 6
    assert len(result["topics"]) == 6

    expected_topics = [
        "workspace.wm.updated",
        "affect.analyzed",
        "space.resolution",
        "embedding.enqueue",
        "hippocampus.pattern_separated",
        "write.complete",
    ]

    for topic in expected_topics:
        assert topic in result["topics"]


@pytest.mark.asyncio
async def test_batch_emission_single_syscall(sample_envelope, mock_context):
    """
    Verify all events emitted in single batch syscall.
    """
    await event_emitter.run(sample_envelope, mock_context)

    # Should call outbox_emit_batch exactly once
    assert mock_context.syscalls.outbox_emit_batch.call_count == 1

    # Should pass all 6 events
    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]
    assert len(events) == 6


@pytest.mark.asyncio
async def test_idempotency_fingerprints_unique(sample_envelope, mock_context):
    """
    Verify each event has unique fingerprint.
    """
    await event_emitter.run(sample_envelope, mock_context)

    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]

    fingerprints = [e["fingerprint"] for e in events]

    # All fingerprints should be unique
    assert len(fingerprints) == len(set(fingerprints))

    # All fingerprints should be 64-char SHA256 hashes
    for fp in fingerprints:
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)


@pytest.mark.asyncio
async def test_same_envelope_produces_same_fingerprints(sample_envelope, mock_context):
    """
    Verify idempotency: same envelope produces same fingerprints.
    """
    # First run
    await event_emitter.run(sample_envelope, mock_context)
    call_args_1 = mock_context.syscalls.outbox_emit_batch.call_args
    events_1 = call_args_1[0][0]
    fingerprints_1 = {e["driver"]: e["fingerprint"] for e in events_1}

    # Reset mock
    mock_context.syscalls.outbox_emit_batch.reset_mock()
    mock_context.syscalls.outbox_emit_batch.return_value = {
        "events_inserted": 6,
        "batch_size": 6,
        "operation": "outbox_emit_batch",
        "status": "success",
    }

    # Second run with same envelope
    await event_emitter.run(sample_envelope, mock_context)
    call_args_2 = mock_context.syscalls.outbox_emit_batch.call_args
    events_2 = call_args_2[0][0]
    fingerprints_2 = {e["driver"]: e["fingerprint"] for e in events_2}

    # Fingerprints should match
    assert fingerprints_1 == fingerprints_2


@pytest.mark.asyncio
async def test_latency_tracking(sample_envelope, mock_context):
    """
    Verify latency_ms tracked in result.
    """
    result = await event_emitter.run(sample_envelope, mock_context)

    assert "latency_ms" in result
    assert result["latency_ms"] >= 0
    assert result["latency_ms"] < 1000  # Should be <1s for 6 events


# ============================================================================
# CATEGORY 3: ERROR HANDLING (6 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_missing_enrichments_key(mock_context):
    """
    Verify KeyError raised when enrichments missing.
    """
    envelope = {"no_enrichments": {}}

    with pytest.raises(KeyError, match="Envelope missing 'enrichments' key"):
        await event_emitter.run(envelope, mock_context)


@pytest.mark.asyncio
async def test_missing_required_enrichment(mock_context):
    """
    Verify KeyError raised when required enrichment missing.
    """
    envelope = {
        "enrichments": {
            "space_resolver": {
                "space_id": "space_123",
                "tenant_id": "tenant_456",
                "envelope_id": "env_789",
            },
            # Missing working_memory, affect_analyzer, embedding_queue, hipp_events
        }
    }

    with pytest.raises(KeyError, match="missing required enrichments"):
        await event_emitter.run(envelope, mock_context)


@pytest.mark.asyncio
async def test_syscall_failure_propagates(sample_envelope, mock_context):
    """
    Verify syscall failures propagate to caller.
    """
    # Simulate outbox_emit_batch failure
    mock_context.syscalls.outbox_emit_batch.side_effect = RuntimeError("Outbox write failed")

    with pytest.raises(RuntimeError, match="Outbox write failed"):
        await event_emitter.run(sample_envelope, mock_context)


@pytest.mark.asyncio
async def test_failure_updates_metrics(sample_envelope, mock_context):
    """
    Verify failed emissions update failure metrics.
    """
    # Simulate failure
    mock_context.syscalls.outbox_emit_batch.side_effect = RuntimeError("Outbox failure")

    with pytest.raises(RuntimeError):
        await event_emitter.run(sample_envelope, mock_context)

    metrics = event_emitter.get_metrics()
    assert metrics["events_failed"] == 6  # All 6 events failed
    assert metrics["events_emitted"] == 0  # No events emitted


@pytest.mark.asyncio
async def test_missing_envelope_id_uses_default(mock_context):
    """
    Verify missing envelope_id uses 'unknown' default.
    """
    envelope = {
        "enrichments": {
            "space_resolver": {
                "space_id": "space_123",
                "tenant_id": "tenant_456",
                # Missing envelope_id
            },
            "working_memory": {"snapshot": {}, "timestamp": ""},
            "affect_analyzer": {"valence": 0, "arousal": 0, "emotion": "neutral", "confidence": 0},
            "embedding_queue": {"embed_event_id": "", "text_hash": "", "priority": "normal"},
            "hipp_events": {
                "hipp_event_id": "",
                "pattern_type": "episodic",
                "encoding_timestamp": "",
            },
        }
    }

    result = await event_emitter.run(envelope, mock_context)

    assert result["status"] == "success"

    # Check event payloads have envelope_id = "unknown"
    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]

    for event in events:
        assert event["payload"]["envelope_id"] == "unknown"


@pytest.mark.asyncio
async def test_partial_enrichment_data_uses_defaults(mock_context):
    """
    Verify missing enrichment fields use defaults (get() with defaults).
    """
    envelope = {
        "enrichments": {
            "space_resolver": {
                "space_id": "space_123",
                "tenant_id": "tenant_456",
                "envelope_id": "env_789",
                # Missing resolution_method, visibility
            },
            "working_memory": {"snapshot": {}},  # Missing timestamp
            "affect_analyzer": {"valence": 0.5},  # Missing arousal, emotion, confidence
            "embedding_queue": {"embed_event_id": "embed_123"},  # Missing text_hash, priority
            "hipp_events": {
                "hipp_event_id": "hipp_456"
            },  # Missing pattern_type, encoding_timestamp
        }
    }

    result = await event_emitter.run(envelope, mock_context)

    assert result["status"] == "success"

    # Verify defaults applied
    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]

    affect_event = next(e for e in events if e["driver"] == "affect.analyzed")
    assert affect_event["payload"]["arousal"] == 0.0  # Default
    assert affect_event["payload"]["emotion"] == "neutral"  # Default


# ============================================================================
# CATEGORY 4: CAPABILITY ENFORCEMENT (3 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_capability_check_enforced(sample_envelope):
    """
    Verify st_outbox.write capability required (PermissionError if missing).
    """
    # Mock context without capability
    context = MagicMock()
    context.syscalls = MagicMock()
    context.syscalls.outbox_emit_batch = AsyncMock(
        side_effect=PermissionError("Missing capability: st_outbox.write")
    )

    with pytest.raises(PermissionError, match="st_outbox.write"):
        await event_emitter.run(sample_envelope, context)


@pytest.mark.asyncio
async def test_no_capability_bypass(sample_envelope, mock_context):
    """
    Verify module cannot bypass capability check.
    """
    # Module should call syscalls.outbox_emit_batch (capability-gated)
    await event_emitter.run(sample_envelope, mock_context)

    # Verify syscall was called (capability check enforced)
    assert mock_context.syscalls.outbox_emit_batch.called


@pytest.mark.asyncio
async def test_capability_failure_no_events_emitted(sample_envelope):
    """
    Verify no events emitted if capability check fails.
    """
    context = MagicMock()
    context.syscalls = MagicMock()
    context.syscalls.outbox_emit_batch = AsyncMock(side_effect=PermissionError("No capability"))

    with pytest.raises(PermissionError):
        await event_emitter.run(sample_envelope, context)

    # Metrics should show failure (6 events failed)
    metrics = event_emitter.get_metrics()
    assert metrics["events_failed"] == 6
    assert metrics["events_emitted"] == 0


# ============================================================================
# CATEGORY 5: METRICS (5 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_metrics_events_emitted_increments(sample_envelope, mock_context):
    """
    Verify events_emitted counter increments.
    """
    await event_emitter.run(sample_envelope, mock_context)

    metrics = event_emitter.get_metrics()
    assert metrics["events_emitted"] == 6


@pytest.mark.asyncio
async def test_metrics_multiple_runs_accumulate(sample_envelope, mock_context):
    """
    Verify metrics accumulate across multiple runs.
    """
    await event_emitter.run(sample_envelope, mock_context)
    await event_emitter.run(sample_envelope, mock_context)
    await event_emitter.run(sample_envelope, mock_context)

    metrics = event_emitter.get_metrics()
    assert metrics["events_emitted"] == 18  # 3 runs * 6 events


@pytest.mark.asyncio
async def test_metrics_latency_tracking(sample_envelope, mock_context):
    """
    Verify latency metrics tracked correctly.
    """
    await event_emitter.run(sample_envelope, mock_context)

    metrics = event_emitter.get_metrics()
    assert metrics["total_latency_ms"] > 0
    assert metrics["avg_latency_ms"] > 0


@pytest.mark.asyncio
async def test_metrics_reset_clears_counters(sample_envelope, mock_context):
    """
    Verify reset_metrics() clears all counters.
    """
    await event_emitter.run(sample_envelope, mock_context)

    metrics = event_emitter.get_metrics()
    assert metrics["events_emitted"] > 0

    event_emitter.reset_metrics()

    metrics = event_emitter.get_metrics()
    assert metrics["events_emitted"] == 0
    assert metrics["events_failed"] == 0
    assert metrics["total_latency_ms"] == 0.0
    assert metrics["avg_latency_ms"] == 0.0


@pytest.mark.asyncio
async def test_metrics_failure_tracking(sample_envelope, mock_context):
    """
    Verify events_failed counter increments on failure.
    """
    mock_context.syscalls.outbox_emit_batch.side_effect = RuntimeError("Outbox failure")

    with pytest.raises(RuntimeError):
        await event_emitter.run(sample_envelope, mock_context)

    metrics = event_emitter.get_metrics()
    assert metrics["events_failed"] == 6
    assert metrics["events_emitted"] == 0


# ============================================================================
# CATEGORY 6: INTEGRATION (4 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_integration_batch_emission_ordering(sample_envelope, mock_context):
    """
    Verify events emitted in deterministic order.
    """
    await event_emitter.run(sample_envelope, mock_context)

    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]

    topics = [e["driver"] for e in events]

    expected_order = [
        "workspace.wm.updated",
        "affect.analyzed",
        "space.resolution",
        "embedding.enqueue",
        "hippocampus.pattern_separated",
        "write.complete",
    ]

    assert topics == expected_order


@pytest.mark.asyncio
async def test_integration_all_events_same_tenant_space(sample_envelope, mock_context):
    """
    Verify all events share same tenant_id and space_id.
    """
    await event_emitter.run(sample_envelope, mock_context)

    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]

    tenant_ids = set(e["tenant_id"] for e in events)
    space_ids = set(e["space_id"] for e in events)

    assert len(tenant_ids) == 1
    assert len(space_ids) == 1
    assert "tenant_test_456" in tenant_ids
    assert "space_test_123" in space_ids


@pytest.mark.asyncio
async def test_integration_fingerprints_deterministic(sample_envelope, mock_context):
    """
    Verify fingerprints deterministic based on space_id + topic + envelope_id.
    """
    # Run twice with same envelope
    await event_emitter.run(sample_envelope, mock_context)
    call_args_1 = mock_context.syscalls.outbox_emit_batch.call_args
    events_1 = call_args_1[0][0]

    mock_context.syscalls.outbox_emit_batch.reset_mock()
    mock_context.syscalls.outbox_emit_batch.return_value = {
        "events_inserted": 6,
        "batch_size": 6,
        "operation": "outbox_emit_batch",
        "status": "success",
    }

    await event_emitter.run(sample_envelope, mock_context)
    call_args_2 = mock_context.syscalls.outbox_emit_batch.call_args
    events_2 = call_args_2[0][0]

    # Fingerprints should match exactly
    for e1, e2 in zip(events_1, events_2):
        assert e1["fingerprint"] == e2["fingerprint"]


@pytest.mark.asyncio
async def test_integration_all_events_op_kind_event_emit(sample_envelope, mock_context):
    """
    Verify all events have op_kind = "EVENT_EMIT".
    """
    await event_emitter.run(sample_envelope, mock_context)

    call_args = mock_context.syscalls.outbox_emit_batch.call_args
    events = call_args[0][0]

    op_kinds = set(e["op_kind"] for e in events)

    assert len(op_kinds) == 1
    assert "EVENT_EMIT" in op_kinds


# ============================================================================
# CATEGORY 7: PERFORMANCE (3 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_performance_batch_emission_under_10ms(sample_envelope, mock_context):
    """
    Verify 6-event batch emitted in <10ms (contract requirement).
    """
    start = time.perf_counter()
    result = await event_emitter.run(sample_envelope, mock_context)
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Should be well under 10ms for in-memory mock
    assert elapsed_ms < 10
    assert result["latency_ms"] < 10


@pytest.mark.asyncio
async def test_performance_throughput_over_100_batches_per_second(sample_envelope, mock_context):
    """
    Verify throughput >100 batches/sec (600 events/sec).
    """
    iterations = 100

    start = time.perf_counter()
    for _ in range(iterations):
        await event_emitter.run(sample_envelope, mock_context)
    elapsed = time.perf_counter() - start

    batches_per_sec = iterations / elapsed
    events_per_sec = (iterations * 6) / elapsed

    assert batches_per_sec > 100
    assert events_per_sec > 600


@pytest.mark.asyncio
async def test_performance_avg_latency_tracking_accurate(sample_envelope, mock_context):
    """
    Verify avg_latency_ms calculation accurate.

    Avg latency = total_latency_ms / events_emitted (per-event latency)
    """
    # Run 10 times
    for _ in range(10):
        await event_emitter.run(sample_envelope, mock_context)

    metrics = event_emitter.get_metrics()

    # Calculate expected avg: total latency / total events
    expected_avg = metrics["total_latency_ms"] / metrics["events_emitted"]
    actual_avg = metrics["avg_latency_ms"]

    # Should match exactly (calculation is simple division)
    assert abs(actual_avg - expected_avg) < 0.0001  # Floating point tolerance
