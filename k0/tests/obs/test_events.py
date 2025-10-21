from __future__ import annotations

from ward import test  # type: ignore[attr-defined]

from k0.obs.events import ObservabilityEmitter
from k0.obs.tracing import TracerFactory


@test("observability emitter adds active cognitive trace identifier when missing")
def _() -> None:
    emitter = ObservabilityEmitter()
    tracer_factory = TracerFactory(
        service_name="test-service",
        service_version="0.1",
        environment="test",
        otlp_endpoint=None,
    )

    trace_id = tracer_factory.new_trace_id()
    token = tracer_factory.attach_cognitive_trace(trace_id)
    try:
        emitter.emit({"event": "unit-test"})
    finally:
        tracer_factory.detach(token)

    events = emitter.snapshot()
    assert len(events) == 1
    assert events[0]["trace_id"] == trace_id


@test("observability emitter preserves explicit trace identifiers")
def _() -> None:
    emitter = ObservabilityEmitter()

    explicit_trace = "feedbead" * 4
    emitter.emit({"event": "unit-test", "trace_id": explicit_trace})

    events = emitter.snapshot()
    assert len(events) == 1
    assert events[0]["trace_id"] == explicit_trace
