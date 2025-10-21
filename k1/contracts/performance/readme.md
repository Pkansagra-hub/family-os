# Performance Contracts

**Source ADRs:** ADR-0013, ADR-0013a-d, ADR-0014, ADR-0015

## Overview

This directory contains performance contracts, including latency budgets, thermal management, KV cache optimization, and backpressure cascade policies.

## Contracts Included

### 1. Performance Budgets Contract (`performance_budgets.yaml`)
- **Source:** ADR-0013a
- TTFT (Time to First Token): <150ms P95
- E2E Turn Latency: <2000ms P95
- Component-level budgets

### 2. KV Cache Contract (`kv_cache.yaml`)
- **Source:** ADR-0014
- Cache architecture and eviction
- Thermal placement (NPU/GPU/CPU/Remote)
- Memory budget: 128MB total

### 3. Thermal Management Contract (`thermal_management.yaml`)
- **Source:** ADR-0014
- Execution placement decisions
- Thermal states and throttling
- Migration policies

### 4. Backpressure Cascade Contract (`backpressure_cascade.yaml`)
- **Source:** ADR-0015
- Backpressure detection thresholds
- Propagation strategy
- Graceful degradation

## Performance Budgets

**Source:** ADR-0013a

```yaml
performance_budgets:
  critical_path_metrics:
    ttft_p95_ms:
      description: Time to First Token (streaming response start)
      budget: 150
      current: 140
      status: PASSING
      components:
        intent_classification: 50
        orchestration_3phase: 250
        agent_warmup: 200
        plan_generation: 800
        k0_recall: 100
        first_token_generation: 50

    e2e_turn_latency_p95_ms:
      description: End-to-end turn completion
      budget: 2000
      current: 1850
      status: PASSING
      components:
        ttft: 150
        token_generation: 1500
        k0_write: 250
        sessionstate_update: 100

  component_budgets:
    intent_classification_p95_ms: 50
    orchestration_3phase_p95_ms: 250
    agent_warmup_p95_ms: 200
    plan_generation_p95_ms: 800
    plan_validation_p95_ms: 200
    tool_call_p95_ms: 3000
    k0_recall_p95_ms: 100
    k0_write_p95_ms: 250
    sessionstate_read_p95_ms: 10
    sessionstate_write_p95_ms: 250
    config_reload_p95_ms: 100
    barge_in_latency_p95_ms: 120

memory_budgets:
  k1_total_memory_mb: 500
  sessionstate_per_session_kb: 64
  kv_cache_total_mb: 128
  agent_memory_per_agent_kb: 500
  max_concurrent_sessions: 100
  max_agents_per_session: 3

throughput_targets:
  requests_per_second: 50
  concurrent_sessions: 100
  tokens_per_second: 100
```

### Budget Enforcement

```yaml
budget_enforcement:
  monitoring:
    - Track P95 latency per component
    - Alert if budget exceeded for 5 minutes
    - Dashboard showing budget vs actual

  breach_handling:
    - Log budget breach
    - Increment breach counter
    - If breaches > threshold: trigger investigation
    - Automatic performance regression detection

  continuous_profiling:
    - py-spy for CPU profiling
    - memory_profiler for memory tracking
    - OpenTelemetry distributed tracing
    - Flame graphs for hot path analysis
```

## KV Cache Management

**Source:** ADR-0014

```yaml
kv_cache:
  description: Key-Value cache for LLM inference acceleration

  architecture:
    total_memory_mb: 128
    cache_granularity: per_turn
    eviction_policy: LRU

  cache_structure:
    key: |
      hash(prompt_prefix + context_summary)
    value: |
      {
        kv_tensors: [Tensor],
        metadata: {
          session_id: string,
          turn_id: integer,
          created_at: timestamp,
          size_mb: float,
          hit_count: integer
        }
      }

  thermal_placement:
    NPU:
      description: On-device neural processor
      capacity_mb: 32
      latency_ms: 1
      power: LOW
      use_case: Active session KV cache

    GPU:
      description: Discrete or integrated GPU
      capacity_mb: 64
      latency_ms: 5
      power: MEDIUM
      use_case: Recent sessions KV cache

    CPU:
      description: System RAM
      capacity_mb: 32
      latency_ms: 10
      power: LOW
      use_case: Cold KV cache, background sessions

    Remote:
      description: Cloud or edge server
      capacity: unlimited
      latency_ms: 50
      power: ZERO (offloaded)
      use_case: Archived KV cache

  eviction_algorithm:
    trigger: memory_usage > 80%

    scoring:
      factors:
        - recency: (now - last_access) (higher = more evictable)
        - frequency: hit_count (higher = less evictable)
        - size: size_mb (larger = more evictable if low hits)

      formula: |
        eviction_score = (
          (now - last_access) * 0.4 +
          (1.0 / hit_count) * 0.3 +
          (size_mb / max_size) * 0.3
        )

    eviction_target: Highest eviction_score
    eviction_quantity: Free 20% of capacity

  hit_rate_target: 75%
```

## Thermal Management

**Source:** ADR-0014

```yaml
thermal_management:
  description: Manage execution placement based on thermal state

  thermal_states:
    COOL:
      temperature_range: [0, 60] celsius
      throttling: none
      placement_preference: [NPU, GPU, CPU]
      max_power: 100%

    WARM:
      temperature_range: [60, 75] celsius
      throttling: light
      placement_preference: [GPU, CPU, Remote]
      max_power: 80%

    HOT:
      temperature_range: [75, 85] celsius
      throttling: moderate
      placement_preference: [CPU, Remote]
      max_power: 60%

    CRITICAL:
      temperature_range: [85, 100] celsius
      throttling: aggressive
      placement_preference: [Remote]
      max_power: 40%
      alert: thermal_critical

  placement_decisions:
    inference:
      COOL: NPU or GPU
      WARM: GPU or CPU
      HOT: CPU or Remote
      CRITICAL: Remote only

    kv_cache:
      COOL: NPU
      WARM: GPU
      HOT: CPU
      CRITICAL: Remote

    background_tasks:
      COOL: CPU
      WARM: CPU (throttled)
      HOT: Remote
      CRITICAL: Remote

  migration_policies:
    trigger:
      - Temperature threshold exceeded
      - Power budget exceeded
      - Performance degradation detected

    migration_latency_target_ms: 100

    migration_steps:
      1. Identify workload to migrate
      2. Select target device (cooler tier)
      3. Transfer state (KV cache, model weights)
      4. Switch execution to target
      5. Release source resources
```

## Backpressure Cascade

**Source:** ADR-0015

```yaml
backpressure_cascade:
  description: Propagate backpressure signals upstream to prevent overload

  detection_thresholds:
    queue_size:
      warning: 80%
      critical: 95%

    latency:
      warning: budget * 1.5
      critical: budget * 2.0

    memory:
      warning: 80%
      critical: 95%

    thermal:
      warning: HOT state
      critical: CRITICAL state

  propagation_strategy:
    layer5_infrastructure:
      detect: API Gateway queue size > 80%
      signal: HTTP 429 (Too Many Requests) to clients
      action: Apply rate limiting

    layer4_ingress:
      detect: WebSocket buffer > 80%
      signal: Backpressure to API Gateway
      action: Slow down message acceptance

    layer3_execution:
      detect: Tool Runner queue > 80%
      signal: Backpressure to Orchestrator
      action: Delay task assignment

    layer2_state:
      detect: K0 write queue > 80%
      signal: Backpressure to SessionState
      action: Apply batching, delay flush

    layer1_kernel:
      detect: Orchestrator queue > 80%
      signal: Backpressure to API Gateway
      action: Reject new sessions

  graceful_degradation:
    level1_reduce_quality:
      - Reduce streaming chunk size
      - Skip non-critical context retrieval
      - Use cached results when available

    level2_shed_load:
      - Drop background tasks
      - Cancel low-priority operations
      - Queue non-urgent requests

    level3_reject_requests:
      - Return HTTP 503 (Service Unavailable)
      - Provide retry-after header
      - Alert operations team
```

## Performance Testing

```yaml
performance_testing:
  load_testing:
    tool: Locust or k6
    scenarios:
      - Normal load: 50 req/s for 10 min
      - Peak load: 100 req/s for 5 min
      - Stress test: 200 req/s until failure

    success_criteria:
      - P95 latency within budget
      - Error rate < 1%
      - No memory leaks

  chaos_testing:
    scenarios:
      - Random pod restarts
      - Network latency injection
      - CPU throttling
      - Memory pressure

    success_criteria:
      - Graceful degradation
      - No cascading failures
      - Recovery within 30s

  profiling:
    cpu:
      - py-spy for Python profiling
      - Flame graphs for hot path analysis
      - Sample rate: 100Hz

    memory:
      - memory_profiler for memory tracking
      - Heap snapshots for leak detection
      - Track allocations > 1MB
```

## Observability

```yaml
observability:
  metrics:
    - request_latency_ms{component, percentile}
    - memory_usage_bytes{component}
    - kv_cache_hit_rate
    - kv_cache_size_mb{device}
    - thermal_state{device}
    - backpressure_active{layer}
    - budget_breach_total{component}

  alerts:
    - LatencyBudgetExceeded: p95 > budget for 5 min
    - MemoryUsageHigh: usage > 80%
    - KVCacheHitRateLow: hit_rate < 60%
    - ThermalCritical: state == CRITICAL
    - BackpressureActive: backpressure detected
```

## Related Contracts

- SessionState: `../sessionstate/`
- Orchestration: `../orchestration/`
- Error Recovery: `../error_recovery/`

---

**Last Updated:** 2025-10-13
