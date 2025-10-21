# Router Policy Contracts

**Source ADR:** ADR-0049

## Overview

This directory contains contracts for K0 Bridge router policies, specifically the Fast/Smart lane selection algorithm that optimizes request routing based on complexity and performance requirements.

## Contracts Included

### 1. Fast/Smart Lane Router Policy (`fast_smart_lane.yaml`)
- Lane selection criteria
- Scoring algorithm
- Lane switching thresholds
- Performance optimization rules

### 2. Lane Scoring Algorithm (`lane_scoring.yaml`)
- Complexity scoring factors
- Performance scoring factors
- Combined score calculation
- Threshold definitions

### 3. Lane Performance Targets (`lane_performance.yaml`)
- Fast lane performance targets (<50ms)
- Smart lane performance targets (<200ms)
- SLO definitions per lane
- Monitoring and alerting thresholds

## Key Specifications

### Lane Selection Policy

**Fast Lane Criteria:**
- Simple queries (key-value lookups)
- Small payload size (<4KB)
- No complex processing required
- Target latency: <50ms P95

**Smart Lane Criteria:**
- Complex queries (multi-store retrieval, fusion)
- Large payload size (>4KB)
- Cognitive enhancements required
- Target latency: <200ms P95

### Scoring Algorithm

```yaml
scoring:
  complexity_factors:
    query_type:
      simple_lookup: 0        # Key-value, single-store
      multi_store: 5          # Multiple stores (FTS + Vector + KG)
      fusion: 8               # Result fusion and ranking
      cognitive: 10           # Cognitive enhancements (bias, affect)

    payload_size:
      small_kb: 0             # <4KB
      medium_kb: 3            # 4-16KB
      large_kb: 7             # 16-64KB
      xlarge_kb: 10           # >64KB

    operations:
      read_only: 0            # Simple reads
      write: 3                # Writes to memory
      batch: 5                # Batch operations
      transaction: 8          # Multi-step transactions

  performance_factors:
    latency_sensitivity:
      critical: 10            # TTFT critical path
      interactive: 5          # User-facing operation
      background: 0           # Background task

    priority:
      urgent: 10              # Highest priority
      high: 7                 # High priority
      normal: 3               # Normal priority
      low: 0                  # Low priority

  threshold:
    fast_lane_max_score: 5    # Route to Fast Lane if score ≤ 5
    smart_lane_min_score: 6   # Route to Smart Lane if score ≥ 6
```

### Lane Routing Decision

```yaml
routing_decision:
  input:
    - query_complexity_score
    - payload_size_score
    - operation_complexity_score
    - latency_sensitivity_score
    - priority_score

  calculation:
    total_score = (
      query_complexity_score * 0.3 +
      payload_size_score * 0.2 +
      operation_complexity_score * 0.2 +
      latency_sensitivity_score * 0.2 +
      priority_score * 0.1
    )

  decision:
    - if total_score <= 5: route_to_fast_lane()
    - if total_score >= 6: route_to_smart_lane()
```

### Performance Targets

```yaml
performance_targets:
  fast_lane:
    p50_latency_ms: 20
    p95_latency_ms: 50
    p99_latency_ms: 100
    throughput_qps: 5000
    use_cases:
      - Simple K0 writes (P02)
      - Key-value reads (P01 simple)
      - Config reads (P08)

  smart_lane:
    p50_latency_ms: 80
    p95_latency_ms: 200
    p99_latency_ms: 500
    throughput_qps: 1000
    use_cases:
      - Multi-store retrieval (P01 complex)
      - Fusion queries (P01 with MMR)
      - Cognitive enhancements (P01 with bias)
      - Policy evaluation (P12)
```

## Usage Examples

### Request Routing

```python
# Evaluate request for lane selection
request = K0Request(
    port="P01",
    operation="RecallQuery",
    query_type="multi_store_fusion",
    payload_size_kb=8,
    latency_sensitivity="interactive",
    priority="high"
)

# Calculate lane score
score = lane_scorer.calculate_score(request)
# score = 5*0.3 + 3*0.2 + 0*0.2 + 5*0.2 + 7*0.1 = 4.0

# Route decision
if score <= 5:
    lane = "fast"      # Fast lane
else:
    lane = "smart"     # Smart lane

# Route request
response = await k0_bridge.route(request, lane=lane)
```

### Lane Switching Example

```python
# Dynamic lane switching based on load
if fast_lane_utilization > 0.8:
    # Fast lane overloaded, temporarily route to smart lane
    route_threshold = 3  # Lower threshold
else:
    route_threshold = 5  # Normal threshold
```

## Monitoring & Observability

```yaml
metrics:
  - lane_routing_decisions_total{lane="fast|smart"}
  - lane_latency_ms{lane="fast|smart", percentile="p50|p95|p99"}
  - lane_utilization{lane="fast|smart"}
  - lane_score_distribution{lane="fast|smart"}
  - lane_switches_total{from="fast|smart", to="fast|smart"}

alerts:
  - FastLaneLatencyHigh: p95 > 50ms for 5 min
  - SmartLaneLatencyHigh: p95 > 200ms for 5 min
  - FastLaneUtilizationHigh: utilization > 80% for 5 min
```

## Related Contracts

- K0 Bridge Contracts: `../k0_bridge/`
- Performance Contracts: `../performance/performance_budgets.yaml`
- Observability Contracts: `../observability/`

---

**Last Updated:** 2025-10-13
