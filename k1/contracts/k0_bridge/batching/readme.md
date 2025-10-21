# K0 Bridge Batching Contracts

**Source ADRs:** ADR-0001a, ADR-0044c

## Overview

This directory contains contracts for K0 Bridge batching strategies, which optimize communication between K1 and K0 by grouping multiple operations together.

## Batching Benefits

- **Reduced overhead:** Fewer round trips between K1 and K0
- **Better throughput:** Higher aggregate throughput
- **Improved efficiency:** Amortize connection costs
- **Backpressure handling:** Natural flow control mechanism

## Contracts Included

### 1. Batch Configuration Contract (`batch_config.yaml`)
- Batch size limits (10-50 messages)
- Flush interval (100ms)
- Adaptive batching rules

### 2. Batch Ordering Contract (`batch_ordering.yaml`)
- FIFO ordering guarantees
- Dependency resolution
- Priority handling

### 3. Batch Compression Contract (`batch_compression.yaml`)
- Compression algorithms (LZ4)
- Compression thresholds
- Decompression strategies

## Batch Configuration

**Source:** ADR-0044c

```yaml
batch_configuration:
  min_batch_size: 10
  max_batch_size: 50
  flush_interval_ms: 100
  max_payload_size_kb: 64

  flush_triggers:
    - Timer expired (100ms)
    - Batch size reached (50 messages)
    - Critical operation (immediate flush)
    - Backpressure signal (delay flush)
    - Session termination (immediate flush)

  adaptive_batching:
    enabled: true

    low_load:
      condition: queue_size < 10
      batch_size: 10
      flush_interval_ms: 50

    normal_load:
      condition: 10 <= queue_size < 30
      batch_size: 30
      flush_interval_ms: 100

    high_load:
      condition: queue_size >= 30
      batch_size: 50
      flush_interval_ms: 150
```

## Batch Structure

```yaml
batch_structure:
  batch_id: string (UUID)
  operations:
    - operation_id: string
      port: Pxx
      payload: [ubyte]  # FlatBuffers encoded
      priority: URGENT | HIGH | NORMAL | LOW
      timestamp: int64

  metadata:
    batch_size: integer
    total_payload_kb: float
    compression_enabled: boolean
    trace_id: string

  constraints:
    max_operations: 50
    max_payload_kb: 64
```

## Batch Ordering

**Source:** ADR-0001a

```yaml
batch_ordering:
  guarantees:
    - Per-session FIFO ordering
    - Operations from same session execute in order
    - Cross-session operations may be reordered

  ordering_strategy:
    per_session_queue:
      description: Separate queue per session
      ordering: FIFO

    global_batch:
      description: Combine operations from multiple sessions
      ordering: Round-robin across sessions
      fairness: Equal priority across sessions

  dependency_resolution:
    - If operation B depends on operation A
    - Ensure A is in same batch before B
    - Or split into separate batches (A first, then B)

  priority_handling:
    URGENT:
      - Bypass batching, send immediately
      - Use for critical operations (e.g., barge-in)

    HIGH:
      - Include in current batch
      - Flush batch early if needed

    NORMAL:
      - Normal batching behavior

    LOW:
      - Can be delayed if needed
      - Drop if queue full (under backpressure)
```

## Batch Compression

**Source:** ADR-0044c

```yaml
batch_compression:
  algorithm: LZ4

  compression_threshold:
    min_payload_size_kb: 4
    compression_ratio_target: 2.0

  strategy:
    - If batch payload < 4KB: no compression
    - If batch payload >= 4KB: compress with LZ4
    - If compression ratio < 1.2: send uncompressed

  compression_overhead:
    cpu_overhead_ms: 5
    decompression_overhead_ms: 3

  compression_metadata:
    compressed: boolean
    original_size_kb: float
    compressed_size_kb: float
    compression_ratio: float
```

## Batch Processing Flow

```yaml
batch_processing:
  k1_side:
    1_collect:
      - Collect operations in per-session queues
      - Monitor batch size and time

    2_trigger_flush:
      - Timer expired OR batch size reached OR critical op

    3_create_batch:
      - Combine operations from queues (round-robin)
      - Respect per-session FIFO ordering
      - Apply priority rules

    4_compress:
      - Compress if payload > 4KB

    5_send:
      - Send batch over HTTP/2 stream
      - Track batch_id for response correlation

  k0_side:
    1_receive:
      - Receive batch over HTTP/2

    2_decompress:
      - Decompress if needed

    3_parse:
      - Parse batch structure
      - Validate operations

    4_execute:
      - Execute operations sequentially
      - Respect per-session ordering

    5_respond:
      - Bundle responses into batch
      - Send back to K1
```

## Performance Characteristics

```yaml
performance:
  batch_creation_latency_ms: 10
  compression_latency_ms: 5
  network_latency_ms: 10
  k0_processing_latency_ms: 50
  decompression_latency_ms: 3
  total_latency_p95_ms: 100

  throughput:
    operations_per_second: 1000
    batches_per_second: 20
    avg_batch_size: 50

  efficiency:
    overhead_reduction: 80% (vs individual operations)
    network_utilization: 90%
```

## Backpressure Integration

```yaml
backpressure_handling:
  detection:
    - K1 queue size > 80%
    - K0 processing slow
    - Network congestion

  response:
    - Increase flush_interval (reduce batch frequency)
    - Increase batch_size (larger batches)
    - Drop LOW priority operations
    - Signal backpressure upstream

  recovery:
    - Queue size drops below 60%
    - Resume normal batching parameters
    - Process queued operations
```

## Error Handling

```yaml
error_handling:
  batch_failure:
    - If entire batch fails: retry whole batch
    - If partial failure: retry failed operations only
    - If retry exhausted: return errors to callers

  operation_failure:
    - Mark operation as failed
    - Continue processing remaining operations
    - Return partial success

  network_failure:
    - Buffer batch in memory
    - Retry with exponential backoff
    - Alert if buffered batches > threshold
```

## Monitoring

```yaml
observability:
  metrics:
    - batch_size{percentile}
    - batch_flush_latency_ms{percentile}
    - batch_compression_ratio
    - batch_throughput{batches_per_sec}
    - batch_failure_total{reason}

  alerts:
    - BatchLatencyHigh: p95 > 150ms for 5 min
    - BatchCompressionRatioLow: ratio < 1.5
    - BatchFailureRateHigh: failure_rate > 5%
```

## Usage Example

```python
# K1 side: Add operations to batch
batch_queue = BatchQueue(
    min_size=10,
    max_size=50,
    flush_interval_ms=100
)

# Add operation
await batch_queue.add(
    port=Port.P02_PERSIST,
    payload=persist_request,
    priority=Priority.NORMAL
)

# Batch flushed automatically after 100ms or 50 ops
```

## Related Contracts

- K0 Bridge Ports: `../ports/`
- Performance: `../../performance/backpressure_cascade.yaml`
- Bridge Integration: `../../bridge_integration/batching_strategy.yaml`

---

**Last Updated:** 2025-10-13
