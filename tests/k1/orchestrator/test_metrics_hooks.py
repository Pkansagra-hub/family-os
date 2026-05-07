from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from k1.orchestrator.metrics import OrchestratorMetrics


@dataclass
class _Point:
    name: str
    value_ms: float
    tags: dict[str, Any]


class _Collector:
    def __init__(self) -> None:
        self.points: list[_Point] = []
        self.counters: list[tuple[str, int, dict[str, Any]]] = []
        self.gauges: list[tuple[str, float, dict[str, Any]]] = []

    def observe_timing(self, metric_name: str, value_ms: float, **tags: Any) -> None:
        self.points.append(_Point(name=metric_name, value_ms=value_ms, tags=tags))

    def increment_counter(self, metric_name: str, value: int = 1, **tags: Any) -> None:
        self.counters.append((metric_name, value, tags))

    def set_gauge(self, metric_name: str, value: float, **tags: Any) -> None:
        self.gauges.append((metric_name, value, tags))


def _find(points: list[_Point], name: str) -> list[_Point]:
    return [p for p in points if p.name == name]


def test_metrics_disabled_noop() -> None:
    collector = _Collector()
    metrics = OrchestratorMetrics(enabled=False, collector=collector)

    with metrics.time_dequeue():
        time.sleep(0.001)

    with metrics.time_total_overhead(message_type="TaskEnvelope", tier="HIGH"):
        with metrics.time_adapter_wait(adapter="fabric", operation="execute"):
            time.sleep(0.001)

    assert collector.points == []


def test_individual_timers_emit() -> None:
    collector = _Collector()
    metrics = OrchestratorMetrics(enabled=True, collector=collector)

    with metrics.time_dequeue():
        time.sleep(0.001)
    with metrics.time_route(message_type="TaskEnvelope"):
        time.sleep(0.001)
    with metrics.time_dag_build(step_count=10):
        time.sleep(0.001)
    with metrics.time_wave_dispatch(wave_index=1, step_count=3):
        time.sleep(0.001)
    with metrics.time_step_execution(step_id="s1", capability_name="cap.a"):
        time.sleep(0.001)
    with metrics.time_guard_pipeline(phase="pre_wave", scope_id="0"):
        time.sleep(0.001)
    with metrics.time_constraint_validation(step_count=10):
        time.sleep(0.001)
    with metrics.time_aggregation(plan_id="p1"):
        time.sleep(0.001)
    with metrics.time_param_resolution(step_id="s2"):
        time.sleep(0.001)

    expected = {
        "orchestrator.sli.dequeue_ms",
        "orchestrator.sli.route_ms",
        "orchestrator.wave.construction_ms",
        "orchestrator.sli.wave_dispatch_ms",
        "orchestrator.step.duration_ms",
        "orchestrator.sli.step_execution_ms",
        "orchestrator.sli.guard_pipeline_ms",
        "orchestrator.constraint.resolution_ms",
        "orchestrator.sli.aggregation_ms",
        "orchestrator.sli.param_resolution_ms",
    }
    seen = {p.name for p in collector.points}
    assert expected.issubset(seen)


def test_total_overhead_subtracts_adapter_wait() -> None:
    collector = _Collector()
    metrics = OrchestratorMetrics(enabled=True, collector=collector)

    with metrics.time_total_overhead(message_type="TaskEnvelope", tier="HIGH"):
        time.sleep(0.001)
        with metrics.time_adapter_wait(adapter="fabric", operation="execute"):
            time.sleep(0.004)
        time.sleep(0.001)

    overhead = _find(collector.points, "orchestrator.dag.overhead_ms")
    adapter_wait = _find(collector.points, "orchestrator.sli.adapter_wait_ms")

    assert len(overhead) == 1
    assert len(adapter_wait) == 1
    assert overhead[0].value_ms > 0.0
    assert adapter_wait[0].value_ms > overhead[0].value_ms


def test_adapter_wait_outside_total_scope_not_recorded() -> None:
    collector = _Collector()
    metrics = OrchestratorMetrics(enabled=True, collector=collector)

    with metrics.time_adapter_wait(adapter="planner", operation="request_plan"):
        time.sleep(0.001)

    assert _find(collector.points, "orchestrator.sli.adapter_wait_ms") == []


def test_metric_catalog_counters_and_gauges_emit() -> None:
    collector = _Collector()
    metrics = OrchestratorMetrics(enabled=True, collector=collector)

    metrics.increment_dag_completed(status="success")
    metrics.increment_step_retry(reason="transient")
    metrics.increment_saga_compensation(count=2)
    metrics.increment_workflow_trigger(trigger_type="cron")
    metrics.increment_error(classification="DEGRADED")
    metrics.increment_hil_request(outcome="responded")
    metrics.increment_mailbox_processed(message_type="TaskEnvelope")

    metrics.set_dag_active(True)
    metrics.set_mailbox_depth(7)
    metrics.set_workflow_active_count(4)
    metrics.set_mcp_registered_capabilities(12)
    metrics.set_pending_plans(2)

    counter_names = {c[0] for c in collector.counters}
    assert {
        "orchestrator.dag.completed_total",
        "orchestrator.step.retry_total",
        "orchestrator.saga.compensation_total",
        "orchestrator.workflow.trigger_total",
        "orchestrator.error.total",
        "orchestrator.hil.request_total",
        "orchestrator.mailbox.processed_total",
    }.issubset(counter_names)

    gauge_names = {g[0] for g in collector.gauges}
    assert {
        "orchestrator.dag.active",
        "orchestrator.mailbox.depth",
        "orchestrator.workflow.active_count",
        "orchestrator.mcp.registered_capabilities",
        "orchestrator.pending_plans",
    }.issubset(gauge_names)


def test_metric_catalog_histogram_helper_emit() -> None:
    collector = _Collector()
    metrics = OrchestratorMetrics(enabled=True, collector=collector)

    metrics.observe_dag_duration(duration_ms=12.5, tier="HIGH")

    points = _find(collector.points, "orchestrator.dag.duration_ms")
    assert len(points) == 1
    assert points[0].value_ms == 12.5
    assert points[0].tags["tier"] == "HIGH"
