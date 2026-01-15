"""
M27: embedding.cleanup

Cleanup orphaned embeddings.
Removes vectors from st_vec and FAISS when parent event no longer exists.

ADR Reference: ADR-K003 (Inline Embedding via UltraBERT)
Contract: k0/contracts/modules/embedding.cleanup.v1.yaml

Flow:
1. Query st_vec for embeddings without parent events in st_hipp_events
2. Remove from FAISS index via faiss_remove_batch syscall
3. Delete from st_vec via vec_delete syscall
4. Emit cognitive.embedding.cleaned.v1 event

Performance: <2s per batch (100 orphans), parallel deletion

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
    "embeddings_cleaned": 0,
    "cleanup_failures": 0,
    "empty_batches": 0,
    "events_emitted": 0,
}


async def run(envelope: dict[str, Any], enriched: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Cleanup orphaned embeddings.

    Args:
        envelope: Event envelope with cognitive.cleanup.requested.v1 data
        enriched: Enrichment data from previous modules
        context: Execution context with syscalls and config

    Returns:
        Dictionary with:
        - cleaned_count: int (number of embeddings cleaned)
        - batch_size: int (requested batch size)
        - remaining: int (estimated remaining orphans)
        - completed: bool (True if no more orphans)

    Raises:
        ValueError: If required fields missing
        RuntimeError: If cleanup fails
    """
    # Extract configuration
    config = getattr(context, "config", {})
    batch_size = config.get("batch_size", 100)
    emit_cleaned_event = config.get("emit_cleaned_event", True)
    cleaned_event_topic = config.get("cleaned_event_topic", "cognitive.embedding.cleaned.v1")
    index_id = config.get("index_id", "ultrabert_v2.1.0_ivf256_pq64")

    # Extract event payload
    payload = envelope.get("payload", {})
    tenant_id = payload.get("tenant_id")
    space_id = payload.get("space_id")

    # Get syscalls
    syscalls = context.syscalls

    # Find orphaned embeddings (st_vec entries without parent in st_hipp_events)
    try:
        orphan_result = await syscalls.vec_find_orphans(
            tenant_id=tenant_id,
            space_id=space_id,
            limit=batch_size,
        )

        orphaned_embeddings = orphan_result.get("orphans", [])

        if not orphaned_embeddings:
            logger.info(
                "M27: No orphaned embeddings found",
                extra={"tenant_id": tenant_id, "space_id": space_id},
            )
            _metrics["empty_batches"] += 1
            return {
                "cleaned_count": 0,
                "batch_size": batch_size,
                "remaining": 0,
                "completed": True,
            }

        logger.info(
            "M27: Processing orphaned embeddings batch",
            extra={
                "tenant_id": tenant_id,
                "space_id": space_id,
                "batch_size": len(orphaned_embeddings),
            },
        )

    except Exception as e:
        _metrics["cleanup_failures"] += 1
        logger.error(
            "M27: Failed to find orphaned embeddings",
            extra={"tenant_id": tenant_id, "space_id": space_id, "error": str(e)},
        )
        raise RuntimeError(f"Failed to find orphaned embeddings: {e}") from e

    # Remove from FAISS (batch)
    embedding_ids = [orphan["embedding_id"] for orphan in orphaned_embeddings]

    try:
        faiss_result = await syscalls.faiss_remove_batch(
            embedding_ids=embedding_ids,
            index_id=index_id,
        )

        logger.info(
            "M27: Removed embeddings from FAISS",
            extra={
                "removed_count": faiss_result.get("removed_count", 0),
                "index_id": index_id,
            },
        )

    except Exception as e:
        logger.warning(
            "M27: Failed to remove from FAISS (continuing with st_vec cleanup)",
            extra={"error": str(e)},
        )

    # Delete from st_vec
    cleaned_count = 0
    failed_count = 0

    for embedding_id in embedding_ids:
        try:
            await syscalls.vec_delete(embedding_id=embedding_id)
            cleaned_count += 1
            logger.debug("M27: Deleted orphaned embedding", extra={"embedding_id": embedding_id})

        except Exception as e:
            failed_count += 1
            logger.error(
                "M27: Failed to delete embedding from st_vec",
                extra={"embedding_id": embedding_id, "error": str(e)},
            )

    # Emit cognitive.embedding.cleaned.v1 event
    if emit_cleaned_event and cleaned_count > 0:
        try:
            await syscalls.outbox_emit_batch(
                events=[
                    {
                        "topic": cleaned_event_topic,
                        "payload": {
                            "tenant_id": tenant_id,
                            "space_id": space_id,
                            "cleaned_count": cleaned_count,
                            "failed_count": failed_count,
                            "batch_size": len(orphaned_embeddings),
                            "index_id": index_id,
                            "cleaned_at": int(time.time()),
                        },
                        "event_id": f"cleanup_{tenant_id}_{int(time.time())}",
                    }
                ],
            )
            _metrics["events_emitted"] += 1

        except Exception as e:
            logger.warning(
                "M27: Failed to emit cleaned event (non-fatal)",
                extra={"error": str(e)},
            )

    _metrics["batches_processed"] += 1
    _metrics["embeddings_cleaned"] += cleaned_count
    _metrics["cleanup_failures"] += failed_count

    remaining = orphan_result.get("total_count", 0) - cleaned_count
    completed = remaining == 0

    logger.info(
        "M27: Cleanup batch complete",
        extra={
            "cleaned_count": cleaned_count,
            "failed_count": failed_count,
            "remaining": remaining,
            "completed": completed,
        },
    )

    return {
        "cleaned_count": cleaned_count,
        "batch_size": len(orphaned_embeddings),
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
