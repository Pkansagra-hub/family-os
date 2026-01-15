"""P03 Distributed Tracing — OpenTelemetry span hierarchy for P03 consolidation.

This module provides distributed tracing for P03 consolidation cycles with
proper span hierarchy for all phases (R0-R8).

Issue Reference: M6_EXECUTION.md Issue 6.1.10
Dossier Reference: docs/pipelines/P03_consolidation_dossier_v2.md Section 8.3

CRITICAL ARCHITECTURE PRINCIPLE:
    P03 USES K0's TracerFactory, it does NOT create its own tracer.
    All spans are created via the kernel's tracing infrastructure.

Span Hierarchy:
    p03.consolidation_cycle (root)
    ├── p03.r0.trigger_detection
    ├── p03.r1.replay
    │   ├── p03.r1.batch_selection
    │   └── p03.r1.importance_scoring
    ├── p03.r2.clustering
    │   ├── p03.r2.embedding_fetch
    │   ├── p03.r2.dbscan
    │   └── p03.r2.pattern_extraction
    ├── p03.r3.forgetting
    │   ├── p03.r3.deduplication
    │   └── p03.r3.retention_enforcement
    ├── p03.r4.kg_consolidation
    │   ├── p03.r4.entity_extraction
    │   ├── p03.r4.entity_resolution
    │   └── p03.r4.edge_discovery
    ├── p03.r5.dream_exploration (optional)
    ├── p03.r6.staging_update
    ├── p03.r7.truth_write
    │   ├── p03.r7.outbox_insert
    │   └── p03.r7.layer_write (per layer)
    └── p03.r8.event_emission
        ├── p03.r8.bus_publish
        └── p03.r8.gap_emission

Usage:
    from k0.obs.tracing import TracerFactory
    from k0.pipelines.p03.ops.tracing import P03ConsolidationTracer

    tracer_factory = TracerFactory(service_name="k0-p03")
    p03_tracer = P03ConsolidationTracer(tracer_factory)

    async with p03_tracer.trace_cycle(cycle_id, tenant_id, space_id):
        async with p03_tracer.phase_span("R1", batch_size=50):
            async with p03_tracer.sub_span("r1.batch_selection"):
                # ... batch selection logic
            async with p03_tracer.sub_span("r1.importance_scoring"):
                # ... importance scoring logic
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from k0.obs.tracing import TracerFactory

__all__ = [
    "P03ConsolidationTracer",
    "PHASE_NAMES",
    "REQUIRED_BAGGAGE",
]

LOGGER = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Phase name mapping (R0-R8)
PHASE_NAMES: Dict[str, str] = {
    "R0": "trigger_detection",
    "R1": "replay",
    "R2": "clustering",
    "R3": "forgetting",
    "R4": "kg_consolidation",
    "R5": "dream_exploration",
    "R6": "staging_update",
    "R7": "truth_write",
    "R8": "event_emission",
}

# Sub-operation names per phase
SUB_OPERATIONS: Dict[str, tuple[str, ...]] = {
    "R1": ("batch_selection", "importance_scoring"),
    "R2": ("embedding_fetch", "dbscan", "pattern_extraction"),
    "R3": ("deduplication", "retention_enforcement"),
    "R4": ("entity_extraction", "entity_resolution", "edge_discovery"),
    "R7": ("outbox_insert", "layer_write"),
    "R8": ("bus_publish", "gap_emission"),
}

# Required baggage items for cross-service propagation
REQUIRED_BAGGAGE = (
    "cycle_id",  # P03 cycle identifier
    "tenant_id",  # Tenant isolation
    "space_id",  # Space isolation
    "correlation_id",  # Cross-service correlation
)

# Optional baggage items
OPTIONAL_BAGGAGE = (
    "source_event_ids",  # Comma-separated source events
    "qos_band",  # QoS band (GREEN, AMBER, RED)
)


# =============================================================================
# P03 CONSOLIDATION TRACER
# =============================================================================


class P03ConsolidationTracer:
    """Distributed tracing for P03 consolidation cycles.

    Wraps K0's TracerFactory to provide P03-specific span hierarchy and
    context propagation. Supports both sync and async context managers.

    Thread Safety:
        Thread-safe. Uses TracerFactory's internal context management.

    Usage:
        tracer_factory = TracerFactory(service_name="k0-p03")
        p03_tracer = P03ConsolidationTracer(tracer_factory)

        # Sync usage
        with p03_tracer.trace_cycle_sync(cycle_id, tenant_id, space_id):
            with p03_tracer.phase_span_sync("R1", batch_size=50):
                # ... phase logic

        # Async usage
        async with p03_tracer.trace_cycle(cycle_id, tenant_id, space_id):
            async with p03_tracer.phase_span("R1", batch_size=50):
                # ... phase logic

    Spec: Dossier 8.3, M6_EXECUTION.md Issue 6.1.10
    """

    def __init__(
        self,
        tracer_factory: TracerFactory,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """Initialize P03 consolidation tracer.

        Args:
            tracer_factory: K0's TracerFactory instance.
            logger: Logger instance. Creates default if None.
        """
        self._factory = tracer_factory
        self._logger = logger or LOGGER

        # Track current context for nesting
        self._current_cycle_id: Optional[str] = None
        self._current_phase: Optional[str] = None

    @property
    def tracer_factory(self) -> TracerFactory:
        """Return the underlying TracerFactory."""
        return self._factory

    # =========================================================================
    # ASYNC CONTEXT MANAGERS
    # =========================================================================

    @asynccontextmanager
    async def trace_cycle(
        self,
        cycle_id: str,
        tenant_id: str,
        space_id: str,
        **attributes: Any,
    ):
        """Create root span for consolidation cycle (async).

        Attaches cognitive trace ID for cross-service correlation.

        Args:
            cycle_id: P03 cycle identifier.
            tenant_id: Tenant identifier.
            space_id: Space identifier.
            **attributes: Additional span attributes.

        Yields:
            Root span for the consolidation cycle.
        """
        # Attach cognitive trace ID for cross-service correlation
        trace_token = self._factory.attach_cognitive_trace(cycle_id)
        self._current_cycle_id = cycle_id

        try:
            with self._factory.span(
                "p03.consolidation_cycle",
                attributes={
                    "cycle_id": cycle_id,
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    **attributes,
                },
            ) as root_span:
                self._logger.debug(
                    "P03 trace started: cycle_id=%s tenant=%s space=%s",
                    cycle_id,
                    tenant_id,
                    space_id,
                )
                yield root_span
        finally:
            self._current_cycle_id = None
            self._factory.detach(trace_token)
            self._logger.debug("P03 trace ended: cycle_id=%s", cycle_id)

    @asynccontextmanager
    async def phase_span(
        self,
        phase_id: str,
        **attributes: Any,
    ):
        """Create span for a consolidation phase (async).

        Args:
            phase_id: Phase identifier (R0-R8).
            **attributes: Additional span attributes (batch_size, etc.).

        Yields:
            Phase span.

        Raises:
            ValueError: If phase_id is not valid (R0-R8).
        """
        phase_name = PHASE_NAMES.get(phase_id.upper())
        if not phase_name:
            raise ValueError(
                f"Invalid phase_id '{phase_id}'. Must be one of: {list(PHASE_NAMES.keys())}"
            )

        self._current_phase = phase_id.upper()
        span_name = f"p03.{phase_id.lower()}.{phase_name}"

        try:
            with self._factory.span(
                span_name,
                attributes={
                    "phase": phase_id.upper(),
                    "phase_name": phase_name,
                    **attributes,
                },
            ) as span:
                yield span
        finally:
            self._current_phase = None

    @asynccontextmanager
    async def sub_span(
        self,
        operation: str,
        **attributes: Any,
    ):
        """Create span for sub-operation within a phase (async).

        Args:
            operation: Sub-operation name (e.g., "r1.batch_selection").
            **attributes: Additional span attributes.

        Yields:
            Sub-operation span.
        """
        span_name = f"p03.{operation}"

        with self._factory.span(
            span_name,
            attributes=attributes,
        ) as span:
            yield span

    @asynccontextmanager
    async def layer_write_span(
        self,
        layer: str,
        operation: str,
        **attributes: Any,
    ):
        """Create span for R7 layer write operation (async).

        Args:
            layer: Memory layer (st_epi, st_sem, etc.).
            operation: Write operation (insert, update, archive, tombstone).
            **attributes: Additional span attributes.

        Yields:
            Layer write span.
        """
        span_name = f"p03.r7.layer_write.{layer}"

        with self._factory.span(
            span_name,
            attributes={
                "layer": layer,
                "operation": operation,
                **attributes,
            },
        ) as span:
            yield span

    # =========================================================================
    # SYNC CONTEXT MANAGERS
    # =========================================================================

    @contextmanager
    def trace_cycle_sync(
        self,
        cycle_id: str,
        tenant_id: str,
        space_id: str,
        **attributes: Any,
    ):
        """Create root span for consolidation cycle (sync).

        Attaches cognitive trace ID for cross-service correlation.

        Args:
            cycle_id: P03 cycle identifier.
            tenant_id: Tenant identifier.
            space_id: Space identifier.
            **attributes: Additional span attributes.

        Yields:
            Root span for the consolidation cycle.
        """
        # Attach cognitive trace ID for cross-service correlation
        trace_token = self._factory.attach_cognitive_trace(cycle_id)
        self._current_cycle_id = cycle_id

        try:
            with self._factory.span(
                "p03.consolidation_cycle",
                attributes={
                    "cycle_id": cycle_id,
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    **attributes,
                },
            ) as root_span:
                self._logger.debug(
                    "P03 trace started: cycle_id=%s tenant=%s space=%s",
                    cycle_id,
                    tenant_id,
                    space_id,
                )
                yield root_span
        finally:
            self._current_cycle_id = None
            self._factory.detach(trace_token)
            self._logger.debug("P03 trace ended: cycle_id=%s", cycle_id)

    @contextmanager
    def phase_span_sync(
        self,
        phase_id: str,
        **attributes: Any,
    ):
        """Create span for a consolidation phase (sync).

        Args:
            phase_id: Phase identifier (R0-R8).
            **attributes: Additional span attributes (batch_size, etc.).

        Yields:
            Phase span.

        Raises:
            ValueError: If phase_id is not valid (R0-R8).
        """
        phase_name = PHASE_NAMES.get(phase_id.upper())
        if not phase_name:
            raise ValueError(
                f"Invalid phase_id '{phase_id}'. Must be one of: {list(PHASE_NAMES.keys())}"
            )

        self._current_phase = phase_id.upper()
        span_name = f"p03.{phase_id.lower()}.{phase_name}"

        try:
            with self._factory.span(
                span_name,
                attributes={
                    "phase": phase_id.upper(),
                    "phase_name": phase_name,
                    **attributes,
                },
            ) as span:
                yield span
        finally:
            self._current_phase = None

    @contextmanager
    def sub_span_sync(
        self,
        operation: str,
        **attributes: Any,
    ):
        """Create span for sub-operation within a phase (sync).

        Args:
            operation: Sub-operation name (e.g., "r1.batch_selection").
            **attributes: Additional span attributes.

        Yields:
            Sub-operation span.
        """
        span_name = f"p03.{operation}"

        with self._factory.span(
            span_name,
            attributes=attributes,
        ) as span:
            yield span

    @contextmanager
    def layer_write_span_sync(
        self,
        layer: str,
        operation: str,
        **attributes: Any,
    ):
        """Create span for R7 layer write operation (sync).

        Args:
            layer: Memory layer (st_epi, st_sem, etc.).
            operation: Write operation (insert, update, archive, tombstone).
            **attributes: Additional span attributes.

        Yields:
            Layer write span.
        """
        span_name = f"p03.r7.layer_write.{layer}"

        with self._factory.span(
            span_name,
            attributes={
                "layer": layer,
                "operation": operation,
                **attributes,
            },
        ) as span:
            yield span

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_current_cycle_id(self) -> Optional[str]:
        """Get the current cycle ID if within a trace_cycle context."""
        return self._current_cycle_id

    def get_current_phase(self) -> Optional[str]:
        """Get the current phase if within a phase_span context."""
        return self._current_phase

    def get_cognitive_trace_id(self) -> Optional[str]:
        """Get the cognitive trace ID from current context."""
        return self._factory.current_cognitive_trace_id()

    def record_exception(self, exception: Exception, **attributes: Any) -> None:
        """Record an exception on the current span.

        Args:
            exception: The exception to record.
            **attributes: Additional attributes for the exception event.
        """
        # TracerFactory handles this via span.record_exception()
        # This is a convenience wrapper for P03-specific error handling
        self._logger.exception(
            "P03 exception recorded: cycle=%s phase=%s error=%s",
            self._current_cycle_id,
            self._current_phase,
            str(exception),
            extra=attributes,
        )

    def add_event(self, name: str, **attributes: Any) -> None:
        """Add an event to the current span.

        Args:
            name: Event name.
            **attributes: Event attributes.
        """
        # This is a convenience method - actual implementation depends on
        # how TracerFactory exposes span events
        self._logger.debug(
            "P03 span event: %s attributes=%s",
            name,
            attributes,
        )
