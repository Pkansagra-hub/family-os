"""
k1.orchestrator.metrics -- SLI measurement hooks for Orchestrator.

Implements issue 8.1.2:
- OrchestratorMetrics context-manager timing helpers
- zero-overhead no-op behavior when disabled
- adapter wait-time subtraction for total overhead metric

This module intentionally keeps the collector abstraction minimal.
Epic 8.2 extends this with concrete histogram/counter/gauge emission.
"""

from __future__ import annotations

import contextvars
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from time import perf_counter_ns
from typing import Any, Dict, Iterator, Optional, Protocol


class MetricsCollector(Protocol):
    """Minimal collector protocol for timing measurements."""

    def observe_timing(self, metric_name: str, value_ms: float, **tags: Any) -> None: ...

    def increment_counter(self, metric_name: str, value: int = 1, **tags: Any) -> None: ...

    def set_gauge(self, metric_name: str, value: float, **tags: Any) -> None: ...


class NullMetricsCollector:
    """No-op collector used when no backend is configured."""

    __slots__ = ()

    def observe_timing(self, metric_name: str, value_ms: float, **tags: Any) -> None:
        return

    def increment_counter(self, metric_name: str, value: int = 1, **tags: Any) -> None:
        return

    def set_gauge(self, metric_name: str, value: float, **tags: Any) -> None:
        return


@dataclass
class _OverheadScope:
    """Per-request scope for total-overhead accounting."""

    start_ns: int
    tags: Dict[str, Any]
    adapter_wait_ns: int = 0


class OrchestratorMetrics:
    """Timing helper facade for Orchestrator SLI measurements."""

    __slots__ = ("_enabled", "_collector", "_active_overhead")

    def __init__(
        self,
        *,
        enabled: bool,
        collector: Optional[MetricsCollector] = None,
    ) -> None:
        self._enabled = enabled
        self._collector: MetricsCollector = collector or NullMetricsCollector()
        self._active_overhead: contextvars.ContextVar[Optional[_OverheadScope]] = (
            contextvars.ContextVar("orchestrator_active_overhead", default=None)
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _record(self, metric_name: str, elapsed_ns: int, **tags: Any) -> None:
        if elapsed_ns < 0:
            elapsed_ns = 0
        self._collector.observe_timing(metric_name, elapsed_ns / 1_000_000.0, **tags)

    def _increment(self, metric_name: str, value: int = 1, **tags: Any) -> None:
        if not self._enabled:
            return
        inc = getattr(self._collector, "increment_counter", None)
        if callable(inc):
            inc(metric_name, value, **tags)

    def _set_gauge(self, metric_name: str, value: float, **tags: Any) -> None:
        if not self._enabled:
            return
        set_gauge = getattr(self._collector, "set_gauge", None)
        if callable(set_gauge):
            set_gauge(metric_name, value, **tags)

    @contextmanager
    def _timed(self, metric_name: str, **tags: Any) -> Iterator[None]:
        if not self._enabled:
            yield
            return

        start_ns = perf_counter_ns()
        try:
            yield
        finally:
            self._record(metric_name, perf_counter_ns() - start_ns, **tags)

    # ------------------------------------------------------------------
    # SLI hook helpers (8.1.2)
    # ------------------------------------------------------------------

    def time_dequeue(self) -> AbstractContextManager[None]:
        return self._timed("orchestrator.sli.dequeue_ms")

    def time_route(self, *, message_type: str) -> AbstractContextManager[None]:
        return self._timed("orchestrator.sli.route_ms", message_type=message_type)

    def time_dag_build(self, *, step_count: int) -> AbstractContextManager[None]:
        return self._timed("orchestrator.wave.construction_ms", step_count=step_count)

    def time_wave_dispatch(
        self, *, wave_index: int, step_count: int
    ) -> AbstractContextManager[None]:
        return self._timed(
            "orchestrator.sli.wave_dispatch_ms",
            wave_index=wave_index,
            step_count=step_count,
        )

    def time_step_execution(
        self, *, step_id: str, capability_name: str
    ) -> AbstractContextManager[None]:
        @contextmanager
        def _ctx() -> Iterator[None]:
            if not self._enabled:
                yield
                return
            start_ns = perf_counter_ns()
            try:
                yield
            finally:
                elapsed_ns = perf_counter_ns() - start_ns
                # 8.2.1 catalog metric (histogram)
                self._record(
                    "orchestrator.step.duration_ms",
                    elapsed_ns,
                    step_id=step_id,
                    capability_name=capability_name,
                )
                # Backward-compatible 8.1.2 SLI hook
                self._record(
                    "orchestrator.sli.step_execution_ms",
                    elapsed_ns,
                    step_id=step_id,
                    capability_name=capability_name,
                )

        return _ctx()

    def time_guard_pipeline(self, *, phase: str, scope_id: str) -> AbstractContextManager[None]:
        return self._timed(
            "orchestrator.sli.guard_pipeline_ms",
            phase=phase,
            scope_id=scope_id,
        )

    def time_constraint_validation(self, *, step_count: int) -> AbstractContextManager[None]:
        return self._timed("orchestrator.constraint.resolution_ms", step_count=step_count)

    def time_aggregation(self, *, plan_id: str) -> AbstractContextManager[None]:
        return self._timed("orchestrator.sli.aggregation_ms", plan_id=plan_id)

    def time_param_resolution(self, *, step_id: str) -> AbstractContextManager[None]:
        return self._timed("orchestrator.sli.param_resolution_ms", step_id=step_id)

    @contextmanager
    def time_total_overhead(self, *, message_type: str, tier: str) -> Iterator[None]:
        """Measure process() overhead excluding Fabric/Planner adapter wait."""
        if not self._enabled:
            yield
            return

        scope = _OverheadScope(
            start_ns=perf_counter_ns(),
            tags={"message_type": message_type, "tier": tier},
        )
        token = self._active_overhead.set(scope)
        try:
            yield
        finally:
            total_ns = perf_counter_ns() - scope.start_ns
            overhead_ns = total_ns - scope.adapter_wait_ns
            self._record("orchestrator.dag.overhead_ms", overhead_ns, **scope.tags)
            self._active_overhead.reset(token)

    # ------------------------------------------------------------------
    # 8.2.1 Metrics catalog (counters/gauges/histogram helpers)
    # ------------------------------------------------------------------

    def observe_dag_duration(self, *, duration_ms: float, tier: str) -> None:
        if not self._enabled:
            return
        self._collector.observe_timing(
            "orchestrator.dag.duration_ms",
            max(0.0, duration_ms),
            tier=tier,
        )

    def increment_dag_completed(self, *, status: str) -> None:
        self._increment("orchestrator.dag.completed_total", status=status)

    def increment_step_retry(self, *, reason: str) -> None:
        self._increment("orchestrator.step.retry_total", reason=reason)

    def increment_saga_compensation(self, *, count: int = 1) -> None:
        self._increment("orchestrator.saga.compensation_total", value=count)

    def increment_workflow_trigger(self, *, trigger_type: str) -> None:
        self._increment("orchestrator.workflow.trigger_total", trigger_type=trigger_type)

    def increment_error(self, *, classification: str) -> None:
        self._increment("orchestrator.error.total", classification=classification)

    def increment_hil_request(self, *, outcome: str) -> None:
        self._increment("orchestrator.hil.request_total", outcome=outcome)

    def increment_mailbox_processed(self, *, message_type: str) -> None:
        self._increment("orchestrator.mailbox.processed_total", message_type=message_type)

    def set_dag_active(self, active: bool) -> None:
        self._set_gauge("orchestrator.dag.active", 1.0 if active else 0.0)

    def set_mailbox_depth(self, depth: int) -> None:
        self._set_gauge("orchestrator.mailbox.depth", float(max(0, depth)))

    def set_workflow_active_count(self, count: int) -> None:
        self._set_gauge("orchestrator.workflow.active_count", float(max(0, count)))

    def set_mcp_registered_capabilities(self, count: int) -> None:
        self._set_gauge("orchestrator.mcp.registered_capabilities", float(max(0, count)))

    def set_pending_plans(self, count: int) -> None:
        self._set_gauge("orchestrator.pending_plans", float(max(0, count)))

    def set_deferred_plan_depth(self, depth: int) -> None:
        """M5.1.6: gauge for plans currently re-enqueued waiting on
        the ConcurrencyGuard. Distinct from mailbox depth: counts only
        plans that have hit the deferred re-enqueue path."""
        self._set_gauge("orchestrator.deferred_plan_depth", float(max(0, depth)))

    @contextmanager
    def time_adapter_wait(self, *, adapter: str, operation: str) -> Iterator[None]:
        """Track adapter wait to subtract from total overhead measurement."""
        if not self._enabled:
            yield
            return

        active = self._active_overhead.get()
        if active is None:
            yield
            return

        start_ns = perf_counter_ns()
        try:
            yield
        finally:
            elapsed_ns = perf_counter_ns() - start_ns
            active.adapter_wait_ns += elapsed_ns
            self._record(
                "orchestrator.sli.adapter_wait_ms",
                elapsed_ns,
                adapter=adapter,
                operation=operation,
            )
