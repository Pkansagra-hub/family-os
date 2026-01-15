"""
WriteResult Dataclasses — Issue 5.2.1

Structured write outcomes for TruthWriter layer operations.
Provides per-layer and aggregate success/failure tracking.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.1 — M24 TruthWriter module scaffolding)
    - Dossier §4.8 (R7 — Memory Layer Writes / Truth Update)

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class LayerWriteResult:
    """
    Result of writes to a single memory layer.

    Tracks success/failure counts and records failed IDs for
    error handling and retry logic.

    Attributes:
        layer: Target layer name (st_epi, st_sem, etc.)
        writes_attempted: Total write attempts
        writes_succeeded: Successful writes
        writes_failed: Failed writes
        failed_ids: Record IDs that failed
        error_message: Error description if any failure
        duration_ms: Time spent on this layer (MILLISECONDS)
    """

    layer: str
    writes_attempted: int
    writes_succeeded: int
    writes_failed: int
    failed_ids: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    duration_ms: int = 0

    @classmethod
    def success(
        cls,
        layer: str,
        count: int,
        duration_ms: int = 0,
    ) -> LayerWriteResult:
        """
        Factory for successful layer write result.

        Args:
            layer: Layer name
            count: Number of successful writes
            duration_ms: Time spent writing (MILLISECONDS)

        Returns:
            LayerWriteResult with all writes succeeded
        """
        return cls(
            layer=layer,
            writes_attempted=count,
            writes_succeeded=count,
            writes_failed=0,
            duration_ms=duration_ms,
        )

    @classmethod
    def failure(
        cls,
        layer: str,
        error: str,
        failed_ids: Optional[List[str]] = None,
    ) -> LayerWriteResult:
        """
        Factory for failed layer write result.

        Args:
            layer: Layer name
            error: Error message
            failed_ids: List of record IDs that failed

        Returns:
            LayerWriteResult with failure info
        """
        ids = failed_ids or []
        return cls(
            layer=layer,
            writes_attempted=len(ids) or 1,
            writes_succeeded=0,
            writes_failed=len(ids) or 1,
            failed_ids=ids,
            error_message=error,
        )

    @classmethod
    def partial(
        cls,
        layer: str,
        succeeded: int,
        failed_ids: List[str],
        error: Optional[str] = None,
    ) -> LayerWriteResult:
        """
        Factory for partial success result.

        Args:
            layer: Layer name
            succeeded: Number of successful writes
            failed_ids: Record IDs that failed
            error: Optional error message

        Returns:
            LayerWriteResult with partial success
        """
        return cls(
            layer=layer,
            writes_attempted=succeeded + len(failed_ids),
            writes_succeeded=succeeded,
            writes_failed=len(failed_ids),
            failed_ids=failed_ids,
            error_message=error,
        )

    @property
    def is_success(self) -> bool:
        """True if all writes succeeded."""
        return self.writes_failed == 0

    @property
    def is_partial(self) -> bool:
        """True if some but not all writes succeeded."""
        return 0 < self.writes_succeeded < self.writes_attempted

    def to_dict(self) -> Dict[str, object]:
        """Convert to dictionary for serialization."""
        return {
            "layer": self.layer,
            "writes_attempted": self.writes_attempted,
            "writes_succeeded": self.writes_succeeded,
            "writes_failed": self.writes_failed,
            "failed_ids": self.failed_ids,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
        }


@dataclass
class WriteResult:
    """
    Aggregate result of all layer writes during R7.

    Combines results from all layer writers and provides
    summary statistics for monitoring and error handling.

    Attributes:
        total_attempted: Total writes attempted across all layers
        total_succeeded: Total successful writes
        total_failed: Total failed writes
        by_layer: Per-layer results keyed by layer name
        failed_decision_ids: All record IDs that failed
        total_duration_ms: Total time for all writes (MILLISECONDS)
    """

    total_attempted: int
    total_succeeded: int
    total_failed: int
    by_layer: Dict[str, LayerWriteResult] = field(default_factory=dict)
    failed_decision_ids: List[str] = field(default_factory=list)
    total_duration_ms: int = 0

    @classmethod
    def from_layer_results(cls, results: List[LayerWriteResult]) -> WriteResult:
        """
        Construct from list of layer results.

        Args:
            results: List of LayerWriteResult from each layer

        Returns:
            Aggregated WriteResult
        """
        by_layer = {r.layer: r for r in results}
        failed_ids = [record_id for r in results for record_id in r.failed_ids]

        return cls(
            total_attempted=sum(r.writes_attempted for r in results),
            total_succeeded=sum(r.writes_succeeded for r in results),
            total_failed=sum(r.writes_failed for r in results),
            by_layer=by_layer,
            failed_decision_ids=failed_ids,
            total_duration_ms=sum(r.duration_ms for r in results),
        )

    @classmethod
    def empty(cls) -> WriteResult:
        """Create empty result for no-op cases."""
        return cls(
            total_attempted=0,
            total_succeeded=0,
            total_failed=0,
        )

    @property
    def is_success(self) -> bool:
        """True if all writes succeeded."""
        return self.total_failed == 0

    @property
    def is_partial(self) -> bool:
        """True if some but not all writes succeeded."""
        return 0 < self.total_succeeded < self.total_attempted

    @property
    def success_rate(self) -> float:
        """Percentage of successful writes (0.0 to 1.0)."""
        if self.total_attempted == 0:
            return 1.0
        return self.total_succeeded / self.total_attempted

    @property
    def layers_written(self) -> List[str]:
        """List of layers that had writes."""
        return list(self.by_layer.keys())

    @property
    def failed_layers(self) -> List[str]:
        """List of layers that had failures."""
        return [name for name, result in self.by_layer.items() if not result.is_success]

    def get_layer_result(self, layer: str) -> Optional[LayerWriteResult]:
        """Get result for a specific layer."""
        return self.by_layer.get(layer)

    def to_dict(self) -> Dict[str, object]:
        """Convert to dictionary for serialization."""
        return {
            "total_attempted": self.total_attempted,
            "total_succeeded": self.total_succeeded,
            "total_failed": self.total_failed,
            "by_layer": {k: v.to_dict() for k, v in self.by_layer.items()},
            "failed_decision_ids": self.failed_decision_ids,
            "total_duration_ms": self.total_duration_ms,
            "success_rate": self.success_rate,
        }

    def to_summary(self) -> str:
        """Human-readable summary for logging."""
        if self.is_success:
            return f"WriteResult: {self.total_succeeded}/{self.total_attempted} succeeded across {len(self.layers_written)} layers"
        return (
            f"WriteResult: {self.total_succeeded}/{self.total_attempted} succeeded, "
            f"{self.total_failed} failed in layers: {', '.join(self.failed_layers)}"
        )
