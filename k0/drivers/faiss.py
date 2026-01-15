"""
pgvector Vector Storage Driver - Outbox Worker Implementation

Purpose:
    Processes outbox entries with alias='st_vector' to store embedding vectors
    in PostgreSQL with pgvector extension for fast approximate nearest neighbor (ANN) search.

Architecture:
    - Reads vectors from st_embedding_queue (after P08 generates them)
    - Stores vectors directly in PostgreSQL with pgvector extension
    - Uses IVFFlat or HNSW indexes for fast similarity search
    - Supports incremental index updates (no full rebuild required)

Contract:
    - apply(entry: OutboxEntry) -> None
    - build_driver() factory function
    - Async context manager support (__aenter__/__aexit__)

Performance:
    - Target: <30ms P95 per vector
    - Batch indexing: 128 vectors per UnitOfWork
    - Index type: IVFFlat for balanced speed/accuracy

Dependencies:
    - asyncpg
    - numpy
    - pgvector extension in PostgreSQL

Usage (from outbox worker):
    driver = await build_driver()
    async with driver:
        for entry in outbox_batch:
            await driver.apply(entry)
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

from k0.db.connection import connection_scope

if TYPE_CHECKING:
    import asyncpg

    from k0.storage.outbox import OutboxEntry

logger = logging.getLogger(__name__)


class PgvectorDriver:
    """
    pgvector driver for semantic similarity search.

    Stores embedding vectors directly in PostgreSQL with pgvector extension.
    Uses IVFFlat index for fast approximate nearest neighbor queries.
    """

    def __init__(self, dimension: int = 384):
        """
        Initialize pgvector driver with vector configuration.

        Args:
            dimension: Vector dimension (default 384 for all-MiniLM-L6-v2)

        Note:
            Uses global connection pool (configured by kernel) for database access.
        """
        self.dimension = dimension
        self._np = None

    async def __aenter__(self):
        """Async context manager entry - ensure pgvector extension and table."""
        try:
            import numpy as np
        except ImportError as e:
            raise ImportError("numpy not installed. Install with: pip install numpy") from e

        self._np = np

        # Ensure pgvector extension and tables exist
        async with connection_scope() as conn:
            await self._ensure_pgvector_setup(conn)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        logger.info("PgvectorDriver closed")

    async def _ensure_pgvector_setup(self, conn: "asyncpg.Connection"):
        """
        Ensure pgvector extension and st_embeddings table exist.

        Args:
            conn: asyncpg connection

        Schema:
            - id (SERIAL, primary key)
            - embedding_id (TEXT, unique, links to st_hipp_events)
            - event_id (TEXT, links to st_hipp_events)
            - tenant_id (TEXT, for multi-tenancy)
            - space_id (TEXT, for ACL filtering)
            - embedding (vector(384), the actual vector)
            - vector_norm (REAL, L2 norm for quality checks)
            - indexed_at (TIMESTAMPTZ, timestamp)
        """
        # Enable pgvector extension
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # Create embeddings table with vector column
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS st_embeddings (
                id SERIAL PRIMARY KEY,
                embedding_id TEXT NOT NULL UNIQUE,
                event_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                space_id TEXT NOT NULL,
                embedding vector({self.dimension}) NOT NULL,
                vector_norm REAL NOT NULL,
                indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        # Create indexes for common queries
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_embeddings_event_id
            ON st_embeddings(event_id)
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_embeddings_tenant_space
            ON st_embeddings(tenant_id, space_id)
            """
        )

        # Create IVFFlat index for vector similarity search
        # Note: IVFFlat requires training data, so we create after some data exists
        # For now, create a simple index that works with any amount of data
        try:
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_embeddings_vector_cosine
                ON st_embeddings USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """
            )
        except Exception as e:
            # IVFFlat might fail if table is empty or too few rows
            logger.debug(f"IVFFlat index creation deferred: {e}")

        logger.info("PgvectorDriver: st_embeddings table ready")

    async def apply(self, entry: "OutboxEntry") -> None:
        """
        Process outbox entry - store vector in pgvector table.

        Args:
            entry: Outbox entry with alias='st_vector'

        Payload Schema:
            {
                "embedding_id": "emb_...",
                "action": "add" | "delete"
            }

        Raises:
            RuntimeError: If driver not initialized
            ValueError: If payload missing required fields or vector not ready
            asyncpg.PostgresError: If database operation fails
        """
        if self._np is None:
            raise RuntimeError("PgvectorDriver not initialized (use async context manager)")

        async with connection_scope() as conn:
            try:
                # Parse payload
                payload = json.loads(entry.payload)
                embedding_id = payload.get("embedding_id")
                action = payload.get("action", "add")

                if not embedding_id:
                    raise ValueError(f"Missing embedding_id in payload: {entry.payload}")

                logger.debug(f"pgvector: Processing {action} for embedding_id={embedding_id}")

                if action == "add":
                    await self._add_vector(conn, embedding_id)
                elif action == "delete":
                    await self._delete_vector(conn, embedding_id)
                else:
                    raise ValueError(f"Unknown action: {action}")

            except json.JSONDecodeError as e:
                logger.error(f"pgvector: Invalid JSON payload: {entry.payload}", exc_info=e)
                raise

    async def _add_vector(self, conn: "asyncpg.Connection", embedding_id: str):
        """
        Add vector from st_embedding_queue to pgvector table.

        Args:
            conn: asyncpg connection
            embedding_id: Embedding identifier

        Raises:
            ValueError: If vector not found or not ready
        """
        # Read vector from st_embedding_queue
        row = await conn.fetchrow(
            """
            SELECT
                embedding_id,
                event_id,
                tenant_id,
                space_id,
                vector_json,
                status
            FROM st_embedding_queue
            WHERE embedding_id = $1
            """,
            embedding_id,
        )

        if not row:
            raise ValueError(f"pgvector: Embedding {embedding_id} not found in st_embedding_queue")

        if row["status"] != "READY":
            raise ValueError(
                f"pgvector: Embedding {embedding_id} not ready (status={row['status']})"
            )

        # Parse vector JSON
        try:
            vector_list = json.loads(row["vector_json"])
            vector = self._np.array(vector_list, dtype=self._np.float32)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"pgvector: Invalid vector_json for {embedding_id}: {e}")

        if vector.shape[0] != self.dimension:
            raise ValueError(
                f"pgvector: Vector dimension mismatch (expected {self.dimension}, got {vector.shape[0]})"
            )

        # Compute L2 norm for quality checks
        vector_norm = float(self._np.linalg.norm(vector))

        # Convert to PostgreSQL vector format (string representation)
        vector_str = "[" + ",".join(str(v) for v in vector.tolist()) + "]"

        # Store in st_embeddings with pgvector
        await conn.execute(
            """
            INSERT INTO st_embeddings (
                embedding_id,
                event_id,
                tenant_id,
                space_id,
                embedding,
                vector_norm
            ) VALUES ($1, $2, $3, $4, $5::vector, $6)
            ON CONFLICT(embedding_id) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                vector_norm = EXCLUDED.vector_norm,
                indexed_at = NOW()
            """,
            row["embedding_id"],
            row["event_id"],
            row["tenant_id"],
            row["space_id"],
            vector_str,
            vector_norm,
        )

        # Update st_embedding_queue status to INDEXED
        await conn.execute(
            """
            UPDATE st_embedding_queue
            SET status = 'INDEXED', updated_at = NOW()
            WHERE embedding_id = $1
            """,
            embedding_id,
        )

        logger.info(f"pgvector: Added vector {embedding_id} (norm={vector_norm:.2f})")

    async def _delete_vector(self, conn: "asyncpg.Connection", embedding_id: str):
        """
        Delete vector from pgvector table.

        Args:
            conn: asyncpg connection
            embedding_id: Embedding identifier
        """
        await conn.execute(
            """
            DELETE FROM st_embeddings WHERE embedding_id = $1
            """,
            embedding_id,
        )

        logger.info(f"pgvector: Deleted embedding {embedding_id}")

    async def search_similar(
        self,
        query_vector: list[float],
        tenant_id: str,
        space_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """
        Search for similar vectors using cosine similarity.

        Args:
            query_vector: Query embedding vector
            tenant_id: Tenant ID for filtering
            space_id: Space ID for filtering
            limit: Maximum number of results

        Returns:
            List of dicts with embedding_id, event_id, and similarity score
        """
        if self._np is None:
            raise RuntimeError("PgvectorDriver not initialized")

        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

        async with connection_scope() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    embedding_id,
                    event_id,
                    1 - (embedding <=> $1::vector) as similarity
                FROM st_embeddings
                WHERE tenant_id = $2 AND space_id = $3
                ORDER BY embedding <=> $1::vector
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
                    "similarity": row["similarity"],
                }
                for row in rows
            ]


async def build_driver() -> PgvectorDriver:
    """
    Factory function to build PgvectorDriver instance.

    Configuration:
        - Reads K0_VECTOR_DIMENSION from environment (default: 384)
        - Uses global connection pool (configured by kernel) for database access

    Returns:
        Configured PgvectorDriver instance
    """
    dimension = int(os.getenv("K0_VECTOR_DIMENSION", "384"))

    return PgvectorDriver(dimension=dimension)
    return PgvectorDriver(dimension=dimension)
    return PgvectorDriver(dimension=dimension)
    return PgvectorDriver(dimension=dimension)
    return PgvectorDriver(dimension=dimension)
    return PgvectorDriver(dimension=dimension)
