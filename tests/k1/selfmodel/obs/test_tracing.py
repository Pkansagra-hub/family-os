"""M4.E4.I2 — selfmodel tracing helper tests."""

from __future__ import annotations

from k1.selfmodel.obs.tracing import OTEL_AVAILABLE, trace_span


def test_trace_span_no_tracer_is_noop() -> None:
    with trace_span("x", tracer=None, trace_id="trace-1") as span:
        assert span is None


def test_trace_span_with_real_tracer_sets_attribute() -> None:
    if not OTEL_AVAILABLE:
        # No-op path already covered above; nothing more to assert.
        return

    captured: dict[str, object] = {}

    class FakeSpan:
        def set_attribute(self, k, v):
            captured[k] = v

    class FakeCM:
        def __enter__(self):
            return FakeSpan()

        def __exit__(self, *a):
            return False

    class FakeTracer:
        def start_as_current_span(self, name):
            captured["name"] = name
            return FakeCM()

    with trace_span("compose_frame", tracer=FakeTracer(), trace_id="t-42", attributes={"k": "v"}):
        pass

    assert captured["name"] == "compose_frame"
    assert captured["cognitive_trace_id"] == "t-42"
    assert captured["k"] == "v"


def test_trace_span_swallows_tracer_errors() -> None:
    if not OTEL_AVAILABLE:
        return

    class BoomTracer:
        def start_as_current_span(self, name):
            raise RuntimeError("tracer down")

    # Must not propagate.
    with trace_span("x", tracer=BoomTracer(), trace_id="t") as span:
        assert span is None
