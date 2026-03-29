# Temporal Anchoring & Holistic Context — Implementation Plan

**Date**: 2025-01-17
**Status**: READY FOR IMPLEMENTATION
**Priority**: CRITICAL
**Pipeline Scope**: P03 Consolidation (WRITE operations only)

---

> **Architecture Boundary**
>
> This plan covers **P03 Consolidation** — writing holistic context to st_observations during truth layer operations.
>
> **Reading/querying observations** belongs to **P01 Recall** and will be implemented separately in `k0/modules/recall/observation_context_fetcher.py`.
>
> See [Architecture Boundary: P03 vs P01](#architecture-boundary-p03-write-vs-p01-read) for details.

---

## Scope Expansion: From Temporal to Holistic

### Original Problem: Lost Timestamps
Every observation is reduced to `observation_count += 1`.

### Expanded Problem: Lost Context
st_hipp_events contains **rich contextual signals** that are discarded during consolidation:

| Signal Category | st_hipp_events Fields | Currently Lost? |
|-----------------|----------------------|-----------------|
| **Emotional** | `sentiment_score`, `sentiment_label`, `dominant_emotions_json`, `affect_valence`, `affect_arousal` | ✅ YES |
| **Salience** | `salience_score`, `novelty_score`, `salience_band` | ✅ YES |
| **Modality** | `ingress_channel`, `ingress_source`, `device_kind` | ✅ YES |
| **Physical** | `location_name`, `location_type`, `geohash_6` | ✅ YES |
| **Social** | `participants_json`, `social_context`, `social_intimacy`, `is_solo_event` | ✅ YES |
| **Temporal** | `time_of_day_bucket`, `circadian_slot`, `is_weekend` | ✅ YES |

### Solution: st_observations as Holistic Context Log

st_observations will capture not just WHEN but also:
- **How did they feel?** (emotional context)
- **How important was it?** (salience)
- **How did they tell us?** (modality)
- **Where were they?** (physical context)
- **Who was present?** (social context)
- **What part of day?** (temporal context)

---

## Codebase Feasibility Analysis

### Assumptions (Validated via Code Discovery)

| Assumption | Validation | Evidence |
|------------|------------|----------|
| R0 correctly loads timestamps | ✅ CONFIRMED | `r0_batch_selector.py:639` — `timestamp=event_time_ms` |
| StagedWrite carries source_event_ids | ✅ CONFIRMED | `staged_writes.py:79` — `source_event_ids: List[str]` |
| Truth writers have INSERT + MERGE paths | ✅ CONFIRMED | All 5 layers have `_insert()`, `_reinforce()` patterns |
| UnitOfWork provides DB connection | ✅ CONFIRMED | All writers use `uow.connection.execute()` |
| st_anchor_observations pattern exists | ✅ CONFIRMED | Migration `0039` — exact model for st_observations |
| TemporalParser uses datetime.now() fallback | ✅ CONFIRMED | `temporal_parser.py:263` — the bug exists |
| EpisodeCluster has member_event_ids | ✅ CONFIRMED | `phase_outputs.py:79` — `member_event_ids: List[str]` |
| Observation counts increment only | ✅ CONFIRMED | All layers: `observation_count = observation_count + 1` |

### What CAN Be Done (Green Light)

| Feature | Feasibility | Rationale |
|---------|-------------|-----------|
| **st_observations table** | ✅ HIGH | Follows existing `st_anchor_observations` pattern exactly |
| **ObservationRecorder service** | ✅ HIGH | Simple INSERT wrapper, no complex logic |
| **TemporalParser fix** | ✅ HIGH | Single line change + caller updates |
| **TemporalAnchor dataclass** | ✅ HIGH | Pure data structure, no dependencies |
| **Episodic layer integration** | ✅ HIGH | `_reinforce()` method already exists at line 318 |
| **Semantic layer integration** | ✅ HIGH | `_reinforce()` method exists at line 357 |
| **Social layer integration** | ✅ HIGH | `_reinforce()` method exists at line 410 |
| **KG layer integration** | ✅ HIGH | `_update_entity_reinforce()` at line 450 |
| **Prospective layer integration** | ✅ MEDIUM | INSERT only (no merge), needs anchor storage |

### What CAN Be Done BUT With Caveats (Yellow Light)

| Feature | Feasibility | Caveat |
|---------|-------------|--------|
| **Holistic life queries** | ⚠️ MEDIUM | Requires JOIN with st_observations; slower than inline array |
| **Trend detection queries** | ⚠️ MEDIUM | Aggregate queries over observations may need materialized views at scale |
| **Pipeline data flow (R2→R6)** | ⚠️ MEDIUM | Need to add `member_timestamps` to EpisodeCluster; flow-through changes |
| **Backfilling existing records** | ⚠️ LOW | source_events_json exists but no timestamps; can only backfill observation_count=1 |

### What CANNOT Be Done (Red Light / Gaps)

| Gap | Reason | Workaround |
|-----|--------|------------|
| **Historical timestamp recovery** | Existing merges lost timestamps forever | Can only track NEW observations going forward |
| **100% accurate anchor times** | Events ingested without event_time_utc (legacy) | Use created_at as fallback anchor |
| **Sub-second precision** | Timestamps are milliseconds, some events same ms | ULID observation_id provides ordering within ms |
| **Observation deletion** | Append-only design | Archive/flag observations, don't delete |
| **Cross-tenant queries** | st_observations partitioned by tenant | No global temporal queries (by design) |

---

## Architecture: Self-Sufficient Observation Layer

### Key Insight: st_observations Tracks TRUTH LAYERS, Not Raw Events

```
st_hipp_events (staging, 20-day tombstone)
        ↓ consolidation (P03)
Truth Layers (st_epi, st_sem, st_kg_dom, st_social, st_prospective)
        ↓ every INSERT/MERGE
st_observations (append-only observation log) ← PERMANENT, SELF-CONTAINED
```

**st_observations is linked to TRUTH LAYERS which are permanent (1-5 year TTL).**
**It does NOT depend on st_hipp_events (20-day tombstone).**

### Why This Architecture Is Self-Sufficient

| Field | Source | Lifetime | Dependency |
|-------|--------|----------|------------|
| `layer` | 'st_epi', 'st_sem', etc. | Permanent | None |
| `record_id` | FK to truth layer PK | Permanent | st_epi, st_sem, etc. (1-5 years) |
| `observed_at` | Timestamp of observation | Permanent | None (self-contained) |
| `observation_type` | FIRST_SEEN / REINFORCEMENT | Permanent | None |
| `source_event_id` | **OPTIONAL** soft reference | Degrades after 20 days | Nice-to-have only |

### What Happens After st_hipp_events Tombstone (20 days)?

| Component | Status | Impact |
|-----------|--------|--------|
| `observed_at` | ✅ Preserved | Full temporal queries work |
| `record_id` → truth layer | ✅ Preserved | Can JOIN to st_epi, st_sem, etc. |
| `observation_type` | ✅ Preserved | Know if FIRST_SEEN or REINFORCEMENT |
| `source_event_id` | ⚠️ Orphaned | Cannot trace to original text (acceptable) |

**Verdict**: st_observations is 100% functional without st_hipp_events.

---

## Dependencies Resolved

### ✅ RESOLVED: st_hipp_events Decay (Not a Blocker)

**Original Concern**: `source_event_id` FK breaks after 20 days.

**Resolution**:
- `source_event_id` is **OPTIONAL soft reference** (no FK constraint)
- All temporal queries work via `observed_at` + `record_id` → truth layer
- Original event text is NOT needed for temporal distribution queries

### ✅ RESOLVED: EpisodeCluster Missing member_timestamps

**Solution in Issue 7.6**:
- Add `member_timestamps: List[int]` to EpisodeCluster
- R2 populates: `member_timestamps = [e.timestamp for e in events]`
- Parallel to existing `member_event_ids`

### ✅ RESOLVED: StagedWrite Missing timestamp Field

**Solution in Issue 7.6**:
- Convention: `record_data["observed_at"]` for observation timestamp
- Fallback chain: `record_data["observed_at"]` → `StagedWrite.created_at_ms`
- All R6 staging code passes timestamp

### ✅ RESOLVED: Prospective Memory Has No Anchor Storage

**Solution in Issue 7.7**:
- Store `anchor_time_utc` and `original_temporal_expr` in st_observations
- Query: `WHERE layer = 'st_prospective' AND anchor_time_utc BETWEEN...`

---

## Storage & Performance Projections

### Current Scale (From memory_tables_consolidated.md)

| Table | Rows | Est. Observations |
|-------|------|-------------------|
| st_epi | 435 | 4,350 (10x) |
| st_sem | 848 | 4,240 (5x) |
| st_kg_dom | 188 | 4,700 (25x) |
| st_social | 3 | 150 (50x) |
| **Total** | 1,474 | **~13,500** |

### 1-Year Projection (10 events/day)

| Component | Estimate |
|-----------|----------|
| Daily events | 10 |
| Yearly events | 3,650 |
| Observations per event | 3 (avg: epi + sem + kg) |
| Yearly observations | ~11,000 |
| Row size (avg) | 200 bytes |
| Yearly storage | ~2.2 MB |

**Verdict**: Storage is negligible. Index maintenance is the only concern at scale.

### Query Performance Analysis

| Query Type | Expected Performance | Notes |
|------------|---------------------|-------|
| Single record observations | O(log n) | `idx_obs_record_time` |
| Temporal range (1 month) | O(n * selectivity) | ~1000 rows scanned |
| Trend detection (GROUP BY month) | O(n) | Consider materialized view at 100K+ |
| Full table scan | O(n) | Avoid; use tenant + time filters |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Performance degradation at scale | LOW | MEDIUM | Partition by tenant_id, add materialized views |
| Legacy events have no anchor | MEDIUM | LOW | Fallback to created_at |
| Truth writer regression | LOW | HIGH | Comprehensive test coverage |
| EpisodeCluster changes break R2 | MEDIUM | MEDIUM | Add field as Optional with default |

**Note**: st_hipp_events FK integrity is NOT a risk — st_observations is self-sufficient.

---

## Table of Contents

1. [Scope Expansion](#scope-expansion-from-temporal-to-holistic)
2. [Codebase Feasibility Analysis](#codebase-feasibility-analysis)
3. [Architecture Decision](#architecture-self-sufficient-observation-layer)
4. [Issue Breakdown](#issue-breakdown)
   - [Issue 7.1: Schema Migration](#issue-71-schema-migration--st_observations-table)
   - [Issue 7.2: ObservationContext Dataclass](#issue-72-observationcontext-dataclass)
   - [Issue 7.3: TemporalParser Fix](#issue-73-temporalparser-fix)
   - [Issue 7.4: Observation Recorder](#issue-74-observation-recorder-service)
   - [Issue 7.5: Truth Writer Integration](#issue-75-truth-writer-integration)
   - [Issue 7.6: Pipeline Data Flow](#issue-76-pipeline-data-flow-r0--r7)
   - [Issue 7.7: Prospective Memory Enhancement](#issue-77-prospective-memory-enhancement)
5. [Test Plan](#test-plan)
6. [Architecture Boundary: P03 vs P01](#architecture-boundary-p03-write-vs-p01-read)
7. [New Features Enabled (P01 Recall)](#new-features-enabled-p01-recall--informational)
8. [Appendix: Investigation Evidence](#appendix-investigation-evidence)

---

## Executive Summary

### The Problem

Temporal signals are **correctly captured** at ingestion (P02 -> st_hipp_events) but are **LOST during merge operations** across all truth layers. When records are merged, we only increment `observation_count` but do NOT preserve individual occurrence timestamps.

**Example**:
```
Day 1: "Had lunch at cafeteria" -> Event 1 (timestamp: 1704067200000)
Day 2: "Had lunch at cafeteria" -> Event 2 (timestamp: 1704153600000)
...
Day 365: -> Event 365

Current Result in st_sem:
  - observation_count: 365
  - first_observed_at: Day 1
  - last_observed_at: Day 365
  - WHERE ARE THE OTHER 363 TIMESTAMPS? LOST!
```

**Queries That FAIL**:
- "What did I eat last summer?" (no per-occurrence timestamps)
- "When do I usually go to the gym?" (no time-of-day distribution)
- "Am I exercising more recently?" (no trend data)
- "Remind me next week" (anchor lost if processing delayed)

### The Solution

Create a normalized `st_observations` table following the existing `st_anchor_observations` pattern. Every merge/insert operation records an observation with full temporal context.

---

## Architecture Decision

### Selected: Option B — Normalized Observations Table

**Rationale**:
1. Follows existing `st_anchor_observations` pattern
2. Bounded parent table growth
3. Rich context per observation (source_event_id, observation_type)
4. Prunable (can archive old observations)
5. Query-friendly with proper indexes

### Alternatives Rejected

| Option | Approach | Why Rejected |
|--------|----------|--------------|
| A | Array append (`BIGINT[]`) | Unbounded growth, slow at scale |
| C | Hybrid histogram + details | Over-engineering for current needs |

### Storage Impact

| Table | Current Rows | Est. Observations/Row | Total Observations |
|-------|-------------|----------------------|-------------------|
| st_epi | 435 | ~10 | 4,350 |
| st_sem | 848 | ~5 | 4,240 |
| st_kg_dom | 188 | ~25 | 4,700 |
| st_social | 3 | ~50 | 150 |
| **Total** | | | ~13,500 rows |

**Verdict**: Negligible storage impact. At scale (10 years), pruning strategy handles growth.

---

## Issue Breakdown

---

### Issue 7.1: Schema Migration — st_observations Table

**Status**: [ ] NOT STARTED
**Complexity**: LOW
**Dependencies**: None

#### Objective

Create the `st_observations` table to store individual observation timestamps with full context. This table is **self-sufficient** — it tracks observations of TRUTH LAYER records, not raw events.

#### Architecture

```
Truth Layers (permanent: 1-5 year TTL)
    st_epi, st_sem, st_kg_dom, st_social, st_prospective
              ↓ every INSERT/MERGE
    st_observations (append-only temporal log)
              ↓ queries
    "What did I eat last summer?" ✅
```

#### Schema

```sql
CREATE TABLE st_observations (
    -- ============================================================
    -- Identity
    -- ============================================================
    observation_id TEXT PRIMARY KEY,  -- ULID (provides sub-ms ordering)

    -- Link to TRUTH LAYER record (THE PRIMARY RELATIONSHIP)
    layer TEXT NOT NULL,  -- 'st_epi', 'st_sem', 'st_kg_dom', 'st_social', 'st_prospective'
    record_id TEXT NOT NULL,  -- FK to parent record PK (episode_id, pattern_id, entity_id, etc.)

    -- Multi-tenant
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,

    -- ============================================================
    -- Temporal Context (SELF-CONTAINED)
    -- ============================================================
    observed_at BIGINT NOT NULL,  -- Unix ms - when this observation happened
    anchor_time_utc BIGINT,  -- For prospective: when user spoke
    original_temporal_expr TEXT,  -- "next week", "tomorrow", "last summer"
    time_of_day_bucket TEXT,  -- 'MORNING', 'AFTERNOON', 'EVENING', 'NIGHT'
    circadian_slot TEXT,  -- 'WAKE', 'ACTIVE', 'WIND_DOWN', 'SLEEP'
    is_weekend BOOLEAN,  -- Saturday/Sunday

    -- ============================================================
    -- Emotional Context (from st_hipp_events)
    -- ============================================================
    sentiment_score FLOAT,  -- 0.0 (negative) to 1.0 (positive)
    sentiment_label TEXT,  -- 'negative', 'neutral', 'positive'
    affect_valence FLOAT,  -- -1.0 to +1.0
    affect_arousal FLOAT,  -- 0.0 (calm) to 1.0 (intense)
    dominant_emotion TEXT,  -- First emotion from dominant_emotions_json

    -- ============================================================
    -- Salience Context (from st_hipp_events)
    -- ============================================================
    salience_score FLOAT,  -- 0.0 to 1.0
    salience_band TEXT,  -- 'HIGH', 'MED', 'LOW'
    novelty_score FLOAT,  -- 0.0 (repetition) to 1.0 (completely new)

    -- ============================================================
    -- Modality Context (from st_hipp_events)
    -- ============================================================
    ingress_channel TEXT,  -- 'voice', 'chat', 'api', 'calendar', etc.
    ingress_source TEXT,  -- Concrete origin (app name, integration)
    device_kind TEXT,  -- 'phone', 'desktop', 'speaker', 'wearable'

    -- ============================================================
    -- Physical Context (from st_hipp_events)
    -- ============================================================
    location_name TEXT,  -- 'Home', 'Office', etc.
    location_type TEXT,  -- 'home', 'work', 'transit', 'other'
    geohash_6 TEXT,  -- Spatial precision

    -- ============================================================
    -- Social Context (from st_hipp_events)
    -- ============================================================
    social_context TEXT,  -- 'solo', 'family', 'work', 'social'
    social_intimacy TEXT,  -- Relationship closeness
    is_solo_event BOOLEAN,  -- No others present
    num_participants INTEGER,  -- Count of people involved

    -- ============================================================
    -- Classification
    -- ============================================================
    observation_type TEXT NOT NULL DEFAULT 'REINFORCEMENT',
    -- FIRST_SEEN: Initial creation of truth record
    -- REINFORCEMENT: Repeated observation (most common)
    -- CORRECTION: User corrected a value
    -- INFERENCE: Inferred from context

    confidence FLOAT DEFAULT 1.0,  -- Observation confidence

    -- ============================================================
    -- Provenance (optional, degrades after 20 days)
    -- ============================================================
    source_event_id TEXT,  -- Soft reference to st_hipp_events
    consolidation_cycle_id TEXT,  -- Which P03 cycle created this

    -- ============================================================
    -- Lifecycle
    -- ============================================================
    created_at BIGINT NOT NULL,

    -- Constraints
    CHECK (layer IN ('st_epi', 'st_sem', 'st_kg_dom', 'st_social', 'st_prospective'))
);

-- ============================================================
-- Indexes
-- ============================================================

-- Primary query pattern: Get observations for a truth record
CREATE INDEX idx_obs_record_time ON st_observations (layer, record_id, observed_at DESC);

-- Temporal range queries: "What happened last summer?"
CREATE INDEX idx_obs_tenant_time ON st_observations (tenant_id, observed_at DESC);

-- Prospective queries: "What reminders did I set last week?"
CREATE INDEX idx_obs_anchor_time ON st_observations (layer, anchor_time_utc DESC)
    WHERE layer = 'st_prospective' AND anchor_time_utc IS NOT NULL;

-- Emotional queries: "What makes me happy?"
CREATE INDEX idx_obs_sentiment ON st_observations (tenant_id, sentiment_label, observed_at DESC)
    WHERE sentiment_label IS NOT NULL;

-- Salience queries: "What stood out this year?"
CREATE INDEX idx_obs_salience ON st_observations (tenant_id, salience_band, observed_at DESC)
    WHERE salience_band = 'HIGH';

-- Modality queries: "What do I say vs type?"
CREATE INDEX idx_obs_channel ON st_observations (tenant_id, ingress_channel, observed_at DESC)
    WHERE ingress_channel IS NOT NULL;

-- Social queries: "What do we discuss as a family?"
CREATE INDEX idx_obs_social ON st_observations (tenant_id, social_context, observed_at DESC)
    WHERE social_context IS NOT NULL;

-- Location queries: "What do I think about at work?"
CREATE INDEX idx_obs_location ON st_observations (tenant_id, location_type, observed_at DESC)
    WHERE location_type IS NOT NULL;
```

#### Files to Create

| File | Description |
|------|-------------|
| `k0/db/alembic/versions/0067_st_observations.py` | Alembic migration |

#### Acceptance Criteria

- [ ] Migration runs successfully
- [ ] All indexes are created
- [ ] Rollback (downgrade) works
- [ ] No FK constraint to st_hipp_events
- [ ] Existing tables unaffected

#### Implementation Notes

```
<!-- TODO: Fill during implementation -->
```

---

### Issue 7.2: ObservationContext Dataclass

**Status**: [ ] NOT STARTED
**Complexity**: MEDIUM
**Dependencies**: None

#### Objective

Create a comprehensive dataclass to carry **all holistic context** through the pipeline. This replaces the simpler TemporalAnchor concept with a full observation context snapshot.

#### Interface

```python
@dataclass
class ObservationContext:
    """Full context snapshot for a memory observation.

    Captures the holistic state at the moment of observation:
    - When it happened (temporal)
    - How they felt (emotional)
    - How important (salience)
    - How they told us (modality)
    - Where they were (physical)
    - Who was present (social)
    """

    # === Temporal (REQUIRED) ===
    observed_at: int  # When observation happened (ms, REQUIRED)
    anchor_time_utc: Optional[int] = None  # For prospective: when user spoke
    original_temporal_expr: Optional[str] = None  # "next week", "tomorrow"
    time_of_day_bucket: Optional[str] = None  # 'MORNING', 'AFTERNOON', etc.
    circadian_slot: Optional[str] = None  # 'WAKE', 'ACTIVE', etc.
    is_weekend: Optional[bool] = None

    # === Emotional ===
    sentiment_score: Optional[float] = None  # 0.0 to 1.0
    sentiment_label: Optional[str] = None  # 'negative', 'neutral', 'positive'
    affect_valence: Optional[float] = None  # -1.0 to +1.0
    affect_arousal: Optional[float] = None  # 0.0 to 1.0
    dominant_emotion: Optional[str] = None  # First from emotions array

    # === Salience ===
    salience_score: Optional[float] = None
    salience_band: Optional[str] = None  # 'HIGH', 'MED', 'LOW'
    novelty_score: Optional[float] = None

    # === Modality ===
    ingress_channel: Optional[str] = None  # 'voice', 'chat', 'api'
    ingress_source: Optional[str] = None  # Concrete origin
    device_kind: Optional[str] = None  # 'phone', 'desktop', 'speaker'

    # === Physical ===
    location_name: Optional[str] = None
    location_type: Optional[str] = None  # 'home', 'work', 'transit'
    geohash_6: Optional[str] = None

    # === Social ===
    social_context: Optional[str] = None  # 'solo', 'family', 'work'
    social_intimacy: Optional[str] = None
    is_solo_event: Optional[bool] = None
    num_participants: Optional[int] = None

    # === Classification ===
    observation_type: str = "REINFORCEMENT"
    confidence: float = 1.0

    # === Provenance ===
    source_event_id: Optional[str] = None
    consolidation_cycle_id: Optional[str] = None

    @classmethod
    def from_event(cls, event: "P03EventState") -> "ObservationContext":
        """Create context from P03 event state.

        Extracts all available context fields from the event.
        """
        return cls(
            # Temporal
            observed_at=event.timestamp,
            time_of_day_bucket=getattr(event, 'time_of_day_bucket', None),
            circadian_slot=getattr(event, 'circadian_slot', None),
            is_weekend=getattr(event, 'is_weekend', None),
            # Emotional
            sentiment_score=getattr(event, 'sentiment_score', None),
            sentiment_label=getattr(event, 'sentiment_label', None),
            affect_valence=getattr(event, 'affect_valence', None),
            affect_arousal=getattr(event, 'affect_arousal', None),
            dominant_emotion=cls._extract_first_emotion(getattr(event, 'dominant_emotions_json', None)),
            # Salience
            salience_score=getattr(event, 'salience_score', None),
            salience_band=getattr(event, 'salience_band', None),
            novelty_score=getattr(event, 'novelty_score', None),
            # Modality
            ingress_channel=getattr(event, 'ingress_channel', None),
            ingress_source=getattr(event, 'ingress_source', None),
            device_kind=getattr(event, 'device_kind', None),
            # Physical
            location_name=getattr(event, 'location_name', None),
            location_type=getattr(event, 'location_type', None),
            geohash_6=getattr(event, 'geohash_6', None),
            # Social
            social_context=getattr(event, 'social_context', None),
            social_intimacy=getattr(event, 'social_intimacy', None),
            is_solo_event=getattr(event, 'is_solo_event', None),
            num_participants=getattr(event, 'num_participants', None),
            # Provenance
            source_event_id=event.event_id,
            observation_type="REINFORCEMENT",
            confidence=1.0,
        )

    @staticmethod
    def _extract_first_emotion(emotions_json: Optional[str]) -> Optional[str]:
        """Extract first emotion from JSON array."""
        if not emotions_json:
            return None
        try:
            import json
            emotions = json.loads(emotions_json)
            return emotions[0] if emotions else None
        except (json.JSONDecodeError, IndexError):
            return None

    @classmethod
    def from_timestamp(cls, timestamp_ms: int) -> "ObservationContext":
        """Create minimal context from raw timestamp."""
        return cls(observed_at=timestamp_ms)
```

#### Files to Create

| File | Description |
|------|-------------|
| `k0/modules/consolidation/algorithms/observation_context.py` | ObservationContext dataclass |

#### Acceptance Criteria

- [ ] Dataclass created with all 25+ fields
- [ ] `from_event()` factory extracts all available context
- [ ] `from_timestamp()` works for minimal context
- [ ] Unit tests for both factory methods
- [ ] JSON serialization works (for debugging)

#### Implementation Notes

```
<!-- TODO: Fill during implementation -->
```

---

### Issue 7.3: TemporalParser Fix

**Status**: [ ] NOT STARTED
**Complexity**: LOW
**Dependencies**: Issue 7.2 (ObservationContext)

#### Objective

Fix the TemporalParser to REQUIRE anchor time instead of defaulting to `datetime.now()`.

#### Current Bug

**File**: `k0/modules/consolidation/algorithms/temporal_parser.py` (line 263)

```python
# BEFORE (buggy):
ref = datetime.fromtimestamp((ref_time or int(datetime.now().timestamp() * 1000)) / 1000)
```

#### Fix

```python
# AFTER (correct):
def _parse_temporal_text(self, text: str, ref_time: int) -> Optional[int]:
    """ref_time is now REQUIRED, not Optional."""
    if ref_time is None or ref_time == 0:
        raise ValueError("anchor_time is REQUIRED for temporal parsing - use event.timestamp")
    ref = datetime.fromtimestamp(ref_time / 1000)
    # ... rest of method
```

#### Files to Modify

| File | Change |
|------|--------|
| `k0/modules/consolidation/algorithms/temporal_parser.py` | Make ref_time required |

#### Acceptance Criteria

- [ ] ValueError raised when ref_time is None
- [ ] ValueError raised when ref_time is 0
- [ ] Existing callers updated to pass event.timestamp
- [ ] All existing tests pass

#### Implementation Notes

```
<!-- TODO: Fill during implementation -->
```

---

### Issue 7.4: Observation Recorder Service

**Status**: [ ] NOT STARTED
**Complexity**: MEDIUM
**Dependencies**: Issue 7.1 (Schema), Issue 7.2 (ObservationContext)

#### Objective

Create a reusable service that records observations with **full holistic context** to `st_observations` table.

#### Interface

```python
class ObservationRecorder:
    """Records observations with full context to st_observations table."""

    async def record(
        self,
        uow: UnitOfWork,
        layer: str,
        record_id: str,
        context: ObservationContext,
        tenant_id: str,
        space_id: str,
    ) -> str:
        """Record a single observation with full context.

        Args:
            uow: Unit of work for transaction
            layer: Truth layer ('st_epi', 'st_sem', etc.)
            record_id: FK to truth layer record
            context: Full observation context (temporal, emotional, etc.)
            tenant_id: Tenant identifier
            space_id: Space identifier

        Returns:
            observation_id (ULID)
        """
        observation_id = generate_ulid()

        await uow.connection.execute(
            """
            INSERT INTO st_observations (
                observation_id, layer, record_id, tenant_id, space_id,
                -- Temporal
                observed_at, anchor_time_utc, original_temporal_expr,
                time_of_day_bucket, circadian_slot, is_weekend,
                -- Emotional
                sentiment_score, sentiment_label, affect_valence,
                affect_arousal, dominant_emotion,
                -- Salience
                salience_score, salience_band, novelty_score,
                -- Modality
                ingress_channel, ingress_source, device_kind,
                -- Physical
                location_name, location_type, geohash_6,
                -- Social
                social_context, social_intimacy, is_solo_event, num_participants,
                -- Classification
                observation_type, confidence,
                -- Provenance
                source_event_id, consolidation_cycle_id,
                -- Lifecycle
                created_at
            ) VALUES (
                :observation_id, :layer, :record_id, :tenant_id, :space_id,
                :observed_at, :anchor_time_utc, :original_temporal_expr,
                :time_of_day_bucket, :circadian_slot, :is_weekend,
                :sentiment_score, :sentiment_label, :affect_valence,
                :affect_arousal, :dominant_emotion,
                :salience_score, :salience_band, :novelty_score,
                :ingress_channel, :ingress_source, :device_kind,
                :location_name, :location_type, :geohash_6,
                :social_context, :social_intimacy, :is_solo_event, :num_participants,
                :observation_type, :confidence,
                :source_event_id, :consolidation_cycle_id,
                :created_at
            )
            """,
            {
                "observation_id": observation_id,
                "layer": layer,
                "record_id": record_id,
                "tenant_id": tenant_id,
                "space_id": space_id,
                **context.to_dict(),  # All context fields
                "created_at": _now_ms(),
            }
        )
        return observation_id

    async def record_batch(
        self,
        uow: UnitOfWork,
        observations: List[Tuple[str, str, ObservationContext, str, str]],
    ) -> List[str]:
        """Record multiple observations efficiently.

        Args:
            observations: List of (layer, record_id, context, tenant_id, space_id)

        Returns:
            List of observation_ids
        """
        ...
```

#### Files to Create

| File | Description |
|------|-------------|
| `k0/modules/consolidation/truth_writer/observation_recorder.py` | ObservationRecorder class |

#### Acceptance Criteria

- [ ] Single observation recording works with full context
- [ ] Batch recording works efficiently
- [ ] ULID generation for observation_id
- [ ] All 25+ context fields correctly persisted
- [ ] NULL handling for optional fields
- [ ] Integration test with real database

#### Implementation Notes

```
<!-- TODO: Fill during implementation -->
```

---

### Issue 7.5: Truth Writer Integration

**Status**: [ ] NOT STARTED
**Complexity**: MEDIUM
**Dependencies**: Issue 7.4 (ObservationRecorder)

#### Objective

Integrate ObservationRecorder into all truth writer layers so every INSERT and MERGE records an observation **with full context**.

#### Layers to Modify

| Layer | File | Observation Type on INSERT | Observation Type on MERGE |
|-------|------|---------------------------|---------------------------|
| Episodic | `layers/episodic.py` | FIRST_SEEN | REINFORCEMENT |
| Semantic | `layers/semantic.py` | FIRST_SEEN | REINFORCEMENT |
| Social | `layers/social.py` | FIRST_SEEN | REINFORCEMENT |
| KG Domain | `layers/kg.py` | FIRST_SEEN | REINFORCEMENT |
| Prospective | `layers/prospective.py` | FIRST_SEEN | N/A (no merge) |

#### Pattern

```python
# In each layer's _insert() and _merge() method:

async def _insert(self, uow: UnitOfWork, write: StagedWrite) -> None:
    # ... existing insert logic ...

    # NEW: Record observation with FULL context
    context = write.observation_context  # Attached in R6
    context.observation_type = "FIRST_SEEN"

    await self._observation_recorder.record(
        uow=uow,
        layer=self.LAYER,
        record_id=write.record_id,
        context=context,
        tenant_id=write.tenant_id,
        space_id=write.space_id,
    )

async def _merge(self, uow: UnitOfWork, write: StagedWrite) -> None:
    # ... existing merge logic ...

    # NEW: Record observation with FULL context
    context = write.observation_context  # Attached in R6
    context.observation_type = "REINFORCEMENT"

    await self._observation_recorder.record(
        uow=uow,
        layer=self.LAYER,
        record_id=write.record_id,
        context=context,
        tenant_id=write.tenant_id,
        space_id=write.space_id,
    )
```

#### Files to Modify

| File | Change |
|------|--------|
| `k0/modules/consolidation/truth_writer/layers/episodic.py` | Add observation recording with context |
| `k0/modules/consolidation/truth_writer/layers/semantic.py` | Add observation recording with context |
| `k0/modules/consolidation/truth_writer/layers/social.py` | Add observation recording with context |
| `k0/modules/consolidation/truth_writer/layers/kg.py` | Add observation recording with context |
| `k0/modules/consolidation/truth_writer/layers/prospective.py` | Add observation recording with context |

#### Acceptance Criteria

- [ ] Every INSERT creates a FIRST_SEEN observation with full context
- [ ] Every MERGE creates a REINFORCEMENT observation with full context
- [ ] All 25+ context fields flow from st_hipp_events → st_observations
- [ ] No regression in existing tests

#### Implementation Notes

```
<!-- TODO: Fill during implementation -->
```

---

### Issue 7.6: Pipeline Data Flow (R0 → R7)

**Status**: [ ] NOT STARTED
**Complexity**: HIGH
**Dependencies**: Issue 7.2 (ObservationContext)

#### Objective

Ensure **full holistic context** flows through the pipeline from R0 to R7. This is the critical data plumbing that carries emotional, salience, modality, physical, and social context alongside temporal.

#### Data Flow Overview

```
R0 (Batch Selector)
    ↓ Load ALL context fields from st_hipp_events
    ↓ P03EventState now has 25+ context fields

R2 (Episodic Integrator)
    ↓ EpisodeCluster gets member_contexts: List[ObservationContext]

R3-R5 (Processing)
    ↓ Context flows through unchanged

R6 (Staging)
    ↓ StagedWrite gets observation_context: ObservationContext

R7 (Truth Writer)
    ↓ ObservationRecorder.record(context=...)

st_observations (FULL CONTEXT PRESERVED)
```

#### R0: Batch Selector (EXPAND LOADING)

**File**: `k0/pipelines/p03/phases/r0_batch_selector.py`

Currently loads timestamp. Expand to load ALL context fields:

```python
# Add to SELECT query:
SELECT
    event_id, event_time_utc as timestamp,
    -- Temporal context
    time_of_day_bucket, circadian_slot, is_weekend,
    -- Emotional context
    sentiment_score, sentiment_label, affect_valence, affect_arousal, dominant_emotions_json,
    -- Salience context
    salience_score, salience_band, novelty_score,
    -- Modality context
    ingress_channel, ingress_source, device_kind,
    -- Physical context
    location_name, location_type, geohash_6,
    -- Social context
    social_context, social_intimacy, is_solo_event, num_participants
FROM st_hipp_events
WHERE ...
```

#### P03EventState Enhancement

**File**: `k0/pipelines/p03/phase_outputs.py`

```python
@dataclass
class P03EventState:
    # ... existing fields ...
    timestamp: int = 0

    # NEW: Holistic context fields (from st_hipp_events)
    # Temporal
    time_of_day_bucket: Optional[str] = None
    circadian_slot: Optional[str] = None
    is_weekend: Optional[bool] = None
    # Emotional
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    affect_valence: Optional[float] = None
    affect_arousal: Optional[float] = None
    dominant_emotions_json: Optional[str] = None  # Will extract first emotion
    # Salience
    salience_score: Optional[float] = None
    salience_band: Optional[str] = None
    novelty_score: Optional[float] = None
    # Modality
    ingress_channel: Optional[str] = None
    ingress_source: Optional[str] = None
    device_kind: Optional[str] = None
    # Physical
    location_name: Optional[str] = None
    location_type: Optional[str] = None
    geohash_6: Optional[str] = None
    # Social
    social_context: Optional[str] = None
    social_intimacy: Optional[str] = None
    is_solo_event: Optional[bool] = None
    num_participants: Optional[int] = None

    def to_observation_context(self) -> ObservationContext:
        """Convert event state to observation context."""
        return ObservationContext.from_event(self)
```

#### R2: Episodic Integrator

**File**: `k0/pipelines/p03/phase_outputs.py`

```python
@dataclass
class EpisodeCluster:
    # ... existing fields ...
    member_event_ids: List[str] = field(default_factory=list)

    # NEW: Full context for each member event
    member_contexts: List[ObservationContext] = field(default_factory=list)
```

**File**: `k0/pipelines/p03/phases/r2_episodic_integrator.py`

```python
# When creating EpisodeCluster:
member_contexts = [e.to_observation_context() for e in events]
```

#### StagedWrite Enhancement

**File**: `k0/pipelines/p03/staged_writes.py`

```python
@dataclass
class StagedWrite:
    # ... existing fields ...
    source_event_ids: List[str] = field(default_factory=list)

    # NEW: Observation context for truth writer
    observation_context: Optional[ObservationContext] = None
```

#### R6: Staging

**File**: `k0/pipelines/p03/phases/r6_staging.py`

```python
# When creating StagedWrite for episodic:
staged_write = StagedWrite(
    layer="st_epi",
    record_id=episode_id,
    # ... other fields ...
    observation_context=cluster.member_contexts[0] if cluster.member_contexts else None,
)

# For semantic/kg/social patterns created from events:
staged_write.observation_context = event.to_observation_context()
```

#### Files to Modify

| File | Change |
|------|--------|
| `k0/pipelines/p03/phases/r0_batch_selector.py` | Load all 25+ context fields |
| `k0/pipelines/p03/phase_outputs.py` | Add context fields to P03EventState, EpisodeCluster |
| `k0/pipelines/p03/staged_writes.py` | Add observation_context to StagedWrite |
| `k0/pipelines/p03/phases/r2_episodic_integrator.py` | Build member_contexts |
| `k0/pipelines/p03/phases/r6_staging.py` | Attach observation_context to writes |

#### Acceptance Criteria

- [ ] R0 loads all 25+ context fields from st_hipp_events
- [ ] P03EventState carries all context fields
- [ ] EpisodeCluster preserves member_contexts
- [ ] StagedWrite carries observation_context
- [ ] Context flows from st_hipp_events → st_observations without loss
- [ ] No breaking changes to existing pipeline logic

#### Implementation Notes

```
<!-- TODO: Fill during implementation -->
```

---

### Issue 7.7: Prospective Memory Enhancement

**Status**: [ ] NOT STARTED
**Complexity**: MEDIUM
**Dependencies**: Issue 7.1 (Schema), Issue 7.4 (ObservationRecorder)

```python
# When creating StagedWrite for episodic:
record_data["timestamp"] = cluster.member_timestamps[0] if cluster.member_timestamps else cluster.temporal_start
record_data["source_event_ids"] = cluster.member_event_ids
```

#### Files to Modify

| File | Change |
|------|--------|
| `k0/pipelines/p03/phase_outputs.py` | Add member_timestamps to EpisodeCluster |
| `k0/pipelines/p03/phases/r2_episodic_integrator.py` | Populate member_timestamps |
| `k0/pipelines/p03/phases/r6_staging.py` | Pass timestamps to StagedWrite |

#### Acceptance Criteria

- [ ] EpisodeCluster carries individual timestamps
- [ ] StagedWrite has timestamp for observation recording
- [ ] No data loss between R2 and R7

#### Implementation Notes

```
<!-- TODO: Fill during implementation -->
```

---

### Issue 7.7: Prospective Memory Enhancement

**Status**: [ ] NOT STARTED
**Complexity**: MEDIUM
**Dependencies**: Issue 7.1 (Schema), Issue 7.4 (ObservationRecorder)

#### Objective

Store temporal anchor context for prospective memories (reminders, deadlines) so we know WHEN a temporal expression was spoken.

#### Problem

"Remind me next week" -> If processed 2 days later, "next week" is wrong.

**Current**: Only stores `target_date` (resolved timestamp)
**Need**: Store `anchor_time_utc` (when user said it) + `original_temporal_expr` ("next week")

#### Schema Addition (Part of Issue 7.1)

The `st_observations` table already has:
- `anchor_time_utc BIGINT`
- `original_temporal_expr TEXT`

For prospective layer observations, these fields will be populated.

#### ProspectiveMemory Dataclass Update

**File**: `k0/pipelines/p03/phase_outputs.py`

```python
@dataclass
class ProspectiveMemory:
    # ... existing fields ...
    deadline_ts: Optional[int] = None

    # NEW: Temporal anchor context
    anchor_time_utc: Optional[int] = None  # When user said it
    original_temporal_expr: Optional[str] = None  # "next week", "tomorrow"
```

#### IntentionWriteData Update

**File**: `k0/modules/consolidation/truth_writer/layers/prospective.py`

```python
@dataclass
class IntentionWriteData:
    # ... existing fields ...
    trigger_time_ms: Optional[int] = None

    # NEW: Temporal anchor context
    anchor_time_utc: Optional[int] = None
    original_temporal_expr: Optional[str] = None
```

#### Files to Modify

| File | Change |
|------|--------|
| `k0/pipelines/p03/phase_outputs.py` | Add anchor fields to ProspectiveMemory |
| `k0/modules/consolidation/truth_writer/layers/prospective.py` | Store anchor in observation |
| `k0/pipelines/p03/phases/r6_staging.py` | Pass anchor to prospective writes |

#### Acceptance Criteria

- [ ] anchor_time_utc stored for prospective observations
- [ ] original_temporal_expr stored (e.g., "next week")
- [ ] Query "what reminders did I set last week?" works

#### Implementation Notes

```
<!-- TODO: Fill during implementation -->
```

---

## Test Plan

### Unit Tests

| Test | Issue | Description |
|------|-------|-------------|
| `test_observation_context_from_event` | 7.2 | Factory extracts all 25+ fields |
| `test_observation_context_from_timestamp` | 7.2 | Minimal context factory works |
| `test_observation_context_emotion_extraction` | 7.2 | First emotion parsed from JSON |
| `test_temporal_parser_requires_anchor` | 7.3 | ValueError on None |
| `test_temporal_parser_requires_nonzero` | 7.3 | ValueError on 0 |
| `test_observation_recorder_single` | 7.4 | Single observation with full context |
| `test_observation_recorder_batch` | 7.4 | Batch recording works |
| `test_observation_ulid_generated` | 7.4 | ULID format correct |
| `test_observation_all_fields_persisted` | 7.4 | All 25+ context fields saved |

### Integration Tests

| Test | Issue | Description |
|------|-------|-------------|
| `test_observation_recorded_on_insert` | 7.5 | FIRST_SEEN observation with context |
| `test_observation_recorded_on_merge` | 7.5 | REINFORCEMENT observation with context |
| `test_source_event_optional` | 7.5 | Works with NULL source_event_id |
| `test_context_flows_r0_to_r7` | 7.6 | All context preserved through pipeline |
| `test_episode_member_contexts` | 7.6 | Member contexts flow through |
| `test_p03_event_state_context_fields` | 7.6 | P03EventState has all fields |
| `test_prospective_anchor_stored` | 7.7 | Anchor stored for reminders |

### Query Tests — Holistic Context

| Test | Query Type | Description |
|------|------------|-------------|
| `test_temporal_query_last_summer` | Temporal | "What did I eat last summer?" |
| `test_trend_detection` | Temporal | Strengthening/fading detection |
| `test_emotional_pattern_query` | Emotional | "What makes me anxious?" |
| `test_sentiment_by_topic` | Emotional | Topics with low sentiment |
| `test_modality_distribution` | Modality | Voice vs text breakdown |
| `test_voice_more_emotional` | Modality | Compare arousal by channel |
| `test_social_context_patterns` | Social | Family vs solo topic differences |
| `test_sentiment_by_social_context` | Social | "Am I happier with family?" |
| `test_location_based_patterns` | Physical | "What do I think during commute?" |
| `test_stress_by_location` | Physical | Work vs home sentiment |
| `test_novelty_over_time` | Salience | High novelty observations |
| `test_circadian_patterns` | Temporal | Time-of-day sentiment |
| `test_cross_context_correlation` | Cross | "When stressed, what else happens?" |

---

## Architecture Boundary: P03 Write vs P01 Read

> **CRITICAL SEPARATION**
>
> This document defines **P03 Consolidation** scope — WRITING observations during truth layer INSERT/MERGE.
>
> **Reading/querying observations** is a **P01 Recall** concern and belongs in `k0/modules/recall/`.
>
> The SQL queries below are **INFORMATIONAL ONLY** — they demonstrate what becomes POSSIBLE
> once P03 writes observations. The actual query implementation lives in P01 recall adapters.

### Pipeline Responsibility (Neurological Grounding)

| Pipeline | Analogy | Direction | st_observations Role |
|----------|---------|-----------|---------------------|
| **P03 Consolidation** | Hippocampal sleep replay | WRITE | Create observation rows during truth layer writes |
| **P01 Recall** | Memory retrieval | READ | Query observations via `k0/modules/recall/` adapters |

### P01 Integration Point

**File**: `k0/modules/recall/observation_context_fetcher.py` (NEW — OUT OF SCOPE for Issue 7)

```python
# This adapter fetches observation context for P01 recall
# Pattern: Same as related_context_fetcher.py
class ObservationContextFetcher:
    """Fetches holistic observation patterns for P01 recall."""

    async def fetch_temporal_distribution(self, entity_ids: Set[str], conn) -> Dict
    async def fetch_emotional_patterns(self, entity_ids: Set[str], conn) -> Dict
    async def fetch_social_context_patterns(self, entity_ids: Set[str], conn) -> Dict
    async def fetch_location_patterns(self, entity_ids: Set[str], conn) -> Dict
    async def fetch_modality_distribution(self, entity_ids: Set[str], conn) -> Dict
```

**Integration with ContextExpander:**
```python
# In context_expander.py (future work)
observation_patterns = await self.observation_fetcher.fetch_patterns(entity_ids, conn)
expanded_context.observation_patterns = observation_patterns
```

---

## New Features Enabled (P01 Recall — INFORMATIONAL)

> **NOTE**: These SQL queries are for **illustration purposes**.
> Actual implementation belongs in `k0/modules/recall/observation_context_fetcher.py`.

### 1. Holistic Life Queries

```sql
-- "What did I eat last summer?"
SELECT DISTINCT o.record_id, s.pattern_name, o.observed_at
FROM st_observations o
JOIN st_sem s ON o.record_id = s.pattern_id
WHERE o.layer = 'st_sem'
  AND (s.pattern_name LIKE '%eat%' OR s.pattern_name LIKE '%lunch%')
  AND o.observed_at BETWEEN 1719792000000 AND 1727740800000;
```

### 2. Trend Detection

```sql
-- "Am I exercising more or less recently?"
WITH monthly_counts AS (
  SELECT
    date_trunc('month', to_timestamp(observed_at/1000)) AS month,
    count(*) AS occurrences
  FROM st_observations o
  JOIN st_sem s ON o.record_id = s.pattern_id
  WHERE s.pattern_name LIKE '%exercise%' OR s.pattern_name LIKE '%gym%'
  GROUP BY 1
)
SELECT month, occurrences,
  occurrences - LAG(occurrences) OVER (ORDER BY month) AS trend
FROM monthly_counts
ORDER BY month DESC;
```

### 3. Time-of-Day Distribution

```sql
-- "When do I usually go to the gym?"
SELECT
  extract(hour FROM to_timestamp(o.observed_at/1000)) AS hour_of_day,
  extract(dow FROM to_timestamp(o.observed_at/1000)) AS day_of_week,
  count(*) AS frequency
FROM st_observations o
JOIN st_sem s ON o.record_id = s.pattern_id
WHERE s.pattern_name LIKE '%gym%'
GROUP BY 1, 2
ORDER BY frequency DESC;
```

### 4. Observation Source Tracing (Best-Effort)

```sql
-- "Why do I think Sarah loves spicy food?"
-- NOTE: This query requires st_hipp_events to still exist (within 20-day window).
-- After tombstone, source provenance degrades gracefully — we still have the observation
-- but lose the link to original text. This is acceptable behavior.
SELECT
  o.observed_at,
  o.observation_type,
  e.text as source_text
FROM st_observations o
LEFT JOIN st_hipp_events e ON o.source_event_id = e.event_id  -- LEFT JOIN: graceful degradation
JOIN st_kg_dom k ON o.record_id = k.entity_id
WHERE k.canonical_name = 'Sarah'
  AND o.layer = 'st_kg_dom'
ORDER BY o.observed_at DESC
LIMIT 10;
```

### 5. Decay Intelligence

```sql
-- "Which patterns are fading vs strengthening?"
SELECT
  s.pattern_name,
  count(*) FILTER (WHERE o.observed_at > now_minus_30_days) AS recent_30d,
  count(*) FILTER (WHERE o.observed_at BETWEEN now_minus_60_days AND now_minus_30_days) AS prev_30d,
  CASE
    WHEN count(*) FILTER (WHERE o.observed_at > now_minus_30_days) >
         count(*) FILTER (WHERE o.observed_at BETWEEN now_minus_60_days AND now_minus_30_days)
    THEN 'STRENGTHENING'
    ELSE 'FADING'
  END AS trend
FROM st_observations o
JOIN st_sem s ON o.record_id = s.pattern_id
WHERE o.layer = 'st_sem'
GROUP BY s.pattern_id, s.pattern_name;
```

### 6. Emotional Pattern Analysis (NEW)

```sql
-- "What topics make me anxious?"
SELECT
  s.pattern_name,
  AVG(o.sentiment_score) AS avg_sentiment,
  COUNT(*) FILTER (WHERE o.dominant_emotion = 'anxiety') AS anxiety_count,
  COUNT(*) AS total_observations
FROM st_observations o
JOIN st_sem s ON o.record_id = s.pattern_id
WHERE o.layer = 'st_sem'
  AND o.sentiment_label IS NOT NULL
GROUP BY s.pattern_id, s.pattern_name
HAVING AVG(o.sentiment_score) < 0.4  -- Lower sentiment = more negative
ORDER BY anxiety_count DESC
LIMIT 10;
```

### 7. Modality Analysis (NEW)

```sql
-- "What do I say out loud vs type?"
SELECT
  o.ingress_channel,
  COUNT(*) AS observation_count,
  AVG(o.sentiment_score) AS avg_sentiment,
  AVG(o.salience_score) AS avg_importance
FROM st_observations o
WHERE o.ingress_channel IS NOT NULL
GROUP BY o.ingress_channel
ORDER BY observation_count DESC;

-- "Voice messages are more emotional than typed ones?"
SELECT
  o.ingress_channel,
  AVG(o.affect_arousal) AS avg_arousal,
  AVG(ABS(o.affect_valence)) AS avg_emotional_intensity
FROM st_observations o
WHERE o.ingress_channel IN ('voice', 'chat')
GROUP BY o.ingress_channel;
```

### 8. Social Context Patterns (NEW)

```sql
-- "What topics come up with family vs alone?"
SELECT
  s.pattern_name,
  o.social_context,
  COUNT(*) AS frequency
FROM st_observations o
JOIN st_sem s ON o.record_id = s.pattern_id
WHERE o.social_context IN ('family', 'solo')
GROUP BY s.pattern_name, o.social_context
ORDER BY frequency DESC
LIMIT 20;

-- "Am I more positive when with family?"
SELECT
  o.social_context,
  AVG(o.sentiment_score) AS avg_sentiment,
  AVG(o.affect_valence) AS avg_valence
FROM st_observations o
WHERE o.social_context IS NOT NULL
GROUP BY o.social_context
ORDER BY avg_sentiment DESC;
```

### 9. Location-Based Patterns (NEW)

```sql
-- "What do I think about during commute?"
SELECT
  s.pattern_name,
  COUNT(*) AS frequency
FROM st_observations o
JOIN st_sem s ON o.record_id = s.pattern_id
WHERE o.location_type = 'transit'
GROUP BY s.pattern_name
ORDER BY frequency DESC
LIMIT 10;

-- "Am I more stressed at work or home?"
SELECT
  o.location_type,
  AVG(o.sentiment_score) AS avg_sentiment,
  AVG(o.affect_arousal) AS avg_arousal
FROM st_observations o
WHERE o.location_type IN ('home', 'work')
GROUP BY o.location_type;
```

### 10. Salience & Novelty Analysis (NEW)

```sql
-- "What new things captured my attention this year?"
SELECT
  s.pattern_name,
  o.observed_at,
  o.novelty_score,
  o.salience_score
FROM st_observations o
JOIN st_sem s ON o.record_id = s.pattern_id
WHERE o.novelty_score > 0.8
  AND o.salience_band = 'HIGH'
  AND o.observed_at > (extract(epoch FROM now()) * 1000) - 31536000000  -- Last year
ORDER BY o.novelty_score DESC
LIMIT 20;

-- "What patterns became less novel over time?" (Habituation)
SELECT
  s.pattern_name,
  MIN(o.novelty_score) AS min_novelty,
  MAX(o.novelty_score) AS max_novelty,
  MAX(o.novelty_score) - MIN(o.novelty_score) AS novelty_decay
FROM st_observations o
JOIN st_sem s ON o.record_id = s.pattern_id
WHERE o.novelty_score IS NOT NULL
GROUP BY s.pattern_name
HAVING COUNT(*) > 5
ORDER BY novelty_decay DESC
LIMIT 10;
```

### 11. Circadian Pattern Analysis (NEW)

```sql
-- "When am I most productive?"
SELECT
  o.time_of_day_bucket,
  o.circadian_slot,
  COUNT(*) AS activity_count,
  AVG(o.salience_score) AS avg_importance
FROM st_observations o
WHERE o.time_of_day_bucket IS NOT NULL
GROUP BY o.time_of_day_bucket, o.circadian_slot
ORDER BY avg_importance DESC;

-- "Am I happier in the morning or evening?"
SELECT
  o.time_of_day_bucket,
  AVG(o.sentiment_score) AS avg_sentiment,
  AVG(o.affect_valence) AS avg_valence
FROM st_observations o
WHERE o.time_of_day_bucket IS NOT NULL
GROUP BY o.time_of_day_bucket
ORDER BY o.time_of_day_bucket;
```

### 12. Cross-Context Correlation (NEW)

```sql
-- "When I'm stressed at work, what else happens?"
SELECT
  s.pattern_name,
  COUNT(*) AS co_occurrence
FROM st_observations stressed
JOIN st_observations o ON
  o.observed_at BETWEEN stressed.observed_at - 3600000 AND stressed.observed_at + 3600000
  AND o.tenant_id = stressed.tenant_id
  AND o.observation_id != stressed.observation_id
JOIN st_sem s ON o.record_id = s.pattern_id
WHERE stressed.location_type = 'work'
  AND stressed.sentiment_score < 0.3
GROUP BY s.pattern_name
ORDER BY co_occurrence DESC
LIMIT 10;
```

---

## Appendix: Investigation Evidence

### R0-R8 Temporal Signal Flow

| Phase | File | Receives Timestamps? | Preserves on Merge? | Issue |
|-------|------|---------------------|---------------------|-------|
| R0 | r0_batch_selector.py | Yes (from st_hipp_events) | N/A (loads only) | None |
| R1 | r1_importance_scorer.py | Has access | N/A (scoring only) | Minor: not used for importance |
| R2 | r2_episodic_integrator.py | Uses for bounds | Only MIN/MAX | Loses individual timestamps |
| R3 | r3_dedup_decay.py | Uses for decay | Only last_observed | Can't analyze distribution |
| R4 | r4_kg_consolidator.py | Uses for Granger | Only observation_count | Loses on entity merge |
| R5 | r5_dream_explorer.py | Receives from R2/R4 | N/A (exploration) | Inherits limitations |
| R6 | r6_staging.py | Passes through | N/A (staging) | None |
| R7 | r7_truth_writer.py | Receives from R6 | **Only increments count** | **ROOT CAUSE** |
| R8 | r8_event_emitter.py | Emits events | N/A (emission) | None |

### Current Schema (Missing Columns)

| Table | Has | Missing |
|-------|-----|---------|
| st_epi | observation_count, start_time_utc, end_time_utc | individual timestamps |
| st_sem | observation_count, first_observed_at, last_observed_at | individual timestamps |
| st_kg_dom | observation_count, last_observed_at | individual timestamps |
| st_social | observation_count, first/last_interaction_at | individual timestamps |
| st_prospective | target_date | anchor_time_utc, original_temporal_expr |

### Existing Pattern Reference

**st_anchor_observations** (migration 0039) — Model for new st_observations:
- observation_id TEXT PRIMARY KEY
- entity_id TEXT NOT NULL
- attribute TEXT NOT NULL
- tenant_id TEXT NOT NULL
- observed_at BIGINT NOT NULL
- event_id TEXT
- supports_anchor BOOLEAN
- observation_weight FLOAT

---

## Implementation Order

```
Issue 7.1 (Schema)
    |
    v
Issue 7.2 (TemporalAnchor) -----> Issue 7.3 (TemporalParser Fix)
    |
    v
Issue 7.4 (ObservationRecorder)
    |
    +-----> Issue 7.5 (Truth Writer Integration)
    |
    +-----> Issue 7.7 (Prospective Enhancement)

Issue 7.6 (Pipeline Data Flow) can proceed in parallel after Issue 7.2
```

**Recommended Order**: 7.1 -> 7.2 -> 7.3 -> 7.4 -> 7.5 -> 7.6 -> 7.7

---

## Blockers/Dependencies

**All dependencies resolved.** This is a self-contained schema + code change that can proceed independently.

**Key Architecture Decisions:**
- st_observations links to TRUTH LAYERS (permanent), NOT st_hipp_events (20-day tombstone)
- source_event_id is OPTIONAL soft reference — degrades gracefully after 20 days
- observed_at is self-contained — no dependency on external timestamps
- All temporal queries work via `observed_at` + `record_id` → truth layer lookup
