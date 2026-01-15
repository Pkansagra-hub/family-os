"""P03 Formula Debug Tracing — Issue 6.1.15.

This module implements three-level formula debug tracing for different
audiences: User, Ops, and Debug. Each level has different content,
retention, and sampling characteristics.

Issue Reference: M6_EXECUTION.md Issue 6.1.15
Dossier Reference: docs/pipelines/P03_consolidation_dossier_v2.md Section 8.5.1

Trace Levels:
    USER: Natural language explanation for end users (90-day retention)
    OPS: Structured audit + decision path for support (90-day retention)
    DEBUG: Full computation trace + intermediates for developers (7-day retention)

Key Features:
    - Three trace levels with audience-appropriate content
    - Configurable sampling rate (default 1%)
    - Always-trace for errors, rollbacks, anomalies
    - Per-space override for 100% tracing
    - Step-by-step computation capture with timing
    - Integration with P03MetricsRegistry for trace metrics

Usage:
    from k0.pipelines.p03.ops.formula_tracing import FormulaTracer, TraceLevel

    tracer = FormulaTracer(metrics_registry, feature_flags)

    # Check if tracing should occur
    if tracer.should_trace(TraceLevel.DEBUG):
        ctx = tracer.create_trace_context(
            formula="hebbian_v2",
            level=TraceLevel.DEBUG,
            inputs={"entity_id": "ent_001", "access_count": 15},
        )

        # Record computation steps
        ctx.add_step("calculate_cooccurrence", {"score": 0.75}, duration_ms=12)
        ctx.add_step("compare_threshold", {"decision": "REINFORCE"}, duration_ms=1)

        # Finalize and store
        ctx.finalize({"action": "REINFORCE", "confidence": 0.85})
        await tracer.store_trace(ctx)
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from k0.pipelines.p03.ops.metrics import P03MetricsRegistry

__all__ = [
    "TraceLevel",
    "TraceStep",
    "TraceContext",
    "NoOpTraceContext",
    "FormulaTracer",
]

LOGGER = logging.getLogger(__name__)


# =============================================================================
# TRACE LEVEL ENUM
# =============================================================================


class TraceLevel(Enum):
    """Trace level for formula debugging.

    Determines content, retention, and audience.
    """

    USER = "user"  # Natural language, 90 days, end users
    OPS = "ops"  # Structured audit, 90 days, support team
    DEBUG = "debug"  # Full trace, 7 days, developers

    @property
    def retention_days(self) -> int:
        """Return retention period in days."""
        if self == TraceLevel.DEBUG:
            return 7
        return 90  # USER and OPS


# =============================================================================
# TRACE DATA CLASSES
# =============================================================================


@dataclass
class TraceStep:
    """Single computation step in a formula trace."""

    step: int
    operation: str
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step": self.step,
            "operation": self.operation,
            "input": self.input_data,
            "output": self.output_data,
            "duration_ms": self.duration_ms,
        }


@dataclass
class TraceContext:
    """Context for capturing formula execution trace.

    Captures inputs, step-by-step computation, and outputs with timing.
    """

    trace_id: str
    level: TraceLevel
    formula: str
    timestamp_ms: int
    inputs: dict[str, Any]
    steps: list[TraceStep] = field(default_factory=list)
    feature_flags: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    total_duration_ms: float = 0.0
    is_error: bool = False
    error_message: str | None = None

    def add_step(
        self,
        operation: str,
        output_data: dict[str, Any],
        duration_ms: float,
        input_data: dict[str, Any] | None = None,
    ) -> None:
        """Record a computation step.

        Args:
            operation: Name of the operation (e.g., "calculate_cooccurrence").
            output_data: Output of this step.
            duration_ms: Duration of this step in milliseconds.
            input_data: Optional input to this step (defaults to previous output).
        """
        step_num = len(self.steps) + 1
        self.steps.append(
            TraceStep(
                step=step_num,
                operation=operation,
                input_data=input_data or {},
                output_data=output_data,
                duration_ms=duration_ms,
            )
        )

    def finalize(
        self,
        output: dict[str, Any],
        total_ms: float | None = None,
    ) -> None:
        """Finalize trace with output.

        Args:
            output: Final output of the formula execution.
            total_ms: Total duration (calculated from steps if not provided).
        """
        self.output = output
        if total_ms is not None:
            self.total_duration_ms = total_ms
        else:
            self.total_duration_ms = sum(s.duration_ms for s in self.steps)

    def mark_error(self, error_message: str) -> None:
        """Mark this trace as containing an error.

        Args:
            error_message: Error message to record.
        """
        self.is_error = True
        self.error_message = error_message

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        result: dict[str, Any] = {
            "trace_id": self.trace_id,
            "level": self.level.value,
            "formula": self.formula,
            "timestamp": self.timestamp_ms,
            "inputs": self.inputs,
            "steps": [s.to_dict() for s in self.steps],
            "output": self.output,
            "total_duration_ms": self.total_duration_ms,
        }
        if self.feature_flags:
            result["feature_flags"] = self.feature_flags
        if self.is_error:
            result["is_error"] = True
            result["error_message"] = self.error_message
        return result


class NoOpTraceContext:
    """No-op trace context for when tracing is disabled.

    All methods are no-ops to minimize overhead when tracing is not active.
    """

    def add_step(
        self,
        operation: str,
        output_data: dict[str, Any],
        duration_ms: float,
        input_data: dict[str, Any] | None = None,
    ) -> None:
        """No-op."""
        pass

    def finalize(
        self,
        output: dict[str, Any],
        total_ms: float | None = None,
    ) -> None:
        """No-op."""
        pass

    def mark_error(self, error_message: str) -> None:
        """No-op."""
        pass

    def to_dict(self) -> dict[str, Any]:
        """Return empty dict."""
        return {}


# =============================================================================
# FORMULA TRACER
# =============================================================================


class FormulaTracer:
    """Capture formula execution traces at multiple levels.

    Implements sampling, always-trace conditions, and per-space overrides.

    Thread Safety:
        Thread-safe. Sampling is probabilistic per call.

    Usage:
        tracer = FormulaTracer(metrics, flags)

        if tracer.should_trace(TraceLevel.DEBUG, is_error=False):
            ctx = tracer.create_trace_context("hebbian_v2", TraceLevel.DEBUG, inputs)
            # ... record steps ...
            await tracer.store_trace(ctx)
    """

    DEFAULT_SAMPLE_RATE = 0.01  # 1%

    def __init__(
        self,
        metrics: P03MetricsRegistry | None = None,
        feature_flags: dict[str, Any] | None = None,
    ) -> None:
        """Initialize formula tracer.

        Args:
            metrics: P03MetricsRegistry for trace metrics.
            feature_flags: Feature flags dict (or callable returning dict).
        """
        self._metrics = metrics
        self._flags = feature_flags or {}

    def get_sample_rate(self) -> float:
        """Get current sampling rate from feature flags."""
        rate = self._flags.get("P03_FF_DEBUG_TRACE_RATE", self.DEFAULT_SAMPLE_RATE)
        try:
            return float(rate)
        except (TypeError, ValueError):
            return self.DEFAULT_SAMPLE_RATE

    def should_trace(
        self,
        level: TraceLevel,
        is_error: bool = False,
        is_rollback: bool = False,
        is_anomaly: bool = False,
        space_id: str | None = None,
    ) -> bool:
        """Determine if tracing should occur.

        Always-trace conditions:
            - Errors (is_error=True)
            - Rollbacks (is_rollback=True)
            - Anomalies (is_anomaly=True)
            - Per-space override (P03_FF_DEBUG_TRACE_SPACES contains space_id)

        Args:
            level: Trace level.
            is_error: Whether this is an error scenario.
            is_rollback: Whether this is a rollback scenario.
            is_anomaly: Whether this is an anomaly scenario.
            space_id: Space ID for per-space override check.

        Returns:
            True if tracing should occur.
        """
        # Always trace errors, rollbacks, anomalies
        if is_error or is_rollback or is_anomaly:
            return True

        # Check per-space override
        if space_id:
            trace_all_spaces = self._flags.get("P03_FF_DEBUG_TRACE_SPACES", [])
            if space_id in trace_all_spaces:
                return True

        # Check global all-spaces override
        if self._flags.get("P03_FF_DEBUG_TRACE_ALL_SPACES", False):
            return True

        # Apply sampling
        sample_rate = self.get_sample_rate()
        return random.random() < sample_rate

    def create_trace_context(
        self,
        formula: str,
        level: TraceLevel,
        inputs: dict[str, Any],
        feature_flags: dict[str, Any] | None = None,
    ) -> TraceContext:
        """Create trace context for formula execution.

        Args:
            formula: Formula name (e.g., "hebbian_v2", "importance_v1").
            level: Trace level.
            inputs: Input values to the formula.
            feature_flags: Active feature flags (for debugging).

        Returns:
            TraceContext for recording execution.
        """
        trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        timestamp_ms = int(time.time() * 1000)

        ctx = TraceContext(
            trace_id=trace_id,
            level=level,
            formula=formula,
            timestamp_ms=timestamp_ms,
            inputs=inputs,
            feature_flags=feature_flags or {},
        )

        # Emit trace capture metric
        if self._metrics:
            self._metrics.exporter.emit(
                "p03_debug_traces_captured",
                1.0,
                level=level.value,
                formula=formula,
            )

        LOGGER.debug(
            "Created trace context: trace_id=%s formula=%s level=%s",
            trace_id,
            formula,
            level.value,
        )

        return ctx

    def get_trace_or_noop(
        self,
        formula: str,
        level: TraceLevel,
        inputs: dict[str, Any],
        is_error: bool = False,
        space_id: str | None = None,
    ) -> TraceContext | NoOpTraceContext:
        """Get trace context or no-op if tracing is disabled.

        Convenience method that combines should_trace and create_trace_context.

        Args:
            formula: Formula name.
            level: Trace level.
            inputs: Input values.
            is_error: Whether this is an error scenario.
            space_id: Space ID for override check.

        Returns:
            TraceContext if tracing, NoOpTraceContext otherwise.
        """
        if self.should_trace(level, is_error=is_error, space_id=space_id):
            return self.create_trace_context(formula, level, inputs)
        return NoOpTraceContext()

    async def store_trace(self, trace: TraceContext) -> None:
        """Persist trace to storage backend.

        Currently logs the trace. Implement storage backend as needed.

        Args:
            trace: TraceContext to store.
        """
        # Log at appropriate level based on trace level
        if trace.level == TraceLevel.DEBUG:
            LOGGER.debug(
                "Formula trace: formula=%s duration=%.1fms steps=%d",
                trace.formula,
                trace.total_duration_ms,
                len(trace.steps),
            )
        else:
            LOGGER.info(
                "Formula trace: formula=%s duration=%.1fms steps=%d",
                trace.formula,
                trace.total_duration_ms,
                len(trace.steps),
            )

        # Update storage metrics
        if self._metrics:
            trace_bytes = len(str(trace.to_dict()))
            self._metrics.exporter.set_gauge(
                "p03_debug_trace_storage_bytes",
                float(trace_bytes),
                level=trace.level.value,
            )

    def set_sampling_rate_metric(self) -> None:
        """Update the sampling rate metric gauge."""
        if self._metrics:
            self._metrics.exporter.set_gauge(
                "p03_debug_trace_sampling_rate",
                self.get_sample_rate(),
            )


# Module-level singleton for convenience
_tracer: FormulaTracer | None = None


def get_formula_tracer(
    metrics: P03MetricsRegistry | None = None,
    feature_flags: dict[str, Any] | None = None,
) -> FormulaTracer:
    """Get or create the module-level formula tracer singleton.

    Args:
        metrics: P03MetricsRegistry (used on first call).
        feature_flags: Feature flags (used on first call).

    Returns:
        FormulaTracer singleton.
    """
    global _tracer
    if _tracer is None:
        _tracer = FormulaTracer(metrics, feature_flags)
    return _tracer
