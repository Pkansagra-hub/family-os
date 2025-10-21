# K0 Bridge Contracts

**Source ADRs:** ADR-0001a (K0 Bridge Communication Protocol), ADR-0001f (State Boundary Management)

## Overview

The K0 Bridge provides the critical communication layer between K1 (agentic orchestrator kernel) and K0 (persistent memory system). This contract defines the 20 bidirectional ports, batching strategies, error handling, and performance guarantees for all K1-K0 interactions.

## Architecture

```
K1 Intelligence Module
       │
       │ K0 Bridge (HTTP/2 + FlatBuffers)
       │ ├─ P01: Recall Query (most critical)
       │ ├─ P02-P20: Other memory operations
       │ └─ Batching Layer (10-50 messages, 100ms flush)
       │
       ▼
K0 Persistent Memory System
```

## Contracts Included

This directory contains:

1. **Port Specifications** (`ports/README.md`) - All 20 K0 Bridge ports (P01-P20)
2. **Batching Strategies** (`batching/README.md`) - Message batching, flushing, compression
3. **Error Handling** - Circuit breaker, retry policies, fallback strategies
4. **Performance Budgets** - Latency targets, throughput requirements, memory limits

## Key Design Principles

### 1. Separation of Concerns

```yaml
responsibilities:
  k1_kernel:
    - Agent lifecycle management
    - Turn orchestration
    - Real-time decision making
    - Stateless (except SessionState)

  k0_memory:
    - Long-term memory persistence
    - Vector search
    - Knowledge graph
    - FTS indexing

  k0_bridge:
    - Protocol translation (K1 ↔ K0)
    - Message batching
    - Circuit breaking
    - Request routing
```

### 2. Zero Trust Communication

```yaml
zero_trust:
  authentication:
    - Every K0 request includes auth token
    - Token rotation every 24 hours
    - Mutual TLS for transport security

  authorization:
    - Fine-grained permissions per port
    - Privacy band validation (GREEN/AMBER/RED)
    - Audit logging for all RED band access

  validation:
    - Schema validation via FlatBuffers
    - Semantic validation via arbiter
    - Rate limiting per session
```

### 3. Performance Optimization

```yaml
optimization_strategies:
  batching:
    - Batch size: 10-50 messages
    - Flush interval: 100ms
    - Priority lanes: recall_query always fast-tracked

  compression:
    - LZ4 for message payloads >1KB
    - Compression ratio: ~3:1 typical
    - Decompression overhead: <10us

  connection_pooling:
    - HTTP/2 multiplexing (100 concurrent streams)
    - Connection reuse across requests
    - Graceful connection drain on restart
```

## Port Overview (20 Ports)

```yaml
port_categories:
  critical_path_ports: # Latency-sensitive
    - P01: Recall Query (<200ms p95)
    - P11: Stream Flush (<50ms p95)

  standard_ports: # Normal latency
    - P02: Write Memory Chunk
    - P03: Update Memory Chunk
    - P04: Delete Memory Chunk
    - P05: Create Snapshot
    - P06: FTS Query
    - P07: Vector Search
    - P08: KG Query
    - P09: Hybrid Recall
    - P10: Get Snapshot
    - P12: Compact Memory
    - P13: Backup Request
    - P14: Restore Request
    - P15: Health Check

  admin_ports: # Low priority
    - P16: Metrics Export
    - P17: Config Sync
    - P18: Schema Migration
    - P19: Reindex Request
    - P20: Vacuum Database
```

## Communication Protocol

### Request/Response Format

```yaml
k0_request:
  format: FlatBuffers
  schema: K0Request.fbs
  fields:
    - request_id: string (UUID)
    - port: uint8 (P01-P20)
    - session_id: string
    - trace_id: string (cognitive_trace_id)
    - auth_token: string
    - payload: [ubyte] (port-specific FlatBuffers)
    - timeout_ms: uint32
    - priority: enum (HIGH, NORMAL, LOW)

k0_response:
  format: FlatBuffers
  schema: K0Response.fbs
  fields:
    - request_id: string (matches request)
    - status: enum (SUCCESS, ERROR, TIMEOUT)
    - payload: [ubyte] (port-specific FlatBuffers)
    - error_code: uint16 (if status=ERROR)
    - error_message: string (if status=ERROR)
    - latency_ms: uint32
    - k0_node_id: string (which K0 node handled request)
```

### HTTP/2 Transport

```yaml
http2_config:
  endpoint: https://k0.internal:443/bridge
  protocol: HTTP/2 with TLS 1.3

  headers:
    Content-Type: application/flatbuffers
    X-K1-Session-ID: <session_id>
    X-K1-Trace-ID: <trace_id>
    X-K1-Port: <port_number>
    Authorization: Bearer <token>

  multiplexing:
    max_concurrent_streams: 100
    stream_priority: P01 > P11 > others

  connection_management:
    max_connections: 10
    idle_timeout: 300s
    keepalive_interval: 60s
```

## Batching Strategy

### Adaptive Batching

```yaml
batching_algorithm:
  batch_size:
    min: 10 messages
    max: 50 messages
    target: 25 messages (adaptive)

  flush_triggers:
    - Time-based: 100ms since first message
    - Size-based: 50 messages accumulated
    - Priority-based: HIGH priority message bypasses batch

  adaptive_tuning:
    - Monitor average batch size
    - If avg < 15: increase flush interval to 150ms
    - If avg > 40: decrease flush interval to 75ms
    - Rebalance every 60 seconds
```

### Port-Specific Batching

```yaml
batching_rules:
  p01_recall_query:
    batching: DISABLED # Always fast-tracked
    reason: Critical path for turn latency

  p02_write_memory:
    batching: ENABLED
    max_batch_size: 50
    flush_interval_ms: 100

  p06_fts_query:
    batching: ENABLED
    max_batch_size: 25 # Queries more expensive
    flush_interval_ms: 150

  p11_stream_flush:
    batching: DISABLED # Streaming sensitive
    reason: Low latency required for streaming
```

## Error Handling

### Circuit Breaker

```yaml
circuit_breaker:
  states: [CLOSED, OPEN, HALF_OPEN]

  thresholds:
    failure_rate: 50% over 10 requests
    slow_call_rate: 75% over 20 requests (>2000ms)
    open_duration: 60s

  behavior:
    CLOSED: All requests pass through
    OPEN: All requests fail-fast with error
    HALF_OPEN: 5 test requests, then re-evaluate

  per_port: true # Each port has independent circuit breaker
```

### Retry Policy

```yaml
retry_policy:
  retryable_errors:
    - HTTP 503 (Service Unavailable)
    - HTTP 429 (Too Many Requests)
    - Network timeout
    - Connection reset

  non_retryable_errors:
    - HTTP 400 (Bad Request)
    - HTTP 401 (Unauthorized)
    - HTTP 404 (Not Found)
    - Validation errors

  retry_strategy:
    max_attempts: 3
    backoff: exponential (100ms, 200ms, 400ms)
    jitter: ±20% to avoid thundering herd
```

### Fallback Strategies

```yaml
fallback_strategies:
  p01_recall_query:
    fallback: Return empty results + log error
    reason: Don't block turn execution

  p02_write_memory:
    fallback: Queue write for later retry
    reason: Eventual consistency acceptable

  p15_health_check:
    fallback: Return cached health status (if <60s old)
    reason: Avoid false positives from transient failures
```

## Performance Requirements

```yaml
performance_budgets:
  latency:
    p01_recall_query:
      p50: 50ms
      p95: 200ms
      p99: 500ms

    p02_write_memory:
      p50: 20ms
      p95: 100ms
      p99: 250ms

    p06_fts_query:
      p50: 100ms
      p95: 500ms
      p99: 1000ms

  throughput:
    total_requests_per_second: 10000
    p01_recall_query: 5000 req/s
    p02_write_memory: 3000 req/s

  connection_limits:
    max_connections: 10 per K1 instance
    max_concurrent_requests: 100 per connection

  memory:
    batch_buffer_size: 1MB per port
    total_bridge_memory: 50MB
```

## Observability

### Metrics (Prometheus)

```yaml
metrics:
  request_metrics:
    - k0_bridge_requests_total{port, status, k0_node}
    - k0_bridge_request_duration_ms{port, percentile}
    - k0_bridge_request_size_bytes{port, percentile}
    - k0_bridge_response_size_bytes{port, percentile}

  batching_metrics:
    - k0_bridge_batch_size{port, percentile}
    - k0_bridge_batch_flush_reason{port, reason} # time/size/priority
    - k0_bridge_batch_latency_ms{port, percentile}

  error_metrics:
    - k0_bridge_errors_total{port, error_type, k0_node}
    - k0_bridge_circuit_breaker_state{port} # 0=CLOSED, 1=OPEN, 2=HALF_OPEN
    - k0_bridge_retries_total{port, attempt}

  connection_metrics:
    - k0_bridge_active_connections
    - k0_bridge_connection_errors_total{error_type}
    - k0_bridge_http2_streams_active
```

### Tracing (OpenTelemetry)

```yaml
tracing:
  span_structure:
    - Span: "k0_bridge.request"
      - Attributes: port, session_id, request_id
      - Child: "k0_bridge.batch_enqueue"
      - Child: "k0_bridge.http2_send"
      - Child: "k0_bridge.http2_receive"
      - Child: "k0_bridge.deserialize_response"

  trace_propagation:
    - K1 cognitive_trace_id → K0 trace_id
    - W3C Trace Context headers
    - Baggage for session metadata
```

### Logging

```yaml
logging:
  log_levels:
    normal_requests: DEBUG
    slow_requests: INFO (>500ms)
    failed_requests: WARNING
    circuit_breaker_open: ERROR

  structured_fields:
    - trace_id (cognitive_trace_id)
    - session_id
    - port
    - request_id
    - latency_ms
    - status
    - k0_node_id
    - error_code (if failed)
```

## Security Considerations

```yaml
security:
  transport:
    - TLS 1.3 with strong cipher suites
    - Certificate pinning for K0 endpoints
    - Mutual TLS (K1 and K0 authenticate each other)

  authentication:
    - JWT tokens with short expiry (1 hour)
    - Token rotation before expiry
    - Revocation list checked on every request

  authorization:
    - Per-port ACLs (Access Control Lists)
    - Privacy band enforcement (GREEN/AMBER/RED)
    - Rate limiting per session (100 req/s default)

  data_protection:
    - PII redaction in logs
    - Memory encryption at rest (K0 responsibility)
    - Audit trail for RED band access
```

## Testing Strategies

```yaml
unit_tests:
  - Request/response serialization
  - Circuit breaker state transitions
  - Retry logic with exponential backoff
  - Batch accumulation and flush triggers

integration_tests:
  - End-to-end K1 → K0 → K1 roundtrip
  - Multi-port request parallelism
  - Circuit breaker behavior under load
  - Fallback strategy activation

performance_tests:
  - Latency benchmarks (p50, p95, p99)
  - Throughput stress testing (10K req/s)
  - HTTP/2 multiplexing efficiency
  - Batch size impact on latency

chaos_tests:
  - K0 node failure during request
  - Network partition between K1 and K0
  - Slow K0 responses (>2000ms)
  - K0 restart during active requests
```

## Migration & Versioning

```yaml
versioning:
  protocol_version: 1.0

  schema_evolution:
    - FlatBuffers provides forward/backward compatibility
    - Version field in all K0Request/K0Response
    - Older K1 instances can use newer K0 (ignore new fields)
    - Newer K1 instances can use older K0 (use defaults)

  migration_strategy:
    - Gradual rollout: K0 upgraded first, then K1
    - Feature flags for new port activation
    - Traffic shadowing for validation
    - Rollback plan for failures
```

## Related Contracts

- **Ports Specification:** `./ports/README.md` - Detailed contracts for all 20 ports
- **Batching Details:** `./batching/README.md` - Advanced batching strategies
- **FlatBuffers Schemas:** `../flatbuffers/layer2_state/README.md` - K0Request/K0Response schemas
- **SessionState:** `../sessionstate/README.md` - State synchronization requirements
- **Performance:** `../performance/README.md` - Performance budgets and optimization
- **Error Recovery:** `../error_recovery/README.md` - Circuit breaker and retry patterns

---

**Last Updated:** 2025-10-13

**Total Ports:** 20 bidirectional K1-K0 communication channels
