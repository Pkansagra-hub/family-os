# P03 R0 Batch Selector — Phase Discovery & Enhancement Plan

> **Epic 5.1 Discovery**: Full audit of the R0 Batch Selection phase (event ingestion entry point
> for the P03 consolidation pipeline). Covers code, contracts, algorithms, data flow, storage,
> observability, tests, dependencies, performance, gaps, and enhancement proposals.

---

## 0. Discovery Metadata

| Field | Value |
| ----- | ----- |
| Pipeline ID | P03 |
| Module Scope | consolidation.batch_selector, consolidation.gap_auto_resolver, pipelines.p03.phases.r0_batch_selector |
| Discovery Date | 2026-03-02 |
| Milestone Target | M5 |
| Governing ADRs | ADR-K010 (P03 consolidation architecture), ADR-K010.1 (sleep-cycle state machine), ADR-K010.9 (capability-based security), ADR-K003-v2 (pgvector migration) |
| Related Dossier | `docs/pipelines/P03_consolidation_dossier_v2.md` |
| Author | copilot-claude |
| Status | DRAFT |

---

## 1. Current State Audit

### 1.1 Code Inventory

| # | File (relative path) | Lines | Status | Last Modified | Purpose |
| - | -------------------- | ----- | ------ | ------------- | ------- |
| 1 | k0/pipelines/p03/phases/r0_batch_selector.py | 760 | LEGACY | 2026-01-24 | Implements R0 phase: offset fetch, eligible event query, embedding materialization, gap auto-resolution, envelope construction |
| 2 | k0/modules/consolidation/batch_selector.py | 138 | LEGACY | 2026-01-05 | Adapts R0 phase to module registry interface for PipelineRunner (async def run wrapper) |
| 3 | k0/modules/consolidation/gap_auto_resolver.py | 473 | LEGACY | 2026-01-09 | Implements implicit gap resolution: matches NER entities from batch against pending AMBIGUOUS_ENTITY gaps in st_learning_queue |
| 4 | k0/pipelines/p03/event_state.py | 517 | LEGACY | 2026-01-24 | Defines P03EventState mutable dataclass: 60+ fields enriched through R0-R7 phases |
| 5 | k0/pipelines/p03/envelope.py | 205 | LEGACY | 2026-01-04 | Defines P03BatchEnvelope: root container (context + events + phase_outputs + staged_writes) |
| 6 | k0/pipelines/p03/context.py | 731 | LEGACY | 2026-01-01 | Defines P03CycleContext (frozen): batch metadata, ULID generation, trigger inputs |
| 7 | k0/pipelines/p03/checkpoint.py | 544 | LEGACY | 2025-12-31 | Defines P03Checkpoint, CheckpointStore protocol, P03_SUBSCRIBER_ID, P03_SOURCE_TOPIC constants |
| 8 | k0/pipelines/p03/phase_interface.py | 558 | LEGACY | 2026-01-04 | Defines P03PhaseResult, P03Phase protocol, P03RunnerContext |
| 9 | k0/pipelines/p03/observability.py | 1060 | LEGACY | 2026-01-04 | Defines P03ObservabilityContext, R1PhaseMetrics, P03Error, phase timing, metrics collection |
| 10 | k0/pipelines/p03/runner_contract.py | 561 | LEGACY | N/A | Defines P03PhaseId enum (R0-R8), P03PhaseStatus enum, phase ordering contracts |
| 11 | k0/contracts/modules/consolidation.batch_selector.v1.yaml | 45 | LEGACY | 2025-12-31 | Module contract: input/output events, latency budget, side effects, failure modes |
| 12 | k0/contracts/pipelines/p03_consolidation.v1.yaml | 397 | LEGACY | N/A | Pipeline contract: R0-R8 stages, triggers, capabilities, DAG, topics |
| 13 | tests/k0/pipelines/p03/test_p03_r0_batch_selector.py | 571 | LEGACY | N/A | Tests R0 offset handling, batch selection, envelope creation, error handling, config |

### 1.2 Contract Inventory

| # | Contract File | Version | Status | Lines | Governs |
| - | ------------- | ------- | ------ | ----- | ------- |
| 1 | k0/contracts/modules/consolidation.batch_selector.v1.yaml | v1 | active | 45 | module:consolidation.batch_selector |
| 2 | k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | active | 397 | pipeline:P03_CONSOLIDATION (all R0-R8 stages) |

### 1.3 Config Inventory

#### 1.3.1 YAML Config Keys

| Config File | Version | Key (dot-path) | Value | Type | Default | Required | Notes |
| ----------- | ------- | --------------- | ----- | ---- | ------- | -------- | ----- |
| k0/contracts/modules/consolidation.batch_selector.v1.yaml | v1 | latency_budget_ms | 50 | int | 50 | yes | R0 latency target per event; actual batch query may exceed this |
| k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | concurrency | 1 | int | 1 | yes | Single concurrent P03 pipeline execution |
| k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | max_queue_depth | 64 | int | 64 | yes | Max queued trigger messages |
| k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | triggers[0].interval_seconds | 5400 | int | 5400 | yes | 90-minute interval trigger |
| k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | triggers[1].threshold_count | 500 | int | 500 | yes | Threshold trigger: 500+ PENDING events |
| k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | triggers[1].check_interval_seconds | 60 | int | 60 | yes | How often to check threshold |

#### 1.3.2 Environment Variables

| Variable | Type | Default | Required | Used By | Purpose |
| -------- | ---- | ------- | -------- | ------- | ------- |
| K0_DB_URL | url | NONE | yes | k0/db/engine.py (shared) | PostgreSQL connection string used by R0 for st_hipp_events, st_offsets, st_vec, st_learning_queue queries |

> **Note**: R0 does not read any R0-specific environment variables. All configuration comes from the module config dict passed via PipelineRunner. Database connectivity is inherited from the shared K0 engine.

#### 1.3.3 Feature Flags

| Flag Name | Source | Default | Scope | Controls | Rollback Behavior |
| --------- | ------ | ------- | ----- | -------- | ----------------- |
| require_embedding_ready | config | true | global | Whether R0 filters to only events with embedding_status='READY' | Safe -- next batch includes non-embedded events |
| exclude_archived | config | true | global | Whether R0 excludes archived events (archival_status IS NULL) | Safe -- next batch includes archived events |

> **Note**: These are R0Config dataclass fields, not external feature flags. They are set via the pipeline YAML config dict.

#### 1.3.4 Constants & Magic Numbers

| Constant | Location (file:line) | Value | Type | Rationale | Externalize? |
| -------- | -------------------- | ----- | ---- | --------- | ------------ |
| batch_size (default) | k0/pipelines/p03/phases/r0_batch_selector.py:189 | 100 | int | Default batch size in R0Config; module wrapper overrides to config value (typically 1000 from pipeline YAML) | no -- already configurable via R0Config |
| max_age_hours (default) | k0/pipelines/p03/phases/r0_batch_selector.py:192 | 0 | int | 0 means no age limit; non-zero filters events older than N hours | no -- already configurable |
| AUTO_RESOLVE_THRESHOLD | k0/modules/consolidation/gap_auto_resolver.py:133 | 0.75 | float | Minimum confidence to auto-resolve a gap; chosen to avoid false matches on common names | yes -- should be tunable per entity type |
| MIN_SIMILARITY | k0/modules/consolidation/gap_auto_resolver.py:136 | 0.6 | float | Minimum Jaccard similarity to consider an entity-gap match | yes -- too low may produce false matches |
| _gap_cache_ttl_ms | k0/modules/consolidation/gap_auto_resolver.py:152 | 60000 | int | Gap query cache TTL (1 minute); avoids repeated st_learning_queue queries within same batch | maybe -- could be higher for large batches |
| LIMIT (pending gaps) | k0/modules/consolidation/gap_auto_resolver.py:186 | 100 | int | Max pending gaps loaded per query; hardcoded SQL LIMIT | yes -- should scale with gap volume |
| specificity_bonus | k0/modules/consolidation/gap_auto_resolver.py:305 | 0.15 | float | Bonus when new entity extends a gap candidate (more specific) | maybe -- affects resolution accuracy |
| label_match_bonus | k0/modules/consolidation/gap_auto_resolver.py:296 | 0.1 | float | Bonus when entity NER label matches gap entity type | maybe |
| text_match_confidence | k0/modules/consolidation/gap_auto_resolver.py:488 | 0.85 | float | Fixed confidence for raw text keyword matching (fallback path) | yes -- should not be higher than NER-based matching |
| max_phrase_words | k0/modules/consolidation/gap_auto_resolver.py:551 | 5 | int | Max words in extracted specific phrase from raw text | no -- reasonable limit for entity names |
| EMBEDDING_DIM | k0/pipelines/p03/event_state.py:271 | 768 | int | UltraBERT v2.1.0 output dimension; validated during materialize_embedding() | no -- tied to model; changing requires migration |
| QoS band threshold | k0/pipelines/p03/phases/r0_batch_selector.py:836 | 50 | int | batch_size <= 50 = GREEN QoS, else AMBER | yes -- arbitrary threshold, no documented rationale |
| P03_SUBSCRIBER_ID | k0/pipelines/p03/checkpoint.py:35 | "P03_CONSOLIDATE" | str | Offset store subscriber for P03 | no -- identity constant |
| P03_SOURCE_TOPIC | k0/pipelines/p03/checkpoint.py:41 | "st_hipp_events" | str | Source topic for offset tracking | no -- identity constant |

### 1.4 Migration Inventory

| # | Migration File | Table(s) | Operation | Columns Affected | Reversible? |
| - | -------------- | -------- | --------- | ---------------- | ----------- |
| 1 | k0/db/alembic/versions/0005_st_offsets.py | st_offsets | CREATE | +subscriber_id, +topic, +offset, +space_id, +tenant_id, +updated_at | yes |
| 2 | k0/db/alembic/versions/0022_st_hipp_events.py | st_hipp_events | CREATE | +event_id, +text, +tenant_id, +space_id, +wal_pos, +created_at, (base columns) | no (DROP destroys data) |
| 3 | k0/db/alembic/versions/0034_st_hipp_events_p03_columns.py | st_hipp_events | ALTER | +consolidation_status, +embedding_status, +archival_status | partial |
| 4 | k0/db/alembic/versions/0037_st_learning_queue.py | st_learning_queue | CREATE | +id, +gap_type, +entity_id, +status, +importance_score, +context_json, +confidence_score, +expires_at | yes |
| 5 | k0/db/alembic/versions/0046_st_hipp_events_p02_ner_columns.py | st_hipp_events | ALTER | +ner_entities_json, +temporal_json, +intent_category | partial |
| 6 | k0/db/alembic/versions/0051_st_hipp_events_archival_status.py | st_hipp_events | ALTER | ~archival_status | partial |
| 7 | k0/db/alembic/versions/0052_st_hipp_events_p03_columns.py | st_hipp_events | ALTER | +affect_valence, +affect_arousal, +salience_score, +salience_band, +novelty_score | partial |
| 8 | k0/db/alembic/versions/0053_st_hipp_events_ultrabert_full.py | st_hipp_events | ALTER | +participants_json, +num_participants, +social_context, +social_intimacy, +is_solo_event, +location_name, +location_type, +geohash_6, +extracted_relations_json | partial |
| 9 | k0/db/alembic/versions/0060_st_hipp_events_activity_ultrabert.py | st_hipp_events | ALTER | +activity_type_ultrabert, +activity_type_confidence, +intent_ultrabert, +intent_confidence, +time_of_day_bucket, +circadian_slot, +is_weekend, +day_of_week, +ingress_channel, +ingress_source, +device_kind | partial |

---

## 2. API Surface Map

### 2.1 Public Functions & Methods

| # | Module | Function / Method | Signature | Return Type | Consumers | Idempotent? | Notes |
| - | ------ | ----------------- | --------- | ----------- | --------- | ----------- | ----- |
| 1 | k0.modules.consolidation.batch_selector | run | (message: Any, context: Any, **config: Any) | dict[str, Any] | PipelineRunner (stage_00_select_batch) | conditional | Idempotent if no events processed between retries (offset unchanged) |
| 2 | k0.pipelines.p03.phases.r0_batch_selector | R0BatchSelector.run | (tenant_id: str, space_id: str, ctx: P03RunnerContext) | Tuple[Optional[P03BatchEnvelope], P03PhaseResult] | consolidation.batch_selector.run() | conditional | Same-offset = same batch selected |
| 3 | k0.pipelines.p03.phases.r0_batch_selector | R0BatchSelector.should_skip | (tenant_id: str, space_id: str, ctx: P03RunnerContext) | Tuple[bool, str] | SequentialRunner protocol check | yes | Always returns (False, "") -- R0 never skips |
| 4 | k0.pipelines.p03.phases.r0_batch_selector | R0BatchSelector.idempotency_key | (tenant_id: str, space_id: str) | str | SequentialRunner dedup | yes | Returns f"p03:r0:{tenant_id}:{space_id}" |
| 5 | k0.modules.consolidation.gap_auto_resolver | GapAutoResolver.process_entities | (entities: list[dict], source_event_id: Optional[str], event_texts: Optional[list[str]]) | int | R0 _try_auto_resolve_gaps | no | Writes RESOLVED status to st_learning_queue |
| 6 | k0.modules.consolidation.gap_auto_resolver | GapAutoResolver.load_pending_gaps | (force_refresh: bool) | list[PendingGap] | GapAutoResolver.process_entities | yes | Reads from st_learning_queue, caches for 60s |
| 7 | k0.modules.consolidation.gap_auto_resolver | GapAutoResolver.match_entity_to_gaps | (entity_text: str, entity_label: str, source_event_id: Optional[str]) | list[ResolutionCandidate] | GapAutoResolver.process_entities | yes | Pure matching logic, no side effects |
| 8 | k0.modules.consolidation.gap_auto_resolver | GapAutoResolver.resolve_gaps | (resolutions: list[ResolutionCandidate]) | int | GapAutoResolver.process_entities | conditional | Idempotent: UPDATE WHERE status='PENDING' (resolved gaps won't match again) |
| 9 | k0.modules.consolidation.gap_auto_resolver | try_auto_resolve_gaps | (pool: Pool, tenant_id: str, entities: list[dict], source_event_id: Optional[str], space_id: Optional[str]) | Tuple[int, GapAutoResolverStats] | Convenience function (unused in R0 -- R0 uses class directly) | no | Writes to st_learning_queue |

### 2.2 Syscalls Used / Required

| # | Syscall | Signature | Status | Used By | SQL Pattern (if DB) | Notes |
| - | ------- | --------- | ------ | ------- | ------------------- | ----- |
| 1 | offset_store.fetch | (subscriber_id: str, topic: str, space_id: str, tenant_id: str) -> Optional[OffsetRecord] | exists | R0BatchSelector._fetch_offset | SELECT offset FROM st_offsets WHERE subscriber_id=$1 AND topic=$2 AND space_id=$3 AND tenant_id=$4 | Returns 0 if no record |
| 2 | unit_of_work (connection) | ctx.syscalls.unit_of_work() -> AsyncContextManager[UoW] | exists | R0BatchSelector._fetch_eligible_events,_load_embeddings_for_events | Provides raw asyncpg Connection | R0 uses raw SQL via uow._connection, not typed syscalls |
| 3 | get_pool | ctx.syscalls.get_pool() -> asyncpg.Pool | exists | _try_auto_resolve_gaps | N/A (provides connection pool) | Capability-gated; PermissionError if not granted |

> **Note**: R0 performs raw SQL queries directly via `uow._connection` rather than using typed syscall methods. This bypasses the syscall abstraction for `st_hipp_events` reads and `st_vec` reads. The direct SQL is in `_fetch_eligible_events` (lines 455-582) and `_load_embeddings_for_events` (lines 700-800).

### 2.3 Internal Helpers (non-public but critical path)

| # | Module | Function | Signature | Called By | Purpose | Risk if Changed |
| - | ------ | -------- | --------- | --------- | ------- | --------------- |
| 1 | k0.pipelines.p03.phases.r0_batch_selector | _extract_entities_from_events | (events: list[P03EventState]) -> tuple[list[dict], list[str]] | _try_auto_resolve_gaps | Extracts NER entities from UltraBERT format (ner_family/ner_general) for gap matching | Breaks gap auto-resolution silently if entity format changes |
| 2 | k0.pipelines.p03.phases.r0_batch_selector | _try_auto_resolve_gaps | (ctx: P03RunnerContext, events: list[P03EventState], tenant_id: str, space_id: str) -> int | R0BatchSelector.run | Orchestrates gap auto-resolution: extracts entities, creates GapAutoResolver, calls process_entities | Non-fatal -- failure is caught and returns 0 |
| 3 | k0.pipelines.p03.phases.r0_batch_selector | R0BatchSelector._row_to_event_state | (row: asyncpg.Record) -> P03EventState | _fetch_eligible_events | Converts database row to P03EventState; maps column names (text->content_text, activity_category->content_type, dominant_emotions_json->emotions_json) | Breaks ALL downstream phases if field mapping is wrong -- every R1-R8 phase reads P03EventState fields |
| 4 | k0.pipelines.p03.phases.r0_batch_selector | R0BatchSelector._fetch_eligible_events | (ctx, tenant_id, space_id, offset) -> list[P03EventState] | R0BatchSelector.run | Builds and executes eligible events SQL query with dynamic WHERE clause | Breaks entire pipeline -- no events = no processing |
| 5 | k0.pipelines.p03.phases.r0_batch_selector | R0BatchSelector._load_embeddings_for_events | (ctx, events) -> int | R0BatchSelector.run | Queries st_vec by event_id, decodes binary float32 vectors, calls materialize_embedding | Non-fatal -- R2 skips events without embeddings |
| 6 | k0.pipelines.p03.phases.r0_batch_selector | R0BatchSelector._build_envelope | (tenant_id, space_id, events, start_offset) -> P03BatchEnvelope | R0BatchSelector.run | Creates P03CycleContext and P03BatchEnvelope from selected events | Changes affect every downstream phase |
| 7 | k0.modules.consolidation.gap_auto_resolver | _normalize_entity | (text: str) -> str | match_entity_to_gaps,_match_text_to_gaps | Lowercase, strip, collapse whitespace, remove stopwords | Affects matching accuracy for all gap resolution |
| 8 | k0.modules.consolidation.gap_auto_resolver | _similarity | (s1: str, s2: str) -> float | match_entity_to_gaps | Jaccard similarity on word sets | Simple metric -- may miss paraphrases or partial overlaps |
| 9 | k0.modules.consolidation.gap_auto_resolver | GapAutoResolver._match_text_to_gaps | (event_texts: list[str], source_event_id: Optional[str]) -> list[ResolutionCandidate] | process_entities | Fallback: searches raw event text for gap keywords when NER misses | Secondary path -- NER matching is primary |
| 10 | k0.modules.consolidation.gap_auto_resolver | GapAutoResolver._extract_specific_phrase | (text: str, keywords: set) -> Optional[str] | _match_text_to_gaps | Extracts proper noun phrase containing all gap keywords from raw text | Heuristic -- may extract wrong phrase in complex sentences |

### 2.4 Classes & Dataclasses

| # | Module | Class | Base Class / Protocol | Key Attributes | Key Methods | Consumers |
| - | ------ | ----- | --------------------- | -------------- | ----------- | --------- |
| 1 | k0.pipelines.p03.phases.r0_batch_selector | R0BatchSelector | (none) | PHASE_ID: P03PhaseId, config: R0Config | run(), should_skip(), idempotency_key() | consolidation.batch_selector module wrapper |
| 2 | k0.pipelines.p03.phases.r0_batch_selector | R0Config | dataclass | batch_size: int, require_embedding_ready: bool, exclude_archived: bool, max_age_hours: int | N/A (data only) | R0BatchSelector.**init** |
| 3 | k0.modules.consolidation.gap_auto_resolver | GapAutoResolver | (none) | _pool: Pool,_tenant_id: str,_space_id: Optional[str],_threshold: float, _stats: GapAutoResolverStats,_pending_gaps: list[PendingGap] | process_entities(), load_pending_gaps(), match_entity_to_gaps(), resolve_gaps() | R0 _try_auto_resolve_gaps |
| 4 | k0.modules.consolidation.gap_auto_resolver | PendingGap | dataclass | id: str, gap_type: str, entity_id: str, candidate_values: list[str], confidence_score: float, context_json: Optional[str], space_id: Optional[str], tenant_id: Optional[str] | N/A (data only) | GapAutoResolver |
| 5 | k0.modules.consolidation.gap_auto_resolver | ResolutionCandidate | dataclass | gap_id: str, entity_id: str, resolved_value: str, confidence: float, source_event_id: Optional[str], match_reason: str | N/A (data only) | GapAutoResolver.resolve_gaps |
| 6 | k0.modules.consolidation.gap_auto_resolver | GapAutoResolverStats | dataclass | gaps_checked: int, entities_matched: int, gaps_resolved: int, gaps_skipped_low_confidence: int | to_dict() | GapAutoResolver, logging |
| 7 | k0.pipelines.p03.event_state | P03EventState | dataclass | 60+ fields (see Section 4.2) | materialize_embedding(), clear_embedding(), set_importance() | All R0-R8 phases |
| 8 | k0.pipelines.p03.event_state | ReconciliationAction | Enum | PENDING, REINFORCE, EXTEND, CREATE, EVOLVE, CONTRADICT, PRUNE, SKIP | N/A | R3, R6, R7 |
| 9 | k0.pipelines.p03.event_state | PruneDecision | Enum | KEEP, ARCHIVE, TOMBSTONE | N/A | R3 |
| 10 | k0.pipelines.p03.envelope | P03BatchEnvelope | dataclass | context: P03CycleContext, events: list[P03EventState], phase_outputs: P03PhaseOutputs, staged_writes: P03StagedWrites | create() factory | All R0-R8 phases |
| 11 | k0.pipelines.p03.context | P03CycleContext | frozen dataclass | cycle_id: str, batch_id: str, tenant_id: str, space_id: str, event_ids: list[str], trigger_type: str, trigger_reason: str, pending_before: int, qos_band: str | create() factory | Envelope, checkpoint, all phases |
| 12 | k0.pipelines.p03.phase_interface | P03PhaseResult | dataclass | phase_id: P03PhaseId, status: P03PhaseStatus, duration_ms: int, outputs_summary: dict, error_info: Optional[P03Error], skip_reason: Optional[str] | done(), skip(), fail() factory methods | SequentialRunner |
| 13 | k0.pipelines.p03.phase_interface | P03RunnerContext | dataclass | syscalls: Any, logger: Any, config: dict | N/A (data only) | All phases |

---

## 3. Algorithm Inventory

### 3.1 Current Algorithms

| # | Algorithm Name | Location | Category | Input Type(s) | Input Constraints | Output Type(s) | Output Guarantees | Time | Space | Det? | Stateful? | State Location | Parameters | Edge Cases | Failure Mode | Fallback | Dependencies | Description |
| - | -------------- | -------- | -------- | ------------- | ----------------- | -------------- | ----------------- | ---- | ----- | ---- | --------- | -------------- | ---------- | ----------- | ------------ | -------- | ------------ | ----------- |
| 1 | offset_fetch | k0/pipelines/p03/phases/r0_batch_selector.py:437 | routing | tenant_id: str, space_id: str | non-empty strings | int (offset position) | offset >= 0; 0 if no prior | O(1) | O(1) | yes | no | N/A | subscriber_id=P03_CONSOLIDATE, topic=st_hipp_events | no prior offset returns 0 | raises RuntimeError on DB failure | returns 0 (fresh start) | offset_store syscall | Fetches current P03 offset position from st_offsets for batch cursor |
| 2 | eligible_event_query | k0/pipelines/p03/phases/r0_batch_selector.py:455 | filtering | tenant_id: str, space_id: str, offset: int | offset >= 0, batch_size > 0 | list[P03EventState] | events ordered by wal_pos ASC, len <= batch_size, all have consolidation_status NULL or PENDING | O(n) where n = batch_size | O(n) per event state | yes | no | N/A | batch_size, require_embedding_ready, exclude_archived, max_age_hours | 0 events returns empty list, no table returns RuntimeError | raises RuntimeError on DB failure | returns empty list (skip) | asyncpg, st_hipp_events table | Queries st_hipp_events for events after offset with status/embedding/archive filters |
| 3 | row_to_event_state_mapping | k0/pipelines/p03/phases/r0_batch_selector.py:631 | transformation | asyncpg.Record | row must have event_id key | P03EventState | all R0 fields populated, timestamp in milliseconds | O(1) | O(1) | yes | no | N/A | N/A | missing columns default to empty/0; event_time < 1e12 treated as seconds and multiplied by 1000 | no explicit error handling (KeyError for event_id) | missing fields get defaults ("", 0, 0.0) | N/A | Converts database row to P03EventState with column name aliasing |
| 4 | embedding_materialization | k0/pipelines/p03/phases/r0_batch_selector.py:700 | transformation | list[P03EventState] with embedding_ids | events must have embedding_id set | int (count loaded) | loaded_count <= len(events), vectors are 768-dim float32 | O(n) where n = events with embedding_id | O(n *768* 4) bytes for vectors | yes | no | N/A | N/A | 0 events with embedding_id returns 0, empty vector bytes skipped, wrong size skipped, decode failure skipped | logs warning on failure, returns partial count | partial loading -- events without embeddings excluded later | asyncpg, st_vec table, struct.unpack | Loads 768-dim vectors from st_vec by event_id, unpacks binary float32, calls materialize_embedding |
| 5 | NER_entity_extraction | k0/pipelines/p03/phases/r0_batch_selector.py:52 | transformation | list[P03EventState] | events may have ner_entities_json | tuple[list[dict], list[str]] | entities have text, label, source_event_id; event_texts are non-empty content strings | O(n * e) where n = events, e = avg entities per event | O(n * e) | yes | no | N/A | N/A | empty ner_entities_json="[]" skipped, malformed JSON caught silently, dict and list NER formats handled | swallows JSONDecodeError/TypeError | returns ([], []) | json.loads | Extracts NER entities from UltraBERT format (ner_family + ner_general sections) and raw text for gap matching |
| 6 | gap_auto_resolution | k0/modules/consolidation/gap_auto_resolver.py:130 | classification | list[dict] entities, list[str] event_texts | entities need text and label keys | int (gaps resolved) | resolved_count >= 0 | O(e * g) where e = entities, g = pending gaps | O(g) for gap cache | no (writes to DB) | yes | _pending_gaps cache (1 min TTL) | auto_resolve_threshold=0.75, MIN_SIMILARITY=0.6 | 0 pending gaps returns 0, 0 entities returns 0, low confidence skipped | logs warning on DB failure | returns 0 on any failure | asyncpg, st_learning_queue | Two-pass matching: NER entities then raw text against AMBIGUOUS_ENTITY gaps; resolves high-confidence matches |
| 7 | jaccard_similarity | k0/modules/consolidation/gap_auto_resolver.py:62 | scoring | s1: str, s2: str | non-empty strings | float [0.0, 1.0] | 0.0 if empty, 1.0 if identical word sets | O(w1 + w2) where w = word count | O(w1 + w2) | yes | no | N/A | N/A | empty strings return 0.0 | N/A | returns 0.0 | N/A | Computes Jaccard similarity on word sets for entity-gap matching |
| 8 | entity_normalization | k0/modules/consolidation/gap_auto_resolver.py:51 | transformation | text: str | any string | str (normalized) | lowercase, stripped, collapsed whitespace, stopwords removed | O(w) where w = word count | O(w) | yes | no | N/A | stopwords = {the, a, an, at, in, on, of} | empty string returns "" | N/A | N/A | N/A | Normalizes entity text for matching by lowercasing, stripping, removing common stopwords |
| 9 | envelope_construction | k0/pipelines/p03/phases/r0_batch_selector.py:808 | aggregation | tenant_id, space_id, events, start_offset | events non-empty | P03BatchEnvelope | context has unique cycle_id (ULID), batch_id, event_ids list | O(n) where n = events | O(n) for event_ids | no (ULID has randomness) | no | N/A | qos_band threshold=50 | N/A | N/A | N/A | P03CycleContext.create, P03BatchEnvelope.create | Constructs immutable P03CycleContext and P03BatchEnvelope from selected events |

### 3.2 Algorithm Gaps

| # | Gap Description | Expected Behavior | Current Behavior | Severity | Proposed Approach | Estimated Complexity |
| - | --------------- | ----------------- | ---------------- | -------- | ----------------- | -------------------- |
| 1 | No adaptive batch sizing | Batch size should scale based on system load, pending event count, and recent P03 cycle duration | Fixed batch_size from config (100 default, 1000 from YAML) regardless of conditions | P2 | Add adaptive batch sizing that considers pending count, last cycle duration, and memory pressure | small |
| 2 | Embedding loading has no pagination | Load embeddings in batches to avoid large IN clause | Single SELECT ... WHERE event_id IN (all_ids) for up to 1000 events | P2 | Chunk event_ids into batches of 100-200 for st_vec query | small |
| 3 | Gap matching uses Jaccard only | Should use semantic similarity (embeddings) for entity matching | Simple word-set Jaccard -- misses synonyms, paraphrases, abbreviations | P3 | Add embedding-based similarity for entity matching (requires vec_search syscall) | medium |
| 4 | No narrative_thread_id loading | R0 should load narrative_thread_id from st_hipp_events for R2 thread-aware clustering | Column not selected in R0 SQL query | P1 | Add narrative_thread_id to SELECT and P03EventState; requires new P03EventState field | small |
| 5 | No temporal_anchor loading | R0 should load temporal_anchor for R2 episode boundary detection | Column not selected in R0 SQL query | P2 | Add temporal_anchor to SELECT and P03EventState | small |
| 6 | No surprise_level loading | R0 should load surprise_level for R1 importance scoring | Column not selected in R0 SQL query | P1 | Add surprise_level to SELECT and P03EventState | small |
| 7 | No identity_relevance loading | R0 should load identity_relevance for R3 immunity decisions | Column not selected in R0 SQL query | P1 | Add identity_relevance to SELECT and P03EventState | small |
| 8 | No memory_tier loading | R0 should load memory_tier for R3 tier-aware decay | Column not selected in R0 SQL query | P1 | Add memory_tier to SELECT and P03EventState | small |
| 9 | No source_reliability loading | R0 should load source_reliability for R1 trust modulation | Column not selected in R0 SQL query | P2 | Add source_reliability to SELECT and P03EventState | small |
| 10 | No elaboration_depth loading | R0 should load elaboration_depth for R1 detail-weighting | Column not selected in R0 SQL query | P2 | Add elaboration_depth to SELECT and P03EventState | small |
| 11 | No cognitive_trace_id propagation | R0 SELECTs cognitive_trace_id but does not map it to P03EventState | cognitive_trace_id is selected in SQL but not assigned to any P03EventState field | P1 | Add cognitive_trace_id field to P03EventState and map in _row_to_event_state | small |
| 12 | Duplicate return statements in idempotency_key | Method has 6 identical return statements | Bug: copy-paste error -- only first return executes, rest are dead code | P3 | Remove 5 duplicate return statements | trivial |

---

## 4. Data Flow & I/O Map

### 4.1 Pipeline Stage Map

| Stage Order | Stage ID | Module | Input Event / Topic | Output Event / Topic | Side Effects | Error Topic | Retry Policy |
| ----------- | -------- | ------ | ------------------- | -------------------- | ------------ | ----------- | ------------ |
| 1 | stage_00_select_batch (R0) | k0.modules.consolidation.batch_selector | p03.consolidation.triggered.v1 (scheduler interval/threshold/manual) | N/A (envelope created, not emitted) | Reads st_offsets, reads st_hipp_events, reads st_vec, reads/writes st_learning_queue (gap resolution) | P03Error (R0_INGESTION_ERROR, recoverable=True) | Retriable (offset is idempotent) |

> **Note**: R0 is the first stage -- it creates the P03BatchEnvelope that is passed in-memory to R1. No bus event is emitted between R0 and R1.

### 4.2 Input Schemas (per stage / module)

**Stage: R0 (batch_selector)**

| # | Field | Type | Required | Nullable | Validation Rule | Source | Example Value |
| - | ----- | ---- | -------- | -------- | --------------- | ------ | ------------- |
| 1 | tenant_id | str | yes | no | non-empty, defaults to "default" if not in message | BusMessage.tenant_id or payload.tenant_id | "tenant_001" |
| 2 | space_id | str | yes | no | non-empty, defaults to "default" | BusMessage.space_id | "family_main" |
| 3 | max_batch_size | int | no | no | > 0, defaults to 100 | config dict from pipeline YAML | 1000 |
| 4 | require_embedding_ready | bool | no | no | defaults to True | config dict | true |
| 5 | exclude_archived | bool | no | no | defaults to True | config dict | true |
| 6 | context_window_hours | int | no | no | >= 0, 0 = no limit, defaults to 0 | config dict | 24 |

**Trigger Payload (p03.consolidation.triggered.v1)**

| # | Field | Type | Required | Nullable | Validation Rule | Source | Example Value |
| - | ----- | ---- | -------- | -------- | --------------- | ------ | ------------- |
| 1 | tenant_id | str | yes | no | non-empty | scheduler or manual trigger | "tenant_001" |
| 2 | space_id | str | no | yes | defaults to "default" | scheduler | "family_main" |
| 3 | trigger_type | str | no | yes | one of: INTERVAL, THRESHOLD, MANUAL | scheduler | "INTERVAL" |

### 4.3 Output Schemas (per stage / module)

**Stage: R0 (module wrapper output)**

| # | Field | Type | Nullable | Produced By | Consumed By | Example Value |
| - | ----- | ---- | -------- | ----------- | ----------- | ------------- |
| 1 | batch_id | str | yes (None if empty) | P03CycleContext.batch_id | PipelineRunner logging | "01HQXYZ..." |
| 2 | event_count | int | no | len(envelope.events) | PipelineRunner metrics | 42 |
| 3 | events | list[dict] | no | serialized P03EventState subset | PipelineRunner logging (not used by R1) | [{event_id, content_text, ...}] |
| 4 | time_range | dict | yes (None if empty) | computed from event timestamps | PipelineRunner logging | {"start": 1735600000000, "end": 1735610000000} |
| 5 | status | str | no | "selected" or "empty" | PipelineRunner flow control | "selected" |
| 6 | skip_reason | str | yes | P03PhaseResult.skip_reason | logging | "No pending events" |
| 7 | duration_ms | int | no | phase timing | metrics | 120 |

**Stage: R0 (internal output -- P03BatchEnvelope)**

| # | Field | Type | Nullable | Produced By | Consumed By | Example Value |
| - | ----- | ---- | -------- | ----------- | ----------- | ------------- |
| 1 | envelope.context | P03CycleContext | no | R0._build_envelope | R1-R8 (immutable batch context) | frozen dataclass |
| 2 | envelope.events | list[P03EventState] | no | R0._fetch_eligible_events +_load_embeddings | R1 (importance), R2 (clustering), R3 (dedup/decay), R4 (KG), R5 (dream) | list of 42 events |
| 3 | envelope.phase_outputs | P03PhaseOutputs | no | created empty, populated by R1-R5 | R6 staging assembler | starts empty |
| 4 | envelope.staged_writes | P03StagedWrites | no | created empty, populated by R6 | R7 truth writer | starts empty |

### 4.4 Error Outputs

| # | Error Code / Type | Condition | HTTP Status | Handling | Downstream Impact | Recoverable? |
| - | ----------------- | --------- | ----------- | -------- | ----------------- | ------------ |
| 1 | ValueError | Malformed trigger payload (bad JSON, missing fields) | N/A | abort | Pipeline does not start | no -- bad payload needs fixing |
| 2 | RuntimeError | Syscalls not available (no context.syscalls) | N/A | abort | Pipeline does not start | no -- config/deployment issue |
| 3 | RuntimeError | UnitOfWork connection not initialized | N/A | abort | No events can be loaded | maybe -- transient connection issue |
| 4 | R0_INGESTION_ERROR | Any unhandled exception in R0BatchSelector.run | N/A | retry | Pipeline fails at R0, offset unchanged | yes -- marked recoverable=True |
| 5 | PermissionError | get_pool() denied by capability system | N/A | skip (gap resolution only) | Gap auto-resolution skipped; batch selection continues | yes -- non-fatal for core R0 flow |

### 4.5 Data Transformation Map

| # | Source Field(s) | Transformation | Target Field | Lossy? | Reversible? | Notes |
| - | --------------- | -------------- | ------------ | ------ | ----------- | ----- |
| 1 | st_hipp_events.text | direct copy | P03EventState.content_text | no | yes | Column aliased as text in DB |
| 2 | st_hipp_events.activity_category | alias to content_type | P03EventState.content_type | no | yes | DB column name differs from field name |
| 3 | st_hipp_events.dominant_emotions_json | alias to emotions_json | P03EventState.emotions_json | no | yes | DB column name differs |
| 4 | st_hipp_events.event_time_utc | seconds-to-milliseconds conversion (if < 1e12) | P03EventState.timestamp | no | yes | Multiplied by 1000 if value < 1e12 (assumed seconds) |
| 5 | st_hipp_events.temporal_json | alias to temporal_expressions_json | P03EventState.temporal_expressions_json | no | yes | Column name mapping |
| 6 | st_hipp_events.intent_ultrabert OR intent_category | fallback chain | P03EventState.intent_label | yes (loses source info) | no | UltraBERT preferred, legacy fallback |
| 7 | st_vec.vector (binary) | struct.unpack(f"{dim}f", bytes) | P03EventState.embedding_768 | no | yes | Binary float32 to list[float]; 768 * 4 = 3072 bytes |
| 8 | st_hipp_events.ner_entities_json | JSON parse + restructure | list[dict] with text/label/source_event_id | yes (adds source_event_id, drops extra fields) | no | UltraBERT ner_family + ner_general extracted |

---

## 5. Storage & Persistence

### 5.1 Tables Touched

| # | Table | Operation | Key Columns Used | Access Pattern | Index Used | Estimated Row Count |
| - | ----- | --------- | ---------------- | -------------- | ---------- | ------------------- |
| 1 | st_offsets | R | subscriber_id, topic, space_id, tenant_id | point (composite key lookup) | PK (subscriber_id, topic, space_id, tenant_id) | ~100 (one per pipeline per space) |
| 2 | st_hipp_events | R | tenant_id, space_id, wal_pos, consolidation_status, embedding_status, archival_status | range (wal_pos > offset, filtered, LIMIT batch_size) | ix_st_hipp_events_tenant_space_walpos (assumed) | ~10K-500K |
| 3 | st_vec | R | event_id, status | point (by event_id IN list) | PK (event_id) or ix_st_vec_event | ~10K-500K |
| 4 | st_learning_queue | RW | tenant_id, status, gap_type, expires_at | range (status=PENDING, gap_type=AMBIGUOUS_ENTITY) | ix_st_learning_queue_tenant_status (assumed) | ~100-1K |

### 5.2 Column-Level Detail

**st_hipp_events columns read by R0:**

| Table | Column | Type | Nullable | Default | Read By | Written By | Indexed? | Notes |
| ----- | ------ | ---- | -------- | ------- | ------- | ---------- | -------- | ----- |
| st_hipp_events | event_id | TEXT | no | NONE | R0 | P02 | yes (PK) | Primary key |
| st_hipp_events | wal_pos | BIGINT | no | NONE | R0 (offset cursor) | P02 | yes | Write-ahead log position for ordering |
| st_hipp_events | tenant_id | VARCHAR(64) | no | NONE | R0 | P02 | yes (composite) | Multi-tenant isolation |
| st_hipp_events | space_id | VARCHAR(64) | no | NONE | R0 | P02 | yes (composite) | Family/user space |
| st_hipp_events | consolidation_status | VARCHAR(16) | yes | NULL | R0 (filter) | R6/R7 | yes | NULL or PENDING = eligible for P03 |
| st_hipp_events | embedding_status | VARCHAR(16) | yes | NULL | R0 (filter) | P08 | yes | READY = embedding available in st_vec |
| st_hipp_events | archival_status | VARCHAR(16) | yes | NULL | R0 (filter) | retention | no | NULL = not archived |
| st_hipp_events | text | TEXT | yes | NULL | R0 -> content_text | P02 | no | Raw user content |
| st_hipp_events | simhash_hex | VARCHAR(16) | yes | NULL | R0 | P02 | no | 64-bit SimHash for fuzzy dedup |
| st_hipp_events | cognitive_trace_id | TEXT | yes | NULL | R0 (selected but NOT mapped) | P02 | no | Conversation trace ID -- GAP: not propagated to P03EventState |
| st_hipp_events | sentiment_score | FLOAT | yes | 0.0 | R0 -> R1 | P02 | no | [-1, 1] sentiment |
| st_hipp_events | affect_valence | FLOAT | yes | 0.0 | R0 -> R1 | P02 | no | [-1, 1] emotional valence |
| st_hipp_events | affect_arousal | FLOAT | yes | 0.0 | R0 -> R1 | P02 | no | [0, 1] emotional arousal |
| st_hipp_events | salience_score | FLOAT | yes | 0.0 | R0 -> R1 | P02 | no | [0, 1] computed salience |
| st_hipp_events | novelty_score | FLOAT | yes | 0.0 | R0 -> R1 | P02 | no | [0, 1] information novelty |
| st_hipp_events | ner_entities_json | TEXT | yes | "[]" | R0 -> R4 | P02 | no | UltraBERT NER entities JSON |
| st_hipp_events | activity_type_ultrabert | VARCHAR(32) | yes | NULL | R0 -> R1 | P02 | no | 12-type INGRESS classification |
| st_hipp_events | intent_ultrabert | VARCHAR(32) | yes | NULL | R0 -> R1 | P02 | no | 8-type INTENT classification |

**st_vec columns read by R0:**

| Table | Column | Type | Nullable | Default | Read By | Written By | Indexed? | Notes |
| ----- | ------ | ---- | -------- | ------- | ------- | ---------- | -------- | ----- |
| st_vec | event_id | TEXT | no | NONE | R0 (join key) | P08 backfill | yes | Links to st_hipp_events.event_id |
| st_vec | vector | BYTEA | no | NONE | R0 (embedding) | P08 | no | Binary float32[768] = 3072 bytes |
| st_vec | vector_dim | INTEGER | no | 768 | R0 (validation) | P08 | no | Expected 768 for UltraBERT |
| st_vec | status | VARCHAR(16) | no | 'READY' | R0 (filter) | P08 | yes | IN ('READY', 'INDEXED') |

**st_learning_queue columns used by gap auto-resolver:**

| Table | Column | Type | Nullable | Default | Read By | Written By | Indexed? | Notes |
| ----- | ------ | ---- | -------- | ------- | ------- | ---------- | -------- | ----- |
| st_learning_queue | id | TEXT | no | NONE | gap_auto_resolver | P06/R4 | yes (PK) | Gap record ID |
| st_learning_queue | status | VARCHAR(16) | no | 'PENDING' | gap_auto_resolver (filter) | gap_auto_resolver (-> RESOLVED) | yes | Lifecycle: PENDING -> RESOLVED/EXPIRED |
| st_learning_queue | gap_type | VARCHAR(32) | no | NONE | gap_auto_resolver (filter) | P06/R4 | yes | AMBIGUOUS_ENTITY type |
| st_learning_queue | entity_id | TEXT | yes | NULL | gap_auto_resolver (matching) | P06/R4 | no | Entity cluster ID |
| st_learning_queue | context_json | TEXT | yes | NULL | gap_auto_resolver (candidates) | P06/R4 | no | JSON with candidate_values array |
| st_learning_queue | confidence_score | FLOAT | yes | 0.5 | gap_auto_resolver | P06/R4 | no | Gap confidence |
| st_learning_queue | importance_score | FLOAT | yes | NULL | gap_auto_resolver (ORDER BY) | P06/R4 | no | Priority for loading |
| st_learning_queue | expires_at | BIGINT | yes | NULL | gap_auto_resolver (filter) | P06/R4 | no | Expiration timestamp (ms) |
| st_learning_queue | resolution_type | VARCHAR(16) | yes | NULL | N/A | gap_auto_resolver (-> IMPLICIT) | no | How gap was resolved |
| st_learning_queue | resolution_data_json | TEXT | yes | NULL | N/A | gap_auto_resolver (JSON) | no | Resolution details |
| st_learning_queue | answered_at | BIGINT | yes | NULL | N/A | gap_auto_resolver (timestamp) | no | When resolved (ms) |

### 5.3 Query Patterns

| # | Query Purpose | SQL Pattern | Frequency | Expected Latency | Index Coverage | Notes |
| - | ------------- | ----------- | --------- | ---------------- | -------------- | ----- |
| 1 | Fetch P03 offset | SELECT offset FROM st_offsets WHERE subscriber_id='P03_CONSOLIDATE' AND topic='st_hipp_events' AND space_id=$1 AND tenant_id=$2 | per-cycle | < 5ms | full (PK) | Single row point lookup |
| 2 | Fetch eligible events | SELECT 30+ columns FROM st_hipp_events WHERE tenant_id=$1 AND space_id=$2 AND wal_pos > $3 AND (consolidation_status IS NULL OR = 'PENDING') AND embedding_status='READY' AND (archival_status IS NULL) ORDER BY wal_pos ASC LIMIT $4 | per-cycle | < 100ms at 100K rows | partial (tenant+space+wal_pos indexed; status filters may not be indexed) | Heavy query -- reads 30+ columns per row |
| 3 | Load embeddings by event_id | SELECT event_id, vector, vector_dim FROM st_vec WHERE event_id IN (...) AND status IN ('READY', 'INDEXED') | per-cycle | < 200ms for 1000 IDs | partial (event_id indexed; IN clause) | No pagination -- single query for all events |
| 4 | Load pending gaps | SELECT 7 columns FROM st_learning_queue WHERE status='PENDING' AND gap_type='AMBIGUOUS_ENTITY' AND tenant_id=$1 AND (expires_at IS NULL OR expires_at > $2) ORDER BY importance_score DESC LIMIT 100 | per-cycle (cached 60s) | < 50ms | partial | Cache avoids repeated queries within same cycle |
| 5 | Resolve gap | UPDATE st_learning_queue SET status='RESOLVED', resolution_type='IMPLICIT', resolution_data_json=$1, answered_at=$2 WHERE id=$3 AND status='PENDING' | per-resolved-gap | < 10ms | full (PK) | WHERE status='PENDING' prevents double resolution |
| 6 | Debug: count events for tenant | SELECT COUNT(*) FROM st_hipp_events WHERE tenant_id=$1 AND space_id=$2 | per-cycle (debug) | < 50ms | partial | Debug logging only -- could be removed in production |
| 7 | Debug: get database name | SELECT current_database() | per-cycle (debug) | < 1ms | N/A | Debug logging only |

### 5.4 Storage Gaps

| # | Gap | Current State | Required State | Migration Needed? | Priority |
| - | --- | ------------- | -------------- | ----------------- | -------- |
| 1 | No composite index on (tenant_id, space_id, wal_pos, consolidation_status, embedding_status) | Separate indexes likely | Single composite covering index for R0 eligible event query | maybe | P2 |
| 2 | cognitive_trace_id selected but not mapped | Column read from DB, never assigned to P03EventState | P03EventState should have cognitive_trace_id field, mapped in _row_to_event_state | no (code only) | P1 |
| 3 | Missing MW v2 columns for R0 loading | narrative_thread_id, temporal_anchor, surprise_level, elaboration_depth, identity_relevance, source_reliability, memory_tier not in st_hipp_events | Columns exist (added by P02/MW v2) but not in R0 SELECT | no (code only) | P1 |

---

## 6. Event Bus & Topics

### 6.1 Topics Consumed

| # | Topic | Schema (YAML ref) | Producer Module | Consumer Module | Ordering Guarantee | Idempotency Key |
| - | ----- | ------------------ | --------------- | --------------- | ------------------ | --------------- |
| 1 | p03.consolidation.triggered.v1 | k0/contracts/pipelines/p03_consolidation.v1.yaml (entry_topic) | k0.scheduler (interval/threshold/manual) | consolidation.batch_selector (R0) | unordered | trigger dedup by tenant_id + space_id |

### 6.2 Topics Emitted

| # | Topic | Schema (YAML ref) | Emitter Module | Known Consumers | Payload Size | Frequency |
| - | ----- | ------------------ | -------------- | --------------- | ------------ | --------- |
| N/A | R0 does not emit topics | N/A | N/A | N/A | N/A | N/A |

> **Note**: R0 passes the P03BatchEnvelope in-memory to R1. No bus events are emitted by R0 itself. R8 handles all P03 event emission.

### 6.3 Topic Gaps (needed but missing)

| # | Proposed Topic | Purpose | Producer | Consumer | Schema Draft | Priority |
| - | -------------- | ------- | -------- | -------- | ------------ | -------- |
| 1 | k0.consolidation.batch.selected.v1 | Enable external monitoring of batch selection outcomes | R0 batch_selector | monitoring/dashboards | {tenant_id: str, space_id: str, batch_id: str, event_count: int, duration_ms: int, status: str} | P3 |

> **Note**: The contract declares `p03.batch.selected.v1` as output but R0 does not actually emit it. This is an inconsistency between contract and code.

---

## 7. Observability Audit

### 7.1 Existing Metrics

| # | Metric Name | Type | Location | Labels | Purpose | Alert Threshold |
| - | ----------- | ---- | -------- | ------ | ------- | --------------- |
| N/A | No Prometheus/OTel metrics in R0 | N/A | N/A | N/A | N/A | N/A |

> **Note**: R0 relies entirely on structured logging for observability. No formal metric counters, gauges, or histograms are defined. P03ObservabilityContext exists but R0 does not use it for metrics emission.

### 7.2 Existing Traces / Spans

| # | Span Name | Location | Attributes | Parent Span | Purpose |
| - | --------- | -------- | ---------- | ----------- | ------- |
| N/A | No OpenTelemetry spans in R0 | N/A | N/A | N/A | N/A |

> **Note**: R0 does not create OTel spans. Duration is tracked manually via `int(time.time() * 1000)` and reported in P03PhaseResult.duration_ms. P03CycleContext includes trace_id but no spans are created.

### 7.3 Structured Log Points

| # | Log Level | Location | Message Pattern | Fields | Purpose |
| - | --------- | -------- | --------------- | ------ | ------- |
| 1 | INFO | r0_batch_selector.py:267 | "R0: Starting batch selection phase" | tenant_id, space_id, batch_size | Track R0 start |
| 2 | INFO | r0_batch_selector.py:276 | "R0: Fetched current offset" | tenant_id, space_id, offset | Verify offset read |
| 3 | INFO | r0_batch_selector.py:300 | "R0: No eligible events found, skipping" | tenant_id, space_id, offset, duration_ms | Normal skip detection |
| 4 | INFO | r0_batch_selector.py:325 | "R0: Loaded embeddings from st_vec" | tenant_id, space_id, events_count, embeddings_loaded | Track embedding loading |
| 5 | INFO | r0_batch_selector.py:338 | "R0: Implicitly resolved %d gaps from user context" | tenant_id, space_id, gaps_resolved | Gap resolution success |
| 6 | WARNING | r0_batch_selector.py:347 | "R0: Excluding events without embeddings" | tenant_id, space_id, total_events, events_with_embeddings, excluded | Data quality alert |
| 7 | INFO | r0_batch_selector.py:383 | "R0: Batch selection complete" | cycle_id, tenant_id, space_id, events_selected, offset_start, batch_watermark, duration_ms | Success summary |
| 8 | INFO | r0_batch_selector.py:599 | "R0: Database connection info" | database, total_events_for_tenant_space, query_params, batch_size | Debug: DB connectivity |
| 9 | INFO | r0_batch_selector.py:616 | "R0: Query returned rows" | row_count | Query result |
| 10 | WARNING | r0_batch_selector.py:167 | "R0: Gap auto-resolution failed (non-fatal): %s" | tenant_id, space_id, error | Gap resolution failure |
| 11 | INFO | gap_auto_resolver.py:228 | "Loaded %d pending AMBIGUOUS_ENTITY gaps" | tenant_id, count | Gap loading |
| 12 | INFO | gap_auto_resolver.py:389 | "Auto-resolved gap %s -> '%s' (confidence=%.2f, reason=%s)" | gap_id, resolved_value, confidence, match_reason | Individual gap resolution |

### 7.4 Observability Gaps

| # | Gap | What's Missing | Impact if Unresolved | Priority |
| - | --- | -------------- | -------------------- | -------- |
| 1 | No OTel spans for R0 phase | Span for entire R0 execution with attributes (tenant_id, batch_size, events_selected) | Cannot trace R0 in distributed tracing dashboards; no visibility in Jaeger/Tempo | P1 |
| 2 | No latency histogram for eligible event query | Histogram metric for st_hipp_events query duration | Cannot detect slow queries; no SLO monitoring for R0 query performance | P1 |
| 3 | No counter for batch selection outcomes | Counter with labels: status=selected/empty/error | Cannot track P03 batch selection success rate | P1 |
| 4 | No gauge for pending event count | Gauge reporting total_events_for_tenant_space | Cannot trend pending event backlog | P2 |
| 5 | No embedding load metrics | Counter/histogram for embedding load success/failure/latency | Cannot detect st_vec degradation from R0 perspective | P2 |
| 6 | Debug SQL logging in production | Lines 599-616 log DB name and event count every cycle | Unnecessary overhead in production; should be DEBUG level or removed | P3 |
| 7 | No gap resolution metrics | Counter for gaps_checked, gaps_resolved, gaps_skipped | Cannot monitor gap resolution effectiveness | P2 |

---

## 8. Test Coverage Audit

### 8.1 Existing Tests

| # | Test File | Lines | Test Count | Type | Coverage Target | Pass / Fail | Notes |
| - | --------- | ----- | ---------- | ---- | --------------- | ----------- | ----- |
| 1 | tests/k0/pipelines/p03/test_p03_r0_batch_selector.py | 571 | 13 | unit | R0BatchSelector (offset, batch selection, envelope, results, errors, config) | PASS (assumed) | Uses mocked syscalls and DB connections |

**Test breakdown:**

| Class | Test | What It Proves |
| ----- | ---- | -------------- |
| TestR0OffsetHandling | test_r0_fetches_offset_at_startup | Offset store is queried with correct subscriber_id and topic |
| TestR0OffsetHandling | test_r0_starts_at_zero_when_no_offset | Returns 0 when no prior offset exists |
| TestR0OffsetHandling | test_r0_respects_offset_exactly | Only events with wal_pos > offset are selected |
| TestR0BatchSelection | test_r0_respects_batch_size_limit | Batch size config limits number of events returned |
| TestR0BatchSelection | test_r0_skip_when_no_events | Returns (None, skip_result) when no eligible events |
| TestR0BatchSelection | test_r0_creates_valid_envelope | Envelope has context, events, and correct structure |
| TestR0BatchSelection | test_r0_event_state_population | P03EventState fields populated correctly from DB rows |
| TestR0Results | test_r0_result_includes_outputs_summary | P03PhaseResult.outputs_summary has events_selected, offset_start, batch_id |
| TestR0Results | test_r0_result_has_idempotency_key | Result includes idempotency_key in correct format |
| TestR0Results | test_r0_result_includes_duration | duration_ms is positive integer |
| TestR0ErrorHandling | test_r0_handles_db_error_gracefully | DB errors produce P03PhaseResult.fail, not unhandled exceptions |
| TestR0ErrorHandling | test_r0_error_is_marked_recoverable | Error result has recoverable=True |
| TestR0Configuration | test_r0_default_config | R0Config defaults: batch_size=100, require_embedding_ready=True, exclude_archived=True, max_age_hours=0 |
| TestR0Configuration | test_r0_custom_config | Custom R0Config values are respected |
| TestR0Configuration | test_r0_uses_configured_batch_size | Configured batch_size flows to SQL LIMIT |

### 8.2 Coverage Gaps

| # | Gap | What's Untested | Risk Level | Proposed Test | Test Type |
| - | --- | --------------- | ---------- | ------------- | --------- |
| 1 | No test for gap auto-resolution | _try_auto_resolve_gaps, GapAutoResolver integration with R0 | P1 | test_r0_auto_resolves_matching_gaps: insert pending gap, run R0 with matching entity, assert gap resolved | integration |
| 2 | No test for embedding materialization | _load_embeddings_for_events with real binary vectors | P1 | test_r0_materializes_embeddings_from_st_vec: insert 768-dim vectors in st_vec, run R0, assert embedding_768 populated | integration |
| 3 | No test for timestamp conversion | event_time_utc seconds -> milliseconds conversion logic | P2 | test_r0_converts_seconds_to_milliseconds: row with event_time_utc=1735600 (seconds), assert timestamp=1735600000 | unit |
| 4 | No test for events-without-embeddings filtering | Post-embedding-load filtering step | P2 | test_r0_excludes_events_without_embeddings: some events have no st_vec row, assert filtered out of envelope | integration |
| 5 | No test for module wrapper (batch_selector.py) | Full end-to-end module wrapper with message parsing | P2 | test_batch_selector_module_wrapper: call run() with BusMessage, verify R0Config constructed correctly | unit |
| 6 | No test for large batch performance | batch_size=1000+ with realistic data | P3 | test_r0_performance_large_batch: 5000 events, assert < 500ms p95 | integration |
| 7 | No test for column name aliasing | content_type aliased from activity_category, emotions_json from dominant_emotions_json | P2 | test_r0_column_aliasing: verify all column aliases in_row_to_event_state produce correct P03EventState fields | unit |
| 8 | No test for concurrent R0 executions | Two R0 runs on same tenant/space | P2 | test_r0_concurrent_safety: two parallel R0 calls, verify no duplicate processing | integration |
| 9 | No test for GapAutoResolver similarity matching | Jaccard matching edge cases (empty, single word, exact match, no match) | P2 | test_gap_resolver_similarity_matching: parametrized test over similarity scenarios | unit |

### 8.3 Test Infrastructure Needs

| # | Need | Current State | Required State | Blocking Epic? |
| - | ---- | ------------- | -------------- | -------------- |
| 1 | Shared mock for P03RunnerContext | Each test creates its own mock context | Shared conftest.py fixture with properly mocked syscalls (offset_store, unit_of_work, get_pool) | no |
| 2 | st_hipp_events test fixture with MW v2 columns | Tests use basic column set | Fixture needs all 30+ columns that R0 reads, including MW v2 signals | 5.1 (new signal loading) |
| 3 | Binary vector test helper | No utility for creating binary float32 vectors | Helper function to create 768-dim binary vectors for st_vec test data | no |

---

## 9. Dependency Map

### 9.1 Upstream (what R0 needs)

| # | Dependency | Type | Status | Owner Milestone | Gap if Missing |
| - | ---------- | ---- | ------ | --------------- | -------------- |
| 1 | st_offsets table with P03 subscriber | table | ready | M1 | R0 cannot determine batch start position; would process from offset=0 every time |
| 2 | st_hipp_events with P02/MW v2 columns | table | partial | M3 | Core columns ready; MW v2 signals (narrative_thread_id, surprise_level, etc.) need verification |
| 3 | st_vec with pgvector embeddings | table | ready | M4 | R0 cannot load embeddings; R2 clustering would skip |
| 4 | st_learning_queue with gap records | table | ready | M1 | Gap auto-resolution would find no gaps (non-fatal) |
| 5 | P02 pipeline (writes st_hipp_events) | pipeline | ready | M3 | No events to consolidate |
| 6 | P08 pipeline (writes st_vec) | pipeline | ready | M4 | No embeddings for events |
| 7 | Scheduler (p03.consolidation.triggered.v1) | service | ready | M1 | P03 would never trigger automatically |
| 8 | OffsetStore syscall | syscall | ready | M1 | R0 cannot read offset |
| 9 | UnitOfWork / asyncpg pool | syscall | ready | M1 | R0 cannot query database |

### 9.2 Downstream (what depends on R0)

| # | Dependent | Type | How Used | Impact if Changed | Owner Milestone |
| - | --------- | ---- | -------- | ----------------- | --------------- |
| 1 | R1 importance scorer | pipeline | Reads P03EventState fields (sentiment_score, affect_valence, novelty_score, num_participants, timestamp, activity_type_ultrabert) | Missing or null fields = dead formula components | M5A |
| 2 | R2 episodic integrator | pipeline | Reads P03EventState.embedding_768, timestamp, geohash_6, ner_entities_json | Missing embeddings = events skipped from clustering | M5A |
| 3 | R3 dedup/decay | pipeline | Reads P03EventState.simhash_hex, embedding_768, importance_score, timestamp | Missing simhash = no dedup; missing embedding = no semantic dedup | M5B |
| 4 | R4 KG consolidator | pipeline | Reads P03EventState.ner_entities_json, extracted_relations_json, social_context, intent_ultrabert | Missing NER = no entities extracted | M5 |
| 5 | R5 dream explorer | pipeline | Reads cluster results, importance scores, entity graph from R2-R4 | Indirect dependency through R1-R4 outputs | M5D |
| 6 | R6 staging | pipeline | Reads all P03EventState fields for staging | Any field change in R0 propagates through entire pipeline | M5 |
| 7 | SequentialRunner | module | Calls R0 as first phase; expects (envelope, result) tuple | Signature change breaks runner | M1 |
| 8 | PipelineRunner | module | Calls batch_selector.run() with module interface | Return dict format change breaks runner | M1 |

### 9.3 External Dependencies (libraries, services, extensions)

| # | Dependency | Version | Purpose | License | Pinned? | Upgrade Risk |
| - | ---------- | ------- | ------- | ------- | ------- | ------------ |
| 1 | asyncpg | >=0.29.0 | PostgreSQL async driver for direct SQL queries | Apache-2.0 | yes | low |
| 2 | struct (stdlib) | N/A | Binary float32 vector decoding | PSF | N/A | none |
| 3 | json (stdlib) | N/A | NER JSON parsing, gap context parsing | PSF | N/A | none |
| 4 | re (stdlib) | N/A | Entity normalization, proper noun extraction | PSF | N/A | none |
| 5 | time (stdlib) | N/A | Millisecond timestamps | PSF | N/A | none |
| 6 | pgvector (PostgreSQL extension) | 0.5+ | VECTOR type in st_vec | PostgreSQL | server-side | low |

---

## 10. Performance Baseline

### 10.1 Current Benchmarks

| # | Operation | Dataset Size | p50 | p95 | p99 | Throughput | Memory Peak | Notes |
| - | --------- | ------------ | --- | --- | --- | ---------- | ----------- | ----- |
| N/A | No formal benchmarks exist for R0 | N/A | N/A | N/A | N/A | N/A | N/A | R0 performance inferred from log timing only |

### 10.2 Known Bottlenecks

| # | Bottleneck | Location | Cause | Measured Impact | Proposed Fix | Priority |
| - | ---------- | -------- | ----- | --------------- | ------------ | -------- |
| 1 | Single embedding query for all events | r0_batch_selector.py:746 | SELECT ... WHERE event_id IN (all 1000 IDs) creates large IN clause | Estimated ~200ms for 1000 IDs | Chunk into batches of 200 with UNION or multiple queries | P2 |
| 2 | 30+ column SELECT | r0_batch_selector.py:528 | Reads all columns from st_hipp_events even if downstream phases don't need all | Estimated ~50ms overhead at 100K rows | Investigate column-specific projection if some MW v2 signals are large | P3 |
| 3 | Debug COUNT query | r0_batch_selector.py:596 | SELECT COUNT(*) every cycle for debug logging | ~50ms overhead per cycle | Remove or gate behind DEBUG log level | P3 |
| 4 | Binary vector decode per-row | r0_batch_selector.py:779 | struct.unpack one-at-a-time for each vector | ~0.1ms per vector * 1000 = ~100ms | Use numpy for bulk decode if available | P3 |

### 10.3 Performance Targets

| # | Operation | Target p95 | Target Throughput | Target Memory | Acceptance Criteria |
| - | --------- | ---------- | ----------------- | ------------- | ------------------- |
| 1 | R0 full phase (100 events) | < 200ms | > 500 events/s | < 64MB | Benchmark with 100 events, real pgvector DB |
| 2 | R0 full phase (1000 events) | < 1000ms | > 1000 events/s | < 256MB | Benchmark with 1000 events, 768-dim vectors |
| 3 | Gap auto-resolution | < 100ms | N/A | < 16MB | Gap resolution should not add > 100ms to R0 latency |
| 4 | Embedding materialization (1000 vectors) | < 500ms | > 2000 vectors/s | < 128MB (1000 *768* 8 bytes = ~6MB) | Binary decode + validation for 1000 vectors |

---

## 11. Gap Analysis & Enhancement Register

### 11.1 Functional Gaps

| # | Gap ID | Gap Description | Current State | Desired State | Severity | Proposed Fix | Related ADR |
| - | ------ | --------------- | ------------- | ------------- | -------- | ------------ | ----------- |
| 1 | FG-001 | MW v2 signals not loaded by R0 | R0 SELECT does not include narrative_thread_id, temporal_anchor, surprise_level, elaboration_depth, identity_relevance, source_reliability, memory_tier | R0 loads all MW v2 signals and populates P03EventState | P1 | Add columns to R0 SQL, add fields to P03EventState, map in _row_to_event_state | ADR-K010 |
| 2 | FG-002 | cognitive_trace_id selected but not propagated | Column read from st_hipp_events but not mapped to P03EventState | cognitive_trace_id available as P03EventState field for R3 conversation-dedup | P1 | Add field to P03EventState, map in _row_to_event_state | ADR-K010 |
| 3 | FG-003 | No adaptive batch sizing | Fixed batch_size regardless of system state | Batch size adapts to pending count, system load, recent cycle duration | P2 | Implement adaptive sizing in R0Config or a sizing helper | none |
| 4 | FG-004 | Embedding loading has no pagination | Single query with large IN clause for all events | Chunked embedding loading in batches of 200 | P2 | Add chunked query logic in _load_embeddings_for_events | none |
| 5 | FG-005 | Gap matching uses Jaccard only | Simple word-set Jaccard similarity | Semantic similarity using embeddings for better entity matching | P3 | Add embedding-based similarity path in GapAutoResolver | none |
| 6 | FG-006 | Contract says output p03.batch.selected.v1 but R0 never emits it | Contract and code are inconsistent | Either emit the event or remove from contract | P2 | Decide: emit event for monitoring or remove from contract | none |
| 7 | FG-007 | P03EventState flat list -- no indexing | envelope.events is a plain list; downstream phases build dict on each access | Pre-build event_id index dict on envelope | P3 | Add _event_index: dict[str, P03EventState] to P03BatchEnvelope | none |
| 8 | FG-008 | Duplicate return statements in idempotency_key | 6 identical return statements (dead code) | Single return statement | P3 | Remove 5 duplicate returns | none |

### 11.2 Contract Gaps

| # | Contract | Section / Field | Gap | Impact | Fix |
| - | -------- | --------------- | --- | ------ | --- |
| 1 | k0/contracts/modules/consolidation.batch_selector.v1.yaml | output_event_types | Lists p03.batch.selected.v1 but R0 never emits it | Contract promises event that is never produced | Either implement emission or remove from contract |
| 2 | k0/contracts/modules/consolidation.batch_selector.v1.yaml | side_effects | Lists read:st_pipeline_status but R0 never reads it | Contract claims dependency that doesn't exist in code | Remove read:st_pipeline_status, add read:st_vec, read:st_learning_queue, write:st_learning_queue |
| 3 | k0/contracts/modules/consolidation.batch_selector.v1.yaml | latency_budget_ms | 50ms is unrealistic for batch of 1000 events with embedding loading | Budget appears to be per-event, but R0 is a batch operation | Clarify: is this per-event or per-batch? Adjust to realistic target |

### 11.3 Architecture Gaps

| # | Area | Gap | ADR Needed? | Impact | Proposed Resolution |
| - | ---- | --- | ----------- | ------ | ------------------- |
| 1 | syscall abstraction | R0 uses raw SQL via uow._connection instead of typed syscalls | update | Bypasses capability checking, SQL injection surface (parameterized mitigates), harder to mock | Create typed syscalls: hipp_events_eligible_batch(), vec_batch_by_event_ids() |
| 2 | observability | No OTel spans or Prometheus metrics in R0 | no | Cannot trace R0 in production dashboards | Add spans and metrics per Section 7.4 |
| 3 | module protocol | R0 has different signature than R1-R8 (creates envelope vs receives it) | no (by design) | SequentialRunner must special-case R0 | Documented in dossier; acceptable tradeoff |

---

## 12. Security & Privacy Audit

### 12.1 Data Classification

| # | Field / Column | Classification | Handling | Retention Policy | Notes |
| - | -------------- | -------------- | -------- | ---------------- | ----- |
| 1 | st_hipp_events.text | PII | plain (in transit and at rest) | until tenant deletion | Raw user-generated content -- highest sensitivity |
| 2 | st_hipp_events.ner_entities_json | PII | plain | until tenant deletion | Contains person names, locations, organizations from user text |
| 3 | st_hipp_events.participants_json | PII | plain | until tenant deletion | Family member identifiers |
| 4 | st_hipp_events.actor_id | PII | plain | until tenant deletion | User identity |
| 5 | st_hipp_events.location_name | PII | plain | until tenant deletion | User location data |
| 6 | st_hipp_events.geohash_6 | PII | plain | until tenant deletion | Geolocation at ~1.2km precision |
| 7 | st_vec.vector | internal | plain | until tenant deletion | Embedding of user text -- derived from PII, not directly reversible |
| 8 | st_learning_queue.entity_id | internal | plain | until gap expiration | Entity cluster ID, not directly PII |
| 9 | st_learning_queue.resolution_data_json | PII | plain | until gap expiration | Contains resolved_value which is entity text from user content |
| 10 | P03EventState (in-memory) | PII | plain (memory) | duration of P03 cycle | Holds all st_hipp_events PII in memory during processing |
| 11 | tenant_id, space_id | internal | plain | indefinite | Multi-tenant keys, not PII themselves |

### 12.2 Capability Boundaries

| # | Operation | Required Capability | Enforced? | Enforcement Location | Gap |
| - | --------- | ------------------- | --------- | -------------------- | --- |
| 1 | Read st_hipp_events | st_hipp_events.read | partial | k0/contracts/pipelines/p03_consolidation.v1.yaml (declared) | Declared in contract but R0 uses raw SQL, no runtime capability check |
| 2 | Read st_offsets | st_offsets.read | yes | offset_store syscall enforces | Properly gated through syscall |
| 3 | Read st_vec | st_vec.read | partial | declared in pipeline contract | R0 uses raw SQL, no runtime check |
| 4 | Read st_learning_queue | st_learning_queue.read | partial | get_pool() gated, but query itself not checked | Pool access checked; individual query not |
| 5 | Write st_learning_queue | st_learning_queue.write | partial | get_pool() gated | UPDATE gap resolution not capability-checked at query level |

### 12.3 Input Validation & Sanitization

| # | Input Source | Validation Applied | Sanitization Applied | Injection Risk | Notes |
| - | ----------- | ------------------ | -------------------- | -------------- | ----- |
| 1 | BusMessage trigger payload | JSON parse with try/except, type check | none | low | Parameterized queries prevent SQL injection |
| 2 | tenant_id from message | Defaults to "default" if missing | none | low | Used as parameterized SQL value |
| 3 | space_id from message | Defaults to "default" if missing | none | low | Parameterized |
| 4 | st_hipp_events rows | Column type coercion (float(), int()) with fallback to defaults | none | none | Data from trusted internal DB |
| 5 | st_vec.vector binary | Size validation (expected_bytes = dim * 4), struct.unpack validation | none | none | Binary data from trusted internal DB |
| 6 | st_learning_queue.context_json | JSON parse with try/except | none | low | Parameterized queries for writes |
| 7 | NER entities JSON (ner_entities_json) | JSON parse with try/except; type checks (dict vs list) | none | none | Already parsed and stored by P02 |

---

## 13. Enhancement Proposals

### 13.1 Proposed Epics

| Epic ID | Title | Scope Summary | Estimated Files | Priority | Dependencies | Issue Count |
| ------- | ----- | ------------- | --------------- | -------- | ------------ | ----------- |
| 5.1A | R0 MW v2 Signal Loading | Add all MW v2 signals to R0 SELECT, P03EventState, and row mapping | 2 MOD | P1 | none | 4 |
| 5.1B | R0 Observability Enhancement | Add OTel spans, Prometheus metrics, and proper structured logging | 2 MOD | P1 | none | 3 |
| 5.1C | R0 Contract & Code Alignment | Fix contract/code inconsistencies, add typed syscalls | 3 MOD | P2 | none | 3 |
| 5.1D | R0 Performance & Robustness | Chunked embedding loading, adaptive batch sizing, dead code cleanup | 2 MOD | P2 | 5.1A | 4 |

### 13.2 Epic Detail

---

#### Epic 5.1A -- R0 MW v2 Signal Loading

**Summary**: Adds all MW v2 signals (narrative_thread_id, temporal_anchor, surprise_level, elaboration_depth, identity_relevance, source_reliability, memory_tier, cognitive_trace_id) to R0 SELECT, P03EventState fields, and _row_to_event_state mapping.

**Problem**: R0 does not load 8 MW v2 signals from st_hipp_events, causing downstream phases (R1 importance, R2 clustering, R3 decay/immunity) to operate with incomplete data. 55% of the R1 importance formula depends on signals R0 does not currently provide.

**Solution**: Add the 8 missing columns to the R0 SQL query, add corresponding fields to P03EventState, and map them in _row_to_event_state. Verify columns exist in st_hipp_events schema before adding.

##### Inputs

| # | Input | Type | Source | Validation |
| - | ----- | ---- | ------ | ---------- |
| 1 | st_hipp_events rows with MW v2 columns | asyncpg.Record | PostgreSQL st_hipp_events table | Column existence checked; None/NULL defaults to appropriate empty/0 value |

##### Outputs

| # | Output | Type | Consumer | Guarantees |
| - | ------ | ---- | -------- | ---------- |
| 1 | P03EventState with 8 new fields populated | P03EventState | R1 (surprise_level, elaboration_depth, source_reliability, identity_relevance), R2 (narrative_thread_id, temporal_anchor), R3 (memory_tier, identity_relevance, cognitive_trace_id) | All new fields have safe defaults (0.0, "", None) when column is NULL |

##### Algorithm Changes

| # | Algorithm | Change Type | Before | After | Rationale |
| - | --------- | ----------- | ------ | ----- | --------- |
| 1 | eligible_event_query | modify | SELECT 30 columns | SELECT 38 columns (add 8 MW v2 fields) | Missing signals cause dead formula components in R1-R3 |
| 2 | row_to_event_state_mapping | modify | Maps 30 columns to P03EventState | Maps 38 columns including new MW v2 fields | New fields must be propagated to downstream phases |

##### Config Changes

| # | Key / Variable / Flag | Change | Old Value | New Value | Type | Notes |
| - | --------------------- | ------ | --------- | --------- | ---- | ----- |
| N/A | No config changes | N/A | N/A | N/A | N/A | New signals always loaded when columns exist |

##### Contract Changes

| # | Contract File | Change | Section | Details |
| - | ------------- | ------ | ------- | ------- |
| 1 | k0/contracts/modules/consolidation.batch_selector.v1.yaml | modify | side_effects | Add read:st_hipp_events columns: narrative_thread_id, temporal_anchor, surprise_level, elaboration_depth, identity_relevance, source_reliability, memory_tier |

##### Storage Changes

| # | Table | Operation | Column(s) | Migration File | Reversible? |
| - | ----- | --------- | --------- | -------------- | ----------- |
| N/A | No storage changes | N/A | MW v2 columns already exist in st_hipp_events (added by P02) | N/A | N/A |

##### Syscall Changes

| # | Syscall | Change | Before Signature | After Signature | Notes |
| - | ------- | ------ | ---------------- | --------------- | ----- |
| N/A | No syscall changes | N/A | N/A | N/A | R0 uses raw SQL (syscall wrapping deferred to 5.1C) |

##### Event / Topic Changes

| # | Topic | Change | Schema Change | Impact |
| - | ----- | ------ | ------------- | ------ |
| N/A | No topic changes | N/A | N/A | N/A |

##### Test Plan

| # | Test File | Test Name | Type | What It Proves | Priority |
| - | --------- | --------- | ---- | -------------- | -------- |
| 1 | tests/k0/pipelines/p03/test_p03_r0_batch_selector.py | test_r0_loads_mw_v2_signals | unit | All 8 MW v2 fields populated in P03EventState from DB row | P0 |
| 2 | tests/k0/pipelines/p03/test_p03_r0_batch_selector.py | test_r0_mw_v2_null_defaults | unit | NULL MW v2 columns default to safe values (0.0, "", None) | P0 |
| 3 | tests/k0/pipelines/p03/test_p03_r0_batch_selector.py | test_r0_cognitive_trace_id_propagated | unit | cognitive_trace_id from DB row appears in P03EventState | P0 |
| 4 | tests/k0/pipelines/p03/test_p03_r0_batch_selector.py | test_r0_event_state_has_mw_v2_fields | unit | P03EventState dataclass has all 8 new fields with correct types and defaults | P0 |

##### Risks

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | MW v2 columns may not exist in all deployments | med | med | Use row.get() with defaults; test with and without columns |
| 2 | Adding 8 columns increases memory per P03EventState | low | low | Float fields add ~64 bytes per event; negligible for 1000 events |

##### Acceptance Criteria

- [ ] Given a st_hipp_events row with all MW v2 columns populated, when R0 runs, then P03EventState has narrative_thread_id, temporal_anchor, surprise_level, elaboration_depth, identity_relevance, source_reliability, memory_tier, cognitive_trace_id fields set
- [ ] Given a st_hipp_events row with NULL MW v2 columns, when R0 runs, then P03EventState has safe defaults (0.0 for floats, "" for strings, None for optional)
- [ ] Given the updated P03EventState, when R1 reads surprise_level, then the value matches what was stored in st_hipp_events
- [ ] All 4 new tests pass

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.1A.1 | Add MW v2 fields to P03EventState | Add 8 new fields to P03EventState dataclass with types and defaults | S | none | dataclass has all 8 fields with correct types |
| 5.1A.2 | Add MW v2 columns to R0 SQL SELECT | Add 8 columns to the eligible events query | S | 5.1A.1 | SQL includes all 8 columns |
| 5.1A.3 | Map MW v2 columns in _row_to_event_state | Add row.get() mappings for all 8 new columns | S | 5.1A.1 | All 8 fields populated from DB row |
| 5.1A.4 | Write MW v2 signal loading tests | 4 test functions covering signal loading, null defaults, propagation | S | 5.1A.3 | All 4 tests pass |

---

#### Epic 5.1B -- R0 Observability Enhancement

**Summary**: Adds OpenTelemetry spans, Prometheus-compatible metrics (counters, histograms), and cleans up debug logging for production readiness.

**Problem**: R0 has zero OTel spans, zero formal metrics, and includes debug SQL logging that runs every cycle. Production visibility is limited to grepping structured logs.

**Solution**: Add OTel span for R0 phase, add metrics for batch selection outcomes, query latency, and embedding load; remove or gate debug queries.

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.1B.1 | Add OTel span for R0 phase | Wrap R0BatchSelector.run in span with tenant_id, batch_size, events_selected attributes | S | none | Span visible in trace output |
| 5.1B.2 | Add Prometheus metrics | Counter for batch outcomes (selected/empty/error), histogram for R0 duration, gauge for embedding load count | M | none | Metrics exported with correct labels |
| 5.1B.3 | Clean debug logging | Remove or gate SELECT COUNT(*) and current_database() queries; standardize log levels | S | none | No unnecessary queries in production; debug queries gated behind DEBUG level |

---

#### Epic 5.1C -- R0 Contract & Code Alignment

**Summary**: Fixes inconsistencies between contract YAML and R0 code, adds missing side effects, and addresses the p03.batch.selected.v1 output event gap.

**Problem**: Contract declares p03.batch.selected.v1 output and read:st_pipeline_status side effect that don't exist in code. Contract is missing read:st_vec, read:st_learning_queue, write:st_learning_queue.

**Solution**: Update contract YAML to match actual code behavior. Decide whether to implement p03.batch.selected.v1 emission or remove from contract.

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.1C.1 | Fix contract side_effects | Update consolidation.batch_selector.v1.yaml: remove read:st_pipeline_status, add read:st_vec, read:st_learning_queue, write:st_learning_queue | S | none | Contract matches actual R0 behavior |
| 5.1C.2 | Resolve p03.batch.selected.v1 gap | Decide: implement event emission or remove from contract output_event_types | S | none | Contract and code agree |
| 5.1C.3 | Fix duplicate return statements | Remove 5 duplicate return lines in idempotency_key method | S | none | Single return, no dead code |

---

#### Epic 5.1D -- R0 Performance & Robustness

**Summary**: Improves R0 performance through chunked embedding loading and removes known inefficiencies.

**Problem**: Embedding loading uses a single IN clause for up to 1000 event_ids. Debug queries add unnecessary latency.

**Solution**: Chunk embedding queries into batches of 200, add optional adaptive batch sizing.

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.1D.1 | Chunked embedding loading | Split _load_embeddings_for_events into chunks of 200 IDs | S | none | Embedding loading works for 1000+ events without large IN clause |
| 5.1D.2 | Add event_id index to P03BatchEnvelope | Add _event_index dict for O(1) lookup by event_id | S | none | Downstream phases can call envelope.get_event(event_id) in O(1) |
| 5.1D.3 | Performance benchmark test | Create benchmark test for R0 with 1000 events + 768-dim vectors | M | 5.1A | Benchmark completes in < 1000ms p95 |
| 5.1D.4 | Adaptive batch sizing (optional) | Implement batch size that considers pending count and last cycle duration | M | none | Batch size scales between 100-2000 based on conditions |

---

## 14. Risk Register

| # | Risk ID | Risk | Category | Likelihood | Impact | Risk Score | Mitigation | Owner | Status |
| - | ------- | ---- | -------- | ---------- | ------ | ---------- | ---------- | ----- | ------ |
| 1 | R-001 | MW v2 columns may not exist in all st_hipp_events deployments | technical | med | med | medium | Use row.get() with safe defaults; verify column existence before adding to SELECT | dev-lead | open |
| 2 | R-002 | Adding new P03EventState fields may break existing tests | technical | low | low | low | All new fields have defaults; existing tests don't reference new fields | dev-lead | open |
| 3 | R-003 | Raw SQL in R0 bypasses capability security model | security | low | med | low | Capability checks happen at pool/uow level; typed syscalls planned for 5.1C | dev-lead | open |
| 4 | R-004 | Gap auto-resolution may false-match common entity names | technical | med | low | low | MIN_SIMILARITY=0.6 and AUTO_RESOLVE_THRESHOLD=0.75 provide reasonable guards; monitor resolution accuracy | dev-lead | accepted |
| 5 | R-005 | Large batch embedding loading may timeout on slow networks | performance | low | med | low | Chunked loading (5.1D.1) mitigates; connection timeout exists at pool level | dev-lead | open |

---

## 15. Open Questions

| # | Question | Context | Blocking? | Answer | Status | Answered By | Date |
| - | -------- | ------- | --------- | ------ | ------ | ----------- | ---- |
| 1 | Do all MW v2 columns (narrative_thread_id, temporal_anchor, surprise_level, elaboration_depth, identity_relevance, source_reliability, memory_tier) exist in current st_hipp_events schema? | R0 needs to SELECT these columns -- will fail if they don't exist | yes | | open | | |
| 2 | Should p03.batch.selected.v1 be emitted by R0 or removed from contract? | Contract declares it but code doesn't emit it | no | | open | | |
| 3 | Should R0 use typed syscalls instead of raw SQL? | Raw SQL bypasses abstraction but is faster and more flexible | no | | open | | |
| 4 | What is the realistic latency budget for R0? Contract says 50ms but batch operation with 1000 events + embedding loading takes > 500ms | Affects performance targets and alerting thresholds | no | | open | | |
| 5 | Should gap auto-resolution be a separate pre-R0 step or remain integrated in R0? | Currently embedded in R0 flow; could be extracted for clarity and testability | no | | open | | |

---

## Appendix A: Glossary

| Term | Definition |
| ---- | ---------- |
| R0 | Phase 0 (Batch Selection) -- Entry point for P03 consolidation pipeline; creates P03BatchEnvelope |
| P03BatchEnvelope | Top-level container flowing through R0-R8: holds P03CycleContext + list[P03EventState] + phase outputs |
| P03EventState | Mutable per-event dataclass enriched by each phase: starts with R0 hydration, accumulates R1-R7 results |
| P03CycleContext | Frozen batch-level metadata set in R0: cycle_id, batch_id, tenant/space, event_ids, trigger info |
| wal_pos | Write-Ahead Log position in st_hipp_events used as offset cursor for batch selection |
| MW v2 | Memory Writer version 2 -- P02 pipeline that computes UltraBERT signals and writes to st_hipp_events |
| GapAutoResolver | Module that matches NER entities against pending AMBIGUOUS_ENTITY gaps in st_learning_queue |
| ULID | Universally Unique Lexicographically Sortable Identifier -- used for cycle_id, batch_id |
| SimHash | 64-bit locality-sensitive hash for fuzzy text deduplication |
| P03_SUBSCRIBER_ID | "P03_CONSOLIDATE" -- identifier in st_offsets for P03's batch cursor position |
| PII | Personally Identifiable Information -- user text, names, locations, participant IDs |

## Appendix B: References

| # | Document | Path / URL | Relevance |
| - | -------- | ---------- | --------- |
| 1 | P03 Consolidation Dossier v2 | docs/pipelines/P03_consolidation_dossier_v2.md | Pipeline scope, stage definitions, R0 specification |
| 2 | ADR-K010 P03 Consolidation Architecture | docs/architecture/decisions-K0/k010-p03-consolidation-architecture.md | Foundational architecture for P03 phases |
| 3 | ADR-K010.1 Sleep-Cycle State Machine | docs/architecture/decisions-K0/k010.1-sleep-cycle-state-machine.md | R0-R8 phase sequencing and state machine |
| 4 | ADR-K010.9 Capability-Based Security | docs/architecture/decisions-K0/k010.9-capability-based-security.md | Capability model for P03 storage access |
| 5 | ADR-K003-v2 pgvector Migration | docs/architecture/decisions-K0/adr-k003-v2-pgvector-migration.md | st_vec schema, FAISS elimination, pgvector native |
| 6 | Master Implementation Skeleton M5 | docs/plans/MASTER_IMPLEMENTATION_SKELETON.md (M5 section, line 5053) | Epic 5.1 R0 discovery spec, signal gaps, known issues |
| 7 | P03 Pipeline Contract | k0/contracts/pipelines/p03_consolidation.v1.yaml | Pipeline stages, triggers, capabilities, topics |
| 8 | R0 Module Contract | k0/contracts/modules/consolidation.batch_selector.v1.yaml | Module interface, latency budget, failure modes |
