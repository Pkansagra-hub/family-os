"""
pgvector Driver - Semantic Similarity Search for K0

Purpose:
    Provides pgvector-based semantic similarity search for episodic memory.
    This is the primary vector search driver for K0 PostgreSQL backend.

Architecture:
    - Uses PostgreSQL pgvector extension for vector storage
    - IVFFlat or HNSW indexes for approximate nearest neighbor search
    - Integrated with k0.db.connection async pool

Features:
    - Cosine similarity search
    - L2 (Euclidean) distance search
    - Inner product search
    - Tenant/space-aware filtering
    - Batch vector operations

Usage:
    from k0.drivers.pgvector import PgvectorSearchClient

    client = PgvectorSearchClient()
    async with client:
        results = await client.search_cosine(
            query_vector=[0.1, 0.2, ...],
            tenant_id="family-123",
            space_id="home",
            limit=10,
        )
"""

from __future__ import annotations

from typing import Any

from k0.db.connection import connection_scope


class PgvectorSearchClient:
    """
    pgvector search client for semantic similarity queries.

    Provides high-level search interface for episodic memory vectors.
    Assumes st_embeddings table already populated by PgvectorDriver.
    """

    def __init__(self, dimension: int = 384):
        """
        Initialize pgvector search client.

        Args:
            dimension: Vector dimension (default 384 for all-MiniLM-L6-v2)
        """
        self.dimension = dimension

    async def __aenter__(self) -> "PgvectorSearchClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        pass

    async def search_cosine(
        self,
        query_vector: list[float],
        tenant_id: str,
        space_id: str,
        limit: int = 10,
        min_similarity: float = 0.0,
    ) -> list[dict[str, Any]]:
        """
        Search for similar vectors using cosine similarity.

        Args:
            query_vector: Query embedding vector (dimension must match)
            tenant_id: Tenant ID for filtering
            space_id: Space ID for filtering
            limit: Maximum number of results (default 10)
            min_similarity: Minimum similarity threshold (0.0-1.0)

        Returns:
            List of dicts with:
                - embedding_id: Embedding identifier
                - event_id: Event identifier
                - similarity: Cosine similarity score (0.0-1.0)

        Raises:
            ValueError: If vector dimension mismatch
        """
        if len(query_vector) != self.dimension:
            raise ValueError(
                f"Vector dimension mismatch: expected {self.dimension}, got {len(query_vector)}"
            )

        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

        async with connection_scope() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    embedding_id,
                    event_id,
                    1 - (embedding <=> $1::vector) as similarity
                FROM st_embeddings
                WHERE tenant_id = $2
                  AND space_id = $3
                  AND 1 - (embedding <=> $1::vector) >= $4
                ORDER BY embedding <=> $1::vector
                LIMIT $5
                """,
                vector_str,
                tenant_id,
                space_id,
                min_similarity,
                limit,
            )

            return [
                {
                    "embedding_id": row["embedding_id"],
                    "event_id": row["event_id"],
                    "similarity": float(row["similarity"]),
                }
                for row in rows
            ]

    async def search_l2(
        self,
        query_vector: list[float],
        tenant_id: str,
        space_id: str,
        limit: int = 10,
        max_distance: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar vectors using L2 (Euclidean) distance.

        Args:
            query_vector: Query embedding vector
            tenant_id: Tenant ID for filtering
            space_id: Space ID for filtering
            limit: Maximum number of results
            max_distance: Maximum L2 distance threshold (optional)

        Returns:
            List of dicts with embedding_id, event_id, and distance
        """
        if len(query_vector) != self.dimension:
            raise ValueError(
                f"Vector dimension mismatch: expected {self.dimension}, got {len(query_vector)}"
            )

        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

        async with connection_scope() as conn:
            if max_distance is not None:
                rows = await conn.fetch(
                    """
                    SELECT
                        embedding_id,
                        event_id,
                        embedding <-> $1::vector as distance
                    FROM st_embeddings
                    WHERE tenant_id = $2
                      AND space_id = $3
                      AND embedding <-> $1::vector <= $4
                    ORDER BY embedding <-> $1::vector
                    LIMIT $5
                    """,
                    vector_str,
                    tenant_id,
                    space_id,
                    max_distance,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT
                        embedding_id,
                        event_id,
                        embedding <-> $1::vector as distance
                    FROM st_embeddings
                    WHERE tenant_id = $2 AND space_id = $3
                    ORDER BY embedding <-> $1::vector
                    LIMIT $4
                    """,
                    vector_str,
                    tenant_id,
                    space_id,
                    limit,
                )

            return [
                {
                    "embedding_id": row["embedding_id"],
                    "event_id": row["event_id"],
                    "distance": float(row["distance"]),
                }
                for row in rows
            ]

    async def search_inner_product(
        self,
        query_vector: list[float],
        tenant_id: str,
        space_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search for similar vectors using inner product (dot product).

        Note: For normalized vectors, inner product equals cosine similarity.
        For unnormalized vectors, this measures magnitude-weighted similarity.

        Args:
            query_vector: Query embedding vector
            tenant_id: Tenant ID for filtering
            space_id: Space ID for filtering
            limit: Maximum number of results

        Returns:
            List of dicts with embedding_id, event_id, and inner_product score
        """
        if len(query_vector) != self.dimension:
            raise ValueError(
                f"Vector dimension mismatch: expected {self.dimension}, got {len(query_vector)}"
            )

        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

        async with connection_scope() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    embedding_id,
                    event_id,
                    (embedding <#> $1::vector) * -1 as inner_product
                FROM st_embeddings
                WHERE tenant_id = $2 AND space_id = $3
                ORDER BY embedding <#> $1::vector
                LIMIT $4
                """,
                vector_str,
                tenant_id,
                space_id,
                limit,
            )

            return [
                {
                    "embedding_id": row["embedding_id"],
                    "event_id": row["event_id"],
                    "inner_product": float(row["inner_product"]),
                }
                for row in rows
            ]

    async def get_vector(
        self,
        embedding_id: str,
    ) -> dict[str, Any] | None:
        """
        Retrieve a specific vector by embedding_id.

        Args:
            embedding_id: Embedding identifier

        Returns:
            Dict with embedding metadata and vector, or None if not found
        """
        async with connection_scope() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    embedding_id,
                    event_id,
                    tenant_id,
                    space_id,
                    embedding::text as vector_str,
                    vector_norm,
                    indexed_at
                FROM st_embeddings
                WHERE embedding_id = $1
                """,
                embedding_id,
            )

            if not row:
                return None

            # Parse vector string back to list
            vector_str = row["vector_str"]
            # Remove brackets and split
            vector_list = [float(v) for v in vector_str.strip("[]").split(",")]

            return {
                "embedding_id": row["embedding_id"],
                "event_id": row["event_id"],
                "tenant_id": row["tenant_id"],
                "space_id": row["space_id"],
                "vector": vector_list,
                "vector_norm": float(row["vector_norm"]),
                "indexed_at": row["indexed_at"],
            }

    async def count_vectors(
        self,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ) -> int:
        """
        Count vectors in the index.

        Args:
            tenant_id: Optional tenant filter
            space_id: Optional space filter (requires tenant_id)

        Returns:
            Number of vectors matching the filter
        """
        async with connection_scope() as conn:
            if tenant_id is None:
                row = await conn.fetchrow("SELECT COUNT(*) as count FROM st_embeddings")
            elif space_id is None:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as count FROM st_embeddings WHERE tenant_id = $1",
                    tenant_id,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as count FROM st_embeddings WHERE tenant_id = $1 AND space_id = $2",
                    tenant_id,
                    space_id,
                )

            return row["count"] if row else 0


__all__ = ["PgvectorSearchClient"]
