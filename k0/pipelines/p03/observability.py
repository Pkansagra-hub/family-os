"""
P03ObservabilityContext - Tracing, timing, and metrics aggregation.

This module implements the observability context carried through the P03
envelope, providing distributed tracing, phase timing, and metrics collection.

Spec Reference: docs/pipelines/P03_envelope_fields_discovery.md section 19.1
Issue Reference: M1_EXECUTION.md Issue 1.1.6 (context), Issue 1.2.4 (logging)

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.

TRACE ID CONVENTION (LOCKED):
    P03 uses `trace_id` as the cognitive trace identifier.
    This is the same as `cognitive_trace_id` used elsewhere in K0/K1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .context import generate_ulid

# =============================================================================
# CONSTANTS
# =============================================================================

PIPELINE_ID = "P03_CONSOLIDATE"

# Valid phase names for validation
VALID_PHASES = frozenset(
    {
        "R0",
        "R1",
        "R2",
        "R3",
        "R4",
        "R5",
        "R6",
        "R7",
        "R8",
    }
)


# =============================================================================
# R1 PHASE METRICS (Issue 4.1.7)
# =============================================================================


# Performance thresholds from Dossier Section 8.2
R1_WARNING_THRESHOLD_MS = 10_000  # Log warning at 10 seconds
R1_ERROR_THRESHOLD_MS = 18_000  # R1 must complete in <5% of cycle time (360s * 0.05 = 18s)

# Histogram buckets for Prometheus metrics (from spec)
IMPORTANCE_SCORE_BUCKETS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
EDGE_WEIGHT_BUCKETS = (0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0)
DURATION_MS_BUCKETS = (100, 500, 1000, 5000, 10000, 18000)


@dataclass
class R1PhaseMetrics:
    """
    Metrics collected during R1 hippocampal replay phase.

    This dataclass captures observability data for importance scoring,
    Hebbian learning, and timing during R1 execution.

    Spec Reference: M4_EXECUTION.md Issue 4.1.7
    Dossier Reference: Section 8.2 (Performance), Appendix C.2 (Hebbian)

    Attributes:
        importance_scores: List of computed importance scores [0.0-1.0]
        importance_weight_values: Current weight values per factor
        importance_weight_samples: Number of training samples used
        importance_weight_source: Source of weights ("static", "space", "global", "blended")
        hebbian_edges_created: Count of new edges created
        hebbian_edges_updated: Count of existing edges updated
        hebbian_edges_pruned: Count of edges pruned (weight < 0.05)
        hebbian_weight_values: List of edge weights for distribution
        anti_hebbian_decreases: Count of anti-Hebbian weight decreases
        r1_duration_ms: Total R1 phase duration in milliseconds
        importance_scoring_ms: Time spent on importance scoring
        hebbian_update_ms: Time spent on Hebbian updates
    """

    # === Importance Scoring Metrics ===
    importance_scores: List[float] = field(default_factory=list)
    importance_weight_values: Dict[str, float] = field(default_factory=dict)
    importance_weight_samples: int = 0
    importance_weight_source: str = "static"

    # === Hebbian Learning Metrics ===
    hebbian_edges_created: int = 0
    hebbian_edges_updated: int = 0
    hebbian_edges_pruned: int = 0
    hebbian_weight_values: List[float] = field(default_factory=list)
    anti_hebbian_decreases: int = 0

    # === Timing Metrics ===
    r1_duration_ms: float = 0.0
    importance_scoring_ms: float = 0.0
    hebbian_update_ms: float = 0.0

    def record_importance_score(self, score: float) -> None:
        """Record a single importance score."""
        self.importance_scores.append(score)

    def record_importance_scores(self, scores: List[float]) -> None:
        """Record multiple importance scores."""
        self.importance_scores.extend(scores)

    def set_weight_info(
        self,
        weights: Dict[str, float],
        sample_count: int,
        source: str,
    ) -> None:
        """
        Set importance weight information.

        Args:
            weights: Weight values per factor (emotional, recency, access, social)
            sample_count: Number of training samples used
            source: Weight source ("static", "space", "global", "blended")
        """
        self.importance_weight_values = weights.copy()
        self.importance_weight_samples = sample_count
        self.importance_weight_source = source

    def record_hebbian_edge_created(self, weight: float) -> None:
        """Record creation of a new Hebbian edge."""
        self.hebbian_edges_created += 1
        self.hebbian_weight_values.append(weight)

    def record_hebbian_edge_updated(self, weight: float) -> None:
        """Record update of an existing Hebbian edge."""
        self.hebbian_edges_updated += 1
        self.hebbian_weight_values.append(weight)

    def record_hebbian_edge_pruned(self) -> None:
        """Record pruning of a weak edge."""
        self.hebbian_edges_pruned += 1

    def record_anti_hebbian_decrease(self) -> None:
        """Record an anti-Hebbian weight decrease."""
        self.anti_hebbian_decreases += 1

    def check_performance_threshold(self) -> Optional[str]:
        """
        Check if R1 duration exceeds performance thresholds.

        Returns:
            "warning" if > 10s, "error" if > 18s, None if OK
        """
        if self.r1_duration_ms >= R1_ERROR_THRESHOLD_MS:
            return "error"
        elif self.r1_duration_ms >= R1_WARNING_THRESHOLD_MS:
            return "warning"
        return None

    def get_importance_score_stats(self) -> Dict[str, float]:
        """
        Get statistics for importance scores.

        Returns:
            Dict with count, min, max, mean, median
        """
        if not self.importance_scores:
            return {"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0}

        sorted_scores = sorted(self.importance_scores)
        n = len(sorted_scores)
        return {
            "count": n,
            "min": sorted_scores[0],
            "max": sorted_scores[-1],
            "mean": sum(sorted_scores) / n,
            "median": sorted_scores[n // 2],
        }

    def get_hebbian_weight_stats(self) -> Dict[str, float]:
        """
        Get statistics for Hebbian edge weights.

        Returns:
            Dict with count, min, max, mean
        """
        if not self.hebbian_weight_values:
            return {"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0}

        return {
            "count": len(self.hebbian_weight_values),
            "min": min(self.hebbian_weight_values),
            "max": max(self.hebbian_weight_values),
            "mean": sum(self.hebbian_weight_values) / len(self.hebbian_weight_values),
        }

    def to_prometheus_metrics(self) -> Dict[str, Any]:
        """
        Export metrics in Prometheus-compatible format.

        Returns:
            Dict with metric names and values for Prometheus export.
            Histogram values are provided as lists for bucket population.

        Prometheus Metrics (from Issue 4.1.7 spec):
            - p03_importance_score_distribution: Histogram of importance scores
            - p03_importance_weight_{emotional,recency,access,social}: Gauge per factor
            - p03_importance_weight_sample_count: Gauge of training samples
            - p03_hebbian_edges_created: Counter
            - p03_hebbian_edges_updated: Counter
            - p03_hebbian_edges_pruned: Counter
            - p03_hebbian_weight_distribution: Histogram of edge weights
            - p03_anti_hebbian_decreases: Counter
            - p03_r1_duration_ms: Histogram of R1 duration
        """
        metrics: Dict[str, Any] = {}

        # Importance score distribution (histogram values)
        metrics["p03_importance_score_distribution"] = {
            "values": self.importance_scores,
            "buckets": IMPORTANCE_SCORE_BUCKETS,
        }

        # Per-factor weight gauges
        for factor in ("emotional", "recency", "access", "social"):
            key = f"p03_importance_weight_{factor}"
            metrics[key] = self.importance_weight_values.get(factor, 0.0)

        # Weight sample count gauge
        metrics["p03_importance_weight_sample_count"] = self.importance_weight_samples

        # Weight source label
        metrics["p03_importance_weight_source"] = self.importance_weight_source

        # Hebbian edge counters
        metrics["p03_hebbian_edges_created"] = self.hebbian_edges_created
        metrics["p03_hebbian_edges_updated"] = self.hebbian_edges_updated
        metrics["p03_hebbian_edges_pruned"] = self.hebbian_edges_pruned

        # Hebbian weight distribution (histogram values)
        metrics["p03_hebbian_weight_distribution"] = {
            "values": self.hebbian_weight_values,
            "buckets": EDGE_WEIGHT_BUCKETS,
        }

        # Anti-Hebbian counter
        metrics["p03_anti_hebbian_decreases"] = self.anti_hebbian_decreases

        # Duration histograms
        metrics["p03_r1_duration_ms"] = {
            "value": self.r1_duration_ms,
            "buckets": DURATION_MS_BUCKETS,
        }
        metrics["p03_r1_importance_scoring_ms"] = self.importance_scoring_ms
        metrics["p03_r1_hebbian_update_ms"] = self.hebbian_update_ms

        return metrics

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to JSON-serializable dict for logging/audit.

        Returns:
            Dict with all R1 phase metrics
        """
        return {
            "importance_scores": self.get_importance_score_stats(),
            "importance_weight_values": self.importance_weight_values,
            "importance_weight_samples": self.importance_weight_samples,
            "importance_weight_source": self.importance_weight_source,
            "hebbian_edges_created": self.hebbian_edges_created,
            "hebbian_edges_updated": self.hebbian_edges_updated,
            "hebbian_edges_pruned": self.hebbian_edges_pruned,
            "hebbian_weight_stats": self.get_hebbian_weight_stats(),
            "anti_hebbian_decreases": self.anti_hebbian_decreases,
            "r1_duration_ms": self.r1_duration_ms,
            "importance_scoring_ms": self.importance_scoring_ms,
            "hebbian_update_ms": self.hebbian_update_ms,
            "performance_status": self.check_performance_threshold(),
        }

    def merge(self, other: "R1PhaseMetrics") -> None:
        """
        Merge another R1PhaseMetrics into this one.

        Useful for aggregating metrics across batches or partitions.

        Args:
            other: R1PhaseMetrics to merge
        """
        self.importance_scores.extend(other.importance_scores)
        # Take the latest weight info if set
        if other.importance_weight_values:
            self.importance_weight_values = other.importance_weight_values
            self.importance_weight_samples = other.importance_weight_samples
            self.importance_weight_source = other.importance_weight_source
        self.hebbian_edges_created += other.hebbian_edges_created
        self.hebbian_edges_updated += other.hebbian_edges_updated
        self.hebbian_edges_pruned += other.hebbian_edges_pruned
        self.hebbian_weight_values.extend(other.hebbian_weight_values)
        self.anti_hebbian_decreases += other.anti_hebbian_decreases
        # Timing: take max or sum based on use case (sum for totals)
        self.r1_duration_ms = max(self.r1_duration_ms, other.r1_duration_ms)
        self.importance_scoring_ms += other.importance_scoring_ms
        self.hebbian_update_ms += other.hebbian_update_ms


# =============================================================================
# PHASE TRANSITION EVENT TYPES (Issue 1.2.4)
# =============================================================================


class PhaseEventType(Enum):
    """
    Structured log event types for phase transitions.

    Per Issue 1.2.4 spec:
    - phase_start: Phase beginning execution
    - phase_skip: Phase skipped (with reason)
    - phase_complete: Phase finished successfully
    - phase_fail: Phase failed (with error details)
    """

    PHASE_START = "phase_start"
    PHASE_SKIP = "phase_skip"
    PHASE_COMPLETE = "phase_complete"
    PHASE_FAIL = "phase_fail"


@dataclass
class PhaseTransitionEvent:
    """
    Structured event for phase transitions.

    This is the canonical format for logging phase state changes.
    All fields are designed for structured logging (JSON-serializable).

    Attributes:
        event_type: Type of phase event
        cycle_id: ULID of the cycle
        batch_id: Batch identifier
        space_id: Space identifier
        tenant_id: Tenant identifier
        phase_id: Phase identifier (R0-R8)
        status: Phase status after event
        timestamp_ms: Event timestamp (unix ms)
        duration_ms: Phase duration (for complete/fail)
        skip_reason: Why phase was skipped (for skip events)
        error_type: Error classification (for fail events)
        error_message: Error details (for fail events)
        retry_count: Number of retries (for fail events)
        trace_id: Distributed trace ID
        span_id: Current span ID
    """

    event_type: PhaseEventType
    cycle_id: str
    batch_id: str
    space_id: str
    tenant_id: str
    phase_id: str
    status: str
    timestamp_ms: int
    duration_ms: Optional[int] = None
    skip_reason: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict for logging."""
        result = {
            "event": self.event_type.value,
            "pipeline_id": PIPELINE_ID,
            "cycle_id": self.cycle_id,
            "batch_id": self.batch_id,
            "space_id": self.space_id,
            "tenant_id": self.tenant_id,
            "phase_id": self.phase_id,
            "status": self.status,
            "timestamp_ms": self.timestamp_ms,
        }
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        if self.error_type:
            result["error_type"] = self.error_type
        if self.error_message:
            result["error_message"] = self.error_message
        if self.retry_count > 0:
            result["retry_count"] = self.retry_count
        if self.trace_id:
            result["trace_id"] = self.trace_id
        if self.span_id:
            result["span_id"] = self.span_id
        return result

    def to_log_line(self) -> str:
        """Generate human-readable log line."""
        base = f"[{self.event_type.value}] {self.phase_id} -> {self.status}"
        if self.duration_ms is not None:
            base += f" ({self.duration_ms}ms)"
        if self.skip_reason:
            base += f" reason={self.skip_reason}"
        if self.error_type:
            base += f" error={self.error_type}"
        return base


# =============================================================================
# PHASE TRANSITION LOGGER PROTOCOL (Issue 1.2.4)
# =============================================================================


@runtime_checkable
class PhaseTransitionLoggerProtocol(Protocol):
    """
    Protocol for logging phase transitions.

    Implementations can emit to:
    - Structured logging (JSON)
    - Metrics systems
    - Event buses
    - Audit stores
    """

    def log_phase_start(
        self,
        cycle_id: str,
        batch_id: str,
        space_id: str,
        tenant_id: str,
        phase_id: str,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> PhaseTransitionEvent:
        """Log phase start event."""
        ...

    def log_phase_skip(
        self,
        cycle_id: str,
        batch_id: str,
        space_id: str,
        tenant_id: str,
        phase_id: str,
        skip_reason: str,
        duration_ms: int = 0,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> PhaseTransitionEvent:
        """Log phase skip event."""
        ...

    def log_phase_complete(
        self,
        cycle_id: str,
        batch_id: str,
        space_id: str,
        tenant_id: str,
        phase_id: str,
        duration_ms: int,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> PhaseTransitionEvent:
        """Log phase completion event."""
        ...

    def log_phase_fail(
        self,
        cycle_id: str,
        batch_id: str,
        space_id: str,
        tenant_id: str,
        phase_id: str,
        error_type: str,
        error_message: str,
        duration_ms: int,
        retry_count: int = 0,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> PhaseTransitionEvent:
        """Log phase failure event."""
        ...


class PhaseTransitionLogger:
    """
    Default implementation of phase transition logging.

    Collects events for later emission and provides structured logging.
    Can be extended or replaced with custom implementations.
    """

    def __init__(self, logger: Optional[Any] = None):
        """
        Initialize the logger.

        Args:
            logger: Optional external logger (e.g., structlog, logging.Logger).
                   If None, events are only collected internally.
        """
        self._logger = logger
        self._events: List[PhaseTransitionEvent] = []

    @property
    def events(self) -> List[PhaseTransitionEvent]:
        """Get all recorded events."""
        return self._events.copy()

    def clear(self) -> None:
        """Clear recorded events."""
        self._events.clear()

    def _emit(self, event: PhaseTransitionEvent) -> None:
        """Emit event to logger and store internally."""
        self._events.append(event)
        if self._logger:
            # Support both structlog and standard logging
            log_data = event.to_dict()
            if hasattr(self._logger, "info"):
                self._logger.info(event.to_log_line(), **log_data)

    def log_phase_start(
        self,
        cycle_id: str,
        batch_id: str,
        space_id: str,
        tenant_id: str,
        phase_id: str,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> PhaseTransitionEvent:
        """Log phase start event."""
        event = PhaseTransitionEvent(
            event_type=PhaseEventType.PHASE_START,
            cycle_id=cycle_id,
            batch_id=batch_id,
            space_id=space_id,
            tenant_id=tenant_id,
            phase_id=phase_id,
            status="PROC",
            timestamp_ms=_now_ms(),
            trace_id=trace_id,
            span_id=span_id,
        )
        self._emit(event)
        return event

    def log_phase_skip(
        self,
        cycle_id: str,
        batch_id: str,
        space_id: str,
        tenant_id: str,
        phase_id: str,
        skip_reason: str,
        duration_ms: int = 0,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> PhaseTransitionEvent:
        """Log phase skip event."""
        event = PhaseTransitionEvent(
            event_type=PhaseEventType.PHASE_SKIP,
            cycle_id=cycle_id,
            batch_id=batch_id,
            space_id=space_id,
            tenant_id=tenant_id,
            phase_id=phase_id,
            status="SKIP",
            timestamp_ms=_now_ms(),
            duration_ms=duration_ms,
            skip_reason=skip_reason,
            trace_id=trace_id,
            span_id=span_id,
        )
        self._emit(event)
        return event

    def log_phase_complete(
        self,
        cycle_id: str,
        batch_id: str,
        space_id: str,
        tenant_id: str,
        phase_id: str,
        duration_ms: int,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> PhaseTransitionEvent:
        """Log phase completion event."""
        event = PhaseTransitionEvent(
            event_type=PhaseEventType.PHASE_COMPLETE,
            cycle_id=cycle_id,
            batch_id=batch_id,
            space_id=space_id,
            tenant_id=tenant_id,
            phase_id=phase_id,
            status="DONE",
            timestamp_ms=_now_ms(),
            duration_ms=duration_ms,
            trace_id=trace_id,
            span_id=span_id,
        )
        self._emit(event)
        return event

    def log_phase_fail(
        self,
        cycle_id: str,
        batch_id: str,
        space_id: str,
        tenant_id: str,
        phase_id: str,
        error_type: str,
        error_message: str,
        duration_ms: int,
        retry_count: int = 0,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> PhaseTransitionEvent:
        """Log phase failure event."""
        event = PhaseTransitionEvent(
            event_type=PhaseEventType.PHASE_FAIL,
            cycle_id=cycle_id,
            batch_id=batch_id,
            space_id=space_id,
            tenant_id=tenant_id,
            phase_id=phase_id,
            status="FAIL",
            timestamp_ms=_now_ms(),
            duration_ms=duration_ms,
            error_type=error_type,
            error_message=error_message,
            retry_count=retry_count,
            trace_id=trace_id,
            span_id=span_id,
        )
        self._emit(event)
        return event

    def get_phase_summary(self) -> Dict[str, Any]:
        """
        Generate summary of phase transitions for audit/outbox.

        Returns:
            Dict with phase statuses, durations, and any errors
        """
        summary: Dict[str, Any] = {
            "phases": {},
            "total_events": len(self._events),
            "failed_phases": [],
            "skipped_phases": [],
        }

        for event in self._events:
            phase = event.phase_id
            if phase not in summary["phases"]:
                summary["phases"][phase] = {
                    "status": event.status,
                    "duration_ms": event.duration_ms,
                }
            else:
                # Update with latest status
                summary["phases"][phase]["status"] = event.status
                if event.duration_ms is not None:
                    summary["phases"][phase]["duration_ms"] = event.duration_ms

            if event.event_type == PhaseEventType.PHASE_FAIL:
                summary["failed_phases"].append(
                    {
                        "phase_id": phase,
                        "error_type": event.error_type,
                        "error_message": event.error_message,
                        "retry_count": event.retry_count,
                    }
                )
            elif event.event_type == PhaseEventType.PHASE_SKIP:
                summary["skipped_phases"].append(
                    {
                        "phase_id": phase,
                        "skip_reason": event.skip_reason,
                    }
                )

        return summary


# =============================================================================
# P03 ERROR DATACLASS
# =============================================================================


@dataclass
class P03Error:
    """
    Error record for envelope error tracking.

    Errors are accumulated in the envelope during processing.
    Non-recoverable errors trigger DLQ routing after R7 attempt.

    Attributes:
        error_id: ULID for error tracking and correlation
        phase: Phase where error occurred (R0-R8)
        stage_id: Stage/module within phase that errored
        error_type: Error classification (e.g., "ValidationError", "TimeoutError")
        error_message: Human-readable error description
        event_id: Event that caused error (if applicable)
        recoverable: Whether error can be retried
        timestamp_ms: Error occurrence time (MILLISECONDS since epoch)
        stack_trace: Optional stack trace for debugging
        context: Additional context data for debugging
    """

    error_id: str
    phase: str
    stage_id: str
    error_type: str
    error_message: str
    event_id: Optional[str] = None
    recoverable: bool = True
    timestamp_ms: int = field(default_factory=lambda: _now_ms())
    stack_trace: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        phase: str,
        stage_id: str,
        error_type: str,
        error_message: str,
        event_id: Optional[str] = None,
        recoverable: bool = True,
        stack_trace: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> P03Error:
        """
        Factory for creating error records.

        Args:
            phase: Phase where error occurred (R0-R8)
            stage_id: Stage/module within phase
            error_type: Error classification
            error_message: Human-readable message
            event_id: Event that caused error (if applicable)
            recoverable: Whether error can be retried
            stack_trace: Optional stack trace
            context: Additional context data

        Returns:
            P03Error instance with generated error_id
        """
        return cls(
            error_id=generate_ulid(),
            phase=phase,
            stage_id=stage_id,
            error_type=error_type,
            error_message=error_message,
            event_id=event_id,
            recoverable=recoverable,
            stack_trace=stack_trace,
            context=context or {},
        )

    @classmethod
    def from_exception(
        cls,
        phase: str,
        stage_id: str,
        exc: Exception,
        event_id: Optional[str] = None,
        recoverable: bool = True,
    ) -> P03Error:
        """
        Create error record from an exception.

        Args:
            phase: Phase where exception occurred
            stage_id: Stage/module within phase
            exc: The exception instance
            event_id: Event that caused error (if applicable)
            recoverable: Whether error can be retried

        Returns:
            P03Error with exception details
        """
        import traceback

        return cls(
            error_id=generate_ulid(),
            phase=phase,
            stage_id=stage_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
            event_id=event_id,
            recoverable=recoverable,
            stack_trace=traceback.format_exc(),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "error_id": self.error_id,
            "phase": self.phase,
            "stage_id": self.stage_id,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "event_id": self.event_id,
            "recoverable": self.recoverable,
            "timestamp_ms": self.timestamp_ms,
            "stack_trace": self.stack_trace,
            "context": self.context,
        }


# =============================================================================
# P03 OBSERVABILITY CONTEXT
# =============================================================================


@dataclass
class P03ObservabilityContext:
    """
    Observability context carried through the envelope.

    Provides distributed tracing, phase timing, and metrics aggregation.
    Each P03 cycle creates one observability context that travels with
    the envelope through all phases.

    Attributes:
        trace_id: Distributed trace identifier (cognitive_trace_id)
        root_span_id: Root span ID for this cycle
        current_span_id: Currently active span ID
        span_stack: Stack of span IDs for nesting
        phase_start_ts: Phase start timestamps (phase → unix ms)
        phase_end_ts: Phase end timestamps (phase → unix ms)
        counters: Metric counters (metric_name → count)
        histograms: Histogram values (metric_name → [values])
        log_context: Structured log context (key → value)
        errors: Accumulated errors during processing
        tenant_id: Tenant identifier for metrics emission (Issue 6.1.3)
        metrics_registry: Optional P03MetricsRegistry for phase timing (Issue 6.1.3)
    """

    # === DISTRIBUTED TRACING ===
    trace_id: str = ""
    root_span_id: str = ""
    current_span_id: str = ""
    span_stack: List[str] = field(default_factory=list)

    # === PHASE TIMING ===
    phase_start_ts: Dict[str, int] = field(default_factory=dict)
    phase_end_ts: Dict[str, int] = field(default_factory=dict)

    # === METRICS AGGREGATION ===
    counters: Dict[str, int] = field(default_factory=dict)
    histograms: Dict[str, List[float]] = field(default_factory=dict)

    # === LOG CONTEXT ===
    log_context: Dict[str, str] = field(default_factory=dict)

    # === ERROR TRACKING ===
    errors: List[P03Error] = field(default_factory=list)

    # === METRICS INTEGRATION (Issue 6.1.3) ===
    tenant_id: str = ""
    metrics_registry: Optional[Any] = None  # P03MetricsRegistry (avoid circular import)

    # =========================================================================
    # FACTORY METHODS
    # =========================================================================

    @classmethod
    def create(
        cls,
        trace_id: Optional[str] = None,
        log_context: Optional[Dict[str, str]] = None,
    ) -> P03ObservabilityContext:
        """
        Factory for creating observability context.

        Args:
            trace_id: Optional trace ID (generated if not provided)
            log_context: Optional initial log context

        Returns:
            P03ObservabilityContext with initialized tracing
        """
        tid = trace_id or generate_ulid()
        root_span = generate_ulid()
        return cls(
            trace_id=tid,
            root_span_id=root_span,
            current_span_id=root_span,
            log_context=log_context or {},
        )

    # =========================================================================
    # SPAN MANAGEMENT
    # =========================================================================

    def push_span(self, span_id: Optional[str] = None) -> str:
        """
        Push a new span onto the stack.

        Args:
            span_id: Optional span ID (generated if not provided)

        Returns:
            The new span ID
        """
        new_span = span_id or generate_ulid()
        self.span_stack.append(self.current_span_id)
        self.current_span_id = new_span
        return new_span

    def pop_span(self) -> str:
        """
        Pop the current span and restore parent.

        Returns:
            The popped span ID
        """
        popped = self.current_span_id
        if self.span_stack:
            self.current_span_id = self.span_stack.pop()
        else:
            self.current_span_id = self.root_span_id
        return popped

    # =========================================================================
    # PHASE TIMING
    # =========================================================================

    def start_phase(self, phase: str) -> int:
        """
        Record phase start time.

        Args:
            phase: Phase name (R0-R8)

        Returns:
            Start timestamp in milliseconds
        """
        ts = _now_ms()
        self.phase_start_ts[phase] = ts
        return ts

    def end_phase(self, phase: str, status: str = "success") -> int:
        """
        Record phase end time and emit phase duration metrics.

        Args:
            phase: Phase name (R0-R8)
            status: Phase status ("success", "failed", "skipped")

        Returns:
            End timestamp in milliseconds
        """
        ts = _now_ms()
        self.phase_end_ts[phase] = ts

        # Issue 6.1.3: Emit phase timing metrics if registry is available
        if self.metrics_registry is not None and self.tenant_id:
            duration_ms = self.get_phase_duration_ms(phase)
            if duration_ms is not None:
                self.metrics_registry.emit_phase_duration(
                    tenant_id=self.tenant_id,
                    phase=phase,
                    duration_s=duration_ms / 1000.0,  # Convert ms to seconds
                )
                self.metrics_registry.emit_phase_complete(
                    tenant_id=self.tenant_id,
                    phase=phase,
                    status=status,
                )

        return ts

    def get_phase_duration_ms(self, phase: str) -> Optional[int]:
        """
        Get duration of a completed phase.

        Args:
            phase: Phase name (R0-R8)

        Returns:
            Duration in milliseconds, or None if phase not complete
        """
        start = self.phase_start_ts.get(phase)
        end = self.phase_end_ts.get(phase)
        if start is not None and end is not None:
            return end - start
        return None

    def get_all_phase_durations(self) -> Dict[str, int]:
        """
        Get durations for all completed phases.

        Returns:
            Dict mapping phase name to duration in milliseconds
        """
        durations = {}
        for phase in self.phase_start_ts:
            duration = self.get_phase_duration_ms(phase)
            if duration is not None:
                durations[phase] = duration
        return durations

    def get_total_duration_ms(self) -> Optional[int]:
        """
        Get total cycle duration (R0 start to last completed phase end).

        Returns:
            Total duration in milliseconds, or None if R0 not started
        """
        r0_start = self.phase_start_ts.get("R0")
        if r0_start is None:
            return None

        # Find latest end time
        latest_end = max(self.phase_end_ts.values()) if self.phase_end_ts else None
        if latest_end is None:
            return None

        return latest_end - r0_start

    # =========================================================================
    # METRICS
    # =========================================================================

    def increment(self, metric: str, delta: int = 1) -> int:
        """
        Increment a counter metric.

        Args:
            metric: Metric name
            delta: Amount to increment (default 1)

        Returns:
            New counter value
        """
        self.counters[metric] = self.counters.get(metric, 0) + delta
        return self.counters[metric]

    def record_histogram(self, metric: str, value: float) -> None:
        """
        Record a value in a histogram.

        Args:
            metric: Histogram metric name
            value: Value to record
        """
        if metric not in self.histograms:
            self.histograms[metric] = []
        self.histograms[metric].append(value)

    def get_histogram_stats(self, metric: str) -> Optional[Dict[str, float]]:
        """
        Get basic statistics for a histogram.

        Args:
            metric: Histogram metric name

        Returns:
            Dict with count, sum, min, max, avg or None if no values
        """
        values = self.histograms.get(metric)
        if not values:
            return None

        return {
            "count": len(values),
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }

    # =========================================================================
    # LOG CONTEXT
    # =========================================================================

    def set_log_context(self, key: str, value: str) -> None:
        """
        Set a log context value.

        Args:
            key: Context key
            value: Context value
        """
        self.log_context[key] = value

    def get_log_context(self, phase: str, module: str) -> Dict[str, str]:
        """
        Get structured log context for current execution point.

        Args:
            phase: Current phase (R0-R8)
            module: Module identifier

        Returns:
            Dict with pipeline_id, trace_id, phase, module_id, and custom context
        """
        return {
            "pipeline_id": PIPELINE_ID,
            "trace_id": self.trace_id,
            "span_id": self.current_span_id,
            "phase": phase,
            "module_id": module,
            **self.log_context,
        }

    # =========================================================================
    # ERROR TRACKING
    # =========================================================================

    def add_error(self, error: P03Error) -> None:
        """
        Add an error to the error list.

        Args:
            error: P03Error to add
        """
        self.errors.append(error)

    def record_error(
        self,
        phase: str,
        stage_id: str,
        error_type: str,
        error_message: str,
        event_id: Optional[str] = None,
        recoverable: bool = True,
    ) -> P03Error:
        """
        Create and record an error.

        Args:
            phase: Phase where error occurred
            stage_id: Stage/module within phase
            error_type: Error classification
            error_message: Human-readable message
            event_id: Event that caused error (if applicable)
            recoverable: Whether error can be retried

        Returns:
            The created P03Error
        """
        error = P03Error.create(
            phase=phase,
            stage_id=stage_id,
            error_type=error_type,
            error_message=error_message,
            event_id=event_id,
            recoverable=recoverable,
        )
        self.errors.append(error)
        self.increment(f"errors.{phase}")
        return error

    def record_exception(
        self,
        phase: str,
        stage_id: str,
        exc: Exception,
        event_id: Optional[str] = None,
        recoverable: bool = True,
    ) -> P03Error:
        """
        Create and record an error from an exception.

        Args:
            phase: Phase where exception occurred
            stage_id: Stage/module within phase
            exc: The exception instance
            event_id: Event that caused error (if applicable)
            recoverable: Whether error can be retried

        Returns:
            The created P03Error
        """
        error = P03Error.from_exception(
            phase=phase,
            stage_id=stage_id,
            exc=exc,
            event_id=event_id,
            recoverable=recoverable,
        )
        self.errors.append(error)
        self.increment(f"errors.{phase}")
        return error

    def has_errors(self) -> bool:
        """Check if any errors have been recorded."""
        return len(self.errors) > 0

    def has_unrecoverable_errors(self) -> bool:
        """Check if any non-recoverable errors exist."""
        return any(not e.recoverable for e in self.errors)

    def get_errors_by_phase(self, phase: str) -> List[P03Error]:
        """Get all errors for a specific phase."""
        return [e for e in self.errors if e.phase == phase]

    # =========================================================================
    # SUMMARY
    # =========================================================================

    def to_summary_dict(self) -> Dict[str, Any]:
        """
        Generate compact summary for logging/metrics.

        Returns:
            Dict with tracing, timing, metrics summary
        """
        return {
            "trace_id": self.trace_id,
            "root_span_id": self.root_span_id,
            "phase_durations_ms": self.get_all_phase_durations(),
            "total_duration_ms": self.get_total_duration_ms(),
            "counters": dict(self.counters),
            "histogram_stats": {k: self.get_histogram_stats(k) for k in self.histograms},
            "error_count": len(self.errors),
            "has_unrecoverable": self.has_unrecoverable_errors(),
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _now_ms() -> int:
    """Get current time in milliseconds since Unix epoch."""
    import time

    return int(time.time() * 1000)
