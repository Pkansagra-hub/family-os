# P03 Milestone 5 Execution Document

> **Milestone**: M5 — R6–R8 finalize: stage → commit → emit
> **Status**: NOT_STARTED
> **Started**: YYYY-MM-DD
> **Completed**: YYYY-MM-DD
> **Prerequisites**: M4 COMPLETED (R1-R4 Core Cognition)
> **Branch**: `postgre-sql-migration`
> **Baseline Commit**: TBD (after M4 completion)

---

## Document Overview

This document provides the execution plan for Milestone 5 (M5), which implements the finalization phases of P03: R6 (Staging), R7 (TruthWriter), and R8 (Event Emission).

**M5 Focus**: Wire the outputs from R1-R5 cognition phases into durable storage writes and bus event emission.

---

## Part A: Context Foundation (BEFORE YOU START)

### A.0 M0–M4 Outputs — EXISTING INFRASTRUCTURE AUDIT

> **CRITICAL**: M5 builds on completed infrastructure from M0-M4.
> This section documents what ALREADY EXISTS to avoid duplication.

#### M0 Deliverables (Contracts & ADRs) — ALL COMPLETE

| Artifact | Path | Status |
|----------|------|--------|
| Pipeline ADR | `docs/architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md` | EXISTS |
| State Machine ADR | `docs/architecture/decisions-K0/pipelines/k010.1-sleep-cycle-state-machine.md` | EXISTS |
| Capability ADR | `docs/architecture/decisions-K0/pipelines/k010.9-capability-based-security.md` | EXISTS |
| Pipeline Contract | `k0/contracts/pipelines/p03_consolidation.v1.yaml` | EXISTS |
| 17 Module Contracts | `k0/contracts/modules/consolidation.*.v1.yaml` | EXISTS |
| Capability Contract | `k0/contracts/capabilities/consolidation.v1.yaml` | EXISTS |
| 8 Event Schemas | `k0/contracts/schemas/p03_*.json` | EXISTS |
| Config Schema | `k0/contracts/jsonschema/p03.config.schema.json` | EXISTS |

#### M1 Deliverables (Pipeline Skeleton) — Detailed File Inventory

> **Epic 1.1**: Envelope Model (Issues 1.1.1-1.1.8)
> **Epic 1.2**: Sequential Runner (Issues 1.2.1-1.2.8)
> **Epic 1.3**: Scheduler + Concurrency (Issues 1.3.1-1.3.6)
> **Total Issues**: 22 | **Test Count**: 399 tests | **Coverage**: 91.74%

---

##### M1 Core Files in `k0/pipelines/p03/`

| File | Lines | Issue | Description | Key Classes/Functions | M5 Usage |
|------|-------|-------|-------------|----------------------|----------|
| `context.py` | 900 | 1.1.2 | Immutable batch-level context set during R0. Contains cycle metadata (cycle_id, batch_id, tenant_id, space_id, trace_id, trigger_type, deadline_ms). Enforces `@dataclass(frozen=True)` for immutability. | `P03CycleContext`, `R0TriggerInputs`, `generate_ulid()` | Cycle context passed to R6-R8 phases |
| `event_state.py` | 531 | 1.1.3 | Mutable per-event state that accumulates enrichment through R0-R6. Tracks each event's journey including importance, clustering, reconciliation decisions, and write results. | `P03EventState`, `ReconciliationAction` (8 values), `PruneDecision` (3 values) | Decision tracking for staging |
| `phase_outputs.py` | 666 | 1.1.4 | Container for batch-level aggregated outputs from each phase R0-R8. Contains 22 aggregate types for clusters, entities, edges, insights. | `P03PhaseOutputs`, `ScoredEvent`, `HebbianEdgeUpdate`, `EpisodeCluster`, `DedupMerge`, `DecayUpdate`, `KGEntity`, `KGEdge`, `CausalEdge`, `GapCandidate`, `WriteResult`, `CycleSummary` | Phase result types for R6 assembly |
| `staged_writes.py` | 587 | 1.1.5 | Deferred write accumulator for atomic commit. Groups writes by layer for batch execution efficiency. Computes idempotency keys deterministically for retry safety. | `P03StagedWrites`, `WriteOperation` (INSERT/UPDATE/ARCHIVE/TOMBSTONE), `StagedWrite`, `StagedOutboxEvent`, `LAYER_*` constants | **CORE FOR R6** - accumulates all writes |
| `observability.py` | 1224 | 1.1.6, 1.2.4 | Tracing, timing, and metrics aggregation. Provides distributed tracing, phase timing, and metrics collection. Includes R1 phase metrics dataclasses. | `P03ObservabilityContext`, `P03Error`, `PhaseTransitionLogger`, `PhaseTransitionLoggerProtocol`, `R1PhaseMetrics` | Observability hooks for R6-R8 |
| `serializer.py` | 744 | 1.1.7 | Envelope serialization for checkpoints, DLQ, and recovery. Handles JSON serialization of all envelope components. | `P03EnvelopeSerializer`, `PhaseCheckpoint`, `InvalidPhaseTransition` | Checkpointing in R7/R8 |
| `envelope.py` | 251 | 1.1.1 | Top-level P03BatchEnvelope container that flows through all R0-R8 phases. Holds context, events, phases, staged writes, observability. | `P03BatchEnvelope` | Root container for all phases |
| `runner_contract.py` | 574 | 1.2.1 | Sequential runner contract defining phase execution rules. Documents strict R0->R8 sequential execution with specific skip transitions. | `P03PhaseId` (11 values), `P03PhaseStatus`, `PHASE_CONTRACTS`, `RESUME_MATRIX`, `SKIP_TRANSITIONS`, `is_valid_transition()` | Phase execution rules |
| `phase_interface.py` | 665 | 1.2.2 | Uniform interface for all R0-R8 phases. Defines the protocol that all phase implementations must follow. | `P03PhaseProtocol`, `P03PhaseResult`, `P03RunnerContext`, `P03CycleResult` | **PHASE INTERFACE** - R6/R7/R8 implement this |
| `sequential_runner.py` | 644 | 1.2.3, 1.2.4 | Engine that runs phases strictly in order R0->R8. Applies transitions/skip rules, records per-phase results, supports resume from checkpoint. | `P03SequentialRunner`, `P03RunnerError`, `PhaseRegistration` | **EXTEND for R6-R8 retry logic** |
| `checkpoint.py` | 665 | 1.2.5 | Checkpoint contract for P03 runner-level checkpointing. Enables recovery from failures and offset management. | `P03Checkpoint`, `P03Offset`, `CheckpointStore` (Protocol), `P03_SUBSCRIBER_ID`, `P03_CHECKPOINT_TOPIC` | Checkpoint storage for R7 recovery |
| `offset_manager.py` | 674 | 1.2.6 | Offset/watermark integration for exactly-once processing. Manages WAL position tracking. Offset writes ONLY on successful R8 completion. | `P03OffsetManager`, `OffsetManagerError`, `OffsetUpdateResult` | Offset management in R8 |
| `deterministic.py` | — | 1.2.7 | Deterministic seeding for reproducible pipeline runs. Provides consistent random state for testing. | `P03DeterministicSeeder`, `seed_from_context()` | Test reproducibility |

---

##### M1 Test Files in `tests/k0/pipelines/p03/`

| File | Tests | Issue | Description |
|------|-------|-------|-------------|
| `test_p03_envelope.py` | ~40 | 1.1.8 | Tests for P03BatchEnvelope, context, event_state, phase_outputs |
| `test_p03_sequential_runner.py` | ~30 | 1.2.8 | Tests for P03SequentialRunner, phase transitions, skip rules |
| `test_p03_checkpoint.py` | ~20 | 1.2.5 | Tests for checkpoint persistence and recovery |
| `test_p03_offset_manager.py` | ~15 | 1.2.6 | Tests for offset management and exactly-once semantics |
| `test_p03_deterministic.py` | ~10 | 1.2.7 | Tests for deterministic seeding |
| `test_p03_triggers.py` | ~15 | 1.3.1-1.3.3 | Tests for trigger configuration |
| `test_p03_qos_integration.py` | ~10 | 1.3.5-1.3.6 | Tests for QoS token acquisition |
| `conftest.py` | — | — | Shared fixtures for P03 tests |

#### M2 Deliverables (Storage + Audit + Learning) — Detailed File Inventory

> **Epic 2.1**: Core truth + operational tables (Issues 2.1.1-2.1.12)
> **Epic 2.2**: Audit + explainability + compliance (Issues 2.2.1-2.2.5)
> **Epic 2.3**: Learning + feedback persistence (Issues 2.3.1-2.3.10)
> **Total Issues**: 27 | **Test Count**: 500+ tests

---

##### M2 Alembic Migrations in `k0/db/alembic/versions/`

| Migration | Table | Issue | Description | Columns | Indexes | M5 Usage |
|-----------|-------|-------|-------------|---------|---------|----------|
| `0027_st_epi.py` | st_epi | 2.1.2 | Episodic memory table. Stores consolidated episode clusters with temporal anchoring. Brain analog: Episodic Memory (Tulving). | 33 columns | 4 indexes | **R7 write target** - EpisodicLayerWriter |
| `0028_st_sem.py` | st_sem | 2.1.3 | Semantic patterns table. Stores extracted semantic patterns and generalizations. Brain analog: Semantic Memory. | 26 columns | 4 indexes | **R7 write target** - SemanticLayerWriter |
| `0029_st_procedural.py` | st_procedural | 2.1.4 | Procedural habits table. Stores learned routines and behavioral patterns. Brain analog: Procedural Memory. | 27 columns | 3 indexes | **R7 write target** - ProceduralLayerWriter |
| `0030_st_social.py` | st_social | 2.1.5 | Social relationships table. Stores relationship graphs and social context. Brain analog: Social Memory. | 27 columns | 2 indexes | **R7 write target** - SocialLayerWriter |
| `0031_st_prospective.py` | st_prospective | 2.1.6 | Prospective intentions table. Stores goals, intentions, and future-oriented memories. Brain analog: Prospective Memory. | 23 columns | 2 indexes | **R7 write target** - ProspectiveLayerWriter |
| `0032_st_kg_dom.py` | st_kg_dom | 2.1.7 | Knowledge graph entities table. Stores disambiguated entities with embeddings. | 23 columns | 3 indexes | **R7 write target** - KGLayerWriter (entities) |
| `0033_st_kg_edges.py` | st_kg_edges | 2.1.8 | Knowledge graph edges table. Stores relationships between entities including causal edges. FK to st_kg_dom. | 22 columns | 3 indexes | **R7 write target** - KGLayerWriter (edges) |
| `0034_st_hipp_events_p03_columns.py` | st_hipp_events | 2.1.10 | P03 consolidation columns. Adds consolidation_status, reconciliation_action, near_duplicates_json, etc. | 6 columns | 1 partial index | R6 status marking |
| `0035_st_outbox_fix_next_attempt_ts.py` | st_outbox | 2.1.11 | Type fix TEXT→BIGINT for next_attempt_ts. Corrects timestamp type for proper sorting. | ALTER column | — | R8 outbox scheduling |
| `0036_st_consolidation_audit.py` | st_consolidation_audit | 2.2.1 | Decision audit trail table. Stores all consolidation decisions with inputs/outputs for explainability. | 20+ columns | 4 indexes | R7 audit logging |
| `0037_st_learning_queue.py` | st_learning_queue | 2.3.2 | Gap detection queue for P06 Active Learning. Stores gaps with priority, ttl, question templates. | 18 columns | 3 indexes | **R8 gap emission** |
| `0038_st_anchors.py` | st_anchors | 2.3.3 | Bayesian anchor points for Thompson sampling. Stores priors for adaptive thresholds. | 15 columns | 2 indexes | R7 anchor updates |
| `0039_st_anchor_observations.py` | st_anchor_observations | 2.3.4 | Anchor outcome tracking. Stores reward signals for Thompson sampling updates. | 12 columns | 2 indexes | R7 observation logging |
| `0040_st_learned_weights.py` | st_learned_weights | 2.3.5 | Thompson sampling parameters. Stores alpha/beta for importance factors. | 10 columns | 1 index | R7 weight updates |
| `0041_st_learned_weights_history.py` | st_learned_weights_history | 2.3.6 | Parameter history for auditing. Append-only log of weight changes. | 8 columns | 1 index | R7 history logging |
| `0042_st_feedback_quarantine.py` | st_feedback_quarantine | 2.3.7 | Suspicious feedback storage. Holds flagged signals for review. | 15 columns | 2 indexes | R0 quarantine check |
| `0043_st_feedback_signals_consumption.py` | st_feedback_signals | 2.3.8 | Consumption columns. Adds consumed_at, consumed_by for P03 consumption semantics. | 2 columns | — | R0 consumption marking |
| `0044_st_golden_dataset.py` | st_golden_dataset_pairs, st_validation_results | 2.3.9 | Golden dataset tables for regression testing. | 20+ columns | — | Validation |
| `0045_st_dlq_p03_reconcile.py` | st_dlq | 2.3.10 | P03 DLQ columns. Adds pipeline_id, phase, error tracking. | 5 columns | 1 index | R6-R8 error handling |

---

##### M2 Python Modules in `k0/pipelines/p03/`

| File | Lines | Issue | Description | Key Classes/Functions | M5 Usage |
|------|-------|-------|-------------|----------------------|----------|
| `audit_logger.py` | 447 | 2.2.2 | Decision audit write path. Writes structured records to st_consolidation_audit with inputs/outputs serialized to JSON. Never logs raw PII. | `P03DecisionAuditLogger`, `AuditAction` (9 values), `AuditEntry`, `log_decision()`, `flush()` | Audit logging in R7 |
| `explainability.py` | 336 | 2.2.3 | Explainability query API. Read path for answering "why was this memory handled this way?". Returns user-safe fields only. | `MemoryExplanation`, `ExplainabilityService` (Protocol), `explain_memory()`, `explain_batch()` | Query API for debugging |
| `retention.py` | 507 | 2.2.4 | Audit retention wiring. Enforces 90-day raw retention with aggregation before deletion. Creates daily summaries. | `DailyAuditSummary`, `AuditRetentionService`, `run_retention()`, `aggregate_daily()` | Retention job |
| `erasure.py` | 756 | 2.2.5 | GDPR erasure hooks. Implements right-to-erasure with three scopes: ACTOR_DATA, ALL_MENTIONS, FULL_PURGE. | `ErasureScope` (3 values), `ErasureResult`, `ErasureService`, `erase_actor()` | GDPR compliance |
| `gap_emitter.py` | 461 | M3 (uses 2.3.2) | Gap emission for P06 Active Learning. Base class for gap detection and queue persistence. | `GapType` (7 values), `P03GapEmitterConfig`, `GapEmitResult`, `P03GapEmitter`, `emit_gaps()` | R8 gap emission base |
| `outbox_publisher.py` | ~400 | M3 (uses 2.1.11) | Outbox drain service. Publishes staged events from st_outbox to bus. | `OutboxPublisher`, `publish_pending()`, `drain()` | R8 outbox drain |
| `feedback_consumer.py` | ~500 | M3 (uses 2.3.8) | Feedback signal consumption. Reads from st_feedback_signals for P03 incorporation. | `FeedbackConsumer`, `consume()`, `mark_consumed()` | R0 feedback integration |

---

##### M2 Test Files in `tests/k0/pipelines/p03/`

| File | Tests | Issue | Description |
|------|-------|-------|-------------|
| `test_p03_storage_migrations.py` | 42 | 2.1.x | Tests for all M2 migrations (table creation, constraints, indexes) |
| `test_p03_audit_logger.py` | ~20 | 2.2.2 | Tests for audit logging, serialization, idempotency |
| `test_p03_explainability.py` | ~15 | 2.2.3 | Tests for explanation queries, default explanations |
| `test_p03_retention.py` | ~15 | 2.2.4 | Tests for retention enforcement, aggregation |
| `test_p03_erasure.py` | ~20 | 2.2.5 | Tests for GDPR erasure, scope handling |
| `test_p03_gap_emitter.py` | 559 | 3.2.3 | Tests for gap emission, deduplication, priority |
| `test_p03_outbox_publisher.py` | 606 | 3.1.3 | Tests for outbox drain, retry, DLQ |
| `test_p03_feedback_consumer.py` | 480 | 3.2.6 | Tests for feedback consumption, routing |

---

#### M3 Deliverables (DB ↔ Outbox ↔ Bus Wiring) — 9 Issues, 11 Files

**Epic 3.1 — R7/R8 Phase Implementation + Outbox Integration**

| Issue | File | Lines | Key Classes | M5 Usage |
|-------|------|-------|-------------|----------|
| 3.1.1 | `k0/pipelines/p03/phases/r7_truth_writer.py` | 604 | `R7TruthWriter`, `LAYER_PK_MAP` | **EXTEND** via 5.2.W1 |
| 3.1.2 | `k0/pipelines/p03/phases/r8_event_emitter.py` | 564 | `R8EventEmitter`, topics | **EXTEND** via 5.2.W2 |
| 3.1.3 | `k0/pipelines/p03/outbox_publisher.py` | 386 | `P03OutboxPublisher`, `OutboxPublisherConfig`, `PublishResult` | Outbox drain |
| 3.1.4 | `tests/k0/pipelines/p03/test_r7_r8_integration.py` | 898 | `TestR7Atomicity`, `TestR8Completion`, `TestEndToEndPipeline` | Integration tests |

**Epic 3.2 — Cross-Pipeline Integration**

| Issue | File | Lines | Key Classes | M5 Usage |
|-------|------|-------|-------------|----------|
| 3.2.1 | `k0/pipelines/p03/phases/r0_batch_selector.py` | 501 | `R0BatchSelector`, `R0Config` | Entry point |
| 3.2.2 | (in r7_truth_writer.py) | — | `_writeback_status()`, `_determine_status()` | Status writeback |
| 3.2.3 | `k0/pipelines/p03/gap_emitter.py` | 461 | `P03GapEmitter`, `GapType` (7 values), `GAP_PRIORITY_MAP` | R8 gap emission |
| 3.2.4 | N/A — Pipelines run independently | — | — | — |
| 3.2.5 | N/A — Event-driven, no circuit breaker needed | — | — | — |
| 3.2.6 | `k0/pipelines/p03/feedback_consumer.py` | 458 | `P03FeedbackConsumer`, `FeedbackType` (6 values), `P03FeedbackSubscriber` | P21 feedback |
| 3.2.7 | `tests/k0/pipelines/p03/test_cross_pipeline_integration.py` | 939 | `TestP02ToP03Handoff`, `TestP03ToP06GapEmission`, `TestP21ToP03Feedback` | Cross-pipeline tests |

**M3 Test Files**

| Test File | Lines | Issue | Classes |
|-----------|-------|-------|---------|
| `test_p03_r0_batch_selector.py` | 512 | 3.2.1 | `TestR0OffsetHandling`, `TestR0BatchSelection`, `TestR0Config` |
| `test_p03_r7_truth_writer.py` | 864 | 3.1.1+3.2.2 | `TestR7Execution`, `TestStatusWriteback`, `TestStatusTransitionValidation` |
| `test_p03_r8_event_emitter.py` | 618 | 3.1.2 | `TestR8SuccessPath`, `TestCompletionPayload`, `TestGapHandling` |
| `test_p03_outbox_publisher.py` | 606 | 3.1.3 | `TestDrainBatch`, `TestExponentialBackoff`, `TestDLQEscalation` |
| `test_p03_gap_emitter.py` | 559 | 3.2.3 | `TestGapType`, `TestGapPriority`, `TestDeduplication`, `TestPersistence` |
| `test_p03_feedback_consumer.py` | 480 | 3.2.6 | `TestP03FeedbackPayload`, `TestFeedbackRouting`, `TestMetrics` |
| `test_r7_r8_integration.py` | 898 | 3.1.4 | `TestR7Atomicity`, `TestR8Completion`, `TestOutboxPublisherIntegration` |
| `test_cross_pipeline_integration.py` | 939 | 3.2.7 | `TestP02ToP03Handoff`, `TestP03ToP06GapEmission`, `TestP21ToP03Feedback` |

**M3 Key Patterns for M5 Extension**

| Pattern | Location | M5 Reuses |
|---------|----------|-----------|
| `LAYER_PK_MAP` | `r7_truth_writer.py:44-56` | Issue 5.2.W1 — layer routing |
| UoW context pattern | `r7_truth_writer.py:95-120` | Issue 5.2.10 — TransactionCoordinator |
| `_execute_single_write()` | `r7_truth_writer.py:230-335` | Issue 5.2.W1 — deprecate, replace with router |
| Completion payload building | `r8_event_emitter.py:170-225` | Issue 5.2.11 — EventEmitter |
| Gap fingerprint pattern | `gap_emitter.py:160-200` | Issue 5.2.12 — GapEmitterModule |

**M3 Summary**: 9 completed issues (2 N/A), 11 production files, 8 test files (5,476 test lines), 2,974 production lines

---

#### M4 Deliverables (R1-R4 Core Cognition) — Verified File Inventory

**Scope**: 40 issues across 4 epics (R1 Importance + Hebbian, R2 DBSCAN Clustering, R3 Dedup + Decay, R4 Entity Resolution + KG)

**Architecture Decision (M4_EXECUTION.md A.5)**: Algorithms placed in `k0/modules/consolidation/algorithms/` for reusability across pipelines, NOT in `k0/pipelines/p03/`.

---

**Phase Coordinators in `k0/pipelines/p03/phases/` (4 files, 2,887 lines):**

| Phase File | Lines | Epic | Key Classes | Purpose |
|------------|-------|------|-------------|---------|
| `r1_importance_scorer.py` | 281 | 4.1 | `R1ImportanceScorer` | Calls algorithm, populates `importance_score`, `affect_factor`, `novelty_factor` |
| `r2_episodic_integrator.py` | 620 | 4.2 | `R2EpisodicIntegrator` | Calls DBSCAN, populates `cluster_id`, `cluster_label`, `cohesion_score` |
| `r3_dedup_decay.py` | 962 | 4.3 | `R3DedupDecay` | Calls dedup + decay, populates `is_duplicate`, `decay_score`, `prune_decision` |
| `r4_kg_consolidator.py` | 1024 | 4.4 | `R4KGConsolidator` | Entity extraction → disambiguation → merge → KG edges |

---

**Algorithms in `k0/modules/consolidation/algorithms/` (30 files, ~14,000 lines):**

**Epic 4.1 — R1 Importance + Hebbian Learning (3 files, 1,894 lines):**

| Algorithm File | Lines | Issue | Key Classes | M5 Relevance |
|----------------|-------|-------|-------------|--------------|
| `importance_scorer.py` | 707 | 4.1.1 | `ImportanceScorer`, `ImportanceWeights`, `ImportanceBreakdown` | Input to R6 staging |
| `hebbian_learner.py` | 597 | 4.1.3 | `HebbianLearner`, `HebbianConfig`, `CoOccurrence`, `EdgeUpdate` | Edge weights for R7 |
| `importance_weight_learner.py` | 590 | 4.1.4 | `ImportanceWeightLearner`, `WeightLearnerConfig` | Adaptive weight learning |

**Epic 4.2 — R2 DBSCAN Clustering (7 files, 2,604 lines):**

| Algorithm File | Lines | Issue | Key Classes | M5 Relevance |
|----------------|-------|-------|-------------|--------------|
| `composite_distance.py` | 355 | 4.2.2 | `CompositeDistance`, `DBSCANParams` | Distance metric for clustering |
| `episode_splitter.py` | 367 | 4.2.1 | `EpisodeSplitter` | Temporal splitting |
| `episodic_dbscan.py` | 365 | 4.2.3 | `EpisodicDBSCAN` | DBSCAN clustering algorithm |
| `centroid_calculator.py` | 470 | 4.2.4 | `CentroidCalculator` | Cluster centroid computation |
| `cluster_quality.py` | 415 | 4.2.5 | `ClusterQuality` | Silhouette scoring |
| `eps_adjuster.py` | 333 | 4.2.6 | `EpsAdjuster` | Adaptive epsilon tuning |
| `min_samples_adjuster.py` | 299 | 4.2.7 | `MinSamplesAdjuster` | Adaptive min_samples tuning |

**Epic 4.3 — R3 Dedup + Decay (11 files, 4,499 lines):**

| Algorithm File | Lines | Issue | Key Classes | M5 Relevance |
|----------------|-------|-------|-------------|--------------|
| `simhasher.py` | 158 | 4.3.1 | `SimHasher` | SimHash fingerprinting |
| `minhash_lsh.py` | 625 | 4.3.1 | `MinHashLSH` | MinHash + LSH |
| `two_stage_dedup.py` | 303 | 4.3.2 | `TwoStageDedup` | Two-stage deduplication |
| `duplicate_detector.py` | 416 | 4.3.2 | `DuplicateDetector` | Near-duplicate detection |
| `decay_engine.py` | 365 | 4.3.3 | `UnifiedDecayEngine`, `DecayConfig` | Unified decay scoring |
| `immunity_checker.py` | 369 | 4.3.4 | `ImmunityChecker` | Decay immunity logic |
| `retention_enforcer.py` | 438 | 4.3.5 | `RetentionEnforcer` | Retention policy enforcement |
| `access_tracker.py` | 470 | 4.3.6 | `AccessTracker` | Access pattern tracking |
| `novelty_bonus_learner.py` | 347 | 4.3.7 | `NoveltyBonusLearner` | Novelty learning |
| `prune_audit_logger.py` | 498 | 4.3.8 | `PruneAuditLogger` | Prune audit logging |
| `prune_regret_detector.py` | 510 | 4.3.9 | `PruneRegretDetector` | Regret detection + feedback |

**Epic 4.4 — R4 Entity Resolution + KG (9 files, 5,110 lines):**

| Algorithm File | Lines | Issue | Key Classes | M5 Relevance |
|----------------|-------|-------|-------------|--------------|
| `entity_extractor.py` | 410 | 4.4.1 | `EntityExtractor` | Entity extraction from text |
| `entity_disambiguator.py` | 803 | 4.4.2 | `EntityDisambiguator` | Entity disambiguation |
| `entity_merger.py` | 934 | 4.4.3 | `EntityMerger` | Entity merging |
| `ambiguous_resolver.py` | 623 | 4.4.4 | `AmbiguousResolver` | Ambiguity resolution |
| `confidence_router.py` | 536 | 4.4.5 | `ConfidenceRouter` | Confidence band routing |
| `merge_threshold_learner.py` | 461 | 4.4.6 | `MergeThresholdLearner` | Adaptive merge thresholds |
| `granger_causality.py` | 403 | 4.4.7a | `GrangerCausalityInference` | Causal edge inference |
| `causality_thresholds.py` | 376 | 4.4.7b | `CausalityThresholds` | Causality thresholds |
| `edge_demotion.py` | 564 | 4.4.7c | `EdgeDemotion` | Edge demotion logic |

---

**M4 Test Files (37 files, 17,324 lines):**

**R1 Tests (6 files, 2,905 lines):**

| Test File | Lines | Coverage |
|-----------|-------|----------|
| `test_r1_importance_scorer.py` | 638 | ImportanceScorer, weights, factors |
| `test_r1_hebbian_learner.py` | 759 | HebbianLearner, co-occurrence |
| `test_r1_importance_learner.py` | 391 | Weight learning adaptation |
| `test_r1_cold_start.py` | 382 | Cold-start scenarios |
| `test_r1_metrics.py` | 441 | R1 phase metrics |
| `test_r1_phase_integration.py` | 294 | R1 integration tests |

**R2 Tests (8 files, 2,471 lines):**

| Test File | Lines | Coverage |
|-----------|-------|----------|
| `test_r2_episodic_dbscan.py` | 370 | DBSCAN clustering |
| `test_r2_composite_distance.py` | 260 | Distance metrics |
| `test_r2_episode_splitter.py` | 397 | Temporal splitting |
| `test_r2_centroid_calculator.py` | 369 | Centroid computation |
| `test_r2_cluster_quality.py` | 287 | Silhouette scoring |
| `test_r2_eps_adjuster.py` | 259 | Epsilon adaptation |
| `test_r2_min_samples_adjuster.py` | 214 | Min samples adaptation |
| `test_r2_integration.py` | 315 | R2 integration tests |

**R3 Tests (12 files, 5,994 lines):**

| Test File | Lines | Coverage |
|-----------|-------|----------|
| `test_r3_simhasher.py` | 230 | SimHash fingerprinting |
| `test_r3_minhash_lsh.py` | 462 | MinHash + LSH |
| `test_r3_two_stage_dedup.py` | 446 | Two-stage dedup |
| `test_r3_duplicate_detector.py` | 542 | Near-duplicate detection |
| `test_r3_decay_engine.py` | 550 | Decay scoring |
| `test_r3_immunity_checker.py` | 432 | Immunity logic |
| `test_r3_retention_enforcer.py` | 562 | Retention policies |
| `test_r3_access_tracker.py` | 420 | Access tracking |
| `test_r3_novelty_learner.py` | 386 | Novelty learning |
| `test_r3_prune_audit.py` | 700 | Prune audit logging |
| `test_r3_prune_regret.py` | 718 | Regret detection |
| `test_r3_integration.py` | 546 | R3 integration tests |

**R4 Tests (11 files, 5,954 lines):**

| Test File | Lines | Coverage |
|-----------|-------|----------|
| `test_r4_entity_extractor.py` | 524 | Entity extraction |
| `test_r4_disambiguator.py` | 519 | Entity disambiguation |
| `test_r4_entity_merger.py` | 531 | Entity merging |
| `test_r4_ambiguous_resolver.py` | 563 | Ambiguity resolution |
| `test_r4_confidence_router.py` | 515 | Confidence routing |
| `test_r4_merge_thresholds.py` | 329 | Threshold learning |
| `test_r4_granger_causality.py` | 643 | Causal inference |
| `test_r4_causality_thresholds.py` | 439 | Causality thresholds |
| `test_r4_edge_demotion.py` | 621 | Edge demotion |
| `test_r4_kg_consolidator.py` | 550 | R4 phase tests |
| `test_r4_integration.py` | 720 | R4 integration tests |

---

**M4 Patterns for M5 Extension:**

| Pattern | M4 Location | M5 Usage |
|---------|-------------|----------|
| Phase coordinator imports algorithms | `r1_importance_scorer.py:30-35` | R6/R7/R8 import from M4 algorithms |
| Event state field population | `r2_episodic_integrator.py:150-180` | R6 populates consolidation_status |
| Batch processing with stats | `r3_dedup_decay.py:200-250` | R6/R7/R8 batch processing |
| Skip condition checking | `r4_kg_consolidator.py:100-130` | R6/R7/R8 skip conditions |
| Phase output dataclass | `k0/pipelines/p03/phase_outputs.py` | R6/R7/R8 output dataclasses |

**M4 Summary**: 40 completed issues, 30 algorithm files (14,107 lines), 4 phase files (2,887 lines), 37 test files (17,324 lines)

#### K0 Core Infrastructure (Pre-existing)

| Component | Path | Purpose |
|-----------|------|---------|
| UnitOfWork | `k0/uow/unit_of_work.py` | Transactional scope with `stage_outbox()`, `upsert_offset()` |
| OutboxStore | `k0/storage/outbox.py` | OutboxEntry dataclass, enqueue/dequeue methods |
| OffsetStore | `k0/storage/offsets.py` | Offset dataclass, upsert/fetch methods |
| BusDispatcher | `k0/bus/core.py` | Event publishing to bus |
| DLQStore | `k0/storage/dlq.py` | Dead letter queue storage |

#### Test Counts (Cumulative)

| Milestone | Tests Added | Cumulative |
|-----------|-------------|------------|
| M1 | 399 | 399 |
| M2 | 500 | 899 |
| M3 | TBD | TBD |
| M4 | 2000+ | 2900+ |

### A.1 Dossier Sections Governing This Milestone

| Section | Title | Link | Why Needed |
|---------|-------|------|------------|
| §4.7 | R6 — Staging Table Updates | [Dossier §4.7](../pipelines/P03_consolidation_dossier_v2.md#47-r6--staging-table-updates) | R6 staging logic |
| §4.7.1 | Consolidation Status Marking | [Dossier §4.7.1](../pipelines/P03_consolidation_dossier_v2.md#471-consolidation-status-marking) | Status assignment |
| §4.7.2 | Deduplication Metadata | [Dossier §4.7.2](../pipelines/P03_consolidation_dossier_v2.md#472-deduplication-metadata) | Near-duplicates JSON |
| §4.7.3 | Reconciliation Decision Recording | [Dossier §4.7.3](../pipelines/P03_consolidation_dossier_v2.md#473-reconciliation-decision-recording) | Decision audit |
| §4.8 | R7 — Memory Layer Writes | [Dossier §4.8](../pipelines/P03_consolidation_dossier_v2.md#48-r7--memory-layer-writes-truth-update) | TruthWriter logic |
| §4.8.1 | Outbox Pattern Implementation | [Dossier §4.8.1](../pipelines/P03_consolidation_dossier_v2.md#481-outbox-implementation) | Transactional writes |
| §4.8.2–4.8.8 | Per-Layer Write Specs | [Dossier §4.8](../pipelines/P03_consolidation_dossier_v2.md#48-r7--memory-layer-writes-truth-update) | Layer-specific writes |
| §4.9 | R8 — Event Emission | [Dossier §4.9](../pipelines/P03_consolidation_dossier_v2.md#49-r8-event-emission) | Bus emission |
| §4.9.1 | Bus Event Emission | [Dossier §4.9.1](../pipelines/P03_consolidation_dossier_v2.md#491-bus-event-emission) | Event types |
| §4.9.2 | Pipeline Offset Updates | [Dossier §4.9.2](../pipelines/P03_consolidation_dossier_v2.md#492-pipeline-offset-updates) | Checkpoint |
| §6.15 | st_outbox | [Dossier §6.15](../pipelines/P03_consolidation_dossier_v2.md#615-st_outbox) | Outbox schema |
| §9.3 | P03 → P06 Contract | [Dossier §9.3](../pipelines/P03_consolidation_dossier_v2.md#93-p03-p06-contract) | Gap emission |
| §12.2.3 | Idempotency Key Design | [Dossier §12.2.3](../pipelines/P03_consolidation_dossier_v2.md#1223-idempotency-key-design) | Key format |
| Appendix G | R0-R8 State Machine Spec | [Dossier Appendix G](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) | Phase states |
| Appendix G.3 | State Transition Rules | [Dossier Appendix G.3](../pipelines/P03_consolidation_dossier_v2.md#g3-state-transition-rules) | Transitions |
| Appendix G.4 | Error Recovery Matrix | [Dossier Appendix G.4](../pipelines/P03_consolidation_dossier_v2.md#g4-error-recovery-matrix) | Retry logic |
| Appendix G.5 | Metrics Per Phase | [Dossier Appendix G.5](../pipelines/P03_consolidation_dossier_v2.md#g5-phase-metrics) | R6/R7/R8 metrics |

### A.2 ADRs to Reference

| ADR | Path | Governs |
|-----|------|---------|
| K010 | [k010-p03-consolidation-architecture.md](../architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md) | P03 pipeline architecture |
| K010.1 | [k010.1-sleep-cycle-state-machine.md](../architecture/decisions-K0/pipelines/k010.1-sleep-cycle-state-machine.md) | R0-R8 state machine |
| K002 | [k002-idempotency-toctou-race-fix.md](../architecture/decisions-K0/k002-idempotency-toctou-race-fix.md) | Idempotency patterns |
| K004 | [k004-capability-mesh-architecture.md](../architecture/decisions-K0/k004-capability-mesh-architecture.md) | Capability model |

### A.3 Governance Sync Tool

| Tool | Command |
|------|---------|
| Sync Script | `python -m governance.k0.scripts.sync --report` |

**When To Run Governance Sync**:

- ✅ Before starting any Epic (capture baseline)
- ✅ After completing any Epic (verify no drift)
- ✅ Before marking M5 complete (final verification)

---

## Part B: What M5 ACTUALLY Needs To Do

### B.1 M5 Scope Definition (Post-Duplication Analysis)

**M5 Goal**: Implement R6 (Staging), complete R7 (TruthWriter), and R8 (Event Emission) to finalize the consolidation cycle.

**R5 Phase Clarification**:

> **R5_DREAM (Dream Exploration)** is **OPTIONAL** and deferred to post-MVP milestone.
> Per `runner_contract.py:81`, transition R4 → R6 skips R5 when not implemented.
> R5 implements counterfactual reasoning and creative insight generation — not required for core consolidation.
> See: Dossier §4.6 "R5 — Dream Exploration (Optional)"

**What M5 Does NOT Do** (already exists from M3):

| Component | Status | Where It Exists |
|-----------|--------|-----------------|
| R7TruthWriter (basic) | M3 Complete | `k0/pipelines/p03/phases/r7_truth_writer.py` |
| R8EventEmitter (basic) | M3 Complete | `k0/pipelines/p03/phases/r8_event_emitter.py` |
| GapEmitter | M3 Complete | `k0/pipelines/p03/gap_emitter.py` |
| OutboxPublisher | M3 Complete | `k0/pipelines/p03/outbox_publisher.py` |
| P03StagedWrites container | M1 Complete | `k0/pipelines/p03/staged_writes.py` |
| UnitOfWork.stage_outbox() | Pre-existing | `k0/uow/unit_of_work.py` |

**What M5 MUST Do** (new work):

| Component | Description | Epic |
|-----------|-------------|------|
| **R6Output dataclass** | Accumulate all staged writes from R1-R5 | 5.1 |
| **StagedWritesContainer** | Manage staged writes with serialization | 5.1 |
| **ConsolidationStatusMarker** | Assign status to each event | 5.1 |
| **DedupMetadataPopulator** | Populate near_duplicates_json | 5.1 |
| **ReconciliationRecorder** | Record decision audit trail | 5.1 |
| **IdempotencyKeyGenerator** | Generate R6/R7/R8 idempotency keys | 5.1 |
| **StagedTruthAssembler** | Assemble per-layer writes | 5.1 |
| **StagedKGAssembler** | Assemble KG entity/edge writes | 5.1 |
| **StagedOutboxAssembler** | Assemble outbox events | 5.1 |
| **ManifestValidator** | Validate R6Output before R7 | 5.1 |
| **ReconciliationSummary** | Aggregate cycle statistics | 5.1 |
| **R6Coordinator** | Orchestrate R6 phase | 5.1 |
| **Per-Layer Writers** | EpisodicLayerWriter, SemanticLayerWriter, etc. | 5.2 |
| **KGLayerWriter** | Entity + edge persistence | 5.2 |
| **VectorLayerWriter** | Embedding persistence + P08 coordination | 5.2 |
| **EventEmitter (full)** | All event types per dossier | 5.2 |
| **GapEmitter (full)** | All gap types + deduplication | 5.2 |
| **OffsetManager** | Offset + checkpoint persistence | 5.2 |
| **MetricsAggregator** | Cycle metrics emission | 5.2 |
| **R7R8Coordinator** | Orchestrate R7/R8 phases | 5.2 |

### B.2 Wiring Architecture

**The Problem**: M5 creates NEW algorithm modules in `k0/modules/consolidation/staging/` and `k0/modules/consolidation/truth_writer/`, but these must wire into EXISTING phase files in `k0/pipelines/p03/phases/`.

```text
                    EXISTING (M3/M4)                         NEW (M5)
                    ================                         ========

k0/pipelines/p03/phases/                    k0/modules/consolidation/
├── r0_batch_selector.py                    ├── staging/
├── r1_importance_scorer.py                 │   ├── r6_output.py
├── r2_episodic_integrator.py    ──────►    │   ├── status_marker.py
├── r3_dedup_decay.py            outputs    │   ├── dedup_metadata.py
├── r4_kg_consolidator.py        ──────►    │   ├── truth_assembler.py
│                                           │   ├── kg_assembler.py
│   [R6 PHASE FILE MISSING!]    ◄────────   │   └── r6_coordinator.py
│                                           │
├── r7_truth_writer.py          ◄────────   └── truth_writer/
│   (604 lines, inline SQL)      wire to        ├── layers/episodic.py
│   MUST CALL layer writers ─────────────►      ├── layers/semantic.py
│                                               └── ...
└── r8_event_emitter.py         ◄────────   └── emission/
    MUST CALL emitters ──────────────────►      ├── emitter.py
                                                └── gap_emitter.py
```

**Wiring Issues Required**:

1. **Create R6 phase file** (`r6_staging.py`) that implements `P03PhaseProtocol` and calls `R6Coordinator`
2. **Update SequentialRunner** to call R6 between R4/R5 and R7
3. **Extend R7 phase** to call new layer writers instead of inline SQL
4. **Extend R8 phase** to call new emitters instead of inline code
5. **Register R6** in `PHASE_CONTRACTS` and `P03PhaseId` enum

### B.3 Directory Structure for M5

```text
k0/modules/consolidation/
├── staging/                       # NEW - R6 components
│   ├── __init__.py
│   ├── r6_output.py               # R6Output, StagedWrite dataclasses
│   ├── container.py               # StagedWritesContainer
│   ├── status_marker.py           # ConsolidationStatusMarker
│   ├── dedup_metadata.py          # DedupMetadataPopulator
│   ├── reconciliation_recorder.py # ReconciliationRecorder
│   ├── idempotency.py             # IdempotencyKeyGenerator
│   ├── truth_assembler.py         # StagedTruthAssembler
│   ├── kg_assembler.py            # StagedKGAssembler
│   ├── outbox_assembler.py        # StagedOutboxAssembler
│   ├── manifest_validator.py      # ManifestValidator
│   ├── summary.py                 # ReconciliationSummary
│   └── r6_coordinator.py          # R6Coordinator
├── truth_writer/                  # NEW - R7 components
│   ├── __init__.py
│   ├── writer.py                  # TruthWriter (extended)
│   ├── outbox.py                  # OutboxWriter
│   ├── result.py                  # WriteResult
│   ├── transaction.py             # TransactionCoordinator
│   ├── r7r8_coordinator.py        # R7R8Coordinator
│   └── layers/                    # Per-layer writers
│       ├── __init__.py
│       ├── episodic.py            # EpisodicLayerWriter
│       ├── semantic.py            # SemanticLayerWriter
│       ├── procedural.py          # ProceduralLayerWriter
│       ├── social.py              # SocialLayerWriter
│       ├── prospective.py         # ProspectiveLayerWriter
│       ├── kg.py                  # KGLayerWriter
│       └── vector.py              # VectorLayerWriter
└── emission/                      # NEW - R8 components
    ├── __init__.py
    ├── emitter.py                 # EventEmitter
    ├── gap_emitter.py             # GapEmitter (extended)
    ├── offset_manager.py          # OffsetManager
    └── metrics.py                 # MetricsAggregator
```

---

## Part C: Epic Execution

### Epic 5.1 — R6 Staging and Manifests

> **Scope**: Implement the R6 phase that accumulates all staged writes from R1-R5 phases, validates them, and prepares them for atomic commit in R7.
>
> **Key Insight**: R6 is the "staging area" where all cognition decisions become concrete write operations with idempotency keys.
>
> **Dossier Reference**: Section 4.7 "R6 — Staging Table Updates", Appendix G "R6Output dataclass"

#### Epic 5.1 Issues Summary

**Algorithm Issues (5.1.1-5.1.12)** — Core R6 staging logic in `k0/modules/consolidation/staging/`:

| Issue | Title | Goal |
|-------|-------|------|
| 5.0.1 | Module package setup | Create staging/truth_writer/emission packages with `__init__.py` |
| 5.1.1 | R6Output dataclass and StagedWritesContainer | Core R6Output dataclass for staged writes |
| 5.1.2 | Consolidation status marking logic | Assign CONSOLIDATED/DUPLICATE/PRUNED/PENDING_REVIEW |
| 5.1.3 | Deduplication metadata population | Populate near_duplicates_json from M19 |
| 5.1.4 | Reconciliation decision recording | Record decision audit trail with similarity scores |
| 5.1.5 | Idempotency key generation for R6 | Generate keys per dossier format |
| 5.1.6 | Staged truth writes assembly | Per-layer write assembly for all 8 layers |
| 5.1.7 | Staged KG writes assembly | Entity + edge write assembly from M21 |
| 5.1.8 | Staged outbox events assembly | Outbox event assembly for R8 |
| 5.1.9 | Manifest validation before commit | Validate R6Output completeness and consistency |
| 5.1.10 | ReconciliationSummary generation | Aggregate cycle statistics |
| 5.1.11 | R6 phase coordinator | Orchestrate all R6 sub-components |
| 5.1.12 | R6 staging unit and integration tests | ≥90% coverage for staging module |

**Wiring Issues (5.1.13-5.1.18)** — Connect staging module to pipeline infrastructure:

| Issue | Title | Goal |
|-------|-------|------|
| 5.1.13 | R6 Phase file implementation | Create `r6_staging.py` implementing P03PhaseProtocol |
| 5.1.14 | R6 accepts R1-R4 outputs | Wire R6 to read from P03BatchEnvelope |
| 5.1.15 | R6 outputs to P03StagedWrites | Wire R6 to populate envelope.staged |
| 5.1.16 | Update P03SequentialRunner for R6 | Register R6 in runner execution |
| 5.1.17 | R6 phase contract registration | Update PHASE_CONTRACTS with R6 |
| 5.1.18 | R6 wiring integration tests | End-to-end R6 pipeline tests |

---

#### Issue 5.0.1 — Module package setup

**Status**: NOT_STARTED

**Goal**: Create the module package structure for M5's new consolidation sub-modules with proper `__init__.py` files.

**Dossier References**:

- N/A (infrastructure setup)

**M4 Architecture Decision (A.5)**: Algorithms in `k0/modules/consolidation/` for reusability. M5 extends with:
- `staging/` — R6 staging logic
- `truth_writer/` — R7 layer writers
- `emission/` — R8 event emitters

**Directories To Create**:

```
k0/modules/consolidation/
├── staging/
│   └── __init__.py
├── truth_writer/
│   ├── __init__.py
│   └── layers/
│       └── __init__.py
└── emission/
    └── __init__.py
```

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/modules/consolidation/staging/__init__.py` | Package init with exports |
| `k0/modules/consolidation/truth_writer/__init__.py` | Package init with exports |
| `k0/modules/consolidation/truth_writer/layers/__init__.py` | Layer writers package |
| `k0/modules/consolidation/emission/__init__.py` | Package init with exports |

**Deliverables**:

1. **staging/__init__.py**:

   ```python
   """
   R6 Staging Module — Issue 5.0.1

   Provides components for R6 phase: accumulate staged writes,
   validate, and prepare for atomic R7 commit.
   """

   from k0.modules.consolidation.staging.r6_output import (
       R6Output,
       StagedEventUpdate,
       StagedWritesContainer,
   )
   from k0.modules.consolidation.staging.status_marker import ConsolidationStatusMarker
   from k0.modules.consolidation.staging.r6_coordinator import R6Coordinator

   __all__ = [
       "R6Output",
       "StagedEventUpdate",
       "StagedWritesContainer",
       "ConsolidationStatusMarker",
       "R6Coordinator",
   ]
   ```

2. **truth_writer/__init__.py** and **emission/__init__.py** follow same pattern.

**Acceptance Criteria**:

- [ ] All 4 `__init__.py` files created
- [ ] Imports work: `from k0.modules.consolidation.staging import R6Output`
- [ ] No circular import issues
- [ ] Follows M4 `algorithms/__init__.py` pattern

**Test**: Verify imports work after first component is created.

---

#### Issue 5.1.1 — R6Output dataclass and StagedWritesContainer

**Status**: NOT_STARTED

**Goal**: Create the core R6Output dataclass that encapsulates all staged writes from R1-R5 phases for atomic commit in R7.

**Dossier References**:

- [Dossier §4.7](../pipelines/P03_consolidation_dossier_v2.md#47-r6--staging-table-updates) — R6 Staging Table Updates
- [Dossier Appendix G](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R6Output specification

**Implementation Plan Reference**:

- [P03_implementation_plan_skeleton.md Issue 5.1.1](../pipelines/P03_implementation_plan_skeleton.md) (lines 2450-2474)

**Existing Code Dependencies**:

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `k0/pipelines/p03/staged_writes.py` (587 lines) | **EXTENDS** — Existing staged writes container | `P03StagedWrites`, `StagedWrite`, `WriteOperation`, `StagedOutboxEvent`, `VALID_LAYERS` |
| `k0/pipelines/p03/phase_outputs.py` (666 lines) | **READS** — R1-R5 output types | `ScoredEvent`, `EpisodeCluster`, `DedupMerge`, `KGEntity`, `KGEdge`, `GapCandidate` |
| `k0/pipelines/p03/event_state.py` (531 lines) | **READS** — Per-event reconciliation state | `P03EventState`, `ReconciliationAction`, `PruneDecision` |
| `k0/pipelines/p03/context.py` | **READS** — Cycle context for IDs | `generate_ulid()`, `P03CycleContext` |

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/modules/consolidation/staging/__init__.py` | Package init |
| `k0/modules/consolidation/staging/r6_output.py` | R6Output dataclass, StagedWritesContainer |

**Deliverables**:

1. **R6Output dataclass** with fields:
   - `staged_event_updates: List[StagedEventUpdate]` — Per-event status updates for st_hipp_events
   - `staged_truth_writes: List[StagedWrite]` — Truth table writes (using existing `StagedWrite`)
   - `staged_kg_writes: List[StagedWrite]` — KG entity/edge writes
   - `staged_outbox_events: List[StagedOutboxEvent]` — Outbox events for R8 (using existing)
   - `reconciliation_summary: ReconciliationSummary` — Cycle statistics
   - `cycle_ulid: str` — Cycle identifier for idempotency
   - `created_at_ms: int` — Timestamp (milliseconds)

2. **StagedEventUpdate dataclass** with fields:
   - `event_id: str` — st_hipp_events.event_id
   - `consolidation_status: str` — CONSOLIDATED/DUPLICATE/PRUNED/PENDING_REVIEW
   - `near_duplicates_json: str` — JSON array of near-duplicate event_ids
   - `novelty_score: float` — Computed novelty [0, 1]
   - `episode_cluster_id: Optional[str]` — Cluster assignment from R2
   - `reconciliation_action: str` — Decision type (REINFORCE, EXTEND, etc.)
   - `best_match_id: Optional[str]` — Matched truth record ID
   - `best_match_layer: Optional[str]` — Truth layer of match

3. **StagedWritesContainer class** with methods:
   - `add_event_update(update: StagedEventUpdate) -> None`
   - `add_truth_write(write: StagedWrite) -> None`
   - `add_kg_write(write: StagedWrite) -> None`
   - `add_outbox_event(event: StagedOutboxEvent) -> None`
   - `get_all_writes_ordered() -> List[StagedWrite]` — Dependency-ordered writes
   - `to_r6_output() -> R6Output` — Finalize container to frozen R6Output
   - `to_json() -> str` — JSON serialization for checkpoint

**Acceptance Criteria**:

- [ ] R6Output is frozen (immutable after creation)
- [ ] StagedEventUpdate contains all fields from Dossier §4.7.1-4.7.3
- [ ] StagedWritesContainer reuses `StagedWrite` and `StagedOutboxEvent` from `staged_writes.py`
- [ ] Dependency order follows: vec → kg_dom → kg_edges → epi → sem → procedural → social → prospective → learning_queue → hipp_events
- [ ] JSON serialization round-trips correctly
- [ ] All dataclasses are hashable (for deduplication)

**Test File**: `tests/k0/modules/consolidation/staging/test_r6_output.py`

---

#### Issue 5.1.2 — Consolidation status marking logic

**Status**: NOT_STARTED

**Goal**: Implement logic to determine and assign consolidation_status to each processed event based on R1-R5 outcomes.

**Dossier References**:

- [Dossier §4.7.1](../pipelines/P03_consolidation_dossier_v2.md#471-consolidation-status-marking) — Consolidation Status Marking
- [Dossier §4.7](../pipelines/P03_consolidation_dossier_v2.md#47-r6--staging-table-updates) — R6 Overview

**Implementation Plan Reference**:

- [P03_implementation_plan_skeleton.md Issue 5.1.2](../pipelines/P03_implementation_plan_skeleton.md) (lines 2476-2504)

**Existing Code Dependencies**:

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `k0/pipelines/p03/event_state.py` (531 lines) | **READS** — Event reconciliation state | `P03EventState.reconciliation_action`, `P03EventState.is_duplicate`, `P03EventState.prune_decision` |
| `k0/pipelines/p03/event_state.py:18-40` | **READS** — ReconciliationAction enum | `ReconciliationAction.REINFORCE`, `.EXTEND`, `.CREATE`, `.EVOLVE`, `.CONTRADICT`, `.PRUNE`, `.SKIP` |
| `k0/pipelines/p03/event_state.py:43-53` | **READS** — PruneDecision enum | `PruneDecision.KEEP`, `.ARCHIVE`, `.TOMBSTONE` |
| `k0/pipelines/p03/phases/r3_dedup_decay.py` (1149 lines) | **UNDERSTANDS** — How R3 sets reconciliation | `R3DedupDecayPhase._apply_reconciliation_decisions()` |

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/modules/consolidation/staging/status_marker.py` | ConsolidationStatusMarker class |

**Status Values** (from Dossier §4.7.1):

| Status | When Assigned | Source |
|--------|---------------|--------|
| `CONSOLIDATED` | Event successfully reconciled | `ReconciliationAction` in {REINFORCE, EXTEND, CREATE, EVOLVE} |
| `DUPLICATE` | Event is exact/near duplicate | `P03EventState.is_duplicate == True` or `ReconciliationAction.SKIP` with duplicate reason |
| `PRUNED` | Event decayed below threshold | `ReconciliationAction.PRUNE` or `PruneDecision` in {ARCHIVE, TOMBSTONE} |
| `PENDING_REVIEW` | Event flagged for P06 | `ReconciliationAction.CONTRADICT` or gap emitted |

**Deliverables**:

1. **ConsolidationStatusMarker class** in `status_marker.py`:

   ```python
   class ConsolidationStatusMarker:
       def mark_status(self, event_state: P03EventState) -> str:
           """Determine consolidation_status from event state."""
           ...

       def mark_batch(self, event_states: List[P03EventState]) -> Dict[str, str]:
           """Mark status for entire batch, returns {event_id: status}."""
           ...
   ```

2. **Status determination rules**:
   - Check `is_duplicate` first → DUPLICATE
   - Check `reconciliation_action == CONTRADICT` → PENDING_REVIEW
   - Check `reconciliation_action == PRUNE` → PRUNED
   - Check `reconciliation_action == SKIP` → determine if DUPLICATE or PRUNED based on reason
   - Otherwise → CONSOLIDATED

3. **Reasoning trace** for audit:
   - `status_reason: str` — Human-readable explanation of why this status
   - Links to source decision (R3 dedup, R3 decay, R4 gap emission, etc.)

**Acceptance Criteria**:

- [ ] All four status values correctly assigned based on P03EventState
- [ ] Status assignment is deterministic (same input → same output)
- [ ] Handles edge cases: partially processed events, timeout events
- [ ] Reasoning trace captures decision path for debugging
- [ ] 100% of ReconciliationAction values mapped to status

**Test File**: `tests/k0/modules/consolidation/staging/test_status_marker.py`

---

#### Issue 5.1.3 — Deduplication metadata population

**Status**: NOT_STARTED

**Goal**: Populate deduplication-related metadata fields on staged event updates from M19 DuplicateDetector results.

**Dossier References**:

- [Dossier §4.7.2](../pipelines/P03_consolidation_dossier_v2.md#472-deduplication-metadata) — Deduplication Metadata
- [Dossier §7.4.2](../pipelines/P03_consolidation_dossier_v2.md#742-m19-duplicatedetector) — M19 DuplicateDetector spec

**Implementation Plan Reference**:

- [P03_implementation_plan_skeleton.md Issue 5.1.3](../pipelines/P03_implementation_plan_skeleton.md) (lines 2506-2536)

**Existing Code Dependencies**:

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `k0/modules/consolidation/algorithms/duplicate_detector.py` (511 lines) | **READS** — Dedup results | `DuplicationResult`, `DuplicationResult.near_duplicates`, `DuplicationResult.novelty_score`, `DuplicationResult.bonuses` |
| `k0/modules/consolidation/algorithms/duplicate_detector.py:113-155` | **READS** — NoveltyBonuses breakdown | `NoveltyBonuses.first_occurrence`, `.milestone`, `.rare_pattern`, `.temporal_anomaly`, `.routine_penalty` |
| `k0/modules/consolidation/algorithms/duplicate_detector.py:157-184` | **READS** — DuplicationResult fields | `is_duplicate`, `near_duplicates`, `novelty_score`, `duplicate_of`, `match_method`, `max_similarity` |
| `k0/pipelines/p03/event_state.py:170-175` | **READS** — Event dedup fields | `P03EventState.is_duplicate`, `.duplicate_of_id`, `.hamming_distance` |
| `k0/pipelines/p03/phases/r3_dedup_decay.py` (1149 lines) | **UNDERSTANDS** — How R3 runs dedup | R3 stores results in `P03EventState` and `P03PhaseOutputs.r3_dedup_merges` |
| `k0/pipelines/p03/phase_outputs.py:103-117` | **READS** — Dedup merge results | `DedupMerge.duplicate_id`, `.canonical_id`, `.hamming_distance`, `.merge_confidence` |

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/modules/consolidation/staging/dedup_metadata.py` | DedupMetadataPopulator class |

**Metadata Fields to Populate** (from Dossier §4.7.2):

| Field | Type | Source |
|-------|------|--------|
| `near_duplicates_json` | `str` (JSON array) | `DuplicationResult.near_duplicates` — List of `{event_id, hamming_distance, similarity, stage}` |
| `novelty_score` | `float [0, 1]` | `DuplicationResult.novelty_score` |
| `episode_cluster_id` | `Optional[str]` | `P03EventState.cluster_id` (from R2) |
| `novelty_bonuses_json` | `str` (JSON object) | `NoveltyBonuses` breakdown for transparency |

**Deliverables**:

1. **DedupMetadataPopulator class** in `dedup_metadata.py`:

   ```python
   @dataclass
   class NearDuplicateEntry:
       event_id: str
       hamming_distance: int
       embedding_similarity: float
       detection_stage: str  # "SIMHASH" or "EMBEDDING"

   class DedupMetadataPopulator:
       def populate(
           self,
           event_state: P03EventState,
           dedup_result: DuplicationResult,
       ) -> DedupMetadata:
           """Create dedup metadata from detector result."""
           ...

       def build_near_duplicates_json(
           self,
           near_duplicates: List[str],
           dedup_result: DuplicationResult,
       ) -> str:
           """Build JSON array of near-duplicate entries."""
           ...
   ```

2. **near_duplicates_json format**:

   ```json
   [
     {
       "event_id": "01HXYZ...",
       "hamming_distance": 2,
       "embedding_similarity": 0.92,
       "detection_stage": "SIMHASH"
     }
   ]
   ```

3. **Handle empty near_duplicates**:
   - If no near-duplicates: `near_duplicates_json = "[]"`
   - `novelty_score` defaults to 1.0 baseline + bonuses - penalties

**Acceptance Criteria**:

- [ ] `near_duplicates_json` correctly captures all SimHash candidates with verification results
- [ ] `novelty_score` reflects dossier formula (base + bonuses - penalty)
- [ ] `episode_cluster_id` links to R2 cluster or null for singletons/noise
- [ ] Handles events with no dedup results (first occurrence)
- [ ] JSON is valid and parseable
- [ ] Bonus breakdown captured for debugging

**Test File**: `tests/k0/modules/consolidation/staging/test_dedup_metadata.py`

---

#### Issue 5.1.4 — Reconciliation decision recording

**Status**: NOT_STARTED

**Goal**: Record complete reconciliation decision audit trail per event, including matched truth record, similarity scores, and decision reasoning.

**Dossier References**:

- [Dossier §4.7.3](../pipelines/P03_consolidation_dossier_v2.md#473-reconciliation-decision-recording) — Reconciliation Decision Recording
- [Dossier §4.3.2](../pipelines/P03_consolidation_dossier_v2.md#432-decision-engine) — Decision Engine (where reconciliation is determined)

**Implementation Plan Reference**:

- [P03_implementation_plan_skeleton.md Issue 5.1.4](../pipelines/P03_implementation_plan_skeleton.md) (lines 2538-2568)

**Existing Code Dependencies**:

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `k0/pipelines/p03/event_state.py:18-40` | **READS** — ReconciliationAction enum | `ReconciliationAction` values: PENDING, REINFORCE, EXTEND, CREATE, EVOLVE, CONTRADICT, PRUNE, SKIP |
| `k0/pipelines/p03/event_state.py:310-340` | **READS** — Reconciliation setter | `P03EventState.set_reconciliation(action, match_id, match_layer, similarity, confidence, reason)` |
| `k0/pipelines/p03/event_state.py:165-170` | **READS** — Reconciliation fields | `best_match_id`, `best_match_layer`, `similarity_score`, `confidence`, `reconciliation_reason` |
| `k0/modules/consolidation/algorithms/reconciliation_decider.py` | **READS** — Decision logic | `ReconciliationDecider.decide()` returns decision with scores |
| `k0/pipelines/p03/phases/r3_dedup_decay.py` (1149 lines) | **UNDERSTANDS** — How R3 applies decisions | `_apply_reconciliation_decisions()` populates event state |

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/modules/consolidation/staging/reconciliation_recorder.py` | ReconciliationRecorder class |

**Decision Fields to Record** (from Dossier §4.7.3):

| Field | Type | Source |
|-------|------|--------|
| `reconciliation_action` | `str` | `P03EventState.reconciliation_action.value` |
| `best_match_id` | `Optional[str]` | `P03EventState.best_match_id` — Truth record matched |
| `best_match_layer` | `Optional[str]` | `P03EventState.best_match_layer` — st_epi, st_sem, etc. |
| `similarity_score` | `float` | `P03EventState.similarity_score` — Cosine similarity [0, 1] |
| `confidence` | `float` | `P03EventState.confidence` — Decision confidence [0, 1] |
| `reconciliation_reason` | `str` | `P03EventState.reconciliation_reason` — Human-readable |
| `decision_timestamp_ms` | `int` | Timestamp when decision was made |

**Deliverables**:

1. **ReconciliationRecorder class** in `reconciliation_recorder.py`:

   ```python
   @dataclass
   class ReconciliationRecord:
       event_id: str
       reconciliation_action: str
       best_match_id: Optional[str]
       best_match_layer: Optional[str]
       similarity_score: float
       confidence: float
       reconciliation_reason: str
       decision_timestamp_ms: int

   class ReconciliationRecorder:
       def record(self, event_state: P03EventState) -> ReconciliationRecord:
           """Extract reconciliation decision from event state."""
           ...

       def record_batch(
           self, event_states: List[P03EventState]
       ) -> List[ReconciliationRecord]:
           """Record decisions for batch of events."""
           ...

       def to_json(self, record: ReconciliationRecord) -> str:
           """Serialize record to JSON for st_hipp_events.reconciliation_json."""
           ...
   ```

2. **Audit trail JSON format** for `st_hipp_events.reconciliation_json`:

   ```json
   {
     "action": "REINFORCE",
     "match_id": "epi-001HXYZ",
     "match_layer": "st_epi",
     "similarity": 0.89,
     "confidence": 0.92,
     "reason": "High embedding similarity to existing episode",
     "decided_at_ms": 1735689600000
   }
   ```

**Acceptance Criteria**:

- [ ] All 8 ReconciliationAction values mapped correctly
- [ ] `best_match_id` and `best_match_layer` captured for REINFORCE/EXTEND/EVOLVE
- [ ] NULL handling for CREATE/PRUNE/SKIP (no truth match)
- [ ] JSON serialization is compact and parseable
- [ ] Timestamp uses consistent millisecond epoch format

**Test File**: `tests/k0/modules/consolidation/staging/test_reconciliation_recorder.py`

---

#### Issue 5.1.5 — Idempotency key generation for R6

**Status**: NOT_STARTED

**Goal**: Implement deterministic idempotency key generation following dossier format for all R6 staged writes.

**Dossier References**:

- [Dossier §12.2.3](../pipelines/P03_consolidation_dossier_v2.md#1223-idempotency-key-design) — Idempotency Key Design
- [Dossier Appendix G](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R6Output specification

**Implementation Plan Reference**:

- [P03_implementation_plan_skeleton.md Issue 5.1.5](../pipelines/P03_implementation_plan_skeleton.md) (lines 2570-2600)

**Existing Code Dependencies**:

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `k0/pipelines/p03/staged_writes.py:110-120` | **PATTERN** — INSERT idempotency | `StagedWrite.insert()` uses `f"{phase}:{layer}:{record_id}"` |
| `k0/pipelines/p03/staged_writes.py:145-150` | **PATTERN** — UPDATE idempotency | `StagedWrite.update()` uses `f"{phase}:{layer}:{record_id}:v{expected_version}"` |
| `k0/pipelines/p03/staged_writes.py:180-185` | **PATTERN** — ARCHIVE idempotency | `StagedWrite.archive()` uses `f"{phase}:{layer}:{record_id}:archive"` |
| `k0/pipelines/p03/context.py` | **READS** — ULID generation | `generate_ulid()`, `P03CycleContext.cycle_ulid` |
| `k0/pipelines/p03/batch_envelope.py` | **READS** — Batch context | `P03BatchEnvelope.batch_id` for batch hash |

**Idempotency Key Formats** (from Dossier §12.2.3):

| Context | Format | Example |
|---------|--------|---------|
| R6 event update | `p03:staging:{cycle_ulid}:{event_id}` | `p03:staging:01HXYZ123:01HABC789` |
| R7 truth write | `p03:write:{cycle_ulid}:{table}:{record_id}` | `p03:write:01HXYZ123:st_epi:epi-001` |
| R8 event emit | `p03:emit:{cycle_ulid}:{topic}:{offset}` | `p03:emit:01HXYZ123:p03.pattern.detected.v1:42` |

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/modules/consolidation/staging/idempotency.py` | IdempotencyKeyGenerator class |

**Deliverables**:

1. **IdempotencyKeyGenerator class** in `idempotency.py`:

   ```python
   class IdempotencyKeyGenerator:
       def __init__(self, cycle_ulid: str):
           self.cycle_ulid = cycle_ulid

       def for_event_update(self, event_id: str) -> str:
           """Generate key for st_hipp_events update in R6."""
           return f"p03:staging:{self.cycle_ulid}:{event_id}"

       def for_truth_write(
           self, table: str, record_id: str
       ) -> str:
           """Generate key for truth layer write in R7."""
           return f"p03:write:{self.cycle_ulid}:{table}:{record_id}"

       def for_event_emit(
           self, topic: str, offset: int
       ) -> str:
           """Generate key for outbox event in R8."""
           return f"p03:emit:{self.cycle_ulid}:{topic}:{offset}"

       def for_batch_phase(
           self, phase: str, batch_hash: str
       ) -> str:
           """Generate key for R1-R5 phase processing."""
           return f"p03:{phase}:{self.cycle_ulid}:{batch_hash}"
   ```

2. **Batch hash computation**:
   - Hash of sorted `event_id` list in batch
   - Uses SHA-256 truncated to 12 hex chars
   - Deterministic for same event set

3. **Key validation**:
   - Validate format on parse
   - Extract components (pipeline, phase, cycle, entity)

**Acceptance Criteria**:

- [ ] All key formats match dossier §12.2.3 exactly
- [ ] Keys are deterministic (same inputs → same key)
- [ ] Keys are unique across cycles (cycle_ulid included)
- [ ] Batch hash is stable regardless of event processing order
- [ ] Key length is reasonable (<200 chars)

**Test File**: `tests/k0/modules/consolidation/staging/test_idempotency.py`

---

#### Issue 5.1.6 — Staged truth writes assembly

**Status**: NOT_STARTED

**Goal**: Implement per-layer write assembly that converts R1-R5 phase outputs into `StagedWrite` objects for all 8 truth layers plus learning queue.

**Dossier References**:

- [Dossier §4.8.2](../pipelines/P03_consolidation_dossier_v2.md#482-st_epi-episodic-writes) — st_epi writes
- [Dossier §4.8.3](../pipelines/P03_consolidation_dossier_v2.md#483-st_sem-semantic-writes) — st_sem writes
- [Dossier §4.8.4](../pipelines/P03_consolidation_dossier_v2.md#484-st_procedural-habits-writes) — st_procedural writes
- [Dossier §4.8.5](../pipelines/P03_consolidation_dossier_v2.md#485-st_social-relationships-writes) — st_social writes
- [Dossier §4.8.6](../pipelines/P03_consolidation_dossier_v2.md#486-st_prospective-intentions-writes) — st_prospective writes
- [Dossier §4.8.7](../pipelines/P03_consolidation_dossier_v2.md#487-st_kg_dom--st_kg_edges-kg-writes) — st_kg_dom/st_kg_edges writes
- [Dossier §4.8.8](../pipelines/P03_consolidation_dossier_v2.md#488-st_vec-embeddings-writes) — st_vec writes

**Implementation Plan Reference**:

- [P03_implementation_plan_skeleton.md Issue 5.1.6](../pipelines/P03_implementation_plan_skeleton.md) (lines 2602-2650)

**Existing Code Dependencies**:

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `k0/pipelines/p03/staged_writes.py:280-300` | **USES** — Layer constants | `LAYER_ST_EPI`, `LAYER_ST_SEM`, `LAYER_ST_PROCEDURAL`, `LAYER_ST_SOCIAL`, `LAYER_ST_PROSPECTIVE`, `LAYER_ST_KG_DOM`, `LAYER_ST_KG_EDGES`, `LAYER_ST_VEC`, `LAYER_ST_LEARNING_QUEUE` |
| `k0/pipelines/p03/staged_writes.py:50-100` | **USES** — StagedWrite factory | `StagedWrite.insert()`, `.update()`, `.archive()` |
| `k0/pipelines/p03/staged_writes.py:310-350` | **POPULATES** — P03StagedWrites container | `P03StagedWrites.add_write()` routes by layer |
| `k0/pipelines/p03/phase_outputs.py:103-117` | **READS** — R3 outputs | `DedupMerge`, `DecayUpdate` |
| `k0/pipelines/p03/phase_outputs.py:135-190` | **READS** — R4 outputs | `KGEntity`, `KGEdge`, `GapCandidate` |
| `k0/pipelines/p03/phase_outputs.py:80-100` | **READS** — R2 outputs | `EpisodeCluster` with `member_event_ids`, `centroid_embedding_id` |
| `k0/pipelines/p03/event_state.py:165-175` | **READS** — Per-event state | `reconciliation_action`, `best_match_id`, `best_match_layer` |

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/modules/consolidation/staging/truth_write_assembler.py` | TruthWriteAssembler class |

**Layer Write Assembly Rules**:

| Layer | Phase Source | When to Write | Operation Type |
|-------|--------------|---------------|----------------|
| `st_epi` | R2 `EpisodeCluster` | New cluster formed | INSERT |
| `st_epi` | R3 REINFORCE | Existing episode matched | UPDATE |
| `st_sem` | R3 CREATE | New pattern detected | INSERT |
| `st_sem` | R3 EXTEND | Pattern extended | UPDATE |
| `st_procedural` | R3 CREATE | New routine detected | INSERT |
| `st_social` | R4 social entity | Social relationship update | UPDATE |
| `st_prospective` | R4 prospective entity | Intention/goal detected | INSERT |
| `st_kg_dom` | R4 `KGEntity` | Entity canonical record | INSERT/UPDATE |
| `st_kg_edges` | R4 `KGEdge` | Relationship edge | INSERT/UPDATE |
| `st_vec` | R2/R4 | Aggregated embeddings | INSERT |
| `st_learning_queue` | R4 `GapCandidate` | Gap for P06 | INSERT |

**Deliverables**:

1. **TruthWriteAssembler class** in `truth_write_assembler.py`:

   ```python
   class TruthWriteAssembler:
       def __init__(
           self,
           idempotency_gen: IdempotencyKeyGenerator,
       ):
           self.idempotency = idempotency_gen

       def assemble_epi_writes(
           self,
           clusters: List[EpisodeCluster],
           event_states: Dict[str, P03EventState],
       ) -> List[StagedWrite]:
           """Assemble st_epi writes from R2 clusters."""
           ...

       def assemble_sem_writes(
           self,
           event_states: Dict[str, P03EventState],
       ) -> List[StagedWrite]:
           """Assemble st_sem writes from R3 CREATE/EXTEND decisions."""
           ...

       def assemble_kg_writes(
           self,
           entities: List[KGEntity],
           edges: List[KGEdge],
       ) -> Tuple[List[StagedWrite], List[StagedWrite]]:
           """Assemble st_kg_dom and st_kg_edges writes from R4."""
           ...

       def assemble_learning_queue_writes(
           self,
           gaps: List[GapCandidate],
       ) -> List[StagedWrite]:
           """Assemble st_learning_queue writes for P06."""
           ...

       def assemble_all(
           self,
           phase_outputs: P03PhaseOutputs,
           event_states: Dict[str, P03EventState],
       ) -> P03StagedWrites:
           """Assemble all layer writes into staged container."""
           ...
   ```

2. **Write record data structure**:
   - Each layer has specific schema from Dossier §6
   - Assembler converts phase outputs to layer-specific record_data dict
   - Provenance tracked via `source_event_ids`

3. **Dependency ordering**:
   - Uses `P03StagedWrites.get_all_writes_ordered()` for commit order
   - Respects: vec → kg_dom → kg_edges → epi → sem → procedural → social → prospective → learning_queue

**Acceptance Criteria**:

- [ ] All 9 layers have assembly methods (8 truth + learning_queue)
- [ ] `StagedWrite` factory methods (`.insert()`, `.update()`) used correctly
- [ ] `source_event_ids` populated for provenance tracking
- [ ] Idempotency keys generated per dossier format
- [ ] Empty phase outputs produce no writes (not empty writes)
- [ ] Integration with `IdempotencyKeyGenerator` from 5.1.5

**Test File**: `tests/k0/modules/consolidation/staging/test_truth_write_assembler.py`

---

#### Issue 5.1.7 — Staged KG writes assembly

**Status**: NOT_STARTED

**Goal**: Implement dedicated KG (Knowledge Graph) write assembler for `st_kg_dom` entities and `st_kg_edges` relationships from R4 phase outputs.

**Dossier References**:

- [Dossier §4.8.7](../pipelines/P03_consolidation_dossier_v2.md#487-st_kg_dom--st_kg_edges-kg-writes) — st_kg_dom / st_kg_edges (KG) Writes
- [Dossier §7.4.4](../pipelines/P03_consolidation_dossier_v2.md#744-m21-kgbuilder) — M21 KGBuilder module spec

**Implementation Plan Reference**:

- [P03_implementation_plan_skeleton.md Issue 5.1.7](../pipelines/P03_implementation_plan_skeleton.md) (lines 2652-2700)

**Existing Code Dependencies**:

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `k0/pipelines/p03/phase_outputs.py:142-160` | **READS** — KGEntity dataclass | `KGEntity.entity_id`, `.canonical_name`, `.entity_type`, `.aliases_json`, `.confidence`, `.embedding_id`, `.source_event_ids`, `.is_new` |
| `k0/pipelines/p03/phase_outputs.py:162-175` | **READS** — KGEntityUpdate dataclass | `KGEntityUpdate.entity_id`, `.field_updates`, `.confidence_delta`, `.new_aliases` |
| `k0/pipelines/p03/phase_outputs.py:178-195` | **READS** — KGEdge dataclass | `KGEdge.edge_id`, `.source_entity_id`, `.target_entity_id`, `.relationship_type`, `.weight`, `.confidence`, `.is_causal`, `.evidence_event_ids`, `.is_new` |
| `k0/pipelines/p03/phase_outputs.py:197-210` | **READS** — KGEdgeUpdate dataclass | `KGEdgeUpdate.edge_id`, `.weight_delta`, `.confidence_delta`, `.new_evidence_ids` |
| `k0/pipelines/p03/phase_outputs.py:212-225` | **READS** — CausalEdge dataclass | `CausalEdge.cause_entity_id`, `.effect_entity_id`, `.lag_days`, `.granger_p_value`, `.effect_size` |
| `k0/pipelines/p03/staged_writes.py:287-288` | **USES** — Layer constants | `LAYER_ST_KG_DOM`, `LAYER_ST_KG_EDGES` |
| `k0/pipelines/p03/staged_writes.py:85-120` | **USES** — StagedWrite factories | `StagedWrite.insert()`, `.update()` |

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/modules/consolidation/staging/kg_write_assembler.py` | KGWriteAssembler class |

**Entity Write Schema** (st_kg_dom record_data):

| Field | Type | Source |
|-------|------|--------|
| `entity_id` | `str` | `KGEntity.entity_id` |
| `canonical_name` | `str` | `KGEntity.canonical_name` |
| `entity_type` | `str` | PERSON, LOCATION, ORG, THING, CONCEPT |
| `aliases_json` | `str` | `KGEntity.aliases_json` — JSON array |
| `confidence` | `float` | `KGEntity.confidence` [0, 1] |
| `embedding_id` | `Optional[str]` | Reference to st_vec |
| `source_event_ids_json` | `str` | JSON array of contributing events |
| `created_at` / `updated_at` | `timestamp` | Auto-managed |

**Edge Write Schema** (st_kg_edges record_data):

| Field | Type | Source |
|-------|------|--------|
| `edge_id` | `str` | `KGEdge.edge_id` |
| `source_entity_id` | `str` | FK to st_kg_dom |
| `target_entity_id` | `str` | FK to st_kg_dom |
| `relationship_type` | `str` | KNOWS, LOCATED_AT, PART_OF, CAUSES |
| `weight` | `float` | `KGEdge.weight` [0, 1] |
| `confidence` | `float` | `KGEdge.confidence` [0, 1] |
| `is_causal` | `bool` | `KGEdge.is_causal` (Granger-validated) |
| `evidence_event_ids_json` | `str` | JSON array of evidence events |

**Deliverables**:

1. **KGWriteAssembler class** in `kg_write_assembler.py`:

   ```python
   class KGWriteAssembler:
       def __init__(self, idempotency_gen: IdempotencyKeyGenerator):
           self.idempotency = idempotency_gen

       def assemble_entity_writes(
           self,
           entities: List[KGEntity],
           entity_updates: List[KGEntityUpdate],
       ) -> List[StagedWrite]:
           """
           Assemble st_kg_dom writes from R4 entities.

           - New entities (is_new=True) → INSERT
           - Existing entities (is_new=False or updates) → UPDATE
           """
           ...

       def assemble_edge_writes(
           self,
           edges: List[KGEdge],
           edge_updates: List[KGEdgeUpdate],
           causal_edges: List[CausalEdge],
       ) -> List[StagedWrite]:
           """
           Assemble st_kg_edges writes from R4 relationships.

           - Causal edges get is_causal=True flag
           - Edge updates merge with existing edges
           """
           ...

       def validate_foreign_keys(
           self,
           entity_ids: Set[str],
           edges: List[KGEdge],
       ) -> List[str]:
           """
           Validate edge source/target reference existing entities.
           Returns list of validation errors.
           """
           ...
   ```

2. **Dependency order enforcement**:
   - Entities assembled BEFORE edges (FK constraint)
   - Uses `LAYER_ST_KG_DOM` and `LAYER_ST_KG_EDGES` for routing

3. **CausalEdge handling**:
   - Convert `CausalEdge` to `KGEdge` with `is_causal=True`
   - Include Granger p-value in metadata

**Acceptance Criteria**:

- [ ] Entity INSERT for `is_new=True`, UPDATE otherwise
- [ ] Edge INSERT for `is_new=True`, UPDATE otherwise
- [ ] CausalEdge converted to KGEdge with `is_causal=True`
- [ ] Foreign key validation catches orphan edges
- [ ] `source_event_ids` populated for provenance
- [ ] Idempotency keys follow `p03:write:{cycle}:st_kg_dom:{entity_id}` format

**Test File**: `tests/k0/modules/consolidation/staging/test_kg_write_assembler.py`

---

#### Issue 5.1.8 — Staged outbox events assembly

**Status**: NOT_STARTED

**Goal**: Implement outbox event assembler that stages all R8 emission events during R6 for transactional consistency.

**Dossier References**:

- [Dossier §4.9.1](../pipelines/P03_consolidation_dossier_v2.md#491-bus-event-emission) — Bus Event Emission (all topic types)
- [Dossier §4.8.1](../pipelines/P03_consolidation_dossier_v2.md#481-outbox-pattern-implementation) — Outbox Pattern Implementation
- [Dossier Appendix G R8](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R8 EmitResult spec

**Implementation Plan Reference**:

- [P03_implementation_plan_skeleton.md Issue 5.1.8](../pipelines/P03_implementation_plan_skeleton.md) (lines 2702-2750)

**Existing Code Dependencies**:

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `k0/pipelines/p03/staged_writes.py:223-270` | **USES** — StagedOutboxEvent dataclass | `StagedOutboxEvent.create()`, `.event_id`, `.topic`, `.payload`, `.source_phase`, `.priority` |
| `k0/pipelines/p03/staged_writes.py:392-425` | **USES** — Container method | `P03StagedWrites.add_outbox_event(topic, payload, phase, priority)` |
| `k0/pipelines/p03/phases/r8_event_emitter.py:1-50` | **PATTERN** — R8 topics | `COMPLETION_TOPIC = "p03.consolidation.complete.v1"`, `GAP_TOPIC = "p03.gap.detected.v1"` |
| `k0/pipelines/p03/phases/r8_event_emitter.py:170-200` | **PATTERN** — Payload building | `_build_completion_payload()` structure |
| `k0/pipelines/p03/phase_outputs.py:227-245` | **READS** — GapCandidate | `gap_id`, `gap_type`, `related_entity_id`, `entropy_score`, `priority`, `context_json` |
| `k0/storage/outbox.py` | **UNDERSTANDS** — OutboxEntry schema | `OutboxEntry` dataclass for persistence |

**Event Topics** (from Dossier §4.9.1):

| Topic | When Emitted | Payload Source |
|-------|--------------|----------------|
| `p03.consolidation.complete.v1` | End of every cycle | ReconciliationSummary |
| `p03.pattern.detected.v1` | New pattern created | R3 CREATE decision |
| `p03.truth.reinforced.v1` | Existing truth reinforced | R3 REINFORCE decision |
| `p03.truth.created.v1` | New truth record | R3 CREATE decision |
| `p03.truth.evolved.v1` | Truth evolved/extended | R3 EVOLVE/EXTEND decision |
| `p03.memory.pruned.v1` | Memory decayed/pruned | R3 PRUNE decision |
| `p03.gap.detected.v1` | Knowledge gap for P06 | R4 GapCandidate |

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/modules/consolidation/staging/outbox_assembler.py` | OutboxEventAssembler class |

**Deliverables**:

1. **OutboxEventAssembler class** in `outbox_assembler.py`:

   ```python
   class OutboxEventAssembler:
       def __init__(
           self,
           cycle_ulid: str,
           tenant_id: str,
           space_id: str,
       ):
           self.cycle_ulid = cycle_ulid
           self.tenant_id = tenant_id
           self.space_id = space_id

       def assemble_completion_event(
           self,
           summary: ReconciliationSummary,
           phase_durations: Dict[str, int],
       ) -> StagedOutboxEvent:
           """Build p03.consolidation.complete.v1 event."""
           ...

       def assemble_decision_events(
           self,
           event_states: Dict[str, P03EventState],
       ) -> List[StagedOutboxEvent]:
           """
           Build per-decision events based on reconciliation_action:
           - REINFORCE → p03.truth.reinforced.v1
           - CREATE → p03.truth.created.v1, p03.pattern.detected.v1
           - EVOLVE/EXTEND → p03.truth.evolved.v1
           - PRUNE → p03.memory.pruned.v1
           """
           ...

       def assemble_gap_events(
           self,
           gaps: List[GapCandidate],
       ) -> List[StagedOutboxEvent]:
           """Build p03.gap.detected.v1 events for P06."""
           ...

       def assemble_all(
           self,
           summary: ReconciliationSummary,
           event_states: Dict[str, P03EventState],
           gaps: List[GapCandidate],
           phase_durations: Dict[str, int],
       ) -> List[StagedOutboxEvent]:
           """Assemble all outbox events for the cycle."""
           ...
   ```

2. **Event payload schemas**:
   - Each topic has specific JSON schema in `k0/contracts/schemas/`
   - Assembler builds payload matching schema
   - Includes `cycle_id`, `tenant_id`, `space_id` envelope

3. **Priority assignment**:
   - Completion: priority 10 (highest)
   - Gaps: priority 30 (high for P06)
   - Decision events: priority 50 (normal)

**Acceptance Criteria**:

- [ ] All 7 topic types assembled correctly
- [ ] Payload matches schema in `k0/contracts/schemas/`
- [ ] `source_phase` set to "R6" (assembled during R6)
- [ ] Priority correctly assigned per event type
- [ ] Completion event includes full `ReconciliationSummary`
- [ ] Gap events deduplicated by `gap_id`

**Test File**: `tests/k0/modules/consolidation/staging/test_outbox_assembler.py`

---

#### Issue 5.1.9 — Manifest validation before commit

**Status**: NOT_STARTED

**Goal**: Implement R6Output manifest validation that ensures staged writes are complete, consistent, and ready for atomic R7 commit.

**Dossier References**:

- [Dossier Appendix G R6](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R6Output specification and DLQ conditions
- [Dossier §4.7](../pipelines/P03_consolidation_dossier_v2.md#47-r6--staging-table-updates) — R6 staging requirements
- [Dossier §12.2.3](../pipelines/P03_consolidation_dossier_v2.md#1223-idempotency-key-design) — Idempotency key format validation

**Implementation Plan Reference**:

- [P03_implementation_plan_skeleton.md Issue 5.1.9](../pipelines/P03_implementation_plan_skeleton.md) (lines 2752-2800)

**Existing Code Dependencies**:

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `k0/pipelines/p03/staged_writes.py:430-445` | **VALIDATES** — Total write counts | `P03StagedWrites.total_writes()`, `.total_outbox_events()` |
| `k0/pipelines/p03/staged_writes.py:447-480` | **VALIDATES** — Dependency order | `P03StagedWrites.get_all_writes_ordered()` |
| `k0/pipelines/p03/staged_writes.py:50-80` | **VALIDATES** — StagedWrite fields | `write_id`, `layer`, `operation`, `record_id`, `idempotency_key` |
| `k0/pipelines/p03/staged_writes.py:280-298` | **VALIDATES** — Valid layers | `VALID_LAYERS` frozenset |
| `k0/pipelines/p03/event_state.py:18-40` | **VALIDATES** — ReconciliationAction coverage | All events must have action set |

**Validation Rules** (from Dossier Appendix G):

| Rule | Description | DLQ Condition |
|------|-------------|---------------|
| Layer validity | All writes use `VALID_LAYERS` | Any invalid layer |
| Idempotency keys | All keys match format | Malformed key |
| FK integrity | Edge writes reference staged/existing entities | Orphan reference |
| Version conflicts | <10% of events have version mismatch | >10% conflicts |
| Event coverage | All batch events have staged updates | Missing event |
| Outbox minimum | At least 1 event (completion) | Zero outbox events |

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/modules/consolidation/staging/manifest_validator.py` | ManifestValidator class |

**Deliverables**:

1. **ManifestValidator class** in `manifest_validator.py`:

   ```python
   @dataclass
   class ValidationResult:
       is_valid: bool
       errors: List[str]
       warnings: List[str]
       stats: Dict[str, int]  # writes_by_layer, events_by_topic, etc.

   class ManifestValidator:
       def validate(
           self,
           r6_output: R6Output,
           batch_event_ids: Set[str],
       ) -> ValidationResult:
           """
           Validate R6Output manifest before R7 commit.

           Checks:
           1. Layer validity
           2. Idempotency key format
           3. FK integrity for edges
           4. Event coverage (all batch events have update)
           5. Outbox event presence
           6. No duplicate record_ids per layer

           Returns ValidationResult with errors/warnings.
           """
           ...

       def _validate_layers(
           self,
           writes: List[StagedWrite],
       ) -> List[str]:
           """Ensure all layers are in VALID_LAYERS."""
           ...

       def _validate_idempotency_keys(
           self,
           writes: List[StagedWrite],
           events: List[StagedOutboxEvent],
       ) -> List[str]:
           """Validate key format: p03:{phase}:{cycle}:{entity}."""
           ...

       def _validate_fk_integrity(
           self,
           kg_dom_writes: List[StagedWrite],
           kg_edge_writes: List[StagedWrite],
       ) -> List[str]:
           """Ensure edges reference staged or existing entities."""
           ...

       def _validate_event_coverage(
           self,
           event_updates: List[StagedEventUpdate],
           batch_event_ids: Set[str],
       ) -> List[str]:
           """Ensure all batch events have staged update."""
           ...

       def _check_duplicate_records(
           self,
           writes: List[StagedWrite],
       ) -> List[str]:
           """Detect duplicate record_ids within same layer."""
           ...
   ```

2. **ValidationResult stats**:

   ```python
   stats = {
       "total_writes": 150,
       "writes_by_layer": {"st_epi": 10, "st_sem": 25, ...},
       "outbox_events": 12,
       "events_by_topic": {"p03.consolidation.complete.v1": 1, ...},
       "event_updates": 100,
       "version_conflicts": 2,
   }
   ```

3. **DLQ threshold check**:
   - If version_conflicts > 10% of total events → DLQ condition
   - Validator returns `is_valid=False` with DLQ reason

**Acceptance Criteria**:

- [ ] All validation rules from Dossier Appendix G implemented
- [ ] `is_valid=False` blocks R7 execution
- [ ] Errors vs warnings correctly categorized
- [ ] Stats provide debugging visibility
- [ ] DLQ condition detected for >10% version conflicts
- [ ] Orphan edge references caught before commit

**Test File**: `tests/k0/modules/consolidation/staging/test_manifest_validator.py`

---

#### Issue 5.1.10 — ReconciliationSummary generation

**Status**: NOT_STARTED

**Goal**: Implement aggregation logic that computes `ReconciliationSummary` statistics from all processed event states in a cycle.

**Dossier References**:

- [Dossier Appendix G R6](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R6Output.reconciliation_summary field
- [Dossier §4.9.3](../pipelines/P03_consolidation_dossier_v2.md#493-metrics-aggregation) — Metrics Aggregation requirements

**Implementation Plan Reference**:

- [P03_implementation_plan_skeleton.md Issue 5.1.10](../pipelines/P03_implementation_plan_skeleton.md) (lines 2802-2840)

**Existing Code Dependencies**:

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `k0/pipelines/p03/phase_outputs.py:351-390` | **EXTENDS** — ReconciliationSummary dataclass | `reinforce_count`, `extend_count`, `create_count`, `evolve_count`, `contradict_count`, `prune_count`, `skip_count`, `total_processed`, `total_all` |
| `k0/pipelines/p03/event_state.py:18-40` | **READS** — ReconciliationAction enum | `PENDING`, `REINFORCE`, `EXTEND`, `CREATE`, `EVOLVE`, `CONTRADICT`, `PRUNE`, `SKIP` |
| `k0/pipelines/p03/event_state.py:160-170` | **READS** — Per-event action | `P03EventState.reconciliation_action` |
| `k0/pipelines/p03/phase_outputs.py:570-595` | **PATTERN** — Existing aggregation | `P03PhaseOutputs.compute_summary()` pattern |

**ReconciliationSummary Fields** (from phase_outputs.py:351-390):

| Field | Type | Aggregation |
|-------|------|-------------|
| `reinforce_count` | `int` | Count of `REINFORCE` decisions |
| `extend_count` | `int` | Count of `EXTEND` decisions |
| `create_count` | `int` | Count of `CREATE` decisions |
| `evolve_count` | `int` | Count of `EVOLVE` decisions |
| `contradict_count` | `int` | Count of `CONTRADICT` decisions |
| `prune_count` | `int` | Count of `PRUNE` decisions |
| `skip_count` | `int` | Count of `SKIP` decisions |
| `total_processed` | `property` | Sum of all except skip |
| `total_all` | `property` | Sum including skip |

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/modules/consolidation/staging/summary_generator.py` | SummaryGenerator class |

**Deliverables**:

1. **SummaryGenerator class** in `summary_generator.py`:

   ```python
   class SummaryGenerator:
       def compute(
           self,
           event_states: Dict[str, P03EventState],
       ) -> ReconciliationSummary:
           """
           Aggregate ReconciliationSummary from all event states.

           Args:
               event_states: Map of event_id → P03EventState

           Returns:
               ReconciliationSummary with all counts populated
           """
           ...

       def compute_from_actions(
           self,
           actions: List[ReconciliationAction],
       ) -> ReconciliationSummary:
           """Compute from list of actions (for testing)."""
           ...

       def merge(
           self,
           summaries: List[ReconciliationSummary],
       ) -> ReconciliationSummary:
           """Merge multiple summaries (for batch parallelism)."""
           ...
   ```

2. **Counter-based aggregation**:
   - Uses `collections.Counter` for efficiency
   - Maps `ReconciliationAction.value` → count field

3. **Validation**:
   - Warn if any event has `PENDING` action (unprocessed)
   - Ensure total matches input count

**Acceptance Criteria**:

- [ ] All 7 ReconciliationAction values correctly counted
- [ ] `total_processed` excludes `skip_count`
- [ ] `total_all` equals input event count
- [ ] PENDING events flagged as warnings
- [ ] Merge function correctly combines summaries
- [ ] Integration with existing `ReconciliationSummary` dataclass

**Test File**: `tests/k0/modules/consolidation/staging/test_summary_generator.py`

---

#### Issue 5.1.11 — R6 phase coordinator

**Status**: NOT_STARTED

**Goal**: Implement the R6Coordinator that orchestrates all R6 sub-components (status marker, dedup metadata, reconciliation recorder, write assemblers, outbox assembler, validator) into a coherent staging phase.

**Dossier References**:

- [Dossier §4.7](../pipelines/P03_consolidation_dossier_v2.md#47-r6--staging-table-updates) — R6 Staging Table Updates (full section)
- [Dossier Appendix G R6](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R6 phase contract

**Implementation Plan Reference**:

- [P03_implementation_plan_skeleton.md Issue 5.1.11](../pipelines/P03_implementation_plan_skeleton.md) (lines 2842-2900)

**Existing Code Dependencies**:

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `k0/pipelines/p03/phase_interface.py:35-115` | **IMPLEMENTS** — P03PhaseResult | `P03PhaseResult.done()`, `.skip()`, `.fail()` factory methods |
| `k0/pipelines/p03/phase_interface.py:160-200` | **RECEIVES** — P03RunnerContext | `syscalls`, `logger`, `config`, `dry_run` |
| `k0/pipelines/p03/envelope.py` | **READS/WRITES** — P03BatchEnvelope | `envelope.event_states`, `envelope.phases`, `envelope.staged` |
| `k0/pipelines/p03/staged_writes.py:310-350` | **POPULATES** — P03StagedWrites | Container that R6 fills with staged writes |
| `k0/pipelines/p03/runner_contract.py` | **USES** — P03PhaseId | `P03PhaseId.R6_STAGING` (to be added) |

**Sub-Components to Orchestrate** (Issues 5.1.1-5.1.10):

| Component | Issue | Input | Output |
|-----------|-------|-------|--------|
| ConsolidationStatusMarker | 5.1.2 | P03EventState | consolidation_status |
| DedupMetadataPopulator | 5.1.3 | DuplicationResult | near_duplicates_json, novelty_score |
| ReconciliationRecorder | 5.1.4 | P03EventState | ReconciliationRecord |
| IdempotencyKeyGenerator | 5.1.5 | cycle_ulid | idempotency keys |
| TruthWriteAssembler | 5.1.6 | phase_outputs | StagedWrite list |
| KGWriteAssembler | 5.1.7 | KGEntity, KGEdge | StagedWrite list |
| OutboxEventAssembler | 5.1.8 | summary, gaps | StagedOutboxEvent list |
| ManifestValidator | 5.1.9 | R6Output | ValidationResult |
| SummaryGenerator | 5.1.10 | event_states | ReconciliationSummary |

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/modules/consolidation/staging/r6_coordinator.py` | R6Coordinator class |

**Deliverables**:

1. **R6Coordinator class** in `r6_coordinator.py`:

   ```python
   class R6Coordinator:
       def __init__(
           self,
           status_marker: ConsolidationStatusMarker,
           dedup_populator: DedupMetadataPopulator,
           recon_recorder: ReconciliationRecorder,
           idempotency_gen: IdempotencyKeyGenerator,
           truth_assembler: TruthWriteAssembler,
           kg_assembler: KGWriteAssembler,
           outbox_assembler: OutboxEventAssembler,
           validator: ManifestValidator,
           summary_gen: SummaryGenerator,
       ):
           """Initialize with all sub-components."""
           ...

       async def execute(
           self,
           envelope: P03BatchEnvelope,
           ctx: P03RunnerContext,
       ) -> R6Output:
           """
           Execute full R6 staging workflow:
           1. Mark consolidation status for all events
           2. Populate dedup metadata
           3. Record reconciliation decisions
           4. Assemble truth layer writes
           5. Assemble KG writes
           6. Assemble outbox events
           7. Generate reconciliation summary
           8. Validate manifest
           9. Return R6Output (or raise on validation failure)
           """
           ...

       def _build_event_updates(
           self,
           event_states: Dict[str, P03EventState],
       ) -> List[StagedEventUpdate]:
           """Build all event updates for st_hipp_events."""
           ...
   ```

2. **Execution flow**:

   ```
   R1-R4 outputs → R6Coordinator.execute() → R6Output
                                           ↓
                   envelope.staged ← P03StagedWrites populated
   ```

3. **Error handling**:
   - Validation failure → return error, do not proceed to R7
   - Component failures → capture in P03Error, return FAIL result

**Acceptance Criteria**:

- [ ] All 9 sub-components integrated
- [ ] R6Output fully populated with all staged writes
- [ ] Validation runs before returning success
- [ ] Validation failure blocks R7 (returns FAIL result)
- [ ] Metrics/logging for each sub-component step
- [ ] Dry-run mode skips actual population

**Test File**: `tests/k0/modules/consolidation/staging/test_r6_coordinator.py`

---

#### Issue 5.1.12 — R6 staging unit and integration tests

**Status**: NOT_STARTED

**Goal**: Achieve ≥90% test coverage for the `k0/modules/consolidation/staging/` module with unit tests for each component and integration tests for R6Coordinator.

**Dossier References**:

- [Dossier Appendix G](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R6 contract for test cases
- [Dossier §12.2.4](../pipelines/P03_consolidation_dossier_v2.md#1224-golden-dataset-for-integration-testing) — Golden dataset for testing

**Implementation Plan Reference**:

- [P03_implementation_plan_skeleton.md Issue 5.1.12](../pipelines/P03_implementation_plan_skeleton.md) (lines 2902-2960)

**Existing Code Dependencies**:

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `tests/k0/pipelines/p03/conftest.py` | **REUSES** — Shared fixtures | `sample_event_state`, `sample_staged_writes`, `sample_phase_outputs`, `sample_envelope` |
| `tests/k0/pipelines/p03/test_p03_envelope.py` | **PATTERN** — Envelope tests | Test patterns for event state manipulation |
| `tests/k0/pipelines/p03/test_r7_r8_integration.py` | **PATTERN** — Phase integration | Integration test patterns for multi-phase |

**Test Directory Structure**:

```
tests/k0/modules/consolidation/staging/
├── __init__.py
├── conftest.py                          # Shared fixtures
├── test_r6_output.py                    # Issue 5.1.1
├── test_status_marker.py                # Issue 5.1.2
├── test_dedup_metadata.py               # Issue 5.1.3
├── test_reconciliation_recorder.py      # Issue 5.1.4
├── test_idempotency.py                  # Issue 5.1.5
├── test_truth_write_assembler.py        # Issue 5.1.6
├── test_kg_write_assembler.py           # Issue 5.1.7
├── test_outbox_assembler.py             # Issue 5.1.8
├── test_manifest_validator.py           # Issue 5.1.9
├── test_summary_generator.py            # Issue 5.1.10
├── test_r6_coordinator.py               # Issue 5.1.11
└── test_r6_integration.py               # Full R6 integration
```

**Deliverables**:

1. **Unit tests** (one per component):
   - Test normal operation
   - Test edge cases (empty inputs, max values)
   - Test error handling

2. **Integration tests** (`test_r6_integration.py`):

   ```python
   class TestR6Integration:
       async def test_r6_full_cycle(
           self,
           sample_envelope: P03BatchEnvelope,
           mock_ctx: P03RunnerContext,
       ):
           """Test R6 with realistic R1-R4 outputs."""
           ...

       async def test_r6_with_duplicates(self, ...):
           """Test R6 handles duplicate events correctly."""
           ...

       async def test_r6_with_gaps(self, ...):
           """Test R6 stages gap events for P06."""
           ...

       async def test_r6_validation_failure(self, ...):
           """Test R6 returns FAIL on validation error."""
           ...

       async def test_r6_idempotency(self, ...):
           """Test R6 produces same output on retry."""
           ...
   ```

3. **conftest.py fixtures**:

   ```python
   @pytest.fixture
   def sample_r4_outputs() -> P03PhaseOutputs:
       """Realistic R4 outputs with entities, edges, gaps."""
       ...

   @pytest.fixture
   def r6_coordinator() -> R6Coordinator:
       """Fully wired R6Coordinator for integration tests."""
       ...
   ```

4. **Golden dataset usage**:
   - Use events from `golden_dataset/p03/hipp_events_baseline.yaml`
   - Use duplicates from `golden_dataset/p03/hipp_events_duplicates.yaml`

**Acceptance Criteria**:

- [ ] ≥90% line coverage for `k0/modules/consolidation/staging/`
- [ ] All 11 component test files created
- [ ] Integration tests cover full R6 workflow
- [ ] Tests use golden dataset where applicable
- [ ] Tests are deterministic (no flaky tests)
- [ ] Tests run in <30 seconds total

**Test Command**:

```bash
python -m pytest tests/k0/modules/consolidation/staging/ -v --cov=k0/modules/consolidation/staging --cov-report=term-missing
```

---

### Epic 5.1 Wiring Issues (5.1.13-5.1.18)

> **Purpose**: Connect the new `k0/modules/consolidation/staging/` module to the existing pipeline infrastructure in `k0/pipelines/p03/`.
> These issues are **CRITICAL** — algorithm-only implementation without wiring leaves R6 disconnected from the pipeline.

---

#### Issue 5.1.13 — R6 Phase file implementation

**Status**: NOT_STARTED

**Goal**: Create the R6 phase file that implements `P03PhaseProtocol` and bridges the new staging module to the existing pipeline infrastructure.

**Dossier References**:

- [Dossier Appendix G R6](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R6 phase contract
- [Dossier §4.7](../pipelines/P03_consolidation_dossier_v2.md#47-r6--staging-table-updates) — R6 Staging requirements

**NEW Files Created in Epic 5.1 (Issues 5.1.1-5.1.11)**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/staging/r6_output.py` | `R6Output`, `StagedEventUpdate` | Output dataclass (5.1.1) |
| `k0/modules/consolidation/staging/status_marker.py` | `ConsolidationStatusMarker` | Status assignment (5.1.2) |
| `k0/modules/consolidation/staging/dedup_metadata.py` | `DedupMetadataPopulator` | Dedup metadata (5.1.3) |
| `k0/modules/consolidation/staging/reconciliation_recorder.py` | `ReconciliationRecorder` | Audit trail (5.1.4) |
| `k0/modules/consolidation/staging/idempotency.py` | `IdempotencyKeyGenerator` | Key generation (5.1.5) |
| `k0/modules/consolidation/staging/truth_write_assembler.py` | `TruthWriteAssembler` | Truth layer writes (5.1.6) |
| `k0/modules/consolidation/staging/kg_write_assembler.py` | `KGWriteAssembler` | KG writes (5.1.7) |
| `k0/modules/consolidation/staging/outbox_assembler.py` | `OutboxEventAssembler` | Outbox events (5.1.8) |
| `k0/modules/consolidation/staging/manifest_validator.py` | `ManifestValidator` | Validation (5.1.9) |
| `k0/modules/consolidation/staging/summary_generator.py` | `SummaryGenerator` | Statistics (5.1.10) |
| `k0/modules/consolidation/staging/r6_coordinator.py` | `R6Coordinator` | Orchestration (5.1.11) |

**EXISTING Files to Wire Into**:

| File | Purpose | Key Integration Points |
|------|---------|------------------------|
| `k0/pipelines/p03/phase_interface.py:160-200` | **IMPLEMENTS** — P03PhaseProtocol | `async run(envelope, ctx) -> P03PhaseResult` |
| `k0/pipelines/p03/phases/__init__.py:1-50` | **REGISTERS** — Phase exports | Add `R6Staging` to exports |
| `k0/pipelines/p03/runner_contract.py:40-55` | **USES** — P03PhaseId enum | `P03PhaseId.R6_STAGE` already defined |
| `k0/pipelines/p03/phases/r7_truth_writer.py:1-100` | **PATTERN** — Phase structure | Follow R7TruthWriter class pattern |

**Files To Create**:

| File | Purpose |
|------|---------|
| `k0/pipelines/p03/phases/r6_staging.py` | R6Staging phase class |

**Deliverables**:

1. **R6Staging class** in `r6_staging.py`:

   ```python
   from k0.modules.consolidation.staging.r6_coordinator import R6Coordinator
   from k0.pipelines.p03.phase_interface import P03PhaseResult
   from k0.pipelines.p03.runner_contract import P03PhaseId

   class R6Staging:
       """
       R6 Phase: Staging Table Updates.

       Bridges the new staging module to the pipeline infrastructure.
       Delegates to R6Coordinator for actual staging logic.
       """

       PHASE_ID = P03PhaseId.R6_STAGE

       def __init__(self, coordinator: Optional[R6Coordinator] = None):
           """Initialize with optional pre-configured coordinator."""
           self._coordinator = coordinator

       async def run(
           self,
           envelope: P03BatchEnvelope,
           ctx: P03RunnerContext,
       ) -> P03PhaseResult:
           """
           Execute R6 phase.

           1. Initialize R6Coordinator with sub-components
           2. Execute coordinator.execute(envelope, ctx)
           3. Populate envelope.staged from R6Output
           4. Return P03PhaseResult
           """
           ...

       def _create_coordinator(
           self,
           envelope: P03BatchEnvelope,
       ) -> R6Coordinator:
           """Create and wire all sub-components."""
           ...
   ```

2. **Export in phases/**init**.py**:

   ```python
   from k0.pipelines.p03.phases.r6_staging import R6Staging
   ```

**Acceptance Criteria**:

- [ ] `R6Staging` implements `P03PhaseProtocol` (duck-typed)
- [ ] `run()` returns `P03PhaseResult.done()`, `.skip()`, or `.fail()`
- [ ] `R6Coordinator` properly wired with all 9 sub-components
- [ ] Phase follows error handling pattern from R7TruthWriter
- [ ] Logging includes cycle_id, batch_id, phase metrics

**Test File**: `tests/k0/pipelines/p03/phases/test_r6_staging.py`

---

#### Issue 5.1.14 — R6 accepts R1-R4 outputs

**Status**: NOT_STARTED

**Goal**: Wire R6 phase to read all required data from `P03BatchEnvelope` populated by R0-R4 phases.

**Existing Code Dependencies**:

| File | Purpose | Key Data Consumed |
|------|---------|-------------------|
| `k0/pipelines/p03/envelope.py:50-65` | **READS** — Envelope container | `envelope.events: List[P03EventState]`, `envelope.phases: P03PhaseOutputs`, `envelope.context: P03CycleContext` |
| `k0/pipelines/p03/event_state.py:150-200` | **READS** — Per-event state | R1: `importance_score`; R2: `cluster_id`; R3: `reconciliation_action`, `is_duplicate`; R4: embedded in KG outputs |
| `k0/pipelines/p03/phase_outputs.py:500-560` | **READS** — Phase outputs container | `r2_clusters: List[EpisodeCluster]`, `r3_dedup_merges: List[DedupMerge]`, `r4_entities: List[KGEntity]`, `r4_edges: List[KGEdge]`, `r4_gap_candidates: List[GapCandidate]` |
| `k0/pipelines/p03/context.py:1-100` | **READS** — Cycle context | `cycle_id`, `tenant_id`, `space_id`, `cycle_ulid` |

**Data Flow Diagram**:

```
R0 → envelope.events populated
R1 → envelope.events[*].importance_score, hebbian_updates
R2 → envelope.phases.r2_clusters, envelope.events[*].cluster_id
R3 → envelope.events[*].reconciliation_action, is_duplicate
     envelope.phases.r3_dedup_merges, r3_decay_updates
R4 → envelope.phases.r4_entities, r4_edges, r4_gap_candidates
     envelope.events[*].kg_entities
          ↓
R6 → READS all above, WRITES envelope.staged, envelope.phases.r6_summary
```

**Deliverables**:

1. **Input extraction method** in R6Staging:

   ```python
   def _extract_inputs(
       self,
       envelope: P03BatchEnvelope,
   ) -> R6Inputs:
       """
       Extract all required inputs from envelope.

       Returns:
           R6Inputs with:
           - event_states: Dict[str, P03EventState]
           - r2_clusters: List[EpisodeCluster]
           - r3_dedup_merges: List[DedupMerge]
           - r4_entities: List[KGEntity]
           - r4_edges: List[KGEdge]
           - r4_gap_candidates: List[GapCandidate]
           - cycle_context: P03CycleContext
       """
       return R6Inputs(
           event_states={e.event_id: e for e in envelope.events},
           r2_clusters=envelope.phases.r2_clusters,
           r3_dedup_merges=envelope.phases.r3_dedup_merges,
           r4_entities=envelope.phases.r4_entities,
           r4_edges=envelope.phases.r4_edges,
           r4_gap_candidates=envelope.phases.r4_gap_candidates,
           cycle_context=envelope.context,
       )
   ```

2. **R6Inputs dataclass**:

   ```python
   @dataclass
   class R6Inputs:
       event_states: Dict[str, P03EventState]
       r2_clusters: List[EpisodeCluster]
       r3_dedup_merges: List[DedupMerge]
       r4_entities: List[KGEntity]
       r4_edges: List[KGEdge]
       r4_gap_candidates: List[GapCandidate]
       cycle_context: P03CycleContext
   ```

**Acceptance Criteria**:

- [ ] All R1-R4 outputs extracted correctly
- [ ] Missing outputs handled gracefully (empty lists)
- [ ] Event state dict keyed by event_id
- [ ] Cycle context provides tenant_id, space_id, cycle_ulid

**Test File**: `tests/k0/pipelines/p03/phases/test_r6_staging.py`

---

#### Issue 5.1.15 — R6 outputs to P03StagedWrites

**Status**: NOT_STARTED

**Goal**: Wire R6Coordinator output (R6Output) to populate the existing `P03StagedWrites` container in the envelope.

**Existing Code Dependencies**:

| File | Purpose | Key Integration Points |
|------|---------|------------------------|
| `k0/pipelines/p03/envelope.py:60-62` | **WRITES** — Envelope staged field | `envelope.staged: P03StagedWrites` |
| `k0/pipelines/p03/staged_writes.py:310-430` | **USES** — Container methods | `P03StagedWrites.add_write()`, `.add_outbox_event()`, `.total_writes()` |
| `k0/pipelines/p03/staged_writes.py:85-220` | **USES** — Write factories | `StagedWrite.insert()`, `.update()`, `.archive()` |
| `k0/pipelines/p03/phase_outputs.py:548` | **WRITES** — Phase summary | `envelope.phases.r6_summary: ReconciliationSummary` |

**Data Flow**:

```
R6Coordinator.execute() → R6Output
                              ↓
R6Staging._populate_envelope()
    ↓
envelope.staged.st_epi_writes ← R6Output.staged_truth_writes (st_epi layer)
envelope.staged.st_sem_writes ← R6Output.staged_truth_writes (st_sem layer)
envelope.staged.st_kg_dom_writes ← R6Output.staged_kg_writes (st_kg_dom layer)
envelope.staged.st_kg_edges_writes ← R6Output.staged_kg_writes (st_kg_edges layer)
envelope.staged.outbox_events ← R6Output.staged_outbox_events
envelope.staged.st_hipp_events_updates ← R6Output.staged_event_updates
envelope.phases.r6_summary ← R6Output.reconciliation_summary
```

**Deliverables**:

1. **Output population method** in R6Staging:

   ```python
   def _populate_envelope(
       self,
       envelope: P03BatchEnvelope,
       r6_output: R6Output,
   ) -> None:
       """
       Populate envelope.staged from R6Output.

       Routes each write to the appropriate layer bucket.
       """
       # Truth writes (route by layer)
       for write in r6_output.staged_truth_writes:
           envelope.staged.add_write(write)

       # KG writes (route by layer)
       for write in r6_output.staged_kg_writes:
           envelope.staged.add_write(write)

       # Outbox events
       for event in r6_output.staged_outbox_events:
           envelope.staged.outbox_events.append(event)

       # Event updates (st_hipp_events status)
       for update in r6_output.staged_event_updates:
           # Convert StagedEventUpdate to StagedWrite
           write = self._event_update_to_staged_write(update)
           envelope.staged.add_write(write)

       # Summary
       envelope.phases.r6_summary = r6_output.reconciliation_summary
   ```

2. **StagedEventUpdate → StagedWrite conversion**:

   ```python
   def _event_update_to_staged_write(
       self,
       update: StagedEventUpdate,
   ) -> StagedWrite:
       """Convert event update to st_hipp_events UPDATE write."""
       return StagedWrite.update(
           layer=LAYER_ST_HIPP_EVENTS,
           record_id=update.event_id,
           data={
               "consolidation_status": update.consolidation_status,
               "near_duplicates_json": update.near_duplicates_json,
               "novelty_score": update.novelty_score,
               "episode_cluster_id": update.episode_cluster_id,
               "reconciliation_action": update.reconciliation_action,
               "best_match_id": update.best_match_id,
               "best_match_layer": update.best_match_layer,
           },
           phase="R6",
           expected_version=1,  # st_hipp_events version column
           event_ids=[update.event_id],
       )
   ```

**Acceptance Criteria**:

- [ ] All writes routed to correct layer bucket
- [ ] `envelope.staged.total_writes()` matches R6Output counts
- [ ] `envelope.phases.r6_summary` populated
- [ ] StagedEventUpdate correctly converted to StagedWrite
- [ ] Existing P03StagedWrites structure unchanged

**Test File**: `tests/k0/pipelines/p03/phases/test_r6_staging.py`

---

#### Issue 5.1.16 — Update P03SequentialRunner for R6

**Status**: NOT_STARTED

**Goal**: Register R6 phase implementation in the sequential runner so it executes between R5 and R7.

**Existing Code Dependencies**:

| File | Purpose | Key Integration Points |
|------|---------|------------------------|
| `k0/pipelines/p03/sequential_runner.py:125-180` | **UPDATES** — Runner init | `self._phases: Dict[P03PhaseId, P03PhaseProtocol]` |
| `k0/pipelines/p03/sequential_runner.py:260-280` | **UNDERSTANDS** — Phase execution loop | Iterates `P03PhaseId.execution_order()` |
| `k0/pipelines/p03/runner_contract.py:65-75` | **USES** — Execution order | `R5_DREAM → R6_STAGE → R7_WRITE` already in order |
| `k0/pipelines/p03/phases/__init__.py:45-50` | **IMPORTS** — Phase classes | Need to add `R6Staging` import |

**Execution Order** (from runner_contract.py:65-75):

```python
def execution_order(cls) -> Tuple["P03PhaseId", ...]:
    return (
        cls.R0_INIT,
        cls.R1_SCORE,
        cls.R2_CLUSTER,
        cls.R3_PRUNE,
        cls.R4_KG,
        cls.R5_DREAM,
        cls.R6_STAGE,   # ← R6 already in order
        cls.R7_WRITE,
        cls.R8_EMIT,
    )
```

**Deliverables**:

1. **Add R6 to phases/**init**.py exports**:

   ```python
   # In k0/pipelines/p03/phases/__init__.py
   from k0.pipelines.p03.phases.r6_staging import R6Staging

   __all__ = [
       # ... existing exports
       "R6Staging",
   ]
   ```

2. **Factory function for creating full runner**:

   ```python
   # In k0/pipelines/p03/factory.py (or similar)
   def create_p03_runner(
       config: P03Config,
       syscalls: K0Syscalls,
   ) -> P03SequentialRunner:
       """Create runner with all phases wired."""
       return P03SequentialRunner(
           phases={
               P03PhaseId.R0_INIT: R0BatchSelector(config.r0),
               P03PhaseId.R1_SCORE: R1ImportanceScorer(config.r1),
               P03PhaseId.R2_CLUSTER: R2EpisodicIntegrator(config.r2),
               P03PhaseId.R3_PRUNE: R3DedupDecay(config.r3),
               P03PhaseId.R4_KG: R4KGConsolidator(config.r4),
               P03PhaseId.R5_DREAM: R5DreamExplorer(config.r5),  # M6
               P03PhaseId.R6_STAGE: R6Staging(),  # ← NEW
               P03PhaseId.R7_WRITE: R7TruthWriter(),
               P03PhaseId.R8_EMIT: R8EventEmitter(),
           }
       )
   ```

3. **Test fixture update** in `tests/k0/pipelines/p03/conftest.py`:

   ```python
   @pytest.fixture
   def phases_with_r6() -> Dict[P03PhaseId, P03PhaseProtocol]:
       """All phases including R6."""
       return {
           P03PhaseId.R0_INIT: MockR0Phase(),
           # ...
           P03PhaseId.R6_STAGE: R6Staging(),
           P03PhaseId.R7_WRITE: R7TruthWriter(),
           P03PhaseId.R8_EMIT: R8EventEmitter(),
       }
   ```

**Acceptance Criteria**:

- [ ] `R6Staging` registered in phases dict
- [ ] Runner executes R6 between R5 and R7
- [ ] Skip transitions R4→R6 (skip R5) still work
- [ ] Runner test fixtures updated
- [ ] No changes to P03PhaseId enum needed (already defined)

**Test File**: `tests/k0/pipelines/p03/test_p03_sequential_runner.py`

---

#### Issue 5.1.17 — R6 phase contract registration

**Status**: NOT_STARTED

**Goal**: Verify and update R6 phase contract in `PHASE_CONTRACTS` dictionary to match actual implementation.

**Existing Code Dependencies**:

| File | Purpose | Key Integration Points |
|------|---------|------------------------|
| `k0/pipelines/p03/runner_contract.py:256-330` | **UPDATES** — PHASE_CONTRACTS dict | `P03PhaseId.R6_STAGE: PhaseContract(...)` |
| `k0/pipelines/p03/runner_contract.py:215-250` | **USES** — PhaseContract dataclass | `purpose`, `db_reads`, `db_writes`, `idempotency_key_template`, `retryable`, `max_retries`, `dlq_condition`, `timeout_seconds`, `skip_condition` |

**Current R6 Contract** (from runner_contract.py:312-324):

```python
P03PhaseId.R6_STAGE: PhaseContract(
    phase_id=P03PhaseId.R6_STAGE,
    purpose="Mark st_hipp_events with consolidation decisions; stage reconciliation",
    db_reads=("st_hipp_events",),
    db_writes=(),  # Preparation only
    idempotency_key_template="p03:r6:{cycle_id}:{event_id}",
    retryable=True,
    max_retries=3,
    dlq_condition="Version conflict on >10% of events",
    timeout_seconds=30,
    skip_condition=None,
),
```

**Updated Contract** (after M5 implementation):

```python
P03PhaseId.R6_STAGE: PhaseContract(
    phase_id=P03PhaseId.R6_STAGE,
    purpose="Stage all R1-R5 outputs as writes; validate manifest; prepare for R7 commit",
    db_reads=("st_hipp_events",),  # For version check
    db_writes=(),  # Preparation only - R7 does actual writes
    idempotency_key_template="p03:staging:{cycle_ulid}:{event_id}",  # Updated format
    retryable=True,
    max_retries=3,
    dlq_condition="Validation failure OR version conflict on >10% of events",
    timeout_seconds=45,  # Increased for larger batches
    skip_condition=None,  # R6 is REQUIRED_PHASE
),
```

**Deliverables**:

1. **Update PHASE_CONTRACTS** in runner_contract.py:
   - Update `purpose` to reflect full staging responsibility
   - Update `idempotency_key_template` to use `cycle_ulid`
   - Update `dlq_condition` to include validation failure
   - Increase `timeout_seconds` if needed

2. **Verify REQUIRED_PHASES includes R6** (already true):

   ```python
   REQUIRED_PHASES: FrozenSet[P03PhaseId] = frozenset({
       P03PhaseId.R0_INIT,
       P03PhaseId.R1_SCORE,
       P03PhaseId.R3_PRUNE,
       P03PhaseId.R4_KG,
       P03PhaseId.R6_STAGE,  # ← Already included
       P03PhaseId.R7_WRITE,
       P03PhaseId.R8_EMIT,
   })
   ```

3. **Verify NORMAL_TRANSITIONS** (already correct):

   ```python
   NORMAL_TRANSITIONS: Dict[P03PhaseId, P03PhaseId] = {
       # ...
       P03PhaseId.R5_DREAM: P03PhaseId.R6_STAGE,
       P03PhaseId.R6_STAGE: P03PhaseId.R7_WRITE,
       # ...
   }
   ```

**Acceptance Criteria**:

- [ ] Contract `purpose` matches actual implementation
- [ ] `idempotency_key_template` matches IdempotencyKeyGenerator
- [ ] `dlq_condition` covers ManifestValidator failures
- [ ] R6 in REQUIRED_PHASES (verified, not added)
- [ ] NORMAL_TRANSITIONS correct (verified)

**Test File**: `tests/k0/pipelines/p03/test_runner_contract.py`

---

#### Issue 5.1.18 — R6 wiring integration tests

**Status**: NOT_STARTED

**Goal**: Create integration tests verifying R6 phase is correctly wired into the pipeline, receives R1-R4 outputs, and produces staged writes for R7.

**Existing Code Dependencies**:

| File | Purpose | Key Patterns |
|------|---------|--------------|
| `tests/k0/pipelines/p03/test_r7_r8_integration.py` | **PATTERN** — Multi-phase integration | Tests R7→R8 flow with realistic data |
| `tests/k0/pipelines/p03/test_full_pipeline_e2e.py` | **PATTERN** — Full pipeline test | R0→R8 end-to-end pattern |
| `tests/k0/pipelines/p03/test_p03_sequential_runner.py` | **PATTERN** — Runner tests | Phase registration, execution order |
| `tests/k0/pipelines/p03/conftest.py:350-400` | **REUSES** — Fixtures | `sample_envelope`, `sample_phase_outputs`, `mock_ctx` |

**Test Scenarios**:

| Test | Description | Validates |
|------|-------------|-----------|
| `test_r6_in_execution_order` | R6 executes between R5 and R7 | Sequential order |
| `test_r6_receives_r4_outputs` | R6 sees entities, edges, gaps from R4 | Input wiring |
| `test_r6_populates_staged_writes` | R6 fills envelope.staged | Output wiring |
| `test_r6_to_r7_handoff` | R7 receives staged writes from R6 | Phase handoff |
| `test_r6_validation_blocks_r7` | Validation failure prevents R7 | Error path |
| `test_r4_skip_r5_to_r6` | Skip transition R4→R6 works | Skip wiring |

**Files To Create**:

| File | Purpose |
|------|---------|
| `tests/k0/pipelines/p03/test_r6_wiring_integration.py` | R6 wiring integration tests |

**Deliverables**:

1. **R6 wiring integration tests**:

   ```python
   class TestR6WiringIntegration:
       """Integration tests for R6 phase wiring."""

       async def test_r6_in_execution_order(
           self,
           phases_with_r6: Dict[P03PhaseId, P03PhaseProtocol],
       ):
           """Verify R6 executes in correct position."""
           runner = P03SequentialRunner(phases=phases_with_r6)
           order = [p.value for p in P03PhaseId.execution_order()]
           assert order.index("R6") == 6  # After R5, before R7
           assert runner.has_phase(P03PhaseId.R6_STAGE)

       async def test_r6_receives_r4_outputs(
           self,
           sample_envelope: P03BatchEnvelope,
           mock_ctx: P03RunnerContext,
       ):
           """Verify R6 can access R4 phase outputs."""
           # Populate R4 outputs
           sample_envelope.phases.r4_entities = [mock_kg_entity()]
           sample_envelope.phases.r4_edges = [mock_kg_edge()]
           sample_envelope.phases.r4_gap_candidates = [mock_gap()]

           # Run R6
           r6 = R6Staging()
           result = await r6.run(sample_envelope, mock_ctx)

           assert result.is_success
           # Verify staged writes include KG data
           assert len(sample_envelope.staged.st_kg_dom_writes) > 0

       async def test_r6_populates_staged_writes(
           self,
           sample_envelope: P03BatchEnvelope,
           mock_ctx: P03RunnerContext,
       ):
           """Verify R6 populates all staged write buckets."""
           # Run R0-R4 to populate envelope
           await run_phases_r0_to_r4(sample_envelope, mock_ctx)

           # Run R6
           r6 = R6Staging()
           result = await r6.run(sample_envelope, mock_ctx)

           assert result.is_success
           assert sample_envelope.staged.total_writes() > 0
           assert sample_envelope.staged.total_outbox_events() >= 1  # completion event
           assert sample_envelope.phases.r6_summary.total_all > 0

       async def test_r6_to_r7_handoff(
           self,
           sample_envelope: P03BatchEnvelope,
           mock_ctx: P03RunnerContext,
       ):
           """Verify R7 can consume R6 staged writes."""
           # Run R6
           r6 = R6Staging()
           await r6.run(sample_envelope, mock_ctx)

           staged_before = sample_envelope.staged.total_writes()

           # Run R7
           r7 = R7TruthWriter()
           result = await r7.run(sample_envelope, mock_ctx)

           assert result.is_success
           # R7 should have processed all staged writes

       async def test_r6_validation_blocks_r7(
           self,
           sample_envelope: P03BatchEnvelope,
           mock_ctx: P03RunnerContext,
       ):
           """Verify validation failure returns FAIL, preventing R7."""
           # Create invalid state (orphan edge)
           sample_envelope.phases.r4_edges = [
               KGEdge(
                   edge_id="edge-orphan",
                   source_entity_id="nonexistent-1",
                   target_entity_id="nonexistent-2",
                   relationship_type="INVALID",
               )
           ]

           r6 = R6Staging()
           result = await r6.run(sample_envelope, mock_ctx)

           assert result.is_failed
           assert "FK integrity" in result.error_info.error_message

       async def test_skip_r5_to_r6_transition(
           self,
           phases_with_r6: Dict[P03PhaseId, P03PhaseProtocol],
           sample_envelope: P03BatchEnvelope,
           mock_ctx: P03RunnerContext,
       ):
           """Verify R4→R6 skip transition works."""
           runner = P03SequentialRunner(phases=phases_with_r6)

           # Configure R5 to skip
           mock_ctx.config["r5_skip_on_backlog"] = True
           mock_ctx.config["backlog_threshold"] = 0

           # Run from R4
           result = await runner.run(
               envelope=sample_envelope,
               ctx=mock_ctx,
               start_phase=P03PhaseId.R4_KG,
           )

           # Verify R5 skipped, R6 executed
           assert sample_envelope.phase_statuses[P03PhaseId.R5_DREAM] == P03PhaseStatus.SKIP
           assert sample_envelope.phase_statuses[P03PhaseId.R6_STAGE] == P03PhaseStatus.DONE
   ```

**Acceptance Criteria**:

- [ ] All 6 test scenarios passing
- [ ] Tests use real R6Staging, not mocks
- [ ] Tests validate actual envelope mutations
- [ ] Tests run in <10 seconds total
- [ ] No flaky tests

**Test Command**:

```bash
python -m pytest tests/k0/pipelines/p03/test_r6_wiring_integration.py -v
```

---

### Epic 5.2 — R7 TruthWriter + R8 Emission

> **Scope**: Complete the R7 TruthWriter with per-layer writers and implement R8 event emission with full gap detection and metrics.
>
> **Key Insight**: R7 performs atomic writes across all memory layers via UnitOfWork; R8 emits events via outbox drain.
>
> **Dossier Reference**: Section 4.8 "R7 — Memory Layer Writes", Section 4.9 "R8 — Event Emission"

#### Epic 5.2 Issues (16 total)

| Issue | Title | Goal |
|-------|-------|------|
| 5.2.1 | M24 TruthWriter module scaffolding and decision router | Core TruthWriter with decision routing |
| 5.2.2 | Outbox pattern implementation for durable writes | Transactional outbox for all writes |
| 5.2.3 | st_epi (episodic) layer writer | Episode records with cluster linking |
| 5.2.4 | st_sem (semantic) layer writer | Pattern records with confidence |
| 5.2.5 | st_procedural (habits) layer writer | Routine patterns |
| 5.2.6 | st_social (relationships) layer writer | Relationship strength updates |
| 5.2.7 | st_prospective (intentions) layer writer | Future-oriented patterns |
| 5.2.8 | st_kg_dom / st_kg_edges (KG) layer writer | Entity + edge persistence |
| 5.2.9 | st_vec coordination with P08 embedding index | Embedding persistence + P08 coordination |
| 5.2.10 | UnitOfWork integration for atomic multi-table writes | Atomic transactions |
| 5.2.11 | R8 bus event emission implementation | All event types per dossier |
| 5.2.12 | R8 gap emission for P06 Active Learning | Gap types + deduplication |
| 5.2.13 | Pipeline offset updates and checkpoint | Offset persistence for resume |
| 5.2.14 | Cycle metrics aggregation and emission | Metrics for monitoring |
| 5.2.15 | R7/R8 phase coordinator | Orchestrate R7/R8 phases |
| 5.2.16 | R7/R8 unit and integration tests | ≥90% coverage for truth_writer + emission |

---

#### Epic 5.2 Reference Guide

> **Purpose**: Comprehensive reference for all dependencies, existing code, and dossier sections for Epic 5.2 issues.

**Existing R7/R8 Phase Files (Created in M3)**:

| File | Lines | Key Content | Reference |
|------|-------|-------------|-----------|
| `k0/pipelines/p03/phases/r7_truth_writer.py` | 604 | R7TruthWriter class, `_execute_staged_writes()`, `_writeback_status()` | M3 Issue 3.1.1 |
| `k0/pipelines/p03/phases/r8_event_emitter.py` | 564 | R8EventEmitter class, `_build_completion_payload()`, `_process_gaps()` | M3 Issue 3.1.2 |
| `k0/pipelines/p03/gap_emitter.py` | ~300 | P03GapEmitter for gap dedup and emission | M3 Issue 3.2.3 |

**Core Dependencies (Existing Infrastructure)**:

| File | Lines | Key Classes/Functions | Used By Issues |
|------|-------|----------------------|----------------|
| `k0/pipelines/p03/staged_writes.py:280-310` | Layer constants | `LAYER_ST_EPI`, `LAYER_ST_SEM`, `LAYER_ST_PROCEDURAL`, etc. | 5.2.3-5.2.8 |
| `k0/pipelines/p03/staged_writes.py:312-450` | Container | `P03StagedWrites.add_write()`, `get_all_writes_ordered()` | 5.2.1, 5.2.10 |
| `k0/pipelines/p03/staged_writes.py:50-200` | Write factories | `StagedWrite.insert()`, `.update()`, `.archive()` | 5.2.3-5.2.8 |
| `k0/uow/unit_of_work.py:1-200` | Transactions | `UnitOfWork`, `stage_outbox()`, `upsert_offset()` | 5.2.2, 5.2.10, 5.2.13 |
| `k0/storage/outbox.py` | Outbox storage | `OutboxEntry`, `OutboxStore` | 5.2.2, 5.2.11 |
| `k0/pipelines/p03/event_state.py:120-200` | Decisions | `ReconciliationAction` enum | 5.2.1 |
| `k0/pipelines/p03/phase_outputs.py:140-250` | KG types | `KGEntity`, `KGEdge`, `CausalEdge`, `GapCandidate` | 5.2.8, 5.2.12 |
| `k0/pipelines/p03/phase_outputs.py:350-430` | Summary | `ReconciliationSummary` dataclass | 5.2.14, 5.2.15 |

**Dossier Sections for Epic 5.2**:

| Section | Title | Topics | Used By Issues |
|---------|-------|--------|----------------|
| §4.8 | R7 — Memory Layer Writes | TruthWriter overview, layer dependencies | 5.2.1, 5.2.10 |
| §4.8.1 | Outbox Pattern Implementation | st_outbox INSERT, durability, fingerprint | 5.2.2 |
| §4.8.2 | st_epi (Episodic) Writes | Episode clustering, source_events_json | 5.2.3 |
| §4.8.3 | st_sem (Semantic) Writes | Patterns, confidence, observation_count | 5.2.4 |
| §4.8.4 | st_procedural (Habits) Writes | Routines, temporal regularity | 5.2.5 |
| §4.8.5 | st_social (Relationships) Writes | Relationship strength, sentiment | 5.2.6 |
| §4.8.6 | st_prospective (Intentions) Writes | Goals, reminders, counterfactuals | 5.2.7 |
| §4.8.7 | st_kg_dom / st_kg_edges Writes | Entities, edges, causality | 5.2.8 |
| §4.8.8 | st_vec (Embeddings) Writes | Aggregated embeddings, P08 coordination | 5.2.9 |
| §4.9 | R8 — Event Emission | All event topics, offset updates | 5.2.11-5.2.14 |
| §4.9.1 | Bus Event Emission | p03.*.v1 topics | 5.2.11 |
| §4.9.2 | Pipeline Offset Updates | st_pipeline_offsets checkpoint | 5.2.13 |
| §4.9.3 | Metrics Aggregation | Cycle metrics | 5.2.14 |
| §6.15 | st_outbox Schema | Outbox table structure | 5.2.2 |
| §7.4.7 | M24 — TruthWriter | Module specification | 5.2.1 |
| §9.3.1 | Gap Emission | p03.gap.detected.v1 contract | 5.2.12 |
| Appendix D.7 | Storage Integration | UnitOfWork, optimistic locking | 5.2.10 |
| Appendix G.5 | R7/R8 State Machine | Phase transitions, idempotency | 5.2.15 |

**Module Directory to Create**:

```
k0/modules/consolidation/truth_writer/
├── __init__.py
├── router.py              # 5.2.1 - Decision router
├── result.py              # 5.2.1 - WriteResult dataclass
├── outbox.py              # 5.2.2 - OutboxWriter
├── transaction.py         # 5.2.10 - TransactionCoordinator
└── layers/
    ├── __init__.py
    ├── episodic.py        # 5.2.3 - EpisodicLayerWriter
    ├── semantic.py        # 5.2.4 - SemanticLayerWriter
    ├── procedural.py      # 5.2.5 - ProceduralLayerWriter
    ├── social.py          # 5.2.6 - SocialLayerWriter
    ├── prospective.py     # 5.2.7 - ProspectiveLayerWriter
    ├── kg.py              # 5.2.8 - KGLayerWriter
    └── vector.py          # 5.2.9 - VectorLayerWriter

k0/modules/consolidation/emission/
├── __init__.py
├── emitter.py             # 5.2.11 - EventEmitter
├── gap_emitter.py         # 5.2.12 - GapEmitter (extends k0/pipelines/p03/gap_emitter.py)
├── offset_manager.py      # 5.2.13 - OffsetManager
└── metrics.py             # 5.2.14 - MetricsAggregator
```

**Layer Write Dependency Order** (from `staged_writes.py:320-330`):

```
vec → kg_dom → kg_edges → epi → sem → procedural → social → prospective → learning_queue → hipp_events
```

**ReconciliationAction → Layer Mapping**:

| ReconciliationAction | Target Layers | Operation | Notes |
|---------------------|---------------|-----------|-------|
| `CREATE` | st_epi, st_sem, st_kg_dom | INSERT | New truth records |
| `EXTEND` | st_epi, st_sem, st_kg_dom, st_kg_edges | UPDATE | Append to existing |
| `REINFORCE` | st_sem, st_procedural | UPDATE | Increment observation_count |
| `EVOLVE` | st_sem, st_kg_dom | INSERT + UPDATE | New version, mark old non-canonical |
| `PRUNE` | All layers | ARCHIVE | Soft-delete with reason |
| `SKIP` | st_hipp_events | UPDATE | Mark as DUPLICATE |

---

#### Issue 5.2.1 — M24 TruthWriter module scaffolding and decision router

**Status**: NOT_STARTED

**Goal**: Create core TruthWriter module with decision routing to appropriate layer writers based on ReconciliationAction.

**Dossier References**:

- [§7.4.7 M24 — TruthWriter](../pipelines/P03_consolidation_dossier_v2.md#747-m24--truthwriter) — Module specification
- [§4.8 R7 — Memory Layer Writes](../pipelines/P03_consolidation_dossier_v2.md#48-r7--memory-layer-writes-truth-update) — TruthWriter logic

**Existing Code Dependencies**:

| File | Lines | Purpose | Key Patterns |
|------|-------|---------|--------------|
| `k0/pipelines/p03/phases/r7_truth_writer.py:200-215` | PATTERN | Write execution loop | `_execute_staged_writes()` iterates writes |
| `k0/pipelines/p03/event_state.py:120-145` | USES | ReconciliationAction enum | `REINFORCE`, `EXTEND`, `CREATE`, `EVOLVE`, `PRUNE`, `SKIP` |
| `k0/pipelines/p03/staged_writes.py:50-80` | USES | StagedWrite dataclass | `layer`, `operation`, `record_data` |
| `k0/pipelines/p03/staged_writes.py:312-400` | USES | P03StagedWrites container | `get_all_writes_ordered()` |
| `k0/pipelines/p03/phase_outputs.py:350-390` | WRITES | ReconciliationSummary | Decision counts by type |

**Files to Create**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/truth_writer/__init__.py` | — | Module exports |
| `k0/modules/consolidation/truth_writer/router.py` | `DecisionRouter` | Route decisions to layer writers |
| `k0/modules/consolidation/truth_writer/result.py` | `WriteResult`, `LayerWriteResult` | Structured write outcomes |
| `k0/contracts/modules/consolidation/truth_writer.yaml` | — | Module contract |

**Deliverables**:

1. **DecisionRouter class**:

   ```python
   from enum import Enum
   from typing import Dict, List, Protocol

   from k0.pipelines.p03.event_state import ReconciliationAction
   from k0.pipelines.p03.staged_writes import StagedWrite

   class LayerWriterProtocol(Protocol):
       """Protocol for layer-specific writers."""
       async def write(self, writes: List[StagedWrite], uow: "UnitOfWork") -> "LayerWriteResult":
           ...

   class WriteMode(Enum):
       ATOMIC = "ATOMIC"     # Rollback entire batch on any failure
       PARTIAL = "PARTIAL"   # Continue on failure, record failed IDs

   class DecisionRouter:
       """Route consolidation decisions to appropriate layer writers."""

       def __init__(
           self,
           layer_writers: Dict[str, LayerWriterProtocol],
           mode: WriteMode = WriteMode.ATOMIC,
       ):
           self._writers = layer_writers
           self._mode = mode

       async def route(
           self,
           staged: "P03StagedWrites",
           uow: "UnitOfWork",
       ) -> "WriteResult":
           """Route all staged writes to layer writers in dependency order."""
           results: List[LayerWriteResult] = []
           writes_ordered = staged.get_all_writes_ordered()

           for write in writes_ordered:
               writer = self._writers.get(write.layer)
               if writer is None:
                   raise ValueError(f"No writer registered for layer: {write.layer}")

               try:
                   result = await writer.write([write], uow)
                   results.append(result)
               except Exception as e:
                   if self._mode == WriteMode.ATOMIC:
                       raise  # UoW will rollback
                   results.append(LayerWriteResult.failure(write.layer, str(e)))

           return WriteResult.from_layer_results(results)
   ```

2. **WriteResult dataclass**:

   ```python
   @dataclass
   class LayerWriteResult:
       layer: str
       writes_attempted: int
       writes_succeeded: int
       writes_failed: int
       failed_ids: List[str] = field(default_factory=list)
       error_message: Optional[str] = None

       @classmethod
       def success(cls, layer: str, count: int) -> "LayerWriteResult":
           return cls(layer=layer, writes_attempted=count, writes_succeeded=count, writes_failed=0)

       @classmethod
       def failure(cls, layer: str, error: str) -> "LayerWriteResult":
           return cls(layer=layer, writes_attempted=1, writes_succeeded=0, writes_failed=1, error_message=error)

   @dataclass
   class WriteResult:
       total_attempted: int
       total_succeeded: int
       total_failed: int
       by_layer: Dict[str, LayerWriteResult]
       failed_decision_ids: List[str] = field(default_factory=list)

       @classmethod
       def from_layer_results(cls, results: List[LayerWriteResult]) -> "WriteResult":
           by_layer = {r.layer: r for r in results}
           return cls(
               total_attempted=sum(r.writes_attempted for r in results),
               total_succeeded=sum(r.writes_succeeded for r in results),
               total_failed=sum(r.writes_failed for r in results),
               by_layer=by_layer,
               failed_decision_ids=[id for r in results for id in r.failed_ids],
           )
   ```

**Acceptance Criteria**:

- [ ] All six decision types correctly routed to appropriate handlers
- [ ] ATOMIC mode rolls back entire batch on failure
- [ ] PARTIAL mode continues on failure, records failed decision IDs
- [ ] WriteResult aggregates outcomes from all layer writers
- [ ] Contract YAML defines module interface

**Test File**: `tests/k0/modules/consolidation/truth_writer/test_router.py`

---

#### Issue 5.2.2 — Outbox pattern implementation for durable writes

**Status**: NOT_STARTED

**Goal**: Implement transactional outbox pattern for all memory layer writes ensuring durability and exactly-once semantics.

**Dossier References**:

- [§4.8.1 Outbox Pattern Implementation](../pipelines/P03_consolidation_dossier_v2.md#481-outbox-pattern-implementation) — Pattern spec
- [§6.15 st_outbox Schema](../pipelines/P03_consolidation_dossier_v2.md#615-st_outbox) — Table structure

**Existing Code Dependencies**:

| File | Lines | Purpose | Key Patterns |
|------|-------|---------|--------------|
| `k0/uow/unit_of_work.py:115-130` | USES | `stage_outbox()` | Stage entry within transaction |
| `k0/storage/outbox.py:1-100` | USES | OutboxEntry, OutboxStore | Entry structure, store interface |
| `k0/pipelines/p03/phases/r7_truth_writer.py:405-440` | PATTERN | `_stage_outbox_events()` | Outbox staging pattern |
| `k0/pipelines/p03/staged_writes.py:215-270` | USES | StagedOutboxEvent | Outbox event structure |

**Files to Create**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/truth_writer/outbox.py` | `OutboxWriter` | Outbox write wrapper |
| `k0/contracts/modules/consolidation/outbox.yaml` | — | Outbox operation schema |

**Deliverables**:

1. **OutboxWriter class**:

   ```python
   from dataclasses import dataclass
   from typing import List
   import json

   from k0.storage.outbox import OutboxEntry
   from k0.uow.unit_of_work import UnitOfWork
   from k0.pipelines.p03.staged_writes import StagedWrite

   @dataclass
   class OutboxWriteConfig:
       driver: str = "p03"  # Target table prefix
       max_batch_size: int = 100
       retry_backoff_base: int = 1000  # ms

   class OutboxWriter:
       """Wrapper for durable writes via st_outbox transactional pattern."""

       def __init__(self, config: OutboxWriteConfig | None = None):
           self._config = config or OutboxWriteConfig()

       def stage_write(
           self,
           uow: UnitOfWork,
           write: StagedWrite,
           tenant_id: str,
           space_id: str,
       ) -> None:
           """Stage a StagedWrite as an outbox entry for durability."""
           entry = OutboxEntry(
               id=None,  # Auto-assigned
               wal_pos=0,  # Set by outbox store
               tenant_id=tenant_id,
               space_id=space_id,
               driver=write.layer,  # Target table
               op_kind=write.operation.value,  # INSERT/UPDATE/ARCHIVE
               payload=json.dumps(write.record_data).encode("utf-8"),
               fingerprint=write.idempotency_key,  # Prevents duplicates
               requeue_seq=0,
               retries=0,
           )
           uow.stage_outbox(entry)

       def stage_batch(
           self,
           uow: UnitOfWork,
           writes: List[StagedWrite],
           tenant_id: str,
           space_id: str,
       ) -> int:
           """Stage multiple writes. Returns count staged."""
           for write in writes[:self._config.max_batch_size]:
               self.stage_write(uow, write, tenant_id, space_id)
           return min(len(writes), self._config.max_batch_size)
   ```

2. **Fingerprint (idempotency key) format**:

   ```
   p03:write:{cycle_ulid}:{layer}:{record_id}
   ```

**Acceptance Criteria**:

- [ ] All writes go through st_outbox for durability
- [ ] Idempotency keys (fingerprint) prevent duplicate writes on retry
- [ ] Failed writes accumulate in outbox with retry scheduling
- [ ] Batch insertion supports efficiency
- [ ] Status lifecycle: PENDING → PROCESSING → DONE/FAILED

**Test File**: `tests/k0/modules/consolidation/truth_writer/test_outbox.py`

---

#### Issue 5.2.3 — st_epi (episodic) layer writer

**Status**: NOT_STARTED

**Goal**: Implement episodic memory layer writer for episode clustering results and source event linking.

**Dossier References**:

- [§4.8.2 st_epi (Episodic) Writes](../pipelines/P03_consolidation_dossier_v2.md#482-st_epi-episodic-writes) — Write spec

**Existing Code Dependencies**:

| File | Lines | Purpose | Key Patterns |
|------|-------|---------|--------------|
| `k0/pipelines/p03/staged_writes.py:284` | USES | `LAYER_ST_EPI = "st_epi"` | Layer constant |
| `k0/pipelines/p03/staged_writes.py:86-110` | USES | `StagedWrite.insert()` | INSERT factory |
| `k0/pipelines/p03/staged_writes.py:120-155` | USES | `StagedWrite.update()` | UPDATE factory with version |
| `k0/pipelines/p03/phases/r7_truth_writer.py:245-280` | PATTERN | `_execute_insert()` | INSERT with ON CONFLICT |
| `k0/pipelines/p03/phase_outputs.py:65-100` | USES | EpisodeCluster | Cluster from R2 |

**Files to Create**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/truth_writer/layers/episodic.py` | `EpisodicLayerWriter` | st_epi writes |

**Deliverables**:

1. **EpisodicLayerWriter class**:

   ```python
   from dataclasses import dataclass
   from typing import List, Optional
   import json

   from k0.pipelines.p03.staged_writes import (
       LAYER_ST_EPI,
       StagedWrite,
       WriteOperation,
   )
   from k0.uow.unit_of_work import UnitOfWork
   from k0.modules.consolidation.truth_writer.result import LayerWriteResult

   @dataclass
   class EpisodeWriteData:
       """Data for episodic layer write."""
       episode_id: str
       tenant_id: str
       space_id: str
       cluster_id: Optional[str]
       source_events_json: str  # JSON array of event_ids
       started_at_ms: int
       ended_at_ms: int
       temporal_spread_ms: int
       confidence: float = 1.0
       observation_count: int = 1

   class EpisodicLayerWriter:
       """Writer for st_epi (episodic memory) layer."""

       LAYER = LAYER_ST_EPI

       async def write(
           self,
           writes: List[StagedWrite],
           uow: UnitOfWork,
       ) -> LayerWriteResult:
           """Execute episodic layer writes."""
           succeeded = 0
           failed_ids = []

           for write in writes:
               if write.layer != self.LAYER:
                   continue

               try:
                   if write.operation == WriteOperation.INSERT:
                       await self._insert(uow, write)
                   elif write.operation == WriteOperation.UPDATE:
                       await self._update(uow, write)
                   elif write.operation == WriteOperation.ARCHIVE:
                       await self._archive(uow, write)
                   succeeded += 1
               except Exception:
                   failed_ids.append(write.record_id)

           return LayerWriteResult(
               layer=self.LAYER,
               writes_attempted=len(writes),
               writes_succeeded=succeeded,
               writes_failed=len(failed_ids),
               failed_ids=failed_ids,
           )

       async def _insert(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """INSERT new episode with ON CONFLICT DO NOTHING."""
           data = write.record_data
           await uow.connection.execute(
               """
               INSERT INTO st_epi (
                   episode_id, tenant_id, space_id, cluster_id,
                   source_events_json, started_at, ended_at,
                   temporal_spread_ms, confidence, observation_count,
                   created_at, version
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 1)
               ON CONFLICT (episode_id) DO NOTHING
               """,
               data["episode_id"],
               data["tenant_id"],
               data["space_id"],
               data.get("cluster_id"),
               data.get("source_events_json", "[]"),
               data["started_at"],
               data["ended_at"],
               data.get("temporal_spread_ms", 0),
               data.get("confidence", 1.0),
               data.get("observation_count", 1),
               data["created_at"],
           )

       async def _update(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """UPDATE episode with optimistic locking."""
           data = write.record_data
           # Build dynamic SET clause from data keys
           set_parts = []
           values = []
           idx = 1

           for key, value in data.items():
               if key != "episode_id":
                   set_parts.append(f"{key} = ${idx}")
                   values.append(value)
                   idx += 1

           values.append(write.record_id)  # WHERE clause
           values.append(write.expected_version)  # Version check

           sql = f"""
               UPDATE st_epi
               SET {", ".join(set_parts)}, version = version + 1
               WHERE episode_id = ${idx}
                 AND version = ${idx + 1}
           """
           result = await uow.connection.execute(sql, *values)

           # Check for version conflict
           rows_affected = int(result.split()[-1]) if result else 0
           if rows_affected == 0 and write.expected_version is not None:
               raise OptimisticLockError(f"Version conflict for st_epi:{write.record_id}")

       async def _archive(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """ARCHIVE episode (soft-delete)."""
           import time
           await uow.connection.execute(
               """
               UPDATE st_epi
               SET archival_status = 'ARCHIVED',
                   archived_at = $1,
                   archived_reason = $2
               WHERE episode_id = $3
                 AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
               """,
               int(time.time() * 1000),
               write.record_data.get("archived_reason", ""),
               write.record_id,
           )
   ```

2. **Idempotency key format**:

   ```
   p03:write:{cycle_ulid}:st_epi:{episode_id}
   ```

**Acceptance Criteria**:

- [ ] Episode records correctly linked to source events via source_events_json
- [ ] Temporal anchoring reflects cluster temporal bounds (started_at, ended_at)
- [ ] Idempotent writes on retry (ON CONFLICT DO NOTHING)
- [ ] Optimistic locking via version column
- [ ] ARCHIVE sets archival_status and reason

**Test File**: `tests/k0/modules/consolidation/truth_writer/layers/test_episodic.py`

---

#### Issue 5.2.4 — st_sem (semantic) layer writer

**Status**: NOT_STARTED

**Goal**: Implement semantic memory layer writer for pattern records with confidence and source episode linking.

**Dossier References**:

- [§4.8.3 st_sem (Semantic) Writes](../pipelines/P03_consolidation_dossier_v2.md#483-st_sem-semantic-writes) — Write spec

**Existing Code Dependencies**:

| File | Lines | Purpose | Key Patterns |
|------|-------|---------|--------------|
| `k0/pipelines/p03/staged_writes.py:285` | USES | `LAYER_ST_SEM = "st_sem"` | Layer constant |
| `k0/pipelines/p03/staged_writes.py:86-155` | USES | `StagedWrite.insert()`, `.update()` | Write factories |
| `k0/pipelines/p03/phases/r7_truth_writer.py:280-310` | PATTERN | `_execute_update()` | UPDATE with optimistic lock |
| `k0/pipelines/p03/event_state.py:130-145` | USES | `ReconciliationAction.EVOLVE` | Pattern evolution trigger |

**Files to Create**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/truth_writer/layers/semantic.py` | `SemanticLayerWriter` | st_sem writes |

**Deliverables**:

1. **SemanticLayerWriter class**:

   ```python
   from dataclasses import dataclass
   from typing import List, Optional
   import json
   import time

   from k0.pipelines.p03.staged_writes import (
       LAYER_ST_SEM,
       StagedWrite,
       WriteOperation,
   )
   from k0.uow.unit_of_work import UnitOfWork
   from k0.modules.consolidation.truth_writer.result import LayerWriteResult

   @dataclass
   class PatternWriteData:
       """Data for semantic layer write."""
       pattern_id: str
       tenant_id: str
       space_id: str
       pattern_type: str  # "semantic", "procedural", etc.
       canonical_name: str
       source_episodes_json: str  # JSON array of episode_ids
       initial_confidence: float
       current_confidence: float
       observation_count: int
       last_observed_at_ms: int
       is_canonical: int = 1  # 1 = canonical, 0 = superseded
       parent_pattern_id: Optional[str] = None

   class SemanticLayerWriter:
       """Writer for st_sem (semantic memory) layer."""

       LAYER = LAYER_ST_SEM

       async def write(
           self,
           writes: List[StagedWrite],
           uow: UnitOfWork,
       ) -> LayerWriteResult:
           """Execute semantic layer writes."""
           succeeded = 0
           failed_ids = []

           for write in writes:
               if write.layer != self.LAYER:
                   continue

               try:
                   if write.operation == WriteOperation.INSERT:
                       await self._insert(uow, write)
                   elif write.operation == WriteOperation.UPDATE:
                       await self._update(uow, write)
                   elif write.operation == WriteOperation.ARCHIVE:
                       await self._archive(uow, write)
                   succeeded += 1
               except Exception:
                   failed_ids.append(write.record_id)

           return LayerWriteResult(
               layer=self.LAYER,
               writes_attempted=len(writes),
               writes_succeeded=succeeded,
               writes_failed=len(failed_ids),
               failed_ids=failed_ids,
           )

       async def _insert(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """INSERT new pattern."""
           data = write.record_data
           await uow.connection.execute(
               """
               INSERT INTO st_sem (
                   pattern_id, tenant_id, space_id, pattern_type,
                   canonical_name, source_episodes_json,
                   initial_confidence, current_confidence,
                   observation_count, last_observed_at,
                   is_canonical, parent_pattern_id,
                   created_at, version
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, 1)
               ON CONFLICT (pattern_id) DO NOTHING
               """,
               data["pattern_id"],
               data["tenant_id"],
               data["space_id"],
               data.get("pattern_type", "semantic"),
               data["canonical_name"],
               data.get("source_episodes_json", "[]"),
               data.get("initial_confidence", 1.0),
               data.get("current_confidence", 1.0),
               data.get("observation_count", 1),
               data.get("last_observed_at", int(time.time() * 1000)),
               data.get("is_canonical", 1),
               data.get("parent_pattern_id"),
               data.get("created_at", int(time.time() * 1000)),
           )

       async def _update(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """UPDATE pattern with optimistic locking."""
           data = write.record_data
           action = data.get("_action")  # REINFORCE, EXTEND, EVOLVE

           if action == "REINFORCE":
               # Increment observation_count, boost confidence
               await uow.connection.execute(
                   """
                   UPDATE st_sem
                   SET observation_count = observation_count + 1,
                       last_observed_at = $1,
                       current_confidence = LEAST(current_confidence * 1.1, 1.0),
                       version = version + 1
                   WHERE pattern_id = $2 AND version = $3
                   """,
                   int(time.time() * 1000),
                   write.record_id,
                   write.expected_version,
               )
           elif action == "EXTEND":
               # Append episodes to source_episodes_json
               await uow.connection.execute(
                   """
                   UPDATE st_sem
                   SET source_episodes_json = source_episodes_json || $1::jsonb,
                       observation_count = observation_count + 1,
                       last_observed_at = $2,
                       version = version + 1
                   WHERE pattern_id = $3 AND version = $4
                   """,
                   data.get("new_episodes_json", "[]"),
                   int(time.time() * 1000),
                   write.record_id,
                   write.expected_version,
               )
           elif action == "EVOLVE":
               # Mark old pattern non-canonical
               await uow.connection.execute(
                   """
                   UPDATE st_sem
                   SET is_canonical = 0, version = version + 1
                   WHERE pattern_id = $1 AND version = $2
                   """,
                   write.record_id,
                   write.expected_version,
               )
   ```

**Acceptance Criteria**:

- [ ] Pattern records link to source episodes via source_episodes_json
- [ ] Confidence correctly updated based on decision type (REINFORCE boosts)
- [ ] Pattern evolution maintains version history (is_canonical=0 for old)
- [ ] observation_count and last_observed_at tracked
- [ ] parent_pattern_id supports pattern hierarchy

**Test File**: `tests/k0/modules/consolidation/truth_writer/layers/test_semantic.py`

---

#### Issue 5.2.5 — st_procedural (habits) layer writer

**Status**: NOT_STARTED

**Goal**: Implement procedural memory layer writer for routine patterns and temporal regularity.

**Dossier References**:

- [§4.8.4 st_procedural (Habits) Writes](../pipelines/P03_consolidation_dossier_v2.md#484-st_procedural-habits-writes) — Write spec

**Existing Code Dependencies**:

| File | Lines | Purpose | Key Patterns |
|------|-------|---------|--------------|
| `k0/pipelines/p03/staged_writes.py:286` | USES | `LAYER_ST_PROCEDURAL = "st_procedural"` | Layer constant |
| `k0/pipelines/p03/staged_writes.py:160-200` | USES | `StagedWrite.archive()` | ARCHIVE for decay |
| `k0/pipelines/p03/phases/r7_truth_writer.py:320-350` | PATTERN | `_execute_archive()` | Soft-delete pattern |

**Files to Create**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/truth_writer/layers/procedural.py` | `ProceduralLayerWriter` | st_procedural writes |

**Deliverables**:

1. **ProceduralLayerWriter class**:

   ```python
   from dataclasses import dataclass
   from typing import List, Optional
   import json
   import time

   from k0.pipelines.p03.staged_writes import (
       LAYER_ST_PROCEDURAL,
       StagedWrite,
       WriteOperation,
   )
   from k0.uow.unit_of_work import UnitOfWork
   from k0.modules.consolidation.truth_writer.result import LayerWriteResult

   @dataclass
   class RoutineWriteData:
       """Data for procedural layer write."""
       routine_id: str
       tenant_id: str
       space_id: str
       routine_name: str
       action_sequence_json: str  # JSON array of action steps
       trigger_conditions_json: str  # JSON object with triggers
       expected_outcomes_json: str  # JSON array of outcomes
       temporal_regularity: float  # 0.0-1.0 regularity score
       daily_pattern: Optional[str] = None  # Cron-like pattern
       weekly_pattern: Optional[str] = None
       confidence: float = 1.0
       value_function: Optional[float] = None  # V(s) for TDL-HCO

   class ProceduralLayerWriter:
       """Writer for st_procedural (habits/routines) layer."""

       LAYER = LAYER_ST_PROCEDURAL

       async def write(
           self,
           writes: List[StagedWrite],
           uow: UnitOfWork,
       ) -> LayerWriteResult:
           """Execute procedural layer writes."""
           succeeded = 0
           failed_ids = []

           for write in writes:
               if write.layer != self.LAYER:
                   continue

               try:
                   if write.operation == WriteOperation.INSERT:
                       await self._insert(uow, write)
                   elif write.operation == WriteOperation.UPDATE:
                       await self._update(uow, write)
                   elif write.operation == WriteOperation.ARCHIVE:
                       await self._archive(uow, write)
                   succeeded += 1
               except Exception:
                   failed_ids.append(write.record_id)

           return LayerWriteResult(
               layer=self.LAYER,
               writes_attempted=len(writes),
               writes_succeeded=succeeded,
               writes_failed=len(failed_ids),
               failed_ids=failed_ids,
           )

       async def _insert(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """INSERT new routine pattern."""
           data = write.record_data
           await uow.connection.execute(
               """
               INSERT INTO st_procedural (
                   routine_id, tenant_id, space_id, routine_name,
                   action_sequence_json, trigger_conditions_json,
                   expected_outcomes_json, temporal_regularity,
                   daily_pattern, weekly_pattern, confidence,
                   value_function, created_at, version
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, 1)
               ON CONFLICT (routine_id) DO NOTHING
               """,
               data["routine_id"],
               data["tenant_id"],
               data["space_id"],
               data["routine_name"],
               data.get("action_sequence_json", "[]"),
               data.get("trigger_conditions_json", "{}"),
               data.get("expected_outcomes_json", "[]"),
               data.get("temporal_regularity", 0.0),
               data.get("daily_pattern"),
               data.get("weekly_pattern"),
               data.get("confidence", 1.0),
               data.get("value_function"),
               int(time.time() * 1000),
           )

       async def _update(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """UPDATE routine with reinforcement."""
           data = write.record_data
           action = data.get("_action")

           if action == "REINFORCE":
               await uow.connection.execute(
                   """
                   UPDATE st_procedural
                   SET confidence = LEAST(confidence * 1.1, 1.0),
                       temporal_regularity = (temporal_regularity + $1) / 2,
                       last_observed_at = $2,
                       version = version + 1
                   WHERE routine_id = $3 AND version = $4
                   """,
                   data.get("new_regularity", 0.5),
                   int(time.time() * 1000),
                   write.record_id,
                   write.expected_version,
               )
           elif action == "EXTEND":
               # Append new action sequences
               await uow.connection.execute(
                   """
                   UPDATE st_procedural
                   SET action_sequence_json = action_sequence_json || $1::jsonb,
                       version = version + 1
                   WHERE routine_id = $2 AND version = $3
                   """,
                   data.get("new_actions_json", "[]"),
                   write.record_id,
                   write.expected_version,
               )

       async def _archive(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """ARCHIVE decayed routine."""
           await uow.connection.execute(
               """
               UPDATE st_procedural
               SET archival_status = 'ARCHIVED',
                   archived_at = $1,
                   archived_reason = $2
               WHERE routine_id = $3
                 AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
               """,
               int(time.time() * 1000),
               write.record_data.get("archived_reason", "decay"),
               write.record_id,
           )
   ```

**Acceptance Criteria**:

- [ ] Routine patterns correctly encode action sequences (action_sequence_json)
- [ ] Temporal regularity reflects observed patterns (daily/weekly patterns)
- [ ] Value function storage ready for R5 Dream phase (TDL-HCO integration)
- [ ] PRUNE operation archives decayed routines
- [ ] trigger_conditions_json supports multiple trigger types

**Test File**: `tests/k0/modules/consolidation/truth_writer/layers/test_procedural.py`

---

#### Issue 5.2.6 — st_social (relationships) layer writer

**Status**: NOT_STARTED

**Goal**: Implement social memory layer writer for relationship strength and interaction tracking.

**Dossier References**:

- [§4.8.5 st_social (Relationships) Writes](../pipelines/P03_consolidation_dossier_v2.md#485-st_social-relationships-writes) — Write spec

**Existing Code Dependencies**:

| File | Lines | Purpose | Key Patterns |
|------|-------|---------|--------------|
| `k0/pipelines/p03/staged_writes.py:287` | USES | `LAYER_ST_SOCIAL = "st_social"` | Layer constant |
| `k0/pipelines/p03/staged_writes.py:86-155` | USES | `StagedWrite.insert()`, `.update()` | Write factories |

**Files to Create**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/truth_writer/layers/social.py` | `SocialLayerWriter` | st_social writes |

**Deliverables**:

1. **SocialLayerWriter class**:

   ```python
   from dataclasses import dataclass
   from typing import List, Optional
   import json
   import time

   from k0.pipelines.p03.staged_writes import (
       LAYER_ST_SOCIAL,
       StagedWrite,
       WriteOperation,
   )
   from k0.uow.unit_of_work import UnitOfWork
   from k0.modules.consolidation.truth_writer.result import LayerWriteResult

   @dataclass
   class RelationshipWriteData:
       """Data for social layer write."""
       relationship_id: str
       tenant_id: str
       space_id: str
       actor_a_id: str  # Person/entity ID
       actor_b_id: str  # Person/entity ID
       relationship_type: str  # "friend", "colleague", "family", etc.
       strength: float  # 0.0-1.0 relationship strength
       interaction_count: int
       last_interaction_at_ms: int
       sentiment_avg: float  # -1.0 to 1.0 rolling average
       interaction_types_json: str  # JSON array of interaction types

   class SocialLayerWriter:
       """Writer for st_social (relationships) layer."""

       LAYER = LAYER_ST_SOCIAL

       # Decay factor for inactive relationships
       DECAY_FACTOR = 0.95  # 5% decay per period of inactivity

       async def write(
           self,
           writes: List[StagedWrite],
           uow: UnitOfWork,
       ) -> LayerWriteResult:
           """Execute social layer writes."""
           succeeded = 0
           failed_ids = []

           for write in writes:
               if write.layer != self.LAYER:
                   continue

               try:
                   if write.operation == WriteOperation.INSERT:
                       await self._insert(uow, write)
                   elif write.operation == WriteOperation.UPDATE:
                       await self._update(uow, write)
                   elif write.operation == WriteOperation.ARCHIVE:
                       await self._archive(uow, write)
                   succeeded += 1
               except Exception:
                   failed_ids.append(write.record_id)

           return LayerWriteResult(
               layer=self.LAYER,
               writes_attempted=len(writes),
               writes_succeeded=succeeded,
               writes_failed=len(failed_ids),
               failed_ids=failed_ids,
           )

       async def _insert(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """INSERT new relationship."""
           data = write.record_data
           await uow.connection.execute(
               """
               INSERT INTO st_social (
                   relationship_id, tenant_id, space_id,
                   actor_a_id, actor_b_id, relationship_type,
                   strength, interaction_count, last_interaction_at,
                   sentiment_avg, interaction_types_json,
                   created_at, version
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 1)
               ON CONFLICT (relationship_id) DO NOTHING
               """,
               data["relationship_id"],
               data["tenant_id"],
               data["space_id"],
               data["actor_a_id"],
               data["actor_b_id"],
               data.get("relationship_type", "unknown"),
               data.get("strength", 0.5),
               data.get("interaction_count", 1),
               data.get("last_interaction_at", int(time.time() * 1000)),
               data.get("sentiment_avg", 0.0),
               data.get("interaction_types_json", "[]"),
               int(time.time() * 1000),
           )

       async def _update(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """UPDATE relationship with interaction tracking."""
           data = write.record_data
           action = data.get("_action")

           if action == "REINFORCE":
               # Boost strength, update interaction metrics
               new_sentiment = data.get("new_sentiment", 0.0)
               await uow.connection.execute(
                   """
                   UPDATE st_social
                   SET strength = LEAST(strength * 1.1, 1.0),
                       interaction_count = interaction_count + 1,
                       last_interaction_at = $1,
                       sentiment_avg = (sentiment_avg * 0.9 + $2 * 0.1),
                       version = version + 1
                   WHERE relationship_id = $3 AND version = $4
                   """,
                   int(time.time() * 1000),
                   new_sentiment,
                   write.record_id,
                   write.expected_version,
               )
           elif action == "EXTEND":
               # Add new interaction types
               await uow.connection.execute(
                   """
                   UPDATE st_social
                   SET interaction_types_json = interaction_types_json || $1::jsonb,
                       interaction_count = interaction_count + 1,
                       last_interaction_at = $2,
                       version = version + 1
                   WHERE relationship_id = $3 AND version = $4
                   """,
                   data.get("new_types_json", "[]"),
                   int(time.time() * 1000),
                   write.record_id,
                   write.expected_version,
               )
           elif action == "DECAY":
               # Apply decay for inactive relationship
               await uow.connection.execute(
                   """
                   UPDATE st_social
                   SET strength = strength * $1,
                       version = version + 1
                   WHERE relationship_id = $2 AND version = $3
                   """,
                   self.DECAY_FACTOR,
                   write.record_id,
                   write.expected_version,
               )

       async def _archive(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """ARCHIVE inactive relationship."""
           await uow.connection.execute(
               """
               UPDATE st_social
               SET archival_status = 'ARCHIVED',
                   archived_at = $1,
                   archived_reason = $2
               WHERE relationship_id = $3
                 AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
               """,
               int(time.time() * 1000),
               write.record_data.get("archived_reason", "inactive"),
               write.record_id,
           )
   ```

**Acceptance Criteria**:

- [ ] Relationship strength reflects interaction patterns
- [ ] Sentiment aggregation smooths individual data points (rolling average)
- [ ] Inactive relationships decay appropriately (DECAY action)
- [ ] interaction_count and last_interaction_at tracked
- [ ] actor_a_id/actor_b_id correctly identify relationship participants

**Test File**: `tests/k0/modules/consolidation/truth_writer/layers/test_social.py`

---

#### Issue 5.2.7 — st_prospective (intentions) layer writer

**Status**: NOT_STARTED

**Goal**: Implement prospective memory layer writer for future-oriented patterns and goal inference.

**Dossier References**:

- [§4.8.6 st_prospective (Intentions) Writes](../pipelines/P03_consolidation_dossier_v2.md#486-st_prospective-intentions-writes) — Write spec

**Existing Code Dependencies**:

| File | Lines | Purpose | Key Patterns |
|------|-------|---------|--------------|
| `k0/pipelines/p03/staged_writes.py:288` | USES | `LAYER_ST_PROSPECTIVE = "st_prospective"` | Layer constant |
| `k0/pipelines/p03/staged_writes.py:86-200` | USES | `StagedWrite.insert()`, `.update()`, `.archive()` | Write factories |
| `k0/pipelines/p03/phases/r7_truth_writer.py:320-350` | PATTERN | `_execute_archive()` | Archive for expired intentions |

**Files to Create**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/truth_writer/layers/prospective.py` | `ProspectiveLayerWriter` | st_prospective writes |

**Deliverables**:

1. **ProspectiveLayerWriter class**:

   ```python
   from dataclasses import dataclass
   from typing import List, Optional
   import json
   import time

   from k0.pipelines.p03.staged_writes import (
       LAYER_ST_PROSPECTIVE,
       StagedWrite,
       WriteOperation,
   )
   from k0.uow.unit_of_work import UnitOfWork
   from k0.modules.consolidation.truth_writer.result import LayerWriteResult

   @dataclass
   class IntentionWriteData:
       """Data for prospective layer write."""
       intention_id: str
       tenant_id: str
       space_id: str
       intention_type: str  # "goal", "reminder", "plan", "intention"
       description: str
       trigger_time_ms: Optional[int]  # When to remind/trigger
       trigger_context_json: str  # JSON object with context triggers
       goal_inference_json: str  # JSON object with inferred goals
       confidence: float
       status: str  # "pending", "completed", "expired", "cancelled"
       source_episodes_json: str  # Contributing episodes
       counterfactual_json: Optional[str] = None  # From R5 CPN

   class ProspectiveLayerWriter:
       """Writer for st_prospective (intentions/goals) layer."""

       LAYER = LAYER_ST_PROSPECTIVE

       async def write(
           self,
           writes: List[StagedWrite],
           uow: UnitOfWork,
       ) -> LayerWriteResult:
           """Execute prospective layer writes."""
           succeeded = 0
           failed_ids = []

           for write in writes:
               if write.layer != self.LAYER:
                   continue

               try:
                   if write.operation == WriteOperation.INSERT:
                       await self._insert(uow, write)
                   elif write.operation == WriteOperation.UPDATE:
                       await self._update(uow, write)
                   elif write.operation == WriteOperation.ARCHIVE:
                       await self._archive(uow, write)
                   succeeded += 1
               except Exception:
                   failed_ids.append(write.record_id)

           return LayerWriteResult(
               layer=self.LAYER,
               writes_attempted=len(writes),
               writes_succeeded=succeeded,
               writes_failed=len(failed_ids),
               failed_ids=failed_ids,
           )

       async def _insert(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """INSERT new intention/goal."""
           data = write.record_data
           await uow.connection.execute(
               """
               INSERT INTO st_prospective (
                   intention_id, tenant_id, space_id, intention_type,
                   description, trigger_time, trigger_context_json,
                   goal_inference_json, confidence, status,
                   source_episodes_json, counterfactual_json,
                   created_at, version
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, 1)
               ON CONFLICT (intention_id) DO NOTHING
               """,
               data["intention_id"],
               data["tenant_id"],
               data["space_id"],
               data.get("intention_type", "intention"),
               data.get("description", ""),
               data.get("trigger_time"),
               data.get("trigger_context_json", "{}"),
               data.get("goal_inference_json", "{}"),
               data.get("confidence", 0.5),
               data.get("status", "pending"),
               data.get("source_episodes_json", "[]"),
               data.get("counterfactual_json"),
               int(time.time() * 1000),
           )

       async def _update(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """UPDATE intention with goal inference or status change."""
           data = write.record_data
           action = data.get("_action")

           if action == "EXTEND":
               # Update goal inference, add trigger contexts
               await uow.connection.execute(
                   """
                   UPDATE st_prospective
                   SET goal_inference_json = $1,
                       trigger_context_json = trigger_context_json || $2::jsonb,
                       confidence = $3,
                       version = version + 1
                   WHERE intention_id = $4 AND version = $5
                   """,
                   data.get("goal_inference_json", "{}"),
                   data.get("new_triggers_json", "{}"),
                   data.get("confidence", 0.5),
                   write.record_id,
                   write.expected_version,
               )
           elif action == "COMPLETE":
               # Mark intention as completed
               await uow.connection.execute(
                   """
                   UPDATE st_prospective
                   SET status = 'completed',
                       completed_at = $1,
                       version = version + 1
                   WHERE intention_id = $2 AND version = $3
                   """,
                   int(time.time() * 1000),
                   write.record_id,
                   write.expected_version,
               )
           elif action == "COUNTERFACTUAL":
               # Store counterfactual from R5 CPN
               await uow.connection.execute(
                   """
                   UPDATE st_prospective
                   SET counterfactual_json = $1,
                       version = version + 1
                   WHERE intention_id = $2 AND version = $3
                   """,
                   data.get("counterfactual_json", "{}"),
                   write.record_id,
                   write.expected_version,
               )

       async def _archive(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """ARCHIVE expired/cancelled intention."""
           reason = write.record_data.get("archived_reason", "expired")
           await uow.connection.execute(
               """
               UPDATE st_prospective
               SET archival_status = 'ARCHIVED',
                   status = CASE
                       WHEN $1 = 'expired' THEN 'expired'
                       WHEN $1 = 'cancelled' THEN 'cancelled'
                       ELSE status
                   END,
                   archived_at = $2,
                   archived_reason = $1
               WHERE intention_id = $3
                 AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
               """,
               reason,
               int(time.time() * 1000),
               write.record_id,
           )
   ```

**Acceptance Criteria**:

- [ ] Future patterns correctly linked to source episodes
- [ ] Goal inference results stored with confidence
- [ ] Counterfactuals from R5 CPN persisted for retrieval
- [ ] trigger_time and trigger_context_json support reminder hints
- [ ] Status lifecycle: pending → completed/expired/cancelled

**Test File**: `tests/k0/modules/consolidation/truth_writer/layers/test_prospective.py`

---

#### Issue 5.2.8 — st_kg_dom / st_kg_edges (KG) layer writer

**Status**: NOT_STARTED

**Goal**: Implement knowledge graph layer writer for entity and edge persistence from M21 KGConsolidator.

**Dossier References**:

- [§4.8.7 st_kg_dom / st_kg_edges Writes](../pipelines/P03_consolidation_dossier_v2.md#487-st_kg_dom--st_kg_edges-kg-writes) — Write spec

**Existing Code Dependencies**:

| File | Lines | Purpose | Key Patterns |
|------|-------|---------|--------------|
| `k0/pipelines/p03/staged_writes.py:289-290` | USES | `LAYER_ST_KG_DOM`, `LAYER_ST_KG_EDGES` | Layer constants |
| `k0/pipelines/p03/phase_outputs.py:140-200` | USES | `KGEntity`, `KGEdge` | Entity/edge dataclasses |
| `k0/pipelines/p03/phase_outputs.py:200-250` | USES | `CausalEdge` | Granger causality edges |
| `k0/pipelines/p03/phases/r7_truth_writer.py:44-55` | USES | `LAYER_PK_MAP` | PK column mapping |
| `k0/pipelines/p03/phases/r4_entity_merger.py` | PATTERN | Entity merge cascade | st_entity_merges tracking |

**Files to Create**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/truth_writer/layers/kg.py` | `KGLayerWriter` | st_kg_dom + st_kg_edges writes |

**Deliverables**:

1. **KGLayerWriter class**:

   ```python
   from dataclasses import dataclass
   from typing import List, Optional
   import json
   import time

   from k0.pipelines.p03.staged_writes import (
       LAYER_ST_KG_DOM,
       LAYER_ST_KG_EDGES,
       StagedWrite,
       WriteOperation,
   )
   from k0.uow.unit_of_work import UnitOfWork
   from k0.modules.consolidation.truth_writer.result import LayerWriteResult

   @dataclass
   class EntityWriteData:
       """Data for st_kg_dom write."""
       entity_id: str
       tenant_id: str
       space_id: str
       entity_type: str  # "PERSON", "LOCATION", "EVENT", etc.
       canonical_name: str
       attributes_json: str  # JSON object with entity attributes
       embedding: Optional[bytes]  # Binary embedding vector
       confidence: float
       valid_from_ms: int
       valid_to_ms: Optional[int]
       source_events_json: str

   @dataclass
   class EdgeWriteData:
       """Data for st_kg_edges write."""
       edge_id: str
       tenant_id: str
       space_id: str
       source_entity_id: str
       target_entity_id: str
       relation_type: str  # "KNOWS", "LOCATED_AT", "CAUSES", etc.
       confidence: float
       valid_from_ms: int
       valid_to_ms: Optional[int]
       precedence_ratio: Optional[float] = None  # For Granger causality CAUSES edges
       attributes_json: str = "{}"

   class KGLayerWriter:
       """Writer for st_kg_dom (entities) and st_kg_edges (relationships) layers."""

       async def write(
           self,
           writes: List[StagedWrite],
           uow: UnitOfWork,
       ) -> LayerWriteResult:
           """Execute KG layer writes (both dom and edges)."""
           succeeded = 0
           failed_ids = []

           for write in writes:
               try:
                   if write.layer == LAYER_ST_KG_DOM:
                       await self._write_entity(uow, write)
                   elif write.layer == LAYER_ST_KG_EDGES:
                       await self._write_edge(uow, write)
                   else:
                       continue
                   succeeded += 1
               except Exception:
                   failed_ids.append(write.record_id)

           return LayerWriteResult(
               layer="kg",  # Combined layer name
               writes_attempted=len(writes),
               writes_succeeded=succeeded,
               writes_failed=len(failed_ids),
               failed_ids=failed_ids,
           )

       async def _write_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """Write to st_kg_dom."""
           if write.operation == WriteOperation.INSERT:
               await self._insert_entity(uow, write)
           elif write.operation == WriteOperation.UPDATE:
               await self._update_entity(uow, write)
           elif write.operation == WriteOperation.ARCHIVE:
               await self._archive_entity(uow, write)

       async def _insert_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """INSERT new entity."""
           data = write.record_data
           await uow.connection.execute(
               """
               INSERT INTO st_kg_dom (
                   entity_id, tenant_id, space_id, entity_type,
                   canonical_name, attributes_json, embedding,
                   confidence, valid_from, valid_to,
                   source_events_json, created_at, version
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 1)
               ON CONFLICT (entity_id) DO NOTHING
               """,
               data["entity_id"],
               data["tenant_id"],
               data["space_id"],
               data["entity_type"],
               data["canonical_name"],
               data.get("attributes_json", "{}"),
               data.get("embedding"),  # bytes or None
               data.get("confidence", 1.0),
               data.get("valid_from", int(time.time() * 1000)),
               data.get("valid_to"),
               data.get("source_events_json", "[]"),
               int(time.time() * 1000),
           )

       async def _update_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """UPDATE entity with optimistic locking."""
           data = write.record_data
           action = data.get("_action")

           if action == "EXTEND":
               # Update attributes, boost confidence
               await uow.connection.execute(
                   """
                   UPDATE st_kg_dom
                   SET attributes_json = attributes_json || $1::jsonb,
                       source_events_json = source_events_json || $2::jsonb,
                       confidence = LEAST(confidence * 1.1, 1.0),
                       version = version + 1
                   WHERE entity_id = $3 AND version = $4
                   """,
                   data.get("new_attributes_json", "{}"),
                   data.get("new_events_json", "[]"),
                   write.record_id,
                   write.expected_version,
               )
           elif action == "EVOLVE":
               # Mark old entity invalid, caller creates new version
               await uow.connection.execute(
                   """
                   UPDATE st_kg_dom
                   SET valid_to = $1,
                       version = version + 1
                   WHERE entity_id = $2 AND version = $3
                   """,
                   int(time.time() * 1000),
                   write.record_id,
                   write.expected_version,
               )

       async def _archive_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """ARCHIVE low-confidence entity."""
           await uow.connection.execute(
               """
               UPDATE st_kg_dom
               SET archival_status = 'ARCHIVED',
                   archived_at = $1,
                   archived_reason = $2
               WHERE entity_id = $3
                 AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
               """,
               int(time.time() * 1000),
               write.record_data.get("archived_reason", "low_confidence"),
               write.record_id,
           )

       async def _write_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """Write to st_kg_edges."""
           if write.operation == WriteOperation.INSERT:
               await self._insert_edge(uow, write)
           elif write.operation == WriteOperation.UPDATE:
               await self._update_edge(uow, write)
           elif write.operation == WriteOperation.ARCHIVE:
               await self._archive_edge(uow, write)

       async def _insert_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """INSERT new edge."""
           data = write.record_data
           await uow.connection.execute(
               """
               INSERT INTO st_kg_edges (
                   edge_id, tenant_id, space_id,
                   source_entity_id, target_entity_id, relation_type,
                   confidence, valid_from, valid_to,
                   precedence_ratio, attributes_json,
                   created_at, version
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 1)
               ON CONFLICT (edge_id) DO NOTHING
               """,
               data["edge_id"],
               data["tenant_id"],
               data["space_id"],
               data["source_entity_id"],
               data["target_entity_id"],
               data["relation_type"],
               data.get("confidence", 1.0),
               data.get("valid_from", int(time.time() * 1000)),
               data.get("valid_to"),
               data.get("precedence_ratio"),  # For CAUSES edges
               data.get("attributes_json", "{}"),
               int(time.time() * 1000),
           )

       async def _update_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """UPDATE edge confidence/attributes."""
           data = write.record_data
           await uow.connection.execute(
               """
               UPDATE st_kg_edges
               SET confidence = $1,
                   attributes_json = attributes_json || $2::jsonb,
                   version = version + 1
               WHERE edge_id = $3 AND version = $4
               """,
               data.get("confidence", 1.0),
               data.get("new_attributes_json", "{}"),
               write.record_id,
               write.expected_version,
           )

       async def _archive_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """ARCHIVE low-confidence edge."""
           await uow.connection.execute(
               """
               UPDATE st_kg_edges
               SET archival_status = 'ARCHIVED',
                   archived_at = $1,
                   archived_reason = $2
               WHERE edge_id = $3
                 AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
               """,
               int(time.time() * 1000),
               write.record_data.get("archived_reason", "low_confidence"),
               write.record_id,
           )

       async def track_merge(
           self,
           uow: UnitOfWork,
           source_id: str,
           target_id: str,
           merge_reason: str,
       ) -> None:
           """Track entity merge in st_entity_merges for undo support."""
           await uow.connection.execute(
               """
               INSERT INTO st_entity_merges (
                   source_entity_id, target_entity_id,
                   merge_reason, merged_at
               ) VALUES ($1, $2, $3, $4)
               ON CONFLICT (source_entity_id, target_entity_id) DO NOTHING
               """,
               source_id,
               target_id,
               merge_reason,
               int(time.time() * 1000),
           )
   ```

**Acceptance Criteria**:

- [ ] Entities correctly persisted with embeddings (binary format)
- [ ] Edges include temporal validity and direction (source → target)
- [ ] Merge cascade tracked in st_entity_merges for undo support
- [ ] Granger causality CAUSES edges store precedence_ratio
- [ ] valid_from/valid_to support temporal windowing

**Test File**: `tests/k0/modules/consolidation/truth_writer/layers/test_kg.py`

---

#### Issue 5.2.9 — st_vec coordination with P08 embedding index

**Status**: NOT_STARTED

**Goal**: Implement vector embedding layer writer with P08 index notification for search updates.

**Dossier References**:

- [§4.8.8 st_vec (Embeddings) Writes](../pipelines/P03_consolidation_dossier_v2.md#488-st_vec-embeddings-writes) — Write spec
- [§9.4 P03 → P08 Contract](../pipelines/P03_consolidation_dossier_v2.md#94-p03--p08-contract) — P08 coordination

**Existing Code Dependencies**:

| File | Lines | Purpose | Key Patterns |
|------|-------|---------|--------------|
| `k0/pipelines/p03/staged_writes.py:291` | USES | `LAYER_ST_VEC = "st_vec"` | Layer constant |
| `k0/pipelines/p03/staged_writes.py:215-270` | USES | `StagedOutboxEvent` | Outbox event for P08 notification |
| `k0/uow/unit_of_work.py:115-130` | USES | `stage_outbox()` | Stage P08 notification |
| `k0/pipelines/p03/phases/r8_event_emitter.py:67-70` | PATTERN | Topic constants | Event topic naming |

**Files to Create**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/truth_writer/layers/vector.py` | `VectorLayerWriter` | st_vec writes + P08 coordination |
| `k0/contracts/events/p03.embedding.created.v1.yaml` | — | Embedding created event schema |
| `k0/contracts/events/p03.embedding.updated.v1.yaml` | — | Embedding updated event schema |

**Deliverables**:

1. **VectorLayerWriter class**:

   ```python
   from dataclasses import dataclass
   from typing import List, Optional
   import json
   import time
   import hashlib

   from k0.pipelines.p03.staged_writes import (
       LAYER_ST_VEC,
       StagedWrite,
       WriteOperation,
   )
   from k0.storage.outbox import OutboxEntry
   from k0.uow.unit_of_work import UnitOfWork
   from k0.modules.consolidation.truth_writer.result import LayerWriteResult

   # P08 coordination event topics
   P08_EMBEDDING_CREATED = "p03.embedding.created.v1"
   P08_EMBEDDING_UPDATED = "p03.embedding.updated.v1"

   @dataclass
   class EmbeddingWriteData:
       """Data for st_vec write."""
       embedding_id: str
       tenant_id: str
       space_id: str
       source_type: str  # "entity", "pattern", "episode"
       source_id: str  # ID of source record
       embedding: bytes  # Binary embedding vector
       model_version: str  # e.g., "text-embedding-3-small-v1"
       source_count: int  # Number of contributing texts
       aggregation_method: str  # "mean", "weighted_mean", "max"

   @dataclass
   class P08CircuitBreakerConfig:
       """Config for P08 unavailability circuit breaker."""
       failure_threshold: int = 5
       reset_timeout_ms: int = 60000  # 1 minute
       use_cached_on_failure: bool = True

   class VectorLayerWriter:
       """Writer for st_vec (embeddings) layer with P08 index coordination."""

       LAYER = LAYER_ST_VEC

       def __init__(self, p08_config: Optional[P08CircuitBreakerConfig] = None):
           self._p08_config = p08_config or P08CircuitBreakerConfig()
           self._p08_failures = 0
           self._last_failure_ms = 0

       async def write(
           self,
           writes: List[StagedWrite],
           uow: UnitOfWork,
       ) -> LayerWriteResult:
           """Execute vector layer writes and notify P08."""
           succeeded = 0
           failed_ids = []
           p08_events = []

           for write in writes:
               if write.layer != self.LAYER:
                   continue

               try:
                   if write.operation == WriteOperation.INSERT:
                       await self._insert(uow, write)
                       p08_events.append(self._create_p08_event(write, "created"))
                   elif write.operation == WriteOperation.UPDATE:
                       await self._update(uow, write)
                       p08_events.append(self._create_p08_event(write, "updated"))
                   elif write.operation == WriteOperation.ARCHIVE:
                       await self._archive(uow, write)
                   succeeded += 1
               except Exception:
                   failed_ids.append(write.record_id)

           # Stage P08 notifications (best effort via circuit breaker)
           await self._notify_p08(uow, p08_events)

           return LayerWriteResult(
               layer=self.LAYER,
               writes_attempted=len(writes),
               writes_succeeded=succeeded,
               writes_failed=len(failed_ids),
               failed_ids=failed_ids,
           )

       async def _insert(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """INSERT new embedding."""
           data = write.record_data
           await uow.connection.execute(
               """
               INSERT INTO st_vec (
                   embedding_id, tenant_id, space_id,
                   source_type, source_id, embedding,
                   model_version, source_count, aggregation_method,
                   created_at, version
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 1)
               ON CONFLICT (embedding_id) DO NOTHING
               """,
               data["embedding_id"],
               data["tenant_id"],
               data["space_id"],
               data["source_type"],
               data["source_id"],
               data["embedding"],  # bytes
               data.get("model_version", "unknown"),
               data.get("source_count", 1),
               data.get("aggregation_method", "mean"),
               int(time.time() * 1000),
           )

       async def _update(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """UPDATE embedding with new aggregated vector."""
           data = write.record_data
           await uow.connection.execute(
               """
               UPDATE st_vec
               SET embedding = $1,
                   source_count = $2,
                   model_version = $3,
                   updated_at = $4,
                   version = version + 1
               WHERE embedding_id = $5 AND version = $6
               """,
               data["embedding"],
               data.get("source_count", 1),
               data.get("model_version", "unknown"),
               int(time.time() * 1000),
               write.record_id,
               write.expected_version,
           )

       async def _archive(self, uow: UnitOfWork, write: StagedWrite) -> None:
           """ARCHIVE stale embedding."""
           await uow.connection.execute(
               """
               UPDATE st_vec
               SET archival_status = 'ARCHIVED',
                   archived_at = $1,
                   archived_reason = $2
               WHERE embedding_id = $3
                 AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
               """,
               int(time.time() * 1000),
               write.record_data.get("archived_reason", "stale"),
               write.record_id,
           )

       def _create_p08_event(self, write: StagedWrite, event_type: str) -> OutboxEntry:
           """Create P08 notification event."""
           data = write.record_data
           topic = P08_EMBEDDING_CREATED if event_type == "created" else P08_EMBEDDING_UPDATED

           payload = {
               "embedding_id": data["embedding_id"],
               "tenant_id": data["tenant_id"],
               "space_id": data["space_id"],
               "source_type": data["source_type"],
               "source_id": data["source_id"],
               "model_version": data.get("model_version", "unknown"),
               "event_type": event_type,
               "timestamp_ms": int(time.time() * 1000),
           }

           return OutboxEntry(
               id=None,
               wal_pos=0,
               tenant_id=data["tenant_id"],
               space_id=data["space_id"],
               driver="p08",  # Target P08 pipeline
               op_kind=topic,
               payload=json.dumps(payload).encode("utf-8"),
               fingerprint=f"p08:{event_type}:{data['embedding_id']}",
               requeue_seq=0,
               retries=0,
           )

       async def _notify_p08(self, uow: UnitOfWork, events: List[OutboxEntry]) -> None:
           """Notify P08 via outbox with circuit breaker."""
           if self._is_circuit_open():
               # Circuit open - skip P08 notifications, use cached embeddings
               return

           try:
               for event in events:
                   uow.stage_outbox(event)
               self._p08_failures = 0  # Reset on success
           except Exception:
               self._p08_failures += 1
               self._last_failure_ms = int(time.time() * 1000)

       def _is_circuit_open(self) -> bool:
           """Check if circuit breaker is open."""
           if self._p08_failures < self._p08_config.failure_threshold:
               return False

           # Check if reset timeout has passed
           now_ms = int(time.time() * 1000)
           if now_ms - self._last_failure_ms > self._p08_config.reset_timeout_ms:
               self._p08_failures = 0
               return False

           return True

       @staticmethod
       def aggregate_embeddings(
           embeddings: List[bytes],
           method: str = "mean",
           weights: Optional[List[float]] = None,
       ) -> bytes:
           """
           Aggregate multiple embeddings into one.

           Args:
               embeddings: List of binary embedding vectors
               method: "mean", "weighted_mean", or "max"
               weights: Optional weights for weighted_mean

           Returns:
               Aggregated embedding as bytes
           """
           import numpy as np

           # Decode embeddings to numpy arrays
           arrays = [np.frombuffer(e, dtype=np.float32) for e in embeddings]

           if method == "mean":
               result = np.mean(arrays, axis=0)
           elif method == "weighted_mean" and weights:
               result = np.average(arrays, axis=0, weights=weights)
           elif method == "max":
               result = np.max(arrays, axis=0)
           else:
               result = np.mean(arrays, axis=0)

           return result.tobytes()
   ```

2. **P08 event contract** (`p03.embedding.created.v1.yaml`):

   ```yaml
   topic: p03.embedding.created.v1
   description: Notifies P08 embedding index of new embedding for indexing
   payload:
     embedding_id: { type: string, required: true }
     tenant_id: { type: string, required: true }
     space_id: { type: string, required: true }
     source_type: { type: string, enum: [entity, pattern, episode] }
     source_id: { type: string, required: true }
     model_version: { type: string }
     event_type: { type: string, enum: [created, updated] }
     timestamp_ms: { type: integer }
   idempotency_key: "p08:{event_type}:{embedding_id}"
   ```

**Acceptance Criteria**:

- [ ] Embeddings correctly aggregated and persisted (binary format)
- [ ] P08 notified for index updates via outbox events
- [ ] Circuit breaker prevents cascade failure on P08 outage
- [ ] aggregation_method supports mean, weighted_mean, max
- [ ] model_version tracked for embedding compatibility

**Test File**: `tests/k0/modules/consolidation/truth_writer/layers/test_vector.py`

---

#### Issue 5.2.10 — UnitOfWork integration for atomic multi-table writes

**Status**: NOT_STARTED

**Goal**: Integrate K0 UnitOfWork for atomic transactions across all memory layer writes.

**Dossier References**:

- [Appendix D.7 Storage Integration](../pipelines/P03_consolidation_dossier_v2.md#appendix-d7-storage-integration) — UoW pattern
- [Appendix D.7.1 UnitOfWork Pattern](../pipelines/P03_consolidation_dossier_v2.md#d71-unitofwork-pattern) — Transaction semantics
- [Appendix D.7.3 Optimistic Locking](../pipelines/P03_consolidation_dossier_v2.md#d73-optimistic-locking) — Version-based concurrency

**Existing Code Dependencies**:

| File | Lines | Purpose | Key Patterns |
|------|-------|---------|--------------|
| `k0/uow/unit_of_work.py:1-100` | USES | UnitOfWork class | `__aenter__`, `__aexit__`, `connection` |
| `k0/uow/unit_of_work.py:100-150` | USES | Transaction methods | `stage_outbox()`, `upsert_offset()` |
| `k0/uow/unit_of_work.py:155-180` | USES | Commit/rollback | `_commit()`, `_rollback()`, `_flush_outbox()` |
| `k0/pipelines/p03/phases/r7_truth_writer.py:95-120` | PATTERN | UoW context usage | `async with ctx.syscalls.unit_of_work() as uow:` |
| `k0/pipelines/p03/phases/r7_truth_writer.py:280-310` | PATTERN | Version conflict | `OptimisticLockError` |

**Files to Create**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/truth_writer/transaction.py` | `TransactionCoordinator` | Atomic multi-table transactions |

**Deliverables**:

1. **TransactionCoordinator class**:

   ```python
   from dataclasses import dataclass
   from typing import Dict, List, Optional
   import logging
   import time

   from k0.uow.unit_of_work import UnitOfWork
   from k0.pipelines.p03.staged_writes import P03StagedWrites, StagedWrite
   from k0.modules.consolidation.truth_writer.result import WriteResult, LayerWriteResult
   from k0.modules.consolidation.truth_writer.router import DecisionRouter, WriteMode

   logger = logging.getLogger(__name__)

   # Maximum retries for version conflicts
   MAX_VERSION_CONFLICT_RETRIES = 3

   @dataclass
   class TransactionConfig:
       """Configuration for transaction coordination."""
       mode: WriteMode = WriteMode.ATOMIC
       max_retries: int = MAX_VERSION_CONFLICT_RETRIES
       retry_delay_ms: int = 100  # Backoff between retries
       require_capabilities: bool = True

   class OptimisticLockError(Exception):
       """Raised when optimistic locking fails due to version conflict."""
       def __init__(self, layer: str, record_id: str, expected_version: int):
           self.layer = layer
           self.record_id = record_id
           self.expected_version = expected_version
           super().__init__(
               f"Version conflict for {layer}:{record_id} "
               f"(expected version {expected_version})"
           )

   class TransactionCoordinator:
       """
       Coordinates atomic writes across all memory layers via UnitOfWork.

       Responsibilities:
           1. Open UoW transaction via syscalls
           2. Execute all layer writes in dependency order
           3. Handle version conflicts with retry
           4. Validate capabilities before writes
           5. Commit atomically or rollback on failure

       Transaction Semantics:
           - All 8+ layer writes atomic within single PostgreSQL transaction
           - VERSION_CONFLICT triggers re-read and retry (max 3)
           - Capability violations raise PermissionError immediately
       """

       def __init__(
           self,
           router: DecisionRouter,
           config: Optional[TransactionConfig] = None,
       ):
           self._router = router
           self._config = config or TransactionConfig()

       async def execute(
           self,
           staged: P03StagedWrites,
           uow: UnitOfWork,
           required_caps: Optional[List[str]] = None,
       ) -> WriteResult:
           """
           Execute all staged writes atomically.

           Args:
               staged: P03StagedWrites container from R6
               uow: Active UnitOfWork (transaction already started)
               required_caps: Required capabilities for validation

           Returns:
               WriteResult with success/failure counts

           Raises:
               PermissionError: If capability validation fails
               OptimisticLockError: If max retries exceeded
           """
           # 1. Validate capabilities (if required)
           if self._config.require_capabilities and required_caps:
               await self._validate_capabilities(uow, required_caps)

           # 2. Execute writes with retry on version conflict
           attempt = 0
           last_error: Optional[OptimisticLockError] = None

           while attempt < self._config.max_retries:
               try:
                   result = await self._router.route(staged, uow)

                   logger.info(
                       "TransactionCoordinator: writes completed",
                       extra={
                           "attempt": attempt + 1,
                           "total_succeeded": result.total_succeeded,
                           "total_failed": result.total_failed,
                       },
                   )

                   return result

               except OptimisticLockError as e:
                   last_error = e
                   attempt += 1

                   if attempt < self._config.max_retries:
                       logger.warning(
                           "TransactionCoordinator: version conflict, retrying",
                           extra={
                               "layer": e.layer,
                               "record_id": e.record_id,
                               "attempt": attempt,
                               "max_retries": self._config.max_retries,
                           },
                       )
                       # Re-read and update expected version
                       await self._refresh_versions(uow, staged, e.layer)
                       await self._backoff(attempt)

           # Max retries exceeded
           raise last_error or RuntimeError("Transaction failed with unknown error")

       async def _validate_capabilities(
           self,
           uow: UnitOfWork,
           required_caps: List[str],
       ) -> None:
           """Validate that UoW has required capabilities."""
           # Capability validation via syscalls
           # For now, we assume all capabilities are granted within UoW
           # Future: integrate with K0 capability system
           pass

       async def _refresh_versions(
           self,
           uow: UnitOfWork,
           staged: P03StagedWrites,
           conflicted_layer: str,
       ) -> None:
           """Re-read versions for conflicted layer's writes."""
           layer_writes = self._get_writes_for_layer(staged, conflicted_layer)

           for write in layer_writes:
               if write.expected_version is not None:
                   # Re-read current version from database
                   pk_col = self._get_pk_column(conflicted_layer)
                   row = await uow.connection.fetchrow(
                       f"SELECT version FROM {conflicted_layer} WHERE {pk_col} = $1",
                       write.record_id,
                   )
                   if row:
                       write.expected_version = row["version"]

       def _get_writes_for_layer(
           self,
           staged: P03StagedWrites,
           layer: str,
       ) -> List[StagedWrite]:
           """Get all writes for a specific layer."""
           layer_attr_map = {
               "st_epi": "st_epi_writes",
               "st_sem": "st_sem_writes",
               "st_procedural": "st_procedural_writes",
               "st_social": "st_social_writes",
               "st_prospective": "st_prospective_writes",
               "st_kg_dom": "st_kg_dom_writes",
               "st_kg_edges": "st_kg_edges_writes",
               "st_vec": "st_vec_writes",
               "st_hipp_events": "st_hipp_events_updates",
               "st_learning_queue": "st_learning_queue_writes",
           }
           attr = layer_attr_map.get(layer)
           return getattr(staged, attr, []) if attr else []

       def _get_pk_column(self, layer: str) -> str:
           """Get primary key column for layer."""
           pk_map = {
               "st_epi": "episode_id",
               "st_sem": "pattern_id",
               "st_procedural": "routine_id",
               "st_social": "relationship_id",
               "st_prospective": "intention_id",
               "st_kg_dom": "entity_id",
               "st_kg_edges": "edge_id",
               "st_vec": "embedding_id",
               "st_hipp_events": "event_id",
               "st_learning_queue": "queue_id",
           }
           return pk_map.get(layer, "id")

       async def _backoff(self, attempt: int) -> None:
           """Exponential backoff between retries."""
           import asyncio
           delay_ms = self._config.retry_delay_ms * (2 ** (attempt - 1))
           await asyncio.sleep(delay_ms / 1000)
   ```

2. **Usage pattern in R7**:

   ```python
   # In R7TruthWriter.run():
   async with ctx.syscalls.unit_of_work() as uow:
       coordinator = TransactionCoordinator(
           router=DecisionRouter(layer_writers),
           config=TransactionConfig(mode=WriteMode.ATOMIC),
       )
       result = await coordinator.execute(
           staged=envelope.staged,
           uow=uow,
           required_caps=["storage.write", "outbox.stage"],
       )
       # Commit happens automatically on UoW __aexit__
   ```

**Acceptance Criteria**:

- [ ] All 8+ layer writes atomic within single PostgreSQL transaction
- [ ] VERSION_CONFLICT triggers re-read and retry (max 3)
- [ ] Capability violations raise PermissionError immediately
- [ ] Exponential backoff between retries
- [ ] WriteResult aggregates layer outcomes

**Test File**: `tests/k0/modules/consolidation/truth_writer/test_transaction.py`

---

#### Issue 5.2.11 — R8 bus event emission implementation

**Status**: NOT_STARTED

**Goal**: Implement R8 phase event emission for all consolidation outcome events.

**Dossier References**:

- [§4.9.1 Bus Event Emission](../pipelines/P03_consolidation_dossier_v2.md#491-bus-event-emission) — All event topics
- [Appendix G.5 R8 Metrics](../pipelines/P03_consolidation_dossier_v2.md#appendix-g5-r8-metrics) — Emission metrics

**Existing Code Dependencies**:

| File | Lines | Purpose | Key Patterns |
|------|-------|---------|--------------|
| `k0/pipelines/p03/phases/r8_event_emitter.py:67-74` | USES | Topic constants | `COMPLETION_TOPIC`, `GAP_TOPIC` |
| `k0/pipelines/p03/phases/r8_event_emitter.py:170-225` | PATTERN | Payload building | `_build_completion_payload()` |
| `k0/pipelines/p03/phases/r8_event_emitter.py:295-325` | PATTERN | Outbox staging | `_stage_completion_event()` |
| `k0/storage/outbox.py:1-50` | USES | OutboxEntry | Entry structure |
| `k0/pipelines/p03/phase_outputs.py:350-430` | USES | ReconciliationSummary | Decision counts |

**Event Topics** (per Dossier §4.9.1):

| Topic | When Emitted | Payload Summary |
|-------|--------------|-----------------|
| `p03.consolidation.complete.v1` | Every cycle end | cycle_id, status, summary, duration_ms |
| `p03.pattern.detected.v1` | New semantic pattern | pattern_id, pattern_type, confidence |
| `p03.truth.reinforced.v1` | Existing truth reinforced | truth_id, layer, observation_count |
| `p03.truth.created.v1` | New truth record | truth_id, layer, source_event_ids |
| `p03.truth.evolved.v1` | Truth evolved (new version) | old_id, new_id, layer, evolution_reason |
| `p03.memory.pruned.v1` | Memory archived/tombstoned | truth_id, layer, prune_reason |

**Files to Create**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/emission/emitter.py` | `EventEmitter` | All event emission |
| `k0/contracts/events/p03.consolidation.complete.v1.yaml` | — | Completion schema |
| `k0/contracts/events/p03.pattern.detected.v1.yaml` | — | Pattern detected schema |
| `k0/contracts/events/p03.truth.reinforced.v1.yaml` | — | Truth reinforced schema |
| `k0/contracts/events/p03.truth.created.v1.yaml` | — | Truth created schema |
| `k0/contracts/events/p03.truth.evolved.v1.yaml` | — | Truth evolved schema |
| `k0/contracts/events/p03.memory.pruned.v1.yaml` | — | Memory pruned schema |

**Deliverables**:

1. **EventEmitter class**:

   ```python
   from dataclasses import dataclass, field
   from typing import Dict, List, Any, Optional
   from enum import Enum
   import json
   import time

   from k0.storage.outbox import OutboxEntry
   from k0.uow.unit_of_work import UnitOfWork
   from k0.pipelines.p03.phase_outputs import ReconciliationSummary

   class EventTopic(Enum):
       """P03 event topics per dossier §4.9.1."""
       CONSOLIDATION_COMPLETE = "p03.consolidation.complete.v1"
       PATTERN_DETECTED = "p03.pattern.detected.v1"
       TRUTH_REINFORCED = "p03.truth.reinforced.v1"
       TRUTH_CREATED = "p03.truth.created.v1"
       TRUTH_EVOLVED = "p03.truth.evolved.v1"
       MEMORY_PRUNED = "p03.memory.pruned.v1"

   @dataclass
   class EmitResult:
       """Result of event emission."""
       total_emitted: int = 0
       by_topic: Dict[str, int] = field(default_factory=dict)
       failed: List[str] = field(default_factory=list)

   @dataclass
   class CircuitBreakerConfig:
       """Circuit breaker for bus unavailability."""
       failure_threshold: int = 5
       reset_timeout_ms: int = 60000
       queue_on_failure: bool = True

   class EventEmitter:
       """
       Emits all consolidation outcome events via outbox pattern.

       Responsibilities:
           1. Build payloads for all event types
           2. Stage events to outbox within UoW
           3. Apply idempotency keys to prevent duplicates
           4. Circuit breaker for bus unavailability

       Thread Safety:
           Not thread-safe. Use one instance per async context.
       """

       def __init__(self, circuit_config: Optional[CircuitBreakerConfig] = None):
           self._circuit_config = circuit_config or CircuitBreakerConfig()
           self._failures = 0
           self._last_failure_ms = 0

       async def emit_all(
           self,
           uow: UnitOfWork,
           envelope: "P03BatchEnvelope",
           summary: ReconciliationSummary,
       ) -> EmitResult:
           """
           Emit all events for a consolidation cycle.

           Args:
               uow: Active UnitOfWork
               envelope: Completed P03BatchEnvelope
               summary: ReconciliationSummary from R6

           Returns:
               EmitResult with counts per topic
           """
           result = EmitResult()

           # 1. Completion event (always emitted)
           await self._emit_completion(uow, envelope, summary, result)

           # 2. Decision-specific events
           await self._emit_decision_events(uow, envelope, summary, result)

           return result

       async def _emit_completion(
           self,
           uow: UnitOfWork,
           envelope: "P03BatchEnvelope",
           summary: ReconciliationSummary,
           result: EmitResult,
       ) -> None:
           """Emit p03.consolidation.complete.v1."""
           payload = {
               "cycle_id": envelope.context.cycle_id,
               "tenant_id": envelope.context.tenant_id,
               "space_id": envelope.context.space_id,
               "status": self._determine_status(envelope),
               "summary": {
                   "events_processed": summary.total_processed,
                   "decisions_by_type": {
                       "reinforce": summary.reinforce_count,
                       "extend": summary.extend_count,
                       "create": summary.create_count,
                       "evolve": summary.evolve_count,
                       "prune": summary.prune_count,
                       "skip": summary.skip_count,
                   },
                   "layers_written": summary.layers_written,
               },
               "duration_ms": envelope.observability.total_duration_ms(),
               "completed_at": self._iso_now(),
           }

           await self._stage_event(
               uow=uow,
               topic=EventTopic.CONSOLIDATION_COMPLETE,
               payload=payload,
               tenant_id=envelope.context.tenant_id,
               space_id=envelope.context.space_id,
               fingerprint=f"complete:{envelope.context.cycle_id}",
               result=result,
           )

       async def _emit_decision_events(
           self,
           uow: UnitOfWork,
           envelope: "P03BatchEnvelope",
           summary: ReconciliationSummary,
           result: EmitResult,
       ) -> None:
           """Emit per-decision events (pattern, truth, prune)."""
           cycle_id = envelope.context.cycle_id

           # Pattern detected events (for CREATE on st_sem)
           for decision in summary.decisions:
               if decision.action == "CREATE" and decision.layer == "st_sem":
                   await self._emit_pattern_detected(uow, envelope, decision, result)

               elif decision.action == "REINFORCE":
                   await self._emit_truth_reinforced(uow, envelope, decision, result)

               elif decision.action == "CREATE" and decision.layer != "st_sem":
                   await self._emit_truth_created(uow, envelope, decision, result)

               elif decision.action == "EVOLVE":
                   await self._emit_truth_evolved(uow, envelope, decision, result)

               elif decision.action == "PRUNE":
                   await self._emit_memory_pruned(uow, envelope, decision, result)

       async def _emit_pattern_detected(
           self,
           uow: UnitOfWork,
           envelope: "P03BatchEnvelope",
           decision: "DecisionRecord",
           result: EmitResult,
       ) -> None:
           """Emit p03.pattern.detected.v1."""
           payload = {
               "pattern_id": decision.record_id,
               "tenant_id": envelope.context.tenant_id,
               "space_id": envelope.context.space_id,
               "pattern_type": decision.metadata.get("pattern_type", "semantic"),
               "confidence": decision.metadata.get("confidence", 1.0),
               "source_event_ids": decision.source_event_ids,
               "detected_at": self._iso_now(),
           }

           await self._stage_event(
               uow=uow,
               topic=EventTopic.PATTERN_DETECTED,
               payload=payload,
               tenant_id=envelope.context.tenant_id,
               space_id=envelope.context.space_id,
               fingerprint=f"pattern:{decision.record_id}",
               result=result,
           )

       async def _emit_truth_reinforced(
           self,
           uow: UnitOfWork,
           envelope: "P03BatchEnvelope",
           decision: "DecisionRecord",
           result: EmitResult,
       ) -> None:
           """Emit p03.truth.reinforced.v1."""
           payload = {
               "truth_id": decision.record_id,
               "tenant_id": envelope.context.tenant_id,
               "space_id": envelope.context.space_id,
               "layer": decision.layer,
               "observation_count": decision.metadata.get("observation_count", 1),
               "reinforced_at": self._iso_now(),
           }

           await self._stage_event(
               uow=uow,
               topic=EventTopic.TRUTH_REINFORCED,
               payload=payload,
               tenant_id=envelope.context.tenant_id,
               space_id=envelope.context.space_id,
               fingerprint=f"reinforce:{decision.record_id}",
               result=result,
           )

       async def _emit_truth_created(
           self,
           uow: UnitOfWork,
           envelope: "P03BatchEnvelope",
           decision: "DecisionRecord",
           result: EmitResult,
       ) -> None:
           """Emit p03.truth.created.v1."""
           payload = {
               "truth_id": decision.record_id,
               "tenant_id": envelope.context.tenant_id,
               "space_id": envelope.context.space_id,
               "layer": decision.layer,
               "source_event_ids": decision.source_event_ids,
               "created_at": self._iso_now(),
           }

           await self._stage_event(
               uow=uow,
               topic=EventTopic.TRUTH_CREATED,
               payload=payload,
               tenant_id=envelope.context.tenant_id,
               space_id=envelope.context.space_id,
               fingerprint=f"create:{decision.record_id}",
               result=result,
           )

       async def _emit_truth_evolved(
           self,
           uow: UnitOfWork,
           envelope: "P03BatchEnvelope",
           decision: "DecisionRecord",
           result: EmitResult,
       ) -> None:
           """Emit p03.truth.evolved.v1."""
           payload = {
               "old_id": decision.metadata.get("old_id"),
               "new_id": decision.record_id,
               "tenant_id": envelope.context.tenant_id,
               "space_id": envelope.context.space_id,
               "layer": decision.layer,
               "evolution_reason": decision.metadata.get("reason", "drift"),
               "evolved_at": self._iso_now(),
           }

           await self._stage_event(
               uow=uow,
               topic=EventTopic.TRUTH_EVOLVED,
               payload=payload,
               tenant_id=envelope.context.tenant_id,
               space_id=envelope.context.space_id,
               fingerprint=f"evolve:{decision.record_id}",
               result=result,
           )

       async def _emit_memory_pruned(
           self,
           uow: UnitOfWork,
           envelope: "P03BatchEnvelope",
           decision: "DecisionRecord",
           result: EmitResult,
       ) -> None:
           """Emit p03.memory.pruned.v1."""
           payload = {
               "truth_id": decision.record_id,
               "tenant_id": envelope.context.tenant_id,
               "space_id": envelope.context.space_id,
               "layer": decision.layer,
               "prune_reason": decision.metadata.get("reason", "decay"),
               "pruned_at": self._iso_now(),
           }

           await self._stage_event(
               uow=uow,
               topic=EventTopic.MEMORY_PRUNED,
               payload=payload,
               tenant_id=envelope.context.tenant_id,
               space_id=envelope.context.space_id,
               fingerprint=f"prune:{decision.record_id}",
               result=result,
           )

       async def _stage_event(
           self,
           uow: UnitOfWork,
           topic: EventTopic,
           payload: Dict[str, Any],
           tenant_id: str,
           space_id: str,
           fingerprint: str,
           result: EmitResult,
       ) -> None:
           """Stage event to outbox with circuit breaker."""
           if self._is_circuit_open():
               result.failed.append(fingerprint)
               return

           try:
               entry = OutboxEntry(
                   id=None,
                   wal_pos=0,
                   tenant_id=tenant_id,
                   space_id=space_id,
                   driver="p03",
                   op_kind=topic.value,
                   payload=json.dumps(payload).encode("utf-8"),
                   fingerprint=fingerprint,
                   requeue_seq=0,
                   retries=0,
               )
               uow.stage_outbox(entry)

               result.total_emitted += 1
               result.by_topic[topic.value] = result.by_topic.get(topic.value, 0) + 1
               self._failures = 0

           except Exception:
               self._failures += 1
               self._last_failure_ms = int(time.time() * 1000)
               result.failed.append(fingerprint)

       def _is_circuit_open(self) -> bool:
           """Check circuit breaker state."""
           if self._failures < self._circuit_config.failure_threshold:
               return False
           now_ms = int(time.time() * 1000)
           if now_ms - self._last_failure_ms > self._circuit_config.reset_timeout_ms:
               self._failures = 0
               return False
           return True

       def _determine_status(self, envelope: "P03BatchEnvelope") -> str:
           """Determine overall cycle status."""
           from k0.pipelines.p03.runner_contract import P03PhaseStatus
           has_failure = any(
               s == P03PhaseStatus.FAIL for s in envelope.phase_statuses.values()
           )
           has_success = any(
               s == P03PhaseStatus.DONE for s in envelope.phase_statuses.values()
           )
           if has_failure and not has_success:
               return "FAILED"
           elif has_failure:
               return "PARTIAL"
           return "SUCCESS"

       @staticmethod
       def _iso_now() -> str:
           from datetime import datetime, timezone
           return datetime.now(timezone.utc).isoformat()
   ```

**Acceptance Criteria**:

- [ ] All 6 event types emitted with correct payloads
- [ ] Idempotency (fingerprint) prevents duplicate emission
- [ ] Circuit breaker queues events on bus outage
- [ ] Event contracts match dossier §4.9.1 schema
- [ ] EmitResult tracks per-topic counts

**Test File**: `tests/k0/modules/consolidation/emission/test_emitter.py`

---

#### Issue 5.2.12 — R8 gap emission for P06 Active Learning

**Status**: NOT_STARTED

**Goal**: Implement gap detection event emission for P06 Active Learning integration.

**Dossier References**:

- [§9.3.1 Gap Emission: p03.gap.detected.v1](../pipelines/P03_consolidation_dossier_v2.md#931-gap-emission) — Gap event contract
- [§7.4.8 M25 — GapDetector](../pipelines/P03_consolidation_dossier_v2.md#748-m25--gapdetector) — Gap detection module
- [§6.11 st_learning_queue Schema](../pipelines/P03_consolidation_dossier_v2.md#611-st_learning_queue) — Queue table

**Existing Code Dependencies**:

| File | Lines | Purpose | Key Patterns |
|------|-------|---------|--------------|
| `k0/pipelines/p03/gap_emitter.py:1-100` | EXTENDS | GapType enum, config | `GapType`, `P03GapEmitterConfig`, `GapEmitResult` |
| `k0/pipelines/p03/gap_emitter.py:90-100` | USES | Priority map | `GAP_PRIORITY_MAP` |
| `k0/pipelines/p03/gap_emitter.py:160-200` | PATTERN | `emit_gaps()` method | Dedup, persist, stage |
| `k0/pipelines/p03/phases/r8_event_emitter.py:330-380` | USES | `_process_gaps()` | Gap processing in R8 |
| `k0/pipelines/p03/phase_outputs.py:250-300` | USES | `GapCandidate` | Gap dataclass |

**Gap Types** (per Dossier §6.11):

| GapType | Priority | Description | P06 Strategy |
|---------|----------|-------------|--------------|
| `CONTRADICTION` | 100 | Conflicting information | Clarification question |
| `AMBIGUOUS_ENTITY` | 80 | Multiple candidates match | Disambiguation prompt |
| `STRUCTURAL_HOLE` | 70 | Missing bridge between clusters | Exploratory question |
| `CONCEPT_DRIFT` | 60 | Entity meaning shifted | Verification question |
| `LOW_CONFIDENCE_EDGE` | 50 | KG edge below threshold | Confirmation question |
| `STALE_ANCHOR` | 40 | Anchor needs refresh | Revalidation prompt |
| `MISSING_ATTRIBUTE` | 30 | Expected attribute missing | Attribute question |

**Files to Create**:

| File | Class | Purpose |
|------|-------|---------|
| `k0/modules/consolidation/emission/gap_emitter.py` | `GapEmitterModule` | Extended gap emission |
| `k0/contracts/events/p03.gap.detected.v1.yaml` | — | Gap event schema |

**Deliverables**:

1. **GapEmitterModule class** (extends existing `P03GapEmitter`):

   ```python
   from dataclasses import dataclass, field
   from typing import Dict, List, Optional, Set
   import json
   import time
   import hashlib

   from k0.pipelines.p03.gap_emitter import (
       GapType,
       P03GapEmitter,
       P03GapEmitterConfig,
       GapEmitResult,
       GAP_PRIORITY_MAP,
   )
   from k0.pipelines.p03.phase_outputs import GapCandidate
   from k0.storage.outbox import OutboxEntry
   from k0.uow.unit_of_work import UnitOfWork

   # Maximum gaps per cycle to avoid P06 overload
   MAX_GAPS_PER_CYCLE = 50

   # Default TTL for gaps (7 days)
   DEFAULT_TTL_HOURS = 168

   @dataclass
   class GapEmitterConfig:
       """Extended configuration for gap emission."""
       topic: str = "p03.gap.detected.v1"
       max_gaps_per_cycle: int = MAX_GAPS_PER_CYCLE
       ttl_hours: int = DEFAULT_TTL_HOURS
       deduplicate: bool = True
       dedup_window_ms: int = 3600000  # 1 hour
       emit_to_outbox: bool = True
       persist_to_queue: bool = True

   @dataclass
   class GapEmitStats:
       """Statistics from gap emission."""
       total_received: int = 0
       emitted: int = 0
       deduplicated: int = 0
       capped: int = 0
       by_type: Dict[str, int] = field(default_factory=dict)
       by_priority: Dict[int, int] = field(default_factory=dict)

   class GapEmitterModule:
       """
       Extended gap emitter for P06 Active Learning integration.

       Extends P03GapEmitter with:
           1. Gap cap per cycle (prevent P06 overload)
           2. Priority-based ordering (high priority first)
           3. Question template generation hints
           4. TTL configuration per gap type
           5. Metrics for gap distribution

       Usage:
           emitter = GapEmitterModule()
           stats = await emitter.emit(uow, gaps, envelope)
       """

       def __init__(self, config: Optional[GapEmitterConfig] = None):
           self._config = config or GapEmitterConfig()
           self._base_emitter = P03GapEmitter(
               P03GapEmitterConfig(
                   topic=self._config.topic,
                   deduplicate=self._config.deduplicate,
                   dedup_window_ms=self._config.dedup_window_ms,
               )
           )
           self._seen_this_cycle: Set[str] = set()

       async def emit(
           self,
           uow: UnitOfWork,
           gaps: List[GapCandidate],
           envelope: "P03BatchEnvelope",
       ) -> GapEmitStats:
           """
           Emit gaps with deduplication, capping, and priority ordering.

           Args:
               uow: Active UnitOfWork
               gaps: List of GapCandidate from R4
               envelope: P03BatchEnvelope for context

           Returns:
               GapEmitStats with emission statistics
           """
           stats = GapEmitStats(total_received=len(gaps))

           if not gaps:
               return stats

           # 1. Sort by priority (highest first)
           sorted_gaps = self._sort_by_priority(gaps)

           # 2. Deduplicate within cycle
           unique_gaps = self._deduplicate(sorted_gaps, stats)

           # 3. Cap to max per cycle
           capped_gaps = unique_gaps[: self._config.max_gaps_per_cycle]
           stats.capped = len(unique_gaps) - len(capped_gaps)

           # 4. Emit each gap
           for gap in capped_gaps:
               await self._emit_gap(uow, gap, envelope, stats)

           return stats

       def _sort_by_priority(self, gaps: List[GapCandidate]) -> List[GapCandidate]:
           """Sort gaps by priority (highest first)."""
           def get_priority(gap: GapCandidate) -> int:
               gap_type = GapType.from_string(gap.gap_type)
               return GAP_PRIORITY_MAP.get(gap_type, 50)

           return sorted(gaps, key=get_priority, reverse=True)

       def _deduplicate(
           self,
           gaps: List[GapCandidate],
           stats: GapEmitStats,
       ) -> List[GapCandidate]:
           """Deduplicate gaps within cycle."""
           unique = []

           for gap in gaps:
               dedup_key = self._make_dedup_key(gap)

               if dedup_key in self._seen_this_cycle:
                   stats.deduplicated += 1
                   continue

               self._seen_this_cycle.add(dedup_key)
               unique.append(gap)

           return unique

       def _make_dedup_key(self, gap: GapCandidate) -> str:
           """Create deduplication key for gap."""
           # Dedup by gap_type + related_entity_id
           key_str = f"{gap.gap_type}:{gap.related_entity_id or 'none'}"
           return hashlib.md5(key_str.encode()).hexdigest()

       async def _emit_gap(
           self,
           uow: UnitOfWork,
           gap: GapCandidate,
           envelope: "P03BatchEnvelope",
           stats: GapEmitStats,
       ) -> None:
           """Emit single gap to queue and outbox."""
           gap_type = GapType.from_string(gap.gap_type)
           priority = GAP_PRIORITY_MAP.get(gap_type, 50)

           # Track stats
           stats.emitted += 1
           stats.by_type[gap.gap_type] = stats.by_type.get(gap.gap_type, 0) + 1
           stats.by_priority[priority] = stats.by_priority.get(priority, 0) + 1

           # 1. Persist to st_learning_queue
           if self._config.persist_to_queue:
               await self._persist_to_queue(uow, gap, envelope, priority)

           # 2. Stage outbox event for immediate notification
           if self._config.emit_to_outbox:
               await self._stage_outbox_event(uow, gap, envelope, priority)

       async def _persist_to_queue(
           self,
           uow: UnitOfWork,
           gap: GapCandidate,
           envelope: "P03BatchEnvelope",
           priority: int,
       ) -> None:
           """Insert gap into st_learning_queue for P06 consumption."""
           now_ms = int(time.time() * 1000)
           expires_ms = now_ms + (self._config.ttl_hours * 3600 * 1000)

           metadata = {
               "related_entity_id": gap.related_entity_id,
               "entropy_score": gap.entropy_score,
               "source_event_ids": gap.source_event_ids,
               "context": gap.context,
               "question_template": self._get_question_template(gap),
           }

           await uow.connection.execute(
               """
               INSERT INTO st_learning_queue (
                   queue_id, tenant_id, space_id, gap_type, gap_id,
                   source_event_id, priority, gap_metadata, status,
                   created_at, expires_at, attempts, max_attempts
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
               ON CONFLICT (gap_id) DO NOTHING
               """,
               gap.gap_id,  # Use gap_id as queue_id
               envelope.context.tenant_id,
               envelope.context.space_id,
               gap.gap_type,
               gap.gap_id,
               gap.source_event_ids[0] if gap.source_event_ids else None,
               priority,
               json.dumps(metadata),
               "PENDING",
               now_ms,
               expires_ms,
               0,  # attempts
               3,  # max_attempts
           )

       async def _stage_outbox_event(
           self,
           uow: UnitOfWork,
           gap: GapCandidate,
           envelope: "P03BatchEnvelope",
           priority: int,
       ) -> None:
           """Stage gap event to outbox."""
           payload = {
               "gap_id": gap.gap_id,
               "tenant_id": envelope.context.tenant_id,
               "space_id": envelope.context.space_id,
               "gap_type": gap.gap_type,
               "importance_score": gap.entropy_score,
               "priority": priority,
               "context": {
                   "related_entity_id": gap.related_entity_id,
                   "source_event_ids": gap.source_event_ids,
                   "conflicting_truths": gap.context.get("conflicting_truths", []),
                   "question_template": self._get_question_template(gap),
               },
               "ttl_hours": self._config.ttl_hours,
               "detected_at": int(time.time() * 1000),
           }

           entry = OutboxEntry(
               id=None,
               wal_pos=0,
               tenant_id=envelope.context.tenant_id,
               space_id=envelope.context.space_id,
               driver="p06",  # Target P06 pipeline
               op_kind=self._config.topic,
               payload=json.dumps(payload).encode("utf-8"),
               fingerprint=f"gap:{gap.gap_id}",
               requeue_seq=0,
               retries=0,
           )
           uow.stage_outbox(entry)

       def _get_question_template(self, gap: GapCandidate) -> str:
           """Get question template based on gap type."""
           templates = {
               "AMBIGUOUS_ENTITY": "Which of these best matches '{entity}'?",
               "LOW_CONFIDENCE_EDGE": "Is it true that '{source}' {relation} '{target}'?",
               "MISSING_ATTRIBUTE": "What is the {attribute} of '{entity}'?",
               "CONTRADICTION": "Which statement is correct: A) {claim_a} or B) {claim_b}?",
               "CONCEPT_DRIFT": "Has the meaning of '{entity}' changed recently?",
               "STRUCTURAL_HOLE": "How are '{entity_a}' and '{entity_b}' related?",
               "STALE_ANCHOR": "Is '{entity}' still valid/current?",
           }
           return templates.get(gap.gap_type, "Can you clarify this?")

       def reset_cycle(self) -> None:
           """Reset per-cycle state. Call at start of each consolidation cycle."""
           self._seen_this_cycle.clear()
   ```

2. **Gap event contract** (`p03.gap.detected.v1.yaml`):

   ```yaml
   topic: p03.gap.detected.v1
   version: "1.0"
   description: Gap detected during consolidation, sent to P06 for active learning

   payload:
     gap_id:
       type: string
       required: true
       description: Unique gap identifier (ULID)
     tenant_id:
       type: string
       required: true
     space_id:
       type: string
       required: true
     gap_type:
       type: string
       enum:
         - AMBIGUOUS_ENTITY
         - LOW_CONFIDENCE_EDGE
         - MISSING_ATTRIBUTE
         - CONTRADICTION
         - CONCEPT_DRIFT
         - STRUCTURAL_HOLE
         - STALE_ANCHOR
       required: true
     importance_score:
       type: number
       description: Entropy-based importance (0.0-1.0)
     priority:
       type: integer
       description: Priority score (higher = more urgent)
     context:
       type: object
       properties:
         related_entity_id: { type: string }
         source_event_ids: { type: array, items: { type: string } }
         conflicting_truths: { type: array, items: { type: string } }
         question_template: { type: string }
     ttl_hours:
       type: integer
       default: 168
       description: Time-to-live before gap expires
     detected_at:
       type: integer
       description: Timestamp in milliseconds

   idempotency_key: "gap:{gap_id}"
   target_pipeline: P06
   ```

**Acceptance Criteria**:

- [ ] All 7 gap types correctly emitted with full context
- [ ] Gaps deduplicated within cycle (same gap_type + entity)
- [ ] Cap enforced at max_gaps_per_cycle (default 50)
- [ ] Priority ordering ensures high-priority gaps emitted first
- [ ] Question templates provided for P06 prompt generation
- [ ] Persisted to st_learning_queue AND staged to outbox

**Test File**: `tests/k0/modules/consolidation/emission/test_gap_emitter.py`

**CRITICAL GAP ANALYSIS** — The issues above create NEW modules in `k0/modules/consolidation/`. But R7/R8 phases ALREADY EXIST in `k0/pipelines/p03/phases/`:

- `r7_truth_writer.py` (604 lines) — Created in M3
- `r8_event_emitter.py` (564 lines) — Created in M3

The wiring issues below integrate the new modules (5.2.1-5.2.12) into the existing phase infrastructure.

---

#### Issue 5.2.W1 — Extend existing R7 phase to use new layer writers

**Status**: NOT_STARTED

**Goal**: Wire `r7_truth_writer.py` to delegate writes to per-layer writers (Issues 5.2.3-5.2.9) instead of inline SQL.

**Dossier References**:

- [Appendix G.7 R7 Specification](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R7 phase spec
- [§4.8 R7 — Memory Layer Writes](../pipelines/P03_consolidation_dossier_v2.md#48-r7--memory-layer-writes) — Write ordering

**Files to Modify**:

| File | Lines | Current Logic | New Logic |
|------|-------|---------------|-----------|
| `k0/pipelines/p03/phases/r7_truth_writer.py:185-220` | `_execute_staged_writes()` | Inline `_execute_single_write()` with raw SQL | Delegate to `DecisionRouter.route()` |
| `k0/pipelines/p03/phases/r7_truth_writer.py:230-335` | `_execute_insert/update/archive/tombstone()` | Keep as FALLBACK | Mark as `@deprecated`, add migration comment |

**Existing Code Dependencies**:

| File | Lines | Purpose | How Used |
|------|-------|---------|----------|
| `k0/pipelines/p03/phases/r7_truth_writer.py:185-220` | MODIFY | `_execute_staged_writes()` | Replace loop with router call |
| `k0/modules/consolidation/truth_writer/router.py` | USE | DecisionRouter (Issue 5.2.1) | Import and instantiate |
| `k0/modules/consolidation/truth_writer/transaction.py` | USE | TransactionCoordinator (Issue 5.2.10) | Wrap writes in atomic transaction |

**Deliverables**:

1. **Replace inline SQL with router delegation**:

   ```python
   # In r7_truth_writer.py - BEFORE (current M3 code):
   async def _execute_staged_writes(
       self,
       uow: UnitOfWork,
       writes: List[StagedWrite],
       ctx: P03RunnerContext,
   ) -> Dict[str, int]:
       counts: Dict[str, int] = {}
       for write in writes:
           await self._execute_single_write(uow.connection, write)
           counts[write.layer] = counts.get(write.layer, 0) + 1
       return counts

   # In r7_truth_writer.py - AFTER (M5 wiring):
   from k0.modules.consolidation.truth_writer.router import DecisionRouter
   from k0.modules.consolidation.truth_writer.transaction import TransactionCoordinator

   async def _execute_staged_writes(
       self,
       uow: UnitOfWork,
       staged: P03StagedWrites,  # Changed from List[StagedWrite]
       ctx: P03RunnerContext,
   ) -> WriteResult:
       """
       Execute all staged writes via DecisionRouter with atomic transaction.

       M5 Wiring: Replaces M3 inline SQL with per-layer writer modules.
       """
       # Initialize router with layer writers (from DI container or direct)
       router = self._get_or_create_router(ctx)

       # Use TransactionCoordinator for atomic multi-table writes
       coordinator = TransactionCoordinator(router=router)

       # Execute all writes atomically
       result = await coordinator.execute(
           staged=staged,
           uow=uow,
           required_caps=["storage.write", "outbox.stage"],
       )

       # Log write distribution
       logger.info(
           "R7: Staged writes executed via router",
           extra={
               "total_succeeded": result.total_succeeded,
               "total_failed": result.total_failed,
               "by_layer": {k: v.writes_succeeded for k, v in result.by_layer.items()},
           },
       )

       return result

   def _get_or_create_router(self, ctx: P03RunnerContext) -> DecisionRouter:
       """Get cached router or create new one with layer writers."""
       if not hasattr(self, "_router"):
           from k0.modules.consolidation.truth_writer.layers.episodic import EpisodicLayerWriter
           from k0.modules.consolidation.truth_writer.layers.semantic import SemanticLayerWriter
           from k0.modules.consolidation.truth_writer.layers.procedural import ProceduralLayerWriter
           from k0.modules.consolidation.truth_writer.layers.social import SocialLayerWriter
           from k0.modules.consolidation.truth_writer.layers.prospective import ProspectiveLayerWriter
           from k0.modules.consolidation.truth_writer.layers.kg import KGLayerWriter
           from k0.modules.consolidation.truth_writer.layers.vector import VectorLayerWriter

           self._router = DecisionRouter(
               layer_writers={
                   "st_epi": EpisodicLayerWriter(),
                   "st_sem": SemanticLayerWriter(),
                   "st_procedural": ProceduralLayerWriter(),
                   "st_social": SocialLayerWriter(),
                   "st_prospective": ProspectiveLayerWriter(),
                   "st_kg_dom": KGLayerWriter(),
                   "st_kg_edges": KGLayerWriter(),
                   "st_vec": VectorLayerWriter(),
               }
           )
       return self._router
   ```

2. **Keep legacy methods with deprecation warning**:

   ```python
   # Mark as deprecated but keep for backward compatibility
   import warnings

   async def _execute_single_write(
       self,
       conn: asyncpg.Connection,
       write: StagedWrite,
   ) -> None:
       """
       DEPRECATED: Use DecisionRouter.route() instead.

       Legacy method kept for backward compatibility with M3 code paths.
       Will be removed in M6.
       """
       warnings.warn(
           "_execute_single_write is deprecated, use DecisionRouter",
           DeprecationWarning,
           stacklevel=2,
       )
       # ... existing implementation unchanged ...
   ```

**Acceptance Criteria**:

- [ ] `_execute_staged_writes()` delegates to `DecisionRouter.route()`
- [ ] All 8 layer writers wired (st_epi, st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges, st_vec)
- [ ] `TransactionCoordinator` provides atomic transaction
- [ ] Legacy `_execute_single_write()` marked deprecated with warning
- [ ] Existing tests pass with new routing path
- [ ] R7 returns `WriteResult` instead of `Dict[str, int]`

**Test File**: `tests/k0/pipelines/p03/phases/test_r7_wiring.py`

---

#### Issue 5.2.W2 — Extend existing R8 phase to use new emitters

**Status**: NOT_STARTED

**Goal**: Wire `r8_event_emitter.py` to use `EventEmitter` (5.2.11), `GapEmitterModule` (5.2.12) instead of inline methods.

**Dossier References**:

- [§4.9.1 Bus Event Emission](../pipelines/P03_consolidation_dossier_v2.md#491-bus-event-emission) — Event topics
- [§5.2 Gap Detection During Reconciliation](../pipelines/P03_consolidation_dossier_v2.md#52-gap-detection-during-reconciliation) — Gap flow
- [Appendix G R8 Specification](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R8 phase spec

**Files to Modify**:

| File | Lines | Current Logic | New Logic |
|------|-------|---------------|-----------|
| `k0/pipelines/p03/phases/r8_event_emitter.py:77-135` | `run()` | Calls inline `_build_completion_payload()`, `_stage_completion_event()`, `_process_gaps()` | Delegate to `EventEmitter.emit_all()`, `GapEmitterModule.emit()` |
| `k0/pipelines/p03/phases/r8_event_emitter.py:175-260` | Inline payload builders | Keep as FALLBACK | Mark deprecated |
| `k0/pipelines/p03/phases/r8_event_emitter.py:310-380` | `_process_gaps()` | Uses `P03GapEmitter` directly | Delegate to `GapEmitterModule` with max cap |

**Existing Code Dependencies**:

| File | Lines | Purpose | How Used |
|------|-------|---------|----------|
| `k0/pipelines/p03/phases/r8_event_emitter.py:77-135` | MODIFY | `run()` method | Add emitter delegation |
| `k0/pipelines/p03/gap_emitter.py:1-200` | USES | P03GapEmitter base | GapEmitterModule extends this |
| `k0/modules/consolidation/emission/emitter.py` | USE | EventEmitter (Issue 5.2.11) | Import and delegate |
| `k0/modules/consolidation/emission/gap_emitter.py` | USE | GapEmitterModule (Issue 5.2.12) | Import and delegate |

**Deliverables**:

1. **Replace inline methods with emitter delegation**:

   ```python
   # In r8_event_emitter.py - AFTER (M5 wiring):
   from k0.modules.consolidation.emission.emitter import EventEmitter, CircuitBreakerConfig
   from k0.modules.consolidation.emission.gap_emitter import GapEmitterModule, GapEmitterConfig

   class R8EventEmitter:
       """R8 Phase: Event Emission & Completion (M5 wiring)."""

       PHASE_ID = P03PhaseId.R8_EMIT
       COMPLETION_TOPIC = "p03.consolidation.complete.v1"
       GAP_TOPIC = "p03.gap.detected.v1"

       def __init__(self):
           # M5: Initialize emitters
           self._event_emitter = EventEmitter(
               circuit_config=CircuitBreakerConfig(
                   failure_threshold=5,
                   reset_timeout_ms=60000,
               )
           )
           self._gap_emitter = GapEmitterModule(
               config=GapEmitterConfig(
                   max_gaps_per_cycle=50,
                   ttl_hours=168,  # 7 days
               )
           )

       async def run(
           self,
           envelope: P03BatchEnvelope,
           ctx: P03RunnerContext,
       ) -> P03PhaseResult:
           start_ms = int(time.time() * 1000)
           cycle_id = envelope.context.cycle_id

           logger.info(
               "R8: Starting event emission phase (M5 wiring)",
               extra={"cycle_id": cycle_id},
           )

           try:
               async with ctx.syscalls.unit_of_work() as uow:
                   # M5: Use EventEmitter for all consolidation events
                   emit_result = await self._event_emitter.emit_all(
                       uow=uow,
                       envelope=envelope,
                       summary=envelope.phases.r6_summary,
                   )

                   # M5: Use GapEmitterModule for P06 gaps
                   gap_stats = await self._gap_emitter.emit(
                       uow=uow,
                       gaps=envelope.phases.r4_gap_candidates,
                       envelope=envelope,
                   )

                   # Commit offset
                   await self._commit_offset(uow, envelope)

               # Trigger outbox drain
               await self._trigger_outbox_drain(ctx)

               duration_ms = int(time.time() * 1000) - start_ms

               logger.info(
                   "R8: Event emission completed (M5 wiring)",
                   extra={
                       "cycle_id": cycle_id,
                       "events_emitted": emit_result.total_emitted,
                       "gaps_emitted": gap_stats.emitted,
                       "gaps_deduplicated": gap_stats.deduplicated,
                       "gaps_capped": gap_stats.capped,
                   },
               )

               return P03PhaseResult.done(
                   phase_id=self.PHASE_ID,
                   duration_ms=duration_ms,
                   outputs_summary={
                       "events_emitted": emit_result.total_emitted,
                       "events_by_topic": emit_result.by_topic,
                       "gaps_emitted": gap_stats.emitted,
                       "gaps_by_type": gap_stats.by_type,
                   },
                   idempotency_key=f"p03:r8:{cycle_id}",
               )

           except Exception as e:
               # ... error handling unchanged ...
   ```

2. **Reset gap emitter state per cycle**:

   ```python
   # Add at start of run():
   self._gap_emitter.reset_cycle()  # Clear per-cycle dedup state
   ```

**Acceptance Criteria**:

- [ ] `EventEmitter.emit_all()` replaces inline payload builders
- [ ] `GapEmitterModule.emit()` replaces `_process_gaps()`
- [ ] All 6 event topics (complete, pattern, truth.*, prune) emitted via EventEmitter
- [ ] All 7 gap types emitted via GapEmitterModule with max cap (50)
- [ ] Gap deduplication works within cycle
- [ ] Circuit breaker handles bus unavailability
- [ ] Existing R8 tests pass with new emitters

**Test File**: `tests/k0/pipelines/p03/phases/test_r8_wiring.py`

---

#### Issue 5.2.W3 — R7 receives R6Output instead of P03StagedWrites

**Status**: NOT_STARTED

**Goal**: Update R7 phase signature to consume `R6Output` dataclass (Issue 5.1.8) with validated manifest instead of raw `P03StagedWrites`.

**Dossier References**:

- [Appendix G.6 R6 Specification](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R6 outputs
- [Appendix G.7 R7 Specification](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R7 inputs

**Files to Modify**:

| File | Lines | Current Logic | New Logic |
|------|-------|---------------|-----------|
| `k0/pipelines/p03/phases/r7_truth_writer.py:90-110` | `run()` signature | Reads `envelope.staged` directly | Reads `envelope.phases.r6_output` |
| `k0/pipelines/p03/envelope.py` | P03PhaseOutputs | Has `r6_summary` | Add `r6_output: R6Output` field |

**Existing Code Dependencies**:

| File | Lines | Purpose | How Used |
|------|-------|---------|----------|
| `k0/pipelines/p03/phases/r7_truth_writer.py:90-110` | MODIFY | `run()` method | Change input source |
| `k0/pipelines/p03/envelope.py:150-200` | MODIFY | P03PhaseOutputs | Add r6_output field |
| `k0/modules/consolidation/staging/r6_output.py` | USE | R6Output dataclass (Issue 5.1.8) | Import and consume |

**Deliverables**:

1. **Add R6Output to P03PhaseOutputs**:

   ```python
   # In k0/pipelines/p03/envelope.py (P03PhaseOutputs):
   from k0.modules.consolidation.staging.r6_output import R6Output

   @dataclass
   class P03PhaseOutputs:
       """Phase outputs container."""
       # ... existing fields ...

       # M5: Add R6 structured output
       r6_output: Optional[R6Output] = None  # From Issue 5.1.8
       r6_summary: Optional[ReconciliationSummary] = None  # Keep for backward compat
   ```

2. **Update R7 to consume R6Output**:

   ```python
   # In r7_truth_writer.py:
   async def run(
       self,
       envelope: P03BatchEnvelope,
       ctx: P03RunnerContext,
   ) -> P03PhaseResult:
       start_ms = int(time.time() * 1000)
       cycle_id = envelope.context.cycle_id

       # M5: Get R6Output with validated manifest
       r6_output = envelope.phases.r6_output
       if r6_output is None:
           # Fallback to legacy P03StagedWrites for backward compatibility
           logger.warning("R7: R6Output missing, using legacy P03StagedWrites")
           staged = envelope.staged
       else:
           # Use validated manifest from R6
           if not r6_output.manifest.all_validated:
               return P03PhaseResult.fail(
                   phase_id=self.PHASE_ID,
                   error=P03Error(
                       error_id=f"r7-{cycle_id}",
                       phase="R7",
                       stage_id="manifest_check",
                       error_type="R6_MANIFEST_INVALID",
                       error_message="R6 manifest not fully validated",
                       recoverable=False,
                   ),
                   duration_ms=0,
                   idempotency_key=f"p03:r7:{cycle_id}",
               )
           staged = r6_output.staged

       logger.info(
           "R7: Starting truth write phase",
           extra={
               "cycle_id": cycle_id,
               "total_writes": staged.total_writes(),
               "manifest_validated": r6_output.manifest.all_validated if r6_output else "N/A",
           },
       )

       # ... rest of implementation uses staged ...
   ```

3. **R6 coordinator stores output**:

   ```python
   # In R6 coordinator (Issue 5.1.11) - store output:
   envelope.phases.r6_output = R6Output(
       staged=staged_writes,
       summary=summary,
       manifest=manifest,
   )
   ```

**Acceptance Criteria**:

- [ ] `P03PhaseOutputs` has `r6_output: R6Output` field
- [ ] R7 reads from `envelope.phases.r6_output` when available
- [ ] R7 validates manifest before proceeding
- [ ] Fallback to `envelope.staged` for backward compatibility
- [ ] R6 coordinator populates `r6_output`
- [ ] Type hints updated throughout

**Test File**: `tests/k0/pipelines/p03/phases/test_r7_r6_integration.py`

---

#### Issue 5.2.W4 — R8 receives R7 write results

**Status**: NOT_STARTED

**Goal**: Wire R8 to receive `WriteResult` from R7 for accurate metrics aggregation in completion payload.

**Dossier References**:

- [Appendix G.7 R7 Specification](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R7 outputs
- [Appendix G.8 R8 Specification](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r0-r8-state-machine-specification) — R8 inputs
- [Appendix G.5 Metrics Per Phase](../pipelines/P03_consolidation_dossier_v2.md#g5-metrics-per-phase) — R7/R8 metrics

**Files to Modify**:

| File | Lines | Current Logic | New Logic |
|------|-------|---------------|-----------|
| `k0/pipelines/p03/envelope.py` | P03PhaseOutputs | No R7 output field | Add `r7_result: WriteResult` |
| `k0/pipelines/p03/phases/r7_truth_writer.py:130-150` | After writes | Returns counts dict | Store `WriteResult` in envelope |
| `k0/pipelines/p03/phases/r8_event_emitter.py:250-280` | `_build_summary()` | Hardcoded summary | Use `envelope.phases.r7_result` |

**Existing Code Dependencies**:

| File | Lines | Purpose | How Used |
|------|-------|---------|----------|
| `k0/pipelines/p03/envelope.py:150-200` | MODIFY | P03PhaseOutputs | Add r7_result field |
| `k0/modules/consolidation/truth_writer/result.py` | USE | WriteResult (Issue 5.2.1) | Import for type |
| `k0/pipelines/p03/phases/r8_event_emitter.py:250-280` | MODIFY | `_build_summary()` | Use R7 results |

**Deliverables**:

1. **Add WriteResult to P03PhaseOutputs**:

   ```python
   # In k0/pipelines/p03/envelope.py:
   from k0.modules.consolidation.truth_writer.result import WriteResult

   @dataclass
   class P03PhaseOutputs:
       # ... existing fields ...

       # M5: Add R7 write result
       r7_result: Optional[WriteResult] = None
   ```

2. **R7 stores WriteResult in envelope**:

   ```python
   # In r7_truth_writer.py after writes:
   result = await self._execute_staged_writes(uow, staged, ctx)

   # M5: Store result for R8 consumption
   envelope.phases.r7_result = result

   return P03PhaseResult.done(
       phase_id=self.PHASE_ID,
       duration_ms=duration_ms,
       outputs_summary={
           "writes_executed": result.total_succeeded,
           "writes_failed": result.total_failed,
           "writes_by_layer": {k: v.writes_succeeded for k, v in result.by_layer.items()},
       },
       # ...
   )
   ```

3. **R8 uses WriteResult for metrics**:

   ```python
   # In r8_event_emitter.py (_build_summary):
   def _build_summary(self, envelope: P03BatchEnvelope) -> Dict[str, Any]:
       """Build summary section using R7 WriteResult."""
       outputs = envelope.phases

       # M5: Include R7 write results
       r7_stats = {}
       if outputs.r7_result:
           r7_stats = {
               "writes_succeeded": outputs.r7_result.total_succeeded,
               "writes_failed": outputs.r7_result.total_failed,
               "layers_touched": list(outputs.r7_result.by_layer.keys()),
               "failed_decision_ids": outputs.r7_result.failed_decision_ids,
           }

       return {
           "events_processed": len(envelope.events),
           "clusters_created": outputs.r2_cluster_count,
           "duplicates_found": len(outputs.r3_dedup_merges),
           "entities_created": len(outputs.r4_new_entities),
           "edges_created": len(outputs.r4_new_edges),
           "gaps_detected": len(outputs.r4_gap_candidates),
           "patterns_updated": len(outputs.r4_updated_entities),
           "salience_changes": outputs.r6_summary.total_processed if outputs.r6_summary else 0,
           # M5: Add R7 write stats
           "truth_writes": r7_stats,
       }
   ```

**Acceptance Criteria**:

- [ ] `P03PhaseOutputs` has `r7_result: WriteResult` field
- [ ] R7 stores `WriteResult` in `envelope.phases.r7_result`
- [ ] R8 `_build_summary()` includes R7 write statistics
- [ ] Completion payload contains accurate write counts
- [ ] Failed decision IDs propagated to completion event
- [ ] Metrics `p03_r7_writes`, `p03_r7_failures` accurate

**Test File**: `tests/k0/pipelines/p03/phases/test_r8_r7_integration.py`

---

#### Issue 5.2.W5 — Full pipeline integration test (R0→R8)

**Status**: NOT_STARTED

**Goal**: Create end-to-end integration test exercising all phases with real implementations (not mocks).

**Dossier References**:

- [Appendix G.1 State Machine Overview](../pipelines/P03_consolidation_dossier_v2.md#g1-state-machine-overview) — Phase flow
- [Appendix G.3 State Transition Rules](../pipelines/P03_consolidation_dossier_v2.md#g3-state-transition-rules) — Valid transitions

**Existing Code Dependencies**:

| File | Lines | Purpose | How Used |
|------|-------|---------|----------|
| `k0/pipelines/p03/sequential_runner.py` | USE | P03SequentialRunner | Run full pipeline |
| `k0/pipelines/p03/phases/r0_init.py` | USE | R0InitPhase | Real phase |
| `k0/pipelines/p03/phases/r1_score.py` | USE | R1ScorePhase | Real phase |
| `k0/pipelines/p03/phases/r2_cluster.py` | USE | R2ClusterPhase | Real phase |
| `k0/pipelines/p03/phases/r3_forget.py` | USE | R3ForgetPhase | Real phase |
| `k0/pipelines/p03/phases/r4_kg.py` | USE | R4KGPhase | Real phase |
| `k0/pipelines/p03/phases/r5_dream.py` | USE | R5DreamPhase | Real phase |
| `k0/pipelines/p03/phases/r6_stage.py` | USE | R6StagePhase | Real phase (Issue 5.1.11) |
| `k0/pipelines/p03/phases/r7_truth_writer.py` | USE | R7TruthWriter | Real phase (M3 + 5.2.W1) |
| `k0/pipelines/p03/phases/r8_event_emitter.py` | USE | R8EventEmitter | Real phase (M3 + 5.2.W2) |

**Files to Create**:

| File | Purpose |
|------|---------|
| `tests/k0/pipelines/p03/integration/test_full_pipeline.py` | Full R0→R8 integration test |
| `tests/k0/pipelines/p03/integration/fixtures.py` | Test fixtures and data generators |

**Deliverables**:

1. **Full pipeline integration test**:

   ```python
   """
   Full P03 Pipeline Integration Test (R0→R8).

   M5 Issue 5.2.W5: End-to-end test with real phases, real database.

   Test Scenarios:
   1. Happy path: 10 events → cluster → KG → write → emit
   2. Deduplication: 5 duplicate events → merged
   3. Gap detection: Ambiguous entity → gap emitted
   4. Error recovery: R7 version conflict → retry
   5. Skip path: R5 backlogged → skipped
   """
   import pytest
   from ward import test

   from k0.pipelines.p03.sequential_runner import P03SequentialRunner
   from k0.pipelines.p03.runner_contract import P03PhaseId, P03PhaseStatus
   from k0.pipelines.p03.envelope import P03BatchEnvelope
   from k0.pipelines.p03.phase_interface import P03RunnerContext

   # Import all real phases
   from k0.pipelines.p03.phases.r0_init import R0InitPhase
   from k0.pipelines.p03.phases.r1_score import R1ScorePhase
   from k0.pipelines.p03.phases.r2_cluster import R2ClusterPhase
   from k0.pipelines.p03.phases.r3_forget import R3ForgetPhase
   from k0.pipelines.p03.phases.r4_kg import R4KGPhase
   from k0.pipelines.p03.phases.r5_dream import R5DreamPhase
   from k0.pipelines.p03.phases.r6_stage import R6StagePhase
   from k0.pipelines.p03.phases.r7_truth_writer import R7TruthWriter
   from k0.pipelines.p03.phases.r8_event_emitter import R8EventEmitter

   from .fixtures import (
       create_test_events,
       create_test_database,
       create_runner_context,
   )


   def build_full_pipeline() -> P03SequentialRunner:
       """Build runner with all real phases."""
       return P03SequentialRunner(
           phases={
               P03PhaseId.R0_INIT: R0InitPhase(),
               P03PhaseId.R1_SCORE: R1ScorePhase(),
               P03PhaseId.R2_CLUSTER: R2ClusterPhase(),
               P03PhaseId.R3_FORGET: R3ForgetPhase(),
               P03PhaseId.R4_KG: R4KGPhase(),
               P03PhaseId.R5_DREAM: R5DreamPhase(),
               P03PhaseId.R6_STAGE: R6StagePhase(),
               P03PhaseId.R7_WRITE: R7TruthWriter(),
               P03PhaseId.R8_EMIT: R8EventEmitter(),
           }
       )


   @test("full pipeline happy path: 10 events processed end-to-end")
   async def test_full_pipeline_happy_path():
       """Test complete R0→R8 flow with real data."""
       # Arrange
       async with create_test_database() as db:
           events = await create_test_events(db, count=10)
           ctx = await create_runner_context(db)
           runner = build_full_pipeline()

           # Act
           envelope = P03BatchEnvelope.create(
               events=events,
               tenant_id="test-tenant",
               space_id="test-space",
           )
           result = await runner.run(envelope, ctx)

           # Assert
           assert result.status == P03PhaseStatus.DONE
           assert result.phases_completed == 9  # R0-R8

           # Verify database state
           episodes = await db.fetch("SELECT * FROM st_epi WHERE tenant_id = $1", "test-tenant")
           assert len(episodes) >= 1  # At least one episode created

           # Verify outbox has completion event
           outbox = await db.fetch("SELECT * FROM st_outbox WHERE driver = 'p03'")
           assert any(e["op_kind"] == "p03.consolidation.complete.v1" for e in outbox)

           # Verify events marked as consolidated
           updated = await db.fetch(
               "SELECT consolidation_status FROM st_hipp_events WHERE event_id = ANY($1)",
               [e.event_id for e in events],
           )
           assert all(r["consolidation_status"] == "CONSOLIDATED" for r in updated)


   @test("full pipeline gap detection: ambiguous entity emits gap")
   async def test_full_pipeline_gap_detection():
       """Test that ambiguous entities trigger gap emission."""
       async with create_test_database() as db:
           # Create events with ambiguous entity reference
           events = await create_test_events(
               db,
               count=3,
               entity_name="Sarah",  # Ambiguous - multiple candidates
           )
           ctx = await create_runner_context(db)
           runner = build_full_pipeline()

           envelope = P03BatchEnvelope.create(events=events, tenant_id="test", space_id="test")
           result = await runner.run(envelope, ctx)

           # Verify gap was emitted
           assert result.status == P03PhaseStatus.DONE
           gaps = await db.fetch("SELECT * FROM st_learning_queue WHERE tenant_id = $1", "test")
           assert len(gaps) >= 1
           assert gaps[0]["gap_type"] == "AMBIGUOUS_ENTITY"


   @test("full pipeline error recovery: R7 version conflict retries")
   async def test_full_pipeline_version_conflict_recovery():
       """Test R7 handles version conflicts with retry."""
       async with create_test_database() as db:
           events = await create_test_events(db, count=5)
           ctx = await create_runner_context(db)
           runner = build_full_pipeline()

           # Simulate version conflict by updating record mid-cycle
           # (This requires hook injection or test-specific UoW)
           # ...

           envelope = P03BatchEnvelope.create(events=events, tenant_id="test", space_id="test")
           result = await runner.run(envelope, ctx)

           # Even with conflict, should succeed after retry
           assert result.status == P03PhaseStatus.DONE
   ```

2. **Test fixtures**:

   ```python
   # tests/k0/pipelines/p03/integration/fixtures.py
   from contextlib import asynccontextmanager
   from typing import List

   from k0.pipelines.p03.event_state import P03EventState


   @asynccontextmanager
   async def create_test_database():
       """Create isolated test database with P03 schema."""
       # Use testcontainers or pytest-postgresql
       # ...

   async def create_test_events(db, count: int, **kwargs) -> List[P03EventState]:
       """Generate and insert test events."""
       # ...

   async def create_runner_context(db) -> P03RunnerContext:
       """Create runner context with real syscalls."""
       # ...
   ```

**Acceptance Criteria**:

- [ ] Test runs R0→R8 with ALL real phases (no mocks)
- [ ] Test uses real PostgreSQL database (testcontainers or fixture)
- [ ] Happy path: events processed, episodes created, outbox populated
- [ ] Gap detection: ambiguous entity → st_learning_queue populated
- [ ] Error recovery: version conflict → retry succeeds
- [ ] Skip path: R5 backlogged → R5 skipped, R6 proceeds
- [ ] All phase statuses correctly recorded in envelope
- [ ] Test cleanup: database reset between tests

**Test File**: `tests/k0/pipelines/p03/integration/test_full_pipeline.py`

---

#### Issue 5.2.W6 — SequentialRunner handles R6 failure/retry

**Status**: NOT_STARTED

**Goal**: Add R6-specific error recovery to `P03SequentialRunner` per Appendix G.4 error recovery matrix.

**Dossier References**:

- [Appendix G.4 Error Recovery Matrix](../pipelines/P03_consolidation_dossier_v2.md#g4-error-recovery-matrix) — Error handling
- [Appendix G.3 State Transition Rules](../pipelines/P03_consolidation_dossier_v2.md#g3-state-transition-rules) — R6 transitions

**Error Recovery for R6** (per Appendix G.4):

| Error Type | Recovery Strategy | Max Retries | Backoff |
|------------|-------------------|-------------|---------|
| `VERSION_CONFLICT` | Re-read, re-stage | 3 | Immediate |
| `UNIQUE_VIOLATION` | Check existing, skip/merge | 1 | Immediate |
| `DLQ_CONDITION` | Version conflict on >10% of events | — | DLQ |

**Files to Modify**:

| File | Lines | Current Logic | New Logic |
|------|-------|---------------|-----------|
| `k0/pipelines/p03/sequential_runner.py:200-280` | `_run_phase()` | Generic error handling | Add R6-specific retry logic |
| `k0/pipelines/p03/runner_contract.py` | Error types | Generic | Add `R6_VERSION_CONFLICT`, `R6_UNIQUE_VIOLATION` |

**Existing Code Dependencies**:

| File | Lines | Purpose | How Used |
|------|-------|---------|----------|
| `k0/pipelines/p03/sequential_runner.py:200-280` | MODIFY | `_run_phase()` | Add R6 retry logic |
| `k0/pipelines/p03/runner_contract.py:1-100` | MODIFY | Error types | Add R6 error constants |
| `k0/pipelines/p03/observability.py` | USE | P03Error | Error classification |

**Deliverables**:

1. **Add R6 error types**:

   ```python
   # In runner_contract.py:
   class P03ErrorType(Enum):
       """Typed error categories for retry logic."""
       GENERIC = "GENERIC"
       DB_TIMEOUT = "DB_TIMEOUT"
       LOCK_TIMEOUT = "LOCK_TIMEOUT"
       POOL_EXHAUSTED = "POOL_EXHAUSTED"
       # M5: R6-specific errors
       R6_VERSION_CONFLICT = "R6_VERSION_CONFLICT"
       R6_UNIQUE_VIOLATION = "R6_UNIQUE_VIOLATION"
       R6_MANIFEST_INVALID = "R6_MANIFEST_INVALID"
   ```

2. **Add R6 retry logic to runner**:

   ```python
   # In sequential_runner.py:
   from k0.pipelines.p03.runner_contract import P03ErrorType

   # R6-specific retry configuration
   R6_RETRY_CONFIG = {
       P03ErrorType.R6_VERSION_CONFLICT: {
           "max_retries": 3,
           "backoff": "immediate",  # No delay
           "strategy": "re_read_re_stage",
       },
       P03ErrorType.R6_UNIQUE_VIOLATION: {
           "max_retries": 1,
           "backoff": "immediate",
           "strategy": "check_existing_skip_merge",
       },
   }

   # DLQ threshold for R6
   R6_DLQ_THRESHOLD = 0.10  # >10% version conflicts = DLQ

   async def _run_phase_with_retry(
       self,
       phase_id: P03PhaseId,
       envelope: P03BatchEnvelope,
       ctx: P03RunnerContext,
   ) -> P03PhaseResult:
       """Run phase with R6-specific retry logic."""

       if phase_id != P03PhaseId.R6_STAGE:
           # Use default retry for non-R6 phases
           return await self._run_phase(phase_id, envelope, ctx)

       # R6-specific retry loop
       retry_count = 0
       conflict_count = 0
       total_events = len(envelope.events)

       while True:
           result = await self._run_phase(phase_id, envelope, ctx)

           if result.status == P03PhaseStatus.DONE:
               return result

           # Check error type
           error_type = self._classify_r6_error(result)

           if error_type == P03ErrorType.R6_VERSION_CONFLICT:
               conflict_count += 1

               # Check DLQ threshold
               conflict_ratio = conflict_count / total_events if total_events > 0 else 0
               if conflict_ratio > R6_DLQ_THRESHOLD:
                   logger.error(
                       "R6: Conflict ratio exceeds DLQ threshold",
                       extra={
                           "conflict_ratio": conflict_ratio,
                           "threshold": R6_DLQ_THRESHOLD,
                       },
                   )
                   return self._create_dlq_result(result, phase_id, envelope)

               # Retry with re-read
               config = R6_RETRY_CONFIG[error_type]
               if retry_count < config["max_retries"]:
                   retry_count += 1
                   logger.warning(
                       "R6: Version conflict, retrying",
                       extra={"retry": retry_count, "max": config["max_retries"]},
                   )
                   # Re-read affected events for fresh versions
                   await self._refresh_event_versions(envelope, ctx)
                   continue

           elif error_type == P03ErrorType.R6_UNIQUE_VIOLATION:
               config = R6_RETRY_CONFIG[error_type]
               if retry_count < config["max_retries"]:
                   retry_count += 1
                   # Check existing, merge if needed
                   await self._handle_unique_violation(envelope, result, ctx)
                   continue

           # Max retries exceeded or unrecoverable error
           return result

   def _classify_r6_error(self, result: P03PhaseResult) -> P03ErrorType:
       """Classify R6 error for retry logic."""
       if result.error is None:
           return P03ErrorType.GENERIC

       error_msg = result.error.error_message.lower()
       if "version" in error_msg or "optimistic" in error_msg:
           return P03ErrorType.R6_VERSION_CONFLICT
       if "unique" in error_msg or "duplicate" in error_msg:
           return P03ErrorType.R6_UNIQUE_VIOLATION
       return P03ErrorType.GENERIC

   async def _refresh_event_versions(
       self,
       envelope: P03BatchEnvelope,
       ctx: P03RunnerContext,
   ) -> None:
       """Re-read event versions after conflict."""
       async with ctx.syscalls.unit_of_work() as uow:
           for event in envelope.events:
               row = await uow.connection.fetchrow(
                   "SELECT version FROM st_hipp_events WHERE event_id = $1",
                   event.event_id,
               )
               if row:
                   event.expected_version = row["version"]

   async def _handle_unique_violation(
       self,
       envelope: P03BatchEnvelope,
       result: P03PhaseResult,
       ctx: P03RunnerContext,
   ) -> None:
       """Handle unique violation by checking existing and merging."""
       # Extract conflicting record ID from error
       # Mark as duplicate in envelope
       # R6 will skip on next run
       pass

   def _create_dlq_result(
       self,
       original: P03PhaseResult,
       phase_id: P03PhaseId,
       envelope: P03BatchEnvelope,
   ) -> P03PhaseResult:
       """Create DLQ result when threshold exceeded."""
       return P03PhaseResult.fail(
           phase_id=phase_id,
           error=P03Error(
               error_id=f"r6-dlq-{envelope.context.cycle_id}",
               phase="R6",
               stage_id="retry_exhausted",
               error_type="R6_DLQ_THRESHOLD_EXCEEDED",
               error_message=f"Version conflicts exceeded {R6_DLQ_THRESHOLD * 100}% threshold",
               recoverable=False,
           ),
           duration_ms=original.duration_ms,
           idempotency_key=f"p03:r6:dlq:{envelope.context.cycle_id}",
       )
   ```

3. **Update run() to use R6-aware retry**:

   ```python
   # In P03SequentialRunner.run():
   async def run(
       self,
       envelope: P03BatchEnvelope,
       ctx: P03RunnerContext,
       resume_from: Optional[P03PhaseId] = None,
   ) -> P03CycleResult:
       # ... existing setup ...

       for phase_id in phase_order:
           if phase_id == P03PhaseId.R6_STAGE:
               # M5: Use R6-specific retry logic
               result = await self._run_phase_with_retry(phase_id, envelope, ctx)
           else:
               result = await self._run_phase(phase_id, envelope, ctx)

           # ... existing result handling ...
   ```

**Acceptance Criteria**:

- [ ] R6 VERSION_CONFLICT triggers immediate retry (max 3)
- [ ] R6 UNIQUE_VIOLATION triggers check-existing-skip-merge (max 1)
- [ ] DLQ triggered when >10% of events have version conflicts
- [ ] Event versions re-read between retries
- [ ] Retry count tracked in timeline/metrics
- [ ] Non-R6 phases use existing generic retry logic
- [ ] DLQ result includes cycle_id for debugging

**Test File**: `tests/k0/pipelines/p03/test_sequential_runner_r6_retry.py`

---

## Part D: References

### D.1 Implementation Plan Reference

Full issue definitions are in:

- [P03_implementation_plan_skeleton.md](../pipelines/P03_implementation_plan_skeleton.md) — Milestone 5 (lines 2446-3200)

### D.2 Dossier Reference

Primary specification:

- [P03_consolidation_dossier_v2.md](../pipelines/P03_consolidation_dossier_v2.md)

Key sections for M5:

- Section 4.7: R6 — Staging Table Updates
- Section 4.8: R7 — Memory Layer Writes
- Section 4.9: R8 — Event Emission
- Section 6.15: st_outbox schema
- Section 9.3: P03 → P06 Contract
- Appendix G: R0-R8 State Machine Specification

### D.3 Related Execution Documents

| Document | Status | Relevance |
|----------|--------|-----------|
| [M0_EXECUTION.md](./M0_EXECUTION.md) | ✅ COMPLETE | Contracts + ADRs foundation |
| [M1_EXECUTION.md](./M1_EXECUTION.md) | ✅ COMPLETE | Pipeline skeleton, P03StagedWrites |
| [M2_EXECUTION.md](./M2_EXECUTION.md) | ✅ COMPLETE | Storage migrations (st_epi, st_sem, etc.) |
| [M3_EXECUTION.md](./M3_EXECUTION.md) | ✅ COMPLETE | R7/R8 basic wiring, outbox integration |
| [M4_EXECUTION.md](./M4_EXECUTION.md) | ✅ COMPLETE | R1-R4 cognition algorithms |

---

## Appendix: Test Strategy

### Test File Locations

```text
tests/k0/modules/consolidation/staging/
├── test_r6_output.py
├── test_status_marker.py
├── test_dedup_metadata.py
├── test_reconciliation_recorder.py
├── test_idempotency.py
├── test_assemblers.py
├── test_manifest_validator.py
└── test_r6_coordinator.py

tests/k0/modules/consolidation/truth_writer/
├── test_writer.py
├── test_outbox.py
├── test_layers.py
├── test_transaction.py
└── test_r7r8_coordinator.py

tests/k0/modules/consolidation/emission/
├── test_emitter.py
├── test_gap_emitter.py
├── test_offset_manager.py
└── test_metrics.py
```

### Coverage Targets

| Module | Target |
|--------|--------|
| `staging/` | ≥90% line coverage |
| `truth_writer/` | ≥90% line coverage |
| `emission/` | ≥90% line coverage |
| Integration tests | Full R6-R7-R8 flow |
