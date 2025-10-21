# SessionState Contracts

**Source ADRs:** ADR-0010, ADR-0010a-e, ADR-0050

## Overview

This directory contains contracts for K1's SessionState management, which implements a 6-section memory structure with 3-tier eviction, FlatBuffers serialization, and coherence guarantees.

## Research Foundation

- **Memory Hierarchies:** Tiered eviction strategies
- **Delta Encoding:** Efficient state tracking
- **Consistency Models:** Read-your-writes, monotonic reads/writes

## Contracts Included

### 1. Six-Section Structure Contract (`six_section_structure.yaml`)
- **Source:** ADR-0010a
- Beliefs, Scoreboard, Control, Persona, Multimodal, Meta sections
- Memory budget allocation per section
- Access patterns per section

### 2. Three-Tier Eviction Contract (`three_tier_eviction.yaml`)
- **Source:** ADR-0010b
- HOT tier (in-memory, <1ms)
- WARM tier (K0 cache, <10ms)
- COLD tier (K0 disk, <100ms)

### 3. Delta Flush Contract (`delta_flush.yaml`)
- **Source:** ADR-0010c
- Incremental state updates
- Batch flushing (250ms interval)
- Delta compression

### 4. Serialization Contract (`serialization.yaml`)
- **Source:** ADR-0010d
- FlatBuffers schema
- Zero-copy deserialization
- Performance target: <1ms

### 5. Coherence Contract (`coherence.yaml`)
- **Source:** ADR-0010e, ADR-0050
- Read-your-writes (RYW)
- Monotonic reads (MR)
- Monotonic writes (MW)
- Bounded staleness (<250ms)

## Six-Section Structure

**Source:** ADR-0010a

```yaml
six_sections:
  beliefs:
    description: Agent's working memory and beliefs about the world
    contents:
      - Current plan
      - Retrieved context
      - User intent
      - Conversation history (recent)
    memory_budget_kb: 16
    access_pattern: read_heavy
    eviction_priority: MEDIUM

  scoreboard:
    description: Short-term performance metrics and decisions
    contents:
      - Recent agent scores
      - Task success/failure rates
      - Tool invocation results
      - Clarification history
    memory_budget_kb: 8
    access_pattern: write_heavy
    eviction_priority: LOW

  control:
    description: Orchestration state and agent lifecycle
    contents:
      - Active agents (state, capabilities)
      - Task queue
      - Protocol states
      - Backpressure signals
    memory_budget_kb: 4
    access_pattern: read_write_balanced
    eviction_priority: HIGH (never evict)

  persona:
    description: User preferences and long-term profile
    contents:
      - User preferences
      - Communication style
      - Privacy settings
      - Accessibility needs
    memory_budget_kb: 8
    access_pattern: read_heavy
    eviction_priority: MEDIUM

  multimodal:
    description: Non-text data (audio, images)
    contents:
      - Voice embeddings
      - Image thumbnails
      - Audio waveform cache
    memory_budget_kb: 16
    access_pattern: read_heavy
    eviction_priority: LOW

  meta:
    description: Session metadata and system state
    contents:
      - Session ID
      - Creation timestamp
      - Last activity timestamp
      - Thermal state
      - Memory pressure
    memory_budget_kb: 2
    access_pattern: read_write_balanced
    eviction_priority: HIGH (never evict)

total_budget:
  soft_limit_kb: 54
  hard_limit_kb: 64
  overflow_policy: trigger_eviction
```

## Three-Tier Eviction

**Source:** ADR-0010b

```yaml
three_tier_eviction:
  HOT:
    description: In-memory, immediately accessible
    storage: K1 heap memory
    latency_p95_ms: 1
    capacity_kb: 64
    eviction_policy: LRU

  WARM:
    description: K0 in-memory cache
    storage: K0 memory (shared across sessions)
    latency_p95_ms: 10
    capacity_kb: 512
    eviction_policy: LRU

  COLD:
    description: K0 persistent storage
    storage: K0 disk (RocksDB)
    latency_p95_ms: 100
    capacity: unlimited
    eviction_policy: TTL (session_ttl + 24h)

eviction_algorithm:
  trigger:
    condition: HOT_usage > soft_limit
    action: evict_to_WARM

  selection:
    factors:
      - section.eviction_priority (HIGH never evicted)
      - last_access_time (LRU)
      - access_frequency (LFU bonus)
      - data_size (prefer evicting large items)

    formula: |
      eviction_score = (
        (now - last_access_time) * 0.5 +
        (1.0 / access_frequency) * 0.3 +
        (data_size / max_size) * 0.2
      )
      evict_highest_score()

  warm_to_cold:
    trigger: WARM_usage > capacity * 0.8
    action: flush_to_K0_disk
    batch_size: 10 entries

  cold_cleanup:
    trigger: session_terminated + 24h
    action: delete_from_K0
```

## Delta Flush

**Source:** ADR-0010c

```yaml
delta_flush:
  description: Incremental state updates to K0

  delta_tracking:
    mechanism: dirty_flag per section
    granularity: section_level

  delta_format:
    session_id: string
    section: beliefs | scoreboard | control | persona | multimodal | meta
    delta_type: UPDATE | DELETE | APPEND
    data: FlatBuffers encoded changes
    version: integer
    timestamp: iso8601

  flush_strategy:
    interval_ms: 250
    batch_size: 10 deltas
    trigger_conditions:
      - Timer expired (250ms)
      - Critical update (control section)
      - Memory pressure (>80% usage)
      - Session termination

  compression:
    algorithm: LZ4
    enabled_for: sections > 4KB
    compression_ratio: ~2x

  ordering:
    guarantee: monotonic_writes
    enforcement: sequence_number per session
    conflict_resolution: last_write_wins
```

## Serialization

**Source:** ADR-0010d

```yaml
serialization:
  format: FlatBuffers

  schema:
    SessionState:
      session_id: string
      created_at: timestamp
      last_updated: timestamp
      sections:
        beliefs: BeliefsSection
        scoreboard: ScoreboardSection
        control: ControlSection
        persona: PersonaSection
        multimodal: MultimodalSection
        meta: MetaSection
      version: integer

  performance:
    serialization_latency_p95_ms: 1
    deserialization_latency_p95_ms: 1
    zero_copy: true

  schema_evolution:
    strategy: forward_and_backward_compatible
    versioning: schema_version field
    migration: on_demand during read
```

## Coherence Guarantees

**Source:** ADR-0010e, ADR-0050

```yaml
coherence:
  read_your_writes:
    guarantee: |
      If session S writes value V to key K at time T1,
      then any read of K by session S at time T2 > T1
      will return V or a newer value.
    implementation: session_local_cache

  monotonic_reads:
    guarantee: |
      If session S reads value V1 at version N1,
      then any subsequent read returns version N2 >= N1.
    implementation: version_tracking

  monotonic_writes:
    guarantee: |
      Writes from session S are applied in the order issued.
    implementation: sequence_numbers + FIFO_queue

  bounded_staleness:
    guarantee: |
      Reads are guaranteed to be no more than 250ms stale.
    implementation: timestamp_checking + flush_interval

# See ../coherence/README.md for full coherence contract details
```

## Performance Requirements

```yaml
performance:
  read_latency_p95_ms:
    HOT: 1
    WARM: 10
    COLD: 100

  write_latency_p95_ms:
    async_write: 1
    sync_flush: 250

  memory_budget:
    per_session_kb: 64
    max_sessions: 100
    total_memory_mb: 6.4

  throughput:
    reads_per_second: 10000
    writes_per_second: 5000
```

## Observability

```yaml
observability:
  metrics:
    - sessionstate_size_bytes{session_id, section}
    - sessionstate_read_latency_ms{tier, percentile}
    - sessionstate_write_latency_ms{percentile}
    - sessionstate_eviction_total{tier, section}
    - sessionstate_delta_flush_total{session_id}
    - sessionstate_coherence_violation_total{type}

  alerts:
    - SessionStateOversized: size > 64KB
    - SessionStateReadSlow: p95 > 10ms for HOT tier
    - SessionStateEvictionHigh: eviction_rate > 10/min
    - CoherenceViolation: violation detected
```

## Related Contracts

- Storage: `../storage/`
- K0 Bridge: `../k0_bridge/`
- Coherence: `../coherence/`
- FlatBuffers: `../flatbuffers/`

---

**Last Updated:** 2025-10-13
