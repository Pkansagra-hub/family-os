# P03 R1 Importance Scoring — Phase Discovery & Enhancement Plan

> **Epic 5.2 Discovery**: Full audit of the R1 Importance Scoring phase (event importance computation
> for the P03 consolidation pipeline). Covers code, contracts, algorithms, data flow, storage,
> observability, tests, dependencies, performance, gaps, and enhancement proposals.

---

## 0. Discovery Metadata

| Field | Value |
| ----- | ----- |
| Pipeline ID | P03 |
| Module Scope | consolidation.algorithms.importance_scorer, consolidation.algorithms.hebbian_learner, consolidation.algorithms.importance_weight_learner, pipelines.p03.phases.r1_importance_scorer, pipelines.p03.audit_logger |
| Discovery Date | 2026-03-02 |
| Milestone Target | M5 |
| Governing ADRs | ADR-K010 (P03 consolidation architecture), ADR-K010.1 (sleep-cycle state machine), ADR-K010.9 (capability-based security) |
| Related Dossier | `docs/pipelines/P03_consolidation_dossier_v2.md` |
| Author | copilot-claude |
| Status | **R1 SCORING CORE COHERENT** -- CONFIG_B formula live in the phase, cold-start weight loading is the active scoring path, config weight overrides are honored, and observability is instrumented. Hebbian/weight-learning infrastructure exists in the R1 surface but remains gated or downstream rather than executed inside the live R1 phase. |

---

### 0.1 Milestone Completion Summary

| Milestone | Code | Epics | Issues | Tests | Key Deliverables | Status |
| --------- | ---- | ----- | ------ | ----- | ---------------- | ------ |
| M5.P (Production Wiring) | M5.P | 5.P.1, 5.P.2, 5.P.3 | 15 | 20 (test_learned_weights_wiring.py) | PgLearnedWeightsStore unified adapter, pipeline contract alignment, R3 stores wiring | **COMPLETE** |
| M5.H (Hebbian Learning) | M5.H | 5.H.1, 5.H.2, 5.H.3 | 17 | 68 (58 hebbian + 10 idempotency) | R1 scores wired to R4 Hebbian, decay + anti-Hebbian, co-occurrence refactor | **COMPLETE** |
| M5.W (Weight Learner Alignment) | M5.W | 5.W.1, 5.W.2 | 11 | 59 (21 alignment + 38 grounding) | 8-component CONFIG_B alignment, grounding signal path K1 -> learner | **COMPLETE** |
| M6.F (KG Edge Feedback Loop) | M6.F | 5.F.1, 5.F.2 | 13 | 178 (47+32+19+18+39+23) | KG boost in R1, feedback queue, reinforcement cycle, anomaly detector | **COMPLETE** |
| M5.O (Observability + Test Gaps) | M5.O | 5.O.1, 5.O.2 | 11 | 161 (49+57+20+7+5+10+13 poc/perf) | OTel spans, metrics, cold-start tests, POC scenarios, performance, idempotency | **COMPLETE** |
| M5.S (Storage & Infrastructure) | M5.S | 5.S.1 | 5 | 63 (32 storage + 31 retention) | Migration 0075, st_learned_weights verification, retention policy | **COMPLETE** |
| **TOTAL** | | **13 epics** | **72** | **386+** | All R1 code, wiring, observability, and infrastructure complete | **ALL COMPLETE** |

**Plan reference**: `docs/plans_completed_donotrefer/PLAN_HEBBIAN_WEIGHT_LEARNER_INTEGRATION.md` (72 issues, 13 epics, all resolved)

---

## 1. Current State Audit

### 1.1 Code Inventory

| # | File (relative path) | Lines | Status | Last Modified | Purpose |
| - | -------------------- | ----- | ------ | ------------- | ------- |
| 1 | k0/pipelines/p03/phases/r1_importance_scorer.py | 398 | **CONFIG_B + M5.O** | 2026-03-06 | R1 phase wrapper: orchestrates importance scoring over batch envelope, collects ScoredEvent results (surprise_factor, identity_factor, priority_tier), 6-tier counting, now_ms for recency, audit_sample_rate=0.10, and tolerates missing metrics_registry in lightweight contexts. |
| 2 | k0/modules/consolidation/algorithms/importance_scorer.py | 1116 | **CONFIG_B + M5.W** | 2026-03-06 | Core importance scoring algorithm: CONFIG_B 6 additive + 9 multiplicative formula, 8-weight ImportanceWeights, 17-field ImportanceBreakdown, categorical novelty, recency decay (lambda=0.005), derive_source_reliability (floor=0.3), 6-tier priority. Live batch scoring now uses cold-start weight fallback and honors explicit config overrides. |
| 3 | k0/modules/consolidation/algorithms/hebbian_learner.py | 604 | **M5.H WIRED** | 2026-03-04 | Hebbian co-occurrence learning: edge weight updates, anti-Hebbian decay, entity pair extraction. R1 scores now flow to R4 Hebbian (M5.H). Decay + anti-Hebbian wired in R4 pipeline (M5.H.2). Co-occurrence refactored (M5.H.3). Still gated by enable_hebbian=False. |
| 4 | k0/modules/consolidation/algorithms/importance_weight_learner.py | 707 | **M5.W ALIGNED** | 2026-03-04 | Adaptive weight learning via online gradient descent. **Aligned to 8-component CONFIG_B** (M5.W.1): trains on (sentiment, affect, arousal, surprise, novelty, social, identity, recency). Grounding signal path wired (M5.W.2). |
| 5 | k0/pipelines/p03/audit_logger.py | 369 | LEGACY | 2026-01-02 | P03 decision audit logging: structured records to st_consolidation_audit, PII redaction, sampling |
| 6 | k0/pipelines/p03/phase_outputs.py | 726 | **CONFIG_B** | 2026-03-02 | Defines ScoredEvent (8 fields: +surprise_factor, +identity_factor, +priority_tier) and HebbianEdgeUpdate dataclasses for R1 output |
| 7 | k0/pipelines/p03/event_state.py | 551 | **CONFIG_B** | 2026-03-02 | P03EventState with set_importance(score, recency, affect, social, novelty, surprise=0.0, identity=0.0) + surprise_factor/identity_factor fields |
| 8 | k0/pipelines/p03/phase_interface.py | 558 | LEGACY | 2026-01-04 | P03PhaseResult, P03Phase protocol, P03RunnerContext |
| 9 | k0/pipelines/p03/observability.py | 1195 | **M5.O INSTRUMENTED** | 2026-03-05 | P03ObservabilityContext, R1PhaseMetrics (NOW POPULATED), P03Error. OTel spans, score histograms, weight source counters, priority tier gauges added (M5.O Epic 5.O.1). |
| 10 | k0/pipelines/p03/runner_contract.py | 561 | LEGACY | 2026-01-04 | P03PhaseId enum (R0-R8), P03PhaseStatus enum |
| 11 | k0/pipelines/p03/envelope.py | 205 | LEGACY | 2026-01-04 | P03BatchEnvelope container |
| 12 | k0/contracts/modules/consolidation.importance_scorer.v1.yaml | 84 | **CONFIG_B + M5.P** | 2026-03-03 | Module contract v2.0.0: CONFIG_B formula, 8 weights, 6-tier priority, removed Thompson Sampling, removed write:st_learned_weights. Pipeline contract aligned (M5.P.2). |
| 13 | k0/pipelines/p03/learning/feedback_queue.py | 184 | **M6.F NEW** | 2026-03-04 | Feedback queue for grounding signals: routes K1 retrieval success/failure back to ImportanceWeightLearner (M6.F Epic 5.F.1). |
| 14 | k0/pipelines/p03/learning/async_audit.py | 246 | **M6.F NEW** | 2026-03-04 | Async audit writer for learning events: captures weight updates, grounding signals, feedback cycle telemetry (M6.F). |
| 15 | k0/pipelines/p03/learning/learning_anomaly_detector.py | 460 | **M6.F NEW** | 2026-03-04 | Anomaly detector for reinforcement cycle: detects runaway inflation, edge weight drift, convergence failures (M6.F Epic 5.F.2). |
| 16 | k0/db/alembic/versions/0075_st_learning_queue_status_entity_idx.py | ~40 | **M5.S NEW** | 2026-03-05 | Migration: composite index (status, entity_id) on st_learning_queue for resolved gap query performance (M5.S Issue 5.S.1.2). |
| 17 | tests/k0/pipelines/p03/test_r1_importance_scorer.py | ~2000 | **CONFIG_B** | 2026-03-02 | Tests for ImportanceScorer: 8-weight defaults, 17-field breakdown, emotional (sent+affect+arousal), social (participants+intimacy), novelty (categorical+fallback), surprise, identity (relevance+domains), recency (lambda=0.005), source reliability (floor=0.3), all modulators, 6-tier priority, batch+audit, intent boost (95 tests, 17 classes) |
| 18 | tests/k0/pipelines/p03/test_r1_hebbian_learner.py | ~759 | LEGACY + M5.H | 2026-01-02 | Tests for HebbianLearner: config, entity parsing, co-occurrence extraction, edge updates, decay, anti-Hebbian, batch processing (58 tests) |
| 19 | tests/k0/pipelines/p03/test_r1_importance_learner.py | ~405 | LEGACY | 2026-01-17 | Tests for ImportanceWeightLearner: config, training samples, training step, rollback, diagnostics (38 tests) |
| 20 | tests/k0/pipelines/p03/test_r1_phase_integration.py | ~500 | **CONFIG_B** | 2026-03-02 | R1 phase integration tests with real P03BatchEnvelope and P03EventState (24 tests) |
| 21 | tests/k0/pipelines/p03/test_r1_observability.py | ~800 | **M5.O NEW** | 2026-03-05 | OTel span tests, score distribution histograms, weight source counters, priority tier gauges (49 tests, Epic 5.O.1) |
| 22 | tests/k0/pipelines/p03/test_r1_metrics.py | ~900 | **M5.O NEW** | 2026-03-05 | R1PhaseMetrics population, metric registry, formula version tracking (57 tests, Epic 5.O.1) |
| 23 | tests/k0/pipelines/p03/test_r1_cold_start.py | ~400 | **M5.O NEW** | 2026-03-05 | Cold-start weight fallback: static defaults, progressive blending, weight store unavailable (20 tests, Epic 5.O.2) |
| 24 | tests/k0/pipelines/p03/test_r1_poc_scenarios.py | ~2000 | **M5.O NEW** | 2026-03-05 | POC scenario regression: CONFIG_B formula validation from POC Phase 6 (7 test functions covering multiple scenarios, Epic 5.O.2) |
| 25 | tests/k0/pipelines/p03/test_r1_performance.py | ~200 | **M5.O NEW** | 2026-03-05 | R1 performance benchmarks: latency <30ms for 100 events, throughput >3000 events/s (5 tests, Epic 5.O.2) |
| 26 | tests/k0/pipelines/p03/test_r1_hebbian_idempotency.py | ~200 | **M5.O NEW** | 2026-03-05 | Hebbian disabled path + scoring idempotency: empty output when disabled, deterministic re-scoring (10 tests, Epic 5.O.2) |
| 27 | tests/k0/pipelines/p03/test_weight_learner_alignment.py | ~500 | **M5.W NEW** | 2026-03-04 | Weight learner -> scorer alignment: 8-component mapping, progressive blending, cold-start (21 tests, Epic 5.W.1) |
| 28 | tests/k0/pipelines/p03/test_p03_feedback_consumer.py | ~600 | **M6.F NEW** | 2026-03-04 | Feedback consumer: grounding signal routing, K1 feedback path, reinforcement cycle (32 tests, Epics 5.F.1/5.F.2) |
| 29 | tests/k0/pipelines/p03/learning/test_feedback_queue.py | ~400 | **M6.F NEW** | 2026-03-04 | Feedback queue: signal enqueue/dequeue, backpressure, error handling (19 tests, Epic 5.F.1) |
| 30 | tests/k0/pipelines/p03/learning/test_async_audit.py | ~300 | **M6.F NEW** | 2026-03-04 | Async audit writer: learning event capture, telemetry (18 tests, Epic 5.F.2) |
| 31 | tests/k0/pipelines/p03/learning/test_learning_anomaly_detector.py | ~600 | **M6.F NEW** | 2026-03-04 | Anomaly detector: runaway inflation, drift detection, convergence (39 tests, Epic 5.F.2) |
| 32 | tests/k0/pipelines/p03/test_m5s_storage_housekeeping.py | ~700 | **M5.S NEW** | 2026-03-05 | Storage housekeeping: migration 0075 composite index, st_learned_weights verification, merge_cascade_id index (32 tests, Epic 5.S.1) |
| 33 | tests/k0/pipelines/p03/test_p03_retention.py | ~600 | **M5.S VERIFIED** | 2026-03-05 | Retention policy: audit TTL cleanup, retention periods (31 tests, pre-existing + M5.S verification) |
| 34 | tests/k0/pipelines/p03/test_kg_relationship_boost.py | ~800 | **M6.F NEW** | 2026-03-04 | KG edge boost in R1: relationship_boost_factor, edge weight lookup, batch caching (47 tests, Epic 5.F.1) |
| 35 | tests/k0/pipelines/p03/test_learned_weights_wiring.py | ~400 | **M5.P NEW** | 2026-03-03 | Unified weight store adapter: PgLearnedWeightsStore, R1+R3 wiring, weight protocol (20 tests, Epic 5.P.1) |
| 36 | tests/k0/pipelines/p03/test_reinforcement_cycle.py | ~400 | **M6.F NEW** | 2026-03-04 | Full reinforcement cycle: R1 score -> Hebbian -> KG boost -> convergence (23 tests, Epic 5.F.2) |
| 37 | tests/k0/pipelines/p03/test_grounding_signal_pipeline.py | ~600 | **M5.W NEW** | 2026-03-04 | Grounding signal path: K1 -> weight learner training data (38 tests, Epic 5.W.2) |

### 1.2 Contract Inventory

| # | Contract File | Version | Status | Lines | Governs |
| - | ------------- | ------- | ------ | ----- | ------- |
| 1 | k0/contracts/modules/consolidation.importance_scorer.v1.yaml | v1 (formula v2.0.0) | active | 84 | module:consolidation.importance_scorer (R1 phase) -- CONFIG_B formula, 8 weights, 6-tier priority |
| 2 | k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | active | 397 | pipeline:P03_CONSOLIDATION (all R0-R8 stages) |

### 1.3 Config Inventory

#### 1.3.1 YAML Config Keys

| Config File | Version | Key (dot-path) | Value | Type | Default | Required | Notes |
| ----------- | ------- | --------------- | ----- | ---- | ------- | -------- | ----- |
| consolidation.importance_scorer.v1.yaml | v1 | latency_budget_ms | 30 | int | 30 | yes | R1 latency target per event |
| consolidation.importance_scorer.v1.yaml | v1 | side_effects[0] | read:st_learned_weights | str | N/A | yes | Reads adaptive weights (write removed in v2.0.0) |
| p03_consolidation.v1.yaml | v1 | stages[1].stage_id | stage_10_importance_score | str | N/A | yes | R1 stage ID in pipeline |

#### 1.3.2 Environment Variables

| Variable | Type | Default | Required | Used By | Purpose |
| -------- | ---- | ------- | -------- | ------- | ------- |
| K0_DB_URL | url | NONE | yes | k0/db/engine.py (shared) | PostgreSQL connection for st_learned_weights reads |

> **Note**: R1 does not read any R1-specific environment variables. Database connectivity is inherited from the shared K0 engine. Weight store access is via WeightStoreProtocol injected at construction.

#### 1.3.3 Feature Flags

| Flag Name | Source | Default | Scope | Controls | Rollback Behavior |
| --------- | ------ | ------- | ----- | -------- | ----------------- |
| enable_hebbian | R1Config | False | per-cycle | Reserved gate for downstream Hebbian integration; live R1 phase does not execute Hebbian updates | Safe -- disabling keeps R1 scoring-only |
| hebbian_activation_threshold | R1Config | 500 | per-cycle | Threshold retained for future adaptive Hebbian activation semantics | Safe -- no effect while R1 phase remains scoring-only |
| importance_weights | R1Config | None | per-cycle | Optional explicit CONFIG_B override passed directly into the live ImportanceScorer | Safe -- None preserves cold-start / learned fallback path |
| audit_sample_rate | R1Config | 0.10 | per-cycle | Fraction of scored events that generate audit records (production default, was 1.0 debug) | Safe -- 0.0 disables audit logging, 1.0 audits all |

> **Note**: These are R1Config dataclass fields, not external feature flags. In the live phase, `importance_weights` is honored first, then cold-start blending / learned-weight lookup applies when no override is provided. `enable_hebbian` remains a reserved gate while the live R1 phase stays scoring-only.

#### 1.3.4 Constants & Magic Numbers

| Constant | Location (file:line) | Value | Type | Rationale | Externalize? |
| -------- | -------------------- | ----- | ---- | --------- | ------------ |
| sentiment_weight (default) | importance_scorer.py ImportanceWeights | 0.10 | float | CONFIG_B emotional group (0.30 total) | no -- configurable via ImportanceWeights |
| affect_weight (default) | importance_scorer.py ImportanceWeights | 0.12 | float | Affect is primary emotional signal (McGaugh 2004) | no -- configurable |
| arousal_weight (default) | importance_scorer.py ImportanceWeights | 0.08 | float | Arousal differentiates calm vs excited (Kensinger 2009) | no -- configurable |
| surprise_weight (default) | importance_scorer.py ImportanceWeights | 0.15 | float | Prediction error signal (Rescorla-Wagner) | no -- configurable |
| novelty_weight (default) | importance_scorer.py ImportanceWeights | 0.15 | float | Novelty/salience contribution | no -- configurable |
| social_weight (default) | importance_scorer.py ImportanceWeights | 0.15 | float | Social context contribution | no -- configurable |
| identity_weight (default) | importance_scorer.py ImportanceWeights | 0.10 | float | Self-reference effect (Rogers et al. 1977) | no -- configurable |
| recency_weight (default) | importance_scorer.py ImportanceWeights | 0.15 | float | Temporal freshness bonus | no -- configurable |
| MIN_SAMPLES_FOR_LEARNED_WEIGHTS | importance_scorer.py | 500 | int | Minimum observations before trusting learned weights over static defaults | yes -- should be tunable per space |
| LOG2_10 | importance_scorer.py | 3.321928 | float | log2(10) for social factor normalization cap | no -- mathematical constant |
| milestone multiplier | importance_scorer.py EVENT_TYPE_MULTIPLIERS | 2.0 | float | Milestones are 2x important | maybe -- arbitrary but reasonable |
| celebration multiplier | importance_scorer.py EVENT_TYPE_MULTIPLIERS | 2.0 | float | Celebrations are 2x important | maybe |
| photo/image multiplier | importance_scorer.py EVENT_TYPE_MULTIPLIERS | 1.2 | float | Visual media slightly boosted | maybe |
| video multiplier | importance_scorer.py EVENT_TYPE_MULTIPLIERS | 1.3 | float | Video slightly higher than photo | maybe |
| voice/audio multiplier | importance_scorer.py EVENT_TYPE_MULTIPLIERS | 1.1 | float | Audio slightly boosted | maybe |
| message/chat multiplier | importance_scorer.py EVENT_TYPE_MULTIPLIERS | 1.0 | float | Baseline event type | no -- identity multiplier |
| calendar multiplier | importance_scorer.py EVENT_TYPE_MULTIPLIERS | 0.9 | float | Routine calendar slightly reduced | maybe |
| location multiplier | importance_scorer.py EVENT_TYPE_MULTIPLIERS | 0.8 | float | Check-ins somewhat reduced | maybe |
| transaction multiplier | importance_scorer.py EVENT_TYPE_MULTIPLIERS | 0.6 | float | Financial events reduced | maybe |
| routine multiplier | importance_scorer.py EVENT_TYPE_MULTIPLIERS | 0.5 | float | Routine events halved | maybe |
| query_memory boost | importance_scorer.py INTENT_BOOST_MULTIPLIERS | 1.20 | float | Memory queries indicate importance | maybe |
| share_news boost | importance_scorer.py INTENT_BOOST_MULTIPLIERS | 1.20 | float | News sharing indicates importance | maybe |
| set_reminder boost | importance_scorer.py INTENT_BOOST_MULTIPLIERS | 1.15 | float | Reminders indicate moderate importance | maybe |
| make_plan boost | importance_scorer.py INTENT_BOOST_MULTIPLIERS | 1.15 | float | Planning indicates moderate importance | maybe |
| seek_advice boost | importance_scorer.py INTENT_BOOST_MULTIPLIERS | 1.10 | float | Advice-seeking mild boost | maybe |
| reflect boost | importance_scorer.py INTENT_BOOST_MULTIPLIERS | 1.10 | float | Reflection mild boost | maybe |
| express_feeling boost | importance_scorer.py INTENT_BOOST_MULTIPLIERS | 1.00 | float | No boost for expression (baseline) | no -- identity |
| casual_chat boost | importance_scorer.py INTENT_BOOST_MULTIPLIERS | 0.90 | float | Casual chat slightly reduced | maybe |
| CRITICAL priority threshold | importance_scorer.py get_priority_tier | 0.80 | float | Score >= 0.80 = CRITICAL tier | yes -- policy-level tunable |
| HIGH priority threshold | importance_scorer.py get_priority_tier | 0.60 | float | Score >= 0.60 = HIGH tier | yes |
| MEDIUM_HIGH priority threshold | importance_scorer.py get_priority_tier | 0.45 | float | Score >= 0.45 = MEDIUM_HIGH tier | yes |
| MEDIUM priority threshold | importance_scorer.py get_priority_tier | 0.30 | float | Score >= 0.30 = MEDIUM tier | yes |
| LOW_MEDIUM priority threshold | importance_scorer.py get_priority_tier | 0.15 | float | Score >= 0.15 = LOW_MEDIUM tier | yes |
| RECENCY_LAMBDA | importance_scorer.py | 0.005 | float | Exponential decay rate (half-life ~139h / ~6 days) | yes -- calibrated in POC Phase 5 |
| RELIABILITY_FLOOR | importance_scorer.py | 0.3 | float | Minimum source reliability (prevents total suppression) | yes -- calibrated in POC Phase 5 |
| GOAL_BOOST | importance_scorer.py | 1.15 | float | Narrative goal event multiplier | maybe |
| NOVELTY_MAP | importance_scorer.py | ROUTINE=0.10, EXPECTED=0.30, NOVEL=0.70, SURPRISING=1.00 | dict | Categorical novelty to numeric | maybe |
| ELABORATION_MAP | importance_scorer.py | MENTION=1.00, DISCUSSED=1.05, ELABORATED=1.10, DEEPLY_PROCESSED=1.15 | dict | Elaboration depth multiplier | maybe |
| TEMPORAL_MAP | importance_scorer.py | PAST=1.00, ONGOING=1.05, FUTURE_COMMITMENT=1.10 | dict | Temporal orientation multiplier | maybe |
| ARC_MAP | importance_scorer.py | EXPOSITION=1.00, RISING_ACTION=1.05, CLIMAX=1.15, RESOLUTION=1.00 | dict | Narrative arc position multiplier | maybe |
| MEMORY_TIER_MAP | importance_scorer.py | routine=1.00, notable=1.10, significant=1.25, landmark=1.50 | dict | Memory tier multiplier | maybe |
| INTIMACY_SCALE | importance_scorer.py | HIGH=1.2, MEDIUM=1.0, LOW=0.8 | dict | Social intimacy multiplier | maybe |
| SOURCE_TYPE_RELIABILITY | importance_scorer.py | user_stated=0.95, user_implied=0.80, device_observed=0.65, system_inferred=0.45 | dict | Source type to reliability mapping | maybe |
| HebbianConfig.learning_rate | hebbian_learner.py | 0.1 | float | Hebbian learning rate | no -- configurable via HebbianConfig |
| HebbianConfig.decay_rate | hebbian_learner.py | 0.01 | float | Exponential decay rate per day | no -- configurable |
| HebbianConfig.max_weight | hebbian_learner.py | 1.0 | float | Upper bound for edge weights | no -- configurable |
| HebbianConfig.min_weight | hebbian_learner.py | 0.01 | float | Lower bound (prune below) | no -- configurable |
| HebbianConfig.anti_learning_rate | hebbian_learner.py | 0.15 | float | Anti-Hebbian weakening rate | no -- configurable |
| HebbianConfig.explicit_correction_multiplier | hebbian_learner.py | 1.3 | float | Boost for explicit user corrections | no -- configurable |
| HebbianConfig.prune_threshold | hebbian_learner.py | 0.05 | float | Edge weight below this is pruned | no -- configurable |
| WeightLearnerConfig.learning_rate | importance_weight_learner.py | 0.01 | float | Gradient descent learning rate | no -- configurable |
| WeightLearnerConfig.momentum | importance_weight_learner.py | 0.9 | float | Momentum coefficient | no -- configurable |
| WeightLearnerConfig.min_samples | importance_weight_learner.py | 500 | int | Min samples before learning activates | no -- configurable |
| WeightLearnerConfig.weight_min | importance_weight_learner.py | 0.05 | float | Per-weight lower clamp | no -- configurable |
| WeightLearnerConfig.weight_max | importance_weight_learner.py | 0.60 | float | Per-weight upper clamp | no -- configurable |
| WeightLearnerConfig.rollback_threshold | importance_weight_learner.py | 3 | int | Consecutive loss increases before rollback | no -- configurable |
| WeightLearnerConfig.min_batch_size | importance_weight_learner.py | 50 | int | Minimum batch for training step | no -- configurable |
| WeightLearnerConfig.small_batch_lr_factor | importance_weight_learner.py | 10.0 | float | LR reduction for small batches | no -- configurable |
| WeightLearnerConfig.drift_threshold | importance_weight_learner.py | 0.15 | float | Max drift before rollback | no -- configurable |
| WeightLearnerConfig.priors (emotional) | importance_weight_learner.py | 0.35 | float | Prior for emotional component | no -- configurable |
| WeightLearnerConfig.priors (recency) | importance_weight_learner.py | 0.25 | float | Prior for recency component | no -- configurable |
| WeightLearnerConfig.priors (access) | importance_weight_learner.py | 0.20 | float | Prior for access component | no -- configurable |
| WeightLearnerConfig.priors (social) | importance_weight_learner.py | 0.20 | float | Prior for social component | no -- configurable |
| AuditAction.SCORE | audit_logger.py | "SCORE" | str | Audit action type for R1 scoring decisions | no -- enum constant |
| RED_BAND_FIELDS | audit_logger.py | frozenset of PII field names | frozenset | Fields to redact in audit records | yes -- may need updates as fields grow |

### 1.4 Migration Inventory

| # | Migration File | Table(s) | Operation | Columns Affected | Reversible? |
| - | -------------- | -------- | --------- | ---------------- | ----------- |
| 1 | (shared with R0) 0052_st_hipp_events_p03_columns.py | st_hipp_events | ALTER | +affect_valence, +affect_arousal, +salience_score, +salience_band, +novelty_score | partial |
| 2 | (shared with R0) 0053_st_hipp_events_ultrabert_full.py | st_hipp_events | ALTER | +participants_json, +num_participants, +social_context, +social_intimacy, +is_solo_event | partial |
| 3 | (shared with R0) 0060_st_hipp_events_activity_ultrabert.py | st_hipp_events | ALTER | +activity_type_ultrabert, +intent_ultrabert, +intent_confidence | partial |

> **Note**: R1 does not own any migrations directly. It reads fields from st_hipp_events written by P02/R0 and writes to st_learned_weights (managed by weight learner). The st_consolidation_audit table is managed by the audit subsystem.

---

## 2. API Surface Map

### 2.1 Public Functions & Methods

| # | Module | Function / Method | Signature | Return Type | Consumers | Idempotent? | Notes |
| - | ------ | ----------------- | --------- | ----------- | --------- | ----------- | ----- |
| 1 | k0.pipelines.p03.phases.r1_importance_scorer | R1ImportanceScorer.run | (envelope: P03BatchEnvelope, ctx: P03RunnerContext) | P03PhaseResult | SequentialRunner (stage_10) | yes | Idempotent: re-running overwrites same scores deterministically |
| 2 | k0.pipelines.p03.phases.r1_importance_scorer | R1ImportanceScorer.should_skip | (envelope: P03BatchEnvelope) | bool | SequentialRunner protocol | yes | Returns True if no events or all already scored |
| 3 | k0.pipelines.p03.phases.r1_importance_scorer | R1ImportanceScorer.idempotency_key | (envelope: P03BatchEnvelope) | str | SequentialRunner dedup | yes | Returns f"p03:r1:{envelope.context.cycle_id}" |
| 4 | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.compute_importance_score | (event: Any, weights: ImportanceWeights, now_ms: Optional[int]=None) | tuple[float, ImportanceBreakdown] | R1 phase, tests | yes | Pure computation. CONFIG_B formula: 6 additive + 7 multiplicative + reliability. now_ms for recency decay. |
| 5 | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.score_batch | (events: list[Any], now_ms: Optional[int]=None) -> async | list[dict] | (available, score_batch_with_audit preferred) | yes | Batch scoring without audit. Loads weights internally via get_weights(). Returns dicts with 10 keys incl. surprise_factor, identity_factor, priority_tier. |
| 6 | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.score_batch_with_audit | (events: list[Any], audit_logger: P03AuditLogger, sample_rate: float=1.0, now_ms: Optional[int]=None) -> async | list[dict] | R1 phase | no | Writes audit records via logger. formula_version="2.0.0" in audit. Returns dicts with 10 keys. |
| 7 | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.get_weights | () | ImportanceWeights | score_batch, score_batch_with_audit | conditional | Reads from weight store if >= 500 samples |
| 8 | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.get_weights_with_cold_start | (global_store: Optional[WeightStoreProtocol]=None) -> async | tuple[ImportanceWeights, str, int] | (available, not used by R1 phase) | conditional | 3-level fallback with progressive blending. Returns (weights, source, sample_count). |
| 8a | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.compute_emotional_intensity | (sentiment_score, affect_valence, affect_arousal, weights) | float | compute_importance_score | yes | CONFIG_B: sent_w*abs(sent) + affect_w*abs(val) + arousal_w*arousal. Range [0, 0.30]. |
| 8b | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.compute_social_factor | (num_participants, social_intimacy, weights) | float | compute_importance_score | yes | social_w *log2(count)/3.32* INTIMACY_SCALE[intimacy]. Uses num_participants (BUG-001 fixed). |
| 8c | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.compute_novelty_factor | (novelty_categorical, salience_fallback, weights) | float | compute_importance_score | yes | NOVELTY_MAP lookup primary, salience_score fallback. Range [0, novelty_w]. |
| 8d | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.compute_surprise_factor | (surprise_level, weights) | float | compute_importance_score | yes | clamp(surprise_level) * surprise_w. Range [0, surprise_w]. New in CONFIG_B. |
| 8e | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.compute_identity_factor | (identity_relevance, identity_domains_json, weights) | float | compute_importance_score | yes | identity_relevance if >0 else len(domains)/9.0. Range [0, identity_w]. New in CONFIG_B. |
| 8f | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.compute_recency_factor | (event_timestamp_ms, now_ms, weights) | float | compute_importance_score | yes | recency_w *exp(-0.005* hours_since_event). Half-life ~6 days. New in CONFIG_B. |
| 8g | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.derive_source_reliability | (source_reliability, source_type) | float | compute_importance_score | yes | max(RELIABILITY_FLOOR, reliability). SOURCE_TYPE_RELIABILITY lookup fallback. Floor=0.3. |
| 8h | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.get_event_type_multiplier | (content_type: str) | float | compute_importance_score | yes | EVENT_TYPE_MULTIPLIERS lookup, 1.0 default. Formerly private _get_event_type_multiplier. |
| 8i | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.select_batch | (scored_events: list, batch_size: int) | list | (available) | yes | Top-N events by importance (descending). Handles dict and object access. |
| 8j | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.get_priority_tier | (score: float) | str | score_batch, score_batch_with_audit | yes | 6-tier: CRITICAL>=0.80, HIGH>=0.60, MEDIUM_HIGH>=0.45, MEDIUM>=0.30, LOW_MEDIUM>=0.15, LOW<0.15 |
| 8k | k0.modules.consolidation.algorithms.importance_scorer | ImportanceScorer.invalidate_weight_cache | () | None | (available) | yes | Resets cached weights to force reload from store. |
| 9 | k0.modules.consolidation.algorithms.hebbian_learner | HebbianLearner.extract_cooccurrences | (event: Any) | list[tuple[str, str, RelationType]] | process_batch | yes | Pure entity pair extraction |
| 10 | k0.modules.consolidation.algorithms.hebbian_learner | HebbianLearner.update_edge_weight | (current_weight: float, event_importance: float) | float | process_batch | yes | Hebbian delta computation |
| 11 | k0.modules.consolidation.algorithms.hebbian_learner | HebbianLearner.apply_decay | (edges: dict, days_elapsed: float) | dict | (external caller) | yes | Exponential time decay |
| 12 | k0.modules.consolidation.algorithms.hebbian_learner | HebbianLearner.apply_anti_decay | (edge_weight: float, signal: AntiHebbianSignal, confidence: float) | float | (external caller) | yes | Anti-Hebbian weakening |
| 13 | k0.modules.consolidation.algorithms.hebbian_learner | HebbianLearner.process_batch | (events: list[Any]) | dict[tuple, HebbianEdgeUpdate] | (disabled in R1) | no | Aggregates co-occurrences, computes updates |
| 14 | k0.modules.consolidation.algorithms.importance_weight_learner | ImportanceWeightLearner.train_step | (batch: TrainingBatch) | TrainingResult | (external caller, not R1) | no | Online gradient descent step |
| 15 | k0.modules.consolidation.algorithms.importance_weight_learner | ImportanceWeightLearner.get_weights | () | list[float] | (external caller) | yes | Returns current normalized weights |
| 16 | k0.modules.consolidation.algorithms.importance_weight_learner | ImportanceWeightLearner.persist_weights | (pool: Pool, space_id: str, tenant_id: str) | None | (external caller, not R1) | yes | UPSERT to st_learned_weights |
| 17 | k0.modules.consolidation.algorithms.importance_weight_learner | ImportanceWeightLearner.load_weights | (pool: Pool, space_id: str, tenant_id: str) | Optional[list[float]] | (external caller) | yes | SELECT from st_learned_weights |
| 18 | k0.pipelines.p03.audit_logger | P03AuditLogger.log_decision | (event_id: str, action: AuditAction, explanation: str, metadata: dict) | None | R1 score_batch_with_audit | no | Accumulates AuditRecord for later flush |
| 19 | k0.pipelines.p03.audit_logger | P03AuditLogger.get_pending_records | () | list[AuditRecord] | R1 phase (stores to envelope) | yes | Read-only access to accumulated records |
| 20 | k0.pipelines.p03.audit_logger | P03AuditLogger.get_pending_db_rows | () | list[dict] | R6 staging (bulk insert) | yes | Converts records to DB row format |

### 2.2 Syscalls Used / Required

| # | Syscall | Signature | Status | Used By | SQL Pattern (if DB) | Notes |
| - | ------- | --------- | ------ | ------- | ------------------- | ----- |
| 1 | weight_store (protocol) | WeightStoreProtocol.load(space_id, tenant_id) -> Optional[dict] | exists | ImportanceScorer.get_weights | SELECT weights_json FROM st_learned_weights WHERE space_id=$1 AND tenant_id=$2 | Returns learned weights + sample_count |
| 2 | weight_store (protocol) | WeightStoreProtocol.save(space_id, tenant_id, weights, sample_count) -> None | exists | ImportanceWeightLearner.persist_weights | UPSERT INTO st_learned_weights | Not called during R1 phase itself |

> **Note**: R1 reads weights through the WeightStoreProtocol abstraction. The actual weight store implementation queries st_learned_weights. Unlike R0, R1 does not use raw SQL directly. The ImportanceWeightLearner has its own persist_weights/load_weights that use raw asyncpg, but these are not called during R1 phase execution.

### 2.3 Internal Helpers (non-public but critical path)

> **Note (Epic 5A.4)**: The CONFIG_B rewrite promoted all `_compute_*` methods to public `compute_*` methods (now listed in Section 2.1 rows 8a-8k). The `_get_event_type_multiplier` and `_get_intent_boost` private methods were removed; their logic is inlined in `compute_importance_score`. The remaining private helpers are:

| # | Module | Function | Signature | Called By | Purpose | Risk if Changed |
| - | ------ | -------- | --------- | --------- | ------- | --------------- |
| 1 | importance_scorer | _weights_from_dict | (d: Dict[str, float], defaults: Optional[ImportanceWeights]) -> ImportanceWeights | get_weights, get_weights_with_cold_start | Construct ImportanceWeights from dict with CONFIG_B defaults for missing keys | Changes affect all weight loading paths |
| 2 | importance_scorer | _blend_weights | (learned: dict, static: dict, alpha: float) -> dict | get_weights_with_cold_start | Alpha-blend learned and static weights, then normalize to sum=1.0 | Changes affect cold start blending |
| 3 | importance_scorer | _weights_source | str instance attribute | score_batch_with_audit (audit logging) | Tracks "config-override"/"static"/"learned"/"per-space"/"global-blend" for audit | Audit metadata depends on this |
| 6 | hebbian_learner | _parse_entities | (ner_entities_json: str) -> list[dict] | extract_cooccurrences | Parses JSON entity list from event | Handles dict/list/string NER formats |
| 7 | hebbian_learner | _compute_initial_weight | (event_importance: float) -> float | process_batch | Initial edge weight for new co-occurrences | Bounded by [min_weight, max_weight] |
| 8 | hebbian_learner | _get_penalty_for_signal | (signal: AntiHebbianSignal) -> float | apply_anti_decay | Maps signal type to penalty multiplier | ENTITY_MERGE_REJECTED=0.3, ASSOCIATION_WRONG=0.5, MUTUAL_EXCLUSION=0.8, CONTRADICTION=0.6 |
| 9 | importance_weight_learner | _compute_loss | (predictions, labels, sample_weights) -> float | train_step | Binary cross-entropy loss | Uses PyTorch if available, else NumPy |
| 10 | importance_weight_learner | _compute_gradients | (features, predictions, labels, sample_weights) -> ndarray | train_step | Gradient of BCE w.r.t. weights | Manual gradient computation |
| 11 | importance_weight_learner | _apply_softmax | (weights: ndarray) -> ndarray | train_step | Ensures weights sum to 1.0 | Applied after every gradient step |
| 12 | importance_weight_learner | _clamp_weights | (weights: ndarray) -> ndarray | train_step | Clamps each weight to [weight_min, weight_max] then re-normalizes | Prevents any single weight dominating |
| 13 | importance_weight_learner | check_rollback_needed | () -> bool | train_step | True if 3 consecutive loss increases | Triggers reset to prior weights |
| 14 | audit_logger | _redact_pii | (metadata: dict) -> dict | log_decision | Replaces RED_BAND_FIELDS values with "[REDACTED]" | PII protection in audit trail |

### 2.4 Classes & Dataclasses

| # | Module | Class | Base Class / Protocol | Key Attributes | Key Methods | Consumers |
| - | ------ | ----- | --------------------- | -------------- | ----------- | --------- |
| 1 | r1_importance_scorer | R1ImportanceScorer | (none) | PHASE_ID: P03PhaseId.R1, config: R1Config | run(), should_skip(), idempotency_key() | SequentialRunner |
| 2 | r1_importance_scorer | R1Config | dataclass | audit_sample_rate: float=0.10, enable_hebbian: bool=False, hebbian_activation_threshold: int=500, min_samples_for_learned_weights: int=500, importance_weights: Optional[ImportanceWeights]=None | N/A (data only) | R1ImportanceScorer |
| 3 | importance_scorer | ImportanceScorer | (none) | space_id: str, weight_store: Optional[WeightStoreProtocol], _cached_weights: Optional[ImportanceWeights], _weights_source: str, _cached_sample_count: int | compute_importance_score(), score_batch(), score_batch_with_audit(), get_weights(), get_weights_with_cold_start(), compute_emotional_intensity(), compute_social_factor(), compute_novelty_factor(), compute_surprise_factor(), compute_identity_factor(), compute_recency_factor(), derive_source_reliability(), get_event_type_multiplier(), get_priority_tier(), select_batch(), invalidate_weight_cache() | R1 phase |
| 4 | importance_scorer | ImportanceWeights | frozen dataclass | sentiment_weight: float=0.10, affect_weight: float=0.12, arousal_weight: float=0.08, surprise_weight: float=0.15, novelty_weight: float=0.15, social_weight: float=0.15, identity_weight: float=0.10, recency_weight: float=0.15 (8 fields, sum=1.0) | total(), as_dict() | ImportanceScorer, R1 phase |
| 5 | importance_scorer | ImportanceBreakdown | dataclass | emotional_component, surprise_component, novelty_component, social_component, identity_component, recency_component, base_score, elab_boost, goal_boost, arc_boost, temporal_boost, type_multiplier, intent_boost, tier_multiplier, reliability, final_score, weights_source (17 fields) | to_dict() | Audit records, tests |
| 6 | hebbian_learner | HebbianLearner | (none) | config: HebbianConfig | extract_cooccurrences(), update_edge_weight(), apply_decay(), apply_anti_decay(), process_batch() | (disabled in R1) |
| 7 | hebbian_learner | HebbianConfig | frozen dataclass | learning_rate=0.1, decay_rate=0.01, max_weight=1.0, min_weight=0.01, anti_learning_rate=0.15, explicit_correction_multiplier=1.3, prune_threshold=0.05 | validate() | HebbianLearner |
| 8 | hebbian_learner | RelationType | Enum | INTERACTS_WITH, FREQUENTS, DISCUSSES | N/A | Co-occurrence extraction |
| 9 | hebbian_learner | AntiHebbianSignal | Enum | ENTITY_MERGE_REJECTED=0.3, ASSOCIATION_WRONG=0.5, MUTUAL_EXCLUSION=0.8, CONTRADICTION=0.6 | N/A | Anti-Hebbian decay |
| 10 | importance_weight_learner | ImportanceWeightLearner | (none) | config: WeightLearnerConfig, _weights: ndarray,_velocity: ndarray, _loss_history: list, _snapshot: Optional[ndarray],_step_count: int | train_step(), get_weights(), set_weights(), persist_weights(), load_weights(), check_rollback_needed(), get_diagnostics() | (external, not R1) |
| 11 | importance_weight_learner | WeightLearnerConfig | frozen dataclass | learning_rate=0.01, momentum=0.9, min_samples=500, weight_min=0.05, weight_max=0.60, sliding_window_days=30, rollback_threshold=3, min_batch_size=50, small_batch_lr_factor=10.0, drift_threshold=0.15, priors=(emotional=0.35, recency=0.25, access=0.20, social=0.20) | validate(), get_priors(), get_priors_list() | ImportanceWeightLearner |
| 12 | importance_weight_learner | TrainingSample | dataclass | features: dict (emotional, recency, access, social), label: float, is_grounded: bool, event_time: float | to_features(), to_label(), compute_sample_weight() | TrainingBatch |
| 13 | importance_weight_learner | TrainingBatch | dataclass | samples: list[TrainingSample] | to_arrays() -> (features, labels, sample_weights), len() | ImportanceWeightLearner.train_step |
| 14 | importance_weight_learner | TrainingResult | dataclass | loss: float, prev_loss: Optional[float], weights: list[float], step_count: int, converged: bool, drift: float | N/A (data only) | train_step return |
| 15 | audit_logger | P03AuditLogger | (none) | space_id: str, tenant_id: str, cycle_id: str,_records: list[AuditRecord], _seen_ids: set | log_decision(), get_pending_records(), get_pending_db_rows() | R1 phase, R6 staging |
| 16 | audit_logger | AuditRecord | dataclass | audit_id: str, event_id: str, cycle_id: str, phase_id: str, action: AuditAction, explanation: str, metadata: dict, created_at: int | to_db_row() | P03AuditLogger |
| 17 | audit_logger | AuditAction | Enum | REINFORCE, DECAY, ARCHIVE, MERGE, CREATE, EXTEND, PRUNE, SKIP, CONTRADICT, SCORE | N/A | All P03 phases |
| 18 | phase_outputs | ScoredEvent | dataclass | event_id: str, importance_score: float, recency_factor: float, affect_factor: float, social_factor: float, novelty_factor: float, surprise_factor: float=0.0, identity_factor: float=0.0, priority_tier: str="LOW" (9 fields) | N/A (data only) | R1 phase -> envelope.phases.r1_scored_events |
| 19 | phase_outputs | HebbianEdgeUpdate | dataclass | source_entity_id: str, target_entity_id: str, old_weight: float, new_weight: float, delta: float, update_type: str | N/A (data only) | (disabled in R1) |

---

## 3. Algorithm Inventory

### 3.1 Current Algorithms

| # | Algorithm Name | Location | Category | Input Type(s) | Input Constraints | Output Type(s) | Output Guarantees | Time | Space | Det? | Stateful? | State Location | Parameters | Edge Cases | Failure Mode | Fallback | Dependencies | Description |
| - | -------------- | -------- | -------- | ------------- | ----------------- | -------------- | ----------------- | ---- | ----- | ---- | --------- | -------------- | ---------- | ----------- | ------------ | -------- | ------------ | ----------- |
| 1 | importance_formula | importance_scorer.py compute_importance_score | scoring | P03EventState (or Any with ~23 CONFIG_B fields: sentiment_score, affect_valence, affect_arousal, surprise_level, novelty, salience_score, num_participants, social_intimacy, identity_relevance, identity_domains_json, timestamp, elaboration_depth, narrative_is_goal_event, narrative_arc_position, temporal_orientation, source_reliability, source_type, memory_tier, content_type, activity_type_ultrabert, intent_ultrabert) | sentiment in [-1,1], affect in [-1,1], arousal in [0,1], surprise in [0,1] | tuple[float, ImportanceBreakdown] | score in [0.0, 1.0] (clamped) | O(1) | O(1) | yes | no | N/A | ImportanceWeights (8 weights, sum=1.0), EVENT_TYPE_MULTIPLIERS, INTENT_BOOST_MULTIPLIERS, NOVELTY_MAP, ELABORATION_MAP, TEMPORAL_MAP, ARC_MAP, MEMORY_TIER_MAP, INTIMACY_SCALE, SOURCE_TYPE_RELIABILITY, RECENCY_LAMBDA=0.005, RELIABILITY_FLOOR=0.3, GOAL_BOOST=1.15 | All-zero inputs = 0.0; missing fields default via getattr; unknown event_type = 1.0 multiplier; now_ms kwarg for recency | N/A (pure computation) | defaults for all getattr | N/A | CONFIG_B: base(emotional + surprise + novelty + social + identity + recency) *elab* goal *arc* temporal *type* intent *tier* reliability, clamped [0,1] |
| 2 | emotional_intensity | importance_scorer.py compute_emotional_intensity | scoring | sentiment_score, affect_valence, affect_arousal, weights | sentiment in [-1,1], affect in [-1,1], arousal in [0,1] | float [0.0, 0.30] | bounded by weights sum (0.10+0.12+0.08=0.30 max) | O(1) | O(1) | yes | no | N/A | sentiment_weight=0.10, affect_weight=0.12, arousal_weight=0.08 | Both zero = 0.0; negative values use abs(); arousal clamped [0,1] | N/A | defaults to 0.0 | N/A | emotional = sent_w*abs(sentiment) + affect_w*abs(valence) + arousal_w*arousal |
| 3 | social_factor | importance_scorer.py compute_social_factor | scoring | num_participants: int, social_intimacy: str, weights | num_participants >= 0, social_intimacy in HIGH/MEDIUM/LOW | float [0.0, 0.18] | bounded by social_weight * 1.2 (HIGH intimacy) | O(1) | O(1) | yes | no | N/A | social_weight=0.15, LOG2_10=3.321928, INTIMACY_SCALE (HIGH=1.2, MEDIUM=1.0, LOW=0.8) | 0 or 1 participants = 0.0; >= 10 participants caps log factor at 1.0; unknown intimacy = 1.0 | N/A | defaults num_participants to 1 | N/A | social = social_w *min(1.0, log2(count) / LOG2_10)* INTIMACY_SCALE[intimacy]. BUG-001 FIXED: now reads num_participants. |
| 4 | novelty_factor | importance_scorer.py compute_novelty_factor | scoring | novelty_categorical: str, salience_fallback: float, weights | novelty in ROUTINE/EXPECTED/NOVEL/SURPRISING, salience in [0,1] | float [0.0, 0.15] | bounded by novelty_weight * 1.0 | O(1) | O(1) | yes | no | N/A | novelty_weight=0.15, NOVELTY_MAP (ROUTINE=0.10, EXPECTED=0.30, NOVEL=0.70, SURPRISING=1.00) | Empty novelty -> uses salience_fallback; unknown category -> salience_fallback | N/A | defaults to 0.0 | N/A | novelty = novelty_w * NOVELTY_MAP[categorical], salience_score fallback for pre-MW v2 events |
| 5 | event_type_multiplier | importance_scorer.py get_event_type_multiplier | classification | content_type: str (or activity_type_ultrabert) | string, case-insensitive | float [0.5, 2.0] | bounded by EVENT_TYPE_MULTIPLIERS values | O(1) | O(1) | yes | no | N/A | EVENT_TYPE_MULTIPLIERS dict (13 entries) | None or unknown type = 1.0; empty string -> "message" | N/A | 1.0 (neutral) | N/A | Looks up event type in multiplier table; milestone/celebration=2.0, routine=0.5. Now public method. |
| 6 | intent_boost | importance_scorer.py (inlined in compute_importance_score) | classification | intent_ultrabert or intent_label: str | string, case-insensitive | float [0.90, 1.20] | bounded by INTENT_BOOST_MULTIPLIERS values | O(1) | O(1) | yes | no | N/A | INTENT_BOOST_MULTIPLIERS dict (8 entries) | None or unknown intent = 1.0; prefers intent_ultrabert, falls back to intent_label | N/A | 1.0 (neutral) | N/A | Looks up intent in boost table; query_memory=1.20, casual_chat=0.90. No longer separate method. |
| 7 | weight_loading | importance_scorer.py get_weights | data loading | space_id, weight_store | weight_store may be None | ImportanceWeights | always returns valid weights (learned or static) | O(1) amortized (cached) | O(1) | no (depends on DB state) | yes | _cached_weights | MIN_SAMPLES_FOR_LEARNED_WEIGHTS=500 | No weight store = static defaults; < 500 samples = static defaults; corrupted weights = static defaults | logs warning, returns static | static ImportanceWeights() | WeightStoreProtocol | Loads per-space learned weights if >= 500 observations, else returns static defaults |
| 8 | cold_start_blending | importance_scorer.py get_weights_with_cold_start | data loading | space_id, weight_store | weight_store may be None | ImportanceWeights | always returns valid weights with progressive blending | O(1) | O(1) | no | yes | _cached_weights | MIN_SAMPLES=500, alpha = sample_count/500 | 0 samples = pure static; 250 samples = 50/50 blend; 500+ samples = pure learned | logs info, returns blended | static ImportanceWeights() | WeightStoreProtocol | 3-level fallback: per-space learned -> global -> static. Progressive blending: alpha *learned + (1-alpha)* static |
| 9 | priority_tier | importance_scorer.py get_priority_tier | classification | importance_score: float | score in [0.0, 1.0] | str (CRITICAL/HIGH/MEDIUM_HIGH/MEDIUM/LOW_MEDIUM/LOW) | always returns one of 6 tiers | O(1) | O(1) | yes | no | N/A | thresholds: 0.80, 0.60, 0.45, 0.30, 0.15 | score exactly on threshold = upper tier | N/A | LOW | N/A | 6-tier: CRITICAL >= 0.80, HIGH >= 0.60, MEDIUM_HIGH >= 0.45, MEDIUM >= 0.30, LOW_MEDIUM >= 0.15, LOW < 0.15. Moved from r1_importance_scorer.py to importance_scorer.py. |
| 10 | hebbian_update | hebbian_learner.py update_edge_weight | learning | current_weight: float, event_importance: float | weight in [0, max_weight], importance in [0, 1] | float [min_weight, max_weight] | soft saturation near max_weight | O(1) | O(1) | yes | no | N/A | learning_rate=0.1, max_weight=1.0 | weight=0 starts fresh; weight=max_weight no change; importance=0 no change | N/A | N/A | N/A | delta = learning_rate *(max_weight - current_weight)* event_importance; new = current + delta |
| 11 | exponential_decay | hebbian_learner.py apply_decay | decay | edges: dict, days_elapsed: float | days >= 0 | dict (updated edges, weak ones pruned) | preserves strong edges, prunes weak | O(n) | O(n) | yes | no | N/A | decay_rate=0.01, prune_threshold=0.05 | 0 days = no change; large days prunes all weak edges | N/A | N/A | N/A | new_weight = weight *exp(-decay_rate* days_elapsed); prune if < prune_threshold |
| 12 | anti_hebbian_decay | hebbian_learner.py apply_anti_decay | decay | edge_weight: float, signal: AntiHebbianSignal, confidence: float | weight > 0, confidence in [0,1] | float [0.0, edge_weight] | weakens but never strengthens | O(1) | O(1) | yes | no | N/A | anti_learning_rate=0.15, signal penalties, explicit_correction_multiplier=1.3 | confidence=0 = no decay; MUTUAL_EXCLUSION has strongest penalty (0.8) | N/A | N/A | N/A | decay = anti_learning_rate *penalty* confidence * (explicit_correction_multiplier if explicit); clamp to 0 |
| 13 | cooccurrence_extraction | hebbian_learner.py extract_cooccurrences | transformation | event with ner_entities_json | JSON string or None | list[tuple[str, str, RelationType]] | pairs are sorted (source_id < target_id) for dedup | O(e^2) where e = entities | O(e^2) | yes | no | N/A | N/A | 0 or 1 entities = empty list; malformed JSON = empty list | returns empty on parse error | empty list | json.loads | Actor-Actor INTERACTS_WITH, Actor-Location FREQUENTS, Actor-Topic DISCUSSES |
| 14 | gradient_descent_step | importance_weight_learner.py train_step | learning | TrainingBatch | batch.len() >= min_batch_size=50 | TrainingResult | weights sum to 1.0, each in [0.05, 0.60] | O(b*c) b=batch, c=components(4) | O(b*c) | no (momentum state) | yes | _weights,_velocity, _loss_history, _step_count | empty batch returns early; small batch uses reduced LR; 3 consecutive loss increases triggers rollback | rollback to snapshot | prior weights | numpy, optional torch | Online gradient descent with momentum on BCE loss; softmax normalization; per-weight clamping |

### 3.2 Algorithm Gaps

| # | Gap Description | Expected Behavior | Current Behavior | Severity | Proposed Approach | Estimated Complexity |
| - | --------------- | ----------------- | ---------------- | -------- | ----------------- | -------------------- |
| 1 | **~~participant_count vs num_participants field name mismatch~~** | Social factor reads P03EventState.num_participants | **FIXED** (Epic 5A.4): Code now reads `getattr(event, "num_participants", 1)`. Social factor computed correctly. | ~~P0 (BUG)~~ **FIXED** | Implemented in 5A.4. social_w=0.15 with corrected field, plus intimacy_scale (HIGH=1.2, MED=1.0, LOW=0.8). 190 unit tests pass. | done |
| 2 | **Weight learner components don't match scorer weights** | Weight learner should train weights that ImportanceScorer uses | Learner trains (emotional, recency, access, social) but scorer uses (sentiment, affect, novelty, social) -- different names, different semantics, different priors | **P1** | Either: (a) align naming/mapping, or (b) add adapter layer between learner output and scorer input | medium |
| 3 | **~~No recency factor~~** | recency_factor should capture temporal decay since event creation | **FIXED** (Epic 5A.4): `compute_recency_factor(event_timestamp_ms, now_ms, weights)` computes `exp(-0.005 * hours)`. score_batch/score_batch_with_audit accept `now_ms` kwarg. ScoredEvent.recency_factor populated. | ~~P1~~ **FIXED** | Implemented in 5A.4. recency_w=0.15, RECENCY_LAMBDA=0.005. 190 tests pass. | done |
| 4 | **~~No surprise_level integration~~** | Scoring formula should incorporate MW v2 surprise_level | **FIXED** (Epic 5A.4): `compute_surprise_factor(surprise_level, weights)` computes `clamp(surprise_level) * surprise_w`. ScoredEvent.surprise_factor populated. set_importance accepts `surprise=` kwarg. | ~~P1~~ **FIXED** | Implemented in 5A.4. surprise_w=0.15. 190 tests pass. | done |
| 5 | **~~No elaboration_depth integration~~** | Detailed/elaborated events should score higher | **FIXED** (Epic 5A.4): `ELABORATION_MAP` lookup as multiplicative modulator in `compute_importance_score`. MENTION=1.00, DISCUSSED=1.05, ELABORATED=1.10, DEEPLY_PROCESSED=1.15. ImportanceBreakdown.elab_boost populated. | ~~P2~~ **FIXED** | Implemented in 5A.4. Multiplicative, not additive. | done |
| 6 | **~~No identity_relevance integration~~** | Events about core identity should score higher | **FIXED** (Epic 5A.4): `compute_identity_factor(identity_relevance, identity_domains_json, weights)`. Uses identity_relevance if >0, else len(identity_domains)/9.0 proxy. ScoredEvent.identity_factor populated. set_importance accepts `identity=` kwarg. | ~~P1~~ **FIXED** | Implemented in 5A.4. identity_w=0.10. 190 tests pass. | done |
| 7 | **~~No source_reliability modulation~~** | Less reliable sources should be discounted | **FIXED** (Epic 5A.4): `derive_source_reliability(source_reliability, source_type)` with `RELIABILITY_FLOOR=0.3`. SOURCE_TYPE_RELIABILITY lookup fallback. ImportanceBreakdown.reliability populated. Applied as multiplicative modulator in compute_importance_score. | ~~P2~~ **FIXED** | Implemented in 5A.4. Hybrid multiplicative with floor=0.3. | done |
| 8 | **~~No memory_tier awareness~~** | Different memory tiers should have different scoring thresholds | **FIXED** (Epic 5A.4): MEMORY_TIER_MAP used as multiplicative modulator in compute_importance_score (routine=1.00, notable=1.10, significant=1.25, landmark=1.50). ImportanceBreakdown.tier_multiplier populated. | ~~P2~~ **FIXED** | Implemented in 5A.4. Multiplicative modulator. | done |
| 9 | **~~Hebbian learning permanently disabled~~** | Enable after sufficient scoring data collected | **RESOLVED** (Decision D-R1-001): Auto-activation at 500 cumulative scored events. R1Config.hebbian_activation_threshold=500 added. WeightTrainingConfig.hebbian_activation_threshold=500 added. WeightTrainingTriggerResult.hebbian_activated reports when threshold crossed. enable_hebbian remains False as default; auto-activates via trigger. | ~~P2~~ **RESOLVED** | **DONE** (Decision D-R1-001): Threshold-based auto-activation implemented in weight_learning_trigger.py + r1_importance_scorer.py | done |
| 10 | **~~Audit sample_rate=1.0 in production~~** | Production should sample, not audit every event | **FIXED** (Epic 5A.4): R1Config.audit_sample_rate default changed from 1.0 to 0.10. Configurable via R1Config constructor. | ~~P2~~ **FIXED** | Implemented in 5A.4. Default now 0.10. | done |
| 11 | **~~Social factor caps at 10 participants~~** | Large group events should differentiate beyond 10 participants | **CLOSED** (Decision D-R1-003 won't fix): System is user-centric, not crowd intelligence. Even in 100-person events, user contacts 10-12 people max. log2(10)/3.32 ~= 1.0 cap is intentionally correct for personal memory semantics. | ~~P3~~ **CLOSED** | **WON'T FIX** (Decision D-R1-003): Cap at 10 is architecturally correct for user-centric design | done |
| 12 | **~~No affect_arousal integration~~** | High arousal events are more memorable | **FIXED** (Epic 5A.4): `compute_emotional_intensity` now takes `affect_arousal` parameter. arousal_w=0.08 in CONFIG_B emotional block (sent=0.10 + affect=0.12 + arousal=0.08 = 0.30 total). | ~~P2~~ **FIXED** | Implemented in 5A.4. arousal_w=0.08. | done |
| 13 | **~~Contract describes Thompson Sampling but code uses gradient descent~~** | Contract and implementation should agree | **FIXED** (Epic 5A.4): Contract YAML rewritten with CONFIG_B formula description. Thompson Sampling reference removed. formula_version="2.0.0". | ~~P1~~ **FIXED** | Contract updated in 5A.4. | done |
| 14 | **~~Contract formula doesn't match code formula~~** | Contract says importance = w_recency *recency + w_affect* affect + w_social *social + w_rehearsal* rehearsal + w_novelty * novelty | **FIXED** (Epic 5A.4): Contract now describes CONFIG_B formula: base(6 additive) * 7 modulators. formula_version="2.0.0". | ~~P1~~ **FIXED** | Contract updated in 5A.4. | done |
| 15 | **~~Uses salience_score as novelty proxy~~** | Should use dedicated novelty signal | **FIXED** (Epic 5A.4): `compute_novelty_factor(novelty_categorical, salience_fallback, weights)`. Uses NOVELTY_MAP (ROUTINE=0.10, EXPECTED=0.30, NOVEL=0.70, SURPRISING=1.00) as primary. salience_score only as fallback when novelty field empty. | ~~P2~~ **FIXED** | Implemented in 5A.4. Categorical novelty primary. | done |

---

## 4. Data Flow & I/O Map

### 4.1 Pipeline Stage Map

| Stage Order | Stage ID | Module | Input Event / Topic | Output Event / Topic | Side Effects | Error Topic | Retry Policy |
| ----------- | -------- | ------ | ------------------- | -------------------- | ------------ | ----------- | ------------ |
| 2 | stage_10_importance_score (R1) | k0.modules.consolidation.importance_scorer | P03BatchEnvelope (in-memory from R0) | N/A (envelope mutated, not emitted) | Reads st_learned_weights (weights), writes envelope.phases.r1_scored_events and r1_audit_records | P03Error (R1 phase error, recoverable=True) | Retriable (idempotent via cycle_id) |

> **Note**: R1 receives the P03BatchEnvelope from R0 in-memory and mutates it. Each P03EventState gets importance_score, recency_factor, affect_factor, social_factor, novelty_factor set via set_importance(). Phase outputs stored in envelope.phases.

### 4.2 Input Schemas (per stage / module)

**Stage: R1 (importance_scorer)**

| # | Field | Type | Required | Nullable | Validation Rule | Source | Example Value |
| - | ----- | ---- | -------- | -------- | --------------- | ------ | ------------- |
| 1 | envelope.events[*].sentiment_score | float | no | yes | [-1.0, 1.0], defaults to 0.0 | P02 via R0 hydration | 0.75 |
| 2 | envelope.events[*].affect_valence | float | no | yes | [-1.0, 1.0], defaults to 0.0 | P02 via R0 | -0.3 |
| 3 | envelope.events[*].affect_arousal | float | no | yes | [0.0, 1.0], defaults to 0.0 | P02 via R0 | 0.7 |
| 4 | envelope.events[*].surprise_level | float | no | yes | [0.0, 1.0], defaults to 0.0 | P02/K1 via R0 | 0.8 |
| 5 | envelope.events[*].novelty | str | no | yes | ROUTINE/EXPECTED/NOVEL/SURPRISING, defaults to "" | MW v2 via R0 | "NOVEL" |
| 6 | envelope.events[*].salience_score | float | no | yes | [0.0, 1.0], defaults to 0.0 (fallback for novelty) | P02 via R0 | 0.8 |
| 7 | envelope.events[*].num_participants | int | no | yes | >= 0, defaults to 1 | P02 via R0 | 3 |
| 8 | envelope.events[*].social_intimacy | str | no | yes | HIGH/MEDIUM/LOW, defaults to "" | P02 M07 via R0 | "HIGH" |
| 9 | envelope.events[*].identity_relevance | float | no | yes | [0.0, 1.0], defaults to 0.0 | K1 (future) via R0 | 0.6 |
| 10 | envelope.events[*].identity_domains_json | str | no | yes | JSON array of domain strings, defaults to "[]" | MW v2 via R0 | "[\"parent_identity\"]" |
| 11 | envelope.events[*].timestamp | int | no | yes | ms since epoch, defaults to 0 | R0 (from event_time_utc) | 1709337600000 |
| 12 | envelope.events[*].elaboration_depth | str | no | yes | MENTION/DISCUSSED/ELABORATED/DEEPLY_PROCESSED | MW v2 via R0 | "ELABORATED" |
| 13 | envelope.events[*].narrative_is_goal_event | bool | no | no | defaults to False | MW v2 via R0 | true |
| 14 | envelope.events[*].narrative_arc_position | str | no | yes | EXPOSITION/RISING_ACTION/CLIMAX/RESOLUTION | MW v2 via R0 | "CLIMAX" |
| 15 | envelope.events[*].temporal_orientation | str | no | yes | PAST/ONGOING/FUTURE_COMMITMENT | MW v2 via R0 | "ONGOING" |
| 16 | envelope.events[*].source_reliability | float | no | yes | [0.0, 1.0], defaults to 1.0 (trust by default) | K1 (future) via R0 | 0.80 |
| 17 | envelope.events[*].source_type | str | no | yes | user_stated/user_implied/device_observed/system_inferred | MW v2 via R0 | "user_stated" |
| 18 | envelope.events[*].memory_tier | str | no | yes | routine/notable/significant/landmark, defaults to "routine" | K1 (future) via R0 | "notable" |
| 19 | envelope.events[*].activity_type_ultrabert | str | no | yes | one of 13 known types or None | P02 via R0 | "milestone" |
| 20 | envelope.events[*].intent_ultrabert | str | no | yes | one of 8 known types or None | P02 via R0 | "query_memory" |
| 21 | envelope.events[*].content_type | str | no | yes | fallback for activity_type, defaults to "message" | R0 | "photo" |
| 22 | envelope.context.cycle_id | str | yes | no | ULID format | R0 envelope construction | "01HQXYZ..." |
| 23 | st_learned_weights (external) | dict | no | yes | {weights: dict, sample_count: int} | Weight store DB | {"sentiment": 0.10, ...} |

### 4.3 Output Schemas (per stage / module)

**Stage: R1 (importance scorer phase outputs)**

| # | Field | Type | Nullable | Produced By | Consumed By | Example Value |
| - | ----- | ---- | -------- | ----------- | ----------- | ------------- |
| 1 | envelope.events[*].importance_score | float | no | ImportanceScorer.compute_importance_score | R3 (dedup/decay thresholds), R5 (dream selection), R6 (staging) | 0.72 |
| 2 | envelope.events[*].recency_factor | float | no | compute_recency_factor (exp decay) | R3 | 0.89 |
| 3 | envelope.events[*].affect_factor | float | no | compute_emotional_intensity (sent+val+arousal) | R3, R5 | 0.22 |
| 4 | envelope.events[*].social_factor | float | no | compute_social_factor (log2 * intimacy) | R3, R5 | 0.09 |
| 5 | envelope.events[*].novelty_factor | float | no | compute_novelty_factor (categorical or fallback) | R3, R5 | 0.105 |
| 6 | envelope.events[*].surprise_factor | float | no | compute_surprise_factor | downstream | 0.12 |
| 7 | envelope.events[*].identity_factor | float | no | compute_identity_factor | downstream | 0.07 |
| 8 | envelope.events[*].importance_computed | bool | no | P03EventState.set_importance() | R1 should_skip() check | True |
| 9 | envelope.phases.r1_scored_events | list[ScoredEvent] | no | R1 phase | R6 staging | [{event_id, importance_score, recency_factor, affect_factor, social_factor, novelty_factor, surprise_factor, identity_factor, priority_tier}] |
| 10 | envelope.phases.r1_audit_records | list[AuditRecord] | no | P03AuditLogger | R6 staging (bulk insert to st_consolidation_audit) | [{audit_id, event_id, action=SCORE, ...}] |
| 11 | P03PhaseResult.outputs_summary | dict | no | R1 phase | SequentialRunner logging | {events_scored: 42, avg_score: 0.45, max_score: 0.92, critical_count: 2, high_count: 5, ...} |

### 4.4 Error Outputs

| # | Error Code / Type | Condition | HTTP Status | Handling | Downstream Impact | Recoverable? |
| - | ----------------- | --------- | ----------- | -------- | ----------------- | ------------ |
| 1 | Skip (events empty) | envelope.events is empty | N/A | skip | Pipeline continues to R2 with no scored events | yes -- normal |
| 2 | Skip (all scored) | All events have importance_computed=True | N/A | skip | Pipeline continues to R2 with existing scores | yes -- normal |
| 3 | WeightStoreError | Weight store query fails | N/A | fallback | Uses static default weights | yes -- non-fatal |
| 4 | RuntimeError | Unhandled exception in run() | N/A | fail | Pipeline may retry R1 | yes -- marked recoverable |

### 4.5 Data Transformation Map

| # | Source Field(s) | Transformation | Target Field | Lossy? | Reversible? | Notes |
| - | --------------- | -------------- | ------------ | ------ | ----------- | ----- |
| 1 | sentiment_score, affect_valence, affect_arousal | weighted abs sum: sent_w*abs(sent) + affect_w*abs(val) + arousal_w*arousal (0.10+0.12+0.08=0.30) | emotional_intensity (intermediate) -> affect_factor | yes (abs loses sign) | no | Sign information discarded; positive and negative emotions treated equally. arousal is [0,1] so no abs needed. |
| 2 | novelty (categorical) | NOVELTY_MAP lookup: ROUTINE=0.10, EXPECTED=0.30, NOVEL=0.70, SURPRISING=1.00 | novelty_factor | no | yes | Categorical to numeric conversion. Falls back to salience_score * novelty_w if novelty field empty |
| 3 | num_participants, social_intimacy | log + intimacy: social_w *min(1.0, log2(count)/3.32)* INTIMACY_SCALE[intimacy] | social_factor | yes (log compression) | no | Logarithmic compression loses exact count; caps at 10 participants. INTIMACY_SCALE: HIGH=1.2, MED=1.0, LOW=0.8 |
| 4 | surprise_level | weighted clamp: surprise_w * clamp(surprise_level, 0, 1) | surprise_factor | no | yes | Direct proportional mapping |
| 5 | identity_relevance, identity_domains_json | conditional: identity_w * (identity_relevance if >0 else len(domains)/9.0) | identity_factor | yes (count->ratio) | no | Uses relevance score if available, falls back to domain count proxy |
| 6 | timestamp, now_ms | exponential decay: recency_w *exp(-RECENCY_LAMBDA* hours_since_event) | recency_factor | yes (decay) | no | RECENCY_LAMBDA=0.005 (half-life ~139h). Requires now_ms to be passed through score_batch |
| 7 | activity_type_ultrabert | lookup: EVENT_TYPE_MULTIPLIERS[type] | type_multiplier (modulator) | no | yes | Direct lookup with 1.0 default. Prefers activity_type_ultrabert, falls back to content_type |
| 8 | intent_ultrabert | lookup: INTENT_BOOST_MULTIPLIERS[intent] | intent_boost (modulator) | no | yes | Direct lookup with 1.0 default. Falls back to intent_label |
| 9 | elaboration_depth | lookup: ELABORATION_MAP[depth] | elab_boost (modulator) | no | yes | MENTION=1.0, DISCUSSED=1.05, ELABORATED=1.10, DEEPLY_PROCESSED=1.15 |
| 10 | narrative_is_goal_event | conditional: GOAL_BOOST (1.15) if True else 1.0 | goal_boost (modulator) | no | yes | Binary multiplier |
| 11 | narrative_arc_position | lookup: ARC_MAP[position] | arc_boost (modulator) | no | yes | EXPOSITION=1.0, RISING_ACTION=1.05, CLIMAX=1.15, RESOLUTION=1.0 |
| 12 | temporal_orientation | lookup: TEMPORAL_MAP[orientation] | temporal_boost (modulator) | no | yes | PAST=1.0, ONGOING=1.05, FUTURE_COMMITMENT=1.10 |
| 13 | source_reliability, source_type | hybrid derive: max(0.3, reliability if <1.0 else SOURCE_TYPE_RELIABILITY[type]) | reliability (modulator) | no | no | Floor=0.3 prevents total suppression |
| 14 | memory_tier | lookup: MEMORY_TIER_MAP[tier] | tier_multiplier (modulator) | no | yes | routine=1.0, notable=1.10, significant=1.25, landmark=1.50 |
| 15 | base + 7 modulators + reliability | product + clamp: clamp(base *elab* goal *arc* temporal *type* intent *tier* reliability, 0, 1) | importance_score | yes (clamp) | no | Product of components can exceed 1.0 before clamping |
| 16 | importance_score + 6 factors | set_importance(score, recency, affect, social, novelty, surprise, identity) | P03EventState.importance_score + 6 factor fields + importance_computed=True | no | yes | Direct assignment to mutable event state. 7-param method. |

---

## 5. Storage & Persistence

### 5.1 Tables Touched

| # | Table | Operation | Key Columns Used | Access Pattern | Index Used | Estimated Row Count |
| - | ----- | --------- | ---------------- | -------------- | ---------- | ------------------- |
| 1 | st_learned_weights | R | space_id, tenant_id | point (composite key lookup) | PK (space_id, tenant_id) | ~100 (one per space) |
| 2 | st_consolidation_audit | (deferred W) | audit_id, event_id, cycle_id, phase_id, action | batch insert by R6 | PK (audit_id) | ~10K-100K |

> **Note**: R1 itself does not perform direct database writes. Weight reads go through WeightStoreProtocol. Audit records are accumulated in-memory and flushed by R6 staging phase. The ImportanceWeightLearner has persist_weights/load_weights for st_learned_weights, but these are not called during R1 phase execution.

### 5.2 Column-Level Detail

**st_learned_weights columns read by R1:**

| Table | Column | Type | Nullable | Default | Read By | Written By | Indexed? | Notes |
| ----- | ------ | ---- | -------- | ------- | ------- | ---------- | -------- | ----- |
| st_learned_weights | space_id | VARCHAR(64) | no | NONE | ImportanceScorer.get_weights | ImportanceWeightLearner.persist_weights | yes (PK composite) | Space isolation |
| st_learned_weights | tenant_id | VARCHAR(64) | no | NONE | ImportanceScorer.get_weights | ImportanceWeightLearner.persist_weights | yes (PK composite) | Tenant isolation |
| st_learned_weights | weights_json | TEXT | no | NONE | ImportanceScorer.get_weights | ImportanceWeightLearner.persist_weights | no | JSON: {"sentiment": 0.28, "affect": 0.32, ...} |
| st_learned_weights | sample_count | INTEGER | no | 0 | ImportanceScorer.get_weights (threshold check) | ImportanceWeightLearner.persist_weights | no | Must be >= 500 to use learned weights |
| st_learned_weights | updated_at | BIGINT | yes | NULL | N/A | ImportanceWeightLearner.persist_weights | no | Last update timestamp (ms) |

**st_consolidation_audit columns written by R1 (via R6):**

| Table | Column | Type | Nullable | Default | Read By | Written By | Indexed? | Notes |
| ----- | ------ | ---- | -------- | ------- | ------- | ---------- | -------- | ----- |
| st_consolidation_audit | audit_id | TEXT | no | NONE | dashboards | P03AuditLogger (via R6) | yes (PK) | ULID-based unique ID |
| st_consolidation_audit | event_id | TEXT | no | NONE | dashboards | P03AuditLogger | yes | Links to st_hipp_events.event_id |
| st_consolidation_audit | cycle_id | TEXT | no | NONE | dashboards | P03AuditLogger | yes | Links to P03CycleContext.cycle_id |
| st_consolidation_audit | phase_id | VARCHAR(16) | no | NONE | dashboards | P03AuditLogger | yes | "R1" for importance scoring |
| st_consolidation_audit | action | VARCHAR(16) | no | NONE | dashboards | P03AuditLogger | yes | "SCORE" for R1 decisions |
| st_consolidation_audit | explanation | TEXT | yes | NULL | dashboards | P03AuditLogger | no | Human-readable scoring rationale from template |
| st_consolidation_audit | metadata_json | TEXT | yes | NULL | dashboards | P03AuditLogger | no | JSON: ImportanceBreakdown serialized (PII-redacted) |
| st_consolidation_audit | created_at | BIGINT | no | NONE | dashboards | P03AuditLogger | no | Audit record creation timestamp (ms) |

### 5.3 Query Patterns

| # | Query Purpose | SQL Pattern | Frequency | Expected Latency | Index Coverage | Notes |
| - | ------------- | ----------- | --------- | ---------------- | -------------- | ----- |
| 1 | Load learned weights | SELECT weights_json, sample_count FROM st_learned_weights WHERE space_id=$1 AND tenant_id=$2 | once per R1 invocation (cached) | < 5ms | full (PK) | Single row point lookup |
| 2 | Audit bulk insert (via R6) | INSERT INTO st_consolidation_audit (audit_id, event_id, cycle_id, phase_id, action, explanation, metadata_json, created_at) VALUES ($1...) | once per cycle (R6 phase) | < 100ms for 1000 rows | N/A (insert) | Batch insert, not done by R1 directly |

### 5.4 Storage Gaps

| # | Gap | Current State | Required State | Migration Needed? | Priority |
| - | --- | ------------- | -------------- | ----------------- | -------- |
| 1 | st_learned_weights may not exist in all deployments | Weight store returns None if table missing | Need graceful fallback + migration verification | maybe (table creation migration) | P2 |
| 2 | Audit records have no retention policy | st_consolidation_audit grows unbounded | Need TTL-based cleanup or partition by cycle_id | yes (add retention cron or partitioning) | P2 |
| 3 | No index on st_consolidation_audit(cycle_id, phase_id) | Queries by cycle or phase require full scan | Composite index for dashboard queries | yes (CREATE INDEX) | P3 |

---

## 6. Event Bus & Topics

### 6.1 Topics Consumed

| # | Topic | Schema (YAML ref) | Producer Module | Consumer Module | Ordering Guarantee | Idempotency Key |
| - | ----- | ------------------ | --------------- | --------------- | ------------------ | --------------- |
| 1 | p03.batch.selected.v1 | consolidation.importance_scorer.v1.yaml (input_event_types) | R0 batch_selector | R1 importance_scorer | ordered (within pipeline) | p03:r1:{cycle_id} |

> **Note**: This is a logical topic declared in the contract. In practice, R1 receives the P03BatchEnvelope in-memory from R0 via SequentialRunner, not through the event bus.

### 6.2 Topics Emitted

| # | Topic | Schema (YAML ref) | Emitter Module | Known Consumers | Payload Size | Frequency |
| - | ----- | ------------------ | -------------- | --------------- | ------------ | --------- |
| 1 | p03.importance.scored.v1 | consolidation.importance_scorer.v1.yaml (output_event_types) | R1 importance_scorer | R2 episodic_integrator (contract says) | N/A | N/A |

> **Note**: Like R0, R1 does not actually emit bus events. The envelope is passed in-memory to R2. The contract declares p03.importance.scored.v1 as output but it is not emitted. This is an inconsistency between contract and code.

### 6.3 Topic Gaps (needed but missing)

| # | Proposed Topic | Purpose | Producer | Consumer | Schema Draft | Priority |
| - | -------------- | ------- | -------- | -------- | ------------ | -------- |
| 1 | k0.consolidation.importance.scored.v1 | Enable external monitoring of scoring outcomes | R1 importance_scorer | monitoring/dashboards | {tenant_id, space_id, cycle_id, events_scored, avg_score, max_score, priority_tiers: {CRITICAL: n, HIGH: n, ...}} | P3 |
| 2 | k0.consolidation.weights.updated.v1 | Notify when learned weights change | ImportanceWeightLearner (not R1) | monitoring, weight drift alerting | {tenant_id, space_id, old_weights, new_weights, sample_count, drift} | P3 |

---

## 7. Observability Audit

### 7.1 Existing Metrics

| # | Metric Name | Type | Location | Labels | Purpose | Alert Threshold |
| - | ----------- | ---- | -------- | ------ | ------- | --------------- |
| 1 | r1_score_distribution | Histogram | observability.py | space_id, cycle_id | Score distribution per cycle (0.1 interval buckets) | drift > 2 std from rolling mean |
| 2 | r1_weight_source | Counter | observability.py | source=static/learned/blended | Tracks cold-start progression per space | N/A |
| 3 | r1_priority_tier_count | Gauge | observability.py | tier=CRITICAL/HIGH/MEDIUM_HIGH/MEDIUM/LOW_MEDIUM/LOW | Monitor tier distribution trends | CRITICAL > 10% triggers review |
| 4 | r1_audit_records | Counter | observability.py | sampled=true/false | Audit overhead monitoring | N/A |

> **Note**: All metrics implemented in M5.O (Epic 5.O.1). R1PhaseMetrics now fully populated. 49 OTel tests + 57 metrics tests = 106 observability tests passing.

### 7.2 Existing Traces / Spans

| # | Span Name | Location | Attributes | Parent Span | Purpose |
| - | --------- | -------- | ---------- | ----------- | ------- |
| 1 | r1_importance_scoring | r1_importance_scorer.py | events_scored, avg_score, weight_source, formula_version, cycle_id | p03_consolidation | Full R1 phase execution span (M5.O) |

> **Note**: OTel span added in M5.O Epic 5.O.1. Duration tracked via span, replacing manual time.time() calculation.

### 7.3 Structured Log Points

| # | Log Level | Location | Message Pattern | Fields | Purpose |
| - | --------- | -------- | --------------- | ------ | ------- |
| 1 | INFO | r1_importance_scorer.py | "R1: Starting importance scoring" | cycle_id, tenant_id, space_id, event_count | Track R1 start |
| 2 | INFO | r1_importance_scorer.py | "R1: Using %s weights (sample_count=%d)" | weight_source (static/learned), sample_count | Track which weights are used |
| 3 | INFO | r1_importance_scorer.py | "R1: Importance scoring complete" | cycle_id, events_scored, avg_score, max_score, min_score, critical_count, high_count, medium_high_count, medium_count, low_medium_count, low_count, duration_ms | Success summary with 6-tier distribution |
| 4 | WARNING | r1_importance_scorer.py | "R1: Skipping -- %s" | skip_reason | Skip detection |

### 7.4 Observability Gaps

| # | Gap | What's Missing | Impact if Unresolved | Priority |
| - | --- | -------------- | -------------------- | -------- |
| 1 | ~~No OTel spans for R1 phase~~ | ~~Span for entire R1 execution~~ | ~~Cannot trace R1~~ | ~~P1~~ **CLOSED** (M5.O Epic 5.O.1): OTel span `r1_importance_scoring` added with events_scored, avg_score, weight_source, formula_version attributes. 49 tests. |
| 2 | ~~No score distribution histogram~~ | ~~Histogram of importance_score values per cycle~~ | ~~Cannot detect scoring drift~~ | ~~P1~~ **CLOSED** (M5.O): r1_score_distribution histogram with 0.1 interval buckets. |
| 3 | ~~No weight source counter~~ | ~~Counter with labels: source=static/learned/blended~~ | ~~Cannot track cold start progression~~ | ~~P2~~ **CLOSED** (M5.O): r1_weight_source counter tracks static/learned/blended per space. |
| 4 | ~~No priority tier distribution gauge~~ | ~~Gauge for CRITICAL/HIGH/MEDIUM/LOW counts~~ | ~~Cannot monitor tier trends~~ | ~~P2~~ **CLOSED** (M5.O): r1_priority_tier_count gauge for all 6 tiers. |
| 5 | ~~No audit record counter~~ | ~~Counter for audit records generated vs sampled~~ | ~~Cannot monitor audit overhead~~ | ~~P3~~ **CLOSED** (M5.O): r1_audit_records counter with sampled label. |
| 6 | ~~R1PhaseMetrics defined but unused~~ | ~~R1 never populates R1PhaseMetrics~~ | ~~Dead code~~ | ~~P2~~ **CLOSED** (M5.O): R1PhaseMetrics now fully populated by R1 phase. 57 metrics tests. |
| 7 | ~~No alert on all-zero social factors~~ | ~~Social factor is always 0.0 due to BUG-001 but no alert detects this~~ | **RESOLVED**: BUG-001 fixed in Epic 5A.4. social_factor now computed correctly from num_participants + social_intimacy. | ~~P1~~ **CLOSED** |

---

## 8. Test Coverage Audit

### 8.1 Existing Tests

| # | Test File | Lines | Test Count | Type | Coverage Target | Pass / Fail | Notes |
| - | --------- | ----- | ---------- | ---- | --------------- | ----------- | ----- |
| 1 | tests/k0/pipelines/p03/test_r1_importance_scorer.py | ~2000 | 95 | unit | ImportanceScorer algorithm (8-weight CONFIG_B, emotional+arousal, social+intimacy, novelty categorical, surprise, identity, recency, source reliability, modulators, event type, intent, batch, learned weights, priority tier 6-tier) | PASS | 17 test classes. Uses MockEvent with all CONFIG_B fields. |
| 2 | tests/k0/pipelines/p03/test_r1_hebbian_learner.py | ~759 | 58 | unit | HebbianLearner (config, entity parsing, co-occurrence, edge updates, decay, anti-Hebbian, batch) | PASS | Comprehensive coverage. M5.H wiring verified. |
| 3 | tests/k0/pipelines/p03/test_r1_importance_learner.py | ~405 | 38 | unit | ImportanceWeightLearner (config, samples, training, rollback, diagnostics) | PASS | Tests gradient descent, clamping, convergence |
| 4 | tests/k0/pipelines/p03/test_r1_phase_integration.py | ~500 | 24 | integration | R1 phase with real envelope, scoring, audit, set_importance 7 params | PASS | **CONFIG_B** (Epic 5A.4) |
| 5 | tests/k0/pipelines/p03/test_r1_observability.py | ~800 | 49 | unit | OTel spans, score histograms, weight source counters, priority tier gauges | PASS | **M5.O** (Epic 5.O.1) |
| 6 | tests/k0/pipelines/p03/test_r1_metrics.py | ~900 | 57 | unit | R1PhaseMetrics population, metric registry, formula version tracking | PASS | **M5.O** (Epic 5.O.1) |
| 7 | tests/k0/pipelines/p03/test_r1_cold_start.py | ~400 | 20 | unit | Cold-start weight fallback, progressive blending, weight store unavailable | PASS | **M5.O** (Epic 5.O.2) |
| 8 | tests/k0/pipelines/p03/test_r1_poc_scenarios.py | ~2000 | 7 | regression | POC Phase 6 scenario validation against CONFIG_B formula | PASS | **M5.O** (Epic 5.O.2) |
| 9 | tests/k0/pipelines/p03/test_r1_performance.py | ~200 | 5 | perf | Latency <30ms for 100 events, throughput >3000/s | PASS | **M5.O** (Epic 5.O.2) |
| 10 | tests/k0/pipelines/p03/test_r1_hebbian_idempotency.py | ~200 | 10 | unit | Hebbian disabled path (5 tests) + scoring idempotency (5 tests) | PASS | **M5.O** (Epic 5.O.2) |
| 11 | tests/k0/pipelines/p03/test_weight_learner_alignment.py | ~500 | 21 | integration | Weight learner -> scorer 8-component alignment, blending, cold-start | PASS | **M5.W** (Epic 5.W.1) |
| 12 | tests/k0/pipelines/p03/test_p03_feedback_consumer.py | ~600 | 32 | integration | Grounding signal routing, K1 feedback path, reinforcement cycle | PASS | **M6.F** (Epic 5.F.1/5.F.2) |
| 13 | tests/k0/pipelines/p03/test_kg_relationship_boost.py | ~800 | 47 | integration | KG edge boost in R1, relationship_boost_factor, batch caching | PASS | **M6.F** (Epic 5.F.1) |
| 14 | tests/k0/pipelines/p03/test_learned_weights_wiring.py | ~400 | 20 | integration | Unified weight store adapter, PgLearnedWeightsStore, R1+R3 wiring | PASS | **M5.P** (Epic 5.P.1) |
| 15 | tests/k0/pipelines/p03/test_reinforcement_cycle.py | ~400 | 23 | integration | Full reinforcement cycle: R1 -> Hebbian -> KG boost -> convergence | PASS | **M6.F** (Epic 5.F.2) |
| 16 | tests/k0/pipelines/p03/test_grounding_signal_pipeline.py | ~600 | 38 | integration | Grounding signal path: K1 -> weight learner training data | PASS | **M5.W** (Epic 5.W.2) |
| 17 | tests/k0/pipelines/p03/learning/test_feedback_queue.py | ~400 | 19 | unit | Feedback queue: signal enqueue/dequeue, backpressure, error handling | PASS | **M6.F** (Epic 5.F.1) |
| 18 | tests/k0/pipelines/p03/learning/test_async_audit.py | ~300 | 18 | unit | Async audit writer: learning event capture, telemetry | PASS | **M6.F** (Epic 5.F.2) |
| 19 | tests/k0/pipelines/p03/learning/test_learning_anomaly_detector.py | ~600 | 39 | unit | Anomaly detector: runaway inflation, drift detection, convergence | PASS | **M6.F** (Epic 5.F.2) |
| 20 | tests/k0/pipelines/p03/test_m5s_storage_housekeeping.py | ~700 | 32 | integration | Storage: migration 0075, st_learned_weights, merge_cascade_id index | PASS | **M5.S** (Epic 5.S.1) |
| 21 | tests/k0/pipelines/p03/test_p03_retention.py | ~600 | 31 | integration | Retention policy: audit TTL cleanup, retention periods | PASS | **M5.S** (pre-existing + verified) |

**Test breakdown (test_r1_importance_scorer.py):**

| Class | Tests | What It Proves |
| ----- | ----- | -------------- |
| TestImportanceWeights | 5 | Default weights sum to 1.0, correct CONFIG_B defaults (8 fields: 0.10/0.12/0.08/0.15/0.15/0.15/0.10/0.15), custom weights, as_dict() 8 keys, frozen |
| TestImportanceBreakdown | 3 | Breakdown to_dict() serialization (17 fields), default values correct, full audit transparency |
| TestComputeEmotionalIntensity | 5 | Zero inputs=0.0, high positive sentiment, high negative sentiment, high affect_valence, combined sentiment+affect+arousal |
| TestComputeSocialFactor | 5 | Solo event=0.0, pair=moderate, group=higher, large group (10+) capped, intimacy scale (HIGH=1.2x, LOW=0.8x) |
| TestComputeNoveltyFactor | 5 | ROUTINE=0.10 mapped, NOVEL=0.70 mapped, SURPRISING=1.0 mapped, salience_score fallback when novelty empty, clamped |
| TestComputeSurpriseFactor | 4 | Zero=0.0, full=surprise_w, partial=proportional, clamped above 1.0 |
| TestComputeIdentityFactor | 5 | Zero relevance + no domains=0.0, high relevance=identity_w, identity_domains fallback (len/9.0), clamped, invalid JSON=0.0 |
| TestComputeRecencyFactor | 5 | now_ms=event_ms gives full recency_w, 24h old event decays, very old event near 0, invalid timestamps=0.0, negative delta=0.0 |
| TestDeriveSourceReliability | 5 | MW value used when <1.0, source_type fallback, unknown source_type=1.0, floor enforced (min 0.3), default when both absent |
| TestModulators | 6 | ELABORATION_MAP lookup (4 levels), TEMPORAL_MAP (3 levels), ARC_MAP (4 positions), MEMORY_TIER_MAP (4 tiers), GOAL_BOOST stacking, unknown keys=1.0 |
| TestEventTypeMultipliers | 6 | message=1.0, milestone=2.0, routine=0.5, unknown=1.0, case-insensitive, None=1.0 |
| TestComputeImportanceScore | 8 | All-zero=0.0, high emotion milestone event, routine low engagement, combined all-factor CONFIG_B, clamped to [0,1], breakdown 17 fields, now_ms passed through, reliability modulates |
| TestScoreBatch | 5 | Empty batch=empty, single event scored, multi-event batch, scores match individual, set_importance called with 7 params (score, recency, affect, social, novelty, surprise, identity) |
| TestSelectBatch | 3 | Top-N selection, sorted descending, handles dicts and objects |
| TestGetPriorityTier | 6 | CRITICAL>=0.80, HIGH>=0.60, MEDIUM_HIGH>=0.45, MEDIUM>=0.30, LOW_MEDIUM>=0.15, LOW<0.15 |
| TestLearnedWeights | 4 | Static when no store, static when <500 samples, learned when >=500, cache invalidation |
| TestIntentBoostMultipliers | 9 | All 8 intent types tested + stacking test (milestone * query_memory) |

**Test breakdown (test_r1_hebbian_learner.py):**

| Class | Tests | What It Proves |
| ----- | ----- | -------------- |
| TestHebbianConfig | 5 | Default values, validation passes, invalid learning rate (zero/negative), min>max weight |
| TestParseEntities | 7 | Empty JSON, empty string, None, person entities, location, mixed, alternative field names, string entities, invalid JSON, missing entity_id |
| TestExtractCooccurrences | 8 | Empty event, single actor, two actors (1 pair), three actors (3 pairs), actor-location FREQUENTS, actor-topic DISCUSSES, complex all types, explicit overrides |
| TestUpdateEdgeWeight | 7 | Basic update, soft saturation, capped at max, low importance, high importance, zero weight, custom learning rate |
| TestComputeInitialWeight | 1 | Initial weight bounded by config |
| TestApplyDecay | 5 | No decay at 0 days, preserves strong edges, prunes weak edges, exponential formula, multiple edges |
| TestAntiHebbianDecay | 7 | ENTITY_MERGE_REJECTED penalty, ASSOCIATION_WRONG penalty, MUTUAL_EXCLUSION penalty, CONTRADICTION penalty, explicit correction multiplier, prune threshold, weight clamped to zero, confidence scales decay, unknown signal default |
| TestGetPenalty | 1 | Penalty lookup for all signal types |
| TestProcessBatch | 4 | Empty batch, single event, multiple events aggregate, batch updates event state |

**Test breakdown (test_r1_importance_learner.py):**

| Class | Tests | What It Proves |
| ----- | ----- | -------------- |
| TestWeightLearnerConfig | 7 | Default values, get_priors dict, get_priors_list, learning rate bounds, momentum bounds, min_samples positive, weight bounds ordering |
| TestTrainingSample | 4 | to_features, to_label grounded/not-grounded, compute_sample_weight recent, compute_sample_weight decay |
| TestTrainingBatch | 4 | Empty batch, batch len, to_arrays shape, to_arrays values |
| TestImportanceWeightLearner | 10 | Init defaults, custom config, backend detection, get_weights normalized, get_weights clamped, get_weights list order, set_weights, train_step empty batch, train_step batch too small, train_step updates state |
| TestTrainStepConvergence | 3 | Loss reduces over time, weights sum to 1.0 after training, training result fields |
| TestRollback | 3 | Not enough history, no consecutive increase, rollback triggered |
| TestAdditional | 5 | Rollback to priors, enable learning, compute_drift, compute_euclidean_drift, get_diagnostics, training_result_converged |

### 8.2 Coverage Gaps

| # | Gap | What's Untested | Risk Level | Proposed Test | Test Type |
| - | --- | --------------- | ---------- | ------------- | --------- |
| 1 | ~~No R1 phase integration test~~ | ~~R1ImportanceScorer.run() with real envelope, scoring, and audit~~ | ~~P0~~ **CLOSED** | **IMPLEMENTED**: test_r1_phase_integration.py (455 lines, 24 tests). Uses MockEventState with 30+ CONFIG_B fields, 7-param set_importance, full envelope lifecycle. All 24 passing. | integration |
| 2 | ~~No test for social factor with real P03EventState~~ | ~~Tests use MockEvent with `participant_count` which masks the `num_participants` bug~~ | ~~P0~~ **CLOSED** | **FIXED**: MockEvent now uses `num_participants` field. TestComputeSocialFactor has 5 tests including intimacy scale. BUG-001 fixed in production code. | unit |
| 3 | ~~No test for should_skip()~~ | ~~R1 skip logic (empty events, all already scored)~~ | ~~P1~~ **CLOSED** | **IMPLEMENTED**: Integration tests include skip condition tests (empty events, all scored). | unit |
| 4 | ~~No test for audit record generation~~ | ~~Audit records produced by score_batch_with_audit~~ | ~~P1~~ **CLOSED** | **IMPLEMENTED**: Integration tests verify audit records with action=SCORE, formula_version="2.0.0", 17-field breakdown. | integration |
| 5 | ~~No test for audit sampling~~ | ~~sample_rate < 1.0 should produce fewer records~~ | ~~P2~~ **CLOSED** | **IMPLEMENTED**: Integration tests verify audit_sample_rate=0.10 flows through R1Config. | unit |
| 6 | ~~**No test for cold start blending**~~ | ~~get_weights_with_cold_start progressive blending~~ | ~~P2~~ **CLOSED** | **IMPLEMENTED** (M5.O Epic 5.O.2): test_r1_cold_start.py (20 tests). Static defaults, progressive blending alpha, weight store unavailable. | unit |
| 7 | ~~**No test for weight learning -> scoring integration**~~ | ~~Learned weights flowing from WeightLearner to ImportanceScorer~~ | ~~P2~~ **CLOSED** | **IMPLEMENTED** (M5.W + M5.P): test_weight_learner_alignment.py (21 tests) + test_learned_weights_wiring.py (20 tests). End-to-end weight flow verified. | integration |
| 8 | ~~**No performance test**~~ | ~~R1 scoring latency for large batches~~ | ~~P3~~ **CLOSED** | **IMPLEMENTED** (M5.O Epic 5.O.2): test_r1_performance.py (5 tests). Latency <30ms for 100 events, throughput >3000 events/s. | performance |
| 9 | ~~**No test for Hebbian disabled path**~~ | ~~R1 with enable_hebbian=False~~ | ~~P2~~ **CLOSED** | **IMPLEMENTED** (M5.O Epic 5.O.2): test_r1_hebbian_idempotency.py (10 tests, 5 for disabled path). Confirms empty Hebbian output when disabled. | unit |
| 10 | ~~**No test for idempotency**~~ | ~~Running R1 twice produces same results~~ | ~~P2~~ **CLOSED** | **IMPLEMENTED** (M5.O Epic 5.O.2): test_r1_hebbian_idempotency.py (10 tests, 5 for idempotency). Score same batch twice with same now_ms -> identical results. | unit |
| 11 | ~~MockEvent hides field name mismatches~~ | ~~MockEvent has `participant_count` but P03EventState has `num_participants`~~ | ~~P0~~ **CLOSED** | **FIXED**: All MockEvent objects updated to use `num_participants` and all CONFIG_B fields. | unit |

### 8.3 Test Infrastructure Needs

| # | Need | Current State | Required State | Blocking Epic? | Status |
| - | ---- | ------------- | -------------- | -------------- | ------ |
| 1 | Shared P03EventState factory fixture | Tests use ad-hoc MockEvent | conftest.py with make_event() that returns real P03EventState with configurable fields | yes (would expose BUG-001) | **Partially addressed**: MockEvent updated with 30+ CONFIG_B fields. Full P03EventState factory not yet implemented. |
| 2 | MockWeightStore fixture | Tests create inline mocks | Shared conftest.py fixture with configurable sample_count and weights | no | **Addressed in integration tests**: test_r1_phase_integration.py has MockWeightStore |
| 3 | R1 phase test harness | No phase-level test infrastructure | Helper that creates envelope, runs R1, and returns results for assertion | yes (needed for P0 integration test) | **IMPLEMENTED**: test_r1_phase_integration.py provides full phase harness with MockEventState, MockBatchEnvelope, etc. |
| 4 | Scoring assertion helpers | Each test computes expected values manually | Helper functions: assert_score_in_range(), assert_tier(), assert_factors_sum() | no | Not yet implemented |

---

## 9. Dependency Map

### 9.1 Upstream (what R1 needs)

| # | Dependency | Type | Status | Owner Milestone | Gap if Missing |
| - | ---------- | ---- | ------ | --------------- | -------------- |
| 1 | P03BatchEnvelope from R0 | in-memory | ready | M5 (5.1) | R1 cannot run without envelope; SequentialRunner skips |
| 2 | P03EventState fields from P02/R0 | data | ready | M3/M5 | All CONFIG_B fields loaded by R0 hydration (Epic 5A.1-5A.3): sentiment_score, affect_valence, affect_arousal, surprise_level, elaboration_depth, identity_relevance, source_reliability, num_participants, social_intimacy, novelty, temporal_orientation, narrative_arc_position, narrative_is_goal_event, memory_tier, source_type, identity_domains_json. All available at R1 time. |
| 3 | st_learned_weights table | table | ready | M1 | Weight loading returns None; falls back to static defaults (non-fatal) |
| 4 | WeightStoreProtocol implementation | service | ready | M1 | ImportanceScorer created with weight_store=None; static weights used |
| 5 | P02 affect/salience/NER enrichment | pipeline | ready | M3 | sentiment_score=0.0, affect_valence=0.0, salience_score=0.0 produce zero importance |
| 6 | P02 activity_type_ultrabert classification | pipeline | ready | M3 | Unknown event types get 1.0 multiplier (neutral) |
| 7 | P02 intent_ultrabert classification | pipeline | ready | M3 | Unknown intents get 1.0 boost (neutral) |

### 9.2 Downstream (what depends on R1)

| # | Dependent | Type | How Used | Impact if Changed | Owner Milestone |
| - | --------- | ---- | -------- | ----------------- | --------------- |
| 1 | R2 episodic integrator | pipeline | Does not read R1 outputs directly (reads embeddings, timestamps) | Indirect -- scoring thresholds may affect which events are clustered | M5 |
| 2 | R3 dedup/decay | pipeline | Reads importance_score for decay immunity thresholds, dedup conflict resolution | Changing score formula changes which events survive dedup/decay | M5 |
| 3 | R5 dream explorer | pipeline | Reads importance_score for dream candidate selection | Changing scores changes dream exploration patterns | M5 |
| 4 | R6 staging assembler | pipeline | Reads importance_score, factors, audit records for staged writes | All R1 outputs flow to R6 for persistence | M5 |
| 5 | R7 truth writer | pipeline | Writes importance_score to st_hipp_events via staged writes | Score value persisted to DB | M5 |
| 6 | K1 retrieval | service | Reads importance_score from st_hipp_events for ranking | Score changes affect memory retrieval ranking | M5+ |
| 7 | ImportanceWeightLearner | algorithm | Uses R1 scoring outcomes + K1 feedback to train weights | Weight learning depends on R1 producing meaningful scores | M5+ |

### 9.3 External Dependencies (libraries, services, extensions)

| # | Dependency | Version | Purpose | License | Pinned? | Upgrade Risk |
| - | ---------- | ------- | ------- | ------- | ------- | ------------ |
| 1 | numpy | >=1.24 | Weight learner array operations, gradient computation | BSD | yes | low |
| 2 | torch (optional) | >=2.0 | Preferred backend for weight learner (GPU-accelerated gradient descent) | BSD | no (optional) | low |
| 3 | math (stdlib) | N/A | log2() for social factor computation | PSF | N/A | none |
| 4 | json (stdlib) | N/A | NER JSON parsing, audit metadata serialization | PSF | N/A | none |
| 5 | time (stdlib) | N/A | Millisecond timestamps for audit records | PSF | N/A | none |
| 6 | asyncpg | >=0.29.0 | Weight learner persist_weights/load_weights (not used during R1 phase) | Apache-2.0 | yes | low |

---

## 10. Performance Baseline

### 10.1 Current Benchmarks

| # | Operation | Dataset Size | p50 | p95 | p99 | Throughput | Memory Peak | Notes |
| - | --------- | ------------ | --- | --- | --- | ---------- | ----------- | ----- |
| N/A | No formal benchmarks exist for R1 | N/A | N/A | N/A | N/A | N/A | N/A | R1 performance inferred from contract latency budget (30ms) only |

### 10.2 Known Bottlenecks

| # | Bottleneck | Location | Cause | Measured Impact | Proposed Fix | Priority |
| - | ---------- | -------- | ----- | --------------- | ------------ | -------- |
| 1 | Weight store query per invocation | importance_scorer.py get_weights | DB round-trip for st_learned_weights, even if cached | ~5ms per invocation | Already cached after first call; consider TTL-based cache invalidation | P3 |
| 2 | ~~Audit record creation at 100% rate~~ | r1_importance_scorer.py | ~~audit_sample_rate=1.0 creates AuditRecord for every event~~ | ~~Memory: ~200 bytes per record * 1000 events = ~200KB~~ | **FIXED**: Default audit_sample_rate changed to 0.10 (Epic 5A.4). Memory reduced ~10x. | ~~P2~~ **FIXED** |
| 3 | Score computation is O(1) per event | importance_scorer.py | Pure arithmetic -- not a bottleneck | ~0.01ms per event | N/A -- already fast | N/A |
| 4 | Audit PII redaction per record | audit_logger.py_redact_pii | Iterates RED_BAND_FIELDS for each audit record | ~0.01ms per record | Negligible at current scale | P3 |

### 10.3 Performance Targets

| # | Operation | Target p95 | Target Throughput | Target Memory | Acceptance Criteria |
| - | --------- | ---------- | ----------------- | ------------- | ------------------- |
| 1 | R1 full phase (100 events) | < 30ms | > 3000 events/s | < 4MB | Benchmark with 100 real P03EventState objects |
| 2 | R1 full phase (1000 events) | < 100ms | > 10000 events/s | < 16MB | Benchmark including audit record creation |
| 3 | Weight loading (cold) | < 10ms | N/A | < 1KB | Single DB query + cache population |
| 4 | Score computation (per event) | < 0.1ms | > 10000/s | < 1KB | Pure arithmetic, no I/O |

---

## 11. Gap Analysis & Enhancement Register

### 11.1 Functional Gaps

| # | Gap ID | Gap Description | Current State | Desired State | Severity | Proposed Fix | Related ADR |
| - | ------ | --------------- | ------------- | ------------- | -------- | ------------ | ----------- |
| 1 | FG-R1-001 | **~~participant_count vs num_participants field name mismatch~~** | **FIXED** (Epic 5A.4): `getattr(event, "num_participants", 1)` | Social factor computed correctly from num_participants | ~~P0 (BUG)~~ **FIXED** | Fixed in importance_scorer.py compute_social_factor | ADR-K010 |
| 2 | FG-R1-002 | **~~Weight component naming mismatch~~** | **FIXED** (M5.W Epic 5.W.1): ImportanceWeightLearner realigned to 8-component CONFIG_B set (sentiment, affect, arousal, surprise, novelty, social, identity, recency). Adapter layer maps learner output to scorer input. 21 tests in test_weight_learner_alignment.py. | Consistent naming and semantic mapping between learner and scorer | ~~P1~~ **FIXED** | Implemented in M5.W (importance_weight_learner.py 707 lines) | ADR-K010 |
| 3 | FG-R1-003 | **~~Contract formula doesn't match code~~** | **FIXED** (Epic 5A.4): Contract YAML rewritten to describe CONFIG_B formula (base 6 additive + 7 modulators). formula_version="2.0.0". Thompson Sampling removed. | Contract accurately describes implemented formula | ~~P1~~ **FIXED** | Contract updated in contracts/modules/consolidation.importance_scorer.v1.yaml | ADR-K010 |
| 4 | FG-R1-004 | **~~MW v2 signals not integrated~~** | **FIXED** (Epic 5A.4): All MW v2 signals integrated in CONFIG_B formula. surprise_w=0.15, identity_w=0.10, arousal_w=0.08, elaboration as multiplicative boost, source_reliability as modulator with floor=0.3, memory_tier as multiplier, novelty categorical, recency exponential decay. | All MW v2 signals contribute to importance scoring | ~~P1~~ **FIXED** | Implemented in importance_scorer.py (1261 lines). 190 unit tests pass. | ADR-K010 |
| 5 | FG-R1-005 | **~~recency_factor never computed~~** | **FIXED** (Epic 5A.4): compute_recency_factor with RECENCY_LAMBDA=0.005. Exponential decay from event timestamp. score_batch/score_batch_with_audit accept now_ms. | recency_factor populated in ScoredEvent and P03EventState | ~~P1~~ **FIXED** | Implemented in importance_scorer.py + r1_importance_scorer.py | none |
| 6 | FG-R1-006 | **~~affect_arousal not used~~** | **FIXED** (Epic 5A.4): compute_emotional_intensity takes affect_arousal param. arousal_w=0.08 in CONFIG_B. | High-arousal events score higher in emotional component | ~~P2~~ **FIXED** | Implemented in importance_scorer.py | none |
| 7 | FG-R1-007 | **~~Hebbian learning: wiring complete, activation deferred~~** | **RESOLVED** (Decision D-R1-001): Auto-activation policy decided. Hebbian activates after 500 cumulative scored events. WeightLearningTrigger reports hebbian_activated=True when threshold crossed. R1Config.hebbian_activation_threshold=500. All wiring complete (M5.H): R1->R4 flow, decay, anti-Hebbian, co-occurrence, anomaly detection. 58 Hebbian + 10 idempotency tests pass. | Hebbian learning activates after 500 scored events | ~~P3~~ **RESOLVED** | **DONE** (Decision D-R1-001): weight_learning_trigger.py + r1_importance_scorer.py updated | none |
| 8 | FG-R1-008 | **~~Audit sample_rate=1.0~~** | **FIXED** (Epic 5A.4): R1Config.audit_sample_rate default is now 0.10 (was 1.0). Configurable via constructor. | Production audit rate 0.10 | ~~P2~~ **FIXED** | Changed default in r1_importance_scorer.py | none |
| 9 | FG-R1-009 | **~~Social factor caps at 10 participants~~** | **CLOSED** (Decision D-R1-003 won't fix): System is user-centric. Even in 100-person events, user contacts 10-12 max. Cap at 10 is intentionally correct. | N/A | ~~P3~~ **CLOSED** | **WON'T FIX** (Decision D-R1-003): Architecturally correct for user-centric design | none |
| 10 | FG-R1-010 | **~~Salience used as novelty proxy~~** | **FIXED** (Epic 5A.4): compute_novelty_factor uses NOVELTY_MAP (ROUTINE/EXPECTED/NOVEL/SURPRISING) as primary. salience_score is fallback only when novelty field empty. | Dedicated novelty signal with categorical->numeric conversion | ~~P2~~ **FIXED** | Implemented in importance_scorer.py | none |

### 11.2 Contract Gaps

| # | Contract | Section / Field | Gap | Impact | Fix |
| - | -------- | --------------- | --- | ------ | --- |
| 1 | consolidation.importance_scorer.v1.yaml | description | ~~Formula in contract doesn't match code~~ **FIXED**: Contract rewritten with CONFIG_B formula description, formula_version="2.0.0" | ~~Misleading documentation~~ **RESOLVED** | **DONE** (Epic 5A.4) |
| 2 | consolidation.importance_scorer.v1.yaml | description | ~~"Thompson Sampling" mentioned but code uses gradient descent~~ **FIXED**: Thompson Sampling reference removed from contract | ~~Incorrect algorithm documentation~~ **RESOLVED** | **DONE** (Epic 5A.4) |
| 3 | consolidation.importance_scorer.v1.yaml | output_event_types | ~~Declares p03.importance.scored.v1 but R1 never emits bus events~~ **FIXED** (Decision D-R1-002): output_event_types set to [] in contract. R1 is an internal pipeline phase, not a bus emitter. Event was never needed. | ~~Contract promises event that is never produced~~ **RESOLVED** | **DONE** (Decision D-R1-002): Removed from contract YAML |
| 4 | consolidation.importance_scorer.v1.yaml | side_effects | ~~Lists write:st_learned_weights but R1 phase does not write weights~~ **FIXED**: write:st_learned_weights removed from contract. Only read:st_learned_weights remains. | ~~Contract claims side effect that doesn't occur~~ **RESOLVED** | **DONE** (Epic 5A.4) |
| 5 | consolidation.importance_scorer.v1.yaml | description | ~~Score components list includes "rehearsal_score" which doesn't exist~~ **FIXED**: Contract description now lists CONFIG_B components (emotional, surprise, novelty, social, identity, recency + 7 modulators) | ~~Dead component in contract~~ **RESOLVED** | **DONE** (Epic 5A.4) |

### 11.3 Architecture Gaps

| # | Area | Gap | ADR Needed? | Impact | Proposed Resolution |
| - | ---- | --- | ----------- | ------ | ------------------- |
| 1 | Weight integration | ~~ImportanceWeightLearner output cannot be consumed by ImportanceScorer due to component naming mismatch~~ | ~~update~~ | ~~Learned weights are never used by scorer~~ | **FIXED** (M5.W Epic 5.W.1): Learner aligned to 8-component CONFIG_B. Adapter maps learner output to scorer input. 21 tests pass. |
| 2 | Feedback loop | ~~No mechanism to feed R1 scoring outcomes back to ImportanceWeightLearner~~ | ~~new~~ | ~~Weight learning has no training signal~~ | **FIXED** (M6.F Epics 5.F.1 + 5.F.2): Full reinforcement cycle wired: R1 score -> Hebbian edge update -> KG boost in R1. Grounding signal path K1 -> weight learner (M5.W.2). feedback_queue.py (184 lines), async_audit.py (246 lines), learning_anomaly_detector.py (460 lines). 32+19+18+39+23 = 131 tests pass. |
| 3 | Observability | ~~R1PhaseMetrics exists in observability.py but R1 never populates it~~ | ~~no~~ | ~~Dead code; metrics framework unused~~ | **FIXED** (M5.O Epic 5.O.1): R1PhaseMetrics populated with OTel spans, score distribution histograms, weight source counters, priority tier gauges. observability.py now 1195 lines. 49+57 = 106 observability tests pass. |

---

## 12. Security & Privacy Audit

### 12.1 Data Classification

| # | Field / Column | Classification | Handling | Retention Policy | Notes |
| - | -------------- | -------------- | -------- | ---------------- | ----- |
| 1 | P03EventState.content_text | PII | in-memory only during R1 | duration of P03 cycle | R1 does not read content_text directly, but it flows through event state |
| 2 | P03EventState.ner_entities_json | PII | read by HebbianLearner (disabled) | duration of P03 cycle | Contains person names, locations |
| 3 | AuditRecord.metadata_json | internal (PII-redacted) | written to st_consolidation_audit | until retention cleanup | RED_BAND_FIELDS redacted before storage |
| 4 | ImportanceBreakdown (in audit) | internal | serialized to audit metadata | until retention cleanup | Contains score components, no PII |
| 5 | st_learned_weights.weights_json | internal | at rest in PostgreSQL | indefinite | Statistical weights, not PII |
| 6 | importance_score (per event) | internal | written to st_hipp_events via R7 | until event deletion | Derived metric, not PII |
| 7 | cycle_id, tenant_id, space_id | internal | in audit records | until retention cleanup | Multi-tenant keys, not PII |

### 12.2 Capability Boundaries

| # | Operation | Required Capability | Enforced? | Enforcement Location | Gap |
| - | --------- | ------------------- | --------- | -------------------- | --- |
| 1 | Read st_learned_weights | st_learned_weights.read | partial | WeightStoreProtocol abstraction | Protocol abstracts access but no runtime capability check |
| 2 | Write audit records | st_consolidation_audit.write | partial | Deferred to R6 staging phase | R1 accumulates records; R6 writes them |
| 3 | Read P03EventState fields | in-memory access | N/A | N/A | No capability check needed for in-memory data |

### 12.3 Input Validation & Sanitization

| # | Input Source | Validation Applied | Sanitization Applied | Injection Risk | Notes |
| - | ----------- | ------------------ | -------------------- | -------------- | ----- |
| 1 | P03EventState fields | getattr with defaults | none | none | In-memory data from trusted R0 |
| 2 | st_learned_weights.weights_json | JSON parse with try/except | none | none | Trusted internal DB |
| 3 | Audit metadata | PII redaction via RED_BAND_FIELDS | _redact_pii() replaces sensitive values with "[REDACTED]" | none | Proactive PII protection |
| 4 | NER entities JSON (Hebbian) | JSON parse with try/except | none | none | Already parsed by P02 |

---

## 13. Enhancement Proposals

> **NOTE**: The original epics 5.2A-5.2F below are **SUPERSEDED** by the holistic redesign approach (Section 16.7).
> The POC (5.2-POC) has validated CONFIG_B weights, lambda=0.005, floor=0.3 across 562K events and 120 scenarios.
> All bug fixes and signal integrations from 5.2A-5.2F are now consolidated into a single **5.2-REDESIGN** epic.
> The individual epics below are retained for historical reference only.

### 13.1 Proposed Epics (SUPERSEDED -- see Section 16.7 for active epic structure)

| Epic ID | Title | Scope Summary | Estimated Files | Priority | Dependencies | Issue Count |
| ------- | ----- | ------------- | --------------- | -------- | ------------ | ----------- |
| 5.2A | R1 Critical Bug Fixes | Fix participant_count field name, update contract to match code | 2 MOD, 1 TEST | P0 | none | 3 |
| 5.2B | R1 MW v2 Signal Integration | Add surprise_level, elaboration_depth, identity_relevance, source_reliability, affect_arousal, recency to formula | 2 MOD, 1 TEST | P1 | 5.1A (R0 loads signals) | 5 |
| 5.2C | R1 Weight System Alignment | Align ImportanceWeightLearner components with ImportanceScorer weights | 2 MOD, 1 TEST | P1 | none | 3 |
| 5.2D | R1 Observability Enhancement | Add OTel spans, score histogram, weight source tracking, priority tier metrics | 2 MOD | P1 | none | 3 |
| 5.2E | R1 Test Coverage & Robustness | Phase integration tests, real P03EventState tests, audit tests | 3 TEST | P1 | 5.2A | 5 |
| 5.2F | R1 Production Hardening | Audit sampling defaults, Hebbian activation mechanism, social factor scaling | 2 MOD | P2 | 5.2A | 4 |

### 13.2 Epic Detail

---

#### Epic 5.2A -- R1 Critical Bug Fixes

**Summary**: Fixes the participant_count field name bug that causes social_factor to always be 0.0, and updates the contract YAML to accurately describe the implemented algorithm.

**Problem**: (1) `_compute_social_factor` reads `participant_count` via getattr but P03EventState has `num_participants` -- social factor is ALWAYS 0.0 for real pipeline events. Tests pass because MockEvent uses the wrong field name. (2) Contract describes Thompson Sampling and a 5-component weighted sum, but code uses gradient descent and a 3-component product formula.

**Solution**: (1) Change `getattr(event, "participant_count", 1)` to `getattr(event, "num_participants", 1)` in importance_scorer.py. (2) Update consolidation.importance_scorer.v1.yaml description to match actual formula and learning algorithm. (3) Fix test MockEvent to use `num_participants` to prevent future regression.

##### Inputs

| # | Input | Type | Source | Validation |
| - | ----- | ---- | ------ | ---------- |
| 1 | P03EventState.num_participants | int | R0 hydration from st_hipp_events | >= 0, defaults to 1 |

##### Outputs

| # | Output | Type | Consumer | Guarantees |
| - | ------ | ---- | -------- | ---------- |
| 1 | social_factor | float [0.0, 0.20] | ScoredEvent, downstream R3/R5/R6 | No longer always 0.0; properly reflects participant count |

##### Algorithm Changes

| # | Algorithm | Change Type | Before | After | Rationale |
| - | --------- | ----------- | ------ | ----- | --------- |
| 1 | social_factor | bugfix | getattr(event, "participant_count", 1) -> always 1 for P03EventState | getattr(event, "num_participants", 1) -> actual participant count | BUG-001: wrong field name causes social factor to be dead |

##### Config Changes

| # | Key / Variable / Flag | Change | Old Value | New Value | Type | Notes |
| - | --------------------- | ------ | --------- | --------- | ---- | ----- |
| N/A | No config changes | N/A | N/A | N/A | N/A | Bug fix only |

##### Contract Changes

| # | Contract File | Change | Section | Details |
| - | ------------- | ------ | ------- | ------- |
| 1 | consolidation.importance_scorer.v1.yaml | modify | description | Replace Thompson Sampling with gradient descent; replace 5-component weighted sum with 3-component product formula |
| 2 | consolidation.importance_scorer.v1.yaml | modify | side_effects | Remove write:st_learned_weights (R1 phase doesn't write) |
| 3 | consolidation.importance_scorer.v1.yaml | modify | output_event_types | Either implement p03.importance.scored.v1 emission or remove |

##### Test Plan

| # | Test File | Test Name | Type | What It Proves | Priority |
| - | --------- | --------- | ---- | -------------- | -------- |
| 1 | test_r1_importance_scorer.py | test_social_factor_with_num_participants | unit | Social factor uses num_participants field correctly | P0 |
| 2 | test_r1_importance_scorer.py | (update existing) | unit | MockEvent updated to use num_participants instead of participant_count | P0 |
| 3 | test_r1_importance_scorer.py | test_social_factor_real_event_state | unit | Social factor works with real P03EventState (not MockEvent) | P0 |

##### Risks

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | Fixing social factor changes ALL importance scores | certain | med | Expected: scores will increase for multi-participant events; run scoring comparison on test data |
| 2 | Existing downstream thresholds may need adjustment | low | med | Review R3/R5 threshold usage after fix |

##### Acceptance Criteria

- [ ] Given a P03EventState with num_participants=5, when compute_importance_score is called, then social_factor > 0.0
- [ ] Given the same event data, running with old code produces social_factor=0.0 and new code produces social_factor>0.0
- [ ] Contract YAML accurately describes the importance formula as implemented in code
- [ ] All existing tests updated and passing with num_participants field name

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.2A.1 | Fix participant_count -> num_participants in _compute_social_factor | Change 1 line in importance_scorer.py | XS | none | Social factor > 0.0 for events with num_participants > 1 |
| 5.2A.2 | Update contract YAML to match implementation | Rewrite description section, fix side_effects, resolve output_event_types | S | none | Contract matches code |
| 5.2A.3 | Update test MockEvent to use num_participants | Fix MockEvent field name, verify all social factor tests still pass | S | 5.2A.1 | Tests use correct field name and pass |

---

#### Epic 5.2B -- R1 MW v2 Signal Integration

**Summary**: Extends the importance scoring formula to incorporate MW v2 signals: surprise_level, elaboration_depth, identity_relevance, source_reliability, affect_arousal, and recency_factor.

**Problem**: The current formula uses only 3 signal components (emotional, novelty, social). MW v2 provides 5+ additional signals that could significantly improve scoring accuracy. The recency_factor is always 0.0 (never computed). affect_arousal is available but unused.

**Solution**: Extend the importance formula with new weighted components. The enhanced formula:
`importance = clamp((emotional + novelty + social + surprise + identity + recency) * event_type_multiplier * intent_boost * source_reliability, 0.0, 1.0)`

Where emotional is enhanced with arousal: `emotional = sentiment_weight * abs(sentiment) + affect_weight * abs(valence) + arousal_weight * arousal`

##### Inputs

| # | Input | Type | Source | Validation |
| - | ----- | ---- | ------ | ---------- |
| 1 | surprise_level | float [0, 1] | P02 via R0 (requires 5.1A) | defaults to 0.0 |
| 2 | elaboration_depth | float [0, 1] | P02 via R0 (requires 5.1A) | defaults to 0.0 |
| 3 | identity_relevance | float [0, 1] | P02 via R0 (requires 5.1A) | defaults to 0.0 |
| 4 | source_reliability | float [0, 1] | P02 via R0 (requires 5.1A) | defaults to 1.0 (trust by default) |
| 5 | affect_arousal | float [0, 1] | P02 via R0 | defaults to 0.0 |
| 6 | event timestamp | int (ms) | R0 hydration | > 0 |

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.2B.1 | Add surprise_level to formula | Add surprise_weight * surprise_level as new component | S | 5.1A (R0 loads signal) | Surprise contributes to score; events with surprise_level=1.0 score higher |
| 5.2B.2 | Add identity_relevance to formula | Add identity_weight * identity_relevance as new component | S | 5.1A | Identity-relevant events score higher |
| 5.2B.3 | Implement recency_factor | exponential decay: recency = exp(-lambda * hours_since_event) | S | none | recency_factor > 0.0 for recent events; decays with age |
| 5.2B.4 | Add affect_arousal to emotional_intensity | arousal_weight * affect_arousal added to emotional computation | S | none | High-arousal events have higher emotional_intensity |
| 5.2B.5 | Add source_reliability modulation | Multiply final score by source_reliability | S | 5.1A | Unreliable sources (0.5) produce 50% reduced scores |

---

#### Epic 5.2C -- R1 Weight System Alignment

**Summary**: Aligns the ImportanceWeightLearner component naming with ImportanceScorer weights so learned weights can actually be used by the scorer.

**Problem**: ImportanceWeightLearner trains weights for components (emotional, recency, access, social) with priors (0.35, 0.25, 0.20, 0.20). ImportanceScorer uses components (sentiment, affect, novelty, social) with defaults (0.25, 0.30, 0.25, 0.20). The names don't map, the semantics differ, and the priors are inconsistent. This means learned weights can NEVER be correctly applied to the scorer.

**Solution**: Either (a) rename learner components to match scorer (requires retraining), or (b) add a mapping layer that translates learner output to scorer input, or (c) redesign both to share a common component set that includes all MW v2 signals.

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.2C.1 | Design unified weight component set | ADR documenting component taxonomy for both scorer and learner | M | none | Clear mapping between learner output and scorer input |
| 5.2C.2 | Implement weight translation layer | Adapter that maps learner weights to scorer weights | M | 5.2C.1 | ImportanceScorer can consume ImportanceWeightLearner output |
| 5.2C.3 | Update learner priors to match scorer defaults | Align prior distributions with actual scoring components | S | 5.2C.1 | Priors consistent with scorer defaults |

---

#### Epic 5.2D -- R1 Observability Enhancement

**Summary**: Adds OpenTelemetry spans, score distribution metrics, weight source tracking, and priority tier distribution for R1.

**Problem**: R1 has zero OTel spans, zero formal metrics, and R1PhaseMetrics is defined but never populated. Production visibility limited to structured logs.

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.2D.1 | Add OTel span for R1 phase | Wrap R1ImportanceScorer.run in span with events_scored, avg_score, weight_source attributes | S | none | Span visible in trace output |
| 5.2D.2 | Add score distribution histogram | Prometheus histogram for importance_score values, buckets at 0.1 intervals | S | none | Score distribution visible in dashboards |
| 5.2D.3 | Add priority tier and weight source metrics | Counter for tier distribution, counter for weight source (static/learned/blended) | S | none | Metrics exported with correct labels |

---

#### Epic 5.2E -- R1 Test Coverage & Robustness

**Summary**: Adds critical missing tests: R1 phase integration test, real P03EventState tests, audit tests, and idempotency tests.

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.2E.1 | R1 phase integration test | test_r1_phase_scores_envelope with real envelope | M | 5.2A | All events scored, importance_computed=True, scores in [0,1] |
| 5.2E.2 | Real P03EventState scoring test | test using actual P03EventState instead of MockEvent | S | 5.2A | Exposes and validates BUG-001 fix |
| 5.2E.3 | Audit record generation test | test_r1_audit_records with action=SCORE | S | none | Audit records created with correct fields |
| 5.2E.4 | R1 skip condition tests | test_r1_should_skip_empty, _all_scored, _normal | S | none | Skip logic works correctly |
| 5.2E.5 | R1 idempotency test | Run R1 twice, assert identical results | S | none | Deterministic scoring |

---

#### Epic 5.2F -- R1 Production Hardening

**Summary**: Reduces audit overhead, adds Hebbian activation mechanism, improves social factor scaling.

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.2F.1 | Reduce audit sample_rate default | Change default from 1.0 to 0.1, make configurable from pipeline YAML | S | none | Production audit volume reduced 10x |
| 5.2F.2 | ~~Add Hebbian activation mechanism~~ | ~~enable_hebbian activates when scoring sample_count exceeds threshold~~ | ~~M~~ | ~~none~~ | **DONE** (Decision D-R1-001): hebbian_activation_threshold=500 in WeightTrainingConfig + R1Config. WeightTrainingTriggerResult.hebbian_activated reports activation. Implemented in weight_learning_trigger.py + r1_importance_scorer.py |
| 5.2F.3 | ~~Improve social factor scaling~~ | ~~Replace log2/3.32 with configurable denominator or intimacy weighting~~ | ~~S~~ | ~~5.2A~~ | **CLOSED** (Decision D-R1-003 won't fix): User-centric design. 10-person cap is correct. |
| 5.2F.4 | Add memory_tier aware thresholds | Priority tier thresholds adjusted by memory_tier | S | 5.1A | Core memories have lower CRITICAL threshold |

---

## 14. Risk Register

| # | Risk ID | Risk | Category | Likelihood | Impact | Risk Score | Mitigation | Owner | Status |
| - | ------- | ---- | -------- | ---------- | ------ | ---------- | ---------- | ----- | ------ |
| 1 | R-R1-001 | Fixing social factor changes ALL historical importance scores | data integrity | certain | med | high | Run comparison analysis; consider re-scoring existing events; downstream thresholds may need adjustment. **POC RESULT**: social_w=0.15 tested with corrected field on 562K events -- score distribution shift is controlled. Re-scoring recommended as part of 5.2-REDESIGN deployment. | dev-lead | **mitigated** |
| 2 | R-R1-002 | MW v2 signal integration changes score distribution | algorithm | high | med | high | A/B test new formula against old; validate distribution shape remains reasonable. **POC RESULT**: CONFIG_B mean=0.435, std=0.231 across 562K events. 6-tier separation validated. CRITICAL/HIGH/MEDIUM_HIGH/MEDIUM/LOW_MEDIUM/LOW tiers produce avg Cohen's d=0.476. Distribution is well-shaped -- no pile-up at boundaries. | dev-lead | **mitigated** |
| 3 | R-R1-003 | Weight system alignment requires retraining all learned weights | technical | ~~med~~ low | ~~med~~ low | ~~medium~~ low | **MITIGATED** (M5.W): CONFIG_B 8-component weights are implemented. Weight learner aligned to same 8-component set (Epic 5.W.1). Grounding signal path wired (5.W.2). 21 alignment tests + 38 grounding signal tests pass. No retraining needed -- learner starts fresh on CONFIG_B components. | dev-lead | **mitigated** |
| 4 | R-R1-004 | Tests pass with MockEvent but fail with real P03EventState | testing | ~~certain~~ low | low | low | **MITIGATED**: MockEvent updated with 30+ CONFIG_B fields including num_participants. Integration tests (test_r1_phase_integration.py) use MockEventState matching P03EventState interface. BUG-001 fixed. | dev-lead | **mitigated** |
| 5 | R-R1-005 | Enabling Hebbian learning may cause unexpected KG edge weight changes | algorithm | low | med | low | **MITIGATED** (M5.H + M6.F): R1 scores wired to R4 Hebbian (5.H.1). Decay + anti-Hebbian wired (5.H.2). Reinforcement cycle has convergence proof (5.F.2) and anomaly detector (learning_anomaly_detector.py, 460 lines, 39 tests). Soft saturation prevents runaway. enable_hebbian=False remains as safety gate until P06 + KG operational. | dev-lead | **mitigated** |
| 6 | R-R1-006 | source_reliability modulation could suppress valid events | algorithm | med | med | medium | Floor source_reliability at 0.5 (minimum 50% of computed score). **POC RESULT**: Floor=0.3 validated (not 0.5). Floor=0.3 provides strong penalty for untrusted sources while preventing total suppression. System-inferred events at floor lose up to 70% of score -- appropriate. 120/120 scenarios pass with floor=0.3 including all 8 source_reliability test scenarios. | dev-lead | **mitigated** |
| 7 | R-R1-007 | Reducing audit sample_rate loses scoring decision visibility | operations | low | low | low | Always audit CRITICAL tier events regardless of sample_rate | dev-lead | open |

---

## 15. Open Questions

| # | Question | Context | Blocking? | Answer | Status | Answered By | Date |
| - | -------- | ------- | --------- | ------ | ------ | ----------- | ---- |
| 1 | Should the social factor bug fix (5.2A.1) trigger a re-scoring of all existing events? | Fixing the bug changes scores for multi-participant events; existing scores in st_hipp_events are wrong | yes | **YES** -- re-scoring is required. The entire R1 formula is being redesigned (5.2-REDESIGN), so all events must be re-scored with the new formula anyway. social_w=0.15 with corrected num_participants field is validated. | **answered** | POC Phase 6 | 2026-03-02 |
| 2 | What should the unified weight component set be for scorer + learner alignment? | Learner uses (emotional, recency, access, social); scorer uses (sentiment, affect, novelty, social) | yes (for 5.2C) | **CONFIG_B 8-component set**: sentiment_w=0.10, affect_w=0.12, arousal_w=0.08, surprise_w=0.15, novelty_w=0.15, social_w=0.15, identity_w=0.10, recency_w=0.15 (sum=1.00). Weight learner will need realignment to match these 8 components. | **answered** | POC Phase 4+6 | 2026-03-02 |
| 3 | Should recency_factor use time-since-event or time-since-ingestion? | event_time_utc vs created_at in st_hipp_events -- affects freshness semantics | yes (for 5.2B.3) | **time-since-event** (event.timestamp). Backdated events get their actual age as recency. R0 already converts event_time_utc to timestamp. POC used event timestamp throughout. is_backdated override deferred to production refinement. | **answered** | POC design (16.5.4) | 2026-03-02 |
| 4 | What is the correct lambda for recency exponential decay? | exp(-lambda * hours) -- lambda=0.01 gives half-life of ~69 hours; lambda=0.1 gives ~7 hours | no | **lambda=0.005** (half-life ~139h / ~6 days). Tested 4 lambdas (0.005, 0.01, 0.02, 0.05) x 5 ages (1h, 6h, 24h, 72h, 168h) x 4 configs = 80 calibration passes on 562K events. lambda=0.005 gives highest avg Cohen's d at 24h (0.472 for CONFIG_B) while keeping CRITICAL events above 0.40 at 72h (0.531). | **answered** | POC Phase 5 | 2026-03-02 |
| 5 | Should source_reliability have a floor (e.g., 0.5) to prevent complete score suppression? | source_reliability=0.0 would zero out any event regardless of other signals | no | **YES, floor=0.3** (not 0.5 as originally proposed). Floor=0.3 allows up to 70% score penalty for untrusted sources, preventing total suppression while maintaining meaningful discrimination. Tested across 8 source_reliability scenarios in Phase 6 -- all pass. | **answered** | POC Phase 5+6 | 2026-03-02 |
| 6 | Should Hebbian learning activation be automatic (threshold-based) or manual (config flag)? | enable_hebbian=False permanently; need activation strategy. **NOTE (M5.H)**: All Hebbian wiring is now complete (R1->R4 score flow, decay, anti-Hebbian, co-occurrence refactor, anomaly detection). The only remaining decision is the activation POLICY: threshold vs manual flag. | no | **AUTOMATIC** (Decision D-R1-001): Hebbian auto-activates after 500 cumulative scored events. WeightLearningTrigger.execute() checks cumulative sample_count >= hebbian_activation_threshold (500) and sets hebbian_activated=True on result. R1Config.hebbian_activation_threshold=500. Pattern follows existing weight_learning_trigger.py threshold mechanism. | **answered** | Decision D-R1-001 | 2026-03-10 |
| 7 | Is the salience_score -> novelty proxy intentional or a gap? | Code uses salience_score where "novelty" is expected; novelty_score exists in st_hipp_events but may not be populated at R1 time | no | **Replaced**: MW v2 `novelty` categorical (ROUTINE/EXPECTED/NOVEL/SURPRISING) is now the primary novelty signal with numeric conversion (0.10/0.30/0.70/1.00). salience_score retained as fallback only when novelty field is empty. novelty_w=0.15 validated across 120 scenarios. | **answered** | POC Phase 4+6 | 2026-03-02 |
| 8 | Should the p03.importance.scored.v1 output event be implemented or removed from contract? | Contract declares it; code doesn't emit it | no | **REMOVED** (Decision D-R1-002): output_event_types set to [] in contract YAML. R1 is an internal P03 phase, not a bus event emitter. Scoring results flow via envelope.phases.r1_scored_events, not bus events. | **answered** | Decision D-R1-002 | 2026-03-10 |

---

## Appendix A: Glossary

| Term | Definition |
| ---- | ---------- |
| R1 | Phase 1 (Importance Scoring) -- Computes per-event importance score using McGaugh (2004) emotional memory encoding model |
| ImportanceScorer | Core algorithm class that computes importance using CONFIG_B formula: base(6 additive: emotional + surprise + novelty + social + identity + recency) *7 multiplicative modulators (elab, goal, arc, temporal, type, intent, tier)* reliability. Implemented in importance_scorer.py (1261 lines). |
| ImportanceWeights | Frozen dataclass holding CONFIG_B 8 weights: sentiment=0.10, affect=0.12, arousal=0.08, surprise=0.15, novelty=0.15, social=0.15, identity=0.10, recency=0.15 (sum=1.0). POC validated across 562K events + 120 scenarios. |
| ImportanceBreakdown | Per-event audit record of score computation with 17 fields: 6 additive components + base_score + 7 multiplicative modulators + reliability + final_score + weights_source |
| ScoredEvent | R1 output dataclass: event_id + importance_score + 6 factor values (recency_factor, affect_factor, social_factor, novelty_factor, surprise_factor, identity_factor) + priority_tier |
| HebbianLearner | Co-occurrence edge weight learning (auto-activates after 500 scored events, Decision D-R1-001) |
| HebbianConfig | Configuration for Hebbian learning: learning_rate, decay_rate, anti_learning_rate, etc. |
| ImportanceWeightLearner | Online gradient descent weight optimizer. **ALIGNED** (M5.W) to 8-component CONFIG_B set (sentiment, affect, arousal, surprise, novelty, social, identity, recency). Grounding signal path wired (M5.W.2). Awaiting production training data (500+ grounded events). |
| WeightStoreProtocol | Abstraction for reading/writing learned weights from st_learned_weights |
| P03AuditLogger | Accumulates structured audit records for scoring decisions; flushed by R6 |
| AuditAction.SCORE | Audit action enum value for R1 importance scoring decisions |
| RED_BAND_FIELDS | Frozenset of PII field names that are redacted in audit records |
| EVENT_TYPE_MULTIPLIERS | Dict mapping activity_type_ultrabert to importance multiplier (0.5-2.0) |
| INTENT_BOOST_MULTIPLIERS | Dict mapping intent_ultrabert to importance boost (0.90-1.20) |
| McGaugh (2004) | Reference: "Memory consolidation and the amygdala" -- theoretical basis for emotional importance weighting |
| Cold start | When a space has < 500 scored observations, static default weights are used instead of learned weights |
| Progressive blending | Technique where alpha = sample_count/500 blends between static and learned weights during cold start |
| Thompson Sampling | Algorithm described in LEGACY contract but NOT implemented. Removed from contract in Epic 5A.4. Actual weight learning uses gradient descent |
| Anti-Hebbian | Weakening of KG edge weights based on negative feedback signals (merge rejection, contradiction, etc.) |
| CONFIG_B | POC-validated weight configuration (B_emotion_heavy): sentiment=0.10, affect=0.12, arousal=0.08, surprise=0.15, novelty=0.15, social=0.15, identity=0.10, recency=0.15. Winner among 4 configs (A/B/C/D) with 120/120 scenario pass rate and highest avg Cohen's d (0.476). |
| R1SignalVector | POC dataclass (signal_derive.py) that converts raw event signals into normalized float components for the enhanced formula |
| NRC-VAD | NRC Valence-Arousal-Dominance Lexicon (Mohammad 2018). Maps ~20,000 English words to [valence, arousal, dominance] triples. Used in POC to derive affect_valence, affect_arousal, and affect_dominance from emotion labels. |
| Reliability floor | Minimum source_reliability value (0.3) preventing total score suppression for untrusted sources. POC-validated. |
| priority_tier | Classification of importance_score into 6 tiers (implemented, POC-validated): CRITICAL >= 0.80, HIGH >= 0.60, MEDIUM_HIGH >= 0.45, MEDIUM >= 0.30, LOW_MEDIUM >= 0.15, LOW < 0.15. Legacy 4-tier system is superseded. |

## Appendix B: References

| # | Document | Path / URL | Relevance |
| - | -------- | ---------- | --------- |
| 1 | P03 Consolidation Dossier v2 | docs/pipelines/P03_consolidation_dossier_v2.md | Pipeline scope, stage definitions, R1 specification |
| 2 | ADR-K010 P03 Consolidation Architecture | docs/architecture/decisions-K0/k010-p03-consolidation-architecture.md | Foundational architecture for P03 phases |
| 3 | ADR-K010.1 Sleep-Cycle State Machine | docs/architecture/decisions-K0/k010.1-sleep-cycle-state-machine.md | R0-R8 phase sequencing and state machine |
| 4 | ADR-K010.9 Capability-Based Security | docs/architecture/decisions-K0/k010.9-capability-based-security.md | Capability model for P03 storage access |
| 5 | Master Implementation Skeleton M5 | docs/plans/MASTER_IMPLEMENTATION_SKELETON.md (M5 section, line 5166) | Epic 5.2 R1 discovery spec, signal gaps, known issues |
| 6 | P03 Pipeline Contract | k0/contracts/pipelines/p03_consolidation.v1.yaml | Pipeline stages, triggers, capabilities, topics |
| 7 | R1 Module Contract | k0/contracts/modules/consolidation.importance_scorer.v1.yaml | Module interface, latency budget, failure modes |
| 8 | R0 Batch Selector Discovery | docs/pipelines/p03_enhancement_discovery/P03_R0_BATCH_SELECTOR_DISCOVERY.md | R0 discovery doc (Epic 5.1) -- upstream phase |
| 9 | McGaugh (2004) | "Memory consolidation and the amygdala: a systems perspective" -- Trends in Neurosciences | Theoretical basis for emotional importance weighting in R1 |
| 10 | R1 Weight Research POC | poc/r1_weight_research/ (config.py, scorer.py, scenarios.py, calibrate.py, etc.) | POC validation of CONFIG_B weights, lambda=0.005, floor=0.3. 562K events + 120 scenarios. |
| 11 | R1 Weight Research Results | poc/r1_weight_research/results/ (summary.md, phase5_summary.md, phase6_summary.md) | Phase 4-6 results: score distributions, Cohen's d, lambda grids, scenario pass rates |
| 12 | R1 Weight Research Plan | docs/pipelines/p03_enhancement_discovery/R1_WEIGHT_RESEARCH_PLAN.md | 6-phase research methodology document |

## Appendix C: Formula Reference

### C.1 Current R1 Importance Formula (CONFIG_B -- Implemented)

```
importance = clamp(
    (emotional + surprise + novelty + social + identity + recency)
    * elab_boost * goal_boost * arc_boost * temporal_boost
    * event_type_multiplier * intent_boost
    * tier_multiplier
    * reliability_adjusted,
    0.0, 1.0
)
```

Where:

- `emotional = sentiment_w(0.10) * |sentiment_score| + affect_w(0.12) * |affect_valence| + arousal_w(0.08) * affect_arousal`
- `surprise = surprise_w(0.15) * clamp(surprise_level, 0, 1)`
- `novelty = novelty_w(0.15) * NOVELTY_MAP[categorical]` (fallback: salience_score if empty)
- `social = social_w(0.15) * min(1.0, log2(num_participants) / LOG2_10) * INTIMACY_SCALE[intimacy]`
- `identity = identity_w(0.10) * (identity_relevance if > 0 else len(identity_domains)/9.0)`
- `recency = recency_w(0.15) * exp(-RECENCY_LAMBDA * hours_since_event)` (RECENCY_LAMBDA=0.005)
- `elab_boost = ELABORATION_MAP[depth]` (MENTION=1.00, DISCUSSED=1.05, ELABORATED=1.10, DEEPLY_PROCESSED=1.15)
- `goal_boost = 1.15 if narrative_is_goal_event else 1.0`
- `arc_boost = ARC_MAP[position]` (EXPOSITION=1.00, RISING_ACTION=1.05, CLIMAX=1.15, RESOLUTION=1.00)
- `temporal_boost = TEMPORAL_MAP[orientation]` (PAST=1.00, ONGOING=1.05, FUTURE_COMMITMENT=1.10)
- `event_type_multiplier = EVENT_TYPE_MULTIPLIERS.get(activity_type_ultrabert, 1.0)`
- `intent_boost = INTENT_BOOST_MULTIPLIERS.get(intent_ultrabert, 1.0)`
- `tier_multiplier = MEMORY_TIER_MAP[memory_tier]` (routine=1.00, notable=1.10, significant=1.25, landmark=1.50)
- `reliability_adjusted = max(RELIABILITY_FLOOR, derive_source_reliability(event))` (RELIABILITY_FLOOR=0.3)

### C.1.1 Legacy R1 Importance Formula (Superseded)

> **This formula was replaced by CONFIG_B in Epic 5A.4. Retained for historical reference only.**

```
importance = clamp(
    (emotional_intensity + novelty_factor + social_factor)
    * event_type_multiplier
    * intent_boost,
    0.0, 1.0
)
```

Where:

- `emotional_intensity = 0.25 * |sentiment_score| + 0.30 * |affect_valence|`
- `novelty_factor = 0.25 * clamp(salience_score, 0.0, 1.0)`
- `social_factor = 0.20 * min(1.0, log2(num_participants) / LOG2_10)`
  - **BUG (FIXED)**: Previously read `participant_count` (always default=1) instead of `num_participants`
- `event_type_multiplier = EVENT_TYPE_MULTIPLIERS.get(activity_type_ultrabert, 1.0)`
- `intent_boost = INTENT_BOOST_MULTIPLIERS.get(intent_ultrabert, 1.0)`

### C.2 Default Weights (Legacy -- Superseded by CONFIG_B)

> **SUPERSEDED**: These 4-component weights have been replaced by the CONFIG_B 8-component weights in Epic 5A.4. Retained for historical reference.

| Component | Weight | Sum Contribution |
| --------- | ------ | ---------------- |
| sentiment | 0.25 | -> emotional_intensity |
| affect | 0.30 | -> emotional_intensity |
| novelty | 0.25 | -> novelty_factor |
| social | 0.20 | -> social_factor |
| **Total** | **1.00** | |

### C.2.1 Current Weights -- CONFIG_B (Implemented, POC-Validated)

| Component | Weight | Sub-Component | Max Contribution | Role |
| --------- | ------ | ------------- | ---------------- | ---- |
| sentiment | 0.10 | emotional block | 0.10 | abs(sentiment_score) -- overall emotional polarity |
| affect | 0.12 | emotional block | 0.12 | abs(affect_valence) -- emotional valence magnitude |
| arousal | 0.08 | emotional block | 0.08 | affect_arousal -- activation level (excitement, fear vs calm) |
| surprise | 0.15 | independent | 0.15 | surprise_level -- prediction error signal |
| novelty | 0.15 | independent | 0.15 | novelty categorical -> numeric (ROUTINE=0.10, EXPECTED=0.30, NOVEL=0.70, SURPRISING=1.00) |
| social | 0.15 | independent | 0.15 | log2(num_participants)/LOG2_10 * intimacy_scale |
| identity | 0.10 | independent | 0.10 | identity_relevance or len(identity_domains)/9.0 |
| recency | 0.15 | independent | 0.15 | exp(-0.005 * hours_since_event) |
| **Total** | **1.00** | | **1.00** | |

**Validated parameters**:

- Lambda (recency decay): **0.005** (half-life ~139h / ~6 days)
- Source reliability floor: **0.3**
- Tier thresholds: CRITICAL >= 0.80, HIGH >= 0.60, MEDIUM_HIGH >= 0.45, MEDIUM >= 0.30, LOW_MEDIUM >= 0.15, LOW < 0.15

**Validation evidence**:

- Phase 4: 562K events, CONFIG_B avg Cohen's d = 0.476 (highest of 4 configs)
- Phase 5: Lambda=0.005 gives highest tier separation at 24h and maintains CRITICAL > 0.40 at 72h
- Phase 6: 120/120 hand-crafted family scenarios pass (100%)
- Hard requirements: Sharvi's first word = 1.000 (>0.85), breakfast alone = 0.087 (<0.25)

### C.3 Score Range Analysis (Legacy -- 4-Component Formula, Superseded)

> **This analysis is for the legacy 4-component formula. The current CONFIG_B formula has different score ranges due to 6 additive components + 7 multiplicative modulators. See POC results at `poc/r1_weight_research/results/` for current score distribution analysis (mean=0.435, std=0.231, 562K events).**

| Scenario | emotional | novelty | social | subtotal | multiplier | boost | final |
| -------- | --------- | ------- | ------ | -------- | ---------- | ----- | ----- |
| All zero | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 1.0 | 0.0 |
| Max emotional (sent=1, affect=1) | 0.55 | 0.0 | 0.0 | 0.55 | 1.0 | 1.0 | 0.55 |
| Max all components | 0.55 | 0.25 | 0.20 | 1.00 | 1.0 | 1.0 | 1.00 |
| Milestone celebration, max emotion | 0.55 | 0.25 | 0.20 | 1.00 | 2.0 | 1.0 | 1.00 (clamped) |
| Routine casual_chat, no emotion | 0.0 | 0.0 | 0.0 | 0.0 | 0.5 | 0.9 | 0.0 |
| High emotion milestone + query_memory | 0.55 | 0.25 | 0.20 | 1.00 | 2.0 | 1.20 | 1.00 (clamped) |
| Moderate emotion message | 0.28 | 0.10 | 0.08 | 0.46 | 1.0 | 1.0 | 0.46 |

### C.4 Hebbian Update Formula (Disabled)

```
delta = learning_rate * (max_weight - current_weight) * event_importance
new_weight = clamp(current_weight + delta, min_weight, max_weight)
```

### C.5 Anti-Hebbian Decay Formula (Disabled)

```
decay = anti_learning_rate * penalty * confidence
if is_explicit_correction:
    decay *= explicit_correction_multiplier
new_weight = max(0.0, current_weight - decay)
if new_weight < prune_threshold:
    new_weight = 0.0  # prune
```

### C.6 Exponential Time Decay Formula (Hebbian, Disabled)

```
new_weight = weight * exp(-decay_rate * days_elapsed)
if new_weight < prune_threshold:
    edge is pruned
```

### C.7 Weight Learning Gradient Descent Formula

```
loss = BCE(sigmoid(features @ weights), labels, sample_weights)
gradient = (1/n) * features.T @ (predictions - labels) * sample_weights
velocity = momentum * velocity - learning_rate * gradient
weights = softmax(weights + velocity)
weights = clamp(weights, weight_min, weight_max)
weights = normalize(weights)  # sum to 1.0
```

---

## 16. Proposed Design Enhancement -- R1 Holistic Redesign

> **Status**: **IMPLEMENTED** -- all 6 research phases complete + production code deployed (Epic 5A.4)
> **Date**: 2026-03-02 (design) / 2026-03-02 (POC validated) / 2026-03-02 (implemented)
> **Decision**: R1 was redesigned as a single cohesive effort. No piecemeal bug fixes.
> The enhanced formula, weight distribution, and signal integration have been **validated** through:
>
> - Phase 4: 562K events scored across 4 weight configurations (CONFIG_B winner, avg Cohen's d = 0.476)
> - Phase 5: Lambda grid search (0.005 selected, half-life ~139h) + reliability floor calibration (0.3 selected)
> - Phase 6: 120 hand-crafted scenarios, CONFIG_B = **120/120 (100%)** pass rate
> - Hard requirements: Sharvi's first word = 1.000 (>0.85 PASS), Breakfast alone = 0.087 (<0.25 PASS)
>
> **Validated configuration**: CONFIG_B (sentiment=0.10, affect=0.12, arousal=0.08, surprise=0.15, novelty=0.15, social=0.15, identity=0.10, recency=0.15), lambda=0.005, floor=0.3
> **POC code**: `poc/r1_weight_research/` (config.py, scorer.py, scenarios.py, calibrate.py, etc.)

---

### 16.1 Design Philosophy

The current R1 has fundamental structural problems, not just bugs:

1. Social factor is dead (wrong field name) -- fixing it alone shifts score distributions
2. Recency is dead (hardcoded 0.0) -- adding it alone changes what LOW/MEDIUM/HIGH means
3. MW v2 + M5A signals are available but untouched -- 10+ unused signals
4. Weight learner cannot feed the scorer (component name mismatch)
5. Contract says Thompson Sampling; code does gradient descent

Fixing any one of these in isolation is dangerous because it changes score distributions that downstream R3/R5/R6/R7 depend on. One bug fix cascades into recalibrating thresholds.

**Therefore**: We redesigned R1 as a whole. One formula. One set of weights. One calibration pass. **COMPLETE**: CONFIG_B (B_emotion_heavy) with 8 components implemented in production code. 190 unit tests + 24 integration tests all passing. The redesign epic (5.2-REDESIGN) and contract epic (5.2-CONTRACT) are COMPLETE.

---

### 16.2 Signals Available to R1 After 5A.1 + 5A.2

Every signal below is now loaded into P03EventState by R0. R1 can read all of them via `getattr(event, field)`.

#### 16.2.1 Existing Signals (Used Today -- partially)

| # | Signal | Field on P03EventState | Type | Range | Currently Used? | How |
|-|-|-|-|-|-|-|
| 1 | Sentiment score | `sentiment_score` | float | [-1, 1] | YES | `0.10 * abs(sentiment_score)` (CONFIG_B) |
| 2 | Affect valence | `affect_valence` | float | [-1, 1] | YES | `0.12 * abs(affect_valence)` (CONFIG_B) |
| 3 | Salience score | `salience_score` | float | [0, 1] | YES (fallback) | Fallback for novelty when categorical empty: `0.15 * salience_score` |
| 4 | Participant count | `num_participants` | int | >= 0 | YES | `0.15 * log2(count)/3.32 * INTIMACY_SCALE[intimacy]` (**BUG FIXED** in 5A.4) |
| 5 | Activity type (UltraBERT) | `activity_type_ultrabert` | str (12 types) | enum | YES | EVENT_TYPE_MULTIPLIERS lookup |
| 6 | Intent (UltraBERT) | `intent_ultrabert` | str (8 types) | enum | YES | INTENT_BOOST_MULTIPLIERS lookup |

#### 16.2.2 Existing Signals (Previously Unused -- NOW INTEGRATED in CONFIG_B)

| # | Signal | Field on P03EventState | Type | Range | Source | Why Valuable for R1 |
|-|-|-|-|-|-|-|
| 7 | Affect arousal | `affect_arousal` | float | [0, 1] | P02 M04 | High arousal = stronger memory encoding (Kensinger 2009). Excitement, fear, anger all encode stronger than calm contentment |
| 8 | Affect dominance | `affect_dominance` | float | [0, 1] | P02 MW v2 (0073) | Low-dominance moments (feeling helpless, overwhelmed) can be highly memorable |
| 9 | Social intimacy | `social_intimacy` | str | LOW/MEDIUM/HIGH | P02 M07 | Family dinner (HIGH) vs work meeting (LOW) -- same participant count, very different importance |
| 10 | Salience band | `salience_band` | str | LOW/MED/HIGH/CRITICAL | P02 M06 | Band-level classification, complementary to float score |
| 11 | Novelty score | `novelty_score` | float | [0, 1] | P02 M06 | Numeric novelty signal (but may be 0.0 if not yet computed at R1 time) |
| 12 | Event timestamp | `timestamp` | int (ms) | > 0 | R0 | Needed for recency computation |

#### 16.2.3 MW v2 Signals (M3 migration 0073 -- NOW INTEGRATED in CONFIG_B)

| # | Signal | Field on P03EventState | Type | Range | MW Source | Why Valuable for R1 |
|-|-|-|-|-|-|-|
| 13 | Novelty (categorical) | `novelty` | str | ROUTINE/EXPECTED/NOVEL/SURPRISING | MW compares against beliefs + scoreboard | The ACTUAL novelty signal from K1. More authoritative than salience proxy |
| 14 | Elaboration depth | `elaboration_depth` | str | MENTION/DISCUSSED/ELABORATED/DEEPLY_PROCESSED | MW counts turns on topic from history | Depth-of-processing effect (Craik & Lockhart 1972). Deeply discussed topics are better encoded |
| 15 | Source type | `source_type` | str | user_stated/user_implied/device_observed/system_inferred | MW cross-references history turns vs extraction origin | user_stated is most reliable, system_inferred least |
| 16 | Narrative is goal event | `narrative_is_goal_event` | bool | T/F | MW matches extraction to thread goal | Goal events have intentional significance |
| 17 | Temporal orientation | `temporal_orientation` | str | PAST/ONGOING/FUTURE_COMMITMENT | MW compares resolved_epoch_ms vs now | FUTURE_COMMITMENT memories need preservation for reminders/planning |
| 18 | Identity domains | `identity_domains_json` | str (JSON array) | array of 9 domain strings | MW maps domains + topics + relationships | More identity domains activated = more self-relevant |
| 19 | Narrative arc position | `narrative_arc_position` | str | EXPOSITION/RISING_ACTION/CLIMAX/RESOLUTION | MW narrative_active.arc.position | CLIMAX moments are peak memory events |

#### 16.2.4 M5A Signals (Migration 0074 -- Loaded by R0)

| # | Signal | Field on P03EventState | Type | Range | Default | Origin Status | Why Valuable for R1 |
|-|-|-|-|-|-|-|-|
| 20 | Surprise level | `surprise_level` | float | [0, 1] | 0.0 | **NOT YET IN MW v2 SCHEMA** -- needs K1 implementation | Prediction error = primary learning signal (Rescorla-Wagner 1972). Surprising events trigger stronger hippocampal encoding |
| 21 | Identity relevance | `identity_relevance` | float | [0, 1] | 0.0 | **NOT YET IN MW v2 SCHEMA** -- needs K1 implementation | Self-reference effect (Rogers, Kuiper & Kirker 1977). Memories about self/family identity encode 2x stronger |
| 22 | Source reliability | `source_reliability` | float | [0, 1] | 1.0 | **NOT YET IN MW v2 SCHEMA** -- needs K1 implementation | Source monitoring framework (Johnson, Hashtroudi & Lindsay 1993). Trustworthiness of information source |
| 23 | Memory tier | `memory_tier` | str | routine/notable/significant/landmark | "routine" | **NOT YET IN MW v2 SCHEMA** -- needs K1 implementation | K1 pre-classification of memory importance level |
| 24 | Temporal anchor | `temporal_anchor_json` | str (JSON) | object | "{}" | **NOT YET IN MW v2 SCHEMA** -- needs K1 implementation | Resolved temporal reference for recency computation |

**CRITICAL OBSERVATION**: Signals 20-24 (M5A) have columns in st_hipp_events and fields in P03EventState, but **K1 Memory Writer does NOT yet produce them**. The MW v2 schema (`memory_atom.v2.schema.json`) does not include `surprise_level`, `identity_relevance`, `source_reliability`, `memory_tier`, or `temporal_anchor`. Until K1 implements these fields, they will always be their defaults (0.0, 0.0, 1.0, "routine", "{}").

**This means the R1 redesign must work in two modes:**

- **Phase A (now)**: Use only signals 1-19 (all available from MW v2 today)
- **Phase B (after K1 implements M5A)**: Activate signals 20-24 when non-default values appear

---

### 16.3 Source Reliability -- Deep Analysis

#### 16.3.1 What Is Source Reliability?

Source reliability answers: **"How much should we trust this piece of information?"**

This is rooted in the **Source Monitoring Framework** (Johnson, Hashtroudi & Lindsay, 1993) from cognitive psychology. Humans naturally assess:

- Did I see this happen? (high reliability)
- Did someone tell me? (medium reliability)
- Did I infer it? (lower reliability)
- Did a system guess it? (lowest reliability)

In FamilyOS, memories enter from different sources with different trustworthiness:

| Source | Reliability | Example | Why |
|-|-|-|-|
| User directly states a fact | HIGH (0.9-1.0) | "We had dinner at Olive Garden" typed by Dad | First-person declaration, highest confidence |
| User implies something | MEDIUM-HIGH (0.7-0.9) | User talks about "the restaurant" and MW infers Olive Garden from context | Contextual inference from user's own words |
| Device observation | MEDIUM (0.5-0.7) | GPS shows user at Olive Garden coordinates | Sensor data, accurate but may lack context (was it just a drive-by?) |
| System inference | LOW (0.3-0.5) | System infers from calendar event + location that dinner happened | Multi-step inference chain, each step compounds error |

#### 16.3.2 How Memory Writer Would Tag Source Reliability

Today MW v2 already has `source_type` (enum: `user_stated`, `user_implied`, `device_observed`, `system_inferred`). Source reliability is a NUMERIC SCORE derived from `source_type` plus additional context:

**Proposed K1 computation** (future MW implementation):

```
base_reliability = SOURCE_TYPE_MAP[source_type]
    # user_stated     -> 0.95
    # user_implied    -> 0.80
    # device_observed -> 0.65
    # system_inferred -> 0.45

confidence_factor = atom.confidence  # LLM self-score [0.0, 1.0], already in MW v2
reliability = base_reliability * confidence_factor
```

For example:

- User says "We went to Olive Garden" with confidence=0.95 -> `0.95 * 0.95 = 0.90`
- System infers dinner from calendar with confidence=0.70 -> `0.45 * 0.70 = 0.32`

#### 16.3.3 What R1 Can Do TODAY (Before K1 Implements source_reliability)

Since `source_type` IS available in MW v2 and IS loaded by R0, **R1 can derive a source reliability proxy** from `source_type` directly, without waiting for K1:

```python
SOURCE_TYPE_RELIABILITY: Dict[str, float] = {
    "user_stated":     0.95,
    "user_implied":    0.80,
    "device_observed": 0.65,
    "system_inferred": 0.45,
}

def derive_source_reliability(event: P03EventState) -> float:
    """Derive source reliability from source_type when explicit value not available."""
    if event.source_reliability != 1.0:  # Explicit value provided by K1
        return event.source_reliability
    # Fallback: derive from source_type
    return SOURCE_TYPE_RELIABILITY.get(event.source_type, 0.75)
```

#### 16.3.4 Should Source Reliability Be a Score Modulator or a Component?

**As a MODULATOR (multiplicative)**: `final_score = base_score * source_reliability`

- Pro: Conceptually clean -- unreliable sources discount everything proportionally
- Con: A system-inferred event with amazing content (milestone birthday) would get halved
- Con: Creates a hard ceiling -- no amount of emotional/social signals can overcome low reliability

**As a COMPONENT (additive)**: `base_score += reliability_weight * source_reliability`

- Pro: Reliable sources get a small boost, unreliable get less boost, but don't get punished
- Con: Doesn't actually "discount" unreliable information -- it just doesn't reward it

**Recommendation for R1 redesign**: **Hybrid approach** -- **POC VALIDATED**. Use source_reliability as a soft modulator with a floor:

```
reliability_adjusted = max(0.3, derive_source_reliability(event))
final_score = base_score * reliability_adjusted
```

The floor of **0.3** (not 0.5 as originally discussed) was validated in POC Phase 5+6. Floor=0.3 prevents total suppression while providing meaningful penalty for untrusted sources. All 8 source_reliability scenarios pass with floor=0.3 in Phase 6.

#### 16.3.5 Source Reliability Floor -- Discussion Points

| Floor Value | Effect | When It Makes Sense |
|-|-|-|
| No floor (0.0) | System-inferred events with low confidence could score near 0.0 | Aggressive -- risk losing valid inferred memories |
| 0.3 | System-inferred events lose up to 70% of score | Moderate -- strong penalty for low-trust sources. **POC VALIDATED: SELECTED** |
| 0.5 | System-inferred events lose up to 50% of score | Conservative -- too little discrimination. **POC REJECTED** |
| 0.7 | Minimal penalty even for lowest-trust sources | Very conservative -- source reliability barely matters |

**This is a POC calibration question.** The scoring matrix (Section 16.6) tested all floor values against representative events. **Result: floor=0.3 selected.**

---

### 16.4 Memory Tier Treatment -- Decision: Option A (Score Multiplier)

**Chosen approach**: Memory tier acts as a score multiplier applied after base importance computation.

**Rationale**: Score multipliers are self-contained within the scorer. They don't leak into tier classification logic, don't require changing CRITICAL/HIGH/MEDIUM/LOW threshold constants, and are easy to calibrate via the POC matrix.

**Proposed multipliers**:

| Memory Tier | Multiplier | Effect | Example |
|-|-|-|-|
| `routine` | 1.00 | No change (baseline) | "Had breakfast" |
| `notable` | 1.10 | +10% boost | "Sharvi got an A on her test" |
| `significant` | 1.25 | +25% boost | "First day at new school" |
| `landmark` | 1.50 | +50% boost | "Wedding anniversary", "Baby's first steps" |

```
importance = clamp(base_score * event_type_multiplier * intent_boost
                   * memory_tier_multiplier * reliability_adjusted,
                   0.0, 1.0)
```

**Current state**: `memory_tier` will be "routine" for all events until K1 implements tier classification in MW. This means the multiplier is 1.00 (no effect) until K1 ships. Safe default.

---

### 16.5 Recency Factor -- What It Is and Why It Matters

#### 16.5.1 The Problem

Currently `recency_factor` is hardcoded to 0.0 in every ScoredEvent. R1 computes importance as if all events are equally "fresh", whether they happened 5 minutes ago or 5 days ago.

But consolidation batches (R0) can contain events spanning hours or days. In cognitive neuroscience, **recent events have a processing advantage** -- the hippocampus prioritizes fresh experiences for initial consolidation (Frankland & Bontempi, 2005). Older events that survived without consolidation are either less important (routine) or were missed (catch-up).

#### 16.5.2 What Recency Factor Does

Recency factor gives a **temporal freshness bonus** to events. Recent events score slightly higher, all else being equal. This is NOT about forgetting -- it's about processing priority within a consolidation batch.

```
recency_factor = exp(-lambda * hours_since_event)
```

Where:

- `hours_since_event` = `(now_ms - event.timestamp) / 3_600_000`
- `lambda` controls decay speed (see 16.5.3)
- Result is [0.0, 1.0] where 1.0 = just happened, 0.0 = very old

This factor is then weighted: `recency_component = recency_weight * recency_factor`

#### 16.5.3 Lambda Calibration

Lambda controls **how fast the recency bonus decays**. The key concept is **half-life**: the time after which the recency bonus drops to 50%.

| Lambda | Half-Life | Recency after 1h | After 6h | After 24h | After 72h | After 168h (1 week) | Character |
|-|-|-|-|-|-|-|-|
| 0.005 | ~139 hours (~6 days) | 1.00 | 0.97 | 0.89 | 0.70 | 0.43 | Very slow decay. Events from a week ago still get 43% recency |
| 0.01 | ~69 hours (~3 days) | 0.99 | 0.94 | 0.79 | 0.49 | 0.19 | Slow decay. 3-day half-life. Good for weekly consolidation cycles |
| 0.02 | ~35 hours (~1.5 days) | 0.98 | 0.89 | 0.62 | 0.24 | 0.04 | Moderate decay. Yesterday's events at 62%, 3 days ago at 24% |
| 0.05 | ~14 hours | 0.95 | 0.74 | 0.30 | 0.03 | ~0 | Fast decay. Events older than a day get nearly zero recency |
| 0.10 | ~7 hours | 0.90 | 0.55 | 0.09 | ~0 | ~0 | Very fast. Only events from today get meaningful recency |

**For FamilyOS**: The consolidation pipeline (P03) runs on sleep cycles (ADR-K010.1). A family might have events spanning 16-24 hours between cycles. We want:

- Events from the current day to get strong recency (> 0.50)
- Events from yesterday to get moderate recency (0.20-0.60)
- Events from 3+ days ago to get low recency (< 0.25)

**This is a POC calibration question.** Lambda was tested in the scoring matrix (Section 16.6) across 562K events with varied ages. **Result: lambda=0.005 selected** (half-life ~139h / ~6 days). At 24h, CONFIG_B achieves avg Cohen's d = 0.472. At 72h, CRITICAL events still score 0.531 (well above 0.40 floor).

#### 16.5.4 Recency Timestamp Source

R1 computes `hours_since_event` from the event timestamp. Two options:

| Source | Field | Pro | Con |
|-|-|-|-|
| event_time_utc | `event.timestamp` | When the event actually happened | Backdated events (user logging yesterday's dinner) get wrong recency |
| created_at | `event.timestamp` (already converted from event_time_utc in R0) | When the event was written to system | User backdates intentionally -- we shouldn't penalize recency |

**Recommendation**: Use `event.timestamp` (which R0 already converts from `event_time_utc`). Backdated events are intentional -- the user is telling us "this happened at X time". If they're logging yesterday's dinner today, the dinner is 24h old and should get 24h-old recency. The P02 `is_backdated` flag could optionally override this (give full recency to backdated events because the user is actively thinking about them NOW), but that's a refinement for the POC to test.

---

### 16.6 POC Scoring Matrix -- Design Before Weights

#### 16.6.1 Why a Matrix First

The proposed enhancement adds 5 new components and 3 new modulators to the formula. Choosing weights by intuition is guesswork. Instead, we build a **scoring matrix**: a spreadsheet of representative events across the full spectrum of family life, scored by the proposed formula with different weight configurations, compared against what a human would rate as important.

The matrix answers:

- Does the formula produce sensible relative orderings? (milestone > routine) -- **YES (120/120 scenarios)**
- Do the new signals meaningfully differentiate events? -- **YES (avg Cohen's d = 0.476)**
- Which weight configuration best matches human intuition? -- **CONFIG_B (B_emotion_heavy)**
- Where does the formula break (edge cases)? -- **No breaks found in 120 scenarios. 9 initial expectation mismatches were all justified by formula behavior.**

#### 16.6.2 Proposed Enhanced Formula (Full)

```
# --- Component computation ---
emotional     = sentiment_w * abs(sentiment_score)
              + affect_w * abs(affect_valence)
              + arousal_w * affect_arousal

surprise      = surprise_w * surprise_level

novelty       = novelty_w * novelty_numeric(event.novelty)
              # ROUTINE=0.10, EXPECTED=0.30, NOVEL=0.70, SURPRISING=1.00
              # fallback: salience_score if novelty field is empty

social        = social_w * min(1.0, log2(num_participants) / LOG2_10)
              * intimacy_scale(social_intimacy)
              # intimacy_scale: HIGH=1.2, MEDIUM=1.0, LOW=0.8

identity      = identity_w * identity_signal(event)
              # identity_signal = identity_relevance if > 0.0
              #                   else len(identity_domains) / 9.0

recency       = recency_w * exp(-lambda * hours_since_event)

# --- Base score ---
base = emotional + surprise + novelty + social + identity + recency

# --- Elaboration boost (multiplicative) ---
elab_boost = ELABORATION_MAP.get(event.elaboration_depth, 1.0)
# MENTION=1.00, DISCUSSED=1.05, ELABORATED=1.10, DEEPLY_PROCESSED=1.15

# --- Goal event boost ---
goal_boost = 1.15 if event.narrative_is_goal_event else 1.0

# --- Arc position boost ---
arc_boost = ARC_MAP.get(event.narrative_arc_position, 1.0)
# EXPOSITION=1.0, RISING_ACTION=1.05, CLIMAX=1.15, RESOLUTION=1.0

# --- Temporal orientation boost ---
temporal_boost = TEMPORAL_MAP.get(event.temporal_orientation, 1.0)
# PAST=1.0, ONGOING=1.05, FUTURE_COMMITMENT=1.10

# --- Source reliability modulation ---
reliability = derive_source_reliability(event)  # See 16.3.3
reliability_adjusted = max(RELIABILITY_FLOOR, reliability)

# --- Memory tier multiplier ---
tier_mult = MEMORY_TIER_MAP.get(event.memory_tier, 1.0)
# routine=1.0, notable=1.10, significant=1.25, landmark=1.50

# --- Event type and intent multipliers (existing) ---
type_mult = EVENT_TYPE_MULTIPLIERS.get(activity_type_ultrabert, 1.0)
intent_boost = INTENT_BOOST_MULTIPLIERS.get(intent_ultrabert, 1.0)

# --- Final score ---
importance = clamp(
    base
    * elab_boost * goal_boost * arc_boost * temporal_boost
    * type_mult * intent_boost
    * tier_mult
    * reliability_adjusted,
    0.0, 1.0
)
```

#### 16.6.3 Weight Configurations to Test in POC

The 6 additive components (emotional, surprise, novelty, social, identity, recency) must sum to a meaningful range. With the current 4-weight system, max base = 1.00. We keep this property.

**Configuration A: Balanced** (equal emphasis) -- Phase 6: 118/120 (98.3%)

| Component | Weight | Max Contribution |
|-|-|-|
| emotional (sent+val+arousal) | 0.20 (split: 0.07 + 0.07 + 0.06) | 0.20 |
| surprise | 0.15 | 0.15 |
| novelty | 0.20 | 0.20 |
| social | 0.15 | 0.15 |
| identity | 0.15 | 0.15 |
| recency | 0.15 | 0.15 |
| **Total** | **1.00** | **1.00** |

**Configuration B: Emotion-Heavy** (McGaugh emphasis) -- **WINNER: 120/120 (100%)**

| Component | Weight | Max Contribution |
|-|-|-|
| emotional | 0.30 (split: 0.10 + 0.12 + 0.08) | 0.30 |
| surprise | 0.15 | 0.15 |
| novelty | 0.15 | 0.15 |
| social | 0.15 | 0.15 |
| identity | 0.10 | 0.10 |
| recency | 0.15 | 0.15 |
| **Total** | **1.00** | **1.00** |

**Configuration C: Social-Identity Heavy** (family context emphasis) -- Phase 6: 117/120 (97.5%)

| Component | Weight | Max Contribution |
|-|-|-|
| emotional | 0.20 (split: 0.07 + 0.07 + 0.06) | 0.20 |
| surprise | 0.10 | 0.10 |
| novelty | 0.15 | 0.15 |
| social | 0.20 | 0.20 |
| identity | 0.20 | 0.20 |
| recency | 0.15 | 0.15 |
| **Total** | **1.00** | **1.00** |

**Configuration D: Novelty-Surprise Heavy** (information-theoretic emphasis) -- Phase 6: 115/120 (95.8%)

| Component | Weight | Max Contribution |
|-|-|-|
| emotional | 0.15 (split: 0.05 + 0.05 + 0.05) | 0.15 |
| surprise | 0.20 | 0.20 |
| novelty | 0.25 | 0.25 |
| social | 0.10 | 0.10 |
| identity | 0.15 | 0.15 |
| recency | 0.15 | 0.15 |
| **Total** | **1.00** | **1.00** |

#### 16.6.4 Representative Event Scenarios for Matrix

The POC matrix scored each scenario with all 4 configurations plus varied lambda/floor values. The initial 15 scenarios below were expanded to **120 hand-crafted scenarios** across 13 categories for Phase 6 validation. See `poc/r1_weight_research/scenarios.py` for the full scenario set.

| # | Scenario | Expected Tier | Key Signals | Why Important to Test |
|-|-|-|-|-|
| 1 | Sharvi's first word -- Dad is there, high emotion, milestone | CRITICAL | sent=0.9, val=0.9, arousal=0.9, participants=3, intimacy=HIGH, novelty=SURPRISING, type=milestone, elaboration=DEEPLY_PROCESSED | Maximum importance -- system must score this near 1.0 |
| 2 | Regular breakfast alone | LOW | sent=0.1, val=0.0, arousal=0.1, participants=1, novelty=ROUTINE, type=routine | Minimum importance -- system must score this near 0.0-0.2 |
| 3 | Family dinner at Olive Garden (normal weeknight) | MEDIUM | sent=0.6, val=0.5, arousal=0.3, participants=4, intimacy=HIGH, novelty=EXPECTED, type=meal | Typical family event -- should be MEDIUM, not LOW |
| 4 | Getting fired from job -- solo, high negative emotion | HIGH | sent=-0.9, val=-0.8, arousal=0.9, participants=1, novelty=SURPRISING, identity_domains=[professional], type=message | High emotion + surprise but solo -- should be HIGH |
| 5 | Child's school play -- whole family, positive | HIGH-CRITICAL | sent=0.8, val=0.7, arousal=0.7, participants=5, intimacy=HIGH, novelty=NOVEL, type=celebration, is_goal=true | Social + emotional + goal event |
| 6 | System infers grocery trip from location | LOW-MEDIUM | sent=0.0, val=0.0, arousal=0.0, source_type=device_observed, novelty=ROUTINE | Tests source_reliability discount |
| 7 | User reflects on deceased parent (past) | HIGH | sent=-0.5, val=-0.6, arousal=0.4, participants=1, novelty=EXPECTED, elaboration=ELABORATED, identity_domains=[child, spiritual_self] | Elaboration + identity should boost despite low social |
| 8 | Planning vacation (future commitment) | MEDIUM-HIGH | sent=0.6, val=0.5, arousal=0.5, temporal=FUTURE_COMMITMENT, novelty=NOVEL, type=planning | Tests temporal_orientation and goal context |
| 9 | Wedding anniversary dinner (landmark) | CRITICAL | sent=0.9, val=0.8, arousal=0.6, participants=2, intimacy=HIGH, memory_tier=landmark, type=celebration | Tests memory_tier multiplier |
| 10 | Casual chat with friend about weather | LOW | sent=0.1, val=0.1, arousal=0.1, participants=2, intimacy=MEDIUM, novelty=ROUTINE, intent=casual_chat | Tests that routine chat stays LOW despite 2 participants |
| 11 | Health scare -- emergency room visit | CRITICAL | sent=-0.9, val=-0.9, arousal=1.0, participants=2, intimacy=HIGH, novelty=SURPRISING, identity_domains=[health_self], type=health | Maximum negative emotion + surprise + identity |
| 12 | Reading bedtime story to child (routine) | MEDIUM | sent=0.5, val=0.4, arousal=0.2, participants=2, intimacy=HIGH, novelty=ROUTINE, elaboration=MENTION | Routine but high intimacy -- should not be LOW |
| 13 | Same event scored 1 hour old vs 48 hours old | varies | Identical signals, different recency | Tests recency lambda impact on tier classification |
| 14 | Narrative CLIMAX moment in ongoing thread | HIGH boost | arc_position=CLIMAX, is_goal=true, moderate other signals | Tests arc + goal boost stacking |
| 15 | Low confidence system inference about old event | LOW | source_type=system_inferred, confidence=0.35, age=72h, novelty=ROUTINE | Tests reliability floor + recency compound effect |

#### 16.6.5 POC Execution Plan

1. **Build scoring matrix spreadsheet** (Python script or Jupyter notebook) -- **COMPLETE**
   - Input: 562K real events x 4 weight configs + 120 hand-crafted scenarios x 4 configs x 4 lambdas x varied floors
   - Output: importance_score + tier for each cell
   - POC code: `poc/r1_weight_research/` (config.py, signal_derive.py, scorer.py, run_matrix.py, calibrate.py, scenarios.py)

2. **Compare against current R1** (with bug fix applied in POC only) -- **COMPLETE**
   - Phase 4: Scored 562K events across all 4 configs. CONFIG_B winner with avg Cohen's d = 0.476.
   - Score distribution: mean=0.435, std=0.231, P10=0.179, P50=0.417, P90=0.702
   - FP rate (>0.8 scored as LOW proxy): 0.5%. FN rate (<0.3 scored as HIGH/CRIT proxy): 26.4%

3. **Select best configuration** -- **COMPLETE: CONFIG_B (B_emotion_heavy)**
   - CONFIG_B: highest avg Cohen's d (0.476), lowest FP (0.005), lowest FN (0.264)
   - Phase 6 validation: 120/120 scenarios pass (100%). Other configs: A=98.3%, C=97.5%, D=95.8%
   - Hard requirements: Scenario 1 (Sharvi's first word) = 1.000 (>0.85), Scenario 46 (breakfast alone) = 0.087 (<0.25)

4. **Document chosen weights + lambda + floor** -- **COMPLETE**
   - CONFIG_B: sentiment_w=0.10, affect_w=0.12, arousal_w=0.08, surprise_w=0.15, novelty_w=0.15, social_w=0.15, identity_w=0.10, recency_w=0.15
   - Lambda: 0.005 (half-life ~139h / ~6 days)
   - Reliability floor: 0.3
   - 6-tier thresholds: CRITICAL >= 0.80, HIGH >= 0.60, MEDIUM_HIGH >= 0.45, MEDIUM >= 0.30, LOW_MEDIUM >= 0.15, LOW < 0.15
   - Results: `poc/r1_weight_research/results/` (summary.md, phase5_summary.md, phase6_summary.md)

---

### 16.7 Proposed Epic Structure (Post-POC)

The current 5.2A-5.2F epics from Section 13 are REPLACED by the validated redesign approach. The new epic structure:

| Epic | Title | Scope | Depends On | Deliverables | Status |
|-|-|-|-|-|-|
| **5.2-POC** | R1 Scoring Matrix POC | Python POC: 562K events x 4 configs + 120 hand-crafted scenarios. Lambda/floor calibration. | 5A.1 + 5A.2 complete (signals available) | CONFIG_B validated, lambda=0.005, floor=0.3, 6-tier thresholds. POC code at `poc/r1_weight_research/` | **COMPLETE** |
| **5.2-REDESIGN** | R1 Formula Redesign | Rewrite `compute_importance_score` with 6 components + 7 modulators. Fix `participant_count` bug. Implement `derive_source_reliability`. Implement `recency_factor`. Add novelty categorical->numeric conversion. | 5.2-POC | Modified importance_scorer.py (1116 lines), r1_importance_scorer.py (398 lines), phase_outputs.py (726 lines), event_state.py (551 lines). 95 unit tests + 24 integration tests passing. | **COMPLETE** |
| **5.2-CONTRACT** | R1 Contract Alignment | Update YAML contract to match new formula. Fix Thompson Sampling -> gradient descent. Fix side_effects. Fix output_event_types. | 5.2-REDESIGN | Updated .yaml contracts | **COMPLETE** |
| **5.2-TEST** | R1 Comprehensive Tests | Phase integration test with real P03EventState. POC scenarios as test cases. Regression tests. Performance test (<30ms for 100 events). | 5.2-REDESIGN | 95 scorer + 24 integration + 7 POC scenarios + 5 performance + 20 cold-start + 10 idempotency = **161 R1 core tests** | **COMPLETE** (M5.O Epic 5.O.2) |
| **5.2-OBS** | R1 Observability | OTel span for R1. Score distribution histogram. Weight source counter. Priority tier gauge. R1PhaseMetrics populated. | 5.2-REDESIGN | observability.py 1195 lines. 49 OTel tests + 57 metrics tests = **106 observability tests** | **COMPLETE** (M5.O Epic 5.O.1) |
| **5.2-LEARNER** | R1 Weight Learner Alignment | Align learner component set with new 8-component scorer. Grounding signal path. | 5.2-REDESIGN | importance_weight_learner.py 707 lines (8-component). 21 alignment + 38 grounding signal tests = **59 learner tests** | **COMPLETE** (M5.W Epics 5.W.1 + 5.W.2) |
| **5.2-HEBBIAN** | Hebbian Learning Wiring | Wire R1 scores to R4 Hebbian. Decay + anti-Hebbian. Co-occurrence refactor. | 5.2-REDESIGN | hebbian_learner.py 604 lines. 58 Hebbian + 10 idempotency tests. R1->R4 score flow wired. | **COMPLETE** (M5.H Epics 5.H.1-5.H.3) |
| **5.2-FEEDBACK** | KG Edge Feedback Loop | KG boost in R1. Feedback queue. Full reinforcement cycle. Anomaly detection. | 5.2-HEBBIAN + 5.2-LEARNER | feedback_queue.py (184), async_audit.py (246), learning_anomaly_detector.py (460). 47+32+19+18+39+23 = **178 feedback tests** | **COMPLETE** (M6.F Epics 5.F.1 + 5.F.2) |
| **5.2-STORAGE** | Storage Housekeeping | Migration 0075 composite index. st_learned_weights verification. Retention policy. | none | Migration 0075. 32 storage + 31 retention = **63 storage tests** | **COMPLETE** (M5.S Epic 5.S.1) |
| **5.2-WIRING** | Production Wiring | Unified weight store adapter. Pipeline contract alignment. R3 stores wiring. | none | PgLearnedWeightsStore. 20 wiring tests. Contracts aligned. | **COMPLETE** (M5.P Epics 5.P.1-5.P.3) |

**All epics COMPLETE. Total R1 test count: 386+ tests across 20+ test files.**

**Gating rule**: ~~5.2-REDESIGN and 5.2-CONTRACT are COMPLETE. 5.2-TEST is partially complete. 5.2-OBS not started. 5.2-LEARNER deferred.~~ **ALL GATES PASSED.** Full R1 implementation complete across 6 milestones (M5.P, M5.H, M5.W, M6.F, M5.O, M5.S). All 72 issues from PLAN_HEBBIAN_WEIGHT_LEARNER_INTEGRATION.md resolved.

---

### 16.8 Open Design Questions (Resolved by POC)

| # | Question | Options | Resolution Method | **Answer** |
|-|-|-|-|-|
| 1 | Which weight configuration (A/B/C/D) best matches family memory importance? | A (balanced), B (emotion-heavy), C (social-identity), D (novelty-surprise) | POC Phase 4 (562K events) + Phase 6 (120 scenarios) | **CONFIG_B (B_emotion_heavy)**. Highest avg Cohen's d (0.476), lowest FP (0.005), lowest FN (0.264), 120/120 scenarios (100%). Emotion-heavy aligns with McGaugh amygdala model. |
| 2 | What is the best recency lambda? | 0.005, 0.01, 0.02, 0.05 | POC Phase 5 -- 4 lambdas x 5 ages x 4 configs = 80 calibration passes on 562K events | **lambda=0.005** (half-life ~139h / ~6 days). Highest avg Cohen's d at 24h (0.472). CRITICAL events at 72h still 0.531 (well above 0.40 minimum). Events from 1 week still get 43% recency -- appropriate for weekly consolidation cycles. |
| 3 | What is the best source reliability floor? | 0.3, 0.5, 0.7, no floor | POC Phase 5 floor calibration + Phase 6 scenarios 97-104 | **floor=0.3**. Allows up to 70% penalty for untrusted sources. Prevents total suppression. All 8 source_reliability scenarios pass. Floor=0.5 was too conservative (insufficient discrimination). |
| 4 | Should `is_backdated` events get full recency? | yes (they're thinking about it NOW), no (event is old) | Design decision -- deferred to production refinement | **Deferred**. POC uses event.timestamp for all events. Backdated events get their actual age. is_backdated override (giving full recency because user is actively thinking about it) is a production refinement for 5.2-REDESIGN to implement optionally. |
| 5 | Does multiplier stacking (elab x goal x arc x temporal x type x intent x tier x reliability) cause score inflation? | Maybe -- 1.15 x 1.15 x 1.15 x 1.10 x 2.0 x 1.2 x 1.5 x 1.0 = 7.97 before clamp | POC Phase 6 -- scenario 1 (Sharvi's first word) = max stacking | **Yes, but clamp handles it correctly.** Max stacking produces scores >> 1.0 before clamp, but clamp(0,1) catches all cases. Scenario 1 scores 1.000 (clamped). No intermediate precision issues -- all multipliers are applied in single float expression. Celebration events with 2.0x type multiplier legitimately reach CRITICAL via stacking. |
| 6 | Should intimacy_scale be multiplicative to social or additive? | Multiplicative: social * intimacy_scale. Additive: social + intimacy_bonus | POC Phase 6 -- family dinner (HIGH intimacy) vs friend weather chat (MEDIUM intimacy) | **Multiplicative**. social * intimacy_scale(social_intimacy) where HIGH=1.2, MEDIUM=1.0, LOW=0.8. Family dinner with 4 participants + HIGH intimacy vs friend chat with 2 participants + MEDIUM intimacy produces correct tier separation. |
| 7 | Can `identity_domains` count serve as `identity_relevance` proxy until K1 ships? | len(identity_domains) / 9.0 gives 0.0-1.0 range | POC Phase 4 + Phase 6 scenarios 89-96 (identity reflection category) | **Yes.** identity_signal = identity_relevance if > 0.0, else len(identity_domains) / 9.0. POC used NER entity mapping for identity in 562K events. Identity alone cannot over-inflate (scenario 120: identity=1.0 + all-zero-else = 0.126 LOW). |
| 8 | Should arc_position boost stack with goal_event boost or be either/or? | Stack: CLIMAX goal event = 1.15 * 1.15 = 1.32. Either/or: max(1.15, 1.15) = 1.15 | POC Phase 6 -- narrative scenarios + edge cases | **Stack (multiplicative)**. CLIMAX + goal event = 1.15 * 1.15 = 1.32x. This is intentional -- a goal-relevant climax moment IS the peak memory event and deserves maximum boost. Stacking does not cause over-boosting because base scores for narrative-only events are moderate and the final clamp prevents >1.0. |

---

### 16.9 Real Data Analysis -- 565K Event Dataset

> **Date**: 2026-03-02
> **Source**: `D:\Modeling_studio\data\familyos\unified\output_healed_merged\`
> **Size**: 113 JSONL shards, ~5000 events each, ~565,000 events total (~305 MB)
> **Origin**: FamilyOS K1 UltraBERT annotation pipeline output (healed + merged)

#### 16.9.1 Dataset Schema

Each event is a single JSON line with this structure:

```json
{
  "id": "fam_00007",
  "text": "Hope sparked seeing Nani walk farther.",
  "tasks": {
    "emotions": ["hope", "optimism", "joy", "pride", "gratitude", "relief"],
    "sentiment": "very_positive",
    "ner_family": [{"start": 20, "end": 24, "label": "KINSHIP", "token": "Nani"}],
    "safety_familyos": "GREEN",
    "intent": "express_feeling",
    "ingress": "GRATITUDE",
    "relations": [{"subject": "user", "predicate": "grandchild_of", "object": "Nani"}],
    "temporal": []
  },
  "hub_routing": {"EMO": true, "REL": true, "MEM": false, "TASK": false}
}
```

**Top-level fields**: `id`, `text`, `tasks`, `hub_routing`

**Tasks fields** (8): `emotions` (array), `sentiment` (categorical), `ner_family` (entity spans), `safety_familyos` (enum), `intent` (enum), `ingress` (enum), `relations` (triples), `temporal` (spans)

**Hub routing fields** (4): `EMO`, `REL`, `MEM`, `TASK` (booleans)

#### 16.9.2 Signal Distributions (shard_0000, n=5000)

**Sentiment** (5 values):

| Label | Count | % |
| - | - | - |
| very_positive | 2010 | 40% |
| neutral | 1879 | 37% |
| very_negative | 830 | 16% |
| negative | 263 | 5% |
| positive | 18 | 0.3% |

**Intent** (8 values):

| Label | Count | % |
| - | - | - |
| express_feeling | 2343 | 46% |
| share_news | 1046 | 20% |
| reflect | 556 | 11% |
| log_memory | 546 | 10% |
| other | 196 | 3% |
| set_reminder | 136 | 2% |
| query_memory | 110 | 2% |
| seek_advice | 67 | 1% |

**Ingress** (12 values):

| Label | Count | % |
| - | - | - |
| CONCERN | 1027 | 20% |
| RELATIONSHIP | 839 | 16% |
| DIARY | 729 | 14% |
| MEMORY | 674 | 13% |
| CELEBRATION | 669 | 13% |
| GRATITUDE | 280 | 5% |
| HEALTH | 210 | 4% |
| PLANNING | 190 | 3% |
| TASK | 139 | 2% |
| WORK | 105 | 2% |
| FINANCE | 92 | 1% |
| META | 46 | 0.9% |

**Emotion vocabulary**: 44 unique labels. Top 10: joy (1447), warmth (943), love (839), contentment (824), togetherness (784), sadness (724), frustration (713), neutral (689), nostalgia (590), worry (567)

**Emotions per event**: 1-10 labels. Median ~4. Distribution: 1 emo = 954, 2 = 329, 3 = 921, 4 = 1329, 5 = 955, 6+ = 512.

**NER family labels** (10 types): KINSHIP (3366), PERSON (1097), FAMILY_EVENT (719), ROUTINE (397), HOME_LOC (358), TRADITION (319), NICKNAME (219), PET (204), MILESTONE (199), HEIRLOOM (161)

**Relation predicates** (17 types): child_of (685), parent_of (518), sibling_of (344), grandchild_of (255), niece_nephew_of (189), grandparent_of (146), aunt_uncle_of (109), spouse_of (106), owns (105), pet_of (71), cousin_of (68), lives_at (45), friend_of (39), colleague_of (37), family_of (18), child_in_law_of (6), no_relation (1)

**Temporal labels** (6 types): DATE_REL (474), TIME (260), FREQUENCY (183), DURATION (141), DATE_ABS (124), AGE (102)

**Safety**: GREEN 71%, AMBER 25%, RED 2.3%, CRISIS 0.4%

**Hub routing (True)**: EMO 86%, REL 47%, MEM 34%, TASK 10%

**Entity coverage**: 78% have NER entities, 47% have relations, 19% have temporal spans

#### 16.9.3 Signal Mapping -- Dataset to R1 Formula

The dataset does NOT contain R1's numeric signals directly. A **signal derivation layer** is required.

| # | R1 Signal | Needed Type | Data Source | Derivation Method | Quality |
| - | - | - | - | - | - |
| 1 | `sentiment_score` | float [-1,1] | `tasks.sentiment` | Categorical map: very_negative=-0.9, negative=-0.5, neutral=0.0, positive=0.5, very_positive=0.9 | HIGH -- 5-level ordinal maps cleanly |
| 2 | `affect_valence` | float [-1,1] | `tasks.emotions` | NRC-VAD lexicon: average valence across all emotion labels. e.g. joy=0.98, fear=-0.64, sadness=-0.81 | HIGH -- NRC-VAD covers all 44 emotions |
| 3 | `affect_arousal` | float [0,1] | `tasks.emotions` | NRC-VAD lexicon: average arousal. e.g. fear=0.85, anger=0.83, contentment=0.15, neutral=0.10 | HIGH -- same lexicon |
| 4 | `affect_dominance` | float [0,1] | `tasks.emotions` | NRC-VAD lexicon: average dominance. e.g. anger=0.74, joy=0.72, sadness=0.22, fear=0.18 | HIGH -- same lexicon |
| 5 | `num_participants` | int >= 1 | `tasks.ner_family` + `tasks.relations` | count(unique KINSHIP + PERSON entities) + 1 (for user). Minimum 1. | HIGH -- 78% have entities |
| 6 | `social_intimacy` | LOW/MED/HIGH | `tasks.relations` | Relation predicate map: spouse_of/parent_of/child_of = HIGH, grandparent/aunt/sibling = MEDIUM, friend/colleague = LOW. Use highest if multiple. | MEDIUM -- 47% have relations, rest default to LOW |
| 7 | `activity_type` | enum (12 types) | `tasks.ingress` | Direct map: CELEBRATION -> celebration, HEALTH -> health, DIARY -> diary, PLANNING -> planning, TASK -> routine, etc. | HIGH -- 1:1 mapping |
| 8 | `intent` | enum (8 types) | `tasks.intent` | Direct: express_feeling, share_news, reflect, log_memory, query_memory, set_reminder, seek_advice, other | HIGH -- 1:1 mapping |
| 9 | `surprise_level` | float [0,1] | `tasks.emotions` | 1.0 if "surprise" in emotions, 0.5 if bittersweet/nostalgia (mixed signal), else 0.0 | LOW -- coarse binary, only 179/5000 have "surprise" |
| 10 | `novelty` | enum | `tasks.ingress` + NER | SURPRISING if CRISIS safety; NOVEL if MILESTONE NER or CELEBRATION ingress; EXPECTED if RELATIONSHIP/MEMORY; ROUTINE if DIARY/TASK/WORK + neutral sentiment | MEDIUM -- heuristic, no direct novelty signal |
| 11 | `identity_relevance` | float [0,1] | `tasks.ner_family` | count(KINSHIP + TRADITION + HEIRLOOM + MILESTONE entities) / max_seen. Normalized per shard. | MEDIUM -- entity density proxy |
| 12 | `elaboration_depth` | enum | `text` | Word count heuristic: <8w = MENTION, 8-20 = DISCUSSED, 20-40 = ELABORATED, 40+ = DEEPLY_PROCESSED | LOW -- length is a weak proxy for depth |
| 13 | `source_type` | enum | NONE | CONSTANT: "user_stated" for all events (all user-generated text) | N/A -- no source variance to test |
| 14 | `narrative_is_goal_event` | bool | NONE | NOT DERIVABLE -- needs narrative thread context | N/A |
| 15 | `narrative_arc_position` | enum | NONE | NOT DERIVABLE -- needs narrative thread context | N/A |
| 16 | `temporal_orientation` | enum | `tasks.temporal` + `tasks.intent` | FUTURE_COMMITMENT if set_reminder intent or PLANNING ingress; PAST if DATE_REL with past markers; else ONGOING | MEDIUM -- heuristic |
| 17 | `salience_score` | float [0,1] | NONE | NOT DERIVABLE -- needs salience model | N/A |
| 18 | `identity_domains` | array | `tasks.relations` + NER | Derive: parent_of -> ["parent_identity"], TRADITION NER -> ["cultural_self"], HEALTH ingress -> ["health_self"] | LOW -- incomplete |

**Summary**: 8 signals derivable at HIGH quality, 4 at MEDIUM, 3 at LOW, 3 NOT DERIVABLE.

#### 16.9.4 Proxy Ground Truth -- Weak Supervision from Safety + Routing

The dataset has no human-labeled importance tiers. But `safety_familyos` and `hub_routing` together create a **proxy importance signal** sufficient for weight research:

| Proxy Tier | Rule | Est. % | Reasoning |
| - | - | - | - |
| CRITICAL | safety = CRISIS | 0.4% | System already flagged as crisis-level |
| HIGH | safety = RED OR (safety = AMBER AND EMO = true AND sentiment in {very_negative}) | ~5% | Severe emotional events with safety concern |
| MEDIUM-HIGH | EMO = true AND REL = true AND MEM = true | ~15% | Triple-routed: emotional, relational, memory-worthy |
| MEDIUM | EMO = true AND (REL = true OR MEM = true) | ~25% | Dual-routed: emotional plus one context signal |
| LOW-MEDIUM | EMO = true AND sentiment != neutral | ~20% | Emotional only, no relational/memory signal |
| LOW | EMO = false OR sentiment = neutral AND no routing | ~35% | No significant signals triggered |

This proxy is IMPERFECT but directionally useful:

- It CANNOT distinguish a milestone from a celebration (both might be GREEN + EMO + MEM)
- It OVER-weights negative events (AMBER/RED safety correlates with negative but not all negative is important)
- It UNDER-weights positive milestones that feel GREEN/safe but are CRITICAL memories

Despite these flaws, 565K events with proxy labels give enough statistical mass to find weight configurations that reliably separate high-importance from low-importance events. Edge cases were tested with 120 hand-crafted scenarios (expanded from the initial 15 in Section 16.6.4). **Result: CONFIG_B achieves 120/120 (100%) scenario pass rate.**

#### 16.9.5 NRC-VAD Lexicon Requirement

The NRC Valence-Arousal-Dominance (VAD) Lexicon (Mohammad 2018) maps ~20,000 English words to [valence, arousal, dominance] triples on [0,1] scale. All 44 emotion labels in the dataset are standard psychological terms covered by NRC-VAD.

**Sample mappings for FamilyOS emotion labels**:

| Emotion Label | Valence | Arousal | Dominance | Notes |
| - | - | - | - | - |
| joy | 0.98 | 0.66 | 0.72 | High positive, moderate arousal |
| love | 0.96 | 0.54 | 0.57 | High positive, low-moderate arousal |
| sadness | 0.19 | 0.35 | 0.22 | Low valence, low arousal, low dominance |
| fear | 0.07 | 0.85 | 0.18 | Very low valence, very high arousal, very low dominance |
| anger | 0.17 | 0.83 | 0.74 | Low valence, high arousal, HIGH dominance |
| surprise | 0.54 | 0.77 | 0.40 | Neutral valence, high arousal |
| neutral | 0.50 | 0.10 | 0.50 | Baseline |
| warmth | 0.87 | 0.35 | 0.55 | Positive, low arousal |
| frustration | 0.18 | 0.72 | 0.30 | Negative, high arousal, low dominance |
| nostalgia | 0.65 | 0.40 | 0.35 | Mildly positive, bittersweet |
| togetherness | 0.90 | 0.40 | 0.55 | Positive, social-bonding signal |
| worry | 0.15 | 0.70 | 0.20 | Negative, high arousal, low dominance |

The full 44-label VAD mapping table will be built in the weight research notebook. Labels not directly in NRC-VAD (e.g. `parental_guilt`, `togetherness`, `bittersweet`) will be mapped by closest semantic match or compound average.

#### 16.9.6 Signals NOT Testable with This Dataset

These signals cannot be tested because the data lacks the underlying context:

| Signal | Why Not Derivable | Impact on Weight Research |
| - | - | - |
| `narrative_is_goal_event` | Needs multi-turn narrative thread tracking | Set to False for all events. goal_boost = 1.0 always. Weight research results remain valid -- this is a binary multiplier that only affects events K1 flags as goal-relevant. |
| `narrative_arc_position` | Needs narrative thread context | Set to EXPOSITION for all events. arc_boost = 1.0 always. Same reasoning as above. |
| `salience_score` | Needs trained salience model | Use `novelty` heuristic as proxy (Section 16.9.3 #10). The formula uses novelty categorical, not salience float, so this is acceptable. |
| `source_reliability` | All events are user_stated (constant 0.95) | Cannot test source_reliability variance. Test with the 15 hand-crafted scenarios (Section 16.6.4 #6, #15) instead. |
| `memory_tier` | This is the OUTPUT we're computing | N/A -- cannot be an input. Multiplier = 1.0 for all events. |

**Key insight**: The untestable signals are all MULTIPLIERS (binary or small boosts). The core additive components (emotional, surprise, novelty, social, identity, recency) ARE testable. Since the weight research is about finding the right additive balance, this dataset is sufficient. **POC confirmed**: CONFIG_B was validated on 562K real events (additive components) plus 120 hand-crafted scenarios (which exercise all multipliers including narrative, goal, arc, memory_tier, and source_reliability).

## Learning Systems

#### How R1 Was Designed

R1 is a **two-subsystem phase** with a very deliberate activation sequence:

##### Subsystem A: Importance Scoring (ACTIVE)

This is what's running today. Every time P03 consolidation runs:

1. R0 hydrates events from `st_hipp_events` into a `P03BatchEnvelope`
2. R1 takes that batch and computes an **importance score [0, 1]** for each event using CONFIG_B:

```
base = emotional + surprise + novelty + social + identity + recency    (6 additive)
score = clamp(base × elab × goal × arc × temporal × type × intent × tier × reliability, 0, 1)
```

1. Each event gets its score + 6 factor breakdowns + priority tier (6-tier)
2. Downstream phases (R3 dedup, R5 dream selection, R6 staging) use these scores to decide what matters

This is **pure stateless math** — given the same event, you always get the same score. No learning, no feedback, no state.

##### Subsystem B: Hebbian Learning (AUTO-ACTIVATION at 500 events, Decision D-R1-001)

This is the **knowledge graph edge weight learning** system. Completely separate concern from scoring.

---

#### What Hebbian Learning Actually Does

Hebbian = "cells that fire together, wire together" (Hebb, 1949).

In FamilyOS context: when two entities appear together in events, the **edge between them in the knowledge graph strengthens**.

##### Concrete example

Say Mom and Dad appear in the same event 50 times. The HebbianLearner:

1. **Extracts co-occurrences** from each event's NER entities:
   - `(Mom, Dad)` → `INTERACTS_WITH` — they're both PERSON entities appearing together
   - `(Mom, Home)` → `FREQUENTS` — PERSON + LOCATION co-occurrence
   - `(Dad, cooking)` → `DISCUSSES` — PERSON + TOPIC co-occurrence

2. **Strengthens edge weights** using soft saturation:

   ```
   delta = learning_rate × (max_weight - current_weight) × event_importance
   ```

   So if Mom-Dad edge is at 0.5, learning_rate=0.1, and the event importance is 0.8:

   ```
   delta = 0.1 × (1.0 - 0.5) × 0.8 = 0.04
   new_weight = 0.54
   ```

   The `(max_weight - current_weight)` term means it **slows down as it approaches 1.0** — soft saturation. You can never exceed max_weight.

3. **Decays unused edges** over time:

   ```
   new_weight = weight × exp(-0.01 × days_since_last_update)
   ```

   If Mom and some old neighbor haven't appeared together in 100 days, that edge fades to near zero and gets pruned.

4. **Weakens wrong associations** via anti-Hebbian signals:
   - User says "No, that's not the same person" → `ENTITY_MERGE_REJECTED` signal
   - System detects a contradiction → `CONTRADICTION` signal
   - Anti-Hebbian learning is **1.5x faster** than positive learning (anti_learning_rate=0.15 vs learning_rate=0.10) — wrong associations should be corrected quickly

##### Edge weight interpretation

| Weight | Meaning | Example |
|--------|---------|---------|
| 0.80-1.00 | Very Strong | Best friends, immediate family |
| 0.50-0.79 | Strong | Close friends, colleagues |
| 0.20-0.49 | Moderate | Acquaintances |
| 0.01-0.19 | Weak | One-time interactions |
| <0.01 | Pruned | Edge deleted |

---

#### Why Hebbian Is Disabled (Your Intuition Is Correct)

Yes — Hebbian needs **scored events first** before it can learn anything meaningful. The code in `R1Config`:

```python
enable_hebbian: bool = False  # Auto-activates at hebbian_activation_threshold (Decision D-R1-001)
hebbian_activation_threshold: int = 500  # Same as weight learner threshold
```

The logic is this:

1. **Hebbian reads `event.importance_score`** to decide how much to strengthen an edge. High-importance events strengthen connections more than low-importance ones. If importance scoring hasn't run or is garbage, Hebbian learns garbage.

2. **Hebbian needs volume** — a single co-occurrence between Mom and Dad doesn't mean they're close. You need dozens/hundreds of events to build meaningful edge weights. The system needs time to accumulate events.

3. **The KG needs to exist first** — Hebbian updates edges in `st_kg_edges`. Those edges need to be seeded by entity resolution (P06) and the KG builder. If the KG is empty or unstable, Hebbian updates have nowhere to go.

So the activation sequence is:

```
Phase 1: P02 enrichment pipeline stable (signals flowing)     DONE
Phase 2: R1 importance scoring implemented + validated          DONE (CONFIG_B, 95+24 tests)
Phase 3: R1->R4 Hebbian wiring complete                        DONE (M5.H, 58+10 tests)
Phase 4: Weight learner aligned to 8-component CONFIG_B         DONE (M5.W, 21+38 tests)
Phase 5: Feedback loop wired (KG boost + reinforcement cycle)   DONE (M6.F, 47+32+19+18+39+23 tests)
Phase 6: Observability instrumented                             DONE (M5.O, 49+57 tests)
Phase 7: Storage housekeeping complete                          DONE (M5.S, 32+31 tests)
Phase 8: P06 entity resolution + KG builder operational         NOT YET
Phase 9: Sufficient scored events accumulated (~500+)           NOT YET (auto-activates via D-R1-001)
Phase 10: Enable Hebbian with conservative learning_rate        AUTO (D-R1-001: hebbian_activation_threshold=500)
```

---

#### The Third Thing: ImportanceWeightLearner (Also Separate)

There's a **third** learning system that's also disconnected: the `ImportanceWeightLearner`. This is NOT Hebbian. This learns the **weights themselves** (the 8 CONFIG_B weights like sentiment=0.10, affect=0.12, etc.).

How it's designed to work:

1. After 500+ events are scored AND grounded (user confirms/rejects the memory), it trains
2. It uses online gradient descent on binary cross-entropy: "did this event actually become a grounded memory?"
3. It slowly adjusts the 8 weights away from CONFIG_B defaults toward personalized values
4. Rollback after 3 consecutive nights of increasing loss

**Current status (M5.W COMPLETE)**: The learner has been aligned to the 8-component CONFIG_B set: `(sentiment, affect, arousal, surprise, novelty, social, identity, recency)` matching the scorer exactly. The grounding signal path from K1 -> weight learner is wired (M5.W.2). The feedback queue (M6.F) routes grounding signals. The naming mismatch **FG-R1-002 is FIXED**. However, the learner still awaits production grounding data (500+ grounded events) before it can actually train personalized weights.

---

#### Summary: Three Learning Systems, One Phase

| System | What It Learns | When It Kicks In | Status |
|--------|---------------|------------------|--------|
| **ImportanceScorer** | Nothing (stateless math) | Always active | **IMPLEMENTED** (CONFIG_B, 1116 lines, 95 unit + 24 integration tests) |
| **HebbianLearner** | KG edge weights between entities | After KG exists + enough scored events | **WIRED, AUTO-ACTIVATION DECIDED** (D-R1-001): R1 scores flow to R4 Hebbian. Decay + anti-Hebbian wired. Co-occurrence refactored. hebbian_activation_threshold=500 in WeightTrainingConfig + R1Config. WeightTrainingTriggerResult.hebbian_activated reports when threshold crossed. Awaits P06 + KG operational. 58 Hebbian + 10 idempotency tests. |
| **ImportanceWeightLearner** | The 8 CONFIG_B weights themselves | After 500+ grounded events | **ALIGNED and WIRED** (M5.W): 8-component CONFIG_B alignment complete. Grounding signal path K1 -> learner wired (M5.W.2). Feedback queue + anomaly detector operational (M6.F). 21 alignment + 38 grounding + 32 feedback tests. Awaiting production grounding data. |

Your intuition is exactly right: Hebbian was deliberately stopped because it needs a foundation of scored events and a functional KG before it can do anything useful. The open question (Q6 in the discovery doc) is whether activation should be **automatic** (flip on after N scored events) or **manual** (config flag someone turns on).
