# Error Recovery Contracts

**Source ADRs:** ADR-0017, ADR-0017a-d, ADR-0018

## Overview

This directory contains error recovery contracts, including circuit breakers, retry policies, saga patterns for distributed transactions, and graceful degradation strategies.

## Research Foundation

- **Circuit Breaker Pattern (Nygard):** Prevent cascading failures
- **Saga Pattern (Garcia-Molina 1987):** Distributed transaction management
- **Chaos Engineering (Netflix):** Resilience through controlled failures

## Contracts Included

### 1. Circuit Breaker Contract (`circuit_breaker.yaml`)
- **Source:** ADR-0017a
- State machine (CLOSED → OPEN → HALF_OPEN)
- Failure threshold and cooldown
- Integration with tool calls and K0 Bridge

### 2. Retry Policy Contract (`retry_policy.yaml`)
- **Source:** ADR-0017b
- Exponential backoff
- Idempotency checking
- Max retry limits

### 3. Saga Pattern Contract (`saga_pattern.yaml`)
- **Source:** ADR-0017c
- Compensating transactions
- Saga coordinator
- Rollback on failure

### 4. Graceful Degradation Contract (`graceful_degradation.yaml`)
- **Source:** ADR-0017d
- Degradation levels
- Fallback strategies
- Feature flags

### 5. Chaos Engineering Contract (`chaos_engineering.yaml`)
- **Source:** ADR-0018
- Fault injection scenarios
- Resilience testing
- Recovery validation

## Circuit Breaker Pattern

**Source:** ADR-0017a

```yaml
circuit_breaker:
  description: Prevent cascading failures by failing fast when service is unhealthy

  states:
    CLOSED:
      description: Normal operation, requests pass through
      transition_condition: failure_rate > threshold
      next_state: OPEN

    OPEN:
      description: Circuit tripped, fast-fail all requests
      transition_condition: cooldown_period elapsed
      next_state: HALF_OPEN
      failure_response:
        error: SERVICE_UNAVAILABLE
        message: "Circuit breaker is OPEN for {service}"
        retry_after_ms: cooldown_period_ms

    HALF_OPEN:
      description: Testing if service recovered
      transition_condition:
        - If test_requests succeed: → CLOSED
        - If test_requests fail: → OPEN
      test_requests: 3

  configuration:
    failure_threshold_percent: 50
    min_requests_before_trip: 10
    cooldown_period_ms: 30000
    test_requests_in_half_open: 3
    success_threshold_to_close: 3

  failure_detection:
    - HTTP 5xx errors
    - Timeouts
    - Connection errors
    - Specific application errors (configurable)

  success_criteria:
    - HTTP 2xx responses
    - Successful task completion
    - No timeout

  monitoring:
    metrics:
      - circuit_breaker_state{service}
      - circuit_breaker_transitions_total{service, from_state, to_state}
      - circuit_breaker_rejected_requests_total{service}

    alerts:
      - CircuitBreakerOpen: state == OPEN
      - CircuitBreakerFlapping: transitions > 5 in 5 minutes
```

### Circuit Breaker Integration Points

```yaml
integration_points:
  tool_calls:
    - Wrap all external tool invocations
    - Per-tool circuit breaker
    - Fast-fail if circuit OPEN

  k0_bridge:
    - Protect K0 ports (P01-P20)
    - Per-port circuit breaker
    - Fallback to local cache if OPEN

  external_apis:
    - HTTP clients
    - WebSocket connections
    - SSE streams

  internal_services:
    - Agent-to-agent communication
    - MCP Gateway
    - Model Hub
```

## Retry Policy

**Source:** ADR-0017b

```yaml
retry_policy:
  strategy: exponential_backoff_with_jitter

  default_configuration:
    max_attempts: 3
    initial_delay_ms: 100
    max_delay_ms: 5000
    backoff_multiplier: 2.0
    jitter_enabled: true
    jitter_range: [0.5, 1.5]

  retry_logic:
    formula: |
      base_delay = min(
        initial_delay * (multiplier ^ attempt),
        max_delay
      )

      if jitter_enabled:
        actual_delay = base_delay * random(jitter_range)
      else:
        actual_delay = base_delay

    example:
      attempt_1: 100ms * random(0.5, 1.5) = 50-150ms
      attempt_2: 200ms * random(0.5, 1.5) = 100-300ms
      attempt_3: 400ms * random(0.5, 1.5) = 200-600ms

  retry_conditions:
    always_retry:
      - Network timeouts
      - Connection errors
      - HTTP 429 (Rate Limit)
      - HTTP 503 (Service Unavailable)

    retry_if_idempotent:
      - HTTP 500 (Internal Server Error)
      - Execution errors
      - Transient failures

    never_retry:
      - HTTP 400 (Bad Request)
      - HTTP 401 (Unauthorized)
      - HTTP 403 (Forbidden)
      - HTTP 404 (Not Found)
      - Validation errors

  idempotency:
    enabled: true
    mechanism: idempotency_key
    key_format: "{operation}:{session_id}:{request_id}"
    ttl: 3600s (1 hour)

  circuit_breaker_integration:
    - Check circuit state before retry
    - If circuit OPEN: skip retry, fail fast
    - If circuit CLOSED: proceed with retry
```

## Saga Pattern

**Source:** ADR-0017c

```yaml
saga_pattern:
  description: Distributed transaction pattern with compensating transactions

  saga_structure:
    saga_id: string
    steps:
      - step_id: string
        action: forward_action
        compensation: compensating_action
        status: PENDING | EXECUTING | COMPLETED | FAILED | COMPENSATED
    status: IN_PROGRESS | COMPLETED | ROLLED_BACK | FAILED

  execution_flow:
    forward_phase:
      - Execute steps sequentially
      - Record completed steps
      - If step fails: trigger rollback

    rollback_phase:
      - Execute compensations in reverse order
      - Mark steps as COMPENSATED
      - Saga status: ROLLED_BACK

  example_saga:
    saga_id: "user_onboarding"
    steps:
      - step_id: "create_user"
        action: create_user_in_db()
        compensation: delete_user_from_db()

      - step_id: "send_welcome_email"
        action: send_email(user)
        compensation: send_cancellation_email(user)

      - step_id: "provision_resources"
        action: allocate_resources(user)
        compensation: deallocate_resources(user)

  compensation_rules:
    - Compensations must be idempotent
    - Compensation may not fully undo (e.g., email sent)
    - Log all compensation attempts
    - Alert if compensation fails

  timeout_handling:
    per_step_timeout_ms: 10000
    saga_total_timeout_ms: 60000

    on_timeout:
      - Mark step as FAILED
      - Trigger rollback
      - Alert: saga_timeout{saga_id, step_id}

  saga_coordinator:
    role: Orchestrate saga execution and rollback
    persistence: Store saga state in K0
    recovery: Resume saga after crash
```

## Graceful Degradation

**Source:** ADR-0017d

```yaml
graceful_degradation:
  description: Progressively reduce service quality under load

  degradation_levels:
    level_0_normal:
      description: Full functionality
      features:
        - All tools enabled
        - Full context retrieval
        - Comprehensive logging
        - Real-time streaming

    level_1_reduced_quality:
      description: Minor reductions
      changes:
        - Reduce context window (from 10 to 5 turns)
        - Cache more aggressively
        - Skip optional cognitive enhancements
        - Reduce logging verbosity

    level_2_degraded:
      description: Significant reductions
      changes:
        - Disable non-critical tools
        - Use stale cache (up to 1s)
        - Skip background tasks
        - Basic logging only

    level_3_minimal:
      description: Core functionality only
      changes:
        - Single agent only (no orchestration)
        - No tool calls
        - No context retrieval
        - Minimal logging
        - Direct LLM responses

    level_4_maintenance:
      description: Read-only or unavailable
      changes:
        - Reject all write operations
        - Return cached responses only
        - Or return HTTP 503 Service Unavailable

  degradation_triggers:
    cpu_usage:
      level_1: > 70%
      level_2: > 85%
      level_3: > 95%

    memory_usage:
      level_1: > 75%
      level_2: > 90%
      level_3: > 95%

    latency:
      level_1: p95 > budget * 1.5
      level_2: p95 > budget * 2.0
      level_3: p95 > budget * 3.0

    error_rate:
      level_1: > 2%
      level_2: > 5%
      level_3: > 10%

  recovery:
    auto_recovery: true
    hysteresis: 20% (prevent flapping)
    recovery_delay: 60s (wait before upgrading level)
```

## Chaos Engineering

**Source:** ADR-0018

```yaml
chaos_engineering:
  description: Proactively inject faults to test resilience

  fault_injection_scenarios:
    network_latency:
      description: Add random latency to requests
      configuration:
        min_delay_ms: 100
        max_delay_ms: 1000
        probability: 0.1

    packet_loss:
      description: Drop random network packets
      configuration:
        loss_rate: 0.05
        burst_duration_ms: 1000

    service_unavailable:
      description: Simulate service outages
      configuration:
        failure_rate: 0.1
        duration_ms: 5000

    resource_exhaustion:
      description: Simulate CPU/memory pressure
      configuration:
        cpu_throttle: 50%
        memory_limit_mb: 256

    partial_failure:
      description: Some requests succeed, others fail
      configuration:
        failure_rate: 0.3
        error_types: [timeout, 500_error, connection_error]

  chaos_testing_framework:
    tool: Chaos Mesh or custom
    target_environments:
      - Development: Always enabled (10% fault rate)
      - Staging: Scheduled chaos tests (weekly)
      - Production: GameDays only (with approval)

  resilience_validation:
    tests:
      - Circuit breaker trips appropriately
      - Retries succeed after transient failure
      - Saga rollback completes successfully
      - Graceful degradation activates
      - System recovers within 30s

    success_criteria:
      - No cascading failures
      - Error rate < 1% during chaos
      - Latency degrades gracefully
      - No data loss
      - All alerts fire correctly
```

## Error Budget Policy

```yaml
error_budget_policy:
  monthly_error_budget: 43 minutes (99.9% SLO)

  budget_tracking:
    - Calculate remaining budget daily
    - Alert if budget < 50% remaining
    - Freeze releases if budget < 20%
    - Stop chaos tests if budget < 10%

  policy_enforcement:
    - If budget exhausted: freeze all risky changes
    - Focus on reliability improvements
    - Increase testing and monitoring
    - Resume normal operations when budget recovers
```

## Observability

```yaml
observability:
  metrics:
    - circuit_breaker_state{service}
    - retry_attempts_total{service, outcome}
    - saga_execution_total{saga_type, outcome}
    - degradation_level{service}
    - chaos_fault_injection_total{fault_type}

  alerts:
    - CircuitBreakerOpen: state == OPEN
    - RetryExhausted: max_attempts exceeded
    - SagaRollback: saga rolled back
    - DegradationActivated: level > 0
    - ChaosTestFailed: resilience test failed
```

## Related Contracts

- Tools: `../tools/retry_policy.yaml`
- Performance: `../performance/backpressure_cascade.yaml`
- Observability: `../observability/`

---

**Last Updated:** 2025-10-13
