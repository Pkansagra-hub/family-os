"""
M25: embedding.backfill

Backfill PENDING embeddings for legacy events.
Reads st_hipp_events WHERE embedding_status=PENDING, computes embeddings, writes to st_vec.

ADR Reference: ADR-K003 (Inline Embedding via UltraBERT)
Contract: k0/contracts/modules/embedding.backfill.v1.yaml

Flow:
1. Query st_hipp_events WHERE embedding_status=PENDING (batch of 100)
2. Compute embeddings via UltraBERT (batch inference)
3. Write to st_vec via vec_write syscall
4. Update st_hipp_events.embedding_status to READY
5. Emit cognitive.embedding.backfilled.v1 event

Performance: <5s per batch (100 events), parallel embedding computation

Version: 1.0.0
Last Updated: 2025-12-13
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Module metrics
_metrics = {
    "batches_processed": 0,
    "embeddings_backfilled": 0,
    "backfill_failures": 0,
    "empty_batches": 0,
    "events_emitted": 0,
}


async def run(envelope: dict[str, Any], enriched: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Backfill PENDING embeddings for legacy events.

    Args:
        envelope: Event envelope with cognitive.backfill.requested.v1 data
        enriched: Enrichment data from previous modules
        context: Execution context with syscalls and config

    Returns:
        Dictionary with:
        - backfilled_count: int (number of embeddings backfilled)
        - batch_size: int (requested batch size)
        - remaining: int (estimated remaining PENDING events)
        - completed: bool (True if no more PENDING events)

    Raises:
        ValueError: If required fields missing
        RuntimeError: If backfill fails
    """
    # Extract configuration
    config = getattr(context, "config", {})
    batch_size = config.get("batch_size", 100)
    emit_backfilled_event = config.get("emit_backfilled_event", True)
    backfilled_event_topic = config.get(
        "backfilled_event_topic", "cognitive.embedding.backfilled.v1"
    )
    model_id = config.get("model_id", "ultrabert_v2.1.0")

    # Extract event payload
    payload = envelope.get("payload", {})
    tenant_id = payload.get("tenant_id")
    space_id = payload.get("space_id")

    # Get syscalls
    syscalls = context.syscalls

    # Query PENDING events (batch of 100)
    try:
        query_result = await syscalls.hipp_events_query(
            tenant_id=tenant_id,
            space_id=space_id,
            embedding_status="PENDING",
            limit=batch_size,
        )

        pending_events = query_result.get("events", [])

        if not pending_events:
            logger.info(
                "M25: No PENDING events found", extra={"tenant_id": tenant_id, "space_id": space_id}
            )
            _metrics["empty_batches"] += 1
            return {
                "backfilled_count": 0,
                "batch_size": batch_size,
                "remaining": 0,
                "completed": True,
            }

        logger.info(
            "M25: Processing PENDING events batch",
            extra={
                "tenant_id": tenant_id,
                "space_id": space_id,
                "batch_size": len(pending_events),
            },
        )

    except Exception as e:
        _metrics["backfill_failures"] += 1
        logger.error(
            "M25: Failed to query PENDING events",
            extra={"tenant_id": tenant_id, "space_id": space_id, "error": str(e)},
        )
        raise RuntimeError(f"Failed to query PENDING events: {e}") from e

    # Compute embeddings (batch inference via UltraBERT)
    backfilled_count = 0
    failed_count = 0

    for event in pending_events:
        event_id = event.get("event_id")
        event_text = event.get("event_text", "")

        if not event_text:
            logger.warning(
                "M25: Skipping event with no text",
                extra={"event_id": event_id},
            )
            continue

        try:
            # Compute embedding via ultrabert_embed syscall
            embed_result = await syscalls.ultrabert_embed(
                text=event_text,
                model_id=model_id,
            )

            embedding = embed_result.get("embedding")
            embedding_id = embed_result.get("embedding_id")

            if not embedding:
                logger.warning(
                    "M25: Embedding computation returned None",
                    extra={"event_id": event_id},
                )
                continue

            # Write to st_vec
            await syscalls.vec_write(
                embedding_id=embedding_id,
                event_id=event_id,
                tenant_id=tenant_id,
                space_id=space_id,
                vector=embedding,
                vector_dim=len(embedding),
                model_id=model_id,
                embedding_status="READY",
            )

            # Update st_hipp_events.embedding_status
            await syscalls.hipp_events_update_embedding_status(
                event_id=event_id,
                embedding_status="READY",
            )

            backfilled_count += 1
            logger.debug(
                "M25: Backfilled embedding",
                extra={"event_id": event_id, "embedding_id": embedding_id},
            )

        except Exception as e:
            failed_count += 1
            logger.error(
                "M25: Failed to backfill embedding",
                extra={"event_id": event_id, "error": str(e)},
            )

    # Emit cognitive.embedding.backfilled.v1 event
    if emit_backfilled_event and backfilled_count > 0:
        try:
            await syscalls.outbox_emit_batch(
                events=[
                    {
                        "topic": backfilled_event_topic,
                        "payload": {
                            "tenant_id": tenant_id,
                            "space_id": space_id,
                            "backfilled_count": backfilled_count,
                            "failed_count": failed_count,
                            "batch_size": len(pending_events),
                            "model_id": model_id,
                            "backfilled_at": int(time.time()),
                        },
                        "event_id": f"backfill_{tenant_id}_{int(time.time())}",
                    }
                ],
            )
            _metrics["events_emitted"] += 1

        except Exception as e:
            logger.warning(
                "M25: Failed to emit backfilled event (non-fatal)",
                extra={"error": str(e)},
            )

    _metrics["batches_processed"] += 1
    _metrics["embeddings_backfilled"] += backfilled_count
    _metrics["backfill_failures"] += failed_count

    remaining = query_result.get("total_count", 0) - backfilled_count
    completed = remaining == 0

    logger.info(
        "M25: Backfill batch complete",
        extra={
            "backfilled_count": backfilled_count,
            "failed_count": failed_count,
            "remaining": remaining,
            "completed": completed,
        },
    )

    return {
        "backfilled_count": backfilled_count,
        "batch_size": len(pending_events),
        "remaining": remaining,
        "completed": completed,
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
