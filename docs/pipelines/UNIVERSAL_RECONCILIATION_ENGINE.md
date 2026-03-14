# Universal Reconciliation Engine -- Design & Milestones

**Status**: DESIGN PHASE
**Date**: 2026-03-13
**Owner**: P03 Consolidation Pipeline
**Scope**: All truth layers (st_epi, st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges)
**Whiteboard**: `docs/whiteboard/whiteboard_reconciliation_engine.md`
**POC Research**: `poc/reconciliation_embedding_poc/` (EXP-0 through EXP-11, reconciliation_engine.py)

---

## 1. Problem Statement

P03 consolidation has no unified reconciliation. Each phase (R2, R3, R4, R5) implements its own matching, scoring, and write-assembly logic independently. When a new batch of events arrives and R2/R3/R4/R5 produce candidates, there is no single engine that answers: "Does this already exist? If so, what do we do about it?"

### Root Causes

| ID | Root Cause |
|----|-----------|
| RC-0 | Current reconciliation is embedding-only -- cannot handle key-based layers (st_kg_dom, st_kg_edges, st_social) |
| RC-1 | TruthQueryService layer registry is incomplete -- 5 of 8+ layers, scattered duplicates |
| RC-2 | No generic truth read syscall -- 8+ bespoke syscalls with different shapes |
| RC-3 | Write assembly is per-layer hardcoded -- 12+ methods in TruthWriteAssembler |
| RC-4 | No identity strategy abstraction -- each layer answers "is this the same thing?" differently |

### Goal

One framework, any truth layer, any reconciliation action -- with zero per-layer code changes when adding new layers.

---

## 2. End-to-End Signal Flow

### 2.1 Batch Lifecycle

```
  Events arrive (batch of N)
        |
        v
  R0 -- Batch Selection & Context Hydration
  R1 -- Importance Scoring
        |
        v
  R2 -- Episodic Clustering (HDBSCAN, within-batch)
        |   produces: EpisodeCandidate[]
  R3 -- Semantic Pattern Detection (SimHash + decay)
        |   produces: PatternCandidate[]
  R4 -- Knowledge Graph Consolidation (NER + relationships)
        |   produces: EntityCandidate[], EdgeCandidate[]
  R5 -- Dream Phase (optional, counterfactual/forward/insight)
        |   produces: InsightCandidate[]
        |
        v
  ==============================
  RECONCILIATION ENGINE
  (Services 1-5, described below)
  ==============================
        |
        v
  ReconciliationResult[] containing StagedWrite[]
        |
        v
  R6 -- Staging (collect & validate all StagedWrites)
  R7 -- Truth Writer (atomic UoW transaction to database)
  R8 -- Event Emitter (bus notifications for downstream)
```

### 2.2 Concrete Example: 260 Existing Episodes + New Batch

```
TRUTH STORE: 260 episodes, ~500 patterns, ~2000 entities, ~3000 edges
NEW BATCH:   300 events

After R2/R3/R4:
  - R2 produces 60 episode candidates
  - R3 produces 15 pattern candidates
  - R4 produces 40 entity candidates + 25 edge candidates

RECONCILIATION ENGINE processes each candidate against existing truth:
  Episodes:  35 EXTEND + 3 REINFORCE + 22 CREATE  (260 -> 282 episodes)
  Patterns:   8 REINFORCE + 2 EXTEND + 5 CREATE
  Entities:  30 REINFORCE + 5 EXTEND + 5 CREATE
  Edges:     20 REINFORCE + 5 CREATE
  K1 bypass:  2 EVOLVE (correction signals) + 1 CONTRADICT (-> P06 queue)

Total: ~180 StagedWrites -> R6 -> R7 (one atomic transaction) -> R8 (bus events)
```

---

## 3. Reconciliation Actions (6 Total)

| Action | Trigger | Write Effect |
|--------|---------|-------------|
| CREATE | No match found | INSERT new row |
| REINFORCE | High-confidence match, same content | UPDATE observation_count++, last_observed_at, version++ |
| EXTEND | Medium match, new content to merge | UPDATE with merge rules (union JSON, LEAST/GREATEST temporals) |
| EVOLVE | K1 correction_signal | UPDATE old (SUPERSEDED) + INSERT new (supersedes_id = old PK) |
| CONTRADICT | K1 contradiction_signal | INSERT gap record into st_learning_queue for P06 |
| PRUNE | Timer-based temporal decay | SET status = ARCHIVED or TOMBSTONED |

---

## 4. The Five Services

### Service 1: Truth Layer Registry

**Question it answers**: "What truth layers exist and what are their schemas?"

Single source of metadata for all 7 truth layers. Each layer declares: PK column, embedding FK, identity columns, merge rules, confidence column, status column, version column, temporal columns, and flags (supports_embedding_match, supports_key_match).

**Truth Layer Matrix**:

| Layer | PK | Embedding Match | Key Match | Current Phase |
|-------|----|----|-----|------|
| st_epi | episode_id | Yes | No | R2 |
| st_sem | semantic_id | Yes | No | R3 |
| st_procedural | routine_id | Yes | Yes | R3/R5 |
| st_social | relationship_id | Yes | Yes | R3 |
| st_prospective | intention_id | Yes | No | R3/R5 |
| st_kg_dom | entity_id | Yes | Yes | R4 |
| st_kg_edges | edge_id | No | Yes | R4 |

**Location**: `k0/modules/consolidation/truth_layer_registry.py`

---

### Service 2: Truth Candidates Query

**Question it answers**: "What already exists in the database that might match this candidate?"

One unified syscall replacing 8+ bespoke query syscalls. Three query paths:

| Path | When Used | Mechanism |
|------|-----------|-----------|
| Embedding | Layers with embeddings (st_epi, st_sem, ...) | pgvector `<=>` cosine distance on st_vec join |
| Key | Layers with identity columns (st_kg_dom, st_kg_edges) | WHERE clause on identity columns |
| Hybrid | Layers with both (st_social, st_procedural) | Key narrows candidates, embedding scores them |

**Syscall**: `truth_candidates_query`
**Capability**: `truth.reconcile.read`
**Location**: `k0/kernel/syscalls.py`

---

### Service 3: Identity Strategies (x7)

**Question it answers**: "Is this candidate the SAME entity as this existing record?"

Per-layer scoring implementations behind one `IdentityStrategy` protocol:

| Layer | Strategy | Match Logic |
|-------|----------|-------------|
| st_epi | EpisodicIdentity | 11-feature logistic scorer (POC-proven, threshold=0.35) |
| st_sem | SemanticIdentity | cosine_sim * pattern_type_match_bonus |
| st_kg_dom | EntityIdentity | exact key (type:name) -> 1.0; fuzzy ILIKE -> scaled; embedding fallback |
| st_kg_edges | EdgeIdentity | compound key (source:target:type) -> 1.0; no embedding |
| st_social | SocialIdentity | participant pair match -> 1.0; embedding tiebreaker |
| st_procedural | ProceduralIdentity | routine name + time pattern -> 1.0; embedding fallback |
| st_prospective | ProspectiveIdentity | cosine_sim only |

**POC Validation**: The `EpisodicIdentity` strategy is directly derived from our reconciliation_engine.py POC:

- 11 structural features (cosine_sim, topic_overlap, participant_overlap, focus_match, social_context_match, location_match, source_type_match, sim_x_focus_match, sim_x_participant_overlap, correction_signal_any, contradiction_signal_any)
- Trained logistic regression, frozen weights
- Feature importance: topic_overlap=2.68, participant_overlap=1.30, cosine_sim=0.84, location_match=0.71
- Best threshold=0.35 (ARI=0.1660, V-measure=0.4974, accuracy=0.8094)
- Beats R2's current cosine-only cross_batch_extend.py (which requires same_thread and misses 686 unthreaded events)

**Location**: `k0/modules/consolidation/identity/`

---

### Service 4: Reconciliation Framework

**Question it answers**: "Given candidate + existing records + identity scores, what action do we take?"

Core decision machine. Two tiers:

**Tier 1 -- K1 Signals (checked FIRST)**:

- `correction_signal = true` -> EVOLVE (regardless of similarity)
- `contradiction_signal = true` -> CONTRADICT (regardless of similarity)
- P03 is a signal processor for K1 decisions, not a signal detector

**Tier 2 -- Identity Score Cascade (checked SECOND)**:

- Identity score from Service 3
- Threshold-based action selection (layer-specific thresholds from registry)
- Default: REINFORCE (high), EXTEND (medium), CREATE (low)

**Absorbed M7 Work**:

- Structured summary generation on CREATE/EXTEND/EVOLVE (M7 7.3)
- Embedding regeneration on EXTEND/EVOLVE (M7 7.4)
- Lifecycle observability counters and structured logs (M7 7.5)

**Location**: `k0/modules/consolidation/reconciliation_framework.py`

---

### Service 5: Write Decision Router

**Question it answers**: "How do we turn the action into actual SQL operations?"

Maps each action to write operations using per-layer merge rules from the registry:

| Action | Write Operation |
|--------|----------------|
| CREATE | INSERT full record |
| REINFORCE | UPDATE observation_count++, last_observed_at, version++ |
| EXTEND | UPDATE with merge rules (appendable JSON union, temporal LEAST/GREATEST, counter increment) |
| EVOLVE | UPDATE old (status=SUPERSEDED) + INSERT new (supersedes_id = old PK) |
| CONTRADICT | INSERT gap record into st_learning_queue (P06 active learning) |
| PRUNE | SET status = ARCHIVED or TOMBSTONED per decay policy |

Output: `StagedWrite[]` -- ready for R6 collection and R7 atomic execution.

**Location**: `k0/modules/consolidation/write_decision_router.py`

---

## 5. R6 -> R7 -> R8 Integration

The reconciliation engine does NOT write to the database. It produces `ReconciliationResult[]` containing `StagedWrite[]`. The existing P03 downstream phases handle the rest:

| Phase | Role | Change Required |
|-------|------|-----------------|
| R6 Staging | Collects StagedWrites from all phases, validates manifest, generates idempotency keys | Receives ReconciliationResult.staged_write instead of bespoke per-layer assembly |
| R7 Truth Writer | Executes all StagedWrites atomically via UoW (one transaction, all-or-nothing) | No change -- remains a blind StagedWrite executor |
| R8 Event Emitter | Emits bus events for each action taken | Maps reconciliation actions to event topics |

### R8 Event Topic Mapping

| Reconciliation Action | Bus Event Topic |
|----------------------|-----------------|
| CREATE | p03.truth.created.v1 |
| REINFORCE | p03.truth.reinforced.v1 |
| EXTEND | p03.truth.reinforced.v1 |
| EVOLVE | p03.truth.evolved.v1 |
| CONTRADICT | p03.gap.detected.v1 |
| PRUNE | p03.memory.pruned.v1 |

---

## 6. Universal Types

### 6.1 ReconciliationCandidate (Input to Engine)

```
ReconciliationCandidate:
    candidate_id: str
    target_layer: str                      # "st_epi", "st_kg_dom", etc.
    embedding: Optional[ndarray]           # 768-dim (None for key-only layers)
    identity_key: Optional[Dict]           # key columns for key-based match
    record_data: Dict                      # full column payload for INSERT/UPDATE
    source_phase: str                      # "R2", "R3", "R4", "R5"
    source_event_ids: List[str]            # provenance chain
    correction_signal: bool = False
    contradiction_signal: bool = False
    supersedes_concept: Optional[str] = None
```

### 6.2 ReconciliationResult (Output from Engine)

```
ReconciliationResult:
    action: ReconciliationAction           # CREATE/REINFORCE/EXTEND/EVOLVE/CONTRADICT/PRUNE
    target_layer: str
    target_record_id: Optional[str]        # existing PK (None for CREATE)
    identity_score: float
    confidence: float
    reason: str                            # human-readable explanation
    staged_write: StagedWrite              # ready for R7
```

---

## 7. Phase Migration Plan

After the engine exists, each P03 phase migrates FROM bespoke logic TO engine calls:

| Phase | Current (Bespoke) | After (Engine) |
|-------|-------------------|----------------|
| R2 | Own cross_batch_extend.py + same_thread_merge.py | `engine.reconcile(target_layer="st_epi", candidates=episode_candidates)` |
| R3 | ReconciliationEngine + TruthQueryService (partial) | `engine.reconcile_batch(candidates=pattern_candidates)` |
| R4 | Own entity matching + AmbiguousEntityResolver | `engine.reconcile(target_layer="st_kg_dom")` + `engine.reconcile(target_layer="st_kg_edges")` |
| R5 | No reconciliation on dream outputs | `engine.reconcile()` for each dream output before staging |
| R6 | 12+ per-layer assemble_*_writes methods | Receives StagedWrite[] from engine. Orchestrates only. |
| R7 | Unchanged | Unchanged -- blind StagedWrite executor |
| R8 | Unchanged | Maps reconciliation action to bus event topic |

---

## 8. Milestones

### M9.1 -- Truth Layer Registry & Contracts

Build the foundational registry that all other services depend on.

**Status**: READY TO IMPLEMENT
**Estimated Scope**: 7 YAML contracts + 1 Python module + 1 test module + cleanup
**Depends on**: Nothing (foundation for everything else)

---

#### M9.1.1 Objective

Create a single authoritative registry (`TruthLayerRegistry`) backed by 7 YAML column contracts that replaces 9 scattered layer metadata locations across the codebase. Every downstream M9 milestone (M9.2-M9.10) depends on this registry for column names, merge rules, thresholds, and layer capabilities.

---

#### M9.1.2 Deliverables

| # | Deliverable | File Path | New/Edit | Description |
|---|-----------|-----------|----------|-------------|
| D1 | st_epi column contract | `k0/contracts/schemas/st_epi.columns.yaml` | NEW | 51 columns, 6 appendable JSON fields, merge rules per column |
| D2 | st_sem column contract | `k0/contracts/schemas/st_sem.columns.yaml` | NEW | 30 columns, 4 appendable JSON fields |
| D3 | st_procedural column contract | `k0/contracts/schemas/st_procedural.columns.yaml` | NEW | 31 columns, 3 appendable JSON fields |
| D4 | st_social column contract | `k0/contracts/schemas/st_social.columns.yaml` | NEW | 42 columns, 6 appendable JSON fields |
| D5 | st_prospective column contract | `k0/contracts/schemas/st_prospective.columns.yaml` | NEW | 27 columns, 2 appendable JSON fields |
| D6 | st_kg_dom column contract | `k0/contracts/schemas/st_kg_dom.columns.yaml` | NEW | 30 columns, 5 appendable JSON fields |
| D7 | st_kg_edges column contract | `k0/contracts/schemas/st_kg_edges.columns.yaml` | NEW | 30 columns, 4 fields (2 PG arrays, not JSON) |
| D8 | TruthLayerSpec + MergeRule enum | `k0/modules/consolidation/truth_layer_registry.py` | NEW | Frozen dataclass (~25 fields) + MergeRule enum (16 values) + ReconciliationThresholds |
| D9 | TruthLayerRegistry class | `k0/modules/consolidation/truth_layer_registry.py` | NEW (same file as D8) | Loads from YAML contracts, singleton, `.get(layer)`, `.all_layers()` |
| D10 | Registry unit tests | `tests/k0/modules/consolidation/test_truth_layer_registry.py` | NEW | Lookup per layer, merge rule validation vs writer SQL, roundtrip YAML-to-spec |
| D11 | Contract validation tests | `tests/k0/contracts/test_truth_layer_contracts.py` | NEW | YAML schema structure, all 7 contracts parseable, cross-contract consistency |
| D12 | Cleanup: stale JSON schema enums | `k0/contracts/jsonschema/acl.schema.json` | EDIT | Fix st_proc -> st_procedural, st_hipp_store -> st_hipp_events, remove st_ws |
| D12b | Cleanup: stale JSON schema enums | `k0/contracts/jsonschema/archive_manifest.schema.json` | EDIT | Same enum fixes |
| D12c | Cleanup: stale JSON schema enums | `k0/contracts/jsonschema/crdt_merge_log.schema.json` | EDIT | Same enum fixes |

---

#### M9.1.3 File Location Map (Complete)

```
NEW FILES:

  k0/contracts/schemas/
      st_epi.columns.yaml             # D1: 51 columns from migrations 0027, 0061, 0083, 0084, 0086
      st_sem.columns.yaml             # D2: 30 columns from migrations 0028, 0062
      st_procedural.columns.yaml      # D3: 31 columns from migrations 0029, 0063
      st_social.columns.yaml          # D4: 42 columns from migrations 0030, 0054, 0064
      st_prospective.columns.yaml     # D5: 27 columns from migrations 0031, 0057, 0065
      st_kg_dom.columns.yaml          # D6: 30 columns from migrations 0032, 0059, 0066
      st_kg_edges.columns.yaml        # D7: 30 columns from migrations 0033, 0059, 0069, 0070

  k0/modules/consolidation/
      truth_layer_registry.py          # D8+D9: MergeRule, TruthLayerSpec, ReconciliationThresholds, TruthLayerRegistry

  tests/k0/modules/consolidation/
      test_truth_layer_registry.py     # D10: Registry unit tests

  tests/k0/contracts/
      test_truth_layer_contracts.py    # D11: Contract YAML validation tests


EXISTING FILES (EDITED):

  k0/contracts/jsonschema/
      acl.schema.json                  # D12: Fix stale layer name enums
      archive_manifest.schema.json     # D12b: Fix stale layer name enums
      crdt_merge_log.schema.json       # D12c: Fix stale layer name enums


SOURCE FILES (READ-ONLY REFERENCES -- where column definitions come from):

  k0/db/alembic/versions/
      0027_st_epi.py                   # Base st_epi schema (+ 0061, 0083, 0084, 0086 for additions)
      0028_st_sem.py                   # Base st_sem schema (+ 0062)
      0029_st_procedural.py            # Base st_procedural schema (+ 0063)
      0030_st_social.py                # Base st_social schema (+ 0054, 0064)
      0031_st_prospective.py           # Base st_prospective schema (+ 0057, 0065)
      0032_st_kg_dom.py                # Base st_kg_dom schema (+ 0059, 0066)
      0033_st_kg_edges.py              # Base st_kg_edges schema (+ 0059, 0069, 0070)

  k0/modules/consolidation/truth_writer/layers/
      episodic.py                      # Source for st_epi merge rules (REINFORCE, EXTEND, ARCHIVE, TOMBSTONE SQL)
      semantic.py                      # Source for st_sem merge rules
      procedural.py                    # Source for st_procedural merge rules
      social.py                        # Source for st_social merge rules
      prospective.py                   # Source for st_prospective merge rules
      kg.py                            # Source for st_kg_dom + st_kg_edges merge rules
      vector.py                        # Source for st_vec merge rules (already has YAML contract)

  k0/modules/consolidation/staging/
      truth_query_service.py           # 5 scattered dicts (LAYER_PK_COLUMNS, LAYER_CONFIDENCE_COLUMNS, etc.)
      truth_write_assembler.py         # 12+ bespoke assemble methods (merge rules embedded in SQL)

  k0/modules/consolidation/algorithms/
      reconciliation_engine.py         # DEFAULT_TRUTH_LAYERS (5 layers only)
      decay_engine.py                  # LAYER_LAMBDAS (8 layers, most complete decay rates)

  k0/pipelines/p03/
      staged_writes.py                 # LAYER_ST_* constants (DUPLICATED at L58-64 and L318-328)


REFERENCE CONTRACT (EXISTING -- template for new contracts):

  k0/contracts/schemas/
      st_vec_v2.columns.yaml           # Only existing truth table contract (11 columns, st_vec)
      st_hipp_events_v2.columns.yaml   # Events table contract (143 columns, for reference format)
```

---

#### M9.1.4 YAML Contract Schema (Structure for All 7 Contracts)

Each contract follows this structure. Fields are derived from migration files (column definitions) + writer files (merge behavior).

```yaml
# =============================================================================
# {table} v1.0.0 -- Truth Layer Column Contract
# =============================================================================
#
# Single source of truth for every column in {table}.
# Used by TruthLayerRegistry to build TruthLayerSpec.
#
# Migrations: {list of migration files}
# Writer: k0/modules/consolidation/truth_writer/layers/{writer}.py
# =============================================================================

schema: {table}                           # e.g. "st_epi"
version: "1.0.0"
migrations:                               # All migrations that define/modify this table
  - "0027"
  - "0061"
column_count: {N}                         # Total column count

# ---------------------------------------------------------------------------
# Layer Metadata (read by TruthLayerRegistry to build TruthLayerSpec)
# ---------------------------------------------------------------------------
layer_metadata:
  pk: {pk_column}                         # e.g. "episode_id"
  version_column: version
  supersedes_column: supersedes_id
  canonical_column: is_canonical
  observation_count_column: observation_count
  confidence_column: {col}                # "confidence_score" or "confidence"
  confidence_boost_strategy: {strategy}   # none | additive_0.05 | multiplicative_1.1 | coalesce
  archival_status_column: archival_status
  active_status_value: ACTIVE
  decay_lambda: {float}                   # From decay_engine.py LAYER_LAMBDAS

  # Matching capabilities
  embedding_fk_column: {col_or_null}      # "embedding_id" or null
  supports_embedding_match: {bool}
  supports_key_match: {bool}
  identity_columns: [{cols}]              # Columns used by IdentityStrategy for key-match

  # Write dependency order (lower = write first in R7 UoW)
  write_order: {int}                      # 1=st_vec, 2=st_kg_dom, 3=st_kg_edges, 4=st_epi, ...

  # Temporal columns (for EXTEND merge rules)
  temporal:
    start: {col_or_null}                  # LEAST on EXTEND
    end: {col_or_null}                    # GREATEST on EXTEND
    last_observed: {col}                  # GREATEST on REINFORCE/EXTEND
    first_observed: {col_or_null}         # Immutable

  # Reconciliation thresholds (from whiteboard Section 32)
  thresholds:
    reinforce: {float}                    # e.g. 0.85
    extend: {float}                       # e.g. 0.60
    evolve: {float}                       # e.g. 0.40

# ---------------------------------------------------------------------------
# Columns (with merge rule per column)
# ---------------------------------------------------------------------------
columns:

  {column_name}:
    type: {sql_type}
    nullable: {bool}
    merge: {merge_rule}                   # One of the 16 merge rule types
    # Optional fields depending on merge rule:
    cap: {int}                            # For appendable_capped
    ema_alpha: {float}                    # For ema
    description: "..."
```

---

#### M9.1.5 Merge Rule Enum (16 Types)

Complete taxonomy extracted from all 7 truth writer SQL implementations:

| MergeRule Value | SQL Behavior | Used By |
|----------------|-------------|---------|
| `IMMUTABLE` | Never changes after INSERT | All PKs, tenant_id, space_id, created_at |
| `COUNTER` | `col = col + N` | version, observation_count, interaction_count, query_count, co_occurrence_count, source_event_count |
| `REPLACED` | `col = new_value` | episode_summary, embedding_text, last_observed_at, updated_at, consolidation_cycle_id |
| `COALESCE` | `COALESCE(new, existing)` | confidence (st_prospective, st_kg_edges), various optional fields |
| `APPENDABLE_DISTINCT` | JSON array union (deduplicated) | source_events_json, participants_json, aliases_json, source_episodes_json |
| `APPENDABLE_ALL` | JSON array concat (NOT deduplicated) | action_sequence_json (st_procedural only) |
| `APPENDABLE_CAPPED` | JSON array with rolling window LIMIT N | sentiment_trajectory_json (st_social, cap=20) |
| `ADDITIVE_MERGE` | `jsonb_object_agg` (additive per key) | emotions_json (st_social only) |
| `SHALLOW_MERGE` | `existing::jsonb \|\| new::jsonb` | attributes_json (st_kg_dom), properties_json (st_kg_edges) |
| `TEMPORAL_MIN` | `LEAST(existing, new)` | start_time_utc (st_epi) |
| `TEMPORAL_MAX` | `GREATEST(existing, new)` | end_time_utc (st_epi), last_observed_at, last_interaction_at |
| `EMA` | `old * (1 - alpha) + new * alpha` | avg_sentiment (st_social, alpha=0.1) |
| `TREND` | `(new - old_avg) * beta + old_trend * (1-beta)` | emotional_valence_trend (st_social, beta=0.3) |
| `DERIVED` | Recomputed from other columns | duration_minutes = `(end - start) / 60000` (st_epi) |
| `PG_ARRAY_CONCAT` | PostgreSQL array concatenation `existing \|\| new::TEXT[]` | evidence_event_ids, evidence_episode_ids (st_kg_edges) |
| `STATUS` | Lifecycle state machine (ACTIVE->ARCHIVED->TOMBSTONE) | archival_status (all layers) |

---

#### M9.1.6 TruthLayerSpec Dataclass (Target)

```python
# k0/modules/consolidation/truth_layer_registry.py

@dataclass(frozen=True)
class ReconciliationThresholds:
    reinforce: float     # Score >= this -> REINFORCE
    extend: float        # Score >= this -> EXTEND
    evolve: float        # Score >= this -> EVOLVE (K1 signal overrides)

@dataclass(frozen=True)
class ColumnSpec:
    name: str
    sql_type: str
    nullable: bool
    merge: MergeRule
    cap: int | None = None          # For APPENDABLE_CAPPED
    ema_alpha: float | None = None  # For EMA
    description: str = ""

@dataclass(frozen=True)
class TemporalSpec:
    start: str | None       # Column for LEAST on EXTEND (e.g. "start_time_utc")
    end: str | None         # Column for GREATEST on EXTEND (e.g. "end_time_utc")
    last_observed: str      # Column for GREATEST on REINFORCE/EXTEND
    first_observed: str | None  # Immutable column

@dataclass(frozen=True)
class TruthLayerSpec:
    # Identity
    layer_name: str                    # "st_epi", "st_sem", ...
    pk_column: str                     # "episode_id", "pattern_id", ...

    # Version control
    version_column: str                # "version"
    supersedes_column: str             # "supersedes_id"
    canonical_column: str              # "is_canonical"

    # Observation tracking
    observation_count_column: str      # "observation_count"
    confidence_column: str             # "confidence_score" or "confidence"
    confidence_boost_strategy: str     # "none" | "additive_0.05" | "multiplicative_1.1" | "coalesce"

    # Lifecycle
    archival_status_column: str        # "archival_status"
    active_status_value: str           # "ACTIVE"

    # Decay
    decay_lambda: float                # From LAYER_LAMBDAS

    # Matching capabilities
    embedding_fk_column: str | None    # "embedding_id" or None
    supports_embedding_match: bool
    supports_key_match: bool
    identity_columns: tuple[str, ...]  # Columns for IdentityStrategy key-match

    # Write ordering
    write_order: int                   # Lower = written first in R7

    # Temporal
    temporal: TemporalSpec

    # Thresholds
    thresholds: ReconciliationThresholds

    # All columns with merge rules
    columns: dict[str, ColumnSpec]     # column_name -> ColumnSpec
```

---

#### M9.1.7 TruthLayerRegistry Class (Target)

```python
# k0/modules/consolidation/truth_layer_registry.py (same file)

class TruthLayerRegistry:
    """Single source of truth for all truth layer metadata.
    Loads from YAML contracts in k0/contracts/schemas/.
    Replaces 9 scattered registries across the codebase.
    """

    def __init__(self) -> None:
        self._layers: dict[str, TruthLayerSpec] = {}

    @classmethod
    def from_contracts(cls, contracts_dir: Path | None = None) -> TruthLayerRegistry:
        """Load all *.columns.yaml from contracts directory.
        Default: k0/contracts/schemas/
        Filters to truth tables only (st_epi, st_sem, st_procedural,
        st_social, st_prospective, st_kg_dom, st_kg_edges).
        """

    def get(self, layer_name: str) -> TruthLayerSpec:
        """Return spec for a layer. Raises KeyError if not registered."""

    def all_layers(self) -> list[TruthLayerSpec]:
        """All registered layer specs, sorted by write_order."""

    def truth_layer_names(self) -> frozenset[str]:
        """All registered layer names. Replaces VALID_LAYERS frozenset."""

    def merge_rules_for(self, layer_name: str) -> dict[str, MergeRule]:
        """Column -> MergeRule mapping for a layer."""

    def appendable_columns(self, layer_name: str) -> list[str]:
        """Columns with APPENDABLE_* merge rules (JSON union targets)."""
```

---

#### M9.1.8 Per-Layer Contract Summary

Concrete metadata for each of the 7 YAML contracts. All values derived from migration audit + writer SQL audit (whiteboard Sections 49-54).

**st_epi** (`k0/contracts/schemas/st_epi.columns.yaml`):

| Field | Value |
|-------|-------|
| PK | `episode_id` |
| Column count | 51 |
| Embedding FK | `embedding_id` (legacy, inline `embedding_vector` preferred) |
| Confidence column | `confidence_score` |
| Confidence boost | `none` (no boost on REINFORCE) |
| Identity columns | `[narrative_thread_id]` |
| Supports embedding match | true |
| Supports key match | false |
| Decay lambda | 0.005 |
| Write order | 4 |
| Temporal start | `start_time_utc` |
| Temporal end | `end_time_utc` |
| Last observed | `last_observed_at` |
| Thresholds | reinforce=0.85, extend=0.60, evolve=0.40 |
| JSON appendable | source_events_json, participants_json, source_texts_json, narrative_thread_ids_json, entity_ids_json, centroid_metadata_json |
| Merge strategy | All APPENDABLE_DISTINCT |
| Migrations | 0027, 0061, 0083, 0084, 0086 |
| Writer source | `k0/modules/consolidation/truth_writer/layers/episodic.py` |

**st_sem** (`k0/contracts/schemas/st_sem.columns.yaml`):

| Field | Value |
|-------|-------|
| PK | `pattern_id` |
| Column count | 30 |
| Embedding FK | `embedding_id` (legacy) |
| Confidence column | `confidence_score` |
| Confidence boost | `additive_0.05` (LEAST(confidence + 0.05, 1.0)) |
| Identity columns | `[pattern_type, category]` |
| Supports embedding match | true |
| Supports key match | false |
| Decay lambda | 0.010 |
| Write order | 5 |
| Temporal start | null |
| Temporal end | null |
| Last observed | `last_observed_at` |
| Thresholds | reinforce=0.90, extend=0.65, evolve=0.45 |
| JSON appendable | source_episodes_json, pattern_attributes_json, temporal_pattern_json, source_texts_json |
| Merge strategy | All APPENDABLE_DISTINCT |
| Migrations | 0028, 0062 |
| Writer source | `k0/modules/consolidation/truth_writer/layers/semantic.py` |

**st_procedural** (`k0/contracts/schemas/st_procedural.columns.yaml`):

| Field | Value |
|-------|-------|
| PK | `routine_id` |
| Column count | 31 |
| Embedding FK | null (inline only) |
| Confidence column | `confidence` |
| Confidence boost | `multiplicative_1.1` (LEAST(confidence * 1.1, 1.0)) |
| Identity columns | `[routine_name, location_context]` |
| Supports embedding match | true |
| Supports key match | true |
| Decay lambda | 0.020 |
| Write order | 6 |
| Temporal start | null |
| Temporal end | null |
| Last observed | `last_observed_at` |
| Thresholds | reinforce=0.90, extend=0.70, evolve=0.50 |
| JSON appendable | source_episodes_json (DISTINCT), action_sequence_json (ALL -- not deduped), source_texts_json (DISTINCT) |
| Special merge | `temporal_regularity` = EMA (moving average on REINFORCE) |
| Migrations | 0029, 0063 |
| Writer source | `k0/modules/consolidation/truth_writer/layers/procedural.py` |

**st_social** (`k0/contracts/schemas/st_social.columns.yaml`):

| Field | Value |
|-------|-------|
| PK | `relationship_id` |
| Column count | 42 |
| Embedding FK | null (inline only) |
| Confidence column | `confidence` (also has `relationship_strength` as domain-specific) |
| Confidence boost | `multiplicative_1.1` (LEAST(relationship_strength * 1.1, 1.0)) |
| Identity columns | `[actor_a_id, actor_b_id]` (UNIQUE constraint: tenant_id/actor_a_id/actor_b_id/is_canonical) |
| Supports embedding match | true |
| Supports key match | true |
| Decay lambda | 0.050 |
| Write order | 7 |
| Temporal start | `first_interaction_at` |
| Temporal end | null |
| Last observed | `last_interaction_at` |
| Thresholds | reinforce=0.85, extend=0.60, evolve=0.40 |
| JSON appendable | source_episodes_json (DISTINCT), interaction_modalities_json (DISTINCT), typical_activities_json (DISTINCT), sentiment_trajectory_json (CAPPED 20), emotions_json (ADDITIVE_MERGE), source_texts_json (DISTINCT) |
| Special merge | avg_sentiment=EMA(alpha=0.1), emotional_valence_trend=TREND(beta=0.3), relationship_strength DECAY(*0.95) |
| Migrations | 0030, 0054, 0064 |
| Writer source | `k0/modules/consolidation/truth_writer/layers/social.py` |

**st_prospective** (`k0/contracts/schemas/st_prospective.columns.yaml`):

| Field | Value |
|-------|-------|
| PK | `intention_id` |
| Column count | 27 |
| Embedding FK | null (inline only) |
| Confidence column | `confidence_score` (also has `inference_confidence`) |
| Confidence boost | `coalesce` (COALESCE(new, existing)) |
| Identity columns | `[]` (no key match, embedding only) |
| Supports embedding match | true |
| Supports key match | false |
| Decay lambda | 0.100 |
| Write order | 8 |
| Temporal start | null |
| Temporal end | null |
| Last observed | `updated_at` |
| Thresholds | reinforce=0.90, extend=0.65, evolve=0.45 |
| JSON appendable | inferred_from_json (COALESCE), source_texts_json (DISTINCT) |
| Special | Has BOTH `status` (ACTIVE/COMPLETED/ABANDONED/DEFERRED) AND `archival_status` (ACTIVE/ARCHIVED/TOMBSTONE) |
| Migrations | 0031, 0057, 0065 |
| Writer source | `k0/modules/consolidation/truth_writer/layers/prospective.py` |

**st_kg_dom** (`k0/contracts/schemas/st_kg_dom.columns.yaml`):

| Field | Value |
|-------|-------|
| PK | `entity_id` |
| Column count | 30 |
| Embedding FK | `embedding_id` (legacy) |
| Confidence column | `confidence` |
| Confidence boost | `multiplicative_1.1` (LEAST(confidence * 1.1, 1.0)) |
| Identity columns | `[entity_type, canonical_name]` |
| Supports embedding match | true |
| Supports key match | true |
| Decay lambda | 0.001 |
| Write order | 2 |
| Temporal start | null |
| Temporal end | null |
| Last observed | `last_observed_at` |
| Thresholds | reinforce=0.90, extend=0.65, evolve=0.45 |
| JSON appendable | aliases_json (DISTINCT), attributes_json (SHALLOW_MERGE), source_episodes_json (DISTINCT), milestones_json (APPENDABLE_ALL), source_texts_json (DISTINCT) |
| Special | QUERY_BOOST action: query_count++, last_queried_at=now (no version check) |
| Migrations | 0032, 0059, 0066 |
| Writer source | `k0/modules/consolidation/truth_writer/layers/kg.py` |

**st_kg_edges** (`k0/contracts/schemas/st_kg_edges.columns.yaml`):

| Field | Value |
|-------|-------|
| PK | `edge_id` |
| Column count | 30 |
| Embedding FK | null (NO inline embedding, NO legacy FK) |
| Confidence column | `confidence` |
| Confidence boost | `coalesce` (COALESCE(new, existing)) |
| Identity columns | `[source_entity_id, target_entity_id, relationship_type]` |
| Supports embedding match | false |
| Supports key match | true |
| Decay lambda | 0.001 |
| Write order | 3 |
| Temporal start | null |
| Temporal end | null |
| Last observed | `last_observed_at` |
| Thresholds | reinforce=0.90, extend=0.65, evolve=0.45 |
| JSON/array fields | properties_json (SHALLOW_MERGE), source_episodes_json (APPENDABLE_DISTINCT), evidence_event_ids (PG_ARRAY_CONCAT), evidence_episode_ids (PG_ARRAY_CONCAT) |
| Special | edge_weight = absolute SET (not increment), co_occurrence_count = COUNTER |
| Migrations | 0033, 0059, 0069, 0070 |
| Writer source | `k0/modules/consolidation/truth_writer/layers/kg.py` |

---

#### M9.1.9 Execution Steps (Ordered)

| Step | Action | Input Source | Output |
|------|--------|-------------|--------|
| 1 | Write `st_epi.columns.yaml` | Migration 0027 + 0061/0083/0084/0086, episodic.py writer | `k0/contracts/schemas/st_epi.columns.yaml` |
| 2 | Write `st_sem.columns.yaml` | Migration 0028 + 0062, semantic.py writer | `k0/contracts/schemas/st_sem.columns.yaml` |
| 3 | Write `st_procedural.columns.yaml` | Migration 0029 + 0063, procedural.py writer | `k0/contracts/schemas/st_procedural.columns.yaml` |
| 4 | Write `st_social.columns.yaml` | Migration 0030 + 0054 + 0064, social.py writer | `k0/contracts/schemas/st_social.columns.yaml` |
| 5 | Write `st_prospective.columns.yaml` | Migration 0031 + 0057 + 0065, prospective.py writer | `k0/contracts/schemas/st_prospective.columns.yaml` |
| 6 | Write `st_kg_dom.columns.yaml` | Migration 0032 + 0059 + 0066, kg.py writer | `k0/contracts/schemas/st_kg_dom.columns.yaml` |
| 7 | Write `st_kg_edges.columns.yaml` | Migration 0033 + 0059 + 0069 + 0070, kg.py writer | `k0/contracts/schemas/st_kg_edges.columns.yaml` |
| 8 | Implement `MergeRule` enum | Whiteboard Section 53.4 (16 types) | `k0/modules/consolidation/truth_layer_registry.py` |
| 9 | Implement `TruthLayerSpec` frozen dataclass | Section M9.1.6 above | Same file |
| 10 | Implement `TruthLayerRegistry.from_contracts()` | YAML loader reading `k0/contracts/schemas/st_*.columns.yaml` | Same file |
| 11 | Write registry unit tests | Registry API, cross-reference with writer SQL | `tests/k0/modules/consolidation/test_truth_layer_registry.py` |
| 12 | Write contract validation tests | YAML structure, completeness, consistency | `tests/k0/contracts/test_truth_layer_contracts.py` |
| 13 | Fix stale JSON schema enums | Replace st_proc/st_hipp_store/st_ws | 3 JSON schema files in `k0/contracts/jsonschema/` |

---

#### M9.1.10 Scattered Registries Replaced

After M9.1, these 9 locations become consumers of `TruthLayerRegistry` (not deleted yet -- that happens in M9.8 phase migration):

| # | Old Registry | Location | Lines | Replaced By |
|---|-------------|----------|-------|------------|
| 1 | `LAYER_PK_COLUMNS` | `k0/modules/consolidation/staging/truth_query_service.py:46` | 5 layers | `registry.get(layer).pk_column` |
| 2 | `LAYER_CONFIDENCE_COLUMNS` | `k0/modules/consolidation/staging/truth_query_service.py:55` | 5 layers | `registry.get(layer).confidence_column` |
| 3 | `LAYER_EMBEDDING_COLUMNS` | `k0/modules/consolidation/staging/truth_query_service.py:37` | 5 layers | `registry.get(layer).embedding_fk_column` |
| 4 | `DECAY_LAYERS` | `k0/modules/consolidation/staging/truth_query_service.py:156` | 6 layers | `registry.all_layers()` filtered by `decay_lambda > 0` |
| 5 | `LAYER_ENTITY_TYPE_COLUMNS` | `k0/modules/consolidation/staging/truth_query_service.py:164` | 5 layers | `registry.get(layer).identity_columns` |
| 6 | `LAYER_LAMBDAS` | `k0/modules/consolidation/algorithms/decay_engine.py:37` | 8 layers | `registry.get(layer).decay_lambda` |
| 7 | `DEFAULT_TRUTH_LAYERS` | `k0/modules/consolidation/algorithms/reconciliation_engine.py:70` | 5 layers | `registry.truth_layer_names()` (all 7) |
| 8 | `LAYER_ST_*` (first set) | `k0/pipelines/p03/staged_writes.py:58-64` | 7 constants | `registry.truth_layer_names()` |
| 9 | `LAYER_ST_*` (duplicate) | `k0/pipelines/p03/staged_writes.py:318-328` | 11 constants | Same -- **delete duplicates** |

---

#### M9.1.11 Validation Criteria (Exit Gates)

| # | Criterion | How to Verify |
|---|----------|---------------|
| V1 | All 7 YAML contracts exist and parse | `test_truth_layer_contracts.py` loads each YAML |
| V2 | Every column in every migration appears in its contract | Cross-reference migration columns vs YAML columns |
| V3 | `TruthLayerRegistry.from_contracts()` returns 7 layers | `test_truth_layer_registry.py::test_all_layers_count` |
| V4 | `registry.get("st_epi").pk_column == "episode_id"` | Per-layer lookup tests |
| V5 | `registry.get("st_epi").confidence_column == "confidence_score"` | Inconsistency resolved per contract |
| V6 | `registry.get("st_social").confidence_column == "confidence"` | Confirms split is declared |
| V7 | `len(MergeRule) == 16` | Enum completeness test |
| V8 | All appendable columns in contract match writer EXTEND SQL | Cross-reference test |
| V9 | `registry.all_layers()` sorted by write_order matches R7 execution order | vec(1) < kg_dom(2) < kg_edges(3) < epi(4) < sem(5) < proc(6) < social(7) < prosp(8) |
| V10 | Stale JSON schema enums fixed | grep for st_proc, st_hipp_store, st_ws returns 0 matches |
| V11 | No duplicate LAYER_ST_* constants | staged_writes.py L58-64 set deleted or refactored |

---

#### M9.1.12 What M9.1 Does NOT Do

| Out of Scope | Why | When |
|-------------|-----|------|
| Replace scattered registries in existing code | Risk: changing consumers while building foundation | M9.8 (phase migration) |
| Add truth-write syscalls | Separate concern from registry | Post-M9 (deferred) |
| Build IdentityStrategy protocol | Depends on registry being done first | M9.2 |
| Build truth_candidates_query syscall | Depends on registry for SQL construction | M9.3 |
| Delete old TruthWriteAssembler | Still in use by R6 until M9.8 | M9.8 |
| Delete old ReconciliationEngine | Still in use by P03 until M9.4 replaces it | M9.4+M9.8 |

---

### M9.2 -- Identity Strategy Protocol & Episodic Implementation

Build the identity scoring abstraction and implement EpisodicIdentity first (POC-proven).

**Status**: READY TO IMPLEMENT
**Estimated Scope**: 1 protocol + 1 implementation + frozen model + tests + golden data
**Depends on**: M9.1 (TruthLayerSpec for column references, TruthLayerRegistry for layer lookup)
**POC Source**: `poc/reconciliation_embedding_poc/experiments/reconciliation_engine.py`

---

#### M9.2.1 Objective

Create the `IdentityStrategy` protocol that all 7 truth layers implement to answer: "Is this candidate the SAME entity as this existing record?" Then implement `EpisodicIdentity` -- the POC-proven 11-feature logistic scorer -- as the first concrete strategy. This is the only identity strategy with a trained model; the other 6 strategies (M9.7) are rule-based.

---

#### M9.2.2 Deliverables

| # | Deliverable | File Path | New/Edit | Description |
|---|-----------|-----------|----------|-------------|
| D1 | IdentityStrategy protocol | `k0/modules/consolidation/identity/__init__.py` | NEW | Protocol class with 3 methods + IdentityResult dataclass |
| D2 | EpisodicIdentity scorer | `k0/modules/consolidation/identity/episodic.py` | NEW | 11-feature logistic scorer ported from POC |
| D3 | Feature extraction module | `k0/modules/consolidation/identity/features.py` | NEW | `event_vs_episode_features()`, `jaccard()`, FEATURE_NAMES constant |
| D4 | Frozen model weights | `k0/modules/consolidation/identity/weights/episodic_v1.json` | NEW | Serialized LogisticRegression coefficients + intercepts |
| D5 | Golden annotation set | `k0/modules/consolidation/identity/weights/golden_annotation_set.jsonl` | NEW | Copy of POC 300 labeled pairs for regression testing |
| D6 | ReconciliationCandidate type | `k0/modules/consolidation/types.py` | NEW | Universal input type to identity strategies |
| D7 | IdentityResult type | `k0/modules/consolidation/types.py` | NEW (same file) | Universal output type from identity strategies |
| D8 | K1SignalBundle type | `k0/modules/consolidation/types.py` | NEW (same file) | Frozen dataclass for correction/contradiction signals |
| D9 | Unit tests: protocol conformance | `tests/k0/modules/consolidation/identity/test_protocol.py` | NEW | Verify EpisodicIdentity satisfies protocol |
| D10 | Unit tests: feature extraction | `tests/k0/modules/consolidation/identity/test_features.py` | NEW | All 11 features individually tested |
| D11 | Unit tests: EpisodicIdentity scoring | `tests/k0/modules/consolidation/identity/test_episodic.py` | NEW | End-to-end scoring, threshold decisions, K1 bypass |
| D12 | Integration test: golden set regression | `tests/k0/modules/consolidation/identity/test_golden_regression.py` | NEW | Macro F1 >= 0.72 on golden set (regression gate) |
| D13 | Module contract | `k0/contracts/modules/consolidation.identity.v1.yaml` | NEW | Protocol definition, feature list, threshold semantics |

---

#### M9.2.3 File Location Map (Complete)

```
NEW FILES:

  k0/modules/consolidation/
      identity/
          __init__.py                   # D1: IdentityStrategy protocol + re-exports
          episodic.py                   # D2: EpisodicIdentity (11-feature logistic scorer)
          features.py                   # D3: Feature extraction (event_vs_episode_features, jaccard)
          weights/
              episodic_v1.json          # D4: Frozen model weights (coef_, intercept_, classes_)
              golden_annotation_set.jsonl # D5: 300 labeled pairs from POC
      types.py                          # D6+D7+D8: ReconciliationCandidate, IdentityResult, K1SignalBundle

  k0/contracts/modules/
      consolidation.identity.v1.yaml    # D13: Module contract

  tests/k0/modules/consolidation/identity/
      __init__.py
      test_protocol.py                  # D9: Protocol conformance
      test_features.py                  # D10: Feature extraction unit tests
      test_episodic.py                  # D11: EpisodicIdentity scoring tests
      test_golden_regression.py         # D12: Golden set regression gate


SOURCE FILES (READ-ONLY -- ported from):

  poc/reconciliation_embedding_poc/experiments/
      reconciliation_engine.py          # POC source: Event, Episode, event_vs_episode_features,
                                        #   train_scorer, ReconciliationEngine, FEATURE_NAMES
                                        #   11 features, logistic weights, process() pipeline

  poc/reconciliation_embedding_poc/data/
      golden_annotation_set.jsonl       # Training data: 300 labeled pairs (CREATE/EXTEND/REINFORCE)
      life_events_enriched.jsonl        # 1410 real events with ground-truth threads

  poc/reconciliation_embedding_poc/results/
      reconciliation_engine_results.json      # Final metrics (F1=0.7264, accuracy=0.8094)
      reconciliation_engine_decisions.jsonl   # Per-event decision log (1410 entries)
      reconciliation_threshold_sweep.json     # Threshold sweep results (0.20-0.60)


EXISTING FILES (CONSUMED -- data structures this code reads):

  k0/pipelines/p03/event_state.py             # P03EventState: embedding_768, participants_json,
                                               #   social_context, place_id, source_type,
                                               #   correction_signal, contradiction_signal,
                                               #   narrative_thread_id, entity_salience_json

  k0/pipelines/p03/phase_outputs.py           # EpisodeCandidate: centroid_embedding, temporal_start/end,
                                               #   participants_json, location_hint, activity_type,
                                               #   dominant_sentiment, summary
                                               # EpisodeCluster: member_event_ids, cohesion_score,
                                               #   centroid_embedding_id, dominant_location,
                                               #   dominant_social_context

  k0/modules/consolidation/algorithms/
      centroid_calculator.py                   # EpisodeCandidate dataclass definition (weighted centroid)
      cross_batch_extend.py                    # CrossBatchExtendMatcher (REPLACED by M9.2 in M9.8)
      reconciliation_engine.py                 # Existing ReconciliationEngine (REPLACED by M9.4 in M9.8)

  k0/modules/consolidation/staging/
      truth_query_service.py                   # TruthCandidate dataclass (consumed by scorer)

  k0/db/alembic/versions/
      0085_st_hipp_events_k1_correction_signals.py  # K1 signal columns (correction_signal, etc.)

  k0/modules/consolidation/truth_layer_registry.py  # M9.1 TruthLayerRegistry (runtime dependency)
```

---

#### M9.2.4 IdentityStrategy Protocol (Target)

```python
# k0/modules/consolidation/identity/__init__.py

from typing import Protocol, runtime_checkable

@runtime_checkable
class IdentityStrategy(Protocol):
    """Per-layer identity matching logic.

    Determines whether a candidate and an existing truth record
    represent the 'same thing'. Each truth layer implements this
    differently based on its identity semantics.

    The protocol has two paths:
    - score_identity(): Full scoring with probability distribution
    - match_key(): Fast key-based pre-filter (optional, for key-match layers)
    """

    @property
    def layer_name(self) -> str:
        """Which truth layer this strategy serves (e.g. 'st_epi')."""
        ...

    def score_identity(
        self,
        candidate: "ReconciliationCandidate",
        existing: "TruthRecord",
        cosine_sim: float,
    ) -> "IdentityResult":
        """Score how likely candidate and existing are the same entity.

        Args:
            candidate: New record from R2/R3/R4/R5 phase output
            existing: Record already in truth table (from truth_candidates_query)
            cosine_sim: Pre-computed cosine similarity between embeddings

        Returns:
            IdentityResult with score, action probabilities, and features used
        """
        ...

    def match_key(
        self,
        candidate: "ReconciliationCandidate",
        existing: "TruthRecord",
    ) -> bool | None:
        """Fast key-based identity check (optional).

        Returns:
            True  = definite key match (skip embedding scoring)
            False = definite key mismatch (skip this candidate)
            None  = inconclusive (proceed to score_identity)

        Layers with supports_key_match=False should return None always.
        """
        ...
```

---

#### M9.2.5 Core Types (ReconciliationCandidate, IdentityResult, K1SignalBundle)

```python
# k0/modules/consolidation/types.py

@dataclass(frozen=True)
class K1SignalBundle:
    """K1 correction/contradiction signals carried per-event."""
    correction_signal: bool = False
    contradiction_signal: bool = False
    supersedes_concept: str = ""
    correction_source: str = ""       # user_explicit | implicit | context_change
    session_context_id: str = ""

@dataclass(frozen=True)
class ReconciliationCandidate:
    """Universal input to identity strategies and reconciliation framework.

    Built from phase outputs (R2 EpisodeCandidate, R3 PatternCandidate,
    R4 EntityCandidate/EdgeCandidate, R5 InsightCandidate).
    """
    # Identity
    candidate_id: str                  # ULID
    layer: str                         # Target truth layer ("st_epi", "st_sem", ...)
    source_phase: str                  # "R2", "R3", "R4", "R5"

    # Embedding (768-dim, L2-normalized)
    embedding: list[float] | None      # None for key-only layers (st_kg_edges)

    # Metadata (layer-specific, read by IdentityStrategy)
    metadata: dict[str, Any]           # Flexible per-layer data bag

    # K1 signals (Tier 1 override)
    k1_signals: K1SignalBundle = field(default_factory=K1SignalBundle)

    # Provenance
    source_event_ids: tuple[str, ...] = ()
    cycle_id: str = ""
    tenant_id: str = ""
    space_id: str = ""

@dataclass(frozen=True)
class TruthRecord:
    """Existing record from truth table (output of truth_candidates_query).

    Wraps the raw DB row with typed access to common fields.
    """
    record_id: str                     # PK value
    layer: str                         # "st_epi", "st_sem", ...
    embedding: list[float] | None      # 768-dim or None
    confidence: float                  # confidence_score or confidence
    version: int                       # Optimistic lock version
    observation_count: int
    last_observed_ms: int              # Milliseconds since epoch
    metadata: dict[str, Any]           # Full row as dict (layer-specific columns)

@dataclass(frozen=True)
class IdentityResult:
    """Output from IdentityStrategy.score_identity().

    Contains the identity score and the probability distribution
    over reconciliation actions.
    """
    # Primary score [0.0, 1.0] -- higher = more likely same entity
    score: float

    # Per-action probabilities (sum to 1.0)
    p_create: float
    p_extend: float
    p_reinforce: float

    # Recommended action (highest probability, but framework makes final call)
    recommended_action: str            # "CREATE" | "EXTEND" | "REINFORCE"

    # Features used (for observability/debugging)
    features: dict[str, float] = field(default_factory=dict)

    # Key match result (from match_key, if applicable)
    key_matched: bool | None = None    # True/False/None
```

---

#### M9.2.6 EpisodicIdentity Implementation (11-Feature Logistic Scorer)

```python
# k0/modules/consolidation/identity/episodic.py

class EpisodicIdentity:
    """Identity strategy for st_epi (episodic memory).

    Uses an 11-feature logistic regression scorer trained on 300 golden
    pairs from the POC (EXP-0 through EXP-11). The model is a 3-way
    multinomial classifier (CREATE/EXTEND/REINFORCE) with frozen weights.

    Pipeline:
      1. match_key() returns None (episodes have no key-match path)
      2. score_identity() computes 11 features -> logistic model -> probabilities
      3. p_assign = P(EXTEND) + P(REINFORCE) is the identity score
    """

    layer_name: str = "st_epi"

    def __init__(self, weights_path: Path | None = None) -> None:
        """Load frozen model weights from JSON.

        Default path: k0/modules/consolidation/identity/weights/episodic_v1.json
        """

    def score_identity(
        self,
        candidate: ReconciliationCandidate,
        existing: TruthRecord,
        cosine_sim: float,
    ) -> IdentityResult:
        """Compute 11 structural features and score via logistic model.

        Feature extraction pipeline:
          1. Extract metadata from candidate.metadata and existing.metadata
          2. Compute 11 features (see M9.2.7)
          3. Pass feature vector through frozen logistic model
          4. Return IdentityResult with probabilities

        The score field = p_extend + p_reinforce (probability of assignment).
        """

    def match_key(
        self,
        candidate: ReconciliationCandidate,
        existing: TruthRecord,
    ) -> bool | None:
        """Episodes do not support key-based matching. Always returns None."""
        return None

    def _extract_features(
        self,
        candidate: ReconciliationCandidate,
        existing: TruthRecord,
        cosine_sim: float,
    ) -> np.ndarray:
        """Compute the 11 structural features. Returns shape (11,)."""

    def _predict(self, features: np.ndarray) -> tuple[dict[str, float], str]:
        """Run frozen logistic model. Returns (prob_dict, best_action)."""
```

---

#### M9.2.7 The 11 Features (Exact Specification)

Directly ported from POC `event_vs_episode_features()`. Feature index order is locked.

| Index | Feature Name | Computation | Input: candidate.metadata | Input: existing.metadata |
|-------|-------------|-------------|--------------------------|--------------------------|
| 0 | `cosine_sim` | Pre-computed cosine similarity (passed as arg) | `embedding` | `embedding` |
| 1 | `topic_overlap` | `jaccard(candidate_topics, existing_topics)` | `topics: set[str]` | `topics: set[str]` (from extracted_relations/source_texts) |
| 2 | `participant_overlap` | `jaccard(candidate_participants, existing_participants)` | `participants: set[str]` (from participants_json) | `participants: set[str]` (from participants_json) |
| 3 | `focus_match` | `1.0 if candidate_focal == existing_focal else 0.0` | `focal: str` (from entity_salience_json max) | `focal: str` (from episode aggregated focal) |
| 4 | `social_context_match` | `1.0 if candidate_social == existing_social else 0.0` | `social_context: str` | `social_context: str` (dominant_social_context) |
| 5 | `location_match` | `1.0 if candidate_place_id in existing_locations else 0.0` | `place_id: str` | `locations: set[str]` (from location_hint/place_ids) |
| 6 | `source_type_match` | `1.0 if candidate_source_type in existing_source_types else 0.0` | `source_type: str` | `source_types: set[str]` |
| 7 | `sim_x_focus_match` | `cosine_sim * focus_match` | (derived) | (derived) |
| 8 | `sim_x_participant_overlap` | `cosine_sim * participant_overlap` | (derived) | (derived) |
| 9 | `correction_signal_any` | `float(candidate.k1_signals.correction_signal)` | K1SignalBundle | N/A |
| 10 | `contradiction_signal_any` | `float(candidate.k1_signals.contradiction_signal)` | K1SignalBundle | N/A |

**Feature importance ranking** (from EXP-9, mean |coefficient| across 3 classes):

| Rank | Feature | Mean |coef| | Significance |
|------|---------|--------------|--------------|
| 1 | topic_overlap | 2.68 | Most discriminative feature |
| 2 | participant_overlap | 1.30 | Second most important |
| 3 | cosine_sim | 0.84 | Embedding similarity |
| 4 | location_match | 0.71 | Spatial context |
| 5 | social_context_match | 0.69 | Social setting |
| 6 | sim_x_participant_overlap | 0.63 | Interaction term |
| 7 | source_type_match | 0.34 | Source modality |
| 8 | focus_match | 0.12 | Focal person |
| 9 | sim_x_focus_match | 0.08 | Interaction term |
| 10 | correction_signal_any | 0.00 | K1 override (bypassed before scoring) |
| 11 | contradiction_signal_any | 0.00 | K1 override (bypassed before scoring) |

**Jaccard function** (shared in features.py):

```python
def jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0
```

---

#### M9.2.8 Frozen Model Weights (episodic_v1.json)

Serialized from POC `sklearn.linear_model.LogisticRegression`:

```json
{
  "model_version": "episodic_v1",
  "source": "poc/reconciliation_embedding_poc/experiments/reconciliation_engine.py",
  "training_date": "2026-03-12",
  "golden_set_size": 300,
  "cv_macro_f1": 0.7264,
  "accuracy": 0.8094,
  "optimal_threshold": 0.35,
  "feature_names": [
    "cosine_sim", "topic_overlap", "participant_overlap",
    "focus_match", "social_context_match", "location_match",
    "source_type_match", "sim_x_focus_match",
    "sim_x_participant_overlap",
    "correction_signal_any", "contradiction_signal_any"
  ],
  "classes": ["CREATE", "EXTEND", "REINFORCE"],
  "coefficients": [
    [-0.1802, -1.9086, -0.3295, -0.1217, -0.5942, -0.3319,  0.3372, -0.0788, -0.4325, 0.0, 0.0],
    [-0.3598,  0.4917,  0.8454,  0.0350, -0.1099, -0.0347, -0.2708,  0.0529,  0.0106, 0.0, 0.0],
    [ 0.5400,  1.4169, -0.5159,  0.0867,  0.7041,  0.3666, -0.0664,  0.0259,  0.6274, 0.0, 0.0]
  ],
  "intercepts": [0.0, 0.0, 0.0],
  "solver": "lbfgs",
  "multi_class": "multinomial",
  "class_weight": "balanced",
  "max_iter": 1000
}
```

**Runtime loading**: `EpisodicIdentity.__init__()` reads this JSON and reconstructs the linear model. No sklearn dependency at runtime -- inference is:

```python
logits = features @ coef.T + intercept  # shape (3,)
exp_logits = np.exp(logits - logits.max())
proba = exp_logits / exp_logits.sum()   # softmax -> P(CREATE), P(EXTEND), P(REINFORCE)
```

This avoids sklearn as a production dependency. Only numpy is needed.

---

#### M9.2.9 Metadata Extraction: P03EventState -> ReconciliationCandidate

How phase outputs map to ReconciliationCandidate.metadata for st_epi:

```python
# Called in R2 after HDBSCAN clustering produces EpisodeCandidate

def episode_candidate_to_reconciliation_candidate(
    episode: EpisodeCandidate,
    events: list[P03EventState],
    cycle_ctx: P03CycleContext,
) -> ReconciliationCandidate:
    """Convert R2 output to universal reconciliation input."""

    # Aggregate metadata from member events
    all_topics = set()
    all_participants = set()
    focal_counter = Counter()
    social_contexts = Counter()
    locations = set()
    source_types = set()
    has_correction = False
    has_contradiction = False

    for ev in events:
        all_topics.update(json.loads(ev.extracted_relations_json or "[]"))
        all_participants.update(json.loads(ev.participants_json or "[]"))
        focal = _extract_focal(ev.entity_salience_json)
        if focal:
            focal_counter[focal] += 1
        if ev.social_context:
            social_contexts[ev.social_context] += 1
        if ev.place_id:
            locations.add(ev.place_id)
        if ev.source_type:
            source_types.add(ev.source_type)
        has_correction = has_correction or ev.correction_signal
        has_contradiction = has_contradiction or ev.contradiction_signal

    return ReconciliationCandidate(
        candidate_id=episode.cluster_id,
        layer="st_epi",
        source_phase="R2",
        embedding=episode.centroid_embedding,
        metadata={
            "topics": all_topics,
            "participants": all_participants,
            "focal": focal_counter.most_common(1)[0][0] if focal_counter else "",
            "social_context": social_contexts.most_common(1)[0][0] if social_contexts else "",
            "place_id": next(iter(locations), ""),
            "locations": locations,
            "source_type": next(iter(source_types), ""),
            "source_types": source_types,
            "temporal_start": episode.temporal_start,
            "temporal_end": episode.temporal_end,
            "dominant_thread": episode.dominant_thread_id if hasattr(episode, 'dominant_thread_id') else "",
            "cohesion_score": episode.cohesion_score,
            "event_count": episode.event_count,
        },
        k1_signals=K1SignalBundle(
            correction_signal=has_correction,
            contradiction_signal=has_contradiction,
        ),
        source_event_ids=tuple(episode.event_ids),
        cycle_id=cycle_ctx.cycle_id,
        tenant_id=cycle_ctx.tenant_id,
        space_id=cycle_ctx.space_id,
    )
```

**Existing TruthRecord metadata** (from truth_candidates_query for st_epi):

```python
# Fields extracted from st_epi row into TruthRecord.metadata:
{
    "topics": set,              # Parsed from source_texts_json or narrative topics
    "participants": set,        # Parsed from participants_json
    "focal": str,               # Derived from entity salience aggregation
    "social_context": str,      # Stored in episode metadata
    "locations": set,           # Parsed from location fields
    "source_types": set,        # Parsed from source event types
    "temporal_start": int,      # start_time_utc (ms)
    "temporal_end": int,        # end_time_utc (ms)
    "dominant_thread": str,     # narrative_thread_id
}
```

---

#### M9.2.10 What EpisodicIdentity Replaces

| Current Code | File | What It Does | M9.2 Replacement |
|-------------|------|-------------|-----------------|
| `CrossBatchExtendMatcher.find_best_match()` | `k0/modules/consolidation/algorithms/cross_batch_extend.py:193` | Cosine >= 0.60 + same thread + 7-day window | `EpisodicIdentity.score_identity()` with 11 features (strictly better) |
| `ReconciliationEngine._score_candidates()` | `k0/modules/consolidation/algorithms/reconciliation_engine.py:280` | Cosine-only scoring against 5 layers | `EpisodicIdentity.score_identity()` for st_epi layer |
| `TruthCandidate.similarity` field | `k0/modules/consolidation/staging/truth_query_service.py:52` | Single cosine float | `IdentityResult.score` + full probability distribution |

**Key improvements over current code**:

| Limitation | Current | M9.2 |
|-----------|---------|------|
| Features | Cosine only (1 signal) | 11 structural features (topic, participant, location, social, source, focal + interactions) |
| Model | Heuristic thresholds (0.85/0.60/0.40) | Trained logistic regression (CV F1=0.7264) |
| Unthreaded events | CrossBatchExtend requires same_thread -> misses 686/1410 events | Works without thread_id (topic_overlap is #1 feature) |
| Temporal gating | Hard 7-day window | No temporal feature (EXP-5: temporal is noise) |
| Probabilities | Binary match/no-match | Full 3-way probability (P_CREATE, P_EXTEND, P_REINFORCE) |
| Threshold | Fixed 0.60 cosine | Learned 0.35 on p_assign (optimal from sweep) |

---

#### M9.2.11 Scoring Pipeline (End-to-End)

```
ReconciliationCandidate (from R2 EpisodeCandidate)
    |
    v
[1. K1 Signal Check]  (done by ReconciliationFramework, NOT by EpisodicIdentity)
    if correction_signal -> EVOLVE (bypass identity scoring entirely)
    if contradiction_signal -> CONTRADICT (bypass identity scoring entirely)
    |
    v  (only if no K1 signals)
[2. Truth Candidates Query]  (M9.3 syscall, returns top-K existing records)
    SELECT from st_epi JOIN st_vec
    ORDER BY cosine_distance ASC
    LIMIT K (default 5)
    -> List[TruthRecord]
    |
    v
[3. EpisodicIdentity.score_identity()]  (called once per candidate-record pair)
    for each TruthRecord in top-K:
        a. Extract 11 features:
           features[0]  = cosine_sim (pre-computed, passed as arg)
           features[1]  = jaccard(candidate.topics, existing.topics)
           features[2]  = jaccard(candidate.participants, existing.participants)
           features[3]  = 1.0 if candidate.focal == existing.focal else 0.0
           features[4]  = 1.0 if candidate.social == existing.social else 0.0
           features[5]  = 1.0 if candidate.place_id in existing.locations else 0.0
           features[6]  = 1.0 if candidate.source in existing.sources else 0.0
           features[7]  = features[0] * features[3]
           features[8]  = features[0] * features[2]
           features[9]  = float(candidate.k1_signals.correction_signal)
           features[10] = float(candidate.k1_signals.contradiction_signal)

        b. Logistic inference (no sklearn):
           logits = features @ coef.T + intercept    # shape (3,)
           proba  = softmax(logits)                   # P(CREATE), P(EXTEND), P(REINFORCE)

        c. Compute identity score:
           score = proba[EXTEND] + proba[REINFORCE]   # p_assign

        d. Return IdentityResult(
               score=score,
               p_create=proba[CREATE],
               p_extend=proba[EXTEND],
               p_reinforce=proba[REINFORCE],
               recommended_action=argmax(proba),
               features={name: val for name, val in zip(FEATURE_NAMES, features)},
           )
    |
    v
[4. ReconciliationFramework.decide()]  (M9.4, consumes IdentityResult)
    Select best IdentityResult by score
    Apply threshold: score > 0.35 -> EXTEND or REINFORCE
    Otherwise -> CREATE
```

---

#### M9.2.12 Execution Steps (Ordered)

| Step | Action | Input Source | Output |
|------|--------|-------------|--------|
| 1 | Create `k0/modules/consolidation/types.py` | Whiteboard Section 43.5 + this plan | ReconciliationCandidate, TruthRecord, IdentityResult, K1SignalBundle |
| 2 | Create `k0/modules/consolidation/identity/__init__.py` | This plan M9.2.4 | IdentityStrategy protocol |
| 3 | Create `k0/modules/consolidation/identity/features.py` | POC `event_vs_episode_features()` | Feature extraction, jaccard, FEATURE_NAMES |
| 4 | Export frozen weights from POC model | `poc/.../reconciliation_engine.py` train output | `k0/modules/consolidation/identity/weights/episodic_v1.json` |
| 5 | Copy golden annotation set | `poc/.../data/golden_annotation_set.jsonl` | `k0/modules/consolidation/identity/weights/golden_annotation_set.jsonl` |
| 6 | Create `k0/modules/consolidation/identity/episodic.py` | POC ReconciliationEngine.process() + this plan | EpisodicIdentity class |
| 7 | Write protocol conformance tests | IdentityStrategy protocol definition | `tests/.../test_protocol.py` |
| 8 | Write feature extraction tests | 11 features individually | `tests/.../test_features.py` |
| 9 | Write EpisodicIdentity scoring tests | End-to-end scoring pipeline | `tests/.../test_episodic.py` |
| 10 | Write golden set regression test | Golden annotation data + frozen weights | `tests/.../test_golden_regression.py` |
| 11 | Create module contract | Protocol + feature + threshold spec | `k0/contracts/modules/consolidation.identity.v1.yaml` |

---

#### M9.2.13 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| No sklearn at runtime | Implement softmax inference with numpy only | Smaller dependency footprint, faster cold-start |
| Frozen weights as JSON | Not pickle/joblib | Human-readable, auditable, no deserialization risk |
| 11 features locked | Same as POC, no additions | POC-proven, adding features requires retraining |
| Threshold = 0.35 | From sweep, not tunable at runtime | Optimal V-measure=0.4974, accuracy=0.8094 |
| K1 bypass in framework, NOT in strategy | EpisodicIdentity does not check K1 signals | Separation of concerns: strategy scores, framework decides |
| ReconciliationCandidate.metadata is dict | Not typed per-layer dataclass | Keeps protocol generic; each strategy knows its own keys |
| match_key() returns None for episodes | Episodes have no natural key | Key match is for st_kg_dom (entity_type:canonical_name), st_kg_edges (source:target:type) |
| Golden set copied to production tree | Not referenced from poc/ | Production tests must not depend on POC directory structure |

---

#### M9.2.14 Metadata Key Contract (Per Layer)

Each IdentityStrategy expects specific keys in `ReconciliationCandidate.metadata` and `TruthRecord.metadata`. This is the contract for st_epi (M9.2) and preview for M9.7 layers:

**st_epi (M9.2 -- this milestone)**:

| metadata key | Type | Source (candidate) | Source (existing) |
|-------------|------|-------------------|-------------------|
| `topics` | `set[str]` | Union of member event extracted_relations | Parsed from episode source_texts/topics |
| `participants` | `set[str]` | Union of member event participants_json | Parsed from participants_json |
| `focal` | `str` | Most common entity from entity_salience_json | Episode aggregated focal |
| `social_context` | `str` | Most common social_context from events | dominant_social_context |
| `place_id` | `str` | First place_id from events | location_hint |
| `locations` | `set[str]` | All place_ids from events | All location fields |
| `source_type` | `str` | First source_type from events | Episode source_type |
| `source_types` | `set[str]` | All source_types from events | All source types |
| `temporal_start` | `int` | episode.temporal_start (ms) | start_time_utc (ms) |
| `temporal_end` | `int` | episode.temporal_end (ms) | end_time_utc (ms) |
| `dominant_thread` | `str` | Episode dominant_thread_id | narrative_thread_id |

**Preview -- st_kg_dom (M9.7)**:

| metadata key | Type | Note |
|-------------|------|------|
| `entity_type` | `str` | PERSON, PLACE, ORG, etc. |
| `canonical_name` | `str` | Normalized entity name |
| `aliases` | `set[str]` | Known aliases |

**Preview -- st_kg_edges (M9.7)**:

| metadata key | Type | Note |
|-------------|------|------|
| `source_entity_id` | `str` | Source entity PK |
| `target_entity_id` | `str` | Target entity PK |
| `relationship_type` | `str` | PARENT_OF, FRIEND_OF, etc. |

---

#### M9.2.15 Validation Criteria (Exit Gates)

| # | Criterion | How to Verify |
|---|----------|---------------|
| V1 | `EpisodicIdentity` satisfies `IdentityStrategy` protocol | `isinstance(EpisodicIdentity(...), IdentityStrategy)` passes |
| V2 | 11 features computed correctly | Unit tests for each feature with known inputs |
| V3 | Frozen weights loaded correctly | `coef_.shape == (3, 11)`, `intercept_.shape == (3,)` |
| V4 | Softmax output sums to 1.0 | Property test: `abs(sum(proba) - 1.0) < 1e-6` |
| V5 | Golden set regression: macro F1 >= 0.72 | `test_golden_regression.py` loads 300 pairs, scores, asserts |
| V6 | K1 signals NOT checked by strategy | `score_identity()` ignores correction_signal (framework does it) |
| V7 | `match_key()` returns None for episodes | Direct assertion |
| V8 | No sklearn import in production code | grep for `sklearn` in `k0/modules/consolidation/identity/` returns 0 |
| V9 | Threshold 0.35 produces 118 episodes on reference corpus | Regression against POC results |
| V10 | `ReconciliationCandidate` is frozen | `frozen=True` on dataclass |
| V11 | `IdentityResult.features` contains all 11 feature names | Dict keys match FEATURE_NAMES |

---

#### M9.2.16 What M9.2 Does NOT Do

| Out of Scope | Why | When |
|-------------|-----|------|
| Implement other 6 identity strategies | Each layer has different semantics | M9.7 |
| Build truth_candidates_query syscall | Separate service (query path) | M9.3 |
| Build ReconciliationFramework | Separate service (decision orchestrator) | M9.4 |
| Replace CrossBatchExtendMatcher in R2 | Migration happens after all services built | M9.8 |
| Replace ReconciliationEngine in R3 | Same as above | M9.8 |
| Retrain model | Frozen weights from POC are production-ready | Future (if new data available) |
| Add temporal distance feature | EXP-5 proved temporal distance is noise | Never (unless re-evaluated) |

---

### M9.3 -- Truth Candidates Query Syscall

Build the unified read path replacing 8+ bespoke query syscalls.

**Status**: READY TO IMPLEMENT
**Estimated Scope**: 1 syscall + 1 query builder + 1 result mapper + tests + contract
**Depends on**: M9.1 (TruthLayerSpec for per-layer column mapping, archival rules, PK names)
**Consumed by**: M9.4 (ReconciliationFramework.reconcile() calls this syscall for candidates)

---

#### M9.3.1 Objective

Create a single `truth_candidates_query` syscall on `k0/kernel/syscalls.py` that replaces the scattered query paths across TruthQueryService, entity_merger, edge_demotion, granger_causality, and cross_batch_extend's implicit dependency. The syscall supports three query modes: **embedding** (pgvector cosine ANN), **key** (WHERE clause exact/fuzzy match), and **hybrid** (key pre-filter + embedding re-rank). All 7 truth layers are queryable through this single entry point.

---

#### M9.3.2 Current State (What Exists Today)

**TruthQueryService.find_candidates()** (`k0/modules/consolidation/staging/truth_query_service.py:238`):

- Covers 5 layers: st_epi, st_sem, st_procedural, st_social, st_prospective
- MISSING: st_kg_dom, st_kg_edges
- Fetches `top_k * 2` rows per layer with NO ORDER BY (arbitrary DB order)
- JOINs st_vec for embeddings, decodes BYTEA via struct.unpack
- Computes cosine similarity in Python post-fetch
- **LATENT BUG**: After migration 0071, st_vec.vector is VECTOR(768) (asyncpg returns string), but code uses struct.unpack for bytes

**Bespoke syscalls** (in `k0/kernel/syscalls.py`):

| Syscall | Line | Table | Query Mode | Used By |
|---------|------|-------|-----------|---------|
| `episodes_query` | 3318 | st_epi + st_observations | Full scan, ORDER start_time DESC | R5 |
| `procedural_memory_query` | 3461 | st_procedural | Full scan, ORDER regularity_score DESC | R5 |
| `semantic_schema_query` | 3593 | st_sem | Filter by pattern_type + min_confidence | R5 |
| `kg_entities_lookup` | 3852 | st_kg_dom | Full scan -> dict by TYPE:name_lower | R4 |
| `kg_edges_lookup` | 3749 | st_kg_edges | Full scan -> dict by sorted_src:sorted_tgt | R4 |
| `kg_candidates_fuzzy_query` | 3952 | st_kg_dom | ILIKE fuzzy name match | R4 |

**Bespoke inline queries** (bypass syscalls entirely):

| File | Line | Table | Query | Phase |
|------|------|-------|-------|-------|
| `entity_merger.py` | ~517 | st_kg_dom | `SELECT * WHERE entity_id = $1` | R6 |
| `edge_demotion.py` | ~254 | st_kg_edges | `SELECT * WHERE edge_id = $1 AND edge_type IN (...)` | R4 |
| `edge_demotion.py` | ~565 | st_kg_edges | `SELECT edge_id WHERE edge_type = 'CAUSAL' AND last_used_at < $2` | R4 |
| `granger_causality.py` | ~432 | st_kg_edges | `SELECT edge_id, observation_count WHERE source = $1 AND target = $2 AND type = 'CAUSES'` | R4 |
| `cross_batch_extend.py` | ~199 | st_epi (implicit) | Caller must pre-query and pass `existing_episodes: List[Dict]` | R2 |
| `transaction.py` | ~349 | {any layer} | `SELECT version WHERE {pk_col} = $1` (OCC refresh) | R7 |

**Total: 12+ query paths** across 6 files, each with different column sets, JOIN patterns, and filter logic.

---

#### M9.3.3 Critical Bugs in Current Code (Fixed by M9.3)

| Bug | Location | Impact | Fix |
|-----|----------|--------|-----|
| B1: struct.unpack on VECTOR(768) | truth_query_service.py:435 | Runtime crash: asyncpg returns string, not bytes after M4 migration 0071 | Use json.loads for pgvector string format |
| B2: No ORDER BY on similarity query | truth_query_service.py:320 | Returns arbitrary rows, may miss best matches | Use pgvector `<=>` operator in ORDER BY |
| B3: Python-side cosine on ALL rows | truth_query_service.py:487 | Fetches 20 rows/layer * 5 layers = 100 rows, decodes ALL, then sorts | Push cosine to pgvector ANN: `ORDER BY v.vector <=> $query LIMIT K` |
| B4: HNSW index unused | st_vec migration 0071 | ix_st_vec_hnsw (m=16, ef_construction=64) exists but nothing queries it | Use `<=>` operator which triggers HNSW probe |
| B5: st_kg_dom/st_kg_edges not in find_candidates | truth_query_service.py | R4 entities/edges never scored by reconciliation engine | Unified syscall covers all 7 layers |

---

#### M9.3.4 Deliverables

| # | Deliverable | File Path | New/Edit | Description |
|---|-----------|-----------|----------|-------------|
| D1 | truth_candidates_query syscall | `k0/kernel/syscalls.py` | EDIT (append method) | Single entry point for all truth layer candidate queries |
| D2 | TruthCandidateQueryBuilder | `k0/modules/consolidation/query/builder.py` | NEW | Builds parameterized SQL per query_mode + layer |
| D3 | TruthCandidateMapper | `k0/modules/consolidation/query/mapper.py` | NEW | Maps asyncpg Row to TruthRecord (M9.2 type) |
| D4 | QueryMode enum | `k0/modules/consolidation/query/__init__.py` | NEW | EMBEDDING, KEY, HYBRID |
| D5 | TruthCandidateRequest dataclass | `k0/modules/consolidation/query/__init__.py` | NEW (same file) | Input type to syscall |
| D6 | TruthCandidateResponse dataclass | `k0/modules/consolidation/query/__init__.py` | NEW (same file) | Output type from syscall |
| D7 | Syscall contract | `k0/contracts/modules/consolidation.truth_query.v1.yaml` | NEW | Syscall definition, modes, capabilities |
| D8 | Unit tests: query builder SQL | `tests/k0/modules/consolidation/query/test_builder.py` | NEW | SQL generation for all 3 modes x 7 layers |
| D9 | Unit tests: mapper | `tests/k0/modules/consolidation/query/test_mapper.py` | NEW | Row-to-TruthRecord mapping |
| D10 | Integration test: pgvector ANN | `tests/k0/modules/consolidation/query/test_pgvector_ann.py` | NEW | HNSW cosine search against st_vec with real vectors |
| D11 | Integration test: key query | `tests/k0/modules/consolidation/query/test_key_query.py` | NEW | WHERE clause queries for st_kg_dom, st_kg_edges |
| D12 | Integration test: full syscall | `tests/k0/modules/consolidation/query/test_syscall_integration.py` | NEW | End-to-end: syscall -> SQL -> asyncpg -> TruthRecord[] |

---

#### M9.3.5 File Location Map (Complete)

```
NEW FILES:

  k0/modules/consolidation/
      query/
          __init__.py                  # D4+D5+D6: QueryMode, TruthCandidateRequest,
                                       #   TruthCandidateResponse, re-exports
          builder.py                   # D2: TruthCandidateQueryBuilder (SQL generation)
          mapper.py                    # D3: TruthCandidateMapper (Row -> TruthRecord)

  k0/contracts/modules/
      consolidation.truth_query.v1.yaml  # D7: Syscall contract

  tests/k0/modules/consolidation/query/
      __init__.py
      test_builder.py                # D8: SQL generation tests
      test_mapper.py                 # D9: Mapping tests
      test_pgvector_ann.py           # D10: ANN search integration
      test_key_query.py              # D11: Key query integration
      test_syscall_integration.py    # D12: Full syscall integration


EDITED FILES:

  k0/kernel/syscalls.py              # D1: Add truth_candidates_query method (~150 lines)
                                     # after kg_candidates_fuzzy_query (line ~4067)


SOURCE FILES (READ-ONLY -- pattern from):

  k0/modules/consolidation/staging/
      truth_query_service.py         # REPLACED find_candidates() and _query_layer()
                                     # Current: find_candidates (line 238), _query_layer (line 320),
                                     #   _cosine_similarity (line 487), _decode_bytea_vector (line 435)

  k0/kernel/syscalls.py              # PATTERN FROM existing syscalls:
                                     #   episodes_query (3318), kg_candidates_fuzzy_query (3952),
                                     #   vec_query (1477) -- connection, capability, logging patterns

  k0/modules/consolidation/
      truth_layer_registry.py        # M9.1: TruthLayerSpec (pk_column, embedding_fk,
                                     #   confidence_column, has_archival_status, query_mode)

  k0/db/connection.py                # read_only_scope() for query-only transactions
  k0/db/pool.py                      # AsyncPgPool for direct pool access


EXISTING FILES (CONSUMED -- schema sources):

  k0/db/alembic/versions/
      0027_st_epi.py                 # st_epi schema (PK: episode_id)
      0028_st_sem.py                 # st_sem schema (PK: pattern_id)
      0029_st_procedural.py          # st_procedural schema (PK: routine_id)
      0030_st_social.py              # st_social schema (PK: relationship_id)
      0031_st_prospective.py         # st_prospective schema (PK: intention_id)
      0032_st_kg_dom.py              # st_kg_dom schema (PK: entity_id)
      0033_st_kg_edges.py            # st_kg_edges schema (PK: edge_id)
      0071_st_vec_pgvector_native.py # st_vec VECTOR(768), HNSW index (m=16, ef=64)

  k0/drivers/pgvector.py             # PgvectorSearchClient: <=> operator pattern for st_embeddings
  k0/drivers/pgvector_outbox.py      # PgvectorDriver: <=> operator pattern for st_embeddings
```

---

#### M9.3.6 Three Query Modes

The syscall supports three modes. The mode for each layer is declared in its `TruthLayerSpec.query_mode` (from M9.1):

| Mode | SQL Pattern | When Used | Layers |
|------|-----------|-----------|--------|
| `EMBEDDING` | `ORDER BY v.vector <=> $query::vector LIMIT K` | Layer has embedding FK, candidate has embedding | st_epi, st_sem, st_procedural, st_social, st_prospective |
| `KEY` | `WHERE {key_col} = $value [AND ...]` | Layer identity is key-based, no embedding | st_kg_edges |
| `HYBRID` | `WHERE {key_cols} AND ORDER BY v.vector <=> $query::vector` | Key pre-filter + embedding re-rank | st_kg_dom |

**Mapping from TruthLayerSpec** (M9.1):

| Layer | TruthLayerSpec.query_mode | PK Column | Embedding FK | Key Columns | Has archival_status |
|-------|--------------------------|-----------|-------------|-------------|-------------------|
| st_epi | `EMBEDDING` | episode_id | embedding_id | -- | YES |
| st_sem | `EMBEDDING` | pattern_id | embedding_id | -- | YES |
| st_procedural | `EMBEDDING` | routine_id | embedding_id | -- | YES |
| st_social | `EMBEDDING` | relationship_id | embedding_id | -- | NO |
| st_prospective | `EMBEDDING` | intention_id | embedding_id | -- | NO |
| st_kg_dom | `HYBRID` | entity_id | embedding_id | entity_type, canonical_name | YES |
| st_kg_edges | `KEY` | edge_id | -- | source_entity_id, target_entity_id, relation_type | YES |

---

#### M9.3.7 Core Types (TruthCandidateRequest, TruthCandidateResponse, QueryMode)

```python
# k0/modules/consolidation/query/__init__.py

from enum import Enum
from dataclasses import dataclass, field
from typing import Any


class QueryMode(Enum):
    """How the syscall searches for candidates."""
    EMBEDDING = "embedding"   # pgvector ANN cosine search (ORDER BY <=>)
    KEY = "key"               # Exact/fuzzy WHERE clause match
    HYBRID = "hybrid"         # Key pre-filter + embedding re-rank


@dataclass(frozen=True)
class TruthCandidateRequest:
    """Input to truth_candidates_query syscall.

    Caller specifies which layer(s) to query, with what embedding
    and/or key filters. The syscall uses TruthLayerSpec to build SQL.
    """
    # Scope (always required)
    tenant_id: str
    space_id: str

    # Target layer(s)
    layers: tuple[str, ...]          # ("st_epi",) or ("st_epi", "st_sem", ...)

    # Embedding search (required for EMBEDDING/HYBRID modes)
    query_embedding: list[float] | None = None  # 768-dim, L2-normalized

    # Key filters (required for KEY/HYBRID modes, per-layer)
    # Keys are layer-specific column names, values are filter values
    # Example: {"entity_type": "PERSON", "canonical_name": "Maya"}
    key_filters: dict[str, Any] = field(default_factory=dict)

    # Pagination
    top_k: int = 10                  # Max candidates per layer
    min_similarity: float = 0.0      # Floor for cosine similarity (EMBEDDING/HYBRID only)

    # Query mode override (None = auto-detect from TruthLayerSpec)
    mode: QueryMode | None = None

    # Performance
    timeout_ms: int = 5000           # Query timeout


@dataclass(frozen=True)
class TruthCandidateResponse:
    """Output from truth_candidates_query syscall.

    Contains TruthRecord instances grouped by layer, plus query metadata.
    """
    # Results per layer
    candidates: dict[str, list["TruthRecord"]]  # layer -> [TruthRecord, ...]
    total_count: int                              # Sum across all layers

    # Query metadata (observability)
    layers_queried: tuple[str, ...]
    modes_used: dict[str, str]                    # layer -> "embedding"|"key"|"hybrid"
    elapsed_ms: float
    query_id: str                                 # For trace correlation

    # Error tracking (partial success)
    errors: dict[str, str] = field(default_factory=dict)  # layer -> error message
```

---

#### M9.3.8 TruthCandidateQueryBuilder (SQL Generation)

```python
# k0/modules/consolidation/query/builder.py

class TruthCandidateQueryBuilder:
    """Builds parameterized SQL for truth candidate queries.

    Uses TruthLayerSpec (M9.1) to determine per-layer column names,
    JOIN patterns, and filter clauses. Never interpolates values into SQL.
    """

    def __init__(self, registry: "TruthLayerRegistry") -> None:
        """Registry provides TruthLayerSpec for each layer."""

    def build(
        self,
        layer: str,
        mode: QueryMode,
        request: TruthCandidateRequest,
    ) -> tuple[str, list[Any]]:
        """Generate (sql, params) for one layer.

        Returns:
            Tuple of (parameterized SQL string, ordered parameter list)
        """
```

**Generated SQL per mode**:

**Mode: EMBEDDING** (st_epi, st_sem, st_procedural, st_social, st_prospective):

```sql
SELECT
    t.{pk_col}               AS record_id,
    '{layer}'                 AS layer,
    1 - (v.vector <=> $1::vector) AS similarity,
    t.{confidence_col}        AS confidence,
    t.version,
    t.observation_count,
    t.last_observed_at        AS last_observed_ms,
    t.participants_json,
    t.{extra_cols}
FROM {layer} t
JOIN st_vec v ON t.{embedding_fk} = v.embedding_id
WHERE t.tenant_id = $2
  AND t.space_id = $3
  {AND t.archival_status = 'ACTIVE'  -- if layer has archival_status}
  AND v.vector IS NOT NULL
  AND 1 - (v.vector <=> $1::vector) >= $4
ORDER BY v.vector <=> $1::vector ASC
LIMIT $5
```

**Params**: `[$1=query_embedding_str, $2=tenant_id, $3=space_id, $4=min_similarity, $5=top_k]`

**pgvector note**: `<=>` is cosine distance (0 = identical, 2 = opposite). Similarity = `1 - distance`. The HNSW index (`ix_st_vec_hnsw`) is triggered by `ORDER BY v.vector <=> $1::vector`.

**Mode: KEY** (st_kg_edges):

```sql
SELECT
    t.{pk_col}               AS record_id,
    '{layer}'                 AS layer,
    0.0                       AS similarity,
    t.{confidence_col}        AS confidence,
    t.version,
    t.observation_count,
    t.last_observed_at        AS last_observed_ms,
    t.source_entity_id,
    t.target_entity_id,
    t.relation_type,
    t.{extra_cols}
FROM {layer} t
WHERE t.tenant_id = $1
  AND t.space_id = $2
  AND t.archival_status = 'ACTIVE'
  {AND t.source_entity_id = $3  -- from key_filters}
  {AND t.target_entity_id = $4  -- from key_filters}
  {AND t.relation_type = $5     -- from key_filters}
ORDER BY t.observation_count DESC
LIMIT $6
```

**Mode: HYBRID** (st_kg_dom):

```sql
SELECT
    t.{pk_col}               AS record_id,
    '{layer}'                 AS layer,
    CASE WHEN v.vector IS NOT NULL
         THEN 1 - (v.vector <=> $1::vector)
         ELSE 0.0
    END                       AS similarity,
    t.{confidence_col}        AS confidence,
    t.version,
    t.observation_count,
    t.last_observed_at        AS last_observed_ms,
    t.canonical_name,
    t.entity_type,
    t.aliases_json,
    t.{extra_cols}
FROM {layer} t
LEFT JOIN st_vec v ON t.{embedding_fk} = v.embedding_id
WHERE t.tenant_id = $2
  AND t.space_id = $3
  AND t.archival_status = 'ACTIVE'
  {AND t.entity_type = $4       -- from key_filters}
  {AND (LOWER(t.canonical_name) LIKE $5 OR LOWER(t.aliases_json::text) LIKE $5)  -- fuzzy}
ORDER BY
    CASE WHEN v.vector IS NOT NULL
         THEN v.vector <=> $1::vector
         ELSE 999.0
    END ASC,
    t.observation_count DESC
LIMIT $6
```

**Extra columns per layer** (selected into TruthRecord.metadata):

| Layer | Extra Columns |
|-------|--------------|
| st_epi | participants_json, primary_location, episode_type, start_time_utc, end_time_utc, narrative_thread_id, dominant_social_context, activity_type_ultrabert, source_events_json |
| st_sem | pattern_type, pattern_name, pattern_attributes_json, temporal_regularity |
| st_procedural | routine_name, routine_category, temporal_anchor, day_pattern, action_sequence_json |
| st_social | actor_a_id, actor_b_id, relationship_type, avg_sentiment, relationship_strength |
| st_prospective | intention_type, intention_description, status, target_date |
| st_kg_dom | canonical_name, entity_type, entity_subtype, aliases_json, attributes_json |
| st_kg_edges | source_entity_id, target_entity_id, relation_type, relation_subtype, edge_weight, properties_json |

---

#### M9.3.9 TruthCandidateMapper (Row -> TruthRecord)

```python
# k0/modules/consolidation/query/mapper.py

class TruthCandidateMapper:
    """Maps asyncpg Row to TruthRecord (M9.2 type).

    Handles:
    - Vector decoding: pgvector VECTOR(768) string -> list[float]
    - Confidence normalization: various column names -> float
    - Metadata extraction: layer-specific columns -> dict
    - Null handling: missing columns default to type zero-value
    """

    def __init__(self, registry: "TruthLayerRegistry") -> None:
        """Registry provides column name mapping per layer."""

    def map_row(self, row: asyncpg.Record, layer: str) -> "TruthRecord":
        """Map one DB row to a TruthRecord.

        The similarity field comes from the SQL SELECT (computed by pgvector
        for EMBEDDING/HYBRID, 0.0 for KEY mode).
        """

    def _decode_vector(self, raw: Any) -> list[float] | None:
        """Decode pgvector VECTOR(768) from asyncpg.

        asyncpg returns VECTOR columns as strings: "[0.1,0.2,...,0.768]"
        Per known codebase convention (R0 batch selector uses json.loads).

        Three-path handling (matching R0 pattern):
        1. str -> json.loads
        2. list/tuple -> direct
        3. bytes -> struct.unpack (legacy, pre-M4)
        """

    def _extract_metadata(self, row: asyncpg.Record, layer: str) -> dict[str, Any]:
        """Extract layer-specific columns into metadata dict.

        Uses TruthLayerSpec.extra_query_columns to know which columns
        to pull from the row. Parses JSON columns (participants_json, etc.)
        """
```

**Vector decoding** follows the R0 three-path pattern (`k0/pipelines/p03/phases/r0_batch_selector.py:1418`):

```python
def _decode_vector(self, raw: Any) -> list[float] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return json.loads(raw)               # pgvector native (current)
    elif isinstance(raw, (list, tuple)):
        return list(raw)                     # pgvector extension codec
    elif isinstance(raw, (bytes, bytearray)):
        dim = len(raw) // 4
        return list(struct.unpack(f"<{dim}f", raw))  # legacy BYTEA
    return None
```

---

#### M9.3.10 Syscall Method Definition (truth_candidates_query)

```python
# Appended to k0/kernel/syscalls.py (after kg_candidates_fuzzy_query, ~line 4067)

async def truth_candidates_query(
    self,
    request: "TruthCandidateRequest",
) -> "TruthCandidateResponse":
    """
    Unified truth layer candidate query for reconciliation engine.

    Replaces TruthQueryService.find_candidates() and 8+ bespoke query paths
    with a single capability-gated, pgvector-accelerated syscall.

    Supports three query modes:
    - EMBEDDING: pgvector cosine ANN (ORDER BY <=> with HNSW index)
    - KEY: Exact/fuzzy WHERE clause match (for st_kg_edges, etc.)
    - HYBRID: Key pre-filter + embedding re-rank (for st_kg_dom)

    Query mode is auto-detected from TruthLayerSpec.query_mode unless
    explicitly overridden in the request.

    Capability Required: "truth.reconcile.read"

    Storage Tables: Any truth layer registered in TruthLayerRegistry
    - st_epi, st_sem, st_procedural, st_social, st_prospective (EMBEDDING)
    - st_kg_dom (HYBRID: entity_type + fuzzy name + cosine re-rank)
    - st_kg_edges (KEY: source + target + relation_type)

    Args:
        request: TruthCandidateRequest with layers, embedding, key_filters

    Returns:
        TruthCandidateResponse with candidates per layer + query metadata

    Raises:
        PermissionError: If pipeline lacks "truth.reconcile.read" capability
        ValueError: If request.layers contains unregistered layer
        asyncio.TimeoutError: If query exceeds request.timeout_ms

    Performance:
        - Target: <100ms P95 for single-layer EMBEDDING query (top_k=10)
        - Target: <200ms P95 for all-layer query (7 layers, top_k=5 each)
        - pgvector HNSW provides O(log N) ANN vs O(N) brute-force
        - Compared to current: eliminates Python-side cosine on 100 rows

    Related:
        - M9.1: TruthLayerRegistry provides per-layer column mapping
        - M9.2: TruthRecord type definition (output element)
        - M9.4: ReconciliationFramework calls this syscall
    """
    self._require_cap("truth.reconcile.read")

    # Implementation delegates to TruthCandidateQueryBuilder + TruthCandidateMapper
    # See M9.3.11 for execution flow
```

**Capability**: `"truth.reconcile.read"` -- a new composite capability that must be added to `k0/contracts/pipelines/p03_consolidation.v1.yaml` under `required_capabilities`. This replaces the need for individual per-table read caps for reconciliation (the existing per-table caps remain for non-reconciliation reads by R5, R4, etc.).

---

#### M9.3.11 Execution Flow (End-to-End)

```
ReconciliationFramework.reconcile(candidate: ReconciliationCandidate)
    |
    v
[1. Build TruthCandidateRequest]
    request = TruthCandidateRequest(
        tenant_id = candidate.tenant_id,
        space_id = candidate.space_id,
        layers = (candidate.layer,),         # Single layer per candidate
        query_embedding = candidate.embedding,
        key_filters = candidate.key_filters, # From IdentityStrategy.extract_keys() if KEY/HYBRID
        top_k = 10,                          # Configurable per layer via TruthLayerSpec
        min_similarity = 0.35,               # Configurable per layer
    )
    |
    v
[2. Syscall: truth_candidates_query(request)]
    self._require_cap("truth.reconcile.read")
    |
    v
[3. Resolve QueryMode per layer]
    for layer in request.layers:
        spec = registry.get(layer)           # TruthLayerSpec from M9.1
        mode = request.mode or spec.query_mode  # Auto-detect from spec
    |
    v
[4. Build SQL]
    builder = TruthCandidateQueryBuilder(registry)
    sql, params = builder.build(layer, mode, request)
    # SQL uses parameterized $N placeholders (never string interpolation)
    # Embedding formatted as "[0.1, 0.2, ...]" string, cast via $1::vector
    |
    v
[5. Execute via UoW connection]
    async with self._uow_factory() as uow:
        conn = uow._connection
        rows = await asyncio.wait_for(
            conn.fetch(sql, *params),
            timeout=request.timeout_ms / 1000.0,
        )
    |
    v
[6. Map rows to TruthRecord]
    mapper = TruthCandidateMapper(registry)
    records = [mapper.map_row(row, layer) for row in rows]
    # Vector decoding: json.loads for pgvector string format
    # Metadata extraction: layer-specific columns -> dict
    # Similarity: comes from SQL (1 - cosine_distance), NOT Python
    |
    v
[7. Return TruthCandidateResponse]
    response = TruthCandidateResponse(
        candidates={layer: records},
        total_count=len(records),
        layers_queried=(layer,),
        modes_used={layer: mode.value},
        elapsed_ms=elapsed,
        query_id=trace_id,
    )
    |
    v
[8. Framework feeds candidates to IdentityStrategy.score_identity()]
    for record in response.candidates[layer]:
        result = identity_strategy.score_identity(
            candidate=reconciliation_candidate,
            existing=record,
            cosine_sim=record.metadata.get("similarity", 0.0),
        )
```

---

#### M9.3.12 pgvector Integration Details

**Current state**: HNSW index exists on st_vec but is UNUSED. All cosine similarity is computed in Python.

**st_vec HNSW index** (from migration 0071):

```sql
CREATE INDEX ix_st_vec_hnsw
ON st_vec
USING hnsw (vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

**M9.3 activates this index** via the `<=>` operator in EMBEDDING mode queries:

```sql
-- This triggers HNSW probe (approximate nearest neighbor)
ORDER BY v.vector <=> $1::vector ASC
LIMIT $5
```

**Embedding parameter formatting** for asyncpg:

```python
# Convert list[float] to pgvector string format
embedding_str = "[" + ",".join(str(f) for f in request.query_embedding) + "]"
# Pass as $1 and cast in SQL: $1::vector
```

**Two pgvector tables exist** (only st_vec is used by M9.3):

| Table | Dim | Index | Used By | M9.3 |
|-------|-----|-------|---------|------|
| st_vec | 768 | HNSW (m=16, ef=64) | Truth layer JOINs | YES |
| st_embeddings | 384 | IVFFlat (lists=100) | Legacy outbox driver | NO (separate system) |

**Performance expectations**:

- HNSW probe: ~1-5ms for top-10 on tables with <100K rows (typical family scale)
- Current Python cosine: ~50-200ms (fetch 100 rows, decode, sort)
- Improvement: **10-50x faster** for EMBEDDING mode queries

---

#### M9.3.13 Connection Strategy

**Current syscalls**: All use `async with self._uow_factory() as uow:` which opens a read-write transaction.

**M9.3 query is read-only**: Could use `read_only_scope()` from `k0/db/connection.py` for safety. However, for consistency with existing syscall patterns and to reuse the UoW's connection pool, M9.3 follows the existing pattern:

```python
async with self._uow_factory() as uow:
    conn = uow._connection
    if conn is None:
        raise RuntimeError("UnitOfWork connection not initialized")
    rows = await asyncio.wait_for(
        conn.fetch(sql, *params),
        timeout=request.timeout_ms / 1000.0,
    )
```

**Rationale**: Switching to `read_only_scope()` would require changing how the syscall obtains its connection (bypassing UoW factory), which is an architectural change beyond M9.3 scope. The UoW pattern is safe for reads -- it just acquires a pooled connection.

---

#### M9.3.14 Multi-Layer Query Strategy

When `request.layers` contains multiple layers, the syscall queries each layer **sequentially** (not parallel):

```python
all_candidates: dict[str, list[TruthRecord]] = {}
total = 0

for layer in request.layers:
    spec = registry.get(layer)
    mode = request.mode or spec.query_mode
    sql, params = builder.build(layer, mode, request)
    rows = await conn.fetch(sql, *params)
    records = [mapper.map_row(row, layer) for row in rows]
    all_candidates[layer] = records
    total += len(records)
```

**Why sequential, not parallel**:

1. All queries share one UoW connection (asyncpg connection is not safe for concurrent use)
2. Typical usage: ReconciliationFramework queries ONE layer per candidate (candidate.layer)
3. Multi-layer queries are rare (only for initial exploration / R5 recall)
4. Sequential on a single connection avoids transaction isolation complexity

**If parallelism is needed later**: Each layer query could use a separate connection from the pool. This is a future optimization, not M9.3 scope.

---

#### M9.3.15 Embedding Format: Similarity vs Distance

pgvector `<=>` returns **cosine distance** (0 = identical, 2 = opposite). The codebase convention is **cosine similarity** (1 = identical, 0 = orthogonal). The SQL converts:

```sql
1 - (v.vector <=> $1::vector) AS similarity
```

This matches the existing Python `_cosine_similarity()` output range `[0, 1]` (clamped). Note: negative similarities (distance > 1) are possible for non-normalized vectors -- the `min_similarity` filter handles this:

```sql
AND 1 - (v.vector <=> $1::vector) >= $4  -- min_similarity filter
```

UltraBERT v4.0.7 embeddings are L2-normalized, so cosine distance is always in `[0, 2]` and similarity in `[-1, 1]`. The `min_similarity >= 0.0` default excludes anti-correlated vectors.

---

#### M9.3.16 What M9.3 Replaces

| Current Code | File:Line | What It Does | M9.3 Replacement |
|-------------|----------|-------------|-----------------|
| `TruthQueryService.find_candidates()` | truth_query_service.py:238 | Python cosine on 5 layers, no ORDER BY, struct.unpack bug | `truth_candidates_query` EMBEDDING mode (pgvector ANN) |
| `TruthQueryService._query_layer()` | truth_query_service.py:320 | Per-layer SQL with no similarity ordering | `TruthCandidateQueryBuilder.build()` with ORDER BY <=> |
| `TruthQueryService._decode_bytea_vector()` | truth_query_service.py:435 | struct.unpack (broken after 0071) | `TruthCandidateMapper._decode_vector()` (json.loads) |
| `TruthQueryService._cosine_similarity()` | truth_query_service.py:487 | Python numpy cosine | Pushed to pgvector `<=>` in SQL |
| `kg_entities_lookup` syscall | syscalls.py:3852 | Full table scan -> dict | `truth_candidates_query` HYBRID mode |
| `kg_edges_lookup` syscall | syscalls.py:3749 | Full table scan -> dict | `truth_candidates_query` KEY mode |
| `kg_candidates_fuzzy_query` syscall | syscalls.py:3952 | ILIKE fuzzy match | `truth_candidates_query` HYBRID mode with key_filters |
| CrossBatchExtend caller pre-query | (implicit, R2 phase) | Must pre-fetch st_epi episodes | `truth_candidates_query` EMBEDDING mode for st_epi |

**Not replaced** (different purpose, remain as-is):

| Syscall | Reason |
|---------|--------|
| `episodes_query` | R5 recall: loads historical episodes for pattern detection, not reconciliation |
| `procedural_memory_query` | R5 recall: loads routines for TDL-HCO, not reconciliation |
| `semantic_schema_query` | R5 recall: loads patterns for SPC-UQ, not reconciliation |
| `transaction._refresh_versions()` | OCC conflict resolution during write, not candidate search |
| `TruthQueryService.query_entities_for_decay()` | Decay evaluation (M9.9), separate from candidate search |

---

#### M9.3.17 Execution Steps (Ordered)

| Step | Action | Input | Output |
|------|--------|-------|--------|
| 1 | Create `k0/modules/consolidation/query/__init__.py` | M9.3.7 types | QueryMode, TruthCandidateRequest, TruthCandidateResponse |
| 2 | Create `k0/modules/consolidation/query/builder.py` | M9.3.8 SQL templates, M9.1 TruthLayerSpec | TruthCandidateQueryBuilder |
| 3 | Create `k0/modules/consolidation/query/mapper.py` | M9.3.9 mapper spec, R0 vector decode pattern | TruthCandidateMapper |
| 4 | Add `truth_candidates_query` method to syscalls.py | M9.3.10 + M9.3.11 flow | Syscall method (~150 lines) |
| 5 | Add `"truth.reconcile.read"` to P03 capabilities | p03_consolidation.v1.yaml | New capability grant |
| 6 | Write SQL generation tests | M9.3.8 SQL templates, all 3 modes x 7 layers | test_builder.py |
| 7 | Write mapper tests | M9.3.9 vector decode, metadata extract | test_mapper.py |
| 8 | Write pgvector ANN integration test | Real HNSW search on test vectors | test_pgvector_ann.py |
| 9 | Write key query integration test | st_kg_dom fuzzy + st_kg_edges exact | test_key_query.py |
| 10 | Write full syscall integration test | End-to-end with capability check | test_syscall_integration.py |
| 11 | Create syscall contract YAML | M9.3.7 types + M9.3.6 modes | consolidation.truth_query.v1.yaml |

---

#### M9.3.18 Validation Criteria (Exit Gates)

| # | Criterion | How to Verify |
|---|----------|---------------|
| V1 | EMBEDDING query uses pgvector `<=>` operator | SQL output contains `ORDER BY v.vector <=> $1::vector` |
| V2 | HNSW index probe confirmed | EXPLAIN ANALYZE shows "Index Scan using ix_st_vec_hnsw" |
| V3 | KEY query produces valid WHERE clause | SQL output for st_kg_edges has `source_entity_id = $N` |
| V4 | HYBRID query has both key filter and cosine ORDER BY | SQL output for st_kg_dom has WHERE + ORDER BY <=> |
| V5 | Vector decoding handles all 3 formats | Test: string (pgvector), list (codec), bytes (legacy) |
| V6 | Capability "truth.reconcile.read" enforced | PermissionError raised without cap |
| V7 | All 7 layers queryable | Integration test queries each layer successfully |
| V8 | min_similarity filter works | Test: returns 0 candidates when floor > max similarity |
| V9 | top_k limit respected per layer | Test: never returns more than top_k per layer |
| V10 | timeout_ms kills long queries | Test: asyncio.TimeoutError raised on synthetic slow query |
| V11 | TruthRecord.metadata populated per layer | Each layer's extra columns appear in metadata dict |
| V12 | No Python-side cosine computation | grep for `np.dot.*norm` in query/ returns 0 matches |
| V13 | Similarity in response matches pgvector output | Known test vectors produce expected similarity values |

---

#### M9.3.19 What M9.3 Does NOT Do

| Out of Scope | Why | When |
|-------------|-----|------|
| Replace R5 recall syscalls (episodes_query, etc.) | Different purpose: historical recall, not reconciliation | Never (separate concern) |
| Parallel multi-layer queries | Single connection per UoW, not needed for typical 1-layer use | Future optimization |
| Build the ReconciliationFramework | Separate service (consumer of this syscall) | M9.4 |
| Deprecate existing bespoke syscalls | Must keep for backward compat during migration | M9.8 |
| Fix TruthQueryService bugs in-place | New code replaces it; old code stays until M9.8 migration | M9.8 |
| Add inline vector column queries (0061-0066) | Inline BYTEA vectors are not pgvector-typed, no HNSW index | Future (if st_vec FK eliminated) |
| Create st_vec indexes for per-layer partition | All layers share one st_vec with one HNSW index | Future (if scale requires) |
| Implement decay query path | Separate from candidate search | M9.9 |

---

### M9.4 -- Reconciliation Framework (Core Decision Machine)

Build the central orchestrator that ties Services 1-3 together and produces decisions.

- ReconciliationFramework.reconcile() method
- Tier 1: K1 signal check (EVOLVE / CONTRADICT)
- Tier 2: identity score cascade (REINFORCE / EXTEND / CREATE)
- Per-layer threshold configuration
- Observability: per-batch, per-layer action counters + structured logs (absorbed M7 7.5)
- Integration tests: full decision flow for each action type

**Depends on**: M9.1, M9.2, M9.3

---

### M9.5 -- Write Decision Router

Build the action-to-SQL mapping layer.

- WriteDecisionRouter.build_staged_write() method
- Per-action write logic: CREATE, REINFORCE, EXTEND, EVOLVE, CONTRADICT, PRUNE
- Merge rules from TruthLayerSpec (appendable JSON union, temporal LEAST/GREATEST, counters)
- Idempotency key generation per StagedWrite
- Integration tests: verify StagedWrite correctness for each action

**Depends on**: M9.1 (merge rules), M9.4 (produces actions)

---

### M9.6 -- Structured Summaries & Embedding Regeneration (Absorbed M7)

Build the post-reconciliation hooks for content generation.

- Structured summary generator for CREATE/EXTEND/EVOLVE (absorbed M7 7.3)
- Centroid recomputation on EXTEND/EVOLVE (absorbed M7 7.4)
- REINFORCE does NOT recompute centroid (lightweight bump only)
- EVOLVE computes fresh centroid for successor (no inheritance)

**Depends on**: M9.4, M9.5

---

### M9.7 -- Remaining Identity Strategies (x6)

Implement the identity strategies for non-episodic layers.

- SemanticIdentity (st_sem)
- EntityIdentity (st_kg_dom) -- exact key + fuzzy + embedding fallback
- EdgeIdentity (st_kg_edges) -- compound key only
- SocialIdentity (st_social) -- participant pair + embedding tiebreaker
- ProceduralIdentity (st_procedural) -- routine name + time pattern
- ProspectiveIdentity (st_prospective) -- cosine only
- Integration tests per strategy

**Depends on**: M9.2 (protocol defined), M9.3 (query paths available)

---

### M9.8 -- Phase Migration (R2 -> R3 -> R4 -> R5)

Migrate each P03 phase from bespoke reconciliation to engine calls.

- R2: Replace cross_batch_extend.py + same_thread_merge.py with engine.reconcile(st_epi)
- R3: Replace bespoke pattern matching with engine.reconcile(st_sem, st_procedural, st_social, st_prospective)
- R4: Replace entity/edge matching with engine.reconcile(st_kg_dom, st_kg_edges)
- R5: Add reconciliation for dream outputs (currently none)
- R6: Simplify to StagedWrite collector (remove 12+ assemble methods)
- Integration tests: full pipeline run with engine vs without (regression)

**Depends on**: M9.1 through M9.7 (all services built)

---

### M9.9 -- PRUNE Sweep (Timer-Based Decay)

Build the temporal decay sweep that runs independently of incoming events.

- Configurable decay policies per truth layer
- PRUNE action: ARCHIVED or TOMBSTONED based on policy
- Scheduled sweep (not triggered by incoming batch)
- Observability: prune counts per layer per sweep

**Depends on**: M9.1, M9.5

---

### M9.10 -- Scene Segmentation (Mega-Episode Splitting)

Address the mega-attractor problem identified in POC (Ep15: 87 events, 33% purity).

- Detect oversized episodes that have grown beyond coherence
- Sub-episode splitting based on temporal gaps, topic shifts, participant changes
- Produces SPLIT action: one episode becomes N episodes
- Integration tests: verify mega-episodes get split correctly

**Depends on**: M9.4, M9.2 (EpisodicIdentity must be live)
**POC Evidence**: Ep15 (Maya life threads -- fears, play, birthday) overlap heavily in participants/topics/settings

---

## 9. Milestone Dependency Graph

```
M9.1  (Registry)
  |
  +---> M9.2  (EpisodicIdentity)
  |       |
  +---> M9.3  (Truth Query Syscall)
  |       |
  |       +---> M9.7  (Remaining Identity Strategies x6)
  |       |
  +-------+---> M9.4  (Reconciliation Framework)
  |               |
  +---> M9.5  (Write Decision Router)
  |       |
  |       +---> M9.6  (Summaries & Embedding Regen)
  |       |
  |       +---> M9.9  (PRUNE Sweep)
  |
  +---> M9.8  (Phase Migration R2-R5)   [depends on M9.1 through M9.7]
  |
  +---> M9.10 (Scene Segmentation)      [depends on M9.2, M9.4]
```

### Suggested Execution Order

1. **M9.1** -- Foundation, everything depends on this
2. **M9.2** + **M9.3** -- Can be built in parallel
3. **M9.4** -- Core decision machine
4. **M9.5** -- Write routing
5. **M9.6** -- Post-reconciliation hooks
6. **M9.7** -- Remaining strategies (can overlap with M9.5/M9.6)
7. **M9.8** -- Phase migration (big integration milestone)
8. **M9.9** + **M9.10** -- Independent, can be done in parallel after M9.8

---

## 10. Component Location Map

```
k0/modules/consolidation/
    truth_layer_registry.py              # Service 1: TruthLayerSpec + Registry
    identity/
        __init__.py                      # IdentityStrategy protocol
        episodic.py                      # Service 3: EpisodicIdentity (POC -> production)
        semantic.py                      # SemanticIdentity
        entity.py                        # EntityIdentity
        edge.py                          # EdgeIdentity
        social.py                        # SocialIdentity
        procedural.py                    # ProceduralIdentity
        prospective.py                   # ProspectiveIdentity
    reconciliation_framework.py          # Service 4: ReconciliationFramework
    write_decision_router.py             # Service 5: WriteDecisionRouter

k0/kernel/syscalls.py                   # Service 2: truth_candidates_query syscall

k0/contracts/modules/
    consolidation.reconciliation.v1.yaml # Engine contract
    consolidation.identity.v1.yaml       # Identity strategy contracts

k0/contracts/schemas/
    reconciliation_candidate.v1.yaml     # ReconciliationCandidate schema
    reconciliation_result.v1.yaml        # ReconciliationResult schema
```

---

## 11. What the POC Proved

| Finding | Source | Implication for Engine |
|---------|--------|----------------------|
| 11-feature logistic beats cosine-only | EXP-9, EXP-11 | EpisodicIdentity uses multi-signal scoring, not just cosine |
| topic_overlap is #1 feature (weight=2.68) | EXP-9 | Structural metadata is critical, embeddings alone are insufficient |
| K1 bypass is a hard override | EXP-4 | Tier 1 (K1 signals) must be checked before any similarity logic |
| Threshold 0.35 optimal (not 0.60) | Threshold sweep | Learned thresholds outperform fixed heuristics |
| Mean centroid converges by k=3 events | EXP-7 | Incremental centroid update is stable for online operation |
| Temporal distance is noise | EXP-5 | Do not use temporal gap as a feature (use it only as a filter/gate) |
| 686/1410 events are unthreaded | Corpus analysis | Engine must work without thread_id (R2's require_same_thread misses these) |
| Mega-episodes form from overlapping participants | Ep15 analysis | Scene segmentation (M9.10) is required for coherent episodes |

---

## 12. Open Questions

- [ ] PRUNE decay policy: per-layer or global? What time windows?
- [ ] Scene segmentation trigger: size-based, purity-based, or both?
- [ ] P06 active learning integration: how does CONTRADICT flow back?
- [ ] Multi-centroid episodes: single embedding_id today, do we need multiple?
- [ ] Performance budget: what is the per-candidate latency target for the engine?
- [ ] Existing bespoke syscalls: deprecate immediately or keep as parallel paths during migration?

---

*This document is the source of truth for the Universal Reconciliation Engine design. Whiteboard details remain in `docs/whiteboard/whiteboard_reconciliation_engine.md`. POC research in `poc/reconciliation_embedding_poc/`.*
