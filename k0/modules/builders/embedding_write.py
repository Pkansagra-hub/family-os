"""
DEPRECATED: M23 builders.embedding_write

This module is deprecated as of ADR-K003 v1.2 (2025-12-13).
Embedding writes are now handled atomically in M16 (hipp_events_writer).

Migration: Remove stage_61 from P02 DAG, M16 handles both st_hipp_events + st_vec tables.

---

Original Purpose (pre-deprecation):
Writes 768-dim embedding directly to st_vec table (inline with P02).
Performance: <5ms P95 (single INSERT with 3KB blob)

ADR Reference: ADR-K003 (Inline Embedding via UltraBERT)
Contract: k0/contracts/modules/builders.embedding_write.v1.yaml

Reason for Deprecation:
- FK ordering violation: M23 wrote st_vec BEFORE st_hipp_events existed
- Transaction atomicity: M16 now writes both tables in single UoW
- Simplified DAG: Fewer stages, cleaner dependency graph
"""

import warnings

warnings.warn(
    "M23 embedding_write is deprecated as of ADR-K003 v1.2. "
    "Use M16 hipp_events_writer instead (atomic 3-table write).",
    DeprecationWarning,
    stacklevel=2,
)

import logging
import struct
import time
from typing import Any

logger = logging.getLogger(__name__)

# Module metrics
_metrics = {
    "embeddings_written": 0,
    "embeddings_pending": 0,
    "invalid_dimensions": 0,
    "write_failures": 0,
    "events_emitted": 0,
}


async def run(message: Any, context: Any, **config: Any) -> dict[str, Any]:
    """
    Write embedding directly to st_vec table.

    Args:
        message: BusMessage with .payload (bytes) containing envelope JSON
        context: PipelineContext with syscalls, logger, config
        **config: Stage configuration (envelope, emit_stored_event, validate_vector_dim, etc.)

    Returns:
        Dictionary with:
        - written: bool (True if st_vec insert succeeded)
        - embedding_id: str (UUID) or None
        - embedding_status: str ('READY' | 'PENDING')
        - vector_dim: int (768)
    """
    # Extract envelope and enriched data from config
    envelope = config.get("envelope", {})

    # Extract configuration
    emit_event = config.get("emit_stored_event", True)
    validate_dim = config.get("validate_vector_dim", True)
    set_pending_on_missing = config.get("set_pending_on_missing", True)
    stored_event_topic = config.get("stored_event_topic", "cognitive.vector.stored.v1")

    # Extract embedding data from M22 output (merged into envelope by pipeline runner)
    embedding = envelope.get("embedding")
    embedding_id = envelope.get("embedding_id")
    model_id = envelope.get("model_id", "ultrabert_v2.1.0")

    # Extract envelope metadata (envelope is flat, no header nesting)
    event_id = envelope.get(
        "cognitive_trace_id"
    )  # cognitive_trace_id IS the event_id per P02 dossier
    tenant_id = envelope.get("tenant_id")
    space_id = envelope.get("space_id")

    # Validate required fields
    if not event_id:
        logger.error("M23: Missing event_id in envelope header")
        raise ValueError("event_id required for embedding write")

    if not tenant_id:
        logger.error("M23: Missing tenant_id in envelope header")
        raise ValueError("tenant_id required for embedding write")

    if not space_id:
        logger.error("M23: Missing space_id in envelope header")
        raise ValueError("space_id required for embedding write")

    # Handle missing embedding (graceful degradation)
    if not embedding or embedding_id is None:
        if set_pending_on_missing:
            _metrics["embeddings_pending"] += 1
            logger.info(
                "M23: No embedding data, setting status=PENDING for P08 backfill",
                extra={
                    "event_id": event_id,
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "embedding_status": "PENDING",
                },
            )
            return {
                "written": False,
                "embedding_id": None,
                "embedding_status": "PENDING",
                "vector_dim": 768,
            }
        else:
            logger.warning("M23: No embedding data and set_pending_on_missing=False, skipping")
            return {
                "written": False,
                "embedding_id": None,
                "embedding_status": "SKIPPED",
                "vector_dim": 768,
            }

    # Validate vector dimension
    if validate_dim and len(embedding) != 768:
        _metrics["invalid_dimensions"] += 1
        logger.error(
            "M23: Invalid embedding dimension, dropping",
            extra={
                "event_id": event_id,
                "expected_dim": 768,
                "actual_dim": len(embedding),
                "embedding_id": embedding_id,
            },
        )
        raise ValueError(f"Invalid embedding dimension: {len(embedding)} (expected 768)")

    # Convert embedding to bytes (768 floats × 4 bytes = 3072 bytes)
    try:
        vector_bytes = struct.pack("768f", *embedding)
    except struct.error as e:
        _metrics["invalid_dimensions"] += 1
        logger.error(
            "M23: Failed to pack embedding vector",
            extra={
                "event_id": event_id,
                "embedding_id": embedding_id,
                "error": str(e),
            },
        )
        raise ValueError(f"Failed to pack embedding vector: {e}")

    # Write to st_vec via syscall
    syscalls = context.syscalls
    try:
        result = await syscalls.vec_write(
            embedding_id=embedding_id,
            event_id=event_id,
            tenant_id=tenant_id,
            space_id=space_id,
            vector=vector_bytes,
            vector_dim=768,
            model_id=model_id,
            status="READY",
            cognitive_trace_id=event_id,  # event_id == cognitive_trace_id
        )

        if result.get("inserted"):
            _metrics["embeddings_written"] += 1
            logger.debug(
                "M23: Embedding written to st_vec",
                extra={
                    "embedding_id": embedding_id,
                    "event_id": event_id,
                    "space_id": space_id,
                    "model_id": model_id,
                    "vector_dim": 768,
                    "status": "READY",
                },
            )
        else:
            logger.debug(
                "M23: Duplicate embedding_id, skipped",
                extra={
                    "embedding_id": embedding_id,
                    "event_id": event_id,
                    "status": result.get("status"),
                },
            )

    except Exception as e:
        _metrics["write_failures"] += 1
        logger.error(
            "M23: Failed to write embedding to st_vec",
            extra={
                "embedding_id": embedding_id,
                "event_id": event_id,
                "error": str(e),
            },
        )
        raise

    # Emit cognitive.vector.stored.v1 event directly to internal bus (for P08 M24 FAISS indexing)
    if emit_event:
        try:
            import json

            from k0.bus.core import BusMessage

            event_payload = {
                "embedding_id": embedding_id,
                "event_id": event_id,
                "model_id": model_id,
                "vector_dim": 768,
                "stored_at": int(time.time()),
                "status": "READY",
                "tenant_id": tenant_id,
                "space_id": space_id,
            }

            # Emit directly to bus (internal pipeline communication - no outbox needed)
            bus_message = BusMessage(
                topic=stored_event_topic,
                payload=json.dumps(event_payload).encode("utf-8"),
                offset=0,
                trace_id=event_id,
                space_id=space_id,
            )

            # Get bus dispatcher from context and dispatch
            bus_dispatcher = getattr(context, "bus_dispatcher", None)
            if bus_dispatcher:
                await bus_dispatcher.dispatch([bus_message])
                _metrics["events_emitted"] += 1
                logger.info(
                    "M23: Emitted cognitive.vector.stored event to internal bus",
                    extra={
                        "topic": stored_event_topic,
                        "embedding_id": embedding_id,
                        "event_id": event_id,
                    },
                )

        except Exception as e:
            # Event emission failure is non-fatal (embedding is stored)
            logger.warning(
                "M23: Failed to emit cognitive.vector.stored event (non-fatal)",
                extra={
                    "embedding_id": embedding_id,
                    "event_id": event_id,
                    "error": str(e),
                },
            )

    return {
        "written": True,
        "embedding_id": embedding_id,
        "embedding_status": "READY",
        "vector_dim": 768,
    }


def get_metrics() -> dict[str, int]:
    """
    Get module metrics for observability.

    Returns:
        Dictionary with metric counters
    """
    return dict(_metrics)


def reset_metrics() -> None:
    """
    Reset metrics counters (for testing).
    """
    for key in _metrics:
        _metrics[key] = 0
        _metrics[key] = 0
        _metrics[key] = 0
