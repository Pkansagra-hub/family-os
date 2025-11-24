"""
FAISS Vector Storage Driver - Outbox Worker Implementation

Purpose:
    Processes outbox entries with alias='st_vector' to store embedding vectors
    in FAISS index for fast approximate nearest neighbor (ANN) search.

Architecture:
    - Reads vectors from st_embedding_queue (after P08 generates them)
    - Stores vectors in binary FAISS index file (Flat/IVF/HNSW)
    - Maintains metadata table (st_embeddings) for event_id ↔ vector_id mapping
    - Supports incremental index updates (no full rebuild required)

Contract:
    - apply(entry: OutboxEntry) -> None
    - build_driver() factory function
    - Context manager support (__enter__/__exit__)

Performance:
    - Target: <30ms P95 per vector
    - Batch indexing: 128 vectors per UnitOfWork
    - Index type: Flat (exact) for small datasets, IVF for large datasets

Dependencies:
    - faiss-cpu (pip install faiss-cpu)
    - numpy

Usage (from outbox worker):
    driver = build_driver()
    with driver:
        for entry in outbox_batch:
            driver.apply(entry)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from k0.uow.connection_pool import connection_scope

if TYPE_CHECKING:
    from k0.storage.outbox import OutboxEntry

logger = logging.getLogger(__name__)


class FaissDriver:
    """
    FAISS vector index driver for semantic similarity search.

    Reads embedding vectors from st_embedding_queue (status='READY')
    and stores them in FAISS index with metadata linkage in st_embeddings.
    """

    def __init__(self, index_path: str, dimension: int = 384):
        """
        Initialize FAISS driver with index configuration.

        Args:
            index_path: Path to FAISS index file (*.faiss)
            dimension: Vector dimension (default 384 for all-MiniLM-L6-v2)

        Note:
            Uses global connection pool (configured by kernel) for database access.
        """
        self.index_path = index_path
        self.dimension = dimension
        self.index = None

    def __enter__(self):
        """Context manager entry - load FAISS index."""
        try:
            import faiss
            import numpy as np
        except ImportError as e:
            raise ImportError(
                "faiss-cpu or numpy not installed. Install with: pip install faiss-cpu numpy"
            ) from e

        # Store imports as instance variables for use in methods
        self.faiss = faiss
        self.np = np

        # Load or create FAISS index
        index_file = Path(self.index_path)
        if index_file.exists():
            self.index = faiss.read_index(str(index_file))
            logger.info(
                f"FaissDriver: Loaded existing index from {self.index_path} ({self.index.ntotal} vectors)"
            )
        else:
            # Create new Flat index (exact search, fast for <1M vectors)
            self.index = faiss.IndexFlatL2(self.dimension)
            logger.info(f"FaissDriver: Created new Flat index (dim={self.dimension})")

        # Create metadata table using thread-local connection
        with connection_scope() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_metadata_table(conn)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - save FAISS index."""
        if self.index:
            # Save index to disk
            self.faiss.write_index(self.index, self.index_path)
            logger.info(
                f"FaissDriver: Saved index to {self.index_path} ({self.index.ntotal} vectors)"
            )

        logger.info("FaissDriver closed")

    def _ensure_metadata_table(self, conn):
        """
        Create st_embeddings metadata table if not exists.

        Args:
            conn: SQLite connection (thread-local)

        Schema:
            - vector_id (INTEGER, FAISS index position)
            - embedding_id (TEXT, unique, links to st_hipp_events)
            - event_id (TEXT, links to st_hipp_events)
            - tenant_id (TEXT, for multi-tenancy)
            - space_id (TEXT, for ACL filtering)
            - vector_norm (REAL, L2 norm for quality checks)
            - indexed_at (INTEGER, timestamp)
        """
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS st_embeddings (
                vector_id INTEGER PRIMARY KEY,
                embedding_id TEXT NOT NULL UNIQUE,
                event_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                space_id TEXT NOT NULL,
                vector_norm REAL NOT NULL,
                indexed_at INTEGER NOT NULL,
                FOREIGN KEY (embedding_id) REFERENCES st_hipp_events(embedding_id),
                FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id)
            )
        """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_embeddings_event_id
            ON st_embeddings(event_id)
        """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_embeddings_tenant_space
            ON st_embeddings(tenant_id, space_id)
        """
        )

        conn.commit()
        logger.info("FaissDriver: st_embeddings metadata table ready")

    def apply(self, entry: OutboxEntry) -> None:
        """
        Process outbox entry - store vector in FAISS index.

        Args:
            entry: Outbox entry with alias='st_vector'

        Payload Schema:
            {
                "embedding_id": "emb_...",
                "action": "add" | "delete"
            }

        Raises:
            RuntimeError: If FAISS index not loaded
            ValueError: If payload missing required fields or vector not ready
            sqlite3.Error: If database operation fails
        """
        if not self.index:
            raise RuntimeError("FaissDriver not loaded (use context manager)")

        with connection_scope() as conn:
            conn.row_factory = sqlite3.Row

            try:
                # Parse payload
                payload = json.loads(entry.payload)
                embedding_id = payload.get("embedding_id")
                action = payload.get("action", "add")

                if not embedding_id:
                    raise ValueError(f"Missing embedding_id in payload: {entry.payload}")

                logger.debug(f"FAISS: Processing {action} for embedding_id={embedding_id}")

                if action == "add":
                    self._add_vector(conn, embedding_id)
                elif action == "delete":
                    self._delete_vector(conn, embedding_id)
                else:
                    raise ValueError(f"Unknown action: {action}")

            except json.JSONDecodeError as e:
                logger.error(f"FAISS: Invalid JSON payload: {entry.payload}", exc_info=e)
                raise
            except Exception as e:
                logger.error(f"FAISS: Failed to process entry {entry.id}", exc_info=e)
                conn.rollback()
                raise

    def _add_vector(self, conn, embedding_id: str):
        """
        Add vector from st_embedding_queue to FAISS index.

        Args:
            conn: SQLite connection (thread-local)
            embedding_id: Embedding identifier

        Raises:
            ValueError: If vector not found or not ready
        """
        # Read vector from st_embedding_queue
        cursor = conn.execute(
            """
            SELECT
                eq.embedding_id,
                eq.event_id,
                eq.tenant_id,
                eq.space_id,
                eq.vector_json,
                eq.status
            FROM st_embedding_queue eq
            WHERE eq.embedding_id = ?
        """,
            (embedding_id,),
        )

        row = cursor.fetchone()
        if not row:
            raise ValueError(f"FAISS: Embedding {embedding_id} not found in st_embedding_queue")

        if row["status"] != "READY":
            raise ValueError(f"FAISS: Embedding {embedding_id} not ready (status={row['status']})")

        # Parse vector JSON
        try:
            vector_list = json.loads(row["vector_json"])
            vector = self.np.array(vector_list, dtype=self.np.float32)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"FAISS: Invalid vector_json for {embedding_id}: {e}")

        if vector.shape[0] != self.dimension:
            raise ValueError(
                f"FAISS: Vector dimension mismatch (expected {self.dimension}, got {vector.shape[0]})"
            )

        # Add to FAISS index
        vector_id = self.index.ntotal  # Next available ID
        self.index.add(vector.reshape(1, -1))

        # Compute L2 norm for quality checks
        vector_norm = float(self.np.linalg.norm(vector))

        # Store metadata in st_embeddings
        conn.execute(
            """
            INSERT INTO st_embeddings (
                vector_id,
                embedding_id,
                event_id,
                tenant_id,
                space_id,
                vector_norm,
                indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(embedding_id) DO UPDATE SET
                vector_id = excluded.vector_id,
                vector_norm = excluded.vector_norm,
                indexed_at = excluded.indexed_at
        """,
            (
                vector_id,
                row["embedding_id"],
                row["event_id"],
                row["tenant_id"],
                row["space_id"],
                vector_norm,
                self._current_timestamp(),
            ),
        )

        # Update st_embedding_queue status to INDEXED
        conn.execute(
            """
            UPDATE st_embedding_queue
            SET status = 'INDEXED', updated_at = ?
            WHERE embedding_id = ?
        """,
            (self._current_timestamp(), embedding_id),
        )

        conn.commit()
        logger.info(
            f"FAISS: Added vector {embedding_id} (vector_id={vector_id}, norm={vector_norm:.2f})"
        )

    def _delete_vector(self, conn, embedding_id: str):
        """
        Delete vector from FAISS index (soft delete in metadata).

        Args:
            conn: SQLite connection (thread-local)
            embedding_id: Embedding identifier

        Note:
            FAISS Flat index doesn't support true deletion. We mark as deleted
            in st_embeddings and rebuild index periodically (offline job).
        """
        # Soft delete in metadata
        conn.execute(
            """
            DELETE FROM st_embeddings WHERE embedding_id = ?
        """,
            (embedding_id,),
        )

        conn.commit()
        logger.info(
            f"FAISS: Soft-deleted embedding {embedding_id} (rebuild required for hard delete)"
        )

    @staticmethod
    def _current_timestamp() -> int:
        """Get current Unix timestamp in milliseconds."""
        import time

        return int(time.time() * 1000)


def build_driver() -> FaissDriver:
    """
    Factory function to build FaissDriver instance.

    Configuration:
        - Reads K0_FAISS_INDEX_PATH from environment (default: ./k0_faiss.index)
        - Reads K0_FAISS_DIMENSION from environment (default: 384)
        - Uses global connection pool (configured by kernel) for database access

    Returns:
        Configured FaissDriver instance

    Raises:
        ImportError: If faiss-cpu not installed
    """
    index_path = os.getenv("K0_FAISS_INDEX_PATH", "./k0_faiss.index")
    dimension = int(os.getenv("K0_FAISS_DIMENSION", "384"))

    return FaissDriver(index_path=index_path, dimension=dimension)
