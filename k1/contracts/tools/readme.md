# Tool Contracts

**Source ADRs:** ADR-0009, ADR-0009a-d

## Overview

This directory contains contracts for K1's Tool System, which enables agents to invoke external tools (MCP servers, APIs, internal services) with type safety, timeout enforcement, and retry policies.

## Research Foundation

- **Function Calling (OpenAI):** LLM-driven tool invocation
- **Model Context Protocol (Anthropic):** Standardized tool interface
- **Idempotency:** Safe retry semantics

## Contracts Included

### 1. Tool Schema Contract (`tool_schema.yaml`)
- **Source:** ADR-0009a
- Tool definition format (name, description, parameters, returns)
- JSON Schema for parameters
- MCP integration

### 2. Tool Invocation Contract (`tool_invocation.yaml`)
- **Source:** ADR-0009b
- Invocation request/response format
- Timeout enforcement (3000ms default)
- Error handling

### 3. Tool Registry Contract (`tool_registry.yaml`)
- **Source:** ADR-0009c
- Tool discovery and registration
- Capability requirements per tool
- Tool versioning

### 4. Retry Policy Contract (`retry_policy.yaml`)
- **Source:** ADR-0009d
- Exponential backoff strategy
- Idempotency checking
- Circuit breaker integration

## Tool Schema Format

**Source:** ADR-0009a

```yaml
tool_schema:
  tool_id: string              # Unique tool identifier
  name: string                 # Human-readable name
  description: string          # What the tool does
  version: string              # Semantic version (e.g., "1.2.0")

  parameters:
    type: object
    properties:
      param_name:
        type: string | integer | boolean | array | object
        description: string
        required: boolean
        default: any | null
    required: [string]

  returns:
    type: object
    properties:
      result_field:
        type: string | integer | boolean | array | object
        description: string

  metadata:
    required_capabilities: [Capability]
    timeout_ms: integer
    idempotent: boolean
    privacy_band: GREEN | AMBER | RED
    cost_estimate: float
    rate_limit: integer

  examples:
    - name: string
      parameters: object
      expected_result: object
```

### Example Tool Schema

```yaml
tool_schema:
  tool_id: "web_search_v1"
  name: "Web Search"
  description: "Search the web for information"
  version: "1.0.0"

  parameters:
    type: object
    properties:
      query:
        type: string
        description: "Search query"
        required: true
      max_results:
        type: integer
        description: "Maximum number of results"
        required: false
        default: 10
    required: ["query"]

  returns:
    type: object
    properties:
      results:
        type: array
        items:
          type: object
          properties:
            title: {type: string}
            url: {type: string}
            snippet: {type: string}

  metadata:
    required_capabilities: [TOOL_CALL]
    timeout_ms: 3000
    idempotent: true
    privacy_band: AMBER
    cost_estimate: 0.05
    rate_limit: 100
```

## Tool Invocation Protocol

**Source:** ADR-0009b

```yaml
tool_invocation:
  request:
    tool_id: string
    parameters: object
    trace_id: string
    timeout_ms: integer
    retry_policy: RetryPolicy | null
    idempotency_key: string | null

  response:
    success: boolean
    result: object | null
    error: ToolError | null
    duration_ms: integer
    trace_id: string

  error_types:
    TIMEOUT:
      description: Tool execution exceeded timeout
      retryable: true
      http_equivalent: 504

    INVALID_PARAMETERS:
      description: Parameters failed validation
      retryable: false
      http_equivalent: 400

    PERMISSION_DENIED:
      description: Missing required capabilities
      retryable: false
      http_equivalent: 403

    TOOL_NOT_FOUND:
      description: Tool does not exist
      retryable: false
      http_equivalent: 404

    TOOL_UNAVAILABLE:
      description: Tool service is down
      retryable: true
      http_equivalent: 503

    EXECUTION_ERROR:
      description: Tool execution failed
      retryable: depends_on_idempotency
      http_equivalent: 500
```

### Tool Call Flow

```yaml
tool_call_flow:
  step1_validate_parameters:
    description: Validate parameters against tool schema
    validator: JSON Schema validator
    failure_action: Return INVALID_PARAMETERS error

  step2_check_capabilities:
    description: Verify agent has required capabilities
    required: tool.metadata.required_capabilities
    failure_action: Return PERMISSION_DENIED error

  step3_check_privacy_band:
    description: Check privacy band compliance
    if tool.metadata.privacy_band == RED:
      require: arbiter_approval
    failure_action: Return PERMISSION_DENIED error

  step4_invoke_tool:
    description: Invoke tool via MCP Gateway or direct call
    timeout: tool.metadata.timeout_ms or 3000ms
    failure_action: Return TIMEOUT or EXECUTION_ERROR

  step5_validate_response:
    description: Validate response against returns schema
    validator: JSON Schema validator
    failure_action: Log warning, return partial result

  step6_log_invocation:
    description: Log tool call for audit trail
    log_level: INFO
    privacy_band: tool.metadata.privacy_band
```

## Tool Registry

**Source:** ADR-0009c

```yaml
tool_registry:
  storage: In-memory registry with K0 persistence

  operations:
    register:
      description: Register new tool or update existing
      validation:
        - Tool schema is valid
        - Tool ID is unique (or version increment)
        - Required capabilities exist

    discover:
      description: List all available tools
      filters:
        - by_capability: [Capability]
        - by_privacy_band: GREEN | AMBER | RED
        - by_name: string (search)

    get:
      description: Get tool schema by ID
      cache: true
      cache_ttl: 3600s

    unregister:
      description: Remove tool from registry
      validation:
        - No active invocations
        - Admin capability required

  versioning:
    strategy: semantic_versioning
    format: "v{major}.{minor}.{patch}"

    compatibility:
      major_change: Breaking API change
      minor_change: Backward-compatible new feature
      patch_change: Backward-compatible bug fix

    deprecation:
      notice_period: 90 days
      warning: Log warning on deprecated tool use
      sunset: Remove tool after notice period
```

## Retry Policy

**Source:** ADR-0009d

```yaml
retry_policy:
  strategy: exponential_backoff

  default_policy:
    max_attempts: 3
    initial_delay_ms: 100
    max_delay_ms: 5000
    backoff_multiplier: 2
    jitter: true

  retry_conditions:
    - error_type in [TIMEOUT, TOOL_UNAVAILABLE]
    - tool.metadata.idempotent == true
    - attempts < max_attempts

  no_retry_conditions:
    - error_type in [INVALID_PARAMETERS, PERMISSION_DENIED, TOOL_NOT_FOUND]
    - tool.metadata.idempotent == false and error_type == EXECUTION_ERROR

  exponential_backoff:
    formula: |
      delay = min(
        initial_delay * (backoff_multiplier ^ attempt),
        max_delay
      )
      if jitter:
        delay = delay * random(0.5, 1.5)

  idempotency_checking:
    if tool.metadata.idempotent:
      - Use idempotency_key in request
      - Server deduplicates based on key
      - Safe to retry on EXECUTION_ERROR
    else:
      - Do not retry EXECUTION_ERROR
      - Risk of duplicate operations
```

### Circuit Breaker Integration

```yaml
circuit_breaker:
  description: Prevent cascading failures from unhealthy tools

  states:
    CLOSED:
      description: Normal operation
      transition: To OPEN if failure_rate > threshold

    OPEN:
      description: Tool unavailable, fast-fail
      transition: To HALF_OPEN after cooldown_period

    HALF_OPEN:
      description: Testing if tool recovered
      transition: To CLOSED if test succeeds, to OPEN if fails

  configuration:
    failure_threshold: 50%
    min_requests: 10
    cooldown_period_ms: 30000
    test_requests: 3

  failure_response:
    error: TOOL_UNAVAILABLE
    message: "Circuit breaker is OPEN for tool {tool_id}"
    retry_after_ms: cooldown_period_ms
```

## MCP Integration

```yaml
mcp_integration:
  protocol: Model Context Protocol (Anthropic)

  mcp_server_connection:
    transport: stdio | http | websocket
    startup: lazy_initialization
    health_check: periodic_ping (every 30s)

  mcp_tool_discovery:
    - Connect to MCP server
    - Call list_tools RPC
    - Parse tool schemas
    - Register tools in ToolRegistry

  mcp_tool_invocation:
    - Map K1 tool call to MCP format
    - Send call_tool RPC
    - Parse MCP response
    - Map back to K1 format

  error_mapping:
    mcp_error: K1_error
    timeout: TIMEOUT
    invalid_params: INVALID_PARAMETERS
    not_found: TOOL_NOT_FOUND
    server_error: EXECUTION_ERROR
```

## Performance Requirements

```yaml
performance:
  tool_call_latency_p95_ms: 3000
  tool_schema_validation_ms: 5
  tool_registry_lookup_ms: 1
  retry_overhead_ms: <10
```

## Observability

```yaml
observability:
  events:
    - tool_called{tool_id, agent_id}
    - tool_completed{tool_id, duration_ms, outcome}
    - tool_failed{tool_id, error_type}
    - tool_retry_attempted{tool_id, attempt}
    - circuit_breaker_state_changed{tool_id, state}

  metrics:
    - tool_invocation_total{tool_id, outcome}
    - tool_duration_ms{tool_id, percentile}
    - tool_error_total{tool_id, error_type}
    - tool_retry_total{tool_id}
    - circuit_breaker_state{tool_id}

  alerts:
    - ToolLatencyHigh: p95 > 3000ms for 5 min
    - ToolErrorRateHigh: error_rate > 10% for 5 min
    - CircuitBreakerOpen: state == OPEN
```

## Testing Strategies

```yaml
tool_tests:
  unit_tests:
    - Schema validation
    - Parameter parsing
    - Error handling
    - Retry logic

  integration_tests:
    - End-to-end tool invocation
    - MCP server integration
    - Circuit breaker behavior
    - Timeout enforcement

  chaos_tests:
    - Tool unavailability
    - Network latency
    - Intermittent failures
```

## Usage Examples

```python
# Register tool
tool_registry.register(ToolSchema(
    tool_id="web_search_v1",
    name="Web Search",
    description="Search the web",
    parameters={"query": {"type": "string", "required": True}},
    metadata={"timeout_ms": 3000, "idempotent": True}
))

# Invoke tool
result = await tool_runner.invoke(
    tool_id="web_search_v1",
    parameters={"query": "quantum computing"},
    trace_id="trace-123",
    retry_policy=RetryPolicy(max_attempts=3)
)
```

## Related Contracts

- Agent Lifecycle: `../agent_lifecycle/`
- Security: `../security/capabilities.yaml`
- Error Recovery: `../error_recovery/circuit_breaker.yaml`

---

**Last Updated:** 2025-10-13
