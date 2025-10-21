# SessionState Coherence Contracts

**Source ADR:** ADR-0050

## Overview

This directory contains contracts for SessionState coherence guarantees, ensuring consistent behavior across distributed K1 components and K0 storage.

## Contracts Included

### 1. Read-Your-Writes Consistency (`read_your_writes.yaml`)
- Guarantee that reads reflect preceding writes from same session
- Implementation strategy
- Timeout and fallback rules

### 2. Monotonic Reads Consistency (`monotonic_reads.yaml`)
- Guarantee that successive reads never return older data
- Versioning strategy
- Cache coherence rules

### 3. Monotonic Writes Consistency (`monotonic_writes.yaml`)
- Guarantee that writes are applied in order
- Write ordering enforcement
- Conflict resolution

### 4. Bounded Staleness Contract (`bounded_staleness.yaml`)
- Maximum staleness guarantees (<250ms)
- Freshness requirements per operation type
- Stale read handling

## Key Specifications

### Read-Your-Writes (RYW)

**Guarantee:** A session that writes data will immediately see that data in subsequent reads.

```yaml
read_your_writes:
  scope: per_session
  guarantee: |
    If session S writes value V to key K at time T1,
    then any read of K by session S at time T2 > T1
    will return V or a newer value.

  implementation:
    - Use session-local cache for immediate reads
    - Tag writes with session_id + write_seqno
    - Track latest write_seqno per session
    - Read from cache if write_seqno >= last_write

  timeout:
    max_propagation_delay_ms: 250  # K0 batch flush interval
    fallback: read_from_cache

  exceptions:
    - Cross-session reads (no RYW guarantee)
    - After session termination (cache cleared)
```

### Monotonic Reads (MR)

**Guarantee:** Successive reads by a session never return older data.

```yaml
monotonic_reads:
  scope: per_session
  guarantee: |
    If session S reads value V1 at version N1 at time T1,
    then any read at time T2 > T1 will return version N2 >= N1.

  implementation:
    - Tag all SessionState updates with monotonic version number
    - Track min_version per session (latest version read)
    - Reject reads returning version < min_version
    - Wait for version propagation if needed (<250ms)

  versioning:
    scheme: lamport_clock
    increment: on_every_delta_flush
    overflow: wrap_at_2^64

  cache_coherence:
    - Check version on cache hit
    - Invalidate cache if version < min_version
    - Fetch fresh data from K0 if stale
```

### Monotonic Writes (MW)

**Guarantee:** Writes from a session are applied in the order they were issued.

```yaml
monotonic_writes:
  scope: per_session
  guarantee: |
    If session S issues write W1 at time T1 and W2 at time T2 > T1,
    then W1 is applied before W2 in K0.

  implementation:
    - Assign sequence number to each write (per session)
    - K0 Bridge applies writes in sequence number order
    - Use FIFO queue per session for write batching
    - Reject out-of-order writes

  ordering:
    - Per-session write queue (FIFO)
    - Sequence number monotonically increasing
    - K0 WAL enforces order

  conflict_resolution:
    - Last-write-wins (LWW) for same key
    - Sequence number determines "last"
    - No concurrent writes within same session
```

### Bounded Staleness (BS)

**Guarantee:** Reads are guaranteed to be no more than 250ms stale.

```yaml
bounded_staleness:
  scope: all_reads
  guarantee: |
    If data is written at time T,
    then any read at time T + 250ms will see the write.

  max_staleness_ms: 250

  implementation:
    - K0 Bridge flushes writes every 250ms
    - Tag writes with flush_timestamp
    - Reads check data age against flush_timestamp
    - Force flush if read requires fresh data

  freshness_by_operation:
    critical_reads:
      - operation: plan_validation
        max_staleness_ms: 0     # Must be fresh
        strategy: synchronous_flush

      - operation: capability_check
        max_staleness_ms: 100   # <100ms stale ok
        strategy: best_effort

    normal_reads:
      - operation: context_retrieval
        max_staleness_ms: 250   # Default staleness ok
        strategy: batched_flush

      - operation: history_query
        max_staleness_ms: 1000  # 1s stale ok
        strategy: no_flush

  stale_read_handling:
    - Log warning if read >250ms stale
    - Metric: stale_reads_total{staleness_bucket}
    - Alert if >5% of reads stale
```

## Coherence Matrix

| Guarantee | Scope | Max Latency | Implementation Cost | Use Case |
|-----------|-------|-------------|---------------------|----------|
| Read-Your-Writes | Per-session | <1ms | Low (cache) | Immediate consistency |
| Monotonic Reads | Per-session | <250ms | Low (versioning) | Progressive data |
| Monotonic Writes | Per-session | <250ms | Medium (ordering) | Write ordering |
| Bounded Staleness | All reads | <250ms | Medium (flush) | Freshness guarantee |

## Failure Modes & Handling

```yaml
failure_modes:
  k0_unavailable:
    ryw_fallback: serve_from_cache
    mr_fallback: serve_last_known_version
    mw_fallback: queue_writes_with_backpressure
    bs_fallback: serve_stale_with_warning

  k0_slow_response:
    timeout_ms: 500
    fallback: serve_from_cache
    alert: k0_bridge_slow_response

  cache_miss:
    action: fetch_from_k0
    timeout_ms: 100
    fallback: return_error

  version_conflict:
    action: invalidate_cache
    refetch: true
    retry_count: 1
```

## Testing Strategies

### RYW Testing
```python
# Test: Read-Your-Writes
session.write("key1", "value1")
assert session.read("key1") == "value1"  # Must see own write
```

### MR Testing
```python
# Test: Monotonic Reads
v1 = session.read("key1")  # version N
time.sleep(0.3)             # Wait for potential update
v2 = session.read("key1")  # version M
assert v2.version >= v1.version  # Never go backwards
```

### MW Testing
```python
# Test: Monotonic Writes
session.write("key1", "A")  # seqno 1
session.write("key1", "B")  # seqno 2
session.write("key1", "C")  # seqno 3
# K0 must apply: A -> B -> C (in order)
```

### BS Testing
```python
# Test: Bounded Staleness
session1.write("key1", "value1", timestamp=T1)
time.sleep(0.26)  # Wait >250ms
session2_value = session2.read("key1")  # Must see value1
assert session2_value == "value1"
```

## Monitoring & Observability

```yaml
metrics:
  - coherence_violation_total{type="ryw|mr|mw|bs"}
  - staleness_ms{operation, percentile="p50|p95|p99"}
  - version_conflicts_total{session_id}
  - cache_coherence_misses_total
  - out_of_order_writes_total

alerts:
  - CoherenceViolation: violation_rate > 0.1% for 5 min
  - StalenessExceeded: p95_staleness > 250ms for 5 min
  - VersionConflictHigh: conflicts > 10/min
```

## Related Contracts

- SessionState Contracts: `../sessionstate/`
- Storage Contracts: `../storage/`
- K0 Bridge Contracts: `../k0_bridge/`
- Performance Contracts: `../performance/`

---

**Last Updated:** 2025-10-13
