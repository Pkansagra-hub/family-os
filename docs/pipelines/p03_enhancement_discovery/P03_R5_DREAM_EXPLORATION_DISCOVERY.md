# P03 R5 Dream Exploration -- Enhancement Discovery Document

---

## Section 0: Discovery Metadata

| Field                 | Value |
|-----------------------|-------|
| **Discovery ID**      | DISC-P03-R5 |
| **Phase**             | R5 -- Dream Exploration |
| **Pipeline**          | P03 Consolidation |
| **Epic**              | 5.6 |
| **Skeleton Reference**| `docs/plans/MASTER_IMPLEMENTATION_SKELETON.md` lines 5402-5600 |
| **Status**            | Discovery Complete |
| **Author**            | Intelligence Kernel Team |
| **Created**           | 2025-01-27 |
| **Last Updated**      | 2025-01-27 |
| **Depends On**        | DISC-P03-R4 (Edge Enrichment), DISC-P03-R3 (Decay & Dedup), DISC-P03-R2 (Episode Clustering) |
| **Blocks**            | Epic 5.7 (R6 Merge Arbitration), Epic 5.8 (R7 Truth Writing) |
| **Related ADRs**      | ADR-K003 (FAISS Elimination), ADR-P03-STAGE5 (pending) |
| **Proposal Docs**     | `docs/pipelines/p03/stage5_refinement_proposal.md` (4882 lines), `docs/pipelines/p03/stage5_proposal_corrections.md` (1640 lines) |

### Discovery Scope

R5 Dream Exploration is the "REM sleep" phase of P03 consolidation. It runs after R0-R4 have reconciled, clustered, decayed, and enriched events, and BEFORE R6-R8 write truth table updates. R5 currently executes 7 algorithms (5 primary + 2 support) that generate insights, counterfactuals, prospective memories, routine optimizations, and intent signals. These outputs flow through R6 merge arbitration and R7 truth writers to update 6 truth tables.

The Stage 5 Refinement Proposal replaces 2 current algorithms (CPN, TPN-MCTS) with 10 observation-driven algorithms and refocuses 1 existing algorithm (SPC-UQ). This discovery document captures the CURRENT state of R5, identifies all gaps, and provides the foundation for the Stage 5 implementation epics (M5C cleanup + M5D infrastructure).

### Key Design Principle (Stage 5)

> Counterfactual reasoning belongs at K1 query time, not K0 consolidation. R5 strengthens existing memory through observation evidence, not by inventing fictional scenarios. All new algorithms are st_observations-first.

---

## Section 1: Current State Audit

### 1.1 Code Inventory

#### Phase File

| File | Path | Lines | Purpose |
|------|------|------:|---------|
| `r5_dream_explorer.py` | `k0/pipelines/p03/phases/r5_dream_explorer.py` | 1,070 | Phase runner: skip logic, data loading (7 syscall loaders), algorithm execution, metrics emission, R5PhaseOutputs assembly |

#### Orchestrator

| File | Path | Lines | Purpose |
|------|------|------:|---------|
| `dream_explorer.py` | `k0/modules/consolidation/dream/dream_explorer.py` | 1,439 | Core orchestrator: parallel Phase 1 (BGT-SM, CPN, SPC-UQ, MCTS, RoutineDetector), sequential Phase 2 (TDL-HCO), Phase 3 (quality filters), Phase 4 (IntentSignalDetector) |

#### Algorithm Files

| File | Path | Lines | Status | Purpose |
|------|------|------:|--------|---------|
| `bgt_sm.py` | `k0/modules/consolidation/algorithms/bgt_sm.py` | 1,208 | KEEP | Bisociative Graph Traversal -- random-walk-with-restart over KG, PMI calculation, insight discovery |
| `cpn.py` | `k0/modules/consolidation/algorithms/cpn.py` | 1,106 | DELETE | Causal Perturbation Network -- counterfactual scenario generation via DAG perturbation. Produces 70 nonsense counterfactuals per run |
| `mcts.py` | `k0/modules/consolidation/algorithms/mcts.py` | 1,113 | DELETE | Temporal Projection Network via MCTS -- UCT tree search for forward simulation. No meaningful game tree; LLM+context is strictly superior |
| `mcts_shadow.py` | `k0/modules/consolidation/algorithms/mcts_shadow.py` | 918 | DELETE | Shadow outcome tracker for MCTS -- records predictions to st_mcts_shadow_log, promotion analysis. Dead code once MCTS is removed |
| `spc_uq.py` | `k0/modules/consolidation/algorithms/spc_uq.py` | 1,253 | REFOCUS | Episodic Simulator with uncertainty quantification -- gap identification, Bayesian reconstruction. Shift from generation to prospective memory cleanup |
| `tdl_hco.py` | `k0/modules/consolidation/algorithms/tdl_hco.py` | 1,025 | KEEP | Temporal Difference Learning -- ValueFunction TD updates, bottleneck detection, routine optimization suggestions |
| `intent_signal_detector.py` | `k0/modules/consolidation/algorithms/intent_signal_detector.py` | 631 | ACTIVE | Regex-based extraction for 6 intent types (Reminder, Decision, Lesson, Emotional, Milestone, QueryBoost) |
| `routine_detector.py` | `k0/modules/consolidation/algorithms/routine_detector.py` | 710 | ACTIVE | Signature grouping, frequency/regularity scoring, lifecycle detection (FORMING->ESTABLISHED->MAINTAINED->DECAYING->EXTINCT) |
| `observation_context.py` | `k0/modules/consolidation/algorithms/observation_context.py` | ~310 | ACTIVE | ObservationContext dataclass (~35 fields), from_event/from_episode_cluster/to_db_row factories |

#### Support Files

| File | Path | Lines | Purpose |
|------|------|------:|---------|
| `config.py` | `k0/modules/consolidation/dream/config.py` | ~180 | DreamConfig: exploration params, quality thresholds, per-algorithm config, derive_seed(), from_r5_config() |
| `models.py` | `k0/modules/consolidation/dream/models.py` | 411 | Frozen dataclasses: Insight, CounterfactualScenario, ProspectiveMemory, RoutineOptimization, DreamExplorerInput, DreamExplorerOutput |
| `compute_budget.py` | `k0/modules/consolidation/dream/compute_budget.py` | 289 | ComputeBudget: rollout allocation for MCTS, elapsed time tracking, AlgorithmResult, OrchestrationResult |
| `intent_signals.py` | `k0/modules/consolidation/dream/intent_signals.py` | 262 | IntentSignalType enum (6 types), IntentSignal base + 6 subclasses (ReminderSignal, DecisionSignal, LessonSignal, EmotionalSignal, MilestoneSignal, QueryBoostSignal) |
| `mcts_persistence.py` | `k0/modules/consolidation/dream/mcts_persistence.py` | ~438 | MCTSDecisionRecord, MCTSDecisionPersistence (SQL INSERT st_mcts_decisions), CycleDecisionTracker. Dead code once MCTS is removed |

#### Phase Config

| File | Path | Lines | Purpose |
|------|------|------:|---------|
| `r5_config.py` | `k0/pipelines/p03/r5_config.py` | 241 | R5Mode enum (DISABLED/SHADOW/ENABLED_LOW/ENABLED), R5Config (~30 params), ROLLOUTS_PER_MODE dict, from_dict() factory |

**Source Code Totals:**

| Category | Files | Lines |
|----------|------:|------:|
| Phase runner | 1 | 1,070 |
| Orchestrator | 1 | 1,439 |
| Algorithm files | 9 | 8,274 |
| Support files | 4 | 1,400 |
| Phase config | 1 | 241 |
| **Total** | **16** | **12,424** |

---

### 1.2 Contract Inventory

| Contract | Path | Lines | Scope |
|----------|------|------:|-------|
| `consolidation.dream_explorer.v1.yaml` | `k0/contracts/modules/consolidation.dream_explorer.v1.yaml` | 248 | M22 DreamExplorer module contract. Input topics: `p03.kg.extracted.v1`, `p03.episodes.clustered.v1`. Output topics: `p03.insights.generated.v1`, `p03.counterfactuals.generated.v1`, `p03.prospective.generated.v1`. Latency budget: 2000ms. 5 fabric capabilities. |
| `p03_consolidation.v1.yaml` | `k0/contracts/pipelines/p03_consolidation.v1.yaml` | 433 | Full P03 pipeline DAG (R0-R8). R5 stages: `stage_50_counterfactual` (CPN), `stage_51_forward_sim` (TPN-MCTS), `stage_52_insight_gen` (BGT-SM). All after `stage_42_causal_inference`, all skippable on backlog. |

**Contract Issues Identified:**

| Issue | Severity | Detail |
|-------|----------|--------|
| Stage naming mismatch | HIGH | Pipeline contract defines `stage_50_counterfactual`, `stage_51_forward_sim`, `stage_52_insight_gen` but actual code runs as a single R5 phase with parallel internal orchestration. No 1:1 mapping between contract stages and code execution. |
| Missing output topics | HIGH | Contract defines 3 output topics but code produces 7 output types (insights, counterfactuals, prospective memories, routine optimizations, intent signals, routine candidates, MCTS scenarios). Intent signals and routine candidates have no contract topic. |
| Latency budget stale | MEDIUM | Contract specifies 2000ms but `r5_config.py` allows `max_r5_seconds=120` (120,000ms). Real execution can exceed contract budget by 60x. |
| CPN/MCTS references | HIGH | Contract references CPN and TPN-MCTS as named stages. These algorithms are scheduled for deletion in M5C. Contract must be updated post-cleanup. |
| No observation evidence contract | HIGH | Stage 5 proposal introduces ObservationEvidenceLoader as shared infrastructure for all new algorithms. No contract exists for this component or the st_observations queries it executes. |

---

### 1.3 Configuration Inventory

#### R5Config (`k0/pipelines/p03/r5_config.py`)

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `r5_mode` | R5Mode enum | `DISABLED` | Master switch: DISABLED / SHADOW / ENABLED_LOW / ENABLED |
| `max_r5_seconds` | float | 120.0 | Global timeout for entire R5 phase |
| `backlog_threshold` | int | 1000 | Skip R5 if pending event count exceeds this |
| `min_clusters_for_r5` | int | 2 | Minimum episode clusters from R2 to justify running R5 |
| `max_insights` | int | 20 | Cap on BGT-SM insight output |
| `max_counterfactuals` | int | 10 | Cap on CPN counterfactual output |
| `max_prospective` | int | 10 | Cap on SPC-UQ/MCTS prospective output |
| `max_routines` | int | 5 | Cap on TDL-HCO routine optimization output |
| `enable_mcts` | bool | True | Feature flag for MCTS algorithm |
| `enable_cpn` | bool | True | Feature flag for CPN algorithm |
| `enable_bgt` | bool | True | Feature flag for BGT-SM algorithm |
| `enable_spc` | bool | True | Feature flag for SPC-UQ algorithm |
| `enable_tdl` | bool | True | Feature flag for TDL-HCO algorithm |
| `enable_routine_detector` | bool | True | Feature flag for RoutineDetector |
| `enable_intent_detector` | bool | True | Feature flag for IntentSignalDetector |
| `mcts_rollouts` | int | mode-dependent | MCTS rollout budget (50/200/500/1000 per mode) |
| `bgt_max_walks` | int | 100 | BGT-SM random walk count |
| `bgt_walk_length` | int | 5 | BGT-SM walk depth |
| `novelty_threshold` | float | 0.3 | Minimum novelty score for insight retention |
| `quality_threshold` | float | 0.5 | Minimum quality score for output retention |
| `seed` | Optional[int] | None | Deterministic seeding for reproducibility |

#### DreamConfig (`k0/modules/consolidation/dream/config.py`)

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `max_exploration_time_ms` | int | 5000 | Per-algorithm time limit |
| `min_serendipity` | float | 0.3 | Minimum novelty for BGT-SM insights |
| `max_insights` | int | 10 | Internal insight cap |
| `max_scenarios` | int | 5 | CPN scenario cap |
| `min_scenario_quality` | float | 0.4 | CPN quality threshold |
| `max_prospective` | int | 5 | Prospective memory cap |
| `max_routines` | int | 3 | Routine optimization cap |
| `cpn_*` | various | various | CPN-specific params (perturbation types, chain length, etc.) |
| `mcts_*` | various | various | MCTS-specific params (rollout budget, UCT constant, etc.) |
| `spc_*` | various | various | SPC-UQ-specific params (gap threshold, reconstruction quality) |
| `bgt_*` | various | various | BGT-SM-specific params (walk count, PMI threshold) |

#### R5Mode Enum & Rollout Mapping

```
DISABLED    -> 0 rollouts (R5 skipped entirely)
SHADOW      -> 50 rollouts (run but don't emit outputs to R6)
ENABLED_LOW -> 200 rollouts (conservative exploration)
ENABLED     -> 500-1000 rollouts (full exploration)
```

**Configuration Issues Identified:**

| Issue | Severity | Detail |
|-------|----------|--------|
| Dual config objects | MEDIUM | `R5Config` (phase-level) and `DreamConfig` (orchestrator-level) overlap in parameters. `DreamConfig.from_r5_config()` bridges them but creates confusion about which is authoritative. |
| CPN/MCTS config params orphaned | LOW | Multiple CPN and MCTS config parameters will become dead config after M5C deletion. |
| No observation evidence config | HIGH | Stage 5 algorithms need config for ObservationEvidenceLoader SQL queries, time windows, and per-algorithm thresholds. None exists. |
| ROLLOUTS_PER_MODE is MCTS-specific | MEDIUM | Rollout budget concept is MCTS-specific. New algorithms use different resource models (time budgets, record count limits). |
| `USE_M5_EMITTERS` defaults to False | HIGH | Feature flag in `dream_explorer.py` that gates whether R5 outputs flow to R6/R7. Default False means R5 outputs are silently discarded in production. |

---

### 1.4 Migration Inventory

| Migration | Number | R5 Impact | Status |
|-----------|--------|-----------|--------|
| Core schema | 0022 | Creates st_hipp_events (111 columns), st_vec, st_pipeline_processed | APPLIED |
| P02 NER | 0046 | Adds ner_entities_json, temporal_json, intent_category to st_hipp_events | APPLIED |
| Reconciliation | 0052 | Adds reconciliation columns to st_hipp_events | APPLIED |
| UltraBERT full | 0053 | Adds extracted_relations_json, safety columns | APPLIED |
| UltraBERT activity | 0060 | Adds activity_type_ultrabert, intent_ultrabert | APPLIED |
| st_observations | (unknown) | Creates 32-column append-only observation table. R5's primary evidence source via ObservationEvidenceLoader | APPLIED |
| st_mcts_decisions | (unknown) | Creates MCTS decision tracking table. To be DELETED with MCTS removal | APPLIED |
| st_mcts_shadow_log | (unknown) | Creates MCTS shadow outcome table. To be DELETED with MCTS removal | APPLIED |

**Migrations Required (Stage 5):**

| Migration | Number | Purpose | Status |
|-----------|--------|---------|--------|
| st_anchors table | 0073 | New truth table for Bayesian anchors (ASU algorithm). Columns: anchor_id, anchor_name, distribution_source, alpha, beta, mean, created_at, updated_at, last_evidence_at, drift_detected | NOT CREATED |
| EST columns | 0073 | Add `reinforcement_count` (INT), `last_reinforced_at` (BIGINT) to st_epi | NOT CREATED |
| SRE columns | 0073 | Add `sentiment_trajectory` (TEXT), `emotional_diversity` (FLOAT), `health_score` (FLOAT) to st_social | NOT CREATED |
| MTP columns | 0073 | Add `memory_tier` (TEXT DEFAULT 'TRANSIENT') to st_epi, st_sem, st_social, st_kg_dom, st_procedural | NOT CREATED |
| SPG columns | 0073 | Add `propagated_salience` (FLOAT) to st_kg_dom, st_kg_edges | NOT CREATED |
| MW v2 st_hipp columns | 0065 | 16 new columns for MW v2 cognitive dimensions (narrative_thread_id, affect_dominance, entity_salience_json, etc.) | NOT CREATED |
| st_observations expansion | 0067 | Add MW v2 context columns to observation snapshot (narrative_thread_id, intent_type, novelty, elaboration_depth, temporal_orientation, source_type, identity_domains_json) | NOT CREATED |

---

## Section 2: API Surface Map

### 2.1 Public Functions (Phase Interface)

| Function | File | Signature | Purpose |
|----------|------|-----------|---------|
| `R5DreamExplorer.run()` | `r5_dream_explorer.py` | `async run(cycle_id, phase_inputs, config) -> R5PhaseOutputs` | Phase entry point. Checks skip conditions, loads accumulated data via 7 syscall loaders, delegates to DreamExplorer.explore(), assembles R5PhaseOutputs |
| `R5DreamExplorer.should_skip()` | `r5_dream_explorer.py` | `should_skip(config, phase_inputs) -> Tuple[bool, Optional[str]]` | Evaluates 4 skip conditions: r5_mode disabled, backlog > threshold, timeout exceeded, clusters < minimum |
| `DreamExplorer.explore()` | `dream_explorer.py` | `explore(input: DreamExplorerInput) -> DreamExplorerOutput` | Core orchestrator: 4-phase execution (parallel algorithms, sequential TDL-HCO, quality filters, intent detection) |

### 2.2 Syscall Data Loaders (Phase File)

| Loader | Syscall | Returns | SQL/Source |
|--------|---------|---------|------------|
| `_load_accumulated_entities()` | `syscall.query_kg_entities()` | `List[EntityRow]` | st_kg_dom active entities |
| `_load_accumulated_edges()` | `syscall.query_kg_edges()` | `List[EdgeRow]` | st_kg_edges active edges |
| `_load_accumulated_episodes()` | `syscall.query_episodes()` | `List[EpisodeCluster]` | st_epi active episode clusters |
| `_load_accumulated_routines()` | `syscall.query_routines()` | `List[RoutineRow]` | st_procedural active routines |
| `_load_accumulated_schemas()` | `syscall.query_semantic_patterns()` | `List[SemanticPatternRow]` | st_sem active patterns |
| `_load_accumulated_social()` | NOT IMPLEMENTED | `List[SocialRow]` | st_social -- MISSING LOADER |
| `_load_accumulated_prospective()` | NOT IMPLEMENTED | `List[ProspectiveRow]` | st_prospective -- MISSING LOADER |
| `_load_accumulated_anchors()` | NOT IMPLEMENTED | `List[AnchorRow]` | st_anchors -- MISSING LOADER (table does not exist yet) |

**Note:** 3 of 8 required data loaders are not implemented. These are required by Stage 5 algorithms (SPC-UQ refocused needs prospective, SRE needs social, ASU needs anchors).

### 2.3 Algorithm Public APIs

| Algorithm | Class | Method | Signature | Returns |
|-----------|-------|--------|-----------|---------|
| BGT-SM | `BisociativeGraphTraversal` | `discover()` | `discover(entities, edges, config) -> List[BGTInsight]` | Non-obvious connections via random walk + PMI |
| CPN | `CausalPerturbationNetwork` | `generate()` | `generate(episodes, edges, config) -> List[CounterfactualScenario]` | Counterfactual scenarios via DAG perturbation (DELETE) |
| TPN-MCTS | `TemporalProjectionMCTS` | `simulate()` | `simulate(episodes, entities, edges, config, budget) -> List[MCTSScenario]` | Forward projections via UCT tree search (DELETE) |
| SPC-UQ | `EpisodicSimulator` | `simulate()` | `simulate(episodes, entities, config) -> SPCResult` | Gap identification + Bayesian reconstruction (REFOCUS) |
| TDL-HCO | `TemporalDifferenceLearning` | `optimize()` | `optimize(routines, episodes, config) -> List[RoutineOptimization]` | Bottleneck detection + routine optimization |
| IntentSignalDetector | `IntentSignalDetector` | `detect_all()` | `detect_all(episodes, config) -> List[IntentSignal]` | Regex-based intent extraction for 6 types |
| RoutineDetector | `RoutineDetector` | `detect()` | `detect(episodes, config) -> List[RoutineCandidate]` | Signature grouping + frequency scoring + lifecycle |
| MCTS Shadow | `ShadowOutcomeTracker` | `record() / evaluate()` | `record(prediction) / evaluate(actual)` | Shadow tracking + promotion analysis (DELETE) |

### 2.4 Internal Helper Methods (Phase File)

| Method | File | Purpose |
|--------|------|---------|
| `_execute_algorithms()` | `r5_dream_explorer.py` | Wraps DreamExplorer.explore() with error handling and timeout |
| `_assemble_phase_outputs()` | `r5_dream_explorer.py` | Maps DreamExplorerOutput fields to R5PhaseOutputs dataclass |
| `_emit_r5_metrics()` | `r5_dream_explorer.py` | Emits counter/histogram metrics for R5 execution |
| `_build_dream_input()` | `r5_dream_explorer.py` | Assembles DreamExplorerInput from loaded data |

### 2.5 Internal Helper Methods (Orchestrator)

| Method | File | Purpose |
|--------|------|---------|
| `_run_phase1_parallel()` | `dream_explorer.py` | Concurrent execution of BGT-SM, CPN, SPC-UQ, MCTS, RoutineDetector using ThreadPoolExecutor |
| `_run_phase2_sequential()` | `dream_explorer.py` | Sequential TDL-HCO (depends on RoutineDetector output from Phase 1) |
| `_run_phase3_filters()` | `dream_explorer.py` | Quality filtering: novelty threshold, quality threshold, max limits per output type |
| `_run_phase4_intent()` | `dream_explorer.py` | IntentSignalDetector on filtered episodes |
| `_rank_by_serendipity()` | `dream_explorer.py` | Sort insights by novelty score descending |
| `_filter_low_quality()` | `dream_explorer.py` | Remove outputs below quality threshold |

### 2.6 Classes & Dataclasses

#### Phase-Level Dataclasses

| Dataclass | File | Fields | Frozen | Purpose |
|-----------|------|--------|--------|---------|
| `R5PhaseOutputs` | `r5_dream_explorer.py` | r5_insights, r5_counterfactuals, r5_routine_optimizations, r5_routine_candidates, r5_prospective_memories, r5_intent_signals, r5_mcts_scenarios, r5_skipped, r5_skip_reason | No | Phase output container |

#### Orchestrator Dataclasses

| Dataclass | File | Fields | Frozen | Purpose |
|-----------|------|--------|--------|---------|
| `DreamExplorerInput` | `models.py` | episodes, entities, edges, routines, schemas, config, cycle_id | Yes | Immutable input bundle |
| `DreamExplorerOutput` | `models.py` | insights, counterfactuals, prospective_memories, routine_optimizations, intent_signals, routine_candidates, mcts_scenarios, execution_stats | Yes | Immutable output bundle |
| `Insight` | `models.py` | insight_id, insight_type (BRIDGE/PATTERN/ANOMALY/PREDICTION), concept_a_id, concept_b_id, pmi_score, novelty_score, relevance_score, natural_language, evidence_ids | Yes | BGT-SM output |
| `CounterfactualScenario` | `models.py` | scenario_id, base_episode_id, perturbation_type (TIME/PARTICIPANT/LOCATION/ACTION), perturbation_target, original_outcome, counterfactual_outcome, probability_shift, utility_delta | Yes | CPN output (DELETE) |
| `ProspectiveMemory` | `models.py` | prosp_id, intention_type (GOAL/REMINDER/DEADLINE/HABIT), description, trigger_condition, action_to_take, deadline_ts, importance, source_episode_id, anchor_time_utc, original_temporal_expr | Yes | SPC-UQ / MCTS output |
| `RoutineOptimization` | `models.py` | routine_id, routine_name, bottleneck_step, bottleneck_position, value_drop, suggested_action, expected_improvement | Yes | TDL-HCO output |
| `ComputeBudget` | `compute_budget.py` | total_rollouts, used_rollouts, start_time_ms, max_time_ms | No | MCTS rollout budget tracking (DELETE with MCTS) |
| `AlgorithmResult` | `compute_budget.py` | algorithm_name, success, duration_ms, rollouts_used, error | Yes | Per-algorithm execution result |
| `OrchestrationResult` | `compute_budget.py` | results, total_duration_ms, budget_utilization | Yes | Aggregate execution result |
| `IntentSignalType` | `intent_signals.py` | REMINDER, DECISION, LESSON, EMOTIONAL, MILESTONE, QUERY_BOOST | - | Enum for 6 intent types |
| `IntentSignal` | `intent_signals.py` | signal_type, source_episode_id, text, confidence, metadata | Yes | Base intent signal |
| `ReminderSignal` | `intent_signals.py` | + deadline_ts, recurrence | Yes | Reminder-specific intent |
| `DecisionSignal` | `intent_signals.py` | + options, urgency | Yes | Decision-specific intent |
| `LessonSignal` | `intent_signals.py` | + domain, evidence_ids | Yes | Lesson-specific intent |
| `EmotionalSignal` | `intent_signals.py` | + emotion, intensity, trigger | Yes | Emotional-specific intent |
| `MilestoneSignal` | `intent_signals.py` | + milestone_type, achievement | Yes | Milestone-specific intent |
| `QueryBoostSignal` | `intent_signals.py` | + query_pattern, boost_factor | Yes | Query boost intent |
| `MCTSDecisionRecord` | `mcts_persistence.py` | decision_id, cycle_id, decision_type, episodes, scenarios, chosen_action, confidence, termination_reason | Yes | MCTS decision record (DELETE) |
| `ObservationContext` | `observation_context.py` | ~35 fields across 8 categories (Identity, Type, Temporal, Emotional, Salience, Modality, Physical, Social, Prospective) | Yes | Observation snapshot for st_observations rows |

#### Algorithm-Specific Dataclasses

| Dataclass | File | Key Fields | Purpose |
|-----------|------|------------|---------|
| `BGTConfig` | `bgt_sm.py` | max_walks, walk_length, pmi_threshold, min_serendipity | BGT-SM configuration |
| `BGTInsight` | `bgt_sm.py` | concept_a, concept_b, pmi, novelty, path | BGT-SM raw insight |
| `KnowledgeGraphView` | `bgt_sm.py` | adjacency, weights, entity_map | Graph abstraction for random walks |
| `EmbeddingCache` | `bgt_sm.py` | cache dict, hit/miss counters | Embedding lookup cache |
| `CausalDAG` | `cpn.py` | nodes, edges, adjacency | CPN directed acyclic graph (DELETE) |
| `CausalNode` | `cpn.py` | node_id, episode_id, attributes | CPN graph node (DELETE) |
| `CausalEdge` | `cpn.py` | source, target, weight, edge_type | CPN graph edge (DELETE) |
| `MCTSNode` | `mcts.py` | state, parent, children, visits, value, UCT | MCTS tree node (DELETE) |
| `MCTSConfig` | `mcts.py` | rollout_budget, uct_constant, max_depth | MCTS configuration (DELETE) |
| `MCTSScenario` | `mcts.py` | scenario_id, episodes, projections, confidence | MCTS output (DELETE) |
| `SemanticPatternData` | `spc_uq.py` | pattern_id, description, frequency, confidence | SPC-UQ pattern input |
| `SPCResult` | `spc_uq.py` | gaps, reconstructions, conflicts | SPC-UQ output bundle |
| `ValueFunction` | `tdl_hco.py` | values dict, learning_rate, discount | TDL-HCO TD value function |
| `RoutineCandidate` | `routine_detector.py` | routine_id, name, frequency, regularity, lifecycle, signature | Detected routine pattern |
| `DreamConfig` | `config.py` | ~25 exploration/quality/algorithm params | Orchestrator configuration |

#### Phase Output Dataclasses (from `phase_outputs.py`)

Defined at lines 497-573 of `k0/pipelines/p03/phase_outputs.py`:

| Dataclass | Fields | Target Table |
|-----------|--------|--------------|
| `CounterfactualScenario` | scenario_id, base_episode_id, perturbation_type, perturbation_target, original_outcome, counterfactual_outcome, probability_shift, utility_delta | st_prospective (DELETE) |
| `Insight` | insight_id, insight_type, concept_a_id, concept_b_id, pmi_score, novelty_score, relevance_score, natural_language, evidence_ids | st_sem |
| `RoutineOptimization` | routine_id, routine_name, bottleneck_step, bottleneck_position, value_drop, suggested_action, expected_improvement | st_procedural |
| `ProspectiveMemory` | prosp_id, intention_type, description, trigger_condition, action_to_take, deadline_ts, importance, source_episode_id, anchor_time_utc, original_temporal_expr | st_prospective |

R5 fields on `P03PhaseOutputs` (lines 782-790):

| Field | Type |
|-------|------|
| `r5_counterfactuals` | `List[CounterfactualScenario]` |
| `r5_insights` | `List[Insight]` |
| `r5_routine_optimizations` | `List[RoutineOptimization]` |
| `r5_routine_candidates` | `List[RoutineCandidate]` |
| `r5_prospective_memories` | `List[ProspectiveMemory]` |
| `r5_intent_signals` | `List[IntentSignal]` |
| `r5_mcts_scenarios` | `List[MCTSScenario]` |
| `r5_skipped` | `bool` |
| `r5_skip_reason` | `Optional[str]` |

---

## Section 3: Algorithm Inventory

### 3.1 Current Algorithm Registry

| # | Algorithm | Class | File | Lines | Status | Phase | Input Sources | Output Type | Target Table | Complexity | Latency (est.) | Deterministic | Cold-Start Safe | Observation-Driven | Known Issues |
|---|-----------|-------|------|------:|--------|-------|---------------|-------------|--------------|------------|-----------------|---------------|-----------------|--------------------|--------------|
| 1 | **BGT-SM** | `BisociativeGraphTraversal` | `bgt_sm.py` | 1,208 | KEEP | Phase 1 (parallel) | st_kg_dom entities, st_kg_edges | `List[Insight]` | st_sem | O(W *L* d) where W=walks, L=length, d=degree | 200-500ms | Yes (seeded) | Yes (returns empty) | No (graph-based) | 82% of edges near-zero weight degrades walk quality; PMI calculation on sparse co-occurrence matrix; EmbeddingCache unbounded growth |
| 2 | **CPN** | `CausalPerturbationNetwork` | `cpn.py` | 1,106 | DELETE | Phase 1 (parallel) | st_epi episodes, st_kg_edges | `List[CounterfactualScenario]` | st_prospective | O(N *P* E) where N=nodes, P=perturbations, E=edges | 300-800ms | Yes (seeded) | No (needs episodes) | No | All modifiability=MODIFIABLE (simplified heuristic); produces 70 nonsense counterfactuals; DAG construction from episode ordering is naive; LLM+context strictly superior for counterfactual reasoning |
| 3 | **TPN-MCTS** | `TemporalProjectionMCTS` | `mcts.py` | 1,113 | DELETE | Phase 1 (parallel) | st_epi episodes, st_kg_dom entities, st_kg_edges | `List[MCTSScenario]` | st_prospective | O(R * D) where R=rollouts, D=depth | 500-2000ms | Yes (seeded) | No (needs episodes) | No | No meaningful game tree (state space undefined for personal memory); UCT exploration constant not calibrated; early termination heuristics untested; forward simulation has no grounding model |
| 4 | **SPC-UQ** | `EpisodicSimulator` | `spc_uq.py` | 1,253 | REFOCUS | Phase 1 (parallel) | st_epi episodes, st_kg_dom entities | `SPCResult` | st_prospective, st_epi | O(E^2) for gap detection | 200-600ms | Yes (seeded) | Yes (returns empty) | No (episode-based) | CRITICAL invariant A.0.6: is_canonical=False on reconstructions; gap detection is pairwise O(n^2); Bayesian reconstruction quality unvalidated; conflict detection simplistic |
| 5 | **TDL-HCO** | `TemporalDifferenceLearning` | `tdl_hco.py` | 1,025 | KEEP | Phase 2 (sequential) | st_procedural routines, st_epi episodes | `List[RoutineOptimization]` | st_procedural | O(R * S) where R=routines, S=steps | <100ms | Yes | Yes (returns empty) | No (routine-based) | Depends on RoutineDetector output from Phase 1; ValueFunction not persisted across cycles; bottleneck detection heuristic-based |
| 6 | **IntentSignalDetector** | `IntentSignalDetector` | `intent_signal_detector.py` | 631 | ACTIVE | Phase 4 (post-filter) | st_epi episodes (filtered) | `List[IntentSignal]` | routing only | O(E * P) where E=episodes, P=patterns | <50ms | Yes | Yes (returns empty) | No (regex-based) | Output not wired to R6/R7 truth writers; regex patterns are English-only; TemporalParser integration for deadline extraction; false positive rate unknown |
| 7 | **RoutineDetector** | `RoutineDetector` | `routine_detector.py` | 710 | ACTIVE | Phase 1 (parallel) | st_epi episodes | `List[RoutineCandidate]` | st_procedural | O(E * log E) for signature sort | <100ms | Yes | Yes (returns empty) | No (episode-based) | Lifecycle detection thresholds uncalibrated; signature grouping is activity_type + time_bucket only; frequency scoring assumes uniform distribution |
| 8 | **MCTS Shadow** | `ShadowOutcomeTracker` | `mcts_shadow.py` | 918 | DELETE | Background | MCTS predictions | shadow log | st_mcts_shadow_log | O(P) per prediction | <10ms | Yes | N/A | No | Dead code once MCTS removed; promotion analysis never triggered in real data; SQL writes to st_mcts_shadow_log |
| 9 | **ComputeBudget** | `ComputeBudget` | `compute_budget.py` | 289 | REWORK | Cross-cutting | R5Config mode | Budget tracking | N/A | O(1) | <1ms | Yes | N/A | No | MCTS-specific rollout model; does not account for non-MCTS algorithm costs; elapsed time tracking but no per-algorithm budget enforcement |

### 3.2 Algorithm Gap Analysis (Stage 5 Proposed Additions)

The Stage 5 Refinement Proposal introduces 10 new observation-driven algorithms organized in 5 execution phases. All algorithms share a common dependency on `ObservationEvidenceLoader` which queries st_observations via 3 SQL aggregation queries.

| # | Algorithm | Acronym | Purpose | Phase | Input Sources | Output Type | Target Table | Observation-Driven | Status |
|---|-----------|---------|---------|-------|---------------|-------------|--------------|--------------------|---------|
| 10 | **Episodic Strength Tracker** | EST | Break flat salience: two-tier reinforcement (observation count + heuristic matching). Logarithmic scaling log2(1+count), emotional diversity bonus (McGaugh 2004). | Phase 1 (parallel) | st_observations record_stats, st_epi | `List[EpisodicStrengthUpdate]` | st_epi.salience_score, st_epi.reinforcement_count | YES | NOT IMPLEMENTED |
| 11 | **Anchor Seeding & Update** | ASU | Bayesian anchor system from observation distributions. Beta-Bernoulli model (alpha=support+1, beta=oppose+1). 9 pre-defined DistributionAnchorSpecs. Temporal decay, drift detection. | Phase 1 (parallel) | st_observations distributions, st_anchors | `List[AnchorUpdate]` | st_anchors | YES | NOT IMPLEMENTED |
| 12 | **Semantic Pattern Reinforcement** | SPR | Break flat confidence=0.80. Two-signal model: observation reinforcement (primary) + specificity scoring (secondary). Pattern deduplication via text similarity. | Phase 1 (parallel) | st_observations record_stats, st_sem | `List[SemanticPatternUpdate]`, `List[PatternMerge]` | st_sem.confidence | YES | NOT IMPLEMENTED |
| 13 | **Social Relationship Enrichment** | SRE | Per-entity emotional context from observations. Sentiment aggregation, trajectory (IMPROVING/STABLE/DECLINING), emotional diversity (Shannon entropy), health score. | Phase 1 (parallel) | st_observations entity_observations, st_social | `List[SocialRelationshipUpdate]` | st_social.sentiment, st_social.sentiment_trajectory, st_social.emotional_diversity, st_social.health_score | YES | NOT IMPLEMENTED |
| 14 | **Edge Weight Refinement** | EWR | Multi-enricher boost, co-occurrence reinforcement, noise demotion. No temporal edge creation (R4 owns that). | Phase 2 (sequential) | st_kg_edges (post-Phase 1), st_epi, R4 enricher metadata | `List[EdgeWeightUpdate]` | st_kg_edges.weight | PARTIAL (uses episode salience) | NOT IMPLEMENTED |
| 15 | **SPC-UQ Refocused** | SPC-UQ v2 | Shift from generation to cleanup: counterfactual purge, observation-based completion/staleness, deduplication. | Phase 2 (sequential) | st_observations record_stats, st_prospective | `List[ProspectiveUpdate]`, `List[ProspectiveMerge]`, `List[ProspectiveMemory]` | st_prospective | YES | NOT IMPLEMENTED (current SPC-UQ is generation-focused) |
| 16 | **Cross-Layer Coherence Verification** | CLV | Semantic referential integrity across truth tables. 6 check types: orphan entities, dangling edges, ungrounded social, orphan patterns, social-entity mismatch. Set intersection operations on loaded data. | Phase 3 (parallel) | All accumulated data + st_observations | `List[CoherenceRepair]` | Various (FLAG/ARCHIVE/SEED/DEMOTE) | PARTIAL | NOT IMPLEMENTED |
| 17 | **Contradiction Detection** | CTD | Find real contradictions and resolve via observation evidence tiebreaker. 3 types: fact conflict, sentiment mismatch, temporal impossibility. Replaces CPN. | Phase 3 (parallel) | st_kg_dom, st_social, st_epi, st_observations | `List[Contradiction]` | Various (DEMOTE_LOSER/ARCHIVE_LOSER/FORCE_RECALC) | YES | NOT IMPLEMENTED |
| 18 | **Memory Tier Promotion** | MTP | Assign tiers (TRANSIENT/ACTIVE/STABLE/CORE) based on reinforcement count + age. Higher tiers get reduced R3 decay. | Phase 5 (sequential) | st_observations record_stats | `List[TierPromotion]` | memory_tier on st_epi, st_sem, st_social, st_kg_dom, st_procedural | YES | NOT IMPLEMENTED |
| 19 | **Episode Compression** | EPC | Compress recurring similar episodes into composites with frequency metadata. Entity overlap grouping + text similarity clustering. Only low-salience episodes compressed. | Phase 4 (parallel) | st_epi (post-Phase 1 EST), st_observations | `List[CompositeEpisode]`, `List[EpisodeArchival]` | st_epi | PARTIAL | NOT IMPLEMENTED |
| 20 | **Salience Propagation through Graph** | SPG | Single-hop propagation: Episode->Entity->Edge. Not PageRank (too expensive). Gives entities and edges importance scores. | Phase 4 (parallel) | st_epi (post-EST), st_kg_dom, st_kg_edges (post-EWR) | `List[EntitySalienceUpdate]`, `List[EdgeSalienceUpdate]` | st_kg_dom.propagated_salience, st_kg_edges.propagated_salience | No (graph-based) | NOT IMPLEMENTED |
| 21 | **Narrative Thread Detection** | NTD | Discover causal/temporal chains across episodes forming coherent stories. Emotional arc detection. Pre-labeled by MW v2 thread_id. | Phase 4 (parallel) | st_epi, st_kg_edges (temporal/causal), st_kg_dom | `List[NarrativeThread]` | st_sem (type=NARRATIVE_THREAD) | No (episode chain) | NOT IMPLEMENTED |

### 3.3 Algorithm Execution Phase Map (Stage 5 Target)

```
Phase 0: ObservationEvidenceLoader (shared infrastructure, 3 SQL queries, ~150ms)
          |
Phase 1 (Parallel): EST, ASU, SPR, SRE
          |         ~200ms each, all read observation evidence independently
          |
Phase 2 (Sequential): EWR (needs EST salience updates), SPC-UQ v2
          |            ~150ms each
          |
Phase 3 (Parallel): CLV, CTD
          |          ~100ms each, cross-layer verification + contradiction detection
          |
Phase 4 (Parallel): EPC (needs EST), SPG (needs EST + EWR), NTD
          |          ~200ms each
          |
Phase 5 (Sequential): TDL-HCO (unchanged), MTP (needs all Phase 1-4 evidence), BGT-SM (benefits from EWR)
                       ~100ms each

Estimated total: ~1,200ms (within 2,000ms contract budget)
```

### 3.4 Algorithm Dependency Graph

```
ObservationEvidenceLoader
  +-> EST (reads obs record_stats for st_epi)
  |     +-> EWR (uses EST-updated episode salience for co-occurrence boost)
  |     |     +-> BGT-SM (benefits from EWR-cleaned edge weights)
  |     |     +-> SPG (uses EWR-updated edge weights)
  |     +-> EPC (uses EST-updated episode salience for compression threshold)
  |     +-> SPG (uses EST-updated episode salience for propagation)
  +-> ASU (reads obs distributions)
  +-> SPR (reads obs record_stats for st_sem)
  +-> SRE (reads obs entity_observations)
  +-> SPC-UQ v2 (reads obs record_stats for st_prospective)
  +-> CLV (reads all accumulated data + obs)
  +-> CTD (reads obs entity_observations + record_stats)
  +-> MTP (reads obs record_stats across all layers)
  +-> NTD (reads episodes, edges, entities -- no direct obs dependency)
  +-> TDL-HCO (reads routines, episodes -- no obs dependency)
```

### 3.5 Critical Algorithm Issues (from Stage 5 Corrections)

| Issue ID | Severity | Algorithm | Description |
|----------|----------|-----------|-------------|
| CORR-001 | CRITICAL | ASU / SPR | **Name confusion between Section 4 and Section 13 of proposal.** In Section 4: ASU = "Anchor Seeding & Update", SPR = "Semantic Pattern Reinforcement". In Section 13: ASU becomes "Adaptive Schema Updater" (completely different algorithm), SPR becomes "Stale Prediction Reaper" (completely different algorithm). The Section 4 definitions are authoritative. |
| CORR-002 | CRITICAL | EST, ASU, EWR, SRE, SPR | **Output dataclass conflicts between Section 4 and Section 13.14.** Section 4 defines clean frozen dataclasses. Section 13.14 defines different dataclasses with overlapping but incompatible field sets. Section 4 definitions are authoritative. |
| CORR-003 | CRITICAL | All Phase 1-5 | **Phase execution order contradictions between Section 5 and Section 13.8.** Section 5 describes 5-phase sequential-parallel execution. Section 13.8 describes a different 4-phase structure. Section 5 is authoritative. |
| CORR-004 | HIGH | SPC-UQ v2, SRE, ASU | **Missing data loaders.** `_load_accumulated_social()`, `_load_accumulated_prospective()`, `_load_accumulated_anchors()` are not implemented in the phase file. Required by SPC-UQ v2 (prospective), SRE (social), ASU (anchors). |
| CORR-005 | HIGH | ASU | **Missing st_anchors infrastructure.** No P03StagedWrites bucket for st_anchors, no AnchorLayerWriter, no routing in R6/R7. Table itself requires migration 0073. |
| CORR-006 | HIGH | EST, SRE, MTP, SPG | **Missing database migrations.** Columns required: reinforcement_count + last_reinforced_at (st_epi), sentiment_trajectory + emotional_diversity + health_score (st_social), memory_tier (5 tables), propagated_salience (st_kg_dom + st_kg_edges). All in proposed migration 0073. |
| CORR-007 | MEDIUM | EPC, NTD | **Stubbed methods.** EPC._synthesize_description(), NTD._synthesize_narrative(), EPC._cluster_by_similarity() are described but implementation is `...` (ellipsis). |
| CORR-008 | MEDIUM | All | **Cold-start/empty evidence behavior undocumented.** What happens when st_observations has 0 rows? Each algorithm needs explicit empty-evidence behavior. |
| CORR-009 | MEDIUM | EST, ASU, SPR, SRE, MTP | **Self-reinforcing loop convergence not proven.** R5 updates -> R7 writes REINFORCEMENT observations -> next R5 cycle sees more evidence -> stronger updates. Theoretical convergence never analyzed. Risk of runaway amplification. |
| CORR-010 | HIGH | All | **Missing governance artifacts.** No ADRs created for Stage 5 design decisions. No contract YAMLs for new algorithms. No architecture master updates. |
| CORR-011 | MEDIUM | MTP | **R3 integration unspecified.** MTP sets memory_tier on records. R3 must read this tier and apply decay_multiplier. No changes to R3 decay logic documented. |

---

## Section 4: Data Flow & I/O Map

### 4.1 Pipeline Stage Map

R5 sits between R4 (Edge Enrichment) and R6 (Merge Arbitration) in the P03 pipeline:

```
R0 (Event Expansion)
  -> R1 (Scoring & Salience)
    -> R2 (Episode Clustering)
      -> R3 (Decay & Dedup)
        -> R4 (Edge Enrichment)
          -> R5 (Dream Exploration)    <-- THIS PHASE
            -> R6 (Merge Arbitration)
              -> R7 (Truth Writing)
                -> R8 (Event Emission)
```

**R5 Entry Conditions:**

| Condition | Check | Skip If |
|-----------|-------|---------|
| R5 mode | `r5_config.r5_mode` | `== DISABLED` |
| Backlog | `len(pending_events)` | `> backlog_threshold (1000)` |
| Timeout | `elapsed_seconds` | `> max_r5_seconds (120)` |
| Minimum clusters | `len(r2_clusters)` | `< min_clusters_for_r5 (2)` |

**R5 Exit Contract:**

R5 produces `R5PhaseOutputs` containing up to 7 output lists. These are passed to R6 which applies merge arbitration (conflict resolution, deduplication) before R7 writes to truth tables. If R5 is skipped, `r5_skipped=True` and all output lists are empty.

### 4.2 Input Schemas

#### Primary Inputs (from R0-R4 pipeline state)

| Input | Source Phase | Type | Loaded By | SQL Source |
|-------|-------------|------|-----------|------------|
| Episode clusters | R2 | `List[EpisodeCluster]` | `_load_accumulated_episodes()` | st_epi WHERE status='ACTIVE' |
| KG entities | R4 | `List[EntityRow]` | `_load_accumulated_entities()` | st_kg_dom WHERE status='ACTIVE' |
| KG edges | R4 | `List[EdgeRow]` | `_load_accumulated_edges()` | st_kg_edges WHERE status='ACTIVE' |
| Routines | R3/prior cycles | `List[RoutineRow]` | `_load_accumulated_routines()` | st_procedural WHERE type='ROUTINE' |
| Semantic patterns | R2/prior cycles | `List[SemanticPatternRow]` | `_load_accumulated_schemas()` | st_sem WHERE status='ACTIVE' |
| Social graph | Prior cycles | `List[SocialRow]` | NOT IMPLEMENTED | st_social WHERE status='ACTIVE' |
| Prospective items | Prior cycles | `List[ProspectiveRow]` | NOT IMPLEMENTED | st_prospective WHERE status IN ('ACTIVE','STALE') |
| Anchor priors | Prior cycles | `List[AnchorRow]` | NOT IMPLEMENTED | st_anchors (table does not exist) |

#### Observation Evidence Inputs (Stage 5 -- shared infrastructure)

| Query | SQL Pattern | Returns | Used By |
|-------|-------------|---------|---------|
| `_RECORD_STATS_SQL` | `SELECT layer, record_id, COUNT(*), COUNT(CASE WHEN observation_type='REINFORCEMENT'), MIN(observed_at), MAX(observed_at), COUNT(DISTINCT dominant_emotion), AVG(salience_score), ... FROM st_observations GROUP BY layer, record_id` | `Dict[(layer, record_id), RecordObservationStats]` with 12 aggregate fields | EST, ASU, SPR, SRE, SPC-UQ v2, CLV, CTD, MTP |
| `_DISTRIBUTION_SQL` | `SELECT social_context, COUNT(*) FROM st_observations GROUP BY social_context` (repeated for 6 distribution types: social, emotion, location, circadian, channel, activity) | `ObservationEvidence.social_distribution`, `.emotion_distribution`, `.location_distribution`, `.circadian_distribution`, `.channel_distribution`, `.activity_distribution` | ASU (all 6 for anchor specs) |
| `_ENTITY_OBSERVATIONS_SQL` | `SELECT entity_id, sentiment_score, affect_valence, dominant_emotion, observed_at FROM st_observations WHERE entity_id IS NOT NULL` | `Dict[entity_id, List[EntityObservation]]` | SRE, CTD |

### 4.3 Output Schemas

#### R5 Output Type Registry

| # | Output Type | Dataclass | Max Count | Target Table | Write Operation | R6 Arbitration | R7 Writer |
|---|-------------|-----------|----------:|--------------|-----------------|----------------|-----------|
| 1 | Insights | `Insight` | 20 | st_sem | INSERT | Dedup by concept pair | SemanticLayerWriter |
| 2 | Counterfactual Scenarios | `CounterfactualScenario` | 10 | st_prospective | INSERT | None (DELETE algorithm) | ProspectiveLayerWriter |
| 3 | Routine Optimizations | `RoutineOptimization` | 5 | st_procedural | UPDATE | Merge by routine_id | ProceduralLayerWriter |
| 4 | Routine Candidates | `RoutineCandidate` | unbounded | st_procedural | INSERT | Dedup by signature | ProceduralLayerWriter |
| 5 | Prospective Memories | `ProspectiveMemory` | 10 | st_prospective | INSERT | Dedup by trigger | ProspectiveLayerWriter |
| 6 | Intent Signals | `IntentSignal` | unbounded | routing only | N/A | N/A | NOT WIRED to R7 |
| 7 | MCTS Scenarios | `MCTSScenario` | mode-dependent | st_prospective | INSERT | None (DELETE algorithm) | ProspectiveLayerWriter |

#### Stage 5 NEW Output Types (Not Yet Implemented)

| # | Output Type | Dataclass | Target Table | Write Operation |
|---|-------------|-----------|--------------|-----------------|
| 8 | Episodic Strength Updates | `EpisodicStrengthUpdate` | st_epi | UPDATE salience_score, reinforcement_count, last_reinforced_at |
| 9 | Anchor Updates | `AnchorUpdate` | st_anchors | UPSERT alpha, beta, mean, drift_detected |
| 10 | Semantic Pattern Updates | `SemanticPatternUpdate` | st_sem | UPDATE confidence |
| 11 | Pattern Merges | `PatternMerge` | st_sem | ARCHIVE remove_id |
| 12 | Social Relationship Updates | `SocialRelationshipUpdate` | st_social | UPDATE sentiment, trajectory, diversity, health_score |
| 13 | Edge Weight Updates | `EdgeWeightUpdate` | st_kg_edges | UPDATE weight |
| 14 | Prospective Updates | `ProspectiveUpdate` | st_prospective | UPDATE status, confidence |
| 15 | Prospective Merges | `ProspectiveMerge` | st_prospective | MERGE keep + archive |
| 16 | Coherence Repairs | `CoherenceRepair` | Various | FLAG/ARCHIVE/SEED/DEMOTE per issue type |
| 17 | Contradictions | `Contradiction` | Various | DEMOTE_LOSER/ARCHIVE_LOSER/FORCE_RECALC |
| 18 | Tier Promotions | `TierPromotion` | st_epi, st_sem, st_social, st_kg_dom, st_procedural | UPDATE memory_tier |
| 19 | Composite Episodes | `CompositeEpisode` | st_epi | INSERT composite + ARCHIVE sources |
| 20 | Episode Archivals | `EpisodeArchival` | st_epi | ARCHIVE (absorbed into composite) |
| 21 | Entity Salience Updates | `EntitySalienceUpdate` | st_kg_dom | UPDATE propagated_salience |
| 22 | Edge Salience Updates | `EdgeSalienceUpdate` | st_kg_edges | UPDATE propagated_salience |
| 23 | Narrative Threads | `NarrativeThread` | st_sem (type=NARRATIVE_THREAD) | INSERT |

### 4.4 Error Output Schemas

| Error Condition | Handling | Output |
|-----------------|----------|--------|
| Algorithm timeout | Per-algorithm try/except with max_exploration_time_ms | AlgorithmResult(success=False, error="timeout") logged; other algorithms continue |
| Algorithm exception | Caught at orchestrator level | AlgorithmResult(success=False, error=str(e)) logged; other algorithms continue |
| R5 phase timeout | Checked in should_skip() before execution | R5PhaseOutputs(r5_skipped=True, r5_skip_reason="timeout") |
| Empty input (no clusters) | Checked in should_skip() | R5PhaseOutputs(r5_skipped=True, r5_skip_reason="insufficient_clusters") |
| Data loader failure | Per-loader try/except | Logged; empty list used as fallback. R5 runs with partial data. |
| Observation evidence empty | NOT HANDLED | Stage 5 gap: each algorithm needs explicit empty-evidence behavior |

### 4.5 Data Transformation Map

```
Input Transformations:
  st_epi rows -> EpisodeCluster objects (via syscall)
  st_kg_dom rows -> EntityRow objects (via syscall)
  st_kg_edges rows -> EdgeRow objects (via syscall)
  st_procedural rows -> RoutineRow objects (via syscall)
  st_sem rows -> SemanticPatternRow objects (via syscall)
  st_observations rows -> ObservationEvidence (via ObservationEvidenceLoader, 3 SQL queries)

Internal Transformations:
  EntityRow + EdgeRow -> KnowledgeGraphView (BGT-SM adjacency matrix)
  EpisodeCluster list -> CausalDAG (CPN, via temporal ordering) [DELETE]
  EpisodeCluster list -> MCTSNode tree (MCTS, via UCT expansion) [DELETE]
  EpisodeCluster list -> routine signatures (RoutineDetector, via activity_type + time_bucket grouping)
  RoutineCandidate + EpisodeCluster -> ValueFunction (TDL-HCO, via TD updates)

Output Transformations:
  BGTInsight -> Insight (field mapping + insight_type classification)
  RoutineCandidate -> RoutineOptimization (via TDL-HCO bottleneck detection)
  SPCResult.gaps -> ProspectiveMemory (via gap-to-intention mapping)
  IntentSignal subclasses -> routing metadata (NOT persisted to truth tables)

Stage 5 NEW Transformations:
  ObservationEvidence.record_stats -> EpisodicStrengthUpdate (EST: log2 scaling + diversity bonus)
  ObservationEvidence.distributions -> AnchorUpdate (ASU: Beta-Bernoulli model)
  ObservationEvidence.record_stats -> SemanticPatternUpdate (SPR: observation_factor + specificity_factor)
  ObservationEvidence.entity_observations -> SocialRelationshipUpdate (SRE: sentiment aggregation + Shannon entropy)
  EpisodeCluster + ObservationEvidence -> CompositeEpisode (EPC: entity overlap + similarity clustering)
  EpisodeCluster salience -> EntitySalienceUpdate -> EdgeSalienceUpdate (SPG: single-hop propagation)
  EpisodeCluster chain -> NarrativeThread (NTD: temporal ordering + emotional arc detection)
  All layer record_stats -> TierPromotion (MTP: reinforcement count + age thresholds)
```

---

## Section 5: Storage & Persistence

### 5.1 Tables Touched by R5

| Table | Read | Write | Purpose in R5 |
|-------|------|-------|----------------|
| `st_epi` | YES | YES (via R7) | Episode clusters: primary input for most algorithms. EST writes salience updates. EPC writes composites + archives sources. |
| `st_sem` | YES | YES (via R7) | Semantic patterns: input for SPR. BGT-SM writes insights. SPR writes confidence updates + merges. NTD writes narrative threads. |
| `st_kg_dom` | YES | YES (via R7) | KG entities: input for BGT-SM, CPN, MCTS, CLV, CTD, SPG. SPG writes propagated_salience. |
| `st_kg_edges` | YES | YES (via R7) | KG edges: input for BGT-SM, CPN, MCTS, EWR, CLV, NTD. EWR writes weight updates. SPG writes propagated_salience. |
| `st_procedural` | YES | YES (via R7) | Routines: input for TDL-HCO. RoutineDetector writes candidates. TDL-HCO writes optimizations. MTP writes memory_tier. |
| `st_prospective` | YES (Stage 5) | YES (via R7) | Prospective memories: CPN/MCTS write scenarios (DELETE). SPC-UQ writes intentions. SPC-UQ v2 writes updates/merges. |
| `st_social` | YES (Stage 5) | YES (via R7) | Social graph: input for SRE, CLV, CTD. SRE writes sentiment/trajectory/diversity/health updates. |
| `st_anchors` | YES (Stage 5) | YES (via R7) | Bayesian anchors: input for ASU. ASU writes anchor updates. TABLE DOES NOT EXIST YET (migration 0073). |
| `st_observations` | YES (Stage 5) | NO (R7 writes) | Observation log: primary evidence source for all Stage 5 algorithms via ObservationEvidenceLoader. R5 reads only. |
| `st_mcts_decisions` | NO | YES | MCTS decision tracking. Written by MCTSDecisionPersistence. DELETE with MCTS. |
| `st_mcts_shadow_log` | YES | YES | MCTS shadow outcome tracking. Written by ShadowOutcomeTracker. DELETE with MCTS. |
| `st_hipp_events` | NO | NO | R5 does NOT read st_hipp_events directly. All evidence flows through st_observations. |

### 5.2 Column-Level Detail

#### st_epi Columns Used by R5

| Column | Read | Write | Algorithm | Purpose |
|--------|------|-------|-----------|---------|
| `episode_id` | YES | - | All | Primary key for episode identification |
| `salience_score` | YES | YES (EST) | EST, EPC, SPG | Current salience; EST updates based on observation evidence |
| `temporal_start` | YES | - | NTD, EPC, CTD | Episode temporal ordering |
| `temporal_end` | YES | - | NTD, CTD | Episode boundary detection |
| `entity_ids` | YES | - | NTD, EPC, SPG | Entity participation in episodes |
| `sentiment_score` | YES | - | EPC | Composite sentiment averaging |
| `dominant_emotion` | YES | - | EPC | Composite emotion detection |
| `cluster_confidence` | YES | - | Quality filter | Minimum quality threshold |
| `semantic_pattern_ids` | YES | - | CLV | Orphan pattern detection |
| `reinforcement_count` | - | YES (EST) | EST | NEW COLUMN: observation reinforcement count |
| `last_reinforced_at` | - | YES (EST) | EST | NEW COLUMN: timestamp of last reinforcement |
| `memory_tier` | - | YES (MTP) | MTP | NEW COLUMN: TRANSIENT/ACTIVE/STABLE/CORE |
| `location_name` | YES | - | CTD | Temporal impossibility check (different locations) |

#### st_sem Columns Used by R5

| Column | Read | Write | Algorithm | Purpose |
|--------|------|-------|-----------|---------|
| `pattern_id` | YES | - | SPR, CLV | Primary key |
| `description` | YES | - | SPR | Specificity scoring (causal/action language analysis) |
| `confidence` | YES | YES (SPR) | SPR | Current confidence; SPR updates based on observation + specificity |
| `pattern_type` | YES | - | SPR | Type bonus in specificity (LESSON > EMOTIONAL_TREND) |
| `insight_id` | - | YES (BGT-SM) | BGT-SM | INSERT new insights |
| `thread_id` | - | YES (NTD) | NTD | INSERT narrative threads (type=NARRATIVE_THREAD) |

#### st_social Columns Used by R5

| Column | Read | Write | Algorithm | Purpose |
|--------|------|-------|-----------|---------|
| `entity_id` | YES | - | SRE, CLV, CTD | Primary key for social entries |
| `name` | YES | - | CLV | Human-readable in coherence reports |
| `sentiment_score` | YES | YES (SRE) | SRE, CTD | Current sentiment; SRE recalculates from observations |
| `sentiment_trajectory` | - | YES (SRE) | SRE | NEW COLUMN: IMPROVING/STABLE/DECLINING |
| `emotional_diversity` | - | YES (SRE) | SRE | NEW COLUMN: Shannon entropy of emotion distribution |
| `health_score` | - | YES (SRE) | SRE | NEW COLUMN: frequency *sentiment* recency |

#### st_kg_dom Columns Used by R5

| Column | Read | Write | Algorithm | Purpose |
|--------|------|-------|-----------|---------|
| `entity_id` | YES | - | BGT-SM, CLV, CTD, SPG | Primary key |
| `label` | YES | - | CLV | Human-readable in coherence reports |
| `entity_type` | YES | - | CLV | Person entity detection for social-entity mismatch |
| `attributes` | YES | - | CTD | Fact conflict detection (same attribute, different values) |
| `propagated_salience` | - | YES (SPG) | SPG | NEW COLUMN: salience derived from connected episodes |

#### st_kg_edges Columns Used by R5

| Column | Read | Write | Algorithm | Purpose |
|--------|------|-------|-----------|---------|
| `edge_id` | YES | - | CLV, EWR, SPG | Primary key |
| `source_id` | YES | - | BGT-SM, CLV, SPG | Edge endpoint |
| `target_id` | YES | - | BGT-SM, CLV, SPG | Edge endpoint |
| `weight` | YES | YES (EWR) | BGT-SM, EWR | Walk probability; EWR refines based on enricher analysis |
| `enricher_sources` | YES | - | EWR | Multi-enricher detection for boost |
| `propagated_salience` | - | YES (SPG) | SPG | NEW COLUMN: salience from endpoint entities |

#### st_observations Columns Read by R5 (via ObservationEvidenceLoader)

| Column | Used In Query | Algorithm Impact |
|--------|--------------|------------------|
| `layer` | _RECORD_STATS_SQL GROUP BY | All -- identifies which truth table the observation relates to |
| `record_id` | _RECORD_STATS_SQL GROUP BY | All -- identifies which record within the table |
| `observation_type` | COUNT(CASE WHEN 'REINFORCEMENT') | EST, SPR, MTP -- reinforcement counting |
| `observed_at` | MIN(), MAX() | EST recency, ASU temporal decay, SPR recency factor |
| `dominant_emotion` | COUNT(DISTINCT) | EST emotional diversity, ASU emotion distribution |
| `salience_score` | AVG() | EST aggregated salience |
| `social_context` | _DISTRIBUTION_SQL GROUP BY | ASU social distribution for anchor specs |
| `location_type` | _DISTRIBUTION_SQL GROUP BY | ASU location distribution |
| `circadian_slot` | _DISTRIBUTION_SQL GROUP BY | ASU circadian distribution |
| `sentiment_score` | Per-entity aggregation | SRE sentiment averaging |
| `affect_valence` | Per-entity aggregation | SRE emotional context |
| `entity_id` | _ENTITY_OBSERVATIONS_SQL WHERE | SRE, CTD -- per-entity observation trail |

### 5.3 Query Patterns

| Pattern | Table | Query Type | Frequency | Estimated Rows |
|---------|-------|------------|-----------|----------------|
| Load all active episodes | st_epi | SELECT WHERE status='ACTIVE' | 1x per cycle | ~339 (current data) |
| Load all active entities | st_kg_dom | SELECT WHERE status='ACTIVE' | 1x per cycle | ~283 (current data) |
| Load all active edges | st_kg_edges | SELECT WHERE status='ACTIVE' | 1x per cycle | ~1,613 (current data) |
| Load all active patterns | st_sem | SELECT WHERE status='ACTIVE' | 1x per cycle | ~545 (current data) |
| Load all active routines | st_procedural | SELECT WHERE type='ROUTINE' | 1x per cycle | ~12 (current data) |
| Observation record stats | st_observations | GROUP BY layer, record_id with aggregates | 1x per cycle (Stage 5) | Grows unboundedly; 12 aggregate columns per group |
| Observation distributions | st_observations | GROUP BY social_context (6x for different columns) | 6x per cycle (Stage 5) | 6 distribution queries |
| Observation entity trail | st_observations | WHERE entity_id IS NOT NULL | 1x per cycle (Stage 5) | Per-entity observation rows |
| MCTS decision write | st_mcts_decisions | INSERT | Per MCTS decision (DELETE) | Batch per cycle |
| MCTS shadow write | st_mcts_shadow_log | INSERT | Per MCTS prediction (DELETE) | Batch per cycle |

### 5.4 Storage Gaps

| Gap | Severity | Detail |
|-----|----------|--------|
| st_anchors table missing | HIGH | ASU algorithm requires a new truth table for Bayesian anchors. No migration, no writer, no R6/R7 routing exists. |
| st_observations unbounded growth | MEDIUM | Append-only table with no retention policy. ObservationEvidenceLoader aggregation queries will slow as table grows. Need index strategy or time-windowed queries. 12 partial indexes exist but no query plan analysis done. |
| No P03StagedWrites bucket for st_anchors | HIGH | R6/R7 pipeline writes use P03StagedWrites which has no anchor bucket. Anchor writes need a new routing path. |
| st_mcts_decisions/shadow_log orphaned | LOW | Tables become dead storage after MCTS deletion. Need cleanup migration. |
| Missing columns on 6 tables | HIGH | EST (st_epi +2 cols), SRE (st_social +3 cols), MTP (5 tables +1 col each), SPG (st_kg_dom +1, st_kg_edges +1). Total: ~12 new columns across 6 tables. |
| No write-back path for Stage 5 UPDATE outputs | HIGH | Current R5 only produces INSERT outputs (insights, counterfactuals, etc.). Stage 5 algorithms produce UPDATE outputs (confidence changes, salience updates, weight adjustments). R6/R7 pipeline must support UPDATE operations, not just INSERT. |

---

## Section 6: Event Bus & Topics

### 6.1 Topics Consumed by R5

| Topic | Schema Version | Source | Content |
|-------|----------------|--------|---------|
| `p03.episodes.clustered.v1` | v1 | R2 Episode Clustering | Episode cluster results with member events, temporal bounds, entity participation |
| `p03.kg.extracted.v1` | v1 | R4 Edge Enrichment | Knowledge graph entities and edges post-enrichment |
| `p03.routines.detected.v1` | v1 | Prior cycles | Detected routine patterns from st_procedural |

### 6.2 Topics Emitted by R5

| Topic | Schema Version | Consumers | Content |
|-------|----------------|-----------|---------|
| `p03.insights.generated.v1` | v1 | R6 Merge Arbitration | BGT-SM insights (concept pairs, PMI, novelty) |
| `p03.counterfactuals.generated.v1` | v1 | R6 Merge Arbitration | CPN counterfactual scenarios (DELETE with CPN) |
| `p03.prospective.generated.v1` | v1 | R6 Merge Arbitration | SPC-UQ/MCTS prospective memories |

### 6.3 Topic Gaps

| Gap | Severity | Detail |
|-----|----------|--------|
| Intent signals have no topic | HIGH | IntentSignalDetector produces `List[IntentSignal]` but these are not emitted to any event bus topic. They exist in R5PhaseOutputs but are not consumed by R6/R7. Dead output. |
| Routine candidates have no topic | MEDIUM | RoutineDetector output goes to R5PhaseOutputs.r5_routine_candidates but has no dedicated event topic. Relies on direct pass-through to R6. |
| MCTS scenarios share prospective topic | LOW | MCTSScenario outputs use the same `p03.prospective.generated.v1` topic as legitimate prospective memories. DELETE with MCTS. |
| No topics for Stage 5 UPDATE outputs | HIGH | Stage 5 algorithms produce UPDATE operations (confidence changes, weight updates, tier promotions). No event bus topics defined for these. Need new topics or extension of existing topics to support UPDATE semantics. |
| Missing `p03.observations.loaded.v1` | MEDIUM | ObservationEvidenceLoader queries are a major data loading step but produce no event for observability. Consider emitting a summary event for monitoring. |
| Stale topic references in contract | HIGH | Pipeline contract references `stage_50_counterfactual` and `stage_51_forward_sim` which are CPN/MCTS stages to be deleted. Contract must be updated. |

---

## Section 7: Observability Audit

### 7.1 Metrics Currently Emitted

| Metric | Type | Labels | Emitted By | Purpose |
|--------|------|--------|------------|---------|
| `r5_phase_duration_ms` | Histogram | cycle_id | r5_dream_explorer.py | Total R5 phase execution time |
| `r5_phase_skipped` | Counter | skip_reason | r5_dream_explorer.py | Count of R5 skip events by reason |
| `r5_insights_count` | Gauge | cycle_id | r5_dream_explorer.py | Number of insights produced |
| `r5_counterfactuals_count` | Gauge | cycle_id | r5_dream_explorer.py | Number of counterfactuals produced (DELETE) |
| `r5_prospective_count` | Gauge | cycle_id | r5_dream_explorer.py | Number of prospective memories produced |
| `r5_routines_count` | Gauge | cycle_id | r5_dream_explorer.py | Number of routine optimizations produced |
| `r5_intent_signals_count` | Gauge | cycle_id | r5_dream_explorer.py | Number of intent signals detected |
| `r5_algorithm_duration_ms` | Histogram | algorithm_name | dream_explorer.py | Per-algorithm execution time |
| `r5_algorithm_error` | Counter | algorithm_name, error_type | dream_explorer.py | Per-algorithm error count |
| `r5_budget_utilization` | Gauge | cycle_id | compute_budget.py | MCTS rollout budget utilization (DELETE) |

### 7.2 Traces

| Span | Parent | Attributes | File |
|------|--------|------------|------|
| `r5_dream_exploration` | `p03_consolidation` | cycle_id, r5_mode, cluster_count | r5_dream_explorer.py |
| `r5_data_loading` | `r5_dream_exploration` | loader_count, total_rows_loaded | r5_dream_explorer.py |
| `r5_algorithm_execution` | `r5_dream_exploration` | algorithm_name, duration_ms, success | dream_explorer.py |
| `r5_quality_filter` | `r5_dream_exploration` | pre_filter_count, post_filter_count | dream_explorer.py |

### 7.3 Log Points

| Log Level | Location | Message Pattern | Purpose |
|-----------|----------|-----------------|---------|
| INFO | r5_dream_explorer.py | "R5 phase starting: mode={mode}, clusters={n}" | Phase entry |
| INFO | r5_dream_explorer.py | "R5 phase skipped: {reason}" | Skip decision |
| INFO | r5_dream_explorer.py | "R5 phase complete: insights={n}, counterfactuals={n}, ..." | Phase summary |
| WARNING | dream_explorer.py | "Algorithm {name} failed: {error}" | Algorithm failure |
| WARNING | dream_explorer.py | "Algorithm {name} timed out after {ms}ms" | Algorithm timeout |
| DEBUG | dream_explorer.py | "Phase 1 parallel results: {algorithm: result}" | Parallel execution detail |
| DEBUG | dream_explorer.py | "Quality filter: {pre} -> {post} outputs" | Filter detail |
| ERROR | r5_dream_explorer.py | "R5 data loader failed: {loader}: {error}" | Data loading failure |
| DEBUG | bgt_sm.py | "BGT walk {i}: {path}, PMI={pmi}" | Random walk detail |
| DEBUG | cpn.py | "CPN perturbation: {type} on {episode}" | Perturbation detail (DELETE) |
| WARNING | dream_explorer.py | `print()` debug artifacts | BUG: print() statements instead of logger calls |

### 7.4 Observability Gaps

| Gap | Severity | Detail |
|-----|----------|--------|
| print() debug artifacts | MEDIUM | `dream_explorer.py` contains `print()` calls instead of structured logging. Must be replaced with logger. |
| No per-algorithm output quality metrics | HIGH | Metrics track COUNT of outputs but not QUALITY (e.g., average insight novelty, average counterfactual utility_delta). Cannot assess algorithm effectiveness. |
| No observation evidence loading metrics | HIGH | Stage 5 ObservationEvidenceLoader executes 3+ SQL queries per cycle. No metrics for query duration, row counts, or cache hit rates. |
| No budget enforcement metrics for non-MCTS | MEDIUM | ComputeBudget tracks MCTS rollouts but Stage 5 algorithms use time budgets. No metrics for per-algorithm time budget utilization. |
| Missing USE_M5_EMITTERS observability | HIGH | Feature flag `USE_M5_EMITTERS` controls whether R5 outputs flow to R6/R7. No metric or log indicating current flag state. Outputs could be silently discarded with no visibility. |
| No cold-start detection metric | MEDIUM | When st_observations is empty, all Stage 5 algorithms degrade gracefully but there is no metric indicating cold-start state for monitoring dashboards. |
| Missing Stage 5 algorithm metrics | HIGH | 10 new algorithms have no metrics defined. Each needs: execution duration, output count, input row count, observation evidence utilization rate. |
| No self-reinforcement loop monitoring | MEDIUM | Stage 5 creates a feedback loop (R5 updates -> R7 observations -> next R5). No metric tracking loop amplification rate or convergence. Risk of runaway without visibility. |

---

## Section 8: Test Coverage Audit

### 8.1 Existing Test Inventory

#### Unit/Integration Tests (`tests/k0/modules/consolidation/dream/`)

| File | Lines | Tests | Coverage Target |
|------|------:|------:|-----------------|
| `test_dream_explorer.py` | 1,312 | 49 | DreamExplorer orchestrator: config validation, seeding/determinism, explore() output structure, insight/scenario/prospective/routine model creation, ranking by serendipity, novelty filtering, max limits, seed selection, routine detector field mapping |
| `test_compute_budget.py` | 629 | 44 | ComputeBudget: allocation/exhaustion/utilization, elapsed time, AlgorithmResult success/failure/rollout tracking, OrchestrationResult aggregation, parallel algorithm isolation, error isolation, deterministic execution |
| `test_mcts_persistence.py` | 544 | 23 | MCTSDecisionRecord creation/serialization, to_db_dict conversion, decision type & termination reason enums, MCTSDecisionConverter, MCTSPersistenceManager persist/flush/batch, ComputeBudgetTracker budget tracking/exhaustion/stats, full cycle workflow. DELETE with MCTS. |
| `test_intent_signals.py` | 327 | 17 | IntentSignalType enum completeness, IntentSignal base creation & confidence validation, all 6 signal subclass creation & validation |
| `test_intent_signal_integration.py` | 334 | 12 | Integration with P03PhaseOutputs and R5PhaseOutputs: field existence, total_outputs counting, explore() detecting all intent types, signal type correctness |
| `test_cpn_integration.py` | 433 | 11 | CPN integration with DreamExplorer: counterfactual generation, model validity, determinism, empty input handling, scaling. DELETE with CPN. |

**Dream test subtotal: 3,579 lines, 156 tests**

#### Benchmark Tests (`tests/k0/modules/consolidation/benchmarks/`)

| File | Lines | Tests | Coverage Target |
|------|------:|------:|-----------------|
| `benchmark_bgt_sm.py` | 757 | 19 | BGT-SM: PMI calculation, graph construction, neighbor lookup, co-occurrence, random walk reach/determinism, insight quality, serendipity scoring, S/M/L scale performance, edge cases, family memory scenario |
| `benchmark_cpn.py` | 573 | 17 | CPN: counterfactual generation, emotional threshold, scenario types, base episode validation, S/M/L performance, plausibility distribution, utility delta, determinism. DELETE with CPN. |
| `benchmark_dream_explorer.py` | 794 | 13 | Full DreamExplorer: all output types, output structure, empty inputs, S/M/L scale, insight quality, counterfactual diversity, output ranking, determinism, realistic scenarios (busy professional week, family vacation) |
| `benchmark_mcts.py` | 704 | 17 | MCTS: UCT exploration term, backpropagation, budget allocation, budget exhaustion, performance benchmarks, action ranking, exploration-exploitation balance, goal alignment, determinism, daily planning. DELETE with MCTS. |
| `benchmark_spc_uq.py` | 672 | 17 | SPC-UQ: gap detection types, gap priority ordering, reconstruction quality, performance benchmarks, coherence, non-canonical flag, determinism, daily memory reconstruction |

**Benchmark test subtotal: 3,500 lines, 83 tests**

#### Benchmark Support Files (no test functions)

| File | Lines | Purpose |
|------|------:|---------|
| `r5_baseline.py` | 575 | Baseline reference data for R5 algorithm comparison |
| `r5_coverage.py` | 725 | Coverage tracking/analysis for R5 algorithms |
| `r5_data_factory.py` | 199 | Factory functions for R5 test data generation |
| `r5_embeddings.py` | 271 | Embedding generation/management for R5 benchmarks |
| `r5_report.py` | 870 | Report generation for R5 benchmark results |
| `r5_statistics.py` | 554 | Statistical analysis utilities for R5 benchmarks |

**Support file subtotal: 3,194 lines**

#### Benchmark Packs (stress/adversarial scenarios, no test functions)

| Pack | Files | Lines | Scenario |
|------|------:|------:|----------|
| CPN packs | 1 | 351 | Sparse graph stress |
| MCTS packs | 2 | 819 | Constrained budget, delayed reward |
| BGT packs | 2 | 832 | Adversarial graph, clustered graph |
| SPC packs | 3 | 1,906 | Conflict, high-conflict, multi-provenance |
| Mixed packs | 7 | ~3,664 | Causal deep, causal fork-join, mixed stress, performance stress, real world, toy |

**Pack subtotal: 15 files, ~7,858 lines**

#### Staging Tests

| File | Lines | Tests | Coverage Target |
|------|------:|------:|-----------------|
| `test_truth_write_assembler_r5.py` | 483 | 26 | R5 output assembly into truth writes: insights -> st_sem INSERT, counterfactuals -> st_prospective INSERT, routine optimizations -> st_procedural INSERT; field validation, idempotency keys, source evidence mapping, merge with R3 sem writes |

### 8.2 Test Coverage Summary

| Category | Files | Lines | Test Functions |
|----------|------:|------:|---------------:|
| Dream unit/integration tests | 6 | 3,579 | 156 |
| Benchmark tests | 5 | 3,500 | 83 |
| Staging tests | 1 | 483 | 26 |
| Support files (data/coverage/report) | 6 | 3,194 | 0 |
| Benchmark packs (stress scenarios) | 15 | ~7,858 | 0 |
| **Grand Total** | **33** | **~18,614** | **265** |

### 8.3 Coverage Gaps

| Gap | Severity | Detail |
|-----|----------|--------|
| No TDL-HCO dedicated tests | HIGH | TDL-HCO algorithm (1,025 lines) has no dedicated test file. Covered only indirectly through DreamExplorer integration tests. ValueFunction TD updates, bottleneck detection, suggestion generation untested in isolation. |
| No RoutineDetector dedicated tests | HIGH | RoutineDetector (710 lines) has no dedicated test file. Signature grouping, frequency scoring, lifecycle detection untested in isolation. |
| No IntentSignalDetector dedicated tests | MEDIUM | IntentSignalDetector (631 lines) has no dedicated test file. Regex pattern matching, TemporalParser integration, false positive rates untested. Only covered through integration test. |
| No observation_context tests | HIGH | ObservationContext (310 lines) with ~35 fields, from_event/from_episode_cluster factories untested. These are critical for Stage 5 observation evidence pipeline. |
| All Stage 5 algorithms untested | CRITICAL | 10 new algorithms (EST, ASU, SPR, SRE, EWR, SPC-UQ v2, CLV, CTD, MTP, EPC, SPG, NTD) have zero test coverage. Need unit tests, integration tests, and benchmark tests for each. |
| No ObservationEvidenceLoader tests | CRITICAL | Shared infrastructure for all Stage 5 algorithms. 3 SQL queries, aggregation logic, empty-evidence handling all untested. |
| CPN/MCTS tests become dead code | MEDIUM | test_cpn_integration.py (433 lines, 11 tests), benchmark_cpn.py (573 lines, 17 tests), benchmark_mcts.py (704 lines, 17 tests), test_mcts_persistence.py (544 lines, 23 tests) will be dead code after M5C deletion. Total: 2,254 lines, 68 tests to delete. |
| No Phase 5 execution runner tests | HIGH | Stage 5 proposes a new 5-phase execution runner replacing the current 4-phase parallel/sequential orchestration. No tests for phase ordering, dependency resolution, or error propagation across phases. |
| No end-to-end R5 cycle test | HIGH | No test validates the full R5 cycle: load data -> run algorithms -> produce outputs -> verify outputs match expected truth table changes. Current tests validate individual components but not the integrated pipeline. |
| No regression test for R5 skip conditions | MEDIUM | The 4 skip conditions (disabled, backlog, timeout, clusters) are tested implicitly but not as a systematic test suite covering all combinations. |

### 8.4 Test Infrastructure Needs

| Need | Priority | Detail |
|------|----------|--------|
| ObservationEvidence test factory | HIGH | Factory to generate realistic ObservationEvidence objects with controlled record_stats, distributions, and entity_observations for Stage 5 algorithm testing. |
| st_observations test fixtures | HIGH | SQL fixtures or in-memory substitutes for st_observations data. Current test infrastructure has no observation data. |
| Stage 5 algorithm test harness | HIGH | Standardized test harness for observation-driven algorithms: inject evidence, run algorithm, validate outputs. Should support empty evidence, single record, and realistic-scale scenarios. |
| R5 phase execution test harness | MEDIUM | Harness for testing multi-phase execution with dependency tracking between phases (Phase 1 outputs feed Phase 2, etc.). |
| Convergence test framework | MEDIUM | Framework to test self-reinforcing loop convergence: run multiple R5 cycles, verify values converge rather than diverge. Needed for EST, ASU, SPR, SRE, MTP feedback loop validation. |

---

## Section 9: Dependency Map

### 9.1 Upstream Dependencies (R5 reads from)

| Component | Type | Interface | Impact if Changed |
|-----------|------|-----------|-------------------|
| R2 Episode Clustering | Pipeline phase | `List[EpisodeCluster]` via syscall | R5 input changes; all episode-based algorithms affected |
| R4 Edge Enrichment | Pipeline phase | `List[EntityRow]`, `List[EdgeRow]` via syscall | BGT-SM walk quality, CPN DAG structure, CLV coherence checks |
| R3 Decay & Dedup | Pipeline phase | Implicit (R3 modifies st_epi, st_sem before R5 reads) | R5 sees post-decay data; salience and confidence values are post-R3 |
| st_observations | Storage (R7 writes) | 3 SQL aggregation queries via ObservationEvidenceLoader | Stage 5 primary evidence source. Schema changes break all new algorithms. |
| R5Config | Configuration | `from_dict()` factory | Parameter changes affect skip conditions, algorithm enables, output caps |
| DreamConfig | Configuration | `from_r5_config()` bridge | Per-algorithm parameter changes |
| Fabric capabilities | Runtime | 5 capabilities from module contract | Algorithm execution gated by capability grants |
| Syscalls | Runtime | query_kg_entities, query_kg_edges, query_episodes, query_routines, query_semantic_patterns | Data loader interface; syscall signature changes break R5 |

### 9.2 Downstream Dependencies (R5 writes to)

| Component | Type | Interface | Impact if R5 Changes |
|-----------|------|-----------|----------------------|
| R6 Merge Arbitration | Pipeline phase | `R5PhaseOutputs` dataclass | New output types need R6 arbitration rules |
| R7 Truth Writing | Pipeline phase | Via R6 arbitrated outputs | New write operations (UPDATE vs INSERT) need R7 writer support |
| R8 Event Emission | Pipeline phase | Via R7 write confirmations | New truth table changes trigger event emission |
| P03PhaseOutputs | Dataclass | R5 fields on P03PhaseOutputs (lines 782-790) | Adding Stage 5 output types requires P03PhaseOutputs extension |
| st_sem | Storage | INSERT insights, UPDATE confidence (Stage 5) | New insight types or confidence update patterns |
| st_prospective | Storage | INSERT prospective, UPDATE status (Stage 5) | Counterfactual purge changes prospective table composition |
| st_procedural | Storage | INSERT routines, UPDATE optimizations | Routine detection output format |
| st_epi | Storage | UPDATE salience (EST), INSERT composites (EPC) | Salience changes affect all downstream consumers of st_epi |
| st_social | Storage | UPDATE sentiment/trajectory/diversity (SRE) | Social graph quality changes affect K1 recall |
| st_kg_dom | Storage | UPDATE propagated_salience (SPG) | Entity salience changes affect graph traversal |
| st_kg_edges | Storage | UPDATE weight (EWR), UPDATE propagated_salience (SPG) | Edge weight changes affect BGT-SM walk quality in next cycle |
| st_anchors | Storage | UPSERT anchors (ASU) | New table, no existing consumers yet |
| R3 Decay | Cross-phase | memory_tier field read by R3 | MTP tier changes modify R3 decay behavior (effective_lambda = base_lambda * decay_multiplier) |

### 9.3 External Dependencies

| Dependency | Type | Version | Purpose | Risk |
|------------|------|---------|---------|------|
| Python stdlib `math` | Standard library | 3.11+ | log2, sqrt in EST, SPR, EPC, SPG calculations | None |
| Python stdlib `random` | Standard library | 3.11+ | Seeded random for BGT-SM walks, CPN perturbation selection | None |
| Python stdlib `collections` | Standard library | 3.11+ | defaultdict for aggregation in CLV, CTD, SPG | None |
| `concurrent.futures` | Standard library | 3.11+ | ThreadPoolExecutor for Phase 1 parallel execution | Thread pool size not configured |
| pgvector (PostgreSQL) | Database extension | 0.5+ | HNSW indexing for st_vec embeddings used by EPC similarity | ADR-K003 mandates pgvector over FAISS |
| ULID generation | Internal utility | - | generate_ulid() for composite episode IDs, narrative thread IDs | Collision risk at high throughput |

### 9.4 Cross-Phase Dependency Analysis

```
R5 <-> R3 Bidirectional Dependency (Stage 5):
  R3 sets decay -> R5 reads post-decay values
  R5 sets memory_tier (MTP) -> R3 reads tier for decay_multiplier
  Risk: circular dependency if R3 and R5 run in same cycle iteration
  Mitigation: R5 reads R3's output from current cycle, MTP tier applies to NEXT cycle's R3

R5 -> R7 -> st_observations -> R5 Feedback Loop:
  R5 produces updates -> R7 writes truth tables + records observations
  Next cycle: R5 reads observations from previous writes
  Risk: self-reinforcing amplification without convergence bounds
  Mitigation: logarithmic scaling (log2) in EST, max bounds on confidence/salience
```

---

## Section 10: Performance Baseline

### 10.1 Current Performance Characteristics

| Metric | Value | Condition | Source |
|--------|-------|-----------|--------|
| R5 total phase time | 500-3000ms | Typical cycle, all algorithms enabled | r5_algorithm_duration_ms histogram |
| BGT-SM execution | 200-500ms | 100 walks, length 5, ~283 entities, ~1613 edges | benchmark_bgt_sm.py |
| CPN execution | 300-800ms | ~339 episodes, ~1613 edges | benchmark_cpn.py (DELETE) |
| TPN-MCTS execution | 500-2000ms | 200-500 rollouts depending on mode | benchmark_mcts.py (DELETE) |
| SPC-UQ execution | 200-600ms | ~339 episodes, ~283 entities | benchmark_spc_uq.py |
| TDL-HCO execution | <100ms | ~12 routines, ~339 episodes | Lightweight; no benchmark |
| IntentSignalDetector execution | <50ms | Regex over filtered episodes | Lightweight; no benchmark |
| RoutineDetector execution | <100ms | Signature sort + grouping | Lightweight; no benchmark |
| Data loading (7 syscalls) | 100-500ms | 5 implemented loaders | Depends on table sizes |

### 10.2 Bottleneck Analysis

| Bottleneck | Impact | Location | Mitigation |
|------------|--------|----------|------------|
| BGT-SM on sparse graph | Random walks degrade to noise when 82% of edges are near-zero weight | `bgt_sm.py` RandomWalkEngine | EWR (Stage 5) cleans edge weights before BGT-SM runs |
| CPN O(N*P*E) complexity | Cubic growth with episode count. 339 episodes is manageable but 1000+ would be problematic | `cpn.py` generate() | DELETE CPN entirely (M5C) |
| MCTS rollout budget | 500-1000 rollouts at ~2ms each = 1-2 seconds. Dominates R5 execution time. | `mcts.py` simulate() | DELETE MCTS entirely (M5C) |
| SPC-UQ O(E^2) gap detection | Pairwise comparison of all episodes. 339 episodes = ~57K pairs. Scales quadratically. | `spc_uq.py` _identify_gaps() | Refocus to prospective cleanup (O(P) where P=prospective count) |
| DreamExplorer sync-with-async wrapper | `explore()` is synchronous but wrapped with async in phase runner. Creates unnecessary thread overhead. | `dream_explorer.py` / `r5_dream_explorer.py` | Refactor to native async or remove wrapper |
| ThreadPoolExecutor unbounded | Phase 1 parallel execution uses ThreadPoolExecutor with no explicit max_workers. Under high load could create excessive threads. | `dream_explorer.py` _run_phase1_parallel() | Set explicit max_workers based on algorithm count |
| EmbeddingCache unbounded growth | BGT-SM's EmbeddingCache dict grows without eviction. Long-running processes accumulate memory. | `bgt_sm.py` EmbeddingCache | Add LRU eviction or cycle-scoped cache |

### 10.3 Stage 5 Performance Estimates

| Algorithm | Estimated Latency | Scaling Factor | Notes |
|-----------|------------------:|----------------|-------|
| ObservationEvidenceLoader | ~150ms | O(R) where R=observation rows | 3 SQL aggregation queries. Grows with st_observations table. |
| EST | ~50ms | O(E) where E=episodes | Simple per-record stats lookup + arithmetic |
| ASU | ~30ms | O(A*D) where A=anchors, D=distributions | 9 anchor specs, 6 distribution lookups |
| SPR | ~50ms | O(P) where P=patterns | Per-pattern stats lookup + specificity analysis |
| SRE | ~80ms | O(S*O) where S=social entries, O=observations | Per-entity observation aggregation |
| EWR | ~100ms | O(E*ep) where E=edges, ep=episodes | Edge-episode co-occurrence analysis |
| SPC-UQ v2 | ~80ms | O(P) where P=prospective items | Linear scan + dedup |
| CLV | ~60ms | O(N+E+S) set operations | Set intersection on loaded data |
| CTD | ~80ms | O(N*A + S*O + ep^2) | Attribute scan + sentiment comparison + temporal overlap |
| EPC | ~200ms | O(ep^2) for similarity clustering | Pairwise similarity; mitigated by entity-group pre-filter |
| SPG | ~50ms | O(ep + E) single-hop propagation | Linear scan over episodes + edges |
| NTD | ~150ms | O(ep^2) for chain detection | Pairwise entity overlap; mitigated by temporal ordering |
| TDL-HCO | ~80ms | O(R*S) unchanged | Same as current |
| MTP | ~30ms | O(R) where R=observed records | Per-record tier calculation |
| BGT-SM | ~300ms | Same as current | Improved quality from EWR-cleaned edges |
| **Estimated Total** | **~1,200ms** | | **Within 2,000ms contract budget** |

### 10.4 Performance Targets

| Target | Value | Rationale |
|--------|-------|-----------|
| R5 total phase time (p99) | <2,000ms | Module contract latency budget |
| ObservationEvidenceLoader (p99) | <300ms | Must not dominate total budget; 3 SQL queries |
| Any single algorithm (p99) | <500ms | No algorithm should exceed 25% of total budget |
| Phase 1 parallel (wall clock) | <300ms | 4 algorithms, longest determines wall clock |
| Memory footprint | <100MB | ObservationEvidence + all accumulated data in memory |
| st_observations query rows | <100K | Performance degrades beyond this; need time-windowed queries or indexes |

---

## Section 11: Gap Analysis & Enhancement Register

### 11.1 Functional Gaps

| Gap ID | Severity | Category | Description | Resolution |
|--------|----------|----------|-------------|------------|
| FG-001 | CRITICAL | Algorithm | CPN produces 70 nonsense counterfactuals per run. All modifiability=MODIFIABLE (simplified heuristic). No grounding model for perturbation plausibility. | DELETE CPN (M5C). Replace with CTD for real contradiction detection. |
| FG-002 | CRITICAL | Algorithm | TPN-MCTS has no meaningful game tree. State space undefined for personal memory. UCT exploration constant not calibrated. Forward simulation has no grounding model. | DELETE MCTS (M5C). No replacement needed; forward simulation belongs at K1 query time. |
| FG-003 | HIGH | Algorithm | SPC-UQ focused on generation (gap identification, Bayesian reconstruction) but prospective memory quality is unvalidated. Reconstructions marked is_canonical=False but never verified. | REFOCUS to prospective cleanup: counterfactual purge, observation-based completion/staleness, deduplication (M5D). |
| FG-004 | HIGH | Data Loading | 3 of 8 required data loaders not implemented: social, prospective, anchors. Stage 5 algorithms cannot access st_social, st_prospective, or st_anchors data. | Implement missing loaders as new syscalls (M5D Epic 5D.3). |
| FG-005 | HIGH | Infrastructure | No ObservationEvidenceLoader exists. All Stage 5 algorithms depend on this shared component for st_observations queries. | Implement ObservationEvidenceLoader with 3 SQL queries (M5D Epic 5D.2). |
| FG-006 | HIGH | Infrastructure | No 5-phase execution runner. Current orchestrator runs 4 phases with different parallel/sequential patterns than Stage 5 requires. | Implement new phase runner supporting 5 phases with dependency tracking (M5D Epic 5D.4). |
| FG-007 | HIGH | Output Pipeline | R5 only produces INSERT outputs. Stage 5 algorithms produce UPDATE outputs (confidence changes, salience updates, weight adjustments). R6/R7 must support UPDATE operations. | Extend R6/R7 for UPDATE semantics. |
| FG-008 | MEDIUM | Feature Flag | `USE_M5_EMITTERS` defaults to False, silently discarding R5 outputs. No observability for this flag state. | Default to True or add mandatory logging when False. |
| FG-009 | MEDIUM | Output | IntentSignalDetector output not wired to R6/R7. Intent signals exist in R5PhaseOutputs but are dead output. | Wire to event bus topic or direct routing to downstream consumers. |
| FG-010 | LOW | Code Quality | `dream_explorer.py` contains print() debug artifacts instead of structured logging. | Replace with logger calls (M5C cleanup). |

### 11.2 Contract Gaps

| Gap ID | Severity | Category | Description | Resolution |
|--------|----------|----------|-------------|------------|
| CG-001 | HIGH | Pipeline Contract | Pipeline contract defines 3 stages (stage_50/51/52) that don't map 1:1 to actual code execution. R5 runs as a single phase with internal orchestration. | Rewrite pipeline contract to reflect actual R5 execution model. |
| CG-002 | HIGH | Module Contract | Module contract missing output topics for intent signals and routine candidates. Only 3 of 7 output types have topics. | Add missing output topics to module contract. |
| CG-003 | HIGH | Latency | Contract specifies 2000ms but r5_config allows 120,000ms. 60x discrepancy. | Align contract with realistic R5 timing or enforce contract limit. |
| CG-004 | HIGH | Stage 5 Contracts | No contracts exist for: ObservationEvidenceLoader, any of the 10 new algorithms, st_anchors table, observation evidence queries. | Create contracts as part of M5D implementation. |
| CG-005 | MEDIUM | Schema | Phase output dataclasses in models.py and phase_outputs.py have overlapping but slightly different field sets. | Consolidate to single authoritative set of dataclasses (M5D Epic 5D.5). |

### 11.3 Architecture Gaps

| Gap ID | Severity | Category | Description | Resolution |
|--------|----------|----------|-------------|------------|
| AG-001 | CRITICAL | Governance | No ADRs created for Stage 5 design decisions. Entire proposal (4882 lines + 1640 lines corrections) has no formal architectural decision backing. | Create ADR-P03-STAGE5 series before implementation. |
| AG-002 | HIGH | Feedback Loop | Self-reinforcing observation loop (R5 -> R7 observations -> R5) has no proven convergence bounds. Risk of runaway amplification. | Formal convergence analysis + damping mechanisms (logarithmic scaling helps but not proven sufficient). |
| AG-003 | HIGH | Cross-Phase | MTP creates bidirectional dependency between R5 and R3. R3 must read memory_tier set by R5. No specification for when R3 reads this value (current cycle vs next cycle). | Specify R5 tier changes apply to next cycle's R3 decay. |
| AG-004 | HIGH | Proposal Contradictions | Stage 5 proposal has critical internal contradictions: ASU/SPR name confusion (Section 4 vs 13), dataclass conflicts, phase order contradictions. | Section 4 definitions are authoritative per corrections doc. |
| AG-005 | MEDIUM | Architecture Master | k0_architecture_master.md does not reflect Stage 5 changes: no entries for new algorithms, new tables, new events, new syscalls. | Update as part of GATE 5 (implementation workflow). |
| AG-006 | MEDIUM | MW v2 Dependency | Stage 5 algorithms benefit dramatically from MW v2 enriched signals (correct social_context, per-extraction affect, entity_salience). Without MW v2, observation distributions remain broken. Implementation sequencing matters. | Document MW v2 as prerequisite or accept degraded Stage 5 performance until MW v2 ships. |
| AG-007 | LOW | Code Organization | 9 algorithm files in `k0/modules/consolidation/algorithms/` will grow to 19+ files. No sub-package organization. | Consider sub-packages: `algorithms/observation/` (EST, ASU, SPR, SRE), `algorithms/graph/` (EWR, SPG, BGT-SM), `algorithms/verification/` (CLV, CTD), `algorithms/compression/` (EPC, NTD, MTP). |

---

## Section 12: Security & Privacy Audit

### 12.1 Data Classification

| Data Element | Classification | Handling |
|--------------|---------------|----------|
| Episode text | PII (user content) | Processed in-memory only. R5 reads but does not persist raw text beyond what already exists in st_epi. |
| Entity names | PII (person names) | Read from st_kg_dom. R5 uses entity_id references, not raw names, in most outputs. CLV coherence reports include entity labels for human readability -- ensure these don't leak to logs. |
| Location data | PII (spatial) | Read from st_epi.location_name. Used by CTD for temporal impossibility checks. Not persisted in R5 outputs. |
| Social relationships | Sensitive | st_social entries read by SRE. Sentiment scores, emotional diversity, health scores are derived aggregate values (not raw conversation content). |
| Observation evidence | Aggregate | st_observations provides aggregate statistics (counts, averages, distributions). Individual observation rows contain context snapshots that may include PII fields. ObservationEvidenceLoader aggregates before returning to algorithms. |
| Bayesian anchors | Derived | ASU produces anchor priors (e.g., family_oriented=0.85). These are statistical aggregates, not raw data. Low PII risk. |
| Narrative threads | Sensitive | NTD produces narrative descriptions synthesized from episode chains. May contain family health, relationship, or financial details in description text. |
| MCTS decisions | Low sensitivity | MCTSDecisionRecord contains scenario projections. Fictional content, not real user data. DELETE with MCTS. |

### 12.2 Capability Requirements

| Capability | Source | Algorithms Using | Purpose |
|------------|--------|------------------|---------|
| `dream_exploration` | Module contract | DreamExplorer orchestrator | Gate R5 phase execution |
| `insight_generation` | Module contract | BGT-SM | Gate insight discovery |
| `counterfactual_analysis` | Module contract | CPN (DELETE) | Gate counterfactual generation |
| `prospective_memory` | Module contract | SPC-UQ, MCTS (DELETE) | Gate prospective memory creation |
| `routine_optimization` | Module contract | TDL-HCO | Gate routine optimization |
| `observation_evidence_read` | NOT IN CONTRACT | All Stage 5 algorithms | Gate st_observations query access. MISSING CAPABILITY. |
| `truth_table_update` | NOT IN CONTRACT | EST, SPR, SRE, EWR, SPG, MTP | Gate UPDATE operations on truth tables. MISSING CAPABILITY. Current capabilities only cover INSERT. |

### 12.3 Input Validation

| Input | Validation | Gap |
|-------|------------|-----|
| Episode clusters | Type check via DreamExplorerInput frozen dataclass | No content validation (text length, entity count bounds) |
| KG entities | Type check via syscall return | No entity_type validation |
| KG edges | Type check via syscall return | No weight range validation (should be 0.0-1.0) |
| R5Config parameters | `from_dict()` with type coercion | No range validation (e.g., max_r5_seconds could be negative) |
| Observation evidence | NOT VALIDATED | Stage 5 gap: ObservationEvidence from SQL queries has no schema validation. Corrupt st_observations data could produce NaN/Inf in algorithm calculations. |
| Algorithm outputs | Quality filter (novelty_threshold, quality_threshold) | No output content validation. Insights could contain empty strings, counterfactuals could have probability_shift > 1.0 |

### 12.4 Security Gaps

| Gap | Severity | Detail |
|-----|----------|--------|
| No capability for observation evidence access | HIGH | Stage 5 algorithms query st_observations directly. No fabric capability gates this access. Any module could potentially query the observation log. |
| No capability for UPDATE operations | HIGH | Stage 5 UPDATE outputs (confidence changes, weight updates) bypass the INSERT-only capability model. Need new capability type. |
| CLV coherence reports contain entity labels | LOW | CoherenceRepair.detail includes entity names and pattern descriptions. If these flow to external logs or monitoring, PII leaks. |
| NTD narrative descriptions may contain PII | MEDIUM | Synthesized descriptions ("How we fixed Panda's sleep") reference family members by name. If narrative threads are exposed to K1 recall, ensure privacy band filtering applies. |
| No rate limiting on observation queries | LOW | ObservationEvidenceLoader has no throttling. A misconfigured R5 running too frequently could overload the database with aggregate queries. |

---

## Section 13: Enhancement Proposals

### 13.1 Proposed Epics

| Epic | Title | Priority | Depends On | Estimated Effort |
|------|-------|----------|------------|------------------|
| M5C | R5 Cleanup (Delete CPN, MCTS, Shadow) | P0 | None | 2-3 days |
| M5D | R5 Infrastructure (Evidence Loader, Data Loaders, Phase Runner, Dataclasses) | P0 | M5C | 3-5 days |
| M5E-Phase1 | Phase 1 Algorithms (EST, ASU, SPR, SRE) | P1 | M5D | 5-7 days |
| M5E-Phase2 | Phase 2 Algorithms (EWR, SPC-UQ v2) | P1 | M5E-Phase1 | 3-4 days |
| M5E-Phase3 | Phase 3 Algorithms (CLV, CTD) | P1 | M5E-Phase1 | 3-4 days |
| M5E-Phase4 | Phase 4 Algorithms (EPC, SPG, NTD) | P2 | M5E-Phase2 | 4-5 days |
| M5E-Phase5 | Phase 5 Algorithms (MTP, TDL-HCO update, BGT-SM update) | P2 | M5E-Phase4 | 3-4 days |
| M5F | R6/R7 UPDATE Support | P0 | M5D | 2-3 days |
| M5G | Contract Updates (Pipeline, Module, Event Topics) | P1 | M5C | 1-2 days |
| M5H | Observability & Metrics for Stage 5 | P1 | M5E-Phase1 | 2-3 days |

### 13.2 Epic Detail: M5C -- R5 Cleanup

**Objective:** Remove CPN, TPN-MCTS, MCTS Shadow, and associated dead code.

**Scope:**

- Delete `cpn.py` (1,106 lines)
- Delete `mcts.py` (1,113 lines)
- Delete `mcts_shadow.py` (918 lines)
- Delete `mcts_persistence.py` (438 lines)
- Delete `test_cpn_integration.py` (433 lines, 11 tests)
- Delete `benchmark_cpn.py` (573 lines, 17 tests)
- Delete `benchmark_mcts.py` (704 lines, 17 tests)
- Delete `test_mcts_persistence.py` (544 lines, 23 tests)
- Remove CPN/MCTS benchmark packs (~1,564 lines)
- Remove CPN/MCTS fields from DreamExplorerOutput, R5PhaseOutputs, P03PhaseOutputs
- Remove CPN/MCTS config parameters from R5Config and DreamConfig
- Remove MCTS-specific ComputeBudget rollout tracking
- Remove `enable_cpn`, `enable_mcts` feature flags
- Remove `USE_M5_EMITTERS` flag or default to True
- Clean print() debug artifacts in dream_explorer.py
- Cleanup migration: DROP st_mcts_decisions, st_mcts_shadow_log tables

**Lines deleted:** ~7,393 production + ~3,818 test = ~11,211 total
**Lines added:** ~50 (cleanup migration, config simplification)
**Net:** ~-11,161 lines

**Success Criteria:**

- Zero references to CPN, MCTS, or counterfactual in k0/ production code
- All remaining R5 tests pass
- R5 phase runs with only BGT-SM, SPC-UQ, TDL-HCO, IntentSignalDetector, RoutineDetector

### 13.3 Epic Detail: M5D -- R5 Infrastructure

**Objective:** Build shared infrastructure required by all Stage 5 algorithms.

**Scope:**

- Migration 0073: Create st_anchors table, add columns to st_epi, st_sem, st_social, st_kg_dom, st_kg_edges, st_procedural
- Implement ObservationEvidenceLoader: 3 SQL queries, ObservationEvidence dataclass, RecordObservationStats dataclass, empty evidence handling
- Implement missing data loaders: `_load_accumulated_social()`, `_load_accumulated_prospective()`, `_load_accumulated_anchors()`
- Implement 5-phase execution runner: phase dependency tracking, parallel Phase 1/3/4, sequential Phase 2/5, error isolation
- Define authoritative output dataclasses for all Stage 5 algorithms (resolve Section 4 vs Section 13 conflicts)
- Create P03StagedWrites bucket for st_anchors
- Implement AnchorLayerWriter for R7
- Extend R6/R7 for UPDATE operation support

**Success Criteria:**

- ObservationEvidenceLoader returns valid evidence from st_observations
- All 8 data loaders implemented and tested
- 5-phase runner executes phases in correct order with dependency resolution
- All output dataclasses defined as frozen dataclasses with clear field documentation
- st_anchors table created and writable via R7

### 13.4 Epic Detail: M5E -- Algorithm Implementation (Phased)

**Phase 1 (EST, ASU, SPR, SRE):**
All four algorithms share the same input pattern (ObservationEvidence -> per-record/per-entity analysis -> typed output list). Can be implemented in parallel by different developers.

- EST: ~200 lines implementation + ~400 lines tests
- ASU: ~300 lines implementation + ~500 lines tests (9 anchor specs + Beta-Bernoulli)
- SPR: ~200 lines implementation + ~400 lines tests
- SRE: ~250 lines implementation + ~500 lines tests (sentiment + trajectory + diversity + health)

**Phase 2 (EWR, SPC-UQ v2):**
EWR depends on EST-updated salience. SPC-UQ v2 refocuses existing code.

- EWR: ~250 lines implementation + ~400 lines tests
- SPC-UQ v2: ~200 lines refactor + ~300 lines tests (shift from generation to cleanup)

**Phase 3 (CLV, CTD):**
Verification algorithms. Run after Phase 1 enrichments.

- CLV: ~200 lines implementation + ~400 lines tests (6 check types as set operations)
- CTD: ~250 lines implementation + ~500 lines tests (3 contradiction types)

**Phase 4 (EPC, SPG, NTD):**
Graph-level algorithms. Depend on Phase 1-2 outputs.

- EPC: ~300 lines implementation + ~500 lines tests (clustering, synthesis)
- SPG: ~150 lines implementation + ~300 lines tests (single-hop propagation)
- NTD: ~250 lines implementation + ~500 lines tests (chain detection, arc classification)

**Phase 5 (MTP, TDL-HCO update, BGT-SM update):**
Final algorithms. MTP depends on all previous phases.

- MTP: ~150 lines implementation + ~300 lines tests
- TDL-HCO: ~50 lines update (no major changes)
- BGT-SM: ~50 lines update (benefits from EWR but no code changes needed)

**Total estimated new code:** ~2,550 lines production + ~5,000 lines tests = ~7,550 lines

**Success Criteria (per proposal):**

| # | Criterion | Target |
|---|-----------|--------|
| 1 | Active anchors with meaningful distributions | 10+ anchors |
| 2 | No relationships with 0.00 sentiment where obs > 5 | 0 relationships |
| 3 | Average edge weight improvement | > 0.10 (current: 0.051) |
| 4 | WeightNormalization-only edges demoted | < 50% of edges |
| 5 | Pattern confidence range | 0.30-0.95 (current: flat 0.80) |
| 7 | Episode salience variance | std_dev > 0.15 (current: ~0.05) |
| 11 | CORE tier records exist | > 0 CORE records |
| 12 | 0 orphan edges, 0 person entities without st_social | 0 issues |
| 13 | 0 unresolved SENTIMENT_MISMATCH where obs > 5 | 0 mismatches |
| 14 | Composites carry frequency_per_month metadata | All composites |
| 15 | Entity salience std_dev | > 0.15 |
| 16 | Narrative threads detected | 1+ per 30 days |

---

## Section 14: Risk Register

| Risk ID | Severity | Probability | Description | Mitigation |
|---------|----------|-------------|-------------|------------|
| RISK-001 | HIGH | HIGH | **Self-reinforcing loop divergence.** R5 updates -> R7 REINFORCEMENT observations -> next R5 sees more evidence -> stronger updates. Logarithmic scaling (log2) provides sub-linear damping but formal convergence not proven. Could produce runaway salience amplification. | Add convergence monitoring metrics. Implement hard caps on per-cycle update magnitude. Run multi-cycle simulation tests before production. |
| RISK-002 | HIGH | MEDIUM | **MW v2 dependency.** Stage 5 algorithms are designed for MW v2 enriched signals. Without MW v2, st_observations distributions remain broken (social_context only "friends"/"solo", salience flat 0.41). ASU family_oriented anchor impossible to seed. SRE sentiment inaccurate. | Document MW v2 as prerequisite. Define degraded-mode behavior for each algorithm when distributions are broken. Implement graceful fallback (skip anchor specs that require correct distributions). |
| RISK-003 | HIGH | MEDIUM | **Proposal internal contradictions.** ASU/SPR name confusion (Section 4 vs 13), dataclass conflicts, phase order contradictions. If implementation follows wrong section, algorithms will be incorrect. | Corrections doc establishes Section 4 as authoritative. ADR-P03-STAGE5 must codify this resolution before implementation begins. |
| RISK-004 | MEDIUM | HIGH | **Test coverage debt.** 10 new algorithms + ObservationEvidenceLoader + 5-phase runner = ~15 new components with zero test coverage. Current R5 has 265 tests but 68 will be deleted with CPN/MCTS. | Require tests before merging each algorithm. Use standardized test harness. Minimum: unit tests for each algorithm + integration test for phase runner. |
| RISK-005 | MEDIUM | MEDIUM | **st_observations unbounded growth.** Append-only table with no retention policy. ObservationEvidenceLoader aggregate queries will degrade as table grows beyond 100K rows. | Add time-windowed queries (e.g., last 90 days). Add table partitioning by month. Add index analysis for the 3 aggregate query patterns. |
| RISK-006 | MEDIUM | MEDIUM | **R6/R7 UPDATE path complexity.** Current R6/R7 pipeline handles INSERT operations only. Adding UPDATE semantics (confidence changes, weight updates, tier promotions) is a significant extension touching merge arbitration logic. | Design UPDATE path as a separate write channel from INSERT path. Don't modify existing INSERT logic. |
| RISK-007 | LOW | HIGH | **Algorithm file proliferation.** Adding 10+ new algorithm files to a flat directory already containing 9 files. Discoverability and maintenance suffer with 19+ files. | Organize into sub-packages by algorithm category during M5D. |
| RISK-008 | MEDIUM | LOW | **EPC composite quality.** Episode compression merges episodes into composites. If similarity threshold is too low, semantically distinct episodes could be merged. Loss of unique memories. | Conservative threshold (0.85). Only compress low-salience episodes (< 0.60). Minimum age requirement (7 days). High-salience episodes never compressed. |
| RISK-009 | LOW | MEDIUM | **CTD false positives on temporal impossibility.** Same-entity, different-location, overlapping-time detection depends on accurate temporal bounds and location data. Current data has sparse location coverage. | Require minimum observation count before flagging. Use min_observations_for_mismatch=5 threshold. |
| RISK-010 | HIGH | LOW | **R3 integration regression.** MTP sets memory_tier which modifies R3 decay behavior. If R3 reads stale tier values or applies multiplier incorrectly, core decay mechanism breaks. | Explicit R3 integration test: verify decay(CORE) = 0, decay(TRANSIENT) = full, decay(ACTIVE) = 0.7x, decay(STABLE) = 0.3x. |

---

## Section 15: Open Questions

| Q# | Question | Context | Impact | Proposed Answer |
|----|----------|---------|--------|-----------------|
| Q-001 | Should MW v2 be a hard prerequisite for Stage 5, or should algorithms support degraded mode? | ASU, SRE, EST all benefit dramatically from MW v2 signals. Without MW v2, social distribution is only "friends"/"solo", salience is flat 0.41. | HIGH -- determines implementation sequencing and algorithm complexity (dual-mode vs single-mode) | Hard prerequisite. Pre-production means no backward compatibility needed. Implement MW v2 first, then Stage 5. |
| Q-002 | What is the convergence bound for the self-reinforcing observation loop? | R5 updates -> R7 observations -> R5. Log2 scaling provides sub-linear damping. But is it sufficient? At what cycle count does the system stabilize? | HIGH -- runaway amplification could corrupt memory quality | Needs formal analysis. Propose: cap per-cycle delta to 10% of current value. Run 20-cycle simulation with synthetic data to validate convergence. |
| Q-003 | How should MTP tier changes propagate to R3? | R5 sets memory_tier. R3 reads tier for decay_multiplier. Same cycle or next cycle? | MEDIUM -- affects whether a newly promoted CORE record still decays in the promoting cycle | Next cycle. R3 runs before R5 in the pipeline (R3 is phase 3, R5 is phase 5). R5 sees post-R3 data. MTP tier set by R5 is read by R3 in the NEXT cycle. |
| Q-004 | Should EPC compression be reversible? | If EPC incorrectly merges distinct episodes, the source episodes are ARCHIVED. Can they be restored? | MEDIUM -- data loss risk if compression threshold is wrong | Yes. EpisodeArchival records the composite_id. Implement un-archive operation that restores source episodes and deletes composite. Add to CLV coherence checks. |
| Q-005 | What is the retention policy for st_observations? | Append-only, currently no cleanup. Table grows unboundedly. | MEDIUM -- affects ObservationEvidenceLoader query performance | Propose: 180-day rolling window for aggregate queries. Keep full history for audit but aggregate queries only scan recent window. |
| Q-006 | Should intent signals be wired to R6/R7 or remain routing-only? | IntentSignalDetector produces List[IntentSignal] but they don't persist to any truth table. Currently dead output. | LOW (current), HIGH (if K1 needs intent history) | Defer to M5E. If K1 needs intent history for recall, wire to st_prospective with intention_type=INTENT_SIGNAL. Otherwise keep as routing metadata. |
| Q-007 | Which Section 4 vs Section 13 definitions are authoritative for each algorithm? | Stage 5 proposal has internal contradictions. Corrections doc says Section 4 is authoritative for algorithm names and dataclasses. But Section 13 has implementation details not present in Section 4. | HIGH -- implementation correctness depends on this | Section 4 for: algorithm names, dataclass definitions, core algorithm logic. Section 13 for: integration details, wiring, phase runner specifics. Create ADR to codify this resolution. |
| Q-008 | How should CLV SEED recommendations be implemented? | CLV detects person entities without st_social entries and recommends SEED. But who creates the social entry? R5 or R7? | MEDIUM -- affects R5 output type and R7 writer | R5 produces SocialRelationshipSeed output. R7 SocialLayerWriter handles INSERT. CLV only recommends; R7 executes. |
| Q-009 | Should BGT-SM and TDL-HCO receive any code changes in Stage 5? | Skeleton says KEEP for both. Stage 5 proposal says "no changes" for both. But BGT-SM benefits from EWR-cleaned edges and TDL-HCO benefits from EST-enriched routines. | LOW -- both benefit from upstream improvements without code changes | No code changes. BGT-SM gets better input (edges) and TDL-HCO gets better input (routines). Quality improvement is emergent, not algorithmic. |
| Q-010 | What observability is needed for the 5-phase execution runner? | New runner replaces current 4-phase orchestrator. Needs metrics, traces, and logs for phase transitions, dependency resolution, and error propagation. | MEDIUM -- without observability, debugging phase ordering issues is impossible | Emit per-phase: start/end timestamps, algorithm list, dependency status, error count. Add phase transition trace spans. |

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **R5** | Phase 5 of the P03 consolidation pipeline. The "Dream Exploration" phase that runs after decay/dedup (R3) and edge enrichment (R4), before merge arbitration (R6) and truth writing (R7). |
| **BGT-SM** | Bisociative Graph Traversal with Semantic Memory. Algorithm that discovers non-obvious connections via random-walk-with-restart over the knowledge graph, using PMI (Pointwise Mutual Information) to score connection strength. |
| **CPN** | Causal Perturbation Network. Algorithm that generates counterfactual scenarios by perturbing a causal DAG built from episode temporal ordering. Scheduled for DELETION in M5C. |
| **TPN-MCTS** | Temporal Projection Network via Monte Carlo Tree Search. Algorithm that performs forward simulation using UCT (Upper Confidence Trees). Scheduled for DELETION in M5C. |
| **SPC-UQ** | Semantic Pattern Completion with Uncertainty Quantification. Algorithm for episodic gap detection and Bayesian reconstruction. Being REFOCUSED from generation to prospective memory cleanup. |
| **TDL-HCO** | Temporal Difference Learning with Habitual Chain Optimization. Algorithm that optimizes detected routines by finding bottleneck steps using TD learning value functions. |
| **EST** | Episodic Strength Tracker. Stage 5 NEW algorithm that breaks flat salience via observation reinforcement counting with logarithmic scaling and emotional diversity bonuses. |
| **ASU** | Anchor Seeding & Update. Stage 5 NEW algorithm that creates Bayesian anchors (Beta-Bernoulli priors) from st_observations distribution aggregates. 9 pre-defined anchor specs. |
| **SPR** | Semantic Pattern Reinforcement. Stage 5 NEW algorithm that differentiates pattern confidence using observation reinforcement (primary) and text specificity scoring (secondary). |
| **SRE** | Social Relationship Enrichment. Stage 5 NEW algorithm that computes per-entity sentiment, trajectory, emotional diversity, and health scores from observation evidence. |
| **EWR** | Edge Weight Refinement. Stage 5 NEW algorithm that refines KG edge weights via multi-enricher boost, co-occurrence reinforcement, and noise demotion. |
| **CLV** | Cross-Layer Coherence Verification. Stage 5 NEW algorithm that verifies semantic referential integrity across truth tables (orphan entities, dangling edges, ungrounded social, orphan patterns). |
| **CTD** | Contradiction Detection. Stage 5 NEW algorithm that finds real contradictions in memory and resolves via observation evidence tiebreaker. Replaces CPN. |
| **MTP** | Memory Tier Promotion. Stage 5 NEW algorithm that assigns memory tiers (TRANSIENT/ACTIVE/STABLE/CORE) based on observation reinforcement count and record age. Higher tiers receive reduced R3 decay. |
| **EPC** | Episode Compression. Stage 5 NEW algorithm that compresses recurring similar episodes into composites with frequency metadata via entity overlap grouping and text similarity clustering. |
| **SPG** | Salience Propagation through Graph. Stage 5 NEW algorithm that propagates salience from high-importance episodes to connected entities and edges via single-hop forward pass. |
| **NTD** | Narrative Thread Detection. Stage 5 NEW algorithm that discovers causal/temporal chains across episodes forming coherent narrative arcs. |
| **st_observations** | Append-only observation log in PostgreSQL. Created by R7 ObservationRecorder when writing to truth tables. 32 columns across 8 context categories. Primary evidence source for all Stage 5 algorithms. |
| **st_anchors** | NEW truth table for Bayesian anchor priors. Created by ASU algorithm. Stores anchor_id, alpha, beta (Beta-Bernoulli parameters), distribution source, drift detection flags. |
| **ObservationEvidenceLoader** | Stage 5 shared infrastructure component that queries st_observations via 3 SQL aggregation queries and returns ObservationEvidence (record_stats + distributions + entity_observations). |
| **MW v2** | Memory Writer version 2. K1 component that extracts 34-field memory atoms with enriched cognitive dimensions (affect, narrative, temporal, social, salience, novelty, elaboration, identity). Dramatically improves observation evidence quality for Stage 5 algorithms. |
| **Memory Tier** | Classification of memory durability: TRANSIENT (full decay), ACTIVE (30% reduced), STABLE (70% reduced), CORE (zero decay -- permanent). Set by MTP, read by R3. |
| **Observation reinforcement** | An st_observations row with observation_type='REINFORCEMENT', indicating that a truth table record was updated/confirmed during a consolidation cycle. The primary evidence signal for Stage 5 algorithms. |
| **USE_M5_EMITTERS** | Feature flag in dream_explorer.py that controls whether R5 outputs flow to R6/R7. Defaults to False, silently discarding outputs. |

---

## Appendix B: References

### Source Files

| File | Path | Lines |
|------|------|------:|
| Phase runner | `k0/pipelines/p03/phases/r5_dream_explorer.py` | 1,070 |
| Orchestrator | `k0/modules/consolidation/dream/dream_explorer.py` | 1,439 |
| Phase config | `k0/pipelines/p03/r5_config.py` | 241 |
| Dream config | `k0/modules/consolidation/dream/config.py` | ~180 |
| Models | `k0/modules/consolidation/dream/models.py` | 411 |
| Compute budget | `k0/modules/consolidation/dream/compute_budget.py` | 289 |
| Intent signals | `k0/modules/consolidation/dream/intent_signals.py` | 262 |
| MCTS persistence | `k0/modules/consolidation/dream/mcts_persistence.py` | ~438 |
| BGT-SM | `k0/modules/consolidation/algorithms/bgt_sm.py` | 1,208 |
| CPN (DELETE) | `k0/modules/consolidation/algorithms/cpn.py` | 1,106 |
| MCTS (DELETE) | `k0/modules/consolidation/algorithms/mcts.py` | 1,113 |
| MCTS Shadow (DELETE) | `k0/modules/consolidation/algorithms/mcts_shadow.py` | 918 |
| SPC-UQ (REFOCUS) | `k0/modules/consolidation/algorithms/spc_uq.py` | 1,253 |
| TDL-HCO | `k0/modules/consolidation/algorithms/tdl_hco.py` | 1,025 |
| Intent signal detector | `k0/modules/consolidation/algorithms/intent_signal_detector.py` | 631 |
| Routine detector | `k0/modules/consolidation/algorithms/routine_detector.py` | 710 |
| Observation context | `k0/modules/consolidation/algorithms/observation_context.py` | ~310 |
| Phase outputs | `k0/pipelines/p03/phase_outputs.py` | 892 (R5 at lines 497-573, 782-790) |
| Module contract | `k0/contracts/modules/consolidation.dream_explorer.v1.yaml` | 248 |
| Pipeline contract | `k0/contracts/pipelines/p03_consolidation.v1.yaml` | 433 |

### Reference Documents

| Document | Path | Lines | Purpose |
|----------|------|------:|---------|
| Master Implementation Skeleton | `docs/plans/MASTER_IMPLEMENTATION_SKELETON.md` | Epic 5.6 at lines 5402-5600 | Epic definition, algorithm status, skip conditions, output types, known issues |
| Stage 5 Refinement Proposal | `docs/pipelines/p03/stage5_refinement_proposal.md` | 4,882 | Complete algorithm designs, evidence analysis, MW v2 impact, phase execution, success criteria |
| Stage 5 Proposal Corrections | `docs/pipelines/p03/stage5_proposal_corrections.md` | 1,640 | Critical issues: name confusion, dataclass conflicts, phase contradictions, missing infrastructure, MW redesign |
| Discovery Template | `docs/pipelines/p03_enhancement_discovery/DISCOVERY_TEMPLATE.md` | 1,420 | Template for this document |

### Test Files

| Category | Path Pattern | Files | Tests |
|----------|-------------|------:|------:|
| Dream unit/integration | `tests/k0/modules/consolidation/dream/test_*.py` | 6 | 156 |
| Benchmarks | `tests/k0/modules/consolidation/benchmarks/benchmark_*.py` | 5 | 83 |
| Staging | `tests/k0/modules/consolidation/staging/test_truth_write_assembler_r5.py` | 1 | 26 |
| Benchmark support | `tests/k0/modules/consolidation/benchmarks/r5_*.py` | 6 | 0 |
| Benchmark packs | `tests/k0/modules/consolidation/benchmarks/packs/*.py` | 15 | 0 |
| **Total** | | **33** | **265** |

### Quantitative Summary

| Metric | Value |
|--------|-------|
| R5 production source lines | 12,424 |
| R5 test lines | 18,614 |
| R5 test functions | 265 |
| Current algorithms | 9 (2 DELETE, 1 REFOCUS, 6 KEEP/ACTIVE) |
| Stage 5 new algorithms | 10 (+ 2 updates to existing) |
| Truth tables touched | 11 (8 read, 11 write via R7) |
| Output types (current) | 7 |
| Output types (Stage 5 total) | 23 |
| Known gaps (functional) | 10 |
| Known gaps (contract) | 5 |
| Known gaps (architecture) | 7 |
| Known risks | 10 |
| Open questions | 10 |
| Lines to delete (M5C) | ~11,161 |
| Lines to add (M5E) | ~7,550 |
| Missing migrations | 3 (0065, 0067, 0073) |
| Missing data loaders | 3 |
| Missing contracts | 10+ (algorithms, evidence loader, anchors table) |
| Missing ADRs | 1+ (ADR-P03-STAGE5) |
