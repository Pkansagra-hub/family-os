# R2 Episodic Integration — End-to-End Gap Analysis Report

**Date**: 2025-07-18
**Source Plan**: `docs/plans/R2_EPISODIC_INTEGRATION_EPIC_PLAN.md` (7207 lines, 9 milestones)
**Method**: Exhaustive plan-vs-code cross-reference via deep codebase analysis

---

## Executive Summary

The R2 Epic Plan is **dramatically behind the actual codebase**. A large volume of work the plan still marks as OPEN has already been implemented, tested, and shipped. Simultaneously, rigorous research (18 scripts, 46 result files in `poc/r2_phase_research/`) has **rejected or deferred** several planned features, significantly narrowing the remaining scope.

| Category | Issue Count | % of Total |
|---|---|---|
| DONE in code (plan says OPEN) | ~121 issues | ~72% |
| Deferred / Rejected by research | ~32 issues | ~19% |
| Genuinely remaining work | ~35 issues | ~21% |
| Blocked on K1 signals | ~17 issues | ~10% |

> **CORRECTED 2025-07-18**: Original analysis understated M9 completion. Deep inspection of
> `k0/modules/consolidation/{identity,reconciliation,query,truth_layer_registry.py}` revealed
> the Universal Reconciliation Engine is ~75% implemented with 100+ tests. The original report
> claimed M9 was "ALL OPEN (~85 issues)" — in reality ~53 of those issues are DONE in code.

**Bottom line**: Of the ~169 trackable issues across M1-M9, roughly 72% are already complete in production code, 19% have been intentionally deferred or rejected by research evidence, and 21% represent genuine remaining implementation work. The largest remaining bodies of work are M9.7-9.10 (R3-R6 phase migrations to the new framework, ~25 issues), M8 (Integration Tests, ~50 tests), and M4 (Centroid & Quality, ~15 active issues after research narrowing).

---

## Milestone-by-Milestone Status

### Milestone 1: Critical Fixes — COMPLETE

**Status**: Plan and code agree. Baseline complete.

| Epic | Plan Status | Code Status | Notes |
|---|---|---|---|
| M1 baseline | Partial/Complete | DONE | EventAdapter, timestamp chain, GAP-002 signals all shipped |

No remaining gaps.

---

### Milestone 2: DBSCAN Removal + Quality Fix + Contract Reconciliation — COMPLETE

**Status**: Plan says OPEN for most issues. Code is fully DONE. This is the single largest plan-vs-code divergence.

| Epic | Issues | Plan Status | Code Status | Evidence |
|---|---|---|---|---|
| 2.1 DBSCAN Full Removal | 8 | OPEN | **DONE** | `episodic_dbscan.py` deleted, zero DBSCAN imports in codebase, contracts clean |
| 2.2 Fake Silhouette Fix | 8 | OPEN | **DONE** | `cluster_quality.py` rewritten, 5 quality channels, real silhouette computation |
| 2.3 Contract Reconciliation | 6 | OPEN | **DONE** | `p03_consolidation.v1.yaml` + `consolidation.episodic_clusterer.v1.yaml` updated, algorithm=HDBSCAN |

**22 issues marked OPEN in plan that are DONE in code.**

---

### Milestone 3: Multi-Dimensional Distance + Splitting + Rescue — ~70% DONE

| Epic | Issues | Plan Status | Code Status | Gap |
|---|---|---|---|---|
| **3.1 6D CompositeDistance** | 7 | OPEN | **5/7 DONE** | 3.1.0 EventAdapter (DONE, 43 properties), 3.1.1 semantic refactor (DONE), 3.1.5 narrative 7-tier chain (DONE), 3.1.6 graceful degradation (DONE). 3.1.2/3.1.3/3.1.4 spatial/social/affective EXCLUDED by research (weight=0.0) |
| **3.2 Log-Temporal** | 3 | OPEN | **2/3 DONE** | 3.2.1 log-temporal (DONE, tau=30min), 3.2.3 hard cutoff (DONE). 3.2.2 timestamp quality BLOCKED (0/1360 K1 temporal_source coverage) |
| **3.3 Boundary Scoring** | 7 | OPEN | **6/7 DONE** | 3.3.0-3.3.2, 3.3.4-3.3.6 all DONE (3-tier accumulated boundary model). 3.3.3 sort verification NEEDS VERIFICATION |
| **3.4 HDBSCAN Noise Rescue** | 4 | OPEN | **1/4 DONE** | 3.4.2 context-aware rescue (DONE: 4-stage scoring with distance 40%, narrative 30%, social 15%, spatial 15%). **3.4.0 zero dedicated HDBSCAN tests**, 3.4.1 magic numbers not externalized, 3.4.3 no weak-cluster tests |
| **3.5 Wrapper Decomposition** | 4 | OPEN | **0/4 DONE** | Pure refactoring. Target: 2134 -> ~762 lines. Not a functionality gap. |
| **3.6 Temporal Context Binding** | 6 | OPEN | **1/6 DONE** | 3.6.0 EventAdapter temporal extension (DONE, 5 fields, 58 tests). 3.6.1-3.6.5 all DEFER (0/1360 K1 signal coverage, documented rationale) |
| **3.7 Signal Surface** | 5 | OPEN | **5/5 DECISIONS MADE** | All RESOLVED: spatial EXCLUDE, location EXCLUDE/KEEP labeling, participants EXCLUDE, intent EXCLUDE/KEEP metadata, content EXCLUDE/ALLOW summary |

**Summary**: 20/36 issues DONE, 8 deferred by research, 5 decisions made. **3 genuinely remaining**: HDBSCAN test file (3.4.0), externalize rescue constants (3.4.1), weak-cluster tests (3.4.3). Wrapper decomposition (3.5) is 4 refactoring issues.

---

### Milestone 4: Centroid & Quality Enhancements — RESEARCH COMPLETE, Implementation OPEN

Research has dramatically narrowed scope. 3 of 6 epics are rejected/deferred.

| Epic | Issues | Plan Status | Code Status | Research Outcome |
|---|---|---|---|---|
| **4.1 Salience-Composite Weighting** | 6 | OPEN | **Research done, code OPEN** | M4-RSCH-01: recency_exp is the ONLY factor needed (MRR=0.9006). Multi-factor formula NOT needed. Scope reduced. |
| **4.2 Multi-Centroid** | 5 | OPEN | **Research done, code OPEN** | M4-RSCH-02: best_of_all MRR=0.9627 (primary + start + end + emotional_peak + narrative_anchor). M4-RSCH-05: json_blob storage wins. 3 write surfaces to update. |
| **4.3 Probability Centroids** | 4 | OPEN | **REJECTED** | M4-RSCH-03: uniform MRR=0.8943 > best prob strategy 0.8813. DO NOT BUILD. |
| **4.4 EpisodicCoherenceScore** | 5 | OPEN | **Research done, code OPEN** | M4-RSCH-04: equal_weight coherence rho=0.4556 vs silhouette mean=-0.0329 (broken post-correction). Coherence should replace silhouette as primary quality metric. |
| **4.5 Vectorized Distance** | 5 | OPEN | **DEFERRED** | M4-RSCH-06: scalar adequate for N<=100. 70.61x speedup possible but parity FAILS on narrative (fuzzy matching). Defer until N>200. |
| **4.6 Signal Encoding** | 5 | OPEN | **Mostly DEFER** | M4-RSCH-07: all 9 signals SUMMARY-ONLY (delta < 0.01). memory_tier, identity_domains_json DON'T EXIST on P03EventState. |

**Summary**: 4 issues REJECTED (4.3), 10 issues DEFERRED (4.5 + most of 4.6). **16 genuinely remaining**: Epic 4.1 (6 issues, reduced scope), Epic 4.2 (5 issues), Epic 4.4 (5 issues).

**Key M4 prerequisites before implementation:**
- 4.0.1: Delete `R2StagedOutput` dead code
- 4.0.2: Baseline existing centroid test surface (17 tests across 6 classes)
- 4.1.0: Extend `CentroidableEvent` protocol (currently only 4 fields)

---

### Milestone 5: Hebbian & Adaptive Enhancements — COMPLETE

| Epic | Issues | Plan Status | Code Status | Research Outcome |
|---|---|---|---|---|
| **5.1 Hebbian Boost** | 5 | Research Complete | **DONE** | ADOPT. scale=0.10, cap=0.05, min_count=1. +3 scenarios 5/8 -> 8/8. `hebbian_boost.py` shipped. |
| **5.2 Adaptive Weights** | - | Research Complete | **REJECTED** | No adaptive policy beats static 0.45/0.25/0.30. DO NOT BUILD. |
| **5.3 Reliability/Provenance Gating** | 6 | OPEN | **DEFERRED** | 0/1360 K1 signal coverage. All 6 sub-issues deferred with documented rationale. |

**Summary**: Research exit gate PASSED. Production wiring DONE. 6 issues deferred (blocked on K1 signals).

**Critical artifact**: M5 contains the **Research-to-Production Parameter Registry** — the authoritative reference for all proven pipeline parameters across 8 stages (S1 Splitting through S8 Centroid Encoding). This registry should be treated as the production configuration source of truth.

---

### Milestone 6: Production Episode Quality — COMPLETE

**Status**: Plan says partially OPEN. Code is fully DONE with 181+ tests.

| Epic | Issues | Plan Status | Code Status | Test Count |
|---|---|---|---|---|
| 6.1 Ensemble Distance Wiring | 5 | DONE | **DONE** | 20 tests |
| 6.2 Thread Purity Correction | 5 | OPEN | **DONE** | 23 tests |
| 6.3 Same-Thread Merge | 5 | OPEN | **DONE** | 33 tests |
| 6.4 Cross-Batch Extension | 4 | OPEN | **DONE** | 31 tests |
| 6.5 Metadata Preservation | 3 | OPEN | **DONE** | Migration 0086 (9 columns to st_epi) |
| 6.6 Deduplication | 3 | DONE | **DONE** | 52 tests, Migration 0087 |

**25 issues, all DONE. 181+ tests shipped.**

---

### Milestone 7: REMOVED

Absorbed into M9. Absorption map:
- 7.1 -> 9.5 + 9.6
- 7.2 -> 9.4.5 + 9.5.5 + 9.6
- 7.3 -> 9.11 (Rich Structured Summaries)
- 7.4 -> 9.12 (Embedding Regeneration)
- 7.5 -> 9.13 (Lifecycle Observability)

Issue 7.2.0 (K1 Signal Pipeline) shipped 2026-03-08.

---

### Milestone 8: Integration Test Suite — ALL OPEN

**Status**: Research complete, execution gate = after M9. None ported to production.

| Epic | Issues | Scope |
|---|---|---|
| 8.1 Test Fixture Infrastructure | - | Real DB fixtures, event generators, episode builders |
| 8.2 Scenario Evaluation Framework | - | K-stage evaluation, MRR/nDCG computation |
| 8.3 Window-2 Adjacent Pair Tests | - | 2-batch sliding window |
| 8.4 Window-3 Triple Tests | - | 3-batch sliding window |
| 8.5 Window-4/5 Tests | - | Deeper chain validation |
| 8.6 Extended + Full Chain Tests | - | Full pipeline validation |
| 8.7 Cross-Batch Lifecycle Tests | - | EXTEND/EVOLVE specific |
| 8.8 Research Parity Regression | - | Production vs research MRR parity |

**~50 sliding-window tests planned. CogQ framework: 8 dimensions, target score=0.7117.**

This is the capstone validation milestone. It cannot execute until M9 (Universal Reconciliation) provides the reconciliation framework that the tests validate against.

---

### Milestone 9: Universal Reconciliation + Lifecycle — ~75% DONE (CORRECTED 2025-07-18)

**Status**: Core framework BUILT and WIRED. Plan marks all ~85 issues as OPEN but code tells a different story.

> **CORRECTION**: The original gap analysis incorrectly stated M9 was "ALL OPEN (~85 issues)."
> Deep code inspection reveals the Universal Reconciliation Engine is largely implemented,
> tested, and actively wired into R2. Only phase migrations (R3-R6) and non-episodic
> identity strategies remain.

**Architecture**: 5 layers — ALL IMPLEMENTED

1. **TruthLayerRegistry** — `k0/modules/consolidation/truth_layer_registry.py`: TruthLayerSpec (20+ fields), MergeRule (16 enum values), 7 truth layers registered via 9 YAML contracts in `k0/contracts/schemas/*.columns.yaml`
2. **IdentityStrategy** — `k0/modules/consolidation/identity/`: Protocol + EpisodicIdentity (11-feature 3-way multinomial logistic regression, trained on 300 golden pairs, frozen weights in `episodic_v1.json`)
3. **TruthCandidateQuery** — `k0/modules/consolidation/query/`: Builder (EMBEDDING/KEY/HYBRID SQL generation with pgvector `<=>`) + Mapper (row-to-TruthRecord with pgvector string decoding)
4. **ReconciliationFramework** — `k0/modules/consolidation/reconciliation/engine.py`: 6-stage stateless `decide()` + `decide_batch()` (K1 Signal Check -> Override Check -> Identity Filter -> Similarity Rank -> Threshold Decision -> Result Assembly)
5. **WriteDecisionRouter** — `k0/modules/consolidation/reconciliation/router.py`: Data-driven ReconciliationResult -> StagedWrite(s) mapping for all 7 actions (SKIP/CREATE/REINFORCE/EXTEND/EVOLVE/CONTRADICT/PRUNE)

**Supporting Components — ALL IMPLEMENTED**:
- `merge_engine.py`: Per-column merge for EXTEND using all 16 MergeRule types from TruthLayerSpec
- `evolve_handler.py`: EVOLVE produces 2 StagedWrites (archive old + insert new canonical)
- `contradict_handler.py`: CONTRADICT inserts gap into st_learning_queue for P06
- `confidence.py`: Per-action confidence formula (base + evidence + identity_boost + count_boost)
- `result.py`: ReconciliationResult frozen dataclass (14 fields)
- `idem.py`: RouterIdempotencyKey deterministic key generation
- `migration.py`: DualPathRunner feature-flagged legacy/engine dual-path with divergence logging
- `adapters/r2_adapter.py`: R2Adapter with event_to_candidate (Seam 1: REINFORCE) + episode_to_candidate (Seam 2: EXTEND)
- `hooks/runner.py`: PostReconciliationHookRunner (summary_regen -> centroid_recompute -> batched UPDATE)
- `hooks/summary_regen.py`: SummaryRegenerator (episodic: StructuredEpisodeSummary JSON; non-episodic: template)
- `hooks/centroid_recompute.py`: CentroidRecomputer (episodic: weighted mean; non-episodic: re-embed via UltraBERT)
- `hooks/episode_summary.py`: StructuredEpisodeSummary dataclass + build_structured_summary()
- `decision_log.py` + `metrics.py`: Structured logging + Prometheus emission (counters, histograms, gauges)
- `types.py`: K1SignalBundle, ReconciliationCandidate, TruthRecord, IdentityResult

**R2 Wiring — LIVE**:
- `r2_episodic_integrator.py` imports `R2Adapter` (line 83) and `ReconciliationFramework` (line 84)
- Seam 1 (event-level REINFORCE): `_engine_match_events()` at line ~2104 — calls `ReconciliationFramework.decide()` per event
- Seam 2 (episode-level EXTEND): `_engine_extend_episodes()` at line ~2186 — calls `ReconciliationFramework.decide()` per episode candidate
- DualPathRunner migration harness available (M9.8) for safe rollout

| Epic | Issues | Plan Status | **Code Status** | Evidence |
|---|---|---|---|---|
| 9.1 Truth Layer Registry | 5 | OPEN | **DONE** | truth_layer_registry.py, 7 layers, 9 YAML contracts, 20+ tests in test_truth_layer_registry.py + test_truth_layer_contracts.py |
| 9.2 Identity Strategy | 9 | OPEN | **PARTIALLY DONE** | Protocol + EpisodicIdentity (11-feature logistic model) DONE. 4 test files: test_protocol.py, test_episodic.py, test_features.py, test_golden_regression.py. **Missing: identity strategies for 6 non-episodic layers** |
| 9.3 truth_candidates_query | 6 | OPEN | **DONE** | query/builder.py (EMBEDDING/KEY/HYBRID), query/mapper.py, pgvector integration |
| 9.4 Reconciliation Framework | 7 | OPEN | **DONE** | engine.py (6-stage decide + decide_batch), confidence.py, result.py. 20+ tests in test_engine.py |
| 9.5 Write Decision Router | 8 | OPEN | **DONE** | router.py, merge_engine.py (16 MergeRules), evolve_handler.py, contradict_handler.py, idem.py. 20+ tests across test_router.py + test_merge_engine.py |
| 9.6 Migrate R2 | 5 | OPEN | **DONE** | r2_adapter.py (2 seams), DualPathRunner, R2 integrator WIRED at lines 2104-2210. 20+ tests in test_r2_engine_path.py |
| 9.7 Migrate R3 | 6 | OPEN | **OPEN** | R3 still imports OLD `ReconciliationEngine` from `algorithms/reconciliation_engine.py`. Needs migration to new `ReconciliationFramework` |
| 9.8 Migrate R4 | 9 | OPEN | **OPEN** | R4 (kg_consolidator) has ZERO reconciliation imports. Needs framework integration for entity/edge resolution |
| 9.9 Migrate R5 | 6 | OPEN | **OPEN** | R5 (dream_explorer) has ZERO reconciliation imports. Needs framework integration for dream outputs |
| 9.10 Simplify R6 | 4 | OPEN | **OPEN** | R6 (staging) collects StagedWrites but doesn't use the new framework. Needs simplification to collect pre-built writes |
| 9.11 Structured Summaries | 6 | OPEN | **DONE** | hooks/episode_summary.py (StructuredEpisodeSummary), hooks/summary_regen.py. 9 tests in test_hooks_integration.py |
| 9.12 Embedding Regeneration | 5 | OPEN | **DONE** | hooks/centroid_recompute.py, hooks/runner.py coordinates post-R7 chain |
| 9.13 Lifecycle Observability | 4 | OPEN | **PARTIALLY DONE** | decision_log.py + metrics.py (DecisionMetrics with Prometheus) exist. **Missing: dashboard queries (M9.13.2)** |

**Revised M9 Summary**:
- **DONE**: 9.1, 9.3, 9.4, 9.5, 9.6, 9.11, 9.12 = ~47 issues (56%)
- **PARTIALLY DONE**: 9.2 (EpisodicIdentity done, 6 other layers missing), 9.13 (logging/metrics done, dashboards missing) = ~13 issues with ~6 done (7%)
- **GENUINELY OPEN**: 9.7, 9.8, 9.9, 9.10 (R3-R6 phase migrations) = ~25 issues (30%)

**Remaining M9 Work** (~32 issues):
1. **M9.2**: Identity strategies for st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges (~6 implementations)
2. **M9.7**: Migrate R3 from old ReconciliationEngine to new ReconciliationFramework (~6 issues)
3. **M9.8**: Add ReconciliationFramework to R4 for entity/edge resolution (~9 issues)
4. **M9.9**: Add ReconciliationFramework to R5 for dream outputs (~6 issues)
5. **M9.10**: Simplify R6 to collect pre-built StagedWrites from framework (~4 issues)
6. **M9.13.2**: Dashboard queries for lifecycle observability (~1-2 issues)

---

## Critical Code Inconsistencies Found

| Issue | Location | Impact | Fix Milestone |
|---|---|---|---|
| EXTEND uses raw string `"EXTEND"`, REINFORCE uses `ReconciliationAction` enum | r2_episodic_integrator.py | Type mismatch between event-level and cluster-level reconciliation | M9.6 — **RESOLVED** (engine path uses `ReconciliationAction` enum consistently) |
| `episode_extend_threshold=0.60` declared but NEVER USED | R2Config | Dead config — EXTEND threshold comes from CrossBatchExtendMatcher | M9.6 — **RESOLVED** (engine uses TruthLayerSpec thresholds) |
| `_decode_vector` may use `struct.unpack` (BYTEA) but pgvector returns strings | r2_episodic_integrator.py | Latent bug since M4 pgvector migration | M3 or M9.6 |
| No `reconciliation_action` field on `EpisodeCluster` dataclass | phase_outputs.py | Cluster-level decisions live on EpisodeCandidate (wrong type) | M9.6 — **RESOLVED** (ReconciliationResult replaces per-type fields) |
| ReconciliationEngine has ZERO test coverage | reconciliation_engine.py | `decide()`, `_determine_action()`, `_compute_confidence()` untested | **SUPERSEDED** — new ReconciliationFramework has 20+ tests |
| Phantom quality bonus: `(1-correction_rate)` adds +0.20 when correction is always 0.0 | cluster_quality.py | Inflated composite quality scores | M4.4 |
| `evolve_sim_threshold=0.40` in ReconciliationEngine — DEAD CODE | reconciliation_engine.py | Config exists but EVOLVE path never fires | M5 dead code checklist |
| `R2StagedOutput` — defined, exported, protocol-referenced, never instantiated | phase_outputs.py | Dead code polluting type surface | M4.0.1 |
| `episodic_dbscan.py` params in code: `DBSCANParams` remnants | If any remain | Should be zero — verify complete removal | M2 (verify) |
| `memory_tier` referenced in M4.6 plan but DOES NOT EXIST on P03EventState | P03EventState | Plan assumes field that was never added | Plan update needed |
| `identity_domains_json` referenced in M4.6 plan but DOES NOT EXIST | P03EventState | Plan assumes field that was never added | Plan update needed |

---

## Dead Code Removal Checklist (from M5 Parameter Registry)

| Item | Action | Status | Milestone |
|---|---|---|---|
| `EpisodicDBSCAN` class | REMOVE | **DONE** (file deleted) | M2 |
| `DBSCANParams` dataclass | REMOVE | Verify complete removal | M3 |
| HDBSCAN-to-DBSCAN bridge code | REMOVE | Verify no bridge remains | M2 |
| `_merge_similar_threads` | DISABLE (currently disabled) | Verify disabled | M6 |
| 6D distance dimensions (spatial, social, affective) | DO NOT BUILD | Research decision | M3 |
| Boost separation (distance vs clustering) | DO NOT BUILD | Research decision | M5 |
| Signal-weighted centroids (multi-factor encoding formula) | DO NOT BUILD | Research decision (recency_exp only) | M4 |
| HDBSCAN probability-weighted centroids | DO NOT BUILD | M4-RSCH-03 rejection | M4 |
| EVOLVE/CONTRADICT cosine detection in P03 | REMOVE from P03 | Move to M9 framework | M9 |
| `dbscan` key rename in contracts | DEFER | Low priority | - |
| `R2StagedOutput` | DELETE | Dead code — never instantiated | M4 |

---

## Blocked Items (Awaiting K1 Signal Population)

These items are architecturally sound but cannot be implemented until K1 populates the required signals on `st_hipp_events`. Current coverage: **0 of 1360 events** have K1 signals.

| Item | K1 Signal Required | Epic |
|---|---|---|
| Timestamp quality weighting | `temporal_source` | 3.2.2 |
| Temporal context binding (5 issues) | `temporal_links_json`, `temporal_anchor_json`, `time_of_day_bucket`, `circadian_slot`, `is_weekend`, `extraction_sequence` | 3.6.1-3.6.5 |
| Reliability/provenance gating (6 issues) | K1 reliability signals | 5.3 |
| K1 threshold cascade in reconciliation | `correction_signal`, `contradiction_signal` | 9.4.5 |

---

## Research-to-Production Parameter Registry (Proven Values)

The following parameters are research-proven and represent the production configuration target. Source: M5 section of Epic Plan.

| Stage | Parameter | Proven Value |
|---|---|---|
| S1 Splitting | config profile | `research_balanced_v1` (14 params) |
| S1 Splitting | batch_size | 300 (DONE 2026-03-09) |
| S2 Distance | model | `ens_fuzzy_narrative_v10` (3D, NOT 6D) |
| S2 Distance | weights | semantic=0.45, temporal=0.25, narrative=0.30 |
| S2 Distance | narrative chain | 7-tier (exact→fuzzy>=0.78→fuzzy>=0.60→different→goal_match→goal_different→partial→MISS) |
| S2 Distance | short-circuit | cap=0.20, confidence >= 0.7 triggers |
| S2b Hebbian | boost_scale | 0.10 |
| S2b Hebbian | cap | 0.05 |
| S2b Hebbian | min_count | 1 |
| S3 HDBSCAN | min_cluster_size | 2 |
| S3 HDBSCAN | min_samples | 1 |
| S3 HDBSCAN | method | leaf, precomputed |
| S4 Thread Purity | strategy | group by narrative_thread_id |
| S4 Thread Purity | merge | DISABLED |
| S5 Same-Thread Merge | centroid_sim | >= 0.70 |
| S5 Same-Thread Merge | temporal_gap | < 4h |
| S5 Same-Thread Merge | purity | >= 80% |
| S6 Cross-Batch | extend_sim | 0.70 |
| S6 Cross-Batch | evolve_sim | 0.40 (DEAD CODE — to remove) |
| S7 Scene Segmentation | scene_gap | 4h |
| S7 Scene Segmentation | overnight | 8h |
| S7 Scene Segmentation | max_events | 35 |
| S8 Centroid | primary | recency_exp |
| S8 Centroid | multi-centroid | best_of_all (primary + start + end + emotional_peak + narrative_anchor) |
| S8 Centroid | storage | json_blob (centroid_metadata_json column) |
| Quality | CogQ dimensions | 8, scene-level score=0.7117 |

---

## Recommended Priority Order for Remaining Work

### Priority 1: Quick Wins and Cleanup (1-2 weeks)

1. **M4.0.1**: Delete `R2StagedOutput` dead code
2. **M3.4.0**: Create `test_r2_episodic_hdbscan.py` (zero tests for 1400-line module)
3. **M3.4.1**: Externalize rescue constants (3 magic numbers)
4. **M3.4.3**: Write weak-cluster behavior tests
5. **Fix type inconsistency**: EXTEND string -> `ReconciliationAction` enum
6. **Fix phantom bonus**: Remove `(1-correction_rate)` +0.20 inflation in cluster_quality.py
7. **Verify pgvector decode**: Confirm `_decode_vector` handles string format correctly

### Priority 2: M4 Centroid & Quality (scope-narrowed by research)

1. **Epic 4.1**: Implement recency_exp as production centroid strategy (research proves MRR=0.9006)
2. **Epic 4.2**: Multi-centroid implementation (json_blob storage, 3 write surfaces, retrieval path)
3. **Epic 4.4**: EpisodicCoherenceScore (replace phantom quality channels, 5 coherence dimensions)

### Priority 3: M3.5 Wrapper Decomposition (refactoring)

1. Extract episode builder (~409 lines)
2. Extract episode matcher (~212 lines)
3. Extract quality coordinator (~200 lines)
4. Reduce wrapper from 2134 to ~762 lines

### Priority 4: M9 Phase Migrations (R3-R6 only)

The core framework is DONE. Remaining M9 work is wiring the other phases:

1. **M9.7**: Migrate R3 from old `ReconciliationEngine` (algorithms/) to new `ReconciliationFramework` (reconciliation/)
2. **M9.8**: Add `ReconciliationFramework` to R4 (kg_consolidator) for entity/edge EXTEND/EVOLVE/CONTRADICT
3. **M9.9**: Add `ReconciliationFramework` to R5 (dream_explorer) for dream output reconciliation
4. **M9.10**: Simplify R6 (staging) to collect pre-built StagedWrites from the framework
5. **M9.2 (remaining)**: Identity strategies for 6 non-episodic truth layers (st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges)
6. **M9.13.2**: Dashboard queries for lifecycle observability

### Priority 5: M8 Integration Tests (capstone validation)

Execute after M9. This is the final proof that production matches research quality.

---

## Positive Changes from Plan (Code Ahead of Documentation)

The following significant improvements exist in code but are NOT reflected in the plan's status tracking:

1. **43-property EventAdapter** — far exceeds the plan's 4-field EventLike protocol
2. **7-tier narrative fallback chain** — more sophisticated than the plan's binary narrative distance
3. **4-stage context-aware noise rescue** — the plan describes hardcoded thresholds; code has weighted multi-signal rescue
4. **Confidence-weighted bagging distance formula** — `d = sum(w_i * conf_i * d_i) / sum(w_i * conf_i)` with MISS exclusion
5. **Short-circuit mechanism** — cap=0.20 for high-confidence narrative matches, not in original plan
6. **181+ M6 tests** — extensive test coverage for thread purity, same-thread merge, cross-batch extend, dedup
7. **Scene segmentation** — fully implemented (scene_gap=4h, overnight=8h, max_events=35, absorption)
8. **Fragment absorption** — small clusters absorbed into larger ones, not in original plan scope
9. **Adaptive learning loop** — quality-driven parameter tuning, not in original plan
10. **Two-stage deduplication** — SimHash + embedding verification (52 tests), added beyond plan scope

---

## Summary Statistics

| Metric | Value |
|---|---|
| Total plan issues (M1-M9) | ~169 |
| DONE in code | ~121 (72%) |
| Deferred/Rejected by research | ~32 (19%) |
| Blocked on K1 signals | ~17 (10%) |
| Genuinely remaining | ~35 (21%) |
| Test files for R2 | 16 files |
| Total R2 tests | 300+ |
| Algorithm modules | 12 files, ~8000 lines |
| Research scripts | 18 |
| Research result files | 46 |
| Proven production parameters | 30+ documented values |
| M9 reconciliation test files | 7 files (engine, router, merge_engine, hooks, truth_layer_registry x2, r2_engine_path) |
| M9 identity test files | 4 files (protocol, episodic, features, golden_regression) |
| M9 YAML contracts | 9 files (7 truth layers + st_vec + st_hipp_events) |

**The plan needs a status refresh to reflect the actual state of the codebase. Roughly 60% of tracked issues are either complete or intentionally deferred, leaving ~52 issues of genuine remaining work concentrated in M4 (centroid/quality), M8 (integration tests), and M9 (universal reconciliation).**
