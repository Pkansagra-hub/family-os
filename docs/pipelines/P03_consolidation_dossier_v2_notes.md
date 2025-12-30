<!-- markdownlint-disable MD041 -->

## P03 Consolidation Dossier v2 — Working Notes (for Implementation Planning)

> **Source**: `docs/pipelines/P03_consolidation_dossier_v2.md`
> **Method**: Notes taken in 4k-line increments, updated sequentially.
> **Audience**: Engineering planning (pipeline wiring, modules, contracts, storage, testing, ops).
> **Important**: These notes intentionally emphasize *what must exist* to implement P03 end-to-end, including dynamic learning/weight updates—not just phase execution.

---

## Notes for Lines 1–4000

### 1) What P03 is (core intent)

- P03 is **Memory Consolidation & Forgetting**.
- **v2 core shift**: consolidation is **bidirectional truth reconciliation**.
  - The 8 memory layers are considered **TRUTH**.
  - New signals from P02 (in `st_hipp_events`) are **candidates**.
  - Every candidate must be reconciled *against existing truth* before writing.

### 2) Reconciliation decision model (must implement)

- Decisions:
  - **REINFORCE**: strong match, boost confidence/observation_count, refresh last_observed, reset decay.
  - **EXTEND**: partial match, add details / update context.
  - **CREATE**: novel signal, insert new truth record.
  - **EVOLVE**: schema/meaning shift, create new version; old becomes non-canonical via `supersedes_id` chain.
  - **CONTRADICT**: conflict with truth; **flag for P06 active learning**.
  - **PRUNE**: decayed/stale truth; archive/tombstone.
- Core reconciliation algorithm shape:
  1) **Query truth** across multiple layers relevant to the signal.
  2) **Compute similarity** (multi-factor).
  3) Choose decision via thresholds + contradiction detection.

### 3) Similarity system is dynamic (not “static thresholds only”)

#### 3.1 Per-layer similarity weights (5-factor)

- Factors: semantic (embedding cosine), simhash similarity, entity overlap, temporal proximity, spatial proximity.
- **Per-layer weight vectors** differ by truth layer (e.g., episodic emphasizes temporal/spatial more than semantic).
- Storage: `st_learned_weights` keys like `similarity_{layer}_{factor}`.
- Metrics:
  - factor contribution histogram
  - weights updated counter
  - drift gauge

#### 3.2 Weight learning from outcomes

- Two learning paths:
  - **ReconciliationOutcome learning** (explicit/implicit outcomes like match used / rejected / manual merge)
  - **Online weight adjustment** using downstream signals from **P04/K1** (match used, user rejects, manual links, query reformulation).
- Constraints:
  - clamp weights in [0.05, 0.60]
  - renormalize to sum to 1.0
  - momentum smoothing appears in some pseudocode

### 4) Entity-type thresholds (precision varies)

- Reconciliation thresholds are **entity-type dependent** (PERSON higher, CONCEPT lower, etc.).
- Supports learned thresholds, per-space variation, bounds per type.
- Storage: again `st_learned_weights` keys like `threshold_{entity_type}_reinforce`, etc.
- Feedback adjusts thresholds based on merges/splits confirmations.

### 5) Golden dataset validation (quality guardrail)

- Weekly validation against curated golden pairs.
- Metrics targets: precision/recall/F1, FP/FN rates.
- Drift detection: alert if F1 drops >5% WoW.
- Schema suggests `st_golden_dataset_pairs`, `st_validation_results`.

### 6) Thompson Sampling thresholds (Bayesian) + stability

- Magic numbers replaced by **Thompson sampling** (Beta priors) for thresholds like reinforce/extend_lower.
- Per-space isolation + hierarchical fallback:
  - Level 1: per-space if enough signals
  - Level 2: global aggregate
  - Level 3: static defaults
- Requires **decision outcome tracking**:
  - store decisions in `st_consolidation_audit` with `threshold_used`, `threshold_name`, outcome evaluation flags.
  - nightly job evaluates outcomes after observation windows and updates Beta params.
- Cold start strategy:
  - <100 signals: static defaults
  - 100–500: wide exploration
  - >500: tighter exploitation bounds
- Stability guardrails:
  - momentum
  - bounds
  - bound-hit alerts
  - rollback if quality degrades for N days

### 7) Architecture placement and dependencies

- P03 reads from `st_hipp_events` produced by P02.
- P03 writes/updates:
  - truth layers (st_epi, st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges, st_vec)
  - learning queue for P06 (gaps)
  - outbox for durable emission
- Dependency on P08: requires `embedding.search` capability.

### 8) Phase state machine (R0–R8) is sequential but can skip

- Base order: R0 → R1 → R2 → R3 → R4 → (R5 optional) → R6 → R7 → R8.
- Skip rules:
  - R5 can be skipped based on backlog/time window.
  - There is also mention of skipping R3-R5 if minimal work (transition R2 → R6).
- Timing constraints per phase + abort/recovery semantics by phase.

### 9) Closed-loop learning exists beyond similarity

- **Importance score learning** (R1): weights become learnable using K1/P04 feedback signals.
- **Adaptive DBSCAN eps/min_samples/temporal_weight** (R2): per-space learning using silhouette, singleton rate, grounding rate, corrections.
- **Decay learning / access tracking / immunity** (R3):
  - per-entity access tracking from P04 retrievals
  - unified decay engine across tables
  - regret detection window (14 days) for pruned entities
  - decay immunity ontology (family members, birthdays, etc.)
  - adaptive novelty bonuses learned from feedback

### 10) Envelope architecture / execution model (critical for wiring)

- P03 is designed around a **batch envelope** flowing through phases.
- Envelope principles:
  - immutable `P03CycleContext` after R0
  - per-event state list enriched R1–R6
  - staged writes accumulated R1–R6
  - R7 commits via UnitOfWork in deterministic dependency order
  - R8 emits events from outbox
- Strong emphasis on:
  - idempotency
  - retryability
  - observability
  - lazy embedding loading / caching
  - phase guards, checkpoints, progress tracking

### 11) Implementation planning implications (what must be epics later)

- This is **not** a single epic “implement R0–R8”. P03 implies multiple parallel but ordered workstreams:
  - Core pipeline wiring + scheduler/locks + abort/resume
  - Truth reconciliation engine (read/compare/decide)
  - Storage/migrations for truth layers + audit/weights tables
  - Outbox + event emission topics
  - Learning loops (similarity weights, thresholds, DBSCAN params, importance weights, novelty bonuses)
  - Decay/unified retention + immunity + prune regret detection
  - P06 gap queue integration
  - P04/K1 feedback ingestion (signals → learners)
  - Validation/guardrails (golden dataset, drift detection, rollback)
  - Tests (integration-first) + performance + ops dashboards/alerts

---

## Running TODO (next increments)

- [x] Read lines 4001–8000 and append notes.
- [x] Read lines 8001–12000 and append notes.
- [x] Read lines 12001–16000 and append notes.
- [x] Read lines 16001–20000 and append notes.
- [x] Read lines 20001–24000 and append notes.
- [x] Read lines 24001–28431 (end) and append notes.
- [x] Repeat in 4k blocks until dossier end.
- [ ] After full read: produce milestone/epic/issue counts + sequencing for end-to-end wiring.

---

## Notes for Lines 4001–8000

### 1) R4 deepens into full KG consolidation (and it’s heavily learnable)

- R4 expands beyond “write KG” into a full **entity/edge management subsystem**:
  - entity extraction + normalization (NER output processing)
  - entity disambiguation (per-entity-type weights)
  - ambiguous mention resolution (context-based)
  - entity merge (cascade + undo)
  - relationship discovery and causal inference (with adaptive thresholds + feedback)

### 2) Per-entity-type disambiguation weights (embedding vs string) are learnable

- Core idea: similarity is not one-size-fits-all; **PERSON** vs **CONCEPT** require different matching.
- Per-type weight matrix (embedding weight vs string weight), stored as learned parameters:
  - keys like `disambiguation_PERSON_embedding` / `disambiguation_PERSON_string` in `st_learned_weights`
  - weights are normalized to sum to 1.0 and clamped to safe ranges (e.g., [0.15, 0.85]).
- The string similarity implementation is explicitly multi-algorithm (Levenshtein / Jaro-Winkler / token sort).
- Feedback signals drive online weight adjustment:
  - false positive merges (rejected) push weight toward the component that differed more
  - false negative merges (manual merges) relax the component that matched well but wasn’t trusted
  - splits (wrong merges) increase strictness
- Planning implication: this is **a distinct learning loop** (separate from earlier per-layer similarity weights).

### 3) Ambiguous entity resolution is explicitly a P06 integration point

- When a mention has multiple candidate entities (“John”), P03 resolves by **context hierarchy**:
  1) recent context
  2) co-occurring entities
  3) location context
  4) temporal pattern
  5) frequency
  6) if low confidence: **emit gap** to P06
- Confidence bands:
  - ≥ 0.85 auto-resolve
  - 0.60–0.85 resolve + flag for review
  - < 0.60 emit `AMBIGUOUS_ENTITY` gap to P06
- New persistence suggested: `st_entity_resolutions` table (mention_text, resolved_entity_id, candidates, confidence, resolution_method, review fields).
- Planning implication: you need end-to-end wiring for **gap emission** and “review/correction” feedback to feed learning.

### 4) Entity merge is a high-stakes, reversible, multi-table cascade

- Merge process is defined as a 6-step operation:
  1) validate
  2) choose primary (more history)
  3) merge attributes
  4) cascade update references
  5) archive secondary (MERGED)
  6) log for undo
- Cascades touch many tables (examples given): `st_kg_edges`, `st_hipp_events` (JSON replacement), `st_epi`, `st_sem`, `st_social`, `st_procedural`, `st_vec`.
- Undo support introduces a new table `st_entity_merges` with snapshots + cascade counts; reversal uses a `merge_cascade_id` to revert updates.
- Planning implication: merge/undo should be treated as its own epic with:
  - transactional guarantees (UnitOfWork)
  - correctness tests (referential integrity + JSON patching correctness)
  - performance bounds (timeouts) + observability

### 5) Adaptive merge thresholds (per-entity-type) are learned + monitored for drift

- Separate from weights: each entity type has a **learned merge threshold** (e.g., FAMILY_MEMBER starts at 0.90).
- Feedback adjusts thresholds (+0.03, +0.05, -0.02, etc.), clamped within per-type ranges.
- Stored in `st_learned_weights` via keys like `disambiguation_threshold_FAMILY_MEMBER`.
- Drift monitoring requirements are explicit:
  - alert on threshold drift > 0.15 in 30 days
  - alert on FP rate > 10% (precision low)
  - alert on FN rate > 20% (recall low)

### 6) Relationship discovery expands into causal inference with guardrails

- R4 includes relationship discovery (co-occurrence / NLP extraction / temporal inference).
- A large sub-system is defined for **Granger-style causal edges**:
  - precedence ratio $= \frac{a\_before\_b}{a\_before\_b + b\_before\_a + simultaneous}$
  - category-specific thresholds (Health/Medical, Financial, Social/Routine, Preference/Habit)
  - thresholds are learnable from feedback signals (raise on wrong predictions, lower on missed causation)
- Additional safeguards:
  - **adaptive minimum observations** based on pattern frequency (daily needs more samples; annual needs fewer)
  - confidence scaling by observation count (with diminishing returns)
  - **confound detection**:
    - common cause detection (C→A and C→B)
    - Simpson’s paradox detection (reversal in context subgroups)
    - results can demote from CAUSAL → CORRELATED / CONTEXT_DEPENDENT
- Schema additions to `st_kg_edges` are extensive (explicitly called out):
  - `edge_type` (CAUSAL/CORRELATED/CONTEXT_DEPENDENT/HEBBIAN)
  - `causality_category`, `precedence_ratio`
  - `observation_count`, `pattern_frequency`, `min_observations_required`
  - `causal_confidence`, `confounder_candidates`, `context_conditions`, `confound_checked`

### 7) Causal edges have a full feedback loop (validate, boost, demote, archive)

- P03 creates causal edges; P04/K1 uses them; outcomes generate feedback.
- Feedback persistence: `st_causal_feedback` (signal_type, contexts, space_id, timestamps).
- Edge usage tracking adds additional columns to `st_kg_edges`:
  - `last_used_at`, `last_validated_at`, `usage_count`, `prediction_accuracy`.
- Demotion behavior:
  - if rolling 30-day accuracy < 0.70 (after min samples + trend check), demote CAUSAL → CORRELATED
  - emits event `p03.causal_edge.demoted.v1`
- Staleness behavior:
  - archive causal edges unused for 90 days

### 8) R5 “Dream-like exploration (REM)” is explicitly feature-flagged and staged

- MVP decision: `P03_FF_R5_MODE=disabled`.
- Rollout plan: disabled → shadow → enabled_low → enabled.
- Shadow mode requirements:
  - run MCTS but do not apply; log heuristic vs MCTS choice to `st_mcts_shadow_log`
  - evaluate outcomes after a delay (e.g., 7 days), decide whether to enable based on metrics
- If enabled, R5 includes:
  - adaptive rollout allocation by decision type (merges get many rollouts; reversible tuning gets few)
  - early termination criteria (clear winner / low uncertainty)
  - compute budget per cycle (e.g., 1000 rollouts)
  - determinism concerns for tests (seed with `cycle_ulid`)
- Storage suggested:
  - `st_mcts_decisions` for executed decisions
  - `st_mcts_shadow_log` for shadow comparison + outcome scoring
- Planning implication: R5 is a **later milestone**; MVP needs hooks/flags, not full algorithms.

### 9) R6/R7/R8 clarify the “commit + emit” mechanics

- R6 (staging updates) defines what must be recorded back to `st_hipp_events`:
  - consolidation_status values: CONSOLIDATED / DUPLICATE / PRUNED / PENDING_REVIEW
  - dedup metadata (near_duplicates_json), novelty score persistence, episode_cluster_id
  - reconciliation decision recording (decision type, target truth id, confidence, similarity)
- R7 (truth writes) emphasizes:
  - outbox durability (`st_outbox`) + transactional boundaries
  - deterministic ordering across truth layers (episodic/semantic/procedural/social/prospective/KG/vector)
  - coordination with P08 for embedding/index updates
- R8 (emission + completion):
  - emits: `p03.consolidation.complete.v1`, `p03.pattern.detected.v1`, `p03.truth.*.v1`, `p03.memory.pruned.v1`
  - **new explicit topic**: `p03.gap.detected.v1` for P06
  - updates `st_pipeline_offsets` for resume
  - aggregates metrics by decision type + errors

### 10) Multi-instance concurrency: K0 kernel enhancements are called out (some superseded)

- Requirements described:
  - per-space single-writer semantics (avoid concurrent consolidation cycles for same space)
  - partitioned execution across spaces in multi-node deployments
- Proposed K0 enhancements:
  - advisory lock service (not needed if using PostgreSQL `pg_advisory_lock()`)
  - scheduler partition strategies (tenant/space/consistent hash)
  - pipeline execution context needs node_id + partition assignment
- Note: dossier claims PostgreSQL migration makes advisory locks + optimistic concurrency “native”; partitioned execution and cluster awareness remain proposed.

### 11) P06 Active Learning integration is specified end-to-end (P03 is the gap detector)

- P03 is the “observer brain”: detects gaps during consolidation and emits to P06.
- Gap types listed (and where they arise):
  - AMBIGUOUS_ENTITY (R4)
  - LOW_CONFIDENCE_EDGE (R4)
  - MISSING_ATTRIBUTE (R4)
  - CONTRADICTION (R7)
  - CONCEPT_DRIFT (R3)
  - STRUCTURAL_HOLE (R5 / background)
  - STALE_ANCHOR (background scan)
- Gap detection includes an **entropy score** calculation (candidate distribution entropy, else inverse confidence).
- Gap emission protocol:
  1) persist gap to `st_learning_queue`
  2) publish `p03.gap.detected.v1` (with partition key `tenant_id:space_id`)

### 12) Entropy scanning is a background job (proactive gaps)

- Scheduled daily (example: 4 AM), post-consolidation trigger, and manual trigger.
- Scan executors described:
  - ontology validator (missing required attributes)
  - anchor decay detector (stale beliefs)
  - structural hole finder (expected-but-missing edges)
- Requires deduping against existing queue entries, rate limiting, and priority sorting.
- Priority scoring formula combines entropy, confidence, recency, and type-specific weights.

### 13) Bayesian anchors are first-class: Beta priors, updates, and drift detection

- Anchors are probabilistic beliefs (Beta(α, β)) about user attributes (e.g., “prefers spicy food”).
- Updated during consolidation (noted as R1) via evidence extractors:
  - apply temporal decay before updating α/β
- Drift detector:
  - if $|\mu\_{recent} - \mu\_{historical}| > 0.20$ and enough recent samples, flag drift
- Planning implication: anchors introduce another table family (e.g., `st_anchors`, `st_anchor_observations`) and must be coherently integrated with P06 (stale anchors become questions).

### 14) Contradiction protocol + attention budget mechanics exist as concrete requirements

- Contradiction classification depends on similarity band + semantic conflict alignment.
- Strategy selection considers:
  - confidence of existing truth
  - confidence/recency of new signal
  - P06 question budget capacity
- Attention budget uses a token bucket (max tokens/day, refill rate, limited overdraw for high-importance gaps).
- Question timing is context-aware (topic match, activity match, idle detection).

### 15) P03 feedback ingestion is formalized as a handler (learning loops wiring)

- P03 subscribes to `feedback.signal.p03.v1` (from P21 feedback pipeline).
- Handler routes feedback payloads into multiple learning modules:
  - importance (salience)
  - decay adjustment
  - clustering/similarity adjustment
  - Hebbian reinforcement outcome
  - novelty / memory gap audit
  - regret signals
- Consumption is tracked in `st_feedback_signals` with statuses PROCESSED/SKIPPED/FAILED.
- Planning implication: contracts for feedback payload types + robust retry semantics are required.

### 16) Implementation planning implications (new work surfaced in this block)

- New storage/migrations implied in this section (beyond what was in 1–4000):
  - `st_entity_resolutions`, `st_entity_merges`, `st_causal_feedback`, `st_mcts_decisions`, `st_mcts_shadow_log`
  - significant `ALTER TABLE st_kg_edges` expansion
- New wiring requirements:
  - bus topic `p03.gap.detected.v1` and downstream P06 consumer expectations
  - P03 consumption of `feedback.signal.p03.v1`
  - emission topic `p03.causal_edge.demoted.v1`
- Test implications:
  - determinism for MCTS shadow logging
  - integration tests for merge cascade + undo
  - confound detection correctness + demotion behavior
  - attention-budget / rate-limit correctness

---

## Notes for Lines 8001–12000

### 1) Feedback ingestion: P03 subscribes + routes + tracks consumption

- P03 must **subscribe** to `feedback.signal.p03.v1` during pipeline initialization.
  - Registration pattern: `register_handlers(bus, db_pool, metrics_registry)`.
  - Health check: pipeline is unhealthy if the subscription fails or `p03_feedback_subscribed` gauge is 0.
- Feedback routing is centralized in `P03FeedbackHandler` with an explicit routing map:
  - salience/importance → ImportanceLearner
  - decay reversal → DecayLearner
  - cluster correction + similarity learning + hebbian outcomes → Similarity/Hebbian learners
  - novelty signal → audit logger
  - regret signal → RegretLearner
- Consumption tracking is not optional:
  - P03 updates shared `st_feedback_signals` fields: `consumed_at`, `consumed_by='P03'`, `consumption_status`, `consumption_reason`.
  - Status semantics:
    - PROCESSED: applied to learning (no retry)
    - SKIPPED: filtered (no retry)
    - FAILED: error (P21 retries up to 3 before DLQ)
- Audit linkage requirement:
  - learning updates should reference the original feedback envelope id in `st_consolidation_audit` (e.g., `feedback_envelope_id`).

### 2) Storage schema: explicit “PostgreSQL is canonical” + durability rules

- The dossier is explicit that schema/DDL targets **PostgreSQL**.
  - Driver placeholder styles may differ (`$1` vs `%s`), but **SQLite-only DDL and functions must not be copied**.
- Durability rules (apply across all truth layers):
  - **Immutability + versioning**:
    - do not update semantic content in place
    - create new version rows, link via `supersedes_id`
    - only one canonical row (`is_canonical=TRUE`) per chain
    - bounded in-place updates are allowed for counters/telemetry and lifecycle flags
  - **No physical deletes**:
    - use `archival_status` state machine: ACTIVE → ARCHIVED → TOMBSTONE → (later GC)
  - **Full provenance chain**:
    - every truth record links to source event/episode ids
    - every decision logged in `st_consolidation_audit`
    - cycle tracing via `consolidation_cycle_id`

### 3) Common columns + indexing + standard read/write patterns

- “Common columns” group is specified (identity, versioning, temporal/bitemporal, truth tracking, source linkage, lifecycle, consolidation cycle id).
- Indexing patterns are standardized:
  - tenant+space partition index first
  - canonical active lookup (partial index)
  - temporal validity queries
  - confidence-based retrieval
  - actor-specific patterns
  - consolidation cycle lookup
  - decay candidate scanning
- Standard write patterns (important implementation constraints):
  - CREATE = INSERT v1 canonical
  - REINFORCE = in-place UPDATE for counters/confidence/last_observed, append to sources (this is a defined exception)
  - EVOLVE = flip existing canonical false + INSERT new version (supersedes)
  - PRUNE = UPDATE archival_status to ARCHIVED or TOMBSTONE
- Standard query patterns:
  - canonical truth query must filter tenant_id+space_id and `is_canonical=TRUE` and `archival_status='ACTIVE'`
  - bitemporal “truth at time” query uses `valid_from/valid_to`
  - version history query walks `supersedes_id` chains

### 4) Concrete table schemas surfaced in this block (critical for migration plan)

- `st_hipp_events` (P02 staging): large contract, but key points for P03:
  - ordering via `wal_pos`
  - strong trace/policy/visibility/retention fields
  - P03 uses column groups by phase (R1/R2/R3/R4/R6/R8)
  - consolidation lifecycle: NULL → PENDING → IN_PROGRESS → (CONSOLIDATED | DUPLICATE | PRUNED | PENDING_REVIEW)
- Truth layer tables defined with consistent columns:
  - `st_epi`, `st_sem`, `st_procedural`, `st_social`, `st_prospective`, `st_kg_dom`, `st_kg_edges`
- Embeddings table `st_vec`:
  - stores vector in `BYTEA`, status includes READY/INDEXED/FAILED
  - P08 integration: `faiss_id`, `indexed_at`
- Active learning queue `st_learning_queue`:
  - gap types enumerated
  - derived `importance_score` computed from entropy and confidence
  - status lifecycle for P06 coordination (PENDING→READY→ASKED→ANSWERED→RESOLVED, plus EXPIRED/REJECTED/SUPPRESSED)
- Anchors + evidence:
  - `st_anchors` stores Beta(α,β) parameters and derived confidence/uncertainty (generated columns)
  - `st_anchor_observations` provides an evidence log for auditability
- Pipeline operational tables:
  - `st_offsets`, `st_pipeline_status`, `st_pipeline_watermarks` for resume and compaction
- Outbox:
  - `st_outbox` stores `payload` as `BYTEA`, idempotency uniqueness via `(tenant_id, space_id, driver, fingerprint, requeue_seq)`
- Retention policy configuration table: `st_retention_policy`

### 5) Learned parameter storage is formalized and secured (RLS)

- `st_learned_weights` is the **central store** for adaptive parameters (importance weights, decay lambdas, DBSCAN params, similarity thresholds, etc.).
- Scope + fallback is formalized via `param_scope` and `scope_id`:
  - `global` | `space` | `entity_type` | `entity`
- Versioning fields support rollback (`prior_value`, `previous_value`, `version`, `quality_at_update`, `rollback_eligible`).
- Row-level security is explicitly required:
  - `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`
  - session context via `SET LOCAL app.current_space_id = $1`
  - isolation policy uses `current_setting('app.current_space_id', true)`
- Parameter history table:
  - `st_learned_weights_history` stores versions and quality for rollback and analysis
  - cleanup keeps last 10 versions per param
  - automatic rollback trigger example: regression of ~15% relative to recent average

### 6) Regret tracking is elevated to a first-class subsystem

- `st_pruned_entities` tracks pruned entities for “regret” detection (query later matches pruned truth).
  - retention: unmatched 14 days, matched 30 days
  - uses semantic matching (pgvector ivfflat index) and fuzzy name matching
  - integrates with P04 retrieval to emit regret learning signals
- Metrics are defined around regrets, cleanup, and storage limits.

### 7) Audit + security quarantine expand operational requirements

- `st_consolidation_audit` is expanded to support explainability + learning analysis:
  - `formula_used`, `formula_version`, `inputs_json`, `outputs_json`, `explanation`, `confidence`
  - retention: 90 days raw, then aggregate daily summaries
- `st_feedback_quarantine` quarantines suspicious feedback signals:
  - reasons: rate limit, velocity spike, anomaly, entropy
  - severity: LOW/MEDIUM/HIGH
  - auto-release after 48h or manual review
- `st_decay_feedback` captures access/resurrection events to learn decay λ with Bayesian estimation over rolling windows.

### 8) Module registry: explicit P03 module decomposition (M18–M25)

- Dependency graph and responsibility split are made explicit:
  - M23 ReplayCoordinator (R1 lead)
  - M18 EpisodicClusterer (R2 lead)
  - M19 DuplicateDetector + M20 RetentionEnforcer (R3)
  - M21 KGConsolidator (R4)
  - M22 DreamExplorer (R5, experimental)
  - M24 TruthWriter (R7 lead)
  - M25 GapDetector (R8 lead)
- Reuse from P02 is explicit: UltraBERT, SimHasher, EntityResolver, OutboxWriter.
- Interface contracts include key algorithm notes (DBSCAN details, novelty scoring formula shape, Hebbian co-occurrence, decision routing in TruthWriter).

### 9) Observability: cross-space leakage detection + learning budget monitoring

- Cross-space leakage is treated as a security property with:
  - query auditing for missing `space_id` filters
  - RLS block metrics
  - integration tests to confirm isolation works
- Learning performance must stay under a compute budget:
  - explicit metrics: learning time percentage, learning latency histograms, queue depth/overflow, batch size/duration, skip counts, budget exceeded counter
  - defined alert thresholds (warning/critical) and dashboard PromQL examples

### 10) Implementation planning implications (new work surfaced in this block)

- Storage/migration scope balloons here: multiple operational + learning tables are now “required by design”, not optional.
- “Security + isolation” is not just an app concern; RLS and monitoring are part of the contract.
- The module registry provides a concrete breakdown that should map cleanly to epics/issues (M18–M25 plus feedback/quarantine/learning subsystems).
- Note: this block contains some duplicated/rough snippets (e.g., stray `WHERE matched_at IS NULL;` and mixed placeholder styles). Treat it as a design spec, but implementations/migrations must be cleaned and made consistent for Postgres.

---

## Notes for Lines 12001–16000

### 1) Observability is a first-class contract (metrics + tracing + logs + dashboards)

- Prometheus metrics are specified at multiple levels:
  - **Decision metrics**: counters for REINFORCE/EXTEND/CREATE/EVOLVE/CONTRADICT/PRUNE, plus similarity bands and threshold buckets.
  - **Gap metrics**: gap type counts, entropy distribution, queue depth, resolution latency, suppression counts.
  - **Memory layer metrics**: per-layer upserts, prune counts, canonical-vs-version writes, conflict rates.
  - **Per-module duration metrics**: histograms for each R-stage and for key modules (e.g., replay, clustering, dedup, KG, writer).
  - **Learning metrics**: updates applied, drift gauges, rollback counters, “shadow vs live” comparison results.
- Shadow-mode comparator is explicitly described:
  - run “candidate algorithm/params” in shadow, compare decisions to live, and record delta metrics.
  - planning implication: implement a comparator abstraction and a consistent metric schema early.
- Distributed tracing:
  - an OpenTelemetry span tree is spelled out (cycle → phase → module → DB/outbox calls), with required attributes like `tenant_id`, `space_id`, `cycle_ulid`, `wal_pos_range`, `event_count`.
  - ensure phase spans align with R0–R8 to make dashboards readable.
- Structured logging schema:
  - JSON log fields are specified (phase, decision_type, target_ids, confidence, thresholds used, error_class, retry_count, etc.).
  - phase-based log levels are recommended (e.g., info for decisions, warn for drift, error for DLQ).
- Ops dashboards and alerting are part of the spec:
  - dashboard panels for end-to-end cycle latency, per-phase latency, error/DLQ rate, drift signals, learning budget usage.
  - alert examples include drift thresholds, DLQ growth, and learning budget exceed.

### 2) Integration contracts are explicit (topics + storage join keys)

- P02 → P03 ingestion contract:
  - P03 reads staged events from `st_hipp_events` using ordering fields (e.g., WAL position) and policy/visibility/retention fields.
  - event topic expectations exist (e.g., indexed/ready events) and must align with `st_hipp_events` lifecycle state.
- P03 → P06 gap contract:
  - P03 publishes gaps and expects resolution acknowledgements.
  - canonical join/correlation decision: **use `body.correlation.gap_id`** in gap answers/acks.
  - note: joining via WAL is mentioned; an indexed column for `gap_id` is an optional future optimization.
- P03 → P08 embedding coordination:
  - P03 emits embedding-related events and/or waits on embedding readiness in `st_vec` (READY/INDEXED/FAILED) depending on sync/async mode.
- P03 ↔ P05 attention/token budget:
  - request/response-style contract for “should we ask questions / spend budget?” and “how much budget do we have?”
  - planning implication: implement a small, typed budget client and treat it as a dependency boundary.
- P03 completion contract:
  - P03 emits `p03.consolidation.complete.v1` (schema includes cycle ids, counts, durations, error summary, offsets advanced).
- P21 feedback contract (consumption):
  - P03 consumes `feedback.signal.p03.v1` and must mark consumption in shared `st_feedback_signals`.
  - a typed payload schema (Pydantic-style) is shown; contract tests should be created for it.

### 3) Testing strategy begins to formalize “integration-first”

- Test pyramid guidance is explicit:
  - contract tests for topics + schemas
  - integration tests for DB + outbox + bus wiring
  - golden dataset quality tests for decision correctness and drift
  - performance tests around batching and per-phase budgets
- Sample scaffolding is included; planning implication: stand up a repeatable “mini-cycle” harness early (one space, seeded events, deterministic cycle ids).

---

## Notes for Lines 16001–20000

### 1) Feature flags + shadow mode are operational requirements (not nice-to-have)

- Multiple capabilities are intended to roll out through:
  - disabled → shadow → enabled_low → enabled.
- Shadow mode must produce **comparative metrics** without applying results.
- Planning implication: define a single feature-flag surface for P03 (env/config) and a shared shadow-comparator utility.

### 2) Error handling is standardized via DLQ + retry scheduler + circuit breakers

- Error classification is specified (examples): TRANSIENT / VALIDATION / LOGIC / FATAL.
- DLQ integration:
  - P03 routes unrecoverable or max-retry failures into `st_dlq` with enough context to replay.
  - a `P03ErrorHandler` pattern is shown (centralizes classification, retry decisioning, and DLQ write).
- Retry scheduler integration:
  - backoff rules, max attempts, and re-queue behavior are explicitly described.
- Circuit breakers:
  - trip on repeated downstream failures (e.g., embedding provider, database overload) and degrade gracefully.
- Partial failure strategies are enumerated:
  - COMMIT_PARTIAL vs ROLLBACK_ALL vs QUARANTINE_BATCH.
  - planning implication: these must be selectable per stage or per error class.
- Operational runbooks/commands are referenced (k0ctl-style):
  - inspect DLQ entries, replay, quarantine, and purge.

### 3) Rollback patterns exist for learning and formulas (guardrails for “adaptive”)

- Parameter rollback:
  - learning updates must be versioned and rollback-eligible.
  - rollbacks are triggered by quality regression and are observable (counters + audit).
- Formula rollback:
  - formula versions must be recorded in `st_consolidation_audit` (inputs/outputs/explanation) to support “what changed?” analysis.

### 4) Security & privacy are integrated into consolidation and learning

- K0 policy engine is treated as the gatekeeper for read/write.
- Privacy bands (GREEN/AMBER/RED) influence:
  - whether consolidation proceeds
  - how data is masked (notably location masking via geohash precision)
  - whether a memory can be used as evidence.
- ACL enforcement is called out as an explicit query-builder responsibility (tenant/space filters + deny-by-default).
- Audit trail:
  - `st_consolidation_audit` is used both for explainability and compliance; it must capture decisions, inputs, outputs, and policy outcomes.
- Retention and erasure:
  - retention enforcement is integrated with consolidation and pruning.
  - GDPR erasure must propagate to truth layers and derived artifacts.
- Learning isolation:
  - learned parameters must be isolated (RLS) and protected from cross-space leakage.
  - anomaly detection around learning updates is part of the spec.

### 5) Performance/QoS integration is concrete

- Token/budget acquisition from the scheduler is part of cycle start.
- QoSContext budgets shape:
  - per-cycle compute time
  - embedding/query fanout (top_k)
  - batch size.
- Adaptive batch sizing is recommended (based on observed latency and backlog).
- Learning compute budget is capped (e.g., under 5% of cycle time) and must be measurable.
- Caching is recommended for expensive lookups (embedding reuse, truth candidate caches).

### 6) Configuration reference begins (implementation must be parameterized)

- P03 expects many knobs to be config-driven:
  - feature flags (shadow/enable)
  - scheduler triggers and cadence
  - thresholds and bounds
  - safety/policy switches
  - provider selections (embedding, NER, etc.).

---

## Notes for Lines 20001–24000

### 1) Appendix algorithms are implementation-grade (need to be mapped into modules)

- Bayesian confidence updating:
  - a `BayesianConfidenceUpdater` is specified, combining frequency/consistency/significance (geometric mean).
  - planning implication: implement this as a reusable utility (used by anchors, KG edges, and truth confidence updates).

### 2) Concurrency safety: optimistic locking and bounded retry loops

- Optimistic locking patterns are specified for truth updates:
  - read version, compute update, write with version check, retry on conflict.
  - integrate with UnitOfWork and error handler; overflow routes to DLQ.
- Planning implication: define a consistent “retry policy” abstraction shared across writers.

### 3) Importance scoring is both a formula and a learner

- Importance scoring formula uses multiple features; thresholds for “high importance” affect downstream:
  - which events become anchors
  - which become candidates for reinforcement
  - which gaps get budget priority.
- Adaptive weight learning is described:
  - gradient/Adam-style updates
  - softmax normalization to keep weights summing to 1
  - drift detection + rollback triggers.
- Planning implication: treat importance as two epics: (a) implement stable formula + audit, (b) implement bounded learning loop + guardrails.

### 4) Hebbian learning details (with anti-Hebbian decay, resurrection, saturation controls)

- Core update is reinforced by co-occurrence and event importance.
- Anti-Hebbian decay reduces stale or spurious edges.
- Resurrection logic reactivates edges that become relevant again.
- Adaptive learning rate and saturation/normalization constraints are explicit.
- Planning implication: implement a “HebbianEdgeUpdater” that is deterministic and testable (seeded by cycle id).

### 5) Episodic clustering (DBSCAN) is adaptive

- DBSCAN is described with pre-splitting sequences by time gaps.
- Parameters (e.g., `min_samples`) adapt based on singleton rate and clustering quality.
- Planning implication: implement parameter updates via `st_learned_weights` and add validation metrics (silhouette/singleton rate).

### 6) Dedup is two-stage (SimHash then embedding verification)

- SimHash thresholds vary by content type; adaptive tuning is discussed.
- Two-stage dedup reduces false positives:
  1) SimHash candidate selection
  2) embedding-based verification.
- Planning implication: treat SimHash threshold learning as a guarded improvement (shadow first), with explicit FP/FN metrics.

---

## Notes for Lines 24001–28431 (End)

### 1) Additional algorithm specifications (novelty, milestones, active learning)

- Novelty scoring and pruning include modifiers for:
  - first-time activities
  - milestone-like events
  - temporal anomalies
  - exact duplicates.
- Milestone detection:
  - uses NER + ontology mapping + recurrence logic to detect “life events” and promote importance/retention.
- Active learning:
  - entropy and Beta-confidence appear as prioritization signals.
  - a token bucket / budget manager constrains question volume.

### 2) KG-specific algorithms and model integration notes

- UltraBERT is referenced as the NER/relation backbone in multiple phases.
- Simplified Granger-style causality logic is reiterated (with guardrails).
- Planning implication: model/version management and provider selection must be explicit (encoder version pinning).

### 3) R5 dream exploration remains experimental, but algorithms are documented

- Counterfactual pattern networks (CPN), MCTS projections, bisociative traversal, TD learning are described.
- Planning implication: MVP should implement the feature-flag and shadow logging hooks; full execution remains a later milestone.

### 4) Appendix D: Kernel Integration Blueprint (how P03 lands in K0)

- The dossier provides a blueprint for wiring P03 into K0:
  - stage/DAG mapping aligned to R0–R8
  - required capabilities matrix (DB, bus, embedding search, NER, policy, scheduler budgets)
  - outbox emission pattern as the durability boundary.
- Module layout is suggested under `k0/modules/consolidation/`.
- Transactionality:
  - UnitOfWork wraps truth writes and outbox rows in a single commit.
- Provider registration and capability fabric integration are described.
- Testing patterns are reiterated (contract + integration + replayable mini-cycles).

### 5) Appendix H: UltraBERT integration reference

- Backend selection guidance (ONNX INT8 default, PyTorch for dev/GPU environments).
- Version pinning notes and integration points per phase (R0/R1/R2/R4/R7).
- Artifact location expectations (`wheels/…`, cache directories).

### 6) Appendix I: Closed-loop feedback system proposals (explicit “self-learning P03” plan)

- Reframes P03 from open-loop to closed-loop:
  - ingest implicit feedback signals from P04 and K1 behaviors
  - adapt thresholds (Thompson sampling)
  - adapt per-entity decay rates
  - learn importance weights.
- Signal taxonomy is defined (MEMORY_MISS, REFORMULATION, CORRECTION, VALIDATION, ABANDONMENT, PRUNE_REGRET).
- Implementation phases are sketched (Phase 1 adds `st_implicit_feedback`, Phase 2 handlers, Phase 3+ learning).
- A “static vs learnable vs research” table is included; treat research items as shadow-mode first.
- ADRs are explicitly called out as required for the closed-loop design changes.
- Priority matrix suggests P0: feedback wiring, regret tracking, `st_implicit_feedback` table.
