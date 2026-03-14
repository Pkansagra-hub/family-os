# Universal Reconciliation Engine -- Whiteboard

**Purpose**: Requirements skeleton and architectural blueprint for the Universal Reconciliation Engine
**Status**: REQUIREMENTS PHASE
**Date**: 2026-03-09
**Source**: R2 Episodic Integration Epic Plan -- Milestone 9 (absorbs M7)
**Scope**: P03 Consolidation (all phases R2-R7) + future P06 active learning integration

---

## 1. Problem Statement

The current P03 consolidation pipeline has **no unified reconciliation**. Each phase (R2, R3, R4, R5) implements its own matching, scoring, and write-assembly logic independently. This creates five root causes that block scalable truth management:

| ID | Root Cause | Impact |
|----|-----------|--------|
| RC-0 | ReconciliationEngine is embedding-only | Cannot reconcile key-based layers (st_kg_dom, st_kg_edges, st_social) |
| RC-1 | TruthQueryService layer registry is incomplete | 5 of 8+ layers registered; scattered duplicate registries |
| RC-2 | No generic truth read syscall exists | 8+ bespoke syscalls with different parameter shapes, return types, filtering |
| RC-3 | Write assembly is per-layer hardcoded | 12+ methods in TruthWriteAssembler, each with bespoke column mappings |
| RC-4 | No identity strategy abstraction | Each layer answers "is this the same thing?" differently, scattered across R2/R3/R4 |

**Goal**: One framework, any truth layer, any reconciliation action -- with zero per-layer code changes when adding new layers.

---

## 2. Reconciliation Actions (6 Total)

| Action | Trigger | Semantic | Write Effect |
|--------|---------|----------|-------------|
| CREATE | No match found (similarity < 0.60) | New truth record | INSERT new row |
| REINFORCE | High match (similarity >= 0.85, same thread) | Strengthen existing record | UPDATE observation_count, last_observed_at, version |
| EXTEND | Medium match (similarity >= 0.60, same thread) | Grow existing record with new content | UPDATE summary, embedding_text, participants, temporal bounds |
| EVOLVE | K1 correction_signal = true | Truth has fundamentally changed | UPDATE old (SUPERSEDED) + INSERT new (supersedes_id = old PK) |
| CONTRADICT | K1 contradiction_signal = true | Conflicting truth detected | INSERT gap record into P06 active learning queue |
| PRUNE | Timer-based temporal decay | Stale truth removal | SET status = ARCHIVED or TOMBSTONED |

---

## 3. Two-Tier Decision Model

### Tier 1: K1-Signaled Decisions (checked FIRST)

K1 LLM conversational signals drive EVOLVE and CONTRADICT. These cannot be detected by cosine similarity -- they require semantic understanding from the conversation layer.

- `correction_signal = true` --> EVOLVE (regardless of similarity score)
- `contradiction_signal = true` --> CONTRADICT (regardless of similarity score)
- P03 is a **signal processor** for these decisions, NOT a signal detector

**Signal Pipeline Status**: DONE (M7 Issue 7.2.0). K1 atom v2.2 --> Bridge envelope --> P02 M13 --> st_hipp_events (migration 0085) --> P03 R0 --> P03EventState. Framework reads from P03EventState.

### Tier 2: K0-Computed Decisions (checked SECOND)

Layer-specific identity policies drive REINFORCE, EXTEND, CREATE.

- Key-match score 1.0 skips similarity thresholds --> REINFORCE or EXTEND based on content change
- Embedding retrieval remains useful for candidate search, but episodic reconciliation should not be embedding-only
- `st_epi` should use a compact multi-signal policy over a bounded subset of `st_hipp_events` / `P03EventState`, not the full event surface
- Default episodic feature family: embedding similarity, thread signal, participant/focus overlap, topic/activity congruence, location/place match, social context match, and temporal continuity
- Timer-based PRUNE operates as a separate sweep, independent of incoming signals

---

## 4. Truth Layer Coverage

### 4.1 Layer Registry Requirements

Every truth table must be described by a single `TruthLayerSpec` containing:

- table/layer name, PK column, embedding FK (or None)
- confidence column, status column, active status value
- supersedes column, version column, observation count column
- identity columns for matching
- temporal columns (start/end)
- flags: supports_embedding_match, supports_key_match

### 4.2 Layer Matrix

| Layer | PK | Embedding FK | Identity Columns | Embedding Match | Key Match | Current Phase |
|-------|----|-----------|--------------------|-----------------|-----------|--------------|
| st_epi | episode_id | embedding_id | narrative_thread_id | Yes | No | R2 |
| st_sem | semantic_id | embedding_id | pattern_type | Yes | No | R3 |
| st_procedural | routine_id | embedding_id | routine_name, time_pattern | Yes | Yes | R3/R5 |
| st_social | relationship_id | embedding_id | participant_a, participant_b | Yes | Yes | R3 |
| st_prospective | intention_id | embedding_id | intention_type | Yes | No | R3/R5 |
| st_kg_dom | entity_id | embedding_id | entity_type, canonical_name | Yes | Yes | R4 |
| st_kg_edges | edge_id | None | source_entity_id, target_entity_id, relation_type | No | Yes | R4 |
| st_vec | embedding_id | (self) | embedding_model, source_layer, source_id | No | Yes | Infrastructure |

---

## 5. Identity Strategy Requirements

Each truth layer needs its own identity function answering: "Is this candidate the same entity as this existing record?"

| Layer | Strategy Name | Logic | Match Type |
|-------|--------------|-------|------------|
| st_epi | EpisodicIdentity | cosine_sim(embedding) * thread_match_bonus(0.15) | EMBEDDING_MATCH |
| st_sem | SemanticIdentity | cosine_sim(embedding) * pattern_type_match_bonus | EMBEDDING_MATCH |
| st_kg_dom | EntityIdentity | exact key (type:name) --> 1.0; fuzzy ILIKE --> scaled; embedding fallback | KEY_MATCH or HYBRID |
| st_kg_edges | EdgeIdentity | compound key (source:target:type) --> 1.0; no embedding fallback | KEY_MATCH |
| st_social | SocialIdentity | participant pair match --> 1.0; embedding tiebreaker | KEY_MATCH or HYBRID |
| st_procedural | ProceduralIdentity | routine name + time pattern --> 1.0; embedding fallback | KEY_MATCH or HYBRID |
| st_prospective | ProspectiveIdentity | cosine_sim(embedding) only | EMBEDDING_MATCH |

**Key insight**: Key-based layers get score 1.0 on exact match and skip the threshold cascade entirely.

---

## 6. Architectural Skeleton

### 6.1 Component Map

```
k0/modules/consolidation/
    truth_layer_registry.py          # Layer 1: TruthLayerSpec + TruthLayerRegistry
    identity/
        __init__.py                  # IdentityStrategy protocol
        episodic.py                  # EpisodicIdentity
        semantic.py                  # SemanticIdentity
        entity.py                    # EntityIdentity
        edge.py                      # EdgeIdentity
        social.py                    # SocialIdentity
        procedural.py                # ProceduralIdentity
        prospective.py               # ProspectiveIdentity
    reconciliation_framework.py      # Layer 4: ReconciliationFramework
    write_decision_router.py         # Layer 5: WriteDecisionRouter

k0/kernel/syscalls.py               # Layer 3: truth_candidates_query syscall
```

### 6.2 Data Flow

```
  Incoming Event/Cluster
         |
         v
  ReconciliationCandidate (universal input)
         |
         v
  ReconciliationFramework.reconcile()
         |
         +-- TIER 1: Check K1 signals (correction_signal, contradiction_signal)
         |      |-- correction_signal --> EVOLVE
         |      |-- contradiction_signal --> CONTRADICT
         |
         +-- TIER 2: K0-computed match
                |
                +-- TruthLayerRegistry.get(target_layer)
                |
                +-- truth_candidates_query syscall
                |      |-- embedding path (pgvector <=>)
                |      |-- key path (WHERE identity_columns)
                |      |-- hybrid path (key first, embedding tiebreak)
                |
                +-- IdentityStrategy.compute_identity_score()
                |
                +-- Threshold cascade (0.85 / 0.60)
                |
                +-- WriteDecisionRouter.build_staged_write()
                       |
                       v
                ReconciliationResult (universal output)
                       |-- action: REINFORCE/EXTEND/EVOLVE/CREATE/CONTRADICT/PRUNE
                       |-- staged_write: StagedWrite (ready for R7)
                       |-- identity_score, similarity_score, confidence, reason
```

### 6.3 Five-Layer Architecture

| Layer | Component | Responsibility | Depends On |
|-------|-----------|---------------|------------|
| 1 | TruthLayerRegistry | Single source of truth for all layer metadata | Nothing |
| 2 | IdentityStrategy (x7) | Per-layer identity scoring | Layer 1 (column references) |
| 3 | truth_candidates_query syscall | Unified truth read for reconciliation | Layer 1 (SQL construction) |
| 4 | ReconciliationFramework | Core decision machine: query + identity + threshold + route | Layers 1, 2, 3, 5 |
| 5 | WriteDecisionRouter | Decision --> StagedWrite, data-driven | Layer 1 (merge rules) |

---

## 7. Universal Types (Skeleton)

### 7.1 ReconciliationCandidate (Input)

```
ReconciliationCandidate:
    candidate_id: str
    embedding: Optional[ndarray]           # 768-dim (None for key-only layers)
    identity_key: Optional[Dict]           # key columns for key-based match
    record_data: Dict                      # full column payload for INSERT/UPDATE
    source_phase: str                      # "R2", "R3", "R4", "R5"
    source_event_ids: List[str]            # provenance chain
    observation_context: Optional[ObservationContext]
    # K1 correction signal fields
    correction_signal: bool = False
    contradiction_signal: bool = False
    supersedes_concept: Optional[str] = None
    correction_source: Optional[str] = None
    session_context_id: Optional[str] = None
```

### 7.2 ReconciliationResult (Output)

```
ReconciliationResult:
    action: ReconciliationAction           # REINFORCE/EXTEND/EVOLVE/CREATE/CONTRADICT/PRUNE
    target_layer: str                      # "st_epi", "st_kg_dom", etc.
    target_record_id: Optional[str]        # existing record PK (None for CREATE)
    identity_score: float                  # from IdentityStrategy
    similarity_score: float                # embedding cosine (0.0 for key-only)
    confidence: float                      # Bayesian posterior
    reason: str                            # human-readable explanation
    staged_write: StagedWrite              # ready for R7 execution
    contradiction_details: Optional[Dict]  # for CONTRADICT --> P06 active learning
```

### 7.3 IdentityResult (Strategy Output)

```
IdentityResult:
    match_score: float                     # [0, 1] overall identity confidence
    match_type: KEY_MATCH | EMBEDDING_MATCH | HYBRID_MATCH | NO_MATCH
    identity_reason: str                   # human-readable explanation
```

---

## 8. Phase Migration Map

After the framework exists, each phase migrates FROM bespoke logic TO framework calls:

| Phase | Current Behavior | After Migration |
|-------|-----------------|-----------------|
| R2 | Own episode matching logic in r2_episodic_integrator.py | `framework.reconcile(target_layer="st_epi")` |
| R3 | ReconciliationEngine + TruthQueryService | `framework.reconcile_batch()` for all layers |
| R4 | Own entity matching + AmbiguousEntityResolver | `framework.reconcile(target_layer="st_kg_dom")` for entities, `"st_kg_edges"` for edges |
| R5 | No reconciliation on dream outputs | `framework.reconcile()` for each dream output before staging |
| R6 | 12+ per-layer assemble_*_writes methods | Receives ReconciliationResult.staged_write from phases. Orchestrates only. |

### Phases NOT Affected

- R0, R1, R8 -- not producers, no reconciliation needed
- R7 -- remains blind StagedWrite executor (correct by design)

---

## 9. Absorbed M7 Lifecycle Work

M7 was removed and absorbed into the reconciliation engine scope. Three epics carry forward:

| Absorbed From | Content | Requirement |
|--------------|---------|-------------|
| M7 7.3 | Rich Structured Episode Summaries | Summary generator called by WriteDecisionRouter on CREATE/EXTEND/EVOLVE for layers with summary support |
| M7 7.4 | Embedding Regeneration on EXTEND/EVOLVE | Centroid recomputation triggered as post-write hook for embedding-bearing layers |
| M7 7.5 | Lifecycle Observability | Per-batch, per-layer action counters + structured logging for all lifecycle transitions |

### 9.1 Structured Summary Requirements

- Episodes carry structured JSON: schema_version, title, event_count, dominant_thread, thread_distribution, goal_distribution, temporal_narrative, participants, affect_trajectory, per-event records
- Generated from ObservationContext on member events
- Computed on CREATE, recomputed on EXTEND and EVOLVE
- HTML rendering computed on demand, not stored

### 9.2 Embedding Regeneration Requirements

- REINFORCE does NOT recompute centroid (lightweight observation bump)
- EXTEND DOES recompute centroid from union of all member embeddings (old + new), recency-weighted
- EVOLVE computes fresh centroid for successor (no inheritance from superseded)
- Multi-centroid recomputation when active

### 9.3 Lifecycle Observability Requirements

- Per-batch, per-layer counters: created, reinforced, extended, evolved, contradicted, pruned
- Structured logs per lifecycle action: record_id, layer, action, event_count_before/after, similarity_score, trigger_source
- Dashboard queries for ops monitoring: action distribution, version chain depth, extend/create ratio

---

## 10. Syscall Requirements

### 10.1 New Syscall: truth_candidates_query

```
syscall: truth_candidates_query
capability: truth.reconcile.read
parameters:
    target_layer: str               # "st_epi", "st_kg_dom", etc.
    space_id: UUID
    tenant_id: UUID
    embedding: Optional[List[float]]       # for similarity search
    identity_key: Optional[Dict]           # for key-based lookup
    top_k: int = 10
    min_similarity: float = 0.35
    time_window_days: Optional[int] = 30
    active_only: bool = True
returns: List[TruthCandidate]
```

### 10.2 Query Paths

- **Embedding path**: pgvector `<=>` cosine distance operator on st_vec join
- **Key path**: WHERE clause on identity columns from TruthLayerSpec
- **Hybrid path**: key match narrows candidates, embedding scores them

### 10.3 Existing Syscalls (Unchanged)

Existing bespoke syscalls (`episodes_query`, `kg_entities_lookup`, etc.) remain for non-reconciliation use cases (R5 dream loading, K1 query serving).

---

## 11. Write Decision Router Requirements

### 11.1 Action-to-Write Mapping

| Action | Write Operation | Key Columns |
|--------|----------------|-------------|
| CREATE | INSERT | Full record_data from candidate |
| REINFORCE | UPDATE | observation_count++, last_observed_at=now(), version++ (optimistic lock) |
| EXTEND | UPDATE | Merge rules: appendable (JSON union), temporal (LEAST/GREATEST), counters (increment), replaced (overwrite) |
| EVOLVE | UPDATE + INSERT | UPDATE old (status=SUPERSEDED), INSERT new (supersedes_id=old PK) |
| CONTRADICT | INSERT | Gap record into st_learning_queue for P06 |
| PRUNE | ARCHIVE | status=ARCHIVED or TOMBSTONED per decay policy |

### 11.2 Merge Rules (Per-Layer, Part of TruthLayerSpec)

Each layer declares which columns are:

- **Appendable**: JSON arrays that union (e.g., narrative_thread_ids_json, participants_json)
- **Temporal min/max**: Use LEAST/GREATEST (e.g., temporal_start, temporal_end)
- **Counters**: Increment (e.g., observation_count)
- **Replaced**: Overwrite with new value (e.g., summary, embedding_text)

---

## 12. Configuration Requirements

```
ReconciliationConfig:
    reinforce_threshold: float = 0.85
    extend_threshold: float = 0.60
    bayesian_confidence: bool = True
    timeout_seconds: float = 30.0
    # Per-action feature flags (independently disableable)
    enable_extend: bool = True
    enable_evolve: bool = True
    enable_contradict: bool = True
    enable_prune: bool = True
    enable_structured_summaries: bool = True
    enable_embedding_regen: bool = True
```

---

## 13. Research Basis (Proven)

The reconciliation engine design is backed by completed research:

| Research Artifact | Location | What It Proved |
|-------------------|----------|----------------|
| reconciliation.py | poc/r2_phase_research/ | Two-tier engine on 1,360 events, 275 decisions. Thresholds 0.85/0.60. AccumulatedEpisode. |
| scene_segmentation.py | poc/r2_phase_research/ | 9 mega-episodes --> 105 scenes. 64% human-scale episodes. CogQ=0.7117. |
| CogQ framework | poc/r2_phase_research/ | 8-metric cognitive quality scoring. Scene-level CogQ=0.7117. 7/8 scenarios. |

**Key research findings**:

- EVOLVE threshold 0.40 is dead code: zero fires in 275 reconciliations (removed in favor of K1 signals)
- Batch size is dominant lever: bs300 sweet spot, not threshold tuning
- AccumulatedEpisode with reinforce_importance_boost=0.10 per REINFORCE
- Evolve chains tracked via supersedes_id

---

## 14. Exit Criteria (Acceptance Gates)

- [ ] TruthLayerRegistry covers all 8 truth tables with complete metadata
- [ ] 7 IdentityStrategy implementations pass unit tests with known inputs
- [ ] truth_candidates_query syscall handles embedding, key, and hybrid queries
- [ ] ReconciliationFramework.reconcile() produces correct decisions for all layers
- [ ] WriteDecisionRouter produces correct StagedWrites for all 6 actions across all layers
- [ ] R2, R3, R4, R5 migrated to framework (zero bespoke matching logic remains)
- [ ] R6 collects pre-built StagedWrites (12+ assemble methods deprecated)
- [ ] Old ReconciliationEngine and TruthQueryService deprecated
- [ ] M8-FULL-01 regression: zero decision drift before vs after
- [ ] Adding new truth layer requires ONLY: TruthLayerSpec + IdentityStrategy (zero framework changes)
- [ ] Structured summaries contain full JSON schema (thread/goal distributions, affect trajectory, per-event records)
- [ ] Embeddings regenerate on EXTEND/EVOLVE; MRR does not degrade
- [ ] Per-batch lifecycle metrics emitted for all layers
- [ ] Each lifecycle action independently disableable via config flags

---

## 15. Execution Order (Build Sequence)

```
1. TruthLayerRegistry          -- pure data, no runtime, enables everything
2. IdentityStrategy (x7)       -- per-layer matching, depends on registry
3. truth_candidates_query      -- unified truth read, depends on registry
4. WriteDecisionRouter         -- data-driven writes, depends on registry
5. ReconciliationFramework     -- core machine, depends on 1-4
6. Migrate R3                  -- backward compat proof (most complete current user)
7. Migrate R2                  -- st_epi matching via framework
8. Migrate R4                  -- entity/edge gains EXTEND/EVOLVE/CONTRADICT
9. Migrate R5                  -- dream outputs get reconciliation
10. Simplify R6                -- orchestrator only, no assembly
11. Structured Summaries       -- universal summary generator (absorbed M7 7.3)
12. Embedding Regeneration     -- centroid recompute on EXTEND/EVOLVE (absorbed M7 7.4)
13. Lifecycle Observability    -- metrics + logs across all layers (absorbed M7 7.5)
```

---

## 16. Dependencies and Constraints

### Prerequisites (Must Exist Before Starting)

- M5 Hebbian boost: DONE
- M6 production episode quality: DONE
- K1 signal pipeline (M7 7.2.0): DONE
- P03EventState carries K1 correction fields: DONE

### Constraints

- R7 remains a blind StagedWrite executor -- framework must produce complete StagedWrites
- Existing bespoke syscalls remain for non-reconciliation use cases
- ReconciliationAction enum unchanged -- same values used by new framework
- StagedWrite type unchanged -- produced by WriteDecisionRouter
- st_hipp_events schema not modified -- framework reads via P03EventState

---

## 17. Open Questions

- [ ] Storage column for structured summaries: reuse episode_summary TEXT or add JSONB column?
- [ ] PRUNE decay policy: per-layer configurable or global?
- [ ] CONTRADICT --> P06 integration: gap record schema and queue table?
- [ ] Multi-centroid recomputation on EXTEND: recompute all secondary centroids or only affected?
- [ ] Performance budget for reconcile_batch(): acceptable latency per candidate?
- [ ] Feature flag granularity: per-action, per-layer, or per-action-per-layer?

---

## 18. ADR Requirements

The following ADRs should exist before implementation begins:

- [ ] ADR: Universal Reconciliation Framework adoption (replacing per-phase bespoke logic)
- [ ] ADR: Two-tier decision model (K1 signals vs K0 similarity)
- [ ] ADR: TruthLayerRegistry as single source of truth for layer metadata
- [ ] ADR: truth_candidates_query syscall design (embedding/key/hybrid paths)
- [ ] ADR: Structured summary storage strategy (TEXT reuse vs JSONB column)

---

# PART 2: Per-Phase Reconciliation Analysis

---

## 19. Phase Applicability Summary

| Phase | Needs Reconciliation? | Current State | Target State |
|-------|----------------------|---------------|-------------|
| **R0** | NO | Read-only batch selector. Loads events from st_hipp_events + st_epi. No matching, no writes. | Unchanged |
| **R1** | NO | Pure importance scoring. Reads st_learned_weights. No truth writes. | Unchanged |
| **R2** | YES (HEAVY) | 3 bespoke matching operations hardcoded in r2_episodic_integrator.py | `framework.reconcile(target_layer="st_epi")` replaces REINFORCE + EXTEND matching |
| **R3** | YES (HEAVIEST) | Contains current ReconciliationEngine + TruthQueryService with 12+ scattered registries | Old engine replaced entirely by ReconciliationFramework |
| **R4** | YES (COMPLEX) | EntityDisambiguator + AmbiguousEntityResolver + ConfidenceRouter. Only CREATE/UPDATE actions. | Gains EXTEND/EVOLVE/CONTRADICT. Fixes st_social duplication. |
| **R5** | YES (CRITICAL GAP) | ZERO reconciliation. Blindly passes all outputs to R6. | All dream outputs reconciled before staging |
| **R6** | YES (SIMPLIFICATION) | 12+ assemble_*_writes methods with hardcoded column mappings (2,034 lines) | Becomes pure StagedWrite collector |
| **R7** | NO | Blind StagedWrite executor. Same P03StagedWrites interface. | Unchanged |
| **R8** | NO | Pure event emission from st_outbox. No truth matching. | Unchanged |

---

## 20. R0 / R1 / R8: Confirmed No Reconciliation Required

### 20.1 R0 Batch Selector

- **Operations**: Reads st_hipp_events (50+ fields) and st_epi (existing episodes) into P03EventState
- **Output**: Pure data loading and enrichment, no writes to any truth tables
- **Matching**: No matching logic. R0 is a field-loading registry.
- **Verdict**: Reconciliation engine not applicable -- R0 is read-only ingestion

### 20.2 R1 Importance Scorer

- **Operations**: Scores event importance using CONFIG_B formula (8 weights, 6-tier priority tiers)
- **Output**: Emits ScoredEvent with surprise_factor, identity_factor, priority_tier -- enrichment only
- **Dependencies**: Optionally reads st_learned_weights for adaptive weight learning (read-only reference data)
- **Verdict**: Reconciliation engine not needed -- R1 is pure scoring with no state mutations

### 20.3 R8 Event Emitter

- **Operations**: Reads st_outbox, stages completion and gap events for external consumption
- **Output**: All logic is event assembly (completion payload, gap priority sorting, dedup within cycle only)
- **Verdict**: Reconciliation engine not applicable -- R8 is pure emission with no truth consolidation

### 20.4 Edge Cases Considered

| Phase | Edge Case | Finding |
|-------|-----------|---------|
| R0 | Could batch selection miss duplicates? | No -- R0 does not deduplicate; R2 handles dedup via HDBSCAN clustering |
| R1 | Could weight learning introduce version conflicts? | No -- R1 reads st_learned_weights, does not write. Weight store is managed externally. |
| R8 | Could gap emission create duplicate topics? | No -- Gaps use 1-hour dedup window and circuit breaker. Outbox pattern is idempotent. |

---

## 21. R2: Episodic Integration (target_layer = st_epi)

### 21.1 Current Bespoke Logic (3 Operations)

R2 currently implements 3 distinct reconciliation operations, all hardcoded in r2_episodic_integrator.py:

**Operation 1: REINFORCE Matching (pre-clustering)**

- Function: `_query_existing_episodes()` + `_match_events_to_existing_episodes()`
- Logic: Queries st_epi for ACTIVE episodes in 7-day lookback window. Compares each event's embedding to existing episode centroids via cosine similarity. If similarity >= 0.85, marks event with ReconciliationAction.REINFORCE.
- Sets: episode_match_id, episode_match_similarity, episode_match_version on matched events
- Output: Splits incoming events into (matched, novel) -- matched events bypass clustering

**Operation 2: EXTEND Matching (post-clustering)**

- Class: `CrossBatchExtendMatcher.match()`
- Logic: After HDBSCAN + purity + merge produces clusters, compares newly-formed cluster centroids to existing episode centroids via cosine >= 0.60. If match, marks cluster for EXTEND.
- Research finding: At batch_size=100, reconciliation thresholds had zero effect -- within-batch clustering already consolidates; cross-batch EXTEND rarely fires. At batch_size=300, EXTEND activates.

**Operation 3: Thread Purity + Same-Thread Merge (intra-batch correction)**

- Classes: `ThreadPurityCorrector.correct()` + `SameThreadMerger.merge()`
- Logic: Post-HDBSCAN, splits clusters containing events from 2+ distinct narrative_thread_id groups. Then re-merges pure clusters sharing same thread if cosine >= 0.70 + temporal gap < 4h.
- Impact: must_separate metric: 0.83 --> 1.00 after correction. must_link metric: 0.33 --> 1.00 after merge.

### 21.2 What R2 Produces

EpisodeCluster output for st_epi/st_vec persistence:

- cluster_id (UUID), member_event_ids, member_contexts (ObservationContext)
- centroid_embedding_id (FK to st_vec, single canonical, 768-dim L2-normalized)
- temporal_start/end, cohesion_score (1 / (1 + variance))
- Enriched: dominant_sentiment, dominant_emotion, activity_type_ultrabert, location_type, participants_json
- Metadata: ambiguity_score, title, summary
- reconciliation_action: "EXTEND" or None (set by extend_matcher)

### 21.3 Framework Integration Points

| Current Operation | What Framework Replaces | What Stays In R2 |
|-------------------|------------------------|-------------------|
| REINFORCE matching (event vs existing episode) | `framework.reconcile(target_layer="st_epi")` per event pre-clustering | -- |
| EXTEND matching (cluster vs existing episode) | `framework.reconcile(target_layer="st_epi")` per cluster post-clustering | -- |
| Thread purity correction | -- | YES: intra-batch clustering refinement, not truth reconciliation |
| Same-thread merge | -- | YES: intra-batch clustering refinement, not truth reconciliation |
| HDBSCAN clustering | -- | YES: core algorithm, not reconciliation |
| Noise/singleton filtering | -- | YES: quality gate before reconciliation |

**Key insight**: Thread purity and same-thread merge are intra-batch clustering corrections. They refine what clusters look like BEFORE reconciliation. The framework handles steps 1 (REINFORCE) and 2 (EXTEND) only.

### 21.4 EpisodicIdentity Strategy Design

Current R2 identity matching uses composite anchors:

- **For REINFORCE**: Event embedding vs episode centroid embedding (cosine >= 0.85)
- **For EXTEND**: Cluster computed centroid vs episode centroid (cosine >= 0.60)
- **Thread bonus**: narrative_thread_id match adds +0.15 bonus to identity score

**Currently missing from identity** (used in clustering but NOT in matching):

- place_id (GAP-002 spatial identity) -- not used in REINFORCE/EXTEND matching
- social_context + participants_json (social set intersection)
- activity_type_ultrabert (activity congruence)
- temporal_orientation (narrative continuity)

This is too narrow for the reconciler we actually want. The engine does not need all 143
columns from `st_hipp_events`; it needs a stable, high-value subset. The POC and R2 epic plan
both point to the same shape: embeddings are retrieval and semantic context, while the final
episodic decision is made from a compact feature set.

**Finalized EpisodicIdentity design**:

- Retrieval step: use embedding similarity to fetch candidate episodes
- Decision step: score only a bounded episodic subset
- Keep K1 correction / contradiction as Tier 1 bypasses, never mixed into the numeric score

**Bounded episodic subset for `st_epi`**:

- semantic: embedding cosine, activity_type_ultrabert / activity_type, topic overlap
- thread: narrative_thread_id when present, inferred-thread analogue when not
- participant: participants_json overlap, focus/primary actor match, relationship context when available
- spatial: place_id exact match, geohash_6 / location hierarchy support, location match
- social/context: social_context, source_type
- temporal: conversation_anchor_ms distance, temporal_orientation, temporal links / anchor continuity

**What becomes EpisodicIdentity**:

```
features = {
    "cosine_sim": cosine_similarity(candidate.embedding, existing.centroid_embedding),
    "participant_overlap": participant_overlap(candidate, existing),
    "focus_match": focus_match(candidate, existing),
    "topic_overlap": topic_overlap(candidate, existing),
    "location_match": location_match(candidate, existing),
    "source_type_match": source_type_match(candidate, existing),
    "social_context_match": social_context_match(candidate, existing),
    "thread_signal": thread_signal(candidate, existing),
}

score = episodic_policy(features)
return IdentityResult(match_score=score, match_type=HYBRID_MATCH)
```

**Design constraint**: `st_epi` should remain dependent on a small, explicit subset of signals.
Do not couple episodic reconciliation to the full `st_hipp_events` contract just because those
columns exist.

### 21.5 K1 Signal Integration for R2

- When P03EventState.correction_signal = true: framework returns EVOLVE for that episode regardless of similarity score. Old episode marked SUPERSEDED, new version created with supersedes_id.
- When P03EventState.contradiction_signal = true: framework returns CONTRADICT. Gap record inserted into st_learning_queue for P06 resolution.
- Signal pipeline already implemented (M7 Issue 7.2.0 DONE). ReconciliationCandidate reads these fields from P03EventState.

### 21.6 R2 Migration Risks

**CRITICAL: Narrative Thread Short-Circuit**

Current R2 has a distance-capping behavior: when narrative dimension reports exact/semantic same-thread with confidence >= 0.7, total ensemble distance is capped at 0.20. This forces same-thread events to cluster together regardless of other dimensions. Example: maya_fears and dad_knee_recovery are semantically similar (both "health concerns") but different threads. Without short-circuit, they cluster together incorrectly.

This behavior lives in composite distance computation (clustering), NOT in REINFORCE/EXTEND matching. It survives framework migration because the framework replaces matching, not clustering.

**HIGH: Thread Purity Correction Must Run Before Framework**

Thread purity and same-thread merge are pre-reconciliation steps. The framework reconcile() call must happen AFTER these corrections produce finalized clusters. Migration sequence: HDBSCAN --> thread purity --> same-thread merge --> framework.reconcile() per cluster.

---

## 22. R3: Dedup / Decay (ALL truth layers via ReconciliationEngine)

### 22.1 Current ReconciliationEngine (Being Replaced)

R3 IS the current reconciliation engine. The full execution flow:

```
R3.execute()
  |
  +-- R3.1: Dedup (SimHash + TwoStage embedding) --> is_duplicate, novelty_score
  +-- R3.2: ...
  +-- R3.3: Decay (UnifiedDecayEngine) --> decay_factor, decay_classification
  +-- R3.4: Retention (RetentionEnforcer) --> KEEP / ARCHIVE / TOMBSTONE
  +-- ...
  +-- R3.9: Reconciliation (LAST step)
        |
        +-- reconcile_batch(events[])
              |
              FOR each event:
                +-- ReconciliationEngine.decide(event)
                      |-- _check_overrides(): is_duplicate --> SKIP; tombstone --> PRUNE
                      |-- _get_event_embedding(): extract 768-dim embedding
                      |-- _find_candidates(): TruthQueryService.find_candidates() with 5s timeout
                      |     +-- FOR each layer in DEFAULT_TRUTH_LAYERS (5 layers):
                      |           +-- _query_layer(): JOIN {layer} to st_vec, cosine similarity
                      |-- _find_best_match(): iterate candidates, compute cosine, return top match
                      |-- _determine_action(): threshold cascade (0.85/0.60/0.40)
                      |-- _compute_confidence(): Bayesian update
                      |-- _build_reason(): human-readable explanation
                      |
                      v
                ReconciliationDecision --> event.set_reconciliation()
```

### 22.2 Layer Coverage (5 of 8 -- Incomplete)

```
DEFAULT_TRUTH_LAYERS = ("st_epi", "st_sem", "st_procedural", "st_social", "st_prospective")
```

**Missing from reconciliation**: st_kg_dom, st_kg_edges (only in DECAY_LAYERS, not queried by reconciliation)

### 22.3 Scattered Registries (12 Locations)

| Registry | Location | Layers Covered |
|----------|----------|----------------|
| LAYER_PK_COLUMNS | truth_query_service.py:46-54 | 5 layers |
| LAYER_CONFIDENCE_COLUMNS | truth_query_service.py:55-63 | 5 layers |
| LAYER_EMBEDDING_COLUMNS | truth_query_service.py:31-39 | 5 layers |
| DECAY_LAYERS | truth_query_service.py:154-160 | 5 layers (includes st_kg_dom) |
| LAYER_ENTITY_TYPE_COLUMNS | truth_query_service.py:168-173 | 5 layers |
| LAYER_LAMBDAS | decay_engine.py:60-69 | 8 layers |
| DEFAULT_TRUTH_LAYERS | reconciliation_engine.py:77-82 | 5 layers |
| DEFAULT_REINFORCE_THRESHOLD | reconciliation_engine.py:54 | global |
| DEFAULT_EXTEND_THRESHOLD | reconciliation_engine.py:55 | global |
| DEFAULT_EVOLVE_THRESHOLD | reconciliation_engine.py:56 | global |
| DEFAULT_CANDIDATE_TOP_K | reconciliation_engine.py:59 | global |
| DEFAULT_MIN_SIMILARITY | reconciliation_engine.py:60 | global |

**Problem**: Adding a new truth layer requires updating 4+ separate dictionaries across 2+ files. TruthLayerRegistry consolidates all 12 into one.

### 22.4 Dedup vs Reconciliation (Separate Systems)

| Aspect | Dedup (R3.1) | Reconciliation (R3.9) |
|--------|-------------|----------------------|
| Input | event.content_text + existing_events | event.embedding_768 + truth layers |
| Comparison | SimHash (64-bit) + TwoStage embedding | Cosine similarity vs truth records |
| Output | is_duplicate (bool), novelty_score | REINFORCE/EXTEND/EVOLVE/CREATE/SKIP/PRUNE |
| Override | -- | is_duplicate=true --> SKIP; tombstone --> PRUNE |

**Gap**: Novelty score from R3.1 dedup is computed but never consumed by reconciliation. No integration between dedup confidence and reconciliation confidence.

### 22.5 Decay / PRUNE Mapping

R3 temporal decay maps cleanly to the framework PRUNE action:

```
UnifiedDecayEngine:
  decay_factor = exp(-lambda_eff * days_since_last_observation)

  Per-layer lambdas:
    st_hipp_events: 0.100  (7-day half-life)
    st_prospective: 0.020
    st_procedural:  0.010
    st_kg_edges:    0.008
    st_epi:         0.005
    st_sem:         0.003
    st_social:      0.002
    st_kg_dom:      0.001  (693-day half-life)

  Classification:
    decay_factor >= 0.10  --> KEEP (ACTIVE)
    decay_factor 0.01-0.10 --> ARCHIVE_CANDIDATE
    decay_factor < 0.01   --> PRUNE_CANDIDATE (TOMBSTONE)
```

When prune_decision = TOMBSTONE, ReconciliationEngine._check_overrides() returns PRUNE action, overriding all similarity logic. This maps directly to the framework's timer-based PRUNE sweep.

### 22.6 R3 Migration Path

R3 is the FIRST migration target because:

1. It contains the current ReconciliationEngine being replaced -- migration proves backward compat
2. It has the most complete test surface to validate against
3. TruthQueryService's scattered registries are the primary consolidation target

**Migration steps**:

1. Inject ReconciliationFramework into R3DedupDecay
2. Replace reconcile_batch() to call framework.reconcile_batch() instead of ReconciliationEngine.decide()
3. Framework produces identical decisions for the same 5 layers
4. Verify zero decision drift on existing test corpus
5. Deprecate ReconciliationEngine and TruthQueryService
6. Enable st_kg_dom and st_kg_edges in framework (layers R3 never queried before)

### 22.7 R3 Migration Risks

- **Override behavior preservation**: is_duplicate --> SKIP and tombstone --> PRUNE overrides must be replicated in framework. These run BEFORE any similarity computation.
- **Sequential processing**: Current R3 reconciles one event at a time (sequential loop). Framework's reconcile_batch() must match this behavior or prove parallel safety.
- **Adaptive learned weights**: R3 uses st_learned_weights for novelty bonus and merge thresholds. These are separate from reconciliation and stay in R3 -- but ensure no accidental coupling.

---

## 23. R4: KG Consolidation (target_layer = st_kg_dom, st_kg_edges, st_social)

### 23.1 Current Entity Identity Pipeline (4 Steps)

```
Step 1: Clustering
  +-- Group by type:normalized_name
  +-- Select canonical_name by frequency > proper_case > length
  +-- Result: EntityCluster[] (same-name clusters)

Step 2: Alias Detection
  +-- AliasDetector.detect() pairwise within each type
  +-- 4-signal score: STRING(0.25) + EMBEDDING(0.30) + NICKNAME(0.25) + CO_OCC(0.20)
  +-- Threshold 0.70 --> merge secondary into primary cluster
  +-- Result: Merged EntityCluster[]

Step 3: Disambiguation
  +-- Query st_kg_dom for fuzzy candidates (kg_candidates_fuzzy_query)
  +-- EntityDisambiguator.compute_similarity():
  |     - Embedding similarity (cosine): per-type weights
  |     - String similarity (rapidfuzz): token_sort_ratio + partial_ratio
  |     - Opposition detection: sim_emb > 0.90 AND sim_str < 0.40 --> penalty -0.25
  |     - Per-type weights: PERSON=0.50/0.50, FAMILY=0.30/0.70, CONCEPT=0.85/0.15
  +-- Combined score = (embedding_weight * sim_emb) + (string_weight * sim_str) - opposition_penalty
  +-- Threshold 0.85 --> merge with existing entity

Step 4: Confidence Routing
  +-- >= 0.85 --> AUTO_RESOLVED (CREATE or UPDATE_ENTITY with confidence boost)
  +-- 0.60-0.85 --> RESOLVED_FLAGGED (UPDATE_ENTITY, mark for review)
  +-- < 0.60 --> GAP_EMITTED (emit to st_learning_queue for P06 resolution)
```

### 23.2 Edge Identity

Compound key: `(source_entity_id, target_entity_id, relation_type)`

| Type | Method | Notes |
|------|--------|-------|
| UltraBERT relations | Infer from extracted_relations_json per event | Priority map: FAMILY=4 > FRIEND=3 > COLLEAGUE=2 > ACQUAINTANCE=1 |
| Hebbian edges | Pairwise within event | No dedup; Hebbian strengthens weights across cycles |
| Causal edges | Temporal precedence ratio (Granger causality) | CAUSES > FOLLOWS > PRECEDES priority |

Edge exists in st_kg_edges --> UPDATE (observation_count++). Not exists --> CREATE.

### 23.3 Social Identity -- CRITICAL GAP

**R4 does NOT check for existing st_social records before creating new ones.**

Each consolidation cycle creates NEW SocialRelationship records without dedup. This means:

- st_social grows with duplicates across cycles
- No REINFORCE for existing relationships (interaction_count resets per cycle)
- Emotional valence averaging is per-cycle only, no historical tracking
- Relationship phase inference only uses within-cycle interaction count

**Fix via framework**: `SocialIdentity` strategy matches on participant pair --> 1.0. Framework routes to REINFORCE (existing pair, boost observation_count) instead of CREATE (duplicate row).

### 23.4 Actions Today vs After Framework

| Action | R4 Today | After Framework |
|--------|----------|-----------------|
| CREATE | CREATE_ENTITY / CREATE_EDGE (new entity/edge) | ReconciliationAction.CREATE |
| UPDATE | UPDATE_ENTITY / UPDATE_EDGE (observation_count++) | ReconciliationAction.REINFORCE |
| EXTEND | NOT SUPPORTED | Entity gains new aliases, new attributes (append to aliases_json) |
| EVOLVE | NOT SUPPORTED | Entity fundamentally changes (person changes name, place changes type) --> version with supersedes_id |
| CONTRADICT | Partial (GAP < 0.60 --> st_learning_queue) | Automatic contradiction detection for conflicting attributes (age, type) --> P06 |
| PRUNE | NOT SUPPORTED | Entity retirement (left family, deceased) with reason trail |

### 23.5 EntityIdentity Strategy Design

```
EntityIdentity:
  # Step 1: Exact key match
  if candidate.entity_type == existing.entity_type
     AND normalize(candidate.canonical_name) == normalize(existing.canonical_name):
    return IdentityResult(score=1.0, match_type=KEY_MATCH)

  # Step 2: Fuzzy name match
  fuzzy_score = rapidfuzz.token_sort_ratio(candidate.name, existing.name) / 100
  if fuzzy_score >= 0.85:
    return IdentityResult(score=fuzzy_score, match_type=KEY_MATCH)

  # Step 3: Embedding fallback (if both have embeddings)
  if candidate.embedding and existing.embedding:
    cosine = cosine_similarity(candidate.embedding, existing.embedding)
    # Opposition detection
    if cosine > 0.90 and fuzzy_score < 0.40:
      cosine -= 0.25  # penalty for antonym pairs
    # Per-type weighting
    combined = (type_weights[entity_type].embedding * cosine
              + type_weights[entity_type].string * fuzzy_score)
    return IdentityResult(score=combined, match_type=HYBRID_MATCH)

  return IdentityResult(score=0.0, match_type=NO_MATCH)
```

### 23.6 R4 Migration Path

1. Wire EntityIdentity strategy wrapping AmbiguousEntityResolver scoring logic
2. Wire EdgeIdentity strategy for compound key matching
3. Wire SocialIdentity strategy for participant pair matching (fixes duplication gap)
4. Replace R4 entity matching with `framework.reconcile(target_layer="st_kg_dom", identity_key={entity_type, canonical_name})`
5. Replace R4 edge matching with `framework.reconcile(target_layer="st_kg_edges", identity_key={source, target, type})`
6. Enable EXTEND for entities gaining new aliases
7. Enable EVOLVE for entities fundamentally changing (name change, type change)
8. Enable CONTRADICT for conflicting attributes --> P06

### 23.7 R4 Migration Risks

- **Multi-step disambiguation complexity**: Entity disambiguation is a 4-step pipeline (clustering --> alias --> disambiguation --> confidence routing). The framework must support the same per-type weighted scoring. EntityIdentity cannot be a simple cosine-only strategy.
- **AdaptiveMergeThresholds**: R4 learns per-type thresholds from P06 FP/FN feedback. Framework thresholds (0.85/0.60) are global. Per-layer or per-type threshold overrides needed.
- **Cascade semantics**: EntityMerger.merge_entities() updates 7 tables. Framework EVOLVE must not accidentally trigger cascades.
- **Alias detection stays in R4**: AliasDetector operates on intra-batch entity clustering (same as thread purity in R2). It runs BEFORE reconciliation against existing truth.

---

## 24. R5: Dream Explorer (target_layer = st_sem, st_procedural, st_prospective)

### 24.1 The Zero-Reconciliation Gap

**R5 does ZERO reconciliation today.** All outputs flow blindly from R5 --> R6 --> R7 with no identity matching, no duplicate detection, no conflict detection.

Evidence:

- No imports of ReconciliationEngine in r5_dream_explorer.py or dream_explorer.py
- No calls to truth_service.find_candidates() or framework.reconcile()
- No configuration for reconciliation in r5_config.py
- `_stage_outputs()` method simply copies lists to envelope fields with no filtering

### 24.2 R5 Output Types and Layer Mapping

| # | Output Type | Source Algorithm | Target Layer | Reconciliation Needed? | Status |
|---|------------|------------------|-------------|----------------------|--------|
| 1 | Insight | BGT-SM (Bisociative Graph Traversal) | st_sem | YES -- duplicate concept pairs not caught | ACTIVE (1,208 lines) |
| 2 | RoutineCandidate | RoutineDetector | st_procedural | YES -- same signature creates duplicates | ACTIVE (710 lines) |
| 3 | RoutineOptimization | TDL-HCO (Temporal Difference Learning) | st_procedural | YES -- links to existing routines | ACTIVE (1,025 lines) |
| 4 | ProspectiveMemory | SPC-UQ (Episodic Simulator) | st_prospective | YES -- duplicate intentions | PARTIAL (needs refocus) |
| 5 | IntentSignal (6 types) | IntentSignalDetector | routing only | NO -- metadata, not truth writes | ACTIVE (631 lines) |
| 6 | CounterfactualScenario | CPN | st_prospective | NO -- scheduled for deletion in M5C | DELETE CANDIDATE |
| 7 | MCTSScenario | TPN-MCTS | st_prospective | NO -- scheduled for deletion in M5C | DELETE CANDIDATE |

### 24.3 Duplicate Scenarios (Today's Behavior)

**Scenario A: Duplicate Routine**

1. RoutineDetector analyzes episodes, detects signature: activity_type='coffee', time_bucket='08:00-09:00'
2. Same signature already exists in st_procedural from previous cycle
3. R5 does NOT check st_procedural
4. R6 receives RoutineCandidate, passes to R7
5. R7 writes INSERT --> duplicate routine in st_procedural

**Scenario B: Contradictory Insight**

1. BGT-SM random walk discovers: "Maya frequents coffee shop" (PMI 0.72)
2. st_sem already contains: "Maya avoids coffee shop" (confidence 0.95)
3. R5 does NOT check st_sem for conflicts
4. R6 passes Insight, R7 writes INSERT
5. Both records coexist --> silent data incoherence
6. K1 query returns both; LLM must resolve manually

**Scenario C: Duplicate Prospective Memory**

1. SPC-UQ generates: "Maya will visit coffee shop Saturday 2pm"
2. st_prospective already contains: "Maya avoids coffee shops" (confidence 0.95)
3. R5 does NOT check
4. Two contradictory intentions in same layer --> query-time confusion

### 24.4 Framework Integration Points

```
R5DreamExplorer.run()
  |
  +-- Load algorithm outputs (insights, routines, etc.)
  |
  +-- FOR EACH output by type:
  |
  +-- Insight --> framework.reconcile(
  |       target_layer="st_sem",
  |       identity_key={concept_a_id, concept_b_id})
  |     Decision: CREATE / REINFORCE / EXTEND / CONTRADICT
  |
  +-- RoutineCandidate --> framework.reconcile(
  |       target_layer="st_procedural",
  |       identity_key={routine_name, time_pattern})
  |     Decision: CREATE / REINFORCE / EVOLVE
  |
  +-- RoutineOptimization --> framework.reconcile(
  |       target_layer="st_procedural",
  |       identity_key={routine_id})
  |     Decision: EXTEND (add optimization) / CREATE (new routine)
  |
  +-- ProspectiveMemory --> framework.reconcile(
  |       target_layer="st_prospective",
  |       identity_key={intention_type, trigger_condition})
  |     Decision: CREATE / REINFORCE / EVOLVE
  |
  +-- CounterfactualScenario --> NO RECONCILIATION (delete in M5C)
  +-- IntentSignal --> NO RECONCILIATION (routing only)
  +-- MCTSScenario --> NO RECONCILIATION (delete in M5C)
  |
  +-- Return ReconciliationResults (not raw outputs) to R6
```

### 24.5 Special Handling: Dream Confidence Discount

R5 outputs are speculative (LLM-generated, graph-walked). They are NOT observation-backed truth.

**Problem**: BGT-SM walks KG and discovers "If Maya visits Park X, she likely visits Cafe Y" (PMI 0.72). No observation evidence exists for this connection. Output flows to st_sem with same confidence as witnessed connections.

**Requirement**: The framework should apply a source_phase confidence modifier:

- R2/R3/R4 outputs (observation-backed): confidence_modifier = 1.0
- R5 outputs (dream/speculative): confidence_modifier = 0.6-0.8 (configurable)

This ensures dream-sourced REINFORCE does not overpower observation-sourced truth.

### 24.6 R5 Migration Risks

- **Cold-start**: All R5 algorithms work on accumulated truth (st_epi, st_kg_dom, etc.). On cold start with empty tables, R5 still runs and produces outputs from empty inputs. Framework must handle zero-candidate queries gracefully (no existing records --> always CREATE).
- **Stage 5 ObservationEvidenceLoader**: Planned but NOT IMPLEMENTED. Stage 5 would validate dream outputs against observation evidence. Until implemented, all R5 outputs are unverified.
- **SPC-UQ invariant violation**: SPC-UQ marks reconstructions is_canonical=False, creating future dedup issues. Framework must not REINFORCE a non-canonical record.

---

## 25. R6: Staging (Simplification Target)

### 25.1 Current TruthWriteAssembler (12+ Methods)

| # | Method | Layer | Action Types | Record Fields |
|---|--------|-------|-------------|---------------|
| 1 | assemble_epi_writes | st_epi | INSERT, UPDATE (REINFORCE) | 30+ columns |
| 2 | assemble_sem_writes | st_sem | INSERT (CREATE) | 29 columns |
| 3 | assemble_procedural_writes | st_procedural | INSERT (CREATE) | 20 columns |
| 4 | assemble_routine_candidate_writes | st_procedural | INSERT (alternative) | RoutineCandidate objects |
| 5 | assemble_social_writes | st_social | INSERT (CREATE) | 39 params |
| 6 | assemble_prospective_writes | st_prospective | INSERT (CREATE) | 17+ columns |
| 7 | assemble_insight_writes | st_sem | INSERT (R5 Insight) | insight fields |
| 8 | assemble_counterfactual_writes | st_sem | INSERT (R5 CounterfactualScenario) | scenario fields |
| 9 | assemble_routine_optimization_writes | st_procedural | INSERT, UPDATE | optimization fields |
| 10 | assemble_mcts_writes | st_mcts_decisions | INSERT (dead code -- deleting in M5D) | MCTS scenario |
| 11 | assemble_intent_signal_writes | st_prospective, st_sem | INSERT (GAP-001 routing) | 6 intent types |
| 12 | assemble_learning_queue_writes | st_learning_queue | INSERT | gap records |

**Additional assemblers** (separate classes):

- KGWriteAssembler: assemble_entity_writes, assemble_edge_writes (st_kg_dom, st_kg_edges)
- IntentSignalAssembler: Routes 6 signal types to 3 different truth layers

**Total**: 2,034+ lines of per-layer column mapping code.

### 25.2 Column Mapping Approach (Hardcoded)

Each assemble method constructs record_data dicts with hardcoded column names:

```
# Example: assemble_sem_writes (line 705)
record_data = {
    "pattern_id": pattern.pattern_id,
    "tenant_id": self.tenant_id,
    "pattern_text": _generate_pattern_name(state),
    "confidence": 0.8,
    "observation_count": 1,
    # ... 25+ more columns
}
```

**Problem**: Column lists are hardcoded per-method. Changes to truth table columns require code edits in assembler methods plus corresponding layer writer methods.

### 25.3 After Framework Migration

R6 becomes a pure StagedWrite collector:

```
BEFORE (current):
  R2/R3/R4/R5 outputs --> R6 TruthWriteAssembler (12+ methods) --> P03StagedWrites --> R7

AFTER (framework):
  R2/R3/R4/R5 --> framework.reconcile() per output --> ReconciliationResult.staged_write --> R6 collects --> P03StagedWrites --> R7
```

R6 responsibilities that SURVIVE:

- Dedup metadata population (DedupMetadataPopulator -- separate from reconciliation)
- Reconciliation recording (ReconciliationRecorder -- audit trail in st_hipp_events.reconciliation_json)
- Manifest validation (ManifestValidator -- 7 validation rules)
- FK dependency ordering (P03StagedWrites.get_all_writes_ordered())
- Outbox event assembly (OutboxEventAssembler)

R6 responsibilities that are REMOVED:

- All 12+ assemble_*_writes methods (replaced by WriteDecisionRouter)
- Per-layer column mapping (moves to TruthLayerSpec merge rules)

### 25.4 Dedup Metadata vs Reconciliation Metadata (Separate Streams)

| Stream | Component | Output | Storage |
|--------|-----------|--------|---------|
| Dedup | DedupMetadataPopulator | near_duplicates_json, novelty_score, is_duplicate | st_hipp_events.near_duplicates_json |
| Reconciliation | ReconciliationRecorder | action, best_match_id, best_match_layer, similarity_score | st_hipp_events.reconciliation_json |

Both metadata streams remain separate after migration. WriteDecisionRouter produces reconciliation metadata; dedup metadata is populated independently by R3.1 dedup engine.

### 25.5 Manifest Validation (Survives Migration)

ManifestValidator enforces 7 rules before R7 handoff:

1. Layer validity: only known layers in P03StagedWrites
2. Idempotency key format: matches `p03:{type}:{cycle_ulid}:{entity}`
3. FK integrity: st_kg_edges source/target exist in st_kg_dom
4. Event coverage: all event IDs in batch have writes or skip marker
5. Outbox minimum: at least completion event present
6. Duplicate records: no duplicate (layer, record_id) pairs within batch
7. Version conflict threshold: >10% conflicts --> DLQ entire batch

All 7 rules apply regardless of whether StagedWrites come from TruthWriteAssembler or WriteDecisionRouter.

### 25.6 R6 Migration Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Column schema mismatch (WriteDecisionRouter omits columns layer writers expect) | HIGH | Document all column schemas in WriteDecisionRouter contract; cross-validate with R7 layer writers |
| Idempotency key generation differs | MEDIUM | WriteDecisionRouter must use same p03:{type}:{cycle_ulid}:{entity} pattern |
| ObservationContext not wired through | MEDIUM | Layer writers depend on attached ObservationContext for observation recording; WriteDecisionRouter must preserve this |
| FK dependency order violated | HIGH | WriteDecisionRouter uses same P03StagedWrites.get_all_writes_ordered() |
| Intent signal routing lost (6 types to 3 layers) | MEDIUM | Router must route: Reminder/Decision --> st_prospective, Lesson/Emotional --> st_sem, Milestone/QueryBoost --> st_kg_dom + st_kg_edges |
| MCTS dead code path | LOW | Remove MCTS routing entirely in M5D before migration |

---

## 26. R7: Truth Writer (Unchanged)

### 26.1 Confirmed: R7 Remains Blind Executor

R7 does NOT interpret reconciliation_action or consolidation_status. R7 only executes WriteOperation (INSERT/UPDATE/ARCHIVE/TOMBSTONE) via layer writers. The framework changes WHAT PRODUCES the StagedWrites, not how R7 executes them.

### 26.2 Write Order (FK-Constrained)

```
1. st_vec               <-- Vectors (no FKs, foundational)
2. st_kg_dom            <-- Entities (referenced by edges)
3. st_kg_edges          <-- Edges (FK: source/target --> st_kg_dom)
4. st_epi               <-- Episodes
5. st_sem               <-- Semantic patterns
6. st_procedural        <-- Routines
7. st_social            <-- Social relationships
8. st_prospective       <-- Intentions
9. st_learning_queue    <-- Gap queue
10. st_hipp_events      <-- Event status update
```

### 26.3 Layer Writers (8 Classes)

| Class | Table | Operations | Key Feature |
|-------|-------|-----------|-------------|
| EpisodicLayerWriter | st_epi | INSERT, REINFORCE, ARCHIVE, TOMBSTONE | jsonb_agg DISTINCT source events, version locking |
| SemanticLayerWriter | st_sem | INSERT, REINFORCE (+0.05), EXTEND, EVOLVE | REINFORCE_BOOST=0.05, marks non-canonical |
| KGLayerWriter | st_kg_dom + st_kg_edges | INSERT, UPDATE, ARCHIVE, TOMBSTONE, EXTEND, track_merge | Entity/edge dedup, FK validation, merge tracking |
| ProceduralLayerWriter | st_procedural | INSERT, REINFORCE (x1.1), EXTEND | REINFORCE_FACTOR=1.1, multiplicative boost |
| SocialLayerWriter | st_social | INSERT, REINFORCE (EMA sentiment), EXTEND, DECAY (x0.95) | EMA sentiment, trajectory rolling window (20), strength decay |
| ProspectiveLayerWriter | st_prospective | INSERT, EXTEND, COMPLETE, COUNTERFACTUAL | Status transitions: pending --> completed/cancelled |
| VectorLayerWriter | st_vec | INSERT, UPDATE (aggregation) | P08 circuit breaker, embedding aggregation |
| MCTSLayerWriter | st_mcts_decisions | INSERT (dead code) | Delete in M5D |

### 26.4 R7 Impact of Framework Migration

**Zero behavior change.** R7 receives StagedWrites from WriteDecisionRouter instead of TruthWriteAssembler. The interface (P03StagedWrites container, LayerWriterProtocol, UoW transaction, FK-constrained write order, optimistic lock retry) remains identical.

---

## 27. P03 Table Ownership Map (Complete)

### 27.1 Core Truth Tables

| Table | READS | PROCESSES | STAGES (assembles writes) | WRITES (commits) |
|-------|-------|-----------|--------------------------|------------------|
| st_epi | R0 (existing episodes), R2 (episode matching), R5 (accumulated) | R2 (HDBSCAN clustering --> EpisodeCluster), R5 (EST salience -- NOT IMPL) | R6 (assemble_epi_writes) | R7 (EpisodicLayerWriter) |
| st_sem | R5 (accumulated schemas) | R2 (semantic patterns), R4 (subtype classification), R5 (BGT-SM Insights) | R6 (assemble_sem_writes, assemble_insight_writes) | R7 (SemanticLayerWriter) |
| st_procedural | R5 (accumulated routines) | R5 (TDL-HCO RoutineOptimization, RoutineDetector RoutineCandidate) | R6 (assemble_procedural_writes, assemble_routine_*) | R7 (ProceduralLayerWriter) |
| st_social | R5 (accumulated -- NOT IMPL) | R4 (social relationship extraction from participants) | R6 (assemble_social_writes) | R7 (SocialLayerWriter) |
| st_prospective | R5 (accumulated -- NOT IMPL) | R5 (SPC-UQ ProspectiveMemory, IntentSignal Reminder/Decision) | R6 (assemble_prospective_writes) | R7 (ProspectiveLayerWriter) |
| st_kg_dom | R4 (existing entity matching), R5 (accumulated) | R4 (entity extraction, disambiguation, alias, merge, subtype) | R6 (KGWriteAssembler.assemble_entity_writes) | R7 (KGLayerWriter) |
| st_kg_edges | R4 (existing edges), R5 (accumulated) | R4 (Hebbian co-occurrence, Granger causality, 9 edge enrichers) | R6 (KGWriteAssembler.assemble_edge_writes) | R7 (KGLayerWriter) |

### 27.2 Supporting Tables

| Table | READS | WRITES | Owner |
|-------|-------|--------|-------|
| st_hipp_events | R0 (batch selector) | R7 (consolidation_status UPDATE) | R0 read / R7 write |
| st_vec | R2 (embeddings for distance) | R7 (VectorLayerWriter) | R2 read / R7 write |
| st_outbox | R8 (reads staged events) | R7 (OutboxWriter), R8 (status update) | R7 create / R8 emit |
| st_learned_weights | R1, R2, R3, R4 (read) | R3, R4 (persistence of learned params) | Multi-reader/writer |
| st_consolidation_audit | -- | R1 (audit sampling 10%), R3 (prune audit) | R1/R3 audit |
| st_learning_queue | -- | R7 (via layer writes from R4 gaps) | R4 --> R6 --> R7 |
| st_observations | -- | R7 (ObservationRecorder: INSERT per truth write) | R7 observation |
| st_entity_merges | -- | R7 (KGLayerWriter.track_merge) | R7 merge audit |

### 27.3 Key Architectural Insight

**R7 is the ONLY phase that writes to truth tables.** All other phases either read from tables or produce in-memory outputs. R6 assembles all writes into P03StagedWrites. R7 commits atomically in a single PostgreSQL transaction. Write order follows FK constraints: st_vec --> st_kg_dom --> st_kg_edges --> st_epi --> st_sem --> st_procedural --> st_social --> st_prospective --> st_hipp_events.

---

## 28. Migration Priority and Risk Matrix

### 28.1 Migration Priority Order

| Priority | Phase | Reason | Risk Level |
|----------|-------|--------|-----------|
| 1 | R3 | Contains current engine being replaced. Migration proves backward compat. Most complete test surface. | MEDIUM (well-understood code) |
| 2 | R2 | Most complex bespoke matching. Highest episode quality test coverage (M8 CogQ). | HIGH (narrative short-circuit, thread purity) |
| 3 | R4 | Gains EXTEND/EVOLVE/CONTRADICT. Fixes st_social duplication gap. | HIGH (multi-step disambiguation) |
| 4 | R5 | Fixes ZERO-reconciliation gap. Prevents duplicate routines and contradictory insights. | MEDIUM (outputs are additive, not destructive) |
| 5 | R6 | Simplification after all phases produce ReconciliationResults. 12+ methods deprecated. | LOW (pure plumbing change) |

### 28.2 Cross-Phase Risk Summary

| Risk | Phases Affected | Severity | Mitigation |
|------|----------------|----------|-----------|
| Column schema mismatch between WriteDecisionRouter and layer writers | R6, R7 | HIGH | Full column contract documentation; cross-validation tests |
| Per-type identity thresholds (entity types have different weights) | R4 | HIGH | IdentityStrategy supports per-type weight configuration |
| Narrative thread short-circuit in clustering distance | R2 | CRITICAL | Stays in R2 clustering (not affected by framework) |
| Dream confidence discount for speculative outputs | R5 | MEDIUM | source_phase confidence modifier in ReconciliationConfig |
| st_social duplication across cycles | R4 | HIGH | SocialIdentity strategy with participant pair matching |
| Dedup/reconciliation metadata separation | R3, R6 | MEDIUM | Maintain separate DedupMetadata and ReconciliationRecord streams |
| FK dependency order in StagedWrites | R6, R7 | HIGH | P03StagedWrites.get_all_writes_ordered() enforced by both old and new paths |
| Override behavior (is_duplicate --> SKIP, tombstone --> PRUNE) | R3 | MEDIUM | Framework checks overrides BEFORE tier 1/tier 2 decisions |
| Intent signal routing (6 types to 3 layers) | R5, R6 | MEDIUM | WriteDecisionRouter must handle IntentSignal routing rules |
| Idempotency key format consistency | R6 | MEDIUM | Same p03:{type}:{cycle_ulid}:{entity} pattern in WriteDecisionRouter |

---

# PART 3: Universal Engine Design and Worked Examples

---

## 29. Universality Principles

### 29.1 The Core Rule

The reconciliation engine is a **standalone, pipeline-agnostic, stateless decision machine**.
It lives outside every pipeline. Any pipeline, any layer, any future truth table plugs in with zero framework changes.

### 29.2 Location Boundary

```
WRONG:  k0/pipelines/p03/reconciliation/       <-- pipeline-coupled
RIGHT:  k0/modules/consolidation/reconciliation/ <-- shared module
```

No pipeline imports flow INTO the engine. Pipelines import FROM the engine.
The engine has zero knowledge of R2, R3, R4, R5, P03EventState, EpisodeCluster, EntityCluster, or any pipeline-specific type.

### 29.3 What the Engine Knows (Exhaustive List)

| Type | Purpose | Pipeline Knowledge |
|------|---------|-------------------|
| ReconciliationCandidate | Universal input envelope | NONE -- caller builds it |
| ReconciliationResult | Universal output envelope | NONE -- caller consumes it |
| TruthLayerSpec | Declarative layer metadata | NONE -- pure data description of a table |
| IdentityStrategy | Plugin protocol for identity scoring | NONE -- pure function (candidate, existing) -> score |
| ReconciliationConfig | Thresholds and feature flags | NONE -- global + per-layer overrides |
| StagedWrite | Output write instruction | NONE -- built from spec merge rules |

### 29.4 The Two-Plugin Contract

Adding a new truth layer (today or 5 years from now) requires EXACTLY two things:

| Step | What You Provide | What The Engine Derives Automatically |
|------|-----------------|--------------------------------------|
| 1 | TruthLayerSpec -- pure data describing the table | SQL query construction, merge rules, threshold cascade, write operations |
| 2 | IdentityStrategy -- pure function `(candidate, existing) -> IdentityResult` | Plugs into reconcile() decision loop. Engine calls it, never modifies it. |

No framework code changes. No new syscalls. No new router code. No new assembler methods.

---

## 30. Boundary Definitions

### 30.1 INSIDE the Engine (Universal, Pipeline-Agnostic)

| Component | Responsibility | What It Never Touches |
|-----------|---------------|----------------------|
| TruthLayerRegistry | Single source of all layer metadata. Returns TruthLayerSpec by layer name. | Pipeline types, domain objects, phase scheduling |
| IdentityStrategy (protocol) | Defines the interface: `compute_identity_score(candidate, existing) -> IdentityResult` | How candidates were built, what phase produced them |
| truth_candidates_query | Builds SQL from TruthLayerSpec (embedding path / key path / hybrid path) | Which caller triggered the query |
| ReconciliationFramework | Core decision machine: override check -> tier 1 (K1 signals) -> tier 2 (K0 similarity) -> action | Domain-specific clustering, enrichment, pre-processing |
| WriteDecisionRouter | Converts (action + TruthLayerSpec + record_data) into StagedWrite using merge rules | Column business meaning, why a column exists |
| ReconciliationConfig | Thresholds, feature flags, per-layer overrides | Pipeline orchestration, batch sizes, scheduling |

### 30.2 OUTSIDE the Engine (Caller's Responsibility)

| Responsibility | Why Outside | Example |
|----------------|------------|---------|
| Domain-specific clustering and refinement | Pre-reconciliation logic, not truth matching | R2 HDBSCAN, R4 alias detection, R2 thread purity |
| Building ReconciliationCandidate | Caller flattens its domain objects | R2 wraps EpisodeCluster -> candidate.record_data, R4 wraps EntityCluster |
| Deciding WHEN to reconcile | Pipeline orchestration concern | R2 reconciles post-clustering, R3 per-event, R5 per-output |
| Setting source_confidence_modifier | Observation-backed vs speculative distinction | R2/R3/R4 set 1.0, R5 sets 0.7 (dream outputs) |
| Override signals | Caller pre-checks domain conditions | R3 sets skip=True for is_duplicate events |
| Consuming ReconciliationResult | What to do with the decision | R6 collects StagedWrites, R3 records reconciliation metadata |

### 30.3 Boundary Diagram

```
+-------------------------------------------------------------------+
|                         CALLER DOMAIN                             |
|   (P03 R2, P03 R3, P03 R4, P03 R5, P06, Bridge, future P07...)  |
|                                                                   |
|   1. Domain processing (clustering, enrichment, scoring)          |
|   2. Build ReconciliationCandidate from domain objects            |
|   3. Set source_confidence_modifier, override flags               |
|                                                                   |
|   candidate = ReconciliationCandidate(                            |
|       target_layer="st_epi",                                      |
|       embedding=centroid_768,                                     |
|       identity_key={"narrative_thread_id": "thread_abc"},         |
|       record_data={...flat column dict...},                       |
|       source_phase="R2",                                          |
|       correction_signal=False,                                    |
|       source_confidence_modifier=1.0                              |
|   )                                                               |
|                                                                   |
+------------------------------|------------------------------------+
                               | ReconciliationCandidate
                               v
+-------------------------------------------------------------------+
|                  RECONCILIATION ENGINE                             |
|            k0/modules/consolidation/reconciliation/               |
|                                                                   |
|   +-- TruthLayerRegistry.get("st_epi") -> TruthLayerSpec         |
|   |                                                               |
|   +-- truth_candidates_query(spec, embedding, identity_key)       |
|   |   |-- embedding path: pgvector <=> on st_vec JOIN st_epi     |
|   |   |-- key path: WHERE identity_columns match                  |
|   |   |-- hybrid: key narrows, embedding scores                   |
|   |   v                                                           |
|   |   List[TruthCandidate] (existing records from DB)             |
|   |                                                               |
|   +-- Override check: skip? tombstone? -> early return            |
|   |                                                               |
|   +-- TIER 1: K1 signals                                         |
|   |   |-- correction_signal -> EVOLVE                             |
|   |   |-- contradiction_signal -> CONTRADICT                      |
|   |                                                               |
|   +-- TIER 2: K0 similarity                                      |
|   |   |-- IdentityStrategy.compute_identity_score()               |
|   |   |-- threshold cascade: >=0.85 REINFORCE, >=0.60 EXTEND     |
|   |   |-- <0.60 CREATE                                            |
|   |                                                               |
|   +-- WriteDecisionRouter.build_staged_write()                    |
|   |   |-- reads TruthLayerSpec.merge_rules                        |
|   |   |-- builds INSERT / UPDATE / ARCHIVE from spec              |
|   |                                                               |
+------------------------------|------------------------------------+
                               | ReconciliationResult
                               v
+-------------------------------------------------------------------+
|                         CALLER DOMAIN                             |
|                                                                   |
|   result.action          = REINFORCE / EXTEND / EVOLVE / CREATE   |
|   result.staged_write    = StagedWrite (ready for R7 or any       |
|                            write executor)                        |
|   result.identity_score  = 0.91                                   |
|   result.confidence      = 0.87                                   |
|   result.reason          = "Matched existing episode ep_abc..."   |
|                                                                   |
|   4. Caller collects StagedWrites, routes to write executor       |
+-------------------------------------------------------------------+
```

---

## 31. Future Callers (Beyond P03)

The engine is NOT a P03 component. Any system that needs to decide "create new, reinforce existing, extend, evolve, or flag contradiction" can call it.

| Future Caller | Scenario | How It Works |
|---------------|----------|-------------|
| P06 Active Learning | Human resolves ambiguous entity from review queue | `framework.reconcile(target_layer="st_kg_dom", candidate=resolved_entity)` -> EVOLVE (supersedes old entity) |
| P07 External Ingestion | Calendar events, location check-ins, imported data | Register new TruthLayerSpec for st_external. `framework.reconcile()` handles merge with zero code changes. |
| K1 Query-Time Correction | User says "Actually Maya's sister is Priya, not Divya" | K1 emits correction_signal via bridge. P03 receives it. `framework.reconcile()` -> EVOLVE with supersedes_id chain. |
| Bridge Cross-Device Sync | Same truth modified on two devices | Bridge resolves CRDT conflict, calls `framework.reconcile()` with resolved candidate. |
| New Truth Layer (st_emotions) | Future memory type not yet designed | Register TruthLayerSpec + EmotionIdentity. Engine works immediately. Zero code changes to framework. |
| New Truth Layer (st_locations) | Place-level truth | Register TruthLayerSpec + LocationIdentity. Engine works immediately. |
| Batch Re-reconciliation | Operator reruns reconciliation on historical data | Load old events, rebuild candidates, call `framework.reconcile_batch()`. Same engine, different trigger. |

---

## 32. Per-Layer Threshold Overrides

### 32.1 Problem

Global thresholds (0.85/0.60) work for embedding-only layers. But R4 entities use per-type weights (PERSON=0.50/0.50, CONCEPT=0.85/0.15) and per-type thresholds. Global thresholds cannot express this.

### 32.2 Solution: Thresholds in TruthLayerSpec

```
TruthLayerSpec:
    # Global defaults used when these are None
    reinforce_threshold: Optional[float] = None   # fallback: config.reinforce_threshold (0.85)
    extend_threshold: Optional[float] = None      # fallback: config.extend_threshold (0.60)

    # Per-subtype overrides (for layers with type-dependent scoring)
    threshold_overrides: Optional[Dict[str, ThresholdOverride]] = None
```

Example for st_kg_dom:

```
TruthLayerSpec(
    layer_name="st_kg_dom",
    reinforce_threshold=0.85,        # default for entities
    threshold_overrides={
        "PERSON":  ThresholdOverride(reinforce=0.80, extend=0.55),
        "CONCEPT": ThresholdOverride(reinforce=0.90, extend=0.70),
        "FAMILY":  ThresholdOverride(reinforce=0.75, extend=0.50),
    }
)
```

The engine reads thresholds from the spec, never from hardcoded per-phase logic.

### 32.3 PRUNE: Separate Sweep, Not Engine Decision

PRUNE is timer-based temporal decay. The engine is a **match decision machine**, not a decay calculator.

- R3 UnifiedDecayEngine computes decay_factor per record
- If decay_factor < 0.01: R3 sets `candidate.override_action = PRUNE`
- Engine sees override -> returns PRUNE immediately, skips similarity
- Engine never calculates time deltas or decay rates

This keeps the engine focused on matching. Decay is a separate temporal concern.

---

## 33. Worked Example: st_epi REINFORCE (Before vs After)

### 33.1 Scenario

Maya has a conversation about her morning coffee routine. An episode about this already exists in st_epi from a previous consolidation cycle. New events arrive in the current batch that describe the same morning routine.

### 33.2 BEFORE (Current R2 Bespoke Code)

```
R2 r2_episodic_integrator.py
  |
  |  Step 1: _query_existing_episodes()
  |    SQL: SELECT episode_id, centroid_embedding, narrative_thread_id, ...
  |          FROM st_epi
  |          WHERE tenant_id = $1 AND space_id = $2
  |            AND status = 'ACTIVE'
  |            AND temporal_end >= (now - 7 days)
  |    Result: existing_episodes = [ep_001 (morning coffee, thread_abc)]
  |
  |  Step 2: _match_events_to_existing_episodes()
  |    FOR each event in batch:
  |      FOR each existing episode:
  |        sim = cosine_similarity(event.embedding, episode.centroid_embedding)
  |        if event.narrative_thread_id == episode.narrative_thread_id:
  |          sim += 0.15   # thread bonus (HARDCODED in R2)
  |        if sim >= 0.85: # threshold (HARDCODED in R2)
  |          event.reconciliation_action = REINFORCE
  |          event.episode_match_id = episode.episode_id
  |          event.episode_match_similarity = sim
  |          event.episode_match_version = episode.version
  |          BREAK
  |
  |  Step 3: Matched events skip HDBSCAN clustering
  |    matched_events -> direct to R6
  |    novel_events -> continue to HDBSCAN
  |
  |  Step 4: R6 TruthWriteAssembler.assemble_epi_writes()
  |    record_data = {
  |        "episode_id": ep_001,
  |        "observation_count": existing.observation_count + 1,  # HARDCODED increment
  |        "last_observed_at": now(),                            # HARDCODED column
  |        "version": existing.version + 1,                     # HARDCODED lock
  |        "confidence": bayesian_update(existing.confidence),   # HARDCODED formula
  |        ... 25+ more HARDCODED columns ...
  |    }
  |    operation = WriteOperation.UPDATE
  |    staged_write = StagedWrite(layer="st_epi", operation=UPDATE, data=record_data)
  |
  |  Step 5: R7 EpisodicLayerWriter executes UPDATE
  |
  |  PROBLEMS:
  |    - Query SQL is in R2 (not reusable by other phases)
  |    - 0.85 threshold is hardcoded in R2
  |    - +0.15 thread bonus is hardcoded in R2
  |    - Column mapping is hardcoded in R6 TruthWriteAssembler
  |    - Adding a new matching signal (e.g., place_id) requires editing R2 code
  |    - No other phase can reuse this matching logic
```

### 33.3 AFTER (Universal Reconciliation Engine)

```
R2 r2_episodic_integrator.py (simplified)
  |
  |  Step 1: R2 still does HDBSCAN clustering, thread purity, same-thread merge
  |           (domain-specific, stays in R2)
  |
  |  Step 2: R2 builds ReconciliationCandidate for each event (pre-clustering)
  |    candidate = ReconciliationCandidate(
  |        target_layer = "st_epi",
  |        embedding = event.embedding_768,
  |        identity_key = {"narrative_thread_id": event.narrative_thread_id},
  |        record_data = {
  |            "tenant_id": event.tenant_id,
  |            "space_id": event.space_id,
  |            "narrative_thread_id": event.narrative_thread_id,
  |            ... event fields flattened by R2 ...
  |        },
  |        source_phase = "R2",
  |        source_event_ids = [event.event_id],
  |        correction_signal = event.correction_signal,    # from P03EventState
  |        contradiction_signal = event.contradiction_signal,
  |        source_confidence_modifier = 1.0                # observation-backed
  |    )
  |
  |  Step 3: Call the engine
  |    result = framework.reconcile(candidate, config)
  |
  |  -- INSIDE THE ENGINE (R2 does not see this) --------------------------
  |  |
  |  |  3a. TruthLayerRegistry.get("st_epi") -> TruthLayerSpec(
  |  |        pk_column="episode_id",
  |  |        embedding_fk="embedding_id",
  |  |        identity_columns=["narrative_thread_id"],
  |  |        supports_embedding_match=True,
  |  |        supports_key_match=False,
  |  |        reinforce_threshold=0.85,   # from spec, not hardcoded in R2
  |  |        merge_rules={
  |  |            "observation_count": COUNTER,       # increment
  |  |            "last_observed_at": REPLACED,       # overwrite with now()
  |  |            "version": COUNTER,                 # increment (optimistic lock)
  |  |            "confidence": REPLACED,             # overwrite with bayesian
  |  |            "narrative_thread_ids_json": APPENDABLE,  # JSON union
  |  |            "temporal_start": TEMPORAL_MIN,     # LEAST
  |  |            "temporal_end": TEMPORAL_MAX,        # GREATEST
  |  |        }
  |  |    )
  |  |
  |  |  3b. truth_candidates_query("st_epi", embedding, identity_key, top_k=10)
  |  |        SQL built FROM SPEC: SELECT ep.*, v.vector
  |  |          FROM st_epi ep JOIN st_vec v ON ep.embedding_id = v.embedding_id
  |  |          WHERE ep.tenant_id = $1 AND ep.space_id = $2
  |  |            AND ep.status = 'ACTIVE'
  |  |          ORDER BY v.vector <=> $3 LIMIT 10
  |  |        Result: [TruthCandidate(ep_001, sim_raw=0.87)]
  |  |
  |  |  3c. Override check: no overrides -> continue
  |  |
  |  |  3d. TIER 1: correction_signal=False, contradiction_signal=False -> skip
  |  |
  |  |  3e. TIER 2: EpisodicIdentity.compute_identity_score(candidate, ep_001)
  |  |        score = cosine_similarity(event.embedding, ep_001.centroid) = 0.87
  |  |        thread match: candidate.thread == ep_001.thread -> bonus +0.15
  |  |        final_score = min(0.87 + 0.15, 1.0) = 1.0
  |  |        -> IdentityResult(score=1.0, match_type=EMBEDDING_MATCH)
  |  |
  |  |  3f. Threshold cascade (from spec): 1.0 >= 0.85 -> REINFORCE
  |  |
  |  |  3g. WriteDecisionRouter.build_staged_write(
  |  |        action=REINFORCE, spec=st_epi_spec, target=ep_001, candidate=candidate)
  |  |        Reads spec.merge_rules:
  |  |          observation_count: COUNTER -> ep_001.observation_count + 1
  |  |          last_observed_at: REPLACED -> now()
  |  |          version: COUNTER -> ep_001.version + 1
  |  |          confidence: REPLACED -> bayesian_update(ep_001.confidence)
  |  |        -> StagedWrite(layer="st_epi", op=UPDATE, data={...})
  |  |
  |  -------------------------------------------------------------------
  |
  |  Step 4: R2 receives ReconciliationResult
  |    result.action = REINFORCE
  |    result.staged_write = StagedWrite (complete, ready for R7)
  |    result.identity_score = 1.0
  |    result.reason = "Matched episode ep_001 (score=1.00, thread bonus)"
  |
  |  Step 5: R6 collects result.staged_write (no assemble_epi_writes needed)
  |  Step 6: R7 executes StagedWrite (unchanged)
  |
  |  ADVANTAGES:
  |    - Query SQL generated from TruthLayerSpec (reusable for any layer)
  |    - 0.85 threshold is in spec (changeable without code edit)
  |    - +0.15 thread bonus is in EpisodicIdentity (isolated, testable)
  |    - Column mapping is in spec.merge_rules (no hardcoded assembler)
  |    - Adding place_id bonus: edit EpisodicIdentity only, nothing else
  |    - R3, R4, R5 reuse the same framework with their own specs + strategies
```

---

## 34. Worked Example: st_epi EXTEND (Before vs After)

### 34.1 Scenario

R2 HDBSCAN produces a new cluster of 5 events about Maya's school morning routine. After clustering + thread purity + same-thread merge, the finalized cluster has centroid_embedding. An existing episode ep_002 (school routine, thread_xyz) has similarity 0.72 to this cluster -- similar topic but broader scope. This should EXTEND ep_002 with new events.

### 34.2 BEFORE (Current R2 CrossBatchExtendMatcher)

```
R2 r2_episodic_integrator.py
  |
  |  After HDBSCAN + purity + merge: cluster_007 (5 events, centroid C7)
  |
  |  CrossBatchExtendMatcher.match()
  |    FOR each cluster:
  |      FOR each existing episode:
  |        sim = cosine_similarity(cluster.centroid, episode.centroid)
  |        if sim >= 0.60:  # HARDCODED threshold
  |          cluster.reconciliation_action = EXTEND
  |          cluster.extend_target_id = episode.episode_id
  |          BREAK
  |    Result: cluster_007.extend_target_id = ep_002 (sim=0.72)
  |
  |  R6 TruthWriteAssembler.assemble_epi_writes()
  |    Manually builds UPDATE with:
  |      - narrative_thread_ids_json: UNION of old + new threads  (HARDCODED JSON merge)
  |      - temporal_start: LEAST(old, new)                        (HARDCODED temporal)
  |      - temporal_end: GREATEST(old, new)                       (HARDCODED temporal)
  |      - observation_count: old + new_event_count               (HARDCODED counter)
  |      - member_event_ids: old + new                            (HARDCODED append)
  |      - summary: regenerated                                   (HARDCODED recompute)
  |      - centroid_embedding: recomputed from all member embeddings (HARDCODED recompute)
  |      ... 20+ more HARDCODED column operations ...
```

### 34.3 AFTER (Universal Engine)

```
R2 r2_episodic_integrator.py
  |
  |  After HDBSCAN + purity + merge: cluster_007 (5 events, centroid C7)
  |
  |  candidate = ReconciliationCandidate(
  |      target_layer = "st_epi",
  |      embedding = cluster_007.centroid_embedding,
  |      identity_key = {"narrative_thread_id": cluster_007.dominant_thread},
  |      record_data = {
  |          "narrative_thread_ids_json": cluster_007.thread_ids,
  |          "temporal_start": cluster_007.temporal_start,
  |          "temporal_end": cluster_007.temporal_end,
  |          "member_event_ids": cluster_007.member_event_ids,
  |          "participants_json": cluster_007.participants,
  |          ...
  |      },
  |      source_phase = "R2",
  |      source_event_ids = cluster_007.member_event_ids,
  |  )
  |
  |  result = framework.reconcile(candidate, config)
  |
  |  -- ENGINE INTERNALLY ------------------------------------------------
  |  |  truth_candidates_query -> finds ep_002 (sim=0.72)
  |  |  EpisodicIdentity -> score=0.72, EMBEDDING_MATCH
  |  |  Threshold: 0.72 >= 0.60, < 0.85 -> EXTEND
  |  |
  |  |  WriteDecisionRouter reads spec.merge_rules:
  |  |    narrative_thread_ids_json: APPENDABLE -> JSON union(ep_002.threads, cluster.threads)
  |  |    temporal_start: TEMPORAL_MIN -> LEAST(ep_002.start, cluster.start)
  |  |    temporal_end: TEMPORAL_MAX -> GREATEST(ep_002.end, cluster.end)
  |  |    observation_count: COUNTER -> ep_002.count + 5
  |  |    member_event_ids: APPENDABLE -> union(ep_002.events, cluster.events)
  |  |    summary: REPLACED -> null (triggers post-write summary recompute hook)
  |  |    embedding_id: RECOMPUTE -> null (triggers post-write centroid recompute hook)
  |  |    version: COUNTER -> ep_002.version + 1
  |  |    confidence: REPLACED -> bayesian_update(ep_002.confidence, new_evidence=5)
  |  |
  |  |  -> StagedWrite(layer="st_epi", op=UPDATE, data={merged columns})
  |  -------------------------------------------------------------------
  |
  |  result.action = EXTEND
  |  result.staged_write = StagedWrite (complete)
  |  -> R6 collects, R7 executes
```

---

## 35. Worked Example: st_epi EVOLVE (K1 Correction Signal)

### 35.1 Scenario

User tells K1: "That episode about Maya being scared of dogs -- that's wrong. She was actually excited to meet the puppy."

K1 LLM detects this is a correction. It sets `correction_signal=true` on the atom. The signal flows: K1 atom -> Bridge envelope -> P02 M13 -> st_hipp_events (migration 0085) -> P03 R0 -> P03EventState.

### 35.2 BEFORE (No Mechanism Exists)

```
NOTHING HAPPENS.
  Current R2 has no EVOLVE code path.
  Current R3 ReconciliationEngine has EVOLVE threshold at 0.40 but it NEVER FIRES
    (research proved: 0 out of 275 reconciliations triggered EVOLVE).
  The correction signal sits in st_hipp_events unused.
  The wrong episode persists indefinitely.
```

### 35.3 AFTER (Universal Engine with K1 Signal)

```
P03 R0 loads event with correction_signal=true from st_hipp_events
R2 builds ReconciliationCandidate:
  |
  |  candidate = ReconciliationCandidate(
  |      target_layer = "st_epi",
  |      embedding = corrected_event.embedding,
  |      record_data = { ...corrected content... },
  |      correction_signal = True,             # <-- K1 signal
  |      supersedes_concept = "scared of dogs",
  |      correction_source = "user_explicit",
  |      session_context_id = "session_xyz"
  |  )
  |
  |  result = framework.reconcile(candidate, config)
  |
  |  -- ENGINE INTERNALLY ------------------------------------------------
  |  |  truth_candidates_query -> finds ep_099 ("Maya scared of dogs", sim=0.78)
  |  |
  |  |  Override check: no overrides
  |  |
  |  |  TIER 1: correction_signal = True --> EVOLVE (immediately)
  |  |    SKIPS tier 2 entirely. Similarity score irrelevant.
  |  |
  |  |  WriteDecisionRouter.build_staged_write(action=EVOLVE):
  |  |    Write 1: UPDATE ep_099 SET status='SUPERSEDED', superseded_at=now()
  |  |    Write 2: INSERT ep_100 (
  |  |      new content: "Maya excited to meet puppy",
  |  |      supersedes_id = ep_099,    # version chain
  |  |      correction_source = "user_explicit",
  |  |      session_context_id = "session_xyz",
  |  |      status = 'ACTIVE',
  |  |      version = 1
  |  |    )
  |  |
  |  |  -> StagedWrite contains TWO operations (UPDATE old + INSERT new)
  |  -------------------------------------------------------------------
  |
  |  result.action = EVOLVE
  |  result.staged_write = StagedWrite (UPDATE + INSERT pair)
  |  result.reason = "K1 correction signal: supersedes ep_099"
  |
  |  Version chain in st_epi:
  |    ep_099: status=SUPERSEDED, superseded_at=2026-03-09T14:30:00Z
  |    ep_100: status=ACTIVE, supersedes_id=ep_099
  |
  |  K1 query for "Maya and dogs" now returns ep_100 (corrected version)
  |  ep_099 is preserved for audit trail but excluded from active queries
```

---

## 36. Worked Example: st_epi CREATE (Novel Episode)

### 36.1 Scenario

R2 HDBSCAN produces a cluster about "family trip to the zoo" -- a topic that has never appeared before. No existing episode matches.

### 36.2 AFTER (Universal Engine)

```
R2 builds candidate from cluster_012 (zoo trip, 8 events)
  |
  |  result = framework.reconcile(candidate, config)
  |
  |  -- ENGINE INTERNALLY ------------------------------------------------
  |  |  truth_candidates_query -> top candidate: ep_055 (sim=0.38, park visit)
  |  |
  |  |  Override check: no overrides
  |  |  TIER 1: no K1 signals
  |  |  TIER 2: EpisodicIdentity -> score=0.38 (no thread match, no bonus)
  |  |  Threshold: 0.38 < 0.60 -> CREATE
  |  |
  |  |  WriteDecisionRouter.build_staged_write(action=CREATE):
  |  |    INSERT ep_new (
  |  |      episode_id = new UUID,
  |  |      all columns from candidate.record_data,
  |  |      observation_count = 1,
  |  |      version = 1,
  |  |      status = 'ACTIVE',
  |  |      confidence = prior (0.5) * likelihood(8 events) = 0.72,
  |  |      created_at = now()
  |  |    )
  |  |    PLUS: INSERT st_vec (embedding_id, vector=centroid_768)
  |  |
  |  |  -> StagedWrite (INSERT episode + INSERT vector)
  |  -------------------------------------------------------------------
  |
  |  result.action = CREATE
  |  result.staged_write = StagedWrite (INSERT pair: st_vec + st_epi)
```

---

## 37. Worked Example: st_epi CONTRADICT (K1 Contradiction Signal)

### 37.1 Scenario

User tells K1: "Maya loves swimming." But st_epi already contains an episode "Maya is afraid of water." K1 detects this as a contradiction (not a correction -- both might be true at different times).

### 37.2 AFTER (Universal Engine)

```
  candidate = ReconciliationCandidate(
      target_layer = "st_epi",
      contradiction_signal = True,    # K1 detected conflict
      ...
  )

  result = framework.reconcile(candidate, config)

  -- ENGINE INTERNALLY ------------------------------------------------
  |  truth_candidates_query -> finds ep_077 ("afraid of water", sim=0.74)
  |
  |  TIER 1: contradiction_signal = True --> CONTRADICT (immediately)
  |
  |  WriteDecisionRouter.build_staged_write(action=CONTRADICT):
  |    INSERT into st_learning_queue (
  |      queue_id = new UUID,
  |      target_layer = "st_epi",
  |      target_record_id = ep_077,
  |      conflicting_candidate = candidate.record_data,
  |      contradiction_type = "semantic_conflict",
  |      confidence = 0.74,
  |      status = "PENDING_REVIEW",
  |      created_at = now()
  |    )
  |    NOTE: ep_077 is NOT modified. Both records preserved until P06 resolves.
  -------------------------------------------------------------------

  result.action = CONTRADICT
  result.staged_write = StagedWrite (INSERT into st_learning_queue only)
  result.contradiction_details = {
      "existing_record": ep_077,
      "conflict_type": "semantic_conflict",
      "resolution_required": True
  }

  P06 Active Learning picks up the queue record, presents to user:
    "Maya loves swimming vs Maya is afraid of water -- which is current?"
  User resolves -> P06 calls framework.reconcile() with correction_signal -> EVOLVE
```

---

## 38. Complete st_epi Lifecycle ASCII Diagram

```
                        EPISODE LIFECYCLE IN st_epi
                    (all actions via Universal Reconciliation Engine)

    New Events Arrive (P03 R0 batch)
           |
           v
    +------------------+
    | R2: HDBSCAN      |     Domain-specific clustering
    | Thread Purity    |     (stays in R2, not engine)
    | Same-Thread Merge|
    +--------|---------+
             |
             v
    R2 builds ReconciliationCandidate per event/cluster
             |
             v
    +========================================+
    |   RECONCILIATION ENGINE                |
    |   framework.reconcile()                |
    +========================================+
             |
     +-------+-------+-------+-------+------+
     |       |       |       |       |      |
     v       v       v       v       v      v
  CREATE  REINFORCE EXTEND  EVOLVE CONTRA- PRUNE
     |       |       |       |    DICT  |      |
     |       |       |       |       |      |
     v       v       v       v       v      v

  +------+ +------+ +------+ +------+ +------+ +------+
  | New  | |Bump  | |Grow  | |Super-| |Queue | |Tomb- |
  |record| |count | |with  | |sede  | |for   | |stone |
  |in    | |+ver  | |new   | |old + | |P06   | |stale |
  |st_epi| |+conf | |data  | |create| |review| |record|
  +------+ +------+ +------+ +------+ +------+ +------+


  CONCRETE st_epi RECORD STATES:

  === CREATE ===
  ep_001: status=ACTIVE, version=1, obs_count=1, confidence=0.72
          narrative_thread_ids=["thread_abc"]
          temporal: 2026-03-01 08:00 -> 2026-03-01 09:30
          member_events: [evt_01, evt_02, evt_03]
          summary: "Maya morning coffee routine at home"

  === REINFORCE (3 cycles later, same topic observed again) ===
  ep_001: status=ACTIVE, version=4, obs_count=4, confidence=0.91
          narrative_thread_ids=["thread_abc"]                    # unchanged
          temporal: 2026-03-01 08:00 -> 2026-03-01 09:30        # unchanged
          member_events: [evt_01, evt_02, evt_03]                # unchanged
          summary: "Maya morning coffee routine at home"         # unchanged
          last_observed_at: 2026-03-09 14:00                     # UPDATED
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
          Only metadata bumped. Content unchanged. Episode is "reconfirmed."

  === EXTEND (new events add to the episode) ===
  ep_001: status=ACTIVE, version=5, obs_count=9, confidence=0.93
          narrative_thread_ids=["thread_abc", "thread_def"]      # APPENDED
          temporal: 2026-03-01 08:00 -> 2026-03-09 09:45         # EXTENDED end
          member_events: [evt_01..03, evt_10..14]                 # APPENDED
          summary: "Maya morning coffee routine, now includes..." # REGENERATED
          centroid_embedding: recomputed from all 9 events        # RECOMPUTED
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
          Content grew. New events absorbed. Summary and embedding refreshed.

  === EVOLVE (K1 correction: "she switched to tea") ===
  ep_001: status=SUPERSEDED, superseded_at=2026-03-09T15:00      # OLD marked dead
  ep_002: status=ACTIVE, version=1, obs_count=1, confidence=0.65
          supersedes_id=ep_001                                    # VERSION CHAIN
          narrative_thread_ids=["thread_abc"]
          summary: "Maya morning TEA routine at home"             # CORRECTED content
          centroid_embedding: fresh from corrected events          # NEW embedding
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
          Old preserved for audit. New version is active.
          K1 query: "Maya morning drink" -> returns ep_002 (tea), not ep_001 (coffee).

  === CONTRADICT (conflicting observation) ===
  ep_001: UNCHANGED (neither modified nor superseded)
  st_learning_queue: new record (
      target_layer="st_epi", target_record_id=ep_001,
      conflict: "Maya hates morning routines" vs existing "Maya loves morning coffee"
      status=PENDING_REVIEW
  )
  P06 presents to user -> user resolves -> triggers EVOLVE or dismisses

  === PRUNE (temporal decay, no observations for 6+ months) ===
  ep_001: status=TOMBSTONED, tombstoned_at=2026-09-15
          All content preserved but excluded from active queries.
          R3 decay sweep: decay_factor=0.008 < 0.01 -> PRUNE override.


  VERSION CHAIN EXAMPLE (EVOLVE x3 over time):

  ep_001 (coffee)
    |  EVOLVE (user: "switched to tea")
    v
  ep_002 (tea), supersedes_id=ep_001
    |  EVOLVE (user: "actually green tea specifically")
    v
  ep_003 (green tea), supersedes_id=ep_002
    |  EVOLVE (user: "back to coffee now")
    v
  ep_004 (coffee again), supersedes_id=ep_003

  Active query returns: ep_004 only
  Audit trail: ep_004 -> ep_003 -> ep_002 -> ep_001 (full history)
  Status chain: ACTIVE -> SUPERSEDED -> SUPERSEDED -> SUPERSEDED


  CROSS-PHASE FLOW (who does what):

  st_hipp_events                 st_epi                    st_learning_queue
  +----------------+             +------------------+       +----------------+
  | raw events     |   R0        | existing episodes|       | contradiction  |
  | (50+ fields)   |---load----->| (ACTIVE ones)    |       | queue records  |
  +-------+--------+             +--------+---------+       +-------+--------+
          |                               |                         ^
          v                               v                         |
  +-------+--------+     +---------------+----------+               |
  | R2: cluster +  |     | ENGINE: reconcile()      |               |
  | purity + merge |---->| -> REINFORCE/EXTEND/     |--CONTRADICT-->|
  | (domain logic) |     |    CREATE/EVOLVE/PRUNE   |               |
  +----------------+     | -> StagedWrite output    |      +--------+-------+
                         +-------------+------------+      | P06: human     |
                                       |                   | resolution     |
                                       v                   | -> EVOLVE call |
                         +-------------+------------+      +----------------+
                         | R6: collect StagedWrites  |
                         | (no assembly, just collect)|
                         +-------------+------------+
                                       |
                                       v
                         +-------------+------------+
                         | R7: execute writes        |
                         | (blind, FK-ordered)       |
                         +--------------------------+
```

---

## 39. Design Decisions Summary

### 39.1 Resolved Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Engine location | `k0/modules/consolidation/reconciliation/` | Pipeline-agnostic. No pipeline imports flow in. |
| Plugin contract | TruthLayerSpec + IdentityStrategy per layer | Minimum viable extension point. Two things to add a layer. |
| Threshold ownership | In TruthLayerSpec with global fallback | Per-layer customization without code changes |
| PRUNE ownership | Outside engine (R3 decay sets override) | Engine is match-decision machine, not decay calculator |
| ReconciliationCandidate.record_data | `Dict[str, Any]` (flat column map) | Engine never understands domain types. Flattening is caller boundary. |
| Engine statefulness | STATELESS -- no instance variables between calls | Enables parallel reconciliation, batch processing, re-reconciliation |
| EVOLVE implementation | UPDATE old (SUPERSEDED) + INSERT new (supersedes_id chain) | Preserves full audit trail. Active query returns latest only. |
| CONTRADICT implementation | INSERT into st_learning_queue (no truth modification) | Truth preserved until human resolution via P06 |

### 39.2 Open Decisions (Require ADR)

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Per-layer threshold subtypes | Global per-layer vs per-entity-type within layer | Per-entity-type via threshold_overrides dict in TruthLayerSpec |
| Post-write hooks (summary regen, centroid recompute) | Engine triggers hook vs caller triggers after result | Engine returns hook_required flags, caller executes hooks (keeps engine stateless) |
| Batch reconciliation parallelism | Sequential per-candidate vs parallel within batch | Sequential first (matches current R3), parallel as optimization later |
| st_learning_queue schema | Minimal (target + conflict) vs rich (resolution hints) | Rich schema -- P06 needs context to present useful review UI |

---

# Part 4: Universal Reconciliation Engine -- Design Blueprint

---

## 40. Complete File Inventory (Existing + Planned)

### 40.1 Existing Files -- What We Have Today

#### Core Engine (2 files, 954 lines)

| File | Lines | Key Types | Purpose |
|------|-------|-----------|---------|
| `k0/modules/consolidation/algorithms/reconciliation_engine.py` | 742 | `ReconciliationConfig`, `ReconciliationDecision`, `ReconciliationEngine` | Per-event decision engine. Queries TruthQueryService, applies threshold logic. Used by R3. |
| `k0/modules/consolidation/algorithms/cross_batch_extend.py` | 212 | `CrossBatchExtendConfig`, `ExtendMatch`, `CrossBatchExtendMatcher` | Episode-level EXTEND. Compares centroids against existing st_epi. Used by R2. |

#### Data Types / Enums (3 files, 1962 lines)

| File | Lines | Key Types | Purpose |
|------|-------|-----------|---------|
| `k0/pipelines/p03/event_state.py` | 572 | `ReconciliationAction` (Enum), `PruneDecision` (Enum), `P03EventState` | Per-event mutable state. Carries reconciliation_action, match_id, similarity, confidence. |
| `k0/pipelines/p03/phase_outputs.py` | 728 | `EpisodeCluster`, `ReconciliationSummary`, `StagedWrite`, `P03PhaseOutputs` | Phase output types. EpisodeCluster has NO reconciliation fields. |
| `k0/modules/consolidation/staging/r6_output.py` | 662 | `StagedEventUpdate`, `ReconciliationSummary`, `R6Output` | Frozen R6 output. Encapsulates all staged writes. |

#### Query Path (1 file, 561 lines)

| File | Lines | Key Types | Purpose |
|------|-------|-----------|---------|
| `k0/modules/consolidation/staging/truth_query_service.py` | 561 | `TruthCandidate`, `DecayCandidate`, `TruthQueryService` | Queries 5 truth layers via embedding cosine similarity. Returns ranked candidates. |

#### Assembly Path (6 key files, ~4500 lines)

| File | Lines | Key Types | Purpose |
|------|-------|-----------|---------|
| `k0/modules/consolidation/staging/truth_write_assembler.py` | 1752 | `TruthWriteAssembler` | Transforms phase outputs into StagedWrites for all truth layers. 12+ assemble methods. |
| `k0/modules/consolidation/staging/r6_coordinator.py` | 515 | `R6Coordinator` | Orchestrates all assembly into R6Output. |
| `k0/modules/consolidation/staging/reconciliation_recorder.py` | 251 | `ReconciliationRecorder` | Audit trail -- records decisions as JSON. |
| `k0/modules/consolidation/staging/status_marker.py` | 333 | `ConsolidationStatusMarker` | Maps ReconciliationAction to consolidation_status on st_hipp_events. |
| `k0/modules/consolidation/staging/idempotency.py` | 281 | Idempotency checking | Dedup keys for write-once safety. |
| `k0/modules/consolidation/staging/dedup_metadata.py` | 333 | Dedup metadata tracking | Near-duplicate metadata for reconciliation. |

#### Truth Writer Module (12 files, ~4900 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/truth_writer/router.py` | 265 | `DecisionRouter` -- dispatches StagedWrites to per-layer writers. |
| `k0/modules/consolidation/truth_writer/transaction.py` | 351 | `TransactionCoordinator` -- UoW wrapper with optimistic locking. |
| `k0/modules/consolidation/truth_writer/result.py` | 219 | `WriteResult`, `LayerWriteResult` -- structured write outcomes. |
| `k0/modules/consolidation/truth_writer/layers/episodic.py` | 532 | st_epi INSERT/UPDATE/REINFORCE/ARCHIVE/TOMBSTONE |
| `k0/modules/consolidation/truth_writer/layers/semantic.py` | 573 | st_sem all operations including EVOLVE |
| `k0/modules/consolidation/truth_writer/layers/social.py` | 671 | st_social writes |
| `k0/modules/consolidation/truth_writer/layers/procedural.py` | 417 | st_procedural writes |
| `k0/modules/consolidation/truth_writer/layers/prospective.py` | 427 | st_prospective writes |
| `k0/modules/consolidation/truth_writer/layers/kg.py` | 1007 | st_kg_dom/st_kg_edges writes |
| `k0/modules/consolidation/truth_writer/layers/vector.py` | 368 | st_vec writes |
| `k0/modules/consolidation/truth_writer/observation_recorder.py` | 256 | ObservationRecorder |
| `k0/modules/consolidation/truth_writer/outbox.py` | 274 | Outbox event writes |

#### Phase Orchestrators (3 key files)

| File | Lines | Purpose |
|------|-------|---------|
| `k0/pipelines/p03/phases/r2_episodic_integrator.py` | 2500 | R2 -- bespoke REINFORCE + CrossBatchExtendMatcher EXTEND |
| `k0/pipelines/p03/phases/r3_dedup_decay.py` | 1320 | R3 -- wires ReconciliationEngine, dedup, decay, prune |
| `k0/pipelines/p03/phases/r6_staging.py` | 505 | R6 -- orchestrates assembly via R6Coordinator |
| `k0/pipelines/p03/phases/r7_truth_writer.py` | 1033 | R7 -- executes writes via TransactionCoordinator |

#### Contracts (6 YAML files)

| File | Purpose |
|------|---------|
| `k0/contracts/pipelines/p03_consolidation.v1.yaml` | Pipeline contract -- all phases, truth layer access |
| `k0/contracts/capabilities/consolidation.v1.yaml` | Syscall capabilities for writes |
| `k0/contracts/modules/consolidation.memory_writer.v1.yaml` | Memory writer module contract |
| `k0/contracts/modules/consolidation.status_updater.v1.yaml` | Status updater module contract |
| `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml` | Episodic clusterer module contract |
| `k0/contracts/schemas/st_hipp_events_v2.columns.yaml` | Schema -- reconciliation columns |

#### Test Files (13+ files, ~3000+ lines)

| File | Focus |
|------|-------|
| `tests/k0/modules/consolidation/staging/test_reconciliation_recorder.py` | ReconciliationRecorder audit trail |
| `tests/k0/pipelines/p03/test_r2_cross_batch_extend.py` | CrossBatchExtendMatcher EXTEND |
| `tests/k0/pipelines/p03/test_r3_two_stage_dedup.py` | R3 dedup (SimHash + embedding) |
| `tests/k0/pipelines/p03/test_p03_r7_truth_writer.py` | R7 INSERT/UPDATE/ARCHIVE SQL |
| `tests/k0/modules/consolidation/staging/test_truth_write_assembler.py` | Write assembly |
| `tests/k0/modules/consolidation/staging/test_r6_coordinator.py` | R6 coordinator |
| `tests/k0/modules/consolidation/staging/test_r6_output.py` | R6Output dataclasses |
| `tests/k0/modules/consolidation/staging/test_r6_integration.py` | R6 integration |
| `tests/k0/pipelines/p03/test_r6_staging.py` | R6 phase |
| `tests/k0/pipelines/p03/test_r7_r6_integration.py` | R7 consuming R6 |

#### POC / Research (1 file)

| File | Lines | Purpose |
|------|-------|---------|
| `poc/r2_phase_research/reconciliation.py` | 641 | Two-tier reconciliation POC. NOT production. |

### 40.2 Planned Files -- What Gets Created (M9)

| New File | Epic | Key Types | Purpose |
|----------|------|-----------|---------|
| `k0/modules/consolidation/reconciliation/registry.py` | 9.1 | `TruthLayerSpec`, `TruthLayerRegistry` | Layer catalog -- thresholds, PK columns, identity strategies per layer |
| `k0/modules/consolidation/reconciliation/identity.py` | 9.2 | `IdentityStrategy` (Protocol), `EpisodicIdentity`, `SemanticIdentity`, `ProceduralIdentity`, `SocialIdentity`, `ProspectiveIdentity`, `KGEntityIdentity`, `KGEdgeIdentity` | Per-layer identity matching. Encapsulates thread/temporal/participant checks. |
| `k0/modules/consolidation/reconciliation/engine.py` | 9.4 | `UniversalReconciliationEngine`, `ReconciliationCandidate`, `ReconciliationResult`, `BatchResult` | STATELESS universal engine. Single decide() function for all layers. |
| `k0/modules/consolidation/reconciliation/candidate.py` | 9.4 | `ReconciliationCandidate` | Universal input type -- layer-agnostic, carries embedding + identity fields |
| `k0/modules/consolidation/reconciliation/syscall.py` | 9.3 | `truth_candidates_query` | Syscall wrapper around TruthQueryService for capability enforcement |
| `k0/modules/consolidation/reconciliation/router.py` | 9.5 | `WriteDecisionRouter` | Maps ReconciliationResult to StagedWrite operations per layer |
| `k0/modules/consolidation/reconciliation/__init__.py` | 9.1 | Public API exports | Package init |
| `k0/contracts/modules/consolidation.reconciliation.v1.yaml` | 9.4 | Module contract | Universal engine module contract |

---

## 41. Current Interface Map -- Existing APIs

### 41.1 ReconciliationEngine (Current -- R3)

```
Location: k0/modules/consolidation/algorithms/reconciliation_engine.py

class ReconciliationEngine:
    __init__(config: ReconciliationConfig, truth_query_service: TruthQueryService)

    async decide(event: P03EventState, space_id: str, tenant_id: str)
        -> ReconciliationDecision

    async decide_batch(events: List[P03EventState], space_id: str, tenant_id: str)
        -> Dict[str, ReconciliationDecision]

    get_metrics() -> Dict
    reset_metrics() -> None

Internal flow:
    _check_overrides(event)       -- SKIP if is_duplicate, PRUNE if tombstone
    _get_event_embedding(event)   -- extract embedding_768
    _find_candidates(emb, ...)    -- TruthQueryService.find_candidates()
    _find_best_match(emb, cands)  -- argmax cosine similarity
    _determine_action(sim, event) -- threshold -> action mapping
    _compute_confidence(sim, n)   -- similarity * log(n+1) heuristic
    _build_reason(...)            -- human-readable string
```

### 41.2 CrossBatchExtendMatcher (Current -- R2)

```
Location: k0/modules/consolidation/algorithms/cross_batch_extend.py

class CrossBatchExtendMatcher:
    __init__(config: CrossBatchExtendConfig)

    match(candidates: List[ExtendableCandidate],
          existing_episodes: List[dict],
          events: Dict[str, ExtendableEvent])
        -> Tuple[List[Optional[ExtendMatch]], CrossBatchExtendStats]

Internal flow:
    for each candidate:
        _dominant_thread_for_candidate(cand, events)
        for each existing episode:
            _cosine_sim_np(cand.centroid, ep.embedding)
            check: same thread? temporal gap <= 7 days? sim >= 0.60?
        pick best match -> ExtendMatch or None
```

### 41.3 TruthQueryService (Current -- Read Path)

```
Location: k0/modules/consolidation/staging/truth_query_service.py

LAYER_PK_COLUMNS = {
    "st_epi":         "episode_id",
    "st_sem":         "semantic_id",
    "st_procedural":  "routine_id",
    "st_social":      "relationship_id",
    "st_prospective": "intention_id",
}

class TruthQueryService:
    __init__(conn_factory=None, pool=None, embedding_dim=768)

    async find_candidates(embedding: ndarray, space_id: str, tenant_id: str,
                          top_k: int=10, min_similarity: float=0.35,
                          layers: Optional[Tuple[str,...]]=None)
        -> List[TruthCandidate]

    async query_entities_for_decay(space_id, tenant_id, layers)
        -> List[DecayCandidate]

    Per layer: SELECT pk, embedding_id FROM layer
               JOIN st_vec v ON t.embedding_id = v.embedding_id
               WHERE tenant_id=? AND space_id=?
               Compute cosine sim in Python, filter, sort, top_k
```

### 41.4 TruthWriteAssembler (Current -- Write Path)

```
Location: k0/modules/consolidation/staging/truth_write_assembler.py

class TruthWriteAssembler:
    assemble_epi_writes(episodes, events, space_id, tenant_id)       -> List[StagedWrite]
    assemble_sem_writes(events, space_id, tenant_id)                 -> List[StagedWrite]
    assemble_procedural_writes(routines, events, space_id, tenant_id)-> List[StagedWrite]
    assemble_social_writes(relationships, events, space_id, tenant_id)-> List[StagedWrite]
    assemble_prospective_writes(intentions, events, space_id, tenant_id)-> List[StagedWrite]
    assemble_insight_writes(...)                                     -> List[StagedWrite]
    assemble_counterfactual_writes(...)                              -> List[StagedWrite]
    assemble_routine_optimization_writes(...)                        -> List[StagedWrite]
    assemble_mcts_writes(...)                                        -> List[StagedWrite]
    assemble_intent_signal_writes(...)                               -> List[StagedWrite]

    12+ methods, each bespoke per layer/type.
    Each method: build record_data dict -> StagedWrite(layer, operation, record_data, ...)
```

### 41.5 DecisionRouter (Current -- Write Dispatch)

```
Location: k0/modules/consolidation/truth_writer/router.py

class DecisionRouter:
    __init__(writers: Dict[str, LayerWriterProtocol])

    async route(writes: List[StagedWrite], uow: UnitOfWork)
        -> WriteResult

    async route_layer(layer: str, writes: List[StagedWrite], uow: UnitOfWork)
        -> LayerWriteResult

    has_writer(layer: str) -> bool
    get_writer(layer: str) -> LayerWriterProtocol
```

### 41.6 R2 Bespoke Episode Matching (Current -- Inline in R2)

```
Location: k0/pipelines/p03/phases/r2_episodic_integrator.py

NOT a separate class. Inline methods on R2EpisodicIntegrator:

    _query_existing_episodes(ctx, space_id, tenant_id, time_window)
        -- Raw SQL: SELECT ... FROM st_epi LEFT JOIN st_vec ...
        -- Returns List[Dict] with episode_id, embedding, version, etc.

    _match_events_to_existing_episodes(events, existing_episodes)
        -- For each event: cosine_sim(event.embedding, ep.embedding)
        -- If sim >= 0.85: event.reconciliation_action = REINFORCE
        -- Sets episode_match_id, episode_match_similarity, episode_match_version

    _decode_vector(data) -- struct.unpack (BYTEA) -- LATENT BUG (pgvector returns string)
    _cosine_similarity(a, b) -- inline cosine sim
```

### 41.7 Key Enums and Types

```
ReconciliationAction (event_state.py):
    PENDING | REINFORCE | EXTEND | CREATE | EVOLVE | CONTRADICT | PRUNE | SKIP

PruneDecision (event_state.py):
    KEEP | ARCHIVE | TOMBSTONE

ReconciliationDecision (reconciliation_engine.py):
    action: ReconciliationAction
    best_match_id: Optional[str]
    best_match_layer: Optional[str]
    similarity_score: float
    confidence: float
    reason: str
    candidates_evaluated: int
    decision_time_ms: float

TruthCandidate (truth_query_service.py):
    record_id: str
    layer: str
    embedding: ndarray
    similarity: float (computed)
    metadata: Dict

StagedWrite (phase_outputs.py):
    write_id: str
    layer: str
    operation: str (INSERT|UPDATE|ARCHIVE|TOMBSTONE)
    record_id: str
    record_data: Dict[str, Any]
    idempotency_key: str
    source_phase: str
    source_event_ids: List[str]
    expected_version: Optional[int]
    observation_context: Optional[ObservationContext]

EpisodeCandidate (centroid_calculator.py):
    cluster_id: str
    centroid_embedding: ndarray
    reconciliation_action: str = "CREATE"     -- NOTE: string not enum!
    extend_target_episode_id: Optional[str]
    extend_similarity: float = 0.0
```

---

## 42. Problems With Current Design

```
PROBLEM 1: Two Parallel Decision Paths (R2 + R3)
+------------------------------------------------------------------+
|                                                                  |
|   R2 (bespoke)                    R3 (ReconciliationEngine)      |
|   +-----------------------+       +-----------------------+      |
|   | _match_events_to_     |       | decide(event, ...)    |      |
|   | existing_episodes()   |       |                       |      |
|   |                       |       | TruthQueryService     |      |
|   | Direct SQL to st_epi  |       | .find_candidates()    |      |
|   | cos_sim >= 0.85       |       | cos_sim thresholds    |      |
|   | -> REINFORCE          |       | -> ALL 6 actions      |      |
|   +-----------+-----------+       +-----------+-----------+      |
|               |                               |                  |
|               v                               v                  |
|   Sets P03EventState.         Sets P03EventState.                |
|   episode_match_id            reconciliation_action              |
|   episode_match_similarity    best_match_id                      |
|   reconciliation_action       best_match_layer                   |
|   = REINFORCE                 similarity_score                   |
|                                                                  |
|   CONFLICT: R2 decides st_epi REINFORCE.                         |
|             R3 independently queries st_epi again.               |
|             R6 sees both. No contract governs priority.          |
+------------------------------------------------------------------+

PROBLEM 2: Type Inconsistency
    R2 sets reconciliation_action = "EXTEND" (string literal)
    R3 sets reconciliation_action = ReconciliationAction.REINFORCE (enum)
    EpisodeCandidate uses str, P03EventState uses enum

PROBLEM 3: Scattered Threshold Ownership
    0.85  -- R2Config.episode_reinforce_threshold (hardcoded)
    0.60  -- R2Config.episode_extend_threshold (declared but UNUSED)
    0.60  -- CrossBatchExtendConfig.centroid_sim_threshold
    0.85  -- ReconciliationConfig.reinforce_threshold
    0.60  -- ReconciliationConfig.extend_threshold
    0.40  -- ReconciliationConfig.evolve_threshold
    Same thresholds defined in 3+ places with no single source of truth.

PROBLEM 4: Bespoke Per-Layer Logic in TruthWriteAssembler
    12+ assemble_*_writes methods, each knows layer-specific column mapping.
    Adding a new layer requires writing a new assemble method.
    No plugin contract. No shared abstraction.

PROBLEM 5: K1 Signals Ignored at R2
    correction_signal and contradiction_signal loaded by R0 (migration 0085)
    but R2 does not check them -- events with K1 corrections still cluster.
    Only R3 routes EVOLVE/CONTRADICT via these signals.

PROBLEM 6: No ReconciliationEngine Tests
    ReconciliationEngine.decide() has ZERO test coverage.
    ReconciliationEngine._determine_action() untested.
    ReconciliationEngine._compute_confidence() untested.
```

---

## 43. Universal Reconciliation Engine -- Target Architecture

### 43.1 ASCII Component Diagram

```
+=========================================================================+
|                   UNIVERSAL RECONCILIATION ENGINE                        |
|                   k0/modules/consolidation/reconciliation/              |
+=========================================================================+
|                                                                         |
|  +------------------+    +---------------------+    +-----------------+ |
|  | TruthLayerSpec   |    | IdentityStrategy    |    | ReconcCandidate | |
|  | (per-layer)      |    | (Protocol)          |    | (universal in)  | |
|  |                  |    |                     |    |                 | |
|  | .layer_name      |    | .compute_identity() |    | .embedding      | |
|  | .pk_column       |    | .match_identity()   |    | .identity_keys  | |
|  | .thresholds      |    | .extract_keys()     |    | .k1_signals     | |
|  | .identity_cls    |    +---------------------+    | .source_phase   | |
|  | .table_name      |        ^                      | .metadata       | |
|  | .archival_col    |        |  implements          +-----------------+ |
|  +--------+---------+        |                                          |
|           |           +------+-------+-------+-------+-------+          |
|           |           |      |       |       |       |       |          |
|           v       Episodic  Sem  Procedural Social Prosp  KGEnt  KGEdge|
|  +------------------+                                                   |
|  | TruthLayerReg    |                                                   |
|  | (singleton)      |                                                   |
|  |                  |                                                   |
|  | .get(layer)      |                                                   |
|  | .all_layers()    |                                                   |
|  | .register(spec)  |                                                   |
|  +--------+---------+                                                   |
|           |                                                             |
|           v                                                             |
|  +======================================+                               |
|  |    UniversalReconciliationEngine     |                               |
|  |    (STATELESS -- no instance vars)   |                               |
|  +======================================+                               |
|  |                                      |                               |
|  |  decide(candidate, layer, registry,  |                               |
|  |         existing_records)            |                               |
|  |      -> ReconciliationResult         |                               |
|  |                                      |                               |
|  |  decide_batch(candidates, layer,     |                               |
|  |              registry, existing)     |                               |
|  |      -> List[ReconciliationResult]   |                               |
|  |                                      |                               |
|  +===========+==========================+                               |
|              |                                                          |
|              | calls                                                    |
|              v                                                          |
|  +-------------------------------------------------------------------+ |
|  |                    DECISION PIPELINE (internal)                    | |
|  |                                                                   | |
|  |  Step 1: K1 Signal Check (Tier 1)                                 | |
|  |    correction_signal=True  -> EVOLVE                              | |
|  |    contradiction_signal=True -> CONTRADICT                        | |
|  |    if Tier 1 fires -> return immediately (no similarity needed)   | |
|  |                                                                   | |
|  |  Step 2: Override Check                                           | |
|  |    is_duplicate=True -> SKIP                                      | |
|  |    prune_decision=TOMBSTONE -> PRUNE                              | |
|  |                                                                   | |
|  |  Step 3: Identity Matching (per-layer strategy)                   | |
|  |    identity_strategy.extract_keys(candidate)                      | |
|  |    identity_strategy.match_identity(candidate, existing_record)   | |
|  |    filters candidates to identity-compatible subset               | |
|  |                                                                   | |
|  |  Step 4: Embedding Similarity (Tier 2)                            | |
|  |    cosine_similarity(candidate.embedding, record.embedding)       | |
|  |    find best match among identity-compatible records              | |
|  |                                                                   | |
|  |  Step 5: Threshold Decision                                       | |
|  |    thresholds = registry.get(layer).thresholds                    | |
|  |    sim >= thresholds.reinforce -> REINFORCE                       | |
|  |    sim >= thresholds.extend    -> EXTEND                          | |
|  |    sim >= thresholds.evolve    -> EVOLVE (no K1 = weak evolve)    | |
|  |    sim < thresholds.evolve + has match -> CONTRADICT              | |
|  |    no match at all -> CREATE                                      | |
|  |                                                                   | |
|  |  Step 6: Build Result                                             | |
|  |    ReconciliationResult(action, match_id, similarity,             | |
|  |                         confidence, reason, hooks_required)       | |
|  +-------------------------------------------------------------------+ |
|                                                                         |
+=========================================================================+
```

### 43.2 ASCII Data Flow -- Engine in Pipeline Context

```
              CALLERS                           ENGINE                          CONSUMERS
  +--------------------------+     +---------------------------+     +-------------------------+
  |                          |     |                           |     |                         |
  |  R2 (episode-level)      |     |  UniversalReconciliation  |     |  R6 (assembly)          |
  |  +---------+             |     |  Engine                   |     |  +-------+              |
  |  | event   +--REINFORCE--+---->|                           |---->|  | Staged|              |
  |  | vs      |             |     |  decide(candidate,        |     |  | Write |              |
  |  | st_epi  |             |     |         layer="st_epi",   |     |  | Router|              |
  |  +---------+             |     |         registry,         |     |  +---+---+              |
  |                          |     |         existing_records)  |     |      |                  |
  |  +---------+             |     |                           |     |      v                  |
  |  | cluster +--EXTEND-----+---->|      -> Result            |     |  +-------+              |
  |  | vs      |             |     |         .action           |     |  | R7    |              |
  |  | st_epi  |             |     |         .match_id         |     |  | Truth |              |
  |  +---------+             |     |         .similarity       |     |  | Write |              |
  |                          |     |         .confidence       |     |  +---+---+              |
  +--------------------------+     |         .reason           |     |      |                  |
                                   |         .hooks_required   |     |      v                  |
  +--------------------------+     |                           |     |  +-------+              |
  |                          |     +---------------------------+     |  |st_epi |              |
  |  R3 (event-level)        |                 ^                     |  |st_sem |              |
  |  +---------+             |                 |                     |  |st_proc|              |
  |  | event   +--per-event--+-----------------+                     |  |st_soc |              |
  |  | vs      |             |     layers: st_sem, st_procedural,    |  |st_pros|              |
  |  | st_sem  |             |     st_social, st_prospective         |  |st_kg  |              |
  |  | st_proc |             |                                       |  +-------+              |
  |  | st_soc  |             |     R3 NO LONGER queries st_epi       |                         |
  |  | st_pros |             |     (R2 owns st_epi decisions)        +-------------------------+
  |  +---------+             |
  |                          |
  +--------------------------+     +---------------------------+
                                   |                           |
  +--------------------------+     |  FUTURE CALLERS           |
  |  P04 (KG reconciliation) +---->|                           |
  |  P10 (cross-space)       +---->|  Same engine, same API,   |
  |  P12 (retention sweep)   +---->|  different layer spec     |
  |  K1 (forced correction)  +---->|                           |
  +--------------------------+     +---------------------------+
```

### 43.3 ASCII Type Hierarchy

```
+----------------------------------------------------------------------+
|                        TYPE HIERARCHY                                 |
+----------------------------------------------------------------------+

ReconciliationCandidate (universal input)
+---------------------------------------+
| embedding: ndarray (768-dim)          |  -- ALWAYS required
| identity_keys: Dict[str, Any]         |  -- layer-specific keys:
|   st_epi: {thread_id, temporal_range} |     filled by IdentityStrategy
|   st_sem: {pattern_type, category}    |     .extract_keys()
|   st_soc: {participant_ids}           |
| k1_signals: K1SignalBundle            |  -- Tier 1 override signals
|   .correction_signal: bool            |
|   .contradiction_signal: bool         |
|   .supersedes_concept: Optional[str]  |
|   .correction_source: Optional[str]   |
| source_phase: str                     |  -- "R2" | "R3" | "R4" | ...
| source_event_ids: List[str]           |  -- provenance
| space_id: str                         |
| tenant_id: str                        |
| metadata: Dict[str, Any]             |  -- caller-specific context
+---------------------------------------+

             |
             | fed into
             v

UniversalReconciliationEngine.decide()
             |
             | produces
             v

ReconciliationResult (universal output)
+---------------------------------------+
| action: ReconciliationAction          |  -- REINFORCE|EXTEND|EVOLVE|
|                                       |     CONTRADICT|CREATE|SKIP|PRUNE
| match_id: Optional[str]              |  -- PK of matched truth record
| match_layer: str                      |  -- "st_epi" | "st_sem" | ...
| similarity: float                     |  -- [0.0, 1.0]
| confidence: float                     |  -- [0.0, 1.0]
| reason: str                           |  -- human-readable decision trace
| identity_match: bool                  |  -- did identity keys match?
| tier: int                             |  -- 1 (K1 signal) or 2 (similarity)
| hooks_required: List[str]             |  -- ["recompute_centroid",
|                                       |      "regenerate_summary", ...]
| decision_time_ms: float              |
+---------------------------------------+

             |
             | consumed by
             v

WriteDecisionRouter.route(result, candidate)
             |
             | produces
             v

StagedWrite (existing type -- no change)
+---------------------------------------+
| write_id: str                         |
| layer: str                            |
| operation: str                        |
| record_id: str                        |
| record_data: Dict[str, Any]          |
| expected_version: Optional[int]       |
| idempotency_key: str                  |
| source_phase: str                     |
| source_event_ids: List[str]           |
| observation_context: ObservationCtx   |
+---------------------------------------+
```

### 43.4 TruthLayerSpec Detail

```
@dataclass(frozen=True)
class ReconciliationThresholds:
    reinforce: float     -- >= this -> REINFORCE (default 0.85)
    extend: float        -- >= this -> EXTEND    (default 0.60)
    evolve: float        -- >= this -> EVOLVE    (default 0.40)
    contradict_floor: float -- below this + match -> CONTRADICT (default 0.20)

@dataclass(frozen=True)
class TruthLayerSpec:
    layer_name: str                    -- "st_epi", "st_sem", ...
    table_name: str                    -- "st_epi", "st_semantic_patterns", ...
    pk_column: str                     -- "episode_id", "semantic_id", ...
    embedding_join: str                -- "embedding_id" (FK to st_vec)
    archival_status_column: str        -- "archival_status" | "status"
    active_value: str                  -- "ACTIVE"
    thresholds: ReconciliationThresholds
    identity_strategy: Type[IdentityStrategy]
    version_column: str                -- "version" (for optimistic locking)
    threshold_overrides: Dict[str, ReconciliationThresholds]  -- per-subtype

Layer Specs (5 truth layers + 2 KG):

  st_epi:         reinforce=0.85, extend=0.60, evolve=0.40
                  identity = EpisodicIdentity (thread + temporal window)

  st_sem:         reinforce=0.90, extend=0.65, evolve=0.45
                  identity = SemanticIdentity (pattern_type + category)

  st_procedural:  reinforce=0.90, extend=0.70, evolve=0.50
                  identity = ProceduralIdentity (routine_name + location)

  st_social:      reinforce=0.85, extend=0.60, evolve=0.40
                  identity = SocialIdentity (participant_ids set overlap)

  st_prospective: reinforce=0.80, extend=0.55, evolve=0.40
                  identity = ProspectiveIdentity (goal_context + deadline)

  st_kg_dom:      reinforce=0.90, extend=0.70, evolve=0.50
                  identity = KGEntityIdentity (entity_name + entity_type)

  st_kg_edges:    reinforce=0.85, extend=0.65, evolve=0.45
                  identity = KGEdgeIdentity (source_id + target_id + rel_type)
```

### 43.5 IdentityStrategy Protocol

```
class IdentityStrategy(Protocol):
    """Per-layer identity matching logic.
    Determines whether two records represent the 'same thing'
    beyond embedding similarity."""

    def extract_keys(self, candidate: ReconciliationCandidate) -> Dict[str, Any]:
        """Extract identity keys from a candidate.
        Returns layer-specific keys used for pre-filtering."""
        ...

    def match_identity(self, candidate_keys: Dict[str, Any],
                       record_keys: Dict[str, Any]) -> bool:
        """Do two records share enough identity to be considered
        the same entity/episode/pattern/relationship?"""
        ...

    def extract_record_keys(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Extract identity keys from an existing truth record."""
        ...


class EpisodicIdentity(IdentityStrategy):
    """Episodes must share thread AND temporal proximity."""

    def extract_keys(self, candidate):
        return {
            "dominant_thread": candidate.metadata.get("dominant_thread"),
            "temporal_start": candidate.metadata.get("temporal_start"),
            "temporal_end": candidate.metadata.get("temporal_end"),
        }

    def match_identity(self, cand_keys, record_keys):
        # Same thread required (mirrors CrossBatchExtendConfig.require_same_thread)
        if cand_keys["dominant_thread"] != record_keys.get("dominant_thread"):
            return False
        # Temporal proximity: gap <= 7 days
        gap = abs(cand_keys["temporal_end"] - record_keys.get("start_time_utc", 0))
        return gap <= 7 * 24 * 3600 * 1000  # 7 days in ms

    def extract_record_keys(self, record):
        return {
            "dominant_thread": record.get("dominant_thread_id"),
            "start_time_utc": record.get("start_time_utc"),
        }


class SemanticIdentity(IdentityStrategy):
    """Semantic patterns must share pattern_type."""

    def extract_keys(self, candidate):
        return {
            "pattern_type": candidate.metadata.get("pattern_type"),
            "category": candidate.metadata.get("category"),
        }

    def match_identity(self, cand_keys, record_keys):
        return cand_keys["pattern_type"] == record_keys.get("pattern_type")

    def extract_record_keys(self, record):
        return {
            "pattern_type": record.get("pattern_type"),
            "category": record.get("category"),
        }


class SocialIdentity(IdentityStrategy):
    """Social relationships must share at least one participant."""

    def extract_keys(self, candidate):
        return {
            "participant_ids": set(candidate.metadata.get("participant_ids", [])),
        }

    def match_identity(self, cand_keys, record_keys):
        cand_parts = cand_keys.get("participant_ids", set())
        rec_parts = set(record_keys.get("participant_ids", []))
        return len(cand_parts & rec_parts) > 0

    def extract_record_keys(self, record):
        return {
            "participant_ids": record.get("participant_ids_json", []),
        }
```

### 43.6 Engine Core -- decide() Pseudocode

```
class UniversalReconciliationEngine:
    """STATELESS. No __init__ instance variables.
    All state passed through function arguments."""

    @staticmethod
    def decide(
        candidate: ReconciliationCandidate,
        layer: str,
        registry: TruthLayerRegistry,
        existing_records: List[Dict[str, Any]],
    ) -> ReconciliationResult:

        spec = registry.get(layer)
        thresholds = spec.thresholds
        identity = spec.identity_strategy()

        # TIER 1: K1 signal override (immediate return)
        if candidate.k1_signals.correction_signal:
            return Result(action=EVOLVE, tier=1,
                          reason="K1 correction signal")
        if candidate.k1_signals.contradiction_signal:
            return Result(action=CONTRADICT, tier=1,
                          reason="K1 contradiction signal")

        # OVERRIDES: dedup / prune
        if candidate.metadata.get("is_duplicate"):
            return Result(action=SKIP, reason="duplicate")
        if candidate.metadata.get("prune_decision") == "TOMBSTONE":
            return Result(action=PRUNE, reason="tombstone")

        # Extract candidate identity keys
        cand_keys = identity.extract_keys(candidate)

        # Filter existing records by identity match
        compatible = []
        for record in existing_records:
            rec_keys = identity.extract_record_keys(record)
            if identity.match_identity(cand_keys, rec_keys):
                compatible.append(record)

        # TIER 2: Embedding similarity against identity-compatible records
        if not compatible:
            return Result(action=CREATE, reason="no identity-compatible records")

        best_match = None
        best_sim = 0.0
        for record in compatible:
            sim = cosine_similarity(candidate.embedding, record["embedding"])
            if sim > best_sim:
                best_sim = sim
                best_match = record

        # Threshold decision
        if best_sim >= thresholds.reinforce:
            action = REINFORCE
        elif best_sim >= thresholds.extend:
            action = EXTEND
        elif best_sim >= thresholds.evolve:
            action = EVOLVE
        elif best_sim >= thresholds.contradict_floor:
            action = CONTRADICT
        else:
            action = CREATE  # below contradict floor = too different

        # Determine post-write hooks
        hooks = []
        if action in (REINFORCE, EXTEND):
            hooks.append("recompute_centroid")
        if action == EXTEND:
            hooks.append("regenerate_summary")
        if action == EVOLVE:
            hooks.append("archive_superseded")

        return ReconciliationResult(
            action=action,
            match_id=best_match[spec.pk_column] if best_match else None,
            match_layer=layer,
            similarity=best_sim,
            confidence=_compute_confidence(best_sim, action, len(compatible)),
            reason=_build_reason(action, best_sim, best_match, layer),
            identity_match=best_match is not None,
            tier=2,
            hooks_required=hooks,
            decision_time_ms=elapsed,
        )
```

---

## 44. Engine Internal Architecture (Detailed ASCII)

### 44.1 Decision Pipeline Stages

```
+============================================================+
|              decide(candidate, layer, registry)             |
+============================================================+
         |
         v
+-------------------+     +-----+
| STAGE 1           |     |     |
| K1 Signal Check   |---->| YES |---> return EVOLVE/CONTRADICT (tier=1)
| correction?       |     |     |     (skip all remaining stages)
| contradiction?    |     +-----+
+--------+----------+
         | NO
         v
+-------------------+     +-----+
| STAGE 2           |     |     |
| Override Check    |---->| YES |---> return SKIP/PRUNE
| is_duplicate?     |     |     |     (skip all remaining stages)
| prune_decision?   |     +-----+
+--------+----------+
         | NO
         v
+-------------------+
| STAGE 3           |
| Identity Filter   |
| extract_keys()    |
| match_identity()  |
| -> compatible[]   |
+--------+----------+
         |
         +----> compatible is empty?
         |          |
         |          YES ---> return CREATE
         |                   (no identity-compatible records)
         | NO (has compatible records)
         v
+-------------------+
| STAGE 4           |
| Similarity Rank   |
| cosine_sim()      |
| find best match   |
| -> best_sim,      |
|    best_match      |
+--------+----------+
         |
         v
+-------------------+
| STAGE 5           |
| Threshold Map     |
|                   |
| sim >= reinforce  |---> REINFORCE
| sim >= extend     |---> EXTEND
| sim >= evolve     |---> EVOLVE
| sim >= contradict |---> CONTRADICT
| else              |---> CREATE
+--------+----------+
         |
         v
+-------------------+
| STAGE 6           |
| Result Assembly   |
| build reason      |
| compute confidence|
| detect hooks      |
| -> Result         |
+-------------------+
```

### 44.2 R2 Integration Detail -- Before vs After

```
BEFORE (current R2 flow):
=========================

run(envelope, ctx)
  |
  +-- _query_existing_episodes(ctx, ...)         <-- raw SQL inline
  +-- _match_events_to_existing_episodes(...)    <-- bespoke cosine sim
  |     for each event:
  |       cos_sim(event, ep) >= 0.85 -> REINFORCE
  |     matched events REMOVED from pipeline
  |
  +-- ... HDBSCAN clustering ...
  |
  +-- CrossBatchExtendMatcher(config).match(...)  <-- separate class
  |     for each candidate:
  |       cos_sim(centroid, ep) >= 0.60 -> "EXTEND" (string!)
  |
  +-- envelope.phases.r2_clusters = [...]


AFTER (universal engine):
=========================

run(envelope, ctx)
  |
  +-- existing = await _query_existing_episodes(ctx, ...)
  |     (same SQL, but decode fix: json.loads not struct.unpack)
  |
  +-- HOOK 1: Pre-clustering event reconciliation
  |     registry = TruthLayerRegistry.default()
  |     for each event with embedding:
  |       candidate = ReconciliationCandidate(
  |           embedding=event.embedding_768,
  |           k1_signals=K1SignalBundle(
  |               correction_signal=event.correction_signal,
  |               contradiction_signal=event.contradiction_signal),
  |           identity_keys={},  # filled by EpisodicIdentity
  |           source_phase="R2",
  |           source_event_ids=[event.event_id],
  |           metadata={"dominant_thread": event.narrative_thread_id,
  |                     "temporal_start": event.timestamp})
  |
  |       result = UniversalReconciliationEngine.decide(
  |           candidate, layer="st_epi", registry=registry,
  |           existing_records=existing)
  |
  |       if result.action == REINFORCE:
  |           event.set_reconciliation(REINFORCE, result.match_id, ...)
  |           -> REMOVE from clustering pipeline
  |       elif result.action in (EVOLVE, CONTRADICT):
  |           event.set_reconciliation(result.action, ...)
  |           -> REMOVE from clustering (K1 directed)
  |       else:
  |           -> KEEP in clustering pipeline (CREATE/EXTEND)
  |
  +-- ... HDBSCAN clustering (unchanged) ...
  +-- ... ThreadPurityCorrector (unchanged) ...
  +-- ... SameThreadMerger (unchanged) ...
  +-- ... CentroidCalculator (unchanged) ...
  |
  +-- HOOK 2: Post-clustering episode reconciliation
  |     for each EpisodeCandidate:
  |       candidate = ReconciliationCandidate(
  |           embedding=ep_candidate.centroid_embedding,
  |           identity_keys={},
  |           source_phase="R2",
  |           source_event_ids=ep_candidate.event_ids,
  |           metadata={"dominant_thread": dominant_thread(ep_candidate),
  |                     "temporal_start": ep_candidate.temporal_start,
  |                     "temporal_end": ep_candidate.temporal_end})
  |
  |       result = UniversalReconciliationEngine.decide(
  |           candidate, layer="st_epi", registry=registry,
  |           existing_records=existing)
  |
  |       ep_candidate.reconciliation_action = result.action  # enum!
  |       if result.action == EXTEND:
  |           ep_candidate.extend_target_episode_id = result.match_id
  |           ep_candidate.extend_similarity = result.similarity
  |       elif result.action == CREATE:
  |           pass  # default, new episode
  |
  +-- envelope.phases.r2_clusters = [...]
```

### 44.3 R3 Integration Detail -- Before vs After

```
BEFORE (current R3 flow):
=========================

reconcile_event(event, space_id, tenant_id):
  engine = ReconciliationEngine(config, truth_query_service)
  decision = await engine.decide(event, space_id, tenant_id)
  |
  +-- Queries ALL 5 truth layers (including st_epi AGAIN)
  +-- Finds best match across all layers
  +-- Applies thresholds -> action
  +-- Sets P03EventState fields

CONFLICT: R3 may override R2's st_epi REINFORCE decision with
          a different layer match.


AFTER (universal engine):
=========================

reconcile_event(event, space_id, tenant_id):
  |
  +-- Skip st_epi layer (R2 already decided)
  |
  +-- remaining_layers = ["st_sem", "st_procedural",
  |                       "st_social", "st_prospective"]
  |
  +-- for layer in remaining_layers:
  |     existing = await truth_query(event.embedding, layer, ...)
  |     candidate = ReconciliationCandidate.from_event(event)
  |     result = UniversalReconciliationEngine.decide(
  |         candidate, layer=layer, registry=registry,
  |         existing_records=existing)
  |
  |     if result.action != CREATE:
  |         event.add_layer_decision(layer, result)
  |
  +-- P03EventState now carries MULTIPLE layer decisions:
      event.layer_decisions = {
          "st_epi": Result(REINFORCE, ...)  # from R2
          "st_sem": Result(EXTEND, ...)     # from R3
          "st_social": Result(CREATE, ...)  # from R3
      }

NO CONFLICT: Each layer decided exactly once by its owning phase.
```

---

## 45. WriteDecisionRouter -- Mapping Results to Writes

```
+------------------------------------------------------------------+
|                      WriteDecisionRouter                          |
|                                                                   |
|  route(result: ReconciliationResult,                              |
|        candidate: ReconciliationCandidate,                        |
|        record_data: Dict[str, Any])                               |
|      -> StagedWrite                                               |
|                                                                   |
|  ACTION -> OPERATION MAPPING:                                     |
|  +-------------------+-------------------------------------------+|
|  | ReconcAction      | StagedWrite.operation                     ||
|  +-------------------+-------------------------------------------+|
|  | CREATE            | INSERT                                    ||
|  |                   | record_id = new ULID                      ||
|  |                   | record_data = caller-provided             ||
|  +-------------------+-------------------------------------------+|
|  | REINFORCE         | UPDATE                                    ||
|  |                   | record_id = result.match_id               ||
|  |                   | record_data = {                           ||
|  |                   |   reinforcement_count += 1,               ||
|  |                   |   last_reinforced_at = now(),             ||
|  |                   |   additional_event_ids = [...],           ||
|  |                   |   version = expected + 1 }               ||
|  +-------------------+-------------------------------------------+|
|  | EXTEND            | UPDATE                                    ||
|  |                   | record_id = result.match_id               ||
|  |                   | record_data = {                           ||
|  |                   |   extended events, new time range,        ||
|  |                   |   updated centroid embedding,             ||
|  |                   |   version = expected + 1 }               ||
|  +-------------------+-------------------------------------------+|
|  | EVOLVE            | UPDATE old (status=SUPERSEDED)            ||
|  |                   | + INSERT new (supersedes_id = old.id)     ||
|  |                   | record_data_old = {status: SUPERSEDED}    ||
|  |                   | record_data_new = full new record         ||
|  +-------------------+-------------------------------------------+|
|  | CONTRADICT        | INSERT into st_learning_queue             ||
|  |                   | record_data = {                           ||
|  |                   |   target_layer, target_id,                ||
|  |                   |   contradicting_event_ids,                ||
|  |                   |   similarity, proposed_resolution }       ||
|  |                   | (truth NOT modified until P06 resolves)   ||
|  +-------------------+-------------------------------------------+|
|  | SKIP              | NO WRITE                                  ||
|  +-------------------+-------------------------------------------+|
|  | PRUNE             | ARCHIVE or TOMBSTONE                      ||
|  |                   | record_id = result.match_id               ||
|  |                   | record_data = {status: ARCHIVED/TOMBSTONE}||
|  +-------------------+-------------------------------------------+|
+------------------------------------------------------------------+
```

---

## 46. Full System ASCII -- End-to-End Pipeline Integration

```
+============================================================================+
|                        P03 CONSOLIDATION PIPELINE                          |
|                     with Universal Reconciliation Engine                    |
+============================================================================+

  st_hipp_events (300 events)
         |
         v
  +------+-------+
  |     R0       |  Batch selector. Loads events, embeddings, K1 signals.
  |              |  Sets: correction_signal, contradiction_signal, place_id,
  |              |  narrative_thread_id, embedding_768
  +------+-------+
         |
         v
  +------+-------+
  |     R1       |  Importance scoring. Sets importance_score, factors.
  +------+-------+
         |
         v
  +------+-------+-----------------------------------------------------+
  |     R2       |  Episodic Integration                                |
  |              |                                                      |
  |  +--------+  |                                                      |
  |  | Query  |  |  SQL: st_epi LEFT JOIN st_vec (50 eps, 7-day window) |
  |  | st_epi |  |                                                      |
  |  +---+----+  |                                                      |
  |      |       |                                                      |
  |      v       |                                                      |
  |  +---+-------------------------------------------+                  |
  |  | HOOK 1: Universal Engine (event vs st_epi)    |                  |
  |  |                                               |                  |
  |  |  for each event:                              |                  |
  |  |    K1 check -> EVOLVE/CONTRADICT (pull out)   |                  |
  |  |    identity + similarity -> REINFORCE (pull)   |                  |
  |  |    else -> novel (keep for clustering)         |                  |
  |  +---+-------------------------------------------+                  |
  |      |                                                              |
  |      | novel events only                                            |
  |      v                                                              |
  |  +---+-------------+                                                |
  |  | EpisodeSplitter |  Pre-clustering boundary detection             |
  |  +---+-------------+                                                |
  |      |                                                              |
  |      v                                                              |
  |  +---+-------------+                                                |
  |  | HDBSCAN         |  3D ensemble distance -> clustering            |
  |  +---+-------------+                                                |
  |      |                                                              |
  |      v                                                              |
  |  +---+-----------------+                                            |
  |  | ThreadPurityCorrect |  Split impure clusters by thread           |
  |  +---+-----------------+                                            |
  |      |                                                              |
  |      v                                                              |
  |  +---+-------------+                                                |
  |  | SameThreadMerge |  Union-find merge same-thread fragments        |
  |  +---+-------------+                                                |
  |      |                                                              |
  |      v                                                              |
  |  +---+-----------------+                                            |
  |  | CentroidCalculator  |  recency_exp centroids -> EpisodeCandidate |
  |  +---+-----------------+                                            |
  |      |                                                              |
  |      v                                                              |
  |  +---+-------------------------------------------+                  |
  |  | HOOK 2: Universal Engine (cluster vs st_epi)  |                  |
  |  |                                               |                  |
  |  |  for each EpisodeCandidate:                   |                  |
  |  |    identity + similarity -> EXTEND/CREATE     |                  |
  |  |    sets reconciliation_action (enum)          |                  |
  |  +---+-------------------------------------------+                  |
  |      |                                                              |
  +------+--------------------------------------------------------------+
         |
         v  R2 output: List[EpisodeCluster] + event states with decisions
  +------+-------+
  |     R3       |  Dedup + Decay + Reconciliation (non-st_epi layers)
  |              |
  |  +--------+  |  SimHash dedup -> is_duplicate flag
  |  | Dedup  |  |
  |  +--------+  |
  |              |
  |  +--------+  |  Decay scoring -> decay_score, prune_decision
  |  | Decay  |  |
  |  +--------+  |
  |              |
  |  +---------------------------------------------+                   |
  |  | HOOK 3: Universal Engine (event vs non-epi)  |                   |
  |  |                                              |                   |
  |  |  layers = [st_sem, st_procedural,            |                   |
  |  |           st_social, st_prospective]         |                   |
  |  |  for each event, for each layer:             |                   |
  |  |    engine.decide(candidate, layer, ...)      |                   |
  |  |  RESPECTS R2's st_epi decision (no override) |                   |
  |  +---------------------------------------------+                   |
  +------+-------+
         |
         v
  +------+-------+
  |  R4 / R5     |  KG extraction / Dream simulation (future hooks)
  +------+-------+
         |
         v
  +------+-------+
  |     R6       |  Write Assembly
  |              |
  |  Reads:      |  - R2 clusters (EpisodeCluster)
  |              |  - R2/R3 reconciliation decisions on P03EventState
  |              |  - R4 KG entities/edges
  |              |  - R5 dream outputs
  |              |
  |  Produces:   |  R6Output (frozen)
  |              |    staged_truth_writes: List[StagedWrite]
  |              |    staged_event_updates: List[StagedEventUpdate]
  |              |    staged_kg_writes: List[StagedWrite]
  |              |    staged_outbox_events: List[StagedOutboxEvent]
  +------+-------+
         |
         v
  +------+-------+
  |     R7       |  Truth Writer (atomic via UoW)
  |              |
  |  Commit order: vec -> kg_dom -> kg_edges -> epi -> sem ->
  |                procedural -> social -> prospective ->
  |                learning_queue -> hipp_events
  +------+-------+
         |
         v
  +------+-------+
  |     R8       |  Feedback / observability
  +--------------+
```

---

## 47. File Structure -- New Package Layout

```
k0/modules/consolidation/reconciliation/
|
+-- __init__.py                 -- public API:
|                                  from .engine import UniversalReconciliationEngine
|                                  from .registry import TruthLayerRegistry, TruthLayerSpec
|                                  from .candidate import ReconciliationCandidate
|                                  from .result import ReconciliationResult
|                                  from .router import WriteDecisionRouter
|
+-- engine.py                   -- UniversalReconciliationEngine (STATELESS)
|                                  decide(candidate, layer, registry, existing_records)
|                                  decide_batch(candidates, layer, registry, existing)
|                                  ~200 lines
|
+-- registry.py                 -- TruthLayerRegistry (singleton catalog)
|                                  TruthLayerSpec (frozen dataclass)
|                                  ReconciliationThresholds (frozen dataclass)
|                                  .get(layer) -> TruthLayerSpec
|                                  .all_layers() -> List[TruthLayerSpec]
|                                  .register(spec) -> None
|                                  .default() -> TruthLayerRegistry (7 layers pre-registered)
|                                  ~250 lines
|
+-- candidate.py                -- ReconciliationCandidate (input)
|                                  K1SignalBundle (frozen)
|                                  .from_event(P03EventState) -> candidate
|                                  .from_episode_candidate(EpisodeCandidate) -> candidate
|                                  ~100 lines
|
+-- result.py                   -- ReconciliationResult (output)
|                                  .is_match -> bool
|                                  .requires_write -> bool
|                                  .requires_archive -> bool
|                                  ~80 lines
|
+-- identity.py                 -- IdentityStrategy (Protocol)
|                                  EpisodicIdentity
|                                  SemanticIdentity
|                                  ProceduralIdentity
|                                  SocialIdentity
|                                  ProspectiveIdentity
|                                  KGEntityIdentity
|                                  KGEdgeIdentity
|                                  ~300 lines
|
+-- router.py                   -- WriteDecisionRouter
|                                  .route(result, candidate, record_data) -> StagedWrite
|                                  ACTION -> OPERATION mapping
|                                  ~200 lines
|
+-- syscall.py                  -- truth_candidates_query syscall wrapper
|                                  wraps TruthQueryService with capability check
|                                  ~80 lines
|
TOTAL: ~1200 lines new code (8 files)


Files MODIFIED (not replaced):
+-- k0/pipelines/p03/phases/r2_episodic_integrator.py
|     DELETE: _match_events_to_existing_episodes() (~90 lines)
|     DELETE: CrossBatchExtendMatcher usage (~25 lines)
|     ADD: 2 engine.decide() call sites (~60 lines)
|     NET: -55 lines
|
+-- k0/pipelines/p03/phases/r3_dedup_decay.py
|     MODIFY: reconcile_event/reconcile_batch to use universal engine
|     MODIFY: skip st_epi layer (R2 owns it)
|     NET: ~0 lines (swap implementation)
|
+-- k0/pipelines/p03/event_state.py
|     ADD: layer_decisions: Dict[str, ReconciliationResult]
|     ADD: add_layer_decision(layer, result) method
|     NET: +20 lines
|
+-- k0/modules/consolidation/algorithms/centroid_calculator.py
|     MODIFY: EpisodeCandidate.reconciliation_action type str -> ReconciliationAction
|     NET: +5 lines


Files DEPRECATED (kept for backward compat, flagged):
+-- k0/modules/consolidation/algorithms/reconciliation_engine.py
|     -> replaced by k0/modules/consolidation/reconciliation/engine.py
|
+-- k0/modules/consolidation/algorithms/cross_batch_extend.py
|     -> absorbed into engine.decide() with EpisodicIdentity
```

---

## 48. API Contract Summary

### 48.1 Public API (what callers import)

```
from k0.modules.consolidation.reconciliation import (
    UniversalReconciliationEngine,   # stateless engine
    TruthLayerRegistry,              # layer catalog
    TruthLayerSpec,                  # per-layer config
    ReconciliationThresholds,        # threshold tuple
    ReconciliationCandidate,         # universal input
    ReconciliationResult,            # universal output
    WriteDecisionRouter,             # result -> StagedWrite
    IdentityStrategy,                # protocol for per-layer identity
)
```

### 48.2 Engine Contract

```
INVARIANTS:
  1. decide() is a PURE FUNCTION (stateless, no side effects)
  2. decide() never reads from database (caller provides existing_records)
  3. decide() never writes to database (caller consumes result)
  4. Tier 1 (K1 signals) always takes priority over Tier 2 (similarity)
  5. Identity filtering happens BEFORE similarity ranking
  6. Each truth layer is decided exactly ONCE by exactly ONE phase
  7. ReconciliationResult.action is always a ReconciliationAction enum value
  8. ReconciliationResult.hooks_required is informational (caller decides execution)

GUARANTEES:
  - If correction_signal=True -> action is EVOLVE (never overridden by similarity)
  - If contradiction_signal=True -> action is CONTRADICT (never overridden)
  - If no existing_records provided -> action is CREATE
  - If no identity-compatible records -> action is CREATE
  - similarity is always in [0.0, 1.0]
  - confidence is always in [0.0, 1.0]
  - match_id is None if and only if action is CREATE or SKIP

LAYER OWNERSHIP (which phase calls engine for which layer):
  +-----+--------------------+-----------------------------------+
  | R2  | st_epi             | event-level + cluster-level       |
  | R3  | st_sem             | event-level                       |
  | R3  | st_procedural      | event-level                       |
  | R3  | st_social          | event-level                       |
  | R3  | st_prospective     | event-level                       |
  | R4  | st_kg_dom          | entity-level (future)             |
  | R4  | st_kg_edges        | edge-level (future)               |
  +-----+--------------------+-----------------------------------+
```

### 48.3 Adding a New Truth Layer (2-Step Plugin Contract)

```
To add a new truth layer (e.g. "st_spatial"):

STEP 1: Implement IdentityStrategy
    class SpatialIdentity(IdentityStrategy):
        def extract_keys(self, candidate): ...
        def match_identity(self, cand_keys, rec_keys): ...
        def extract_record_keys(self, record): ...

STEP 2: Register TruthLayerSpec
    registry.register(TruthLayerSpec(
        layer_name="st_spatial",
        table_name="st_spatial_contexts",
        pk_column="spatial_id",
        embedding_join="embedding_id",
        archival_status_column="status",
        active_value="ACTIVE",
        thresholds=ReconciliationThresholds(
            reinforce=0.85, extend=0.60, evolve=0.40),
        identity_strategy=SpatialIdentity,
        version_column="version",
    ))

DONE. No engine code changes. No new assemble method needed.
The engine, the router, the write path all work automatically.
```

---

# PART 4: M9.1 Pre-Implementation Research (Codebase Audit 2026-03-13)

---

## 49. Scattered Registry Audit (9 Locations Found)

The codebase has **9 independent registries** defining truth layer metadata. None is authoritative. All must be consolidated into TruthLayerRegistry.

| # | Registry | File | Layers Known | What It Tracks |
|---|----------|------|-------------|----------------|
| 1 | LAYER_PK_COLUMNS | k0/modules/consolidation/staging/truth_query_service.py:46 | 5 | PK column per layer |
| 2 | LAYER_CONFIDENCE_COLUMNS | k0/modules/consolidation/staging/truth_query_service.py:55 | 5 | Confidence column (INCONSISTENT: st_epi/st_sem use `confidence_score`, others use `confidence`) |
| 3 | LAYER_EMBEDDING_COLUMNS | k0/modules/consolidation/staging/truth_query_service.py:37 | 5 | Embedding FK column (all `embedding_id`) |
| 4 | DECAY_LAYERS | k0/modules/consolidation/staging/truth_query_service.py:156 | 6 | PK for decay queries (adds st_kg_dom) |
| 5 | LAYER_ENTITY_TYPE_COLUMNS | k0/modules/consolidation/staging/truth_query_service.py:164 | 5 | Entity type column (some None) |
| 6 | LAYER_LAMBDAS | k0/modules/consolidation/algorithms/decay_engine.py:37 | 8 | Decay lambda per layer (most complete) |
| 7 | DEFAULT_TRUTH_LAYERS | k0/modules/consolidation/algorithms/reconciliation_engine.py:70 | 5 | Tuple of layer names for ReconciliationConfig |
| 8 | LAYER_ST_* constants | k0/pipelines/p03/staged_writes.py:58 AND :318 | 11 | String constants (DUPLICATED in same file) |
| 9 | VALID_LAYERS frozenset | k0/pipelines/p03/staged_writes.py:330 | 11 | Validation set (includes non-truth: st_hipp_events, st_mcts) |

### 49.1 Layer Coverage Gap

| Layer | truth_query_service | reconciliation_engine | decay_engine | staged_writes | truth_writers | pipeline YAML |
|-------|--------------------|-----------------------|-------------|---------------|---------------|---------------|
| st_epi | YES | YES | YES | YES | YES | YES |
| st_sem | YES | YES | YES | YES | YES | YES |
| st_procedural | YES | YES | YES | YES | YES | YES |
| st_social | YES | YES | YES | YES | YES | YES |
| st_prospective | YES | YES | YES | YES | YES | YES |
| **st_kg_dom** | **partial (decay only)** | **MISSING** | YES | YES | YES | YES |
| **st_kg_edges** | **MISSING** | **MISSING** | YES | YES | YES | YES |
| st_vec | MISSING | MISSING | MISSING | YES | YES | YES |

**Critical**: st_kg_dom and st_kg_edges are invisible to the current reconciliation engine. Only decay and writers know about them.

### 49.2 Inconsistencies to Resolve

| Inconsistency | Detail | Impact |
|---------------|--------|--------|
| Confidence column naming | st_epi/st_sem: `confidence_score`. st_procedural/st_social: writer references `confidence`. st_prospective: both `confidence_score` AND `inference_confidence`. | TruthLayerSpec must declare the canonical confidence column per layer. |
| Observation count naming | st_social has BOTH `observation_count` AND `interaction_count`. | TruthLayerSpec needs `observation_count_column` (primary) plus optional aliases. |
| Duplicate constants | LAYER_ST_* defined twice in staged_writes.py (L58-64 and L318-327). | Delete duplicates when TruthLayerRegistry replaces them. |
| Stale JSON schemas | k0/contracts/jsonschema/ uses `st_proc` (not `st_procedural`), `st_hipp_store` (not `st_hipp_events`), `st_ws` (undefined). Missing 4 layers. | Update or deprecate JSON schema enums. |
| Status column split | st_prospective has BOTH `status` (ACTIVE/COMPLETED/ABANDONED/DEFERRED) AND `archival_status` (ACTIVE/ARCHIVED/TOMBSTONE). | TruthLayerSpec needs `archival_status_column` and optionally `domain_status_column`. |

---

## 50. Truth Table Column Inventory (From Migrations)

**No YAML schema contracts exist for any of the 7 truth tables.** Only st_vec has a column contract (`k0/contracts/schemas/st_vec_v2.columns.yaml`). All column definitions live exclusively in migration files.

### 50.1 Column Counts

| Table | Total Columns | PK | Embedding FK | Inline Vector | JSON Appendable | Version/Supersedes |
|-------|--------------|-----|-------------|---------------|-----------------|-------------------|
| st_epi | 51 | episode_id | embedding_id (legacy) | YES | 6 fields | YES |
| st_sem | 30 | pattern_id | embedding_id (legacy) | YES | 4 fields | YES |
| st_procedural | 31 | routine_id | -- | YES | 3 fields | YES |
| st_social | 42 | relationship_id | -- | YES | 6 fields | YES |
| st_prospective | 27 | intention_id | -- | YES | 2 fields | YES |
| st_kg_dom | 30 | entity_id | embedding_id (legacy) | YES | 5 fields | YES |
| st_kg_edges | 30 | edge_id | None | **NO** | 4 fields (2 PG arrays) | YES |

### 50.2 Common Columns Across All 7 Truth Tables

Every truth table has these columns (registry can assume their existence):

| Column | Type | Purpose |
|--------|------|---------|
| `{pk}_id` | Text | Primary key (layer-specific name) |
| `tenant_id` | Text | Multi-tenancy scoping |
| `space_id` | Text | Space scoping |
| `version` | Integer (default 1) | Optimistic locking |
| `supersedes_id` | Text | Version chain (EVOLVE) |
| `is_canonical` | Boolean (default TRUE) | Current version flag |
| `observation_count` | Integer (default 1) | REINFORCE counter |
| `confidence_score` | Float (default 0.5) | Truth confidence |
| `decay_factor` | Float (default 1.0) | Temporal decay |
| `archival_status` | Text (default 'ACTIVE') | Lifecycle state (ACTIVE/ARCHIVED/TOMBSTONE) |
| `created_at` | BigInteger | Record creation time |
| `updated_at` | BigInteger | Last modification time |
| `valid_from` | BigInteger | Bitemporal start |
| `valid_to` | BigInteger | Bitemporal end |

### 50.3 Common Inline Embedding Columns (6 of 7 tables)

Added by migrations 0061-0066. **st_kg_edges is the only table WITHOUT inline embeddings.**

| Column | Type | Purpose |
|--------|------|---------|
| `source_texts_json` | Text | JSON array of source texts (EXTEND appendable) |
| `embedding_text` | Text | Concatenated text for embedding generation (REPLACED on EXTEND) |
| `embedding_vector` | LargeBinary (768-dim BYTEA) | Inline embedding vector |
| `embedding_model` | Text (default 'ultrabert-v2.1.0') | Model version |

### 50.4 JSON Appendable Fields Per Layer (Merge Rules)

| Layer | Appendable JSON Fields | Union Strategy |
|-------|----------------------|----------------|
| st_epi | source_events_json, participants_json, source_texts_json, narrative_thread_ids_json, entity_ids_json, centroid_metadata_json | DISTINCT (deduped) |
| st_sem | source_episodes_json, pattern_attributes_json, temporal_pattern_json, source_texts_json | DISTINCT (deduped) |
| st_procedural | source_episodes_json, action_sequence_json, source_texts_json | **UNION ALL (not deduped)** for action_sequence_json |
| st_social | source_episodes_json, interaction_modalities_json, typical_activities_json, sentiment_trajectory_json (capped 20), emotions_json (additive merge), source_texts_json | Mixed: DISTINCT for modalities, CAPPED for trajectory, ADDITIVE for emotions |
| st_prospective | inferred_from_json, source_texts_json | COALESCE (replace if provided) |
| st_kg_dom | aliases_json, attributes_json (shallow merge), source_episodes_json, milestones_json, source_texts_json | DISTINCT for aliases/episodes, SHALLOW MERGE for attributes |
| st_kg_edges | properties_json (shallow merge), source_episodes_json, evidence_event_ids (PG array concat), evidence_episode_ids (PG array concat) | PG array concat (not JSON) for evidence |

### 50.5 Temporal Columns Per Layer

| Layer | Start | End | Last Observed | First Observed | Tracking |
|-------|-------|-----|---------------|----------------|----------|
| st_epi | start_time_utc | end_time_utc | last_observed_at | created_at | duration_minutes (derived) |
| st_sem | -- | -- | last_observed_at | first_observed_at | -- |
| st_procedural | -- | -- | last_observed_at | -- | streak_count, streak_broken_at |
| st_social | first_interaction_at | -- | last_interaction_at | -- | interaction_frequency |
| st_prospective | target_date | -- | -- | -- | -- |
| st_kg_dom | -- | -- | last_observed_at | -- | query_count, last_queried_at |
| st_kg_edges | -- | -- | last_observed_at | -- | query_count, last_queried_at |

---

## 51. Per-Layer Writer Merge Rules (Existing Production Code)

These are the ACTUAL merge rules already implemented in `k0/modules/consolidation/truth_writer/layers/`. TruthLayerSpec must encode these declaratively.

### 51.1 Confidence Boost Strategies (4 Different Approaches)

| Layer | REINFORCE Confidence Rule | Formula |
|-------|--------------------------|---------|
| st_epi | None (no confidence boost on REINFORCE) | -- |
| st_sem | Additive, capped at 1.0 | `LEAST(confidence + 0.05, 1.0)` |
| st_procedural | Multiplicative, capped at 1.0 | `LEAST(confidence * 1.1, 1.0)` |
| st_social | Multiplicative, capped at 1.0 | `LEAST(relationship_strength * 1.1, 1.0)` |
| st_prospective | COALESCE (replace if provided) | `COALESCE(new, existing)` |
| st_kg_dom | Multiplicative, capped at 1.0 | `LEAST(confidence * 1.1, 1.0)` |
| st_kg_edges | COALESCE (replace if provided) | `COALESCE(new, existing)` |

### 51.2 ARCHIVE / TOMBSTONE Behavior

| Layer | ARCHIVE Sets | TOMBSTONE Clears (GDPR) |
|-------|-------------|-------------------------|
| st_epi | archival_status='ARCHIVED', archived_at, archived_reason, valid_to, version++ | archival_status='TOMBSTONE', archived_at, valid_to, version++ |
| st_sem | Same | Same |
| st_procedural | Same (reason='decay') | Same |
| st_social | Same (reason='inactive') | Same |
| st_prospective | archival_status='ARCHIVED', status mapped from reason | Clears: description, trigger_time, trigger_context_json, goal_inference_json, source_episodes_json, counterfactual_json |
| st_kg_dom | archival_status='ARCHIVED', valid_to | Clears: canonical_name, attributes_json, embedding_vector, embedding_text, source_episodes_json |
| st_kg_edges | archival_status='ARCHIVED' | (not documented separately) |

### 51.3 Special Merge Behaviors (Layer-Specific)

| Layer | Special Behavior | Detail |
|-------|-----------------|--------|
| st_epi | duration_minutes recomputed | `(GREATEST(end) - LEAST(start)) / 60000` on EXTEND |
| st_procedural | temporal_regularity moving average | `(existing + new) / 2` on REINFORCE |
| st_social | EMA sentiment tracking | `avg_sentiment = old * 0.9 + new * 0.1` on REINFORCE |
| st_social | Valence trend calculation | `trend = (new - old_avg) * 0.3 + old_trend * 0.7` |
| st_social | Sentiment trajectory cap | `ORDER BY timestamp DESC LIMIT 20` (rolling window) |
| st_social | Decay multiplier | `relationship_strength * 0.95` on DECAY action |
| st_kg_dom | QUERY_BOOST action | `query_count + increment`, no version check |
| st_kg_dom | MILESTONE append | `milestones_json = COALESCE(existing, '[]') || new` |
| st_kg_edges | Weight absolute set | `edge_weight = new_weight` (not increment) |
| st_kg_edges | PG array concat (not JSON) | `evidence_event_ids = existing || new::TEXT[]` |

---

## 52. Syscall Audit: 17 Read Syscalls, 0 Truth-Write Syscalls

### 52.1 The R7 Syscall Bypass Problem

**R7 writes to all 7 truth tables using raw SQL through per-layer writers, completely bypassing the syscall capability-security layer.** This means:

- No capability checks on truth writes (any UoW caller can write to any table)
- No audit trail via syscall logging
- No rate limiting or circuit breaking on write path
- Write SQL is spread across 8 writer classes, not centralized

### 52.2 Existing Truth-Read Syscalls (17 total)

| Syscall | Table | What It Does | Problem |
|---------|-------|-------------|---------|
| `episodes_query` | st_epi | SELECT with JOIN st_observations, ORDER BY start_time_utc DESC | Bespoke for R0/K1 query serving |
| `semantic_schema_query` | st_sem | SELECT with confidence filter, pattern_type IN | Bespoke for K1 query serving |
| `procedural_memory_query` | st_procedural | SELECT ORDER BY regularity_score DESC | Bespoke for K1 query serving |
| `kg_entities_query` | st_kg_dom | SELECT with entity_type filter, ORDER BY observation_count DESC | Bespoke for K1 query serving |
| `kg_entities_lookup` | st_kg_dom | SELECT all active -> build O(1) dict keyed by type:name | Bespoke for R4 entity matching |
| `kg_candidates_fuzzy_query` | st_kg_dom | ILIKE fuzzy match on canonical_name OR aliases_json | Bespoke for R4 disambiguation |
| `kg_edges_query` | st_kg_edges | SELECT with relationship_type filter, ORDER BY edge_weight DESC | Bespoke for K1 query serving |
| `kg_edges_lookup` | st_kg_edges | SELECT all active -> build O(1) dict keyed by sorted_source:sorted_target | Bespoke for R4 edge matching |
| `relationships_query` | st_kg_edges | Match actor canonical_name to source_entity_id | Bespoke for K1 social context |
| `embedding_vectors_batch_query` | st_vec | SELECT by embedding_id IN (...), unpack BYTEA | Bespoke for R0/R2 embedding loading |
| `embeddings_by_event_ids` | st_vec | DISTINCT ON (event_id) | Bespoke for P08 coordination |
| `vec_query` | st_vec | Paginated by status/tenant/space | Bespoke for P08 management |
| `hipp_events_query` | st_hipp_events | Paginated with WHERE filters | Bespoke for K1/admin |
| `query_count` | any | Generic COUNT(*) on allowed tables | Generic utility |
| `learned_weights_query` | st_learned_weights | LIKE prefix search | Bespoke for R1/R2/R3 |
| `learned_weights_get` | st_learned_weights | Exact key fetch | Bespoke for R1/R2/R3 |
| `query_embeddings` | TBD | **NOT IMPLEMENTED** -- placeholder for P01 vector search | Dead code |

### 52.3 What truth_candidates_query Replaces

The new unified syscall does NOT replace all 17 existing syscalls. Those serve K1 query serving, R0 batch loading, and admin needs. The new syscall specifically replaces the RECONCILIATION query pattern:

| Current Code | What It Does | Replaced By |
|-------------|-------------|------------|
| TruthQueryService._query_layer() | JOIN truth table to st_vec, cosine in Python, per-layer SQL | truth_candidates_query embedding path |
| kg_entities_lookup | O(1) dict by type:name for R4 entity matching | truth_candidates_query key path |
| kg_candidates_fuzzy_query | ILIKE fuzzy match for R4 disambiguation | truth_candidates_query hybrid path (key narrows, embedding scores) |
| kg_edges_lookup | O(1) dict by sorted source:target for R4 edge matching | truth_candidates_query key path |

### 52.4 Existing Syscalls That STAY (Unchanged)

All K1 query-serving syscalls, R0 batch loading, admin queries, and st_learned_weights operations remain. They serve different use cases than reconciliation.

---

## 53. Pre-M9.1 Work: YAML Contracts for All 7 Truth Tables

### 53.1 The Contract Gap

Only `st_vec` has a YAML column contract. The other 7 truth tables have their schemas defined **only in migration files**. Before building TruthLayerRegistry, we need authoritative column contracts.

### 53.2 Required Contracts (7 files to create)

```
k0/contracts/schemas/
    st_epi.columns.yaml          # 51 columns, 6 migrations
    st_sem.columns.yaml          # 30 columns, 2 migrations
    st_procedural.columns.yaml   # 31 columns, 2 migrations
    st_social.columns.yaml       # 42 columns, 3 migrations
    st_prospective.columns.yaml  # 27 columns, 3 migrations
    st_kg_dom.columns.yaml       # 30 columns, 3 migrations
    st_kg_edges.columns.yaml     # 30 columns, 4 migrations
    st_vec_v2.columns.yaml       # (already exists, 11 columns)
```

### 53.3 What Each Contract Must Capture (for TruthLayerSpec)

Each YAML contract must tag every column with its merge behavior so TruthLayerRegistry can build TruthLayerSpec declaratively:

```yaml
# Example: st_epi.columns.yaml (structure)
table: st_epi
pk: episode_id
version_column: version
supersedes_column: supersedes_id
canonical_column: is_canonical
observation_count_column: observation_count
confidence_column: confidence_score
confidence_boost_strategy: none           # none | additive_0.05 | multiplicative_1.1 | coalesce
archival_status_column: archival_status
active_status_value: ACTIVE
decay_lambda: 0.005
embedding_fk_column: embedding_id         # nullable, legacy
supports_embedding_match: true
supports_key_match: false
identity_columns: [narrative_thread_id]

# Write dependency order (lower = write first)
write_order: 4                            # after st_vec(1), st_kg_dom(2), st_kg_edges(3)

# Temporal columns
temporal:
  start: start_time_utc                   # LEAST on EXTEND
  end: end_time_utc                       # GREATEST on EXTEND
  last_observed: last_observed_at         # GREATEST on REINFORCE/EXTEND
  first_observed: created_at             # immutable

# Merge rules per column
columns:
  episode_id:
    type: text
    merge: immutable                      # never modified
  tenant_id:
    type: text
    merge: immutable
  version:
    type: integer
    merge: counter                        # increment on any write
  observation_count:
    type: integer
    merge: counter
  episode_summary:
    type: text
    merge: replaced                       # overwrite on EXTEND/EVOLVE
  embedding_text:
    type: text
    merge: replaced
  source_events_json:
    type: text
    merge: appendable_distinct            # JSON array union, deduped
  participants_json:
    type: text
    merge: appendable_distinct
  narrative_thread_ids_json:
    type: text
    merge: appendable_distinct
  action_sequence_json:                   # (st_procedural example)
    type: text
    merge: appendable_all                 # JSON array concat, NOT deduped
  sentiment_trajectory_json:              # (st_social example)
    type: text
    merge: appendable_capped              # JSON array, LIMIT 20
    cap: 20
  emotions_json:                          # (st_social example)
    type: text
    merge: additive_merge                 # jsonb_object_agg, additive per key
  start_time_utc:
    type: biginteger
    merge: temporal_min                   # LEAST(existing, new)
  end_time_utc:
    type: biginteger
    merge: temporal_max                   # GREATEST(existing, new)
  archival_status:
    type: text
    merge: status                         # lifecycle transition rules
  # ... remaining columns
```

### 53.4 Merge Rule Types (Complete Taxonomy)

From the per-layer writer audit, these are ALL the merge behaviors that exist in production:

| Merge Rule | Meaning | Where Used |
|-----------|---------|-----------|
| `immutable` | Never changes after INSERT | All PKs, tenant_id, space_id, created_at |
| `counter` | Increment by 1 (or N) | version, observation_count, interaction_count, co_occurrence_count, source_event_count, query_count |
| `replaced` | Overwrite with new value | episode_summary, embedding_text, last_observed_at, updated_at, consolidation_cycle_id |
| `coalesce` | Use new if provided, else keep existing | confidence (some layers), target_context, various optional fields |
| `appendable_distinct` | JSON array union (deduplicated) | source_events_json, participants_json, aliases_json, source_episodes_json |
| `appendable_all` | JSON array concat (NOT deduplicated) | action_sequence_json (st_procedural) |
| `appendable_capped` | JSON array with rolling window | sentiment_trajectory_json (st_social, cap=20) |
| `additive_merge` | jsonb_object_agg (additive per key) | emotions_json (st_social) |
| `shallow_merge` | `existing::jsonb \|\| new::jsonb` | attributes_json (st_kg_dom), properties_json (st_kg_edges) |
| `temporal_min` | `LEAST(existing, new)` | start_time_utc (st_epi) |
| `temporal_max` | `GREATEST(existing, new)` | end_time_utc (st_epi), last_observed_at |
| `ema` | Exponential moving average | avg_sentiment (st_social): `old * 0.9 + new * 0.1` |
| `trend` | Trend calculation | emotional_valence_trend (st_social): `(new - old_avg) * 0.3 + old_trend * 0.7` |
| `derived` | Recomputed from other columns | duration_minutes (st_epi): `(end - start) / 60000` |
| `pg_array_concat` | PostgreSQL array concatenation (not JSON) | evidence_event_ids, evidence_episode_ids (st_kg_edges) |
| `status` | Lifecycle state machine | archival_status: ACTIVE -> ARCHIVED -> TOMBSTONE |
| `decay_multiply` | Multiplicative decay | relationship_strength (st_social): `* 0.95` on DECAY |

### 53.5 Execution Dependency

**YAML contracts MUST be written BEFORE TruthLayerRegistry.** The registry reads from contracts. Without contracts, the registry has nothing to load.

Order:
1. Write 7 YAML column contracts (from migration audit above)
2. Build TruthLayerSpec dataclass with merge rule taxonomy
3. Build TruthLayerRegistry that loads from YAML
4. Validate: registry.get("st_epi").merge_rules matches what EpisodicLayerWriter does today

---

## 54. Cleanup Targets: Old Reconciliation Code

### 54.1 Code to Deprecate After M9.1-M9.8

| File | What | Lines | When Deprecated |
|------|------|-------|-----------------|
| k0/modules/consolidation/algorithms/reconciliation_engine.py | Old ReconciliationEngine class | ~400 | After M9.4 (framework replaces it) |
| k0/modules/consolidation/staging/truth_query_service.py | Old TruthQueryService + 5 dicts | ~500 | After M9.3 (unified syscall replaces it) |
| k0/modules/consolidation/staging/truth_write_assembler.py | 12+ assemble_*_writes methods | ~2034 | After M9.5+M9.8 (WriteDecisionRouter replaces it) |
| k0/modules/consolidation/algorithms/cross_batch_extend.py | CrossBatchExtendMatcher | ~250 | After M9.2+M9.8 R2 migration (EpisodicIdentity replaces it) |
| k0/pipelines/p03/staged_writes.py (LAYER_ST_* dupes) | Duplicate constants L58-64 vs L318-327 | ~20 | After M9.1 (registry replaces constants) |
| k0/contracts/jsonschema/acl.schema.json (stale enums) | Uses st_proc, st_hipp_store, st_ws | ~5 | After M9.1 (update to current layer names) |
| k0/contracts/jsonschema/archive_manifest.schema.json | Same stale enums | ~5 | After M9.1 |
| k0/contracts/jsonschema/crdt_merge_log.schema.json | Same stale enums | ~5 | After M9.1 |

### 54.2 Code That STAYS (Not Replaced)

| File | What | Why It Stays |
|------|------|-------------|
| k0/modules/consolidation/truth_writer/layers/*.py | Per-layer SQL writers | R7 writers execute StagedWrites. They stay because WriteDecisionRouter produces StagedWrites, writers consume them. The interface is the same. |
| k0/modules/consolidation/truth_writer/router.py | DecisionRouter | Routes StagedWrites to layer writers. Same interface whether writes come from old assembler or new engine. |
| k0/modules/consolidation/algorithms/decay_engine.py | UnifiedDecayEngine | Decay calculation is separate from reconciliation. PRUNE action is passed to engine as override, not computed by engine. |
| k0/modules/consolidation/algorithms/same_thread_merge.py | SameThreadMerger | Intra-batch clustering refinement (pre-reconciliation). Stays in R2. |
| k0/modules/consolidation/algorithms/thread_purity.py | ThreadPurityCorrector | Intra-batch clustering refinement (pre-reconciliation). Stays in R2. |
| All 17 existing read syscalls | K1 query serving, R0 loading | Different use case. truth_candidates_query is additive, not replacement. |

### 54.3 The R6/R7 Syscall Problem (Separate Concern)

R7 bypasses the syscall layer for ALL truth writes. This is a **separate architectural concern** from the reconciliation engine:

- **Reconciliation engine scope**: Produce correct StagedWrites from candidates + existing records
- **Syscall scope**: Whether R7 writers go through syscalls or raw SQL

The reconciliation engine does NOT fix the R7 syscall bypass. That requires:
1. Adding truth-write syscalls to k0/kernel/syscalls.py (one per action: insert, update, archive, tombstone)
2. Wiring R7 layer writers to call syscalls instead of raw SQL
3. Adding capability checks (truth.{layer}.write)

This is DEFERRED to a separate milestone (post-M9) because:
- R7 already works correctly with raw SQL
- Changing R7's write path during reconciliation engine migration adds compounding risk
- The syscall enforcement is orthogonal to reconciliation correctness

---

## 55. M9.1 Execution Prerequisites

### 55.1 What Must Happen BEFORE M9.1 Implementation

| # | Prerequisite | Status | Detail |
|---|-------------|--------|--------|
| 1 | YAML column contracts for 7 truth tables | NOT STARTED | Must be created from migration audit (Section 50) |
| 2 | Merge rule taxonomy finalized | THIS DOCUMENT | Section 53.4 defines 16 merge rule types |
| 3 | Identity column decisions finalized | THIS DOCUMENT | Section 50.2 + per-layer analysis in Sections 21-24 |
| 4 | Confidence boost strategy per layer decided | THIS DOCUMENT | Section 51.1 documents current production behavior |
| 5 | Write dependency order confirmed | CONFIRMED | vec -> kg_dom -> kg_edges -> epi -> sem -> procedural -> social -> prospective |
| 6 | Stale JSON schema enums acknowledged | ACKNOWLEDGED | Will update in M9.1 as cleanup |

### 55.2 M9.1 Deliverables (From This Research)

| Deliverable | Description |
|-------------|-------------|
| 7 YAML column contracts | `k0/contracts/schemas/st_{layer}.columns.yaml` with merge rules per column |
| TruthLayerSpec dataclass | 20+ fields covering PK, embedding FK, identity, version, confidence, status, temporal, merge rules, thresholds, decay |
| TruthLayerRegistry class | Loads from YAML contracts, returns TruthLayerSpec by layer name, validates completeness |
| Merge rule type enum | 16 merge behaviors (immutable, counter, replaced, coalesce, appendable_distinct, appendable_all, appendable_capped, additive_merge, shallow_merge, temporal_min, temporal_max, ema, trend, derived, pg_array_concat, status, decay_multiply) |
| Validation tests | Registry lookup per layer, merge rule coverage vs existing writer SQL, roundtrip YAML -> TruthLayerSpec -> validate |
| Cleanup: deduplicate LAYER_ST_* constants | Remove staged_writes.py L58-64 duplicates |
| Cleanup: update stale JSON schema enums | Fix st_proc -> st_procedural, st_hipp_store -> st_hipp_events, remove st_ws |
