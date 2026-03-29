# R3 Dedup/Decay Phase -- Whiteboard

**Purpose**: Gap analysis, enhancement plan, and implementation roadmap for R3 Dedup/Decay
**Status**: RESEARCH PHASE (revised)
**Date**: 2026-03-19 (revised 2026-03-19 v2)
**Source**: P03_R3_DEDUP_DECAY_DISCOVERY.md, MASTER_IMPLEMENTATION_SKELETON.md, live DB audit, 6-agent full pipeline audit
**Scope**: P03 Consolidation Phase R3 (sub-phases R3.1-R3.8)
**Tests**: 409 passing across 12 test files (baseline 2026-03-19)

---

## 1. Current State Summary

R3 is **92% implemented** with 13 algorithm files, a 1,309-line orchestrator, and 409 passing tests. All sub-phases execute end-to-end with no stubs. The phase has **never run on live data** -- all 135 episodes have `decay_factor=1.0` and all R3 output tables (`st_consolidation_audit`, `st_pruned_entities`, `st_learned_weights`, `st_feedback_signals`) are empty.

### 1.1 Live DB State (2026-03-19)

| Table | Rows | R3 Role | Notes |
|-------|------|---------|-------|
| st_hipp_events | 1,410 | Input events | All CONSOLIDATED, all have simhash_hex |
| st_epi | 135 | Truth layer (episodic) | All have embedding_id, decay_factor=1.0 |
| st_sem | 2,367 | Truth layer (semantic) | 1,410 have embedding_id |
| st_procedural | 23 | Truth layer (procedural) | |
| st_social | 5 | Truth layer (social) | |
| st_prospective | 48 | Truth layer (prospective) | |
| st_vec | 1,410 | Embedding store | All events have vectors |
| st_consolidation_audit | 0 | R3 output (GDPR audit) | Never written |
| st_learned_weights | 0 | R3 output (adaptive lambdas) | Never written |
| st_pruned_entities | 0 | R3 output (regret tracking) | Never written |
| st_feedback_signals | 0 | R3 output (regret signals) | Never written |

### 1.2 Sub-Phase Inventory

| Sub-Phase | Component | File | Lines | Status |
|-----------|-----------|------|-------|--------|
| R3.1 | SimHasher | `k0/modules/consolidation/algorithms/simhasher.py` | 158 | Stable |
| R3.1 | TwoStageDeduplicator | `k0/modules/consolidation/algorithms/two_stage_dedup.py` | 303 | Stable |
| R3.1 | DuplicateDetector | `k0/modules/consolidation/algorithms/duplicate_detector.py` | 416 | Stable |
| R3.2 | AdaptiveNoveltyBonusLearner | `k0/modules/consolidation/algorithms/novelty_bonus_learner.py` | 347 | Stable |
| R3.3 | UnifiedDecayEngine | `k0/modules/consolidation/algorithms/decay_engine.py` | 365 | Gap: no learned lambda |
| R3.4 | RetentionEnforcer | `k0/modules/consolidation/algorithms/retention_enforcer.py` | 438 | Stable |
| R3.4 | ImmunityChecker | `k0/modules/consolidation/algorithms/immunity_checker.py` | 369 | Stable |
| R3.5 | PruneAuditLogger | `k0/modules/consolidation/algorithms/prune_audit_logger.py` | 498 | Stable |
| R3.6 | AccessTracker + BayesianLambdaEstimator | `k0/modules/consolidation/algorithms/access_tracker.py` | 470 | Stable (output unused) |
| R3.7 | PruneRegretDetector | `k0/modules/consolidation/algorithms/prune_regret_detector.py` | 510 | Stable (not wired to P21) |
| R3.8 | MinHashLSH + AdaptiveStrategy | `k0/modules/consolidation/algorithms/minhash_lsh.py` | 625 | Disabled by default |
| R3 | R3DedupDecay Orchestrator | `k0/pipelines/p03/phases/r3_dedup_decay.py` | 1,309 | See gaps below |

### 1.3 Test Inventory

| Test File | Tests | Covers |
|-----------|-------|--------|
| test_r3_simhasher.py | ~30 | SimHash computation, hamming distance, content-type thresholds |
| test_r3_two_stage_dedup.py | ~35 | Stage1 SimHash filter, Stage2 embedding verification, fallback |
| test_r3_duplicate_detector.py | ~40 | Combined dedup + novelty scoring |
| test_r3_decay_engine.py | ~35 | Exponential decay, per-layer lambdas, effective lambda |
| test_r3_retention_enforcer.py | ~35 | KEEP/ARCHIVE/TOMBSTONE decisions, resurrection |
| test_r3_immunity_checker.py | ~30 | Entity-level, attribute-level immunity |
| test_r3_prune_audit.py | ~34 | GDPR sampling, audit record structure |
| test_r3_prune_regret.py | ~35 | Regret detection, retention windows |
| test_r3_novelty_learner.py | ~25 | Adaptive bonus learning, feedback signals |
| test_r3_access_tracker.py | ~30 | Access tracking, Bayesian lambda estimation |
| test_r3_minhash_lsh.py | ~45 | MinHash, LSH, adaptive strategy switching |
| test_r3_integration.py | ~35 | End-to-end orchestrator, phase result |
| **Total** | **409** | |

---

## 2. R3 Role in P03 Pipeline (Corrected)

### 2.0 Event Origin: K1 Memory Writer

Events do NOT come from a chat interface. The K1 Memory Writer observes each conversation turn, extracts 0-6 short factual MemoryAtoms via LLM (2000-token budget), builds K0 command envelopes, and submits them through the Bridge to K0 P02. P02 enriches them (UltraBERT validation, embeddings) and stores them in `st_hipp_events`. Events accumulate one by one. P03 triggers periodically and grabs a batch of up to **300 pending events** per consolidation cycle.

### 2.1 Pipeline Execution Order

```
R0 (Batch Select) -> R1 (Importance Score) -> R2 (Episode Cluster) -> R3 (Dedup + Decay)
    -> R4 (Knowledge Graph) -> R5 (Dream Explorer) -> R6 (Staging) -> R7 (Atomic Write) -> R8 (Emit)
```

Single `P03BatchEnvelope` flows through all 9 phases. **R0-R6 are read-compute-stage. R7 is the ONLY database commit (atomic, all-or-nothing).**

### 2.2 R3 Has Exactly 2 Responsibilities

No other phase performs these functions. Reconciliation does NOT belong in R3.

**JOB 1: Batch-Internal Deduplication**

- 300 events arrive per cycle from Memory Writer
- MW has a 5-minute dedup window per session, but events from different sessions, or mentions >5 minutes apart within the same session, pass through as separate events
- R2 catches cross-batch overlap (new events vs existing episodes in st_epi, cosine sim >= 0.85)
- R2 does NOT catch within-batch text-level near-duplicates (R2 clusters events, it does not detect textual duplication)
- R3 SimHash + MinHash catches "these 2 events in this batch have near-identical text content"
- Output: `is_duplicate`, `duplicate_of_id`, `novelty_score` per event, `r3_dedup_results` dict

**JOB 2: Decay + Retention (Memory Lifecycle Management)**

- No other phase manages memory aging
- Compute exponential decay for entities across ALL truth layers
- Decide KEEP / ARCHIVE / TOMBSTONE based on decay_factor + importance + access patterns
- Immunity gate protects important/pinned/recently-accessed memories
- Audit log for GDPR compliance
- Output: retention decisions (DecayUpdate, DedupMerge) staged for R6 -> R7

### 2.3 R3 Output Consumption by Downstream Phases

R3 enriches each `P03EventState` in the envelope and produces batch-level outputs. These flow downstream:

| R3 Output | Set On | Consumed By | How It Is Used |
|-----------|--------|-------------|----------------|
| `event.is_duplicate` | P03EventState | R6 (staging) | Duplicate events get `consolidation_status=DUPLICATE`, skipped from truth writes |
| `event.duplicate_of_id` | P03EventState | R6 (staging) | Links duplicate to its original for traceability |
| `event.novelty_score` | P03EventState | R5 (dream) | `min_novelty_score` filter: only high-novelty events feed dream algorithms (CPN, BGT-SM) |
| `event.novelty_score` | P03EventState | R4 (KG) | Does NOT currently filter by novelty -- R4 processes ALL events. FUTURE: could skip low-novelty for entity extraction |
| `r3_dedup_results` | envelope.phases | R6 (staging) | DedupMetadataPopulator uses results to set merge/skip operations |
| `r3_dedup_merges` | envelope.phases | R6 (staging) | Dedup merge operations staged as StagedWrites for R7 |
| `r3_decay_updates` | envelope.phases | R6 (staging) | Decay factor updates + ARCHIVE/TOMBSTONE operations staged for R7 |
| Retention decisions | Internal stats | R6 -> R7 | ARCHIVE operations = soft-delete; TOMBSTONE operations = permanent marker |
| Audit records | audit_store | R6 -> R7 (if DB-backed) | GDPR audit trail written to st_consolidation_audit |

**Key insight**: R3 does not write to the database itself. All its decisions flow through R6 (staging) and are committed atomically by R7.

### 2.4 Reconciliation -- REMOVED from R3 Scope

Reconciliation is already distributed per-layer where each phase has domain-specific identity strategies:

| Phase | Layer | What it reconciles | Mechanism |
|-------|-------|--------------------|-----------|
| R2 | st_epi (episodes) | New events vs existing episodes | Cosine sim: >=0.85 REINFORCE, >=0.60 EXTEND |
| R4 | st_kg_dom + st_kg_edges | New entities vs existing KG | Entity resolution: name+type matching, confidence bands |
| R4 | st_social | New relationships vs existing | Social relationship extraction + merge |
| R5 | st_sem + st_procedural | Schemas + routines | SPC-UQ reconstruction + TDL-HCO optimization |

R3's legacy `ReconciliationEngine` (in `reconciliation_engine.py`) does embedding-only similarity matching across 5 truth tables. It duplicates R2's episode matching, does worse than R4's entity resolution (no name/type awareness), and doesn't know about R5's semantic/procedural identity strategies. It has 5 root-cause limitations (RC-0 through RC-4, see `whiteboard_reconciliation_engine.md`).

**Decision**: Set `enable_reconciliation = False` as default. Remove reconciliation code from R3 orchestrator. M9 Universal Reconciliation Engine replaces it entirely as a cross-cutting service.

### 2.5 What R3 Does NOT Own

| Responsibility | Owned By | NOT R3 |
|---------------|----------|--------|
| Cross-batch episode matching | R2 (cosine sim vs st_epi) | R3 only does within-batch text dedup |
| Entity resolution | R4 (name+type vs st_kg_dom) | R3 has no entity awareness |
| Semantic pattern reconciliation | R5 (SPC-UQ vs st_sem) | R3 has no schema awareness |
| Truth layer writes | R7 (atomic UoW) | R3 only produces decisions |
| Event bus emission | R8 (outbox drain) | R3 produces no events |

---

## 3. Identified Gaps

### 3.1 P1 -- CRITICAL (Must Fix Before Live R3 Run)

#### GAP-R3-01: In-Memory Stores Lose Data Between Cycles

**Problem**: `R3Stores.create_production()` uses `InMemoryAccessStore`, `InMemoryPrunedEntityStore`, and `InMemoryAuditStore`. Only `learned_weights_store` uses the DB-backed `SyscallLearnedWeightsStore`. Every P03 cycle discards:

- Access patterns (kills Bayesian lambda estimation across cycles)
- Pruned entity tracking (kills regret detection across cycles)
- Audit records (kills GDPR compliance trail)

**Current code** (`r3_dedup_decay.py` lines 342-351):

```python
@classmethod
def create_production(cls, syscalls: Any) -> "R3Stores":
    return cls(
        access_store=InMemoryAccessStore(),           # LOST every cycle
        pruned_entity_store=InMemoryPrunedEntityStore(),  # LOST every cycle
        learned_weights_store=SyscallLearnedWeightsStore(syscalls=syscalls),  # OK
        audit_store=InMemoryAuditStore(),              # LOST every cycle
    )
```

**Required**: Implement `SyscallAccessStore`, `SyscallPrunedEntityStore`, `SyscallAuditStore` backed by existing DB tables (st_learned_weights, st_pruned_entities, st_consolidation_audit).

**Tables already exist** -- schemas verified:

| Store | Target Table | Schema Columns |
|-------|-------------|----------------|
| SyscallAccessStore | st_learned_weights | param_id, param_key, param_scope, scope_id, space_id, current_value, prior_value, confidence, sample_count, last_updated_at, version |
| SyscallPrunedEntityStore | st_pruned_entities | (needs schema audit) |
| SyscallAuditStore | st_consolidation_audit | audit_id, memory_id, source_table, action, formula_used, formula_version, inputs_json, outputs_json, explanation, decision_id, space_id, tenant_id, cycle_id, confidence, created_at, threshold_used, threshold_name, outcome_evaluated, outcome_success, evaluated_at |

**Protocols to implement** (all defined in algorithm files):

| Protocol | Defined In | Methods |
|----------|-----------|---------|
| AccessStoreProtocol | access_tracker.py | `record_access()`, `get_access_history()`, `get_access_count()` |
| PrunedEntityStoreProtocol | prune_regret_detector.py | `insert_pruned_entity()`, `get_unmatched_entities()`, `update_matched()`, `delete_old()` |
| AuditStoreProtocol | prune_audit_logger.py | `log_record()`, `get_records()` |

**Impact**: Without this, R3 is stateless across cycles. Regret detection, adaptive lambda, and GDPR audit all require cross-cycle persistence.

---

#### GAP-R3-02: Per-Entity Learned Lambda Not Wired into Decay Engine

**Problem**: `BayesianLambdaEstimator` (in access_tracker.py) computes per-entity decay rates from access patterns and persists them to `st_learned_weights`. But `UnifiedDecayEngine.compute_effective_lambda()` only reads from `LAYER_LAMBDAS` (per-table static values). The learned lambda is **never consumed**.

**Consequence**: All entities in the same truth table decay at identical rates regardless of how often they're accessed. A birthday memory and a coffee-run memory in st_epi both decay at lambda=0.005 (139-day half-life).

**Current decay formula** (`decay_engine.py` line 218):

```python
def compute_effective_lambda(
    self,
    table_name: str,
    importance_score: float = 0.0,
    confidence_score: float = 0.0,
    observation_count: int = 1,
    space_modifier: float = 1.0,
    entity_type_modifier: float = 1.0,
) -> float:
    base = self.get_base_lambda(table_name)  # Always LAYER_LAMBDAS[table_name]
    ...
```

**Missing**: A `learned_lambda_override: Optional[float] = None` parameter that, when set and confidence > threshold, replaces `base` with the learned value.

**Decision needed**: Override vs blend?

- Option A: Override when confidence > 0.5 (`base = learned_lambda if confidence > 0.5 else base`)
- Option B: Weighted blend (`base = learned * 0.7 + layer_default * 0.3`)

**Depends on**: GAP-R3-01 (access store must persist across cycles for BayesianLambdaEstimator to accumulate enough observations -- min 5 accesses, 7-day spread)

---

### 3.2 P2 -- HIGH (Fix Before Milestone Release)

#### GAP-R3-03: No OpenTelemetry Spans or Prometheus Metrics

**Problem**: R3 has no observability integration. Cannot:

- Trace sub-phase execution timeline (which sub-phase is slow?)
- Export metrics to Prometheus (dedup rate, decay distribution, prune count)
- Alert on regret spikes (are we over-pruning?)
- Track per-entity decay factor histogram (systemic drift detection)

**R3PhaseStats** exists as an internal dataclass with all the right counters (events_processed, duplicates_found, active_count, archive_candidate_count, prune_candidate_count, immune_count, etc.) but these are never exported.

**Required**:

- OTel trace span per sub-phase (R3.1 dedup, R3.3 decay, R3.4 retention, R3.5 audit, R3.7 regret)
- Prometheus counters/histograms exported from R3PhaseStats
- Per-cycle structured log with action distribution

---

#### GAP-R3-04: SimHash Base Threshold Too Strict

**Problem**: Default SimHash hamming threshold is 3 bits (out of 64). While content-type-specific thresholds exist (TRANSACTION=1, CHAT_MESSAGE=3, VOICE_MEMO=5), the base threshold misses paraphrased content where word order differs but semantics are identical.

**Example**: "We went to the park and had ice cream" vs "Had ice cream after going to the park" -- different SimHash (hamming > 3) but cosine_sim=0.92.

**Mitigating factor**: Two-stage dedup has an embedding fallback path -- if cosine_sim >= 0.90 it catches the duplicate even when SimHash misses. But the gap between SimHash threshold 3 and embedding fallback 0.90 means some near-duplicates in the 0.85-0.90 range slip through.

**Options**:

- Increase base threshold to 5 (matches VOICE_MEMO already)
- Add content types for NARRATIVE (threshold=5) and DIALOGUE (threshold=4)
- Make base threshold configurable via R3Config

---

### 3.3 P3 -- MEDIUM (Enhancements)

#### GAP-R3-05: P21 Feedback Loop Not Wired

**Problem**: `PruneRegretDetector` writes PRUNE_REGRET signals to `st_feedback_signals` when a user query matches a recently pruned entity. But P21 (the feedback pipeline) never reads these signals. The regret detection is write-only with no consumer.

**Impact**: System cannot auto-tune decay lambdas based on prune regret rate. Over-aggressive pruning goes undetected.

---

#### GAP-R3-06: MW v2 Signals Not Integrated

**Problem**: Several MW v2 signals available on P03EventState are ignored by R3:

| Signal | Available On | Could Improve | How |
|--------|-------------|--------------|-----|
| memory_tier | P03EventState | Decay rate | Per-tier lambdas: core=0.001, important=0.01, routine=0.05, peripheral=0.10 |
| identity_relevance | P03EventState | Immunity | Grant immunity if identity_relevance > 0.7 |
| surprise_level | P03EventState | Novelty scoring | Supplement content novelty with cognitive novelty |
| social_intimacy_level | P03EventState | Decay rate | Intimate social memories decay slower |
| elaboration_depth | P03EventState | Novelty scoring | Elaborate events get novelty bonus |
| cognitive_trace_id | P03EventState | Dedup | Same trace = same conversation = merge-eligible |

**Impact**: R3 treats all memories uniformly instead of leveraging the rich signal surface from upstream phases.

---

#### GAP-R3-07: Novelty x Reconciliation Not Integrated

**Problem**: High-novelty events from R3.1 duplicate detection don't influence reconciliation decisions. A first-ever-seen activity type should bias toward CREATE rather than EXTEND, but the novelty_score is not passed to the reconciliation engine.

**Note**: This gap becomes moot when the Universal Reconciliation Engine (M9) is implemented, as it will consume novelty directly from the candidate payload. For the current legacy reconciliation_engine.py, this is not worth fixing.

---

## 4. Execution Flow (Revised -- Reconciliation Removed)

```text
R3 Orchestrator: R3DedupDecay.run(envelope, ctx)
    |
    +-- Skip check (no events/clusters?)
    |
    +-- Create stores: R3Stores.create_production(syscalls)
    |       access_store       = InMemoryAccessStore()      [GAP-R3-01]
    |       pruned_entity_store = InMemoryPrunedEntityStore() [GAP-R3-01]
    |       learned_weights_store = SyscallLearnedWeightsStore(syscalls) [OK]
    |       audit_store        = InMemoryAuditStore()        [GAP-R3-01]
    |
    +-- Query entities for decay evaluation (TruthQueryService)
    |
    +-- execute():
    |       |
    |       +-- R3.1: DuplicateDetector.detect()
    |       |       +-- SimHasher.compute_simhash()
    |       |       +-- TwoStageDeduplicator.find_duplicates()
    |       |       +-- Novelty scoring (bonuses/penalties)
    |       |       +-- OUTPUT: event.is_duplicate, event.novelty_score
    |       |                 -> consumed by R4 (all events), R5 (min_novelty filter), R6 (skip dups)
    |       |
    |       +-- R3.3: UnifiedDecayEngine.compute_decay_factor()  [GAP-R3-02]
    |       |       +-- compute_effective_lambda(table_name, importance, confidence, obs_count)
    |       |       +-- decay_factor = exp(-lambda_eff * days)
    |       |       +-- classify: ACTIVE / ARCHIVE_CANDIDATE / PRUNE_CANDIDATE
    |       |
    |       +-- R3.4: RetentionEnforcer.evaluate_batch()
    |       |       +-- ImmunityChecker.check_record_immunity()
    |       |       +-- KEEP (decay >= 0.10) / ARCHIVE (0.01-0.10) / TOMBSTONE (< 0.01)
    |       |       +-- OUTPUT: r3_decay_updates -> staged by R6, written by R7
    |       |
    |       +-- R3.5: PruneAuditLogger.log_prune_decision()
    |       |       +-- 10% sampling (TOMBSTONE always 100%)
    |       |       +-- Writes to audit_store [IN-MEMORY, GAP-R3-01]
    |       |
    |       +-- R3.6: AccessTracker.record_access()
    |       |       +-- BayesianLambdaEstimator.estimate_lambda()  [OUTPUT UNUSED, GAP-R3-02]
    |       |       +-- Writes to access_store [IN-MEMORY, GAP-R3-01]
    |       |
    |       +-- R3.7: PruneRegretDetector.check_query_for_regret()
    |       |       +-- Cosine match against pruned entities (14-day window)
    |       |       +-- Reads/writes pruned_entity_store [IN-MEMORY, GAP-R3-01]
    |       |
    |       +-- R3.8: AdaptiveDeduplicationStrategy.update_event_count()
    |       |       +-- Strategy selection (pairwise < 10K, bucketing 10K-50K, LSH > 50K)
    |       |
    |       +-- [REMOVED] R3.9: ReconciliationEngine -- no longer in scope
    |
    +-- Return R3PhaseStats + enriched envelope
```

---

## 5. Key Constants & Configuration

### 5.1 Decay Lambdas (Per-Table)

| Table | Lambda | Half-Life | Description |
|-------|--------|-----------|-------------|
| st_hipp_events | 0.100 | 7 days | Raw events (fastest decay) |
| st_prospective | 0.020 | 35 days | Goals and plans |
| st_procedural | 0.010 | 69 days | Habits and routines |
| st_kg_edges | 0.008 | 87 days | Knowledge graph relationships |
| st_epi | 0.005 | 139 days | Episodes |
| st_sem | 0.003 | 231 days | Semantic facts |
| st_social | 0.002 | 347 days | Social relationships |
| st_kg_dom | 0.001 | 693 days | Knowledge graph entities |

### 5.2 Dedup Thresholds

| Constant | Value | Location | Purpose |
|----------|-------|----------|---------|
| SimHash hamming (base) | 3 | simhasher.py | Near-duplicate bit distance |
| SimHash TRANSACTION | 1 | simhasher.py | Strict for structured data |
| SimHash VOICE_MEMO | 5 | simhasher.py | Loose for transcriptions |
| Cosine DUPLICATE | 0.85 | two_stage_dedup.py | Stage 2 confirmed duplicate |
| Cosine LIKELY_DUPLICATE | 0.70 | two_stage_dedup.py | Stage 2 likely duplicate |
| Embedding fallback | 0.90 | two_stage_dedup.py | Catch duplicates SimHash missed |

### 5.3 Retention Thresholds

| Threshold | Value | Decision |
|-----------|-------|----------|
| ACTIVE | decay >= 0.10 | KEEP |
| ARCHIVE | 0.01 <= decay < 0.10 | ARCHIVE (reversible) |
| TOMBSTONE | decay < 0.01 | TOMBSTONE (permanent) |
| Resurrection floor | 0.70 | Minimum decay after resurrection |

### 5.4 Novelty Bonuses

| Bonus | Default | Trigger |
|-------|---------|---------|
| first_occurrence | 0.15 | Activity type seen for first time |
| milestone | 0.20 | Keywords: birthday, anniversary, graduation, wedding, etc. |
| rare_pattern | 0.10 | Activity occurred < 5 times in 90 days |
| temporal_anomaly | 0.10 | Activity at unusual hour |
| routine_penalty | -0.30 | Routine activity (e.g., daily coffee) |

### 5.5 Feature Flags

| Flag | Default | Controls |
|------|---------|----------|
| enable_reconciliation | **False** | Legacy ReconciliationEngine (R3.9) -- DISABLED, M9 replaces |
| is_debug | False | 100% audit sampling vs 10% |
| MinHashConfig.enabled | False | LSH for >50K events |
| family_member_immune | True | Auto-mark FAMILY_MEMBER immune |
| milestone_events_immune | True | Auto-mark milestone events immune |

---

## 6. Store Protocol Matrix

| Store | Protocol | InMemory Impl | DB-Backed Impl | Table | Status |
|-------|----------|--------------|-----------------|-------|--------|
| Access | AccessStoreProtocol | InMemoryAccessStore | **MISSING** | st_learned_weights | GAP-R3-01 |
| Pruned Entity | PrunedEntityStoreProtocol | InMemoryPrunedEntityStore | **MISSING** | st_pruned_entities | GAP-R3-01 |
| Learned Weights | LearnedWeightsStoreProtocol | InMemoryLearnedWeightsStore | SyscallLearnedWeightsStore | st_learned_weights | OK |
| Audit | AuditStoreProtocol | InMemoryAuditStore | **MISSING** | st_consolidation_audit | GAP-R3-01 |

---

## 7. Implementation Roadmap

### Phase 1: DB-Backed Stores (GAP-R3-01)

| # | Deliverable | File | Type | Description |
|---|------------|------|------|-------------|
| 1a | SyscallAccessStore | k0/pipelines/p03/stores.py | EDIT | Implement AccessStoreProtocol via syscalls to st_learned_weights |
| 1b | SyscallPrunedEntityStore | k0/pipelines/p03/stores.py | EDIT | Implement PrunedEntityStoreProtocol via syscalls to st_pruned_entities |
| 1c | SyscallAuditStore | k0/pipelines/p03/stores.py | EDIT | Implement AuditStoreProtocol via syscalls to st_consolidation_audit |
| 1d | Wire into create_production() | k0/pipelines/p03/phases/r3_dedup_decay.py | EDIT | Replace InMemory*with Syscall* in R3Stores.create_production() |
| 1e | Tests | tests/k0/pipelines/p03/test_r3_stores.py | NEW | Unit tests for all 3 DB-backed stores |

**Acceptance**: After a P03 cycle, `st_consolidation_audit`, `st_pruned_entities`, and `st_learned_weights` contain R3 data. Data persists across cycles.

### Phase 2: Learned Lambda Wiring (GAP-R3-02)

| # | Deliverable | File | Type | Description |
|---|------------|------|------|-------------|
| 2a | Add learned_lambda_override param | k0/modules/consolidation/algorithms/decay_engine.py | EDIT | Optional override in compute_effective_lambda() and compute_decay_factor() |
| 2b | R3 orchestrator passes learned lambda | k0/pipelines/p03/phases/r3_dedup_decay.py | EDIT | Query BayesianLambdaEstimator output, pass to decay engine when confidence > threshold |
| 2c | Tests | tests/k0/pipelines/p03/test_r3_decay_engine.py | EDIT | Add tests for learned lambda override path |

**Acceptance**: End-to-end: 10+ accesses to entity -> lambda estimated -> next cycle uses learned lambda -> entity decays at personalized rate.

### Phase 3: Observability (GAP-R3-03)

| # | Deliverable | File | Type | Description |
|---|------------|------|------|-------------|
| 3a | OTel trace spans | k0/pipelines/p03/phases/r3_dedup_decay.py | EDIT | Span per sub-phase (dedup, decay, retention, audit, regret) |
| 3b | Prometheus metrics export | k0/pipelines/p03/phases/r3_dedup_decay.py | EDIT | Export R3PhaseStats to metrics registry |
| 3c | Structured log | k0/pipelines/p03/phases/r3_dedup_decay.py | EDIT | Per-cycle summary log with action distribution |

### Phase 4: SimHash Tuning (GAP-R3-04)

| # | Deliverable | File | Type | Description |
|---|------------|------|------|-------------|
| 4a | Configurable base threshold | k0/modules/consolidation/algorithms/simhasher.py | EDIT | Move DEFAULT_THRESHOLD to R3Config |
| 4b | Additional content types | k0/modules/consolidation/algorithms/simhasher.py | EDIT | Add NARRATIVE=5, DIALOGUE=4 thresholds |
| 4c | Tests | tests/k0/pipelines/p03/test_r3_simhasher.py | EDIT | Test new thresholds and configurability |

### Future (Deferred)

| Gap | Blocked By | Notes |
|-----|-----------|-------|
| GAP-R3-05: P21 feedback loop | P21 pipeline implementation | Cross-pipeline, not R3-only |
| GAP-R3-06: MW v2 signal integration | Signal stability verification | Needs MW v2 signals validated in production |
| GAP-R3-07: Novelty x reconciliation | M9 Universal Reconciliation Engine | Moot after M9 |

---

## 8. Dependencies

```
Phase 1 (DB Stores)
    |
    +---> Phase 2 (Learned Lambda)  [needs persistent access patterns]
    |
    +---> Phase 3 (Observability)   [independent, can parallel]
    |
    +---> Phase 4 (SimHash Tuning)  [independent, can parallel]
```

Phase 1 is the foundation. Phases 2/3/4 can proceed in parallel after Phase 1 completes.

---

## 9. Open Questions

| # | Question | Options | Impact |
|---|----------|---------|--------|
| Q1 | Learned lambda: override or blend? | A) Override if confidence > 0.5; B) Weighted blend 70/30 | Affects decay personalization aggressiveness |
| Q2 | Max tombstone per cycle safety limit? | No limit currently; propose 5% of active entities max | Prevents mass data loss on lambda misconfiguration |
| Q3 | Should MinHash LSH default to enabled? | Currently disabled; irrelevant at 1,410 events | Only matters at scale (>10K) |
| Q4 | Acceptable prune regret rate for lambda re-tuning? | No threshold defined; propose alert if > 2% | Requires P21 consumer (GAP-R3-05) |
| Q5 | Decay chicken-and-egg: all 135 episodes have decay_factor=1.0, but sweep queries decay_factor < 0.99 | A) Initial pass computes decay for ALL entities regardless of current factor; B) Change sweep to query ALL entities (remove < 0.99 filter) | Without fix, decay sweep finds nothing and R3 never starts aging memories |
| Q6 | Should R4 filter out events where is_duplicate=True? | A) Yes, skip duplicate events for entity extraction; B) No, let R4 process all (current behavior) | Filtering avoids duplicate KG entities from same-text events |

---

## 10. Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| DB store implementation breaks existing 409 tests | Medium | High | InMemory stores remain for tests; Syscall stores for production only |
| Learned lambda causes over-aggressive decay on cold start | Low | High | Minimum 5 accesses + 7-day spread before lambda eligible; layer default used otherwise |
| GDPR audit table grows unbounded | Medium | Medium | 10% sampling in production; add TTL-based cleanup |
| Regret detection useless without P21 consumer | High | Low | Write-only is still auditable; P21 wiring is deferred |
| SimHash threshold change causes dedup rate regression | Low | Medium | A/B test with current data before deploying |
