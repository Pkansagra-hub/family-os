# R0 Batch Selector — Complete Deep Dive

> **Pipeline:** P03 Consolidation
> **Phase:** R0 (Entry Point)
> **Location:** `k0/pipelines/p03/phases/r0_batch_selector.py`
> **Last Updated:** 2026-01-09

---

## Table of Contents

1. [Overview](#1-overview)
2. [R0 in the Pipeline Context](#2-r0-in-the-pipeline-context)
3. [Core Files & Dependencies](#3-core-files--dependencies)
4. [Step-by-Step Execution Flow](#4-step-by-step-execution-flow)
5. [Data Structures](#5-data-structures)
6. [Database Tables Accessed](#6-database-tables-accessed)
7. [Algorithms & Helper Functions](#7-algorithms--helper-functions)
8. [Gap Auto-Resolution](#8-gap-auto-resolution)
9. [Configuration](#9-configuration)
10. [Error Handling](#10-error-handling)
11. [Code Walkthrough](#11-code-walkthrough)

---

## 1. Overview

**R0 (Batch Selector)** is the **entry point** for the P03 Consolidation Pipeline. Unlike phases R1-R8 which receive an envelope, **R0 CREATES the envelope**.

### Key Responsibilities

1. **Fetch current offset** from `st_offsets` (via OffsetStore)
2. **Query eligible events** from `st_hipp_events` after offset
3. **Load embeddings** from `st_vec` for selected events (lazy materialization)
4. **Auto-resolve pending gaps** from user context (non-blocking)
5. **Build P03BatchEnvelope** with context and events
6. **Return envelope** for R1-R8 processing

### Signature Difference

| Phase | Signature |
|-------|-----------|
| **R0** | `run(tenant_id, space_id, ctx) -> (envelope, result)` |
| **R1-R8** | `run(envelope, ctx) -> result` |

---

## 2. R0 in the Pipeline Context

```
┌─────────────────────────────────────────────────────────────────┐
│                    P03 CONSOLIDATION PIPELINE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐          │
│  │  R0  │──▶│  R1  │──▶│  R2  │──▶│  R3  │──▶│  R4  │          │
│  │BATCH │   │SCORE │   │CLUST │   │DEDUP │   │  KG  │          │
│  └──────┘   └──────┘   └──────┘   └──────┘   └──────┘          │
│      │                                            │              │
│      │         Creates Envelope                   ▼              │
│      │                              ┌──────┐   ┌──────┐         │
│      └─────────────────────────────▶│  R6  │──▶│  R7  │         │
│                                     │STAGE │   │WRITE │         │
│                                     └──────┘   └──────┘         │
│                                                    │             │
│                                                    ▼             │
│                                               ┌──────┐          │
│                                               │  R8  │          │
│                                               │ EMIT │          │
│                                               └──────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### Phase Execution Order

```python
# From runner_contract.py
P03PhaseId.execution_order() = (
    R0_INIT,    # Batch Selection (THIS PHASE)
    R1_SCORE,   # Importance Scoring
    R2_CLUSTER, # Episodic Clustering
    R3_PRUNE,   # Dedup & Decay
    R4_KG,      # Knowledge Graph
    R5_DREAM,   # Dream Exploration (optional)
    R6_STAGE,   # Staging
    R7_WRITE,   # Truth Writer
    R8_EMIT,    # Event Emission
)
```

---

## 3. Core Files & Dependencies

### Primary File

```
k0/pipelines/p03/phases/r0_batch_selector.py (845 lines)
```

### Direct Imports

| File | Classes/Functions Imported |
|------|---------------------------|
| `k0/modules/consolidation/gap_auto_resolver.py` | `GapAutoResolver` |
| `k0/pipelines/p03/checkpoint.py` | `P03_SOURCE_TOPIC`, `P03_SUBSCRIBER_ID` |
| `k0/pipelines/p03/context.py` | `P03CycleContext` |
| `k0/pipelines/p03/envelope.py` | `P03BatchEnvelope` |
| `k0/pipelines/p03/event_state.py` | `P03EventState` |
| `k0/pipelines/p03/observability.py` | `P03Error` |
| `k0/pipelines/p03/phase_interface.py` | `P03PhaseResult` |
| `k0/pipelines/p03/runner_contract.py` | `P03PhaseId` |

### Module Wrapper

```
k0/modules/consolidation/batch_selector.py
```

This wraps R0BatchSelector for the module registry interface.

---

## 4. Step-by-Step Execution Flow

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         R0 EXECUTION                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. FETCH OFFSET                                                │
│     ├── Query st_offsets table                                  │
│     ├── subscriber_id = "P03_CONSOLIDATE"                       │
│     ├── topic = "st_hipp_events"                                │
│     └── Returns: current_offset (int, 0 if none)                │
│                          │                                       │
│                          ▼                                       │
│  2. FETCH ELIGIBLE EVENTS                                       │
│     ├── Query st_hipp_events WHERE:                             │
│     │   ├── wal_pos > current_offset                            │
│     │   ├── consolidation_status IS NULL OR 'PENDING'           │
│     │   ├── embedding_status = 'READY'                          │
│     │   └── archival_status IS NULL                             │
│     ├── ORDER BY wal_pos ASC                                    │
│     └── LIMIT batch_size (default: 100)                         │
│                          │                                       │
│                          ▼                                       │
│  3. HANDLE EMPTY BATCH                                          │
│     └── If no events → Return (None, SKIP result)               │
│                          │                                       │
│                          ▼                                       │
│  4. LOAD EMBEDDINGS                                             │
│     ├── Query st_vec for event_ids                              │
│     ├── Unpack binary vectors (768 floats × 4 bytes)            │
│     └── Call event.materialize_embedding(vector)                │
│                          │                                       │
│                          ▼                                       │
│  5. GAP AUTO-RESOLUTION (non-blocking)                          │
│     ├── Extract NER entities from events                        │
│     ├── Load pending AMBIGUOUS_ENTITY gaps                      │
│     ├── Match entities to gaps via similarity                   │
│     └── Auto-resolve high-confidence matches                    │
│                          │                                       │
│                          ▼                                       │
│  6. FILTER EVENTS WITHOUT EMBEDDINGS                            │
│     └── Remove events where embedding_768 is None               │
│                          │                                       │
│                          ▼                                       │
│  7. BUILD ENVELOPE                                              │
│     ├── Create P03CycleContext (immutable)                      │
│     ├── Create P03BatchEnvelope with events                     │
│     └── Return (envelope, DONE result)                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Data Structures

### R0Config (Configuration)

```python
@dataclass
class R0Config:
    """R0 phase configuration."""

    batch_size: int = 100
    # Maximum events per batch

    require_embedding_ready: bool = True
    # Only include events with embedding_status='READY'

    exclude_archived: bool = True
    # Exclude events with archival_status set

    max_age_hours: int = 0
    # Maximum age of events to consider (0 = no limit)
```

### P03EventState (Per-Event State)

R0 creates this from each `st_hipp_events` row:

```python
@dataclass
class P03EventState:
    # === IDENTIFICATION (R0) ===
    event_id: str
    hipp_event_id: str = ""

    # === CONTENT (R0) ===
    content_text: str = ""
    content_type: str = ""
    simhash_hex: str = ""
    timestamp: int = 0  # milliseconds
    channel_id: str = ""

    # === PRE-COMPUTED NLP (R0) ===
    embedding_id: str = ""
    embedding_768: Optional[List[float]] = None  # Loaded from st_vec
    sentiment_score: float = 0.0
    sentiment_label: str = "neutral"
    emotions_json: str = "[]"
    intent_label: str = ""
    ner_entities_json: str = "[]"
    temporal_expressions_json: str = "[]"

    # === SOCIAL CONTEXT (R0) ===
    participants_json: str = "[]"
    num_participants: int = 0
    social_context: str = ""
    social_intimacy: str = ""
    location_name: str = ""
    location_type: str = ""
    activity_type: str = ""
    actor_id: str = ""
```

### P03CycleContext (Immutable Batch Context)

```python
@dataclass(frozen=True)
class P03CycleContext:
    # === IDENTIFICATION ===
    cycle_id: str      # ULID - unique per cycle
    batch_id: str      # SHA256[:16] of sorted event_ids
    tenant_id: str
    space_id: str
    trace_id: str      # Cognitive trace ID for observability

    # === TRIGGER CONTEXT ===
    trigger_type: str  # INTERVAL / THRESHOLD / MANUAL / IDLE
    trigger_reason: str
    triggered_at: int  # MILLISECONDS since epoch

    # === BATCH METADATA ===
    batch_size: int    # INVARIANT: == len(event_ids)
    event_ids: Tuple[str, ...]  # Sorted, deduplicated, immutable
    pending_before: int

    # === SCHEDULER CONTEXT ===
    scheduler_token: Optional[str] = None
    qos_band: str = "AMBER"  # GREEN / AMBER / RED
    priority: int = 50       # 0-100
    deadline_ms: int = 300000  # 5 minutes default
```

### P03BatchEnvelope (Top-Level Container)

```python
@dataclass
class P03BatchEnvelope:
    # === IMMUTABLE CONTEXT (set in R0) ===
    context: P03CycleContext

    # === MUTABLE PER-EVENT STATE ===
    events: List[P03EventState]

    # === PHASE OUTPUTS (populated incrementally) ===
    phases: P03PhaseOutputs

    # === STAGED WRITES (accumulated, committed in R7) ===
    staged: P03StagedWrites

    # === OBSERVABILITY ===
    observability: P03ObservabilityContext

    # === STATE TRACKING ===
    current_phase: P03PhaseId
    phase_statuses: Dict[P03PhaseId, P03PhaseStatus]
```

---

## 6. Database Tables Accessed

### st_offsets (READ)

```sql
-- Fetch current offset
SELECT offset
FROM st_offsets
WHERE subscriber_id = 'P03_CONSOLIDATE'
  AND topic = 'st_hipp_events'
  AND space_id = $1
  AND tenant_id = $2
```

| Column | Type | Description |
|--------|------|-------------|
| subscriber_id | TEXT | Pipeline identifier |
| topic | TEXT | Source topic name |
| space_id | TEXT | Space identifier |
| tenant_id | TEXT | Tenant identifier |
| offset | BIGINT | Last processed position |

### st_hipp_events (READ)

```sql
-- Fetch eligible events
SELECT
    event_id,
    wal_pos,
    cognitive_trace_id,
    tenant_id,
    space_id,
    topic,
    text,
    simhash_hex,
    activity_category as content_type,
    activity_type,
    embedding_id,
    embedding_status,
    sentiment_score,
    sentiment_label,
    dominant_emotions_json as emotions_json,
    intent_category,
    ner_entities_json,
    temporal_json,
    salience_score,
    created_at,
    participants_json,
    num_participants,
    social_context,
    social_intimacy,
    location_name,
    location_type,
    actor_id
FROM st_hipp_events
WHERE tenant_id = $1
  AND space_id = $2
  AND wal_pos > $3
  AND (consolidation_status IS NULL OR consolidation_status = 'PENDING')
  AND embedding_status = 'READY'
  AND (archival_status IS NULL OR archival_status = '')
ORDER BY wal_pos ASC
LIMIT $4
```

### st_vec (READ)

```sql
-- Load embeddings for events
SELECT event_id, vector, vector_dim
FROM st_vec
WHERE event_id IN ($1, $2, ...)
  AND status IN ('READY', 'INDEXED')
```

| Column | Type | Description |
|--------|------|-------------|
| event_id | TEXT | Event identifier |
| vector | BYTEA | Binary 768-dim float32 vector (3072 bytes) |
| vector_dim | INT | Vector dimension (768) |
| status | TEXT | READY, INDEXED, PENDING |

---

## 7. Algorithms & Helper Functions

### Vector Unpacking Algorithm

```python
# From _load_embeddings_for_events()
# Unpack binary vector from PostgreSQL BYTEA

expected_bytes = vector_dim * 4  # 768 * 4 = 3072 bytes
if len(vector_bytes) != expected_bytes:
    # Invalid vector size - skip
    continue

# Unpack as 768 float32 values
vector = list(struct.unpack(f"{vector_dim}f", vector_bytes))

# Materialize into event state
event.materialize_embedding(vector)
```

### Row to Event State Conversion

```python
def _row_to_event_state(self, row: Any) -> P03EventState:
    # Convert event_time from seconds to milliseconds
    event_time_seconds = row.get("event_time_utc") or row.get("created_at") or 0
    event_time_ms = (
        event_time_seconds * 1000
        if event_time_seconds < 1e12
        else event_time_seconds
    )

    return P03EventState(
        event_id=row["event_id"],
        hipp_event_id=row["event_id"],
        content_text=row.get("text") or "",
        content_type=row.get("content_type") or "",
        simhash_hex=row.get("simhash_hex") or "",
        timestamp=event_time_ms,
        channel_id=row.get("topic") or "",
        embedding_id=row.get("embedding_id") or "",
        sentiment_score=float(row.get("sentiment_score") or 0.0),
        sentiment_label=row.get("sentiment_label") or "neutral",
        emotions_json=row.get("emotions_json") or "[]",
        intent_label=row.get("intent_category") or "",
        ner_entities_json=row.get("ner_entities_json") or "[]",
        temporal_expressions_json=row.get("temporal_json") or "[]",
        participants_json=row.get("participants_json") or "[]",
        num_participants=int(row.get("num_participants") or 0),
        social_context=row.get("social_context") or "",
        social_intimacy=row.get("social_intimacy") or "",
        location_name=row.get("location_name") or "",
        location_type=row.get("location_type") or "",
        activity_type=row.get("activity_type") or "",
        actor_id=row.get("actor_id") or "",
    )
```

---

## 8. Gap Auto-Resolution

R0 includes a **non-blocking** gap auto-resolution step that checks incoming events for entities that resolve pending gaps.

### Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    GAP AUTO-RESOLUTION                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. EXTRACT ENTITIES FROM EVENTS                                │
│     ├── Parse ner_entities_json from each event                 │
│     ├── Handle UltraBERT format: {ner_family, ner_general}      │
│     └── Collect entity text, label, source_event_id            │
│                          │                                       │
│                          ▼                                       │
│  2. LOAD PENDING GAPS                                           │
│     ├── Query st_learning_queue                                 │
│     ├── WHERE status = 'PENDING'                                │
│     ├── AND gap_type = 'AMBIGUOUS_ENTITY'                       │
│     └── Cache for 60 seconds                                    │
│                          │                                       │
│                          ▼                                       │
│  3. MATCH ENTITIES TO GAPS                                      │
│     ├── Normalize entity text (lowercase, remove stopwords)    │
│     ├── Calculate Jaccard similarity                            │
│     ├── Apply label match bonus (+0.1)                          │
│     ├── Apply specificity bonus (+0.1 to +0.15)                 │
│     └── Keep matches where similarity >= 0.6                    │
│                          │                                       │
│                          ▼                                       │
│  4. RESOLVE HIGH-CONFIDENCE GAPS                                │
│     ├── Filter where confidence >= 0.75                         │
│     ├── UPDATE st_learning_queue SET status = 'RESOLVED'        │
│     └── Store resolution metadata                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### GapAutoResolver (from gap_auto_resolver.py)

```python
class GapAutoResolver:
    """Automatically resolves gaps from user context."""

    AUTO_RESOLVE_THRESHOLD = 0.75  # Minimum confidence
    MIN_SIMILARITY = 0.6           # Minimum entity match

    def __init__(self, pool, tenant_id, space_id=None):
        self._pool = pool
        self._tenant_id = tenant_id
        self._space_id = space_id
        self._gap_cache_ttl_ms = 60000  # 1 minute

    async def process_entities(self, entities, source_event_id, event_texts):
        """Main entry point - matches and resolves gaps."""
        await self.load_pending_gaps()

        # Pass 1: NER-based matching
        candidates = []
        for entity in entities:
            matches = self.match_entity_to_gaps(
                entity["text"],
                entity["label"],
                source_event_id
            )
            candidates.extend(matches)

        # Pass 2: Raw text fallback matching
        if event_texts:
            text_matches = self._match_text_to_gaps(event_texts, source_event_id)
            candidates.extend(text_matches)

        # Deduplicate and resolve
        return await self.resolve_gaps(candidates)
```

### Similarity Algorithm

```python
def _similarity(s1: str, s2: str) -> float:
    """Jaccard similarity for entity matching."""
    words1 = set(s1.lower().split())
    words2 = set(s2.lower().split())

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union)
```

### Specificity Bonus

```python
# If new entity is MORE SPECIFIC than gap candidates:
# e.g., "Lincoln Elementary" resolves "Lincoln School" gap

if normalized_entity.startswith(_normalize_entity(candidate)):
    specificity_bonus = 0.15  # Entity extends candidate

if _normalize_entity(candidate) in normalized_entity:
    specificity_bonus = 0.10  # Candidate is substring
```

---

## 9. Configuration

### Constants from checkpoint.py

```python
P03_SUBSCRIBER_ID = "P03_CONSOLIDATE"
P03_CHECKPOINT_TOPIC = "p03_checkpoints"
P03_SOURCE_TOPIC = "st_hipp_events"
```

### Default R0Config Values

| Parameter | Default | Description |
|-----------|---------|-------------|
| `batch_size` | 100 | Max events per batch |
| `require_embedding_ready` | True | Only READY embeddings |
| `exclude_archived` | True | Skip archived events |
| `max_age_hours` | 0 | No age limit |

### QoS Band Assignment

```python
# In _build_envelope()
qos_band = "GREEN" if self.config.batch_size <= 50 else "AMBER"
```

---

## 10. Error Handling

### Error Classification

```python
# R0 errors are marked as RECOVERABLE (retriable)
error = P03Error.create(
    phase="R0",
    stage_id="batch_selector",
    error_type="R0_INGESTION_ERROR",
    error_message=str(e),
    recoverable=True,  # R0 failures are retriable
)
```

### Idempotency

- **Offset read is idempotent** - same offset on retry
- **Same batch selected** if no events processed between retries
- **cycle_id regenerated** on each call (new ULID)

### Non-Fatal Failures

Gap auto-resolution failures are **non-blocking**:

```python
except Exception as e:
    logger.warning(
        "R0: Gap auto-resolution failed (non-fatal): %s",
        str(e),
    )
    return 0  # Continue with batch processing
```

---

## 11. Code Walkthrough

### Main Entry Point

```python
class R0BatchSelector:
    PHASE_ID = P03PhaseId.R0_INIT

    async def run(
        self,
        tenant_id: str,
        space_id: str,
        ctx: "P03RunnerContext",
    ) -> Tuple[Optional[P03BatchEnvelope], P03PhaseResult]:
```

### Step 1: Fetch Offset

```python
# Line ~230
current_offset = await self._fetch_offset(ctx, tenant_id, space_id)

# Implementation:
async def _fetch_offset(self, ctx, tenant_id, space_id) -> int:
    offset_store = ctx.syscalls.offset_store
    offset_record = await offset_store.fetch(
        subscriber_id=P03_SUBSCRIBER_ID,
        topic=P03_SOURCE_TOPIC,
        space_id=space_id,
        tenant_id=tenant_id,
    )
    return offset_record.offset if offset_record else 0
```

### Step 2: Fetch Eligible Events

```python
# Line ~244
events = await self._fetch_eligible_events(
    ctx, tenant_id, space_id, current_offset
)
```

The query includes:

- `wal_pos > offset` (new events only)
- `consolidation_status IS NULL OR 'PENDING'`
- `embedding_status = 'READY'`
- `archival_status IS NULL`

### Step 3: Handle Empty Batch

```python
# Line ~260
if not events:
    return None, P03PhaseResult.skip(
        phase_id=self.PHASE_ID,
        reason="No eligible events found",
        duration_ms=duration_ms,
    )
```

### Step 4: Load Embeddings

```python
# Line ~275
embeddings_loaded = await self._load_embeddings_for_events(ctx, events)
```

Key algorithm:

```python
# Query st_vec
rows = await conn.fetch(query, *event_ids)

for row in rows:
    event_id = row["event_id"]
    vector_bytes = row["vector"]
    vector_dim = row["vector_dim"]

    # Unpack binary to float list
    vector = list(struct.unpack(f"{vector_dim}f", vector_bytes))

    # Materialize into event
    event.materialize_embedding(vector)
```

### Step 5: Gap Auto-Resolution

```python
# Line ~290
gaps_resolved = await _try_auto_resolve_gaps(ctx, events, tenant_id, space_id)
```

### Step 6: Filter Events Without Embeddings

```python
# Line ~300
events_with_embeddings = [e for e in events if e.embedding_768 is not None]
events = events_with_embeddings

if not events:
    return None, P03PhaseResult.skip(
        phase_id=self.PHASE_ID,
        reason="No events with embeddings",
        duration_ms=duration_ms,
    )
```

### Step 7: Build Envelope

```python
# Line ~320
envelope = self._build_envelope(tenant_id, space_id, events, current_offset)

def _build_envelope(self, tenant_id, space_id, events, start_offset):
    event_ids = [e.event_id for e in events]

    context = P03CycleContext.create(
        tenant_id=tenant_id,
        space_id=space_id,
        event_ids=event_ids,
        trigger_type="BATCH",
        trigger_reason=f"R0 selected {len(events)} events after offset {start_offset}",
        pending_before=len(events),
        qos_band="GREEN" if self.config.batch_size <= 50 else "AMBER",
    )

    return P03BatchEnvelope.create(context=context, events=events)
```

### Step 8: Return Result

```python
# Line ~350
result = P03PhaseResult.done(
    phase_id=self.PHASE_ID,
    duration_ms=duration_ms,
    outputs_summary={
        "events_selected": len(events),
        "offset_start": current_offset,
        "batch_id": envelope.context.batch_id,
    },
    idempotency_key=f"p03:r0:{envelope.context.cycle_id}",
)

return envelope, result
```

---

## Complete File Dependencies Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    R0 BATCH SELECTOR                             │
│              r0_batch_selector.py (845 lines)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  IMPORTS FROM P03 ROOT:                                         │
│  ├── checkpoint.py ─────────▶ P03_SOURCE_TOPIC, P03_SUBSCRIBER_ID│
│  ├── context.py ────────────▶ P03CycleContext                   │
│  ├── envelope.py ───────────▶ P03BatchEnvelope                  │
│  ├── event_state.py ────────▶ P03EventState                     │
│  ├── observability.py ──────▶ P03Error                          │
│  ├── phase_interface.py ────▶ P03PhaseResult                    │
│  └── runner_contract.py ────▶ P03PhaseId                        │
│                                                                  │
│  IMPORTS FROM MODULES:                                          │
│  └── consolidation/gap_auto_resolver.py ──▶ GapAutoResolver     │
│                                                                  │
│  DATABASE ACCESS:                                                │
│  ├── st_offsets ────────────▶ READ (fetch offset)               │
│  ├── st_hipp_events ────────▶ READ (fetch eligible events)      │
│  ├── st_vec ────────────────▶ READ (load embeddings)            │
│  └── st_learning_queue ─────▶ READ/WRITE (gap resolution)       │
│                                                                  │
│  OUTPUTS:                                                        │
│  ├── P03BatchEnvelope ──────▶ To R1-R8                          │
│  └── P03PhaseResult ────────▶ To Sequential Runner              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Summary

**R0 Batch Selector** is the critical entry point that:

1. **Reads offset** to determine where to resume processing
2. **Selects eligible events** from hippocampus storage
3. **Materializes embeddings** for semantic processing in R2
4. **Auto-resolves gaps** from implicit user context
5. **Creates the envelope** that flows through all subsequent phases

The phase is designed to be **idempotent** (same input → same batch) and **recoverable** (failures are retriable). It outputs an immutable `P03CycleContext` and mutable `P03EventState` list wrapped in a `P03BatchEnvelope`.

---
---

# R1 Importance Scorer — Complete Deep Dive

> **Pipeline:** P03 Consolidation
> **Phase:** R1 (Importance Scoring & Hebbian Learning)
> **Location:** `k0/pipelines/p03/phases/r1_importance_scorer.py`
> **Last Updated:** 2026-01-09

---

## Table of Contents (R1)

1. [R1 Overview](#r1-1-overview)
2. [R1 in the Pipeline Context](#r1-2-pipeline-context)
3. [Core Files & Dependencies](#r1-3-core-files--dependencies)
4. [Step-by-Step Execution Flow](#r1-4-step-by-step-execution-flow)
5. [Data Structures](#r1-5-data-structures)
6. [Algorithms](#r1-6-algorithms)
7. [Hebbian Learning](#r1-7-hebbian-learning)
8. [Weight Learning (Adaptive)](#r1-8-weight-learning)
9. [Audit Logging](#r1-9-audit-logging)
10. [Configuration](#r1-10-configuration)
11. [Code Walkthrough](#r1-11-code-walkthrough)

---

## R1-1. Overview

**R1 (Importance Scorer)** computes importance scores for each event in the batch, determining which memories are prioritized for consolidation.

### Scientific Basis

Based on McGaugh (2004):
> *"Emotional memories are more strongly encoded due to amygdala-hippocampus interaction."*

Events with high emotional salience, novelty, or social significance are prioritized for memory consolidation.

### Key Responsibilities

1. **Load importance weights** (learned or static)
2. **Compute importance score** for each event
3. **Log scoring factors** for audit trail (explainability)
4. **Update event state** with importance fields
5. **(Future)** Extract co-occurrences for Hebbian edge updates

### Core Formula

```
importance = (emotional + novelty + social) × event_type_multiplier
```

Where:

- **emotional** = `sentiment_weight × |sentiment| + affect_weight × |affect|`
- **novelty** = `novelty_weight × novelty_score`
- **social** = `social_weight × log2(participants) / 3.32`

---

## R1-2. Pipeline Context

```
┌─────────────────────────────────────────────────────────────────┐
│                    P03 CONSOLIDATION PIPELINE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐          │
│  │  R0  │──▶│  R1  │──▶│  R2  │──▶│  R3  │──▶│  R4  │          │
│  │BATCH │   │SCORE │   │CLUST │   │DEDUP │   │  KG  │          │
│  └──────┘   └──────┘   └──────┘   └──────┘   └──────┘          │
│                 ▲                                                │
│                 │                                                │
│            THIS PHASE                                           │
│                                                                  │
│   Receives: P03BatchEnvelope (from R0)                          │
│   Outputs:  Scored events with importance factors               │
│   Updates:  event.importance_score, event.importance_computed   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Signature

```python
async def run(
    envelope: "P03BatchEnvelope",
    ctx: "P03RunnerContext",
) -> P03PhaseResult
```

---

## R1-3. Core Files & Dependencies

### Primary File

```
k0/pipelines/p03/phases/r1_importance_scorer.py (345 lines)
```

### Algorithm Files

| File | Purpose | Lines |
|------|---------|-------|
| `k0/modules/consolidation/algorithms/importance_scorer.py` | Core scoring logic | 844 |
| `k0/modules/consolidation/algorithms/importance_weight_learner.py` | Adaptive weight learning | 746 |
| `k0/modules/consolidation/algorithms/hebbian_learner.py` | Co-occurrence edge learning | 750 |

### Direct Imports

| File | Classes/Functions Imported |
|------|---------------------------|
| `importance_scorer.py` | `ImportanceScorer`, `ImportanceWeights` |
| `audit_logger.py` | `P03AuditLogger` |
| `observability.py` | `P03Error` |
| `phase_interface.py` | `P03PhaseResult` |
| `phase_outputs.py` | `ScoredEvent` |
| `runner_contract.py` | `P03PhaseId` |

---

## R1-4. Step-by-Step Execution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         R1 EXECUTION                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. SKIP CHECK                                                  │
│     ├── If no events → SKIP                                     │
│     └── If all events.importance_computed → SKIP                │
│                          │                                       │
│                          ▼                                       │
│  2. INITIALIZE SCORER                                           │
│     ├── Get weight_store from ctx.syscalls                      │
│     ├── Create ImportanceScorer(space_id, weight_store)         │
│     └── Create P03AuditLogger(space_id, tenant_id, cycle_id)    │
│                          │                                       │
│                          ▼                                       │
│  3. LOAD WEIGHTS                                                │
│     ├── Try per-space learned weights (if samples >= 500)       │
│     ├── Fallback: global learned weights                        │
│     ├── Fallback: static priors                                 │
│     └── Progressive blending for 100-499 samples                │
│                          │                                       │
│                          ▼                                       │
│  4. SCORE BATCH                                                 │
│     ├── For each event:                                         │
│     │   ├── Compute emotional_component                         │
│     │   ├── Compute novelty_component                           │
│     │   ├── Compute social_component                            │
│     │   ├── Apply event_type_multiplier                         │
│     │   ├── Clamp to [0.0, 1.0]                                 │
│     │   └── Update event.set_importance(...)                    │
│     └── Collect ScoredEvent list                                │
│                          │                                       │
│                          ▼                                       │
│  5. AUDIT LOGGING                                               │
│     ├── Sample events at sample_rate (default 100%)             │
│     ├── Log inputs: sentiment, affect, novelty, participants    │
│     ├── Log outputs: score, components, multiplier              │
│     └── Store audit records for R7 batch write                  │
│                          │                                       │
│                          ▼                                       │
│  6. COLLECT PHASE OUTPUTS                                       │
│     ├── envelope.phases.r1_scored_events = scored_events        │
│     └── envelope.phases.r1_audit_records = audit_records        │
│                          │                                       │
│                          ▼                                       │
│  7. RETURN RESULT                                               │
│     └── P03PhaseResult.done(outputs_summary, idempotency_key)   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## R1-5. Data Structures

### R1Config (Configuration)

```python
@dataclass
class R1Config:
    """R1 phase configuration."""

    audit_sample_rate: float = 1.0
    # Fraction of events to audit [0.0, 1.0]
    # 1.0 = 100% (debug), 0.1 = 10% (production)

    enable_hebbian: bool = False
    # Whether to run Hebbian learning (Issue 4.1.3)

    min_samples_for_learned_weights: int = 500
    # Minimum samples before using learned weights

    importance_weights: Optional[ImportanceWeights] = None
    # Optional custom weights (uses defaults if None)
```

### ImportanceWeights (Frozen)

```python
@dataclass(frozen=True)
class ImportanceWeights:
    """Configurable weights for importance scoring components."""

    sentiment_weight: float = 0.25  # Sentiment analysis contribution
    affect_weight: float = 0.30     # Emotional valence/arousal
    novelty_weight: float = 0.25    # Information novelty
    social_weight: float = 0.20     # Social context

    # Total sums to 1.0 for normalization
```

### ImportanceBreakdown (Audit Output)

```python
@dataclass
class ImportanceBreakdown:
    """Component breakdown for audit logging."""

    emotional_component: float  # Combined sentiment + affect
    novelty_component: float    # Novelty contribution
    social_component: float     # Social relevance
    multiplier: float           # Event type multiplier
    final_score: float          # Final normalized score [0, 1]
    weights_source: str = "static"  # "static" or "learned"
```

### ScoredEvent (Phase Output)

```python
@dataclass
class ScoredEvent:
    """Event with computed importance score (R1 output)."""

    event_id: str
    importance_score: float
    recency_factor: float
    affect_factor: float
    social_factor: float
    novelty_factor: float
```

---

## R1-6. Algorithms

### ImportanceScorer Class

**Location:** `k0/modules/consolidation/algorithms/importance_scorer.py`

#### Event Type Multipliers

```python
EVENT_TYPE_MULTIPLIERS = {
    "message": 1.0,      # Default text messages
    "chat": 1.0,         # Chat conversations
    "photo": 1.2,        # Visual memories (higher)
    "image": 1.2,        # Same as photo
    "video": 1.3,        # Video memories (highest)
    "milestone": 2.0,    # Birthdays, anniversaries
    "celebration": 2.0,  # Special occasions
    "routine": 0.5,      # Daily repeated events (lower)
    "location": 0.8,     # Check-ins
    "voice": 1.1,        # Voice memos
    "audio": 1.1,        # Same as voice
    "calendar": 0.9,     # Calendar events
    "transaction": 0.6,  # Financial transactions (lower)
}
```

#### Priority Tiers

```python
def get_priority_tier(score: float) -> str:
    """Map importance score to priority tier."""
    if score >= 0.80:
        return "CRITICAL"   # Process immediately
    elif score >= 0.50:
        return "HIGH"       # Process in current cycle
    elif score >= 0.30:
        return "MEDIUM"     # Process if capacity allows
    else:
        return "LOW"        # May be deferred
```

### Emotional Intensity Formula

```python
def compute_emotional_intensity(
    sentiment_score: float,   # [-1, 1]
    affect_valence: float,    # [-1, 1]
    weights: ImportanceWeights,
) -> float:
    """
    Uses absolute values because both strong positive AND
    strong negative emotions enhance memory encoding.
    """
    sentiment_intensity = abs(sentiment_score)
    affect_intensity = abs(affect_valence)

    return (
        sentiment_intensity * weights.sentiment_weight
        + affect_intensity * weights.affect_weight
    )
    # Returns [0, ~0.55] (unclamped)
```

### Social Factor Formula

```python
LOG2_10 = 3.321928  # log2(10)

def compute_social_factor(
    participant_count: int,
    weights: ImportanceWeights,
) -> float:
    """
    Logarithmic scaling prevents large groups from
    dominating importance scores.

    Scale:
        1 person:  0.0    (solo, no social bonus)
        2 people:  ~0.30 × weight
        5 people:  ~0.70 × weight
        10+ people: ~1.0 × weight (capped)
    """
    if participant_count <= 1:
        return 0.0

    log_factor = min(1.0, math.log2(participant_count) / LOG2_10)
    return log_factor * weights.social_weight
```

### Novelty Factor Formula

```python
def compute_novelty_factor(
    novelty_score: float,     # [0, 1] pre-computed
    weights: ImportanceWeights,
) -> float:
    """
    Novelty score represents how different this event
    is from existing memory clusters.
    """
    clamped = max(0.0, min(1.0, novelty_score))
    return clamped * weights.novelty_weight
```

### Complete Importance Score

```python
def compute_importance_score(
    event: Any,
    weights: ImportanceWeights,
) -> Tuple[float, ImportanceBreakdown]:
    """
    importance = (emotional + novelty + social) × multiplier
    """
    # Extract event attributes
    sentiment_score = getattr(event, "sentiment_score", 0.0)
    affect_valence = getattr(event, "affect_valence", 0.0)
    novelty_score = getattr(event, "novelty_score", 0.0)
    participant_count = getattr(event, "participant_count", 1)
    content_type = getattr(event, "content_type", "message")

    # Compute components
    emotional = compute_emotional_intensity(sentiment_score, affect_valence, weights)
    novelty = compute_novelty_factor(novelty_score, weights)
    social = compute_social_factor(participant_count, weights)

    # Sum and multiply
    base_importance = emotional + novelty + social
    multiplier = EVENT_TYPE_MULTIPLIERS.get(content_type.lower(), 1.0)
    raw_score = base_importance * multiplier

    # Clamp to [0.0, 1.0]
    final_score = max(0.0, min(1.0, raw_score))

    return final_score, ImportanceBreakdown(...)
```

---

## R1-7. Hebbian Learning

**Location:** `k0/modules/consolidation/algorithms/hebbian_learner.py`

### Principle

> *"Cells that fire together, wire together"* — Hebb, 1949

In FamilyOS context: Entities (people, places, concepts) that appear together in events strengthen their connection in the knowledge graph.

### Relation Types

```python
class RelationType(str, Enum):
    INTERACTS_WITH = "INTERACTS_WITH"  # Actor-Actor
    FREQUENTS = "FREQUENTS"            # Actor-Location
    DISCUSSES = "DISCUSSES"            # Actor-Topic
```

### HebbianConfig

```python
@dataclass(frozen=True)
class HebbianConfig:
    # Positive (Hebbian) learning
    learning_rate: float = 0.1     # Strength per co-occurrence
    decay_rate: float = 0.01       # Daily decay for unused edges
    max_weight: float = 1.0        # Weight cap
    min_weight: float = 0.01       # Below this, edge is pruned

    # Anti-Hebbian learning
    anti_learning_rate: float = 0.15        # Faster than positive
    explicit_correction_multiplier: float = 1.3  # User corrections
    prune_threshold: float = 0.05           # Archive threshold
```

### Hebbian Weight Update Formula

```python
def update_edge_weight(
    current_weight: float,
    current_count: int,
    event_importance: float,
) -> Tuple[float, int]:
    """
    Soft saturation formula from Dossier C.2.2:

    delta = learning_rate × (max_weight - current_weight) × event_importance

    The (max_weight - current_weight) term prevents weights from
    exceeding max_weight asymptotically.
    """
    delta = learning_rate * (max_weight - current_weight) * event_importance
    new_weight = min(max_weight, current_weight + delta)
    new_count = current_count + 1

    return (new_weight, new_count)
```

### Time-Based Decay

```python
def apply_decay(edges: List[KGEdge], days_since_update: int):
    """
    Exponential decay for edges not reinforced:

    new_weight = weight × exp(-decay_rate × days)

    Edges below min_weight are pruned (soft delete).
    """
    decay_factor = math.exp(-decay_rate * days_since_update)

    for edge in edges:
        new_weight = edge.weight * decay_factor
        if new_weight < min_weight:
            # Prune edge
            ...
```

### Anti-Hebbian Decay (Negative Learning)

```python
# Signals that trigger anti-Hebbian decay
class AntiHebbianSignal(str, Enum):
    ENTITY_MERGE_REJECTED = "ENTITY_MERGE_REJECTED"  # P06/User rejects
    ASSOCIATION_WRONG = "ASSOCIATION_WRONG"          # K1 correction
    MUTUAL_EXCLUSION = "MUTUAL_EXCLUSION"            # R4 detection
    CONTRADICTION = "CONTRADICTION"                   # R7 detection

# Penalty lookup
ANTI_HEBBIAN_PENALTIES = {
    ENTITY_MERGE_REJECTED: 0.2,
    ASSOCIATION_WRONG: 0.3,
    MUTUAL_EXCLUSION: 0.4,
    CONTRADICTION: 0.15,
}

def apply_anti_decay(edge, signal_type, confidence, is_explicit_correction):
    """
    Formula from Dossier C.2.2.1:

    Δw = -anti_lr × current_weight × confidence × penalty × multiplier

    Where multiplier = 1.3 if explicit user correction.
    """
    ...
```

### Weight Interpretation

```python
def weight_interpretation(weight: float) -> str:
    """Human-readable edge strength."""
    if weight >= 0.80:
        return "Very Strong"  # Best friends, family
    elif weight >= 0.50:
        return "Strong"       # Colleagues, close friends
    elif weight >= 0.20:
        return "Moderate"     # Acquaintances
    elif weight >= 0.01:
        return "Weak"         # One-time interactions
    else:
        return "Negligible"
```

---

## R1-8. Weight Learning (Adaptive)

**Location:** `k0/modules/consolidation/algorithms/importance_weight_learner.py`

### Cold Start Strategy (Issue 4.1.6)

```
┌─────────────────────────────────────────────────────────────────┐
│                    WEIGHT SELECTION STRATEGY                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Samples    │  Strategy                                         │
│  ──────────────────────────────────────────────────────────     │
│  0-99       │  Pure static priors (α = 0)                       │
│  100-499    │  Progressive blending: α = samples/500            │
│  500+       │  Pure learned weights (α = 1)                     │
│                                                                  │
│  Blending Formula:                                               │
│      blended_weight = α × learned + (1 - α) × prior             │
│                                                                  │
│  Fallback Order:                                                 │
│      1. Per-space learned weights                               │
│      2. Global learned weights                                  │
│      3. Static priors                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### WeightLearnerConfig

```python
@dataclass(frozen=True)
class WeightLearnerConfig:
    learning_rate: float = 0.01      # Gradient descent η
    momentum: float = 0.9            # Velocity smoothing β
    min_samples: int = 500           # Cold start threshold
    weight_min: float = 0.05         # Per-weight floor
    weight_max: float = 0.60         # Per-weight ceiling
    sliding_window_days: int = 30    # Training data window
    rollback_threshold: int = 3      # Consecutive loss nights

    # Static priors (from Dossier §4.2.2)
    prior_emotional: float = 0.35
    prior_recency: float = 0.25
    prior_access: float = 0.20
    prior_social: float = 0.20
```

### Training Step

```python
def train_step(batch: TrainingBatch) -> TrainingResult:
    """
    Online gradient descent with momentum.

    Loss: Binary cross-entropy predicting "will event be grounded?"
    Training: Nightly batch during P03 consolidation
    """
    features, labels, sample_weights = batch.to_arrays()

    # Softmax ensures weights sum to 1
    w = softmax(weights_tensor)

    # Predictions: weighted sum of features
    predictions = (features * w).sum(dim=1)

    # Weighted BCE loss (exponential decay on older samples)
    loss = bce_with_logits(predictions, labels) * sample_weights

    # Gradient descent with momentum
    velocity = momentum * velocity + gradient
    weights = weights - learning_rate * velocity

    # Clamp weights to [0.05, 0.60]
    ...
```

### Stability Controls

- **Weight Clamping:** Each weight clamped to `[0.05, 0.60]`
- **Softmax Normalization:** Weights always sum to 1.0
- **Rollback:** After 3 consecutive nights of increasing loss, rollback to priors

---

## R1-9. Audit Logging

**Location:** `k0/pipelines/p03/audit_logger.py`

### AuditAction Enum

```python
class AuditAction(Enum):
    REINFORCE = "REINFORCE"
    DECAY = "DECAY"
    ARCHIVE = "ARCHIVE"
    MERGE = "MERGE"
    CREATE = "CREATE"
    EXTEND = "EXTEND"
    PRUNE = "PRUNE"
    SKIP = "SKIP"
    CONTRADICT = "CONTRADICT"
    SCORE = "SCORE"  # R1 importance scoring
```

### Explanation Template (SCORE)

```python
EXPLANATION_TEMPLATES[AuditAction.SCORE] = (
    "Importance score computed: {importance_score:.3f} (priority: {priority_tier}). "
    "Components: emotional={emotional:.3f}, novelty={novelty:.3f}, social={social:.3f}, "
    "multiplier={multiplier:.2f}. Weights source: {weights_source}."
)
```

### PII Redaction

```python
# RED-band forbidden fields (NEVER logged)
RED_BAND_FIELDS = frozenset({
    "raw_content", "message_body", "user_input", "personal_name",
    "email", "phone", "address", "ssn", "credit_card",
    "password", "api_key", "secret", "token",
    "biometric", "health_data", "financial_data", "location_precise",
})
```

### Audit Record Structure

```python
@dataclass
class AuditRecord:
    audit_id: str              # ULID (auto-generated)
    memory_id: str             # Event ID being scored
    source_table: str          # "st_hipp_events"
    action: AuditAction        # SCORE
    formula_used: str          # "importance_scorer"
    formula_version: str       # "1.0.0"
    inputs: Dict[str, Any]     # Scoring inputs (redacted)
    outputs: Dict[str, Any]    # Score components
    explanation: str           # Human-readable
    decision_id: str           # cycle_id
    space_id: str
    tenant_id: str
    cycle_id: str
    confidence: float          # importance_score value
    created_at: int            # MILLISECONDS
```

---

## R1-10. Configuration

### Default Values Summary

| Parameter | Default | Description |
|-----------|---------|-------------|
| `audit_sample_rate` | 1.0 | 100% audit (debug mode) |
| `enable_hebbian` | False | Hebbian learning disabled |
| `min_samples_for_learned_weights` | 500 | Cold start threshold |
| `sentiment_weight` | 0.25 | Sentiment contribution |
| `affect_weight` | 0.30 | Emotional contribution |
| `novelty_weight` | 0.25 | Novelty contribution |
| `social_weight` | 0.20 | Social contribution |

### Database Tables Accessed

| Table | Access | Purpose |
|-------|--------|---------|
| `st_importance_weights` | READ | Load learned weights |
| `st_consolidation_audit` | WRITE (staged) | Audit records |

---

## R1-11. Code Walkthrough

### Main Entry Point

```python
class R1ImportanceScorer:
    PHASE_ID = P03PhaseId.R1_SCORE

    async def run(
        self,
        envelope: "P03BatchEnvelope",
        ctx: "P03RunnerContext",
    ) -> P03PhaseResult:
```

### Step 1: Skip Check

```python
# Line ~150
if self.should_skip(envelope):
    return P03PhaseResult.skip(
        phase_id=self.PHASE_ID,
        reason="No unscored events in batch",
        duration_ms=duration_ms,
        idempotency_key=self.idempotency_key(envelope),
    )

def should_skip(envelope):
    if not envelope.events:
        return True
    # Check if all events already scored
    return all(event.importance_computed for event in envelope.events)
```

### Step 2: Initialize Scorer

```python
# Line ~170
weight_store = getattr(ctx.syscalls, "weight_store", None)
scorer = ImportanceScorer(
    space_id=space_id,
    weight_store=weight_store,
)

audit_logger = P03AuditLogger(
    space_id=space_id,
    tenant_id=tenant_id,
    cycle_id=cycle_id,
)
```

### Step 3: Score Batch with Audit

```python
# Line ~190
sample_rate = ctx.get_config(
    "p03.importance.audit_sample_rate",
    self.config.audit_sample_rate,
)

scored_results = await scorer.score_batch_with_audit(
    events=envelope.events,
    audit_logger=audit_logger,
    sample_rate=sample_rate,
)
```

### Step 4: Collect Phase Outputs

```python
# Line ~210
scored_events: List[ScoredEvent] = []
for result in scored_results:
    scored_events.append(
        ScoredEvent(
            event_id=result["event_id"],
            importance_score=result["importance_score"],
            recency_factor=result["recency_factor"],
            affect_factor=result["affect_factor"],
            social_factor=result["social_factor"],
            novelty_factor=result["novelty_factor"],
        )
    )

# Store in envelope
envelope.phases.r1_scored_events = scored_events
envelope.phases.r1_audit_records = audit_logger.get_pending_records()
```

### Step 5: Calculate Statistics

```python
# Line ~240
scores = [e.importance_score for e in scored_events]
avg_score = sum(scores) / len(scores)
max_score = max(scores)
min_score = min(scores)

# Priority tier counts
critical_count = sum(1 for s in scores if s >= 0.80)
high_count = sum(1 for s in scores if 0.50 <= s < 0.80)
medium_count = sum(1 for s in scores if 0.30 <= s < 0.50)
low_count = sum(1 for s in scores if s < 0.30)
```

### Step 6: Return Result

```python
# Line ~270
return P03PhaseResult.done(
    phase_id=self.PHASE_ID,
    duration_ms=duration_ms,
    outputs_summary={
        "events_scored": len(scored_events),
        "audit_records": audit_logger.record_count(),
        "avg_importance": round(avg_score, 3),
        "critical_count": critical_count,
        "high_count": high_count,
        "weights_source": scorer._weights_source,
    },
    idempotency_key=self.idempotency_key(envelope),
)
```

---

## Complete R1 File Dependencies Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    R1 IMPORTANCE SCORER                          │
│              r1_importance_scorer.py (345 lines)                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ALGORITHMS USED:                                               │
│  ├── importance_scorer.py ─────▶ ImportanceScorer               │
│  │   ├── compute_emotional_intensity()                          │
│  │   ├── compute_social_factor()                                │
│  │   ├── compute_novelty_factor()                               │
│  │   ├── compute_importance_score()                             │
│  │   ├── score_batch()                                          │
│  │   └── score_batch_with_audit()                               │
│  │                                                               │
│  ├── importance_weight_learner.py ─▶ ImportanceWeightLearner    │
│  │   ├── train_step() [gradient descent]                        │
│  │   ├── get_weights_with_cold_start()                          │
│  │   └── Progressive blending (α = samples/500)                 │
│  │                                                               │
│  └── hebbian_learner.py ───────▶ HebbianLearner (Future)        │
│      ├── extract_cooccurrences()                                │
│      ├── update_edge_weight()                                   │
│      ├── apply_decay()                                          │
│      └── apply_anti_decay()                                     │
│                                                                  │
│  IMPORTS FROM P03 ROOT:                                         │
│  ├── audit_logger.py ───────────▶ P03AuditLogger, AuditAction   │
│  ├── observability.py ──────────▶ P03Error                      │
│  ├── phase_interface.py ────────▶ P03PhaseResult                │
│  ├── phase_outputs.py ──────────▶ ScoredEvent                   │
│  └── runner_contract.py ────────▶ P03PhaseId                    │
│                                                                  │
│  DATABASE ACCESS:                                                │
│  ├── st_importance_weights ─────▶ READ (learned weights)        │
│  └── st_consolidation_audit ────▶ WRITE (staged for R7)         │
│                                                                  │
│  INPUTS:                                                         │
│  └── P03BatchEnvelope ──────────▶ From R0                       │
│                                                                  │
│  OUTPUTS:                                                        │
│  ├── envelope.phases.r1_scored_events                           │
│  ├── envelope.phases.r1_audit_records                           │
│  └── event.importance_score (updated in-place)                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Summary

**R1 Importance Scorer** computes importance scores using:

1. **Emotional intensity** (sentiment + affect)
2. **Novelty** (how different from existing memories)
3. **Social factor** (number of participants)
4. **Event type multiplier** (milestones = 2.0×, routine = 0.5×)

The phase supports:

- **Adaptive weight learning** with cold-start blending
- **Hebbian edge updates** for knowledge graph (future)
- **Audit logging** with PII redaction for explainability
- **Priority tier classification** (CRITICAL, HIGH, MEDIUM, LOW)

---
---

# R2 Episodic Integrator — Complete Deep Dive

> **Pipeline:** P03 Consolidation
> **Phase:** R2 (Episodic Clustering)
> **Location:** `k0/pipelines/p03/phases/r2_episodic_integrator.py`
> **Last Updated:** 2026-01-09

---

## Table of Contents (R2)

1. [R2 Overview](#r2-1-overview)
2. [R2 in the Pipeline Context](#r2-2-pipeline-context)
3. [Core Files & Dependencies](#r2-3-core-files--dependencies)
4. [Step-by-Step Execution Flow](#r2-4-step-by-step-execution-flow)
5. [Data Structures](#r2-5-data-structures)
6. [Algorithms](#r2-6-algorithms)
7. [Composite Distance](#r2-7-composite-distance)
8. [Episode Splitting](#r2-8-episode-splitting)
9. [DBSCAN & HDBSCAN Clustering](#r2-9-dbscan--hdbscan-clustering)
10. [Centroid Calculation](#r2-10-centroid-calculation)
11. [Adaptive Learning](#r2-11-adaptive-learning)
12. [Quality Tracking](#r2-12-quality-tracking)
13. [Configuration](#r2-13-configuration)
14. [Code Walkthrough](#r2-14-code-walkthrough)

---

## R2-1. Overview

**R2 (Episodic Integrator)** clusters events into coherent episodes using DBSCAN/HDBSCAN with composite distance (semantic + temporal).

### Scientific Basis

Based on Tulving (2002) episodic memory theory:
> *"Episodic memory is the memory of autobiographical events that can be explicitly stated or conjured."*

Events occurring close together in time AND semantically related form natural episodes (e.g., "lunch with mom at cafe").

### Key Responsibilities

1. **Split events** into sequences by time gaps / location / activity
2. **Cluster sequences** using DBSCAN with composite distance
3. **Compute centroids** for each episode (weighted by importance)
4. **Track quality** via silhouette score
5. **Adaptive learning** of eps and min_samples per-space

### Core Formula

```
composite_distance = semantic_weight × cosine_distance + temporal_weight × time_distance
```

Where:

- **cosine_distance** = `1 - cosine_similarity(embedding_a, embedding_b)`
- **time_distance** = `min(1.0, |ts_a - ts_b| / max_temporal_gap_ms)`
- Default weights: `semantic=0.7, temporal=0.3`

---

## R2-2. Pipeline Context

```
┌─────────────────────────────────────────────────────────────────┐
│                    P03 CONSOLIDATION PIPELINE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐          │
│  │  R0  │──▶│  R1  │──▶│  R2  │──▶│  R3  │──▶│  R4  │          │
│  │BATCH │   │SCORE │   │CLUST │   │DEDUP │   │  KG  │          │
│  └──────┘   └──────┘   └──────┘   └──────┘   └──────┘          │
│                            ▲                                     │
│                            │                                     │
│                       THIS PHASE                                │
│                                                                  │
│   Receives: P03BatchEnvelope with importance-scored events      │
│   Outputs:  Episode clusters with centroids                     │
│   Updates:  event.cluster_id, event.is_noise                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### R2 Signature

```python
async def run(
    envelope: "P03BatchEnvelope",
    ctx: "P03RunnerContext",
) -> P03PhaseResult
```

---

## R2-3. Core Files & Dependencies

### Primary File

```
k0/pipelines/p03/phases/r2_episodic_integrator.py (1221 lines)
```

### Algorithm Files

| File | Purpose | Lines |
|------|---------|-------|
| `composite_distance.py` | Semantic + temporal distance metric | 461 |
| `episode_splitter.py` | Pre-clustering sequence splitting | 463 |
| `episodic_dbscan.py` | DBSCAN with composite distance | 460 |
| `episodic_hdbscan.py` | HDBSCAN with noise rescue | 653 |
| `centroid_calculator.py` | Weighted centroid computation | 614 |
| `eps_adjuster.py` | Adaptive eps learning | 406 |
| `min_samples_adjuster.py` | Adaptive min_samples learning | 369 |
| `cluster_quality.py` | Closed-loop quality metrics | 522 |

### Direct Imports

```python
from k0.modules.consolidation.algorithms import (
    CentroidCalculator, CentroidResult,
    ClusteringResult, ClusterQualityMetrics, ClusterQualityTracker,
    DBSCANParams, EpisodeCandidate, EpisodeSplitter,
    EpisodicDBSCAN, EpisodicHDBSCAN, EpsAdjuster, EpsAdjustmentConfig,
    HDBSCANClusteringResult, HDBSCANParams,
    MinSamplesAdjuster, MinSamplesConfig,
    SplitConfig, WeightingStrategy,
)
```

---

## R2-4. Step-by-Step Execution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         R2 EXECUTION                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. SKIP CHECK                                                  │
│     ├── If events < min_batch_size (2) → SKIP                   │
│     └── If no events have embeddings → SKIP                     │
│                          │                                       │
│                          ▼                                       │
│  2. INITIALIZE COMPONENTS                                       │
│     ├── EpisodeSplitter (time gap config)                       │
│     ├── EpisodicHDBSCAN or EpisodicDBSCAN                       │
│     ├── CentroidCalculator                                      │
│     ├── ClusterQualityTracker (optional)                        │
│     └── EpsAdjuster + MinSamplesAdjuster (adaptive)             │
│                          │                                       │
│                          ▼                                       │
│  3. GET CLUSTERING PARAMS                                       │
│     ├── Try per-space learned params (st_learned_weights)       │
│     └── Fallback: config defaults (eps=0.07, min_samples=2)     │
│                          │                                       │
│                          ▼                                       │
│  4. SPLIT EVENTS INTO SEQUENCES                                 │
│     ├── Sort by timestamp                                       │
│     ├── Detect breaks: location, activity, time gap, hard limit │
│     └── Output: List[List[Event]] (episodes)                    │
│                          │                                       │
│                          ▼                                       │
│  5. CLUSTER EACH SEQUENCE                                       │
│     ├── Build composite distance matrix                         │
│     ├── Run HDBSCAN (or DBSCAN fallback)                        │
│     ├── Rescue noise with low outlier scores                    │
│     └── Output: ClusteringResult per sequence                   │
│                          │                                       │
│                          ▼                                       │
│  6. COMPUTE CENTROIDS                                           │
│     ├── For each cluster: weighted average of embeddings        │
│     ├── Strategy: IMPORTANCE (weight by importance_score)       │
│     ├── L2-normalize centroid                                   │
│     └── Calculate variance (cluster cohesion)                   │
│                          │                                       │
│                          ▼                                       │
│  7. CANONICALIZE EPISODES (optional)                            │
│     ├── Group by signature: (type, location, time_bucket)       │
│     └── Merge episodes with same signature                      │
│                          │                                       │
│                          ▼                                       │
│  8. UPDATE EVENT STATES                                         │
│     ├── event.cluster_id = assigned cluster                     │
│     ├── event.cluster_label = DBSCAN label                      │
│     └── event.is_noise = True if label == -1                    │
│                          │                                       │
│                          ▼                                       │
│  9. TRACK QUALITY & ADAPT                                       │
│     ├── Compute silhouette score                                │
│     ├── Adjust eps if clusters too loose/tight                  │
│     ├── Adjust min_samples if too much noise                    │
│     └── Persist to st_learned_weights                           │
│                          │                                       │
│                          ▼                                       │
│  10. POPULATE ENVELOPE OUTPUTS                                  │
│      ├── envelope.phases.r2_clusters                            │
│      ├── envelope.phases.r2_noise_event_ids                     │
│      └── envelope.phases.r2_clustering_params                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## R2-5. Data Structures

### R2Config (Configuration)

```python
@dataclass
class R2Config:
    min_batch_size: int = 2              # Skip if fewer events
    eps: float = 0.0                     # 0.0 = use adaptive/default
    min_samples: int = 0                 # 0 = use adaptive/default
    semantic_weight: float = 0.7         # Weight for embedding distance
    temporal_weight: float = 0.3         # Weight for time distance
    enable_splitting: bool = True        # Split by time gaps
    time_gap_minutes: int = 60           # Gap threshold for splitting
    enable_adaptive_eps: bool = True     # Learn eps per-space
    enable_adaptive_min_samples: bool = True
    enable_quality_tracking: bool = True
    weighting_strategy: WeightingStrategy = WeightingStrategy.IMPORTANCE
    use_hdbscan: bool = True             # HDBSCAN vs DBSCAN
    noise_rescue_threshold: float = 0.5  # Rescue noise with outlier < this
    cluster_selection_method: str = "leaf"  # 'leaf' preserves small clusters
    enable_canonicalization: bool = True    # Merge same-signature episodes
    canonicalization_time_bucket_hours: int = 6
```

### DBSCANParams (Clustering Parameters)

```python
@dataclass(frozen=True)
class DBSCANParams:
    eps: float = 0.15           # Max distance to cluster (tighter for UltraBERT)
    min_samples: int = 2        # Min events for core point
    temporal_weight: float = 0.3
    max_temporal_gap_hours: float = 4.0  # Hard limit - beyond = infinity

    @property
    def max_temporal_gap_ms(self) -> int:
        return int(self.max_temporal_gap_hours * 3_600_000)

    @property
    def semantic_weight(self) -> float:
        return 1.0 - self.temporal_weight
```

### HDBSCANParams (Hierarchical Clustering)

```python
@dataclass(frozen=True)
class HDBSCANParams:
    min_cluster_size: int = 2            # Smallest episode size
    min_samples: int = 1                 # Density smoothing (lower = less noise)
    cluster_selection_epsilon: float = 0.0  # 0 = automatic
    cluster_selection_method: str = "leaf"  # 'leaf' preserves small clusters
    noise_rescue_threshold: float = 0.5     # Rescue noise below this
    temporal_weight: float = 0.3
    max_temporal_gap_hours: float = 4.0
    allow_single_cluster: bool = False
```

### EpisodeCluster (Output)

```python
@dataclass
class EpisodeCluster:
    cluster_id: str                          # ULID or uuid hex
    member_event_ids: List[str] = []         # Events in this episode
    centroid_embedding_id: Optional[str] = None  # st_vec reference
    dominant_sentiment: float = 0.0          # Average sentiment
    dominant_emotion: str = ""               # Most common emotion
    temporal_start: int = 0                  # MILLISECONDS
    temporal_end: int = 0                    # MILLISECONDS
    location_hint: Optional[str] = None      # Common location
    participants_json: str = "[]"            # Aggregated participants
    activity_type: str = ""                  # Inferred activity
    cohesion_score: float = 0.0              # Intra-cluster similarity
    title: str = ""                          # Generated title
    summary: str = ""                        # Generated summary

    @property
    def event_count(self) -> int:
        return len(self.member_event_ids)

    @property
    def duration_ms(self) -> int:
        return self.temporal_end - self.temporal_start
```

### ClusteringResult (DBSCAN Output)

```python
@dataclass
class ClusteringResult:
    clusters: List[EpisodeCluster]   # All clusters including noise
    total_events: int                # Events processed
    cluster_count: int               # Non-noise clusters
    noise_count: int                 # Singleton/noise events
    labels: List[int]                # DBSCAN labels per event

    @property
    def singleton_rate(self) -> float:
        if self.total_events == 0:
            return 0.0
        return self.noise_count / self.total_events
```

---

## R2-6. Algorithms Overview

R2 uses a multi-stage clustering pipeline:

```
Events → Split → Cluster → Centroid → Canonicalize → Output
         ▲        ▲          ▲
         │        │          │
    EpisodeSplitter  HDBSCAN  CentroidCalculator
```

| Algorithm | Purpose | Key Insight |
|-----------|---------|-------------|
| CompositeDistance | Combine semantic + temporal | Events close in time AND meaning cluster |
| EpisodeSplitter | Pre-split sequences | Prevent cross-activity clusters |
| EpisodicHDBSCAN | Density-based clustering | Automatic multi-resolution |
| CentroidCalculator | Weighted embedding average | Important events weight more |
| EpsAdjuster | Learn optimal eps | Per-space tuning |
| ClusterQualityTracker | Closed-loop feedback | Silhouette-based monitoring |

---

## R2-7. Composite Distance

**Location:** `k0/modules/consolidation/algorithms/composite_distance.py`

### Core Formula

```
distance = semantic_weight × cosine_distance + temporal_weight × time_distance
```

Where:

- `cosine_distance = 1 - cosine_similarity(emb_a, emb_b)`
- `time_distance = min(1.0, |ts_a - ts_b| / max_temporal_gap_ms)`

### Distance Interpretation

| Distance | Meaning |
|----------|---------|
| 0.0 | Identical (same embedding, same time) |
| 0.0 - 0.15 | Very similar (should cluster with eps=0.15) |
| 0.15 - 0.30 | Moderately similar |
| 0.30 - 0.50 | Dissimilar |
| > 0.50 | Very different |
| ∞ (infinity) | Exceeds temporal gap (cannot cluster) |

### CompositeDistance Class

```python
class CompositeDistance:
    def compute(self, event_a, event_b) -> float:
        # Step 1: Check temporal hard limit
        time_diff_ms = abs(event_a.timestamp - event_b.timestamp)
        if time_diff_ms > self.params.max_temporal_gap_ms:
            return float("inf")  # Cannot cluster

        # Step 2: Compute semantic distance
        semantic_dist = self._cosine_distance(
            event_a.embedding_768,
            event_b.embedding_768
        )

        # Step 3: Compute normalized temporal distance
        temporal_dist = min(1.0, time_diff_ms / self.params.max_temporal_gap_ms)

        # Step 4: Weighted combination
        return (
            self.params.semantic_weight * semantic_dist
            + self.params.temporal_weight * temporal_dist
        )

    def _cosine_distance(self, emb_a, emb_b) -> float:
        """cosine_distance = 1 - cosine_similarity"""
        arr_a = np.asarray(emb_a, dtype=np.float32)
        arr_b = np.asarray(emb_b, dtype=np.float32)

        norm_a = np.linalg.norm(arr_a)
        norm_b = np.linalg.norm(arr_b)

        if norm_a < 1e-10 or norm_b < 1e-10:
            return 1.0  # Treat zero vectors as orthogonal

        cosine_similarity = np.dot(arr_a, arr_b) / (norm_a * norm_b)
        return 1.0 - cosine_similarity

    def build_distance_matrix(self, events) -> np.ndarray:
        """Build n×n symmetric distance matrix for DBSCAN."""
        n = len(events)
        distances = np.zeros((n, n), dtype=np.float32)

        for i in range(n):
            for j in range(i + 1, n):
                dist = self.compute(events[i], events[j])
                distances[i, j] = dist
                distances[j, i] = dist

        return distances
```

---

## R2-8. Episode Splitting

**Location:** `k0/modules/consolidation/algorithms/episode_splitter.py`

### Purpose

Pre-split long event sequences BEFORE clustering to prevent cross-activity episodes. For example, "morning at home" should not cluster with "afternoon at office" even if semantically similar.

### Split Signals (Priority Order)

| Signal | Threshold | Example |
|--------|-----------|---------|
| Location Change | geohash differs by >4 chars | Home → Office |
| Activity Change | activity_type changes | work → recreation |
| Time Gap | gap > 30 minutes | 9am event ... 11am event |
| Hard Limit | episode > 4 hours | Force split at 4h boundary |

### SplitConfig

```python
@dataclass(frozen=True)
class SplitConfig:
    max_episode_hours: float = 4.0        # Hard limit
    time_gap_minutes: float = 30.0        # Gap threshold
    geohash_distance_threshold: int = 4   # Location sensitivity

    @property
    def max_episode_ms(self) -> int:
        return int(self.max_episode_hours * 3_600_000)

    @property
    def time_gap_ms(self) -> int:
        return int(self.time_gap_minutes * 60_000)
```

### EpisodeSplitter Algorithm

```python
class EpisodeSplitter:
    def split(self, events: Sequence) -> SplitResult:
        """Split event sequence into episodes."""
        episodes = []
        current_episode = []
        episode_start_ts = None

        for event in events:
            if not current_episode:
                # First event starts new episode
                current_episode.append(event)
                episode_start_ts = event.timestamp
                continue

            # Check for split condition
            prev_event = current_episode[-1]
            split_reason = self._detect_break(prev_event, event, episode_start_ts)

            if split_reason != SplitReason.NONE:
                # End current, start new
                episodes.append(current_episode)
                current_episode = [event]
                episode_start_ts = event.timestamp
            else:
                current_episode.append(event)

        # Don't forget last episode
        if current_episode:
            episodes.append(current_episode)

        return SplitResult(episodes=episodes, ...)

    def _detect_break(self, prev, curr, episode_start_ts) -> str:
        # Priority 1: Location change
        if self._geohash_distance(prev.geohash, curr.geohash) > threshold:
            return SplitReason.LOCATION_CHANGE

        # Priority 2: Activity change
        if prev.activity_type != curr.activity_type:
            return SplitReason.ACTIVITY_CHANGE

        # Priority 3: Time gap
        if curr.timestamp - prev.timestamp > self.config.time_gap_ms:
            return SplitReason.TIME_GAP

        # Priority 4: Hard limit
        if curr.timestamp - episode_start_ts > self.config.max_episode_ms:
            return SplitReason.HARD_LIMIT

        return SplitReason.NONE

    def _geohash_distance(self, gh1, gh2) -> int:
        """Distance = chars from first difference."""
        min_len = min(len(gh1), len(gh2))
        for i in range(min_len):
            if gh1[i] != gh2[i]:
                return max(len(gh1), len(gh2)) - i
        return abs(len(gh1) - len(gh2))
```

### Geohash Distance Examples

| Geohash A | Geohash B | Distance | Interpretation |
|-----------|-----------|----------|----------------|
| u4pruyd | u4pruyd | 0 | Same location |
| u4pruyd | u4pruyc | 1 | Adjacent cell |
| u4pruyd | u4pru00 | 2 | Nearby |
| u4pruyd | gcpvj0d | 7 | Different city |

---

## R2-9. DBSCAN & HDBSCAN Clustering

### EpisodicDBSCAN

**Location:** `k0/modules/consolidation/algorithms/episodic_dbscan.py`

Standard DBSCAN with precomputed composite distance matrix:

```python
class EpisodicDBSCAN:
    def cluster(self, events) -> ClusteringResult:
        # Step 1: Build distance matrix
        distances = self.distance_calculator.build_distance_matrix(events)

        # Step 2: Cap infinity values (sklearn can't handle inf)
        distances = np.clip(distances, 0.0, 1e10)

        # Step 3: Run sklearn DBSCAN
        sklearn_dbscan = DBSCAN(
            eps=self.params.eps,
            min_samples=self.params.min_samples,
            metric="precomputed",
        )
        sklearn_dbscan.fit(distances)

        labels = sklearn_dbscan.labels_.tolist()
        # labels: -1 = noise, 0+ = cluster ID

        # Step 4: Group events by label
        label_to_events = {}
        for idx, label in enumerate(labels):
            label_to_events.setdefault(label, []).append(events[idx])

        # Step 5: Create EpisodeCluster objects
        clusters = []
        for label, cluster_events in label_to_events.items():
            cluster = self._create_cluster(cluster_events, label)
            clusters.append(cluster)

        return ClusteringResult(clusters, ...)
```

### EpisodicHDBSCAN (Preferred)

**Location:** `k0/modules/consolidation/algorithms/episodic_hdbscan.py`

HDBSCAN provides better handling of variable-density clusters and noise rescue:

```python
class EpisodicHDBSCAN:
    def cluster(self, events) -> HDBSCANClusteringResult:
        distances = self.distance_calculator.build_distance_matrix(events)
        distances = np.clip(distances, 0.0, 1e10)

        # Run HDBSCAN
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self.params.min_cluster_size,
            min_samples=self.params.min_samples,
            metric="precomputed",
            cluster_selection_method=self.params.cluster_selection_method,
        )
        clusterer.fit(distances)

        labels = clusterer.labels_.tolist()
        probabilities = clusterer.probabilities_.tolist()
        outlier_scores = clusterer.outlier_scores_.tolist()

        # Rescue noise with low outlier scores
        labels, rescued_indices = self._rescue_noise(
            events, labels, probabilities, outlier_scores, distances
        )

        return HDBSCANClusteringResult(
            clusters=clusters,
            labels=labels,
            probabilities=probabilities,
            outlier_scores=outlier_scores,
            rescued_count=len(rescued_indices),
        )
```

### Noise Rescue Algorithm

```python
def _rescue_noise(self, events, labels, probs, outlier_scores, distances):
    """Rescue noise points with low outlier scores."""
    rescued = []

    for idx in range(len(labels)):
        if labels[idx] != -1:  # Not noise
            continue

        if outlier_scores[idx] >= self.params.noise_rescue_threshold:
            continue  # Too outlier-like, keep as noise

        # Find nearest cluster
        best_cluster = -1
        best_distance = float("inf")

        for j in range(len(labels)):
            if labels[j] >= 0 and distances[idx, j] < best_distance:
                best_distance = distances[idx, j]
                best_cluster = labels[j]

        if best_cluster >= 0 and best_distance < 0.3:
            # Rescue: assign to nearest cluster
            labels[idx] = best_cluster
            rescued.append(idx)
        else:
            # Create weak cluster from nearby noise
            nearby = [j for j in range(len(labels))
                      if labels[j] == -1 and distances[idx, j] < 0.2
                      and outlier_scores[j] < self.params.noise_rescue_threshold]
            if nearby:
                new_cluster = max(labels) + 1
                labels[idx] = new_cluster
                for j in nearby:
                    labels[j] = new_cluster
                rescued.extend([idx] + nearby)

    return labels, rescued
```

### Cluster Cohesion Calculation

```python
def _compute_cohesion(self, events) -> float:
    """Average pairwise cosine similarity within cluster."""
    if len(events) < 2:
        return 1.0

    embeddings = [np.asarray(e.embedding_768) for e in events
                  if e.embedding_768 is not None]

    if len(embeddings) < 2:
        return 1.0

    total_sim = 0.0
    count = 0

    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            sim = np.dot(embeddings[i], embeddings[j]) / (
                np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j])
            )
            total_sim += max(0.0, min(1.0, sim))
            count += 1

    return total_sim / count if count > 0 else 1.0
```

---

## R2-10. Centroid Calculation

**Location:** `k0/modules/consolidation/algorithms/centroid_calculator.py`

### Purpose

Compute a representative embedding for each episode cluster. The centroid is used for:

- Episode similarity search in K1
- Duplicate detection in R3
- Clustering quality measurement

### Weighting Strategies

| Strategy | Formula | Use Case |
|----------|---------|----------|
| UNIFORM | `weight = 1/n` | All events equal |
| IMPORTANCE | `weight = importance_score` | Key moments matter more |
| RECENCY | `weight = (ts - min_ts) / range` | Recent events matter more |
| HYBRID | `0.7 × importance + 0.3 × recency` | Default, balanced |

### CentroidCalculator Class

```python
class CentroidCalculator:
    def compute_weights(self, events, strategy) -> np.ndarray:
        n = len(events)

        if strategy == "uniform":
            return np.ones(n) / n

        elif strategy == "importance":
            weights = np.array([e.importance_score for e in events])
            weights = weights + 0.01  # Avoid zero weights
            return weights / weights.sum()

        elif strategy == "recency":
            timestamps = np.array([e.timestamp for e in events])
            if timestamps.max() == timestamps.min():
                return np.ones(n) / n
            recency = (timestamps - timestamps.min()) / (timestamps.max() - timestamps.min())
            weights = recency + 0.1
            return weights / weights.sum()

        elif strategy == "hybrid":
            importance = np.array([e.importance_score for e in events])
            timestamps = np.array([e.timestamp for e in events])
            recency = (timestamps - timestamps.min()) / (timestamps.max() - timestamps.min() + 1)
            weights = 0.7 * importance + 0.3 * recency + 0.01
            return weights / weights.sum()

    def compute_centroid(self, events, strategy="hybrid") -> np.ndarray:
        """Weighted average of embeddings, L2-normalized."""
        valid = [e for e in events if e.embedding_768 is not None]
        weights = self.compute_weights(valid, strategy)

        # Stack embeddings: (n, 768)
        embeddings = np.stack([np.asarray(e.embedding_768) for e in valid])

        # Weighted sum
        centroid = np.sum(embeddings * weights[:, np.newaxis], axis=0)

        # L2 normalize for cosine similarity
        norm = np.linalg.norm(centroid)
        if norm > 1e-10:
            centroid = centroid / norm

        return centroid

    def compute_variance(self, events, centroid) -> float:
        """Variance from centroid (lower = tighter cluster)."""
        embeddings = [np.asarray(e.embedding_768) for e in events
                      if e.embedding_768 is not None]

        if not embeddings:
            return 0.0

        # Cosine distances from centroid
        similarities = [np.dot(emb, centroid) for emb in embeddings]
        distances = [1.0 - sim for sim in similarities]

        return float(np.mean(np.square(distances)))
```

### CentroidResult

```python
@dataclass
class CentroidResult:
    centroid: np.ndarray     # 768-dim L2-normalized
    variance: float          # Distance from centroid
    weights: np.ndarray      # Weight per event
    strategy: str            # Weighting strategy used
    event_count: int         # Events with valid embeddings

    @property
    def centroid_list(self) -> List[float]:
        return self.centroid.tolist()
```

---

## R2-11. Adaptive Learning

### EpsAdjuster

**Location:** `k0/modules/consolidation/algorithms/eps_adjuster.py`

Automatically tunes the DBSCAN `eps` parameter per-space based on cluster quality.

#### Problem

Fixed `eps=0.25` doesn't suit all spaces:

- **Tight spaces** (single-topic): Events cluster too broadly → need lower eps
- **Loose spaces** (multi-domain): Events fail to cluster → need higher eps

#### Algorithm

```python
class EpsAdjuster:
    DEFAULT_EPS = 0.15  # Tighter for UltraBERT L2-normalized embeddings

    def adjust(self, current_eps, silhouette_score, avg_cluster_size,
               singleton_rate, total_clusters_formed) -> EpsAdjustmentResult:

        # Cold start: skip if < 100 clusters formed
        if total_clusters_formed < self.config.cold_start_threshold:
            return EpsAdjustmentResult(adjusted=False, reason="Cold start")

        # Quality acceptable: skip if silhouette >= 0.5
        if silhouette_score >= 0.5 and avg_cluster_size <= 10:
            return EpsAdjustmentResult(adjusted=False, reason="Quality OK")

        # Clusters too loose: decrease eps
        if avg_cluster_size > 10:
            eps_adjusted = current_eps - 0.02
            reason = "Clusters too loose → DECREASE eps"

        # Too much noise: increase eps
        elif singleton_rate > 0.20:
            eps_adjusted = current_eps + 0.02
            reason = "Too much noise → INCREASE eps"

        else:
            return EpsAdjustmentResult(adjusted=False)

        # Momentum smoothing: 90% old + 10% new
        eps_smoothed = 0.9 * current_eps + 0.1 * eps_adjusted

        # Clamp to bounds [0.15, 0.40]
        eps_clamped = max(0.15, min(0.40, eps_smoothed))

        return EpsAdjustmentResult(
            previous_eps=current_eps,
            new_eps=eps_clamped,
            adjusted=True,
            reason=reason,
        )
```

#### EpsAdjustmentConfig

```python
@dataclass(frozen=True)
class EpsAdjustmentConfig:
    eps_min: float = 0.15              # Tightest clustering
    eps_max: float = 0.40              # Loosest clustering
    eps_step: float = 0.02             # Adjustment increment
    silhouette_target: float = 0.5     # Quality threshold
    momentum: float = 0.9              # Smoothing factor
    cold_start_threshold: int = 100    # Clusters before learning
    avg_cluster_size_high: float = 10.0
    singleton_rate_high: float = 0.20
```

### MinSamplesAdjuster

**Location:** `k0/modules/consolidation/algorithms/min_samples_adjuster.py`

Tunes DBSCAN `min_samples` based on noise level.

#### Adjustment Rules

| Singleton Rate | Diagnosis | Action | New min_samples |
|----------------|-----------|--------|-----------------|
| > 20% | Too noisy | Increase | +1 |
| < 5% | Too strict | Decrease | -1 |
| 5-20% | Good balance | Keep | unchanged |

**Bounds:** `min_samples ∈ [2, 5]`

```python
class MinSamplesAdjuster:
    DEFAULT_MIN_SAMPLES = 2

    def adjust(self, current_min_samples, singleton_rate) -> MinSamplesAdjustmentResult:
        # High noise: increase threshold
        if singleton_rate > 0.20:
            new = min(5, current_min_samples + 1)
            return MinSamplesAdjustmentResult(new, adjusted=True, direction="increase")

        # Low noise: decrease threshold
        if singleton_rate < 0.05:
            new = max(2, current_min_samples - 1)
            return MinSamplesAdjustmentResult(new, adjusted=True, direction="decrease")

        # Good balance
        return MinSamplesAdjustmentResult(current_min_samples, adjusted=False)
```

### Storage: st_learned_weights

Both adjusters persist learned parameters:

```sql
INSERT INTO st_learned_weights (
    param_key,           -- 'dbscan_eps' or 'dbscan_min_samples'
    param_scope,         -- 'space'
    space_id,
    current_value,
    prior_value,
    confidence,          -- silhouette score
    sample_count,
    last_updated_at
) VALUES (...)
ON CONFLICT DO UPDATE SET
    prior_value = current_value,
    current_value = $new_value,
    sample_count = sample_count + 1
```

---

## R2-12. Quality Tracking

**Location:** `k0/modules/consolidation/algorithms/cluster_quality.py`

### Problem

No ground truth labels for clusters (unsupervised learning). Need proxy metrics to evaluate quality.

### Quality Signals

| Signal | Source | Weight | Target | Interpretation |
|--------|--------|--------|--------|----------------|
| Silhouette Score | sklearn | 0.40 | > 0.5 | Cluster cohesion/separation |
| Grounding Rate | K1 feedback | 0.30 | > 0.6 | % clusters used by K1 |
| Correction Rate | User feedback | 0.20 | < 0.05 | User corrections / cluster |
| Singleton Rate | R2 output | 0.10 | < 0.20 | Noise % of total |

### Composite Quality Formula

```
composite = 0.40 × silhouette
          + 0.30 × grounding_rate
          + 0.20 × (1 - correction_rate)
          + 0.10 × (1 - singleton_rate)
```

Range: `[0, 1]` where 1.0 = perfect clustering
Target: `> 0.5` for acceptable quality

### ClusterQualityMetrics

```python
@dataclass
class ClusterQualityMetrics:
    # Core metrics [0, 1]
    silhouette_score: float = 0.0
    grounding_rate: float = 0.0
    correction_rate: float = 0.0
    singleton_rate: float = 0.0
    composite_quality: float = 0.0

    # Raw counts
    total_clusters: int = 0
    grounded_clusters: int = 0
    corrected_clusters: int = 0
    singleton_clusters: int = 0

    # Metadata
    space_id: str = ""
    cycle_id: str = ""
    computed_at: int = 0  # MILLISECONDS

    def compute_composite(self) -> float:
        normalized_silhouette = (self.silhouette_score + 1.0) / 2.0
        self.composite_quality = (
            0.40 * normalized_silhouette
            + 0.30 * self.grounding_rate
            + 0.20 * (1.0 - self.correction_rate)
            + 0.10 * (1.0 - self.singleton_rate)
        )
        return max(0.0, min(1.0, self.composite_quality))

    @property
    def is_acceptable(self) -> bool:
        return self.composite_quality > 0.5
```

### ClusterQualityTracker

```python
class ClusterQualityTracker:
    def __init__(self, alert_threshold=0.3, consecutive_failures=3):
        self.alert_threshold = alert_threshold
        self.consecutive_failures = consecutive_failures
        self._recent_scores = []

    async def compute_metrics(self, space_id, r2_output, db_conn) -> ClusterQualityMetrics:
        metrics = ClusterQualityMetrics(space_id=space_id)

        # From R2 output
        metrics.silhouette_score = r2_output.batch_silhouette_score
        metrics.total_clusters = r2_output.cluster_count + r2_output.noise_count
        metrics.singleton_clusters = r2_output.noise_count

        # Query grounding feedback
        grounded = await db_conn.fetchval("""
            SELECT COUNT(DISTINCT payload->>'epi_id')
            FROM st_feedback_signals
            WHERE space_id = $1 AND signal_type = 'CLUSTER_GROUNDED'
        """, space_id)
        metrics.grounded_clusters = grounded or 0

        # Query correction feedback
        corrected = await db_conn.fetchval("""
            SELECT COUNT(DISTINCT payload->>'epi_id')
            FROM st_feedback_signals
            WHERE space_id = $1 AND signal_type = 'CLUSTER_WRONG'
        """, space_id)
        metrics.corrected_clusters = corrected or 0

        metrics.compute_rates()
        metrics.compute_composite()
        return metrics

    def check_for_alert(self, metrics) -> Optional[str]:
        """Alert if silhouette < threshold for N consecutive cycles."""
        self._recent_scores.append(metrics.silhouette_score)
        if len(self._recent_scores) > self.consecutive_failures:
            self._recent_scores.pop(0)

        if len(self._recent_scores) >= self.consecutive_failures:
            if all(s < self.alert_threshold for s in self._recent_scores):
                return f"CLUSTER_QUALITY_DEGRADED: silhouette < {self.alert_threshold} for {self.consecutive_failures} cycles"

        return None

    def get_tuning_recommendation(self, metrics) -> Dict[str, str]:
        """Map quality issues to parameter adjustments."""
        recommendations = {}

        if metrics.silhouette_score < 0.5:
            if metrics.singleton_rate > 0.20:
                recommendations["eps"] = "INCREASE (too much noise)"
            else:
                recommendations["eps"] = "DECREASE (clusters too loose)"

        if metrics.singleton_rate > 0.20:
            recommendations["min_samples"] = "INCREASE (too many singletons)"

        if metrics.singleton_rate < 0.05:
            recommendations["min_samples"] = "DECREASE (too strict)"

        return recommendations
```

---

## R2-13. Configuration

### Default Values Summary

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_batch_size` | 2 | Skip if fewer events |
| `eps` | 0.07 | DBSCAN radius (0 = adaptive) |
| `min_samples` | 2 | Min core point neighbors |
| `semantic_weight` | 0.7 | Embedding distance weight |
| `temporal_weight` | 0.3 | Time distance weight |
| `time_gap_minutes` | 60 | Split threshold |
| `max_temporal_gap_hours` | 4.0 | Hard clustering limit |
| `use_hdbscan` | True | Use HDBSCAN vs DBSCAN |
| `noise_rescue_threshold` | 0.5 | Rescue noise below this |
| `cluster_selection_method` | "leaf" | Preserve small clusters |

### Database Tables Accessed

| Table | Access | Purpose |
|-------|--------|---------|
| `st_learned_weights` | READ/WRITE | Load/save eps, min_samples |
| `st_feedback_signals` | READ | Grounding/correction counts |
| `st_consolidation_audit` | WRITE (staged) | Quality metrics |

---

## R2-14. Code Walkthrough

### Main Entry Point

```python
class R2EpisodicIntegrator:
    PHASE_ID = P03PhaseId.R2_CLUSTER

    async def run(self, envelope, ctx) -> P03PhaseResult:
        # 1. Skip check
        if self.should_skip(envelope):
            return P03PhaseResult.skip(...)

        # 2. Initialize components
        self._initialize_components(ctx)

        # 3. Get clustering params
        dbscan_params = await self._get_dbscan_params(ctx, space_id)

        # 4. Filter events with embeddings
        events_with_embeddings = [e for e in envelope.events
                                   if e.embedding_768 is not None]

        # 5. Split into sequences
        sequences = self._split_events(adapted_events)

        # 6. Cluster each sequence
        all_results = []
        for sequence in sequences:
            result = self._clusterer.cluster(sequence)
            all_results.append(result)

        # 7. Compute centroids
        for cluster in clustering_result.clusters:
            centroid_result = self._centroid_calculator.compute(
                cluster_events,
                strategy=self.config.weighting_strategy
            )
            episode_candidate = ...

        # 8. Canonicalize episodes
        if self.config.enable_canonicalization:
            episode_clusters, merge_count = self._canonicalize_episodes(...)

        # 9. Update event states
        self._update_event_states(envelope.events, all_results, noise_ids)

        # 10. Populate envelope outputs
        envelope.phases.r2_clusters = episode_clusters
        envelope.phases.r2_noise_event_ids = noise_ids
        envelope.phases.r2_clustering_params = {...}

        # 11. Track quality & adapt
        quality_metrics = await self._track_quality_and_adapt(...)

        return P03PhaseResult.done(...)
```

### Key Helper Methods

```python
def _initialize_components(self, ctx):
    """Initialize all algorithm components."""
    # Splitter
    self._splitter = EpisodeSplitter(SplitConfig(
        time_gap_minutes=self.config.time_gap_minutes
    ))

    # Clusterer (HDBSCAN or DBSCAN)
    if self.config.use_hdbscan:
        self._clusterer = EpisodicHDBSCAN(HDBSCANParams(...))
    else:
        self._clusterer = EpisodicDBSCAN(DBSCANParams(...))

    # Centroid calculator
    self._centroid_calculator = CentroidCalculator()

    # Quality tracker
    self._quality_tracker = ClusterQualityTracker()

    # Adaptive adjusters
    self._eps_adjuster = EpsAdjuster()
    self._min_samples_adjuster = MinSamplesAdjuster()

async def _get_dbscan_params(self, ctx, space_id) -> DBSCANParams:
    """Get params from config or learned values."""
    eps = self.config.eps if self.config.eps > 0 else 0.07
    min_samples = self.config.min_samples if self.config.min_samples > 0 else 2

    # Try learned params
    if hasattr(ctx.syscalls, "get_learned_param"):
        learned_eps = await ctx.syscalls.get_learned_param(
            space_id=space_id, param_key="dbscan_eps"
        )
        if learned_eps is not None:
            eps = learned_eps

    return DBSCANParams(eps=eps, min_samples=min_samples)

def _canonicalize_episodes(self, episodes) -> Tuple[List, int]:
    """Merge episodes with same signature."""
    # Signature = (episode_type, location, time_bucket)
    bucket_ms = self.config.canonicalization_time_bucket_hours * 3600 * 1000

    signature_groups = defaultdict(list)
    for ep in episodes:
        time_bucket = ep.temporal_start // bucket_ms
        episode_type = self._infer_episode_type(ep)
        signature = (episode_type, ep.location_hint or "", time_bucket)
        signature_groups[signature].append(ep)

    # Merge groups with >1 episode
    canonical = []
    merge_count = 0
    for group in signature_groups.values():
        if len(group) == 1:
            canonical.append(group[0])
        else:
            merged = self._merge_episodes(group)
            canonical.append(merged)
            merge_count += len(group) - 1

    return canonical, merge_count
```

---

## Complete R2 File Dependencies Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    R2 EPISODIC INTEGRATOR                        │
│            r2_episodic_integrator.py (1221 lines)                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ALGORITHMS USED:                                               │
│  ├── composite_distance.py ────▶ CompositeDistance, DBSCANParams │
│  │   ├── compute(event_a, event_b) → float                      │
│  │   └── build_distance_matrix(events) → np.ndarray             │
│  │                                                               │
│  ├── episode_splitter.py ──────▶ EpisodeSplitter, SplitConfig   │
│  │   ├── split(events) → SplitResult                            │
│  │   └── _detect_break(prev, curr) → SplitReason                │
│  │                                                               │
│  ├── episodic_hdbscan.py ──────▶ EpisodicHDBSCAN, HDBSCANParams  │
│  │   ├── cluster(events) → HDBSCANClusteringResult              │
│  │   └── _rescue_noise(labels, outlier_scores) → rescued        │
│  │                                                               │
│  ├── centroid_calculator.py ───▶ CentroidCalculator             │
│  │   ├── compute_weights(events, strategy) → np.ndarray         │
│  │   ├── compute_centroid(events) → np.ndarray                  │
│  │   └── compute_variance(events, centroid) → float             │
│  │                                                               │
│  ├── eps_adjuster.py ──────────▶ EpsAdjuster                    │
│  │   └── adjust(eps, silhouette, ...) → EpsAdjustmentResult     │
│  │                                                               │
│  ├── min_samples_adjuster.py ──▶ MinSamplesAdjuster             │
│  │   └── adjust(min_samples, singleton_rate) → Result           │
│  │                                                               │
│  └── cluster_quality.py ───────▶ ClusterQualityTracker          │
│      ├── compute_metrics(r2_output) → ClusterQualityMetrics     │
│      └── check_for_alert(metrics) → Optional[str]               │
│                                                                  │
│  DATABASE ACCESS:                                                │
│  ├── st_learned_weights ────────▶ READ/WRITE (eps, min_samples) │
│  ├── st_feedback_signals ───────▶ READ (grounding/correction)   │
│  └── st_consolidation_audit ────▶ WRITE (quality metrics)       │
│                                                                  │
│  INPUTS:                                                         │
│  └── P03BatchEnvelope ──────────▶ From R1 (with importance)     │
│                                                                  │
│  OUTPUTS:                                                        │
│  ├── envelope.phases.r2_clusters                                │
│  ├── envelope.phases.r2_noise_event_ids                         │
│  ├── envelope.phases.r2_clustering_params                       │
│  └── event.cluster_id, event.is_noise (updated in-place)        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Summary

**R2 Episodic Integrator** clusters events into coherent episodes using:

1. **Pre-splitting** by time gaps, location changes, activity changes
2. **HDBSCAN clustering** with composite distance (semantic + temporal)
3. **Noise rescue** for borderline points with low outlier scores
4. **Weighted centroids** using importance scores
5. **Episode canonicalization** to merge same-signature episodes
6. **Adaptive learning** of eps and min_samples per-space
7. **Quality tracking** via silhouette score and feedback signals

The phase transforms flat event lists into structured episodes ready for R3 dedup/decay and R4 knowledge graph extraction.

---

# R3: Deduplication & Decay Phase

## R3-1. Overview

**Purpose**: Wire together 13 algorithms (4.3.1-4.3.13) to handle duplicate detection, decay computation, retention decisions, immunity checking, audit logging, regret detection, and truth reconciliation.

**Phase ID**: `P03PhaseId.R3_PRUNE`

**Spec Reference**: Dossier §4.3, M4_EXECUTION.md Issue 4.3.12

---

## R3-2. Table of Contents

| Section | Topic |
| ------- | ----- |
| R3-1 | Overview |
| R3-2 | Table of Contents |
| R3-3 | R3 Sub-Phases |
| R3-4 | Core Files & Dependencies |
| R3-5 | R3Config & R3Stores |
| R3-6 | R3.1 - Duplicate Detection (SimHash, TwoStage) |
| R3-7 | R3.2 - Novelty Scoring |
| R3-8 | R3.3 - Decay Computation |
| R3-9 | R3.4 - Retention Evaluation |
| R3-10 | R3.5 - Immunity Checking |
| R3-11 | R3.6 - Audit Logging |
| R3-12 | R3.7 - Access Tracking & Lambda Learning |
| R3-13 | R3.8 - Prune Regret Detection |
| R3-14 | R3.9 - Scale Optimization (MinHash LSH) |
| R3-15 | R3.10 - Truth Reconciliation |
| R3-16 | Main Execution Flow |
| R3-17 | R3PhaseStats |
| R3-18 | Summary |

---

## R3-3. R3 Sub-Phases

| Sub-Phase | Issue | Algorithm | Purpose |
| --------- | ----- | --------- | ------- |
| R3.1 | 4.3.1, 4.3.2, 4.3.7 | SimHasher, TwoStageDeduplicator, DuplicateDetector | Duplicate detection |
| R3.2 | 4.3.8 | AdaptiveNoveltyBonusLearner | Novelty scoring with learned bonuses |
| R3.3 | 4.3.3 | UnifiedDecayEngine | Exponential decay computation |
| R3.4 | 4.3.4 | RetentionEnforcer | KEEP/ARCHIVE/TOMBSTONE decisions |
| R3.5 | 4.3.9 | ImmunityChecker | Protect core identity facts |
| R3.6 | 4.3.10 | PruneAuditLogger | GDPR compliance logging |
| R3.7 | 4.3.5 | AccessTracker, BayesianLambdaEstimator | Per-entity λ learning |
| R3.8 | 4.3.6 | PruneRegretDetector, PrunedEntityTracker | Detect queries on pruned entities |
| R3.9 | 4.3.11 | MinHashLSH, AdaptiveDeduplicationStrategy | Scale optimization (>50K events) |
| R3.10 | 4.3.13 | ReconciliationEngine | Truth layer reconciliation |

---

## R3-4. Core Files & Dependencies

```
k0/pipelines/p03/phases/r3_dedup_decay.py (1507 lines)
├── R3Config, R3Stores, R3PhaseStats, R3DedupDecay
│
k0/modules/consolidation/algorithms/
├── simhasher.py (168 lines) ──────────────▶ SimHasher
│   └── 64-bit fingerprint, Hamming distance, per-content-type thresholds
│
├── two_stage_dedup.py (327 lines) ────────▶ TwoStageDeduplicator
│   ├── Stage1SimHashFilter (fast O(n))
│   └── Stage2EmbeddingVerifier (cosine similarity)
│
├── duplicate_detector.py (511 lines) ─────▶ DuplicateDetector
│   └── Novelty scoring with bonuses/penalties
│
├── decay_engine.py (452 lines) ───────────▶ UnifiedDecayEngine
│   └── decay_factor = exp(-λ_effective × days)
│
├── retention_enforcer.py (533 lines) ─────▶ RetentionEnforcer
│   └── KEEP/ARCHIVE/TOMBSTONE + resurrection
│
├── immunity_checker.py (467 lines) ───────▶ ImmunityChecker
│   └── Entity-level & attribute-level immunity
│
├── prune_audit_logger.py (612 lines) ─────▶ PruneAuditLogger
│   └── GDPR Article 22 compliance
│
├── access_tracker.py (595 lines) ─────────▶ AccessTracker, BayesianLambdaEstimator
│   └── Per-entity λ learning from access patterns
│
├── prune_regret_detector.py (637 lines) ──▶ PruneRegretDetector
│   └── Match queries against pruned entities (14-day window)
│
├── novelty_bonus_learner.py (500 lines) ──▶ AdaptiveNoveltyBonusLearner
│   └── Learn per-space novelty bonuses from feedback
│
├── minhash_lsh.py (805 lines) ────────────▶ MinHashLSH, AdaptiveDeduplicationStrategy
│   └── O(log n) dedup for >50K events
│
└── reconciliation_engine.py (800 lines) ──▶ ReconciliationEngine
    └── REINFORCE/EXTEND/CREATE/EVOLVE/CONTRADICT decisions
```

---

## R3-5. R3Config & R3Stores

### R3Config

```python
@dataclass
class R3Config:
    """Configuration for R3 Deduplication & Decay phase."""

    # Sub-component configurations
    decay_config: Optional[DecayConfig] = None
    access_config: Optional[AccessTrackerConfig] = None
    novelty_config: Optional[NoveltyBonusConfig] = None
    regret_config: Optional[PruneRegretConfig] = None
    dedup_config: Optional[DuplicateDetectorConfig] = None
    immunity_config: Optional[ImmunityCheckerConfig] = None
    audit_config: Optional[PruneAuditLoggerConfig] = None
    minhash_config: Optional[MinHashConfig] = None
    adaptive_config: Optional[AdaptiveStrategyConfig] = None
    reconciliation_config: Optional[ReconciliationConfig] = None

    # Feature flags
    enable_reconciliation: bool = True  # Issue 4.3.13
    is_debug: bool = False
```

### R3Stores

```python
@dataclass
class R3Stores:
    """Container for all R3 storage backends."""

    access_store: AccessStoreProtocol          # Access patterns
    pruned_entity_store: PrunedEntityStoreProtocol  # Pruned entities for regret
    learned_weights_store: LearnedWeightsStoreProtocol  # Novelty bonuses, λ
    audit_store: AuditStoreProtocol            # Prune decisions

    @classmethod
    def create_in_memory(cls) -> "R3Stores":
        """Create in-memory stores for testing."""
        return cls(
            access_store=InMemoryAccessStore(),
            pruned_entity_store=InMemoryPrunedEntityStore(),
            learned_weights_store=InMemoryLearnedWeightsStore(),
            audit_store=InMemoryAuditStore(),
        )
```

---

## R3-6. R3.1 - Duplicate Detection

### SimHasher (Issue 4.3.1)

**Scientific Basis**: Charikar (2002) - Similarity estimation using random projections.

```python
class SimHasher:
    """64-bit SimHash for near-duplicate detection."""

    HASH_BITS = 64

    # Per-content-type Hamming thresholds
    CONTENT_TYPE_THRESHOLDS = {
        "TRANSACTION": 1,      # Financial exactness required
        "CALENDAR_EVENT": 2,   # Structured, small variations matter
        "CONTACT_UPDATE": 2,   # Names/phones must match closely
        "CHAT_MESSAGE": 3,     # Default, mixed content
        "PHOTO_CAPTION": 4,    # Free-form, allow paraphrasing
        "JOURNAL_ENTRY": 4,    # Personal text, subjective
        "VOICE_MEMO": 5,       # ASR transcription has noise
    }
    DEFAULT_THRESHOLD = 3

    def compute_simhash(self, text: str) -> int:
        """
        Compute 64-bit SimHash.

        Algorithm:
        1. Tokenize text into 3-gram shingles
        2. Hash each shingle to 64-bit (MD5)
        3. For each bit: sum +1 (if 1) or -1 (if 0)
        4. Final: bit=1 if sum > 0, else bit=0
        """
        shingles = self.tokenize(text)
        bit_sums = [0] * 64

        for shingle in shingles:
            h = int(hashlib.md5(shingle.encode()).hexdigest()[:16], 16)
            for i in range(64):
                bit_sums[i] += 1 if (h & (1 << i)) else -1

        simhash = 0
        for i in range(64):
            if bit_sums[i] > 0:
                simhash |= (1 << i)
        return simhash

    def hamming_distance(self, hash1: int, hash2: int) -> int:
        """Count differing bits (0-64)."""
        return bin(hash1 ^ hash2).count("1")

    def is_near_duplicate(self, hash1, hash2, content_type) -> Tuple[bool, int]:
        threshold = self.CONTENT_TYPE_THRESHOLDS.get(content_type, 3)
        distance = self.hamming_distance(hash1, hash2)
        return (distance <= threshold, distance)
```

### TwoStageDeduplicator (Issue 4.3.2)

**Problem**: SimHash alone has limitations:

- False Positives: "I ate pizza" vs "I hate pizza" (Hamming=2, opposite meaning)
- False Negatives: "Had pizza for dinner" vs "Ate pizza tonight" (Hamming>3, same meaning)

**Solution**: Combine SimHash syntactic filtering with embedding semantic verification.

```python
class TwoStageDeduplicator:
    """Two-stage pipeline: SimHash filter + embedding verification."""

    def find_duplicates(self, new_event, window_events) -> List[DuplicateMatch]:
        # Stage 1: SimHash filter (fast O(n))
        candidates = self.stage1.find_candidates(new_event, window_events, threshold=3)

        # Stage 2: Embedding verification (accurate)
        matches = []
        for event_id, hamming_dist in candidates:
            event = event_map[event_id]
            is_dup, similarity, decision = self.stage2.verify_duplicate(new_event, event)
            if is_dup:
                matches.append(DuplicateMatch(
                    event_id=event_id,
                    hamming_distance=hamming_dist,
                    embedding_similarity=similarity,
                    decision_type=decision,  # DUPLICATE, LIKELY_DUPLICATE
                    check_method="TWO_STAGE",
                ))

        # Fallback: High embedding similarity even if SimHash missed
        fallback_matches = self._check_embedding_fallback(new_event, window_events)
        matches.extend(fallback_matches)

        return matches
```

**Performance Comparison**:

| Method | Complexity | Precision | Recall | Best For |
| ------ | ---------- | --------- | ------ | -------- |
| SimHash only | O(n) | 0.85 | 0.90 | Fast, syntactic |
| Embedding only | O(n²) | 0.95 | 0.98 | Accurate, slow |
| Two-stage | O(n + k) | 0.93 | 0.95 | Balanced (k ~ 0.01n) |

**Decision Thresholds**:

| Similarity | Decision | Action |
| ---------- | -------- | ------ |
| ≥ 0.95 | DUPLICATE | Merge immediately |
| 0.85-0.94 | DUPLICATE | Merge |
| 0.70-0.84 | LIKELY_DUPLICATE | Flag for review |
| < 0.70 | NOT_DUPLICATE | Process independently |
| ≥ 0.90 (fallback) | SEMANTIC_DUPLICATE | Caught by embedding |

---

## R3-7. R3.2 - Novelty Scoring

### DuplicateDetector (Issue 4.3.7)

Combines SimHash, two-stage dedup, and novelty scoring.

**Novelty Formula** (from Dossier §7.4.2):

```
novelty = base_novelty
          × (1 + first_occurrence_bonus)
          × (1 + milestone_bonus)
          × (1 + rare_pattern_bonus)
          × (1 + temporal_anomaly_bonus)
          × (1 - routine_penalty)
```

**Base Novelty**: `1.0 - max_similarity` (where max_similarity is highest cosine to existing events)

**Bonus/Penalty Values** (defaults):

| Type | Default | Description |
| ---- | ------- | ----------- |
| first_occurrence_bonus | 0.15 | First time seeing this activity category |
| milestone_bonus | 0.20 | Keywords: birthday, wedding, graduation, etc. |
| rare_pattern_bonus | 0.10 | < 5 occurrences in 90 days |
| temporal_anomaly_bonus | 0.10 | Unusual time-of-day for activity |
| routine_penalty | 0.30 | Routine activity (e.g., daily exercise) |

### AdaptiveNoveltyBonusLearner (Issue 4.3.8)

Learns per-space bonus values from feedback signals.

```python
class AdaptiveNoveltyBonusLearner:
    """Learn per-space novelty bonuses from feedback."""

    # Bounds
    BONUS_MIN = 0.05
    BONUS_MAX = 0.30

    # Adjustment amounts per signal
    ADJUSTMENTS = {
        "NOVEL_EVENT_GROUNDED": +0.01,      # User used high-novelty event
        "NOVEL_EVENT_NEVER_QUERIED": -0.02, # High-novelty event ignored
        "USER_SAYS_NOT_NEW": -0.03,         # User says "I knew that"
        "MILESTONE_GROUNDED": +0.01,        # Milestone event was useful
        "RARE_PATTERN_USEFUL": +0.01,       # Rare pattern was queried
    }

    async def process_feedback_signal(self, signal_type, space_id, store):
        current = await self._get_current_bonus(bonus_type, space_id, store)
        new_value = clamp(current + adjustment, 0.05, 0.30)
        await store.upsert_weight(param_key, space_id, new_value)
```

---

## R3-8. R3.3 - Decay Computation

### UnifiedDecayEngine (Issue 4.3.3)

**Scientific Basis**:

- Ebbinghaus (1885): Forgetting curve — memory strength decays exponentially
- Tononi & Cirelli (2006): Synaptic homeostasis hypothesis

**Core Formula**:

$$\text{decay\_factor} = e^{-\lambda_{\text{effective}} \times \text{days\_since\_observed}}$$

### Per-Layer λ Values

| Table | λ (per day) | Half-life (days) |
| ----- | ----------- | ---------------- |
| st_hipp_events | 0.100 | ~7 |
| st_prospective | 0.020 | ~35 |
| st_procedural | 0.010 | ~69 |
| st_kg_edges | 0.008 | ~87 |
| st_epi | 0.005 | ~139 |
| st_sem | 0.003 | ~231 |
| st_social | 0.002 | ~347 |
| st_kg_dom | 0.001 | ~693 |

### Effective Lambda Calculation

```python
def compute_effective_lambda(self, table_name, importance_score, confidence_score,
                              observation_count, space_modifier, entity_type_modifier):
    base = LAYER_LAMBDAS[table_name]

    # importance_score=1.0 → halves λ
    importance_factor = 1.0 - (importance_score * 0.5)

    # confidence_score=1.0 → 30% reduction
    confidence_factor = 1.0 - (confidence_score * 0.3)

    # observation_count=10 → halves λ
    reinforcement_factor = 1.0 / (1.0 + 0.1 * observation_count)

    return base * space_modifier * entity_type_modifier * importance_factor * confidence_factor * reinforcement_factor
```

### Decay Classification

```python
class DecayClassification(Enum):
    ACTIVE = "ACTIVE"              # decay_factor >= 0.10
    ARCHIVE_CANDIDATE = "ARCHIVE"  # 0.01 <= decay_factor < 0.10
    PRUNE_CANDIDATE = "PRUNE"      # decay_factor < 0.01
```

---

## R3-9. R3.4 - Retention Evaluation

### RetentionEnforcer (Issue 4.3.4)

**Decision Logic**:

| Classification | Current Status | Decision |
| -------------- | -------------- | -------- |
| ACTIVE | Any | KEEP |
| ARCHIVE_CANDIDATE | ACTIVE | ARCHIVE |
| ARCHIVE_CANDIDATE | ARCHIVED | KEEP (no action) |
| PRUNE_CANDIDATE | Any | TOMBSTONE |

### Resurrection Formula

When archived/tombstoned record is re-accessed:

$$\text{new\_decay} = \max(0.70, 0.50 + \text{old\_decay} \times 0.50)$$

```python
class RetentionEnforcer:
    RESURRECTION_FLOOR = 0.70
    RESURRECTION_BASE = 0.50
    RESURRECTION_CARRY = 0.50

    def resurrect(self, entity_id, current_decay, trigger):
        new_decay = max(0.70, 0.50 + current_decay * 0.50)
        return ResurrectionResult(
            old_decay=current_decay,
            new_decay=new_decay,
            new_status="ACTIVE",
            trigger=trigger,  # EXPLICIT_ACCESS, ASSOCIATION_HIT, SEARCH_RESULT, etc.
        )
```

---

## R3-10. R3.5 - Immunity Checking

### ImmunityChecker (Issue 4.3.9)

**Purpose**: Prevent decay of core identity facts. Human memory analogy: we don't forget our birthday or family members.

**Two-Level System**:

1. **Entity-Level Immunity**: Entire entity type is immune
2. **Attribute-Level Immunity**: Specific attributes trigger immunity

```python
# Level 1: Entity-level (entire entity never decays)
ENTITY_LEVEL_IMMUNE_TYPES = {"FAMILY_MEMBER"}

# Level 2: Attribute-level (entity immune if attribute present)
ATTRIBUTE_LEVEL_IMMUNITY = {
    "PERSON": {"birthday", "name", "relationship_to_user"},
    "PLACE": {"home_address", "work_address"},
    "EVENT": {"wedding_date", "birth_date", "death_date"},
    "ORGANIZATION": {"employer", "school"},
    "CONCEPT": {"core_value", "religion", "political_affiliation"},
}
```

```python
def should_mark_immune(self, entity_type, entity_attributes) -> ImmunityResult:
    # Level 1: FAMILY_MEMBER → full entity immunity
    if entity_type == "FAMILY_MEMBER":
        return ImmunityResult(is_immune=True, level=ImmunityLevel.ENTITY)

    # Level 2: Check if any immune attributes present
    immune_attrs = ATTRIBUTE_LEVEL_IMMUNITY.get(entity_type, set())
    present = [a for a in immune_attrs if entity_attributes.get(a)]
    if present:
        return ImmunityResult(is_immune=True, level=ImmunityLevel.ATTRIBUTE,
                              protected_attributes=tuple(present))

    return ImmunityResult(is_immune=False, level=ImmunityLevel.NONE)
```

---

## R3-11. R3.6 - Audit Logging

### PruneAuditLogger (Issue 4.3.10)

**Purpose**: Record all prune/archive/tombstone decisions for GDPR Article 22 compliance ("meaningful information about logic involved").

**Storage**: `st_consolidation_audit` table

```python
class PruneAction(Enum):
    ARCHIVE = "ARCHIVE"      # decay < 0.10, reversible
    TOMBSTONE = "TOMBSTONE"  # decay < 0.01, permanent
    PRUNE = "PRUNE"          # Explicit prune decision
    SKIP = "SKIP"            # Decision to NOT prune

class PruneAuditLogger:
    def __init__(self, config):
        self.sample_rate_production = 0.10  # 10% sampling
        self.sample_rate_debug = 1.0        # 100% in debug

    def should_log(self, action: PruneAction) -> bool:
        # TOMBSTONE always logged (100%) - permanent deletion requires audit
        if action == PruneAction.TOMBSTONE:
            return True
        # Other actions sampled
        return random.random() < self.config.sample_rate

    async def log_prune_decision(self, action, context, space_id, tenant_id, cycle_id, store):
        record = PruneAuditRecord(
            audit_id=str(uuid.uuid4()),
            memory_id=context.memory_id,
            action=action,
            formula_used="UnifiedDecayFormula",
            formula_version="1.0",
            inputs_json=json.dumps({
                "decay_factor": context.decay_factor,
                "effective_lambda": context.effective_lambda,
                "days_since_access": context.days_since_access,
                "is_immune": context.is_immune,
            }),
            explanation=self._generate_explanation(action, context),
        )
        await store.insert_audit_record(record)
```

---

## R3-12. R3.7 - Access Tracking & Lambda Learning

### AccessTracker (Issue 4.3.5)

**Purpose**: Track entity access patterns for per-entity decay rate (λ) learning.

```python
@dataclass
class AccessStats:
    entity_id: str
    access_count: int = 0
    first_access_at: int = 0  # ms
    last_access_at: int = 0   # ms
    access_intervals_ms: List[int] = field(default_factory=list)  # Last 10
    spread_days: float = 0.0
    eligible_for_learning: bool = False  # 5+ accesses AND 7+ day spread

class AccessTracker:
    def __init__(self, config):
        self.min_access_count = 5       # Min accesses before learning
        self.min_spread_days = 7        # Min spread between first/last
        self.max_intervals_stored = 10  # Keep last 10 intervals

    async def record_access(self, entity_id, entity_table, accessed_at_ms, store):
        stats = await store.get_access_stats(entity_id, entity_table) or new_stats()

        # Compute interval from last access
        if stats.last_access_at > 0:
            interval_ms = accessed_at_ms - stats.last_access_at
            stats.access_intervals_ms.append(interval_ms)
            stats.access_intervals_ms = stats.access_intervals_ms[-10:]  # Keep last 10

        stats.access_count += 1
        stats.last_access_at = accessed_at_ms
        stats.spread_days = (stats.last_access_at - stats.first_access_at) / MS_PER_DAY
        stats.eligible_for_learning = (stats.access_count >= 5 and stats.spread_days >= 7)

        await store.update_access_stats(stats)
        return stats
```

### BayesianLambdaEstimator

**Scientific Basis**: Maximum Likelihood Estimation for exponential distribution.

$$\lambda_{\text{MLE}} = \frac{n}{\sum(\text{intervals})}$$

```python
class BayesianLambdaEstimator:
    LAMBDA_MIN = 0.0001  # ~6931 day half-life
    LAMBDA_MAX = 0.1     # ~7 day half-life

    def estimate_lambda(self, entity_id, intervals_days) -> LambdaEstimate:
        if len(intervals_days) < 2:
            return None

        # MLE for exponential distribution
        total_days = sum(intervals_days)
        n = len(intervals_days)
        lambda_mle = n / total_days

        # Clamp to bounds
        lambda_value = max(self.LAMBDA_MIN, min(self.LAMBDA_MAX, lambda_mle))

        # Confidence increases with sample count
        confidence = min(1.0, n / 10.0)

        return LambdaEstimate(
            entity_id=entity_id,
            lambda_value=lambda_value,
            confidence=confidence,
            sample_count=n,
            half_life_days=0.693 / lambda_value,
        )
```

---

## R3-13. R3.8 - Prune Regret Detection

### PruneRegretDetector (Issue 4.3.6)

**Purpose**: Detect when pruned entities are later queried (regret).

**Scientific Basis**:

- Weekly patterns (7-day cycles)
- Biweekly patterns (payday, 14-day cycles)
- 90% of regrets occur within 14 days

```python
# Match thresholds
STRONG_MATCH_THRESHOLD = 0.90   # cosine similarity
LIKELY_MATCH_THRESHOLD = 0.85
SEMANTIC_MATCH_THRESHOLD = 0.80

# Retention periods
UNMATCHED_RETENTION_DAYS = 14   # Keep unmatched for 14 days
MATCHED_RETENTION_DAYS = 30     # Keep matched (regret) for 30 days

class PrunedEntityTracker:
    async def track_pruned_entity(self, entity_id, entity_type, canonical_name,
                                   embedding, space_id, layer_table,
                                   decay_factor, lambda_value, pruned_at, store):
        """Called when entity transitions to TOMBSTONE."""
        entity = PrunedEntity(
            prune_id=f"prune_{uuid.uuid4().hex[:16]}",
            entity_id=entity_id,
            embedding=embedding,
            pruned_at=pruned_at,
            decay_factor_at_prune=decay_factor,
        )
        await store.insert_pruned_entity(entity)

class PruneRegretDetector:
    async def check_query(self, query_embedding, space_id, query_id,
                          current_time_ms, store) -> List[RegretMatch]:
        """Check if query matches recently pruned entities."""
        unmatched = await store.get_unmatched_entities(space_id)

        matches = []
        for entity in unmatched:
            similarity = cosine_similarity(query_embedding, entity.embedding)
            match_type = self._classify_match(similarity)

            if match_type != MatchType.NO_MATCH:
                matches.append(RegretMatch(
                    prune_id=entity.prune_id,
                    entity_id=entity.entity_id,
                    match_type=match_type,
                    match_confidence=similarity,
                ))
                await store.update_match(entity.prune_id, query_id,
                                         current_time_ms, match_type, similarity)

        return matches
```

---

## R3-14. R3.9 - Scale Optimization (MinHash LSH)

### MinHashLSH (Issue 4.3.11)

**Problem**: Dedup performance degrades at scale:

- 10K events: ~10ms per new event (acceptable)
- 50K events: ~50ms per new event (slow)
- 100K+ events: >100ms per new event (unacceptable)

**Solution**: MinHash LSH achieves O(log n) candidate retrieval.

**Scientific Basis**: Broder (1997) - Near-duplicate detection using MinHash.

```python
class DeduplicationStrategy(Enum):
    SIMHASH_PAIRWISE = "simhash_pairwise"   # O(n)
    SIMHASH_BUCKETING = "simhash_bucketing" # O(n/b)
    MINHASH_LSH = "minhash_lsh"             # O(log n)

# Auto-switch thresholds
THRESHOLD_PAIRWISE = 10_000   # Below: O(n) pairwise
THRESHOLD_BUCKETING = 50_000  # Below: SimHash bucketing, above: MinHash LSH
```

### MinHashLSH Algorithm

```python
class MinHashLSH:
    def __init__(self, config):
        self.num_hashes = 128     # Total hash functions
        self.num_bands = 32       # LSH bands
        self.rows_per_band = 4    # 128 / 32 = 4
        self.similarity_threshold = 0.85

    def compute_minhash(self, text: str) -> np.ndarray:
        """Compute MinHash signature (128 values)."""
        shingles = self._tokenize_shingles(text, k=3)  # 3-char shingles
        signature = np.full(128, np.iinfo(np.uint64).max, dtype=np.uint64)

        for shingle in shingles:
            for i in range(128):
                h = self._hash_shingle(shingle, seed=i)
                signature[i] = min(signature[i], h)

        return signature

    def index_event(self, event_id: str, signature: np.ndarray):
        """Add event to LSH index."""
        self._signatures[event_id] = signature
        band_hashes = self.hash_bands(signature)
        for band_idx, band_hash in enumerate(band_hashes):
            self._lsh_index[(band_idx, band_hash)].append(event_id)

    def find_candidates(self, signature, exclude_event_id=None) -> List[LSHCandidate]:
        """Find candidates in O(log n)."""
        band_hashes = self.hash_bands(signature)
        match_counts = defaultdict(int)

        for band_idx, band_hash in enumerate(band_hashes):
            for event_id in self._lsh_index.get((band_idx, band_hash), []):
                if event_id != exclude_event_id:
                    match_counts[event_id] += 1

        return [LSHCandidate(event_id, bands, self._estimate_similarity(bands))
                for event_id, bands in match_counts.items()]
```

### AdaptiveDeduplicationStrategy

```python
class AdaptiveDeduplicationStrategy:
    def __init__(self, minhash_lsh):
        self._current_strategy = DeduplicationStrategy.SIMHASH_PAIRWISE
        self._event_count = 0
        self._minhash_lsh = minhash_lsh

    def update_event_count(self, count: int) -> Optional[Tuple[str, str]]:
        self._event_count = count
        new_strategy = self._determine_strategy(count)

        if new_strategy != self._current_strategy:
            old = self._current_strategy.value
            self._current_strategy = new_strategy
            return (old, new_strategy.value)
        return None

    def _determine_strategy(self, count: int) -> DeduplicationStrategy:
        if count < 10_000:
            return DeduplicationStrategy.SIMHASH_PAIRWISE
        elif count < 50_000:
            return DeduplicationStrategy.SIMHASH_BUCKETING
        else:
            return DeduplicationStrategy.MINHASH_LSH
```

---

## R3-15. R3.10 - Truth Reconciliation

### ReconciliationEngine (Issue 4.3.13)

**Purpose**: Determine how incoming events relate to existing truth records.

**Thresholds** (from Dossier Appendix C.1):

| Similarity | Action | Meaning |
| ---------- | ------ | ------- |
| ≥ 0.85 | REINFORCE | Strengthen existing truth |
| 0.60-0.84 | EXTEND | Add detail to existing |
| 0.40-0.59 | EVOLVE | Related but distinct |
| < 0.40 | CONTRADICT or CREATE | Based on context |
| Override: is_duplicate=True | SKIP | Skip processing |
| Override: prune_decision=TOMBSTONE | PRUNE | Mark for deletion |

```python
class ReconciliationEngine:
    def __init__(self, config, truth_query_service=None):
        self._config = config
        self._truth_service = truth_query_service

    async def decide(self, event, space_id, tenant_id) -> ReconciliationDecision:
        # 1. Check overrides
        override = self._check_overrides(event)
        if override:
            return override

        # 2. Get event embedding
        embedding = self._get_event_embedding(event)
        if embedding is None:
            return ReconciliationDecision(action=ReconciliationAction.CREATE)

        # 3. Query truth layers for candidates
        candidates = await self._find_candidates(embedding, space_id, tenant_id)

        # 4. Find best match
        best_match, similarity = self._find_best_match(embedding, candidates)

        # 5. Determine action based on thresholds
        if similarity >= 0.85:
            action = ReconciliationAction.REINFORCE
        elif similarity >= 0.60:
            action = ReconciliationAction.EXTEND
        elif similarity >= 0.40:
            action = ReconciliationAction.EVOLVE
        elif best_match:
            action = ReconciliationAction.CONTRADICT
        else:
            action = ReconciliationAction.CREATE

        # 6. Compute Bayesian confidence
        confidence = self._compute_confidence(similarity, action, len(candidates))

        return ReconciliationDecision(
            action=action,
            best_match_id=best_match.record_id if best_match else None,
            best_match_layer=best_match.layer if best_match else None,
            similarity_score=similarity,
            confidence=confidence,
        )
```

### ReconciliationAction Enum

```python
class ReconciliationAction(Enum):
    REINFORCE = "REINFORCE"   # ≥0.85: Strengthen existing
    EXTEND = "EXTEND"         # 0.60-0.84: Add detail
    CREATE = "CREATE"         # <0.40: New truth record
    EVOLVE = "EVOLVE"         # 0.40-0.59: Related but distinct
    CONTRADICT = "CONTRADICT" # <0.40 with match: Conflicting
    SKIP = "SKIP"             # Duplicate, skip processing
    PRUNE = "PRUNE"           # Tombstoned, mark for deletion
```

### Truth Layers Queried

```python
DEFAULT_TRUTH_LAYERS = (
    "st_epi",        # Episodic memory
    "st_sem",        # Semantic memory
    "st_procedural", # Habits/routines
    "st_social",     # Social relationships
    "st_prospective", # Plans/goals
)
```

---

## R3-16. Main Execution Flow

### R3DedupDecay.run()

```python
async def run(self, envelope, ctx) -> P03PhaseResult:
    # 1. Skip check
    if self.should_skip(envelope):  # No events or no clusters
        return P03PhaseResult.skip(...)

    # 2. Create in-memory stores for this cycle
    stores = R3Stores.create_in_memory()

    # 3. Initialize TruthQueryService for reconciliation
    if self.config.enable_reconciliation:
        self._truth_query_service = TruthQueryService(pool=get_pool())
        self._reconciliation_engine.set_truth_service(self._truth_query_service)

    # 4. Gather existing events for dedup comparison
    existing_events = [e for e in envelope.events if e.embedding_id is not None]

    # 5. Execute full R3 phase
    stats = await self.execute(
        events=envelope.events,
        existing_events=existing_events,
        entities_for_decay=[],  # Evaluated in later cycles
        space_id=space_id,
        tenant_id=tenant_id,
        cycle_id=cycle_id,
        current_time=int(time.time() * 1000),
        stores=stores,
    )

    return P03PhaseResult.done(
        phase_id=P03PhaseId.R3_PRUNE,
        duration_ms=duration_ms,
        outputs_summary={
            "duplicates_found": stats.duplicates_found,
            "near_duplicates_found": stats.near_duplicates_found,
            "distinct_events": stats.distinct_events,
            "avg_novelty": stats.avg_novelty_score,
        },
    )
```

### R3DedupDecay.execute()

```python
async def execute(self, events, existing_events, entities_for_decay,
                  space_id, tenant_id, cycle_id, current_time, stores) -> R3PhaseStats:
    stats = R3PhaseStats()

    # R3.1: Process events for deduplication
    dedup_results = await self.process_events(events, existing_events, space_id, stores)

    for result in dedup_results:
        if result.is_duplicate:
            stats.duplicates_found += 1
        elif result.near_duplicates:
            stats.near_duplicates_found += 1
        else:
            stats.distinct_events += 1

        if result.novelty_score >= 0.7:
            stats.high_novelty_count += 1
        elif result.novelty_score < 0.3:
            stats.low_novelty_count += 1

    # R3.4: Evaluate entities for retention
    batch_result = self.evaluate_retention_batch(entities_for_decay, current_time)

    for result in batch_result.results:
        # Check immunity
        immunity = self.check_immunity(entity_type, entity_attrs)
        if immunity.is_immune:
            stats.immune_count += 1

        # R3.5: Log audit record
        audit_id = await self.log_retention_decision(result, effective_lambda, ...)
        if audit_id:
            stats.decisions_logged += 1
        else:
            stats.decisions_sampled_out += 1

    # R3.8: Update strategy stats
    stats.current_strategy = self.get_current_strategy().value

    # R3.9: Reconciliation
    if self.config.enable_reconciliation:
        recon_decisions = await self.reconcile_batch(events, space_id, tenant_id)

        for decision in recon_decisions.values():
            if decision.action == ReconciliationAction.REINFORCE:
                stats.reinforce_count += 1
            elif decision.action == ReconciliationAction.EXTEND:
                stats.extend_count += 1
            # ... etc

    return stats
```

---

## R3-17. R3PhaseStats

```python
@dataclass
class R3PhaseStats:
    # Duplicate detection
    events_processed: int = 0
    duplicates_found: int = 0
    near_duplicates_found: int = 0
    distinct_events: int = 0

    # Novelty scoring
    avg_novelty_score: float = 0.0
    high_novelty_count: int = 0   # novelty >= 0.7
    low_novelty_count: int = 0    # novelty < 0.3

    # Decay/retention
    entities_evaluated: int = 0
    active_count: int = 0
    archive_candidate_count: int = 0
    prune_candidate_count: int = 0
    keep_count: int = 0
    archive_count: int = 0
    tombstone_count: int = 0

    # Immunity
    immune_count: int = 0
    immune_by_entity: int = 0
    immune_by_attribute: int = 0

    # Audit
    decisions_logged: int = 0
    decisions_sampled_out: int = 0

    # Access tracking
    accesses_recorded: int = 0
    lambda_estimates_created: int = 0

    # Regret detection
    regrets_detected: int = 0
    strong_matches: int = 0
    likely_matches: int = 0

    # Scale optimization
    current_strategy: str = "simhash_pairwise"
    strategy_switches: int = 0
    lsh_queries: int = 0

    # Reconciliation (Issue 4.3.13)
    reconciliation_enabled: bool = False
    reconciliation_count: int = 0
    reinforce_count: int = 0
    extend_count: int = 0
    create_count: int = 0
    evolve_count: int = 0
    contradict_count: int = 0
    skip_count: int = 0
    prune_count: int = 0

    # Timing
    total_duration_ms: float = 0.0
```

---

## R3-18. Complete R3 File Dependencies Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         R3 DEDUP & DECAY ORCHESTRATOR                         │
│                    r3_dedup_decay.py (1507 lines)                             │
├──────────────────────────────────────────────────────────────────────────────┤
│  ALGORITHMS USED (13 total):                                                  │
│                                                                               │
│  R3.1 Duplicate Detection:                                                    │
│  ├── simhasher.py ──────────▶ SimHasher                                      │
│  │   └── 64-bit fingerprint, Hamming distance, content-type thresholds       │
│  ├── two_stage_dedup.py ────▶ TwoStageDeduplicator                           │
│  │   └── Stage1 SimHash filter + Stage2 embedding verification               │
│  └── duplicate_detector.py ─▶ DuplicateDetector                              │
│      └── Novelty scoring with bonuses/penalties                               │
│                                                                               │
│  R3.2 Novelty Scoring:                                                        │
│  └── novelty_bonus_learner.py ─▶ AdaptiveNoveltyBonusLearner                 │
│      └── Learn per-space bonuses from feedback signals                        │
│                                                                               │
│  R3.3 Decay Computation:                                                      │
│  └── decay_engine.py ───────▶ UnifiedDecayEngine                             │
│      └── decay = exp(-λ_effective × days), per-layer λ                        │
│                                                                               │
│  R3.4 Retention Evaluation:                                                   │
│  └── retention_enforcer.py ─▶ RetentionEnforcer                              │
│      └── KEEP/ARCHIVE/TOMBSTONE + resurrection formula                        │
│                                                                               │
│  R3.5 Immunity Checking:                                                      │
│  └── immunity_checker.py ───▶ ImmunityChecker                                │
│      └── Entity-level (FAMILY_MEMBER) & attribute-level immunity              │
│                                                                               │
│  R3.6 Audit Logging:                                                          │
│  └── prune_audit_logger.py ─▶ PruneAuditLogger                               │
│      └── GDPR Article 22 compliance, 10% sampling (100% TOMBSTONE)           │
│                                                                               │
│  R3.7 Access Tracking:                                                        │
│  └── access_tracker.py ─────▶ AccessTracker, BayesianLambdaEstimator         │
│      └── Per-entity λ learning: λ_MLE = n / Σ(intervals)                      │
│                                                                               │
│  R3.8 Prune Regret Detection:                                                 │
│  └── prune_regret_detector.py ─▶ PruneRegretDetector, PrunedEntityTracker    │
│      └── 14-day window, match thresholds: 0.90/0.85/0.80                      │
│                                                                               │
│  R3.9 Scale Optimization:                                                     │
│  └── minhash_lsh.py ────────▶ MinHashLSH, AdaptiveDeduplicationStrategy      │
│      └── Auto-switch: <10K pairwise, 10K-50K bucketing, >50K LSH             │
│                                                                               │
│  R3.10 Truth Reconciliation:                                                  │
│  └── reconciliation_engine.py ─▶ ReconciliationEngine                        │
│      └── Thresholds: ≥0.85 REINFORCE, 0.60-0.84 EXTEND, <0.40 CREATE/CONTRA  │
│                                                                               │
│  DATABASE ACCESS:                                                             │
│  ├── st_learned_weights ─────▶ READ/WRITE (eps, min_samples, novelty bonuses)│
│  ├── st_consolidation_audit ─▶ WRITE (prune decisions)                       │
│  ├── st_pruned_entities ─────▶ WRITE (for regret detection)                  │
│  ├── st_access_log ──────────▶ WRITE (access patterns)                       │
│  └── st_epi, st_sem, etc. ───▶ READ (truth layer queries for reconciliation) │
│                                                                               │
│  INPUTS:                                                                      │
│  └── P03BatchEnvelope ───────▶ From R2 (with clusters)                       │
│                                                                               │
│  OUTPUTS:                                                                     │
│  ├── envelope.phases.r3_dedup_merges                                         │
│  ├── envelope.phases.r3_decay_updates                                        │
│  ├── event.is_duplicate, event.canonical_event_id                            │
│  ├── event.novelty_score, event.decay_score                                  │
│  ├── event.prune_decision, event.immunity_level                              │
│  └── event.reconciliation_action, event.reconciliation_match_id              │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Summary

**R3 Deduplication & Decay Phase** orchestrates 13 algorithms across 10 sub-phases:

1. **Duplicate Detection**: SimHash 64-bit fingerprints + two-stage embedding verification
2. **Novelty Scoring**: Multiplicative formula with adaptive per-space bonuses
3. **Decay Computation**: Exponential decay with per-layer λ and modifiers
4. **Retention Decisions**: KEEP/ARCHIVE/TOMBSTONE based on decay thresholds
5. **Immunity Checking**: Protect FAMILY_MEMBER and core identity attributes
6. **Audit Logging**: GDPR-compliant decision records with 10% sampling
7. **Access Tracking**: Record patterns for Bayesian λ learning
8. **Regret Detection**: Match queries against 14-day pruned entity window
9. **Scale Optimization**: Auto-switch from O(n) to O(log n) at 50K events
10. **Truth Reconciliation**: REINFORCE/EXTEND/CREATE/EVOLVE/CONTRADICT decisions

The phase transforms clustered episodes into consolidated, deduplicated events with decay scores, retention decisions, and truth layer reconciliation actions ready for R4 knowledge graph extraction.

---
---

# R4 KG Consolidator — Complete Deep Dive

> **Pipeline:** P03 Consolidation
> **Phase:** R4 (Knowledge Graph)
> **Location:** `k0/pipelines/p03/phases/r4_kg_consolidator.py`
> **Last Updated:** 2026-01-09

---

## Table of Contents

1. [Overview](#r4-1-overview)
2. [R4 in the Pipeline Context](#r4-2-r4-in-the-pipeline-context)
3. [Core Files & Dependencies](#r4-3-core-files--dependencies)
4. [Step-by-Step Execution Flow](#r4-4-step-by-step-execution-flow)
5. [Data Structures](#r4-5-data-structures)
6. [Database Tables Accessed](#r4-6-database-tables-accessed)
7. [Algorithms — Entity Extraction (4.4.1-4.4.3)](#r4-7-algorithms--entity-extraction-441-443)
8. [Algorithms — Entity Disambiguation (4.4.4-4.4.7)](#r4-8-algorithms--entity-disambiguation-444-447)
9. [Algorithms — Relationship Discovery (4.4.8)](#r4-9-algorithms--relationship-discovery-448)
10. [Algorithms — Causal Inference (4.4.9-4.4.11)](#r4-10-algorithms--causal-inference-449-4411)
11. [Social Relationship Extraction](#r4-11-social-relationship-extraction)
12. [Gap Resolution Integration](#r4-12-gap-resolution-integration)
13. [Configuration](#r4-13-configuration)
14. [Statistics & Metrics](#r4-14-statistics--metrics)
15. [Error Handling](#r4-15-error-handling)
16. [Formulas Reference](#r4-16-formulas-reference)
17. [ASCII Architecture Diagram](#r4-17-ascii-architecture-diagram)
18. [Summary](#r4-18-summary)

---

## R4-1. Overview

**R4 (KG Consolidator)** extracts entities and relationships from events, builds knowledge graph structures, and infers causal patterns. It transforms unstructured event text into structured graph knowledge.

### Key Responsibilities

1. **Entity Extraction** — UltraBERT NER + BERT-NER hybrid extraction
2. **Entity Disambiguation** — Per-type weighted similarity matching
3. **Ambiguous Resolution** — 5-priority context hierarchy
4. **Confidence Routing** — AUTO/FLAG/GAP band routing with P06 emission
5. **Merge Threshold Learning** — Per-entity-type adaptive thresholds
6. **Entity Merging** — Full cascade across 7 tables with undo
7. **Hebbian Co-occurrence** — Edge weights via "fire together, wire together"
8. **Granger Causality** — Temporal precedence → causal direction
9. **Adaptive Causality Thresholds** — Per-category (Health > Social > Habit)
10. **Edge Feedback & Staleness** — Boost/demote/archive based on accuracy
11. **Social Extraction** — Build st_social relationships from UltraBERT

### Sub-Operations (Issue References)

| Sub-Op | Issue | Algorithm |
|--------|-------|-----------|
| 4.4.1 | Entity Extraction | `UltraBERTEntityExtractor` |
| 4.4.2 | Entity Disambiguation | `EntityDisambiguator` |
| 4.4.3 | Hybrid NER | BERT-NER fallback for ner_general |
| 4.4.4 | Ambiguous Resolution | `AmbiguousEntityResolver` |
| 4.4.5 | Confidence Routing | `ConfidenceRouter` |
| 4.4.6 | Merge Thresholds | `AdaptiveMergeThresholds` |
| 4.4.7 | Entity Merger | `EntityMerger` |
| 4.4.8 | Hebbian Learning | `HebbianLearner` |
| 4.4.9 | Granger Causality | `GrangerCausalityInference` |
| 4.4.10 | Causality Thresholds | `AdaptiveCausalityThresholds` |
| 4.4.11 | Edge Feedback | `CausalEdgeFeedbackProcessor`, `CausalEdgeStalenessChecker` |

---

## R4-2. R4 in the Pipeline Context

```
┌─────────────────────────────────────────────────────────────────┐
│                    P03 CONSOLIDATION PIPELINE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐          │
│  │  R0  │──▶│  R1  │──▶│  R2  │──▶│  R3  │──▶│ ▶R4◀ │          │
│  │BATCH │   │SCORE │   │CLUST │   │DEDUP │   │  KG  │          │
│  └──────┘   └──────┘   └──────┘   └──────┘   └──────┘          │
│                                                  │               │
│                                                  │               │
│                              ┌──────┐   ┌──────┐ │              │
│                              │  R6  │◀──│  R5  │◀┘              │
│                              │STAGE │   │DREAM │               │
│                              └──────┘   └──────┘               │
│                                  │                              │
│                                  ▼                              │
│                              ┌──────┐   ┌──────┐               │
│                              │  R7  │──▶│  R8  │               │
│                              │WRITE │   │ EMIT │               │
│                              └──────┘   └──────┘               │
└─────────────────────────────────────────────────────────────────┘
```

### Input from R3

- Deduplicated events with `is_duplicate`, `canonical_event_id`
- Decay scores in `event.decay_score`
- Novelty scores in `event.novelty_score`
- Retention decisions in `event.prune_decision`
- Events with `ner_entities_json` from P02

### Output to R5/R6

- `envelope.phases.r4_new_entities` — New KG entities for st_kg_dom
- `envelope.phases.r4_updated_entities` — Entity updates (canonical_name, aliases)
- `envelope.phases.r4_new_edges` — New KG edges (Hebbian + causal)
- `envelope.phases.r4_updated_edges` — Edge weight updates
- `envelope.phases.r4_gap_candidates` — Low-confidence gaps for P06
- `envelope.phases.r4_social_entities` — Social relationships for st_social

---

## R4-3. Core Files & Dependencies

### Primary File

```
k0/pipelines/p03/phases/r4_kg_consolidator.py (2294 lines)
```

### Algorithm Files (11 total)

```
k0/modules/consolidation/algorithms/
├── entity_extractor.py      (796 lines)  — 4.4.1 UltraBERTEntityExtractor
├── bert_ner_adapter.py      (~200 lines) — 4.4.3 Hybrid BERT-NER
├── entity_disambiguator.py  (1011 lines) — 4.4.2 EntityDisambiguator
├── ambiguous_resolver.py    (763 lines)  — 4.4.4 AmbiguousEntityResolver
├── confidence_router.py     (660 lines)  — 4.4.5 ConfidenceRouter
├── merge_threshold_learner.py (573 lines) — 4.4.6 AdaptiveMergeThresholds
├── entity_merger.py         (1094 lines) — 4.4.7 EntityMerger
├── hebbian_learner.py       (750 lines)  — 4.4.8 HebbianLearner
├── granger_causality.py     (501 lines)  — 4.4.9 GrangerCausalityInference
├── causality_thresholds.py  (463 lines)  — 4.4.10 AdaptiveCausalityThresholds
└── edge_demotion.py         (681 lines)  — 4.4.11 CausalEdgeFeedbackProcessor
```

### Key Imports

```python
from k0.modules.consolidation.algorithms.entity_extractor import (
    UltraBERTEntityExtractor, ExtractedEntity, KGEntityType
)
from k0.modules.consolidation.algorithms.entity_disambiguator import (
    EntityDisambiguator, SemanticOppositionDetector
)
from k0.modules.consolidation.algorithms.ambiguous_resolver import (
    AmbiguousEntityResolver, ResolutionOutcome
)
from k0.modules.consolidation.algorithms.confidence_router import (
    ConfidenceRouter, ConfidenceBand, quick_band
)
from k0.modules.consolidation.algorithms.merge_threshold_learner import (
    AdaptiveMergeThresholds
)
from k0.modules.consolidation.algorithms.entity_merger import EntityMerger
from k0.modules.consolidation.algorithms.hebbian_learner import (
    HebbianLearner, HebbianConfig
)
from k0.modules.consolidation.algorithms.granger_causality import (
    GrangerCausalityInference, CausalEdge
)
from k0.modules.consolidation.algorithms.causality_thresholds import (
    AdaptiveCausalityThresholds, CausalityCategory, CausalCategoryClassifier
)
from k0.modules.consolidation.algorithms.edge_demotion import (
    CausalEdgeFeedbackProcessor, CausalEdgeStalenessChecker
)
```

---

## R4-4. Step-by-Step Execution Flow

### Main Execution (`run()` method)

```python
async def run(self, envelope: P03BatchEnvelope, ctx: P03RunnerContext) -> P03PhaseResult:
    # Step 1: Check skip conditions
    if self.should_skip(envelope):
        return P03PhaseResult.skip(...)

    # Step 2: Initialize algorithm components
    self._initialize_components(ctx)

    # Step 3: Extract entities from all events
    all_entities, event_entity_map = await self._extract_entities(envelope.events, space_id)

    # Step 4: Build entity clusters (uses resolved gaps from st_learning_queue)
    clusters = await self._build_entity_clusters(
        all_entities, event_entity_map, envelope.events, ctx
    )

    # Step 5: Disambiguate and resolve ambiguous mentions
    resolved_clusters, gaps = await self._resolve_entities(
        clusters, envelope.events, space_id, ctx
    )

    # Step 6: Process entity updates (create/update based on confidence)
    kg_updates = await self._process_entity_clusters(resolved_clusters, space_id, ctx)

    # Step 7: Discover relationships via Hebbian co-occurrence
    edge_updates = await self._discover_relationships(resolved_clusters, event_entity_map)

    # Step 7.5: Extract social relationships for st_social
    social_relationships = await self._extract_social_relationships(
        envelope.events, resolved_clusters, space_id
    )

    # Step 8: Infer causal direction via Granger causality (4.4.9)
    causal_edges = await self._infer_causal_relationships(
        edge_updates, resolved_clusters, space_id, ctx
    )

    # Step 9: Populate envelope.phases.r4_* outputs
    self._populate_phase_outputs(
        envelope, kg_updates, edge_updates, gaps, causal_edges, social_relationships, ctx
    )

    # Step 10: Emit canonical_name updates for resolved gaps
    await self._emit_canonical_name_updates(envelope, kg_updates, ctx)

    return P03PhaseResult.done(...)
```

### Processing Stages Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                     R4 EXECUTION FLOW                              │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  STAGE 1: ENTITY EXTRACTION                                       │
│  ─────────────────────────────────────────────────────────────    │
│  events[].ner_entities_json ──┬──▶ UltraBERT ner_family           │
│                               ├──▶ UltraBERT temporal             │
│                               └──▶ BERT-NER (if use_hybrid_ner)   │
│              │                                                     │
│              ▼                                                     │
│         ExtractedEntity[]                                          │
│                                                                    │
│  STAGE 2: ENTITY CLUSTERING                                        │
│  ─────────────────────────────────────────────────────────────    │
│  ExtractedEntity[] ──▶ Group by type:normalized_name              │
│              │                                                     │
│              ▼                                                     │
│         EntityCluster[]                                            │
│              │                                                     │
│              ▼                                                     │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │  STAGE 3: DISAMBIGUATION & RESOLUTION                      │    │
│  │  ─────────────────────────────────────────────────────────│    │
│  │  EntityCluster[] ──▶ quick_band(confidence)               │    │
│  │        │                                                   │    │
│  │        ├─▶ ≥0.85 AUTO ──▶ resolved_clusters               │    │
│  │        ├─▶ 0.60-0.85 FLAG ──▶ resolved_clusters + flag    │    │
│  │        └─▶ <0.60 GAP ──▶ gaps[] (for P06)                 │    │
│  └───────────────────────────────────────────────────────────┘    │
│                                                                    │
│  STAGE 4: ENTITY PROCESSING                                        │
│  ─────────────────────────────────────────────────────────────    │
│  resolved_clusters[] ──▶ AdaptiveMergeThresholds.should_merge()   │
│              │                                                     │
│              ├─▶ should_merge=True ──▶ CREATE_ENTITY              │
│              └─▶ should_merge=False ──▶ CREATE_ENTITY (flagged)   │
│                                                                    │
│  STAGE 5: RELATIONSHIP DISCOVERY                                   │
│  ─────────────────────────────────────────────────────────────    │
│  resolved_clusters[] ──▶ HebbianLearner.update_edge_weight()      │
│              │                                                     │
│              ▼                                                     │
│         edge_updates[] (RELATED_TO edges)                          │
│                                                                    │
│  STAGE 6: CAUSAL INFERENCE                                         │
│  ─────────────────────────────────────────────────────────────    │
│  edge_updates[] ──▶ GrangerCausalityInference.infer_direction()   │
│              │                                                     │
│              ├─▶ precedence_ratio ≥ threshold ──▶ CAUSES edge     │
│              └─▶ precedence_ratio < threshold ──▶ keep RELATED_TO │
│                                                                    │
│  STAGE 7: SOCIAL EXTRACTION                                        │
│  ─────────────────────────────────────────────────────────────    │
│  events[].extracted_relations_json ──▶ UltraBERT relation types   │
│              │                                                     │
│              ▼                                                     │
│         SocialRelationship[] (for st_social)                       │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## R4-5. Data Structures

### R4Config

```python
@dataclass
class R4Config:
    # Confidence thresholds
    confidence_threshold_auto: float = 0.85    # Auto-resolve threshold
    confidence_threshold_flag: float = 0.60    # Flag for review threshold

    # Edge discovery
    min_co_occurrence: int = 2                 # Min co-occurrences for edge
    base_confidence: float = 0.3               # Base edge confidence
    confidence_increment: float = 0.1          # Per co-occurrence increment
    max_relationship_confidence: float = 1.0   # Max edge confidence cap

    # Causal inference (4.4.9)
    enable_causal_inference: bool = True
    granger_min_observations: int = 5          # Min for Granger causality
    granger_precedence_threshold: float = 0.75 # Precedence ratio threshold

    # Feature flags
    enable_adaptive_thresholds: bool = True    # 4.4.10 per-category thresholds
    enable_hebbian_adaptive_rates: bool = True # 4.4.8 adaptive learning rates
    enable_causality_thresholds: bool = True   # 4.4.10
    enable_edge_feedback: bool = True          # 4.4.11
    emit_gaps_on_low_confidence: bool = True   # Emit gaps to P06

    # Hybrid NER
    use_hybrid_ner: bool = True                # Use BERT-NER for ner_general

    # Entity promotion
    min_event_observations: int = 2            # Min for EVENT entity promotion

    # Staleness
    staleness_check_days: int = 90             # Days for edge staleness
```

### R4PhaseStats

```python
@dataclass
class R4PhaseStats:
    # Extraction
    events_processed: int = 0
    entities_extracted: int = 0
    entities_by_type: Dict[str, int] = field(default_factory=dict)
    extraction_duration_ms: int = 0

    # Disambiguation
    auto_resolved: int = 0
    flagged_for_review: int = 0
    gaps_emitted: int = 0
    ambiguous_mentions: int = 0
    resolved_gaps_applied: int = 0
    disambiguation_duration_ms: int = 0

    # Entity processing
    new_entities_created: int = 0
    existing_entities_updated: int = 0
    entities_merged: int = 0

    # Edge discovery
    co_occurrence_pairs: int = 0
    new_edges_created: int = 0
    existing_edges_updated: int = 0
    edges_boosted: int = 0
    edges_demoted: int = 0
    edge_discovery_duration_ms: int = 0

    # Hebbian stats
    hebbian_edges_strengthened: int = 0
    hebbian_edges_weakened: int = 0

    # Causal inference
    causal_pairs_analyzed: int = 0
    causal_edges_created: int = 0
    causal_edges_by_category: Dict[str, int] = field(default_factory=dict)
    causal_inference_duration_ms: int = 0

    # Edge feedback
    edge_feedback_duration_ms: int = 0

    # Social extraction
    social_relationships_extracted: int = 0
    social_relationships_by_type: Dict[str, int] = field(default_factory=dict)
    social_extraction_duration_ms: int = 0

    # Total
    total_duration_ms: int = 0
```

### KGEntityType Enum

```python
class KGEntityType(Enum):
    """Canonical KG entity types for knowledge graph population."""
    FAMILY_MEMBER = "FAMILY_MEMBER"
    PERSON = "PERSON"
    LOCATION = "LOCATION"
    ORGANIZATION = "ORGANIZATION"
    EVENT = "EVENT"
    OBJECT = "OBJECT"
    TEMPORAL = "TEMPORAL"
    CONCEPT = "CONCEPT"
```

### ExtractedEntity

```python
@dataclass
class ExtractedEntity:
    """Normalized entity for KG population."""
    text: str                         # Original text
    kg_type: KGEntityType             # Canonical type
    normalized_text: str              # Cleaned text (lowercase, no possessives)
    source_label: str                 # UltraBERT label (KINSHIP, PERSON, etc.)
    source_head: str                  # ner_family, ner_general, bert_ner
    priority: float                   # 0.0-1.0, for dedup (KINSHIP > PERSON)
    start_token: int
    end_token: int
```

### EntityCluster

```python
@dataclass
class EntityCluster:
    """Cluster of resolved entity mentions."""
    cluster_id: str                   # e.g., "cluster_PERSON_john_smith"
    canonical_name: str               # Display name
    entity_type: str                  # PERSON, FAMILY_MEMBER, etc.
    mentions: List[str]               # All surface forms
    observation_ids: List[str]        # Event IDs where mentioned
    confidence: float                 # Average confidence
    embedding: Optional[List[float]]  # Embedding vector (768-dim)
```

### KGUpdate

```python
class KGUpdateType(str, Enum):
    CREATE_ENTITY = "CREATE_ENTITY"
    UPDATE_ENTITY = "UPDATE_ENTITY"
    CREATE_EDGE = "CREATE_EDGE"
    UPDATE_EDGE = "UPDATE_EDGE"

@dataclass
class KGUpdate:
    """KG update operation."""
    update_type: KGUpdateType

    # Entity fields
    entity_id: Optional[str] = None
    canonical_name: Optional[str] = None
    entity_type: Optional[str] = None
    aliases: Optional[List[str]] = None
    new_observations: int = 0
    source_event_ids: List[str] = field(default_factory=list)

    # Edge fields
    edge_id: Optional[str] = None
    source_id: Optional[str] = None
    target_id: Optional[str] = None
    relation_type: Optional[str] = None
    observation_count: Optional[int] = None

    # Common
    confidence: float = 0.0
```

### CausalEdge

```python
@dataclass
class CausalEdge:
    """Inferred causal relationship between two entities."""
    source_id: str
    target_id: str
    relation_type: str              # Always "CAUSES"
    confidence: float
    observation_count: int
    precedence_ratio: float
```

### SocialRelationship

```python
@dataclass
class SocialRelationship:
    """Social relationship for st_social."""
    relationship_id: str
    actor_a_id: str                          # Self actor
    actor_b_id: str                          # Other person
    actor_b_name: str                        # Display name
    ultrabert_relation_types: List[str]      # parent_of, friend_of, etc.
    relationship_type: str                   # FAMILY, FRIEND, COLLEAGUE
    relationship_subtype: str                # SPOUSE, PARENT, COWORKER
    social_context: str                      # work, family, friends
    intimacy_level: str                      # CASUAL, CLOSE, INTIMATE
    location_pattern: str                    # Most common location
    emotional_role: str                      # MENTOR, CONFIDANT, ENERGY_SOURCE
    emotional_valence_avg: float             # -1.0 to 1.0
    emotional_valence_trend: float           # Positive = warming
    dominant_emotion: str                    # Most common emotion
    relationship_phase: str                  # FORMING, STABLE, DEEPENING, COOLING
    interaction_modalities: List[str]        # in_person, phone, text, video
    typical_activities: List[str]            # Top 5 activities
    emotions: Dict[str, int]                 # Emotion counts
    sentiment_trajectory: List[Dict]         # Last 10 sentiment records
    interaction_count: int
    confidence: float
    source_event_ids: List[str]
    canonical_entity_id: str                 # Link to st_kg_dom entity
    is_new: bool = True
```

---

## R4-6. Database Tables Accessed

| Table | Access | Purpose |
|-------|--------|---------|
| `st_learning_queue` | READ | Load resolved gaps for canonical_name lookup |
| `st_learned_weights` | READ/WRITE | Load/persist learned thresholds |
| `st_kg_dom` | READ (via R7) | Entity lookup for merge decisions |
| `st_kg_edges` | READ (via R7) | Edge lookup for updates |
| `st_causal_feedback` | WRITE | Record causal prediction feedback |

### Output to Envelope (for R7 write)

| Envelope Field | Target Table |
|----------------|--------------|
| `r4_new_entities` | `st_kg_dom` |
| `r4_updated_entities` | `st_kg_dom` |
| `r4_new_edges` | `st_kg_edges` |
| `r4_updated_edges` | `st_kg_edges` |
| `r4_gap_candidates` | `st_learning_queue` (via P06) |
| `r4_social_entities` | `st_social` |

---

## R4-7. Algorithms — Entity Extraction (4.4.1-4.4.3)

### 4.4.1 UltraBERTEntityExtractor

**File:** `entity_extractor.py`
**Purpose:** Process UltraBERT NER outputs and map to canonical KG types.

#### Label Mapping

```python
LABEL_MAPPING: Dict[str, Tuple[KGEntityType, float]] = {
    # ner_family labels (highest priority)
    "KINSHIP": (KGEntityType.FAMILY_MEMBER, 0.95),
    "FAMILY_EVENT": (KGEntityType.EVENT, 0.90),

    # ner_general labels
    "PERSON": (KGEntityType.PERSON, 0.85),
    "PER": (KGEntityType.PERSON, 0.85),
    "ORG": (KGEntityType.ORGANIZATION, 0.80),
    "LOC": (KGEntityType.LOCATION, 0.80),
    "GPE": (KGEntityType.LOCATION, 0.80),
    "PRODUCT": (KGEntityType.OBJECT, 0.70),
    "EVENT": (KGEntityType.EVENT, 0.75),

    # temporal labels
    "DATE_REL": (KGEntityType.TEMPORAL, 0.90),
    "DATE": (KGEntityType.TEMPORAL, 0.90),
    "TIME": (KGEntityType.TEMPORAL, 0.90),
    "DURATION": (KGEntityType.TEMPORAL, 0.85),
}
```

#### Nickname Normalization

```python
NICKNAME_MAP = {
    "wifey": "wife", "hubby": "husband",
    "mom": "mother", "dad": "father",
    "grandma": "grandmother", "grandpa": "grandfather",
    "sis": "sister", "bro": "brother",
    "nana": "grandmother", "pop": "grandfather",
}
```

#### Name Normalization Steps

1. Lowercase
2. Strip whitespace
3. Remove trailing possessives (`'s`, `'`)
4. Remove trailing conjunctions (`and`, `or`)
5. Remove punctuation
6. Collapse multiple spaces
7. Apply nickname map

#### Location Affordance Detection

```python
LOCATION_AFFORDANCES = frozenset({
    "park", "plaza", "center", "school", "hospital",
    "church", "stadium", "restaurant", "hotel", "station",
    "airport", "beach", "lake", "mountain", "downtown", ...
})

def _has_location_affordance(text: str) -> bool:
    """Check if ORG should be reclassified as LOCATION."""
    words = set(text.lower().split())
    return bool(words & LOCATION_AFFORDANCES)
```

#### Word Boundary Validation

```python
def is_complete_word(entity_text: str, source_text: str) -> bool:
    """Filter sub-word tokenization artifacts like 'Fur' from 'Fur Elise'."""
    pattern = r"\b" + re.escape(entity_text) + r"\b"
    return bool(re.search(pattern, source_text, re.IGNORECASE))
```

### 4.4.3 Hybrid NER Mode

**Problem:** UltraBERT's `ner_general` head was trained only for replay/distillation and produces garbage (e.g., "Drove", "authentication" as PERSON).

**Solution:** In hybrid mode (`use_hybrid_ner=True`):

- Use UltraBERT `ner_family` (properly trained for KINSHIP, FAMILY_EVENT)
- Use UltraBERT `temporal` (properly trained for dates/times)
- Skip UltraBERT `ner_general` entirely
- Run `dslim/bert-base-NER` on source text for PER/ORG/LOC

```python
# From _extract_entities:
if self.config.use_hybrid_ner and source_head == "ner_general":
    logger.debug("Skipping UltraBERT ner_general (hybrid mode - using BERT-NER)")
    continue

# Then run BERT-NER:
bert_ner = get_bert_ner()
bert_results = bert_ner.extract(source_text)
```

**Performance:**

- UltraBERT only: <5ms per event (no model inference)
- With BERT-NER: +3.8ms per event (acceptable for nightly P03)

---

## R4-8. Algorithms — Entity Disambiguation (4.4.4-4.4.7)

### 4.4.2 EntityDisambiguator

**File:** `entity_disambiguator.py`
**Purpose:** Per-entity-type weighted similarity for merge decisions.

#### Per-Type Weight Matrix

```python
DEFAULT_WEIGHTS = {
    # Names matter precisely
    "PERSON": DisambiguationWeights(embedding=0.50, string=0.50),
    "FAMILY_MEMBER": DisambiguationWeights(embedding=0.55, string=0.45),

    # Synonyms common
    "LOCATION": DisambiguationWeights(embedding=0.60, string=0.40),
    "ORGANIZATION": DisambiguationWeights(embedding=0.55, string=0.45),

    # Many synonyms (car/vehicle/automobile)
    "OBJECT": DisambiguationWeights(embedding=0.80, string=0.20),
    "CONCEPT": DisambiguationWeights(embedding=0.85, string=0.15),

    # Events described many ways
    "EVENT": DisambiguationWeights(embedding=0.70, string=0.30),

    # Time expressions need precision
    "TEMPORAL": DisambiguationWeights(embedding=0.40, string=0.60),
}
```

#### Human Memory Model

- **PERSON**: Balanced — we remember names AND context
- **FAMILY_MEMBER**: More embedding — "mom" = "mother" = "mama"
- **CONCEPT**: Mostly semantic — "happy" and "joyful" mean the same
- **TEMPORAL**: More string — "2pm" vs "14:00" need precision

#### Similarity Formula

```
combined_score = (embedding_weight × cosine_sim) + (string_weight × fuzzy_sim)
```

#### Fuzzy String Matching (Best-of-Three)

```python
def fuzzy_string_match(name1: str, name2: str) -> float:
    levenshtein = fuzz.ratio(n1, n2)
    token_sort = fuzz.token_sort_ratio(n1, n2)  # "John Smith" = "Smith, John"
    partial = fuzz.partial_ratio(n1, n2)        # "NYC" in "New York City"
    return max(levenshtein, token_sort, partial) / 100.0
```

#### Semantic Opposition Detection

**Neuroscience Insight:** Antonyms have HIGH embedding similarity (distributional hypothesis) but LOW string similarity.

```python
class SemanticOppositionDetector:
    """Detect opposites via embedding geometry (no hardcoded word lists)."""

    def detect_opposition(self, emb1, name1, emb2, name2, emb_sim, str_sim):
        signals = {}

        # Signal 1: Paradox — high embedding sim + low string sim
        if emb_sim >= 0.90 and str_sim <= 0.40:
            signals["paradox"] = sqrt((emb_sim - 0.90) * (0.40 - str_sim))

        # Signal 2: Magnitude Symmetry — antonyms are "equally strong"
        signals["magnitude_symmetry"] = min(|emb1|, |emb2|) / max(|emb1|, |emb2|)

        # Signal 3: Dimensional Concentration — differ on few axes
        signals["dimensional_concentration"] = gini(|emb1 - emb2|)

        # Combine with weighted voting (paradox = 0.70 weight)
        confidence = 0.70 * paradox + 0.10 * magnitude + ...

        return OppositionAnalysis(
            is_opposition=confidence >= 0.50,
            penalty_applied=0.25 * confidence
        )
```

### 4.4.4 AmbiguousEntityResolver

**File:** `ambiguous_resolver.py`
**Purpose:** 5-priority context hierarchy for ambiguous mentions.

#### Priority Hierarchy

| Priority | Boost | Signal |
|----------|-------|--------|
| P1 | +0.35 | **Recent context** — mentioned recently in session |
| P2 | +0.30 | **Co-occurring entities** — other entities narrow it down |
| P3 | +0.20 | **Location context** — "at work" → colleague |
| P4 | +0.10 | **Temporal pattern** — morning → commute entities |
| P5 | +0.05 | **Frequency** — higher frequency = more likely |

#### Resolution Scoring

```python
def _score_candidate(candidate, context) -> float:
    score = 0.30  # Base score

    # P1: Recency
    recency_age = context.timestamp - candidate.last_seen_ms
    if recency_age <= RECENCY_WINDOW_MS:
        score += 0.35 * (1 - recency_age / RECENCY_WINDOW_MS)

    # P2: Co-occurring
    if candidate.entity_id in context.co_occurring_entities:
        score += 0.30

    # P3: Location match
    if matches_location(candidate, context.location_hint):
        score += 0.20

    # P4: Temporal match
    if matches_temporal(candidate, context.temporal_category):
        score += 0.10

    # P5: Frequency
    score += 0.05 * min(1.0, candidate.frequency / 100.0)

    return score
```

#### Close Race Penalty

If top two candidates differ by < 0.10, apply penalty:

```python
if gap < CLOSE_RACE_THRESHOLD:
    penalty = best_score * CLOSE_RACE_PENALTY  # 0.10
    best_score -= penalty
```

### 4.4.5 ConfidenceRouter

**File:** `confidence_router.py`
**Purpose:** Route resolution results by confidence band.

#### Confidence Bands

| Band | Threshold | Action |
|------|-----------|--------|
| AUTO | ≥ 0.85 | Accept silently |
| FLAG | 0.60 - 0.84 | Accept but flag for review |
| GAP | < 0.60 | Emit to P06 for clarification |

```python
def quick_band(confidence: float) -> ConfidenceBand:
    if confidence >= 0.85:
        return ConfidenceBand.AUTO
    elif confidence >= 0.60:
        return ConfidenceBand.FLAG
    else:
        return ConfidenceBand.GAP
```

#### Gap Emission

Low-confidence resolutions are written to `st_learning_queue` and staged to `st_outbox` for reliable delivery to P06.

### 4.4.6 AdaptiveMergeThresholds

**File:** `merge_threshold_learner.py`
**Purpose:** Per-entity-type merge thresholds with learning.

#### Default Thresholds

```python
DEFAULT_THRESHOLD_BOUNDS = {
    "FAMILY_MEMBER": ThresholdBounds(min=0.85, max=0.98, default=0.90),
    "PERSON": ThresholdBounds(min=0.80, max=0.95, default=0.85),
    "LOCATION": ThresholdBounds(min=0.65, max=0.85, default=0.75),
    "ORGANIZATION": ThresholdBounds(min=0.70, max=0.90, default=0.80),
    "OBJECT": ThresholdBounds(min=0.60, max=0.80, default=0.70),
    "CONCEPT": ThresholdBounds(min=0.55, max=0.75, default=0.65),
    "EVENT": ThresholdBounds(min=0.65, max=0.85, default=0.75),
    "TEMPORAL": ThresholdBounds(min=0.70, max=0.90, default=0.80),
}
```

#### Human Memory Model

- **FAMILY_MEMBER=0.90**: Highest — merging wrong family members is catastrophic
- **CONCEPT=0.65**: Lowest — abstract concepts can be liberally merged

#### Learning Rates

```python
FEEDBACK_LEARNING_RATES = {
    "MERGE_CONFIRMED": 0.0,    # Correct, no change
    "MERGE_REJECTED": +0.02,   # FP: raise threshold
    "SPLIT_REQUEST": +0.05,    # Strong FP: raise more
    "MISSED_MERGE": -0.02,     # FN: lower threshold
}
```

### 4.4.7 EntityMerger

**File:** `entity_merger.py`
**Purpose:** Complete entity merge with cascade and undo support.

#### 6-Step Merge Process

1. **Validate** — Both exist, not already merged, same type
2. **Select Primary** — Entity with more observations wins
3. **Merge Attributes** — Combine observation counts and properties
4. **Cascade** — Update references in 7 tables
5. **Archive** — Mark secondary as MERGED
6. **Log** — Record in st_entity_merges for undo

#### Cascade Tables

```python
# Tables updated with merge_cascade_id for undo:
1. st_kg_edges.source_entity_id
2. st_kg_edges.target_entity_id
3. st_hipp_events.entities_json
4. st_epi.entity_ids
5. st_sem.entity_ids
6. st_social.actor_id
7. st_procedural.participants
8. st_vec.metadata_json
```

#### Undo Support

All merge operations capture snapshots before merge. `merge_cascade_id` tracks affected rows for reversal.

---

## R4-9. Algorithms — Relationship Discovery (4.4.8)

### 4.4.8 HebbianLearner

**File:** `hebbian_learner.py`
**Purpose:** "Neurons that fire together, wire together" for edge strength.

#### Core Formula

```python
def update_edge_weight(edge, event_importance):
    # Soft saturation: growth slows as weight approaches max
    delta = learning_rate * (max_weight - current_weight) * event_importance

    new_weight = current_weight + delta
    return min(new_weight, max_weight)
```

**Why Soft Saturation?**

- Linear updates would hit ceiling abruptly
- Soft saturation mimics biological synapses
- Well-established relationships stabilize naturally

#### Anti-Hebbian Decay

For corrections and contradictions:

```python
def apply_anti_decay(edge, correction_strength):
    """Weaken edges that prove incorrect."""
    delta = anti_learning_rate * current_weight * correction_strength
    new_weight = current_weight - delta
    return max(new_weight, min_weight)
```

#### Co-Occurrence Extraction

```python
def extract_cooccurrences(event) -> List[CoOccurrence]:
    """Extract entity pairs from event."""
    entities = event.entities
    pairs = []
    for i, e1 in enumerate(entities):
        for e2 in entities[i+1:]:
            pairs.append(CoOccurrence(
                entity_a_id=e1.id,
                entity_b_id=e2.id,
                event_id=event.event_id,
                importance=event.importance_score,
                timestamp_ms=event.event_ts
            ))
    return pairs
```

#### Configuration

```python
@dataclass
class HebbianConfig:
    learning_rate: float = 0.10
    anti_learning_rate: float = 0.15  # Faster unlearning
    decay_rate: float = 0.01
    max_weight: float = 1.00
    min_weight: float = 0.01
    initial_weight: float = 0.10
```

---

## R4-10. Algorithms — Causal Inference (4.4.9-4.4.11)

### 4.4.9 GrangerCausalityInference

**File:** `granger_causality.py`
**Purpose:** Infer causal direction from temporal precedence.

#### Core Principle

**Granger Causality:** If A consistently precedes B, A may cause B.

```python
@dataclass
class TemporalPrecedenceStats:
    a_before_b_count: int = 0
    b_before_a_count: int = 0
    simultaneous_count: int = 0

    @property
    def precedence_ratio(self) -> float:
        total = self.a_before_b_count + self.b_before_a_count
        if total < MIN_OBSERVATIONS:
            return 0.5  # Insufficient data
        return self.a_before_b_count / total
```

#### Causal Edge Inference

```python
def infer_causal_edges(entity_pairs) -> List[CausalEdge]:
    for pair in entity_pairs:
        stats = compute_precedence_stats(pair)

        if stats.total_observations < MIN_OBSERVATIONS:
            continue

        # Check if A→B is stronger than B→A
        if stats.precedence_ratio >= PRECEDENCE_THRESHOLD:
            edge = CausalEdge(
                cause=pair.entity_a,
                effect=pair.entity_b,
                confidence=stats.precedence_ratio,
                observation_count=stats.total_observations
            )
            edges.append(edge)
```

#### Configuration

```python
MIN_OBSERVATIONS = 5
PRECEDENCE_THRESHOLD = 0.75
TEMPORAL_WINDOW_MS = 60 * 60 * 1000  # 60 minutes
```

### 4.4.10 AdaptiveCausalityThresholds

**File:** `causality_thresholds.py`
**Purpose:** Per-category causal thresholds.

#### Category Hierarchy

```python
class CausalityCategory(Enum):
    HEALTH = "health"       # Threshold: 0.85 (high stakes)
    FINANCIAL = "financial" # Threshold: 0.80
    SOCIAL = "social"       # Threshold: 0.70
    HABIT = "habit"         # Threshold: 0.65 (casual patterns)
```

#### Category Classification

```python
CATEGORY_KEYWORDS = {
    CausalityCategory.HEALTH: {
        "doctor", "hospital", "medication", "symptom", "pain",
        "exercise", "diet", "sleep", "headache", "illness"
    },
    CausalityCategory.FINANCIAL: {
        "bank", "payment", "salary", "investment", "purchase",
        "bill", "loan", "budget", "expense", "money"
    },
    CausalityCategory.SOCIAL: {
        "friend", "family", "party", "meeting", "call",
        "visit", "dinner", "birthday", "wedding", "gathering"
    },
    CausalityCategory.HABIT: {
        "morning", "coffee", "routine", "commute", "workout",
        "breakfast", "lunch", "walk", "reading", "music"
    }
}
```

#### Human Memory Model

- **HEALTH=0.85**: High threshold — "coffee causes headache" needs strong evidence
- **HABIT=0.65**: Lower threshold — casual patterns are often tentative

### 4.4.11 CausalEdgeFeedbackProcessor

**File:** `edge_demotion.py`
**Purpose:** Accuracy-based boost/demote/archive.

#### Feedback Actions

```python
class FeedbackAction(Enum):
    BOOST = "boost"     # User confirmed prediction
    DEMOTE = "demote"   # Prediction was wrong
    ARCHIVE = "archive" # Remove from active use
```

#### Adjustment Rates

```python
FEEDBACK_MULTIPLIERS = {
    FeedbackAction.BOOST: 1.10,   # +10% on confirmation
    FeedbackAction.DEMOTE: 0.85,  # -15% on error
}
```

#### Staleness Check

```python
class CausalEdgeStalenessChecker:
    STALE_THRESHOLD_DAYS = 90

    def check_staleness(self, edge) -> bool:
        age_days = (now_ms - edge.last_observed_ms) / MS_PER_DAY
        return age_days > STALE_THRESHOLD_DAYS

    def archive_stale_edges(self, edges):
        for edge in edges:
            if self.check_staleness(edge):
                edge.status = "archived"
```

---

## R4-11. Social Relationship Extraction

UltraBERT's `relation_family` head produces social relationship labels.

#### Relationship Types

```python
RELATIONSHIP_MAPPING = {
    "SPOUSE": SocialRelationType.SPOUSE,
    "PARENT": SocialRelationType.PARENT,
    "CHILD": SocialRelationType.CHILD,
    "SIBLING": SocialRelationType.SIBLING,
    "GRANDPARENT": SocialRelationType.GRANDPARENT,
    "GRANDCHILD": SocialRelationType.GRANDCHILD,
    "AUNT_UNCLE": SocialRelationType.EXTENDED,
    "COUSIN": SocialRelationType.EXTENDED,
    "FRIEND": SocialRelationType.FRIEND,
    "COLLEAGUE": SocialRelationType.COLLEAGUE,
    "NEIGHBOR": SocialRelationType.NEIGHBOR,
}
```

#### Output Structure

```python
@dataclass
class SocialRelationship:
    person_a_id: str
    person_b_id: str
    relation_type: SocialRelationType
    confidence: float
    source_event_id: str
```

---

## R4-12. Gap Resolution Integration

R4 consumes resolved gaps from `st_learning_queue`:

```python
def _load_resolved_gaps(batch_ids: List[str]) -> Dict[str, str]:
    """Load resolved gap values to use as canonical names."""
    query = """
        SELECT id, resolved_value
        FROM st_learning_queue
        WHERE batch_id = ANY($1)
          AND status = 'RESOLVED'
    """
    return {row["id"]: row["resolved_value"] for row in results}
```

#### Usage in Entity Resolution

When resolving an entity, if a previous gap was resolved by P06:

1. Check if entity mention matches a gap
2. Use `resolved_value` as canonical name
3. Skip disambiguation (user already clarified)

---

## R4-13. Configuration

### R4Config Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_causal_inference` | bool | True | Run Granger causality inference |
| `enable_adaptive_thresholds` | bool | True | Use learned thresholds per type |
| `emit_gaps_on_low_confidence` | bool | True | Route low-confidence to P06 |
| `enable_hebbian_adaptive_rates` | bool | True | Adjust Hebbian rates based on accuracy |
| `use_hybrid_ner` | bool | False | Use BERT-NER for ner_general |
| `confidence_threshold_auto` | float | 0.85 | Auto-accept threshold |
| `confidence_threshold_flag` | float | 0.60 | Flag-for-review threshold |
| `min_entity_confidence` | float | 0.40 | Discard entities below this |
| `batch_size` | int | 1000 | Entity processing batch size |

---

## R4-14. Statistics & Metrics

### R4PhaseStats Fields

| Field | Description |
|-------|-------------|
| `entities_extracted` | Total entities from NER |
| `entities_merged` | Entities merged into existing |
| `entities_created` | New entities created |
| `entities_flagged` | Entities flagged for review |
| `gaps_emitted` | Low-confidence sent to P06 |
| `edges_created` | New relationship edges |
| `edges_strengthened` | Existing edges with higher weight |
| `causal_edges_inferred` | New causal relationships |
| `social_relations_extracted` | Social relationships found |
| `processing_time_ms` | Total R4 runtime |

---

## R4-15. Error Handling

```python
try:
    entities = self._extract_entities(events)
except EntityExtractionError as e:
    stats.extraction_errors += 1
    logger.warning(f"Entity extraction failed: {e}")
    entities = []  # Continue with empty set

try:
    resolved = self._resolve_entities(entities)
except DisambiguationError as e:
    stats.disambiguation_errors += 1
    logger.error(f"Disambiguation failed: {e}")
    raise  # Critical error, abort phase

try:
    edges = self._discover_relationships(resolved)
except HebbianError as e:
    stats.hebbian_errors += 1
    logger.warning(f"Hebbian learning failed: {e}")
    edges = []  # Continue without edges
```

---

## R4-16. Formulas Reference

### Entity Similarity

```
combined_score = (emb_weight × cosine_sim) + (str_weight × fuzzy_sim)
```

### Semantic Opposition

```
opposition_confidence = 0.70 × paradox + 0.10 × magnitude + 0.20 × concentration
```

### Context Score

```
context_score = 0.30 + (0.35 × recency) + (0.30 × cooccur) + (0.20 × location) + (0.10 × temporal) + (0.05 × frequency)
```

### Hebbian Update

```
delta = learning_rate × (max_weight - current_weight) × event_importance
```

### Anti-Hebbian Decay

```
delta = anti_learning_rate × current_weight × correction_strength
```

### Granger Precedence

```
precedence_ratio = a_before_b / (a_before_b + b_before_a)
```

### Causal Confidence

```
causal_confidence = precedence_ratio × category_threshold_weight
```

---

## R4-17. ASCII Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         R4 KG CONSOLIDATOR PHASE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │ From R3 Output  │                                                        │
│  │  (event batch)  │                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                      ENTITY EXTRACTION                             │    │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐   │    │
│  │  │ UltraBERT NER   │  │  BERT-NER       │  │  Name            │   │    │
│  │  │ ner_family      │  │  (hybrid mode)  │  │  Normalization   │   │    │
│  │  │ ner_general*    │  │  dslim/bert-ner │  │  Nickname Map    │   │    │
│  │  │ temporal        │  └────────┬────────┘  │  Location Check  │   │    │
│  │  └────────┬────────┘           │           └────────┬─────────┘   │    │
│  │           └────────────────────┴────────────────────┘             │    │
│  │                          │                                         │    │
│  │                          ▼                                         │    │
│  │                 ┌──────────────────┐                               │    │
│  │                 │ Extracted Entity │                               │    │
│  │                 │ + KGEntityType   │                               │    │
│  │                 │ + confidence     │                               │    │
│  │                 └────────┬─────────┘                               │    │
│  └──────────────────────────┼─────────────────────────────────────────┘    │
│                             │                                              │
│                             ▼                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                     ENTITY DISAMBIGUATION                          │    │
│  │                                                                    │    │
│  │  ┌──────────────────────────────────────────────────────────────┐ │    │
│  │  │              Per-Type Weighted Similarity                    │ │    │
│  │  │  FAMILY_MEMBER: 55% embedding / 45% string                   │ │    │
│  │  │  CONCEPT:       85% embedding / 15% string                   │ │    │
│  │  │  TEMPORAL:      40% embedding / 60% string                   │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │ │    │
│  │                          │                                       │ │    │
│  │                          ▼                                       │ │    │
│  │  ┌──────────────────────────────────────────────────────────────┐ │    │
│  │  │           Semantic Opposition Detector                      │ │    │
│  │  │  Paradox signal: high emb_sim + low str_sim = antonyms      │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │ │    │
│  │                          │                                       │ │    │
│  │                          ▼                                       │ │    │
│  │  ┌──────────────────────────────────────────────────────────────┐ │    │
│  │  │            Ambiguous Entity Resolver                        │ │    │
│  │  │  P1: Recency (+0.35)     P4: Temporal (+0.10)               │ │    │
│  │  │  P2: Co-occur (+0.30)    P5: Frequency (+0.05)              │ │    │
│  │  │  P3: Location (+0.20)                                        │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │ │    │
│  │                          │                                       │ │    │
│  │                          ▼                                       │ │    │
│  │  ┌──────────────────────────────────────────────────────────────┐ │    │
│  │  │                  Confidence Router                          │ │    │
│  │  │         ┌─────────────────────────────────────┐             │ │    │
│  │  │         │  AUTO ≥0.85  │  FLAG 0.60-0.84  │  GAP <0.60      │ │    │
│  │  │         │    ✓ Accept  │    ⚑ Review     │    → P06        │ │    │
│  │  │         └─────────────────────────────────────┘             │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │ │    │
│  └──────────────────────────┼─────────────────────────────────────────┘    │
│                             │                                              │
│                             ▼                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                       ENTITY MERGING                              │    │
│  │  ┌──────────────────────────────────────────────────────────────┐ │    │
│  │  │              Adaptive Merge Thresholds                       │ │    │
│  │  │  FAMILY_MEMBER: 0.90    ORGANIZATION: 0.80                   │ │    │
│  │  │  PERSON:        0.85    OBJECT:       0.70                   │ │    │
│  │  │  LOCATION:      0.75    CONCEPT:      0.65                   │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │ │    │
│  │                          │                                       │ │    │
│  │                          ▼                                       │ │    │
│  │  ┌──────────────────────────────────────────────────────────────┐ │    │
│  │  │                    Entity Merger                             │ │    │
│  │  │  1. Validate    2. Select Primary   3. Merge Attributes     │ │    │
│  │  │  4. Cascade (7 tables)   5. Archive   6. Log for Undo       │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │ │    │
│  └──────────────────────────┼─────────────────────────────────────────┘    │
│                             │                                              │
│                             ▼                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                   RELATIONSHIP DISCOVERY                          │    │
│  │  ┌──────────────────────────────────────────────────────────────┐ │    │
│  │  │                   Hebbian Learner                            │ │    │
│  │  │  "Fire together, wire together"                              │ │    │
│  │  │  delta = LR × (max - current) × importance                   │ │    │
│  │  │  Anti-Hebbian: faster unlearning for corrections             │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │ │    │
│  │                          │                                       │ │    │
│  │                          ▼                                       │ │    │
│  │  ┌──────────────────────────────────────────────────────────────┐ │    │
│  │  │              Social Relationship Extraction                  │ │    │
│  │  │  SPOUSE, PARENT, CHILD, SIBLING, FRIEND, COLLEAGUE          │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │ │    │
│  └──────────────────────────┼─────────────────────────────────────────┘    │
│                             │                                              │
│                             ▼                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                     CAUSAL INFERENCE                              │    │
│  │  ┌──────────────────────────────────────────────────────────────┐ │    │
│  │  │              Granger Causality Inference                     │ │    │
│  │  │  Temporal precedence → causal direction                      │ │    │
│  │  │  precedence_ratio = A→B / (A→B + B→A)                        │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │ │    │
│  │                          │                                       │ │    │
│  │                          ▼                                       │ │    │
│  │  ┌──────────────────────────────────────────────────────────────┐ │    │
│  │  │            Adaptive Causality Thresholds                     │ │    │
│  │  │  HEALTH: 0.85  FINANCIAL: 0.80  SOCIAL: 0.70  HABIT: 0.65   │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │ │    │
│  │                          │                                       │ │    │
│  │                          ▼                                       │ │    │
│  │  ┌──────────────────────────────────────────────────────────────┐ │    │
│  │  │           Causal Edge Feedback Processor                     │ │    │
│  │  │  BOOST (+10%)   DEMOTE (-15%)   ARCHIVE (90 days stale)     │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │ │    │
│  └──────────────────────────┼─────────────────────────────────────────┘    │
│                             │                                              │
│                             ▼                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                         OUTPUT                                    │    │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐  │    │
│  │  │ r4_new_entities │ │ r4_new_edges    │ │ r4_gap_candidates   │  │    │
│  │  │ r4_updated_ents │ │ r4_updated_edge │ │ → P06 learning      │  │    │
│  │  │ → st_kg_dom     │ │ → st_kg_edges   │ │ → st_learning_queue │  │    │
│  │  └─────────────────┘ └─────────────────┘ └─────────────────────┘  │    │
│  └──────────────────────────┼─────────────────────────────────────────┘    │
│                             │                                              │
│                             ▼                                              │
│                   ┌───────────────────┐                                    │
│                   │   To R5: Memory   │                                    │
│                   │   Layer Routing   │                                    │
│                   └───────────────────┘                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## R4-18. Summary

R4 KG Consolidator is the **Knowledge Graph brain** of P03, performing:

1. **Entity Extraction** — Maps UltraBERT NER to canonical KG types
2. **Entity Disambiguation** — Per-type weighted similarity with semantic opposition detection
3. **Ambiguous Resolution** — 5-priority context hierarchy (recency > frequency)
4. **Confidence Routing** — AUTO/FLAG/GAP bands for quality control
5. **Entity Merging** — 6-step merge with 7-table cascade and undo
6. **Relationship Discovery** — Hebbian learning with soft saturation
7. **Social Extraction** — Family/friend/colleague relationships from NER
8. **Causal Inference** — Granger causality with per-category thresholds
9. **Edge Feedback** — Boost/demote/archive based on prediction accuracy

**Human Memory Model Alignment:**

- Per-type weights mimic how we remember (names precisely, concepts flexibly)
- Recency bias matches human memory primacy
- Hebbian learning mirrors biological synapses
- Anti-Hebbian decay enables unlearning incorrect associations
- Category-specific causality thresholds reflect real-world risk differences

**Key Outputs:**

- New/updated entities → `st_kg_dom`
- New/updated edges → `st_kg_edges`
- Gap candidates → `st_learning_queue` → P06
- Social relations → `st_social`

---

# R5 — Memory Layer Routing (NOT YET IMPLEMENTED)

**Status:** Phase not yet implemented. R5 will handle routing consolidated memories to appropriate truth layers (episodic, semantic, procedural, prospective).

**Placeholder for future documentation.**

---

# R6 — Staging Table Updates

## R6-1. Overview

R6 is the **Staging Phase** of P03 Consolidation. It collects all outputs from R1-R5 and stages them for atomic commit in R7.

**Purpose:** Prepare all database writes for atomic transaction commit.

| Issue | Component | Purpose |
|-------|-----------|---------|
| 5.1.1 | R6Output | Core dataclass for staged writes container |
| 5.1.2 | ConsolidationStatusMarker | Assign CONSOLIDATED/DUPLICATE/PRUNED/PENDING_REVIEW |
| 5.1.3 | DedupMetadataPopulator | Populate near_duplicates_json, novelty_score |
| 5.1.4 | ReconciliationRecorder | Record reconciliation decision audit trail |
| 5.1.5 | IdempotencyKeyGenerator | Deterministic idempotency keys |
| 5.1.6 | TruthWriteAssembler | Assemble st_epi, st_sem, st_procedural, etc. |
| 5.1.7 | KGWriteAssembler | Assemble st_kg_dom, st_kg_edges |
| 5.1.8 | OutboxEventAssembler | Assemble outbox events for R8 |
| 5.1.9 | ManifestValidator | Validate before commit (DLQ routing) |
| 5.1.10 | SummaryGenerator | Generate ReconciliationSummary |
| 5.1.11 | R6Coordinator | Orchestrate all sub-components |
| 5.1.13 | R6Staging | Phase file entry point |
| 5.1.14 | R6Inputs | Container for R1-R5 inputs |
| 5.1.15 | Envelope population | Route R6Output to envelope.staged |

---

## R6-2. R6 in the Pipeline Context

```
R0 (Batch) → R1 (Score) → R2 (Cluster) → R3 (Dedup/Decay) → R4 (KG) → [R5] → R6 (Stage) → R7 (Commit)
                                                                          ↑
                                                                     WE ARE HERE
```

### Input (from R1-R5)

| Source | Data |
|--------|------|
| R1 | `event_states` with importance scores |
| R2 | `r2_clusters` (EpisodeCluster) |
| R3 | `r3_dedup_merges`, `r3_decay_updates` |
| R4 | `r4_new_entities`, `r4_updated_entities`, `r4_new_edges`, `r4_updated_edges`, `r4_causal_edges`, `r4_gap_candidates` |
| R5 | `r5_routines`, `r5_intentions`, gaps |

### Output (to R7)

| Field | Description |
|-------|-------------|
| `envelope.staged.st_hipp_events_updates` | Per-event status updates |
| `envelope.staged.truth_writes` | Writes for st_epi, st_sem, st_procedural, etc. |
| `envelope.staged.kg_writes` | Writes for st_kg_dom, st_kg_edges |
| `envelope.staged.outbox_events` | Events for R8 emission |
| `envelope.phases.r6_summary` | ReconciliationSummary |

---

## R6-3. Core Files & Dependencies

| File | Lines | Purpose |
|------|-------|---------|
| `k0/pipelines/p03/phases/r6_staging.py` | 585 | Phase entry point |
| `k0/modules/consolidation/staging/r6_coordinator.py` | 485 | Orchestrates sub-components |
| `k0/modules/consolidation/staging/r6_output.py` | 789 | R6Output, StagedEventUpdate, StagedWritesContainer |
| `k0/modules/consolidation/staging/status_marker.py` | 394 | ConsolidationStatusMarker |
| `k0/modules/consolidation/staging/dedup_metadata.py` | 410 | DedupMetadataPopulator |
| `k0/modules/consolidation/staging/reconciliation_recorder.py` | 315 | ReconciliationRecorder |
| `k0/modules/consolidation/staging/idempotency.py` | 369 | IdempotencyKeyGenerator |
| `k0/modules/consolidation/staging/truth_write_assembler.py` | 779 | TruthWriteAssembler |
| `k0/modules/consolidation/staging/kg_write_assembler.py` | 621 | KGWriteAssembler |
| `k0/modules/consolidation/staging/outbox_assembler.py` | 466 | OutboxEventAssembler |
| `k0/modules/consolidation/staging/manifest_validator.py` | 532 | ManifestValidator |
| `k0/modules/consolidation/staging/summary_generator.py` | 343 | SummaryGenerator |

---

## R6-4. Step-by-Step Execution Flow

### R6Staging.run() Flow

```python
async def run(envelope, ctx) -> P03PhaseResult:
    # STEP 1: Create coordinator
    coordinator = self._create_coordinator(envelope, ctx)

    # STEP 2: Extract inputs from envelope
    event_states = self._extract_event_states(envelope)
    phase_outputs = self._extract_phase_outputs(envelope)
    gaps = self._extract_gaps(envelope)
    batch_event_ids = self._extract_batch_event_ids(envelope)
    dedup_results = self._extract_dedup_results(envelope)
    phase_durations = self._extract_phase_durations(envelope)

    # STEP 3: Execute coordinator
    result = coordinator.execute(
        event_states, phase_outputs, gaps,
        batch_event_ids, dedup_results, phase_durations,
        cycle_start_ms
    )

    # STEP 4: Handle failure → P03PhaseResult.fail()
    if not result.success:
        return self._handle_failure(result, cycle_id, start_ms)

    # STEP 5: Populate envelope with R6Output
    self._populate_envelope(envelope, result)

    return P03PhaseResult.done(...)
```

### R6Coordinator.execute() Flow

```python
def execute(event_states, phase_outputs, gaps, ...):
    # STEP 1: Build event updates (status + dedup metadata)
    event_updates = self._build_event_updates(event_states, dedup_results)

    # STEP 2: Assemble truth writes (st_epi, st_sem, st_procedural, etc.)
    truth_assembly = self.truth_assembler.assemble_all(...)
    truth_writes = self._flatten_truth_writes(truth_assembly)

    # STEP 3: Assemble KG writes (st_kg_dom, st_kg_edges)
    entity_writes, edge_writes = self.kg_assembler.assemble_all(...)
    kg_writes = entity_writes + edge_writes

    # STEP 4: Generate summary
    summary_result = self.summary_gen.compute_with_writes(...)

    # STEP 5: Assemble outbox events
    outbox_assembly = self.outbox_assembler.assemble_all(...)

    # STEP 6: Build R6Output (frozen/immutable)
    r6_output = R6Output(...)

    # STEP 7: Validate manifest
    if self.config.validate_manifest:
        validation_result = self.validator.validate(r6_output, batch_event_ids)
        if not validation_result.is_valid:
            return R6CoordinatorResult(success=False, dlq_reason=...)

    return R6CoordinatorResult(success=True, r6_output=r6_output)
```

---

## R6-5. Data Structures

### R6Output (Frozen)

```python
@dataclass(frozen=True)
class R6Output:
    cycle_ulid: str
    batch_id: str
    staged_event_updates: Tuple[StagedEventUpdate, ...]
    staged_truth_writes: Tuple[StagedWrite, ...]
    staged_kg_writes: Tuple[StagedWrite, ...]
    staged_outbox_events: Tuple[StagedOutboxEvent, ...]
    reconciliation_summary: ReconciliationSummary
    created_at_ms: int
    r6_idempotency_key: str
```

**Why Frozen?** Immutability after R6 completes ensures no accidental modifications before R7 commit.

### StagedEventUpdate

```python
@dataclass
class StagedEventUpdate:
    event_id: str
    consolidation_status: str  # CONSOLIDATED/DUPLICATE/PRUNED/PENDING_REVIEW
    near_duplicates_json: str = "[]"
    novelty_score: float = 1.0
    episode_cluster_id: Optional[str] = None
    reconciliation_action: str = "PENDING"
    best_match_id: Optional[str] = None
    best_match_layer: Optional[str] = None
    similarity_score: float = 0.0
    confidence: float = 0.0
    reconciliation_reason: str = ""
    idempotency_key: str = ""
    version_conflict: bool = False
    created_at_ms: int = field(default_factory=lambda: _now_ms())
```

### ReconciliationSummary

```python
@dataclass(frozen=True)
class ReconciliationSummary:
    total_events: int = 0
    consolidated_count: int = 0
    duplicate_count: int = 0
    pruned_count: int = 0
    pending_review_count: int = 0
    action_breakdown: Tuple[Tuple[str, int], ...] = ()
    layer_write_counts: Tuple[Tuple[str, int], ...] = ()
    kg_entity_count: int = 0
    kg_edge_count: int = 0
    gap_count: int = 0
    total_writes: int = 0
    cycle_duration_ms: int = 0
```

### R6Inputs

```python
@dataclass
class R6Inputs:
    event_states: Dict[str, P03EventState]
    r2_clusters: List[EpisodeCluster]
    r3_dedup_merges: List[DedupMerge]
    r3_decay_updates: List[DecayUpdate]
    r4_new_entities: List[KGEntity]
    r4_updated_entities: List[KGEntityUpdate]
    r4_new_edges: List[KGEdge]
    r4_updated_edges: List[KGEdgeUpdate]
    r4_causal_edges: List[CausalEdge]
    r4_gap_candidates: List[GapCandidate]
    cycle_id: str
    tenant_id: str
    space_id: str
    cycle_start_ms: int
```

---

## R6-6. Database Tables Accessed

### Target Tables (via staged writes)

| Table | Write Type | Source |
|-------|------------|--------|
| `st_hipp_events` | UPDATE | StagedEventUpdate → status, dedup metadata |
| `st_epi` | INSERT | R2 EpisodeCluster → episodic memory |
| `st_sem` | INSERT/UPDATE/ARCHIVE | R3 reconciliation decisions |
| `st_procedural` | INSERT | R5 routines |
| `st_social` | INSERT | R4 social relationships |
| `st_prospective` | INSERT | R5 ProspectiveMemory |
| `st_learning_queue` | INSERT | R4 GapCandidate → P06 |
| `st_kg_dom` | INSERT/UPDATE | R4 entities |
| `st_kg_edges` | INSERT/UPDATE | R4 edges + causal edges |

### Write Dependency Order (for R7)

```
vec → kg_dom → kg_edges → epi → sem →
procedural → social → prospective →
learning_queue → hipp_events
```

---

## R6-7. Algorithms — Status Marking (5.1.2)

### ConsolidationStatusMarker

**Decision Tree:**

```
1. is_duplicate=True? → DUPLICATE
2. action=CONTRADICT? → PENDING_REVIEW
3. action=PRUNE or PruneDecision∈{ARCHIVE,TOMBSTONE}? → PRUNED
4. action=SKIP? → Check reason (duplicate→DUPLICATE, decay→PRUNED, default→DUPLICATE)
5. action=PENDING? → PENDING_REVIEW
6. low_confidence && flag_low_confidence? → PENDING_REVIEW
7. action∈{REINFORCE,EXTEND,CREATE,EVOLVE}? → CONSOLIDATED
8. fallback → CONSOLIDATED
```

### Status Values

| Status | Meaning |
|--------|---------|
| CONSOLIDATED | Event successfully reconciled |
| DUPLICATE | Exact/near duplicate detected |
| PRUNED | Decayed below threshold |
| PENDING_REVIEW | Flagged for P06 review |

---

## R6-8. Algorithms — Idempotency (5.1.5)

### IdempotencyKeyGenerator

**Key Formats:**

| Operation | Format | Example |
|-----------|--------|---------|
| Event update | `p03:staging:{cycle}:{event_id}` | `p03:staging:01ABC...:evt_001` |
| Truth write | `p03:write:{cycle}:{table}:{record_id}` | `p03:write:01ABC...:st_epi:epi-001` |
| Outbox emit | `p03:emit:{cycle}:{topic}:{offset}` | `p03:emit:01ABC...:p03.pattern.detected.v1:42` |
| Batch phase | `p03:{phase}:{cycle}:{batch_hash}` | `p03:R6:01ABC...:a1b2c3d4e5f6` |

**Batch Hash Computation:**

```python
def compute_batch_hash(event_ids: List[str]) -> str:
    sorted_ids = sorted(event_ids)
    combined = "\x00".join(sorted_ids)
    return hashlib.sha256(combined.encode()).hexdigest()[:12]
```

---

## R6-9. Algorithms — Write Assembly (5.1.6-5.1.7)

### TruthWriteAssembler

Assembles writes for truth layers from phase outputs:

| Layer | Source | Operation |
|-------|--------|-----------|
| st_epi | R2 EpisodeCluster | INSERT |
| st_sem | R3 CREATE | INSERT |
| st_sem | R3 REINFORCE/EXTEND/EVOLVE | UPDATE |
| st_sem | R3 PRUNE | ARCHIVE |
| st_procedural | R5 routines | INSERT |
| st_social | R4 social relationships | INSERT |
| st_prospective | R5 ProspectiveMemory | INSERT |
| st_learning_queue | R4 GapCandidate | INSERT |

### KGWriteAssembler

Assembles writes for KG layers:

| Layer | Source | Operation |
|-------|--------|-----------|
| st_kg_dom | R4 KGEntity (is_new=True) | INSERT |
| st_kg_dom | R4 KGEntityUpdate | UPDATE |
| st_kg_edges | R4 KGEdge (is_new=True) | INSERT |
| st_kg_edges | R4 CausalEdge | INSERT (is_causal=True) |
| st_kg_edges | R4 KGEdgeUpdate | UPDATE |

---

## R6-10. Algorithms — Outbox Assembly (5.1.8)

### OutboxEventAssembler

**Event Topics:**

| Topic | Trigger | Priority |
|-------|---------|----------|
| `p03.consolidation.complete.v1` | Cycle completion | 10 (highest) |
| `p03.truth.created.v1` | ReconciliationAction.CREATE | 50 |
| `p03.truth.reinforced.v1` | ReconciliationAction.REINFORCE | 50 |
| `p03.truth.evolved.v1` | ReconciliationAction.EVOLVE/EXTEND | 50 |
| `p03.memory.pruned.v1` | ReconciliationAction.PRUNE | 50 |
| `p03.pattern.detected.v1` | ReconciliationAction.CREATE | 50 |
| `p03.gap.detected.v1` | GapCandidate → P06 | 30 |

**Completion Event Payload:**

```python
{
    "cycle_id": cycle_ulid,
    "tenant_id": tenant_id,
    "space_id": space_id,
    "timestamp_ms": now_ms,
    "summary": {...},
    "phase_durations": {"R0": 100, "R1": 200, ...},
    "total_events": 50,
    "consolidated_count": 45,
    "duplicate_count": 3,
    "pruned_count": 1,
    "gap_count": 1
}
```

---

## R6-11. Algorithms — Manifest Validation (5.1.9)

### ManifestValidator

**Validation Rules:**

| Rule | Check | DLQ Reason |
|------|-------|------------|
| 1 | All layers in VALID_LAYERS | `invalid_layer` |
| 2 | Idempotency keys match format | `malformed_idempotency_key` |
| 3 | Edge FKs reference staged/existing entities | `orphan_fk_reference` |
| 4 | All batch events have staged update | `missing_event_coverage` |
| 5 | At least 1 outbox event | `zero_outbox_events` |
| 6 | No duplicate record_ids per layer | `duplicate_record_ids` |
| 7 | Version conflicts <10% | `version_conflict_threshold_exceeded` |

**DLQ Flow:**

```
ManifestValidator.validate() → is_valid=False
    → R6CoordinatorResult(success=False, dlq_reason=...)
    → P03PhaseResult.fail()
    → Envelope routed to DLQ
```

---

## R6-12. Configuration

### R6CoordinatorConfig

```python
@dataclass
class R6CoordinatorConfig:
    dry_run: bool = False           # Skip actual writes
    validate_manifest: bool = True  # Run validation
    emit_metrics: bool = True       # Emit metrics
```

### ConsolidationStatusMarker Config

```python
low_confidence_threshold: float = 0.5
flag_low_confidence: bool = False  # If True, low confidence → PENDING_REVIEW
```

---

## R6-13. Statistics & Metrics

### R6CoordinatorResult.step_durations_ms

| Step | Description |
|------|-------------|
| `build_event_updates` | Status marking + dedup metadata |
| `assemble_truth_writes` | TruthWriteAssembler |
| `assemble_kg_writes` | KGWriteAssembler |
| `generate_summary` | SummaryGenerator |
| `assemble_outbox` | OutboxEventAssembler |
| `build_r6_output` | R6Output construction |
| `validate_manifest` | ManifestValidator |

### ManifestValidationResult.stats

| Stat | Description |
|------|-------------|
| `total_writes` | Total database writes |
| `truth_writes` | Truth layer writes |
| `kg_writes` | KG writes |
| `outbox_events` | Outbox events |
| `event_updates` | Per-event status updates |
| `version_conflicts` | Events with version mismatch |

---

## R6-14. Error Handling

```python
try:
    result = coordinator.execute(...)
except Exception as e:
    return P03PhaseResult.fail(
        phase_id=P03PhaseId.R6_STAGE,
        error=P03Error(
            error_type="R6_STAGING_ERROR",
            error_message=str(e),
            recoverable=True  # R6 can be retried
        )
    )
```

**Recoverable:** R6 is idempotent — same inputs produce same outputs.

---

## R6-15. ASCII Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         R6 STAGING PHASE                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        R6Staging.run()                              │   │
│  │  1. Create R6Coordinator                                            │   │
│  │  2. Extract R1-R5 inputs from envelope                              │   │
│  │  3. Execute coordinator                                             │   │
│  │  4. Populate envelope with R6Output                                 │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      R6Coordinator.execute()                        │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│           ┌───────────────────┼───────────────────┐                         │
│           │                   │                   │                         │
│           ▼                   ▼                   ▼                         │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                │
│  │ Status Marker  │  │ Dedup Metadata │  │  Recon        │                │
│  │ (5.1.2)        │  │ Populator      │  │  Recorder     │                │
│  │                │  │ (5.1.3)        │  │  (5.1.4)      │                │
│  │ CONSOLIDATED   │  │ near_dups_json │  │ best_match_id │                │
│  │ DUPLICATE      │  │ novelty_score  │  │ similarity    │                │
│  │ PRUNED         │  │                │  │ confidence    │                │
│  │ PENDING_REVIEW │  │                │  │               │                │
│  └───────┬────────┘  └───────┬────────┘  └───────┬───────┘                │
│          │                   │                   │                         │
│          └───────────────────┼───────────────────┘                         │
│                              ▼                                             │
│                   ┌──────────────────────┐                                 │
│                   │  StagedEventUpdate   │                                 │
│                   │  (per-event status)  │                                 │
│                   └──────────┬───────────┘                                 │
│                              │                                             │
│  ┌───────────────────────────┼───────────────────────────┐                 │
│  │                           │                           │                 │
│  ▼                           ▼                           ▼                 │
│ ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐         │
│ │TruthWriteAssemb │  │ KGWriteAssembler│  │ OutboxEventAssembler│         │
│ │ler (5.1.6)      │  │ (5.1.7)         │  │ (5.1.8)             │         │
│ │                 │  │                 │  │                     │         │
│ │ st_epi (R2)     │  │ st_kg_dom       │  │ p03.complete.v1     │         │
│ │ st_sem (R3)     │  │ st_kg_edges     │  │ p03.truth.*.v1      │         │
│ │ st_procedural   │  │ (incl causal)   │  │ p03.gap.detected.v1 │         │
│ │ st_social       │  │                 │  │                     │         │
│ │ st_prospective  │  │                 │  │                     │         │
│ │ st_learning_q   │  │                 │  │                     │         │
│ └────────┬────────┘  └────────┬────────┘  └──────────┬──────────┘         │
│          │                    │                      │                     │
│          └────────────────────┼──────────────────────┘                     │
│                               ▼                                            │
│                    ┌────────────────────┐                                  │
│                    │ IdempotencyKeyGen  │                                  │
│                    │ (5.1.5)            │                                  │
│                    │                    │                                  │
│                    │ p03:staging:...    │                                  │
│                    │ p03:write:...      │                                  │
│                    │ p03:emit:...       │                                  │
│                    └─────────┬──────────┘                                  │
│                              │                                             │
│                              ▼                                             │
│                    ┌────────────────────┐                                  │
│                    │ SummaryGenerator   │                                  │
│                    │ (5.1.10)           │                                  │
│                    │                    │                                  │
│                    │ ReconciliationSum. │                                  │
│                    │ action_breakdown   │                                  │
│                    │ layer_write_counts │                                  │
│                    └─────────┬──────────┘                                  │
│                              │                                             │
│                              ▼                                             │
│                    ┌────────────────────┐                                  │
│                    │    R6Output        │                                  │
│                    │    (frozen)        │                                  │
│                    │                    │                                  │
│                    │ staged_event_upd   │                                  │
│                    │ staged_truth_writ  │                                  │
│                    │ staged_kg_writes   │                                  │
│                    │ staged_outbox_evt  │                                  │
│                    │ recon_summary      │                                  │
│                    └─────────┬──────────┘                                  │
│                              │                                             │
│                              ▼                                             │
│                    ┌────────────────────┐                                  │
│                    │ ManifestValidator  │                                  │
│                    │ (5.1.9)            │                                  │
│                    │                    │                                  │
│                    │ ✓ Layer validity   │                                  │
│                    │ ✓ Idempotency keys │                                  │
│                    │ ✓ FK integrity     │                                  │
│                    │ ✓ Event coverage   │                                  │
│                    │ ✓ Outbox minimum   │                                  │
│                    │ ✓ No duplicates    │                                  │
│                    │ ✓ Version conflicts│                                  │
│                    └─────────┬──────────┘                                  │
│                              │                                             │
│              ┌───────────────┴───────────────┐                             │
│              │                               │                             │
│              ▼                               ▼                             │
│    ┌─────────────────┐             ┌─────────────────┐                    │
│    │   is_valid=True │             │  is_valid=False │                    │
│    │                 │             │                 │                    │
│    │ Populate        │             │ DLQ routing     │                    │
│    │ envelope.staged │             │ P03PhaseResult  │                    │
│    │ → R7 commit     │             │ .fail()         │                    │
│    └─────────────────┘             └─────────────────┘                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## R6-16. Summary

R6 Staging is the **Assembly Line** of P03, collecting all phase outputs and preparing atomic database writes:

1. **Status Marking** — Assign CONSOLIDATED/DUPLICATE/PRUNED/PENDING_REVIEW
2. **Dedup Metadata** — Populate near_duplicates_json, novelty_score
3. **Reconciliation Recording** — Audit trail of decisions
4. **Idempotency Keys** — Deterministic keys for retry safety
5. **Truth Write Assembly** — st_epi, st_sem, st_procedural, etc.
6. **KG Write Assembly** — st_kg_dom, st_kg_edges (with causal edges)
7. **Outbox Assembly** — Events for R8 emission
8. **Summary Generation** — ReconciliationSummary statistics
9. **Manifest Validation** — DLQ routing for invalid manifests

**Key Design Decisions:**

- **R6Output is frozen** — Immutability ensures no accidental modifications before R7
- **Dependency order** — Writes ordered for FK constraints (vec → kg_dom → kg_edges → ...)
- **Manifest validation** — DLQ routing prevents corrupt writes
- **Idempotency** — Same inputs produce same outputs for retry safety
- **StagedWritesContainer** — Mutable builder pattern for R6Output construction

**Key Outputs:**

- `staged_event_updates` → `st_hipp_events` (UPDATE)
- `staged_truth_writes` → truth layers (INSERT/UPDATE/ARCHIVE)
- `staged_kg_writes` → KG layers (INSERT/UPDATE)
- `staged_outbox_events` → R8 emission
- `reconciliation_summary` → Metrics/logging

---
