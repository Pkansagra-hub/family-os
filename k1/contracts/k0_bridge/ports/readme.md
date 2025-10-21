# K0 Bridge Ports Contracts

**Source ADRs:** ADR-0001a, ADR-0001e

## Overview

This directory contains contracts for all 20 K0 Bridge ports (P01-P20) that enable communication between K1 (intelligence kernel) and K0 (memory kernel).

## K0 Bridge Architecture

The K0 Bridge provides a type-safe, high-performance interface for K1 to access K0's memory stores using 20 specialized ports.

## Port Categories

### Memory Operations (P01-P04)
- **P01: Recall Query** - Multi-store retrieval with fusion
- **P02: Persist** - Write data to K0
- **P03: Forget** - Delete data from K0
- **P04: Compact** - Trigger K0 compaction

### Context Management (P05-P07)
- **P05: Context Window** - Manage conversation context
- **P06: Context Summarize** - Generate context summaries
- **P07: Context Prune** - Remove old context

### Configuration (P08-P09)
- **P08: Config Read** - Read K0 configuration
- **P09: Config Write** - Update K0 configuration

### Analytics (P10-P12)
- **P10: Analytics Query** - Query analytics data
- **P11: Analytics Aggregate** - Aggregate metrics
- **P12: Policy Evaluate** - Evaluate retention policies

### Observability (P13-P15)
- **P13: Metrics Export** - Export K0 metrics
- **P14: Health Check** - K0 health status
- **P15: Diagnostics** - K0 diagnostic info

### Advanced Operations (P16-P20)
- **P16: Batch Operations** - Batch multiple operations
- **P17: Transaction Begin/Commit** - Transaction support
- **P18: Snapshot Create/Restore** - Snapshot operations
- **P19: Replication** - Cross-device replication
- **P20: Schema Migration** - Schema evolution

## Port Contract Template

Each port contract includes:

```yaml
port_contract:
  port_number: Pxx
  port_name: PortName
  operation: OperationType

  request_schema:
    format: FlatBuffers
    schema_file: Pxx_Request.fbs
    fields: [...]

  response_schema:
    format: FlatBuffers
    schema_file: Pxx_Response.fbs
    fields: [...]

  performance:
    latency_p95_ms: target
    timeout_ms: maximum

  semantics:
    idempotent: true/false
    side_effects: description

  error_handling:
    error_types: [...]
    retry_policy: [...]
```

## Port P01: Recall Query

**The most critical port for K1 operations**

```yaml
port_p01_recall_query:
  description: Multi-store retrieval with cognitive enhancements

  request:
    query: string
    filters:
      session_id: string | null
      timestamp_range: [start, end] | null
      tags: [string] | null
      privacy_band: GREEN | AMBER | RED | null

    retrieval_config:
      stores: [fts, vector, kg]
      max_results_per_store: 10
      fusion_algorithm: mmr | reciprocal_rank_fusion
      diversity_lambda: 0.5

    cognitive_enhancements:
      apply_recency_bias: boolean
      apply_affect_weighting: boolean
      apply_confidence_filtering: boolean

    trace_id: string

  response:
    results:
      - content: string
        score: float
        source_store: fts | vector | kg
        metadata: object

    fusion_metadata:
      stores_queried: [string]
      total_candidates: integer
      fusion_algorithm_used: string

    latency_ms: integer
    trace_id: string

  performance:
    latency_p95_ms: 100
    timeout_ms: 500

  idempotent: true
  side_effects: none
```

## Port P02: Persist

```yaml
port_p02_persist:
  description: Write data to K0 stores

  request:
    session_id: string
    content: string
    metadata:
      timestamp: int64
      tags: [string]
      privacy_band: GREEN | AMBER | RED
      author: user | agent

    indexing_options:
      fts: boolean
      vector: boolean
      kg: boolean

    trace_id: string

  response:
    receipt_id: string
    indexed_stores: [string]
    latency_ms: integer
    trace_id: string

  performance:
    latency_p95_ms: 250
    timeout_ms: 1000

  idempotent: false (use idempotency_key for safety)
  side_effects: Writes to K0, triggers indexing
```

## Port P08: Config Read

```yaml
port_p08_config_read:
  description: Read K0 configuration

  request:
    config_keys: [string]  # Empty for all configs
    trace_id: string

  response:
    configs: {key: value}
    version: string
    trace_id: string

  performance:
    latency_p95_ms: 10
    timeout_ms: 100

  idempotent: true
  side_effects: none
```

## Port P16: Batch Operations

```yaml
port_p16_batch:
  description: Execute multiple operations in a batch

  request:
    operations:
      - port: Pxx
        payload: [ubyte]  # FlatBuffers encoded request

    atomic: boolean  # All succeed or all fail
    trace_id: string

  response:
    results:
      - success: boolean
        response: [ubyte] | null
        error: string | null

    batch_latency_ms: integer
    trace_id: string

  performance:
    latency_p95_ms: 500
    timeout_ms: 2000

  idempotent: depends on operations
  side_effects: depends on operations
```

## Performance Characteristics

```yaml
port_performance:
  read_operations: [P01, P05, P08, P10, P14]
    latency_p95_ms: 100

  write_operations: [P02, P09, P17]
    latency_p95_ms: 250

  heavy_operations: [P06, P11, P18, P19, P20]
    latency_p95_ms: 1000
```

## Router Policy (Fast/Smart Lane)

**Source:** ADR-0049

```yaml
router_policy:
  fast_lane:
    target_latency_ms: 50
    ports: [P08, P14]  # Simple reads

  smart_lane:
    target_latency_ms: 200
    ports: [P01, P02, P06, P11]  # Complex operations
```

## Error Handling

```yaml
error_handling:
  common_errors:
    - K0_UNAVAILABLE: K0 service down
    - TIMEOUT: Operation exceeded timeout
    - INVALID_REQUEST: Request validation failed
    - PERMISSION_DENIED: Privacy band violation
    - RATE_LIMIT_EXCEEDED: Too many requests

  retry_policy:
    - K0_UNAVAILABLE: Retry with exponential backoff
    - TIMEOUT: Retry once with increased timeout
    - INVALID_REQUEST: No retry
    - PERMISSION_DENIED: No retry
    - RATE_LIMIT_EXCEEDED: Retry after delay
```

## FlatBuffers Schemas

All port contracts are defined using FlatBuffers for performance:

```
ports/
├── P01_RecallQuery.fbs
├── P02_Persist.fbs
├── P03_Forget.fbs
├── ...
└── P20_SchemaMigration.fbs
```

## Usage Example

```python
from k1.k0_bridge import K0Bridge, Port

bridge = K0Bridge()

# P01: Recall Query
result = await bridge.call(
    port=Port.P01_RECALL_QUERY,
    request=RecallQueryRequest(
        query="quantum computing",
        retrieval_config=RetrievalConfig(
            stores=[Store.FTS, Store.VECTOR],
            fusion_algorithm=FusionAlgorithm.MMR
        )
    )
)
```

## Related Contracts

- Storage: `../../storage/`
- Router Policies: `../../router_policies/`
- Performance: `../../performance/`

---

**Last Updated:** 2025-10-13
