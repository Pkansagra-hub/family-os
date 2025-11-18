"""
Tests for M14 (Embedding Queue Writer)

Test Coverage:
- Queue record assembly (5 tests)
- Database write operations (4 tests)
- Idempotency (3 tests)
- P08 integration (claim, ready, failed) (6 tests)
- Error handling (3 tests)
- Performance (<5ms P95 budget) (2 tests)
- Metrics (2 tests)
- End-to-end integration (3 tests)

Total: ~28 tests

**Contract**: k0/contracts/modules/builders.embedding_queue_write.v1.yaml
**ADR**: docs/architecture/decisions-K0/modules/k009.2-embedding-queue-writer.md
"""

import time
from typing import Any, Dict

import pytest

from k0.modules.builders.embedding_queue_write import (
    assemble_embedding_queue_record,
    claim_embedding_job,
    get_metrics,
    get_queue_record,
    mark_embedding_failed,
    mark_embedding_ready,
    reset_metrics,
    run,
    write_to_embedding_queue,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def base_envelope() -> Dict[str, Any]:
    """Base envelope with all required fields"""
    return {
        "header": {
            "event_id": "evt_123456",
            "wal_pos": 1001,
            "tenant_id": "tenant_family123",
            "space_id": "space_personal_dad",
            "trace_id": "trace_abc123",
        },
        "body": {"actor_id": "person_dad", "text": "Had dinner with family"},
        "outputs": {},
    }


@pytest.fixture
def ca1_output() -> Dict[str, Any]:
    """M02 semantic_project output"""
    return {
        "embedding_id": "emb_uuid_abc123",
        "entities": ["person_mom", "Olive_Garden"],
        "kg_triples": [["person_dad", "had_dinner_with", "person_mom"]],
    }


# =============================================================================
# Queue Record Assembly Tests
# =============================================================================


@pytest.mark.asyncio
async def test_assemble_queue_record_success(base_envelope, ca1_output):
    """Test successful queue record assembly"""
    reset_metrics()
    record = assemble_embedding_queue_record(base_envelope, ca1_output)

    assert record["embedding_id"] == "emb_uuid_abc123"
    assert record["event_id"] == "evt_123456"
    assert record["wal_pos"] == 1001
    assert record["tenant_id"] == "tenant_family123"
    assert record["space_id"] == "space_personal_dad"
    assert record["vector_kind"] == "memory.body.text"
    assert record["model_id"] == "embed-mini-001"
    assert record["priority"] == "NORMAL"
    assert record["status"] == "PENDING"
    assert record["attempt_count"] == 0
    assert record["max_attempts"] == 5
    assert record["last_error"] is None
    assert "created_at" in record
    assert "updated_at" in record


@pytest.mark.asyncio
async def test_assemble_queue_record_missing_embedding_id(base_envelope):
    """Test queue record assembly fails with missing embedding_id"""
    reset_metrics()
    bad_ca1_output = {"entities": [], "kg_triples": []}  # No embedding_id

    with pytest.raises(ValueError, match="Missing embedding_id"):
        assemble_embedding_queue_record(base_envelope, bad_ca1_output)

    metrics = get_metrics()
    assert metrics["missing_embedding_id"] == 1


@pytest.mark.asyncio
async def test_assemble_queue_record_default_values(base_envelope, ca1_output):
    """Test default values in queue record"""
    reset_metrics()
    record = assemble_embedding_queue_record(base_envelope, ca1_output)

    # Verify defaults
    assert record["vector_kind"] == "memory.body.text"  # Default for P02
    assert record["model_id"] == "embed-mini-001"  # Default model
    assert record["priority"] == "NORMAL"  # Default priority
    assert record["status"] == "PENDING"  # Initial status
    assert record["attempt_count"] == 0  # No attempts yet
    assert record["max_attempts"] == 5  # Default max retries


@pytest.mark.asyncio
async def test_assemble_queue_record_timestamps(base_envelope, ca1_output):
    """Test timestamp fields in queue record"""
    reset_metrics()
    before = int(time.time())
    record = assemble_embedding_queue_record(base_envelope, ca1_output)
    after = int(time.time())

    assert before <= record["created_at"] <= after
    assert before <= record["updated_at"] <= after
    assert before <= record["next_attempt_ts"] <= after


@pytest.mark.asyncio
async def test_assemble_queue_record_immediateattempt(base_envelope, ca1_output):
    """Test next_attempt_ts is immediate (now) for initial insert"""
    reset_metrics()
    now = int(time.time())
    record = assemble_embedding_queue_record(base_envelope, ca1_output)

    # Should be immediate (within 1 second of now)
    assert abs(record["next_attempt_ts"] - now) <= 1


# =============================================================================
# Database Write Tests
# =============================================================================


@pytest.mark.asyncio
async def test_write_to_queue_success(base_envelope, ca1_output):
    """Test successful write to embedding queue"""
    reset_metrics()
    record = assemble_embedding_queue_record(base_envelope, ca1_output)

    result = await write_to_embedding_queue(record)

    assert result["inserted"] is True
    assert result["embedding_id"] == "emb_uuid_abc123"
    assert result["status"] == "PENDING"
    assert "created_at" in result

    # Verify metrics
    metrics = get_metrics()
    assert metrics["jobs_enqueued"] == 1
    assert metrics["duplicates_skipped"] == 0


@pytest.mark.asyncio
async def test_write_to_queue_duplicate_skipped(base_envelope, ca1_output):
    """Test duplicate embedding_id is skipped (idempotent)"""
    reset_metrics()
    record = assemble_embedding_queue_record(base_envelope, ca1_output)

    # First write succeeds
    result1 = await write_to_embedding_queue(record)
    assert result1["inserted"] is True

    # Second write skipped (duplicate)
    result2 = await write_to_embedding_queue(record)
    assert result2["inserted"] is False
    assert result2["status"] == "SKIPPED_DUPLICATE"
    assert "already exists" in result2["reason"]

    # Verify metrics
    metrics = get_metrics()
    assert metrics["jobs_enqueued"] == 1  # Only first insert counted
    assert metrics["duplicates_skipped"] == 1


@pytest.mark.asyncio
async def test_write_to_queue_multiple_unique(base_envelope, ca1_output):
    """Test multiple unique embedding_ids can be written"""
    reset_metrics()

    # Write first job
    record1 = assemble_embedding_queue_record(base_envelope, ca1_output)
    result1 = await write_to_embedding_queue(record1)
    assert result1["inserted"] is True

    # Write second job (different embedding_id)
    ca1_output["embedding_id"] = "emb_uuid_xyz789"
    record2 = assemble_embedding_queue_record(base_envelope, ca1_output)
    result2 = await write_to_embedding_queue(record2)
    assert result2["inserted"] is True

    # Verify metrics
    metrics = get_metrics()
    assert metrics["jobs_enqueued"] == 2
    assert metrics["duplicates_skipped"] == 0


@pytest.mark.asyncio
async def test_get_queue_record(base_envelope, ca1_output):
    """Test queue record retrieval"""
    reset_metrics()
    record = assemble_embedding_queue_record(base_envelope, ca1_output)
    await write_to_embedding_queue(record)

    # Retrieve record
    retrieved = get_queue_record("emb_uuid_abc123")
    assert retrieved is not None
    assert retrieved["embedding_id"] == "emb_uuid_abc123"
    assert retrieved["status"] == "PENDING"


# =============================================================================
# Idempotency Tests
# =============================================================================


@pytest.mark.asyncio
async def test_idempotency_same_envelope(base_envelope, ca1_output):
    """Test idempotency with same envelope run twice"""
    reset_metrics()
    base_envelope["outputs"]["semantic_project"] = ca1_output

    # First run succeeds
    result1 = await run(base_envelope)
    assert result1["inserted"] is True

    # Second run skipped (duplicate)
    result2 = await run(base_envelope)
    assert result2["inserted"] is False


@pytest.mark.asyncio
async def test_idempotency_no_state_pollution(base_envelope, ca1_output):
    """Test idempotency doesn't pollute state"""
    reset_metrics()
    record = assemble_embedding_queue_record(base_envelope, ca1_output)

    # Write once
    await write_to_embedding_queue(record)
    retrieved1 = get_queue_record("emb_uuid_abc123")

    # Write again (duplicate)
    await write_to_embedding_queue(record)
    retrieved2 = get_queue_record("emb_uuid_abc123")

    # Record should be unchanged
    assert retrieved1 == retrieved2


@pytest.mark.asyncio
async def test_idempotency_concurrent_writes(base_envelope, ca1_output):
    """Test idempotency with concurrent writes (simulated)"""
    reset_metrics()
    record = assemble_embedding_queue_record(base_envelope, ca1_output)

    # Simulate concurrent writes
    results = []
    for _ in range(5):
        result = await write_to_embedding_queue(record)
        results.append(result)

    # Only first write succeeds
    assert results[0]["inserted"] is True
    assert all(r["inserted"] is False for r in results[1:])

    # Verify metrics
    metrics = get_metrics()
    assert metrics["jobs_enqueued"] == 1
    assert metrics["duplicates_skipped"] == 4


# =============================================================================
# P08 Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_p08_claim_pending_job(base_envelope, ca1_output):
    """Test P08 worker claims PENDING job"""
    reset_metrics()
    record = assemble_embedding_queue_record(base_envelope, ca1_output)
    await write_to_embedding_queue(record)

    # P08 claims job
    job = await claim_embedding_job()
    assert job is not None
    assert job["embedding_id"] == "emb_uuid_abc123"
    assert job["status"] == "IN_PROGRESS"
    assert job["attempt_count"] == 1

    # Verify queue metrics
    metrics = get_metrics()
    assert metrics["queue_depth_pending"] == 0
    assert metrics["queue_depth_in_progress"] == 1


@pytest.mark.asyncio
async def test_p08_claim_no_pending_jobs():
    """Test P08 worker returns None when no PENDING jobs"""
    reset_metrics()

    # No jobs in queue
    job = await claim_embedding_job()
    assert job is None


@pytest.mark.asyncio
async def test_p08_mark_ready(base_envelope, ca1_output):
    """Test P08 marks job READY after vector stored"""
    reset_metrics()
    record = assemble_embedding_queue_record(base_envelope, ca1_output)
    await write_to_embedding_queue(record)

    # P08 claims and processes
    await claim_embedding_job()

    # P08 marks ready
    success = await mark_embedding_ready("emb_uuid_abc123")
    assert success is True

    # Verify status
    retrieved = get_queue_record("emb_uuid_abc123")
    assert retrieved["status"] == "READY"

    # Verify metrics
    metrics = get_metrics()
    assert metrics["queue_depth_ready"] == 1


@pytest.mark.asyncio
async def test_p08_mark_failed_retryable(base_envelope, ca1_output):
    """Test P08 marks job FAILED_RETRYABLE after error"""
    reset_metrics()
    record = assemble_embedding_queue_record(base_envelope, ca1_output)
    await write_to_embedding_queue(record)

    # P08 claims job
    await claim_embedding_job()

    # P08 marks failed (first attempt)
    success = await mark_embedding_failed("emb_uuid_abc123", "Model timeout")
    assert success is True

    # Verify status
    retrieved = get_queue_record("emb_uuid_abc123")
    assert retrieved["status"] == "FAILED_RETRYABLE"
    assert retrieved["last_error"] == "Model timeout"
    assert retrieved["next_attempt_ts"] > int(time.time())  # Backoff applied


@pytest.mark.asyncio
async def test_p08_mark_failed_permanent(base_envelope, ca1_output):
    """Test P08 marks job FAILED_PERMANENT after max retries"""
    reset_metrics()
    record = assemble_embedding_queue_record(base_envelope, ca1_output)
    record["attempt_count"] = 5  # Max attempts
    await write_to_embedding_queue(record)

    # P08 claims job
    await claim_embedding_job()

    # P08 marks failed (max retries exceeded)
    success = await mark_embedding_failed("emb_uuid_abc123", "Max retries exceeded")
    assert success is True

    # Verify status
    retrieved = get_queue_record("emb_uuid_abc123")
    assert retrieved["status"] == "FAILED_PERMANENT"
    assert retrieved["last_error"] == "Max retries exceeded"

    # Verify metrics
    metrics = get_metrics()
    assert metrics["queue_depth_failed"] == 1


@pytest.mark.asyncio
async def test_p08_exponential_backoff(base_envelope, ca1_output):
    """Test P08 exponential backoff for retries"""
    reset_metrics()
    record = assemble_embedding_queue_record(base_envelope, ca1_output)
    await write_to_embedding_queue(record)

    # Claim and fail (attempt 1)
    await claim_embedding_job()
    now1 = int(time.time())
    await mark_embedding_failed("emb_uuid_abc123", "Error 1")
    retrieved1 = get_queue_record("emb_uuid_abc123")
    backoff1 = retrieved1["next_attempt_ts"] - now1

    # Should be ~60 seconds (2^0 × 60)
    assert 55 <= backoff1 <= 65

    # Simulate claim and fail again (attempt 2)
    retrieved1["status"] = "PENDING"  # Reset for next claim
    await claim_embedding_job()
    now2 = int(time.time())
    await mark_embedding_failed("emb_uuid_abc123", "Error 2")
    retrieved2 = get_queue_record("emb_uuid_abc123")
    backoff2 = retrieved2["next_attempt_ts"] - now2

    # Should be ~120 seconds (2^1 × 60)
    assert 115 <= backoff2 <= 125


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.asyncio
async def test_error_missing_ca1_output(base_envelope):
    """Test error handling when M02 output missing"""
    reset_metrics()
    base_envelope["outputs"] = {}  # No M02 output

    result = await run(base_envelope)

    assert result["inserted"] is False
    assert result["status"] == "SKIPPED"
    assert "missing_embedding_id" in result["reason"]

    metrics = get_metrics()
    assert metrics["missing_embedding_id"] == 1


@pytest.mark.asyncio
async def test_error_missing_embedding_id_in_output(base_envelope):
    """Test error handling when embedding_id missing from M02"""
    reset_metrics()
    base_envelope["outputs"]["semantic_project"] = {
        "entities": [],
        "kg_triples": [],
    }  # No embedding_id

    result = await run(base_envelope)

    assert result["inserted"] is False
    assert result["status"] == "SKIPPED"


@pytest.mark.asyncio
async def test_error_mark_nonexistent_ready():
    """Test error handling when marking nonexistent job ready"""
    reset_metrics()

    success = await mark_embedding_ready("emb_nonexistent")
    assert success is False


# =============================================================================
# End-to-End Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_full_pipeline_p02_to_p08(base_envelope, ca1_output):
    """Test complete P02 → P08 flow"""
    reset_metrics()
    base_envelope["outputs"]["semantic_project"] = ca1_output

    # P02: Enqueue job
    result = await run(base_envelope)
    assert result["inserted"] is True

    # P08: Claim job
    job = await claim_embedding_job()
    assert job is not None
    assert job["status"] == "IN_PROGRESS"

    # P08: Mark ready
    await mark_embedding_ready(job["embedding_id"])

    # Verify final state
    final = get_queue_record(job["embedding_id"])
    assert final["status"] == "READY"


@pytest.mark.asyncio
async def test_multiple_jobs_fifo_order(base_envelope, ca1_output):
    """Test multiple jobs processed in FIFO order"""
    reset_metrics()

    # Enqueue 3 jobs
    for i in range(3):
        ca1_output["embedding_id"] = f"emb_job_{i}"
        base_envelope["outputs"]["semantic_project"] = ca1_output
        await run(base_envelope)
        time.sleep(0.01)  # Ensure different created_at

    # P08 claims in FIFO order
    job1 = await claim_embedding_job()
    job2 = await claim_embedding_job()
    job3 = await claim_embedding_job()

    assert job1["embedding_id"] == "emb_job_0"
    assert job2["embedding_id"] == "emb_job_1"
    assert job3["embedding_id"] == "emb_job_2"


@pytest.mark.asyncio
async def test_retry_after_failure(base_envelope, ca1_output):
    """Test job can be retried after failure"""
    reset_metrics()
    base_envelope["outputs"]["semantic_project"] = ca1_output

    # P02: Enqueue
    await run(base_envelope)

    # P08: Claim and fail
    job1 = await claim_embedding_job()
    await mark_embedding_failed(job1["embedding_id"], "Temporary error")

    # Verify failed status
    failed = get_queue_record(job1["embedding_id"])
    assert failed["status"] == "FAILED_RETRYABLE"

    # Simulate retry (reset status to PENDING)
    failed["status"] = "PENDING"

    # P08: Claim again (retry)
    job2 = await claim_embedding_job()
    assert job2["embedding_id"] == job1["embedding_id"]
    assert job2["attempt_count"] == 2  # Incremented


# =============================================================================
# Performance Tests
# =============================================================================


@pytest.mark.asyncio
async def test_performance_under_5ms(base_envelope, ca1_output):
    """Test embedding queue write meets <5ms P95 budget"""
    reset_metrics()
    base_envelope["outputs"]["semantic_project"] = ca1_output

    latencies = []
    for i in range(100):
        ca1_output["embedding_id"] = f"emb_perf_{i}"
        start = time.perf_counter()
        await run(base_envelope)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[49]
    p95 = latencies_sorted[94]
    p99 = latencies_sorted[98]

    print("\nEmbedding Queue Write Performance:")
    print(f"  P50: {p50:.4f}ms")
    print(f"  P95: {p95:.4f}ms")
    print(f"  P99: {p99:.4f}ms")

    assert p95 < 5.0, f"P95 latency {p95:.4f}ms exceeds 5ms budget"


@pytest.mark.asyncio
async def test_performance_batch_enqueue():
    """Test batch enqueue performance"""
    reset_metrics()

    # Prepare 100 jobs
    jobs = []
    for i in range(100):
        envelope = {
            "header": {"event_id": f"evt_{i}", "wal_pos": i},
            "outputs": {"semantic_project": {"embedding_id": f"emb_batch_{i}"}},
        }
        jobs.append(envelope)

    # Enqueue all jobs
    start = time.perf_counter()
    for envelope in jobs:
        await run(envelope)
    elapsed_ms = (time.perf_counter() - start) * 1000

    avg_ms = elapsed_ms / 100
    print("\nBatch Enqueue (100 jobs):")
    print(f"  Total: {elapsed_ms:.2f}ms")
    print(f"  Avg per job: {avg_ms:.4f}ms")

    assert avg_ms < 5.0, f"Average latency {avg_ms:.4f}ms exceeds 5ms budget"


# =============================================================================
# Metrics Tests
# =============================================================================


@pytest.mark.asyncio
async def test_metrics_tracking(base_envelope, ca1_output):
    """Test metrics are tracked correctly"""
    reset_metrics()

    # Enqueue 3 unique jobs
    for i in range(3):
        ca1_output["embedding_id"] = f"emb_metric_{i}"
        base_envelope["outputs"]["semantic_project"] = ca1_output
        await run(base_envelope)

    # Try duplicate (should skip)
    ca1_output["embedding_id"] = "emb_metric_0"
    await run(base_envelope)

    # Claim 2 jobs
    await claim_embedding_job()
    await claim_embedding_job()

    # Mark 1 ready
    await mark_embedding_ready("emb_metric_0")

    metrics = get_metrics()
    assert metrics["jobs_enqueued"] == 3
    assert metrics["duplicates_skipped"] == 1
    assert metrics["queue_depth_pending"] == 1
    assert metrics["queue_depth_in_progress"] == 1
    assert metrics["queue_depth_ready"] == 1


@pytest.mark.asyncio
async def test_metrics_reset():
    """Test metrics can be reset"""
    reset_metrics()

    metrics = get_metrics()
    assert metrics["jobs_enqueued"] == 0
    assert metrics["duplicates_skipped"] == 0
    assert metrics["queue_depth_pending"] == 0
