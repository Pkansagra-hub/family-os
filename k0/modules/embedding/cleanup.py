"""M27: embedding.cleanup -- pgvector-only orphan cleanup.

Cleanup orphaned embeddings from st_vec.
Pure SQL DELETE for st_vec rows without parent st_hipp_events.

ADR Reference: ADR-K003 v2.0 (Inline Embedding via UltraBERT)
Contract: k0/contracts/modules/embedding.cleanup.v2.yaml

Flow:
1. Count orphaned st_vec rows (NOT EXISTS st_hipp_events)
2. Batch DELETE orphaned rows (LIMIT for safety)
3. Emit cognitive.embedding.cleaned.v1 event

Performance: <2s per batch (500 deletes), pure SQL

Version: 2.0.0
Last Updated: 2025-06-30
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


async def run(
    message: Any, context: Any, envelope: dict[str, Any] | None = None, **config: Any
) -> dict[str, Any]:
    """
    Cleanup orphaned embeddings via pure SQL DELETE.

    Removes st_vec rows where event_id has no matching st_hipp_events row.
    No FAISS index manipulation -- pgvector HNSW auto-maintains.

    Args:
        message: BusMessage (trigger message from scheduler or bus)
        context: Execution context with syscalls and config
        envelope: Event envelope (optional, for scoped cleanup)
        **config: Stage configuration:
            - batch_size: int (default: 500)
            - dry_run: bool (default: False)
            - emit_cleaned_event: bool (default: True)

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
    # Extract configuration from **config (stage config) or context.config
    ctx_config = getattr(context, "config", {})
    batch_size = config.get("batch_size", ctx_config.get("batch_size", 500))
    emit_cleaned_event = config.get(
        "emit_cleaned_event", ctx_config.get("emit_cleaned_event", True)
    )
    cleaned_event_topic = config.get(
        "cleaned_event_topic",
        ctx_config.get("cleaned_event_topic", "cognitive.embedding.cleaned.v1"),
    )
    dry_run = config.get("dry_run", ctx_config.get("dry_run", False))

    # Extract event payload from envelope
    if envelope:
        payload = envelope.get("payload", {})
    else:
        payload = {}
    tenant_id = payload.get("tenant_id")
    space_id = payload.get("space_id")

    # Get syscalls
    syscalls = context.syscalls

    # Count orphaned embeddings first (for metrics/reporting)
    try:
        orphan_count_result = await syscalls.vec_orphan_count(
            tenant_id=tenant_id,
            space_id=space_id,
        )
        total_orphans = orphan_count_result.get("count", 0)

        if total_orphans == 0:
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
                "dry_run": dry_run,
            }

        logger.info(
            "M27: Found orphaned embeddings",
            extra={
                "tenant_id": tenant_id,
                "space_id": space_id,
                "total_orphans": total_orphans,
                "dry_run": dry_run,
            },
        )

    except Exception as e:
        _metrics["cleanup_failures"] += 1
        logger.error(
            "M27: Failed to count orphaned embeddings",
            extra={"tenant_id": tenant_id, "space_id": space_id, "error": str(e)},
        )
        raise RuntimeError(f"Failed to count orphaned embeddings: {e}") from e

    if dry_run:
        logger.info("M27: Dry run -- no deletes executed", extra={"total_orphans": total_orphans})
        return {
            "cleaned_count": 0,
            "batch_size": batch_size,
            "remaining": total_orphans,
            "completed": False,
            "dry_run": True,
        }

    # Batch DELETE orphaned st_vec rows (pure SQL, no FAISS)
    # DELETE FROM st_vec WHERE NOT EXISTS (SELECT 1 FROM st_hipp_events ...) LIMIT batch_size
    try:
        delete_result = await syscalls.vec_delete_orphans(
            tenant_id=tenant_id,
            space_id=space_id,
            limit=batch_size,
        )
        cleaned_count = delete_result.get("deleted_count", 0)

    except Exception as e:
        _metrics["cleanup_failures"] += 1
        logger.error(
            "M27: Failed to delete orphaned embeddings",
            extra={"tenant_id": tenant_id, "space_id": space_id, "error": str(e)},
        )
        raise RuntimeError(f"Failed to delete orphaned embeddings: {e}") from e

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
                            "batch_size": batch_size,
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

    remaining = max(0, total_orphans - cleaned_count)
    completed = remaining == 0

    logger.info(
        "M27: Cleanup batch complete",
        extra={
            "cleaned_count": cleaned_count,
            "remaining": remaining,
            "completed": completed,
        },
    )

    return {
        "cleaned_count": cleaned_count,
        "batch_size": batch_size,
        "remaining": remaining,
        "completed": completed,
        "dry_run": False,
    }


def get_metrics() -> dict[str, int]:
    """
    Get module metrics for observability.

    Returns:
        Dictionary with metric counters
    """
    return dict(_metrics)


def reset_metrics() -> None:
    """Reset metrics counters (for testing)."""
    for key in _metrics:
        _metrics[key] = 0
