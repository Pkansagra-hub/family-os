# Week 5 Implementation Plan — SessionState & Actor Fabric Mailbox

**Date**: October 26, 2025
**Epic**: K1 Layer 4 Runtime Core
**Duration**: 2 weeks (10 working days)
**Status**: 🟢 READY FOR IMPLEMENTATION
**Target**: Production-grade code with full WARD test coverage

---

## 📊 Plan Overview

This plan decomposes Week 5 implementation into **3 Epics**, **15 Issues**, and **5 Milestones** for structured development with clear dependencies.

### Epic Dependencies

```
Epic 1: SessionState Foundation
├── Issue 1.1: FlatBuffers Schema Definition
├── Issue 1.2: SessionState Model Class
├── Issue 1.3: Serialization/Deserialization
├── Issue 1.4: Delta Computation
└── Issue 1.5: WARD Tests (SessionState)

Epic 2: Actor Fabric Mailbox (Parallel)
├── Issue 2.1: MPSC Queue Infrastructure
├── Issue 2.2: Priority Queue Routing
├── Issue 2.3: Backpressure Watermarks
├── Issue 2.4: Message TTL & Cleanup
├── Issue 2.5: WARD Tests (Mailbox)
└── Issue 2.6: Dead Letter Queue

Epic 3: Runtime Integration
├── Issue 3.1: SessionState Control (RwLock + Batching)
├── Issue 3.2: Memory Manager (3-Tier Eviction)
├── Issue 3.3: Integration Tests (SessionState ↔ Mailbox)
└── Issue 3.4: Observability (Metrics + Spans)
```

---

## 📋 Epic 1: SessionState Foundation

**Status**: 🔴 NOT STARTED
**Duration**: 3 days
**Complexity**: HIGH
**Dependencies**: FlatBuffers compiler, Message.fbs schema

### Issue 1.1: FlatBuffers Schema Definition

**Title**: Define FlatBuffers schema for SessionState (6-section structure)
**Points**: 8
**Priority**: 🔴 BLOCKER
**Owner**: AI Coder

**Description**:
Create FlatBuffers schema file for SessionState with 6 sections:

1. Beliefs (user model, inferences, preferences)
2. Scoreboard (current task, subtasks, progress)
3. Control (session metadata, trace_id, version)
4. Persona (agent type, OCEAN traits, tone)
5. Multimodal (audio/text/vision buffers)
6. Meta (schema version, checksum, compression)

**Acceptance Criteria**:

- [ ] Schema file: `k1/contracts/flatbuffers/session_state.fbs`
- [ ] All 6 sections defined with proper types
- [ ] Comments document each field's purpose
- [ ] Compiles with `flatc` without warnings
- [ ] Cross-references to Message.fbs validated
- [ ] Performance inline comments (e.g., "serialization budget: <1ms")

**Tasks**:

```
1. Create session_state.fbs file in k1/contracts/flatbuffers/
2. Define Beliefs table (Dict-like, 3 fields)
3. Define Scoreboard table (current_task: TaskInfo, subtasks: Vector[SubtaskInfo])
4. Define Control table (session_id: string, user_id: string, trace_id: string, etc.)
5. Define Persona table (agent_type: string, traits: Map<string, string>, tone: string)
6. Define Multimodal table (audio_buffer: bytes, text_history: Vector[string], vision_context: bytes)
7. Define Meta table (schema_version: string, checksum: string, compression: string)
8. Define root SessionState table combining all 6 sections
9. Run flatc compiler: flatc --python -o k1/l4_runtime/session_state/ session_state.fbs
10. Verify generated code in session_state/ directory
```

**Related ADRs**: ADR-0011 (Message.fbs), ADR-0012 (FlatBuffers)

---

### Issue 1.2: SessionState Model Class

**Title**: Implement SessionState wrapper class with Python API
**Points**: 13
**Priority**: 🔴 BLOCKER
**Owner**: AI Coder
**Depends On**: Issue 1.1

**Description**:
Create Python wrapper class `SessionState` that:

- Wraps FlatBuffers generated code
- Provides ergonomic Python API for reads/writes
- Implements `__repr__`, `__eq__` for debugging
- Validates schema invariants (e.g., version matches)
- Tracks field access patterns for performance monitoring

**Acceptance Criteria**:

- [ ] File: `k1/l4_runtime/session_state/model.py` (~300 lines)
- [ ] Class `SessionState` with 6 properties (beliefs, scoreboard, control, persona, multimodal, meta)
- [ ] Constructor accepts Dict or FlatBuffers bytes
- [ ] `.to_bytes()` serialization method
- [ ] `.from_bytes()` class method (deserialization)
- [ ] `.to_dict()` method for logging/debugging
- [ ] Type hints on all methods
- [ ] Docstrings with examples
- [ ] No simulation code (real FlatBuffers usage)

**Tasks**:

```
1. Create k1/l4_runtime/session_state/__init__.py with module exports
2. Create k1/l4_runtime/session_state/model.py
3. Import generated FlatBuffers code (SessionState_generated.py)
4. Define SessionState class with 6 properties:
   - beliefs: Beliefs (read-only)
   - scoreboard: Scoreboard (read-only)
   - control: Control (read-only)
   - persona: Persona (read-only)
   - multimodal: Multimodal (read-only)
   - meta: Meta (read-only)
5. Implement __init__(beliefs=None, scoreboard=None, ...)
6. Implement to_bytes() → bytes (serialize via FlatBuffers)
7. Implement @classmethod from_bytes(data: bytes) → SessionState
8. Implement to_dict() → Dict for debugging
9. Implement __repr__() for logging
10. Implement __eq__() for testing
11. Add type hints (from typing import Optional, Dict, List, etc.)
12. Add docstring with usage example
13. Test imports work correctly
```

**Related ADRs**: ADR-0011, ADR-0012

---

### Issue 1.3: Serialization & Deserialization

**Title**: Implement <1ms P95 serialization/deserialization with benchmarks
**Points**: 8
**Priority**: 🟡 HIGH
**Owner**: AI Coder
**Depends On**: Issue 1.2

**Description**:
Optimize serialization path to meet <1ms P95 budget:

- Profile serialization performance
- Add compression option (gzip, zstd)
- Implement streaming deserialization
- Add performance monitoring hooks

**Acceptance Criteria**:

- [ ] `SessionState.serialize(compression=None)` method
- [ ] `SessionState.deserialize(data, compression=None)` class method
- [ ] Uncompressed: <0.5ms P95 serialization
- [ ] Compressed (zstd): <0.8ms P95 serialization + compression
- [ ] Deserialization: <0.5ms P95
- [ ] Benchmark code in tests/
- [ ] Metrics exported for monitoring

**Tasks**:

```
1. Add serialize() method to SessionState:
   - FlatBuffers builder pattern
   - Optional compression (zstd recommended)
   - Return (compressed_bytes, compression_type)
2. Add deserialize(data, compression) class method
3. Profile with 1000 iterations (average, P95, P99)
4. Create benchmark file: tests/l4_runtime/benchmarks/bench_session_state_serialization.py
5. Run benchmark and validate <1ms P95
6. Add Prometheus metric: session_state_serialization_ms histogram
7. Log compression ratio achieved (target: 40-60% reduction)
8. Document in docstring
```

**Related ADRs**: ADR-0011

---

### Issue 1.4: Delta Computation

**Title**: Implement incremental state diffs for K0 batching
**Points**: 13
**Priority**: 🔴 BLOCKER
**Owner**: AI Coder
**Depends On**: Issue 1.2

**Description**:
Compute deltas between state snapshots for efficient K0 batching:

- Track before/after for each field
- Only serialize changed sections
- Maintain version number for conflict detection
- Budget: <10ms P95 delta merge

**Acceptance Criteria**:

- [ ] `SessionState.compute_delta(prev_state: SessionState) → Delta`
- [ ] Delta class: `@dataclass Delta` with changed fields only
- [ ] Version tracking: `state.control.version` increments on each update
- [ ] P95 latency: <10ms for 100-field state
- [ ] Only changed sections included in delta
- [ ] Metrics exported: `session_state_delta_merge_ms`

**Tasks**:

```
1. Create Delta dataclass in model.py:
   - changed_sections: List[str]  # ['beliefs', 'scoreboard', ...]
   - beliefs_delta: Optional[Beliefs]
   - scoreboard_delta: Optional[Scoreboard]
   - ... (one per section)
   - new_version: int
   - timestamp_ms: int

2. Implement compute_delta(prev_state) method:
   - Compare self.beliefs with prev_state.beliefs (field-by-field)
   - If different, add 'beliefs' to changed_sections
   - Repeat for all 6 sections
   - Return Delta with only changed sections
   - Include timestamp_ms (current time)
   - Increment version

3. Implement Delta.to_bytes() for K0 transmission

4. Create benchmark: tests/l4_runtime/benchmarks/bench_delta_computation.py
   - Test with 100 fields changed
   - Test with 1 field changed
   - Measure P95 latency

5. Add Prometheus metric: session_state_delta_merge_ms
```

**Related ADRs**: ADR-0038b (K0 WAL), ADR-0011

---

### Issue 1.5: WARD Tests for SessionState

**Title**: Comprehensive WARD test suite for SessionState (100% coverage)
**Points**: 13
**Priority**: 🟡 HIGH
**Owner**: AI Coder
**Depends On**: Issues 1.2, 1.3, 1.4

**Description**:
Full WARD test suite covering:

- Serialization/deserialization round-trip
- Delta computation correctness
- Concurrent access (read safety)
- Version tracking
- Performance budgets

**Acceptance Criteria**:

- [ ] File: `tests/l4_runtime/test_session_state.py` (~400 lines)
- [ ] ≥15 test cases covering all scenarios
- [ ] Performance benchmarks integrated
- [ ] Coverage: >95% code coverage
- [ ] All tests pass in <5 seconds total
- [ ] Uses WARD fixtures and assertions

**Tasks**:

```
1. Create tests/l4_runtime/test_session_state.py

2. Write test cases:
   @test("session_state_serializes_to_bytes")
   @test("session_state_deserializes_from_bytes")
   @test("serialization_round_trip_preserves_data")
   @test("serialization_latency_under_1ms_p95")
   @test("delta_computation_identifies_changed_fields")
   @test("delta_only_includes_changed_sections")
   @test("delta_increments_version")
   @test("delta_preserves_timestamp")
   @test("version_mismatch_detected")
   @test("empty_delta_when_no_changes")
   @test("multiple_section_changes_tracked")
   @test("concurrent_reads_allowed")
   @test("to_dict_produces_valid_structure")
   @test("compression_reduces_size")
   @test("decompression_restores_original")

3. Use fixtures for common state objects:
   - fixture: sample_beliefs
   - fixture: sample_scoreboard
   - fixture: sample_control
   - fixture: full_session_state

4. Verify all tests pass: python -m ward test --path tests/l4_runtime/

5. Generate coverage report: pytest --cov tests/l4_runtime/
```

**Related ADRs**: ADR-0011

---

## 📋 Epic 2: Actor Fabric Mailbox

**Status**: 🔴 NOT STARTED
**Duration**: 3 days (parallel with Epic 1)
**Complexity**: VERY HIGH
**Dependencies**: FlatBuffers Message.fbs, asyncio/tokio

### Issue 2.1: MPSC Queue Infrastructure

**Title**: Implement async MPSC queue with <0.5ms P95 enqueue/dequeue
**Points**: 13
**Priority**: 🔴 BLOCKER
**Owner**: AI Coder

**Description**:
Core MPSC (Multiple Producers, Single Consumer) queue using asyncio.Queue:

- Thread-safe message passing
- Low-latency enqueue/dequeue
- Configurable capacity (default 1024)
- Performance budget: <0.5ms P95 per operation

**Acceptance Criteria**:

- [ ] File: `k1/l4_runtime/actor_fabric/mailbox/base.py` (~150 lines)
- [ ] Class `MessageQueue` wrapping `asyncio.Queue`
- [ ] `async enqueue(message: Message) → bool`
- [ ] `async dequeue() → Message`
- [ ] `size() → int` (current queue depth)
- [ ] `capacity() → int` (max capacity)
- [ ] Enqueue P95 latency: <0.5ms
- [ ] Dequeue P95 latency: <0.5ms
- [ ] Type hints, docstrings, no simulation

**Tasks**:

```
1. Create k1/l4_runtime/actor_fabric/mailbox/__init__.py
2. Create k1/l4_runtime/actor_fabric/mailbox/base.py
3. Import Message from k1/contracts/flatbuffers/message_pb2.py
4. Define MessageQueue class:
   - __init__(capacity: int = 1024)
   - _queue: asyncio.Queue
5. Implement async enqueue(message: Message) → bool:
   - Check capacity
   - Put in queue (returns True)
   - Return False if full (but asyncio.Queue shouldn't block)
6. Implement async dequeue() → Message:
   - Get from queue
   - Return Message
7. Implement size() → int (queue.qsize())
8. Implement capacity() → int (return self._capacity)
9. Add __repr__ and status logging
10. Add docstring with usage example
```

**Related ADRs**: ADR-0002 (Actor Model), ADR-0002a (Mailbox MPSC Queue), ADR-0011 (Message.fbs)

**Note**: Code header must explicitly reference ADR-0002a for cross-reference.

---

### Issue 2.2: Priority Queue Routing

**Title**: Implement 4-tier priority scheduler (URGENT/REALTIME/INTERACTIVE/BACKGROUND)
**Points**: 21
**Priority**: 🔴 BLOCKER
**Owner**: AI Coder
**Depends On**: Issue 2.1

**Description**:
Route messages to 4 separate priority queues with strict ordering:

- URGENT (0): System-critical, max 50 messages
- REALTIME (1): User input, max 100 messages
- INTERACTIVE (2): Tool results, max 200 messages
- BACKGROUND (3): Batch ops, max 1024 messages

Dequeue in URGENT→REALTIME→INTERACTIVE→BACKGROUND order.

**Acceptance Criteria**:

- [ ] File: `k1/l4_runtime/actor_fabric/mailbox/scheduler.py` (~250 lines)
- [ ] Class `PriorityScheduler` with 4 queues
- [ ] `async send(message: Message, priority: int) → SendResult`
- [ ] `async receive() → Message` (respects priority order)
- [ ] Backpressure returns error (not blocking)
- [ ] Enqueue P95: <0.5ms (even with 4 queues)
- [ ] Dequeue respects URGENT > REALTIME > INTERACTIVE > BACKGROUND
- [ ] Round-robin fairness within tier
- [ ] Metrics: enqueue latency per priority

**Tasks**:

```
1. Create k1/l4_runtime/actor_fabric/mailbox/scheduler.py

2. Define Priority constants:
   PRIORITY_URGENT = 0
   PRIORITY_REALTIME = 1
   PRIORITY_INTERACTIVE = 2
   PRIORITY_BACKGROUND = 3

3. Define SendResult dataclass:
   @dataclass
   class SendResult:
       success: bool
       reason: Optional[str] = None  # "BACKPRESSURE", "INVALID_PRIORITY"

4. Implement PriorityScheduler class:
   - __init__()
   - _queues: Dict[int, MessageQueue] (4 queues)
   - _queue_capacities: Dict[int, int]
     {0: 50, 1: 100, 2: 200, 3: 1024}

5. Implement async send(message, priority) → SendResult:
   - Validate priority in [0, 1, 2, 3]
   - Check queue size < capacity
   - If >= capacity, return SendResult(success=False, reason="BACKPRESSURE")
   - Enqueue to appropriate priority queue
   - Return SendResult(success=True)

6. Implement async receive() → Message:
   - Check URGENT queue first
   - If empty, check REALTIME
   - If empty, check INTERACTIVE
   - If empty, check BACKGROUND
   - Use round-robin fairness (don't always pick URGENT)
     - Pattern: receive 4 BACKGROUND messages for every 1 URGENT
   - Return next Message

7. Implement WFQ aging mechanism (ADR-0002a parity):
   - Track message age in each queue
   - Promote BACKGROUND messages to INTERACTIVE after 5s
   - Promote INTERACTIVE to REALTIME after 5s
   - Log promotion events for observability

8. Implement size() → Dict[int, int] (sizes per priority)

9. Add metrics tracking:
   - enqueue_latency_ms per priority
   - backpressure_events_total
   - priority_promotions_total counter (for aging)

10. Add code header referencing ADR-0002a explicitly

11. Add comprehensive docstrings
```

**Related ADRs**: ADR-0002a (Mailbox MPSC Queue), ADR-0061a (Watermark Thresholds)

**Note**: Code header must explicitly reference ADR-0002a for cross-reference.

---

### Issue 2.3: Backpressure Watermarks

**Title**: Implement 3-level watermarks (WARN/DEGRADE/REJECT)
**Points**: 13
**Priority**: 🟡 HIGH
**Owner**: AI Coder
**Depends On**: Issue 2.2

**Description**:
Add watermark monitoring to detect and handle queue saturation:

- GREEN: <50% capacity
- YELLOW: 50-70% (log warning)
- RED: 70-90% (degrade service)
- CRITICAL: >90% (reject new messages)

**Acceptance Criteria**:

- [ ] Watermarks enforced at: warn=80%, degrade=90%, reject=95%
- [ ] `get_pressure_level() → PressureLevel` (GREEN/YELLOW/RED/CRITICAL)
- [ ] Callbacks on level change (for backpressure cascade integration)
- [ ] Hysteresis to prevent thrashing (5% band)
- [ ] Metrics: `mailbox_pressure_level` gauge

**Tasks**:

```
1. Create k1/l4_runtime/actor_fabric/mailbox/watermarks.py

2. Define PressureLevel enum:
   class PressureLevel(IntEnum):
       GREEN = 0        # <50%
       YELLOW = 1       # 50-70%
       RED = 2          # 70-90%
       CRITICAL = 3     # >90%

3. Update PriorityScheduler to track watermarks:
   - _pressure_level: PressureLevel = GREEN
   - _pressure_callbacks: List[Callable[[PressureLevel]]] = []

4. Update send() to check watermark:
   - usage_pct = (queue_size / queue_capacity) * 100
   - If usage_pct >= 95%, return SendResult(success=False)
   - If usage_pct >= 90% and pressure_level < RED, update to RED
   - Log watermark changes

5. Implement get_pressure_level() → PressureLevel

6. Implement register_pressure_callback(callback):
   - Callback called on pressure level change

7. Add Prometheus metrics:
   - mailbox_queue_usage_pct gauge (per priority)
   - mailbox_pressure_level gauge
   - mailbox_pressure_transitions_total counter

8. Test with gradual queue filling
```

**Related ADRs**: ADR-0061 (Backpressure Cascade), ADR-0061a (Watermarks)

---

### Issue 2.4: Message TTL & Cleanup

**Title**: Implement message expiry and dead letter routing
**Points**: 8
**Priority**: 🟡 HIGH
**Owner**: AI Coder
**Depends On**: Issue 2.1

**Description**:
Add message TTL tracking and automatic cleanup:

- Default TTL: 5000ms
- Periodic cleanup every 100ms
- Expired messages → Dead Letter Queue
- Metrics: messages_expired_total

**Acceptance Criteria**:

- [ ] Message includes `ttl_ms` field (default 5000)
- [ ] Cleanup loop every 100ms
- [ ] Expired messages removed and logged
- [ ] Metrics tracking expiry events
- [ ] No performance impact (<1ms cleanup per 1000 messages)

**Tasks**:

```
1. Add cleanup() method to MessageQueue:
   - Iterate through queue
   - Check each message's (current_time - timestamp) > ttl_ms
   - If expired, route to DLQ
   - Record metric: messages_expired_total

2. Create async cleanup task in Mailbox:
   - Run every 100ms
   - Call cleanup() on each queue

3. Add Prometheus metrics:
   - mailbox_messages_expired_total counter
   - mailbox_cleanup_latency_ms histogram

4. Add configuration option: cleanup_interval_ms (default 100)

5. Test cleanup doesn't block dequeue operations
```

**Related ADRs**: ADR-0002 (Actor Model), ADR-0002a (Mailbox MPSC Queue)

---

### Issue 2.5: WARD Tests for Mailbox

**Title**: Comprehensive WARD test suite for Mailbox
**Points**: 13
**Priority**: 🟡 HIGH
**Owner**: AI Coder
**Depends On**: Issues 2.1-2.4

**Description**:
Full test coverage for mailbox operations:

- Priority ordering
- Backpressure behavior
- TTL expiry
- Performance budgets
- Concurrent access

**Acceptance Criteria**:

- [ ] File: `tests/l4_runtime/test_mailbox.py` (~500 lines)
- [ ] ≥20 test cases
- [ ] Coverage: >95% code coverage
- [ ] All performance budgets validated
- [ ] All tests pass in <10 seconds

**Tasks**:

```
1. Create tests/l4_runtime/test_mailbox.py

2. Write test cases:
   @test("mailbox_enqueue_dequeue_fifo")
   @test("mailbox_priority_ordering_urgent_first")
   @test("mailbox_priority_ordering_realtime_second")
   @test("mailbox_round_robin_fairness_within_tier")
   @test("mailbox_enqueue_latency_under_0_5ms")
   @test("mailbox_dequeue_latency_under_0_5ms")
   @test("mailbox_backpressure_reject_at_95_percent")
   @test("mailbox_pressure_level_transitions_correctly")
   @test("mailbox_message_ttl_expiry_removes_old_messages")
   @test("mailbox_cleanup_runs_every_100ms")
   @test("mailbox_concurrent_senders_no_race")
   @test("mailbox_size_returns_accurate_count")
   @test("mailbox_empty_returns_none_or_blocks")
   @test("mailbox_watermark_hysteresis_prevents_thrashing")
   @test("mailbox_metrics_exported_correctly")
   @test("mailbox_prometheus_registry_contains_expected_metrics")  # NEW: Verify metrics sanity
   @test("mailbox_message_trace_id_preserved")
   @test("mailbox_invalid_priority_rejected")
   @test("mailbox_large_message_payload_handled")
   @test("mailbox_wfq_aging_promotes_background_after_5s")  # NEW: WFQ aging test
   @test("mailbox_dlq_retention_config_respected")  # NEW: DLQ retention config test
   @test("mailbox_stress_test_1000_concurrent_sends")
   @test("mailbox_stress_test_rapid_priority_transitions")
   @test("mailbox_promotion_when_destination_full_pushes_back") — aged BACKGROUND→INTERACTIVE promotion fails when dest full; message returned to source.
   @test("mailbox_promotion_metadata_preserved_and_incremented") — original_priority unchanged, current_priority updated, promotions += 1.
   @test("mailbox_aging_disabled_never_moves_messages") — with enable_aging=False, no promotions occur.
   @test("mailbox_aging_respects_max_scan_window") — promotions scan at most max_scan items; untouched items remain in order.
   @test("mailbox_fairness_background_seen_under_urgent_pressure") — with continuous URGENT load, BACKGROUND still surfaces per fairness rule.
   @test("mailbox_watermark_callbacks_hysteresis_once_per_transition") — GREEN↔YELLOW↔RED↔CRITICAL fire exactly once each, with 5% hysteresis.
   @test("mailbox_ttl_boundary_exact_threshold") — message expiring exactly at TTL is treated as expired (edge boundary).
   @test("mailbox_dlq_capacity_and_retention_enforced") — DLQ caps at N, oldest evicted; entries expire per retention config.
   @test("mailbox_corrupted_header_rejected_no_crash") — truncated/invalid header safely rejected; counters updated.
   @test("mailbox_metrics_self_consistency_invariants") — sum(dequeue_count) == total_received, sum(enqueue_count) - sum(dequeue_count) == total_queue_size.

3. Fixtures:
   - fixture: test_message
   - fixture: test_priority_messages (one per priority)
   - fixture: mailbox
   - fixture: prometheus_registry (for metrics sanity tests)

4. Metrics sanity test implementation:
   - Verify Prometheus registry contains expected metrics
   - Check histogram buckets configured correctly
   - Validate counter/gauge/histogram types match specs

5. Verify all pass: python -m ward test --path tests/l4_runtime/test_mailbox.py
```

**Related ADRs**: ADR-0002 (Actor Model), ADR-0002a (Mailbox MPSC Queue)

---

### Issue 2.6: Dead Letter Queue

**Title**: Implement Dead Letter Queue for undeliverable messages
**Points**: 13
**Priority**: 🟡 MEDIUM
**Owner**: AI Coder
**Depends On**: Issue 2.5

**Description**:
DLQ storage for failed/expired messages with replay capability:

- In-memory storage with TTL (24h default)
- Lookup by trace_id
- Replay to new recipient
- Metrics: dlq_depth, replay_attempts

**Acceptance Criteria**:

- [ ] File: `k1/l4_runtime/actor_fabric/mailbox/dead_letter.py` (~200 lines)
- [ ] `enqueue(message, reason) → dlq_id`
- [ ] `get_by_trace_id(trace_id) → List[DLQEntry]`
- [ ] `replay(dlq_id, new_recipient) → bool`
- [ ] Automatic expiry after 24h
- [ ] Metrics exported

**Tasks**:

```
1. Create k1/l4_runtime/actor_fabric/mailbox/dead_letter.py

2. Define DLQEntry dataclass:
   @dataclass
   class DLQEntry:
       dlq_id: str
       original_message: Message
       rejection_reason: str
       rejected_at_ms: int
       ttl_ms: int = 86400000  # 24 hours (configurable)
       trace_id: str

3. Implement DeadLetterQueue class:
   - __init__(retention_ms: int = 86400000)  # Load from mailbox_config.yml
   - _entries: Dict[str, DLQEntry]
   - _trace_id_index: Dict[str, List[str]] (trace_id → dlq_ids)
   - _retention_ms: int (configurable retention period)

4. Implement enqueue(message, reason) → str:
   - Generate dlq_id
   - Create DLQEntry with configured ttl_ms
   - Store in _entries
   - Index by trace_id
   - Return dlq_id

5. Implement get_by_trace_id(trace_id) → List[DLQEntry]:
   - Return all entries for trace_id

6. Implement replay(dlq_id, new_recipient) → bool:
   - Lookup DLQEntry
   - Update message.receiver_id
   - Send to new mailbox (if provided)

7. Implement cleanup() (called every 100ms):
   - Remove expired entries based on _retention_ms

8. Add k1/config/mailbox_config.yml:
   - dlq_retention_ms: 86400000  # 24h default
   - dlq_max_entries: 10000
   - dlq_cleanup_interval_ms: 100

9. Add Prometheus metrics:
   - mailbox_dlq_depth gauge
   - mailbox_dlq_replay_total counter
   - mailbox_dlq_replay_errors_total counter

10. Add code header referencing ADR-0002a explicitly

11. Add comprehensive docstrings
```

**Related ADRs**: ADR-0002 (Actor Model), ADR-0002a (Mailbox MPSC Queue)

**Note**: Code header must explicitly reference ADR-0002a for cross-reference.

---

## 📋 Epic 3: Runtime Integration

**Status**: 🔴 NOT STARTED
**Duration**: 4 days (after Epics 1 & 2)
**Complexity**: VERY HIGH
**Dependencies**: Epics 1 & 2 complete

### Issue 3.1: SessionState Control (RwLock + Delta Batching)

**Title**: Implement concurrent RwLock + 250ms delta batching
**Points**: 21
**Priority**: 🔴 BLOCKER
**Owner**: AI Coder
**Depends On**: Epic 1 complete, Epic 2 complete

**Description**:
Stateful manager for SessionState with:

- RwLock allowing 100+ concurrent readers
- Serialized writes with delta computation
- 250ms batching to K0 WAL
- Lock contention monitoring

**Acceptance Criteria**:

- [ ] File: `k1/l4_runtime/session_state/control.py`
- [ ] `async read_state() → SessionState`
- [ ] `async update_state(updates: Dict) → Delta`
- [ ] Flush to K0 every 250ms or 100 deltas
- [ ] Lock acquire/release: <0.1ms P95
- [ ] Delta computation: <5ms P95
- [ ] Metrics: lock_contention, flush_latency

**Tasks**:

```
1. Create k1/l4_runtime/session_state/control.py

2. Import dependencies:
   - asyncio, time, logging
   - SessionState from model.py
   - bridge_k0/batch_client
   - Prometheus metrics

3. Define SessionStateControl class:
   - __init__(session_id: str, initial_state: SessionState = None)
   - _state: SessionState
   - _read_lock: asyncio.Lock
   - _write_lock: asyncio.Lock
   - _current_state_snapshot: SessionState
   - _pending_deltas: List[Delta] = []
   - _last_flush_ms: float = 0

4. Implement async read_state() → SessionState:
   - Acquire read_lock (non-blocking RwLock simulation)
   - Return current _state
   - Release read_lock

5. Implement async update_state(updates: Dict) → Delta:
   - Acquire write_lock
   - Merge updates into _state
   - Compute delta vs _current_state_snapshot
   - Add to _pending_deltas
   - Check if flush needed (250ms elapsed OR 100 deltas)
   - If flush needed, call flush_to_k0()
   - Release write_lock
   - Return delta

6. Implement async flush_to_k0() → Receipt:
   - Combine all _pending_deltas into batch
   - Call batch_client.submit_batch(deltas)
   - Clear _pending_deltas
   - Update _last_flush_ms
   - Update _current_state_snapshot
   - Return receipt or error

7. Implement 250ms timer:
   - Background task checking if flush needed
   - Every 250ms, if _pending_deltas not empty, flush

8. Add Prometheus metrics:
   - session_state_lock_acquire_ms histogram
   - session_state_write_queue_depth gauge
   - session_state_flush_latency_ms histogram
   - session_state_flush_batch_size histogram

9. Add error handling:
   - Retry flush with exponential backoff on failure
   - Log all errors with trace_id

10. Add comprehensive docstrings with examples
```

**Related ADRs**: ADR-0038b (K0 WAL), ADR-0045a (Event Bus)

---

### Issue 3.2: Memory Manager (3-Tier Eviction)

**Title**: Implement 3-tier memory eviction (beliefs→multimodal→scoreboard)
**Points**: 13
**Priority**: 🟡 HIGH
**Owner**: AI Coder
**Depends On**: Epic 1 complete

**Description**:
Memory pressure monitoring with progressive eviction:

- Tier 1: Evict oldest beliefs
- Tier 2: Evict oldest multimodal buffers
- Tier 3: Evict oldest scoreboard tasks

Audit every 5 seconds, thresholds: 50% (green), 70% (yellow), 90% (red), 95% (critical).

**Acceptance Criteria**:

- [ ] File: `k1/l4_runtime/session_state/memory_manager.py` (~300 lines)
- [ ] `audit_memory() → MemoryPressure`
- [ ] Tier 1 eviction if >70%
- [ ] Tier 2 eviction if >85%
- [ ] Tier 3 eviction if >95%
- [ ] Audit every 5 seconds
- [ ] Memory latency: <50ms per eviction cycle
- [ ] Metrics: evicted_bytes_total per tier

**Tasks**:

```
1. Create k1/l4_runtime/session_state/memory_manager.py

2. Define MemoryPressure enum:
   class MemoryPressure(IntEnum):
       GREEN = 0
       YELLOW = 1
       RED = 2
       CRITICAL = 3

3. Implement MemoryManager class:
   - __init__(control: SessionStateControl)
   - _control: SessionStateControl
   - _last_audit_ms: float = 0
   - _pressure_level: MemoryPressure = GREEN

4. Implement audit_memory() → MemoryPressure:
   - Get current memory usage (psutil or sys.getsizeof)
   - Calculate usage_pct
   - If >95%, return CRITICAL
   - If >70%, mark RED
   - If >50%, mark YELLOW
   - Else GREEN

5. Implement async evict_tier1():
   - Get session state
   - Sort beliefs by last_used_timestamp (LRU)
   - Remove oldest 25% of beliefs
   - Update state via control.update_state()

6. Implement async evict_tier2():
   - Get session state
   - Clear oldest multimodal buffers
   - Prefer audio > vision > text

7. Implement async evict_tier3():
   - Get session state
   - Remove oldest completed scoreboard tasks

8. Implement async monitor_loop():
   - Every 5 seconds, call audit_memory()
   - If pressure_level increased, trigger eviction
   - Log transitions

9. Add Prometheus metrics:
   - memory_pressure_level gauge
   - memory_evicted_bytes_total counter (per tier)
   - memory_audit_latency_ms histogram

10. Add error handling for memory pressure
```

**Related ADRs**: ADR-0005 (Agent Lifecycle)

---

### Issue 3.3: Integration Tests (SessionState ↔ Mailbox ↔ K0)

**Title**: End-to-end integration tests for full data flow
**Points**: 21
**Priority**: 🔴 BLOCKER
**Owner**: AI Coder
**Depends On**: Issues 3.1, 3.2

**Description**:
Integration test validating full loop:

1. Agent sends mailbox message
2. Message routed by priority
3. SessionState updated
4. Delta computed
5. K0 WAL flush (mocked)
6. Metrics emitted

**Acceptance Criteria**:

- [ ] File: `tests/l4_runtime/test_integration_session_state_mailbox.py` (~600 lines)
- [ ] ≥10 integration test cases
- [ ] Full data flow tested end-to-end
- [ ] K0 bridge mocked or stubbed
- [ ] All metrics verified
- [ ] Coverage: >90% integration paths

**Tasks**:

```
1. Create tests/l4_runtime/test_integration_session_state_mailbox.py

2. Write integration test cases:
   @test("user_message_flows_through_mailbox_to_session_state")
   @test("high_priority_message_processed_before_low_priority")
   @test("session_state_delta_batches_over_250ms")
   @test("memory_pressure_triggers_eviction")
   @test("backpressure_cascade_from_mailbox_to_k0")
   @test("concurrent_agents_send_without_race_conditions")
   @test("k0_flush_includes_all_pending_deltas")
   @test("expired_messages_routed_to_dlq")
   @test("metrics_exported_for_all_operations")
   @test("error_recovery_after_k0_failure")

3. Mock K0 bridge:
   - Mock batch_client.submit_batch()
   - Verify batch structure

4. Fixtures:
   - fixture: control (SessionStateControl instance)
   - fixture: mailbox (PriorityScheduler instance)
   - fixture: k0_mock (mocked batch_client)

5. Test data:
   - Create sample agents (A, B, C)
   - Create sample messages (URGENT, REALTIME, BACKGROUND)
   - Create sample state updates

6. Verify metrics in each test:
   - mailbox_enqueue_ms
   - session_state_delta_merge_ms
   - session_state_flush_latency_ms
   - memory_evicted_bytes_total

7. Run full test: python -m ward test --path tests/l4_runtime/test_integration_session_state_mailbox.py
```

**Related ADRs**: ADR-0038b, ADR-0061

---

### Issue 3.4: Observability (Metrics + Spans)

**Title**: Export Prometheus metrics and OpenTelemetry spans
**Points**: 13
**Priority**: 🟡 HIGH
**Owner**: AI Coder
**Depends On**: Epic 1 & 2 complete

**Description**:
Comprehensive observability for all Layer 4 components:

- Prometheus metrics for all operations
- OpenTelemetry spans for tracing
- Grafana dashboard definitions
- Structured logging with trace_id

**Acceptance Criteria**:

- [ ] ≥25 Prometheus metrics defined
- [ ] OpenTelemetry spans for critical paths
- [ ] Metrics exported to /metrics endpoint
- [ ] Structured logging in all components
- [ ] Example Grafana dashboards in `k1/dashboards/`

**Tasks**:

```
1. Create k1/l4_runtime/observability/metrics.py

2. Define Prometheus metrics:
   # SessionState
   - session_state_serialization_ms (histogram)
   - session_state_delta_merge_ms (histogram)
   - session_state_memory_bytes (gauge, per session)
   - session_state_version (gauge, per session)

   # Mailbox
   - mailbox_enqueue_ms (histogram, per priority)
   - mailbox_dequeue_ms (histogram)
   - mailbox_backpressure_events_total (counter)
   - mailbox_queue_depth (gauge, per priority)
   - mailbox_pressure_level (gauge)

   # MemoryManager
   - memory_pressure_level (gauge)
   - memory_evicted_bytes_total (counter, per tier)
   - memory_audit_latency_ms (histogram)

   # Control
   - session_state_lock_acquire_ms (histogram)
   - session_state_write_queue_depth (gauge)
   - session_state_flush_latency_ms (histogram)
   - session_state_flush_batch_size (histogram)

   # DLQ
   - mailbox_dlq_depth (gauge)
   - mailbox_dlq_replay_total (counter)
   - mailbox_dlq_replay_errors_total (counter)

3. Create k1/l4_runtime/observability/tracing.py

4. Define OpenTelemetry spans:
   - Span: orchestrator.select_agent
     └── Span: mailbox.send
         └── Span: session_state.update
             └── Span: session_state.compute_delta
             └── Span: k0_bridge.flush

5. Add structured logging:
   - Use structlog for JSON logs
   - Include trace_id, span_id in all logs
   - Log levels: DEBUG, INFO, WARN, ERROR

6. Create k1/dashboards/layer4_runtime.json:
   - Panel 1: Mailbox queue depth over time
   - Panel 2: SessionState serialization latency P95
   - Panel 3: Memory pressure level
   - Panel 4: K0 flush latency
   - Panel 5: Backpressure events rate

7. Update k1/config/logging.yaml:
   - Configure structlog formatters
   - Set log level to INFO (DEBUG in dev)

8. Verify metrics:
   - Scrape /metrics endpoint
   - Verify all metrics present
```

**Related ADRs**: ADR-0061 (Backpressure), ADR-0038b (K0 Integration)

---

## 📅 Milestone Schedule

### Milestone 1: SessionState Model Complete ✓

**Target Date**: Day 3
**Status**: PLANNED
**Issues**: 1.1, 1.2, 1.3, 1.4, 1.5

**Acceptance**:

- [ ] All SessionState code written (~400 lines)
- [ ] Serialization/deserialization working
- [ ] Delta computation accurate
- [ ] WARD tests passing (15+ tests)
- [ ] Performance budgets validated

---

### Milestone 2: Mailbox Core Complete ✓

**Target Date**: Day 6
**Status**: PLANNED
**Issues**: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6

**Acceptance**:

- [ ] MPSC queue working
- [ ] Priority scheduler routing correctly
- [ ] Backpressure watermarks enforced
- [ ] TTL cleanup running
- [ ] WARD tests passing (20+ tests)
- [ ] Dead Letter Queue functional

---

### Milestone 3: SessionState Control Complete ✓

**Target Date**: Day 9
**Status**: PLANNED
**Issues**: 3.1, 3.2

**Acceptance**:

- [ ] RwLock concurrency working
- [ ] 250ms batching to K0 functional
- [ ] Memory eviction working
- [ ] Lock contention <0.1ms
- [ ] All integration tests passing

---

### Milestone 4: Integration Testing Complete ✓

**Target Date**: Day 10
**Status**: PLANNED
**Issues**: 3.3, 3.4

**Acceptance**:

- [ ] End-to-end data flow tested
- [ ] Prometheus metrics exported
- [ ] OpenTelemetry spans working
- [ ] Grafana dashboards functional
- [ ] Structured logging in place
- [ ] All 100+ tests passing

---

### Milestone 5: Production Readiness ✓

**Target Date**: Day 12
**Status**: PLANNED

**Acceptance**:

- [ ] All ADRs cross-referenced (0002, 0004, 0005, 0011, 0012, 0038b, 0045a, 0061, 0061a)
- [ ] Performance budgets validated via benchmarks
- [ ] Code coverage: >95% for all modules
- [ ] Documentation complete (docstrings, examples)
- [ ] No simulation code (real implementations)
- [ ] Security review passed (no PII in logs)
- [ ] Ready for Layer 3 integration

---

## 📊 Dependencies Summary

```
Issue 1.1 (FlatBuffers schema)
    ↓
Issue 1.2 (SessionState model)
    ├→ Issue 1.3 (Serialization) ─────┐
    ├→ Issue 1.4 (Delta computation) ─→ Issue 1.5 (Tests)
    └→ Issue 3.1 (Control)

Issue 2.1 (MPSC queue)
    ↓
Issue 2.2 (Priority scheduler)
    ├→ Issue 2.3 (Watermarks)
    ├→ Issue 2.4 (TTL cleanup)
    └──────────────────→ Issue 2.5 (Tests)
                            ↓
Issue 2.6 (Dead Letter Queue)

Issue 3.1 + Issue 3.2 → Issue 3.3 (Integration Tests) → Issue 3.4 (Observability)
```

---

## 🎯 Success Criteria (Final Checklist)

### Code Quality

- [ ] All 15 issues completed with code
- [ ] Total lines: ~3,000 lines (models, control, mailbox, tests, observability)
- [ ] Code coverage: >95% across all modules
- [ ] No simulation code (real asyncio, FlatBuffers, prometheus)
- [ ] Type hints on 100% of functions
- [ ] Docstrings on all public APIs

### Performance

- [ ] SessionState serialization: <1ms P95 ✓
- [ ] SessionState delta merge: <10ms P95 ✓
- [ ] Mailbox enqueue: <0.5ms P95 ✓
- [ ] Mailbox dequeue: <0.5ms P95 ✓
- [ ] K0 flush: <100ms P95 (async, non-blocking) ✓
- [ ] Memory audit: <10ms P95 ✓
- [ ] All performance validated with WARD benchmarks ✓

### Testing

- [ ] Unit tests: 15+ per module (WARD framework)
- [ ] Integration tests: 10+ scenarios
- [ ] Performance benchmarks: All budgets validated
- [ ] Concurrent access tests: Race conditions eliminated
- [ ] Error path tests: >90% exception coverage

### Documentation

- [ ] Docstrings for all classes/methods
- [ ] Usage examples in docstrings
- [ ] ADR cross-references in comments
- [ ] Architecture diagrams updated
- [ ] Performance budget comments in code

### Observability

- [ ] 25+ Prometheus metrics exported
- [ ] OpenTelemetry spans implemented
- [ ] Structured logging with trace_id
- [ ] Grafana dashboards functional
- [ ] Alerts defined for critical thresholds

### Integration

- [ ] SessionState ↔ Mailbox integration working
- [ ] Mailbox ↔ K0 bridge integration (mocked)
- [ ] Backpressure cascade functional
- [ ] Memory management effective
- [ ] All metrics aggregating correctly

---

## 📚 References & Commands

### Run All Tests

```bash
python -m ward test --path tests/l4_runtime/ --verbose
```

### Run Specific Test File

```bash
python -m ward test --path tests/l4_runtime/test_session_state.py
```

### Run with Coverage

```bash
pytest --cov=k1/l4_runtime tests/l4_runtime/
```

### Run Benchmarks

```bash
python tests/l4_runtime/benchmarks/bench_session_state_serialization.py
python tests/l4_runtime/benchmarks/bench_mailbox_throughput.py
```

### Lint Code

```bash
pylint k1/l4_runtime/
mypy k1/l4_runtime/  # Type checking
```

### Generate Metrics

```bash
curl http://localhost:9090/metrics  # Prometheus endpoint
```

### Related ADRs

- ADR-0002: Actor Model (Mailbox, Supervisor)
- ADR-0004: 56-Module Microkernel (Architecture)
- ADR-0005: Agent Lifecycle FSM (State transitions)
- ADR-0011: FlatBuffers Message Schema
- ADR-0012: FlatBuffers Implementation
- ADR-0038b: K0 WAL Integration
- ADR-0045a: K1 Event Bus
- ADR-0061: Backpressure Cascade
- ADR-0061a: Watermark Thresholds

---

**Status**: ✅ PLAN COMPLETE
**Total Work**: ~3,000 lines of code + 500+ tests
**Ready for**: AI Coder implementation (10 working days)
