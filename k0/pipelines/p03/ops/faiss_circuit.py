"""FAISS Index Circuit Breaker — Issue 6.2.8.

Specialized circuit breaker for FAISS vector index used in R2 similarity search.

References:
- Dossier Section 13.6: Circuit Breaker (External Dependencies)
- Dossier Section 13.9: Edge Case Handling Matrix
- M6_EXECUTION.md Issue 6.2.8
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from k0.pipelines.p03.ops.circuit_breaker import (
    FAISS_INDEX_CONFIG,
    P03CircuitBreaker,
    P03CircuitBreakerState,
)

if TYPE_CHECKING:
    import asyncpg
    import numpy as np

    from k0.obs.metrics import MetricsExporter


@dataclass
class SimilarityResult:
    """Result of similarity search."""

    entity_id: str
    similarity: float
    method: str  # "faiss" or "brute_force"


class FAISSCircuitBreaker:
    """Circuit breaker for FAISS vector index.

    Used by R2 phase for similarity search during clustering.
    Provides fallback to brute-force search when FAISS unavailable.

    Fallback Strategy:
    - FAISS Available: Fast ANN via FAISS
    - FAISS Unavailable: Brute-force PostgreSQL (slower but functional)

    Dossier Reference: Section 13.6, Edge Case 13.9
    """

    # Maximum embeddings to load for brute-force search
    BRUTE_FORCE_LIMIT = 10000

    def __init__(
        self,
        faiss_index,
        circuit: P03CircuitBreaker,
        metrics: Optional[MetricsExporter] = None,
    ) -> None:
        """Initialize FAISS circuit breaker.

        Args:
            faiss_index: FAISS index client for similarity search.
            circuit: Underlying circuit breaker instance.
            metrics: Optional metrics exporter.
        """
        self._faiss = faiss_index
        self._circuit = circuit
        self._metrics = metrics
        self._rebuild_requested = False

    @property
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self._circuit.state == P03CircuitBreakerState.OPEN

    @property
    def state(self) -> P03CircuitBreakerState:
        """Get current circuit state."""
        return self._circuit.state

    @property
    def rebuild_requested(self) -> bool:
        """Check if index rebuild has been requested."""
        return self._rebuild_requested

    async def search(
        self,
        query_vec: "np.ndarray",
        top_k: int = 10,
        *,
        space_id: str,
        connection: "asyncpg.Connection | None" = None,
    ) -> List[SimilarityResult]:
        """Search for similar entities with circuit breaker protection.

        Args:
            query_vec: Query embedding vector.
            top_k: Number of results to return.
            space_id: Space to search within.
            connection: Optional database connection for brute-force fallback.

        Returns:
            List of SimilarityResult, empty if both methods fail.
        """
        start_time = time.monotonic()

        if not self._circuit.should_allow_request():
            self._emit_metric("p03_faiss_fallback_total", 1.0)
            results = await self._brute_force_search(
                query_vec, top_k, space_id=space_id, connection=connection
            )
            self._observe_latency("brute_force", start_time)
            return results

        try:
            raw_results = await self._faiss.search(query_vec, top_k, space_id=space_id)
            self._circuit.record_success()

            results = [
                SimilarityResult(
                    entity_id=r["entity_id"],
                    similarity=r["similarity"],
                    method="faiss",
                )
                for r in raw_results
            ]
            self._observe_latency("faiss", start_time)
            return results

        except Exception as e:
            self._circuit.record_failure()
            self._emit_metric(
                "p03_faiss_error_total",
                1.0,
                error_type=type(e).__name__,
            )

            self._emit_metric("p03_faiss_fallback_total", 1.0)
            results = await self._brute_force_search(
                query_vec, top_k, space_id=space_id, connection=connection
            )
            self._observe_latency("brute_force", start_time)

            if not self._rebuild_requested:
                await self._trigger_index_rebuild()

            return results

    async def _brute_force_search(
        self,
        query_vec: "np.ndarray",
        top_k: int,
        *,
        space_id: str,
        connection: "asyncpg.Connection | None" = None,
    ) -> List[SimilarityResult]:
        """Brute-force similarity search via PostgreSQL.

        Slower but always available as fallback.

        Args:
            query_vec: Query embedding vector.
            top_k: Number of results to return.
            space_id: Space to search within.
            connection: Database connection.

        Returns:
            List of SimilarityResult sorted by similarity descending.
        """
        if connection is None:
            return []

        import numpy as np

        rows = await connection.fetch(
            """
            SELECT entity_id, embedding
            FROM st_vec
            WHERE space_id = $1 AND status = 'ACTIVE'
            LIMIT $2
            """,
            space_id,
            self.BRUTE_FORCE_LIMIT,
        )

        if not rows:
            return []

        results = []
        query_norm = float(np.linalg.norm(query_vec))

        for row in rows:
            if row["embedding"] is None:
                continue

            emb = np.array(row["embedding"])
            emb_norm = float(np.linalg.norm(emb))

            if emb_norm == 0 or query_norm == 0:
                continue

            similarity = float(np.dot(query_vec, emb) / (query_norm * emb_norm))
            results.append(
                SimilarityResult(
                    entity_id=row["entity_id"],
                    similarity=similarity,
                    method="brute_force",
                )
            )

        results.sort(key=lambda r: r.similarity, reverse=True)
        return results[:top_k]

    async def _trigger_index_rebuild(self) -> None:
        """Request FAISS index rebuild job."""
        self._rebuild_requested = True
        self._emit_metric("p03_faiss_rebuild_requested_total", 1.0)

    def clear_rebuild_flag(self) -> None:
        """Clear the rebuild requested flag."""
        self._rebuild_requested = False

    def reset(self) -> None:
        """Reset circuit breaker and rebuild flag."""
        self._circuit.reset()
        self._rebuild_requested = False

    def _observe_latency(self, method: str, start_time: float) -> None:
        """Record search latency.

        Args:
            method: Search method used ("faiss" or "brute_force").
            start_time: Monotonic start time.
        """
        latency = time.monotonic() - start_time
        if self._metrics is not None:
            self._metrics.observe(
                "p03_similarity_search_seconds",
                latency,
                labels={"method": method},
            )

    def _emit_metric(self, name: str, value: float, **labels: str) -> None:
        """Emit metric if exporter available."""
        if self._metrics is not None:
            self._metrics.emit(name, value, **labels)


def create_faiss_circuit_breaker(
    faiss_index,
    metrics: Optional[MetricsExporter] = None,
) -> FAISSCircuitBreaker:
    """Factory for FAISS circuit breaker.

    Args:
        faiss_index: FAISS index client.
        metrics: Optional metrics exporter.

    Returns:
        Configured FAISSCircuitBreaker.
    """
    circuit = P03CircuitBreaker(
        name="faiss_index",
        config=FAISS_INDEX_CONFIG,
        metrics=metrics,
    )
    return FAISSCircuitBreaker(faiss_index, circuit, metrics)
