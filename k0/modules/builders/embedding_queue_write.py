"""
Embedding Queue Writer Module (M14)

Enqueues embedding generation jobs to st_embedding_queue for P08 background processing.

**Purpose**: Decouple fast memory writes (P02) from slow vector computation (P08).
P02 writes PENDING jobs, P08 picks them up asynchronously.

**Performance**: <5ms P95 (single row INSERT with indexed PK)

**Contract**: k0/contracts/modules/builders.embedding_queue_write.v1.yaml
**ADR**: docs/architecture/decisions-K0/modules/k009.2-embedding-queue-writer.md
**Schema**: docs/pipelines/P02_data_schema.md (lines 275-355)

**Inputs**:
- M02 (semantic_project): embedding_id, entities, kg_triples
- M13 (hipp_events_row): event_id, wal_pos, tenant_id, space_id

**Output**: st_embedding_queue row with status=PENDING

**Status Lifecycle** (P08 updates these):
1. PENDING: Initial state (written by P02)
2. IN_PROGRESS: Claimed by P08 worker
3. READY: Vector computed and stored
4. FAILED_RETRYABLE: Computation failed, will retry
5. FAILED_PERMANENT: Max retries exceeded

**Idempotency**: Uses embedding_id as PRIMARY KEY with INSERT OR IGNORE.
Duplicate embedding_id triggers skip (no error).

**Version**: 1.0.0
**Last Updated**: 2025-11-17
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

# =============================================================================
# In-Memory Simulated Database (for testing)
# =============================================================================

_embedding_queue_db: Dict[str, Dict[str, Any]] = {}


# =============================================================================
# Metrics Tracking
# =============================================================================


@dataclass
class QueueMetrics:
    """Metrics for embedding queue operations"""

    jobs_enqueued: int = 0
    duplicates_skipped: int = 0
    insert_failures: int = 0
    missing_embedding_id: int = 0


_metrics = QueueMetrics()


# =============================================================================
# Queue Record Assembly
# =============================================================================


def assemble_embedding_queue_record(
    envelope: Dict[str, Any],
    ca1_output: Dict[str, Any],
    priority: str = "NORMAL",
    model_id: str = "embed-mini-001",
) -> Dict[str, Any]:
    """
    Assemble st_embedding_queue record from CA1 output and envelope.

    Args:
        envelope: Envelope with header and body
        ca1_output: M02 semantic_project output (contains embedding_id)
        priority: Job priority ('LOW'|'NORMAL'|'HIGH', default: 'NORMAL')
        model_id: Embedding model ID (default: 'embed-mini-001')

    Returns:
        Dictionary with embedding queue fields

    Raises:
        ValueError: If embedding_id missing
    """
    embedding_id = ca1_output.get("embedding_id")
    if not embedding_id:
        _metrics.missing_embedding_id += 1
        raise ValueError("Missing embedding_id from CA1 semantic projection")

    header = envelope.get("header", {})

    now = int(time.time())

    return {
        "job_id": None,  # Auto-increment in database
        "embedding_id": embedding_id,
        "event_id": header.get("event_id"),
        "wal_pos": header.get("wal_pos"),
        "tenant_id": header.get("tenant_id"),
        "space_id": header.get("space_id"),
        "vector_kind": "memory.body.text",  # Default for P02 (text embeddings)
        "model_id": model_id,  # Configurable model
        "priority": priority,  # Configurable priority
        "status": "PENDING",  # Initial status for P02
        "attempt_count": 0,  # No attempts yet
        "max_attempts": 5,  # Default max retries
        "next_attempt_ts": now,  # Immediate processing
        "last_error": None,  # No errors yet
        "created_at": now,
        "updated_at": now,
    }


# =============================================================================
# Database Write (Idempotent)
# =============================================================================


async def write_to_embedding_queue(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Write embedding queue record to st_embedding_queue.

    Uses INSERT OR IGNORE for idempotency (duplicate embedding_id skipped).

    Args:
        record: Embedding queue record from assemble_embedding_queue_record()

    Returns:
        Dictionary with:
        - inserted: bool (True if inserted, False if duplicate skipped)
        - embedding_id: str
        - status: str

    Raises:
        RuntimeError: If database write fails (non-duplicate error)
    """
    embedding_id = record["embedding_id"]

    # Simulate INSERT OR IGNORE (idempotent)
    if embedding_id in _embedding_queue_db:
        # Duplicate embedding_id - skip
        _metrics.duplicates_skipped += 1
        return {
            "inserted": False,
            "embedding_id": embedding_id,
            "status": "SKIPPED_DUPLICATE",
            "reason": "embedding_id already exists in queue",
        }

    # Insert new record
    try:
        _embedding_queue_db[embedding_id] = record.copy()
        _metrics.jobs_enqueued += 1

        return {
            "inserted": True,
            "embedding_id": embedding_id,
            "status": "PENDING",
            "created_at": record["created_at"],
        }
    except Exception as e:
        _metrics.insert_failures += 1
        raise RuntimeError(f"Failed to write to embedding queue: {e}")


# =============================================================================
# Main Module Entry Point
# =============================================================================


async def run(message: Any, context: Any, **config: Any) -> Dict[str, Any]:
    """
    Enqueue embedding generation job for P08 background processing.

    **Phase 2 Signature**:
        message: BusMessage with .payload (envelope JSON) and .trace_id
        context: PipelineContext with .logger and .syscalls
        **config: Stage configuration
            - priority (str): Job priority ('LOW'|'NORMAL'|'HIGH', default: 'NORMAL')
            - model_id (str): Embedding model ID (default: 'embed-mini-001')

    **Required Inputs** (from envelope['outputs']):
    - semantic_project (M02): embedding_id

    Returns:
        Enriched envelope with "embedding_queue_write" containing:
        - inserted: bool (True if enqueued, False if duplicate skipped)
        - embedding_id: str
        - status: str ('PENDING' or 'SKIPPED_DUPLICATE')

    Raises:
        ValueError: If embedding_id missing from M02 output
        RuntimeError: If database write fails
    """
    import json

    # Use enriched envelope from config (passed by pipeline runner)
    # Falls back to parsing from message.payload if not available (for backward compat)
    envelope = config.get("envelope")
    if envelope is None:
        envelope = (
            json.loads(message.payload)
            if isinstance(message.payload, (str, bytes))
            else message.payload
        )

    # Extract configuration
    priority = config.get("priority", "NORMAL")
    model_id = config.get("model_id", "embed-mini-001")

    # Log start
    context.logger.debug(
        "M14 embedding_queue_write starting",
        extra={
            "trace_id": message.trace_id,
            "event_id": envelope.get("header", {}).get("event_id"),
            "priority": priority,
        },
    )

    # Phase 3: Extract from nested enrichments, fallback to flat
    enrichments = envelope.get("enrichments", {})
    ca1_enrichment = enrichments.get("hippocampus_semantic_project", {})

    embedding_id = ca1_enrichment.get("embedding_id") or envelope.get("embedding_id")

    if not embedding_id:
        _metrics.missing_embedding_id += 1
        context.logger.warning(
            "M14 skipping - missing embedding_id from CA1", extra={"trace_id": message.trace_id}
        )
        return {
            **envelope,
            "embedding_queue_write": {
                "inserted": False,
                "status": "SKIPPED",
                "reason": "missing_embedding_id_from_ca1",
            },
        }

    # Build CA1 output dict (prefer nested, fallback to flat)
    ca1_output = {
        "embedding_id": embedding_id,
        "entities_json": ca1_enrichment.get("entities_json") or envelope.get("entities_json", "[]"),
        "kg_triples_json": ca1_enrichment.get("kg_triples_json")
        or envelope.get("kg_triples_json", "[]"),
    }

    # Assemble embedding queue record (using config values)
    record = assemble_embedding_queue_record(envelope, ca1_output, priority, model_id)

    # Write to st_embedding_queue (idempotent)
    result = await write_to_embedding_queue(record)

    # Log completion
    context.logger.debug(
        "M14 embedding_queue_write completed",
        extra={
            "trace_id": message.trace_id,
            "embedding_id": result.get("embedding_id"),
            "inserted": result.get("inserted"),
        },
    )

    return {**envelope, "embedding_queue_write": result}


# =============================================================================
# P08 Helper Functions (for testing/integration)
# =============================================================================


async def claim_embedding_job() -> Optional[Dict[str, Any]]:
    """
    P08 worker claims next PENDING job.

    Simulates:
    ```sql
    SELECT * FROM st_embedding_queue
    WHERE status = 'PENDING'
    ORDER BY created_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
    ```

    Returns:
        Job record if found, None otherwise
    """
    now = int(time.time())

    # Find first PENDING job
    for embedding_id, record in sorted(
        _embedding_queue_db.items(), key=lambda x: x[1]["created_at"]
    ):
        if record["status"] == "PENDING":
            # Claim job
            record["status"] = "IN_PROGRESS"
            record["attempt_count"] += 1
            record["updated_at"] = now
            return record.copy()

    return None


async def mark_embedding_ready(embedding_id: str) -> bool:
    """
    P08 marks job complete after vector stored.

    Args:
        embedding_id: Job to mark ready

    Returns:
        True if updated, False if not found
    """
    if embedding_id not in _embedding_queue_db:
        return False

    record = _embedding_queue_db[embedding_id]
    record["status"] = "READY"
    record["updated_at"] = int(time.time())
    return True


async def mark_embedding_failed(embedding_id: str, error_message: str) -> bool:
    """
    P08 marks job failed after error.

    Args:
        embedding_id: Job to mark failed
        error_message: Error description

    Returns:
        True if updated, False if not found
    """
    if embedding_id not in _embedding_queue_db:
        return False

    record = _embedding_queue_db[embedding_id]
    record["last_error"] = error_message
    record["updated_at"] = int(time.time())

    # Check if max attempts exceeded
    if record["attempt_count"] >= record["max_attempts"]:
        record["status"] = "FAILED_PERMANENT"
    else:
        record["status"] = "FAILED_RETRYABLE"
        # Exponential backoff: next_attempt_ts = now + (2^(attempt_count-1) × 60s)
        backoff_seconds = (2 ** (record["attempt_count"] - 1)) * 60
        record["next_attempt_ts"] = int(time.time()) + backoff_seconds

    return True


# =============================================================================
# Metrics & Observability
# =============================================================================


def get_metrics() -> Dict[str, Any]:
    """Return current metrics for observability"""
    return {
        "jobs_enqueued": _metrics.jobs_enqueued,
        "duplicates_skipped": _metrics.duplicates_skipped,
        "insert_failures": _metrics.insert_failures,
        "missing_embedding_id": _metrics.missing_embedding_id,
        "queue_depth_pending": sum(
            1 for r in _embedding_queue_db.values() if r["status"] == "PENDING"
        ),
        "queue_depth_in_progress": sum(
            1 for r in _embedding_queue_db.values() if r["status"] == "IN_PROGRESS"
        ),
        "queue_depth_ready": sum(1 for r in _embedding_queue_db.values() if r["status"] == "READY"),
        "queue_depth_failed": sum(
            1
            for r in _embedding_queue_db.values()
            if r["status"] in ["FAILED_RETRYABLE", "FAILED_PERMANENT"]
        ),
    }


def reset_metrics() -> None:
    """Reset metrics (for testing)"""
    global _metrics, _embedding_queue_db
    _metrics = QueueMetrics()
    _embedding_queue_db = {}


def get_queue_record(embedding_id: str) -> Optional[Dict[str, Any]]:
    """
    Get queue record by embedding_id (for testing).

    Args:
        embedding_id: Embedding ID to lookup

    Returns:
        Queue record if found, None otherwise
    """
    return _embedding_queue_db.get(embedding_id)
