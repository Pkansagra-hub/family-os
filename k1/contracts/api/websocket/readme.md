# WebSocket API Contracts

**Source ADRs:** ADR-0019, ADR-0047

## Overview

This directory contains WebSocket API contracts for K1's real-time bidirectional communication, including streaming responses and live updates.

## WebSocket Protocol

- **Protocol:** WebSocket (RFC 6455)
- **Subprotocol:** `k1.v1.json`
- **Format:** JSON messages
- **Authentication:** Token in connection URL or initial message

## Connection Lifecycle

### 1. Connection Establishment

```yaml
connection:
  url: wss://k1.local/v1/ws

  query_parameters:
    session_id: string (optional, create new if omitted)
    token: string (authentication token)

  example:
    wss://k1.local/v1/ws?session_id=sess-abc123&token=<bearer_token>

handshake:
  request:
    GET /v1/ws HTTP/1.1
    Host: k1.local
    Upgrade: websocket
    Connection: Upgrade
    Sec-WebSocket-Key: <key>
    Sec-WebSocket-Protocol: k1.v1.json

  response:
    HTTP/1.1 101 Switching Protocols
    Upgrade: websocket
    Connection: Upgrade
    Sec-WebSocket-Accept: <accept>
    Sec-WebSocket-Protocol: k1.v1.json
```

### 2. Initial Message

```yaml
client_to_server:
  type: "connect"
  payload:
    session_id: string | null
    user_id: string
    preferences: object | null

  example:
    {
      "type": "connect",
      "payload": {
        "session_id": null,
        "user_id": "user-123",
        "preferences": {"voice_enabled": true}
      }
    }

server_to_client:
  type: "connected"
  payload:
    session_id: string
    connection_id: string

  example:
    {
      "type": "connected",
      "payload": {
        "session_id": "sess-abc123",
        "connection_id": "conn-xyz789"
      }
    }
```

### 3. Message Exchange

```yaml
message_structure:
  type: string (message type)
  payload: object (type-specific data)
  message_id: string (UUID, optional)
  trace_id: string (cognitive_trace_id, optional)
  timestamp: string (ISO 8601)
```

## Message Types

### Client → Server

#### turn_submit
Submit a new turn.

```yaml
message:
  type: "turn_submit"
  payload:
    content: string
    modality: text | voice
    metadata: object | null
  message_id: string
  trace_id: string

example:
  {
    "type": "turn_submit",
    "payload": {
      "content": "What is quantum computing?",
      "modality": "text"
    },
    "message_id": "msg-001",
    "trace_id": "trace-abc"
  }
```

#### barge_in
Interrupt ongoing turn.

```yaml
message:
  type: "barge_in"
  payload:
    turn_id: string
    reason: user_interrupt | timeout | error
  message_id: string

example:
  {
    "type": "barge_in",
    "payload": {
      "turn_id": "turn-123",
      "reason": "user_interrupt"
    },
    "message_id": "msg-002"
  }
```

#### ping
Heartbeat to keep connection alive.

```yaml
message:
  type: "ping"
  payload: {}
  message_id: string

response:
  type: "pong"
  payload: {}
  message_id: string (same as ping)
```

### Server → Client

#### turn_start
Turn processing started.

```yaml
message:
  type: "turn_start"
  payload:
    turn_id: string
    session_id: string
  trace_id: string
```

#### turn_chunk
Streaming response chunk.

```yaml
message:
  type: "turn_chunk"
  payload:
    turn_id: string
    chunk_type: token | tool_call | metadata
    data: string | object
    sequence: integer
  trace_id: string

example:
  {
    "type": "turn_chunk",
    "payload": {
      "turn_id": "turn-123",
      "chunk_type": "token",
      "data": "Quantum computing is ",
      "sequence": 1
    },
    "trace_id": "trace-abc"
  }
```

#### turn_complete
Turn processing completed.

```yaml
message:
  type: "turn_complete"
  payload:
    turn_id: string
    result: string
    metadata:
      duration_ms: integer
      tokens_generated: integer
  trace_id: string
```

#### turn_error
Turn processing failed.

```yaml
message:
  type: "turn_error"
  payload:
    turn_id: string
    error:
      type: string
      message: string
      retryable: boolean
  trace_id: string
```

#### agent_update
Agent state changed.

```yaml
message:
  type: "agent_update"
  payload:
    agent_id: string
    state: PENDING | WARMING | ACTIVE | IDLE | DRAINING | TERMINATED
    event: hired | warmup_complete | task_assigned | task_complete
```

#### session_update
Session state changed.

```yaml
message:
  type: "session_update"
  payload:
    session_id: string
    event: created | updated | terminated
    metadata: object
```

## Error Handling

```yaml
websocket_errors:
  connection_errors:
    1000: Normal closure
    1001: Going away (server shutdown)
    1002: Protocol error
    1003: Unsupported data
    1006: Abnormal closure (no close frame)
    1008: Policy violation
    1009: Message too big
    1011: Internal server error

  application_errors:
    code: 4000-4999 (custom range)
    examples:
      4000: Invalid message format
      4001: Authentication failed
      4002: Session expired
      4003: Rate limit exceeded
      4004: Barge-in failed
```

## Reconnection Strategy

```yaml
reconnection:
  strategy: exponential_backoff

  config:
    initial_delay_ms: 1000
    max_delay_ms: 30000
    backoff_multiplier: 2
    jitter: true

  resume_session:
    - Include session_id in reconnection URL
    - Server resumes from last acknowledged message
    - Client receives buffered messages

  message_acknowledgement:
    - Client sends ack for each message_id
    - Server buffers unacknowledged messages
    - On reconnect, resend unacknowledged messages
```

## Heartbeat

```yaml
heartbeat:
  interval_ms: 30000
  timeout_ms: 60000

  mechanism:
    - Client sends "ping" every 30s
    - Server responds with "pong"
    - If no pong within 60s, connection dead

  keep_alive:
    - Server sends "ping" if idle > 30s
    - Client must respond with "pong"
```

## Flow Control

```yaml
flow_control:
  message_rate_limit:
    per_connection: 100 messages/minute
    burst: 10 messages

  backpressure:
    - If client slow to consume: buffer server messages
    - If buffer full: apply backpressure to K1
    - If still overloaded: close connection with code 4003

  message_size_limit:
    max_message_size_kb: 64
    enforcement: Close connection with code 1009
```

## Performance

```yaml
performance:
  connection_latency_ms: 100
  message_latency_p95_ms: 50
  throughput_messages_per_sec: 100

  max_connections:
    per_server: 10000
    per_user: 5
```

## Monitoring

```yaml
observability:
  metrics:
    - websocket_connections_active
    - websocket_messages_total{type, direction}
    - websocket_message_latency_ms{percentile}
    - websocket_errors_total{code}
    - websocket_reconnections_total

  alerts:
    - WebSocketConnectionsHigh: active > 8000
    - WebSocketLatencyHigh: p95 > 100ms
    - WebSocketErrorRateHigh: error_rate > 5%
```

## Security

```yaml
security:
  authentication:
    - Token in connection URL (query param)
    - Or token in first message
    - Validate before accepting connection

  message_validation:
    - Validate message format
    - Validate payload against schema
    - Sanitize user inputs

  rate_limiting:
    - Per connection rate limits
    - Per user rate limits
    - Close connection if exceeded
```

## Usage Example

```javascript
// Client-side JavaScript
const ws = new WebSocket(
  'wss://k1.local/v1/ws?session_id=sess-abc123&token=<token>'
);

ws.onopen = () => {
  // Submit turn
  ws.send(JSON.stringify({
    type: 'turn_submit',
    payload: {
      content: 'What is quantum computing?',
      modality: 'text'
    },
    message_id: 'msg-001'
  }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'turn_chunk') {
    // Append streaming chunk
    console.log(msg.payload.data);
  } else if (msg.type === 'turn_complete') {
    // Turn completed
    console.log('Done:', msg.payload.result);
  }
};
```

## Related Contracts

- REST API: `../rest/`
- SSE API: `../sse/`
- API Specs: `../../api_specs/`

---

**Last Updated:** 2025-10-13
