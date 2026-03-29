# P03 R3 Dedup/Decay — Phase Discovery & Enhancement Plan

> **Epic 5.4 Discovery**: Full audit of the R3 Deduplication & Decay phase (dedup detection, novelty
> scoring, exponential decay, retention enforcement, immunity, audit logging, access tracking, regret
> detection, scale optimization, and reconciliation). Covers code, contracts, algorithms, data flow,
> storage, observability, tests, dependencies, performance, gaps, and enhancement proposals.

---

## 0. Discovery Metadata

| Field | Value |
| ----- | ----- |
| Pipeline ID | P03 |
| Module Scope | consolidation.simhasher, consolidation.two_stage_dedup, consolidation.duplicate_detector, consolidation.decay_engine, consolidation.retention_enforcer, consolidation.immunity_checker, consolidation.novelty_bonus_learner, consolidation.access_tracker, consolidation.prune_audit_logger, consolidation.prune_regret_detector, consolidation.minhash_lsh, consolidation.reconciliation_engine, pipelines.p03.phases.r3_dedup_decay |
| Discovery Date | 2026-03-02 |
| Milestone Target | M5 |
| Governing ADRs | ADR-K010 (P03 consolidation architecture), ADR-K003-v2 (pgvector migration / FAISS elimination), ADR-K010.9 (capability-based security) |
| Related Dossier | `docs/pipelines/P03_consolidation_dossier_v2.md` |
| Author | copilot-claude |
| Status | DRAFT |

---

## 1. Current State Audit

### 1.1 Code Inventory

| # | File (relative path) | Lines | Status | Last Modified | Purpose |
| - | -------------------- | ----- | ------ | ------------- | ------- |
| 1 | k0/pipelines/p03/phases/r3_dedup_decay.py | 1309 | MOD | 2026-01-18 | Orchestrates all R3 sub-phases (R3.1-R3.9): duplicate detection, novelty scoring, decay computation, retention evaluation, immunity checking, audit logging, access tracking, regret detection, scale optimization, and reconciliation |
| 2 | k0/modules/consolidation/algorithms/simhasher.py | 158 | LEGACY | 2026-01-02 | Implements 64-bit SimHash using 3-gram shingles with MD5 hashing and content-type-aware Hamming thresholds |
| 3 | k0/modules/consolidation/algorithms/two_stage_dedup.py | 303 | LEGACY | 2026-01-02 | Implements Stage1SimHashFilter (Hamming distance) + Stage2EmbeddingVerifier (cosine similarity) two-stage dedup pipeline |
| 4 | k0/modules/consolidation/algorithms/duplicate_detector.py | 416 | LEGACY | 2026-01-02 | Orchestrates SimHash + TwoStage + novelty scoring with milestone/rare-pattern/temporal-anomaly bonuses |
| 5 | k0/modules/consolidation/algorithms/decay_engine.py | 365 | LEGACY | 2026-01-02 | Implements UnifiedDecayEngine: exponential decay with per-layer lambda, importance/confidence/reinforcement modifiers |
| 6 | k0/modules/consolidation/algorithms/retention_enforcer.py | 438 | LEGACY | 2026-01-02 | Implements KEEP/ARCHIVE/TOMBSTONE retention decisions with resurrection support (floor=0.70) |
| 7 | k0/modules/consolidation/algorithms/immunity_checker.py | 369 | LEGACY | 2026-01-02 | Implements two-level immunity: entity-level (FAMILY_MEMBER) and attribute-level (birthday, name, etc.) per ontology |
| 8 | k0/modules/consolidation/algorithms/novelty_bonus_learner.py | 347 | LEGACY | 2026-01-02 | Implements per-space adaptive novelty bonus learning from feedback signals with st_learned_weights persistence |
| 9 | k0/modules/consolidation/algorithms/access_tracker.py | 470 | LEGACY | 2026-01-02 | Tracks entity access patterns (counts, intervals) and provides Bayesian lambda MLE estimation |
| 10 | k0/modules/consolidation/algorithms/prune_audit_logger.py | 498 | LEGACY | 2026-01-02 | Logs prune/archive/tombstone decisions to st_consolidation_audit with GDPR-compliant explanations and sampling |
| 11 | k0/modules/consolidation/algorithms/prune_regret_detector.py | 510 | LEGACY | 2026-01-02 | Tracks pruned entities for 14 days, detects regret via cosine similarity when queries match pruned data |
| 12 | k0/modules/consolidation/algorithms/minhash_lsh.py | 625 | LEGACY | 2026-01-02 | Implements MinHash LSH for sub-linear O(log n) dedup at scale (>50K events) with adaptive strategy switching |
| 13 | k0/modules/consolidation/algorithms/reconciliation_engine.py | 742 | MOD | 2026-01-11 | Implements REINFORCE/EXTEND/CREATE/EVOLVE/CONTRADICT/SKIP/PRUNE decisions by comparing events to truth layer via cosine similarity |
| 14 | k0/contracts/modules/consolidation.simhash_deduplicator.v1.yaml | 68 | LEGACY | N/A | Module contract: SimHash dedup input/output events, latency budget, failure modes |
| 15 | k0/contracts/pipelines/p03_consolidation.v1.yaml | 397 | LEGACY | N/A | Pipeline contract: R0-R8 stages, triggers, capabilities, DAG, topics |
| 16 | tests/k0/pipelines/p03/test_r3_simhasher.py | 230 | LEGACY | 2026-01-02 | Tests SimHasher: hashing, hamming distance, content-type thresholds (25 tests) |
| 17 | tests/k0/pipelines/p03/test_r3_two_stage_dedup.py | 446 | LEGACY | 2026-01-02 | Tests TwoStageDeduplicator: stage1 filter, stage2 verify, combined flow (20 tests) |
| 18 | tests/k0/pipelines/p03/test_r3_duplicate_detector.py | 542 | LEGACY | 2026-01-02 | Tests DuplicateDetector: duplicate detection, novelty scoring, bonuses (29 tests) |
| 19 | tests/k0/pipelines/p03/test_r3_decay_engine.py | 433 | LEGACY | 2026-01-02 | Tests UnifiedDecayEngine: per-layer lambdas, modifiers, classification (44 tests) |
| 20 | tests/k0/pipelines/p03/test_r3_retention_enforcer.py | 562 | LEGACY | 2026-01-02 | Tests RetentionEnforcer: KEEP/ARCHIVE/TOMBSTONE decisions, resurrection, batch (36 tests) |
| 21 | tests/k0/pipelines/p03/test_r3_immunity_checker.py | 432 | LEGACY | 2026-01-02 | Tests ImmunityChecker: entity-level, attribute-level, ontology matching (45 tests) |
| 22 | tests/k0/pipelines/p03/test_r3_novelty_learner.py | 386 | LEGACY | 2026-01-02 | Tests AdaptiveNoveltyBonusLearner: feedback signals, bonus adjustment, persistence (25 tests) |
| 23 | tests/k0/pipelines/p03/test_r3_access_tracker.py | 420 | LEGACY | 2026-01-02 | Tests AccessTracker + BayesianLambdaEstimator: recording, eligibility, MLE (35 tests) |
| 24 | tests/k0/pipelines/p03/test_r3_prune_audit.py | 700 | LEGACY | 2026-01-02 | Tests PruneAuditLogger: sampling, tombstone always-log, explanations, context (34 tests) |
| 25 | tests/k0/pipelines/p03/test_r3_prune_regret.py | 718 | LEGACY | 2026-01-02 | Tests PruneRegretDetector: tracking, query matching, regret signals, cleanup (35 tests) |
| 26 | tests/k0/pipelines/p03/test_r3_minhash_lsh.py | 462 | LEGACY | 2026-01-02 | Tests MinHashLSH + AdaptiveStrategy: hashing, indexing, candidates, strategy switches (45 tests) |
| 27 | tests/k0/pipelines/p03/test_r3_integration.py | 700 | MOD | 2026-01-15 | Tests R3DedupDecay orchestrator: full phase execution, component wiring, envelope population (36 tests) |

### 1.2 Contract Inventory

| # | Contract File | Version | Status | Lines | Governs |
| - | ------------- | ------- | ------ | ----- | ------- |
| 1 | k0/contracts/modules/consolidation.simhash_deduplicator.v1.yaml | v1 | active | 68 | module:consolidation.simhash_deduplicator |
| 2 | k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | active | 397 | pipeline:P03_CONSOLIDATION (R0-R8 stages incl. R3) |

### 1.3 Config Inventory

#### 1.3.1 YAML Config Keys

| Config File | Version | Key (dot-path) | Value | Type | Default | Required | Notes |
| ----------- | ------- | --------------- | ----- | ---- | ------- | -------- | ----- |
| k0/contracts/modules/consolidation.simhash_deduplicator.v1.yaml | v1 | latency_budget_ms | 100 | int | 100 | yes | R3 dedup latency target per event |
| k0/contracts/modules/consolidation.simhash_deduplicator.v1.yaml | v1 | idempotent | true | bool | true | yes | SimHash dedup is idempotent |

#### 1.3.2 Environment Variables

| Variable | Type | Default | Required | Used By | Purpose |
| -------- | ---- | ------- | -------- | ------- | ------- |
| K0_DB_URL | url | NONE | yes | k0/db/engine.py (shared) | PostgreSQL connection string used by R3 for truth layer queries, st_consolidation_audit, st_pruned_entities, st_learned_weights |

> **Note**: R3 does not read any R3-specific environment variables. All configuration comes from R3Config/sub-config dataclass defaults or pipeline config dict. Database connectivity is inherited from the shared K0 engine.

#### 1.3.3 Feature Flags

| Flag Name | Source | Default | Scope | Controls | Rollback Behavior |
| --------- | ------ | ------- | ----- | -------- | ----------------- |
| enable_reconciliation | config (R3Config) | true | global | Enables ReconciliationEngine (Issue 4.3.13) for truth-layer comparison decisions | Safe -- next cycle skips reconciliation step, no data loss |
| is_debug | config (R3Config) | false | global | Enables debug-level logging and 100% audit sampling (vs 10% production) | Safe -- reverts to production sampling rate |
| DEFAULT_MINHASH_LSH_ENABLED | code constant (minhash_lsh.py) | false | global | Enables MinHash LSH strategy for >50K events; disabled until M4 stabilization | Safe -- falls back to SimHash bucketing |

#### 1.3.4 Constants & Magic Numbers

| Constant | Location (file:line) | Value | Type | Rationale | Externalize? |
| -------- | -------------------- | ----- | ---- | --------- | ------------ |
| DEFAULT_THRESHOLD | simhasher.py:23 | 3 | int | Hamming distance threshold for near-duplicate; 3 bits out of 64 allows minor edits | yes -- content-type thresholds already vary, base should be configurable |
| CONTENT_TYPE_THRESHOLDS | simhasher.py:14-22 | {TRANSACTION:1, ..., VOICE_MEMO:5} | dict | Content-type-specific thresholds: tighter for structured data (1), looser for creative text (5) | maybe -- stable mapping but production tuning may require adjustment |
| DUPLICATE_THRESHOLD | two_stage_dedup.py:36 | 0.85 | float | Cosine similarity for DUPLICATE classification; standard near-duplicate cutoff | yes -- should be per-content-type like SimHash |
| LIKELY_DUPLICATE_THRESHOLD | two_stage_dedup.py:37 | 0.70 | float | Cosine similarity for LIKELY_DUPLICATE; looser threshold for soft matches | yes |
| SEMANTIC_FALLBACK_THRESHOLD | two_stage_dedup.py:38 | 0.90 | float | Cosine similarity for embedding-only fallback when SimHash disagrees | no -- high bar is intentional for fallback path |
| first_occurrence_bonus | duplicate_detector.py:47 | 0.15 | float | Novelty bonus for first-time activity category; empirical default | yes -- adaptive learning adjusts per-space |
| milestone_bonus | duplicate_detector.py:48 | 0.20 | float | Novelty bonus for milestone keywords (birthday, wedding, etc.) | yes -- adaptive learning adjusts per-space |
| rare_pattern_bonus | duplicate_detector.py:49 | 0.10 | float | Novelty bonus for activity seen < 5 times in 90 days | yes -- adaptive learning adjusts per-space |
| temporal_anomaly_bonus | duplicate_detector.py:50 | 0.10 | float | Novelty bonus for event at unusual hour for that activity type | yes -- adaptive learning adjusts per-space |
| routine_penalty | duplicate_detector.py:51 | 0.30 | float | Novelty penalty for routine patterns; multiplicative (1-0.30) | yes |
| MILESTONE_KEYWORDS | duplicate_detector.py:55-58 | {birthday, anniversary, graduation, wedding, ...} | set | 14 life-event keywords that trigger milestone bonus | maybe -- stable but cultures vary |
| LAYER_LAMBDAS | decay_engine.py:60-69 | {st_hipp_events: 0.100, ..., st_kg_dom: 0.001} | dict | Per-layer base decay rates; half-lives from 7d (hipp) to 693d (knowledge graph) | no -- core architectural constant from Ebbinghaus model |
| ARCHIVE_THRESHOLD | decay_engine.py:74 | 0.10 | float | Decay factor below which entity becomes ARCHIVE_CANDIDATE | yes -- may need per-tier tuning |
| TOMBSTONE_THRESHOLD | decay_engine.py:75 | 0.01 | float | Decay factor below which entity becomes PRUNE_CANDIDATE for permanent deletion | yes -- conservative default, may need adjustment |
| RESURRECTION_FLOOR | retention_enforcer.py:22 | 0.70 | float | Minimum decay factor after resurrection; ensures resurrected entity is meaningfully active | maybe -- Bjork & Bjork (1992) suggests 0.70 is appropriate |
| RESURRECTION_ALERT_THRESHOLD | retention_enforcer.py:25 | 3 | int | Alert after N resurrections of same entity; suggests lambda is too aggressive | yes |
| BONUS_MIN | novelty_bonus_learner.py:28 | 0.05 | float | Lower bound for learned novelty bonus; prevents bonus collapsing to zero | no -- floor guard |
| BONUS_MAX | novelty_bonus_learner.py:29 | 0.30 | float | Upper bound for learned novelty bonus; prevents runaway bonus inflation | no -- ceiling guard |
| DEFAULT_MIN_ACCESS_COUNT | access_tracker.py:29 | 5 | int | Minimum accesses before Bayesian lambda estimation is eligible; from Dossier section 4.4.1 | no -- statistical minimum for MLE |
| DEFAULT_MIN_SPREAD_DAYS | access_tracker.py:30 | 7 | float | Minimum days between first and last access for lambda eligibility | maybe -- could be shorter for high-frequency entities |
| LAMBDA_MIN | access_tracker.py:34 | 0.0001 | float | Floor for estimated lambda (~6931 day half-life); prevents never-decay | no -- safety bound |
| LAMBDA_MAX | access_tracker.py:35 | 0.1 | float | Ceiling for estimated lambda (~7 day half-life); prevents instant-decay | no -- matches fastest layer (st_hipp_events) |
| sample_rate_production | prune_audit_logger.py:210 | 0.10 | float | 10% audit sampling in production; TOMBSTONE always 100% regardless | yes -- compliance requirements may require higher |
| sample_rate_debug | prune_audit_logger.py:211 | 1.0 | float | 100% audit sampling in debug mode | no -- debug always full |
| DEFAULT_UNMATCHED_RETENTION_DAYS | prune_regret_detector.py:31 | 14 | int | Days to keep unmatched pruned entities for regret detection; 90% of regrets within 14d | maybe -- empirical, could be per-space |
| DEFAULT_MATCHED_RETENTION_DAYS | prune_regret_detector.py:32 | 30 | int | Days to keep matched (regret) entities for analysis | maybe |
| STRONG_MATCH_THRESHOLD | prune_regret_detector.py:35 | 0.90 | float | Cosine similarity for STRONG_MATCH regret classification | no -- high bar intentional |
| LIKELY_MATCH_THRESHOLD | prune_regret_detector.py:36 | 0.85 | float | Cosine similarity for LIKELY_MATCH regret classification; minimum for regret signal emission | no |
| SEMANTIC_MATCH_THRESHOLD | prune_regret_detector.py:37 | 0.80 | float | Cosine similarity for SEMANTIC_MATCH; logged but not treated as regret | no |
| DEFAULT_NUM_HASHES | minhash_lsh.py:41 | 128 | int | Total MinHash hash functions for precision | no -- standard LSH parameter |
| DEFAULT_NUM_BANDS | minhash_lsh.py:42 | 32 | int | LSH bands; num_hashes must be divisible by num_bands | no |
| THRESHOLD_PAIRWISE | minhash_lsh.py:46 | 10000 | int | Event count below which O(n) pairwise SimHash is used | yes -- depends on hardware |
| THRESHOLD_BUCKETING | minhash_lsh.py:47 | 50000 | int | Event count above which MinHash LSH activates | yes -- depends on hardware |
| DEFAULT_REINFORCE_THRESHOLD | reconciliation_engine.py:55 | 0.85 | float | Cosine similarity for REINFORCE action (strengthen existing truth) | yes -- may need per-layer tuning |
| DEFAULT_EXTEND_THRESHOLD | reconciliation_engine.py:56 | 0.60 | float | Cosine similarity for EXTEND action (add detail to existing truth) | yes |
| DEFAULT_EVOLVE_THRESHOLD | reconciliation_engine.py:57 | 0.40 | float | Cosine similarity for EVOLVE action (related but distinct) | yes |

### 1.4 Migration Inventory

| # | Migration File | Table(s) | Operation | Columns Affected | Reversible? |
| - | -------------- | -------- | --------- | ---------------- | ----------- |
| 1 | k0/db/alembic/versions/0036_st_consolidation_audit.py | st_consolidation_audit | CREATE | +audit_id, +memory_id, +source_table, +action, +formula_used, +formula_version, +inputs_json, +outputs_json, +explanation, +decision_id, +space_id, +tenant_id, +cycle_id, +confidence, +created_at, +threshold_used, +threshold_name, +outcome_evaluated, +outcome_success, +evaluated_at | yes |
| 2 | k0/db/alembic/versions/0042_st_pruned_entities.py | st_pruned_entities | CREATE | +prune_id, +entity_id, +entity_type, +canonical_name, +embedding, +space_id, +layer_table, +decay_factor_at_prune, +lambda_at_prune, +pruned_at, +matched_query_id, +matched_at, +match_type, +match_confidence | yes |
| 3 | k0/db/alembic/versions/0025_st_learned_weights.py | st_learned_weights | CREATE | +param_key, +space_id, +value, +updated_at | yes |

> **Note**: Migration file numbers are approximate based on schema references in source code. Actual alembic version files should be verified.

---

## 2. API Surface Map

### 2.1 Public Functions & Methods

| # | Module | Function / Method | Signature | Return Type | Consumers | Idempotent? | Notes |
| - | ------ | ----------------- | --------- | ----------- | --------- | ----------- | ----- |
| 1 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.run | (envelope: P03BatchEnvelope, ctx: P03RunnerContext) | P03PhaseResult | P03 PipelineRunner | no | Main phase entry; creates in-memory stores per cycle |
| 2 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.execute | (events, existing_events, entities_for_decay, space_id, tenant_id, cycle_id, current_time, stores: R3Stores) | R3PhaseStats | R3DedupDecay.run | no | Full orchestration: dedup + decay + retention + audit + reconciliation |
| 3 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.detect_duplicate | (event, existing_events, space_id, event_hour, activity_type) | DuplicationResult | R3DedupDecay.process_events | conditional | Idempotent if activity_history unchanged |
| 4 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.process_events | (events, existing_events, space_id, stores: R3Stores) | list[DuplicationResult] | R3DedupDecay.execute | no | Updates adaptive strategy and LSH index |
| 5 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.compute_decay | (table_name, last_observed_at, current_time, importance_score, confidence_score, observation_count) | tuple[float, DecayClassification] | R3DedupDecay.execute | yes | Pure computation, no side effects |
| 6 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.check_immunity | (entity_type, entity_attributes) | ImmunityResult | R3DedupDecay.execute | yes | Pure lookup against ontology |
| 7 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.evaluate_retention | (entity_id, table_name, last_observed_at, current_time, current_status, importance_score, confidence_score, observation_count) | RetentionResult | R3DedupDecay.execute | yes | Pure computation |
| 8 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.evaluate_retention_batch | (records: list[dict], current_time) | BatchRetentionResult | R3DedupDecay.execute | yes | Iterates evaluate_retention |
| 9 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.resurrect_entity | (entity_id, table_name, current_decay, current_status, trigger, current_time) | ResurrectionResult | P04 retrieval | yes | Formula: max(0.70, 0.50 + old_decay * 0.50) |
| 10 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.log_prune_decision | (action, context, space_id, tenant_id, cycle_id, stores) | Optional[str] | R3DedupDecay.execute | no | Writes audit record with sampling |
| 11 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.record_access | (entity_id, entity_table, accessed_at_ms, stores) | AccessStats | P04 retrieval | no | Updates access count and intervals |
| 12 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.estimate_and_persist_lambda | (stats, space_id, stores) | Optional[LambdaEstimate] | P04 retrieval | no | MLE: lambda = n / sum(intervals) |
| 13 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.track_pruned_entity | (entity_id, entity_type, canonical_name, embedding, space_id, layer_table, decay_factor, lambda_value, pruned_at, stores) | str | R3DedupDecay.execute | no | Returns prune_id |
| 14 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.check_query_regret | (query_embedding, space_id, query_id, stores) | list[RegretMatch] | P04 retrieval | no | Emits PRUNE_REGRET signals |
| 15 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.reconcile_event | (event, space_id, tenant_id) | Optional[ReconciliationDecision] | R3DedupDecay.execute | conditional | Idempotent if truth layer unchanged |
| 16 | k0.pipelines.p03.phases.r3_dedup_decay | R3DedupDecay.reconcile_batch | (events, space_id, tenant_id) | dict[str, ReconciliationDecision] | R3DedupDecay.execute | conditional | Iterates reconcile_event |
| 17 | k0.pipelines.p03.phases.r3_dedup_decay | create_r3_phase | (config: Optional[R3Config]) | R3DedupDecay | PipelineRunner factory | yes | Factory with reconciliation enabled by default |
| 18 | k0.modules.consolidation.algorithms.simhasher | SimHasher.compute_simhash | (text: str) | int | TwoStageDeduplicator, DuplicateDetector | yes | Returns 64-bit SimHash |
| 19 | k0.modules.consolidation.algorithms.simhasher | SimHasher.hamming_distance | (hash1: int, hash2: int) | int | TwoStageDeduplicator | yes | XOR popcount |
| 20 | k0.modules.consolidation.algorithms.simhasher | SimHasher.is_near_duplicate | (hash1: int, hash2: int, content_type: str) | bool | DuplicateDetector | yes | Uses content-type threshold |
| 21 | k0.modules.consolidation.algorithms.two_stage_dedup | TwoStageDeduplicator.find_duplicates | (text: str, simhash: int, embedding: list, existing_events: list) | list[DuplicateMatch] | DuplicateDetector | yes | Stage1 + Stage2 pipeline |
| 22 | k0.modules.consolidation.algorithms.duplicate_detector | DuplicateDetector.detect | (event, existing_events, seen_categories, routine_patterns, activity_history, space_id, event_hour, activity_type) -> DuplicationResult | DuplicationResult | R3DedupDecay.detect_duplicate | conditional | Novelty depends on activity_history state |
| 23 | k0.modules.consolidation.algorithms.decay_engine | UnifiedDecayEngine.compute_and_classify | (table_name, last_observed_at, current_time, importance_score, confidence_score, observation_count) | tuple[float, DecayClassification] | R3DedupDecay, RetentionEnforcer | yes | Pure exponential decay |
| 24 | k0.modules.consolidation.algorithms.decay_engine | UnifiedDecayEngine.compute_effective_lambda | (table_name, importance_score, confidence_score, observation_count) | float | R3DedupDecay | yes | lambda_eff = lambda_base * modifiers |
| 25 | k0.modules.consolidation.algorithms.retention_enforcer | RetentionEnforcer.evaluate | (entity_id, table_name, last_observed_at, current_time, current_status, importance_score, confidence_score, observation_count) | RetentionResult | R3DedupDecay | yes | Uses DecayEngine internally |
| 26 | k0.modules.consolidation.algorithms.retention_enforcer | RetentionEnforcer.resurrect | (entity_id, table_name, current_decay, current_status, trigger, current_time) | ResurrectionResult | R3DedupDecay | yes | max(0.70, 0.50 + old * 0.50) |
| 27 | k0.modules.consolidation.algorithms.retention_enforcer | RetentionEnforcer.evaluate_batch | (records: list[dict], current_time) | BatchRetentionResult | R3DedupDecay | yes | Iterates evaluate() |
| 28 | k0.modules.consolidation.algorithms.immunity_checker | ImmunityChecker.should_mark_immune | (entity_type, entity_attributes) | ImmunityResult | R3DedupDecay | yes | Two-level ontology check |
| 29 | k0.modules.consolidation.algorithms.novelty_bonus_learner | AdaptiveNoveltyBonusLearner.process_feedback_signal | (signal_type, space_id, store) | Optional[BonusAdjustment] | R3DedupDecay | no | Persists to st_learned_weights |
| 30 | k0.modules.consolidation.algorithms.novelty_bonus_learner | AdaptiveNoveltyBonusLearner.get_bonuses_as_dict | (space_id, store) | dict[str, float] | R3DedupDecay | yes | Read-only |
| 31 | k0.modules.consolidation.algorithms.access_tracker | AccessTracker.record_access | (entity_id, entity_table, accessed_at_ms, store) | AccessStats | R3DedupDecay | no | Updates count, intervals |
| 32 | k0.modules.consolidation.algorithms.access_tracker | BayesianLambdaEstimator.estimate_lambda | (entity_id, entity_table, intervals_days: list[float]) | Optional[LambdaEstimate] | R3DedupDecay | yes | MLE: lambda = n / sum(intervals) |
| 33 | k0.modules.consolidation.algorithms.prune_audit_logger | PruneAuditLogger.log_prune_decision | (action, context, space_id, tenant_id, cycle_id, store) | Optional[str] | R3DedupDecay | no | Sampling + TOMBSTONE always logged |
| 34 | k0.modules.consolidation.algorithms.prune_regret_detector | PruneRegretDetector.check_query | (query_embedding, space_id, query_id, current_time_ms, store) | list[RegretMatch] | R3DedupDecay | no | Updates match records |
| 35 | k0.modules.consolidation.algorithms.prune_regret_detector | PrunedEntityTracker.track_pruned_entity | (entity_id, entity_type, canonical_name, embedding, space_id, layer_table, decay_factor, lambda_value, pruned_at, store) | str | R3DedupDecay | no | Inserts to st_pruned_entities |
| 36 | k0.modules.consolidation.algorithms.minhash_lsh | MinHashLSH.compute_minhash | (text: str) | np.ndarray | R3DedupDecay, AdaptiveStrategy | yes | Returns uint64 array of num_hashes values |
| 37 | k0.modules.consolidation.algorithms.minhash_lsh | MinHashLSH.find_candidates | (signature: np.ndarray, exclude_event_id: Optional[str]) | list[LSHCandidate] | AdaptiveStrategy | yes | O(log n) band lookup |
| 38 | k0.modules.consolidation.algorithms.minhash_lsh | AdaptiveDeduplicationStrategy.get_strategy | () | DeduplicationStrategy | R3DedupDecay | yes | Based on event_count vs thresholds |
| 39 | k0.modules.consolidation.algorithms.reconciliation_engine | ReconciliationEngine.decide | (event: P03EventState, space_id, tenant_id) | ReconciliationDecision | R3DedupDecay | conditional | Queries truth layers; idempotent if truth unchanged |
| 40 | k0.modules.consolidation.algorithms.reconciliation_engine | ReconciliationEngine.decide_batch | (events: list[P03EventState], space_id, tenant_id) | dict[str, ReconciliationDecision] | R3DedupDecay | conditional | Iterates decide() |

### 2.2 Syscalls Used / Required

| # | Syscall | Signature | Status | Used By | SQL Pattern | Notes |
| - | ------- | --------- | ------ | ------- | ----------- | ----- |
| 1 | TruthQueryService.query_entities_for_decay | (space_id, tenant_id, max_decay_factor, limit_per_layer) -> list[DecayCandidate] | exists | R3DedupDecay.run | SELECT from truth layers WHERE decay_factor < max AND status = 'ACTIVE' | Queries ACTIVE entities needing decay evaluation |
| 2 | TruthQueryService.find_candidates | (embedding, space_id, tenant_id, top_k, min_similarity, layers) -> list[TruthCandidate] | exists | ReconciliationEngine._find_candidates | pgvector <=> similarity search across truth layers | Async with timeout (5s default) |

> **Note**: R3 primarily uses protocol-based storage (AccessStoreProtocol, PrunedEntityStoreProtocol, LearnedWeightsStoreProtocol, AuditStoreProtocol) rather than direct syscalls. In production these would bind to real DB stores; in-memory implementations are used for testing and per-cycle isolation.

### 2.3 Internal Helpers (non-public but critical path)

| # | Module | Function | Signature | Called By | Purpose | Risk if Changed |
| - | ------ | -------- | --------- | --------- | ------- | --------------- |
| 1 | k0.modules.consolidation.algorithms.two_stage_dedup | Stage1SimHashFilter._filter | (text, simhash, existing) -> list[DuplicateMatch] | TwoStageDeduplicator.find_duplicates | Performs O(n) Hamming distance scan for candidate generation | Breaks all dedup -- gates Stage2 verification |
| 2 | k0.modules.consolidation.algorithms.two_stage_dedup | Stage2EmbeddingVerifier._verify | (embedding, candidates, existing) -> list[DuplicateMatch] | TwoStageDeduplicator.find_duplicates | Cosine similarity verification of Stage1 candidates | Breaks accuracy -- false positives without verification |
| 3 | k0.modules.consolidation.algorithms.duplicate_detector | DuplicateDetector._compute_novelty_score | (result, seen_categories, routine_patterns, activity_history, space_id, event_hour, activity_type) -> float | DuplicateDetector.detect | Computes multiplicative novelty: base *(1+first)* (1+milestone) *(1+rare)* (1+temporal) * (1-routine) | Breaks novelty scoring; all downstream ranking affected |
| 4 | k0.modules.consolidation.algorithms.decay_engine | UnifiedDecayEngine._get_base_lambda | (table_name: str) -> float | compute_effective_lambda | Looks up LAYER_LAMBDAS dict; returns default 0.01 for unknown tables | Breaks per-layer differentiation if dict changes |
| 5 | k0.modules.consolidation.algorithms.prune_audit_logger | PruneAuditLogger._generate_explanation | (action, context) -> str | log_prune_decision | Generates GDPR-compliant human-readable explanation for audit record | GDPR compliance risk if explanations become unclear |
| 6 | k0.modules.consolidation.algorithms.prune_regret_detector | cosine_similarity | (a: np.ndarray, b: np.ndarray) -> float | PruneRegretDetector.check_query | Inline cosine similarity for regret matching | Breaks regret detection if removed |
| 7 | k0.modules.consolidation.algorithms.minhash_lsh | MinHashLSH._estimate_similarity | (bands_matched: int) -> float | find_candidates | Approximates Jaccard from band ratio using LSH probability inversion | Affects candidate ranking if formula changes |
| 8 | k0.modules.consolidation.algorithms.reconciliation_engine | ReconciliationEngine._check_overrides | (event: P03EventState) -> Optional[ReconciliationDecision] | decide | Checks is_duplicate (SKIP) and prune_decision=TOMBSTONE (PRUNE) before any DB query | Bypass failure allows unnecessary truth queries |
| 9 | k0.modules.consolidation.algorithms.prune_audit_logger | determine_prune_action | (decay_factor, is_immune, archive_threshold, tombstone_threshold) -> tuple | build_prune_context | Maps decay factor to PruneAction enum with threshold metadata | Breaks audit context if thresholds drift |

### 2.4 Classes & Dataclasses

| # | Module | Class | Base Class / Protocol | Key Attributes | Key Methods | Consumers |
| - | ------ | ----- | --------------------- | -------------- | ----------- | --------- |
| 1 | r3_dedup_decay | R3Config | dataclass | decay_config, access_config, novelty_config, regret_config, dedup_config, immunity_config, audit_config, minhash_config, adaptive_config, reconciliation_config, enable_reconciliation, is_debug | N/A (data only) | R3DedupDecay.**init** |
| 2 | r3_dedup_decay | R3PhaseStats | dataclass | events_processed, duplicates_found, near_duplicates_found, distinct_events, avg_novelty_score, entities_evaluated, keep/archive/tombstone_count, immune_count, decisions_logged, regrets_detected, reconciliation_count, total_duration_ms, dedup_results: dict | to_dict() | R3DedupDecay.execute |
| 3 | r3_dedup_decay | R3Stores | dataclass | access_store, pruned_entity_store, learned_weights_store, audit_store | create_in_memory() | R3DedupDecay.run, tests |
| 4 | r3_dedup_decay | R3DedupDecay | object | _simhasher,_two_stage_dedup, _decay_engine, _retention_enforcer, _access_tracker, _lambda_estimator, _regret_detector, _duplicate_detector, _novelty_learner, _immunity_checker, _audit_logger, _minhash_lsh, _adaptive_strategy, _reconciliation_engine | run(), execute(), detect_duplicate(), process_events(), compute_decay(), check_immunity(), evaluate_retention(), resurrect_entity(), log_prune_decision(), record_access(), check_query_regret(), reconcile_event() | PipelineRunner |
| 5 | simhasher | SimHasher | object | N/A (stateless) | tokenize(), compute_simhash(), hamming_distance(), is_near_duplicate(), compute_and_format() | TwoStageDeduplicator, DuplicateDetector |
| 6 | two_stage_dedup | TwoStageDeduplicator | object | _simhasher,_stage1, _stage2 | find_duplicates(), find_best_duplicate(), find_duplicates_async() | DuplicateDetector |
| 7 | two_stage_dedup | DuplicateMatch | dataclass | event_id, hamming_distance, embedding_similarity, decision_type, check_method | N/A (data only) | TwoStageDeduplicator, DuplicateDetector |
| 8 | two_stage_dedup | DuplicateDecision | Enum | DUPLICATE, LIKELY_DUPLICATE, NOT_DUPLICATE, SEMANTIC_DUPLICATE, DISTINCT | N/A | DuplicateMatch |
| 9 | duplicate_detector | DuplicateDetector | object | _simhasher,_two_stage_dedup, config | detect() | R3DedupDecay |
| 10 | duplicate_detector | DuplicationResult | dataclass | event_id, is_duplicate, near_duplicates, novelty_score, duplicate_of, match_method, max_similarity, bonuses | N/A (data only) | R3DedupDecay, envelope population |
| 11 | duplicate_detector | DuplicateDetectorConfig | dataclass | first_occurrence_bonus, milestone_bonus, rare_pattern_bonus, temporal_anomaly_bonus, routine_penalty, hamming_threshold, exact_duplicate_similarity, near_duplicate_similarity | N/A (data only) | DuplicateDetector |
| 12 | duplicate_detector | NoveltyBonuses | dataclass | first_occurrence, milestone, rare_pattern, temporal_anomaly, routine_penalty | N/A (data only) | DuplicationResult |
| 13 | decay_engine | UnifiedDecayEngine | object | config: DecayConfig | compute_effective_lambda(), compute_decay_factor(), classify_record(), compute_and_classify(), days_until_archive(), get_layer_info() | RetentionEnforcer, R3DedupDecay |
| 14 | decay_engine | DecayConfig | dataclass(frozen) | base_lambda, importance_modifier, confidence_modifier, archive_threshold, tombstone_threshold | N/A (data only) | UnifiedDecayEngine |
| 15 | decay_engine | DecayClassification | Enum | ACTIVE, ARCHIVE_CANDIDATE, PRUNE_CANDIDATE | N/A | UnifiedDecayEngine, RetentionEnforcer |
| 16 | retention_enforcer | RetentionEnforcer | object | _decay_engine, _resurrection_counts | evaluate(), resurrect(), evaluate_batch() | R3DedupDecay |
| 17 | retention_enforcer | RetentionDecision | Enum | KEEP, ARCHIVE, TOMBSTONE | N/A | RetentionResult |
| 18 | retention_enforcer | RetentionResult | dataclass | entity_id, table_name, current_decay, classification, decision, reason, days_since_access, importance_score | N/A (data only) | R3DedupDecay |
| 19 | retention_enforcer | ResurrectionResult | dataclass | entity_id, table_name, trigger, old_decay, new_decay, old_status, new_status, resurrection_count | N/A (data only) | R3DedupDecay |
| 20 | retention_enforcer | BatchRetentionResult | dataclass | total_evaluated, keep_count, archive_count, tombstone_count, results: list[RetentionResult] | N/A (data only) | R3DedupDecay |
| 21 | retention_enforcer | ResurrectionTrigger | Enum | EXPLICIT_ACCESS, ASSOCIATION_HIT, SEARCH_RESULT, CONSOLIDATION_RESCUE | N/A | R3DedupDecay |
| 22 | immunity_checker | ImmunityChecker | object | config: ImmunityCheckerConfig | should_mark_immune(), auto_mark_immunity(), set_entity_immunity() | R3DedupDecay |
| 23 | immunity_checker | ImmunityLevel | Enum | NONE, ATTRIBUTE, ENTITY | N/A | ImmunityResult |
| 24 | immunity_checker | ImmunityResult | dataclass | is_immune, level, reason, protected_attributes | N/A (data only) | R3DedupDecay |
| 25 | novelty_bonus_learner | AdaptiveNoveltyBonusLearner | object | _bonuses, config | adjust_bonus(), process_feedback_signal(), get_all_bonuses(), get_bonuses_as_dict() | R3DedupDecay |
| 26 | novelty_bonus_learner | NoveltyBonusType | Enum | FIRST_OCCURRENCE, MILESTONE, RARE_PATTERN, TEMPORAL_ANOMALY | N/A | AdaptiveNoveltyBonusLearner |
| 27 | novelty_bonus_learner | NoveltyFeedbackSignal | Enum | NOVEL_EVENT_GROUNDED(+0.01), NOVEL_EVENT_NEVER_QUERIED(-0.02), USER_SAYS_NOT_NEW(-0.03), MILESTONE_GROUNDED(+0.01), RARE_PATTERN_USEFUL(+0.01) | N/A | AdaptiveNoveltyBonusLearner |
| 28 | access_tracker | AccessTracker | object | config: AccessTrackerConfig | record_access(), check_learning_eligibility(), get_inter_access_intervals_days() | R3DedupDecay |
| 29 | access_tracker | BayesianLambdaEstimator | object | config: AccessTrackerConfig | estimate_lambda(), persist_lambda() | R3DedupDecay |
| 30 | access_tracker | AccessStats | dataclass | entity_id, entity_table, access_count, first_access_at, last_access_at, access_intervals_ms, spread_days, eligible_for_learning | get_intervals_days() | AccessTracker |
| 31 | access_tracker | LambdaEstimate | dataclass | entity_id, entity_table, lambda_value, confidence, sample_count, half_life_days | N/A (auto half_life) | BayesianLambdaEstimator |
| 32 | prune_audit_logger | PruneAuditLogger | object | config: PruneAuditLoggerConfig, _logged_count, _sampled_out_count | should_log(), log_prune_decision(), get_decision_history() | R3DedupDecay |
| 33 | prune_audit_logger | PruneAction | Enum | ARCHIVE, TOMBSTONE, PRUNE, SKIP | N/A | PruneAuditLogger |
| 34 | prune_audit_logger | PruneDecisionContext | dataclass(frozen) | memory_id, source_table, decay_factor, effective_lambda, days_since_access, access_count, is_immune, threshold_used, threshold_name | to_inputs_dict(), to_outputs_dict() | PruneAuditLogger |
| 35 | prune_audit_logger | PruneAuditRecord | dataclass | audit_id, memory_id, source_table, action, formula_used, formula_version, inputs_json, outputs_json, explanation, decision_id, space_id, tenant_id, cycle_id, confidence, created_at, threshold_used, threshold_name, outcome_evaluated, outcome_success, evaluated_at | to_dict() | PruneAuditLogger |
| 36 | prune_regret_detector | PruneRegretDetector | object | _config: PruneRegretConfig | check_query(), emit_regret_signal() | R3DedupDecay |
| 37 | prune_regret_detector | PrunedEntityTracker | object | _config: PruneRegretConfig | track_pruned_entity() | R3DedupDecay |
| 38 | prune_regret_detector | PrunedEntitiesCleanup | object | _config: PruneRegretConfig | cleanup_old_pruned_entities() | Scheduler (daily 2am) |
| 39 | prune_regret_detector | RegretMatch | dataclass | prune_id, entity_id, entity_type, match_type, match_confidence, query_id, pruned_at, matched_at, canonical_name, layer_table | N/A (data only) | PruneRegretDetector |
| 40 | prune_regret_detector | MatchType | Enum | STRONG_MATCH, LIKELY_MATCH, SEMANTIC_MATCH, NO_MATCH | N/A | PruneRegretDetector |
| 41 | minhash_lsh | MinHashLSH | object | config: MinHashConfig, _lsh_index, _signatures | compute_minhash(), hash_bands(), index_event(), find_candidates(), compute_exact_similarity(), remove_event(), get_stats() | AdaptiveStrategy, R3DedupDecay |
| 42 | minhash_lsh | AdaptiveDeduplicationStrategy | object | minhash_lsh, config,_event_count | get_strategy(), update_event_count(), find_duplicates() | R3DedupDecay |
| 43 | minhash_lsh | DeduplicationStrategy | Enum | SIMHASH_PAIRWISE, SIMHASH_BUCKETING, MINHASH_LSH | N/A | AdaptiveStrategy |
| 44 | minhash_lsh | LSHCandidate | dataclass(frozen) | event_id, bands_matched, estimated_similarity | N/A (data only) | MinHashLSH |
| 45 | reconciliation_engine | ReconciliationEngine | object | _config,_truth_service,_total_decisions,_action_counts,_similarity_histogram | decide(), decide_batch(), get_metrics(), set_truth_service() | R3DedupDecay |
| 46 | reconciliation_engine | ReconciliationConfig | dataclass | reinforce_threshold, extend_threshold, evolve_threshold, candidate_top_k, min_candidate_similarity, prior_confidence, evidence_weight, truth_layers, enable_batch_mode, query_timeout_seconds | N/A (validates in **post_init**) | ReconciliationEngine |
| 47 | reconciliation_engine | ReconciliationDecision | dataclass | action, best_match_id, best_match_layer, similarity_score, confidence, reason, candidates_evaluated, decision_time_ms | to_dict() | R3DedupDecay, event_state |

---

## 3. Algorithm Inventory

### 3.1 Current Algorithms

| # | Algorithm Name | Location | Category | Input Type(s) | Input Constraints | Output Type(s) | Output Guarantees | Time | Space | Det? | Stateful? | State Location | Parameters | Edge Cases | Failure Mode | Fallback | Dependencies | Description |
| - | -------------- | -------- | -------- | ------------- | ----------------- | -------------- | ----------------- | ---- | ----- | ---- | --------- | -------------- | ---------- | ----------- | ------------ | -------- | ------------ | ----------- |
| 1 | SimHash 64-bit | simhasher.py:1 | search | str (text) | non-empty string | int (64-bit hash) | 64-bit unsigned integer | O(n*k) where n=text length, k=3 | O(n) shingles | yes | no | N/A | threshold=3, 3-gram shingles, MD5 hashing | empty text returns 0, short text (<3 chars) single shingle | returns 0 for empty | N/A | hashlib (MD5) | Computes 64-bit locality-sensitive hash from text using 3-gram character shingles with MD5 hashing per Charikar (2002) |
| 2 | Stage1 SimHash Filter | two_stage_dedup.py:40 | filtering | str, int, list[EventState] | simhash must be 64-bit, existing_events non-empty | list[DuplicateMatch] | candidates have hamming_distance <= threshold | O(n) where n=existing events | O(k) candidates | yes | no | N/A | hamming_threshold=3 | empty existing returns [], no simhash returns [] | returns empty list | N/A | SimHasher | Fast O(n) Hamming distance scan to generate dedup candidates from existing events |
| 3 | Stage2 Embedding Verify | two_stage_dedup.py:90 | classification | list[float], list[DuplicateMatch], list[EventState] | embedding must be non-empty, candidates from Stage1 | list[DuplicateMatch] | each match classified DUPLICATE/LIKELY/NOT | O(k) where k=candidates | O(1) | yes | no | N/A | duplicate_thresh=0.85, likely_thresh=0.70 | no candidates returns [], zero-norm embedding returns 0.0 similarity | returns empty list | N/A | numpy (cosine) | Cosine similarity verification of Stage1 SimHash candidates using event embeddings |
| 4 | Two-Stage Dedup Pipeline | two_stage_dedup.py:140 | search | str, int, list[float], list[EventState] | all inputs from Stage1+Stage2 | list[DuplicateMatch] | O(n+k) combined; k ~ 0.01n | O(n+k) | O(k) | yes | no | N/A | all Stage1+Stage2 params | delegates edge cases to stages | raises on Stage2 failure | Stage1-only if no embeddings | SimHasher, numpy | Combines SimHash candidate generation (Stage1) with embedding verification (Stage2) for O(n+k) dedup |
| 5 | Novelty Scoring | duplicate_detector.py:100 | scoring | DuplicationResult, set, set, ActivityHistory, str, int, str | activity_type optional, event_hour 0-23 | float | novelty in [0.0, ~2.0] (multiplicative bonuses can exceed 1.0) | O(1) per event | O(1) | no | yes | _seen_categories set, _routine_patterns set, ActivityHistory | first_occ=0.15, milestone=0.20, rare=0.10, temporal=0.10, routine=0.30 | no activity_type: no first/rare bonus, no event_hour: no temporal bonus, empty history: no routine penalty | returns base_novelty (1-similarity) | N/A | N/A | Computes multiplicative novelty score: base_novelty *(1+first)* (1+milestone) *(1+rare)* (1+temporal) * (1-routine) |
| 6 | Unified Exponential Decay | decay_engine.py:1 | scoring | str (table_name), int (ms timestamps), float (importance), float (confidence), int (obs_count) | table_name in LAYER_LAMBDAS or uses default; timestamps positive | tuple[float, DecayClassification] | decay_factor in [0.0, 1.0], classification always valid | O(1) | O(1) | yes | no | N/A | LAYER_LAMBDAS (8 layers), importance_modifier=0.5, confidence_modifier=0.3, archive_thresh=0.10, tombstone_thresh=0.01 | zero days_since=1.0, unknown table=default lambda 0.01, importance 0=no modifier | returns (1.0, ACTIVE) for zero age | N/A | math.exp | Computes decay_factor = exp(-lambda_eff *days) where lambda_eff = lambda_base* importance *confidence* reinforcement per Ebbinghaus (1885) |
| 7 | Retention Decision | retention_enforcer.py:1 | classification | entity metadata (id, table, timestamps, scores) | entity_id non-empty, timestamps valid | RetentionResult | decision always KEEP/ARCHIVE/TOMBSTONE; exactly one | O(1) | O(1) | yes | no | N/A | archive_thresh=0.10, tombstone_thresh=0.01 | zero decay=TOMBSTONE, 1.0 decay=KEEP, archived entity already=KEEP override | always returns valid decision | N/A | UnifiedDecayEngine | Classifies entity retention as KEEP (decay >= 0.10), ARCHIVE (0.01-0.10), or TOMBSTONE (< 0.01) |
| 8 | Resurrection | retention_enforcer.py:200 | transformation | entity_id, table, float (current_decay), str (status), ResurrectionTrigger | current_decay in [0, 1], status must be ARCHIVED or TOMBSTONE | ResurrectionResult | new_decay >= 0.70 (RESURRECTION_FLOOR), new_status = ACTIVE | O(1) | O(1) | yes | yes | _resurrection_counts dict (in-memory) | floor=0.70, base=0.50, carry=0.50, alert_threshold=3 | already ACTIVE returns unchanged, count > 3 triggers alert | always succeeds | N/A | N/A | Resurrects archived/tombstoned entity: new_decay = max(0.70, 0.50 + old_decay * 0.50) per Bjork & Bjork (1992) retrieval strengthening |
| 9 | Entity Immunity Check | immunity_checker.py:1 | classification | str (entity_type), dict (entity_attributes) | entity_type matches ontology keys | ImmunityResult | is_immune true/false, level NONE/ATTRIBUTE/ENTITY | O(a) where a=attribute count | O(1) | yes | no | N/A | FAMILY_MEMBER=entity immune, PERSON(birthday,name,relationship), PLACE(home,work), EVENT(wedding,birth,death), ORG(employer,school), CONCEPT(core_value,religion,political) | unknown entity_type=not immune, empty attributes=not immune, disabled config=not immune | returns ImmunityResult(is_immune=False) | N/A | N/A | Two-level immunity: Level 1 grants full entity immunity to FAMILY_MEMBER; Level 2 protects specific attributes per ontology |
| 10 | Adaptive Novelty Learning | novelty_bonus_learner.py:1 | scoring | str (signal_type), str (space_id), LearnedWeightsStore | signal_type must match NoveltyFeedbackSignal enum | Optional[BonusAdjustment] | bonus always in [0.05, 0.30] (BONUS_MIN/MAX) | O(1) | O(1) | no | yes | st_learned_weights table | BONUS_MIN=0.05, BONUS_MAX=0.30, 5 signal types with deltas (+0.01 to -0.03) | unknown signal_type=None returned, missing store=raises | returns None for unknown signal | N/A | LearnedWeightsStoreProtocol | Adjusts per-space novelty bonuses from feedback: GROUNDED (+0.01), NEVER_QUERIED (-0.02), USER_SAYS_NOT_NEW (-0.03) |
| 11 | Access Pattern Tracking | access_tracker.py:1 | aggregation | entity_id, entity_table, int (ms timestamp), AccessStore | timestamps positive, entity_id non-empty | AccessStats | access_count >= 1, intervals list <= max_stored (10) | O(1) per access | O(k) intervals | no | yes | AccessStoreProtocol (DB) | min_access=5, min_spread=7d, max_intervals=10 | first access: count=1 no intervals, duplicate timestamp: zero interval filtered | always returns valid stats | N/A | AccessStoreProtocol | Tracks entity access counts, timestamps, and inter-access intervals for Bayesian lambda learning eligibility |
| 12 | Bayesian Lambda MLE | access_tracker.py:300 | scoring | entity_id, entity_table, list[float] (intervals_days) | >= 4 valid intervals (from 5+ accesses), all > 0 | Optional[LambdaEstimate] | lambda in [0.0001, 0.1], confidence in [0.50, 0.95] | O(n) where n=intervals | O(1) | yes | no | N/A | LAMBDA_MIN=0.0001, LAMBDA_MAX=0.1, confidence curve: 4=0.50, 6=0.65, 8=0.75, 10=0.85, 15+=0.95 | < 4 intervals: None, zero intervals: None, all same timestamp: None | returns None if insufficient data | uses default layer lambda | N/A | Estimates per-entity decay lambda via MLE: lambda = n / sum(intervals) for exponential inter-arrival distribution |
| 13 | Prune Audit Logging | prune_audit_logger.py:1 | other | PruneAction, PruneDecisionContext, space/tenant/cycle IDs, AuditStore | context must have valid decay_factor | Optional[str] (audit_id) | TOMBSTONE always logged (100%); others sampled | O(1) | O(1) | no | yes | _logged_count, _sampled_out_count dicts | sample_prod=0.10, sample_debug=1.0, retention=90d, formula="UnifiedDecayFormula" v1.0 | disabled config: always None, immune entity: SKIP explanation | returns None if sampled out | N/A -- sampling is intentional | AuditStoreProtocol | Logs prune decisions to st_consolidation_audit with GDPR Article 22 compliant explanations, 10% sampling (TOMBSTONE always 100%) |
| 14 | Prune Regret Detection | prune_regret_detector.py:1 | search | np.ndarray (query_embedding), str (space_id), str (query_id), int (current_time_ms), PrunedEntityStore | embedding must be non-zero norm | list[RegretMatch] | matches have confidence >= 0.85 (LIKELY_MATCH threshold) | O(m) where m=unmatched pruned entities | O(m) entity load | no | yes | st_pruned_entities table | strong=0.90, likely=0.85, semantic=0.80, unmatched_retention=14d, matched_retention=30d | no unmatched entities: empty list, zero-norm query: 0.0 similarity for all | returns empty list | N/A | numpy, PrunedEntityStoreProtocol | Detects regret by comparing incoming query embeddings against recently pruned entities (14-day window) via cosine similarity |
| 15 | MinHash LSH Indexing | minhash_lsh.py:1 | search | str (text) | non-empty text for meaningful hash | np.ndarray (uint64 signature), list[LSHCandidate] | candidates sorted by bands_matched descending | O(log n) query, O(1) index | O(n * h) where h=num_hashes | yes | yes | _lsh_index dict, _signatures dict (in-memory) | num_hashes=128, num_bands=32, similarity_thresh=0.85, hash_seed=42 | empty text: zero signature, no indexed events: empty candidates | returns empty candidates | N/A | hashlib (SHA256), numpy | Sub-linear O(log n) near-duplicate detection using MinHash with 32-band LSH indexing per Broder (1997) |
| 16 | Adaptive Strategy Switch | minhash_lsh.py:500 | routing | int (event_count) | count >= 0 | DeduplicationStrategy | always returns valid strategy enum | O(1) | O(1) | yes | yes | _event_count, _strategy_switches | pairwise_thresh=10K, bucketing_thresh=50K, lsh_enabled=false | 0 events: SIMHASH_PAIRWISE, LSH disabled: never MINHASH_LSH | always returns valid strategy | falls back to SIMHASH_BUCKETING if LSH disabled | N/A | Routes dedup to optimal strategy based on event count: <10K O(n) pairwise, 10K-50K O(n/b) bucketing, >50K O(log n) MinHash LSH |
| 17 | Reconciliation Decision | reconciliation_engine.py:1 | classification | P03EventState, str (space_id), str (tenant_id) | event must have embedding_768 or embedding field | ReconciliationDecision | action is one of 7 enum values; confidence in [0, 1] | O(k) where k=candidate_top_k per layer | O(k) candidates | no | yes | _total_decisions, _action_counts, _similarity_histogram | reinforce=0.85, extend=0.60, evolve=0.40, top_k=10, min_sim=0.35, timeout=5s, prior_confidence=0.5, evidence_weight=0.3 | no embedding: CREATE, no truth_service: CREATE, timeout: empty candidates, duplicate: SKIP override, tombstone: PRUNE override | returns CREATE for no candidates | CREATE on timeout/error | TruthQueryService, numpy | Determines reconciliation action (REINFORCE/EXTEND/CREATE/EVOLVE/CONTRADICT/SKIP/PRUNE) by comparing event embedding to truth layer candidates via cosine similarity with Bayesian confidence |

### 3.2 Algorithm Gaps

| # | Gap Description | Expected Behavior | Current Behavior | Severity | Proposed Approach | Estimated Complexity |
| - | --------------- | ----------------- | ---------------- | -------- | ----------------- | -------------------- |
| 1 | No per-entity learned lambda integration in DecayEngine | UnifiedDecayEngine should use per-entity lambda from BayesianLambdaEstimator when available | Uses only per-layer LAYER_LAMBDAS; BayesianLambdaEstimator persists to st_learned_weights but DecayEngine never reads it | P1 | Add optional entity_lambda param to compute_effective_lambda(); fall back to LAYER_LAMBDAS if None | small |
| 2 | ImmunityChecker does not check recency or milestone events as skeleton claims | Skeleton says "grants immunity for recent < 7 days" and "milestone events immune" | Actual code uses entity-type/attribute ontology only; no time-based or milestone-event immunity | P2 | Clarify spec: either add recency check or update skeleton to match actual ontology approach | small |
| 3 | SimHash hamming_threshold=3 may miss paraphrases | Paraphrased text with same meaning should be detected as near-duplicate | Hamming distance > 3 for paraphrases that change multiple n-grams but preserve meaning | P2 | Increase threshold for creative content types or add semantic-only dedup path for content_type not in CONTENT_TYPE_THRESHOLDS | small |
| 4 | PruneRegretDetector not wired to st_learning_queue | Regret signals should trigger lambda adjustment via P21 feedback loop | emit_regret_signal writes to st_feedback_signals but no consumer wired | P2 | Wire P21 to consume PRUNE_REGRET signals and adjust lambda for regretted entities | medium |
| 5 | BayesianLambdaEstimator needs minimum 10 access observations for good confidence | New entities should have reasonable decay behavior | New entities always use default LAYER_LAMBDAS until 5+ accesses and 7+ day spread | P3 | Accept as designed: cold-start uses layer defaults, learned lambda replaces after sufficient data | trivial |
| 6 | MinHash LSH disabled by default (DEFAULT_MINHASH_LSH_ENABLED=false) | Should auto-enable for spaces with >50K events | Feature flag forces manual enablement even when event count exceeds threshold | P2 | Add auto-enable logic: if event_count > THRESHOLD_BUCKETING and lsh_enabled=false, log recommendation or auto-switch | small |
| 7 | Reconciliation truth query can timeout (5s) with no retry | Should retry once on timeout for resilience | Single attempt; returns empty candidates on timeout causing all events to become CREATE | P2 | Add single retry with backoff in _find_candidates; already tracks timeout count in metrics | small |
| 8 | R3 execute() uses in-memory stores (R3Stores.create_in_memory) per cycle | Production should use real DB stores for persistence across cycles | Audit records, pruned entities, access stats created in memory and discarded after cycle | P1 | Wire real DB stores in PipelineRunner; in-memory stores appropriate for testing only | medium |
| 9 | Signal gaps: memory_tier, identity_relevance, cognitive_trace_id, elaboration_depth, social_intimacy_level, surprise_level not used by R3 | These signals from upstream phases could improve decay/retention decisions | Not consumed or referenced in any R3 algorithm | P3 | Future enhancement: incorporate memory_tier in decay lambda, identity_relevance in immunity, surprise_level in novelty | medium |
| 10 | Reconciliation does not integrate with novelty scoring | Events with high novelty should bias toward CREATE; low novelty toward REINFORCE | Reconciliation uses only embedding similarity; novelty_score from R3.1 is ignored | P3 | Pass novelty_score to ReconciliationEngine._determine_action as additional signal | small |

---

## 4. Data Flow & I/O Map

### 4.1 Pipeline Stage Map

| Stage Order | Stage ID | Module | Input Event / Topic | Output Event / Topic | Side Effects | Error Topic | Retry Policy |
| ----------- | -------- | ------ | ------------------- | -------------------- | ------------ | ----------- | ------------ |
| 1 | R3.1 Duplicate Detection | consolidation.duplicate_detector (via R3DedupDecay.process_events) | P03BatchEnvelope.events from R2 | envelope.phases.r3_dedup_results, event.is_duplicate, event.novelty_score | Updates adaptive strategy event count, indexes LSH | N/A (internal phase) | no retry (deterministic) |
| 2 | R3.2 Novelty Feedback | consolidation.novelty_bonus_learner | External feedback signals | st_learned_weights bonus adjustments | Writes to st_learned_weights | N/A | no retry |
| 3 | R3.3 Decay Computation | consolidation.decay_engine | TruthQueryService.query_entities_for_decay results | decay_factor, DecayClassification per entity | None (pure computation) | N/A | N/A (stateless) |
| 4 | R3.4 Retention Evaluation | consolidation.retention_enforcer + immunity_checker | Decay results + entity attributes | RetentionResult per entity (KEEP/ARCHIVE/TOMBSTONE) | None (pure computation) | N/A | N/A (stateless) |
| 5 | R3.5 Audit Logging | consolidation.prune_audit_logger | RetentionResult + context | st_consolidation_audit records | Writes audit records (10% sampled, TOMBSTONE 100%) | N/A | no retry (best-effort) |
| 6 | R3.6 Access Tracking | consolidation.access_tracker | P04 retrieval events | AccessStats, LambdaEstimate to st_learned_weights | Writes access stats, persists learned lambda | N/A | no retry |
| 7 | R3.7 Regret Detection | consolidation.prune_regret_detector | P04 query embeddings | RegretMatch list, PRUNE_REGRET signals to st_feedback_signals | Updates st_pruned_entities match fields, inserts feedback signals | N/A | no retry |
| 8 | R3.8 Scale Optimization | consolidation.minhash_lsh | Event count updates | DeduplicationStrategy switch events | In-memory LSH index updates | N/A | N/A |
| 9 | R3.9 Reconciliation | consolidation.reconciliation_engine | P03EventState + truth layer candidates | ReconciliationDecision per event, event state updated | Queries truth layers via TruthQueryService | N/A | no retry (timeout returns CREATE) |

### 4.2 Input Schemas (per stage / module)

**Stage: R3.1 Duplicate Detection**

| # | Field | Type | Required | Nullable | Validation Rule | Source | Example Value |
| - | ----- | ---- | -------- | -------- | --------------- | ------ | ------------- |
| 1 | event.event_id | str | yes | no | non-empty UUID | R0 batch selector | "evt_abc123" |
| 2 | event.content_text | str | yes | no | non-empty string | R0 from st_hipp_events | "Had dinner with Mom at Olive Garden" |
| 3 | event.simhash_hex | str | no | yes | 16-char hex string | R0 or computed inline | "a1b2c3d4e5f6a7b8" |
| 4 | event.embedding_id | str | no | yes | UUID format | R0 from st_vec | "emb_xyz789" |
| 5 | event.activity_type | str | no | yes | string | R2 classification | "DINING" |
| 6 | event.activity_type_ultrabert | str | no | yes | UltraBERT 12-type | R2 UltraBERT classification | "social_dining" |
| 7 | existing_events | list[P03EventState] | yes | no | from envelope.events with embedding_id | R0 batch | [...] |

**Stage: R3.3 Decay Computation**

| # | Field | Type | Required | Nullable | Validation Rule | Source | Example Value |
| - | ----- | ---- | -------- | -------- | --------------- | ------ | ------------- |
| 1 | table_name | str | yes | no | one of 8 layer tables | TruthQueryService | "st_epi" |
| 2 | last_observed_at | int | yes | no | epoch ms, > 0 | Truth layer record | 1700000000000 |
| 3 | current_time | int | yes | no | epoch ms, > last_observed_at | time.time() * 1000 | 1700086400000 |
| 4 | importance_score | float | no | no | [0.0, 1.0], default 0.0 | R1 importance scoring | 0.75 |
| 5 | confidence_score | float | no | no | [0.0, 1.0], default 0.0 | Truth layer record | 0.85 |
| 6 | observation_count | int | no | no | >= 1, default 1 | Truth layer record | 5 |

**Stage: R3.9 Reconciliation**

| # | Field | Type | Required | Nullable | Validation Rule | Source | Example Value |
| - | ----- | ---- | -------- | -------- | --------------- | ------ | ------------- |
| 1 | event.embedding_768 | list[float] or np.ndarray | no | yes | 768-dim UltraBERT vector | R2 embedding | [0.012, -0.034, ...] |
| 2 | event.is_duplicate | bool | yes | no | from R3.1 | R3.1 dedup | false |
| 3 | event.prune_decision | PruneDecision | no | yes | TOMBSTONE overrides to PRUNE | R3.4 retention | None |
| 4 | space_id | str | yes | no | non-empty | envelope.context | "space_family_1" |
| 5 | tenant_id | str | yes | no | non-empty | envelope.context | "tenant_001" |

### 4.3 Output Schemas (per stage / module)

**Stage: R3.1 Duplicate Detection (per event)**

| # | Field | Type | Nullable | Produced By | Consumed By | Example Value |
| - | ----- | ---- | -------- | ----------- | ----------- | ------------- |
| 1 | event.is_duplicate | bool | no | DuplicateDetector.detect | R3.9 reconciliation (SKIP override), R6 merge | true |
| 2 | event.novelty_score | float | no | DuplicateDetector._compute_novelty_score | Envelope summary, downstream ranking | 0.85 |
| 3 | event.duplicate_of_id | str | yes | DuplicateDetector.detect | R6 merge linking | "evt_original_123" |
| 4 | event.near_duplicates_json | str | yes | json.dumps(result.near_duplicates) | Debugging, audit | "[\"evt_456\", \"evt_789\"]" |
| 5 | event.hamming_distance | int | yes | DuplicateMatch.hamming_distance | Debugging | 2 |

**Stage: R3 Phase Summary (R3PhaseStats)**

| # | Field | Type | Nullable | Produced By | Consumed By | Example Value |
| - | ----- | ---- | -------- | ----------- | ----------- | ------------- |
| 1 | duplicates_found | int | no | process_events loop | P03PhaseResult.outputs_summary | 3 |
| 2 | near_duplicates_found | int | no | process_events loop | P03PhaseResult.outputs_summary | 7 |
| 3 | distinct_events | int | no | process_events loop | P03PhaseResult.outputs_summary | 42 |
| 4 | avg_novelty_score | float | no | novelty_sum / events_processed | P03PhaseResult.outputs_summary, metrics | 0.72 |
| 5 | entities_evaluated | int | no | evaluate_retention_batch | Metrics, logging | 150 |
| 6 | keep_count | int | no | BatchRetentionResult | Metrics | 120 |
| 7 | archive_count | int | no | BatchRetentionResult | Metrics | 25 |
| 8 | tombstone_count | int | no | BatchRetentionResult | Metrics | 5 |
| 9 | immune_count | int | no | immunity_checker loop | Metrics | 8 |
| 10 | decisions_logged | int | no | audit_logger loop | Metrics | 15 |
| 11 | reconciliation_count | int | no | reconcile_batch | Metrics | 42 |

### 4.4 Error Outputs

| # | Error Code / Type | Condition | HTTP Status | Handling | Downstream Impact | Recoverable? |
| - | ----------------- | --------- | ----------- | -------- | ----------------- | ------------ |
| 1 | RuntimeError | TruthQueryService not initialized (pool unavailable) | N/A | skip | Reconciliation skipped this cycle; all events become CREATE if no truth service | yes -- next cycle retries pool init |
| 2 | asyncio.TimeoutError | Truth query exceeds 5s timeout | N/A | skip | Returns empty candidates; events default to CREATE action | yes -- transient |
| 3 | ValueError | Invalid R3Config (e.g., thresholds out of order) | N/A | abort | R3 phase cannot initialize | no -- config error |
| 4 | Exception | TruthQueryService.query_entities_for_decay fails | N/A | skip | Decay evaluation runs on empty entity set; no retention decisions this cycle | yes -- transient DB error |
| 5 | ImportError | get_pool() fails (DB not configured) | N/A | skip | Reconciliation disabled for session | maybe -- deployment issue |

### 4.5 Data Transformation Map

| # | Source Field(s) | Transformation | Target Field | Lossy? | Reversible? | Notes |
| - | --------------- | -------------- | ------------ | ------ | ----------- | ----- |
| 1 | event.content_text | SimHasher.compute_simhash: 3-gram MD5 -> 64-bit hash | simhash (int) | yes | no | One-way locality-sensitive hash |
| 2 | event.content_text | MinHashLSH.compute_minhash: 3-gram SHA256 -> 128 uint64 | minhash_signature (np.ndarray) | yes | no | One-way; independent from SimHash |
| 3 | simhash pair | XOR + popcount -> hamming distance | hamming_distance (int) | no | yes | Distance metric, symmetric |
| 4 | embedding pair | dot product / (norm * norm) -> cosine similarity | similarity (float) | no | no | Loses individual vector information |
| 5 | similarity, bonuses | base *(1+first)* (1+milestone) *(1+rare)* (1+temporal) * (1-routine) | novelty_score (float) | yes | no | Multiplicative composition loses individual factors |
| 6 | last_observed_at, current_time, lambda_eff | exp(-lambda_eff * days_since) | decay_factor (float) | no | yes | Invertible given lambda and one timestamp |
| 7 | decay_factor | threshold comparison: < 0.01 PRUNE, < 0.10 ARCHIVE, else ACTIVE | DecayClassification (enum) | yes | no | Discretization loses exact factor |
| 8 | access_intervals | lambda_MLE = n / sum(intervals) | lambda_value (float) | yes | no | Summary statistic loses individual intervals |
| 9 | event embedding, truth embedding | cosine similarity -> threshold comparison -> action | ReconciliationAction (enum) | yes | no | Discretization of continuous similarity |

---

## 5. Storage & Persistence

### 5.1 Tables Touched

| # | Table | Operation | Key Columns Used | Access Pattern | Index Used | Estimated Row Count |
| - | ----- | --------- | ---------------- | -------------- | ---------- | ------------------- |
| 1 | st_consolidation_audit | W | audit_id, memory_id, space_id, tenant_id, cycle_id | point (insert by audit_id) | PK (audit_id) | ~10K (10% sampled) |
| 2 | st_pruned_entities | RW | prune_id, entity_id, space_id, matched_at | point (insert), range (unmatched by space_id), range (cleanup by pruned_at) | PK (prune_id), ix_space_unmatched | ~1K (14-day window) |
| 3 | st_learned_weights | RW | param_key, space_id | point (by param_key + space_id) | PK or unique (param_key, space_id) | ~100 (per space, per bonus type + lambda) |
| 4 | st_feedback_signals | W | entity_id, space_id, signal_type | point (insert) | N/A | ~100 (regret signals) |
| 5 | st_epi (truth layer) | R | space_id, tenant_id, embedding | range (pgvector similarity search) | HNSW index | ~100K |
| 6 | st_sem (truth layer) | R | space_id, tenant_id, embedding | range (pgvector similarity search) | HNSW index | ~50K |
| 7 | st_procedural (truth layer) | R | space_id, tenant_id, embedding | range (pgvector similarity search) | HNSW index | ~10K |
| 8 | st_social (truth layer) | R | space_id, tenant_id, embedding | range (pgvector similarity search) | HNSW index | ~10K |
| 9 | st_prospective (truth layer) | R | space_id, tenant_id, embedding | range (pgvector similarity search) | HNSW index | ~5K |

### 5.2 Column-Level Detail

| Table | Column | Type | Nullable | Default | Read By | Written By | Indexed? | Notes |
| ----- | ------ | ---- | -------- | ------- | ------- | ---------- | -------- | ----- |
| st_consolidation_audit | audit_id | UUID | no | gen_random_uuid() | prune_audit_logger (history) | prune_audit_logger | yes (PK) | Primary key |
| st_consolidation_audit | memory_id | TEXT | no | NONE | prune_audit_logger (history) | prune_audit_logger | yes | Links to source entity |
| st_consolidation_audit | action | VARCHAR(16) | no | NONE | analysis | prune_audit_logger | no | ARCHIVE/TOMBSTONE/PRUNE/SKIP |
| st_consolidation_audit | inputs_json | JSONB | no | NONE | analysis, GDPR | prune_audit_logger | no | Decay factor, lambda, access count |
| st_consolidation_audit | outputs_json | JSONB | no | NONE | analysis, GDPR | prune_audit_logger | no | Action, threshold used |
| st_consolidation_audit | explanation | TEXT | no | NONE | GDPR Article 22 | prune_audit_logger | no | Human-readable decision explanation |
| st_consolidation_audit | created_at | BIGINT | no | NONE | cleanup | prune_audit_logger | yes | Epoch ms |
| st_pruned_entities | prune_id | TEXT | no | NONE | regret_detector | pruned_entity_tracker | yes (PK) | "prune_{uuid_hex16}" format |
| st_pruned_entities | embedding | VECTOR(1024) | no | NONE | regret_detector (cosine) | pruned_entity_tracker | no | Used for cosine similarity matching |
| st_pruned_entities | pruned_at | BIGINT | no | NONE | cleanup | pruned_entity_tracker | yes | Epoch ms; cleanup after 14/30 days |
| st_pruned_entities | matched_at | BIGINT | yes | NULL | cleanup | regret_detector | no | Set when query matches pruned entity |
| st_learned_weights | param_key | TEXT | no | NONE | novelty_learner, lambda_estimator | novelty_learner, lambda_estimator | yes (PK) | "novelty_bonus_{type}" or "decay_lambda_{id}" |
| st_learned_weights | space_id | TEXT | no | NONE | novelty_learner | novelty_learner | yes (PK) | Space isolation |
| st_learned_weights | value | FLOAT | no | NONE | novelty_learner | novelty_learner | no | Learned parameter value |

### 5.3 Query Patterns

| # | Query Purpose | SQL Pattern | Frequency | Expected Latency | Index Coverage | Notes |
| - | ------------- | ----------- | --------- | ---------------- | -------------- | ----- |
| 1 | Insert audit record | INSERT INTO st_consolidation_audit (audit_id, memory_id, ...) VALUES (...) | per-entity, 10% sampled | < 5ms | PK | TOMBSTONE always logged |
| 2 | Get decision history | SELECT * FROM st_consolidation_audit WHERE memory_id = ? ORDER BY created_at DESC LIMIT ? | on-demand | < 10ms | ix_memory_id | For debugging and GDPR requests |
| 3 | Get unmatched pruned entities | SELECT * FROM st_pruned_entities WHERE space_id = ? AND matched_at IS NULL | per-query regret check | < 50ms at ~1K rows | ix_space_unmatched | Scans all unmatched in space |
| 4 | Update pruned entity match | UPDATE st_pruned_entities SET matched_query_id=?, matched_at=?, match_type=?, match_confidence=? WHERE prune_id=? | per-regret match | < 5ms | PK | Point update |
| 5 | Cleanup old pruned entities | DELETE FROM st_pruned_entities WHERE (matched_at IS NULL AND pruned_at < ?) OR (matched_at IS NOT NULL AND matched_at < ?) | daily (2am) | < 100ms | ix_pruned_at | 14-day unmatched, 30-day matched |
| 6 | Get/set learned weight | SELECT value FROM st_learned_weights WHERE param_key=? AND space_id=? | per-feedback | < 5ms | PK | Upsert pattern |
| 7 | Truth layer candidate search | SELECT *, embedding <=> ? AS sim FROM st_epi WHERE space_id=? AND tenant_id=? ORDER BY sim LIMIT ? | per-event reconciliation | < 100ms | HNSW | pgvector cosine distance, repeated per layer |
| 8 | Query entities for decay | SELECT * FROM {layer} WHERE space_id=? AND tenant_id=? AND decay_factor < ? AND status='ACTIVE' LIMIT ? | per-cycle (batch) | < 200ms | ix_space_decay | 100 per layer, across 5 layers |

### 5.4 Storage Gaps

| # | Gap | Current State | Required State | Migration Needed? | Priority |
| - | --- | ------------- | -------------- | ----------------- | -------- |
| 1 | R3 uses in-memory stores per cycle | R3Stores.create_in_memory() discards data after cycle | Real DB stores that persist audit records, pruned entities, learned weights across cycles | no (code-only: wire real store implementations) | P1 |
| 2 | No composite index on st_pruned_entities (space_id, matched_at) | Likely sequential scan on unmatched query | Composite index for efficient unmatched entity lookup | yes | P2 |
| 3 | st_pruned_entities embedding uses VECTOR(1024) | Hardcoded dimension in code | Should match actual model dimension (768 for UltraBERT) | maybe (verify dimension at insert time) | P2 |
| 4 | No partitioning on st_consolidation_audit | Single table grows indefinitely | Consider time-based partitioning or retention policy | maybe | P3 |

---

## 6. Event Bus & Topics

### 6.1 Topics Consumed

| # | Topic | Schema | Producer | Consumer | Ordering | Idempotency Key |
| - | ----- | ------ | -------- | -------- | -------- | --------------- |
| 1 | k0.consolidation.trigger | k0/contracts/pipelines/p03_consolidation.v1.yaml | Scheduler (interval/threshold) | P03 PipelineRunner (R0 entry) | ordered | cycle_id |
| 2 | (internal) P03BatchEnvelope from R2 | N/A (in-process) | R2 episodic integration | R3 dedup/decay | ordered (sequential phases) | cycle_id |

> **Note**: R3 does not directly consume bus topics. It receives its input via the P03BatchEnvelope passed in-process from R2 by the PipelineRunner. Access tracking and regret detection are triggered by P04 retrieval events, not bus topics.

### 6.2 Topics Emitted

| # | Topic | Schema | Emitter | Known Consumers | Payload Size | Frequency |
| - | ----- | ------ | ------- | --------------- | ------------ | --------- |
| 1 | (internal) PRUNE_REGRET signal | st_feedback_signals row | prune_regret_detector.emit_regret_signal | P21 Feedback Loop (not yet wired) | ~500B | rare (~1-5/day) |

> **Note**: R3 does not emit bus events. It modifies the P03BatchEnvelope in-process (setting is_duplicate, novelty_score, reconciliation fields) and writes directly to database tables. The PRUNE_REGRET signal is a database record, not a bus event.

### 6.3 Topic Gaps (needed but missing)

| # | Proposed Topic | Purpose | Producer | Consumer | Schema Draft | Priority |
| - | -------------- | ------- | -------- | -------- | ------------ | -------- |
| 1 | k0.consolidation.regret.detected | Notify downstream that a pruned entity was queried (regret event) | prune_regret_detector | P21 feedback loop, monitoring | {entity_id: str, prune_id: str, match_type: str, confidence: float, space_id: str} | P2 |
| 2 | k0.consolidation.retention.decided | Broadcast retention decisions for monitoring and audit dashboards | R3 audit logger | Monitoring, analytics | {entity_id: str, action: str, decay_factor: float, cycle_id: str} | P3 |

---

## 7. Observability Audit

### 7.1 Existing Metrics

| # | Metric Name | Type | Location | Labels | Purpose | Alert Threshold |
| - | ----------- | ---- | -------- | ------ | ------- | --------------- |
| 1 | R3PhaseStats.duplicates_found | gauge | r3_dedup_decay.py (R3PhaseStats.to_dict) | cycle_id | Count of exact duplicates detected per cycle | none |
| 2 | R3PhaseStats.near_duplicates_found | gauge | r3_dedup_decay.py (R3PhaseStats.to_dict) | cycle_id | Count of near-duplicates detected per cycle | none |
| 3 | R3PhaseStats.avg_novelty_score | gauge | r3_dedup_decay.py (R3PhaseStats.to_dict) | cycle_id | Average novelty score across processed events | none |
| 4 | R3PhaseStats.keep_count | gauge | r3_dedup_decay.py (R3PhaseStats.to_dict) | cycle_id | Entities retained per cycle | none |
| 5 | R3PhaseStats.archive_count | gauge | r3_dedup_decay.py (R3PhaseStats.to_dict) | cycle_id | Entities archived per cycle | none |
| 6 | R3PhaseStats.tombstone_count | gauge | r3_dedup_decay.py (R3PhaseStats.to_dict) | cycle_id | Entities tombstoned per cycle | > 100/cycle (mass pruning alert) |
| 7 | R3PhaseStats.immune_count | gauge | r3_dedup_decay.py (R3PhaseStats.to_dict) | cycle_id | Entities protected by immunity per cycle | none |
| 8 | R3PhaseStats.decisions_logged | gauge | r3_dedup_decay.py (R3PhaseStats.to_dict) | cycle_id | Audit records written per cycle | none |
| 9 | R3PhaseStats.regrets_detected | gauge | r3_dedup_decay.py (R3PhaseStats.to_dict) | cycle_id | Prune regrets detected per cycle | > 10/day (lambda too aggressive) |
| 10 | R3PhaseStats.current_strategy | gauge | r3_dedup_decay.py (R3PhaseStats.to_dict) | cycle_id | Active dedup strategy name | none |
| 11 | R3PhaseStats.reconciliation_count | gauge | r3_dedup_decay.py (R3PhaseStats.to_dict) | cycle_id | Events reconciled per cycle | none |
| 12 | R3PhaseStats.total_duration_ms | gauge | r3_dedup_decay.py (R3PhaseStats.to_dict) | cycle_id | Total R3 phase execution time | > 5000ms (performance regression) |
| 13 | PruneAuditLogger._logged_count | counter | prune_audit_logger.py | action_type | Cumulative audit records by action type | none |
| 14 | PruneAuditLogger._sampled_out_count | counter | prune_audit_logger.py | action_type | Cumulative sampled-out decisions by action type | none |
| 15 | ReconciliationEngine._total_decisions | counter | reconciliation_engine.py | N/A | Total reconciliation decisions made | none |
| 16 | ReconciliationEngine._action_counts | counter | reconciliation_engine.py | action | Reconciliation decisions by action type | none |
| 17 | ReconciliationEngine._similarity_histogram | histogram | reconciliation_engine.py | bucket | Distribution of similarity scores | none |
| 18 | ReconciliationEngine._query_errors | counter | reconciliation_engine.py | N/A | Truth query errors | > 5/cycle (DB connectivity issue) |
| 19 | ReconciliationEngine._query_timeouts | counter | reconciliation_engine.py | N/A | Truth query timeouts | > 3/cycle (performance issue) |
| 20 | MinHashLSH._query_count | counter | minhash_lsh.py | N/A | LSH queries performed | none |
| 21 | AdaptiveDeduplicationStrategy._strategy_switches | counter | minhash_lsh.py | from, to | Strategy switches with event count | any (should be rare) |
| 22 | ImmunityMetricsCollector | counter | immunity_checker.py | metric_type | Auto-marked and skipped immunity counts | none |

> **Note**: R3 metrics are primarily tracked via dataclass fields (R3PhaseStats, engine-level counters) rather than Prometheus-style metrics. They are exposed via to_dict() and structured logging. No formal OpenTelemetry metrics instrumentation exists.

### 7.2 Existing Traces / Spans

| # | Span Name | Location | Attributes | Parent Span | Purpose |
| - | --------- | -------- | ---------- | ----------- | ------- |
| 1 | N/A | N/A | N/A | N/A | No OpenTelemetry spans defined in R3 |

> **Note**: R3 has no explicit OpenTelemetry trace spans. Timing is captured via R3PhaseStats.total_duration_ms and P03PhaseResult.duration_ms. This is a gap for production observability.

### 7.3 Structured Log Points

| # | Log Level | Location | Message Pattern | Fields | Purpose |
| - | --------- | -------- | --------------- | ------ | ------- |
| 1 | INFO | r3_dedup_decay.py:run | "R3: Starting deduplication & decay phase" | cycle_id, tenant_id, space_id, event_count, cluster_count | Phase entry point |
| 2 | INFO | r3_dedup_decay.py:run (skip) | "R3: Skipping phase - no events or clusters" | cycle_id, duration_ms | Skip conditions met |
| 3 | DEBUG | r3_dedup_decay.py:run | "R3: Queried {N} entities for decay evaluation" | cycle_id, entity_count | Decay query results |
| 4 | WARNING | r3_dedup_decay.py:run | "R3: Could not initialize TruthQueryService: {e}" | error | Pool unavailable |
| 5 | WARNING | r3_dedup_decay.py:run | "R3: Failed to query entities for decay: {e}" | error | Decay query failure |
| 6 | INFO | r3_dedup_decay.py:run (complete) | "R3: Deduplication & decay phase complete" | cycle_id, duplicates_found, near_duplicates_found, distinct_events, avg_novelty, duration_ms | Phase completion summary |
| 7 | INFO | r3_dedup_decay.py:execute | "R3 phase complete: {N} events, {N} entities, {N} decisions logged, {N}ms" | events_processed, entities_evaluated, decisions_logged, total_duration_ms | Execution summary |
| 8 | INFO | r3_dedup_decay.py:execute | "R3.9 reconciliation: {N} events, REINFORCE={N}, EXTEND={N}, CREATE={N}, EVOLVE={N}" | reconciliation stats | Reconciliation summary |
| 9 | INFO | reconciliation_engine.py | "ReconciliationEngine initialized (enabled)" | N/A | Engine startup |
| 10 | WARNING | reconciliation_engine.py | "ReconciliationEngine._find_candidates called without truth_service" | N/A | Missing dependency |
| 11 | ERROR | reconciliation_engine.py | "Truth query timeout after {N}s for space={s} tenant={t}" | timeout, space_id, tenant_id | Timeout alert |
| 12 | DEBUG | access_tracker.py | "Access recorded: entity={id} table={t} count={n} eligible={b}" | entity_id, entity_table, access_count, eligible_for_learning | Access tracking |
| 13 | INFO | access_tracker.py (BayesianLambdaEstimator) | "Lambda estimated: entity={id} table={t} lambda={v} confidence={c} samples={n} half_life={d}d" | entity_id, lambda_value, confidence, sample_count, half_life_days | Lambda learning |
| 14 | INFO | prune_regret_detector.py | "Prune regret detected" | prune_id, entity_id, query_id, match_type, confidence, space_id | Regret event |
| 15 | INFO | prune_regret_detector.py | "Emitted PRUNE_REGRET signal" | entity_id, prune_id, confidence, space_id | Signal emission |
| 16 | INFO | minhash_lsh.py (AdaptiveStrategy) | "Strategy switch: {old} -> {new} at {count} events" | old_strategy, new_strategy, event_count | Strategy change |

### 7.4 Observability Gaps

| # | Gap | What's Missing | Impact if Unresolved | Priority |
| - | --- | -------------- | -------------------- | -------- |
| 1 | No OpenTelemetry trace spans | Trace spans for R3 sub-phases (dedup, decay, retention, reconciliation) | Cannot visualize R3 execution timeline in distributed tracing; hard to identify bottleneck sub-phase | P1 |
| 2 | No Prometheus-style metrics export | All metrics are in-memory dataclass fields, not exported to metrics backend | No alerting, no dashboard, no SLO tracking in production | P1 |
| 3 | No per-entity decay factor histogram | Distribution of decay factors across entities per cycle | Cannot detect systemic over-pruning or under-pruning trends | P2 |
| 4 | No novelty score distribution | Only avg_novelty_score tracked; no histogram | Cannot detect novelty scoring drift or calibration issues | P2 |
| 5 | No resurrection rate metric | Resurrection count tracked in-memory per RetentionEnforcer instance but not exported | Cannot detect if lambda is too aggressive (high resurrection = bad lambda) | P2 |
| 6 | No regret rate over time | Single-cycle count only; no time-series | Cannot detect increasing regret trend that signals lambda tuning needed | P2 |

---

## 8. Test Coverage Audit

### 8.1 Test File Inventory

| # | Test File | Lines | Test Count | Type | Covers (source file) | Last Modified |
| - | --------- | ----- | ---------- | ---- | -------------------- | ------------- |
| 1 | tests/k0/pipelines/p03/test_r3_simhasher.py | 298 | 25 | unit | algorithms/simhasher.py (158 LOC) | 2026-01-14 |
| 2 | tests/k0/pipelines/p03/test_r3_two_stage_dedup.py | 446 | 20 | unit | algorithms/two_stage_dedup.py (303 LOC) | 2026-01-14 |
| 3 | tests/k0/pipelines/p03/test_r3_duplicate_detector.py | 542 | 29 | unit | algorithms/duplicate_detector.py (416 LOC) | 2026-01-14 |
| 4 | tests/k0/pipelines/p03/test_r3_decay_engine.py | 550 | 44 | unit | algorithms/decay_engine.py (365 LOC) | 2026-01-14 |
| 5 | tests/k0/pipelines/p03/test_r3_retention_enforcer.py | 562 | 36 | unit | algorithms/retention_enforcer.py (438 LOC) | 2026-01-14 |
| 6 | tests/k0/pipelines/p03/test_r3_immunity_checker.py | 432 | 45 | unit | algorithms/immunity_checker.py (369 LOC) | 2026-01-14 |
| 7 | tests/k0/pipelines/p03/test_r3_novelty_learner.py | 386 | 25 | unit | algorithms/novelty_bonus_learner.py (347 LOC) | 2026-01-14 |
| 8 | tests/k0/pipelines/p03/test_r3_access_tracker.py | 420 | 35 | unit | algorithms/access_tracker.py (470 LOC) | 2026-01-14 |
| 9 | tests/k0/pipelines/p03/test_r3_prune_audit.py | 700 | 34 | unit | algorithms/prune_audit_logger.py (612 LOC) | 2026-01-14 |
| 10 | tests/k0/pipelines/p03/test_r3_prune_regret.py | 864 | 35 | unit | algorithms/prune_regret_detector.py (637 LOC) | 2026-01-14 |
| 11 | tests/k0/pipelines/p03/test_r3_minhash_lsh.py | 462 | 45 | unit | algorithms/minhash_lsh.py (805 LOC) | 2026-01-14 |
| 12 | tests/k0/pipelines/p03/test_r3_integration.py | 861 | 36 | integration | phases/r3_dedup_decay.py (1309 LOC) + all algorithms | 2026-01-15 |
| **TOTAL** | | **6523** | **409** | | | |

### 8.2 Test Coverage by Sub-Phase

| Sub-Phase | Algorithm(s) | Test File | Tests | Unit? | Integration? | Edge Cases? | Error Paths? | Coverage Est. |
| --------- | ------------ | --------- | ----- | ----- | ------------ | ----------- | ------------ | ------------- |
| R3.1 Dedup | SimHasher, TwoStageDedup, DuplicateDetector, NoveltyScoring | test_r3_simhasher, test_r3_two_stage_dedup, test_r3_duplicate_detector | 74 | yes | partial (integration) | yes (empty text, zero hash, identical events) | partial | ~85% |
| R3.2 Novelty | NoveltyBonusLearner | test_r3_novelty_learner | 25 | yes | no | yes (zero bonus, max clamp) | partial | ~80% |
| R3.3 Decay | UnifiedDecayEngine | test_r3_decay_engine | 44 | yes | no | yes (zero days, max days, edge thresholds) | partial | ~90% |
| R3.4 Retention | RetentionEnforcer, ImmunityChecker | test_r3_retention_enforcer, test_r3_immunity_checker | 81 | yes | partial (integration) | yes (resurrection, boundary values) | partial | ~85% |
| R3.5 Audit | PruneAuditLogger | test_r3_prune_audit | 34 | yes | no | yes (sampling rates, GDPR explanation) | partial | ~80% |
| R3.6 Access | AccessTracker, BayesianLambdaEstimator | test_r3_access_tracker | 35 | yes | no | yes (min observations, interval calculation) | partial | ~80% |
| R3.7 Regret | PruneRegretDetector, PrunedEntityTracker | test_r3_prune_regret | 35 | yes | no | yes (threshold boundaries, cleanup) | partial | ~80% |
| R3.8 Scale | MinHashLSH, AdaptiveStrategy | test_r3_minhash_lsh | 45 | yes | no | yes (empty set, strategy switch thresholds) | partial | ~85% |
| R3.9 Recon | ReconciliationEngine | test_r3_integration (partial) | ~10 | no | yes | partial | partial | ~60% |
| Full Phase | R3DedupDecay orchestrator | test_r3_integration | 36 | no | yes | partial | partial | ~70% |

### 8.3 Test Gaps

| # | Gap | Missing Test | Impact | Priority |
| - | --- | ------------ | ------ | -------- |
| 1 | No dedicated ReconciliationEngine unit tests | test_r3_reconciliation.py covering all 5 actions (REINFORCE, EXTEND, EVOLVE, CONTRADICT, CREATE) individually | Action threshold boundaries untested in isolation; only tested through integration | P1 |
| 2 | No truth layer query failure tests | Tests for TruthQueryService timeout, empty results, partial layer failures | Reconciliation error paths not verified | P1 |
| 3 | No concurrent access tests | Multi-threaded access to InMemoryActivityHistory, InMemoryPrunedEntityStore | Thread safety unverified for shared stores | P2 |
| 4 | No property-based tests | Hypothesis tests for SimHash locality preservation, decay monotonicity, novelty score bounds | Corner cases potentially missed by example-based tests | P2 |
| 5 | No performance regression tests | Benchmark tests for LSH query latency at 10K, 50K, 100K events | Performance regressions undetectable in CI | P2 |
| 6 | No cross-phase data flow tests | Test that R3 output envelope fields are correctly consumed by downstream R6 | Integration contract between R3 and R6 unverified | P2 |
| 7 | No in-memory-to-real-store migration tests | Tests verifying R3Stores.create_in_memory() behavior matches real DB stores | Store implementation swap could silently break R3 | P2 |
| 8 | No GDPR compliance tests | Verify audit logger explanation field covers all GDPR Article 22 scenarios | Compliance gap in automated decision explanation | P3 |

---

## 9. Dependency Map

### 9.1 Upstream Dependencies (R3 consumes)

| # | Dependency | Type | Source | Used By (R3 file) | Purpose | Coupling |
| - | ---------- | ---- | ------ | ------------------ | ------- | -------- |
| 1 | P03BatchEnvelope.events | data | R2 episodic integration | r3_dedup_decay.py | Input event list for dedup processing | tight (shared dataclass) |
| 2 | P03EventState | protocol | k0/pipelines/p03/event_state.py | r3_dedup_decay.py, reconciliation_engine.py | Event state with simhash_hex, embedding_768, content_text, is_duplicate, prune_decision | tight |
| 3 | P03PhaseId, P03PhaseResult | protocol | k0/pipelines/p03/phase_interface.py | r3_dedup_decay.py | Phase lifecycle interface | tight |
| 4 | TruthQueryService | service | k0/modules/consolidation/staging/truth_query_service.py | r3_dedup_decay.py | Queries truth layer tables for decay candidates and reconciliation candidates | medium (injected, optional) |
| 5 | get_pool() | infrastructure | k0 DB pool | r3_dedup_decay.py | Database connection pool for TruthQueryService initialization | loose (lazy init, skip on failure) |
| 6 | PruneDecision, ReconciliationAction | enum | k0/pipelines/p03/event_state.py | reconciliation_engine.py | Event state enums for reconciliation decisions | tight |
| 7 | EpisodeCluster | data | k0/pipelines/p03/phase_outputs.py | r3_dedup_decay.py | Cluster data from R2 | loose (used for context only) |
| 8 | generate_ulid | utility | k0/pipelines/p03/context.py | prune_audit_logger.py | Unique ID generation for audit records | loose |

### 9.2 Downstream Dependents (R3 produces for)

| # | Consumer | Type | What It Receives | Coupling |
| - | -------- | ---- | ---------------- | -------- |
| 1 | R6 Merge Phase | phase | event.is_duplicate, event.duplicate_of_id, event.novelty_score, event.near_duplicates_json | medium (envelope fields) |
| 2 | P03PhaseResult | data | R3PhaseStats via to_dict(), duration_ms, events_processed | tight (phase interface) |
| 3 | P04 Retrieval (future) | pipeline | st_pruned_entities (for regret detection), st_learned_weights (for adaptive lambda) | loose (DB table) |
| 4 | P21 Feedback Loop (future) | pipeline | PRUNE_REGRET signals in st_feedback_signals | loose (DB table, not yet wired) |
| 5 | Monitoring / GDPR | audit | st_consolidation_audit records with decision explanations | loose (DB table) |

### 9.3 Internal Dependencies (R3 algorithm cross-references)

| # | Source | Depends On | Relationship |
| - | ------ | ---------- | ------------ |
| 1 | duplicate_detector.py | simhasher.py | SimHasher for hash computation |
| 2 | duplicate_detector.py | two_stage_dedup.py | TwoStageDeduplicator for stage 1 + stage 2 verification |
| 3 | duplicate_detector.py | novelty_bonus_learner.py | NoveltyBonusLearner for adaptive novelty scoring |
| 4 | duplicate_detector.py | minhash_lsh.py | AdaptiveDeduplicationStrategy for scale-aware dedup |
| 5 | r3_dedup_decay.py | all 12 algorithm files | Orchestrates all algorithms in sequence |
| 6 | r3_dedup_decay.py | truth_query_service.py | Optional dependency for decay entity queries and reconciliation |
| 7 | reconciliation_engine.py | event_state.py | P03EventState, PruneDecision, ReconciliationAction |
| 8 | retention_enforcer.py | decay_engine.py | DecayClassification, DecayConfig for decay results |
| 9 | prune_audit_logger.py | retention_enforcer.py | RetentionDecision for building audit context |

### 9.4 Third-Party / Stdlib Dependencies

| # | Package | Version | Used By | Purpose | License | Pinned? | Upgrade Risk |
| - | ------- | ------- | ------- | ------- | ------- | ------- | ------------ |
| 1 | numpy | >=1.24 | two_stage_dedup, minhash_lsh, prune_regret_detector, reconciliation_engine | Cosine similarity, MinHash signatures, embedding operations | BSD-3-Clause | yes | low |
| 2 | asyncio | stdlib | reconciliation_engine | Async truth layer queries with timeout | N/A | N/A | none |
| 3 | hashlib | stdlib | simhasher, minhash_lsh | MD5 (SimHash), SHA256 (MinHash) hash computation | N/A | N/A | none |
| 4 | math | stdlib | decay_engine | Exponential decay (math.exp), logarithm | N/A | N/A | none |
| 5 | json | stdlib | prune_audit_logger | Serialize inputs_json, outputs_json for audit records | N/A | N/A | none |
| 6 | uuid | stdlib | prune_audit_logger, prune_regret_detector | Generate unique IDs for audit and prune records | N/A | N/A | none |
| 7 | random | stdlib | prune_audit_logger | Sampling decision (random.random() < sample_rate) | N/A | N/A | none |
| 8 | logging | stdlib | all R3 files | Structured logging | N/A | N/A | none |
| 9 | time | stdlib | prune_audit_logger, reconciliation_engine, r3_dedup_decay | Timestamps, duration measurement | N/A | N/A | none |

---

## 10. Performance Baseline

### 10.1 Current Benchmarks

| # | Operation | Dataset Size | p50 | p95 | p99 | Throughput (ops/s) | Memory Peak | Notes |
| - | --------- | ------------ | --- | --- | --- | ------------------ | ----------- | ----- |
| 1 | SimHash compute | 1 event (~100 words) | <1ms | <1ms | <2ms | >10K/s | negligible | Pure CPU, deterministic |
| 2 | Two-stage dedup (stage 1 SimHash) | 50 events pairwise | <5ms | <10ms | <15ms | ~200 batches/s | negligible | O(n^2) pairwise comparison |
| 3 | Two-stage dedup (stage 2 embedding) | 50 events, ~5 candidates | <10ms | <20ms | <30ms | ~100 verifications/s | ~50MB (embeddings in memory) | Cosine similarity on 768-dim vectors |
| 4 | MinHash compute | 1 event | <2ms | <3ms | <5ms | ~500/s | ~1KB per signature (128 uint64) | 128 hash functions, 3-gram shingles |
| 5 | MinHash LSH query | 10K indexed events | <5ms | <10ms | <20ms | ~200/s | ~10MB (index) | 32 bands, 4 rows/band |
| 6 | Decay computation | 1 entity | <0.1ms | <0.1ms | <0.1ms | >100K/s | negligible | Single math.exp call |
| 7 | Retention evaluation (batch) | 100 entities | <5ms | <10ms | <15ms | ~200 batches/s | negligible | Threshold comparison per entity |
| 8 | Immunity check | 1 entity | <0.1ms | <0.1ms | <0.1ms | >100K/s | negligible | Dictionary lookup |
| 9 | Truth layer query (reconciliation) | 1 event, 5 layers | est. 50ms | est. 200ms | est. 500ms | ~5/s | negligible | pgvector HNSW search per layer, 5s timeout |
| 10 | Full R3 phase | 50 events, 100 entities | est. 500ms | est. 1500ms | est. 3000ms | ~2 cycles/s | ~100MB | Dominated by truth queries |

> Note: Benchmarks for items 1-8 are estimated from algorithmic complexity and unit test execution times. Items 9-10 are estimated from DB query patterns; no formal benchmark suite exists for R3.

### 10.2 Known Bottlenecks

| # | Bottleneck | Location (file:line) | Cause | Measured Impact | Proposed Fix | Priority |
| - | ---------- | -------------------- | ----- | --------------- | ------------ | -------- |
| 1 | Sequential truth layer queries in reconciliation | reconciliation_engine.py:_find_candidates | Queries 5 truth layers sequentially with 5s timeout each | Up to 25s worst case per event (5 layers x 5s timeout) | Use asyncio.gather for parallel layer queries | P1 |
| 2 | O(n^2) pairwise SimHash comparison | duplicate_detector.py:process_events | Compares every event against every other event in batch | Quadratic scaling; 500 events = 125K comparisons | Pre-filter with MinHash LSH bands before pairwise | P2 |
| 3 | In-memory LSH index rebuilt per cycle | minhash_lsh.py:MinHashLSH | LSH index discarded after each consolidation cycle | Redundant indexing of previously seen events | Persist LSH index across cycles (or use pgvector for near-dedup) | P3 |
| 4 | Regret detection scans all unmatched entities | prune_regret_detector.py:check_query_regret | Loads all unmatched entities per space for cosine comparison | O(n*m) where n=queries, m=pruned entities | Use pgvector index on st_pruned_entities.embedding | P2 |

### 10.3 Performance Targets

| # | Operation | Target p95 | Target Throughput | Target Memory | Acceptance Criteria |
| - | --------- | ---------- | ----------------- | ------------- | ------------------- |
| 1 | Full R3 phase (50 events, 100 entities) | < 2000ms | > 1 cycle/s | < 256MB | Benchmark test with 50 events and 100 decay entities passes p95 target |
| 2 | SimHash + dedup (500 events) | < 500ms | > 2 batches/s | < 128MB | Benchmark test with 500-event batch completes within budget |
| 3 | Reconciliation per event (5 layers) | < 500ms | > 10 events/s | < 64MB | Truth query parallelization delivers sub-500ms per event |
| 4 | Regret detection per query | < 100ms | > 50 queries/s | < 64MB | pgvector indexed scan on pruned entities |

---

## 11. Gap Analysis & Enhancement Register

### 11.1 Functional Gaps

| # | Gap ID | Gap Description | Current State | Desired State | Severity | Proposed Fix | Related ADR |
| - | ------ | --------------- | ------------- | ------------- | -------- | ------------ | ----------- |
| 1 | FG-R3-001 | No per-entity learned lambda integration with decay engine | decay_engine uses fixed LAYER_LAMBDAS per table; BayesianLambdaEstimator output not consumed | Decay engine consumes per-entity learned lambda from access_tracker, falling back to LAYER_LAMBDAS | P1 | Add lambda_override parameter to compute_decay; wire BayesianLambdaEstimator output | none |
| 2 | FG-R3-002 | ReconciliationEngine has no dedicated unit test file | Only tested through integration tests (~10 cases) | Dedicated test_r3_reconciliation.py with per-action threshold tests | P1 | Create comprehensive unit test suite | none |
| 3 | FG-R3-003 | R3 uses in-memory stores that discard data after cycle | R3Stores.create_in_memory() creates ephemeral stores | Real DB-backed stores that persist audit, pruned entities, learned weights | P1 | Implement real store classes and wire via DI | none |
| 4 | FG-R3-004 | Novelty scoring does not use memory_tier signal | Novelty formula uses activity bonuses only | Incorporate memory_tier from R1 to bias novelty (semantic memories inherently less novel) | P2 | Add memory_tier modifier to novelty computation | none |
| 5 | FG-R3-005 | Prune regret detector not wired to P21 feedback loop | PRUNE_REGRET signals written to DB but never consumed | P21 reads PRUNE_REGRET and adjusts decay lambda downward for affected entity types | P2 | Wire P21 consumer for PRUNE_REGRET topic | none |
| 6 | FG-R3-006 | SimHash hamming threshold=3 too strict for paraphrases | Paraphrased content (same meaning, different words) may exceed threshold 3 | Adaptive threshold per content_type; narrative/paraphrase uses threshold 5-6 | P2 | Add content-type-aware threshold lookup | none |
| 7 | FG-R3-007 | BayesianLambdaEstimator needs min 5 accesses (4 intervals) | Entities with fewer than 5 accesses get no learned lambda | Use informative prior (layer default) with lower observation threshold (e.g., 3) | P3 | Bayesian conjugate prior with layer_lambda as prior mean | none |
| 8 | FG-R3-008 | No surprise_level or social_intimacy_level signal integration | R3 ignores these signals from upstream | High-surprise events should get immunity/lower decay; high-intimacy entities should be retained longer | P3 | Add signal modifiers to decay and retention evaluation | none |

### 11.2 Contract Gaps

| # | Contract | Section / Field | Gap | Impact | Fix |
| - | -------- | --------------- | --- | ------ | --- |
| 1 | consolidation.simhash_deduplicator.v1.yaml | entire contract | Only covers SimHash dedup; no contracts for other R3 algorithms | Decay, retention, reconciliation, novelty, regret detection have no formal contracts | Create v1 contracts for each R3 sub-phase |
| 2 | consolidation.simhash_deduplicator.v1.yaml | output_schema | Missing novelty_score and near_duplicates_json fields | Downstream consumers cannot validate dedup output schema | Add novelty_score: float and near_duplicates_json: str to output |
| 3 | (missing) | N/A | No contract for reconciliation engine | ReconciliationAction decisions (REINFORCE, EXTEND, EVOLVE, CONTRADICT, CREATE) lack formal schema | Create consolidation.reconciliation.v1.yaml |
| 4 | (missing) | N/A | No contract for retention evaluation | Retention decisions (KEEP, ARCHIVE, TOMBSTONE) and immunity rules lack formal schema | Create consolidation.retention.v1.yaml |
| 5 | (missing) | N/A | No contract for prune audit logging | Audit record schema and sampling rules lack formal definition | Create consolidation.prune_audit.v1.yaml |

### 11.3 Architecture Gaps

| # | Area | Gap | ADR Needed? | Impact | Proposed Resolution |
| - | ---- | --- | ----------- | ------ | ------------------- |
| 1 | storage layer | R3Stores uses in-memory protocol implementations; no DB-backed stores | no (existing storage patterns apply) | Data lost between cycles; audit trail not persistent | Implement DB-backed store classes following existing K0 storage patterns |
| 2 | event bus | R3 does not emit bus events for retention decisions or regret detection | yes | No event-driven downstream processing; monitoring relies on log scraping | ADR for R3 event bus integration: retention.decided and regret.detected topics |
| 3 | observability | No OpenTelemetry spans or Prometheus metrics in R3 | no (follow existing K0 observability ADR) | Production monitoring blind to R3 sub-phase performance | Add OTel spans following K0 observability patterns |
| 4 | module protocol | ReconciliationEngine uses async (asyncio) while rest of R3 is sync | no | Async/sync boundary creates complexity in phase wrapper (uses asyncio.run) | Evaluate if reconciliation should remain async or if sync with connection pool is simpler |
| 5 | feedback loop | Access tracker and regret detector write signals but P21 does not consume them | update (P21 ADR) | Learned lambdas and regret signals do not close the loop; system cannot self-tune | Wire P21 to consume st_feedback_signals and st_learned_weights |

---

## 12. Security & Privacy Audit

### 12.1 Data Classification

| # | Field / Column / Payload Key | Classification | Handling | Retention Policy | Notes |
| - | ---------------------------- | -------------- | -------- | ---------------- | ----- |
| 1 | event.content_text | PII | plain (in-memory only during cycle) | cycle duration | User-generated text; not persisted by R3, but passed through from st_hipp_events |
| 2 | event.embedding_768 | internal | plain | cycle duration | Derived from PII content; not independently re-identifiable |
| 3 | st_consolidation_audit.inputs_json | internal | plain | indefinite | Contains decay_factor, lambda values; no PII directly but linked to memory_id |
| 4 | st_consolidation_audit.explanation | internal | plain | indefinite | GDPR Article 22 automated decision explanation; no raw PII |
| 5 | st_consolidation_audit.memory_id | internal | plain | indefinite | Links to source entity; indirect PII reference |
| 6 | st_pruned_entities.embedding | internal | plain | 14-30 days | Embedding of pruned entity; derived from PII |
| 7 | st_learned_weights.value | internal | plain | indefinite | Learned parameters (bonus values, lambda); no PII |
| 8 | st_feedback_signals (PRUNE_REGRET) | internal | plain | indefinite | Entity ID + confidence; no raw PII |
| 9 | SimHash (64-bit) | internal | hashed | cycle duration (in-memory) | One-way hash of content; not reversible to original text |
| 10 | MinHash signature (128 uint64) | internal | hashed | cycle duration (in-memory) | One-way hash; not reversible |

### 12.2 Capability Boundaries

| # | Operation | Required Capability | Enforced? | Enforcement Location | Gap |
| - | --------- | ------------------- | --------- | -------------------- | --- |
| 1 | Write audit records to st_consolidation_audit | cap:consolidation:audit:write | no | N/A | No capability check; any code with DB access can write audit records |
| 2 | Read truth layer tables (st_epi, st_sem, etc.) | cap:truth:read | no | N/A | ReconciliationEngine reads any truth layer without capability token |
| 3 | Write to st_pruned_entities | cap:consolidation:prune:write | no | N/A | PrunedEntityTracker writes without authorization check |
| 4 | Write to st_learned_weights | cap:consolidation:learn:write | no | N/A | NoveltyBonusLearner and BayesianLambdaEstimator write without check |
| 5 | Delete from st_pruned_entities (cleanup) | cap:consolidation:prune:delete | no | N/A | PrunedEntitiesCleanup deletes without authorization |
| 6 | Execute TOMBSTONE decision | cap:consolidation:tombstone | no | N/A | RetentionEnforcer makes TOMBSTONE decisions without elevated capability |

### 12.3 Input Validation & Sanitization

| # | Input Source | Validation Applied | Sanitization Applied | Injection Risk | Notes |
| - | ----------- | ------------------ | -------------------- | -------------- | ----- |
| 1 | event.content_text (from st_hipp_events) | type check (str), non-empty check | none | low | Used for hashing only, not SQL interpolation |
| 2 | event.simhash_hex | type check (str), length check (16 hex chars) | none | none | Validated hex format before use |
| 3 | event.embedding_768 | type check (list/ndarray), dimension check (768) | none | none | Numeric data, no injection surface |
| 4 | TruthQueryService results | type check on returned rows | none | low | Parameterized queries prevent SQL injection; results from trusted DB |
| 5 | NoveltyFeedbackSignal | enum validation | none | none | Constrained to 5 known signal types |
| 6 | R3Config fields | dataclass type hints, threshold range validation in **post_init** | none | none | Internal config, not user-facing |

---

## 13. Enhancement Proposals

### 13.1 Proposed Epics

| Epic ID | Title | Scope Summary | Estimated Files | Priority | Dependencies | Issue Count |
| ------- | ----- | ------------- | --------------- | -------- | ------------ | ----------- |
| E-R3-01 | Per-Entity Learned Lambda | Wire BayesianLambdaEstimator output into decay engine for per-entity adaptive decay rates | 3 MOD | P1 | none | 4 |
| E-R3-02 | Reconciliation Engine Hardening | Add dedicated unit tests, contract YAML, and parallel truth queries | 2 NEW, 2 MOD | P1 | none | 5 |
| E-R3-03 | R3 Persistent Stores | Replace in-memory stores with DB-backed implementations | 4 NEW, 1 MOD | P1 | none | 4 |
| E-R3-04 | R3 Observability Layer | Add OpenTelemetry spans and Prometheus metrics export for all R3 sub-phases | 2 NEW, 13 MOD | P1 | none | 3 |
| E-R3-05 | Adaptive SimHash Thresholds | Content-type-aware hamming thresholds for paraphrase detection | 1 MOD, 1 MOD (test) | P2 | none | 3 |
| E-R3-06 | P21 Feedback Loop Wiring | Connect PRUNE_REGRET and learned weights to P21 for closed-loop tuning | 2 MOD, 1 NEW | P2 | E-R3-01 | 3 |
| E-R3-07 | R3 Contract Suite | Create v1 YAML contracts for reconciliation, retention, prune audit, and novelty | 4 NEW | P2 | none | 4 |

### 13.2 Epic Detail

---

#### Epic E-R3-01 -- Per-Entity Learned Lambda

**Summary**: Wire BayesianLambdaEstimator per-entity lambda into UnifiedDecayEngine for adaptive decay rates.

**Problem**: Decay engine uses fixed LAYER_LAMBDAS per table; high-access entities decay at the same rate as rarely-accessed ones.

**Solution**: Add lambda_override parameter to compute_decay; R3 orchestrator passes learned lambda (if available) from access_tracker before falling back to layer default.

##### Inputs

| # | Input | Type | Source | Validation |
| - | ----- | ---- | ------ | ---------- |
| 1 | entity_id | str | truth layer record | non-empty UUID |
| 2 | entity_table | str | truth layer record | one of 8 layer table names |
| 3 | learned_lambda | Optional[float] | st_learned_weights via BayesianLambdaEstimator | [0.0001, 0.1] if present |

##### Outputs

| # | Output | Type | Consumer | Guarantees |
| - | ------ | ---- | -------- | ---------- |
| 1 | decay_factor (with learned lambda) | float | RetentionEnforcer | [0.0, 1.0], uses learned lambda when confidence > 0.5, else layer default |

##### Algorithm Changes

| # | Algorithm | Change Type | Before | After | Rationale |
| - | --------- | ----------- | ------ | ----- | --------- |
| 1 | ExponentialDecay | modify | Uses LAYER_LAMBDAS[table] only | Accepts optional lambda_override; uses it when provided with confidence > threshold | Enables per-entity adaptive decay |
| 2 | BayesianLambdaEstimator | modify | Estimates lambda but does not feed into decay | Persists lambda to st_learned_weights; decay engine reads it | Closes the learning loop |

##### Test Plan

| # | Test File | Test Name | Type | What It Proves | Priority |
| - | --------- | --------- | ---- | -------------- | -------- |
| 1 | tests/k0/pipelines/p03/test_r3_decay_engine.py | test_learned_lambda_overrides_layer_default | unit | When learned lambda provided, decay uses it instead of LAYER_LAMBDAS | P0 |
| 2 | tests/k0/pipelines/p03/test_r3_decay_engine.py | test_learned_lambda_fallback_on_low_confidence | unit | When confidence below threshold, falls back to LAYER_LAMBDAS | P0 |
| 3 | tests/k0/pipelines/p03/test_r3_integration.py | test_end_to_end_learned_lambda | integration | Full cycle: access tracking -> lambda estimation -> decay computation | P1 |

##### Risks

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | Learned lambda oscillates due to sparse data | med | med | Enforce minimum observation count (5 accesses) and confidence threshold (0.5) before override |
| 2 | Lambda too low leads to premature pruning | low | high | Regret detection catches over-pruning; cap lambda at LAYER_LAMBDAS[table] * 2 |

##### Acceptance Criteria

- [ ] Given entity with 10+ accesses and confidence > 0.5, when decay runs, then learned lambda is used
- [ ] Given entity with < 5 accesses, when decay runs, then LAYER_LAMBDAS default is used
- [ ] Given learned lambda = 0.05 and layer default = 0.005, when decay runs, then decay_factor reflects learned lambda

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| E-R3-01.1 | Add lambda_override to compute_decay | Modify UnifiedDecayEngine.compute_decay signature and logic | S | none | Unit test with override passes |
| E-R3-01.2 | Wire lambda lookup in orchestrator | R3DedupDecay reads learned lambda before calling compute_decay | S | E-R3-01.1 | Integration test passes |
| E-R3-01.3 | Add confidence gate | Only use learned lambda when BayesianLambdaEstimator confidence > 0.5 | S | E-R3-01.1 | Fallback test passes |
| E-R3-01.4 | Integration tests | End-to-end test of access -> learn -> decay cycle | M | E-R3-01.2 | Full cycle test passes |

---

#### Epic E-R3-02 -- Reconciliation Engine Hardening

**Summary**: Add comprehensive unit tests, formal contract, and parallel truth queries for ReconciliationEngine.

**Problem**: ReconciliationEngine only tested through integration; no formal contract; sequential truth queries cause latency.

**Solution**: Create dedicated test suite, YAML contract, and use asyncio.gather for parallel layer queries.

##### Inputs

| # | Input | Type | Source | Validation |
| - | ----- | ---- | ------ | ---------- |
| 1 | event (P03EventState) | P03EventState | R3 envelope | embedding_768 not None for reconciliation |
| 2 | truth_service | TruthQueryService | R3DedupDecay lazy init | initialized with valid pool |

##### Outputs

| # | Output | Type | Consumer | Guarantees |
| - | ------ | ---- | -------- | ---------- |
| 1 | ReconciliationDecision | dataclass | R3 orchestrator, event state | action in {REINFORCE, EXTEND, EVOLVE, CONTRADICT, CREATE}, similarity in [0,1] |

##### Algorithm Changes

| # | Algorithm | Change Type | Before | After | Rationale |
| - | --------- | ----------- | ------ | ----- | --------- |
| 1 | TruthLayerQuery | modify | Sequential queries to 5 layers with 5s timeout each | asyncio.gather for parallel queries; combined 5s timeout | Reduces worst-case from 25s to 5s |

##### Test Plan

| # | Test File | Test Name | Type | What It Proves | Priority |
| - | --------- | --------- | ---- | -------------- | -------- |
| 1 | tests/k0/pipelines/p03/test_r3_reconciliation.py | test_reinforce_above_085 | unit | Similarity >= 0.85 returns REINFORCE | P0 |
| 2 | tests/k0/pipelines/p03/test_r3_reconciliation.py | test_extend_060_to_085 | unit | Similarity in [0.60, 0.85) returns EXTEND | P0 |
| 3 | tests/k0/pipelines/p03/test_r3_reconciliation.py | test_evolve_040_to_060 | unit | Similarity in [0.40, 0.60) returns EVOLVE | P0 |
| 4 | tests/k0/pipelines/p03/test_r3_reconciliation.py | test_contradict_below_040_with_match | unit | Similarity < 0.40 with existing match returns CONTRADICT | P0 |
| 5 | tests/k0/pipelines/p03/test_r3_reconciliation.py | test_create_no_match | unit | No candidates found returns CREATE | P0 |

##### Risks

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | Parallel queries increase DB connection pressure | med | med | Use connection pool with max_connections limit; degrade gracefully |

##### Acceptance Criteria

- [ ] Given all 5 reconciliation actions, when individual threshold tests run, then each action is correctly assigned
- [ ] Given 5 truth layers, when queries run in parallel, then total latency < 5s even if one layer is slow
- [ ] Contract YAML validates with schema linter and covers all inputs/outputs

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| E-R3-02.1 | Create reconciliation unit tests | New test_r3_reconciliation.py with per-action tests | M | none | 15+ tests covering all 5 actions and edge cases |
| E-R3-02.2 | Create reconciliation contract | consolidation.reconciliation.v1.yaml with full I/O schema | S | none | Contract passes YAML lint |
| E-R3-02.3 | Parallel truth layer queries | Use asyncio.gather in _find_candidates | S | none | p95 reduced from ~5s to ~1s per event |
| E-R3-02.4 | Truth query error handling tests | Test timeout, partial failure, empty results | M | E-R3-02.1 | All error paths return graceful defaults |
| E-R3-02.5 | Metrics for reconciliation | Export action counts and similarity histogram to metrics backend | S | E-R3-02.1 | Metrics visible in observability dashboard |

---

## 14. Risk Register

| # | Risk ID | Risk | Category | Likelihood | Impact | Risk Score | Mitigation | Owner | Status |
| - | ------- | ---- | -------- | ---------- | ------ | ---------- | ---------- | ----- | ------ |
| 1 | R-R3-001 | Mass tombstoning due to aggressive decay lambda | performance | med | high | high | Regret detection catches over-pruning; add max_tombstone_per_cycle safety limit | dev-lead | open |
| 2 | R-R3-002 | In-memory stores lose audit trail on crash | technical | high | high | high | Implement DB-backed stores (Epic E-R3-03) before production | dev-lead | open |
| 3 | R-R3-003 | Reconciliation timeout cascades block R3 phase | performance | med | med | medium | 5s per-layer timeout + overall 10s phase timeout with graceful degradation to CREATE | dev-lead | open |
| 4 | R-R3-004 | SimHash hamming threshold=3 misses paraphrased duplicates | technical | high | med | high | Adaptive thresholds per content_type (Epic E-R3-05) | dev-lead | open |
| 5 | R-R3-005 | O(n^2) pairwise dedup scales poorly beyond 500 events | performance | med | med | medium | MinHash LSH pre-filter (already implemented but not default); switch threshold to 100 events | dev-lead | open |
| 6 | R-R3-006 | No GDPR Article 22 compliance verification | security | low | high | medium | Add GDPR compliance test suite (test gap #8); verify explanation field covers all scenarios | dev-lead | open |
| 7 | R-R3-007 | Learned lambda oscillation destabilizes decay | technical | med | med | medium | Confidence gate (0.5 threshold) and clamping to [0.0001, 0.1] prevent wild swings | dev-lead | open |
| 8 | R-R3-008 | No capability enforcement for destructive operations (TOMBSTONE, DELETE) | security | low | high | medium | Add capability checks for TOMBSTONE decisions and pruned entity cleanup | dev-lead | open |

---

## 15. Open Questions

| # | Question | Context | Blocking? | Answer | Status | Answered By | Date |
| - | -------- | ------- | --------- | ------ | ------ | ----------- | ---- |
| 1 | Should learned lambda override or blend with layer default? | FG-R3-001: Override is simpler but riskier; blending (weighted average) is smoother | yes | | open | | |
| 2 | What is the max_tombstone_per_cycle safety limit? | R-R3-001: Need a hard cap to prevent mass data loss in a single cycle | yes | | open | | |
| 3 | Should R3 emit bus events or continue writing directly to DB? | Architecture gap #2: Bus events enable event-driven monitoring but add complexity | no | | open | | |
| 4 | Is 5s timeout per truth layer query sufficient for production? | ReconciliationEngine uses 5s; at scale with loaded DB, this may be too short or too long | no | | open | | |
| 5 | Should MinHash LSH be the default dedup strategy for all batch sizes? | Currently default is PAIRWISE for <10K; LSH is more consistent but slower for small batches | no | | open | | |
| 6 | What observation threshold should trigger learned lambda usage? | Currently BayesianLambdaEstimator needs min 5 accesses (4 intervals); is this too conservative? | no | | open | | |
| 7 | Should reconciliation integrate novelty_score as an additional signal? | Algorithm gap #10: High novelty biases toward CREATE; low novelty biases toward REINFORCE | no | | open | | |
| 8 | What is the target prune regret rate that triggers lambda re-tuning? | No threshold defined; need to establish acceptable regret rate (e.g., < 2% of pruned entities queried within 14 days) | no | | open | | |

---

## Appendix A: Glossary

| Term | Definition |
| ---- | ---------- |
| SimHash | 64-bit locality-sensitive hash using character n-grams and MD5; similar texts produce hashes with low hamming distance |
| MinHash LSH | MinHash Locality-Sensitive Hashing -- approximate set similarity using 128 hash functions organized in 32 bands of 4 rows |
| Hamming Distance | Number of bit positions where two binary strings differ; used to measure SimHash similarity |
| Jaccard Similarity | Ratio of set intersection to set union; approximated by MinHash for shingle sets |
| Cosine Similarity | Dot product of two vectors divided by product of their norms; used for embedding similarity |
| Decay Factor | Value in [0.0, 1.0] computed by exponential decay: exp(-lambda * days_since_last_observation) |
| Lambda (decay rate) | Rate parameter for exponential decay; higher lambda = faster decay. Layer defaults in LAYER_LAMBDAS |
| LAYER_LAMBDAS | Per-table default decay rates: st_hipp=0.100, st_prospective=0.020, st_procedural=0.010, st_kg_edges=0.008, st_epi=0.005, st_sem=0.003, st_social=0.002, st_kg_dom=0.001 |
| Bayesian Lambda | Per-entity learned decay rate estimated from access intervals using MLE: lambda = n / sum(intervals) |
| Retention Decision | Classification of entity as KEEP (active), ARCHIVE (low decay but valuable), or TOMBSTONE (marked for removal) |
| Resurrection | Restoration of a previously archived or tombstoned entity when new evidence increases its relevance |
| Immunity | Protection from decay/pruning based on entity type (FAMILY_MEMBER) or attribute (birthday, name, relationship, etc.) |
| IMMUNITY_ONTOLOGY | Two-level ontology: Level 1 is entity-level immunity (FAMILY_MEMBER); Level 2 is attribute-level per PERSON, PLACE, EVENT, ORG, CONCEPT |
| Novelty Score | Value in [0.0, 1.0] measuring how new/surprising an event is, computed with multiplicative bonuses for first occurrence, milestones, rare patterns, temporal significance |
| Prune Regret | Detection that a query matches a previously tombstoned entity, indicating the pruning was premature |
| Reconciliation Action | One of: REINFORCE (>=0.85 sim), EXTEND (>=0.60), EVOLVE (>=0.40), CONTRADICT (<0.40 with match), CREATE (<0.40 no match) |
| P03 | Pipeline 03: Memory Consolidation -- processes hippocampal events through R0-R9 phases into long-term memory |
| R3 | Phase R3: Dedup/Decay -- deduplication, decay computation, retention evaluation, and reconciliation within P03 |
| HNSW | Hierarchical Navigable Small World -- approximate nearest neighbor graph index used by pgvector for embedding search |
| TruthQueryService | Service that queries truth layer tables (st_epi, st_sem, st_procedural, st_social, st_prospective) for existing entities |
| GDPR Article 22 | EU regulation requiring explanation of automated decisions affecting individuals; R3 audit logger generates explanations |

## Appendix B: References

| # | Document | Path / URL | Relevance |
| - | -------- | ---------- | --------- |
| 1 | M5 Master Implementation Skeleton | docs/plans/MASTER_IMPLEMENTATION_SKELETON.md (R3 section, lines 5261-5700) | R3 skeleton claims, gap analysis, and algorithm inventory |
| 2 | P03 Consolidation Pipeline Contract | k0/contracts/pipelines/p03_consolidation.v1.yaml | Pipeline-level contract governing P03 phases |
| 3 | SimHash Deduplicator Contract | k0/contracts/modules/consolidation.simhash_deduplicator.v1.yaml | Only existing R3 algorithm contract (68 lines) |
| 4 | R3 Phase Wrapper | k0/pipelines/p03/phases/r3_dedup_decay.py | Main orchestrator (1309 lines) |
| 5 | R3 Integration Tests | tests/k0/pipelines/p03/test_r3_integration.py | Phase-level integration tests (861 lines, 36 tests) |
| 6 | Discovery Template | docs/pipelines/p03_enhancement_discovery/DISCOVERY_TEMPLATE.md | Template used for this document |
| 7 | R0 Discovery (reference) | docs/pipelines/p03_enhancement_discovery/P03_R0_BATCH_SELECTOR_DISCOVERY.md | Style reference for discovery format |
| 8 | ADR-K003 pgvector Migration | docs/architecture/decisions-K0/adr-k003-v2-pgvector-migration.md | FAISS elimination; all vector search uses pgvector HNSW |
| 9 | P03 Enhancement Discovery README | docs/pipelines/p03_enhancement_discovery/README.md | Discovery epic overview and phase index |
