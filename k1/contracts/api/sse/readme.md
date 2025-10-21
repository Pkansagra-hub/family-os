# Server-Sent Events (SSE) API Contracts

**Source ADRs:** ADR-0019, ADR-0042, ADR-0043, ADR-0046

## Overview

This directory contains SSE API contracts for K1's unidirectional streaming from server to client, including K0 event streaming and real-time updates.

## SSE Protocol

- **Protocol:** Server-Sent Events (SSE) / EventSource
- **Format:** text/event-stream
- **Direction:** Server → Client (unidirectional)
- **Reconnection:** Automatic with Last-Event-ID

## Connection Establishment

```yaml
connection:
  url: https://k1.local/v1/events
  method: GET

  query_parameters:
    session_id: string (required)
    token: string (authentication token)
    topics: string (comma-separated topic filters, optional)

  example:
    https://k1.local/v1/events?session_id=sess-abc123&token=<token>&topics=session.*,agent.*

request_headers:
  Accept: text/event-stream
  Authorization: Bearer <token>
  Cache-Control: no-cache

response_headers:
  Content-Type: text/event-stream
  Cache-Control: no-cache
  Connection: keep-alive
  X-Accel-Buffering: no  # Disable nginx buffering
```

## Event Format

```yaml
sse_event:
  id: string (event ID for cursor-based replay)
  event: string (event type)
  data: JSON string (event payload)
  retry: integer (reconnection delay in ms, optional)

example:
  id: evt-001
  event: turn.started
  data: {"turn_id":"turn-123","session_id":"sess-abc123"}

  id: evt-002
  event: turn.chunk
  data: {"turn_id":"turn-123","chunk":"Quantum computing is ","sequence":1}
```

## Event Types

### Session Events

#### session.created
```yaml
event: session.created
data:
  session_id: string
  created_at: timestamp
  user_id: string
```

#### session.updated
```yaml
event: session.updated
data:
  session_id: string
  updated_at: timestamp
  changes: object
```

#### session.terminated
```yaml
event: session.terminated
data:
  session_id: string
  terminated_at: timestamp
  reason: string
```

### Turn Events

#### turn.started
```yaml
event: turn.started
data:
  turn_id: string
  session_id: string
  trace_id: string
```

#### turn.chunk
```yaml
event: turn.chunk
data:
  turn_id: string
  chunk_type: token | tool_call | metadata
  chunk: string | object
  sequence: integer
```

#### turn.completed
```yaml
event: turn.completed
data:
  turn_id: string
  session_id: string
  result: string
  duration_ms: integer
  trace_id: string
```

#### turn.failed
```yaml
event: turn.failed
data:
  turn_id: string
  error_type: string
  error_message: string
  trace_id: string
```

### Agent Events

#### agent.hired
```yaml
event: agent.hired
data:
  agent_id: string
  agent_type: planner | executor | tool_caller | clarifier
  session_id: string
  capabilities: [string]
```

#### agent.state_changed
```yaml
event: agent.state_changed
data:
  agent_id: string
  from_state: string
  to_state: string
  timestamp: string
```

#### agent.terminated
```yaml
event: agent.terminated
data:
  agent_id: string
  reason: string
  timestamp: string
```

### Tool Events

#### tool.called
```yaml
event: tool.called
data:
  tool_id: string
  tool_name: string
  parameters: object
  trace_id: string
```

#### tool.completed
```yaml
event: tool.completed
data:
  tool_id: string
  result: object
  duration_ms: integer
  trace_id: string
```

### K0 Events (from K0 SSE Bridge)

#### k0.memory.stored
```yaml
event: k0.memory.stored
data:
  entry_id: string
  session_id: string
  content_preview: string
  timestamp: string
```

#### k0.memory.recalled
```yaml
event: k0.memory.recalled
data:
  query: string
  result_count: integer
  latency_ms: integer
```

## Topic Hierarchy

**Source:** ADR-0043a

```yaml
topic_hierarchy:
  format: <scope>.<entity>.<action>

  examples:
    session.created
    session.updated
    session.terminated

    turn.started
    turn.chunk
    turn.completed
    turn.failed

    agent.hired
    agent.state_changed
    agent.terminated

    tool.called
    tool.completed
    tool.failed

    k0.memory.stored
    k0.memory.recalled
```

## Topic Subscription

**Source:** ADR-0043b

```yaml
topic_subscription:
  wildcard_patterns:
    single_level: "*"
    multi_level: "**"

  examples:
    "session.*" → All session events
    "agent.*" → All agent events
    "turn.*" → All turn events
    "**" → All events

  filtering:
    - Filter by topic pattern on server side
    - Only send matching events to client
    - Reduce bandwidth and client processing
```

## Reconnection & Replay

**Source:** ADR-0042c

```yaml
reconnection:
  automatic: true (built into EventSource)

  last_event_id:
    - Client sends Last-Event-ID header on reconnect
    - Server replays events since last_event_id
    - Buffering window: 60 seconds

  example_flow:
    1. Connection lost after event evt-100
    2. Client reconnects with header:
       Last-Event-ID: evt-100
    3. Server replays events evt-101, evt-102, ... evt-150
    4. Resume live stream

request_header:
  Last-Event-ID: evt-100

server_response:
  - Replay buffered events from evt-100 onwards
  - Then switch to live stream
```

## Event Buffering

**Source:** ADR-0042d

```yaml
event_buffering:
  buffer_duration: 60 seconds
  max_buffer_size: 1000 events

  overflow_policy:
    - Drop oldest events
    - Log warning
    - Metric: sse_buffer_overflow_total

  storage:
    - In-memory ring buffer per session
    - Cleared when session terminated
```

## Backpressure Handling

**Source:** ADR-0042d

```yaml
backpressure:
  detection:
    - Client not consuming events (TCP backpressure)
    - Send buffer full

  response:
    - Slow down event production
    - Signal backpressure to K1
    - Drop non-critical events
    - Close connection if still overloaded

  monitoring:
    - Track send buffer size
    - Alert if buffer > 80% full
```

## Performance

```yaml
performance:
  event_latency_p95_ms: 50
  throughput_events_per_sec: 100
  max_event_size_kb: 16

  connection_limits:
    max_connections_per_server: 10000
    max_connections_per_user: 3
```

## Monitoring

```yaml
observability:
  metrics:
    - sse_connections_active
    - sse_events_sent_total{event_type}
    - sse_event_latency_ms{percentile}
    - sse_buffer_size{percentile}
    - sse_reconnections_total

  alerts:
    - SSEConnectionsHigh: active > 8000
    - SSELatencyHigh: p95 > 100ms
    - SSEBufferFull: buffer_size > 80%
```

## Security

```yaml
security:
  authentication:
    - Token in query parameter
    - Validate before accepting connection

  authorization:
    - Verify user can access session events
    - Filter events by privacy band
    - Redact PII if needed

  rate_limiting:
    - Per connection event rate limit
    - Per user connection limit
    - Close connection if exceeded
```

## Usage Example

```javascript
// Client-side JavaScript (EventSource)
const eventSource = new EventSource(
  'https://k1.local/v1/events?session_id=sess-abc123&token=<token>&topics=turn.*,agent.*'
);

eventSource.addEventListener('turn.chunk', (event) => {
  const data = JSON.parse(event.data);
  console.log('Chunk:', data.chunk);
});

eventSource.addEventListener('turn.completed', (event) => {
  const data = JSON.parse(event.data);
  console.log('Turn completed:', data.result);
});

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
  // EventSource will automatically reconnect
};
```

## Comparison: SSE vs WebSocket

```yaml
comparison:
  sse:
    direction: Server → Client only
    reconnection: Automatic with replay
    protocol: HTTP/1.1 or HTTP/2
    use_cases:
      - Real-time updates
      - Event streaming
      - Progress notifications

  websocket:
    direction: Bidirectional
    reconnection: Manual (app-level)
    protocol: WebSocket (RFC 6455)
    use_cases:
      - Interactive communication
      - Request/response
      - Client-initiated actions
```

## Related Contracts

- K0 SSE: `../../k0_sse/`
- Bridge Integration: `../../bridge_integration/sse_websocket_bridge.yaml`
- REST API: `../rest/`
- WebSocket API: `../websocket/`

---

**Last Updated:** 2025-10-13
