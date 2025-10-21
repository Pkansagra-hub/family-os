from __future__ import annotations

from opentelemetry import trace
from ward import test  # type: ignore[attr-defined]

from k0.obs.tracing import TracerFactory


@test("tracer factory generates 32-character trace identifiers")
def _() -> None:
    factory = TracerFactory(
        service_name="test-service",
        service_version="0.0-test",
        environment="test",
        otlp_endpoint=None,
    )

    trace_id = factory.new_trace_id()
    assert len(trace_id) == 32

    token = factory.attach_cognitive_trace(trace_id)
    try:
        assert factory.current_cognitive_trace_id() == trace_id
    finally:
        factory.detach(token)


@test("span helper establishes current context")
def _() -> None:
    factory = TracerFactory(
        service_name="test-service",
        service_version="0.0-test",
        environment="test",
        otlp_endpoint=None,
    )

    with factory.span("test-span"):
        current_span = trace.get_current_span()
        assert current_span.get_span_context().is_valid


@test("context propagation via inject and extract succeeds")
def _() -> None:
    factory = TracerFactory(
        service_name="test-service",
        service_version="0.0-test",
        environment="test",
        otlp_endpoint=None,
    )

    carrier: dict[str, str] = {}
    factory.inject(carrier)

    extracted = factory.extract(carrier)
    with factory.span("child-span", context_override=extracted):
        current_span = trace.get_current_span()
        assert current_span.get_span_context().is_valid
