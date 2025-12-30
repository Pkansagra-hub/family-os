# P03 Consolidation Envelope Fields Discovery

> **Purpose**: Comprehensive extraction of ALL envelope fields from P03_consolidation_dossier_v2.md (27,978 lines)
> **Source**: Systematic line-by-line reading of entire dossier
> **Created**: 2025-01-XX
> **Status**: Complete - Ready for envelope design

---

## Table of Contents

1. [Batch-Level Fields](#1-batch-level-fields)
2. [Per-Event Fields](#2-per-event-fields)
3. [Per-Phase Output Fields (R0-R8)](#3-per-phase-output-fields-r0-r8)
4. [Truth Layer Write Fields (8 Layers)](#4-truth-layer-write-fields-8-layers)
5. [Learning System Fields](#5-learning-system-fields)
6. [Algorithm Parameter Fields](#6-algorithm-parameter-fields)
7. [Observability Fields](#7-observability-fields)
8. [Module Interface Contracts](#8-module-interface-contracts)
9. [Configuration Fields](#9-configuration-fields)
10. [Event Topic Payloads](#10-event-topic-payloads)
11. [Reconciliation Decision Fields](#11-reconciliation-decision-fields)
12. [Active Learning Integration Fields](#12-active-learning-integration-fields)
13. [Error Handling Fields](#13-error-handling-fields)

---

## 1. Batch-Level Fields

*Fields that apply to the entire consolidation cycle (one per batch)*

### 1.1 Cycle Identification

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `cycle_id` | str (ULID) | R0 | Unique identifier for this consolidation cycle |
| `batch_id` | str | R0 | SHA256(sorted(event_ids))[:16] |
| `tenant_id` | str | Input | Multi-tenant isolation |
| `space_id` | str | Input | User/family space identifier |
| `trace_id` | str | Input | Distributed tracing identifier |

### 1.2 Cycle Timing

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `started_at` | int | R0 | Unix timestamp (ms) cycle start |
| `completed_at` | int | R8 | Unix timestamp (ms) cycle end |
| `duration_ms` | int | R8 | Total cycle duration |
| `trigger_type` | str | Input | "INTERVAL" / "THRESHOLD" / "MANUAL" / "IDLE" |
| `trigger_reason` | str | Input | Human-readable trigger description |

### 1.3 Batch Metadata

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `batch_size` | int | R0 | Number of events in this batch |
| `max_batch_size` | int | Config | Configured maximum (default: 1000) |
| `event_ids` | List[str] | R0 | ULIDs of events being consolidated |
| `pending_count` | int | R0 | Total pending events before selection |
| `backlog_ratio` | float | R0 | pending_count / max_batch_size |

### 1.4 Scheduler Context

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `scheduler_token` | str | K0 Scheduler | QoS scheduler token |
| `qos_band` | str | K0 | "GREEN" / "AMBER" / "RED" |
| `priority` | int | Config | Batch priority (0-100) |
| `deadline_ms` | int | Config | Hard deadline for cycle completion |

---

## 2. Per-Event Fields

*Fields attached to each event within the batch*

### 2.1 Event Identification

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `event_id` | str (ULID) | P02 | Original event identifier |
| `hipp_event_id` | str | st_hipp_events | Hippocampal staging ID |
| `original_message_id` | str | P02 | Source message from ingestion |
| `content_hash` | str | P02 | SHA256 of content for dedup |
| `simhash_hex` | str | P02 | SimHash fingerprint (64-bit) |

### 2.2 Event Content (from P02)

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `content_text` | str | P02 | Original text content |
| `content_type` | str | P02 | "CHAT" / "VOICE" / "CALENDAR" / "TRANSACTION" |
| `source_type` | str | P02 | "manual" / "inferred" / "imported" |
| `channel_id` | str | P02 | Communication channel identifier |
| `timestamp` | int | P02 | Event occurrence time (Unix ms) |

### 2.3 Pre-Computed NLP (from P02/UltraBERT)

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `embedding_768` | List[float] | P02 | 768-dim semantic embedding vector |
| `embedding_id` | str | st_vec | Vector storage reference |
| `sentiment_score` | float | P02 | Polarity score [-1.0, 1.0] |
| `sentiment_label` | str | P02 | "positive" / "negative" / "neutral" |
| `emotions_json` | str | P02 | Multi-label emotion classification |
| `intent_label` | str | P02 | Primary user intent |
| `ner_entities_json` | str | P02 | Named entity recognition results |
| `safety_score` | float | P02 | Content safety classification |
| `temporal_expressions_json` | str | P02 | Extracted time references |

### 2.4 Event Scoring (R1)

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `importance_score` | float | R1 | Computed importance [0.0, 1.0] |
| `recency_factor` | float | R1 | Time-based decay component |
| `affect_factor` | float | R1 | Emotional weight component |
| `social_factor` | float | R1 | Social context weight |
| `novelty_factor` | float | R1 | Information novelty score |
| `importance_factors_json` | str | R1 | Breakdown of all factors |

### 2.5 Clustering Assignment (R2)

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `cluster_id` | str | R2 | Episode cluster assignment |
| `cluster_label` | int | R2 | DBSCAN cluster label (-1 = noise) |
| `is_noise` | bool | R2 | True if not clustered |
| `centroid_distance` | float | R2 | Distance to cluster centroid |
| `temporal_cluster_id` | str | R2 | Time-based grouping |

### 2.6 Reconciliation Decision (R3-R6)

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `reconciliation_action` | str | R3 | "REINFORCE" / "EXTEND" / "CREATE" / "EVOLVE" / "CONTRADICT" / "PRUNE" |
| `best_match_id` | str | R3 | ID of matched truth record |
| `best_match_layer` | str | R3 | Which truth layer matched |
| `similarity_score` | float | R3 | Cosine similarity to best match |
| `confidence` | float | R3 | Reconciliation confidence |
| `reconciliation_reason` | str | R3 | Human-readable decision rationale |
| `version_conflict` | bool | R6 | Optimistic locking conflict detected |
| `prior_version` | int | R6 | Expected version number |

### 2.7 Decay and Pruning (R3)

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `decay_score` | float | R3 | Current decay value [0.0, 1.0] |
| `lambda_decay` | float | R3 | Decay rate parameter |
| `days_since_access` | int | R3 | Days since last retrieval |
| `access_count` | int | R3 | Historical access frequency |
| `prune_decision` | str | R3 | "KEEP" / "ARCHIVE" / "TOMBSTONE" |
| `archive_reason` | str | R3 | Why archived if applicable |

### 2.8 Duplicate Detection (R3)

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `is_duplicate` | bool | R3 | SimHash duplicate detected |
| `duplicate_of_id` | str | R3 | Canonical record if duplicate |
| `hamming_distance` | int | R3 | SimHash Hamming distance |
| `merge_strategy` | str | R3 | "SKIP" / "MERGE" / "SUPERSEDE" |

---

## 3. Per-Phase Output Fields (R0-R8)

*Envelope enrichment at each pipeline phase*

### 3.1 R0 Output (Batch Selection)

```python
@dataclass
class R0Output:
    cycle_id: str                    # ULID
    batch_id: str                    # SHA256 hash[:16]
    event_ids: List[str]             # Selected event ULIDs
    batch_size: int                  # Number of events
    started_at: int                  # Unix ms timestamp
    pending_remaining: int           # Events still pending
    selection_strategy: str          # "FIFO" / "PRIORITY" / "ADAPTIVE"
```

### 3.2 R1 Output (Importance Scoring)

```python
@dataclass
class R1Output:
    scored_events: List[ScoredEvent]           # Events with importance scores
    hebbian_updates: List[HebbianEdgeUpdate]   # Co-occurrence edge updates
    total_importance: float                     # Sum of all scores
    avg_importance: float                       # Mean importance
    max_importance: float                       # Highest scoring event
    importance_distribution: Dict[str, int]     # Histogram buckets
```

```python
@dataclass
class ScoredEvent:
    event_id: str
    importance_score: float
    recency_factor: float
    affect_factor: float
    social_factor: float
    novelty_factor: float
    raw_factors_json: str
```

```python
@dataclass
class HebbianEdgeUpdate:
    source_entity_id: str
    target_entity_id: str
    old_weight: float
    new_weight: float
    delta: float
    update_type: str  # "STRENGTHEN" / "DECAY" / "CREATE"
```

### 3.3 R2 Output (Episodic Clustering)

```python
@dataclass
class R2Output:
    clusters: List[EpisodeCluster]
    noise_events: List[str]          # Event IDs not clustered
    cluster_count: int
    avg_cluster_size: float
    max_cluster_size: int
    temporal_spans: List[Tuple[int, int]]  # Start/end times
```

```python
@dataclass
class EpisodeCluster:
    cluster_id: str                  # ULID
    member_event_ids: List[str]
    centroid_embedding: List[float]  # 768-dim
    centroid_embedding_id: str       # st_vec reference
    dominant_sentiment: float
    temporal_start: int
    temporal_end: int
    location_hint: str
    participants_json: str
    activity_type: str
    cohesion_score: float            # Intra-cluster similarity
```

### 3.4 R3 Output (Forgetting/Pruning)

```python
@dataclass
class R3Output:
    dedup_merges: List[DedupMerge]
    decay_updates: List[DecayUpdate]
    archive_candidates: List[str]    # Record IDs to archive
    prune_candidates: List[str]      # Record IDs to tombstone
    novelty_scores: Dict[str, float]
    resurrection_candidates: List[str]  # Previously pruned, now relevant
```

```python
@dataclass
class DedupMerge:
    duplicate_id: str
    canonical_id: str
    hamming_distance: int
    merge_confidence: float
    content_type: str
```

```python
@dataclass
class DecayUpdate:
    record_id: str
    record_layer: str
    old_decay: float
    new_decay: float
    lambda_used: float
    days_since_access: int
    access_count: int
    decision: str  # "ACTIVE" / "ARCHIVE" / "TOMBSTONE"
```

### 3.5 R4 Output (Knowledge Graph)

```python
@dataclass
class R4Output:
    new_entities: List[KGEntity]
    updated_entities: List[KGEntityUpdate]
    new_edges: List[KGEdge]
    updated_edges: List[KGEdgeUpdate]
    causal_edges: List[CausalEdge]
    gap_candidates: List[GapCandidate]
    entity_merge_decisions: List[EntityMerge]
```

```python
@dataclass
class KGEntity:
    entity_id: str                   # ULID
    canonical_name: str
    entity_type: str                 # "PERSON" / "LOCATION" / "ORG" / "EVENT"
    aliases_json: str
    confidence: float
    first_seen_ts: int
    source_event_ids: List[str]
    embedding_id: str
```

```python
@dataclass
class KGEdge:
    edge_id: str                     # ULID
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    weight: float
    confidence: float
    evidence_event_ids: List[str]
    temporal_start: int
    temporal_end: int
    is_causal: bool
```

```python
@dataclass
class CausalEdge:
    cause_entity_id: str
    effect_entity_id: str
    lag_days: int
    granger_p_value: float
    effect_size: float
    confidence: float
```

```python
@dataclass
class GapCandidate:
    gap_id: str
    gap_type: str  # "AMBIGUITY" / "CONTRADICTION" / "LOW_CONFIDENCE" / "MISSING_INFO"
    related_entity_id: str
    entropy_score: float
    priority: str  # "HIGH" / "MEDIUM" / "LOW"
    context_json: str
    candidate_values: List[str]
```

### 3.6 R5 Output (Dream Exploration)

```python
@dataclass
class R5Output:
    counterfactuals: List[CounterfactualScenario]
    insights: List[Insight]
    routine_optimizations: List[RoutineOptimization]
    prospective_memories: List[ProspectiveMemory]
    skipped: bool
    skip_reason: Optional[str]
```

```python
@dataclass
class CounterfactualScenario:
    scenario_id: str
    base_episode_id: str
    perturbation_type: str
    perturbation_target: str
    original_outcome: str
    counterfactual_outcome: str
    probability_shift: float
    utility_delta: float
    causal_mechanism: str
```

```python
@dataclass
class Insight:
    insight_id: str
    insight_type: str  # "BRIDGE" / "PATTERN" / "ANOMALY" / "PREDICTION"
    concept_a_id: str
    concept_b_id: str
    pmi_score: float
    novelty_score: float
    relevance_score: float
    natural_language: str
    evidence_ids: List[str]
```

```python
@dataclass
class RoutineOptimization:
    routine_id: str
    bottleneck_step: str
    bottleneck_position: int
    value_drop: float
    suggested_action: str
    expected_improvement: float
```

```python
@dataclass
class ProspectiveMemory:
    prosp_id: str
    intention_type: str
    trigger_condition: str
    action_to_take: str
    deadline_ts: int
    importance: float
    source_episode_id: str
```

### 3.7 R6 Output (Status Staging)

```python
@dataclass
class R6Output:
    staged_event_updates: List[EventStatusUpdate]
    staged_truth_writes: List[TruthWrite]
    staged_kg_writes: List[KGWrite]
    staged_outbox_events: List[OutboxEvent]
    reconciliation_summary: ReconciliationSummary
    version_conflicts: List[VersionConflict]
```

```python
@dataclass
class EventStatusUpdate:
    event_id: str
    old_status: str
    new_status: str
    expected_version: int
    new_version: int
```

```python
@dataclass
class TruthWrite:
    layer: str  # "st_epi" / "st_sem" / etc.
    operation: str  # "INSERT" / "UPDATE" / "ARCHIVE" / "TOMBSTONE"
    record_id: str
    record_data_json: str
    idempotency_key: str
```

```python
@dataclass
class ReconciliationSummary:
    reinforce_count: int
    extend_count: int
    create_count: int
    evolve_count: int
    contradict_count: int
    prune_count: int
    skip_count: int
    total_processed: int
```

### 3.8 R7 Output (Memory Writing)

```python
@dataclass
class R7Output:
    records_written: int
    records_failed: int
    tables_touched: Set[str]
    transaction_id: str
    duration_ms: int
    bytes_written: int
    write_manifest: List[WriteResult]
```

```python
@dataclass
class WriteResult:
    table: str
    record_id: str
    operation: str
    success: bool
    error_message: Optional[str]
    rows_affected: int
    new_version: int
```

### 3.9 R8 Output (Event Emission)

```python
@dataclass
class R8Output:
    events_emitted: int
    gaps_detected: int
    topics_published: List[str]
    outbox_entries_marked: int
    cycle_completed: bool
    cycle_duration_ms: int
    next_cycle_eta: Optional[int]
    cycle_summary: CycleSummary
```

```python
@dataclass
class CycleSummary:
    cycle_id: str
    events_processed: int
    episodes_created: int
    patterns_discovered: int
    kg_entities_added: int
    kg_edges_added: int
    gaps_detected: int
    r5_insights_generated: int
    prune_count: int
    error_count: int
    duration_ms: int
```

---

## 4. Truth Layer Write Fields (8 Layers)

*Complete schema for each truth layer written by P03*

### 4.1 st_epi (Episodic Memory)

| Column | Type | Description |
|--------|------|-------------|
| `epi_id` | ULID | Primary key |
| `tenant_id` | str | Multi-tenant isolation |
| `space_id` | str | User space |
| `title` | str | Episode title (generated or extracted) |
| `summary` | str | Episode summary text |
| `start_time` | int | Episode start (Unix ms) |
| `end_time` | int | Episode end (Unix ms) |
| `location_name` | str | Primary location |
| `location_geo_json` | str | GeoJSON if available |
| `participants_json` | str | List of participant entity IDs |
| `activity_type` | str | Activity classification |
| `dominant_sentiment` | float | Aggregated sentiment |
| `dominant_emotion` | str | Primary emotion label |
| `importance` | float | Episode importance score |
| `confidence` | float | Reconstruction confidence |
| `decay` | float | Current decay value |
| `access_count` | int | Retrieval count |
| `last_accessed_ts` | int | Last retrieval time |
| `source_event_ids_json` | str | Contributing event IDs |
| `centroid_embedding_id` | str | st_vec reference |
| `version` | int | Optimistic locking |
| `is_archived` | bool | Archive flag |
| `supersedes_id` | str | Previous version ID |
| `reconstructed_fields_json` | str | Fields filled by R5 |
| `created_at` | int | Creation timestamp |
| `updated_at` | int | Last update timestamp |

### 4.2 st_sem (Semantic Patterns)

| Column | Type | Description |
|--------|------|-------------|
| `sem_id` | ULID | Primary key |
| `tenant_id` | str | Multi-tenant isolation |
| `space_id` | str | User space |
| `pattern_type` | str | "ROUTINE" / "PREFERENCE" / "BELIEF" / "FACT" |
| `pattern_text` | str | Natural language pattern |
| `pattern_embedding_id` | str | st_vec reference |
| `confidence` | float | Pattern confidence |
| `frequency` | int | Observation count |
| `first_observed_ts` | int | First occurrence |
| `last_observed_ts` | int | Most recent occurrence |
| `supporting_episode_ids_json` | str | Evidence episodes |
| `decay` | float | Current decay |
| `is_canonical` | bool | Is primary truth |
| `supersedes_id` | str | Previous version |
| `contradicts_json` | str | Contradicting pattern IDs |
| `version` | int | Optimistic locking |
| `created_at` | int | Creation timestamp |
| `updated_at` | int | Last update timestamp |

### 4.3 st_procedural (Habits/Routines)

| Column | Type | Description |
|--------|------|-------------|
| `proc_id` | ULID | Primary key |
| `tenant_id` | str | Multi-tenant isolation |
| `space_id` | str | User space |
| `routine_name` | str | Routine identifier |
| `routine_description` | str | Human description |
| `trigger_conditions_json` | str | When routine activates |
| `action_sequence_json` | str | Ordered steps |
| `avg_duration_minutes` | float | Typical duration |
| `frequency_per_week` | float | Execution frequency |
| `last_executed_ts` | int | Most recent execution |
| `success_rate` | float | Completion rate |
| `importance` | float | Routine importance |
| `decay` | float | Current decay |
| `optimization_suggestions_json` | str | R5 improvements |
| `bottleneck_steps_json` | str | TDL-HCO identified |
| `value_function_json` | str | V(s) per step |
| `version` | int | Optimistic locking |
| `created_at` | int | Creation timestamp |
| `updated_at` | int | Last update timestamp |

### 4.4 st_social (Social Relationships)

| Column | Type | Description |
|--------|------|-------------|
| `social_id` | ULID | Primary key |
| `tenant_id` | str | Multi-tenant isolation |
| `space_id` | str | User space |
| `person_entity_id` | str | st_kg_dom reference |
| `relationship_type` | str | "FAMILY" / "FRIEND" / "COLLEAGUE" / etc. |
| `relationship_strength` | float | Closeness score [0,1] |
| `interaction_frequency` | float | Interactions per week |
| `last_interaction_ts` | int | Most recent contact |
| `sentiment_history_json` | str | Sentiment over time |
| `shared_activities_json` | str | Common activities |
| `communication_channels_json` | str | How they communicate |
| `decay` | float | Relationship decay |
| `version` | int | Optimistic locking |
| `created_at` | int | Creation timestamp |
| `updated_at` | int | Last update timestamp |

### 4.5 st_prospective (Intentions/Goals)

| Column | Type | Description |
|--------|------|-------------|
| `prosp_id` | ULID | Primary key |
| `tenant_id` | str | Multi-tenant isolation |
| `space_id` | str | User space |
| `intention_type` | str | "GOAL" / "REMINDER" / "DEADLINE" / "WISH" |
| `description` | str | What to remember |
| `trigger_condition` | str | When to surface |
| `trigger_location` | str | Where to surface |
| `trigger_person` | str | Who triggers |
| `action_to_take` | str | What to do |
| `deadline_ts` | int | Optional deadline |
| `importance` | float | Priority score |
| `status` | str | "PENDING" / "COMPLETED" / "EXPIRED" |
| `source_episode_id` | str | Origin episode |
| `created_by` | str | "USER" / "INFERRED" |
| `confidence` | float | If inferred |
| `version` | int | Optimistic locking |
| `created_at` | int | Creation timestamp |
| `updated_at` | int | Last update timestamp |

### 4.6 st_kg_dom (Knowledge Graph Entities)

| Column | Type | Description |
|--------|------|-------------|
| `entity_id` | ULID | Primary key |
| `tenant_id` | str | Multi-tenant isolation |
| `canonical_name` | str | Normalized name |
| `display_name` | str | Preferred display |
| `entity_type` | str | "PERSON" / "LOCATION" / "ORG" / "THING" / "EVENT" |
| `entity_subtype` | str | More specific type |
| `aliases_json` | str | Alternative names |
| `attributes_json` | str | Key-value properties |
| `embedding_id` | str | st_vec reference |
| `confidence` | float | Entity confidence |
| `is_canonical` | bool | Primary vs alias |
| `canonical_entity_id` | str | If alias, points to canonical |
| `first_seen_ts` | int | First mention |
| `last_seen_ts` | int | Most recent mention |
| `mention_count` | int | Total references |
| `source_event_ids_json` | str | Evidence events |
| `decay` | float | Entity decay |
| `version` | int | Optimistic locking |
| `created_at` | int | Creation timestamp |
| `updated_at` | int | Last update timestamp |

### 4.7 st_kg_edges (Knowledge Graph Relationships)

| Column | Type | Description |
|--------|------|-------------|
| `edge_id` | ULID | Primary key |
| `tenant_id` | str | Multi-tenant isolation |
| `source_entity_id` | str | st_kg_dom reference |
| `target_entity_id` | str | st_kg_dom reference |
| `relationship_type` | str | Edge type label |
| `relationship_subtype` | str | More specific type |
| `weight` | float | Edge strength [0,1] |
| `confidence` | float | Relationship confidence |
| `is_causal` | bool | Causal relationship |
| `causal_direction` | str | "FORWARD" / "BIDIRECTIONAL" |
| `lag_days` | int | Causal lag if applicable |
| `granger_p_value` | float | Statistical significance |
| `evidence_event_ids_json` | str | Supporting events |
| `temporal_start` | int | Relationship start |
| `temporal_end` | int | Relationship end (null = ongoing) |
| `hebbian_weight` | float | Co-occurrence learning weight |
| `decay` | float | Edge decay |
| `version` | int | Optimistic locking |
| `created_at` | int | Creation timestamp |
| `updated_at` | int | Last update timestamp |

### 4.8 st_vec (Embedding Vectors)

| Column | Type | Description |
|--------|------|-------------|
| `vec_id` | ULID | Primary key |
| `tenant_id` | str | Multi-tenant isolation |
| `space_id` | str | User space |
| `source_type` | str | "EVENT" / "EPISODE" / "PATTERN" / "ENTITY" |
| `source_id` | str | Reference to source record |
| `embedding_model` | str | "ultrabert-v2.2.1" |
| `embedding_dim` | int | 768 |
| `embedding_vector` | vector(768) | The actual embedding |
| `normalized` | bool | L2 normalized |
| `created_at` | int | Creation timestamp |

---

## 5. Learning System Fields

*Fields for adaptive learning and calibration*

### 5.1 Thompson Sampling Priors

| Field | Type | Description |
|-------|------|-------------|
| `threshold_name` | str | "reinforce" / "extend_lower" |
| `alpha` | int | Beta distribution α parameter |
| `beta` | int | Beta distribution β parameter |
| `target` | float | Target threshold value |
| `effective_samples` | int | α + β |
| `current_mean` | float | α / (α + β) |

### 5.2 Hebbian Learning

| Field | Type | Description |
|-------|------|-------------|
| `learning_rate` | float | Default 0.1 |
| `decay_rate` | float | Default 0.01 |
| `max_weight` | float | Default 1.0 |
| `min_weight` | float | Default 0.01 |
| `saturation_threshold` | float | Default 0.95 |
| `anti_hebbian_penalty` | float | -0.15 to -0.4 |

### 5.3 Importance Weight Learning

| Field | Type | Description |
|-------|------|-------------|
| `sentiment_weight` | float | Default 0.25 |
| `affect_weight` | float | Default 0.30 |
| `novelty_weight` | float | Default 0.25 |
| `social_weight` | float | Default 0.20 |
| `learning_rate` | float | Default 0.01 |
| `l2_reg` | float | Default 0.001 |

### 5.4 Bayesian Lambda Estimation

| Field | Type | Description |
|-------|------|-------------|
| `entity_type` | str | Entity type for λ lookup |
| `prior_alpha` | float | Gamma prior α |
| `prior_beta` | float | Gamma prior β |
| `posterior_alpha` | float | Updated α |
| `posterior_beta` | float | Updated β |
| `map_lambda` | float | Maximum a posteriori λ |
| `ci_lower` | float | 90% credible interval lower |
| `ci_upper` | float | 90% credible interval upper |

### 5.5 Adaptive SimHash Thresholds

| Field | Type | Description |
|-------|------|-------------|
| `content_type` | str | Content type for threshold |
| `current_threshold` | int | Current Hamming threshold |
| `false_positive_rate` | float | Observed FP rate |
| `false_negative_rate` | float | Observed FN rate |
| `learning_rate` | float | Default 0.1 |

---

## 6. Algorithm Parameter Fields

*Configuration for all P03 algorithms*

### 6.1 DBSCAN Clustering

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `eps` | float | 0.25 | Epsilon neighborhood radius |
| `min_samples` | int | 2 | Minimum cluster size |
| `temporal_weight` | float | 0.3 | Weight for temporal distance |
| `max_temporal_gap_hours` | float | 4.0 | Max gap within episode |
| `min_samples_base` | int | 2 | Base min_samples |
| `min_samples_per_10_events` | int | 1 | Scaling factor |

### 6.2 SimHash Deduplication

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hash_bits` | int | 64 | SimHash bit length |
| `default_threshold` | int | 3 | Default Hamming threshold |
| `transaction_threshold` | int | 1 | For TRANSACTION content |
| `calendar_threshold` | int | 2 | For CALENDAR content |
| `chat_threshold` | int | 3 | For CHAT content |
| `voice_threshold` | int | 5 | For VOICE content |

### 6.3 Exponential Decay

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `base_lambda` | float | 0.01 | Default decay rate |
| `prune_threshold` | float | 0.01 | Threshold for tombstone |
| `archive_threshold` | float | 0.10 | Threshold for archive |
| `active_threshold` | float | 0.30 | Threshold for active |
| `resurrection_weight` | float | 0.7 | Base weight after resurrection |

### 6.4 Granger Causality

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_lag_days` | int | 7 | Maximum lag to test |
| `significance_level` | float | 0.05 | p-value threshold |
| `min_observations` | int | 20 | Minimum data points |

### 6.5 TPN-MCTS (Forward Simulation)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_simulations` | int | 100 | MCTS iterations |
| `exploration_constant` | float | 1.414 | UCT exploration |
| `max_depth` | int | 5 | Simulation depth |
| `dpp_lambda` | float | 0.5 | Diversity weight |

### 6.6 BGT-SM (Insight Generation)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `pmi_threshold` | float | 3.0 | Minimum PMI for bridge |
| `max_hops` | int | 3 | Graph traversal depth |
| `diversity_weight` | float | 0.4 | Exploration preference |
| `min_novelty` | float | 0.5 | Minimum novelty score |

### 6.7 TDL-HCO (Motor Rehearsal)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `learning_rate` | float | 0.3 | TD learning rate α |
| `discount_factor` | float | 0.95 | Future reward discount γ |
| `bottleneck_threshold` | float | -2.0 | Value drop for bottleneck |

---

## 7. Observability Fields

*Metrics, traces, and logging context*

### 7.1 Metrics Fields

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `p03_cycles_total` | counter | status | Total cycles |
| `p03_events_processed_total` | counter | decision_type | Events by decision |
| `p03_episodes_created_total` | counter | - | Episodes created |
| `p03_patterns_discovered_total` | counter | pattern_type | Patterns found |
| `p03_kg_entities_total` | counter | entity_type | Entities created |
| `p03_kg_edges_total` | counter | edge_type | Edges created |
| `p03_gaps_detected_total` | counter | gap_type | P06 gaps |
| `p03_prune_total` | counter | action | Prune/archive |
| `p03_errors_total` | counter | error_type | Errors |
| `p03_cycle_duration_seconds` | histogram | - | Cycle duration |
| `p03_phase_duration_seconds` | histogram | phase | Per-phase duration |
| `p03_batch_size` | histogram | - | Batch size distribution |
| `p03_pending_events` | gauge | - | Pending count |
| `p03_similarity_score` | histogram | decision_type | Similarity distribution |
| `p03_confidence_score` | histogram | layer | Confidence distribution |

### 7.2 Tracing Context

| Field | Type | Description |
|-------|------|-------------|
| `trace_id` | str | Distributed trace identifier |
| `span_id` | str | Current span identifier |
| `parent_span_id` | str | Parent span |
| `operation_name` | str | "p03.consolidation.cycle" |
| `phase` | str | "R0" through "R8" |
| `stage_id` | str | Pipeline stage identifier |

### 7.3 Log Context

| Field | Type | Description |
|-------|------|-------------|
| `pipeline_id` | str | "P03_CONSOLIDATE" |
| `module_id` | str | Current module |
| `cycle_id` | str | Cycle ULID |
| `phase` | str | R0-R8 |
| `stage_id` | str | Stage identifier |
| `tenant_id` | str | Tenant |
| `space_id` | str | Space |
| `trace_id` | str | Trace ID |
| `level` | str | "DEBUG" / "INFO" / "WARN" / "ERROR" |
| `timestamp` | str | ISO8601 timestamp |

---

## 8. Module Interface Contracts

*Input/Output for each P03 module*

### 8.1 M18 EpisodicClusterer

```python
@dataclass
class EpisodicClustererInput:
    scored_events: List[ScoredEvent]
    existing_episodes: List[EpisodeRef]  # For merge detection
    config: DBSCANConfig

@dataclass
class EpisodicClustererOutput:
    clusters: List[EpisodeCluster]
    noise_events: List[str]
    merge_candidates: List[Tuple[str, str]]
```

### 8.2 M19 DuplicateDetector

```python
@dataclass
class DuplicateDetectorInput:
    events: List[EventWithSimHash]
    content_type_thresholds: Dict[str, int]

@dataclass
class DuplicateDetectorOutput:
    duplicates: List[DedupMerge]
    unique_events: List[str]
    duplicate_groups: Dict[str, List[str]]
```

### 8.3 M20 RetentionEnforcer

```python
@dataclass
class RetentionEnforcerInput:
    records: List[DecayableRecord]
    retention_policies: Dict[str, RetentionPolicy]
    resurrection_queue: List[str]

@dataclass
class RetentionEnforcerOutput:
    active: List[str]
    archive: List[str]
    tombstone: List[str]
    resurrect: List[str]
```

### 8.4 M21 KGConsolidator

```python
@dataclass
class KGConsolidatorInput:
    episodes: List[EpisodeCluster]
    extracted_entities: List[NERResult]
    existing_entities: List[KGEntityRef]
    existing_edges: List[KGEdgeRef]

@dataclass
class KGConsolidatorOutput:
    new_entities: List[KGEntity]
    updated_entities: List[KGEntityUpdate]
    new_edges: List[KGEdge]
    updated_edges: List[KGEdgeUpdate]
    merges: List[EntityMerge]
```

### 8.5 M22 DreamExplorer

```python
@dataclass
class DreamExplorerInput:
    episodes: List[EpisodeCluster]
    kg_snapshot: KGSnapshot
    routines: List[ProceduralMemory]
    config: DreamConfig

@dataclass
class DreamExplorerOutput:
    counterfactuals: List[CounterfactualScenario]
    insights: List[Insight]
    optimizations: List[RoutineOptimization]
    prospective: List[ProspectiveMemory]
```

### 8.6 M23 ReplayCoordinator

```python
@dataclass
class ReplayCoordinatorInput:
    events: List[HippEvent]
    hebbian_config: HebbianConfig
    importance_weights: ImportanceWeights

@dataclass
class ReplayCoordinatorOutput:
    scored_events: List[ScoredEvent]
    edge_updates: List[HebbianEdgeUpdate]
    importance_stats: ImportanceStats
```

### 8.7 M24 TruthWriter

```python
@dataclass
class TruthWriterInput:
    staged_writes: List[TruthWrite]
    staged_kg_writes: List[KGWrite]
    staged_event_updates: List[EventStatusUpdate]
    staged_outbox: List[OutboxEvent]

@dataclass
class TruthWriterOutput:
    write_results: List[WriteResult]
    transaction_id: str
    success: bool
    error_details: Optional[str]
```

### 8.8 M25 GapDetector

```python
@dataclass
class GapDetectorInput:
    entities: List[KGEntity]
    edges: List[KGEdge]
    patterns: List[SemanticPattern]
    entropy_threshold: float

@dataclass
class GapDetectorOutput:
    gaps: List[GapCandidate]
    questions: List[P06Question]
    priority_queue: List[str]
```

---

## 9. Configuration Fields

*All P03 configuration parameters*

### 9.1 Trigger Configuration

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `p03.schedule.enabled` | bool | true | Enable scheduling |
| `p03.schedule.interval_seconds` | int | 5400 | Interval (90 min) |
| `p03.schedule.cron` | str | "0 3 ** *" | Cron expression |
| `p03.trigger.threshold.enabled` | bool | true | Enable threshold trigger |
| `p03.trigger.threshold.pending_count` | int | 500 | Event threshold |

### 9.2 Batch Configuration

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `p03.batch.size` | int | 1000 | Events per cycle |
| `p03.batch.max_events_per_cycle` | int | 10000 | Hard cap |
| `p03.batch.timeout_seconds` | int | 300 | Cycle timeout |
| `p03.batch.selection_strategy` | str | "FIFO" | Selection order |

### 9.3 Reconciliation Thresholds

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `p03.reconciliation.thresholds.reinforce_min` | float | 0.85 | REINFORCE min |
| `p03.reconciliation.thresholds.extend_min` | float | 0.60 | EXTEND min |
| `p03.reconciliation.thresholds.extend_max` | float | 0.85 | EXTEND max |
| `p03.reconciliation.thresholds.contradict` | float | 0.30 | CONTRADICT threshold |
| `p03.reconciliation.thresholds.novelty_min` | float | 0.70 | CREATE novelty min |

### 9.4 Phase Configuration

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `p03.phases.r5_dream.enabled` | bool | true | Enable R5 |
| `p03.phases.r5_dream.skip_on_backlog` | bool | true | Skip if backlogged |
| `p03.phases.r5_dream.backlog_threshold` | int | 5000 | Backlog threshold |
| `p03.phases.r5_dream.timeout_ms` | int | 120000 | R5 timeout |

### 9.5 Active Learning

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `p03.active_learning.enabled` | bool | true | Enable P06 gaps |
| `p03.active_learning.max_gaps_per_cycle` | int | 50 | Gap limit |
| `p03.active_learning.entropy_threshold` | float | 0.50 | Min entropy |

### 9.6 Concurrency

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `p03.concurrency.parallel_workers` | int | 4 | Worker count |
| `p03.concurrency.max_concurrent_cycles` | int | 2 | Max cycles |

---

## 10. Event Topic Payloads

*Schema for each event topic*

### 10.1 P03ConsolidationComplete

```python
@dataclass
class P03ConsolidationComplete:
    cycle_id: str
    tenant_id: str
    space_id: str
    started_at: int
    completed_at: int
    duration_ms: int
    events_processed: int
    episodes_created: int
    patterns_discovered: int
    kg_entities_added: int
    kg_edges_added: int
    gaps_detected: int
    r5_insights_generated: int
    prune_count: int
    error_count: int
```

### 10.2 P03EpisodeFormed

```python
@dataclass
class P03EpisodeFormed:
    episode_id: str
    tenant_id: str
    space_id: str
    title: str
    start_time: int
    end_time: int
    event_count: int
    centroid_embedding_id: str
    dominant_sentiment: float
```

### 10.3 P03GapDetected

```python
@dataclass
class P03GapDetected:
    gap_id: str
    gap_type: str  # "AMBIGUITY" / "CONTRADICTION" / "LOW_CONFIDENCE" / "MISSING_INFO"
    tenant_id: str
    space_id: str
    related_entity_id: str
    entropy_score: float
    priority: str  # "HIGH" / "MEDIUM" / "LOW"
    context_json: str
    candidate_values: List[str]
```

### 10.4 P03PatternDiscovered

```python
@dataclass
class P03PatternDiscovered:
    pattern_id: str
    tenant_id: str
    space_id: str
    pattern_type: str
    pattern_text: str
    confidence: float
    supporting_episode_count: int
```

### 10.5 P03KGUpdated

```python
@dataclass
class P03KGUpdated:
    tenant_id: str
    space_id: str
    entities_added: int
    entities_updated: int
    edges_added: int
    edges_updated: int
    causal_edges_added: int
```

### 10.6 P03InsightGenerated

```python
@dataclass
class P03InsightGenerated:
    insight_id: str
    tenant_id: str
    space_id: str
    insight_type: str
    natural_language: str
    novelty_score: float
    relevance_score: float
```

### 10.7 P03MemoryPruned

```python
@dataclass
class P03MemoryPruned:
    record_id: str
    tenant_id: str
    space_id: str
    layer: str
    action: str  # "ARCHIVE" / "TOMBSTONE"
    decay_at_prune: float
    days_since_access: int
```

### 10.8 P03TruthReinforced / Created / Evolved

```python
@dataclass
class P03TruthEvent:
    record_id: str
    tenant_id: str
    space_id: str
    layer: str
    action: str  # "REINFORCE" / "CREATE" / "EVOLVE"
    old_confidence: Optional[float]
    new_confidence: float
    similarity_score: float
```

---

## 11. Reconciliation Decision Fields

*Fields specific to the 6 reconciliation actions*

### 11.1 REINFORCE Decision

| Field | Type | Description |
|-------|------|-------------|
| `action` | str | "REINFORCE" |
| `matched_record_id` | str | Existing truth record |
| `matched_layer` | str | Truth layer |
| `similarity_score` | float | >= 0.85 |
| `old_confidence` | float | Previous confidence |
| `new_confidence` | float | Boosted confidence |
| `frequency_increment` | int | +1 observation |

### 11.2 EXTEND Decision

| Field | Type | Description |
|-------|------|-------------|
| `action` | str | "EXTEND" |
| `matched_record_id` | str | Base record to extend |
| `matched_layer` | str | Truth layer |
| `similarity_score` | float | 0.60 - 0.85 |
| `extension_type` | str | "DETAIL" / "CONTEXT" / "TEMPORAL" |
| `extended_fields_json` | str | What was added |

### 11.3 CREATE Decision

| Field | Type | Description |
|-------|------|-------------|
| `action` | str | "CREATE" |
| `target_layer` | str | Which layer to write |
| `novelty_score` | float | >= 0.70 |
| `best_match_similarity` | float | < 0.60 |
| `initial_confidence` | float | Starting confidence |

### 11.4 EVOLVE Decision

| Field | Type | Description |
|-------|------|-------------|
| `action` | str | "EVOLVE" |
| `superseded_record_id` | str | Old version |
| `superseded_layer` | str | Truth layer |
| `evolution_type` | str | "CORRECTION" / "UPDATE" / "REFINEMENT" |
| `new_version` | int | Incremented version |
| `changes_json` | str | What changed |

### 11.5 CONTRADICT Decision

| Field | Type | Description |
|-------|------|-------------|
| `action` | str | "CONTRADICT" |
| `conflicting_record_id` | str | Existing conflicting truth |
| `conflicting_layer` | str | Truth layer |
| `contradiction_type` | str | "FACTUAL" / "TEMPORAL" / "RELATIONSHIP" |
| `resolution_strategy` | str | "DEFER" / "USER_QUERY" / "NEWER_WINS" |
| `gap_created` | bool | P06 gap generated |

### 11.6 PRUNE Decision

| Field | Type | Description |
|-------|------|-------------|
| `action` | str | "PRUNE" |
| `prune_type` | str | "ARCHIVE" / "TOMBSTONE" |
| `decay_score` | float | Current decay value |
| `days_since_access` | int | Inactivity period |
| `reason` | str | Why pruned |
| `reversible` | bool | Can be resurrected |

---

## 12. Active Learning Integration Fields

*P06 integration for gap detection and questioning*

### 12.1 st_learning_queue Schema

| Column | Type | Description |
|--------|------|-------------|
| `gap_id` | ULID | Primary key |
| `tenant_id` | str | Multi-tenant |
| `space_id` | str | User space |
| `gap_type` | str | Gap classification |
| `related_entity_id` | str | Entity with gap |
| `entropy_score` | float | Uncertainty measure |
| `priority` | str | "HIGH" / "MEDIUM" / "LOW" |
| `status` | str | "PENDING" / "ASKED" / "RESOLVED" |
| `context_json` | str | Full context |
| `candidate_values_json` | str | Possible answers |
| `question_text` | str | Generated question |
| `created_at` | int | When detected |
| `asked_at` | int | When question asked |
| `resolved_at` | int | When answered |
| `resolution_json` | str | User's answer |

### 12.2 st_anchors Schema

| Column | Type | Description |
|--------|------|-------------|
| `anchor_id` | ULID | Primary key |
| `tenant_id` | str | Multi-tenant |
| `space_id` | str | User space |
| `anchor_type` | str | "ENTITY" / "RELATIONSHIP" / "PATTERN" |
| `canonical_value` | str | Anchored truth |
| `confidence` | float | Current confidence |
| `observation_count` | int | Evidence count |
| `created_at` | int | When anchored |
| `updated_at` | int | Last update |

### 12.3 Feedback Signal Fields

| Field | Type | Description |
|-------|------|-------------|
| `signal_type` | str | "MEMORY_MISS" / "REFORMULATION" / "CORRECTION" / etc. |
| `confidence` | float | Signal confidence |
| `source_query_id` | str | Originating query |
| `related_entity_id` | str | Affected entity |
| `lambda_adjustment` | float | Decay rate change |
| `threshold_update` | float | Threshold change |

---

## 13. Error Handling Fields

*Error recovery and DLQ fields*

### 13.1 DLQ Record

| Field | Type | Description |
|-------|------|-------------|
| `dlq_id` | ULID | Primary key |
| `tenant_id` | str | Multi-tenant |
| `topic` | str | Original topic |
| `payload_json` | str | Full payload |
| `error_type` | str | Error classification |
| `error_message` | str | Error details |
| `stage_id` | str | Failed stage |
| `cycle_id` | str | Cycle context |
| `trace_id` | str | Trace context |
| `attempt_count` | int | Retry attempts |
| `first_failure_ts` | int | Initial failure |
| `last_failure_ts` | int | Most recent failure |
| `next_retry_ts` | int | Scheduled retry |
| `status` | str | "PENDING" / "RETRYING" / "RESOLVED" / "DEAD" |

### 13.2 Retry Scheduling

| Field | Type | Description |
|-------|------|-------------|
| `attempt` | int | Current attempt number |
| `base_delay_ms` | int | Base delay (100) |
| `max_delay_ms` | int | Cap (64000) |
| `jitter_factor` | float | Randomization (0.2) |
| `calculated_delay_ms` | int | Actual delay |
| `next_attempt_ts` | int | When to retry |

### 13.3 Circuit Breaker State

| Field | Type | Description |
|-------|------|-------------|
| `circuit_name` | str | Circuit identifier |
| `state` | str | "CLOSED" / "OPEN" / "HALF_OPEN" |
| `failure_count` | int | Recent failures |
| `success_count` | int | Recent successes |
| `last_failure_ts` | int | Last failure time |
| `open_until_ts` | int | When to try again |
| `half_open_attempts` | int | Test attempts |

---

## Summary Statistics

| Category | Field Count |
|----------|-------------|
| Batch-Level Fields | 18 |
| Per-Event Fields | 42 |
| R0-R8 Phase Outputs | 85+ |
| Truth Layer Columns (8 layers) | 120+ |
| Learning System Fields | 35 |
| Algorithm Parameters | 45 |
| Observability Fields | 30 |
| Module Interface Fields | 64 |
| Configuration Fields | 25 |
| Event Topic Payloads | 55 |
| Reconciliation Decision Fields | 35 |
| Active Learning Fields | 25 |
| Error Handling Fields | 20 |
| **TOTAL** | **~600+ fields** |

---

# PART II: P03 Envelope Architecture Design

> **Status**: Design Specification
> **Based On**: Field discovery from Part I (600+ fields extracted)
> **Pattern**: Batch-oriented envelope with per-event state tracking

---

## 14. Envelope Design Principles

### 14.1 P02 vs P03 Envelope Pattern Comparison

| Aspect | P02 (Write Pipeline) | P03 (Consolidation Pipeline) |
|--------|---------------------|------------------------------|
| **Input** | Single event | Batch of 100-1000 events |
| **Cardinality** | 1:1 (event→envelope) | 1:N (batch→events) |
| **Propagation** | Shallow merge per stage | Nested enrichment |
| **State** | Stateless between events | Stateful across batch |
| **Outputs** | Single record writes | Multi-table atomic writes |
| **Duration** | ~50ms per event | 30-300 seconds per cycle |

### 14.2 Design Constraints

1. **Memory Bound**: Batch of 1000 events × 768-dim embeddings = ~3MB vectors alone
2. **Atomicity**: R7 must commit all writes or none (UnitOfWork pattern)
3. **Idempotency**: Each phase must be retryable with same inputs → same outputs
4. **Observability**: Every field change must be traceable to source phase
5. **Lazy Loading**: Embeddings should be IDs until needed, not materialized

### 14.3 Envelope Hierarchy

```
P03BatchEnvelope (1 per cycle)
├── context: P03CycleContext          # Batch-level metadata
├── events: List[P03EventState]       # Per-event enrichment (N events)
├── phases: P03PhaseOutputs           # Aggregated phase results
├── staged: P03StagedWrites           # Deferred writes for R7
└── observability: P03ObservabilityContext
```

---

## 15. Core Envelope Dataclasses

### 15.1 Top-Level Envelope

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Any
from enum import Enum
import time
import ulid


class P03Phase(Enum):
    """Current phase of the consolidation cycle."""
    R0_INIT = "R0"
    R1_SCORE = "R1"
    R2_CLUSTER = "R2"
    R3_PRUNE = "R3"
    R4_KG = "R4"
    R5_DREAM = "R5"
    R6_STAGE = "R6"
    R7_WRITE = "R7"
    R8_EMIT = "R8"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass
class P03BatchEnvelope:
    """
    Top-level envelope for P03 consolidation pipeline.

    This is the root container that flows through all R0-R8 phases.
    Unlike P02's shallow merge, P03 uses nested enrichment:
    - context: Immutable batch metadata (set in R0)
    - events: Mutable per-event state (enriched R1-R6)
    - phases: Aggregated outputs (populated per phase)
    - staged: Deferred writes (accumulated R1-R6, committed R7)
    """

    # === IMMUTABLE CONTEXT (set in R0) ===
    context: P03CycleContext

    # === MUTABLE PER-EVENT STATE ===
    events: List[P03EventState] = field(default_factory=list)

    # === PHASE OUTPUTS (populated incrementally) ===
    phases: P03PhaseOutputs = field(default_factory=lambda: P03PhaseOutputs())

    # === STAGED WRITES (accumulated, committed in R7) ===
    staged: P03StagedWrites = field(default_factory=lambda: P03StagedWrites())

    # === OBSERVABILITY ===
    observability: P03ObservabilityContext = field(
        default_factory=lambda: P03ObservabilityContext()
    )

    # === STATE TRACKING ===
    current_phase: P03Phase = P03Phase.R0_INIT
    phase_timings: Dict[str, int] = field(default_factory=dict)  # phase → duration_ms
    errors: List[P03Error] = field(default_factory=list)

    def mark_phase_start(self, phase: P03Phase) -> None:
        """Record phase transition."""
        self.current_phase = phase
        self.observability.phase_start_ts[phase.value] = int(time.time() * 1000)

    def mark_phase_complete(self, phase: P03Phase) -> None:
        """Record phase completion with timing."""
        start = self.observability.phase_start_ts.get(phase.value, 0)
        self.phase_timings[phase.value] = int(time.time() * 1000) - start

    def get_event(self, event_id: str) -> Optional[P03EventState]:
        """Lookup event by ID."""
        for event in self.events:
            if event.event_id == event_id:
                return event
        return None

    def get_events_by_cluster(self, cluster_id: str) -> List[P03EventState]:
        """Get all events in a cluster."""
        return [e for e in self.events if e.cluster_id == cluster_id]
```

### 15.2 Cycle Context (Immutable After R0)

```python
@dataclass(frozen=True)
class P03CycleContext:
    """
    Immutable batch-level context set during R0.

    These fields NEVER change after R0 completes.
    Use frozen=True to enforce immutability.
    """

    # === IDENTIFICATION ===
    cycle_id: str                    # ULID, generated in R0
    batch_id: str                    # SHA256(sorted(event_ids))[:16]
    tenant_id: str                   # Multi-tenant isolation
    space_id: str                    # User/family space
    trace_id: str                    # Distributed tracing

    # === TRIGGER CONTEXT ===
    trigger_type: str                # "INTERVAL" / "THRESHOLD" / "MANUAL"
    trigger_reason: str              # Human-readable
    triggered_at: int                # Unix ms when trigger fired

    # === BATCH METADATA ===
    batch_size: int                  # Number of events selected
    event_ids: tuple                 # Immutable tuple of event ULIDs
    pending_before: int              # Pending count before selection

    # === SCHEDULER CONTEXT ===
    scheduler_token: Optional[str] = None
    qos_band: str = "AMBER"
    priority: int = 50
    deadline_ms: int = 300000        # 5 minutes default

    @classmethod
    def create(
        cls,
        tenant_id: str,
        space_id: str,
        event_ids: List[str],
        trigger_type: str = "MANUAL",
        trigger_reason: str = "",
        trace_id: Optional[str] = None,
        pending_before: int = 0,
        scheduler_token: Optional[str] = None,
    ) -> P03CycleContext:
        """Factory method for creating cycle context."""
        sorted_ids = sorted(event_ids)
        import hashlib
        batch_hash = hashlib.sha256(",".join(sorted_ids).encode()).hexdigest()[:16]

        return cls(
            cycle_id=str(ulid.new()),
            batch_id=batch_hash,
            tenant_id=tenant_id,
            space_id=space_id,
            trace_id=trace_id or str(ulid.new()),
            trigger_type=trigger_type,
            trigger_reason=trigger_reason,
            triggered_at=int(time.time() * 1000),
            batch_size=len(event_ids),
            event_ids=tuple(sorted_ids),
            pending_before=pending_before,
            scheduler_token=scheduler_token,
        )
```

---

## 16. Per-Event State Tracking

### 16.1 Event State Dataclass

```python
class ReconciliationAction(Enum):
    """Possible reconciliation decisions for an event."""
    PENDING = "PENDING"           # Not yet decided
    REINFORCE = "REINFORCE"       # Strengthen existing truth (sim >= 0.85)
    EXTEND = "EXTEND"             # Add detail to existing (0.60 <= sim < 0.85)
    CREATE = "CREATE"             # New truth record (sim < 0.60, novelty >= 0.70)
    EVOLVE = "EVOLVE"             # Version existing truth (schema change)
    CONTRADICT = "CONTRADICT"     # Conflicts with existing (flagged for P06)
    PRUNE = "PRUNE"               # Decay below threshold
    SKIP = "SKIP"                 # Duplicate, already processed, or filtered


@dataclass
class P03EventState:
    """
    Per-event state that is enriched as event flows through phases.

    Each event in the batch has one P03EventState instance.
    Fields are populated incrementally by different phases:
    - R0: event_id, hipp_event_id, content fields (from st_hipp_events)
    - R1: importance_score, factors, hebbian_updates
    - R2: cluster_id, cluster assignment
    - R3: reconciliation_action, similarity, dedup, decay
    - R6: staged write references
    """

    # === IDENTIFICATION (R0 - from st_hipp_events) ===
    event_id: str                              # ULID
    hipp_event_id: str                         # st_hipp_events primary key

    # === CONTENT (R0 - from P02 pre-computation) ===
    content_text: str = ""
    content_type: str = ""                     # CHAT/VOICE/CALENDAR/TRANSACTION
    content_hash: str = ""                     # SHA256 for dedup
    simhash_hex: str = ""                      # 64-bit SimHash
    timestamp: int = 0                         # Event occurrence time
    channel_id: str = ""

    # === PRE-COMPUTED NLP (R0 - from P02/UltraBERT) ===
    embedding_id: str = ""                     # st_vec reference (lazy load)
    embedding_768: Optional[List[float]] = None  # Materialized when needed
    sentiment_score: float = 0.0
    sentiment_label: str = "neutral"
    emotions_json: str = "{}"
    intent_label: str = ""
    ner_entities_json: str = "[]"
    temporal_expressions_json: str = "[]"

    # === IMPORTANCE SCORING (R1) ===
    importance_score: float = 0.0              # Computed importance [0, 1]
    recency_factor: float = 0.0
    affect_factor: float = 0.0
    social_factor: float = 0.0
    novelty_factor: float = 0.0
    importance_computed: bool = False

    # === HEBBIAN UPDATES (R1) ===
    hebbian_updates: List[Dict[str, Any]] = field(default_factory=list)

    # === CLUSTERING (R2) ===
    cluster_id: Optional[str] = None           # Episode cluster assignment
    cluster_label: int = -1                    # DBSCAN label (-1 = noise)
    is_noise: bool = False
    centroid_distance: float = 0.0

    # === RECONCILIATION DECISION (R3) ===
    reconciliation_action: ReconciliationAction = ReconciliationAction.PENDING
    best_match_id: Optional[str] = None        # Matched truth record
    best_match_layer: Optional[str] = None     # st_epi, st_sem, etc.
    similarity_score: float = 0.0              # Cosine to best match
    confidence: float = 0.0
    reconciliation_reason: str = ""

    # === DEDUPLICATION (R3) ===
    is_duplicate: bool = False
    duplicate_of_id: Optional[str] = None
    hamming_distance: int = 64                 # Max = 64 (no match)

    # === DECAY (R3) ===
    decay_score: float = 1.0                   # Current decay [0, 1]
    lambda_decay: float = 0.01                 # Decay rate
    days_since_access: int = 0
    access_count: int = 0
    prune_decision: str = "KEEP"               # KEEP/ARCHIVE/TOMBSTONE

    # === VERSION CONTROL (R6) ===
    expected_version: int = 0
    version_conflict: bool = False

    # === WRITE TRACKING (R7) ===
    write_success: bool = False
    write_error: Optional[str] = None
    written_to_layer: Optional[str] = None
    written_record_id: Optional[str] = None

    def materialize_embedding(self, embedding: List[float]) -> None:
        """Load embedding vector when needed for similarity computation."""
        self.embedding_768 = embedding

    def set_importance(
        self,
        score: float,
        recency: float,
        affect: float,
        social: float,
        novelty: float
    ) -> None:
        """Set importance score and factors (R1)."""
        self.importance_score = score
        self.recency_factor = recency
        self.affect_factor = affect
        self.social_factor = social
        self.novelty_factor = novelty
        self.importance_computed = True

    def assign_cluster(
        self,
        cluster_id: str,
        label: int,
        distance: float
    ) -> None:
        """Assign to episode cluster (R2)."""
        self.cluster_id = cluster_id
        self.cluster_label = label
        self.is_noise = (label == -1)
        self.centroid_distance = distance

    def set_reconciliation(
        self,
        action: ReconciliationAction,
        match_id: Optional[str] = None,
        match_layer: Optional[str] = None,
        similarity: float = 0.0,
        confidence: float = 0.0,
        reason: str = ""
    ) -> None:
        """Set reconciliation decision (R3)."""
        self.reconciliation_action = action
        self.best_match_id = match_id
        self.best_match_layer = match_layer
        self.similarity_score = similarity
        self.confidence = confidence
        self.reconciliation_reason = reason
```

---

## 17. Phase Outputs Container

### 17.1 Aggregated Phase Results

```python
@dataclass
class P03PhaseOutputs:
    """
    Container for aggregated outputs from each phase.

    Unlike per-event state, these are batch-level aggregates:
    - R2: Episode clusters (not per-event)
    - R4: KG entities and edges (extracted from batch)
    - R5: Insights and counterfactuals (creative outputs)

    Each field is populated by its respective phase and consumed
    by downstream phases or R7 writes.
    """

    # === R1 OUTPUTS ===
    r1_total_importance: float = 0.0
    r1_avg_importance: float = 0.0
    r1_max_importance: float = 0.0
    r1_importance_histogram: Dict[str, int] = field(default_factory=dict)
    r1_hebbian_edge_count: int = 0

    # === R2 OUTPUTS (Episode Clusters) ===
    r2_clusters: List[EpisodeCluster] = field(default_factory=list)
    r2_noise_event_ids: List[str] = field(default_factory=list)
    r2_cluster_count: int = 0
    r2_avg_cluster_size: float = 0.0

    # === R3 OUTPUTS (Pruning/Dedup) ===
    r3_dedup_merges: List[DedupMerge] = field(default_factory=list)
    r3_archive_candidates: List[str] = field(default_factory=list)
    r3_prune_candidates: List[str] = field(default_factory=list)
    r3_resurrection_candidates: List[str] = field(default_factory=list)

    # === R4 OUTPUTS (Knowledge Graph) ===
    r4_new_entities: List[KGEntity] = field(default_factory=list)
    r4_updated_entities: List[KGEntityUpdate] = field(default_factory=list)
    r4_new_edges: List[KGEdge] = field(default_factory=list)
    r4_updated_edges: List[KGEdgeUpdate] = field(default_factory=list)
    r4_causal_edges: List[CausalEdge] = field(default_factory=list)
    r4_gap_candidates: List[GapCandidate] = field(default_factory=list)

    # === R5 OUTPUTS (Dream Exploration) ===
    r5_counterfactuals: List[CounterfactualScenario] = field(default_factory=list)
    r5_insights: List[Insight] = field(default_factory=list)
    r5_routine_optimizations: List[RoutineOptimization] = field(default_factory=list)
    r5_prospective_memories: List[ProspectiveMemory] = field(default_factory=list)
    r5_skipped: bool = False
    r5_skip_reason: Optional[str] = None

    # === R6 OUTPUTS (Reconciliation Summary) ===
    r6_reinforce_count: int = 0
    r6_extend_count: int = 0
    r6_create_count: int = 0
    r6_evolve_count: int = 0
    r6_contradict_count: int = 0
    r6_prune_count: int = 0
    r6_skip_count: int = 0


@dataclass
class EpisodeCluster:
    """Episode formed by clustering events in R2."""
    cluster_id: str                            # ULID
    member_event_ids: List[str] = field(default_factory=list)
    centroid_embedding_id: Optional[str] = None
    centroid_embedding: Optional[List[float]] = None
    dominant_sentiment: float = 0.0
    dominant_emotion: str = ""
    temporal_start: int = 0
    temporal_end: int = 0
    location_hint: Optional[str] = None
    participants_json: str = "[]"
    activity_type: str = ""
    cohesion_score: float = 0.0                # Intra-cluster similarity
    title: str = ""                            # Generated or extracted
    summary: str = ""


@dataclass
class DedupMerge:
    """Duplicate detection result from R3."""
    duplicate_id: str
    canonical_id: str
    hamming_distance: int
    merge_confidence: float
    content_type: str


@dataclass
class KGEntity:
    """Knowledge graph entity extracted in R4."""
    entity_id: str                             # ULID (new) or existing
    canonical_name: str
    entity_type: str                           # PERSON/LOCATION/ORG/THING
    aliases_json: str = "[]"
    confidence: float = 0.0
    embedding_id: Optional[str] = None
    source_event_ids: List[str] = field(default_factory=list)
    is_new: bool = True


@dataclass
class KGEntityUpdate:
    """Update to existing KG entity in R4."""
    entity_id: str
    field_updates: Dict[str, Any] = field(default_factory=dict)
    confidence_delta: float = 0.0
    new_aliases: List[str] = field(default_factory=list)


@dataclass
class KGEdge:
    """Knowledge graph edge created in R4."""
    edge_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    weight: float = 0.5
    confidence: float = 0.0
    is_causal: bool = False
    evidence_event_ids: List[str] = field(default_factory=list)
    is_new: bool = True


@dataclass
class KGEdgeUpdate:
    """Update to existing KG edge in R4."""
    edge_id: str
    weight_delta: float = 0.0
    confidence_delta: float = 0.0
    new_evidence_ids: List[str] = field(default_factory=list)


@dataclass
class CausalEdge:
    """Causal relationship inferred via Granger in R4."""
    cause_entity_id: str
    effect_entity_id: str
    lag_days: int
    granger_p_value: float
    effect_size: float
    confidence: float


@dataclass
class GapCandidate:
    """Knowledge gap for P06 active learning."""
    gap_id: str
    gap_type: str                              # AMBIGUITY/CONTRADICTION/LOW_CONFIDENCE
    related_entity_id: str
    entropy_score: float
    priority: str                              # HIGH/MEDIUM/LOW
    context_json: str = "{}"
    candidate_values: List[str] = field(default_factory=list)


@dataclass
class CounterfactualScenario:
    """What-if scenario generated in R5."""
    scenario_id: str
    base_episode_id: str
    perturbation_type: str
    perturbation_target: str
    original_outcome: str
    counterfactual_outcome: str
    probability_shift: float
    utility_delta: float


@dataclass
class Insight:
    """Creative insight from R5 dream exploration."""
    insight_id: str
    insight_type: str                          # BRIDGE/PATTERN/ANOMALY/PREDICTION
    concept_a_id: str
    concept_b_id: str
    pmi_score: float
    novelty_score: float
    relevance_score: float
    natural_language: str
    evidence_ids: List[str] = field(default_factory=list)


@dataclass
class RoutineOptimization:
    """Routine improvement suggestion from R5."""
    routine_id: str
    bottleneck_step: str
    bottleneck_position: int
    value_drop: float
    suggested_action: str
    expected_improvement: float


@dataclass
class ProspectiveMemory:
    """Future intention/reminder from R5."""
    prosp_id: str
    intention_type: str                        # GOAL/REMINDER/DEADLINE
    description: str
    trigger_condition: str
    action_to_take: str
    deadline_ts: Optional[int] = None
    importance: float = 0.5
    source_episode_id: Optional[str] = None
```

---

## 18. Staged Writes Container

### 18.1 Deferred Write Accumulation

```python
class WriteOperation(Enum):
    """Types of write operations."""
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    ARCHIVE = "ARCHIVE"
    TOMBSTONE = "TOMBSTONE"


@dataclass
class StagedWrite:
    """
    A single deferred write operation.

    Writes are accumulated during R1-R6 but not executed.
    R7 commits all staged writes atomically via UnitOfWork.
    """
    write_id: str                              # ULID for tracking
    layer: str                                 # Target table (st_epi, st_sem, etc.)
    operation: WriteOperation
    record_id: str                             # Primary key
    record_data: Dict[str, Any]                # Full record for INSERT/UPDATE
    idempotency_key: str                       # For retry safety
    source_phase: str                          # Which phase created this
    source_event_ids: List[str] = field(default_factory=list)
    expected_version: Optional[int] = None     # For optimistic locking

    @classmethod
    def insert(
        cls,
        layer: str,
        record_id: str,
        data: Dict[str, Any],
        phase: str,
        event_ids: List[str]
    ) -> StagedWrite:
        """Create an INSERT write."""
        return cls(
            write_id=str(ulid.new()),
            layer=layer,
            operation=WriteOperation.INSERT,
            record_id=record_id,
            record_data=data,
            idempotency_key=f"{phase}:{layer}:{record_id}",
            source_phase=phase,
            source_event_ids=event_ids,
        )

    @classmethod
    def update(
        cls,
        layer: str,
        record_id: str,
        data: Dict[str, Any],
        phase: str,
        expected_version: int
    ) -> StagedWrite:
        """Create an UPDATE write with version check."""
        return cls(
            write_id=str(ulid.new()),
            layer=layer,
            operation=WriteOperation.UPDATE,
            record_id=record_id,
            record_data=data,
            idempotency_key=f"{phase}:{layer}:{record_id}:v{expected_version}",
            source_phase=phase,
            expected_version=expected_version,
        )


@dataclass
class StagedOutboxEvent:
    """Outbox event to be published after R7 commit."""
    event_id: str
    topic: str
    payload: Dict[str, Any]
    source_phase: str
    priority: int = 50


@dataclass
class P03StagedWrites:
    """
    Container for all deferred writes accumulated during R1-R6.

    Writes are grouped by layer for efficient batch execution.
    R7 processes these in dependency order with atomic commit.
    """

    # === TRUTH LAYER WRITES ===
    st_epi_writes: List[StagedWrite] = field(default_factory=list)
    st_sem_writes: List[StagedWrite] = field(default_factory=list)
    st_procedural_writes: List[StagedWrite] = field(default_factory=list)
    st_social_writes: List[StagedWrite] = field(default_factory=list)
    st_prospective_writes: List[StagedWrite] = field(default_factory=list)
    st_kg_dom_writes: List[StagedWrite] = field(default_factory=list)
    st_kg_edges_writes: List[StagedWrite] = field(default_factory=list)
    st_vec_writes: List[StagedWrite] = field(default_factory=list)

    # === SOURCE EVENT UPDATES ===
    st_hipp_events_updates: List[StagedWrite] = field(default_factory=list)

    # === OUTBOX EVENTS ===
    outbox_events: List[StagedOutboxEvent] = field(default_factory=list)

    # === LEARNING QUEUE (P06) ===
    st_learning_queue_writes: List[StagedWrite] = field(default_factory=list)

    def add_write(self, write: StagedWrite) -> None:
        """Route write to appropriate layer list."""
        layer_map = {
            "st_epi": self.st_epi_writes,
            "st_sem": self.st_sem_writes,
            "st_procedural": self.st_procedural_writes,
            "st_social": self.st_social_writes,
            "st_prospective": self.st_prospective_writes,
            "st_kg_dom": self.st_kg_dom_writes,
            "st_kg_edges": self.st_kg_edges_writes,
            "st_vec": self.st_vec_writes,
            "st_hipp_events": self.st_hipp_events_updates,
            "st_learning_queue": self.st_learning_queue_writes,
        }
        target = layer_map.get(write.layer)
        if target is not None:
            target.append(write)

    def add_outbox_event(
        self,
        topic: str,
        payload: Dict[str, Any],
        phase: str
    ) -> None:
        """Stage an outbox event for R8 emission."""
        self.outbox_events.append(StagedOutboxEvent(
            event_id=str(ulid.new()),
            topic=topic,
            payload=payload,
            source_phase=phase,
        ))

    def total_writes(self) -> int:
        """Count total staged writes."""
        return sum([
            len(self.st_epi_writes),
            len(self.st_sem_writes),
            len(self.st_procedural_writes),
            len(self.st_social_writes),
            len(self.st_prospective_writes),
            len(self.st_kg_dom_writes),
            len(self.st_kg_edges_writes),
            len(self.st_vec_writes),
            len(self.st_hipp_events_updates),
            len(self.st_learning_queue_writes),
        ])

    def get_all_writes_ordered(self) -> List[StagedWrite]:
        """
        Return writes in dependency order for atomic commit.

        Order: vec → kg_dom → kg_edges → epi → sem →
               procedural → social → prospective →
               learning_queue → hipp_events
        """
        return [
            *self.st_vec_writes,           # Embeddings first (referenced by others)
            *self.st_kg_dom_writes,        # Entities before edges
            *self.st_kg_edges_writes,      # Edges reference entities
            *self.st_epi_writes,           # Episodes
            *self.st_sem_writes,           # Patterns
            *self.st_procedural_writes,    # Routines
            *self.st_social_writes,        # Relationships
            *self.st_prospective_writes,   # Intentions
            *self.st_learning_queue_writes, # P06 gaps
            *self.st_hipp_events_updates,  # Source status last
        ]
```

---

## 19. Observability Context

### 19.1 Tracing and Metrics

```python
@dataclass
class P03ObservabilityContext:
    """
    Observability context carried through the envelope.

    Provides tracing, timing, and metrics aggregation.
    """

    # === DISTRIBUTED TRACING ===
    trace_id: str = ""
    root_span_id: str = ""
    current_span_id: str = ""
    span_stack: List[str] = field(default_factory=list)

    # === PHASE TIMING ===
    phase_start_ts: Dict[str, int] = field(default_factory=dict)
    phase_end_ts: Dict[str, int] = field(default_factory=dict)

    # === METRICS AGGREGATION ===
    counters: Dict[str, int] = field(default_factory=dict)
    histograms: Dict[str, List[float]] = field(default_factory=dict)

    # === LOG CONTEXT ===
    log_context: Dict[str, str] = field(default_factory=dict)

    def increment(self, metric: str, delta: int = 1) -> None:
        """Increment a counter metric."""
        self.counters[metric] = self.counters.get(metric, 0) + delta

    def record_histogram(self, metric: str, value: float) -> None:
        """Record a value in a histogram."""
        if metric not in self.histograms:
            self.histograms[metric] = []
        self.histograms[metric].append(value)

    def get_log_context(self, phase: str, module: str) -> Dict[str, str]:
        """Get structured log context for current execution point."""
        return {
            "pipeline_id": "P03_CONSOLIDATE",
            "trace_id": self.trace_id,
            "phase": phase,
            "module_id": module,
            **self.log_context,
        }


@dataclass
class P03Error:
    """Error record for envelope error tracking."""
    error_id: str
    phase: str
    stage_id: str
    error_type: str
    error_message: str
    event_id: Optional[str] = None
    recoverable: bool = True
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
```

---

## 20. Propagation Rules

### 20.1 Phase-by-Phase Envelope Mutation

This section defines exactly what each phase reads and writes on the envelope.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         ENVELOPE PROPAGATION FLOW                               │
│                                                                                 │
│  ┌─────┐     ┌─────┐     ┌─────┐     ┌─────┐     ┌─────┐                       │
│  │ R0  │────▶│ R1  │────▶│ R2  │────▶│ R3  │────▶│ R4  │                       │
│  └──┬──┘     └──┬──┘     └──┬──┘     └──┬──┘     └──┬──┘                       │
│     │           │           │           │           │                           │
│  context     events.      events.     events.    phases.                        │
│  events      importance   cluster_id  reconcile  r4_entities                    │
│  (init)      phases.r1_*  phases.r2_* phases.r3_* r4_edges                      │
│                           staged.kg   staged.     staged.kg                     │
│                                       prune                                     │
│                                                                                 │
│  ┌─────┐     ┌─────┐     ┌─────┐     ┌─────┐                                   │
│  │ R5  │────▶│ R6  │────▶│ R7  │────▶│ R8  │                                   │
│  └──┬──┘     └──┬──┘     └──┬──┘     └──┬──┘                                   │
│     │           │           │           │                                       │
│  phases.      phases.     COMMIT     EMIT                                       │
│  r5_insights  r6_summary  staged.*   outbox                                     │
│  staged.prosp staged.     → DB       events                                     │
│               hipp_upd                                                          │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 20.2 Detailed Propagation Table

| Phase | Reads | Writes | Invariants |
|-------|-------|--------|------------|
| **R0** | trigger event | `context` (frozen), `events[]` (initialized from st_hipp_events) | `context` is immutable after R0 |
| **R1** | `events[].embedding_id` | `events[].importance_*`, `phases.r1_*`, `events[].hebbian_updates` | All events scored |
| **R2** | `events[].embedding_768`, `events[].timestamp` | `events[].cluster_*`, `phases.r2_clusters[]` | Clusters have ≥1 event |
| **R3** | `events[].simhash_hex`, `phases.r2_clusters` | `events[].reconciliation_*`, `events[].decay_*`, `phases.r3_*`, `staged.prune` | Every event has decision |
| **R4** | `phases.r2_clusters`, `events[].ner_entities_json` | `phases.r4_*`, `staged.st_kg_dom`, `staged.st_kg_edges` | Entities deduped |
| **R5** | `phases.r2_clusters`, `phases.r4_*` | `phases.r5_*`, `staged.st_prospective` | Optional (can skip) |
| **R6** | All `events[]`, all `phases.*` | `phases.r6_*`, `staged.st_hipp_events`, all final staging | Staging complete |
| **R7** | `staged.*` | Database (atomic commit) | All-or-nothing |
| **R8** | `staged.outbox_events`, `phases.r4_gap_candidates` | Event bus, st_learning_queue | Events emitted |

### 20.3 Immutability Rules

```python
# IMMUTABLE after creation:
P03CycleContext        # frozen=True dataclass
envelope.context       # Never reassigned after R0

# APPEND-ONLY during phases:
envelope.events[]      # Events added in R0, enriched R1-R6
envelope.staged.*      # Writes accumulated, never removed
envelope.errors[]      # Errors appended

# REPLACE per-phase:
envelope.current_phase # Updated at phase boundaries
envelope.phases.r{N}_* # Set once per phase
```

### 20.4 Module Return Pattern

Each module returns enrichment data that the pipeline runner merges:

```python
async def run(
    message: Any,
    context: PipelineContext,
    **config
) -> Dict[str, Any]:
    """
    Module return contract for P03.

    Returns dict with specific keys based on phase:
    - R1: {"scored_events": [...], "hebbian_updates": [...], "r1_stats": {...}}
    - R2: {"clusters": [...], "noise_ids": [...]}
    - R3: {"reconciliation_decisions": [...], "dedup_merges": [...]}
    - etc.

    Pipeline runner merges into envelope based on keys.
    """
    envelope: P03BatchEnvelope = config["envelope"]

    # Phase-specific processing...

    return {
        "scored_events": [...],  # Runner merges into envelope.events
        "r1_total_importance": total,
        "r1_avg_importance": avg,
    }
```

### 20.5 Envelope Merge Strategy

```python
class P03EnvelopeMerger:
    """
    Merges module outputs into envelope.

    Unlike P02's shallow dict.update(), P03 uses typed merging:
    - Per-event fields: Match by event_id and update
    - Phase outputs: Direct assignment to phases.r{N}_*
    - Staged writes: Append to staged.* lists
    """

    @staticmethod
    def merge_r1_output(
        envelope: P03BatchEnvelope,
        output: Dict[str, Any]
    ) -> None:
        """Merge R1 importance scoring results."""
        # Update per-event scores
        scored_events = output.get("scored_events", [])
        for scored in scored_events:
            event = envelope.get_event(scored["event_id"])
            if event:
                event.set_importance(
                    score=scored["importance_score"],
                    recency=scored["recency_factor"],
                    affect=scored["affect_factor"],
                    social=scored["social_factor"],
                    novelty=scored["novelty_factor"],
                )
                event.hebbian_updates = scored.get("hebbian_updates", [])

        # Update phase outputs
        envelope.phases.r1_total_importance = output.get("r1_total_importance", 0)
        envelope.phases.r1_avg_importance = output.get("r1_avg_importance", 0)
        envelope.phases.r1_max_importance = output.get("r1_max_importance", 0)
        envelope.phases.r1_hebbian_edge_count = len(output.get("hebbian_updates", []))

    @staticmethod
    def merge_r2_output(
        envelope: P03BatchEnvelope,
        output: Dict[str, Any]
    ) -> None:
        """Merge R2 clustering results."""
        clusters = output.get("clusters", [])

        # Create EpisodeCluster objects
        for cluster_data in clusters:
            cluster = EpisodeCluster(
                cluster_id=cluster_data["cluster_id"],
                member_event_ids=cluster_data["member_event_ids"],
                centroid_embedding_id=cluster_data.get("centroid_embedding_id"),
                dominant_sentiment=cluster_data.get("dominant_sentiment", 0),
                temporal_start=cluster_data.get("temporal_start", 0),
                temporal_end=cluster_data.get("temporal_end", 0),
                cohesion_score=cluster_data.get("cohesion_score", 0),
            )
            envelope.phases.r2_clusters.append(cluster)

            # Update per-event cluster assignment
            for event_id in cluster.member_event_ids:
                event = envelope.get_event(event_id)
                if event:
                    event.assign_cluster(
                        cluster_id=cluster.cluster_id,
                        label=cluster_data.get("label", 0),
                        distance=cluster_data.get("distances", {}).get(event_id, 0),
                    )

        # Mark noise events
        envelope.phases.r2_noise_event_ids = output.get("noise_ids", [])
        for noise_id in envelope.phases.r2_noise_event_ids:
            event = envelope.get_event(noise_id)
            if event:
                event.is_noise = True
                event.cluster_label = -1

        envelope.phases.r2_cluster_count = len(clusters)
        envelope.phases.r2_avg_cluster_size = (
            sum(len(c.member_event_ids) for c in envelope.phases.r2_clusters)
            / max(len(clusters), 1)
        )

    @staticmethod
    def merge_r3_output(
        envelope: P03BatchEnvelope,
        output: Dict[str, Any]
    ) -> None:
        """Merge R3 reconciliation and pruning results."""
        decisions = output.get("reconciliation_decisions", [])

        for decision in decisions:
            event = envelope.get_event(decision["event_id"])
            if event:
                event.set_reconciliation(
                    action=ReconciliationAction(decision["action"]),
                    match_id=decision.get("match_id"),
                    match_layer=decision.get("match_layer"),
                    similarity=decision.get("similarity", 0),
                    confidence=decision.get("confidence", 0),
                    reason=decision.get("reason", ""),
                )
                event.decay_score = decision.get("decay_score", 1.0)
                event.prune_decision = decision.get("prune_decision", "KEEP")

        # Dedup merges
        for merge in output.get("dedup_merges", []):
            envelope.phases.r3_dedup_merges.append(DedupMerge(**merge))

        # Prune/archive candidates
        envelope.phases.r3_archive_candidates = output.get("archive_candidates", [])
        envelope.phases.r3_prune_candidates = output.get("prune_candidates", [])
```

---

## 21. Envelope Factory and Lifecycle

### 21.1 Envelope Creation (R0)

```python
class P03EnvelopeFactory:
    """Factory for creating P03 envelopes from trigger events."""

    @staticmethod
    async def create_from_trigger(
        trigger_event: Dict[str, Any],
        syscalls: Any,  # K0 syscalls interface
    ) -> P03BatchEnvelope:
        """
        Create envelope from trigger event.

        1. Extract trigger metadata
        2. Query st_hipp_events for pending events
        3. Initialize P03EventState for each event
        4. Create immutable context
        """
        tenant_id = trigger_event.get("tenant_id")
        space_id = trigger_event.get("space_id")
        trigger_type = trigger_event.get("trigger_type", "MANUAL")
        trace_id = trigger_event.get("trace_id")
        max_batch = trigger_event.get("max_batch_size", 1000)

        # Query pending events from st_hipp_events
        pending_events = await syscalls.read(
            "st_hipp_events",
            {
                "tenant_id": tenant_id,
                "space_id": space_id,
                "consolidation_status": "PENDING",
            },
            limit=max_batch,
            order_by="created_at ASC",
        )

        if not pending_events:
            raise ValueError("No pending events for consolidation")

        # Create context (frozen after this)
        context = P03CycleContext.create(
            tenant_id=tenant_id,
            space_id=space_id,
            event_ids=[e["event_id"] for e in pending_events],
            trigger_type=trigger_type,
            trigger_reason=trigger_event.get("trigger_reason", ""),
            trace_id=trace_id,
            pending_before=len(pending_events),
        )

        # Initialize per-event state
        events = []
        for row in pending_events:
            events.append(P03EventState(
                event_id=row["event_id"],
                hipp_event_id=row["hipp_event_id"],
                content_text=row.get("content_text", ""),
                content_type=row.get("content_type", ""),
                content_hash=row.get("content_hash", ""),
                simhash_hex=row.get("simhash_hex", ""),
                timestamp=row.get("timestamp", 0),
                channel_id=row.get("channel_id", ""),
                embedding_id=row.get("embedding_id", ""),
                sentiment_score=row.get("sentiment_score", 0.0),
                sentiment_label=row.get("sentiment_label", "neutral"),
                emotions_json=row.get("emotions_json", "{}"),
                intent_label=row.get("intent_label", ""),
                ner_entities_json=row.get("ner_entities_json", "[]"),
                temporal_expressions_json=row.get("temporal_expressions_json", "[]"),
            ))

        # Create observability context
        observability = P03ObservabilityContext(
            trace_id=context.trace_id,
            log_context={
                "cycle_id": context.cycle_id,
                "tenant_id": context.tenant_id,
                "space_id": context.space_id,
                "batch_size": str(context.batch_size),
            },
        )

        envelope = P03BatchEnvelope(
            context=context,
            events=events,
            observability=observability,
        )

        envelope.mark_phase_start(P03Phase.R0_INIT)

        return envelope
```

### 21.2 Envelope Serialization

```python
class P03EnvelopeSerializer:
    """
    Serialize/deserialize envelopes for checkpointing.

    Used for:
    - DLQ storage (failed cycles)
    - Debugging (envelope snapshots)
    - Recovery (resume from checkpoint)
    """

    @staticmethod
    def to_dict(envelope: P03BatchEnvelope) -> Dict[str, Any]:
        """Convert envelope to JSON-serializable dict."""
        return {
            "context": {
                "cycle_id": envelope.context.cycle_id,
                "batch_id": envelope.context.batch_id,
                "tenant_id": envelope.context.tenant_id,
                "space_id": envelope.context.space_id,
                "trace_id": envelope.context.trace_id,
                "trigger_type": envelope.context.trigger_type,
                "triggered_at": envelope.context.triggered_at,
                "batch_size": envelope.context.batch_size,
                "event_ids": list(envelope.context.event_ids),
            },
            "current_phase": envelope.current_phase.value,
            "phase_timings": envelope.phase_timings,
            "events_count": len(envelope.events),
            "staged_writes_count": envelope.staged.total_writes(),
            "errors_count": len(envelope.errors),
            # Note: Full event state omitted for size;
            # use to_full_dict() for complete serialization
        }

    @staticmethod
    def to_full_dict(envelope: P03BatchEnvelope) -> Dict[str, Any]:
        """Full serialization including all events."""
        base = P03EnvelopeSerializer.to_dict(envelope)
        base["events"] = [
            {
                "event_id": e.event_id,
                "importance_score": e.importance_score,
                "cluster_id": e.cluster_id,
                "reconciliation_action": e.reconciliation_action.value,
                "similarity_score": e.similarity_score,
                # Add more fields as needed
            }
            for e in envelope.events
        ]
        return base
```

---

## 22. Usage Example: Complete Cycle

### 22.1 Pipeline Runner Integration

```python
class P03ConsolidationPipeline:
    """
    P03 pipeline orchestrator.

    Demonstrates envelope flow through all phases.
    """

    def __init__(
        self,
        module_registry: Any,
        syscalls: Any,
    ):
        self.modules = module_registry
        self.syscalls = syscalls
        self.merger = P03EnvelopeMerger()

    async def handle(self, trigger_event: Dict[str, Any]) -> Dict[str, Any]:
        """Execute full consolidation cycle."""

        # === R0: INIT ===
        envelope = await P03EnvelopeFactory.create_from_trigger(
            trigger_event,
            self.syscalls,
        )
        envelope.mark_phase_complete(P03Phase.R0_INIT)

        try:
            # === R1: IMPORTANCE SCORING ===
            envelope.mark_phase_start(P03Phase.R1_SCORE)
            r1_output = await self.modules.invoke(
                "consolidation.importance_scorer:v1",
                envelope=envelope,
            )
            self.merger.merge_r1_output(envelope, r1_output)
            envelope.mark_phase_complete(P03Phase.R1_SCORE)

            # === R2: EPISODIC CLUSTERING ===
            envelope.mark_phase_start(P03Phase.R2_CLUSTER)
            r2_output = await self.modules.invoke(
                "consolidation.episodic_clusterer:v1",
                envelope=envelope,
            )
            self.merger.merge_r2_output(envelope, r2_output)
            envelope.mark_phase_complete(P03Phase.R2_CLUSTER)

            # === R3: FORGETTING/PRUNING ===
            envelope.mark_phase_start(P03Phase.R3_PRUNE)
            r3_output = await self.modules.invoke(
                "consolidation.prune_decider:v1",
                envelope=envelope,
            )
            self.merger.merge_r3_output(envelope, r3_output)
            envelope.mark_phase_complete(P03Phase.R3_PRUNE)

            # === R4: KNOWLEDGE GRAPH ===
            envelope.mark_phase_start(P03Phase.R4_KG)
            r4_output = await self.modules.invoke(
                "consolidation.kg_consolidator:v1",
                envelope=envelope,
            )
            # Merge R4 outputs...
            envelope.mark_phase_complete(P03Phase.R4_KG)

            # === R5: DREAM (optional) ===
            if self._should_run_r5(envelope):
                envelope.mark_phase_start(P03Phase.R5_DREAM)
                r5_output = await self.modules.invoke(
                    "consolidation.dream_explorer:v1",
                    envelope=envelope,
                )
                # Merge R5 outputs...
                envelope.mark_phase_complete(P03Phase.R5_DREAM)
            else:
                envelope.phases.r5_skipped = True
                envelope.phases.r5_skip_reason = "Backlog threshold exceeded"

            # === R6: STAGING ===
            envelope.mark_phase_start(P03Phase.R6_STAGE)
            await self._stage_all_writes(envelope)
            envelope.mark_phase_complete(P03Phase.R6_STAGE)

            # === R7: ATOMIC COMMIT ===
            envelope.mark_phase_start(P03Phase.R7_WRITE)
            await self._commit_staged_writes(envelope)
            envelope.mark_phase_complete(P03Phase.R7_WRITE)

            # === R8: EVENT EMISSION ===
            envelope.mark_phase_start(P03Phase.R8_EMIT)
            await self._emit_events(envelope)
            envelope.mark_phase_complete(P03Phase.R8_EMIT)

            envelope.current_phase = P03Phase.COMPLETE

        except Exception as e:
            envelope.current_phase = P03Phase.FAILED
            envelope.errors.append(P03Error(
                error_id=str(ulid.new()),
                phase=envelope.current_phase.value,
                stage_id="pipeline",
                error_type=type(e).__name__,
                error_message=str(e),
            ))
            raise

        return P03EnvelopeSerializer.to_dict(envelope)

    def _should_run_r5(self, envelope: P03BatchEnvelope) -> bool:
        """Check if R5 dream phase should run."""
        # Skip if backlogged
        return envelope.context.pending_before < 5000

    async def _stage_all_writes(self, envelope: P03BatchEnvelope) -> None:
        """Stage all writes from accumulated phase outputs."""
        # Stage episode writes
        for cluster in envelope.phases.r2_clusters:
            envelope.staged.add_write(StagedWrite.insert(
                layer="st_epi",
                record_id=cluster.cluster_id,
                data={
                    "epi_id": cluster.cluster_id,
                    "tenant_id": envelope.context.tenant_id,
                    "space_id": envelope.context.space_id,
                    "title": cluster.title,
                    "start_time": cluster.temporal_start,
                    "end_time": cluster.temporal_end,
                    "source_event_ids_json": str(cluster.member_event_ids),
                    # ... more fields
                },
                phase="R6",
                event_ids=cluster.member_event_ids,
            ))

        # Stage hipp_events status updates
        for event in envelope.events:
            envelope.staged.add_write(StagedWrite.update(
                layer="st_hipp_events",
                record_id=event.hipp_event_id,
                data={
                    "consolidation_status": "CONSOLIDATED",
                    "consolidation_action": event.reconciliation_action.value,
                    "consolidated_at": int(time.time() * 1000),
                },
                phase="R6",
                expected_version=event.expected_version,
            ))

        # Stage outbox events
        envelope.staged.add_outbox_event(
            topic="p03.consolidation.complete.v1",
            payload={
                "cycle_id": envelope.context.cycle_id,
                "events_processed": len(envelope.events),
                "episodes_created": len(envelope.phases.r2_clusters),
            },
            phase="R8",
        )

    async def _commit_staged_writes(self, envelope: P03BatchEnvelope) -> None:
        """Commit all staged writes atomically."""
        async with self.syscalls.unit_of_work() as uow:
            for write in envelope.staged.get_all_writes_ordered():
                if write.operation == WriteOperation.INSERT:
                    await uow.insert(write.layer, write.record_data)
                elif write.operation == WriteOperation.UPDATE:
                    await uow.update(
                        write.layer,
                        write.record_data,
                        {"id": write.record_id},
                        expected_version=write.expected_version,
                    )
            # Commit happens on context exit

    async def _emit_events(self, envelope: P03BatchEnvelope) -> None:
        """Emit staged outbox events."""
        for outbox_event in envelope.staged.outbox_events:
            await self.syscalls.emit(
                topic=outbox_event.topic,
                payload=outbox_event.payload,
            )
```

---

## 23. Summary: Envelope Architecture

### 23.1 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Batch vs Single** | Batch envelope | P03 processes 100-1000 events per cycle |
| **Immutable Context** | `frozen=True` dataclass | Prevent accidental mutation after R0 |
| **Per-Event State** | `List[P03EventState]` | Each event tracked independently |
| **Staged Writes** | Deferred accumulation | Atomic R7 commit via UnitOfWork |
| **Typed Merging** | Custom merger per phase | Type safety, not shallow dict merge |
| **Lazy Embeddings** | ID reference by default | Materialize 768-dim vectors only when needed |

### 23.2 Memory Footprint Estimate

| Component | Per Event | Per Batch (1000) |
|-----------|-----------|------------------|
| Event State (no embedding) | ~2 KB | ~2 MB |
| Embedding (768 × 4 bytes) | 3 KB | 3 MB |
| Cluster metadata | - | ~100 KB |
| Staged writes | ~500 bytes | ~500 KB |
| **Total (lazy embeddings)** | - | **~2.5 MB** |
| **Total (materialized)** | - | **~5.5 MB** |

### 23.3 Next Steps

1. **Create module stubs** in `k0/modules/consolidation/`
2. **Define YAML contracts** for P03 pipeline
3. **Implement R0-R1** as first milestone
4. **Add unit tests** for envelope creation and merging
5. **Create ADR** k010.x-p03-envelope-architecture.md

---

## 24. Design Refinements

> **Status**: Enhancements to base architecture
> **Priority**: Implement with initial module stubs

---

### 24.1 Embedding Cache (Lazy Loading with Memoization)

```python
from typing import Callable, Awaitable

@dataclass
class P03BatchEnvelope:
    """
    Top-level envelope with embedding cache.

    Embeddings are expensive (768 floats × 4 bytes = 3KB each).
    Cache avoids redundant fetches when same embedding needed
    by multiple phases (R1 scoring, R2 clustering, R3 similarity).
    """

    # === EXISTING FIELDS ===
    context: P03CycleContext
    events: List[P03EventState] = field(default_factory=list)
    phases: P03PhaseOutputs = field(default_factory=lambda: P03PhaseOutputs())
    staged: P03StagedWrites = field(default_factory=lambda: P03StagedWrites())
    observability: P03ObservabilityContext = field(
        default_factory=lambda: P03ObservabilityContext()
    )
    current_phase: P03Phase = P03Phase.R0_INIT
    phase_timings: Dict[str, int] = field(default_factory=dict)
    errors: List[P03Error] = field(default_factory=list)

    # === NEW: EMBEDDING CACHE ===
    _embedding_cache: Dict[str, List[float]] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
    )
    _embedding_loader: Optional[Callable[[str], Awaitable[List[float]]]] = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    # === NEW: EVENT INDEX ===
    _event_index: Dict[str, int] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
    )

    def set_embedding_loader(
        self,
        loader: Callable[[str], Awaitable[List[float]]]
    ) -> None:
        """Inject embedding loader function (from syscalls or st_vec driver)."""
        self._embedding_loader = loader

    async def get_embedding(self, embedding_id: str) -> List[float]:
        """
        Get embedding with caching.

        First call fetches from st_vec, subsequent calls use cache.
        Raises if loader not set or embedding not found.
        """
        if not embedding_id:
            raise ValueError("Empty embedding_id")

        if embedding_id not in self._embedding_cache:
            if self._embedding_loader is None:
                raise RuntimeError("Embedding loader not configured")
            self._embedding_cache[embedding_id] = await self._embedding_loader(embedding_id)
            self.observability.increment("embeddings_loaded")
        else:
            self.observability.increment("embeddings_cache_hits")

        return self._embedding_cache[embedding_id]

    async def get_embedding_batch(self, embedding_ids: List[str]) -> Dict[str, List[float]]:
        """
        Batch load embeddings (for R2 clustering efficiency).

        Fetches missing embeddings in single batch query.
        """
        missing = [eid for eid in embedding_ids if eid not in self._embedding_cache]

        if missing and self._embedding_loader:
            # Loader should support batch - implementation detail
            for eid in missing:
                self._embedding_cache[eid] = await self._embedding_loader(eid)
            self.observability.increment("embeddings_loaded", len(missing))

        return {eid: self._embedding_cache[eid] for eid in embedding_ids if eid in self._embedding_cache}

    def preload_embeddings(self, embeddings: Dict[str, List[float]]) -> None:
        """Bulk load embeddings into cache (for testing or warm start)."""
        self._embedding_cache.update(embeddings)

    def embedding_cache_size(self) -> int:
        """Return number of cached embeddings."""
        return len(self._embedding_cache)

    def embedding_cache_memory_bytes(self) -> int:
        """Estimate memory used by embedding cache."""
        # 768 floats × 4 bytes = 3072 bytes per embedding
        return len(self._embedding_cache) * 768 * 4

    # === NEW: O(1) EVENT LOOKUP ===
    def build_event_index(self) -> None:
        """Build index for O(1) event lookup. Call after R0 populates events."""
        self._event_index = {e.event_id: i for i, e in enumerate(self.events)}

    def get_event(self, event_id: str) -> Optional[P03EventState]:
        """O(1) lookup event by ID (uses index if built)."""
        if self._event_index:
            idx = self._event_index.get(event_id)
            return self.events[idx] if idx is not None else None
        # Fallback to O(n) scan
        for event in self.events:
            if event.event_id == event_id:
                return event
        return None
```

---

### 24.2 Hebbian Updates at Batch Level

Move `hebbian_updates` from per-event to phase outputs (they're cross-event relationships):

```python
@dataclass
class HebbianUpdate:
    """
    Single Hebbian edge weight update.

    Represents co-activation between concepts/entities.
    Stored at batch level since edges span multiple events.
    """
    source_entity_id: str
    target_entity_id: str
    edge_type: str                    # "CO_OCCURS" / "CAUSES" / "FOLLOWS"
    weight_delta: float               # Δw = η × pre × post
    pre_activation: float             # Source activation [0, 1]
    post_activation: float            # Target activation [0, 1]
    learning_rate: float = 0.01       # η
    source_event_ids: List[str] = field(default_factory=list)
    timestamp: int = 0


@dataclass
class P03PhaseOutputs:
    """Updated with batch-level Hebbian updates."""

    # === R1 OUTPUTS (UPDATED) ===
    r1_total_importance: float = 0.0
    r1_avg_importance: float = 0.0
    r1_max_importance: float = 0.0
    r1_importance_histogram: Dict[str, int] = field(default_factory=dict)

    # MOVED FROM PER-EVENT TO BATCH LEVEL:
    r1_hebbian_updates: List[HebbianUpdate] = field(default_factory=list)
    r1_hebbian_edge_count: int = 0
    r1_hebbian_total_delta: float = 0.0

    # ... rest unchanged


@dataclass
class P03EventState:
    """Updated: Remove per-event hebbian_updates."""

    # === IMPORTANCE SCORING (R1) - UPDATED ===
    importance_score: float = 0.0
    recency_factor: float = 0.0
    affect_factor: float = 0.0
    social_factor: float = 0.0
    novelty_factor: float = 0.0
    importance_computed: bool = False

    # REMOVED: hebbian_updates: List[Dict[str, Any]]
    # Reason: Hebbian updates are cross-event, moved to phases.r1_hebbian_updates

    # Instead, track which entities this event activated:
    activated_entity_ids: List[str] = field(default_factory=list)
```

---

### 24.3 Phase Transition Guards

```python
class P03Phase(Enum):
    """Phase enum with transition validation."""
    R0_INIT = "R0"
    R1_SCORE = "R1"
    R2_CLUSTER = "R2"
    R3_PRUNE = "R3"
    R4_KG = "R4"
    R5_DREAM = "R5"
    R6_STAGE = "R6"
    R7_WRITE = "R7"
    R8_EMIT = "R8"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"

    @staticmethod
    def valid_transitions() -> Dict[str, List[str]]:
        """Define valid phase transitions."""
        return {
            "R0": ["R1", "FAILED"],
            "R1": ["R2", "FAILED"],
            "R2": ["R3", "FAILED"],
            "R3": ["R4", "FAILED"],
            "R4": ["R5", "R6", "FAILED"],  # R5 is optional
            "R5": ["R6", "FAILED"],
            "R6": ["R7", "FAILED"],
            "R7": ["R8", "FAILED"],
            "R8": ["COMPLETE", "FAILED"],
            "COMPLETE": [],  # Terminal
            "FAILED": [],    # Terminal
        }

    def can_transition_to(self, target: "P03Phase") -> bool:
        """Check if transition is valid."""
        return target.value in self.valid_transitions().get(self.value, [])


@dataclass
class P03BatchEnvelope:
    """With phase transition guards."""

    def transition_to(self, phase: P03Phase) -> None:
        """
        Validated phase transition.

        Raises InvalidPhaseTransition if progression is invalid.
        """
        if not self.current_phase.can_transition_to(phase):
            raise InvalidPhaseTransition(
                f"Cannot transition from {self.current_phase.value} to {phase.value}"
            )
        self.mark_phase_complete(self.current_phase)
        self.mark_phase_start(phase)
        self.current_phase = phase


class InvalidPhaseTransition(Exception):
    """Raised when attempting invalid phase progression."""
    pass
```

---

### 24.4 Checkpoint Snapshots

```python
from copy import deepcopy
from dataclasses import asdict


@dataclass
class PhaseCheckpoint:
    """Immutable snapshot at phase boundary."""
    phase: str
    timestamp: int
    events_count: int
    staged_writes_count: int
    errors_count: int
    phase_timings: Dict[str, int]
    summary: Dict[str, Any]  # Phase-specific summary


@dataclass
class P03BatchEnvelope:
    """With checkpoint capability."""

    # === CHECKPOINTS ===
    _checkpoints: List[PhaseCheckpoint] = field(
        default_factory=list,
        init=False,
        repr=False,
    )

    def checkpoint(self, summary: Optional[Dict[str, Any]] = None) -> PhaseCheckpoint:
        """
        Create checkpoint at current phase.

        Use for:
        - Recovery after failure
        - Debugging phase issues
        - Audit trail
        """
        cp = PhaseCheckpoint(
            phase=self.current_phase.value,
            timestamp=int(time.time() * 1000),
            events_count=len(self.events),
            staged_writes_count=self.staged.total_writes(),
            errors_count=len(self.errors),
            phase_timings=dict(self.phase_timings),
            summary=summary or self._generate_phase_summary(),
        )
        self._checkpoints.append(cp)
        return cp

    def _generate_phase_summary(self) -> Dict[str, Any]:
        """Auto-generate summary based on current phase."""
        phase = self.current_phase.value

        if phase == "R1":
            return {
                "avg_importance": self.phases.r1_avg_importance,
                "max_importance": self.phases.r1_max_importance,
                "hebbian_edges": self.phases.r1_hebbian_edge_count,
            }
        elif phase == "R2":
            return {
                "cluster_count": self.phases.r2_cluster_count,
                "noise_count": len(self.phases.r2_noise_event_ids),
                "avg_cluster_size": self.phases.r2_avg_cluster_size,
            }
        elif phase == "R3":
            return {
                "reinforce": self.phases.r6_reinforce_count,
                "extend": self.phases.r6_extend_count,
                "create": self.phases.r6_create_count,
                "prune": self.phases.r6_prune_count,
            }
        # ... more phases
        return {}

    def get_checkpoint(self, phase: str) -> Optional[PhaseCheckpoint]:
        """Retrieve checkpoint for specific phase."""
        for cp in reversed(self._checkpoints):
            if cp.phase == phase:
                return cp
        return None

    def checkpoints_summary(self) -> List[Dict[str, Any]]:
        """Get all checkpoints as dicts (for serialization)."""
        return [
            {
                "phase": cp.phase,
                "timestamp": cp.timestamp,
                "events": cp.events_count,
                "staged": cp.staged_writes_count,
                "errors": cp.errors_count,
            }
            for cp in self._checkpoints
        ]
```

---

### 24.5 Progress Tracking

```python
@dataclass
class P03BatchEnvelope:
    """With progress tracking for long batches."""

    # === PROGRESS ===
    _events_processed: int = field(default=0, init=False, repr=False)
    _current_phase_progress: float = field(default=0.0, init=False, repr=False)

    def update_progress(self, processed: int, total: Optional[int] = None) -> float:
        """
        Update processing progress.

        Returns percentage complete [0.0, 1.0].
        """
        if total is None:
            total = len(self.events)

        self._events_processed = processed
        self._current_phase_progress = processed / max(total, 1)
        return self._current_phase_progress

    def get_overall_progress(self) -> Dict[str, Any]:
        """
        Get overall cycle progress.

        Returns phase completion + current phase progress.
        """
        completed_phases = len([p for p in self.phase_timings.keys()])
        total_phases = 9  # R0-R8

        return {
            "completed_phases": completed_phases,
            "total_phases": total_phases,
            "current_phase": self.current_phase.value,
            "current_phase_progress": self._current_phase_progress,
            "overall_progress": (completed_phases + self._current_phase_progress) / total_phases,
            "events_processed": self._events_processed,
            "events_total": len(self.events),
        }
```

---

### 24.6 Event Filtering Views

```python
@dataclass
class P03BatchEnvelope:
    """With event filtering helper methods."""

    # === EVENT VIEWS ===

    def get_events_by_action(
        self,
        action: ReconciliationAction
    ) -> List[P03EventState]:
        """Filter events by reconciliation action."""
        return [e for e in self.events if e.reconciliation_action == action]

    def get_events_by_cluster(self, cluster_id: str) -> List[P03EventState]:
        """Get all events in a cluster."""
        return [e for e in self.events if e.cluster_id == cluster_id]

    def get_noise_events(self) -> List[P03EventState]:
        """Get events not assigned to any cluster."""
        return [e for e in self.events if e.is_noise]

    def get_high_importance_events(self, threshold: float = 0.7) -> List[P03EventState]:
        """Get events above importance threshold."""
        return [e for e in self.events if e.importance_score >= threshold]

    def get_events_for_layer(self, layer: str) -> List[P03EventState]:
        """Get events targeting a specific truth layer."""
        return [e for e in self.events if e.best_match_layer == layer]

    def get_duplicate_events(self) -> List[P03EventState]:
        """Get events marked as duplicates."""
        return [e for e in self.events if e.is_duplicate]

    def get_events_with_errors(self) -> List[P03EventState]:
        """Get events that failed during write."""
        return [e for e in self.events if e.write_error is not None]

    def partition_by_action(self) -> Dict[ReconciliationAction, List[P03EventState]]:
        """Partition all events by their reconciliation action."""
        result: Dict[ReconciliationAction, List[P03EventState]] = {}
        for event in self.events:
            action = event.reconciliation_action
            if action not in result:
                result[action] = []
            result[action].append(event)
        return result

    def get_action_counts(self) -> Dict[str, int]:
        """Count events by reconciliation action."""
        counts: Dict[str, int] = {}
        for event in self.events:
            action = event.reconciliation_action.value
            counts[action] = counts.get(action, 0) + 1
        return counts
```

---

### 24.7 R8 Cycle Summary (Structured Emission)

```python
@dataclass
class P03CycleSummary:
    """
    Structured summary for R8 emission.

    Published to p03.consolidation.complete.v1 topic.
    Consumed by dashboards, monitoring, and downstream pipelines.
    """

    # === IDENTIFICATION ===
    cycle_id: str
    batch_id: str
    tenant_id: str
    space_id: str
    trace_id: str

    # === TIMING ===
    started_at: int                  # Unix ms
    completed_at: int                # Unix ms
    total_duration_ms: int
    phase_timings: Dict[str, int]    # Phase → duration_ms

    # === BATCH METRICS ===
    events_input: int
    events_processed: int
    events_failed: int

    # === R1 SUMMARY ===
    avg_importance: float
    max_importance: float
    hebbian_edges_updated: int

    # === R2 SUMMARY ===
    episodes_formed: int
    avg_episode_size: float
    noise_events: int

    # === R3 SUMMARY ===
    action_counts: Dict[str, int]    # REINFORCE/EXTEND/CREATE/PRUNE/SKIP
    duplicates_merged: int
    archived_count: int
    pruned_count: int

    # === R4 SUMMARY ===
    entities_created: int
    entities_updated: int
    edges_created: int
    edges_updated: int
    gaps_detected: int

    # === R5 SUMMARY ===
    r5_executed: bool
    insights_generated: int
    counterfactuals_generated: int
    prospective_memories: int

    # === R7 SUMMARY ===
    writes_committed: int
    writes_failed: int
    layers_written: List[str]

    # === STATUS ===
    status: str                      # "COMPLETE" / "PARTIAL" / "FAILED"
    errors: List[Dict[str, str]]     # Serialized P03Error list

    @classmethod
    def from_envelope(cls, envelope: P03BatchEnvelope) -> "P03CycleSummary":
        """Generate summary from completed envelope."""
        return cls(
            # Identification
            cycle_id=envelope.context.cycle_id,
            batch_id=envelope.context.batch_id,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            trace_id=envelope.context.trace_id,

            # Timing
            started_at=envelope.context.triggered_at,
            completed_at=int(time.time() * 1000),
            total_duration_ms=sum(envelope.phase_timings.values()),
            phase_timings=dict(envelope.phase_timings),

            # Batch metrics
            events_input=envelope.context.batch_size,
            events_processed=len([e for e in envelope.events if e.write_success]),
            events_failed=len([e for e in envelope.events if e.write_error]),

            # R1
            avg_importance=envelope.phases.r1_avg_importance,
            max_importance=envelope.phases.r1_max_importance,
            hebbian_edges_updated=envelope.phases.r1_hebbian_edge_count,

            # R2
            episodes_formed=envelope.phases.r2_cluster_count,
            avg_episode_size=envelope.phases.r2_avg_cluster_size,
            noise_events=len(envelope.phases.r2_noise_event_ids),

            # R3
            action_counts=envelope.get_action_counts(),
            duplicates_merged=len(envelope.phases.r3_dedup_merges),
            archived_count=len(envelope.phases.r3_archive_candidates),
            pruned_count=len(envelope.phases.r3_prune_candidates),

            # R4
            entities_created=len(envelope.phases.r4_new_entities),
            entities_updated=len(envelope.phases.r4_updated_entities),
            edges_created=len(envelope.phases.r4_new_edges),
            edges_updated=len(envelope.phases.r4_updated_edges),
            gaps_detected=len(envelope.phases.r4_gap_candidates),

            # R5
            r5_executed=not envelope.phases.r5_skipped,
            insights_generated=len(envelope.phases.r5_insights),
            counterfactuals_generated=len(envelope.phases.r5_counterfactuals),
            prospective_memories=len(envelope.phases.r5_prospective_memories),

            # R7
            writes_committed=envelope.staged.total_writes(),
            writes_failed=len([e for e in envelope.events if e.write_error]),
            layers_written=cls._get_written_layers(envelope),

            # Status
            status=envelope.current_phase.value,
            errors=[
                {
                    "phase": e.phase,
                    "type": e.error_type,
                    "message": e.error_message,
                }
                for e in envelope.errors
            ],
        )

    @staticmethod
    def _get_written_layers(envelope: P03BatchEnvelope) -> List[str]:
        """Get list of layers that received writes."""
        layers = []
        if envelope.staged.st_epi_writes:
            layers.append("st_epi")
        if envelope.staged.st_sem_writes:
            layers.append("st_sem")
        if envelope.staged.st_kg_dom_writes:
            layers.append("st_kg_dom")
        if envelope.staged.st_kg_edges_writes:
            layers.append("st_kg_edges")
        if envelope.staged.st_vec_writes:
            layers.append("st_vec")
        if envelope.staged.st_prospective_writes:
            layers.append("st_prospective")
        if envelope.staged.st_social_writes:
            layers.append("st_social")
        if envelope.staged.st_procedural_writes:
            layers.append("st_procedural")
        return layers

    def to_event_payload(self) -> Dict[str, Any]:
        """Convert to event bus payload."""
        return {
            "event_type": "p03.consolidation.complete.v1",
            "cycle_id": self.cycle_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "trace_id": self.trace_id,
            "timestamp": self.completed_at,
            "summary": {
                "duration_ms": self.total_duration_ms,
                "events": {
                    "input": self.events_input,
                    "processed": self.events_processed,
                    "failed": self.events_failed,
                },
                "episodes": {
                    "formed": self.episodes_formed,
                    "avg_size": self.avg_episode_size,
                },
                "actions": self.action_counts,
                "kg": {
                    "entities_created": self.entities_created,
                    "edges_created": self.edges_created,
                    "gaps": self.gaps_detected,
                },
                "writes": self.writes_committed,
            },
            "status": self.status,
            "errors": self.errors if self.errors else None,
        }
```

---

### 24.8 Schema Version for Evolution

```python
from typing import ClassVar


@dataclass
class P03BatchEnvelope:
    """With schema versioning for envelope evolution."""

    # === SCHEMA VERSION ===
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    schema_version: str = field(default="1.0.0", init=False)

    @classmethod
    def supports_version(cls, version: str) -> bool:
        """Check if envelope supports a schema version."""
        current = tuple(map(int, cls.SCHEMA_VERSION.split(".")))
        check = tuple(map(int, version.split(".")))
        # Support same major version
        return current[0] == check[0]

    @classmethod
    def migrate(cls, old_envelope: Dict[str, Any]) -> "P03BatchEnvelope":
        """
        Migrate envelope from older schema version.

        Used when loading checkpoints from previous versions.
        """
        version = old_envelope.get("schema_version", "0.9.0")

        if version == "0.9.0":
            # Migration from 0.9.0 → 1.0.0
            # Example: hebbian_updates moved from events to phases
            for event in old_envelope.get("events", []):
                if "hebbian_updates" in event:
                    del event["hebbian_updates"]
            old_envelope["schema_version"] = "1.0.0"

        # Reconstruct envelope from migrated dict
        # (Implementation depends on full deserialization logic)
        return cls._from_dict(old_envelope)
```

---

### 24.9 Memory Pressure Tracking

```python
import sys


@dataclass
class P03BatchEnvelope:
    """With memory pressure estimation."""

    def estimate_memory_bytes(self) -> Dict[str, int]:
        """
        Estimate memory usage of envelope components.

        Returns breakdown by component for monitoring.
        """
        return {
            "context": sys.getsizeof(self.context),
            "events_base": len(self.events) * 2048,  # ~2KB per event state
            "embeddings_cached": self.embedding_cache_memory_bytes(),
            "staged_writes": self.staged.total_writes() * 512,  # ~500 bytes per write
            "phase_outputs": self._estimate_phase_outputs_size(),
            "checkpoints": len(self._checkpoints) * 256,
        }

    def total_memory_bytes(self) -> int:
        """Total estimated memory in bytes."""
        return sum(self.estimate_memory_bytes().values())

    def total_memory_mb(self) -> float:
        """Total estimated memory in megabytes."""
        return self.total_memory_bytes() / (1024 * 1024)

    def _estimate_phase_outputs_size(self) -> int:
        """Estimate size of phase outputs."""
        size = 0
        size += len(self.phases.r2_clusters) * 1024  # ~1KB per cluster
        size += len(self.phases.r4_new_entities) * 512
        size += len(self.phases.r4_new_edges) * 256
        size += len(self.phases.r5_insights) * 512
        size += len(self.phases.r1_hebbian_updates) * 128
        return size

    def is_memory_pressure_high(self, threshold_mb: float = 50.0) -> bool:
        """Check if memory usage exceeds threshold."""
        return self.total_memory_mb() > threshold_mb
```

---

### 24.10 Batch Partitioning for Parallelism

```python
from typing import Iterator


@dataclass
class P03BatchEnvelope:
    """With batch partitioning hints for parallel processing."""

    def partition_events(
        self,
        partition_size: int = 100
    ) -> Iterator[List[P03EventState]]:
        """
        Partition events for parallel processing.

        Use within phases that can parallelize per-event work:
        - R1: Importance scoring (embarrassingly parallel)
        - R3: Decay computation (per-event)

        NOT for R2 (clustering requires all embeddings) or R4 (entity resolution).
        """
        for i in range(0, len(self.events), partition_size):
            yield self.events[i:i + partition_size]

    def partition_by_content_type(self) -> Dict[str, List[P03EventState]]:
        """
        Partition by content type for specialized processing.

        Some phases may process CHAT vs CALENDAR differently.
        """
        partitions: Dict[str, List[P03EventState]] = {}
        for event in self.events:
            ct = event.content_type or "UNKNOWN"
            if ct not in partitions:
                partitions[ct] = []
            partitions[ct].append(event)
        return partitions

    def get_parallelizable_phases(self) -> List[str]:
        """Return phases that can parallelize event processing."""
        return ["R1", "R3", "R6"]

    def get_sequential_phases(self) -> List[str]:
        """Return phases requiring full batch context."""
        return ["R2", "R4", "R5", "R7", "R8"]
```

---

### 24.11 Complete Refined Envelope

Combining all refinements into a single unified dataclass:

```python
@dataclass
class P03BatchEnvelope:
    """
    Complete P03 batch envelope with all refinements.

    Includes:
    - Embedding cache with lazy loading
    - O(1) event lookup via index
    - Phase transition guards
    - Checkpoint snapshots
    - Progress tracking
    - Event filtering views
    - Memory pressure estimation
    - Batch partitioning
    - Schema versioning
    """

    # === SCHEMA ===
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    schema_version: str = field(default="1.0.0", init=False)

    # === CORE STATE ===
    context: P03CycleContext
    events: List[P03EventState] = field(default_factory=list)
    phases: P03PhaseOutputs = field(default_factory=lambda: P03PhaseOutputs())
    staged: P03StagedWrites = field(default_factory=lambda: P03StagedWrites())
    observability: P03ObservabilityContext = field(
        default_factory=lambda: P03ObservabilityContext()
    )

    # === STATE TRACKING ===
    current_phase: P03Phase = P03Phase.R0_INIT
    phase_timings: Dict[str, int] = field(default_factory=dict)
    errors: List[P03Error] = field(default_factory=list)

    # === PRIVATE: CACHES & INDEXES ===
    _embedding_cache: Dict[str, List[float]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _embedding_loader: Optional[Callable[[str], Awaitable[List[float]]]] = field(
        default=None, init=False, repr=False, compare=False
    )
    _event_index: Dict[str, int] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _checkpoints: List[PhaseCheckpoint] = field(
        default_factory=list, init=False, repr=False
    )
    _events_processed: int = field(default=0, init=False, repr=False)
    _current_phase_progress: float = field(default=0.0, init=False, repr=False)

    # === POST-INIT ===
    def __post_init__(self) -> None:
        """Build indexes after initialization."""
        self.build_event_index()

    # All methods from sections 24.1-24.10...
```

---

## 25. Updated Design Summary

### 25.1 Refinements Applied

| Refinement | Impact | Complexity |
|------------|--------|------------|
| **Embedding Cache** | Avoid redundant st_vec fetches | Low |
| **Event Index** | O(1) lookup vs O(n) scan | Low |
| **Hebbian at Batch Level** | Correct modeling (cross-event) | Medium |
| **Phase Guards** | Prevent invalid progressions | Low |
| **Checkpoints** | Recovery + debugging | Medium |
| **Progress Tracking** | Visibility for long batches | Low |
| **Event Views** | Clean filtering patterns | Low |
| **R8 Summary** | Structured emission payload | Medium |
| **Schema Version** | Future envelope evolution | Low |
| **Memory Tracking** | Prevent OOM on large batches | Low |
| **Partitioning** | Enable phase parallelism | Medium |

### 25.2 Memory Budget (Revised)

| Component | Per Event | Per Batch (1000) | Notes |
|-----------|-----------|------------------|-------|
| Event State (base) | ~2 KB | ~2 MB | Without embeddings |
| Embedding Cache | 3 KB | 3 MB | If all unique |
| Embedding Cache | 3 KB | ~500 KB | With dedup (typical) |
| Cluster metadata | - | ~100 KB | |
| Staged writes | ~500 B | ~500 KB | |
| Checkpoints | ~256 B × 9 | ~2.3 KB | Per phase |
| Hebbian updates | - | ~100 KB | Batch level |
| **Total (typical)** | - | **~3.2 MB** | With embedding dedup |
| **Total (worst)** | - | **~5.8 MB** | All unique embeddings |

### 25.3 Next Implementation Steps (Updated)

1. **Create envelope module** at `k0/modules/consolidation/envelope.py`
2. **Add unit tests** for:
   - Embedding cache hits/misses
   - Phase transition guards
   - Event index lookup
   - R8 summary generation
3. **Create ADR** `k010.x-p03-envelope-architecture.md` with all refinements
4. **Define YAML contract** for envelope schema
5. **Implement R0** using `P03EnvelopeFactory`

---

*Document Complete - Part I: Field Discovery + Part II: Envelope Architecture + Part III: Design Refinements*
