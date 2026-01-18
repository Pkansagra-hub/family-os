"""
P08 UnionIndex Rebuild Job - GAP-001 Milestone 4 (Issue 4.5)

Scheduled job that rebuilds FAISS union index from truth layers.
Runs every 6 hours (configurable).

GAP Reference: GAP_001 Section 7 (Phase 4)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_4_FAISS_UNION_INDEX.md

Architecture:
- Triggered by scheduler (cron-like) every 6 hours
- Queries all 6 truth layers for embedding_vector IS NOT NULL
- Builds unified FAISS IndexFlatIP
- Persists to disk for P01 recall queries

Trigger:
- Scheduled: Every 6 hours (configurable via FAISS_REBUILD_INTERVAL_HOURS)
- Manual: Via syscall union_index_rebuild(force=True)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_INDEX_DIR = "/data/faiss_union"
DEFAULT_REBUILD_INTERVAL_HOURS = 6


async def run(message: Any, context: Any, **config: Any) -> dict:
    """
    Rebuild FAISS union index from all truth layers.

    This job is designed to run as a scheduled P08 pipeline stage.
    It queries all 6 truth layers (st_epi, st_sem, st_procedural,
    st_social, st_prospective, st_kg_dom) for records with inline
    vectors and builds a unified FAISS index.

    Args:
        message: BusMessage (trigger event, may be None for scheduled)
        context: PipelineContext with syscalls and config
        **config: Stage configuration:
            - index_dir: Directory for index files (default: /data/faiss_union)
            - force: Force rebuild regardless of age (default: False)
            - rebuild_interval_hours: Hours between rebuilds (default: 6)

    Returns:
        Dictionary with rebuild statistics:
        - action: "rebuilt", "skipped", or "failed"
        - total_vectors: Number of vectors in index
        - layer_counts: Vectors per layer
        - duration_ms: Build time
        - reason: Why action was taken

    Performance:
        - Build time: ~1-5 seconds for 10k vectors
        - Memory: ~4MB per 10k vectors (768 dims × 4 bytes × 1.3x overhead)
    """
    # Get configuration
    index_dir = config.get(
        "index_dir",
        os.environ.get("FAISS_UNION_INDEX_DIR", DEFAULT_INDEX_DIR),
    )
    force = config.get("force", False)
    rebuild_interval_hours = config.get(
        "rebuild_interval_hours",
        int(os.environ.get("FAISS_REBUILD_INTERVAL_HOURS", DEFAULT_REBUILD_INTERVAL_HOURS)),
    )

    logger.info(
        "P08 UnionIndex: starting rebuild job",
        extra={
            "index_dir": index_dir,
            "force": force,
            "rebuild_interval_hours": rebuild_interval_hours,
        },
    )

    try:
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        manager = UnionIndexManager(
            index_dir=index_dir,
            rebuild_interval_hours=rebuild_interval_hours,
        )

        # Check if rebuild needed
        if not force and not manager.needs_rebuild:
            age_hours = manager.index_age_hours
            logger.info(
                "P08 UnionIndex: index is fresh, skipping rebuild",
                extra={"age_hours": age_hours},
            )
            return {
                "action": "skipped",
                "reason": "index_fresh",
                "age_hours": age_hours,
            }

        # Get database connection
        # Try multiple methods to get connection
        conn = None

        # Method 1: From context syscalls (preferred)
        if hasattr(context, "syscalls") and hasattr(context.syscalls, "get_connection"):
            conn = await context.syscalls.get_connection()

        # Method 2: From context directly
        if conn is None and hasattr(context, "db_connection"):
            conn = context.db_connection

        # Method 3: Create new connection
        if conn is None:
            try:
                from k0.db.connection import get_connection

                conn = await get_connection()
            except ImportError:
                pass

        if conn is None:
            logger.error("P08 UnionIndex: no database connection available")
            return {
                "action": "failed",
                "reason": "no_database_connection",
            }

        # Rebuild index
        import time

        start = time.time()
        searcher = await manager.build_and_save(conn)
        duration_ms = int((time.time() - start) * 1000)

        result = {
            "action": "rebuilt",
            "total_vectors": searcher.total_vectors,
            "layer_counts": searcher.layer_counts,
            "duration_ms": duration_ms,
            "index_dir": index_dir,
            "model_version": searcher.model_version,
        }

        logger.info("P08 UnionIndex: rebuild complete", extra=result)
        return result

    except ImportError as e:
        logger.error(
            "P08 UnionIndex: missing dependency",
            extra={"error": str(e)},
        )
        return {
            "action": "failed",
            "reason": "missing_dependency",
            "error": str(e),
        }
    except Exception as e:
        logger.error(
            "P08 UnionIndex: rebuild failed",
            extra={"error": str(e)},
        )
        return {
            "action": "failed",
            "reason": "exception",
            "error": str(e),
        }


async def search(
    query_vector: list,
    k: int = 20,
    layer_filter: Optional[list] = None,
    tenant_id: Optional[str] = None,
    space_id: Optional[str] = None,
    index_dir: Optional[str] = None,
) -> dict:
    """
    Search the union index.

    Convenience function for searching without the full pipeline context.
    Used by syscalls and direct API calls.

    Args:
        query_vector: 768-dim query embedding as list
        k: Number of results
        layer_filter: Optional layer filter
        tenant_id: Optional tenant filter
        space_id: Optional space filter
        index_dir: Index directory (default: /data/faiss_union)

    Returns:
        Dictionary with results:
        - results: List of {layer, record_id, score, tenant_id, space_id}
        - count: Number of results
        - error: Error message if failed
    """
    import numpy as np

    try:
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        _index_dir = index_dir or os.environ.get("FAISS_UNION_INDEX_DIR", DEFAULT_INDEX_DIR)

        manager = UnionIndexManager(_index_dir)
        searcher = manager.get_searcher()

        if searcher is None:
            return {
                "results": [],
                "count": 0,
                "error": "no_index_available",
            }

        # Convert to numpy
        query_np = np.array(query_vector, dtype=np.float32)

        results = searcher.search(
            query_np,
            k=k,
            layer_filter=layer_filter,
            tenant_id=tenant_id,
            space_id=space_id,
        )

        return {
            "results": [r.to_dict() for r in results],
            "count": len(results),
        }

    except Exception as e:
        logger.error(f"P08 UnionIndex search failed: {e}")
        return {
            "results": [],
            "count": 0,
            "error": str(e),
        }


def get_stats(index_dir: Optional[str] = None) -> dict:
    """
    Get union index statistics.

    Args:
        index_dir: Index directory

    Returns:
        Dictionary with index stats
    """
    try:
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        _index_dir = index_dir or os.environ.get("FAISS_UNION_INDEX_DIR", DEFAULT_INDEX_DIR)

        manager = UnionIndexManager(_index_dir)
        return manager.get_stats()

    except Exception as e:
        return {"error": str(e)}
