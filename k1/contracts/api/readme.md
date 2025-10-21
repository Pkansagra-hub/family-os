# API Contracts Overview

**Source ADRs:** ADR-0044 (API Specifications), ADR-0001e (P21 Integration Pipeline Layer)

## Overview

This directory contains all external API contracts for K1 Intelligence Module. These APIs provide the interface for frontend applications, voice assistants, and third-party integrations to interact with K1's agentic orchestrator kernel.

## API Categories

```yaml
api_types:
  rest_api: # HTTP REST endpoints
    base_path: /api/v1
    transport: HTTP/1.1 or HTTP/2
    format: JSON
    authentication: Bearer token (JWT)
    documentation: OpenAPI 3.1 specification

  websocket_api: # Bidirectional streaming
    endpoint: wss://k1.example.com/ws
    protocol: WebSocket (RFC 6455)
    format: JSON messages
    authentication: Token in query param or header

  sse_api: # Server-Sent Events streaming
    endpoint: /api/v1/stream
    protocol: Server-Sent Events (text/event-stream)
    format: JSON events
    authentication: Bearer token (JWT)
```

## Directory Structure

```
api/
├── rest/           # REST API contracts (HTTP endpoints)
├── websocket/      # WebSocket API contracts (bidirectional streaming)
├── sse/            # Server-Sent Events contracts (server push)
└── api_specs/      # OpenAPI 3.1 specifications
    └── openapi_3_1_specs/
        ├── master_spec.yaml
        ├── session_endpoints.yaml
        ├── turn_endpoints.yaml
        ├── stream_endpoints.yaml
        └── admin_endpoints.yaml
```

## Unified API Philosophy

### Design Principles

```yaml
design_principles:
  consistency:
    - Uniform error format (RFC 7807)
    - Standard authentication across all APIs
    - Consistent field naming (snake_case)
    - Predictable resource paths

  security:
    - HTTPS/WSS required (TLS 1.3)
    - JWT authentication with short expiry
    - Rate limiting per session
    - CORS configuration for web clients

  performance:
    - Connection pooling
    - HTTP/2 multiplexing for REST
    - WebSocket for low-latency bidirectional
    - SSE for server-push events

  observability:
    - Request ID in all responses
    - Structured logging for all requests
    - Prometheus metrics
    - OpenTelemetry tracing
```

## Authentication & Authorization

### JWT Token Format

```yaml
jwt_token:
  header:
    alg: RS256
    typ: JWT

  payload:
    sub: user-id-123
    session_id: session-abc
    iat: 1697234567 # Issued at
    exp: 1697238167 # Expires in 1 hour
    scopes: ["turn:create", "session:read", "stream:subscribe"]

  signature:
    algorithm: RSA-SHA256
    key_rotation: Every 7 days
```

### Authorization Scopes

```yaml
scopes:
  session_management:
    - session:create # Create new session
    - session:read # Read session details
    - session:update # Update session config
    - session:delete # Terminate session

  turn_execution:
    - turn:create # Submit user turn
    - turn:read # Read turn history
    - turn:cancel # Cancel in-progress turn

  streaming:
    - stream:subscribe # Subscribe to SSE stream
    - stream:read # Read streamed events

  admin:
    - admin:health # Health check endpoints
    - admin:metrics # Metrics endpoints
    - admin:config # Configuration endpoints
```

## Error Handling (RFC 7807)

### Standard Error Format

```json
{
  "type": "https://k1.example.com/errors/rate-limit-exceeded",
  "title": "Rate Limit Exceeded",
  "status": 429,
  "detail": "Session session-abc has exceeded 100 req/min limit",
  "instance": "/api/v1/sessions/session-abc/turns",
  "request_id": "req-xyz-789",
  "trace_id": "trace-abc-123",
  "timestamp": "2025-01-13T10:30:00Z",
  "retryable": true,
  "retry_after": 60
}
```

### Error Categories

```yaml
error_types:
  client_errors_4xx:
    - 400: Bad Request (validation failure)
    - 401: Unauthorized (missing/invalid token)
    - 403: Forbidden (insufficient scopes)
    - 404: Not Found (resource doesn't exist)
    - 409: Conflict (concurrent modification)
    - 422: Unprocessable Entity (semantic validation)
    - 429: Too Many Requests (rate limit)

  server_errors_5xx:
    - 500: Internal Server Error (unhandled exception)
    - 502: Bad Gateway (K0 bridge failure)
    - 503: Service Unavailable (circuit breaker open)
    - 504: Gateway Timeout (K0 timeout)
```

## Rate Limiting

```yaml
rate_limits:
  per_session:
    requests_per_minute: 100
    burst_capacity: 20

  per_ip:
    requests_per_minute: 500
    burst_capacity: 100

  per_user:
    sessions_per_day: 100
    turns_per_day: 10000

  headers:
    X-RateLimit-Limit: 100
    X-RateLimit-Remaining: 87
    X-RateLimit-Reset: 1697234620 # Unix timestamp
```

## API Versioning

```yaml
versioning_strategy:
  approach: URL-based versioning
  current_version: v1

  version_lifecycle:
    v1:
      status: ACTIVE
      released: 2025-01-01
      deprecation: None
      sunset: None

  backward_compatibility:
    - Minor version updates (v1.1, v1.2) are backward compatible
    - Major version updates (v2) may break compatibility
    - Deprecated endpoints supported for 6 months
    - Sunset date announced 3 months in advance
```

## Performance Targets

```yaml
performance_budgets:
  rest_api:
    p50_latency_ms: 100
    p95_latency_ms: 500
    p99_latency_ms: 1500
    throughput_req_per_sec: 1000

  websocket_api:
    connection_setup_ms: 200
    message_latency_ms: 50 # One-way
    max_concurrent_connections: 10000

  sse_api:
    connection_setup_ms: 150
    event_delivery_latency_ms: 100
    max_concurrent_connections: 5000
```

## CORS Configuration

```yaml
cors:
  allowed_origins:
    - https://app.example.com
    - https://*.example.com # Wildcard for subdomains

  allowed_methods:
    - GET
    - POST
    - PUT
    - DELETE
    - OPTIONS

  allowed_headers:
    - Authorization
    - Content-Type
    - X-Request-ID
    - X-Trace-ID

  exposed_headers:
    - X-RateLimit-Limit
    - X-RateLimit-Remaining
    - X-RateLimit-Reset
    - X-Request-ID

  credentials: true
  max_age: 3600 # Preflight cache duration (1 hour)
```

## Observability

### Metrics (Prometheus)

```yaml
metrics:
  request_metrics:
    - api_requests_total{method, path, status, api_type}
    - api_request_duration_ms{method, path, percentile, api_type}
    - api_request_size_bytes{method, path, percentile}
    - api_response_size_bytes{method, path, percentile}

  connection_metrics:
    - api_active_connections{api_type} # websocket, sse
    - api_connection_errors_total{api_type, error_type}

  rate_limit_metrics:
    - api_rate_limit_exceeded_total{session_id, ip}
    - api_rate_limit_remaining{session_id}

  authentication_metrics:
    - api_auth_failures_total{reason} # invalid_token, expired, etc.
    - api_auth_success_total
```

### Tracing (OpenTelemetry)

```yaml
tracing:
  trace_propagation:
    - W3C Trace Context standard
    - Inject trace_id into all K1 operations
    - Propagate to K0 bridge requests

  span_structure:
    - Span: "api.request"
      - Attributes: method, path, status, session_id
      - Child: "api.authentication"
      - Child: "api.authorization"
      - Child: "k1.turn_execution" (if applicable)
      - Child: "k0_bridge.request" (if applicable)
```

### Logging

```yaml
logging:
  access_logs:
    format: JSON structured logs
    fields:
      - timestamp
      - request_id
      - trace_id
      - method
      - path
      - status
      - latency_ms
      - user_agent
      - ip_address
      - session_id (if authenticated)

  error_logs:
    format: JSON structured logs
    fields:
      - timestamp
      - request_id
      - trace_id
      - error_type
      - error_message
      - stack_trace
      - session_id
```

## Security Considerations

```yaml
security:
  transport:
    - TLS 1.3 required (no downgrade)
    - Strong cipher suites only
    - HSTS header (max-age=31536000)

  authentication:
    - JWT with RS256 signing
    - Token expiry: 1 hour
    - Refresh token: 7 days
    - Revocation list checked

  input_validation:
    - Schema validation for all payloads
    - SQL injection prevention (parameterized queries)
    - XSS prevention (output encoding)
    - CSRF protection (SameSite cookies)

  rate_limiting:
    - Per-session limits (100 req/min)
    - Per-IP limits (500 req/min)
    - Burst capacity (20 requests)
    - Exponential backoff on 429

  audit_logging:
    - All authentication attempts
    - All authorization failures
    - All RED band operations
    - Session creation/termination
```

## Testing Strategies

```yaml
testing:
  unit_tests:
    - Request validation logic
    - Response serialization
    - Error formatting (RFC 7807)

  integration_tests:
    - End-to-end API workflows
    - Authentication/authorization
    - Rate limiting behavior
    - CORS preflight handling

  performance_tests:
    - Latency benchmarks (p50, p95, p99)
    - Throughput stress testing (1000 req/s)
    - WebSocket connection scaling (10K connections)
    - SSE event delivery latency

  security_tests:
    - OWASP Top 10 vulnerability scanning
    - JWT token validation
    - Rate limit bypass attempts
    - CORS misconfiguration tests
```

## API Gateway Features

```yaml
api_gateway:
  routing:
    - Path-based routing to K1 services
    - Load balancing across K1 instances
    - Health check integration

  middleware:
    - Authentication/authorization
    - Rate limiting
    - Request logging
    - CORS handling
    - Compression (gzip, br)

  caching:
    - Cache-Control headers
    - ETag support
    - Conditional requests (If-None-Match)

  monitoring:
    - Request metrics
    - Error tracking
    - Latency histograms
    - Alert integration
```

## Client SDKs (Future)

```yaml
planned_sdks:
  languages:
    - Python SDK (k1-sdk-python)
    - JavaScript/TypeScript SDK (k1-sdk-js)
    - Go SDK (k1-sdk-go)
    - Rust SDK (k1-sdk-rust)

  features:
    - Automatic authentication
    - Retry with exponential backoff
    - Rate limit handling
    - WebSocket reconnection
    - SSE event streaming
    - Type-safe API calls
```

## Related Contracts

- **REST API:** `./rest/README.md` - HTTP endpoint contracts
- **WebSocket API:** `./websocket/README.md` - Bidirectional streaming contracts
- **SSE API:** `./sse/README.md` - Server-push event contracts
- **OpenAPI Specs:** `./api_specs/README.md` - Complete OpenAPI 3.1 specifications
- **K0 SSE:** `../k0_sse/README.md` - K0 SSE event streaming
- **Bridge Integration:** `../bridge_integration/README.md` - SSE-WebSocket bridge
- **SessionState:** `../sessionstate/README.md` - Session state management

---

**Last Updated:** 2025-10-13

**API Version:** v1 (Active)
