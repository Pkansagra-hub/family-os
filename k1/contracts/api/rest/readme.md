# REST API Contracts

**Source ADRs:** ADR-0019, ADR-0047

## Overview

This directory contains REST API contracts for K1's HTTP endpoints, including session management, turn submission, and agent management.

## API Standards

- **Protocol:** HTTP/1.1 and HTTP/2
- **Format:** JSON (request/response)
- **Authentication:** Bearer tokens
- **Versioning:** URL path (`/v1/`)
- **Error Format:** RFC 7807 Problem Details

## Endpoints

### Session Management

#### POST /v1/sessions
Create a new session.

```yaml
request:
  body:
    user_id: string
    preferences: object
    initial_context: string | null

  example:
    {
      "user_id": "user-123",
      "preferences": {"voice_enabled": true},
      "initial_context": null
    }

response:
  status: 201 Created
  body:
    session_id: string
    created_at: timestamp
    expires_at: timestamp

  example:
    {
      "session_id": "sess-abc123",
      "created_at": "2025-10-13T10:00:00Z",
      "expires_at": "2025-10-13T11:00:00Z"
    }
```

#### GET /v1/sessions/{session_id}
Get session details.

```yaml
response:
  status: 200 OK
  body:
    session_id: string
    created_at: timestamp
    last_activity: timestamp
    turn_count: integer
    active: boolean
```

#### DELETE /v1/sessions/{session_id}
Terminate session.

```yaml
response:
  status: 204 No Content
```

### Turn Management

#### POST /v1/sessions/{session_id}/turns
Submit a new turn.

```yaml
request:
  body:
    content: string
    modality: text | voice
    metadata: object | null

  example:
    {
      "content": "What is quantum computing?",
      "modality": "text",
      "metadata": null
    }

response:
  status: 202 Accepted
  body:
    turn_id: string
    session_id: string
    status: processing | completed | failed

  headers:
    Location: /v1/sessions/{session_id}/turns/{turn_id}
```

#### GET /v1/sessions/{session_id}/turns/{turn_id}
Get turn status and result.

```yaml
response:
  status: 200 OK
  body:
    turn_id: string
    session_id: string
    status: processing | completed | failed
    result: string | null
    error: object | null
    created_at: timestamp
    completed_at: timestamp | null
```

### Agent Management

#### GET /v1/agents
List available agents.

```yaml
response:
  status: 200 OK
  body:
    agents:
      - agent_id: string
        agent_type: string
        capabilities: [string]
        state: string
```

#### GET /v1/agents/{agent_id}
Get agent details.

```yaml
response:
  status: 200 OK
  body:
    agent_id: string
    agent_type: planner | executor | tool_caller | clarifier
    capabilities: [string]
    state: PENDING | WARMING | ACTIVE | IDLE | DRAINING | TERMINATED
    memory_mb: integer
```

## Error Responses (RFC 7807)

```yaml
error_format:
  type: string         # URI identifying problem type
  title: string        # Short, human-readable summary
  status: integer      # HTTP status code
  detail: string       # Detailed explanation
  instance: string     # URI to specific occurrence
  trace_id: string     # cognitive_trace_id

example:
  {
    "type": "https://k1.local/errors/session-not-found",
    "title": "Session Not Found",
    "status": 404,
    "detail": "Session 'sess-abc123' does not exist or has expired",
    "instance": "/v1/sessions/sess-abc123",
    "trace_id": "trace-xyz789"
  }
```

## HTTP Status Codes

```yaml
status_codes:
  2xx_success:
    200: OK - Request succeeded
    201: Created - Resource created
    202: Accepted - Request accepted for async processing
    204: No Content - Request succeeded, no response body

  4xx_client_errors:
    400: Bad Request - Invalid request format
    401: Unauthorized - Missing or invalid authentication
    403: Forbidden - Insufficient permissions
    404: Not Found - Resource not found
    409: Conflict - Resource state conflict
    429: Too Many Requests - Rate limit exceeded

  5xx_server_errors:
    500: Internal Server Error - Unexpected error
    503: Service Unavailable - K1 overloaded or down
    504: Gateway Timeout - Request timeout
```

## Rate Limiting

```yaml
rate_limiting:
  strategy: token_bucket

  limits:
    per_user:
      requests_per_minute: 60
      burst: 10

    per_ip:
      requests_per_minute: 100
      burst: 20

  headers:
    X-RateLimit-Limit: Maximum requests
    X-RateLimit-Remaining: Remaining requests
    X-RateLimit-Reset: Reset timestamp

  response_on_limit:
    status: 429 Too Many Requests
    retry_after: seconds until reset
```

## Authentication

```yaml
authentication:
  method: Bearer token

  header:
    Authorization: "Bearer <token>"

  token_validation:
    - Verify signature
    - Check expiration
    - Validate scope

  error_responses:
    missing_token:
      status: 401
      message: "Missing Authorization header"

    invalid_token:
      status: 401
      message: "Invalid or expired token"

    insufficient_scope:
      status: 403
      message: "Token lacks required scope"
```

## CORS

```yaml
cors:
  enabled: true

  allowed_origins:
    - https://app.k1.local
    - https://dashboard.k1.local

  allowed_methods:
    - GET
    - POST
    - PUT
    - DELETE
    - OPTIONS

  allowed_headers:
    - Authorization
    - Content-Type
    - X-Trace-Id

  exposed_headers:
    - X-RateLimit-Limit
    - X-RateLimit-Remaining
    - X-RateLimit-Reset

  credentials: true
  max_age: 3600
```

## Performance

```yaml
performance:
  latency_targets:
    p50: 50ms
    p95: 150ms
    p99: 300ms

  timeout: 30s

  connection_pooling:
    max_connections: 1000
    keep_alive: 60s
```

## Related Contracts

- API Specs: `../../api_specs/`
- OpenAPI: `../../api_specs/openapi_3_1_specs/`
- WebSocket: `../websocket/`

---

**Last Updated:** 2025-10-13
