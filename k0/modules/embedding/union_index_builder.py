"""
UnionIndexBuilder - GAP-001 Milestone 4 (Issue 4.2)

Builds composite FAISS index from all 6 truth layers.
Queries embedding_vector BYTEA columns and adds to unified index.

GAP Reference: GAP_001 Section 7 (P08 FAISS Union Build)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_4_FAISS_UNION_INDEX.md
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional, Tuple

import numpy as np

from .union_index_metadata import UnionIndexMetadata, VectorMetadata

logger = logging.getLogger(__name__)


# Truth layers with inline vectors (from GAP-001)
# Format: (table_name, primary_key_column)
TRUTH_LAYERS = [
    ("st_epi", "episode_id"),
    ("st_sem", "pattern_id"),
    ("st_procedural", "routine_id"),
    ("st_social", "relationship_id"),
    ("st_prospective", "intention_id"),
    ("st_kg_dom", "entity_id"),
]

# Vector dimensions for UltraBERT
VECTOR_DIMENSION = 768
VECTOR_BYTES = VECTOR_DIMENSION * 4  # float32 = 4 bytes per element


class UnionIndexBuilder:
    """
    Builds FAISS union index from all truth layers.

    Queries each truth layer for records with embedding_vector IS NOT NULL,
    extracts the vectors, and builds a unified FAISS IndexFlatIP index.

    The builder also creates UnionIndexMetadata that tracks the source
    layer and record ID for each vector, enabling attribution of search
    results back to their origin.

    Usage:
        builder = UnionIndexBuilder()
        async with connection_scope() as conn:
            index, metadata = await builder.build(conn)
            # index is FAISS IndexFlatIP with all vectors
            # metadata maps FAISS indices to (layer, record_id)
    """

    def __init__(self, batch_size: int = 1000):
        """
        Initialize builder.

        Args:
            batch_size: Maximum records to fetch per query (for memory control)
        """
        self.batch_size = batch_size
        self._faiss = None  # Lazy import

    async def build(
        self,
        conn: Any,
        tenant_id: Optional[str] = None,
        space_id: Optional[str] = None,
    ) -> Tuple[Any, UnionIndexMetadata]:
        """
        Build FAISS index from all truth layers.

        Queries each of the 6 truth layers for records with inline vectors,
        normalizes vectors for cosine similarity, and adds them to a
        FAISS IndexFlatIP index.

        Args:
            conn: asyncpg connection
            tenant_id: Optional filter (only include vectors from this tenant)
            space_id: Optional filter (only include vectors from this space)

        Returns:
            Tuple of (faiss_index, UnionIndexMetadata)
        """
        import faiss

        # Initialize index (Inner Product for normalized vectors = cosine similarity)
        index = faiss.IndexFlatIP(VECTOR_DIMENSION)

        metadata = UnionIndexMetadata(
            build_timestamp=int(time.time() * 1000),
        )

        all_vectors: List[np.ndarray] = []
        start_time = time.time()

        for layer, pk_column in TRUTH_LAYERS:
            layer_start = time.time()

            vectors, metas = await self._fetch_layer_vectors(
                conn, layer, pk_column, tenant_id, space_id
            )

            for vec, meta in zip(vectors, metas):
                metadata.add(meta)
                all_vectors.append(vec)

            layer_duration_ms = int((time.time() - layer_start) * 1000)
            logger.debug(
                f"UnionIndexBuilder: fetched {len(vectors)} vectors from {layer}",
                extra={
                    "layer": layer,
                    "count": len(vectors),
                    "duration_ms": layer_duration_ms,
                },
            )

        if all_vectors:
            # Stack all vectors into numpy array
            vectors_np = np.vstack(all_vectors).astype(np.float32)

            # Normalize for cosine similarity via inner product
            faiss.normalize_L2(vectors_np)

            # Add to FAISS index
            index.add(vectors_np)

        total_duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "UnionIndexBuilder: build complete",
            extra={
                "total_vectors": metadata.total_vectors,
                "layer_counts": metadata.layer_counts,
                "duration_ms": total_duration_ms,
            },
        )

        return index, metadata

    async def _fetch_layer_vectors(
        self,
        conn: Any,
        layer: str,
        pk_column: str,
        tenant_id: Optional[str],
        space_id: Optional[str],
    ) -> Tuple[List[np.ndarray], List[VectorMetadata]]:
        """
        Fetch vectors from a single truth layer.

        First tries inline embedding_vector. Falls back to st_vec JOIN
        via embedding_id for records without inline vectors (GAP-001 transition).

        Args:
            conn: asyncpg connection
            layer: Table name (e.g., "st_epi")
            pk_column: Primary key column name
            tenant_id: Optional tenant filter
            space_id: Optional space filter

        Returns:
            Tuple of (vectors, metadata_entries)
        """
        # GAP-001: All truth layers now have inline embedding_vector
        vectors, metas = await self._fetch_inline_vectors(
            conn, layer, pk_column, tenant_id, space_id
        )

        # Legacy st_vec fallback removed - GAP-001 ensures inline vectors
        return vectors, metas

    async def _fetch_inline_vectors(
        self,
        conn: Any,
        layer: str,
        pk_column: str,
        tenant_id: Optional[str],
        space_id: Optional[str],
    ) -> Tuple[List[np.ndarray], List[VectorMetadata]]:
        """Fetch vectors from inline embedding_vector column."""
        # Build WHERE clause dynamically
        conditions = ["embedding_vector IS NOT NULL"]
        params: List[Any] = []

        if tenant_id:
            params.append(tenant_id)
            conditions.append(f"tenant_id = ${len(params)}")

        if space_id:
            params.append(space_id)
            conditions.append(f"space_id = ${len(params)}")

        # Add lifecycle filter (skip archived/tombstoned records)
        conditions.append("(archival_status IS NULL OR archival_status = 'ACTIVE')")

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT {pk_column}, tenant_id, space_id, embedding_vector
            FROM {layer}
            WHERE {where_clause}
            LIMIT {self.batch_size}
        """

        try:
            rows = await conn.fetch(query, *params)
        except Exception as e:
            logger.warning(
                f"UnionIndexBuilder: failed to query {layer}",
                extra={"layer": layer, "error": str(e)},
            )
            return [], []

        vectors: List[np.ndarray] = []
        metas: List[VectorMetadata] = []

        for row in rows:
            vec_bytes = row["embedding_vector"]

            # Validate vector bytes (768 floats × 4 bytes = 3072 bytes)
            if not vec_bytes or len(vec_bytes) != VECTOR_BYTES:
                logger.debug(
                    "UnionIndexBuilder: invalid vector bytes",
                    extra={
                        "layer": layer,
                        "record_id": row[pk_column],
                        "expected_bytes": VECTOR_BYTES,
                        "actual_bytes": len(vec_bytes) if vec_bytes else 0,
                    },
                )
                continue

            # Unpack BYTEA to float32 array
            vec = np.frombuffer(vec_bytes, dtype=np.float32).copy()
            vectors.append(vec)

            metas.append(
                VectorMetadata(
                    layer=layer,
                    record_id=str(row[pk_column]),
                    tenant_id=row["tenant_id"] or "",
                    space_id=row["space_id"] or "",
                )
            )

        return vectors, metas

    async def build_incremental(
        self,
        conn: Any,
        existing_index: Any,
        existing_metadata: UnionIndexMetadata,
        since_timestamp: int,
    ) -> Tuple[Any, UnionIndexMetadata]:
        """
        Incrementally add new vectors to existing index.

        Only fetches records created after the given timestamp.
        This is more efficient than full rebuild for frequent updates.

        Note: This does NOT handle deletions or updates - use full rebuild
        periodically (every 6 hours) to handle those cases.

        Args:
            conn: asyncpg connection
            existing_index: Existing FAISS index to add to
            existing_metadata: Existing metadata
            since_timestamp: Unix timestamp (ms) - only fetch newer records

        Returns:
            Tuple of (updated_index, updated_metadata)
        """
        import faiss

        all_vectors: List[np.ndarray] = []

        for layer, pk_column in TRUTH_LAYERS:
            vectors, metas = await self._fetch_incremental_vectors(
                conn, layer, pk_column, since_timestamp
            )

            for vec, meta in zip(vectors, metas):
                existing_metadata.add(meta)
                all_vectors.append(vec)

        if all_vectors:
            vectors_np = np.vstack(all_vectors).astype(np.float32)
            faiss.normalize_L2(vectors_np)
            existing_index.add(vectors_np)

        # Update timestamp
        existing_metadata.build_timestamp = int(time.time() * 1000)

        logger.info(
            "UnionIndexBuilder: incremental build complete",
            extra={
                "new_vectors": len(all_vectors),
                "total_vectors": existing_metadata.total_vectors,
            },
        )

        return existing_index, existing_metadata

    async def _fetch_incremental_vectors(
        self,
        conn: Any,
        layer: str,
        pk_column: str,
        since_timestamp: int,
    ) -> Tuple[List[np.ndarray], List[VectorMetadata]]:
        """Fetch vectors created after a given timestamp."""
        query = f"""
            SELECT {pk_column}, tenant_id, space_id, embedding_vector
            FROM {layer}
            WHERE embedding_vector IS NOT NULL
              AND (archival_status IS NULL OR archival_status = 'ACTIVE')
              AND created_at > $1
            LIMIT {self.batch_size}
        """

        try:
            # Convert ms to datetime if needed
            from datetime import datetime, timezone

            since_dt = datetime.fromtimestamp(since_timestamp / 1000, tz=timezone.utc)
            rows = await conn.fetch(query, since_dt)
        except Exception as e:
            logger.warning(
                f"UnionIndexBuilder: incremental query failed for {layer}",
                extra={"layer": layer, "error": str(e)},
            )
            return [], []

        vectors: List[np.ndarray] = []
        metas: List[VectorMetadata] = []

        for row in rows:
            vec_bytes = row["embedding_vector"]
            if not vec_bytes or len(vec_bytes) != VECTOR_BYTES:
                continue

            vec = np.frombuffer(vec_bytes, dtype=np.float32).copy()
            vectors.append(vec)

            metas.append(
                VectorMetadata(
                    layer=layer,
                    record_id=str(row[pk_column]),
                    tenant_id=row["tenant_id"] or "",
                    space_id=row["space_id"] or "",
                )
            )

        return vectors, metas
