"""P03 Edge Case Handler.

Implements handlers for P03-specific edge cases as defined in the dossier
edge case matrix, ensuring graceful degradation and appropriate metrics.

Issue 6.2.18: Edge Case Handling Implementation
Dossier Reference: Section 13.9 Edge Case Handling Matrix
"""

from __future__ import annotations

import gc
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    import asyncpg

    from k0.obs.metrics import MetricsExporter


class EdgeCaseType(Enum):
    """Types of edge cases detected."""

    IDLE_CYCLE = "IDLE_CYCLE"
    CORRUPTED_EMBEDDING = "CORRUPTED_EMBEDDING"
    PARTIAL_WRITE_FAILURE = "PARTIAL_WRITE_FAILURE"
    BACKLOG_OVERFLOW = "BACKLOG_OVERFLOW"
    P08_CIRCUIT_OPEN = "P08_CIRCUIT_OPEN"
    FAISS_UNAVAILABLE = "FAISS_UNAVAILABLE"
    DUPLICATE_TRIGGER = "DUPLICATE_TRIGGER"
    MEMORY_PRESSURE = "MEMORY_PRESSURE"
    KG_EXPLOSION = "KG_EXPLOSION"


@dataclass
class EdgeCaseResult:
    """Result of edge case detection."""

    detected: bool
    edge_case_type: Optional[EdgeCaseType] = None
    action_taken: Optional[str] = None
    details: dict = field(default_factory=dict)

    @property
    def severity(self) -> str:
        """Get severity level for the edge case."""
        critical_types = {
            EdgeCaseType.KG_EXPLOSION,
            EdgeCaseType.MEMORY_PRESSURE,
            EdgeCaseType.CORRUPTED_EMBEDDING,
        }
        warning_types = {
            EdgeCaseType.BACKLOG_OVERFLOW,
            EdgeCaseType.IDLE_CYCLE,
            EdgeCaseType.P08_CIRCUIT_OPEN,
            EdgeCaseType.FAISS_UNAVAILABLE,
        }
        if self.edge_case_type in critical_types:
            return "critical"
        elif self.edge_case_type in warning_types:
            return "warning"
        return "info"


class P03EdgeCaseHandler:
    """
    Handle P03-specific edge cases with graceful degradation.

    Provides detection, handling, and recovery for edge cases
    defined in dossier Section 13.9.

    Edge Case Matrix:
    | Edge Case | Detection | Handling | Recovery | Metric |
    |-----------|-----------|----------|----------|--------|
    | Empty st_hipp_events (>24h) | Health check | Emit idle event | None | p03_idle_cycles_total |
    | Corrupted embeddings | NaN/dimension | Skip, flag recompute | P08 re-embed | p03_corrupted_embeddings_total |
    | Partial R7 failure | Rollback exception | COMMIT_PARTIAL | DLQ requeue | p03_partial_write_failures_total |
    | Backlog > 10K | Batch overflow | Adaptive batching | Alert ops | p03_backlog_overflow_total |
    | P08 circuit > 5min | Circuit duration | Queue locally | Auto on half-open | p03_p08_circuit_open_seconds |
    | FAISS unavailable | Load failure | Brute-force fallback | Index rebuild | p03_faiss_fallback_total |
    | Duplicate trigger | batch_hash match | Idempotent skip | None | p03_duplicate_triggers_total |
    | Memory pressure | Heap > 80% | Skip R5 | Automatic | p03_r5_memory_skipped_total |
    | KG explosion (>1M) | Node threshold | Partition KG | Enable sharding | p03_kg_partition_events_total |
    """

    # Thresholds from dossier Section 13.9
    IDLE_THRESHOLD_HOURS: int = 24
    BACKLOG_WARNING_THRESHOLD: int = 10_000
    BACKLOG_CRITICAL_THRESHOLD: int = 50_000
    MEMORY_PRESSURE_THRESHOLD: float = 0.80  # 80%
    KG_NODE_THRESHOLD: int = 1_000_000  # 1M nodes
    P08_CIRCUIT_OPEN_THRESHOLD_SECONDS: float = 300.0  # 5 minutes
    EMBEDDING_DIMENSION: int = 1536  # OpenAI ada-002
    BATCH_HASH_WINDOW_SECONDS: float = 3600.0  # 1 hour

    def __init__(
        self,
        *,
        metrics: Optional[MetricsExporter] = None,
        idle_threshold_hours: int = IDLE_THRESHOLD_HOURS,
        backlog_warning_threshold: int = BACKLOG_WARNING_THRESHOLD,
        backlog_critical_threshold: int = BACKLOG_CRITICAL_THRESHOLD,
        memory_pressure_threshold: float = MEMORY_PRESSURE_THRESHOLD,
        kg_node_threshold: int = KG_NODE_THRESHOLD,
        embedding_dimension: int = EMBEDDING_DIMENSION,
    ) -> None:
        self._metrics = metrics
        self._idle_threshold_hours = idle_threshold_hours
        self._backlog_warning_threshold = backlog_warning_threshold
        self._backlog_critical_threshold = backlog_critical_threshold
        self._memory_pressure_threshold = memory_pressure_threshold
        self._kg_node_threshold = kg_node_threshold
        self._embedding_dimension = embedding_dimension

        # Duplicate detection state
        self._seen_batch_hashes: set[str] = set()
        self._batch_hash_window: List[tuple[float, str]] = []

    async def check_idle_cycle(
        self,
        space_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> EdgeCaseResult:
        """
        Check if st_hipp_events has been empty for > 24h.

        This is normal during low activity periods but should emit
        a health event for monitoring visibility.

        Args:
            space_id: Space to check
            connection: Database connection

        Returns:
            EdgeCaseResult with idle status (action: EMIT_IDLE_EVENT)
        """
        now = int(time.time())
        threshold_seconds = self._idle_threshold_hours * 3600
        threshold_ts = (now - threshold_seconds) * 1000  # Convert to ms

        row = await connection.fetchrow(
            """
            SELECT MAX(created_at) as last_event
            FROM st_hipp_events
            WHERE space_id = $1
            """,
            space_id,
        )

        last_event = row["last_event"] if row else None

        if last_event is None or last_event < threshold_ts:
            self._emit_metric("p03_idle_cycles_total", 1.0, space_id=space_id[:8])

            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.IDLE_CYCLE,
                action_taken="EMIT_IDLE_EVENT",
                details={
                    "last_event_at": last_event,
                    "threshold_hours": self._idle_threshold_hours,
                    "space_id": space_id,
                },
            )

        return EdgeCaseResult(detected=False)

    def check_corrupted_embedding(
        self,
        entity_id: str,
        embedding: List[float],
        expected_dimension: Optional[int] = None,
    ) -> EdgeCaseResult:
        """
        Check for corrupted embeddings (NaN or dimension mismatch).

        Corrupted embeddings should be flagged for P08 re-embedding.

        Args:
            entity_id: Entity the embedding belongs to
            embedding: Embedding vector to check
            expected_dimension: Expected dimension (default: 1536)

        Returns:
            EdgeCaseResult with corruption details (action: FLAG_FOR_RECOMPUTE)
        """
        expected_dim = expected_dimension or self._embedding_dimension

        # Check dimension mismatch
        if len(embedding) != expected_dim:
            self._emit_metric(
                "p03_corrupted_embeddings_total",
                1.0,
                reason="dimension_mismatch",
            )
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.CORRUPTED_EMBEDDING,
                action_taken="FLAG_FOR_RECOMPUTE",
                details={
                    "entity_id": entity_id,
                    "actual_dimension": len(embedding),
                    "expected_dimension": expected_dim,
                    "reason": "dimension_mismatch",
                },
            )

        # Check for NaN values
        has_nan = any(math.isnan(v) for v in embedding)
        if has_nan:
            self._emit_metric(
                "p03_corrupted_embeddings_total",
                1.0,
                reason="nan_detected",
            )
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.CORRUPTED_EMBEDDING,
                action_taken="FLAG_FOR_RECOMPUTE",
                details={
                    "entity_id": entity_id,
                    "reason": "nan_detected",
                },
            )

        # Check for infinite values
        has_inf = any(math.isinf(v) for v in embedding)
        if has_inf:
            self._emit_metric(
                "p03_corrupted_embeddings_total",
                1.0,
                reason="inf_detected",
            )
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.CORRUPTED_EMBEDDING,
                action_taken="FLAG_FOR_RECOMPUTE",
                details={
                    "entity_id": entity_id,
                    "reason": "inf_detected",
                },
            )

        return EdgeCaseResult(detected=False)

    async def check_backlog_overflow(
        self,
        space_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> EdgeCaseResult:
        """
        Check if st_hipp_events backlog exceeds threshold.

        Warning at 10K, critical at 50K pending events.

        Args:
            space_id: Space to check
            connection: Database connection

        Returns:
            EdgeCaseResult with backlog details (action: ADAPTIVE_BATCHING_*)
        """
        row = await connection.fetchrow(
            """
            SELECT COUNT(*) as pending_count
            FROM st_hipp_events
            WHERE space_id = $1
              AND processed_at IS NULL
            """,
            space_id,
        )

        pending = row["pending_count"] if row else 0

        if pending >= self._backlog_critical_threshold:
            self._emit_metric(
                "p03_backlog_overflow_total",
                1.0,
                severity="critical",
            )
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.BACKLOG_OVERFLOW,
                action_taken="ADAPTIVE_BATCHING_CRITICAL",
                details={
                    "pending_count": pending,
                    "threshold": self._backlog_critical_threshold,
                    "severity": "critical",
                    "space_id": space_id,
                },
            )
        elif pending >= self._backlog_warning_threshold:
            self._emit_metric(
                "p03_backlog_overflow_total",
                1.0,
                severity="warning",
            )
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.BACKLOG_OVERFLOW,
                action_taken="ADAPTIVE_BATCHING_WARNING",
                details={
                    "pending_count": pending,
                    "threshold": self._backlog_warning_threshold,
                    "severity": "warning",
                    "space_id": space_id,
                },
            )

        return EdgeCaseResult(detected=False)

    def check_duplicate_trigger(
        self,
        batch_hash: str,
        cycle_id: str,
    ) -> EdgeCaseResult:
        """
        Check for duplicate cycle trigger using batch_hash.

        Uses sliding window to prevent memory growth.
        Duplicate triggers are idempotently skipped.

        Args:
            batch_hash: Hash of the batch being processed
            cycle_id: ID of the cycle

        Returns:
            EdgeCaseResult with duplicate status (action: IDEMPOTENT_SKIP)
        """
        now = time.time()

        # Clean old hashes (older than window)
        cutoff = now - self.BATCH_HASH_WINDOW_SECONDS
        self._batch_hash_window = [(ts, h) for ts, h in self._batch_hash_window if ts >= cutoff]
        self._seen_batch_hashes = {h for _, h in self._batch_hash_window}

        if batch_hash in self._seen_batch_hashes:
            self._emit_metric("p03_duplicate_triggers_total", 1.0)
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.DUPLICATE_TRIGGER,
                action_taken="IDEMPOTENT_SKIP",
                details={
                    "batch_hash": batch_hash,
                    "cycle_id": cycle_id,
                },
            )

        # Add to window
        self._batch_hash_window.append((now, batch_hash))
        self._seen_batch_hashes.add(batch_hash)

        return EdgeCaseResult(detected=False)

    def check_memory_pressure(
        self,
        threshold: Optional[float] = None,
    ) -> EdgeCaseResult:
        """
        Check if memory usage exceeds threshold for R5 skip.

        When memory pressure is high, R5 dream phase should be skipped
        to prevent OOM conditions.

        Args:
            threshold: Memory usage threshold (default: 0.80)

        Returns:
            EdgeCaseResult with memory status (action: SKIP_R5_PHASE)
        """
        threshold = threshold or self._memory_pressure_threshold

        # Try to get memory usage via psutil
        usage_pct = 0.0
        try:
            import psutil

            process = psutil.Process()
            memory_info = process.memory_info()
            total_memory = psutil.virtual_memory().total
            usage_pct = memory_info.rss / total_memory
        except ImportError:
            # Fallback: gc-based rough estimation
            gc.collect()
            # Without psutil, we can't accurately measure
            # Return not detected to avoid false positives
            return EdgeCaseResult(detected=False)

        if usage_pct >= threshold:
            self._emit_metric("p03_r5_memory_skipped_total", 1.0)
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.MEMORY_PRESSURE,
                action_taken="SKIP_R5_PHASE",
                details={
                    "memory_usage_pct": round(usage_pct, 4),
                    "threshold": threshold,
                },
            )

        return EdgeCaseResult(detected=False)

    async def check_kg_explosion(
        self,
        space_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> EdgeCaseResult:
        """
        Check if KG node count exceeds threshold for partitioning.

        When KG exceeds 1M nodes, sharding should be enabled.

        Args:
            space_id: Space to check
            connection: Database connection

        Returns:
            EdgeCaseResult with KG status (action: ENABLE_KG_SHARDING)
        """
        row = await connection.fetchrow(
            """
            SELECT COUNT(*) as node_count
            FROM st_kg_dom
            WHERE space_id = $1
            """,
            space_id,
        )

        node_count = row["node_count"] if row else 0

        if node_count >= self._kg_node_threshold:
            self._emit_metric(
                "p03_kg_partition_events_total",
                1.0,
                space_id=space_id[:8],
            )
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.KG_EXPLOSION,
                action_taken="ENABLE_KG_SHARDING",
                details={
                    "node_count": node_count,
                    "threshold": self._kg_node_threshold,
                    "space_id": space_id,
                },
            )

        return EdgeCaseResult(detected=False)

    def check_p08_circuit_open_duration(
        self,
        circuit_open_since: Optional[float],
        threshold_seconds: Optional[float] = None,
    ) -> EdgeCaseResult:
        """
        Check if P08 circuit has been open too long.

        Args:
            circuit_open_since: Timestamp when circuit opened (None if closed)
            threshold_seconds: Threshold for alerting (default: 300s/5min)

        Returns:
            EdgeCaseResult with circuit status (action: QUEUE_LOCALLY)
        """
        if circuit_open_since is None:
            return EdgeCaseResult(detected=False)

        threshold = threshold_seconds or self.P08_CIRCUIT_OPEN_THRESHOLD_SECONDS
        now = time.time()
        open_duration = now - circuit_open_since

        if open_duration >= threshold:
            self._emit_metric(
                "p03_p08_circuit_open_duration_exceeded",
                1.0,
                duration_seconds=round(open_duration, 2),
            )
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.P08_CIRCUIT_OPEN,
                action_taken="QUEUE_LOCALLY",
                details={
                    "open_duration_seconds": round(open_duration, 2),
                    "threshold_seconds": threshold,
                },
            )

        return EdgeCaseResult(detected=False)

    async def flag_embedding_for_recompute(
        self,
        entity_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> None:
        """
        Flag corrupted embedding for P08 re-embedding.

        Args:
            entity_id: Entity with corrupted embedding
            connection: Database connection
        """
        await connection.execute(
            """
            UPDATE st_vec
            SET status = 'RECOMPUTE_REQUIRED',
                updated_at = $1
            WHERE entity_id = $2
            """,
            int(time.time() * 1000),
            entity_id,
        )
        self._emit_metric("p03_embeddings_flagged_for_recompute", 1.0)

    def can_skip_dream_phase(self) -> bool:
        """
        Check if R5 dream phase should be skipped due to memory pressure.

        Returns:
            True if memory pressure detected, R5 should be skipped.
        """
        result = self.check_memory_pressure()
        return result.detected

    def clear_batch_hash_cache(self) -> None:
        """Clear the batch hash duplicate detection cache."""
        self._batch_hash_window.clear()
        self._seen_batch_hashes.clear()

    def get_batch_hash_cache_size(self) -> int:
        """Get current size of batch hash cache."""
        return len(self._seen_batch_hashes)

    def _emit_metric(self, name: str, value: float, **labels: object) -> None:
        """Emit a metric if metrics exporter is available."""
        if self._metrics:
            self._metrics.emit(name, value, **labels)


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    check_name: str
    status: str  # "ok", "warning", "critical"
    details: dict = field(default_factory=dict)
    edge_case: Optional[EdgeCaseResult] = None


class P03HealthCheck:
    """
    Scheduled health check for P03 edge cases.

    Runs all edge case checks and returns aggregated results
    for monitoring and alerting.
    """

    def __init__(
        self,
        handler: P03EdgeCaseHandler,
    ) -> None:
        self._handler = handler

    async def run_all_checks(
        self,
        space_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> List[HealthCheckResult]:
        """
        Run all health checks and return results.

        Args:
            space_id: Space to check
            connection: Database connection

        Returns:
            List of HealthCheckResult with all check outcomes.
        """
        results: List[HealthCheckResult] = []

        # Check idle cycle
        idle_result = await self._handler.check_idle_cycle(space_id, connection=connection)
        if idle_result.detected:
            results.append(
                HealthCheckResult(
                    check_name="idle_cycle",
                    status="warning",
                    details=idle_result.details,
                    edge_case=idle_result,
                )
            )

        # Check backlog overflow
        backlog_result = await self._handler.check_backlog_overflow(space_id, connection=connection)
        if backlog_result.detected:
            results.append(
                HealthCheckResult(
                    check_name="backlog_overflow",
                    status=backlog_result.details.get("severity", "warning"),
                    details=backlog_result.details,
                    edge_case=backlog_result,
                )
            )

        # Check memory pressure
        memory_result = self._handler.check_memory_pressure()
        if memory_result.detected:
            results.append(
                HealthCheckResult(
                    check_name="memory_pressure",
                    status="warning",
                    details=memory_result.details,
                    edge_case=memory_result,
                )
            )

        # Check KG explosion
        kg_result = await self._handler.check_kg_explosion(space_id, connection=connection)
        if kg_result.detected:
            results.append(
                HealthCheckResult(
                    check_name="kg_explosion",
                    status="critical",
                    details=kg_result.details,
                    edge_case=kg_result,
                )
            )

        return results

    async def get_health_summary(
        self,
        space_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> dict:
        """
        Get a summary of health check status.

        Args:
            space_id: Space to check
            connection: Database connection

        Returns:
            Dict with overall status and individual check results.
        """
        results = await self.run_all_checks(space_id, connection=connection)

        # Determine overall status
        statuses = [r.status for r in results]
        if "critical" in statuses:
            overall = "critical"
        elif "warning" in statuses:
            overall = "warning"
        elif results:
            overall = "ok"
        else:
            overall = "healthy"

        return {
            "overall_status": overall,
            "checks_run": len(results) + 4,  # Include passed checks
            "issues_found": len(results),
            "issues": [
                {
                    "check": r.check_name,
                    "status": r.status,
                    "details": r.details,
                }
                for r in results
            ],
        }


def create_edge_case_handler(
    *,
    metrics: Optional["MetricsExporter"] = None,
    **config: object,
) -> P03EdgeCaseHandler:
    """
    Factory for P03EdgeCaseHandler.

    Args:
        metrics: Optional metrics exporter
        **config: Optional threshold overrides

    Returns:
        Configured P03EdgeCaseHandler instance.
    """
    return P03EdgeCaseHandler(metrics=metrics, **config)


def create_health_check(
    handler: Optional[P03EdgeCaseHandler] = None,
    *,
    metrics: Optional["MetricsExporter"] = None,
) -> P03HealthCheck:
    """
    Factory for P03HealthCheck.

    Args:
        handler: Optional edge case handler (created if not provided)
        metrics: Optional metrics exporter

    Returns:
        Configured P03HealthCheck instance.
    """
    if handler is None:
        handler = create_edge_case_handler(metrics=metrics)
    return P03HealthCheck(handler)
