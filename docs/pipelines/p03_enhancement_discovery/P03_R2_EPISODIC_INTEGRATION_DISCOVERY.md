# P03 R2 Episodic Integration -- Phase Discovery & Enhancement Plan

> **Epic 5.3 Discovery**: Full audit of the R2 Episodic Integration phase (HDBSCAN clustering
> of events into coherent episodes for the P03 consolidation pipeline). Covers code, contracts,
> algorithms, data flow, storage, observability, tests, dependencies, performance, gaps, and
> enhancement proposals.

---

## 0. Discovery Metadata

| Field | Value |
| ----- | ----- |
| Pipeline ID | P03 |
| Module Scope | consolidation.algorithms.episode_splitter, ~~consolidation.algorithms.episodic_dbscan~~ (DEPRECATED), consolidation.algorithms.episodic_hdbscan, consolidation.algorithms.composite_distance, consolidation.algorithms.centroid_calculator, consolidation.algorithms.eps_adjuster, consolidation.algorithms.min_samples_adjuster, consolidation.algorithms.cluster_quality, pipelines.p03.phases.r2_episodic_integrator |
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
| 1 | k0/pipelines/p03/phases/r2_episodic_integrator.py | 1573 | MOD | 2026-01-25 | R2 phase wrapper: orchestrates episodic clustering -- splits events, runs HDBSCAN, computes centroids, matches existing episodes, updates event states, tracks quality metrics, triggers adaptive learning |
| 2 | k0/modules/consolidation/algorithms/episode_splitter.py | 367 | LEGACY | 2026-01-02 | Pre-clustering sequence splitting by time gaps (30min default), geohash distance (4-char threshold), activity type changes, and hard duration limit (4h) |
| 3 | k0/modules/consolidation/algorithms/episodic_dbscan.py | 365 | **DEPRECATED** | 2026-01-08 | DEPRECATED -- DBSCAN clustering superseded by HDBSCAN (Section 19). Scheduled for removal. |
| 4 | k0/modules/consolidation/algorithms/episodic_hdbscan.py | 532 | LEGACY | 2026-01-08 | HDBSCAN clustering with soft noise rescue (outlier_score < threshold), mandatory dependency (no fallback) |
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
| 18 | tests/k0/pipelines/p03/test_r2_episodic_dbscan.py | 282 | **DEPRECATED** | 2026-01-02 | DEPRECATED -- Tests for EpisodicDBSCAN (scheduled for removal with episodic_dbscan.py) |
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
| consolidation.episodic_clusterer.v1.yaml | v1 | idempotent | true | bool | true | yes | HDBSCAN deterministic given same input order and fixed random state |
| p03_consolidation.v1.yaml | v1 | stages[2].stage_id | stage_20_episodic_cluster | str | N/A | yes | R2 stage ID in pipeline |

#### 1.3.2 Environment Variables

| Variable | Type | Default | Required | Used By | Purpose |
| -------- | ---- | ------- | -------- | ------- | ------- |
| K0_DB_URL | url | NONE | yes | k0/db/engine.py (shared) | PostgreSQL connection for st_epi episode queries and st_learned_weights reads |

> **Note**: R2 does not read any R2-specific environment variables. Database connectivity is inherited from shared K0 engine. Episode matching queries and adaptive parameter persistence use syscalls injected via P03RunnerContext.

#### 1.3.3 Feature Flags

| Flag Name | Source | Default | Scope | Controls | Rollback Behavior |
| --------- | ------ | ------- | ----- | -------- | ----------------- |
| use_hdbscan | R2Config | True | per-cycle | **DEPRECATED** -- Always True. HDBSCAN is mandatory; DBSCAN fallback removed (Section 19). Flag will be removed in cleanup. | N/A -- HDBSCAN is the sole algorithm |
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
| 1 | pipelines.p03.phases.r2_episodic_integrator | R2EpisodicIntegrator.run | (envelope: P03BatchEnvelope, ctx: P03RunnerContext) -> P03PhaseResult | P03PhaseResult | P03 runner (stage_20) | conditional | Idempotent if same batch produces same clusters (deterministic HDBSCAN with fixed seed) |
| 2 | pipelines.p03.phases.r2_episodic_integrator | R2EpisodicIntegrator.should_skip | (envelope: P03BatchEnvelope) -> bool | bool | R2EpisodicIntegrator.run | yes | Checks min_batch_size and embedding presence |
| 3 | pipelines.p03.phases.r2_episodic_integrator | create_r2_phase | (config: Optional[R2Config] = None) -> R2EpisodicIntegrator | R2EpisodicIntegrator | Factory consumer | yes | Factory function for R2 phase creation |
| 4 | consolidation.algorithms.episode_splitter | EpisodeSplitter.split | (events: Sequence[SplittableEvent]) -> SplitResult | SplitResult | R2EpisodicIntegrator._split_events | yes | Pre-splits events into episodes by boundary detection |
| 5 | consolidation.algorithms.episode_splitter | EpisodeSplitter.split_long_sequences | (events: Sequence[SplittableEvent]) -> List[List[SplittableEvent]] | list | Convenience caller | yes | Simplified interface returning just episodes list |
| 6 | consolidation.algorithms.episodic_dbscan | EpisodicDBSCAN.cluster | (events: Sequence[ClusterableEvent]) -> ClusteringResult | ClusteringResult | **DEPRECATED** -- no callers (HDBSCAN is sole algorithm) | yes | DEPRECATED -- DBSCAN with precomputed composite distance matrix |
| 7 | consolidation.algorithms.episodic_dbscan | EpisodicDBSCAN.cluster_and_update_events | (events: List[Any]) -> ClusteringResult | ClusteringResult | **DEPRECATED** -- no callers | no | DEPRECATED -- Mutates event objects (sets cluster_id, label, is_noise) |
| 8 | consolidation.algorithms.episodic_hdbscan | EpisodicHDBSCAN.cluster | (events: Sequence[ClusterableEvent]) -> HDBSCANClusteringResult | HDBSCANClusteringResult | R2EpisodicIntegrator (sole clustering algorithm) | yes | HDBSCAN with noise rescue and soft membership probabilities |
| 9 | consolidation.algorithms.composite_distance | CompositeDistance.compute | (event_a: EventLike, event_b: EventLike) -> float | float | EpisodicHDBSCAN (indirect) | yes | Pairwise composite distance between two events |
| 10 | consolidation.algorithms.composite_distance | CompositeDistance.build_distance_matrix | (events: Sequence[EventLike]) -> np.ndarray | np.ndarray (n x n) | EpisodicHDBSCAN.cluster | yes | Builds full pairwise distance matrix for HDBSCAN |
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
| 1 | r2_episodic_integrator | _initialize_components | (ctx: P03RunnerContext) -> None | R2EpisodicIntegrator.run | Creates EpisodeSplitter, HDBSCAN clusterer, CentroidCalculator, QualityTracker, EpsAdjuster, MinSamplesAdjuster | Breaks all R2 clustering if component wiring changes |
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
| 3 | r2_episodic_integrator | EventAdapter | dataclass | event: P03EventState | event_id, timestamp, embedding_768, geohash, geohash_6, ner_entities, importance_score, activity_type, activity_type_ultrabert, narrative_thread_id, social_context, social_intimacy, participants_json, affect_valence, affect_arousal, affect_dominance, sentiment_score, salience_score, temporal_orientation, temporal_resolved_epoch_ms, temporal_anchor_json, narrative_arc_position, and 10+ more (20+ properties total -- GAP-002 expanded) | R2EpisodicIntegrator.run |
| 4 | episode_splitter | SplitConfig | dataclass(frozen) | max_episode_hours: float=4.0, time_gap_minutes: float=30.0, geohash_distance_threshold: int=4 | validate(), to_dict(), from_dict(), max_episode_ms, time_gap_ms (properties) | EpisodeSplitter |
| 5 | episode_splitter | EpisodeSplitter | (none) | config: SplitConfig | split(), split_long_sequences(), get_split_stats() | R2EpisodicIntegrator |
| 6 | episode_splitter | SplitResult | dataclass | episodes: List[List], split_count: int, split_reasons: Dict[str,int], total_events: int | episode_count (property) | EpisodeSplitter.split return |
| 7 | composite_distance | DBSCANParams | dataclass(frozen) | eps: float=0.15, min_samples: int=2, temporal_weight: float=0.3, max_temporal_gap_hours: float=4.0 | validate(), to_dict(), from_dict(), semantic_weight, max_temporal_gap_ms (properties) | CompositeDistance, EpisodicHDBSCAN (EpisodicDBSCAN DEPRECATED) |
| 8 | composite_distance | CompositeDistance | (none) | params: DBSCANParams | compute(), compute_from_arrays(), build_distance_matrix(), get_semantic_distance(), get_temporal_distance(), would_cluster() | EpisodicHDBSCAN (EpisodicDBSCAN DEPRECATED) |
| 9 | episodic_dbscan | ~~EpisodicDBSCAN~~ | (none) | params: DBSCANParams, distance_calculator: CompositeDistance | cluster(), cluster_and_update_events(), get_cluster_stats() | **DEPRECATED** -- no active callers |
| 10 | episodic_dbscan | ~~ClusteringResult~~ | dataclass | clusters: List[EpisodeCluster], total_events: int, cluster_count: int, noise_count: int, labels: List[int] | singleton_rate (property) | **DEPRECATED** -- EpisodicDBSCAN.cluster return |
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

> **Cross-reference**: Section 17 contains the authoritative deep-trace analysis of CompositeDistance
> (expanded 6-dimensional formula, logarithmic temporal decay, context-adaptive weights).
> Section 20 contains the authoritative HDBSCAN deep trace. This section documents the current
> implementation state; the deep traces document the target design.

### 3.1 Algorithm Catalog

| # | Algorithm | File | Scientific Basis | Input | Output | Complexity | Parameters |
| - | --------- | ---- | ---------------- | ----- | ------ | ---------- | ---------- |
| 1 | EpisodeSplitter | episode_splitter.py | Event segmentation theory (Zacks & Swallow 2007): people segment experience into discrete events at prediction error boundaries | Sequence[SplittableEvent] (sorted by timestamp) | SplitResult (list of episode sequences + split metadata) | O(n) linear scan | max_episode_hours=4.0, time_gap_minutes=30.0, geohash_distance_threshold=4 |
| 2 | CompositeDistance | composite_distance.py | Temporal binding in episodic memory (Tulving 2002): events occurring close in time are more likely same episode | (EventLike, EventLike) or Sequence[EventLike] | float distance or n x n distance matrix | O(d) per pair, O(n^2 * d) for matrix where d=768 | eps=0.15, temporal_weight=0.3, max_temporal_gap_hours=4.0 |
| 3 | ~~EpisodicDBSCAN~~ | episodic_dbscan.py | **DEPRECATED** -- DBSCAN (Ester et al. 1996) superseded by HDBSCAN. Scheduled for removal (Section 19). | -- | -- | -- | -- |
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
    +-- [2b] EpisodicHDBSCAN.cluster()
    |         -- HDBSCAN: auto eps, soft membership, noise rescue
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
| 5 | P03EventState.geohash_6 | P02 location resolution | Optional[str] | no | None -- **ACTIVE**: EventAdapter.geohash_6 passes through to EpisodeSplitter (GAP-002 fix) |
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
| 1 | numpy | >=1.24 | Array operations for embeddings, distance matrices, centroids | composite_distance.py, episodic_hdbscan.py, centroid_calculator.py, r2_episodic_integrator.py | BSD-3-Clause |
| 2 | scikit-learn | >=1.3 | sklearn.metrics.pairwise_distances, silhouette_score | composite_distance.py, cluster_quality.py | BSD-3-Clause |
| 3 | hdbscan | >=0.8.33 | hdbscan.HDBSCAN with precomputed metric, soft membership, outlier scores | episodic_hdbscan.py | BSD-3-Clause |

> **Note**: hdbscan is a **mandatory** dependency. DBSCAN fallback has been removed (Section 19). The hdbscan package must be pinned in requirements.txt and included in Docker images.

### 9.2 Internal Dependencies

| # | Module | Depends On | Dependency Type |
| - | ------ | ---------- | --------------- |
| 1 | r2_episodic_integrator.py | episode_splitter, episodic_hdbscan, composite_distance, centroid_calculator, eps_adjuster, min_samples_adjuster, cluster_quality | Algorithm imports (7 active R2 algorithms; episodic_dbscan DEPRECATED) |
| 2 | r2_episodic_integrator.py | event_state.ReconciliationAction | Enum for episode matching |
| 3 | r2_episodic_integrator.py | observability.P03Error | Error creation |
| 4 | r2_episodic_integrator.py | phase_interface.P03PhaseResult | Phase result protocol |
| 5 | r2_episodic_integrator.py | phase_outputs.EpisodeCluster | Output dataclass |
| 6 | r2_episodic_integrator.py | runner_contract.P03PhaseId | Phase ID enum |
| 7 | r2_episodic_integrator.py | observation_context.ObservationContext | Member context for Issue 7.6 |
| 8 | ~~episodic_dbscan.py~~ | ~~composite_distance.CompositeDistance, DBSCANParams~~ | **DEPRECATED** -- scheduled for removal |
| 9 | ~~episodic_dbscan.py~~ | ~~phase_outputs.EpisodeCluster~~ | **DEPRECATED** -- scheduled for removal |
| 10 | episodic_hdbscan.py | composite_distance.CompositeDistance, DBSCANParams | Distance computation |
| 11 | episodic_hdbscan.py | phase_outputs.EpisodeCluster | Cluster output dataclass |
| 12 | centroid_calculator.py | (none) | Standalone -- no K0 imports (only numpy) |
| 13 | episode_splitter.py | (none) | Standalone -- no K0 imports |
| 14 | eps_adjuster.py | (none) | Standalone -- no K0 imports |
| 15 | min_samples_adjuster.py | (none) | Standalone -- no K0 imports |
| 16 | cluster_quality.py | (none) | Standalone -- no K0 imports |

### 9.3 Dependency Notes

- **6 of 7 active algorithm files are standalone** (no K0 internal imports): episode_splitter, centroid_calculator, eps_adjuster, min_samples_adjuster, cluster_quality, composite_distance. This makes them highly testable.
- **1 active algorithm file** (episodic_hdbscan) imports from composite_distance and phase_outputs, creating a shallow dependency chain. (episodic_dbscan is DEPRECATED and scheduled for removal.)
- **The phase wrapper** (r2_episodic_integrator.py) is the heaviest dependency node, importing all 7 active algorithms plus 6 P03 infrastructure modules.

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

> **Cross-reference**: All gaps identified in this section are fully analyzed with neuroscience-grounded
> designs in Sections 16-24 (deep traces). The consolidated enhancement roadmap in Section 13.1
> provides the prioritized implementation plan. This section preserves the raw gap inventory for
> traceability.

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
| 5 | spatial resolution (full) | P03EventState.location_geohash | **RESOLVED** -- EventAdapter.geohash returns `self.event.geohash_6 or None` | ~~EventAdapter hardcodes geohash=None~~ FIXED: location splitting is ACTIVE (GAP-002) |
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
| 6 | R2-ISSUE-006 | ~~EventAdapter.geohash hardcoded to return None~~ | **RESOLVED** (GAP-002): EventAdapter now exposes `geohash_6`, `activity_type`, and 20+ MW v2 properties. All 4 split signals are LIVE. | ~~HIGH~~ CLOSED |
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

> **Note**: The preliminary epics (5.3A-5.3F) documented in the initial discovery pass have been
> superseded by the deep-trace analysis in Sections 16-24. Those sections contain the authoritative,
> neuroscience-grounded design with exact formulas, weight tables, and implementation specs.
> This section now serves as the consolidated enhancement index.

### 13.1 Prioritized Enhancement Roadmap

| Priority | Enhancement | Source Section | Effort | Blocking? |
| -------- | ----------- | -------------- | ------ | --------- |
| ~~P0~~ **DONE** | ~~Fix EventAdapter signal blockade~~ **RESOLVED** (GAP-002): EventAdapter now exposes 20+ properties including geohash_6, activity_type, activity_type_ultrabert, all MW v2 signals | Section 18.4, 20.2 | COMPLETE | ~~Yes -- unblocks ALL enhancements below~~ Unblocked |
| ~~P0~~ **MITIGATED** | ~~Fix timestamp chain~~ **MITIGATED** (GAP-002): R0 now uses `conversation_anchor_ms` as gold standard temporal signal. Chain: conversation_anchor_ms -> event_time_utc -> created_at -> now(). Priority 3+ fallback is no longer the most common path. | Section 16.2 | PARTIALLY COMPLETE | Severity reduced -- conversation_anchor_ms covers most cases |
| **P1** | DBSCAN full removal (829 lines of dead code) | Section 19 | LOW (2 days) | No -- cleanup, reduces maintenance burden |
| **P1** | Fix fake silhouette (avg cohesion != silhouette; entire adaptive loop is dead) | Section 24.4 | LOW (1 day) | Yes -- adaptive learning is broken without this |
| **P1** | Contract reconciliation (8 divergences, undeclared capabilities) | Section 11.1, 12.2 | LOW (1 day) | Yes -- capability audit compliance |
| **P2** | 6-dimensional CompositeDistance (semantic, log-temporal, spatial, social, affective, narrative) | Section 17.6, 20.7 | MEDIUM (5-7 days) | No |
| **P2** | Logarithmic temporal distance (replace linear normalization with exponential/log decay) | Section 17.4.2 | LOW (1 day) | No -- can ship independently |
| **P2** | Boundary strength scoring for EpisodeSplitter (replace 4-signal priority cascade with weighted multi-signal scoring) | Section 18.8 | MEDIUM (3-5 days) | Depends on P0 EventAdapter fix |
| **P2** | HDBSCAN noise rescue calibration (extract magic numbers, context-aware rescue) | Section 20.8 | MEDIUM (3-4 days) | No |
| **P2** | Phase wrapper decomposition (extract episode_builder, episode_matcher, episode_metrics) | Section 11.3 R2-ISSUE-008 | MEDIUM (3-4 days) | No |
| **P3** | Salience-composite centroid weighting (use MW v2 salience, arousal, elaboration_depth) | Section 21.8 | MEDIUM (3-4 days) | Depends on P0 EventAdapter fix |
| **P3** | Multi-centroid episode representation (primary, start, end, emotional peak, narrative) | Section 21.9 | MEDIUM (4-5 days) | No |
| **P3** | HDBSCAN probability-augmented centroid weighting | Section 21.10 | LOW (1-2 days) | No |
| **P3** | EpisodicCoherenceScore (replace phantom grounding/correction signals with MW v2 coherence metrics) | Section 24.5 | MEDIUM (2-3 days) | Depends on P0 EventAdapter fix |
| **P3** | Vectorized distance matrix (scipy.cdist + numpy broadcasting, 50-100x speedup) | Section 17.4.3, 20.9 | LOW (1-2 days) | No |
| **P4** | Hebbian distance boost (wire st_cooccurrence into distance computation) | Section 11.1 R2-DIV-003 | MEDIUM (3-4 days) | Depends on R1 HebbianLearner enabled |
| **P4** | Context-adaptive weights (dynamic weight modulation based on novelty/routine) | Section 17.5.5 | MEDIUM (3-4 days) | Depends on P2 6D distance |

### 13.2 Critical Dependency Chain

```
~~P0: EventAdapter fix + Timestamp fix~~ RESOLVED (GAP-002)
         |
         v
P1: DBSCAN removal + Fake silhouette fix + Contract reconciliation
         |
         v
P2: 6D CompositeDistance + Log-temporal + Boundary scoring + Noise rescue calibration
         |
         v
P3: Salience weighting + Multi-centroid + Coherence score + Vectorized matrix
         |
         v
P4: Hebbian boost + Context-adaptive weights
```

### 13.3 Cross-Reference to Deep Trace Sections

| Old Epic | Superseded By | Key Differences |
| -------- | ------------- | --------------- |
| 5.3A Multi-Dimensional Distance | Section 17 (CompositeDistance) + Section 20.7 (6D formula) | Expanded from 4D to 6D; added affective and narrative dimensions; neuroscience-grounded weights |
| 5.3B EventAdapter Signal Activation | Section 18.4 (EventAdapter Blockade) + Section 20.2 (Signal Funnel) | **RESOLVED** (GAP-002): EventAdapter now exposes 20+ properties. Signal funnel bottleneck moved from EventAdapter to CompositeDistance (2D -> need 6D upgrade) |
| 5.3C HDBSCAN Noise Rescue | Section 20.8 (Context-Aware Rescue) | Upgraded from config extraction to multi-signal rescue scoring |
| 5.3D Contract Reconciliation | Section 11.1 (unchanged, still valid) | Same scope |
| 5.3E Phase Wrapper Decomposition | Section 11.3 R2-ISSUE-008 (unchanged, still valid) | Same scope |
| 5.3F Hebbian Distance Boost | Section 11.1 R2-DIV-003 (unchanged, still valid) | Same scope; blocked by R1 HebbianLearner |

---

## 14. Risk Register

| # | Risk | Probability | Impact | Mitigation |
| - | ---- | ----------- | ------ | ---------- |
| 1 | HDBSCAN library not available in production | LOW | Hard failure -- HDBSCAN is mandatory (no DBSCAN fallback) | Pin hdbscan in requirements.txt and Docker images; add import health check at startup |
| 2 | Distance matrix OOM for large batches | LOW | Crash on batches > 5000 events | EpisodeSplitter pre-splits; add max_sequence_size guard |
| 3 | Episode matching false positives at 0.85 threshold | MEDIUM | Wrong events get REINFORCE action, corrupting existing episodes | Monitor match rates; tune threshold per space |
| 4 | Fake silhouette renders adaptive learning dead | HIGH | EpsAdjuster and MinSamplesAdjuster never fire; eps stays at default forever | Fix: compute real silhouette with sklearn using precomputed distance matrix (Section 24.4) |
| 5 | No tests for HDBSCAN code path | HIGH | HDBSCAN regressions go undetected (653 lines untested) | Write comprehensive HDBSCAN test suite (Section 20) |
| 6 | PII in episode titles and summaries | MEDIUM | Privacy violation if episodes are exposed to logs or APIs | Add PII redaction to _generate_episode_title/_generate_episode_summary |
| 7 | Undeclared capabilities (read:st_epi, write:st_learned_weights) | MEDIUM | Capability audit fails; security boundary violation | Update contract (Section 11.1) |
| 8 | ~~EventAdapter blocks 34+ MW v2 signals~~ | ~~HIGH~~ **RESOLVED** | **RESOLVED** (GAP-002): EventAdapter now exposes 20+ properties. All 4 split signals are LIVE. HDBSCAN still clusters on 2D (CompositeDistance not yet upgraded to 6D). | ~~Fix EventAdapter~~ DONE. Remaining: upgrade CompositeDistance to 6D (Section 17.6, 20.7) |
| 9 | ~~Timestamp fallback = wrong time for most events~~ | ~~HIGH~~ **MITIGATED** | **MITIGATED** (GAP-002): R0 now uses `conversation_anchor_ms` as gold standard. Priority 3+ fallback is no longer the dominant path. Residual risk: events without conversation_anchor_ms still fall to Priority 3. | conversation_anchor_ms covers most cases. Residual: enhance M08 NER for edge cases |

---

## 15. Open Questions

| # | Question | Context | Blocking? | Resolution |
| - | -------- | ------- | --------- | ---------- |
| 1 | ~~Should HDBSCAN be mandatory or optional?~~ | ~~Currently optional (try/except import) with DBSCAN fallback~~ | RESOLVED | **MANDATORY.** DBSCAN is deprecated and will be removed (Section 19). hdbscan becomes a hard dependency in requirements.txt and Docker images. No fallback. |
| 2 | Is episode_reinforce_threshold=0.85 correct for UltraBERT? | Cosine similarity 0.85 is very high; may miss legitimate reinforcements | No | Test empirically; consider 0.75-0.80 range |
| 3 | Should canonicalization be re-enabled? | Currently disabled (enable_canonicalization=False); HDBSCAN clusters are already good | No | Keep disabled until evidence of duplicate episodes |
| 4 | ~~How should co-occurrence boost interact with HDBSCAN?~~ | ~~Contract says boost, HDBSCAN has its own noise rescue~~ | RESOLVED | Apply boost to distance matrix BEFORE HDBSCAN clustering, not after. Boost modifies pairwise distances so HDBSCAN hierarchy naturally incorporates co-occurrence. Blocked by R1 HebbianLearner. |
| 5 | Is cold_start_threshold=100 clusters too high? | New spaces with < 100 total clusters don't benefit from adaptive learning | No | Consider lowering to 30-50 for faster adaptation. Note: adaptive learning is currently dead due to fake silhouette (Section 24.4) -- fix silhouette first |
| 6 | Should R2 emit events to external bus? | Currently only populates envelope (internal); no bus event emission | No | Keep internal for now; add bus emission in M6 when K1 subscribes |
| 7 | Should noise events (is_noise=True) skip R3 entirely? | Currently passed through to R3; dedup/decay may process noise unnecessarily | No | Add skip condition in R3 for noise events |
| 8 | Should _compute_confidence and _compute_ambiguity_score use learned weights? | Currently use hardcoded formulas | No | Consider adaptive confidence in M6 with feedback loop |

---

## 16. Timestamp Chain Analysis (K1 -> Bridge -> K0 -> P02 -> P03 R2)

**Date**: 2026-03-03
**Status**: CONFIRMED -- 3 structural problems identified via end-to-end code trace

### 16.1 Full Chain Trace

```text
K1 MW Stage 4             Bridge                 K0 P02 M08                st_hipp_events          P03 R0                    R2
-------------             ------                 ----------                --------------          ------                    --
body.event_time=now()     ts=now()               normalize_timestamp()     event_time_utc (INT)    row["event_time_utc"]     EventAdapter.timestamp
body.temporal.            idem_key, sig          Priority 1-5 chain        created_at (INT)        or row["created_at"]      -> EpisodeSplitter
  resolved_epoch_ms                                                                                or 0                      -> CompositeDistance
body.temporal.                                                                                                               -> Episode matching
  mentioned_time                                                             -> P03EventState.timestamp (ms)
```

**M08 `normalize_timestamp()`** (`k0/modules/context/temporal_profile.py:432`) implements the 5-level fallback:

| Priority | Source | Provenance Tag | Fidelity |
| -------- | ------ | -------------- | -------- |
| 0 | `conversation_anchor_ms` (GAP-002) | `conversation_anchor` | **Highest** -- K1 conversation turn timestamp, gold standard (GAP-002 addition) |
| 1 | `body.temporal.resolved_epoch_ms` | `mw_resolved` | High -- K1 LLM resolved "yesterday evening" to epoch |
| 2 | M02 NER temporal + regex resolution | `ner_temporal` | Medium -- regex resolves "yesterday", "last week" etc. |
| 3 | `body.event_time` | `event_time` | Low -- MW sets to `now_utc()` at processing time |
| 4 | `envelope.ts` | `envelope_ts` | Low -- Bridge build time |
| 5 | `now()` | `now` | Lowest -- P02 processing time |

**R0 `_row_to_event_state()`** (`k0/pipelines/p03/phases/r0_batch_selector.py:666`):

```python
# GAP-002 UPDATE: R0 now uses conversation_anchor_ms as gold standard temporal signal.
# Timestamp chain: conversation_anchor_ms -> event_time_utc -> created_at -> now()
event_time_seconds = row.get("conversation_anchor_ms") or row.get("event_time_utc") or row.get("created_at") or 0
```

Falls back through the chain if higher-priority sources are falsy (0, None, or missing).

**R2 uses `P03EventState.timestamp`** in ALL temporal decisions:

- `EpisodeSplitter._detect_break()` -- 30min time gap split (`k0/modules/consolidation/algorithms/episode_splitter.py:367`)
- `CompositeDistance.compute()` -- temporal normalization = `abs(ts_a - ts_b) / max_temporal_gap_ms` (`k0/modules/consolidation/algorithms/composite_distance.py:220`)
- Episode matching -- 7-day lookback window (`r2_episodic_integrator.py:356-357`)

### 16.2 Problem 1: Priority 3+ Fallback = Wrong Time (CRITICAL)

When MW v2 does NOT send `resolved_epoch_ms` AND text has no detectable temporal expression that NER regex can catch, M08 falls to Priority 3: `body.event_time = now_utc()` -- the MW processing time, NOT the actual event time.

**Scenario A (silent past event)**: User says "Had a great dinner with Mom" at 10am (no temporal marker like "yesterday"). MW sets `body.event_time = 10am today`. M08 cannot resolve it better. `event_time_utc = 10am today`. R2 clusters this with today's morning events instead of yesterday's dinner episode.

**Scenario B (offline queue drain)**: K0 is offline. K1 sends 50 events over 6 hours, queued in Bridge LocalOutbox (SQLite, max 10K depth). K0 comes back. All 50 events arrive within seconds. If `event_time_utc` ends up null/0 in DB (M08 failure, legacy data, migration gap), R0 falls back to `created_at` = K0 receipt time. All 50 events appear to happen at the SAME MOMENT. R2 over-clusters everything into one mega-episode because time gaps disappear.

**Scenario C (batch aggregation)**: MW-08 specifies 250ms batch aggregation window. Multiple events batched together get identical or near-identical `body.event_time` values. Even if the user discussed events spanning hours, they all look temporally co-located.

**Impact on R2**:

- `EpisodeSplitter`: 30min gap check sees no gap between events that actually happened hours apart -> no split -> single mega-episode
- `CompositeDistance`: `normalized_time_distance` is near 0 for events that should be temporally distant -> artificially low composite distance -> DBSCAN clusters unrelated events
- Episode matching: 7-day lookback is correct IF timestamp is correct; with wrong timestamps, matching against st_epi returns wrong "best match" episodes

**Root cause**: ~~Priority 3 (`body.event_time = now_utc()`) is the MOST COMMON path today.~~ **UPDATE (GAP-002)**: `conversation_anchor_ms` (Priority 0) is now the gold standard and covers the majority of events. Priority 3+ fallback is no longer the dominant path. Residual risk: events without `conversation_anchor_ms` and without detectable temporal markers still fall to Priority 3.

### 16.3 Problem 2: EventAdapter.geohash Hardcoded to None ~~(MEDIUM)~~ **(RESOLVED)**

~~`r2_episodic_integrator.py:155`:~~

```python
# BEFORE (GAP-002 fix):
# @property
# def geohash(self) -> Optional[str]:
#     return None
#
# AFTER (current code):
@property
def geohash(self) -> Optional[str]:
    return self.event.geohash_6 or None
```

~~But `P03EventState.geohash_6` IS populated from `st_hipp_events` by R0 (line 701). The `EventAdapter` wrapper just doesn't pass it through.~~

**RESOLVED**: EventAdapter now returns `self.event.geohash_6 or None`. Also exposes `geohash_6` as a separate property. Location-based splitting is ACTIVE.

~~`EpisodeSplitter._detect_break()` checks geohash for Signal 1 (location change, highest priority split signal) but always receives `None` from both events -> `if prev_geohash and curr_geohash:` is always False -> **location-based splitting is completely disabled**.~~

**RESOLVED**: All 4 split signals are now LIVE. Location-based splitting triggers when geohash_6 values differ.

~~**Impact**: Dinner at Olive Garden and workout at the gym cluster together if they occur within 30 minutes of each other. Location is the strongest episode boundary signal in human episodic memory (Zacks & Swallow, 2007), yet it contributes zero signal to R2.~~

**RESOLVED**: Different geohash values now correctly trigger episode splits.

~~**Fix**: One-line change: `return self.event.geohash_6 or None`~~

**COMPLETE**: Fix applied in GAP-002.

### 16.4 Problem 3: CompositeDistance Uses Only 2 Dimensions (LOW)

Current formula:

```text
distance = 0.7 * cosine_distance(emb_a, emb_b) + 0.3 * normalized_time_distance(ts_a, ts_b)
```

No location component, no activity type, no social context. Combined with Problem 2, there is ZERO spatial signal in the R2 clustering distance metric.

The composite distance was designed for the minimal R2 (M4 scope). With MW v2 signals now available (location, social, narrative, activity), the formula can be extended (tracked as Epic 5.3A in this document).

### 16.5 Correctness Matrix

| Scenario | Timestamp Used | Source | Correct? |
| -------- | -------------- | ------ | -------- |
| MW v2 sends `resolved_epoch_ms` ("yesterday evening" -> epoch) | K1-resolved epoch | `mw_resolved` | YES |
| Text has "yesterday", "last week" (NER regex matches) | Regex-resolved epoch | `ner_temporal` | MOSTLY (heuristic, coarse resolution) |
| Real-time chat, no temporal markers | `body.event_time` ~ when user spoke | `event_time` | ACCEPTABLE (order preserved) |
| Offline queue, `event_time_utc` preserved in DB | MW original `now_utc()` | `event_time` | ACCEPTABLE (per-event order correct, but gaps lost) |
| `event_time_utc` null/0 in DB -> fallback to `created_at` | K0 receipt time | `created_at` | ~~BROKEN~~ **MITIGATED** -- conversation_anchor_ms (Priority 0) resolves this when populated; offline events without it still collapse |
| Past event without temporal words ("Had dinner with Mom") | `body.event_time = now()` | `event_time` | ~~BROKEN~~ **MITIGATED** -- conversation_anchor_ms provides conversational time anchor; past-reference events still need MW resolved_epoch_ms |
| Batch drain: 50 events arrive within seconds | `created_at` ~ same second | `created_at` | ~~BROKEN~~ **MITIGATED** -- conversation_anchor_ms preserves per-conversation ordering; batch drain within single conversation still compresses |

### 16.6 Fix Surface

| # | Problem | Severity | Fix | Scope |
| - | ------- | -------- | --- | ----- |
| 1 | Priority 3+ fallback = wrong time | CRITICAL | Ensure MW v2 ALWAYS populates `resolved_epoch_ms` (K1 side) OR enhance M08 NER regex temporal pattern coverage (K0 side) OR add conversational-time heuristic to M08 (e.g., infer "this happened around the time user said it" with confidence tag) | K1 MW + K0 M08 |
| 2 | ~~EventAdapter.geohash hardcoded None~~ | ~~MEDIUM~~ **RESOLVED** | ~~Change `return None` to `return self.event.geohash_6 or None`~~ **DONE** (GAP-002 exposed geohash_6 + 20 properties via EventAdapter) | ~~1-line fix~~ **DONE** |
| 3 | CompositeDistance only 2 dimensions | LOW | Extend formula with location, activity, social signals (Epic 5.3A) | R2 algorithm redesign |

### 16.7 Relationship to Existing Issues

| Problem | Existing Issue | Notes |
| ------- | -------------- | ----- |
| Problem 1 (timestamp fallback) | NEW -- not previously documented | Root cause of "episodes get screwed up" user report |
| Problem 2 (geohash None) | R2-ISSUE-006 (Section 10) | ~~Already identified as "EventAdapter.geohash hardcodes None"~~ **RESOLVED** (GAP-002) |
| Problem 3 (2D distance) | R2-ISSUE-001 (Section 10), Epic 5.3A (Section 13) | Already tracked as enhancement |

---

## 17. Algorithm Inventory & Deep Trace: CompositeDistance

**Date**: 2026-03-03
**Status**: COMPLETE -- Full end-to-end trace of core distance metric
**Scope**: Catalog all 8 R2 algorithms, deep-trace CompositeDistance

### 17.1 Complete R2 Algorithm Inventory

R2 imports 8 algorithm modules from `k0/modules/consolidation/algorithms/`:

| # | Algorithm | File | Lines | Role in R2 | Depends On | Test Count |
| - | --------- | ---- | ----- | ---------- | ---------- | ---------- |
| 1 | **EpisodeSplitter** | episode_splitter.py | 463 | Pre-clustering segmentation: splits long sequences at time gaps (30min), location changes, activity changes, hard limit (4h) | None (standalone) | 30 |
| 2 | **CompositeDistance** | composite_distance.py | 461 | Core distance metric: `d = 0.7*cosine + 0.3*temporal`. Builds NxN precomputed distance matrix for HDBSCAN | numpy | 21 |
| 3 | **EpisodicDBSCAN** | episodic_dbscan.py | 460 | Legacy density clustering via sklearn DBSCAN on precomputed distance matrix. Fixed eps. | CompositeDistance, sklearn | 13 |
| 4 | **EpisodicHDBSCAN** | episodic_hdbscan.py | 653 | Hierarchical density clustering with soft membership, outlier scores, noise rescue. Falls back to DBSCAN if hdbscan lib missing. | CompositeDistance, hdbscan/sklearn | **0** |
| 5 | **CentroidCalculator** | centroid_calculator.py | 614 | Computes importance-weighted 768-dim centroids per cluster. 4 strategies: uniform, importance, recency, hybrid (0.7*importance + 0.3*recency). L2-normalizes output. | numpy | 22 |
| 6 | **EpsAdjuster** | eps_adjuster.py | 406 | Adaptive eps learning: if silhouette < 0.5, adjusts eps +/-0.02 based on cluster size and singleton rate. Momentum smoothing (0.9). Bounds [0.15, 0.40]. Cold start at 100 clusters. | None (standalone) | 15 |
| 7 | **MinSamplesAdjuster** | min_samples_adjuster.py | 369 | Adaptive min_samples: singleton_rate > 20% = increase, < 5% = decrease. Bounds [2, 5]. | None (standalone) | 11 |
| 8 | **ClusterQualityTracker** | cluster_quality.py | 522 | Closed-loop quality: `Q = 0.40*silhouette + 0.30*grounding + 0.20*(1-correction) + 0.10*(1-singleton)`. Persists to st_consolidation_audit. | sklearn (silhouette_score) | 20 |

**Total**: 3948 lines of algorithm code, 132 tests

**Execution order in R2**:

```text
EpisodeSplitter.split() -> [sequences]
  for each sequence:
    CompositeDistance.build_distance_matrix() -> NxN matrix
    EpisodicDBSCAN.cluster() or EpisodicHDBSCAN.cluster() -> ClusteringResult
  for each cluster:
    CentroidCalculator.compute() -> CentroidResult (768-dim centroid)
  ClusterQualityTracker.compute_metrics() -> quality score
  EpsAdjuster.adjust() -> new eps
  MinSamplesAdjuster.adjust() -> new min_samples
```

### 17.2 Deep Trace Target: CompositeDistance

**Why this algorithm**: CompositeDistance is the mathematical heart of R2. Every clustering decision (DBSCAN/HDBSCAN) consumes its output. A flaw here propagates to every episode formed. It is also the algorithm most affected by the timestamp problem (Section 16) and the one with the most room for MW v2 signal integration.

### 17.3 CompositeDistance: Formula Analysis

**Current formula** (composite_distance.py:200-243):

$$d(a, b) = (1 - w_t) \cdot d_{cos}(a, b) + w_t \cdot d_{time}(a, b)$$

Where:

- $w_t = 0.3$ (temporal_weight, configurable)
- $d_{cos}(a, b) = 1 - \cos(\vec{e}_a, \vec{e}_b)$ (cosine distance of 768-dim embeddings)
- $d_{time}(a, b) = \min\left(1.0, \frac{|ts_a - ts_b|}{T_{max}}\right)$ (normalized temporal distance)
- $T_{max} = 4 \text{ hours} = 14{,}400{,}000 \text{ ms}$ (hard cutoff: events > 4h apart = infinity)

**Distance range**: $[0.0, \infty)$ where $\infty$ = events cannot cluster (temporal hard limit exceeded)

**Key implementation details**:

- If $|ts_a - ts_b| > T_{max}$: returns `float("inf")` immediately (line 220-221)
- Cosine distance handles zero vectors: returns 1.0 (orthogonal, line 326)
- Cosine similarity clamped to $[-1, 1]$ to handle float precision (line 329)
- `build_distance_matrix()` is $O(n^2 \cdot d)$ where $n$ = events, $d$ = 768 (line 360-386)
- Matrix is symmetric: `distances[i,j] == distances[j,i]` (line 384-385)
- Pre-extracts embeddings to numpy arrays before loop (line 372-377)

### 17.4 Correctness Audit

#### 17.4.1 Mathematically Correct

| Check | Status | Notes |
| ----- | ------ | ----- |
| Cosine distance formula | CORRECT | $1 - \frac{\vec{a} \cdot \vec{b}}{|\vec{a}| \cdot |\vec{b}|}$ matches standard definition |
| Symmetry | CORRECT | Matrix built with `distances[i,j] = distances[j,i]` |
| Diagonal | CORRECT | Initialized to 0 via `np.zeros()`, never overwritten (loop starts at `j = i+1`) |
| Temporal normalization | CORRECT | Linear normalization $\in [0, 1]$ with hard cutoff at $T_{max}$ |
| Weight sum | CORRECT | $w_{sem} + w_{time} = (1 - w_t) + w_t = 1.0$ always |
| Float clamping | CORRECT | `max(-1.0, min(1.0, cosine_similarity))` prevents NaN from float errors |
| Zero vector handling | CORRECT | Returns 1.0 (treats as orthogonal) -- reasonable choice |

#### 17.4.2 Scientifically Problematic

**Problem 1: Linear temporal normalization ignores neuroscience of temporal binding**

The current formula uses LINEAR normalization:
$$d_{time} = \frac{|ts_a - ts_b|}{T_{max}}$$

Neuroscience says temporal binding follows an EXPONENTIAL decay (Howard & Kahana, 2002; Polyn et al., 2009). Events 5 minutes apart feel much more "same episode" than events 2 hours apart, but the difference between 3.5h and 4h barely matters. The current linear function treats these gaps as proportionally equivalent.

**Proposed** (**SUPERSEDED** — Neuromorphic Design Subsystem 3 Dim 2 uses log-temporal with confidence weighting + temporal_link binding): Exponential temporal kernel:
$$d_{time}^{exp} = 1 - \exp\left(-\frac{|ts_a - ts_b|}{\tau}\right)$$
where $\tau$ is a half-life parameter (e.g., 30 minutes = 1,800,000 ms). This makes near-events much closer (exponentially) while still saturating at 1.0 for distant events.

**Impact**: With linear normalization, two events 10 minutes apart get $d_{time} = 0.0042$ and two events 2 hours apart get $d_{time} = 0.5$. With exponential ($\tau = 30\text{min}$), the same events get $d_{time} = 0.283$ and $d_{time} = 0.982$. The exponential creates a sharper "same episode" vs "different episode" boundary that matches human memory formation.

**Problem 2: Only 2 dimensions -- ignores spatial, social, and activity signals**

Human episodic memory encodes events along AT LEAST 5 dimensions (Tulving, 2002; Conway, 2005; Rubin, 2006).
**NOTE**: The Neuromorphic Design (temp_r2_design.md, Subsystem 3) extends this to **6D** with full GAP-002 signal utilization:

| Dimension | Neuroscience Basis | Available Signal on P03EventState | Used in CompositeDistance? |
| --------- | ------------------ | --------------------------------- | ------------------------- |
| **Semantic** (what) | Hippocampal pattern completion | `embedding_768` (UltraBERT 768-dim) | YES (weight 0.7) |
| **Temporal** (when) | Medial temporal lobe time cells | `conversation_anchor_ms` (gold), `timestamp` (ms), `temporal_source`, `temporal_links_json` | YES (weight 0.3) |
| **Spatial** (where) | Place cells, grid cells | `place_id`, `geohash_6`, `location_name`, `location_type`, `location_hierarchy_json`, `spatial_context_json` | NO |
| **Social** (who) | Social cognition network | `participants_json`, `participant_relationships_json`, `num_participants`, `social_context`, `social_intimacy`, `is_solo_event` | NO |
| **Activity** (doing what) | Motor/action schemas | `activity_type_ultrabert` (12-type), `intent_ultrabert` (8-type), `activity_type` (7-type fallback) | NO |
| **Affective** (how it felt) | Amygdala-hippocampal modulation (McGaugh, 2004) | `affect_valence`, `affect_arousal`, `affect_dominance`, `emotions_json`, `surprise_level`, `salience_score`, `entity_salience_json` | NO |
| **Narrative** (why it matters) | Default mode network (Rubin, 2006) | `narrative_thread_id`, `narrative_arc_position`, `narrative_is_goal_event`, `goal_context`, `intent_type`, `temporal_orientation` | NO |

The embedding captures some semantic overlap with spatial/social/activity, but it cannot reliably distinguish "dinner at home with family" from "dinner at restaurant with colleagues" -- both produce similar semantic embeddings around "dinner" but are clearly different episodes due to location and social context.

**Problem 3: Fixed weights ignore context-dependent binding strength**

The weights (0.7 semantic, 0.3 temporal) are static. But temporal binding strength is context-dependent:

- **Routine events** (breakfast, commute): Temporal proximity matters most (same morning = same episode regardless of topic shifts)
- **Novel events** (wedding, accident): Semantic coherence matters most (wedding events cluster even if spread over a whole day)
- **Social events** (family dinner): Social context dominates (who you were with defines the episode more than what you discussed)

MW v2 provides `novelty` (ROUTINE/EXPECTED/NOVEL/SURPRISING), `elaboration_depth`, and `social_intimacy` that could dynamically adjust weights.

#### 17.4.3 Performance Audit

| Metric | Current | Assessment |
| ------ | ------- | ---------- |
| build_distance_matrix complexity | $O(n^2 \cdot 768)$ with Python loop | SLOW for large batches. For n=200 events: 19,900 distance computations. Each does 2 numpy ops. |
| Memory | $O(n^2)$ float32 matrix | For n=200: 160KB. For n=1000: 4MB. Acceptable. |
| Vectorization | None -- pure Python double loop (line 380-386) | Could be 50-100x faster with `scipy.spatial.distance.cdist` for cosine + vectorized temporal |
| Redundant array creation | `np.asarray()` called in pre-extraction loop AND inside `_cosine_distance()` | Pre-extraction (line 372-377) is efficient. `compute_from_arrays()` path avoids double conversion. |
| Infinity handling | Downstream clips to 1e10 (episodic_dbscan.py:220, episodic_hdbscan.py:290) | CORRECT but fragile -- magic number. Should be a named constant. |

**Vectorization opportunity**: The entire distance matrix can be computed ~100x faster:

```python
# Current: O(n^2) Python loop with per-pair numpy calls
for i in range(n):
    for j in range(i + 1, n):
        dist = self.compute_from_arrays(embeddings[i], embeddings[j], ...)

# Proposed: Vectorized with scipy + numpy broadcasting
from scipy.spatial.distance import cdist
cosine_matrix = cdist(embeddings_matrix, embeddings_matrix, metric='cosine')  # O(n^2*d) in C
temporal_matrix = np.abs(timestamps[:, None] - timestamps[None, :]) / max_gap_ms
temporal_matrix = np.clip(temporal_matrix, 0.0, 1.0)
distance_matrix = semantic_weight * cosine_matrix + temporal_weight * temporal_matrix
distance_matrix[temporal_matrix_raw > max_gap_ms] = np.inf
```

For n=200 events, this would reduce wall time from ~200ms to ~2ms.

### 17.5 MW v2 Signal Enhancement Opportunities

> **SUPERSEDED**: All proposals in 17.5.1-17.5.5 are replaced by the Neuromorphic Design (temp_r2_design.md, Subsystem 3: 6D distance function with tiered fallbacks, confidence gating, and source reliability modifiers). Retained here for historical context.

P03EventState carries 25+ MW v2 signals that CompositeDistance currently ignores. Here are the highest-impact enhancements:

#### 17.5.1 Spatial Distance Component (from `geohash_6`, `location_name`, `location_type`)

```text
d_spatial(a, b):
  if both have geohash_6:
    return geohash_prefix_distance(a.geohash_6, b.geohash_6) / 6  # [0, 1]
  if both have location_type and location_type matches:
    return 0.2  # Same type of place
  if both have location_name and location_name matches:
    return 0.0  # Same place
  return 0.5  # Unknown (neutral -- does not push apart)
```

**Prerequisite**: ~~Fix EventAdapter.geohash to return `self.event.geohash_6 or None` (Problem 2 in Section 16).~~ **PREREQUISITE MET** (GAP-002 exposed geohash_6 + 20 properties via EventAdapter).

**Weight**: 0.15 (taken from temporal, reducing it to 0.15). New formula: `d = 0.55*cosine + 0.15*temporal + 0.15*spatial + 0.15*social`

#### 17.5.2 Social Distance Component (from `participants_json`, `social_context`, `social_intimacy`)

```text
d_social(a, b):
  participants_a = set(json.loads(a.participants_json))
  participants_b = set(json.loads(b.participants_json))
  if participants_a and participants_b:
    jaccard = len(participants_a & participants_b) / len(participants_a | participants_b)
    return 1.0 - jaccard  # 0 = same people, 1 = totally different people
  if a.social_context == b.social_context and a.social_context:
    return 0.3  # Same social context (nuclear_family, work, etc.)
  return 0.5  # Unknown
```

**Neuroscience basis**: People remember episodes primarily by WHO was present (social brain hypothesis, Dunbar, 1998). "Family dinner" vs "work lunch" are distinct episodes even if both involve eating at the same time.

#### 17.5.3 Activity Distance Component (from `activity_type_ultrabert`)

```text
d_activity(a, b):
  if a.activity_type_ultrabert == b.activity_type_ultrabert and a.activity_type_ultrabert:
    return 0.0  # Same activity type
  # Activity similarity matrix (some types are closer than others)
  # e.g., DIARY and GRATITUDE are closer than DIARY and FINANCE
  return activity_similarity_matrix.get((a_type, b_type), 0.5)
```

**Source**: UltraBERT 12-type classification: DIARY/TASK/HEALTH/FINANCE/RELATIONSHIP/WORK/META/MEMORY/PLANNING/CELEBRATION/CONCERN/GRATITUDE

#### 17.5.4 Narrative Thread Distance (from MW v2 `narrative_thread_id`)

```text
d_narrative(a, b):
  if a.narrative_thread_id and b.narrative_thread_id:
    if a.narrative_thread_id == b.narrative_thread_id:
      return 0.0  # Same conversation thread -- strongly co-episodic
    return 0.8  # Different threads
  return 0.5  # Unknown
```

**This is the highest-fidelity signal**: MW v2 tracks which conversation thread produced each event. Events from the same K1 conversation thread are almost certainly the same episode. This alone would fix the "events submitted together but about different topics" problem.

#### 17.5.5 Context-Adaptive Weights (from MW v2 `novelty`, `elaboration_depth`)

Instead of fixed weights, dynamically adjust per-event-pair:

```text
adaptive_weights(a, b):
  # Base weights
  w_sem = 0.55, w_time = 0.15, w_spatial = 0.15, w_social = 0.15

  # If both events are ROUTINE, boost temporal weight (routines are time-defined)
  if a.novelty == "ROUTINE" and b.novelty == "ROUTINE":
    w_time += 0.10; w_sem -= 0.10

  # If either event is NOVEL/SURPRISING, boost semantic weight (content defines the episode)
  if a.novelty in ("NOVEL", "SURPRISING") or b.novelty in ("NOVEL", "SURPRISING"):
    w_sem += 0.10; w_time -= 0.05; w_spatial -= 0.05

  # If both have same narrative_thread_id, collapse weights toward 0 (same episode guaranteed)
  if a.narrative_thread_id == b.narrative_thread_id and a.narrative_thread_id:
    return 0.0  # Short-circuit: same thread = same episode

  return w_sem, w_time, w_spatial, w_social
```

### 17.6 Proposed Enhanced Formula (**SUPERSEDED** by Neuromorphic 6D Formula)

> **See**: temp_r2_design.md Subsystem 3 — 6D distance: semantic [0.25] + log-temporal [0.15] + spatial [0.12] + social [0.15] + affective [0.10] + narrative [0.23] with global modifiers (reliability gating, landmark anchoring, extraction sequence binding).

**Current (2-dimensional, linear temporal, static weights)**:
$$d(a, b) = 0.7 \cdot d_{cos} + 0.3 \cdot d_{time}^{linear}$$

**Proposed (5-dimensional, exponential temporal, context-adaptive weights)**:
$$d(a, b) = w_s \cdot d_{cos} + w_t \cdot d_{time}^{exp} + w_{sp} \cdot d_{spatial} + w_{soc} \cdot d_{social} + w_a \cdot d_{activity}$$

With short-circuit: if `narrative_thread_id` matches, $d = 0$.

Default weights: $w_s = 0.45, w_t = 0.20, w_{sp} = 0.15, w_{soc} = 0.10, w_a = 0.10$ (sum = 1.0)

**Backward compatibility**: When MW v2 signals are absent (legacy events, missing fields), spatial/social/activity distances default to 0.5 (neutral), and the formula degrades gracefully to approximately the current 2D behavior.

### 17.7 Summary of Findings

| Finding | Category | Severity | Action |
| ------- | -------- | -------- | ------ |
| Cosine distance implementation is mathematically correct | Correctness | N/A | No action needed |
| Temporal normalization is linear; neuroscience says it should be exponential | Science | MEDIUM | Replace with exponential kernel ($\tau = 30\text{min}$) |
| Only 2 of 5 episodic binding dimensions used | Science | HIGH | Add spatial, social, activity components |
| Static weights ignore event novelty/routine context | Science | MEDIUM | Add context-adaptive weight adjustment |
| `build_distance_matrix` uses Python double loop -- 100x slower than vectorized | Performance | MEDIUM | Replace with scipy.cdist + numpy broadcasting |
| `narrative_thread_id` is the highest-fidelity clustering signal, completely unused | MW v2 gap | HIGH | Add narrative thread short-circuit |
| ~~`geohash_6` available on P03EventState but EventAdapter returns None~~ | Bug | ~~MEDIUM~~ **RESOLVED** | ~~One-line fix (Section 16.3)~~ **DONE** (GAP-002) |
| Infinity clipped to magic number 1e10 in downstream consumers | Code quality | LOW | Extract to named constant |
| `compute_from_arrays` exists as optimized path but `build_distance_matrix` still creates per-pair arrays | Performance | LOW | Refactor to use stacked matrix path |

### 17.8 Neuroscience References

| # | Reference | Relevance |
| - | --------- | --------- |
| 1 | Tulving, E. (2002). Episodic memory: From mind to brain. Annual Review of Psychology, 53, 1-25. | Foundational: Defines 5 dimensions of episodic encoding (what, when, where, who, how) |
| 2 | Howard, M.W. & Kahana, M.J. (2002). A distributed representation of temporal context. Journal of Mathematical Psychology, 46(3), 269-299. | Temporal context model (TCM): temporal binding follows exponential decay, not linear |
| 3 | Polyn, S.M. et al. (2009). A context maintenance and retrieval model of organizational processes in free recall. Psychological Review, 116(1), 129-156. | CMR model: context drifts exponentially, nearby events share more context |
| 4 | Conway, M.A. (2005). Memory and the self. Journal of Memory and Language, 53(4), 594-628. | Self-Memory System: episodes cluster by goal relevance and identity themes |
| 5 | Rubin, D.C. (2006). The Basic-Systems Model of Episodic Memory. Perspectives on Psychological Science, 1(4), 277-311. | Basic Systems: spatial, emotion, narrative, and sensory systems bind episodes |
| 6 | Zacks, J.M. & Swallow, K.M. (2007). Event segmentation. Current Directions in Psychological Science, 16(2), 80-84. | Event segmentation theory: boundaries at prediction errors (location change, goal change, person change) |
| 7 | Dunbar, R.I.M. (1998). The social brain hypothesis. Evolutionary Anthropology, 6(5), 178-190. | Social brain: who was present is primary memory organizer |
| 8 | Eichenbaum, H. (2017). On the integration of space, time, and memory. Neuron, 95(5), 1007-1018. | Hippocampal integration: space and time are bound together in episodic memory, not independent |

---

## 18. Algorithm Deep Trace: EpisodeSplitter

**File**: `k0/modules/consolidation/algorithms/episode_splitter.py` (463 lines)
**Role**: Pre-clustering event segmentation — runs FIRST in R2 pipeline before DBSCAN/HDBSCAN
**Called by**: `R2EpisodicIntegrator._split_events()` at line 665 of `r2_episodic_integrator.py`
**Tests**: 30 tests in `tests/k0/consolidation/algorithms/test_episode_splitter.py`

### 18.1 Algorithm Description

EpisodeSplitter implements sequential event segmentation: given a time-sorted stream of events,
it partitions them into discrete "episodes" (contiguous subsequences) by detecting **boundary signals**
between consecutive events. This is the R2 gatekeeper — its output determines what events
get grouped together for downstream DBSCAN/HDBSCAN clustering.

**Core Data Structures:**

```text
SplitConfig:
    max_episode_hours: float = 4.0       # Hard ceiling per episode
    time_gap_minutes: float = 30.0       # Silence-based boundary
    geohash_distance_threshold: int = 4  # Prefix character distance
```

```text
SplittableEvent Protocol:
    event_id: str        # Required
    timestamp: int       # Required (milliseconds)
    # Optional (accessed via getattr):
    location_geohash: Optional[str]
    geohash_6: Optional[str]
    activity_type: Optional[str]
```

**Split Result**: `SplitResult(episodes=List[List[Event]], split_reasons=Dict[str, int])`

### 18.2 Algorithm Logic: 4-Signal Priority Cascade

The `_detect_break(prev, curr, episode_start_ts)` method checks signals in fixed priority order.
First match wins — only one reason is recorded per boundary:

| Priority | Signal | Condition | Field Accessed |
| -------- | ------ | --------- | -------------- |
| 1 | **Location Change** | `_geohash_distance(prev_geo, curr_geo) >= threshold` | `getattr(e, "location_geohash") or getattr(e, "geohash_6")` |
| 2 | **Activity Change** | `prev_activity != curr_activity` (both non-None) | `getattr(e, "activity_type")` |
| 3 | **Time Gap** | `curr.timestamp - prev.timestamp > 30min` | `e.timestamp` (direct) |
| 4 | **Hard Limit** | `curr.timestamp - episode_start > 4h` | `e.timestamp` (direct) |

**Geohash Distance Algorithm** (`_geohash_distance`):

```python
# Counts characters from first difference position
# "u4pruyd" vs "gcpvj0d" -> differ at pos 0 -> distance = 7
# "u4pruyd" vs "u4qabcd" -> differ at pos 2 -> distance = 5
for i, (c1, c2) in enumerate(zip(geo1, geo2)):
    if c1 != c2:
        return max(len(geo1), len(geo2)) - i
return 0  # identical
```

**Split Loop** (`split(events)`):

```
episodes = [[events[0]]]
for each event[i] (i=1..n):
    if _detect_break(events[i-1], events[i], episode_start_ts):
        start new episode
    else:
        append to current episode
return SplitResult(episodes, split_reasons)
```

### 18.3 Caller Trace: How R2 Feeds the Splitter

**Step 1: Component Initialization** (`_initialize_components`, line 575):

```python
split_config = SplitConfig(
    time_gap_minutes=self.config.time_gap_minutes,
    # NOTE: max_episode_hours and geohash_distance_threshold NOT passed
    # Uses defaults: 4.0 hours, threshold 4
)
self._splitter = EpisodeSplitter(config=split_config)
```

**Step 2: Event Wrapping** (line ~370 in `run()`):

```python
adapted_events = [EventAdapter(e) for e in novel_events]
```

**Step 3: Splitting** (`_split_events`, line 665):

```python
def _split_events(self, events: List[EventAdapter]) -> List[List[EventAdapter]]:
    if not self.config.enable_splitting or self._splitter is None:
        return [events]  # No splitting = single sequence
    split_result = self._splitter.split(events)
    return split_result.episodes
```

**Step 4: Post-Split Clustering** (line ~380):

```python
for sequence in sequences:
    if len(sequence) < self.config.min_batch_size:
        all_noise_ids.extend(e.event_id for e in sequence)  # Too small = noise
        continue
    clustering_result = self._clusterer.cluster(sequence)
```

### 18.4 The EventAdapter Blockade (~~CRITICAL~~ **RESOLVED -- GAP-002**)

EventAdapter (lines 130-175 of `r2_episodic_integrator.py`) wraps P03EventState for R2 algorithms.
**~~It blocks 2 of 4 split signals:~~ All 4 split signals are now LIVE after GAP-002 EventAdapter fix:**

| EpisodeSplitter Needs | EventAdapter Exposes | P03EventState Has | Status |
| --------------------- | -------------------- | ----------------- | ------ |
| `location_geohash` or `geohash_6` | `geohash` property ~~returns `None` (hardcoded)~~ **returns `self.event.geohash_6`** | `geohash_6: str = ""` | **~~DEAD~~ LIVE** |
| `activity_type` | ~~Not exposed at all~~ **Exposed via `self.event.activity_type`** | `activity_type: str = ""` | **~~DEAD~~ LIVE** |
| `timestamp` | `self.event.timestamp` (passthrough) | `timestamp: int` | **WORKS** |
| *(episode_start via timestamp)* | *(same)* | *(same)* | **WORKS** |

**~~Root Cause~~** **RESOLVED**: EventAdapter was designed for the EventLike protocol (event_id, timestamp,
embedding_768, geohash, ner_entities, importance_score). GAP-002 expanded EventAdapter to expose 20+ properties
including geohash_6, activity_type, activity_type_ultrabert, narrative_thread_id, social_context, and all
MW v2 signals from the underlying P03EventState.

**~~Impact~~** **MITIGATED**: ~~The splitter degrades to a pure time-based segmenter. It can only detect:~~
With GAP-002, the splitter now has access to all 4 signals. Remaining gap: the splitter still uses
a first-match-wins priority cascade rather than the neuromorphic boundary strength scoring.
Pre-GAP-002 it could only detect:

- Signal 3: Time gaps > 30 minutes
- Signal 4: Hard limit > 4 hours

A family dinner that transitions smoothly to homework help at the same table (no time gap)
will be treated as one episode, even though they are cognitively distinct events.

### 18.5 Correctness Audit

| ID | Severity | Finding | Evidence |
| -- | -------- | ------- | -------- |
| S18-1 | ~~**P1-CRITICAL**~~ **RESOLVED** | ~~2 of 4 split signals are dead~~ **4 of 4 split signals are LIVE** | ~~EventAdapter.geohash returns `None`; EventAdapter has no `activity_type`, `location_geohash`, or `geohash_6` attribute~~ GAP-002 exposed geohash_6, activity_type, and 18+ other properties via EventAdapter |
| S18-2 | **P2-MEDIUM** | No sort verification | `split()` docstring says "Events must be sorted by timestamp" but no assertion. If R0/R1 scrambles order, episodes will be incorrect |
| S18-3 | **P2-MEDIUM** | Geohash distance is Z-curve-naive | Geohash prefix comparison ignores Z-curve interleaving. Two locations 100m apart at cell boundaries can have max geohash_distance. Should convert to lat/lon for Haversine |
| S18-4 | **P3-LOW** | First-match-wins loses boundary strength | A boundary where location AND activity AND time gap all change is recorded as just "location_change". Multi-signal boundaries are stronger in memory (Zacks et al., 2007) |
| S18-5 | **P3-LOW** | Hard 30-min cutoff ignores context | A 31-min break during sleep is not a boundary. A 10-min break between "got fired" and "told wife" is a boundary. Context-dependent thresholds needed |
| S18-6 | **P3-LOW** | SplitConfig only receives time_gap_minutes | `_initialize_components` passes only `time_gap_minutes`. `max_episode_hours` and `geohash_distance_threshold` use defaults. Config flexibility lost |

### 18.6 Science Assessment: Event Segmentation Theory

The EpisodeSplitter implements a simplified version of **Event Segmentation Theory** (EST)
(Zacks & Swallow, 2007; Zacks, Speer, Swallow, Brewer & Reynolds, 2007).

EST identifies that humans naturally segment continuous experience into discrete events at
**event boundaries** — points where there is a significant change in the ongoing situation.
The brain's prediction system detects these boundaries: when the current situation model
fails to predict what happens next, a new event model is initiated.

**EST Boundary Types vs Current Implementation:**

| EST Boundary Type | Neuroscience Basis | Current Status | Signal Source Available |
| ----------------- | ------------------ | -------------- | ---------------------- |
| Spatial (new location) | Place cells, grid cells (O'Keefe & Moser) | Signal 1: **~~DEAD~~ LIVE** (GAP-002 EventAdapter fix) | `place_id` (primary), `geohash_6`, `location_name`, `location_hierarchy_json`, `spatial_context_json` |
| Temporal (time gap) | Time cells in hippocampus (Eichenbaum, 2014) | Signal 3: WORKS | `conversation_anchor_ms` (gold), `temporal_source`, `temporal_links_json`, `temporal_anchor_json` |
| Goal/Task (new activity) | Prefrontal goal representations (Zacks, 2007) | Signal 2: **~~DEAD~~ LIVE** (GAP-002 EventAdapter fix) | `activity_type_ultrabert` (12-type), `intent_ultrabert`, `goal_context` |
| Social (different people) | Social brain network (Dunbar, 1998) | NOT IMPLEMENTED (signals available) | `social_context`, `social_intimacy`, `participants_json`, `participant_relationships_json`, `is_solo_event` |
| Causal (prediction error) | Anterior cingulate prediction error (Zacks, 2007) | NOT IMPLEMENTED (signals available) | `novelty`, `surprise_level`, `memory_tier` (landmark = flashbulb) |
| Narrative (topic change) | Default mode network, narrative integration | NOT IMPLEMENTED (signals available) | `narrative_thread_id`, `narrative_arc_position`, `narrative_is_goal_event`, `temporal_orientation` |
| Affective (emotional shift) | Amygdala modulation (McGaugh, 2004) | NOT IMPLEMENTED (signals available) | `affect_valence`, `affect_arousal`, `affect_dominance`, `emotions_json`, `entity_salience_json` |
| Cognitive (encoding depth) | Prefrontal encoding (Craik & Lockhart, 1972) | NOT IMPLEMENTED (signals available) | `elaboration_depth`, `identity_domains_json`, `identity_relevance`, `source_reliability` |

**Key Gap**: EST emphasizes that **prediction error** is the core mechanism — boundaries occur
when what happens next violates expectations. The current implementation checks only surface
feature changes (location, activity, time), not prediction error. MW v2 signals `novelty`
and `surprise_level` are direct proxies for prediction error but are completely unused.

### 18.7 MW v2 Signal Enhancement Opportunities

P03EventState carries 15+ MW v2 signals that the splitter ignores. These map directly to
neuroscience-validated episode boundary types:

**Enhancement 1: Narrative Thread Break (HIGHEST IMPACT)**

- **Signal**: `narrative_thread_id` (MW v2 M3/0073)
- **Boundary Logic**: If `prev.narrative_thread_id != curr.narrative_thread_id` (both non-empty), this is a topic change
- **Neuroscience**: Narrative structure is a primary organizer of episodic memory (Rubin, 2006). Same conversation thread = same episode. Different thread = different episode
- **Impact**: This is the STRONGEST available signal for episode boundaries. Two events 5 minutes apart on different topics are different episodes; two events 2 hours apart on the same topic continuation are the same episode

**Enhancement 2: Social Context Change**

- **Signal**: `social_context` (nuclear_family / solo / work / friends), `social_intimacy` (HIGH / LOW), `participants_json`
- **Boundary Logic**: If `prev.social_context != curr.social_context`, or participant set changes significantly
- **Neuroscience**: Social brain hypothesis (Dunbar, 1998) — who is present is a primary memory organizer. "Dinner with family" vs "call with boss" = separate episodes even if 2 minutes apart
- **Impact**: Especially important for family-oriented system where social relationships are core

**Enhancement 3: UltraBERT Activity Type (12-type)**

- **Signal**: `activity_type_ultrabert` (DIARY/TASK/HEALTH/FINANCE/RELATIONSHIP/WORK/META/MEMORY/PLANNING/CELEBRATION/CONCERN/GRATITUDE)
- **Boundary Logic**: Replace legacy 7-type with 12-type classification. `HEALTH -> FINANCE` = clear boundary
- **Neuroscience**: Activity type maps to goal boundaries in EST. Finer-grained classification = more accurate segmentation
- **Impact**: 12 types vs 7 types means 71% more discriminative power

**Enhancement 4: Novelty/Surprise Spike**

- **Signal**: `novelty` (ROUTINE/EXPECTED/NOVEL/SURPRISING), `surprise_level` (float 0-1)
- **Boundary Logic**: If curr.novelty in (NOVEL, SURPRISING) and prev.novelty in (ROUTINE, EXPECTED), or surprise_level > 0.7 = boundary
- **Neuroscience**: This is the CORE EST mechanism — prediction error. Novel/surprising events create strong episode boundaries because they force a new situation model (Zacks & Swallow, 2007)
- **Impact**: Captures boundaries that no surface feature change detects (e.g., unexpected bad news in an otherwise routine conversation)

**Enhancement 5: Temporal Orientation Shift**

- **Signal**: `temporal_orientation` (PAST / ONGOING / FUTURE_COMMITMENT)
- **Boundary Logic**: If `prev.temporal_orientation != curr.temporal_orientation` (both non-empty)
- **Neuroscience**: Mental time travel engages distinct hippocampal circuits for past recall vs future planning (Schacter et al., 2012). Shifting between "remembering yesterday" and "planning tomorrow" is a cognitive mode switch
- **Impact**: Moderate — fires less often but captures important cognitive transitions

**Enhancement 6: Identity Domain Change**

- **Signal**: `identity_domains_json` (e.g., ["parenting", "career"])
- **Boundary Logic**: If dominant identity domain shifts between consecutive events
- **Neuroscience**: Self-referential processing in medial prefrontal cortex. Different identity domains activate different self-schemas
- **Impact**: Low frequency but high significance when it fires

### 18.8 Proposed Enhanced Splitter Design (**SUPERSEDED** by Neuromorphic Subsystem 2: Prediction Error Accumulator)

> **See**: temp_r2_design.md Subsystem 2 — 7-channel prediction error accumulator (narrative [0.25] + social [0.15] + spatial [0.12] + activity [0.13] + temporal [0.15] + affective [0.10] + cognitive [0.10]) with narrative veto, landmark anchoring, and 3-tier boundary logic.

Replace fixed 4-signal priority cascade with **boundary strength scoring**:

```
BoundaryScore = weighted sum of all signals that fire at each event pair

Signal Weights (proposed, tunable):
    narrative_thread_break:  0.30  (strongest predictor per EST)
    social_context_change:   0.20  (who-was-there is primary organizer)
    activity_type_change:    0.15  (goal boundary)
    location_change:         0.10  (place cell activation)
    novelty_spike:           0.10  (prediction error)
    temporal_orientation:    0.05  (cognitive mode shift)
    time_gap_normalized:     0.10  (continuous, not binary cutoff)

Boundary Decision:
    if BoundaryScore >= threshold (default 0.25):
        split here
    Hard limit: episode duration > max_episode_hours always splits
```

**Key Differences from Current:**

1. **All signals contribute** — no first-match-wins information loss
2. **Continuous scoring** — time_gap is normalized (gap_minutes / max_gap) not binary (> 30min)
3. **Context-dependent** — a 15-min gap with narrative_thread_break and social_context_change scores higher than a 45-min gap with no other signals
4. **MW v2 signals** — 5 new dimensions from P03EventState
5. **Adaptive threshold** — threshold can be tuned per space via st_learned_weights (same pattern as EpsAdjuster)

**Sort Verification** (mandatory addition):

```python
def split(self, events):
    for i in range(1, len(events)):
        assert events[i].timestamp >= events[i-1].timestamp, \
            f"Events not sorted: [{i-1}].ts={events[i-1].timestamp} > [{i}].ts={events[i].timestamp}"
```

### 18.9 Summary of Findings

| Dimension | Current State | Proposed State |
| --------- | ------------- | -------------- |
| Active signals | ~~2 of 4 (time gap + hard limit)~~ **4 of 4 (all signals LIVE after GAP-002)** | 8 (all MW v2 signals + fixed EventAdapter) |
| Signal fusion | First-match-wins (lossy) | Weighted boundary strength scoring |
| Time model | Binary 30-min cutoff | Normalized continuous contribution |
| Activity classification | Legacy 7-type (dead) | UltraBERT 12-type |
| Social awareness | None | social_context + participants |
| Narrative awareness | None | narrative_thread_id |
| Prediction error | None | novelty + surprise_level |
| Sort safety | Assumed, not verified | Asserted |
| Geohash distance | Z-curve-naive prefix diff | Prefix diff (acceptable heuristic) |
| Blocking fix required | ~~N/A~~ **DONE** | ~~EventAdapter must expose geohash_6, activity_type, and all MW v2 signals~~ **RESOLVED** (GAP-002) |

**~~Minimum Fix (unblocks 2 dead signals)~~** **DONE**: ~~Fix EventAdapter to expose `geohash_6` and `activity_type` from underlying P03EventState.~~ GAP-002 exposed geohash_6, activity_type, and 18+ other MW v2 properties via EventAdapter.

**Full Enhancement**: Replace priority cascade with boundary strength scoring using all 8 MW v2 signals.

### 18.10 Neuroscience References

| # | Reference | Relevance to EpisodeSplitter |
| - | --------- | ---------------------------- |
| 1 | Zacks, J.M. & Swallow, K.M. (2007). Event segmentation. Current Directions in Psychological Science, 16(2), 80-84. | Core theory: event boundaries at prediction errors (location, goal, person, cause changes) |
| 2 | Zacks, J.M., Speer, N.K., Swallow, K.M., Brewer, J.B. & Reynolds, J.R. (2007). Event perception: a mind-brain perspective. Psychological Bulletin, 133(2), 273-293. | Comprehensive EST model: hierarchical segmentation with coarse and fine boundaries |
| 3 | Rubin, D.C. (2006). The Basic-Systems Model of Episodic Memory. Perspectives on Psychological Science, 1(4), 277-311. | Basic Systems: narrative, spatial, emotion, and sensory systems independently contribute to episode boundaries |
| 4 | Dunbar, R.I.M. (1998). The social brain hypothesis. Evolutionary Anthropology, 6(5), 178-190. | Social group changes are primary memory organizers — "who was there" defines episodes |
| 5 | Schacter, D.L., Addis, D.R. & Buckner, R.L. (2012). Remembering the past to imagine the future. Nature Reviews Neuroscience, 8, 657-661. | Past vs future mental time travel engages distinct hippocampal circuits — temporal orientation shift = episode boundary |
| 6 | Kurby, C.A. & Zacks, J.M. (2008). Segmentation in the perception and memory of events. Trends in Cognitive Sciences, 12(2), 72-79. | Segmentation quality predicts memory quality — better boundaries = better recall. Multi-signal boundaries are remembered better than single-signal |
| 7 | Radvansky, G.A. & Zacks, J.M. (2014). Event Cognition. Oxford University Press. | Book-length treatment: event models are updated at boundaries when prediction error exceeds threshold |
| 8 | Eichenbaum, H. (2014). Time cells in the hippocampus: a new dimension for mapping memories. Nature Reviews Neuroscience, 15(11), 732-744. | Time cells fire at specific moments within episodes — temporal gaps between events signal new episodes |

---

## 19. DBSCAN Deprecation: Full Touch-Point Inventory & Removal Plan

**Decision**: DBSCAN is deprecated in favor of HDBSCAN. `R2Config.use_hdbscan` already defaults to `True`.
HDBSCAN is the production clustering algorithm. All DBSCAN code, imports, config paths, fallbacks,
test files, and contract references must be removed or migrated.

### 19.1 Why DBSCAN Is Deprecated

| Dimension | DBSCAN | HDBSCAN | Winner |
| --------- | ------ | ------- | ------ |
| Eps selection | Fixed eps -- requires manual tuning or adaptive learning loop | Automatic multi-resolution -- discovers cluster structure without eps | HDBSCAN |
| Variable density | Fails when episodes have different densities (tight diary cluster vs sparse work cluster) | Handles variable density natively via hierarchical tree | HDBSCAN |
| Noise handling | Hard noise -- label = -1 is final, no rescue | Soft noise rescue via outlier_scores -- recovers borderline events | HDBSCAN |
| Membership confidence | Binary (in or out) | Probabilities [0,1] per event -- enables downstream confidence-weighted processing | HDBSCAN |
| Parameter sensitivity | Highly sensitive to eps -- wrong value = over/under clustering | Robust to parameter choices -- min_cluster_size=2 works broadly | HDBSCAN |
| Adaptive learning dependency | Needs EpsAdjuster + MinSamplesAdjuster to tune eps/min_samples per space | Minimal tuning needed -- can remove adaptive eps learning entirely | HDBSCAN |

**Summary**: DBSCAN requires an entire adaptive learning subsystem (eps_adjuster, min_samples_adjuster,
st_learned_weights storage, syscall param_key reads/writes) just to approximate what HDBSCAN gives out of
the box. Removing DBSCAN simplifies R2 by eliminating the eps learning loop.

### 19.2 Complete DBSCAN Touch-Point Inventory

Every file, class, function, config field, import, contract, test, and database key that references
DBSCAN. Organized by removal action required.

#### Category A: Files to DELETE (entire file removal)

| # | File | Lines | Contents | Dependents |
| - | ---- | ----- | -------- | ---------- |
| A1 | `k0/modules/consolidation/algorithms/episodic_dbscan.py` | 460 | `EpisodicDBSCAN` class, `ClusteringResult` dataclass, `ClusterableEvent` protocol | R2 integrator (conditional), **init**.py, test file |
| A2 | `tests/k0/pipelines/p03/test_r2_episodic_dbscan.py` | 282 | 13 tests for EpisodicDBSCAN (all 5 test classes) | None |

**ClusteringResult migration note**: `ClusteringResult` is defined in `episodic_dbscan.py` but
referenced by `r2_episodic_integrator.py` in the `Union[ClusteringResult, HDBSCANClusteringResult]`
type hints. After DBSCAN removal, the Union simplifies to just `HDBSCANClusteringResult`.

#### Category B: Files to EDIT (remove DBSCAN branches, imports, config)

| # | File | Line(s) | What to Remove/Change | Impact |
| - | ---- | ------- | --------------------- | ------ |
| B1 | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | 34 | Remove import: `ClusteringResult` | Dead import after file A1 deleted |
| B2 | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | 40 | Remove import: `EpisodicDBSCAN` | Dead import |
| B3 | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | 71-119 | R2Config: remove `eps`, `min_samples`, `use_hdbscan` fields; `use_hdbscan` is always True so the field is pointless; eps/min_samples are DBSCAN-only | Config simplification |
| B4 | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | 213 | Remove type hint: `Optional[Union[EpisodicDBSCAN, EpisodicHDBSCAN]]` -> `Optional[EpisodicHDBSCAN]` | Type simplification |
| B5 | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | 582-612 | `_initialize_components`: remove entire `else` branch (DBSCAN path) | Dead code path |
| B6 | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | 628-660 | `_get_dbscan_params` method: rename or refactor. Currently returns `DBSCANParams` for both paths. HDBSCAN uses `HDBSCANParams` directly. Method can be simplified to only get learned temporal_weight or removed entirely | Method removal/rename |
| B7 | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | 322 | `dbscan_params = await self._get_dbscan_params(ctx, space_id)` call in `run()` -- no longer needed if HDBSCAN has its own param init | Dead call |
| B8 | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | 385 | `all_results: List[Union[ClusteringResult, HDBSCANClusteringResult]]` -> `List[HDBSCANClusteringResult]` | Type simplification |
| B9 | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | 1376-1420 | `_update_event_states`: remove `Union[ClusteringResult, HDBSCANClusteringResult]` type hint -> `List[HDBSCANClusteringResult]` | Type simplification |
| B10 | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | 1486 | `param_key="dbscan_eps"` -- rename to `clustering_eps` or remove (HDBSCAN auto-tunes) | DB key rename |
| B11 | `k0/pipelines/p03/phases/r2_episodic_integrator.py` | 1515 | `param_key="dbscan_min_samples"` -- rename to `clustering_min_samples` or remove | DB key rename |
| B12 | `k0/modules/consolidation/algorithms/__init__.py` | 155 | Remove: `from .episodic_dbscan import ClusteringResult, EpisodicDBSCAN` | Dead import |
| B13 | `k0/modules/consolidation/algorithms/__init__.py` | 369 | Remove: `"ClusteringResult"` from `__all__` | Dead export |
| B14 | `k0/modules/consolidation/algorithms/composite_distance.py` | 54-125 | `DBSCANParams` dataclass: **DO NOT DELETE** -- shared by HDBSCAN (via `to_dbscan_params()`). Rename to `ClusteringParams` or `DistanceParams` to remove DBSCAN naming | Rename only |
| B15 | `k0/modules/consolidation/algorithms/episodic_hdbscan.py` | 37 | `from sklearn.cluster import DBSCAN` -- remove if fallback removed | Dead import |
| B16 | `k0/modules/consolidation/algorithms/episodic_hdbscan.py` | 39 | `from ... import CompositeDistance, DBSCANParams` -- rename DBSCANParams usage | Rename |
| B17 | `k0/modules/consolidation/algorithms/episodic_hdbscan.py` | 116-120 | `to_dbscan_params()` method in HDBSCANParams -- rename to `to_distance_params()` | Rename |
| B18 | `k0/modules/consolidation/algorithms/episodic_hdbscan.py` | 296 | `_run_dbscan_fallback(distances)` call -- remove fallback path | Dead code |
| B19 | `k0/modules/consolidation/algorithms/episodic_hdbscan.py` | 362-416 | `_run_dbscan_fallback()` method + `_compute_outlier_scores_fallback()` -- delete entirely | Dead code (55 lines) |
| B20 | `k0/modules/consolidation/algorithms/episodic_hdbscan.py` | 249-254 | HDBSCAN_AVAILABLE fallback warning -- replace with hard error if hdbscan not installed | Fail-fast |
| B21 | `k0/modules/consolidation/algorithms/eps_adjuster.py` | 338, 374 | SQL `param_key = 'dbscan_eps'` -- rename to `clustering_eps` | DB key rename |
| B22 | `k0/modules/consolidation/algorithms/min_samples_adjuster.py` | 296, 336 | SQL `param_key = 'dbscan_min_samples'` -- rename to `clustering_min_samples` | DB key rename |
| B23 | `k0/modules/consolidation/__init__.py` | 28, 45 | Commented-out `EpisodicDBSCAN` references -- delete comments | Cleanup |

#### Category C: Contracts to UPDATE

| # | File | Line(s) | Current Text | New Text |
| - | ---- | ------- | ------------ | -------- |
| C1 | `k0/contracts/pipelines/p03_consolidation.v1.yaml` | 18 | `R2: Episodic clustering (DBSCAN on 768-dim embeddings)` | `R2: Episodic clustering (HDBSCAN on 768-dim embeddings)` |
| C2 | `k0/contracts/pipelines/p03_consolidation.v1.yaml` | 163 | `R2 - Episodic clustering using DBSCAN on 768-dim embeddings` | `R2 - Episodic clustering using HDBSCAN on 768-dim embeddings` |
| C3 | `k0/contracts/pipelines/p03_consolidation.v1.yaml` | 167 | `algorithm: DBSCAN` | `algorithm: HDBSCAN` |
| C4 | `k0/contracts/pipelines/p03_consolidation.v1.yaml` | 405 | `DBSCAN timeout - skip R2` | `HDBSCAN timeout - skip R2` |
| C5 | `k0/contracts/capabilities/consolidation.v1.yaml` | 58 | `Cluster events into episodes using DBSCAN` | `Cluster events into episodes using HDBSCAN` |
| C6 | `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml` | 40 | `Groups related events into coherent episodes using DBSCAN` | `Groups related events into coherent episodes using HDBSCAN` |
| C7 | `k0/contracts/modules/consolidation.episodic_clusterer.v1.yaml` | 44 | `Algorithm: DBSCAN (Density-Based Spatial Clustering)` | `Algorithm: HDBSCAN (Hierarchical Density-Based Clustering)` |

#### Category D: Test Files to UPDATE

| # | File | What to Change |
| - | ---- | -------------- |
| D1 | `tests/k0/pipelines/p03/test_r2_episodic_dbscan.py` | DELETE entire file (13 tests) -- replaced by HDBSCAN tests |
| D2 | `tests/k0/pipelines/p03/test_r2_composite_distance.py` | Rename `TestDBSCANParams` class and all `test_dbscan_params_*` methods. Change `DBSCANParams` usage to renamed class. (~20 references) |
| D3 | `tests/k0/pipelines/p03/test_r2_integration.py` | Remove `EpisodicDBSCAN` imports (lines 41, 43). Replace all `EpisodicDBSCAN` usage with `EpisodicHDBSCAN`. Update `DBSCANParams` to renamed class. (~15 references) |

#### Category E: Database / Storage Keys to MIGRATE

| # | Storage | Current Key | New Key | Files Affected |
| - | ------- | ----------- | ------- | -------------- |
| E1 | st_learned_weights | `dbscan_eps` | `clustering_eps` | eps_adjuster.py (2), r2_episodic_integrator.py (2) |
| E2 | st_learned_weights | `dbscan_min_samples` | `clustering_min_samples` | min_samples_adjuster.py (2), r2_episodic_integrator.py (2) |

**Migration SQL** (run once on deployed databases):

```sql
UPDATE st_learned_weights SET param_key = 'clustering_eps' WHERE param_key = 'dbscan_eps';
UPDATE st_learned_weights SET param_key = 'clustering_min_samples' WHERE param_key = 'dbscan_min_samples';
```

#### Category F: Architecture Diagrams to UPDATE

| # | File | What to Change |
| - | ---- | -------------- |
| F1 | `architecture_diagrams/k0/p03_file_dependencies.mmd` | Line 100: change "Cluster via DBSCAN" to "Cluster via HDBSCAN" |
| F2 | `architecture_diagrams/k0/p03_file_dependencies.mmd` | Line 227: remove `ALG_EPISODIC_DBSCAN` node or rename to HDBSCAN |
| F3 | `architecture_diagrams/k0/p03_file_dependencies.mmd` | Lines 576, 1131, 1174, 1209: update all `ALG_EPISODIC_DBSCAN` references |

#### Category G: Documentation to UPDATE

| # | File | What to Change |
| - | ---- | -------------- |
| G1 | `docs/plans/MASTER_IMPLEMENTATION_SKELETON.md` | Lines 5085, 5214, 5221, 5235, 5257, 5266: replace DBSCAN references with HDBSCAN |
| G2 | This discovery doc (Sections 1-18) | Multiple references to "DBSCAN/HDBSCAN" -- update to "HDBSCAN" only |

### 19.3 Dependency Analysis: What Breaks When episodic_dbscan.py Is Deleted

```text
episodic_dbscan.py EXPORTS:
  +-- EpisodicDBSCAN (class)
  |     +-- used by r2_episodic_integrator.py (conditional: use_hdbscan=False)
  |     +-- imported in algorithms/__init__.py
  |     +-- imported in test_r2_episodic_dbscan.py
  |     +-- imported in test_r2_integration.py
  |
  +-- ClusteringResult (dataclass)
  |     +-- used by r2_episodic_integrator.py in Union type hints (4 places)
  |     +-- imported in algorithms/__init__.py
  |     +-- exported in algorithms/__init__.__all__
  |
  +-- ClusterableEvent (Protocol)
        +-- internal to episodic_dbscan.py only
        +-- episodic_hdbscan.py defines its own identical protocol
```

**Safe to delete**: `ClusterableEvent` protocol is duplicated in `episodic_hdbscan.py`.
**Requires migration**: `ClusteringResult` must be replaced with `HDBSCANClusteringResult` in all Union types.

### 19.4 HDBSCAN Internal DBSCAN Fallback: Must Remove

`episodic_hdbscan.py` contains a DBSCAN fallback path:

```python
# Line 29-34: Conditional import
try:
    import hdbscan
    HDBSCAN_AVAILABLE = True
except ImportError:
    HDBSCAN_AVAILABLE = False

# Line 37: sklearn DBSCAN import (for fallback)
from sklearn.cluster import DBSCAN

# Line 294-296: Fallback branch in cluster()
if self._use_hdbscan:
    labels, probabilities, outlier_scores = self._run_hdbscan(distances)
else:
    labels, probabilities, outlier_scores = self._run_dbscan_fallback(distances)

# Lines 362-416: _run_dbscan_fallback() + _compute_outlier_scores_fallback() methods
```

**Action**: Replace conditional import with hard requirement. If `hdbscan` is not installed,
raise `ImportError` at module load time. Remove the `_run_dbscan_fallback()` and
`_compute_outlier_scores_fallback()` methods (55 lines). Remove `from sklearn.cluster import DBSCAN`.

### 19.5 EpsAdjuster / MinSamplesAdjuster: Keep or Remove?

These two algorithms exist primarily to tune DBSCAN's eps and min_samples parameters.
With HDBSCAN, the question is: are they still needed?

| Algorithm | DBSCAN Role | HDBSCAN Role | Verdict |
| --------- | ----------- | ------------ | ------- |
| EpsAdjuster | Tunes eps per-space based on silhouette score | HDBSCAN has `cluster_selection_epsilon` (optional flat cut). Could tune this, but HDBSCAN works well without it | **KEEP but rename** -- useful for fine-tuning cluster_selection_epsilon in edge cases |
| MinSamplesAdjuster | Tunes min_samples per-space based on noise ratio | HDBSCAN has `min_samples` param that controls density smoothing. Could tune this | **KEEP but rename** -- noise level tuning is still valuable |

**Action**: Keep both algorithms but rename their param_keys from `dbscan_eps`/`dbscan_min_samples`
to `clustering_eps`/`clustering_min_samples`. Update their docstrings from "DBSCAN" to "clustering".

### 19.6 DBSCANParams Rename Plan

`DBSCANParams` in `composite_distance.py` is the shared parameter dataclass used by BOTH
EpisodicDBSCAN and EpisodicHDBSCAN (via `to_dbscan_params()`). It holds:

- `eps`, `min_samples`, `temporal_weight`, `max_temporal_gap_hours`

These are distance parameters, not DBSCAN-specific. The rename:

| Current Name | New Name | Reason |
| ------------ | -------- | ------ |
| `DBSCANParams` | `DistanceParams` | These control CompositeDistance behavior, not DBSCAN specifically |
| `to_dbscan_params()` | `to_distance_params()` | Method on HDBSCANParams that creates equivalent DistanceParams |
| `P03_DBSCAN_EPS` | `P03_CLUSTERING_EPS` | Config key naming in comments |

**Impact**: Rename affects ~60 references across production code and ~40 references in tests.
All are mechanical renames with no logic changes.

### 19.7 Execution Order & Risk Assessment

| Step | Action | Files Touched | Risk | Tests Affected |
| ---- | ------ | ------------- | ---- | -------------- |
| 1 | Rename `DBSCANParams` -> `DistanceParams` in composite_distance.py | 1 file | LOW (mechanical rename) | ~20 test references |
| 2 | Update all imports of `DBSCANParams` across codebase | ~8 files | LOW (find-replace) | ~40 test references |
| 3 | Remove DBSCAN fallback from episodic_hdbscan.py | 1 file | LOW (fallback removal) | 0 (no fallback tests) |
| 4 | Make hdbscan a hard dependency (remove try/except) | 1 file | MEDIUM (deploy must have hdbscan) | 0 |
| 5 | Remove `_initialize_components` DBSCAN branch | 1 file | LOW (dead code) | 0 |
| 6 | Remove `_get_dbscan_params` method, inline HDBSCAN param init | 1 file | MEDIUM (param loading refactor) | Integration tests |
| 7 | Simplify Union types to HDBSCANClusteringResult only | 1 file | LOW (type narrowing) | 0 |
| 8 | Remove R2Config DBSCAN fields (eps, min_samples, use_hdbscan) | 1 file | MEDIUM (config contract change) | Any test using R2Config |
| 9 | Delete episodic_dbscan.py | 1 file | LOW (no dependents after steps 5-7) | 0 |
| 10 | Delete test_r2_episodic_dbscan.py | 1 file | LOW (test deletion) | -13 tests |
| 11 | Update **init**.py exports | 1 file | LOW | 0 |
| 12 | Update contracts (YAML files) | 3 files | LOW (text changes) | 0 |
| 13 | Rename param_keys in eps_adjuster, min_samples_adjuster | 2 files | MEDIUM (DB key migration) | Adjuster tests |
| 14 | Run st_learned_weights migration SQL | Database | MEDIUM (data migration) | 0 |
| 15 | Update architecture diagrams | 1 file | LOW | 0 |

### 19.8 Lines of Code Impact

| Category | Lines Removed | Lines Added | Net Change |
| -------- | ------------- | ----------- | ---------- |
| episodic_dbscan.py (delete) | -460 | 0 | -460 |
| test_r2_episodic_dbscan.py (delete) | -282 | 0 | -282 |
| HDBSCAN fallback removal | -55 | +3 (hard error) | -52 |
| R2 integrator DBSCAN branch | -30 | 0 | -30 |
| R2Config field removal | -5 | 0 | -5 |
| Union type simplification | -4 | +4 (simpler types) | 0 |
| DBSCANParams rename | 0 | 0 | 0 (rename only) |
| Contract text updates | 0 | 0 | 0 (text only) |
| **TOTAL** | **-836** | **+7** | **-829** |

### 19.9 Summary

**DBSCAN is dead weight.** `R2Config.use_hdbscan` defaults to `True`. The DBSCAN code path
is unreachable in production. The HDBSCAN fallback-to-DBSCAN is a safety net for missing
pip install, not a design choice.

**Removal yields**:

- 829 fewer lines of production + test code
- Elimination of the `use_hdbscan` config toggle (single code path = fewer bugs)
- Simplified type system (`HDBSCANClusteringResult` only, no Union)
- Cleaner dependency graph (no sklearn.cluster.DBSCAN import in HDBSCAN module)
- Accurate contracts and documentation (no more "DBSCAN/HDBSCAN" ambiguity)

**Blocking dependency**: `hdbscan` pip package must be in `requirements.txt` and Docker images.
Currently it is optional (try/except). After removal, it becomes mandatory.

---

## 20. Algorithm Deep Trace: EpisodicHDBSCAN

**File**: `k0/modules/consolidation/algorithms/episodic_hdbscan.py` (653 lines)
**Role**: Primary R2 clustering algorithm -- groups pre-split event sequences into coherent episodes
**Called by**: `R2EpisodicIntegrator.run()` via `self._clusterer.cluster(sequence)` at line 395
**Upstream**: EpisodeSplitter (Section 18) feeds sequences -> HDBSCAN clusters them
**Downstream**: CentroidCalculator receives clusters -> R3 receives EpisodeClusters
**Tests**: 0 dedicated tests (gap -- only integration tests in `test_r2_integration.py`)

### 20.1 Algorithm Description

EpisodicHDBSCAN implements **Hierarchical Density-Based Spatial Clustering of Applications with Noise**
(Campello, Moulavi & Sander, 2013). Unlike DBSCAN's fixed-eps threshold, HDBSCAN builds a
hierarchical cluster tree and extracts stable clusters at multiple density levels.

**The core insight**: HDBSCAN treats clustering as a topological problem -- it builds a minimum
spanning tree of the mutual reachability graph, then walks the hierarchy to find persistent
clusters (those that survive across many density thresholds). This is fundamentally more robust
than DBSCAN's single-threshold approach.

**Pipeline Position**:

```text
R0 (Load) -> R1 (Importance) -> R2 (Cluster) -> R3 (Truth Resolution) -> R4+ (downstream)
                                  |
                            EpisodeSplitter
                                  |
                          +-------+-------+
                          |               |
                     [sequence 1]    [sequence 2]  ...
                          |               |
                     EpisodicHDBSCAN  EpisodicHDBSCAN
                          |               |
                     HDBSCANClusteringResult
                          |
                     CentroidCalculator
                          |
                     EpisodeCluster (output)
```

### 20.2 Data Flow: What HDBSCAN Actually Sees

This is the critical trace. Events flow through 3 transformations before reaching HDBSCAN:

**Layer 1: P03EventState** (40+ fields from R0 loading)

```text
Full signal inventory available:
  embedding_768, timestamp, geohash_6, activity_type, activity_type_ultrabert,
  narrative_thread_id, social_context, social_intimacy, participants_json,
  novelty, surprise_level, temporal_orientation, affect_valence, affect_arousal,
  salience_score, importance_score, location_name, location_type,
  identity_domains_json, elaboration_depth, source_type, ...
```

**Layer 2: EventAdapter** (~~6 properties -- massive signal loss~~ **20+ properties after GAP-002**)

```text
EventAdapter now exposes (GAP-002):
  event_id, timestamp, embedding_768, geohash (geohash_6),
  ner_entities, importance_score, activity_type, activity_type_ultrabert,
  narrative_thread_id, social_context, social_intimacy, participants_json,
  affect_valence, affect_arousal, novelty, surprise_level,
  temporal_orientation, salience_score, elaboration_depth,
  location_name, location_type, identity_domains_json, ...
```

**Layer 3: What HDBSCAN algorithms actually consume**

```text
CompositeDistance.compute() uses ONLY:
  embedding_768   -> cosine distance (semantic dimension)
  timestamp       -> normalized time distance (temporal dimension)

NOTHING ELSE. 40+ signals reduced to 2 dimensions.
```

**The Signal Funnel Problem** (~~CRITICAL~~ **MITIGATED after GAP-002 -- bottleneck moved from EventAdapter to CompositeDistance**):

```text
P03EventState: 40+ signals
       |
       v  (EventAdapter: GAP-002 exposes 20+ signals)
EventAdapter: 20+ signals
       |
       v  (CompositeDistance STILL ignores 18+ of 20 -- THIS is now the bottleneck)
HDBSCAN input: 2 dimensions (semantic + temporal)
```

### 20.3 Algorithm Mechanics: Step-by-Step

**Step 1: Distance Matrix Construction** (CompositeDistance.build_distance_matrix)

For n events, builds n x n pairwise distance matrix:

```text
d(i,j) = (1 - w_t) * cosine_distance(emb_i, emb_j)
        + w_t * min(1.0, |ts_i - ts_j| / max_gap_ms)

where:
  w_t = temporal_weight (default 0.3)
  max_gap_ms = 4 hours in milliseconds (14,400,000)
  cosine_distance = 1 - (emb_i . emb_j) / (||emb_i|| * ||emb_j||)

Hard cutoff: if |ts_i - ts_j| > max_gap_ms -> d(i,j) = infinity
Infinity capped to 1e10 before passing to HDBSCAN.
```

Complexity: O(n^2 * 768) -- Python double-loop, not vectorized.

**Step 2: HDBSCAN Clustering** (_run_hdbscan)

```python
hdbscan.HDBSCAN(
    min_cluster_size=2,           # Smallest episode = 2 events
    min_samples=1,                # Density smoothing (lower = more inclusive)
    metric="precomputed",         # Uses our distance matrix
    cluster_selection_epsilon=0.0, # Automatic (no flat cut)
    cluster_selection_method="leaf", # Preserve small clusters
    allow_single_cluster=False,   # Require at least 2 clusters or noise
)
```

Outputs: labels (int per event), probabilities (float per event), outlier_scores (float per event)

**Step 3: Noise Rescue** (_rescue_noise)

Two rescue strategies for noise events with `outlier_score < 0.5`:

```text
Strategy A: Assign to nearest cluster
  IF nearest_cluster_distance < 0.3:
    label[noise_event] = nearest_cluster_label
    -> rescued

Strategy B: Create weak cluster from nearby noise
  IF any other noise events within distance < 0.2 AND their outlier_score < 0.5:
    Create new cluster from noise group
    -> rescued as "weak" episode
```

**Step 4: Cluster Creation** (_create_cluster)

For each cluster label, creates EpisodeCluster with:

- cluster_id: uuid (prefixed "noise-" or "weak-" for special clusters)
- member_event_ids: list of event_ids
- dominant_sentiment: probability-weighted average of sentiment_score
- temporal_start/end: min/max timestamps
- cohesion_score: intra-cluster cosine similarity * avg_probability

### 20.4 Correctness Audit

| ID | Severity | Finding | Evidence |
| -- | -------- | ------- | -------- |
| S20-1 | ~~**P1-CRITICAL**~~ **P1-HIGH** | Only 2 of ~~40+~~ 20+ exposed signals used for clustering | CompositeDistance uses only embedding_768 + timestamp. All MW v2 signals (narrative, social, spatial, activity, novelty, affect) are **now available via EventAdapter** but invisible to CompositeDistance formula |
| S20-2 | **P1-CRITICAL** | Noise rescue uses hardcoded magic numbers | `0.3` for rescue distance, `0.2` for weak cluster distance -- no theoretical basis, not tunable via config, not adaptive |
| S20-3 | **P2-MEDIUM** | Cohesion score conflates two metrics | `cohesion = cosine_similarity * avg_probability` mixes cluster tightness (similarity) with membership confidence (probability). These measure different things |
| S20-4 | **P2-MEDIUM** | Distance matrix is O(n^2) Python loop | `build_distance_matrix` in composite_distance.py uses nested Python for-loop. For 500 events = 124,750 distance computations in pure Python. Should use scipy.spatial.distance.cdist or vectorized numpy |
| S20-5 | **P2-MEDIUM** | No test coverage for EpisodicHDBSCAN | 0 dedicated unit tests. Only tested indirectly via integration tests. Noise rescue, weak cluster creation, probability weighting all untested |
| S20-6 | **P3-LOW** | Infinity capping at 1e10 distorts hierarchy | HDBSCAN builds a minimum spanning tree. 1e10 values create artificial hierarchy levels. Should use `np.finfo(np.float64).max` or filter events before matrix construction |
| S20-7 | **P3-LOW** | Sentiment weighting only uses sentiment_score | `_create_cluster` weights sentiment by membership probability but ignores affect_valence, affect_arousal (MW v2 signals). sentiment_score is legacy P02 output |
| S20-8 | **P3-LOW** | EpisodeCluster output ignores MW v2 fields | EpisodeCluster has `activity_type_ultrabert`, `dominant_social_context`, `participants_json` fields, but HDBSCAN's `_create_cluster` does NOT populate them. Only `_build_episode_cluster` in R2 integrator fills them AFTER clustering |

### 20.5 Neuroscience Assessment: How the Hippocampus Actually Clusters

The hippocampus does not cluster memories using only two dimensions. Current neuroscience
(Eichenbaum, 2017; Davachi & DuBrow, 2015) identifies a **multi-dimensional binding process**
where episodic memories are organized along at least 6 axes:

**Axis 1: Semantic Content** (What happened)

- **Brain Region**: Perirhinal cortex -> CA1 via lateral entorhinal cortex
- **Current State**: embedding_768 cosine distance -- IMPLEMENTED
- **Adequacy**: Good for topic similarity, but misses hierarchical semantic structure
  (DIARY and GRATITUDE are more related than DIARY and FINANCE)

**Axis 2: Temporal Context** (When it happened)

- **Brain Region**: Time cells in CA1 (Eichenbaum, 2014), lateral entorhinal cortex
- **Current State**: Linear normalized time distance -- IMPLEMENTED but scientifically wrong
- **Problem**: The brain uses **logarithmic temporal compression** (Howard & Kahana, 2002).
  Events 5 minutes apart feel "same time". Events 1 hour apart feel "different time".
  Events 8 hours apart and 12 hours apart feel "equally distant". Current linear scaling
  treats 1 hour vs 2 hours the same as 3 hours vs 4 hours. Should be:
  `temporal_distance = log(1 + time_diff_ms / tau) / log(1 + max_gap_ms / tau)`
  where tau is a time constant (~30 minutes for episodic memory)

**Axis 3: Spatial Context** (Where it happened)

- **Brain Region**: Place cells and grid cells in hippocampus (O'Keefe & Moser, Nobel 2014)
- **Current State**: ~~NOT USED -- geohash hardcoded None in EventAdapter~~ **AVAILABLE** -- geohash_6 exposed by EventAdapter (GAP-002), but CompositeDistance does not yet consume it
- **Available Signal**: `P03EventState.geohash_6`, `location_name`, `location_type`
- **Impact**: A family dinner at home and a family dinner at a restaurant are DIFFERENT
  episodes despite identical semantic content. Place cells fire differently.

**Axis 4: Social Context** (Who was there)

- **Brain Region**: Medial prefrontal cortex, temporoparietal junction (Dunbar, 1998)
- **Current State**: NOT USED by HDBSCAN (only populated post-clustering by `_build_episode_cluster`). **Signals now AVAILABLE via EventAdapter (GAP-002)** but CompositeDistance does not yet consume them
- **Available Signals**: `social_context` (nuclear_family/solo/work), `social_intimacy` (HIGH/LOW),
  `participants_json`, `num_participants`
- **Impact**: "Told mom about promotion" and "told boss about promotion" are DIFFERENT
  episodes. The social brain hypothesis (Dunbar) says who-was-there is a primary memory
  organizer. These should cluster separately despite identical content.

**Axis 5: Emotional Valence & Arousal** (How it felt)

- **Brain Region**: Amygdala modulates hippocampal binding strength (McGaugh, 2004)
- **Current State**: NOT USED for clustering (only for sentiment aggregation post-clustering). **GAP-002 signals available**: `affect_valence`, `affect_arousal`, `affect_dominance` (full 3D VAD), `emotions_json`, `entity_salience_json`
- **Available Signals**: `affect_valence` [-1,1], `affect_arousal` [0,1], `salience_score`,
  `surprise_level`, `novelty` (ROUTINE/NOVEL/SURPRISING)
- **Impact**: Emotionally charged events create distinct episodes even within same context.
  "Got the job offer" (high arousal, positive valence) separates from "routine emails"
  (low arousal, neutral valence) even if 5 minutes apart. The amygdala literally tags
  these as different memory traces.

**Axis 6: Narrative/Goal Context** (Why it matters)

- **Brain Region**: Default mode network, ventromedial prefrontal cortex (Schacter et al., 2012)
- **Current State**: NOT USED. **GAP-002 signals available**: `narrative_thread_id`, `narrative_arc_position`, `narrative_is_goal_event`, `goal_context`, `temporal_orientation`, `identity_domains_json`, `identity_relevance`
- **Available Signals**: `narrative_thread_id`, `narrative_arc_position`, `narrative_is_goal_event`,
  `intent_type`, `goal_context`, `temporal_orientation` (PAST/ONGOING/FUTURE_COMMITMENT)
- **Impact**: Two events about "planning birthday party" should cluster even if 2 hours
  apart and interspersed with unrelated events. The narrative thread IS the episode.
  This is what Rubin (2006) calls the "narrative basic system" -- stories organize memory
  more powerfully than time or location.

### 20.6 The Fundamental Architecture Problem

The current design has a **separation of concerns problem** (~~blocking~~ **unblocked by GAP-002 EventAdapter fix, now an algorithm design task**): HDBSCAN clusters on 2 dimensions
(semantic + temporal), then `_build_episode_cluster` enriches the output with MW v2 signals
(social context, activity type, location, etc.). But these enrichment signals should be
**clustering inputs**, not post-hoc decorations.

```text
CURRENT (suboptimal -- EventAdapter blockade removed but CompositeDistance still 2D):
  [2D clustering] -> [post-hoc enrichment with 20+ available signals]
  "Here's a cluster based on what-and-when, now let me tell you who-where-why"

CORRECT (neuroscience-aligned):
  [6D clustering] -> [output already captures full episodic context]
  "Here's a cluster based on what-when-where-who-how-why"
```

The difference matters because post-hoc enrichment can produce incoherent episodes:

- Cluster has 3 events: 2 with social_context="nuclear_family", 1 with "work"
- Post-hoc: dominant_social_context = "nuclear_family" (majority vote)
- But the work event should never have been in this cluster in the first place

### 20.7 MW v2 Signal Enhancement: 6-Dimensional CompositeDistance (**SUPERSEDED** by Neuromorphic 6D Formula)

> **See**: temp_r2_design.md Subsystem 3 — final 6D formula with place_id-primary spatial (not just geohash), typed-relationship social Jaccard, full 3D VAD affective, and narrative short-circuit override. Weights refined from this initial proposal.

Replace the 2D CompositeDistance with a 6D distance function that aligns with hippocampal
binding dimensions:

**Proposed Enhanced Distance Formula**:

```text
d(i,j) = w_sem * cosine_distance(emb_i, emb_j)
        + w_tmp * log_temporal_distance(ts_i, ts_j)
        + w_spa * spatial_distance(geo_i, geo_j)
        + w_soc * social_distance(soc_i, soc_j)
        + w_aff * affective_distance(aff_i, aff_j)
        + w_nar * narrative_distance(nar_i, nar_j)

Default weights (from neuroscience literature):
  w_sem = 0.30  (semantic content -- perirhinal/entorhinal binding)
  w_tmp = 0.15  (temporal context -- time cells)
  w_spa = 0.10  (spatial context -- place/grid cells)
  w_soc = 0.15  (social context -- social brain network)
  w_aff = 0.10  (affective state -- amygdala modulation)
  w_nar = 0.20  (narrative thread -- default mode network)
  SUM  = 1.00

  NOTE: Neuromorphic Design (temp_r2_design.md) refines to:
  sem=0.25, tmp=0.15, spa=0.12, soc=0.15, aff=0.10, nar=0.23 (SUM=1.00)
```

**Dimension 1: Semantic Distance** (existing, keep)

```text
cosine_distance(emb_i, emb_j) = 1 - (emb_i . emb_j) / (||emb_i|| * ||emb_j||)
Range: [0, 2], typical: [0.05, 0.40] for UltraBERT
```

**Dimension 2: Log-Temporal Distance** (replace linear with logarithmic)

```text
log_temporal(ts_i, ts_j) = log(1 + |ts_i - ts_j| / tau) / log(1 + max_gap / tau)

tau = 1,800,000 ms (30 minutes)
max_gap = 14,400,000 ms (4 hours)

Example distances:
  5 min apart  -> 0.22 (vs linear: 0.035 -- current massively undercounts short gaps)
  30 min apart -> 0.50 (vs linear: 0.208)
  2h apart     -> 0.77 (vs linear: 0.500)
  4h apart     -> 1.00 (vs linear: 1.000)

Neuroscience: Howard & Kahana (2002) temporal context model. Recent events are
sharply separated; distant events are compressed. This matches how we experience
time in episodic memory.
```

**Dimension 3: Spatial Distance** (NEW -- uses geohash_6 or location_name)

```text
IF both events have geohash_6:
  spatial_distance = geohash_prefix_distance(geo_i, geo_j) / 6.0
  (normalized prefix character difference, range [0, 1])

ELIF both events have location_name:
  spatial_distance = 0.0 if same, 1.0 if different

ELSE:
  spatial_distance = 0.5 (unknown -- neutral contribution)

Signals: P03EventState.geohash_6, location_name, location_type
Requires: Fix EventAdapter to expose geohash_6
```

**Dimension 4: Social Distance** (NEW -- uses social_context, participants)

```text
social_distance = 1.0 - jaccard_similarity(participants_i, participants_j)

Fallback if no participant data:
  IF social_context matches: 0.0
  IF social_context differs: 1.0
  IF unknown: 0.5

Additional boost for social_intimacy:
  IF both HIGH intimacy and matching context: distance * 0.5 (tighter binding)

Signals: social_context, social_intimacy, participants_json, num_participants
Neuroscience: Dunbar (1998) -- social group composition is primary memory organizer
```

**Dimension 5: Affective Distance** (NEW -- uses affect_valence, affect_arousal)

```text
affective_distance = sqrt(
  (valence_i - valence_j)^2 / 4.0   # valence range [-1,1], so max diff = 2
  + (arousal_i - arousal_j)^2        # arousal range [0,1], so max diff = 1
) / sqrt(2)                           # normalize to [0, 1]

Novelty boost:
  IF one event is SURPRISING and other is ROUTINE:
    affective_distance = max(affective_distance, 0.8)  # Force separation

Signals: affect_valence, affect_arousal, novelty, surprise_level
Neuroscience: McGaugh (2004) -- emotional arousal modulates memory consolidation
via amygdala-hippocampal interaction. High-arousal events form distinct traces.
```

**Dimension 6: Narrative Distance** (NEW -- uses narrative_thread_id)

```text
IF both events have narrative_thread_id:
  IF same thread: 0.0 (same story = same episode, strongest possible binding)
  IF different thread: 1.0 (different story = different episode)

ELIF both events have temporal_orientation:
  IF same orientation: 0.3
  IF different orientation: 0.8

ELSE:
  narrative_distance = 0.5 (unknown)

Short-circuit rule:
  IF narrative_thread_id matches AND distance < 0.5: override to 0.0
  (Same conversation thread ALWAYS clusters together regardless of other dimensions)

Signals: narrative_thread_id, narrative_arc_position, temporal_orientation,
         intent_type, goal_context
Neuroscience: Rubin (2006) Basic Systems Model -- narrative is the primary
organizing system for autobiographical memory. A story thread binds events
across time and space.
```

### 20.8 Noise Rescue Enhancement: Context-Aware Rescue (**SUPERSEDED** by Neuromorphic 7-Signal Rescue)

> **See**: temp_r2_design.md Enhanced Noise Rescue — 7-channel rescue scoring (narrative [0.28] + social [0.18] + spatial [0.14] + semantic [0.14] + temporal [0.12] + activity [0.08] + entity [0.06]) with memory_tier-lowered threshold.

Current noise rescue uses two hardcoded thresholds (0.3 and 0.2). With MW v2 signals,
rescue can become context-aware:

**Current (blind rescue)**:

```text
IF outlier_score < 0.5 AND nearest_cluster_distance < 0.3:
  Rescue to nearest cluster
```

**Proposed (context-aware rescue)**:

```text
rescue_score = 0.0

# Semantic proximity (existing)
IF nearest_cluster_distance < 0.3: rescue_score += 0.25

# Narrative match (strongest signal)
IF noise_event.narrative_thread_id == nearest_cluster.dominant_thread:
  rescue_score += 0.35

# Social match
IF noise_event.social_context == nearest_cluster.dominant_social_context:
  rescue_score += 0.15

# Spatial match
IF noise_event.geohash_6[:4] == nearest_cluster.dominant_geohash[:4]:
  rescue_score += 0.10

# Temporal proximity (within 15 min of cluster boundary)
IF time_to_cluster_boundary < 15 minutes:
  rescue_score += 0.15

IF rescue_score >= 0.40:
  Rescue to nearest cluster
```

This prevents rescuing a work event into a family dinner cluster just because the
embeddings happen to be similar (both discuss "scheduling").

### 20.9 Performance Optimization: Vectorized Distance Matrix

The `build_distance_matrix` in composite_distance.py is the performance bottleneck:

**Current**: O(n^2) Python double-loop with per-pair numpy operations

```python
for i in range(n):
    for j in range(i + 1, n):
        dist = self.compute_from_arrays(embeddings[i], embeddings[j], ...)
```

**Proposed**: Vectorized computation using scipy and numpy broadcasting

```python
from scipy.spatial.distance import cdist

# Semantic: batch cosine distance (one call)
semantic_matrix = cdist(embedding_matrix, embedding_matrix, metric='cosine')

# Temporal: vectorized time distance
time_diffs = np.abs(timestamps[:, None] - timestamps[None, :])
temporal_matrix = np.log1p(time_diffs / tau) / np.log1p(max_gap / tau)
temporal_matrix = np.clip(temporal_matrix, 0.0, 1.0)

# Hard cutoff mask
hard_cutoff = time_diffs > max_gap_ms
temporal_matrix[hard_cutoff] = np.inf

# Weighted combination
distance_matrix = w_sem * semantic_matrix + w_tmp * temporal_matrix
# + spatial, social, affective, narrative matrices when enhanced
```

**Expected speedup**: 50-100x for batches of 100+ events. scipy.cdist uses optimized C/Fortran
for cosine distance computation. numpy broadcasting eliminates the Python loop entirely.

### 20.10 Cohesion Score Fix

Current cohesion mixes two independent measures:

```python
cohesion = cosine_similarity * avg_probability  # WRONG: conflates tightness with confidence
```

These should be reported separately:

```text
cohesion_score = mean pairwise cosine similarity within cluster (how tight)
membership_confidence = mean HDBSCAN probability (how certain the assignment)
cluster_strength = cohesion_score * membership_confidence (combined quality)
```

EpisodeCluster already has `cohesion_score`. Add `membership_confidence` as a new field
so downstream phases (R3 truth resolution, R4 social extraction) can use both signals
independently. A tight cluster with low confidence means "these events look similar but
HDBSCAN isn't sure they belong together" -- useful for R3 conflict detection.

### 20.11 Summary of Findings

| Dimension | Current State | Proposed Enhancement |
| --------- | ------------- | -------------------- |
| **Distance dimensions** | 2 (semantic + linear temporal) | 6 (semantic, log-temporal, spatial, social, affective, narrative) |
| **Temporal model** | Linear normalization | Logarithmic compression (Howard & Kahana 2002) |
| **Spatial input** | ~~None (EventAdapter blocks)~~ **Available** (GAP-002: `place_id`, `geohash_6`, `location_hierarchy_json`, `spatial_context_json`) | place_id primary (place cell) → geohash fallback (grid cell) → hierarchy → name |
| **Social input** | ~~None (post-hoc only)~~ **Available** (GAP-002: `participant_relationships_json`, `social_context`, `social_intimacy`) | Typed relationship Jaccard + social_context + intimacy modulation |
| **Affective input** | ~~None~~ **Available** (GAP-002: `affect_valence`, `affect_arousal`, `affect_dominance`, `emotions_json`) | Full 3D VAD + novelty/surprise + emotion overlap |
| **Narrative input** | ~~None~~ **Available** (GAP-002: `narrative_thread_id`, `narrative_arc_position`, `goal_context`) | narrative_thread_id match (strongest binding signal) + short-circuit override |
| **Noise rescue** | Hardcoded 0.3/0.2 thresholds | Context-aware multi-signal rescue scoring |
| **Cohesion metric** | cosine_sim * probability (conflated) | Separate cohesion_score + membership_confidence |
| **Performance** | O(n^2) Python loop | Vectorized scipy.cdist + numpy broadcasting (50-100x) |
| **Test coverage** | 0 dedicated tests | Need full unit test suite for HDBSCAN |
| **EventAdapter** | ~~Strips 34+ signals~~ **Exposes 20+ signals (GAP-002)** | ~~Must expose all MW v2 signals to algorithms~~ **DONE** |

**The single most impactful change**: Adding `narrative_thread_id` as a clustering dimension.
Two events on the same conversation thread should ALWAYS cluster together regardless of
time gap (within the 4-hour hard limit). This alone would fix the most common misclustering
pattern: interleaved conversations being merged into one mega-episode.

**The EventAdapter blockade** (documented in Section 18, S18-1) ~~affects HDBSCAN identically
to EpisodeSplitter. Fixing EventAdapter to expose MW v2 signals from P03EventState is the
prerequisite for ALL enhancements in this section. Without it, HDBSCAN remains a 2D clusterer
operating on 5% of available information.~~ **has been RESOLVED by GAP-002.** EventAdapter now
exposes 20+ signals. The remaining gap is that CompositeDistance formula still only consumes
2 dimensions (semantic + temporal). Extending to 6D (neuromorphic design) is the next step.

### 20.12 Neuroscience References

| # | Reference | Relevance to EpisodicHDBSCAN |
| - | --------- | ---------------------------- |
| 1 | Campello, R.J.G.B., Moulavi, D. & Sander, J. (2013). Density-Based Clustering Based on Hierarchical Density Estimates. PAKDD 2013, 160-172. | HDBSCAN algorithm paper: hierarchical density estimation, cluster tree extraction, outlier scoring |
| 2 | Eichenbaum, H. (2017). On the integration of space, time, and memory. Neuron, 95(5), 1007-1018. | Hippocampal binding: space, time, and content are integrated in CA1, not processed independently |
| 3 | Howard, M.W. & Kahana, M.J. (2002). A distributed representation of temporal context. Journal of Mathematical Psychology, 46(3), 269-299. | Temporal Context Model: logarithmic time compression in episodic memory. Recent events are sharply separated; distant events are compressed |
| 4 | Davachi, L. & DuBrow, S. (2015). How the hippocampus preserves order: the role of prediction and context. Trends in Cognitive Sciences, 19(2), 92-99. | Hippocampal sequence binding: prediction errors at event boundaries create new memory traces. Context shifts drive segmentation |
| 5 | McGaugh, J.L. (2004). The amygdala modulates the consolidation of memories of emotionally arousing experiences. Annual Review of Neuroscience, 27, 1-28. | Amygdala-hippocampal interaction: emotional arousal modulates memory consolidation strength. High-arousal events form distinct, stronger traces |
| 6 | Dunbar, R.I.M. (1998). The social brain hypothesis. Evolutionary Anthropology, 6(5), 178-190. | Social group composition is primary organizer of autobiographical memory. Who-was-there defines episode identity |
| 7 | Rubin, D.C. (2006). The Basic-Systems Model of Episodic Memory. Perspectives on Psychological Science, 1(4), 277-311. | Narrative, spatial, emotion, and sensory systems independently bind episodic memories. Narrative is the strongest organizer |
| 8 | Schacter, D.L., Addis, D.R. & Buckner, R.L. (2012). Remembering the past to imagine the future. Nature Reviews Neuroscience, 8, 657-661. | Default mode network supports both memory retrieval and future imagination via shared narrative/scene construction |
| 9 | Tulving, E. (2002). Episodic memory: from mind to brain. Annual Review of Psychology, 53, 1-25. | Foundational: episodic memory is multi-dimensional (what-where-when), binding requires all three |
| 10 | O'Keefe, J. & Moser, E.I. (2014). Nobel Prize Lecture: Place cells, grid cells, and memory. Nobel Foundation. | Place cells and grid cells encode spatial context. Different locations = different spatial firing patterns = different memory traces |

---

## 21. Algorithm Deep Trace: CentroidCalculator

**File**: `k0/modules/consolidation/algorithms/centroid_calculator.py` (614 lines)
**Role**: Computes weighted centroid embeddings for episode clusters -- the "representative memory" for each episode
**Called by**: `R2EpisodicIntegrator.run()` at line 434 via `self._centroid_calculator.compute(cluster_events, strategy=...)`
**Upstream**: EpisodicHDBSCAN produces clusters -> CentroidCalculator creates centroid per cluster
**Downstream**: Centroid stored as `EpisodeCandidate.centroid_embedding` -> R6/R7 persist to `st_vec` -> used for retrieval similarity search
**Tests**: 22 dedicated tests in `test_r2_centroid_calculator.py`

### 21.1 What CentroidCalculator Does

CentroidCalculator takes a list of events belonging to a single cluster and produces a **768-dimensional
L2-normalized centroid embedding** that represents the episode in vector space. This centroid is the
episode's "address" for future retrieval -- when searching "what happened at dinner last Tuesday?",
the query embedding is compared against episode centroids via cosine similarity.

The centroid is a **weighted average** of constituent event embeddings:

```text
centroid = sum(w_i * embedding_i) for all i, then L2-normalize

where w_i is determined by the weighting strategy
```

### 21.2 Data Flow: Input to Output

```text
HDBSCAN clusters events
    |
    v
R2 integrator loops over clusters (line 412-457)
    |
    v
For each cluster:
  cluster_events = [event_lookup[eid] for eid in member_ids]  # EventAdapter objects
    |
    v
  centroid_result = self._centroid_calculator.compute(
      cluster_events,
      strategy=self.config.weighting_strategy   # default: IMPORTANCE
  )
    |
    v
  CentroidResult {
      centroid: np.ndarray (768-dim, L2-normalized)
      variance: float (mean squared cosine distance from centroid)
      weights: np.ndarray (weight per event, sums to 1.0)
      strategy: str ("importance")
      event_count: int
  }
    |
    v
  cohesion = 1.0 / (1.0 + centroid_result.variance)   # line 440
    |
    v
  EpisodeCandidate {
      centroid_embedding: centroid_result.centroid
      variance: centroid_result.variance
      cohesion_score: cohesion
  }
    |
    v
  R6/R7: centroid_embedding -> st_vec table (pgvector HNSW index)
```

### 21.3 Weighting Strategies: What Exists

**CentroidableEvent Protocol** requires only:

- `event_id: str`
- `timestamp: int` (milliseconds)
- `embedding_768: Optional[List[float]]`
- `importance_score: float`

**Four strategies** (from Dossier C.3.2):

| Strategy | Formula | What it Captures |
| -------- | ------- | ---------------- |
| **UNIFORM** | `w_i = 1/n` | Equal contribution -- all events matter the same |
| **IMPORTANCE** | `w_i = importance_score_i + 0.01` | R1 importance weighting -- key events dominate |
| **RECENCY** | `w_i = (ts_i - ts_min) / (ts_max - ts_min) + 0.1` | Recent events dominate -- episode = latest state |
| **HYBRID** | `w_i = 0.7 * importance + 0.3 * recency` | Balanced: important recent events dominate |

**Default in R2Config**: `WeightingStrategy.IMPORTANCE` (line 102)

**Initialization**: `CentroidCalculator()` -- bare, no config, no strategy override at init (line 617 of R2 integrator)

### 21.4 Variance Computation

```python
def compute_variance(self, events, centroid):
    similarities = np.dot(emb_matrix, centroid)  # cosine since both L2-normalized
    distances = 1.0 - similarities
    variance = float(np.mean(distances ** 2))
```

**The variance is mean squared cosine distance from centroid**.

This variance feeds into R2 integrator's cohesion formula:

```python
cohesion = 1.0 / (1.0 + variance)   # line 440
```

Range: cohesion in (0.5, 1.0] for typical clusters (variance << 1.0 for real episodes)

### 21.5 EpisodeCandidate: The Staged Write Object

CentroidCalculator also defines `EpisodeCandidate` and `R2StagedOutput` -- the output containers
that carry episode data through R3-R7 without database writes:

```text
EpisodeCandidate fields:
  cluster_id, space_id, event_ids, event_count,
  centroid_embedding, centroid_embedding_id (set by R7),
  temporal_start, temporal_end,
  cohesion_score, variance, is_noise,
  dominant_sentiment, dominant_emotion,
  location_hint, activity_type, participants_json,
  title, summary, confidence_score
```

R2StagedOutput wraps a list of EpisodeCandidates with batch metrics.

**Note**: R2 integrator currently builds both `EpisodeCandidate` (line 442-455) and
`EpisodeCluster` (line 458 via `_build_episode_cluster`). These are **parallel representations**
of the same data. EpisodeCandidate is for staged writes; EpisodeCluster is for envelope
outputs. This duplication is a maintenance risk (Section 21.8, S21-5).

### 21.6 Correctness Audit

| ID | Severity | Finding | Evidence |
| -- | -------- | ------- | -------- |
| S21-1 | **P1-CRITICAL** | Centroid uses only semantic dimension -- ignores temporal, spatial, social, narrative | Centroid = weighted average of embedding_768 only. An episode spanning 4 hours gets a single embedding that loses all temporal structure. Events about different topics at different times collapse into one "average topic" vector |
| S21-2 | **P2-MEDIUM** | Importance weighting ignores MW v2 signals | Weights use only `importance_score` (from R1 heuristic). Ignores `salience_score` (MW v2 P02), `affect_arousal` (emotional intensity), `elaboration_depth` (MENTION vs DEEPLY_PROCESSED), `surprise_level` (novelty). An event the user mentioned in passing (MENTION) gets equal weight to one they wrote 500 words about (DEEPLY_PROCESSED) if importance_score happens to be similar |
| S21-3 | **P2-MEDIUM** | Recency weighting has linear bias toward latest event | `recency = (ts - ts_min) / (ts_max - ts_min)`. For a 4-hour episode, an event at 3h59m gets weight ~1.0, one at 0h01m gets ~0.0. The episode centroid is dominated by the last event. Should use a softer decay (e.g., exponential with half-life = episode_duration/3) |
| S21-4 | **P2-MEDIUM** | Variance formula assumes embeddings are pre-L2-normalized | `similarities = np.dot(emb_matrix, centroid)` treats dot product as cosine similarity. This is only correct if event embeddings AND centroid are L2-normalized. The centroid IS normalized (line 448), but emb_matrix from event.embedding_768 may NOT be. UltraBERT outputs are generally not L2-normalized. If norm(emb_i) != 1, then dot(emb_i, centroid) != cos_sim(emb_i, centroid) |
| S21-5 | **P3-LOW** | Dual output objects: EpisodeCandidate and EpisodeCluster | R2 creates both for each cluster. EpisodeCandidate carries centroid + variance but NOT emotion, location, activity_type, entity_ids. EpisodeCluster carries all enrichment but NOT centroid as numpy array. They duplicate event_ids, temporal bounds, cohesion, sentiment. Should be merged or one should reference the other |
| S21-6 | **P3-LOW** | `create_episode_candidate` method is dead code | The class has a `create_episode_candidate()` method (line 568) but R2 integrator does NOT call it -- it manually constructs `EpisodeCandidate` at line 442. The method uses `getattr(e, "sentiment_score", 0.0)` while R2 uses `e.event.sentiment_score`. Different access patterns for the same data |
| S21-7 | **P3-LOW** | `update_event_centroid_distances` not called by R2 | This method (line 553) sets per-event centroid distance. R2 integrator never calls it. Each event's distance from its cluster centroid is useful for outlier detection in R3 truth resolution, but is never computed |

### 21.7 Neuroscience Assessment: How the Brain Represents Episodes

A single 768-dimensional centroid embedding is a computationally convenient summary, but it
fundamentally misrepresents how the hippocampus stores episode representations.

**21.7.1 The Binding Problem in Centroid Space**

The hippocampus does not store a "weighted average" of experiences. It stores a **bound
representation** that preserves the relationship between constituent elements (Eichenbaum, 2017).
A centroid embedding collapses these relationships:

```text
Episode: "Dad picked up kids from school, stopped at grocery store, came home, made dinner"

Event embeddings capture:
  e1 = "school pickup" embedding
  e2 = "grocery store" embedding
  e3 = "arriving home" embedding
  e4 = "cooking dinner" embedding

Centroid = average(e1, e2, e3, e4) = "some blurry family-activities vector"

LOST: The temporal sequence (school -> store -> home -> dinner)
LOST: The causal chain (pickup -> needed groceries -> dinner requires cooking)
LOST: The spatial trajectory (school -> store -> home)
LOST: The emotional arc (stressed at school -> peaceful at home)
```

The centroid captures **topic** but loses **structure**. For retrieval this works tolerably
(searching "family evening activities" will match the average vector), but for understanding
the episode it fails catastrophically.

**21.7.2 Temporal Context in Memory Representation**

Howard & Kahana (2002) Temporal Context Model shows that memories are not stored as isolated
points but as **context vectors that drift over time**. The "beginning" and "end" of an episode
feel qualitatively different in memory. A single centroid loses this:

```text
Human memory of "dinner party":
  - Arrival (anticipation, seeing friends)
  - Main course (lively conversation)
  - Dessert (winding down, feeling full)

These are NOT a single point in memory space -- they form a TRAJECTORY.
The brain can distinguish "early dinner" from "late dinner" queries.
A centroid collapses this into one point.
```

**21.7.3 Emotional Modulation of Memory Strength**

McGaugh (2004) shows the amygdala modulates memory consolidation: emotionally arousing events
are remembered better. The current importance_score weighting partially captures this (R1 boosts
importance for emotional content), but misses the specific signals:

- `affect_arousal` [0,1]: Direct measure of emotional intensity
- `surprise_level` [0,1]: Prediction error signal -- the brain pays more attention to surprises
- `elaboration_depth` (MENTION/DISCUSSED/ELABORATED/DEEPLY_PROCESSED): The user's own
  investment of attention in describing the event

An event marked DEEPLY_PROCESSED with high arousal should dominate the centroid far more
than a routine MENTION, regardless of what R1 importance says.

**21.7.4 The Salience Signal**

MW v2 Module M06 produces `salience_score` -- a P02-computed estimate of how important this
event is to the user's life. This is a richer signal than R1's heuristic `importance_score`
because it considers:

- Emotional intensity (affect_valence, affect_arousal)
- Personal relevance (identity_domains)
- Novelty (surprise_level, novelty category)
- Social significance (social_context, num_participants)
- Temporal orientation (future commitments > routine past events)

Using `salience_score` instead of or alongside `importance_score` for centroid weighting
would produce centroids that represent what matters to the user, not just what R1's
simple heuristic flagged.

### 21.8 MW v2 Enhancement: Multi-Signal Weighting Strategy (**SUPERSEDED** by Neuromorphic Subsystem 4: 7-Factor Encoding Weight)

> **See**: temp_r2_design.md Subsystem 4 — encoding_weight = salience [0.25] + elaboration [0.20] + identity_relevance [0.15] + arousal_boost [0.15] + memory_tier [0.10] + recency [0.10] + hdbscan_probability [0.05]. This incorporates and refines the SALIENCE_COMPOSITE proposal below.

Replace the 4 simple weighting strategies with a **salience-aware composite weight**
that uses MW v2 signals:

**Proposed: SALIENCE_COMPOSITE Strategy**

```text
w_i = alpha * salience_score_i         # How important P02 thinks this is
    + beta  * arousal_boost_i           # Emotional intensity amplification
    + gamma * elaboration_weight_i      # User's own attention investment
    + delta * recency_decay_i           # Soft temporal decay
    + MIN_WEIGHT                        # Floor to prevent zero weights

Normalize: w_i = w_i / sum(w_j)

Default coefficients:
  alpha = 0.35  (salience is primary driver)
  beta  = 0.20  (emotional events should dominate)
  gamma = 0.25  (user's investment is a strong signal)
  delta = 0.20  (recent still matters but softer)
```

**Component definitions**:

```text
salience_score_i:
  Direct from P03EventState.salience_score [0, 1]
  Fallback: importance_score if salience not available (trust-then-fill)

arousal_boost_i:
  = affect_arousal * (1 + abs(affect_valence))
  Range: [0, 2]
  Rationale: High arousal + strong valence (positive or negative) = memorable
  Fallback: 0.5 if affect signals missing

elaboration_weight_i:
  MENTION           -> 0.2
  DISCUSSED         -> 0.5
  ELABORATED        -> 0.8
  DEEPLY_PROCESSED  -> 1.0
  Unknown/empty     -> 0.5
  Rationale: The user wrote more about events that matter to them.
  This is a DIRECT MEASURE of subjective importance.

recency_decay_i:
  = exp(-lambda * (ts_max - ts_i) / episode_duration)
  lambda = 1.5 (half-life at ~46% of episode duration)
  Range: [exp(-1.5), 1.0] = [0.22, 1.0]
  Rationale: Exponential decay is more natural than linear.
  Recent events are privileged but not overwhelmingly so.
```

### 21.9 MW v2 Enhancement: Multi-Centroid Episode Representation

A single centroid is fundamentally lossy. For richer episode representation,
compute **multiple centroids** that capture the episode's internal structure:

**Proposed: EpisodeCentroidSet**

```text
EpisodeCentroidSet {
    primary_centroid: np.ndarray       # Weighted average (current behavior, improved weights)
    temporal_start_centroid: np.ndarray # Average of first 30% of events (how episode began)
    temporal_end_centroid: np.ndarray   # Average of last 30% of events (how episode ended)
    emotional_peak_centroid: np.ndarray # Average of top-3 highest arousal events
    narrative_centroid: np.ndarray      # Average of events with same narrative_thread_id as majority

    variance: float                    # From primary centroid
    emotional_range: float             # Distance between most positive and most negative events
    temporal_drift: float              # Distance between start and end centroids
}
```

**Why this matters for retrieval**:

- Query "how did dinner start?" -> match against `temporal_start_centroid`
- Query "what was the emotional high point?" -> match against `emotional_peak_centroid`
- Query "evening activities" -> match against `primary_centroid` (current behavior)
- The `temporal_drift` value tells downstream phases whether this episode
  was a single consistent topic (low drift) or a journey across topics (high drift)

**Storage cost**: 5 x 768 = 3,840 floats per episode vs current 768.
At 4 bytes each = 15KB per episode vs 3KB. For 1000 episodes = 15MB.
Negligible cost for dramatically richer retrieval.

### 21.10 MW v2 Enhancement: Membership-Weighted Centroid (**INCORPORATED** into Neuromorphic Subsystem 4 as hdbscan_probability factor [w=0.05])

HDBSCAN produces `probabilities` per event (0.0 = barely belongs, 1.0 = definitely belongs).
CentroidCalculator currently ignores these probabilities entirely.

**Proposed: Probability-Augmented Weighting**

```text
w_i_final = w_i_strategy * probability_i^kappa

where:
  w_i_strategy = weight from chosen strategy (importance, salience_composite, etc.)
  probability_i = HDBSCAN membership probability for event i
  kappa = 0.5 (square root -- softens the effect so low-probability events still contribute)
```

This means noise-rescued events (which have lower HDBSCAN probability by definition)
contribute less to the centroid than core cluster members. The centroid represents
the "heart" of the episode, not its fringes.

**Implementation requirement**: CentroidCalculator.compute() must accept an optional
`probabilities: np.ndarray` parameter. R2 integrator passes it from
`HDBSCANClusteringResult.probabilities` for the relevant cluster members.

### 21.11 Performance Notes

CentroidCalculator is **already well-optimized**:

- `np.stack` + broadcasting for weighted sum: O(n * 768), vectorized
- `np.dot(emb_matrix, centroid)` for variance: O(n * 768), vectorized
- L2 normalization: O(768), negligible

**One fix needed**: Variance computation should normalize event embeddings before
dot product, or explicitly compute cosine similarity:

```python
# Current (assumes L2-normalized embeddings):
similarities = np.dot(emb_matrix, centroid)

# Correct (handles un-normalized embeddings):
norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
norms = np.clip(norms, 1e-10, None)
normalized = emb_matrix / norms
similarities = np.dot(normalized, centroid)  # centroid already L2-normalized
```

### 21.12 Summary of Findings

| Dimension | Current State | Proposed Enhancement |
| --------- | ------------- | -------------------- |
| **Weighting signals** | importance_score only (R1 heuristic) | salience_score (P02), affect_arousal, elaboration_depth, exponential recency |
| **Weighting strategy** | 4 strategies (uniform, importance, recency, hybrid) | Add SALIENCE_COMPOSITE using MW v2 signals |
| **Episode representation** | Single 768-dim centroid | Multi-centroid set (primary, start, end, emotional peak, narrative) |
| **HDBSCAN integration** | Ignores membership probabilities | Probability-augmented weighting (core members dominate centroid) |
| **Variance formula** | Assumes L2-normalized embeddings | Explicit normalization before cosine similarity |
| **Recency model** | Linear (latest event gets ~1.0) | Exponential decay (half-life at 46% of episode duration) |
| **Dead code** | `create_episode_candidate()` unused, `update_event_centroid_distances()` uncalled | Remove or wire into pipeline |
| **Dual output** | EpisodeCandidate + EpisodeCluster parallel objects | Merge or reference to eliminate duplication |

**The single most impactful change**: Adding `elaboration_depth` to centroid weighting.
When a user writes 500 words about a single event in an episode, that event IS the episode
from the user's perspective. The centroid should be pulled toward that event's embedding.
This is direct evidence of subjective importance -- stronger than any heuristic score.

**The EventAdapter blockade** (Section 18, S18-1) ~~affects CentroidCalculator indirectly.~~ **is RESOLVED (GAP-002).**
CentroidCalculator accesses events via `CentroidableEvent` protocol which only requires
`event_id`, `timestamp`, `embedding_768`, `importance_score`. To use MW v2 signals
(salience_score, affect_arousal, elaboration_depth), either:

1. Extend `CentroidableEvent` protocol with new properties, or
2. Pass MW v2 signals as a separate weights array from R2 integrator

Option 2 is cleaner: R2 integrator already has access to `e.event.*` (full P03EventState).
Compute the composite weight in R2, pass as array to CentroidCalculator.

### 21.13 Neuroscience References

| # | Reference | Relevance to CentroidCalculator |
| - | --------- | ------------------------------- |
| 1 | Eichenbaum, H. (2017). On the integration of space, time, and memory. Neuron, 95(5), 1007-1018. | Episodes are bound representations, not averaged vectors. Centroid loses relational structure between events |
| 2 | Howard, M.W. & Kahana, M.J. (2002). A distributed representation of temporal context. Journal of Mathematical Psychology, 46(3), 269-299. | Temporal context drifts across episode. Single centroid collapses beginning/middle/end into one point |
| 3 | McGaugh, J.L. (2004). The amygdala modulates the consolidation of memories. Annual Review of Neuroscience, 27, 1-28. | Emotional arousal modulates memory strength -- high arousal events should receive higher centroid weight |
| 4 | Craik, F.I.M. & Lockhart, R.S. (1972). Levels of processing: A framework for memory research. Journal of Verbal Learning and Verbal Behavior, 11(6), 671-684. | Deeper processing = stronger memory trace. elaboration_depth directly measures processing depth |
| 5 | Tulving, E. & Thomson, D.M. (1973). Encoding specificity and retrieval processes in episodic memory. Psychological Review, 80(5), 352-373. | Retrieval depends on encoding context match. Multi-centroid representation preserves more encoding contexts for retrieval matching |
| 6 | Conway, M.A. & Pleydell-Pearce, C.W. (2000). The construction of autobiographical memories in the self-memory system. Psychological Review, 107(2), 261-288. | Autobiographical memories are hierarchical (lifetime period > general event > specific event). Episode centroid should reflect user's own emphasis, not uniform averaging |

---

## 22. Algorithm Deep Trace: EpsAdjuster

**File**: `k0/modules/consolidation/algorithms/eps_adjuster.py` (406 lines)
**Role**: Adaptive per-space learning of DBSCAN/HDBSCAN eps parameter via silhouette feedback
**Called by**: `R2EpisodicIntegrator._track_quality_and_adjust()` at line 1474
**Upstream**: ClusterQualityTracker produces silhouette + singleton rate -> EpsAdjuster uses them
**Downstream**: Adjusted eps persisted to `st_learned_weights` via `ctx.syscalls.set_learned_param`
**Tests**: 15 dedicated tests in `test_r2_eps_adjuster.py`

### 22.1 Algorithm Description

EpsAdjuster implements a **closed-loop control system** for the eps parameter. eps controls
how tight or loose clusters are -- lower eps = tighter clusters (fewer events per cluster),
higher eps = looser clusters (more events merged). The adjuster observes clustering quality
after each P03 cycle and nudges eps in the right direction.

**Control loop**:

```text
R2 clustering -> ClusterQualityTracker (observe) -> EpsAdjuster (adjust) -> next R2 cycle
                                                        |
                                                        v
                                               st_learned_weights (persist)
```

### 22.2 Adjustment Algorithm

```text
Input: current_eps, silhouette_score, avg_cluster_size, singleton_rate, total_clusters_formed

Step 1 -- Cold Start Guard
  IF total_clusters_formed < 100:
    SKIP (not enough data to learn)

Step 2 -- Quality Check
  IF silhouette_score >= 0.5 AND avg_cluster_size <= 10:
    SKIP (quality acceptable, clusters right-sized)

Step 3 -- Direction Decision
  IF avg_cluster_size > 10.0:
    eps_adjusted = eps - 0.02  (clusters too loose, tighten)
  ELIF singleton_rate > 0.20:
    eps_adjusted = eps + 0.02  (too much noise, loosen)
  ELSE:
    SKIP (neither condition met)

Step 4 -- Momentum Smoothing
  eps_new = 0.9 * eps_old + 0.1 * eps_adjusted
  (90% old value + 10% adjustment to prevent oscillation)

Step 5 -- Bounds Clamping
  eps_final = clamp(eps_new, 0.15, 0.40)
```

### 22.3 Configuration

```text
EpsAdjustmentConfig:
  eps_min:               0.15   (tightest allowed clustering)
  eps_max:               0.40   (loosest allowed clustering)
  eps_step:              0.02   (adjustment per cycle)
  silhouette_target:     0.5    (quality threshold)
  momentum:              0.9    (smoothing factor)
  cold_start_threshold:  100    (clusters before learning starts)
  avg_cluster_size_high: 10.0   (above = too loose)
  singleton_rate_high:   0.20   (above = too much noise)
```

### 22.4 Correctness Audit

| ID | Severity | Finding | Evidence |
| -- | -------- | ------- | -------- |
| S22-1 | **P1-CRITICAL** | EpsAdjuster is a DBSCAN concept -- largely irrelevant to HDBSCAN | HDBSCAN does NOT use eps for clustering. It builds a hierarchy and extracts stable clusters at multiple density levels. The cluster_selection_epsilon in HDBSCAN serves a completely different purpose (flat-cut on the cluster tree) than DBSCAN eps (neighborhood radius). Tuning eps for HDBSCAN is at best unnecessary, at worst counterproductive |
| S22-2 | **P2-MEDIUM** | Silhouette score is ~~approximated~~ **faked** (avg cohesion != silhouette) | R2 integrator line 1449 computes batch_silhouette as average of cohesion_scores -- which is NOT silhouette. Silhouette measures both intra-cluster cohesion AND inter-cluster separation. Cohesion only measures internal tightness. **This drives the entire adaptive learning loop on a wrong metric** |
| S22-3 | **P2-MEDIUM** | Step size is fixed at 0.02 regardless of error magnitude | If silhouette is 0.01 (terrible) vs 0.45 (almost good), the adjustment is the same 0.02. Proportional control would converge faster |
| S22-4 | **P2-MEDIUM** | Only two input signals (avg_cluster_size, singleton_rate) | Does not consider cluster count, temporal span, MW v2 signal coherence within clusters |
| S22-5 | **P3-LOW** | Cold start threshold of 100 is arbitrary | No basis for why 100 clusters. A space producing 2 clusters per cycle needs 50 cycles before learning starts |
| S22-6 | **P3-LOW** | No learning rate decay | After 1000 cycles the adjustment magnitude is the same as after 100. Mature spaces should converge and stabilize |

### 22.5 Neuroscience Assessment: Does the Brain Tune Its Own Clustering?

Yes -- but not like this.

**Neuromodulatory Gating** (Hasselmo, 2006): The hippocampus has two operational modes
controlled by acetylcholine (ACh) levels:

- **High ACh** (during active experience): Pattern separation mode -- incoming events
  are kept distinct, preventing interference. Analogous to LOW eps (tight clustering).
- **Low ACh** (during consolidation/sleep): Pattern completion mode -- related memories
  are merged and generalized. Analogous to HIGH eps (loose clustering).

The brain does not tune a single parameter -- it shifts between two fundamentally different
modes based on context. EpsAdjuster's gradual nudging is more like a thermostat than a brain.

**Prediction Error Signal**: The brain adjusts memory encoding strength based on prediction
error (Rescorla-Wagner model). When events violate expectations (high surprise_level), the
brain increases encoding specificity (lower eps equivalent). When events match predictions
(low surprise), encoding is more general (higher eps equivalent). EpsAdjuster ignores this.

### 22.6 MW v2 Enhancement: Context-Aware Eps (**DEPRIORITIZED** — eps is a DBSCAN concept; HDBSCAN auto-tunes via hierarchy)

> **Note**: The Neuromorphic Design uses HDBSCAN natively without eps tuning. Context-aware batch modulation may still apply to `cluster_selection_epsilon` but is lower priority than the 6D distance function.

Instead of a single per-space eps, use MW v2 signals to modulate eps per-batch:

**Proposed: Dynamic Eps Based on Batch Characteristics**

```text
base_eps = learned_per_space_eps  (from EpsAdjuster, current behavior)

# Modulation factors
novelty_factor = mean(surprise_level for events in batch)
arousal_factor = mean(affect_arousal for events in batch)
thread_diversity = count(unique narrative_thread_ids) / count(events)

# High novelty -> tighter clustering (separate novel events)
novelty_mod = 1.0 - 0.3 * novelty_factor   # [0.7, 1.0]

# High arousal -> tighter clustering (emotional events are distinct)
arousal_mod = 1.0 - 0.2 * arousal_factor    # [0.8, 1.0]

# High thread diversity -> tighter clustering (many stories = many episodes)
diversity_mod = 1.0 - 0.3 * thread_diversity # [0.7, 1.0]

effective_eps = base_eps * novelty_mod * arousal_mod * diversity_mod
effective_eps = clamp(effective_eps, eps_min, eps_max)
```

This mirrors ACh gating: routine batches get higher eps (merge aggressively), while
surprising emotional multi-thread batches get lower eps (keep episodes distinct).

### 22.7 MW v2 Enhancement: Replace Silhouette Approximation (**SUPERSEDED** by Neuromorphic EpisodicCoherenceScore)

> **See**: temp_r2_design.md Enhanced Quality Assessment — 7-dimension episodic coherence: narrative [0.25] + social [0.20] + spatial [0.15] + true_silhouette [0.15] + temporal [0.10] + affective [0.10] + identity [0.05].

The fake silhouette score should be replaced with either:

**Option A**: True silhouette using sklearn.metrics.silhouette_score with the precomputed
distance matrix (cost: O(n^2) already paid for building distance_matrix -- free).

**Option B**: Multi-dimensional quality metric using MW v2 signals:

```text
quality = 0.25 * silhouette (true)
        + 0.25 * narrative_coherence (% events with same narrative_thread_id)
        + 0.20 * social_coherence (% events with same social_context)
        + 0.15 * temporal_compactness (1 - normalized_duration / max_gap)
        + 0.15 * activity_coherence (% events with same activity_type_ultrabert)
```

---

## 23. Algorithm Deep Trace: MinSamplesAdjuster

**File**: `k0/modules/consolidation/algorithms/min_samples_adjuster.py` (369 lines)
**Role**: Adaptive per-space learning of min_samples parameter via singleton rate feedback
**Called by**: `R2EpisodicIntegrator._track_quality_and_adjust()` at line 1506
**Upstream**: ClusterQualityTracker produces singleton rate -> MinSamplesAdjuster uses it
**Downstream**: Adjusted min_samples persisted to `st_learned_weights`
**Tests**: 11 dedicated tests in `test_r2_min_samples_adjuster.py`

### 23.1 Algorithm Description

MinSamplesAdjuster controls the **density threshold** for cluster formation. min_samples
is the minimum number of events within an eps-neighborhood required for a point to be
a core point. Higher min_samples = stricter density = fewer clusters.

```text
Input: current_min_samples, singleton_rate

IF singleton_rate > 0.20:
  min_samples = min(5, current + 1)  (too noisy, increase threshold)

ELIF singleton_rate < 0.05:
  min_samples = max(2, current - 1)  (too strict, decrease threshold)

ELSE:
  No change (5-20% singleton rate = good balance)

Bounds: min_samples in [2, 5]
```

Key difference from EpsAdjuster: No momentum smoothing. Changes are immediate (+1 or -1)
because min_samples is integer-valued with tiny range [2, 5].

### 23.2 Correctness Audit

| ID | Severity | Finding | Evidence |
| -- | -------- | ------- | -------- |
| S23-1 | **P1-CRITICAL** | min_samples has different semantics in HDBSCAN vs DBSCAN | In DBSCAN, min_samples is the core point threshold. In HDBSCAN, it controls mutual reachability distance smoothing. With HDBSCAN as default, tuning min_samples as if it were DBSCAN is incorrect |
| S23-2 | **P2-MEDIUM** | Only one input signal (singleton_rate) | Does not consider silhouette, cluster count, cluster size distribution, or MW v2 coherence |
| S23-3 | **P2-MEDIUM** | No distinction between good noise and bad noise | Some singletons SHOULD be noise (genuinely unique events). Others are misclustered. MW v2 can distinguish: ROUTINE event as noise = bad (should cluster). SURPRISING event as noise = acceptable (genuinely unique) |
| S23-4 | **P3-LOW** | Only 4 possible values {2, 3, 4, 5} | Very coarse control with minimal parameter space |
| S23-5 | **P3-LOW** | No cold start guard unlike EpsAdjuster | Adjusts from first cycle. With small batches, singleton_rate is noisy |

### 23.3 Neuroscience Assessment: Density Thresholds in Memory

The brain's encoding threshold is not a fixed count. It is modulated by:

1. **Attention** (elaboration_depth): Deeply processed events have lower encoding threshold
2. **Emotional arousal** (affect_arousal): High-arousal events have lower threshold (amygdala facilitation)
3. **Novelty** (surprise_level): Novel events capture attention and lower threshold
4. **Goal relevance** (narrative_is_goal_event): Goal-related events are preferentially encoded

### 23.4 MW v2 Enhancement: Weighted Density Instead of Count

**Proposed: Replace integer min_samples with weighted density threshold**

```text
Current: cluster forms IF count(events within eps) >= min_samples

Proposed: cluster forms IF sum(encoding_weight_i) >= density_threshold

where encoding_weight_i =
    0.30 * salience_score_i
  + 0.25 * elaboration_map[elaboration_depth_i]
  + 0.25 * affect_arousal_i
  + 0.20 * surprise_level_i

elaboration_map:
  MENTION           -> 0.2
  DISCUSSED         -> 0.5
  ELABORATED        -> 0.8
  DEEPLY_PROCESSED  -> 1.0
```

Two DEEPLY_PROCESSED high-salience events (weight ~1.5 each, total ~3.0) form a cluster.
Three routine MENTIONs (weight ~0.3 each, total ~0.9) may not. Density reflects cognitive
significance, not just event count.

---

## 24. Algorithm Deep Trace: ClusterQualityTracker

**File**: `k0/modules/consolidation/algorithms/cluster_quality.py` (522 lines)
**Role**: Closed-loop quality metrics: silhouette, grounding, correction, singleton rates + composite score
**Called by**: `R2EpisodicIntegrator._track_quality_and_adjust()` at line 1462
**Upstream**: R2 output (batch_silhouette, cluster_count, noise_count) + K1 feedback signals
**Downstream**: Feeds EpsAdjuster and MinSamplesAdjuster; persists to `st_consolidation_audit`
**Tests**: 20 dedicated tests in `test_r2_cluster_quality.py`

### 24.1 Quality Signals and Composite Formula

```text
composite = 0.40 * silhouette       # Cluster geometry
          + 0.30 * grounding_rate   # K1 usage
          + 0.20 * (1 - correction) # User feedback
          + 0.10 * (1 - singleton)  # Noise level

Range: [0, 1], target > 0.5
```

| Signal | Weight | Source | Status |
| ------ | ------ | ------ | ------ |
| Silhouette | 0.40 | R2 (~~approximated as avg cohesion~~ **FAKED: avg(cohesion) != silhouette**) | **FAKED** -- see Section 24.4 impact chain |
| Grounding Rate | 0.30 | st_feedback_signals CLUSTER_GROUNDED | PHANTOM (K1 not emitting) |
| Correction Rate | 0.20 | st_feedback_signals CLUSTER_WRONG | PHANTOM (UI not built) |
| Singleton Rate | 0.10 | R2 noise count | REAL |

### 24.2 Alert System

```text
IF silhouette < 0.3 for 3 consecutive cycles:
  RAISE "CLUSTER_QUALITY_DEGRADED" alert
```

### 24.3 Correctness Audit

| ID | Severity | Finding | Evidence |
| -- | -------- | ------- | -------- |
| S24-1 | **P1-CRITICAL** | Silhouette score is FAKED -- **entire adaptive loop broken** | R2 integrator line 1449: batch_silhouette = avg(cohesion_scores). This is NOT silhouette. Silhouette measures both cohesion AND separation. Average cohesion only measures internal tightness. The fake silhouette drives BOTH EpsAdjuster and MinSamplesAdjuster. **The entire adaptive learning loop is based on a wrong metric -- see Section 24.4 for full impact chain** |
| S24-2 | **P2-MEDIUM** | Grounding rate always 0.0 | K1 does not emit CLUSTER_GROUNDED signals. 30% of composite formula is dead |
| S24-3 | **P2-MEDIUM** | Correction rate always 0.0 | User correction UI not built. 0.20 * (1 - 0.0) = 0.20 constant inflates quality |
| S24-4 | **P2-MEDIUM** | Silhouette normalization double-maps | normalized_silhouette = (sil + 1.0) / 2.0 maps [-1,1] to [0,1]. But input is already [0,1] (avg cohesion). So it maps [0,1] to [0.5,1.0], compressing range and inflating score |
| S24-5 | **P3-LOW** | Alert threshold 0.3 unreachable with fake silhouette | Fake silhouette (avg cohesion) is typically 0.7-0.99. Alert never triggers |
| S24-6 | **P3-LOW** | No MW v2 quality signals | Ignores narrative, social, activity, spatial coherence |

### 24.4 The Fake Silhouette Problem: Full Impact Chain

```text
Source of fake silhouette:
  cohesion = 1.0 / (1.0 + variance)
  variance = mean((1 - cos_sim)^2) ≈ 0.003-0.02 for real clusters
  -> cohesion ≈ 0.98-0.997
  -> batch_silhouette ≈ 0.98 (always near 1.0)

Impact on EpsAdjuster:
  silhouette >= 0.5 is ALWAYS TRUE (fake value ~0.98)
  -> Adjuster almost NEVER fires
  -> eps stays at default forever
  -> Adaptive learning is effectively DEAD

Impact on ClusterQualityTracker composite:
  normalized = (0.98 + 1.0) / 2.0 = 0.99
  composite ≈ 0.40*0.99 + 0.30*0.0 + 0.20*1.0 + 0.10*(1-singleton)
           ≈ 0.60-0.70 regardless of actual quality
  -> Quality appears "acceptable" even with terrible episodes
  -> Alert threshold (0.3) NEVER triggers

The entire adaptive learning subsystem is a CLOSED LOOP WITH A BROKEN SENSOR.
```

### 24.5 MW v2 Enhancement: EpisodicCoherenceScore (**ALIGNED** with Neuromorphic Enhanced Quality Assessment — weights refined)

> **See**: temp_r2_design.md Enhanced Quality Assessment. The neuromorphic design builds on this proposal with 7 dimensions (adds identity_coherence) and refined weights.

Replace fake silhouette + phantom signals with quality assessment using MW v2 signals
available NOW:

```text
For each cluster, compute coherence across MW v2 dimensions:

narrative_coherence = fraction sharing majority narrative_thread_id
social_coherence    = fraction sharing majority social_context
activity_coherence  = fraction sharing majority activity_type_ultrabert
spatial_coherence   = fraction sharing first 4 chars of geohash_6
temporal_compactness = 1.0 - (episode_duration / max_gap_hours)
affect_coherence    = 1.0 - stddev(affect_valence) / 2.0

Batch episodic_coherence = mean across clusters of:
    0.25 * narrative_coherence
  + 0.20 * social_coherence
  + 0.20 * activity_coherence
  + 0.15 * temporal_compactness
  + 0.10 * spatial_coherence
  + 0.10 * affect_coherence
```

### 24.6 MW v2 Enhancement: Replace Composite Formula (**SUPERSEDED** by Neuromorphic EpisodicCoherenceScore)

**Current** (with fake/phantom signals):

```text
composite ≈ 0.40 * 0.98 + 0.30 * 0.0 + 0.20 * 1.0 + 0.10 * (1-singleton) ≈ 0.65 always
```

**Proposed** (all signals available NOW):

```text
composite = 0.30 * true_silhouette
          + 0.30 * episodic_coherence
          + 0.20 * narrative_coverage
          + 0.10 * cluster_size_entropy
          + 0.10 * (1 - singleton_rate)
```

### 24.7 Combined Summary: Adaptive Learning Subsystem

| Component | Status | Core Problem |
| --------- | ------ | ------------ |
| ClusterQualityTracker | **Broken input** | Silhouette **FAKED** (~0.98 always), grounding and correction phantom (always 0.0). **Entire quality assessment unreliable** |
| EpsAdjuster | **Effectively dead** | Fake silhouette always passes quality check -> adjuster **never fires** -> eps stuck at default forever |
| MinSamplesAdjuster | Partially working | Uses singleton_rate (real signal) but blind to WHY noise occurs |

**Fix priority**:

1. Compute real silhouette using sklearn with precomputed distance matrix (free)
2. Add MW v2 coherence metrics as quality signals
3. Re-evaluate eps relevance for HDBSCAN (different semantics)
4. Implement weighted density for min_samples
5. Wire K1 feedback when available for grounding_rate

### 24.8 Neuroscience References (Sections 22-24)

| # | Reference | Relevance |
| - | --------- | --------- |
| 1 | Hasselmo, M.E. (2006). The role of acetylcholine in learning and memory. Current Opinion in Neurobiology, 16(6), 710-715. | ACh gating: high ACh = pattern separation (tight clustering), low ACh = pattern completion (loose clustering). Context-dependent eps modulation |
| 2 | Rescorla, R.A. & Wagner, A.R. (1972). A theory of Pavlovian conditioning. In Classical Conditioning II, 64-99. | Prediction error drives learning rate. surprise_level should modulate clustering parameters |
| 3 | Karpicke, J.D. & Roediger, H.L. (2008). The critical importance of retrieval for learning. Science, 319(5865), 966-968. | Retrieval success is best memory quality metric. grounding_rate (when implemented) is the right signal |
| 4 | Nader, K., Schafe, G.E. & LeDoux, J.E. (2000). Fear memories require protein synthesis for reconsolidation. Nature, 406(6797), 722-726. | Reconsolidation: user corrections = memory update events. correction_rate is neurologically valid |
| 5 | Craik, F.I.M. & Lockhart, R.S. (1972). Levels of processing. Journal of Verbal Learning and Verbal Behavior, 11(6), 671-684. | Encoding threshold modulated by processing depth. elaboration_depth should influence density threshold |

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
