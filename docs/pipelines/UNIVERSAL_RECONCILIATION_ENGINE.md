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

**Status**: READY TO IMPLEMENT
**Estimated Scope**: 1 engine module + 1 batch coordinator + 1 confidence model + 1 result type + 1 contract YAML + tests + observability
**Depends on**: M9.1 (TruthLayerRegistry for per-layer thresholds), M9.2 (IdentityStrategy for scoring), M9.3 (truth_candidates_query for candidate retrieval)
**Replaces**: `k0/modules/consolidation/algorithms/reconciliation_engine.py` (878 lines, ReconciliationEngine + ReconciliationConfig + ReconciliationDecision)
**POC Lineage**: `poc/reconciliation_embedding_poc/experiments/reconciliation_engine.py` (K1 bypass -> cosine retrieval -> structural scoring -> threshold decision)

---

#### M9.4.1 Objective

Create the `ReconciliationFramework` -- a stateless, pure-function decision machine that receives a `ReconciliationCandidate` (M9.2) plus pre-fetched truth records from `truth_candidates_query` (M9.3), applies a 6-stage decision pipeline, and returns a `ReconciliationResult` containing the action enum, match metadata, confidence score, reason trace, and a list of post-decision hooks. This is Service 4 of the 5-service Universal Reconciliation Engine architecture: the central orchestrator that coordinates the registry (M9.1), identity scoring (M9.2), and candidate retrieval (M9.3) into a single deterministic decision per candidate.

The framework must:

1. Apply Tier 1 (K1 signal override) BEFORE any similarity computation
2. Apply identity filtering BEFORE similarity ranking (only score identity-compatible records)
3. Use per-layer thresholds from TruthLayerSpec (not hardcoded constants)
4. Produce a `ReconciliationResult` consumed by WriteDecisionRouter (M9.5) and R6 staging
5. Support batch processing with query deduplication (multiple candidates, one truth fetch)
6. Emit per-batch, per-layer, per-action Prometheus counters and structured logs (absorbed M7 7.5)
7. Be a **pure function** -- no database reads, no database writes, no instance state mutation

---

#### M9.4.2 What M9.4 Replaces (Existing Code -> New Code)

| Existing Component | File | Lines | Problem | M9.4 Replacement |
|---|---|---|---|---|
| `ReconciliationEngine` class | `k0/modules/consolidation/algorithms/reconciliation_engine.py` | L198-878 | Owns DB queries (TruthQueryService) + decision logic in one class; no K1 awareness; hardcoded thresholds 0.85/0.60/0.40; Python-side cosine on all candidates | `ReconciliationFramework.decide()` -- pure function, no DB, per-layer thresholds from TruthLayerSpec |
| `ReconciliationConfig` dataclass | same file | L85-145 | Global thresholds, no per-layer override | Replaced by `TruthLayerSpec.thresholds` (M9.1) -- each layer has its own reinforce/extend/evolve thresholds |
| `ReconciliationDecision` dataclass | same file | L150-193 | Missing: tier indicator, identity_match flag, hooks_required, staged_write | `ReconciliationResult` (M9.4) -- 14 fields vs 8 |
| `ReconciliationEngine.decide()` | same file | L283-378 | Calls `_find_candidates` (DB query) inside decision logic | `ReconciliationFramework.decide()` receives pre-fetched records as argument |
| `ReconciliationEngine.decide_batch()` | same file | L382-414 | Sequential per-event, each event triggers separate DB query | `ReconciliationFramework.decide_batch()` -- one truth fetch per (layer, space_id, tenant_id), then N decisions |
| `ReconciliationEngine._determine_action()` | same file | L633-686 | No identity filtering before threshold; EVOLVE only if 0.40 <= sim < 0.60 (gap between EXTEND and EVOLVE is invisible) | 6-stage pipeline: K1 -> override -> identity filter -> similarity rank -> threshold -> assembly |
| `ReconciliationEngine._compute_confidence()` | same file | L688-757 | Ad-hoc Bayesian-style with magic numbers | `ConfidenceModel.compute()` -- explicit formula, per-action, testable in isolation |
| `CrossBatchExtendMatcher.match()` | `k0/modules/consolidation/algorithms/cross_batch_extend.py` | L172-240 | Bespoke extend logic for episodes only; 3 conditions (sim + thread + temporal) hardcoded | Absorbed into EpisodicIdentity (M9.2) -- thread + temporal are identity features, sim is Tier 2 |
| R3 `reconcile_batch()` loop | `k0/pipelines/p03/phases/r3_dedup_decay.py` | L1200-1290 | Per-event `decide()` calls with per-event DB queries | R3 calls `framework.decide_batch()` -- one query, N decisions |

---

#### M9.4.3 Deliverables

| # | Deliverable | File Path | New/Edit | Description |
|---|-----------|-----------|----------|-------------|
| D1 | ReconciliationResult type | `k0/modules/consolidation/reconciliation/result.py` | NEW | Frozen dataclass with 14 fields: action, match_id, match_layer, similarity, confidence, reason, identity_match, tier, hooks_required, contradiction_details, decision_time_ms, candidate_id, layer, cycle_id |
| D2 | ConfidenceModel | `k0/modules/consolidation/reconciliation/confidence.py` | NEW | Pure-function confidence computation: per-action formula, candidate-count boost, identity-match boost |
| D3 | ReconciliationFramework.decide() | `k0/modules/consolidation/reconciliation/engine.py` | NEW | Static method: 6-stage pipeline, ~150 lines |
| D4 | ReconciliationFramework.decide_batch() | `k0/modules/consolidation/reconciliation/engine.py` | NEW (same file) | Batch coordinator: groups candidates by layer, calls truth_candidates_query once per (layer, space, tenant), iterates decide() per candidate |
| D5 | DecisionMetrics | `k0/modules/consolidation/reconciliation/metrics.py` | NEW | Prometheus counters: decisions_total(layer, action), decision_confidence(layer, action), decision_latency_ms(layer), batch_size(layer), identity_filter_ratio(layer), k1_bypass_total(signal_type) |
| D6 | Structured decision log schema | `k0/modules/consolidation/reconciliation/decision_log.py` | NEW | Structured log helper: cycle_id, candidate_id, layer, action, similarity, confidence, tier, match_id, reason, duration_ms |
| D7 | YAML contract | `k0/contracts/modules/reconciliation.framework.v1.yaml` | NEW | Input/output schemas, 6-stage pipeline spec, threshold contract referencing TruthLayerSpec |
| D8 | Unit tests | `tests/k0/modules/consolidation/reconciliation/test_engine.py` | NEW | Per-stage tests, per-action tests, K1 bypass tests, identity filter tests, threshold boundary tests |
| D9 | Batch tests | `tests/k0/modules/consolidation/reconciliation/test_batch.py` | NEW | Query deduplication, mixed-layer batch, empty candidates, partial failure |
| D10 | Confidence model tests | `tests/k0/modules/consolidation/reconciliation/test_confidence.py` | NEW | Per-action confidence formulas, boundary values, monotonicity |
| D11 | Golden data tests | `tests/k0/modules/consolidation/reconciliation/test_golden_decisions.py` | NEW | End-to-end golden vectors: known candidate + known records -> expected action + match_id + confidence range |

---

#### M9.4.4 File Location Map (Complete)

```
NEW FILES:

  k0/modules/consolidation/reconciliation/
      result.py                        # D1: ReconciliationResult frozen dataclass (14 fields)
      confidence.py                    # D2: ConfidenceModel.compute() pure function
      engine.py                        # D3+D4: ReconciliationFramework.decide() + decide_batch()
      metrics.py                       # D5: DecisionMetrics (Prometheus counters + histograms)
      decision_log.py                  # D6: log_decision() structured logger

  k0/contracts/modules/
      reconciliation.framework.v1.yaml # D7: Contract for ReconciliationFramework

  tests/k0/modules/consolidation/reconciliation/
      test_engine.py                   # D8: Per-stage unit tests
      test_batch.py                    # D9: Batch coordination tests
      test_confidence.py               # D10: Confidence model tests
      test_golden_decisions.py         # D11: Golden data end-to-end tests


EXISTING FILES (READ-ONLY during M9.4, deleted/edited in M9.8):

  k0/modules/consolidation/algorithms/reconciliation_engine.py     # Current engine (878 lines) -- NOT modified, NOT deleted
  k0/modules/consolidation/algorithms/cross_batch_extend.py        # Current extend matcher -- NOT modified
  k0/pipelines/p03/phases/r3_dedup_decay.py                        # Current R3 (calls old engine) -- NOT modified until M9.8
  k0/pipelines/p03/phases/r2_episodic_integrator.py                # Current R2 (calls CrossBatchExtendMatcher) -- NOT modified until M9.8
  k0/pipelines/p03/event_state.py                                  # ReconciliationAction enum (8 values) -- REUSED as-is
  k0/pipelines/p03/staged_writes.py                                # StagedWrite, WriteOperation -- REUSED as-is
```

---

#### M9.4.5 ReconciliationResult Type (Target)

The existing `ReconciliationDecision` (8 fields) is replaced by `ReconciliationResult` (14 fields) that carries everything downstream consumers need:

```python
# k0/modules/consolidation/reconciliation/result.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from k0.pipelines.p03.event_state import ReconciliationAction


@dataclass(frozen=True)
class ReconciliationResult:
    """Immutable decision output from ReconciliationFramework.decide()."""

    # -- Decision --
    action: ReconciliationAction              # REINFORCE|EXTEND|EVOLVE|CREATE|CONTRADICT|SKIP|PRUNE
    tier: int                                 # 1 = K1 signal override, 2 = identity+similarity cascade

    # -- Match --
    match_id: Optional[str]                   # PK of matched truth record (None for CREATE, SKIP)
    match_layer: str                          # target truth layer ("st_epi", "st_sem", etc.)
    similarity: float                         # [0.0, 1.0] best cosine similarity (0.0 if Tier 1)
    identity_match: bool                      # did identity keys match? (False if Tier 1)

    # -- Confidence --
    confidence: float                         # [0.0, 1.0] computed by ConfidenceModel

    # -- Trace --
    reason: str                               # human-readable decision explanation
    candidate_id: str                         # input candidate's ID (provenance)
    layer: str                                # target layer (same as match_layer for non-CREATE)
    cycle_id: str                             # P03 cycle ID

    # -- Hooks --
    hooks_required: List[str] = field(default_factory=list)
    # Possible values: "recompute_centroid", "regenerate_summary", "archive_superseded"

    # -- Contradiction detail (Tier 1 only) --
    contradiction_details: Optional[Dict[str, Any]] = None
    # Contains: correction_source, supersedes_concept, session_context_id (for P06 learning queue)

    # -- Timing --
    decision_time_ms: float = 0.0

    def __post_init__(self):
        # Clamp similarity and confidence to [0.0, 1.0]
        object.__setattr__(self, "similarity", max(0.0, min(1.0, self.similarity)))
        object.__setattr__(self, "confidence", max(0.0, min(1.0, self.confidence)))

    @property
    def has_match(self) -> bool:
        return self.match_id is not None

    @property
    def is_k1_override(self) -> bool:
        return self.tier == 1
```

**Invariants**:

- `match_id is None` if and only if `action in {CREATE, SKIP}`
- `tier == 1` if and only if `action in {EVOLVE, CONTRADICT}` AND triggered by K1 signal (not by similarity)
- `similarity == 0.0` when `tier == 1` (K1 override does not compute cosine)
- `identity_match == False` when `tier == 1` (identity filtering skipped for K1)
- `contradiction_details is not None` only when `action == CONTRADICT`
- `hooks_required` is never None, always at least empty list

---

#### M9.4.6 The 6-Stage Decision Pipeline (Complete Specification)

The core of M9.4. Each stage is a pure function with explicit inputs and outputs.

**Stage 1: K1 Signal Check (Tier 1)**

```
INPUT:  candidate.k1_signals (K1SignalBundle from M9.2)
OUTPUT: ReconciliationResult with tier=1, OR pass-through to Stage 2

IF candidate.k1_signals.correction_signal == True:
    RETURN ReconciliationResult(
        action=EVOLVE, tier=1, match_id=None, similarity=0.0,
        identity_match=False, confidence=0.95,
        reason="K1 correction signal from {correction_source}",
        hooks_required=["archive_superseded"],
        contradiction_details=None
    )

IF candidate.k1_signals.contradiction_signal == True:
    RETURN ReconciliationResult(
        action=CONTRADICT, tier=1, match_id=None, similarity=0.0,
        identity_match=False, confidence=0.90,
        reason="K1 contradiction signal: {supersedes_concept}",
        hooks_required=[],
        contradiction_details={
            "correction_source": candidate.k1_signals.correction_source,
            "supersedes_concept": candidate.k1_signals.supersedes_concept,
            "session_context_id": candidate.k1_signals.session_context_id,
        }
    )
```

**Why K1 fires first**: Correction/contradiction signals come from explicit user or K1 agent action. They represent ground truth that overrides any statistical similarity. A corrected fact must EVOLVE regardless of how similar it looks to existing records. A contradicted claim must go to P06 learning regardless of score.

**Stage 2: Override Check**

```
INPUT:  candidate.metadata (Dict from M9.2)
OUTPUT: ReconciliationResult with SKIP or PRUNE, OR pass-through to Stage 3

IF candidate.metadata.get("is_duplicate") == True:
    RETURN ReconciliationResult(
        action=SKIP, tier=2, match_id=None, similarity=0.0,
        identity_match=False, confidence=1.0,
        reason="Duplicate detected by R3 dedup (duplicate_of={duplicate_of_id})",
        hooks_required=[]
    )

IF candidate.metadata.get("prune_decision") == "TOMBSTONE":
    RETURN ReconciliationResult(
        action=PRUNE, tier=2, match_id=None, similarity=0.0,
        identity_match=False, confidence=1.0,
        reason="Prune override: TOMBSTONE",
        hooks_required=[]
    )
```

**Stage 3: Identity Filter**

```
INPUT:  candidate (ReconciliationCandidate),
        existing_records (List[TruthRecord] from M9.3),
        identity_strategy (IdentityStrategy from M9.2, obtained via TruthLayerSpec)
OUTPUT: compatible_records (List[TruthRecord]), OR CREATE if empty

spec = registry.get(layer)
identity = spec.identity_strategy

candidate_keys = identity.extract_keys(candidate)
compatible = []
for record in existing_records:
    record_keys = identity.extract_record_keys(record)
    if identity.match_identity(candidate_keys, record_keys):
        compatible.append(record)

IF len(compatible) == 0:
    RETURN ReconciliationResult(
        action=CREATE, tier=2, match_id=None, similarity=0.0,
        identity_match=False, confidence=_confidence(CREATE, 0.0, len(existing_records)),
        reason="No identity-compatible records ({len(existing_records)} candidates evaluated, 0 compatible)",
        hooks_required=["recompute_centroid", "regenerate_summary"]
    )
```

**Why identity before similarity**: The POC proved that raw cosine similarity produces false matches between semantically similar but identity-distinct records (e.g., two different coffee-shop visits on different days). Identity filtering eliminates impossible matches before scoring, reducing false EXTEND/REINFORCE.

**Stage 4: Similarity Rank**

```
INPUT:  candidate.embedding (ndarray 768-dim),
        compatible (List[TruthRecord] from Stage 3)
OUTPUT: best_match (TruthRecord), best_similarity (float)

scored = []
for record in compatible:
    sim = cosine_similarity(candidate.embedding, record.embedding)
    scored.append((record, sim))

best_match, best_similarity = max(scored, key=lambda x: x[1])
```

**Note**: `cosine_similarity` here is numpy dot product on L2-normalized vectors (both candidate embedding from UltraBERT and record embedding from st_vec are already L2-normalized). This is NOT the Python-side-cosine-on-all-rows bug from the old TruthQueryService -- the records arriving here are already pre-filtered by pgvector ANN (M9.3) and identity (Stage 3), so the set is small (typically 1-10 records).

**Stage 5: Threshold Decision**

```
INPUT:  best_similarity (float),
        thresholds (ReconciliationThresholds from TruthLayerSpec via M9.1)
OUTPUT: ReconciliationAction

thresholds = spec.thresholds
# thresholds.reinforce, thresholds.extend, thresholds.evolve are per-layer from M9.1

IF best_similarity >= thresholds.reinforce:    action = REINFORCE
ELIF best_similarity >= thresholds.extend:     action = EXTEND
ELIF best_similarity >= thresholds.evolve:     action = EVOLVE
ELSE:                                          action = CREATE
```

**Per-layer thresholds** (from M9.1 TruthLayerSpec):

| Layer | reinforce | extend | evolve | Source |
|-------|-----------|--------|--------|--------|
| st_epi | 0.85 | 0.60 | 0.40 | POC-validated, EpisodicIdentity already handles thread+temporal |
| st_sem | 0.90 | 0.65 | 0.45 | Higher: semantic patterns need stronger match |
| st_procedural | 0.90 | 0.70 | 0.50 | Highest extend: routines are sticky, false extend is costly |
| st_social | 0.85 | 0.60 | 0.40 | Same as episodic: social context is broad |
| st_prospective | 0.80 | 0.55 | 0.40 | Lowest: free-text goals are fuzzy |
| st_kg_dom | 0.90 | 0.70 | 0.50 | Key-based layers: exact key match -> 1.0, bypasses cascade |
| st_kg_edges | 0.85 | 0.65 | 0.45 | Compound key: source+target+type, no embedding fallback |

**CONTRADICT is Tier 1 only**: Unlike the existing engine where `similarity < 0.40 + has_match => CONTRADICT`, the new framework reserves CONTRADICT exclusively for K1 signals. Low similarity with an identity match just means CREATE (new record). The rationale: statistical similarity alone cannot determine contradiction -- only an explicit correction/contradiction signal from K1 can.

**Key-based layers** (st_kg_dom, st_kg_edges): When EntityIdentity or EdgeIdentity returns `match_identity == True` (exact key match), the "similarity" is semantically 1.0 for identity purposes. The actual cosine similarity then determines the action:

- Keys match + content unchanged (high cosine) -> REINFORCE
- Keys match + content changed (lower cosine) -> EXTEND (merge via merge rules)

**Stage 6: Result Assembly**

```
INPUT:  action, best_match, best_similarity, identity_match=True, layer, candidate, spec
OUTPUT: ReconciliationResult

# Determine post-decision hooks
hooks = []
if action in (REINFORCE, EXTEND):
    hooks.append("recompute_centroid")
if action == EXTEND:
    hooks.append("regenerate_summary")
if action == EVOLVE:
    hooks.append("archive_superseded")
    hooks.append("recompute_centroid")
    hooks.append("regenerate_summary")
if action == CREATE:
    hooks.append("recompute_centroid")
    hooks.append("regenerate_summary")

confidence = ConfidenceModel.compute(
    action=action,
    similarity=best_similarity,
    compatible_count=len(compatible),
    total_candidates=len(existing_records),
    identity_match=True,
)

reason = _build_reason(action, best_similarity, best_match, layer, len(compatible))

RETURN ReconciliationResult(
    action=action,
    tier=2,
    match_id=best_match.record_id if action != CREATE else None,
    match_layer=layer,
    similarity=best_similarity,
    identity_match=True,
    confidence=confidence,
    reason=reason,
    candidate_id=candidate.candidate_id,
    layer=layer,
    cycle_id=candidate.cycle_id,
    hooks_required=hooks,
    contradiction_details=None,
    decision_time_ms=elapsed_ms,
)
```

**Hook semantics**:

| Hook | Trigger Actions | What It Means for M9.5/M9.6 |
|------|----------------|------------------------------|
| `recompute_centroid` | CREATE, REINFORCE, EXTEND, EVOLVE | Centroid recalc with HYBRID weighting (CentroidCalculator) |
| `regenerate_summary` | CREATE, EXTEND, EVOLVE | Layer-specific text generator -> UltraBERT -> new embedding |
| `archive_superseded` | EVOLVE | Old record status -> SUPERSEDED, version chain maintained |

---

#### M9.4.7 ReconciliationFramework Class (Target)

```python
# k0/modules/consolidation/reconciliation/engine.py

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.modules.consolidation.reconciliation.confidence import ConfidenceModel
from k0.modules.consolidation.reconciliation.metrics import DecisionMetrics
from k0.modules.consolidation.reconciliation.decision_log import log_decision
from k0.pipelines.p03.event_state import ReconciliationAction

# M9.2 types
from k0.modules.consolidation.reconciliation.identity import IdentityStrategy
# M9.3 types
from k0.modules.consolidation.reconciliation.types import TruthRecord, ReconciliationCandidate


class ReconciliationFramework:
    """
    Stateless decision machine. No DB reads. No DB writes.
    All state comes from arguments. decide() is the only decision path.
    """

    @staticmethod
    def decide(
        candidate: ReconciliationCandidate,
        layer: str,
        registry: TruthLayerRegistry,
        existing_records: List[TruthRecord],
    ) -> ReconciliationResult:
        """
        6-stage decision pipeline. Pure function.

        Args:
            candidate: The item to reconcile (from R2/R3/R4)
            layer: Target truth layer ("st_epi", "st_sem", etc.)
            registry: M9.1 TruthLayerRegistry (provides thresholds, identity strategy)
            existing_records: Pre-fetched truth records from M9.3 truth_candidates_query

        Returns:
            ReconciliationResult with action, match, confidence, hooks
        """
        t0 = time.perf_counter()
        spec = registry.get(layer)

        # Stage 1: K1 Signal Check (Tier 1)
        result = _check_k1_signals(candidate, layer)
        if result is not None:
            return _finalize(result, t0, candidate)

        # Stage 2: Override Check
        result = _check_overrides(candidate, layer)
        if result is not None:
            return _finalize(result, t0, candidate)

        # Stage 3: Identity Filter
        identity = spec.identity_strategy
        compatible = _filter_by_identity(candidate, existing_records, identity)

        if not compatible:
            return _finalize(_create_result(
                candidate, layer, 0.0, len(existing_records)
            ), t0, candidate)

        # Stage 4: Similarity Rank
        best_match, best_sim = _rank_by_similarity(candidate.embedding, compatible)

        # Stage 5: Threshold Decision
        action = _apply_thresholds(best_sim, spec.thresholds)

        # Stage 6: Result Assembly
        return _finalize(_assemble_result(
            action, candidate, layer, best_match, best_sim,
            compatible, existing_records, spec
        ), t0, candidate)


    @staticmethod
    def decide_batch(
        candidates: Sequence[ReconciliationCandidate],
        layer: str,
        registry: TruthLayerRegistry,
        existing_records: List[TruthRecord],
        metrics: Optional[DecisionMetrics] = None,
    ) -> Dict[str, ReconciliationResult]:
        """
        Batch decision: same pre-fetched records, N candidates.

        The caller is responsible for calling truth_candidates_query (M9.3) ONCE
        for (layer, space_id, tenant_id) and passing the result here.
        This avoids N separate DB queries for N candidates.

        Args:
            candidates: Batch of items to reconcile
            layer: Target truth layer
            registry: M9.1 registry
            existing_records: Pre-fetched records (shared across all candidates)
            metrics: Optional DecisionMetrics for Prometheus emission

        Returns:
            Dict[candidate_id -> ReconciliationResult]
        """
        results = {}
        for candidate in candidates:
            result = ReconciliationFramework.decide(
                candidate=candidate,
                layer=layer,
                registry=registry,
                existing_records=existing_records,
            )
            results[candidate.candidate_id] = result

            if metrics is not None:
                metrics.record_decision(result)

        return results
```

**Key design decisions**:

| Decision | Rationale |
|----------|-----------|
| `decide()` is `@staticmethod` | Pure function -- no `self` state, no instance variables, trivially testable |
| `existing_records` is an argument, not queried internally | Separation of concerns: M9.3 handles query, M9.4 handles decision. Enables batch deduplication: one query, N decisions |
| `decide_batch()` is NOT async | All inputs are pre-fetched. The only async operation (DB query) happens BEFORE `decide_batch()` is called. Decision logic is pure CPU computation (~0.5ms per candidate) |
| No `set_truth_service()` method | The framework does not own a truth service. The caller (R3, R2) owns the syscall and passes records |
| `metrics` is optional in `decide_batch()` | Allows unit tests to skip Prometheus; production code always passes metrics |

---

#### M9.4.8 ConfidenceModel (Explicit Formula)

The existing engine uses an ad-hoc Bayesian-style formula with magic numbers (L688-757). M9.4 replaces it with an explicit, testable model:

```python
# k0/modules/consolidation/reconciliation/confidence.py

from k0.pipelines.p03.event_state import ReconciliationAction

class ConfidenceModel:
    """
    Pure-function confidence computation.
    Confidence = base + evidence + identity_boost + count_boost.
    All values clamped to [0.0, 1.0].
    """

    # Per-action base confidence
    _BASE = {
        ReconciliationAction.REINFORCE:  0.50,
        ReconciliationAction.EXTEND:     0.45,
        ReconciliationAction.EVOLVE:     0.40,
        ReconciliationAction.CREATE:     0.35,
        ReconciliationAction.CONTRADICT: 0.90,  # Tier 1 only
        ReconciliationAction.SKIP:       1.00,  # Override, always certain
        ReconciliationAction.PRUNE:      1.00,  # Override, always certain
    }

    # Evidence weight: how much similarity contributes above the base
    _EVIDENCE_WEIGHT = {
        ReconciliationAction.REINFORCE:  0.40,  # sim 0.85-1.0 -> evidence 0.0-0.40
        ReconciliationAction.EXTEND:     0.35,  # sim 0.60-0.85 -> evidence 0.0-0.35
        ReconciliationAction.EVOLVE:     0.25,  # sim 0.40-0.60 -> evidence 0.0-0.25
        ReconciliationAction.CREATE:     0.15,  # no match -> small fixed evidence
    }

    @staticmethod
    def compute(
        action: ReconciliationAction,
        similarity: float,
        compatible_count: int,
        total_candidates: int,
        identity_match: bool,
    ) -> float:
        base = ConfidenceModel._BASE.get(action, 0.5)

        # Evidence from similarity (Tier 2 actions only)
        evidence = 0.0
        weight = ConfidenceModel._EVIDENCE_WEIGHT.get(action, 0.0)
        if action == ReconciliationAction.REINFORCE:
            # How far above reinforce threshold (0.85): (sim - 0.85) / 0.15
            evidence = weight * min(1.0, max(0.0, (similarity - 0.85) / 0.15))
        elif action == ReconciliationAction.EXTEND:
            # How far into extend range
            evidence = weight * min(1.0, max(0.0, (similarity - 0.60) / 0.25))
        elif action == ReconciliationAction.EVOLVE:
            evidence = weight * min(1.0, max(0.0, (similarity - 0.40) / 0.20))
        elif action == ReconciliationAction.CREATE:
            evidence = weight  # flat: no similarity signal

        # Identity boost: if identity keys matched, confidence increases
        identity_boost = 0.05 if identity_match else 0.0

        # Count boost: more candidates evaluated = more confident in the winner
        count_boost = 0.0
        if compatible_count >= 5:
            count_boost = 0.05
        elif compatible_count >= 3:
            count_boost = 0.02

        return max(0.0, min(1.0, base + evidence + identity_boost + count_boost))
```

**Confidence ranges** (with default episodic thresholds):

| Action | Sim Range | Confidence Range | Formula |
|--------|-----------|-----------------|---------|
| REINFORCE | 0.85-1.00 | 0.55-0.95 | 0.50 + 0.40*(sim-0.85)/0.15 + identity + count |
| EXTEND | 0.60-0.84 | 0.50-0.85 | 0.45 + 0.35*(sim-0.60)/0.25 + identity + count |
| EVOLVE | 0.40-0.59 | 0.45-0.70 | 0.40 + 0.25*(sim-0.40)/0.20 + identity + count |
| CREATE (no match) | 0.00 | 0.40-0.45 | 0.35 + 0.15 + count_boost |
| CREATE (below evolve) | < 0.40 | 0.40-0.45 | 0.35 + 0.15 + count_boost |
| CONTRADICT (Tier 1) | N/A | 0.90 | Fixed: K1 signal confidence |
| EVOLVE (Tier 1) | N/A | 0.95 | Fixed: K1 correction confidence |
| SKIP | N/A | 1.00 | Fixed: dedup override |
| PRUNE | N/A | 1.00 | Fixed: tombstone override |

---

#### M9.4.9 Batch Coordination Strategy

The existing `ReconciliationEngine.decide_batch()` (L382-414) runs sequentially: each event triggers a separate `TruthQueryService.find_candidates()` call. For a batch of 50 events all going to `st_sem`, this means 50 separate DB queries.

M9.4 splits batch processing into two phases:

**Phase A: Query (caller's responsibility, NOT inside framework)**

```python
# In R3 (or whichever phase):
# 1. Group candidates by layer
candidates_by_layer: Dict[str, List[ReconciliationCandidate]] = group_by_layer(candidates)

# 2. One truth query per layer (using M9.3 syscall)
records_by_layer: Dict[str, List[TruthRecord]] = {}
for layer, layer_candidates in candidates_by_layer.items():
    # Gather all embeddings for this layer
    embeddings = [c.embedding for c in layer_candidates]
    # Single M9.3 syscall: fetches all candidates for this (layer, space, tenant)
    response = await syscalls.truth_candidates_query(
        layer=layer,
        space_id=space_id,
        tenant_id=tenant_id,
        embeddings=embeddings,  # M9.3 handles multi-embedding ANN
        top_k=spec.top_k,
    )
    records_by_layer[layer] = response.candidates.get(layer, [])
```

**Phase B: Decision (inside framework)**

```python
# 3. Batch decide per layer
for layer, layer_candidates in candidates_by_layer.items():
    results = ReconciliationFramework.decide_batch(
        candidates=layer_candidates,
        layer=layer,
        registry=registry,
        existing_records=records_by_layer[layer],
        metrics=metrics,
    )
    all_results.update(results)
```

**Query deduplication benefit**: For a typical P03 batch (260 events):

- R2: 1 query to st_epi (not 60 per-episode-candidate queries)
- R3: 1 query to st_sem + 1 to st_procedural + 1 to st_social + 1 to st_prospective (4 queries, not 260)
- Total: 5 queries instead of 320

---

#### M9.4.10 Reason String Format

Every `ReconciliationResult.reason` follows a structured format for machine parsing and human readability:

```
Tier 1 reasons:
  "K1_CORRECTION: correction_source={source}, session={session_id}"
  "K1_CONTRADICTION: supersedes_concept={concept}, correction_source={source}"

Tier 2 override reasons:
  "OVERRIDE_SKIP: duplicate_of={duplicate_of_id}"
  "OVERRIDE_PRUNE: prune_decision=TOMBSTONE"

Tier 2 identity filter reasons:
  "IDENTITY_FILTER: 0/{total} candidates identity-compatible -> CREATE"

Tier 2 threshold reasons:
  "REINFORCE: sim={sim:.4f} >= threshold={thresh:.2f}, match={match_id}, layer={layer}, compatible={n}/{total}"
  "EXTEND: sim={sim:.4f} >= threshold={thresh:.2f}, match={match_id}, layer={layer}, compatible={n}/{total}"
  "EVOLVE: sim={sim:.4f} >= threshold={thresh:.2f}, match={match_id}, layer={layer}, compatible={n}/{total}"
  "CREATE: sim={sim:.4f} < evolve_threshold={thresh:.2f}, best_match={match_id}, layer={layer}, compatible={n}/{total}"
```

All reasons include the threshold value that was applied, enabling post-hoc analysis of threshold sensitivity without re-running the pipeline.

---

#### M9.4.11 DecisionMetrics (Prometheus Counters)

The absorbed M7 7.5 observability work. Uses the existing `P03MetricsRegistry` (at `k0/pipelines/p03/ops/metrics.py`) and `K0 MetricsExporter` (at `k0/obs/metrics.py`):

```python
# k0/modules/consolidation/reconciliation/metrics.py

class DecisionMetrics:
    """Per-batch Prometheus emission. Created per P03 cycle, not singleton."""

    def __init__(self, metrics_registry):
        self._registry = metrics_registry

    def record_decision(self, result: ReconciliationResult) -> None:
        """Record a single decision to Prometheus counters."""
        # Counter: total decisions by (layer, action)
        self._registry.counter(
            "reconciliation_decisions_total",
            labels={"layer": result.layer, "action": result.action.value},
        )

        # Histogram: confidence distribution by (layer, action)
        self._registry.observe(
            "reconciliation_decision_confidence",
            value=result.confidence,
            labels={"layer": result.layer, "action": result.action.value},
        )

        # Histogram: similarity distribution by (layer, action) -- Tier 2 only
        if result.tier == 2 and result.similarity > 0.0:
            self._registry.observe(
                "reconciliation_similarity_score",
                value=result.similarity,
                labels={"layer": result.layer, "action": result.action.value},
            )

        # Histogram: decision latency
        self._registry.observe(
            "reconciliation_decision_latency_ms",
            value=result.decision_time_ms,
            labels={"layer": result.layer},
        )

        # Counter: K1 bypass (Tier 1 only)
        if result.tier == 1:
            signal_type = "correction" if result.action == ReconciliationAction.EVOLVE else "contradiction"
            self._registry.counter(
                "reconciliation_k1_bypass_total",
                labels={"signal_type": signal_type},
            )

    def record_batch_summary(
        self, layer: str, batch_size: int, identity_filtered: int, results: Dict[str, ReconciliationResult]
    ) -> None:
        """Record batch-level aggregates after decide_batch()."""
        # Gauge: batch size
        self._registry.gauge(
            "reconciliation_batch_size",
            value=batch_size,
            labels={"layer": layer},
        )

        # Gauge: identity filter ratio (what fraction was filtered out)
        if batch_size > 0:
            self._registry.gauge(
                "reconciliation_identity_filter_ratio",
                value=identity_filtered / batch_size,
                labels={"layer": layer},
            )

        # Per-action counts in this batch
        action_counts = {}
        for r in results.values():
            action_counts[r.action.value] = action_counts.get(r.action.value, 0) + 1
        for action_name, count in action_counts.items():
            self._registry.gauge(
                "reconciliation_batch_action_count",
                value=count,
                labels={"layer": layer, "action": action_name},
            )
```

**Metric names** (all prefixed by `k0_kernel_` namespace via MetricsExporter):

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `reconciliation_decisions_total` | Counter | layer, action | Total decisions per action per layer |
| `reconciliation_decision_confidence` | Histogram | layer, action | Confidence distribution |
| `reconciliation_similarity_score` | Histogram | layer, action | Similarity distribution (Tier 2 only) |
| `reconciliation_decision_latency_ms` | Histogram | layer | Per-decision wall clock |
| `reconciliation_k1_bypass_total` | Counter | signal_type | K1 override count |
| `reconciliation_batch_size` | Gauge | layer | Candidates per batch per layer |
| `reconciliation_identity_filter_ratio` | Gauge | layer | Fraction filtered by identity |
| `reconciliation_batch_action_count` | Gauge | layer, action | Actions per batch |

---

#### M9.4.12 Structured Decision Log

Every decision is logged as a structured JSON line via `k0.obs.logging.StructuredLogFormatter`:

```python
# k0/modules/consolidation/reconciliation/decision_log.py

import structlog

logger = structlog.get_logger("k0.reconciliation")

def log_decision(result: ReconciliationResult) -> None:
    """Emit one structured log line per decision."""
    logger.info(
        "reconciliation_decision",
        cycle_id=result.cycle_id,
        candidate_id=result.candidate_id,
        layer=result.layer,
        action=result.action.value,
        tier=result.tier,
        similarity=round(result.similarity, 4),
        confidence=round(result.confidence, 4),
        match_id=result.match_id,
        identity_match=result.identity_match,
        hooks=result.hooks_required,
        reason=result.reason,
        decision_time_ms=round(result.decision_time_ms, 2),
    )
```

**Log fields** align with `PhaseTransitionEvent` (at `k0/pipelines/p03/observability.py`) for cross-phase correlation:

- `cycle_id` joins with `PhaseTransitionEvent.cycle_id`
- `candidate_id` traces back to source event(s) via `ReconciliationCandidate.source_event_ids`
- `layer` enables per-layer log filtering

---

#### M9.4.13 YAML Contract (reconciliation.framework.v1.yaml)

```yaml
# k0/contracts/modules/reconciliation.framework.v1.yaml
module: reconciliation.framework
version: v1
status: planning

description: >
  Stateless 6-stage decision pipeline that produces ReconciliationResult
  from ReconciliationCandidate + pre-fetched TruthRecords.

dependencies:
  - module: reconciliation.truth_layer_registry
    version: v1
    provides: TruthLayerSpec, ReconciliationThresholds
  - module: reconciliation.identity_strategy
    version: v1
    provides: IdentityStrategy protocol
  - module: reconciliation.truth_candidates_query
    version: v1
    provides: TruthRecord, TruthCandidateResponse

input:
  type: ReconciliationCandidate
  source: R2 (st_epi), R3 (st_sem, st_procedural, st_social, st_prospective), R4 (st_kg_dom, st_kg_edges)
  required_fields:
    - candidate_id
    - embedding         # ndarray(768,) L2-normalized
    - k1_signals        # K1SignalBundle
    - metadata          # Dict with optional is_duplicate, prune_decision
    - source_phase
    - source_event_ids
    - tenant_id
    - space_id
    - cycle_id

output:
  type: ReconciliationResult
  consumed_by:
    - WriteDecisionRouter (M9.5)
    - R6 staging pipeline
    - ReconciliationRecorder (audit)
  fields:
    - action            # ReconciliationAction enum
    - tier              # 1 or 2
    - match_id          # Optional[str]
    - match_layer       # str
    - similarity        # float [0.0, 1.0]
    - identity_match    # bool
    - confidence        # float [0.0, 1.0]
    - reason            # str (structured format)
    - candidate_id      # str
    - layer             # str
    - cycle_id          # str
    - hooks_required    # List[str]
    - contradiction_details  # Optional[Dict]
    - decision_time_ms  # float

pipeline_stages:
  - stage: 1
    name: K1 Signal Check
    tier: 1
    actions: [EVOLVE, CONTRADICT]
    short_circuit: true
  - stage: 2
    name: Override Check
    tier: 2
    actions: [SKIP, PRUNE]
    short_circuit: true
  - stage: 3
    name: Identity Filter
    tier: 2
    actions: [CREATE]
    short_circuit: true  # if 0 compatible
  - stage: 4
    name: Similarity Rank
    tier: 2
    actions: []
    short_circuit: false
  - stage: 5
    name: Threshold Decision
    tier: 2
    actions: [REINFORCE, EXTEND, EVOLVE, CREATE]
    short_circuit: false
  - stage: 6
    name: Result Assembly
    tier: 2
    actions: []
    short_circuit: false

invariants:
  - "decide() is a pure function: no DB reads, no DB writes, no instance state"
  - "Tier 1 always fires before Tier 2"
  - "Identity filtering happens before similarity ranking"
  - "match_id is None iff action in {CREATE, SKIP}"
  - "similarity == 0.0 when tier == 1"
  - "hooks_required is never None"
  - "ReconciliationAction enum reused from k0.pipelines.p03.event_state (no new enum)"

observability:
  prometheus_metrics:
    - reconciliation_decisions_total
    - reconciliation_decision_confidence
    - reconciliation_similarity_score
    - reconciliation_decision_latency_ms
    - reconciliation_k1_bypass_total
    - reconciliation_batch_size
    - reconciliation_identity_filter_ratio
    - reconciliation_batch_action_count
  structured_log_event: reconciliation_decision
```

---

#### M9.4.14 Integration with Existing P03EventState

The framework does NOT modify `P03EventState` directly. The calling phase (R2, R3) is responsible for mapping `ReconciliationResult` fields back to the event:

```python
# In R3 (or R2), after calling framework.decide():
event.set_reconciliation(
    action=result.action,                          # ReconciliationAction enum
    match_id=result.match_id,                      # Optional[str]
    match_layer=result.match_layer,                # str
    similarity=result.similarity,                  # float
    confidence=result.confidence,                  # float
    reason=result.reason,                          # str
)
```

This mapping preserves the existing R6 contract: `R6Coordinator._build_event_updates()` (at `k0/modules/consolidation/staging/r6_coordinator.py` L545) reads `state.reconciliation_action.value`, `state.best_match_id`, etc. The M9.4 framework produces the same field set, just via a cleaner code path.

**What changes for R6**: Nothing. R6 continues to read `P03EventState` fields. The difference is upstream: R3 calls `ReconciliationFramework.decide()` instead of `ReconciliationEngine.decide()`, then maps the result to the same event fields.

---

#### M9.4.15 Layer Ownership Invariant

Each truth layer is decided exactly once by exactly one phase. The framework enforces this via the `layer` argument -- the caller declares which layer it is reconciling:

| Phase | Calls `decide(layer=...)` with | Layers | Granularity |
|-------|-------------------------------|--------|-------------|
| R2 | `"st_epi"` | st_epi only | Per-EpisodeCandidate (cluster-level) |
| R3 | `"st_sem"`, `"st_procedural"`, `"st_social"`, `"st_prospective"` | 4 non-episodic layers | Per-event |
| R4 | `"st_kg_dom"`, `"st_kg_edges"` | 2 KG layers | Per-entity / per-edge |

**R3 no longer queries st_epi**: In the current code, `ReconciliationEngine` queries all 5 layers (`DEFAULT_TRUTH_LAYERS`). After M9.8 migration, R3 only queries its 4 owned layers. This eliminates the dual-decision problem where both R2 and R3 could make conflicting decisions about the same episodic record.

---

#### M9.4.16 Error Handling Strategy

The framework is a pure function, so error handling is minimal and explicit:

| Error | Where | Handling |
|-------|-------|----------|
| `candidate.embedding is None` | Stage 4 (Similarity Rank) | Return CREATE with confidence 0.35, reason="No embedding available" |
| `existing_records is empty` | Stage 3 (Identity Filter) | Return CREATE with confidence 0.40, reason="No existing records for layer" |
| `identity_strategy raises` | Stage 3 | Let exception propagate -- caller catches and logs. No silent swallowing |
| `cosine_similarity NaN` | Stage 4 | Treat as 0.0 similarity (both vectors should be L2-normalized, NaN means corrupt input) |
| `registry.get(layer) raises KeyError` | Top of decide() | Let exception propagate -- unknown layer is a configuration error, not a runtime error |
| `candidate.k1_signals is None` | Stage 1 | Treat as no K1 signals (skip Tier 1), proceed to Stage 2 |

**No silent failures**: The existing engine catches `TimeoutError` and general `Exception` and silently returns `[]` (all events become CREATE). The new framework does not catch exceptions -- if the query fails, the caller (R3) handles it, not the decision function. This is because the framework does not own the query.

---

#### M9.4.17 Execution Steps (Ordered)

| Step | Action | Output | Verification |
|------|--------|--------|--------------|
| 1 | Create `k0/modules/consolidation/reconciliation/result.py` | ReconciliationResult frozen dataclass (14 fields) | `test_engine.py::test_result_immutable`, `test_engine.py::test_result_invariants` |
| 2 | Create `k0/modules/consolidation/reconciliation/confidence.py` | ConfidenceModel.compute() static method | `test_confidence.py::test_reinforce_confidence_range`, `test_confidence.py::test_monotonicity` |
| 3 | Create `k0/modules/consolidation/reconciliation/engine.py` | ReconciliationFramework.decide() + decide_batch() | `test_engine.py::test_k1_correction_evolve`, `test_engine.py::test_threshold_cascade` |
| 4 | Create `k0/modules/consolidation/reconciliation/metrics.py` | DecisionMetrics class | `test_engine.py::test_metrics_recorded` |
| 5 | Create `k0/modules/consolidation/reconciliation/decision_log.py` | log_decision() function | `test_engine.py::test_decision_logged` |
| 6 | Create `k0/contracts/modules/reconciliation.framework.v1.yaml` | Contract YAML | CI schema validation |
| 7 | Create `tests/.../test_engine.py` | Per-stage unit tests (30+ test cases) | pytest passes |
| 8 | Create `tests/.../test_batch.py` | Batch coordination tests (10+ test cases) | pytest passes |
| 9 | Create `tests/.../test_confidence.py` | Confidence model tests (15+ test cases) | pytest passes |
| 10 | Create `tests/.../test_golden_decisions.py` | Golden data end-to-end tests (7+ vectors, one per action) | pytest passes |
| 11 | Verify: old `ReconciliationEngine` still works | No edits to existing files | Existing tests pass unchanged |
| 12 | Verify: framework produces same actions as old engine for identical inputs | Regression comparison test | Action agreement >= 95% on test corpus |

---

#### M9.4.18 Golden Decision Vectors (Test Data)

7 golden vectors, one per action, with exact expected outputs:

| # | Action | Candidate Setup | Existing Records | Expected |
|---|--------|----------------|------------------|----------|
| G1 | EVOLVE (Tier 1) | `k1_signals.correction_signal=True, correction_source="user_edit"` | Any (irrelevant) | `action=EVOLVE, tier=1, similarity=0.0, confidence=0.95` |
| G2 | CONTRADICT (Tier 1) | `k1_signals.contradiction_signal=True, supersedes_concept="old_fact"` | Any (irrelevant) | `action=CONTRADICT, tier=1, similarity=0.0, confidence=0.90, contradiction_details != None` |
| G3 | SKIP (Override) | `metadata.is_duplicate=True` | Any (irrelevant) | `action=SKIP, tier=2, confidence=1.0` |
| G4 | REINFORCE (Tier 2) | Episodic candidate, sim=0.92 to existing ep | 1 identity-compatible record with sim=0.92 | `action=REINFORCE, tier=2, similarity=0.92, match_id=ep_id, hooks=["recompute_centroid"]` |
| G5 | EXTEND (Tier 2) | Episodic candidate, sim=0.72 to existing ep | 1 identity-compatible record with sim=0.72 | `action=EXTEND, tier=2, similarity=0.72, hooks=["recompute_centroid", "regenerate_summary"]` |
| G6 | EVOLVE (Tier 2) | Episodic candidate, sim=0.48 to existing ep | 1 identity-compatible record with sim=0.48 | `action=EVOLVE, tier=2, similarity=0.48, hooks=["archive_superseded", "recompute_centroid", "regenerate_summary"]` |
| G7 | CREATE (Tier 2) | Episodic candidate, no identity-compatible records | 5 records, none identity-compatible | `action=CREATE, tier=2, similarity=0.0, match_id=None, hooks=["recompute_centroid", "regenerate_summary"]` |

---

#### M9.4.19 Key Design Decisions

| # | Decision | Rationale | Alternative Considered | Why Rejected |
|---|----------|-----------|----------------------|--------------|
| KD1 | `decide()` is a pure static method, not async | All inputs pre-fetched; no I/O inside the decision function | async decide() that queries DB internally | Violates separation of concerns; prevents batch query deduplication |
| KD2 | CONTRADICT is Tier 1 only (K1 signals), NOT Tier 2 (low similarity) | Low similarity != contradiction; only explicit K1 agent/user action can determine contradiction | Keep existing `sim < 0.40 + has_match => CONTRADICT` | False positives: many legitimately low-similarity records are just CREATE, not contradictions |
| KD3 | No `ReconciliationConfig` dataclass | Thresholds come from TruthLayerSpec (M9.1), not a separate config | Keep ReconciliationConfig alongside TruthLayerSpec | Dual-config creates ambiguity about which threshold wins |
| KD4 | Identity filter before similarity rank | POC showed cosine-only matching produces false EXTEND between distinct entities | Similarity first, identity as tiebreaker | Identity filtering is O(N) key comparison, cheap; doing similarity first wastes computation on impossible matches |
| KD5 | hooks_required is a list of strings, not enum | Hooks evolve independently of the framework; M9.6 defines what each hook means | HookType enum in M9.4 | Tight coupling: adding a hook would require editing M9.4 code |
| KD6 | Reuse existing ReconciliationAction enum from event_state.py | 8 values already defined, imported by 13 files; creating a new enum creates migration burden | New enum in reconciliation/ | All downstream consumers (R6, R7, R8, recorder, router) already import from event_state.py |
| KD7 | Batch processing = caller queries, framework decides | Enables query deduplication (1 query per layer vs N per candidate) | Framework owns batch query | Framework becomes stateful (needs DB connection), can no longer be tested without DB |
| KD8 | Per-layer thresholds, not global | POC showed episodic 0.85/0.60/0.40 works but procedural needs 0.90/0.70/0.50 | Global thresholds with per-layer override | Override mechanism is complex; registry already has per-layer spec |
| KD9 | ConfidenceModel is a separate class | Enables isolated testing of confidence formula without running full pipeline | Inline confidence computation in decide() | 60-line formula clutters the 6-stage pipeline; separate class is testable |
| KD10 | No Python-side cosine on all candidates | M9.3 already returns pgvector-ranked candidates; Stage 4 cosine is only on identity-compatible subset (1-10 records) | Skip Stage 4, use M9.3 similarity directly | Identity filtering may reorder: M9.3 top-1 by cosine may not be identity-compatible, and M9.3 #3 might be the true match |

---

#### M9.4.20 What M9.4 Depends On (Input Contract Summary)

| Dependency | Service | What M9.4 Receives | How |
|-----------|---------|--------------------|----|
| TruthLayerRegistry | M9.1 | `TruthLayerSpec` with `thresholds` (reinforce, extend, evolve), `identity_strategy` (IdentityStrategy instance), `pk_column`, `confidence_column` | `registry.get(layer)` |
| IdentityStrategy | M9.2 | `extract_keys(candidate) -> Dict`, `extract_record_keys(record) -> Dict`, `match_identity(cand_keys, rec_keys) -> bool` | `spec.identity_strategy.match_identity()` |
| ReconciliationCandidate | M9.2 | Frozen dataclass: candidate_id, embedding, k1_signals, metadata, source_phase, source_event_ids, tenant_id, space_id, cycle_id | Built by R2/R3/R4 from P03EventState |
| K1SignalBundle | M9.2 | correction_signal: bool, contradiction_signal: bool, supersedes_concept: Optional[str], correction_source: Optional[str], session_context_id: Optional[str] | Inside ReconciliationCandidate.k1_signals |
| TruthRecord | M9.3 | record_id, layer, embedding (ndarray), confidence, version, observation_count, last_observed_ms, metadata: Dict | From `truth_candidates_query` response |
| truth_candidates_query | M9.3 | Syscall that returns `TruthCandidateResponse` with `candidates: Dict[str, List[TruthRecord]]` | Called by R2/R3/R4 BEFORE calling framework.decide() |

---

#### M9.4.21 What M9.4 Produces (Output Contract Summary)

| Consumer | Milestone | What It Receives | How |
|----------|-----------|-----------------|-----|
| WriteDecisionRouter | M9.5 | `ReconciliationResult.action` + `match_id` + `match_layer` + `hooks_required` | Router maps action -> StagedWrite (INSERT/UPDATE/ARCHIVE) |
| R6 Coordinator | Existing | `P03EventState` fields set by calling phase (R2/R3) from ReconciliationResult | `event.set_reconciliation(action, match_id, ...)` |
| ReconciliationRecorder | Existing | `ReconciliationResult` fields for audit JSON | `reconciliation_json` column in st_hipp_events |
| R8 Bus Events | Existing | `ReconciliationResult.action` -> topic mapping | CREATE->p03.truth.created.v1, REINFORCE->p03.truth.reinforced.v1, EXTEND->p03.truth.reinforced.v1, EVOLVE->p03.truth.evolved.v1, CONTRADICT->p03.gap.detected.v1 |
| Summary Generator (M9.6) | M9.6 | `hooks_required` contains "regenerate_summary" | Text generator + UltraBERT re-embedding |
| Centroid Calculator (M9.6) | M9.6 | `hooks_required` contains "recompute_centroid" | CentroidCalculator.compute() with HYBRID weighting |

---

#### M9.4.22 Validation Criteria (Exit Gates)

| # | Criterion | How to Verify |
|---|----------|---------------|
| V1 | `decide()` is a pure function: no DB reads, no DB writes | grep for `await`, `pool`, `connection`, `query`, `execute` in engine.py returns 0 matches |
| V2 | K1 correction signal -> EVOLVE with tier=1 | `test_engine.py::test_k1_correction_returns_evolve` |
| V3 | K1 contradiction signal -> CONTRADICT with tier=1, contradiction_details populated | `test_engine.py::test_k1_contradiction_returns_contradict_with_details` |
| V4 | is_duplicate -> SKIP with confidence=1.0 | `test_engine.py::test_override_skip` |
| V5 | prune_decision=TOMBSTONE -> PRUNE with confidence=1.0 | `test_engine.py::test_override_prune` |
| V6 | 0 identity-compatible records -> CREATE | `test_engine.py::test_identity_filter_empty_creates` |
| V7 | sim >= reinforce threshold -> REINFORCE | `test_engine.py::test_threshold_reinforce` |
| V8 | extend <= sim < reinforce -> EXTEND | `test_engine.py::test_threshold_extend` |
| V9 | evolve <= sim < extend -> EVOLVE (Tier 2) | `test_engine.py::test_threshold_evolve_tier2` |
| V10 | sim < evolve threshold -> CREATE (not CONTRADICT) | `test_engine.py::test_below_evolve_creates_not_contradicts` |
| V11 | Per-layer thresholds used (not hardcoded 0.85/0.60/0.40) | `test_engine.py::test_custom_thresholds` -- pass TruthLayerSpec with 0.90/0.70/0.50, verify behavior |
| V12 | decide_batch() produces same results as N individual decide() calls | `test_batch.py::test_batch_equals_individual` |
| V13 | decide_batch() with empty candidates returns empty dict | `test_batch.py::test_empty_batch` |
| V14 | Confidence monotonically increases with similarity for same action | `test_confidence.py::test_reinforce_monotonic`, `test_extend_monotonic` |
| V15 | Confidence in [0.0, 1.0] for all inputs | `test_confidence.py::test_confidence_bounds` (property test with random inputs) |
| V16 | hooks_required correct per action | `test_engine.py::test_reinforce_hooks`, `test_extend_hooks`, `test_evolve_hooks`, `test_create_hooks` |
| V17 | Golden vectors G1-G7 all pass | `test_golden_decisions.py::test_golden_*` (7 tests) |
| V18 | ReconciliationResult is frozen (immutable) | `test_engine.py::test_result_frozen` -- `setattr` raises `FrozenInstanceError` |
| V19 | DecisionMetrics.record_decision() emits expected counters | `test_engine.py::test_metrics_emitted` (mock registry) |
| V20 | log_decision() produces structured JSON with all required fields | `test_engine.py::test_structured_log` (capture log output) |
| V21 | Existing ReconciliationEngine tests still pass | `pytest tests/k0/modules/consolidation/algorithms/test_reconciliation_engine.py` -- no modifications |
| V22 | No import of asyncio, asyncpg, or k0.db anywhere in engine.py | grep confirms pure synchronous code |
| V23 | ReconciliationAction enum NOT duplicated (imported from event_state.py) | Only one definition in codebase |

---

#### M9.4.23 What M9.4 Does NOT Do

| Out of Scope | Why | When |
|-------------|-----|------|
| Modify existing `ReconciliationEngine` | Still in use by R3 until M9.8 phase migration | M9.8 |
| Modify existing `CrossBatchExtendMatcher` | Still in use by R2 until M9.8 phase migration | M9.8 |
| Build `WriteDecisionRouter` (action -> StagedWrite) | Separate concern: M9.4 decides, M9.5 writes | M9.5 |
| Build structured summary generator | Post-decision hook, separate module | M9.6 |
| Build centroid recomputation | Post-decision hook, separate module | M9.6 |
| Wire R2/R3 to call the framework | Phase migration is a separate milestone | M9.8 |
| Implement SemanticIdentity, SocialIdentity, etc. | Only EpisodicIdentity needed for validation | M9.7 |
| Add PRUNE sweep logic | Timer-based, not triggered by incoming batch | M9.9 |
| Delete old `reconciliation_engine.py` | Still in use until full migration | M9.8 |
| Make thresholds hot-reloadable | YAGNI: config reloads require pipeline restart anyway | Future if needed |
| Handle multi-embedding candidates | Current contract: one embedding per candidate | Future if needed |
| Parallel decide() across layers | CPU-bound pure function, parallelism adds complexity for ~1ms savings | Future if needed |

---

### M9.5 -- Write Decision Router

Build the action-to-StagedWrite mapping layer.

**Status**: READY TO IMPLEMENT
**Estimated Scope**: 1 router module + 1 merge engine + 1 EVOLVE handler + 1 idempotency helper + 1 contract YAML + tests
**Depends on**: M9.1 (TruthLayerSpec with merge rules per column), M9.4 (ReconciliationResult with action + match_id + hooks_required)
**Replaces**: 12+ bespoke `_create_*_insert()` / `_create_*_update()` methods scattered across `TruthWriteAssembler` (2000+ lines at `k0/modules/consolidation/staging/truth_write_assembler.py`)
**Reuses**: `StagedWrite`, `WriteOperation`, `P03StagedWrites` from `k0/pipelines/p03/staged_writes.py` (unchanged)

---

#### M9.5.1 Objective

Create the `WriteDecisionRouter` -- a data-driven mapping layer that converts a `ReconciliationResult` (from M9.4) into one or more `StagedWrite` objects ready for R7 execution. The router reads merge rules from `TruthLayerSpec` (M9.1) to mechanically apply per-column merge logic during EXTEND, eliminating the need for 12+ hand-coded assembler methods that duplicate merge logic across layers.

The router must:

1. Map each of the 6 reconciliation actions to the correct `WriteOperation` (INSERT, UPDATE, ARCHIVE, TOMBSTONE)
2. Apply the 16 merge rule types (M9.1.5) per column during EXTEND -- reading the rule from `TruthLayerSpec.columns`, not from hardcoded SQL
3. Handle EVOLVE as exactly 2 writes: INSERT new canonical + UPDATE old to SUPERSEDED
4. Handle CONTRADICT as INSERT to `st_learning_queue` (truth NOT modified)
5. Generate deterministic idempotency keys per `StagedWrite`
6. Produce `StagedWrite` objects compatible with the existing R7 pipeline (no R7 changes)

---

#### M9.5.2 What M9.5 Replaces (Existing Code -> New Code)

| Existing Component | File | Lines | Problem | M9.5 Replacement |
|---|---|---|---|---|
| `TruthWriteAssembler._create_sem_insert()` | `truth_write_assembler.py` | L800-840 | Layer-specific INSERT with hardcoded columns | `WriteDecisionRouter.build(CREATE, ...)` -- generic INSERT from `candidate.record_data` |
| `TruthWriteAssembler._create_sem_update()` | same | L1038-1065 | Hardcoded REINFORCE/EXTEND update with `_action` routing key | `build(REINFORCE, ...)` and `build(EXTEND, ...)` with merge rules from TruthLayerSpec |
| `TruthWriteAssembler._create_sem_evolve_writes()` | same | L838-920 | EVOLVE-specific 2-write pattern baked into assembler | `EvolveHandler.build_evolve_pair()` -- generic 2-write pattern from spec |
| `TruthWriteAssembler._create_sem_archive()` | same | ~L1080 | Layer-specific ARCHIVE | `build(PRUNE, ...)` -- generic ARCHIVE/TOMBSTONE |
| `TruthWriteAssembler.assemble_epi_writes()` | same | L295-584 | 290 lines of episodic-specific write assembly | `build(action, spec=registry.get("st_epi"), ...)` |
| `KGWriteAssembler._create_entity_insert/update()` | `kg_write_assembler.py` | various | KG-specific with edge merging | `build(action, spec=registry.get("st_kg_dom"), ...)` |
| `KGWriteAssembler._merge_edge_writes()` | same | various | Batch dedup of same-edge writes | Router handles dedup via idempotency keys |
| Confidence boost per layer | Scattered across 7 layer writers | various | Each writer has its own boost formula | `spec.confidence_boost_strategy` drives generic boost in REINFORCE |
| `_action` routing key in `record_data` | `truth_write_assembler.py` | various | Magic string inside record_data to route writer behavior | Action is explicit `WriteOperation` enum on `StagedWrite`, no `_action` field needed |

---

#### M9.5.3 Deliverables

| # | Deliverable | File Path | New/Edit | Description |
|---|-----------|-----------|----------|-------------|
| D1 | WriteDecisionRouter class | `k0/modules/consolidation/reconciliation/router.py` | NEW | `build(result, candidate, spec)` static method, ~200 lines |
| D2 | MergeEngine class | `k0/modules/consolidation/reconciliation/merge_engine.py` | NEW | `apply_merge_rules(spec, candidate_data, existing_data)` -- per-column merge rule execution, ~250 lines |
| D3 | EvolveHandler | `k0/modules/consolidation/reconciliation/evolve_handler.py` | NEW | `build_evolve_pair(result, candidate, spec)` -- always returns exactly 2 StagedWrites, ~80 lines |
| D4 | ContradictHandler | `k0/modules/consolidation/reconciliation/contradict_handler.py` | NEW | `build_learning_queue_entry(result, candidate)` -- INSERT to st_learning_queue, ~60 lines |
| D5 | Router idempotency helper | `k0/modules/consolidation/reconciliation/idem.py` | NEW | `RouterIdempotencyKey.for_write(cycle_id, layer, record_id, action)` -- deterministic key gen, ~40 lines |
| D6 | YAML contract | `k0/contracts/modules/reconciliation.write_router.v1.yaml` | NEW | Input/output schemas, action-to-operation mapping |
| D7 | Unit tests: per-action | `tests/k0/modules/consolidation/reconciliation/test_router.py` | NEW | 6 actions x StagedWrite correctness (30+ tests) |
| D8 | Unit tests: merge engine | `tests/k0/modules/consolidation/reconciliation/test_merge_engine.py` | NEW | 16 merge rules x correctness (20+ tests) |
| D9 | Unit tests: EVOLVE handler | `tests/k0/modules/consolidation/reconciliation/test_evolve_handler.py` | NEW | 2-write pair, version chain, supersedes_id linking |
| D10 | Golden write tests | `tests/k0/modules/consolidation/reconciliation/test_golden_writes.py` | NEW | End-to-end: ReconciliationResult -> StagedWrite comparison vs existing assembler output |

---

#### M9.5.4 File Location Map (Complete)

```
NEW FILES:

  k0/modules/consolidation/reconciliation/
      router.py                         # D1: WriteDecisionRouter.build() static method
      merge_engine.py                   # D2: MergeEngine.apply_merge_rules() per-column
      evolve_handler.py                 # D3: EvolveHandler.build_evolve_pair()
      contradict_handler.py             # D4: ContradictHandler.build_learning_queue_entry()
      idem.py                           # D5: RouterIdempotencyKey.for_write()

  k0/contracts/modules/
      reconciliation.write_router.v1.yaml  # D6: Contract YAML

  tests/k0/modules/consolidation/reconciliation/
      test_router.py                    # D7: Per-action StagedWrite tests
      test_merge_engine.py              # D8: Per-merge-rule tests
      test_evolve_handler.py            # D9: EVOLVE 2-write pair tests
      test_golden_writes.py             # D10: Golden data end-to-end comparison


EXISTING FILES (NOT MODIFIED during M9.5):

  k0/pipelines/p03/staged_writes.py                                 # StagedWrite, WriteOperation, P03StagedWrites -- REUSED as-is
  k0/modules/consolidation/staging/truth_write_assembler.py          # Old assembler -- NOT modified, NOT deleted until M9.8
  k0/modules/consolidation/staging/kg_write_assembler.py             # Old KG assembler -- NOT modified until M9.8
  k0/modules/consolidation/staging/idempotency.py                    # Existing IdempotencyKeyGenerator -- REUSED as reference
  k0/modules/consolidation/truth_writer/layers/episodic.py           # R7 layer writer -- NOT modified (consumes StagedWrite unchanged)
  k0/modules/consolidation/truth_writer/layers/semantic.py           # R7 layer writer -- NOT modified
  k0/modules/consolidation/truth_writer/layers/procedural.py         # R7 layer writer -- NOT modified
  k0/modules/consolidation/truth_writer/layers/social.py             # R7 layer writer -- NOT modified
  k0/modules/consolidation/truth_writer/layers/kg.py                 # R7 layer writer -- NOT modified
  k0/pipelines/p03/phases/r7_truth_writer.py                         # R7 phase -- NOT modified
```

---

#### M9.5.5 Action-to-WriteOperation Mapping (Complete)

| ReconciliationAction | WriteOperation(s) | StagedWrites Count | Key Details |
|---------------------|-------------------|-------------------|-------------|
| CREATE | INSERT | 1 | New ULID record_id, full `candidate.record_data`, version=1 |
| REINFORCE | UPDATE | 1 | observation_count++, last_observed_at=now, version++, confidence boost per spec |
| EXTEND | UPDATE | 1 | Per-column merge rules from `spec.columns`, version++ |
| EVOLVE | UPDATE old + INSERT new | 2 | Write 1: old record `is_canonical=FALSE, archival_status=SUPERSEDED`. Write 2: new record with `supersedes_id=old.PK` |
| CONTRADICT | INSERT (st_learning_queue) | 1 | `target_layer`, `target_id`, `contradicting_event_ids`, `similarity`, truth NOT modified |
| PRUNE | ARCHIVE or TOMBSTONE | 1 | `archival_status=ARCHIVED` (decay) or `TOMBSTONE` (GDPR) |
| SKIP | (none) | 0 | No StagedWrite produced |

---

#### M9.5.6 WriteDecisionRouter Class (Target)

```python
# k0/modules/consolidation/reconciliation/router.py

from __future__ import annotations
from typing import List, Optional

from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry, TruthLayerSpec
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.modules.consolidation.reconciliation.merge_engine import MergeEngine
from k0.modules.consolidation.reconciliation.evolve_handler import EvolveHandler
from k0.modules.consolidation.reconciliation.contradict_handler import ContradictHandler
from k0.modules.consolidation.reconciliation.idem import RouterIdempotencyKey
from k0.pipelines.p03.event_state import ReconciliationAction
from k0.pipelines.p03.staged_writes import StagedWrite, WriteOperation

# M9.2 type
from k0.modules.consolidation.reconciliation.types import ReconciliationCandidate


class WriteDecisionRouter:
    """
    Data-driven mapping: ReconciliationResult -> StagedWrite(s).
    Reads merge rules from TruthLayerSpec. Zero knowledge of column semantics.
    """

    @staticmethod
    def build(
        result: ReconciliationResult,
        candidate: ReconciliationCandidate,
        spec: TruthLayerSpec,
        cycle_id: str,
    ) -> List[StagedWrite]:
        """
        Convert a reconciliation decision into write operations.

        Args:
            result: Decision from ReconciliationFramework.decide() (M9.4)
            candidate: The original candidate with record_data
            spec: Layer spec from TruthLayerRegistry (M9.1)
            cycle_id: P03 cycle ULID for idempotency

        Returns:
            List of StagedWrite objects (0 for SKIP, 1 for most, 2 for EVOLVE)
        """
        action = result.action

        if action == ReconciliationAction.SKIP:
            return []

        if action == ReconciliationAction.CREATE:
            return [_build_create(result, candidate, spec, cycle_id)]

        if action == ReconciliationAction.REINFORCE:
            return [_build_reinforce(result, candidate, spec, cycle_id)]

        if action == ReconciliationAction.EXTEND:
            return [_build_extend(result, candidate, spec, cycle_id)]

        if action == ReconciliationAction.EVOLVE:
            return EvolveHandler.build_evolve_pair(result, candidate, spec, cycle_id)

        if action == ReconciliationAction.CONTRADICT:
            return [ContradictHandler.build_learning_queue_entry(result, candidate, cycle_id)]

        if action == ReconciliationAction.PRUNE:
            return [_build_prune(result, candidate, spec, cycle_id)]

        return []  # PENDING -- should not reach here
```

**Key design**: Each `_build_*` function is a pure function that reads `spec` for column rules and `candidate.record_data` for values. No database access. No layer-specific `if layer == "st_epi"` branches.

---

#### M9.5.7 Per-Action Write Logic (Complete Specification)

**CREATE**:

```python
def _build_create(result, candidate, spec, cycle_id):
    record_data = dict(candidate.record_data)
    record_id = record_data.get(spec.pk_column) or generate_ulid()
    record_data.setdefault(spec.pk_column, record_id)
    record_data.setdefault(spec.version_column, 1)
    record_data.setdefault(spec.observation_count_column, 1)
    record_data.setdefault(spec.archival_status_column, spec.active_status_value)
    record_data.setdefault(spec.canonical_column, True)

    return StagedWrite(
        write_id=generate_ulid(),
        layer=spec.layer_name,
        operation=WriteOperation.INSERT,
        record_id=record_id,
        record_data=record_data,
        idempotency_key=RouterIdempotencyKey.for_write(cycle_id, spec.layer_name, record_id, "create"),
        source_phase=candidate.source_phase,
        source_event_ids=list(candidate.source_event_ids),
        expected_version=None,  # INSERT, no version check
    )
```

**REINFORCE**:

```python
def _build_reinforce(result, candidate, spec, cycle_id):
    record_data = {
        spec.observation_count_column: 1,                    # COUNTER: +1 in R7 SQL
        spec.temporal.last_observed: _now_ms(),               # REPLACED
    }

    # Per-layer confidence boost from spec
    if spec.confidence_boost_strategy == "additive_0.05":
        record_data["_confidence_boost"] = 0.05              # R7 writer: LEAST(conf + 0.05, 1.0)
    elif spec.confidence_boost_strategy == "multiplicative_1.1":
        record_data["_confidence_boost_factor"] = 1.1        # R7 writer: LEAST(conf * 1.1, 1.0)
    # "none" or "coalesce" -> no confidence change

    return StagedWrite(
        write_id=generate_ulid(),
        layer=spec.layer_name,
        operation=WriteOperation.UPDATE,
        record_id=result.match_id,
        record_data=record_data,
        idempotency_key=RouterIdempotencyKey.for_write(cycle_id, spec.layer_name, result.match_id, "reinforce"),
        source_phase=candidate.source_phase,
        source_event_ids=list(candidate.source_event_ids),
        expected_version=None,  # REINFORCE uses idempotent bump, no version check
    )
```

**EXTEND** (merge-rule-driven):

```python
def _build_extend(result, candidate, spec, cycle_id):
    # MergeEngine applies per-column merge rules from spec
    record_data = MergeEngine.build_extend_data(
        spec=spec,
        candidate_data=candidate.record_data,
        existing_record_id=result.match_id,
    )

    return StagedWrite(
        write_id=generate_ulid(),
        layer=spec.layer_name,
        operation=WriteOperation.UPDATE,
        record_id=result.match_id,
        record_data=record_data,
        idempotency_key=RouterIdempotencyKey.for_write(cycle_id, spec.layer_name, result.match_id, "extend"),
        source_phase=candidate.source_phase,
        source_event_ids=list(candidate.source_event_ids),
        expected_version=result.match_version if hasattr(result, "match_version") else None,
    )
```

**PRUNE**:

```python
def _build_prune(result, candidate, spec, cycle_id):
    # Determine ARCHIVE vs TOMBSTONE from candidate metadata
    is_tombstone = candidate.metadata.get("prune_decision") == "TOMBSTONE"
    operation = WriteOperation.TOMBSTONE if is_tombstone else WriteOperation.ARCHIVE

    record_data = {
        spec.archival_status_column: "TOMBSTONE" if is_tombstone else "ARCHIVED",
    }
    if not is_tombstone:
        record_data["archived_reason"] = candidate.metadata.get("prune_reason", "decay")

    return StagedWrite(
        write_id=generate_ulid(),
        layer=spec.layer_name,
        operation=operation,
        record_id=result.match_id or candidate.record_data.get(spec.pk_column, ""),
        record_data=record_data,
        idempotency_key=RouterIdempotencyKey.for_write(
            cycle_id, spec.layer_name, result.match_id or "", "prune"
        ),
        source_phase=candidate.source_phase,
        source_event_ids=list(candidate.source_event_ids),
        expected_version=None,
    )
```

---

#### M9.5.8 MergeEngine: Data-Driven EXTEND (Complete Specification)

The heart of M9.5. Instead of 12+ `_create_*_update()` methods with hardcoded SQL fragments, the MergeEngine reads `spec.columns` and applies each column's declared `MergeRule` mechanically.

```python
# k0/modules/consolidation/reconciliation/merge_engine.py

from k0.modules.consolidation.truth_layer_registry import TruthLayerSpec, MergeRule, ColumnSpec

class MergeEngine:
    """
    Data-driven per-column merge for EXTEND operations.
    Reads merge rules from TruthLayerSpec.columns.
    Produces record_data dict that R7 layer writers execute.
    """

    @staticmethod
    def build_extend_data(
        spec: TruthLayerSpec,
        candidate_data: dict,
        existing_record_id: str,
    ) -> dict:
        """
        Build the UPDATE record_data by applying merge rules to each column
        that has new data in candidate_data.

        Returns:
            Dict suitable for StagedWrite.record_data
        """
        record_data = {}

        for col_name, col_spec in spec.columns.items():
            if col_name not in candidate_data:
                continue  # No new data for this column, skip

            new_value = candidate_data[col_name]
            rule = col_spec.merge

            if rule == MergeRule.IMMUTABLE:
                continue  # Never update immutable columns

            elif rule == MergeRule.COUNTER:
                record_data[col_name] = new_value  # R7 SQL: col = col + N

            elif rule == MergeRule.REPLACED:
                record_data[col_name] = new_value  # R7 SQL: col = $new

            elif rule == MergeRule.COALESCE:
                record_data[col_name] = new_value  # R7 SQL: COALESCE($new, existing)

            elif rule == MergeRule.APPENDABLE_DISTINCT:
                # R7 SQL: jsonb_agg(DISTINCT elem) FROM (old UNION new)
                record_data[col_name] = new_value  # New items to append (deduped by R7)

            elif rule == MergeRule.APPENDABLE_ALL:
                # R7 SQL: jsonb_agg(value) FROM (old UNION ALL new)
                record_data[col_name] = new_value  # New items to append (no dedup)

            elif rule == MergeRule.APPENDABLE_CAPPED:
                # R7 SQL: jsonb array with LIMIT cap
                record_data[col_name] = new_value
                record_data[f"_{col_name}_cap"] = col_spec.cap  # E.g., 20

            elif rule == MergeRule.ADDITIVE_MERGE:
                # R7 SQL: jsonb_object_agg(key, sum_of_values)
                record_data[col_name] = new_value

            elif rule == MergeRule.SHALLOW_MERGE:
                # R7 SQL: existing::jsonb || new::jsonb
                record_data[col_name] = new_value

            elif rule == MergeRule.TEMPORAL_MIN:
                # R7 SQL: LEAST(existing, $new)
                record_data[col_name] = new_value

            elif rule == MergeRule.TEMPORAL_MAX:
                # R7 SQL: GREATEST(existing, $new)
                record_data[col_name] = new_value

            elif rule == MergeRule.EMA:
                # R7 SQL: old * (1 - alpha) + new * alpha
                record_data[col_name] = new_value
                record_data[f"_{col_name}_alpha"] = col_spec.ema_alpha  # E.g., 0.1

            elif rule == MergeRule.TREND:
                # R7 SQL: (new - old_avg) * beta + old_trend * (1-beta)
                record_data[col_name] = new_value

            elif rule == MergeRule.DERIVED:
                continue  # Derived columns recomputed by R7 from other columns

            elif rule == MergeRule.PG_ARRAY_CONCAT:
                # R7 SQL: existing || new::TEXT[]
                record_data[col_name] = new_value

            elif rule == MergeRule.STATUS:
                record_data[col_name] = new_value  # Lifecycle state transition

        # Always include version increment and last_observed
        record_data[spec.observation_count_column] = 1  # COUNTER: +1
        record_data[spec.temporal.last_observed] = _now_ms()

        return record_data
```

**Critical invariant**: MergeEngine does NOT execute SQL. It builds `record_data` dicts that existing R7 layer writers consume. The merge rule enum tells R7 *how* to apply each value (e.g., APPENDABLE_DISTINCT means JSON union, COUNTER means `col = col + N`). The actual SQL stays in the layer writers.

**Why this replaces 12+ methods**: Each existing assembler method (e.g., `_create_sem_update`, `_create_epi_update`, `_create_social_update`) hardcodes which columns to set and how. MergeEngine reads the same information from `spec.columns[col].merge`, making it generic across all 7 layers.

---

#### M9.5.9 EvolveHandler: Version Chain (Complete Specification)

EVOLVE always produces exactly 2 `StagedWrite` objects. This is the only action that produces more than one write.

```python
# k0/modules/consolidation/reconciliation/evolve_handler.py

class EvolveHandler:
    """
    Handles EVOLVE: UPDATE old record to SUPERSEDED + INSERT new canonical record.
    """

    @staticmethod
    def build_evolve_pair(
        result: ReconciliationResult,
        candidate: ReconciliationCandidate,
        spec: TruthLayerSpec,
        cycle_id: str,
    ) -> List[StagedWrite]:
        """Always returns exactly [archive_old, insert_new]."""

        old_record_id = result.match_id
        new_record_id = candidate.record_data.get(spec.pk_column) or generate_ulid()

        # Write 1: UPDATE old record -> SUPERSEDED (non-canonical)
        archive_old = StagedWrite(
            write_id=generate_ulid(),
            layer=spec.layer_name,
            operation=WriteOperation.UPDATE,
            record_id=old_record_id,
            record_data={
                spec.canonical_column: False,                    # is_canonical = FALSE
                spec.archival_status_column: "SUPERSEDED",       # New status
                "valid_to": _now_ms(),                           # When superseded
                spec.version_column: 1,                          # COUNTER: version++
            },
            idempotency_key=RouterIdempotencyKey.for_write(
                cycle_id, spec.layer_name, old_record_id, "evolve_archive"
            ),
            source_phase=candidate.source_phase,
            source_event_ids=list(candidate.source_event_ids),
            expected_version=None,  # No version check for archive
        )

        # Write 2: INSERT new canonical record (successor)
        new_data = dict(candidate.record_data)
        new_data[spec.pk_column] = new_record_id
        new_data[spec.supersedes_column] = old_record_id         # Version chain link
        new_data[spec.canonical_column] = True                   # is_canonical = TRUE
        new_data[spec.version_column] = 1                        # New record starts at v1
        new_data[spec.observation_count_column] = 1
        new_data[spec.archival_status_column] = spec.active_status_value  # "ACTIVE"

        insert_new = StagedWrite(
            write_id=generate_ulid(),
            layer=spec.layer_name,
            operation=WriteOperation.INSERT,
            record_id=new_record_id,
            record_data=new_data,
            idempotency_key=RouterIdempotencyKey.for_write(
                cycle_id, spec.layer_name, new_record_id, "evolve_create"
            ),
            source_phase=candidate.source_phase,
            source_event_ids=list(candidate.source_event_ids),
            expected_version=None,  # INSERT
        )

        return [archive_old, insert_new]
```

**Version chain semantics**:

- Old record: `is_canonical=FALSE`, `archival_status=SUPERSEDED`, `valid_to=now`
- New record: `supersedes_id=old.PK`, `is_canonical=TRUE`, `valid_from=now`
- To trace history: follow `supersedes_id` backward from canonical record
- Existing code confirms this pattern: `SemanticLayerWriter._evolve()` at `semantic.py` L523-548

---

#### M9.5.10 ContradictHandler: Learning Queue (Complete Specification)

CONTRADICT does NOT modify truth tables. It inserts a gap record into `st_learning_queue` for P06 active learning resolution.

```python
# k0/modules/consolidation/reconciliation/contradict_handler.py

class ContradictHandler:
    """
    Handles CONTRADICT: INSERT gap into st_learning_queue.
    Truth NOT modified -- P06 resolves contradictions.
    """

    @staticmethod
    def build_learning_queue_entry(
        result: ReconciliationResult,
        candidate: ReconciliationCandidate,
        cycle_id: str,
    ) -> StagedWrite:
        queue_id = generate_ulid()

        record_data = {
            "queue_id": queue_id,
            "gap_type": "CONTRADICTION",
            "target_layer": result.match_layer,
            "target_id": result.match_id,
            "contradicting_event_ids": list(candidate.source_event_ids),
            "similarity": result.similarity,
            "confidence": result.confidence,
            "context_json": _build_contradiction_context(result, candidate),
            "status": "PENDING",
            "priority": 80,  # High priority: user/K1 flagged contradiction
            "created_at_ms": _now_ms(),
            "tenant_id": candidate.tenant_id,
            "space_id": candidate.space_id,
        }

        return StagedWrite(
            write_id=generate_ulid(),
            layer="st_learning_queue",
            operation=WriteOperation.INSERT,
            record_id=queue_id,
            record_data=record_data,
            idempotency_key=RouterIdempotencyKey.for_write(
                cycle_id, "st_learning_queue", queue_id, "contradict"
            ),
            source_phase=candidate.source_phase,
            source_event_ids=list(candidate.source_event_ids),
            expected_version=None,
        )

    @staticmethod
    def _build_contradiction_context(result, candidate):
        """Build context JSON for P06 review."""
        import json
        ctx = {
            "contradiction_reason": result.reason,
            "tier": result.tier,
        }
        if result.contradiction_details:
            ctx["correction_source"] = result.contradiction_details.get("correction_source")
            ctx["supersedes_concept"] = result.contradiction_details.get("supersedes_concept")
            ctx["session_context_id"] = result.contradiction_details.get("session_context_id")
        return json.dumps(ctx)
```

---

#### M9.5.11 RouterIdempotencyKey (Complete Specification)

Deterministic key generation compatible with existing `IdempotencyKeyGenerator` (at `k0/modules/consolidation/staging/idempotency.py`):

```python
# k0/modules/consolidation/reconciliation/idem.py

import hashlib

class RouterIdempotencyKey:
    """
    Deterministic idempotency key generation for router-produced StagedWrites.
    Pattern: p03:reconcile:{cycle_ulid}:{layer}:{record_id}:{action_suffix}
    """

    @staticmethod
    def for_write(cycle_id: str, layer: str, record_id: str, action_suffix: str) -> str:
        """
        Generate idempotency key.

        Args:
            cycle_id: P03 cycle ULID (26 chars)
            layer: Truth layer name (st_epi, st_sem, etc.)
            record_id: Target record PK
            action_suffix: "create", "reinforce", "extend", "evolve_archive",
                           "evolve_create", "contradict", "prune"
        """
        return f"p03:reconcile:{cycle_id}:{layer}:{record_id}:{action_suffix}"

    @staticmethod
    def for_batch(cycle_id: str, layer: str, event_ids: list) -> str:
        """Idempotency key for batch-level operations."""
        batch_hash = hashlib.sha256(
            "\x00".join(sorted(event_ids)).encode("utf-8")
        ).hexdigest()[:12]
        return f"p03:reconcile:{cycle_id}:{layer}:batch:{batch_hash}"
```

**Compatibility with existing keys**: The existing `IdempotencyKeyGenerator.for_truth_write()` produces `p03:write:{ulid}:{table}:{record_id}`. The new router keys use `p03:reconcile:...` prefix, so there's zero collision with old keys during migration (M9.8). Both old and new writes can coexist in the same R7 execution.

---

#### M9.5.12 Confidence Boost Strategy (Per-Layer)

REINFORCE applies a per-layer confidence boost declared in `TruthLayerSpec.confidence_boost_strategy`:

| Layer | Strategy | Formula | Source |
|-------|----------|---------|--------|
| st_epi | `"none"` | No confidence change | Episodic confidence from centroid cohesion |
| st_sem | `"additive_0.05"` | `LEAST(confidence + 0.05, 1.0)` | `SemanticLayerWriter` L430-445 |
| st_procedural | `"multiplicative_1.1"` | `LEAST(confidence * 1.1, 1.0)` | `ProceduralLayerWriter` L320-330 |
| st_social | `"multiplicative_1.1"` | `LEAST(relationship_strength * 1.1, 1.0)` | `SocialLayerWriter` L500-550 |
| st_prospective | `"coalesce"` | `COALESCE(new, existing)` | Only updates if explicitly provided |
| st_kg_dom | `"multiplicative_1.1"` | `LEAST(confidence * 1.1, 1.0)` | `KGLayerWriter` L620-655 |
| st_kg_edges | `"coalesce"` | `COALESCE(new, existing)` | Edge weight is absolute-set, not boosted |

The router passes the boost hint to R7 via `record_data["_confidence_boost"]` or `record_data["_confidence_boost_factor"]`. R7 layer writers already handle these routing keys.

---

#### M9.5.13 R7 Compatibility: How Router StagedWrites Flow Through Existing R7

M9.5 produces `StagedWrite` objects identical in structure to what the existing assemblers produce. R7 is NOT modified. The flow:

```
M9.4 decide() -> ReconciliationResult
                    |
                    v
M9.5 WriteDecisionRouter.build()
                    |
                    v
              StagedWrite (same dataclass as today)
                    |
                    v
R6 P03StagedWrites.add_write(write)   <-- routes to correct per-layer list
                    |
                    v
R7 TransactionCoordinator.execute()
                    |
                    v
R7 DecisionRouter.route() -> per-layer LayerWriter.write()
                    |
                    v
PostgreSQL (INSERT/UPDATE/ARCHIVE/TOMBSTONE)
```

**What changes**: The `StagedWrite.record_data` dict is assembled by MergeEngine (data-driven from spec) instead of by hand-coded assembler methods. The dict structure is identical -- R7 reads the same keys.

**What does NOT change**:

- `StagedWrite` dataclass (same fields)
- `WriteOperation` enum (same 4 values)
- `P03StagedWrites` container (same routing)
- R7 layer writers (same SQL)
- R7 `TransactionCoordinator` (same retry logic)
- Idempotency handling (ON CONFLICT DO NOTHING for INSERT, version check for UPDATE)

---

#### M9.5.14 Per-Layer Appendable JSON Fields (Reference)

The MergeEngine must handle these JSON fields correctly for EXTEND:

| Layer | APPENDABLE_DISTINCT Fields | APPENDABLE_ALL | APPENDABLE_CAPPED | ADDITIVE_MERGE | SHALLOW_MERGE |
|-------|---------------------------|----------------|-------------------|----------------|---------------|
| st_epi | source_events_json, participants_json, source_texts_json, narrative_thread_ids_json, entity_ids_json, centroid_metadata_json | -- | -- | -- | -- |
| st_sem | source_episodes_json, pattern_attributes_json, temporal_pattern_json, source_texts_json | -- | -- | -- | -- |
| st_procedural | source_episodes_json, source_texts_json | action_sequence_json | -- | -- | -- |
| st_social | source_episodes_json, interaction_modalities_json, typical_activities_json, source_texts_json | -- | sentiment_trajectory_json (cap=20) | emotions_json | -- |
| st_prospective | source_texts_json | -- | -- | -- | -- |
| st_kg_dom | aliases_json, source_episodes_json, source_texts_json | milestones_json | -- | -- | attributes_json |
| st_kg_edges | source_episodes_json | -- | -- | -- | properties_json |

Note: st_kg_edges also uses PG_ARRAY_CONCAT for `evidence_event_ids` and `evidence_episode_ids` (native PostgreSQL arrays, not JSON).

---

#### M9.5.15 Special Layer Merge Behaviors (Captured in TruthLayerSpec)

These layer-specific behaviors are NOT hardcoded in the router -- they are expressed as merge rules in the YAML contracts (M9.1):

| Layer | Special Behavior | How It's Expressed |
|-------|-----------------|-------------------|
| st_epi | `duration_minutes` recomputed from `(GREATEST(end) - LEAST(start)) / 60000` | DERIVED rule on `duration_minutes` column |
| st_procedural | `temporal_regularity` moving average `(existing + new) / 2` | EMA rule with alpha=0.5 |
| st_social | `avg_sentiment` EMA `old * 0.9 + new * 0.1` | EMA rule with alpha=0.1 |
| st_social | `emotional_valence_trend` tracking | TREND rule with beta=0.3 |
| st_social | `sentiment_trajectory_json` rolling window | APPENDABLE_CAPPED with cap=20 |
| st_social | `emotions_json` additive per-key merge | ADDITIVE_MERGE rule |
| st_kg_dom | `decay_factor` reset on REINFORCE | REPLACED rule (value=1.0) |
| st_kg_dom | `milestones_json` append without dedup | APPENDABLE_ALL rule |
| st_kg_edges | `edge_weight` absolute set (not increment) | REPLACED rule |
| st_kg_edges | `evidence_*` PG array concatenation | PG_ARRAY_CONCAT rule |

---

#### M9.5.16 Execution Steps (Ordered)

| Step | Action | Output | Verification |
|------|--------|--------|--------------|
| 1 | Create `k0/modules/consolidation/reconciliation/idem.py` | RouterIdempotencyKey class | `test_router.py::test_idempotency_key_format`, `test_router.py::test_idempotency_key_deterministic` |
| 2 | Create `k0/modules/consolidation/reconciliation/merge_engine.py` | MergeEngine.build_extend_data() | `test_merge_engine.py::test_appendable_distinct`, `test_merge_engine.py::test_counter`, etc. (16 merge rule tests) |
| 3 | Create `k0/modules/consolidation/reconciliation/evolve_handler.py` | EvolveHandler.build_evolve_pair() | `test_evolve_handler.py::test_evolve_produces_two_writes`, `test_evolve_handler.py::test_supersedes_id_links` |
| 4 | Create `k0/modules/consolidation/reconciliation/contradict_handler.py` | ContradictHandler.build_learning_queue_entry() | `test_router.py::test_contradict_inserts_to_learning_queue` |
| 5 | Create `k0/modules/consolidation/reconciliation/router.py` | WriteDecisionRouter.build() | `test_router.py::test_create_produces_insert`, `test_router.py::test_skip_produces_empty`, etc. |
| 6 | Create `k0/contracts/modules/reconciliation.write_router.v1.yaml` | Contract YAML | CI schema validation |
| 7 | Create `tests/.../test_router.py` | Per-action tests (30+ test cases) | pytest passes |
| 8 | Create `tests/.../test_merge_engine.py` | Per-merge-rule tests (20+ test cases) | pytest passes |
| 9 | Create `tests/.../test_evolve_handler.py` | EVOLVE tests (10+ test cases) | pytest passes |
| 10 | Create `tests/.../test_golden_writes.py` | Golden data: compare router output vs existing assembler output | Action agreement >= 98% on existing test corpus |
| 11 | Verify: old TruthWriteAssembler still works | No edits to existing files | Existing tests pass unchanged |
| 12 | Verify: router StagedWrites accepted by R7 | Feed router output to R7 in integration test | R7 executes all writes without error |

---

#### M9.5.17 Key Design Decisions

| # | Decision | Rationale | Alternative Considered | Why Rejected |
|---|----------|-----------|----------------------|--------------|
| KD1 | MergeEngine reads rules from TruthLayerSpec, not hardcoded | Adding a layer or changing a merge rule requires only YAML edit, not code change | Keep per-layer assembler methods | 12+ methods duplicating merge logic; 7 YAML changes when adding a field |
| KD2 | Router produces StagedWrite (same dataclass), not a new type | R7 is NOT modified; all existing infrastructure reused | New WriteInstruction type | Migration cost: R7, TransactionCoordinator, LayerWriters all need updates |
| KD3 | EVOLVE is exactly 2 writes (UPDATE + INSERT), not a single compound operation | Matches existing SemanticLayerWriter._evolve() pattern; R7 already handles ordered writes | Single EVOLVE WriteOperation value | R7 would need new SQL path; existing ARCHIVE+INSERT pipeline works |
| KD4 | CONTRADICT inserts to st_learning_queue, does NOT modify truth | User/K1 contradictions need human review (P06); auto-modifying truth on contradiction is dangerous | Auto-archive contradicted record | False contradiction from K1 would destroy valid truth records |
| KD5 | Confidence boost expressed as strategy string, not inline formula | Layer writers already have the SQL; router just signals which strategy to use | Router computes new confidence value | Router cannot read current DB value; R7 writers use `LEAST(conf + X, 1.0)` in SQL |
| KD6 | Idempotency key uses `p03:reconcile:` prefix (not `p03:write:`) | Zero collision with old assembler keys during migration; both can coexist | Reuse existing `p03:write:` prefix | Old and new writes for same record in same cycle would collide |
| KD7 | MergeEngine does NOT execute SQL | Merge rules describe WHAT to do; R7 layer writers describe HOW in SQL. Clean separation | MergeEngine generates SQL fragments | Couples router to PostgreSQL dialect; blocks future DB migration |
| KD8 | `_action` routing key in record_data eliminated | Action is explicit on `StagedWrite.operation` enum; `_action` was a workaround for shared update path | Keep `_action` for backward compat | Magic strings in data dicts are fragile; explicit enum is type-safe |
| KD9 | Router is pure function (static build method) | No instance state, no DB, trivially testable | Instance with config | No config needed -- all data comes from TruthLayerSpec |

---

#### M9.5.18 Validation Criteria (Exit Gates)

| # | Criterion | How to Verify |
|---|----------|---------------|
| V1 | CREATE produces StagedWrite with `operation=INSERT`, `version=1` | `test_router.py::test_create_insert` |
| V2 | REINFORCE produces StagedWrite with `operation=UPDATE`, `observation_count=1` | `test_router.py::test_reinforce_update` |
| V3 | EXTEND applies APPENDABLE_DISTINCT correctly | `test_merge_engine.py::test_appendable_distinct_dedup` |
| V4 | EXTEND applies TEMPORAL_MIN correctly | `test_merge_engine.py::test_temporal_min` |
| V5 | EXTEND applies TEMPORAL_MAX correctly | `test_merge_engine.py::test_temporal_max` |
| V6 | EXTEND applies COUNTER correctly | `test_merge_engine.py::test_counter_increment` |
| V7 | EXTEND applies EMA correctly | `test_merge_engine.py::test_ema_with_alpha` |
| V8 | EXTEND applies APPENDABLE_CAPPED with correct cap | `test_merge_engine.py::test_appendable_capped_limit` |
| V9 | EXTEND applies SHALLOW_MERGE correctly | `test_merge_engine.py::test_shallow_merge` |
| V10 | EXTEND skips IMMUTABLE columns | `test_merge_engine.py::test_immutable_skipped` |
| V11 | EXTEND skips DERIVED columns | `test_merge_engine.py::test_derived_skipped` |
| V12 | EVOLVE produces exactly 2 StagedWrites | `test_evolve_handler.py::test_evolve_count` |
| V13 | EVOLVE Write 1: old record `is_canonical=FALSE`, `archival_status=SUPERSEDED` | `test_evolve_handler.py::test_evolve_archive_old` |
| V14 | EVOLVE Write 2: new record `supersedes_id=old.PK`, `is_canonical=TRUE` | `test_evolve_handler.py::test_evolve_insert_new` |
| V15 | CONTRADICT inserts to `st_learning_queue`, NOT to truth layer | `test_router.py::test_contradict_layer_is_learning_queue` |
| V16 | PRUNE produces ARCHIVE with `archival_status=ARCHIVED` | `test_router.py::test_prune_archive` |
| V17 | PRUNE with TOMBSTONE produces TOMBSTONE operation | `test_router.py::test_prune_tombstone` |
| V18 | SKIP produces empty list | `test_router.py::test_skip_no_writes` |
| V19 | Idempotency keys are deterministic (same inputs -> same key) | `test_router.py::test_idempotency_deterministic` |
| V20 | Idempotency keys use `p03:reconcile:` prefix | `test_router.py::test_idempotency_prefix` |
| V21 | Router output accepted by R7 without modification | Integration test: feed router StagedWrites to R7 mock |
| V22 | Golden writes match existing assembler output for st_epi | `test_golden_writes.py::test_epi_golden` |
| V23 | Golden writes match existing assembler output for st_sem | `test_golden_writes.py::test_sem_golden` |
| V24 | All 16 merge rules have at least one test | `test_merge_engine.py` has 16+ test methods |
| V25 | Existing TruthWriteAssembler tests still pass | `pytest tests/k0/modules/consolidation/staging/` -- no modifications |
| V26 | Per-layer confidence boost strategy applied correctly | `test_router.py::test_reinforce_additive_boost`, `test_router.py::test_reinforce_multiplicative_boost` |

---

#### M9.5.19 What M9.5 Does NOT Do

| Out of Scope | Why | When |
|-------------|-----|------|
| Delete old TruthWriteAssembler | Still in use by R6 until M9.8 migration | M9.8 |
| Delete old KGWriteAssembler | Still in use until M9.8 | M9.8 |
| Modify R7 layer writers | Router produces StagedWrites compatible with existing writers | Never (unless merge rules change) |
| Modify R6 coordinator | R6 still uses old assemblers until M9.8 | M9.8 |
| Generate actual SQL | Router builds record_data dicts; R7 writers generate SQL | Never (separation of concerns) |
| Handle st_vec writes | Embedding writes are handled by TextVectorCoordinator (M9.6 hooks) | M9.6 |
| Handle st_hipp_events status updates | StagedEventUpdate is R6-specific, not a truth write | Stays in R6 |
| Implement batch write deduplication (same record appears twice) | KGWriteAssembler._merge_edge_writes handles this today | M9.8 (edge merging moves to router) |
| Handle outbox events (StagedOutboxEvent) | Separate from truth writes; R8 handles bus events | Stays in R6/R8 |
| Make merge rules hot-reloadable | YAML loaded at registry init; restart required | Future if needed |

---

### M9.6 -- Structured Summaries & Embedding Regeneration (Absorbed M7)

Build the post-reconciliation hook system that generates content after R7 writes.

**Status**: READY TO IMPLEMENT
**Estimated Scope**: 1 hook runner + 1 summary builder + 1 centroid recomputer + 1 embedding regenerator + 1 contract YAML + tests
**Depends on**: M9.1 (TruthLayerSpec declares which layers need summaries/centroids), M9.4 (ReconciliationResult.hooks_required), M9.5 (StagedWrites committed by R7)
**Absorbs**: M7 7.3 (Rich Structured Episode Summaries), M7 7.4 (Embedding Regeneration on EXTEND/EVOLVE)
**Reuses**: `TextVectorCoordinator` (GAP-001), `CentroidCalculator` (R2 algorithm), `EmbeddingGenerator` (UltraBERT adapter)

---

#### M9.6.1 Objective

Create the `PostReconciliationHookRunner` -- a post-R7 coordinator that reads `ReconciliationResult.hooks_required` and executes two content-generation hooks:

1. **`regenerate_summary`**: Rebuild the structured summary JSON and `embedding_text` for a truth record whose content changed (CREATE, EXTEND, EVOLVE)
2. **`recompute_centroid`**: Recompute the mean centroid embedding for an episodic or embedding-bearing truth record (CREATE, REINFORCE, EXTEND, EVOLVE)

These hooks run AFTER R7 commits the StagedWrites (truth records exist in DB with the new data but stale or null embedding/summary columns), and BEFORE R8 bus events are published.

The hook runner must:

1. Accept a list of `(ReconciliationResult, StagedWrite)` pairs from R6
2. Filter to those with non-empty `hooks_required`
3. Execute hooks in order: `regenerate_summary` first (produces new `embedding_text`), then `recompute_centroid` (may use the new text for inline embedding)
4. Batch DB writes for efficiency (one UPDATE per record, not per hook)
5. Be idempotent (re-running hooks on the same record produces the same result)
6. NOT block the critical write path -- hook failures are logged but do NOT roll back R7 writes

---

#### M9.6.2 What M9.6 Replaces and Extends

| Existing Component | File | Current Behavior | M9.6 Change |
|---|---|---|---|
| `TextVectorCoordinator.process()` | `text_vector_coordinator.py` | Called by R7 layer writers on INSERT only | REUSED as-is; M9.6 calls it again on EXTEND/EVOLVE for regen |
| `EpisodicLayerWriter._insert()` | `episodic.py` L247-310 | Generates embedding_text + embedding_vector on INSERT | No change; M9.6 handles post-write regen separately |
| `CentroidCalculator.compute()` | `centroid_calculator.py` L497-537 | Called by R2 during HDBSCAN clustering; result stored in-memory only | REUSED; M9.6 calls it for post-write centroid recomputation |
| `EpisodeCandidate.centroid_embedding` | `phase_outputs.py` L115 | Computed by R2 but never persisted to st_vec | M9.6 writes the centroid to inline `embedding_vector` on st_epi |
| `episode_summary` on st_epi | `0027_st_epi.py` L53 | `cluster.summary or cluster.title or "Untitled episode"` -- plain text | M9.6 replaces with structured JSON (schema_version, affect_trajectory, etc.) |
| `embedding_text` on all layers | GAP-001 `0061-0066` migrations | Generated once on INSERT, never updated | M9.6 regenerates on EXTEND/EVOLVE to reflect new merged content |
| No post-write hook system | -- | Hooks exist only in spec (M9.4 `hooks_required`), no runner | M9.6 builds the full runner |

---

#### M9.6.3 Deliverables

| # | Deliverable | File Path | New/Edit | Description |
|---|-----------|-----------|----------|-------------|
| D1 | PostReconciliationHookRunner | `k0/modules/consolidation/reconciliation/hooks/runner.py` | NEW | Coordinator: iterates results, dispatches to hook handlers, batches DB writes, ~200 lines |
| D2 | SummaryRegenerator | `k0/modules/consolidation/reconciliation/hooks/summary_regen.py` | NEW | Rebuilds `episode_summary` (structured JSON) + `embedding_text` for a truth record, ~250 lines |
| D3 | CentroidRecomputer | `k0/modules/consolidation/reconciliation/hooks/centroid_recompute.py` | NEW | Recomputes centroid embedding and writes `embedding_vector` inline, ~180 lines |
| D4 | StructuredEpisodeSummary dataclass | `k0/modules/consolidation/reconciliation/hooks/episode_summary.py` | NEW | Schema for the structured JSON stored in `episode_summary` column, ~80 lines |
| D5 | HookResult dataclass | `k0/modules/consolidation/reconciliation/hooks/result.py` | NEW | Per-record hook execution result (success/skip/failure + timing), ~30 lines |
| D6 | YAML contract | `k0/contracts/modules/reconciliation.post_hooks.v1.yaml` | NEW | Input/output schemas, hook types, per-layer applicability |
| D7 | Unit tests: runner | `tests/k0/modules/consolidation/reconciliation/hooks/test_runner.py` | NEW | Per-action hook dispatch, ordering, error isolation (20+ tests) |
| D8 | Unit tests: summary | `tests/k0/modules/consolidation/reconciliation/hooks/test_summary_regen.py` | NEW | Structured summary format, field population, EXTEND vs CREATE (15+ tests) |
| D9 | Unit tests: centroid | `tests/k0/modules/consolidation/reconciliation/hooks/test_centroid_recompute.py` | NEW | Centroid recalc, weighting, EVOLVE fresh centroid (15+ tests) |
| D10 | Integration test | `tests/k0/modules/consolidation/reconciliation/hooks/test_hooks_integration.py` | NEW | Full flow: R7 write -> hook runner -> verify DB columns updated |

---

#### M9.6.4 File Location Map (Complete)

```
NEW FILES:

  k0/modules/consolidation/reconciliation/hooks/
      __init__.py                        # Hook type constants
      runner.py                          # D1: PostReconciliationHookRunner
      summary_regen.py                   # D2: SummaryRegenerator
      centroid_recompute.py              # D3: CentroidRecomputer
      episode_summary.py                 # D4: StructuredEpisodeSummary dataclass
      result.py                          # D5: HookResult dataclass

  k0/contracts/modules/
      reconciliation.post_hooks.v1.yaml  # D6: Contract YAML

  tests/k0/modules/consolidation/reconciliation/hooks/
      __init__.py
      test_runner.py                     # D7: Runner dispatch tests
      test_summary_regen.py              # D8: Summary generation tests
      test_centroid_recompute.py         # D9: Centroid recomputation tests
      test_hooks_integration.py          # D10: End-to-end integration tests


EXISTING FILES REUSED (NOT MODIFIED):

  k0/modules/consolidation/truth_writer/text_vector_coordinator.py   # TextVectorCoordinator.process() -- called by SummaryRegenerator
  k0/modules/consolidation/truth_writer/embedding_generator.py       # EmbeddingGenerator -- UltraBERT embedding
  k0/modules/consolidation/truth_writer/source_text_fetcher.py       # SourceTextFetcher -- fetches texts from st_hipp_events
  k0/modules/consolidation/algorithms/centroid_calculator.py         # CentroidCalculator.compute() -- called by CentroidRecomputer
  k0/modules/consolidation/algorithms/text_generators/               # 6 layer-specific text generators (episodic, semantic, etc.)
  k0/modules/consolidation/algorithms/embedding_text_generator.py    # Base text generator class
  k0/runtime/ultrabert_adapter.py                                    # UltraBERT v2.1.0, 768-dim, ~30ms per call
  k0/modules/consolidation/algorithms/observation_context.py         # ObservationContext dataclass -- input for structured summaries


EXISTING FILES NOT MODIFIED:

  k0/modules/consolidation/truth_writer/layers/episodic.py           # INSERT path unchanged; hooks handle post-write regen
  k0/modules/consolidation/truth_writer/layers/semantic.py           # Same
  k0/pipelines/p03/phases/r7_truth_writer.py                         # R7 phase unchanged; hooks run AFTER R7
  k0/db/alembic/versions/0027_st_epi.py                              # episode_summary column already TEXT -- reused for structured JSON
```

---

#### M9.6.5 Hook Assignment Matrix (From M9.4)

| ReconciliationAction | hooks_required | regenerate_summary | recompute_centroid | archive_superseded |
|---------------------|----------------|-------------------|-------------------|-------------------|
| CREATE | `["recompute_centroid", "regenerate_summary"]` | YES | YES | -- |
| REINFORCE | `["recompute_centroid"]` | -- | YES | -- |
| EXTEND | `["recompute_centroid", "regenerate_summary"]` | YES | YES | -- |
| EVOLVE | `["archive_superseded", "recompute_centroid", "regenerate_summary"]` | YES (new record) | YES (new record) | Handled by M9.5 EvolveHandler |
| CONTRADICT | `[]` | -- | -- | -- |
| SKIP | `[]` | -- | -- | -- |
| PRUNE | `[]` | -- | -- | -- |

**Note**: `archive_superseded` is handled IN the M9.5 EVOLVE StagedWrite pair (Write 1: UPDATE old record to SUPERSEDED). It is NOT a post-R7 hook. Only `regenerate_summary` and `recompute_centroid` are true post-write hooks executed by M9.6.

---

#### M9.6.6 PostReconciliationHookRunner Class (Target)

```python
# k0/modules/consolidation/reconciliation/hooks/runner.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging
import time

from k0.modules.consolidation.reconciliation.hooks.summary_regen import SummaryRegenerator
from k0.modules.consolidation.reconciliation.hooks.centroid_recompute import CentroidRecomputer
from k0.modules.consolidation.reconciliation.hooks.result import HookResult
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.modules.consolidation.truth_layer_registry import TruthLayerSpec
from k0.pipelines.p03.staged_writes import StagedWrite

logger = logging.getLogger(__name__)


@dataclass
class HookBatchResult:
    """Result of running hooks for an entire batch."""
    total: int                              # Total records processed
    summary_regen_count: int                # Records that had summary regenerated
    centroid_recompute_count: int           # Records that had centroid recomputed
    skipped: int                            # Records with empty hooks_required
    failed: int                             # Records where hooks errored
    total_time_ms: float                    # Wall-clock time for all hooks
    per_record: List[HookResult]            # Per-record results for observability


class PostReconciliationHookRunner:
    """
    Post-R7 coordinator that executes content-generation hooks.

    Runs AFTER R7 commits StagedWrites, BEFORE R8 bus events.
    Hook failures are logged but do NOT roll back R7 writes.

    Execution order per record:
        1. regenerate_summary (produces new embedding_text)
        2. recompute_centroid (uses embedding_text for inline vector)
        3. Single batched UPDATE to write all hook outputs

    Usage:
        runner = PostReconciliationHookRunner(conn, registry)
        batch_result = await runner.run(hook_inputs)
    """

    def __init__(
        self,
        conn,  # AsyncDBConnection
        registry,  # TruthLayerRegistry
        summary_regen: Optional[SummaryRegenerator] = None,
        centroid_recomputer: Optional[CentroidRecomputer] = None,
    ):
        self._conn = conn
        self._registry = registry
        self._summary = summary_regen or SummaryRegenerator(conn)
        self._centroid = centroid_recomputer or CentroidRecomputer()

    async def run(
        self,
        hook_inputs: List[Tuple[ReconciliationResult, StagedWrite]],
    ) -> HookBatchResult:
        """
        Execute hooks for a batch of reconciliation results.

        Args:
            hook_inputs: List of (result, staged_write) pairs from R6.
                         Only pairs with non-empty hooks_required are processed.

        Returns:
            HookBatchResult with per-record and aggregate results.
        """
        start = time.monotonic()
        per_record = []
        summary_count = 0
        centroid_count = 0
        skipped = 0
        failed = 0

        for result, write in hook_inputs:
            if not result.hooks_required:
                skipped += 1
                continue

            spec = self._registry.get(result.layer)
            record_id = result.match_id or write.record_id

            try:
                hook_result = await self._run_hooks_for_record(
                    result, write, spec, record_id
                )
                per_record.append(hook_result)
                if hook_result.summary_regenerated:
                    summary_count += 1
                if hook_result.centroid_recomputed:
                    centroid_count += 1
            except Exception as exc:
                logger.error(
                    "Hook execution failed for %s/%s: %s",
                    result.layer, record_id, exc,
                )
                failed += 1
                per_record.append(HookResult.failed(result.layer, record_id, str(exc)))

        elapsed = (time.monotonic() - start) * 1000
        return HookBatchResult(
            total=len(hook_inputs),
            summary_regen_count=summary_count,
            centroid_recompute_count=centroid_count,
            skipped=skipped,
            failed=failed,
            total_time_ms=elapsed,
            per_record=per_record,
        )

    async def _run_hooks_for_record(
        self,
        result: ReconciliationResult,
        write: StagedWrite,
        spec: TruthLayerSpec,
        record_id: str,
    ) -> HookResult:
        """Execute hooks for a single record in correct order."""
        new_embedding_text = None
        new_summary_json = None
        new_embedding_vector = None

        # Hook 1: regenerate_summary (must run first -- produces new embedding_text)
        if "regenerate_summary" in result.hooks_required:
            regen_result = await self._summary.regenerate(
                layer=result.layer,
                record_id=record_id,
                spec=spec,
                source_event_ids=write.source_event_ids,
                record_data=write.record_data,
            )
            new_embedding_text = regen_result.embedding_text
            new_summary_json = regen_result.summary_json

        # Hook 2: recompute_centroid (uses new embedding_text if available)
        if "recompute_centroid" in result.hooks_required:
            centroid_result = await self._centroid.recompute(
                layer=result.layer,
                record_id=record_id,
                spec=spec,
                source_event_ids=write.source_event_ids,
                embedding_text=new_embedding_text,
            )
            new_embedding_vector = centroid_result.embedding_vector

        # Batched UPDATE: write all hook outputs in one statement
        await self._write_hook_outputs(
            layer=result.layer,
            record_id=record_id,
            spec=spec,
            summary_json=new_summary_json,
            embedding_text=new_embedding_text,
            embedding_vector=new_embedding_vector,
        )

        return HookResult(
            layer=result.layer,
            record_id=record_id,
            summary_regenerated=new_summary_json is not None,
            centroid_recomputed=new_embedding_vector is not None,
        )
```

**Key design decisions**:

- Hooks run in order: summary first (generates `embedding_text`), centroid second (may embed that text)
- One batched UPDATE per record (not per hook) to minimize DB round trips
- Failures are logged and recorded in `HookResult`, never propagated to R7
- Runner receives `(ReconciliationResult, StagedWrite)` pairs -- the result has `hooks_required`, the write has `source_event_ids` and `record_data`

---

#### M9.6.7 SummaryRegenerator: Structured Summaries (Complete Specification)

**Two outputs per regeneration**:

1. `embedding_text` -- updated template text for UltraBERT re-embedding (via existing `TextVectorCoordinator`)
2. `summary_json` -- rich structured JSON for the `episode_summary` column (episodic layer only; other layers use `embedding_text` as their descriptive content)

```python
# k0/modules/consolidation/reconciliation/hooks/summary_regen.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from k0.modules.consolidation.truth_writer.text_vector_coordinator import TextVectorCoordinator
from k0.modules.consolidation.reconciliation.hooks.episode_summary import (
    StructuredEpisodeSummary,
    build_structured_summary,
)

@dataclass
class SummaryRegenResult:
    embedding_text: Optional[str]     # New template text for embedding
    summary_json: Optional[str]       # Structured JSON (episodic only)
    embedding_model: Optional[str]    # Model version


class SummaryRegenerator:
    """
    Regenerates summary text and embedding_text for truth records.

    For episodic layer: builds StructuredEpisodeSummary JSON + embedding_text
    For all other layers: rebuilds embedding_text using layer-specific template generator

    No LLM involved -- all generation is template-based + extractive (TextRank).
    """

    def __init__(self, conn):
        self._conn = conn
        self._coordinator = TextVectorCoordinator()

    async def regenerate(
        self,
        layer: str,
        record_id: str,
        spec,  # TruthLayerSpec
        source_event_ids: List[str],
        record_data: Dict[str, Any],
    ) -> SummaryRegenResult:
        """
        Regenerate summary content for a truth record.

        For st_epi:
            1. Fetch source events from st_hipp_events
            2. Build StructuredEpisodeSummary from ObservationContext per event
            3. Regenerate embedding_text via EpisodicTextGenerator
            4. Return both structured JSON + new embedding_text

        For other layers:
            1. Call TextVectorCoordinator.process() with updated record_data
            2. Return new embedding_text (no structured summary)
        """
        if layer == "st_epi":
            return await self._regenerate_episodic(
                record_id, source_event_ids, record_data
            )
        else:
            return await self._regenerate_generic(
                layer, source_event_ids, record_data
            )

    async def _regenerate_episodic(
        self, record_id, source_event_ids, record_data
    ) -> SummaryRegenResult:
        # 1. Fetch full event data for structured summary
        events = await self._fetch_events(source_event_ids)

        # 2. Build structured summary from events
        structured = build_structured_summary(events, record_data)
        summary_json = structured.to_json()

        # 3. Regenerate embedding_text via coordinator
        tv_result = await self._coordinator.process(
            layer="st_epi",
            record_data=record_data,
            source_event_ids=source_event_ids,
            conn=self._conn,
        )

        return SummaryRegenResult(
            embedding_text=tv_result.embedding_text,
            summary_json=summary_json,
            embedding_model=tv_result.embedding_model,
        )

    async def _regenerate_generic(
        self, layer, source_event_ids, record_data
    ) -> SummaryRegenResult:
        # Use existing TextVectorCoordinator for non-episodic layers
        tv_result = await self._coordinator.process(
            layer=layer,
            record_data=record_data,
            source_event_ids=source_event_ids,
            conn=self._conn,
        )

        return SummaryRegenResult(
            embedding_text=tv_result.embedding_text,
            summary_json=None,  # Non-episodic layers have no structured summary
            embedding_model=tv_result.embedding_model,
        )
```

---

#### M9.6.8 StructuredEpisodeSummary: Rich JSON Schema (Absorbed M7 7.3)

Today `episode_summary` is plain text: `cluster.summary or cluster.title or "Untitled episode"`. M9.6 replaces it with structured JSON.

```python
# k0/modules/consolidation/reconciliation/hooks/episode_summary.py

from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"


@dataclass
class EventRecord:
    """Per-event record within the structured summary."""
    event_id: str
    timestamp_ms: int
    text_preview: str                      # First 200 chars of event text
    sentiment_label: Optional[str]         # positive/neutral/negative
    dominant_emotion: Optional[str]
    intent: Optional[str]                  # UltraBERT 8-type
    salience_band: Optional[str]           # HIGH/MED/LOW
    ingress_channel: Optional[str]         # voice/chat/api


@dataclass
class StructuredEpisodeSummary:
    """
    Rich structured JSON for episode_summary column.

    Replaces plain text "Untitled episode" with actionable structure.
    Generated from ObservationContext fields on member events.
    No LLM -- all fields derived from existing event metadata.

    Stored as TEXT (JSON-serialized) in st_epi.episode_summary.
    Reuses existing column -- no schema migration needed.
    """
    schema_version: str = SCHEMA_VERSION
    title: str = ""                        # Best-effort title from events
    event_count: int = 0
    dominant_thread_id: Optional[str] = None
    thread_distribution: Dict[str, int] = field(default_factory=dict)
    goal_distribution: Dict[str, int] = field(default_factory=dict)
    temporal_narrative: str = ""           # "Morning episode (9:15-10:30), weekday"
    participants: List[str] = field(default_factory=list)
    affect_trajectory: List[Dict[str, Any]] = field(default_factory=list)
    # [{timestamp_ms, valence, arousal, emotion}]
    dominant_sentiment: Optional[str] = None
    dominant_emotion: Optional[str] = None
    location_context: Optional[str] = None  # "Home, kitchen"
    activity_type: Optional[str] = None     # UltraBERT classification
    event_records: List[EventRecord] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, raw: str) -> "StructuredEpisodeSummary":
        data = json.loads(raw)
        events = [EventRecord(**e) for e in data.pop("event_records", [])]
        return cls(**data, event_records=events)


def build_structured_summary(
    events: List[Dict[str, Any]],
    record_data: Dict[str, Any],
) -> StructuredEpisodeSummary:
    """
    Build StructuredEpisodeSummary from event rows + episode record_data.

    Args:
        events: List of st_hipp_events rows (dicts) for member events
        record_data: Episode record_data from StagedWrite

    Returns:
        StructuredEpisodeSummary with all derivable fields populated
    """
    event_records = []
    affect_trajectory = []
    thread_counts = {}
    goal_counts = {}
    sentiments = []
    emotions = []
    participants_set = set()

    for evt in events:
        # Build per-event record
        event_records.append(EventRecord(
            event_id=evt.get("event_id", ""),
            timestamp_ms=evt.get("conversation_anchor_ms") or evt.get("event_time_utc", 0),
            text_preview=(evt.get("user_message") or "")[:200],
            sentiment_label=evt.get("sentiment_label"),
            dominant_emotion=_first_emotion(evt.get("emotions_json")),
            intent=evt.get("intent_ultrabert"),
            salience_band=evt.get("salience_band"),
            ingress_channel=evt.get("ingress_channel"),
        ))

        # Affect trajectory
        if evt.get("affect_valence") is not None:
            affect_trajectory.append({
                "timestamp_ms": evt.get("conversation_anchor_ms") or evt.get("event_time_utc", 0),
                "valence": evt.get("affect_valence"),
                "arousal": evt.get("affect_arousal"),
                "emotion": _first_emotion(evt.get("emotions_json")),
            })

        # Thread distribution
        thread_id = evt.get("narrative_thread_id")
        if thread_id:
            thread_counts[thread_id] = thread_counts.get(thread_id, 0) + 1

        # Goal distribution
        goal = evt.get("intent_ultrabert")
        if goal:
            goal_counts[goal] = goal_counts.get(goal, 0) + 1

        # Sentiment/emotion aggregation
        if evt.get("sentiment_label"):
            sentiments.append(evt["sentiment_label"])
        if _first_emotion(evt.get("emotions_json")):
            emotions.append(_first_emotion(evt["emotions_json"]))

        # Participants
        _collect_participants(evt, participants_set)

    # Sort events chronologically
    event_records.sort(key=lambda e: e.timestamp_ms)
    affect_trajectory.sort(key=lambda a: a["timestamp_ms"])

    # Build temporal narrative
    temporal_narrative = _build_temporal_narrative(event_records, record_data)

    # Dominant thread
    dominant_thread = max(thread_counts, key=thread_counts.get) if thread_counts else None

    return StructuredEpisodeSummary(
        title=record_data.get("episode_summary") or record_data.get("title", ""),
        event_count=len(events),
        dominant_thread_id=dominant_thread,
        thread_distribution=thread_counts,
        goal_distribution=goal_counts,
        temporal_narrative=temporal_narrative,
        participants=sorted(participants_set),
        affect_trajectory=affect_trajectory,
        dominant_sentiment=_mode(sentiments),
        dominant_emotion=_mode(emotions),
        location_context=record_data.get("primary_location"),
        activity_type=record_data.get("activity_type_ultrabert"),
        event_records=event_records,
    )
```

**Key decisions**:

- **No LLM** -- all fields derived from existing event metadata (ObservationContext fields, UltraBERT classifications, affect scores)
- **Reuses `episode_summary` TEXT column** -- stores JSON string, no schema migration needed
- **`schema_version` field** allows future format evolution without breaking readers
- **HTML rendering not stored** -- computed on demand by K1/frontend
- **Non-episodic layers** do NOT get structured summaries -- they use `embedding_text` from their layer-specific template generators

---

#### M9.6.9 CentroidRecomputer: Embedding Regeneration (Absorbed M7 7.4)

```python
# k0/modules/consolidation/reconciliation/hooks/centroid_recompute.py

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
import logging

from k0.modules.consolidation.algorithms.centroid_calculator import CentroidCalculator
from k0.modules.consolidation.truth_writer.embedding_generator import EmbeddingGenerator

logger = logging.getLogger(__name__)


@dataclass
class CentroidResult:
    embedding_vector: Optional[bytes]     # 768-dim float32 as bytes (3072 bytes)
    embedding_model: Optional[str]
    centroid_variance: Optional[float]    # Cluster cohesion metric
    strategy_used: str                    # "hybrid", "recency_exp", etc.
    member_count: int                     # Number of events contributing


class CentroidRecomputer:
    """
    Recomputes centroid embedding for truth records after R7 writes.

    Two paths depending on layer type:

    1. EPISODIC (st_epi): Weighted mean centroid from member event embeddings
       - Uses CentroidCalculator.compute() with HYBRID weighting
       - Writes result to st_epi.embedding_vector (inline, GAP-001)

    2. NON-EPISODIC (st_sem, st_procedural, etc.): Re-embed the embedding_text
       - Uses EmbeddingGenerator (UltraBERT) on the updated embedding_text
       - Writes result to <layer>.embedding_vector (inline, GAP-001)

    REINFORCE behavior:
       - Episodic: Recompute centroid (new event changes weighted mean)
       - Non-episodic: Only recompute if embedding_text changed (unlikely for REINFORCE)

    EVOLVE behavior:
       - Fresh centroid for the NEW canonical record (no inheritance from superseded)
       - The superseded record keeps its old embedding (historical accuracy)
    """

    def __init__(
        self,
        centroid_calc: Optional[CentroidCalculator] = None,
        embedding_gen: Optional[EmbeddingGenerator] = None,
    ):
        self._centroid_calc = centroid_calc or CentroidCalculator()
        self._embedding_gen = embedding_gen or EmbeddingGenerator()

    async def recompute(
        self,
        layer: str,
        record_id: str,
        spec,  # TruthLayerSpec
        source_event_ids: List[str],
        embedding_text: Optional[str] = None,
    ) -> CentroidResult:
        """
        Recompute embedding for a truth record.

        For st_epi: weighted mean of member event embeddings
        For others: re-embed the embedding_text via UltraBERT
        """
        if layer == "st_epi":
            return await self._recompute_episodic(source_event_ids)
        else:
            return await self._recompute_text_based(embedding_text)

    async def _recompute_episodic(
        self, source_event_ids: List[str]
    ) -> CentroidResult:
        """
        Recompute weighted mean centroid from member event embeddings.

        Steps:
            1. Load event embeddings from st_hipp_events.embedding_768
            2. Load event metadata (importance_score, timestamp) for weighting
            3. Call CentroidCalculator.compute() with HYBRID strategy
            4. Return centroid as bytes for inline storage
        """
        # Fetch event data with embeddings (reuses R2 pattern)
        # NOTE: Actual DB fetch delegated to caller or injected fetcher
        # For now, the runner provides pre-fetched event states

        # CentroidCalculator.compute() returns CentroidResult with:
        #   .centroid (ndarray 768-dim, L2-normalized)
        #   .variance (cluster cohesion)
        #   .member_count

        # This is a placeholder showing the expected flow:
        # centroid_result = self._centroid_calc.compute(events, strategy="hybrid")
        # vector_bytes = _ndarray_to_bytes(centroid_result.centroid)
        # return CentroidResult(
        #     embedding_vector=vector_bytes,
        #     embedding_model="ultrabert-v2.1.0",
        #     centroid_variance=centroid_result.variance,
        #     strategy_used="hybrid",
        #     member_count=centroid_result.member_count,
        # )
        raise NotImplementedError("Episodic centroid recompute -- full implementation in M9.6")

    async def _recompute_text_based(
        self, embedding_text: Optional[str]
    ) -> CentroidResult:
        """
        Re-embed the embedding_text via UltraBERT for non-episodic layers.

        This handles st_sem, st_procedural, st_social, st_prospective, st_kg_dom.
        Their embedding_vector is derived from the template-generated embedding_text,
        NOT from a centroid of member embeddings.
        """
        if not embedding_text:
            return CentroidResult(
                embedding_vector=None, embedding_model=None,
                centroid_variance=None, strategy_used="text_embed", member_count=0,
            )

        embedding = await self._embedding_gen.generate(embedding_text)
        return CentroidResult(
            embedding_vector=embedding.vector_bytes if embedding else None,
            embedding_model=embedding.model_id if embedding else None,
            centroid_variance=None,  # Not applicable for text-based
            strategy_used="text_embed",
            member_count=1,
        )
```

---

#### M9.6.10 Per-Action Centroid Behavior (Complete)

| Action | Episodic (st_epi) | Non-Episodic (st_sem, etc.) |
|--------|-------------------|----------------------------|
| CREATE | Compute centroid from initial member events (HYBRID weighting) | Embed the initial `embedding_text` via UltraBERT |
| REINFORCE | Recompute centroid with new event added to member set (recency weights shift) | Skip -- REINFORCE does not change `embedding_text` content |
| EXTEND | Recompute centroid from ALL member events (old + new, HYBRID weighting) | Re-embed the updated `embedding_text` (reflects merged content) |
| EVOLVE | Fresh centroid for NEW record only (no inheritance from superseded) | Fresh embedding for NEW record from its `embedding_text` |
| CONTRADICT | No hook | No hook |
| SKIP | No hook | No hook |
| PRUNE | No hook | No hook |

**REINFORCE special case for non-episodic layers**: The M9.4 hook assignment includes `recompute_centroid` for REINFORCE, but non-episodic REINFORCE only bumps `observation_count` and `last_observed_at` -- the `embedding_text` does NOT change. The CentroidRecomputer detects this (no new `embedding_text` provided by SummaryRegenerator) and skips re-embedding. This avoids wasteful UltraBERT calls (~30ms each) on pure observation bumps.

**REINFORCE for episodic**: The centroid DOES change because the member set grows by 1 event. Adding a new event shifts the recency-weighted mean. The CentroidCalculator recomputes from the full member set.

---

#### M9.6.11 Dual Embedding System: st_vec vs Inline (GAP-001)

K0 has two coexisting embedding systems. M9.6 operates on the **inline system only**:

| System | Columns | Where | Written By | M9.6 Impact |
|--------|---------|-------|-----------|-------------|
| **st_vec** (legacy) | `embedding_id` FK | st_epi, st_sem, st_kg_dom | P02 (per-event) | NOT touched by M9.6 |
| **Inline** (GAP-001) | `embedding_text`, `embedding_vector`, `embedding_model`, `source_texts_json` | st_epi, st_sem, st_procedural, st_social, st_prospective, st_kg_dom | R7 layer writers on INSERT; **M9.6 on EXTEND/EVOLVE/REINFORCE** | M9.6 UPDATE target |

**Why inline, not st_vec**: The st_vec table has an `event_id` FK constraint to st_hipp_events. Episode centroids are NOT events -- they have no event_id. Storing centroids in st_vec would require a schema change (relaxing the FK or adding synthetic event_ids). The inline system (`embedding_vector` directly on each truth table) has no FK constraint and already stores 768-dim vectors as BYTEA. M9.6 writes to the inline columns.

**st_vec.embedding_id on st_epi**: This column currently points to the first member event's st_vec record (fallback in TruthWriteAssembler). M9.6 does NOT modify this column. The inline `embedding_vector` is the authoritative centroid; `embedding_id` remains a legacy reference. Future cleanup (post-M9.8) may deprecate `embedding_id` on st_epi.

---

#### M9.6.12 Where Hooks Execute in the P03 Pipeline

```
R2/R3/R4 -> M9.4 decide() -> ReconciliationResult [with hooks_required]
                |
                v
             M9.5 WriteDecisionRouter.build() -> List[StagedWrite]
                |
                v
             R6 collects StagedWrites + hook_inputs
                |
                v
             R7 TransactionCoordinator.execute()  <- WRITES COMMITTED
                |
                v
          +-----+-----+
          |           |
    [M9.6 hooks]    [R8 bus events]
          |
          v
    PostReconciliationHookRunner.run(hook_inputs)
          |
          +-> SummaryRegenerator.regenerate()     per record with "regenerate_summary"
          +-> CentroidRecomputer.recompute()      per record with "recompute_centroid"
          +-> Batched UPDATE (summary_json, embedding_text, embedding_vector)
```

**Critical sequencing**: Hooks run AFTER R7 commits, so the truth records exist in DB with their new merged data (from M9.5) but potentially stale or null embedding columns. The hook runner then UPDATEs those records with fresh content. This is safe because:

- R7 writes are already committed (no rollback risk)
- Hook failures leave the record with stale content (degraded but not corrupted)
- The batched UPDATE uses the record's PK and version for safety

**R8 bus events**: Can run in parallel with hooks or after hooks. The bus event payload does NOT include embedding_vector (too large), so hook timing does not affect R8.

---

#### M9.6.13 Batched UPDATE Statement (Per-Record)

The hook runner writes all hook outputs in a single UPDATE per record:

```sql
-- For episodic layer (all hooks):
UPDATE st_epi
SET episode_summary = $2,          -- structured JSON from SummaryRegenerator
    embedding_text = $3,           -- regenerated template text
    embedding_vector = $4,         -- recomputed centroid (768-dim bytes)
    embedding_model = $5,          -- "ultrabert-v2.1.0"
    source_texts_json = $6,        -- refreshed from current member events
    updated_at = $7
WHERE episode_id = $1
  AND archival_status = 'ACTIVE';

-- For non-episodic layers (e.g., st_sem):
UPDATE st_sem
SET embedding_text = $2,
    embedding_vector = $3,
    embedding_model = $4,
    source_texts_json = $5,
    updated_at = $6
WHERE pattern_id = $1
  AND archival_status = 'ACTIVE';
```

**No version check**: Unlike M9.5 EXTEND (which uses optimistic locking), hook UPDATEs do NOT check version. The record was just written by R7 in the same cycle -- there's no concurrent writer risk. The `archival_status = 'ACTIVE'` guard prevents writing to records that were simultaneously PRUNED or SUPERSEDED.

---

#### M9.6.14 Per-Layer Applicability Matrix

| Layer | Has `embedding_text` | Has `embedding_vector` | Has `episode_summary` | regenerate_summary | recompute_centroid | Notes |
|-------|---------------------|----------------------|---------------------|-------------------|-------------------|-------|
| st_epi | YES | YES | YES (TEXT) | YES (structured JSON + embedding_text) | YES (weighted mean centroid) | Full hook support |
| st_sem | YES | YES | NO | YES (embedding_text only) | YES (text-based re-embed) | No structured summary -- uses `pattern_description` |
| st_procedural | YES | YES | NO | YES (embedding_text only) | YES (text-based re-embed) | |
| st_social | YES | YES | NO | YES (embedding_text only) | YES (text-based re-embed) | |
| st_prospective | YES | YES | NO | YES (embedding_text only) | YES (text-based re-embed) | |
| st_kg_dom | YES | YES | NO | YES (embedding_text only) | YES (text-based re-embed) | |
| st_kg_edges | NO | NO | NO | NO | NO | Edges have no embedding |
| st_learning_queue | NO | NO | NO | NO | NO | CONTRADICT target, no embedding |

---

#### M9.6.15 Centroid Computation Detail: Episodic EXTEND vs EVOLVE

**EXTEND** (add new content to existing episode):

```
Before EXTEND: Episode E1 has events [e1, e2, e3], centroid C1
New event e4 is added by EXTEND (M9.5 merges event_ids)
After R7 write: Episode E1 has events [e1, e2, e3, e4], centroid is STALE

M9.6 hook:
    1. Load embeddings for [e1, e2, e3, e4] from st_hipp_events.embedding_768
    2. Load metadata (importance_score, conversation_anchor_ms) for weighting
    3. CentroidCalculator.compute([e1,e2,e3,e4], strategy="hybrid")
       -> 0.7 * importance_weight + 0.3 * recency_weight per event
       -> weighted sum, L2-normalized
    4. New centroid C2 (reflects e4's contribution)
    5. UPDATE st_epi SET embedding_vector = C2 WHERE episode_id = E1
```

**EVOLVE** (create successor, supersede old):

```
Before EVOLVE: Episode E1 (old) has events [e1, e2, e3], centroid C1
K1 correction signal provides updated understanding

M9.5 produces 2 writes:
    Write 1: UPDATE E1 SET is_canonical=FALSE, archival_status=SUPERSEDED
    Write 2: INSERT E2 (new) with supersedes_id=E1, events from candidate

After R7 write: E2 exists with events from the correction candidate

M9.6 hook (runs on E2 ONLY, not on superseded E1):
    1. Load embeddings for E2's member events
    2. CentroidCalculator.compute(E2_events, strategy="hybrid")
    3. Fresh centroid C3 -- NO inheritance from E1's centroid
    4. UPDATE st_epi SET embedding_vector = C3 WHERE episode_id = E2

E1 keeps its old centroid C1 (historical accuracy preserved)
```

---

#### M9.6.16 Performance Budget

| Operation | Latency | Frequency | Notes |
|-----------|---------|-----------|-------|
| SummaryRegenerator: fetch events | ~5ms per 10 events | Per record with `regenerate_summary` | Async DB query to st_hipp_events |
| SummaryRegenerator: build structured JSON | <1ms | Per episodic record | Pure Python, no I/O |
| SummaryRegenerator: generate embedding_text | <1ms | Per record | Template-based, no LLM |
| CentroidRecomputer: load event embeddings | ~5ms per 10 events | Per episodic record with `recompute_centroid` | Async DB query to st_hipp_events |
| CentroidRecomputer: compute centroid | <1ms | Per episodic record | NumPy weighted sum + L2 norm |
| CentroidRecomputer: UltraBERT re-embed | ~30ms | Per non-episodic record | Only if embedding_text changed |
| Hook UPDATE statement | ~2ms per record | Per record with any hook | Single UPDATE, no version check |
| **Total per-record** | **~10-40ms** | | Episodic: ~15ms (no UltraBERT); Non-episodic: ~35ms (with UltraBERT) |
| **Typical batch (50 records, 30 hookable)** | **~500ms** | | Dominated by UltraBERT calls on non-episodic records |

**Optimization**: Batch the UltraBERT calls for non-episodic records. Instead of 20 individual ~30ms calls, batch them as a single inference pass (~100ms total). The `EmbeddingGenerator` already supports batch mode internally.

---

#### M9.6.17 Error Handling and Degradation

| Failure Scenario | Impact | Recovery |
|-----------------|--------|----------|
| SummaryRegenerator fails for one record | Record keeps old `episode_summary` and `embedding_text` | Logged; next EXTEND/EVOLVE will retry |
| CentroidRecomputer fails for one record | Record keeps stale `embedding_vector` | Logged; retrieval quality slightly degraded until next regen |
| UltraBERT service unavailable | All non-episodic centroids skip | `embedding_vector` stays as-is; logged as batch warning |
| st_hipp_events query returns 0 events | Empty structured summary, no centroid | Summary gets `event_count: 0`; centroid skipped |
| Hook UPDATE fails (DB error) | Record has committed R7 data but stale embedding | Logged; manual recompute via CLI tool or next cycle |
| Entire hook runner crashes | All records in batch keep stale content | R7 writes are safe (already committed); R8 bus events proceed |

**Invariant**: Hook failures NEVER roll back R7 writes. The truth record is always consistent (correct action, merge rules applied, version incremented). Only the embedding/summary content may be stale.

---

#### M9.6.18 Execution Steps (Ordered)

| Step | Action | Output | Verification |
|------|--------|--------|--------------|
| 1 | Create `hooks/__init__.py` with hook type constants | `HOOK_REGENERATE_SUMMARY`, `HOOK_RECOMPUTE_CENTROID` | Import check |
| 2 | Create `hooks/result.py` | HookResult dataclass | `test_runner.py::test_hook_result_fields` |
| 3 | Create `hooks/episode_summary.py` | StructuredEpisodeSummary + `build_structured_summary()` | `test_summary_regen.py::test_structured_summary_schema` |
| 4 | Create `hooks/summary_regen.py` | SummaryRegenerator class | `test_summary_regen.py::test_episodic_regen`, `test_summary_regen.py::test_generic_regen` |
| 5 | Create `hooks/centroid_recompute.py` | CentroidRecomputer class | `test_centroid_recompute.py::test_episodic_centroid`, `test_centroid_recompute.py::test_text_based_embed` |
| 6 | Create `hooks/runner.py` | PostReconciliationHookRunner | `test_runner.py::test_dispatch_order`, `test_runner.py::test_skip_empty_hooks` |
| 7 | Create contract YAML | `reconciliation.post_hooks.v1.yaml` | CI schema validation |
| 8 | Create `test_runner.py` | 20+ tests: dispatch, ordering, error isolation, batch result | pytest passes |
| 9 | Create `test_summary_regen.py` | 15+ tests: structured summary fields, template text, EXTEND vs CREATE | pytest passes |
| 10 | Create `test_centroid_recompute.py` | 15+ tests: centroid recalc, weighting, EVOLVE fresh, REINFORCE skip | pytest passes |
| 11 | Create `test_hooks_integration.py` | End-to-end: R7 write -> hook runner -> verify DB columns | Integration test passes |
| 12 | Verify: existing R7 layer writer tests unchanged | No edits to existing files | `pytest tests/k0/modules/consolidation/truth_writer/` passes |

---

#### M9.6.19 Key Design Decisions

| # | Decision | Rationale | Alternative Considered | Why Rejected |
|---|----------|-----------|----------------------|--------------|
| KD1 | Hooks run AFTER R7 commits, not during R7 writes | Decouples content generation from critical write path; hook failures are safe | Run during R7 INSERT/UPDATE | R7 write fails if centroid computation errors; blocks entire transaction |
| KD2 | No LLM for summaries -- template-based + extractive only | K0 has zero LLM integration; UltraBERT is embedding-only; adding LLM is a separate architecture decision | Use LLM (GPT/Claude) for rich summaries | Latency (~500ms+), cost, external dependency; template quality is sufficient for structured data |
| KD3 | Reuse `episode_summary` TEXT column for structured JSON | No schema migration needed; backwards compatible (readers can check `schema_version` field) | New JSONB column `structured_summary_json` | Migration needed; two columns for same concept; ADR pending but TEXT reuse is pragmatic |
| KD4 | Write to inline `embedding_vector`, NOT st_vec | st_vec has `event_id` FK constraint; centroids are not events; inline system (GAP-001) is the current standard | Write to st_vec with synthetic event_id | FK violation workaround is fragile; inline is simpler and already deployed |
| KD5 | REINFORCE skips summary regen for non-episodic layers | REINFORCE only bumps observation_count; embedding_text content unchanged; ~30ms UltraBERT call is wasted | Always re-embed on every REINFORCE | 20x wasted compute for pure observation bumps; episodic still recomputes (member set changes) |
| KD6 | EVOLVE hooks run on NEW record only | Superseded record keeps historical centroid for audit; new record needs fresh content | Run hooks on both old and new | Superseded record is frozen; recomputing its centroid is wasteful and misleading |
| KD7 | Hook order: summary first, centroid second | Summary produces `embedding_text` which centroid may use for non-episodic re-embedding | Centroid first, summary second | Centroid for non-episodic needs the updated `embedding_text` as input |
| KD8 | One batched UPDATE per record, not per hook | Minimizes DB round trips (1 UPDATE vs 2 per record) | Separate UPDATE per hook output | 2x DB round trips; MVCC overhead for double version bump |
| KD9 | Hook failures logged, never propagated | R7 writes are safe; stale content is degraded but not corrupted; next cycle will retry | Propagate errors to R6 for retry | R7 transaction already committed; retry semantics are complex; stale content is tolerable |
| KD10 | `archive_superseded` is NOT a post-R7 hook | Already handled by M9.5 EvolveHandler as part of the EVOLVE StagedWrite pair | Make it a post-R7 hook | It's a write operation (SET is_canonical=FALSE), not content generation; must be in the same transaction as the INSERT new |

---

#### M9.6.20 Validation Criteria (Exit Gates)

| # | Criterion | How to Verify |
|---|----------|---------------|
| V1 | CREATE triggers both `regenerate_summary` and `recompute_centroid` | `test_runner.py::test_create_both_hooks` |
| V2 | REINFORCE triggers only `recompute_centroid` (no summary regen) | `test_runner.py::test_reinforce_centroid_only` |
| V3 | EXTEND triggers both hooks | `test_runner.py::test_extend_both_hooks` |
| V4 | EVOLVE hooks run on NEW record only (not superseded) | `test_runner.py::test_evolve_hooks_new_record_only` |
| V5 | CONTRADICT/SKIP/PRUNE trigger no hooks | `test_runner.py::test_no_hooks_actions` |
| V6 | Summary order before centroid | `test_runner.py::test_hook_execution_order` |
| V7 | StructuredEpisodeSummary has schema_version field | `test_summary_regen.py::test_schema_version` |
| V8 | StructuredEpisodeSummary round-trips through JSON | `test_summary_regen.py::test_json_roundtrip` |
| V9 | Episodic summary contains affect_trajectory from member events | `test_summary_regen.py::test_affect_trajectory_populated` |
| V10 | Episodic summary event_records are sorted chronologically | `test_summary_regen.py::test_event_records_sorted` |
| V11 | Non-episodic summary returns embedding_text only (no summary_json) | `test_summary_regen.py::test_generic_no_summary_json` |
| V12 | Episodic centroid uses HYBRID weighting strategy | `test_centroid_recompute.py::test_hybrid_strategy` |
| V13 | Non-episodic centroid uses UltraBERT text embedding | `test_centroid_recompute.py::test_text_based_embed` |
| V14 | REINFORCE on non-episodic skips centroid (no embedding_text change) | `test_centroid_recompute.py::test_reinforce_nonep_skip` |
| V15 | EVOLVE produces fresh centroid (not inherited from superseded) | `test_centroid_recompute.py::test_evolve_fresh_centroid` |
| V16 | Batched UPDATE writes all hook outputs in one statement | `test_hooks_integration.py::test_single_update_per_record` |
| V17 | Hook failure does NOT roll back R7 writes | `test_runner.py::test_failure_isolation` |
| V18 | HookBatchResult counts are accurate (summary_regen_count, centroid_recompute_count, skipped, failed) | `test_runner.py::test_batch_result_counts` |
| V19 | 768-dim centroid vector stored correctly as bytes (3072 bytes) | `test_centroid_recompute.py::test_vector_bytes_length` |
| V20 | Existing TextVectorCoordinator tests still pass | `pytest tests/k0/modules/consolidation/truth_writer/` -- no modifications |

---

#### M9.6.21 What M9.6 Does NOT Do

| Out of Scope | Why | When |
|-------------|-----|------|
| Add LLM-generated summaries | K0 has zero LLM integration; architecture decision needed first | Future ADR |
| Create new `structured_summary_json` JSONB column | Reuses existing `episode_summary` TEXT column for JSON | Future if TEXT proves insufficient |
| Modify st_vec schema (add episode centroid rows) | st_vec has event_id FK; inline embedding_vector is the target | Never (inline is the standard) |
| Modify R7 layer writers | Hooks run AFTER R7; existing INSERT path unchanged | Never |
| Modify R6 coordinator | R6 only needs to collect `(result, write)` pairs and pass to runner | M9.8 wires the runner into R6 |
| Build HTML rendering of structured summaries | Computed on demand by K1/frontend, not stored | K1 scope |
| Handle st_kg_edges or st_learning_queue hooks | These layers have no embedding columns | Never (by design) |
| Deprecate `embedding_id` on st_epi | Legacy FK to st_vec; still referenced by some queries | Post-M9.8 cleanup |
| Make hooks async/parallel across records | Sequential per-record is simpler; batch UltraBERT handles parallelism | Future optimization if latency is a problem |
| Build a standalone centroid recompute CLI tool | Useful but not blocking M9.6 | Can be added as a script later |

---

### M9.7 -- Remaining Identity Strategies (x6)

Implement the identity strategies for the 6 non-episodic truth layers: SemanticIdentity, EntityIdentity, EdgeIdentity, SocialIdentity, ProceduralIdentity, ProspectiveIdentity.

**Status**: READY TO IMPLEMENT
**Estimated Scope**: 6 strategy classes + 1 shared utility + per-strategy tests + contracts
**Depends on**: M9.2 (IdentityStrategy protocol defined, ReconciliationCandidate/IdentityResult types), M9.3 (query paths available for existing truth records)

---

#### M9.7.1 Objective

Implement the 6 remaining `IdentityStrategy` classes -- one per non-episodic truth layer -- so that M9.4's `ReconciliationFramework.decide()` can score identity for ANY truth layer, not just st_epi. These strategies range from pure deterministic key matching (st_kg_edges) to hybrid exact+fuzzy+embedding scoring (st_kg_dom). Unlike `EpisodicIdentity` (M9.2), none of these have a trained ML model; all use rule-based scoring calibrated to the existing bespoke thresholds from R3/R4.

---

#### M9.7.2 Why 6 Strategies, Not 1

Each truth layer has a fundamentally different identity model:

| Layer | Identity Signal | Nature | Complexity |
|-------|----------------|--------|-----------|
| st_sem | Embedding cosine + pattern_type match | Continuous | Medium |
| st_kg_dom | Exact canonical_name -> fuzzy alias -> embedding fallback | Hybrid cascade | High |
| st_kg_edges | Compound key: (source_entity_id, target_entity_id, relationship_type) | Deterministic | Low |
| st_social | Normalized participant pair: (min(a,b), max(a,b)) | Deterministic | Low |
| st_procedural | Routine name fuzzy + action_sequence embedding + temporal pattern | Hybrid | Medium |
| st_prospective | Embedding cosine + deadline proximity boost | Continuous | Medium |

A single generic strategy would either over-engineer the simple cases (edges, social) or under-serve the complex ones (entities, procedural). The `IdentityStrategy` protocol (M9.2) is the unifying abstraction; concrete strategies encapsulate per-layer semantics.

---

#### M9.7.3 Deliverables

| # | Deliverable | File Path | New/Edit | Description |
|---|-----------|-----------|----------|-------------|
| D1 | SemanticIdentity | `k0/modules/consolidation/identity/semantic.py` | NEW | Cosine + pattern_type matching for st_sem |
| D2 | EntityIdentity | `k0/modules/consolidation/identity/entity.py` | NEW | 3-tier cascade: exact name -> fuzzy -> embedding |
| D3 | EdgeIdentity | `k0/modules/consolidation/identity/edge.py` | NEW | Compound key deterministic match for st_kg_edges |
| D4 | SocialIdentity | `k0/modules/consolidation/identity/social.py` | NEW | Normalized pair deterministic match for st_social |
| D5 | ProceduralIdentity | `k0/modules/consolidation/identity/procedural.py` | NEW | Name fuzzy + embedding + temporal pattern for st_procedural |
| D6 | ProspectiveIdentity | `k0/modules/consolidation/identity/prospective.py` | NEW | Cosine + deadline proximity for st_prospective |
| D7 | Shared string utilities | `k0/modules/consolidation/identity/string_utils.py` | NEW | Levenshtein, normalized_name, alias_match for entity/procedural |
| D8 | Strategy factory update | `k0/modules/consolidation/identity/__init__.py` | EDIT | Register all 7 strategies in `IDENTITY_STRATEGIES: Dict[str, Type[IdentityStrategy]]` |
| D9 | Per-strategy unit tests (x6) | `tests/k0/modules/consolidation/identity/test_<layer>.py` | NEW | Each strategy tested against known inputs |
| D10 | Cross-strategy protocol conformance | `tests/k0/modules/consolidation/identity/test_all_strategies.py` | NEW | All 7 satisfy IdentityStrategy protocol |
| D11 | Per-layer contract files (x6) | `k0/contracts/modules/consolidation.identity.<layer>.v1.yaml` | NEW | Metadata key contracts, thresholds, behaviors |
| D12 | Module contract update | `k0/contracts/modules/consolidation.identity.v1.yaml` | EDIT | Add strategy registry and factory contract |

---

#### M9.7.4 File Location Map

```
NEW FILES:

  k0/modules/consolidation/identity/
      semantic.py                   # D1: SemanticIdentity
      entity.py                     # D2: EntityIdentity
      edge.py                       # D3: EdgeIdentity
      social.py                     # D4: SocialIdentity
      procedural.py                 # D5: ProceduralIdentity
      prospective.py                # D6: ProspectiveIdentity
      string_utils.py               # D7: Levenshtein, normalize, alias match

  k0/contracts/modules/
      consolidation.identity.semantic.v1.yaml
      consolidation.identity.entity.v1.yaml
      consolidation.identity.edge.v1.yaml
      consolidation.identity.social.v1.yaml
      consolidation.identity.procedural.v1.yaml
      consolidation.identity.prospective.v1.yaml

  tests/k0/modules/consolidation/identity/
      test_semantic.py
      test_entity.py
      test_edge.py
      test_social.py
      test_procedural.py
      test_prospective.py
      test_all_strategies.py        # Cross-strategy protocol conformance

EDITED FILES:

  k0/modules/consolidation/identity/__init__.py    # Add factory, register 7 strategies
  k0/contracts/modules/consolidation.identity.v1.yaml  # Strategy registry
```

---

#### M9.7.5 IdentityStrategy Protocol (Recap from M9.2)

All 7 strategies implement this protocol:

```python
class IdentityStrategy(Protocol):
    @property
    def layer_id(self) -> str:
        """Which truth layer this strategy serves (e.g. 'st_sem')."""
        ...

    def match_key(
        self,
        candidate: ReconciliationCandidate,
    ) -> Optional[str]:
        """Return deterministic key for exact-match lookup, or None if no natural key."""
        ...

    def score_identity(
        self,
        candidate: ReconciliationCandidate,
        existing: TruthRecord,
        cosine_sim: float,
    ) -> IdentityResult:
        """Score identity between candidate and existing record."""
        ...
```

---

#### M9.7.6 Strategy 1: SemanticIdentity (st_sem)

**Identity model**: Cosine similarity on embedding, boosted by pattern_type match and topic overlap.

**match_key()**: Returns `None`. Semantic patterns have no natural key -- identity is always embedding-based.

**score_identity() logic**:

```
Input:
  candidate.metadata: {pattern_type, topics: set[str], exemplar_count: int}
  existing.metadata:  {pattern_type, topics: set[str], exemplar_count: int}
  cosine_sim: float (pre-computed from M9.3 query)

Features (5):
  f0 = cosine_sim
  f1 = 1.0 if candidate.pattern_type == existing.pattern_type else 0.0
  f2 = jaccard(candidate.topics, existing.topics)
  f3 = min(existing.exemplar_count, 10) / 10.0   # saturation at 10
  f4 = f0 * f1  # interaction: cosine * type_match

Score = weighted_sum:
  score = 0.50 * f0 + 0.20 * f1 + 0.15 * f2 + 0.05 * f3 + 0.10 * f4

Thresholds (calibrated to existing R3 ReconciliationEngine):
  score >= 0.85  -> recommended_action = REINFORCE
  score >= 0.55  -> recommended_action = EXTEND
  score >= 0.35  -> recommended_action = EVOLVE
  score <  0.35  -> recommended_action = CREATE
```

**Return**: `IdentityResult(score=score, recommended_action=action, features={...})`

**What it replaces**: `ReconciliationEngine._score_candidates()` in R3 for st_sem layer. Current code uses cosine-only (1 signal); SemanticIdentity adds pattern_type gating and topic overlap (3 additional signals).

---

#### M9.7.7 Strategy 2: EntityIdentity (st_kg_dom)

**Identity model**: 3-tier deterministic cascade with embedding fallback.

**match_key()**: Returns `f"{entity_type}:{canonical_name.lower()}"`. Entities have a natural key (type+name), which is checked first before any scoring.

**score_identity() logic** -- 3-tier cascade:

```
Tier 1: Exact canonical name match
  IF candidate.canonical_name.lower() == existing.canonical_name.lower()
     AND candidate.entity_type == existing.entity_type:
     RETURN IdentityResult(score=1.0, recommended_action=REINFORCE)

Tier 2: Alias match
  IF candidate.canonical_name.lower() IN existing.aliases (lowered):
     RETURN IdentityResult(score=0.92, recommended_action=REINFORCE)

  IF existing.canonical_name.lower() IN candidate.aliases (lowered):
     RETURN IdentityResult(score=0.92, recommended_action=REINFORCE)

Tier 3: Fuzzy name + embedding composite
  edit_dist = levenshtein(candidate.canonical_name.lower(), existing.canonical_name.lower())
  name_sim  = max(0.0, 1.0 - edit_dist / max(len(cand_name), len(exist_name)))

  IF candidate.entity_type != existing.entity_type:
     type_penalty = 0.3  # Different entity types rarely match
  ELSE:
     type_penalty = 0.0

  score = 0.40 * cosine_sim + 0.35 * name_sim + 0.25 * context_boost - type_penalty

  Where context_boost:
    co_occurrence = 1.0 if candidate.co_occurring_entities & existing.co_occurring_entities else 0.0
    location_match = 1.0 if candidate.location_hint == existing.location_hint else 0.0
    context_boost = 0.5 * co_occurrence + 0.5 * location_match

  Thresholds:
    score >= 0.85 -> REINFORCE
    score >= 0.60 -> EXTEND (merge attributes)
    score >= 0.40 -> EVOLVE
    score <  0.40 -> CREATE
```

**What it replaces**: `AmbiguousEntityResolver` 5-priority context hierarchy in R4. Current code uses recency/co-occurrence/location/temporal/frequency boosts as additive confidence adjustments. EntityIdentity consolidates this into a single scored pipeline with deterministic key fast-path.

**Confidence bands preserved**: AUTO_RESOLVED (>= 0.85), RESOLVED_FLAGGED (0.60-0.84), GAP_EMITTED (< 0.60) map to REINFORCE/EXTEND/CREATE action recommendations. The GAP_EMITTED -> P06 routing is handled by M9.4 framework, not the identity strategy.

---

#### M9.7.8 Strategy 3: EdgeIdentity (st_kg_edges)

**Identity model**: Pure deterministic compound key. No scoring needed.

**match_key()**: Returns `f"{source_entity_id}:{target_entity_id}:{relationship_type}"`. Edges are uniquely identified by their compound key.

**score_identity() logic**:

```
key_match = (
    candidate.source_entity_id == existing.source_entity_id
    AND candidate.target_entity_id == existing.target_entity_id
    AND candidate.relationship_type == existing.relationship_type
)

IF key_match:
    RETURN IdentityResult(score=1.0, recommended_action=REINFORCE)
ELSE:
    RETURN IdentityResult(score=0.0, recommended_action=CREATE)
```

There is no fuzzy or embedding matching for edges. Edge identity is binary: exact compound key match or create new.

**Why no embedding?**: Edges inherit semantics from their endpoint entities. The relationship type (PARENT_OF, FRIEND_OF, CAUSES, etc.) is a controlled vocabulary, not free text. Two edges with different endpoints are never "the same edge."

**What it replaces**: R4's `HebbianLearner.discover_relationships()` which checks `(source, target, relation_type)` existence before creating. Same logic, now expressed as an IdentityStrategy.

---

#### M9.7.9 Strategy 4: SocialIdentity (st_social)

**Identity model**: Deterministic normalized participant pair. No scoring needed for identity; scoring is reserved for relationship strength updates.

**match_key()**: Returns `f"{min(actor_a_id, actor_b_id)}:{max(actor_a_id, actor_b_id)}"`. Social relationships are unique by their order-normalized participant pair.

**score_identity() logic**:

```
pair_a = normalize(candidate.actor_a_id, candidate.actor_b_id)
pair_b = normalize(existing.actor_a_id, existing.actor_b_id)

IF pair_a == pair_b:
    # Same relationship -- check if relationship_type matches
    IF candidate.relationship_type == existing.relationship_type:
        RETURN IdentityResult(score=1.0, recommended_action=REINFORCE)
    ELSE:
        # Same people, different relationship type -- EXTEND (add new type)
        RETURN IdentityResult(score=0.90, recommended_action=EXTEND)
ELSE:
    RETURN IdentityResult(score=0.0, recommended_action=CREATE)
```

**Why deterministic?**: Social relationships are graph edges between resolved entities. Once entities are resolved (by EntityIdentity in M9.7.7), the relationship is uniquely identified by the ordered pair. Embedding similarity is meaningless for relationship identity -- "Sarah and Emma" is always the same relationship regardless of context text.

**Embedding tiebreaker** (exception): If the same participant pair appears with relationship_type=None (unresolved), embedding similarity on interaction text breaks the tie for EXTEND vs CREATE. This is handled as a fallback:

```
IF pair_match AND both relationship_type is None:
    IF cosine_sim >= 0.70:
        RETURN IdentityResult(score=0.85, recommended_action=EXTEND)
    ELSE:
        RETURN IdentityResult(score=0.50, recommended_action=CREATE)
```

**What it replaces**: R3/R6 social write assembly which normalizes `(min(a,b), max(a,b))` for dedup. Same identity logic, now formalized as a strategy.

---

#### M9.7.10 Strategy 5: ProceduralIdentity (st_procedural)

**Identity model**: Hybrid -- routine name fuzzy match + action sequence embedding + temporal pattern alignment.

**match_key()**: Returns `normalize_routine_name(routine_name)`. Procedural routines have a semi-natural key (routine name), but fuzzy matching is needed because the same routine may be described differently across observations ("morning coffee" vs "make coffee in the morning").

**score_identity() logic**:

```
Input:
  candidate.metadata: {routine_name, action_sequence_embedding, daily_pattern, weekly_pattern}
  existing.metadata:  {routine_name, action_sequence_embedding, daily_pattern, weekly_pattern}
  cosine_sim: float (from action_sequence embedding comparison)

Step 1: Name similarity
  name_sim = max(
      normalized_levenshtein(candidate.routine_name, existing.routine_name),
      substring_match_score(candidate.routine_name, existing.routine_name)
  )

Step 2: Temporal pattern alignment
  temporal_sim = 0.0
  IF candidate.daily_pattern AND existing.daily_pattern:
      daily_overlap = overlap_ratio(candidate.daily_pattern, existing.daily_pattern)
      temporal_sim = max(temporal_sim, daily_overlap)
  IF candidate.weekly_pattern AND existing.weekly_pattern:
      weekly_overlap = overlap_ratio(candidate.weekly_pattern, existing.weekly_pattern)
      temporal_sim = max(temporal_sim, weekly_overlap)

Step 3: Composite score
  score = 0.35 * cosine_sim + 0.35 * name_sim + 0.30 * temporal_sim

Thresholds:
  score >= 0.80 -> REINFORCE (same routine observed again)
  score >= 0.55 -> EXTEND (routine variation -- merge steps)
  score >= 0.35 -> EVOLVE (evolved routine)
  score <  0.35 -> CREATE
```

**What it replaces**: R3's bespoke routine matching which uses embedding-only. ProceduralIdentity adds name fuzzy matching (catches "morning coffee" == "make coffee") and temporal alignment (catches routines at same time of day).

---

#### M9.7.11 Strategy 6: ProspectiveIdentity (st_prospective)

**Identity model**: Embedding cosine similarity with deadline proximity boost. This is the most "fuzzy" strategy -- intentions have no natural key and are identified purely by semantic content similarity.

**match_key()**: Returns `None`. Prospective memories have no deterministic key. "Call mom for her birthday" and "Phone mom about birthday" are the same intention but share no exact key.

**score_identity() logic**:

```
Input:
  candidate.metadata: {intention_type, trigger_time_ms, action_text}
  existing.metadata:  {intention_type, trigger_time_ms, action_text, status}
  cosine_sim: float (from embedding comparison)

Step 1: Status filter
  IF existing.status IN ('completed', 'cancelled', 'expired'):
      RETURN IdentityResult(score=0.0, recommended_action=CREATE)
  # Only match against active/pending intentions

Step 2: Deadline proximity boost
  IF candidate.trigger_time_ms AND existing.trigger_time_ms:
      time_diff_days = abs(candidate.trigger_time_ms - existing.trigger_time_ms) / 86400000
      IF time_diff_days <= 7:
          deadline_boost = 0.10 * (1.0 - time_diff_days / 7.0)
      ELSE:
          deadline_boost = 0.0
  ELSE:
      deadline_boost = 0.0

Step 3: Type match boost
  type_boost = 0.05 if candidate.intention_type == existing.intention_type else 0.0

Step 4: Composite score
  score = cosine_sim + deadline_boost + type_boost
  score = min(score, 1.0)  # Cap at 1.0

Thresholds:
  score >= 0.85 -> REINFORCE (same intention re-expressed)
  score >= 0.60 -> EXTEND (add details to existing intention)
  score >= 0.40 -> EVOLVE (related but distinct intention)
  score <  0.40 -> CREATE
```

**Why cosine-only base?**: Intentions are free-text expressions of future plans. There is no structured field (like entity_type or routine_name) that reliably discriminates. The temporal boost addresses the common case where the same intention is expressed near its deadline ("remind me to call mom" 2 days before her birthday vs 1 day before).

**What it replaces**: R3 ReconciliationEngine's cosine-only matching for st_prospective. ProspectiveIdentity adds deadline proximity and type matching (2 new signals).

---

#### M9.7.12 Strategy Factory & Registry

**File**: `k0/modules/consolidation/identity/__init__.py` (EDIT)

```python
IDENTITY_STRATEGIES: Dict[str, Type[IdentityStrategy]] = {
    "st_epi":         EpisodicIdentity,       # M9.2 -- 11-feature logistic
    "st_sem":         SemanticIdentity,        # M9.7 -- cosine + type + topic
    "st_kg_dom":      EntityIdentity,          # M9.7 -- 3-tier cascade
    "st_kg_edges":    EdgeIdentity,            # M9.7 -- compound key
    "st_social":      SocialIdentity,          # M9.7 -- normalized pair
    "st_procedural":  ProceduralIdentity,      # M9.7 -- name + embedding + temporal
    "st_prospective": ProspectiveIdentity,     # M9.7 -- cosine + deadline
}

def get_identity_strategy(layer_id: str) -> IdentityStrategy:
    """Factory function used by ReconciliationFramework (M9.4) to get the correct strategy."""
    cls = IDENTITY_STRATEGIES.get(layer_id)
    if cls is None:
        raise ValueError(f"No identity strategy registered for layer: {layer_id}")
    return cls()
```

The framework calls `get_identity_strategy(layer_id)` once per reconciliation cycle, caches the instance, and reuses it for all candidates targeting that layer.

---

#### M9.7.13 Metadata Key Contracts (Per Layer)

Each strategy expects specific keys in `ReconciliationCandidate.metadata` and `TruthRecord.metadata`. These are strict contracts -- missing keys cause the strategy to degrade gracefully (not crash).

**st_sem metadata contract**:

| Key | Type | Required | Fallback |
|-----|------|----------|----------|
| `pattern_type` | `str` | Yes | score ignores type match (f1=0) |
| `topics` | `set[str]` | Yes | empty set (f2=0) |
| `exemplar_count` | `int` | No | 0 (f3=0) |

**st_kg_dom metadata contract**:

| Key | Type | Required | Fallback |
|-----|------|----------|----------|
| `entity_type` | `str` | Yes | type_penalty=0.3 |
| `canonical_name` | `str` | Yes | Tier 1/2 skipped, Tier 3 name_sim=0 |
| `aliases` | `set[str]` | No | empty set (Tier 2 skipped) |
| `co_occurring_entities` | `set[str]` | No | empty set (context_boost partial=0) |
| `location_hint` | `str` | No | None (location_match=0) |

**st_kg_edges metadata contract**:

| Key | Type | Required | Fallback |
|-----|------|----------|----------|
| `source_entity_id` | `str` | Yes | match_key returns None, score=0 |
| `target_entity_id` | `str` | Yes | match_key returns None, score=0 |
| `relationship_type` | `str` | Yes | match_key returns None, score=0 |

**st_social metadata contract**:

| Key | Type | Required | Fallback |
|-----|------|----------|----------|
| `actor_a_id` | `str` | Yes | match_key returns None, score=0 |
| `actor_b_id` | `str` | Yes | match_key returns None, score=0 |
| `relationship_type` | `str` | No | None (unresolved -- triggers embedding tiebreaker) |

**st_procedural metadata contract**:

| Key | Type | Required | Fallback |
|-----|------|----------|----------|
| `routine_name` | `str` | Yes | name_sim=0 |
| `daily_pattern` | `str` | No | temporal_sim partial=0 |
| `weekly_pattern` | `str` | No | temporal_sim partial=0 |

**st_prospective metadata contract**:

| Key | Type | Required | Fallback |
|-----|------|----------|----------|
| `intention_type` | `str` | No | type_boost=0 |
| `trigger_time_ms` | `int` | No | deadline_boost=0 |
| `status` | `str` | No | assumed "pending" |

---

#### M9.7.14 Threshold Calibration: Bespoke -> Strategy Mapping

Each strategy's thresholds are calibrated to produce equivalent decisions to the existing bespoke code they replace. This table documents the mapping:

| Layer | Bespoke Threshold Source | Strategy Threshold | Rationale |
|-------|------------------------|-------------------|-----------|
| st_sem | ReconciliationEngine: 0.85/0.60/0.40 cosine | 0.85/0.55/0.35 composite | Composite score has more signals -> lower thresholds produce equivalent partitions |
| st_kg_dom | AmbiguousEntityResolver: AUTO(0.85)/FLAGGED(0.60)/GAP(<0.60) | Tier 1/2 deterministic (1.0/0.92), Tier 3: 0.85/0.60/0.40 | Deterministic tiers bypass scoring entirely |
| st_kg_edges | HebbianLearner: exists? increment : create | 1.0 / 0.0 (binary) | No intermediate state for edges |
| st_social | R3: normalize(a,b) then exists? | 1.0 / 0.90 / 0.0 | 0.90 for same-pair different-type |
| st_procedural | ReconciliationEngine: 0.85/0.60/0.40 cosine | 0.80/0.55/0.35 composite | Name+temporal signals lower the cosine bar |
| st_prospective | ReconciliationEngine: 0.85/0.60/0.40 cosine + 0.10 deadline boost | 0.85/0.60/0.40 (boost additive) | Boost on top of base thresholds |

---

#### M9.7.15 Deterministic vs Scored Strategies

The 6 strategies fall into 2 categories with distinct performance characteristics:

**Deterministic strategies** (fast path, O(1) per lookup):

- EdgeIdentity: compound key hash lookup
- SocialIdentity: normalized pair hash lookup

These strategies do NOT need embedding vectors from st_vec. M9.3's `truth_candidates_query` syscall skips embedding loading for these layers when the `match_key()` returns a non-None value. This is a critical optimization: edge and social queries are pure key lookups, never cosine scans.

**Scored strategies** (embedding path, O(K) per candidate where K=top-K):

- SemanticIdentity: cosine + features
- EntityIdentity: 3-tier with embedding fallback
- ProceduralIdentity: name + embedding + temporal
- ProspectiveIdentity: cosine + boosts

These strategies consume the `cosine_sim` pre-computed by M9.3 and add layer-specific signals.

**EntityIdentity hybrid**: Tier 1/2 are deterministic (exact/alias match). Only falls through to Tier 3 (embedding) when deterministic tiers fail. The `match_key()` enables a fast-path: if M9.3 finds an exact key match, it returns that record immediately without loading embeddings.

---

#### M9.7.16 Implementation Order

Strategies should be implemented in this order (simplest first, building complexity incrementally):

| Order | Strategy | Complexity | Why This Order |
|-------|----------|-----------|----------------|
| 1 | EdgeIdentity | LOW | Pure deterministic, no scoring, simplest protocol validation |
| 2 | SocialIdentity | LOW | Deterministic + one edge case (unresolved type tiebreaker) |
| 3 | SemanticIdentity | MEDIUM | First scored strategy, closest to EpisodicIdentity pattern |
| 4 | ProspectiveIdentity | MEDIUM | Scored with boosts, slightly more complex than semantic |
| 5 | ProceduralIdentity | MEDIUM | 3-signal composite, temporal pattern alignment is new |
| 6 | EntityIdentity | HIGH | 3-tier cascade, most complex, builds on string_utils from step 5 |

After each strategy, run `test_all_strategies.py` to verify the growing registry still passes protocol conformance.

---

#### M9.7.17 String Utility Module (Shared)

**File**: `k0/modules/consolidation/identity/string_utils.py`

Used by EntityIdentity (Tier 2/3) and ProceduralIdentity (name matching):

```python
def normalize_name(name: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    ...

def levenshtein_distance(a: str, b: str) -> int:
    """Standard DP Levenshtein. No external dependency."""
    ...

def normalized_levenshtein(a: str, b: str) -> float:
    """1.0 - (distance / max(len(a), len(b))). Returns 0.0 if both empty."""
    ...

def substring_match_score(needle: str, haystack: str) -> float:
    """Ratio of longest common substring to max length. For catching partial routine names."""
    ...

def alias_match(name: str, aliases: set[str]) -> bool:
    """Case-insensitive check if name appears in aliases set."""
    ...
```

No external dependencies (no `python-Levenshtein`, no `fuzzywuzzy`). Pure Python implementation. This avoids adding C extension dependencies to the production image.

---

#### M9.7.18 Validation Criteria (Exit Gates)

| # | Criterion | How to Verify |
|---|----------|---------------|
| V1 | All 6 strategies satisfy `IdentityStrategy` protocol | `test_all_strategies.py` -- `isinstance` + method signature check for all 7 (including EpisodicIdentity) |
| V2 | EdgeIdentity returns 1.0 on exact key match, 0.0 otherwise | Unit test with known compound keys |
| V3 | SocialIdentity normalizes pair order correctly | `(B, A)` matches `(A, B)` with score=1.0 |
| V4 | EntityIdentity Tier 1 bypasses Tier 2/3 | Timing test: Tier 1 match returns without computing Levenshtein |
| V5 | EntityIdentity Tier 2 matches aliases | Alias "Bob" matches canonical_name "Robert" |
| V6 | SemanticIdentity type mismatch penalty applies | Same embedding, different pattern_type -> lower score |
| V7 | ProspectiveIdentity deadline boost is bounded [0, 0.10] | Edge cases: same day, 7 days apart, no deadline |
| V8 | ProceduralIdentity temporal_sim handles missing patterns | daily_pattern=None -> temporal_sim=0 |
| V9 | get_identity_strategy() returns correct type for all 7 layers | Factory test |
| V10 | get_identity_strategy() raises ValueError for unknown layer | Error test |
| V11 | Deterministic strategies (edge, social) produce no IdentityResult with score in (0, 1) exclusive | They return only 0.0, 0.90, 0.92, or 1.0 |
| V12 | No external string matching dependency imported | grep for `fuzzywuzzy`, `rapidfuzz`, `python-Levenshtein` returns 0 in `k0/modules/consolidation/identity/` |

---

#### M9.7.19 What M9.7 Does NOT Do

| Out of Scope | Why | When |
|-------------|-----|------|
| Replace bespoke matching in R3/R4 | Phase migration is M9.8 | M9.8 |
| Train ML models for non-episodic layers | Rule-based is sufficient for current data volume; ML comes if needed | Future |
| Add new truth layers | M9.7 covers the 6 existing non-episodic layers | Future |
| Modify M9.3 query paths | M9.3 already supports per-layer queries; M9.7 consumes them | Done (M9.3) |
| Handle K1 signal bypass | Framework (M9.4) checks K1 signals before calling strategy | Done (M9.4) |
| Implement confidence bands routing to P06 | Framework responsibility, not strategy | Done (M9.4) |

---

### M9.8 -- Phase Migration (R2 -> R3 -> R4 -> R5)

Migrate each P03 phase from bespoke reconciliation logic to unified engine calls. This is the big integration milestone where the M9.1-M9.7 infrastructure replaces scattered reconciliation code across R2, R3, R4, R5, and R6.

**Status**: READY TO IMPLEMENT (after M9.1-M9.7)
**Estimated Scope**: 4 phase rewrites + R6 simplification + dual-path migration harness + regression suite
**Depends on**: M9.1 (registry), M9.2 (EpisodicIdentity), M9.3 (query syscall), M9.4 (framework), M9.5 (write router), M9.6 (hooks), M9.7 (all identity strategies)

---

#### M9.8.1 Objective

Replace bespoke reconciliation logic in 4 P03 phases (R2, R3, R4, R5) with calls to the unified `ReconciliationFramework.decide()` (M9.4) and `WriteDecisionRouter.route()` (M9.5). Each phase migration follows the same pattern: feature-flagged dual-path, divergence logging, canary rollout, then bespoke removal. R6 is simplified from 14 assemble methods to a StagedWrite collector. R7 and R8 are unchanged.

---

#### M9.8.2 Current Bespoke Reconciliation Inventory

Code archaeology reveals 3 independent reconciliation subsystems that M9.8 replaces:

**R2 Bespoke (Episodic -- 3 seams)**:

| Seam | File | Lines | What It Does | Engine Replacement |
|------|------|-------|-------------|-------------------|
| Episode Matching | `r2_episodic_integrator.py` | 607-625 | Query st_epi, cosine >= 0.85 -> REINFORCE, remove from clustering pool | `framework.decide()` per event against st_epi, EpisodicIdentity scores |
| Same-Thread Merge | `same_thread_merge.py` | 211-268 | Group clusters by thread, union-find merge if centroid_sim >= 0.70 AND gap <= 4h | KEPT IN R2 (intra-batch optimization, not truth reconciliation) |
| Cross-Batch Extend | `cross_batch_extend.py` | 198-240 | Match new episode candidates to existing by centroid >= 0.60 + same thread + 7d | `framework.decide()` per EpisodeCandidate against st_epi, EpisodicIdentity scores |

**R3 Bespoke (Dedup/Decay -- 1 seam)**:

| Seam | File | Lines | What It Does | Engine Replacement |
|------|------|-------|-------------|-------------------|
| ReconciliationEngine v1 | `reconciliation_engine.py` | 290-600 | Per-event cosine matching across 5 layers, threshold-based action | `framework.decide()` per event, dispatches to per-layer IdentityStrategy |

**R4 Bespoke (Knowledge Graph -- 2 seams)**:

| Seam | File | Lines | What It Does | Engine Replacement |
|------|------|-------|-------------|-------------------|
| AmbiguousEntityResolver | `ambiguous_resolver.py` | 365+ | 5-priority context hierarchy for entity disambiguation | `framework.decide()` with EntityIdentity 3-tier cascade |
| HebbianLearner edge existence | R4 edge creation | scattered | Check (source, target, type) exists before create | `framework.decide()` with EdgeIdentity compound key match |

---

#### M9.8.3 Migration Principle: Same-Thread Merge Stays in R2

**Critical design decision**: Same-thread merge is NOT migrated to the engine. It remains as bespoke R2 logic.

Rationale:

1. Same-thread merge operates on **intra-batch clusters** (not truth records). It merges HDBSCAN fragment clusters that share a narrative thread within a single batch. This is a clustering quality optimization, not truth reconciliation.
2. The engine operates on **candidate vs existing truth record** pairs. It answers "does this candidate match an existing record?" Same-thread merge answers "should these two new clusters be combined?"
3. ThreadPurityCorrector also stays in R2 for the same reason (clustering quality, not truth identity).

What moves to the engine:

- Episode Matching (REINFORCE): candidate event -> existing episode (truth reconciliation)
- Cross-Batch Extend: candidate episode -> existing episode (truth reconciliation)

What stays in R2:

- EpisodeSplitter (pre-clustering segmentation)
- HDBSCAN clustering
- ThreadPurityCorrector (Epic 6.2)
- SameThreadMerger (Epic 6.3)
- CentroidCalculator
- SecondaryCentroidSelector
- EpsAdjuster/MinSamplesAdjuster (adaptive learning)
- ClusterQualityTracker

---

#### M9.8.4 Migration Architecture: Feature-Flagged Dual-Path

Every phase migration uses the same dual-path pattern:

```
R2Config / R3Config / R4Config:
    enable_engine_reconciliation: bool = False    # Master switch (default OFF)
    engine_dual_path_enabled: bool = False        # A/B comparison mode
    engine_dual_path_log_divergences: bool = True

Phase.run():
    IF enable_engine_reconciliation:
        result = await self._run_with_engine(envelope, ctx)
    ELSE:
        result = await self._run_bespoke(envelope, ctx)    # Existing code unchanged

    IF engine_dual_path_enabled:
        bespoke_result = await self._run_bespoke(envelope_copy, ctx)
        engine_result  = await self._run_with_engine(envelope_copy, ctx)
        divergences = self._compare_results(bespoke_result, engine_result)
        IF divergences:
            logger.warning("Phase %s: %d divergences", phase_id, len(divergences))
        result = bespoke_result  # Always use bespoke during dual-path
```

This pattern ensures:

- Default behavior is UNCHANGED (bespoke path)
- Engine can be enabled per-space via config override
- Dual-path mode runs both paths and logs differences WITHOUT affecting output
- Rollback is instant: flip feature flag OFF

---

#### M9.8.5 Deliverables

| # | Deliverable | File Path | New/Edit | Description |
|---|-----------|-----------|----------|-------------|
| D1 | R2 engine path | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | EDIT | Add `_run_with_engine()` for episode matching + cross-batch extend |
| D2 | R3 engine path | `k0/pipelines/p03/phases/r3_dedup_decay.py` | EDIT | Replace ReconciliationEngine v1 with framework.decide() |
| D3 | R4 engine path | `k0/pipelines/p03/phases/r4_kg_consolidator.py` | EDIT | Replace AmbiguousEntityResolver + HebbianLearner edge check |
| D4 | R5 engine path | `k0/pipelines/p03/phases/r5_dream_explorer.py` | EDIT | Add reconciliation for dream outputs (currently none) |
| D5 | R6 simplification | `k0/pipelines/p03/phases/r6_staging.py` | EDIT | Simplify to StagedWrite collector when engine is active |
| D6 | Migration harness | `k0/modules/consolidation/reconciliation/migration.py` | NEW | DualPathRunner, DivergenceLogger, ResultComparator |
| D7 | Phase adapter per layer | `k0/modules/consolidation/reconciliation/adapters/` | NEW | R2Adapter, R3Adapter, R4Adapter -- translate phase outputs to ReconciliationCandidate |
| D8 | Config extensions | `k0/pipelines/p03/config.py` | EDIT | Add engine flags to R2Config, R3Config, R4Config, R5Config |
| D9 | Regression test suite | `tests/k0/pipelines/p03/test_migration_regression.py` | NEW | Full pipeline: engine vs bespoke comparison |
| D10 | Per-phase migration tests | `tests/k0/pipelines/p03/test_r2_engine_path.py` etc. | NEW | Engine path unit tests per phase |
| D11 | Divergence analysis tool | `k0/scripts/analyze_migration_divergences.py` | NEW | Offline tool to analyze dual-path logs |

---

#### M9.8.6 File Location Map

```
EDITED FILES:

  k0/pipelines/p03/phases/
      r2_episodic_integrator.py         # D1: Add _run_with_engine(), feature flag
      r3_dedup_decay.py                 # D2: Replace ReconciliationEngine v1
      r4_kg_consolidator.py             # D3: Replace entity/edge bespoke matching
      r5_dream_explorer.py              # D4: Add reconciliation for dream outputs
      r6_staging.py                     # D5: Simplify assembly when engine active

  k0/pipelines/p03/config.py           # D8: Engine flags per phase

NEW FILES:

  k0/modules/consolidation/reconciliation/
      migration.py                      # D6: DualPathRunner, DivergenceLogger
      adapters/
          __init__.py
          r2_adapter.py                 # D7: R2 EpisodeCandidate -> ReconciliationCandidate
          r3_adapter.py                 # D7: R3 P03EventState -> ReconciliationCandidate
          r4_adapter.py                 # D7: R4 KGEntity/KGEdge -> ReconciliationCandidate

  k0/scripts/
      analyze_migration_divergences.py  # D11: Divergence analysis

  tests/k0/pipelines/p03/
      test_migration_regression.py      # D9: Full pipeline regression
      test_r2_engine_path.py            # D10: R2 engine path tests
      test_r3_engine_path.py            # D10: R3 engine path tests
      test_r4_engine_path.py            # D10: R4 engine path tests
```

---

#### M9.8.7 Phase Adapters: Translating Phase Outputs to ReconciliationCandidate

Each phase produces different output types. The adapters convert them to the universal `ReconciliationCandidate` type (M9.2) so the framework can process any layer uniformly.

**R2Adapter** (`adapters/r2_adapter.py`):

```
Source types:
  - P03EventState (for pre-clustering REINFORCE matching)
  - EpisodeCandidate (for post-clustering EXTEND matching)

event_to_candidate(event: P03EventState) -> ReconciliationCandidate:
    ReconciliationCandidate(
        candidate_id = event.event_id,
        embedding = event.embedding_768,
        source_phase = "R2",
        source_event_ids = [event.event_id],
        tenant_id = event.tenant_id,
        space_id = event.space_id,
        target_layers = ["st_epi"],
        metadata = {
            "topics": extract_topics(event),
            "participants": extract_participants(event),
            "focal": extract_focal(event),
            "social_context": event.social_context,
            "place_id": event.place_id,
            "source_type": event.source_type,
            "locations": {event.place_id} if event.place_id else set(),
        },
        k1_signals = K1SignalBundle(
            correction_signal = event.k1_correction_signal or False,
            contradiction_signal = event.k1_contradiction_signal or False,
        ),
    )

episode_to_candidate(episode: EpisodeCandidate, event_lookup) -> ReconciliationCandidate:
    member_events = [event_lookup[eid] for eid in episode.event_ids]
    ReconciliationCandidate(
        candidate_id = episode.cluster_id,
        embedding = episode.centroid_embedding,     # 768-dim weighted centroid
        source_phase = "R2",
        source_event_ids = episode.event_ids,
        tenant_id = episode.tenant_id,
        space_id = episode.space_id,
        target_layers = ["st_epi"],
        metadata = {
            "topics": union(extract_topics(e) for e in member_events),
            "participants": union(extract_participants(e) for e in member_events),
            "focal": most_common_focal(member_events),
            "social_context": most_common_social(member_events),
            "place_id": first_place_id(member_events),
            "locations": {e.place_id for e in member_events if e.place_id},
            "source_types": {e.source_type for e in member_events if e.source_type},
            "temporal_start": episode.temporal_start,
            "temporal_end": episode.temporal_end,
            "dominant_thread": episode.dominant_thread_id,
        },
        k1_signals = K1SignalBundle.empty(),
    )
```

**R3Adapter** (`adapters/r3_adapter.py`):

```
Source types:
  - P03EventState (for multi-layer reconciliation)

event_to_candidates(event: P03EventState) -> List[ReconciliationCandidate]:
    # R3 reconciles each event against MULTIPLE layers
    # Return one candidate per target layer

    candidates = []
    for layer in ["st_sem", "st_procedural", "st_social", "st_prospective"]:
        candidates.append(ReconciliationCandidate(
            candidate_id = f"{event.event_id}:{layer}",
            embedding = event.embedding_768,
            source_phase = "R3",
            source_event_ids = [event.event_id],
            target_layers = [layer],
            metadata = build_metadata_for_layer(event, layer),
            k1_signals = ...,
        ))
    return candidates
```

**R4Adapter** (`adapters/r4_adapter.py`):

```
Source types:
  - KGEntity (from NER extraction)
  - KGEdge (from Hebbian/Granger)

entity_to_candidate(entity: KGEntity) -> ReconciliationCandidate:
    ReconciliationCandidate(
        candidate_id = entity.entity_id,
        embedding = entity.embedding,
        source_phase = "R4",
        target_layers = ["st_kg_dom"],
        metadata = {
            "entity_type": entity.entity_type,
            "canonical_name": entity.canonical_name,
            "aliases": set(entity.aliases),
            "co_occurring_entities": entity.co_occurring_entity_ids,
            "location_hint": entity.location_hint,
        },
    )

edge_to_candidate(edge: KGEdge) -> ReconciliationCandidate:
    ReconciliationCandidate(
        candidate_id = edge.edge_id,
        embedding = None,              # Edges have no embedding
        source_phase = "R4",
        target_layers = ["st_kg_edges"],
        metadata = {
            "source_entity_id": edge.source_entity_id,
            "target_entity_id": edge.target_entity_id,
            "relationship_type": edge.relationship_type,
        },
    )
```

---

#### M9.8.8 R2 Migration: Episodic Layer (Detailed)

R2 is the most complex migration because it has 2 distinct reconciliation seams operating at different granularities (event-level and episode-level).

**Seam 1: Pre-Clustering Episode Matching (Event-Level REINFORCE)**

Current bespoke code (r2_episodic_integrator.py lines 607-625):

```
1. Query st_epi for existing episodes (50 max, 7-day window, ACTIVE)
2. For each event with embedding:
   a. Compute cosine(event.embedding, episode.centroid) for each episode
   b. If best_sim >= 0.85 -> mark as REINFORCE, remove from clustering pool
3. Output: matched_events (REINFORCE), novel_events (cluster these)
```

Engine replacement:

```
1. For each event with embedding:
   a. candidate = R2Adapter.event_to_candidate(event)
   b. result = await framework.decide(candidate)
      - M9.3 queries st_epi (same 50-max, 7-day window)
      - M9.2 EpisodicIdentity.score_identity() scores 11 features
      - M9.4 applies threshold 0.35 on p_assign
   c. If result.action == REINFORCE -> matched_events
   d. If result.action == CREATE -> novel_events
2. Output: same matched_events / novel_events split
```

Key differences from engine path:

- Bespoke uses 1 feature (cosine >= 0.85); engine uses 11 features (threshold 0.35 on p_assign)
- Engine may match events that bespoke misses (topic_overlap, participant_overlap, etc.)
- Engine may miss events that bespoke matches (if 11-feature model scores below 0.35)
- This is WHY dual-path logging is essential during migration

**Seam 2: Cross-Batch Extend (Episode-Level EXTEND)**

Current bespoke code (r2_episodic_integrator.py lines 787-805):

```
1. For each EpisodeCandidate (with computed centroid):
   a. Compute cosine(candidate.centroid, episode.centroid) for each existing episode
   b. Filter: sim >= 0.60 AND same_thread AND gap <= 7d
   c. If match found -> mark EXTEND with target_episode_id
2. Output: candidates annotated with reconciliation_action and extend_target_episode_id
```

Engine replacement:

```
1. For each EpisodeCandidate:
   a. candidate = R2Adapter.episode_to_candidate(episode, event_lookup)
   b. result = await framework.decide(candidate)
      - M9.3 queries st_epi
      - M9.2 EpisodicIdentity.score_identity() with centroid as embedding
      - M9.4 framework: if p_assign >= 0.35 AND recommended_action IN (EXTEND, REINFORCE)
   c. If result.action == EXTEND:
      episode.reconciliation_action = "EXTEND"
      episode.extend_target_episode_id = result.best_match_id
      episode.extend_similarity = result.similarity_score
   d. If result.action == CREATE:
      episode.reconciliation_action = "CREATE" (default)
2. Output: same annotated candidates
```

Key differences:

- Bespoke requires same_thread + 7-day window (hard filters); engine has no temporal feature (EXP-5: temporal is noise) and thread is captured via topic_overlap
- Engine may produce EXTEND for cross-thread episodes that bespoke would CREATE (because topic_overlap scores high despite different threads)
- Engine may produce CREATE for same-thread low-topic episodes that bespoke would EXTEND (because 11-feature model finds low p_assign)

**R2 Migration config additions**:

```python
@dataclass
class R2Config:
    # ... existing fields unchanged ...

    # M9.8: Engine migration
    enable_engine_reconciliation: bool = False
    enable_engine_reinforce: bool = False    # Seam 1 only
    enable_engine_extend: bool = False       # Seam 2 only
    engine_dual_path_enabled: bool = False
    engine_dual_path_log_divergences: bool = True
```

Granular flags allow migrating Seam 1 (REINFORCE) independently of Seam 2 (EXTEND). Recommended order: Seam 1 first (simpler, event-level), then Seam 2 (episode-level).

---

#### M9.8.9 R3 Migration: Dedup/Decay Layer (Detailed)

R3 already has a feature flag (`enable_reconciliation_engine`) for the existing ReconciliationEngine v1. Migration replaces v1 with the M9.4 framework.

**Current bespoke code** (r3_dedup_decay.py lines 1192-1220):

```
1. If enable_reconciliation_engine:
   a. engine = ReconciliationEngine(config)
   b. For each event:
      decision = await engine.decide(event, space_id, tenant_id)
      - Queries 5 layers via TruthQueryService
      - Cosine-only scoring
      - Threshold: 0.85/0.60/0.40
      event.set_reconciliation(decision)
2. Else: skip (no reconciliation in R3 bespoke path)
```

Engine replacement:

```
1. If enable_engine_reconciliation:
   a. For each event (non-duplicate, non-pruned):
      candidates = R3Adapter.event_to_candidates(event)
      # One candidate per target layer: st_sem, st_procedural, st_social, st_prospective
      for candidate in candidates:
          result = await framework.decide(candidate)
          # M9.3 queries only the target layer
          # M9.7 per-layer IdentityStrategy scores
          # M9.4 framework applies per-layer thresholds
      best_result = select_best(results)
      event.set_reconciliation(best_result)
```

Key differences:

- v1 engine queries ALL 5 layers per event; new framework queries EACH layer separately with per-layer strategy
- v1 uses cosine-only scoring; new framework uses per-layer features (SemanticIdentity has 5 features, etc.)
- v1 returns single ReconciliationDecision; new framework returns per-layer results, caller selects best

**R3 migration is the simplest** because:

1. R3 already has the feature flag pattern
2. R3's ReconciliationEngine v1 was already architecturally close to the new framework
3. R3's dedup/decay logic (SimHash, UnifiedDecayEngine, RetentionEnforcer) is UNCHANGED -- only the reconciliation sub-step migrates

**R3 output contract is unchanged**: R3 populates `event.reconciliation_action`, `event.best_match_id`, `event.best_match_layer`, `event.similarity_score`, `event.confidence` -- same fields, same values, different scoring pipeline.

---

#### M9.8.10 R4 Migration: Knowledge Graph Layer (Detailed)

R4 has 2 reconciliation seams: entity disambiguation and edge existence checking.

**Seam 1: Entity Disambiguation (AmbiguousEntityResolver)**

Current bespoke code:

```
1. NER extraction produces candidate entities
2. For each entity mention:
   a. AmbiguousEntityResolver.resolve(mention, candidates, context)
   b. 5-priority context hierarchy: recency + co-occurrence + location + temporal + frequency
   c. Confidence bands: AUTO(0.85) / FLAGGED(0.60) / GAP(<0.60)
3. Output: resolved entity_id + confidence + resolution_outcome
```

Engine replacement:

```
1. NER extraction produces candidate entities (UNCHANGED)
2. For each entity:
   a. candidate = R4Adapter.entity_to_candidate(entity)
   b. result = await framework.decide(candidate)
      - M9.3 queries st_kg_dom with match_key fast-path
      - M9.7 EntityIdentity: Tier 1 exact -> Tier 2 alias -> Tier 3 fuzzy+embedding
      - M9.4 framework: confidence bands -> actions
   c. If result.action == REINFORCE: AUTO_RESOLVED
   d. If result.action == EXTEND: RESOLVED_FLAGGED
   e. If result.action == CREATE: GAP_EMITTED (if score < 0.60)
3. Output: same resolution_outcome, same confidence, same entity_id
```

**Confidence band mapping**:

| Current (AmbiguousEntityResolver) | Engine (EntityIdentity + Framework) |
|----------------------------------|--------------------------------------|
| AUTO_RESOLVED (>= 0.85) | result.action == REINFORCE |
| RESOLVED_FLAGGED (0.60-0.84) | result.action == EXTEND |
| GAP_EMITTED (< 0.60) | result.action == CREATE AND framework emits P06 gap |

**Seam 2: Edge Existence (HebbianLearner)**

Current bespoke code:

```
1. For each entity pair co-occurrence:
   a. Check if (source, target, type) exists in st_kg_edges
   b. If exists: increment observation_count, boost confidence
   c. If not: create new edge
```

Engine replacement:

```
1. For each entity pair co-occurrence:
   a. candidate = R4Adapter.edge_to_candidate(edge)
   b. result = await framework.decide(candidate)
      - M9.3 queries st_kg_edges with match_key = "source:target:type"
      - M9.7 EdgeIdentity: exact compound key match (score 1.0 or 0.0)
      - M9.4 framework: REINFORCE or CREATE
   c. If result.action == REINFORCE: framework returns StagedWrite(UPDATE)
   d. If result.action == CREATE: framework returns StagedWrite(INSERT)
```

**R4 components NOT migrated** (stay bespoke):

- UltraBERTEntityExtractor (NER extraction)
- EntityDisambiguator (mention -> entity mapping pre-step)
- EntityMerger (cascade merge)
- HebbianLearner co-occurrence discovery logic
- GrangerCausalityInference
- AdaptiveCausalityThresholds
- CausalEdgeFeedbackProcessor

Only the identity/existence check and write-decision routing move to the engine.

---

#### M9.8.11 R5 Migration: Dream Explorer (Detailed)

R5 currently has NO reconciliation. Dream outputs (insights, counterfactuals, routine optimizations) are staged as CREATE-only writes. M9.8 adds reconciliation so dream outputs can REINFORCE or EXTEND existing truth records.

**Current state**:

```
R5 produces:
  - Insights (BGT-SM) -> always INSERT new
  - Counterfactuals (CPN) -> always INSERT new
  - RoutineOptimizations (TDL-HCO) -> always INSERT new
  - ProspectiveMemories -> always INSERT new
```

**Engine addition**:

```
R5 produces candidates:
  - ProspectiveMemory -> framework.decide() against st_prospective
    If score >= 0.85 -> REINFORCE (same intention re-confirmed by dream)
    If score >= 0.60 -> EXTEND (dream adds detail to intention)
    If score < 0.60  -> CREATE (new intention from dream)

  - RoutineOptimization -> framework.decide() against st_procedural
    If score >= 0.80 -> REINFORCE (dream confirms existing routine)
    If score < 0.80  -> CREATE (new optimization)

  - Insights, Counterfactuals -> always CREATE (no identity matching)
    (Insights are inherently novel; counterfactuals are hypothetical)
```

R5 migration is the smallest scope because only 2 output types (prospective, procedural) benefit from reconciliation. Insights and counterfactuals remain CREATE-only.

---

#### M9.8.12 R6 Simplification: StagedWrite Collector

**Before M9.8** (current): R6 orchestrates 14 assemble methods in TruthWriteAssembler:

```
R6Coordinator calls:
  truth_assembler.assemble_epi_writes()
  truth_assembler.assemble_sem_writes()
  truth_assembler.assemble_procedural_writes()
  truth_assembler.assemble_social_writes()
  truth_assembler.assemble_prospective_writes()
  truth_assembler.assemble_insight_writes()
  truth_assembler.assemble_counterfactual_writes()
  truth_assembler.assemble_routine_optimization_writes()
  truth_assembler.assemble_mcts_writes()
  truth_assembler.assemble_intent_signal_writes()
  truth_assembler.assemble_learning_queue_writes()
  ... etc
```

**After M9.8** (engine active): R6 becomes a simple collector:

```
R6Coordinator:
  IF engine_active:
      # StagedWrites already produced by M9.5 WriteDecisionRouter in R2/R3/R4/R5
      # R6 just collects them from envelope.staged_writes
      all_writes = envelope.collect_staged_writes()
      # Add R6-specific writes that DON'T go through engine:
      all_writes.extend(status_marker.mark_events(envelope))
      all_writes.extend(outbox_assembler.assemble(envelope))
      # Validate
      manifest_validator.validate(all_writes)
      envelope.phases.r6_output = R6Output(writes=all_writes)
  ELSE:
      # Bespoke path: use TruthWriteAssembler (unchanged)
      all_writes = truth_assembler.assemble_all(...)
```

**What R6 still does** (not simplified):

- `ConsolidationStatusMarker`: marks events as CONSOLIDATED on st_hipp_events
- `OutboxEventAssembler`: stages outbox messages for R8
- `ManifestValidator`: validates write manifest completeness
- `SummaryGenerator`: pipeline metrics (NOT content summary)
- `IdempotencyKeyGenerator`: generates deterministic keys
- `DedupMetadataPopulator`: populates dedup metadata
- `ReconciliationRecorder`: records reconciliation decisions

**What R6 drops** (when engine active):

- `TruthWriteAssembler.assemble_epi_writes()` -> M9.5 already produced these
- `TruthWriteAssembler.assemble_sem_writes()` -> M9.5 already produced these
- `TruthWriteAssembler.assemble_procedural_writes()` -> M9.5 already produced these
- ... etc for all 14 assemble_* methods

The 14 assemble methods are NOT deleted -- they remain for the bespoke fallback path. Deletion happens in a future cleanup milestone after engine is stable in production.

---

#### M9.8.13 R7 and R8: Unchanged

**R7 (Truth Writer)**: Unchanged. R7 is a blind StagedWrite executor. It receives `List[StagedWrite]` from R6 and executes them atomically via UnitOfWork. The source of StagedWrites (bespoke assembler vs engine) is transparent to R7.

**R8 (Event Emitter)**: Unchanged. R8 maps reconciliation actions to bus event topics. The action names (CREATE, REINFORCE, EXTEND, EVOLVE, CONTRADICT) are the same regardless of whether bespoke or engine produced them.

---

#### M9.8.14 Migration Harness: DualPathRunner

**File**: `k0/modules/consolidation/reconciliation/migration.py`

```python
@dataclass
class DivergenceRecord:
    candidate_id: str
    bespoke_action: str
    engine_action: str
    bespoke_match_id: Optional[str]
    engine_match_id: Optional[str]
    bespoke_similarity: float
    engine_similarity: float
    phase: str
    layer: str

class DualPathRunner:
    """Runs bespoke and engine paths, compares, logs divergences."""

    async def run_dual(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
        bespoke_fn: Callable,
        engine_fn: Callable,
    ) -> Tuple[P03PhaseResult, List[DivergenceRecord]]:
        # Deep copy envelope for isolation
        envelope_bespoke = deepcopy(envelope)
        envelope_engine = deepcopy(envelope)

        bespoke_result = await bespoke_fn(envelope_bespoke, ctx)
        engine_result = await engine_fn(envelope_engine, ctx)

        divergences = self._compare(envelope_bespoke, envelope_engine)
        self._log_divergences(divergences)

        return bespoke_result, divergences

class DivergenceLogger:
    """Structured logging for migration divergences."""

    def log(self, divergences: List[DivergenceRecord]):
        for d in divergences:
            logger.info(
                "migration_divergence",
                extra={
                    "candidate_id": d.candidate_id,
                    "bespoke_action": d.bespoke_action,
                    "engine_action": d.engine_action,
                    "phase": d.phase,
                    "layer": d.layer,
                },
            )
```

---

#### M9.8.15 Migration Sequence: Phase-by-Phase Rollout

Phases are migrated in this order (simplest risk first):

| Order | Phase | Seams | Risk | Rationale |
|-------|-------|-------|------|-----------|
| 1 | R3 | 1 seam (ReconciliationEngine v1) | LOW | Already has feature flag pattern; closest to engine architecture; dedup/decay logic unchanged |
| 2 | R4 | 2 seams (entity + edge) | LOW-MEDIUM | EdgeIdentity is deterministic (zero risk); EntityIdentity is highest semantic complexity but isolated |
| 3 | R2-Seam1 | 1 seam (REINFORCE) | MEDIUM | Event-level matching; affects clustering pool size (matched events removed) |
| 4 | R2-Seam2 | 1 seam (EXTEND) | MEDIUM-HIGH | Episode-level matching; changes extend_target_episode_id assignments; directly affects R7 write path |
| 5 | R5 | 2 seams (prospective + procedural) | LOW | Currently no reconciliation; adding engine is additive, not replacing |
| 6 | R6 | Simplification | LOW | Collector pattern; bespoke fallback retained |

Per-phase rollout stages:

```
Stage 1: Unit tests pass (engine path produces valid output)
Stage 2: Dual-path mode enabled on dev environment (1 week)
         - Log divergences
         - Analyze divergence patterns
         - Fix any systematic mismatches
Stage 3: Engine enabled on 1-2 canary spaces (1-2 weeks)
         - Monitor episode counts, action distributions, latency
Stage 4: Engine enabled on 10% of spaces (2 weeks)
         - A/B test metrics within tolerance
Stage 5: Engine enabled on 100% of spaces
         - Mark bespoke path as deprecated
```

---

#### M9.8.16 Regression Test Suite

**File**: `tests/k0/pipelines/p03/test_migration_regression.py`

The regression suite runs the FULL P03 pipeline twice -- once with bespoke, once with engine -- and compares outputs at every phase boundary.

```
Test fixtures:
  - 300-event batch (same as whiteboard Section 2.2 example)
  - 260 existing episodes in st_epi
  - 500 patterns in st_sem
  - 2000 entities in st_kg_dom
  - 3000 edges in st_kg_edges

Test cases:

  test_r2_episode_count_parity():
      """Engine produces same episode count (+/- 5%)."""
      bespoke = run_pipeline(engine=False)
      engine = run_pipeline(engine=True)
      assert abs(bespoke.r2_cluster_count - engine.r2_cluster_count) / bespoke.r2_cluster_count < 0.05

  test_r2_extend_ratio_parity():
      """Engine produces same EXTEND ratio (+/- 3%)."""
      bespoke_extend = count(action == EXTEND for c in bespoke.r2_candidates)
      engine_extend = count(action == EXTEND for c in engine.r2_candidates)
      assert abs(bespoke_extend - engine_extend) / max(bespoke_extend, 1) < 0.03

  test_r3_action_distribution_parity():
      """Action distribution across 5 layers matches (+/- 5%)."""
      ...

  test_r4_entity_resolution_parity():
      """Same entities resolved to same canonical_name."""
      ...

  test_r7_staged_write_count_parity():
      """Total StagedWrites within 2% of bespoke."""
      ...

  test_r7_write_layer_distribution():
      """Per-layer write counts match."""
      ...

  test_phase_latency_acceptable():
      """Engine path latency < 1.5x bespoke path."""
      ...
```

---

#### M9.8.17 Output Contract Preservation

M9.8 MUST preserve these output contracts (consumed by downstream phases):

**R2 outputs consumed by R3**:

| Field | Type | Must Match |
|-------|------|-----------|
| `envelope.phases.r2_clusters` | `List[EpisodeCluster]` | Yes -- same EpisodeCluster structure |
| `envelope.phases.r2_noise_event_ids` | `List[str]` | Yes -- noise classification unchanged |
| `envelope.phases.r2_cluster_count` | `int` | Within 5% tolerance |
| `event.reconciliation_action` | `str` | Same action vocabulary (CREATE/EXTEND/REINFORCE) |
| `event.extend_target_episode_id` | `str` | Same episode IDs (if target exists) |
| `event.cluster_id` | `str` | Same cluster assignments (clustering is unchanged) |

**R3 outputs consumed by R4**:

| Field | Type | Must Match |
|-------|------|-----------|
| `event.reconciliation_action` | `str` | Same action vocabulary |
| `event.best_match_id` | `str` | Same truth record IDs |
| `event.best_match_layer` | `str` | Same layer names |
| `event.novelty_score` | `float` | Unchanged (dedup logic not migrated) |
| `event.is_duplicate` | `bool` | Unchanged |

**R6 outputs consumed by R7**:

| Field | Type | Must Match |
|-------|------|-----------|
| `staged_writes: List[StagedWrite]` | Each with layer, operation, record_data, idempotency_key | Same StagedWrite format |

The StagedWrite interface is the common denominator. Whether bespoke assembler or engine produces them, R7 executes them identically.

---

#### M9.8.18 Risk Matrix & Mitigation

| # | Risk | Severity | Impact | Mitigation |
|---|------|----------|--------|-----------|
| R1 | Episode count divergence | HIGH | R2 produces different episode count -> downstream metrics affected | Dual-path logging, 5% tolerance gate, rollback on breach |
| R2 | EXTEND target mismatch | HIGH | Engine assigns different extend_target_episode_id -> wrong episode updated in R7 | Compare extend assignments in dual-path, verify same target_id |
| R3 | R3 action distribution shift | MEDIUM | Engine assigns more CREATE, fewer REINFORCE -> truth table growth | Track per-action counts, alert on > 5% shift |
| R4 | Entity resolution regression | MEDIUM | EntityIdentity resolves differently than AmbiguousEntityResolver | Golden entity test set (known disambiguation cases) |
| R5 | Phase timeout | MEDIUM | Engine queries add latency, R2 exceeds 60s timeout | Pre-fetch existing episodes in R0, cache in envelope |
| R6 | Dual-path overhead | LOW | Running both paths doubles compute during testing | Only enable dual-path on dev/staging, not production |
| R7 | Partial engine failure | LOW | Engine fails for 1 candidate, corrupts batch | Fallback: if engine throws, use bespoke for entire batch |

**Rollback procedure**:

```
1. Set enable_engine_reconciliation = false in config
2. Restart affected P03 workers
3. All subsequent cycles use bespoke path
4. No data corruption: engine writes and bespoke writes are identical StagedWrite format
5. Investigate divergence logs, fix engine, re-enable
```

---

#### M9.8.19 What Gets Deprecated (But NOT Deleted)

After engine is stable at 100%, these files are marked deprecated:

| File | Status | When to Delete |
|------|--------|----------------|
| `k0/modules/consolidation/algorithms/cross_batch_extend.py` | DEPRECATED | M10+ (after 2 stable production months) |
| `k0/modules/consolidation/algorithms/same_thread_merge.py` | KEPT (not migrated) | Never -- stays in R2 |
| `k0/modules/consolidation/algorithms/reconciliation_engine.py` | DEPRECATED | M10+ (replaced by M9.4 framework) |
| `k0/modules/consolidation/algorithms/ambiguous_resolver.py` | DEPRECATED | M10+ (replaced by EntityIdentity) |
| `k0/modules/consolidation/staging/truth_write_assembler.py` | DEPRECATED (14 methods) | M10+ (replaced by M9.5 WriteDecisionRouter) |
| `k0/modules/consolidation/staging/truth_query_service.py` | DEPRECATED | M10+ (replaced by M9.3 syscall) |

Deprecated files get a docstring warning:

```python
"""
DEPRECATED: This module is replaced by the M9 Reconciliation Framework.
Retained as bespoke fallback during migration (M9.8).
Scheduled for removal: M10+
Do not add new features to this module.
"""
```

---

#### M9.8.20 Performance Budget

Engine path must meet these latency targets per phase:

| Phase | Bespoke Baseline | Engine Target | Hard Limit |
|-------|-----------------|---------------|-----------|
| R2 (episode matching) | ~15ms (50 episodes x cosine) | < 25ms | 50ms |
| R2 (cross-batch extend) | ~8ms (candidates x episodes) | < 15ms | 30ms |
| R3 (per-event reconciliation) | ~50ms (300 events x 5 layers) | < 80ms | 120ms |
| R4 (entity resolution) | ~20ms (40 entities x 5-priority) | < 30ms | 60ms |
| R4 (edge existence) | ~5ms (25 edges x key lookup) | < 8ms | 15ms |
| R5 (dream reconciliation) | 0ms (no reconciliation) | < 10ms | 20ms |
| R6 (assembly) | ~12ms (14 assemble methods) | < 5ms (collector only) | 10ms |

Total pipeline overhead: engine path should be < 1.2x bespoke path end-to-end.

Key optimization: M9.3's `truth_candidates_query` pre-fetches and caches existing truth records at the start of each phase. Subsequent `framework.decide()` calls hit the cache, not the database.

---

#### M9.8.21 StagedWrite Accumulation Pattern

When engine is active, StagedWrites are produced by M9.5 WriteDecisionRouter during R2/R3/R4/R5 and accumulated on the envelope:

```
R2.run():
    for result in framework.decide_batch(candidates):
        staged_write = write_router.route(result)
        envelope.staged_writes.append(staged_write)
        # Also run M9.6 hooks (recompute_centroid, regenerate_summary)

R3.run():
    for result in framework.decide_batch(candidates):
        staged_write = write_router.route(result)
        envelope.staged_writes.append(staged_write)

R4.run():
    for result in framework.decide_batch(candidates):
        staged_write = write_router.route(result)
        envelope.staged_writes.append(staged_write)

R5.run():
    for result in framework.decide_batch(candidates):
        staged_write = write_router.route(result)
        envelope.staged_writes.append(staged_write)

R6.run():
    all_writes = envelope.staged_writes  # Already accumulated from R2-R5
    all_writes.extend(status_marker.mark_events(envelope))
    all_writes.extend(outbox_assembler.assemble(envelope))
    manifest_validator.validate(all_writes)

R7.run():
    for write in all_writes:
        execute(write)  # Same as before
```

`envelope.staged_writes` is a new field on `P03BatchEnvelope` (added in M9.8). When engine is disabled, this list stays empty and R6 uses the bespoke TruthWriteAssembler path.

---

#### M9.8.22 Envelope Extension

**File**: `k0/pipelines/p03/envelope.py` (EDIT)

```python
@dataclass
class P03BatchEnvelope:
    # ... existing fields ...

    # M9.8: Engine-produced staged writes (accumulated during R2-R5)
    staged_writes: List[StagedWrite] = field(default_factory=list)

    def collect_staged_writes(self) -> List[StagedWrite]:
        """Return all accumulated writes. Called by R6 when engine is active."""
        return list(self.staged_writes)

    def append_staged_write(self, write: StagedWrite) -> None:
        """Append a write produced by the reconciliation engine."""
        self.staged_writes.append(write)
```

---

#### M9.8.23 Validation Criteria (Exit Gates)

| # | Criterion | How to Verify |
|---|----------|---------------|
| V1 | Dual-path mode produces identical bespoke output (engine path logged but not used) | `test_dual_path_bespoke_unchanged()` |
| V2 | Engine path populates all R2 output fields consumed by R3 | `test_r2_output_contract()` |
| V3 | Engine path populates all R3 output fields consumed by R4 | `test_r3_output_contract()` |
| V4 | R7 processes engine-produced StagedWrites without error | `test_r7_engine_writes()` |
| V5 | Episode count within 5% of bespoke baseline | `test_r2_episode_count_parity()` |
| V6 | Action distribution within 5% per phase | `test_action_distribution_parity()` |
| V7 | Phase latency within 1.5x of bespoke | `test_phase_latency_acceptable()` |
| V8 | Feature flag OFF = zero engine code executed | `test_feature_flag_off()` |
| V9 | Feature flag ON = zero bespoke reconciliation code executed | `test_feature_flag_on()` |
| V10 | Partial engine failure falls back to bespoke gracefully | `test_engine_failure_fallback()` |
| V11 | SameThreadMerger still runs in R2 with engine enabled | `test_same_thread_merge_preserved()` |
| V12 | Deprecated modules have docstring warnings | grep for DEPRECATED in bespoke files |

---

#### M9.8.24 What M9.8 Does NOT Do

| Out of Scope | Why | When |
|-------------|-----|------|
| Delete deprecated bespoke code | Need fallback during stabilization period | M10+ cleanup milestone |
| Retrain EpisodicIdentity model | Model is production-ready from POC | Future (if divergence analysis shows need) |
| Add new truth layers | M9.8 migrates existing 7 layers only | Future |
| Modify R7 or R8 | These phases are engine-agnostic (StagedWrite interface) | Never needed |
| Migrate SameThreadMerger | Intra-batch clustering optimization, not truth reconciliation | Never |
| Migrate ThreadPurityCorrector | Clustering quality, not truth identity | Never |
| Modify HDBSCAN or EpisodeSplitter | Clustering algorithms are orthogonal to reconciliation | Never |
| Production rollout | M9.8 delivers the code; rollout is ops decision with feature flags | Ops team |

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
