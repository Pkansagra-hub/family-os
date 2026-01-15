# R8 Event Emitter — Complete Deep Dive

> **Pipeline:** P03 Consolidation
> **Phase:** R8 (Event Emission & Completion)
> **Location:** `k0/pipelines/p03/phases/r8_event_emitter.py`
> **Last Updated:** 2026-01-10

---

## Table of Contents

1. [Overview](#1-overview)
2. [R8 in the Pipeline Context](#2-r8-in-the-pipeline-context)
3. [Core Files & Dependencies](#3-core-files--dependencies)
4. [Step-by-Step Execution Flow](#4-step-by-step-execution-flow)
5. [Data Structures](#5-data-structures)
6. [Event Topics](#6-event-topics)
7. [Completion Payload Schema](#7-completion-payload-schema)
8. [Gap Emission (P06 Integration)](#8-gap-emission-p06-integration)
9. [Offset Commit (Exactly-Once)](#9-offset-commit-exactly-once)
10. [Circuit Breaker](#10-circuit-breaker)
11. [Outbox Pattern](#11-outbox-pattern)
12. [Configuration](#12-configuration)
13. [Error Handling](#13-error-handling)
14. [ASCII Architecture Diagram](#14-ascii-architecture-diagram)
15. [Summary](#15-summary)

---

## 1. Overview

**R8 (Event Emitter)** is the **final phase** of the P03 Consolidation Pipeline. It completes the consolidation cycle by emitting events to notify downstream consumers and committing the processing offset.

### Key Responsibilities

1. **Build completion payload** with cycle statistics
2. **Emit consolidation events** (complete, pattern, truth, memory)
3. **Persist detected gaps** to `st_learning_queue` for P06
4. **Stage gap events** (`p03.gap.detected.v1`) to outbox
5. **Commit offset** for exactly-once processing guarantee
6. **Signal outbox drain** for async event publication

### Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Exactly-Once** | Offset commit with idempotency fingerprint |
| **Durability** | Events staged to outbox within UoW transaction |
| **Recoverability** | R8 errors can retry without re-running R0-R7 |
| **Decoupling** | Outbox pattern separates write from publish |
| **Rate Limiting** | Circuit breaker prevents cascade failure |

### TIMESTAMP CONVENTION (LOCKED)

All `*_ts` and `*_ms` fields use **MILLISECONDS** since Unix epoch.

---

## 2. R8 in the Pipeline Context

```
┌─────────────────────────────────────────────────────────────────┐
│                    P03 CONSOLIDATION PIPELINE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐          │
│  │  R0  │──▶│  R1  │──▶│  R2  │──▶│  R3  │──▶│  R4  │          │
│  │BATCH │   │SCORE │   │CLUST │   │DEDUP │   │  KG  │          │
│  └──────┘   └──────┘   └──────┘   └──────┘   └──────┘          │
│                                                 │                │
│                                                 ▼                │
│                                    ┌──────┐   ┌──────┐          │
│                                    │  R5  │──▶│  R6  │          │
│                                    │DREAM │   │STAGE │          │
│                                    └──────┘   └──────┘          │
│                                                 │                │
│                                                 ▼                │
│                                            ┌──────┐             │
│                                            │  R7  │             │
│                                            │WRITE │             │
│                                            └──────┘             │
│                                                 │                │
│                                                 ▼                │
│                                           ╔══════════╗          │
│                                           ║    R8    ║          │
│                                           ║   EMIT   ║◀── YOU   │
│                                           ╚══════════╝    HERE  │
│                                                 │                │
│                                                 ▼                │
│                                          [CYCLE DONE]           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Phase Execution Order

```python
# From runner_contract.py
P03PhaseId.execution_order() = (
    R0_INIT,    # Batch Selection
    R1_SCORE,   # Importance Scoring
    R2_CLUSTER, # Episodic Clustering
    R3_PRUNE,   # Dedup & Decay
    R4_KG,      # Knowledge Graph
    R5_DREAM,   # Dream Exploration (optional)
    R6_STAGE,   # Staging Table Updates
    R7_WRITE,   # Truth Writer
    R8_EMIT,    # Event Emission (THIS PHASE)
)
```

### R8 Input/Output

| Direction | Data |
|-----------|------|
| **Input** | `P03BatchEnvelope` with all phase outputs (R0-R7) |
| **Output** | `P03PhaseResult` with emission statistics |
| **Side Effects** | Outbox events staged, offset committed, gaps persisted |

### Recoverability Note

R8 is **recoverable** after R7 success. If R8 fails, it can be retried independently because:
- R7 has already committed truth writes
- Outbox events are idempotent via fingerprint
- Offset commit is an upsert (safe to retry)

---

## 3. Core Files & Dependencies

### Primary File

```
k0/pipelines/p03/phases/r8_event_emitter.py (725 lines)
```

### Module Structure

```
k0/
├── pipelines/p03/phases/
│   └── r8_event_emitter.py             # Phase entry point
│
├── pipelines/p03/
│   └── gap_emitter.py                  # Base gap emitter
│
├── modules/consolidation/emission/
│   ├── __init__.py
│   ├── emitter.py                      # EventEmitter (M5)
│   └── gap_emitter.py                  # GapEmitterModule (M5)
│
└── storage/
    ├── outbox.py                       # OutboxEntry model
    └── offsets.py                      # Offset model
```

### Direct Imports in r8_event_emitter.py

| File | Classes/Functions Imported |
|------|---------------------------|
| `k0/modules/consolidation/emission/emitter.py` | `EventEmitter`, `CircuitBreakerConfig` |
| `k0/modules/consolidation/emission/gap_emitter.py` | `GapEmitterModule`, `GapEmitterConfig` |
| `k0/pipelines/p03/gap_emitter.py` | `P03GapEmitter` |
| `k0/pipelines/p03/envelope.py` | `P03BatchEnvelope` |
| `k0/pipelines/p03/phase_interface.py` | `P03PhaseResult` |
| `k0/pipelines/p03/runner_contract.py` | `P03PhaseId` |
| `k0/storage/outbox.py` | `OutboxEntry` |
| `k0/storage/offsets.py` | `Offset` |

### Feature Flags

```python
# r8_event_emitter.py
USE_M5_EMITTERS = False  # Toggle for M5 EventEmitter vs Legacy inline
```

When `USE_M5_EMITTERS = True`, R8 uses modular `EventEmitter` + `GapEmitterModule`.
When `False` (default), R8 uses legacy inline methods for rollback safety.

---

## 4. Step-by-Step Execution Flow

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         R8 EXECUTION                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. BUILD COMPLETION PAYLOAD                                    │
│     ├── Determine overall status (SUCCESS/PARTIAL/FAILED)      │
│     ├── Aggregate statistics from R1-R7                         │
│     ├── Collect phase durations                                 │
│     └── Collect errors from observability context               │
│                          │                                       │
│                          ▼                                       │
│  2. OPEN UNIT OF WORK                                           │
│     ├── async with ctx.syscalls.unit_of_work() as uow:          │
│     └── All operations in same transaction                      │
│                          │                                       │
│                          ▼                                       │
│  3. EMIT COMPLETION EVENT                                       │
│     ├── Topic: p03.consolidation.complete.v1                    │
│     ├── Fingerprint: complete:{cycle_id}                        │
│     └── Stage to st_outbox                                      │
│                          │                                       │
│                          ▼                                       │
│  4. EMIT ACTION-BASED EVENTS (M5 path)                          │
│     ├── p03.truth.reinforced.v1 (if REINFORCE count > 0)        │
│     ├── p03.pattern.detected.v1 (if st_sem creates > 0)         │
│     ├── p03.truth.created.v1 (if non-sem creates > 0)           │
│     ├── p03.truth.evolved.v1 (if EVOLVE count > 0)              │
│     └── p03.memory.pruned.v1 (if PRUNE count > 0)               │
│                          │                                       │
│                          ▼                                       │
│  5. PROCESS GAPS (P06 Integration)                              │
│     ├── Sort by priority (CONTRADICTION first)                  │
│     ├── Deduplicate within cycle                                │
│     ├── Cap to max_gaps_per_cycle (50)                          │
│     ├── Persist to st_learning_queue                            │
│     └── Stage p03.gap.detected.v1 to outbox                     │
│                          │                                       │
│                          ▼                                       │
│  6. COMMIT OFFSET                                               │
│     ├── Upsert into st_offsets                                  │
│     ├── subscriber_id = "p03"                                   │
│     └── offset = max event_id (ULID timestamp prefix)           │
│                          │                                       │
│                          ▼                                       │
│  7. UoW COMMIT                                                  │
│     ├── All outbox entries atomically committed                 │
│     └── Offset update atomically committed                      │
│                          │                                       │
│                          ▼                                       │
│  8. TRIGGER OUTBOX DRAIN (async, non-blocking)                  │
│     └── Background worker will publish events to bus            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### M5 vs Legacy Flow

| Step | M5 (`USE_M5_EMITTERS=True`) | Legacy (`USE_M5_EMITTERS=False`) |
|------|------------------------------|----------------------------------|
| Event Emission | `EventEmitter.emit_all()` | `_stage_completion_event()` inline |
| Gap Emission | `GapEmitterModule.emit()` | `_process_gaps()` with `P03GapEmitter` |
| Result Tracking | `EmitResult` dataclass | Manual counters |
| Circuit Breaker | Built into EventEmitter | Not available |

---

## 5. Data Structures

### P03PhaseResult (Output)

```python
@dataclass
class P03PhaseResult:
    phase_id: P03PhaseId
    status: P03PhaseStatus  # DONE, FAIL, SKIP
    duration_ms: int
    outputs_summary: Dict[str, Any]
    error: Optional[P03Error] = None
    idempotency_key: Optional[str] = None

    @classmethod
    def done(cls, phase_id, duration_ms, outputs_summary, idempotency_key) -> P03PhaseResult:
        """Create successful result."""
        ...

    @classmethod
    def fail(cls, phase_id, error, duration_ms, idempotency_key) -> P03PhaseResult:
        """Create failure result."""
        ...
```

### EmitResult (M5)

```python
@dataclass
class EmitResult:
    """Result of event emission."""
    total_emitted: int = 0
    by_topic: Dict[str, int] = field(default_factory=dict)
    failed: List[str] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def success(self) -> bool:
        return len(self.failed) == 0
```

### GapEmitStats (M5)

```python
@dataclass
class GapEmitStats:
    """Statistics from gap emission."""
    total_received: int = 0
    emitted: int = 0
    deduplicated: int = 0
    capped: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    by_priority: Dict[int, int] = field(default_factory=dict)
    duration_ms: int = 0

    @property
    def skipped(self) -> int:
        return self.deduplicated + self.capped
```

### GapType Enum

```python
class GapType(Enum):
    """Gap types for P06 active learning."""
    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"      # Multiple candidates match
    LOW_CONFIDENCE_EDGE = "LOW_CONFIDENCE_EDGE"  # KG edge below threshold
    MISSING_ATTRIBUTE = "MISSING_ATTRIBUTE"      # Expected attribute missing
    CONTRADICTION = "CONTRADICTION"              # Conflicting information
    CONCEPT_DRIFT = "CONCEPT_DRIFT"              # Entity meaning shifted
    STRUCTURAL_HOLE = "STRUCTURAL_HOLE"          # Missing cluster bridge
    STALE_ANCHOR = "STALE_ANCHOR"                # Anchor needs refresh
```

---

## 6. Event Topics

### P03 Event Topics (Dossier §4.9.1)

| Topic | Description | Trigger | Priority |
|-------|-------------|---------|----------|
| `p03.consolidation.complete.v1` | Cycle completion summary | Every successful cycle | Always |
| `p03.pattern.detected.v1` | New semantic pattern found | CREATE on st_sem | If count > 0 |
| `p03.truth.reinforced.v1` | Existing truth reinforced | REINFORCE action | If count > 0 |
| `p03.truth.created.v1` | New truth record created | CREATE on non-sem | If count > 0 |
| `p03.truth.evolved.v1` | Truth evolved to new version | EVOLVE action | If count > 0 |
| `p03.memory.pruned.v1` | Memory archived/tombstoned | PRUNE action | If count > 0 |
| `p03.gap.detected.v1` | Gap detected for P06 | Per gap (capped) | Per gap |

### EventTopic Enum (M5)

```python
class EventTopic(Enum):
    """P03 event topics per dossier §4.9.1."""
    CONSOLIDATION_COMPLETE = "p03.consolidation.complete.v1"
    PATTERN_DETECTED = "p03.pattern.detected.v1"
    TRUTH_REINFORCED = "p03.truth.reinforced.v1"
    TRUTH_CREATED = "p03.truth.created.v1"
    TRUTH_EVOLVED = "p03.truth.evolved.v1"
    MEMORY_PRUNED = "p03.memory.pruned.v1"
```

### Event Fingerprints (Idempotency)

| Event Type | Fingerprint Pattern | Purpose |
|------------|---------------------|---------|
| Completion | `complete:{cycle_id}` | One per cycle |
| Reinforce | `reinforce_agg:{cycle_id}` | Aggregate per cycle |
| Create | `create_agg:{cycle_id}` | Aggregate per cycle |
| Pattern | `pattern_agg:{cycle_id}` | Aggregate per cycle |
| Evolve | `evolve_agg:{cycle_id}` | Aggregate per cycle |
| Prune | `prune_agg:{cycle_id}` | Aggregate per cycle |
| Gap | `gap:{gap_id}` | One per gap |

---

## 7. Completion Payload Schema

### Schema Reference

```
k0/contracts/schemas/p03_consolidation_complete.json
```

### Payload Structure

```json
{
  "cycle_id": "01HXYZ...",
  "tenant_id": "tenant_123",
  "space_id": "space_456",
  "status": "SUCCESS",
  "summary": {
    "total_events": 100,
    "consolidated_count": 85,
    "duplicate_count": 10,
    "pruned_count": 5,
    "pending_review_count": 0,
    "action_breakdown": {
      "REINFORCE": 45,
      "EXTEND": 20,
      "CREATE": 15,
      "EVOLVE": 5,
      "PRUNE": 5
    },
    "layer_write_counts": {
      "st_epi": 30,
      "st_sem": 15,
      "st_procedural": 10,
      "st_social": 5,
      "st_kg_dom": 20,
      "st_kg_edges": 35
    },
    "kg_entity_count": 20,
    "kg_edge_count": 35,
    "gap_count": 3
  },
  "duration_ms": 1250,
  "completed_at": "2026-01-10T12:30:45.123Z",
  "phase_durations": {
    "R0_INIT": 50,
    "R1_SCORE": 120,
    "R2_CLUSTER": 200,
    "R3_PRUNE": 80,
    "R4_KG": 300,
    "R5_DREAM": 0,
    "R6_STAGE": 150,
    "R7_WRITE": 300,
    "R8_EMIT": 50
  },
  "errors": []
}
```

### Status Determination

```python
def _determine_status(envelope: P03BatchEnvelope) -> str:
    """
    Determine overall cycle status.

    Returns:
        "SUCCESS" - All phases completed without errors
        "PARTIAL" - Some phases had recoverable errors
        "FAILED" - Fatal error occurred
    """
    has_failure = False
    has_success = False

    for phase_id, status in envelope.phase_statuses.items():
        if status == P03PhaseStatus.FAIL:
            has_failure = True
        elif status == P03PhaseStatus.DONE:
            has_success = True

    if has_failure and not has_success:
        return "FAILED"
    elif has_failure:
        return "PARTIAL"
    else:
        return "SUCCESS"
```

---

## 8. Gap Emission (P06 Integration)

### Gap Priority Map

| Gap Type | Priority | Description |
|----------|----------|-------------|
| `CONTRADICTION` | 100 | Conflicts block progress |
| `AMBIGUOUS_ENTITY` | 80 | Entity resolution critical |
| `STRUCTURAL_HOLE` | 70 | Data connectivity issues |
| `CONCEPT_DRIFT` | 60 | May cause stale results |
| `LOW_CONFIDENCE_EDGE` | 50 | Can often infer |
| `STALE_ANCHOR` | 40 | Needs refresh |
| `MISSING_ATTRIBUTE` | 30 | Optional enrichment |

### Gap Processing Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      GAP PROCESSING                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  INPUT: List[GapCandidate] from R4                              │
│                          │                                       │
│                          ▼                                       │
│  1. SORT BY PRIORITY                                            │
│     └── CONTRADICTION (100) first, MISSING_ATTRIBUTE (30) last  │
│                          │                                       │
│                          ▼                                       │
│  2. DEDUPLICATE                                                 │
│     ├── Key: gap_type + related_entity_id                       │
│     └── Skip duplicates within cycle                            │
│                          │                                       │
│                          ▼                                       │
│  3. CAP TO MAX                                                  │
│     └── max_gaps_per_cycle = 50 (prevent P06 overload)          │
│                          │                                       │
│                          ▼                                       │
│  4. PERSIST TO st_learning_queue                                │
│     ├── ON CONFLICT (id) DO NOTHING                             │
│     ├── status = 'PENDING'                                      │
│     ├── expires_at = now + ttl_hours                            │
│     └── max_attempts = 3                                        │
│                          │                                       │
│                          ▼                                       │
│  5. STAGE TO OUTBOX                                             │
│     ├── Topic: p03.gap.detected.v1                              │
│     ├── Driver: "p06" (target pipeline)                         │
│     └── Fingerprint: gap:{gap_id}                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Question Templates (P06)

```python
QUESTION_TEMPLATES = {
    "AMBIGUOUS_ENTITY": "Which of these best matches '{entity}'?",
    "LOW_CONFIDENCE_EDGE": "Is it true that '{source}' {relation} '{target}'?",
    "MISSING_ATTRIBUTE": "What is the {attribute} of '{entity}'?",
    "CONTRADICTION": "Which statement is correct: A) {claim_a} or B) {claim_b}?",
    "CONCEPT_DRIFT": "Has the meaning of '{entity}' changed recently?",
    "STRUCTURAL_HOLE": "How are '{entity_a}' and '{entity_b}' related?",
    "STALE_ANCHOR": "Is '{entity}' still valid/current?",
}
```

### st_learning_queue Schema

| Column | Type | Description |
|--------|------|-------------|
| `id` | `TEXT` | Gap ID (PK) |
| `tenant_id` | `TEXT` | Tenant identifier |
| `space_id` | `TEXT` | Space identifier |
| `gap_type` | `TEXT` | GapType enum value |
| `entity_id` | `TEXT` | Related entity ID |
| `confidence_score` | `FLOAT` | 1 - entropy_score |
| `entropy_score` | `FLOAT` | Uncertainty level |
| `context_json` | `TEXT` | JSON context blob |
| `status` | `TEXT` | PENDING, IN_PROGRESS, RESOLVED, EXPIRED |
| `created_at` | `BIGINT` | Creation timestamp (ms) |
| `expires_at` | `BIGINT` | Expiration timestamp (ms) |
| `attempts` | `INT` | P06 attempts count |
| `max_attempts` | `INT` | Max attempts (default: 3) |
| `consolidation_cycle_id` | `TEXT` | Source cycle ID |

---

## 9. Offset Commit (Exactly-Once)

### Purpose

The offset marks the **high watermark** of processed events. On restart, P03 resumes from this offset, ensuring exactly-once processing.

### Offset Commit Logic

```python
async def _commit_offset(
    self,
    uow: UnitOfWork,
    envelope: P03BatchEnvelope,
) -> None:
    """
    Commit offset for exactly-once processing.

    The offset is derived from the maximum event_id (ULID) processed.
    ULID first 10 characters encode the timestamp in base32.
    """
    if not envelope.events:
        return  # No events processed

    # Get max event_id (ULIDs are lexicographically sortable)
    max_event_id = max(e.event_id for e in envelope.events)

    # Convert ULID timestamp prefix to integer offset
    try:
        offset_value = int(max_event_id[:10], 32)
    except ValueError:
        offset_value = hash(max_event_id)

    offset_record = Offset(
        subscriber_id="p03",
        topic="p02.hipp_events",
        space_id=envelope.context.space_id,
        tenant_id=envelope.context.tenant_id,
        offset=offset_value,
        updated_ts=datetime.now(timezone.utc).isoformat(),
    )

    await uow.upsert_offset(offset_record)
```

### Offset Record Structure

```python
@dataclass
class Offset:
    subscriber_id: str    # "p03"
    topic: str            # "p02.hipp_events"
    space_id: str
    tenant_id: str
    offset: int           # ULID timestamp as integer
    updated_ts: str       # ISO8601 timestamp
```

### Resume Behavior

On pipeline restart:
1. R0 queries `st_offsets` for `subscriber_id="p03"`
2. Fetches events from `st_hipp_events` WHERE `wal_pos > offset`
3. Processes only events after the committed offset

---

## 10. Circuit Breaker

### Purpose

Prevents cascade failure when the event bus is unavailable.

### CircuitBreakerConfig

```python
@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5       # Failures before opening
    reset_timeout_ms: int = 60000    # 1 minute before retry
    queue_on_failure: bool = True    # Queue events on outage
```

### Circuit States

| State | Description | Behavior |
|-------|-------------|----------|
| **Closed** | Normal operation | Events staged normally |
| **Open** | Too many failures | Events skipped with warning |
| **Half-Open** | Reset timeout elapsed | Next event tests circuit |

### Circuit Logic

```python
def _is_circuit_open(self) -> bool:
    """Check circuit breaker state."""
    if self._failures < self._circuit_config.failure_threshold:
        return False  # Closed

    now_ms = _now_ms()
    if now_ms - self._last_failure_ms > self._circuit_config.reset_timeout_ms:
        self._failures = 0  # Reset to half-open
        return False

    return True  # Open

async def _stage_event(self, uow, topic, payload, ...):
    if self._is_circuit_open():
        result.failed.append(fingerprint)
        logger.warning("Circuit open, skipping event")
        return

    try:
        uow.stage_outbox(entry)
        self._failures = 0  # Reset on success
    except Exception:
        self._failures += 1
        self._last_failure_ms = _now_ms()
```

---

## 11. Outbox Pattern

### Why Outbox?

The transactional outbox pattern ensures events are **durably staged** before publishing:

1. Events written to `st_outbox` within R8's UoW transaction
2. Background worker polls `st_outbox` and publishes to event bus
3. On publish success, outbox entry marked as processed
4. Fingerprint prevents duplicate emissions on retry

### OutboxEntry Structure

```python
@dataclass
class OutboxEntry:
    id: Optional[int]      # Auto-assigned by database
    wal_pos: int           # Write-ahead log position
    tenant_id: str
    space_id: str
    driver: str            # "p03" or "p06"
    op_kind: str           # Event topic
    payload: bytes         # JSON-encoded payload
    fingerprint: str       # Idempotency key
    requeue_seq: int       # Requeue count
    retries: int           # Retry count
```

### Outbox Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                     OUTBOX LIFECYCLE                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. STAGE (R8)                                                  │
│     ├── uow.stage_outbox(entry)                                 │
│     └── Entry buffered in UoW                                   │
│                          │                                       │
│                          ▼                                       │
│  2. COMMIT (R8)                                                 │
│     ├── UoW._flush_outbox() inserts to st_outbox                │
│     └── ON CONFLICT (fingerprint) DO NOTHING                    │
│                          │                                       │
│                          ▼                                       │
│  3. POLL (Background Worker)                                    │
│     ├── SELECT * FROM st_outbox WHERE status = 'PENDING'        │
│     └── ORDER BY created_at ASC LIMIT batch_size                │
│                          │                                       │
│                          ▼                                       │
│  4. PUBLISH (Background Worker)                                 │
│     ├── Publish payload to event bus topic                      │
│     └── Mark entry as 'DONE' on success                         │
│                          │                                       │
│                          ▼                                       │
│  5. CLEANUP (Background Worker)                                 │
│     └── DELETE FROM st_outbox WHERE status = 'DONE'             │
│         AND created_at < retention_cutoff                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 12. Configuration

### R8EventEmitter Configuration

| Config | Default | Description |
|--------|---------|-------------|
| `USE_M5_EMITTERS` | `False` | Use M5 modular emitters |
| `COMPLETION_TOPIC` | `p03.consolidation.complete.v1` | Completion event topic |
| `GAP_TOPIC` | `p03.gap.detected.v1` | Gap event topic |

### EventEmitter (M5) Configuration

| Config | Default | Description |
|--------|---------|-------------|
| `failure_threshold` | `5` | Circuit breaker threshold |
| `reset_timeout_ms` | `60000` | Circuit reset timeout (1 min) |
| `queue_on_failure` | `True` | Queue events when bus down |

### GapEmitterModule (M5) Configuration

| Config | Default | Description |
|--------|---------|-------------|
| `topic` | `p03.gap.detected.v1` | Gap event topic |
| `max_gaps_per_cycle` | `50` | Cap per cycle |
| `ttl_hours` | `168` | Gap TTL (7 days) |
| `deduplicate` | `True` | Enable deduplication |
| `dedup_window_ms` | `3600000` | Dedup window (1 hour) |
| `emit_to_outbox` | `True` | Stage to outbox |
| `persist_to_queue` | `True` | Persist to st_learning_queue |

### P03GapEmitter (Legacy) Configuration

| Config | Default | Description |
|--------|---------|-------------|
| `topic` | `p03.gap.detected.v1` | Gap event topic |
| `deduplicate` | `True` | Enable deduplication |
| `dedup_window_ms` | `3600000` | Dedup window (1 hour) |
| `default_expires_ms` | `604800000` | Gap TTL (7 days) |
| `max_attempts` | `3` | P06 max attempts |

---

## 13. Error Handling

### Error Categories

| Error | Cause | Handling |
|-------|-------|----------|
| `R8_EMISSION_ERROR` | Event staging failed | Recoverable, retry R8 |
| Circuit Open | Too many bus failures | Skip events with warning |
| Offset Commit Failure | Database error | Retry transaction |
| Gap Persist Failure | st_learning_queue error | Continue with other gaps |

### Error Result

```python
return P03PhaseResult.fail(
    phase_id=self.PHASE_ID,
    error=P03Error(
        error_id=f"r8-{cycle_id}",
        phase="R8",
        stage_id="event_emitter",
        error_type="R8_EMISSION_ERROR",
        error_message=str(e),
        recoverable=True,  # R8 can retry after R7 success
    ),
    duration_ms=duration_ms,
    idempotency_key=f"p03:r8:{cycle_id}",
)
```

### Recoverability

R8 is marked as **recoverable** because:
1. R7 has already committed truth writes (durable)
2. Outbox entries use fingerprints (idempotent)
3. Offset is an upsert (safe to retry)
4. Gaps use ON CONFLICT DO NOTHING (idempotent)

---

## 14. ASCII Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              R8 EVENT EMITTER                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │                         INPUT FROM R7                                   │     │
│  │  P03BatchEnvelope with:                                                │     │
│  │    ├── phases.r6_summary: ReconciliationSummary                        │     │
│  │    ├── phases.r4_gap_candidates: List[GapCandidate]                    │     │
│  │    ├── phases.r7_result: WriteResult                                   │     │
│  │    └── phase_statuses: Dict[P03PhaseId, P03PhaseStatus]                │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│                                      │                                           │
│                                      ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │                         UNIT OF WORK                                    │     │
│  │                                                                         │     │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │     │
│  │  │                   EVENT EMITTER (M5)                            │   │     │
│  │  │                                                                  │   │     │
│  │  │  ┌────────────────────────────────────────────────────────────┐ │   │     │
│  │  │  │ COMPLETION EVENT (always)                                  │ │   │     │
│  │  │  │ └─▶ p03.consolidation.complete.v1                          │ │   │     │
│  │  │  └────────────────────────────────────────────────────────────┘ │   │     │
│  │  │                                                                  │   │     │
│  │  │  ┌────────────────────────────────────────────────────────────┐ │   │     │
│  │  │  │ ACTION EVENTS (if count > 0)                               │ │   │     │
│  │  │  │ ├─▶ p03.truth.reinforced.v1     (REINFORCE)               │ │   │     │
│  │  │  │ ├─▶ p03.pattern.detected.v1     (CREATE st_sem)           │ │   │     │
│  │  │  │ ├─▶ p03.truth.created.v1        (CREATE other)            │ │   │     │
│  │  │  │ ├─▶ p03.truth.evolved.v1        (EVOLVE)                  │ │   │     │
│  │  │  │ └─▶ p03.memory.pruned.v1        (PRUNE)                   │ │   │     │
│  │  │  └────────────────────────────────────────────────────────────┘ │   │     │
│  │  │                                                                  │   │     │
│  │  │  ┌──────────────────────────────────────────────────────────┐   │   │     │
│  │  │  │ CIRCUIT BREAKER                                          │   │   │     │
│  │  │  │ └─▶ failure_threshold=5, reset_timeout=60s               │   │   │     │
│  │  │  └──────────────────────────────────────────────────────────┘   │   │     │
│  │  └─────────────────────────────────────────────────────────────────┘   │     │
│  │                                                                         │     │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │     │
│  │  │                 GAP EMITTER MODULE (M5)                         │   │     │
│  │  │                                                                  │   │     │
│  │  │  INPUT: gaps from R4 ──▶ SORT ──▶ DEDUP ──▶ CAP ──▶ EMIT       │   │     │
│  │  │                         (priority) (key)   (50)                  │   │     │
│  │  │                                                                  │   │     │
│  │  │  PERSIST: st_learning_queue (for P06)                           │   │     │
│  │  │  STAGE: p03.gap.detected.v1 (outbox)                            │   │     │
│  │  └─────────────────────────────────────────────────────────────────┘   │     │
│  │                                                                         │     │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │     │
│  │  │                   OFFSET COMMIT                                  │   │     │
│  │  │  uow.upsert_offset(subscriber="p03", offset=max_event_id)       │   │     │
│  │  └─────────────────────────────────────────────────────────────────┘   │     │
│  │                                                                         │     │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │     │
│  │  │                   OUTBOX STAGING                                 │   │     │
│  │  │  st_outbox ◀── All events with fingerprints                     │   │     │
│  │  └─────────────────────────────────────────────────────────────────┘   │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│                                      │                                           │
│                                      ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │                    OUTBOX DRAIN SIGNAL                                  │     │
│  │  └─▶ Background worker publishes events to bus                        │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│                                      │                                           │
│                                      ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │                         OUTPUT                                          │     │
│  │  P03PhaseResult                                                        │     │
│  │    ├── status: DONE                                                    │     │
│  │    ├── duration_ms: int                                                │     │
│  │    └── outputs_summary:                                                │     │
│  │          ├── events_emitted: int                                       │     │
│  │          ├── events_by_topic: Dict[str, int]                           │     │
│  │          ├── gaps_emitted: int                                         │     │
│  │          ├── gaps_deduplicated: int                                    │     │
│  │          └── gaps_capped: int                                          │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Downstream Consumers

```
                        ┌──────────────────────────────────────────┐
                        │              EVENT BUS                    │
                        └────────────────────┬─────────────────────┘
                                             │
         ┌───────────────────────────────────┼───────────────────────────────────┐
         │                                   │                                   │
         ▼                                   ▼                                   ▼
┌────────────────────┐           ┌────────────────────┐            ┌────────────────────┐
│   P06 Active       │           │   P08 Embedding    │            │   External         │
│   Learning         │           │   Index            │            │   Consumers        │
│                    │           │                    │            │                    │
│ ◀── gap.detected   │           │ ◀── pattern.*     │            │ ◀── complete.*    │
│                    │           │ ◀── truth.*       │            │ ◀── truth.*       │
└────────────────────┘           └────────────────────┘            └────────────────────┘
```

---

## 15. Summary

### R8 at a Glance

| Aspect | Description |
|--------|-------------|
| **Phase** | R8 Event Emitter |
| **Purpose** | Emit events, commit offset, complete cycle |
| **Input** | `P03BatchEnvelope` with all phase outputs |
| **Output** | `P03PhaseResult` with emission statistics |
| **Tables** | st_outbox, st_offsets, st_learning_queue |
| **Events** | 7 topics (complete, pattern, truth×3, memory, gap) |
| **Transaction** | Single UoW with all operations |
| **Idempotency** | Fingerprints for all outbox entries |
| **Recoverability** | Can retry independently of R0-R7 |

### Key Design Decisions

1. **Outbox Pattern**: Events staged atomically with offset commit
2. **Exactly-Once**: Offset marks high watermark for resume
3. **Gap Priority**: CONTRADICTION (100) processed before MISSING_ATTRIBUTE (30)
4. **Gap Capping**: Max 50 gaps per cycle to prevent P06 overload
5. **Circuit Breaker**: Prevents cascade failure when bus unavailable
6. **M5 Modularity**: Separate emitters for events and gaps

### Files Summary

| File | Lines | Purpose |
|------|-------|---------|
| [r8_event_emitter.py](../../k0/pipelines/p03/phases/r8_event_emitter.py) | 725 | Phase entry point |
| [emitter.py](../../k0/modules/consolidation/emission/emitter.py) | 545 | M5 EventEmitter |
| [gap_emitter.py](../../k0/modules/consolidation/emission/gap_emitter.py) | 461 | M5 GapEmitterModule |
| [gap_emitter.py](../../k0/pipelines/p03/gap_emitter.py) | 480 | Base P03GapEmitter |

### Event Topics Quick Reference

| Topic | Fingerprint | When Emitted |
|-------|-------------|--------------|
| `p03.consolidation.complete.v1` | `complete:{cycle_id}` | Every cycle |
| `p03.pattern.detected.v1` | `pattern_agg:{cycle_id}` | CREATE on st_sem |
| `p03.truth.reinforced.v1` | `reinforce_agg:{cycle_id}` | REINFORCE action |
| `p03.truth.created.v1` | `create_agg:{cycle_id}` | CREATE (non-sem) |
| `p03.truth.evolved.v1` | `evolve_agg:{cycle_id}` | EVOLVE action |
| `p03.memory.pruned.v1` | `prune_agg:{cycle_id}` | PRUNE action |
| `p03.gap.detected.v1` | `gap:{gap_id}` | Per detected gap |

---

*Document generated: 2026-01-10*
*Source: k0/pipelines/p03/phases/r8_event_emitter.py and k0/modules/consolidation/emission/*
