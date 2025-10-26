"""
OpenTelemetry Distributed Tracing - DESIGN DOCUMENT

⚠️ **IMPORTANT: This file is a DESIGN SPECIFICATION, not implementation code.**

**Current Implementation Status:**
- ✅ **IMPLEMENTED:** K1 uses K0's TracerFactory (via k1.l5_infrastructure.observability.get_tracer())
- ✅ **IMPLEMENTED:** Head-based sampling (1% baseline, 100% errors, configurable via OTEL_SAMPLE_RATIO)
- ✅ **IMPLEMENTED:** cognitive_trace_id propagation (W3C Trace Context)
- ✅ **IMPLEMENTED:** OTLP/HTTP export to Tempo (http://localhost:4318/v1/traces)
- ❌ **NOT IMPLEMENTED:** Tail-based sampling (60s buffer, post-decision)
- ❌ **NOT IMPLEMENTED:** Adaptive sampling FSM (NORMAL/DEGRADATION/CRITICAL states)
- ❌ **NOT IMPLEMENTED:** Jaeger-specific integration (Badger storage)

**To use K1 tracing:**
```python
from k1.l5_infrastructure.observability import get_tracer

tracer = get_tracer()  # Returns K0 TracerFactory with k1_intelligence service name
with tracer.span("k1.operation") as span:
    span.set_attribute("key", "value")
```

**This file documents:**
1. Future sampling strategies (tail-based, adaptive)
2. Storage tier design (hot/warm/cold)
3. Performance targets and benchmarks
4. Research citations and ADR references

**See Also:**
- k1/l5_infrastructure/observability/__init__.py (actual tracing glue code)
- k0/obs/tracing.py (K0 TracerFactory implementation)
- ADR-0030: Intelligent Trace Sampling

---

Purpose: Distributed tracing with adaptive sampling for K1
Location: k1/l5_infrastructure/observability/tracing.py
Performance: <5ms span creation

Primary ADRs:
- ADR-0030: Trace Sampling (cognitive_trace_id, 1% sampling)
- ADR-0030a: Head-Based Sampling (baseline 1%, error 100%, slow 100%)
- ADR-0030b: Tail-Based Sampling (span buffering, post-decision) [FUTURE]
- ADR-0030c: Adaptive Sampling (rate adjustment FSM, health indicators) [FUTURE]
- ADR-0030d: Jaeger Integration (OTLP exporter, Badger storage) [FUTURE]
- ADR-0002d: Actor Fabric Observability (actor.send/recv spans)

Related ADRs:
- ADR-0024: Performance Budgets (tracing <5ms)

Key Responsibilities:

1. Span Creation:
   - OpenTelemetry spans (start, end, attributes)
   - Span types: actor.send, actor.recv, router.admission, mailbox.enq, mailbox.deq, layer{N}.operation
   - cognitive_trace_id propagation (128-bit unique ID, hex format)
   - W3C Trace Context format (traceparent header)

2. Trace Sampling (ADR-0030a):
   - Baseline: 1% random sampling (hash-based decision <0.2ms)
   - Error: 100% error sampling (turn_status==ERROR)
   - Slow Request: 100% sampling for >P95 latency (TTFT >150ms, E2E >2000ms)
   - Privacy Band: 100% RED band sampling (audit compliance)
   - Hash-based sampling: hash(cognitive_trace_id) % 100 < sampling_rate

3. Tail-Based Sampling (ADR-0030b):
   - 60s span buffer (<50MB memory)
   - Decision after turn completion (<100ms latency)
   - KEEP (export) or DISCARD (drop)
   - Retention criteria: Errors, slow requests (>P95), RED band, SLO violations
   - TTL-based eviction for overflow protection

4. Adaptive Sampling (ADR-0030c):
   - 3 states: NORMAL (1%), DEGRADATION (10%), CRITICAL (50%)
   - Health-based triggers:
     * NORMAL → DEGRADATION: TTFT >150ms OR error rate >1% OR backpressure events >10/min
     * DEGRADATION → CRITICAL: TTFT >200ms OR error rate >5% OR backpressure sustained >1min
     * CRITICAL/DEGRADATION → NORMAL: Gradual recovery (50%→25%→10%→5%→1%)
   - Hysteresis: 10% margin (prevent oscillation)
   - State persistence: Minimum 60s per state (prevent rapid switching)

5. Trace Export:
   - Export to Jaeger/Zipkin (OTLP protocol over gRPC)
   - Batch export: Every 5s, max 100 spans per batch
   - gRPC OTLP endpoint: localhost:4317
   - Non-blocking async export (<5ms latency)
   - Retry logic: Exponential backoff (1s→2s→4s max)

6. Storage (ADR-0030d):
   - Hot: 7 days (all sampled traces)
   - Warm: 30 days (errors/SLO violations/RED band)
   - Cold: >30 days to S3 (optional, compressed)
   - Cost target: <$50/month (97% reduction vs 100% tracing)
   - Storage volume: 25MB/day typical (175MB hot, 750MB warm)

Performance Metrics:
- Span creation: <5ms P95 (<3ms typical)
- Sampling rate: 1% (normal), 10% (degradation), 50% (critical), 100% (errors)
- Trace export: <50ms per batch
- Storage volume: 25MB/day (175MB hot, 750MB warm)
- Sampling decision: <0.2ms (hash-based)

Implementation Notes:
- Use opentelemetry-sdk-python library
- cognitive_trace_id: 128-bit hex (32 characters)
- Span attributes: actor_id, layer, operation, latency_ms, error
- W3C Trace Context: traceparent header (version-trace_id-span_id-flags)
- Tail-based buffer: LRU eviction, 60s TTL
- Adaptive FSM: State transitions with hysteresis

Example Usage:
    from k1.l5_infrastructure.observability import tracing

    # Create span
    with tracing.start_span("layer2.planning", cognitive_trace_id="abc123...") as span:
        span.set_attribute("agent_id", "planner_001")
        span.set_attribute("task_type", "photo_search")
        result = planner.plan(task)
        span.set_attribute("result_count", len(result))

    # Actor fabric spans
    with tracing.start_span("actor.send", cognitive_trace_id=trace_id) as span:
        span.set_attribute("sender", "orchestrator")
        span.set_attribute("receiver", "planner")
        span.set_attribute("message_type", "TaskAnnouncement")
        actor.send(message)

    # Propagate trace context
    context = tracing.inject_context(cognitive_trace_id)
    # Pass context to downstream service

Research Foundation:
- OpenTelemetry (CNCF distributed tracing standard)
- W3C Trace Context (traceparent header propagation)
- Tail-based sampling (Jaeger, Lightstep)
- Adaptive sampling (dynamic rate adjustment, health-based triggers)
- Google Dapper (distributed tracing paper)

TODO:
- [ ] Implement TracingManager class with OpenTelemetry SDK
- [ ] Implement cognitive_trace_id generation (128-bit UUID4)
- [ ] Implement head-based sampling (1% baseline, 100% errors/slow)
- [ ] Implement tail-based sampling (60s buffer, KEEP/DISCARD decision)
- [ ] Implement adaptive sampling FSM (NORMAL/DEGRADATION/CRITICAL states)
- [ ] Add W3C Trace Context propagation (traceparent header)
- [ ] Add span creation API (start_span, set_attribute, end_span)
- [ ] Add OTLP exporter (gRPC to Jaeger at localhost:4317)
- [ ] Add batch export (5s interval, max 100 spans per batch)
- [ ] Add storage tier management (Hot 7d, Warm 30d, Cold >30d)
- [ ] Add hysteresis for adaptive FSM (10% margin, 60s persistence)
- [ ] Add unit tests for sampling logic and span creation
- [ ] Add integration tests with Jaeger backend
"""

# TODO: Implement TracingManager with OpenTelemetry and adaptive sampling
