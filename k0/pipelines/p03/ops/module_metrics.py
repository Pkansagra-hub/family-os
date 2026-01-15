"""P03 Module Metrics — Performance instrumentation for P03 modules.

This module provides decorators and helpers for instrumenting P03 modules
(M18-M25) with performance metrics.

Issue Reference: M6_EXECUTION.md Issue 6.1.7
Dossier Reference: docs/pipelines/P03_consolidation_dossier_v2.md Section 8.2.5

Module Registry:
    M18: R2EpisodicIntegrator (r2_episodic_integrator.py)
    M19: DuplicateDetector (duplicate_detector.py)
    M20: RetentionEnforcer (retention_enforcer.py)
    M21: R4KGConsolidator (r4_kg_consolidator.py)
    M22: DreamExplorer (optional, not implemented)
    M23: R1ImportanceScorer (r1_importance_scorer.py)
    M24: R7TruthWriter (r7_truth_writer.py)
    M25: P03GapEmitter (gap_emitter.py)

Usage:
    from k0.pipelines.p03.ops.module_metrics import module_metric, ModuleMetricContext

    # Using decorator
    @module_metric("M19")
    async def detect_duplicates(self, items: list) -> list:
        # ... duplicate detection logic
        return results

    # Using context manager
    async with ModuleMetricContext(registry, tenant_id, "M20") as ctx:
        result = await enforcer.evaluate(record)
        ctx.record_items(1, outcome="success")
"""

from __future__ import annotations

import functools
import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

if TYPE_CHECKING:
    from k0.pipelines.p03.ops.metrics import P03MetricsRegistry

__all__ = [
    "module_metric",
    "module_metric_sync",
    "ModuleMetricContext",
    "MODULE_NAMES",
]

LOGGER = logging.getLogger(__name__)

# Type variable for decorated functions
F = TypeVar("F", bound=Callable[..., Any])


# =============================================================================
# CONSTANTS
# =============================================================================

# Module ID to name mapping
MODULE_NAMES = {
    "M18": "R2EpisodicIntegrator",
    "M19": "DuplicateDetector",
    "M20": "RetentionEnforcer",
    "M21": "R4KGConsolidator",
    "M22": "DreamExplorer",
    "M23": "R1ImportanceScorer",
    "M24": "R7TruthWriter",
    "M25": "P03GapEmitter",
}

# Outcome labels
OUTCOME_SUCCESS = "success"
OUTCOME_SKIP = "skip"
OUTCOME_ERROR = "error"


# =============================================================================
# DECORATOR: ASYNC MODULE METRIC
# =============================================================================


def module_metric(
    module_id: str,
    registry_attr: str = "_metrics",
    tenant_id_attr: str = "_tenant_id",
    items_attr: Optional[str] = None,
) -> Callable[[F], F]:
    """Decorator for async module performance instrumentation.

    Automatically measures execution time and emits metrics to P03MetricsRegistry.
    Expects the decorated method to be on a class with `_metrics` and `_tenant_id`
    attributes.

    Args:
        module_id: Module ID (M18-M25).
        registry_attr: Attribute name for P03MetricsRegistry on self.
        tenant_id_attr: Attribute name for tenant_id on self.
        items_attr: Optional attribute name for items count on result.

    Returns:
        Decorated async function.

    Example:
        class DuplicateDetector:
            def __init__(self, metrics: P03MetricsRegistry, tenant_id: str):
                self._metrics = metrics
                self._tenant_id = tenant_id

            @module_metric("M19")
            async def detect(self, items: list) -> list:
                # ... detection logic
                return deduplicated
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            registry: Optional[P03MetricsRegistry] = getattr(self, registry_attr, None)
            tenant_id: str = getattr(self, tenant_id_attr, "unknown")

            start = time.monotonic()
            outcome = OUTCOME_SUCCESS
            items_processed = 1

            try:
                result = await func(self, *args, **kwargs)

                # Optionally extract items count from result
                if items_attr and hasattr(result, items_attr):
                    items_processed = getattr(result, items_attr)
                elif isinstance(result, (list, tuple)):
                    items_processed = len(result)

                return result
            except Exception:
                outcome = OUTCOME_ERROR
                raise
            finally:
                duration_s = time.monotonic() - start

                if registry:
                    registry.emit_module_duration(
                        tenant_id=tenant_id,
                        module=module_id,
                        duration_s=duration_s,
                    )
                    registry.emit_module_items_processed(
                        tenant_id=tenant_id,
                        module=module_id,
                        outcome=outcome,
                        count=items_processed,
                    )

                LOGGER.debug(
                    "Module %s completed: duration=%.4fs outcome=%s items=%d",
                    module_id,
                    duration_s,
                    outcome,
                    items_processed,
                )

        return wrapper  # type: ignore[return-value]

    return decorator


# =============================================================================
# DECORATOR: SYNC MODULE METRIC
# =============================================================================


def module_metric_sync(
    module_id: str,
    registry_attr: str = "_metrics",
    tenant_id_attr: str = "_tenant_id",
    items_attr: Optional[str] = None,
) -> Callable[[F], F]:
    """Decorator for sync module performance instrumentation.

    Same as module_metric but for synchronous functions.

    Args:
        module_id: Module ID (M18-M25).
        registry_attr: Attribute name for P03MetricsRegistry on self.
        tenant_id_attr: Attribute name for tenant_id on self.
        items_attr: Optional attribute name for items count on result.

    Returns:
        Decorated sync function.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            registry: Optional[P03MetricsRegistry] = getattr(self, registry_attr, None)
            tenant_id: str = getattr(self, tenant_id_attr, "unknown")

            start = time.monotonic()
            outcome = OUTCOME_SUCCESS
            items_processed = 1

            try:
                result = func(self, *args, **kwargs)

                # Optionally extract items count from result
                if items_attr and hasattr(result, items_attr):
                    items_processed = getattr(result, items_attr)
                elif isinstance(result, (list, tuple)):
                    items_processed = len(result)

                return result
            except Exception:
                outcome = OUTCOME_ERROR
                raise
            finally:
                duration_s = time.monotonic() - start

                if registry:
                    registry.emit_module_duration(
                        tenant_id=tenant_id,
                        module=module_id,
                        duration_s=duration_s,
                    )
                    registry.emit_module_items_processed(
                        tenant_id=tenant_id,
                        module=module_id,
                        outcome=outcome,
                        count=items_processed,
                    )

                LOGGER.debug(
                    "Module %s completed: duration=%.4fs outcome=%s items=%d",
                    module_id,
                    duration_s,
                    outcome,
                    items_processed,
                )

        return wrapper  # type: ignore[return-value]

    return decorator


# =============================================================================
# CONTEXT MANAGER: MODULE METRIC CONTEXT
# =============================================================================


class ModuleMetricContext:
    """Context manager for module performance metrics.

    Provides more control than the decorator, allowing manual item counting
    and outcome setting.

    Usage:
        async with ModuleMetricContext(registry, tenant_id, "M20") as ctx:
            for record in records:
                result = await enforcer.evaluate(record)
                if result.decision == "KEEP":
                    ctx.record_items(1, outcome="success")
                else:
                    ctx.record_items(1, outcome="skip")
    """

    def __init__(
        self,
        registry: P03MetricsRegistry,
        tenant_id: str,
        module_id: str,
    ) -> None:
        """Initialize module metric context.

        Args:
            registry: P03MetricsRegistry instance.
            tenant_id: Tenant identifier.
            module_id: Module ID (M18-M25).
        """
        self._registry = registry
        self._tenant_id = tenant_id
        self._module_id = module_id
        self._start_time: float = 0.0
        self._items_by_outcome: dict[str, int] = {
            OUTCOME_SUCCESS: 0,
            OUTCOME_SKIP: 0,
            OUTCOME_ERROR: 0,
        }
        self._has_error = False

    def record_items(self, count: int = 1, outcome: str = OUTCOME_SUCCESS) -> None:
        """Record processed items.

        Args:
            count: Number of items processed.
            outcome: Processing outcome (success, skip, error).
        """
        if outcome not in self._items_by_outcome:
            outcome = OUTCOME_SUCCESS
        self._items_by_outcome[outcome] += count

    def record_error(self) -> None:
        """Mark that an error occurred (for duration tracking)."""
        self._has_error = True

    async def __aenter__(self) -> "ModuleMetricContext":
        """Enter async context."""
        self._start_time = time.monotonic()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        """Exit async context and emit metrics."""
        duration_s = time.monotonic() - self._start_time

        # Emit duration
        self._registry.emit_module_duration(
            tenant_id=self._tenant_id,
            module=self._module_id,
            duration_s=duration_s,
        )

        # Emit items by outcome
        for outcome, count in self._items_by_outcome.items():
            if count > 0:
                self._registry.emit_module_items_processed(
                    tenant_id=self._tenant_id,
                    module=self._module_id,
                    outcome=outcome,
                    count=count,
                )

        # If exception occurred, record error
        if exc_type is not None:
            self._registry.emit_module_items_processed(
                tenant_id=self._tenant_id,
                module=self._module_id,
                outcome=OUTCOME_ERROR,
                count=1,
            )

        total_items = sum(self._items_by_outcome.values())
        LOGGER.debug(
            "Module %s completed: duration=%.4fs items=%d (success=%d skip=%d error=%d)",
            self._module_id,
            duration_s,
            total_items,
            self._items_by_outcome[OUTCOME_SUCCESS],
            self._items_by_outcome[OUTCOME_SKIP],
            self._items_by_outcome[OUTCOME_ERROR],
        )

    def __enter__(self) -> "ModuleMetricContext":
        """Enter sync context."""
        self._start_time = time.monotonic()
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        """Exit sync context and emit metrics."""
        duration_s = time.monotonic() - self._start_time

        # Emit duration
        self._registry.emit_module_duration(
            tenant_id=self._tenant_id,
            module=self._module_id,
            duration_s=duration_s,
        )

        # Emit items by outcome
        for outcome, count in self._items_by_outcome.items():
            if count > 0:
                self._registry.emit_module_items_processed(
                    tenant_id=self._tenant_id,
                    module=self._module_id,
                    outcome=outcome,
                    count=count,
                )

        # If exception occurred, record error
        if exc_type is not None:
            self._registry.emit_module_items_processed(
                tenant_id=self._tenant_id,
                module=self._module_id,
                outcome=OUTCOME_ERROR,
                count=1,
            )


# =============================================================================
# HELPER: CLUSTERING METRICS
# =============================================================================


def emit_clustering_metrics(
    registry: P03MetricsRegistry,
    tenant_id: str,
    clusters: list[Any],
) -> None:
    """Emit M18 (R2EpisodicIntegrator) clustering metrics.

    Helper function for emitting cluster creation statistics.

    Args:
        registry: P03MetricsRegistry instance.
        tenant_id: Tenant identifier.
        clusters: List of cluster objects (must have len()).
    """
    cluster_sizes = [len(c) if hasattr(c, "__len__") else 1 for c in clusters]

    registry.emit_clustering_stats(
        tenant_id=tenant_id,
        clusters_created=len(clusters),
        cluster_sizes=cluster_sizes,
    )

    LOGGER.debug(
        "M18 clustering metrics: clusters=%d sizes=%s",
        len(clusters),
        cluster_sizes[:5],  # Log first 5 for brevity
    )
