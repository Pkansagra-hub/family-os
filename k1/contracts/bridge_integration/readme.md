# Bridge Integration Contracts

**Source ADRs:** ADR-0044, ADR-0044a-d, ADR-0045, ADR-0045a-d, ADR-0046

## Overview

This directory contains contracts for K0-K1 bridge integration, agent-agent coordination, and SSE-WebSocket bridging.

## Contracts Included

### 1. HTTP/2 Multiplexing Contract (`http2_multiplexing.yaml`)
- **Source:** ADR-0044a
- HTTP/2 stream management
- Connection pooling rules
- Multiplexing strategies

### 2. FlatBuffers Serialization Strategy (`flatbuffers_strategy.yaml`)
- **Source:** ADR-0044b
- Serialization format selection
- Zero-copy optimization rules
- Schema versioning

### 3. Batching Strategy Contract (`batching_strategy.yaml`)
- **Source:** ADR-0044c
- Batch size limits (10-50 messages)
- Flush interval (100ms)
- Backpressure handling

### 4. Error Handling & Retry Contract (`error_retry.yaml`)
- **Source:** ADR-0044d
- Error classification
- Retry policies (exponential backoff)
- Circuit breaker integration

### 5. K1 Event Bus Pub/Sub Contract (`k1_event_bus.yaml`)
- **Source:** ADR-0045a, ADR-0048
- Internal K1 event bus specification
- Publish/Subscribe patterns
- Event delivery guarantees

### 6. Topic Routing Contract (`topic_routing.yaml`)
- **Source:** ADR-0045b
- Topic-based routing rules
- Subscription management
- Wildcard patterns

### 7. Delivery Guarantees Contract (`delivery_guarantees.yaml`)
- **Source:** ADR-0045c
- At-most-once delivery
- At-least-once delivery
- Exactly-once semantics (where applicable)

### 8. Agent-Agent SSE Coordination (`agent_sse_coordination.yaml`)
- **Source:** ADR-0045
- Inter-agent event coordination
- SSE-based agent messaging
- Event propagation rules

### 9. SSE-WebSocket Bridge Contract (`sse_websocket_bridge.yaml`)
- **Source:** ADR-0046
- SSE to WebSocket translation
- Protocol conversion rules
- Connection management

## Key Specifications

### HTTP/2 Settings
```yaml
http2:
  max_concurrent_streams: 100
  initial_window_size: 65535
  max_frame_size: 16384
  header_table_size: 4096
```

### Batching Configuration
```yaml
batching:
  min_batch_size: 10
  max_batch_size: 50
  flush_interval_ms: 100
  max_payload_size_kb: 64
```

### Retry Policy
```yaml
retry:
  max_attempts: 3
  initial_delay_ms: 100
  max_delay_ms: 5000
  backoff_multiplier: 2
  jitter: true
```

## Usage Examples

See `examples/` directory for implementation examples.

## Related Contracts

- K0 Bridge Ports: `../k0_bridge/ports/`
- K0 SSE Contracts: `../k0_sse/`
- Circuit Breaker: `../error_recovery/circuit_breaker.yaml`

---

**Last Updated:** 2025-10-13
