from __future__ import annotations

from textwrap import dedent

from prometheus_client.exposition import (
    CONTENT_TYPE_LATEST as PROM_CONTENT_TYPE_LATEST,
)  # type: ignore[attr-defined]
from ward import test  # type: ignore[attr-defined]

from k0.obs.events import ObservabilityEmitter
from k0.obs.metrics import CONTENT_TYPE_LATEST, MetricsExporter


@test("metrics exporter increments counters with labels")
def _() -> None:
    exporter = MetricsExporter(namespace="test_kernel")
    exporter.emit("requests_total", 3, outcome="success")
    exporter.emit("requests_total", 2, outcome="success")

    payload = exporter.latest().decode()
    expected_line = 'test_kernel_requests_total{outcome="success"} 5'
    assert expected_line in payload or expected_line + ".0" in payload
    assert CONTENT_TYPE_LATEST == PROM_CONTENT_TYPE_LATEST


@test("metrics exporter records histogram observations")
def _() -> None:
    exporter = MetricsExporter(namespace="test_kernel")
    exporter.observe(
        "latency_seconds",
        0.25,
        labels={"route": "/k0/command.submit"},
        buckets=(0.1, 0.5, 1.0),
    )
    exporter.observe(
        "latency_seconds",
        0.45,
        labels={"route": "/k0/command.submit"},
        buckets=(0.1, 0.5, 1.0),
    )

    payload = exporter.latest().decode()
    snapshot = dedent(
        """
        test_kernel_latency_seconds_bucket{le="0.5",route="/k0/command.submit"} 2.0
        test_kernel_latency_seconds_bucket{le="+Inf",route="/k0/command.submit"} 2.0
        test_kernel_latency_seconds_count{route="/k0/command.submit"} 2.0
        test_kernel_latency_seconds_sum{route="/k0/command.submit"} 0.7
        """
    ).strip()
    for line in snapshot.splitlines():
        assert line in payload


@test("metrics exporter sets gauges")
def _() -> None:
    exporter = MetricsExporter(namespace="test_kernel")
    exporter.set_gauge("queue_depth", 7, driver="outbox")

    payload = exporter.latest().decode()
    assert 'test_kernel_queue_depth{driver="outbox"} 7' in payload


@test("metrics exporter forwards counter updates to observability emitter")
def _() -> None:
    emitter = ObservabilityEmitter()
    exporter = MetricsExporter(observability_emitter=emitter)

    exporter.emit("command_requests_total", value=4.0, port="command")

    events = emitter.snapshot()
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "metric_update"
    assert event["metric"] == "command_requests_total"
    assert event["operation"] == "counter"
    assert event["value"] == 4.0
    assert event["labels"] == {"port": "command"}
    assert event["namespace"] == "k0_kernel"


@test("observability emitter attachment works after exporter creation")
def _() -> None:
    exporter = MetricsExporter(namespace="custom_kernel")
    emitter = ObservabilityEmitter()
    exporter.attach_observability_emitter(emitter)

    exporter.set_gauge("kernel_ready_state", 1.0)

    events = emitter.snapshot()
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "metric_update"
    assert event["operation"] == "gauge"
    assert event["namespace"] == "custom_kernel"
    assert event["value"] == 1.0
    assert event["labels"] == {}
