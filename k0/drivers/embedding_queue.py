"""
Embedding Queue Worker Driver - Outbox Worker Implementation

Purpose:
    Processes outbox entries with alias='st_emb' to compute embedding vectors
    for episodic memory events using sentence-transformers models.

Architecture:
    - Reads jobs from st_embedding_queue (status='PENDING')
    - Computes vectors using sentence-transformers (all-MiniLM-L6-v2)
    - Stores results back to st_embedding_queue (status='READY', vector_json populated)
    - Enqueues st_vector outbox entry for pgvector indexing

Contract:
    - apply(entry: OutboxEntry) -> None
    - build_driver() factory function
    - Async context manager support (__aenter__/__aexit__)

Performance:
    - Target: <200ms P95 per embedding (model inference bottleneck)
    - Batch inference: 32 texts per batch (GPU acceleration if available)
    - Model: all-MiniLM-L6-v2 (384-dim, fast, good quality)

Dependencies:
    - sentence-transformers (pip install sentence-transformers)
    - torch (CPU or GPU)

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


class EmbeddingQueueDriver:
    """
    Embedding queue worker for vector generation.

    Reads pending embedding jobs from st_embedding_queue, computes vectors
    using sentence-transformers, and enqueues results for pgvector indexing.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize embedding queue driver.

        Args:
            model_name: Sentence-transformers model name (default: all-MiniLM-L6-v2)

        Note:
            Uses global connection pool (configured by kernel) for database access.
        """
        self.model_name = model_name
        self.model = None

    async def __aenter__(self):
        """Async context manager entry - load embedding model."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers not installed. Install with: pip install sentence-transformers"
            ) from e

        # Load embedding model
        logger.info(f"EmbeddingQueueDriver: Loading model {self.model_name}...")
        self.model = SentenceTransformer(self.model_name)
        logger.info(
            f"EmbeddingQueueDriver: Model loaded (dim={self.model.get_sentence_embedding_dimension()})"
        )

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        logger.info("EmbeddingQueueDriver closed")

    async def apply(self, entry: "OutboxEntry") -> None:
        """
        Process outbox entry - compute embedding vector for text.

        Args:
            entry: Outbox entry with alias='st_emb'

        Payload Schema:
            {
                "job_id": 123,
                "embedding_id": "emb_...",
                "action": "compute" | "retry" | "cancel"
            }

        Raises:
            RuntimeError: If model not loaded
            ValueError: If payload missing required fields
            asyncpg.PostgresError: If database operation fails
        """
        if not self.model:
            raise RuntimeError("EmbeddingQueueDriver model not loaded (use async context manager)")

        job_id = None
        async with connection_scope() as conn:
            try:
                # Parse payload
                payload = json.loads(entry.payload)
                job_id = payload.get("job_id")
                embedding_id = payload.get("embedding_id")
                action = payload.get("action", "compute")

                if not job_id or not embedding_id:
                    raise ValueError(f"Missing job_id or embedding_id in payload: {entry.payload}")

                logger.debug(f"EmbeddingQueue: Processing {action} for job_id={job_id}")

                if action == "compute":
                    await self._compute_embedding(conn, job_id, embedding_id)
                elif action == "retry":
                    await self._retry_embedding(conn, job_id, embedding_id)
                elif action == "cancel":
                    await self._cancel_embedding(conn, job_id)
                else:
                    raise ValueError(f"Unknown action: {action}")

            except json.JSONDecodeError as e:
                logger.error(f"EmbeddingQueue: Invalid JSON payload: {entry.payload}", exc_info=e)
                raise
            except Exception as e:
                logger.error(f"EmbeddingQueue: Failed to process entry {entry.id}", exc_info=e)
                # Mark job as FAILED_RETRYABLE
                if job_id:
                    await self._mark_failed(conn, job_id, str(e))
                raise

    async def _compute_embedding(self, conn: "asyncpg.Connection", job_id: int, embedding_id: str):
        """
        Compute embedding vector for text from st_hipp_events.

        Args:
            conn: asyncpg connection
            job_id: Job identifier in st_embedding_queue
            embedding_id: Embedding identifier (links to st_hipp_events)
        """
        # Read job from st_embedding_queue
        row = await conn.fetchrow(
            """
            SELECT
                job_id,
                event_id,
                embedding_id,
                tenant_id,
                space_id,
                status,
                attempt_count,
                max_attempts
            FROM st_embedding_queue
            WHERE job_id = $1 AND embedding_id = $2
            """,
            job_id,
            embedding_id,
        )

        if not row:
            raise ValueError(f"EmbeddingQueue: Job {job_id} not found")

        if row["status"] not in ("PENDING", "FAILED_RETRYABLE"):
            logger.warning(f"EmbeddingQueue: Job {job_id} status={row['status']} (skipping)")
            return

        # Read text from st_hipp_events
        event_row = await conn.fetchrow(
            """
            SELECT text, text_normalized
            FROM st_hipp_events
            WHERE event_id = $1
            """,
            row["event_id"],
        )

        if not event_row or not event_row["text"]:
            raise ValueError(f"EmbeddingQueue: Event {row['event_id']} has no text")

        text = event_row["text"]

        # Compute embedding vector
        logger.info(f"EmbeddingQueue: Computing embedding for job {job_id} (text len={len(text)})")
        vector = self.model.encode(text, convert_to_numpy=True)

        # Serialize vector to JSON
        vector_json = json.dumps(vector.tolist())

        # Update st_embedding_queue with result
        await conn.execute(
            """
            UPDATE st_embedding_queue
            SET
                status = 'READY',
                vector_json = $1,
                attempt_count = attempt_count + 1,
                updated_at = NOW()
            WHERE job_id = $2
            """,
            vector_json,
            job_id,
        )

        # Enqueue st_vector outbox entry for pgvector indexing
        await self._enqueue_vector_indexing(conn, embedding_id)

        logger.info(f"EmbeddingQueue: Computed embedding for job {job_id} (dim={len(vector)})")

    async def _retry_embedding(self, conn: "asyncpg.Connection", job_id: int, embedding_id: str):
        """
        Retry failed embedding computation with exponential backoff.

        Args:
            conn: asyncpg connection
            job_id: Job identifier
            embedding_id: Embedding identifier
        """
        # Check retry limit
        row = await conn.fetchrow(
            """
            SELECT attempt_count, max_attempts
            FROM st_embedding_queue
            WHERE job_id = $1
            """,
            job_id,
        )

        if not row:
            raise ValueError(f"EmbeddingQueue: Job {job_id} not found")

        if row["attempt_count"] >= row["max_attempts"]:
            # Exceeded max attempts, mark as FAILED_PERMANENT
            await conn.execute(
                """
                UPDATE st_embedding_queue
                SET status = 'FAILED_PERMANENT', updated_at = NOW()
                WHERE job_id = $1
                """,
                job_id,
            )
            logger.error(f"EmbeddingQueue: Job {job_id} exceeded max attempts (FAILED_PERMANENT)")
            return

        # Retry computation
        await self._compute_embedding(conn, job_id, embedding_id)

    async def _cancel_embedding(self, conn: "asyncpg.Connection", job_id: int):
        """
        Cancel embedding job (mark as FAILED_PERMANENT).

        Args:
            conn: asyncpg connection
            job_id: Job identifier
        """
        await conn.execute(
            """
            UPDATE st_embedding_queue
            SET status = 'FAILED_PERMANENT', updated_at = NOW()
            WHERE job_id = $1
            """,
            job_id,
        )

        logger.info(f"EmbeddingQueue: Cancelled job {job_id}")

    async def _mark_failed(self, conn: "asyncpg.Connection", job_id: int, error_msg: str):
        """
        Mark embedding job as FAILED_RETRYABLE with error message.

        Args:
            conn: asyncpg connection
            job_id: Job identifier
            error_msg: Error message
        """
        # Compute next attempt timestamp (exponential backoff)
        row = await conn.fetchrow(
            """
            SELECT attempt_count
            FROM st_embedding_queue
            WHERE job_id = $1
            """,
            job_id,
        )

        if not row:
            return

        attempt_count = row["attempt_count"]
        backoff_seconds = min(60 * (2**attempt_count), 3600)  # Max 1 hour

        await conn.execute(
            """
            UPDATE st_embedding_queue
            SET
                status = 'FAILED_RETRYABLE',
                last_error = $1,
                next_attempt_ts = NOW() + ($2 || ' seconds')::INTERVAL,
                updated_at = NOW()
            WHERE job_id = $3
            """,
            error_msg[:500],
            str(backoff_seconds),
            job_id,
        )

        logger.warning(f"EmbeddingQueue: Job {job_id} failed (retry in {backoff_seconds}s)")

    async def _enqueue_vector_indexing(self, conn: "asyncpg.Connection", embedding_id: str):
        """
        Enqueue st_vector outbox entry for pgvector indexing.

        Args:
            conn: asyncpg connection
            embedding_id: Embedding identifier
        """
        payload = {"embedding_id": embedding_id, "action": "add"}

        await conn.execute(
            """
            INSERT INTO st_outbox (topic, alias, payload, status, created_at, updated_at)
            VALUES ('p02.vector.ready.v1', 'st_vector', $1, 'PENDING', NOW(), NOW())
            """,
            json.dumps(payload),
        )

        logger.debug(f"EmbeddingQueue: Enqueued st_vector job for {embedding_id}")


async def build_driver() -> EmbeddingQueueDriver:
    """
    Factory function to build EmbeddingQueueDriver instance.

    Configuration:
        - Reads K0_EMBEDDING_MODEL from environment (default: all-MiniLM-L6-v2)
        - Uses global connection pool (configured by kernel) for database access

    Returns:
        Configured EmbeddingQueueDriver instance

    Raises:
        ImportError: If sentence-transformers not installed
    """
    model_name = os.getenv("K0_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    return EmbeddingQueueDriver(model_name=model_name)
    return EmbeddingQueueDriver(model_name=model_name)
    return EmbeddingQueueDriver(model_name=model_name)
    return EmbeddingQueueDriver(model_name=model_name)
    return EmbeddingQueueDriver(model_name=model_name)
    return EmbeddingQueueDriver(model_name=model_name)
