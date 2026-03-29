# R2 Episodic Integration Enhancement -- Epic Implementation Plan

**Date**: 2026-03-04
**Updated**: 2026-03-06
**Status**: ACTIVE PLANNING
**Priority**: HIGH
**Pipeline Scope**: P03 Consolidation (R2 Phase)
**Branch**: `k1-Kernel-POC`
**Discovery Source**: `docs/pipelines/p03_enhancement_discovery/P03_R2_EPISODIC_INTEGRATION_DISCOVERY.md`
**Planning Basis**: corrected discovery document + verified repo status as of 2026-03-06

---

## Executive Summary

This plan has been rewritten to match the corrected discovery document and the current repository state.
The previous version assumed Milestone 1 had not started; that is no longer true.
The repo already contains the core GAP-002/M1 signal-surface work, while most Milestone 2 through
Milestone 5 work remains open.

The planning posture is now:

1. Treat completed and partially completed work as baseline, not future scope.
2. Focus next execution on Milestone 2 cleanup/compliance before moving into new algorithm design.
3. Preserve milestone order, but re-scope each epic against verified code reality.
4. Track open work at the issue level with explicit status: `DONE`, `PARTIAL`, `OPEN`, `BLOCKED`.

---

## Verified Current Status Summary

| Component | Status | Notes |
| --------- | ------ | ----- |
| Discovery & Deep Traces (Sections 16-24) | DONE | Corrected discovery doc is coherent and up to date. |
| Milestone 1: Critical Fixes (P0) | MOSTLY COMPLETE | EventAdapter expansion is implemented. Timestamp chain is mitigated via `conversation_anchor_ms`, fallback hardening, `temporal_source`, and observability. |
| Milestone 2: Cleanup & Compliance (P1) | OPEN | DBSCAN removal has not happened. Fake silhouette remains. Contracts are still stale. |
| Milestone 3: Distance & Splitting (P2) | OPEN | Event surface is available, but CompositeDistance and EpisodeSplitter still use legacy logic. |
| Milestone 4: Centroid & Quality (P3) | OPEN | Existing centroiding is legacy importance/recency based. No multi-centroid or episodic coherence implementation exists. |
| Milestone 5: Hebbian & Adaptive (P4) | DONE (2026-03-09) | Hebbian boost IMPLEMENTED (scale=0.10, cap=0.05, 8/8 scenarios, zero contamination). Adaptive weights REJECTED (static 0.45/0.25/0.30 wins). Reliability gating DEFERRED (K1 signals not populated). |
| Milestone 6: Production Episode Quality (P5) | DONE | RC-0 batch_size=300 + drain loop. 6.1 Ensemble 3D wiring (20 tests), 6.2 Thread purity correction (23 tests), 6.3 Same-thread merge (33 tests), 6.4 Cross-batch extension (31 tests), 6.5 Metadata preservation (migration 0086, 22 tests), 6.6 Consolidation cycle dedup (6.6.1+6.6.2 verified in code, 6.6.3 migration 0087, 52 tests). Total: 181 tests. |
| Milestone 7: REMOVED | REMOVED | Absorbed into M9 (2026-03-08). Issue 7.2.0 (signal pipeline) DONE — inherited by M9. All lifecycle mechanics (EXTEND, EVOLVE, summaries, embedding regen, observability) moved to M9 Epics 9.11-9.13. |
| Milestone 8: Integration Test Suite (P8) | RESEARCH COMPLETE | 8-metric CogQ framework (CogQ=0.7117 scene-level), 8 hand-crafted scenarios (7/8 perfect), 13 retrieval probes, run_matrix config sweep. Port cognitive_metrics.py and scenarios.py to production test suite. |
| Milestone 9: Universal Reconciliation + Lifecycle (P6) | RESEARCH COMPLETE | Two-tier reconciliation engine proven (Tier 1: K1 signals EVOLVE/CONTRADICT, Tier 2: similarity cascade REINFORCE>=0.85/EXTEND>=0.60/CREATE<0.60). AccumulatedEpisode with importance tracking and evolve chains. Scene segmentation Phase 9 (64% human-scale episodes). Port reconciliation.py and scene_segmentation.py. |

---

## Milestone Overview

```text
MILESTONE 1: Critical Fixes (P0)
  1.1 EventAdapter Signal Activation        DONE
  1.2 Timestamp Chain Fix                   PARTIAL

MILESTONE 2: Cleanup & Compliance (P1)
  2.1 DBSCAN Full Removal                   OPEN
  2.2 Fake Silhouette Fix                   OPEN
  2.3 Contract Reconciliation               OPEN

MILESTONE 3: Distance & Splitting (P2)
  3.1 6-Dimensional CompositeDistance       OPEN
  3.2 Logarithmic Temporal Distance         OPEN
  3.3 Boundary Strength Scoring             OPEN
  3.4 HDBSCAN Noise Rescue Calibration      PARTIAL
  3.5 Phase Wrapper Decomposition           OPEN
  3.6 Temporal Context Binding              OPEN
  3.7 Signal Surface Completion             OPEN

MILESTONE 4: Centroid & Quality (P3)
  4.1 Salience-Composite Centroid Weighting OPEN
  4.2 Multi-Centroid Episode Representation OPEN
  4.3 Probability-Augmented Centroids       OPEN
  4.4 EpisodicCoherenceScore                OPEN
  4.5 Vectorized Distance Matrix            OPEN
  4.6 Narrative/Cognitive Signal Encoding   OPEN

MILESTONE 5: Hebbian & Adaptive (P4)                   DONE (2026-03-09)
  5.1 Hebbian Distance Boost                DONE (hebbian_boost.py, 39 tests, 0 regression)
  5.2 Context-Adaptive Weights              REJECTED (static wins)
  5.3 Reliability & Provenance Gating       DEFERRED (K1 signals not populated)

MILESTONE 6: Production Episode Quality (P5)            DONE
  RC-0: Batch size 100->300                 DONE (r0_batch_selector.py, 2026-03-09)
  RC-0: Drain loop                          DONE (sequential_adapter.py, 2026-03-09)
  6.1 Wire Ensemble Distance                DONE (composite_distance.py, 20 tests)
  6.2 Thread Purity Correction              DONE (thread_purity.py, 23 tests)
  6.3 Same-Thread Episode Merge             DONE (same_thread_merge.py, 33 tests)
  6.4 Cross-Batch Episode Extension         DONE (cross_batch_extend.py, 31 tests)
  6.5 Metadata Preservation                 DONE (migration 0086, 22 tests)
  6.6 Consolidation Cycle Deduplication     DONE (6.6.1+6.6.2 verified in code, 6.6.3 migration 0087, 52 tests)

MILESTONE 7: REMOVED — Absorbed Into Milestone 9 (2026-03-08)
  (All epics moved to M9. Issue 7.2.0 signal pipeline DONE — inherited by M9.)

MILESTONE 8: Integration Test Suite (P8)                RESEARCH COMPLETE
  8.1 CogQ Metric Framework Port            OPEN (8 metrics, weighted composite)
  8.2 Scenario Evaluation Framework Port    OPEN (8 scenarios, must-link/must-separate)
  8.3 Retrieval Probe Suite                 OPEN (13 multi-dimensional probes)
  8.4 Config Sweep Infrastructure           OPEN (run_matrix, batch_size, thresholds)
  8.5 Research Parity Regression            OPEN (CogQ >= 0.70, 7/8 scenarios)
  8.6 Production Replay Comparison          OPEN (P03 vs research baseline)

MILESTONE 9: Universal Reconciliation + Lifecycle (P6)  RESEARCH COMPLETE [absorbs M7]
  9.1  Two-Tier Reconciliation Engine       OPEN (Tier 1 K1 signals, Tier 2 similarity)
  9.2  AccumulatedEpisode Truth Store       OPEN (importance, evolve chains, versioning)
  9.3  Scene Segmentation (Phase 9)         OPEN (mega-split + micro-absorption)
  9.4  Reconciliation Action Handlers       OPEN (REINFORCE/EXTEND/CREATE/EVOLVE/CONTRADICT)
  9.5  Cross-Batch Episode Lifecycle        OPEN (extend, supersede, contradiction log)
  9.6  Rich Structured Episode Summaries    OPEN [from M7 7.3]
  9.7  Episode Embedding Regeneration       OPEN [from M7 7.4]
  9.8  Episode Lifecycle Observability       OPEN [from M7 7.5]
```

---

## Repo-Verified Baseline

### Verified Done in Code

- `EventAdapter` now exposes `geohash`, `geohash_6`, `activity_type`, `activity_type_ultrabert`, `social_context`, `narrative_thread_id`, affective fields, `sentiment_score`, `salience_score`, and temporal fields in `k0/pipelines/p03/phases/r2_episodic_integrator.py`.
- `P03EventState` includes `temporal_source` in `k0/pipelines/p03/event_state.py`.
- R0 now prefers `conversation_anchor_ms` before `event_time_utc` and `created_at` in `k0/pipelines/p03/phases/r0_batch_selector.py`.
- R2 logs timestamp quality distribution and degraded timestamp ratio in `k0/pipelines/p03/phases/r2_episodic_integrator.py`.
- Dedicated tests exist for EventAdapter passthrough and timestamp-chain behavior in `tests/k0/pipelines/p03/test_r2_event_adapter.py` and `tests/k0/pipelines/p03/test_r2_timestamp_chain.py`.

### Verified Still Open in Code

- `episodic_dbscan.py` still exists and is still imported by R2.
- `episodic_hdbscan.py` still contains DBSCAN fallback logic.
- `CompositeDistance` remains 2D and uses linear temporal normalization.
- `EpisodeSplitter` still uses first-match-wins priority logic.
- `R2EpisodicIntegrator` still computes batch silhouette as average cohesion.
- Contracts still describe R2 as DBSCAN-based and still declare stale capabilities.
- Centroid calculation still uses only `uniform`, `importance`, `recency`, and `hybrid` weighting.
- No multi-centroid representation, episodic coherence metric, or vectorized distance matrix exists.
- No Hebbian/co-occurrence signal is used by R2 clustering distance.

---

## Planning Principles

1. Milestone 1 is baseline, not future scope.
2. Milestone 2 is the next execution target because it removes dead branches and fixes a broken quality loop.
3. Milestone 3 starts only after Milestone 2 contract and cleanup work is stable.
4. Milestone 4 should not proceed until the clustering substrate is real, not fake-silhouette driven.
5. Milestone 5 remains blocked on R2 consuming co-occurrence signals and on the final shape of Milestone 3 distance weighting.

---

## Signal Coverage Target

The completion target for this plan is full R2 coverage of the signal families defined in the
corrected discovery and temp design, not just milestone-level algorithm parity.

| Channel | Signals To Cover In Plan | Primary Target Milestones |
| ------- | ------------------------ | ------------------------- |
| Temporal core | `conversation_anchor_ms`, `temporal_source`, `temporal_links_json`, `temporal_anchor_json`, `temporal_orientation` | M1, M3, M5 |
| Temporal support | `time_of_day_bucket`, `circadian_slot`, `is_weekend`, `extraction_sequence` | M3 |
| Spatial core | `place_id`, `geohash_6`, `location_hierarchy_json` | M1, M3 |
| Spatial support | `location_name`, `location_type`, `spatial_context_json` | M3, M4 |
| Semantic core | `embedding_768`, `activity_type_ultrabert`, `activity_type` | M1, M3 |
| Semantic support | `intent_ultrabert`, `content_text` | M3 |
| Social core | `participants_json`, `participant_relationships_json`, `social_context`, `social_intimacy` | M1, M3 |
| Social support | `num_participants`, `is_solo_event` | M3, M4 |
| Affective core | `affect_valence`, `affect_arousal`, `affect_dominance`, `surprise_level`, `salience_score` | M1, M3, M4 |
| Affective support | `emotions_json`, `salience_band`, `entity_salience_json` | M4 |
| Narrative core | `narrative_thread_id`, `goal_context`, `intent_type` | M1, M3, M4 |
| Narrative support | `narrative_arc_position`, `narrative_is_goal_event` | M4 |
| Cognitive core | `elaboration_depth`, `identity_relevance`, `novelty`, `memory_tier` | M3, M4 |
| Cognitive support | `identity_domains_json`, `source_type` | M4 |
| K1 correction signals | `correction_signal`, `contradiction_signal`, `supersedes_concept`, `correction_source`, `session_context_id` | M7 (7.2.0 DONE) |
| Reliability | `source_reliability`, `activity_type_confidence`, `intent_confidence`, `k1_signal_version` | M5 |

### Out Of Immediate Scope But Tracked

| Signal | Tracking Note |
| ------ | ------------- |
| `spatial_familiarity` | Follow-on enhancement after core R2 signal-complete milestone set. |
| `has_partner_present` / `has_parent_present` | Derivable from relationship signals; track only if direct flags prove operationally useful. |
| `salience_reasons_json` | Optional explanatory signal; do not block core clustering redesign on it. |

---

## MILESTONE 1: Critical Fixes (P0)

**Milestone Status**: COMPLETE

### Epic 1.1: EventAdapter Signal Activation

**Discovery Reference**: Sections 18.4 and 20.2
**Repo Status**: DONE
**Why Status Changed**: The previous plan treated this as future work. The repo now contains the core EventAdapter surface expansion and dedicated tests.

#### Epic 1.1 Verified Completed

| Issue | Status | Verified State |
| ----- | ------ | -------------- |
| 1.1.1 geohash passthrough | DONE | `EventAdapter.geohash` and `EventAdapter.geohash_6` exist. |
| 1.1.2 activity passthrough | DONE | `activity_type` and `activity_type_ultrabert` exist. |
| 1.1.3 social passthrough | DONE | `social_context`, `social_intimacy`, `participants_json` exist. |
| 1.1.4 narrative passthrough | DONE | `narrative_thread_id` and related narrative properties exist. |
| 1.1.5 affective passthrough | DONE | `affect_valence`, `affect_arousal`, `sentiment_score`, `salience_score` exist. |
| 1.1.6 temporal passthrough | DONE | `temporal_orientation`, `temporal_resolved_epoch_ms`, `temporal_anchor_json` exist. |
| 1.1.7 dedicated tests | DONE | `test_r2_event_adapter.py` exists and covers passthrough and protocol integration. |

#### Epic 1.1 Remaining Work

| Issue | Status | Scope |
| ----- | ------ | ----- |
| M1-ADAPTER-01 | OPEN | Verify the EventAdapter property list against the final GAP-002 discovery inventory and remove stale inline comments that still talk as if Epic 1.1 were future work. |
| M1-ADAPTER-02 | OPEN | Update module/class docstrings in `r2_episodic_integrator.py` so they describe current behavior instead of historical issue numbers. |

#### Epic 1.1 Exit Criteria

- EventAdapter documentation matches the actual implemented property surface.
- No milestone plan text treats Epic 1.1 as future work.
- Tests remain green for EventAdapter passthrough.

### Epic 1.2: Timestamp Chain Fix

**Discovery Reference**: Section 16
**Repo Status**: DONE
**Why Status Changed**: All timestamp chain issues resolved. Core mitigation was already in repo; remaining gaps (M08 regex, MW turn_timestamp_ms wiring, residual fallbacks) have been completed.

#### Epic 1.2 Verified Completed

| Issue | Status | Verified State |
| ----- | ------ | -------------- |
| 1.2.1 audit + distinction of chains | DONE | The code and tests distinguish conversation-time vs temporal-resolution fields. |
| 1.2.2 R0 fallback hardening | DONE | R0 prefers `conversation_anchor_ms -> event_time_utc -> created_at -> now()`. |
| 1.2.3 temporal_source on P03EventState | DONE | `temporal_source` exists on `P03EventState`. |
| 1.2.4 timestamp quality observability | DONE | R2 computes `ts_quality` and degraded ratio and logs warnings when degraded. |
| 1.2.5 M08 temporal regex expansion | DONE | 24 patterns in `_TEMPORAL_PATTERNS` including Issue 1.2.5 additions (a few hours ago, an hour ago, a couple of days ago, last month, last year, over the weekend, this afternoon, this evening, today, noon). |
| 1.2.6 timestamp-chain tests | DONE | `test_r2_timestamp_chain.py` exists. |
| M1-TIME-01 MW now_utc proxy | DONE | `assemble_temporal_spatial()` now propagates `payload.timestamp_ms` as `turn_timestamp_ms` into `ExtractionContext`. Data model complete: `ExtractionContext.turn_timestamp_ms`, `MemoryAtom.conversation_anchor_ms`. 3 new tests in `test_turn_timestamp_propagation.py`. |
| M1-TIME-02 residual fallbacks | MITIGATED | R0 fallback chain (`anchor_ms -> event_time_utc -> created_at -> now()`) is correct and observable (warning/error logs). `temporal_source` tracks provenance. Residual low-fidelity paths exist by design for backward compatibility with historical events. |

#### Epic 1.2 Anomalies Resolved

| Anomaly | Severity | Resolution |
| ------- | -------- | ---------- |
| `novelty_score` duplicate definition in P03EventState (L148 default=0.0 and L267 default=1.0) | HIGH | Removed duplicate at L148. Single definition in DEDUPLICATION section with default=0.0. R0 loads P02 value, R3 overwrites with dedup novelty. |
| `narrative_thread_completed` not in R0 SELECT | MEDIUM | FALSE GAP. Field is R2-computed (not a st_hipp_events column). Written to st_epi via migration 0084. Correctly absent from R0 SELECT. |
| `content_hash` dead field on P03EventState | LOW | Annotated as not loaded by R0. Reserved for future exact-dedup. Test fixtures use it but no production path populates it. |

---

## MILESTONE 2: Cleanup & Compliance (P1)

**Milestone Status**: OPEN
**Execution Priority**: NEXT

Milestone 2 is now the primary execution focus. The repo still carries dual clustering branches,
a false quality signal, and contract drift that will undermine any Milestone 3+ work.

### Milestone 2 Operating Goal

Milestone 2 is not only cleanup. It is the substrate-preparation milestone for optimal signal usage
in R2 memory generation. The goal is to remove misleading or dead behavior before we prove, with
real data, which formulas and signal interactions actually improve episode formation.

### Milestone 2 Context Pack

Read these before implementation, research, or POC work begins.

| Priority | Source | Why It Must Be Read |
| -------- | ------ | ------------------- |
| 1 | `docs/pipelines/p03_enhancement_discovery/P03_R2_EPISODIC_INTEGRATION_DISCOVERY.md` | Authoritative deep trace for current R2 architecture, gap inventory, DBSCAN removal scope, HDBSCAN behavior, and formula drift. |
| 2 | `docs/pipelines/p03_enhancement_discovery/temp_r2_design.md` | Authoritative target design for optimal signal usage, formula candidates, channel inventory, and proof targets. |
| 3 | Milestone 1 in this plan | Required to understand what is already baseline and should not be re-planned. |
| 4 | Milestone 3 through Milestone 5 in this plan | Required to ensure Milestone 2 cleanup keeps the future 6D and signal-complete design viable. |
| 5 | Discovery Section 16 | Timestamp chain and temporal correctness context. |
| 6 | Discovery Section 17 | CompositeDistance critique, replacement direction, and adaptive-weight context. |
| 7 | Discovery Section 18 | EpisodeSplitter deep trace and boundary logic context. |
| 8 | Discovery Section 19 | Full DBSCAN removal scope and line-impact summary. |
| 9 | Discovery Section 20 | HDBSCAN deep trace, rescue behavior, and current signal funnel. |
| 10 | Discovery Section 24 | Quality loop critique, fake silhouette failure mode, and replacement direction. |

### Milestone 2 Proof-First Requirement

Before implementation details are locked, create a POC/research track in the style of the existing
`poc/r1_weight_research` directory: small executable experiments, scenario packs, calibration runs,
proxy-label analysis, and result artifacts grounded in real or replayed repository data.

This is not just a loose PoC requirement. Milestone 2 needs a structured research program with
repeatable experiments, benchmark scenarios, replayable datasets, proxy truth definitions,
ablation studies, calibration runs, and decision gates.

### Existing Research Pattern To Reuse

The R1 research pack already demonstrates the right pattern for this repository and should be
treated as the template to copy and adapt for R2.

| Existing Research Asset | What It Proves About The Expected Pattern |
| ----------------------- | ------------------------------------------ |
| `poc/r1_weight_research/run_matrix.py` | Batch-runner over multiple candidate configurations with comparable output metrics |
| `poc/r1_weight_research/scenarios.py` | Hand-crafted validation scenarios with expected outcomes and tolerance bands |
| `poc/r1_weight_research/proxy_labels.py` | Weak-supervision / proxy-ground-truth layer for offline evaluation |
| `poc/r1_weight_research/scorer.py` | Standalone research formula implementation decoupled from production pipeline code |
| `poc/r1_weight_research/results/` | Persisted artifacts that support comparison and go/no-go decisions |

### Milestone 2 Required Research Tracks

| Track | Requirement | Why It Is Needed |
| ----- | ----------- | ---------------- |
| Formula research | Standalone implementations of clustering-quality and cleanup-sensitive formulas outside production code | Lets us falsify bad assumptions before wiring them into R2 |
| Scenario research | Hand-crafted scenario suites covering clean episodes, mixed contexts, contamination, rescue, and edge cases | Ensures changes are judged on memory behavior, not code neatness |
| Replay research | Replayed real or repository-derived event sequences through old and proposed logic | Needed to evaluate actual effect on memory generation |
| Proxy-label research | Weak-supervision or heuristic truth signals for clustering purity / contamination / rescue correctness | We need an evaluation layer even without perfect gold labels |
| Ablation research | Turn signals and formula terms on/off to measure marginal value | Confirms optimal signal usage instead of blindly using everything |
| Calibration research | Threshold and parameter sweeps for rescue, silhouette, and migration-safe defaults | Prevents arbitrary constants from getting promoted into production |
| Regression research | Before/after comparison against current R2 outputs | Required to prove cleanup did not silently degrade clustering |

### Milestone 2 Research Questions Beyond POCs

| Research ID | Question | Expected Research Form |
| ----------- | -------- | ---------------------- |
| M2-RSCH-01 | Which existing signals are actually predictive of better episodic separation and which are just available noise? | Ablation matrix over signal families on replay datasets |
| M2-RSCH-02 | What is the best offline proxy for “good memory generation” before we have richer user feedback loops? | Proxy-label definition note plus validation scenarios |
| M2-RSCH-03 | When does HDBSCAN rescue improve memory coherence and when does it contaminate episodes? | Rescue contamination benchmark with real/replayed sequences |
| M2-RSCH-04 | What sequence sizes make true silhouette practical in the real pipeline? | Performance benchmark with representative sequence sizes |
| M2-RSCH-05 | Which nomenclature and learned-weight migration strategy preserves historical adaptive state safely? | Migration rehearsal and key-translation report |
| M2-RSCH-06 | Which Milestone 3+ formulas need proof before they are allowed into production implementation? | Research gating note tied to Milestone 3 entry criteria |

### Milestone 2 Proof Obligations

These are the questions we must prove with real data before finalizing later formulas and tuning.

| Proof ID | What Must Be Proven | Why It Matters | Suggested POC Shape |
| -------- | ------------------- | -------------- | ------------------- |
| M2-POC-01 | HDBSCAN-only path is behaviorally equivalent or better than the mixed DBSCAN/HDBSCAN substrate on representative R2 scenarios | Justifies full DBSCAN eradication without hidden regression | Replay representative clustered sequences through both paths and compare cluster count, noise rate, rescue rate, and episode purity |
| M2-POC-02 | Average cohesion is not a valid silhouette substitute on real cluster layouts | Justifies replacing the current adaptive loop input | Build scenario matrix with known good/bad cluster layouts and compare fake vs true silhouette divergence |
| M2-POC-03 | Real silhouette on precomputed matrices is computationally feasible for expected sequence sizes | Ensures Milestone 2.2 is viable operationally | Benchmark true silhouette by sequence size and track latency and memory |
| M2-POC-04 | Existing HDBSCAN rescue thresholds do or do not over-rescue cross-context events | Determines whether current rescue behavior is distorting memory generation | Create cross-context contamination scenarios with similar embeddings but different narrative/social/spatial context |
| M2-POC-05 | Current baseline parameter names and learned-weight keys can be migrated without corrupting adaptive state | Prevents silent breakage when removing DBSCAN nomenclature | Migration sandbox over saved learned-weight rows |
| M2-POC-06 | Milestone 2 cleanup preserves the signal surface needed for later optimal-signal R2 design | Ensures cleanup does not block future 6D and gating work | Validate retained interfaces against temp design channel inventory |
| M2-POC-07 | Rescue behavior, cluster counts, and purity remain stable across representative real-data replays after DBSCAN removal | Prevents cleanup from silently changing memory outcomes | Replay harness with before/after cluster comparison |
| M2-POC-08 | True silhouette plus current adjusters does not create oscillatory parameter behavior | Prevents adaptive instability from replacing one bad metric with another | Offline cycle simulation over repeated batches |

### Milestone 2 Research And POC Outputs

| Output | Purpose |
| ------ | ------- |
| Scenario pack | Curated real-data or replay-derived sequences for same-episode, cross-episode, cross-context, and noisy-edge cases |
| Formula benchmark | Fake silhouette vs true silhouette vs quality proxies |
| Cleanup regression report | Before/after comparison for cluster assignments and adaptive metrics |
| Migration checklist | Learned-param rename safety checks and fallback behavior |
| Recommendation note | Clear go/no-go guidance for moving from Milestone 2 into Milestone 3 |
| Ablation report | Signal-family contribution analysis for clustering-quality outcomes |
| Replay harness | Repeatable runner for comparing current vs proposed Milestone 2 behavior |
| Parameter sweep results | Threshold and stability sweeps for silhouette and rescue logic |

### Milestone 2 Research Deliverable Shape

The preferred structure is an R2-specific research pack under `poc`, modeled after `poc/r1_weight_research`.

| Deliverable Type | Suggested Shape |
| ---------------- | --------------- |
| Research scorer / evaluator | Standalone math and evaluation helpers, not production imports |
| Scenario library | Hand-crafted edge cases and representative memory-generation cases |
| Replay runner | Batch runner over saved/replayed real event sequences |
| Proxy labels | Weak truth for purity, contamination, rescue correctness, and quality expectations |
| Calibration runner | Matrix execution over threshold/config combinations |
| Results artifacts | CSV/JSON/Markdown summaries under a dedicated `results/` folder |
| Decision memo | Short summary of what the research proved and what is still uncertain |

### Milestone 2 Research Execution Checklist

This checklist is the operational entry point for Milestone 2 research. Each step must produce
named artifacts and meet explicit success criteria before the next step is considered complete.

1. Establish the R2 research workspace.
  Artifacts:
  `poc/r2_phase_research/`
  `poc/r2_phase_research/results/`
  `poc/r2_phase_research/README.md`
  Success criteria:
  The research pack exists under `poc`, documents scope and commands, and is clearly separated from production code.

2. Define the replay dataset contract.
  Artifacts:
  `poc/r2_phase_research/dataset_contract.md`
  `poc/r2_phase_research/replay_loader.py`
  Success criteria:
  We can load replayable event sequences with the fields needed for current R2 and proposed Milestone 3 signal use, and the contract explicitly states what is real, derived, or missing.

3. Build the scenario library.
  Artifacts:
  `poc/r2_phase_research/scenarios.py`
  `poc/r2_phase_research/scenario_catalog.md`
  Success criteria:
  The suite includes at least clean-episode, cross-context contamination, rescue-edge, temporal-drift, and mixed-signal scenarios, each with expected qualitative outcomes.

4. Define proxy evaluation labels.
  Artifacts:
  `poc/r2_phase_research/proxy_labels.py`
  `poc/r2_phase_research/proxy_label_notes.md`
  Success criteria:
  We have a documented weak-truth scheme for purity, contamination, rescue correctness, and adaptive-loop plausibility that is good enough to compare alternatives offline.

5. Implement the baseline evaluator.
  Artifacts:
  `poc/r2_phase_research/baseline_runner.py`
  `poc/r2_phase_research/results/baseline_metrics.json`
  Success criteria:
  The current Milestone 2 baseline can be replayed end to end and produces stable metrics for cluster count, noise rate, rescue rate, pseudo-purity, and fake-silhouette outputs.

6. Implement the DBSCAN-removal comparison harness.
  Artifacts:
  `poc/r2_phase_research/dbscan_removal_compare.py`
  `poc/r2_phase_research/results/dbscan_removal_compare.csv`
  Success criteria:
  We can compare mixed-path behavior to HDBSCAN-only behavior on the same replay sets, and any drift in cluster assignments is visible and attributable.

7. Implement the silhouette research harness.
  Artifacts:
  `poc/r2_phase_research/silhouette_research.py`
  `poc/r2_phase_research/results/silhouette_comparison.json`
  Success criteria:
  The research output demonstrates, on real or replayed cluster layouts, where average cohesion diverges from true silhouette and whether true silhouette is operationally feasible.

8. Implement rescue contamination research.
  Artifacts:
  `poc/r2_phase_research/rescue_research.py`
  `poc/r2_phase_research/results/rescue_contamination_report.md`
  Success criteria:
  We can identify at least the dominant over-rescue and under-rescue patterns in the current HDBSCAN rescue logic using cross-context scenarios and replay data.

9. Implement parameter and threshold sweeps.
  Artifacts:
  `poc/r2_phase_research/run_matrix.py`
  `poc/r2_phase_research/results/parameter_sweeps.csv`
  Success criteria:
  Rescue thresholds, silhouette settings, and any migration-safe defaults can be swept and ranked by repeatable offline metrics rather than intuition.

10. Run signal-family ablation analysis.
   Artifacts:
   `poc/r2_phase_research/ablation.py`
   `poc/r2_phase_research/results/ablation_report.md`
   Success criteria:
   The report identifies which currently available signals materially improve or degrade memory-generation proxies, so Milestone 3 uses signals optimally instead of indiscriminately.

11. Rehearse learned-parameter migration.
   Artifacts:
   `poc/r2_phase_research/migration_rehearsal.py`
   `poc/r2_phase_research/results/migration_rehearsal.json`
   Success criteria:
   We can rename DBSCAN-era learned-weight keys to neutral clustering keys without losing history or producing ambiguous fallback behavior.

12. Produce the Milestone 2 decision memo.
   Artifacts:
   `poc/r2_phase_research/results/m2_decision_memo.md`
   Success criteria:
   The memo clearly states what was proven, what remains uncertain, whether Milestone 2 implementation can proceed, and which Milestone 3 formulas are approved, blocked, or require more research.

### Milestone 2 Research Exit Gate

Milestone 2 research is complete only when all of the following are true.

| Gate | Requirement |
| ---- | ----------- |
| G1 | Replay harness and scenario library exist and are runnable |
| G2 | Baseline, DBSCAN-removal, silhouette, rescue, and ablation artifacts are generated |
| G3 | Success criteria are met or explicitly documented as failed with rationale |
| G4 | Decision memo identifies the approved Milestone 2 implementation path |
| G5 | Research outputs are sufficient to justify moving into production cleanup and later formula work |

### Epic 2.1: DBSCAN Full Removal

**Discovery Reference**: Section 19
**Repo Status**: OPEN

#### Epic 2.1 Verified Current State

| Area | Status | Verified State |
| ----- | ------ | -------------- |
| DBSCAN production file | OPEN | `k0/modules/consolidation/algorithms/episodic_dbscan.py` still exists. |
| R2 imports | OPEN | `r2_episodic_integrator.py` still imports `EpisodicDBSCAN` and `ClusteringResult`. |
| Config toggle | OPEN | `R2Config.use_hdbscan` still exists. |
| Integrator branching | OPEN | `_initialize_components` still chooses DBSCAN or HDBSCAN by config. |
| HDBSCAN fallback | OPEN | `episodic_hdbscan.py` still has `HDBSCAN_AVAILABLE`, `_use_hdbscan`, and `_run_dbscan_fallback()`. |
| Tests | OPEN | DBSCAN-specific tests still exist and integration tests still instantiate `EpisodicDBSCAN`. |
| Diagrams/docs | OPEN | DBSCAN references remain in architecture diagrams and contracts. |

#### Milestone 2.1 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 2.1.1 Rename `DBSCANParams` to neutral name | OPEN | Rename to `DistanceParams` or `ClusteringDistanceParams` before deletion work. |
| 2.1.2 Remove DBSCAN from R2 integrator | OPEN | Delete imports, config toggle, union types, and conditional branch. |
| 2.1.3 Remove DBSCAN fallback from HDBSCAN | OPEN | Make `hdbscan` mandatory at module import time. |
| 2.1.4 Purge DBSCAN exports/comments | OPEN | Update `__init__.py` files and comments. |
| 2.1.5 Delete DBSCAN production/test files | OPEN | Remove `episodic_dbscan.py` and DBSCAN-only tests after all imports are gone. |
| 2.1.6 Update contracts/diagrams | OPEN | Replace DBSCAN language with HDBSCAN language everywhere it still drives understanding. |
| 2.1.7 Rename learned param keys | OPEN | Move from `dbscan_*` keys to neutral clustering keys. |
| 2.1.8 Run cleanup validation | OPEN | Final grep/import/test pass after eradication. |

#### Epic 2.1 Execution Order

1. Neutral rename of DBSCAN-derived parameter names.
2. R2 integrator cleanup.
3. HDBSCAN fallback removal.
4. File deletion and export cleanup.
5. Contract/diagram updates.
6. Migration/test validation.

#### Epic 2.1 Issue Execution Checklist

##### Issue 2.1.1 Rename `DBSCANParams` to neutral name

| Item | Detail |
| ---- | ------ |
| Goal | Remove algorithm-specific naming from the shared distance configuration before deleting the legacy algorithm path. |
| Read | `k0/modules/consolidation/algorithms/composite_distance.py` `DBSCANParams`; `k0/modules/consolidation/algorithms/episodic_hdbscan.py` `to_dbscan_params()`; `k0/modules/consolidation/algorithms/__init__.py` exports; `tests/k0/pipelines/p03/test_r2_composite_distance.py`. |
| Change | Introduce a neutral type such as `ClusteringDistanceParams`, update `CompositeDistance` and HDBSCAN to consume it, and leave a short compatibility alias only if required for staged migration. |
| Core idea | The distance metric belongs to the clustering substrate, not to DBSCAN. The shared config object must stop encoding the removed algorithm in its name. |
| Tests | Rewrite `test_r2_composite_distance.py` to assert neutral-param defaults, validation, and serialization; update any integration tests importing the old class name. |
| Success criteria | Production imports no longer depend on `DBSCANParams`; any temporary alias is limited to migration scope and scheduled for removal within Epic 2.1. |

**Codebase Reality** (verified 2026-03-07):

`DBSCANParams` is a frozen dataclass at `k0/modules/consolidation/algorithms/composite_distance.py` L57-116 with 4 fields: `eps=0.15`, `min_samples=2`, `temporal_weight=0.3`, `max_temporal_gap_hours=4.0`. It exposes computed properties `max_temporal_gap_ms` (L81), `semantic_weight` (L86), and methods `validate()` (L90), `to_dict()` (L105), `from_dict()` (L113).

Consumers:

- `episodic_hdbscan.py` L38 imports `DBSCANParams`; `HDBSCANParams.to_dbscan_params()` at L107 converts HDBSCAN config to `DBSCANParams` for `CompositeDistance` compatibility.
- `r2_episodic_integrator.py` L37-55 imports `DBSCANParams`; `_get_dbscan_params()` at L806 constructs it from config/learned-weights.
- `algorithms/__init__.py` L85-86 exports `DBSCANParams` in `__all__` (L362-379).
- `test_r2_composite_distance.py` has `TestDBSCANParams` class (L71, 7 methods) plus ~20 `DBSCANParams()` usages across `CompositeDistance` tests.
- `test_r2_integration.py` L41 imports `DBSCANParams` with 14 instantiations.

**Research Evidence**:

R2 research (`poc/r2_phase_research/`) proved the entire `DBSCANParams` contract is misaligned with the optimal distance approach. Research Section 2.2 (`R2_RESEARCH_FINAL.md`) established a 3D confidence-weighted ensemble (semantic=0.45, temporal=0.25, narrative=0.30) that replaces the 2-field `temporal_weight`/`semantic_weight` split. The `eps`/`min_samples` fields move to HDBSCAN-specific config. Go/No-Go memo (Section 9.2): **Epic 2.1 = GO**. POC-05 (`poc_05_dbscan_key_inventory.json`): 9 code references to DBSCAN-era param keys across 4 files.

**Implementation Detail**:

1. Create `ClusteringDistanceParams` frozen dataclass at L57 in `composite_distance.py` preserving `eps`, `min_samples`, `temporal_weight`, `max_temporal_gap_hours`, `semantic_weight` (computed), `max_temporal_gap_ms` (computed), `validate()`, `to_dict()`, `from_dict()`.
2. Add `DBSCANParams = ClusteringDistanceParams` alias immediately below for staged migration.
3. Update `HDBSCANParams.to_dbscan_params()` at L107 to return `ClusteringDistanceParams` and rename method to `to_distance_params()`.
4. Update `algorithms/__init__.py` L85-86: export `ClusteringDistanceParams`; keep `DBSCANParams` in exports with deprecation comment.
5. Rename `TestDBSCANParams` class in `test_r2_composite_distance.py` to `TestClusteringDistanceParams`.
6. Mark alias for removal in Issue 2.1.5 (after all DBSCAN imports are gone).

##### Issue 2.1.2 Remove DBSCAN from R2 integrator

| Item | Detail |
| ---- | ------ |
| Goal | Collapse R2 orchestration to a single HDBSCAN path. |
| Read | `k0/pipelines/p03/phases/r2_episodic_integrator.py` module header, `R2Config`, `_initialize_components`, `_get_dbscan_params`, and any methods typed with `DBSCANParams` or `EpisodicDBSCAN`. |
| Change | Remove `EpisodicDBSCAN`, `ClusteringResult`, `DBSCANParams`, `use_hdbscan`, the `Union[...]` clusterer type, and the DBSCAN-specific learned-param fetch helper; keep one initialization path with HDBSCAN plus neutral distance params. |
| Core idea | The main phase runner should describe one real algorithm path. Keeping a dead branch in the orchestrator guarantees future drift. |
| Tests | Update `tests/k0/pipelines/p03/test_r2_integration.py` so clustering flows through the surviving HDBSCAN path or through the integrator facade rather than instantiating DBSCAN directly. |
| Success criteria | The integrator module docstring, imports, config fields, and initialization flow contain no DBSCAN-specific language or branching. |

**Codebase Reality** (verified 2026-03-07):

`r2_episodic_integrator.py` (2134 lines) imports at L37-55:

- `ClusteringResult` (from `episodic_dbscan.py` L73)
- `DBSCANParams` (from `composite_distance.py` L57)
- `EpisodicDBSCAN` (from `episodic_dbscan.py` L100)
- `EpisodicHDBSCAN` (from `episodic_hdbscan.py` L218)
- `HDBSCANClusteringResult` (from `episodic_hdbscan.py` L159)
- `HDBSCANParams` (from `episodic_hdbscan.py` L53)

`R2Config` at L72 has `use_hdbscan: bool = True` at L94. HDBSCAN is already the default; DBSCAN path is dead code.

`_initialize_components` at L768 branches: if `self.config.use_hdbscan` creates `EpisodicHDBSCAN(params=hdbscan_params)` at L781, else creates `EpisodicDBSCAN(params=dbscan_params)` at L793 with `eps=0.07`.

`_get_dbscan_params` at L806 constructs `DBSCANParams` from config and `ctx.syscalls.get_learned_param("dbscan_eps")` and `"dbscan_min_samples"`.

`test_r2_integration.py` L39-44 imports `DBSCANParams` (L41) and `EpisodicDBSCAN` (L43) with 14 `DBSCANParams()` and 8 `EpisodicDBSCAN()` instantiations.

**Research Evidence**:

Production baseline comparison (R2_RESEARCH_FINAL.md Section 7): DBSCAN+CompositeDistance produces 160 clusters with 972 noise (71.5%), all must_link=0.00. Research HDBSCAN+ensemble: 260 clusters, 2 noise (0.15%), all must_link=1.00, 7/8 scenarios perfect. Go/No-Go Section 9.2: "The DBSCAN code path in r2_episodic_integrator.py is dead code. HDBSCAN with the ensemble distance produces strictly better results." POC-01/07 (Section 8.4): SUPERSEDED -- research pipeline strictly better on every dimension.

**Implementation Detail**:

1. Remove from imports (L37-55): `EpisodicDBSCAN`, `ClusteringResult`, and the `DBSCANParams` import (use `ClusteringDistanceParams` from 2.1.1).
2. Remove `R2Config.use_hdbscan` field at L94.
3. Collapse `_initialize_components` (L768) to single HDBSCAN path: delete the `else` branch at L793 and the `if self.config.use_hdbscan` conditional. Keep only `EpisodicHDBSCAN(params=hdbscan_params)`.
4. Rename `_get_dbscan_params` (L806) to `_get_distance_params`, return `ClusteringDistanceParams`.
5. Remove any `Union[EpisodicDBSCAN, EpisodicHDBSCAN]` type annotations.
6. Update `test_r2_integration.py`: replace 14 `DBSCANParams()` with `ClusteringDistanceParams()`, replace 8 `EpisodicDBSCAN()` with `EpisodicHDBSCAN()`, remove DBSCAN-only test branches.
7. Net code reduction: ~30-50 lines from integrator, ~80-100 lines from tests.

##### Issue 2.1.3 Remove DBSCAN fallback from HDBSCAN

| Item | Detail |
| ---- | ------ |
| Goal | Make HDBSCAN a mandatory dependency for the production clustering path. |
| Read | `k0/modules/consolidation/algorithms/episodic_hdbscan.py` import block, `HDBSCAN_AVAILABLE`, `EpisodicHDBSCAN.__init__`, `cluster()`, and `_run_dbscan_fallback()`. |
| Change | Remove the optional-import fallback, delete `_use_hdbscan` state and `_run_dbscan_fallback()`, and fail fast if HDBSCAN cannot be imported in environments that claim to run R2. |
| Core idea | A fallback to the deleted algorithm path defeats the entire cleanup milestone and makes contracts impossible to keep honest. |
| Tests | Replace any fallback-oriented tests with environment/integration checks that assert HDBSCAN availability is required in supported execution environments. |
| Success criteria | `episodic_hdbscan.py` no longer imports sklearn DBSCAN, no longer exposes fallback behavior, and no longer routes through DBSCAN-style compatibility methods. |

**Codebase Reality** (verified 2026-03-07):

`episodic_hdbscan.py` (657 lines) has a try/except import block at L28-36:

```python
try:
    import hdbscan
    HDBSCAN_AVAILABLE = True       # L32
except ImportError:
    HDBSCAN_AVAILABLE = False      # L34
    hdbscan = None
```

Plus `from sklearn.cluster import DBSCAN` at L37 for fallback.

`EpisodicHDBSCAN.__init__` at L236 sets `self._use_hdbscan = HDBSCAN_AVAILABLE` at L249. If False, logs warning.

`cluster()` at L258 branches at L293: `if self._use_hdbscan` calls `_run_hdbscan(distances)`, else calls `_run_dbscan_fallback(distances)`.

`_run_dbscan_fallback()` at L362 uses `sklearn.cluster.DBSCAN` with `metric="precomputed"`, simulates probabilities (1.0/0.0) and outlier scores via `_compute_outlier_scores_fallback()`.

`HDBSCANParams.to_dbscan_params()` at L107 is a bridge method returning `DBSCANParams` for `CompositeDistance` compatibility.

**Research Evidence**:

All 68 experiments (Phases 1-3), all POCs, and all M4/M5 research used HDBSCAN directly -- DBSCAN was never invoked. POC-08 (`poc_08_oscillation_simulation.json`): EpsAdjuster loop converges with HDBSCAN silhouette feedback (0 direction changes in 10 batches, eps=0.2500->0.2540). `hdbscan` package is listed in `requirements.txt` and `pyproject.toml` as a required dependency, not optional.

**Implementation Detail**:

1. Replace try/except block (L28-36) with direct `import hdbscan` (fail fast if not installed).
2. Delete `HDBSCAN_AVAILABLE` module constant (L32/34).
3. Delete `from sklearn.cluster import DBSCAN` at L37.
4. Remove `self._use_hdbscan` assignment from `__init__` at L249.
5. In `cluster()` at L293: remove `if` conditional, call `_run_hdbscan(distances)` unconditionally.
6. Delete `_run_dbscan_fallback()` method (L362+) and `_compute_outlier_scores_fallback()`.
7. Rename `HDBSCANParams.to_dbscan_params()` (L107) to `to_distance_params()`, return `ClusteringDistanceParams`.
8. Net code reduction: ~100-120 lines (fallback method + bridge code + conditional logic).

##### Issue 2.1.4 Purge DBSCAN exports and comments

| Item | Detail |
| ---- | ------ |
| Goal | Remove DBSCAN from public algorithm surfaces and module documentation. |
| Read | `k0/modules/consolidation/algorithms/__init__.py`; `k0/modules/consolidation/__init__.py`; `k0/pipelines/p03/phases/r2_episodic_integrator.py` module header; `architecture_diagrams/k0/p03_file_dependencies.mmd`; `architecture_diagrams/k0/p03_code_structure.mmd`. |
| Change | Update public exports, package comments, Mermaid diagram labels, and any internal notes that still present DBSCAN as an active R2 algorithm. |
| Core idea | Public import surfaces and diagrams are part of the implementation contract. If they lie, the code will drift back toward the wrong design. |
| Tests | No direct unit tests, but final grep validation must include code, diagrams, and package exports. |
| Success criteria | A repository search shows DBSCAN-era references only in historical notes, explicitly deprecated migration context, or intentionally preserved discovery docs. |

**Codebase Reality** (verified 2026-03-07):

`algorithms/__init__.py` L85-86: `from .composite_distance import CompositeDistance, DBSCANParams`. L153-154: `from .episodic_dbscan import ClusteringResult, EpisodicDBSCAN`. `__all__` at L362-379 includes `"CompositeDistance"`, `"DBSCANParams"`, `"EpisodicDBSCAN"`, `"ClusteringResult"`.

`r2_episodic_integrator.py` module header (first ~35 lines) describes dual-algorithm architecture. Comments throughout reference DBSCAN as the clustering algorithm.

Mermaid diagrams in `architecture_diagrams/k0/` include `p03_file_dependencies.mmd` and `p03_code_structure.mmd` with DBSCAN nodes and edges.

**Research Evidence**:

Go/No-Go Section 9.2: "Removing the DBSCAN branch simplifies r2_episodic_integrator.py without breaking the adaptive loop." Production baseline (Section 7): DBSCAN path has never been the production default (R2Config.use_hdbscan=True). All research runs exclusively used HDBSCAN. No research artifact references DBSCAN as viable.

**Implementation Detail**:

1. `algorithms/__init__.py`: Remove L153-154 (`from .episodic_dbscan import ...`). Remove `"EpisodicDBSCAN"` and `"ClusteringResult"` from `__all__`. Replace `"DBSCANParams"` with `"ClusteringDistanceParams"` in `__all__`. Update L85-86 to `from .composite_distance import CompositeDistance, ClusteringDistanceParams`.
2. `r2_episodic_integrator.py` module header: Rewrite to describe single HDBSCAN+ensemble path.
3. Mermaid diagrams: Remove `episodic_dbscan.py` nodes and DBSCAN edges from `p03_file_dependencies.mmd` and `p03_code_structure.mmd`. Update clustering algorithm labels to HDBSCAN.
4. Grep targets post-cleanup: `EpisodicDBSCAN`, `ClusteringResult` (from dbscan), `DBSCANParams`, `use_hdbscan`, `_run_dbscan_fallback`, `HDBSCAN_AVAILABLE`.

##### Issue 2.1.5 Delete DBSCAN production and test files

| Item | Detail |
| ---- | ------ |
| Goal | Remove the dead implementation and the tests that only protect it. |
| Read | `k0/modules/consolidation/algorithms/episodic_dbscan.py`; `tests/k0/pipelines/p03/test_r2_episodic_dbscan.py`; DBSCAN-instantiating sections in `tests/k0/pipelines/p03/test_r2_integration.py`. |
| Change | Delete the production file once all imports are gone, then delete or rewrite the DBSCAN-specific test module so only behavior-level coverage survives. |
| Core idea | Dead implementations attract accidental reuse. If the file remains, future work will import it. |
| Tests | Preserve behavior coverage for empty input, low-density noise, temporal separation, cluster stats, and event mutation, but express those checks through HDBSCAN or higher-level R2 behavior tests. |
| Success criteria | The repository no longer contains `episodic_dbscan.py` or a test module named for DBSCAN; equivalent behavior remains covered elsewhere where still relevant. |

**Codebase Reality** (verified 2026-03-07):

`episodic_dbscan.py` (459 lines) contains:

- `ClusterableEvent` (Protocol, L38) -- duplicated in `episodic_hdbscan.py` L128
- `ClusteringResult` (dataclass, L73) -- result container with clusters, labels, counts
- `EpisodicDBSCAN` (L100) -- wraps `sklearn.cluster.DBSCAN`
- Methods: `cluster()` L150, `cluster_and_update_events()` L232, `_create_cluster()` L291, `_compute_cohesion()` L343, `_create_all_noise_result()` L391

`test_r2_episodic_dbscan.py` contains classes `TestEpisodicDBSCANBasic` and `TestEpisodicDBSCANClustering` covering empty input, low-density, temporal separation, cohesion computation, and event mutation.

`test_r2_integration.py` L43 imports `EpisodicDBSCAN` with 8 direct instantiations scattered across integration test methods.

**Research Evidence**:

POC-01/07 (R2_RESEARCH_FINAL.md Section 8.4): "POC-01 (basic DBSCAN comparison) and POC-07 (enhanced production DBSCAN baseline) are fully covered by the production baseline comparison in Section 7." Result: Production DBSCAN path produces 972/1360 noise events (71.5%), all must_link=0.00. HDBSCAN path: 2 noise events (0.15%), all must_link=1.00. Research never invoked `EpisodicDBSCAN` during any of 68 experiments.

**Implementation Detail**:

1. Delete `k0/modules/consolidation/algorithms/episodic_dbscan.py` (459 lines removed).
2. Delete `tests/k0/pipelines/p03/test_r2_episodic_dbscan.py`.
3. Remove `DBSCANParams` alias (introduced in 2.1.1) from `composite_distance.py` now that all consumers migrated.
4. Behavioral tests to preserve via HDBSCAN path: empty input (should return empty clusters), single-event batch (should return 1-event cluster or noise), cohesion computation (now covered by `EpisodicHDBSCAN._compute_cohesion()`). Check if `test_r2_integration.py` already covers these scenarios through HDBSCAN.
5. `ClusterableEvent` protocol: keep only the copy in `episodic_hdbscan.py` (L128). If any external consumer references the `episodic_dbscan` version, update its import.

##### Issue 2.1.6 Update contracts and diagrams

| Item | Detail |
| ---- | ------ |
| Goal | Bring the documented R2 algorithm surface into sync with the cleaned code. |
| Read | `k0/contracts/pipelines/p03_consolidation.v1.yaml`; `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml`; `k0/contracts/capabilities/consolidation.v1.yaml`; `architecture_diagrams/k0/p03_file_dependencies.mmd`; `architecture_diagrams/k0/p03_code_structure.mmd`. |
| Change | Replace DBSCAN language with HDBSCAN or neutral clustering-distance language, and remove fallback narratives that no longer exist after Issues 2.1.2 and 2.1.3. |
| Core idea | Code cleanup without contract cleanup guarantees a second cleanup later. The docs need to become truthful in the same milestone. |
| Tests | Contract/code audit and grep validation; if diagram checks exist elsewhere in the repo, include them in the validation pass. |
| Success criteria | Pipeline, module, capability, and diagram descriptions all describe one HDBSCAN-based R2 path and no longer promise DBSCAN behavior. |

**Codebase Reality** (verified 2026-03-07):

`p03_consolidation.v1.yaml` R2 stage block (L105-125):

```yaml
- id: stage_20_episodic_cluster
  module: consolidation.episodic_clusterer:v1
  description: |
    R2 - Episodic clustering using DBSCAN on 768-dim embeddings.
  config:
    algorithm: DBSCAN
    eps: 0.3
    min_samples: 3
    metric: cosine
    use_cooccurrence_boost: true
    cooccurrence_weight: 0.2
```

Contract says `eps: 0.3` but code defaults to `0.15` (DBSCANParams) or `0.07` (r2_episodic_integrator). Contract says `min_samples: 3` but code defaults to `2`. Contract says `metric: cosine` but code uses `precomputed` (HDBSCAN on ensemble distance matrix). Contract says `use_cooccurrence_boost: true` but R2 does not consume co-occurrence data.

`consolidation.episodic_clusterer.v1.yaml`: algorithm description says "DBSCAN (Density-Based Spatial Clustering)", lists `eps: 0.3`, `min_samples: 3`, `metric: cosine`. Side effects include `read:st_cooccurrence` (R2 does not use this). Co-occurrence Boost section describes Hebbian boost that is not wired.

`consolidation.v1.yaml` capability: `cluster_episodes` description = "Cluster events into episodes using DBSCAN on 768-dim embeddings".

**Research Evidence**:

Go/No-Go Section 9.4 recommends DEFER contract reconciliation to post-ensemble-distance integration. However, DBSCAN algorithm references are demonstrably false NOW and should be updated as part of the DBSCAN removal epic. The research-proven config: HDBSCAN with min_cluster_size=2, min_samples=1, cluster_selection_method=leaf, metric=precomputed, 3D ensemble distance (semantic=0.45, temporal=0.25, narrative=0.30). Co-occurrence boost: research (M5-RSCH-01) proved ADOPT at scale=0.10, cap=0.05 but via participant co-occurrence at distance level, not via `st_cooccurrence` table read.

**Implementation Detail**:

1. `p03_consolidation.v1.yaml` L105-125: Update `algorithm: HDBSCAN`, `eps: 0.15` (current default), `min_samples: 2` (current default), `metric: precomputed`. Remove `use_cooccurrence_boost` and `cooccurrence_weight` (or mark as future/M5). Update description to "HDBSCAN on precomputed composite distance matrix".
2. `consolidation.episodic_clusterer.v1.yaml`: Replace "DBSCAN (Density-Based Spatial Clustering)" with "HDBSCAN on precomputed ensemble distance". Update eps/min_samples/metric. Remove `read:st_cooccurrence` from side_effects (R2 does not read this table). Remove or flag co-occurrence boost section.
3. `consolidation.v1.yaml`: Change `cluster_episodes` description to "Cluster events into episodes using HDBSCAN on precomputed ensemble distance matrices".
4. Defer precision config updates (exact eps, ensemble weights) to Epic 2.3 when full contract reconciliation runs after ensemble distance lands. This issue handles only the blatantly false DBSCAN claims.

##### Issue 2.1.7 Rename learned param keys

| Item | Detail |
| ---- | ------ |
| Goal | Remove DBSCAN naming from adaptive parameter persistence. |
| Read | `k0/pipelines/p03/phases/r2_episodic_integrator.py` learned-param read/write calls; `k0/modules/consolidation/algorithms/eps_adjuster.py`; `k0/modules/consolidation/algorithms/min_samples_adjuster.py`. |
| Change | Rename `dbscan_eps` and `dbscan_min_samples` to neutral keys such as `clustering_eps` and `clustering_min_samples`, then add a bounded migration or backward-compatible read path during rollout. |
| Core idea | Persistence keys are part of the operational API. If they keep the old algorithm name, the system stays semantically stale even after code cleanup. |
| Tests | Add migration-path tests for read-old/write-new behavior or explicit one-time migration behavior; verify adjusters still persist and reload learned values correctly. |
| Success criteria | New writes use neutral keys, old rows are either migrated or intentionally read for backward compatibility, and no new code writes `dbscan_*` keys. |

**Codebase Reality** (verified 2026-03-07):

POC-05 inventory (`poc_05_dbscan_key_inventory.json`): 2 param keys, 9 total code references across 4 files:

| param_key | File | Occurrences |
| --------- | ---- | ----------- |
| `dbscan_eps` | `eps_adjuster.py` | 2 (read + write via `get_learned_param`/`set_learned_param`) |
| `dbscan_eps` | `r2_episodic_integrator.py` | 2 (read in `_get_dbscan_params`, logging) |
| `dbscan_min_samples` | `min_samples_adjuster.py` | 2 (read + write) |
| `dbscan_min_samples` | `r2_episodic_integrator.py` | 2 (read in `_get_dbscan_params`, logging) |

Plus 3 documentation references in `M4_EXECUTION.md`, P03 discovery doc, and this plan.

Database: `st_learned_weights` table stores these as `param_key` values. Production rows may exist with `dbscan_eps` and `dbscan_min_samples` keys.

**Research Evidence**:

POC-05 (R2_RESEARCH_FINAL.md Section 8.3): "Rename is cosmetic -- `dbscan_eps` and `dbscan_min_samples` work correctly as keys regardless of the algorithm name. A rename requires a database data migration (`UPDATE st_learned_weights SET param_key=...`) which adds risk with no functional benefit." Go/No-Go Section 9.4 originally recommended DEFER. However, since DBSCAN removal makes the keys semantically false, do the rename as part of the cleanup to avoid permanent semantic drift.

POC-08 (`poc_08_oscillation_simulation.json`): EpsAdjuster with HDBSCAN feedback is stable: eps 0.2500->0.2540, 0 direction changes, converged=True. Key rename does not affect adjuster math.

**Implementation Detail**:

1. In `eps_adjuster.py`: Change `"dbscan_eps"` string literals to `"clustering_eps"` (2 occurrences: read and write).
2. In `min_samples_adjuster.py`: Change `"dbscan_min_samples"` to `"clustering_min_samples"` (2 occurrences).
3. In `r2_episodic_integrator.py` (renamed `_get_distance_params` from 2.1.2): Change `"dbscan_eps"` and `"dbscan_min_samples"` reads to new key names (4 occurrences).
4. Backward-compatible read: In `_get_distance_params`, first try `get_learned_param("clustering_eps")`, then fall back to `get_learned_param("dbscan_eps")`. Same for min_samples. Write always uses new key. This handles existing production rows without a database migration.
5. Add Alembic migration (optional): `UPDATE st_learned_weights SET param_key = 'clustering_eps' WHERE param_key = 'dbscan_eps'` and equivalent for min_samples. This is a one-row UPDATE per key -- low risk.
6. Update doc references in M4_EXECUTION.md and P03 discovery doc.

##### Issue 2.1.8 Run cleanup validation

| Item | Detail |
| ---- | ------ |
| Goal | Prove the repository no longer contains active DBSCAN dependencies in R2. |
| Read | Final state of all files touched in Issues 2.1.1 through 2.1.7 plus the remaining R2 test suite. |
| Change | Run focused tests, grep validation, and import-surface verification after cleanup is complete. |
| Core idea | DBSCAN removal is only done when the remaining code, tests, and contracts agree there is one clustering path. |
| Tests | Run the R2 test files under `tests/k0/pipelines/p03/`, then perform repo-wide searches for `EpisodicDBSCAN`, `DBSCANParams`, `use_hdbscan`, `dbscan_eps`, and `dbscan_min_samples`. |
| Success criteria | Tests pass, repository searches show no active DBSCAN-era identifiers in production code, and the Milestone 2 contract documents match the post-cleanup implementation. |

**Codebase Reality** (verified 2026-03-07):

Current grep targets that should yield ZERO production hits after cleanup:

| Pattern | Current Hits (production) | Expected After Cleanup |
| ------- | ------------------------- | ---------------------- |
| `EpisodicDBSCAN` | `episodic_dbscan.py`, `r2_episodic_integrator.py`, `algorithms/__init__.py`, `test_r2_episodic_dbscan.py`, `test_r2_integration.py` | 0 production, 0 test (discovery docs OK) |
| `DBSCANParams` | `composite_distance.py`, `episodic_hdbscan.py`, `r2_episodic_integrator.py`, `algorithms/__init__.py`, `test_r2_composite_distance.py`, `test_r2_integration.py` | 0 production, 0 test |
| `use_hdbscan` | `r2_episodic_integrator.py` (`R2Config.use_hdbscan`) | 0 |
| `HDBSCAN_AVAILABLE` | `episodic_hdbscan.py` | 0 |
| `_run_dbscan_fallback` | `episodic_hdbscan.py` | 0 |
| `dbscan_eps` | `eps_adjuster.py`, `r2_episodic_integrator.py` | 0 (migrated to `clustering_eps`) |
| `dbscan_min_samples` | `min_samples_adjuster.py`, `r2_episodic_integrator.py` | 0 (migrated to `clustering_min_samples`) |
| `from sklearn.cluster import DBSCAN` | `episodic_dbscan.py`, `episodic_hdbscan.py` | 0 |

Test files under `tests/k0/pipelines/p03/`: 17 test files. After cleanup, run full suite to ensure no import breakage or missing class references.

**Research Evidence**:

POC-05 (`poc_05_dbscan_key_inventory.json`): Complete inventory of all 9 code + 3 doc references. This inventory is the checklist for validation. Go/No-Go Section 9.2: Epic 2.1 = GO with "high confidence". All evidence from 68 experiments + 8 POCs confirms HDBSCAN-only path is strictly superior.

**Implementation Detail**:

1. Run `pytest tests/k0/pipelines/p03/ -x -q` to verify all R2 tests pass after issues 2.1.1-2.1.7.
2. Run `grep -rn "EpisodicDBSCAN\|DBSCANParams\|use_hdbscan\|HDBSCAN_AVAILABLE\|_run_dbscan_fallback\|dbscan_eps\|dbscan_min_samples" k0/ tests/` excluding `*.pyc`, `__pycache__`, and discovery docs.
3. Run `python -c "from k0.modules.consolidation.algorithms import ClusteringDistanceParams, EpisodicHDBSCAN"` to verify clean import surface.
4. Verify `episodic_dbscan.py` no longer exists on filesystem.
5. Verify contracts (`p03_consolidation.v1.yaml`, `consolidation.episodic_clusterer.v1.yaml`, `consolidation.v1.yaml`) contain no DBSCAN algorithm references.
6. Run governance sync: `python -m governance.k0.scripts.sync --report` to detect architecture drift.

#### Epic 2.1 Implementation Context

| Read First | Why |
| ---------- | --- |
| Discovery Section 19 | Full removal scope, line-impact estimate, and dependency chain. |
| Discovery Section 20 | Confirms what the surviving HDBSCAN path actually needs. |
| Milestone 3 in this plan | Ensures the rename and cleanup support future 6D work rather than baking DBSCAN language deeper. |

#### Epic 2.1 Verified Read Set

| File / Symbol | What To Extract |
| ------------- | --------------- |
| `k0/pipelines/p03/phases/r2_episodic_integrator.py` module header, `R2Config`, `_initialize_components`, `_get_dbscan_params` | Confirm the remaining DBSCAN language, config surface, and two-path clusterer initialization. |
| `k0/modules/consolidation/algorithms/episodic_hdbscan.py` `HDBSCANParams.to_dbscan_params`, `EpisodicHDBSCAN.__init__`, `_run_dbscan_fallback` | Confirm the exact DBSCAN compatibility seam that still survives inside the HDBSCAN path. |
| `k0/modules/consolidation/algorithms/composite_distance.py` `DBSCANParams` | Identify the neutral rename entry point before deleting the legacy file. |
| `tests/k0/pipelines/p03/test_r2_episodic_dbscan.py` | Inventory all behavior currently pinned to the dead DBSCAN production path. |
| `tests/k0/pipelines/p03/test_r2_integration.py` and `tests/k0/pipelines/p03/test_r2_composite_distance.py` | Identify integration and parameter tests that still encode DBSCAN names and constructors. |

#### Epic 2.1 Codebase Change Map

| File / Area | What Changes | Core Idea |
| ----------- | ------------ | --------- |
| `k0/modules/consolidation/algorithms/composite_distance.py` | Rename `DBSCANParams` to neutral clustering-distance params and keep only distance semantics there | Remove DBSCAN-era naming without changing the distance math yet |
| `k0/modules/consolidation/algorithms/episodic_hdbscan.py` | Replace `to_dbscan_params()` and DBSCAN fallback plumbing with direct neutral distance params | HDBSCAN should depend on a distance metric, not on a legacy algorithm shim |
| `k0/pipelines/p03/phases/r2_episodic_integrator.py` | Remove `EpisodicDBSCAN`, `DBSCANParams`, `use_hdbscan`, `_get_dbscan_params`, and the union-typed clusterer branch | Reduce R2 orchestration to a single production algorithm path |
| `k0/modules/consolidation/algorithms/episodic_dbscan.py` | Delete after all imports and exports are removed | Remove the dead production path completely |
| `k0/modules/consolidation/algorithms/__init__.py` and any R2 export surfaces | Purge DBSCAN exports and replace renamed param exports | Prevent accidental reintroduction through public imports |
| `tests/k0/pipelines/p03/test_r2_episodic_dbscan.py` | Delete or convert to HDBSCAN regression scenarios that protect the intended behavior rather than the dead class name | Remove dead-path tests instead of preserving obsolete implementation detail |
| `tests/k0/pipelines/p03/test_r2_integration.py` and `tests/k0/pipelines/p03/test_r2_composite_distance.py` | Rewrite constructors, comments, and assertions to use the surviving HDBSCAN/neutral-param path | Keep integration coverage while removing DBSCAN terminology |
| learned-weight key usage and any persistence keys | Rename `dbscan_*` keys to neutral clustering keys with backward-compatibility handling | Avoid future semantic drift in learned tuning state |

#### Epic 2.1 Test And Wiring Requirements

| Test Area | What To Verify |
| --------- | -------------- |
| Import/wiring tests | `r2_episodic_integrator.py` initializes only HDBSCAN components and no stale DBSCAN imports remain anywhere in R2-related imports |
| Regression conversion | The scenarios currently covered by `test_r2_episodic_dbscan.py` are either intentionally dropped as dead-path coverage or re-expressed against the HDBSCAN path |
| Integration regression | `tests/k0/pipelines/p03/test_r2_integration.py` still proves semantically similar events group, dissimilar events stay separated/noisy, and pre-splitting still works after constructor renames |
| Config compatibility | Existing config objects and defaults still boot R2 cleanly after removing `use_hdbscan` and any DBSCAN-only config branches |
| Learned-param migration | Old learned-weight rows keyed with `dbscan_*` are migrated or safely read through a compatibility shim before cleanup is finalized |
| Grep validation | Final repository search shows no production references to `EpisodicDBSCAN`, `DBSCANParams`, or `use_hdbscan` outside approved migration notes/history |

### Epic 2.2: Fake Silhouette Fix

**Discovery Reference**: Section 24.4
**Repo Status**: OPEN

#### Epic 2.2 Verified Current State

- `r2_episodic_integrator.py` still computes `batch_silhouette` as average cohesion.
- `cluster_quality.py` still assumes a real silhouette input and normalizes from `[-1, 1]`.
- `eps_adjuster.py` still uses a silhouette target of `0.5`.
- No real `sklearn.metrics.silhouette_score(..., metric="precomputed")` call exists in the R2 path.

#### Milestone 2.2 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 2.2.1 carry distance matrix in clustering result | OPEN | Extend HDBSCAN result object or recompute the matrix where quality is evaluated. |
| 2.2.2 compute true silhouette | OPEN | Replace avg cohesion with true silhouette over the precomputed matrix. |
| 2.2.3 document normalization assumptions | OPEN | Keep normalization code only if fed with real silhouette values. |
| 2.2.4 retune `silhouette_target` | OPEN | Re-evaluate whether `0.5` is defensible once real values are flowing. |
| 2.2.5 validate interaction with `MinSamplesAdjuster` | OPEN | Test for feedback-loop stability after silhouette becomes real. |
| 2.2.6 add regression tests | OPEN | Add tests that prove fake and real silhouette diverge on the same cluster layout. |
| 2.2.7 document phantom quality channels | OPEN | Keep grounding/correction signals marked as inactive until they exist in the system. |

#### Epic 2.2 Exit Criteria

- R2 quality loop consumes a real silhouette value.
- `ClusterQualityTracker` no longer reports inflated quality because of fake silhouette input.
- Adjuster behavior is validated with realistic clustering outputs.

#### Epic 2.2 Issue Execution Checklist

##### Issue 2.2.1 Carry distance matrix through the clustering result

| Item | Detail |
| ---- | ------ |
| Goal | Ensure the quality loop has access to the exact precomputed distance matrix and labels used during clustering. |
| Read | `k0/modules/consolidation/algorithms/episodic_hdbscan.py` `cluster()`, `_run_hdbscan()`, `HDBSCANClusteringResult`; `k0/pipelines/p03/phases/r2_episodic_integrator.py` `_track_quality_and_adapt()`. |
| Change | Extend the HDBSCAN result surface or add a controlled quality-evaluation payload so the integrator can compute silhouette from the same matrix and label assignment used by clustering. |
| Core idea | A real silhouette is only defensible if it is derived from the same distance geometry and label mask that produced the clusters. |
| Tests | Add regression coverage that the quality pipeline receives labels and the matching distance matrix without recomputing from a different event subset. |
| Success criteria | The post-clustering quality path can access precomputed distances plus labels directly, without reverse-engineering them from episode candidates alone. |

**Codebase Reality** (verified 2026-03-07):

`EpisodicHDBSCAN.cluster()` at L258 in `episodic_hdbscan.py` computes `distances = self._compute_distance_matrix(events)` internally but does NOT expose the distance matrix on `HDBSCANClusteringResult` (dataclass at L159). The result contains: `clusters: List[EpisodeCluster]`, `labels: ndarray`, `noise_count: int`, `probabilities: ndarray`, `outlier_scores: ndarray`. The distance matrix is discarded after clustering.

`_track_quality_and_adapt()` in `r2_episodic_integrator.py` receives `candidates` (list of `EpisodeCandidate`) and computes `batch_silhouette` from cohesion scores at L1628-1639. It has NO access to the distance matrix or raw labels -- only episode-level aggregates.

`cluster_quality.py` `compute_from_r2_output()` at L271 takes `R2OutputProtocol` which exposes `batch_silhouette_score` (L186) -- a single float. No matrix access path exists.

**Research Evidence**:

POC-02/03 (`poc_02_03_silhouette_feasibility.json`, R2_RESEARCH_FINAL.md Section 8.1): Research computed `sklearn.metrics.silhouette_score(distance_matrix, labels, metric="precomputed")` on ALL 32 sequence distance matrices. This required the exact same matrix used for clustering plus the label assignment. 30/32 sequences had valid silhouette (2 had only 1 cluster). Mean silhouette = 0.2707, latency = 0.49ms avg per sequence. The research pipeline (`research_distance.py`) returns the distance matrix as part of its output -- K0 production code needs the same surface.

**Implementation Detail**:

1. Add `distance_matrix: Optional[np.ndarray] = None` field to `HDBSCANClusteringResult` at L159.
2. In `EpisodicHDBSCAN.cluster()` at L258: after computing `distances`, assign it to the result: `result.distance_matrix = distances`.
3. Alternative (memory-conscious): add a `compute_quality_metrics()` method on `EpisodicHDBSCAN` that accepts the result and computes silhouette internally, returning a quality payload. This avoids holding NxN matrices in memory across phase boundaries.
4. In `r2_episodic_integrator.py` `_track_quality_and_adapt()`: extract `result.distance_matrix` and `result.labels` for silhouette computation.
5. Ensure the matrix is the SAME one used for HDBSCAN fit -- not a recomputed version that might differ due to event filtering.

##### Issue 2.2.2 Replace average cohesion with true silhouette

| Item | Detail |
| ---- | ------ |
| Goal | Remove the fake silhouette calculation from the integrator. |
| Read | `k0/pipelines/p03/phases/r2_episodic_integrator.py` `_track_quality_and_adapt()` around `batch_silhouette`; `k0/modules/consolidation/algorithms/cluster_quality.py` `compute_from_r2_output()`. |
| Change | Replace the current `sum(c.cohesion_score)/cluster_count` approximation with a true silhouette computation over the precomputed distance matrix and cluster labels, with an explicit unavailable/skip policy when silhouette is mathematically invalid. |
| Core idea | Average cohesion is an intra-cluster compactness proxy. It is not a separation metric and cannot stand in for silhouette. |
| Tests | Add curated scenarios where average cohesion looks strong but true silhouette is weak or invalid, and prove the new path produces the correct distinction. |
| Success criteria | The integrator no longer computes or stores a fake silhouette approximation, and the value handed to the quality loop has true silhouette semantics. |

**Codebase Reality** (verified 2026-03-07):

The fake silhouette computation at `r2_episodic_integrator.py` L1628-1639:

```python
batch_silhouette = (
    sum(c.cohesion_score for c in candidates) / cluster_count if cluster_count > 0 else 0.0
)
```

This computes average intra-cluster cosine similarity (range [0, 1]) and labels it `batch_silhouette`. The value is passed to `R2OutputSimple(sil=batch_silhouette, ...)` which sets `batch_silhouette_score` consumed by `ClusterQualityTracker.compute_from_r2_output()` at L271 in `cluster_quality.py`.

`compute_composite()` at L117 normalizes: `normalized_silhouette = (self.silhouette_score + 1.0) / 2.0` mapping [-1,1] to [0,1]. Since fake silhouette from cohesion is already [0,1], this inflates it: cohesion 0.8 becomes normalized 0.9, making the adaptive loop believe quality is excellent when it may not be.

**Research Evidence**:

POC-02/03 (R2_RESEARCH_FINAL.md Section 8.1): True silhouette mean = 0.2707, range [0.14, 0.41], p25=0.24, p75=0.31. Spearman rho vs proxy = 0.4981 (p=0.005). Verdict: "MARGINAL as sole signal. Silhouette is useful as one of several signals in the composite quality tracker."

POC-08 (Section 8.2): EpsAdjuster with real silhouette: most batches (8/10) trigger "No adjustment" because silhouette is below target (0.5) but avg_cluster_size and singleton_rate are within range. The adjuster correctly avoids unnecessary movement.

M4-RSCH-04 (`m4_rsch04_episodic_coherence.json`, Section 11.6): Post-correction silhouette drops to -0.0329 because thread-purity correction moves events across sequence boundaries, invalidating per-sequence distance matrices. Episodic coherence (rho=0.4556) is stable across correction while silhouette breaks.

**Implementation Detail**:

1. In `r2_episodic_integrator.py` L1628-1639: Replace the cohesion average with:

   ```python
   from sklearn.metrics import silhouette_score
   if result.distance_matrix is not None and len(set(result.labels[result.labels >= 0])) >= 2:
       batch_silhouette = silhouette_score(result.distance_matrix, result.labels, metric="precomputed")
   else:
       batch_silhouette = None  # insufficient clusters for valid silhouette
   ```

2. Update `R2OutputSimple` to accept `Optional[float]` for `batch_silhouette_score`.
3. Keep `cohesion_score` per-episode as a useful diagnostic -- just stop labeling its average as silhouette.
4. Import `sklearn.metrics.silhouette_score` (already a project dependency via scikit-learn).
5. Handle noise labels: `silhouette_score` on precomputed matrices with `-1` noise labels -- either filter noise events before computing silhouette or use sklearn's built-in handling.

##### Issue 2.2.3 Define silhouette validity and normalization rules

| Item | Detail |
| ---- | ------ |
| Goal | Make the metric contract explicit for one-cluster, all-noise, and too-small batches. |
| Read | `k0/modules/consolidation/algorithms/cluster_quality.py` `ClusterQualityMetrics.compute_composite()` and alert logic; any R2 docs describing silhouette targets. |
| Change | Define how the system handles cases where silhouette cannot be computed, decide whether to use `None`, a sentinel value, or a skip flag, and keep the `[-1, 1]` normalization only for genuinely computed silhouettes. |
| Core idea | A mathematically undefined silhouette must not be silently converted into a misleading quality value. |
| Tests | Add unit tests for one-cluster, all-noise, single-point, and insufficient-label cases so composite quality and alerting do not misfire. |
| Success criteria | Quality computation distinguishes between real low silhouette and no valid silhouette, and downstream code handles both states intentionally. |

**Codebase Reality** (verified 2026-03-07):

`ClusterQualityMetrics.compute_composite()` at L117 in `cluster_quality.py`:

```python
normalized_silhouette = (self.silhouette_score + 1.0) / 2.0  # L131
```

This maps [-1,1] to [0,1]. But `silhouette_score` is currently always >= 0 (cohesion average), so the mapping never exercises the negative branch. Alert logic downstream uses `silhouette_score < threshold` to trigger warnings.

Edge cases NOT handled: one-cluster batches (silhouette undefined), all-noise batches (no labels >= 0), single-point clusters (degenerate), batches with < 2 distinct labels. All these currently get `batch_silhouette = 0.0` (the `else` branch in the fake computation), which the normalization converts to 0.5 -- misleadingly suggesting moderate quality.

**Research Evidence**:

POC-02/03 (`poc_02_03_silhouette_feasibility.json`): 30/32 sequences had valid silhouette, 2 had only 1 cluster (silhouette undefined). Range: [0.14, 0.41] -- all positive for valid sequences. Post-correction (M4-RSCH-04): silhouette can go negative (-0.0329 mean) when events are reassigned across sequence boundaries. The normalization is correct for real silhouette in [-1, 1] but must handle `None`/undefined explicitly.

**Implementation Detail**:

1. Add `silhouette_valid: bool` field to `ClusterQualityMetrics` (default=True).
2. When silhouette is `None` (undefined): set `silhouette_valid = False`, set `silhouette_score = 0.0` as sentinel, exclude silhouette from composite weight calculation (redistribute its 0.40 weight to remaining live channels).
3. Update `compute_composite()`: if `not self.silhouette_valid`, use 3-channel composite: `0.50*grounding + 0.33*(1-correction) + 0.17*(1-singleton)` (renormalized from 0.30/0.20/0.10).
4. Alert logic: distinguish `silhouette < threshold AND valid` (real quality concern) from `silhouette invalid` (data insufficiency -- different alert type).
5. Document edge cases: one-cluster = skip, all-noise = skip, < 2 distinct labels = skip.

##### Issue 2.2.4 Retune `silhouette_target` against real distributions

| Item | Detail |
| ---- | ------ |
| Goal | Reassess the `0.5` target now that the input metric becomes real instead of inflated by cohesion. |
| Read | `k0/modules/consolidation/algorithms/eps_adjuster.py` `EpsAdjustmentConfig`; research requirements in Milestone 2 proof obligations; replay harness outputs once available. |
| Change | Use the Milestone 2 research harness to benchmark real silhouette distributions on representative replayed batches, then either keep, lower, or parameterize the target with evidence. |
| Core idea | Thresholds chosen under a fake metric are not trustworthy once the metric becomes real. |
| Tests | Add config-level tests covering the accepted target and any new bounds or environment-specific overrides. |
| Success criteria | The selected silhouette target is justified by replay/research evidence rather than inherited from the fake-quality era. |

**Codebase Reality** (verified 2026-03-07):

`EpsAdjustmentConfig` at L42 in `eps_adjuster.py`:

```python
silhouette_target: float = 0.5   # L55
```

The adjuster triggers eps changes when `silhouette_score < 0.5`. Since fake silhouette (cohesion avg) is typically 0.7-0.95, the adjuster **almost never triggers**. The target of 0.5 was chosen under false metric assumptions.

The adjuster also checks secondary signals: `avg_cluster_size` and `singleton_rate` before adjusting. When silhouette < target BUT secondary signals are OK, no adjustment is made (POC-08: 8/10 batches correctly skipped).

**Research Evidence**:

POC-02/03 (`poc_02_03_silhouette_feasibility.json`): Real silhouette distribution on 30 valid sequences: mean=0.2707, median=0.2792, p25=0.2389, p75=0.3057, max=0.4148. **Every real silhouette value is below the current target of 0.5.** This means the adjuster will ALWAYS see below-target silhouette -- the secondary signal gates become the de facto decision maker.

POC-08 (`poc_08_oscillation_simulation.json`): With real silhouette (mean=0.3102 across 10 batches), the adjuster made only 2 adjustments in 10 cycles, both singleton-rate-driven (not silhouette-driven). eps moved from 0.2500 to 0.2540. The loop is stable because the secondary gates prevent overreaction.

Recommendation from R2_RESEARCH_FINAL.md Section 8.1: "Keep silhouette as the 0.40 weight component in `ClusterQualityTracker.compute_composite()`. The production formula is well-calibrated."

**Implementation Detail**:

1. Lower `silhouette_target` from 0.5 to **0.30** based on the research distribution (mean=0.2707, p75=0.3057). A target of 0.30 sits at the 75th percentile of real silhouette values -- above it means the batch is genuinely better than typical.
2. Alternative: make `silhouette_target` configurable via `R2Config` so it can be adjusted without code changes.
3. The EpsAdjuster's current secondary-gate behavior (check avg_cluster_size and singleton_rate before adjusting) is **already correct** for real silhouette. Do not change the gate logic.
4. Add a unit test asserting the target value and documenting the research-derived justification.
5. Monitor: log the silhouette value and target delta for the first 100 production cycles to validate the 0.30 target against live data.

##### Issue 2.2.5 Revalidate `EpsAdjuster` and `MinSamplesAdjuster` loop stability

| Item | Detail |
| ---- | ------ |
| Goal | Ensure the adaptive loop remains stable after the silhouette signal becomes more volatile and more honest. |
| Read | `k0/modules/consolidation/algorithms/eps_adjuster.py`; `k0/modules/consolidation/algorithms/min_samples_adjuster.py`; integration tests in `tests/k0/pipelines/p03/test_r2_integration.py`. |
| Change | Re-examine adjustment direction logic, cold-start behavior, and interaction between silhouette, singleton rate, and average cluster size once the input metric is real. |
| Core idea | Fixing the metric can destabilize the tuning loop unless the adjustment heuristics are rechecked under realistic values. |
| Tests | Add sequence tests that simulate multiple consecutive cycles and assert the loop does not oscillate or ratchet parameters in the wrong direction. |
| Success criteria | Adaptive tuning behaves predictably across repeated low-quality, recovery, and singleton-heavy scenarios when driven by real silhouette values. |

**Codebase Reality** (verified 2026-03-07):

`EpsAdjuster.adjust()` in `eps_adjuster.py` uses three inputs: `silhouette_score`, `avg_cluster_size`, `singleton_rate`. Direction logic: if silhouette < target AND (singleton_rate > threshold OR avg_cluster_size < min), increase eps. Momentum smoothing (0.9) damps oscillations. Cold-start: first N cycles use a different learning rate.

`MinSamplesAdjuster` in `min_samples_adjuster.py` uses only `singleton_rate` -- no silhouette dependency. It adjusts `min_samples` up when singletons are excessive.

`test_r2_eps_adjuster.py` tests: coverage for basic adjustment, cold-start, boundary conditions, momentum. Tests supply arbitrary silhouette values (0.3, 0.6, 0.8) without deriving them from real clustering.

**Research Evidence**:

POC-08 (`poc_08_oscillation_simulation.json`, R2_RESEARCH_FINAL.md Section 8.2): 10-batch simulation with real silhouette (mean=0.3102). Results: initial eps=0.2500, final=0.2540, total delta=+0.0040, max swing=0.0020, direction changes=0, converged=True. The momentum smoothing (0.9) is sufficient to prevent wild swings. Most batches (8/10) trigger "No adjustment" -- silhouette below target but secondary signals within range. The adjuster correctly avoids unnecessary movement.

MinSamplesAdjuster: not tested in POC-08 but its singleton_rate-only logic means the silhouette fix does not affect its behavior.

**Implementation Detail**:

1. No algorithm changes needed to EpsAdjuster or MinSamplesAdjuster. The loop is already stable with real silhouette.
2. Update `silhouette_target` from 0.5 to 0.30 (Issue 2.2.4).
3. Add multi-cycle integration test: simulate 10 cycles with real silhouette distributions (sample from [0.14, 0.41] uniform) and assert: eps stays within [0.20, 0.30], direction changes <= 2, no oscillation (no A-B-A-B pattern).
4. Add edge-case test: what happens when silhouette is `None` (invalid) for several consecutive cycles? The adjuster should skip silhouette-based adjustment and fall back to secondary gates only.
5. Keep `test_r2_eps_adjuster.py` existing arithmetic tests but add the new integration-level scenarios.

##### Issue 2.2.6 Rewrite the quality regression test surface

| Item | Detail |
| ---- | ------ |
| Goal | Make the test suite prove the new metric semantics instead of merely accepting injected silhouette numbers. |
| Read | `tests/k0/pipelines/p03/test_r2_cluster_quality.py`; `tests/k0/pipelines/p03/test_r2_integration.py`; `tests/k0/pipelines/p03/test_r2_eps_adjuster.py`. |
| Change | Keep downstream formula tests, but add integration-style tests that derive silhouette from real cluster layouts and precomputed matrices instead of stubbing in arbitrary values everywhere. |
| Core idea | Current tests mostly validate arithmetic after a silhouette is supplied; they do not validate whether the R2 pipeline computes that silhouette correctly. |
| Tests | Add explicit divergence tests between cohesion and silhouette, invalid-silhouette path tests, and end-to-end quality-loop tests using real clustering outputs. |
| Success criteria | The R2 quality test surface fails if the pipeline regresses back to average cohesion masquerading as silhouette. |

**Codebase Reality** (verified 2026-03-07):

`test_r2_cluster_quality.py`: Tests `ClusterQualityMetrics` arithmetic (composite formula, alert thresholds). Supplies silhouette as a parameter -- does not validate where it comes from.

`test_r2_integration.py`: Integration tests create `EpisodicDBSCAN`/`EpisodicHDBSCAN`, cluster events, but the quality path is not tested end-to-end (no assertion that the silhouette passed to quality tracking is real vs cohesion-derived).

`test_r2_eps_adjuster.py`: Tests adjustment direction and momentum with injected silhouette values. No test verifies the injected values match what the pipeline actually produces.

Gap: NO test currently catches the fake silhouette. A test that asserts `batch_silhouette` comes from `sklearn.metrics.silhouette_score` (not cohesion average) does not exist.

**Research Evidence**:

The research pipeline (`poc/r2_phase_research/r2_final_pipeline.py`) computes real silhouette via `silhouette_score(dm, labels, metric="precomputed")` and records it alongside proxy metrics. The integrated silhouette test (`poc/r2_phase_research/integrated_silhouette_test.py`, `results/integrated_silhouette_test.json`) proved: 30/32 valid, mean=0.2707, total compute=15.8ms. This serves as the golden reference for what production should produce on equivalent data.

**Implementation Detail**:

1. Add `test_real_vs_fake_silhouette_divergence()`: create a known cluster layout where cohesion avg = 0.85 but true silhouette = 0.15 (well-separated within-cluster, poor between-cluster separation). Assert the pipeline computes 0.15 (not 0.85).
2. Add `test_silhouette_from_distance_matrix()`: create a precomputed distance matrix, run HDBSCAN, compute silhouette, assert it matches `sklearn.metrics.silhouette_score()` on the same matrix.
3. Add `test_silhouette_invalid_cases()`: one-cluster, all-noise, single-point -- assert `silhouette_valid=False` and composite quality excludes silhouette weight.
4. Add regression guard: `test_no_cohesion_as_silhouette()` that asserts the integrator does NOT compute `sum(c.cohesion_score) / count`.
5. Keep existing `test_r2_cluster_quality.py` arithmetic tests (they validate downstream formula, which remains correct).

##### Issue 2.2.7 Mark dormant grounding/correction channels honestly

| Item | Detail |
| ---- | ------ |
| Goal | Prevent the composite quality score from being misread as fully closed-loop while grounding and correction inputs remain mostly absent. |
| Read | `k0/modules/consolidation/algorithms/cluster_quality.py` `compute_from_r2_output()` and `compute_metrics()`; relevant Milestone 2 research notes. |
| Change | Document and, if necessary, encode whether zero grounding/correction counts mean true zero signals or simply unavailable feedback for the current cycle. |
| Core idea | Fixing silhouette should not leave another silent semantic bug in the composite score. |
| Tests | Add tests that distinguish between absent feedback channels and actual zero-rate feedback, or explicitly document why the current zero default is acceptable. |
| Success criteria | Quality reporting and plan documentation clearly state which channels are live, which are dormant, and how that affects interpretation of composite quality. |

**Codebase Reality** (verified 2026-03-07):

`compute_composite()` at L117 in `cluster_quality.py`:

```python
# Composite formula:
# 0.40 * silhouette + 0.30 * grounding + 0.20 * (1 - correction_rate) + 0.10 * (1 - singleton_rate)
```

Current channel status:

- `silhouette_score`: FAKE (cohesion average) -- being fixed by Issues 2.2.1-2.2.2
- `grounding_rate`: DORMANT -- no grounding/reconciliation feedback loop exists in production. Value is always 0.0, contributing 0.0 to composite.
- `correction_rate`: DORMANT -- no external correction signals feed into this. Value is always 0.0, contributing 0.20 to composite (since `1 - 0.0 = 1.0`).
- `singleton_rate`: LIVE -- computed from actual cluster assignments. This is the only honestly-derived channel besides (soon-to-be-real) silhouette.

Net effect: composite = `0.40 * fake_sil + 0.30 * 0.0 + 0.20 * 1.0 + 0.10 * (1 - singleton_rate)` = `0.40 * fake_sil + 0.20 + 0.10 * (1 - singleton_rate)`. With fake silhouette ~0.85 and singleton_rate ~0.05: composite ~= 0.34 + 0.20 + 0.095 = 0.635. This inflated value masks poor clustering.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 8.1 recommendation: "Keep silhouette as the 0.40 weight component. The production formula `0.40*silhouette + 0.30*grounding + 0.20*(1-correction) + 0.10*(1-singleton)` is well-calibrated." This assumes real silhouette and eventual grounding/correction signals. Until those signals exist, the formula produces misleading composites.

M4-RSCH-04: Episodic coherence (mean=0.8167) provides a stable quality signal that could supplement or replace dormant grounding/correction channels.

**Implementation Detail**:

1. Add `channel_status` dict to `ClusterQualityMetrics`: `{"silhouette": "live", "grounding": "dormant", "correction": "dormant", "singleton": "live"}`.
2. In `compute_composite()`: when a channel is dormant, exclude its weight and renormalize. With silhouette (0.40) + singleton (0.10) live: effective formula becomes `0.80 * normalized_silhouette + 0.20 * (1 - singleton_rate)`.
3. Add logging: when composite is computed, emit which channels were live vs dormant for observability.
4. Add plan note: when grounding/correction become live (future milestone), re-enable their weights.
5. Alternative (simpler): keep 4-channel formula but log a clear warning that composite includes 2 dormant channels with zero contribution. Let operators decide if the raw composite value is meaningful.

##### Issue 2.2.8 Run scientific and performance validation

| Item | Detail |
| ---- | ------ |
| Goal | Prove the true silhouette path is both correct and operationally acceptable. |
| Read | Milestone 2 research checklist and replay-harness deliverables; the final quality-loop implementation after Issues 2.2.1 through 2.2.7. |
| Change | Run focused unit/integration tests plus research benchmarks covering sequence size, cluster-count shape, and invalid-silhouette cases; record latency and memory impact. |
| Core idea | This fix changes a core quality signal. It needs scientific validation, not only passing unit tests. |
| Tests | Run the R2 quality-related tests and the Milestone 2 research harness scenarios that benchmark true silhouette on precomputed matrices. |
| Success criteria | The repository has evidence that true silhouette is computed correctly, edge cases are handled intentionally, and the runtime cost is acceptable for expected batch sizes. |

**Codebase Reality** (verified 2026-03-07):

The validation target is the full quality path: `EpisodicHDBSCAN.cluster()` -> distance matrix + labels -> `silhouette_score()` -> `ClusterQualityTracker.compute_from_r2_output()` -> `EpsAdjuster.adjust()`. This path spans 4 files and 3 module boundaries.

Performance baseline: current fake silhouette is O(N) (sum of cohesion scores). True silhouette on precomputed matrix is O(N^2) for N events in a sequence. Largest sequence in corpus: 100 events (100x100 matrix = 80KB).

**Research Evidence**:

POC-02/03 (`poc_02_03_silhouette_feasibility.json`): Comprehensive benchmark results:

| Metric | Value |
| ------ | ----- |
| Sequences with valid silhouette | 30/32 |
| Mean silhouette | 0.2707 |
| Mean latency per sequence | 0.49ms |
| Total silhouette compute time (32 seq) | 15.8ms |
| Max sequence size | 100 events |
| Memory overhead per sequence | ~80KB (100x100 float64) |

POC-08 (`poc_08_oscillation_simulation.json`): 10-batch adaptive loop simulation: converged=True, no oscillation, eps 0.2500->0.2540. Mean silhouette across batches = 0.3102.

Integrated silhouette test (`results/integrated_silhouette_test.json`): End-to-end test of silhouette inside the full pipeline: 16ms total, 30/32 valid, Spearman rho=0.4981 (p=0.005) vs proxy composite.

**Implementation Detail**:

1. Run `pytest tests/k0/pipelines/p03/` after Issues 2.2.1-2.2.7 to verify all unit/integration tests pass.
2. Run the research silhouette harness (`poc/r2_phase_research/poc_02_03_silhouette.py`) against the updated K0 quality path to verify production silhouette values match research silhouette values on the same corpus (tolerance: mean within +/- 0.05).
3. Benchmark latency: measure silhouette computation time on 32 sequences, assert < 50ms total (research showed 15.8ms).
4. Verify edge cases: run sequences with 1 cluster, 0 clusters (all noise), and 1-event sequences through the full quality path.
5. Run POC-08 oscillation simulation against the updated code to confirm adaptive loop stability is preserved.
6. Record all validation results in `poc/r2_phase_research/results/m2_silhouette_validation.json`.

#### Epic 2.2 Implementation Context

| Read First | Why |
| ---------- | --- |
| Discovery Section 24.4 | Documents the fake-silhouette defect and why the loop is effectively dead. |
| temp design quality section | Defines the intended direction for coherence-quality metrics after Milestone 2. |
| Discovery Section 20 | Needed to understand what data is available after HDBSCAN clustering. |

#### Epic 2.2 Verified Read Set

| File / Symbol | What To Extract |
| ------------- | --------------- |
| `k0/pipelines/p03/phases/r2_episodic_integrator.py` batch stats path around `avg_cohesion`, `batch_silhouette`, and `R2OutputSimple` | Confirm where average cohesion is currently mislabeled as silhouette and fed into the adaptive loop. |
| `k0/modules/consolidation/algorithms/cluster_quality.py` `ClusterQualityMetrics.compute_composite`, `compute_from_r2_output`, alert logic | Confirm the tracker expects true silhouette semantics and normalizes from `[-1, 1]`. |
| `k0/modules/consolidation/algorithms/eps_adjuster.py` `EpsAdjustmentConfig` and `EpsAdjuster.adjust` | Confirm which thresholds and adjustment directions currently depend on the silhouette stream. |
| `tests/k0/pipelines/p03/test_r2_cluster_quality.py` | Inventory current assumptions that treat any supplied silhouette value as real. |
| `tests/k0/pipelines/p03/test_r2_integration.py` and `tests/k0/pipelines/p03/test_r2_eps_adjuster.py` | Identify where the adaptive loop is already pinned to the fake silhouette contract. |

#### Epic 2.2 Codebase Change Map

| File / Area | What Changes | Core Idea |
| ----------- | ------------ | --------- |
| `k0/pipelines/p03/phases/r2_episodic_integrator.py` | Stop computing `batch_silhouette` from average episode cohesion and replace it with a real silhouette pipeline over labels plus a precomputed distance matrix | Feed the adaptive loop a true separation/cohesion metric rather than a renamed cohesion average |
| `k0/modules/consolidation/algorithms/episodic_hdbscan.py` or `HDBSCANClusteringResult` | Expose the exact distance matrix and labels needed for silhouette computation, or expose enough state to recompute once in a controlled place | Prevent duplicate or inconsistent quality calculations |
| `k0/modules/consolidation/algorithms/cluster_quality.py` | Keep the `[-1, 1]` normalization only if the upstream metric is now a real silhouette, and mark grounding/correction channels as inactive inputs until they are real | Restore quality-metric correctness without pretending dormant channels are live |
| `k0/modules/consolidation/algorithms/eps_adjuster.py` | Revalidate `silhouette_target` and adjustment heuristics against real post-fix distributions | Prevent unstable or meaningless adaptation |
| `tests/k0/pipelines/p03/test_r2_cluster_quality.py`, `test_r2_integration.py`, and `test_r2_eps_adjuster.py` | Replace fake assumptions with true silhouette expectations and add explicit divergence cases where average cohesion and true silhouette disagree | Keep the quality loop scientifically defensible |

#### Epic 2.2 Test And Wiring Requirements

| Test Area | What To Verify |
| --------- | -------------- |
| Formula regression | Curated scenarios prove true silhouette differs from average cohesion on the same clustering output when separation is poor but per-cluster cohesion looks deceptively good |
| Quality loop stability | `EpsAdjuster` and `MinSamplesAdjuster` respond sensibly to real silhouette values rather than oscillating on batches dominated by rescued noise or tiny clusters |
| Sequence-size edge cases | Silhouette handling works for tiny batches, one-cluster batches, singleton-heavy batches, insufficient-label cases, and batches where silhouette must be skipped or reported as unavailable |
| Performance | Real silhouette on precomputed matrices remains within the latency envelope established by the Milestone 2 research harness |
| Wiring | Distance matrix and label flow reaches quality tracking exactly once and does not silently recompute with different masks or filtered event subsets |
| Dormant-signal honesty | Grounding/correction channels remain explicitly inactive in tests unless backed by actual signal sources, so the composite quality output is not misread as fully closed-loop |

### Epic 2.3: Contract Reconciliation

**Discovery Reference**: Sections 11.1 and 12.2
**Repo Status**: OPEN

#### Epic 2.3 Verified Current State

| Drift Area | Status | Verified State |
| --------- | ------ | -------------- |
| Pipeline contract algorithm | OPEN | `k0/contracts/pipelines/p03_consolidation.v1.yaml` still says DBSCAN. |
| Module contract algorithm | OPEN | `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml` still says DBSCAN. |
| Capability description | OPEN | `k0/contracts/capabilities/consolidation.v1.yaml` still says DBSCAN. |
| `read:st_cooccurrence` declaration | OPEN | Contract still declares it even though R2 does not use it. |
| `read:st_epi` / write capabilities | OPEN | Discovery still marks capability declaration drift; not reconciled in plan or contracts. |

#### Epic 2.3 Issue Execution Checklist

##### Issue 2.3.1 Reconcile algorithm descriptions

| Item | Detail |
| ---- | ------ |
| Goal | Remove DBSCAN-era algorithm claims from every R2-facing contract and replace them with the post-cleanup HDBSCAN/distance-based truth. |
| Read | `k0/contracts/pipelines/p03_consolidation.v1.yaml` R2 stage block; `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml` description block; `k0/contracts/capabilities/consolidation.v1.yaml` `cluster_episodes`; the final Epic 2.1 cleanup result. |
| Change | Update algorithm names, config examples, and descriptive text so they refer to HDBSCAN plus precomputed composite distance rather than DBSCAN eps/min_samples semantics. |
| Core idea | Contract text is part of the implementation surface. If it keeps describing DBSCAN after the cleanup, future design, review, and security work will be grounded in the wrong substrate. |
| Tests | Perform contract-to-code comparison after Epic 2.1 to ensure YAML wording matches the surviving clustering path and parameter model. |
| Success criteria | No active R2 contract or capability description claims DBSCAN is the production algorithm or describes DBSCAN-only configuration behavior. |

**Codebase Reality** (verified 2026-03-07):

Three contract files contain false DBSCAN algorithm claims:

1. `p03_consolidation.v1.yaml` R2 stage (L105-125): `algorithm: DBSCAN`, `eps: 0.3`, `min_samples: 3`, `metric: cosine`, `use_cooccurrence_boost: true`. Code defaults: HDBSCAN, eps=0.15, min_samples=2, metric=precomputed, no co-occurrence boost.
2. `consolidation.episodic_clusterer.v1.yaml`: "Algorithm: DBSCAN (Density-Based Spatial Clustering)", `eps: 0.3`, `min_samples: 3`, `metric: cosine`. Silhouette target >0.3, noise target <10%.
3. `consolidation.v1.yaml` `cluster_episodes`: "Cluster events into episodes using DBSCAN on 768-dim embeddings".

Parameter drift: Contract says eps=0.3, code says 0.15 (DBSCANParams default) or 0.07 (integrator DBSCAN fallback). Contract says min_samples=3, code says 2. Contract says cosine metric, code uses precomputed (HDBSCAN on distance matrix). Every config value is wrong.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.2: Proven optimal config is HDBSCAN with min_cluster_size=2, min_samples=1, cluster_selection_method=leaf, metric=precomputed, 3D ensemble distance (semantic=0.45, temporal=0.25, narrative=0.30). Go/No-Go Section 9.2: Epic 2.1 = GO. The entire DBSCAN contract surface is false.

**Implementation Detail**:

1. `p03_consolidation.v1.yaml` R2 stage: Change `algorithm: HDBSCAN`, `min_cluster_size: 2`, `min_samples: 1`, `metric: precomputed`, `cluster_selection_method: leaf`. Remove `use_cooccurrence_boost` (or mark as `false` with comment: "M5 Hebbian boost proved beneficial, integrate when production-ready").
2. `consolidation.episodic_clusterer.v1.yaml`: Replace "DBSCAN" with "HDBSCAN on precomputed composite distance". Update all config values to match code defaults. Update noise target to match research: 2/1360 = 0.15% noise (not <10%).
3. `consolidation.v1.yaml`: Change `cluster_episodes` description to "Cluster events into episodes using HDBSCAN on precomputed composite distance matrices".
4. After M3 lands (ensemble distance): do a second pass to update the exact weights, thresholds, and narrative fallback chain in contracts.

##### Issue 2.3.2 Reconcile capability declarations

| Item | Detail |
| ---- | ------ |
| Goal | Align declared side effects and capabilities with what the live R2 code actually reads, writes, and queries. |
| Read | `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml` `side_effects`; `k0/pipelines/p03/phases/r2_episodic_integrator.py` learned-param calls, existing-episode queries, quality tracking hooks, and embedding-dependent flow. |
| Change | Remove stale `read:st_cooccurrence` if Epic 5.1 remains blocked, add or justify `st_epi` access if episode matching stays in R2, and verify whether learned-weight, feedback, and audit interactions belong in this contract or in adjacent module contracts. |
| Core idea | Capability declarations must reflect actual authority use. Overdeclared capabilities weaken review; underdeclared capabilities make the contract false. |
| Tests | Run a contract-code audit against actual table access and syscall usage, including `st_vec`, `st_epi`, learned-param reads/writes, and any quality-related persistence paths. |
| Success criteria | Every declared capability is exercised by the real R2 path, every exercised table/capability is declared in the correct contract surface, and no stale R2 authority remains justified only by old design intent. |

**Codebase Reality** (verified 2026-03-07):

Contract declares these side effects in `consolidation.episodic_clusterer.v1.yaml`:

- `read:st_vec` -- REAL: R2 joins st_vec at L1760 for episode centroid embeddings
- `read:st_cooccurrence` -- FALSE: R2 never reads st_cooccurrence. The table concept exists in contracts but R2 clustering does not consume co-occurrence data from any table.

Undeclared but exercised:

- `read:st_epi` -- R2 queries existing episodes at L1759 via `ctx.syscalls.execute_query()` raw SQL for episode matching
- `read:st_learned_weights` -- R2 reads `dbscan_eps` and `dbscan_min_samples` at L821-831 via `ctx.syscalls.get_learned_param()`
- `write:st_learned_weights` -- R2 writes adjusted eps/min_samples at L1660-1700 via `ctx.syscalls.set_learned_param()`

Total actual syscall usage: `get_learned_param` (2 reads), `set_learned_param` (2 writes), `execute_query` (1 raw SQL join on st_epi + st_vec).

**Research Evidence**:

M5-RSCH-01 (`m5_rsch01_02_hebbian_boost.json`, R2_RESEARCH_FINAL.md Section 12.3): Hebbian co-occurrence boost proved beneficial (5/8->8/8 scenarios) but operates on participant co-occurrence at distance level, NOT via `st_cooccurrence` table read. The `read:st_cooccurrence` declaration was a planned-but-never-implemented feature. Section 12.6: "st_cooccurrence exit gate is partially met: Hebbian boost works via participant co-occurrence without needing a separate st_cooccurrence table."

**Implementation Detail**:

1. Remove `read:st_cooccurrence` from side_effects -- R2 does not read this table and the Hebbian boost (M5) will use participant lists from events, not a separate co-occurrence table.
2. Add `read:st_epi` -- R2 queries existing episodes for episode matching.
3. Add `read:st_learned_weights` and `write:st_learned_weights` -- R2 reads and writes adaptive clustering parameters.
4. Review whether the raw SQL join on st_epi + st_vec should be documented as a composite capability or as separate table accesses.
5. Add `input_event_types` update: contract says `[p03.importance.scored.v1, p03.hebbian.updated.v1]` -- verify `p03.hebbian.updated.v1` is real (Hebbian update happens in a separate R2 sub-phase or is stale).
6. After Epic 2.1 key rename: update learned-param key references from `dbscan_eps`/`dbscan_min_samples` to `clustering_eps`/`clustering_min_samples` in contract documentation.

##### Issue 2.3.3 Reconcile quality thresholds and semantics

| Item | Detail |
| ---- | ------ |
| Goal | Make contract-level quality language reflect the post-fix meaning of silhouette, singleton/noise behavior, and dormant feedback channels. |
| Read | `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml` quality section; `k0/modules/consolidation/algorithms/cluster_quality.py`; `k0/modules/consolidation/algorithms/eps_adjuster.py`; Epic 2.2 outputs. |
| Change | Replace the current silhouette and noise targets if needed, clarify whether thresholds are targets, alerts, or tuning heuristics, and stop implying a fully closed-loop quality signal if grounding/correction channels are still largely dormant. |
| Core idea | A contract that names quality thresholds without matching the actual metric semantics is worse than no threshold, because it creates false confidence in tuning and audit discussions. |
| Tests | Verify that contract wording matches the final real-silhouette implementation, invalid-silhouette handling, and the chosen interpretation of feedback-derived channels. |
| Success criteria | Quality terminology in contracts matches the live implementation and does not overstate the maturity of the quality loop. |

**Codebase Reality** (verified 2026-03-07):

`consolidation.episodic_clusterer.v1.yaml` quality targets: "Silhouette target >0.3, noise target <10%".

Code reality:

- `silhouette_target` = 0.5 in `EpsAdjustmentConfig` (L55 of eps_adjuster.py) -- different from contract's 0.3
- Actual silhouette: FAKE (cohesion average, typically 0.7-0.95) -- neither matches contract nor code target
- Research real silhouette: mean=0.2707, which is BELOW the contract target of 0.3
- Noise: research shows 2/1360 = 0.15% noise (well under 10%); production baseline shows 972/1360 = 71.5% noise (wildly above 10%)

Contract also implies a closed-loop quality signal. Reality: composite formula has 2 dormant channels (grounding, correction) contributing 0.0 and 1.0 respectively. Only silhouette (soon real) and singleton_rate are live.

**Research Evidence**:

POC-02/03 (R2_RESEARCH_FINAL.md Section 8.1): Real silhouette distribution: mean=0.2707, p75=0.3057. A target of 0.3 (contract) is at the 75th percentile -- most batches will be below it. A target of 0.5 (code) means ALL batches are below it. Research recommendation: lower code target to 0.30 (Issue 2.2.4).

M4-RSCH-04 (Section 11.6): Episodic coherence (mean=0.8167) provides a stable supplementary quality signal. Contract should acknowledge coherence as a future quality channel.

**Implementation Detail**:

1. Update contract silhouette target from ">0.3" to match the research-justified code target (0.30 per Issue 2.2.4). Add note: "Mean real silhouette on representative corpus = 0.27; target of 0.30 is at p75 of observed distribution."
2. Update noise target: keep "<10%" as a contract invariant. Current research achieves 0.15% noise. Production baseline violates this at 71.5%.
3. Add quality channel status section: explicitly state which channels are live (silhouette, singleton_rate) and which are dormant (grounding, correction). Document the renormalized composite formula.
4. Add note about episodic coherence as a planned quality supplement (M4-RSCH-04 proved rho=0.4556 post-correction, stable across correction).

##### Issue 2.3.4 Reconcile failure modes and skip behavior

| Item | Detail |
| ---- | ------ |
| Goal | Replace stale failure policies with the actual R2 skip, exclusion, and error behavior. |
| Read | `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml` `failure_modes`; `k0/contracts/pipelines/p03_consolidation.v1.yaml` R2 timeout wording; `k0/pipelines/p03/phases/r2_episodic_integrator.py` `should_skip()`, `_get_skip_reason()`, and the main `run()` flow. |
| Change | Remove `fallback_skip` and `single_cluster` language if those behaviors are not real, capture actual skip conditions such as insufficient batch size and no embeddings, and re-check whether embedding-missing events are excluded at event level or cause full-phase skip. |
| Core idea | Failure contracts must describe what the phase really does under degraded input or timeout pressure, not what a previous algorithm variant once did. |
| Tests | Add or update wiring tests so the documented skip/exclude behavior for insufficient events, missing embeddings, and other non-exception paths matches the contract text exactly. |
| Success criteria | Contract failure and skip policies match the observable behavior of the live R2 phase and no longer refer to dead fallback semantics. |

**Codebase Reality** (verified 2026-03-07):

Contract `failure_modes` in `consolidation.episodic_clusterer.v1.yaml`:

- `EMBEDDING_NOT_FOUND` -> `exclude_event` -- PARTIALLY REAL: events without `embedding_768` are filtered, but the failure mode code is not raised as an explicit error.
- `CLUSTER_TIMEOUT` -> `fallback_skip` -- STALE: "fallback_skip" implies DBSCAN fallback, which no longer exists. Timeout behavior is not implemented in R2 (no explicit timeout enforcement in `cluster()`).
- `INSUFFICIENT_EVENTS` -> `single_cluster` -- STALE: R2 does not create a single cluster for insufficient events. It returns `skip` (no episodes formed).

Actual skip behavior in `r2_episodic_integrator.py`:

| Skip Point | Location | Condition | Actual Behavior |
| ---------- | -------- | --------- | --------------- |
| Pre-run | L431 | `should_skip()`: batch < min_batch_size OR no embeddings | `P03PhaseResult.skip()` -- skip entire phase |
| Post-filter | L472 | After embedding filter, 0 events remain | `envelope.with_skip()` |
| Per-cluster | L588 | Noise label (-1) | Skip noise cluster during iteration |
| Per-cluster | L593-597 | Single-member cluster | Skip (not considered episode) |

Contract says `single_cluster` fallback; code says `skip`. Contract says `fallback_skip` (implying DBSCAN fallback); code says phase skip.

**Research Evidence**:

Research corpus: 1360 events, 2 noise events (0.15%), 260 clusters, minimum cluster size 2. No scenario triggered insufficient-events or timeout skip. The skip behavior was tested implicitly through empty-batch edge cases in `test_r2_integration.py`.

**Implementation Detail**:

1. Update `CLUSTER_TIMEOUT` action from `fallback_skip` to `phase_skip` -- no DBSCAN fallback exists. If timeout is real, R2 should skip cleanly.
2. Update `INSUFFICIENT_EVENTS` action from `single_cluster` to `phase_skip` -- code does not create a single cluster, it skips.
3. Add `EMBEDDING_FILTER` failure mode: when some events lack embeddings, they are excluded from clustering (not the phase). Document this as `exclude_event` behavior (existing behavior, but should be explicitly captured).
4. Remove "fallback" language from all failure modes.
5. Add actual skip conditions to contract: `batch_size < min_batch_size` (configurable), `no events with embedding_768`.
6. Consider adding `NO_VALID_CLUSTERS` failure mode for cases where HDBSCAN assigns all events to noise (label=-1).

##### Issue 2.3.5 Reconcile pipeline and module boundary ownership

| Item | Detail |
| ---- | ------ |
| Goal | Clarify which R2 behaviors belong in the pipeline contract versus the module contract versus adjacent quality or episode-matching surfaces. |
| Read | `k0/contracts/pipelines/p03_consolidation.v1.yaml`; `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml`; `k0/pipelines/p03/phases/r2_episodic_integrator.py` episode-matching and quality-tracking flow. |
| Change | Decide whether episode matching against `st_epi`, learned-param adaptation, and quality persistence are intrinsic to the clusterer contract or need separate documentation/contract surfaces to avoid overloading the module contract. |
| Core idea | Contract reconciliation is not only wording cleanup. It is also about placing responsibilities on the correct boundary so later phases do not inherit a misleading contract split. |
| Tests | Use a contract review checklist rather than unit tests: each responsibility should appear exactly once at the right layer with no ambiguous duplication between pipeline and module descriptions. |
| Success criteria | The pipeline and module contracts divide R2 responsibilities cleanly enough that future reviewers can tell where clustering ends and adjacent orchestration begins. |

**Codebase Reality** (verified 2026-03-07):

Current responsibility tangle in `r2_episodic_integrator.py` (2134 lines):

| Responsibility | Owner (Pipeline or Module?) | Current Location |
| -------------- | --------------------------- | ---------------- |
| Event filtering + embedding check | Pipeline (orchestration) | L431-472 (should_skip, post-filter) |
| Sequence splitting (EpisodeSplitter) | Module (algorithm) | L480-500 (delegated to EpisodeSplitter) |
| Distance matrix + HDBSCAN clustering | Module (algorithm) | L500-600 (delegated to EpisodicHDBSCAN) |
| Episode candidate assembly | Pipeline (orchestration) | L600-800 (builds EpisodeCandidate from clusters) |
| Episode matching against st_epi | Pipeline (cross-cutting) | L1759 (raw SQL query joining st_epi + st_vec) |
| Quality tracking (silhouette, composite) | Module (quality) | L1628-1650 (computes batch_silhouette, delegates to ClusterQualityTracker) |
| Adaptive param tuning (EpsAdjuster) | Module (learning) | L1660-1700 (reads/writes st_learned_weights) |
| Observability (logging, metrics) | Pipeline (cross-cutting) | Throughout |

The pipeline contract describes the R2 stage as a single stage (`stage_20_episodic_cluster`). The module contract describes the clusterer as a single module (`consolidation.episodic_clusterer:v1`). But the integrator combines clustering, quality tracking, adaptive tuning, episode matching, and observability in one 2134-line file.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 5.1-5.2 (Production Implementation Plan): Identifies 3 distinct components for the target R2 path: (1) CompositeDistance replacement with ensemble, (2) ThreadEmbeddingCache, (3) Post-clustering thread purity correction. These map naturally to separate module contracts but are currently all inside the integrator.

Section 8.1 recommendation: "Keep silhouette as the 0.40 weight component in ClusterQualityTracker." This confirms quality tracking as a distinct responsibility from clustering.

**Implementation Detail**:

1. Document the boundary split in contracts (no code refactoring in M2 -- that's M3 Epic 3.5 Phase Wrapper Decomposition):
   - **Pipeline contract** (`p03_consolidation.v1.yaml`): Owns event filtering, skip logic, episode candidate assembly, episode matching, and observability.
   - **Module contract** (`consolidation.episodic_clusterer.v1.yaml`): Owns distance matrix computation, HDBSCAN clustering, noise rescue.
   - **Quality module** (new or extended contract): Owns silhouette computation, composite quality, channel status.
   - **Adaptive module** (EpsAdjuster, MinSamplesAdjuster): Owns learned-param read/write, adjustment logic.
2. Add a "Responsibility Boundaries" section to the module contract clarifying what is intrinsic (clustering algorithm, distance matrix) vs delegated (quality tracking, adaptive tuning, episode matching).
3. Flag episode matching (raw SQL on st_epi + st_vec) as a candidate for extraction into a separate phase or module in M3.

##### Issue 2.3.6 Run contract and architecture sync validation

| Item | Detail |
| ---- | ------ |
| Goal | Prove the reconciled YAML, code, and architecture descriptions all agree after Milestone 2 changes land. |
| Read | Final state of the R2 contracts, any touched architecture diagrams/docs, and the relevant R2 implementation files after Epics 2.1 and 2.2 are complete. |
| Change | Run the contract-code audit, grep validation, and required architecture sync checks, then capture any residual intentional drift explicitly. |
| Core idea | Contract reconciliation is only complete when the repo stops telling multiple different stories about R2. |
| Tests | Validate the relevant R2 tests, grep for stale DBSCAN/fallback terms, and run the required governance sync check for K0 documentation alignment. |
| Success criteria | Contracts, code, and architecture references are mutually consistent, and any remaining drift is intentional, documented, and non-blocking. |

**Codebase Reality** (verified 2026-03-07):

Current known drift inventory:

| Contract Element | Contract Says | Code Does | Drift Type |
| ---------------- | ------------- | --------- | ---------- |
| Algorithm | DBSCAN | HDBSCAN (default) | Critical -- false |
| eps | 0.3 | 0.15 (param default) / 0.07 (fallback) | Wrong value |
| min_samples | 3 | 2 (param default) | Wrong value |
| metric | cosine | precomputed | Wrong value |
| Co-occurrence boost | enabled, weight=0.2 | NOT wired | False capability |
| read:st_cooccurrence | declared | never accessed | Overdeclared |
| read:st_epi | NOT declared | accessed (L1759) | Underdeclared |
| read/write:st_learned_weights | NOT declared | accessed (L821, L1660) | Underdeclared |
| Silhouette target | >0.3 | 0.5 (code) / 0.27 (real) | Misaligned |
| Noise target | <10% | 0.15% (research) / 71.5% (prod) | Misleading |
| CLUSTER_TIMEOUT action | fallback_skip | phase_skip (no fallback) | Stale |
| INSUFFICIENT_EVENTS action | single_cluster | phase_skip | Stale |
| Quality loop | implied closed | 2/4 channels dormant | Overstated |

Governance sync tool: `python -m governance.k0.scripts.sync --report` can detect module/pipeline/event/ADR drift against `k0_architecture_master.md`.

**Research Evidence**:

All drift items above are documented in the R2 research: Go/No-Go Section 9 (algorithm GO, quality GO, contract DEFER-then-DO), POC-02/03 (silhouette values), POC-05 (key inventory), POC-08 (stability), Production Baseline Section 7 (noise comparison). The research pack provides the authoritative "truth" for what contracts should say.

**Implementation Detail**:

1. After Issues 2.3.1-2.3.5 are complete, run the full drift audit:
   - `grep -rn "DBSCAN\|dbscan" k0/contracts/` -- should yield 0 active hits
   - `grep -rn "st_cooccurrence" k0/contracts/` -- should yield 0 or only "planned/future" context
   - Compare every `side_effects` entry against actual syscall usage in `r2_episodic_integrator.py`
2. Run governance sync: `python -m governance.k0.scripts.sync --report`
   - Expect: Module registry updated for HDBSCAN, event topics current, pipeline row updated
   - Accept: "Planning" drift for M3-M5 items that are documented as future work
3. Update `k0_architecture_master.md` sections:
   - Part 2.1 Pipeline Master Registry: P03 R2 stage algorithm = HDBSCAN
   - Part 3.1 Module Master Registry: episodic_clusterer algorithm = HDBSCAN
   - Part 5.1 Global Contract Registry: update p03, episodic_clusterer, consolidation capability contracts
4. Document residual intentional drift:
   - Ensemble distance weights (0.45/0.25/0.30) documented in research but not yet in production code (M3 scope)
   - Hebbian boost (M5) proved beneficial but not yet integrated
   - Post-clustering thread purity correction (M3) not yet implemented
   - These are "Planning" drift, not unexpected drift

#### Epic 2.3 Implementation Context

| Read First | Why |
| ---------- | --- |
| Discovery Sections 11.1 and 12.2 | Canonical divergence list for algorithm, capability, and security drift. |
| Updated Milestone 2.1 and 2.2 sections in this plan | Contract edits must follow code-path truth after cleanup and quality fixes. |
| Relevant pipeline/module/capability YAMLs | Source of truth to be reconciled against actual code |

#### Epic 2.3 Verified Read Set

| File / Symbol | What To Extract |
| ------------- | --------------- |
| `k0/contracts/pipelines/p03_consolidation.v1.yaml` R2 stage description, `algorithm: DBSCAN`, and timeout/failure text | Confirm the pipeline contract still describes the removed algorithm and stale fallback behavior. |
| `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml` side effects, failure modes, and quality targets | Confirm exactly where algorithm, capability, and quality drift is encoded in the module contract. |
| `k0/contracts/capabilities/consolidation.v1.yaml` `cluster_episodes` description | Confirm the capability description still anchors future readers to DBSCAN terminology. |
| `k0/pipelines/p03/phases/r2_episodic_integrator.py` and surviving clustering algorithm files | Reconcile contracts against actual table access, failure behavior, and quality semantics rather than against the old dossier language alone. |

#### Epic 2.3 Codebase Change Map

| File / Area | What Changes | Core Idea |
| ----------- | ------------ | --------- |
| `k0/contracts/pipelines/p03_consolidation.v1.yaml` | Update R2 stage description, config keys, timeout behavior, and quality language away from DBSCAN-era wording | Pipeline contract must describe the real R2 behavior after cleanup |
| `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml` | Update algorithm description, side effects, failure policies, and quality targets after the real-silhouette fix | Module contract must stop describing dead DBSCAN behavior and phantom feedback closure |
| `k0/contracts/capabilities/consolidation.v1.yaml` | Reconcile declared R2 capability description with the actual HDBSCAN/distance-based clustering path | Capability model must match security reality and help future reviews |
| Any architecture/docs rows tied to R2 | Update terminology and dependencies once code and YAML truth are aligned | Prevent future planning drift |

#### Epic 2.3 Test And Wiring Requirements

| Test Area | What To Verify |
| --------- | -------------- |
| Contract-code audit | Every declared capability is actually used, every used capability is declared, and stale `read:st_cooccurrence` or other R2 declarations are either justified or removed |
| Failure-mode alignment | Timeout and insufficient-event behaviors described in YAML match the actual R2 path after DBSCAN fallback removal and real silhouette wiring |
| Quality-language alignment | Contract quality targets and metric descriptions reflect the post-fix semantics of silhouette and any still-dormant grounding/correction channels |
| Terminology consistency | DBSCAN-era names are removed anywhere they would mislead future implementation or security review |
| Security review readiness | Contract declarations are sufficient for capability audit, syscall review, and future ADR reconciliation |

#### Milestone 2 Exit Criteria

- DBSCAN path fully removed.
- Fake silhouette eliminated.
- Contracts and capability declarations describe actual R2 behavior.
- POC/research outputs exist and are sufficient to justify moving from cleanup into formula-heavy Milestone 3 work.

#### Milestone 2 Completion Verification

| Area | Verification Requirement |
| ---- | ------------------------ |
| Research | POC outputs exist for all Milestone 2 proof obligations and are grounded in replayed or real repository data |
| Code | No DBSCAN production path, no fake silhouette input, no stale capability drift |
| Tests | Unit, regression, and wiring coverage are updated for the surviving HDBSCAN-only path |
| Handoff | Milestone 3 starts with evidence, not assumptions, about what formulas and signal interactions should be carried forward |

---

## MILESTONE 3: Distance & Splitting Enhancements (P2)

**Milestone Status**: OPEN
**Execution Gate**: Start only after Milestone 2 cleanup and contract work stabilize.

### Milestone 3 Operating Assumption

The planning below assumes Milestone 2 is complete and already merged into the live substrate.
That means Milestone 3 work starts from an HDBSCAN-only clustering path, real silhouette semantics,
and reconciled contracts/capabilities rather than from the current DBSCAN-era drift still present in repo today.

### Milestone 3 Structural Prerequisites

Two protocol contracts must be extended before any M3 epic can proceed. Both are consumed by
multiple epics and must be coordinated as a shared dependency.

| Protocol | Current Surface | Required For | Gap |
| -------- | --------------- | ------------ | --- |
| `EventLike` in `composite_distance.py` | `event_id`, `timestamp`, `embedding_768` | Epics 3.1, 3.2, 3.4, 3.6 | Needs spatial, social, affective, narrative, and temporal-support fields for 6D distance and context-aware rescue |
| `SplittableEvent` in `episode_splitter.py` | `event_id`, `timestamp` (all else via `getattr` fallback) | Epics 3.3, 3.6 | Needs narrative, social, affective, cognitive channel fields for multi-signal boundary scoring |
| `EventAdapter` in `r2_episodic_integrator.py` | Exposes 3 of 8 temporal support fields | Epics 3.6, 3.7 | Missing: `temporal_links_json`, `time_of_day_bucket`, `circadian_slot`, `is_weekend`, `extraction_sequence` |

These protocols are shared across `CompositeDistance`, `EpisodeSplitter`, and `EpisodicHDBSCAN` rescue.
Changes to `EventLike` and `SplittableEvent` must be coordinated: both should adopt the same
underlying enriched event contract so downstream consumers see a consistent field surface.

### Milestone 3 Signal Availability And Fallback Design Principle

Not every signal will be populated for every event. Real-world causes include:

- **User permissions**: Location signals (`place_id`, `geohash_6`, `location_hierarchy_json`) may be absent if the user has not granted device location access.
- **MW version gaps**: Events ingested under older MW versions may lack fields added later (`k1_signal_version` drift).
- **Sparse extraction**: NER/temporal extraction may fail to produce `temporal_links_json`, `temporal_anchor_json`, or `extraction_sequence` on some events.
- **Classifier uncertainty**: `activity_type_ultrabert`, `intent_ultrabert`, and their confidence scores may be absent or below useful thresholds.
- **Minimal social context**: Solo events may lack `participants_json`, `participant_relationships_json`, and `social_intimacy`.

Every M3 distance dimension, splitter channel, and rescue evaluator MUST implement a fallback chain:

1. **Primary signal** (strongest, most specific): e.g., `place_id` for spatial.
2. **Secondary signal** (weaker but available): e.g., `location_hierarchy_json`, then `geohash_6`.
3. **Neutral fallback** (no signal available): dimension contributes `0.5` (neutral distance) and its weight is redistributed proportionally to dimensions that have real data.

The neutral-fallback contract means:

- Missing signals NEVER produce accidental `0.0` (false closeness) or `1.0` (false separation).
- Missing signals NEVER crash or raise exceptions.
- The weight budget is always normalized: if 2 of 6 dimensions are missing, the remaining 4 share the full weight budget proportionally.
- Per-event signal-availability masks are tracked for observability so operators can distinguish "low quality because signals are sparse" from "low quality because the episode is incoherent."

#### Canonical Composite Distance Formula (Confidence-Weighted Bagging)

The composite distance MUST use confidence-weighted bagging, not a naive weighted sum. This is
the proven formula from the research pipeline (`_ensemble_distance()` in `research_distance.py`):

$$d(a, b) = \frac{\sum_{i} w_i \cdot c_i \cdot d_i}{\sum_{i} w_i \cdot c_i}$$

Where:

- $w_i$ = static weight for dimension $i$ (semantic=0.45, temporal=0.25, narrative=0.30, etc.)
- $c_i$ = confidence score for dimension $i$ on this specific event pair, range [0.0, 1.0]
- $d_i$ = raw distance for dimension $i$, range [0.0, 1.0] (or inf for hard temporal cutoff)

Each dimension function returns BOTH a distance AND a confidence:

- **Semantic**: confidence = 1.0 if both embeddings exist, 0.3 if one is missing
- **Temporal**: confidence = 1.0 always (timestamps always available)
- **Narrative**: confidence varies by tier (T1: 1.0, T2: 0.7, T2b: 0.45, T3: 0.9, T4: 0.6, T5: 0.4, T6: 0.2, MISS: 0.0)
- **Spatial/Social/Affective**: confidence = 1.0 if signals present, 0.0 if absent

When $c_i = 0.0$, the dimension is excluded from both numerator and denominator. This achieves
automatic weight redistribution: if narrative signals are missing ($c_{narr} = 0.0$), the
0.30 narrative weight is automatically redistributed proportionally to semantic and temporal.

This formula is the canonical distance equation for all M3 Epic 3.1 implementations. Do NOT
implement a naive `sum(w_i * d_i)` weighted sum — it produces incorrect results when signals
are sparse because missing dimensions contribute their neutral value (0.5) at full weight
instead of being excluded.

This fallback design applies uniformly to:

- `CompositeDistance.compute()` and `build_distance_matrix()` (Epic 3.1)
- `EpisodeSplitter._detect_break()` boundary scoring (Epic 3.3)
- `EpisodicHDBSCAN._rescue_noise()` context-aware rescue (Epic 3.4)
- Temporal context binding (Epic 3.6)

### Milestone 3 Research Program

Milestone 3 is where the real formula design happens. The 6D weights, the log-temporal curve shape,
boundary scoring weights, and rescue scoring weights all need empirical validation. The M2 research
harness (`poc/r2_phase_research/`) must be extended for M3 formula validation before any formula is
locked into production code.

#### Milestone 3 Required Research Tracks

| Track | Requirement | Why It Is Needed |
| ----- | ----------- | ---------------- |
| 6D weight calibration | Sweep dimension weights on replay datasets and measure clustering quality under various weight combinations | Prevents arbitrary weights from being promoted to production constants |
| Log-temporal curve research | Compare linear, logarithmic, and exponential temporal decay functions on replay data | Justifies the chosen curve shape and tau parameter |
| Boundary scoring research | Evaluate multi-signal boundary scoring against current first-match-wins on replay sequences | Proves the new splitter is better, not just more complex |
| Rescue scoring research | Benchmark context-aware rescue vs distance-only rescue on contamination and recall scenarios | Prevents rescue from becoming a new contamination vector |
| Fallback neutrality research | Measure how sparse-signal batches behave under weight redistribution vs fixed neutral values | Ensures the fallback design does not create hidden biases |
| Signal contribution ablation | Turn individual dimensions on/off and measure marginal contribution to clustering quality | Confirms each dimension earns its place in the model |
| Protocol extension validation | Verify enriched event protocols work across CompositeDistance, EpisodeSplitter, and HDBSCAN rescue | Prevents protocol drift between consumers |

#### Milestone 3 Research Questions

| Research ID | Question | Expected Research Form |
| ----------- | -------- | ---------------------- |
| M3-RSCH-01 | What 6D weight combination optimizes clustering quality on representative replay data? | Weight-sweep matrix with quality proxies |
| M3-RSCH-02 | Which log-temporal tau and curve shape best match neuromorphic episodic binding? | Curve comparison benchmark |
| M3-RSCH-03 | Does multi-signal boundary scoring reduce cross-context contamination vs first-match-wins? | Boundary comparison on contamination scenarios |
| M3-RSCH-04 | Does context-aware rescue improve episode purity without excessive noise rejection? | Rescue contamination/recall benchmark |
| M3-RSCH-05 | How does weight redistribution under sparse signals compare to fixed neutral fallback? | Sparse-batch ablation study |
| M3-RSCH-06 | Which support signals (3.7.1-3.7.5) materially improve clustering vs merely adding noise? | Signal-family ablation from M2 research extended to M3 formulas |
| M3-RSCH-07 | Does wrapper decomposition (3.5) before algorithmic changes reduce implementation risk? | Code complexity and review difficulty comparison |

#### Milestone 3 Proof Obligations

| Proof ID | What Must Be Proven | Why It Matters |
| -------- | ------------------- | -------------- |
| M3-POC-01 | 6D distance with calibrated weights produces better clustering than 2D baseline | Justifies the complexity increase |
| M3-POC-02 | Log-temporal distance produces more neuromorphic temporal binding than linear | Justifies replacing a simple, working function |
| M3-POC-03 | Multi-signal boundary scoring catches more real context breaks than 4-signal priority | Justifies replacing simple splitter logic |
| M3-POC-04 | Context-aware rescue reduces contamination without excessive noise survival | Justifies touching the rescue path |
| M3-POC-05 | Fallback/neutral behavior under sparse signals does not create hidden clustering biases | Required for production safety |
| M3-POC-06 | Each support signal (3.7.x) either earns its place via ablation or is explicitly excluded | Prevents support-signal sprawl |

#### Milestone 3 Research-Proven Parameter Baseline

The research pipeline (`poc/r2_phase_research/`) has already calibrated working parameters through
extensive experimentation. All M3 research tracks MUST start from these values as the default
baseline. Research should IMPROVE on these, not start from scratch. Any deviation from the
baseline must be justified by measurable improvement on the replay corpus.

**Distance Parameters (proven in `research_distance.py` `ens_fuzzy_narrative_v10`)**:

| Parameter | Proven Value | Source |
| --------- | ------------ | ------ |
| Semantic weight | 0.45 | `EnsembleDistanceConfig.w_semantic` |
| Temporal weight | 0.25 | `EnsembleDistanceConfig.w_temporal` |
| Narrative weight | 0.30 | `EnsembleDistanceConfig.w_narrative` |
| Log-temporal tau | 1,800,000 ms (30 min) | `EnsembleDistanceConfig.log_temporal_tau_ms` |
| Log-temporal max gap | 14,400,000 ms (4h) | `EnsembleDistanceConfig.max_temporal_gap_ms` |
| Hard temporal cutoff | True | `EnsembleDistanceConfig.hard_temporal_cutoff` |
| Short-circuit cap (same thread) | 0.20 | `EnsembleDistanceConfig.shortcircuit_cap` |
| Short-circuit cap (fuzzy thread) | 0.30 | Research `_ensemble_distance()` |
| Thread semantic same threshold | 0.78 | `_cd_narrative()` T2 tier |
| Thread semantic fuzzy threshold | 0.60 | `_cd_narrative()` T2b tier, `thread_fuzzy_threshold` |

**Splitter Parameters (proven in `run_matrix.py` `research_balanced_v1`)**:

| Parameter | Proven Value | Source |
| --------- | ------------ | ------ |
| Hard time gap | 480 min (8h) | `ResearchSplitConfig.hard_time_gap_minutes` |
| Hard episode span | 1,080 min (18h) | `ResearchSplitConfig.hard_episode_span_minutes` |
| Hard context gap | 180 min (3h) | `ResearchSplitConfig.hard_context_gap_minutes` |
| Hard context semantic threshold | 0.55 | `ResearchSplitConfig.hard_context_semantic_threshold` |
| Soft split threshold | 0.45 | `ResearchSplitConfig.soft_split_threshold` |
| Same-thread bonus | -0.45 | `_research_boundary_decision()` |
| Thread mismatch penalty | +0.35 | `_research_boundary_decision()` |
| Partial thread mismatch penalty | +0.10 | `_research_boundary_decision()` |
| Low semantic penalty (< 0.55) | +0.30 | `_research_boundary_decision()` |
| Medium semantic penalty (< 0.70) | +0.15 | `_research_boundary_decision()` |
| Zero participant overlap penalty | +0.15 | `_research_boundary_decision()` |
| Social context change penalty | +0.10 | `_research_boundary_decision()` |
| Place change penalty | +0.15 | `_research_boundary_decision()` |
| Activity type change penalty | +0.10 | `_research_boundary_decision()` |
| Time gap >= 360 min penalty | +0.30 | `_research_boundary_decision()` |
| Time gap >= 180 min penalty | +0.20 | `_research_boundary_decision()` |
| Time gap >= 90 min penalty | +0.10 | `_research_boundary_decision()` |
| Strong semantic bonus (>= 0.86) | -0.20 | `_research_boundary_decision()` |
| Participant overlap >= 0.50 bonus | -0.15 | `_research_boundary_decision()` |
| Same goal context bonus | -0.10 | `_research_boundary_decision()` |
| Same place + gap < 120 min bonus | -0.05 | `_research_boundary_decision()` |

**Merge Parameters (proven in `r2_final_pipeline.py`)**:

| Parameter | Proven Value | Source |
| --------- | ------------ | ------ |
| Same-thread merge centroid sim | >= 0.70 | `merge_same_thread_clusters()` |
| Same-thread merge max temporal gap | 14,400,000 ms (4h) | `merge_same_thread_clusters()` |
| Thread purity threshold for merge | >= 80% | `merge_same_thread_clusters()` |

**Narrative Distance Tier Chain (proven in `_cd_narrative()`)**:

| Tier | Condition | Distance | Confidence |
| ---- | --------- | -------- | ---------- |
| T1 | Both have thread_id, exact match | 0.0 | 1.0 |
| T2 | Both have thread_id, UltraBERT sim >= 0.78 | 1.0 - sim | 0.7 |
| T2b | Both have thread_id, UltraBERT sim >= 0.60 | 1.0 - sim | 0.45 |
| T3 | Both have thread_id, genuinely different | 1.0 | 0.9 |
| T4 | Both have goal_context, exact match | 0.1 | 0.6 |
| T5 | Both have goal_context, different | 0.85 | 0.4 |
| T6 | One has thread/goal, other does not | 0.5 | 0.2 |
| MISS | Neither has any narrative signal | 0.5 | 0.0 (excluded) |

**HDBSCAN Parameters (proven in `research_distance.py`)**:

| Parameter | Proven Value | Source |
| --------- | ------------ | ------ |
| min_cluster_size | 2 | `cluster_with_ensemble_distance()` |
| min_samples | 1 | `cluster_with_ensemble_distance()` |
| cluster_selection_method | leaf | `cluster_with_ensemble_distance()` |
| allow_single_cluster | False | `cluster_with_ensemble_distance()` |
| Noise rescue outlier threshold | 0.5 | `_rescue_noise()` |

M3 research tracks (M3-RSCH-01 through M3-RSCH-07) should use these values as their starting
point. If research finds better values, document the improvement with before/after metrics.
If research cannot improve on the baseline, adopt the baseline as-is.

#### Milestone 3 Research Exit Gate

| Gate | Requirement |
| ---- | ----------- |
| G1 | 6D weight sweep and log-temporal curve comparison artifacts exist and are runnable |
| G2 | Boundary scoring and rescue scoring comparison artifacts exist |
| G3 | Sparse-signal fallback behavior is benchmarked |
| G4 | Signal-family ablation report from M2 is extended to cover M3 formula decisions |
| G5 | `results/m3_decision_memo.md` names approved weights, curves, and signal roles |
| G6 | Every parameter that deviates from the Research-Proven Baseline above has a documented improvement justification with before/after metrics |

### Epic 3.1: 6-Dimensional CompositeDistance

**Discovery Reference**: Sections 17.6 and 20.7
**Repo Status**: OPEN

#### Epic 3.1 Verified Current State

- `CompositeDistance` still uses only semantic cosine distance plus linear temporal distance.
- EventAdapter exposes some additional social/spatial/narrative/affective signals, but the `EventLike` protocol in `composite_distance.py` only declares `event_id`, `timestamp`, and `embedding_768` -- the protocol itself must be extended before any new dimension can read event fields.
- No spatial, social, affective, or narrative distance components exist in production R2 clustering.

#### Epic 3.1 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 3.1.0 extend or replace `EventLike` protocol | OPEN | Extend `EventLike` to declare all fields needed by 6D distance (spatial, social, affective, narrative, temporal-support) with `Optional` typing and neutral defaults. This is a prerequisite for 3.1.2-3.1.6 and must be coordinated with `SplittableEvent` (Epic 3.3) and rescue event access (Epic 3.4). |
| 3.1.1 extend params model | OPEN | Define neutral parameter structure that supports 6D weights, per-dimension fallback policies, and weight-redistribution rules for missing signals. |
| 3.1.2 add spatial distance | OPEN | Use `place_id`/`geohash_6`/location hierarchy fallback chain. Neutral fallback when user has not granted location permission or spatial data is absent. |
| 3.1.3 add social distance | OPEN | Use participants, social context, intimacy, and relationships. Neutral fallback for solo events or missing participant data. |
| 3.1.4 add affective distance | OPEN | Use VAD plus novelty/surprise signals. Neutral fallback when affect extraction is sparse or absent. |
| 3.1.5 add narrative distance with short-circuit override | OPEN | Use `narrative_thread_id`, `goal_context`, `temporal_orientation`, and `intent_type` as a tiered narrative distance. Implement the mandatory **narrative short-circuit override**: when both events share the same `narrative_thread_id` and the total composite distance `d(i,j) > 0.4`, clamp `d(i,j) = min(d(i,j), 0.20)`. This is the single most important rule in the target design: same thread always clusters together, overridden only by the 4h hard temporal cutoff. Neutral fallback when no thread ID is available. |
| 3.1.6 preserve graceful degradation | OPEN | Implement the signal-availability mask and proportional weight redistribution described in the M3 Fallback Design Principle. Ensure missing MW-v2 fields degrade cleanly to neutral distances without crashing, false-binding, or false-separation. |

#### Epic 3.1 Issue Execution Checklist

##### Issue 3.1.0 Extend or replace the `EventLike` protocol

| Item | Detail |
| ---- | ------ |
| Goal | Make `EventLike` declare all fields needed by the 6D distance model so downstream code uses typed access instead of `getattr` guessing. |
| Read | `k0/modules/consolidation/algorithms/composite_distance.py` `EventLike` protocol; `k0/modules/consolidation/algorithms/episode_splitter.py` `SplittableEvent` protocol; `k0/modules/consolidation/algorithms/episodic_hdbscan.py` rescue event access; `k0/pipelines/p03/phases/r2_episodic_integrator.py` `EventAdapter`. |
| Change | Extend `EventLike` with `Optional` typed fields for `geohash_6`, `place_id`, `location_hierarchy_json`, `social_context`, `participants_json`, `participant_relationships_json`, `social_intimacy`, `affect_valence`, `affect_arousal`, `affect_dominance`, `surprise_level`, `narrative_thread_id`, `goal_context`, `intent_type`, and temporal-support fields. All new fields default to `None`. Coordinate with `SplittableEvent` so both protocols share a consistent enriched-event contract rather than diverging. |
| Core idea | The protocol is the contract between EventAdapter and all distance/splitter/rescue consumers. If the protocol stays minimal, every consumer reinvents `getattr` fallback logic independently and inconsistently. |
| Tests | Add protocol compliance tests proving EventAdapter satisfies the enriched `EventLike` and `SplittableEvent` contracts. Add missing-field tests proving `None` defaults do not crash any consumer. |
| Success criteria | All M3 consumers use typed protocol access. No `getattr` fallback for fields that belong in the protocol. Both protocols are coordinated and EventAdapter satisfies both. |

**Codebase Reality** (verified 2026-03-07):

`EventLike` protocol in `composite_distance.py` (L120-L137) declares only 3 fields:

- `event_id: str` (L131)
- `timestamp: int` (L136)
- `embedding_768: Optional[List[float]]` (L141)

`SplittableEvent` protocol in `episode_splitter.py` (L112-L126) declares only 2 fields:

- `event_id: str` (L119)
- `timestamp: int` (L124)

`ClusterableEvent` protocol in `episodic_hdbscan.py` (L128-L145) declares 4 fields (adds `sentiment_score`).

All three protocols are independent -- no shared base, no coordination. Meanwhile, `EventAdapter` in `r2_episodic_integrator.py` (L109-L299) already exposes 23+ properties including social (L178-L189), narrative (L196-L204), affective (L210-L220), and temporal (L237-L249) -- but no algorithm consumes them because the protocols don't declare them.

`P03EventState` (event_state.py) has ALL required M3 fields with defaults: spatial (L163-L168: place_id, geohash_6, location_hierarchy_json, spatial_context_json, location_name, location_type), social (L156-L160: participants_json, social_context, social_intimacy, num_participants, is_solo_event; L225: participant_relationships_json), affect (L138-L139: valence/arousal; L216: dominance; L229: surprise_level), narrative (L208-L214: thread_id, arc_position, goal_context, intent_type).

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.2: The proven ensemble uses 3D (semantic=0.45, temporal=0.25, narrative=0.30) with spatial/social/affective at weight 0.0. Section 5.3: "6D distance -- spatial, social, affective: Tested in V12/V15/V18, no improvement over 3D. These dimensions have too many missing values in real data." However, the protocol extension should declare all 6D fields to support future M3-RSCH-06 ablation and fallback-chain testing, even if initial weights are 0.0.

**Implementation Detail**:

1. Unify all three protocols into a single `EnrichedEvent` protocol (or extend `EventLike` as the shared base). Fields: `event_id`, `timestamp`, `embedding_768`, plus Optional fields for all 6D dimensions.
2. Required Optional fields for protocol: `geohash_6`, `place_id`, `location_hierarchy_json`, `participants_json`, `participant_relationships_json`, `social_context`, `social_intimacy`, `affect_valence`, `affect_arousal`, `affect_dominance`, `surprise_level`, `narrative_thread_id`, `goal_context`, `intent_type`, `temporal_orientation`, `temporal_links_json`, `time_of_day_bucket`, `circadian_slot`, `is_weekend`, `extraction_sequence`, `sentiment_score`, `activity_type`, `num_participants`, `is_solo_event`.
3. All new fields default to `None`. Existing consumers remain unbroken because they only access the fields they need.
4. Verify EventAdapter satisfies the enriched protocol via a `Protocol` compliance test.
5. Coordinate with `SplittableEvent` (Issue 3.3.0) -- ideally both share the same enriched protocol or `SplittableEvent` extends `EventLike`.

##### Issue 3.1.1 Extend the parameter model

| Item | Detail |
| ---- | ------ |
| Goal | Replace the current 2D distance config with a neutral structure that can express semantic, temporal, spatial, social, affective, and narrative weights plus fallback rules. |
| Read | `k0/modules/consolidation/algorithms/composite_distance.py`; EventAdapter signal surface in `k0/pipelines/p03/phases/r2_episodic_integrator.py`; Milestone 3 target channels in this plan. |
| Change | Introduce a neutral distance-config model that separates dimension weights, hard gates, fallback policies, and optional support-signal modifiers. Include per-dimension fallback policy (neutral value, weight redistribution rule) and signal-availability mask tracking. |
| Core idea | The current config still encodes a semantic-plus-time worldview. Milestone 3 needs a configuration layer that can carry the full channel model without another rename later. |
| Tests | Add config serialization/validation tests covering all six core dimensions, missing-signal defaults, and weight-redistribution behavior when dimensions are absent. |
| Success criteria | Distance configuration is dimension-complete, algorithm-neutral, fallback-aware, and ready for later adaptive/gating work. |

**Codebase Reality** (verified 2026-03-07):

Current distance config is `DBSCANParams` (composite_distance.py L53-L113), a frozen dataclass with:

- `eps: float = 0.15` (L68)
- `min_samples: int = 2` (L69)
- `temporal_weight: float = 0.3` (L70)
- `max_temporal_gap_hours: float = 4.0` (L71)
- Derived: `semantic_weight = 1.0 - temporal_weight` (L79)

This is a 2-weight system: `semantic_weight` + `temporal_weight` = 1.0. There is no room for spatial, social, affective, or narrative weights. The class name (`DBSCANParams`) is scheduled for rename in Epic 2.1 Issue 2.1.1.

The research ensemble config (`EnsembleDistanceConfig` in `poc/r2_phase_research/research_distance.py`) already implements the target model: per-dimension weights, per-dimension confidence, short-circuit, fallback chain. This is the reference implementation.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.2.1: Proven weights are semantic=0.45, temporal=0.25, narrative=0.30, spatial=0.0, social=0.0, affective=0.0. Section 2.2: Core formula: `d = sum(w_i * conf_i * d_i) / sum(w_i * conf_i)` -- confidence-weighted redistribution. M3-RSCH-05 (fallback neutrality) is required to validate weight redistribution under sparse signals.

**Implementation Detail**:

1. Replace `DBSCANParams` (after M2 rename to `ClusteringDistanceParams`) with a new `EnsembleDistanceConfig` dataclass. Fields: `weights: Dict[str, float]` for 6 dimensions, `fallback_policy: Dict[str, FallbackPolicy]`, `max_temporal_gap_ms: int`, `shortcircuit_enabled: bool`, `shortcircuit_cap: float = 0.20`, `shortcircuit_activation: float = 0.4`.
2. Each dimension weight defaults to the proven values (sem=0.45, temp=0.25, narr=0.30, spatial=0.0, social=0.0, affective=0.0). Weights with 0.0 are effectively disabled.
3. Add `FallbackPolicy` enum or config: `NEUTRAL_05` (contribute 0.5 distance), `REDISTRIBUTE` (remove from denominator), `EXCLUDE` (skip dimension entirely). Research uses REDISTRIBUTE (confidence-weighted denominator).
4. Keep `max_temporal_gap_ms` as the hard gate parameter.
5. Port the research `EnsembleDistanceConfig` from `poc/r2_phase_research/research_distance.py` as the reference.

##### Issue 3.1.2 Add spatial distance

| Item | Detail |
| ---- | ------ |
| Goal | Add a spatial component that goes beyond raw geohash mismatch. |
| Read | `k0/modules/consolidation/algorithms/composite_distance.py`; EventAdapter spatial fields in `r2_episodic_integrator.py`; temp design spatial channel notes. |
| Change | Define a spatial comparator chain using `place_id` first, then `location_hierarchy_json`, then `geohash_6`, with neutral fallback when spatial data is absent. |
| Core idea | Geohash-only comparison is a weak proxy. The spatial distance needs semantic location identity, not just coordinate proximity. |
| Tests | Add cases for same-place/different-geohash, related hierarchy/same venue family, and missing-spatial-data neutrality. |
| Success criteria | Spatial distance distinguishes same-place continuity from merely nearby or unrelated locations. |

**Codebase Reality** (verified 2026-03-07):

No spatial distance exists in `CompositeDistance`. The current formula (L183-L224) is purely semantic + temporal. The splitter has a spatial channel via `_detect_break()` (L340-L349) using `getattr(prev, "location_geohash", None) or getattr(prev, "geohash_6", None)` with `_geohash_distance()` (L386-L424) as a character-prefix comparator.

EventAdapter exposes no spatial fields directly -- `geohash` (L129) and `geohash_6` (L135) are exposed for the splitter, but `place_id`, `location_hierarchy_json`, and `spatial_context_json` are NOT on EventAdapter.

P03EventState has all spatial fields: `place_id` (L166), `geohash_6` (L165), `location_hierarchy_json` (L167), `spatial_context_json` (L168), `location_name` (L163), `location_type` (L164).

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.2.1: Spatial weight = 0.0 in proven config. Section 5.3: "Spatial, social, affective signals are too sparse in current data. Adding them adds noise without improving clustering." However, the research corpus is a single-family dataset -- spatial signals may be more useful in multi-location families. M3-RSCH-06 (signal ablation) must determine if spatial earns its weight.

The splitter already uses geohash for boundary detection (research_balanced_v1 `place_change_penalty: 0.15`), confirming spatial signal has value for splitting even if not yet for distance.

**Implementation Detail**:

1. Add `place_id`, `location_hierarchy_json`, `spatial_context_json`, `location_name`, `location_type` to EventAdapter.
2. Implement spatial distance function with fallback chain: `place_id` exact match (d=0.0, conf=1.0) -> `location_hierarchy_json` overlap (d=hierarchy_distance, conf=0.7) -> `geohash_6` prefix comparison (d=geohash_distance, conf=0.5) -> MISS (d=0.5, conf=0.0 = excluded from ensemble).
3. Wire into ensemble with weight=0.0 (disabled by default). Enable via config when M3-RSCH-06 ablation justifies it.
4. Spatial distance must handle: both events at same place, both at different places, one/both missing spatial data entirely.

##### Issue 3.1.3 Add social distance

| Item | Detail |
| ---- | ------ |
| Goal | Incorporate who was present and what the social frame was. |
| Read | EventAdapter fields `participants_json`, `participant_relationships_json`, `social_context`, and `social_intimacy`; current centroid/episode aggregation helpers that already parse participants. |
| Change | Add participant overlap, relationship-role similarity, and social-context similarity into a single social distance component with graceful fallback for sparse participant data. |
| Core idea | Episodes often stay coherent because the social setting is stable even when text semantics drift. |
| Tests | Add cases for same participants/different topic, different participants/similar topic, and solo-to-group transitions. |
| Success criteria | Socially consistent events can bind despite modest semantic drift, while socially incompatible events are penalized. |

**Codebase Reality** (verified 2026-03-07):

No social distance exists in `CompositeDistance`. EventAdapter exposes `social_context` (L178), `social_intimacy` (L184), and `participants_json` (L189) but no algorithm consumes them for distance. The splitter has no social channel -- participant data is not used in `_detect_break()`.

P03EventState social fields: `participants_json` (L156), `num_participants` (L157), `social_context` (L158), `social_intimacy` (L159), `is_solo_event` (L160), `participant_relationships_json` (L225).

The research splitter config already includes social signals: `participant_zero_penalty: 0.15` and `participant_overlap_bonus: 0.15` (Section 2.1), confirming social context has value for boundary detection.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.2.1: Social weight = 0.0 in proven config. M5-RSCH-01 (Section 12.3): Hebbian co-occurrence boost uses participant co-occurrence at the distance level (5/8 -> 8/8 scenarios). This is a social-distance-like signal operating outside the ensemble formula -- applied as a multiplicative boost. Section 11.6 (M4-RSCH-04): Social coherence sub-dimension = 0.3920 post-correction (strongest coherence signal).

Social context is confirmed high-value for quality assessment and Hebbian boost, even though it didn't improve the ensemble distance formula directly.

**Implementation Detail**:

1. Implement social distance function: participant Jaccard overlap (d=1-overlap, conf=1.0) -> social_context match (d based on context similarity, conf=0.6) -> num_participants similarity (d=|diff|/max, conf=0.3) -> MISS (d=0.5, conf=0.0).
2. Wire into ensemble with weight=0.0 (disabled by default). The Hebbian boost (M5) provides the social binding pathway at scale=0.10, cap=0.05.
3. Consider whether social distance and Hebbian boost are complementary or redundant. If Hebbian already captures participant co-occurrence, social distance may only add value for non-participant social signals (context, intimacy).
4. Add `participant_relationships_json` to EventAdapter for relationship-role similarity.

##### Issue 3.1.4 Add affective distance

| Item | Detail |
| ---- | ------ |
| Goal | Use affect to separate emotionally distinct contexts. |
| Read | EventAdapter affect fields `affect_valence`, `affect_arousal`, `affect_dominance`, `surprise_level`, `salience_score`; current `composite_distance.py`. |
| Change | Add an affective distance term based on VAD delta plus optional surprise/salience modulation where evidence shows it helps. |
| Core idea | Emotionally opposite events can be narratively adjacent yet episodically distinct; the distance model needs to see that. |
| Tests | Add low-VAD-delta and high-VAD-delta scenarios, plus sparse-affect fallback coverage. |
| Success criteria | Affective contrast influences pairwise distance without overwhelming stronger semantic or social continuity. |

**Codebase Reality** (verified 2026-03-07):

No affective distance exists in `CompositeDistance`. EventAdapter exposes `affect_valence` (L210), `affect_arousal` (L215), `affect_dominance` (L220), `sentiment_score` (L225), and `salience_score` (L232) but none are used by the distance formula. Only `sentiment_score` is consumed -- by `ClusterableEvent` protocol for HDBSCAN's `_create_cluster()` dominant sentiment calculation (L524-L530).

P03EventState affect fields: `affect_valence` (L138), `affect_arousal` (L139), `affect_dominance` (L216), `surprise_level` (L229), `salience_score` (L140), `sentiment_score` (L131), `novelty_score` (L143).

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.2.1: Affective weight = 0.0 in proven config. Section 11.6 (M4-RSCH-04): Affective coherence sub-dimension was one of the 5 coherence dimensions measured -- spatial=0.1732, narrative=0.3386, social=0.3920 dominated, suggesting affective coherence is less discriminating. Section 11.9 (M4-RSCH-07): `novelty` signal was best marginal contributor but only +0.0008 MRR -- effectively SUMMARY-ONLY.

Affective distance is the weakest candidate for ensemble inclusion based on current evidence.

**Implementation Detail**:

1. Implement affective distance: VAD Euclidean distance (d=||VAD_a - VAD_b||/sqrt(3), conf=1.0 when all 3 present) -> partial VAD (conf=0.5 when only valence present) -> MISS (d=0.5, conf=0.0).
2. Optionally modulate with surprise_level: high surprise delta could amplify affective distance.
3. Wire into ensemble with weight=0.0 (disabled). M3-RSCH-06 ablation must show affective distance contributes before enabling.
4. Keep as lowest priority among the 3 new dimensions (spatial > social > affective based on coherence evidence).

##### Issue 3.1.5 Add narrative distance with short-circuit override

| Item | Detail |
| ---- | ------ |
| Goal | Make the distance model aware of story/thread continuity and enforce the narrative short-circuit guarantee. |
| Read | EventAdapter fields `narrative_thread_id`, `goal_context`, `temporal_orientation`, `intent_type`; existing episode-matching logic that already queries `st_epi` by `narrative_thread_id`; temp design Subsystem 3 Dimension 6 and narrative short-circuit override. |
| Change | (1) Add tiered narrative distance: `narrative_thread_id` match/mismatch (tier 1), `goal_context` (tier 2), `temporal_orientation` (tier 3), `intent_type` (tier 4), neutral 0.5 fallback. (2) Implement the **narrative short-circuit override** as a post-composite-sum hook: if both events share the same `narrative_thread_id` and the total `d(i,j) > 0.4`, clamp `d(i,j) = min(d(i,j), 0.20)`. The override threshold (0.20) and activation threshold (0.4) must be configurable in the distance params model. The only thing that overrides the short-circuit is the hard temporal cutoff (absolute time gap exceeding `max_gap_ms`). |
| Core idea | The target design declares narrative thread identity as "the single most important rule in the entire system" (Rubin 2006 Basic Systems Model). Two events on the same thread 3 hours apart are ONE episode. Two events 5 minutes apart on different threads are DIFFERENT episodes. The short-circuit ensures this guarantee is enforced at the distance level, not left to HDBSCAN to discover. |
| Tests | (1) Same thread + semantically different events = short-circuit clamps total distance. (2) Same thread + close events (d < 0.4) = no clamp needed, distance stays as-is. (3) Different threads + similar events = no short-circuit, normal distance. (4) Same thread + time gap exceeding hard cutoff = short-circuit does NOT apply (temporal cutoff wins). (5) One or both threads missing = short-circuit inactive, neutral narrative distance. |
| Success criteria | Narrative short-circuit is active, configurable, and demonstrably prevents same-thread events from being split across clusters by any other dimension. |

##### Issue 3.1.6 Preserve graceful degradation

| Item | Detail |
| ---- | ------ |
| Goal | Ensure the 6D model still behaves safely when only a subset of signals is present. |
| Read | The final distance-config model and EventAdapter field coverage; temp design fallback notes. |
| Change | Define neutral-value behavior, missing-signal masks, and per-dimension fallback policies so absent signals do not create accidental penalties or rewards. |
| Core idea | A richer distance model is only viable if sparse batches degrade predictably instead of collapsing into noisy pseudo-precision. |
| Tests | Add ablation-style cases where individual dimensions are missing and verify pairwise distance stays stable and interpretable. |

**Discovery Reference**: Sections 17.4.2 and 20.5 axis 2
**Repo Status**: OPEN

### Epic 3.2 Verified Current State

- Temporal distance remains linear with a hard 4-hour cutoff.
- No log-temporal or confidence-weighted temporal distance exists.

#### Epic 3.2 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 3.2.1 replace linear normalization | OPEN | Introduce log or exponential temporal compression consistent with the neuromorphic design. |
| 3.2.2 incorporate timestamp quality | OPEN | Use `temporal_source` to down-weight degraded timestamps where appropriate. |
| 3.2.3 verify hard-cutoff semantics | OPEN | Reconfirm how the hard 4-hour temporal gate interacts with the new temporal distance. |

#### Epic 3.2 Issue Execution Checklist

##### Issue 3.2.1 Replace linear normalization

| Item | Detail |
| ---- | ------ |
| Goal | Replace the current linear time-distance term with a compressed curve that better reflects episodic binding. |
| Read | `k0/modules/consolidation/algorithms/composite_distance.py` temporal formula; discovery and temp-design temporal notes; Milestone 2 replay findings if available. |
| Change | Introduce a logarithmic or exponential temporal-distance function and make the exact curve explicit in configuration or formula helpers. |
| Core idea | Linear time normalization over-penalizes moderate gaps and under-expresses near-time binding. |
| Tests | Add pairwise tests showing the new curve compresses far gaps and differentiates near gaps more meaningfully than the current linear function. |
| Success criteria | Temporal distance no longer scales linearly across the full window and the chosen curve is documented and test-covered. |

**Codebase Reality** (verified 2026-03-07):

Current temporal distance formula in `composite_distance.py` `_normalized_time_distance()` (L349-L361):

```python
def _normalized_time_distance(self, time_diff_ms: int) -> float:
    return min(1.0, time_diff_ms / self.params.max_temporal_gap_ms)
```

Purely linear. Ramps from 0.0 at t=0 to 1.0 at t=max_gap (4h = 14,400,000 ms). No logarithmic compression, no curve shape parameter, no tau constant.

Hard cutoff at L199: `if time_diff_ms > self.params.max_temporal_gap_ms: return float("inf")` -- events beyond 4h cannot cluster.

The research ensemble uses log-compressed temporal distance (research_distance.py), which is the proven replacement.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.2.1: Temporal weight = 0.25 in proven ensemble. The ensemble uses a log-compressed temporal distance function (not the linear `min(1.0, diff/max)`). Section 5.1: "New production: Confidence-weighted 3D ensemble (semantic 0.45, temporal 0.25, narrative 0.30) with log-compressed temporal." M3-RSCH-02 is specifically designed to validate the curve choice: "Which log-temporal tau and curve shape best match neuromorphic episodic binding?"

Section 3: Phase progression shows temporal distance improvement contributed to proxy composite rising from 0.8068 (Phase 1) to 0.8692 (Phase 2).

**Implementation Detail**:

1. Replace `_normalized_time_distance()` with log-compressed formula from research. Reference implementation in `research_distance.py`.
2. Formula: `d_temporal = log(1 + time_diff_ms / tau) / log(1 + max_gap_ms / tau)`. Tau controls compression -- small tau = steep early, flat later; large tau = nearly linear.
3. Add `temporal_tau_ms` as a configurable parameter in the ensemble distance config. Default from research calibration.
4. Keep hard cutoff at `max_temporal_gap_ms` as a safety gate: events beyond this threshold get `d=inf` regardless of curve shape.
5. Temporal dimension returns `(distance, confidence)` where confidence = 1.0 (timestamp always available).
6. M3-RSCH-02 must compare: linear (current), logarithmic, and exponential curves on the replay corpus before locking production parameters.

##### Issue 3.2.2 Incorporate timestamp quality

| Item | Detail |
| ---- | ------ |
| Goal | Make degraded timestamps less authoritative in temporal distance. |
| Read | `temporal_source` usage in `r2_episodic_integrator.py`; Milestone 1 timestamp-chain notes; final distance-config model. |
| Change | Add timestamp-quality-aware weighting or confidence attenuation so `mw_resolved` and `ner_temporal` are treated differently from `event_time`, `envelope_ts`, or `now`. |
| Core idea | A sophisticated temporal formula still fails if it treats guessed timestamps as exact. |
| Tests | Add scenarios where identical event pairs receive different temporal influence depending on timestamp provenance. |
| Success criteria | Temporal distance is measurably less brittle on degraded timestamp paths without collapsing into neutrality everywhere. |

**Codebase Reality** (verified 2026-03-07):

`temporal_source` exists on P03EventState (L220) as `str` with default `""`. It tracks timestamp provenance (e.g., `mw_resolved`, `ner_temporal`, `event_time`, `envelope_ts`, `now`). R0 batch selector already applies the M1 timestamp preference chain: `conversation_anchor_ms` > `event_time_utc` > `created_at`.

EventAdapter exposes `temporal_resolved_epoch_ms` (L243) and `temporal_anchor_json` (L249) but NOT `temporal_source`. Neither `CompositeDistance` nor any other algorithm reads `temporal_source` to adjust confidence.

The ensemble distance formula's confidence-weighted approach naturally accommodates timestamp quality: if temporal_source indicates low quality, temporal confidence can be reduced, and weight redistributes to other dimensions.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 12.6 (M5-RSCH-07): `temporal_source` has 0/1360 coverage in the research corpus -- it's not yet propagated to st_hipp_events. BLOCKED for empirical validation. However, the confidence-weighted ensemble framework (Section 2.2) already supports the concept: temporal dimension returns `(distance, confidence)` where confidence can be degraded based on source quality.

M1 research (timestamp chain tests) validated that R0 prefers `conversation_anchor_ms` -- so most production events will have high-quality timestamps from the MW layer.

**Implementation Detail**:

1. Add `temporal_source` to EventAdapter properties.
2. Define timestamp quality tiers: `mw_resolved` -> conf=1.0, `conversation_anchor_ms` -> conf=1.0, `event_time_utc` -> conf=0.8, `created_at` -> conf=0.6, `envelope_ts` -> conf=0.4, `now`/empty -> conf=0.3.
3. Use temporal_source to set the temporal dimension's confidence in the ensemble formula. Low-quality timestamps get lower confidence -> less weight in the ensemble.
4. This is implementable NOW at the framework level but CANNOT be empirically validated until K1 populates `temporal_source` (M5-RSCH-07 blocker). Deploy with conservative confidence mapping (all sources >= 0.5) until empirical data is available.

##### Issue 3.2.3 Verify hard-cutoff semantics

| Item | Detail |
| ---- | ------ |
| Goal | Reconfirm whether the 4-hour gate remains a hard `inf` cutoff, becomes softer, or becomes dimension-specific. |
| Read | `CompositeDistance.compute()` and `compute_from_arrays()`; HDBSCAN rescue behavior; temp design temporal-binding expectations. |
| Change | Decide whether the hard cutoff remains global or becomes conditional, then apply that rule consistently in both scalar and matrix paths. |
| Core idea | Once temporal distance becomes logarithmic and context-aware, the old hard gate may be too rigid or may still be necessary as a safety brake. |
| Tests | Add tests for near-threshold, just-over-threshold, and context-rich same-thread events to ensure the gate behaves intentionally. |
| Success criteria | The final temporal gating rule is explicit, consistently enforced, and compatible with rescue and narrative binding logic. |

**Codebase Reality** (verified 2026-03-07):

Hard cutoff is enforced at two levels:

1. `CompositeDistance.compute()` L199: `if time_diff_ms > self.params.max_temporal_gap_ms: return float("inf")` -- global hard gate, returns infinity.
2. `CompositeDistance.build_distance_matrix()` L364-L404: calls `compute()` for each pair, so the hard gate is implicitly enforced in the matrix.
3. Splitter `SplitConfig.max_episode_hours = 4.0` (L76): Forces split on episodes spanning > 4h. This is a separate mechanism from the distance hard gate.
4. Research splitter: `hard_time_gap_minutes = 480` (8h silence) and `hard_episode_span_minutes = 1080` (18h span) -- different from the 4h distance gate.

The 4h gate interacts with narrative short-circuit: if two same-thread events are 5h apart, the hard cutoff returns `inf` and short-circuit cannot override it (the distance is already set before narrative checks). This is the correct priority: temporal hard cutoff > narrative short-circuit.

No configurable interaction between hard cutoff and rescue exists. Rescue operates on the precomputed distance matrix, so events > 4h apart already have `inf` distance and cannot be rescued into the same cluster.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.2.5: `noise_rescue_threshold: 0.5`. Research uses 4h hard cutoff in distance (same as production). The research splitter uses 8h hard gap (Section 2.1: `hard_time_gap_minutes: 480`) and 18h hard span -- but these are SPLITTER gates, not DISTANCE gates. The two are independent: distance 4h gate prevents clustering across 4h gaps; splitter 8h gate prevents sequences spanning 8h silence.

Section 6.3 Key Decision: Short-circuit is overridden by hard temporal cutoff. This is by design -- the plan issue text correctly states "The only thing that overrides the short-circuit is the hard temporal cutoff."

**Implementation Detail**:

1. Keep the 4h hard cutoff as `float("inf")` in the distance matrix. This is working correctly and is the foundation of temporal safety.
2. Clarify the interaction chain: hard cutoff (inf) > narrative short-circuit (0.20 cap) > ensemble distance. Document this priority in the ensemble distance config.
3. Consider whether the hard cutoff should become configurable (e.g., `max_temporal_gap_ms` in ensemble config vs a separate hard-gate parameter). Currently they are the same value.
4. The research splitter uses different thresholds (8h gap, 18h span) -- when the research splitter lands in production (it's already selected as the winner), the splitter and distance hard gates will operate at different time scales. Document this intentional divergence.
5. M3-RSCH-02 should test whether the hard cutoff should soften (sigmoid instead of step function) or remain a hard `inf` wall.

### Epic 3.3: Boundary Strength Scoring (EpisodeSplitter)

**Discovery Reference**: Section 18.8
**Repo Status**: OPEN

#### Epic 3.3 Verified Current State

- `EpisodeSplitter` can access some signals via `getattr` fallback, but the `SplittableEvent` protocol only declares `event_id` and `timestamp`. All other field access is untyped and inconsistent.
- The algorithm still uses a first-match-wins priority cascade.
- No multi-signal boundary score exists.

#### Epic 3.3 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 3.3.0 extend `SplittableEvent` protocol | OPEN | Extend `SplittableEvent` to declare all fields needed by 7-channel boundary scoring with `Optional` typing. Coordinate with `EventLike` (Issue 3.1.0) so both protocols share a consistent enriched-event contract. Implement the same fallback-chain principle: missing fields produce neutral boundary contributions, never crashes or false splits. |
| 3.3.1 replace first-match-wins logic | OPEN | Introduce weighted boundary accumulation instead of one winning signal. |
| 3.3.2 add narrative/social/affective/cognitive channels | OPEN | Expand splitter inputs to match the neuromorphic 7-channel boundary design. Each channel evaluator must implement the fallback chain: primary signal -> secondary signal -> neutral contribution. |
| 3.3.3 add sort verification | OPEN | Explicitly verify timestamp ordering before splitting. |
| 3.3.4 calibrate thresholds | OPEN | Replace hard single thresholds with tunable boundary score thresholds. |
| 3.3.5 implement narrative veto | OPEN | When both events share the same `narrative_thread_id` and the accumulated prediction error is below a narrative-veto threshold (design default 0.55), suppress the split. This enforces the neuroscience guarantee that a coherent story thread resists boundary detection (Zacks 2007: an active situation model resists updating). Only the Tier 1 hard boundaries (4h gap, landmark, flashbulb surprise) can override the narrative veto. |
| 3.3.6 record soft/weak boundary markers | OPEN | When prediction error falls between a soft threshold (design default 0.15) and the split threshold but does not trigger a split, record the event pair as a "weak boundary" marker. Weak boundary markers feed downstream consumers: episode sub-structure annotation, retrieval-hint generation, and HDBSCAN noise rescue guidance (Epic 3.4). |

#### Epic 3.3 Issue Execution Checklist

##### Issue 3.3.1 Replace first-match-wins logic

| Item | Detail |
| ---- | ------ |
| Goal | Replace the current priority cascade with an accumulated boundary score. |
| Read | `k0/modules/consolidation/algorithms/episode_splitter.py` `_detect_break()` and `SplitReason`; temp design boundary concepts. |
| Change | Introduce a weighted multi-signal boundary score and keep observability about which signals contributed to the split. |
| Core idea | The current splitter can only explain one reason per boundary even when multiple weaker signals should combine into a real break. |
| Tests | Add cases where no single signal crosses a threshold alone but multiple moderate signals together should split. |
| Success criteria | Boundary decisions are multi-signal and debuggable, not first-match-wins. |

**Codebase Reality** (verified 2026-03-07):

`_detect_break()` in episode_splitter.py (L316-L384) implements a strict first-match-wins priority cascade with 4 channels:

1. Location change (L340-L349): `getattr(prev, "location_geohash", None) or getattr(prev, "geohash_6", None)` -> `_geohash_distance() > threshold`
2. Activity change (L354-L363): `getattr(prev, "activity_type", None) != getattr(curr, "activity_type", None)`
3. Time gap (L366-L373): `curr.timestamp - prev.timestamp > config.time_gap_ms`
4. Hard limit (L376-L384): `curr.timestamp - episode_start_ts > config.max_episode_ms`

Each check returns `(True, SplitReason.X)` immediately on match -- no accumulation, no weighting. If location changes, the function returns without checking time gap, activity, or anything else.

The research splitter (`research_balanced_v1`) already implements accumulated scoring with penalties and bonuses (Section 2.1): `soft_split_threshold=0.45`, thread_mismatch_penalty=0.35, semantic_low_penalty=0.30, participant_zero_penalty=0.15, place_change_penalty=0.15, etc. This is the proven replacement.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.1: Winner is `research_balanced_v1` with accumulated penalty model. Uses `soft_split_threshold=0.45` -- split occurs when accumulated penalties exceed threshold. Includes bonuses (same_thread_bonus=0.45, participant_overlap_bonus=0.15, strong_semantic_bonus=0.20) that can PREVENT splits. Phase 1 results: 31 sequences from 1360 events, 3 noise, proxy=0.8068.

Section 6.3 Key Decision: "Pairwise contamination metric, not strict intra-group" -- the accumulation model directly supports multi-signal debugging.

**Implementation Detail**:

1. Replace the first-match-wins cascade with accumulated penalty/bonus model from `research_balanced_v1`.
2. Port the `ResearchSplitConfig` from `poc/r2_phase_research/research_distance.py` (or `run_matrix.py`) as the new `SplitConfig`.
3. Each channel contributes a penalty (positive) or bonus (negative) to an accumulator. Split when accumulator > `soft_split_threshold`.
4. Keep hard boundaries (4h gap, hard episode span) as Tier 1 overrides that bypass accumulation.
5. Return `SplitResult` with full channel contribution breakdown for observability.
6. Existing 37 splitter tests must be updated to the new accumulation model.

##### Issue 3.3.0 Extend `SplittableEvent` protocol

| Item | Detail |
| ---- | ------ |
| Goal | Make `SplittableEvent` declare all fields needed by 7-channel boundary scoring so the splitter uses typed access instead of fragile `getattr` fallback. |
| Read | `k0/modules/consolidation/algorithms/episode_splitter.py` `SplittableEvent` protocol and `_detect_break()` `getattr` usage; Issue 3.1.0 `EventLike` extension; `EventAdapter` property surface. |
| Change | Extend `SplittableEvent` with `Optional` typed fields for `narrative_thread_id`, `social_context`, `participants_json`, `affect_valence`, `affect_arousal`, `affect_dominance`, `identity_relevance`, `novelty`, `activity_type`, `geohash_6`, `place_id`, and any additional fields needed by the 7-channel design. All new fields default to `None`. Coordinate with `EventLike` (Issue 3.1.0) so both protocols share a consistent contract. |
| Core idea | Two protocols diverging into separate `getattr` patterns will produce inconsistent missing-field behavior across distance and splitting. They must be coordinated now. |
| Tests | Add protocol compliance tests proving EventAdapter satisfies enriched `SplittableEvent`. Add missing-field tests proving `None` defaults produce neutral boundary contributions. |
| Success criteria | All splitter channel evaluators use typed protocol access. No `getattr` guessing for fields that belong in the boundary contract. |

**Codebase Reality** (verified 2026-03-07):

`SplittableEvent` protocol in episode_splitter.py (L112-L126) declares only 2 fields:

- `event_id: str` (L119)
- `timestamp: int` (L124)

All other field access in `_detect_break()` uses `getattr` fallback:

- L340: `getattr(prev, "location_geohash", None) or getattr(prev, "geohash_6", None)`
- L354: `getattr(prev, "activity_type", None)`

No narrative, social, affective, or cognitive fields are declared or accessed. The research splitter accesses `narrative_thread_id`, `participants`, `place_id`, `activity_type`, and semantic similarity -- all via direct attribute access on enriched event objects.

This issue is tightly coupled with Issue 3.1.0 (extend `EventLike`). Both protocols need the same enriched event surface.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.1: The research splitter config includes `thread_mismatch_penalty` (needs `narrative_thread_id`), `participant_zero_penalty`/`participant_overlap_bonus` (needs `participants`), `place_change_penalty` (needs `place_id`/`geohash_6`), and `semantic_low_penalty`/`strong_semantic_bonus` (needs `embedding_768` for cosine similarity). All 7 channels need typed event access.

**Implementation Detail**:

1. Extend `SplittableEvent` to include all fields needed by the 7-channel boundary scorer. Ideally, share a single enriched event protocol with `EventLike` (Issue 3.1.0) so both distance and splitter consume the same contract.
2. Required fields (Optional, defaulting to None): `narrative_thread_id`, `participants_json`, `participant_relationships_json`, `social_context`, `affect_valence`, `affect_arousal`, `affect_dominance`, `surprise_level`, `geohash_6`, `place_id`, `activity_type`, `embedding_768`, `identity_relevance`, `novelty_score`, `goal_context`, `intent_type`.
3. Remove all `getattr` patterns in `_detect_break()` and replace with typed protocol access.
4. Verify EventAdapter satisfies the enriched `SplittableEvent` protocol.

##### Issue 3.3.2 Add narrative, social, affective, and cognitive channels

| Item | Detail |
| ---- | ------ |
| Goal | Expand the splitter beyond geohash/activity/time/hard-limit logic. |
| Read | Enriched `SplittableEvent` protocol from Issue 3.3.0; EventAdapter signal surface; temp design 7-channel boundary notes. |
| Change | Add channel evaluators for narrative discontinuity, participant/social changes, affective shifts, and cognitive-context changes. Each evaluator must implement the fallback chain: primary signal -> secondary signal -> neutral contribution (0.0 boundary score for that channel). |
| Core idea | The splitter should prevent cross-context contamination before clustering, not leave every non-temporal distinction for HDBSCAN to clean up later. |
| Tests | Add split/no-split scenarios for narrative-thread shifts, participant swaps, emotional discontinuity, and identity/novelty changes. Include sparse-signal scenarios where some channels have no data and must contribute neutral scores. |
| Success criteria | Splitter input coverage matches the intended multi-channel boundary design rather than only temporal and activity cues. Sparse signals do not cause false splits or crashes. |

**Codebase Reality** (verified 2026-03-07):

Current `_detect_break()` has 4 channels: location, activity, time_gap, hard_limit. `SplitReason` enum (L132-L140) has 5 values: NONE, LOCATION_CHANGE, ACTIVITY_CHANGE, TIME_GAP, HARD_LIMIT.

Missing channels that the research splitter already uses:

- **Narrative**: `thread_mismatch_penalty=0.35` when `narrative_thread_id` differs; `same_thread_bonus=0.45` when same thread
- **Semantic**: `semantic_low_penalty=0.30` when cosine similarity < 0.55; `strong_semantic_bonus=0.20` when > 0.86
- **Social**: `participant_zero_penalty=0.15` when no overlap; `participant_overlap_bonus=0.15` when strong overlap

Not yet in research splitter but planned for M3:

- **Affective**: VAD delta across boundary
- **Cognitive**: identity_relevance, novelty shifts

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.1: Research splitter uses 7 penalty/bonus channels (thread, semantic_low, semantic_mid, semantic_high, participant_zero, participant_overlap, place_change, activity_change). Section 4.1-4.2: Thread purity correction post-HDBSCAN catches contamination that the splitter misses. The combination of narrative splitter channel + post-cluster correction achieves 7/8 scenarios.

Section 6.3: "Event Segmentation Theory says an active situation model resists updating" -- the narrative channel (same_thread_bonus) is the implementation of this neuroscience principle in the splitter.

**Implementation Detail**:

1. Add `SplitReason` values: `NARRATIVE_CHANGE`, `SEMANTIC_SHIFT`, `SOCIAL_CHANGE`, `AFFECTIVE_SHIFT`, `COGNITIVE_SHIFT`. Keep existing values for backward compatibility.
2. Port the 7 penalty/bonus channels from research_balanced_v1. Each channel evaluator: (a) checks signal availability, (b) computes penalty or bonus, (c) accumulates to total.
3. For sparse signals: if a channel's required fields are all None, that channel contributes 0.0 (neutral -- neither penalty nor bonus). This is the same MISS pattern as ensemble distance.
4. Add affective channel: large VAD delta -> boundary penalty. Affective continuity -> no contribution.
5. Add cognitive channel: identity_relevance shift or novelty spike -> boundary penalty. Lower priority than narrative/social.
6. Each channel's contribution should be logged for observability (`SplitResult.channel_contributions: Dict[str, float]`).

##### Issue 3.3.3 Add sort verification

| Item | Detail |
| ---- | ------ |
| Goal | Ensure pre-splitting logic never runs on unsorted sequences silently. |
| Read | `episode_splitter.py` `split()` assumptions; R2 wrapper flow that prepares adapted events before splitting. |
| Change | Add explicit ordering verification or sort/assert behavior before splitting, with observability if out-of-order events are detected. |
| Core idea | Boundary scoring is meaningless on unsorted events; this should be asserted rather than assumed. |
| Tests | Add tests for already sorted, reverse-sorted, and partially disordered event lists. |
| Success criteria | Splitter ordering behavior is explicit and test-covered. |

**Codebase Reality** (verified 2026-03-07):

`EpisodeSplitter.split()` in episode_splitter.py iterates events sequentially and compares consecutive pairs via `_detect_break()`. There is no explicit sort or sort-verification step before iteration. The method assumes events arrive pre-sorted by timestamp.

In practice, R2 integrator sorts events before passing to splitter: `_split_events()` (L843) delegates to `EpisodeSplitter.split()` which receives adapted events. The EventAdapter wraps P03EventState objects that are already sorted by R0 batch selector's ORDER BY clause.

However, there is no assertion or guard -- if events arrive unsorted (e.g., due to a bug in the upstream phase or a new caller), boundary detection produces silently wrong results.

**Research Evidence**:

Research splitter in `r2_final_pipeline.py` also assumes pre-sorted input. No sort verification exists in research code either. The 1360-event corpus was always sorted by R0.

**Implementation Detail**:

1. Add `assert all(events[i].timestamp <= events[i+1].timestamp for i in range(len(events)-1))` at the top of `split()`, or sort explicitly.
2. Prefer assert-first approach: if events arrive unsorted, it's a bug in the caller that should be caught immediately, not silently masked by re-sorting.
3. Add observability: if out-of-order events are detected, log a warning with the affected event IDs before raising.
4. Add tests for sorted, reverse-sorted, partially disordered, and equal-timestamp event lists.
5. Lightweight change -- can be done early in the Epic 3.3 sequence.

##### Issue 3.3.4 Calibrate thresholds

| Item | Detail |
| ---- | ------ |
| Goal | Replace the current single-threshold constants with tunable boundary thresholds tied to research evidence. |
| Read | `SplitConfig`; Milestone 2 scenario/replay harness outputs; temp design channel guidance. |
| Change | Move boundary thresholds and weights into configuration and establish calibration guidance for each boundary dimension. |
| Core idea | Once the splitter becomes multi-signal, its thresholds can no longer live as implicit constants hidden in code. |
| Tests | Add config-boundary tests and replay-derived threshold regression cases. |
| Success criteria | Boundary thresholds are configurable, interpretable, and evidence-backed. |

**Codebase Reality** (verified 2026-03-07):

`SplitConfig` in episode_splitter.py (L47-L107) has 3 configurable parameters:

- `max_episode_hours: float = 4.0` (L76)
- `time_gap_minutes: float = 30.0` (L77)
- `geohash_distance_threshold: int = 4` (L78)

Activity change has no threshold -- it's a binary inequality check. There's no configurable split threshold for accumulated scores because the current splitter doesn't accumulate.

The research config (`ResearchSplitConfig`) has 13 configurable parameters including `soft_split_threshold=0.45`, individual penalties/bonuses, hard gap/span thresholds, and semantic similarity bands (0.55, 0.70, 0.86). These values were calibrated across 11 splitter variants in Phase 1.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.1: All 13 parameter values come from Phase 1 calibration (11 variants). The winner `research_balanced_v1` was selected because it tied at scenario_mean=0.6103 with fewer noise events. Section 3: Phase progression shows splitter calibration improved proxy from baseline to 0.8068.

M3-RSCH-03 is specifically designed to validate these thresholds against the full multi-signal boundary scorer: "Does multi-signal boundary scoring reduce cross-context contamination vs first-match-wins?"

**Implementation Detail**:

1. Port all 13 `ResearchSplitConfig` parameters to the production `SplitConfig`.
2. Keep the research-calibrated values as defaults. These are the empirically validated starting points.
3. Add M3-RSCH-03 as a prerequisite for threshold changes beyond the research defaults.
4. Document each threshold's purpose and calibration source in the config class docstring.
5. The existing 3 SplitConfig parameters (max_episode_hours, time_gap_minutes, geohash_distance_threshold) become subsumed by the richer config or kept as legacy compatibility aliases.

##### Issue 3.3.5 Implement narrative veto

| Item | Detail |
| ---- | ------ |
| Goal | Prevent the boundary detector from splitting inside a coherent narrative thread unless prediction error is extreme. |
| Read | `episode_splitter.py` boundary logic after Issue 3.3.1 weighted accumulation is in place; temp design Subsystem 2 Tier 2 narrative veto; Zacks (2007) sustained-attention model resistance. |
| Change | After computing `PredictionError(i, i+1)`, check: if both events share `narrative_thread_id` and `PredictionError < theta_narrative_veto` (configurable, design default 0.55), suppress the split. Tier 1 hard boundaries (4h gap, `memory_tier == "landmark"`, `surprise_level > 0.85`) still override the veto unconditionally. Add the veto threshold to `SplitConfig`. |
| Core idea | Event Segmentation Theory says an active situation model resists updating. A coherent narrative thread is the strongest situation model signal. Splitting inside an ongoing story requires dramatically higher prediction error than splitting between unrelated events. This is one of the three neuroscience guarantees in the target design. |
| Tests | (1) Same thread + moderate PE below veto threshold = NO split. (2) Same thread + extreme PE above veto threshold = split. (3) Same thread + Tier 1 hard boundary (4h gap) = split regardless of veto. (4) Different threads + moderate PE = split normally. (5) One or both threads missing = veto does not apply (neutral behavior). |
| Success criteria | Narrative veto is active, configurable, overridden only by Tier 1 hard boundaries, and falls back to no-op when thread signals are absent. |

**Codebase Reality** (verified 2026-03-07):

No narrative veto exists in the production splitter. `_detect_break()` has no concept of suppressing a split based on narrative continuity. The research splitter implements the veto as `same_thread_bonus=0.45` -- a negative penalty (bonus) that counteracts moderate accumulation when both events share the same `narrative_thread_id`. Combined with `soft_split_threshold=0.45`, a same-thread bonus alone can fully neutralize up to 0.45 worth of penalty.

This is functionally equivalent to a veto when the only penalties are moderate (< 0.45 + 0.45 = 0.90). The research config effectively prevents splitting same-thread events unless the accumulated penalty exceeds 0.90 (= thread bonus + threshold), which requires multiple strong signals simultaneously.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.1: `same_thread_bonus=0.45` in research_balanced_v1. Section 2.2.4: Short-circuit in distance (cap=0.20) is the distance-level veto; `same_thread_bonus` is the splitter-level veto. They reinforce each other: splitter keeps same-thread events in the same sequence, short-circuit keeps them in the same cluster.

Section 4.3: `clean_maya_fears_arc` must_link went from 0.33 to 1.00 after correction + merge. The narrative veto (splitter) + short-circuit (distance) + same-thread merge (post-cluster) form a three-layer guarantee that same-thread events stay together.

**Implementation Detail**:

1. In the accumulated boundary scorer, add narrative veto as: if both events share `narrative_thread_id`, subtract `same_thread_bonus` from accumulator. This is already proven in research.
2. Veto threshold concept from plan text (theta_narrative_veto=0.55) maps to: if accumulator < (threshold - bonus), the bonus prevents the split. With threshold=0.45 and bonus=0.45, this means accumulator must exceed 0.90 to split same-thread events.
3. Tier 1 hard boundaries (4h gap, hard episode span) bypass the accumulator entirely -- they fire before accumulation. This is the correct override order.
4. When `narrative_thread_id` is None on either event, bonus is not applied (neutral behavior).
5. The same_thread_bonus value (0.45) should be configurable in `SplitConfig`.

##### Issue 3.3.6 Record soft/weak boundary markers

| Item | Detail |
| ---- | ------ |
| Goal | Capture sub-threshold prediction error signals as weak boundary annotations for downstream consumers. |
| Read | `episode_splitter.py` split output; temp design Subsystem 2 Tier 3 soft boundaries; Epic 3.4 rescue scoring (consumer of weak markers). |
| Change | When `PredictionError >= theta_soft` (configurable, design default 0.15) but below the split threshold, annotate the event pair as a "weak boundary" in the split output. Add `theta_soft` to `SplitConfig`. Expose weak boundary markers so that (a) rescue scoring in Epic 3.4 can use them as cluster-boundary hints, (b) episode sub-structure can be annotated for retrieval, and (c) quality assessment can detect episodes with high internal weak-boundary density. |
| Core idea | Not all boundaries are binary. Sub-threshold prediction errors carry information about episode internal structure. Discarding them loses rescue guidance and retrieval-hint opportunities. |
| Tests | (1) PE between soft and split threshold = weak marker recorded, no split. (2) PE below soft threshold = no marker. (3) Weak markers are accessible to downstream rescue and quality consumers. (4) Weak marker output does not alter existing split behavior. |
| Success criteria | Weak boundary markers are produced, configurable, and consumed by at least one downstream path (rescue or quality). |

**Codebase Reality** (verified 2026-03-07):

No weak boundary concept exists in the production splitter. `_detect_break()` returns `Tuple[bool, str]` -- binary split/no-split with a reason string. There is no intermediate state between "split" and "continue."

The `SplitResult` from `split()` is a list of `EpisodeSequence` objects (event groups). No per-boundary metadata is preserved -- the information about WHY a boundary was detected (or almost detected) is lost.

The research splitter also does not record weak boundaries -- it only produces sequences. Weak boundary markers are a net-new M3 feature.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.1: `soft_split_threshold=0.45` is the split threshold. No "weak boundary" concept is tested in research. However, the accumulation model naturally produces intermediate scores. The weak boundary concept (plan text: `theta_soft=0.15`) would capture event pairs where accumulator is between 0.15 and 0.45 -- enough prediction error to be interesting but not enough to split.

Section 4.6 Remaining Weakness: `rescue_edge_family_overlap` scores 0.83 before correction. Weak boundary markers from the splitter could provide additional guidance to rescue scoring (Epic 3.4) for these edge cases.

**Implementation Detail**:

1. Extend `SplitResult` output to include `List[WeakBoundary]` alongside the split boundaries. Each `WeakBoundary` records: event_pair (i, i+1), accumulated_score, channel_contributions, narrative_thread_match.
2. Add `theta_soft: float = 0.15` to `SplitConfig`. When accumulator >= theta_soft but < soft_split_threshold, record a weak boundary.
3. Downstream consumers:
   - **Rescue scoring** (Epic 3.4): noise events near weak boundaries may belong to the "wrong" sequence. Rescue can check if a noise event falls near a weak boundary and adjust assignment.
   - **Quality assessment**: episodes with high internal weak-boundary density may be less coherent.
   - **Retrieval hints**: weak boundaries can annotate episode sub-structure for future retrieval.
4. Weak boundaries do NOT alter split behavior -- they are purely observational annotations.
5. This is lower priority than the core accumulation model (Issues 3.3.1-3.3.5). Can be deferred to late M3 if needed.

### Epic 3.4: HDBSCAN Noise Rescue Calibration

**Discovery Reference**: Sections 20.8 and 20.11
**Repo Status**: PARTIAL

#### Epic 3.4 Verified Current State

- Noise rescue exists today.
- Rescue remains threshold-based and distance-only.
- Narrative/social/spatial context is not part of rescue decisions.

#### Epic 3.4 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 3.4.0 establish dedicated HDBSCAN test coverage | OPEN | Discovery Section 20 flags EpisodicHDBSCAN as having 0 dedicated test files. Before restructuring rescue logic, establish a dedicated `test_r2_episodic_hdbscan.py` covering the surviving HDBSCAN clustering path, rescue flow, and weak-cluster creation. This test surface must exist before 3.4.1-3.4.3 modify rescue behavior. |
| 3.4.1 externalize rescue constants | OPEN | Remove hardcoded `0.3` / `0.2` style thresholds. |
| 3.4.2 add context-aware rescue scoring | OPEN | Incorporate narrative, social, spatial, and temporal rescue evidence. Use the enriched `EventLike` protocol from Issue 3.1.0 for typed field access. Implement fallback chain: rescue scoring uses available context fields and falls back to distance-only when context is absent. |
| 3.4.3 test weak-cluster behavior | OPEN | Add dedicated rescue-path unit coverage including context-aware and sparse-signal scenarios. |

#### Epic 3.4 Issue Execution Checklist

##### Issue 3.4.0 Establish dedicated HDBSCAN test coverage

| Item | Detail |
| ---- | ------ |
| Goal | Create a dedicated test file for EpisodicHDBSCAN before any rescue restructuring begins. |
| Read | `k0/modules/consolidation/algorithms/episodic_hdbscan.py`; existing integration tests in `tests/k0/pipelines/p03/test_r2_integration.py` that implicitly exercise HDBSCAN; discovery Section 20 (flags 0 dedicated tests). |
| Change | Create `tests/k0/pipelines/p03/test_r2_episodic_hdbscan.py` covering: basic clustering, noise detection, rescue assignment to existing clusters, weak-cluster creation, rescue rate tracking, outlier score behavior, and probability surface. |
| Core idea | Section 20 of the discovery doc flags HDBSCAN as having zero dedicated tests. Modifying rescue logic (3.4.1-3.4.3) without baseline HDBSCAN coverage means there is no regression safety net. |
| Tests | Cover the full HDBSCAN path: happy-path clustering, noise-dominant batches, rescue eligibility, weak-cluster formation, and distance-matrix interaction. |
| Success criteria | A dedicated HDBSCAN test file exists and passes before any rescue changes begin. |

**Codebase Reality** (verified 2026-03-07):

`test_r2_episodic_hdbscan.py` does NOT exist. The test file inventory under `tests/k0/pipelines/p03/` shows:

- `test_r2_composite_distance.py` (11 tests)
- `test_r2_episode_splitter.py` (37 tests)
- `test_r2_episodic_dbscan.py` (18 tests -- for the DBSCAN path being removed in M2)
- `test_r2_integration.py` (23 tests -- exercises HDBSCAN indirectly through full-phase integration)
- `test_r2_event_adapter.py` (50+ tests)

`episodic_hdbscan.py` (657 lines) has zero dedicated tests. The HDBSCAN clustering path, noise rescue logic (`_rescue_noise()` L431-L499), weak-cluster creation (L484-L499), outlier score handling, and probability surface are all untested directly. They are only exercised indirectly through `test_r2_integration.py`.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.2.5: HDBSCAN params (min_cluster_size=2, min_samples=1, leaf, precomputed, noise_rescue_threshold=0.5) are proven stable across all 68+ experiments. Section 8.2 (POC-08): Adaptive loop with HDBSCAN is stable (0 direction changes in 10 batches). The research pipeline uses HDBSCAN exclusively -- all quality metrics are based on HDBSCAN output.

**Implementation Detail**:

1. Create `tests/k0/pipelines/p03/test_r2_episodic_hdbscan.py`.
2. Required test cases:
   - **Basic clustering**: N events -> K clusters with expected assignments
   - **Noise detection**: Outlier events with distance > rescue threshold are classified as noise
   - **Rescue to existing cluster**: Noise point with distance < 0.3 to nearest cluster is rescued
   - **Weak cluster creation**: 2+ noise points within 0.2 of each other form a weak cluster
   - **Rescue rate tracking**: `rescued_count` and `noise_count` in output are accurate
   - **Outlier score surface**: `outlier_scores` array matches HDBSCAN output
   - **Probability surface**: `membership_probabilities` are accessible
   - **Distance matrix interaction**: Verify rescue operates on the precomputed distance matrix
   - **Edge cases**: 0 events, 1 event, all noise, all same cluster
3. Use the DBSCAN test file (`test_r2_episodic_dbscan.py`) as a structural reference for test organization.
4. This must be DONE before Issues 3.4.1-3.4.3 modify rescue behavior.

##### Issue 3.4.1 Externalize rescue constants

| Item | Detail |
| ---- | ------ |
| Goal | Remove hardcoded rescue distances and weak-cluster thresholds from `episodic_hdbscan.py`. |
| Read | `k0/modules/consolidation/algorithms/episodic_hdbscan.py` `_rescue_noise()` and `HDBSCANParams`. |
| Change | Move hardcoded values like `best_distance < 0.3` and nearby-noise `distance < 0.2` into explicit rescue configuration. |
| Core idea | Rescue logic is currently only partially configurable; the most behavior-defining constants are still buried in code. |
| Tests | Add tests that prove rescue behavior changes only through configuration, not hidden magic numbers. |
| Success criteria | Rescue thresholds are parameterized and no unexplained rescue constants remain in code. |

**Codebase Reality** (verified 2026-03-07):

Three hardcoded rescue constants in `episodic_hdbscan.py` `_rescue_noise()` (L431-L499):

| Constant | Value | Location | Purpose |
| -------- | ----- | -------- | ------- |
| Rescue distance threshold | `0.3` | L475 (`best_distance < 0.3`) | Max distance to assign noise to existing cluster |
| Weak cluster distance | `0.2` | L489 (`distances[idx, j] < 0.2`) | Max distance between noise points to form weak cluster |
| Noise rescue threshold | `0.5` | L87 (`noise_rescue_threshold`) in HDBSCANParams | Max outlier score for rescue eligibility |

The third constant (`noise_rescue_threshold=0.5`) is already in `HDBSCANParams` (L87) -- it's configurable. But the first two (`0.3` and `0.2`) are inline magic numbers with no config path.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.2.5: `noise_rescue_threshold: 0.5`. Research uses this same value. The 0.3 and 0.2 constants are not mentioned in research -- they were inherited from the original HDBSCAN implementation and never calibrated.

M3-RSCH-04 (rescue scoring research) is specifically designed to benchmark context-aware rescue. Externalizing constants is a prerequisite so the research can sweep them.

**Implementation Detail**:

1. Add to `HDBSCANParams`:
   - `rescue_max_distance: float = 0.3` -- max distance to assign noise to existing cluster
   - `weak_cluster_max_distance: float = 0.2` -- max distance between noise points for weak cluster formation
2. Replace hardcoded values in `_rescue_noise()` with `self.params.rescue_max_distance` and `self.params.weak_cluster_max_distance`.
3. Add tests (from Issue 3.4.0) proving rescue behavior changes when these config values change.
4. Keep defaults at 0.3 and 0.2 to preserve existing behavior. M3-RSCH-04 will determine if these need adjustment.

##### Issue 3.4.2 Add context-aware rescue scoring

| Item | Detail |
| ---- | ------ |
| Goal | Make rescue decisions depend on more than raw distance and outlier score. |
| Read | `episodic_hdbscan.py` `_rescue_noise()`; EventAdapter signals; Milestone 3 distance/splitter channel plan. |
| Change | Add narrative, social, spatial, and temporal rescue evidence so a noise point is rescued only when its broader context supports the nearest cluster assignment. |
| Core idea | Distance-only rescue is exactly where cross-context contamination is most likely to slip in. |
| Tests | Add rescue contamination scenarios for same-embedding/different-context and same-thread/weak-distance cases. |
| Success criteria | Rescue behavior improves coherence on ambiguous cases and rejects contextually incompatible near neighbors. |

**Codebase Reality** (verified 2026-03-07):

Current rescue in `_rescue_noise()` (L431-L499) operates entirely on the precomputed distance matrix and outlier scores. It does NOT access any event fields -- no spatial, social, narrative, or affective context is used. The rescue decision is:

1. Filter noise points by `outlier_score < noise_rescue_threshold` (L455-L458)
2. For each eligible noise point, find the nearest cluster centroid
3. If `best_distance < 0.3`, assign to that cluster (L475)
4. Otherwise, try to form a weak cluster with nearby noise points within `0.2` (L484-L499)

Event fields accessed by rescue: only `event_id` (for logging at L479). No typed event access beyond the index into the distance matrix.

The `ClusterableEvent` protocol (L128-L145) adds `sentiment_score` beyond `EventLike`, but this is only used in `_create_cluster()` for dominant sentiment calculation, not in rescue decisions.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 4.6 Remaining Weakness: `rescue_edge_family_overlap` scores 0.83 before correction -- one pair still leaks. This is exactly the scenario where distance-only rescue fails: family events are semantically and spatially close but narratively different.

M5-RSCH-01 (Section 12.3): Hebbian co-occurrence boost improved this specific scenario from 0.83 to 1.00. The Hebbian boost works at the distance matrix level (modifying d before HDBSCAN), which indirectly improves rescue by changing the distances rescue operates on. Context-aware rescue scoring would address the remaining cases more directly.

M3-RSCH-04: "Does context-aware rescue improve episode purity without excessive noise rejection?" This is the research prerequisite.

**Implementation Detail**:

1. After the enriched `EventLike` protocol (Issue 3.1.0) is in place, rescue can access narrative_thread_id, participants, place_id, etc.
2. Add a rescue scoring function that combines distance with context signals:
   - Same narrative_thread as nearest cluster dominant thread -> boost rescue probability
   - Different narrative_thread -> penalize rescue (leave as noise or try next cluster)
   - Same participants/place -> boost rescue probability
   - Missing context -> fall back to distance-only (current behavior)
3. Rescue scoring formula: `rescue_score = w_distance * (1 - normalized_distance) + w_narrative * thread_match + w_social * participant_overlap + w_spatial * place_match`. Rescue if `rescue_score > rescue_threshold`.
4. Weak boundary markers (Issue 3.3.6) can provide additional rescue guidance: noise events near weak boundaries may belong to one side or the other.
5. M3-RSCH-04 must validate that context-aware rescue reduces contamination on the `rescue_edge_family_overlap` scenario without excessive noise rejection.

##### Issue 3.4.3 Test weak-cluster behavior

| Item | Detail |
| ---- | ------ |
| Goal | Add dedicated coverage for weak clusters and rescued fringe events. |
| Read | `episodic_hdbscan.py` weak-cluster creation path; current R2 HDBSCAN tests if present. |
| Change | Add targeted tests for single rescued points, newly formed weak clusters, and the distinction between true noise and rescued members. |
| Core idea | Rescue is currently a high-risk behavior with little direct behavioral pinning. |
| Tests | Add unit and integration cases for rescue rate, rescued count, cluster assignment, and contamination avoidance. |
| Success criteria | Rescue-path behavior is explicit, stable, and no longer inferred indirectly through generic clustering tests. |

**Codebase Reality** (verified 2026-03-07):

Weak cluster creation in `_rescue_noise()` (L484-L499):

- Triggers when a noise point cannot be assigned to any existing cluster (distance > 0.3)
- Finds other noise points within 0.2 with outlier_score < threshold
- Creates a new cluster with `"weak-"` prefix (L513 in `_create_cluster()`)
- Other cluster prefixes: `"noise-"` (L511 -- unreachable after rescue), plain UUID (L515)

No tests verify:

- Weak cluster formation conditions
- Weak cluster vs rescue-to-existing cluster priority
- Weak cluster member count (minimum 2?)
- The distinction between rescued noise and true noise in output
- `rescued_count` accuracy

Research corpus: 1360 events, only 2 noise events (0.15%). Weak cluster behavior is unlikely to be exercised on the research corpus -- it needs synthetic test scenarios.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 3: Only 2 noise events across all phases. This means weak cluster creation was almost never triggered in research experiments. The feature is untested empirically at scale.

Section 7.1: Production baseline has 972 noise events (71.5%). If the production baseline were to use HDBSCAN rescue, weak cluster formation would be heavily exercised. This gap between research (2 noise) and production (972 noise) means rescue behavior must be tested with synthetic scenarios, not just research replay.

**Implementation Detail**:

1. Add to `test_r2_episodic_hdbscan.py` (from Issue 3.4.0):
   - **Weak cluster formation**: 3+ noise points within 0.2 of each other but >0.3 from any cluster -> forms weak cluster
   - **Single noise point**: 1 noise point far from everything -> remains noise (no weak cluster)
   - **Rescue vs weak priority**: noise point within 0.3 of existing cluster AND within 0.2 of other noise -> should rescue to existing cluster (distance path takes priority)
   - **Weak cluster size**: verify minimum member count behavior
   - **Rescued count tracking**: `result.rescued_count` matches actual rescues
   - **Context-aware rescue** (after Issue 3.4.2): same-thread noise rescued, different-thread noise rejected
2. Use synthetic distance matrices with known structure to control rescue behavior deterministically.
3. Test the contamination scenario: noise event semantically close to cluster A but narratively aligned with cluster B -> context-aware rescue should assign to B (after 3.4.2).

### Epic 3.5: Phase Wrapper Decomposition

**Discovery Reference**: Section 11.3 issue R2-ISSUE-008
**Repo Status**: OPEN

#### Epic 3.5 Verified Current State

- `r2_episodic_integrator.py` still holds heavy orchestration plus episode building and quality logic.
- Helper methods exist, but the wrapper is still oversized and mixes concerns.

#### Epic 3.5 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 3.5.1 extract episode builder | OPEN | Move `_build_episode_cluster` and related enrichment logic into a dedicated component. |
| 3.5.2 extract episode matcher | OPEN | Isolate existing episode matching/query logic. |
| 3.5.3 extract quality coordinator | OPEN | Isolate quality/adaptation orchestration from core clustering flow. |
| 3.5.4 reduce wrapper surface | OPEN | Leave `R2EpisodicIntegrator` as a coordinator, not a mega-module. |

#### Epic 3.5 Issue Execution Checklist

##### Issue 3.5.1 Extract the episode builder

| Item | Detail |
| ---- | ------ |
| Goal | Move episode-cluster assembly and enrichment out of the wrapper. |
| Read | `r2_episodic_integrator.py` `_build_episode_cluster()` and surrounding aggregation helpers. |
| Change | Introduce a dedicated builder component for episode output assembly, summary fields, and derived per-cluster metadata. |
| Core idea | Builder logic is a separate concern from orchestration and clustering control flow. |
| Tests | Move current builder behavior under dedicated tests and keep the wrapper covered only at integration level. |
| Success criteria | The wrapper no longer owns detailed episode materialization logic directly. |

**Codebase Reality** (verified 2026-03-07):

`_build_episode_cluster()` at L1238 in `r2_episodic_integrator.py` is the episode materialization method. It's 176 lines (L1238-L1414) and handles:

- EpisodeCluster construction with all metadata fields
- Centroid calculation delegation to CentroidCalculator
- Episode type inference via `_infer_episode_type()` (L925, 93 lines)
- Title generation via `_generate_episode_title()` (L1414, 87 lines)
- Summary generation via `_generate_episode_summary()` (L1501, 21 lines)
- Context field aggregation via `_aggregate_context_fields()` (L1522, 32 lines)

Total builder-related code: ~409 lines across 5 methods. This is a self-contained concern that can be extracted without touching clustering or quality logic.

The builder depends on: events (List[EventAdapter]), centroid_calculator, config (episode_reinforce_threshold, etc.), and ctx (for logging). No dependency on the splitter, clusterer, or quality tracker.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 5.1: Target implementation identifies episode builder as a distinct component. The research pipeline (`r2_final_pipeline.py`) keeps episode construction separate from clustering -- clusters are formed first, then episodes are assembled. This separation is proven to work.

**Implementation Detail**:

1. Create `k0/modules/consolidation/algorithms/episode_builder.py` (or `k0/pipelines/p03/phases/r2_episode_builder.py`).
2. Move `_build_episode_cluster()`, `_infer_episode_type()`, `_generate_episode_title()`, `_generate_episode_summary()`, `_aggregate_context_fields()` into a `EpisodeBuilder` class.
3. The wrapper calls `episode_builder.build(cluster_events, centroid_calculator, config)` instead of inline methods.
4. Preserve existing tests in `test_r2_integration.py` that exercise builder behavior. Add dedicated builder unit tests.
5. No behavioral changes -- pure extraction refactoring.

##### Issue 3.5.2 Extract the episode matcher

| Item | Detail |
| ---- | ------ |
| Goal | Isolate existing-episode query and match logic from the main `run()` flow. |
| Read | `r2_episodic_integrator.py` `_query_existing_episodes()` and `_match_events_to_existing_episodes()`. |
| Change | Move matching/query logic into a dedicated matcher or repository-style component. |
| Core idea | Existing-episode matching is operationally important but conceptually distinct from cluster formation. |
| Tests | Add dedicated tests for match/no-match behavior independent of the main phase orchestration. |
| Success criteria | Existing-episode matching is no longer embedded inline in the wrapper’s core execution path. |

**Codebase Reality** (verified 2026-03-07):

`_query_existing_episodes()` at L1717 (87 lines) and `_match_events_to_existing_episodes()` at L1823 (88 lines) form the episode matching subsystem. Together with `_decode_vector()` (L1806, 17 lines) and `_cosine_similarity()` (L1991, 20 lines), this is ~212 lines of matching logic.

Matching behavior:

- Queries st_epi + st_vec via raw SQL (L1717, 7-day lookback window)
- Compares each event embedding to existing episode embeddings
- Threshold: `episode_reinforce_threshold = 0.85` (L102)
- Sets `reconciliation_action = REINFORCE` on matched events
- Returns `(matched_events, novel_events)` -- only novel events go to clustering

This is a cross-cutting concern (database query + similarity matching + event state mutation) that mixes repository access with domain logic.

**Research Evidence**:

R2_RESEARCH_FINAL.md does not test episode matching -- the research pipeline clusters all events without a matching step. Episode matching is a production-only concern for incremental ingestion. The matching threshold (0.85) was set by the original implementation and has not been empirically validated against the research corpus.

Section 5.2 Step 5-6: Post-clustering thread purity correction and same-thread merge are implemented as separate post-processing steps. Episode matching could follow the same pattern -- a separate component in the phase pipeline.

**Implementation Detail**:

1. Create `k0/pipelines/p03/phases/r2_episode_matcher.py` with an `EpisodeMatcher` class.
2. Move `_query_existing_episodes()`, `_match_events_to_existing_episodes()`, `_decode_vector()`, `_cosine_similarity()` into the matcher.
3. The matcher needs: `ctx.syscalls.execute_query()` for database access, embeddings for similarity, and config for thresholds. Pass these as constructor args or method params.
4. The wrapper calls `matcher.match(events) -> (matched, novel)` and routes novel events to clustering.
5. Flag the raw SQL query (L1717) as a candidate for migration to a repository pattern or syscall in a future cleanup pass.
6. Add dedicated matcher tests: match/no-match behavior, threshold boundary, empty st_epi, multiple matches per event.

##### Issue 3.5.3 Extract the quality coordinator

| Item | Detail |
| ---- | ------ |
| Goal | Isolate quality tracking and adaptive parameter writes from the clustering coordinator. |
| Read | `r2_episodic_integrator.py` `_track_quality_and_adapt()` and related learned-param calls. |
| Change | Move quality-loop orchestration into a dedicated coordinator/service that accepts clustering outputs and returns quality/adaptation results. |
| Core idea | Quality tracking is its own pipeline concern and will keep growing after Milestone 3 and 4. |
| Tests | Add direct tests for the quality coordinator and keep the wrapper focused on invocation/wiring. |
| Success criteria | The wrapper delegates quality orchestration instead of embedding the full loop internally. |

**Codebase Reality** (verified 2026-03-07):

`_track_quality_and_adapt()` at L1597 (120 lines) orchestrates:

- Silhouette computation via `ClusterQualityTracker.compute_from_r2_output()`
- Composite quality score assembly
- `EpsAdjuster.adjust()` triggered by silhouette/singleton_rate
- `MinSamplesAdjuster.adjust()` triggered by singleton_rate
- Learned param persistence via `ctx.syscalls.set_learned_param()` (writes `dbscan_eps`, `dbscan_min_samples`)
- `_compute_ambiguity_score()` (L1911, 80 lines) for missing-field uncertainty

Total quality-related code: ~200 lines. Dependencies: `ClusterQualityTracker`, `EpsAdjuster`, `MinSamplesAdjuster`, clustering output, ctx.syscalls for learned params.

The quality loop will grow in M3+ (episodic coherence from M4-RSCH-04, additional quality channels, grounding/correction channels becoming live). Keeping it inside the wrapper will make the wrapper unmanageable.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 8.1-8.2: Quality tracking uses composite formula `0.40*silhouette + 0.30*grounding + 0.20*(1-correction) + 0.10*(1-singleton)`. POC-08: Adaptive loop is stable (0 oscillation in 10 batches). Section 11.6 (M4-RSCH-04): Episodic coherence (rho=0.4556) is a new quality signal that will need to be integrated. The quality coordinator will need to manage both silhouette-based and coherence-based quality tracking.

**Implementation Detail**:

1. Create `k0/pipelines/p03/phases/r2_quality_coordinator.py` with a `QualityCoordinator` class.
2. Move `_track_quality_and_adapt()` and `_compute_ambiguity_score()` into the coordinator.
3. The coordinator accepts: clustering output (clusters, noise, distance_matrix), adjusters (eps, min_samples), quality tracker, and ctx.syscalls for learned param persistence.
4. The coordinator returns: quality metrics, adjusted params, ambiguity scores.
5. Future M4 addition: episodic coherence tracking plugs into the coordinator without touching the wrapper.
6. Add dedicated quality coordinator tests: quality computation, adjuster triggering, param persistence, ambiguity scoring.

##### Issue 3.5.4 Reduce the wrapper surface

| Item | Detail |
| ---- | ------ |
| Goal | Leave `R2EpisodicIntegrator` as a coordinator rather than a mega-module. |
| Read | The wrapper’s current private helper inventory and the extracted components above. |
| Change | Refactor the wrapper to sequence splitter, clusterer, matcher, builder, and quality coordinator components with minimal inline logic. |
| Core idea | Milestone 4 and 5 work will be unmanageable if the wrapper remains the place where every R2 concern accumulates. |
| Tests | Preserve an end-to-end integration test for the wrapper while shifting detailed behavior tests to extracted units. |
| Success criteria | The wrapper’s responsibility is orchestration only, with a materially smaller helper surface and cleaner dependency graph. |

**Codebase Reality** (verified 2026-03-07):

`R2EpisodicIntegrator` in r2_episodic_integrator.py is 2134 lines with 20+ private methods. After extracting builder (~409 lines), matcher (~212 lines), and quality coordinator (~200 lines), the wrapper retains:

| Remaining Method | Lines | Purpose |
| ---------------- | ----- | ------- |
| `run()` | ~200 | Main orchestration flow |
| `should_skip()` | ~30 | Skip gate |
| `_initialize_components()` | ~50 | Component setup |
| `_get_dbscan_params()` | ~40 | Param loading |
| `_split_events()` | ~16 | Delegate to splitter |
| `_canonicalize_episodes()` | ~163 | Merge episodes by signature |
| `_merge_episodes()` | ~125 | Merge group into canonical |
| `_recompute_confidence()` | ~42 | Confidence recalc |
| `_compute_confidence()` | ~53 | Confidence formula |
| `_update_event_states()` | ~43 | Write cluster assignments |

Estimated post-extraction wrapper: ~762 lines (down from 2134). The remaining methods are pure orchestration and event-state management.

`_canonicalize_episodes()` (L859, 163 lines) and `_merge_episodes()` (L1018, 125 lines) are candidates for further extraction but can stay in the wrapper for M3.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 5.1: Production implementation plan identifies 3 components: (1) CompositeDistance replacement, (2) ThreadEmbeddingCache, (3) Post-clustering correction. M3-RSCH-07: "Does wrapper decomposition before algorithmic changes reduce implementation risk?" The answer is architectural: smaller components are easier to modify, test, and review.

**Implementation Detail**:

1. After Issues 3.5.1-3.5.3, the wrapper’s `run()` becomes a sequential coordinator: adapt -> skip-check -> match -> split -> cluster -> build -> quality -> update states -> return.
2. Target: wrapper under 800 lines, `run()` under 100 lines.
3. Each extracted component has its own test file. Wrapper tests become pure integration tests.
4. M4 and M5 additions (thread purity correction, same-thread merge, Hebbian boost, coherence tracking) each plug into the coordinator flow without expanding the wrapper.
5. The `_canonicalize_episodes()` block is the largest remaining inline concern. Consider extracting to `EpisodeCanonicalizer` if the wrapper still exceeds 800 lines.

### Epic 3.6: Temporal Context Binding

**Discovery Reference**: Sections 16, 17, and temp design temporal channel
**Repo Status**: OPEN

#### Epic 3.6 Verified Current State

- Core timestamp mitigation exists, but temporal context is not yet a first-class clustering input.
- The temp design expects temporal-link binding, temporal-anchor context, and same-turn binding modifiers.
- The current plan did not explicitly schedule the support signals required for that target.

#### Epic 3.6 EventAdapter Surface Gap

The plan previously stated "EventAdapter now sees the temporal support signals." This is only partially true.
EventAdapter currently exposes 3 of 8 temporal support fields: `temporal_orientation`, `temporal_resolved_epoch_ms`,
and `temporal_anchor_json`. The remaining 5 fields (`temporal_links_json`, `time_of_day_bucket`, `circadian_slot`,
`is_weekend`, `extraction_sequence`) exist on `P03EventState` but are NOT wrapped by EventAdapter.
Issue 3.6.0 must be completed before Issues 3.6.1-3.6.5 can proceed.

#### Epic 3.6 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 3.6.0 extend EventAdapter for remaining temporal support fields | DONE | Added `temporal_links_json`, `time_of_day_bucket`, `circadian_slot`, `is_weekend`, and `extraction_sequence` as properties on `EventAdapter`. Extended `EventLike` (5 fields) and `SplittableEvent` (4 fields) protocols. 14 tests added, 58 total adapter tests passing. |
| 3.6.1 bind `temporal_links_json` into distance | DEFER | M3-RSCH-06: temporal support signals have 0/1360 coverage in research corpus. 3D ensemble (sem=0.45, temp=0.25, narr=0.30) is optimal. Signal surfaced on EventAdapter (3.6.0) but cannot be tested or validated until K1 populates temporal links. Revisit when coverage >= 30%. |
| 3.6.2 incorporate `temporal_anchor_json` | DEFER | M3-RSCH-06: research corpus lacks temporal anchor metadata. temporal_anchor_json already on EventAdapter (L300) but orphaned -- no algorithm reads it. Log-compressed temporal distance (Epic 3.2) handles most cases. Revisit when K1 populates anchor metadata with coverage >= 30%. |
| 3.6.3 incorporate `time_of_day_bucket` and `circadian_slot` | DEFER | M3-RSCH-06: 0/1360 coverage in corpus. Circadian signals are derivable from timestamps (theoretically 100%) but not populated by current MW. Signal surfaced on EventAdapter (3.6.0). Revisit when K1/MW populates these fields. |
| 3.6.4 incorporate `is_weekend` | DEFER | M3-RSCH-06: 0/1360 coverage. is_weekend derivable from timestamp but not populated. Surfaced on EventAdapter (3.6.0). Low expected value in family domain where weekend/workday distinction is less salient. Revisit when populated. |
| 3.6.5 incorporate `extraction_sequence` | DEFER | Same-turn events already bind via dt=0 in temporal distance. extraction_sequence adds ordering context but dt=0 already prevents false separation. Surfaced on EventAdapter (3.6.0). Low priority -- implement only if same-turn events are being split by other channels. |

#### Epic 3.6 Issue Execution Checklist

##### Issue 3.6.0 Extend EventAdapter for remaining temporal support fields

| Item | Detail |
| ---- | ------ |
| Goal | Surface the 5 missing temporal support fields through EventAdapter so downstream consumers have typed access. |
| Read | `k0/pipelines/p03/phases/r2_episodic_integrator.py` `EventAdapter` class; `k0/pipelines/p03/event_state.py` `P03EventState` fields `temporal_links_json` (L223), `time_of_day_bucket` (L176), `circadian_slot` (L177), `is_weekend` (L178), `extraction_sequence` (L224). |
| Change | Add 5 new properties to `EventAdapter`: `temporal_links_json`, `time_of_day_bucket`, `circadian_slot`, `is_weekend`, `extraction_sequence`, each wrapping the corresponding `P03EventState` field with `None` default for missing data. Also add these fields to the enriched `EventLike` and `SplittableEvent` protocols from Issues 3.1.0 and 3.3.0. |
| Core idea | Issues 3.6.1-3.6.5 all assume these fields are accessible through EventAdapter, but they are not yet. Without this issue, temporal context binding would require bypassing EventAdapter and accessing P03EventState directly, breaking the adapter pattern. |
| Tests | Add property-access tests for each new field, including `None` fallback when `P03EventState` does not populate them. Add protocol compliance tests confirming the enriched protocols accept the new fields. |
| Success criteria | All 8 temporal support fields are accessible through EventAdapter. No M3 consumer needs to reach through to P03EventState for temporal support data. |

**Codebase Reality** (verified 2026-03-07):

EventAdapter (r2_episodic_integrator.py L109-L309) exposes 22 properties wrapping P03EventState fields. The temporal surface currently has 3 properties:

- `temporal_orientation` (L287) -> P03EventState.temporal_orientation (L221)
- `temporal_resolved_epoch_ms` (L292) -> P03EventState.temporal_resolved_epoch_ms (L218)
- `temporal_anchor_json` (L300) -> P03EventState.temporal_anchor_json (L232)

The 5 MISSING temporal fields all exist on P03EventState:

- `temporal_links_json` (L223): str = ""
- `time_of_day_bucket` (L176): str = ""
- `circadian_slot` (L177): str = ""
- `is_weekend` (L178): Optional[bool] = None
- `extraction_sequence` (L224): int = 0

Each existing EventAdapter temporal property follows the pattern: `@property` returning `self.event.<field>` with a None/empty-string fallback. Adding 5 more follows the same pattern.

The `EventLike` protocol (composite_distance.py L120-L137) has only 3 fields (event_id, timestamp, embedding_768). The `SplittableEvent` protocol (episode_splitter.py L112-L126) has only 2 fields (event_id, timestamp). Both need extension to include the new temporal fields.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.2: The research pipeline uses only `timestamp` for temporal distance. No temporal support fields (time_of_day_bucket, circadian_slot, is_weekend, extraction_sequence, temporal_links_json) were tested in the 68-experiment corpus because they were not available on the research event schema. M5-RSCH-07: temporal_source has 0/1360 coverage -- BLOCKED. The same sparsity risk applies to all temporal support fields.

**Implementation Detail**:

1. Add 5 `@property` methods to EventAdapter following the existing temporal pattern (L287-L309).
2. Each property wraps the corresponding P03EventState field with None/empty fallback.
3. Extend `EventLike` protocol with optional temporal support fields (all Optional with None default to preserve backward compatibility).
4. Extend `SplittableEvent` protocol similarly.
5. Add property-access tests for each new field, including None fallback when P03EventState does not populate them.
6. Add protocol compliance tests confirming EventAdapter satisfies both enriched protocols.
7. This is pure surface expansion -- no behavioral change to distance or splitting.

##### Issue 3.6.1 Bind `temporal_links_json` into distance

| Item | Detail |
| ---- | ------ |
| Goal | Use explicit temporal-link structure to reduce false separation. |
| Read | EventAdapter temporal support fields (after Issue 3.6.0); temporal-distance implementation after Epic 3.2; temp design temporal-link notes. |
| Change | Add a temporal-link overlap/binding term that can reduce distance when events are explicitly linked by shared temporal anchors or references. |
| Core idea | Some events belong together because they reference the same temporal frame, not because their timestamps are numerically adjacent. |
| Tests | Add cases for shared anchor/shared link vs nearby-but-unlinked events. |
| Success criteria | Temporal links can bind related events even when naive timestamp distance would over-separate them. |

**Codebase Reality** (verified 2026-03-07):

`temporal_links_json` (P03EventState L223): JSON string containing explicit temporal references between events (e.g., "yesterday's meeting" links to a previous event). Currently str = "" default. Not on EventAdapter (requires Issue 3.6.0).

The temporal distance function `_normalized_time_distance()` (composite_distance.py L349-L361) uses only `abs(t1 - t2)` -- pure wall-clock difference. After Epic 3.2 (logarithmic), it will use log-compressed time. Neither version considers explicit temporal-link metadata.

The `compute()` method (L183-L224) aggregates weighted dimension distances. A temporal-link binding term would need to reduce the temporal distance component when events share explicit temporal references.

**Research Evidence**:

R2_RESEARCH_FINAL.md does not include temporal-link binding experiments. The corpus events lack temporal_links_json population. M5-RSCH-07 is BLOCKED (temporal_source 0/1360 coverage) -- similar sparsity risk applies here. This is a design-first issue: define the binding semantics, then validate when K1 populates temporal links.

**Implementation Detail**:

1. Parse `temporal_links_json` into a set of referenced event IDs or temporal anchors.
2. Define a link-overlap function: events sharing >= 1 temporal link get a distance reduction factor.
3. Apply the reduction to the temporal distance component in `compute()`, not as a separate dimension.
4. Fallback: if both events have empty temporal_links_json, the term contributes 0 (neutral).
5. Requires M3-RSCH-06 ablation to validate marginal improvement once data is available.
6. Test with synthetic temporal-link scenarios (shared/disjoint/empty links).

##### Issue 3.6.2 Incorporate `temporal_anchor_json`

| Item | Detail |
| ---- | ------ |
| Goal | Use temporal-anchor context to reduce ambiguity in recurring or loosely timestamped events. |
| Read | EventAdapter `temporal_anchor_json`; temp design temporal anchor expectations. |
| Change | Define how anchor identity and anchor kind contribute to distance or boundary behavior. |
| Core idea | Anchor metadata can disambiguate recurring routines and loosely expressed times better than timestamps alone. |
| Tests | Add recurring-anchor and ambiguous-time scenarios. |
| Success criteria | Temporal anchors affect episode binding in a predictable and documented way. |

**Codebase Reality** (verified 2026-03-07):

`temporal_anchor_json` is already on EventAdapter (L300): returns `self.event.temporal_anchor_json` with `{}` -> None fallback. P03EventState field at L232 (str = "").

The anchor JSON contains MW v2 temporal context: anchor kind (absolute/relative/recurring), resolved time, and confidence. Currently NOT consumed by any distance or boundary algorithm. The property exists but is orphaned -- no algorithm reads it.

Potential roles: (a) reduce ambiguity score when anchor kind is 'absolute' (high confidence), (b) bind recurring events that share the same anchor pattern (e.g., "every Monday" anchors), (c) modify temporal distance when anchor resolution differs from wall-clock timestamp.

**Research Evidence**:

R2_RESEARCH_FINAL.md does not test temporal anchors. The research corpus events use raw timestamps only. Section 2.2 log-compressed temporal distance already handles most cases where wall-clock distance is misleading. Anchor-based binding would be additive for recurring/routine events that log-compression alone cannot capture.

**Implementation Detail**:

1. Parse `temporal_anchor_json` into a typed struct (anchor_kind, resolved_time, confidence).
2. Define anchor-similarity function: same anchor_kind + overlapping resolved_time = binding signal.
3. Integrate as a modifier on temporal distance (reduce distance for anchor-matched events) or as a boundary-strength modifier in the splitter.
4. Fallback: empty/null anchor contributes 0 (neutral).
5. M3-RSCH-06 ablation validates benefit once K1 populates anchor metadata.
6. Test with synthetic anchor scenarios (recurring, absolute, missing).

##### Issue 3.6.3 Incorporate `time_of_day_bucket` and `circadian_slot`

| Item | Detail |
| ---- | ------ |
| Goal | Decide whether circadian context is a temporal prior, a boundary hint, or both. |
| Read | Temp design support signals; future distance/splitter interfaces. |
| Change | Add circadian similarity either to temporal distance or to boundary strength with explicit rationale. |
| Core idea | Routine memory often binds by daily slot rather than exact wall-clock adjacency. |
| Tests | Add morning/evening routine and same-slot/different-day scenarios. |
| Success criteria | Circadian signals have an explicit home in the model instead of remaining orphaned support fields. |

**Codebase Reality** (verified 2026-03-07):

`time_of_day_bucket` (P03EventState L176, str = "") and `circadian_slot` (P03EventState L177, str = ""). Neither field is on EventAdapter (requires Issue 3.6.0).

These are categorical fields from MW v2: time_of_day_bucket is coarse (MORNING/AFTERNOON/EVENING/NIGHT), circadian_slot is finer-grained. Neither is consumed by any algorithm today.

The temporal distance function operates on continuous timestamps. Circadian signals are categorical -- they cannot be directly added to the continuous temporal distance. Options:

- Soft prior: same circadian slot reduces temporal distance by a small factor
- Boundary hint: circadian slot change increases boundary strength in splitter
- Both: slot similarity reduces distance AND slot change strengthens boundaries

**Research Evidence**:

R2_RESEARCH_FINAL.md does not test circadian signals. The research corpus uses timestamps but not derived circadian buckets. Section 5.3 ("What NOT to build yet"): spatial/social/affective dimensions flagged as too sparse for M3 -- similar risk applies to circadian signals if coverage is low. However, circadian signals are derivable from timestamps, so coverage is theoretically 100% for events with valid timestamps.

**Implementation Detail**:

1. After Issue 3.6.0 surfaces these fields on EventAdapter, define a circadian similarity function.
2. Categorical match: same bucket/slot = 0.0 (identical), adjacent = 0.5, opposite = 1.0.
3. Integrate as a modifier on temporal distance or as a standalone soft dimension.
4. Boundary strength: circadian slot change between adjacent events increases boundary score.
5. Fallback: empty/missing circadian fields contribute neutral (0.5).
6. M3-RSCH-06 ablation validates whether circadian similarity adds marginal value over log-temporal distance.

##### Issue 3.6.4 Incorporate `is_weekend`

| Item | Detail |
| ---- | ------ |
| Goal | Decide whether weekend/workday mode changes should influence temporal and activity interpretation. |
| Read | Temporal support-signal design notes and splitter policy. |
| Change | Add weekend/workday mode as a soft prior or boundary modifier where it improves separation of routine contexts. |
| Core idea | A Saturday morning routine and a weekday morning routine can be semantically similar but episodically distinct. |
| Tests | Add workday/weekend mode-shift scenarios. |
| Success criteria | Weekend mode contributes intentionally or is explicitly excluded with evidence-backed rationale. |

**Codebase Reality** (verified 2026-03-07):

`is_weekend` (P03EventState L178, Optional[bool] = None). Not on EventAdapter (requires Issue 3.6.0).

Binary categorical field derivable from timestamp. Not consumed by any algorithm. The splitter has no concept of weekday/weekend mode shifts -- all events are treated identically regardless of day type.

Potential roles: (a) boundary modifier -- weekend-to-weekday transition adds boundary strength, (b) temporal distance modifier -- same-day-type events get slight distance reduction, (c) episode type hint -- contributes to `_infer_episode_type()` context.

**Research Evidence**:

R2_RESEARCH_FINAL.md does not test weekend/workday signals. The 8-scenario research corpus spans a family context where weekend/workday distinction may be less salient than in work-focused corpora. M3-RSCH-06 ablation should test whether is_weekend has any marginal value in the family domain. Section 5.3 warns against premature addition of sparse signals.

**Implementation Detail**:

1. After Issue 3.6.0 surfaces `is_weekend` on EventAdapter, evaluate coverage (should be ~100% for valid timestamps).
2. If coverage >= 90%: add as boundary modifier (weekend/weekday transition += boundary_strength_delta).
3. If coverage < 90%: defer with documented rationale.
4. M3-RSCH-06 ablation is the decision gate. No implementation without evidence.
5. Fallback: None -> neutral (no effect on distance or boundary).

##### Issue 3.6.5 Incorporate `extraction_sequence`

| Item | Detail |
| ---- | ------ |
| Goal | Use same-turn extraction order when it improves coherence. |
| Read | Temp design same-turn binding notes and event adapter support fields if/when added. |
| Change | Add same-turn extraction ordering as a local binding or boundary modifier for temporally co-emitted events. |
| Core idea | Events extracted from the same conversational turn may need a local adjacency hint even when timestamps are identical or coarse. |
| Tests | Add same-turn multi-event scenarios with and without sequence metadata. |
| Success criteria | Extraction-order metadata is either integrated deliberately or explicitly ruled out with rationale. |

**Codebase Reality** (verified 2026-03-07):

`extraction_sequence` (P03EventState L224, int = 0). Not on EventAdapter (requires Issue 3.6.0).

This field represents the position of an event within a single conversational turn when MW v2 extracts multiple events from one message. Events from the same turn share the same timestamp but have different extraction_sequence values.

The splitter `_detect_break()` (episode_splitter.py L316-L384) uses timestamp difference as the primary temporal signal. When multiple events share an identical timestamp (same-turn extraction), the splitter sees dt=0 and never fires a TIME_GAP break. This is correct behavior -- same-turn events should stay together. But extraction_sequence could strengthen this binding (ensure same-turn events are never split by other channels).

The distance function `_normalized_time_distance()` (composite_distance.py L349-L361) returns 0.0 for dt=0, so same-turn events already have minimal temporal distance. Extraction_sequence would add ordering context, not distance reduction.

**Research Evidence**:

R2_RESEARCH_FINAL.md does not test extraction_sequence. The corpus events have unique timestamps, so same-turn co-emission is not represented. This signal matters only when MW v2 extracts multiple events from a single message, which is a production concern not captured in the research pipeline.

**Implementation Detail**:

1. After Issue 3.6.0, surface extraction_sequence on EventAdapter.
2. Define same-turn binding: events with identical timestamp AND sequential extraction_sequence values get a local adjacency bonus (reduced distance or boundary suppression).
3. This is a low-priority signal -- same-turn events already bind via dt=0. Only implement if same-turn events are being split by other channels (spatial, social, narrative).
4. Fallback: extraction_sequence=0 (default) -> no effect.
5. Test with synthetic same-turn multi-event scenarios.

### Epic 3.7: Signal Surface Completion For Distance And Splitting

**Discovery Reference**: temp design channel inventory
**Repo Status**: OPEN

#### Epic 3.7 Verified Current State

- The current plan covered primary signal families but omitted several support signals needed for full channel completion.
- These support signals should be explicitly planned before implementation detail work begins.
- Issues 3.7.1-3.7.5 are primarily design decisions, not implementation tasks. Each must be resolved with explicit decision criteria and evidence before implementation proceeds.

#### Epic 3.7 Decision Gate

Each Issue in 3.7 must produce a short decision note (approve/exclude/defer) before implementation.
The preferred resolution path is:

1. **M2 research ablation** already identifies which signals help clustering quality (M2-RSCH-01).
2. **M3 research signal-family ablation** (M3-RSCH-06) extends the analysis to M3 formulas.
3. If a signal earns its place in ablation results, it gets a home (distance, splitter, rescue, or summary).
4. If a signal does not earn its place, it is explicitly excluded with documented rationale.
5. Unresolved 3.7 decisions block M3 exit, not M3 entry -- but they should be resolved during the M3 research phase, not deferred to implementation time.

#### Epic 3.7 Issues

| Issue | Status | Planned Action | Decision Criteria |
| ----- | ------ | -------------- | ----------------- |
| 3.7.1 incorporate `spatial_context_json` | EXCLUDE | EXCLUDE from distance and splitter. Keep for future labeling/metadata only. | M3-RSCH-06 ablation (68 experiments): spatial weight=0.0 in optimal config. 0/1360 corpus coverage. Adding spatial degraded quality. |
| 3.7.2 incorporate `location_name` and `location_type` | EXCLUDE (distance) / KEEP (labeling) | EXCLUDE from distance and splitter. KEEP for episode labeling (already used at L1287, L1295). | M3-RSCH-06: spatial weight=0.0. No EventAdapter surface needed -- direct P03EventState access in builder is sufficient. |
| 3.7.3 incorporate `num_participants` and `is_solo_event` | EXCLUDE | EXCLUDE from distance and splitter. Too coarse vs Hebbian participant co-occurrence. | M3-RSCH-06: social weight=0.0. M5-RSCH-01 Hebbian (participant-level) achieves 8/8 without count signals. |
| 3.7.4 incorporate `intent_ultrabert` | EXCLUDE (clustering) / KEEP (metadata) | EXCLUDE from all clustering math. KEEP as episode-level summary metadata. | M4-RSCH-07: All 9 signals SUMMARY-ONLY (delta < 0.01 MRR). No improvement in any role tested. |
| 3.7.5 decide on `content_text` role | EXCLUDE (clustering) / ALLOW (summary/labeling) | EXCLUDE from pairwise distance, splitting, HDBSCAN input. ALLOW in title/summary generation (already the case). | embedding_768 captures semantic content. Raw text in distance = double-count + privacy concern. |

#### Epic 3.7 Issue Execution Checklist

##### Issue 3.7.1 Incorporate `spatial_context_json`

| Item | Detail |
| ---- | ------ |
| Goal | Use explicit movement/transition context where geohash or place identity alone is insufficient. |
| Read | Temp design spatial support channel notes; distance and splitter extension points. |
| Change | Decide whether `spatial_context_json` affects spatial distance, boundary strength, or rescue scoring, and implement it in one primary place. |
| Core idea | Spatial transitions are part of episode structure, not just point-in-space metadata. |
| Tests | Add transition-aware scenarios such as travel/arrival/departure chains. |
| Success criteria | Spatial context is either mapped into the model intentionally or excluded with explicit rationale. |

**Codebase Reality** (verified 2026-03-07):

`spatial_context_json` (P03EventState L168, str = ""). NOT on EventAdapter. Contains structured transition/movement context from MW v2 (e.g., arriving, departing, traveling).

Current spatial signals consumed by algorithms:

- `geohash_6` via EventAdapter.geohash_6 (L177) -> used by EpisodeSplitter._detect_break Signal 1 (L340)
- `place_id` via P03EventState.place_id (L166) -> used by R0 batch selector, NOT by distance or splitter
- `spatial_context_json` is not consumed by any algorithm

Spatial context could add transition-awareness to the splitter (arrival/departure as boundary signals) or to distance (events sharing a transition context bind more strongly).

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 5.3 ("What NOT to build yet"): 6D spatial/social/affective flagged as too sparse. The research corpus has geohash_6 but not spatial_context_json. M3-RSCH-06 ablation is the decision gate. Section 2.2: spatial is not part of the 3D ensemble (sem=0.45, temp=0.25, narr=0.30).

**Implementation Detail**:

Decision issue. Resolution path:

1. Check spatial_context_json population rate in production st_hipp_events.
2. If coverage >= 30%: run M3-RSCH-06 ablation to test marginal improvement.
3. If ablation positive: add as splitter boundary modifier (transition = stronger boundary).
4. If ablation negative or coverage < 30%: explicitly exclude with documented rationale.
5. Output: short decision note (approve/exclude/defer).

##### Issue 3.7.2 Incorporate `location_name` and `location_type`

| Item | Detail |
| ---- | ------ |
| Goal | Preserve human-meaningful spatial fallback comparators when `place_id` is missing. |
| Read | Spatial distance design and event adapter fields. |
| Change | Add fallback comparators based on normalized location name and location type, and use them for labeling or rescue hints when appropriate. |
| Core idea | Many real events will have partial spatial metadata, and the model should still extract some spatial continuity signal. |
| Tests | Add same-type/different-name and same-name/missing-place-id cases. |
| Success criteria | Missing `place_id` does not collapse spatial reasoning to geohash only. |

**Codebase Reality** (verified 2026-03-07):

`location_name` (P03EventState L163, str = "") and `location_type` (P03EventState L164, str = ""). Neither is on EventAdapter. However, both are accessed directly via `e.event.location_name` (L1287) and `e.event.location_type` (L1295) inside `_build_episode_cluster()` for episode labeling and type aggregation.

Current spatial fallback chain in algorithms:

- Splitter: `geohash_6` only (via `_geohash_distance()` L386-L424)
- Distance: no spatial dimension exists yet (2D: semantic + temporal)
- Rescue: no spatial signal
- Episode builder: uses location_name and location_type for labels (not for clustering math)

Epic 3.1.2 (spatial distance dimension) will need a fallback chain: place_id -> geohash_6 -> location_name/type. These fields are the secondary/tertiary fallback when place_id is absent.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 5.3: spatial dimension flagged as too sparse. The research corpus uses geohash_6 for spatial comparisons. location_name and location_type coverage is unknown in the research corpus. M4-RSCH-07 showed all 9 signals (including spatial) are SUMMARY-ONLY -- they contribute to episode metadata but not clustering math.

**Implementation Detail**:

Decision issue. Resolution path:

1. Surface location_name and location_type on EventAdapter (can be done in Issue 3.6.0 or as a parallel adapter issue).
2. Define string-similarity fallback for location_name (normalized string match) and category-match for location_type.
3. Integrate into Epic 3.1.2 spatial distance as fallback when place_id is absent and geohash_6 is unavailable.
4. Keep using these fields in episode builder for labeling regardless of distance decision.
5. M3-RSCH-06 ablation validates marginal value of name/type fallback over geohash-only.

##### Issue 3.7.3 Incorporate `num_participants` and `is_solo_event`

| Item | Detail |
| ---- | ------ |
| Goal | Add lightweight social structure even when full participant identity data is sparse. |
| Read | Social-distance and boundary-scoring design for Milestone 3. |
| Change | Use participant count and solo/group state as fallback social modifiers in distance, splitting, or rescue. |
| Core idea | A shift from solo to group context is often episodically significant even without a full participant list. |
| Tests | Add solo-to-group and equal-count/different-identity fallback scenarios. |
| Success criteria | Social fallback signals contribute meaningfully when richer participant data is missing. |

**Codebase Reality** (verified 2026-03-07):

`num_participants` (P03EventState L159, int = 0) and `is_solo_event` (P03EventState L162, Optional[bool] = None). Neither is on EventAdapter. EventAdapter exposes `participants_json` (L235) and `social_context` (L224) but not these summary fields.

Current social signals consumed by algorithms:

- None consumed by distance or splitter
- `participants_json` exposed on EventAdapter but not used by any algorithm
- `social_context` exposed on EventAdapter but not used by any algorithm
- Episode builder accesses `e.event.participants_json` directly (L1306+) for episode metadata

Epic 3.1.3 (social distance dimension) will use Jaccard similarity on participant sets. When participant sets are empty/unknown, num_participants and is_solo_event are the fallback: solo->group shift = maximum social distance; same-count = neutral.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 5.3: social dimension flagged as too sparse. M5 Hebbian co-occurrence boost (Section 12.3) uses participant co-occurrence (person_dad, person_maya, etc.) and achieves 5/8->8/8 with scale=0.10, cap=0.05. This works at the identity level, not the count level. num_participants/is_solo_event are a coarser signal for when identity is unavailable.

**Implementation Detail**:

Decision issue. Resolution path:

1. Surface num_participants and is_solo_event on EventAdapter.
2. Define social fallback function: solo->group transition = high social distance, group->group with same count = low.
3. Integrate into Epic 3.1.3 social distance as fallback when participants_json is empty.
4. Also useful as boundary-strength modifier: solo-to-group shift strengthens episode boundary.
5. M3-RSCH-06 ablation validates marginal value over Jaccard-only social distance.

##### Issue 3.7.4 Incorporate `intent_ultrabert`

| Item | Detail |
| ---- | ------ |
| Goal | Place intent classification in the correct layer of the model. |
| Read | Temp design semantic/narrative support notes; EventAdapter and future distance model. |
| Change | Decide whether `intent_ultrabert` belongs primarily in semantic distance, narrative distance, boundary scoring, or some combination, then encode that choice explicitly. |
| Core idea | Intent is semantically rich but can also act as a narrative-mode shift; it should not be sprinkled into multiple places without a clear role. |
| Tests | Add cases where intent agrees with topic, conflicts with topic, or shifts despite stable participants/location. |
| Success criteria | Intent has a documented primary role in R2 and is not left as an unplanned support field. |

**Codebase Reality** (verified 2026-03-07):

`intent_ultrabert` (P03EventState L194, str = "") and `intent_type` (P03EventState L208, str = ""). Neither is on EventAdapter. `intent_type` is listed among the 7 zombie/deprecated columns in st_hipp_events; `intent_ultrabert` is the UltraBERT replacement from P02.

EventAdapter has `activity_type_ultrabert` (L215) -- the INGRESS 12-type classification. `intent_ultrabert` is a separate classification (intent vs activity). The two are conceptually distinct: activity_type = what is happening, intent = why the user is communicating.

Candidate roles:

- Semantic distance: intent match/mismatch as a distance modifier
- Narrative distance: intent shift (DIARY->TASK->PLANNING) as narrative transition signal
- Boundary detection: intent change as a boundary-strength modifier

**Research Evidence**:

R2_RESEARCH_FINAL.md M4-RSCH-07: All 9 signals tested (including intent) are SUMMARY-ONLY -- they contribute to episode metadata but showed no marginal improvement in clustering quality. Section 5.3: 6D model with spatial/social/affective too sparse. Intent was not part of the 3D ensemble. The research evidence does not support adding intent to distance math.

**Implementation Detail**:

Decision issue. Resolution path:

1. M3-RSCH-06 ablation: test intent_ultrabert in each role (semantic modifier, narrative modifier, boundary modifier) separately.
2. If ablation shows marginal improvement in one role: assign it there with documented rationale.
3. If no role shows improvement: explicitly exclude from clustering math, keep as episode-level summary metadata.
4. M4-RSCH-07 result (SUMMARY-ONLY) suggests exclusion is likely but M3-RSCH-06 ablation with the 6D model may differ.
5. Surface on EventAdapter regardless of distance role -- needed for episode labeling.

##### Issue 3.7.5 Decide on the `content_text` role

| Item | Detail |
| ---- | ------ |
| Goal | Explicitly decide whether raw text participates in clustering math or stays outside it. |
| Read | Temp design notes on support signals and rescue/summary heuristics; existing embedding-first design assumptions. |
| Change | Either define a narrow role for raw text in rescue/summary/boundary heuristics or explicitly exclude it from pairwise clustering math. |
| Core idea | Raw text is powerful but risky; the plan must say where it is allowed rather than letting it leak into the model opportunistically. |
| Tests | Add tests only for the chosen role, not for both possibilities. |
| Success criteria | `content_text` has a documented and intentionally bounded role in Milestone 3. |

**Codebase Reality** (verified 2026-03-07):

`content_text` (P03EventState L129, str = ""). Not on EventAdapter. Contains raw user text from P02 ingestion. This is the original message content before embedding.

Current usage in R2:

- `_generate_episode_summary()` accesses `e.event.content_text` for episode summary generation
- `_generate_episode_title()` uses content_text for title heuristics
- NOT used in distance computation, splitting, or rescue
- embedding_768 is the semantic representation of content_text

Design constraint: embedding_768 already captures semantic content. Using raw content_text in pairwise distance would double-count semantics and introduce privacy/security concerns (raw text in clustering math vs. embeddings). The embedding-first design deliberately avoids raw text in distance computation.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 2.2.3: ThreadEmbeddingCache uses embeddings for semantic distance, not raw text. Section 7: The 3D ensemble (sem=0.45, temp=0.25, narr=0.30) uses cosine distance on embedding_768 for the semantic component. Raw text is never part of the research pipeline. Section 5.3 ("What NOT to build yet") implicitly excludes raw text from clustering.

**Implementation Detail**:

Decision issue. Expected resolution: EXCLUDE from clustering math, ALLOW in rescue/summary heuristics.

1. Explicitly document: content_text is NOT used in pairwise distance, splitting thresholds, or HDBSCAN input.
2. ALLOWED uses: episode title generation, episode summary generation, rescue heuristics (keyword overlap as a rescue tiebreaker).
3. If rescue keyword overlap is implemented, it must use normalized/lowered text -- never raw content in distance matrices.
4. Privacy review: any rescue heuristic using content_text must not log or persist raw text beyond the episode summary.
5. Output: short decision note documenting the boundary.

#### Milestone 3 Exit Criteria

- R2 clustering operates on the intended multi-dimensional signal set.
- Splitter and rescue behavior use the same signal philosophy as the corrected discovery doc.
- Temporal support signals and omitted support fields are explicitly mapped into R2 logic or deliberately excluded with rationale.
- Wrapper complexity is reduced enough that Milestone 4 can build on stable components.
- `EventLike` and `SplittableEvent` protocols are extended, coordinated, and satisfied by EventAdapter.
- All distance dimensions, splitter channels, and rescue evaluators implement the fallback chain (primary -> secondary -> neutral) and handle missing signals safely.
- Dedicated HDBSCAN test coverage exists before and after rescue restructuring.
- M3 research exit gate is passed: weight calibration, curve comparison, boundary/rescue benchmarks, and signal ablation artifacts exist.
- Epic 3.7 decisions are all resolved (approve/exclude/defer) with documented rationale.

#### Milestone 3 Completion Verification

| Area | Verification Requirement |
| ---- | ------------------------ |
| Research | M3 research artifacts exist for 6D weights, log-temporal curve, boundary scoring, rescue scoring, and signal ablation |
| Protocols | `EventLike` and `SplittableEvent` are enriched, coordinated, and tested |
| Fallback safety | Every dimension, channel, and rescue evaluator handles missing signals without crash, false-bind, or false-separate |
| Test coverage | Dedicated HDBSCAN tests exist; splitter, distance, and rescue tests cover sparse-signal scenarios |
| Decisions | Epic 3.7 signals all have documented approve/exclude/defer decisions |
| Code | Wrapper decomposition is complete; Milestone 4 does not inherit a 1,800+ line monolith |

---

## MILESTONE 4: Centroid & Quality Enhancements (P3)

**Milestone Status**: OPEN

### Milestone 4 Operating Assumption

The planning below assumes Milestone 3 is complete and already merged into the live substrate.
That means Milestone 4 starts from a 6D distance model, calibrated splitter/rescue behavior,
and decomposed R2 components rather than from the current legacy centroid and quality surface
still visible in repo today.

### Milestone 4 Operating Goal

Milestone 4 is the episode-representation and quality-honesty milestone. The goal is not only to
change centroid formulas. It is to prove that richer encoding and coherence metrics improve the
retrieval and audit value of formed episodes without breaking the single-embedding storage path,
downstream truth writing, or later adaptive work.

### Milestone 4 Structural Prerequisites

Milestone 4 has protocol and integration gaps that mirror Milestone 3's pre-fix state.
These must be resolved as shared prerequisites before any epic proceeds.

| Protocol / Contract | Current Surface | Required For | Gap |
| ------------------- | --------------- | ------------ | --- |
| `CentroidableEvent` in `centroid_calculator.py` | `event_id`, `timestamp`, `embedding_768`, `importance_score` | Epics 4.1, 4.3, 4.6 | Needs `salience_score`, `elaboration_depth`, `identity_relevance`, `affect_arousal`, `affect_dominance`, `novelty`, `memory_tier`, `source_type`, and later `hdbscan_probability` for encoding-strength formula |
| `R2StagedOutput` in `centroid_calculator.py` | Defined but NOT used in the live R2 path | Epics 4.1, 4.2, 4.4 | Live R2 builds `EpisodeCluster` directly and bypasses `R2StagedOutput`. Must be explicitly revived, replaced, or deleted before M4 adds encoding/coherence outputs |
| `ObservationContext` in `observation_context.py` | Already carried on `EpisodeCluster.member_contexts` with salience, novelty, affect, identity fields | Epics 4.1, 4.4, 4.6 | Rich signal surface exists post-clustering but is not connected to the centroid-weighting or coherence input paths. M4 must decide whether encoding-strength inputs come from the event protocol (pre-clustering) or from `ObservationContext` (post-aggregation) |
| `EpisodicLayerWriter` in `truth_writer/layers/episodic.py` | Writes `embedding_text`, `embedding_vector`, `embedding_model` for single embeddings | Epic 4.2 | Must be reconciled alongside `truth_write_assembler.py` and `truth_query_service.py` if multi-centroid ships |

### Milestone 4 Signal Availability And Fallback Design Principle

Milestone 4 inherits the M3 fallback-chain principle and extends it to encoding-strength and coherence inputs.

Not every encoding or coherence signal will be populated for every event. Causes include:

- **MW version gaps**: Events ingested under older MW versions may lack `elaboration_depth`, `identity_relevance`, or `affect_arousal`.
- **Sparse extraction**: `salience_score` may be absent or zero for low-content events.
- **Missing HDBSCAN probability**: Rescued or DBSCAN-fallback events may not carry meaningful membership probabilities.
- **No narrative thread**: Events without `narrative_thread_id` cannot contribute to narrative coherence.
- **Partial social context**: Solo events with no participants cannot contribute to social coherence.

Every M4 encoding-strength term, coherence dimension, and quality metric MUST implement a fallback chain:

1. **Primary signal** (strongest, most specific): e.g., `salience_score` for salience weighting.
2. **Secondary signal** (weaker but available): e.g., `importance_score` as salience fallback.
3. **Neutral fallback** (no signal available): term contributes its neutral default and its weight is redistributed proportionally to terms that have real data.

The neutral-fallback contract means:

- Missing encoding terms NEVER produce accidental zero-weight (event disappears from centroid) or max-weight (event dominates centroid).
- Missing coherence dimensions contribute `0.5` (uncertain) and their weight is redistributed.
- Per-event signal-availability masks are tracked so observability can distinguish "low encoding confidence because signals are sparse" from "low encoding because the event genuinely is not representative."

This fallback design applies uniformly to:

- `CentroidCalculator` encoding-strength formula (Epic 4.1)
- HDBSCAN probability combination (Epic 4.3)
- `EpisodicCoherenceScore` per-dimension computation (Epic 4.4)
- Support-signal encoding roles (Epic 4.6)

### Milestone 4 Encoding Input Design Decision

`ObservationContext` already carries most of the signals needed for encoding-strength computation
(`salience_score`, `novelty_score`, `affect_valence`, `affect_arousal`, `sentiment_score`, `intent_ultrabert`,
`intent_confidence`, `identity_relevance` implicitly through domain fields, `memory_tier` candidates, `source_type`).
It is built per member event during `_build_episode_cluster()` and stored on `EpisodeCluster.member_contexts`.

The design question is: should encoding-strength inputs come from the **event protocol** (pre-clustering,
via `CentroidableEvent`) or from **`ObservationContext`** (post-clustering, already aggregated)?

**Decision**: Encoding-strength inputs MUST come from the event protocol (`CentroidableEvent`), not from
`ObservationContext`. Rationale:

1. `CentroidCalculator.compute_weights()` runs BEFORE `_build_episode_cluster()` — it needs per-event
   weights to compute the centroid, and the centroid is needed to build the episode cluster.
2. `ObservationContext` is built AFTER centroiding — using it for weights would create a circular dependency.
3. The event protocol is the correct contract surface for "what each event contributes to centroid formation."
4. `ObservationContext` is the correct surface for "what each event contributes to coherence assessment"
   and episode metadata — this feeds Epic 4.4 coherence, not Epic 4.1 weighting.

Therefore:

- Issue 4.1.0 extends `CentroidableEvent` for encoding-strength inputs.
- Epic 4.4 coherence dimensions consume `ObservationContext` member contexts for post-clustering quality assessment.
- No circular dependency exists because the two input paths serve different phases of episode formation.

### Milestone 4 R2StagedOutput Decision

`R2StagedOutput` is defined in `centroid_calculator.py` (line 219) but is NOT imported or used in the live
R2 path (`r2_episodic_integrator.py`). The live R2 path builds `EpisodeCluster` objects directly and returns
them via `P03PhaseResult`. `R2StagedOutput` is exported from `__init__.py` and referenced by
`cluster_quality.py` as a protocol, but that protocol usage is also bypassed by the live path's
`compute_from_r2_output()` call.

**Decision**: `R2StagedOutput` must be explicitly addressed in Milestone 4 as a prerequisite (Issue 4.0.1).
Options:

1. **Revive**: Make it the canonical R2 output container, replace the current direct-`EpisodeCluster` build.
2. **Delete**: Remove it and update `cluster_quality.py` protocol references to use the live path directly.
3. **Reconcile**: Keep it as the internal centroid-phase output and define a clear transformation to `EpisodeCluster`.

The chosen option must be decided before Epic 4.1 changes the weighting model, because the weighting
model's output shape depends on whether `R2StagedOutput` or `EpisodeCluster` is the canonical container.

### Milestone 4 Context Pack

Read these before implementation or research begins.

| Priority | Source | Why It Must Be Read |
| -------- | ------ | ------------------- |
| 1 | `docs/pipelines/p03_enhancement_discovery/P03_R2_EPISODIC_INTEGRATION_DISCOVERY.md` Sections 21.8, 21.9, 21.10, 24.5, 24.6, 20.9 | Authoritative source for enhanced centroiding, multi-centroid target state, probability weighting, coherence metrics, and vectorization expectations. |
| 2 | `docs/pipelines/p03_enhancement_discovery/temp_r2_design.md` Subsystem 4 and Enhanced Quality Assessment | Defines the target encoding-strength formula, episode-encoding direction, and neuromorphic coherence dimensions. |
| 3 | `k0/modules/consolidation/algorithms/centroid_calculator.py` | Current centroid strategies, EpisodeCandidate shape, and R2StagedOutput batch metadata. |
| 4 | `tests/k0/pipelines/p03/test_r2_centroid_calculator.py` and `tests/k0/pipelines/p03/test_r2_integration.py` | Current tests pin the legacy weighting strategies and single-centroid assumptions. |
| 5 | `k0/modules/consolidation/algorithms/cluster_quality.py` | Current quality model still centers silhouette plus dormant grounding/correction signals. |
| 6 | `k0/pipelines/p03/phases/r2_episodic_integrator.py` `_build_episode_cluster()` and `_track_quality_and_adapt()` | Confirms what R2 currently aggregates into EpisodeCluster and how quality still flows into adaptive learning. |
| 7 | `k0/pipelines/p03/phase_outputs.py` `EpisodeCluster` | Shows that the aggregate R2 episode surface still has one centroid reference and limited encoding metadata. |
| 8 | `k0/db/alembic/versions/0027_st_epi.py` | Current storage contract for episodic memory still exposes a single `embedding_id`. |
| 9 | `k0/modules/consolidation/staging/truth_write_assembler.py` episodic assembly path | Confirms R6/R7 still write one embedding reference and one summary path for episodes. |
| 10 | `k0/modules/consolidation/truth_writer/layers/episodic.py` and `k0/modules/consolidation/staging/truth_query_service.py` | Downstream write and query surfaces still assume a single embedding column for `st_epi`. |
| 11 | `k0/modules/consolidation/algorithms/episodic_hdbscan.py` | Confirms probabilities/outlier scores already exist and can be threaded into encoding work. |
| 12 | `k0/modules/consolidation/algorithms/composite_distance.py` | Confirms matrix build is still nested-loop and that vectorization work must integrate with the real distance substrate. |

### Milestone 4 Research Requirement

Milestone 4 must be research-backed, not formula-declared. Extend the Milestone 2 research pack under
`poc/r2_phase_research` with a dedicated encoding-and-quality track before locking final centroid,
coherence, or multi-centroid storage decisions.

### Milestone 4 Required Research Tracks

| Track | Requirement | Why It Is Needed |
| ----- | ----------- | ---------------- |
| Encoding-strength research | Standalone centroid-weight experiments using salience, elaboration, identity, affect, recency, and HDBSCAN probability | Prevents arbitrary weight mixtures from becoming permanent episode representations |
| Retrieval-shape research | Compare single-centroid vs multi-centroid retrieval behavior on replayed episodes | Multi-centroid work is only justified if it helps retrieval or matching materially |
| Storage-contract research | Rehearse schema and serialization options for multi-centroid persistence and backward compatibility | The live `st_epi` path still assumes one `embedding_id` |
| Coherence research | Compute candidate episodic-coherence formulas on replayed clusters and compare against true silhouette and contamination proxies | Prevents another quality metric that looks plausible but does not correlate with better episodes |
| Probability-weighting research | Test whether HDBSCAN probabilities improve centroids or simply overfit dense cores | Soft membership exists already, but it may or may not help representation |
| Vectorization research | Measure parity, latency, and memory for NumPy-only broadcasting vs adding `scipy`-based paths | The repo does not currently declare `scipy`, so the dependency decision must be explicit |
| Support-signal encoding research | Measure whether narrative/cognitive/support signals belong in encoding strength, summaries, coherence, or nowhere | Prevents support signals from being smeared across every representation layer |

### Milestone 4 Research Questions

| Research ID | Question | Expected Research Form |
| ----------- | -------- | ---------------------- |
| M4-RSCH-01 | Which encoding-strength terms actually improve episode retrieval or representative quality over the current hybrid baseline? | Weight-sweep benchmark against replayed episodes and retrieval proxies |
| M4-RSCH-02 | Which secondary centroids materially improve episode matching or retrieval: start, end, emotional peak, narrative, or some smaller subset? | Multi-centroid ablation study with retrieval comparisons |
| M4-RSCH-03 | Do HDBSCAN probabilities improve centroids, or do they over-focus on dense cores and ignore important fringe events? | Probability-on/off comparison with rescue/noise edge cases |
| M4-RSCH-04 | Does episodic coherence correlate better with contamination and replay quality than silhouette alone? | Offline quality comparison on replayed cluster outputs |
| M4-RSCH-05 | Can multi-centroid representations fit the current write/query path, or is a schema change mandatory? | Storage rehearsal and migration note |
| M4-RSCH-06 | Is vectorization best implemented with pure NumPy broadcasting or by introducing `scipy` deliberately? | Performance and dependency tradeoff report |
| M4-RSCH-07 | Which narrative, cognitive, and support signals help encoding quality versus merely belonging in summaries and observability? | Support-signal ablation report |

### Milestone 4 Proof Obligations

| Proof ID | What Must Be Proven | Why It Matters | Suggested Research Shape |
| -------- | ------------------- | -------------- | ------------------------ |
| M4-POC-01 | Salience-composite weighting beats or matches the current hybrid centroid on replay retrieval and representative-quality proxies | Justifies replacing a simple, stable baseline | Replay centroid benchmark with ranked retrieval or nearest-episode comparisons |
| M4-POC-02 | HDBSCAN probability weighting improves centroids without letting rescued or fringe noise dominate them | Prevents cluster-confidence leakage into bad episode vectors | Compare dense-core-only, probability-weighted, and capped-probability strategies |
| M4-POC-03 | Multi-centroid representation provides measurable value over single-centroid storage | Avoids expensive schema and retrieval complexity with no benefit | Compare single vs multi-centroid retrieval hit quality and episode continuity |
| M4-POC-04 | EpisodicCoherenceScore better captures contamination and support-signal agreement than silhouette plus phantom feedback channels | Prevents another misleading quality loop | Offline comparison on good/bad clusters with contamination labels or proxies |
| M4-POC-05 | Vectorized matrix generation is mathematically identical to the scalar path for all supported gates and masks | Performance work cannot change clustering semantics silently | Matrix parity harness across curated scenarios |
| M4-POC-06 | Narrative, cognitive, and support signals improve encoding/coherence only in the roles assigned to them | Prevents support-signal sprawl | Role-ablation matrix across encoding, coherence, and summary tasks |
| M4-POC-07 | The chosen multi-centroid storage plan is backward-compatible with the current R6/R7 write path and `st_epi` consumers | Storage drift would break downstream retrieval and truth-writing behavior | Schema rehearsal and consumer compatibility test |

### Milestone 4 Research Deliverables

| Output | Purpose |
| ------ | ------- |
| `encoding_strength.py` research scorer | Standalone implementation for centroid-weight experiments |
| `encoding_scenarios.py` | Replay and hand-crafted episodes for representative, edge, and contamination cases |
| `retrieval_benchmark.py` | Single-centroid vs multi-centroid retrieval comparison harness |
| `coherence_research.py` | Candidate EpisodicCoherenceScore computation and comparison against baseline quality signals |
| `vectorization_benchmark.py` | Scalar vs vectorized parity, latency, and memory benchmark |
| `storage_rehearsal.py` | Multi-centroid schema/serialization rehearsal against current write-query expectations |
| `results/m4_decision_memo.md` | Approved encoding, coherence, vectorization, and storage direction for production work |

### Epic 4.1: Salience-Composite Centroid Weighting

**Discovery Reference**: Section 21.8
**Repo Status**: OPEN

#### Epic 4.1 Verified Current State

- `CentroidCalculator` only supports `uniform`, `importance`, `recency`, and `hybrid` strategies.
- It does not use `salience_score`, `elaboration_depth`, `identity_relevance`, or affective weighting.
- The `CentroidableEvent` protocol requires only `event_id`, `timestamp`, `embedding_768`, `importance_score` — too narrow for the encoding-strength formula. It must be extended before any new weighting term can read event fields.
- The current centroid tests are strongly pinned to those four strategies and their current semantics. These tests must be baselined before strategy replacement.

#### Epic 4.1 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 4.1.0 extend `CentroidableEvent` protocol | OPEN | Extend `CentroidableEvent` to declare all fields needed by the encoding-strength formula with `Optional` typing and neutral defaults. This is a prerequisite for 4.1.1-4.1.4 and must be coordinated with the enriched `EventLike` protocol from M3 Issue 3.1.0. |
| 4.0.1 resolve `R2StagedOutput` fate | OPEN | Decide whether to revive, delete, or reconcile `R2StagedOutput` before changing the weighting model. See Milestone 4 R2StagedOutput Decision above. |
| 4.0.2 baseline existing centroid test surface | OPEN | Snapshot and document the current centroid test surface (4 strategies, pinned assertions) before any strategy model changes. Tests pinned to legacy strategies must be consciously preserved as regression baselines or replaced with encoding-strength equivalents. |
| 4.1.1 define encoding-strength formula | OPEN | Replace legacy strategy names with a researched multi-factor encoding-strength model. |
| 4.1.2 expose weighting inputs cleanly | OPEN | Extend EventAdapter to satisfy the enriched `CentroidableEvent` protocol so centroiding has typed access to all encoding-strength inputs. |
| 4.1.3 revisit recency weighting | OPEN | Replace current linear recency dominance with softer decay and bounded influence. |
| 4.1.4 validate retrieval impact | OPEN | Prove the new weighting improves representative quality on replay datasets before production lock-in. |

#### Epic 4.1 Issue Execution Checklist

##### Issue 4.1.0 Extend `CentroidableEvent` protocol

| Item | Detail |
| ---- | ------ |
| Goal | Make `CentroidableEvent` declare all fields needed by the encoding-strength formula so centroiding uses typed access instead of `getattr` guessing. |
| Read | `k0/modules/consolidation/algorithms/centroid_calculator.py` `CentroidableEvent` protocol (lines 63-82); M3 Issue 3.1.0 enriched `EventLike` protocol; `EventAdapter` property surface; temp design Subsystem 4 encoding-weight factors. |
| Change | Extend `CentroidableEvent` with `Optional` typed fields for `salience_score`, `elaboration_depth`, `identity_relevance`, `affect_valence`, `affect_arousal`, `affect_dominance`, `novelty`, `memory_tier`, `source_type`, and a placeholder for `hdbscan_probability` (populated later by Epic 4.3). All new fields default to `None`. Coordinate with the enriched `EventLike` from M3 so both protocols share a consistent event contract surface. |
| Core idea | The protocol is the contract between EventAdapter and centroid computation. If the protocol stays minimal (4 fields), every encoding term reinvents `getattr` fallback logic independently, exactly as M3 discovered for `EventLike`. |
| Tests | Add protocol compliance tests proving EventAdapter satisfies the enriched `CentroidableEvent`. Add missing-field tests proving `None` defaults do not crash `compute_weights()`. |
| Success criteria | All encoding-strength terms use typed protocol access. No `getattr` fallback for fields that belong in the centroid contract. Protocol is coordinated with `EventLike` and `SplittableEvent`. |

**Codebase Reality** (verified 2026-03-07):

`CentroidableEvent` protocol (centroid_calculator.py L62-L83) has exactly 4 fields:

- `event_id`: str (L68)
- `timestamp`: int (L73)
- `embedding_768`: Optional[List[float]] (L78)
- `importance_score`: float (L83)

`compute_weights()` (L275-L326) reads only `importance_score` and `timestamp` from events. No other signal field is accessed. The 4-strategy enum (`WeightingStrategy` L49-L55): UNIFORM, IMPORTANCE, RECENCY, HYBRID.

`EventLike` protocol (composite_distance.py L120-L137) has 3 fields: event_id, timestamp, embedding_768. `SplittableEvent` (episode_splitter.py L112-L126) has 2 fields: event_id, timestamp. All three protocols are minimal and uncoordinated.

`EventAdapter` (r2_episodic_integrator.py L109-L309) already exposes salience_score (L272), affect_valence (L257), affect_arousal (L262), affect_dominance (L267), sentiment_score (L250), novelty_score is NOT exposed, memory_tier is NOT on P03EventState, source_type is NOT exposed. The adapter has the signals; the protocols do not declare them.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.3 (M4-RSCH-01): recency_exp wins with MRR=0.9006 (+6.6% vs hybrid). But Section 11.9 (M4-RSCH-07): ALL 9 cognitive/support signals are SUMMARY-ONLY -- baseline MRR=0.9975 is near-perfect with unweighted mean. The encoding-strength formula needs recency but not salience/elaboration/identity weighting on centroids. Protocol extension for those signals serves coherence (Epic 4.4) and metadata, not centroid weighting.

**Implementation Detail**:

1. Extend `CentroidableEvent` with Optional fields: salience_score, affect_valence, affect_arousal, affect_dominance, novelty_score, sentiment_score. All default None.
2. Do NOT add elaboration_depth, identity_relevance, memory_tier, source_type to CentroidableEvent -- M4-RSCH-07 proves they do not help encoding. Keep them on ObservationContext for coherence.
3. Coordinate with M3 `EventLike` extension: shared fields should use identical names and types.
4. Protocol compliance tests: EventAdapter satisfies enriched CentroidableEvent.
5. Missing-field tests: None defaults do not crash compute_weights().

##### Issue 4.0.1 Resolve `R2StagedOutput` fate

| Item | Detail |
| ---- | ------ |
| Goal | Decide whether `R2StagedOutput` is revived, deleted, or reconciled before M4 changes the weighting/coherence model. |
| Read | `centroid_calculator.py` `R2StagedOutput` (line 219); `r2_episodic_integrator.py` live path (bypasses `R2StagedOutput`); `cluster_quality.py` `R2OutputProtocol` usage; `__init__.py` export. |
| Change | Choose one: (a) revive `R2StagedOutput` as the canonical R2 output container and refactor `_build_episode_cluster` to produce it, (b) delete it and update `cluster_quality.py` protocol references, or (c) keep it as internal centroid-phase output with a clear transformation to `EpisodeCluster`. Document the chosen option in the M4 decision memo. |
| Core idea | A dead container that looks alive confuses every consumer. M4 changes the weighting and quality model — the output container question must be settled first. |
| Tests | If revived: add output-shape tests. If deleted: verify no import breaks. If reconciled: add transformation tests. |
| Success criteria | `R2StagedOutput` has a single documented role (live, dead, or bridge) and M4 code implements that role consistently. |

**Codebase Reality** (verified 2026-03-07):

`R2StagedOutput` (centroid_calculator.py L203-L270): dataclass with 7 fields (episode_candidates, cluster_count, noise_count, avg_cluster_size, total_events_processed, batch_silhouette_score, batch_cohesion_avg) plus methods add_candidate(), finalize(), singleton_rate, to_dict().

It is exported from `__init__.py` and referenced by `cluster_quality.py` `R2OutputProtocol` (L161-L167: batch_silhouette_score, cluster_count, noise_count). However, the live R2 path in r2_episodic_integrator.py builds `EpisodeCluster` objects directly via `_build_episode_cluster()` and returns them via `P03PhaseResult`. The live path calls `ClusterQualityTracker.compute_from_r2_output()` but passes a dict-like object, not an R2StagedOutput instance.

`R2StagedOutput` is effectively dead code -- defined, exported, protocol-referenced, but never instantiated by the live pipeline.

**Research Evidence**:

R2_RESEARCH_FINAL.md does not reference R2StagedOutput. The research pipeline builds its own output containers. M4-RSCH-05 (storage rehearsal) recommends json_blob for multi-centroid persistence -- this affects EpisodeCluster, not R2StagedOutput. The decision is architectural, not research-driven.

**Implementation Detail**:

1. Recommended option: DELETE. R2StagedOutput duplicates fields already on EpisodeCluster and P03PhaseResult.
2. Update R2OutputProtocol in cluster_quality.py to reference EpisodeCluster fields directly (cluster_count, noise_count from P03PhaseResult; silhouette from ClusterQualityMetrics).
3. Remove R2StagedOutput from **init**.py exports and centroid_calculator.py.
4. Verify no external consumer imports R2StagedOutput (grep across codebase).
5. Preserve R2StagedOutput test coverage (TestR2StagedOutput in test_r2_centroid_calculator.py) only if the equivalent behavior is tested elsewhere.

##### Issue 4.0.2 Baseline existing centroid test surface

| Item | Detail |
| ---- | ------ |
| Goal | Snapshot the current centroid test surface before any strategy model changes. |
| Read | `tests/k0/pipelines/p03/test_r2_centroid_calculator.py`; current `WeightingStrategy` enum; `compute_weights()` method. |
| Change | Document which tests pin which strategy behavior. Decide explicitly: (a) preserve legacy tests as regression baselines alongside new encoding-strength tests, or (b) replace legacy tests with encoding-strength equivalents and archive the old assertions. |
| Core idea | M3 learned that modifying rescue logic without baseline test coverage creates a regression gap. The same applies to replacing centroid strategies. |
| Tests | No new tests needed — this issue is about documenting and consciously managing existing tests. |
| Success criteria | A decision exists about whether legacy strategy tests survive, get archived, or get replaced — before any strategy code changes. |

**Codebase Reality** (verified 2026-03-07):

test_r2_centroid_calculator.py has 17 tests across 6 test classes:

- `TestWeightingStrategies` (5 tests): pin uniform (1/n), importance (higher score = higher weight), recency (most recent = highest), hybrid (0.7*importance + 0.3*recency), same-timestamps fallback.
- `TestCentroidComputation` (3 tests): L2 normalization, single-event centroid, no-embeddings error.
- `TestVarianceComputation` (3 tests): variance in [0,1], identical embeddings = 0, single event = 0.
- `TestCentroidResult` (3 tests): all fields populated, centroid_list property, empty returns zero.
- `TestEpisodeCandidate` (2 tests): field population, duration_ms property.
- `TestR2StagedOutput` (3 tests) + `TestEventUpdate` (1 test).

test_r2_integration.py has 16 tests covering end-to-end cluster production, semantic grouping, splitting, adaptive eps/min_samples adjustment, write structure, quality metrics, and distance matrix properties.

**Research Evidence**:

M4-RSCH-01 shows recency_exp (MRR=0.9006) replaces hybrid (MRR=0.8344). The 5 TestWeightingStrategies tests will need updating: uniform may remain as a baseline, importance stays, recency changes to exponential, hybrid gets replaced. M4-RSCH-03 REJECTS probability weighting, so no probability-related test additions needed.

**Implementation Detail**:

1. Snapshot current test assertions in a brief test-surface document before any changes.
2. Decision: REPLACE legacy strategy tests with encoding-strength equivalents. Archive old assertions as comments for regression reference.
3. Keep TestCentroidComputation, TestVarianceComputation, TestCentroidResult, TestEpisodeCandidate unchanged -- these are strategy-independent.
4. TestR2StagedOutput tests: if Issue 4.0.1 deletes R2StagedOutput, these tests are removed with it.
5. test_r2_integration.py tests remain as end-to-end regression baselines.

##### Issue 4.1.1 Define the encoding-strength formula

| Item | Detail |
| ---- | ------ |
| Goal | Replace the current `uniform` / `importance` / `recency` / `hybrid` worldview with a researched encoding-strength formula aligned to the target design. |
| Read | `centroid_calculator.py`; temp design Subsystem 4; discovery Section 21.8; current centroid tests; M4 fallback design principle in this plan. |
| Change | Define a production strategy that combines salience, elaboration depth, identity relevance, affective intensity, memory tier, recency, and later probability weighting. Each term must implement the M4 fallback chain: primary signal -> secondary signal -> neutral default with weight redistribution when signals are absent. Include per-event signal-availability mask tracking. |
| Core idea | Milestone 4 should encode why an event matters to the episode representation, not merely when it happened or its coarse importance score. |
| Tests | Add formula tests that cover each contributing term, term clipping, fully sparse fallback behavior, and weight redistribution under partial signal availability. |
| Success criteria | The new strategy is explicit, bounded, fallback-safe, and supported by offline research artifacts rather than intuition. |

**Codebase Reality** (verified 2026-03-07):

`compute_weights()` (L275-L326) implements 4 strategies via a match/case on `WeightingStrategy`:

- UNIFORM (L289): `np.ones(n) / n`
- IMPORTANCE (L292-L297): `importance_score + 0.01`, normalized
- RECENCY (L299-L306): linear `(ts - min) / (max - min + 1)` + 0.1 floor, normalized; uniform fallback for equal timestamps
- HYBRID (L308-L322): `0.7 * importance + 0.3 * recency + 0.01`, normalized

The recency implementation is linear normalization, which is the WORST performer in research (linear_recency MRR=0.5990 -- collapses). The hybrid implementation uses fixed 0.7/0.3 weights with no fallback chain.

No signal-availability mask tracking. No per-event sparse-data handling. No weight redistribution for missing signals.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.3 (M4-RSCH-01): recency_exp wins (MRR=0.9006). The exponential decay formula emphasizes recent events without the extreme bias of linear normalization. Section 11.9 (M4-RSCH-07): ALL cognitive/support signals are SUMMARY-ONLY (baseline MRR=0.9975) -- the encoding-strength formula should NOT include salience, novelty, identity, or affect weighting. M4-RSCH-03 REJECTS probability weighting.

The approved formula is effectively: `weight_i = exp(-decay * (t_max - t_i) / t_range)`, normalized to sum=1. This is a 1-factor model (recency only), not a multi-factor encoding-strength formula.

**Implementation Detail**:

1. Add RECENCY_EXP strategy to WeightingStrategy enum.
2. Implement exponential decay: `w_i = exp(-lambda * (t_max - t_i) / (t_max - t_min + 1))` with configurable decay lambda.
3. Preserve UNIFORM as a baseline. IMPORTANCE and HYBRID can remain for backward compatibility but are not the production path.
4. No multi-factor encoding-strength formula needed -- research proves recency is the only weighting factor that helps.
5. Fallback: if all timestamps equal, return uniform weights (same as current RECENCY fallback).
6. Tests: recency_exp produces higher weights for recent events, exponential vs linear comparison, equal-timestamp fallback, configurable decay parameter.

##### Issue 4.1.2 Expose weighting inputs cleanly

| Item | Detail |
| ---- | ------ |
| Goal | Ensure centroiding can consume all required weighting inputs through the enriched `CentroidableEvent` protocol from Issue 4.1.0. |
| Read | Enriched `CentroidableEvent` from Issue 4.1.0; `EventAdapter` in `r2_episodic_integrator.py`; enriched `EventLike` from M3 Issue 3.1.0. |
| Change | Extend EventAdapter to satisfy the enriched `CentroidableEvent` protocol, wrapping the corresponding `P03EventState` fields. Ensure the encoding-input surface is consistent with M3's enriched `EventLike` — both protocols should source from the same EventAdapter properties without diverging. Note: encoding inputs come from the event protocol (pre-clustering), NOT from `ObservationContext` (post-clustering). See Milestone 4 Encoding Input Design Decision above. |
| Core idea | The weighting model should have one truthful input contract rather than repeatedly reaching through `getattr()` for whatever field happens to exist. |
| Tests | Add protocol/adapter compliance tests proving all encoding-strength fields are present or intentionally defaulted to `None`. |
| Success criteria | Encoding inputs are explicit, typed, and future Milestone 4.6 fields have a clear path into centroid weighting via the protocol. |

**Codebase Reality** (verified 2026-03-07):

EventAdapter (r2_episodic_integrator.py L109-L309) exposes 22 properties. For centroid weighting, the only input needed is `timestamp` (already on CentroidableEvent via L166). `importance_score` is also already on the protocol (L200 via P03EventState.importance_score).

The research result (M4-RSCH-07: all signals SUMMARY-ONLY) means the centroid formula only needs timestamp access, which is already on the protocol. The "expose weighting inputs cleanly" issue is largely resolved by M4-RSCH-07 proving those inputs are not needed.

However, for Epic 4.4 (coherence), ObservationContext already carries the richer signal surface: salience_score (L90), novelty_score (L92), affect_valence (L74), affect_arousal (L75), sentiment_score (L72), intent_ultrabert (L83), social_context (L115), location_name (L107). ObservationContext is built post-clustering by `_build_episode_cluster()` at L1363-L1369 via `ObservationContext.from_event(e.event)`.

**Research Evidence**:

M4-RSCH-01: recency_exp only needs timestamp. M4-RSCH-07: no signal improves encoding beyond MRR=0.9975 baseline. The "weighting inputs" issue scope shrinks to: ensure CentroidableEvent has timestamp (already done) and prepare a clear path for coherence inputs via ObservationContext (already done by the existing from_event() factory).

**Implementation Detail**:

1. This issue has reduced scope post-research: CentroidableEvent already has timestamp for recency_exp.
2. Verify EventAdapter satisfies CentroidableEvent protocol (add protocol compliance test).
3. Ensure M3 EventLike and CentroidableEvent share consistent field names for overlapping fields.
4. For coherence inputs: document that ObservationContext.from_event() is the input path for Epic 4.4, not CentroidableEvent.
5. No new EventAdapter properties needed specifically for centroid weighting.

##### Issue 4.1.3 Revisit recency weighting

| Item | Detail |
| ---- | ------ |
| Goal | Replace the current linear recency term with a softer decay that does not let one late event dominate the episode vector. |
| Read | `compute_weights()` in `centroid_calculator.py`; temp design encoding notes; replay results once available. |
| Change | Introduce an exponential, logarithmic, or capped-recency decay and document how it interacts with salience and identity-driven terms. |
| Core idea | Recency matters, but the current linear normalization is too crude for episodic representation. |
| Tests | Add same-cluster scenarios where a very recent but low-salience event should not overpower a salient earlier anchor. |
| Success criteria | Recency helps representation without collapsing the centroid onto the last event in the cluster. |

**Codebase Reality** (verified 2026-03-07):

Current recency weighting (compute_weights RECENCY, L299-L306): `weight = (ts - min_ts) / (max_ts - min_ts + 1) + 0.1`, normalized. This is linear normalization to [0.1, ~1.1] range. For clusters spanning hours, the most recent event gets ~1.1 weight while the earliest gets ~0.1 -- a 10:1 ratio that can dominate the centroid.

The HYBRID strategy (L308-L322) mitigates this with `0.7 * importance + 0.3 * recency`, but importance_score is coarse (often uniform) so recency still dominates.

The floor of 0.1 prevents total erasure of early events but does not prevent disproportionate influence of the last event.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.3: linear_recency MRR=0.5990 (WORST strategy -- extreme recency bias collapses centroid onto last event). recency_exp MRR=0.9006 (BEST -- exponential decay naturally bounds recency influence). The exponential decay curve gives recent events higher weight while keeping early events meaningfully represented.

The research directly validates this issue: linear recency is harmful, exponential recency is beneficial.

**Implementation Detail**:

1. Replace RECENCY strategy logic with exponential decay: `w_i = exp(-lambda * (t_max - t_i) / (t_max - t_min + eps))`.
2. Configurable lambda parameter (research used specific decay rate -- extract from r2_final_pipeline.py).
3. Floor: exp(-lambda * 1.0) for the oldest event ensures minimum contribution (never zero).
4. The exp decay naturally bounds the ratio between newest and oldest events, unlike linear.
5. Preserve uniform fallback for equal timestamps.
6. Test: verify newest/oldest weight ratio is bounded (e.g., <= 5:1 for typical lambda).

##### Issue 4.1.4 Validate retrieval impact

| Item | Detail |
| ---- | ------ |
| Goal | Prove the new weighting improves representative quality in replay and retrieval comparisons. |
| Read | Research harness outputs from `encoding_strength.py` and `retrieval_benchmark.py`; current hybrid baseline behavior. |
| Change | Benchmark legacy hybrid against candidate encoding-strength formulas using retrieval- and match-oriented proxies. |
| Core idea | Better-looking math is irrelevant if it does not improve how episodes are represented and later found. |
| Tests | Add research-backed regression fixtures and focused production tests for the approved strategy. |
| Success criteria | The approved weighting strategy outperforms or clearly matches the current baseline on replay metrics and edge cases. |

**Codebase Reality** (verified 2026-03-07):

The current production centroid uses HYBRID strategy (0.7*importance + 0.3*recency). No retrieval benchmarks exist in the production test suite -- test_r2_centroid_calculator.py tests weight computation mechanics (sums to 1.0, relative ordering) but not retrieval quality or representative quality.

test_r2_integration.py has `test_centroid_l2_normalized` and `test_centroid_variance_low_for_similar_events` but these test centroid properties, not retrieval effectiveness.

The research pipeline (r2_final_pipeline.py) contains the MRR benchmarking infrastructure that can be adapted for production validation.

**Research Evidence**:

M4-RSCH-01: recency_exp MRR=0.9006 vs hybrid MRR=0.8344 -- a +6.6% improvement on 246 clusters from the replay corpus. This is the validation result. The replay dataset uses the same life_events.jsonl corpus (1360 events, 32 sequences) that established the M2/M3 baseline.

M4-RSCH-07: unweighted mean MRR=0.9975 -- near-perfect with the corrected clustering pipeline. This suggests that clustering quality (from M2/M3) matters more than centroid weighting. recency_exp still helps for edge cases where event ordering matters.

**Implementation Detail**:

1. Research validation is already complete (M4-RSCH-01). The production implementation task is: integrate recency_exp into CentroidCalculator and verify it reproduces the research MRR on the replay corpus.
2. Add a focused production test: create a cluster with known temporal ordering, verify the centroid is pulled toward recent events but not collapsed onto them.
3. Preserve HYBRID as a fallback strategy during rollout. If recency_exp regresses on production data, HYBRID is the fallback.
4. Add retrieval-oriented regression fixtures from the research corpus as permanent test cases.

### Epic 4.2: Multi-Centroid Episode Representation

**Discovery Reference**: Section 21.9
**Repo Status**: OPEN

#### Epic 4.2 Verified Current State

- R2 produces a single centroid per cluster.
- No start/end/emotional-peak/narrative centroid set exists.
- `EpisodeCluster` and `EpisodeCandidate` still expose only one centroid reference.
- `st_epi` still persists one `embedding_id`, and the write/query path still assumes one embedding column for episodic memory.

#### Epic 4.2 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 4.2.1 define centroid-set schema | OPEN | Decide how multi-centroid state lives in `EpisodeCluster`, `EpisodeCandidate`, and persistence surfaces. |
| 4.2.2 compute secondary centroids | OPEN | Add start, end, emotional-peak, and narrative centroids only after replay evidence supports them. |
| 4.2.3 wire storage path | OPEN | Reconcile multi-centroid persistence with the current single-`embedding_id` `st_epi` contract. Must also reconcile `EpisodicLayerWriter` in `truth_writer/layers/episodic.py` which writes `embedding_text`, `embedding_vector`, `embedding_model` for single embeddings. |
| 4.2.4 wire retrieval and query consumers | OPEN | Ensure query and retrieval paths can exploit or safely ignore richer centroid sets. |
| 4.2.5 validate backward compatibility | OPEN | Preserve single-centroid compatibility for existing consumers during rollout. |

#### Epic 4.2 Issue Execution Checklist

##### Issue 4.2.1 Define the centroid-set schema

| Item | Detail |
| ---- | ------ |
| Goal | Define the representation surface for a richer episode embedding set before computing any additional vectors. |
| Read | `phase_outputs.py` `EpisodeCluster`; `centroid_calculator.py` `EpisodeCandidate`; `serializer.py`; `0027_st_epi.py`; `truth_write_assembler.py`. |
| Change | Decide whether multi-centroid state is represented as named embedding references, JSON metadata, a side table, or a staged transitional schema. |
| Core idea | Multi-centroid work is a representation change first and a math change second. |
| Tests | Add serialization and staged-output tests covering presence, absence, and partial population of centroid sets. |
| Success criteria | There is one clear schema plan that production code, writes, and queries can all implement consistently. |

**Codebase Reality** (verified 2026-03-07):

`EpisodeCluster` (phase_outputs.py L77-L161): single `centroid_embedding_id: Optional[str]` at L93. No field for secondary centroids, centroid metadata, or centroid set.

`EpisodeCandidate` (centroid_calculator.py L121-L196): single `centroid_embedding: Optional[List[float]]` at L147 and `centroid_embedding_id: Optional[str]` at L150.

`st_epi` schema (0027_st_epi.py): single `embedding_id` column (L94, Text, nullable). 33 total columns, 4 indexes. No centroid_metadata or secondary embedding columns.

`truth_write_assembler.py` (L517-L530): resolves single `embedding_id` from `cluster.centroid_embedding_id`, falls back to first event's embedding_id.

All four surfaces assume exactly one embedding per episode.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.7 (M4-RSCH-05): json_blob wins. Recommended schema: add `centroid_metadata` JSON column to st_epi containing secondary centroid references (emotional_peak, narrative_anchor, start, end). MRR gap: +0.2147 vs single centroid (exceeds 0.05 threshold). json_blob is simpler than side_table, same MRR, backward compatible.

Section 11.4 (M4-RSCH-02): best_of_all (5-way) MRR=0.9627. Emotional_peak found in 246/246 clusters (100%), narrative_anchor in 113/246 (45.9%). Primary + emotional_peak + narrative_anchor captures the most retrieval-relevant perspectives.

**Implementation Detail**:

1. Add `centroid_metadata: Optional[Dict[str, Any]]` to EpisodeCluster with structure: `{"emotional_peak": {"embedding_id": str, "event_id": str}, "narrative_anchor": {"embedding_id": str, "event_id": str}, ...}`.
2. Add `centroid_metadata` JSON column to st_epi via new Alembic migration.
3. Preserve `centroid_embedding_id` as the canonical primary centroid FK (backward compatible).
4. Secondary centroids reference existing st_vec entries (event embeddings) -- no new vector generation needed.
5. EpisodeCandidate gets optional `secondary_centroids` dict alongside existing centroid fields.

##### Issue 4.2.2 Compute secondary centroids

| Item | Detail |
| ---- | ------ |
| Goal | Compute only the secondary centroids that prove useful in research. |
| Read | Discovery Section 21.9; temp design encoding notes; replay retrieval benchmark outputs. |
| Change | Implement start, end, emotional-peak, and narrative centroids as named strategies or selectors, with deterministic selection rules and missing-signal fallback behavior. |
| Core idea | The target is not “more centroids.” The target is preserving retrieval-relevant views of the same episode. |
| Tests | Add cases for short episodes, low-affect episodes, no-thread episodes, and clusters where multiple candidate anchor events compete. |
| Success criteria | Secondary centroids are deterministic, interpretable, and limited to the researched set that actually helps. |

**Codebase Reality** (verified 2026-03-07):

CentroidCalculator.compute() (L436-L535) produces a single centroid via weighted mean of member embeddings. No secondary centroid computation exists.

`_build_episode_cluster()` (r2_episodic_integrator.py, ~176 lines) already iterates all cluster events and has access to: timestamps (for start/end), sentiment_score (for emotional peak), narrative_thread_id (for narrative anchor). The selection logic for secondary centroids can reuse this iteration.

ObservationContext.from_event() (observation_context.py) carries sentiment_score, affect_valence, affect_arousal for emotional peak selection.

**Research Evidence**:

M4-RSCH-02: best_of_all (5-way: primary + start + end + emotional_peak + narrative_anchor) MRR=0.9627. But primary+emotional_peak+narrative_anchor MRR=0.9003, while primary_only MRR=0.9140 -- adding emo+nar without start+end actually hurts slightly. Start+end alone MRR~0.35 (terrible as standalone, but useful in combination).

Emotional_peak: select event with max |affect_valence| or max affect_arousal. 100% coverage (every cluster has at least one event with affect data).
Narrative_anchor: select event with the dominant narrative_thread_id. 45.9% coverage.
Start/end: select events with min/max timestamp. 100% coverage.

**Implementation Detail**:

1. Add secondary centroid selectors to CentroidCalculator or a new `SecondaryCentroidSelector` class.
2. Selection rules (deterministic):
   - `emotional_peak`: event with max `abs(affect_valence) + affect_arousal`
   - `narrative_anchor`: event with the most common narrative_thread_id in the cluster
   - `start`: event with min timestamp
   - `end`: event with max timestamp
3. Each selector returns the event's existing embedding_768 reference -- no new embedding computation.
4. Missing signal fallback: if narrative_thread_id is absent for all events, narrative_anchor is null.
5. Tests: short episodes (1-2 events where all selectors return the same event), competing emotional peaks, no-thread episodes.

##### Issue 4.2.3 Wire the storage path

| Item | Detail |
| ---- | ------ |
| Goal | Make multi-centroid persistence real instead of leaving it as in-memory-only state. |
| Read | `0027_st_epi.py`; `truth_write_assembler.py`; `truth_writer/layers/episodic.py` (`EpisodicLayerWriter` and `EpisodeWriteData`); `r7_truth_writer.py`. |
| Change | Extend storage and write-path contracts for multi-centroid support or define an explicit compatibility layer that preserves one canonical `embedding_id` while storing secondary centroids safely elsewhere. Must address THREE write surfaces: (1) `truth_write_assembler.py` which writes `embedding_id` to the staged record, (2) `EpisodicLayerWriter` which writes `embedding_text`, `embedding_vector`, `embedding_model` to the layer output, and (3) `truth_query_service.py` which JOINs `st_epi.embedding_id` to `st_vec`. All three assume single-embedding semantics today. |
| Core idea | The current `st_epi` contract stores one embedding. Multi-centroid work is incomplete until storage truth matches the runtime representation. The episodic layer writer is an additional single-embedding surface that must not be forgotten. |
| Tests | Add write-layer tests for canonical-only, canonical-plus-secondary, and backward-compatible read/write scenarios across all three write surfaces. |
| Success criteria | R6/R7 can persist the approved centroid-set shape without breaking existing episodic writes. All three write surfaces handle multi-centroid or explicitly preserve single-centroid compatibility. |

**Codebase Reality** (verified 2026-03-07):

Three write surfaces assume single-embedding semantics:

1. **truth_write_assembler.py** (L517-L530): Writes `embedding_id` from `cluster.centroid_embedding_id`. Falls back to first event embedding_id if centroid is None. Single field.

2. **EpisodicLayerWriter._insert()** (episodic.py L194-L303): INSERT SQL includes `embedding_text`, `embedding_vector`, `embedding_model`, `embedding_id`. All four are single-valued. The TextVectorCoordinator generates one text+vector pair per episode.

3. **truth_query_service._query_layer()** (L279-L367): `JOIN st_vec v ON t.embedding_id = v.embedding_id`. Single JOIN, single vector per episode.

st_epi schema has no centroid_metadata column (would need migration).

**Research Evidence**:

M4-RSCH-05: json_blob recommended. One new column (`centroid_metadata` JSONB) on st_epi. Backward compatible: old episodes have NULL centroid_metadata, query path falls back to primary embedding_id. MRR gap: +0.2147 justifies the schema change.

Write surface impact from research:

- TruthWriteAssembler: add centroid_metadata JSON field to the staged record
- EpisodicLayerWriter: write centroid_metadata JSON alongside primary embedding fields
- TruthQueryService: add optional secondary vector lookup for re-ranking (retrieval-time only)

**Implementation Detail**:

1. New Alembic migration: `ALTER TABLE st_epi ADD COLUMN centroid_metadata JSONB DEFAULT NULL`.
2. TruthWriteAssembler: write `centroid_metadata` JSON from EpisodeCluster.centroid_metadata. Null-safe (old code path produces NULL).
3. EpisodicLayerWriter._insert(): add `centroid_metadata` to INSERT SQL. The JSON contains references to existing st_vec entries, not new vectors.
4. TruthQueryService: Phase 1 -- no query change (primary embedding_id JOIN unchanged). Phase 2 -- add optional secondary centroid re-ranking at retrieval time.
5. Backward compatibility: episodes with NULL centroid_metadata behave exactly as today.
6. Tests: write with/without centroid_metadata, read old episodes (NULL metadata), mixed population.

##### Issue 4.2.4 Wire retrieval and query consumers

| Item | Detail |
| ---- | ------ |
| Goal | Ensure downstream retrieval/query paths can either use richer centroid sets or safely ignore them. |
| Read | `truth_query_service.py`; any R5 or downstream retrieval code that loads episodic embeddings; `serializer.py`. |
| Change | Update query and retrieval paths to define which centroid is canonical for default retrieval and how optional secondary centroids are exposed to future consumers. |
| Core idea | A richer representation is only useful if retrieval semantics are explicit. |
| Tests | Add query-surface tests for canonical retrieval plus optional secondary-centroid access. |
| Success criteria | Default consumers keep working, and richer consumers have a documented access pattern for additional centroids. |

**Codebase Reality** (verified 2026-03-07):

`truth_query_service.py` find_candidates() (L216-L277) iterates all layers (st_hipp, st_sem, st_epi), queries each via _query_layer(), computes cosine similarity against query vector, returns top-k. For st_epi, this always uses the primary embedding_id.

`_query_layer()` (L279-L367) returns `(record_id, vector, vector_dim, confidence)` tuples. The vector is always the single primary embedding.

`r2_episodic_integrator.py` `_query_existing_episodes()` (L1717) and `_match_events_to_existing_episodes()` (L1823) also query st_epi by primary embedding_id for episode matching/reinforcement.

No consumer currently expects multiple vectors per episode.

**Research Evidence**:

M4-RSCH-02: best_of_all MRR=0.9627 vs primary_only MRR=0.9140. The +4.9% improvement comes from using the best-matching secondary centroid at retrieval time. Storage rehearsal (M4-RSCH-05): secondary centroids are only needed at retrieval time, not for reconciliation matching.

**Implementation Detail**:

1. Phase 1 (M4): Add an optional `use_secondary_centroids: bool` parameter to find_candidates(). When True, also load centroid_metadata JSON and compute similarity against secondary centroids for st_epi results. Return the best similarity across all centroids per episode.
2. Phase 1 default: False (existing behavior unchanged).
3. Episode matching (_query_existing_episodes) stays on primary centroid only -- secondary centroids do not change reconciliation behavior.
4. Tests: retrieval with/without secondary centroids, episodes with no centroid_metadata, mixed population.

##### Issue 4.2.5 Validate backward compatibility

| Item | Detail |
| ---- | ------ |
| Goal | Avoid breaking the current single-centroid assumptions while multi-centroid support rolls out. |
| Read | Existing episodic writer/query tests plus any schema migration plan from Issue 4.2.3. |
| Change | Keep one canonical episode embedding path stable during rollout and add compatibility behavior for episodes that only have a single centroid. |
| Core idea | The system already has a large single-centroid footprint; migration has to be deliberate. |
| Tests | Add mixed-population tests with legacy single-centroid episodes and newly written multi-centroid episodes. |
| Success criteria | No existing episodic read/write path fails when the repository contains both legacy and upgraded episode representations. |

**Codebase Reality** (verified 2026-03-07):

The current st_epi table has 33 columns and ~78 rows (per stored memory). All existing episodes have a single embedding_id and no centroid_metadata. The migration path adds a NULLABLE JSONB column, so all existing rows get NULL centroid_metadata automatically.

TruthWriteAssembler, EpisodicLayerWriter, and TruthQueryService all use hardcoded column lists in their SQL. Any new column must be added to all three surfaces.

EpisodeCluster serialization happens via P03PhaseResult (phase_outputs.py) which passes through the R6/R7 truth writing pipeline. Adding centroid_metadata requires it to survive serialization.

**Research Evidence**:

M4-RSCH-05 explicitly tested backward compatibility: json_blob strategy preserves single-centroid semantics for existing episodes (NULL centroid_metadata = primary-only retrieval). No migration risk for existing data.

**Implementation Detail**:

1. Migration: NULLABLE JSONB column, no DEFAULT value (existing rows get NULL).
2. All SQL paths must handle NULL centroid_metadata gracefully (COALESCE or IS NOT NULL checks).
3. Mixed-population integration test: create legacy episodes (no metadata), create new episodes (with metadata), verify read/write/retrieval works for both.
4. Rollback plan: column can be dropped without data loss if multi-centroid is reverted.
5. Version the centroid_metadata JSON schema: `{"version": 1, "centroids": {...}}` for future extensibility.

### Epic 4.3: HDBSCAN Probability-Augmented Centroids

**Discovery Reference**: Section 21.10
**Repo Status**: OPEN

#### Epic 4.3 Verified Current State

- HDBSCAN produces probabilities.
- Centroid weighting does not use those probabilities today.
- The probability surface exists in `HDBSCANClusteringResult`, but it is not threaded into `EpisodeCluster` or `CentroidCalculator` inputs.

#### Epic 4.3 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 4.3.1 pass probabilities into centroiding | OPEN | Thread membership probabilities through the centroid calculation path. |
| 4.3.2 define combination rule | OPEN | Decide exact interaction between encoding strength and HDBSCAN membership probability. |
| 4.3.3 verify rescued/noisy points behavior | OPEN | Ensure rescued fringe points or weak clusters do not dominate centroid formation. |
| 4.3.4 validate probability value | OPEN | Prove probability weighting improves representation enough to justify the added complexity. |

#### Epic 4.3 Issue Execution Checklist

##### Issue 4.3.1 Pass probabilities into centroiding

| Item | Detail |
| ---- | ------ |
| Goal | Make HDBSCAN soft membership available to centroid computation. |
| Read | `episodic_hdbscan.py` result surface; `r2_episodic_integrator.py` cluster-build flow; `centroid_calculator.py`. |
| Change | Extend cluster-build and centroid-input surfaces so per-event membership probability can be supplied alongside encoding-strength inputs. |
| Core idea | Probability weighting cannot exist if probabilities are discarded before the episode representation phase. |
| Tests | Add wiring tests that prove probabilities survive from clustering output into centroid computation. |
| Success criteria | Per-event probability is available at the centroid layer without inference hacks or index-order ambiguity. |

**Codebase Reality** (verified 2026-03-07):

`HDBSCANClusteringResult` (episodic_hdbscan.py L170-L199) stores `probabilities: List[float]` (L195) and `outlier_scores: List[float]` (L198). These are populated from HDBSCAN fit output at L282-L300 (_run_hdbscan) or simulated as 1.0/0.0 by DBSCAN fallback at L302-L323.

However, probabilities are NOT threaded into EpisodeCluster or CentroidCalculator inputs. The path breaks at `_build_episode_cluster()` in r2_episodic_integrator.py -- it receives cluster_events (List[EventAdapter]) but not per-event probabilities. The probability array is indexed by global event position, not by cluster membership, creating an index-alignment challenge.

CentroidableEvent protocol has no probability field. CentroidCalculator.compute_weights() has no probability input.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.5 (M4-RSCH-03): REJECTED. Uniform MRR=0.8943 beats all probability strategies. Best prob strategy: prob_floor_x_imp MRR=0.8813. 1217/1360 events (89.5%) had prob > 0.01 -- probabilities are nearly uniform for most events, providing minimal discrimination.

**Implementation Detail**:

1. RESEARCH REJECTS THIS ISSUE. M4-RSCH-03 proves probability weighting does not improve centroids.
2. However, threading probabilities through the pipeline still has value for: observability (log probability distribution per cluster), rescue quality tracking (low-prob rescued events), coherence diagnostics (Epic 4.4).
3. Minimal implementation: add `probability` field to EpisodeCluster or ObservationContext per member event. Do NOT use it for centroid weighting.
4. The index-alignment problem remains: probabilities array is global, cluster membership is per-cluster. Must map global indices to cluster-local events during _build_episode_cluster.
5. Defer full implementation unless Epic 4.4 coherence requires probability as a diagnostic input.

##### Issue 4.3.2 Define the combination rule

| Item | Detail |
| ---- | ------ |
| Goal | Decide how membership probability modifies encoding strength. |
| Read | temp design weighting notes; HDBSCAN probability semantics; research outputs from M4-POC-02. |
| Change | Define whether probability multiplies, caps, or modulates the encoding-strength weight, including floor behavior for rescued or low-confidence members. |
| Core idea | Probability is a confidence signal, not a replacement for salience or identity-driven importance. |
| Tests | Add cases for high-salience/low-probability, low-salience/high-probability, and balanced events. |
| Success criteria | Probability interaction is explicit, bounded, and does not erase non-density reasons an event should represent the episode. |

**Codebase Reality** (verified 2026-03-07):

CentroidCalculator.compute_weights() (L275-L326) returns a weight array that is normalized to sum=1.0. The 4 current strategies (uniform, importance, recency, hybrid) all produce final weights via division by sum. Any probability multiplier would need to be applied before normalization.

The hybrid formula is: `0.7 * importance_weights + 0.3 * recency_weights + 0.01`, normalized. A probability combination rule would add a third factor: `w_final = encoding_strength * probability^alpha`, where alpha controls probability influence.

**Research Evidence**:

M4-RSCH-03: REJECTED. All probability strategies tested (prob_weighted, prob_thresholded, prob_x_importance, prob_floor_x_imp, prob_softmax) underperform uniform. The combination rule question is moot -- no combination helps. The research tested the exact interaction patterns this issue proposes.

**Implementation Detail**:

1. DO NOT IMPLEMENT. M4-RSCH-03 explicitly rejects probability-based centroid weighting.
2. Document the rejection: "HDBSCAN probabilities do not improve centroid quality because the probability distribution is nearly uniform (89.5% of events have prob > 0.01) and provides minimal discrimination between event contributions."
3. If future corpus data shows more varied probability distributions, re-run M4-RSCH-03.
4. The combination rule remains documented in the research memo for future reference.

##### Issue 4.3.3 Verify rescued and weak-cluster behavior

| Item | Detail |
| ---- | ------ |
| Goal | Ensure fringe or rescued points do not distort episode vectors disproportionately. |
| Read | Rescue output behavior in `episodic_hdbscan.py`; replay rescue scenarios from Milestone 3 and Milestone 4 research. |
| Change | Apply caps, floors, or rescue-specific treatment so centroid weighting remains stable for weak clusters and rescued members. |
| Core idea | Soft membership is useful only if it improves cluster representation instead of amplifying rescue artifacts. |
| Tests | Add weak-cluster and rescued-fringe cases with expected centroid influence bounds. |
| Success criteria | Rescued or weakly attached events can contribute without hijacking the episode vector. |

**Codebase Reality** (verified 2026-03-07):

`_rescue_noise()` (episodic_hdbscan.py L359-L436): rescued events get probability = their pre-rescue probability (from HDBSCAN output, typically low). Weak cluster events (from nearby noise grouping) get probability based on DBSCAN fallback (1.0 if clustered).

The rescue path assigns events to clusters with hardcoded thresholds: rescue distance 0.3 (L475-equiv), weak cluster 0.2 (L489-equiv). Rescued events are full cluster members -- their embeddings contribute equally to the centroid regardless of their rescue status or probability.

EpisodeCluster has no mechanism to distinguish rescued vs core members. CentroidCalculator treats all member events identically.

**Research Evidence**:

M4-RSCH-03: probability weighting rejected, which also covers rescue/fringe behavior. Uniform weighting means rescued events contribute equally to centroids, which is the same as the current behavior. The research found this is fine -- rescued events don't distort centroids because they were rescued based on proximity (distance < 0.3), meaning they're semantically similar to core members.

Section 7: production baseline had 71.5% noise; research pipeline reduced to 0.15% noise (2 events). Rescue is rare in the improved pipeline, limiting its centroid impact.

**Implementation Detail**:

1. NO CHANGE NEEDED for centroid weighting (M4-RSCH-03 validates uniform is best).
2. For observability: tag rescued events in EpisodeCluster.member_contexts or a rescue_status field so quality tracking can distinguish core vs rescued member quality.
3. If rescue frequency increases (more noise), revisit with rescue-specific centroid dampening.
4. Weak cluster events (prefix "weak-") already have separate cluster IDs, so their centroids are separate from main clusters.

##### Issue 4.3.4 Validate the value of probability weighting

| Item | Detail |
| ---- | ------ |
| Goal | Prove probability augmentation is worth shipping. |
| Read | Retrieval and representative-quality research outputs comparing probability-on vs probability-off strategies. |
| Change | Benchmark probability-weighted centroids against the approved non-probability baseline. |
| Core idea | Existing HDBSCAN probabilities are useful only if they improve episode representation measurably. |
| Tests | Add regression fixtures for the approved probability strategy or intentionally omit production implementation if the research is negative. |
| Success criteria | Probability weighting is either validated and approved or explicitly rejected with documented rationale. |

**Codebase Reality** (verified 2026-03-07):

No probability weighting exists in CentroidCalculator. The current system uses uniform/importance/recency/hybrid strategies that ignore HDBSCAN probabilities entirely.

**Research Evidence**:

M4-RSCH-03: EXPLICITLY REJECTED. Uniform MRR=0.8943 > best probability strategy (prob_floor_x_imp MRR=0.8813). All 6 probability strategies tested underperform uniform. Zero contamination risk from rejection -- the current non-probability path is already the better path.

Research POC-02 obligation met: "Probabilities add variance without retrieval benefit."

**Implementation Detail**:

1. REJECTED -- no production implementation.
2. Document rejection in the M4 decision memo: "HDBSCAN probability weighting rejected per M4-RSCH-03. Uniform centroid contribution is optimal. Probability data remains available on HDBSCANClusteringResult for observability and diagnostics but is not used for centroid computation."
3. Remove placeholder in CentroidableEvent for `hdbscan_probability` (from Issue 4.1.0) if it was added.
4. This closes Epic 4.3 with a documented null result. The epic produced knowledge (probability doesn't help) which is valuable for preventing future re-investigation.

### Epic 4.4: EpisodicCoherenceScore

**Discovery Reference**: Sections 24.5 and 24.6
**Repo Status**: OPEN

#### Epic 4.4 Verified Current State

- `ClusterQualityTracker` still uses silhouette + grounding + correction + singleton.
- No episodic coherence family of metrics exists.
- Grounding/correction signals remain inactive in practice.
- The current quality surface still centers batch-level metrics rather than per-episode coherence diagnostics.

#### Epic 4.4 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 4.4.1 define coherence dimensions | OPEN | Add narrative, social, spatial, temporal, affective, and identity coherence metrics with explicit formulas. |
| 4.4.2 compute per-episode and batch coherence | OPEN | Produce cluster-level coherence and batch aggregates rather than one opaque score. |
| 4.4.3 integrate with quality tracker | OPEN | Replace or augment the current composite formula and clarify relation to silhouette. |
| 4.4.4 keep dormant channels honest | OPEN | Keep grounding/correction semantics explicit until those channels are truly live. |
| 4.4.5 validate tuning implications | OPEN | Re-check quality thresholds and any adaptive loop use after coherence is added. |

#### Epic 4.4 Issue Execution Checklist

##### Issue 4.4.1 Define the coherence dimensions

| Item | Detail |
| ---- | ------ |
| Goal | Define a real EpisodicCoherenceScore with explicit per-dimension formulas rather than loose narrative language. |
| Read | Discovery Sections 24.5 and 24.6; temp design Enhanced Quality Assessment; EventAdapter signal surface after Milestones 3 and 4.6. |
| Change | Specify formulas for narrative, social, spatial, temporal, affective, and identity coherence, including missing-signal handling. |
| Core idea | Quality should measure whether a cluster is internally coherent in the same dimensions used to form and represent it. |
| Tests | Add formula tests for each coherence dimension plus mixed-signal edge cases. |
| Success criteria | Every coherence dimension has documented math, bounded outputs, and explicit sparse-data behavior. |

**Codebase Reality** (verified 2026-03-07):

`ClusterQualityMetrics` (cluster_quality.py L58-L155) has no coherence fields. The composite formula (L108-L130) is: `0.40 * silhouette + 0.30 * grounding + 0.20 * (1-correction) + 0.10 * (1-singleton)`. Grounding is always 0.0, correction is always 0.0, so the formula gives a permanent +0.20 bonus from (1-correction) and 0.0 from grounding -- effectively `0.40 * silhouette + 0.20 + 0.10 * (1-singleton)`.

No coherence metrics exist anywhere in the codebase. No narrative, social, spatial, temporal, affective, or identity coherence computation.

`ObservationContext` (observation_context.py L30-L150) carries the raw signals needed for coherence: narrative_thread_id (via source event), social_context (L115), location_name (L107), sentiment_score (L72), affect_valence (L74), affect_arousal (L75). These are per-member-event contexts stored on `EpisodeCluster.member_contexts`.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.6 (M4-RSCH-04): equal_weight coherence (mean of 5 sub-dimensions) achieves rho=0.4556 post-correction vs silhouette mean=-0.0329 (broken). Coherence is stable across correction; silhouette breaks because thread-purity correction invalidates per-sequence distance matrices.

Key dimensions post-correction: social (0.3920), narrative (0.3386), spatial (0.1732). Temporal and affective contribute less.

**Implementation Detail**:

1. Create `k0/modules/consolidation/algorithms/episodic_coherence.py` with `EpisodicCoherenceScore` class.
2. Five coherence dimensions (each outputs [0, 1]):
   - Narrative: fraction of events sharing the dominant narrative_thread_id
   - Social: fraction sharing dominant social_context
   - Spatial: fraction sharing dominant location (geohash_6 or location_name)
   - Temporal: 1 - normalized_temporal_spread (tighter = more coherent)
   - Affective: 1 - stddev(affect_valence) / max_range (similar affect = more coherent)
3. Composite: equal-weight mean of populated dimensions.
4. Missing-signal fallback: if a dimension has no data (e.g., no narrative_thread_id for any member), contribute 0.5 (uncertain) and redistribute weight.
5. Input: List[ObservationContext] from EpisodeCluster.member_contexts.
6. Tests: single-thread cluster (narrative=1.0), mixed-thread (narrative < 1.0), no-thread (narrative=0.5 fallback).

##### Issue 4.4.2 Compute per-episode and batch coherence

| Item | Detail |
| ---- | ------ |
| Goal | Move from one batch-level heuristic toward episode-level coherence diagnostics aggregated at batch level. |
| Read | `cluster_quality.py`; `EpisodeCluster` surface; `r2_episodic_integrator.py` quality handoff. |
| Change | Compute coherence per cluster first, then aggregate into batch-level outputs with observability for per-dimension distributions. |
| Core idea | Good and bad clusters can coexist in one batch. The quality system should expose that instead of flattening everything immediately. |
| Tests | Add scenarios with mixed-quality clusters where the batch average alone would hide a bad cluster. |
| Success criteria | The system exposes both per-cluster coherence and batch summaries clearly enough for tuning and audit. |

**Codebase Reality** (verified 2026-03-07):

Current quality is batch-level only. `ClusterQualityTracker.compute_from_r2_output()` (L242-L276) takes batch-level inputs (batch_silhouette_score, cluster_count, noise_count) and produces one ClusterQualityMetrics per batch. No per-cluster quality metrics exist.

`_track_quality_and_adapt()` in r2_episodic_integrator.py (L1597, ~120 lines) calls compute_from_r2_output() once per batch, gets one composite score, and feeds it to adjusters.

EpisodeCluster has `cohesion_score` (L110) which is per-cluster variance-based (from CentroidCalculator.compute_variance()), but this is a geometric metric, not a semantic coherence measure.

**Research Evidence**:

M4-RSCH-04: equal_weight coherence computed per-cluster, then aggregated. Post-correction rho=0.4556 for the aggregate. Per-cluster coherence reveals that mixed-quality batches exist -- some clusters are highly coherent while others are contaminated. Batch-level silhouette hides this variance.

**Implementation Detail**:

1. Compute EpisodicCoherenceScore per EpisodeCluster (from member_contexts).
2. Store per-cluster coherence on EpisodeCluster as `coherence_score: float` and `coherence_dimensions: Dict[str, float]`.
3. Aggregate to batch level: mean, min, max, stddev of per-cluster coherence scores.
4. BatchCoherenceSummary: `{mean_coherence, min_coherence, max_coherence, std_coherence, worst_cluster_id, per_dimension_means}`.
5. Feed batch coherence into quality tracker alongside existing silhouette.
6. Observability: log per-cluster coherence dimensions for audit and debugging.

##### Issue 4.4.3 Integrate with the quality tracker

| Item | Detail |
| ---- | ------ |
| Goal | Replace or augment the current quality tracker with coherence-aware metrics. |
| Read | `cluster_quality.py`; `r2_episodic_integrator.py` `_track_quality_and_adapt()`; adjuster expectations after Milestone 2. |
| Change | Decide whether coherence replaces silhouette as the primary quality driver, coexists beside it, or feeds a new composite. |
| Core idea | Milestone 4 should make the quality loop more truthful, not simply add another unused metric. |
| Tests | Add end-to-end tests for coherence-aware quality computation and any revised adaptation inputs. |
| Success criteria | Quality tracking and downstream consumers use coherence intentionally and do not keep the old silhouette-centric semantics by accident. |

**Codebase Reality** (verified 2026-03-07):

`ClusterQualityTracker.compute_from_r2_output()` (L242-L276): creates ClusterQualityMetrics, calls compute_composite() which applies the fixed formula (0.40*silhouette + 0.30*grounding + 0.20*(1-correction) + 0.10*(1-singleton)).

`_track_quality_and_adapt()` (r2_episodic_integrator.py L1597): passes metrics.silhouette_score to EpsAdjuster and metrics.singleton_rate to both adjusters. The composite_quality score is computed but only used for quality tracking and alerts, not directly by adjusters.

Weight constants are module-level in cluster_quality.py (L44-L47): WEIGHT_SILHOUETTE=0.40, WEIGHT_GROUNDING=0.30, WEIGHT_CORRECTION=0.20, WEIGHT_SINGLETON=0.10.

**Research Evidence**:

M4-RSCH-04: silhouette breaks post-correction (mean=-0.0329). Coherence is stable (rho=0.4556). The recommendation is to use coherence AS the primary quality metric, with silhouette as a secondary geometric diagnostic. The 50% phantom weight (grounding=0 + correction=0) should be replaced with real signal.

**Implementation Detail**:

1. Replace composite formula: `0.50 * coherence + 0.30 * normalized_silhouette + 0.10 * (1-singleton) + 0.10 * reserved_for_future`.
2. OR: Drop silhouette from composite entirely and use `0.60 * coherence + 0.20 * (1-singleton) + 0.20 * reserved`.
3. Remove phantom grounding and correction weights (they are always 0.0/1.0).
4. Keep ClusterQualityMetrics fields for grounding/correction but mark them as dormant (explicit is_active flag or documentation).
5. Adjusters: see Issue 4.4.5 -- must be re-validated with new metric distribution in the SAME cycle.

##### Issue 4.4.4 Keep dormant channels honest

| Item | Detail |
| ---- | ------ |
| Goal | Prevent coherence and quality outputs from pretending external grounding or correction closure that still does not exist. |
| Read | Current `ClusterQualityMetrics` fields and any documentation for grounding/correction behavior. |
| Change | Mark which metrics are intrinsic cluster-quality signals and which remain external feedback channels that may be absent for long periods. |
| Core idea | The quality layer must say exactly what it knows and what it does not know. |
| Tests | Add tests and documentation checks for absent feedback channels, zero-count channels, and partial-signal batches. |
| Success criteria | Quality outputs clearly distinguish cluster-internal coherence from unavailable external feedback. |

**Codebase Reality** (verified 2026-03-07):

ClusterQualityMetrics (L58-L155) has fields that mix intrinsic and extrinsic signals without distinction:

- Intrinsic (cluster-internal): `silhouette_score`, `singleton_rate`, `total_clusters`, `singleton_clusters`
- Extrinsic (external feedback, currently dormant): `grounding_rate`, `correction_rate`, `grounded_clusters`, `corrected_clusters`
- Meta: `space_id`, `cycle_id`, `computed_at`, `composite_quality`

The `is_acceptable` property (L155) checks `composite_quality >= 0.50`, but composite_quality gets a permanent +0.20 boost from `(1 - correction_rate)` where correction_rate is always 0.0. This means "acceptable" quality is easier to reach than it should be.

**Research Evidence**:

M4-RSCH-04: coherence is intrinsic (computed from cluster member signals). Silhouette is intrinsic (computed from distance matrix). Grounding and correction are extrinsic (require human or downstream feedback loops that do not exist). The research validates that intrinsic metrics alone (coherence + silhouette) provide meaningful quality assessment without phantom extrinsic signals.

**Implementation Detail**:

1. Add an `is_dormant` flag or separate intrinsic vs extrinsic metric groups in ClusterQualityMetrics.
2. Mark grounding_rate and correction_rate as dormant with explicit documentation: "These fields require external feedback loops (human review, downstream correction) that are not yet operational."
3. Composite formula must NOT give credit for absent extrinsic signals (no more +0.20 from 1-correction).
4. Add a `signal_availability` dict to metrics: `{"coherence": True, "silhouette": True, "grounding": False, "correction": False}`.
5. Quality alerts must distinguish "low quality because cluster is bad" from "low quality because signals are missing."

##### Issue 4.4.5 Validate tuning implications (co-validation with adjusters)

| Item | Detail |
| ---- | ------ |
| Goal | Re-check thresholds and adaptation policies after coherence replaces part of the old quality loop. This is a co-validation, not a follow-up — adjuster behavior must be validated alongside the new formula, not after. |
| Read | Approved coherence formula; `eps_adjuster.py` (adjusts eps using silhouette, avg cluster size, singleton rate; bounds [0.15, 0.40]); `min_samples_adjuster.py` (adjusts min_samples using singleton rate; bounds [2, 5]); `r2_episodic_integrator.py` `_track_quality_and_adapt()` which feeds `metrics.silhouette_score` and `metrics.singleton_rate` into both adjusters. |
| Change | Revisit any thresholds, acceptability cutoffs, or alert rules that previously assumed silhouette-dominant quality semantics. CRITICAL: The current composite formula gives a permanent `+0.20` bonus from `(1 - correction_rate)` because correction is always 0. The adjusters consume `silhouette_score` and `singleton_rate` directly — if coherence replaces or augments silhouette, the adjuster input distribution changes and their thresholds (e.g., avg_cluster_size > 10, singleton_rate > 0.20) may need recalibration. This must happen in the SAME implementation cycle as the formula change, not as a follow-up. |
| Core idea | A more truthful metric changes the distribution of "good" and "bad" batches. Tuning must move with it. Grounding (0.30 weight) and correction (0.20 weight) together account for 50% of the composite formula and are always zero/one respectively — replacing them changes numerical behavior dramatically. |
| Tests | Add repeated-cycle scenarios to ensure new thresholds do not create unstable or noisy adaptation. Include adjuster-specific tests that prove eps and min_samples adjustment remain stable under the new quality metric distribution. |
| Success criteria | Quality alerts and adaptation logic behave predictably with the new coherence-aware metric surface. Adjusters are re-validated, not assumed stable. |

**Codebase Reality** (verified 2026-03-07):

`EpsAdjuster.adjust()` (eps_adjuster.py L170-L308) reads: `silhouette_score`, `avg_cluster_size`, `singleton_rate`, `total_clusters_formed`. Decision logic:

- Cold start skip: total_clusters_formed < 100
- Quality acceptable: silhouette >= 0.5 AND avg_cluster_size <= 10
- Decrease eps: avg_cluster_size > 10.0
- Increase eps: singleton_rate > 0.20
- Bounds: [0.15, 0.40], momentum=0.9

`MinSamplesAdjuster.adjust()` (min_samples_adjuster.py L150-L233) reads: `singleton_rate`.

- Increase min_samples: singleton_rate > 0.20
- Decrease min_samples: singleton_rate < 0.05
- Bounds: [2, 5]

Both adjusters consume `silhouette_score` and `singleton_rate` from ClusterQualityMetrics. If coherence replaces silhouette in the composite formula, EpsAdjuster's `silhouette >= 0.5` threshold needs recalibration because the input distribution changes.

Current composite gives +0.20 phantom bonus from (1-correction). Removing this drops composite scores by ~0.20, potentially triggering more frequent eps adjustments.

**Research Evidence**:

M4-RSCH-04: coherence rho=0.4556 post-correction, silhouette mean=-0.0329. The numerical distribution of coherence scores will differ from silhouette scores. Adjuster thresholds calibrated for silhouette distribution may not be appropriate for coherence distribution. POC-08 (M2 research): adaptive loop is stable with 0 oscillation in 10 batches -- but this was tested under the old quality formula.

**Implementation Detail**:

1. Replace EpsAdjuster's `silhouette_score >= silhouette_target(0.5)` with either `coherence_score >= coherence_target` or `composite_quality >= composite_target` (using the new formula without phantom weights).
2. Calibrate new thresholds by computing coherence distribution on the replay corpus (246 clusters).
3. MinSamplesAdjuster uses only singleton_rate -- unaffected by coherence change.
4. Run adjuster stability test: simulate 10+ batch cycles with new quality formula, verify no oscillation.
5. Update cold_start_threshold if coherence requires more batches to stabilize.
6. Tests: adjuster behavior under new quality distribution, phantom-free composite, edge cases at threshold boundaries.

### Epic 4.5: Vectorized Distance Matrix

**Discovery Reference**: Sections 17.4.3 and 20.9
**Repo Status**: OPEN

#### Epic 4.5 Verified Current State

- `CompositeDistance.build_distance_matrix()` still uses nested Python loops.
- No `cdist` or equivalent vectorized path exists.
- The current repository does not declare `scipy` in the dependency surface reviewed for this task, so vectorization must include an explicit dependency decision.

#### Epic 4.5 Complexity Warning: 6D Vectorization

Milestone 3 changes the distance formula from 2D (semantic + linear temporal) to 6D (semantic, temporal,
spatial, social, affective, narrative) with per-dimension missing-signal masks, hard gates, weight redistribution,
and neutral fallbacks. Vectorizing the M3 formula is significantly harder than vectorizing the current 2D formula:

- Each dimension needs its own vectorized path (cosine, log-temporal, categorical match, set overlap, etc.).
- Missing-signal masks must be carried as boolean matrices and applied per-dimension before weight normalization.
- Hard gates (e.g., temporal `inf` cutoff) must be implemented as masked array operations, not scalar `if` branches.
- Weight redistribution under sparse signals means the weight matrix is event-pair-specific, not global.

This complexity must be accounted for in Issue 4.5.3 (preserve semantics) and Issue 4.5.5 (benchmark).
Vectorization research (M4-RSCH-06) should include a feasibility assessment of vectorizing the full 6D formula
rather than assuming the 2D vectorization approach scales linearly.

#### Epic 4.5 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 4.5.1 vectorize semantic distance path | OPEN | Replace per-pair Python looping with a vectorized matrix path. |
| 4.5.2 vectorize temporal distance path | OPEN | Broadcast timestamps instead of computing time gaps pairwise in Python. |
| 4.5.3 preserve inf / hard-cutoff behavior | OPEN | Keep temporal hard-limit and missing-signal semantics stable under vectorization. |
| 4.5.4 choose dependency strategy | OPEN | Decide between pure NumPy broadcasting and deliberately adding `scipy`. |
| 4.5.5 benchmark and test | OPEN | Add parity, latency, and memory regression coverage. |

#### Epic 4.5 Issue Execution Checklist

##### Issue 4.5.1 Vectorize the semantic distance path

| Item | Detail |
| ---- | ------ |
| Goal | Remove Python-level pairwise iteration from semantic distance computation. |
| Read | `composite_distance.py` `build_distance_matrix()` and any helper math; discovery Section 20.9. |
| Change | Replace the pairwise semantic loop with vectorized cosine-distance computation using either normalized matrix multiplication or a chosen library path. |
| Core idea | Matrix construction is an algorithmic hotspot and should not remain Python-loop bound once Milestone 3 increases dimensional complexity. |
| Tests | Add parity tests comparing scalar and vectorized semantic submatrices on curated event sets. |
| Success criteria | Semantic pairwise distances match the scalar implementation within tight tolerance and materially reduce runtime on representative batch sizes. |

**Codebase Reality** (verified 2026-03-07):

`build_distance_matrix()` (composite_distance.py L270-L311): Pre-extracts embeddings and timestamps into Python lists (L282-L292), then nested loop:

```
for i in range(n):
    for j in range(i + 1, n):
        dist = self.compute_from_arrays(embeddings[i], embeddings[j], ...)
```

`compute_from_arrays()` (L230-L255): calls `_cosine_distance_arrays()` which normalizes both vectors and computes `1 - dot(a, b)`. Each call creates 2 numpy arrays from Python lists, normalizes, dots. The per-pair overhead is dominated by list-to-array conversion.

No scipy import. No cdist call. NumPy is used only for single-pair operations within the scalar loop.

Semantic cosine distance vectorization: stack all embeddings into an (N, 768) matrix, L2-normalize rows, compute `1 - (M @ M.T)` for the full NxN distance matrix in one operation.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.8 (M4-RSCH-06): 70.61x speedup for full vectorization. Semantic distance is the easiest dimension to vectorize (matrix multiply). 4/6 M3 dimensions are vectorizable (semantic, temporal, affective, spatial). Parity FAILS on narrative (fuzzy UltraBERT matching) and social (set overlap).

Current corpus: max sequence N=100, total runtime 2.5 seconds scalar. Vectorization benefit is marginal for N<=100 but significant for N>200.

**Implementation Detail**:

1. M4-RSCH-06 DEFERS vectorization (scalar adequate for N<=100).
2. If implemented anyway: stack embeddings into (N, 768) ndarray, L2-normalize via `embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)`, compute `cosine_matrix = 1 - (normalized @ normalized.T)`.
3. Handle zero vectors: pre-mask rows with zero norm, assign 1.0 (orthogonal) for those pairs.
4. Parity test: compare vectorized NxN cosine matrix against scalar pairwise computation, tolerance 1e-6.
5. No scipy dependency needed for semantic-only vectorization (pure NumPy).

##### Issue 4.5.2 Vectorize the temporal and gating path

| Item | Detail |
| ---- | ------ |
| Goal | Broadcast temporal computations instead of recomputing pairwise gaps in Python. |
| Read | `composite_distance.py` temporal-distance logic after Milestone 3; discovery Section 20.9 proposals. |
| Change | Implement timestamp-difference broadcasting, temporal transforms, and any hard-gap masking using vectorized NumPy operations. |
| Core idea | Temporal logic is part of the same matrix and should benefit from the same vectorization discipline. |
| Tests | Add parity tests for near-threshold, over-threshold, degraded-timestamp, and masked pair cases. |
| Success criteria | Vectorized temporal distance reproduces the scalar path exactly for supported cases, including hard gates and degraded paths. |

**Codebase Reality** (verified 2026-03-07):

`_normalized_time_distance()` (composite_distance.py L349-L361): `min(1.0, abs(t1-t2) / max_gap_ms)` (linear). After M3 Epic 3.2, this becomes logarithmic. The hard cutoff is in `compute()` (L199): `if time_diff_ms > max_temporal_gap_ms: return float("inf")`.

Temporal vectorization: extract timestamps into (N,) array, compute `abs(ts[:, None] - ts[None, :])` for NxN time-diff matrix, apply log or linear transform, apply inf mask where diff > max_gap.

This is straightforward broadcasting -- no complex per-pair logic. The hard cutoff becomes `np.where(time_diff > max_gap, np.inf, normalized_dist)`.

**Research Evidence**:

M4-RSCH-06: temporal broadcasting is one of the 4 easily vectorizable dimensions. Parity passes for temporal (failures are in narrative dimension only). The 70.61x speedup includes temporal vectorization.

**Implementation Detail**:

1. DEFERRED per M4-RSCH-06 (scalar adequate for N<=100).
2. If implemented: `time_diffs = np.abs(ts[:, None] - ts[None, :])`, apply transform (linear or log), apply inf mask.
3. Handle M3 logarithmic transform: `np.log1p(time_diffs / scale)` broadcast.
4. Parity test: compare against scalar pairwise for near-threshold, over-threshold, and equal-timestamp cases.
5. The inf mask is the only tricky part -- must match scalar hard-cutoff exactly.

##### Issue 4.5.3 Preserve hard-cutoff and missing-signal semantics

| Item | Detail |
| ---- | ------ |
| Goal | Ensure vectorization does not silently change masking, `inf` assignment, or sparse-signal fallback behavior. |
| Read | Final Milestone 3 distance semantics; any scalar helper paths still used for edge behavior. |
| Change | Carry missing-signal masks, temporal hard-cutoff rules, and dimension-level neutralization into the vectorized path explicitly. |
| Core idea | Faster wrong math is still wrong. The vectorized path has to preserve the real contract. |
| Tests | Add mask-heavy and sparse-signal parity tests that would catch silent dense-array regressions. |
| Success criteria | All scalar edge semantics survive the vectorized implementation. |

**Codebase Reality** (verified 2026-03-07):

Scalar edge cases that must survive vectorization:

1. Hard cutoff: `time_diff > max_gap -> inf` (composite_distance.py L199)
2. Zero-vector fallback: `_cosine_distance_arrays` returns 1.0 for zero-norm vectors (L336)
3. Missing embedding: `build_distance_matrix` raises ValueError for missing embeddings (L286)
4. After M3: per-dimension missing-signal masks, weight redistribution, neutral fallbacks, categorical comparisons

The 6D M3 formula is significantly harder to vectorize than 2D because:

- Narrative distance uses UltraBERT fuzzy thread matching (string comparison, not numeric)
- Social distance uses Jaccard set overlap (set operations, not matrix operations)
- Missing-signal masks create per-pair-specific weight vectors

**Research Evidence**:

M4-RSCH-06: parity FAILS (max_err=0.329) due to narrative fuzzy matching. The scalar path uses UltraBERT fuzzy thread matching; the vectorized path used exact-match only, producing different distances. 4/6 dimensions vectorizable; narrative and social require scalar loops.

**Implementation Detail**:

1. DEFERRED per M4-RSCH-06.
2. If partially vectorized: vectorize semantic + temporal + affective + spatial (4 dimensions), keep narrative + social as scalar loops.
3. The mixed approach creates a "partially vectorized" matrix that is harder to maintain than pure scalar.
4. Recommendation: keep scalar until sequence sizes grow significantly (N > 200) or a new narrative distance function allows vectorization.
5. Parity harness: mandatory before any vectorization ships. Compare full NxN matrix, scalar vs vectorized, tolerance 1e-6 per element.

##### Issue 4.5.4 Choose the dependency strategy

| Item | Detail |
| ---- | ------ |
| Goal | Make the vectorization dependency choice explicit instead of assuming `scipy` exists. |
| Read | Reviewed dependency surface, current use of NumPy, and any existing `scipy` usage in non-production areas. |
| Change | Decide whether production vectorization remains NumPy-only or whether `scipy` is added intentionally with dependency, build, and test implications documented. |
| Core idea | Dependency choice is part of the architecture here, not an implementation footnote. |
| Tests | If `scipy` is added, add environment and dependency validation; if not, add tests proving the NumPy path is sufficient. |
| Success criteria | The plan and code clearly state which vectorization dependency model the repo supports and why. |

**Codebase Reality** (verified 2026-03-07):

Current dependencies (from pyproject.toml and requirements.txt): numpy is used throughout K0. scipy is NOT in the dependency surface. No `from scipy.spatial.distance import cdist` or similar import exists in any K0 production code.

NumPy broadcasting is sufficient for: cosine distance (matrix multiply), temporal distance (broadcasting), affective distance (element-wise ops), spatial distance (categorical match).

scipy.spatial.distance.cdist would add: optimized C-level pairwise distance for common metrics, but adds a ~30MB dependency and requires binary compatibility.

**Research Evidence**:

M4-RSCH-06: vectorization benchmark used pure NumPy broadcasting. No scipy required. 70.61x speedup achieved without scipy. The research validates that NumPy-only is sufficient.

**Implementation Detail**:

1. Decision: NumPy-only. Do NOT add scipy dependency.
2. Rationale: NumPy broadcasting achieves sufficient speedup for vectorizable dimensions. scipy adds dependency weight without proportional benefit for the 4 vectorizable dimensions. The 2 non-vectorizable dimensions (narrative, social) cannot use cdist anyway.
3. Document in pyproject.toml or architecture docs: "K0 vectorization uses NumPy broadcasting only. scipy is explicitly excluded."
4. If future profiling shows NumPy bottleneck at N > 500: revisit scipy decision with measured evidence.

##### Issue 4.5.5 Benchmark and test

| Item | Detail |
| ---- | ------ |
| Goal | Prove vectorization improves runtime without unacceptable memory blowups or semantic drift. |
| Read | Discovery performance notes; research benchmark outputs; final vectorized implementation. |
| Change | Benchmark scalar vs vectorized implementations across representative batch sizes and memory envelopes, then preserve the chosen implementation with parity tests. |
| Core idea | This work is justified by measured gains, not by the existence of vectorized APIs. |
| Tests | Add parity benchmarks, representative-size performance benchmarks, and regression guards for memory growth. |
| Success criteria | The approved vectorized path is demonstrably faster and semantically equivalent on representative workloads. |

**Codebase Reality** (verified 2026-03-07):

Current scalar performance: 2.5 seconds for full corpus (1360 events, 32 sequences, max N=100). This is measured in the research pipeline, not production. Production batch sizes are typically smaller (P03 processes recent events, not the full corpus).

No existing benchmark or parity test infrastructure in the production test suite. test_r2_integration.py has `test_distance_matrix_for_clustering` which checks matrix properties (symmetric, non-negative, diagonal=0) but not performance.

**Research Evidence**:

M4-RSCH-06: 70.61x speedup (vectorized). Memory: 7x overhead (7 NxN matrices vs 1), 547 KB vs 78 KB for N=100 -- acceptable. Parity: FAILS (narrative fuzzy matching). Verdict: scalar_adequate for current workloads.

Small sequences: 8x speedup. Medium: 27x. Large: 70x. The speedup scales with N^2, so benefit increases with batch size.

**Implementation Detail**:

1. DEFERRED per M4-RSCH-06 research verdict.
2. When implementing: add parity harness that runs vectorized and scalar on identical inputs, asserts max_err < 1e-6 per element.
3. Add performance benchmark: measure scalar vs vectorized on N=10, 50, 100, 200, 500 event batches.
4. Add memory regression test: verify matrix memory stays within bounds for expected batch sizes.
5. Gate: vectorization only ships when parity passes (narrative dimension must be resolved).
6. Current action: document the deferral decision and the conditions under which vectorization becomes necessary (N > 200 regularly, or latency SLA requires sub-second matrix generation).

### Epic 4.6: Narrative, Cognitive, And Support-Signal Encoding

**Discovery Reference**: temp design narrative/cognitive/affective support channels
**Repo Status**: OPEN

#### Epic 4.6 Verified Current State

- The current plan explicitly names only part of the encoding surface.
- Several narrative, cognitive, and support signals are required for full channel completion but are not yet represented as planned work.
- Current R2 aggregation uses only a narrow subset of those fields in summary and context aggregation, not as first-class encoding or coherence inputs.

#### Epic 4.6 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 4.6.1 encode `narrative_arc_position` and `narrative_is_goal_event` | OPEN | Decide how they affect episode summaries, confidence, and coherence scoring. |
| 4.6.2 encode `goal_context` and `intent_type` explicitly | OPEN | Ensure goal and intent signals are not only distance inputs but also episode-level metadata and coherence dimensions. |
| 4.6.3 encode `novelty`, `memory_tier`, and `source_type` | OPEN | Use them in encoding strength, boundary semantics, rescue priority, and episode characterization. Additionally, `memory_tier` must serve a **pairwise distance anchoring** role (not just encoding): landmark events attract related events (`d *= 0.5` when narrative or spatial context matches) and repel unrelated events (`d *= 1.3`). This dual role (distance modifier + encoding weight) must be coordinated with Epic 3.1 distance infrastructure. |
| 4.6.4 encode `identity_domains_json` | OPEN | Define identity-domain coherence and summary contribution rules. |
| 4.6.5 encode `emotions_json`, `entity_salience_json`, and `salience_band` | OPEN | Use them for affective coherence, emotional-peak centroiding, and support-signal summaries. |

#### Epic 4.6 Issue Execution Checklist

##### Issue 4.6.1 Encode `narrative_arc_position` and `narrative_is_goal_event`

| Item | Detail |
| ---- | ------ |
| Goal | Give narrative arc and goal-event status an explicit role in episode encoding and coherence. |
| Read | temp design narrative channel; discovery notes on available narrative signals; `EventAdapter` surface. |
| Change | Decide whether these fields affect summary generation, confidence, narrative centroid selection, coherence scoring, or some combination with one primary home per signal. |
| Core idea | Narrative support signals should shape episode representation intentionally, not appear only as passive metadata. |
| Tests | Add scenarios for exposition vs climax vs resolution episodes and goal-event dominated clusters. |
| Success criteria | Narrative arc signals have a documented and test-covered role in Milestone 4 outputs. |

**Codebase Reality** (verified 2026-03-07):

`narrative_arc_position` is on EventAdapter (L209): returns `self.event.narrative_arc_position or None`. P03EventState (L209): str = "". Values: BEGINNING/MIDDLE/END/CLIMAX.

`narrative_is_goal_event` does NOT exist on P03EventState or EventAdapter. No field by this name in event_state.py. The closest field is `goal_context` (P03EventState L209, str = "").

ObservationContext does NOT carry narrative_arc_position. It has no narrative-specific fields beyond what the source event provides.

Current usage: narrative_arc_position is exposed on EventAdapter but NOT consumed by any algorithm. It is available for M3 narrative distance (Epic 3.1.4) but the algorithm does not read it yet.

**Research Evidence**:

M4-RSCH-07: ALL 9 cognitive/narrative signals tested (including narrative_arc_position) are SUMMARY-ONLY. They do not improve centroid encoding quality (baseline MRR=0.9975). The research recommends keeping these signals in episode metadata and summaries, not in encoding or distance math.

M4-RSCH-04: narrative coherence is one of the 5 coherence dimensions (rho post-correction: narrative=0.3386). Narrative arc position could contribute to narrative coherence assessment (clusters with consistent arc progression are more coherent).

**Implementation Detail**:

1. Primary role: SUMMARY and COHERENCE, not encoding.
2. Add narrative_arc_position to ObservationContext so it flows into episode metadata.
3. For coherence (Issue 4.4.1): compute arc consistency -- clusters where events progress BEGINNING -> MIDDLE -> END/CLIMAX are more narratively coherent.
4. For summary: include dominant arc position in episode summary metadata.
5. `narrative_is_goal_event`: derive from `goal_context != ""` rather than adding a new field.
6. Tests: clusters with consistent vs mixed arc positions, clusters with goal events.

##### Issue 4.6.2 Encode `goal_context` and `intent_type` explicitly

| Item | Detail |
| ---- | ------ |
| Goal | Promote goal and intent signals from distance-only support into episode-level meaning. |
| Read | Existing narrative-thread and episode-summary logic; temp design support-signal notes. |
| Change | Define how goal context and intent contribute to episode metadata, confidence, coherence, and optional narrative centroids. |
| Core idea | If goal and intent help form episodes, they should also help describe and audit them. |
| Tests | Add same-thread/different-goal and same-goal/different-intent clusters plus summary-field assertions. |
| Success criteria | Goal and intent are represented coherently in both encoding and episode metadata surfaces. |

**Codebase Reality** (verified 2026-03-07):

`goal_context` (P03EventState L209, str = ""): NOT on EventAdapter. Contains free-text goal description from MW v2.

`intent_type` (P03EventState L208, str = ""): NOT on EventAdapter. Listed among 7 zombie/deprecated columns. `intent_ultrabert` (P03EventState L194, str = "") is the replacement from P02 UltraBERT. `intent_ultrabert` is NOT on EventAdapter either.

ObservationContext carries `intent_ultrabert` (L83) and `intent_confidence` (L84) but NOT `goal_context` or `intent_type`.

Current usage: none of these fields are consumed by any clustering, distance, or quality algorithm. They are passive P03EventState fields.

**Research Evidence**:

M4-RSCH-07: goal_context and intent signals are SUMMARY-ONLY -- they do not improve centroid encoding. M4-RSCH-04: coherence includes no intent or goal dimension explicitly, but intent consistency within a cluster could contribute to narrative coherence.

**Implementation Detail**:

1. Primary role: SUMMARY metadata and episode characterization.
2. Add goal_context to ObservationContext so it flows into episode-level metadata.
3. For episode summary: aggregate goal contexts across cluster events (dominant goal, goal diversity).
4. Intent: use intent_ultrabert from ObservationContext for intent consistency metric (could augment narrative coherence).
5. Do NOT add intent_type (zombie column) to any new surface.
6. Tests: clusters with consistent vs mixed goals, clusters with intent shifts.

##### Issue 4.6.3 Encode `novelty`, `memory_tier`, and `source_type`

| Item | Detail |
| ---- | ------ |
| Goal | Decide how these support signals affect encoding strength, episode characterization, quality interpretation, **and pairwise distance anchoring**. |
| Read | temp design cognitive channel and global modifiers (memory tier anchoring); any existing event-state fields for novelty, source type, and memory tier; Epic 3.1 distance infrastructure for the anchoring hook point. |
| Change | (1) Map novelty, memory tier, and source type into encoding strength and/or episode metadata with explicit limits so they do not become catch-all modifiers everywhere. (2) Implement **memory-tier distance anchoring** as a global modifier applied after the 6D distance sum: if either event has `memory_tier == "landmark"`, check whether the pair shares `narrative_thread_id` or `place_id`; if related context matches, multiply `d(i,j) *= 0.5` (landmark attracts); if no context match, multiply `d(i,j) *= 1.3` (landmark repels unrelated events). The anchoring multipliers must be configurable. Coordinate with Epic 3.1 distance params model to register the anchoring hook. |
| Core idea | `memory_tier` has a dual role: it shapes encoding weight (how strongly an event contributes to the centroid) AND pairwise distance (how landmarks attract or repel neighbors). The target design treats these as separate mechanisms: encoding weight is per-event, distance anchoring is per-pair. Conflating them into encoding alone loses the clustering-level effect where landmarks create tight clusters of related events around them. |
| Tests | (1) Landmark + same narrative thread = distance reduced (attraction). (2) Landmark + no shared context = distance increased (repulsion). (3) No landmark events = anchoring modifier is identity (1.0). (4) Anchoring multipliers are configurable. (5) High-novelty vs low-novelty encoding scenarios. (6) Observation vs reflection source-type scenarios. |
| Success criteria | `memory_tier` has exactly two bounded jobs: encoding weight and distance anchoring. `novelty` and `source_type` each have one or two bounded jobs in the representation layer. Anchoring is a configurable post-sum modifier, not an ad-hoc hack inside a single dimension. |

**Codebase Reality** (verified 2026-03-07):

`novelty_score` (P03EventState L154, float = 0.0): NOT on EventAdapter. ObservationContext carries it (L92). Computed by P02 processing.

`memory_tier`: does NOT exist on P03EventState. Not in event_state.py. Not on EventAdapter. Not on ObservationContext. This field is a design-time concept from the temp_r2_design document, not yet materialized in the codebase.

`source_type`: does NOT exist on P03EventState. Not on EventAdapter. ObservationContext has related fields: `ingress_channel` (L98), `ingress_category` (L99), `ingress_source` (L100), but no `source_type` field.

For distance anchoring: composite_distance.py compute() returns a weighted sum. A post-sum anchoring modifier would multiply the final distance: `d_final = d_sum * anchoring_factor(event_i, event_j)`. This hook does not exist yet.

**Research Evidence**:

M4-RSCH-07: novelty tested as encoding weight modifier -- SUMMARY-ONLY (delta < 0.01 vs baseline MRR=0.9975). The research does not test memory_tier or source_type because they do not exist in the corpus.

Memory tier anchoring (landmark attraction/repulsion) is a design-time proposal from the discovery doc. No empirical validation exists. The mechanism (d *= 0.5 for related landmarks, d*= 1.3 for unrelated) is untested.

**Implementation Detail**:

1. `novelty_score`: SUMMARY-ONLY per M4-RSCH-07. Keep on ObservationContext for episode metadata. Surface on EventAdapter for coherence diagnostics.
2. `memory_tier`: DEFER. Does not exist on P03EventState. Requires K1 memory classification pipeline to populate. Cannot implement until the field exists and has non-trivial population. Create a placeholder architecture note for when K1 provides memory_tier.
3. `source_type`: DEFER. Map to ObservationContext's ingress fields (ingress_channel, ingress_source) which already exist. Define the mapping: ingress_channel -> source_type normalization rule.
4. Distance anchoring: DEFER until memory_tier exists and has empirical validation. The post-sum modifier hook can be designed now but not implemented without data.
5. Tests: novelty in summary, deferred placeholder tests for memory_tier and source_type.

##### Issue 4.6.4 Encode `identity_domains_json`

| Item | Detail |
| ---- | ------ |
| Goal | Make identity-domain structure visible in coherence and episode summaries. |
| Read | temp design cognitive channel; discovery notes on `identity_domains_json`; current summary and context aggregation helpers. |
| Change | Define identity-domain coherence, summary rollup, and any identity-driven encoding effects. |
| Core idea | Identity relevance is stronger when it is grounded in specific domains rather than a scalar alone. |
| Tests | Add multi-domain and dominant-domain scenarios, including mixed-role episodes. |
| Success criteria | Identity-domain information influences coherence or summary output in a deterministic and documented way. |

**Codebase Reality** (verified 2026-03-07):

`identity_domains_json` does NOT exist on P03EventState. Not in event_state.py. Not on EventAdapter. Not on ObservationContext. This is a design-time concept from the discovery document.

The closest existing field is `ner_entities_json` (P03EventState L172, str = "[]"): JSON array of NER-extracted entities with text and labels. EventAdapter wraps this (L183-L192) by parsing the JSON and extracting text fields.

`identity_relevance` also does not exist -- another design-time concept. No identity scoring or domain classification pipeline exists in K0/K1.

**Research Evidence**:

M4-RSCH-07: identity_domains tested as encoding weight modifier -- SUMMARY-ONLY (delta < 0.01). Even if the field existed, it would not improve centroid quality.

M4-RSCH-04: no identity coherence dimension was computed in the research (only narrative, social, spatial, temporal, affective). Identity coherence (do cluster events share identity domains?) would be a new dimension.

**Implementation Detail**:

1. DEFER. The field does not exist in the codebase. Cannot implement until K1 provides identity domain classification.
2. When available: add identity_domains_json to P03EventState and EventAdapter.
3. Identity coherence: fraction of cluster events sharing a dominant identity domain (similar pattern to social coherence).
4. Summary contribution: aggregate identity domains across cluster events for episode characterization.
5. No encoding role per M4-RSCH-07.
6. Placeholder: document the intended integration point for when K1 identity classification ships.

##### Issue 4.6.5 Encode `emotions_json`, `entity_salience_json`, and `salience_band`

| Item | Detail |
| ---- | ------ |
| Goal | Use support affect/salience signals for richer episode representation and emotional-peak selection. |
| Read | temp design affective support notes; current dominant-emotion aggregation and salience usage. |
| Change | Define how detailed emotion sets, entity-level salience, and salience bands contribute to affective coherence, emotional-peak centroid selection, and episode summaries. |
| Core idea | Support signals should refine the representation layer where they add explanatory value, not simply mirror fields already present. |
| Tests | Add emotional-peak selection cases, mixed-emotion clusters, and entity-salience-driven summary assertions. |
| Success criteria | Affective support signals are represented in encoding and summary outputs with clear scope and no opportunistic leakage. |

**Codebase Reality** (verified 2026-03-07):

`emotions_json` / `dominant_emotions_json`: ObservationContext has `dominant_emotions_json` (L77, Optional[str]). P03EventState has `emotions_json` (L135, str = "[]"). EventAdapter does NOT expose emotions_json.

`entity_salience_json`: does NOT exist on P03EventState or EventAdapter. The closest field is `salience_score` (P03EventState L140, float = 0.0) which is a scalar, not per-entity salience.

`salience_band`: P03EventState has it (L142, str = ""). ObservationContext carries it (L91). EventAdapter does NOT expose it.

Current usage in R2:

- `_build_episode_cluster()` (r2_episodic_integrator.py) aggregates `dominant_emotion` via majority vote from cluster events (L1260-L1280). This uses parsed `emotions_json` to find the most common emotion across events.
- EpisodeCluster has `dominant_emotion` (L95) and `dominant_sentiment` (L94) -- both are scalar aggregates.
- Emotional-peak centroid selection (Issue 4.2.2) would use affect_valence and affect_arousal, which are already on EventAdapter.

**Research Evidence**:

M4-RSCH-07: emotion_tags tested as encoding weight modifier -- SUMMARY-ONLY. entity_salience tested -- SUMMARY-ONLY. All signals: delta < 0.01 vs baseline MRR=0.9975.

M4-RSCH-02: emotional_peak centroid selection uses max |affect_valence| + affect_arousal. Found in 246/246 clusters (100%). This is the primary affective signal role: selecting the emotional-peak secondary centroid.

M4-RSCH-04: affective coherence is one of 5 dimensions. Post-correction contribution is lower than narrative and social.

**Implementation Detail**:

1. `emotions_json`: SUMMARY-ONLY. Keep in ObservationContext (dominant_emotions_json). Used by _build_episode_cluster() for dominant_emotion aggregation. No change needed.
2. `entity_salience_json`: DEFER. Does not exist on P03EventState. Requires MW v2 entity-level salience extraction.
3. `salience_band`: SUMMARY-ONLY. Already on ObservationContext. Surface on EventAdapter for coherence diagnostics if needed.
4. Emotional-peak centroid: use affect_valence + affect_arousal from EventAdapter (already available). This is the primary M4 role for affective signals.
5. Affective coherence (Issue 4.4.1): use stddev of affect_valence across cluster members from ObservationContext.
6. Tests: emotional-peak selection from cluster events, affective coherence computation, dominant emotion aggregation.

#### Milestone 4 Research Exit Gate

Milestone 4 research is complete only when all of the following are true.

| Gate | Requirement |
| ---- | ----------- |
| G1 | Encoding-strength, retrieval, coherence, storage, and vectorization research artifacts exist and are runnable |
| G2 | Single-centroid vs multi-centroid comparisons are generated on replayed or representative episode datasets |
| G3 | Coherence formulas and vectorized matrix parity are benchmarked with explicit pass/fail outcomes |
| G4 | Storage rehearsal identifies the approved persistence/query strategy for richer centroid sets |
| G5 | `results/m4_decision_memo.md` names the approved Milestone 4 production path and any rejected options |

#### Milestone 4 Exit Criteria

- Centroiding reflects the richer MW-v2 and HDBSCAN output surface.
- Quality assessment is no longer dependent on phantom product signals.
- Narrative, cognitive, and support-signal families are represented in episode encoding and coherence outputs.
- Distance-matrix generation is performant enough for larger sequence sizes.
- Multi-centroid work is either fully wired through storage/query consumers or explicitly deferred behind a documented schema boundary.
- `CentroidableEvent` protocol is extended, coordinated with M3 `EventLike`, and satisfied by EventAdapter.
- All encoding-strength terms and coherence dimensions implement the M4 fallback chain (primary -> secondary -> neutral) and handle missing signals safely.
- `R2StagedOutput` has a documented fate (revived, deleted, or reconciled) and code implements that decision.
- `EpisodicLayerWriter` is reconciled with multi-centroid storage or explicitly documented as single-centroid-only.
- Adaptive adjusters (`EpsAdjuster`, `MinSamplesAdjuster`) are re-validated under the new quality metric distribution.
- Existing centroid test surface is consciously managed (preserved, archived, or replaced) — not silently broken.

#### Milestone 4 Completion Verification

| Area | Verification Requirement |
| ---- | ------------------------ |
| Research | Milestone 4 research artifacts exist for encoding strength, retrieval comparison, coherence, vectorization, and storage rehearsal |
| Protocols | `CentroidableEvent` is enriched, coordinated with `EventLike`/`SplittableEvent`, and tested |
| Fallback safety | Every encoding term and coherence dimension handles missing signals without crash, zero-weight, or max-weight artifacts |
| Integration | `R2StagedOutput` fate is decided and implemented; `EpisodicLayerWriter` is reconciled; all three write surfaces handle multi-centroid or preserve compatibility |
| Adjusters | `EpsAdjuster` and `MinSamplesAdjuster` are re-validated under new quality metric distribution |
| Code | Approved centroid/coherence/vectorization changes are implemented without leaving legacy assumptions hidden in storage or query paths |
| Tests | Centroid, quality, vectorization, and episodic write/query tests cover the approved production path and backward compatibility; legacy test surface is consciously managed |
| Handoff | Milestone 5 starts from truthful episode representations and coherence outputs rather than from legacy single-centroid assumptions |

---

## MILESTONE 5: Hebbian & Adaptive Enhancements (P4)

**Milestone Status**: RESEARCH COMPLETE (2026-07-10)

### Milestone 5 Research Summary

All M5 research tracks have been executed. Findings from `poc/r2_phase_research/m5_rsch01_02_hebbian_boost.py`,
`poc/r2_phase_research/m5_rsch03_04_adaptive_weights.py`, and `R2_RESEARCH_FINAL.md` Sections 12.3-12.6:

| Research ID | Question | Verdict | Key Finding |
| ----------- | -------- | ------- | ----------- |
| M5-RSCH-01 | Hebbian co-occurrence contamination risk | **ADOPT** | +3 scenarios (5/8 to 8/8), zero contamination. Conservative params: scale=0.10, cap=0.05. |
| M5-RSCH-02 | Evidence threshold for Hebbian boost | **min_count=1** | All thresholds (1-20) achieve 8/8. Corpus dense enough that evidence thresholds dont discriminate. |
| M5-RSCH-03 | Context-adaptive weight shifts | **REJECTED** | No adaptive policy beats static 0.45/0.25/0.30. Uniform (1/3 each) scored 7/8 but Hebbian already achieves 8/8 with static. |
| M5-RSCH-04 | Multi-cycle stability | **STABLE** | score_std=0.0 across 5 cycles. Weight variance negligible (sem_std=0.009, temp_std=0.005, narr_std=0.012). |

**Proven Hebbian Boost Formula**:

```
affinity = max(edge.weight for all participant-pair co-occurrences)
  where edge.weight = 1.0 - exp(-0.1 * count)

boost = min(affinity * boost_scale, boost_cap)
d_hebbian = d_ensemble * (1.0 - boost)
```

**Production Parameters** (research-validated):

| Param | Value | Notes |
|-------|-------|-------|
| boost_scale | 0.10 | All scales >= 0.10 achieve 8/8 |
| boost_cap | 0.05 | Max 5% distance reduction |
| min_count | 1 | All thresholds equivalent |
| use_recency | False | Raw and decayed both 8/8; raw simpler |

**Co-occurrence Graph**: 27 edges from 5 family participants + locations. Top edges saturated at weight=1.0
(e.g., person_maya + loc:place_home = 548 co-occurrences).

**M5 Production Decisions**:

| Decision | Rationale |
|----------|-----------|
| ADOPT Hebbian co-occurrence boost | +3 scenarios (5/8 to 8/8), zero contamination, conservative params |
| KEEP static weights (no adaptive) | No context-adaptive rule beats 0.45/0.25/0.30 |
| Hebbian fallback = boost_factor=1.0 | Neutral state = no distance modification. Safe rollback. |
| DEFER RSCH-05/06/07 | Signals not in corpus. Cannot test until K1 populates them. |
| M5 exit gate G5 partially met | Hebbian works via participant co-occurrence without needing a separate st_cooccurrence table |

### Epic 5.1: Hebbian Distance Boost

**Discovery Reference**: Section 11.1 divergence R2-DIV-003 and roadmap Section 13
**Repo Status**: RESEARCH COMPLETE — ADOPT

| Issue | Status | Action |
| ----- | ------ | ------ |
| 5.1.1 define boost semantics | RESEARCH COMPLETE | Multiplicative: d_final = d_base *(1 - min(affinity* 0.10, 0.05)). Max 5% reduction. |
| 5.1.2 define evidence and decay policy | RESEARCH COMPLETE | min_count=1, raw co-occurrence (no recency decay needed). |
| 5.1.3 wire st_cooccurrence read path | RESEARCH COMPLETE | Preload entity pairs from st_kg_edges. Fallback: affinity=0, boost_factor=1.0. |
| 5.1.4 integrate with distance and rescue | RESEARCH COMPLETE | PAIRWISE DISTANCE ONLY. No rescue or matching modification. |
| 5.1.5 validate contamination risk | RESEARCH COMPLETE | Zero contamination across 8 scenarios. +3 improvements (5/8 to 8/8). |

### Epic 5.2: Context-Adaptive Weights

**Discovery Reference**: Sections 17.5.5 (SUPERSEDED) and 13.1; authoritative source is temp_r2_design.md Subsystem 3 (Neuromorphic Distance Model) and global modifiers section
**Repo Status**: RESEARCH COMPLETE — REJECTED

| Issue | Status | Action |
| ----- | ------ | ------ |
| 5.2.1 define adaptive weighting policy | REJECTED | No adaptive policy beats static 0.45/0.25/0.30. |
| 5.2.2 define learned-weight persistence model | DEFERRED | Key schema designed (dist_weight_ prefix) but unpopulated. |
| 5.2.3 integrate after 6D distance lands | DEFERRED | Weight-injection hook useful for experimentation but no production adaptive path. |
| 5.2.4 separate from parameter tuning | DEFERRED | Moot since adaptive weights rejected. |
| 5.2.5 validate stability and rollback | VERIFIED | score_std=0.0 across 5 cycles, but adaptive weights not being deployed. |

### Epic 5.3: Reliability And Provenance Gating

**Discovery Reference**: temp design reliability channel and global modifiers
**Repo Status**: DEFERRED — K1 signal data not populated in corpus

| Issue | Status | Action |
| ----- | ------ | ------ |
| 5.3.1 add source_reliability gating | DEFERRED | 0/1360 coverage. Cannot validate until K1 populates. |
| 5.3.2 add activity_type_confidence gating | DEFERRED | Homogeneous in corpus (mean=0.90). Insufficient variation. |
| 5.3.3 add intent_confidence gating | DEFERRED | No intent-driven distance modifier exists to gate. |
| 5.3.4 add k1_signal_version compatibility rules | DEFERRED | 0/1360 coverage. K1 versioned emission not built. |
| 5.3.5 add temporal_source provenance gating | DEFERRED | 0/1360 in corpus. |
| 5.3.6 propagate reliability into quality outputs | DEFERRED | Depends on 5.3.1-5.3.5 landing first. |

#### Milestone 5 Research Exit Gate — PASSED (2025-07-10)

All gates satisfied:

| Gate | Requirement | Status | Evidence |
| ---- | ----------- | ------ | -------- |
| G1 | Hebbian, adaptive-weight, reliability-gating, mixed-version, and stability research artifacts exist and are runnable | PASSED | `poc/r2_phase_research/m5_rsch01_02_hebbian_boost.py`, `m5_rsch03_04_adaptive_weights.py` |
| G2 | Replay comparisons exist for Hebbian-on/off, static-vs-adaptive weights, and reliability/provenance gating | PASSED | Hebbian on/off: 7/8 vs 8/8. Static vs adaptive: 7/8 vs 5/8. Reliability: 0/1360 coverage blocks gating. |
| G3 | Stability analysis identifies the approved safety rails for adaptive weights | PASSED (N/A) | Adaptive weights REJECTED. Static weights (0.45/0.25/0.30) proven stable (score_std=0.0 over 5 cycles). |
| G4 | Decision memo names the approved Milestone 5 production path and any rejected strategies | PASSED | ADOPT Hebbian (scale=0.10, cap=0.05). REJECT adaptive weights. DEFER reliability gating. See R2_RESEARCH_FINAL.md. |
| G5 | Research outputs are sufficient to justify either making `st_cooccurrence` real in R2 or removing the stale contract promise | PASSED | Co-occurrence implemented via participant entity pairs from st_kg_edges. Contract `read:st_cooccurrence` should be updated to reflect actual mechanism. |

#### Milestone 5 Exit Criteria — Updated Per Research

- [x] Co-occurrence/Hebbian data is consumed by R2 via participant co-occurrence from st_kg_edges (27 edges, 5 family entities).
- [x] Adaptive weighting REJECTED — static weights (0.45 semantic / 0.25 temporal / 0.30 narrative) outperform all tested adaptive policies.
- [ ] Reliability and provenance gating DEFERRED — 0/1360 corpus coverage for source_reliability, k1_signal_version, temporal_source. Cannot validate.
- [ ] EventAdapter reliability/provenance properties — DEFERRED pending K1 signal population.
- [x] Adaptive distance weight key namespace — designed (dist_weight_ prefix) but deployment unnecessary since adaptive weights rejected.
- [x] Combined Hebbian + static weight interaction bounded: max 5% distance reduction, score_std=0.0 over 5 stability cycles.
- [x] Fallback chain: Hebbian fallback = affinity 0 -> boost_factor 1.0 (neutral). Weights fallback = static defaults.

#### Milestone 5 Completion Verification

| Area | Status | Evidence |
| ---- | ------ | -------- |
| Research | COMPLETE | All M5 research artifacts in `poc/r2_phase_research/`. Hebbian, adaptive, stability all researched. |
| Code | RESEARCH COMPLETE | Hebbian boost proven in POC. Production wiring into `composite_distance.py` is implementation (not research). |
| Tests | RESEARCH COMPLETE | 8-scenario replay proves Hebbian boost improves 3 scenarios without contaminating 5 others. |
| Protocol | PARTIAL | EventAdapter reliability properties exist but are unpopulated. Adaptive-weight key schema designed but deployment unnecessary. |
| Fallback safety | VERIFIED | Hebbian: affinity=0 -> neutral. Static weights: hardcoded defaults. No oscillation risk with rejected adaptive path. |
| Cross-epic integration | VERIFIED | Hebbian + static weights: bounded at 5% max reduction, non-oscillatory, score_std=0.0. |
| Adjuster independence | N/A | Adaptive weights rejected. Only Hebbian boost + static weights remain. No state stomping possible. |
| Handoff | READY | Clear production parameters documented. Implementation is straightforward wiring. |

---

## RESEARCH-TO-PRODUCTION PARAMETER REGISTRY

**Source**: `poc/r2_phase_research/results/R2_RESEARCH_FINAL.md` (authoritative)
**Date**: 2025-07-10
**Purpose**: Complete mapping of every proven research parameter to its production target.
This is the single reference for what production must implement. Every value below is research-proven
and backed by experimental evidence across 68+ configurations on 1,360 real events.

### Proven Production Pipeline (Stage Order)

| Stage | Name | Research Implementation | Production Target | Milestone |
| ----- | ---- | ---------------------- | ----------------- | --------- |
| S1 | Splitting | `research_balanced_v1` config in `run_matrix.py` | `EpisodeSplitter.split()` with `research_balanced_v1` defaults | M3 |
| S2 | Distance matrix | `ens_fuzzy_narrative_v10` 3D confidence-weighted ensemble | `EnsembleDistance.build_distance_matrix()` via `EnsembleDistanceConfig` | M3 + M6 |
| S2b | Hebbian boost | Participant co-occurrence multiplicative post-modifier | DONE: `hebbian_boost.py` + `EpisodicHDBSCAN` + `R2PhaseAdapter` wiring | M5 |
| S3 | HDBSCAN clustering | Precomputed metric, leaf, min_cluster=2, min_samples=1 | `EpisodicHDBSCAN.cluster()` (params unchanged) | M2 |
| S4 | Thread purity correction | `correct_cluster_thread_purity()` in `r2_final_pipeline.py` | New: `ThreadPurityCorrector` in `thread_purity.py` | M6 |
| S5 | Same-thread merge | `merge_same_thread_clusters()` in `r2_final_pipeline.py` | New: `SameThreadMerger` in `same_thread_merge.py` | M6 |
| S6 | Cross-batch reconciliation | `run_two_tier_pipeline()` in `reconciliation.py` | `ReconciliationEngine` rewrite (two-tier) | M9 |
| S7 | Scene segmentation | `segment_mega_episodes()` in `scene_segmentation.py` | New: `SceneSegmenter` module | M9 |
| S8 | Centroid encoding | `recency_exp` + `best_of_all` multi-centroid | `CentroidCalculator` (update weighting + add multi-centroid) | M4 |

### Batch Size Decision (CRITICAL)

| Parameter | Current Production | Research Proven | Change Required |
| --------- | ------------------ | --------------- | --------------- |
| `R0SelectionConfig.batch_size` | **300** | **300** | DONE (2026-03-09) |

**Evidence** (R2_RESEARCH_FINAL.md Section 13.7):

- bs300 CogQ = 0.7293 (95% of maximum, 172 episodes)
- bs100 CogQ = identical across ALL 9 threshold variants (thresholds are inert at bs100)
- Single-pass CogQ = 0.6668 (worst non-temporal, mega-blob bias)
- Temporal gap configs CogQ = 0.656 (worst overall)
- bs500 gains only +0.38% over bs300 (diminishing returns)
- **Batch size is the dominant lever for cognitive quality, not threshold tuning**

### Splitter Configuration (`research_balanced_v1`)

**Source**: R2_RESEARCH_FINAL.md Section 2.1

| Parameter | Value |
| --------- | ----- |
| `hard_time_gap_minutes` | 480 (8h silence -> force split) |
| `hard_episode_span_minutes` | 1080 (18h span -> force split) |
| `hard_context_gap_minutes` | 180 (3h gap + low semantic sim -> force split) |
| `soft_split_threshold` | 0.45 |
| `thread_mismatch_penalty` | 0.35 |
| `same_thread_bonus` | 0.45 |
| `semantic_low_penalty` | 0.30 (cosine < 0.55) |
| `semantic_mid_penalty` | 0.15 (cosine 0.55-0.70) |
| `strong_semantic_bonus` | 0.20 (cosine > 0.86) |
| `participant_zero_penalty` | 0.15 |
| `participant_overlap_bonus` | 0.15 |
| `place_change_penalty` | 0.15 |
| `activity_change_penalty` | 0.10 |

### 3D Distance Model (`ens_fuzzy_narrative_v10`)

**Source**: R2_RESEARCH_FINAL.md Section 2.2

**Decision: 3D not 6D** — Spatial/social/affective tested in V12/V15/V18, no improvement. Revisit when coverage improves.

| Dimension | Weight | Notes |
| --------- | ------ | ----- |
| Semantic (cosine) | 0.45 | Primary, always available |
| Temporal (log-compressed) | 0.25 | Always available |
| Narrative (thread/goal fallback) | 0.30 | Thread identity with UltraBERT semantic matching |
| Spatial | 0.0 | NOT USED — too sparse |
| Social | 0.0 | NOT USED — too sparse |
| Affective | 0.0 | NOT USED — too sparse |

**Formula**: `d = sum(w_i * conf_i * d_i) / sum(w_i * conf_i)` — auto-redistributes when dimensions missing.

**Narrative Fallback Chain** (7 tiers):

| Tier | Condition | Distance | Confidence |
| ---- | --------- | -------- | ---------- |
| 1 | Thread exact match | 0.00 | 1.0 |
| 2 | Thread semantic same (>= 0.78) | 1 - sim | 0.7 |
| 3 | Thread semantic fuzzy (>= 0.60) | 1 - sim | 0.45 |
| 4 | Thread different (< 0.60) | 1.0 | 0.9 |
| 5 | Goal exact match | 0.10 | 0.6 |
| 6 | Goal different | 0.85 | 0.4 |
| 7 | One has signal, other doesn't | 0.50 | 0.2 |
| MISS | No narrative signal | 0.50 | 0.0 (excluded) |

**Short-circuit**: enabled, cap = 0.20, triggers on narrative confidence >= 0.7 (same-thread only, asymmetric safety).

**UltraBERT thread cache**: thread slug -> natural language phrase -> 768-dim embedding, cached per unique slug.

**Thread merge in purity correction**: DISABLED (threshold = 1.0). 6/21 false merges at 0.78. Re-enable only with explicit allowlist.

### Hebbian Boost Parameters

**Source**: R2_RESEARCH_FINAL.md Section 12.3

| Parameter | Value |
| --------- | ----- |
| `boost_scale` | 0.10 |
| `boost_cap` | 0.05 |
| `min_count` | 1 |
| Formula | `d_hebbian = d_ensemble * (1 - min(affinity * boost_scale, boost_cap))` |
| Fallback (disabled/missing) | `boost_factor = 1.0` (neutral) |

### HDBSCAN Parameters (unchanged)

**Source**: R2_RESEARCH_FINAL.md Section 2.2.5

| Parameter | Value |
| --------- | ----- |
| `min_cluster_size` | 2 |
| `min_samples` | 1 |
| `metric` | precomputed |
| `cluster_selection_method` | leaf |
| `noise_rescue_threshold` | 0.5 |

### Post-Cluster Thread Purity Correction

**Source**: R2_RESEARCH_FINAL.md Section 4.2

| Parameter | Value |
| --------- | ----- |
| Group by | `narrative_thread_id` (fallback: `goal_context`) |
| Thread merge (UltraBERT) | DISABLED (threshold = 1.0) |
| Split trigger | 2+ distinct thread groups in cluster |
| No-thread events | Assigned to majority thread |
| Label policy | Majority (>50%), not plurality |

### Same-Thread Episode Merge

**Source**: R2_RESEARCH_FINAL.md Section 4.5

| Parameter | Value |
| --------- | ----- |
| Purity threshold | >= 80% |
| Centroid similarity | cosine >= 0.70 |
| Temporal proximity | gap < 4 hours |
| Algorithm | Union-find with path compression |

### Reconciliation Configuration

**Source**: R2_RESEARCH_FINAL.md Section 13.8, 15.7

| Parameter | Value | Notes |
| --------- | ----- | ----- |
| `batch_size` | 300 | Sweet spot (Section 13.7) |
| `extend_sim` | 0.70 | Matches single-pass merge threshold |
| `evolve_sim` | 0.40 | DEAD CODE — zero fires in 275 reconciliations. Remove. |
| `temporal_gap` | OFF (disabled) | Any gap fragments episodes |
| `evolve_absorbs` | false | Inert |
| `post_cluster_correction` | ON | Thread purity correction |
| `same_thread_merge` | ON | Union-find merge |

**Two-tier engine**: K1 signals checked first (EVOLVE/CONTRADICT), then cosine cascade (REINFORCE > 0.85, EXTEND > 0.60, CREATE < 0.60).

### Centroid Encoding

**Source**: R2_RESEARCH_FINAL.md Section 11

| Decision | Value | Evidence |
| -------- | ----- | -------- |
| Primary weighting | `recency_exp` | MRR = 0.9006 (+6.6% vs hybrid) |
| Multi-centroid strategy | `best_of_all` (primary + start + end + emotional_peak + narrative_anchor) | MRR = 0.9627 (+4.9% vs primary_only) |
| Storage | `json_blob` (add `centroid_metadata` JSON column to st_epi) | Simpler than side_table, backward compat |
| HDBSCAN probability weighting | REJECTED | Uniform MRR = 0.8943 > best prob 0.8813 |
| Signal-weighted centroids | REJECTED | All 9 signals SUMMARY-ONLY (delta < 0.01) |

### Scene Segmentation

**Source**: R2_RESEARCH_FINAL.md Section 14

| Parameter | Value |
| --------- | ----- |
| `scene_gap_hours` | 4.0 |
| `overnight_gap_hours` | 8.0 |
| `max_scene_events` | 35 |
| `min_scene_events` | 3 |
| `context_gap_hours` | 2.0 |
| `absorb_max_events` | 4 |
| `absorb_max_gap_hours` | 6.0 |
| `absorb_min_similarity` | 0.50 |

**Position**: Between batch reconciliation and centroid encoding (Stage S7).

### Silhouette & Adaptive Loop

**Source**: R2_RESEARCH_FINAL.md Section 8

| Parameter | Value |
| --------- | ----- |
| ClusterQualityTracker composite | `0.40 * silhouette + 0.30 * grounding + 0.20 * (1 - correction) + 0.10 * (1 - singleton)` |
| `silhouette_target` (EpsAdjuster) | 0.5 (soft gate) |
| EpsAdjuster convergence | Stable: 0.2500 -> 0.2540 over 10 batches, 0 oscillation |

### CogQ Metric Weights (Scene-Level Calibration)

**Source**: R2_RESEARCH_FINAL.md Section 13.2, 14.6

| Metric | Weight | Scene-Level Score |
| ------ | ------ | ----------------- |
| M1 Entity Retrievability | 0.15 | 0.727 |
| M2 Affective Quality | 0.15 | 0.643 |
| M3 Activity Clustering | 0.10 | 0.579 |
| M4 Spatial-Social | 0.10 | 0.781 |
| M5 Temporal Integrity | 0.10 | 0.794 |
| M6 Narrative Fidelity | 0.10 | 0.703 |
| M7 Coverage | 0.05 | 0.997 |
| M8 Retrieval Simulation | 0.25 | 0.683 |

**Scene-level recalibrations** (Section 14.6): M6 fragmentation `max(1, n_events // 8)`, M1 weights 0.25/0.35/0.40, M3 concentration `/3.0` + weights 0.50/0.50, M8 weights 0.30/0.40/0.30.

### Dead Code Removal Checklist

**Source**: R2_RESEARCH_FINAL.md Sections 5.3, 9.2, 15

| Item | Action | When | Rationale |
| ---- | ------ | ---- | --------- |
| `EpisodicDBSCAN` class | REMOVE | M2 | Dead code, HDBSCAN strictly better (Section 9.2) |
| `DBSCANParams` dataclass | REMOVE | After M3 (ensemble distance lands) | Currently needed by CompositeDistance (Section 9.4) |
| `HDBSCANParams.to_dbscan_params()` bridge | REMOVE | After M3 | Bridge to dead path (Section 9.4) |
| `_merge_similar_threads()` in post-cluster | DISABLE (threshold=1.0) | M6 | 6/21 false merges at 0.78 (Section 2.2.3.1) |
| 6D distance dims (spatial, social, affective) | DO NOT BUILD | N/A | No improvement, too sparse (Section 5.3) |
| Boost separation | DO NOT BUILD | N/A | Post-cluster correction solves it (Section 5.3) |
| Signal-weighted centroids | DO NOT BUILD | N/A | All 9 signals SUMMARY-ONLY (Section 11.9) |
| HDBSCAN probability-weighted centroids | DO NOT BUILD | N/A | Uniform beats all (Section 11.5) |
| EVOLVE/CONTRADICT cosine detection (0.40 threshold) | REMOVE from P03 | M9 | Cannot work, delegate to K1 (Section 15) |
| `dbscan_eps`/`dbscan_min_samples` key rename | DEFER | After M3 | Cosmetic, single migration (Section 8.3) |

### Production Target File Map

| Production File | Change | Milestone |
| --------------- | ------ | --------- |
| `k0/modules/consolidation/algorithms/composite_distance.py` | Replace 2D with 3D confidence-weighted ensemble | M3 + M6 |
| `k0/modules/consolidation/algorithms/episodic_hdbscan.py` | Wire `EnsembleDistanceConfig`, pass to distance builder | M6 |
| `k0/modules/consolidation/algorithms/thread_purity.py` | NEW: post-cluster correction + label policy | M6 |
| `k0/modules/consolidation/algorithms/same_thread_merge.py` | NEW: union-find merge with cosine >= 0.70, gap < 4h | M6 |
| `k0/modules/consolidation/algorithms/centroid_calculator.py` | Replace uniform with `recency_exp`, add `best_of_all` multi-centroid | M4 |
| `k0/modules/consolidation/algorithms/scene_segmenter.py` | NEW: temporal/context/size splitting + micro-fragment absorption | M9 |
| `k0/pipelines/p03/phases/r0_batch_selector.py` | Change `batch_size` default from 100 to 300 | M6 |
| `k0/pipelines/p03/phases/r2_episodic_integrator.py` | Wire ensemble distance, add post-cluster stages (S4, S5) | M6 |
| `k0/pipelines/p03/phases/r3_dedup_decay.py` | Rewrite to two-tier reconciliation engine | M9 |
| `k0/db/alembic/versions/` | Add `centroid_metadata` JSON column to st_epi | M4 |
| `k0/modules/consolidation/algorithms/episodic_hdbscan.py` | Remove `EpisodicDBSCAN` class | M2 |

---

## MILESTONE 6: Production Episode Quality — Wiring, Purity, Merge, Cross-Batch (P5)

**Milestone Status**: IN PROGRESS (started 2026-03-09, M5 complete)
**Execution Gate**: M5 DONE.
**Priority**: HIGHEST — This is the gap between research-quality episodes and production disaster.

### Milestone 6 Research Summary

Research pipeline (`r2_final_pipeline.py`) proves all M6 algorithms on 1,360 events across 8 scenarios.
Production baseline comparison demonstrates the gap is real and the fixes are proven:

| Root Cause | Research Fix | Research Result | Production Gap |
| ---------- | ------------ | --------------- | -------------- |
| RC-0: Batch-100 | batch_size=300 sweet spot | CogQ=0.7293 at bs300 | DONE: batch_size=300 in r0_batch_selector.py + drain loop in sequential_adapter.py (2026-03-09) |
| RC-1: No ensemble distance | ens_fuzzy_narrative_v10 (3D: 0.45/0.25/0.30) | Thread-aware clustering | Falls back to legacy 2D (0.7 sem + 0.3 temp) |
| RC-2: No thread purity | correct_cluster_thread_purity() | 70 clusters split, 0% contamination | 53% contamination (260/490 episodes) |
| RC-3: No same-thread merge | merge_same_thread_clusters() | 531->260 clusters, 271 merged | 183 maya_fears fragments (2-8 events each) |
| RC-4: No cross-batch extend | Two-tier reconciliation (M9) | EXTEND>=0.60+same_thread | REINFORCE-only at 0.85 (no episode growth) |

**Proven production parameters**:

- Ensemble config: `ens_fuzzy_narrative_v10` with confidence-weighted bagging, 6-tier narrative fallback, shortcircuit cap=0.20, thread_fuzzy_threshold=0.65
- Thread purity: split on distinct narrative threads per cluster. UltraBERT thread merge DISABLED (6/21 false merges at cosine>=0.78)
- Same-thread merge: union-find with path compression, centroid_sim>=0.70, temporal_gap<=4h, purity>=80%
- Cross-batch: reconciliation-based (deferred to M9 universal reconciliation architecture)

### Epic 6.1: Wire Ensemble Distance Into Production R2

**Discovery Reference**: Milestone 6 RC-1
**Repo Status**: DONE (2026-03-09)
**Dependency**: `EnsembleDistanceConfig` and `EnsembleDistance` already exist. `EpisodicHDBSCAN` already accepts `ensemble_config`.

#### Epic 6.1 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 6.1.1 Wire ensemble_config in_initialize_components | DONE | Passed `ensemble_config=EnsembleDistanceConfig()` to `EpisodicHDBSCAN` constructor. |
| 6.1.2 Add R2Config fields for ensemble control | DONE | Added `enable_ensemble_distance: bool = True` and `ensemble_distance_config: Optional[EnsembleDistanceConfig] = None` to `R2Config`. |
| 6.1.3 Remove legacy semantic_weight/temporal_weight from R2Config | DONE | Kept as fallback when `enable_ensemble_distance=False`. Legacy 2D path preserved. |
| 6.1.4 Update integration tests | DONE | 20 tests in `test_r2_ensemble_wiring.py`: config fields, wiring, clustering integration, legacy fallback, matrix parity. |
| 6.1.5 Update contracts | DONE | Updated `p03_consolidation.v1.yaml` R2 stage: ensemble_v10 distance model, 3D weights, shortcircuit, Hebbian. |

### Epic 6.2: Thread Purity Correction

**Discovery Reference**: Milestone 6 RC-2
**Repo Status**: OPEN
**Dependency**: None -- operates on any list of episode clusters with member events that have `narrative_thread_id`.

#### Epic 6.2 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 6.2.1 Implement ThreadPurityCorrector | OPEN | Create `k0/modules/consolidation/algorithms/thread_purity.py` with a `ThreadPurityCorrector` class. |
| 6.2.2 Wire into R2 execute flow | OPEN | Add purity correction step after HDBSCAN clustering, before centroid calculation. |
| 6.2.3 Add R2Config control | OPEN | Add `enable_thread_purity_correction: bool = True` to `R2Config`. |
| 6.2.4 Add observability | OPEN | Emit correction stats: clusters_before, clusters_after, clusters_split, events_reassigned. |
| 6.2.5 Write tests | OPEN | Unit tests for pure clusters (no-op), impure clusters (split), unthreaded events (majority assignment), edge cases. |

### Epic 6.3: Same-Thread Episode Merge

**Discovery Reference**: Milestone 6 RC-3
**Repo Status**: OPEN
**Dependency**: Epic 6.2 (purity correction must run first so merged clusters are pure).

#### Epic 6.3 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 6.3.1 Implement SameThreadMerger | OPEN | Create `k0/modules/consolidation/algorithms/same_thread_merge.py` with `SameThreadMerger` class. |
| 6.3.2 Wire into R2 execute flow | OPEN | Add same-thread merge step after purity correction, before centroid calculation. |
| 6.3.3 Add R2Config control | OPEN | Add `enable_same_thread_merge: bool = True`, `merge_centroid_sim_threshold: float = 0.70`, `merge_max_temporal_gap_hours: float = 4.0` to `R2Config`. |
| 6.3.4 Add observability | OPEN | Emit merge stats: clusters_before, clusters_after, merges_performed, largest_merged_cluster_size. |
| 6.3.5 Write tests | OPEN | Unit tests for merge eligibility, union-find correctness, transitive merge chains, non-merge cases. |

### Epic 6.4: Cross-Batch Episode Extension

**Discovery Reference**: Milestone 6 RC-0 and RC-4
**Repo Status**: OPEN
**Dependency**: Epics 6.1-6.3 (intra-batch quality must be solved first; cross-batch builds on top).

#### Epic 6.4 Problem Statement

Even after Epics 6.1-6.3 fix intra-batch quality, the batch-300 architecture with drain loop
means events from the same thread spanning multiple batches still produce separate episodes per
batch. The within-batch merge (Epic 6.3) can only merge fragments within a single 300-event batch.

The drain loop (sequential_adapter.py, 2026-03-09) processes ALL pending events in st_hipp_events
(300 per batch, looping until R0 reports no more eligible events). This reduces but does not
eliminate cross-batch fragmentation: maya_fears with 183 events now fits in a single batch, but
larger thread backlogs or ongoing ingestion still produce multi-batch fragments.

Example: A thread with 500 events spans 2 drain batches (batch 1: 300, batch 2: 200). Each batch
produces internally pure, merged episodes, but the 2 batches' episodes should be reconciled.

#### Epic 6.4 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 6.4.1 Implement EXTEND action in episode matching | OPEN | When a new episode's centroid matches an existing episode at >= 0.60 similarity AND shares dominant thread, merge the new into the existing. |
| 6.4.2 Add cross-batch merge eligibility criteria | OPEN | Same dominant thread required. Centroid similarity >= 0.60. Temporal gap < configurable limit. |
| 6.4.3 Prevent duplicate episodes from re-clustering | OPEN | After EXTEND, ensure extended events are not re-processed in future batches (update consolidation_status). |
| 6.4.4 Write tests | OPEN | Integration tests for cross-batch scenarios with thread continuity. |

**Shared implementation note**: The actual `_update_extend()` truth writer method, centroid
recomputation, and EXTEND/EVOLVE observability are defined canonically in **M7 Epics 7.1, 7.4,
and 7.5** respectively. M6 6.4 defines the cross-batch episode-to-episode MATCHING LOGIC only.
M7 defines the downstream WRITE and RECOMPUTE paths that both M6 cross-batch extend and M7
event-level extend share.

### Epic 6.5: Metadata Preservation In Truth Writer

**Discovery Reference**: Milestone 6 supplementary finding
**Repo Status**: OPEN
**Dependency**: M4 multi-centroid (4.2) and coherence (4.4) outputs exist on EpisodeCluster but are lost during persistence.

#### Epic 6.5 Problem Statement

`truth_write_assembler.py` `_build_epi_record_data()` maps `EpisodeCluster` to st_epi columns
but drops several fields:

| Field | Status | Impact |
| ----- | ------ | ------ |
| `centroid_metadata` | LOST | Multi-centroids (start, end, emotional_peak, narrative_anchor) computed by M4 but never stored |
| `ambiguity_score` | LOST | Episode confidence quality signal discarded |
| `source_events_json` | UUID list only | No event text, participant info, or affect scores preserved |

#### Epic 6.5 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 6.5.1 Persist centroid_metadata to st_epi | OPEN | Add `centroid_metadata` JSONB column to st_epi (migration). Map from `EpisodeCluster.centroid_metadata` in truth writer. |
| 6.5.2 Persist ambiguity_score | OPEN | Map `EpisodeCluster.ambiguity_score` to existing or new st_epi column. |
| 6.5.3 Enrich source_events_json | OPEN | Optionally store per-event summary data (thread_id, timestamp, participants) alongside UUIDs for faster episode reconstruction without joining st_hipp_events. |

---

### Epic 6.6: Consolidation Cycle Deduplication

**Discovery Reference**: Milestone 6 supplementary finding (RC-4 duplicate episodes)
**Repo Status**: DONE

#### Epic 6.6 Problem Statement

30 duplicate episodes (10 groups) exist in st_epi with identical `source_events_json`. The
`ON CONFLICT DO NOTHING` in `EpisodicLayerWriter._insert()` prevents crashes on episode_id
collision but does NOT prevent multiple consolidation cycles from re-clustering the same events
and creating new episodes with different UUIDs covering the same event set.

Root cause: R0 batch selection does not exclude events that were already clustered into episodes
in a previous cycle. The `consolidation_status` field on st_hipp_events should be updated to
`CONSOLIDATED` after successful R7 write, but 260 events have `consolidation_status = NULL`.

#### Epic 6.6 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 6.6.1 Update consolidation_status after R7 write | DONE (verified in code) | R7 `_writeback_status()` (line 1031) atomically updates consolidation_status for ALL batch events inside the same UoW as truth writes. Status mapping: CREATE/REINFORCE/EXTEND/EVOLVE->CONSOLIDATED, SKIP->DUPLICATE, PRUNE->PRUNED, CONTRADICT->PENDING_REVIEW, PENDING->PENDING. Default (noise events) -> PENDING (re-processable). |
| 6.6.2 R0 exclusion filter | DONE (verified in code) | R0 `_fetch_eligible_events()` (line 1219) filters `WHERE consolidation_status IS NULL OR consolidation_status = 'PENDING'`. CONSOLIDATED, DUPLICATE, PRUNED, PENDING_REVIEW events are excluded. |
| 6.6.3 Orphan event rescue | DONE (migration 0087) | Root cause: events processed before _writeback_status existed. Migration 0087 backfills: Pass 1 sets events found in st_epi to CONSOLIDATED, Pass 2 sets remaining ready events to PENDING for re-processing. |

**Test file**: `tests/k0/pipelines/p03/test_consolidation_cycle_dedup.py` (52 tests)
**Migration**: `k0/db/alembic/versions/0087_backfill_consolidation_status.py`

---

### Milestone 6 Execution Order

0. **RC-0** (batch_size=300 + drain loop) DONE (2026-03-09).
1. **Epic 6.1** (ensemble distance wiring) FIRST -- highest impact, lowest risk, smallest change.
2. **Epic 6.2** (thread purity correction) SECOND -- eliminates 53% contamination.
3. **Epic 6.3** (same-thread merge) THIRD -- depends on 6.2 output, reduces 800 episodes to ~260.
4. **Epic 6.6** (deduplication) FOURTH -- prevents future duplicate creation before extending.
5. **Epic 6.4** (cross-batch extension) FIFTH -- addresses cross-batch fragmentation across drain cycles.
6. **Epic 6.5** (metadata preservation) LAST -- supplementary quality improvement.

### Milestone 6 Exit Criteria

- Production R2 uses 6D ensemble distance (narrative dimension active).
- Thread purity correction runs on every batch, producing 0% cross-thread contamination.
- Same-thread merge runs on every batch, producing episode sizes comparable to research.
- Cross-batch extension enables episodes to grow across consolidation cycles.
- No duplicate episodes from re-clustering already-consolidated events.
- Centroid_metadata and ambiguity_score are persisted to st_epi.
- Replay comparison against research baseline: scenario must_link >= 0.8 on at least 7/8 scenarios.

### Milestone 6 Completion Verification

| Area | Verification Requirement |
| ---- | ------------------------ |
| Research parity | Production episode counts, contamination, fragmentation, and scenario scores within 20% of research pipeline output on the same 1,360-event corpus |
| Code | ThreadPurityCorrector, SameThreadMerger, EXTEND action, and ensemble wiring all present and enabled by default |
| Tests | Unit tests for purity correction, same-thread merge, cross-batch extension. Integration tests for full R2 flow with all 3 new steps. Replay comparison test. |
| Contracts | P03 pipeline and R2 module contracts updated to describe purity correction, same-thread merge, and cross-batch extension |
| Deduplication | No duplicate source_events_json in st_epi. consolidation_status correctly updated after R7 write. |
| Observability | Correction stats, merge stats, and extend stats emitted per batch for monitoring |
| Rollback safety | Each new step (ensemble, purity, merge, extend) independently disableable via R2Config flags |

---

## MILESTONE 7: REMOVED — Absorbed Into Milestone 9 (2026-03-08)

**Milestone Status**: REMOVED
**Reason**: M7 built bespoke EXTEND/EVOLVE lifecycle mechanics for st_epi only. M9 builds a
universal reconciliation framework that handles EXTEND/EVOLVE/CONTRADICT for ALL truth layers.
Maintaining both milestones created structural duplication where M7 proved patterns that M9
immediately generalized and replaced. Building `_update_extend()` and `_evolve()` bespoke for
st_epi in M7, then immediately replacing the routing with WriteDecisionRouter in M9, is wasted
effort. M9 builds the framework AND the layer-specific SQL methods simultaneously.

### Absorption Map

| M7 Epic | Content | M9 Home | Notes |
| ------- | ------- | ------- | ----- |
| 7.1 Wire EXTEND (R3-R6-R7) | Bespoke st_epi EXTEND routing + `_update_extend()` | 9.5 WriteDecisionRouter EXTEND mapping + 9.6 Migrate R2 | `_update_extend()` created in `episodic.py`, called by WriteDecisionRouter |
| 7.2 Wire EVOLVE (versioning) | K1 signal check + `_evolve()` + SUPERSEDED lifecycle | 9.4.5 K1 signal tier + 9.5.5 EVOLVE mapping + 9.6 | `_evolve()` created in `episodic.py`, called by WriteDecisionRouter |
| 7.2.0 Signal pipeline | K1 atom v2.2 -> P02 -> st_hipp_events -> P03 R0 -> EventState | **DONE (inherited by M9)** | Implemented 2026-03-08. M9 ReconciliationCandidate reads from P03EventState. |
| 7.2.8 Remove cosine EVOLVE | Remove 0.40 threshold from R3 `_determine_action()` | 9.4.5 + 9.7 (R3 migration) | Framework has no 0.40 threshold. R3 migration replaces the engine entirely. |
| 7.3 Rich Structured Summaries | EpisodeStructuredSummary schema + generator | **9.11** (new epic) | Independent of reconciliation, needed by EXTEND/EVOLVE write paths. |
| 7.4 Embedding Regeneration | Recompute centroid on EXTEND/EVOLVE | **9.12** (new epic) | WriteDecisionRouter EXTEND/EVOLVE paths include embedding regen. |
| 7.5 Lifecycle Observability | EXTEND/EVOLVE metrics + logging | **9.13** (new epic) | Framework-level observability across all layers, not just st_epi. |

### Completed Work Preserved

**Issue 7.2.0 (K1 Correction Signal Pipeline) — DONE (2026-03-08)**:

Files: `memory_atom.v2.schema.json`, `types.py`, `memory_writer_architecture.md`,
`0085_st_hipp_events_k1_correction_signals.py`, `st_hipp_events_v2.columns.yaml`,
`hipp_events_row.py`, `r0_batch_selector.py`, `event_state.py`.

End-to-end verified: K1 atom -> Bridge envelope.body -> P02 M13 -> st_hipp_events -> P03 R0 ->
P03EventState. The ReconciliationCandidate type (M9 Epic 9.4) reads these fields from
P03EventState (already populated by R0). M9 does NOT re-implement the signal pipeline.

### Design Context Preserved

The M7 root cause analysis, operating assumptions, context pack, proof obligations, and per-epic
design details remain valid architectural context for M9 implementation. Key references:

- **EXTEND design**: `_update_reinforce()` pattern in `episodic.py` L401-510 is the model for
  `_update_extend()`. EXTEND updates: summary, embedding_text, participants_json,
  narrative_thread_ids_json (not just event IDs and temporal bounds like REINFORCE).
- **EVOLVE design**: Two SQL operations in one transaction — UPDATE old (SUPERSEDED) + INSERT
  new (supersedes_id = old PK). Optimistic locking on old episode version.
- **Structured summary schema**: See M9 Epic 9.11 for the full schema, ported from research
  `export_episodes_json()` at `r2_final_pipeline.py` L941-1021.
- **Embedding regen**: See M9 Epic 9.12. REINFORCE does NOT recompute centroid (lightweight).
  EXTEND DOES recompute (episode substantively grew). EVOLVE computes fresh (new episode).

---

## MILESTONE 8: End-to-End Integration Test Suite — Research-to-Production Parity (P8)

**Milestone Status**: RESEARCH COMPLETE (2025-07-10)
**Execution Gate**: Start after Milestone 9 completes.
**Priority**: CRITICAL — Without this, every prior milestone is self-certified. M8 is the external
proof that the production pipeline produces research-quality output through the full chain.

### Milestone 8 Research Summary

The CogQ (Cognitive Quality) metric framework and 8-scenario evaluation are fully proven in
`poc/r2_phase_research/`. M8 implementation ports these to production test infrastructure.

**CogQ Metric Framework** (8 weighted dimensions):

| Metric | Weight | Description | Research Score (Phase 9, Scene-Level) |
| ------ | ------ | ----------- | ------------------------------------- |
| M1: Entity Retrievability | 0.15 | Named entity recall per episode vs source events | 0.727 |
| M2: Affective Quality | 0.15 | Sentiment coherence within episodes | 0.643 |
| M3: Activity Clustering | 0.10 | Activity type coherence within episodes | 0.579 |
| M4: Spatial-Social | 0.10 | Location and participant coherence | 0.781 |
| M5: Temporal Integrity | 0.10 | Temporal continuity and ordering quality | 0.794 |
| M6: Narrative Fidelity | 0.10 | Thread coherence and narrative arc preservation | 0.703 |
| M7: Coverage | 0.05 | Fraction of events assigned to episodes (not noise) | 0.997 |
| M8: Retrieval Simulation | 0.25 | must_link/must_separate scoring across 8 scenarios | 0.683 |

**Final CogQ = 0.7117** (scene-level honest, Phase 9 after scene segmentation).
Phase 8 batch-optimal CogQ = 0.7293 (before scene segmentation splits mega-episodes).

**Target**: CogQ >= 0.70 for production parity. 7/8 scenarios at scene-level, 8/8 at cluster-level with Hebbian.

### Milestone 8 Component Map

The following maps each research pipeline stage to its production equivalent. After M2-M7
complete, every research stage has a production counterpart.

| Stage | ID | Research Implementation | Production Equivalent (Post-M7) | Key File |
| ----- | -- | ---------------------- | ------------------------------- | -------- |
| Load + Embed | A | `load_life_events()` + `attach_ultrabert_embeddings()` in `replay_loader.py` | R0 `R0BatchSelector.run()` — selects from st_hipp_events + st_vec | `r0_batch_selector.py` |
| Split | B | `split_with_research_rules()` in `run_matrix.py` — narrative-aware splitter | `EpisodeSplitter.split()` (M3 multi-signal boundary scoring) | `episode_splitter.py` |
| Distance + Cluster | C | `build_ensemble_distance_matrix()` + `cluster_with_ensemble_distance()` — 6D ensemble + HDBSCAN | `EpisodicHDBSCAN.cluster()` with `EnsembleDistanceConfig` (M3 6D + M6 wiring) | `episodic_hdbscan.py`, `composite_distance.py` |
| Thread Purity | D | `correct_cluster_thread_purity()` | `ThreadPurityCorrector.correct()` (M6 Epic 6.2) | `thread_purity.py` |
| Same-Thread Merge | E | `merge_same_thread_clusters()` | `SameThreadMerger.merge()` (M6 Epic 6.3) | `same_thread_merge.py` |
| Centroid + Quality | F | `_recency_exp_centroid()` + `_cluster_coherence()` + `_compute_multi_centroids()` | `CentroidCalculator` (RECENCY_EXP M4) + `EpisodicCoherenceScorer` (M4) + `SecondaryCentroidSelector` (M4) | `centroid_calculator.py`, `episodic_coherence.py` |
| Episode Matching + Lifecycle | G | N/A (research processes all events at once) | `_match_events_to_existing_episodes()` + EXTEND/EVOLVE (M6 6.4 + M7 7.1/7.2) | `r2_episodic_integrator.py` |
| Structured Summary | H | `export_episodes_json()` + `generate_episode_html()` | `StructuredSummaryGenerator` (M7 Epic 7.3) + `TextVectorCoordinator` (M7 7.4) | `episode_summary.py`, `text_vector_coordinator.py` |
| Reconciliation | I | N/A (research has no R3) | R3 `ReconciliationEngine` — REINFORCE/EXTEND/EVOLVE routing (M7 wiring) | `reconciliation_engine.py`, `r3_dedup_decay.py` |
| Staging + Truth Write | J | N/A (research outputs files) | R6 `TruthWriteAssembler` + R7 `EpisodicLayerWriter` — st_epi INSERT/UPDATE/EVOLVE | `truth_write_assembler.py`, `episodic.py` |
| Scenario Evaluation | K | `evaluate_scenarios_cluster_level()` — must_link/must_separate scoring | Test harness (NEW — port scenario framework to production test suite) | NEW: `test_scenario_evaluator.py` |

**Total**: 11 stages (A through K). All sequential in production (R0 -> R1 -> R2 -> R3 -> ... -> R8).

### Milestone 8 Testing Philosophy

**No mocks. No fakes. No simulations.**

Every integration test:

- Loads real event data (the 1,360-event corpus or a representative subset).
- Uses real embeddings (UltraBERT 768-dim, pre-computed and stored).
- Runs real algorithms (actual HDBSCAN, actual distance computation, actual SQL writes).
- Reads/writes real database tables (test schema, rolled back after each test).
- Validates output against the research pipeline's known-good results.

The ONLY acceptable test doubles are:

- Test database (separate schema or transaction rollback — NOT a mock DB).
- Pre-computed embeddings loaded from fixture files (NOT mock vectors).
- Fixture event data loaded from JSONL (the SAME data the research pipeline uses).

### Milestone 8 Sliding Window Test Matrix

The integration test suite uses a sliding window approach across the 11 stages. For a chain of
components A-B-C-D-E-F-G-H-I-J-K, the test windows are:

#### Window Size 2 (Adjacent Pairs) — 10 Tests

Each test exercises one handoff boundary between adjacent stages.

| Test ID | Window | What It Proves |
| ------- | ------ | -------------- |
| M8-W2-01 | A->B | R0 batch output feeds correctly into EpisodeSplitter. Event ordering, embedding availability, and split config compatibility. |
| M8-W2-02 | B->C | Splitter sequences feed correctly into EpisodicHDBSCAN with 6D ensemble distance. Sequence boundaries preserved. Distance matrix shape matches sequence length. |
| M8-W2-03 | C->D | HDBSCAN cluster output feeds correctly into ThreadPurityCorrector. Cluster member lists, thread IDs, and noise labels transfer correctly. |
| M8-W2-04 | D->E | Purity-corrected clusters feed correctly into SameThreadMerger. Pure sub-clusters eligible for merge. Thread IDs consistent after split. |
| M8-W2-05 | E->F | Merged clusters feed correctly into CentroidCalculator + CoherenceScorer. Member embeddings available for centroid computation. Coherence dimensions computable. |
| M8-W2-06 | F->G | EpisodeCluster objects (with centroids, coherence, multi-centroid metadata) feed correctly into episode matching. Centroid similarity computation works against st_epi. |
| M8-W2-07 | G->H | Episode matching output (INSERT/EXTEND/EVOLVE decisions) feeds correctly into StructuredSummaryGenerator. Member contexts available for summary extraction. |
| M8-W2-08 | H->I | Structured summaries feed correctly into R3 ReconciliationEngine. Event states carry correct reconciliation actions. EXTEND/EVOLVE actions route correctly. |
| M8-W2-09 | I->J | Reconciliation output feeds correctly into R6 TruthWriteAssembler + R7 EpisodicLayerWriter. StagedWrite objects contain correct action types. INSERT/UPDATE/EVOLVE SQL executes without error. |
| M8-W2-10 | J->K | Truth-written episodes can be read back and evaluated against scenarios. Episode data in st_epi matches expected structure. Scenario must_link computable from persisted episodes. |

#### Window Size 3 (Triples) — 9 Tests

Each test exercises two handoff boundaries, catching interface mismatches that pair tests miss.

| Test ID | Window | What It Proves |
| ------- | ------ | -------------- |
| M8-W3-01 | A->B->C | Full data acquisition through clustering. Events load, split into sequences, and cluster with 6D distance. Output: labeled clusters with member events and embeddings. |
| M8-W3-02 | B->C->D | Split + cluster + purity correction. Sequences cluster correctly and impure clusters are split by thread. Output: pure clusters. |
| M8-W3-03 | C->D->E | Cluster + purity + merge. Raw HDBSCAN output is corrected for purity then merged into coherent same-thread arcs. Output: final episode candidates. |
| M8-W3-04 | D->E->F | Purity + merge + centroid/quality. Pure merged clusters get RECENCY_EXP centroids, coherence scores, and multi-centroid metadata. Output: fully-scored EpisodeCluster objects. |
| M8-W3-05 | E->F->G | Merge + centroid + episode matching. Merged episodes with centroids are matched against existing st_epi episodes for EXTEND/EVOLVE/INSERT decisions. |
| M8-W3-06 | F->G->H | Centroid + matching + summary. Episodes with lifecycle decisions get rich structured summaries generated from member event contexts. |
| M8-W3-07 | G->H->I | Matching + summary + reconciliation. Lifecycle decisions flow through structured summary generation into R3 reconciliation, which validates and routes actions. |
| M8-W3-08 | H->I->J | Summary + reconciliation + truth write. Reconciled events with structured summaries are staged and written atomically to st_epi with correct EXTEND/EVOLVE/INSERT handling. |
| M8-W3-09 | I->J->K | Reconciliation + write + evaluation. Written episodes are readable, scenario-evaluable, and produce must_link scores consistent with research. |

**Total test count: 50 integration tests** (10 + 9 + 8 + 7 + 6 + 5 + 2 + 1 + 1 + 1 = 50).

### Milestone 8 Test Data Strategy

**Primary corpus**: The same 1,360-event dataset used by the research pipeline
(`poc/r2_phase_research/data/life_events.jsonl`). This is the ONLY dataset that has research
baseline results for comparison.

**Fixture preparation**: Before M8 tests run, a fixture generation step pre-computes and caches:

1. **Event fixtures**: 1,360 events loaded from JSONL with all fields populated.
2. **Embedding fixtures**: Pre-computed UltraBERT 768-dim embeddings for all 1,360 events
   (stored as numpy arrays or JSON). Tests load these instead of calling UltraBERT at test time.
3. **Research baseline fixtures**: Known-good outputs from the research pipeline at each stage:
   - Stage B output: expected sequence boundaries (split points).
   - Stage C output: expected cluster assignments per sequence.
   - Stage D output: expected purity-corrected clusters.
   - Stage E output: expected merged clusters.
   - Stage F output: expected centroid embeddings and coherence scores.
   - Stage K output: expected scenario must_link/must_separate scores.
4. **Database fixtures**: Test schema with st_hipp_events, st_vec, st_epi pre-populated for
   cross-batch tests (episodes from "previous batches" that EXTEND/EVOLVE tests match against).

**Fixture location**: `tests/k0/pipelines/p03/fixtures/r2_integration/`

**Fixture generation script**: `tests/k0/pipelines/p03/fixtures/generate_r2_fixtures.py` — runs
the research pipeline once and snapshots output at each stage. This script is run manually when
the research pipeline changes, NOT as part of the test suite.

### Milestone 8 Scenario Framework

The research pipeline's scenario evaluation (`evaluate_scenarios_cluster_level()`) is a key
validation tool. M8 ports this to a reusable test framework.

**Scenario definition**: Each scenario specifies:

- `scenario_id`: unique identifier (e.g., `maya_fears_at_home`)
- `must_link`: list of event groups that MUST land in the same episode
- `must_separate`: list of event groups that MUST land in DIFFERENT episodes
- `description`: human-readable scenario description

**Scenario scoring**:

- `must_link_score`: fraction of must_link groups where all events share the same episode
- `must_separate_score`: pairwise contamination check (0 overlap = 1.0)
- `overall_score`: weighted combination (0.45 must_link + 0.45 must_separate + 0.10 purity)

**Scenario pack**: The standard 8 scenarios from the research pipeline (`poc/r2_phase_research/cognitive_metrics.py`):

1. `clean_maya_fears_arc` — Maya's fears narrative thread (longest arc, up to 47 events)
2. `clean_familyos_development_work_block` — FamilyOS development/work discussion thread
3. `cross_context_home_office_collision` — Same participant, different contexts (home vs office) must separate
4. `dad_recovery_temporal_drift` — Temporally drifted arc, tests temporal gap handling
5. `rescue_edge_family_overlap` — Edge case: family overlap scenario, tests rescue mechanism + Hebbian
6. `within_entity_maya_birthday_vs_preschool` — Maya events: birthday vs preschool must separate
7. `within_entity_maya_fears_vs_preschool` — Maya events: fears vs preschool must separate (Hebbian improved)
8. `within_entity_maya_fears_vs_birthday` — Maya events: fears vs birthday must separate

**Research results** (Phase 8, cluster-level with Hebbian): 8/8 scenarios perfect (must_link=1.0).
**Research results** (Phase 9, scene-level after segmentation): 7/8 scenarios (dad_recovery_temporal_drift drops to 0.50).

**Production scenario evaluator**: `k0/modules/consolidation/algorithms/scenario_evaluator.py`
(NEW) — operates on st_epi rows instead of in-memory clusters. Queries episode membership,
computes must_link/must_separate against persisted episodes.

### Milestone 8 Full Config Verification

The final integration test (M8-FULL-01) runs with the COMPLETE production configuration:

| Config Area | Setting | Source |
| ----------- | ------- | ------ |
| R0 batch_size | **300** (research-proven sweet spot, was 100) | `R0SelectionConfig` — R2_RESEARCH_FINAL.md Section 13.7 |
| Ensemble distance | ENABLED (3D: 0.45 sem / 0.25 temp / 0.30 narr) | `R2Config.enable_ensemble_distance = True` |
| Narrative config | `ens_fuzzy_narrative_v10` (7-tier fallback, shortcircuit cap=0.20) | `EnsembleDistanceConfig` |
| Hebbian boost | ENABLED (scale=0.10, cap=0.05) | `R2Config.enable_hebbian_boost = True` |
| Thread purity | ENABLED (M6) | `R2Config.enable_thread_purity_correction = True` |
| Same-thread merge | ENABLED (cosine >= 0.70, gap < 4h, purity >= 80%) | `R2Config.enable_same_thread_merge = True` |
| Cross-batch reconciliation | Two-tier (K1 first, cosine cascade second) | `R2Config.enable_episode_matching = True` |
| Scene segmentation | ENABLED (gap=4h, overnight=8h, max=35, min=3) | `R2Config.enable_scene_segmentation = True` |
| Centroid strategy | RECENCY_EXP (M4) | `R2Config.centroid_strategy = "recency_exp"` |
| Multi-centroid | ENABLED: best_of_all (primary + start + end + peak + anchor) | `R2Config.enable_multi_centroid = True` |
| Coherence scoring | ENABLED alongside silhouette (M4) | `R2Config.enable_coherence = True` |
| EpsAdjuster | ENABLED (silhouette_target=0.5) | `R2Config.enable_adaptive_eps = True` |
| Structured summaries | ENABLED (M9 Epic 9.11) | `R2Config.enable_structured_summaries = True` |
| Embedding regen on EXTEND | ENABLED (M9 Epic 9.12) | `R2Config.enable_embedding_regen = True` |

The full config test additionally verifies:

1. **Multi-batch processing**: 1,360 events processed in ~5 batches of 300 (research-proven batch size).
2. **Cross-batch episode growth**: Episodes that span multiple batches are correctly extended via two-tier reconciliation.
3. **Episode versioning**: At least one EVOLVE action triggers during multi-batch processing.
4. **Structured summaries persisted**: st_epi rows contain valid structured JSON in episode_summary.
5. **Scenario parity**: must_link >= 0.8 on at least 7/8 scenarios after full multi-batch processing.
6. **No duplicate episodes**: Zero duplicate source_events_json in st_epi.
7. **No orphan events**: All 1,360 events accounted for (in episodes or classified as noise with reason).
8. **Embedding freshness**: Extended episodes have embeddings reflecting all member events.

---

### Epic 8.1: Test Fixture Infrastructure

**Repo Status**: OPEN
**Dependency**: None — fixture infrastructure can be built before M2-M7 implementation.

#### Epic 8.1 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 8.1.1 Create fixture directory structure | OPEN | Create `tests/k0/pipelines/p03/fixtures/r2_integration/` with subdirectories for events, embeddings, baselines, and db fixtures. |
| 8.1.2 Build fixture generation script | OPEN | `generate_r2_fixtures.py` runs the research pipeline and snapshots output at each stage boundary. Stores as JSON/numpy. |
| 8.1.3 Create event fixture loader | OPEN | `R2IntegrationFixtures` class that loads events, embeddings, and baselines. Provides `get_events()`, `get_embeddings()`, `get_baseline(stage)`. |
| 8.1.4 Create DB fixture setup | OPEN | Test helper that populates st_hipp_events + st_vec from fixture data within a transaction. Rolls back after test. |
| 8.1.5 Create scenario definition fixtures | OPEN | Port the 8 research scenarios to structured test fixtures with must_link/must_separate event groups. |

### Epic 8.2: Port Scenario Evaluation Framework

**Repo Status**: OPEN
**Dependency**: None — can be built independently.

#### Epic 8.2 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 8.2.1 Create ScenarioEvaluator | OPEN | Create `k0/modules/consolidation/algorithms/scenario_evaluator.py` with `ScenarioEvaluator` class. Operates on `List[EpisodeCluster]` or st_epi query results. |
| 8.2.2 Define scenario data schema | OPEN | `ScenarioDefinition` dataclass with scenario_id, must_link groups, must_separate groups, description. |
| 8.2.3 Port 8 research scenarios | OPEN | Convert research scenario definitions to structured `ScenarioDefinition` fixtures. Map conversation turns to event IDs from the fixture corpus. |
| 8.2.4 Implement must_link scoring | OPEN | For each must_link group, check all events share the same episode. Score = fraction of groups fully linked. |
| 8.2.5 Implement must_separate scoring | OPEN | For each pair of must_separate groups, check zero episode overlap. Pairwise contamination = 0 -> score 1.0. |
| 8.2.6 Implement overall scoring | OPEN | Weighted: 0.45 *must_link + 0.45* must_separate + 0.10 * mean_purity. |
| 8.2.7 Write tests for the evaluator itself | OPEN | Test the scoring logic with hand-crafted cluster assignments. Verify edge cases: single-event episodes, all-noise, partial overlap. |

### Epic 8.3: Window-2 Adjacent Pair Integration Tests

**Repo Status**: OPEN
**Dependency**: Epic 8.1 (fixtures), relevant M2-M7 components implemented.

#### Epic 8.3 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 8.3.1 Test A->B: Load to Split | OPEN | Load fixture events, run through EpisodeSplitter. Verify sequence count and boundaries match research baseline. |
| 8.3.2 Test B->C: Split to Cluster | OPEN | Take fixture sequences, run through EpisodicHDBSCAN with 6D ensemble config. Verify cluster count and noise ratio within 20% of research. |
| 8.3.3 Test C->D: Cluster to Purity | OPEN | Take HDBSCAN output clusters, run through ThreadPurityCorrector. Verify 0% cross-thread contamination. Verify split count matches research. |
| 8.3.4 Test D->E: Purity to Merge | OPEN | Take purity-corrected clusters, run through SameThreadMerger. Verify merged cluster count within 20% of research. Verify largest cluster size >= 30. |
| 8.3.5 Test E->F: Merge to Centroid+Quality | OPEN | Take merged clusters, run CentroidCalculator + CoherenceScorer + SecondaryCentroidSelector. Verify centroid embeddings are 768-dim, coherence scores in [0,1], multi-centroid metadata populated. |
| 8.3.6 Test F->G: Quality to Matching | OPEN | Take scored EpisodeCluster objects, populate st_epi with "previous batch" fixtures, run episode matching. Verify REINFORCE/EXTEND/EVOLVE decisions are assigned correctly. |
| 8.3.7 Test G->H: Matching to Summary | OPEN | Take matched episodes with lifecycle decisions, run StructuredSummaryGenerator. Verify structured JSON output with schema_version, thread_distribution, per-event records. |
| 8.3.8 Test H->I: Summary to Reconciliation | OPEN | Take episodes with structured summaries, run R3 ReconciliationEngine. Verify reconciliation actions match expected (REINFORCE/EXTEND/EVOLVE/CREATE). |
| 8.3.9 Test I->J: Reconciliation to Write | OPEN | Take reconciled events, run R6 TruthWriteAssembler + R7 EpisodicLayerWriter. Verify st_epi rows created/updated correctly. Transaction rollback after verification. |
| 8.3.10 Test J->K: Write to Evaluation | OPEN | Read st_epi rows written in previous step, run ScenarioEvaluator. Verify scenario scores computable from persisted data. |

### Epic 8.4: Window-3 Triple Integration Tests

**Repo Status**: OPEN
**Dependency**: Epic 8.3 (pair tests must pass first).

#### Epic 8.4 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 8.4.1 Test A->B->C: Load to Cluster | OPEN | Full data acquisition through clustering. Verify labeled clusters with member events. |
| 8.4.2 Test B->C->D: Split to Purity | OPEN | Sequences cluster and impure clusters split. All output clusters are thread-pure. |
| 8.4.3 Test C->D->E: Cluster to Merge | OPEN | HDBSCAN -> purity -> merge. Output episodes are pure and consolidated. |
| 8.4.4 Test D->E->F: Purity to Quality | OPEN | Pure merged clusters get RECENCY_EXP centroids and coherence scores. |
| 8.4.5 Test E->F->G: Merge to Matching | OPEN | Merged episodes with centroids matched against existing st_epi. Lifecycle decisions assigned. |
| 8.4.6 Test F->G->H: Quality to Summary | OPEN | Scored episodes with lifecycle decisions get rich structured summaries. |
| 8.4.7 Test G->H->I: Matching to Reconciliation | OPEN | Lifecycle decisions flow through summary into reconciliation. Action routing verified. |
| 8.4.8 Test H->I->J: Summary to Write | OPEN | Reconciled episodes with summaries written atomically to st_epi. EXTEND/EVOLVE SQL correct. |
| 8.4.9 Test I->J->K: Reconciliation to Evaluation | OPEN | Written episodes pass scenario evaluation with must_link >= 0.8. |

---

### Epic 8.5: Window-4 and Window-5 Integration Tests

**Repo Status**: OPEN
**Dependency**: Epic 8.4.

#### Epic 8.5 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 8.5.1 Window-4 tests (8 tests) | OPEN | M8-W4-01 through M8-W4-08 as defined in the test matrix. Each exercises 3 handoff boundaries. |
| 8.5.2 Window-5 tests (7 tests) | OPEN | M8-W5-01 through M8-W5-07 as defined in the test matrix. Each exercises 4 handoff boundaries. |

---

### Epic 8.6: Extended Window and Full Chain Integration Tests

**Repo Status**: OPEN
**Dependency**: Epics 8.3-8.5.

#### Epic 8.6 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 8.6.1 Window-6 tests (6 tests) | OPEN | M8-W6-01 through M8-W6-06 as defined in the test matrix. |
| 8.6.2 Window-7 tests (5 tests) | OPEN | M8-W7-01 through M8-W7-05 as defined in the test matrix. |
| 8.6.3 Window-8 tests (2 tests) | OPEN | M8-W8-01 through M8-W8-02 as defined in the test matrix. |
| 8.6.4 Window-9 test (1 test) | OPEN | M8-W9-01: Load through reconciliation. Nearly-complete pipeline. |
| 8.6.5 Window-10 test (1 test) | OPEN | M8-W10-01: Load through truth write. Complete pipeline minus scenario eval. |
| 8.6.6 Full chain test M8-FULL-01 | OPEN | A->B->C->D->E->F->G->H->I->J->K. 1,360 events, 14 batches, full production config, all M2-M7 features enabled, scenario parity with research. |

| Max episode size | >= 30 events | 47 events |
| Thread purity (3+ event episodes) | 100% | 100% |
| Scenario must_link (7/8 scenarios) | >= 0.8 | 1.0 |
| Scenario must_separate (all) | >= 0.9 | 1.0 |
| Duplicate episodes | 0 | 0 |
| Orphan events | <= 5% | ~0% |
| Structured summary validity | 100% parseable JSON with schema_version | N/A |
| Extended episodes exist | >= 1 episode with version > 1 | N/A |
| Embedding freshness | extended episode embeddings differ from original | N/A |
| Cross-batch convergence (per-thread) | For each thread with 3+ episodes in research, production EXTEND chain produces <= 2 episodes covering the same events | Research: 1 episode per thread |
| maya_fears convergence | <= 30 episodes (vs 183 today), largest >= 30 events (vs 8 today) | Research: 22 episodes, largest 47 events |

#### Cross-Batch Convergence Proof (M8-CONV-01)

This is the hardest production-specific assertion. The research pipeline sees all 1,360 events at
once and produces globally optimal clusters. Production sees them in 14 batches of ~100 and must
reach the same result incrementally via EXTEND.

The convergence proof requires:

1. **Per-thread episode count**: For every `narrative_thread_id` that the research pipeline assigns
   to 3 or more episodes, production's cross-batch EXTEND chain must produce a single episode
   (or at most 2) covering the same events. If production produces 3+ episodes for a thread that
   research merges into 1, the EXTEND mechanism is failing to accumulate across batches.

2. **Event coverage**: For each research episode with >= 10 events, at least 80% of those events
   must appear in a single production episode (not scattered across multiple small episodes).

3. **Centroid drift bound**: After the final batch, the production centroid for an extended episode
   must have cosine similarity >= 0.90 with the research centroid for the corresponding episode.
   If centroids drift too far, subsequent batches will fail to match and the accumulation chain
   breaks.

4. **Monotonic growth**: For threads that span 3+ batches, the episode's `source_events_json`
   length must grow monotonically across batches (never shrink, never stall for 2+ consecutive
   batches when events from that thread are being processed).

The convergence proof is the gate that determines whether the batch-100 architecture can
replicate global single-pass quality. If M8-CONV-01 fails, the batch size or EXTEND matching
thresholds must be revisited before M8 can exit.

---

### Epic 8.7: Cross-Batch Lifecycle Integration Tests

**Repo Status**: OPEN
**Dependency**: Epics 8.1-8.2, M6-M7 implementation.

These tests specifically exercise the batch-100 architecture with EXTEND/EVOLVE lifecycle:

#### Epic 8.7 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 8.7.1 Test two-batch EXTEND | OPEN | Batch 1: create episode from events 1-50 of maya_fears. Batch 2: events 51-100 should EXTEND the batch-1 episode (centroid sim >= 0.60, same thread). Verify source_events_json grows, temporal bounds extend, embedding regenerates. |
| 8.7.2 Test three-batch accumulation | OPEN | Episode grows across 3 consecutive batches. After batch 3: event count = sum of all three batch contributions. Version >= 3. |
| 8.7.3 Test EVOLVE on thread shift | OPEN | Batch 1: "casual dinner" episode. Batch 2: events shift to "relationship conflict" (same participants, different thread, sim 0.40-0.59). Verify: old episode SUPERSEDED, new episode created with supersedes_id, old episode excluded from future matching. |
| 8.7.4 Test REINFORCE vs EXTEND boundary | OPEN | Events at 0.85+ sim get REINFORCE (lightweight update). Events at 0.60-0.84 sim get EXTEND (full update with summary regen). Verify different update behavior. |
| 8.7.5 Test no cross-thread EXTEND | OPEN | Two episodes with sim >= 0.60 but DIFFERENT dominant threads. Verify they remain separate. Thread match is required for EXTEND. |
| 8.7.6 Test EXTEND embedding freshness | OPEN | After EXTEND, query st_vec for the episode's embedding. Verify it differs from the pre-EXTEND embedding. Verify cosine similarity between old and new embedding is < 1.0 (changed). |
| 8.7.7 Test structured summary update on EXTEND | OPEN | After EXTEND, verify episode_summary JSON contains events from BOTH batches. thread_distribution reflects combined events. event_count matches total. |

---

### Epic 8.8: Research Parity Regression Test

**Repo Status**: OPEN
**Dependency**: All other M8 epics.

This is the final capstone test that gates M8 completion:

#### Epic 8.8 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 8.8.1 Create parity comparison harness | OPEN | Test that runs BOTH pipelines (research and production) on the same 1,360 events and compares output side-by-side. |
| 8.8.2 Episode count parity | OPEN | Assert production episode count within 30% of research (262). Cross-batch extension may produce slightly different counts. |
| 8.8.3 Thread purity parity | OPEN | Assert 100% thread purity in production (matching research 100%). |
| 8.8.4 Scenario score parity | OPEN | Assert production scenario scores within 0.2 of research scores on all 8 scenarios. |
| 8.8.5 Episode size distribution parity | OPEN | Assert max episode size >= 30 events. Assert mean episode size >= 4 events. Assert weak episodes (1-2 events) <= 20%. |
| 8.8.6 Maya_fears parity | OPEN | Assert maya_fears episodes <= 30 (research: 22). Assert largest maya_fears episode >= 30 events (research: 47). Assert consecutive mergeable pairs < 10% (research: N/A, already merged). |
| 8.8.7 Generate parity report | OPEN | Output a comparison table (production vs research) for inclusion in CI artifacts. |

---

### Milestone 8 Test File Organization

```
tests/k0/pipelines/p03/
    fixtures/
        r2_integration/
            events/
                life_events.jsonl           # 1,360 event corpus
            embeddings/
                embeddings_768.npy          # pre-computed UltraBERT vectors
            baselines/
                stage_A_output.json         # research baseline per stage
                stage_B_output.json
                ...
                stage_K_output.json
            scenarios/
                scenario_definitions.json   # 8 scenario definitions
            db/
                st_epi_fixtures.sql         # pre-existing episodes for matching tests
        generate_r2_fixtures.py             # fixture generation script

    test_r2_integration_w2.py               # 10 window-2 tests (Epic 8.3)
    test_r2_integration_w3.py               # 9 window-3 tests (Epic 8.4)
    test_r2_integration_w4w5.py             # 15 window-4+5 tests (Epic 8.5)
    test_r2_integration_w6plus.py           # 15 window-6+ tests (Epic 8.6)
    test_r2_integration_lifecycle.py         # 7 cross-batch lifecycle tests (Epic 8.7)
    test_r2_integration_parity.py           # 7 parity regression tests (Epic 8.8)
    test_r2_scenario_evaluator.py           # scenario evaluator unit tests (Epic 8.2)
    conftest.py                             # shared fixtures, DB setup, R2IntegrationTestBase
```

### Milestone 8 Execution Order

1. **Epic 8.1** (fixture infrastructure) FIRST — required by all other epics.
2. **Epic 8.2** (scenario evaluator) SECOND — needed for K-stage in all windows.
3. **Epic 8.3** (window-2 pairs) THIRD — smallest tests, catch interface mismatches early.
4. **Epic 8.4** (window-3 triples) FOURTH — catch multi-boundary issues.
5. **Epic 8.5** (window-4+5) FIFTH — deeper chain validation.
6. **Epic 8.7** (cross-batch lifecycle) SIXTH — specialized EXTEND/EVOLVE tests.
7. **Epic 8.6** (extended windows + full chain) SEVENTH — longest tests, highest value.
8. **Epic 8.8** (research parity regression) LAST — capstone gate.

### Milestone 8 Exit Criteria

- All 50 sliding window integration tests pass with NO mocks.
- Full chain test (M8-FULL-01) achieves research parity thresholds.
- Scenario evaluator ported and validated against research scoring.
- Cross-batch lifecycle tests prove EXTEND/EVOLVE/REINFORCE work across batch boundaries.
- Research parity regression test produces side-by-side comparison report.
- Test fixtures cover all 1,360 events with pre-computed embeddings and stage baselines.
- All tests use real DB transactions (test schema with rollback), real algorithms, real embeddings.
- CI can run the full M8 suite (fixture loading + all 50 tests) in under 30 minutes.

### Milestone 8 Completion Verification

| Area | Verification Requirement |
| ---- | ------------------------ |
| Test count | All 50 integration tests present and passing: 10 W2 + 9 W3 + 8 W4 + 7 W5 + 15 W6+ + 1 FULL |
| No mocks | Zero mock objects in any M8 test file. Real components, real DB, real embeddings. |
| Fixtures | Event corpus, embedding vectors, stage baselines, and scenario definitions all present in fixture directory |
| Scenario evaluator | ScenarioEvaluator class exists, handles both in-memory and DB modes, scores match research on fixture data |
| Cross-batch | 7 lifecycle tests prove EXTEND grows episodes, EVOLVE versions episodes, REINFORCE is lightweight |
| Research parity | M8-FULL-01 passes: episode count within 30%, 100% purity, must_link >= 0.8 on 7/8 scenarios |
| Parity report | Automated comparison table (production vs research) generated as CI artifact |
| Performance | Full M8 suite completes in under 30 minutes on CI |
| Full config | M8-FULL-01 runs with ALL M2-M7 features enabled simultaneously |

---

## MILESTONE 9: Universal Reconciliation + Lifecycle (P6)

**Milestone Status**: RESEARCH COMPLETE (2025-07-10)
**Execution Gate**: Start after Milestone 6 completes.
**Priority**: HIGH — Absorbs M7 lifecycle mechanics (EXTEND, EVOLVE, structured summaries,
embedding regeneration, observability) into the universal framework.

### Milestone 9 Research Summary

The two-tier reconciliation engine is fully proven in `poc/r2_phase_research/reconciliation.py`.
Scene segmentation is proven in `poc/r2_phase_research/scene_segmentation.py`.

**Two-Tier Reconciliation Architecture** (proven on 1,360 events, 275 reconciliation decisions):

| Tier | Trigger | Actions | Threshold | Research Result |
| ---- | ------- | ------- | --------- | --------------- |
| Tier 1 (K1 signals) | `correction_signal=true` | EVOLVE | N/A (checked first) | 0 fires in corpus (K1 signals not yet populated) |
| Tier 1 (K1 signals) | `contradiction_signal=true` | CONTRADICT | N/A (checked first) | 0 fires in corpus |
| Tier 2 (similarity) | cosine >= 0.85 + same_thread | REINFORCE | reinforce_threshold=0.85 | Majority action |
| Tier 2 (similarity) | cosine >= 0.60 + same_thread | EXTEND | extend_threshold=0.60 | Episode growth across batches |
| Tier 2 (similarity) | cosine < 0.60 OR different thread | CREATE | N/A | New episode creation |

**Key findings**:

- EVOLVE threshold 0.40 is dead code: zero fires in 275 reconciliations (should be removed)
- AccumulatedEpisode tracks importance via `reinforce_importance_boost=0.10` per REINFORCE
- Evolve chains tracked via `supersedes_id` for versioning
- Batch size is dominant lever: bs300 sweet spot (CogQ=0.7293), not threshold tuning

**Scene Segmentation** (Phase 9, proven on 105 scenes from 9 mega-episodes):

| Parameter | Value | Effect |
| --------- | ----- | ------ |
| scene_gap_hours | 4.0 | Primary temporal split threshold |
| overnight_gap_hours | 8.0 | Forced split across overnight boundaries |
| max_scene_events | 35 | Cap for human-cognitive episode size |
| min_scene_events | 3 | Minimum viable scene |
| absorb_max_events | 4 | Micro-fragment absorption threshold |
| absorb_max_gap_hours | 6.0 | Temporal proximity for absorption |
| absorb_min_similarity | 0.50 | Semantic threshold for absorption |

Results: 9 mega-episodes split into 105 scenes, 180 micro-fragments absorbed, 64% human-scale episodes.
CogQ drops from 0.7293 (Phase 8) to 0.7117 (Phase 9) — honest trade for human-scale episodes.

### Milestone 9 K1 Signal Integration Note (2026-03-08)

R2 research (Section 15, `R2_RESEARCH_FINAL.md`) established that EVOLVE and CONTRADICT cannot
be detected by cosine similarity. These decisions require K1 LLM conversational signals. The
M9 universal reconciliation framework must therefore implement a **two-tier decision model**:

1. **K1-signaled decisions (checked first)**: If the incoming atom carries `correction_signal =
   true`, the framework returns EVOLVE regardless of similarity score. If the atom carries
   `contradiction_signal = true`, the framework returns CONTRADICT. P03 is a signal processor
   for these decisions, not a signal detector.

2. **K0-computed decisions (checked second)**: REINFORCE (>0.85), EXTEND (0.60-0.85), CREATE
   (<0.60) are determined by embedding similarity via the standard threshold cascade.

3. **Timer-based decisions (separate sweep)**: PRUNE is driven by temporal decay, independent
   of incoming signals.

This does NOT change the M9 architecture (5 layers, 10 epics). It changes the trigger mechanism
for two of six reconciliation actions. The `ReconciliationFramework.reconcile()` method checks
K1 correction/contradiction metadata BEFORE computing embedding similarity. The
`WriteDecisionRouter` EVOLVE and CONTRADICT write paths remain unchanged.

**Signal pipeline status (2026-03-08)**: The K1 correction signal pipeline is fully implemented
end-to-end (M7 Issue 7.2.0 DONE). K1 Memory Writer atom v2.2 -> Bridge envelope -> P02 M13 ->
st_hipp_events (migration 0085) -> P03 R0 -> P03EventState. The `ReconciliationCandidate` type
defined in M9 Epic 9.4 should read these fields from `P03EventState` (already populated by R0).
M9 does NOT need to re-implement the signal pipeline — it only needs to check the fields in the
Tier 1 decision path.

### Milestone 7 Absorption Note (2026-03-08)

Milestone 7 was removed and absorbed into Milestone 9. See the M7 tombstone section above for
the full absorption map. Key inheritance:

- **Signal pipeline (7.2.0)**: DONE. ReconciliationCandidate reads K1 correction signals from
  P03EventState. M9 framework consumes these signals via Tier 1 decision path (Epic 9.4.5).
- **EXTEND/EVOLVE layer methods**: Built as part of WriteDecisionRouter (Epic 9.5) and layer
  writer implementations, not as bespoke st_epi code.
- **Structured summaries**: Epic 9.11 (absorbed from M7 7.3).
- **Embedding regeneration**: Epic 9.12 (absorbed from M7 7.4).
- **Lifecycle observability**: Epic 9.13 (absorbed from M7 7.5).

### Milestone 9 Root Cause Inventory

Five root causes explain why the dossier principle is not universally implemented:

**RC-0: ReconciliationEngine is embedding-only**

`ReconciliationEngine._find_candidates()` delegates to `TruthQueryService.find_candidates()` which
queries via embedding cosine similarity. This works for st_epi and st_sem (both have embeddings) but
fails for st_kg_dom (identity is `entity_type:canonical_name`, not embedding), st_kg_edges (identity
is `source:target:relation_type`), and st_social (identity is participant pair). KG entities need
KEY-BASED matching, not embedding matching. The engine has no key-based match path.

**RC-1: TruthQueryService layer registry is incomplete**

`LAYER_PK_COLUMNS` dict at `truth_query_service.py` L39 covers only 5 layers (st_epi, st_sem,
st_procedural, st_social, st_prospective). Missing: st_kg_dom, st_kg_edges, st_vec. The registry
is also scattered — `LAYER_CONFIDENCE_COLUMNS`, `DECAY_LAYERS`, and `LAYER_*` constants in
`staged_writes.py` are separate duplicated registries.

**RC-2: No generic truth read syscall exists**

Every truth layer has bespoke syscalls: `episodes_query`, `semantic_schema_query`,
`procedural_memory_query`, `kg_entities_query`, `kg_entities_lookup`, `kg_edges_query`,
`kg_edges_lookup`, `kg_candidates_fuzzy_query`. Each has different parameter shapes, different
return types, different filtering logic. Meanwhile `TruthQueryService` bypasses syscalls entirely
with raw SQL. There is no "query any truth layer for reconciliation candidates" syscall.

**RC-3: Write assembly is per-layer hardcoded**

`TruthWriteAssembler` has 12+ methods, each building `StagedWrite` objects with layer-specific
column mappings. Adding a new layer or changing the reconciliation routing requires editing
multiple methods. The decision-to-write mapping should be data-driven (layer registry tells you
which columns to UPDATE for EXTEND, which columns to set for EVOLVE), not code-driven.

**RC-4: No identity strategy abstraction**

"Does this new thing match that existing thing?" is answered differently per layer:

- st_epi: embedding cosine similarity + thread match
- st_sem: embedding cosine similarity + pattern_type match
- st_kg_dom: entity_type + canonical_name exact/fuzzy match
- st_kg_edges: source_entity + target_entity + relation_type compound key
- st_social: participant pair match
- st_procedural: routine name + time pattern match
- st_prospective: intention description similarity

Each layer needs its own "identity function" but the FRAMEWORK (query → compare → threshold →
decide) is identical. Currently these identity functions are scattered across R2 (_match_events),
R3 (TruthQueryService), and R4 (entity lookup + fuzzy query) with no shared abstraction.

### Milestone 9 Architecture

#### Layer 1: Truth Layer Registry

A single source of truth for all truth table metadata. Replaces the scattered constants in
`truth_query_service.py`, `staged_writes.py`, and per-phase configs.

```
TruthLayerSpec:
    layer_name: str                    # "st_epi", "st_kg_dom", etc.
    table_name: str                    # actual DB table
    pk_column: str                     # "episode_id", "entity_id", etc.
    embedding_fk: Optional[str]        # "embedding_id" or None (st_kg_edges has no embedding)
    confidence_column: Optional[str]   # "confidence_score", "confidence", None
    status_column: Optional[str]       # "lifecycle_status", "archival_status", None
    active_status_value: str           # "ACTIVE"
    supersedes_column: Optional[str]   # "supersedes_id" for versioning
    version_column: Optional[str]      # "version" for optimistic locking
    observation_count_column: Optional[str]  # "observation_count"
    identity_columns: List[str]        # key columns for identity match
    temporal_columns: Optional[Tuple[str, str]]  # (start_col, end_col)
    supports_embedding_match: bool     # True for st_epi, st_sem; False for st_kg_edges
    supports_key_match: bool           # True for st_kg_dom, st_kg_edges; False for st_epi
```

Registered layers (all 8 truth tables + st_vec):

| Layer | PK | Embedding FK | Identity Columns | Embedding Match | Key Match |
| ----- | -- | ------------ | ---------------- | --------------- | --------- |
| st_epi | episode_id | embedding_id | narrative_thread_id | Yes | No |
| st_sem | semantic_id | embedding_id | pattern_type | Yes | No |
| st_procedural | routine_id | embedding_id | routine_name, time_pattern | Yes | Yes |
| st_social | relationship_id | embedding_id | participant_a, participant_b | Yes | Yes |
| st_prospective | intention_id | embedding_id | intention_type | Yes | No |
| st_kg_dom | entity_id | embedding_id | entity_type, canonical_name | Yes | Yes |
| st_kg_edges | edge_id | None | source_entity_id, target_entity_id, relation_type | No | Yes |
| st_vec | embedding_id | (self) | embedding_model, source_layer, source_id | No | Yes |

#### Layer 2: Identity Strategy Interface

Each truth layer registers an identity strategy that answers: "Is this candidate the same entity
as this existing record?"

```
class IdentityStrategy(Protocol):
    def compute_identity_score(
        self,
        candidate: ReconciliationCandidate,
        existing: TruthRecord,
    ) -> IdentityResult:
        """
        Returns:
          - match_score: float [0, 1] — overall identity confidence
          - match_type: KEY_MATCH | EMBEDDING_MATCH | HYBRID_MATCH | NO_MATCH
          - identity_reason: str — human-readable explanation
        """
        ...
```

Layer-specific implementations:

| Layer | Strategy | Logic |
| ----- | -------- | ----- |
| st_epi | EpisodicIdentity | cosine_sim(embedding) * thread_match_bonus(0.0 or 0.15) |
| st_sem | SemanticIdentity | cosine_sim(embedding) * pattern_type_match_bonus |
| st_kg_dom | EntityIdentity | exact key match (type:name) → 1.0; fuzzy name → ILIKE score; fallback embedding |
| st_kg_edges | EdgeIdentity | compound key match (source:target:type) → 1.0; no embedding fallback |
| st_social | SocialIdentity | participant pair match → 1.0; embedding similarity as tiebreaker |
| st_procedural | ProceduralIdentity | routine name + time pattern key match → 1.0; embedding fallback |
| st_prospective | ProspectiveIdentity | cosine_sim(embedding) only |

The key insight: key-based layers (st_kg_dom, st_kg_edges) get score 1.0 on exact match —
they skip the threshold cascade and go straight to REINFORCE or EXTEND based on whether the
record content has changed. Embedding-based layers (st_epi, st_sem) use the standard similarity
thresholds.

#### Layer 3: Universal Truth Query Syscall

A single new syscall that replaces the 8+ bespoke read syscalls for reconciliation purposes:

```
syscall: truth_candidates_query
    capability: truth.reconcile.read
    parameters:
        target_layer: str           # "st_epi", "st_kg_dom", etc.
        space_id: UUID
        tenant_id: UUID
        embedding: Optional[List[float]]   # for similarity search
        identity_key: Optional[Dict]       # for key-based lookup
        top_k: int = 10
        min_similarity: float = 0.35
        time_window_days: Optional[int] = 30
        active_only: bool = True
    returns: List[TruthCandidate]
```

This syscall uses the `TruthLayerSpec` registry to construct the correct SQL dynamically:

- If `embedding` provided AND layer `supports_embedding_match`: pgvector `<=>` operator search
- If `identity_key` provided AND layer `supports_key_match`: WHERE clause on identity columns
- If both provided: HYBRID — key match first (fast), embedding tiebreaker (slow)
- Respects `active_status_value` filter and `time_window_days` temporal filter

The existing bespoke syscalls (`episodes_query`, `kg_entities_lookup`, etc.) remain for
non-reconciliation use cases (R5 dream loading, K1 query serving). The new syscall is
purpose-built for the reconciliation read path.

#### Layer 4: Unified Reconciliation Framework

The core machine. Replaces the current pattern where each phase has its own matching logic.

**Two-tier decision model** (K1 signals checked before K0 similarity):

```
class ReconciliationFramework:
    def __init__(
        self,
        layer_registry: TruthLayerRegistry,
        identity_strategies: Dict[str, IdentityStrategy],
        config: ReconciliationConfig,
    ):
        ...

    async def reconcile(
        self,
        candidate: ReconciliationCandidate,
        target_layer: str,
        space_id: UUID,
        tenant_id: UUID,
    ) -> ReconciliationResult:
        """
        Universal reconciliation: one method, any layer.

        TIER 1 — K1-signaled decisions (checked first):
        1a. If candidate.correction_signal: return EVOLVE
        1b. If candidate.contradiction_signal: return CONTRADICT

        TIER 2 — K0-computed decisions (embedding similarity):
        2. Look up TruthLayerSpec from registry
        3. Call truth_candidates_query syscall
        4. Apply layer's IdentityStrategy to score each candidate
        5. Apply threshold cascade on best score (0.85/0.60)
        6. Return decision + pre-built StagedWrite
        """
        ...

    async def reconcile_batch(
        self,
        candidates: List[ReconciliationCandidate],
        target_layer: str,
        space_id: UUID,
        tenant_id: UUID,
    ) -> List[ReconciliationResult]:
        """Batch version with query deduplication."""
        ...
```

**ReconciliationCandidate** — the universal input:

```
ReconciliationCandidate:
    candidate_id: str               # caller-assigned ID
    embedding: Optional[ndarray]    # 768-dim vector (or None for key-only layers)
    identity_key: Optional[Dict]    # key columns for key-based match
    record_data: Dict               # full column payload for INSERT/UPDATE
    source_phase: str               # "R2", "R4", "R5"
    source_event_ids: List[str]     # provenance
    observation_context: Optional[ObservationContext]
    # K1 correction signal fields (from Memory Writer atom)
    correction_signal: bool = False  # True if K1 LLM detected a correction
    contradiction_signal: bool = False  # True if K1 LLM detected a contradiction
    supersedes_concept: Optional[str] = None  # what truth is being replaced
    correction_source: Optional[str] = None  # "user_explicit", "user_implicit", "context_change"
    session_context_id: Optional[str] = None  # links back to conversation
```

**ReconciliationResult** — the universal output:

```
ReconciliationResult:
    action: ReconciliationAction       # REINFORCE/EXTEND/EVOLVE/CREATE/CONTRADICT/PRUNE
    target_layer: str                  # "st_kg_dom"
    target_record_id: Optional[str]    # existing record PK (None for CREATE)
    identity_score: float              # from IdentityStrategy
    similarity_score: float            # embedding cosine (0.0 for key-only)
    confidence: float                  # Bayesian posterior
    reason: str                        # human-readable
    staged_write: StagedWrite          # ready for R7 — INSERT, UPDATE, or ARCHIVE
    contradiction_details: Optional[Dict]  # for CONTRADICT → P06 active learning
```

The `staged_write` field is the key innovation. The framework produces the complete `StagedWrite`
object using the layer registry metadata — the caller does not need to know column mappings.

#### Layer 5: Generic Write Decision Router

Replaces the 12+ `assemble_*_writes()` methods with a single data-driven router:

```
class WriteDecisionRouter:
    def build_staged_write(
        self,
        decision: ReconciliationResult,
        layer_spec: TruthLayerSpec,
        candidate: ReconciliationCandidate,
        existing_record: Optional[TruthRecord],
    ) -> StagedWrite:
        """
        Given a reconciliation decision, build the correct StagedWrite.

        CREATE  → StagedWrite.insert(record_data=candidate.record_data)
        REINFORCE → StagedWrite.update(
            record_id=existing.pk,
            record_data={
                observation_count_col: existing.observation_count + 1,
                last_observed_at: now(),
                version: existing.version + 1,
            },
            expected_version=existing.version,
        )
        EXTEND → StagedWrite.update(
            record_id=existing.pk,
            record_data=merge_records(existing, candidate, layer_spec),
            expected_version=existing.version,
        )
        EVOLVE → [
            StagedWrite.update(old.pk, {status: SUPERSEDED}),
            StagedWrite.insert(new_record, {supersedes_id: old.pk}),
        ]
        CONTRADICT → StagedWrite.insert(gap_record for P06 learning queue)
        PRUNE → StagedWrite.archive(existing.pk)
        """
```

The `merge_records()` function uses layer_spec to know which columns are appendable (JSON arrays),
which are min/max temporal, which are counters, and which are replaced. This replaces the
per-layer column-mapping tables currently hardcoded in each `assemble_*_writes()` method.

### Milestone 9 Scope And Phasing

#### What M9 Builds (Foundation)

| Component | Location | Purpose |
| --------- | -------- | ------- |
| TruthLayerRegistry | `k0/modules/consolidation/truth_layer_registry.py` | Single source of truth for all layer metadata |
| IdentityStrategy protocol + 7 implementations | `k0/modules/consolidation/identity/` | Per-layer identity matching |
| truth_candidates_query syscall | `k0/kernel/syscalls.py` | Unified truth read for reconciliation |
| ReconciliationFramework | `k0/modules/consolidation/reconciliation_framework.py` | One machine, any layer |
| WriteDecisionRouter | `k0/modules/consolidation/write_decision_router.py` | Decision → StagedWrite, data-driven |

#### What M9 Migrates (Phase Integration)

| Phase | Current | After M9 |
| ----- | ------- | -------- |
| R2 | Own episode matching logic | Calls `framework.reconcile(target_layer="st_epi")` |
| R3 | Own ReconciliationEngine + TruthQueryService | Calls `framework.reconcile_batch()` for all layers |
| R4 | Own entity matching + disambiguation | Calls `framework.reconcile(target_layer="st_kg_dom")` for entities, `framework.reconcile(target_layer="st_kg_edges")` for edges |
| R5 | No reconciliation on outputs | Calls `framework.reconcile()` for each dream output before staging |
| R6 | 12+ per-layer assemble methods | Receives `ReconciliationResult.staged_write` from phases. Orchestrates but does not assemble. |

#### What M9 Does NOT Change

- R0, R1, R8 — not producers, no reconciliation needed
- R7 — remains a blind executor of StagedWrites (correct by design)
- Existing syscalls — remain for non-reconciliation use cases (R5 context loading, K1 queries)
- ReconciliationAction enum — stays the same, used by the new framework
- StagedWrite — stays the same, produced by WriteDecisionRouter

### Epic 9.1: Truth Layer Registry

**Repo Status**: OPEN
**Dependency**: None — pure data structure, no runtime dependencies.

#### Epic 9.1 Problem Statement

Layer metadata is scattered across 4+ locations: `TruthQueryService.LAYER_PK_COLUMNS` (5 layers),
`TruthQueryService.LAYER_CONFIDENCE_COLUMNS` (5 layers), `TruthQueryService.DECAY_LAYERS` (5 layers),
`staged_writes.py` constants, and implicit knowledge in each `assemble_*_writes()` method. Adding
a new layer or changing column names requires editing multiple files.

#### Epic 9.1 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.1.1 Define TruthLayerSpec dataclass | OPEN | Frozen dataclass with all layer metadata fields. |
| 9.1.2 Create TruthLayerRegistry | OPEN | Registry class with `get(layer_name)`, `all_layers()`, `layers_with_embedding()`, `layers_with_key_match()`. Validates all specs at construction. |
| 9.1.3 Register all 8 truth layers + st_vec | OPEN | One `TruthLayerSpec` per table with complete metadata. |
| 9.1.4 Define per-layer merge rules | OPEN | For EXTEND: which columns are appendable (JSON arrays), which are temporal min/max, which are counters, which are replaced. Stored as part of `TruthLayerSpec`. |
| 9.1.5 Write tests | OPEN | Registry completeness tests: every truth table has a spec, every spec has valid column references. |

---

### Epic 9.2: Identity Strategy Interface And Implementations

**Repo Status**: OPEN
**Dependency**: Epic 9.1 (uses TruthLayerSpec for column references).

#### Epic 9.2 Problem Statement

"Is this new thing the same as that existing thing?" is answered differently per layer but the
current code has no shared abstraction. R2 uses cosine similarity + thread, R4 uses exact key match

- fuzzy ILIKE, R3 uses pure cosine via TruthQueryService. These need a common interface.

#### Epic 9.2 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.2.1 Define IdentityStrategy protocol | OPEN | Protocol with `compute_identity_score()` returning `IdentityResult(score, match_type, reason)`. |
| 9.2.2 Implement EpisodicIdentity | OPEN | Embedding cosine + thread match bonus. Port from R2 `_match_events_to_existing_episodes()`. |
| 9.2.3 Implement SemanticIdentity | OPEN | Embedding cosine + pattern_type match. Port from R3/TruthQueryService. |
| 9.2.4 Implement EntityIdentity | OPEN | Key match (type:name) → 1.0; fuzzy ILIKE → scaled score; embedding fallback. Port from R4 `AmbiguousEntityResolver`. |
| 9.2.5 Implement EdgeIdentity | OPEN | Compound key match (source:target:type) → 1.0. No embedding fallback. |
| 9.2.6 Implement SocialIdentity | OPEN | Participant pair match → 1.0; embedding tiebreaker. |
| 9.2.7 Implement ProceduralIdentity | OPEN | Routine name + time pattern key → 1.0; embedding fallback. |
| 9.2.8 Implement ProspectiveIdentity | OPEN | Embedding cosine only (intentions are free-text). |
| 9.2.9 Write tests | OPEN | Per-strategy unit tests with known inputs and expected scores. |

---

### Epic 9.3: truth_candidates_query Syscall

**Repo Status**: OPEN
**Dependency**: Epic 9.1 (registry drives SQL construction).

#### Epic 9.3 Problem Statement

No generic "query any truth layer for reconciliation candidates" syscall exists. 8+ bespoke
syscalls cover specific layers for specific use cases. `TruthQueryService` bypasses syscalls
entirely with raw SQL. A universal reconciliation framework needs one entry point for truth reads
that respects the kernel capability system.

#### Epic 9.3 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.3.1 Define truth.reconcile.read capability | OPEN | New capability in the kernel capability system for reconciliation truth reads. |
| 9.3.2 Implement truth_candidates_query syscall | OPEN | Accepts target_layer, embedding (optional), identity_key (optional), top_k, min_similarity, time_window_days, active_only. Uses TruthLayerRegistry to construct SQL. |
| 9.3.3 Embedding path: pgvector operator search | OPEN | For layers with embedding FK: JOIN st_vec, use `<=>` cosine distance operator, return top_k. Replaces the manual `struct.unpack` + Python cosine in current TruthQueryService. |
| 9.3.4 Key path: identity column WHERE clause | OPEN | For key-based layers: construct WHERE clause from identity_key dict + TruthLayerSpec.identity_columns. |
| 9.3.5 Hybrid path: key first, embedding tiebreak | OPEN | For layers supporting both: key match narrows candidates, embedding scores them. |
| 9.3.6 Write tests | OPEN | Per-layer integration test: insert known records, query via syscall, verify correct candidates returned with correct scores. |

---

### Epic 9.4: Unified Reconciliation Framework

**Repo Status**: OPEN
**Dependency**: Epics 9.1, 9.2, 9.3 (registry, strategies, syscall).

#### Epic 9.4 Problem Statement

The current `ReconciliationEngine` is tightly coupled to `TruthQueryService` and produces
decisions without `StagedWrite` outputs. Phases must separately map decisions to writes. The new
framework combines query + identity + threshold + write routing into a single `reconcile()` call.

#### Epic 9.4 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.4.1 Define ReconciliationCandidate input type | OPEN | Universal input: embedding, identity_key, record_data, source_phase, source_event_ids. |
| 9.4.2 Define ReconciliationResult output type | OPEN | Universal output: action, target_layer, target_record_id, identity_score, similarity_score, staged_write. |
| 9.4.3 Implement ReconciliationFramework.reconcile() | OPEN | Orchestrator: registry lookup → syscall query → identity strategy → threshold cascade → write router → return result. |
| 9.4.4 Implement ReconciliationFramework.reconcile_batch() | OPEN | Batch version with query deduplication: group candidates by layer, single query per layer, distribute results. |
| 9.4.5 Threshold cascade with identity-aware and K1-signal routing | OPEN | TIER 1: K1-signaled correction_signal → EVOLVE, contradiction_signal → CONTRADICT (checked BEFORE similarity). TIER 2: Key-match score 1.0 skips similarity thresholds → REINFORCE or EXTEND based on content change. Embedding-match uses standard 0.85/0.60. |
| 9.4.6 Preserve existing ReconciliationConfig | OPEN | Same K0 thresholds (0.85/0.60 for similarity), same Bayesian confidence, same timeout. EVOLVE/CONTRADICT cosine thresholds (0.40) removed in favor of K1 signal check. Config drives the framework. |
| 9.4.7 Write tests | OPEN | Integration tests: framework produces correct decisions for known scenarios across all layers. Regression test: framework matches current ReconciliationEngine output for st_sem. |

---

### Epic 9.5: Write Decision Router

**Repo Status**: OPEN
**Dependency**: Epics 9.1, 9.4 (registry for column metadata, framework for decisions).

#### Epic 9.5 Problem Statement

`TruthWriteAssembler` has 12+ hardcoded methods mapping decisions to StagedWrites per layer. Each
method has its own column mapping. Adding EXTEND support for a new layer means writing a new
method. The router must be data-driven: given a decision + layer spec + merge rules, produce the
correct StagedWrite without per-layer code.

#### Epic 9.5 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.5.1 Implement WriteDecisionRouter | OPEN | Takes ReconciliationResult + ReconciliationCandidate + existing TruthRecord + TruthLayerSpec → StagedWrite. |
| 9.5.2 CREATE → INSERT mapping | OPEN | record_data from candidate, layer_spec for column names. |
| 9.5.3 REINFORCE → UPDATE mapping | OPEN | Generic: increment observation_count, refresh last_observed_at, increment version with optimistic lock. Uses layer_spec column names. |
| 9.5.4 EXTEND → UPDATE mapping | OPEN | Uses merge_rules from layer_spec: appendable columns (jsonb union), temporal columns (LEAST/GREATEST), counter columns (increment), replaced columns (overwrite). |
| 9.5.5 EVOLVE → INSERT + UPDATE mapping | OPEN | UPDATE old record (set status to SUPERSEDED), INSERT new record (set supersedes_id to old PK). Uses layer_spec for supersedes_column and status_column. |
| 9.5.6 CONTRADICT → gap queue INSERT | OPEN | Creates StagedWrite for st_learning_queue with conflict details. Links to P06 active learning. |
| 9.5.7 PRUNE → ARCHIVE mapping | OPEN | Sets status to ARCHIVED or TOMBSTONED based on decay policy. |
| 9.5.8 Write tests | OPEN | Per-action per-layer: verify correct WriteOperation, correct column values, correct optimistic lock version. |

---

### Epic 9.6: Migrate R2 To Framework

**Repo Status**: OPEN
**Dependency**: Epics 9.4, 9.5 (framework and router must exist).

#### Epic 9.6 Problem Statement

R2 currently has its own episode matching logic at `r2_episodic_integrator.py` L1991-2070.
After M6/M7, this includes REINFORCE, EXTEND, and EVOLVE for st_epi. This must migrate to
calling `framework.reconcile(target_layer="st_epi")`.

#### Epic 9.6 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.6.1 Inject ReconciliationFramework into R2 | OPEN | Add framework as dependency to R2EpisodicIntegrator. |
| 9.6.2 Replace _match_events_to_existing_episodes | OPEN | After HDBSCAN + purity + merge produces clusters, call `framework.reconcile()` for each cluster against st_epi. |
| 9.6.3 Verify zero decision drift | OPEN | M8 test suite must pass identically. Same episodes created/extended/evolved. |
| 9.6.4 Remove R2-internal matching code | OPEN | Delete _query_existing_episodes(),_match_events_to_existing_episodes(), cosine_similarity helper. |
| 9.6.5 Write regression tests | OPEN | Before/after comparison: same input → same output. |

---

### Epic 9.7: Migrate R3 To Framework

**Repo Status**: OPEN
**Dependency**: Epics 9.4, 9.5.

#### Epic 9.7 Problem Statement

R3 uses `ReconciliationEngine` + `TruthQueryService` — the most complete current implementation.
Migrating R3 to the framework proves backward compatibility.

#### Epic 9.7 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.7.1 Inject ReconciliationFramework into R3 | OPEN | Replace ReconciliationEngine and TruthQueryService with framework. |
| 9.7.2 Map R3 reconcile_batch to framework.reconcile_batch | OPEN | R3 calls framework per event, framework queries all configured layers. |
| 9.7.3 Verify zero decision drift | OPEN | All existing R3 tests pass. All M8 tests pass. |
| 9.7.4 Deprecate old ReconciliationEngine | OPEN | Mark as deprecated after R3 migration proves framework parity. |
| 9.7.5 Deprecate old TruthQueryService | OPEN | Mark as deprecated after framework syscall proves parity. |
| 9.7.6 Write regression tests | OPEN | Before/after decision comparison on the standard 1,360-event corpus. |

---

### Epic 9.8: Migrate R4 To Framework

**Repo Status**: OPEN
**Dependency**: Epics 9.2 (EntityIdentity, EdgeIdentity), 9.4, 9.5.

#### Epic 9.8 Problem Statement

R4 has its own entity resolution pipeline (`AmbiguousEntityResolver`, `kg_entities_lookup`,
`kg_candidates_fuzzy_query`) producing binary CREATE_ENTITY / UPDATE_ENTITY. This must migrate
to the framework while preserving the fuzzy disambiguation capability.

#### Epic 9.8 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.8.1 Wire EntityIdentity strategy | OPEN | Wrap AmbiguousEntityResolver as the identity scoring function. Exact key → 1.0, fuzzy → scaled, embedding fallback. |
| 9.8.2 Wire EdgeIdentity strategy | OPEN | Compound key match for st_kg_edges. |
| 9.8.3 Replace R4 entity matching with framework | OPEN | `framework.reconcile(target_layer="st_kg_dom", identity_key={"entity_type": t, "canonical_name": n})`. |
| 9.8.4 Replace R4 edge matching with framework | OPEN | `framework.reconcile(target_layer="st_kg_edges", identity_key={"source": s, "target": t, "type": r})`. |
| 9.8.5 Enable EXTEND for entities | OPEN | Entity gains new aliases, new attributes → EXTEND (not binary UPDATE). |
| 9.8.6 Enable EVOLVE for entities | OPEN | Entity fundamentally changes (person changes name, place changes type) → EVOLVE with supersedes_id. |
| 9.8.7 Enable CONTRADICT for entities | OPEN | Conflicting attributes (age, type) → CONTRADICT → P06 active learning. |
| 9.8.8 Verify zero entity drift | OPEN | Same entity creation/update decisions on standard corpus. |
| 9.8.9 Write regression tests | OPEN | Before/after entity comparison. |

---

### Epic 9.9: Migrate R5 To Framework

**Repo Status**: OPEN
**Dependency**: Epics 9.4, 9.5, and Epics 9.6-9.8 proven (framework stable).

#### Epic 9.9 Problem Statement

R5 Dream Explorer outputs (routine candidates, insights, counterfactuals, intent signals, MCTS
scenarios) are passed to R6 with no reconciliation. Duplicates and contradictions are not caught.

#### Epic 9.9 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.9.1 Reconcile routine candidates against st_procedural | OPEN | Before staging: `framework.reconcile(target_layer="st_procedural")`. Duplicate routine → REINFORCE. Extended routine → EXTEND. |
| 9.9.2 Reconcile insights against st_sem | OPEN | Before staging: `framework.reconcile(target_layer="st_sem")`. Duplicate insight → REINFORCE. |
| 9.9.3 Reconcile counterfactuals against st_prospective | OPEN | Before staging: `framework.reconcile(target_layer="st_prospective")`. |
| 9.9.4 Reconcile intent signals against st_prospective | OPEN | Before staging: `framework.reconcile(target_layer="st_prospective")`. |
| 9.9.5 Handle dream-specific CONTRADICT | OPEN | Dream proposes something conflicting with truth → flag for P06, do not write blindly. |
| 9.9.6 Write tests | OPEN | Integration: duplicate routine in st_procedural is REINFORCED not duplicated. Contradicting insight is flagged not written. |

---

### Epic 9.10: Simplify R6 Assembler

**Repo Status**: OPEN
**Dependency**: Epics 9.6-9.9 (all phases migrated to framework, producing ReconciliationResults).

#### Epic 9.10 Problem Statement

After all phases produce `ReconciliationResult` objects with pre-built `StagedWrite` fields, R6
no longer needs 12+ per-layer assembly methods. R6 becomes a pure orchestrator that collects
StagedWrites from phase outputs.

#### Epic 9.10 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.10.1 Collect StagedWrites from phase ReconciliationResults | OPEN | R6 iterates phase outputs, extracts staged_write from each ReconciliationResult. |
| 9.10.2 Deprecate per-layer assemble methods | OPEN | Mark 12+ assemble_*_writes methods as deprecated. Keep as fallback behind feature flag. |
| 9.10.3 Preserve R6 orchestration responsibilities | OPEN | R6 still handles: dedup metadata, reconciliation recording, manifest generation, write ordering. |
| 9.10.4 Write regression tests | OPEN | Full pipeline produces identical StagedWrite set before and after R6 simplification. |

---

### Epic 9.11: Rich Structured Episode Summaries (Absorbed from M7 7.3)

**Discovery Reference**: M7 RC-2 (summary generation is heuristic-only)
**Repo Status**: OPEN
**Dependency**: Epic 9.5 (WriteDecisionRouter provides the write path for summaries).
**Absorption**: M7 Epic 7.3 designed this as bespoke st_epi code. M9 implements it as a
universal summary generator that the framework calls for any layer with summary support.

#### Epic 9.11 Problem Statement

Production episode summaries are template strings: "Routine with maya, prince at Home".
The research pipeline (`poc/r2_phase_research/r2_final_pipeline.py` `export_episodes_json()`
L941-1021) produces structured per-episode data with per-event metadata, thread distributions,
goal distributions, and affect trajectories. The structured data is already computable from
`ObservationContext` on member events. Production never computes it.

The universal framework provides the right abstraction point: `TruthLayerSpec` can declare
whether a layer supports structured summaries, and `WriteDecisionRouter` calls the summary
generator during CREATE, EXTEND, and EVOLVE writes.

#### Epic 9.11 Target Representation

Episodes carry structured JSON (in `episode_summary` or dedicated JSONB column) containing:
schema_version, title, event_count, dominant_thread, thread_distribution, goal_distribution,
temporal_narrative (start/end/duration/arc_position), participants, primary_location,
affect_trajectory (opening/closing/peak valence, trend), cohesion_score, and per-event records
(event_id, turn, timestamp, text_preview, thread, goal, activity, place, participants, valence).

HTML rendering is computed on demand from the structured JSON, not stored.

#### Epic 9.11 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.11.1 Define EpisodeStructuredSummary schema | OPEN | Versioned dataclass with schema_version, to_json(), from_json(). Mirrors research export_episodes_json() schema. |
| 9.11.2 Implement StructuredSummaryGenerator | OPEN | Replaces _generate_episode_title() and_generate_episode_summary(). Accepts List[ObservationContext] + cluster metadata, produces structured JSON. Algorithm: sort events by timestamp, compute thread/goal distributions, affect trajectory, build per-event records. |
| 9.11.3 Decide storage column strategy | OPEN | Option A: store in existing episode_summary TEXT. Option B: add episode_structured_data JSONB column (new migration). Recommend Option B for clean separation. |
| 9.11.4 Wire into WriteDecisionRouter | OPEN | WriteDecisionRouter calls StructuredSummaryGenerator on CREATE, EXTEND, and EVOLVE for layers that declare summary support in TruthLayerSpec. |
| 9.11.5 Populate narrative columns from structured data | OPEN | narrative_thread_id, narrative_thread_ids_json, narrative_arc_position derived from structured summary. |
| 9.11.6 Write tests | OPEN | Unit tests for distribution/trajectory computation. Integration test for full structured summary from real ObservationContexts. Schema validation tests. |

---

### Epic 9.12: Embedding Regeneration On EXTEND And EVOLVE (Absorbed from M7 7.4)

**Discovery Reference**: M7 RC-3 (episode embedding stale after EXTEND/EVOLVE)
**Repo Status**: OPEN
**Dependency**: Epics 9.5 (WriteDecisionRouter), 9.11 (summaries provide embedding text).
**Absorption**: M7 Epic 7.4 designed this as bespoke st_epi code. M9 implements it as a
universal embedding recomputation that the framework triggers for any embedding-bearing layer.

#### Epic 9.12 Problem Statement

When an episode is extended with new events, the centroid embedding in st_vec still represents
only the original member events. The embedding_text still describes the original episode.
Retrieval queries against extended episodes use stale embeddings, reducing recall.

The universal framework handles this cleanly: `WriteDecisionRouter` knows when an EXTEND or
EVOLVE write occurs. It can trigger embedding regeneration as a post-write hook for any layer
whose `TruthLayerSpec` declares an embedding FK.

#### Epic 9.12 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.12.1 Regenerate embedding_text on EXTEND | OPEN | After EXTEND: use StructuredSummaryGenerator to produce updated summary, then TextVectorCoordinator to generate new embedding_text. Universal: works for any layer with embedding support. |
| 9.12.2 Recompute centroid embedding on EXTEND | OPEN | Compute new centroid from union of all member embeddings (old + new). Recency-weighted using RECENCY_EXP strategy. Write to st_vec. Update layer table embedding_id. |
| 9.12.3 Generate fresh embedding for EVOLVE successor | OPEN | New record from EVOLVE gets its own centroid computed from its member events only. No inheritance from superseded record. |
| 9.12.4 Handle multi-centroid recomputation | OPEN | If multi-centroid is active, recompute secondary centroids for extended/evolved records. |
| 9.12.5 Write tests | OPEN | Test embedding changes after EXTEND. Test EVOLVE successor has independent embedding. Test MRR does not degrade after EXTEND operations. |

---

### Epic 9.13: Lifecycle Observability (Absorbed from M7 7.5)

**Discovery Reference**: M7 supplementary (lifecycle actions need operational visibility)
**Repo Status**: OPEN
**Dependency**: Epics 9.4 (ReconciliationFramework), 9.5 (WriteDecisionRouter).
**Absorption**: M7 Epic 7.5 designed this for st_epi only. M9 implements universal lifecycle
metrics and logging across all truth layers.

#### Epic 9.13 Problem Statement

With EXTEND, EVOLVE, CONTRADICT, and PRUNE active across all layers, operators need visibility
into lifecycle action distribution per batch, per layer. This includes: action counts, episode
growth rates, summary regeneration latency, embedding recomputation latency, superseded record
counts, and version chain depth.

#### Epic 9.13 Issues

| Issue | Status | Planned Action |
| ----- | ------ | -------------- |
| 9.13.1 Add per-layer lifecycle metrics to framework | OPEN | ReconciliationFramework emits per-batch, per-layer counters: records_created, records_reinforced, records_extended, records_evolved, records_contradicted, records_pruned. Universal: one implementation covers all layers. |
| 9.13.2 Add lifecycle dashboard queries | OPEN | SQL queries for ops monitoring: action distribution over time per layer, version chain depth, superseded count, extend/create ratio. |
| 9.13.3 Add structured logging for lifecycle transitions | OPEN | Log each lifecycle action with record_id, layer, action, event_count_before/after, similarity_score, trigger_source (K1 signal vs K0 threshold). |
| 9.13.4 Write tests | OPEN | Verify metrics emitted for all action types. Verify log entries contain required fields. Verify per-layer breakdown accuracy. |

---

### Milestone 9 Execution Order

1. **Epic 9.1** (truth layer registry) FIRST — pure data structure, no runtime changes, enables
   everything else. Can be tested in isolation.
2. **Epic 9.2** (identity strategies) SECOND — implements per-layer matching logic. Depends on
   registry for column references.
3. **Epic 9.3** (truth_candidates_query syscall) THIRD — unified truth read. Depends on registry
   for SQL construction.
4. **Epic 9.5** (write decision router) FOURTH — data-driven write assembly. Depends on registry
   for merge rules.
5. **Epic 9.4** (reconciliation framework) FIFTH — the core machine. Depends on 9.1-9.3 and 9.5.
6. **Epic 9.7** (migrate R3) SIXTH — R3 is the most complete current implementation. Migrating it
   first proves backward compatibility with the least risk.
7. **Epic 9.6** (migrate R2) SEVENTH — R2 st_epi matching via framework replaces bespoke code.
8. **Epic 9.8** (migrate R4) EIGHTH — R4 entity/edge resolution gains EXTEND/EVOLVE/CONTRADICT.
9. **Epic 9.9** (migrate R5) NINTH — R5 dream outputs get reconciliation for the first time.
10. **Epic 9.10** (simplify R6) TENTH — after all phases produce ReconciliationResults.
11. **Epic 9.11** (rich structured summaries) ELEVENTH — absorbed from M7 7.3. Universal summary
    generator for all layers, starting with st_epi. Depends on 9.5 (WriteDecisionRouter).
12. **Epic 9.12** (embedding regeneration) TWELFTH — absorbed from M7 7.4. Embedding recomputation
    on EXTEND/EVOLVE for all layers. Depends on 9.11 (summaries provide embedding text).
13. **Epic 9.13** (lifecycle observability) LAST — absorbed from M7 7.5. Metrics and structured
    logging for all lifecycle actions across all layers.

### Milestone 9 Exit Criteria

- TruthLayerRegistry covers all 8 truth tables with complete metadata.
- IdentityStrategy implementations exist for all 7 reconciliation-eligible layers.
- truth_candidates_query syscall handles embedding, key, and hybrid queries for all layers.
- ReconciliationFramework.reconcile() produces correct decisions for all layers.
- WriteDecisionRouter produces correct StagedWrites for all 6 actions across all layers.
- R2, R3, R4, R5 all use the framework instead of bespoke matching logic.
- R6 collects pre-built StagedWrites from phase outputs instead of assembling per-layer.
- Old ReconciliationEngine and TruthQueryService are deprecated.
- M8-FULL-01 regression test passes with zero delta (backward compatible).
- No phase has its own matching/query/write-assembly logic — the framework handles all of it.
- Each new truth layer addition requires only: one TruthLayerSpec, one IdentityStrategy, and
  column entries in the merge rules. Zero code changes to the framework or any phase.
- Episode summaries contain structured JSON with thread_distribution, goal_distribution,
  per-event metadata, affect_trajectory, and temporal_narrative. (Absorbed from M7 7.3)
- Episode embeddings and embedding_text regenerate on EXTEND and EVOLVE. (Absorbed from M7 7.4)
- Per-batch EXTEND/EVOLVE/CREATE/REINFORCE metrics emitted for all layers. (Absorbed from M7 7.5)
- Summary schema is versioned (schema_version field) for forward compatibility.
- Each lifecycle action is independently disableable via framework config flags.

### Milestone 9 Completion Verification

| Area | Verification Requirement |
| ---- | ------------------------ |
| Registry | TruthLayerRegistry.all_layers() returns 8+ entries. Every entry has valid PK, embedding FK, identity columns. |
| Identity | 7 IdentityStrategy implementations pass unit tests with known inputs. |
| Syscall | truth_candidates_query returns correct candidates for all 7 layers in integration tests. pgvector operator used for embedding path. |
| Framework | reconcile() produces identical decisions to current code for st_epi (R2), st_sem (R3), st_kg_dom (R4). |
| Write router | WriteDecisionRouter produces correct StagedWrites for CREATE/REINFORCE/EXTEND/EVOLVE/CONTRADICT/PRUNE across all layers. |
| R2 migration | R2 uses framework. M8 tests pass. |
| R3 migration | R3 uses framework. Old ReconciliationEngine deprecated. |
| R4 migration | R4 uses framework. Entities support EXTEND/EVOLVE/CONTRADICT. |
| R5 migration | R5 dream outputs reconciled. No duplicate routines/insights in output. |
| R6 simplification | R6 collects pre-built StagedWrites. Old assemble methods deprecated. |
| Backward compat | M8-FULL-01 passes with zero delta before vs after M9. |
| Extensibility | Adding a new truth layer requires only TruthLayerSpec + IdentityStrategy, zero framework changes. |
| Structured summaries | episode_summary (or dedicated JSONB column) contains schema_version, thread_distribution, goal_distribution, per-event records, affect_trajectory, temporal_narrative. (Epic 9.11) |
| Embedding freshness | After EXTEND: st_vec embedding reflects all member events. After EVOLVE: successor has independent embedding. MRR does not degrade. (Epic 9.12) |
| Lifecycle metrics | Per-batch, per-layer action counters emitted. Structured logs for each lifecycle transition. Dashboard queries operational. (Epic 9.13) |
| Rollback safety | Each lifecycle action (structured summaries, embedding regen, per-action routing) independently disableable via framework config. |

---

## Recommended Execution Order

### Phase A: Finish Plan Reality Alignment

1. Mark Milestone 1 as baseline complete/partial.
2. Remove stale future-tense implementation language for EventAdapter and timestamp-chain work.
3. Preserve only residual M1 hardening items.

### Phase B: Execute Milestone 2

1. Epic 2.1 DBSCAN full removal.
2. Epic 2.2 fake silhouette fix.
3. Epic 2.3 contract reconciliation.

### Phase C: Execute Milestone 3

1. Epic 3.5 wrapper decomposition (3.5.1 builder, 3.5.2 matcher extraction FIRST to reduce wrapper before algorithmic changes).
2. Issues 3.1.0, 3.3.0, 3.6.0: Protocol and EventAdapter extensions (shared prerequisite for all algorithmic epics).
3. Epic 3.1 6D CompositeDistance (after protocols are ready).
4. Epic 3.2 log-temporal distance.
5. Epic 3.3 boundary strength scoring (after protocols are ready).
6. Epic 3.4 rescue calibration (after 3.4.0 HDBSCAN test baseline).
7. Epic 3.6 temporal context binding (after 3.6.0 EventAdapter extension).
8. Epic 3.7 signal surface decisions (resolved via M3 research, before M3 exit).
9. Epic 3.5.3, 3.5.4: Quality coordinator extraction and final wrapper reduction (after algorithmic changes stabilize).

### Phase D: Execute Milestone 4

1. Issues 4.0.1, 4.0.2, 4.1.0: Prerequisites (resolve `R2StagedOutput` fate, baseline existing centroid tests, extend `CentroidableEvent` protocol).
2. Epic 4.1 salience-composite weighting (after protocol is ready).
3. Epic 4.3 probability-augmented centroiding (after 4.1 encoding model is stable).
4. Epic 4.4 episodic coherence WITH adjuster co-validation (4.4.5 runs alongside 4.4.3, not after).
5. Epic 4.6 narrative/cognitive/support-signal encoding (feeds into 4.1 and 4.4).
6. Epic 4.5 vectorized matrix (after M3 6D distance is stable; includes 6D complexity assessment).
7. Epic 4.2 multi-centroid representation (last — requires storage/retrieval contract decisions, reconciles all three write surfaces including `EpisodicLayerWriter`).

### Phase E: Execute Milestone 5

1. Issues 5.0.1, 5.0.2, 5.0.3: Prerequisites (extend EventAdapter with reliability/provenance properties, define adaptive-weight store key schema, baseline Hebbian test surface).
2. Epic 5.3 reliability and provenance gating (lowest dependency — requires only EventAdapter extension from 5.0.1 and M3 distance model, not Hebbian or adaptive-weight infrastructure).
3. Epic 5.1 Hebbian boost (after M3 6D distance lands and M2 contract reconciliation resolves `st_cooccurrence` drift).
4. Epic 5.2 context-adaptive weights (after 6D distance is stable, Hebbian interaction contract from prerequisites is defined, and adaptive-weight store schema from 5.0.2 is implemented).
5. Cross-epic validation: combined Hebbian + adaptive weight interaction tests (after both 5.1 and 5.2 ship, before M5 exit).

### Phase F: Execute Milestone 6

1. Epic 6.1 ensemble distance wiring (highest impact, smallest change).
2. Epic 6.2 thread purity correction (eliminates 53% contamination).
3. Epic 6.3 same-thread merge (depends on 6.2, reduces 800 episodes to ~260).
4. Epic 6.6 consolidation cycle deduplication (prevents duplicates before extending).
5. Epic 6.4 cross-batch extension (addresses batch-100 fragmentation across cycles).
6. Epic 6.5 metadata preservation (supplementary quality improvement).

### Phase G: Execute Milestone 9

1. Epic 9.1 truth layer registry FIRST (pure data structure, enables everything else).
2. Epic 9.2 identity strategy interface + 7 implementations (per-layer matching, depends on 9.1).
3. Epic 9.3 truth_candidates_query syscall (unified truth read, depends on 9.1).
4. Epic 9.5 write decision router (data-driven write assembly, depends on 9.1).
5. Epic 9.4 reconciliation framework (the core machine, depends on 9.1-9.3 + 9.5).
6. Epic 9.7 migrate R3 (backward compatibility proof — R3 is most complete current user).
7. Epic 9.6 migrate R2 (st_epi matching via framework, replaces bespoke code).
8. Epic 9.8 migrate R4 (entity/edge resolution gains EXTEND/EVOLVE/CONTRADICT).
9. Epic 9.9 migrate R5 (dream outputs get reconciliation for the first time).
10. Epic 9.10 simplify R6 (after all phases produce ReconciliationResults).
11. Epic 9.11 rich structured summaries (universal summary generator for all layers).
12. Epic 9.12 embedding regeneration on EXTEND/EVOLVE (centroid recomputation for all layers).
13. Epic 9.13 lifecycle observability (metrics + structured logging for all lifecycle actions).

### Phase H: Execute Milestone 8

1. Epic 8.1 test fixture infrastructure FIRST (required by all other epics).
2. Epic 8.2 scenario evaluation framework (needed for K-stage in all test windows).
3. Epic 8.3 window-2 adjacent pair tests (smallest tests, catch interface mismatches early).
4. Epic 8.4 window-3 triple tests (catch multi-boundary issues).
5. Epic 8.5 window-4 and window-5 tests (deeper chain validation).
6. Epic 8.7 cross-batch lifecycle tests (specialized EXTEND/EVOLVE tests).
7. Epic 8.6 extended window + full chain tests (longest tests, highest value).
8. Epic 8.8 research parity regression (capstone gate — proves production matches research).

---

Created 5 todos

Let me first find the milestone boundaries in the epic plan and read the research document.

Searched for regex `^## Milestone [679]` (`**/docs/plans/R2_EPISODIC_INTEGRATION_EPIC_PLAN.md`), 3 results

Searched for regex `^## Milestone` (`**/docs/plans/R2_EPISODIC_INTEGRATION_EPIC_PLAN.md`), 10 results

Searched for regex `^#` (`**/poc/r2_phase_research/results/R2_RESEARCH_FINAL.md`), 60 results

Now let me read M6, M7, M9 in parallel plus the research document.

Read [](file:///d%3A/familyos/docs/plans/R2_EPISODIC_INTEGRATION_EPIC_PLAN.md#5106-5106), lines 5106 to 5304

Read [](file:///d%3A/familyos/docs/plans/R2_EPISODIC_INTEGRATION_EPIC_PLAN.md#5305-5305), lines 5305 to 5400

Read [](file:///d%3A/familyos/docs/plans/R2_EPISODIC_INTEGRATION_EPIC_PLAN.md#5819-5819), lines 5819 to 6700

Read [](file:///d%3A/familyos/poc/r2_phase_research/results/R2_RESEARCH_FINAL.md#1-1), lines 1 to 400

Read [](file:///d%3A/familyos/poc/r2_phase_research/results/R2_RESEARCH_FINAL.md#400-400), lines 400 to 800

Starting: *Deep R2 code analysis via subagents* (3/5)

Now let me launch deep code analysis subagents in parallel to examine the actual R2 source files end-to-end.

Analyze R2 main orchestrator

Analyze R2 algorithm files

Analyze R2 types and data flow

Analyze R2 tests and current engine

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#1-1), lines 1 to 150

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#151-151), lines 151 to 350

Read [](file:///d%3A/familyos/k0/pipelines/p03/event_state.py#1-1), lines 1 to 300

Searched for files matching `**/r2*config*`, no matches

Searched for text `assemble_epi_writes`, 20 results

Searched for text `CrossBatchExtendMatcher`, 20 results

Read [](file:///d%3A/familyos/k0/pipelines/p03/phase_outputs.py#1-1), lines 1 to 300

Read [](file:///d%3A/familyos/k0/pipelines/p03/context.py#1-1), lines 1 to 300

Searched for files matching `**/tests/k0/pipelines/p03/test_r2*`, 16 matches

Searched for files matching `**/tests/k0/modules/consolidation/test_*`, no matches

Searched for files matching `**/test_r2_ensemble_wiring*`, 1 match

Searched for regex `REINFORCE|EXTEND|reconciliation|episode_match|CrossBatchExtendMatcher` (`**/tests/k0/**`), 20 results

Searched for regex `class ReconciliationEngine|def decide|def reconcile|def match` (`**/k0/modules/consolidation/reconciliation_engine.py`), no results

Searched for regex `LAYER_PK_COLUMNS|DEFAULT_TRUTH_LAYERS|def find_candidates` (`**/k0/modules/consolidation/staging/truth_query_service.py`), 7 results

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms)

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/composite_distance.py#1-1), lines 1 to 500

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/episodic_hdbscan.py#1-1), lines 1 to 500

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/centroid_calculator.py#1-1), lines 1 to 500

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/episode_splitter.py#1-1), lines 1 to 500

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#351-351), lines 351 to 550

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#551-551), lines 551 to 750

Searched for files matching `**/reconciliation_engine.py`, 1 match

Searched for regex `REINFORCE|reconciliation|episode_match|CrossBatchExtendMatcher|ReconciliationEngine` (`**/tests/k0/**`), 20 results

Read [](file:///d%3A/familyos/k0/modules/consolidation/staging/truth_query_service.py#1-1), lines 1 to 100

Read [](file:///d%3A/familyos/k0/pipelines/p03/phase_outputs.py#300-300), lines 300 to 600

Searched for regex `r2_config|R2Config|R2_CONFIG|r2_settings` (`**/k0/pipelines/p03/**`), 20 results

Searched for text `ObservationContext` (`**/k0/modules/consolidation/algorithms/**`), 20 results

Read [](file:///d%3A/familyos/k0/modules/consolidation/staging/truth_write_assembler.py#280-280), lines 280 to 500

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/cross_batch_extend.py)

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#751-751), lines 751 to 950

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/composite_distance.py#500-500), lines 500 to 1000

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/episodic_hdbscan.py#500-500), lines 500 to 910

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/centroid_calculator.py#500-500), lines 500 to 727

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/episode_splitter.py#500-500), lines 500 to 824

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/thread_purity.py)

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/same_thread_merge.py)

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/reconciliation_engine.py#1-1), lines 1 to 500

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#951-951), lines 951 to 1150

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#1151-1151), lines 1151 to 1400

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/reconciliation_engine.py#1-1), lines 1 to 300

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_cross_batch_extend.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_integration.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_ensemble_wiring.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_centroid_calculator.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_composite_distance.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_cluster_quality.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_timestamp_chain.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_thread_purity.py`), 20 results

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#1401-1401), lines 1401 to 1600

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/composite_distance.py#1000-1000), lines 1000 to 1293

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/reconciliation_engine.py#500-500), lines 500 to 700

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/cross_batch_extend.py#1-1), lines 1 to 200

Read [](file:///d%3A/familyos/k0/pipelines/p03/phase_outputs.py#1-1), lines 1 to 100

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#1601-1601), lines 1601 to 1850

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#1851-1851), lines 1851 to 2100

Read [](file:///d%3A/familyos/k0/pipelines/p03/phase_outputs.py#100-100), lines 100 to 200

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/cross_batch_extend.py#200-200), lines 200 to 282

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/reconciliation_engine.py#700-700), lines 700 to 875

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#2101-2101), lines 2101 to 2350

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/reconciliation_engine.py#300-300), lines 300 to 500

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_same_thread_merge.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_min_samples_adjuster.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_hebbian_boost.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_event_adapter.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_eps_adjuster.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_episodic_hdbscan.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_episodic_coherence.py`), 20 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_episode_splitter.py`), 20 results

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#2351-2351), lines 2351 to 2435

Searched for text `class R2Config` (`**/k0/pipelines/p03/phases/r2_episodic_integrator.py`), 1 result

Searched for text `class R6Output`, 4 results

Read [](file:///d%3A/familyos/k0/modules/consolidation/staging/truth_write_assembler.py#500-500), lines 500 to 700

Read [](file:///d%3A/familyos/k0/pipelines/p03/phase_outputs.py#600-600), lines 600 to 897

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/observation_context.py#1-1), lines 1 to 250

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#2435-2435), lines 2435 to 2435

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r2_episodic_integrator.py#80-80), lines 80 to 200

Read [](file:///d%3A/familyos/k0/modules/consolidation/staging/r6_output.py#1-1), lines 1 to 450

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/reconciliation_engine.py#500-500), lines 500 to 650

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_cross_batch_extend.py`), 39 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_integration.py`), 29 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_r2_same_thread_merge.py`), 42 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_grounding_signal_pipeline.py`), 43 results

Searched for regex `def test_|class Test` (`**/tests/k0/pipelines/p03/test_p03_audit_logger.py`), 30 results

Read [](file:///d%3A/familyos/tests/k0/pipelines/p03/test_r2_cross_batch_extend.py#1-1), lines 1 to 100

Searched for text `class StagedWrite` (`**/k0/pipelines/p03/staged_writes.py`), 1 result

Read [](file:///d%3A/familyos/k0/pipelines/p03/event_state.py#290-290), lines 290 to 300

Read [](file:///d%3A/familyos/k0/modules/consolidation/staging/truth_write_assembler.py#1900-1900), lines 1900 to 2000

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/reconciliation_engine.py#640-640), lines 640 to 750

Read [](file:///d%3A/familyos/k0/modules/consolidation/staging/truth_query_service.py#100-100), lines 100 to 400

Read [](file:///d%3A/familyos/k0/pipelines/p03/staged_writes.py#50-50), lines 50 to 200

Created memory file [](file:///c%3A/Users/princ/AppData/Roaming/Code/User/workspaceStorage/af8eada89b8e0ceb331a1a230f56c42f/GitHub.copilot-chat/memory-tool/memories/NWQzMjAyY2YtNTcwYi00YmJhLWE2ODQtMWRkNWMyMWEyNmQw/r2_test_inventory_reconciliation.md)

Read [](file:///c%3A/Users/princ/AppData/Roaming/Code/User/workspaceStorage/af8eada89b8e0ceb331a1a230f56c42f/GitHub.copilot-chat/chat-session-resources/5d3202cf-570b-4bba-a684-1dd5c21a26d0/tooluse_AlH0jnbQMRm1HGMWxKSh2r__vscode-1773081868568/content.txt)

Read [](file:///c%3A/Users/princ/AppData/Roaming/Code/User/workspaceStorage/af8eada89b8e0ceb331a1a230f56c42f/GitHub.copilot-chat/chat-session-resources/5d3202cf-570b-4bba-a684-1dd5c21a26d0/tooluse_CdWi7EfMvu7ACcWBDHq5O0__vscode-1773081868567/content.txt)

Read [](file:///c%3A/Users/princ/AppData/Roaming/Code/User/workspaceStorage/af8eada89b8e0ceb331a1a230f56c42f/GitHub.copilot-chat/chat-session-resources/5d3202cf-570b-4bba-a684-1dd5c21a26d0/tooluse_ueDIaY8MPpSWY1nMNplTTG__vscode-1773081868569/content.txt)

Read [](file:///c%3A/Users/princ/AppData/Roaming/Code/User/workspaceStorage/af8eada89b8e0ceb331a1a230f56c42f/GitHub.copilot-chat/chat-session-resources/5d3202cf-570b-4bba-a684-1dd5c21a26d0/tooluse_meb5YBNb23H0YBVWUMz97T__vscode-1773081868566/content.txt)

Compacted conversation

Starting: *Synthesize hook points analysis* (4/5)

Starting: *Present integration plan to user* (5/5)

Here is the complete end-to-end R2 code analysis with exact hook points for Universal Reconciliation Engine integration.

---

## R2 Current Pipeline Flow (2,500-line orchestrator)

```
run(envelope, ctx)
 |
 +-- 1. _query_existing_episodes()          SQL → st_epi (50 episodes, 7-day window)
 +-- 2. _match_events_to_existing_episodes() BESPOKE REINFORCE (cos >= 0.85)
 |       matched events REMOVED from clustering pipeline
 +-- 3. EventAdapter wraps novel events
 +-- 4. EpisodeSplitter.split()              pre-clustering boundary detection
 +-- 5. build_cooccurrence_graph()           Hebbian graph (Epic 5.1)
 +-- 6. EpisodicHDBSCAN.cluster()            3D ensemble distance → HDBSCAN
 +-- 7. ThreadPurityCorrector.correct()      split impure clusters (Epic 6.2)
 +-- 8. SameThreadMerger.merge()             union-find merge (Epic 6.3)
 +-- 9. CentroidCalculator.compute()         recency_exp centroid → EpisodeCandidate
 +-- 10. CrossBatchExtendMatcher.match()     BESPOKE EXTEND (cos >= 0.60 + same thread)
 +-- 11. _update_event_states()              stamp cluster_id on P03EventState
 +-- 12. envelope.phases.r2_clusters = [...]
```

---

## Three Exact Hook Points

### HOOK 1: Replace `_match_events_to_existing_episodes` (Pre-Clustering REINFORCE)

**Current code** (r2_episodic_integrator.py):

- Iterates every event against every existing episode
- Direct `_cosine_similarity(event_embedding, ep_embedding)`
- Hardcoded `episode_reinforce_threshold = 0.85`
- Sets `event.reconciliation_action = ReconciliationAction.REINFORCE` on P03EventState
- Removes matched events from the clustering pipeline (they skip HDBSCAN)

**Problems with current approach:**

1. Bespoke cosine similarity inline - duplicates logic that lives in ReconciliationEngine
2. No Tier 1 K1 signal check - ignores `correction_signal` / `contradiction_signal` on P03EventState
3. Uses `struct.unpack` for vector decoding (r2_episodic_integrator.py) - latent bug since pgvector returns strings
4. No observability (no ReconciliationDecision audit trail)

**Proposed replacement:**

```
universal_engine.decide_episode_match(
    candidate_embedding = event.embedding_768,
    layer = "st_epi",
    identity_strategy = EpisodicIdentityStrategy,
    existing_records = queried_episodes,
    k1_signals = { correction_signal, contradiction_signal }
)
```

The engine returns `ReconciliationDecision` with action = REINFORCE / EXTEND / EVOLVE / CONTRADICT / CREATE. Only REINFORCE events get pulled out of the clustering pipeline. EVOLVE/CONTRADICT events also get pulled (they should NOT cluster with novel events - they need K1-directed handling).

**What changes in the `run()` method:**

- Step 2 calls `universal_engine.decide_batch()` instead of `_match_events_to_existing_episodes()`
- Events with action in {REINFORCE, EVOLVE, CONTRADICT} are removed from clustering
- Events with EXTEND stay in pipeline (they need cluster context first)
- CREATE events proceed to HDBSCAN as before

---

### HOOK 2: Replace `CrossBatchExtendMatcher.match()` (Post-Clustering EXTEND)

**Current code** (r2_episodic_integrator.py + cross_batch_extend.py):

- Separate matcher class with its own config (`centroid_sim_threshold=0.60`, `require_same_thread=True`, `max_temporal_gap_ms=7 days`)
- Compares `EpisodeCandidate.centroid_embedding` vs existing episode embedding
- Sets `cand.reconciliation_action = "EXTEND"` (raw **string**, not enum - inconsistency!)
- Sets `cand.extend_target_episode_id`, `cand.extend_similarity`

**Problems with current approach:**

1. Type inconsistency: REINFORCE uses `ReconciliationAction` enum, EXTEND uses raw string `"EXTEND"`
2. Separate threshold config - not governed by a unified layer spec
3. Thread requirement is hardcoded in matcher, not in identity strategy
4. No EVOLVE/CONTRADICT path for clusters (only events get K1 routing)

**Proposed replacement:**

```
for each EpisodeCandidate:
    decision = universal_engine.decide_episode_match(
        candidate_embedding = candidate.centroid_embedding,
        layer = "st_epi",
        identity_strategy = EpisodicIdentityStrategy,
        existing_records = queried_episodes,
        supplementary_checks = {
            thread_match: candidate.dominant_thread == episode.dominant_thread,
            temporal_proximity: abs(candidate.temporal_end - episode.end_time) <= 7 days
        }
    )
```

The EpisodicIdentityStrategy encapsulates:

- Thread match requirement (currently `require_same_thread=True`)
- Temporal gap check (currently `max_temporal_gap_ms=7 days`)
- Cosine similarity thresholds (from TruthLayerSpec, not hardcoded)

**What changes:**

- `CrossBatchExtendMatcher` gets replaced by a single engine call per candidate
- `EpisodeCandidate.reconciliation_action` uses the enum (not string)
- The engine applies the two-tier model: check K1 signals first, then similarity thresholds

---

### HOOK 3: Bridge R2 Output to R3/R6 (New Reconciliation Summary)

**Current data flow gap:**

- R2 produces `List[EpisodeCluster]` (no reconciliation fields on clusters)
- R2 stamps `episode_match_id` on P03EventState (for REINFORCE events only)
- R3's `ReconciliationEngine` independently decides per-event against ALL truth layers (not just st_epi)
- R6's `TruthWriteAssembler` reads both R2 clusters AND R3 decisions

**The logical problem:**
R2 makes REINFORCE/EXTEND decisions for st_epi using bespoke code.
R3 makes REINFORCE/EXTEND/EVOLVE/CONTRADICT/CREATE decisions for ALL layers using ReconciliationEngine.
These two decision paths can CONFLICT. An event could get REINFORCE from R2 (matched existing episode) but CREATE from R3 (ReconciliationEngine doesn't see the R2 match because it queries independently).

**Proposed fix - Unified decision surface:**

R2's hook points feed into the Universal Engine, which returns decisions that R3 CONSUMES rather than re-deriving:

```
R2 (episode-level decisions via universal engine)
 |
 +-- REINFORCE events: engine.decide() → action=REINFORCE
 |    Stamped on P03EventState.reconciliation_action
 |    P03EventState.episode_match_id = best_match_id
 |
 +-- EXTEND clusters: engine.decide() → action=EXTEND
 |    Stamped on EpisodeCandidate.reconciliation_action
 |    EpisodeCandidate.extend_target_episode_id = best_match_id
 |
 +-- EVOLVE/CONTRADICT: engine.decide() → action=EVOLVE/CONTRADICT
 |    K1 signal detected, pulled from clustering
 |    Stamped on P03EventState, routed to st_learning_queue
 |
 +-- CREATE: no match found, proceed through HDBSCAN
      New EpisodeCandidate with action=CREATE

R3 then ONLY handles non-st_epi layers (st_sem, st_procedural, st_social, st_prospective)
and RESPECTS R2's st_epi decisions rather than overriding them.
```

---

## What STAYS in R2 (Domain Logic, Not Reconciliation)

| Component | Why It Stays |
|---|---|
| `EpisodeSplitter` | Pre-clustering boundary detection - episode structure, not reconciliation |
| `EpisodicHDBSCAN` | Clustering algorithm - finds natural groupings, not truth matching |
| `ThreadPurityCorrector` | Post-clustering quality - ensures cluster purity, not a reconciliation concern |
| `SameThreadMerger` | Post-clustering merge - episode structure refinement |
| `CentroidCalculator` | Computes representative embeddings - input TO reconciliation, not part of it |
| Quality tracking / adaptive tuning | Operational concern, not reconciliation |

## What MOVES to Universal Engine

| Current Location | What Moves |
|---|---|
| `_match_events_to_existing_episodes` (L2123-L2210) | Similarity matching + threshold decision logic |
| `CrossBatchExtendMatcher` (cross_batch_extend.py) | EXTEND matching + thread/temporal checks |
| Hardcoded thresholds (0.85, 0.60) | Governed by `TruthLayerSpec.thresholds` |
| `ReconciliationEngine.decide()` (R3) | Per-event multi-layer decisions |
| `ReconciliationAction` assignment | Single decision function in engine |

## Logical Soundness Verification

### Before: Two separate decision paths (CONFLICT RISK)

```
Event E1 arrives with embedding_768

R2 path (bespoke):
  cos_sim(E1, existing_episode_X) = 0.87
  → REINFORCE (>= 0.85)
  → episode_match_id = X

R3 path (ReconciliationEngine):
  TruthQueryService.find_candidates(E1, all_layers)
  → finds st_sem match Y with sim 0.92
  → REINFORCE against st_sem (highest sim wins)
  → best_match_id = Y, best_match_layer = st_sem

R6 sees BOTH:
  episode_match_id = X (from R2)
  best_match_id = Y (from R3)
  → WHICH ONE WINS? Currently: R6 writes BOTH (st_epi UPDATE + st_sem UPDATE)
  → This is CORRECT but ACCIDENTAL — no contract guarantees it
```

### After: Single decision surface (NO CONFLICT)

```
Event E1 arrives with embedding_768

Universal Engine (called from R2 for st_epi):
  engine.decide(E1, layer="st_epi", ...)
  cos_sim(E1, episode_X) = 0.87
  → REINFORCE(st_epi, X)
  → Stamped on P03EventState

Universal Engine (called from R3 for remaining layers):
  engine.decide(E1, layers=["st_sem", "st_procedural", "st_social", "st_prospective"])
  cos_sim(E1, sem_Y) = 0.92
  → REINFORCE(st_sem, Y)
  → Stamped on P03EventState (multi-layer decisions list)

R6 reads unified decision list:
  [(REINFORCE, st_epi, X), (REINFORCE, st_sem, Y)]
  → Writes both with clear provenance
```

---

## Critical Inconsistencies Found in Current Code

| Issue | Location | Impact |
|---|---|---|
| EXTEND uses string `"EXTEND"`, REINFORCE uses `ReconciliationAction` enum | r2_episodic_integrator.py vs r2_episodic_integrator.py | Type mismatch between event-level and cluster-level reconciliation |
| `episode_extend_threshold=0.60` declared but NEVER USED in R2 | r2_episodic_integrator.py | Dead config - EXTEND comes from CrossBatchExtendMatcher with its own threshold |
| `_decode_vector` uses `struct.unpack` (BYTEA) but pgvector returns strings | r2_episodic_integrator.py | Latent bug - vectors may fail to decode since M4 pgvector migration |
| No `reconciliation_action` on `EpisodeCluster` dataclass | phase_outputs.py | Cluster-level decisions live on EpisodeCandidate (different type), not on the R2 output type |
| ReconciliationEngine has ZERO test coverage | - | `decide()`, `_determine_action()`, `_compute_confidence()` are untested |
| No EVOLVE/CONTRADICT path at R2 level | R2 only does REINFORCE + EXTEND | K1 signals (`correction_signal`, `contradiction_signal`) are loaded by R0 but ignored until R3 |

---

## Recommended Integration Order (M9 Epics)

Per the Epic Plan M9, the correct sequence is:

1. **M9.1** — `TruthLayerRegistry` + `TruthLayerSpec` (5 layers with thresholds)
2. **M9.2** — `IdentityStrategy` per layer (`EpisodicIdentity` with thread+temporal checks)
3. **M9.3** — Syscall for `find_candidates` (replaces inline SQL in R2)
4. **M9.5** — Write Decision Router (replaces R6's scattered assembly)
5. **M9.4** — Universal Engine framework (stateless `decide()` function)
6. **M9.6** — **R2 integration** (Hook 1 + Hook 2 + Hook 3 above)
7. **M9.7** → M9.10 — R3/R4/R5/R6 migration to universal engine

Hook 1 (pre-clustering REINFORCE) and Hook 2 (post-clustering EXTEND) are M9.6. Hook 3 (bridge to R3/R6) is the cross-cutting concern that spans M9.6 through M9.10.

Completed: *Present integration plan to user* (5/5)

That's the complete analysis. The three hook points are:

1. **Replace `_match_events_to_existing_episodes`** (L2123-L2210) — bespoke REINFORCE becomes an engine call
2. **Replace `CrossBatchExtendMatcher.match()`** (L793-L817) — bespoke EXTEND becomes an engine call with EpisodicIdentityStrategy
3. **Bridge R2 decisions to R3** — eliminate the dual-decision-path conflict where R2 and R3 independently decide against st_epi

The critical logical fix is that today R2 and R3 make **independent, potentially conflicting** st_epi decisions. The universal engine creates a single decision surface where R2 owns st_epi decisions and R3 owns the remaining 4 layers, both through the same engine interface.


4 Bugs Found
BUG 1: dominant_sentiment = raw float, not label
Where: episodic_hdbscan.py ~L855 averages sentiment_score floats
Stored: 0.6491875 instead of "positive"
Fix: Classify averaged score → label (>0.6 = positive, 0.4-0.6 = neutral, <0.4 = negative), or use MODE of event labels
BUG 2: episode_summary = template garbage
Where: r2_episodic_integrator.py ~L1780
Result: "Routine with Dad, Mom, person_dad at Home Office" × 9 copies
Pattern: {activity_type} with {participants} at {location} — no actual summarization
Fix: Use TextRank (already exists at consolidation/algorithms/text_generators/textrank.py) or LLM
BUG 3: No duration cap — episodes span 81 hours
Where: truth_write_assembler.py ~L513 computes (end - start) / 60000 with no cap
Config: episode_splitter.py L95 has hard_episode_span_minutes = 1080 (18h) but it's not enforced
Fix: Enforce the 18h hard split in EpisodeSplitter, cap in TruthWriteAssembler
BUG 4: NIGHT bucket = 57% of episodes
Where: temporal_profile.py L85 — NIGHT spans 22:00→06:00 (8 hours vs 5-6 for others)
Root cause: Unequal bucket sizes + the conversation_anchor_ms timestamps likely use a timezone offset that pushes daytime events into the NIGHT window
Fix: Rebalance buckets to equal 6h spans, verify timezone handling
