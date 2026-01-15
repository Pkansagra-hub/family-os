"""
VectorLayerWriter — Issue 5.2.9

Writer for st_vec (embeddings) layer with P08 index coordination.
Handles embedding persistence and notifies P08 for search index updates.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.9 — st_vec coordination with P08)
    - Dossier §4.8.8 (st_vec Writes)
    - Dossier §9.4 (P03 → P08 Contract)

Operations:
    INSERT: Create new embedding
    UPDATE: Update aggregated embedding vector
    ARCHIVE: Soft-delete stale embedding

P08 Coordination:
    - Notifies P08 via outbox events for index updates
    - Circuit breaker prevents cascade failure on P08 outage
    - Events: p03.embedding.created.v1, p03.embedding.updated.v1

Embedding Aggregation:
    - mean: Simple average of all embeddings
    - weighted_mean: Weighted average with recency weights
    - max: Element-wise maximum

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from k0.modules.consolidation.truth_writer.result import LayerWriteResult
from k0.pipelines.p03.phases.r7_truth_writer import OptimisticLockError
from k0.pipelines.p03.staged_writes import LAYER_ST_VEC, StagedWrite, WriteOperation
from k0.storage.outbox import OutboxEntry

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


# P08 coordination event topics
P08_EMBEDDING_CREATED = "p03.embedding.created.v1"
P08_EMBEDDING_UPDATED = "p03.embedding.updated.v1"


@dataclass
class EmbeddingWriteData:
    """
    Data structure for st_vec (embedding) writes.

    Represents an aggregated embedding vector.

    Attributes:
        embedding_id: Unique embedding identifier
        tenant_id: Tenant identifier
        space_id: Space identifier
        source_type: Type of source (entity, pattern, episode)
        source_id: ID of source record
        embedding: Binary embedding vector
        model_version: Model version for compatibility
        source_count: Number of contributing texts
        aggregation_method: Aggregation method (mean, weighted_mean, max)
    """

    embedding_id: str
    tenant_id: str
    space_id: str
    source_type: str = "entity"  # entity, pattern, episode
    source_id: str = ""
    embedding: bytes = b""
    model_version: str = "unknown"
    source_count: int = 1
    aggregation_method: str = "mean"  # mean, weighted_mean, max


@dataclass
class P08CircuitBreakerConfig:
    """
    Configuration for P08 unavailability circuit breaker.

    Attributes:
        failure_threshold: Number of failures before opening circuit
        reset_timeout_ms: Time (ms) before attempting to close circuit
        use_cached_on_failure: Whether to use cached embeddings when P08 is down
    """

    failure_threshold: int = 5
    reset_timeout_ms: int = 60000  # 1 minute
    use_cached_on_failure: bool = True


class VectorLayerWriter:
    """
    Writer for st_vec (embeddings) layer with P08 index coordination.

    Handles INSERT, UPDATE, and ARCHIVE operations for embedding records.
    Notifies P08 embedding index via outbox events for search updates.

    Table: st_vec
    Primary Key: embedding_id
    Version Column: version (for optimistic locking)

    P08 Coordination:
        - INSERT triggers p03.embedding.created.v1 event
        - UPDATE triggers p03.embedding.updated.v1 event
        - Circuit breaker prevents cascade failure on P08 outage

    Usage:
        writer = VectorLayerWriter()
        result = await writer.write(staged_writes, uow)
    """

    LAYER = LAYER_ST_VEC

    def __init__(self, p08_config: Optional[P08CircuitBreakerConfig] = None):
        """
        Initialize vector layer writer.

        Args:
            p08_config: Optional circuit breaker configuration for P08
        """
        self._p08_config = p08_config or P08CircuitBreakerConfig()
        self._p08_failures = 0
        self._last_failure_ms = 0

    @property
    def layer(self) -> str:
        """Target layer name."""
        return self.LAYER

    async def write(
        self,
        writes: List[StagedWrite],
        uow: UnitOfWork,
    ) -> LayerWriteResult:
        """
        Execute vector layer writes and notify P08.

        Processes all writes for this layer, tracking successes and failures.
        Stages P08 notification events for index updates.

        Args:
            writes: List of StagedWrite objects for this layer
            uow: UnitOfWork providing database connection

        Returns:
            LayerWriteResult with success/failure counts
        """
        succeeded = 0
        failed_ids: List[str] = []
        error_messages: List[str] = []
        p08_events: List[OutboxEntry] = []

        for write in writes:
            if write.layer != self.LAYER:
                continue

            try:
                if write.operation == WriteOperation.INSERT:
                    await self._insert(uow, write)
                    p08_events.append(self._create_p08_event(write, "created"))
                elif write.operation == WriteOperation.UPDATE:
                    await self._update(uow, write)
                    p08_events.append(self._create_p08_event(write, "updated"))
                elif write.operation == WriteOperation.ARCHIVE:
                    await self._archive(uow, write)
                elif write.operation == WriteOperation.TOMBSTONE:
                    await self._tombstone(uow, write)
                succeeded += 1
            except OptimisticLockError:
                failed_ids.append(write.record_id)
                error_messages.append(f"Version conflict for embedding {write.record_id}")
            except Exception as e:
                failed_ids.append(write.record_id)
                error_messages.append(f"Failed to write {write.record_id}: {e}")

        # Stage P08 notifications (best effort via circuit breaker)
        await self._notify_p08(uow, p08_events)

        return LayerWriteResult(
            layer=self.LAYER,
            writes_attempted=len([w for w in writes if w.layer == self.LAYER]),
            writes_succeeded=succeeded,
            writes_failed=len(failed_ids),
            failed_ids=failed_ids,
            error_message="; ".join(error_messages) if error_messages else None,
        )

    async def _insert(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        INSERT new embedding into st_vec.

        Creates a new embedding record with binary vector data.
        Uses ON CONFLICT DO NOTHING for idempotency.
        """
        data = write.record_data
        now = _now_ms()

        await uow.connection.execute(
            """
            INSERT INTO st_vec (
                embedding_id, tenant_id, space_id,
                source_type, source_id, embedding,
                model_version, source_count, aggregation_method,
                created_at, version
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 1)
            ON CONFLICT (embedding_id) DO NOTHING
            """,
            data["embedding_id"],
            data["tenant_id"],
            data["space_id"],
            data.get("source_type", "entity"),
            data.get("source_id", ""),
            data.get("embedding", b""),  # bytes
            data.get("model_version", "unknown"),
            data.get("source_count", 1),
            data.get("aggregation_method", "mean"),
            now,
        )

    async def _update(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        UPDATE embedding with new aggregated vector.

        Raises OptimisticLockError if version mismatch.
        """
        data = write.record_data
        now = _now_ms()

        result = await uow.connection.execute(
            """
            UPDATE st_vec
            SET embedding = COALESCE($1, embedding),
                source_count = COALESCE($2, source_count),
                model_version = COALESCE($3, model_version),
                aggregation_method = COALESCE($4, aggregation_method),
                updated_at = $5,
                version = version + 1
            WHERE embedding_id = $6 AND version = $7
            """,
            data.get("embedding"),
            data.get("source_count"),
            data.get("model_version"),
            data.get("aggregation_method"),
            now,
            write.record_id,
            write.expected_version,
        )

        if result == "UPDATE 0":
            raise OptimisticLockError(f"Version conflict updating embedding {write.record_id}")

    async def _archive(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """ARCHIVE stale embedding."""
        now = _now_ms()
        reason = write.record_data.get("archived_reason", "stale")

        await uow.connection.execute(
            """
            UPDATE st_vec
            SET archival_status = 'ARCHIVED',
                archived_at = $1,
                archived_reason = $2
            WHERE embedding_id = $3
              AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
            """,
            now,
            reason,
            write.record_id,
        )

    async def _tombstone(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """TOMBSTONE embedding for GDPR deletion."""
        now = _now_ms()
        await uow.connection.execute(
            """
            UPDATE st_vec
            SET embedding = NULL,
                archival_status = 'TOMBSTONE',
                archived_at = $1,
                archived_reason = 'gdpr_deletion'
            WHERE embedding_id = $2
            """,
            now,
            write.record_id,
        )

    def _create_p08_event(self, write: StagedWrite, event_type: str) -> OutboxEntry:
        """
        Create P08 notification event.

        Args:
            write: The StagedWrite that was processed
            event_type: Either "created" or "updated"

        Returns:
            OutboxEntry for P08 notification
        """
        data = write.record_data
        topic = P08_EMBEDDING_CREATED if event_type == "created" else P08_EMBEDDING_UPDATED
        now = _now_ms()

        payload = {
            "embedding_id": data["embedding_id"],
            "tenant_id": data["tenant_id"],
            "space_id": data["space_id"],
            "source_type": data.get("source_type", "entity"),
            "source_id": data.get("source_id", ""),
            "model_version": data.get("model_version", "unknown"),
            "event_type": event_type,
            "timestamp_ms": now,
        }

        return OutboxEntry(
            id=None,
            wal_pos=0,
            tenant_id=data["tenant_id"],
            space_id=data["space_id"],
            driver="p08",  # Target P08 pipeline
            op_kind=topic,
            payload=json.dumps(payload).encode("utf-8"),
            fingerprint=f"p08:{event_type}:{data['embedding_id']}",
            requeue_seq=0,
            retries=0,
        )

    async def _notify_p08(self, uow: UnitOfWork, events: List[OutboxEntry]) -> None:
        """
        Notify P08 via outbox with circuit breaker.

        If circuit is open (too many failures), notifications are skipped
        and P08 will use cached embeddings until circuit resets.

        Args:
            uow: UnitOfWork for staging outbox events
            events: List of P08 notification events
        """
        if not events:
            return

        if self._is_circuit_open():
            # Circuit open - skip P08 notifications, use cached embeddings
            return

        try:
            for event in events:
                uow.stage_outbox(event)
            self._p08_failures = 0  # Reset on success
        except Exception:
            self._p08_failures += 1
            self._last_failure_ms = _now_ms()

    def _is_circuit_open(self) -> bool:
        """
        Check if circuit breaker is open.

        Returns True if too many P08 failures have occurred
        and reset timeout has not elapsed.
        """
        if self._p08_failures < self._p08_config.failure_threshold:
            return False

        # Check if reset timeout has passed
        now = _now_ms()
        if now - self._last_failure_ms > self._p08_config.reset_timeout_ms:
            self._p08_failures = 0
            return False

        return True

    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker."""
        self._p08_failures = 0
        self._last_failure_ms = 0

    @staticmethod
    def aggregate_embeddings(
        embeddings: List[bytes],
        method: str = "mean",
        weights: Optional[List[float]] = None,
    ) -> bytes:
        """
        Aggregate multiple embeddings into one.

        This is a utility method for combining embeddings from
        multiple sources into a single representative vector.

        Args:
            embeddings: List of binary embedding vectors (float32)
            method: Aggregation method (mean, weighted_mean, max)
            weights: Optional weights for weighted_mean

        Returns:
            Aggregated embedding as bytes (float32)

        Raises:
            ValueError: If embeddings list is empty
            ImportError: If numpy is not available
        """
        if not embeddings:
            raise ValueError("Cannot aggregate empty embeddings list")

        try:
            import numpy as np
        except ImportError as e:
            raise ImportError("numpy is required for embedding aggregation") from e

        # Decode embeddings to numpy arrays
        arrays = [np.frombuffer(e, dtype=np.float32) for e in embeddings]

        if method == "mean":
            result = np.mean(arrays, axis=0)
        elif method == "weighted_mean" and weights:
            result = np.average(arrays, axis=0, weights=weights)
        elif method == "max":
            result = np.max(arrays, axis=0)
        else:
            # Default to mean for unknown methods
            result = np.mean(arrays, axis=0)

        return result.astype(np.float32).tobytes()


def create_vector_writer(
    p08_config: Optional[P08CircuitBreakerConfig] = None,
) -> VectorLayerWriter:
    """
    Factory function to create VectorLayerWriter instance.

    Args:
        p08_config: Optional circuit breaker configuration for P08

    Returns:
        Configured VectorLayerWriter instance
    """
    return VectorLayerWriter(p08_config=p08_config)
