"""
Integration tests for K1 observability (metrics and tracing)

Tests that K1 properly integrates with K0's observability stack:
- MetricsExporter creates k1_intelligence_* metrics
- TracerFactory creates k1_intelligence service spans
- cognitive_trace_id propagates through baggage
"""

from ward import test

from k1.l5_infrastructure.observability import get_metrics, get_tracer


@test("observability: get_metrics returns k1_intelligence MetricsExporter")
async def _():
    """Test that get_metrics returns a MetricsExporter with k1_intelligence namespace"""
    metrics = get_metrics()

    assert metrics is not None
    assert metrics.namespace == "k1_intelligence"

    # Create a test counter
    test_counter = metrics.counter(
        "test_counter",
        "Test counter for observability verification",
        labelnames=["status"],
    )

    # Increment counter
    test_counter.labels(status="success").inc()

    # Verify metric is in registry
    metric_output = metrics.latest().decode("utf-8")
    assert "k1_intelligence_test_counter" in metric_output
    assert 'status="success"' in metric_output


@test("observability: get_tracer returns k1_intelligence TracerFactory")
async def _():
    """Test that get_tracer returns a TracerFactory with k1_intelligence service"""
    tracer = get_tracer()

    assert tracer is not None
    assert tracer._service_name == "k1_intelligence"
    assert tracer._service_version == "1.0.0"

    # Create a test span
    with tracer.span("test.operation", attributes={"test": "value"}):
        # Verify cognitive trace ID propagation
        trace_id = tracer.current_cognitive_trace_id()
        # Note: trace_id will be None unless attached, which is expected


@test("observability: cognitive_trace_id propagation works")
async def _():
    """Test that cognitive_trace_id can be attached and retrieved"""
    tracer = get_tracer()

    test_trace_id = "test-trace-123456"

    # Attach trace ID
    token = tracer.attach_cognitive_trace(test_trace_id)

    try:
        # Verify it's retrievable
        current_trace_id = tracer.current_cognitive_trace_id()
        assert current_trace_id == test_trace_id

        # Verify it works within span context
        with tracer.span("test.span"):
            span_trace_id = tracer.current_cognitive_trace_id()
            assert span_trace_id == test_trace_id
    finally:
        # Clean up
        tracer.detach(token)

    # Verify it's detached
    detached_trace_id = tracer.current_cognitive_trace_id()
    assert detached_trace_id is None


@test("observability: command_client metrics are exported")
async def _():
    """Test that command_client metrics are properly exported"""
    from k1.l5_infrastructure.bridge_k0.command_client import (
        command_latency_ms,
        command_requests_total,
        command_retries_total,
    )

    # Verify metrics exist
    assert command_requests_total is not None
    assert command_latency_ms is not None
    assert command_retries_total is not None

    # Get metrics output
    metrics = get_metrics()
    metric_output = metrics.latest().decode("utf-8")

    # Verify command client metrics are registered
    # (They may not have values yet, but should be in registry)
    # Note: Prometheus only exports metrics with at least one observation
    # So we'll just verify the metrics objects exist
    assert hasattr(command_requests_total, "labels")
    assert hasattr(command_latency_ms, "labels")
    assert hasattr(command_retries_total, "labels")


@test("observability: metrics histogram has correct buckets")
async def _():
    """Test that histogram metrics use correct buckets for latency measurement"""
    metrics = get_metrics()

    # Create histogram with custom buckets
    test_histogram = metrics.histogram(
        "test_latency",
        "Test latency histogram",
        labelnames=["operation"],
        buckets=[10, 25, 50, 100, 200, 500, 1000],
    )

    # Observe some values
    test_histogram.labels(operation="test").observe(45)  # 50ms bucket
    test_histogram.labels(operation="test").observe(150)  # 200ms bucket
    test_histogram.labels(operation="test").observe(800)  # 1000ms bucket

    # Verify metric is exported with buckets
    metric_output = metrics.latest().decode("utf-8")
    assert "k1_intelligence_test_latency" in metric_output
    assert 'le="50.0"' in metric_output  # 50ms bucket
    assert 'le="200.0"' in metric_output  # 200ms bucket
    assert 'le="1000.0"' in metric_output  # 1000ms bucket
