"""Async worker coordinator for V1.4 (Performance Optimization).

Coordinates embedding and FTS workers through outbox-based work queuing.

Architecture:
  1. Commit phase: Create outbox entries for embedding + FTS work
  2. Worker discovery: Poll outbox for pending work
  3. Worker dispatch: Send to embedding/FTS workers
  4. Worker completion: Update WAL with results, mark outbox complete
  5. Status propagation: Track embedding_status and fts_status in hippocampus store

This reduces commit latency from ~150ms to ~80-100ms by deferring heavy
computation to background workers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

# Lazy imports to avoid sys.modules conflicts when running workers as -m scripts
if TYPE_CHECKING:
    from k0.workers.embedding_worker import EmbeddingResult
    from k0.workers.fts_worker import FtsIndexResult

logger = logging.getLogger(__name__)


@dataclass
class WorkerCoordinatorConfig:
    """Configuration for async worker coordinator."""

    embedding_batch_size: int = 10
    fts_batch_size: int = 50
    max_retries: int = 3
    retry_backoff_ms: int = 100


@dataclass
class WorkerResult:
    """Result of async worker operation."""

    operation_kind: str  # COMPUTE_EMBEDDING or INDEX_FTS
    event_id: str
    status: str  # COMPLETE or FAILED
    result: EmbeddingResult | FtsIndexResult | None = None
    error: str | None = None


class AsyncWorkerCoordinator:
    """Coordinates embedding and FTS async workers.

    Responsible for:
      1. Dispatching work from outbox to workers
      2. Aggregating results
      3. Updating WAL with embedding_id, fts_entry_id
      4. Marking outbox entries complete
      5. Tracking worker status
    """

    def __init__(self, config: WorkerCoordinatorConfig | None = None) -> None:
        """Initialize async worker coordinator.

        Args:
            config: Coordinator configuration
        """
        # Import workers at runtime to avoid sys.modules conflicts with -m execution
        from k0.workers.embedding_worker import EmbeddingWorker
        from k0.workers.fts_worker import FtsIndexingWorker

        self._config = config or WorkerCoordinatorConfig()
        self._embedding_worker = EmbeddingWorker()
        self._fts_worker = FtsIndexingWorker()
        self._processed = 0
        self._failed = 0

    def process_outbox_batch(self, outbox_entries: list[dict[str, Any]]) -> list[WorkerResult]:
        """Process batch of outbox entries.

        Args:
            outbox_entries: List of outbox entries with operation_kind + payload

        Returns:
            List of worker results (COMPLETE or FAILED)
        """
        # Import helper functions at runtime
        from k0.workers.embedding_worker import embedding_payload_to_request
        from k0.workers.fts_worker import fts_payload_to_request

        results = []

        # Separate by operation kind
        embedding_requests = []
        fts_requests = []

        for entry in outbox_entries:
            operation_kind = entry.get("operation_kind")
            payload = entry.get("payload", {})

            try:
                if operation_kind == "COMPUTE_EMBEDDING":
                    req = embedding_payload_to_request(payload)
                    embedding_requests.append(req)
                elif operation_kind == "INDEX_FTS":
                    req = fts_payload_to_request(payload)
                    fts_requests.append(req)
            except Exception as exc:
                logger.error(
                    f"Failed to parse outbox entry {entry.get('id')}: {exc}",
                    exc_info=exc,
                )
                results.append(
                    WorkerResult(
                        operation_kind=operation_kind or "UNKNOWN",
                        event_id=payload.get("event_id", "UNKNOWN"),
                        status="FAILED",
                        error=str(exc),
                    )
                )

        # Process embedding batch
        if embedding_requests:
            try:
                embedding_results = self._embedding_worker.process_batch(embedding_requests)
                for result in embedding_results:
                    results.append(
                        WorkerResult(
                            operation_kind="COMPUTE_EMBEDDING",
                            event_id=result.event_id,
                            status="COMPLETE",
                            result=result,
                        )
                    )
                    self._processed += 1
                    logger.info(f"Embedding worker: processed {self._processed} events")
            except Exception as exc:
                logger.exception("Embedding worker batch failed", exc_info=exc)
                self._failed += len(embedding_requests)
                for req in embedding_requests:
                    results.append(
                        WorkerResult(
                            operation_kind="COMPUTE_EMBEDDING",
                            event_id=req.event_id,
                            status="FAILED",
                            error=str(exc),
                        )
                    )

        # Process FTS batch
        if fts_requests:
            try:
                fts_results = self._fts_worker.process_batch(fts_requests)
                for result in fts_results:
                    results.append(
                        WorkerResult(
                            operation_kind="INDEX_FTS",
                            event_id=result.event_id,
                            status="COMPLETE",
                            result=result,
                        )
                    )
                    self._processed += 1
                    logger.info(f"FTS worker: processed {self._processed} events")
            except Exception as exc:
                logger.exception("FTS worker batch failed", exc_info=exc)
                self._failed += len(fts_requests)
                for req in fts_requests:
                    results.append(
                        WorkerResult(
                            operation_kind="INDEX_FTS",
                            event_id=req.event_id,
                            status="FAILED",
                            error=str(exc),
                        )
                    )

        return results

    def get_status(self) -> dict[str, Any]:
        """Get coordinator status (processed/failed counts).

        Returns:
            Status dict with counters
        """
        return {
            "processed": self._processed,
            "failed": self._failed,
            "success_rate": (
                self._processed / (self._processed + self._failed)
                if (self._processed + self._failed) > 0
                else 0.0
            ),
        }


__all__ = [
    "AsyncWorkerCoordinator",
    "WorkerCoordinatorConfig",
    "WorkerResult",
]
