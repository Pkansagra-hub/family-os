# R4 KG Consolidator Enhancement — Epic Implementation Plan

**Date**: 2025-01-24
**Updated**: 2025-01-24
**Status**: IN PROGRESS
**Priority**: HIGH
**Pipeline Scope**: P03 Consolidation (R4 Phase)
**Branch**: `postgre-sql-migration`

---

## Implementation Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| st_observations table (0067) | ✅ DONE | 30+ columns, 13 indexes |
| st_kg_edges layer in observations (0068) | ✅ DONE | Added to VALID_LAYERS |
| ObservationContext dataclass | ✅ DONE | All 25+ fields, factory methods |
| ObservationRecorder service | ✅ DONE | record(), record_batch(), record_for_insert/merge |
| P03EventState context fields | ✅ DONE | All temporal, emotional, social fields |
| EpisodeCluster.member_contexts | ✅ DONE | Field exists in phase_outputs.py |
| KGLayerWriter observation recording | ✅ DONE | Records to st_observations |
| R0 SELECT context fields | ✅ DONE | Lines 525-574 load all fields |
| R2 member_contexts population | ✅ DONE | Lines 1152-1163 populate contexts |
| R4 entity-to-context mapping | 🔲 TODO | R4 does not yet use ObservationContext |
| st_kg_edges.source_algorithm column | 🔲 TODO | Need migration 0069 |
| st_kg_edges evidence columns | 🔲 TODO | Need migration 0070 |
| KGEdge.source_algorithm field | 🔲 TODO | Need to add to dataclass |
| EdgeEnrichmentConfig | 🔲 TODO | New file needed |
| 6 Enrichment Algorithms | 🔲 TODO | Main GAP-007 work |
| R4 Integration | 🔲 TODO | Wire enrichers into R4 |
| Algorithm math & thresholds | 🔲 TODO | GAP-007 tuning spec |
| Wiring conformance checklist | 🔲 TODO | GAP-007 execution wiring |
| TemporalParser anchor fix | 🔲 TODO | From temporal_fix.md |
| Prospective anchor fields | 🔲 TODO | From temporal_fix.md |
| Episode member_timestamps | 🔲 TODO | From temporal_fix.md |

---

## Executive Summary

This epic enhances the R4 KG Consolidator phase with:

1. **GAP-007**: Six new edge enrichment algorithms
2. **Holistic Context Flow**: Preserve and use full observation context during KG operations
3. **Schema Evolution**: New columns and tables to support enriched edges

**Key Discovery**: Much of the foundation (Milestone 1 and 2) is ALREADY IMPLEMENTED. The remaining work focuses on:

- Schema changes to st_kg_edges (source_algorithm, evidence columns)
- The 6 edge enrichment algorithms (Milestone 3)
- R4 integration and output pipeline (Milestone 4)

---

## Milestone Overview

```
MILESTONE 1: Foundation (Schema + Data Structures)
├── Epic 1.1: Schema Migrations
└── Epic 1.2: Core Data Structures

MILESTONE 2: Context Pipeline (R0 → R4 Flow)
├── Epic 2.1: R0 Context Loading
├── Epic 2.2: Pipeline Context Flow
└── Epic 2.3: R4 Context Reception

MILESTONE 3: Edge Enrichment Algorithms (GAP-007)
├── Epic 3.1: Semantic Similarity Edges
├── Epic 3.2: Temporal Proximity Edges
├── Epic 3.3: Contextual Edges
├── Epic 3.4: Transitive Closure Edges
├── Epic 3.5: Bayesian Causal Edges
└── Epic 3.6: Edge Weight Normalization

MILESTONE 4: Output Pipeline (R4 → R7 Flow)
├── Epic 4.1: R4 Output Enhancement
├── Epic 4.2: R6 Staging Integration
└── Epic 4.3: R7 Truth Writer Integration

MILESTONE 5: Testing & Validation
├── Epic 5.1: Unit Tests
├── Epic 5.2: Integration Tests
└── Epic 5.3: Performance Validation
```

---

# MILESTONE 1: Foundation (Schema + Data Structures)

## Epic 1.1: Schema Migrations

### Issue 1.1.1: Add source_algorithm Column to st_kg_edges

**Status**: 🔲 TODO
**Complexity**: LOW
**Dependencies**: None
**Files**: `k0/db/alembic/versions/0069_st_kg_edges_source_algorithm.py`
**Note**: Next available migration number is 0069 (0068 already exists for st_kg_edges layer in observations)

#### Objective

Add `source_algorithm` column to track which algorithm produced each edge.

#### Schema Change

```sql
ALTER TABLE st_kg_edges
ADD COLUMN source_algorithm TEXT;

-- Backfill existing edges
UPDATE st_kg_edges
SET source_algorithm = 'co_occurrence'
WHERE source_algorithm IS NULL;

-- Add index for algorithm-based queries
CREATE INDEX idx_kg_edges_source_algorithm
ON st_kg_edges (tenant_id, source_algorithm);
```

#### Valid Values

```python
SOURCE_ALGORITHMS = [
    'co_occurrence',      # Existing Hebbian reinforcement
    'granger_causal',     # Existing Granger causality
    'semantic_similarity', # NEW: Embedding similarity
    'temporal_proximity',  # NEW: Time window co-occurrence
    'contextual',         # NEW: Shared context features
    'transitive_closure', # NEW: Graph inference
    'bayesian_causal',    # NEW: Bayesian causal inference
    'weight_normalization', # NEW: Normalization adjustments
    'manual',             # User-provided edges
]
```

#### Acceptance Criteria

- [ ] Migration runs successfully (upgrade)
- [ ] Rollback works (downgrade)
- [ ] Existing edges backfilled with `co_occurrence`
- [ ] Index created for algorithm queries
- [ ] No data loss

---

### Issue 1.1.2: Add Evidence Columns to st_kg_edges

**Status**: 🔲 TODO
**Complexity**: LOW
**Dependencies**: Issue 1.1.1
**Files**: `k0/db/alembic/versions/0070_st_kg_edges_evidence.py`

#### Objective

Add columns to track evidence provenance for each edge.

#### Schema Change

```sql
ALTER TABLE st_kg_edges
ADD COLUMN evidence_event_ids TEXT[],      -- Array of source event IDs
ADD COLUMN evidence_episode_ids TEXT[],    -- Array of source episode IDs
ADD COLUMN algorithm_params_json TEXT,     -- Algorithm-specific parameters used
ADD COLUMN inference_chain_json TEXT;      -- For transitive closure: path taken

-- Partial index for edges with event evidence
CREATE INDEX idx_kg_edges_has_evidence
ON st_kg_edges (tenant_id, created_at DESC)
WHERE evidence_event_ids IS NOT NULL;
```

#### Acceptance Criteria

- [ ] Migration runs successfully
- [ ] Rollback works
- [ ] Existing edges unaffected (NULL values)
- [ ] Array operations work correctly

---

### Issue 1.1.4: Evidence Linkage Rules & Relation Type Registry

**Status**: 🔲 TODO
**Complexity**: LOW
**Dependencies**: Issue 1.1.2
**Files**: `k0/pipelines/p03/phase_outputs.py`, `k0/modules/consolidation/truth_writer/layers/kg.py`

#### Objective

Define and enforce the evidence linkage rules and relation types used by GAP-007 algorithms.

#### Scope

- Decide whether each algorithm uses `evidence_event_ids`, `evidence_episode_ids`, or both.
- Define canonical `relation_type` values per algorithm.
- Confirm how evidence arrays are merged on UPDATE (append, dedupe, cap).

#### Acceptance Criteria

- [ ] Evidence linkage rules documented per algorithm
- [ ] Relation types enumerated and consistent across R4, R6, and R7
- [ ] Update semantics defined (append + dedupe)

---

### Issue 1.1.3: Create st_observations Table

**Status**: ✅ DONE
**Complexity**: MEDIUM
**Dependencies**: None
**Files**: `k0/db/alembic/versions/0067_st_observations.py` (ALREADY EXISTS)

#### Objective

Create the holistic observation log table (from temporal_fix.md Issue 7.1).

#### IMPLEMENTATION STATUS: COMPLETE

The st_observations table was created in migration 0067 with:

- 30+ columns covering all context categories
- 13 indexes for efficient querying
- CHECK constraint for valid layers
- Migration 0068 added 'st_kg_edges' to the valid layers

#### Schema

```sql
CREATE TABLE st_observations (
    -- Identity
    observation_id TEXT PRIMARY KEY,
    layer TEXT NOT NULL,
    record_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    space_id TEXT NOT NULL,

    -- Temporal Context
    observed_at BIGINT NOT NULL,
    anchor_time_utc BIGINT,
    original_temporal_expr TEXT,
    time_of_day_bucket TEXT,
    circadian_slot TEXT,
    is_weekend BOOLEAN,

    -- Emotional Context
    sentiment_score FLOAT,
    sentiment_label TEXT,
    affect_valence FLOAT,
    affect_arousal FLOAT,
    dominant_emotion TEXT,

    -- Salience Context
    salience_score FLOAT,
    salience_band TEXT,
    novelty_score FLOAT,

    -- Modality Context
    ingress_channel TEXT,
    ingress_source TEXT,
    device_kind TEXT,

    -- Physical Context
    location_name TEXT,
    location_type TEXT,
    geohash_6 TEXT,

    -- Social Context
    social_context TEXT,
    social_intimacy TEXT,
    is_solo_event BOOLEAN,
    num_participants INTEGER,

    -- Classification
    observation_type TEXT NOT NULL DEFAULT 'REINFORCEMENT',
    confidence FLOAT DEFAULT 1.0,

    -- Provenance
    source_event_id TEXT,
    consolidation_cycle_id TEXT,

    -- Lifecycle
    created_at BIGINT NOT NULL,

    CHECK (layer IN ('st_epi', 'st_sem', 'st_kg_dom', 'st_social', 'st_prospective', 'st_kg_edges'))
);

-- Indexes
CREATE INDEX idx_obs_record_time ON st_observations (layer, record_id, observed_at DESC);
CREATE INDEX idx_obs_tenant_time ON st_observations (tenant_id, observed_at DESC);
CREATE INDEX idx_obs_sentiment ON st_observations (tenant_id, sentiment_label, observed_at DESC)
    WHERE sentiment_label IS NOT NULL;
CREATE INDEX idx_obs_salience ON st_observations (tenant_id, salience_band, observed_at DESC)
    WHERE salience_band = 'HIGH';
CREATE INDEX idx_obs_channel ON st_observations (tenant_id, ingress_channel, observed_at DESC)
    WHERE ingress_channel IS NOT NULL;
CREATE INDEX idx_obs_social ON st_observations (tenant_id, social_context, observed_at DESC)
    WHERE social_context IS NOT NULL;
CREATE INDEX idx_obs_location ON st_observations (tenant_id, location_type, observed_at DESC)
    WHERE location_type IS NOT NULL;
```

#### Acceptance Criteria

- [x] Table created with all 30+ columns
- [x] All 13 indexes created (more than originally planned)
- [x] CHECK constraint enforced
- [x] Rollback drops table cleanly

---

## Epic 1.2: Core Data Structures

### Issue 1.2.1: Create ObservationContext Dataclass

**Status**: ✅ DONE
**Complexity**: MEDIUM
**Dependencies**: None
**Files**: `k0/modules/consolidation/algorithms/observation_context.py` (ALREADY EXISTS)

#### Objective

Create dataclass to carry full holistic context through the pipeline.

#### IMPLEMENTATION STATUS: COMPLETE

The ObservationContext dataclass exists with:

- All 25+ fields (temporal, emotional, salience, modality, physical, social)
- `from_event()` factory method for P03EventState
- `from_timestamp()` factory method for minimal context
- `from_episode_cluster()` factory method for cluster aggregation
- `to_dict()`, `to_db_row()`, `with_type()`, `with_provenance()` helpers

#### Implementation

```python
from dataclasses import dataclass, field, asdict
from typing import Optional, List
import json

@dataclass
class ObservationContext:
    """Full context snapshot for a memory observation."""

    # === Temporal (REQUIRED) ===
    observed_at: int  # Unix ms, REQUIRED
    anchor_time_utc: Optional[int] = None
    original_temporal_expr: Optional[str] = None
    time_of_day_bucket: Optional[str] = None  # MORNING, AFTERNOON, EVENING, NIGHT
    circadian_slot: Optional[str] = None  # WAKE, ACTIVE, WIND_DOWN, SLEEP
    is_weekend: Optional[bool] = None

    # === Emotional ===
    sentiment_score: Optional[float] = None  # 0.0 to 1.0
    sentiment_label: Optional[str] = None  # negative, neutral, positive
    affect_valence: Optional[float] = None  # -1.0 to +1.0
    affect_arousal: Optional[float] = None  # 0.0 to 1.0
    dominant_emotion: Optional[str] = None

    # === Salience ===
    salience_score: Optional[float] = None
    salience_band: Optional[str] = None  # HIGH, MED, LOW
    novelty_score: Optional[float] = None

    # === Modality ===
    ingress_channel: Optional[str] = None  # voice, chat, api
    ingress_source: Optional[str] = None
    device_kind: Optional[str] = None  # phone, desktop, speaker

    # === Physical ===
    location_name: Optional[str] = None
    location_type: Optional[str] = None  # home, work, transit
    geohash_6: Optional[str] = None

    # === Social ===
    social_context: Optional[str] = None  # solo, family, work
    social_intimacy: Optional[str] = None
    is_solo_event: Optional[bool] = None
    num_participants: Optional[int] = None

    # === Classification ===
    observation_type: str = "REINFORCEMENT"
    confidence: float = 1.0

    # === Provenance ===
    source_event_id: Optional[str] = None
    consolidation_cycle_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for SQL insertion."""
        return asdict(self)

    @classmethod
    def from_event(cls, event: "P03EventState") -> "ObservationContext":
        """Create context from P03 event state."""
        return cls(
            observed_at=event.timestamp,
            time_of_day_bucket=getattr(event, 'time_of_day_bucket', None),
            circadian_slot=getattr(event, 'circadian_slot', None),
            is_weekend=getattr(event, 'is_weekend', None),
            sentiment_score=getattr(event, 'sentiment_score', None),
            sentiment_label=getattr(event, 'sentiment_label', None),
            affect_valence=getattr(event, 'affect_valence', None),
            affect_arousal=getattr(event, 'affect_arousal', None),
            dominant_emotion=cls._extract_first_emotion(
                getattr(event, 'dominant_emotions_json', None)
            ),
            salience_score=getattr(event, 'salience_score', None),
            salience_band=getattr(event, 'salience_band', None),
            novelty_score=getattr(event, 'novelty_score', None),
            ingress_channel=getattr(event, 'ingress_channel', None),
            ingress_source=getattr(event, 'ingress_source', None),
            device_kind=getattr(event, 'device_kind', None),
            location_name=getattr(event, 'location_name', None),
            location_type=getattr(event, 'location_type', None),
            geohash_6=getattr(event, 'geohash_6', None),
            social_context=getattr(event, 'social_context', None),
            social_intimacy=getattr(event, 'social_intimacy', None),
            is_solo_event=getattr(event, 'is_solo_event', None),
            num_participants=getattr(event, 'num_participants', None),
            source_event_id=event.event_id,
        )

    @classmethod
    def from_timestamp(cls, timestamp_ms: int) -> "ObservationContext":
        """Create minimal context from raw timestamp."""
        return cls(observed_at=timestamp_ms)

    @staticmethod
    def _extract_first_emotion(emotions_json: Optional[str]) -> Optional[str]:
        if not emotions_json:
            return None
        try:
            emotions = json.loads(emotions_json)
            return emotions[0] if emotions else None
        except (json.JSONDecodeError, IndexError):
            return None
```

#### Acceptance Criteria

- [x] Dataclass created with 25+ fields
- [x] `from_event()` extracts all available context
- [x] `from_timestamp()` creates minimal context
- [x] `to_dict()` serializes for SQL
- [x] `from_episode_cluster()` for cluster aggregation (bonus)
- [x] `to_db_row()`, `with_type()`, `with_provenance()` helpers (bonus)
- [ ] Unit tests pass (verify test coverage)

---

### Issue 1.2.2: Create KGEdge and KGEdgeUpdate Dataclasses

**Status**: 🔶 PARTIAL - Needs `source_algorithm` field
**Complexity**: LOW
**Dependencies**: Issue 1.2.1
**Files**: `k0/pipelines/p03/phase_outputs.py`

#### IMPLEMENTATION STATUS

- `KGEdge` exists but needs `source_algorithm` field added
- `KGEdgeUpdate` exists with `observation_count_increment` field
- Both need enhancement for evidence tracking fields

#### Objective

Enhance/create dataclasses for R4 edge outputs.

#### Implementation

```python
@dataclass
class KGEdge:
    """New edge to be created in st_kg_edges."""
    edge_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str  # RELATED_TO, CAUSES, SIMILAR_TO, etc.
    edge_weight: float
    confidence_score: float
    source_algorithm: str  # NEW: Required

    # Evidence
    evidence_event_ids: List[str] = field(default_factory=list)
    evidence_episode_ids: List[str] = field(default_factory=list)

    # Algorithm-specific
    properties_json: Optional[str] = None
    algorithm_params_json: Optional[str] = None
    inference_chain_json: Optional[str] = None  # For transitive closure

    # Context
    observation_context: Optional[ObservationContext] = None


@dataclass
class KGEdgeUpdate:
    """Update to an existing edge in st_kg_edges."""
    edge_id: str
    weight_delta: float = 0.0
    confidence_delta: float = 0.0
    new_weight: Optional[float] = None  # If set, replaces weight
    new_confidence: Optional[float] = None  # If set, replaces confidence
    source_algorithm: str = ""

    # Additional evidence
    new_evidence_event_ids: List[str] = field(default_factory=list)
    new_evidence_episode_ids: List[str] = field(default_factory=list)

    # Context
    observation_context: Optional[ObservationContext] = None
```

#### Acceptance Criteria

- [ ] KGEdge has all required fields including `source_algorithm`
- [ ] KGEdgeUpdate supports both delta and absolute updates
- [ ] Both carry `observation_context`
- [ ] JSON serialization works

---

### Issue 1.2.3: Create EdgeEnrichmentConfig Dataclass

**Status**: 🔲 TODO
**Complexity**: LOW
**Dependencies**: None
**Files**: `k0/pipelines/p03/phases/r4_config.py`

#### Objective

Centralized configuration for all edge enrichment algorithms.

#### Implementation

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class SemanticSimilarityConfig:
    """Config for semantic similarity edge algorithm."""
    enabled: bool = True
    k_neighbors: int = 10
    similarity_threshold: float = 0.75
    max_edges_per_entity: int = 5
    relation_type: str = "SIMILAR_TO"


@dataclass
class TemporalProximityConfig:
    """Config for temporal proximity edge algorithm."""
    enabled: bool = True
    window_ms: int = 300_000  # 5 minutes
    tau_ms: int = 60_000  # 1 minute decay constant
    min_weight: float = 0.1
    max_edges_per_entity: int = 10
    relation_type: str = "TEMPORALLY_ASSOCIATED"


@dataclass
class ContextualEdgeConfig:
    """Config for contextual edge algorithm."""
    enabled: bool = True
    similarity_threshold: float = 0.5
    max_edges_per_entity: int = 5
    context_weights: dict = None  # Feature importance weights
    relation_type: str = "CONTEXTUALLY_RELATED"

    def __post_init__(self):
        if self.context_weights is None:
            self.context_weights = {
                'location_type': 1.0,
                'social_context': 1.0,
                'time_of_day_bucket': 0.5,
                'sentiment_label': 0.5,
            }


@dataclass
class TransitiveClosureConfig:
    """Config for transitive closure edge algorithm."""
    enabled: bool = True
    max_hops: int = 2
    attenuation_factor: float = 0.7
    min_confidence: float = 0.3
    max_edges_per_entity: int = 3
    relation_type: str = "INFERRED_RELATED"


@dataclass
class BayesianCausalConfig:
    """Config for Bayesian causal inference algorithm."""
    enabled: bool = True
    prior_strength: float = 0.1
    min_evidence_count: int = 3
    posterior_threshold: float = 0.6
    relation_type: str = "CAUSES"


@dataclass
class WeightNormalizationConfig:
    """Config for edge weight normalization."""
    enabled: bool = True
    strategy: str = "softmax"  # softmax, sum_to_one, cap
    max_weight: float = 1.0
    min_weight: float = 0.01


@dataclass
class EdgeEnrichmentConfig:
    """Master config for all R4 edge enrichment algorithms."""
    semantic_similarity: SemanticSimilarityConfig = None
    temporal_proximity: TemporalProximityConfig = None
    contextual: ContextualEdgeConfig = None
    transitive_closure: TransitiveClosureConfig = None
    bayesian_causal: BayesianCausalConfig = None
    weight_normalization: WeightNormalizationConfig = None

    # Global settings
    max_total_new_edges_per_cycle: int = 100
    max_total_updates_per_cycle: int = 500

    def __post_init__(self):
        self.semantic_similarity = self.semantic_similarity or SemanticSimilarityConfig()
        self.temporal_proximity = self.temporal_proximity or TemporalProximityConfig()
        self.contextual = self.contextual or ContextualEdgeConfig()
        self.transitive_closure = self.transitive_closure or TransitiveClosureConfig()
        self.bayesian_causal = self.bayesian_causal or BayesianCausalConfig()
        self.weight_normalization = self.weight_normalization or WeightNormalizationConfig()
```

#### Acceptance Criteria

- [ ] All 6 algorithm configs defined
- [ ] Sensible defaults for all thresholds
- [ ] Master config aggregates all
- [ ] Can be loaded from YAML/env

---

# MILESTONE 2: Context Pipeline (R0 → R4 Flow)

## Epic 2.1: R0 Context Loading

### Issue 2.1.1: Expand R0 SELECT Query for Full Context

**Status**: ✅ DONE
**Complexity**: MEDIUM
**Dependencies**: Issue 1.2.1
**Files**: `k0/pipelines/p03/phases/r0_batch_selector.py` (lines 525-574)

#### IMPLEMENTATION STATUS: COMPLETE

The R0 SELECT query (lines 525-574) already loads ALL context fields:

- **Temporal**: `time_of_day_bucket`, `circadian_slot`, `is_weekend`, `day_of_week`
- **Modality**: `ingress_channel`, `ingress_source`, `device_kind`
- **Social**: `social_context`, `social_intimacy`, `num_participants`, `participants_json`
- **Physical**: `location_name`, `location_type`
- **Emotional**: `sentiment_score`, `affect_valence`, `affect_arousal`
- **Salience**: `salience_score`

The `_row_to_event_state()` method (lines 626-690) maps all these fields to P03EventState.

#### Objective

Load all 25+ context fields from st_hipp_events during batch selection.

#### Current State

```python
# Line ~639 in r0_batch_selector.py
SELECT event_id, event_time_utc as timestamp, ...
```

#### Required Change

```python
BATCH_SELECT_QUERY = """
SELECT
    event_id,
    event_time_utc as timestamp,

    -- Temporal context
    time_of_day_bucket,
    circadian_slot,
    is_weekend,

    -- Emotional context
    sentiment_score,
    sentiment_label,
    affect_valence,
    affect_arousal,
    dominant_emotions_json,

    -- Salience context
    salience_score,
    salience_band,
    novelty_score,

    -- Modality context
    ingress_channel,
    ingress_source,
    device_kind,

    -- Physical context
    location_name,
    location_type,
    geohash_6,

    -- Social context
    social_context,
    social_intimacy,
    is_solo_event,
    (SELECT COUNT(*) FROM json_each(participants_json)) as num_participants,

    -- Existing fields
    text,
    embedding_id,
    entities_json,
    ...

FROM st_hipp_events
WHERE tenant_id = :tenant_id
  AND space_id = :space_id
  AND consolidation_status = 'PENDING'
  AND created_at <= :cutoff_time
ORDER BY created_at ASC
LIMIT :batch_size
"""
```

#### Acceptance Criteria

- [x] Query loads all 25+ context fields
- [x] NULL handling for missing fields (uses `or ""` and `or 0.0` defaults)
- [x] Existing batch selection logic unchanged
- [ ] Performance benchmark documented

---

### Issue 2.1.2: Enhance P03EventState with Context Fields

**Status**: ✅ DONE
**Complexity**: MEDIUM
**Dependencies**: Issue 2.1.1
**Files**: `k0/pipelines/p03/event_state.py` (ALREADY ENHANCED)

#### IMPLEMENTATION STATUS: COMPLETE

P03EventState already includes:

- Temporal: `time_of_day_bucket`, `circadian_slot`, `is_weekend`, `day_of_week`
- Modality: `ingress_channel`, `ingress_source`, `device_kind`
- Social: `social_context`, `social_intimacy`, `is_solo_event`, `num_participants`
- UltraBERT: `ultrabert_embedding_id`, `ultrabert_embedding_seq_offset`, `ultrabert_entities_json`

#### Objective

Add all context fields to P03EventState dataclass.

#### Implementation

```python
@dataclass
class P03EventState:
    """State for a single event in P03 pipeline."""

    # === Identity ===
    event_id: str
    tenant_id: str
    space_id: str

    # === Content ===
    text: str = ""
    embedding_id: Optional[str] = None
    entities_json: Optional[str] = None

    # === Timing ===
    timestamp: int = 0
    created_at: int = 0

    # === NEW: Temporal Context ===
    time_of_day_bucket: Optional[str] = None
    circadian_slot: Optional[str] = None
    is_weekend: Optional[bool] = None

    # === NEW: Emotional Context ===
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    affect_valence: Optional[float] = None
    affect_arousal: Optional[float] = None
    dominant_emotions_json: Optional[str] = None

    # === NEW: Salience Context ===
    salience_score: Optional[float] = None
    salience_band: Optional[str] = None
    novelty_score: Optional[float] = None

    # === NEW: Modality Context ===
    ingress_channel: Optional[str] = None
    ingress_source: Optional[str] = None
    device_kind: Optional[str] = None

    # === NEW: Physical Context ===
    location_name: Optional[str] = None
    location_type: Optional[str] = None
    geohash_6: Optional[str] = None

    # === NEW: Social Context ===
    social_context: Optional[str] = None
    social_intimacy: Optional[str] = None
    is_solo_event: Optional[bool] = None
    num_participants: Optional[int] = None

    # === Processing State ===
    consolidation_status: str = "PENDING"

    def to_observation_context(self) -> "ObservationContext":
        """Convert to ObservationContext for downstream use."""
        from k0.modules.consolidation.algorithms.observation_context import ObservationContext
        return ObservationContext.from_event(self)

    @classmethod
    def from_row(cls, row: dict) -> "P03EventState":
        """Create from database row."""
        return cls(
            event_id=row['event_id'],
            tenant_id=row['tenant_id'],
            space_id=row['space_id'],
            text=row.get('text', ''),
            timestamp=row.get('timestamp', 0),
            # ... all other fields ...
            time_of_day_bucket=row.get('time_of_day_bucket'),
            sentiment_score=row.get('sentiment_score'),
            # etc.
        )
```

#### Acceptance Criteria

- [x] All 25+ context fields added
- [x] Backward compatible (new fields Optional with None default)
- [ ] `to_observation_context()` method works - VERIFY if exists
- [ ] `from_row()` factory handles all fields - VERIFY

---

## Epic 2.2: Pipeline Context Flow

### Issue 2.2.1: Enhance EpisodeCluster with Member Contexts

**Status**: ✅ DONE
**Complexity**: MEDIUM
**Dependencies**: Issue 2.1.2
**Files**: `k0/pipelines/p03/phase_outputs.py` (ALREADY ENHANCED)

#### IMPLEMENTATION STATUS: COMPLETE

EpisodeCluster already has:

- `member_contexts: List[ObservationContext] = field(default_factory=list)`
- Field exists and is ready for use

#### Objective

Carry full context for each member event through episode clustering.

#### Implementation

```python
@dataclass
class EpisodeCluster:
    """Cluster of related events forming an episode."""

    cluster_id: str
    member_event_ids: List[str] = field(default_factory=list)

    # NEW: Full context for each member
    member_contexts: List[ObservationContext] = field(default_factory=list)

    # Temporal bounds
    temporal_start: int = 0
    temporal_end: int = 0

    # Aggregated features
    centroid_embedding_id: Optional[str] = None
    dominant_entities: List[str] = field(default_factory=list)

    # NEW: Aggregated context (for the cluster as a whole)
    aggregated_sentiment: Optional[float] = None
    aggregated_salience: Optional[float] = None
    dominant_location: Optional[str] = None
    dominant_social_context: Optional[str] = None

    def get_representative_context(self) -> Optional[ObservationContext]:
        """Get most representative context (highest salience or first)."""
        if not self.member_contexts:
            return None
        # Return highest salience context
        return max(
            self.member_contexts,
            key=lambda c: c.salience_score or 0.0
        )
```

#### Acceptance Criteria

- [x] `member_contexts` field added
- [ ] Aggregated context fields added - VERIFY
- [ ] `get_representative_context()` works - VERIFY if exists
- [ ] Serialization handles list of contexts - VERIFY

---

### Issue 2.2.2: Update R2 to Build Member Contexts

**Status**: ✅ DONE
**Complexity**: MEDIUM
**Dependencies**: Issue 2.2.1
**Files**: `k0/pipelines/p03/phases/r2_episodic_integrator.py` (lines 1152-1163)

#### IMPLEMENTATION STATUS: COMPLETE

The `_build_episode_cluster()` method (lines 1045-1177) populates `member_contexts`:

```python
# Issue 7.6: Build ObservationContext for each member event
from k0.modules.consolidation.algorithms.observation_context import ObservationContext

member_contexts = []
for e in cluster_events:
    ctx = ObservationContext.from_event(e.event)
    member_contexts.append(ctx)
```

Additionally, `_merge_episodes()` (line 931) aggregates member_contexts when canonicalizing episodes.

#### Objective

Populate `member_contexts` when creating EpisodeClusters.

#### Implementation

```python
def _create_episode_cluster(
    self,
    cluster_id: str,
    events: List[P03EventState],
) -> EpisodeCluster:
    """Create an EpisodeCluster from grouped events."""

    # Build member contexts
    member_contexts = [event.to_observation_context() for event in events]

    # Aggregate sentiment
    sentiments = [c.sentiment_score for c in member_contexts if c.sentiment_score is not None]
    aggregated_sentiment = sum(sentiments) / len(sentiments) if sentiments else None

    # Aggregate salience
    saliences = [c.salience_score for c in member_contexts if c.salience_score is not None]
    aggregated_salience = max(saliences) if saliences else None  # Max salience

    # Dominant location (mode)
    locations = [c.location_type for c in member_contexts if c.location_type]
    dominant_location = max(set(locations), key=locations.count) if locations else None

    # Dominant social context (mode)
    social_contexts = [c.social_context for c in member_contexts if c.social_context]
    dominant_social = max(set(social_contexts), key=social_contexts.count) if social_contexts else None

    return EpisodeCluster(
        cluster_id=cluster_id,
        member_event_ids=[e.event_id for e in events],
        member_contexts=member_contexts,
        temporal_start=min(e.timestamp for e in events),
        temporal_end=max(e.timestamp for e in events),
        aggregated_sentiment=aggregated_sentiment,
        aggregated_salience=aggregated_salience,
        dominant_location=dominant_location,
        dominant_social_context=dominant_social,
    )
```

#### Acceptance Criteria

- [x] `member_contexts` populated from events
- [x] Aggregations computed correctly (in `_merge_episodes()`)
- [x] No change to existing clustering logic
- [x] Context flows to R4 via `envelope.phases.r2_clusters`

---

## Epic 2.3: R4 Context Reception

### Issue 2.3.1: R4 Receives Full Context from Envelope

**Status**: 🔲 TODO - R4 does not yet use ObservationContext
**Complexity**: LOW
**Dependencies**: Issue 2.2.2
**Files**: `k0/pipelines/p03/phases/r4_kg_consolidator.py`

#### VERIFICATION RESULT

Searched R4 for `ObservationContext`, `observation_context`, `entity_contexts`, `member_contexts` - **NO MATCHES FOUND**.

R4 currently:

- Extracts entities from events using UltraBERT NER
- Builds entity clusters and edges via Hebbian/Granger algorithms
- Does NOT build entity-to-context mapping for enrichment algorithms

#### Required Implementation

```python
def _build_entity_context_map(
    self,
    events: List[P03EventState],
) -> Dict[str, List[ObservationContext]]:
    """Map entity IDs to their observation contexts."""
    from k0.modules.consolidation.algorithms.observation_context import ObservationContext

    entity_contexts: Dict[str, List[ObservationContext]] = {}

    for event in events:
        context = ObservationContext.from_event(event)
        entities = self._extract_entities(event.ner_entities_json)

        for entity_id in entities:
            if entity_id not in entity_contexts:
                entity_contexts[entity_id] = []
            entity_contexts[entity_id].append(context)

    return entity_contexts
```

#### Objective

Ensure R4 receives and can access full context from upstream phases.

#### Implementation

```python
class R4KGConsolidator:
    """Knowledge Graph consolidation phase."""

    async def execute(self, envelope: P03Envelope) -> R4Output:
        """Execute R4 phase."""

        # Access events with full context
        events = envelope.events  # List[P03EventState] with all context fields

        # Access episode clusters with member contexts
        clusters = envelope.phases.r2_clusters  # List[EpisodeCluster]

        # Build entity-to-context mapping for edge algorithms
        entity_contexts = self._build_entity_context_map(events)

        # Execute enrichment algorithms (see Milestone 3)
        ...

    def _build_entity_context_map(
        self,
        events: List[P03EventState],
    ) -> Dict[str, List[ObservationContext]]:
        """Map entity IDs to their observation contexts."""
        entity_contexts: Dict[str, List[ObservationContext]] = {}

        for event in events:
            context = event.to_observation_context()
            entities = self._extract_entities(event.entities_json)

            for entity_id in entities:
                if entity_id not in entity_contexts:
                    entity_contexts[entity_id] = []
                entity_contexts[entity_id].append(context)

        return entity_contexts
```

#### Acceptance Criteria

- [ ] R4 accesses events with full context
- [ ] R4 accesses clusters with member contexts
- [ ] Entity-to-context mapping built correctly
- [ ] No breaking changes to existing R4 logic

---

## Epic 2.4: Temporal Anchoring Fixes (from temporal_fix.md)

### Issue 2.4.1: TemporalParser Requires Anchor Time

**Status**: 🔲 TODO
**Complexity**: LOW
**Dependencies**: Issue 1.2.1
**Files**: `k0/modules/consolidation/algorithms/temporal_parser.py`

#### Objective

Require `ref_time` for temporal parsing to avoid `datetime.now()` fallback.

#### Acceptance Criteria

- [ ] ValueError when ref_time is None or 0
- [ ] All callers pass event.timestamp

---

### Issue 2.4.2: EpisodeCluster member_timestamps Flow

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 2.2.2
**Files**: `k0/pipelines/p03/phase_outputs.py`, `k0/pipelines/p03/phases/r2_episodic_integrator.py`, `k0/pipelines/p03/phases/r6_staging.py`

#### Objective

Preserve per-event timestamps through episodic clustering and staging.

#### Acceptance Criteria

- [ ] EpisodeCluster includes member_timestamps
- [ ] R2 populates member_timestamps from events
- [ ] R6 passes timestamps into staged writes where needed

---

### Issue 2.4.3: Prospective Anchor Fields

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 1.1.3, Issue 1.2.1
**Files**: `k0/pipelines/p03/phase_outputs.py`, `k0/modules/consolidation/truth_writer/layers/prospective.py`, `k0/pipelines/p03/phases/r6_staging.py`

#### Objective

Store `anchor_time_utc` and `original_temporal_expr` for prospective memories.

#### Acceptance Criteria

- [ ] ProspectiveMemory includes anchor fields
- [ ] Prospective truth writer persists anchor fields to st_observations
- [ ] R6 staging passes anchor fields to writes

---

# MILESTONE 3: Edge Enrichment Algorithms (GAP-007)

## Epic 3.0: Algorithm Math & Threshold Tuning (GAP-007)

### Issue 3.0.1: Shared Definitions & Fusion Rules

**Status**: 🔲 TODO
**Complexity**: LOW
**Dependencies**: Issue 1.1.4

#### Objective

Define directionality rules, weight vs confidence semantics, and multi-algorithm fusion rules.

#### Acceptance Criteria

- [ ] Canonical edge key rules for undirected relations
- [ ] Clear mapping for weight vs confidence
- [ ] Fusion rule defined for multi-algorithm overlap

---

### Issue 3.0.2: Per-Algorithm Thresholds & Calibration Plan

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 3.0.1

#### Objective

Set initial thresholds/hyperparameters and calibration strategy per algorithm.

#### Acceptance Criteria

- [ ] Initial thresholds defined for all 6 algorithms
- [ ] Calibration plan specified (offline + runtime metrics)
- [ ] Defaults reflected in EdgeEnrichmentConfig

## Epic 3.1: Semantic Similarity Edges

### Issue 3.1.1: Implement SemanticSimilarityEnricher

**Status**: 🔲 TODO - Core GAP-007 algorithm
**Complexity**: HIGH
**Dependencies**: Issue 1.2.2, Issue 1.2.3, Issue 2.3.1
**Files**: `k0/modules/consolidation/algorithms/edge_enrichers/semantic_similarity.py`

#### Objective

Create edges between semantically similar entities using embedding cosine similarity.

#### Algorithm

```python
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass
import numpy as np

class SemanticSimilarityEnricher:
    """Creates edges for semantically similar entities."""

    def __init__(
        self,
        config: SemanticSimilarityConfig,
        syscalls: Syscalls,
    ):
        self.config = config
        self.syscalls = syscalls

    async def enrich(
        self,
        entities: List[KGEntity],
        entity_contexts: Dict[str, List[ObservationContext]],
        existing_edges: Set[Tuple[str, str]],
        tenant_id: str,
        space_id: str,
    ) -> Tuple[List[KGEdge], List[KGEdgeUpdate]]:
        """Find and create semantic similarity edges."""

        new_edges: List[KGEdge] = []
        updates: List[KGEdgeUpdate] = []

        # Get embeddings for all entities
        entity_embeddings = await self._get_entity_embeddings(entities)

        for entity in entities:
            if entity.entity_id not in entity_embeddings:
                continue

            query_vector = entity_embeddings[entity.entity_id]

            # Find k nearest neighbors
            neighbors = await self.syscalls.union_index_search(
                query_vector=query_vector,
                k=self.config.k_neighbors,
                layer_filter=["st_kg_dom"],
                tenant_id=tenant_id,
                space_id=space_id,
            )

            edges_for_entity = 0
            for neighbor in neighbors:
                if edges_for_entity >= self.config.max_edges_per_entity:
                    break

                if neighbor.entity_id == entity.entity_id:
                    continue  # Skip self

                similarity = neighbor.score
                if similarity < self.config.similarity_threshold:
                    continue

                edge_key = self._canonical_edge_key(entity.entity_id, neighbor.entity_id)

                if edge_key in existing_edges:
                    # Update existing edge
                    updates.append(KGEdgeUpdate(
                        edge_id=self._find_edge_id(edge_key),
                        weight_delta=similarity * 0.1,  # Reinforce
                        source_algorithm="semantic_similarity",
                        observation_context=self._get_best_context(
                            entity_contexts.get(entity.entity_id, [])
                        ),
                    ))
                else:
                    # Create new edge
                    new_edges.append(KGEdge(
                        edge_id=generate_ulid(),
                        source_entity_id=entity.entity_id,
                        target_entity_id=neighbor.entity_id,
                        relation_type=self.config.relation_type,
                        edge_weight=similarity,
                        confidence_score=similarity,
                        source_algorithm="semantic_similarity",
                        properties_json=json.dumps({
                            "similarity_score": similarity,
                            "k": self.config.k_neighbors,
                            "threshold": self.config.similarity_threshold,
                        }),
                        observation_context=self._get_best_context(
                            entity_contexts.get(entity.entity_id, [])
                        ),
                    ))
                    edges_for_entity += 1

        return new_edges, updates

    def _canonical_edge_key(self, a: str, b: str) -> Tuple[str, str]:
        """Return canonical (sorted) edge key for undirected edges."""
        return tuple(sorted([a, b]))

    def _get_best_context(
        self,
        contexts: List[ObservationContext],
    ) -> Optional[ObservationContext]:
        """Get highest salience context."""
        if not contexts:
            return None
        return max(contexts, key=lambda c: c.salience_score or 0.0)
```

#### Syscalls Required

- `union_index_search(query_vector, k, layer_filter, tenant_id, space_id)`
- `embedding_vectors_batch_query(embedding_ids)` (if vectors not in memory)

#### Acceptance Criteria

- [ ] Finds k-nearest neighbors using FAISS
- [ ] Respects similarity threshold
- [ ] Respects max edges per entity limit
- [ ] Creates edges with correct `source_algorithm`
- [ ] Attaches observation context
- [ ] Handles existing edges (updates vs creates)
- [ ] Unit tests with mock syscalls

---

### Issue 3.1.2: Unit Tests for Semantic Similarity

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 3.1.1
**Files**: `tests/k0/modules/consolidation/algorithms/edge_enrichers/test_semantic_similarity.py`

#### Test Cases

```python
class TestSemanticSimilarityEnricher:

    async def test_finds_similar_entities(self):
        """Should create edges for entities above threshold."""
        pass

    async def test_respects_threshold(self):
        """Should not create edges below similarity threshold."""
        pass

    async def test_respects_max_edges_limit(self):
        """Should stop after max_edges_per_entity."""
        pass

    async def test_skips_self_edges(self):
        """Should not create edge from entity to itself."""
        pass

    async def test_updates_existing_edges(self):
        """Should create update for existing edges."""
        pass

    async def test_attaches_context(self):
        """Should attach highest salience context."""
        pass

    async def test_canonical_edge_ordering(self):
        """Should use consistent edge key ordering."""
        pass
```

---

## Epic 3.2: Temporal Proximity Edges

### Issue 3.2.1: Implement TemporalProximityEnricher

**Status**: 🔲 TODO - Core GAP-007 algorithm
**Complexity**: MEDIUM
**Dependencies**: Issue 1.2.2, Issue 1.2.3
**Files**: `k0/modules/consolidation/algorithms/edge_enrichers/temporal_proximity.py`

#### Objective

Create/strengthen edges when entities are observed within a short time window.

#### Algorithm

```python
import math
from collections import defaultdict

class TemporalProximityEnricher:
    """Creates edges for temporally co-occurring entities."""

    def __init__(self, config: TemporalProximityConfig):
        self.config = config

    async def enrich(
        self,
        events: List[P03EventState],
        entity_contexts: Dict[str, List[ObservationContext]],
        existing_edges: Set[Tuple[str, str]],
    ) -> Tuple[List[KGEdge], List[KGEdgeUpdate]]:
        """Find entities that co-occur within time window."""

        # Build entity -> [(timestamp, context)] mapping
        entity_observations: Dict[str, List[Tuple[int, ObservationContext]]] = defaultdict(list)

        for event in events:
            context = event.to_observation_context()
            entities = self._extract_entities(event.entities_json)
            for entity_id in entities:
                entity_observations[entity_id].append((event.timestamp, context))

        # Find temporal co-occurrences
        co_occurrences: Dict[Tuple[str, str], List[Tuple[int, int]]] = defaultdict(list)

        entity_ids = list(entity_observations.keys())
        for i, entity_a in enumerate(entity_ids):
            for entity_b in entity_ids[i+1:]:
                for ts_a, _ in entity_observations[entity_a]:
                    for ts_b, _ in entity_observations[entity_b]:
                        delta = abs(ts_a - ts_b)
                        if delta <= self.config.window_ms:
                            edge_key = self._canonical_edge_key(entity_a, entity_b)
                            co_occurrences[edge_key].append((ts_a, ts_b))

        # Calculate edge weights using exponential decay
        new_edges: List[KGEdge] = []
        updates: List[KGEdgeUpdate] = []

        for edge_key, occurrences in co_occurrences.items():
            weight = sum(
                math.exp(-abs(ts_a - ts_b) / self.config.tau_ms)
                for ts_a, ts_b in occurrences
            )

            if weight < self.config.min_weight:
                continue

            # Normalize weight to [0, 1]
            weight = min(1.0, weight / len(occurrences))

            entity_a, entity_b = edge_key

            if edge_key in existing_edges:
                updates.append(KGEdgeUpdate(
                    edge_id=self._find_edge_id(edge_key),
                    weight_delta=weight * 0.1,
                    source_algorithm="temporal_proximity",
                    new_evidence_event_ids=[e.event_id for e in events],
                ))
            else:
                new_edges.append(KGEdge(
                    edge_id=generate_ulid(),
                    source_entity_id=entity_a,
                    target_entity_id=entity_b,
                    relation_type=self.config.relation_type,
                    edge_weight=weight,
                    confidence_score=min(1.0, len(occurrences) / 5),  # Confidence from count
                    source_algorithm="temporal_proximity",
                    evidence_event_ids=[e.event_id for e in events],
                    properties_json=json.dumps({
                        "co_occurrence_count": len(occurrences),
                        "window_ms": self.config.window_ms,
                        "tau_ms": self.config.tau_ms,
                    }),
                ))

        return new_edges, updates
```

#### Acceptance Criteria

- [ ] Detects entities within time window
- [ ] Uses exponential decay for weight calculation
- [ ] Respects minimum weight threshold
- [ ] Creates/updates edges correctly
- [ ] Records evidence event IDs

---

### Issue 3.2.2: Unit Tests for Temporal Proximity

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 3.2.1
**Files**: `tests/k0/modules/consolidation/algorithms/edge_enrichers/test_temporal_proximity.py`

---

## Epic 3.3: Contextual Edges

### Issue 3.3.1: Implement ContextualEdgeEnricher

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 1.2.2, Issue 2.2.2
**Files**: `k0/modules/consolidation/algorithms/edge_enrichers/contextual.py`

#### Objective

Create edges based on shared context features (location, social, affect, activity).

#### Algorithm

```python
class ContextualEdgeEnricher:
    """Creates edges for entities sharing context features."""

    def __init__(self, config: ContextualEdgeConfig):
        self.config = config

    async def enrich(
        self,
        entity_contexts: Dict[str, List[ObservationContext]],
        existing_edges: Set[Tuple[str, str]],
    ) -> Tuple[List[KGEdge], List[KGEdgeUpdate]]:
        """Find entities with similar context profiles."""

        # Build context feature sets per entity
        entity_features: Dict[str, Set[str]] = {}

        for entity_id, contexts in entity_contexts.items():
            features = set()
            for ctx in contexts:
                if ctx.location_type:
                    features.add(f"location:{ctx.location_type}")
                if ctx.social_context:
                    features.add(f"social:{ctx.social_context}")
                if ctx.time_of_day_bucket:
                    features.add(f"time:{ctx.time_of_day_bucket}")
                if ctx.sentiment_label:
                    features.add(f"sentiment:{ctx.sentiment_label}")
                if ctx.ingress_channel:
                    features.add(f"channel:{ctx.ingress_channel}")
            entity_features[entity_id] = features

        # Calculate Jaccard similarity between entity pairs
        new_edges: List[KGEdge] = []
        updates: List[KGEdgeUpdate] = []

        entity_ids = list(entity_features.keys())
        for i, entity_a in enumerate(entity_ids):
            edges_for_entity = 0
            for entity_b in entity_ids[i+1:]:
                if edges_for_entity >= self.config.max_edges_per_entity:
                    break

                features_a = entity_features[entity_a]
                features_b = entity_features[entity_b]

                intersection = features_a & features_b
                union = features_a | features_b

                if not union:
                    continue

                jaccard = len(intersection) / len(union)

                if jaccard < self.config.similarity_threshold:
                    continue

                edge_key = self._canonical_edge_key(entity_a, entity_b)

                if edge_key in existing_edges:
                    updates.append(KGEdgeUpdate(
                        edge_id=self._find_edge_id(edge_key),
                        weight_delta=jaccard * 0.1,
                        source_algorithm="contextual",
                    ))
                else:
                    new_edges.append(KGEdge(
                        edge_id=generate_ulid(),
                        source_entity_id=entity_a,
                        target_entity_id=entity_b,
                        relation_type=self.config.relation_type,
                        edge_weight=jaccard,
                        confidence_score=jaccard,
                        source_algorithm="contextual",
                        properties_json=json.dumps({
                            "shared_features": list(intersection),
                            "jaccard_similarity": jaccard,
                        }),
                    ))
                    edges_for_entity += 1

        return new_edges, updates
```

#### Acceptance Criteria

- [ ] Extracts context features correctly
- [ ] Calculates Jaccard similarity
- [ ] Respects similarity threshold
- [ ] Creates edges with shared features in properties

---

### Issue 3.3.2: Unit Tests for Contextual Edges

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 3.3.1
**Files**: `tests/k0/modules/consolidation/algorithms/edge_enrichers/test_contextual.py`

---

## Epic 3.4: Transitive Closure Edges

### Issue 3.4.1: Implement TransitiveClosureEnricher

**Status**: 🔲 TODO
**Complexity**: HIGH
**Dependencies**: Issue 1.2.2
**Files**: `k0/modules/consolidation/algorithms/edge_enrichers/transitive_closure.py`

#### Objective

Infer edges via short paths in the KG (bounded hop count).

#### Algorithm

```python
class TransitiveClosureEnricher:
    """Infers edges via graph paths."""

    def __init__(
        self,
        config: TransitiveClosureConfig,
        syscalls: Syscalls,
    ):
        self.config = config
        self.syscalls = syscalls

    async def enrich(
        self,
        batch_entities: List[str],
        existing_edges: Dict[Tuple[str, str], KGEdge],
        tenant_id: str,
        space_id: str,
    ) -> Tuple[List[KGEdge], List[KGEdgeUpdate]]:
        """Infer edges via 2-hop paths."""

        # Get local subgraph (edges involving batch entities)
        local_edges = await self.syscalls.kg_edges_by_entity_ids(
            tenant_id=tenant_id,
            space_id=space_id,
            entity_ids=batch_entities,
        )

        # Build adjacency list
        adjacency: Dict[str, List[Tuple[str, float, float]]] = defaultdict(list)
        for edge in local_edges:
            adjacency[edge.source_entity_id].append(
                (edge.target_entity_id, edge.edge_weight, edge.confidence_score)
            )
            # Undirected: add reverse
            adjacency[edge.target_entity_id].append(
                (edge.source_entity_id, edge.edge_weight, edge.confidence_score)
            )

        # Find 2-hop paths
        new_edges: List[KGEdge] = []
        updates: List[KGEdgeUpdate] = []

        for entity_a in batch_entities:
            if entity_a not in adjacency:
                continue

            for neighbor, weight_ab, conf_ab in adjacency[entity_a]:
                if neighbor not in adjacency:
                    continue

                for entity_c, weight_bc, conf_bc in adjacency[neighbor]:
                    if entity_c == entity_a:
                        continue  # Skip going back

                    # Already have direct edge?
                    edge_key = self._canonical_edge_key(entity_a, entity_c)
                    if edge_key in existing_edges:
                        continue

                    # Calculate inferred weight
                    inferred_weight = self.config.attenuation_factor * min(weight_ab, weight_bc)
                    inferred_conf = self.config.attenuation_factor * min(conf_ab, conf_bc)

                    if inferred_conf < self.config.min_confidence:
                        continue

                    new_edges.append(KGEdge(
                        edge_id=generate_ulid(),
                        source_entity_id=entity_a,
                        target_entity_id=entity_c,
                        relation_type=self.config.relation_type,
                        edge_weight=inferred_weight,
                        confidence_score=inferred_conf,
                        source_algorithm="transitive_closure",
                        inference_chain_json=json.dumps({
                            "path": [entity_a, neighbor, entity_c],
                            "hop_count": 2,
                            "attenuation": self.config.attenuation_factor,
                        }),
                    ))

        return new_edges, updates
```

#### Acceptance Criteria

- [ ] Finds 2-hop paths correctly
- [ ] Applies attenuation factor
- [ ] Respects minimum confidence
- [ ] Records inference chain
- [ ] Does not duplicate existing edges

---

### Issue 3.4.2: Unit Tests for Transitive Closure

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 3.4.1
**Files**: `tests/k0/modules/consolidation/algorithms/edge_enrichers/test_transitive_closure.py`

---

## Epic 3.5: Bayesian Causal Edges

### Issue 3.5.1: Implement BayesianCausalEnricher

**Status**: 🔲 TODO
**Complexity**: HIGH
**Dependencies**: Issue 1.2.2
**Files**: `k0/modules/consolidation/algorithms/edge_enrichers/bayesian_causal.py`

#### Objective

Infer causal edges under sparse observations where Granger is insufficient.

#### Algorithm

```python
class BayesianCausalEnricher:
    """Infers causal edges using Bayesian inference."""

    def __init__(self, config: BayesianCausalConfig):
        self.config = config

    async def enrich(
        self,
        entity_observations: Dict[str, List[Tuple[int, ObservationContext]]],
        existing_causal_edges: Set[Tuple[str, str]],
    ) -> Tuple[List[KGEdge], List[KGEdgeUpdate]]:
        """Infer causal relationships from temporal ordering."""

        new_edges: List[KGEdge] = []
        updates: List[KGEdgeUpdate] = []

        entity_ids = list(entity_observations.keys())

        for entity_a in entity_ids:
            observations_a = entity_observations[entity_a]

            for entity_b in entity_ids:
                if entity_a == entity_b:
                    continue

                observations_b = entity_observations[entity_b]

                # Count temporal precedence evidence
                a_before_b = 0
                b_before_a = 0

                for ts_a, _ in observations_a:
                    for ts_b, _ in observations_b:
                        if ts_a < ts_b:
                            a_before_b += 1
                        elif ts_b < ts_a:
                            b_before_a += 1

                total_pairs = a_before_b + b_before_a

                if total_pairs < self.config.min_evidence_count:
                    continue

                # Bayesian update
                # Prior: uniform (0.5)
                prior = self.config.prior_strength

                # Likelihood ratio
                if a_before_b > b_before_a:
                    likelihood_ratio = a_before_b / max(1, b_before_a)
                    cause, effect = entity_a, entity_b
                else:
                    likelihood_ratio = b_before_a / max(1, a_before_b)
                    cause, effect = entity_b, entity_a

                # Posterior (simplified)
                posterior = (prior * likelihood_ratio) / (
                    prior * likelihood_ratio + (1 - prior)
                )

                if posterior < self.config.posterior_threshold:
                    continue

                edge_key = (cause, effect)  # Directed edge

                if edge_key in existing_causal_edges:
                    updates.append(KGEdgeUpdate(
                        edge_id=self._find_edge_id(edge_key),
                        confidence_delta=0.05,
                        source_algorithm="bayesian_causal",
                    ))
                else:
                    new_edges.append(KGEdge(
                        edge_id=generate_ulid(),
                        source_entity_id=cause,
                        target_entity_id=effect,
                        relation_type=self.config.relation_type,
                        edge_weight=posterior,
                        confidence_score=posterior,
                        source_algorithm="bayesian_causal",
                        properties_json=json.dumps({
                            "precedence_count": max(a_before_b, b_before_a),
                            "total_pairs": total_pairs,
                            "posterior": posterior,
                            "prior": prior,
                        }),
                    ))

        return new_edges, updates
```

#### Acceptance Criteria

- [ ] Counts temporal precedence correctly
- [ ] Applies Bayesian update
- [ ] Creates directed CAUSES edges
- [ ] Respects minimum evidence count
- [ ] Respects posterior threshold

---

### Issue 3.5.2: Unit Tests for Bayesian Causal

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 3.5.1
**Files**: `tests/k0/modules/consolidation/algorithms/edge_enrichers/test_bayesian_causal.py`

---

## Epic 3.6: Edge Weight Normalization

### Issue 3.6.1: Implement EdgeWeightNormalizer

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 1.2.2
**Files**: `k0/modules/consolidation/algorithms/edge_enrichers/weight_normalization.py`

#### Objective

Prevent runaway hubs and keep edge weights in a stable range.

#### Algorithm

```python
class EdgeWeightNormalizer:
    """Normalizes edge weights to prevent hub dominance."""

    def __init__(self, config: WeightNormalizationConfig):
        self.config = config

    def normalize(
        self,
        new_edges: List[KGEdge],
        updates: List[KGEdgeUpdate],
        existing_edges: Dict[str, List[KGEdge]],  # entity_id -> outgoing edges
    ) -> List[KGEdgeUpdate]:
        """Apply normalization to edges."""

        normalization_updates: List[KGEdgeUpdate] = []

        # Group all edges by source entity
        entity_edges: Dict[str, List[Tuple[str, float]]] = defaultdict(list)

        # Add existing edges
        for entity_id, edges in existing_edges.items():
            for edge in edges:
                entity_edges[entity_id].append((edge.edge_id, edge.edge_weight))

        # Add new edges
        for edge in new_edges:
            entity_edges[edge.source_entity_id].append((edge.edge_id, edge.edge_weight))

        # Apply updates
        for update in updates:
            # Find and apply delta (simplified)
            pass

        # Normalize per entity
        for entity_id, edges in entity_edges.items():
            if len(edges) <= 1:
                continue

            weights = [w for _, w in edges]
            total_weight = sum(weights)

            if self.config.strategy == "sum_to_one":
                for edge_id, old_weight in edges:
                    new_weight = old_weight / total_weight
                    if abs(new_weight - old_weight) > 0.001:
                        normalization_updates.append(KGEdgeUpdate(
                            edge_id=edge_id,
                            new_weight=new_weight,
                            source_algorithm="weight_normalization",
                        ))

            elif self.config.strategy == "cap":
                for edge_id, old_weight in edges:
                    if old_weight > self.config.max_weight:
                        normalization_updates.append(KGEdgeUpdate(
                            edge_id=edge_id,
                            new_weight=self.config.max_weight,
                            source_algorithm="weight_normalization",
                        ))

            elif self.config.strategy == "softmax":
                import math
                exp_weights = [math.exp(w) for w in weights]
                exp_sum = sum(exp_weights)
                for (edge_id, _), exp_w in zip(edges, exp_weights):
                    new_weight = exp_w / exp_sum
                    normalization_updates.append(KGEdgeUpdate(
                        edge_id=edge_id,
                        new_weight=new_weight,
                        source_algorithm="weight_normalization",
                    ))

        return normalization_updates
```

#### Acceptance Criteria

- [ ] Supports sum_to_one strategy
- [ ] Supports cap strategy
- [ ] Supports softmax strategy
- [ ] Only creates updates when weight changes
- [ ] Handles edge cases (single edge, no edges)

---

### Issue 3.6.2: Unit Tests for Weight Normalization

**Status**: 🔲 TODO
**Complexity**: LOW
**Dependencies**: Issue 3.6.1
**Files**: `tests/k0/modules/consolidation/algorithms/edge_enrichers/test_weight_normalization.py`

---

# MILESTONE 4: Output Pipeline (R4 → R7 Flow)

## Epic 4.0: Wiring Conformance Checklist (GAP-007)

### Issue 4.0.1: Envelope and Persistence Mapping

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 1.1.4, Issue 4.1.2

#### Objective

Ensure all R4 outputs map cleanly through envelope → staging → truth writer.

#### Acceptance Criteria

- [ ] Each algorithm’s outputs mapped to envelope fields
- [ ] R6 staging maps all required fields
- [ ] R7 write SQL covers all fields consistently

---

### Issue 4.0.2: Syscall/Capability Validation and Bounded Reads

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 3.0.1

#### Objective

Validate required syscalls and ensure bounded KG reads for performance.

#### Acceptance Criteria

- [ ] Required syscalls/capabilities confirmed per algorithm
- [ ] Bounded read strategy defined for transitive closure and normalization

## Epic 4.1: R4 Output Enhancement

### Issue 4.1.1: Integrate All Enrichers into R4

**Status**: 🔲 TODO
**Complexity**: HIGH
**Dependencies**: All Epic 3.x issues
**Files**: `k0/pipelines/p03/phases/r4_kg_consolidator.py`

#### Objective

Wire all enrichment algorithms into R4 execution flow.

#### Implementation

```python
class R4KGConsolidator:
    """Enhanced R4 with edge enrichment algorithms."""

    def __init__(
        self,
        config: EdgeEnrichmentConfig,
        syscalls: Syscalls,
    ):
        self.config = config
        self.syscalls = syscalls

        # Initialize enrichers
        self.semantic_enricher = SemanticSimilarityEnricher(
            config.semantic_similarity, syscalls
        )
        self.temporal_enricher = TemporalProximityEnricher(
            config.temporal_proximity
        )
        self.contextual_enricher = ContextualEdgeEnricher(
            config.contextual
        )
        self.transitive_enricher = TransitiveClosureEnricher(
            config.transitive_closure, syscalls
        )
        self.bayesian_enricher = BayesianCausalEnricher(
            config.bayesian_causal
        )
        self.normalizer = EdgeWeightNormalizer(
            config.weight_normalization
        )

    async def execute(self, envelope: P03Envelope) -> R4Output:
        """Execute R4 with all enrichment algorithms."""

        # Existing R4 logic (entity extraction, Granger causality)
        entities, existing_edges = await self._run_existing_logic(envelope)

        # Build context maps
        entity_contexts = self._build_entity_context_map(envelope.events)
        entity_observations = self._build_entity_observations(envelope.events)
        existing_edge_set = {
            (e.source_entity_id, e.target_entity_id) for e in existing_edges
        }

        # Run enrichment algorithms
        all_new_edges: List[KGEdge] = []
        all_updates: List[KGEdgeUpdate] = []

        # 1. Semantic similarity
        if self.config.semantic_similarity.enabled:
            new, updates = await self.semantic_enricher.enrich(
                entities, entity_contexts, existing_edge_set,
                envelope.tenant_id, envelope.space_id,
            )
            all_new_edges.extend(new)
            all_updates.extend(updates)

        # 2. Temporal proximity
        if self.config.temporal_proximity.enabled:
            new, updates = await self.temporal_enricher.enrich(
                envelope.events, entity_contexts, existing_edge_set,
            )
            all_new_edges.extend(new)
            all_updates.extend(updates)

        # 3. Contextual edges
        if self.config.contextual.enabled:
            new, updates = await self.contextual_enricher.enrich(
                entity_contexts, existing_edge_set,
            )
            all_new_edges.extend(new)
            all_updates.extend(updates)

        # 4. Transitive closure
        if self.config.transitive_closure.enabled:
            batch_entity_ids = [e.entity_id for e in entities]
            new, updates = await self.transitive_enricher.enrich(
                batch_entity_ids, existing_edges,
                envelope.tenant_id, envelope.space_id,
            )
            all_new_edges.extend(new)
            all_updates.extend(updates)

        # 5. Bayesian causal
        if self.config.bayesian_causal.enabled:
            existing_causal = {
                (e.source_entity_id, e.target_entity_id)
                for e in existing_edges
                if e.relation_type == "CAUSES"
            }
            new, updates = await self.bayesian_enricher.enrich(
                entity_observations, existing_causal,
            )
            all_new_edges.extend(new)
            all_updates.extend(updates)

        # 6. Normalize weights
        if self.config.weight_normalization.enabled:
            norm_updates = self.normalizer.normalize(
                all_new_edges, all_updates, existing_edges,
            )
            all_updates.extend(norm_updates)

        # Apply limits
        all_new_edges = all_new_edges[:self.config.max_total_new_edges_per_cycle]
        all_updates = all_updates[:self.config.max_total_updates_per_cycle]

        return R4Output(
            entities=entities,
            new_edges=all_new_edges,
            updated_edges=all_updates,
        )
```

#### Acceptance Criteria

- [ ] All 6 enrichers integrated
- [ ] Config controls enabled/disabled state
- [ ] Global limits enforced
- [ ] Existing R4 logic unchanged
- [ ] Output contains new_edges and updated_edges

---

### Issue 4.1.2: Update R4Output Dataclass

**Status**: 🔲 TODO
**Complexity**: LOW
**Dependencies**: Issue 1.2.2
**Files**: `k0/pipelines/p03/phase_outputs.py`

#### Implementation

```python
@dataclass
class R4Output:
    """Output from R4 KG Consolidation phase."""

    # Existing outputs
    entities: List[KGEntity] = field(default_factory=list)
    causal_edges: List[KGEdge] = field(default_factory=list)  # From Granger

    # NEW: Edge enrichment outputs
    new_edges: List[KGEdge] = field(default_factory=list)
    updated_edges: List[KGEdgeUpdate] = field(default_factory=list)

    # NEW: Algorithm attribution
    edges_by_algorithm: Dict[str, int] = field(default_factory=dict)

    def get_all_new_edges(self) -> List[KGEdge]:
        """Get all new edges (causal + enrichment)."""
        return self.causal_edges + self.new_edges
```

---

## Epic 4.2: R6 Staging Integration

### Issue 4.2.1: Update KGWriteAssembler for New Edge Fields

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 4.1.2
**Files**: `k0/modules/consolidation/staging/kg_write_assembler.py`

#### Objective

Handle new edge fields when creating StagedWrite records.

#### Implementation

```python
class KGWriteAssembler:
    """Assembles StagedWrite records for KG layer."""

    def assemble_edge_writes(
        self,
        new_edges: List[KGEdge],
        updated_edges: List[KGEdgeUpdate],
        cycle_id: str,
    ) -> List[StagedWrite]:
        """Create StagedWrite records for edges."""

        writes: List[StagedWrite] = []

        for edge in new_edges:
            writes.append(StagedWrite(
                layer="st_kg_edges",
                operation="INSERT",
                record_id=edge.edge_id,
                record_data={
                    "edge_id": edge.edge_id,
                    "source_entity_id": edge.source_entity_id,
                    "target_entity_id": edge.target_entity_id,
                    "relation_type": edge.relation_type,
                    "edge_weight": edge.edge_weight,
                    "confidence_score": edge.confidence_score,
                    "source_algorithm": edge.source_algorithm,  # NEW
                    "evidence_event_ids": edge.evidence_event_ids,  # NEW
                    "evidence_episode_ids": edge.evidence_episode_ids,  # NEW
                    "properties_json": edge.properties_json,
                    "algorithm_params_json": edge.algorithm_params_json,  # NEW
                    "inference_chain_json": edge.inference_chain_json,  # NEW
                    "observation_count": 1,
                },
                source_event_ids=edge.evidence_event_ids,
                observation_context=edge.observation_context,  # NEW
                consolidation_cycle_id=cycle_id,
            ))

        for update in updated_edges:
            writes.append(StagedWrite(
                layer="st_kg_edges",
                operation="UPDATE",
                record_id=update.edge_id,
                record_data={
                    "weight_delta": update.weight_delta,
                    "confidence_delta": update.confidence_delta,
                    "new_weight": update.new_weight,
                    "new_confidence": update.new_confidence,
                    "source_algorithm": update.source_algorithm,
                    "new_evidence_event_ids": update.new_evidence_event_ids,
                },
                observation_context=update.observation_context,
                consolidation_cycle_id=cycle_id,
            ))

        return writes
```

#### Acceptance Criteria

- [ ] Handles all new edge fields
- [ ] Creates INSERT writes for new edges
- [ ] Creates UPDATE writes for edge updates
- [ ] Attaches observation context

---

### Issue 4.2.2: Update StagedWrite Dataclass

**Status**: 🔲 TODO
**Complexity**: LOW
**Dependencies**: Issue 1.2.1
**Files**: `k0/modules/consolidation/staging/staged_writes.py`

#### Implementation

```python
@dataclass
class StagedWrite:
    """Staged write for truth layer."""

    layer: str
    operation: str  # INSERT, UPDATE, MERGE
    record_id: str
    record_data: dict

    # Existing
    source_event_ids: List[str] = field(default_factory=list)

    # NEW: Full observation context
    observation_context: Optional[ObservationContext] = None

    # NEW: Cycle tracking
    consolidation_cycle_id: Optional[str] = None
```

---

## Epic 4.3: R7 Truth Writer Integration

### Issue 4.3.1: Update KGLayerWriter for New Columns

**Status**: 🔶 PARTIAL - Exists, needs enhancement for new columns
**Complexity**: MEDIUM
**Dependencies**: Issue 1.1.1, Issue 1.1.2
**Files**: `k0/modules/consolidation/truth_writer/layers/kg.py` (EXISTS)

#### CURRENT STATUS

KGLayerWriter already:

- Handles st_kg_dom (entities) and st_kg_edges (relationships)
- Records observations with ObservationRecorder
- Tracks FIRST_SEEN/REINFORCEMENT observation types
- Has `_update_edge_observation_count()` for Granger causality

Needs enhancement for:

- source_algorithm column in INSERT/UPDATE SQL
- evidence_event_ids, evidence_episode_ids arrays
- algorithm_params_json, inference_chain_json columns

#### Objective

Update INSERT and UPDATE SQL to include new columns.

#### Implementation

```python
class KGLayerWriter:
    """Writes to st_kg_edges table."""

    async def _insert_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """Insert new edge."""
        data = write.record_data

        await uow.connection.execute(
            """
            INSERT INTO st_kg_edges (
                edge_id, tenant_id, space_id,
                source_entity_id, target_entity_id, relation_type,
                edge_weight, confidence_score, observation_count,
                source_algorithm,  -- NEW
                evidence_event_ids,  -- NEW
                evidence_episode_ids,  -- NEW
                algorithm_params_json,  -- NEW
                inference_chain_json,  -- NEW
                properties_json,
                created_at, updated_at
            ) VALUES (
                :edge_id, :tenant_id, :space_id,
                :source_entity_id, :target_entity_id, :relation_type,
                :edge_weight, :confidence_score, :observation_count,
                :source_algorithm,
                :evidence_event_ids,
                :evidence_episode_ids,
                :algorithm_params_json,
                :inference_chain_json,
                :properties_json,
                :now, :now
            )
            """,
            {
                **data,
                "tenant_id": write.tenant_id,
                "space_id": write.space_id,
                "now": _now_ms(),
            }
        )

        # Record observation
        if write.observation_context:
            await self._observation_recorder.record(
                uow=uow,
                layer="st_kg_edges",
                record_id=write.record_id,
                context=write.observation_context,
                tenant_id=write.tenant_id,
                space_id=write.space_id,
            )

    async def _update_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """Update existing edge."""
        data = write.record_data

        # Build dynamic UPDATE
        updates = []
        params = {"edge_id": write.record_id, "now": _now_ms()}

        if data.get("weight_delta"):
            updates.append("edge_weight = edge_weight + :weight_delta")
            params["weight_delta"] = data["weight_delta"]

        if data.get("new_weight") is not None:
            updates.append("edge_weight = :new_weight")
            params["new_weight"] = data["new_weight"]

        if data.get("confidence_delta"):
            updates.append("confidence_score = confidence_score + :confidence_delta")
            params["confidence_delta"] = data["confidence_delta"]

        if data.get("new_evidence_event_ids"):
            updates.append(
                "evidence_event_ids = array_cat(evidence_event_ids, :new_evidence)"
            )
            params["new_evidence"] = data["new_evidence_event_ids"]

        updates.append("observation_count = observation_count + 1")
        updates.append("updated_at = :now")

        await uow.connection.execute(
            f"""
            UPDATE st_kg_edges
            SET {', '.join(updates)}
            WHERE edge_id = :edge_id
            """,
            params
        )

        # Record observation
        if write.observation_context:
            await self._observation_recorder.record(
                uow=uow,
                layer="st_kg_edges",
                record_id=write.record_id,
                context=write.observation_context,
                tenant_id=write.tenant_id,
                space_id=write.space_id,
            )
```

#### Acceptance Criteria

- [ ] INSERT includes all new columns
- [ ] UPDATE handles delta and absolute updates
- [ ] Evidence arrays appended correctly
- [ ] Observation recorded on every write

---

### Issue 4.3.2: Create ObservationRecorder Service

**Status**: ✅ DONE
**Complexity**: MEDIUM
**Dependencies**: Issue 1.1.3, Issue 1.2.1
**Files**: `k0/modules/consolidation/truth_writer/observation_recorder.py` (ALREADY EXISTS)

#### IMPLEMENTATION STATUS: COMPLETE

ObservationRecorder service exists with:

- `record()` - Single observation recording
- `record_batch()` - Batch recording for efficiency
- `record_for_insert()` - Convenience for FIRST_SEEN operations
- `record_for_merge()` - Convenience for REINFORCEMENT operations
- Supports all 6 valid layers including st_kg_edges
- Full 32-column INSERT SQL

#### Implementation (Reference)

```python
class ObservationRecorder:
    """Records observations to st_observations table."""

    async def record(
        self,
        uow: UnitOfWork,
        layer: str,
        record_id: str,
        context: ObservationContext,
        tenant_id: str,
        space_id: str,
    ) -> str:
        """Record a single observation."""

        observation_id = generate_ulid()

        await uow.connection.execute(
            """
            INSERT INTO st_observations (
                observation_id, layer, record_id, tenant_id, space_id,
                observed_at, anchor_time_utc, original_temporal_expr,
                time_of_day_bucket, circadian_slot, is_weekend,
                sentiment_score, sentiment_label, affect_valence,
                affect_arousal, dominant_emotion,
                salience_score, salience_band, novelty_score,
                ingress_channel, ingress_source, device_kind,
                location_name, location_type, geohash_6,
                social_context, social_intimacy, is_solo_event, num_participants,
                observation_type, confidence,
                source_event_id, consolidation_cycle_id,
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
                **context.to_dict(),
                "created_at": _now_ms(),
            }
        )

        return observation_id
```

#### Acceptance Criteria

- [x] Inserts all 32 columns
- [x] ULID generated for observation_id
- [x] NULL handling for optional fields
- [x] Supports all 6 valid layers (including st_kg_edges)
- [x] record_for_insert() and record_for_merge() convenience methods
- [ ] Integration test with real database - VERIFY test coverage

---

# MILESTONE 5: Testing & Validation

## Epic 5.1: Unit Tests

### Issue 5.1.1: Unit Tests for Data Structures

**Status**: 🔲 TODO
**Complexity**: LOW
**Dependencies**: Epic 1.2
**Files**: `tests/k0/modules/consolidation/algorithms/test_observation_context.py`

---

### Issue 5.1.2: Unit Tests for All Enrichers

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Epic 3.x
**Files**: `tests/k0/modules/consolidation/algorithms/edge_enrichers/`

---

## Epic 5.2: Integration Tests

### Issue 5.2.1: R4 Integration Test with Mock Syscalls

**Status**: 🔲 TODO
**Complexity**: HIGH
**Dependencies**: Issue 4.1.1
**Files**: `tests/k0/pipelines/p03/test_r4_integration.py`

#### Test Cases

```python
class TestR4Integration:

    async def test_full_r4_pipeline_with_enrichment(self):
        """R4 produces edges from all enabled algorithms."""
        pass

    async def test_r4_respects_config_disabled(self):
        """Disabled algorithms produce no edges."""
        pass

    async def test_r4_respects_global_limits(self):
        """Total edges capped at config limit."""
        pass

    async def test_r4_context_flows_to_edges(self):
        """Observation context attached to edges."""
        pass

    async def test_r4_existing_edges_updated_not_duplicated(self):
        """Existing edges receive updates, not new edges."""
        pass
```

---

### Issue 5.2.2: End-to-End P03 Integration Test

**Status**: 🔲 TODO
**Complexity**: HIGH
**Dependencies**: All Milestone 4 issues
**Files**: `tests/k0/pipelines/p03/test_p03_e2e_enrichment.py`

#### Test Cases

```python
class TestP03EndToEndEnrichment:

    async def test_enriched_edges_persisted_to_database(self):
        """New edges written to st_kg_edges with all fields."""
        pass

    async def test_observations_recorded_for_edges(self):
        """st_observations has records for each edge write."""
        pass

    async def test_source_algorithm_correctly_set(self):
        """Each edge has correct source_algorithm."""
        pass

    async def test_evidence_event_ids_populated(self):
        """Evidence arrays contain source event IDs."""
        pass
```

---

## Epic 5.3: Performance Validation

### Issue 5.3.1: Benchmark Edge Enrichment Algorithms

**Status**: 🔲 TODO
**Complexity**: MEDIUM
**Dependencies**: Issue 4.1.1
**Files**: `tests/k0/pipelines/p03/benchmarks/test_r4_performance.py`

#### Metrics to Measure

| Metric | Target | Current |
|--------|--------|---------|
| Semantic similarity (100 entities) | <500ms | TBD |
| Temporal proximity (1000 events) | <200ms | TBD |
| Contextual edges (100 entities) | <100ms | TBD |
| Transitive closure (1000 edges) | <300ms | TBD |
| Full R4 cycle | <2000ms | TBD |

---

### Issue 5.3.2: Load Test with Production-Scale Data

**Status**: 🔲 TODO
**Complexity**: HIGH
**Dependencies**: Issue 5.3.1
**Files**: `tests/k0/pipelines/p03/benchmarks/test_r4_load.py`

---

# Implementation Order (UPDATED)

```
PHASE 1: Foundation - MOSTLY COMPLETE
├── Issue 1.1.1: source_algorithm column         🔲 TODO
├── Issue 1.1.2: evidence columns                🔲 TODO
├── Issue 1.1.3: st_observations table           ✅ DONE (0067)
├── Issue 1.1.4: evidence linkage rules          🔲 TODO
├── Issue 1.2.1: ObservationContext dataclass    ✅ DONE
├── Issue 1.2.2: KGEdge/KGEdgeUpdate dataclasses 🔶 PARTIAL (needs source_algorithm)
└── Issue 1.2.3: EdgeEnrichmentConfig            🔲 TODO

PHASE 2: Context Pipeline - ALMOST COMPLETE
├── Issue 2.1.1: R0 expanded SELECT              ✅ DONE (lines 525-574)
├── Issue 2.1.2: P03EventState enhancement       ✅ DONE
├── Issue 2.2.1: EpisodeCluster enhancement      ✅ DONE
├── Issue 2.2.2: R2 member contexts              ✅ DONE (lines 1152-1163)
├── Issue 2.3.1: R4 context reception            🔲 TODO (needs entity-to-context map)
├── Issue 2.4.1: TemporalParser anchor fix       🔲 TODO
├── Issue 2.4.2: Episode member_timestamps       🔲 TODO
└── Issue 2.4.3: Prospective anchor fields       🔲 TODO

PHASE 3: Algorithms - MAIN REMAINING WORK
├── Issue 3.0.1: Shared definitions/fusion       🔲 TODO
├── Issue 3.0.2: Thresholds & calibration        🔲 TODO
├── Issue 3.1.1: Semantic similarity             🔲 TODO
├── Issue 3.2.1: Temporal proximity              🔲 TODO
├── Issue 3.3.1: Contextual edges                🔲 TODO
├── Issue 3.4.1: Transitive closure              🔲 TODO
├── Issue 3.5.1: Bayesian causal                 🔲 TODO
└── Issue 3.6.1: Weight normalization            🔲 TODO

PHASE 4: Output Pipeline - PARTIALLY COMPLETE
├── Issue 4.0.1: Wiring mapping checklist        🔲 TODO
├── Issue 4.0.2: Syscall/capability validation   🔲 TODO
├── Issue 4.1.1: R4 enricher integration         🔲 TODO
├── Issue 4.1.2: R4Output update                 🔲 TODO
├── Issue 4.2.1: KGWriteAssembler update         🔲 TODO
├── Issue 4.2.2: StagedWrite update              🔲 TODO
├── Issue 4.3.1: KGLayerWriter update            🔲 TODO (needs new columns)
└── Issue 4.3.2: ObservationRecorder             ✅ DONE

PHASE 5: Testing
├── Issue 5.1.x: Unit tests                      🔲 TODO
├── Issue 5.2.x: Integration tests               🔲 TODO
└── Issue 5.3.x: Performance validation          🔲 TODO
```

## Recommended Next Steps

1. **R4 Context Reception** (Issue 2.3.1):
   - Add `_build_entity_context_map()` method to R4KGConsolidator
   - This enables all 6 enrichment algorithms to access context

2. **Schema Migrations**:
   - Create 0069: st_kg_edges.source_algorithm
   - Create 0070: st_kg_edges evidence columns

3. **Enhance Data Structures**:
   - Add source_algorithm to KGEdge dataclass
   - Create EdgeEnrichmentConfig

4. **Implement Algorithms** (Main Work):
   - Start with temporal_proximity (simplest)
   - Then semantic_similarity, contextual
   - Then transitive_closure, bayesian_causal
   - Finally weight_normalization

5. **Wire into R4**:
   - Integrate enrichers into R4KGConsolidator
   - Update output pipeline

---

# Effort Summary

| Category | Total Issues | Done | Partial | TODO |
|----------|-------------|------|---------|------|
| Foundation (Schema) | 3 | 1 | 0 | 2 |
| Foundation (Data) | 3 | 1 | 1 | 1 |
| Context Pipeline | 5 | 4 | 0 | 1 |
| Algorithms | 12 | 0 | 0 | 12 |
| Output Pipeline | 6 | 1 | 1 | 4 |
| Testing | 6 | 0 | 0 | 6 |
| **TOTAL** | **35** | **7** | **2** | **26** |

**Work Reduction**: ~26% of planned work is already complete. The main remaining effort is:

- 1 R4 enhancement (entity-to-context mapping)
- 2 schema migrations (source_algorithm, evidence columns)
- 12 algorithm implementations + tests (6 algorithms × 2)
- 4 output pipeline updates
- 6 test suites

---

# Blockers & Dependencies

| Blocker | Status | Resolution |
|---------|--------|------------|
| P08 embedding search syscall | Available | Use `union_index_search` |
| st_kg_edges schema access | Available | PostgreSQL migration complete |
| FAISS index availability | Available | P08 v1.0+ |

---

# Success Criteria

1. **Functional**: All 6 enrichment algorithms produce edges correctly
2. **Context**: Full observation context flows from st_hipp_events → st_observations
3. **Provenance**: Every edge has `source_algorithm` set
4. **Performance**: Full R4 cycle <2000ms at production scale
5. **Testing**: >90% code coverage on new code
6. **Zero Regression**: Existing R4 logic (entity extraction, Granger) unchanged

---

# References

- [temporal_fix.md](./temporal_fix.md) - Holistic context flow design
- [GAP_007_ALGORITHM_MATH_TUNING_SKELETON.md](../TEMP_EXECUTION_DOCS/GAP_007_ALGORITHM_MATH_TUNING_SKELETON.md) - Algorithm math
- [GAP_007_WIRING_EXECUTION_SKELETON.md](../TEMP_EXECUTION_DOCS/GAP_007_WIRING_EXECUTION_SKELETON.md) - Wiring spec
- [P03_consolidation_dossier_v2.md](../pipelines/P03_consolidation_dossier_v2.md) - P03 pipeline spec
