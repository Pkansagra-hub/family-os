# P03 R7 Truth Writer Discovery & Enhancement Plan

> **Discovery document for Epic 5.8 -- R7 Truth Writer.** Follows DISCOVERY_TEMPLATE.md (15 sections + appendices).
> R7 is the atomic truth-writing phase that sits between R6 (Staging) and R8 (Event Emission).
> It receives all staged writes from R6, executes them atomically against truth tables via UnitOfWork,
> records observations, stages outbox events, and updates hipp_events consolidation status.
>
> **Key design principle**: R7 is the ONLY phase that writes to the database -- all mutations are committed
> in a single transaction, ensuring either all writes succeed or none do (atomic commit).

---

## 0. Discovery Metadata

| Field | Value |
| ----- | ----- |
| Pipeline ID | P03 |
| Module Scope | consolidation.truth_writer.router, consolidation.truth_writer.transaction, consolidation.truth_writer.observation_recorder, consolidation.truth_writer.result, consolidation.truth_writer.outbox, consolidation.truth_writer.embedding_generator, consolidation.truth_writer.source_text_fetcher, consolidation.truth_writer.text_vector_coordinator, consolidation.truth_writer.layers.episodic, consolidation.truth_writer.layers.semantic, consolidation.truth_writer.layers.kg, consolidation.truth_writer.layers.procedural, consolidation.truth_writer.layers.social, consolidation.truth_writer.layers.prospective, consolidation.truth_writer.layers.mcts, consolidation.truth_writer.layers.vector |
| Discovery Date | 2026-03-03 |
| Milestone Target | M5 |
| Governing ADRs | ADR-K003 (pgvector migration, no FAISS) |
| Related Dossier | `docs/pipelines/P03_consolidation_dossier_v2.md` |
| Author | copilot-claude |
| Status | DRAFT |

**Scope Summary**:

R7 Truth Writer is the atomic commit phase of the P03 consolidation pipeline. It receives staged writes from R6 (grouped by truth table layer in `P03StagedWrites`), routes them through a `DecisionRouter` to 8 per-layer writers, executes all writes atomically within a single `UnitOfWork` transaction, records observations to `st_observations`, stages outbox events for R8, and updates `st_hipp_events` consolidation status. R7 is the largest and most critical phase in P03, with ~7,000 lines of production code across 18 source files.

**Key Design Principles**:

1. **Atomic commit**: All truth table writes, observation records, outbox events, and status updates execute in a single PostgreSQL transaction. Either all succeed or all roll back.
2. **Dual-path architecture**: R7 supports both the M5 `DecisionRouter` + `TransactionCoordinator` path (enabled via `USE_M5_ROUTER=True`) and a deprecated legacy inline-SQL path for rollback safety.
3. **Dependency-ordered writes**: Writes follow FK constraint order: `st_vec` -> `st_kg_dom` -> `st_kg_edges` -> `st_epi` -> `st_sem` -> `st_procedural` -> `st_social` -> `st_prospective` -> `st_hipp_events`.
4. **Optimistic locking**: All UPDATE operations use version columns for conflict detection, with exponential-backoff retry (3 attempts, 100ms base delay).
5. **Inline embedding generation**: `TextVectorCoordinator` (GAP-001) generates UltraBERT v2.1.0 embeddings within the transaction for layer writers that need text-to-vector conversion.

---

## 1. Current State Audit

### 1.1 Code Inventory

| # | File (relative path) | Lines | Status | Last Modified | Purpose |
| - | -------------------- | ----: | ------ | ------------- | ------- |
| 1 | k0/pipelines/p03/phases/r7_truth_writer.py | 1,033 | MOD | M5 | Implements R7 pipeline phase: opens UoW, dispatches to M5 router or legacy path, stages outbox, updates hipp_events status, commits atomically |
| 2 | k0/modules/consolidation/truth_writer/router.py | 265 | MOD | M5 | Implements DecisionRouter that routes staged writes to per-layer writers with ATOMIC/PARTIAL mode support |
| 3 | k0/modules/consolidation/truth_writer/transaction.py | 351 | MOD | M5 | Implements TransactionCoordinator wrapping DecisionRouter with retry on OptimisticLockError and version refresh |
| 4 | k0/modules/consolidation/truth_writer/observation_recorder.py | 256 | MOD | M5 | Implements ObservationRecorder for 32-column INSERT into st_observations on every truth write |
| 5 | k0/modules/consolidation/truth_writer/result.py | 219 | MOD | M5 | Defines LayerWriteResult and WriteResult dataclasses for per-layer and aggregate write statistics |
| 6 | k0/modules/consolidation/truth_writer/outbox.py | 274 | MOD | M5 | Implements OutboxWriter for transactional outbox staging with fingerprint idempotency keys |
| 7 | k0/modules/consolidation/truth_writer/embedding_generator.py | 169 | MOD | M5 | Wraps UltraBERT v2.1.0 client to produce 768-dimensional embeddings for text summaries |
| 8 | k0/modules/consolidation/truth_writer/source_text_fetcher.py | 218 | MOD | M5 | Fetches source texts from st_hipp_events for embedding generation (20-day text decay constraint) |
| 9 | k0/modules/consolidation/truth_writer/text_vector_coordinator.py | 213 | MOD | M5 | Orchestrates GAP-001 text-fetch -> embedding-generate -> vector-write pipeline for layer writers |
| 10 | k0/modules/consolidation/truth_writer/layers/episodic.py | 489 | MOD | M5 | Implements EpisodicLayerWriter for st_epi: INSERT (30 cols), REINFORCE (jsonb_agg, temporal bounds), ARCHIVE, TOMBSTONE |
| 11 | k0/modules/consolidation/truth_writer/layers/semantic.py | 573 | MOD | M5 | Implements SemanticLayerWriter for st_sem: INSERT (29 cols), REINFORCE (confidence boost), EXTEND, EVOLVE |
| 12 | k0/modules/consolidation/truth_writer/layers/kg.py | 1,007 | MOD | M5 | Implements KGLayerWriter for st_kg_dom + st_kg_edges + st_entity_merges: entity/edge INSERT, UPDATE, ARCHIVE, TOMBSTONE, track_merge |
| 13 | k0/modules/consolidation/truth_writer/layers/procedural.py | 417 | MOD | M5 | Implements ProceduralLayerWriter for st_procedural: INSERT (20 cols), REINFORCE (multiplicative confidence), EXTEND |
| 14 | k0/modules/consolidation/truth_writer/layers/social.py | 671 | MOD | M5 | Implements SocialLayerWriter for st_social: INSERT (39 params), REINFORCE (EMA sentiment, trajectory), EXTEND, DECAY |
| 15 | k0/modules/consolidation/truth_writer/layers/prospective.py | 427 | MOD | M5 | Implements ProspectiveLayerWriter for st_prospective: INSERT (21 cols), EXTEND, COMPLETE, COUNTERFACTUAL, TOMBSTONE |
| 16 | k0/modules/consolidation/truth_writer/layers/mcts.py | 106 | DEPRECATED | M5 | Implements MCTSLayerWriter for st_mcts_decisions: INSERT-only (13 cols, no ON CONFLICT). DELETE candidate in M5D |
| 17 | k0/modules/consolidation/truth_writer/layers/vector.py | 368 | MOD | M5 | Implements VectorLayerWriter for st_vec: INSERT/UPDATE with P08 circuit breaker and embedding aggregation |
| 18 | k0/modules/consolidation/truth_writer/__init__.py | 147 | MOD | M5 | Barrel re-export of 48 symbols from all R7 sub-modules |
| 19 | k0/modules/consolidation/truth_writer/layers/__init__.py | 112 | MOD | M5 | Barrel re-export of layer writer classes and data types |
| **TOTAL** | | **7,340** | | | |

### 1.2 Contract Inventory

| # | Contract File | Version | Status | Lines | Governs |
| - | ------------- | ------- | ------ | ----- | ------- |
| 1 | k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | active | 433 | pipeline:p03 (stage_70_memory_writer section governs R7) |
| 2 | k0/contracts/modules/consolidation.memory_writer.v1.yaml | v1 | active | ~90 | module:consolidation.memory_writer (R7 I/O, side effects, failure modes) |

### 1.3 Config Inventory

#### 1.3.1 YAML Config Keys

| Config File | Version | Key (dot-path) | Value | Type | Default | Required | Notes |
| ----------- | ------- | --------------- | ----- | ---- | ------- | -------- | ----- |
| k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | stages.stage_70.config.transaction_timeout_ms | 30000 | int | NONE | yes | Max transaction duration before timeout |
| k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | stages.stage_70.config.batch_size | 100 | int | NONE | no | Records per insert batch |
| k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | stages.stage_70.config.retry_on_conflict | true | bool | true | no | Whether to retry on optimistic lock conflicts |
| k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | stages.stage_70.config.max_retries | 3 | int | 3 | no | Max version conflict retry attempts |
| k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | stages.stage_70.config.retry_backoff_ms | 100 | int | 100 | no | Base delay for exponential backoff on retry |

#### 1.3.2 Environment Variables

| Variable | Type | Default | Required | Used By | Purpose |
| -------- | ---- | ------- | -------- | ------- | ------- |
| K0_DB_URL | url | NONE | yes | k0/db/engine.py (UoW) | PostgreSQL connection string for all R7 truth writes |

#### 1.3.3 Feature Flags

| Flag Name | Source | Default | Scope | Controls | Rollback Behavior |
| --------- | ------ | ------- | ----- | -------- | ----------------- |
| USE_M5_ROUTER | code (r7_truth_writer.py) | True | global | Switches between M5 DecisionRouter path and deprecated legacy inline-SQL path | Safe -- legacy path is fully functional, no data loss |

#### 1.3.4 Constants & Magic Numbers

| Constant | Location (file:line) | Value | Type | Rationale | Externalize? |
| -------- | -------------------- | ----- | ---- | --------- | ------------ |
| LAYER_PK_MAP | r7_truth_writer.py:53 | dict (10 entries) | dict[str,str] | Maps each truth table to its PK column for point lookups and dedup | maybe -- duplicated in transaction.py |
| LAYER_PK_MAP | transaction.py (duplicated) | dict (10 entries) | dict[str,str] | Same map duplicated for version refresh queries | yes -- extract to shared constant |
| USE_M5_ROUTER | r7_truth_writer.py:72 | True | bool | Toggles M5 router vs legacy inline SQL path | no -- code flag for migration rollback |
| EXTERNALLY_HANDLED_LAYERS | router.py:234 | {"st_hipp_events"} | frozenset | st_hipp_events handled by R7 phase directly, not by layer writers | no -- architectural constant |
| VALID_LAYERS | observation_recorder.py:47 | frozenset (6 entries) | frozenset[str] | Only these layers produce observation records | no -- maps to schema |
| REINFORCE_BOOST | semantic.py:138 | 0.05 | float | Additive confidence boost per reinforcement for semantic patterns | maybe -- could be configurable |
| REINFORCE_FACTOR | procedural.py:127 | 1.1 | float | Multiplicative confidence factor for procedural reinforcement | maybe -- could be configurable |
| REINFORCE_FACTOR | social.py:133 | 1.1 | float | Multiplicative strength factor for social reinforcement | maybe -- could be configurable |
| DECAY_FACTOR | social.py:136 | 0.95 | float | Multiplicative decay for social relationship DECAY action | maybe -- could be configurable |
| SENTIMENT_OLD_WEIGHT | social.py:140 | 0.9 | float | EMA weight for existing sentiment in social reinforcement | maybe -- model tuning parameter |
| SENTIMENT_NEW_WEIGHT | social.py:139 | 0.1 | float | EMA weight for new sentiment in social reinforcement | maybe -- model tuning parameter |
| EXTEND_BOOST | kg.py:231 | 1.1 | float | Multiplicative confidence boost for KG entity EXTEND action | maybe -- could be configurable |
| MODEL_ID | embedding_generator.py:55 | "ultrabert-v2.1.0" | str | UltraBERT model version for all R7 embeddings | no -- tied to model, changing requires migration |
| DIMENSION | embedding_generator.py:56 | 768 | int | UltraBERT output vector dimension | no -- tied to model and VECTOR(768) schema |
| BYTES_PER_VECTOR | embedding_generator.py:57 | 3072 | int | float32 storage per vector (768 * 4) | no -- derived from DIMENSION |
| MAX_TEXT_LENGTH | embedding_generator.py:60 | 2000 | int | Max text chars before truncation for embedding | maybe -- model-dependent |
| MAX_BATCH_SIZE | source_text_fetcher.py:79 | 500 | int | Max event IDs per text fetch batch from st_hipp_events | yes -- performance tuning |
| failure_threshold | vector.py (P08CircuitBreakerConfig) | 5 | int | P08 circuit breaker opens after this many consecutive failures | yes -- operational tuning |
| reset_timeout_ms | vector.py (P08CircuitBreakerConfig) | 60000 | int | P08 circuit breaker reset timeout (60 seconds) | yes -- operational tuning |
| max_batch_size | outbox.py (OutboxWriteConfig) | 100 | int | Max outbox entries per staging batch | yes -- performance tuning |
| driver_prefix | outbox.py (OutboxWriteConfig) | "p03" | str | Fingerprint prefix for idempotency keys | no -- pipeline identity |
| max_retries | transaction.py (TransactionConfig) | 3 | int | Max OptimisticLockError retries before failure | yes -- matches contract |
| retry_delay_ms | transaction.py (TransactionConfig) | 100 | int | Base delay for exponential backoff (100ms * 2^attempt) | yes -- matches contract |

### 1.4 Migration Inventory

| # | Migration File | Table(s) | Operation | Columns Affected | Reversible? |
| - | -------------- | -------- | --------- | ---------------- | ----------- |
| N/A | R7 writes to existing tables created by prior milestones | st_epi, st_sem, st_kg_dom, st_kg_edges, st_procedural, st_social, st_prospective, st_vec, st_observations, st_outbox, st_hipp_events, st_mcts_decisions, st_entity_merges | N/A | N/A | N/A |

> R7 does not create or alter any tables. All truth tables were created by M3/M4 migrations. R7 only performs INSERT, UPDATE, and status-change operations on existing schemas.

---

## 2. API Surface Map

### 2.1 Public Functions & Methods

| # | Module | Function / Method | Signature | Return Type | Consumers | Idempotent? | Notes |
| - | ------ | ----------------- | --------- | ----------- | --------- | ----------- | ----- |
| 1 | k0.pipelines.p03.phases.r7_truth_writer | R7TruthWriter.run | (self, envelope: P03Envelope, context: P03Context) -> None | None | P03 pipeline runner | no | Mutates envelope.write_result, commits to DB |
| 2 | k0.modules.consolidation.truth_writer.router | DecisionRouter.route | (self, staged_writes: P03StagedWrites, uow: UnitOfWork) -> WriteResult | WriteResult | TransactionCoordinator, R7TruthWriter | no | Routes writes to per-layer writers |
| 3 | k0.modules.consolidation.truth_writer.router | create_decision_router | (writers: list[LayerWriterProtocol], mode: WriteMode = ATOMIC) -> DecisionRouter | DecisionRouter | R7TruthWriter._get_or_create_coordinator | yes | Factory function |
| 4 | k0.modules.consolidation.truth_writer.transaction | TransactionCoordinator.execute | (self, staged_writes: P03StagedWrites, uow: UnitOfWork) -> TransactionResult | TransactionResult | R7TruthWriter._execute_staged_writes_m5 | no | Retries on OptimisticLockError |
| 5 | k0.modules.consolidation.truth_writer.transaction | TransactionCoordinator.execute_simple | (self, staged_writes: P03StagedWrites, uow: UnitOfWork) -> WriteResult | WriteResult | N/A (available for callers managing own conflicts) | no | Direct route() without retry |
| 6 | k0.modules.consolidation.truth_writer.observation_recorder | ObservationRecorder.record | (self, uow: UnitOfWork, ..., 30+ fields) -> str | str (observation_id) | Layer writers (episodic, semantic, kg, social, prospective) | no | Inserts 32-column row into st_observations |
| 7 | k0.modules.consolidation.truth_writer.observation_recorder | ObservationRecorder.record_batch | (self, uow: UnitOfWork, observations: list[dict]) -> list[str] | list[str] | Layer writers | no | Sequential record() calls (not executemany) |
| 8 | k0.modules.consolidation.truth_writer.observation_recorder | ObservationRecorder.record_for_insert | (self, uow: UnitOfWork, ...) -> str | str | Layer writers on INSERT | no | Records FIRST_SEEN observation |
| 9 | k0.modules.consolidation.truth_writer.observation_recorder | ObservationRecorder.record_for_merge | (self, uow: UnitOfWork, ...) -> str | str | Layer writers on REINFORCE/EXTEND | no | Records REINFORCEMENT observation |
| 10 | k0.modules.consolidation.truth_writer.observation_recorder | get_observation_recorder | () -> ObservationRecorder | ObservationRecorder | Layer writers | yes | Singleton factory |
| 11 | k0.modules.consolidation.truth_writer.result | LayerWriteResult.success | (layer: str, writes_attempted: int, duration_ms: float) -> LayerWriteResult | LayerWriteResult | Layer writers, DecisionRouter | yes | Factory method |
| 12 | k0.modules.consolidation.truth_writer.result | LayerWriteResult.failure | (layer: str, writes_attempted: int, error_message: str, ...) -> LayerWriteResult | LayerWriteResult | Layer writers, DecisionRouter | yes | Factory method |
| 13 | k0.modules.consolidation.truth_writer.result | WriteResult.from_layer_results | (results: list[LayerWriteResult]) -> WriteResult | WriteResult | DecisionRouter, TransactionCoordinator | yes | Aggregate factory |
| 14 | k0.modules.consolidation.truth_writer.outbox | OutboxWriter.stage_write | (self, uow: UnitOfWork, ...) -> OutboxStagingResult | OutboxStagingResult | R7TruthWriter._stage_outbox_events | no | Stages one outbox entry with fingerprint |
| 15 | k0.modules.consolidation.truth_writer.outbox | OutboxWriter.stage_batch | (self, uow: UnitOfWork, entries: list) -> OutboxStagingResult | OutboxStagingResult | R7TruthWriter._stage_outbox_events | no | Stages multiple outbox entries |
| 16 | k0.modules.consolidation.truth_writer.embedding_generator | EmbeddingGenerator.generate | (self, text: str) -> GeneratedEmbedding or None | GeneratedEmbedding or None | TextVectorCoordinator | no | Returns None on any failure |
| 17 | k0.modules.consolidation.truth_writer.source_text_fetcher | SourceTextFetcher.fetch_for_events | (self, uow: UnitOfWork, event_ids: list[str]) -> FetchedSourceTexts | FetchedSourceTexts | TextVectorCoordinator.process | no | Reads st_hipp_events text (20-day decay) |
| 18 | k0.modules.consolidation.truth_writer.source_text_fetcher | SourceTextFetcher.fetch_for_episodes | (self, uow: UnitOfWork, episode_ids: list[str]) -> FetchedSourceTexts | FetchedSourceTexts | TextVectorCoordinator.process_for_episodes | no | Resolves episodes to events via st_epi.source_events_json |
| 19 | k0.modules.consolidation.truth_writer.text_vector_coordinator | TextVectorCoordinator.process | (self, uow: UnitOfWork, event_ids: list[str], layer: str) -> TextVectorResult | TextVectorResult | EpisodicLayerWriter, SemanticLayerWriter, KGLayerWriter | no | Full GAP-001 pipeline: fetch -> generate -> result |
| 20 | k0.modules.consolidation.truth_writer.text_vector_coordinator | TextVectorCoordinator.process_for_episodes | (self, uow: UnitOfWork, episode_ids: list[str], layer: str) -> TextVectorResult | TextVectorResult | SocialLayerWriter | no | Episode-based GAP-001 pipeline |
| 21 | k0.modules.consolidation.truth_writer.text_vector_coordinator | TextVectorCoordinator.process_without_fetch | (self, texts: dict[str, str], layer: str) -> TextVectorResult | TextVectorResult | ProceduralLayerWriter, ProspectiveLayerWriter | no | Direct text-to-embedding, no DB fetch |
| 22 | k0.modules.consolidation.truth_writer.text_vector_coordinator | get_coordinator | () -> TextVectorCoordinator | TextVectorCoordinator | Layer writers | yes | Singleton factory |

### 2.2 Syscalls Used / Required

| # | Syscall | Signature | Status | Used By | SQL Pattern | Notes |
| - | ------- | --------- | ------ | ------- | ----------- | ----- |
| N/A | R7 does not use syscalls -- all SQL is inline in layer writers via UoW.execute() | | | | | R7 bypasses the syscall layer for performance; all queries are parameterized SQL executed directly through UnitOfWork |

> **Note**: R7 layer writers construct parameterized SQL and execute it directly via `uow.execute(sql, params)`. This is an intentional architectural decision to keep all writes within the same transaction context. The syscall layer is not used because syscalls open their own connections, which would break transaction atomicity.

### 2.3 Internal Helpers (non-public but critical path)

| # | Module | Function | Signature | Called By | Purpose | Risk if Changed |
| - | ------ | -------- | --------- | --------- | ------- | --------------- |
| 1 | r7_truth_writer | _execute_staged_writes_m5 | (self, envelope, uow) -> None | R7TruthWriter.run | Dispatches to TransactionCoordinator for M5 router path | Breaks all M5 writes if signature or coordinator init changes |
| 2 | r7_truth_writer | _get_or_create_coordinator | (self) -> TransactionCoordinator | _execute_staged_writes_m5 | Lazy-initializes all 8 layer writers and TransactionCoordinator | Breaks all writes -- every layer writer instantiated here |
| 3 | r7_truth_writer | _deduplicate_writes | (self, writes) -> list | Legacy path | Groups by (layer, record_id) and merges duplicate writes | Legacy-only but needed for rollback path |
| 4 | r7_truth_writer | _merge_writes | (self, writes) -> StagedWrite | _deduplicate_writes | INSERT precedence, record_data merge, version tracking | Legacy-only; incorrect merge = data corruption |
| 5 | r7_truth_writer | _stage_outbox_events | (self, envelope, uow) -> None | R7TruthWriter.run | Stages StagedOutboxEvent objects from envelope.staged | R8 receives no events if broken |
| 6 | r7_truth_writer | _writeback_status | (self, envelope, uow) -> None | R7TruthWriter.run | Updates st_hipp_events consolidation_status to CONSOLIDATED | Events never marked consolidated if broken |
| 7 | transaction | _refresh_versions | (self, writes, uow) -> list | TransactionCoordinator.execute retry loop | Re-reads version from DB for each conflicting write | Stale version on retry = infinite retry loop |
| 8 | transaction | _backoff | (self, attempt: int) -> None | TransactionCoordinator.execute retry loop | Exponential delay: retry_delay_ms * 2^attempt | Too aggressive = DB hammering; too slow = timeout |
| 9 | router | _route_layer | (self, layer, writes, uow) -> LayerWriteResult | DecisionRouter.route | Delegates to registered LayerWriterProtocol.write() for one layer | Missing writer for layer = unhandled writes |
| 10 | kg | _normalize_json | (value) -> str | KGLayerWriter entity/edge INSERT | Normalizes dict/list to JSON string for JSONB columns | Bad JSON = INSERT failure |
| 11 | semantic | _looks_like_event_ids | (ids: list[str]) -> bool | SemanticLayerWriter | UUID regex to distinguish event IDs from episode IDs for TVC routing | Wrong routing = missing embeddings |
| 12 | vector | aggregate_embeddings | (embeddings, method) -> list[float] | VectorLayerWriter | numpy-based mean/weighted_mean/max embedding aggregation | Bad aggregation = corrupted vectors |

### 2.4 Classes & Dataclasses

| # | Module | Class | Base Class / Protocol | Key Attributes | Key Methods | Consumers |
| - | ------ | ----- | --------------------- | -------------- | ----------- | --------- |
| 1 | r7_truth_writer | R7TruthWriter | (none) | PHASE_ID, LAYER_PK_MAP, USE_M5_ROUTER, _coordinator | run(), _execute_staged_writes_m5(), _get_or_create_coordinator() | P03 pipeline runner |
| 2 | router | DecisionRouter | (none) | _writers: dict, _mode: WriteMode | route(), has_writer(), get_writer() | TransactionCoordinator |
| 3 | router | WriteMode | Enum | ATOMIC, PARTIAL | N/A | DecisionRouter |
| 4 | router | LayerWriterProtocol | Protocol | layer: str | write(writes, uow) | DecisionRouter (type check) |
| 5 | router | DecisionRouterError | Exception | message, partial_result: WriteResult | N/A | DecisionRouter.route() |
| 6 | transaction | TransactionCoordinator | (none) | _router: DecisionRouter, _config: TransactionConfig, _layer_pk_map | execute(), execute_simple() | R7TruthWriter |
| 7 | transaction | TransactionConfig | dataclass | mode: WriteMode, max_retries: int, retry_delay_ms: int, require_capabilities: bool | N/A | TransactionCoordinator |
| 8 | transaction | TransactionResult | dataclass | write_result: WriteResult, attempts: int, total_duration_ms: float, version_conflicts: int | is_success, is_partial | R7TruthWriter |
| 9 | transaction | OptimisticLockError | Exception | layer: str, record_id: str, expected_version: int | N/A | Layer writers, TransactionCoordinator |
| 10 | observation_recorder | ObservationRecorder | (none) | (stateless) | record(), record_batch(), record_for_insert(), record_for_merge() | 5 layer writers |
| 11 | result | LayerWriteResult | dataclass | layer, writes_attempted, writes_succeeded, writes_failed, failed_ids, error_message, duration_ms | success(), failure(), partial(), is_success, is_partial, to_dict() | All layer writers, DecisionRouter |
| 12 | result | WriteResult | dataclass | total_attempted, total_succeeded, total_failed, by_layer: dict, failed_decision_ids, total_duration_ms | from_layer_results(), empty(), is_success, is_partial, success_rate, to_summary() | TransactionCoordinator, R7TruthWriter |
| 13 | outbox | OutboxWriter | (none) | _config: OutboxWriteConfig | stage_write(), stage_batch(), stage_event() | R7TruthWriter |
| 14 | outbox | OutboxWriteConfig | dataclass | driver_prefix: str, max_batch_size: int, retry_backoff_base_ms: int | N/A | OutboxWriter |
| 15 | outbox | OutboxStagingResult | dataclass | staged_count, failed_count, fingerprints | N/A | R7TruthWriter |
| 16 | embedding_generator | EmbeddingGenerator | (none) | MODEL_ID, DIMENSION, BYTES_PER_VECTOR, MAX_TEXT_LENGTH | generate(), generate_sync(), vector_to_bytes(), bytes_to_vector() | TextVectorCoordinator |
| 17 | embedding_generator | GeneratedEmbedding | dataclass | vector: list[float], model_id: str, dimension: int | N/A | EmbeddingGenerator, TextVectorCoordinator |
| 18 | source_text_fetcher | SourceTextFetcher | (none) | MAX_BATCH_SIZE | fetch_for_events(), fetch_for_episodes() | TextVectorCoordinator |
| 19 | source_text_fetcher | FetchedSourceTexts | dataclass | texts: dict[str, str], found_count: int, missing_count: int | is_complete | TextVectorCoordinator |
| 20 | text_vector_coordinator | TextVectorCoordinator | (none) | _fetcher: SourceTextFetcher, _generator: EmbeddingGenerator | process(), process_for_episodes(), process_without_fetch() | 6 layer writers |
| 21 | text_vector_coordinator | TextVectorResult | dataclass | embeddings: dict[str, GeneratedEmbedding], failed_ids: list[str] | has_results | Layer writers |
| 22 | layers.episodic | EpisodicLayerWriter | LayerWriterProtocol | layer="st_epi", _obs_recorder, _tvc | write(writes, uow) | DecisionRouter |
| 23 | layers.episodic | EpisodeWriteData | dataclass | episode_id, tenant_id, space_id, ... (30+ fields) | N/A | EpisodicLayerWriter |
| 24 | layers.semantic | SemanticLayerWriter | LayerWriterProtocol | layer="st_sem", REINFORCE_BOOST=0.05, _obs_recorder, _tvc | write(writes, uow) | DecisionRouter |
| 25 | layers.semantic | PatternWriteData | dataclass | pattern_id, tenant_id, space_id, ... | N/A | SemanticLayerWriter |
| 26 | layers.semantic | PatternAction | Enum (str) | REINFORCE, EXTEND, EVOLVE | N/A | SemanticLayerWriter |
| 27 | layers.kg | KGLayerWriter | LayerWriterProtocol | layer="st_kg_dom", EXTEND_BOOST=1.1, _obs_recorder, _tvc | write(writes, uow), track_merge() | DecisionRouter (handles st_kg_dom + st_kg_edges) |
| 28 | layers.kg | EntityWriteData | dataclass | entity_id, tenant_id, canonical_name, ... (22+ fields) | N/A | KGLayerWriter |
| 29 | layers.kg | EdgeWriteData | dataclass | edge_id, source_entity_id, target_entity_id, ... (24 fields) | N/A | KGLayerWriter |
| 30 | layers.kg | EntityAction | Enum (str) | EXTEND, EVOLVE | N/A | KGLayerWriter |
| 31 | layers.procedural | ProceduralLayerWriter | LayerWriterProtocol | layer="st_procedural", REINFORCE_FACTOR=1.1, _tvc | write(writes, uow) | DecisionRouter |
| 32 | layers.procedural | RoutineWriteData | dataclass | routine_id, tenant_id, ... | N/A | ProceduralLayerWriter |
| 33 | layers.procedural | RoutineAction | Enum (str) | REINFORCE, EXTEND | N/A | ProceduralLayerWriter |
| 34 | layers.social | SocialLayerWriter | LayerWriterProtocol | layer="st_social", REINFORCE_FACTOR=1.1, DECAY_FACTOR=0.95, SENTIMENT_*_WEIGHT, _obs_recorder, _tvc | write(writes, uow) | DecisionRouter |
| 35 | layers.social | RelationshipWriteData | dataclass | relationship_id, tenant_id, ... (39 params) | N/A | SocialLayerWriter |
| 36 | layers.social | RelationshipAction | Enum (str) | REINFORCE, EXTEND, DECAY | N/A | SocialLayerWriter |
| 37 | layers.prospective | ProspectiveLayerWriter | LayerWriterProtocol | layer="st_prospective", _obs_recorder, _tvc | write(writes, uow) | DecisionRouter |
| 38 | layers.prospective | IntentionWriteData | dataclass | intention_id, tenant_id, ... (17+ fields) | N/A | ProspectiveLayerWriter |
| 39 | layers.prospective | IntentionAction | Enum (str) | EXTEND, COMPLETE, COUNTERFACTUAL | N/A | ProspectiveLayerWriter |
| 40 | layers.mcts | MCTSLayerWriter | LayerWriterProtocol | layer="st_mcts_decisions" | write(writes, uow) | DecisionRouter |
| 41 | layers.vector | VectorLayerWriter | LayerWriterProtocol | layer="st_vec", _p08_config: P08CircuitBreakerConfig | write(writes, uow) | DecisionRouter |
| 42 | layers.vector | EmbeddingWriteData | dataclass | embedding_id, vector, model_id, dimension, ... | N/A | VectorLayerWriter |
| 43 | layers.vector | P08CircuitBreakerConfig | dataclass | failure_threshold=5, reset_timeout_ms=60000 | N/A | VectorLayerWriter |

---

## 3. Algorithm Inventory

### 3.1 Current Algorithms

| # | Algorithm Name | Location | Category | Input Type(s) | Input Constraints | Output Type(s) | Output Guarantees | Time | Space | Det? | Stateful? | State Location | Parameters | Edge Cases | Failure Mode | Fallback | Dependencies | Description |
| - | -------------- | -------- | -------- | ------------- | ----------------- | -------------- | ----------------- | ---- | ----- | ---- | --------- | -------------- | ---------- | ----------- | ------------ | -------- | ------------ | ----------- |
| 1 | decision_routing | router.py:85 | routing | P03StagedWrites, UnitOfWork | writes grouped by layer, UoW open | WriteResult | all layers attempted (PARTIAL) or first failure raised (ATOMIC) | O(L*W) where L=layers, W=writes per layer | O(L) layer results | yes | no | N/A | mode=ATOMIC/PARTIAL | empty staged writes, unknown layer, externally-handled layer (st_hipp_events) | raises DecisionRouterError in ATOMIC mode | continues and records failures in PARTIAL mode | LayerWriterProtocol implementations | Routes staged writes to registered per-layer writers in dependency order |
| 2 | optimistic_lock_retry | transaction.py | merging | P03StagedWrites, UnitOfWork | writes must have expected_version | TransactionResult | max attempts <= max_retries+1, version_conflicts tracked | O(R*L*W) where R=retries | O(W) refreshed versions | no (timing-dependent) | yes | retry counter in execute() | max_retries=3, retry_delay_ms=100 | no conflicts (fast path), max retries exceeded | raises OptimisticLockError after max retries | N/A -- caller must handle | DecisionRouter, DB version reads | Wraps DecisionRouter with retry-on-OptimisticLockError and exponential backoff version refresh |
| 3 | exponential_backoff | transaction.py | scheduling | attempt: int | attempt >= 0 | None (sleep) | delay = retry_delay_ms * 2^attempt | O(1) | O(1) | yes | no | N/A | retry_delay_ms=100 | attempt=0 (100ms), attempt=2 (400ms) | N/A -- always succeeds | N/A | asyncio.sleep | Implements exponential backoff delay between version conflict retries |
| 4 | write_deduplication | r7_truth_writer.py | merging | list[StagedWrite] | writes may contain duplicates for same (layer, record_id) | list[StagedWrite] (deduped) | one write per (layer, record_id), INSERT takes precedence | O(W) | O(W) grouping dict | yes | no | N/A | N/A | empty list, single write, all duplicates | returns empty list for empty input | N/A | N/A | Groups duplicate staged writes by (layer, record_id) and merges into single write with INSERT precedence |
| 5 | write_merge | r7_truth_writer.py | merging | list[StagedWrite] for same (layer, record_id) | all writes target same record | StagedWrite | INSERT precedence, record_data merged (later overrides), min expected_version, combined source_event_ids | O(D) where D=duplicates | O(1) | yes | no | N/A | N/A | single write (passthrough), conflicting operations | returns first write if single | N/A | N/A | Merges multiple staged writes for same record: INSERT takes priority over UPDATE, record_data dicts merged with later overriding |
| 6 | episodic_reinforce | layers/episodic.py | merging | StagedWrite (REINFORCE action), UoW | existing episode in st_epi with matching episode_id | None (DB mutation) | temporal bounds extended, source_events merged, version incremented | O(1) per record | O(1) | no (reads DB) | no | N/A | N/A | empty source_events, no temporal change, version conflict | raises OptimisticLockError on version mismatch | N/A | UoW, ObservationRecorder | Reinforces existing episode: jsonb_agg DISTINCT source events, LEAST/GREATEST temporal bounds, duration recalc |
| 7 | semantic_reinforce | layers/semantic.py | merging | StagedWrite (REINFORCE action), UoW | existing pattern in st_sem | None (DB mutation) | confidence += REINFORCE_BOOST (capped at 1.0), observation_count incremented | O(1) | O(1) | no | no | N/A | REINFORCE_BOOST=0.05 | confidence already at 1.0, version conflict | raises OptimisticLockError | N/A | UoW, ObservationRecorder, TVC | Boosts semantic pattern confidence by additive 0.05, updates last_observed, records observation |
| 8 | kg_extend | layers/kg.py | merging | StagedWrite (EXTEND action), UoW | existing entity in st_kg_dom | None (DB mutation) | confidence *= EXTEND_BOOST (no cap), attributes merged | O(1) | O(1) | no | no | N/A | EXTEND_BOOST=1.1 | version conflict, missing entity, null attributes | raises OptimisticLockError | N/A | UoW, ObservationRecorder, TVC | Extends KG entity: multiplicative confidence boost, attribute merge, provenance tracking |
| 9 | social_ema_sentiment | layers/social.py:466 | aggregation | existing_sentiment: float, new_sentiment: float | both in [-1.0, 1.0] | float | result = old*0.9 + new*0.1, in [-1.0, 1.0] | O(1) | O(1) | yes | no | N/A | SENTIMENT_OLD_WEIGHT=0.9, SENTIMENT_NEW_WEIGHT=0.1 | first observation (no existing), extreme values | uses new_sentiment if no existing | N/A | N/A | Computes exponential moving average of sentiment for social relationship reinforcement |
| 10 | social_decay | layers/social.py | transformation | StagedWrite (DECAY action), UoW | existing relationship in st_social | None (DB mutation) | strength *= DECAY_FACTOR (min 0.0) | O(1) | O(1) | no | no | N/A | DECAY_FACTOR=0.95, custom factor via record_data | strength already 0.0 | raises OptimisticLockError | N/A | UoW | Decays social relationship strength by multiplicative factor (default 0.95) |
| 11 | p08_circuit_breaker | layers/vector.py | validation | failure event | continuous failure count tracked | bool (open/closed/half-open) | opens after failure_threshold consecutive failures, resets after reset_timeout_ms | O(1) | O(1) | no (time-dependent) | yes | VectorLayerWriter instance fields | failure_threshold=5, reset_timeout_ms=60000 | first call (closed), threshold exact boundary, timeout boundary | skips P08 event staging when open | continues without P08 notification | N/A | Tracks P08 outbox failures and stops staging events after threshold, auto-resets after timeout |
| 12 | embedding_aggregation | layers/vector.py | aggregation | list[list[float]], method: str | all vectors must be same dimension (768) | list[float] (768-dim) | output dimension matches input dimension | O(N*D) where N=vectors, D=dimension | O(N*D) numpy array | yes | no | N/A | method: mean/weighted_mean/max | empty list raises ValueError, single vector passthrough | raises ValueError on empty input | N/A | numpy | Aggregates multiple embedding vectors into single vector via mean, weighted_mean, or element-wise max |
| 13 | embedding_generation | embedding_generator.py:42 | transformation | text: str | non-empty, max 2000 chars (truncated) | GeneratedEmbedding or None | vector is 768-dim float, model_id="ultrabert-v2.1.0" | O(T) where T=text length (model inference) | O(D) where D=768 | no (model inference) | no | N/A | MODEL_ID, DIMENSION, MAX_TEXT_LENGTH | empty text, whitespace only, text > 2000 chars (truncated), model failure | returns None on any failure | returns None -- caller must handle | k0.runtime.ultrabert_adapter | Generates 768-dim UltraBERT v2.1.0 embedding from text, truncating to MAX_TEXT_LENGTH chars |
| 14 | text_source_fetch | source_text_fetcher.py:63 | search | event_ids: list[str] | max 500 IDs (truncated), valid UUIDs | FetchedSourceTexts | found_count + missing_count = len(input) | O(N) where N=event count | O(N) texts dict | no (reads DB) | no | N/A | MAX_BATCH_SIZE=500 | empty IDs, all missing (text decayed), IDs > 500 (truncated) | returns empty FetchedSourceTexts on DB failure | returns empty result | UoW, st_hipp_events | Fetches source text from st_hipp_events for embedding generation (text decays after 20 days) |
| 15 | outbox_fingerprinting | outbox.py | transformation | cycle_ulid, layer, record_id | all non-empty strings | str (fingerprint) | deterministic: p03:write:{cycle_ulid}:{layer}:{record_id} | O(1) | O(1) | yes | no | N/A | driver_prefix="p03" | N/A | N/A | N/A | N/A | Generates deterministic idempotency key for outbox entries to prevent duplicate staging |
| 16 | procedural_regularity_average | layers/procedural.py | aggregation | existing_regularity: float, new_regularity: float | both >= 0.0 | float | (existing + new) / 2 | O(1) | O(1) | yes | no | N/A | N/A | first observation, zero values | uses new value if no existing | N/A | N/A | Computes moving average of routine regularity for procedural reinforcement |
| 17 | prospective_lifecycle | layers/prospective.py | transformation | IntentionAction, current_status | action in {EXTEND, COMPLETE, COUNTERFACTUAL} | new_status | status transitions: pending->completed/expired/cancelled | O(1) | O(1) | yes | no | N/A | N/A | already completed, tombstone on completed | no-op if already in terminal state | N/A | N/A | Manages prospective intention lifecycle transitions: pending to completed/expired/cancelled/counterfactual |
| 18 | observation_recording | observation_recorder.py:52 | transformation | write context (30+ fields) | layer must be in VALID_LAYERS | observation_id (ULID) | 32-column row inserted into st_observations | O(1) per record | O(1) | no (generates ULID) | no | N/A | N/A | invalid layer raises ValueError, null optional fields | raises ValueError on invalid layer | N/A | UoW | Records a holistic observation row to st_observations for every truth write: temporal, emotional, social, location context |

### 3.2 Algorithm Gaps

| # | Gap Description | Expected Behavior | Current Behavior | Severity | Proposed Approach | Estimated Complexity |
| - | --------------- | ----------------- | ---------------- | -------- | ----------------- | -------------------- |
| 1 | TransactionCoordinator retries entire batch on single-row failure | Retry only conflicting rows, not entire batch | Entire P03StagedWrites re-routed on any OptimisticLockError | P2 | Track per-row conflict, build reduced StagedWrites with only conflicting writes for retry | medium |
| 2 | ObservationRecorder.record_batch uses sequential inserts | Batch INSERT via executemany or COPY for N observations | Loops over observations calling record() sequentially | P2 | Replace sequential loop with executemany or VALUES list INSERT | small |
| 3 | MCTSLayerWriter INSERT has no ON CONFLICT clause | Idempotent INSERT with ON CONFLICT DO NOTHING | Raw INSERT that will raise on duplicate PK | P3 | Add ON CONFLICT DO NOTHING (or delete writer entirely in M5D) | trivial |
| 4 | EmbeddingGenerator runs synchronously within transaction | Async embedding generation or pre-compute before transaction | Synchronous UltraBERT call inside UoW transaction context | P1 | Move embedding generation to pre-transaction phase (before UoW.begin) or use async call | medium |
| 5 | No version conflict telemetry | Metric tracking version conflict rate per layer | Conflicts counted in TransactionResult but not emitted as metrics | P2 | Add counter metric for version_conflicts_total with layer label | trivial |
| 6 | Procedural layer writer lacks ObservationRecorder integration | All truth writes produce observation records | ProceduralLayerWriter skips observation recording | P2 | Add ObservationRecorder calls to procedural INSERT and REINFORCE paths | small |

---

## 4. Data Flow & I/O Map

### 4.1 Pipeline Stage Map

| Stage Order | Stage ID | Module | Input Event / Topic | Output Event / Topic | Side Effects | Error Topic | Retry Policy |
| ----------- | -------- | ------ | ------------------- | -------------------- | ------------ | ----------- | ------------ |
| 7 | stage_70_memory_writer | consolidation.memory_writer:v1 | stage_60_status_update completion (R6 Output) | p03.truth.written.v1 | Writes all truth tables (st_epi, st_sem, st_kg_dom, st_kg_edges, st_procedural, st_social, st_prospective, st_vec), st_observations, st_outbox, st_hipp_events status update | R7_COMMIT_ERROR (non-recoverable) | 3x exponential backoff on OptimisticLockError within transaction; TRANSACTION_ROLLBACK retries entire R7 phase (2x per pipeline contract) |

### 4.2 Input Schemas (per stage / module)

**Stage: stage_70_memory_writer**

| # | Field | Type | Required | Nullable | Validation Rule | Source | Example Value |
| - | ----- | ---- | -------- | -------- | --------------- | ------ | ------------- |
| 1 | envelope.staged_writes | P03StagedWrites | yes | no | Must contain at least one layer with writes | R6 staging phase | P03StagedWrites(st_epi=[...], st_sem=[...], ...) |
| 2 | envelope.staged_writes.{layer} | list[StagedWrite] | no | yes | Each write must have record_id, operation, record_data | R6 truth_write_assembler / kg_write_assembler | [StagedWrite(record_id="ep_001", operation="INSERT", ...)] |
| 3 | envelope.cycle_context | P03CycleContext | yes | no | Must have tenant_id, space_id, cycle_id | P03 pipeline runner | P03CycleContext(tenant_id="t1", space_id="s1", cycle_id="01HX...") |
| 4 | envelope.staged_outbox_events | list[StagedOutboxEvent] | no | yes | Each event must have topic and payload | R6 outbox_assembler | [StagedOutboxEvent(topic="p03.episode.formed.v1", ...)] |
| 5 | envelope.event_ids | list[str] | yes | no | Non-empty, valid UUIDs | R0 batch selector | ["evt_abc123", "evt_def456"] |
| 6 | staged_write.record_id | str | yes | no | Non-empty, matches PK column in target table | R6 assemblers | "ep_01HX..." |
| 7 | staged_write.operation | str | yes | no | One of: INSERT, UPDATE, ARCHIVE, TOMBSTONE | R6 assemblers | "INSERT" |
| 8 | staged_write.record_data | dict[str, Any] | yes | no | Keys must match target table columns | R6 assemblers | {"episode_id": "ep_01HX...", "tenant_id": "t1", ...} |
| 9 | staged_write.expected_version | int or None | no | yes | Required for UPDATE operations (optimistic locking) | R6 assemblers | 3 |
| 10 | staged_write.source_event_ids | list[str] | no | yes | Event IDs that triggered this write | R6 assemblers | ["evt_abc123"] |

### 4.3 Output Schemas (per stage / module)

**Stage: stage_70_memory_writer**

| # | Field | Type | Nullable | Produced By | Consumed By | Example Value |
| - | ----- | ---- | -------- | ----------- | ----------- | ------------- |
| 1 | envelope.write_result | WriteResult | no | TransactionCoordinator.execute() / legacy path | R8 event emitter, pipeline summary | WriteResult(total_attempted=42, total_succeeded=42, ...) |
| 2 | envelope.write_result.by_layer | dict[str, LayerWriteResult] | no | DecisionRouter.route() | R8 per-layer event emission | {"st_epi": LayerWriteResult(succeeded=5), ...} |
| 3 | envelope.write_result.total_succeeded | int | no | WriteResult.from_layer_results() | Pipeline metrics | 42 |
| 4 | envelope.write_result.total_failed | int | no | WriteResult.from_layer_results() | Pipeline error handling | 0 |
| 5 | envelope.outbox_staged | int | no | _stage_outbox_events() | R8 event emitter | 15 |
| 6 | envelope.transaction_id | str | no | UoW transaction | Audit trail | "txn_01HX..." |
| 7 | st_hipp_events.consolidation_status | str | no | _writeback_status() | Future P03 cycles (skip already-consolidated) | "CONSOLIDATED" |
| 8 | st_hipp_events.consolidation_cycle_id | str | no | _writeback_status() | Audit trail | "01HX..." |

### 4.4 Error Outputs

| # | Error Code / Type | Condition | HTTP Status | Handling | Downstream Impact | Recoverable? |
| - | ----------------- | --------- | ----------- | -------- | ----------------- | ------------ |
| 1 | R7_COMMIT_ERROR | Any unrecoverable failure during atomic commit | N/A | abort | Entire R7 rolls back, R8 not reached, events remain unconsolidated | no -- recoverable=False, requires re-running from R6 |
| 2 | OptimisticLockError | Version column mismatch on UPDATE (concurrent modification) | N/A | retry (3x) | Transaction retried with refreshed versions; if max retries exceeded, R7_COMMIT_ERROR | yes -- up to max_retries |
| 3 | TRANSACTION_ROLLBACK | PostgreSQL transaction failure (deadlock, timeout, constraint violation) | N/A | retry (2x per contract) | Entire R7 phase re-attempted by pipeline runner | maybe -- depends on root cause |
| 4 | FK_VIOLATION | Foreign key constraint failure (write order incorrect) | N/A | retry_with_deps | Transaction rolled back, dependency order may need adjustment | yes -- retry with corrected order |
| 5 | DecisionRouterError | Layer writer failure in ATOMIC mode | N/A | abort (within transaction) | Partial WriteResult attached, entire transaction rolls back | no -- requires investigation |
| 6 | ValueError | Invalid layer in ObservationRecorder, bad input data | N/A | skip (layer writer catches) | Single write skipped, layer continues with remaining writes | no -- data problem |

### 4.5 Data Transformation Map

| # | Source Field(s) | Transformation | Target Field | Lossy? | Reversible? | Notes |
| - | --------------- | -------------- | ------------ | ------ | ----------- | ----- |
| 1 | staged_write.record_data (all fields) | Direct mapping to SQL INSERT/UPDATE params | truth table columns | no | yes | 1:1 mapping from staged write dict to table columns |
| 2 | staged_write.source_event_ids | TextVectorCoordinator: fetch text -> UltraBERT encode -> 768-dim vector | truth table GAP-001 columns (summary_text, summary_embedding, embedding_model_id, embedding_dimension) | yes | no | Text-to-embedding is one-way; text decays in 20 days from st_hipp_events |
| 3 | staged_write.record_data.sentiment_score + existing sentiment | EMA: old*0.9 + new*0.1 | st_social.avg_sentiment | yes | no | Moving average loses individual observation values |
| 4 | staged_write.record_data.sentiment entries | Append to trajectory, cap at 20 | st_social.sentiment_trajectory | yes | no | Oldest entries dropped when cap reached |
| 5 | staged_write.record_data.confidence + REINFORCE_BOOST | Additive: confidence += 0.05 (capped at 1.0) | st_sem.confidence | no | yes | Reversible by subtracting boost |
| 6 | staged_write.record_data.confidence * REINFORCE_FACTOR | Multiplicative: confidence *= 1.1 (capped at 1.0) | st_procedural.confidence | no | yes | Reversible by dividing |
| 7 | staged_write.record_data.strength * DECAY_FACTOR | Multiplicative: strength *= 0.95 | st_social.strength | no | yes | Reversible by dividing |
| 8 | staged_write (all layers) | ObservationRecorder: extract 32 context fields | st_observations row | no | yes | Lossless observation record |
| 9 | staged_write + envelope context | Outbox fingerprinting: p03:write:{cycle_ulid}:{layer}:{record_id} | st_outbox.idempotency_key | yes | no | Hash-based, not reversible to original components |
| 10 | list[embedding vectors] | numpy aggregation (mean/weighted_mean/max) | st_vec.vector (single 768-dim) | yes | no | Multiple vectors collapsed to one |

---

## 5. Storage & Persistence

### 5.1 Tables Touched

| # | Table | Operation | Key Columns Used | Access Pattern | Index Used | Estimated Row Count |
| - | ----- | --------- | ---------------- | -------------- | ---------- | ------------------- |
| 1 | st_epi | RW | episode_id, tenant_id, space_id, version | point (by episode_id) INSERT/UPDATE | PK (episode_id) | ~100K |
| 2 | st_sem | RW | pattern_id, tenant_id, space_id, version | point (by pattern_id) INSERT/UPDATE | PK (pattern_id) | ~50K |
| 3 | st_kg_dom | RW | entity_id, tenant_id, canonical_name, version | point (by entity_id) INSERT/UPDATE | PK (entity_id) | ~200K |
| 4 | st_kg_edges | RW | edge_id, source_entity_id, target_entity_id, version | point (by edge_id) INSERT/UPDATE | PK (edge_id), FK indexes | ~500K |
| 5 | st_procedural | RW | routine_id, tenant_id, version | point (by routine_id) INSERT/UPDATE | PK (routine_id) | ~10K |
| 6 | st_social | RW | relationship_id, tenant_id, version | point (by relationship_id) INSERT/UPDATE | PK (relationship_id) | ~50K |
| 7 | st_prospective | RW | intention_id, tenant_id, version | point (by intention_id) INSERT/UPDATE | PK (intention_id) | ~20K |
| 8 | st_vec | RW | embedding_id, event_id, tenant_id | point (by embedding_id) INSERT/UPDATE | PK (embedding_id) | ~100K |
| 9 | st_observations | W | observation_id | INSERT only (append) | PK (observation_id) | ~1M (high volume) |
| 10 | st_outbox | W | outbox_id, idempotency_key | INSERT only | PK, unique (idempotency_key) | ~50K |
| 11 | st_hipp_events | RW | event_id, consolidation_status, consolidation_cycle_id | point (by event_id) UPDATE | PK (event_id) | ~500K |
| 12 | st_mcts_decisions | W | decision_id | INSERT only (no ON CONFLICT) | PK (decision_id) | ~5K (DELETE candidate) |
| 13 | st_entity_merges | W | merge_id | INSERT only | PK (merge_id) | ~1K |

### 5.2 Column-Level Detail

> Due to the breadth of R7 (13 tables, 200+ columns), this section documents only the critical columns
> that R7 writes or reads for its core operations. Full column specifications are in the M3/M4 migration files.

| Table | Column | Type | Nullable | Default | Read By | Written By | Indexed? | Notes |
| ----- | ------ | ---- | -------- | ------- | ------- | ---------- | -------- | ----- |
| st_epi | episode_id | TEXT | no | NONE | R7 (point lookup) | R6 assembler -> R7 episodic writer | yes (PK) | ULID format |
| st_epi | version | INTEGER | no | 1 | R7 (optimistic lock check) | R7 episodic writer (INCREMENT) | no | Optimistic locking version column |
| st_epi | source_events_json | JSONB | yes | '[]' | R7 (reinforce merge) | R7 episodic writer | no | jsonb_agg DISTINCT on reinforce |
| st_epi | summary_text | TEXT | yes | NONE | N/A | R7 episodic writer (GAP-001 TVC) | no | Generated by TextVectorCoordinator |
| st_epi | summary_embedding | VECTOR(768) | yes | NONE | N/A | R7 episodic writer (GAP-001 TVC) | yes (HNSW) | UltraBERT v2.1.0 embedding |
| st_sem | pattern_id | TEXT | no | NONE | R7 (point lookup) | R7 semantic writer | yes (PK) | ULID format |
| st_sem | confidence | FLOAT | no | 0.0 | R7 (reinforce read) | R7 semantic writer (+ REINFORCE_BOOST) | no | Capped at 1.0 |
| st_sem | version | INTEGER | no | 1 | R7 (optimistic lock) | R7 semantic writer (INCREMENT) | no | Optimistic locking |
| st_kg_dom | entity_id | TEXT | no | NONE | R7 (point lookup) | R7 KG writer | yes (PK) | ULID format |
| st_kg_dom | canonical_name | TEXT | no | NONE | R7 (INSERT ON CONFLICT) | R7 KG writer | yes (unique) | ON CONFLICT DO UPDATE for canonical_name |
| st_kg_dom | version | INTEGER | no | 1 | R7 (optimistic lock) | R7 KG writer (INCREMENT) | no | Optimistic locking |
| st_kg_edges | edge_id | TEXT | no | NONE | R7 (point lookup) | R7 KG writer | yes (PK) | ULID format |
| st_kg_edges | source_algorithm | TEXT | yes | NONE | N/A | R7 KG writer | no | GAP-007 provenance tracking |
| st_social | relationship_id | TEXT | no | NONE | R7 (point lookup) | R7 social writer | yes (PK) | ULID format |
| st_social | avg_sentiment | FLOAT | yes | NONE | R7 (EMA read) | R7 social writer (EMA update) | no | EMA: old*0.9 + new*0.1 |
| st_social | sentiment_trajectory | JSONB | yes | '[]' | R7 (trajectory read) | R7 social writer (append, cap 20) | no | Rolling window of sentiment values |
| st_social | strength | FLOAT | no | 0.0 | R7 (decay read) | R7 social writer (multiplicative) | no | DECAY_FACTOR=0.95 |
| st_vec | embedding_id | TEXT | no | NONE | R7 (point lookup) | R7 vector writer | yes (PK) | ULID format |
| st_vec | vector | VECTOR(768) | yes | NONE | P08 (search) | R7 vector writer | yes (HNSW cosine) | pgvector native per ADR-K003 |
| st_observations | observation_id | TEXT | no | NONE | N/A | R7 ObservationRecorder | yes (PK) | ULID, 32 columns total |
| st_outbox | idempotency_key | TEXT | no | NONE | R8 (dedup check) | R7 outbox writer | yes (unique) | p03:write:{cycle}:{layer}:{record_id} |
| st_hipp_events | consolidation_status | TEXT | yes | 'PENDING' | R0 batch selector | R7 _writeback_status() | yes (ix_consolidation_status) | Updated to CONSOLIDATED |
| st_hipp_events | consolidation_cycle_id | TEXT | yes | NONE | Audit | R7 _writeback_status() | no | Cycle ULID for traceability |

### 5.3 Query Patterns

| # | Query Purpose | SQL Pattern | Frequency | Expected Latency | Index Coverage | Notes |
| - | ------------- | ----------- | --------- | ---------------- | -------------- | ----- |
| 1 | Insert truth record (per layer) | INSERT INTO {table} (...30+ cols...) VALUES ($1, $2, ...) ON CONFLICT ({pk}) DO NOTHING | per-write | < 5ms | full (PK) | Most layers use ON CONFLICT DO NOTHING except st_kg_dom (DO UPDATE) |
| 2 | Update truth record (reinforce/extend) | UPDATE {table} SET col1=$1, col2=$2, ..., version=version+1 WHERE {pk}=$N AND version=$M | per-write | < 5ms | full (PK) | Optimistic locking via WHERE version=$M |
| 3 | Archive truth record | UPDATE {table} SET status='ARCHIVED', archived_at=NOW() WHERE {pk}=$1 | per-write | < 2ms | full (PK) | Status lifecycle transition |
| 4 | Tombstone truth record | UPDATE {table} SET status='TOMBSTONED', {sensitive_cols}=NULL WHERE {pk}=$1 | per-write | < 2ms | full (PK) | GDPR: nullifies sensitive data |
| 5 | Record observation | INSERT INTO st_observations (...32 cols...) VALUES ($1, $2, ...) | per-write | < 3ms | full (PK) | Every INSERT/MERGE generates an observation |
| 6 | Stage outbox event | INSERT INTO st_outbox (...) VALUES ($1, $2, ...) ON CONFLICT (idempotency_key) DO NOTHING | per-outbox-event | < 2ms | full (unique key) | Fingerprint idempotency prevents duplicates |
| 7 | Update hipp_events status | UPDATE st_hipp_events SET consolidation_status='CONSOLIDATED', consolidation_cycle_id=$2 WHERE event_id=$1 | per-event | < 2ms | full (PK) | Final step in R7 commit |
| 8 | Refresh version (retry) | SELECT version FROM {table} WHERE {pk}=$1 | per-conflict | < 1ms | full (PK) | TransactionCoordinator._refresh_versions on retry |
| 9 | Fetch source texts | SELECT event_id, text FROM st_hipp_events WHERE event_id = ANY($1) AND text IS NOT NULL | per-TVC-call | < 10ms for batch | partial (PK covers event_id) | Text decays after 20 days |
| 10 | Resolve episode events | SELECT source_events_json FROM st_epi WHERE episode_id = ANY($1) | per-TVC-episode-call | < 5ms | full (PK) | Resolves episode IDs to source event IDs |
| 11 | KG entity upsert | INSERT INTO st_kg_dom (...22+ cols...) ON CONFLICT (entity_id) DO UPDATE SET canonical_name=$2 | per-entity-write | < 5ms | full (PK) | Unique: only table with ON CONFLICT DO UPDATE on INSERT |
| 12 | KG edge insert with provenance | INSERT INTO st_kg_edges (...24 cols + GAP-007...) ON CONFLICT DO NOTHING | per-edge-write | < 5ms | full (PK) | Includes source_algorithm, evidence arrays, inference_chain_json |
| 13 | Social EMA sentiment update | UPDATE st_social SET avg_sentiment = avg_sentiment * 0.9 + $1 * 0.1, sentiment_trajectory = ... WHERE relationship_id = $2 AND version = $3 | per-reinforce | < 5ms | full (PK) | Most complex UPDATE: EMA + trajectory append + emotion merge |

### 5.4 Storage Gaps

| # | Gap | Current State | Required State | Migration Needed? | Priority |
| - | --- | ------------- | -------------- | ----------------- | -------- |
| 1 | st_observations has no partition strategy | Single table, append-only, grows unbounded | Time-based partitioning (monthly) for efficient cleanup | yes | P2 |
| 2 | No index on st_observations.layer for analytics queries | Sequential scan for per-layer observation analysis | Composite index on (layer, observed_at) | yes | P3 |
| 3 | st_mcts_decisions accumulates dead writes | Rows never read, no cleanup | Table DELETE or deprecation in M5D | no (code change only) | P3 |
| 4 | No composite index on st_hipp_events(consolidation_status, tenant_id) | Separate indexes | Composite for R0 batch selector query pattern | maybe | P2 |

---

## 6. Event Bus & Topics

### 6.1 Topics Consumed

| # | Topic | Schema | Producer | Consumer | Ordering | Idempotency Key |
| - | ----- | ------ | -------- | -------- | -------- | --------------- |
| 1 | p03.status.updated.v1 | k0/contracts/modules/consolidation.memory_writer.v1.yaml | R6 status marker (stage_60) | R7 truth writer (stage_70) | ordered (within cycle) | cycle_id + event_id |

> R7 does not directly consume bus topics. It is triggered by the P03 pipeline runner after R6 completes.
> The contract lists `p03.status.updated.v1` as the input event type, but in practice R7 reads from the
> envelope populated by R6, not from the bus.

### 6.2 Topics Emitted

| # | Topic | Schema | Emitter | Known Consumers | Payload Size | Frequency |
| - | ----- | ------ | ------- | --------------- | ------------ | --------- |
| 1 | p03.truth.written.v1 | k0/contracts/modules/consolidation.memory_writer.v1.yaml | R7 truth writer (via st_outbox) | R8 event emitter | ~500B | per-cycle |
| 2 | p08.embedding.created.v1 | (P08 contract) | R7 vector writer (via st_outbox) | P08 pipeline | ~300B | per-vector-INSERT |
| 3 | p08.embedding.updated.v1 | (P08 contract) | R7 vector writer (via st_outbox) | P08 pipeline | ~300B | per-vector-UPDATE |
| 4 | p03.episode.formed.v1 | (R6 outbox assembler) | R7 via outbox staging | K1 agents, P08 | ~1KB | per-new-episode |
| 5 | p03.pattern.discovered.v1 | (R6 outbox assembler) | R7 via outbox staging | K1 agents | ~500B | per-new-pattern |
| 6 | p03.gap.detected.v1 | (R6 outbox assembler) | R7 via outbox staging | K1 agents, monitoring | ~300B | per-detected-gap |

> All topics are staged to st_outbox within the R7 transaction. R8 reads st_outbox and publishes
> to the actual event bus. This guarantees exactly-once delivery semantics (transactional outbox pattern).

### 6.3 Topic Gaps (needed but missing)

| # | Proposed Topic | Purpose | Producer | Consumer | Schema Draft | Priority |
| - | -------------- | ------- | -------- | -------- | ------------ | -------- |
| 1 | p03.truth.conflict.v1 | Emit when version conflict occurs and retry succeeds | R7 TransactionCoordinator | Monitoring, analytics | {cycle_id: str, layer: str, record_id: str, attempts: int, final_version: int} | P3 |
| 2 | p03.observation.batch.v1 | Batch observation notification for downstream analytics | R7 ObservationRecorder | Analytics pipeline | {cycle_id: str, observation_count: int, layers: list[str]} | P3 |

---

## 7. Observability Audit

### 7.1 Existing Metrics

| # | Metric Name | Type | Location | Labels | Purpose | Alert Threshold |
| - | ----------- | ---- | -------- | ------ | ------- | --------------- |
| N/A | No explicit metrics defined | N/A | N/A | N/A | R7 relies on structured logging, not Prometheus/OTel metrics | N/A |

> R7 currently has no dedicated metric instrumentation. All observability is via structured logs
> and the WriteResult/TransactionResult dataclasses. This is a significant observability gap.

### 7.2 Existing Traces / Spans

| # | Span Name | Location | Attributes | Parent Span | Purpose |
| - | --------- | -------- | ---------- | ----------- | ------- |
| N/A | No OpenTelemetry spans defined | N/A | N/A | N/A | R7 has no tracing instrumentation |

> R7 has no OpenTelemetry span instrumentation. Pipeline-level tracing exists in the P03 runner
> but does not propagate into R7 layer writers.

### 7.3 Structured Log Points

| # | Log Level | Location | Message Pattern | Fields | Purpose |
| - | --------- | -------- | --------------- | ------ | ------- |
| 1 | INFO | r7_truth_writer.py (run start) | "R7 truth writer starting" | cycle_id, tenant_id, space_id, write_count, layer_counts | Verify R7 invocation and input size |
| 2 | INFO | r7_truth_writer.py (run complete) | "R7 truth writer complete" | cycle_id, total_succeeded, total_failed, duration_ms, outbox_staged | Verify successful atomic commit |
| 3 | ERROR | r7_truth_writer.py (run failure) | "R7 truth writer failed" | cycle_id, error_type, error_message, duration_ms | Diagnose R7 failures |
| 4 | WARNING | r7_truth_writer.py (legacy path) | "R7 using legacy inline SQL path" | cycle_id | Flag deprecated path usage |
| 5 | DEBUG | transaction.py (retry) | "Version conflict, retrying" | layer, record_id, expected_version, attempt | Track optimistic lock conflict rate |
| 6 | WARNING | transaction.py (max retries) | "Max retries exceeded for version conflict" | layer, record_id, attempts | Alert on persistent conflicts |
| 7 | DEBUG | router.py (route start) | "Routing writes to layer" | layer, write_count | Track per-layer routing |
| 8 | WARNING | embedding_generator.py | "Embedding generation failed" | text_length, error | Track embedding failures |
| 9 | WARNING | source_text_fetcher.py | "Text fetch truncated" | requested, truncated_to | Track batch size overflow |
| 10 | DEBUG | observation_recorder.py | "Observation recorded" | layer, record_id, observation_type | Verify observation recording |

### 7.4 Observability Gaps

| # | Gap | What's Missing | Impact if Unresolved | Priority |
| - | --- | -------------- | -------------------- | -------- |
| 1 | No write latency histogram | Histogram metric for per-layer write latency (p50/p95/p99) | Cannot detect slow writes, no SLO monitoring for R7 | P1 |
| 2 | No version conflict counter | Counter metric for optimistic lock conflicts by layer | Cannot detect hot-record contention patterns | P1 |
| 3 | No transaction duration histogram | Histogram for total R7 transaction duration | Cannot monitor transaction timeout risk | P1 |
| 4 | No OpenTelemetry spans | Spans for R7 phase, per-layer routing, transaction coordination | Cannot trace write ordering or pinpoint slow layers in distributed trace | P1 |
| 5 | No observation volume gauge | Gauge for st_observations row count per cycle | Cannot monitor observation table growth rate | P2 |
| 6 | No outbox staging counter | Counter for outbox events staged per cycle | Cannot verify R7-R8 handoff completeness | P2 |
| 7 | No circuit breaker state metric | Gauge for P08 circuit breaker state (open/closed/half-open) | Cannot detect P08 outbox failures silently suppressed | P2 |
| 8 | No embedding generation latency | Histogram for UltraBERT inference time within transaction | Cannot detect model latency impacting transaction timeout | P1 |

---

## 8. Test Coverage Audit

### 8.1 Existing Tests

| # | Test File | Lines | Test Count | Type | Coverage Target | Pass / Fail | Notes |
| - | --------- | ----: | ---------: | ---- | --------------- | ----------- | ----- |
| 1 | tests/k0/modules/consolidation/truth_writer/test_result.py | 294 | 25 | unit | result.LayerWriteResult, result.WriteResult | PASS | Factories, flags, aggregation, to_dict, to_summary |
| 2 | tests/k0/modules/consolidation/truth_writer/test_router.py | 420 | 19 | unit | router.DecisionRouter | PASS | Routing, ATOMIC/PARTIAL modes, error handling, StubLayerWriter protocol |
| 3 | tests/k0/modules/consolidation/truth_writer/test_outbox.py | 381 | 22 | unit | outbox.OutboxWriter, OutboxWriteConfig | PASS | Config defaults, staging, fingerprinting, batch staging, event staging |
| 4 | tests/k0/modules/consolidation/truth_writer/test_transaction.py | 458 | 24 | unit | transaction.TransactionCoordinator, TransactionConfig, OptimisticLockError | PASS | Retry logic, backoff, max retries, capability validation, LAYER_PK_MAP coverage |
| 5 | tests/k0/modules/consolidation/truth_writer/test_observation_recorder.py | 469 | 17 | unit | observation_recorder.ObservationRecorder | PASS | ULID generation, all context fields, layer validation, insert vs merge, batch, edge cases |
| 6 | tests/k0/modules/consolidation/truth_writer/test_episodic.py | 417 | 20 | unit | layers.episodic.EpisodicLayerWriter | PASS | INSERT all columns, UPDATE with optimistic lock, reinforce temporal bounds, archive, tombstone |
| 7 | tests/k0/modules/consolidation/truth_writer/test_semantic.py | 578 | 28 | unit | layers.semantic.SemanticLayerWriter, PatternAction | PASS | REINFORCE_BOOST, extend episodes, evolve marks non-canonical, result parsing |
| 8 | tests/k0/modules/consolidation/truth_writer/test_kg.py | 1,042 | 39 | unit | layers.kg.KGLayerWriter, EntityWriteData, EdgeWriteData | PASS | Entity/edge INSERT/UPDATE/ARCHIVE/TOMBSTONE, track_merge, query_boost, milestone_append, mixed writes |
| 9 | tests/k0/modules/consolidation/truth_writer/test_procedural.py | 476 | 23 | unit | layers.procedural.ProceduralLayerWriter | PASS | REINFORCE_FACTOR, INSERT all columns, version conflict, archive, tombstone |
| 10 | tests/k0/modules/consolidation/truth_writer/test_social.py | 578 | 26 | unit | layers.social.SocialLayerWriter, RelationshipAction | PASS | REINFORCE/EXTEND/DECAY, EMA sentiment, strength boost, version conflict |
| 11 | tests/k0/modules/consolidation/truth_writer/test_prospective.py | 660 | 28 | unit | layers.prospective.ProspectiveLayerWriter, IntentionAction | PASS | EXTEND/COMPLETE/COUNTERFACTUAL, lifecycle transitions, TOMBSTONE GDPR, mixed ops |
| 12 | tests/k0/modules/consolidation/truth_writer/test_vector.py | 600 | 29 | unit | layers.vector.VectorLayerWriter, P08CircuitBreakerConfig | PASS | P08 events, circuit breaker open/close/half-open, embedding aggregation, TOMBSTONE |
| 13 | tests/k0/modules/consolidation/truth_writer/test_text_vector_coordinator.py | 490 | 23 | unit | text_vector_coordinator, source_text_fetcher, embedding_generator | PASS | GAP-001 pipeline, SourceTextBatch, EmbeddingGenerator failure, factory singleton |
| 14 | tests/k0/pipelines/p03/test_r7_r8_integration.py | 898 | 16 | integration | R7+R8 end-to-end: atomicity, outbox staging, publisher, DLQ | PASS | R7 atomicity, R8 completion payload, fingerprint dedup, gap context, offset commit |
| 15 | tests/k0/pipelines/p03/test_r7_r6_integration.py | 246 | 7 | integration | R7 consuming R6 output | PASS | R6Output field existence, fallback without R6, logging of has_r6_output flag |
| 16 | tests/k0/pipelines/p03/test_r7_m5_wiring.py | 388 | 11 | integration | M5 router wiring: coordinator creation, layer writer registration | PASS | M5 enable/disable, coordinator reuse, all layer writers registered, legacy path warning |
| **TOTAL** | | **7,404** | **357** | | | | |

### 8.2 Coverage Gaps

| # | Gap | What's Untested | Risk Level | Proposed Test | Test Type |
| - | --- | --------------- | ---------- | ------------- | --------- |
| 1 | No concurrent write test | Two R7 transactions targeting same records (optimistic lock race) | P1 | test_concurrent_r7_version_conflict: run 2 parallel R7 cycles, assert retry succeeds and no data corruption | integration |
| 2 | No MCTSLayerWriter duplicate PK test | INSERT without ON CONFLICT hitting existing PK | P2 | test_mcts_duplicate_insert_raises: insert same decision_id twice, assert IntegrityError | unit |
| 3 | No embedding generation timeout test | UltraBERT slow response causing transaction timeout | P1 | test_embedding_timeout_within_transaction: mock slow generator, assert transaction completes within timeout | integration |
| 4 | No large batch write test | 1000+ staged writes in single transaction | P2 | test_large_batch_write_performance: stage 1000 writes across layers, assert completion < 30s | integration |
| 5 | No text decay edge case | Source text expired (>20 days), embedding generation fails | P2 | test_text_fetch_after_decay: set text to NULL, verify TVC returns empty, layer writer handles gracefully | unit |
| 6 | No partial mode routing test with real writers | PARTIAL mode with real layer writers (not stubs) | P2 | test_partial_mode_continues_on_real_failure: inject failure in one layer, assert others succeed | integration |
| 7 | No st_observations volume test | High observation count (100+ per cycle) | P3 | test_observation_volume: generate 100 writes, verify 100 observations inserted | unit |
| 8 | No KG entity merge tracking test with real DB | track_merge with real st_entity_merges table | P2 | test_kg_merge_tracking_integration: merge two entities, verify merge record | integration |

### 8.3 Test Infrastructure Needs

| # | Need | Current State | Required State | Blocking Epic? |
| - | ---- | ------------- | -------------- | -------------- |
| 1 | UoW test fixture with real PostgreSQL | Tests use mock UoW with mock execute() | Real UoW with test database for integration tests | no (unit tests work with mocks) |
| 2 | Multi-table transaction fixture | Each layer writer tested in isolation | Fixture that creates all 13 tables, runs R7, validates all tables atomically | 5.8 (for full integration test) |
| 3 | UltraBERT test mock with configurable latency | Static mock that returns immediately | Mock with configurable delay for timeout testing | no |
| 4 | Concurrent R7 test harness | No concurrent test infrastructure | asyncio-based concurrent R7 runner with shared DB | no |

---

## 9. Dependency Map

### 9.1 Upstream (what this pipeline / module needs)

| # | Dependency | Type | Status | Owner Milestone | Gap if Missing |
| - | ---------- | ---- | ------ | --------------- | -------------- |
| 1 | R6 staging output (P03StagedWrites) | module | ready | M5 | R7 has no writes to execute |
| 2 | R6 outbox assembly (StagedOutboxEvent) | module | ready | M5 | R7 cannot stage outbox events for R8 |
| 3 | UnitOfWork (k0.uow) | module | ready | M4 | R7 cannot open transactions |
| 4 | st_epi table | table | ready | M3 | Episodic writes fail |
| 5 | st_sem table | table | ready | M3 | Semantic writes fail |
| 6 | st_kg_dom table | table | ready | M3 | KG entity writes fail |
| 7 | st_kg_edges table | table | ready | M3 | KG edge writes fail |
| 8 | st_procedural table | table | ready | M3 | Procedural writes fail |
| 9 | st_social table | table | ready | M3 | Social writes fail |
| 10 | st_prospective table | table | ready | M3 | Prospective writes fail |
| 11 | st_vec table | table | ready | M4 | Vector writes fail (pgvector VECTOR(768)) |
| 12 | st_observations table | table | ready | M3 | ObservationRecorder fails |
| 13 | st_outbox table | table | ready | M3 | Outbox staging fails, R8 receives no events |
| 14 | st_hipp_events table | table | ready | M2 | Status writeback fails |
| 15 | UltraBERT v2.1.0 adapter | service | ready | M4 | EmbeddingGenerator returns None, GAP-001 columns empty |
| 16 | pgvector extension | library | ready | M4 | VECTOR(768) type unavailable, st_vec broken |
| 17 | P03CycleContext | module | ready | M5 | No tenant/space/cycle context for writes |

### 9.2 Downstream (what depends on this)

| # | Dependent | Type | How Used | Impact if Changed | Owner Milestone |
| - | --------- | ---- | -------- | ----------------- | --------------- |
| 1 | R8 event emitter (stage_80) | pipeline | Reads st_outbox entries staged by R7 | R8 receives no events if outbox staging format changes | M5 |
| 2 | P08 pipeline | pipeline | Consumes p08.embedding.created/updated events from R7 vector writer | P08 embedding pipeline breaks if event schema changes | M4 |
| 3 | K1 agents | module | Consume p03.episode.formed, p03.pattern.discovered, p03.gap.detected events | Agent behavior affected if event payloads change | M5 |
| 4 | Future P03 cycles (R0 batch selector) | pipeline | R0 filters events by consolidation_status = 'PENDING' (R7 sets to 'CONSOLIDATED') | Events reprocessed if status writeback fails | M5 |
| 5 | Monitoring / analytics | service | Query st_observations for write audit trail | Observation schema changes break analytics queries | M5 |

### 9.3 External Dependencies (libraries, services, extensions)

| # | Dependency | Version | Purpose | License | Pinned? | Upgrade Risk |
| - | ---------- | ------- | ------- | ------- | ------- | ------------ |
| 1 | pgvector | 0.2.4 | PostgreSQL vector similarity search (VECTOR(768) type, HNSW index) | PostgreSQL | yes | low |
| 2 | numpy | >=1.24 | Embedding aggregation (mean, weighted_mean, max) in VectorLayerWriter | BSD-3-Clause | no (range) | low |
| 3 | asyncpg | >=0.28 | PostgreSQL async driver for UoW.execute() | Apache-2.0 | no (range) | low |
| 4 | UltraBERT v2.1.0 (internal) | v2.1.0 | 768-dim text embeddings for GAP-001 columns | internal | yes (model version) | medium (model update requires migration) |

---

## 10. Performance Baseline

### 10.1 Current Benchmarks

| # | Operation | Dataset Size | p50 | p95 | p99 | Throughput | Memory Peak | Notes |
| - | --------- | ------------ | --- | --- | --- | ---------- | ----------- | ----- |
| 1 | Single layer INSERT | 1 row | ~2ms | ~5ms | ~10ms | ~450/s | ~50MB | Local PostgreSQL 16, pgvector 0.2.4, estimated from test timings |
| 2 | Full R7 cycle (typical) | ~40 writes across 8 layers | ~50ms | ~200ms | ~500ms | ~20 cycles/s | ~100MB | Includes observation recording and outbox staging |
| 3 | UltraBERT embedding (per text) | 1 text (avg 500 chars) | ~10ms | ~30ms | ~50ms | ~100/s | ~200MB | Synchronous within transaction, blocks commit |
| 4 | ObservationRecorder batch | 40 observations | ~80ms | ~150ms | ~300ms | N/A | ~50MB | Sequential INSERT, not batch |

> **Note**: No formal benchmark suite exists for R7. These estimates are derived from test execution
> timings and extrapolation. A dedicated benchmark is needed (Section 10.3).

### 10.2 Known Bottlenecks

| # | Bottleneck | Location | Cause | Measured Impact | Proposed Fix | Priority |
| - | ---------- | -------- | ----- | --------------- | ------------ | -------- |
| 1 | Synchronous embedding generation | embedding_generator.py:42 | UltraBERT inference runs synchronously within transaction, blocking commit | Adds ~10-30ms per text embedding within transaction hold | Move embedding generation before transaction open, or use pre-computed embeddings | P1 |
| 2 | Sequential observation recording | observation_recorder.py:52 | record_batch() calls record() in a loop, one INSERT per observation | ~2ms per observation * 40 obs = ~80ms per cycle | Use executemany or multi-row INSERT VALUES | P2 |
| 3 | Full batch retry on version conflict | transaction.py | Entire P03StagedWrites re-routed on any single OptimisticLockError | All layers re-written on retry, multiplying write cost by attempt count | Track conflicting rows, retry only those writes | P2 |
| 4 | LAYER_PK_MAP duplication | r7_truth_writer.py:53, transaction.py | Same map defined twice, maintenance risk and potential desync | No runtime impact, but code maintenance risk | Extract to shared constant module | P3 |
| 5 | Transaction hold time | r7_truth_writer.py | Long transaction with embedding gen + observation recording + outbox staging | Transaction timeout risk at 30s budget with 100+ writes | Pipeline: embed first, then open short transaction for writes only | P1 |

### 10.3 Performance Targets

| # | Operation | Target p95 | Target Throughput | Target Memory | Acceptance Criteria |
| - | --------- | ---------- | ----------------- | ------------- | ------------------- |
| 1 | Full R7 cycle (50 writes) | < 500ms | > 10 cycles/s | < 256MB | Benchmark with 50 staged writes across 8 layers completes in < 500ms p95 |
| 2 | Full R7 cycle (200 writes) | < 2000ms | > 5 cycles/s | < 512MB | Benchmark with 200 staged writes completes within transaction timeout |
| 3 | Single layer write | < 10ms | > 100/s per layer | < 50MB | Per-layer write latency histogram p95 < 10ms |
| 4 | Observation recording (batch 50) | < 50ms | > 1000 obs/s | < 50MB | Batch INSERT of 50 observations in < 50ms |
| 5 | Transaction retry (1 conflict) | < 300ms overhead | N/A | N/A | Single retry with backoff adds < 300ms to total cycle time |

---

## 11. Gap Analysis & Enhancement Register

### 11.1 Functional Gaps

| # | Gap ID | Gap Description | Current State | Desired State | Severity | Proposed Fix | Related ADR |
| - | ------ | --------------- | ------------- | ------------- | -------- | ------------ | ----------- |
| 1 | FG-001 | MCTSLayerWriter writes dead data to st_mcts_decisions | INSERT executes but data is never read by any consumer | Remove MCTSLayerWriter entirely in M5D cleanup | P3 | Delete MCTSLayerWriter, remove from router registration, clean up __init__.py exports | none (M5D deprecation) |
| 2 | FG-002 | LAYER_PK_MAP duplicated in two files | r7_truth_writer.py and transaction.py each define the same 10-entry map | Single source of truth for layer-to-PK mapping | P2 | Extract to shared constant module (e.g., truth_writer/constants.py) | none |
| 3 | FG-003 | MCTSLayerWriter missing from __init__.py exports | Both __init__.py files omit MCTSLayerWriter from __all__ | Either add to exports or remove writer entirely | P3 | Align with FG-001 (remove if M5D, add to exports if retained) | none |
| 4 | FG-004 | ProceduralLayerWriter lacks ObservationRecorder | 5 of 6 truth layer writers record observations; procedural does not | All truth writes produce observation records | P2 | Add ObservationRecorder integration to ProceduralLayerWriter INSERT and REINFORCE | none |
| 5 | FG-005 | TransactionCoordinator._validate_capabilities is a no-op | Placeholder method returns immediately without any validation | Validate that caller has required K0 capabilities before write | P2 | Implement capability check when K0 capability system is available | none (future capability ADR) |
| 6 | FG-006 | MCTSLayerWriter INSERT is not idempotent | INSERT has no ON CONFLICT clause, will raise on duplicate PK | Idempotent INSERT with ON CONFLICT DO NOTHING | P3 | Add ON CONFLICT DO NOTHING (or align with FG-001 deletion) | none |
| 7 | FG-007 | R7 cannot resume mid-transaction | resume_from=R6_STAGE required; no savepoint within R7 | Resume from last successful layer within R7 | P2 | Add savepoints per-layer within UoW for partial resume | none |

### 11.2 Contract Gaps

| # | Contract | Section / Field | Gap | Impact | Fix |
| - | -------- | --------------- | --- | ------ | --- |
| 1 | consolidation.memory_writer.v1.yaml | side_effects | Missing write:st_social, write:st_mcts_decisions, write:st_entity_merges, write:st_observations | Contract under-reports side effects -- consumers may not know about all writes | Add all 13 table writes to side_effects list |
| 2 | consolidation.memory_writer.v1.yaml | description.Write Order | Order lists 9 steps but code has 10+ layers (missing st_mcts_decisions, st_entity_merges, st_observations) | Documentation drift from implementation | Update order to match actual code execution |
| 3 | consolidation.memory_writer.v1.yaml | failure_modes | Missing EMBEDDING_TIMEOUT failure mode for synchronous UltraBERT within transaction | Unhandled failure mode in contract | Add EMBEDDING_TIMEOUT with fallback:skip_embedding policy |
| 4 | p03_consolidation.v1.yaml | stage_70.description.Order | Write order differs from code (contract: st_kg_dom first; code: st_vec first via dependency order) | Misleading documentation | Align contract order with actual dependency-ordered code execution |

### 11.3 Architecture Gaps

| # | Area | Gap | ADR Needed? | Impact | Proposed Resolution |
| - | ---- | --- | ----------- | ------ | ------------------- |
| 1 | transaction management | Embedding generation inside transaction holds lock longer than necessary | yes | Transaction timeout risk, 30s budget consumed by model inference | ADR for pre-transaction embedding pipeline: compute embeddings before UoW.begin(), pass into layer writers |
| 2 | observability | No metrics, traces, or SLO monitoring for R7 | no | Cannot detect performance degradation or failures in production | Add OTel spans per-phase and per-layer, add write latency histograms, conflict counters |
| 3 | module protocol | R7 bypasses syscall layer for all DB operations | update | Syscall-level authorization, auditing, and rate limiting not applied to R7 writes | ADR update for "transaction-mode syscalls" that participate in existing UoW |
| 4 | retry strategy | Full batch retry on single-row version conflict | no | Unnecessary re-writes of non-conflicting rows | Implement per-row conflict tracking in TransactionCoordinator |
| 5 | storage growth | st_observations grows unbounded with no partition or retention | yes | Table becomes unmanageably large in production | ADR for st_observations partitioning strategy (monthly time-based) |

---

## 12. Security & Privacy Audit

### 12.1 Data Classification

| # | Field / Column | Classification | Handling | Retention Policy | Notes |
| - | -------------- | -------------- | -------- | ---------------- | ----- |
| 1 | st_epi.summary_text | PII | plain | until tenant deletion | Generated text summary of user episodes -- contains PII-derived content |
| 2 | st_epi.summary_embedding | internal | plain | until tenant deletion | UltraBERT embedding of summary_text -- not PII itself but derived from PII |
| 3 | st_sem.pattern_text | PII | plain | until tenant deletion | Semantic pattern text derived from user behavior |
| 4 | st_kg_dom.canonical_name | internal | plain | until tenant deletion | Entity names (may include person names = PII) |
| 5 | st_kg_edges.evidence_json | PII | plain | until tenant deletion | Evidence arrays may contain user-generated content |
| 6 | st_social.emotion_json | confidential | plain | until tenant deletion | Emotional state data classified as sensitive health info |
| 7 | st_social.sentiment_trajectory | confidential | plain | until tenant deletion | Rolling sentiment history -- sensitive behavioral data |
| 8 | st_prospective.goal_text | PII | plain | until tenant deletion | User goals and intentions -- directly PII |
| 9 | st_hipp_events.text | PII | plain | 20 days (text decay) | User-generated text content, decays automatically |
| 10 | st_observations (all context fields) | internal | plain | indefinite (no retention policy) | Observation metadata -- temporal, emotional, social, location context |
| 11 | st_observations.location_name | PII | plain | indefinite | User location data -- directly PII |
| 12 | st_observations.geohash_6 | PII | plain | indefinite | Geospatial location at ~1.2km precision -- PII |

### 12.2 Capability Boundaries

| # | Operation | Required Capability | Enforced? | Enforcement Location | Gap |
| - | --------- | ------------------- | --------- | -------------------- | --- |
| 1 | Write to all truth tables | cap:write_memories (per contract) | no | N/A | TransactionCoordinator._validate_capabilities is a no-op placeholder |
| 2 | Write to st_observations | cap:write_observations | no | N/A | No capability check -- any module with UoW can write observations |
| 3 | Write to st_outbox | cap:stage_outbox | no | N/A | No capability check on outbox staging |
| 4 | Update st_hipp_events status | cap:update_events | no | N/A | No capability check on event status writeback |
| 5 | Read st_hipp_events text | cap:read_events | no | N/A | SourceTextFetcher reads text without capability check |

> **Critical gap**: R7 has zero capability enforcement despite the contract specifying `fabric_capabilities: [write_memories]`.
> The `_validate_capabilities()` method in TransactionCoordinator is a no-op. All capability checks are deferred to the
> future K0 capability system implementation.

### 12.3 Input Validation & Sanitization

| # | Input Source | Validation Applied | Sanitization Applied | Injection Risk | Notes |
| - | ----------- | ------------------ | -------------------- | -------------- | ----- |
| 1 | P03StagedWrites (from R6) | Type check (dataclass), non-empty check | none | none | Structured data from trusted upstream phase, not user input |
| 2 | StagedWrite.record_data (dict) | Keys checked against expected columns per layer writer | none | low | Parameterized queries ($1, $2, ...) prevent SQL injection |
| 3 | StagedWrite.record_id (str) | Non-empty check in layer writers | none | none | Used only in parameterized WHERE clauses |
| 4 | StagedWrite.expected_version (int) | Type check (int), used in WHERE version=$N | none | none | Parameterized, cannot inject |
| 5 | ObservationRecorder.layer (str) | Validated against VALID_LAYERS frozenset | none | none | Raises ValueError if not in whitelist |
| 6 | Embedding text (from st_hipp_events) | Length check (MAX_TEXT_LENGTH=2000), truncated if exceeded | none | none | Text used only for embedding model input, not SQL |
| 7 | JSONB fields (record_data dicts) | Serialized via json.dumps (KG _normalize_json) | none | low | JSON serialization prevents injection into JSONB columns |

> **Overall injection risk**: Low. All SQL is parameterized. No user input reaches R7 directly -- all data
> passes through R6 staging validation first. The primary risk surface is JSONB columns where arbitrary
> dict values are serialized, but json.dumps handles this safely.

---

## 13. Enhancement Proposals

### 13.1 Proposed Epics

| Epic ID | Title | Scope Summary | Estimated Files | Priority | Dependencies | Issue Count |
| ------- | ----- | ------------- | --------------- | -------- | ------------ | ----------- |
| 5.08.1 | R7 Observability Instrumentation | Add OTel spans, write latency histograms, conflict counters, and circuit breaker metrics to all R7 components | 0 NEW, 8 MOD | P1 | none | 4 |
| 5.08.2 | R7 Transaction Optimization | Move embedding generation before transaction, batch observation recording, implement per-row retry | 1 NEW, 4 MOD | P1 | none | 3 |
| 5.08.3 | R7 Shared Constants Extraction | Extract LAYER_PK_MAP and shared constants to single module, eliminate duplication | 1 NEW, 3 MOD | P2 | none | 2 |
| 5.08.4 | R7 MCTSLayerWriter Cleanup (M5D) | Remove dead MCTSLayerWriter code and st_mcts_decisions writes | 0 NEW, 5 MOD (delete) | P3 | M5D milestone | 2 |
| 5.08.5 | R7 ProceduralLayerWriter Observation Gap | Add ObservationRecorder integration to ProceduralLayerWriter | 0 NEW, 2 MOD | P2 | none | 1 |
| 5.08.6 | R7 Contract Alignment | Update memory_writer contract to reflect actual side effects, write order, and failure modes | 0 NEW, 2 MOD | P2 | none | 2 |

### 13.2 Epic Detail

---

#### Epic 5.08.1 -- R7 Observability Instrumentation

**Summary**: Adds OpenTelemetry spans, Prometheus-style metrics, and structured observability to all R7 components.

**Problem**: R7 has zero metrics and zero tracing instrumentation, making production monitoring impossible.

**Solution**: Instrument R7 with OTel spans per-phase and per-layer, add write latency histograms, version conflict counters, and circuit breaker state gauges.

##### Inputs

| # | Input | Type | Source | Validation |
| - | ----- | ---- | ------ | ---------- |
| 1 | OTel tracer | Tracer | k0.telemetry | Must be initialized before R7 runs |
| 2 | Metrics registry | MetricsRegistry | k0.obs | Must support counter, histogram, gauge |

##### Outputs

| # | Output | Type | Consumer | Guarantees |
| - | ------ | ---- | -------- | ---------- |
| 1 | r7.write.latency histogram | histogram (per-layer) | Grafana dashboards | p50/p95/p99 per layer |
| 2 | r7.version_conflicts_total counter | counter (per-layer) | Alert manager | Monotonically increasing |
| 3 | r7.transaction.duration histogram | histogram | SLO monitoring | Includes all retry attempts |
| 4 | r7.p08_circuit_breaker gauge | gauge | Monitoring | 0=closed, 1=half-open, 2=open |

##### Algorithm Changes

| # | Algorithm | Change Type | Before | After | Rationale |
| - | --------- | ----------- | ------ | ----- | --------- |
| N/A | No algorithm changes | N/A | N/A | N/A | Pure instrumentation, no logic changes |

##### Config Changes

| # | Key / Variable / Flag | Change | Old Value | New Value | Type | Notes |
| - | --------------------- | ------ | --------- | --------- | ---- | ----- |
| 1 | r7.telemetry.enabled | add | N/A | true | bool | Feature flag to enable/disable R7 telemetry |

##### Contract Changes

| # | Contract File | Change | Section | Details |
| - | ------------- | ------ | ------- | ------- |
| N/A | No contract changes | N/A | N/A | Observability is implementation detail, not contract surface |

##### Storage Changes

| # | Table | Operation | Column(s) | Migration File | Reversible? |
| - | ----- | --------- | --------- | -------------- | ----------- |
| N/A | No storage changes | N/A | N/A | N/A | N/A |

##### Syscall Changes

| # | Syscall | Change | Before Signature | After Signature | Notes |
| - | ------- | ------ | ---------------- | --------------- | ----- |
| N/A | No syscall changes | N/A | N/A | N/A | N/A |

##### Event / Topic Changes

| # | Topic | Change | Schema Change | Impact |
| - | ----- | ------ | ------------- | ------ |
| N/A | No topic changes | N/A | N/A | N/A |

##### Test Plan

| # | Test File | Test Name | Type | What It Proves | Priority |
| - | --------- | --------- | ---- | -------------- | -------- |
| 1 | tests/k0/pipelines/p03/test_r7_observability.py | test_write_latency_histogram_emitted | unit | Histogram metric emitted for each layer write | P0 |
| 2 | tests/k0/pipelines/p03/test_r7_observability.py | test_version_conflict_counter_incremented | unit | Conflict counter incremented on OptimisticLockError | P0 |
| 3 | tests/k0/pipelines/p03/test_r7_observability.py | test_otel_spans_created | unit | OTel spans created for R7 phase and per-layer routing | P1 |
| 4 | tests/k0/pipelines/p03/test_r7_observability.py | test_circuit_breaker_gauge_reflects_state | unit | P08 circuit breaker gauge changes on open/close | P1 |

##### Risks

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | Telemetry overhead adds latency to R7 transaction | low | med | Benchmarking before/after; keep span count minimal |
| 2 | Metric cardinality explosion from layer labels | low | low | Fixed set of 10 layers, bounded cardinality |

##### Acceptance Criteria

- [ ] Given an R7 cycle completing, when Prometheus scrapes, then write latency histograms exist for each layer
- [ ] Given a version conflict retry, when the conflict counter is queried, then count > 0 with correct layer label
- [ ] Given OTel tracing enabled, when R7 runs, then spans exist for r7.phase, r7.route.{layer}, r7.transaction
- [ ] Given P08 circuit breaker opens, when gauge is queried, then value = 2

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.08.1.1 | Add OTel spans to R7 phase and router | Instrument r7_truth_writer.py and router.py with spans | M | none | OTel spans appear in trace for r7.phase and per-layer routing |
| 5.08.1.2 | Add write latency histograms | Add histogram metric to each layer writer write() method | M | none | Histogram metrics emitted per layer per cycle |
| 5.08.1.3 | Add version conflict counter | Instrument TransactionCoordinator retry path with counter | S | none | Counter incremented on each OptimisticLockError |
| 5.08.1.4 | Add circuit breaker gauge | Expose P08 circuit breaker state as gauge metric | S | none | Gauge reflects closed/half-open/open state transitions |

---

#### Epic 5.08.2 -- R7 Transaction Optimization

**Summary**: Reduces R7 transaction hold time by moving embedding generation before transaction open and batching observation recording.

**Problem**: UltraBERT inference runs synchronously within the UoW transaction, consuming up to 30ms per text and risking the 30s timeout budget. ObservationRecorder uses sequential INSERTs.

**Solution**: Pre-compute embeddings before UoW.begin(), pass results into layer writers. Replace sequential observation INSERTs with multi-row batch INSERT.

##### Inputs

| # | Input | Type | Source | Validation |
| - | ----- | ---- | ------ | ---------- |
| 1 | Staged writes with text fields | P03StagedWrites | R6 output | Non-empty |
| 2 | Pre-computed embeddings | dict[str, GeneratedEmbedding] | Pre-transaction TVC | All texts embedded before transaction |

##### Outputs

| # | Output | Type | Consumer | Guarantees |
| - | ------ | ---- | -------- | ---------- |
| 1 | Reduced transaction hold time | float (ms) | SLO monitoring | Transaction < 10s for 200 writes (was < 30s) |
| 2 | Batch observation INSERT | int (rows) | st_observations | All observations in single INSERT |

##### Algorithm Changes

| # | Algorithm | Change Type | Before | After | Rationale |
| - | --------- | ----------- | ------ | ----- | --------- |
| 1 | embedding_generation | modify | Synchronous within transaction | Pre-computed before UoW.begin(), cached in dict | Removes model inference from transaction hold |
| 2 | observation_recording | modify | Sequential record() calls in loop | Multi-row INSERT VALUES with executemany | Reduces DB round-trips from N to 1 |
| 3 | optimistic_lock_retry | modify | Retries entire P03StagedWrites | Retries only conflicting rows | Reduces retry cost proportional to conflict rate |

##### Config Changes

| # | Key / Variable / Flag | Change | Old Value | New Value | Type | Notes |
| - | --------------------- | ------ | --------- | --------- | ---- | ----- |
| 1 | r7.pre_transaction_embedding | add | N/A | true | bool | Enable pre-transaction embedding computation |

##### Contract Changes

| # | Contract File | Change | Section | Details |
| - | ------------- | ------ | ------- | ------- |
| N/A | No contract changes | N/A | N/A | Internal optimization, contract surface unchanged |

##### Storage Changes

| # | Table | Operation | Column(s) | Migration File | Reversible? |
| - | ----- | --------- | --------- | -------------- | ----------- |
| N/A | No storage changes | N/A | N/A | N/A | N/A |

##### Syscall Changes

| # | Syscall | Change | Before Signature | After Signature | Notes |
| - | ------- | ------ | ---------------- | --------------- | ----- |
| N/A | No syscall changes | N/A | N/A | N/A | N/A |

##### Event / Topic Changes

| # | Topic | Change | Schema Change | Impact |
| - | ----- | ------ | ------------- | ------ |
| N/A | No topic changes | N/A | N/A | N/A |

##### Test Plan

| # | Test File | Test Name | Type | What It Proves | Priority |
| - | --------- | --------- | ---- | -------------- | -------- |
| 1 | tests/k0/pipelines/p03/test_r7_transaction_opt.py | test_embedding_computed_before_transaction | integration | Embeddings available before UoW.begin() is called | P0 |
| 2 | tests/k0/pipelines/p03/test_r7_transaction_opt.py | test_observation_batch_insert | unit | 50 observations inserted in single SQL statement | P0 |
| 3 | tests/k0/pipelines/p03/test_r7_transaction_opt.py | test_per_row_retry_only_conflicting | integration | Retry targets only version-conflicted rows, non-conflicting layers not re-written | P1 |

##### Risks

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | Pre-computed embeddings become stale if source text changes between fetch and write | low | med | Source text is immutable after R6 staging |
| 2 | Batch observation INSERT may fail atomically if one row is invalid | low | low | Validate all observation data before batch INSERT |

##### Acceptance Criteria

- [ ] Given 50 staged writes with text fields, when R7 runs, then no UltraBERT calls occur within UoW transaction
- [ ] Given 50 observations, when batch is recorded, then 1 SQL statement executes (not 50)
- [ ] Given 1 version conflict out of 50 writes, when retry occurs, then only the conflicting layer is re-written

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.08.2.1 | Pre-transaction embedding pipeline | Compute all embeddings before UoW.begin(), inject as pre-computed dict | L | none | No UltraBERT calls within transaction context |
| 5.08.2.2 | Batch observation recording | Replace sequential record() with multi-row INSERT VALUES | M | none | Single SQL statement for N observations |
| 5.08.2.3 | Per-row conflict retry | Track conflicting writes, rebuild reduced StagedWrites for retry | M | none | Retry cost proportional to conflict count, not total write count |

---

## 14. Risk Register

| # | Risk ID | Risk | Category | Likelihood | Impact | Risk Score | Mitigation | Owner | Status |
| - | ------- | ---- | -------- | ---------- | ------ | ---------- | ---------- | ----- | ------ |
| 1 | R-001 | Transaction timeout under high write volume (>200 writes + embeddings) | performance | med | high | high | Move embedding generation before transaction; implement transaction budget monitoring | dev-lead | open |
| 2 | R-002 | st_observations unbounded growth causes storage exhaustion | performance | high | high | high | Implement time-based partitioning and retention policy for st_observations | dev-lead | open |
| 3 | R-003 | Version conflict storm during concurrent P03 cycles targeting same records | technical | low | high | medium | Exponential backoff already implemented; add conflict rate monitoring and circuit breaker | dev-lead | mitigated |
| 4 | R-004 | MCTSLayerWriter dead writes accumulate indefinitely | technical | high | low | medium | Planned deletion in M5D; no runtime impact beyond wasted I/O | dev-lead | accepted |
| 5 | R-005 | No capability enforcement allows any module to execute R7 writes | security | med | med | medium | Placeholder exists; implement when K0 capability system is available | security-lead | open |
| 6 | R-006 | Legacy inline SQL path diverges from M5 router path over time | technical | med | med | medium | Remove legacy path once M5 router is proven stable (track via USE_M5_ROUTER flag) | dev-lead | open |
| 7 | R-007 | Source text decay (20 days) causes missing embeddings for late consolidation | technical | low | med | low | P03 typically runs within hours of ingestion; add monitoring for consolidation lag > 7 days | dev-lead | accepted |
| 8 | R-008 | LAYER_PK_MAP desync between r7_truth_writer.py and transaction.py | technical | med | high | high | Extract to shared constant module (Epic 5.08.3) | dev-lead | open |
| 9 | R-009 | P08 circuit breaker silently suppresses embedding update notifications | technical | low | med | low | Add circuit breaker state metric (Epic 5.08.1) for monitoring | dev-lead | open |

---

## 15. Open Questions

| # | Question | Context | Blocking? | Answer | Status | Answered By | Date |
| - | -------- | ------- | --------- | ------ | ------ | ----------- | ---- |
| 1 | Should R7 use SERIALIZABLE or READ COMMITTED isolation level? | Contract says SERIALIZABLE but code uses UoW default (likely READ COMMITTED). Higher isolation prevents anomalies but increases conflict rate. | yes | | open | | |
| 2 | What is the retention policy for st_observations? | Table grows by ~40 rows per P03 cycle. At 1000 cycles/day = 40K rows/day = 14.6M/year. No retention policy exists. | no | | open | | |
| 3 | Should ProceduralLayerWriter produce observations? | 5 of 6 truth layer writers have ObservationRecorder integration. Procedural is the exception. Is this intentional or an oversight? | no | | open | | |
| 4 | When should the legacy inline SQL path be removed? | USE_M5_ROUTER=True is current default. Legacy path adds ~400 lines of unmaintained code. What stability threshold triggers removal? | no | | open | | |
| 5 | Should embedding generation be moved to R6 staging? | Currently in R7 (within transaction). Moving to R6 would reduce transaction hold time but adds R6 complexity and a dependency on UltraBERT availability during staging. | no | | open | | |
| 6 | What is the correct write dependency order? | Contract says st_kg_dom first; code execution follows LAYER_PK_MAP order starting with st_vec. Which is correct for FK constraints? | yes | | open | | |
| 7 | Should MCTSLayerWriter be deleted before M5D? | Writer produces dead writes. Keeping it wastes I/O. Deleting early simplifies code but deviates from M5D plan. | no | | open | | |

---

## Appendix A: Glossary

| Term | Definition |
| ---- | ---------- |
| UoW | Unit of Work -- transaction pattern that groups all DB writes into a single atomic commit |
| GAP-001 | Gap analysis finding: truth tables need inline text summary + embedding columns, addressed by TextVectorCoordinator |
| GAP-007 | Gap analysis finding: KG edges need provenance tracking (source_algorithm, evidence arrays, inference_chain_json) |
| TVC | TextVectorCoordinator -- orchestrates text fetch, embedding generation, and vector result packaging |
| EMA | Exponential Moving Average -- used for social sentiment smoothing (old*0.9 + new*0.1) |
| HNSW | Hierarchical Navigable Small World -- approximate nearest neighbor index algorithm used by pgvector |
| P08 | Pipeline 08: Embedding Management -- handles vector storage, integrity, and search |
| MCTS | Monte Carlo Tree Search -- planning algorithm whose outputs are written by MCTSLayerWriter (DELETE candidate) |
| CPN | Causal Planning Network -- replaces MCTS in M5D for prospective reasoning |
| DLQ | Dead Letter Queue -- topic where unprocessable messages are sent for manual review |
| Outbox Pattern | Transactional outbox: events staged in st_outbox within the same transaction as truth writes, then published by R8 |
| Optimistic Locking | Concurrency control via version column: UPDATE WHERE version=$expected fails if another writer incremented version |
| FK | Foreign Key -- database constraint ensuring referential integrity between tables |
| ULID | Universally Unique Lexicographically Sortable Identifier -- used for all R7 record IDs |

## Appendix B: References

| # | Document | Path / URL | Relevance |
| - | -------- | ---------- | --------- |
| 1 | P03 Consolidation Dossier v2 | docs/pipelines/P03_consolidation_dossier_v2.md | Pipeline scope, stage definitions, and R7 position |
| 2 | ADR-K003 pgvector Migration | docs/architecture/decisions-K0/adr-k003-v2-pgvector-migration.md | Eliminated FAISS, all vectors via pgvector HNSW natively |
| 3 | M5 Master Implementation Skeleton (Epic 5.8) | docs/plans/MASTER_IMPLEMENTATION_SKELETON.md (lines 5542-5620) | R7 component inventory, write order, I/O contract, known issues |
| 4 | P03 Pipeline Contract v1 | k0/contracts/pipelines/p03_consolidation.v1.yaml (stage_70) | R7 stage definition, config, failure modes |
| 5 | Memory Writer Module Contract v1 | k0/contracts/modules/consolidation.memory_writer.v1.yaml | R7 module I/O, side effects, capabilities, failure modes |
| 6 | R6 Staging Discovery | docs/pipelines/p03_enhancement_discovery/P03_R6_STAGING_DISCOVERY.md | Upstream R6 produces P03StagedWrites consumed by R7 |
| 7 | R5 Dream Exploration Discovery | docs/pipelines/p03_enhancement_discovery/P03_R5_DREAM_EXPLORATION_DISCOVERY.md | R5 CPN results written by ProspectiveLayerWriter COUNTERFACTUAL action |
| 8 | Discovery Template | docs/pipelines/p03_enhancement_discovery/DISCOVERY_TEMPLATE.md | 15-section template governing this document format |
