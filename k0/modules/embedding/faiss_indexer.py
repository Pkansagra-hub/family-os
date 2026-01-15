"""
M24: embedding.faiss_indexer

FAISS index management for vector similarity search.
Supports both scheduled batch mode and single embedding mode.

ADR Reference: ADR-K003 v1.2 (Inline Embedding via UltraBERT)
Contract: k0/contracts/modules/embedding.faiss_indexer.v1.yaml

Architecture (ADR-K003 v1.2 Update):
- P02 M16 writes vector to st_vec with status=READY (atomic with st_hipp_events)
- P08 runs as scheduled batch job (every 5 minutes)
- P08 M24 queries st_vec WHERE status='READY' via vec_query syscall
- P08 M24 adds vectors to FAISS index via faiss_add syscall
- P08 M24 updates st_vec.status to INDEXED via vec_update_status syscall

Trigger Modes:
1. Scheduled Batch: Query st_vec WHERE status='READY', process in batch
2. Single Embedding: Process specific embedding_id (manual/debug mode)

Performance:
- <50ms P95 per vector (single indexing)
- <500ms P95 per batch of 100 vectors

Security:
- Uses syscalls exclusively (no raw SQLite connections)
- Requires capabilities: st_vec.read, st_vec.write, faiss.write

Version: 2.0.0 (ADR-K003 v1.2 - Syscall-based)
Last Updated: 2025-12-13
"""

import logging
import struct
import time
from typing import Any

logger = logging.getLogger(__name__)

# Module metrics
_metrics = {
    "vectors_indexed": 0,
    "indexing_failures": 0,
    "missing_vectors": 0,
    "invalid_dimensions": 0,
    "batches_processed": 0,
    "empty_batches": 0,
}


async def run(message: Any, context: Any, **config: Any) -> dict[str, Any]:
    """
    Index READY embeddings in FAISS for similarity search.

    Supports two trigger modes:
    1. Scheduled Batch: Query st_vec WHERE status='READY', batch process
    2. Single Embedding: Process specific embedding_id from config

    Args:
        message: BusMessage (optional, not used in scheduled mode)
        context: PipelineContext with syscalls, logger, config
        **config: Stage configuration:
            - batch_size: int (default: 100) - Max embeddings per batch
            - embedding_id: str (optional) - Single embedding mode
            - index_id: str (default: ultrabert_v2.1.0_ivf256_pq64)
            - tenant_id: str (optional) - Filter by tenant
            - space_id: str (optional) - Filter by space

    Returns:
        Dictionary with:
        - indexed: int (count of vectors indexed)
        - batch_size: int (embeddings processed)
        - failures: int (failed indexing attempts)
        - empty: bool (True if no READY embeddings found)

    Raises:
        RuntimeError: If critical failure occurs
    """
    # Get configuration
    batch_size = config.get("batch_size", 100)
    single_embedding_id = config.get("embedding_id")  # For single-mode
    index_id = config.get("index_id", "ultrabert_v2.1.0_ivf256_pq64")
    tenant_id = config.get("tenant_id")
    space_id = config.get("space_id")

    # Get syscalls
    syscalls = context.syscalls

    # Determine mode and get embeddings
    if single_embedding_id:
        # Single embedding mode (for manual/debug trigger)
        logger.info(
            "M24: Single embedding mode",
            extra={"embedding_id": single_embedding_id},
        )
        embeddings = await _get_single_embedding(syscalls, single_embedding_id)
    else:
        # Batch mode (for scheduled trigger)
        logger.info(
            "M24: Batch mode",
            extra={"batch_size": batch_size, "tenant_id": tenant_id, "space_id": space_id},
        )
        result = await syscalls.vec_query(
            status="READY",
            tenant_id=tenant_id,
            space_id=space_id,
            limit=batch_size,
        )
        embeddings = result["embeddings"]

        logger.info(
            "M24: Found READY embeddings",
            extra={
                "count": len(embeddings),
                "total": result["total"],
            },
        )

    # Handle empty result
    if not embeddings:
        _metrics["empty_batches"] += 1
        logger.debug("M24: No READY embeddings found")
        return {
            "indexed": 0,
            "batch_size": 0,
            "failures": 0,
            "empty": True,
            "message": "No READY embeddings found",
        }

    # Process embeddings
    indexed_count = 0
    failure_count = 0

    for emb in embeddings:
        embedding_id = emb["embedding_id"]
        vector_bytes = emb["vector"]
        event_id = emb.get("event_id")

        try:
            # Validate vector bytes
            if not vector_bytes or len(vector_bytes) != 3072:
                _metrics["invalid_dimensions"] += 1
                logger.warning(
                    "M24: Invalid vector bytes",
                    extra={
                        "embedding_id": embedding_id,
                        "expected_bytes": 3072,
                        "actual_bytes": len(vector_bytes) if vector_bytes else 0,
                    },
                )
                failure_count += 1
                continue

            # Unpack vector from bytes (768 floats x 4 bytes = 3072 bytes)
            vector = list(struct.unpack("768f", vector_bytes))

            # Validate dimension
            if len(vector) != 768:
                _metrics["invalid_dimensions"] += 1
                logger.warning(
                    "M24: Invalid vector dimension",
                    extra={
                        "embedding_id": embedding_id,
                        "expected_dim": 768,
                        "actual_dim": len(vector),
                    },
                )
                failure_count += 1
                continue

            # Add to FAISS via syscall
            faiss_result = await syscalls.faiss_add(
                embedding_id=embedding_id,
                vector=vector,
                index_id=index_id,
            )

            logger.debug(
                "M24: Vector added to FAISS",
                extra={
                    "embedding_id": embedding_id,
                    "index_id": index_id,
                    "total_vectors": faiss_result.get("total_vectors"),
                },
            )

            # Update st_vec status to INDEXED via syscall
            now = int(time.time())
            await syscalls.vec_update_status(
                embedding_id=embedding_id,
                status="INDEXED",
                indexed_at=now,
            )

            logger.debug(
                "M24: Updated st_vec status to INDEXED",
                extra={
                    "embedding_id": embedding_id,
                    "indexed_at": now,
                },
            )

            indexed_count += 1
            _metrics["vectors_indexed"] += 1

        except Exception as e:
            failure_count += 1
            _metrics["indexing_failures"] += 1
            logger.error(
                "M24: Failed to index embedding",
                extra={
                    "embedding_id": embedding_id,
                    "event_id": event_id,
                    "error": str(e),
                },
            )
            # Continue processing remaining embeddings (non-fatal for batch)
            continue

    _metrics["batches_processed"] += 1

    logger.info(
        "M24: Batch complete",
        extra={
            "indexed": indexed_count,
            "failures": failure_count,
            "batch_size": len(embeddings),
        },
    )

    return {
        "indexed": indexed_count,
        "batch_size": len(embeddings),
        "failures": failure_count,
        "empty": False,
    }


async def _get_single_embedding(
    syscalls: Any,
    embedding_id: str,
) -> list[dict[str, Any]]:
    """
    Get a single embedding by ID for manual/debug mode.

    Uses vec_query with limit=1 and then filters by embedding_id.
    (A more efficient vec_get_by_id syscall could be added later.)

    Args:
        syscalls: Syscalls instance
        embedding_id: Embedding to retrieve

    Returns:
        List with single embedding dict, or empty list if not found
    """
    # Query for this specific embedding
    # Note: vec_query doesn't have embedding_id filter, so we query READY and filter
    # For production, consider adding a vec_get_by_id syscall
    result = await syscalls.vec_query(limit=1000)  # Get a batch to search

    for emb in result["embeddings"]:
        if emb["embedding_id"] == embedding_id:
            return [emb]

    # Not found
    _metrics["missing_vectors"] += 1
    logger.warning(
        "M24: Embedding not found",
        extra={"embedding_id": embedding_id},
    )
    return []


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
