# P03 R2 Episodic Integration -- Phase Discovery & Enhancement Plan

> **Epic 5.3 Discovery**: Full audit of the R2 Episodic Integration phase (DBSCAN/HDBSCAN clustering
> of events into coherent episodes for the P03 consolidation pipeline). Covers code, contracts,
> algorithms, data flow, storage, observability, tests, dependencies, performance, gaps, and
> enhancement proposals.

---

## 0. Discovery Metadata

| Field | Value |
| ----- | ----- |
| Pipeline ID | P03 |
| Module Scope | consolidation.algorithms.episode_splitter, consolidation.algorithms.episodic_dbscan, consolidation.algorithms.episodic_hdbscan, consolidation.algorithms.composite_distance, consolidation.algorithms.centroid_calculator, consolidation.algorithms.eps_adjuster, consolidation.algorithms.min_samples_adjuster, consolidation.algorithms.cluster_quality, pipelines.p03.phases.r2_episodic_integrator |
| Discovery Date | 2026-03-02 |
| Milestone Target | M5 |
| Governing ADRs | ADR-K010 (P03 consolidation architecture), ADR-K010.1 (sleep-cycle state machine), ADR-K010.9 (capability-based security) |
| Related Dossier | `docs/pipelines/P03_consolidation_dossier_v2.md` |
| Author | copilot-claude |
| Status | DRAFT |

---

## 1. Current State Audit

### 1.1 Code Inventory

| # | File (relative path) | Lines | Status | Last Modified | Purpose |
| - | -------------------- | ----- | ------ | ------------- | ------- |
| 1 | k0/pipelines/p03/phases/r2_episodic_integrator.py | 1573 | MOD | 2026-01-25 | R2 phase wrapper: orchestrates episodic clustering -- splits events, runs HDBSCAN/DBSCAN, computes centroids, matches existing episodes, updates event states, tracks quality metrics, triggers adaptive learning |
| 2 | k0/modules/consolidation/algorithms/episode_splitter.py | 367 | LEGACY | 2026-01-02 | Pre-clustering sequence splitting by time gaps (30min default), geohash distance (4-char threshold), activity type changes, and hard duration limit (4h) |
| 3 | k0/modules/consolidation/algorithms/episodic_dbscan.py | 365 | LEGACY | 2026-01-08 | DBSCAN clustering with composite distance (semantic + temporal), wraps sklearn DBSCAN with precomputed distance matrix, outputs EpisodeCluster list |
| 4 | k0/modules/consolidation/algorithms/episodic_hdbscan.py | 532 | LEGACY | 2026-01-08 | HDBSCAN alternative with soft noise rescue (outlier_score < threshold), fallback to DBSCAN if hdbscan library not installed |
| 5 | k0/modules/consolidation/algorithms/composite_distance.py | 358 | LEGACY | 2026-01-18 | Composite distance metric: (1-temporal_weight) *cosine_distance + temporal_weight* normalized_time_distance, with 4h hard limit |
| 6 | k0/modules/consolidation/algorithms/centroid_calculator.py | 470 | LEGACY | 2026-01-02 | Importance-weighted centroid embedding per cluster (4 strategies: uniform, importance, recency, hybrid), plus EpisodeCandidate and R2StagedOutput dataclasses |
| 7 | k0/modules/consolidation/algorithms/eps_adjuster.py | 338 | LEGACY | 2026-01-08 | Adaptive eps learning via silhouette score: decrease if avg_cluster_size > 10, increase if singleton_rate > 0.20, momentum smoothing 0.9/0.1, bounds [0.15, 0.40] |
| 8 | k0/modules/consolidation/algorithms/min_samples_adjuster.py | 299 | LEGACY | 2026-01-02 | Adaptive min_samples learning: increase if singleton_rate > 0.20, decrease if < 0.05, bounds [2, 5] |
| 9 | k0/modules/consolidation/algorithms/cluster_quality.py | 415 | LEGACY | 2026-01-02 | Closed-loop quality metrics: composite formula (0.40 silhouette + 0.30 grounding + 0.20 correction + 0.10 singleton), alert system, tuning recommendations |
| 10 | k0/pipelines/p03/phase_outputs.py | 723 | LEGACY | 2026-01-26 | Defines EpisodeCluster dataclass (cluster_id, member_event_ids, member_contexts, entity_ids, centroid_embedding_id, temporal_start/end, cohesion_score, ambiguity_score, etc.) |
| 11 | k0/pipelines/p03/event_state.py | 517 | LEGACY | 2026-01-24 | P03EventState with R2 fields: cluster_id, cluster_label, is_noise, centroid_distance, episode_match_id, episode_match_similarity, reconciliation_action |
| 12 | k0/pipelines/p03/phase_interface.py | 558 | LEGACY | 2026-01-04 | P03PhaseResult, P03Phase protocol, P03RunnerContext |
| 13 | k0/pipelines/p03/observability.py | 1060 | LEGACY | 2026-01-04 | P03ObservabilityContext, P03Error |
| 14 | k0/pipelines/p03/runner_contract.py | 561 | LEGACY | 2026-01-04 | P03PhaseId enum (R0-R8), P03PhaseStatus enum |
| 15 | k0/pipelines/p03/envelope.py | 205 | LEGACY | 2026-01-04 | P03BatchEnvelope container |
| 16 | k0/modules/consolidation/algorithms/observation_context.py | -- | LEGACY | -- | ObservationContext dataclass for member_contexts in EpisodeCluster (Issue 7.6) |
| 17 | tests/k0/pipelines/p03/test_r2_episode_splitter.py | 397 | LEGACY | 2026-01-02 | Tests for EpisodeSplitter: config, splits, geohash distance, priority order (~30 tests) |
| 18 | tests/k0/pipelines/p03/test_r2_episodic_dbscan.py | 282 | LEGACY | 2026-01-02 | Tests for EpisodicDBSCAN: clustering, noise, cohesion, stats (~13 tests) |
| 19 | tests/k0/pipelines/p03/test_r2_composite_distance.py | 260 | LEGACY | 2026-01-15 | Tests for CompositeDistance: params, cosine, temporal, matrix (~21 tests) |
| 20 | tests/k0/pipelines/p03/test_r2_centroid_calculator.py | 369 | LEGACY | 2026-01-02 | Tests for CentroidCalculator: weighting strategies, normalization, variance, staged output (~22 tests) |
| 21 | tests/k0/pipelines/p03/test_r2_cluster_quality.py | 287 | LEGACY | 2026-01-02 | Tests for ClusterQualityTracker: composite formula, alerts, tuning recommendations (~20 tests) |
| 22 | tests/k0/pipelines/p03/test_r2_eps_adjuster.py | 259 | LEGACY | 2026-01-02 | Tests for EpsAdjuster: adjustment directions, momentum, bounds, cold start (~15 tests) |
| 23 | tests/k0/pipelines/p03/test_r2_min_samples_adjuster.py | 214 | LEGACY | 2026-01-02 | Tests for MinSamplesAdjuster: increase, decrease, bounds, good range (~11 tests) |
| 24 | tests/k0/pipelines/p03/test_r2_integration.py | 403 | LEGACY | 2026-01-02 | Integration tests: full phase flow, splitting triggers, adaptive learning, quality metrics (~16 tests) |

### 1.2 Contract Inventory

| # | Contract File | Version | Status | Lines | Governs |
| - | ------------- | ------- | ------ | ----- | ------- |
| 1 | k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml | v1 | active | 49 | module:consolidation.episodic_clusterer (R2 phase) |
| 2 | k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | active | 397 | pipeline:P03_CONSOLIDATION (all R0-R8 stages) |

### 1.3 Config Inventory

#### 1.3.1 YAML Config Keys

| Config File | Version | Key (dot-path) | Value | Type | Default | Required | Notes |
| ----------- | ------- | --------------- | ----- | ---- | ------- | -------- | ----- |
| consolidation.episodic_clusterer.v1.yaml | v1 | latency_budget_ms | 200 | int | 200 | yes | R2 latency target per batch |
| consolidation.episodic_clusterer.v1.yaml | v1 | side_effects[0] | read:st_vec | str | N/A | yes | Reads vector embeddings for distance computation |
| consolidation.episodic_clusterer.v1.yaml | v1 | side_effects[1] | read:st_cooccurrence | str | N/A | yes | Reads co-occurrence for Hebbian boost (not yet implemented) |
| consolidation.episodic_clusterer.v1.yaml | v1 | idempotent | true | bool | true | yes | DBSCAN deterministic given same input order |
| p03_consolidation.v1.yaml | v1 | stages[2].stage_id | stage_20_episodic_cluster | str | N/A | yes | R2 stage ID in pipeline |

#### 1.3.2 Environment Variables

| Variable | Type | Default | Required | Used By | Purpose |
| -------- | ---- | ------- | -------- | ------- | ------- |
| K0_DB_URL | url | NONE | yes | k0/db/engine.py (shared) | PostgreSQL connection for st_epi episode queries and st_learned_weights reads |

> **Note**: R2 does not read any R2-specific environment variables. Database connectivity is inherited from shared K0 engine. Episode matching queries and adaptive parameter persistence use syscalls injected via P03RunnerContext.

#### 1.3.3 Feature Flags

| Flag Name | Source | Default | Scope | Controls | Rollback Behavior |
| --------- | ------ | ------- | ----- | -------- | ----------------- |
| use_hdbscan | R2Config | True | per-cycle | Selects HDBSCAN (True) vs legacy DBSCAN (False) for clustering | Safe -- falls back to DBSCAN with configured eps |
| enable_splitting | R2Config | True | per-cycle | Whether EpisodeSplitter pre-splits events before clustering | Safe -- disabling treats all events as one sequence |
| enable_adaptive_eps | R2Config | True | per-cycle | Whether EpsAdjuster runs after clustering to learn optimal eps | Safe -- disabling keeps eps static at configured value |
| enable_adaptive_min_samples | R2Config | True | per-cycle | Whether MinSamplesAdjuster runs after clustering | Safe -- disabling keeps min_samples static |
| enable_quality_tracking | R2Config | True | per-cycle | Whether ClusterQualityTracker computes composite quality metrics | Safe -- disabling skips quality computation |
| enable_episode_matching | R2Config | True | per-cycle | Whether existing episodes in st_epi are queried for REINFORCE matching before clustering | Safe -- disabling clusters all events as novel |
| enable_canonicalization | R2Config | False | per-cycle | Whether episode clusters are merged by signature (type, location, time bucket) | Safe -- currently disabled; HDBSCAN clusters are already good |

#### 1.3.4 Constants & Magic Numbers

| Constant | Location (file:line) | Value | Type | Rationale | Externalize? |
| -------- | -------------------- | ----- | ---- | --------- | ------------ |
| DEFAULT_MAX_EPISODE_HOURS | episode_splitter.py:14 | 4.0 | float | Dossier C.3.1.1 -- episodes > 4h are likely multi-activity | yes -- should be tunable per space |
| DEFAULT_TIME_GAP_MINUTES | episode_splitter.py:15 | 30.0 | float | Dossier C.3.1.1 -- 30min gap indicates activity boundary (Zacks & Swallow 2007) | yes -- should be tunable per space |
| DEFAULT_GEOHASH_DISTANCE_THRESHOLD | episode_splitter.py:16 | 4 | int | Geohash prefix difference > 4 chars = significant location change | maybe -- depends on geography granularity |
| eps (default) | composite_distance.py DBSCANParams | 0.15 | float | Optimized for UltraBERT L2-normalized embeddings (typical cosine distance 0.10-0.30) | no -- configurable via R2Config |
| min_samples (default) | composite_distance.py DBSCANParams | 2 | int | Minimum events per core point -- allows pairs to cluster | no -- configurable |
| temporal_weight (default) | composite_distance.py DBSCANParams | 0.3 | float | 30% temporal, 70% semantic -- semantic similarity dominates | no -- configurable |
| max_temporal_gap_hours (default) | composite_distance.py DBSCANParams | 4.0 | float | Hard limit: events > 4h apart cannot cluster (returns infinity) | yes -- same as episode split limit |
| EMBEDDING_DIM | composite_distance.py:14 / centroid_calculator.py:14 | 768 | int | UltraBERT v2.1.0 output dimension | no -- tied to model |
| noise_rescue_threshold (default) | episodic_hdbscan.py HDBSCANParams | 0.5 | float | Outlier score below which noise is rescued into nearest cluster | maybe -- not tuned, may be too aggressive |
| cluster_selection_method (default) | R2Config | "leaf" | str | 'leaf' preserves small clusters better than 'eom' for episodic memory | no -- empirically validated |
| episode_reinforce_threshold | R2Config | 0.85 | float | Cosine similarity threshold for matching events to existing episodes (REINFORCE) | yes -- should be tunable per space |
| episode_query_limit | R2Config | 50 | int | Max episodes queried from st_epi per batch | yes -- may need scaling |
| SEVEN_DAYS_MS | r2_episodic_integrator.py | 604800000 | int | 7-day lookback window for existing episode matching | yes -- should be configurable |
| rescue distance threshold | episodic_hdbscan.py:_rescue_noise | 0.3 | float | Max distance for rescuing noise into existing cluster | maybe -- hardcoded magic number |
| nearby noise threshold | episodic_hdbscan.py:_rescue_noise | 0.2 | float | Max distance for forming weak cluster from noise points | maybe -- hardcoded magic number |
| eps_min | eps_adjuster.py EpsAdjustmentConfig | 0.15 | float | Lower bound for adaptive eps (tightest clustering) | no -- configurable |
| eps_max | eps_adjuster.py EpsAdjustmentConfig | 0.40 | float | Upper bound for adaptive eps (loosest clustering) | no -- configurable |
| eps_step | eps_adjuster.py EpsAdjustmentConfig | 0.02 | float | Step size for eps adjustment per cycle | no -- configurable |
| momentum | eps_adjuster.py EpsAdjustmentConfig | 0.9 | float | Smoothing factor: 90% old + 10% new to prevent oscillation | no -- configurable |
| cold_start_threshold | eps_adjuster.py EpsAdjustmentConfig | 100 | int | Minimum clusters before adaptive learning starts | yes -- may be too high for sparse spaces |
| min_samples_min | min_samples_adjuster.py MinSamplesConfig | 2 | int | Floor for min_samples (allows pairs) | no -- correct minimum |
| min_samples_max | min_samples_adjuster.py MinSamplesConfig | 5 | int | Ceiling for min_samples (requires 5+ events per cluster) | maybe -- might be too restrictive |
| WEIGHT_SILHOUETTE | cluster_quality.py | 0.40 | float | Dossier 4.3.4.1 -- silhouette is primary quality signal | no -- designed weight |
| WEIGHT_GROUNDING | cluster_quality.py | 0.30 | float | K1 grounding rate contribution to quality | no -- designed weight |
| WEIGHT_CORRECTION | cluster_quality.py | 0.20 | float | User correction rate (inverse) contribution | no -- designed weight |
| WEIGHT_SINGLETON | cluster_quality.py | 0.10 | float | Noise rate (inverse) contribution | no -- designed weight |
| ALERT_THRESHOLD_LOW | cluster_quality.py | 0.3 | float | Silhouette threshold below which quality alert may trigger | no -- configurable |
| CONSECUTIVE_FAILURES_FOR_ALERT | cluster_quality.py | 3 | int | Consecutive low-quality cycles before alerting | no -- configurable |

### 1.4 Migration Inventory

| # | Migration File | Table(s) | Operation | Columns Affected | Reversible? |
| - | -------------- | -------- | --------- | ---------------- | ----------- |
| 1 | k0/db/alembic/versions/0040_st_learned_weights.py | st_learned_weights | CREATE | +param_id, +param_key, +param_scope, +scope_id, +space_id, +current_value, +prior_value, +confidence, +sample_count, +last_updated_at | yes |
| 2 | k0/db/alembic/versions/0036_st_consolidation_audit.py | st_consolidation_audit | CREATE | +audit_id, +space_id, +audit_type, +action, +details_json, +created_at | yes |

> **Note**: R2 reads from st_learned_weights (eps, min_samples adaptive params) and writes quality metrics to st_consolidation_audit. R2 also queries st_epi for existing episode matching (Issue 2 fix) and reads embeddings from st_vec via distance computation. These tables were created in M4 migrations.

---

## 2. API Surface Map

### 2.1 Public Functions & Methods

| # | Module | Function / Method | Signature | Return Type | Consumers | Idempotent? | Notes |
| - | ------ | ----------------- | --------- | ----------- | --------- | ----------- | ----- |
| 1 | pipelines.p03.phases.r2_episodic_integrator | R2EpisodicIntegrator.run | (envelope: P03BatchEnvelope, ctx: P03RunnerContext) -> P03PhaseResult | P03PhaseResult | P03 runner (stage_20) | conditional | Idempotent if same batch produces same clusters (deterministic DBSCAN) |
| 2 | pipelines.p03.phases.r2_episodic_integrator | R2EpisodicIntegrator.should_skip | (envelope: P03BatchEnvelope) -> bool | bool | R2EpisodicIntegrator.run | yes | Checks min_batch_size and embedding presence |
| 3 | pipelines.p03.phases.r2_episodic_integrator | create_r2_phase | (config: Optional[R2Config] = None) -> R2EpisodicIntegrator | R2EpisodicIntegrator | Factory consumer | yes | Factory function for R2 phase creation |
| 4 | consolidation.algorithms.episode_splitter | EpisodeSplitter.split | (events: Sequence[SplittableEvent]) -> SplitResult | SplitResult | R2EpisodicIntegrator._split_events | yes | Pre-splits events into episodes by boundary detection |
| 5 | consolidation.algorithms.episode_splitter | EpisodeSplitter.split_long_sequences | (events: Sequence[SplittableEvent]) -> List[List[SplittableEvent]] | list | Convenience caller | yes | Simplified interface returning just episodes list |
| 6 | consolidation.algorithms.episodic_dbscan | EpisodicDBSCAN.cluster | (events: Sequence[ClusterableEvent]) -> ClusteringResult | ClusteringResult | R2EpisodicIntegrator (if use_hdbscan=False) | yes | DBSCAN with precomputed composite distance matrix |
| 7 | consolidation.algorithms.episodic_dbscan | EpisodicDBSCAN.cluster_and_update_events | (events: List[Any]) -> ClusteringResult | ClusteringResult | Direct callers needing in-place updates | no | Mutates event objects (sets cluster_id, label, is_noise) |
| 8 | consolidation.algorithms.episodic_hdbscan | EpisodicHDBSCAN.cluster | (events: Sequence[ClusterableEvent]) -> HDBSCANClusteringResult | HDBSCANClusteringResult | R2EpisodicIntegrator (if use_hdbscan=True) | yes | HDBSCAN with noise rescue and soft membership probabilities |
| 9 | consolidation.algorithms.composite_distance | CompositeDistance.compute | (event_a: EventLike, event_b: EventLike) -> float | float | EpisodicDBSCAN, EpisodicHDBSCAN (indirect) | yes | Pairwise composite distance between two events |
| 10 | consolidation.algorithms.composite_distance | CompositeDistance.build_distance_matrix | (events: Sequence[EventLike]) -> np.ndarray | np.ndarray (n x n) | EpisodicDBSCAN.cluster, EpisodicHDBSCAN.cluster | yes | Builds full pairwise distance matrix for DBSCAN/HDBSCAN |
| 11 | consolidation.algorithms.composite_distance | CompositeDistance.would_cluster | (event_a: EventLike, event_b: EventLike) -> bool | bool | Tests, diagnostics | yes | Checks if two events would cluster (distance <= eps) |
| 12 | consolidation.algorithms.centroid_calculator | CentroidCalculator.compute | (events: Sequence[CentroidableEvent], strategy: Optional[str]) -> CentroidResult | CentroidResult | R2EpisodicIntegrator._build_episode_cluster | yes | Full centroid computation with variance and weights |
| 13 | consolidation.algorithms.centroid_calculator | CentroidCalculator.compute_weights | (events: Sequence[CentroidableEvent], strategy: str) -> np.ndarray | np.ndarray | CentroidCalculator.compute | yes | Returns normalized weight array per strategy |
| 14 | consolidation.algorithms.centroid_calculator | CentroidCalculator.compute_centroid | (events: Sequence[CentroidableEvent], strategy: Optional[str]) -> np.ndarray | np.ndarray | CentroidCalculator.compute | yes | Returns L2-normalized 768-dim centroid |
| 15 | consolidation.algorithms.centroid_calculator | CentroidCalculator.compute_variance | (events: Sequence[CentroidableEvent], centroid: np.ndarray) -> float | float | CentroidCalculator.compute | yes | Mean squared cosine distance from centroid |
| 16 | consolidation.algorithms.eps_adjuster | EpsAdjuster.adjust | (current_eps: float, silhouette_score: float, avg_cluster_size: float, singleton_rate: float, total_clusters_formed: int) -> EpsAdjustmentResult | EpsAdjustmentResult | R2EpisodicIntegrator._track_quality_and_adapt | yes | Computes new eps from quality feedback |
| 17 | consolidation.algorithms.min_samples_adjuster | MinSamplesAdjuster.adjust | (current_min_samples: int, singleton_rate: float) -> MinSamplesAdjustmentResult | MinSamplesAdjustmentResult | R2EpisodicIntegrator._track_quality_and_adapt | yes | Computes new min_samples from noise level |
| 18 | consolidation.algorithms.cluster_quality | ClusterQualityTracker.compute_from_r2_output | (space_id: str, r2_output: R2OutputProtocol, grounded_clusters: int = 0, corrected_clusters: int = 0) -> ClusterQualityMetrics | ClusterQualityMetrics | R2EpisodicIntegrator._track_quality_and_adapt | yes | Sync quality computation from R2 output |
| 19 | consolidation.algorithms.cluster_quality | ClusterQualityTracker.compute_metrics | (space_id: str, r2_output: R2OutputProtocol, db_conn: AsyncDBConnection, lookback_ms: int) -> ClusterQualityMetrics | ClusterQualityMetrics | Future async callers | no | Async version querying st_feedback_signals |
| 20 | consolidation.algorithms.cluster_quality | ClusterQualityTracker.check_for_alert | (metrics: ClusterQualityMetrics) -> Optional[str] | Optional[str] | R2 post-processing | yes | Returns alert message if quality degraded |

### 2.2 Syscalls Used / Required

| # | Syscall | Signature | Status | Used By | SQL Pattern (if DB) | Notes |
| - | ------- | --------- | ------ | ------- | ------------------- | ----- |
| 1 | get_learned_param | (space_id: str, param_key: str) -> Optional[float] | exists | R2EpisodicIntegrator._get_dbscan_params | SELECT current_value FROM st_learned_weights WHERE space_id=$1 AND param_key=$2 | Reads adaptive eps and min_samples |
| 2 | set_learned_param | (space_id: str, param_key: str, param_value: float) -> None | exists | R2EpisodicIntegrator._track_quality_and_adapt | INSERT/UPSERT INTO st_learned_weights | Persists adjusted eps/min_samples |
| 3 | execute_query | (query: str, *args) -> List[Dict] | exists | R2EpisodicIntegrator._query_existing_episodes | SELECT FROM st_epi e LEFT JOIN st_vec v ON e.embedding_id = v.embedding_id WHERE ... | Episode matching (Issue 2 fix) |

### 2.3 Internal Helpers (non-public but critical path)

| # | Module | Function | Signature | Called By | Purpose | Risk if Changed |
| - | ------ | -------- | --------- | --------- | ------- | --------------- |
| 1 | r2_episodic_integrator | _initialize_components | (ctx: P03RunnerContext) -> None | R2EpisodicIntegrator.run | Creates EpisodeSplitter, HDBSCAN/DBSCAN clusterer, CentroidCalculator, QualityTracker, EpsAdjuster, MinSamplesAdjuster | Breaks all R2 clustering if component wiring changes |
| 2 | r2_episodic_integrator | _get_dbscan_params | (ctx, space_id) -> DBSCANParams | R2EpisodicIntegrator.run | Loads eps/min_samples from config or st_learned_weights | Breaks adaptive learning if syscall changes |
| 3 | r2_episodic_integrator | _split_events | (events: List[EventAdapter]) -> List[List[EventAdapter]] | R2EpisodicIntegrator.run | Delegates to EpisodeSplitter.split | Bypasses splitting if splitter not initialized |
| 4 | r2_episodic_integrator | _update_event_states | (events, clustering_results, noise_ids) -> None | R2EpisodicIntegrator.run | Updates cluster_id, cluster_label, is_noise on P03EventState | Breaks R3+ phases that depend on cluster assignments |
| 5 | r2_episodic_integrator | _build_episode_cluster | (cluster_id, member_ids, cluster_events, centroid_result) -> EpisodeCluster | R2EpisodicIntegrator.run | Constructs full EpisodeCluster with sentiment, emotion, location, participants, NER entities, title, summary, ambiguity_score | Most complex helper -- aggregates 15+ fields from events |
| 6 | r2_episodic_integrator | _match_events_to_existing_episodes | (events, existing_episodes) -> Tuple[matched, novel] | R2EpisodicIntegrator.run | Matches events to st_epi episodes by cosine similarity (>= 0.85 = REINFORCE) | Breaks episode dedup if threshold miscalibrated |
| 7 | r2_episodic_integrator | _query_existing_episodes | (ctx, space_id, tenant_id, time_start_ms, time_end_ms) -> List[Dict] | R2EpisodicIntegrator.run | Queries st_epi + st_vec for existing episodes with embeddings | Network-dependent; failure falls back to clustering all events |
| 8 | r2_episodic_integrator | _canonicalize_episodes | (episodes) -> tuple[List[EpisodeCluster], int] | R2EpisodicIntegrator.run | Merges episodes with same signature (type, location, time bucket) | Currently disabled (enable_canonicalization=False) |
| 9 | r2_episodic_integrator | _infer_episode_type | (ep: EpisodeCluster) -> str | _canonicalize_episodes | Maps activity_type_ultrabert / activity_type / location to episode type string | 3-level fallback: UltraBERT (12 types) > legacy (14 types) > location-based |
| 10 | r2_episodic_integrator | _compute_confidence | (event_count, temporal_start, temporal_end, participant_count, cohesion, location_purity) -> float | _recompute_confidence, _merge_episodes | Weighted confidence: 0.25 event + 0.20 temporal + 0.15 participant + 0.25 cohesion + 0.15 location | Formula weights are hardcoded |
| 11 | r2_episodic_integrator | _compute_ambiguity_score | (location_hint, participants_json, activity_type, activity_type_ultrabert, entity_ids, cluster_events) -> float | _build_episode_cluster | Counts missing critical fields (location, participants, activity, entities) with bonus penalties for small clusters and missing sentiment | M0-E2-I5 uncertainty quantification |
| 12 | r2_episodic_integrator | _track_quality_and_adapt | (ctx, space_id, candidates, noise_ids, params) -> Optional[ClusterQualityMetrics] | R2EpisodicIntegrator.run | Computes quality, triggers eps/min_samples adjustment, persists learned params | Async; failure is logged but non-fatal |
| 13 | r2_episodic_integrator | _aggregate_context_fields | (contexts: List[ObservationContext]) -> tuple | _build_episode_cluster,_merge_episodes | Aggregates sentiment (avg), salience (max), dominant location, dominant social context from member contexts | Issue 7.6 context aggregation |
| 14 | composite_distance | _cosine_distance_arrays | (arr_a, arr_b) -> float | CompositeDistance.compute, build_distance_matrix | Core cosine distance: 1 - dot(a,b)/(|a|*|b|) | Breaks all distance computation if normalization changes |
| 15 | composite_distance | _normalized_time_distance | (time_diff_ms) -> float | CompositeDistance.compute | min(1.0, time_diff_ms / max_temporal_gap_ms) | Linear normalization; bounds at 1.0 |
| 16 | episodic_hdbscan | _rescue_noise | (events, labels, probabilities, outlier_scores, distances) -> Tuple[labels, rescued_indices] | EpisodicHDBSCAN.cluster | Assigns noise points with outlier_score < threshold to nearest cluster or creates weak episode | Hardcoded distance thresholds (0.3, 0.2) |

### 2.4 Classes & Dataclasses

| # | Module | Class | Base Class / Protocol | Key Attributes | Key Methods | Consumers |
| - | ------ | ----- | --------------------- | -------------- | ----------- | --------- |
| 1 | r2_episodic_integrator | R2Config | dataclass | min_batch_size: int=2, eps: float=0.0, min_samples: int=0, semantic_weight: float=0.7, temporal_weight: float=0.3, use_hdbscan: bool=True, noise_rescue_threshold: float=0.5, cluster_selection_method: str="leaf", enable_episode_matching: bool=True, episode_reinforce_threshold: float=0.85 | N/A (data only) | R2EpisodicIntegrator |
| 2 | r2_episodic_integrator | R2EpisodicIntegrator | (none) | config: R2Config, PHASE_ID: P03PhaseId.R2_CLUSTER | run(), should_skip(), idempotency_key() | P03 runner |
| 3 | r2_episodic_integrator | EventAdapter | dataclass | event: P03EventState | event_id, timestamp, embedding_768, geohash, ner_entities, importance_score (properties) | R2EpisodicIntegrator.run |
| 4 | episode_splitter | SplitConfig | dataclass(frozen) | max_episode_hours: float=4.0, time_gap_minutes: float=30.0, geohash_distance_threshold: int=4 | validate(), to_dict(), from_dict(), max_episode_ms, time_gap_ms (properties) | EpisodeSplitter |
| 5 | episode_splitter | EpisodeSplitter | (none) | config: SplitConfig | split(), split_long_sequences(), get_split_stats() | R2EpisodicIntegrator |
| 6 | episode_splitter | SplitResult | dataclass | episodes: List[List], split_count: int, split_reasons: Dict[str,int], total_events: int | episode_count (property) | EpisodeSplitter.split return |
| 7 | composite_distance | DBSCANParams | dataclass(frozen) | eps: float=0.15, min_samples: int=2, temporal_weight: float=0.3, max_temporal_gap_hours: float=4.0 | validate(), to_dict(), from_dict(), semantic_weight, max_temporal_gap_ms (properties) | CompositeDistance, EpisodicDBSCAN, EpisodicHDBSCAN |
| 8 | composite_distance | CompositeDistance | (none) | params: DBSCANParams | compute(), compute_from_arrays(), build_distance_matrix(), get_semantic_distance(), get_temporal_distance(), would_cluster() | EpisodicDBSCAN, EpisodicHDBSCAN |
| 9 | episodic_dbscan | EpisodicDBSCAN | (none) | params: DBSCANParams, distance_calculator: CompositeDistance | cluster(), cluster_and_update_events(), get_cluster_stats() | R2EpisodicIntegrator |
| 10 | episodic_dbscan | ClusteringResult | dataclass | clusters: List[EpisodeCluster], total_events: int, cluster_count: int, noise_count: int, labels: List[int] | singleton_rate (property) | EpisodicDBSCAN.cluster return |
| 11 | episodic_hdbscan | HDBSCANParams | dataclass(frozen) | min_cluster_size: int=2, min_samples: int=1, cluster_selection_epsilon: float=0.0, cluster_selection_method: str="leaf", noise_rescue_threshold: float=0.5, temporal_weight: float=0.3 | validate(), to_dbscan_params(), to_dict() | EpisodicHDBSCAN |
| 12 | episodic_hdbscan | EpisodicHDBSCAN | (none) | params: HDBSCANParams, distance_calculator: CompositeDistance | cluster(), get_cluster_stats() | R2EpisodicIntegrator |
| 13 | episodic_hdbscan | HDBSCANClusteringResult | dataclass | clusters: List[EpisodeCluster], total_events, cluster_count, noise_count, rescued_count: int, labels, probabilities: List[float], outlier_scores: List[float] | singleton_rate, rescue_rate (properties) | EpisodicHDBSCAN.cluster return |
| 14 | centroid_calculator | CentroidCalculator | (none) | default_strategy: str="hybrid", normalize: bool=True | compute(), compute_weights(), compute_centroid(), compute_variance(), update_event_centroid_distances(), create_episode_candidate() | R2EpisodicIntegrator |
| 15 | centroid_calculator | CentroidResult | dataclass | centroid: np.ndarray, variance: float, weights: np.ndarray, strategy: str, event_count: int | centroid_list (property) | CentroidCalculator.compute return |
| 16 | centroid_calculator | EpisodeCandidate | dataclass | cluster_id, space_id, event_ids, event_count, centroid_embedding, temporal_start, temporal_end, cohesion_score, variance, is_noise, confidence_score | duration_ms (property) | R2 staged writes |
| 17 | centroid_calculator | R2StagedOutput | dataclass | episode_candidates: List[EpisodeCandidate], cluster_count, noise_count, avg_cluster_size, batch_silhouette_score, batch_cohesion_avg | add_candidate(), finalize(), singleton_rate (property) | R2 output container |
| 18 | centroid_calculator | WeightingStrategy | Enum(str) | UNIFORM, IMPORTANCE, RECENCY, HYBRID | N/A | CentroidCalculator |
| 19 | eps_adjuster | EpsAdjustmentConfig | dataclass(frozen) | eps_min=0.15, eps_max=0.40, eps_step=0.02, silhouette_target=0.5, momentum=0.9, cold_start_threshold=100, avg_cluster_size_high=10.0, singleton_rate_high=0.20 | validate() | EpsAdjuster |
| 20 | eps_adjuster | EpsAdjuster | (none) | config: EpsAdjustmentConfig, DEFAULT_EPS=0.15 | adjust(), load_eps(), save_eps() | R2EpisodicIntegrator |
| 21 | eps_adjuster | EpsAdjustmentResult | dataclass | previous_eps, new_eps, adjusted: bool, reason: str, silhouette_score, avg_cluster_size, singleton_rate, cold_start: bool | to_dict() | EpsAdjuster.adjust return |
| 22 | min_samples_adjuster | MinSamplesConfig | dataclass(frozen) | min_samples_min=2, min_samples_max=5, noise_threshold_high=0.20, noise_threshold_low=0.05 | validate() | MinSamplesAdjuster |
| 23 | min_samples_adjuster | MinSamplesAdjuster | (none) | config: MinSamplesConfig, DEFAULT_MIN_SAMPLES=2 | adjust(), load_min_samples(), save_min_samples() | R2EpisodicIntegrator |
| 24 | min_samples_adjuster | MinSamplesAdjustmentResult | dataclass | previous_min_samples, new_min_samples, adjusted: bool, reason: str, singleton_rate, direction: str | to_dict() | MinSamplesAdjuster.adjust return |
| 25 | cluster_quality | ClusterQualityMetrics | dataclass | silhouette_score, grounding_rate, correction_rate, singleton_rate, composite_quality, total_clusters, grounded_clusters, corrected_clusters, singleton_clusters | compute_composite(), compute_rates(), is_acceptable (property) | ClusterQualityTracker |
| 26 | cluster_quality | ClusterQualityTracker | (none) | alert_threshold=0.3, consecutive_failures=3, _recent_scores: List[float] | compute_from_r2_output(), compute_metrics(), persist_metrics(), check_for_alert(), get_tuning_recommendation(), reset_alert_state() | R2EpisodicIntegrator |
| 27 | phase_outputs | EpisodeCluster | dataclass | cluster_id, member_event_ids, member_contexts, entity_ids, ambiguity_score, centroid_embedding_id, dominant_sentiment, dominant_emotion, aggregated_sentiment, aggregated_salience, dominant_location, dominant_social_context, temporal_start, temporal_end, location_hint, location_type, participants_json, activity_type, activity_type_ultrabert, cohesion_score, title, summary | event_count (property) | R2, R6, R7, K1 |

---

## 3. Algorithm Inventory

### 3.1 Algorithm Catalog

| # | Algorithm | File | Scientific Basis | Input | Output | Complexity | Parameters |
| - | --------- | ---- | ---------------- | ----- | ------ | ---------- | ---------- |
| 1 | EpisodeSplitter | episode_splitter.py | Event segmentation theory (Zacks & Swallow 2007): people segment experience into discrete events at prediction error boundaries | Sequence[SplittableEvent] (sorted by timestamp) | SplitResult (list of episode sequences + split metadata) | O(n) linear scan | max_episode_hours=4.0, time_gap_minutes=30.0, geohash_distance_threshold=4 |
| 2 | CompositeDistance | composite_distance.py | Temporal binding in episodic memory (Tulving 2002): events occurring close in time are more likely same episode | (EventLike, EventLike) or Sequence[EventLike] | float distance or n x n distance matrix | O(d) per pair, O(n^2 * d) for matrix where d=768 | eps=0.15, temporal_weight=0.3, max_temporal_gap_hours=4.0 |
| 3 | EpisodicDBSCAN | episodic_dbscan.py | DBSCAN (Ester et al. 1996): density-based clustering finds arbitrarily-shaped clusters and noise | Sequence[ClusterableEvent] | ClusteringResult (List[EpisodeCluster], labels, counts) | O(n^2) from precomputed distance matrix (sklearn DBSCAN) | eps=0.15, min_samples=2 (via DBSCANParams) |
| 4 | EpisodicHDBSCAN | episodic_hdbscan.py | HDBSCAN (Campello et al. 2013): hierarchical DBSCAN with automatic multi-resolution clustering and soft membership | Sequence[ClusterableEvent] | HDBSCANClusteringResult (clusters, labels, probabilities, outlier_scores, rescued_count) | O(n^2) from precomputed distance matrix | min_cluster_size=2, min_samples=1, cluster_selection_method="leaf", noise_rescue_threshold=0.5 |
| 5 | CentroidCalculator | centroid_calculator.py | Prototype theory (Rosch 1978): categories represented by prototypical examples; importance-weighted centroid captures "representative" embedding | Sequence[CentroidableEvent] | CentroidResult (768-dim L2-normalized centroid, variance, weights) | O(n *d) for weighted sum, O(n* d) for variance | strategy: uniform/importance/recency/hybrid, normalize=True |
| 6 | EpsAdjuster | eps_adjuster.py | Silhouette analysis (Rousseeuw 1987): measures cluster cohesion vs separation; used as feedback signal for parameter tuning | (current_eps, silhouette_score, avg_cluster_size, singleton_rate, total_clusters_formed) | EpsAdjustmentResult (new_eps, adjusted, reason) | O(1) | eps_min=0.15, eps_max=0.40, eps_step=0.02, momentum=0.9, silhouette_target=0.5, cold_start_threshold=100 |
| 7 | MinSamplesAdjuster | min_samples_adjuster.py | Noise rate feedback: too many singletons means threshold too low, too few means threshold too high | (current_min_samples, singleton_rate) | MinSamplesAdjustmentResult (new_min_samples, adjusted, reason) | O(1) | min_samples_min=2, min_samples_max=5, noise_threshold_high=0.20, noise_threshold_low=0.05 |
| 8 | ClusterQualityTracker | cluster_quality.py | Multi-criteria quality evaluation: silhouette (automated) + grounding (K1 feedback) + correction (user feedback) + noise rate | R2OutputProtocol + optional feedback counts | ClusterQualityMetrics (composite_quality, alert status) | O(1) for computation, O(n) for persisting where n=1 row per cycle | weights: 0.40/0.30/0.20/0.10, alert_threshold=0.3, consecutive_failures=3 |

### 3.2 Algorithm Pipeline (R2 execution order)

```
events (from R1, with importance_score)
    |
    v
[1] EpisodeSplitter.split()
    -- Pre-splits by: location change > activity change > time gap > hard limit
    -- Output: List of episode sequences
    |
    v
[2] For each sequence:
    |
    +-- [2a] CompositeDistance.build_distance_matrix()
    |         -- distance = 0.7*cosine + 0.3*temporal_normalized
    |         -- Events > 4h apart get distance = infinity
    |
    +-- [2b] EpisodicHDBSCAN.cluster() (or EpisodicDBSCAN.cluster())
    |         -- HDBSCAN: auto eps, soft membership, noise rescue
    |         -- DBSCAN: fixed eps=0.15, min_samples=2
    |
    +-- [2c] _rescue_noise() [HDBSCAN only]
              -- outlier_score < 0.5: assign to nearest cluster (dist < 0.3)
              -- or create weak cluster from nearby noise (dist < 0.2)
    |
    v
[3] CentroidCalculator.compute()
    -- Weighted centroid: 0.7*importance + 0.3*recency (hybrid default)
    -- L2-normalized to 768-dim unit vector
    -- Variance = mean(cosine_distance_from_centroid^2)
    |
    v
[4] _build_episode_cluster()
    -- Aggregates: sentiment (avg), emotion (mode), location (mode),
       participants (union), NER entities, activity type, title, summary,
       ambiguity_score, ObservationContext per member
    |
    v
[5] ClusterQualityTracker.compute_from_r2_output()
    -- composite = 0.40*silhouette + 0.30*grounding + 0.20*(1-correction) + 0.10*(1-singleton)
    |
    +-- [5a] EpsAdjuster.adjust()
    |         -- if silhouette < 0.5 AND avg_size > 10: eps -= 0.02 (momentum-smoothed)
    |         -- if silhouette < 0.5 AND singleton > 0.20: eps += 0.02 (momentum-smoothed)
    |
    +-- [5b] MinSamplesAdjuster.adjust()
              -- if singleton > 0.20: min_samples += 1 (max 5)
              -- if singleton < 0.05: min_samples -= 1 (min 2)
    |
    v
[6] Update P03EventState:
    -- cluster_id, cluster_label, is_noise for each event
    -- episode_match_id, reconciliation_action for matched events
    |
    v
[7] Populate envelope.phases.r2_*:
    -- r2_clusters: List[EpisodeCluster]
    -- r2_noise_event_ids: List[str]
    -- r2_cluster_count, r2_avg_cluster_size, r2_clustering_params
```

### 3.3 Formula Reference

| # | Formula | Variables | Range | File:Line |
| - | ------- | --------- | ----- | --------- |
| 1 | `distance = semantic_weight * cosine_distance + temporal_weight * normalized_time_distance` | semantic_weight=0.7, temporal_weight=0.3, cosine_distance=[0,2], normalized_time_distance=[0,1] | [0, inf) -- inf if time gap > max_temporal_gap_ms | composite_distance.py:compute() |
| 2 | `cosine_distance = 1 - dot(a,b) / (|a| * |b|)` | a, b = 768-dim embeddings | [0, 2] -- 0=identical, 1=orthogonal, 2=opposite | composite_distance.py:_cosine_distance_arrays() |
| 3 | `normalized_time_distance = min(1.0, abs(ts_a - ts_b) / max_temporal_gap_ms)` | max_temporal_gap_ms=14,400,000 (4 hours) | [0, 1] | composite_distance.py:_normalized_time_distance() |
| 4 | `centroid = sum(weight_i * embedding_i)` with L2 normalization | weight_i from selected strategy, embedding_i = 768-dim | L2 unit sphere (norm=1) | centroid_calculator.py:compute_centroid() |
| 5 | `variance = mean((1 - cosine_similarity(event, centroid))^2)` | cosine_similarity=[-1,1] | [0, 1] -- 0=tight cluster | centroid_calculator.py:compute_variance() |
| 6 | `cohesion = 1 / (1 + variance)` | variance from centroid_calculator | (0, 1] -- 1=perfect cohesion | r2_episodic_integrator.py:run() |
| 7 | `eps_new = momentum * eps_old + (1 - momentum) * eps_adjusted` | momentum=0.9, eps_adjusted = eps_old +/- eps_step | [eps_min, eps_max] = [0.15, 0.40] | eps_adjuster.py:adjust() |
| 8 | `composite_quality = 0.40*sil_norm + 0.30*grounding + 0.20*(1-correction) + 0.10*(1-singleton)` | sil_norm=(silhouette+1)/2, all in [0,1] | [0, 1] -- target > 0.5 | cluster_quality.py:compute_composite() |
| 9 | `confidence = 0.25*event_score + 0.20*temporal_score + 0.15*participant_score + 0.25*cohesion + 0.15*location_purity` | event_score=min(1,count/10), temporal_score based on duration, cohesion in [0,1] | [0, 1] | r2_episodic_integrator.py:_compute_confidence() |
| 10 | `ambiguity_score = missing_fields/4 + penalties` | missing_fields: location, participants, activity, entities (0-4); penalties: small cluster (+0.1), no sentiment (+0.1) | [0, 1] -- 0=fully specified | r2_episodic_integrator.py:_compute_ambiguity_score() |

---

## 4. Data Flow & I/O Map

### 4.1 Phase Inputs

| # | Field | Source | Type | Required? | Fallback |
| - | ----- | ------ | ---- | --------- | -------- |
| 1 | P03EventState.embedding_768 | R0/P02 (UltraBERT embedding) | Optional[List[float]] | yes (for clustering) | Events without embeddings excluded from clustering |
| 2 | P03EventState.timestamp | Envelope event | int (ms since epoch) | yes | N/A -- mandatory field |
| 3 | P03EventState.importance_score | R1 ImportanceScorer | Optional[float] | no | 0.0 (default weight in centroid) |
| 4 | P03EventState.importance_computed | R1 ImportanceScorer | bool | no | False (treated as no importance) |
| 5 | P03EventState.geohash_6 | P02 location resolution | Optional[str] | no | None (geohash split signal inactive) |
| 6 | P03EventState.ner_entities_json | P02 NER extraction | Optional[str] | no | "[]" (no entity boundary split signal) |
| 7 | P03EventState.sentiment_score | P02 affect pipeline | float | no | 0.0 (neutral sentiment for cluster aggregation) |
| 8 | P03EventState.emotions_json | P02 affect pipeline | Optional[str] | no | "[]" (no dominant emotion) |
| 9 | P03EventState.location_name | P02 location resolution | Optional[str] | no | None (no location hint for cluster) |
| 10 | P03EventState.location_type | P02 location resolution | Optional[str] | no | None (GAP-002 location category) |
| 11 | P03EventState.participants_json | P02 social context | Optional[str] | no | "[]" (no participant aggregation) |
| 12 | P03EventState.activity_type | P02 activity classification | Optional[str] | no | "" (no activity type for episode) |
| 13 | P03EventState.activity_type_ultrabert | P02 UltraBERT INGRESS | Optional[str] | no | "" (Issue 0060: 12-type UltraBERT classification) |
| 14 | P03BatchEnvelope.context.cycle_id | Scheduler | str | yes | N/A |
| 15 | P03BatchEnvelope.context.space_id | Scheduler | str | yes | N/A |
| 16 | P03BatchEnvelope.context.tenant_id | Scheduler | str | yes | N/A |

### 4.2 Phase Outputs

| # | Field | Target | Type | Always Set? | Notes |
| - | ----- | ------ | ---- | ----------- | ----- |
| 1 | P03EventState.cluster_id | R3+ phases | Optional[str] | yes (if clustered) | 26-char hex UUID; None for unmatched events |
| 2 | P03EventState.cluster_label | R3+ phases | int | yes | DBSCAN label (0+ = cluster, -1 = noise) |
| 3 | P03EventState.is_noise | R3+ phases | bool | yes | True for noise/singleton events |
| 4 | P03EventState.episode_match_id | R6/R7 reconciliation | Optional[str] | only if matched | Episode ID from st_epi (REINFORCE action) |
| 5 | P03EventState.episode_match_similarity | R6/R7 | Optional[float] | only if matched | Cosine similarity to matched episode |
| 6 | P03EventState.episode_match_version | R6/R7 | Optional[int] | only if matched | Version of matched episode for OCC |
| 7 | P03EventState.reconciliation_action | R6/R7 | ReconciliationAction | only if matched | REINFORCE for matched events |
| 8 | P03EventState.reconciliation_reason | R6/R7 | Optional[str] | only if matched | Human-readable match explanation |
| 9 | envelope.phases.r2_clusters | R3+ phases, R6/R7 | List[EpisodeCluster] | yes | All formed episode clusters |
| 10 | envelope.phases.r2_noise_event_ids | R3+ phases | List[str] | yes | Event IDs marked as noise |
| 11 | envelope.phases.r2_cluster_count | Observability | int | yes | Number of episode clusters formed |
| 12 | envelope.phases.r2_avg_cluster_size | Observability | float | yes | Average events per cluster |
| 13 | envelope.phases.r2_clustering_params | Observability | Dict | yes | eps, min_samples, weights, matched count |

### 4.3 Skip Conditions

| # | Condition | Reason | Behavior |
| - | --------- | ------ | -------- |
| 1 | len(envelope.events) < min_batch_size (2) | Too few events for meaningful clustering | P03PhaseResult.skip(), no state changes |
| 2 | No events have embedding_768 | Cannot compute distance without embeddings | P03PhaseResult.skip(), no state changes |

### 4.4 Data Flow Diagram

```
                R1 Output (events with importance_score)
                         |
                         v
                 +--[Skip Check]--+
                 |  < 2 events?   |
                 |  No embeddings?|
                 +-------+--------+
                    No   |   Yes -> SKIP
                         v
              +--[Episode Matching]--+
              | Query st_epi (7-day  |
              | lookback) for        |
              | existing episodes    |
              +----------+-----------+
                         |
              +----------+-----------+
              | matched (>=0.85 sim) | novel (need clustering)
              | -> REINFORCE action  |
              v                      v
      [Update event states]   +--[EpisodeSplitter]--+
                              | time gap > 30min    |
                              | location change     |
                              | activity change     |
                              | duration > 4h       |
                              +----------+----------+
                                         |
                              sequences[]|
                                         v
                              +--[For each sequence]--+
                              |                       |
                              v                       |
                   [CompositeDistance]                 |
                   build_distance_matrix()            |
                              |                       |
                              v                       |
                   [HDBSCAN / DBSCAN]                 |
                   cluster(events)                    |
                              |                       |
                              v                       |
                   [CentroidCalculator]               |
                   compute(strategy=hybrid)           |
                              |                       |
                              +-------<-------<-------+
                                         |
                                         v
                   +--[_build_episode_cluster]--+
                   | Aggregate: sentiment, emotion,  |
                   | location, participants, NER,    |
                   | activity, title, summary,       |
                   | ambiguity_score, contexts       |
                   +----------------+----------------+
                                    |
                                    v
                   +--[Quality & Adaptive Learning]--+
                   | ClusterQualityTracker           |
                   | EpsAdjuster                     |
                   | MinSamplesAdjuster              |
                   +----------------+----------------+
                                    |
                                    v
                   [Populate envelope.phases.r2_*]
                   [Return P03PhaseResult.done()]
```

---

## 5. Storage & Persistence

### 5.1 Tables Read

| # | Table | Read Pattern | Fields Used | Purpose |
| - | ----- | ------------ | ----------- | ------- |
| 1 | st_learned_weights | SELECT current_value WHERE space_id=$1 AND param_key IN ('dbscan_eps', 'dbscan_min_samples') | current_value | Load adaptive clustering parameters |
| 2 | st_epi | SELECT episode_id, episode_type, primary_location, location_type, start_time_utc, end_time_utc, source_event_count, cluster_confidence, version, embedding_id WHERE tenant_id=$1 AND space_id=$2 AND archival_status='ACTIVE' | episode_id, start_time_utc, version, + joined vector | Match incoming events to existing episodes (Issue 2 dedup) |
| 3 | st_vec | LEFT JOIN st_vec v ON e.embedding_id = v.embedding_id | vector, vector_dim | Get centroid embeddings for existing episode similarity comparison |

### 5.2 Tables Written

| # | Table | Write Pattern | Fields Written | Purpose |
| - | ----- | ------------- | -------------- | ------- |
| 1 | st_learned_weights | INSERT/UPSERT via set_learned_param syscall | param_key ('dbscan_eps' or 'dbscan_min_samples'), current_value, confidence, sample_count | Persist adaptive eps/min_samples adjustments |
| 2 | st_consolidation_audit | INSERT via persist_metrics (ClusterQualityTracker) | audit_type='CLUSTER_QUALITY', action='METRICS_COMPUTED', details_json (composite, silhouette, rates) | Audit trail for cluster quality metrics |

### 5.3 In-Memory State

| # | State | Location | Lifecycle | Size Estimate | Notes |
| - | ----- | -------- | --------- | ------------- | ----- |
| 1 | Distance matrix | CompositeDistance.build_distance_matrix | Per-sequence, freed after clustering | n^2 * 4 bytes (float32) -- 100 events = 40KB | Largest memory allocation in R2; O(n^2) |
| 2 | Episode clusters list | envelope.phases.r2_clusters | Per-batch, passed to R3+ | ~1KB per cluster (EpisodeCluster dataclass) | Grows with cluster count |
| 3 | ClusterQualityTracker._recent_scores | ClusterQualityTracker instance | Across cycles (within same process) | List of up to 3 floats | Used for consecutive failure detection |
| 4 | EventAdapter list | R2EpisodicIntegrator.run | Per-batch execution | ~100 bytes per event wrapper | Wraps P03EventState for protocol compatibility |
| 5 | Existing episodes (from st_epi query) | _query_existing_episodes return | Per-batch execution | ~2KB per episode (including 768-dim vector) -- max 50 episodes = 100KB | episode_query_limit=50 caps this |

---

## 6. Event Bus & Topics

### 6.1 Events Consumed

| # | Event Type | Source | Schema | Fields Used | Trigger |
| - | ---------- | ------ | ------ | ----------- | ------- |
| 1 | p03.importance.scored.v1 | R1 ImportanceScorer | (internal P03EventState) | embedding_768, timestamp, importance_score, importance_computed | R1 completion triggers R2 start |
| 2 | p03.hebbian.updated.v1 | R1 HebbianLearner | (internal P03EventState) | (same as above; Hebbian edges not consumed by R2 directly) | R1 completion (Hebbian currently disabled) |

### 6.2 Events Emitted

| # | Event Type | Destination | Schema | Fields Set | Trigger |
| - | ---------- | ----------- | ------ | ---------- | ------- |
| 1 | p03.clusters.formed.v1 | R3 Dedup/Decay | (internal envelope.phases.r2_*) | r2_clusters, r2_noise_event_ids, r2_cluster_count, r2_avg_cluster_size, r2_clustering_params | R2 completion (P03PhaseResult.done) |

> **Note**: R2 does not emit events to the external event bus. All communication is via the P03BatchEnvelope passed through the P03 phase runner. The "events" listed above are contract-level logical events defined in consolidation.episodic_clusterer.v1.yaml.

---

## 7. Observability Audit

### 7.1 Structured Logs

| # | Log Level | Message | Extra Fields | Location | Notes |
| - | --------- | ------- | ------------ | -------- | ----- |
| 1 | INFO | "R2: Starting episodic integration phase" | cycle_id, tenant_id, space_id, event_count | r2_episodic_integrator.py:run() | Entry log for phase start |
| 2 | INFO | "R2: Skipping phase" | cycle_id, reason, duration_ms | r2_episodic_integrator.py:run() | Skip condition met |
| 3 | WARNING | "R2: Excluding events without embeddings" | total_events, events_with_embeddings, events_without_embeddings | r2_episodic_integrator.py:run() | Partial embedding coverage |
| 4 | INFO | "R2 using HDBSCAN with noise_rescue_threshold=..." | noise_rescue_threshold, cluster_selection | r2_episodic_integrator.py:_initialize_components() | Algorithm selection logging |
| 5 | INFO | "R2 using DBSCAN with eps=... min_samples=..." | eps, min_samples | r2_episodic_integrator.py:_initialize_components() | Legacy DBSCAN path |
| 6 | INFO | "R2: Matched events to existing episodes" | matched_count, novel_count, threshold | r2_episodic_integrator.py:_match_events_to_existing_episodes() | Episode matching results (Issue 2 fix) |
| 7 | DEBUG | "R2: Event matched to existing episode" | event_id, episode_id, similarity | r2_episodic_integrator.py:_match_events_to_existing_episodes() | Per-event match detail |
| 8 | INFO | "R2: Canonicalized episodes" | merged_count, canonical_count | r2_episodic_integrator.py:run() | Canonicalization results (if enabled) |
| 9 | INFO | "R2: Episodic integration complete" | cycle_id, clusters_formed, matched_to_existing, noise_events, avg_cluster_size, eps, min_samples, silhouette, duration_ms | r2_episodic_integrator.py:run() | Phase completion summary |
| 10 | EXCEPTION | "R2: Episodic integration failed" | cycle_id, error, duration_ms | r2_episodic_integrator.py:run() | Unhandled exception |
| 11 | INFO | "R2: Adjusted eps" | space_id, old_eps, new_eps, reason | r2_episodic_integrator.py:_track_quality_and_adapt() | Adaptive eps change |
| 12 | INFO | "R2: Adjusted min_samples" | space_id, old_min_samples, new_min_samples, reason | r2_episodic_integrator.py:_track_quality_and_adapt() | Adaptive min_samples change |
| 13 | WARNING | "R2: Failed to get learned params, using defaults" | error | r2_episodic_integrator.py:_get_dbscan_params() | Syscall failure fallback |
| 14 | WARNING | "R2: Failed to query existing episodes, will cluster all as new" | error | r2_episodic_integrator.py:_query_existing_episodes() | Episode matching failure fallback |
| 15 | WARNING | "R2: Failed to persist eps/min_samples adjustment" | error | r2_episodic_integrator.py:_track_quality_and_adapt() | Adaptive persistence failure |
| 16 | WARNING | "HDBSCAN not available, falling back to DBSCAN" | -- | episodic_hdbscan.py:**init**() | Library import failure |
| 17 | DEBUG | "Episode split: location change / activity change / time gap / hard limit" | specific split details | episode_splitter.py:_detect_break() | Per-split debug logging |

### 7.2 Metrics Emitted

| # | Metric Name | Type | Labels | Source | Notes |
| - | ----------- | ---- | ------ | ------ | ----- |
| 1 | r2_clusters_formed | gauge | cycle_id, space_id | P03PhaseResult.outputs_summary | Number of episode clusters per cycle |
| 2 | r2_noise_events | gauge | cycle_id, space_id | P03PhaseResult.outputs_summary | Noise/singleton count per cycle |
| 3 | r2_matched_to_existing | gauge | cycle_id, space_id | P03PhaseResult.outputs_summary | Events matched to existing episodes (Issue 2) |
| 4 | r2_avg_cluster_size | gauge | cycle_id, space_id | P03PhaseResult.outputs_summary | Average events per cluster |
| 5 | r2_silhouette | gauge | cycle_id, space_id | quality_metrics | Batch silhouette score |
| 6 | r2_duration_ms | histogram | cycle_id, space_id | P03PhaseResult | Phase execution time |
| 7 | r2_eps_current | gauge | space_id | dbscan_params | Current eps value (static or adaptive) |
| 8 | r2_min_samples_current | gauge | space_id | dbscan_params | Current min_samples value |

> **Note**: Metrics are emitted via P03PhaseResult.outputs_summary and structured logs. There is no dedicated Prometheus/StatsD instrumentation in R2 code -- metrics rely on log parsing or envelope inspection.

### 7.3 Error Handling

| # | Error Type | Severity | Recovery | Error Code | Notes |
| - | ---------- | -------- | -------- | ---------- | ----- |
| 1 | R2_CLUSTERING_ERROR | Recoverable | Retry cycle | P03Error.create(phase="R2") | Catch-all for R2 failures |
| 2 | EMBEDDING_NOT_FOUND | Informational | Exclude event | (contract: exclude_event) | Events without embeddings skipped |
| 3 | CLUSTER_TIMEOUT | Recoverable | Fallback skip | (contract: fallback_skip) | Not implemented in code |
| 4 | INSUFFICIENT_EVENTS | Informational | Single cluster | (contract: single_cluster) | Not implemented -- R2 does P03PhaseResult.skip instead |
| 5 | ValueError (no embeddings) | Recoverable | Phase fail | Caught by outer try/except | CentroidCalculator raises if no valid embeddings |
| 6 | Syscall failure (get_learned_param) | Degraded | Use defaults | Logged as warning | Adaptive learning falls back to config values |
| 7 | Syscall failure (execute_query) | Degraded | Cluster all as novel | Logged as warning | Episode matching falls back to full clustering |

---

## 8. Test Coverage Audit

### 8.1 Test Inventory

| # | Test File | Tests | Lines | Coverage Target | Status |
| - | --------- | ----- | ----- | --------------- | ------ |
| 1 | test_r2_episode_splitter.py | 30 | 397 | EpisodeSplitter: config, splits, geohash distance, priority, edge cases | PASS |
| 2 | test_r2_episodic_dbscan.py | 13 | 282 | EpisodicDBSCAN: clustering, noise, cohesion, temporal bounds, stats | PASS |
| 3 | test_r2_composite_distance.py | 21 | 260 | CompositeDistance: params, cosine, temporal, matrix, edge cases | PASS |
| 4 | test_r2_centroid_calculator.py | 22 | 369 | CentroidCalculator: weighting strategies, normalization, variance, staged output | PASS |
| 5 | test_r2_cluster_quality.py | 20 | 287 | ClusterQualityTracker: composite formula, alerts, tuning recommendations | PASS |
| 6 | test_r2_eps_adjuster.py | 15 | 259 | EpsAdjuster: adjustment directions, momentum, bounds, cold start | PASS |
| 7 | test_r2_min_samples_adjuster.py | 11 | 214 | MinSamplesAdjuster: increase, decrease, bounds, good range | PASS |
| 8 | test_r2_integration.py | 16 | 403 | Full R2 phase integration: clustering flow, splitting, adaptive, quality | PASS |
| **TOTAL** | | **148** | **2471** | | |

### 8.2 Test Function Inventory

#### test_r2_episode_splitter.py (30 tests)

| # | Test | Category | Tests What |
| - | ---- | -------- | ---------- |
| 1 | test_split_config_defaults | config | Default values match Dossier C.3.1.1 |
| 2 | test_split_config_derived_properties | config | max_episode_ms and time_gap_ms computed correctly |
| 3 | test_split_config_validation_max_episode_hours | validation | Rejects max_episode_hours <= 0 |
| 4 | test_split_config_validation_time_gap_minutes | validation | Rejects time_gap_minutes <= 0 |
| 5 | test_split_config_validation_geohash_threshold | validation | Rejects geohash threshold outside [1,12] |
| 6 | test_split_config_serialization | serialization | Round-trip to_dict/from_dict preserves values |
| 7 | test_empty_input | edge case | Empty list produces empty SplitResult |
| 8 | test_single_event | edge case | Single event creates single episode |
| 9 | test_no_splits_needed | happy path | Contiguous events stay in one episode |
| 10 | test_simplified_interface | API | split_long_sequences returns just episodes list |
| 11 | test_split_on_time_gap | split signal | Gap > 30min creates new episode |
| 12 | test_split_on_hard_limit | split signal | Episode > 4h creates new episode |
| 13 | test_split_on_location_change | split signal | Geohash distance > 4 creates new episode |
| 14 | test_split_on_activity_change | split signal | Activity type change creates new episode |
| 15 | test_location_change_beats_time_gap | priority | Location change has higher priority than time gap |
| 16 | test_activity_change_beats_time_gap | priority | Activity change has higher priority than time gap |
| 17 | test_location_change_beats_activity_change | priority | Location change beats activity change |
| 18 | test_geohash_distance_identical | geohash | Identical geohashes = distance 0 |
| 19 | test_geohash_distance_one_char_diff | geohash | One char difference = distance 1 |
| 20 | test_geohash_distance_completely_different | geohash | Completely different = max distance |
| 21 | test_geohash_distance_empty | geohash | Empty geohash = max distance |
| 22 | test_geohash_distance_different_lengths | geohash | Different length strings handled |
| 23 | test_split_result_counts | metadata | split_count and split_reasons tracked correctly |
| 24 | test_get_split_stats | stats | Detailed statistics computed correctly |
| 25 | test_get_split_stats_empty | stats | Empty result produces zero stats |
| 26 | test_missing_geohash | robustness | Missing geohash doesn't cause error |
| 27 | test_missing_activity_type | robustness | Missing activity_type doesn't cause error |
| 28 | test_partial_geohash_available | robustness | Only one event has geohash -- no split |
| 29 | test_partial_activity_available | robustness | Only one event has activity -- no split |
| 30 | test_geohash_6_attribute_fallback | robustness | Falls back to geohash_6 attribute |

#### test_r2_composite_distance.py (21 tests)

| # | Test | Category |
| - | ---- | -------- |
| 1 | test_dbscan_params_defaults | config |
| 2 | test_dbscan_params_derived_properties | config |
| 3 | test_dbscan_params_validation_eps | validation |
| 4 | test_dbscan_params_validation_min_samples | validation |
| 5 | test_dbscan_params_validation_temporal_weight | validation |
| 6 | test_dbscan_params_validation_max_temporal_gap | validation |
| 7 | test_dbscan_params_serialization | serialization |
| 8 | test_cosine_distance_identical | distance |
| 9 | test_cosine_distance_orthogonal | distance |
| 10 | test_temporal_hard_limit | distance |
| 11 | test_composite_distance_formula | formula |
| 12 | test_composite_distance_mixed | formula |
| 13 | test_distance_matrix_symmetric | matrix |
| 14 | test_distance_matrix_diagonal_zero | matrix |
| 15 | test_distance_matrix_empty | matrix |
| 16 | test_would_cluster_under_eps | clustering |
| 17 | test_would_cluster_over_eps | clustering |
| 18 | test_compute_from_arrays | optimization |
| 19 | test_missing_embedding_raises | error |
| 20 | test_get_semantic_distance | decomposition |
| 21 | test_get_temporal_distance | decomposition |

#### test_r2_episodic_dbscan.py (13 tests)

| # | Test | Category |
| - | ---- | -------- |
| 1 | test_empty_input | edge case |
| 2 | test_single_event | edge case |
| 3 | test_min_samples_below_threshold | edge case |
| 4 | test_cluster_similar_events | happy path |
| 5 | test_separate_dissimilar_events | separation |
| 6 | test_temporal_separation_prevents_clustering | temporal |
| 7 | test_cohesion_score_computed | metrics |
| 8 | test_temporal_bounds_correct | validation |
| 9 | test_dominant_sentiment_computed | aggregation |
| 10 | test_cluster_and_update_events | mutation |
| 11 | test_singleton_rate | metrics |
| 12 | test_get_cluster_stats | stats |
| 13 | test_get_cluster_stats_empty | stats |

#### test_r2_centroid_calculator.py (22 tests)

| # | Test | Category |
| - | ---- | -------- |
| 1 | test_centroid_uniform_weighting | weighting |
| 2 | test_centroid_importance_weighting | weighting |
| 3 | test_centroid_recency_weighting | weighting |
| 4 | test_centroid_hybrid_weighting | weighting |
| 5 | test_weighting_same_timestamps | edge case |
| 6 | test_centroid_l2_normalized | normalization |
| 7 | test_centroid_not_normalized | normalization |
| 8 | test_centroid_single_event | edge case |
| 9 | test_centroid_no_valid_embeddings | error |
| 10 | test_variance_computed | metrics |
| 11 | test_variance_identical_embeddings | metrics |
| 12 | test_variance_single_event | edge case |
| 13 | test_compute_returns_result | integration |
| 14 | test_centroid_list_property | serialization |
| 15 | test_compute_empty_returns_zero | edge case |
| 16 | test_episode_candidate_created | dataclass |
| 17 | test_duration_ms_property | dataclass |
| 18 | test_add_candidate | container |
| 19 | test_finalize_computes_aggregates | container |
| 20 | test_singleton_rate | container |
| 21 | test_to_dict | serialization |
| 22 | test_update_event_centroid_distances | mutation |

#### test_r2_cluster_quality.py (20 tests)

| # | Test | Category |
| - | ---- | -------- |
| 1 | test_composite_quality_formula_perfect | formula |
| 2 | test_composite_quality_formula_worst | formula |
| 3 | test_composite_quality_formula_weights | formula |
| 4 | test_composite_quality_mixed | formula |
| 5 | test_silhouette_normalization | normalization |
| 6 | test_rates_from_counts | computation |
| 7 | test_rates_zero_clusters | edge case |
| 8 | test_alert_after_3_failures | alert |
| 9 | test_no_alert_if_recovery | alert |
| 10 | test_no_alert_above_threshold | alert |
| 11 | test_reset_alert_state | state |
| 12 | test_high_singleton_rate_recommends_increase_min_samples | tuning |
| 13 | test_low_singleton_rate_recommends_decrease_min_samples | tuning |
| 14 | test_low_silhouette_high_singletons_recommends_increase_eps | tuning |
| 15 | test_low_silhouette_low_singletons_recommends_decrease_eps | tuning |
| 16 | test_high_correction_rate_flags_review | tuning |
| 17 | test_metrics_to_dict | serialization |
| 18 | test_is_acceptable_above_threshold | threshold |
| 19 | test_is_not_acceptable_below_threshold | threshold |
| 20 | test_compute_from_r2_output | integration |

#### test_r2_eps_adjuster.py (15 tests)

| # | Test | Category |
| - | ---- | -------- |
| 1 | test_no_adjustment_above_silhouette_target | no-op |
| 2 | test_cold_start_no_adjustment | cold start |
| 3 | test_decrease_eps_large_clusters | decrease |
| 4 | test_decrease_respects_bounds | bounds |
| 5 | test_bounds_min_enforced | bounds |
| 6 | test_increase_eps_high_noise | increase |
| 7 | test_bounds_max_enforced | bounds |
| 8 | test_momentum_smoothing_decrease | smoothing |
| 9 | test_momentum_smoothing_increase | smoothing |
| 10 | test_custom_momentum | config |
| 11 | test_no_adjustment_metrics_in_range | no-op |
| 12 | test_decrease_priority_over_increase | priority |
| 13 | test_result_to_dict | serialization |
| 14 | test_default_config | config |
| 15 | test_custom_config | config |

#### test_r2_min_samples_adjuster.py (11 tests)

| # | Test | Category |
| - | ---- | -------- |
| 1 | test_increase_on_high_singleton_rate | increase |
| 2 | test_increase_multiple_times | increase |
| 3 | test_at_max_no_increase | bounds |
| 4 | test_decrease_on_low_singleton_rate | decrease |
| 5 | test_decrease_multiple_times | decrease |
| 6 | test_at_min_no_decrease | bounds |
| 7 | test_no_change_in_good_range | no-op |
| 8 | test_exactly_at_low_threshold | boundary |
| 9 | test_exactly_at_high_threshold | boundary |
| 10 | test_bounds_min_value | bounds |
| 11 | test_bounds_max_value | bounds |

#### test_r2_integration.py (16 tests)

| # | Test | Category |
| - | ---- | -------- |
| 1 | test_full_r2_phase_produces_clusters | integration |
| 2 | test_semantically_similar_events_cluster_together | clustering |
| 3 | test_dissimilar_events_form_separate_clusters_or_noise | clustering |
| 4 | test_large_time_gap_triggers_split | splitting |
| 5 | test_location_change_triggers_split | splitting |
| 6 | test_no_split_for_close_events | splitting |
| 7 | test_silhouette_triggers_eps_decrease | adaptive |
| 8 | test_silhouette_triggers_eps_increase | adaptive |
| 9 | test_singleton_rate_triggers_min_samples_increase | adaptive |
| 10 | test_staged_writes_contain_expected_structure | output |
| 11 | test_centroid_l2_normalized | centroid |
| 12 | test_centroid_variance_low_for_similar_events | centroid |
| 13 | test_quality_metrics_computed | quality |
| 14 | test_quality_alert_mechanism | alert |
| 15 | test_distance_matrix_for_clustering | distance |
| 16 | test_temporal_weight_affects_clustering | parameter |

### 8.3 Coverage Gaps

| # | Gap | Severity | Impacted Code | Recommended Test |
| - | --- | -------- | ------------- | ---------------- |
| 1 | No tests for EpisodicHDBSCAN | HIGH | episodic_hdbscan.py (532 lines) -- entire HDBSCAN path untested | test_r2_episodic_hdbscan.py: cluster, noise rescue, fallback to DBSCAN, probabilities, outlier scores |
| 2 | No tests for R2EpisodicIntegrator.run() | HIGH | r2_episodic_integrator.py async run() -- 1573 lines, the main orchestrator | test_r2_phase_integration.py: mock syscalls, test full async run with envelope |
| 3 | No tests for episode matching (_match_events_to_existing_episodes) | HIGH | r2_episodic_integrator.py:_match_events_to_existing_episodes -- Issue 2 dedup | test_r2_episode_matching.py: match/novel split, threshold, cosine similarity |
| 4 | No tests for canonicalization (_canonicalize_episodes) | MEDIUM | r2_episodic_integrator.py:_canonicalize_episodes -- episode merging | test_r2_canonicalization.py: signature grouping, merge, type inference |
| 5 | No tests for _build_episode_cluster aggregation | MEDIUM | r2_episodic_integrator.py:_build_episode_cluster -- 15+ field aggregation | test_r2_episode_builder.py: sentiment avg, emotion mode, NER extraction, title generation |
| 6 | No tests for _compute_confidence formula | MEDIUM | r2_episodic_integrator.py:_compute_confidence -- hardcoded weights | test_r2_confidence.py: weight verification, edge cases |
| 7 | No tests for _compute_ambiguity_score | MEDIUM | r2_episodic_integrator.py:_compute_ambiguity_score -- M0-E2-I5 | test_r2_ambiguity.py: missing fields, penalties |
| 8 | No tests for EventAdapter protocol | LOW | r2_episodic_integrator.py:EventAdapter -- wraps P03EventState | test_r2_event_adapter.py: property delegation, NER parsing |
| 9 | No tests for ClusterQualityTracker.persist_metrics (async) | LOW | cluster_quality.py:persist_metrics -- DB write | test_r2_quality_persistence.py: async DB mock |
| 10 | No tests for EpsAdjuster.load_eps / save_eps (async) | LOW | eps_adjuster.py:load_eps, save_eps -- DB read/write | test_r2_eps_persistence.py: async DB mock |
| 11 | No tests for observation_context.py | LOW | observation_context.py:ObservationContext -- member contexts | Already covered by Issue 7.6 tests (if they exist) |

---

## 9. Dependency Map

### 9.1 External Dependencies

| # | Package | Version | Purpose | Imported By | License |
| - | ------- | ------- | ------- | ----------- | ------- |
| 1 | numpy | >=1.24 | Array operations for embeddings, distance matrices, centroids | composite_distance.py, episodic_dbscan.py, episodic_hdbscan.py, centroid_calculator.py, r2_episodic_integrator.py | BSD-3-Clause |
| 2 | scikit-learn | >=1.3 | sklearn.cluster.DBSCAN with precomputed metric | episodic_dbscan.py, episodic_hdbscan.py (fallback) | BSD-3-Clause |
| 3 | hdbscan | >=0.8.33 | hdbscan.HDBSCAN with precomputed metric, soft membership, outlier scores | episodic_hdbscan.py | BSD-3-Clause |

> **Note**: hdbscan is an optional dependency. If not installed, EpisodicHDBSCAN falls back to sklearn DBSCAN with simulated probabilities and outlier scores. This fallback is logged as a WARNING.

### 9.2 Internal Dependencies

| # | Module | Depends On | Dependency Type |
| - | ------ | ---------- | --------------- |
| 1 | r2_episodic_integrator.py | episode_splitter, episodic_dbscan, episodic_hdbscan, composite_distance, centroid_calculator, eps_adjuster, min_samples_adjuster, cluster_quality | Algorithm imports (all 8 R2 algorithms) |
| 2 | r2_episodic_integrator.py | event_state.ReconciliationAction | Enum for episode matching |
| 3 | r2_episodic_integrator.py | observability.P03Error | Error creation |
| 4 | r2_episodic_integrator.py | phase_interface.P03PhaseResult | Phase result protocol |
| 5 | r2_episodic_integrator.py | phase_outputs.EpisodeCluster | Output dataclass |
| 6 | r2_episodic_integrator.py | runner_contract.P03PhaseId | Phase ID enum |
| 7 | r2_episodic_integrator.py | observation_context.ObservationContext | Member context for Issue 7.6 |
| 8 | episodic_dbscan.py | composite_distance.CompositeDistance, DBSCANParams | Distance computation |
| 9 | episodic_dbscan.py | phase_outputs.EpisodeCluster | Cluster output dataclass |
| 10 | episodic_hdbscan.py | composite_distance.CompositeDistance, DBSCANParams | Distance computation |
| 11 | episodic_hdbscan.py | phase_outputs.EpisodeCluster | Cluster output dataclass |
| 12 | centroid_calculator.py | (none) | Standalone -- no K0 imports (only numpy) |
| 13 | episode_splitter.py | (none) | Standalone -- no K0 imports |
| 14 | eps_adjuster.py | (none) | Standalone -- no K0 imports |
| 15 | min_samples_adjuster.py | (none) | Standalone -- no K0 imports |
| 16 | cluster_quality.py | (none) | Standalone -- no K0 imports |

### 9.3 Dependency Notes

- **6 of 8 algorithm files are standalone** (no K0 internal imports): episode_splitter, centroid_calculator, eps_adjuster, min_samples_adjuster, cluster_quality, composite_distance. This makes them highly testable.
- **2 algorithm files** (episodic_dbscan, episodic_hdbscan) import from composite_distance and phase_outputs, creating a shallow dependency chain.
- **The phase wrapper** (r2_episodic_integrator.py) is the heaviest dependency node, importing all 8 algorithms plus 6 P03 infrastructure modules.

---

## 10. Performance Baseline

### 10.1 Theoretical Complexity

| # | Operation | Complexity | Dominant Factor | Bottleneck |
| - | --------- | ---------- | --------------- | ---------- |
| 1 | EpisodeSplitter.split | O(n) | Linear scan through sorted events | Not a bottleneck |
| 2 | CompositeDistance.build_distance_matrix | O(n^2 * d) where d=768 | All-pairs distance computation | Primary bottleneck for large batches |
| 3 | DBSCAN clustering (sklearn) | O(n^2) with precomputed | Distance matrix already built | Fast with precomputed |
| 4 | HDBSCAN clustering | O(n^2) with precomputed | Minimum spanning tree + hierarchy | Slightly slower than DBSCAN |
| 5 | CentroidCalculator.compute | O(n * d) | Weighted sum of embeddings | Fast |
| 6 | Episode matching (st_epi query) | O(e * d) where e=episode count | Cosine similarity per episode | Network-bound (DB query + comparison) |
| 7 | _build_episode_cluster | O(m) where m=member count | JSON parsing per event | Fast but many allocations |
| 8 | Quality tracking + adaptive | O(1) | Simple arithmetic | Negligible |

### 10.2 Contract Latency Budget

| # | Metric | Budget | Basis | Notes |
| - | ------ | ------ | ----- | ----- |
| 1 | R2 total latency | 200ms | consolidation.episodic_clusterer.v1.yaml | Per-batch, not per-event |
| 2 | Distance matrix | ~100ms | Estimated for 100 events (768-dim) | n^2 * 768 float ops |
| 3 | HDBSCAN/DBSCAN | ~50ms | Estimated for 100-event precomputed matrix | sklearn overhead |
| 4 | Centroid computation | ~10ms | Estimated for 10 clusters | Weighted sum per cluster |
| 5 | Episode matching (DB) | ~50ms | Network round-trip + comparison | episode_query_limit=50 |

### 10.3 Scalability Concerns

| # | Concern | Trigger | Impact | Mitigation |
| - | ------- | ------- | ------ | ---------- |
| 1 | Distance matrix O(n^2) memory | Batch size > 1000 events | 1000^2 * 4 bytes = 4MB; 5000^2 = 100MB | EpisodeSplitter pre-splits into smaller sequences |
| 2 | All-pairs computation time | Batch size > 500 events | >1s for matrix build with 768-dim cosine | Split into sequences; vectorized numpy operations |
| 3 | Episode matching grows with history | >50 active episodes per space | Comparison time scales linearly | episode_query_limit=50 caps query; future: ANN index |
| 4 | HDBSCAN memory | n > 5000 in single sequence | MST computation dominates | Pre-splitting should prevent this |

---

## 11. Gap Analysis & Enhancement Register

### 11.1 Contract-Code Divergence

| # | Gap ID | Contract Says | Code Does | Severity | Fix |
| - | ------ | ------------- | --------- | -------- | --- |
| 1 | R2-DIV-001 | eps=0.3, min_samples=3 | eps=0.15, min_samples=2 (DBSCANParams defaults) | MEDIUM | Contract is stale -- update YAML to match code (0.15 for UltraBERT L2-normalized embeddings) |
| 2 | R2-DIV-002 | metric: cosine | metric: precomputed (composite distance = cosine + temporal) | LOW | Contract incomplete -- distance is composite, not pure cosine |
| 3 | R2-DIV-003 | co-occurrence boost (boost_factor = 1 - cooccurrence_weight * edge_weight) | Not implemented -- st_cooccurrence read listed as side effect but no code uses it | MEDIUM | Remove co-occurrence from contract OR implement Hebbian distance boost |
| 4 | R2-DIV-004 | silhouette target > 0.3 | silhouette target > 0.5 (eps_adjuster.py silhouette_target=0.5) | LOW | Code uses stricter target than contract; update contract |
| 5 | R2-DIV-005 | noise ratio target < 10% | No explicit 10% target in code; singleton_rate thresholds are 0.05/0.20 | LOW | Contract and code use different noise targets |
| 6 | R2-DIV-006 | ULID cluster identifier | UUID hex[:26] cluster IDs | LOW | Cluster IDs are 26-char hex (UUID-based), not ULIDs |
| 7 | R2-DIV-007 | failure_mode: CLUSTER_TIMEOUT with fallback_skip | Not implemented in code -- no timeout mechanism | MEDIUM | Add configurable timeout or remove from contract |
| 8 | R2-DIV-008 | failure_mode: INSUFFICIENT_EVENTS with single_cluster | Not implemented -- code does P03PhaseResult.skip instead of single cluster | LOW | Code behavior is more conservative (skip vs single cluster) |

### 11.2 Signal Gaps (MW v2 signals NOT used by R2)

| # | Signal | MW v2 Field | Current Use in R2 | Gap Description |
| - | ------ | ----------- | ----------------- | --------------- |
| 1 | narrative_thread_id | P03EventState.narrative_thread_id | NOT USED | Events in same narrative thread should have reduced distance (narrative continuity) |
| 2 | temporal_anchor | P03EventState.temporal_anchor | NOT USED | Could improve temporal distance normalization for recurring events |
| 3 | participant_relationships | P03EventState.participant_relationships | NOT USED | Could add social distance dimension to composite distance |
| 4 | memory_tier | P03EventState.memory_tier | NOT USED | Could weight clustering priority by memory tier |
| 5 | spatial resolution (full) | P03EventState.location_geohash | Partial -- EventAdapter.geohash returns None | EventAdapter hardcodes geohash=None; location splitting partially inactive |
| 6 | intent_category | P03EventState.intent_category | NOT USED | Could separate intent-based activities into distinct episodes |
| 7 | social_context | P03EventState.social_context | Only aggregated in contexts, not used for distance | Could add social proximity dimension |
| 8 | co-occurrence edges | st_cooccurrence (Hebbian) | Contract lists read:st_cooccurrence but code never queries it | Hebbian edges could boost distance for co-occurring entities |

### 11.3 Known Issues (from M5 skeleton)

| # | Issue ID | Description | Impact | Priority |
| - | -------- | ----------- | ------ | -------- |
| 1 | R2-ISSUE-001 | CompositeDistance only uses 2 dimensions (semantic + temporal) -- no social, spatial, or intent distance | Episodes may merge unrelated activities at same time | HIGH |
| 2 | R2-ISSUE-002 | EpisodeSplitter time_gap_minutes=30 is hardcoded default; Dossier says 30 but R2Config allows 60 (inconsistency) | R2Config.time_gap_minutes=60 vs SplitConfig default=30; phase wrapper uses R2Config value | MEDIUM |
| 3 | R2-ISSUE-003 | HDBSCAN noise rescue threshold (0.5) and distance thresholds (0.3, 0.2) are not empirically tuned | May rescue too aggressively (outlier_score < 0.5 includes borderline points) | HIGH |
| 4 | R2-ISSUE-004 | CentroidCalculator importance-weighting may get 0.0 from R1 dead signals | If importance_score defaults to 0.0 for all events, importance weighting degenerates to uniform | MEDIUM |
| 5 | R2-ISSUE-005 | Cluster quality metrics not fed back in same cycle (delayed feedback) | EpsAdjuster and MinSamplesAdjuster only affect NEXT cycle; current cycle uses stale params | LOW |
| 6 | R2-ISSUE-006 | EventAdapter.geohash hardcoded to return None | Location-based splitting in EpisodeSplitter is effectively disabled for R2 | HIGH |
| 7 | R2-ISSUE-007 | No co-occurrence distance boost despite contract listing read:st_cooccurrence | Hebbian edges not used to reduce distance between frequently co-occurring entities | MEDIUM |
| 8 | R2-ISSUE-008 | _build_episode_cluster is 200+ lines with 15+ field aggregations | High cyclomatic complexity; difficult to test individual aggregations | MEDIUM |

---

## 12. Security & Privacy Audit

### 12.1 Data Classification

| # | Data | Classification | Handler | Notes |
| - | ---- | -------------- | ------- | ----- |
| 1 | Event embeddings (768-dim) | Internal | CompositeDistance | Cannot reconstruct text from embedding; low PII risk |
| 2 | Event text (used in summary/title generation) | PII-Sensitive | _generate_episode_summary,_generate_episode_title | Raw text included in episode summaries -- needs redaction |
| 3 | Participant names | PII | _build_episode_cluster (participants_json) | Extracted from NER and events; stored in episode cluster |
| 4 | Location data (geohash, location_name) | PII-Adjacent | EpisodeSplitter, _build_episode_cluster | Geohash encodes physical location |
| 5 | NER entities | PII | _build_episode_cluster (entity_ids from ner_entities_json) | Person names, organizations extracted by NER |
| 6 | Adaptive parameters (eps, min_samples) | Internal | st_learned_weights | Non-sensitive configuration data |
| 7 | Quality metrics (silhouette, composite) | Internal | st_consolidation_audit | Non-sensitive operational metrics |

### 12.2 Capability Audit

| # | Capability | Declared | Used | Gap |
| - | ---------- | -------- | ---- | --- |
| 1 | cluster_episodes | Yes (contract) | Yes (R2 phase) | Aligned |
| 2 | read:st_vec | Yes (contract) | Yes (episode matching joins st_vec) | Aligned |
| 3 | read:st_cooccurrence | Yes (contract) | No (never queried) | GAP -- declared but unused |
| 4 | read:st_epi | No (not in contract) | Yes (_query_existing_episodes) | GAP -- used but not declared in contract |
| 5 | write:st_learned_weights | No (not in contract) | Yes (set_learned_param for eps/min_samples) | GAP -- used but not declared |
| 6 | write:st_consolidation_audit | No (not in contract) | Yes (persist_metrics) | GAP -- used but not declared |

### 12.3 Privacy Controls

| # | Control | Status | Notes |
| - | ------- | ------ | ----- |
| 1 | PII in episode titles/summaries | NOT CONTROLLED | Raw text from events used in _generate_episode_title and_generate_episode_summary without redaction |
| 2 | Participant names in clusters | NOT CONTROLLED | participants_json includes names extracted from events |
| 3 | Location in clusters | NOT CONTROLLED | location_hint stores raw location names |
| 4 | Embedding data | SAFE | Embeddings are non-reversible vector representations |
| 5 | Audit trail PII | PARTIAL | st_consolidation_audit stores metrics JSON but not raw event data |

---

## 13. Enhancement Proposals

### Epic 5.3A: Multi-Dimensional Composite Distance

**Problem**: CompositeDistance only uses 2 dimensions (semantic + temporal). Events with different social contexts or locations that happen at the same time get clustered together.

**Proposal**: Extend CompositeDistance to support 4+ dimensions:

- Semantic distance (cosine, current)
- Temporal distance (normalized, current)
- Social distance (participant overlap: 1 - Jaccard similarity)
- Spatial distance (geohash prefix distance, normalized)
- Optional: intent distance (category mismatch penalty)
- Optional: narrative distance (thread ID mismatch penalty)

**Formula**: `distance = w_sem * d_sem + w_temp * d_temp + w_social * d_social + w_spatial * d_spatial`

**Estimated Impact**: Better episode boundaries for multi-activity families (e.g., dad working from home while kids play)

**Dependencies**: Requires EventAdapter to expose social_context, geohash, narrative_thread_id

**Effort**: MEDIUM (3-5 days)

---

### Epic 5.3B: EventAdapter Signal Activation

**Problem**: EventAdapter.geohash hardcodes return None (R2-ISSUE-006). Multiple P03EventState signals are available but not exposed through the adapter.

**Proposal**: Fix EventAdapter to properly expose:

- `geohash`: Extract from P03EventState.location_geohash or geohash_6 (currently returns None)
- `social_context`: Extract from P03EventState.social_context for social distance
- `narrative_thread_id`: For narrative continuity distance
- `intent_category`: For intent-based distance
- `activity_type`: Already available but not used in distance

**Estimated Impact**: Unlocks location-based splitting (currently dead) and enables multi-dimensional distance

**Dependencies**: None -- fields already exist on P03EventState

**Effort**: LOW (1-2 days)

---

### Epic 5.3C: HDBSCAN Noise Rescue Calibration

**Problem**: HDBSCAN noise rescue uses hardcoded thresholds (outlier_score < 0.5, rescue distance < 0.3, weak cluster distance < 0.2) that are not empirically validated (R2-ISSUE-003).

**Proposal**:

1. Extract hardcoded thresholds to HDBSCANParams configuration
2. Add configurable rescue strategy (nearest-cluster-only vs weak-cluster-creation)
3. Log rescue decisions for offline analysis
4. Create test suite for EpisodicHDBSCAN (currently 0 tests -- 8.3 Gap #1)

**Estimated Impact**: Reduces false episode merging from aggressive rescue; better noise handling

**Dependencies**: None

**Effort**: MEDIUM (3-4 days)

---

### Epic 5.3D: Contract Reconciliation

**Problem**: 8 contract-code divergences identified (R2-DIV-001 through R2-DIV-008). Contract is stale with M4 defaults and unimplemented features.

**Proposal**:

1. Update consolidation.episodic_clusterer.v1.yaml:
   - eps: 0.3 -> 0.15 (match UltraBERT defaults)
   - min_samples: 3 -> 2 (match code)
   - metric: cosine -> precomputed (composite distance)
   - Add HDBSCAN as primary algorithm
   - Remove co-occurrence boost (or implement it)
   - Add read:st_epi, write:st_learned_weights, write:st_consolidation_audit
2. Remove or implement CLUSTER_TIMEOUT failure mode
3. Align noise ratio targets

**Estimated Impact**: Documentation accuracy; unblocks capability audit compliance

**Dependencies**: None

**Effort**: LOW (1 day)

---

### Epic 5.3E: Phase Wrapper Decomposition

**Problem**: r2_episodic_integrator.py is 1573 lines with _build_episode_cluster at 200+ lines. High complexity makes testing difficult (8.3 Gap #2, #5).

**Proposal**:

1. Extract _build_episode_cluster into a separate `episode_builder.py` module
2. Extract _match_events_to_existing_episodes into `episode_matcher.py`
3. Extract _canonicalize_episodes into `episode_canonicalizer.py`
4. Extract _compute_confidence and _compute_ambiguity_score into `episode_metrics.py`
5. R2EpisodicIntegrator.run() becomes a thin orchestrator calling these modules

**Estimated Impact**: Enables unit testing of each aggregation function; reduces phase wrapper to ~500 lines

**Dependencies**: None

**Effort**: MEDIUM (3-4 days)

---

### Epic 5.3F: Hebbian Distance Boost

**Problem**: Contract declares `read:st_cooccurrence` but code never queries it (R2-DIV-003, R2-ISSUE-007). Hebbian co-occurrence edges from R1 are unused in R2 clustering.

**Proposal**:

1. Query st_cooccurrence for entity pair weights in the batch time window
2. Reduce distance between events sharing Hebbian-connected entities:
   `boosted_distance = distance * (1 - cooccurrence_weight * edge_weight)`
3. Make co-occurrence boost configurable (weight: 0.0-0.3, default 0.2)
4. Only activate after Hebbian learning is enabled in R1

**Estimated Impact**: Events about frequently co-occurring people/topics cluster more tightly

**Dependencies**: R1 HebbianLearner must be enabled (currently disabled)

**Effort**: MEDIUM (3-4 days)

---

## 14. Risk Register

| # | Risk | Probability | Impact | Mitigation |
| - | ---- | ----------- | ------ | ---------- |
| 1 | HDBSCAN library not available in production | LOW | Fallback to DBSCAN with simulated probabilities (degraded noise handling) | Pin hdbscan in requirements.txt; add import health check |
| 2 | Distance matrix OOM for large batches | LOW | Crash on batches > 5000 events | EpisodeSplitter pre-splits; add max_sequence_size guard |
| 3 | Episode matching false positives at 0.85 threshold | MEDIUM | Wrong events get REINFORCE action, corrupting existing episodes | Monitor match rates; tune threshold per space |
| 4 | Adaptive eps oscillation between cycles | LOW | eps ping-pongs between increase/decrease | Momentum smoothing (0.9) prevents rapid changes |
| 5 | No tests for HDBSCAN code path | HIGH | HDBSCAN regressions go undetected (532 lines untested) | Write comprehensive HDBSCAN test suite (Epic 5.3C) |
| 6 | PII in episode titles and summaries | MEDIUM | Privacy violation if episodes are exposed to logs or APIs | Add PII redaction to _generate_episode_title/_generate_episode_summary |
| 7 | Undeclared capabilities (read:st_epi, write:st_learned_weights) | MEDIUM | Capability audit fails; security boundary violation | Update contract (Epic 5.3D) |
| 8 | Stale contract misleads developers | MEDIUM | New code uses wrong defaults from contract (eps=0.3 vs 0.15) | Update contract immediately (Epic 5.3D) |

---

## 15. Open Questions

| # | Question | Context | Blocking? | Proposed Answer |
| - | -------- | ------- | --------- | --------------- |
| 1 | Should HDBSCAN be mandatory or optional? | Currently optional (try/except import) with DBSCAN fallback | No | Keep optional with fallback; add to requirements.txt |
| 2 | Is episode_reinforce_threshold=0.85 correct for UltraBERT? | Cosine similarity 0.85 is very high; may miss legitimate reinforcements | No | Test empirically; consider 0.75-0.80 range |
| 3 | Should canonicalization be re-enabled? | Currently disabled (enable_canonicalization=False); "HDBSCAN clusters are already good" | No | Keep disabled until evidence of duplicate episodes |
| 4 | How should co-occurrence boost interact with HDBSCAN? | Contract says boost, HDBSCAN has its own noise rescue | No | Apply boost to distance matrix before HDBSCAN, not after |
| 5 | Is cold_start_threshold=100 clusters too high? | New spaces with < 100 total clusters don't benefit from adaptive learning | No | Consider lowering to 30-50 for faster adaptation |
| 6 | Should R2 emit events to external bus? | Currently only populates envelope (internal); no bus event emission | No | Keep internal for now; add bus emission in M6 when K1 subscribes |
| 7 | Should noise events (is_noise=True) skip R3 entirely? | Currently passed through to R3; dedup/decay may process noise unnecessarily | No | Add skip condition in R3 for noise events |
| 8 | Should _compute_confidence and _compute_ambiguity_score use learned weights? | Currently use hardcoded formulas | No | Consider adaptive confidence in M6 with feedback loop |

---

## Appendix A: File Sizes Summary

| Category | Files | Total Lines |
| -------- | ----- | ----------- |
| Phase wrapper | 1 | 1573 |
| Algorithm files | 8 | 3144 |
| Contract | 1 | 49 |
| Test files | 8 | 2471 |
| **TOTAL** | **18** | **7237** |

## Appendix B: Test Count Summary

| Test File | Test Count |
| --------- | ---------- |
| test_r2_episode_splitter.py | 30 |
| test_r2_composite_distance.py | 21 |
| test_r2_centroid_calculator.py | 22 |
| test_r2_cluster_quality.py | 20 |
| test_r2_integration.py | 16 |
| test_r2_eps_adjuster.py | 15 |
| test_r2_episodic_dbscan.py | 13 |
| test_r2_min_samples_adjuster.py | 11 |
| **TOTAL** | **148** |

## Appendix C: Cross-References

| Reference | Location | Notes |
| --------- | -------- | ----- |
| P03 R0 Discovery | docs/pipelines/p03_enhancement_discovery/P03_R0_BATCH_SELECTOR_DISCOVERY.md | Batch selection phase (upstream of R2) |
| P03 R1 Discovery | docs/pipelines/p03_enhancement_discovery/P03_R1_IMPORTANCE_SCORING_DISCOVERY.md | Importance scoring phase (immediate upstream of R2) |
| M5 Skeleton | docs/plans/MASTER_IMPLEMENTATION_SKELETON.md (lines 5200-5500) | Epic 5.3 scope definition |
| Dossier Appendix C.3 | P03_consolidation_dossier_v2.md Appendix C.3 | R2 algorithm specifications |
| ADR-K010 | docs/architecture/decisions-K0/ADR-K010.md | P03 consolidation architecture |
