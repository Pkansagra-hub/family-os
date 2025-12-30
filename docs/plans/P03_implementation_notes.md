# P03 Consolidation Pipeline — Implementation Notes

> **Purpose**: Implementation planning notes extracted from P03_consolidation_dossier_v2.md
> **Created**: 2025-12-27
> **Dossier Version**: 2.3.0 (Production-Ready Draft)
> **Status**: In Progress — Reading dossier incrementally

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Core Philosophy & Reconciliation Engine](#3-core-philosophy--reconciliation-engine)
4. [Phase Specifications (R0-R8)](#4-phase-specifications-r0-r8)
5. [Learning Systems & Adaptive Parameters](#5-learning-systems--adaptive-parameters)
6. [Storage Schema Summary](#6-storage-schema-summary)
7. [Module Registry](#7-module-registry)
8. [Integration Contracts](#8-integration-contracts)
   - 8a. [Observability & Metrics](#8a-observability--metrics)
9. [Key Algorithms](#9-key-algorithms)
10. [Configuration Reference](#10-configuration-reference)
    - 10a. [Testing Strategy](#10a-testing-strategy)
    - 10b. [Migration & Evolution](#10b-migration--evolution)
11. [Implementation Priorities](#11-implementation-priorities)
12. [Policy Decisions & Feature Flags](#12-policy-decisions--feature-flags)
13. [Error Handling & DLQ](#13-error-handling--dlq)
14. [Security & Privacy](#14-security--privacy)
15. [Performance Tuning](#15-performance-tuning)
16. [Ops Readiness](#16-ops-readiness)
17. [Algorithm Specifications (Detailed)](#17-algorithm-specifications-detailed)
18. [Glossary](#18-glossary)
19. [K0 Kernel Integration Blueprint](#19-k0-kernel-integration-blueprint)
20. [Canonical Name Registry](#20-canonical-name-registry)
21. [Threshold Configuration](#21-threshold-configuration)
22. [State Machine Specification](#22-state-machine-specification)
23. [UltraBERT Model Specification](#23-ultrabert-model-specification)
24. [Open Questions & TODOs](#24-open-questions--todos)

---

## 1. Executive Summary

### 1.1 What is P03?

P03 is the **Memory Consolidation & Forgetting Pipeline** — an offline process that transforms raw episodic signals (from P02) into durable, queryable memory structures across 8 memory layers.

### 1.2 Core Paradigm Shift (v1 → v2)

| Aspect | v1 (Old) | v2 (New) |
|--------|----------|----------|
| **Data Flow** | One-way: P02 → Memory Layers | **Bidirectional**: New signals reconciled against existing truth |
| **Memory Model** | Overwrite existing | **Truth-first**: 8 layers are TRUTH, new signals are candidates |
| **Decision Making** | Simple insert | **Reconciliation**: REINFORCE / EXTEND / CREATE / EVOLVE / CONTRADICT / PRUNE |

### 1.3 Key Dependencies

| Dependency | Location | Relationship |
|------------|----------|--------------|
| P02 Write Pipeline | Upstream | Produces `st_hipp_events` |
| P08 Embedding Pipeline | Dependency | `embedding.search`, FAISS indexing |
| P06 Active Learning | Downstream | `gap.detected` events for ambiguity resolution |
| P04 Query Pipeline | Downstream | Consumes consolidated truth |

---

## 2. Architecture Overview

### 2.1 Pipeline Position in K0 Ecosystem

```
P02 (Memory Formation)
    │
    ▼ writes
st_hipp_events (Staging)
    │
    ▼ consolidation (offline)
P03 (Consolidation & Forgetting)
    │
    ▼ writes (bidirectional)
8 MEMORY LAYERS (TRUTH)
    │
    ├─▶ P04 (Query) — reads
    ├─▶ P05 (Proactive Triggers) — reads
    └─▶ P08 (Embedding Indexing) — indexes
```

### 2.2 The 8 Memory Layers (Truth)

| Layer | Brain Analog | Purpose | Default λ (decay) |
|-------|--------------|---------|-------------------|
| `st_epi` | Episodic Memory | Episodes, events | 0.005 (139-day half-life) |
| `st_sem` | Semantic Memory | Patterns, themes | 0.003 (231-day half-life) |
| `st_procedural` | Procedural Memory | Habits, routines | 0.010 (69-day half-life) |
| `st_social` | Social Memory | Relationships | 0.002 (347-day half-life) |
| `st_prospective` | Plans/Goals | Intentions, future | 0.020 (35-day half-life) |
| `st_kg_dom` | Concepts | KG Entities | 0.001 (693-day half-life) |
| `st_kg_edges` | Associations | KG Relationships | 0.008 (87-day half-life) |
| `st_vec` | Embeddings | Vector store | N/A |

### 2.3 Sleep Cycle Metaphor (Phases R0-R8)

| Phase | Sleep Stage | Brain Region | P03 Function |
|-------|-------------|--------------|--------------|
| R0 | Sleep Onset | Hypothalamus | Trigger detection, idle check |
| R1 | NREM1 | CA3 (Hippocampus) | Replay, importance scoring |
| R2 | NREM2 | CA1 → Neocortex | Episodic clustering, pattern extraction |
| R3 | SWS | Whole Brain | Synaptic homeostasis, forgetting |
| R4 | NREM2-3 | Temporal Cortex | KG consolidation |
| R5 | REM | Prefrontal Cortex | Dream-like exploration |
| R6 | Transition | Hippocampus | Staging table updates |
| R7 | Transition | Neocortex | Truth layer writes |
| R8 | Wake | Whole Brain | Event emission, completion |

---

## 3. Core Philosophy & Reconciliation Engine

### 3.1 Reconciliation Decision Types

| Decision | Condition | Action on Truth |
|----------|-----------|-----------------|
| **REINFORCE** | Similarity > 0.85 | Increment `observation_count`, boost confidence, reset decay |
| **EXTEND** | Similarity 0.60-0.85 | Append new details to existing record |
| **CREATE** | Similarity < 0.60, no conflict | INSERT new record with `is_canonical=1` |
| **EVOLVE** | Schema evolution detected | Create new version, mark old as `is_canonical=0` |
| **CONTRADICT** | Conflicting information | Flag for P06 Active Learning |
| **PRUNE** | Not reinforced for extended period | Apply decay, archive, tombstone |

### 3.2 Multi-Factor Similarity Computation

Default weights (static):

- Semantic (embedding cosine): **40%**
- SimHash (Hamming distance): **25%**
- Entity overlap (Jaccard): **15%**
- Temporal proximity: **10%**
- Spatial proximity: **10%**

**Per-Layer Weight Matrices** (learned):

| Layer | Semantic | SimHash | Entity | Temporal | Spatial |
|-------|----------|---------|--------|----------|---------|
| st_epi | 0.30 | 0.15 | 0.15 | **0.25** | **0.15** |
| st_sem | **0.50** | 0.20 | 0.15 | 0.10 | 0.05 |
| st_procedural | 0.25 | 0.15 | 0.20 | **0.30** | 0.10 |
| st_social | 0.35 | 0.10 | **0.35** | 0.10 | 0.10 |
| st_kg_dom | **0.45** | 0.25 | 0.15 | 0.10 | 0.05 |

### 3.3 Per-Entity-Type Thresholds

| Entity Type | REINFORCE (>) | EXTEND Range | CREATE (<) |
|-------------|---------------|--------------|------------|
| PERSON | 0.90 | 0.70-0.90 | 0.70 |
| FAMILY_MEMBER | 0.95 | 0.80-0.95 | 0.80 |
| PLACE | 0.80 | 0.55-0.80 | 0.55 |
| ORGANIZATION | 0.85 | 0.65-0.85 | 0.65 |
| CONCEPT | 0.70 | 0.45-0.70 | 0.45 |

---

## 4. Phase Specifications (R0-R8)

### 4.1 Phase Timing Constraints

| Phase | Target Duration | Max Duration | Abort Trigger |
|-------|-----------------|--------------|---------------|
| R0 | <1s | 5s | Lock contention |
| R1 | 10-30s | 60s | User activity |
| R2 | 30-120s | 300s | Memory pressure |
| R3 | 10-30s | 60s | — |
| R4 | 30-120s | 300s | — |
| R5 | 10-60s | 120s | Skip if backlog |
| R6 | 5-15s | 30s | — |
| R7 | 10-30s | 60s | Transaction timeout |
| R8 | <1s | 5s | — |

### 4.2 Phase Transitions (State Machine)

```
IDLE → R0 → R1 → R2 → R3 → R4 → R5 → R6 → R7 → R8 → COMPLETE → IDLE
                           ↓         ↓
                      (R6 shortcut if minimal work)

Any phase can → ABORT → IDLE
```

### 4.3 R1 — Hippocampal Replay

**Key Components**:

1. **Importance Scoring** — Weights: emotional (0.35), recency (0.25), frequency (0.20), social (0.20)
2. **Association Strengthening** — Hebbian learning for co-occurring entities
3. **Closed-Loop Learning** — Learn importance weights from K1 grounding feedback

**Cold Start**: Use static weights until 500 samples accumulated per space.

### 4.4 R2 — Neocortical Integration

**Key Components**:

1. **DBSCAN Clustering** — eps=0.25 (learned), min_samples=2 (learned)
2. **Pattern Extraction** — Routines, preferences, themes
3. **CA1 Bridge** — Query existing truth, make reconciliation decisions

**Adaptive Learning**: Silhouette score target > 0.5, adjust eps per space.

### 4.5 R3 — Synaptic Homeostasis (Forgetting)

**Key Components**:

1. **Per-Entity Access Tracking** — Min 5 accesses, 7-day spread for λ learning
2. **SimHash Deduplication** — Hamming distance ≤3 = near-duplicate
3. **Novelty Scoring** — First occurrence +0.15, milestone +0.20, rare +0.10
4. **Decay Lifecycle** — ACTIVE → ARCHIVED (decay <0.10) → TOMBSTONE (decay <0.01)

**Decay Immunity**: Family members, birthdays, home address never decay.

**Prune Regret Detection**: Track pruned entities 14 days, detect if queried (regret).

### 4.6 R4 — Knowledge Graph Consolidation

**Key Components**:

1. **Entity Extraction & Normalization** — UltraBERT NER
2. **Per-Entity-Type Disambiguation** — Learned embedding vs string weights
3. **Ambiguous Entity Resolution** — Priority: recent context > co-occurrence > location > temporal > frequency > P06

**Causality Threshold Learning** (Section 4.5.4.1):

- Per-category thresholds: Health/Medical (0.85), Financial (0.80), Social/Routine (0.70), Preference/Habit (0.65)
- Feedback signals: CAUSAL_PREDICTION_CONFIRMED, CAUSAL_PREDICTION_WRONG (+0.02), USER_REJECTS_CAUSATION (+0.05), MISSED_CAUSATION (-0.03)
- Bounds by category: Health (0.80-0.95), Financial (0.75-0.90), Social (0.60-0.80), Preference (0.55-0.75)

**Adaptive Observation Requirements** (Section 4.5.4.2):

- Daily patterns (>0.8/day): 10 observations required
- Weekly patterns (0.1-0.8/day): 5 observations required
- Monthly patterns (<0.1/day): 3 observations required
- Annual patterns (<0.01/day): 2 observations required
- Confidence formula: `confidence = base_confidence × sqrt(observations / min_required)`

**Confound Detection** (Section 4.5.4.3):

- **Common Cause Detection**: If entity C precedes both A and B in >50% of cases → demote to CORRELATED
- **Simpson's Paradox Detection**: If A→B globally but reverses in context subgroups → demote to CONTEXT_DEPENDENT
- Edge types: CAUSAL, CORRELATED, CONTEXT_DEPENDENT, HEBBIAN
- Context variables tracked: time_of_day, day_of_week, location, actor, mood

**Causal Edge Feedback Loop** (Section 4.5.4.4):

- Accuracy thresholds: >90% → boost confidence +0.05, 70-90% → maintain, <70% → demote to CORRELATED
- Usage tracking: last_used_at, usage_count, prediction_accuracy (30-day rolling)
- Staleness: Archive edges unused for 90 days
- Table: `st_causal_feedback` (edge_id, signal_type, source_system, created_at)

### 4.7 R5 — Dream-Like Exploration

**MVP Strategy** (Section 4.6.0):

- **Decision**: R5 disabled for MVP via `P03_FF_R5_MODE=disabled`
- Only TDL-HCO (motor rehearsal) enabled for MVP (~100ms, lightweight)
- Rollout plan: disabled → shadow (2-4 weeks) → enabled_low (10 rollouts) → enabled (full adaptive)

**MCTS Adaptive Rollouts** (Section 4.6.2.1):

- Entity merge/split: 100 rollouts
- Causal edge creation: 50 rollouts
- Episode cluster assignment: 30 rollouts
- Memory reinforcement: 20 rollouts
- Decay/novelty tuning: 10 rollouts
- Early termination: Clear winner (>90% visits) or low uncertainty (CI <5%)
- Compute budget: 1000 total rollouts per P03 cycle

**Exploration Constant** (Section 4.6.2.2):

- Keep static: c = √2 ≈ 1.414 (theoretically optimal UCT)
- Not learned per decision type — rollout count already adapts

**Shadow Mode Validation** (Section 4.6.5):

- Track heuristic vs MCTS decisions in `st_mcts_shadow_log`
- Comparison: If agreement >95% → keep disabled, if MCTS better >55% → enable
- Outcome scoring: MEMORY_GROUNDED (+0.3), USER_REJECTS (-0.5), ENTITY_SPLIT (-0.6)
- 7-day delay for outcome evaluation

**R5 Complexity Assessment**:

| Algorithm | Latency (P95) | MVP Alternative | Phase |
|-----------|---------------|-----------------|-------|
| CPN (Counterfactual) | ~300ms | Skip | Phase 2 |
| TPN-MCTS (Forward Sim) | ~500ms | 10 rollouts | Phase 2 |
| BGT-SM (Remote Assoc) | ~400ms | 3 walks | Phase 2 |
| SPC-UQ (Episodic Sim) | ~200ms | Skip | Phase 2 |
| TDL-HCO (Motor Rehearsal) | ~100ms | Keep | MVP |

---

## 5. Learning Systems & Adaptive Parameters

### 5.1 Learnable Parameters Summary

| Parameter | Scope | Default | Range | Learning Signal |
|-----------|-------|---------|-------|-----------------|
| `importance_weights` | space | [0.35,0.25,0.20,0.20] | — | K1 grounding feedback |
| `similarity_weights` | layer × space | see §3.2 | [0.05, 0.60] | Match used/rejected |
| `entity_thresholds` | entity_type × space | see §3.3 | varies | User merge/split actions |
| `dbscan_eps` | space | 0.25 | [0.15, 0.40] | Silhouette score |
| `decay_lambda` | entity × layer | varies | — | Prune regret signals |
| `novelty_bonuses` | space | [0.15,0.20,0.10] | [0.05, 0.30] | Grounding/rejection |
| `disambiguation_weights` | entity_type | 50/50 | [0.15, 0.85] | User corrections |

### 5.2 Thompson Sampling for Thresholds

**Model**: Beta-Bernoulli for REINFORCE and EXTEND_LOWER thresholds

**Priors**:

- REINFORCE: Beta(17, 3) → E[x] = 0.85
- EXTEND_LOWER: Beta(12, 8) → E[x] = 0.60

**Cold Start Phases**:

1. **Cold** (< 100 signals): Static defaults
2. **Warm** (100-500 signals): Thompson Sampling, wide exploration
3. **Hot** (> 500 signals): Thompson Sampling, exploitation focus

**Hierarchy**: Space-specific → Global → Static default

### 5.3 Golden Dataset Validation

**Weekly job** validates similarity formulas against curated dataset:

- 500+ known duplicate pairs
- 500+ known distinct pairs
- Target: Precision > 0.90, Recall > 0.85, F1 > 0.87
- Alert if F1 drops > 5% week-over-week (drift detection)

### 5.4 Storage: st_learned_weights

All learned parameters stored in `st_learned_weights` table with:

- `param_key`, `param_type`, `param_scope`
- `current_value`, `prior_value`, `confidence`, `sample_count`
- `last_updated_at`

---

## 6. Storage Schema Summary

> **Source**: `governance/k0/k0_architecture_master.md` Part 6 (Storage Tables Registry)
> **Backend**: PostgreSQL 16+ with asyncpg (NOT SQLite)
> **Migrations**: Alembic managed in `k0/db/alembic/`

### 6.1 CRITICAL: Storage Technology Notes

| Technology | Dossier Says | Actual K0 |
|------------|--------------|-----------|
| Database | SQLite | **PostgreSQL 16+** |
| Driver | sqlite3 | **asyncpg** (native async) |
| Connection Pool | - | **pgbouncer** |
| Embeddings | FAISS index | **pgvector** with HNSW |
| FTS | FTS5 (SQLite) | **tsvector + GIN** |
| Migrations | Manual | **Alembic** (25 migrations) |
| st_vec.vector | BLOB 768 floats | **pgvector VECTOR(768)** |

### 6.2 Key Tables (from k0_architecture_master.md Part 6)

| Table | Purpose | Key Columns | Indexes |
|-------|---------|-------------|---------|
| `st_hipp_events` | Staging (hippocampus) | embedding, simhash, entities_json, consolidation_status | btree(tenant_id,created_at), btree(consolidation_status) |
| `st_epi` | Episodic memory | episode_id, source_events_json, observation_count, decay_factor | btree(episode_id), btree(decay_factor) |
| `st_sem` | Semantic patterns | pattern_id, pattern_type, pattern_attributes_json, confidence_score | btree(pattern_type), btree(confidence_score) |
| `st_procedural` | Habits/routines | routine_id, action_sequence_json, temporal_anchor, regularity_score | btree(routine_id), btree(regularity_score) |
| `st_social` | Relationships | relationship_id, actor_a_id, actor_b_id, relationship_strength | btree(actor_a_id), btree(actor_b_id) |
| `st_prospective` | Intentions/goals | intention_id, intention_type, status, target_date | btree(status), btree(target_date) |
| `st_kg_dom` | KG entities | entity_id, entity_type, canonical_name, aliases_json, attributes_json | btree(entity_type), gin(aliases_json) |
| `st_kg_edges` | KG relationships | edge_id, source_entity_id, target_entity_id, relation_type, edge_weight | btree(source_entity_id), btree(target_entity_id) |
| `st_vec` | Embeddings (**pgvector**) | embedding_id, event_id, **vector VECTOR(768)** | **HNSW(vector)** m=16 ef=64 |
| `st_learned_weights` | Learned parameters | param_id, param_key, param_scope, scope_id, current_value | btree(param_key,param_scope) |
| `st_consolidation_audit` | Audit trail | decision_id, decision_type, outcome, feedback_envelope_id | btree(decision_type), btree(created_at) |
| `st_pruned_entities` | Regret tracking (14-day) | prune_id, entity_id, entity_type, canonical_name, **embedding VECTOR(768)** | btree(pruned_at), HNSW(embedding) |
| `st_golden_dataset_pairs` | Validation pairs | pair1_json, pair2_json, ground_truth | - |
| `st_feedback_signals` | Feedback from P21 | envelope_id, signal_type, consumed_at, consumed_by | btree(signal_type), btree(consumed_at) |
| `st_learning_queue` | Gap queue for P06 | gap_id, gap_type, entity_id, entropy_score, importance_score | btree(status), btree(importance_score DESC) |
| `st_anchors` | Bayesian beliefs | (entity_id, attribute, tenant_id) PK, alpha, beta, confidence | btree(entity_id,attribute) |
| `st_anchor_observations` | Evidence log | observation_id, entity_id, attribute, supports_anchor | btree(entity_id), btree(created_at) |
| `st_causal_feedback` | Causal edge feedback | feedback_id, edge_id, signal_type, source_system | btree(edge_id), btree(signal_type) |
| `st_mcts_shadow_log` | Shadow mode validation | decision_id, heuristic_choice, mcts_choice, choices_differ | btree(created_at), btree(choices_differ) |
| `st_mcts_decisions` | MCTS tracking | decision_id, decision_type, rollouts_allocated, early_termination | btree(decision_type), btree(created_at) |
| `st_offsets` | Pipeline checkpoints | (subscriber_id, topic, space_id, tenant_id) PK, offset | btree(subscriber_id,topic) |
| `st_pipeline_processed` | Event processing status | (pipeline_id, event_id) PK, status, duration_ms, error_kind | btree(pipeline_id,status) |
| `st_outbox` | Durable writes | id, wal_pos, driver, op_kind, payload, fingerprint, status | btree(status), btree(wal_pos) |
| `st_retention_policy` | Lifecycle management | policy_id, resource_type, privacy_band, retention_days | btree(resource_type,privacy_band) |

### 6.3 PostgreSQL-Specific Features Used

```sql
-- pgvector embedding storage (NOT BLOB)
CREATE TABLE st_vec (
    embedding_id UUID PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES st_hipp_events(event_id),
    vector VECTOR(768) NOT NULL,  -- pgvector native type
    created_at TIMESTAMPTZ DEFAULT now()
);

-- HNSW index for similarity search (NOT FAISS)
CREATE INDEX ix_st_vec_hnsw ON st_vec
    USING hnsw (vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- tsvector for FTS (NOT FTS5)
ALTER TABLE st_hipp_events ADD COLUMN content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX ix_hipp_events_fts ON st_hipp_events USING gin(content_tsv);

-- Common schema additions (across all memory tables)
access_count INTEGER DEFAULT 0,
last_accessed_at TIMESTAMPTZ,
decay_factor REAL DEFAULT 1.0,
decay_immune BOOLEAN DEFAULT FALSE,
version INTEGER DEFAULT 1,
is_canonical BOOLEAN DEFAULT TRUE,
supersedes_id UUID,
created_at TIMESTAMPTZ DEFAULT now(),
updated_at TIMESTAMPTZ DEFAULT now(),
source_pipeline TEXT
```

### 6.3 Extended Schema Details (from Sections 6.19-6.23)

**st_pruned_entities (6.19) - Prune Regret Tracking**:

- Purpose: Track pruned entities for 14-day regret detection window
- Key Columns: `prune_id`, `entity_id`, `entity_type`, `canonical_name`, `embedding` (pgvector), `decay_factor_at_prune`, `pruned_at`, `matched_at`
- Cleanup: Auto-delete after 14 days if not matched
- Metrics: `p03_prune_regret_rate`, `p03_prune_regret_confidence`

**st_consolidation_audit (6.20) - Decision Audit**:

- Purpose: Complete audit trail for explainability and debugging
- Key Columns: `audit_id`, `memory_id`, `source_table`, `action`, `formula_used`, `formula_version`, `inputs_json`, `outputs_json`, `explanation`, `confidence`, `decision_id`, `cycle_id`
- Retention: 90 days detailed → aggregate to daily summaries (2 years)
- RLS: Enforced for multi-tenant isolation

**st_feedback_quarantine (6.21) - Suspicious Signals**:

- Purpose: Quarantine adversarial/anomalous feedback for review
- Key Columns: `quarantine_id`, `signal_id`, `reason`, `severity`, `detected_at`, `auto_release_at`, `reviewed_at`, `reviewed_by`, `decision`
- Reasons: RATE_LIMIT, VELOCITY_SPIKE, ANOMALY, ENTROPY
- Auto-release: 48 hours if not manually reviewed

**st_decay_feedback (6.22) - Decay Rate Learning**:

- Purpose: Track access patterns for Bayesian lambda estimation
- Key Columns: `feedback_id`, `memory_id`, `layer`, `event_type`, `inter_access_interval`, `decay_factor_at_event`, `expected_decay`, `resurrection_needed`, `archival_premature`
- Event Types: ACCESS, RESURRECTION, ARCHIVE, TOMBSTONE
- Retention: 365 days rolling window (seasonal patterns)

**st_learned_weights_history (6.23) - Parameter Versioning**:

- Purpose: Maintain rollback history for learned parameters
- Key Columns: `history_id`, `param_id` (FK), `version`, `value`, `quality_at_time`, `applied_at`
- Retention: Last 10 versions per parameter
- Quality rollback: Trigger if quality drops >15% from recent average

---

## 7. Module Registry

> **Source**: `governance/k0/k0_architecture_master.md` Part 3 (Module Master Registry)
> **Location**: `k0/modules/consolidation/` (to be created for P03)

### 7.1 Existing K0 Modules (Available for P03 Reuse)

**From k0_architecture_master.md Part 3.1 - Modules P03 can invoke**:

| Module ID | Name | Location | Status | P03 Usage |
|-----------|------|----------|--------|-----------|
| M01 | SalienceScorer | `k0/modules/salience/` | ✅ Active | R1 importance input |
| M02 | IngestionClassifier | `k0/modules/context/` | ✅ Active | - |
| M04 | EntityResolver | `k0/modules/hippocampus/` | ✅ Active | R4 entity dedup |
| M07 | EmbeddingGenerator | `k0/modules/embedding/` | ✅ Active | - |
| M14 | SimilarityScorer | `k0/modules/salience/` | ✅ Active | R2, R3 similarity |
| M15 | HippEventsReader | `k0/modules/hippocampus/` | ✅ Active | R0 batch selection |
| M16 | HippEventsWriter | `k0/modules/hippocampus/` | ✅ Active | R6-R7 writes |
| M17 | OutboxEmitter | `k0/modules/core/` | ✅ Active | R8 event emission |
| M22 | UltraBERTCache | `k0/modules/embedding/` | ✅ Active | R4 NER embeddings |

**Deprecated Modules (DO NOT USE)**:

| Module ID | Name | Reason | Replacement |
|-----------|------|--------|-------------|
| M23 | EmbeddingVecWriter | ❌ Merged into M16 | Use M16 + `vec_write()` |
| M24 | FAISSIndexer | ❌ pgvector replaces | Native HNSW indexing |

### 7.2 P03-Specific Modules (To Be Created)

| Module ID | Name | Phase | Function | Location |
|-----------|------|-------|----------|----------|
| M30 | BatchSelector | R0 | Select pending events from st_hipp_events | `k0/modules/consolidation/batch_selector.py` |
| M31 | ImportanceScorer | R1 | Importance weighting (emotional, recency, novelty, social) | `k0/modules/consolidation/importance_scorer.py` |
| M32 | HebbianLearner | R1 | Hebbian strength updates for co-occurrence | `k0/modules/consolidation/hebbian_learner.py` |
| M33 | EpisodicClusterer | R2 | DBSCAN clustering by embedding similarity | `k0/modules/consolidation/episodic_clusterer.py` |
| M34 | EpisodeBuilder | R2 | Construct EpisodeCluster objects | `k0/modules/consolidation/episode_builder.py` |
| M35 | SimHashDeduplicator | R3 | SimHash deduplication and novelty scoring | `k0/modules/consolidation/simhash_deduplicator.py` |
| M36 | DecayScorer | R3 | Exponential decay calculation | `k0/modules/consolidation/decay_scorer.py` |
| M37 | PruneDecider | R3 | Archival/tombstone decisions | `k0/modules/consolidation/prune_decider.py` |
| M38 | EntityExtractor | R4 | UltraBERT-based NER extraction | `k0/modules/consolidation/entity_extractor.py` |
| M39 | RelationshipBuilder | R4 | Knowledge graph relationship creation | `k0/modules/consolidation/relationship_builder.py` |
| M40 | CausalInference | R4 | Temporal causal edge discovery | `k0/modules/consolidation/causal_inference.py` |
| M41 | Counterfactual | R5 | CPN counterfactual scenarios (Phase 2) | `k0/modules/consolidation/counterfactual.py` |
| M42 | ForwardSimulator | R5 | TPN-MCTS future simulation (Phase 2) | `k0/modules/consolidation/forward_simulator.py` |
| M43 | InsightGenerator | R5 | BGT-SM creative insights (Phase 2) | `k0/modules/consolidation/insight_generator.py` |
| M44 | StatusUpdater | R6 | Update consolidation_status on st_hipp_events | `k0/modules/consolidation/status_updater.py` |
| M45 | MemoryWriter | R7 | Write to memory layers via syscalls | `k0/modules/consolidation/memory_writer.py` |
| M46 | GapDetector | R8 | Active Learning gap detection for P06 | `k0/modules/consolidation/gap_detector.py` |
| M24 | TruthWriter | R7 | Memory layer write orchestration via outbox |
| M25 | GapDetector | R8 | Active Learning gap detection and emission |

### 7.3 Module Dependency Graph (Updated with K0 IDs)

```
                           ┌─────────────────────────────────────────┐
                           │     R0: BatchSelector (M30)             │
                           │     Syscalls: hipp_events_query()       │
                           └────────────────┬────────────────────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    ▼                       ▼                       ▼
    ┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐
    │ R1: ImportanceScorer  │  │ R1: HebbianLearner    │  │ Reuse: M01 Salience   │
    │ (M31)                 │  │ (M32)                 │  │ Scorer                │
    └───────────┬───────────┘  └───────────┬───────────┘  └───────────────────────┘
                │                          │
                └──────────┬───────────────┘
                           ▼
           ┌───────────────────────────────┐
           │ R2: EpisodicClusterer (M33)   │
           │ + EpisodeBuilder (M34)        │
           │ Syscalls: vec_query()         │
           └───────────────┬───────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ R3: SimHash   │  │ R3: Decay     │  │ R4: Entity    │
│ Deduplicator  │  │ Scorer (M36)  │  │ Extractor     │
│ (M35)         │  │               │  │ (M38)         │
│ Reuse: M14    │  │               │  │ Syscalls:     │
│               │  │               │  │ ultrabert_    │
│               │  │               │  │ embed()       │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        │                  ▼                  ▼
        │          ┌───────────────┐  ┌───────────────┐
        │          │ R3: Prune     │  │ R4: Relation  │
        │          │ Decider (M37) │  │ Builder (M39) │
        │          └───────────────┘  └───────┬───────┘
        │                                     │
        │                                     ▼
        │                             ┌───────────────┐
        │                             │ R4: Causal    │
        │                             │ Inference     │
        │                             │ (M40)         │
        │                             └───────┬───────┘
        │                                     │
        └──────────────┬──────────────────────┘
                       ▼
    ┌────────────────────────────────────────────────┐
    │ R5: Dream Phase (Phase 2)                      │
    │ Counterfactual(M41) + ForwardSim(M42) +        │
    │ InsightGen(M43) — DISABLED IN MVP              │
    └────────────────────────┬───────────────────────┘
                             ▼
           ┌─────────────────────────────────┐
           │ R6: StatusUpdater (M44)         │
           │ Syscalls: hipp_events_upsert()  │
           └─────────────────┬───────────────┘
                             ▼
           ┌─────────────────────────────────┐
           │ R7: MemoryWriter (M45)          │
           │ Syscalls: vec_write(),          │
           │ relationships_upsert()          │
           │ Reuse: M16, M17                 │
           └─────────────────┬───────────────┘
                             ▼
           ┌─────────────────────────────────┐
           │ R8: GapDetector (M46)           │
           │ Syscalls: outbox_emit_batch()   │
           │ Emit: p03.gap.detected.v1       │
           └─────────────────────────────────┘
```

### 7.4 Key Module Interfaces (Updated)

**M30 — BatchSelector**:

- Input: consolidation_status filter, batch_size limit
- Output: List[HippEvent] ready for consolidation
- Syscall: `hipp_events_query()` with capability `st_hipp_events.read`
- Filter: `consolidation_status = 'PENDING' AND embedding_status = 'READY'`

**M33 — EpisodicClusterer**:

- Input: List[HippEvent], Dict[event_id → embedding]
- Output: List[EpisodeCluster] with member_events, centroid_embedding, temporal_span, cluster_confidence
- Config: eps (0.3), min_samples (2), max_cluster_size (50), temporal_window_hours (4)
- Syscall: `vec_query()` with capability `st_vec.read` (pgvector HNSW)
- Confidence formula: mean pairwise cosine similarity within cluster

**M35 — SimHashDeduplicator**:

- Input: HippEvent, existing_hashes Dict[event_id → simhash]
- Output: DuplicationResult (is_duplicate, near_duplicates, novelty_score, duplicate_of)
- Novelty formula: `(1 - similarity_to_nearest) × (1 + first_time_bonus) × (1 + milestone_bonus) × (1 - routine_penalty)`
- Hamming threshold: 3 (near-duplicate)

**M36 — DecayScorer**:

- Input: TruthRecord, table name
- Output: RetentionDecision (current_decay, new_decay, action, reason)
- Actions: KEEP, DECAY, ARCHIVE, TOMBSTONE
- Decay formula: `decay_factor = exp(-λ × days_since_observation)`

**M38 — EntityExtractor**:

- Input: List[EpisodeCluster]
- Output: List[Entity] with canonical_name, entity_type, confidence
- Syscall: `ultrabert_embed()` with capability `ultrabert.call`
- Reuse: M22 UltraBERTCache for embedding lookup

**M39 — RelationshipBuilder**:

- Input: List[EpisodeCluster], extracted entities
- Output: List[KGUpdate] (CREATE_ENTITY, UPDATE_ENTITY, CREATE_EDGE, UPDATE_EDGE)
- Syscall: `relationships_upsert()` with capability `st_relationships.write`
- Relationship discovery: Hebbian co-occurrence with min 2 occurrences
- Confidence formula: `min(0.9, 0.3 + 0.1 × co_occurrence_count)`

**M31 — ImportanceScorer**:

- Importance formula: `I = w_e × emotional + w_r × recency + w_n × novelty + w_s × social`
- Default weights: emotional (0.35), recency (0.25), novelty (0.20), social (0.20)
- Batch selection: Over-sample 2× then sort by importance

**M46 — GapDetector**:

- Input: List[ReconciliationResult]
- Output: List[GapRecord] with gap_type, importance_score
- Syscall: `outbox_emit_batch()` with capability `st_outbox.write`
- Gap types: AMBIGUOUS_ENTITY, LOW_CONFIDENCE_EDGE, MISSING_ATTRIBUTE, CONTRADICTION, CONCEPT_DRIFT, STRUCTURAL_HOLE, STALE_ANCHOR
- Max gaps per cycle: 50

### 7.5 Reused K0 Modules

| K0 Module | Purpose in P03 | Phase | Syscalls Used |
|-----------|----------------|-------|---------------|
| M01 (SalienceScorer) | Input to importance calculation | R1 | - |
| M04 (EntityResolver) | Entity deduplication in KG | R4 | - |
| M14 (SimilarityScorer) | Cosine similarity for clustering | R2, R3 | vec_query() |
| M15 (HippEventsReader) | Read events from st_hipp_events | R0 | hipp_events_query() |
| M16 (HippEventsWriter) | Write updates to st_hipp_events | R6, R7 | hipp_events_upsert() |
| M17 (OutboxEmitter) | Durable event emission | R8 | outbox_emit_batch() |
| M22 (UltraBERTCache) | Embedding lookup/generation | R4 | ultrabert_embed() |

---

## 8. Integration Contracts

### 8.1 P02 → P03 Contract

**Input Table**: `st_hipp_events`

- Filter: `consolidation_status IS NULL OR consolidation_status = 'PENDING'` AND `embedding_status = 'READY'`
- Required fields: event_id, tenant_id, space_id, actor_id, content_hash, embedding_id, salience_score, policy_band, entities_json, triplets_json, created_at

**Event Trigger**: `p02.event.indexed.v1`

- Protocol: Kafka
- Topic: `familyos.p02.events`
- Partition key: `$.tenant_id`
- Payload: event_id, tenant_id, space_id, salience_score, embedding_status, indexed_at

### 8.2 P03 → P06 Contract (Active Learning)

**Overview**: P03 acts as the "Observer Brain" that detects knowledge gaps during consolidation. P06 is the "Curious Mind" that proactively seeks to fill those gaps through targeted questions.

**Gap Emission Event**: `p03.gap.detected.v1`

- Protocol: Kafka
- Topic: `familyos.p03.gaps`
- Partition key: `$.tenant_id`
- Payload: gap_id (ULID), tenant_id, space_id, actor_id (optional), gap_type, importance_score, context, ttl_hours (default 168), detected_at

**Gap Types Detected by P03**:

| Gap Type | Detection Phase | Trigger Condition | Priority |
|----------|-----------------|-------------------|----------|
| AMBIGUOUS_ENTITY | R4 | Multiple candidates, max confidence < 0.7 | HIGH |
| LOW_CONFIDENCE_EDGE | R4 | Relationship confidence < 0.6 | MEDIUM |
| MISSING_ATTRIBUTE | R4 | Ontology-required attribute NULL | MEDIUM |
| CONTRADICTION | R7 | Semantic conflict with existing truth | HIGH |
| CONCEPT_DRIFT | R3 | Anchor confidence shifted >20% in 30 days | LOW |
| STRUCTURAL_HOLE | R5 | Missing expected edge in KG | LOW |
| STALE_ANCHOR | Background Scan | Anchor not updated in 90+ days | LOW |

**Resolution Event** (P06 → P03): `p06.gap.resolved.v1`

- Topic: `familyos.p06.resolutions`
- Partition key: `$.gap_id`
- Resolution types: ANSWERED, DISMISSED, EXPIRED, SUPERSEDED

**Importance Score Formula**:

```
importance = entropy × (1 / (confidence + 0.1)) × recency_boost × type_weight
```

- Type weights: CONTRADICTION (1.5), AMBIGUOUS_ENTITY (1.3), MISSING_ATTRIBUTE (1.0), LOW_CONFIDENCE_EDGE (0.9), STALE_ANCHOR (0.5)

**Attention Budget (Token Bucket via P05)**:

- Query: actor_id → is_available, availability_score, next_available_at, rejection_reason
- Rejection reasons: DND_MODE, BUDGET_EXHAUSTED, RATE_LIMITED, OFFLINE

### 8.3 P03 → P08 Contract (Embedding Index)

**Embedding Creation Event**: `p03.embedding.created.v1`

- Topic: `familyos.p03.embeddings`
- Partition key: `$.tenant_id`
- Owner types: EPISODIC_CLUSTER, SEMANTIC_CONCEPT, ENTITY_NODE, PROCEDURAL_STEP
- Index priority: HIGH, NORMAL, LOW

**Coordination Modes**:

- SYNC: Wait for P08 ack (timeout 30s, retries 3)
- ASYNC: Fire-and-forget with batch flush (size 100, interval 5s)
- Circuit breaker: enabled, failure_threshold 5, reset_timeout 60s

### 8.4 P03 ↔ P21 Contract (Feedback Integration)

**P03 is CONSUMER of P21 feedback system**.

**Bus Subscription**: `feedback.signal.p03`

- Schema: P03FeedbackPayload (registered in P21 FeedbackSchemaRegistry)
- Consumption tracking: Update `st_feedback_signals.consumed_at`, `consumed_by='P03'`

**P03FeedbackPayload Fields**:

- feedback_type: SALIENCE_ADJUSTMENT, DECAY_REVERSAL, CLUSTER_CORRECTION, REINFORCEMENT_OUTCOME, NOVELTY_SIGNAL, REGRET_SIGNAL
- wal_positions: list[int]
- entity_id, cluster_id (optional)
- salience_delta (-1.0 to +1.0), importance_override (0-1), decay_lambda_delta
- was_retrieved, was_helpful, user_confirmed (bool)
- confidence (0-1, default 0.5)

**Signal-to-Learner Routing**:

| Signal Type | Learning Module | Parameter Updated |
|-------------|-----------------|-------------------|
| SALIENCE_ADJUSTMENT | ImportanceLearner | α_imp |
| DECAY_REVERSAL | DecayLearner | λ |
| CLUSTER_CORRECTION | SimilarityLearner | eps, similarity_weights |
| REINFORCEMENT_OUTCOME | HebbianLearner | association_strength |
| REGRET_SIGNAL | DecayLearner | decay_factor |

### 8.5 P03 Output Events

| Event | Topic | Description |
|-------|-------|-------------|
| `p03.memory.consolidated.v1` | familyos.p03.cycles | Cycle complete summary |
| `p03.gap.detected.v1` | familyos.p03.gaps | Knowledge gap for P06 |
| `p03.embedding.created.v1` | familyos.p03.embeddings | New embedding for P08 |

**Consolidation Complete Payload**:

- cycle_id, tenant_id, space_id, status (SUCCESS/PARTIAL/FAILED)
- summary: events_processed, clusters_created, duplicates_found, entities_created, edges_created, gaps_detected
- decisions: { reinforce, extend, create, evolve, prune, contradict }
- duration_ms, completed_at

---

## 8a. Observability & Metrics

### 8a.1 Cross-Space Leakage Detection

**Critical Security Requirement**: Monitor and prevent any cross-space data access in learning systems.

**Monitoring Strategy**:

1. Query Audit: Log all queries to learning tables, scan for missing `WHERE space_id`
2. Weekly automated scan for violations
3. Quarterly manual security review

**Critical Metrics**:

- `p03_cross_space_query_attempts` (Counter) — should always be 0
- `p03_rls_policy_blocks` (Counter)
- `p03_isolation_health` (Gauge) — 1 if no violations, 0 otherwise

### 8a.2 Learning Performance Metrics (< 5% Budget)

**Core Metrics**:

- `p03_learning_time_pct` (Gauge) — Target <5%
- `p03_learning_latency_ms` (Histogram) — by component, operation
- `p03_learning_queue_depth` (Gauge) — warning >500, critical >1000
- `p03_learning_queue_overflow` (Counter) — signals discarded
- `p03_learning_skip_count` (Counter) — skipped due to budget
- `p03_learning_parameter_updates` (Counter) — by param_key

**Alert Thresholds**:

| Metric | Warning | Critical |
|--------|---------|----------|
| learning_time_pct | >4% | >5% |
| learning_queue_depth | >500 | >1000 |
| learning_skip_count | >1/hour | >10/hour |
| learning_queue_overflow | >10/min | >50/min |

### 8a.3 Consolidation Cycle Metrics

- `p03_cycle_total` (Counter) — by tenant_id, status (success/failure/partial/aborted)
- `p03_cycle_duration_seconds` (Histogram) — by tenant_id, phase
- `p03_events_processed_total` (Counter) — by outcome (consolidated/duplicate/pruned)
- `p03_pending_events` (Gauge) — pending queue size
- `p03_phase_duration_seconds` (Histogram) — by phase (R0-R8)

### 8a.4 Decay Engine Metrics

- `p03_decay_total_active/archived/tombstoned` (Gauge) — per layer
- `p03_decay_resurrections_total` (Counter) — by trigger (QUERY/CO_OCCURRENCE/USER_MENTION)
- `p03_resurrection_rate` (Gauge) — per 1000 accesses, 7d rolling
- `p03_decay_immune_entities` (Gauge) — by layer, reason
- `p03_lambda_drift_30d` (Gauge) — max λ change over 30 days
- `p03_premature_archival_rate` (Gauge) — accessed within 7 days of archival

**Decay Alerts**: resurrection_rate >10% → λ too aggressive

### 8a.5 Shadow Mode Metrics

- `p03_shadow_executions_total` (Counter) — by learning_type, outcome
- `p03_shadow_agreement_rate` (Gauge) — % where old/new agree
- `p03_shadow_improvement_rate` (Gauge) — % where new is better
- `p03_shadow_regression_rate` (Gauge) — % where new is worse
- `p03_shadow_promotion_eligibility` (Gauge) — 0/1

### 8a.6 Distributed Tracing

**Span Hierarchy**:

```
p03.consolidation_cycle (root)
├── p03.r0.trigger_detection
├── p03.r1.replay
│   ├── p03.r1.batch_selection
│   └── p03.r1.importance_scoring
├── p03.r2.clustering
├── p03.r3.forgetting
├── p03.r4.kg_consolidation
├── p03.r5.dream_exploration (optional)
├── p03.r6.staging_update
├── p03.r7.truth_write
└── p03.r8.event_emission
```

**Required Baggage**: cycle_id, tenant_id, space_id, correlation_id

### 8a.7 Formula Debug Tracing

**Trace Levels**:

| Level | Audience | Content | Retention |
|-------|----------|---------|-----------|
| User | End users | Natural language explanation | 90 days |
| Ops | Support | Structured audit + decision path | 90 days |
| Debug | Developers | Full computation trace | 7 days |

**Sampling**: Default 1% of decisions; always trace errors, rollbacks, anomalies

---

## 9. Key Algorithms

### 9.1 Reconciliation Algorithm (Core)

```python
async def reconcile_signal_against_truth(signal, truth_layers, ctx):
    # 1. Query existing truth across all relevant layers
    truth_matches = await query_truth_for_signal(signal, truth_layers)

    # 2. Compute similarity to each match
    similarities = [(match, compute_similarity(signal, match)) for match in truth_matches]

    # 3. Determine decision based on best match
    if not similarities:
        return CREATE decision

    best_match, best_sim = max(similarities, key=lambda x: x[1])

    if best_sim > 0.85:
        return REINFORCE decision
    elif best_sim > 0.60:
        return EXTEND or EVOLVE decision
    else:
        if is_contradiction(signal, best_match):
            return CONTRADICT decision
        else:
            return CREATE decision
```

### 9.2 Importance Score Formula

```
importance = (
    0.35 × |sentiment| × |affect_valence| × (1 + affect_arousal)  # Emotional
  + 0.25 × exp(-0.05 × days_since_event)                          # Recency
  + 0.20 × log(1 + access_count) / log(10)                        # Frequency
  + 0.20 × participant_count × avg_relationship_strength          # Social
)
```

### 9.3 Decay Formula

```
decay_factor = exp(-λ × days_since_last_observed)

λ_effective = λ_base × space_modifier × entity_type_modifier × importance_modifier
```

### 9.4 Association Strength (Hebbian)

```
strength = (
    co_occurrence_count
  × exp(-0.01 × avg_time_gap_hours)
  × (unique_contexts / total_contexts)
  × (1 + avg_sentiment_score)
)
```

---

## 10. Configuration Reference

### 10.1 Key Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `P03_BATCH_SIZE` | 100 | Events per consolidation batch |
| `P03_SIMILARITY_REINFORCE_THRESHOLD` | 0.85 | Threshold for REINFORCE decision |
| `P03_SIMILARITY_EXTEND_THRESHOLD` | 0.60 | Lower threshold for EXTEND decision |
| `P03_DECAY_ARCHIVE_THRESHOLD` | 0.10 | Decay factor for ACTIVE → ARCHIVED |
| `P03_DECAY_TOMBSTONE_THRESHOLD` | 0.01 | Decay factor for ARCHIVED → TOMBSTONE |
| `P03_COLD_START_MIN_SAMPLES` | 500 | Samples before using learned weights |
| `P03_THOMPSON_SAMPLING_MOMENTUM` | 0.9 | Momentum for Beta parameter updates |
| `P03_PRUNE_REGRET_WINDOW_DAYS` | 14 | Days to track pruned entities |
| `P03_GOLDEN_DATASET_PRECISION_TARGET` | 0.90 | Precision target for validation |
| `P03_GOLDEN_DATASET_RECALL_TARGET` | 0.85 | Recall target for validation |

### 10.2 Causality & Causal Edge Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `P03_CAUSALITY_THRESHOLD_HEALTH` | 0.85 | Causality threshold for health/medical |
| `P03_CAUSALITY_THRESHOLD_FINANCIAL` | 0.80 | Causality threshold for financial |
| `P03_CAUSALITY_THRESHOLD_SOCIAL` | 0.70 | Causality threshold for social/routine |
| `P03_CAUSALITY_THRESHOLD_PREFERENCE` | 0.65 | Causality threshold for preference/habit |
| `P03_CAUSALITY_MIN_OBS_DAILY` | 10 | Min observations for daily patterns |
| `P03_CAUSALITY_MIN_OBS_WEEKLY` | 5 | Min observations for weekly patterns |
| `P03_CAUSALITY_MIN_OBS_MONTHLY` | 3 | Min observations for monthly patterns |
| `P03_CAUSALITY_MIN_OBS_ANNUAL` | 2 | Min observations for annual patterns |
| `P03_CONFOUND_DETECTION_ENABLED` | TRUE | Enable confound checking |
| `P03_CONFOUND_COMMON_CAUSE_THRESHOLD` | 0.50 | >50% precedence = confounder |
| `P03_CAUSAL_ACCURACY_BOOST_THRESHOLD` | 0.90 | Boost confidence above this |
| `P03_CAUSAL_ACCURACY_DEMOTE_THRESHOLD` | 0.70 | Demote below this |
| `P03_CAUSAL_STALENESS_DAYS` | 90 | Archive if unused |
| `P03_CAUSAL_FEEDBACK_WINDOW_DAYS` | 30 | Accuracy computation window |

### 10.3 R5 (MCTS) Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `P03_FF_R5_MODE` | disabled | R5 mode: disabled/shadow/enabled_low/enabled |
| `P03_MCTS_COMPUTE_BUDGET` | 1000 | Max rollouts per cycle |
| `P03_MCTS_EARLY_TERM_VISIT_THRESHOLD` | 0.90 | 90% visits → terminate |
| `P03_MCTS_EARLY_TERM_CI_THRESHOLD` | 0.05 | 5% CI width → terminate |
| `P03_MCTS_MIN_ROLLOUTS` | 10 | Always do at least 10 |
| `P03_MCTS_UCT_EXPLORATION_CONSTANT` | 1.414 | √2, static |
| `P03_SHADOW_EVALUATION_WINDOW_DAYS` | 30 | Evaluation period |
| `P03_SHADOW_OUTCOME_DELAY_DAYS` | 7 | Wait 7 days before scoring outcome |
| `P03_SHADOW_AGREEMENT_THRESHOLD` | 0.95 | 95% agreement → not useful |
| `P03_SHADOW_BETTER_THRESHOLD` | 0.55 | 55% better → enable |

### 10.4 Per-Layer Decay Constants (λ)

| Layer | λ | Half-Life (days) |
|-------|---|------------------|
| st_hipp_events | 0.100 | 7 |
| st_epi | 0.005 | 139 |
| st_sem | 0.003 | 231 |
| st_procedural | 0.010 | 69 |
| st_social | 0.002 | 347 |
| st_kg_dom | 0.001 | 693 |
| st_kg_edges | 0.008 | 87 |
| st_prospective | 0.020 | 35 |

---

## 10a. Testing Strategy

### 10a.1 Test Architecture (Pyramid)

```
              ┌─────────────────┐
              │   E2E Tests     │  ← Full cycle, real DB (5-10 tests)
              └────────┬────────┘
         ┌─────────────┴─────────────┐
         │    Integration Tests      │  ← Phase combinations (50-100)
         └─────────────┬─────────────┘
    ┌──────────────────┴──────────────────┐
    │          Contract Tests             │  ← Schema validation (20-30)
    └──────────────────┬──────────────────┘
┌──────────────────────┴──────────────────────┐
│              Unit Tests                      │  ← Algorithms (200-500)
└─────────────────────────────────────────────┘
```

### 10a.2 Unit Test Categories

| Category | Examples | Target Coverage |
|----------|----------|-----------------|
| Algorithm | DBSCAN clustering, SimHash, importance scoring | 95% |
| Decision Logic | REINFORCE/EXTEND/CREATE/CONTRADICT decisions | 100% |
| Decay Computation | Per-layer λ, access slowing | 95% |
| Threshold Learning | Thompson Sampling, cold start | 90% |

### 10a.3 Integration Test Focus

**End-to-End Consolidation Cycle**:

- 100 events with 5 patterns → verify st_sem has 5 patterns
- Entity extraction → verify KG nodes/edges created
- Observation counts incremented correctly

**Bidirectional Reconciliation**:

- Reinforcing signal boosts confidence
- Contradiction emits gap to P06

**Phase Transitions**:

- R1 → R2: High-importance events selected
- R3: Duplicates removed before R4

### 10a.4 Contract Tests

**Event Schema Validation**:

- GapDetectedPayload: gap_type enum, required fields
- EmbeddingCreatedPayload: owner_type enum
- MemoryConsolidatedPayload: status enum

**Database Schema**:

- Verify all required columns exist
- Verify RLS policies active

### 10a.5 Performance Tests

| Test | Target | Metric |
|------|--------|--------|
| Throughput | 1000 events/min | events_per_minute |
| Large Batch | <5 min for 10K events | cycle_duration |
| Peak Memory | <500MB | peak_memory_mb |
| Streaming | No OOM for 100K events | memory_stable |

### 10a.6 Golden Dataset Validation

**Weekly Job** (Sunday 3 AM):

- Dataset: 500+ duplicate pairs, 500+ distinct pairs
- Targets: Precision >0.90, Recall >0.85, F1 >0.87
- Drift alert: F1 drops >5% week-over-week
- Auto-augment from user corrections (confidence >0.9)

---

## 10b. Migration & Evolution

### 10b.1 v1 → v2 Schema Migrations

| Migration | Description | Est. Duration |
|-----------|-------------|---------------|
| P03_001 | Add reconciliation columns to st_hipp_events | 5 min |
| P03_002 | Create st_learning_queue table | 1 min |
| P03_003 | Create st_anchors table | 1 min |
| P03_004 | Add observation_count columns | 10 min |
| P03_005 | Backfill observation_count from patterns | 60 min |

### 10b.2 Evolution Roadmap

| Version | Timeline | Features |
|---------|----------|----------|
| v2.0 | Q1 2025 | 8-phase pipeline, bidirectional truth, gap detection |
| v2.5 | Q2 2025 | Enhanced Dream (CPN/TPN-MCTS), creative insights |
| v3.0 | Q3 2025 | Multi-tenant, distributed, partitioned, auto-scaling |

---

## 11. Implementation Priorities

### 11.1 Phase 1: Core Reconciliation Engine

1. [ ] Implement `ReconciliationEngine` with REINFORCE/EXTEND/CREATE/PRUNE
2. [ ] Implement multi-factor similarity computation
3. [ ] Implement per-layer weight matrices (static first, then learned)
4. [ ] Implement phase state machine (R0-R8)

### 11.2 Phase 2: Learning Systems

1. [ ] Implement `st_learned_weights` table and access patterns
2. [ ] Implement Thompson Sampling for thresholds
3. [ ] Implement cold start strategy (3-level fallback)
4. [ ] Implement golden dataset validation (weekly job)

### 11.3 Phase 3: Decay & Forgetting

1. [ ] Implement `UnifiedDecayEngine` with per-layer λ
2. [ ] Implement access tracking for per-entity λ learning
3. [ ] Implement decay immunity for core entities
4. [ ] Implement prune regret detection (14-day window)

### 11.4 Phase 4: Active Learning Integration (P06)

1. [ ] Implement CONTRADICT detection and P06 event emission
2. [ ] Implement ambiguous entity resolution with P06 fallback
3. [ ] Implement gap detection during reconciliation

---

## 12. Policy Decisions & Feature Flags

### 12.1 Resolved Design Decisions

| Decision | Policy | Default | Feature Flag |
|----------|--------|---------|--------------|
| **Q1: CONTRADICT Handling** | CONTRADICT proceeds with reduced confidence, does NOT block P03 | `blocking_mode: false` | `P03_FF_CONTRADICT_BLOCKING` |
| **Q2: Gap Queue Max Depth** | Stop gap detection when st_learning_queue > threshold | `max_depth: 500` | `P03_GAP_QUEUE_MAX_DEPTH` |
| **Q3: Anchor Drift** | Multi-modal anchor tracking with explicit conflict markers | `drift_mode: multimodal` | `P03_FF_ANCHOR_DRIFT_MODE` |
| **Q4: R5 Dream Execution** | R5 runs conditionally based on backlog and time constraints | `execution_mode: conditional` | `P03_FF_R5_MODE` |

### 12.2 Feature Flag Master List

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `P03_FF_CONTRADICT_BLOCKING` | bool | `false` | Block on unresolved contradictions |
| `P03_FF_ANCHOR_DRIFT_MODE` | enum | `multimodal` | Anchor drift handling strategy |
| `P03_FF_R5_MODE` | enum | `conditional` | Dream phase execution: `always`, `conditional`, `disabled` |
| `P03_FF_GAP_DETECTION_ENABLED` | bool | `true` | Enable P06 gap detection |
| `P03_FF_SIMHASH_DEDUP_ENABLED` | bool | `true` | Enable near-duplicate detection |
| `P03_FF_GRANGER_CAUSALITY_ENABLED` | bool | `true` | Enable causal inference in R4 |
| `P03_FF_OPTIMISTIC_LOCKING` | bool | `true` | Use optimistic locking for writes |
| `P03_FF_ADAPTIVE_BATCHING` | bool | `true` | Adjust batch size based on load |
| `P03_FF_OBSERVABILITY_VERBOSE` | bool | `false` | Emit detailed phase-level metrics |
| `P03_FF_LEARNING_ENABLED` | bool | `false` | Master switch for all learning |
| `P03_FF_IMPORTANCE_LEARNING` | enum | `disabled` | `disabled`, `shadow`, `enabled` |
| `P03_FF_HEBBIAN_LEARNING` | enum | `disabled` | `disabled`, `shadow`, `enabled` |
| `P03_FF_DECAY_LEARNING` | enum | `disabled` | `disabled`, `shadow`, `enabled` |
| `P03_FF_SIMILARITY_LEARNING` | enum | `disabled` | `disabled`, `shadow`, `enabled` |
| `P03_FF_THRESHOLD_LEARNING` | enum | `disabled` | `disabled`, `shadow`, `enabled` |

### 12.3 Shadow Mode Specification

**Purpose**: Safe testing of new learning formulas without risking production data.

| Flag Value | Behavior |
|------------|----------|
| `disabled` | Only baseline formula runs (no learning) |
| `shadow` | Both run, only baseline applies (safe testing) |
| `enabled` | Only new formula runs (learning active) |

**Promotion Criteria** (from shadow → enabled):

- Agreement rate > 80%
- Improvement rate > Regression rate
- Shadow duration ≥ 7 days
- Sample size ≥ 1000 decisions
- No critical errors (0 exceptions)

### 12.4 Environment-Specific Defaults

| Environment | R5_MODE | OBSERVABILITY_VERBOSE | ADAPTIVE_BATCHING |
|-------------|---------|----------------------|-------------------|
| Development | `disabled` | `true` | `false` |
| Staging | `conditional` | `true` | `true` |
| Production | `conditional` | `false` | `true` |
| Load Test | `disabled` | `false` | `true` |

### 12.5 Formula Canary Rollout

| Phase | Duration | % of Spaces | Criteria to Advance |
|-------|----------|-------------|---------------------|
| 0. Shadow | 7 days | 0% | Comparison metrics look good |
| 1. Canary | 7 days | 5% | No regressions detected |
| 2. Gradual | 14 days | 25→50→75% | Metrics continue to improve |
| 3. Full | Permanent | 100% | All metrics stable |

**Halt Criteria** (automatic rollback):

- Any metric regresses > 10% → immediate halt
- User corrections spike > 3× baseline → halt + alert
- Error rate > 5% → immediate rollback
- Regret signal rate doubles → halt learning

---

## 13. Error Handling & DLQ

### 13.1 Error Classification

| Error Type | Severity | Retry Strategy | K0 Component |
|------------|----------|----------------|--------------|
| **TRANSIENT** | Low | Yes (exponential backoff) | RetryScheduler |
| **VALIDATION** | Medium | No (DLQ) | DLQStore |
| **LOGIC** | High | No (DLQ + alert) | DLQ + ObsEmitter |
| **FATAL** | Critical | No (abort cycle) | Circuit Breaker |

### 13.2 K0 DLQ Integration

- **DLQStore**: `k0/storage/dlq.py` → `record()`, `list_pending()`, `mark_requeued()`
- **RetryScheduler**: `k0/outbox/scheduler.py` → exponential backoff with jitter
- **Idempotency Keys**: Per-phase format for safe replay

| Phase | Idempotency Key Format |
|-------|----------------------|
| R0 | `p03:cycle:{cycle_ulid}` |
| R1-R5 | `p03:{phase}:{cycle_ulid}:{batch_hash}` |
| R6 | `p03:staging:{cycle_ulid}:{event_id}` |
| R7 | `p03:write:{cycle_ulid}:{table}:{record_id}` |
| R8 | `p03:emit:{cycle_ulid}:{topic}:{offset}` |

### 13.3 Circuit Breaker (P08 Coordination)

| Parameter | Default | Config Key |
|-----------|---------|------------|
| Failure threshold | 5 | `p03.circuit_breaker.failure_threshold` |
| Success threshold | 3 | `p03.circuit_breaker.success_threshold` |
| Timeout seconds | 30 | `p03.circuit_breaker.timeout_seconds` |
| Half-open attempts | 1 | `p03.circuit_breaker.half_open_attempts` |

**States**: CLOSED → OPEN (after 5 failures) → HALF_OPEN (after 60s) → CLOSED (after 3 successes)

### 13.4 Partial Failure Strategies

| Strategy | Behavior | Use When |
|----------|----------|----------|
| **COMMIT_PARTIAL** (default) | Commit successes, DLQ failures | Normal operation |
| **ROLLBACK_ALL** | Rollback entire batch | Ordering critical |
| **QUARANTINE_BATCH** | Move batch to DLQ, advance offset | Failure rate > 20% |

### 13.5 Edge Case Handling

| Edge Case | Detection | Handling | Metric |
|-----------|-----------|----------|--------|
| Empty st_hipp_events (>24h) | Scheduled health check | Emit `p03.health.idle.v1` | `p03_idle_cycles_total` |
| Corrupted embeddings | Dimension/NaN check | Skip, flag for re-embedding | `p03_corrupted_embeddings_total` |
| Partial R7 write failure | Transaction rollback | COMMIT_PARTIAL → DLQ | `p03_partial_write_failures_total` |
| Backlog > 10K | Batch selector overflow | Adaptive batching | `p03_backlog_overflow_total` |
| P08 circuit open > 5min | Circuit breaker duration | Queue locally | `p03_p08_circuit_open_seconds` |
| FAISS unavailable | Index load failure | Brute-force fallback | `p03_faiss_fallback_total` |
| Memory pressure in R5 | Heap > 80% | Skip R5 | `p03_r5_memory_skipped_total` |
| KG entity explosion (>1M) | Node count threshold | Partition by space_id | `p03_kg_partition_events_total` |

### 13.6 Recovery Procedures

**Manual DLQ Recovery**:

```bash
k0ctl dlq list --pipeline p03_consolidation --status PENDING
k0ctl dlq get <dlq_id> --verbose
k0ctl dlq requeue <dlq_id>
k0ctl dlq requeue-all --pipeline p03_consolidation --max-items 100
```

**Backlog Recovery**:

1. Increase batch size: `k0ctl config set p03.batch.size 2000`
2. Enable parallel cycles: `k0ctl config set p03.parallel_cycles 2`
3. Skip R5 temporarily: `k0ctl feature set P03_FF_R5_MODE disabled`
4. Monitor: `k0ctl metrics watch p03_events_processed_per_second`
5. Restore defaults after backlog < 1000

### 13.7 Parameter & Formula Rollback

**Parameter Rollback**: st_learned_weights stores last 10 versions per parameter.

- Rollback speed: Instant (single UPDATE)
- Trigger: Parameter drift > 20% in 24h, or quality metric drops > 10%

**Formula Rollback**: Feature flag controls formula version.

- Rollback speed: ~60 seconds (flag propagation)
- Trigger: Bug discovery, regression > 10%
- Formula version registry: importance (v2), hebbian (v2), decay (v3), similarity (v2)

---

## 14. Security & Privacy

### 14.1 K0 Policy Engine Integration

- **PEP Syscall**: `k0/policy/pep_syscall.py` → `evaluate_envelope()`, `_lookup_band()`
- **PolicyStamp**: Attached to each event, contains privacy band
- **Redaction**: `k0/policy/redact.py` → applied before KG ingestion

### 14.2 Privacy Band Enforcement

| Band | Cross-Event Linking | Cross-Actor Linking | KG Entities | Location Precision |
|------|---------------------|---------------------|-------------|-------------------|
| **GREEN** | Yes | Yes | Full | Full |
| **AMBER** | Yes | Same actor only | Anonymized | City (~10km) |
| **RED** | Self only | No | No | Country |

**Rule**: RED events cannot link to anything else; AMBER events link only within same actor.

### 14.3 Tenant Isolation (K0 ACL)

- **Mandatory**: Every P03 query MUST include `WHERE tenant_id = :tenant_id`
- **RLS**: PostgreSQL Row Level Security enforced at database level
- **K0 ACL Enforcer**: `k0/policy/acl_enforcer.py` → `check_permission()`

### 14.4 Location Privacy

- **K0 Integration**: `k0/policy/location_privacy.py`
- **Geohash Precision by Band**:
  - GREEN: precision 8 (~40m)
  - AMBER: precision 4 (~39km)
  - RED: precision 1 (~5000km)

### 14.5 GDPR Erasure Handling

**Erasure Request Cascade**:

1. Mark st_hipp_events as TOMBSTONE where actor_id matches
2. Cascade to all truth tables (st_epi, st_sem, etc.)
3. Remove from st_vec (embedding deletion)
4. Request FAISS index rebuild from P08
5. Update st_kg_dom and st_kg_edges (anonymize or delete)
6. Log in K0 audit trail (ObservabilityEmitter)
7. Record in K0 WAL for compliance

### 14.6 Learning Data Isolation

**Absolute Isolation Rule**: No cross-space learning leakage.

| Data Type | Isolation Level | Mechanism |
|-----------|-----------------|-----------|
| Learned weights | Per-space | space_id column + RLS |
| Feedback signals | Per-space | space_id column + RLS |
| Audit records | Per-space | space_id column + RLS |

**Principle**: Each space learns independently. No shared priors. Static defaults only from code configuration.

### 14.7 Memory Decision Explanations

**User-Facing Templates**:

| Decision | Template |
|----------|----------|
| REINFORCE | "This memory was reinforced because you mentioned {entity} frequently this week." |
| DECAY | "This memory faded because it hasn't been accessed in {N} days." |
| ARCHIVE | "This memory was archived to make room for more recent information." |
| MERGE | "These two memories were combined because they refer to the same {entity_type}." |
| CREATE | "A new memory was created for {entity} based on your conversation." |

---

## 15. Performance Tuning

### 15.1 K0 QoS Integration

- **Scheduler**: `k0/qos/scheduler.py` → acquire token before batch processing
- **QoSContext**: `k0/qos/context.py` → consume `fanout_budget`, `top_k_budget`
- **Budget Defaults**: fanout_budget=1000, top_k_budget=500

### 15.2 Performance Baselines

| Phase | Target P50 | Target P95 | Target P99 |
|-------|------------|------------|------------|
| R0 (Batch Select) | 10ms | 50ms | 100ms |
| R1 (Importance/Hebbian) | 20ms | 100ms | 200ms |
| R2 (Episode Clustering) | 50ms | 200ms | 500ms |
| R3 (Dedup/Decay/Prune) | 30ms | 150ms | 300ms |
| R4 (KG/Entity/Causal) | 100ms | 300ms | 600ms |
| R5 (Dream - if enabled) | 200ms | 500ms | 1000ms |
| R6 (Status Update) | 10ms | 30ms | 50ms |
| R7 (Truth Write) | 50ms | 150ms | 300ms |
| R8 (Event Emit) | 5ms | 20ms | 50ms |
| **Full Cycle** | 500ms | 1500ms | 3000ms |

### 15.3 Batch Size Optimization

| Factor | Small (100) | Medium (1000) | Large (10000) |
|--------|-------------|---------------|---------------|
| Latency | Low (~5s) | Medium (~30s) | High (~5min) |
| Memory | Low (~50MB) | Medium (~200MB) | High (~1GB) |
| Throughput | Low | Optimal | Diminishing returns |
| Recovery | Fast | Moderate | Slow |

### 15.4 PostgreSQL Configuration (K0)

- **Connection Pool**: min=5, max=25 (asyncpg via pgbouncer)
- **Session Settings**: statement_timeout=300s, lock_timeout=30s, work_mem=256MB
- **K0 Integration**: `k0/config/postgres.py` → PostgresSettings

### 15.5 Learning Compute Budget

**Rule**: Learning operations use < 5% of P03 consolidation cycle time.

| Component | % of Budget | Absolute Target |
|-----------|-------------|-----------------|
| Feedback ingestion | 20% | < 10ms per signal |
| Parameter update | 30% | < 50ms per update |
| Quality monitoring | 30% | < 100ms per cycle |
| Audit logging | 20% | < 20ms per record |

### 15.6 Memory Management

- **Streaming**: Process events in batches of 100, release memory after each batch
- **Embedding Cache**: LRU cache with max 10,000 entries, 1-hour TTL
- **Memory Thresholds**: warning=256MB, throttle=384MB, critical=480MB

---

## 16. Ops Readiness

### 16.1 Service Level Objectives (SLOs)

**Availability**:

| SLO ID | Metric | Target |
|--------|--------|--------|
| SLO-P03-001 | Cycle success rate | ≥ 99.5% |
| SLO-P03-002 | Event processing success | ≥ 99.9% |
| SLO-P03-003 | Scheduled trigger reliability | ≥ 99.9% |

**Latency**:

| SLO ID | Metric | P95 Target | P99 Target |
|--------|--------|------------|------------|
| SLO-P03-010 | Full cycle duration | ≤ 180s | ≤ 300s |
| SLO-P03-011 | R7 truth write latency | ≤ 200ms | ≤ 500ms |
| SLO-P03-012 | R8 event emission | ≤ 50ms | ≤ 100ms |

### 16.2 Critical Alerts (Page On-Call)

| Alert | Condition | Runbook |
|-------|-----------|---------|
| P03CycleFailureHigh | failure rate > 10% in 15m | RB-P03-001 |
| P03TruthWriteFailure | R7 write failures > 0 | RB-P03-002 |
| P03DLQOverflow | DLQ depth > 1000 | RB-P03-003 |
| P03CircuitBreakerOpen | state == OPEN | RB-P03-004 |
| P03SLOBurnRateFast | burn rate > 14.4 | RB-P03-005 |

### 16.3 Warning Alerts (Ticket)

| Alert | Condition | Runbook |
|-------|-----------|---------|
| P03PendingEventBacklog | pending > 10000 | RB-P03-010 |
| P03CycleLatencyHigh | P95 duration > 300s | RB-P03-011 |
| P03GapQueueHigh | gap queue > 400 | RB-P03-012 |
| P03R5SkipRateHigh | skip rate > 50% | RB-P03-013 |
| P03ImportanceWeightDrift | drift > 30% | RB-P03-016 |

### 16.4 Dashboard Panels (Grafana)

**P03 Operations Overview** (`p03-ops-overview`):

- Row 1: Cycle Success Rate, Events Pending, Last Cycle Timestamp, Active Errors
- Row 2: Cycle Duration Histogram, Events per Cycle, Decision Distribution
- Row 3: Phase Durations (stacked), Phase Errors (heatmap), R5 Skip Rate
- Row 4: Episodes Created, Patterns Discovered, KG Updates, Gaps Detected
- Row 5: DLQ Depth, Error Rate by Type, Retry Success Rate

### 16.5 Key Runbooks

| Runbook | Title | Trigger |
|---------|-------|---------|
| RB-P03-001 | High Cycle Failure Rate | P03CycleFailureHigh |
| RB-P03-002 | R7 Truth Write Failure | P03TruthWriteFailure |
| RB-P03-003 | DLQ Overflow | P03DLQOverflow |
| RB-P03-010 | Pending Event Backlog | P03PendingEventBacklog |
| RB-P03-011 | High Cycle Latency | P03CycleLatencyHigh |

### 16.6 Automatic Rollback Triggers

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Memory retrieval accuracy drop | >15% in 24h | Rollback parameters |
| User corrections spike | >3× baseline | Alert + manual review |
| Processing time increase | >2× baseline | Rollback formula |
| Error rate spike | >5% | Immediate halt |
| Regret signal spike | >5× baseline | Rollback decay params |

**Evaluation Frequency**: Every 15 minutes
**Cooldown Period**: 24 hours after rollback

---

## 17. Algorithm Specifications (Detailed)

### 17.1 Cosine Similarity (R4/R6 Reconciliation)

**Purpose**: Determine if new experience is repetition of known pattern or something new.

**Formula**: `cos(θ) = (A · B) / (||A|| × ||B||)`

For L2-normalized vectors (P08 UltraBERT): `cos(θ) = A · B` (dot product)

**Decision Mapping**:

| Score | Action | Effect |
|-------|--------|--------|
| ≥ 0.85 | REINFORCE | Update observation_count, confidence |
| 0.60 - 0.85 | EXTEND | Add attributes, expand pattern |
| < 0.30 | CONTRADICT | Flag conflict, may create alternative |
| else | CREATE | Insert new st_sem record |

### 17.2 Bayesian Confidence Updating (R7)

**Purpose**: Model "trust" in a memory. Repeated observations increase confidence.

**Core Formula**: `confidence = √(frequency × consistency × significance)`

**Components**:

- **Frequency Factor**: `log(1 + obs_count) / log(1 + expected_count)` — Logarithmic to prevent runaway
- **Consistency Factor**: `1.0 - std_dev(observations)` — Low variance = high trust
- **Significance Factor**: `0.5 + 0.5 × max(|affect|, importance)` — Emotional enhancement

**Config** (from `p03.reconciliation.confidence`):

- boost_per_observation: 0.05
- decay_per_day: 0.001
- min_for_canonical: 0.50
- consistency_weight: 0.4
- frequency_weight: 0.3
- significance_weight: 0.3

### 17.3 Optimistic Locking (R7 Truth Writes)

**Purpose**: Ensures data integrity when multiple consolidation workers update same memory.

**SQL Pattern**:

```sql
UPDATE {table}
SET field1 = :val1, version = version + 1
WHERE id = :id AND version = :expected_version
```

- If `rows_affected == 0`: Another worker updated first → retry
- **Retry Config**: MAX_RETRY_ATTEMPTS = 3, RETRY_BACKOFF_MS = [100, 500, 2000]

### 17.4 Importance Scoring (R1 Hippocampal Replay)

**Purpose**: Prioritizes high-emotion or high-novelty events over mundane background noise.

**Formula**: `importance = (emotional_intensity + novelty × novelty_weight + social × social_weight) × event_type_multiplier`

**Default Weights**:

- sentiment_weight: 0.25
- affect_weight: 0.30
- novelty_weight: 0.25
- social_weight: 0.20

**Event Type Multipliers**:

- "message": 1.0
- "photo": 1.2 (visual memories weighted higher)
- "milestone": 2.0 (birthdays, anniversaries)
- "routine": 0.5 (daily repeated events)

**Adaptive Weight Learning**: Online gradient descent with momentum=0.9, lr=0.01, minimum 500 samples before learning.

**Stability Controls**:

- Momentum smoothing: `velocity_t = 0.9 × velocity_{t-1} + ∇L_t`
- Weight clamping: `w_i = max(0.05, min(0.60, w_i))`
- Rollback: If training loss increases 3 consecutive nights → rollback to static weights

### 17.5 Hebbian Learning (R1 Co-occurrence)

**Purpose**: "Neurons that fire together, wire together" — strengthen connections between co-occurring entities.

**Update Formula**:

```
delta = learning_rate × (max_weight - current_weight) × event_importance
new_weight = current_weight + delta
```

**Decay Formula**: `new_weight = weight × exp(-decay_rate × days_since_update)`

**Anti-Hebbian Decay** (for wrong associations):

```
Δw = -anti_lr × current_weight × confidence × penalty_multiplier
anti_lr = 0.15 (faster than positive learning)
```

**Edge Resurrection** (archived edges reappearing):

```
new_weight = max(0.7, 0.5 + old_weight × 0.5)
resurrection_count += 1
```

**Adaptive Learning Rate** (based on relationship maturity):

- New edges (1-5 co-occurrences): LR = 0.25-0.30
- Emerging (6-15): LR = 0.15-0.20
- Established (16-50): LR = 0.08-0.12
- Mature (50+): LR = 0.05 (minimum)

### 17.6 DBSCAN Episodic Clustering (R2)

**Purpose**: Group scattered events into coherent "episodes."

**Composite Distance**: `distance = (1 - temporal_weight) × semantic_dist + temporal_weight × temporal_dist`

**Parameters**:

- eps: 0.25 (max distance between points)
- min_samples: 2-5 (adaptive based on singleton rate)
- temporal_weight: 0.3
- max_temporal_gap_hours: 4.0

**Pre-Clustering Episode Split** (before DBSCAN):

1. Location Change: geohash prefix differs by >4 chars → split
2. Activity Change: activity_type changes → split
3. Time Gap: >30 minutes → split
4. Hard Limit: >4 hours → force split

**Adaptive Min_samples**:

- Singleton rate >20% → increase min_samples +1 (max 5)
- Singleton rate <5% → decrease min_samples -1 (min 2)

### 17.7 SimHash Deduplication (R3)

**Purpose**: Fast near-duplicate detection using 64-bit locality-sensitive hashing.

**Algorithm**: Tokenize → hash shingles → accumulate bit sums → final hash

**Hamming Threshold** (by content type):

| Content Type | Threshold | Rationale |
|--------------|-----------|-----------|
| TRANSACTION | 1 | Financial exactness |
| CALENDAR_EVENT | 2 | Structured |
| CHAT_MESSAGE | 3 | Default |
| JOURNAL_ENTRY | 4 | Free-form |
| VOICE_MEMO | 5 | Transcription noise |

**Two-Stage Deduplication**:

1. Stage 1: SimHash filter (fast, O(n))
2. Stage 2: Embedding verification (accurate, O(k) where k ≈ 0.01n)

**Scale Strategy** (MinHash LSH for >50K events): O(log n) lookup

### 17.8 Exponential Decay (R3 Memory Fading)

**Purpose**: Biological forgetting — unused memories fade and are eventually archived.

**Formula**: `decay_factor = exp(-λ × days_since_last_observed)`

**Effective λ Calculation**:

```
effective_λ = base_λ × importance_factor × confidence_factor × reinforcement_factor
```

**Bayesian Lambda Estimation** (per-entity learning):

- Prior: `λ ~ Gamma(α=2, β=2/λ_base)` (per entity-type)
- Posterior: `λ | data ~ Gamma(α + n, β + Σ intervals)`
- CI Width <20%: Use learned λ directly
- CI Width 20-50%: Blend 50/50 with default
- CI Width >50%: Use default

**Lambda Fallback Hierarchy**:

1. Per-entity λ (if 5+ accesses)
2. Per-entity-type λ (space-specific)
3. Global entity-type λ (from DECAY_CONFIGS)
4. Layer default λ

**Memory Resurrection**:

```
new_decay = max(0.7, 0.5 + old_decay × 0.5)
```

- Triggers: QUERY, CO_OCCURRENCE, USER_MENTION

### 17.9 Query-to-Pruned Matching (R3 Regret Detection)

**Purpose**: Check if P04 query matches recently pruned entities.

**Two-Stage Matching**:

1. Name Match (Fuzzy): Levenshtein + token overlap, threshold >0.70
2. Semantic Match: Embedding cosine, threshold >0.75

**Decision Matrix**:

| Name Score | Embedding Score | Decision | Confidence |
|------------|-----------------|----------|------------|
| >0.70 | >0.75 | STRONG_MATCH | 0.90 |
| >0.70 | 0.60-0.75 | LIKELY_MATCH | 0.70 |
| <0.70 | >0.85 | SEMANTIC_MATCH | 0.85 |

**Context Boosts**: Same space (+0.10), Same actor (+0.05)

### 17.10 Regret Signal Processing

**Purpose**: Adjust decay parameters when regret detected.

**Actions by Match Type**:

- STRONG_MATCH (0.90 confidence): Lower λ by 10%
- LIKELY_MATCH (0.70): Lower λ by 5%, flag for review
- SEMANTIC_MATCH (0.85): Lower λ by 8%
- Multiple same type (0.95): Alert + lower λ by 15%

**Rate Limits**: Max 10 regrets per entity-type per day

### 17.11 Novelty Scoring (R4)

**Formula**: `novelty = 1.0 - (duplicate_count / window_count)`

**Milestone Detection** (3-layer):

1. NER: Extract temporal entities ("birthday", "anniversary")
2. Ontology Match: Cross-reference with st_kg_dom
3. Recurrence Detection: Same date ±3 days in previous years

**Milestone Bonus**: +0.20 to novelty for confirmed milestones

### 17.12 Granger Causality (R4 Temporal Inference)

**Purpose**: Distinguish correlation from causation in routines.

**Precedence Ratio**: `a_before_b / (a_before_b + b_before_a + simultaneous)`

**Thresholds**:

- Ratio ≥ 0.75: A CAUSES B (high confidence)
- Ratio ≤ 0.25: B CAUSES A
- 0.25 < Ratio < 0.75: No causal inference (correlation only)

### 17.13 Active Learning Algorithms (P06 Integration)

**Shannon Entropy** (uncertainty quantification):

```
H(X) = -Σ p(x) × log2(p(x))
```

- Normalized to [0, 1] by dividing by max entropy

**Beta Distribution** (confidence modeling):

```
Beta(α, β) where α = confirmations + 1, β = contradictions + 1
Mean = α / (α + β)
```

**Token Bucket** (rate limiting):

- bucket_size: 5 (max burst)
- refill_rate: 1/hour
- Each question consumes 1 token

### 17.14 Dream Phase Algorithms (R5)

**CPN (Causal Perturbation Network)**: Generate "what if" scenarios by perturbing past events.

**TPN-MCTS (Temporal Projection)**: Monte Carlo Tree Search for personal future scenarios.

- UCT formula: `UCT = Q/N + c × sqrt(ln(N_parent) / N)`
- EXPLORATION_CONSTANT: 1.414 (sqrt(2))
- MAX_ROLLOUT_DEPTH: 30 days
- DPP sampling for diversity

**BGT-SM (Bisociative Graph Traversal)**: Discover surprising connections via random walks + PMI scoring.

- RESTART_PROBABILITY: 0.15
- WALK_STEPS: 1000
- PMI_THRESHOLD: 3.0 (high = surprising)

**TDL-HCO (Temporal Difference Learning)**: Learn value functions for routine optimization.

- TD(0) update: `V(s) ← V(s) + α × (r + γ × V(s') - V(s))`
- DISCOUNT_FACTOR (γ): 0.99
- LEARNING_RATE (α): 0.1

### 17.15 Supplementary Algorithms

**Exponential Backoff** (retry scheduling):

- delay = min(cap, base × 2^attempt) + jitter
- BASE_DELAY_MS: 100
- MAX_DELAY_MS: 64000
- MAX_RETRIES: 6

**Weighted Fair Queuing** (multi-tenant scheduling):

- vtime_finish = vtime_start + (cost / weight)
- Higher weight = lower finish time = earlier service

---

## 18. Glossary

| Term | Definition |
|------|------------|
| **Anchor Point** | Bayesian belief about user attribute (preferences, values), modeled as Beta distribution |
| **Concept Drift** | Change in underlying data distribution over time (e.g., user preferences shifting) |
| **Entropy Score** | Measure of uncertainty/randomness; higher = more curious |
| **Gap Record** | Record in st_learning_queue representing missing/ambiguous information |
| **Reconciliation** | Process of comparing new signals against existing truth to determine action |
| **SimHash** | Locality-sensitive hash producing similar fingerprints for similar text |
| **Tombstone** | Soft-deleted record kept for audit/recovery; eventually garbage collected |
| **Truth Layer** | One of 8 long-term memory tables representing consolidated knowledge |
| **UltraBERT** | FamilyOS's custom 768-dim embedding model for semantic representation |
| **CPN** | Causal Perturbation Network — counterfactual "what if" scenario generation |
| **TPN-MCTS** | Temporal Projection Network with Monte Carlo Tree Search — forward simulation |
| **BGT-SM** | Bisociative Graph Traversal with Surprise Maximization — insight generation |
| **TDL-HCO** | Temporal Difference Learning for Habit Chain Optimization — routine learning |
| **DPP** | Determinantal Point Process — diversity sampling for scenario generation |
| **LSH** | Locality-Sensitive Hashing — sub-linear similarity search |
| **MinHash** | Min-wise independent permutations for Jaccard similarity estimation |
| **PMI** | Pointwise Mutual Information — measures association strength |
| **WFQ** | Weighted Fair Queuing — multi-tenant scheduling algorithm |

---

## 19. K0 Kernel Integration Blueprint

> **Source Documents**:
> - Architecture Diagram: `architecture_diagrams/k0/k0_source_of_truth_postgresql.mmd`
> - Architecture Master: `governance/k0/k0_architecture_master.md`

### 19.1 CRITICAL: Deprecated Items (Dossier vs Reality)

**The dossier references several deprecated/changed items. This section maps dossier references to actual K0 implementation:**

| Dossier Reference | Status | Actual K0 Implementation |
|-------------------|--------|--------------------------|
| `st_vec` + FAISS indexing | ⚠️ **FAISS Deprecated** | `st_vec` uses **pgvector HNSW** (native PostgreSQL) |
| FTS5 (SQLite) | ❌ **Removed** | **tsvector + GIN** indexes (PostgreSQL native) |
| SQLite backend | ❌ **Removed** | **PostgreSQL 16+ / asyncpg** only |
| `st_embedding_queue` | ⚠️ **Deprecated** | Inline embedding via M22 (UltraBERT cache) |
| `faiss.read`, `faiss.write` syscalls | ⚠️ **pgvector replaces** | `vec_query()`, `vec_write()` via pgvector |
| M23 (EmbeddingVecWriter) | ❌ **Deprecated** | Merged into M16 (HippEventsWriter) |
| M24 (FAISSIndexer) | ⚠️ **pgvector replaces** | pgvector HNSW handles indexing natively |
| `st_hipp_store` | ❌ **Dropped** | Use `st_hipp_events` via `hipp_events_upsert()` |

### 19.2 K0 Layer Stack Overview (Actual)

| Layer | Name | P03 Integration Point | K0 Location |
|-------|------|----------------------|-------------|
| Layer 0 | Client Interfaces | No direct integration | `k0/ports/` |
| Layer 1 | Kernel Ports | `/k0/consolidate.trigger` admin endpoint | `k0/ports/command.py` |
| Layer 2 | Gate & Policy | Inherit PolicyStamp from source events | `k0/gate/`, `k0/policy/` |
| Layer 3 | Transaction Coordination | UnitOfWork for atomic multi-table writes | `k0/uow/unit_of_work.py` |
| Layer 4 | Storage Core | st_hipp_events, st_vec (pgvector), st_outbox | `k0/storage/`, `k0/db/` |
| Layer 5 | QoS & Scheduling | Scheduler token for batch processing | `k0/qos/`, `k0/scheduler/` |
| Layer 6 | Event Bus | Subscribe `p02.write.complete.v1`, emit `p03.*.v1` | `k0/bus/core.py` |
| Layer 6.5 | Capability Mesh | Register/invoke capabilities via Fabric | `k0/fabric/fabric.py` |
| Layer 7 | Query Drivers | **pgvector** for similarity, tsvector for FTS | `k0/drivers/pgvector.py` |
| Layer 10 | Infrastructure | PipelineScheduler trigger registration | `k0/kernel/app.py` |

### 19.3 Key K0 Components (with paths)

| Component | Location | Purpose |
|-----------|----------|---------|
| **BusDispatcher** | `k0/bus/core.py` | Subscribe to topics via `dispatcher.subscribe(topic, handler)` |
| **CapabilityFabric** | `k0/fabric/fabric.py` | Request/reply by capability name |
| **PipelineRunner** | `k0/runtime/pipeline_runner.py` | Generic DAG executor for YAML-declared pipelines |
| **ModuleRegistry** | `k0/runtime/module_registry.py` | Lookup modules by `module_id:version` |
| **PipelineScheduler** | `k0/scheduler/scheduler.py` | Declarative triggers (INTERVAL, THRESHOLD, MANUAL) |
| **Syscalls** | `k0/kernel/syscalls.py` | Capability-gated storage access (2623 lines) |
| **UnitOfWork** | `k0/uow/unit_of_work.py` | Native async PostgreSQL transactions |
| **PostgresDriver** | `k0/drivers/postgres.py` | asyncpg native async driver |
| **PgVectorDriver** | `k0/drivers/pgvector.py` | pgvector HNSW for similarity search |

### 19.3 Pipeline Contract Structure

**P03_CONSOLIDATE (Batch Mode)**:

- Entry: `p03.consolidation.trigger.v1`
- Exit: `p03.consolidation.complete.v1`
- Concurrency: 1 (single consolidation cycle)
- Required caps: 15+ storage capabilities

**Triggers**:

- INTERVAL: Every 90 minutes (5400 seconds)
- THRESHOLD: 500+ pending events in st_hipp_events
- MANUAL: Admin/debug trigger via API

### 19.4 DAG Stage Mapping

| Stage ID | Module | Phase | Dependencies |
|----------|--------|-------|--------------|
| stage_00_select_batch | consolidation.batch_selector:v1 | R0 | [] |
| stage_10_importance_score | consolidation.importance_scorer:v1 | R1 | [00] |
| stage_11_hebbian_update | consolidation.hebbian_learner:v1 | R1 | [00] |
| stage_20_episodic_cluster | consolidation.episodic_clusterer:v1 | R2 | [10,11] |
| stage_21_episode_builder | consolidation.episode_builder:v1 | R2 | [20] |
| stage_30_simhash_dedup | consolidation.simhash_deduplicator:v1 | R3 | [21] |
| stage_31_decay_scorer | consolidation.decay_scorer:v1 | R3 | [21] |
| stage_32_prune_decider | consolidation.prune_decider:v1 | R3 | [30,31] |
| stage_40_entity_extractor | consolidation.entity_extractor:v1 | R4 | [21] |
| stage_41_relationship_builder | consolidation.relationship_builder:v1 | R4 | [40] |
| stage_42_causal_inference | consolidation.causal_inference:v1 | R4 | [41] |
| stage_50_counterfactual | consolidation.counterfactual:v1 | R5 | [42] |
| stage_51_forward_sim | consolidation.forward_simulator:v1 | R5 | [42] |
| stage_52_insight_gen | consolidation.insight_generator:v1 | R5 | [42] |
| stage_60_status_update | consolidation.status_updater:v1 | R6 | [32,52] |
| stage_70_memory_writer | consolidation.memory_writer:v1 | R7 | [60] |
| stage_80_event_emitter | core.event_emitter:v1 | R8 | [70] |

### 19.5 Parallel Execution Groups

- **Level 0**: stage_00 (sequential)
- **Level 1 (parallel)**: stage_10, stage_11
- **Level 2**: stage_20
- **Level 3**: stage_21
- **Level 4 (parallel)**: stage_30, stage_31, stage_40
- **Level 5 (parallel)**: stage_32, stage_41
- **Level 6**: stage_42
- **Level 7 (parallel R5)**: stage_50, stage_51, stage_52
- **Level 8+**: stage_60, stage_70, stage_80 (sequential)

### 19.6 Implementation Roadmap

**Phase 1 (Week 1-2)**: Foundation

- Pipeline contract `p03_consolidation.v1.yaml`
- Module directory `k0/modules/consolidation/`
- Core modules: batch_selector, importance_scorer, episodic_clusterer, episode_builder

**Phase 2 (Week 3-4)**: Core Reconciliation

- R3 modules: simhash_deduplicator, decay_scorer, prune_decider
- R4 modules: entity_extractor, relationship_builder, causal_inference

**Phase 3 (Week 5-6)**: Dream Phase

- R5 modules: counterfactual, forward_simulator, insight_generator (P1 priority)

**Phase 4 (Week 7-8)**: Finalization

- R6/R7/R8: status_updater, memory_writer, event_emitter
- Integration testing, performance profiling, documentation

---

## 20. Canonical Name Registry

> **Source**: `k0/kernel/syscalls.py`, `governance/k0/k0_architecture_master.md` Part 7

### 20.1 Pipeline Identifiers

| Canonical ID | Version | Status | Description |
|--------------|---------|--------|-------------|
| P03_CONSOLIDATE | v1 | 🎯 Planning | Batch memory consolidation |
| P03_INCREMENTAL | v1 | 📋 Future | Event-driven incremental |

### 20.2 K0 Syscalls Required for P03

**From `k0/kernel/syscalls.py` - Capability-Gated Storage Access**:

| Syscall | Required Capability | P03 Usage | Status |
|---------|---------------------|-----------|--------|
| `hipp_events_query()` | `st_hipp_events.read` | R0: Select batch by status | ✅ Active |
| `hipp_events_upsert()` | `st_hipp_events.write` | R6-R7: Update consolidated events | ✅ Active |
| `pipeline_processed_upsert()` | `st_pipeline_processed.write` | Track processing status | ✅ Active |
| `vec_query()` | `st_vec.read` | R2: Similarity search for clustering | ✅ Active (pgvector) |
| `vec_write()` | `st_vec.write` | R7: Write consolidated embeddings | ✅ Active (pgvector) |
| `relationships_query()` | `st_relationships.read` | R4: Query knowledge graph | ✅ Active |
| `relationships_upsert()` | `st_relationships.write` | R4: Write new relationships | ✅ Active |
| `ultrabert_embed()` | `ultrabert.call` | R4: Entity extraction embeddings | ✅ Active |
| `outbox_emit_batch()` | `st_outbox.write` | R8: Emit completion events | ✅ Active |
| `working_memory_read()` | `st_working_memory.read` | Context for consolidation | 🚧 Not Implemented |
| `working_memory_write()` | `st_working_memory.write` | Write temporary state | 🚧 Not Implemented |

**Deprecated Syscalls (DO NOT USE)**:

| Syscall | Reason | Replacement |
|---------|--------|-------------|
| `hipp_store_upsert()` | ❌ Deprecated | Use `hipp_events_upsert()` |
| `embedding_enqueue()` | ❌ Deprecated | Inline via M22 UltraBERT |
| `faiss_read()` | ❌ pgvector replaces | Use `vec_query()` |
| `faiss_write()` | ❌ pgvector replaces | Use `vec_write()` |

### 20.3 Event Topics (P03 Emits)

| Topic | Consumer | Purpose |
|-------|----------|---------|
| `p03.consolidation.complete.v1` | Monitoring, P04 | Cycle completion |
| `p03.phase.complete.v1` | Monitoring | Per-phase progress |
| `p03.episode.formed.v1` | P04, P05 | New episode created |
| `p03.pattern.discovered.v1` | P04 | New semantic pattern |
| `p03.truth.reinforced.v1` | Audit | Existing truth strengthened |
| `p03.truth.created.v1` | Audit | New truth record |
| `p03.truth.evolved.v1` | Audit | Truth record versioned |
| `p03.memory.pruned.v1` | Audit | Memory archived/tombstoned |
| `p03.gap.detected.v1` | P06 | Knowledge gap for questioning |
| `p03.kg.updated.v1` | P04 | Knowledge graph changes |
| `p03.insight.generated.v1` | P05 | R5 creative insight |

### 20.4 Fabric Capabilities

**From `governance/k0/k0_architecture_master.md` Part 8 - 18 Registered Capabilities**:

| Capability | Provider | Timeout | Purpose | Status |
|------------|----------|---------|---------|--------|
| `hipp_store.read` | HippStoreDriver | 50ms | Read hipp events | ✅ Active |
| `hipp_store.write` | HippStoreDriver | 100ms | Write hipp events | ✅ Active |
| `vec.read` | PgVectorDriver | 100ms | Similarity query (HNSW) | ✅ Active |
| `vec.write` | PgVectorDriver | 150ms | Write embeddings | ✅ Active |
| `relationships.read` | Neo4jDriver | 200ms | Knowledge graph query | ✅ Active |
| `relationships.write` | Neo4jDriver | 250ms | Knowledge graph write | ✅ Active |
| `ultrabert.embed` | UltraBERTCache | 50ms | Get/compute embeddings | ✅ Active |
| `outbox.emit` | OutboxDriver | 50ms | Emit events | ✅ Active |
| `score_salience` | salience_scorer:v1 | 30ms | Compute salience score | ✅ Active |
| `score_decay` | decay_scorer:v1 | 50ms | Exponential decay | 🎯 P03 |
| `cluster_episodes` | episodic_clusterer:v1 | 200ms | DBSCAN clustering | 🎯 P03 |
| `detect_duplicates` | simhash_deduplicator:v1 | 100ms | SimHash dedup | 🎯 P03 |
| `extract_entities` | entity_extractor:v1 | 150ms | UltraBERT NER | 🎯 P03 |
| `generate_counterfactuals` | counterfactual:v1 | 300ms | CPN scenarios | 🎯 P03 Phase 2 |
| `simulate_futures` | forward_simulator:v1 | 500ms | TPN-MCTS | 🎯 P03 Phase 2 |
| `generate_insights` | insight_generator:v1 | 400ms | BGT-SM | 🎯 P03 Phase 2 |

### 20.5 Scheduler Trigger Types

**From `k0/scheduler/triggers.py` - Active Trigger Engines**:

| Trigger Type | Engine | P03 Usage | Status |
|--------------|--------|-----------|--------|
| INTERVAL | `IntervalTriggerEngine` | Every 5400s (90 min) | ✅ Active |
| THRESHOLD | `ThresholdTriggerEngine` | 500+ pending events | ✅ Active |
| MANUAL | `ManualTriggerEngine` | Admin/debug trigger | ✅ Active |
| CRON | `CronTriggerEngine` | - | 📋 Phase 2 |
| IDLE | `IdleTriggerEngine` | - | 📋 Phase 2 |

---

## 21. Threshold Configuration

### 21.1 Thompson Sampling Priors

| Threshold | Target | Prior | Effective Samples |
|-----------|--------|-------|-------------------|
| REINFORCE | 0.85 | Beta(17, 3) | 20 |
| EXTEND_LOWER | 0.60 | Beta(12, 8) | 20 |

**Why α+β=20?**: Requires ~50 signals to shift threshold by 0.05. Balances stability vs adaptability.

### 21.2 Static Thresholds Reference

| Threshold | Default | Range | Unit |
|-----------|---------|-------|------|
| REINFORCE_MIN | 0.85 | 0.80-0.95 | cosine |
| EXTEND_MIN | 0.60 | 0.50-0.75 | cosine |
| EXTEND_MAX | 0.85 | 0.75-0.90 | cosine |
| CONTRADICT | 0.30 | 0.20-0.45 | cosine |
| NOVELTY_MIN | 0.70 | 0.60-0.85 | score |
| PRUNE | 0.01 | 0.005-0.05 | decay |
| ARCHIVE | 0.10 | 0.05-0.20 | decay |
| ACTIVE | 0.30 | 0.20-0.50 | decay |
| CANONICAL_MIN | 0.50 | 0.40-0.70 | confidence |
| GAP_ENTROPY_MIN | 0.50 | 0.30-0.70 | entropy |

### 21.3 Validation Rules

- contradict < extend_min < extend_max ≤ reinforce_min
- prune < archive < active
- low < medium < high (confidence)

---

## 22. State Machine Specification

### 22.1 Phase State Machine

```
IDLE → R0.INIT → R1.PROC → R2.PROC → R3.PROC → R4.PROC → R5.PROC → R6.PROC → R7.PROC → R8.PROC → IDLE
              ↓         ↓         ↓         ↓         ↓                  ↓         ↓
          [FAIL]    [SKIP]    [FAIL]    [FAIL]    [SKIP]             [FAIL]    [FAIL]
```

### 22.2 Phase Specifications

| Phase | Purpose | Timeout | Retryable | DLQ Condition |
|-------|---------|---------|-----------|---------------|
| R0 | Batch selection | 30s | Yes | DB failure after 3 retries |
| R1 | Importance scoring | 60s | Yes | P08 unavailable |
| R2 | Episodic clustering | 120s | Yes | Algorithm timeout |
| R3 | Forgetting/pruning | 60s | Yes | None (always succeeds) |
| R4 | KG building | 90s | Yes | Entity resolution failure |
| R5 | Dream exploration | 120s | Yes | MCTS timeout |
| R6 | Status staging | 30s | Yes | Version conflict >10% |
| R7 | Memory writing | 60s | Yes | Transaction failure |
| R8 | Event emission | 30s | Yes | Bus unavailable |

### 22.3 Error Recovery Matrix (PostgreSQL)

| Error Type | Recovery | Max Retries | Backoff |
|------------|----------|-------------|---------|
| DB_TIMEOUT | Retry | 3 | Exponential |
| LOCK_TIMEOUT | Wait and retry | 5 | Linear |
| POOL_EXHAUSTED | Queue | 3 | Exponential |
| VERSION_CONFLICT | Re-read, re-stage | 3 | Immediate |
| UNIQUE_VIOLATION | Check existing | 1 | Immediate |
| SERIALIZATION_FAIL | Retry with fresh read | 3 | Immediate |

---

## 23. UltraBERT Model Specification

### 23.1 Model Overview

| Property | Value |
|----------|-------|
| Package Name | `familyos-ultrabert` |
| Target Version | v2.2.1 |
| Architecture | BERT-based (12 encoders, 768-dim) |
| Parameters | 155M (15% pruned) |
| Memory Footprint | ~175MB (INT8 quantized) |
| First-Call Latency | ~17ms (with warmup) |
| Throughput | ~500 samples/sec (batch=32) |

### 23.2 Encoder Capabilities Used by P03

| Capability | Phase | Purpose |
|------------|-------|---------|
| embedding | R1, R2, R4 | 768-dim semantic embeddings |
| sentiment | R1 | Emotional weight for importance |
| emotions | R1 | Multi-label emotion classification |
| ner_family | R4 | Family-context NER (relationships) |
| ner_general | R4 | General NER (persons, locations) |
| relation | R4 | Relationship type classification |
| nli | R7 | Contradiction detection |

### 23.3 Performance Benchmarks

| Metric | Value |
|--------|-------|
| Weighted Accuracy | 89.60% |
| Crisis Detection Recall | 100% |
| NER F1 (Family) | 92.3% |
| Embedding Similarity | 0.91 (vs SBERT) |

---

## 27. UltraBERT Capabilities → P03 Phase Mapping

> **Purpose**: Map the 12 UltraBERT client capabilities to specific P03 phases and algorithms.
> **Client Location**: `familyos-ultrabert` package
> **Latency**: ~22ms per forward pass (all 12 heads)

### 27.1 UltraBERT Capability Inventory

| Capability | Output Type | P03 Phase | Primary Use |
|------------|-------------|-----------|-------------|
| `embedding` | VECTOR(768) | R1, R2, R3, R4 | Semantic similarity, clustering, dedup |
| `sentiment` | 5-class + scores | R1 | Emotional weight for importance |
| `emotions` | 43-class multi-label | R1 | Affect valence/arousal |
| `ner_family` | KINSHIP entities | R4 | Family member extraction |
| `ner_general` | PERSON/LOC/ORG | R4 | General entity extraction |
| `temporal` | DATE/TIME entities | R2, R4 | Temporal clustering, KG edges |
| `relation` | 15-class relationship | R4 | KG edge type classification |
| `intent` | 8-class user intent | R1 | Importance type multiplier |
| `ingress` | 12-class content type | R1, R3 | Event type classification |
| `nli` | entail/contradict/neutral | R4, R7 | Contradiction detection |
| `safety_familyos` | GREEN/AMBER/RED/CRISIS | Policy | Privacy band assignment |
| `safety_generic` | Toxicity scores | Policy | Content filtering |

### 27.2 Phase-by-Phase Usage

#### R1 — Hippocampal Replay (Importance Scoring)

```python
# ImportanceScorer uses 4 UltraBERT capabilities
importance = (
    0.35 × emotional_intensity(sentiment, emotions) +  # sentiment + emotions
    0.25 × recency_factor(timestamp) +
    0.20 × novelty_score(embedding) +                   # embedding
    0.20 × social_factor(ner_family)                    # ner_family
) × event_type_multiplier(ingress, intent)              # ingress + intent

# Emotional intensity from UltraBERT
def emotional_intensity(sentiment_result, emotions_result):
    sentiment_score = {
        'very_positive': 1.0, 'positive': 0.7,
        'neutral': 0.0,
        'negative': -0.7, 'very_negative': -1.0
    }[sentiment_result['prediction']]

    # Top emotion score as affect_arousal
    top_emotion_score = max(emotions_result['scores'].values())

    return abs(sentiment_score) * (1 + top_emotion_score)

# Event type multiplier from ingress
EVENT_TYPE_MULTIPLIERS = {
    'PLANNING': 1.2,      # High importance
    'TASK': 1.1,
    'MEMORY': 1.3,        # Very high (explicit memory)
    'RELATIONSHIP': 1.4,  # Family context boost
    'CELEBRATION': 1.5,   # Milestone detection
    'HEALTH': 1.3,
    'CONCERN': 1.2,
    'GRATITUDE': 1.1,
    'DIARY': 0.9,
    'FINANCE': 1.0,
    'WORK': 0.8,
    'META': 0.5,          # Low importance
}
```

#### R2 — Episodic Clustering (DBSCAN)

```python
# EpisodicClusterer uses embedding + temporal
def compute_composite_distance(event_a, event_b):
    # Semantic distance from UltraBERT embedding
    cos_sim = np.dot(event_a.embedding, event_b.embedding)
    semantic_dist = 1.0 - cos_sim

    # Temporal distance (normalized)
    time_diff_hours = abs(event_a.timestamp - event_b.timestamp) / 3600000
    if time_diff_hours > 4.0:  # Max gap
        return float('inf')
    temporal_dist = time_diff_hours / 4.0

    # Composite (70% semantic, 30% temporal)
    return 0.7 * semantic_dist + 0.3 * temporal_dist
```

#### R3 — Forgetting/Pruning (Deduplication)

```python
# Two-stage deduplication using embedding
# Stage 1: SimHash (fast filter) - from content hash
# Stage 2: Embedding verification (semantic)
def verify_duplicate(event1, event2):
    similarity = np.dot(event1.embedding, event2.embedding)
    if similarity >= 0.85:
        return 'DUPLICATE'
    elif similarity >= 0.70:
        return 'LIKELY_DUPLICATE'
    else:
        return 'NOT_DUPLICATE'
```

#### R4 — Knowledge Graph Consolidation

```python
# EntityExtractor uses 4 UltraBERT capabilities
def extract_entities(ultrabert_result):
    entities = []

    # Family NER (KINSHIP → FAMILY_MEMBER)
    for e in ultrabert_result['ner_family']['entities']:
        entities.append(Entity(
            text=e['text'],
            type='FAMILY_MEMBER',
            subtype=e['label'],  # KINSHIP
            confidence=0.90
        ))

    # General NER (PERSON, LOCATION, ORG)
    for e in ultrabert_result['ner_general']['entities']:
        entities.append(Entity(
            text=e['text'],
            type=e['label'],  # PERSON, LOCATION, etc.
            confidence=0.85
        ))

    # Temporal entities → prospective memory
    for e in ultrabert_result['temporal']['entities']:
        entities.append(Entity(
            text=e['text'],
            type='TEMPORAL',
            subtype=e['label'],  # DATE_REL, TIME
            confidence=0.95
        ))

    return entities

# RelationshipBuilder uses relation head
def extract_relationships(ultrabert_result, entities):
    relation = ultrabert_result['relation']

    # Top relationship prediction
    rel_type = relation['predictions'][0]  # e.g., 'spouse_of'
    confidence = relation['scores'][rel_type]

    # Map to KG edge type
    KG_RELATION_MAP = {
        'spouse_of': 'MARRIED_TO',
        'parent_of': 'PARENT_OF',
        'child_of': 'CHILD_OF',
        'sibling_of': 'SIBLING_OF',
        'friend_of': 'FRIEND_OF',
        'colleague_of': 'WORKS_WITH',
        'lives_at': 'RESIDES_AT',
        'owns': 'OWNS',
        # ... etc
    }

    return Relationship(
        type=KG_RELATION_MAP.get(rel_type, 'ASSOCIATED_WITH'),
        confidence=confidence
    )

# ContradictionDetector uses NLI head
def detect_contradiction(new_signal, existing_truth):
    # Compare new signal text against existing truth
    nli_result = ultrabert.forward(
        premise=existing_truth.canonical_text,
        hypothesis=new_signal.text,
        heads=['nli']
    )

    if nli_result['nli']['prediction'] == 'contradiction':
        if nli_result['nli']['confidence'] > 0.70:
            return ReconciliationDecision.CONTRADICT

    return None  # No contradiction detected
```

#### R7 — Truth Write (Contradiction Check)

```python
# Final contradiction check before writing to truth layers
async def check_truth_contradiction(signal, truth_record):
    nli_result = await ultrabert.forward(
        premise=truth_record.canonical_text,
        hypothesis=signal.text,
        heads=['nli']
    )

    if nli_result['nli']['prediction'] == 'contradiction':
        confidence = nli_result['nli']['confidence']
        if confidence > 0.70:
            # Queue for P06 Active Learning
            await emit_gap(
                gap_type='CONTRADICTION',
                importance=confidence,
                context={
                    'new_signal': signal.id,
                    'existing_truth': truth_record.id,
                    'nli_confidence': confidence
                }
            )
            return False  # Block write

    return True  # Allow write
```

### 27.3 Security & Policy Integration

```python
# Privacy band assignment from safety_familyos
def assign_privacy_band(ultrabert_result):
    safety = ultrabert_result['safety_familyos']

    # Direct mapping
    return safety['band']  # GREEN, AMBER, RED, CRISIS

# Content filtering from safety_generic
def filter_toxic_content(ultrabert_result):
    safety = ultrabert_result['safety_generic']

    # Check critical thresholds
    if safety['scores']['self_harm'] > 0.8:
        return 'CRISIS_ESCALATE'
    if safety['scores']['threat'] > 0.7:
        return 'RED_FLAG'
    if safety['scores']['toxic'] > 0.5:
        return 'MODERATE'

    return 'PASS'
```

### 27.4 Example: Full P03 Processing Flow

For input: *"Remind me pickup my child from costco on sunday at 8 and also I am planning to have a romantic date with my wifey"*

| Phase | UltraBERT Used | Extracted Data |
|-------|----------------|----------------|
| **R1** | sentiment, emotions, ingress, intent | importance=HIGH (excitement+planning+family) |
| **R2** | embedding, temporal | cluster by date (sunday), embedding vector |
| **R3** | embedding | novelty check against existing reminders |
| **R4** | ner_family, temporal, relation | KINSHIP: child, wife; DATE: sunday; TIME: 8; REL: spouse_of, parent_of |
| **R7** | nli | Check no contradiction with existing calendar |
| **Policy** | safety_familyos | GREEN band (safe content) |

**Entities Created**:
- `FAMILY_MEMBER(child)` with `PARENT_OF` edge to user
- `FAMILY_MEMBER(wife)` with `SPOUSE_OF` edge to user
- `LOCATION(costco)` with `FREQUENTS` edge to user
- `TEMPORAL(sunday at 8)` → prospective memory trigger

**Memory Writes**:
- `st_prospective`: Reminder for child pickup (sunday 8am, costco)
- `st_prospective`: Romantic date intention (unscheduled)
- `st_social`: Strengthen spouse_of, parent_of edges
- `st_epi`: Episode cluster for "family planning day"

### 27.5 UltraBERT Syscall Integration

```python
# P03 calls UltraBERT via M22 (UltraBERTCache)
# Syscall: ultrabert_embed() with capability 'ultrabert.call'

async def process_event_with_ultrabert(event: HippEvent) -> UltraBERTResult:
    """Full forward pass for P03 consolidation."""

    result = await syscall(
        'ultrabert_embed',
        text=event.body_text,
        heads=[
            'embedding',      # Always needed
            'sentiment',      # R1 importance
            'emotions',       # R1 importance
            'ner_family',     # R4 entities
            'ner_general',    # R4 entities
            'temporal',       # R2, R4
            'relation',       # R4 edges
            'ingress',        # R1 type
            'intent',         # R1 type
            'nli',            # R4, R7 contradiction
            'safety_familyos' # Policy band
        ]
    )

    return result

# Cached embedding lookup (most common case)
async def get_embedding_only(event_id: str) -> np.ndarray:
    """Fast path: embedding already computed by P02."""
    cached = await syscall(
        'ultrabert_embed',
        event_id=event_id,
        heads=['embedding'],
        use_cache=True
    )
    return np.array(cached['embedding'])
```

### 27.6 Performance Considerations

| Operation | Latency | When Used |
|-----------|---------|-----------|
| Full forward (12 heads) | ~22ms | New event ingestion |
| Cached embedding only | ~1ms | R2 clustering, R3 dedup |
| NLI pair comparison | ~15ms | R7 contradiction check |
| Batch forward (32 events) | ~180ms | R1 batch processing |

**Optimization Strategy**:
- P02 computes full forward pass on ingestion → cache all heads
- P03 reads cached results for R1-R4
- Only R7 contradiction check may need fresh NLI computation

---

## 24. Open Questions & TODOs

### 24.1 Questions for Architecture Review

- [ ] Confirm P08 circuit breaker configuration
- [ ] Clarify K1 integration timeline for feedback signals
- [ ] Review Thompson Sampling bounds with ML team

### 24.2 Implementation TODOs

- [ ] Create pipeline contract `p03_consolidation.v1.yaml`
- [ ] Create module directory `k0/modules/consolidation/`
- [ ] Implement 16 P03-specific modules
- [ ] Complete R5 Dream-Like Exploration algorithms
- [ ] Define st_learning_queue schema for P06
- [x] Complete st_anchors schema for Bayesian beliefs
- [x] Define migration path from v1 → v2 (see §10b)
- [x] Complete policy decisions (CONTRADICT, gap queue, anchor drift, R5)
- [x] Complete feature flag master list
- [x] Complete error handling & DLQ integration
- [x] Complete security & privacy (K0 policy engine, GDPR)

### 24.3 ADRs Required

| ADR ID | Title | Status |
|--------|-------|--------|
| k010 | P03 Consolidation Architecture | 🎯 Draft |
| k010.1-p03 | Sleep Cycle State Machine | 🎯 Draft |
| k010.2-p03 | Importance Scoring Formula | 🎯 Draft |
| k010.3-p03 | Episodic Clustering Algorithm | 🎯 Draft |
| k010.4-p03 | CA1 Bridge Decision Protocol | 🎯 Draft |
| k010.5-p03 | SimHash Deduplication | 🎯 Draft |
| k010.6-p03 | Entity Normalization Strategy | 🎯 Draft |
| k010.7-p03 | 8-Layer Memory Write Coordination | 🎯 Draft |
| k010.8-p03 | P08 Embedding Coordination | 🎯 Draft |
| k010.9-p03 | Capability-Based Security | 🎯 Draft |
| k010.10-p03 | Dream Phase Algorithms | 🎯 Draft |

### 24.4 Reading Progress

- [x] Lines 1-5000: Core philosophy, architecture, R1-R4 phases, learning systems
- [x] Lines 5001-10000: R4 causality, R5 MVP, P06 integration, storage schemas
- [x] Lines 10001-15000: Module Registry, Observability, Integration Contracts, Testing, Migration
- [x] Lines 15001-20000: Feature flags, Policy decisions, Error handling, Security, Performance, Ops readiness
- [x] Lines 20001-27978: Detailed algorithm specifications (Appendix C complete), K0 Integration Blueprint (Appendix D), Canonical Name Registry (Appendix E), Threshold Configuration (Appendix F), State Machine Spec (Appendix G), UltraBERT Spec (Appendix H), Closed-Loop Feedback vision (Appendix I)

### 24.5 Dossier Reading COMPLETE ✅

**Total Lines Read**: 27,978
**Chunks Processed**: 6 (5 × 5000 + 1 × 2978)
**Completion Date**: Session end

---

## 26. Detailed Algorithm Appendix Addendum

> **Purpose**: Capture additional algorithm details from Appendix C (lines 20001-27978) not fully covered in Section 17.
> **Note**: Most algorithms are covered in Section 17. This section captures advanced sub-algorithms and learning variants.

### 26.1 Adaptive Importance Weight Learning (C.2.1.1)

**Method**: Online gradient descent with momentum=0.9
**Loss Function**: Binary cross-entropy predicting "will event be grounded?"
**Training Schedule**: Nightly batch during P03 consolidation cycle
**Minimum Samples**: 500 events with grounding feedback before learning starts

**Weight Persistence**:
- Storage Table: `st_learned_weights` (key pattern: `importance_<component>`)
- Scope: Per-space isolation
- Loading: At kernel bootup, weights loaded; fallback to static prior if none exist

**Drift Handling**:
- Sliding Window: Last 30 days of feedback
- Exponential Decay: `weight = exp(-0.1 × days_ago)`
- Momentum Update: `v = 0.9 × v + gradient`

### 26.2 Stability Controls for Learning (C.2.1.2)

**Momentum-Based Smoothing**:
```
velocity_t = β × velocity_{t-1} + ∇L_t
w_t = w_{t-1} - η × velocity_t
```
Where β=0.9 (momentum), η=0.01 (learning rate)

**Weight Clamping**:
```python
w_i = max(0.05, min(0.60, w_i))  # All importance weights
```
- min=0.05: All signals contribute at least 5%
- max=0.60: No signal exceeds 60%

**Rollback Trigger**: If training loss increases 3 consecutive nights → rollback to static weights.

### 26.3 Anti-Hebbian Decay (C.2.2.1)

**Principle**: "Cells that fire apart, unwire" — weaken wrong associations.

| Signal Type | Source | Penalty |
|-------------|--------|--------|
| `ENTITY_MERGE_REJECTED` | P06/User | -0.2 |
| `ASSOCIATION_WRONG` | K1 correction | -0.3 |
| `MUTUAL_EXCLUSION` | P03 R4 | -0.4 |
| `CONTRADICTION` | P03 R7 | -0.15 |

**Anti-Hebbian Formula**:
```
Δw = -anti_lr × current_weight × confidence × penalty_multiplier
anti_lr = 0.15 (faster than positive learning 0.1)
penalty_multiplier = 1.3 if explicit_correction else 1.0
```

### 26.4 Edge Resurrection (C.2.2.2)

**Resurrection Formula**:
```python
new_weight = max(0.7, 0.5 + old_weight × 0.5)
resurrection_count += 1
archival_status = 'ACTIVE'
```

**Instability Alert**: If `resurrection_count >= 3` → emit alert `P03HebbianEdgeUnstable`.

### 26.5 Adaptive Learning Rate for Hebbian (C.2.2.3)

```python
def compute_learning_rate(cooccurrence_count: int) -> float:
    lr_max = 0.3   # New edges
    lr_min = 0.05  # Mature edges
    decay_factor = 0.1
    lr = lr_max * math.exp(-decay_factor * cooccurrence_count) + lr_min
    return max(lr_min, min(lr_max, lr))
```

| Co-occurrence | Learning Rate | Interpretation |
|---------------|---------------|----------------|
| 1-5 (new) | 0.25-0.30 | Fast learning |
| 6-15 (emerging) | 0.15-0.20 | Moderate |
| 16-50 (established) | 0.08-0.12 | Slow |
| 50+ (mature) | 0.05 | Minimal (resist noise) |

### 26.6 Saturation Controls (C.2.2.4)

**Co-occurrence Capping** (logarithmic scaling):
```python
def normalize_cooccurrence(raw_count: int, cap_threshold: int = 50) -> float:
    if raw_count <= cap_threshold:
        return float(raw_count)
    excess = raw_count - cap_threshold
    return cap_threshold + math.log2(excess + 1)
```

### 26.7 Pre-Clustering Episode Split (C.3.1.1)

**Problem**: Events spanning >4 hours create poor DBSCAN clusters.

**Split Signals** (priority order):
1. Location Change: geohash prefix differs by >4 chars
2. Activity Change: `activity_type` changes
3. Time Gap: Gap > 30 minutes
4. Hard Limit: Episode > 4 hours

### 26.8 Adaptive Min_samples for DBSCAN (C.3.1.2)

| Singleton Rate | Diagnosis | Action |
|----------------|-----------|--------|
| > 20% | Under-clustering | min_samples + 1 (max 5) |
| < 5% | Over-clustering | min_samples - 1 (min 2) |
| 5-20% | Good balance | No change |

### 26.9 Content-Type SimHash Thresholds (C.4.1.1)

| Content Type | Threshold (bits) | Rationale |
|--------------|------------------|-----------|
| `TRANSACTION` | 1 | Financial exactness |
| `CALENDAR_EVENT` | 2 | Structured |
| `CONTACT_UPDATE` | 2 | Names must match |
| `CHAT_MESSAGE` | 3 | Default |
| `PHOTO_CAPTION` | 4 | Free-form |
| `JOURNAL_ENTRY` | 4 | Subjective |
| `VOICE_MEMO` | 5 | Transcription noise |

**Learning from Feedback**:
- `UNMERGE_DEDUP`: Increase threshold +1
- `MANUAL_MERGE`: Decrease threshold -1

### 26.10 Two-Stage Deduplication Pipeline (C.4.1.2)

**Stage 1**: SimHash (fast filter, O(n))
**Stage 2**: Embedding (semantic verification, cosine ≥0.85)

| SimHash | Embedding | Decision |
|---------|-----------|----------|
| ≤ threshold | ≥ 0.85 | DUPLICATE |
| ≤ threshold | 0.70-0.85 | LIKELY_DUPLICATE |
| ≤ threshold | < 0.70 | NOT_DUPLICATE (false positive) |
| > threshold | ≥ 0.90 | SEMANTIC_DUPLICATE (fallback catch) |

### 26.11 MinHash LSH Scale Strategy (C.4.1.3)

**Transition Logic**:
| Event Count | Algorithm | Complexity |
|-------------|-----------|------------|
| < 10,000 | SimHash pairwise | O(n) |
| 10K-50K | SimHash + bucketing | O(n/b) |
| > 50,000 | MinHash LSH | O(log n) |

**MinHash Parameters**:
- `num_hashes = 128`
- `num_bands = 32`
- `rows_per_band = 4`

### 26.12 Memory Resurrection (C.4.2.1)

**Triggers**:
1. QUERY: P04 retrieval queries archived entity
2. CO_OCCURRENCE: Archived entity reappears in new event
3. USER_MENTION: User explicitly references archived entity

**Resurrection Formula**:
```python
new_decay = max(0.7, 0.5 + old_decay * 0.5)
resurrection_count += 1
```

### 26.13 Bayesian Lambda Estimation (C.4.1 detailed)

**Conjugate Model**: Gamma-Exponential
- Inter-access times: `x ~ Exponential(λ)`
- Prior: `λ ~ Gamma(α₀, β₀)`
- Posterior: `λ | data ~ Gamma(α₀ + n, β₀ + Σxᵢ)`

**Entity-Type Priors**:
| Entity Type | Default λ | α₀ | β₀ |
|-------------|-----------|-----|-----|
| PERSON | 0.002 | 2 | 1000 |
| FAMILY_MEMBER | 0.001 | 2 | 2000 |
| PLACE | 0.003 | 2 | 667 |
| ORGANIZATION | 0.0025 | 2 | 800 |
| THING | 0.005 | 2 | 400 |
| ACTIVITY | 0.006 | 2 | 333 |

**Confidence-Based Application**:
| CI Width | Confidence | Action |
|----------|------------|--------|
| < 20% | NARROW | Use learned λ directly |
| 20-50% | MODERATE | Blend 50/50 with default |
| > 50% | WIDE | Use default, keep collecting |

### 26.14 Lambda Fallback Hierarchy (C.4.2)

4-level fallback chain:
1. **Per-Entity λ** (if 5+ accesses, 7+ day spread)
2. **Per-Entity-Type λ** (space-specific learning)
3. **Global Entity-Type λ** (from DECAY_CONFIGS)
4. **Layer Default λ** (last resort)

**30-Day Warm-Up**: New entities use entity-type default for 30 days.
**Aggressive Decay**: Post-warm-up entities with <5 accesses get 1.5× decay.

### 26.15 Query-to-Pruned Matching (C.4.3)

**Two-Stage Matching**:
| Stage | Method | Threshold |
|-------|--------|-----------|
| 1 | Fuzzy name (Levenshtein + token) | > 0.70 |
| 2 | Embedding cosine | > 0.75 |

**Context Boosts**:
- Same space: +0.10
- Same actor: +0.05
- Same time window: +0.03
- Co-occurring entities: +0.05

### 26.16 Regret Signal Processing (C.4.4)

**Base Confidence**: 0.90 (very high)

| Regret Type | Confidence | Lambda Adjustment |
|-------------|------------|-------------------|
| STRONG_MATCH | 0.90 | -10% |
| LIKELY_MATCH | 0.70 | -5% |
| SEMANTIC_MATCH | 0.85 | -8% |
| Multiple (same type) | 0.95 | -15% + alert |

**Rate Limits**:
- Max 10 regret signals per entity-type per day
- Alert if regret rate > 20% of pruning rate

### 26.17 Milestone Event Detection (C.4.3.1)

**Three-Layer Detection**:
1. **NER**: Extract temporal entities ("birthday", "anniversary")
2. **Ontology Match**: Cross-reference with st_kg_dom (PERSON.birthday == event_date)
3. **Recurrence Detection**: Same date (±3 days) in previous years

**Confidence Levels**:
| Source | Confidence |
|--------|------------|
| NER + Ontology | 0.95 |
| Ontology only | 0.85 |
| NER only | 0.70 |
| Recurrence only | 0.60 |

**Milestone Types**:
BIRTHDAY, ANNIVERSARY, GRADUATION, WEDDING, BIRTH, DEATH, RETIREMENT, PROMOTION, FIRST_DAY, LAST_DAY, HOLIDAY

### 26.18 Feedback-to-Formula Mapping (C.4.6)

| Feedback Type | Affected Formula | Parameter Updated |
|---------------|------------------|-------------------|
| `SALIENCE_ADJUSTMENT` | Importance (R1) | α_importance weights |
| `DECAY_REVERSAL` | Unified Decay (R3) | decay λ |
| `CLUSTER_CORRECTION` | DBSCAN (R2) | eps, min_samples |
| `NOVELTY_SIGNAL` | Novelty Score (R4) | novelty thresholds |
| `REFORMULATION` | Similarity (R6) | similarity thresholds |

**Confidence Weighting**:
| Confidence | Strategy |
|------------|----------|
| < 0.50 | Aggregate only (10+ signals) |
| 0.50-0.75 | Apply with 50% weight |
| > 0.75 | Apply full weight |

### 26.19 Implicit Signal Confidence (C.4.7)

| Signal | Base Confidence | Reliability |
|--------|-----------------|-------------|
| `CORRECTION` | 0.90 | High (explicit) |
| `MEMORY_MISS` | 0.80 | High |
| `REGRET` | 0.90 | High |
| `REFORMULATION` | 0.60 | Medium |
| `ABANDONMENT` | 0.50 | Low |

**Adjustments**:
- Explicit user action: +0.10
- Via UI (indirect): -0.10
- Late night (11pm-5am): -0.20
- Repeat pattern (3+): +0.10

---

## 25. K0 Alignment Changelog

> **Purpose**: Track changes made to align implementation notes with actual K0 kernel architecture.
> **Sources Used**:
> - `architecture_diagrams/k0/k0_source_of_truth_postgresql.mmd` (1,550 lines)
> - `governance/k0/k0_architecture_master.md` (2,602 lines)
> - `k0/kernel/syscalls.py` (2,623 lines)

### 25.1 Technology Stack Corrections

| Area | Dossier (Outdated) | Actual K0 V3 |
|------|-------------------|--------------|
| Database | SQLite | PostgreSQL 16+ |
| Async Driver | sqlite3 | asyncpg (native async) |
| Connection Pool | None | pgbouncer |
| Embedding Search | FAISS indexes | pgvector HNSW |
| Full-Text Search | FTS5 | tsvector + GIN |
| Migrations | Manual scripts | Alembic (25 migrations) |
| Vector Storage | BLOB 768 floats | VECTOR(768) native |

### 25.2 Deprecated Items Marked

| Item | Status | Replacement |
|------|--------|-------------|
| FAISS | ❌ Deprecated | pgvector with HNSW indexes |
| FTS5 | ❌ Removed | PostgreSQL tsvector + GIN |
| `st_embedding_queue` | ❌ Deprecated | Inline via M22 UltraBERTCache |
| `hipp_store_upsert()` | ❌ Deprecated | `hipp_events_upsert()` |
| `embedding_enqueue()` | ❌ Deprecated | Inline via M22 |
| `faiss_read()`, `faiss_write()` | ❌ Deprecated | `vec_query()`, `vec_write()` |
| M23 (EmbeddingVecWriter) | ❌ Merged | M16 (HippEventsWriter) |
| M24 (FAISSIndexer) | ❌ Deprecated | Native pgvector HNSW |

### 25.3 Sections Updated

| Section | Changes Made |
|---------|--------------|
| 6. Storage Schema | Added PostgreSQL tech stack table, updated st_vec to use VECTOR(768), added HNSW index examples |
| 7. Module Registry | Split into K0 reusable (M01-M22) and P03-specific (M30-M46), added syscall mappings |
| 7.3 Dependency Graph | Rebuilt with K0 module IDs and syscall annotations |
| 19. K0 Integration | Added deprecation table, corrected layer stack with file paths, added component location table |
| 20. Canonical Names | Added syscalls registry from k0/kernel/syscalls.py, added fabric capabilities from Part 8, added trigger types |

### 25.4 K0 Architecture Cross-References Added

| Notes Section | K0 Source | Part/Layer |
|---------------|-----------|------------|
| 6.1 Tech Stack | k0_source_of_truth_postgresql.mmd | Layer 10 |
| 6.2 Tables | k0_architecture_master.md | Part 6 |
| 7.1 K0 Modules | k0_architecture_master.md | Part 3 |
| 19.2 Layers | k0_source_of_truth_postgresql.mmd | Layers 0-10 |
| 19.3 Components | k0/ folder structure | - |
| 20.2 Syscalls | k0/kernel/syscalls.py | Part 7 |
| 20.4 Capabilities | k0_architecture_master.md | Part 8 |
| 20.5 Triggers | k0/scheduler/triggers.py | Part 9 |

### 25.5 Module ID Renumbering

**Rationale**: Dossier used M18-M25 but M22/M23/M24 conflict with existing K0 modules.

| Dossier ID | Dossier Name | New K0 ID | Notes |
|------------|--------------|-----------|-------|
| - | (Batch selection) | M30 | New module added |
| M23 | ReplayCoordinator | M31 | Renamed to ImportanceScorer |
| - | (Hebbian learning) | M32 | New module added |
| M18 | EpisodicClusterer | M33 | Renumbered |
| - | (Episode building) | M34 | New module added |
| M19 | DuplicateDetector | M35 | Renamed to SimHashDeduplicator |
| - | (Decay scoring) | M36 | New module added |
| M20 | RetentionEnforcer | M37 | Renamed to PruneDecider |
| - | (Entity extraction) | M38 | New module from M21 split |
| - | (Relationship building) | M39 | New module from M21 split |
| - | (Causal inference) | M40 | New module from M21 split |
| M22 | DreamExplorer | M41-M43 | Split into 3 (Counterfactual, ForwardSim, InsightGen) |
| M24 | TruthWriter | M44-M45 | Split into StatusUpdater + MemoryWriter |
| M25 | GapDetector | M46 | Renumbered |

---

*Implementation notes extracted from P03_consolidation_dossier_v2.md (27,978 lines)*
*Dossier Version: 2.3.0 (Production-Ready Draft)*
*K0 Alignment Date: Current session*
*Last Updated: K0 architecture alignment complete*
