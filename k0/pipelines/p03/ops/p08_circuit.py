"""P08 Embedding Circuit Breaker — Issue 6.2.6.

Specialized circuit breaker for P08 embedding pipeline coordination
used in R4 KG entity embedding.

References:
- Dossier Section 13.6: Circuit Breaker (External Dependencies)
- M6_EXECUTION.md Issue 6.2.6
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from k0.pipelines.p03.ops.circuit_breaker import (
    P08_EMBEDDING_CONFIG,
    P03CircuitBreaker,
    P03CircuitBreakerState,
)

if TYPE_CHECKING:
    import asyncpg

    from k0.obs.metrics import MetricsExporter


class P08EmbeddingCircuitBreaker:
    """Circuit breaker for P08 embedding pipeline coordination.

    Used by R4 phase for entity embedding requests.
    Provides fallback to cached embeddings when P08 unavailable.

    Fallback Strategy:
    - P08 Available: Real-time embedding via P08
    - P08 Unavailable: Use cached embedding from st_vec
    - New Entity (no cache): Queue for later embedding

    Dossier Reference: Section 13.6
    """

    def __init__(
        self,
        p08_client,
        circuit: P03CircuitBreaker,
        metrics: Optional[MetricsExporter] = None,
    ) -> None:
        """Initialize P08 embedding circuit breaker.

        Args:
            p08_client: P08 pipeline client for embedding requests.
            circuit: Underlying circuit breaker instance.
            metrics: Optional metrics exporter.
        """
        self._p08 = p08_client
        self._circuit = circuit
        self._metrics = metrics
        self._pending_queue: List[str] = []

    @property
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self._circuit.state == P03CircuitBreakerState.OPEN

    @property
    def state(self) -> P03CircuitBreakerState:
        """Get current circuit state."""
        return self._circuit.state

    @property
    def pending_count(self) -> int:
        """Get count of entities pending embedding."""
        return len(self._pending_queue)

    async def get_embedding(
        self,
        entity_id: str,
        *,
        connection: "asyncpg.Connection | None" = None,
    ) -> Optional[List[float]]:
        """Get entity embedding with circuit breaker protection.

        Args:
            entity_id: Entity to get embedding for.
            connection: Optional database connection for cache lookup.

        Returns:
            Embedding vector if available, None if circuit open and no cache.
        """
        if not self._circuit.should_allow_request():
            self._emit_metric("p03_p08_circuit_fallback_total", 1.0)
            return await self._fallback_to_cached(entity_id, connection=connection)

        try:
            embedding = await self._p08.get_embedding(entity_id)
            self._circuit.record_success()
            return embedding

        except Exception as e:
            self._circuit.record_failure()
            self._emit_metric(
                "p03_p08_embedding_failure_total",
                1.0,
                error_type=type(e).__name__,
            )

            cached = await self._fallback_to_cached(entity_id, connection=connection)
            if cached is None:
                await self._queue_for_later(entity_id)
            return cached

    async def _fallback_to_cached(
        self,
        entity_id: str,
        *,
        connection: "asyncpg.Connection | None" = None,
    ) -> Optional[List[float]]:
        """Retrieve cached embedding from st_vec.

        Args:
            entity_id: Entity to lookup.
            connection: Optional database connection.

        Returns:
            Cached embedding vector or None.
        """
        if connection is None:
            self._emit_metric("p03_p08_cache_miss_total", 1.0)
            return None

        row = await connection.fetchrow(
            """
            SELECT embedding
            FROM st_vec
            WHERE entity_id = $1 AND status = 'ACTIVE'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            entity_id,
        )

        if row and row["embedding"]:
            self._emit_metric("p03_p08_cache_hit_total", 1.0)
            return list(row["embedding"])

        self._emit_metric("p03_p08_cache_miss_total", 1.0)
        return None

    async def _queue_for_later(self, entity_id: str) -> None:
        """Queue entity for embedding when circuit recovers.

        Args:
            entity_id: Entity to queue.
        """
        if entity_id not in self._pending_queue:
            self._pending_queue.append(entity_id)
            self._emit_metric("p03_p08_queued_total", 1.0)

    async def process_pending_queue(self) -> int:
        """Process pending embeddings when circuit closes.

        Returns:
            Count of successfully processed entities.
        """
        if self._circuit.state != P03CircuitBreakerState.CLOSED:
            return 0

        processed = 0
        while self._pending_queue and self._circuit.should_allow_request():
            entity_id = self._pending_queue.pop(0)
            try:
                await self._p08.get_embedding(entity_id)
                self._circuit.record_success()
                processed += 1
            except Exception:
                self._circuit.record_failure()
                self._pending_queue.insert(0, entity_id)
                break

        return processed

    def reset(self) -> None:
        """Reset circuit breaker and clear pending queue."""
        self._circuit.reset()
        self._pending_queue.clear()

    def _emit_metric(self, name: str, value: float, **labels: str) -> None:
        """Emit metric if exporter available."""
        if self._metrics is not None:
            self._metrics.emit(name, value, **labels)


def create_p08_circuit_breaker(
    p08_client,
    metrics: Optional[MetricsExporter] = None,
) -> P08EmbeddingCircuitBreaker:
    """Factory for P08 embedding circuit breaker.

    Args:
        p08_client: P08 pipeline client.
        metrics: Optional metrics exporter.

    Returns:
        Configured P08EmbeddingCircuitBreaker.
    """
    circuit = P03CircuitBreaker(
        name="p08_embedding",
        config=P08_EMBEDDING_CONFIG,
        metrics=metrics,
    )
    return P08EmbeddingCircuitBreaker(p08_client, circuit, metrics)
