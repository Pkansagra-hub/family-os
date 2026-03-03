# P03 R6 Staging Discovery & Enhancement Plan

> **Discovery document for Epic 5.7 -- R6 Staging.** Follows DISCOVERY_TEMPLATE.md (15 sections + appendices).
> R6 is the staging/assembly phase that sits between R5 (Dream Exploration) and R7 (Truth Writing).
> It accumulates all R1-R5 outputs, assembles per-layer truth writes, validates the manifest,
> and prepares everything for R7's atomic commit.
>
> **Key design principle**: R6 does NOT write to the database -- it stages writes for R7 to execute atomically.

---

## 0. Discovery Metadata

| Field | Value |
| ----- | ----- |
| Pipeline ID | P03 |
| Module Scope | consolidation.staging.r6_coordinator, consolidation.staging.status_marker, consolidation.staging.dedup_metadata, consolidation.staging.reconciliation_recorder, consolidation.staging.idempotency, consolidation.staging.truth_write_assembler, consolidation.staging.kg_write_assembler, consolidation.staging.outbox_assembler, consolidation.staging.manifest_validator, consolidation.staging.summary_generator, consolidation.staging.intent_signal_assembler, consolidation.staging.truth_query_service, consolidation.staging.r6_output |
| Discovery Date | 2026-03-02 |
| Milestone Target | M5 |
| Governing ADRs | ADR-K003 (pgvector migration, no FAISS) |
| Related Dossier | `docs/pipelines/P03_consolidation_dossier_v2.md` |
| Author | copilot-claude |
| Status | DRAFT |

**Scope Summary**:

R6 Staging is the assembly and validation phase of the P03 consolidation pipeline. It receives outputs from all prior phases (R0-R5), transforms them into a set of staged writes grouped by truth table layer, validates the complete manifest, and hands off to R7 for atomic database commit. R6 is a pure data-transformation phase with no database side-effects.

**Key Design Principle**:

R6 follows the **staged writes pattern**: all database mutations are accumulated as `StagedWrite` objects grouped by layer in `P03StagedWrites`. R7 executes these atomically via UnitOfWork, ensuring either all writes succeed or none do. This separation enables manifest validation, idempotency key verification, and FK integrity checking before any data is committed.

---

## 1. Current State Audit

### 1.1 Code Inventory

| # | File (relative path) | Lines | Status | Last Modified | Purpose |
| - | -------------------- | ----: | ------ | ------------- | ------- |
| 1 | k0/pipelines/p03/phases/r6_staging.py | 612 | MOD | M5 | Implements R6 pipeline phase: extracts R1-R5 inputs from envelope, creates R6Coordinator, executes staging workflow, populates envelope with R6Output |
| 2 | k0/modules/consolidation/staging/r6_coordinator.py | 590 | MOD | M5 | Orchestrates all 10 R6 sub-components into a sequential staging pipeline with step timing |
| 3 | k0/modules/consolidation/staging/r6_output.py | 801 | MOD | M5 | Defines R6Output (frozen), StagedEventUpdate, ReconciliationSummary, and StagedWritesContainer (mutable builder) dataclasses |
| 4 | k0/modules/consolidation/staging/status_marker.py | 293 | MOD | M5 | Determines consolidation_status (CONSOLIDATED/DUPLICATE/PRUNED/PENDING_REVIEW) per event based on R1-R5 outcomes |
| 5 | k0/modules/consolidation/staging/dedup_metadata.py | 303 | MOD | M5 | Populates dedup metadata (near_duplicates_json, novelty_score, episode_cluster_id) from DuplicateDetector results |
| 6 | k0/modules/consolidation/staging/reconciliation_recorder.py | 253 | MOD | M5 | Records complete reconciliation decision history per event for audit trail |
| 7 | k0/modules/consolidation/staging/idempotency.py | 279 | MOD | M5 | Generates deterministic idempotency keys for staging, write, emit, and phase operations using SHA-256 batch hashing |
| 8 | k0/modules/consolidation/staging/truth_write_assembler.py | 2,034 | MOD | M5 | Assembles staged writes for ALL truth layers from R2-R5 outputs. Largest R6 file. Handles st_epi, st_sem, st_procedural, st_social, st_prospective, st_mcts, st_learning_queue |
| 9 | k0/modules/consolidation/staging/kg_write_assembler.py | 857 | MOD | M5 | Assembles staged writes for KG layers (st_kg_dom entities and st_kg_edges relationships) with FK validation and edge merge logic |
| 10 | k0/modules/consolidation/staging/outbox_assembler.py | 572 | MOD | M5 | Assembles outbox events for R8 emission: completion, decision (per-action), gap, insight events with priority ordering |
| 11 | k0/modules/consolidation/staging/manifest_validator.py | 532 | MOD | M5 | Validates R6Output manifest with 7 rules: layer validity, idempotency key format, FK integrity, event coverage, outbox minimum, duplicate record detection, version conflict threshold |
| 12 | k0/modules/consolidation/staging/summary_generator.py | 324 | MOD | M5 | Generates ReconciliationSummary with action/status counts, layer write counts, KG/gap/insight/counterfactual counts, and cycle duration |
| 13 | k0/modules/consolidation/staging/intent_signal_assembler.py | 653 | NEW | M5 | Routes 6 intent signal types from R5 IntentSignalDetector to appropriate truth layer writes (GAP-001) |
| 14 | k0/modules/consolidation/staging/truth_query_service.py | 663 | MOD | M5 | Async service querying truth layers for reconciliation candidates using vector similarity search (pgvector) and decay candidates |
| 15 | k0/modules/consolidation/staging/**init**.py | 202 | MOD | M5 | Package init re-exporting 48 public symbols across 11 issue modules |
| 16 | k0/pipelines/p03/staged_writes.py | 629 | MOD | M5 | Defines P03StagedWrites container, StagedWrite, StagedOutboxEvent, WriteOperation enum, and 11 LAYER_* constants |
| **TOTAL** | | **8,968** | | | |

### 1.2 Contract Inventory

| # | Contract File | Version | Status | Lines | Governs |
| - | ------------- | ------- | ------ | ----: | ------- |
| 1 | k0/contracts/modules/consolidation.status_updater.v1.yaml | v1 | active | 71 | module:consolidation.status_updater (R6 status update) |
| 2 | k0/contracts/pipelines/p03_consolidation.v1.yaml (stage_60) | v1 | active | 433 (R6 at lines 338-358) | pipeline:p03 stage_60_status_update |

**Contract Issues**:

| Issue | Severity | Detail |
|-------|----------|--------|
| Contract names R6 "status_updater" but code is "r6_coordinator" | HIGH | Contract `consolidation.status_updater` describes a narrow status-update module. Actual R6 code is a full staging orchestrator with 10 sub-components. The contract underdescribes R6 by ~90%. |
| Pipeline contract stage_60 is too simplistic | HIGH | Stage_60 describes only status update + audit write. Actual R6 performs: status marking, dedup metadata population, reconciliation recording, idempotency key generation, truth write assembly (7 tables), KG write assembly (2 tables), outbox event assembly, intent signal routing, manifest validation, summary generation. |
| No standalone R6 coordinator contract | HIGH | The R6Coordinator orchestrates 10 sub-components but has no module contract. No input/output schema, latency budget, or capability requirements are formally defined for the coordinator. |
| Missing intent signal assembler contract | MEDIUM | IntentSignalAssembler (GAP-001) routes 6 signal types but has no contract YAML. |
| Missing truth query service contract | MEDIUM | TruthQueryService does async pgvector queries but has no contract defining latency budget or query patterns. |

### 1.3 Config Inventory

#### 1.3.1 YAML Config Keys

R6 has no dedicated YAML configuration file. Configuration is passed programmatically via `R6CoordinatorConfig` dataclass. The pipeline contract specifies minimal config:

| Config File | Version | Key (dot-path) | Value | Type | Default | Required | Notes |
| ----------- | ------- | --------------- | ----- | ---- | ------- | -------- | ----- |
| p03_consolidation.v1.yaml | v1 | stage_60.config.status_values.success | CONSOLIDATED | str | CONSOLIDATED | yes | Final status for processed events |
| p03_consolidation.v1.yaml | v1 | stage_60.config.status_values.archived | ARCHIVED | str | ARCHIVED | yes | Status for archived events |
| p03_consolidation.v1.yaml | v1 | stage_60.config.status_values.pruned | TOMBSTONED | str | TOMBSTONED | yes | Status for pruned events |
| p03_consolidation.v1.yaml | v1 | stage_60.config.write_audit | true | bool | true | no | Enable audit trail writing |

#### 1.3.2 Environment Variables

R6 does not read any environment variables directly. All configuration flows through R6CoordinatorConfig.

#### 1.3.3 Feature Flags

| Flag Name | Source | Default | Scope | Controls | Rollback Behavior |
| --------- | ------ | ------- | ----- | -------- | ----------------- |
| R6CoordinatorConfig.dry_run | code | false | global | When true, R6 assembles but does not populate envelope (no writes reach R7) | Safe -- next run executes normally |
| R6CoordinatorConfig.validate_manifest | code | true | global | Enable/disable ManifestValidator step. If false, skips validation entirely. | Risky -- invalid manifests pass to R7 unchecked |
| R6CoordinatorConfig.emit_metrics | code | true | global | Enable/disable R6 metrics emission | Safe -- no data loss, metrics stop |

#### 1.3.4 Constants & Magic Numbers

| Constant | Location (file:line) | Value | Type | Rationale | Externalize? |
| -------- | -------------------- | ----- | ---- | --------- | ------------ |
| `STATUS_CONSOLIDATED` | r6_output.py:52 | `"CONSOLIDATED"` | str | Primary success status matching pipeline contract | no -- tied to contract |
| `STATUS_DUPLICATE` | r6_output.py:53 | `"DUPLICATE"` | str | Near-duplicate detected by R3 DuplicateDetector | no -- tied to contract |
| `STATUS_PRUNED` | r6_output.py:54 | `"PRUNED"` | str | Pruned by R3 decay or R2 quality filter | no -- tied to contract |
| `STATUS_PENDING_REVIEW` | r6_output.py:55 | `"PENDING_REVIEW"` | str | Low confidence reconciliation, needs human review | no -- tied to contract |
| `LOW_CONFIDENCE_THRESHOLD` | status_marker.py | `0.5` | float | Below this, events with match get PENDING_REVIEW instead of CONSOLIDATED | yes -- should be configurable |
| `VERSION_CONFLICT_THRESHOLD` | manifest_validator.py:111 | `0.10` (10%) | float | If >10% of writes have version conflicts, DLQ the entire batch | yes -- should be adaptive per skeleton Part D |
| `MAX_KEY_LENGTH` | idempotency.py:44 | `200` | int | Maximum idempotency key length for DB column constraints | no -- tied to DB schema |
| `BATCH_HASH_LENGTH` | idempotency.py:47 | `12` | int | Truncated SHA-256 hex for batch idempotency keys. 12 hex = 6 bytes = 48 bits = ~281 trillion space | maybe -- collision risk at extreme scale |
| `VALID_ENTITY_TYPES` | kg_write_assembler.py:46 | `{"PERSON","LOCATION","ORG","THING","CONCEPT"}` | frozenset | KG entity types accepted for staging | no -- tied to NER ontology |
| `VALID_RELATIONSHIP_TYPES` | kg_write_assembler.py:55 | 18-member frozenset | frozenset | KG relationship types accepted for edge staging. Includes KNOWS, LOCATED_AT, PARENT_OF, CO_MENTIONED, etc. | no -- tied to edge enrichment ontology |
| `PRIORITY_COMPLETION` | outbox_assembler.py:52 | `10` | int | Highest priority for cycle completion events | maybe |
| `PRIORITY_GAP` | outbox_assembler.py:53 | `30` | int | Priority for gap detection events | maybe |
| `PRIORITY_INSIGHT` | outbox_assembler.py:54 | `40` | int | Priority for insight generation events | maybe |
| `PRIORITY_DECISION` | outbox_assembler.py:55 | `50` | int | Default priority for per-event decision events | maybe |
| `VALID_ENTITY_LABELS` | truth_write_assembler.py:105 | `{"PERSON","PER","KINSHIP","ORG","LOC","PET"}` | set | Semantic name generation from NER entities (M10.8). Used in `_generate_pattern_name()` | no -- tied to NER model output |

### 1.4 Migration Inventory

R6 does not own any database migrations. R6 is a pure staging phase that assembles writes for R7. All table schemas are owned by R7 layer writers.

| # | Migration File | Table(s) | Operation | Columns Affected | Reversible? |
| - | -------------- | -------- | --------- | ---------------- | ----------- |
| - | N/A | N/A | N/A | N/A | N/A |

**Justification**: R6 reads event states and phase outputs from the in-memory envelope and produces `P03StagedWrites` / `R6Output`. It never executes SQL directly. All database writes are deferred to R7's `TransactionCoordinator`.

---

## 2. API Surface Map

### 2.1 Public Functions & Methods

| # | Module | Function / Method | Signature | Return Type | Consumers | Idempotent? | Notes |
| - | ------ | ----------------- | --------- | ----------- | --------- | ----------- | ----- |
| 1 | k0.pipelines.p03.phases.r6_staging | R6Staging.run | `(envelope: P03BatchEnvelope, ctx: P03RunnerContext) -> P03PhaseResult` | P03PhaseResult | P03 pipeline runner | yes (idempotency keys) | Async method. Top entry point for R6 phase. |
| 2 | k0.modules.consolidation.staging.r6_coordinator | R6Coordinator.execute | `(event_states: Dict, phase_outputs, gaps, batch_event_ids, dedup_results, phase_durations, cycle_start_ms) -> R6CoordinatorResult` | R6CoordinatorResult | R6Staging.run | yes | Synchronous orchestration of 10 sub-components |
| 3 | k0.modules.consolidation.staging.r6_coordinator | R6Coordinator.create | `(cls, cycle_ulid, tenant_id, space_id, actor_id, existing_entity_ids, config) -> R6Coordinator` | R6Coordinator | R6Staging._create_coordinator | N/A (factory) | Class method factory that wires all sub-components |
| 4 | k0.modules.consolidation.staging.r6_coordinator | create_r6_coordinator | `(cycle_ulid, tenant_id, space_id, actor_id, existing_entity_ids, dry_run) -> R6Coordinator` | R6Coordinator | External consumers, tests | N/A (factory) | Module-level convenience factory |
| 5 | k0.modules.consolidation.staging.status_marker | ConsolidationStatusMarker.mark_batch | `(event_states: Dict[str, P03EventState]) -> Dict[str, StatusResult]` | Dict[str, StatusResult] | R6Coordinator | yes | Determines status for all events in batch |
| 6 | k0.modules.consolidation.staging.dedup_metadata | DedupMetadataPopulator.from_event_state | `(event_state: P03EventState, dedup_merges: List[DedupMerge]) -> DedupMetadata` | DedupMetadata | R6Coordinator | yes | Builds dedup metadata from event state |
| 7 | k0.modules.consolidation.staging.reconciliation_recorder | ReconciliationRecorder.record_batch | `(event_states: Dict, timestamp_ms: int) -> Dict[str, ReconciliationRecord]` | Dict | R6Coordinator | yes | Records reconciliation decisions for audit |
| 8 | k0.modules.consolidation.staging.idempotency | IdempotencyKeyGenerator.for_event_update | `(event_id: str) -> str` | str | R6Coordinator, TruthWriteAssembler | yes | Pattern: `p03:staging:{cycle_ulid}:{event_id}` |
| 9 | k0.modules.consolidation.staging.idempotency | IdempotencyKeyGenerator.for_truth_write | `(table: str, record_id: str) -> str` | str | TruthWriteAssembler, KGWriteAssembler | yes | Pattern: `p03:write:{cycle_ulid}:{table}:{record_id}` |
| 10 | k0.modules.consolidation.staging.truth_write_assembler | TruthWriteAssembler.assemble_all | `(clusters, event_states, routines, social_relationships, intentions, gaps, insights, counterfactuals, routine_optimizations, intent_signals, routine_candidates, mcts_scenarios) -> Dict[str, List[StagedWrite]]` | Dict | R6Coordinator | yes | Master assembly for 7 truth tables + 2 special tables |
| 11 | k0.modules.consolidation.staging.kg_write_assembler | KGWriteAssembler.assemble_all | `(entities, entity_updates, edges, edge_updates, causal_edges) -> Tuple[List, List]` | Tuple | R6Coordinator | yes | Assembles KG entity and edge writes with FK validation |
| 12 | k0.modules.consolidation.staging.outbox_assembler | OutboxEventAssembler.assemble_all | `(summary, event_states, gaps, phase_durations, insights) -> AssembledOutbox` | AssembledOutbox | R6Coordinator | yes | Assembles 4 outbox event categories with priorities |
| 13 | k0.modules.consolidation.staging.manifest_validator | ManifestValidator.validate | `(r6_output: R6Output, batch_event_ids: Set[str]) -> ManifestValidationResult` | ManifestValidationResult | R6Coordinator | yes | 7-rule validation of R6Output before R7 |
| 14 | k0.modules.consolidation.staging.summary_generator | SummaryGenerator.compute | `(event_states, layer_write_counts, kg_entity_count, kg_edge_count, ...) -> GeneratorResult` | GeneratorResult | R6Coordinator | yes | Computes ReconciliationSummary statistics |
| 15 | k0.modules.consolidation.staging.intent_signal_assembler | IntentSignalAssembler.assemble_all | `(signals: List[IntentSignal]) -> Dict[str, List[StagedWrite]]` | Dict | R6Coordinator | yes | Routes 6 signal types to layer writes |
| 16 | k0.modules.consolidation.staging.truth_query_service | TruthQueryService.find_candidates | `(embedding, space_id, tenant_id, top_k, min_similarity, layers) -> List[TruthCandidate]` | List[TruthCandidate] | Reconciliation phase (pre-R6) | yes | Async pgvector similarity search |
| 17 | k0.modules.consolidation.staging.truth_query_service | TruthQueryService.query_entities_for_decay | `(space_id, tenant_id, max_decay_factor, limit_per_layer, layers) -> List[DecayCandidate]` | List[DecayCandidate] | R3 decay phase (pre-R6) | yes | Async decay candidate query |
| 18 | k0.pipelines.p03.staged_writes | P03StagedWrites.add_write | `(write: StagedWrite) -> bool` | bool | R6Output.get_all_writes_ordered path | yes | Routes write to layer bucket |
| 19 | k0.pipelines.p03.staged_writes | P03StagedWrites.get_all_writes_ordered | `() -> List[StagedWrite]` | List[StagedWrite] | R7 truth writer | yes | Returns writes in FK dependency order |

### 2.2 Syscalls Used / Required

| # | Syscall | Signature | Status | Used By | SQL Pattern (if DB) | Notes |
| - | ------- | --------- | ------ | ------- | ------------------- | ----- |
| 1 | N/A (direct SQL) | TruthQueryService uses raw SQL via connection factory | exists | truth_query_service.py | SELECT with pgvector `<=>` operator for cosine similarity | Not a formal syscall -- uses raw connection pool |

R6 does not use any formal kernel syscalls. TruthQueryService is the only R6 component that touches the database, and it does so via a raw connection factory rather than through the syscalls layer. All other R6 components operate purely on in-memory data from the envelope.

**Gap**: TruthQueryService should use formal syscalls for consistency with the rest of K0. Current raw SQL bypasses syscall-level observability, capability enforcement, and audit logging.

### 2.3 Internal Helpers (non-public but critical path)

| # | Module | Function | Signature | Called By | Purpose | Risk if Changed |
| - | ------ | -------- | --------- | --------- | ------- | --------------- |
| 1 | staging.r6_coordinator | _build_event_updates | `(event_states, status_results, dedup_metas, recon_records, idempotency_gen, cycle_ulid) -> List[StagedEventUpdate]` | R6Coordinator.execute | Combines status, dedup, reconciliation into per-event updates | Breaks R7 hipp_events writes if event update format changes |
| 2 | staging.truth_write_assembler | _generate_pattern_name | `(state: P03EventState, max_length=200) -> str` | assemble_sem_writes | M10.8 semantic name from NER entities. Parses NER JSON, extracts PERSON/LOC/ORG labels | Breaks semantic pattern descriptions if NER format changes |
| 3 | staging.truth_write_assembler | _build_epi_record_data | `(cluster: EpisodeCluster, event_states: Dict) -> Dict` | assemble_epi_writes | Builds full st_epi record schema from cluster + event state enrichments | Breaks episodic write format -- 30+ fields |
| 4 | staging.kg_write_assembler | _merge_edge_writes | `(a: StagedWrite, b: StagedWrite) -> StagedWrite` | assemble_edge_writes | Deduplicates same edge_id writes within batch (INSERT+INSERT, INSERT+UPDATE, UPDATE+UPDATE) | Breaks edge dedup causing duplicate key violations in R7 |
| 5 | staging.r6_staging | _extract_inputs | `(envelope: P03BatchEnvelope) -> R6Inputs` | R6Staging.run | Extracts all R1-R5 outputs from envelope into R6Inputs container | Breaks R6 input if envelope phase output fields change |
| 6 | staging.r6_staging | _populate_envelope | `(envelope, result: R6CoordinatorResult) -> None` | R6Staging.run | Writes R6Output and staged writes back to envelope for R7 consumption | Breaks R7 if envelope population logic changes |
| 7 | staging.r6_output | StagedWritesContainer.to_r6_output | `(cycle_ulid, batch_id, r6_idempotency_key, summary) -> R6Output` | R6Coordinator | Finalizes mutable container into frozen R6Output. Can only be called once. | Breaks R6 output if called twice (raises RuntimeError) |
| 8 | staging.outbox_assembler | _build_decision_payload | Per-action payload builders | assemble_decision_events | Builds outbox event payloads for REINFORCE, CREATE, EVOLVE, PRUNE, PATTERN actions | Breaks R8 event payloads if enrichment fields change |
| 9 | staging.idempotency | compute_batch_hash | `(event_ids: Set[str]) -> str` (static) | for_batch_phase | SHA-256 of sorted event IDs, truncated to 12 hex chars | Collision risk if hash length reduced |

### 2.4 Classes & Dataclasses

| # | Module | Class | Base Class | Key Attributes | Key Methods | Consumers |
| - | ------ | ----- | ---------- | -------------- | ----------- | --------- |
| 1 | staging.r6_output | R6Output | dataclass(frozen=True) | staged_event_updates: List, staged_truth_writes: List, staged_kg_writes: List, staged_outbox_events: List, reconciliation_summary, cycle_ulid, batch_id, r6_idempotency_key | event_count, total_writes, get_all_writes_ordered(), to_json(), to_summary_dict() | R7 truth writer, R6Staging, tests |
| 2 | staging.r6_output | StagedEventUpdate | dataclass | event_id, consolidation_status, consolidation_reason, idempotency_key, near_duplicates_json, novelty_score, episode_cluster_id, reconciliation_json, novelty_bonuses_json, expected_version, consolidation_cycle_id, consolidated_at_ms, is_duplicate, duplicate_of | to_record_data(), to_staged_write(phase), to_json(), from_json(cls) | R6Coordinator, R7 EpisodicLayerWriter |
| 3 | staging.r6_output | ReconciliationSummary | dataclass(frozen=True) | total_events, consolidated_count, duplicate_count, pruned_count, pending_review_count, action_breakdown, layer_write_counts, kg_entity_count, kg_edge_count, gap_count, insight_count, counterfactual_count, routine_optimization_count, total_writes, cycle_duration_ms | to_dict(), to_json() | SummaryGenerator, R6Coordinator, outbox events |
| 4 | staging.r6_output | StagedWritesContainer | class (mutable) | _event_updates: List, _truth_writes: Dict, _kg_writes: Dict, _outbox_events: List, _finalized: bool | add_event_update(), add_truth_write(), add_kg_write(), add_outbox_event(), to_r6_output() | R6Coordinator (internal builder) |
| 5 | staging.r6_coordinator | R6CoordinatorConfig | dataclass | dry_run: bool, validate_manifest: bool, emit_metrics: bool | N/A | R6Staging, tests |
| 6 | staging.r6_coordinator | R6CoordinatorResult | dataclass | success: bool, r6_output: Optional[R6Output], validation_result: Optional, error: Optional[str], phase_duration_ms: int, step_durations_ms: Dict | N/A | R6Staging |
| 7 | staging.r6_coordinator | R6Coordinator | class | All 10 sub-component instances, config, cycle/tenant/space context | create(cls), execute() | R6Staging |
| 8 | staging.status_marker | StatusResult | dataclass | event_id, status, reason, source_decision, contributing_factors | N/A | R6Coordinator, StagedEventUpdate builder |
| 9 | staging.status_marker | ConsolidationStatusMarker | class | LOW_CONFIDENCE_THRESHOLD=0.5, CONSOLIDATED_ACTIONS frozenset | mark_status(event_state), mark_batch(event_states), get_status_counts(results) | R6Coordinator |
| 10 | staging.dedup_metadata | DedupMetadata | dataclass | event_id, near_duplicates_json, novelty_score, episode_cluster_id, novelty_bonuses_json, is_duplicate, duplicate_of | N/A (validates in **post_init**) | R6Coordinator, StagedEventUpdate builder |
| 11 | staging.dedup_metadata | NearDuplicateEntry | dataclass | event_id, hamming_distance, embedding_similarity, detection_stage | to_dict() | DedupMetadataPopulator |
| 12 | staging.dedup_metadata | DedupMetadataPopulator | class | DEFAULT_NOVELTY_SCORE=1.0 | from_duplication_result(), from_event_state(), build_near_duplicates_json() | R6Coordinator |
| 13 | staging.reconciliation_recorder | ReconciliationRecord | dataclass | event_id, reconciliation_action, best_match_id, best_match_layer, similarity_score, confidence, reconciliation_reason, decision_timestamp_ms | to_dict(), to_json() | R6Coordinator, audit trail |
| 14 | staging.reconciliation_recorder | ReconciliationRecorder | class | MATCH_REQUIRED_ACTIONS, NO_MATCH_ACTIONS frozensets | record(), record_batch(), to_json(), validate_record() | R6Coordinator |
| 15 | staging.idempotency | IdempotencyKeyGenerator | class | cycle_ulid (26-char ULID) | for_event_update(), for_truth_write(), for_event_emit(), for_batch_phase(), for_outbox_event(), compute_batch_hash() | All assemblers |
| 16 | staging.idempotency | ParsedKey | dataclass | pipeline, key_type, cycle_ulid, entity_id, extra | N/A | parse_idempotency_key() consumers |
| 17 | staging.truth_write_assembler | TruthWriteAssembler | class | idempotency_gen, source_phase, tenant_id, space_id, consolidation_cycle_id | assemble_all() + 15 per-layer assemble methods | R6Coordinator |
| 18 | staging.truth_write_assembler | AssembledWrite | dataclass | write: StagedWrite, layer, record_id, source | N/A | flatten_writes() |
| 19 | staging.kg_write_assembler | KGWriteAssembler | class | idempotency_gen, source_phase, tenant_id, space_id, consolidation_cycle_id, existing_entity_ids | assemble_all(), assemble_entity_writes(), assemble_edge_writes(), validate_foreign_keys() | R6Coordinator |
| 20 | staging.kg_write_assembler | ValidationResult | dataclass | is_valid, errors, orphan_edges | N/A | KGWriteAssembler.validate_foreign_keys |
| 21 | staging.outbox_assembler | OutboxEventAssembler | class | cycle_ulid, tenant_id, space_id, consolidation_cycle_id | assemble_all(), assemble_completion_event(), assemble_decision_events(), assemble_gap_events(), assemble_insight_events() | R6Coordinator |
| 22 | staging.outbox_assembler | AssembledOutbox | dataclass | events, completion_event, decision_events, gap_events, insight_events, event_count_by_topic | N/A | R6Coordinator |
| 23 | staging.manifest_validator | ManifestValidator | class | KEY_PREFIX="p03:", VERSION_CONFLICT_THRESHOLD=0.10 | validate() (7 rules) | R6Coordinator |
| 24 | staging.manifest_validator | ManifestValidationResult | dataclass | is_valid, errors, warnings, stats, dlq_reason | add_error(), add_warning(), set_dlq() | R6Coordinator |
| 25 | staging.summary_generator | SummaryGenerator | class | ACTION_TO_STATUS dict | compute(), compute_from_actions(), merge(), compute_with_writes() | R6Coordinator |
| 26 | staging.summary_generator | GeneratorResult | dataclass | summary: ReconciliationSummary, warnings: List, pending_count: int | N/A | R6Coordinator |
| 27 | staging.intent_signal_assembler | IntentSignalAssembler | class | tenant_id, space_id, actor_id, SOURCE_PHASE="R6" | assemble_all() | R6Coordinator |
| 28 | staging.truth_query_service | TruthQueryService | class | conn_factory, pool, embedding_dim=768 | find_candidates() (async), query_entities_for_decay() (async), get_metrics() | Reconciliation phase (pre-R6) |
| 29 | staging.truth_query_service | TruthCandidate | dataclass | record_id, layer, embedding: ndarray, similarity, confidence, last_accessed_ms | N/A | TruthQueryService consumers |
| 30 | staging.truth_query_service | DecayCandidate | dataclass | entity_id, table_name, last_observed_at, decay_factor, confidence_score, observation_count, entity_type, attributes | to_dict() | R3 decay phase |
| 31 | p03.staged_writes | StagedWrite | dataclass | write_id, layer, operation, record_id, record_data, idempotency_key, source_phase, source_event_ids, expected_version, created_at_ms, observation_context | insert(cls), update(cls), archive(cls), tombstone(cls) | All assemblers, R7 truth writer |
| 32 | p03.staged_writes | StagedOutboxEvent | dataclass | event_id, topic, payload, source_phase, idempotency_key, priority, created_at_ms | create(cls) | OutboxEventAssembler, R8 emitter |
| 33 | p03.staged_writes | P03StagedWrites | dataclass | 11 per-layer write lists + outbox_events | add_write(), total_writes(), get_all_writes_ordered(), get_writes_by_layer(), get_writes_by_phase(), to_summary_dict(), clear() | R6Staging, R7 truth writer |
| 34 | p03.staged_writes | WriteOperation | Enum | INSERT, UPDATE, ARCHIVE, TOMBSTONE | N/A | StagedWrite |
| 35 | p03.r6_staging | R6Inputs | dataclass | event_states, r2_clusters, r3_dedup_merges, r3_decay_updates, r4_new_entities, r4_updated_entities, r4_new_edges, r4_updated_edges, r4_causal_edges, r4_gap_candidates, cycle_id, tenant_id, space_id, cycle_start_ms | event_count, batch_event_ids | R6Staging internal |

---

## 3. Algorithm Inventory

### 3.1 Current Algorithms

R6 is primarily a data-transformation and validation phase rather than an algorithmic phase. However, several components implement non-trivial logic:

| # | Algorithm Name | Location | Category | Input Type(s) | Input Constraints | Output Type(s) | Output Guarantees | Time | Space | Det? | Stateful? | State Location | Parameters | Edge Cases | Failure Mode | Fallback | Dependencies | Description |
| - | -------------- | -------- | -------- | ------------- | ----------------- | -------------- | ----------------- | ---- | ----- | ---- | --------- | -------------- | ---------- | ----------- | ------------ | -------- | ------------ | ----------- |
| 1 | status_determination | status_marker.py | classification | P03EventState | Must have reconciliation_action set | StatusResult | status is one of 4 valid values, reason is non-empty | O(1) per event | O(1) | yes | no | N/A | LOW_CONFIDENCE_THRESHOLD=0.5, CONSOLIDATED_ACTIONS frozenset | skip action, no reconciliation_action set, low confidence match | returns StatusResult (never raises) | status="CONSOLIDATED" if no special conditions | event_state.reconciliation_action, event_state.reconciliation_confidence | Classifies event into CONSOLIDATED/DUPLICATE/PRUNED/PENDING_REVIEW based on R1-R5 reconciliation outcomes |
| 2 | idempotency_key_generation | idempotency.py | transformation | cycle_ulid + entity identifiers | cycle_ulid must be 26-char ULID, entity IDs non-empty | str (key) | key matches regex pattern, length <= 200 | O(1) per key, O(n log n) for batch hash | O(1) | yes | no | N/A | KEY_PATTERNS (4 regexes), MAX_KEY_LENGTH=200, BATCH_HASH_LENGTH=12 | empty event_id, empty table, negative offset | raises ValueError | N/A -- required | hashlib.sha256 | Generates deterministic, unique idempotency keys for all R6-R8 operations using structured patterns |
| 3 | truth_write_assembly | truth_write_assembler.py | transformation | R2-R5 phase outputs: clusters, event_states, routines, social_relationships, intentions, gaps, insights, counterfactuals, routine_optimizations, intent_signals, routine_candidates, mcts_scenarios | Each input list may be empty; event_states must have reconciliation_action | Dict[str, List[StagedWrite]] | writes grouped by layer name, each write has valid idempotency_key and record_data | O(E + C + R + S + I + G + M) where E=events, C=clusters, etc. | O(same) | yes | no | N/A | 12 input parameters, per-layer record schema templates | empty inputs (returns empty), missing NER data, invalid JSON in enrichments | graceful skip per-write (try/except), returns partial results | empty dict for missing layers | IdempotencyKeyGenerator, subtype_classifier | Transforms R2-R5 phase outputs into per-layer StagedWrite objects with full record schemas for 9 truth tables |
| 4 | kg_write_assembly | kg_write_assembler.py | transformation | KGEntity, KGEntityUpdate, KGEdge, KGEdgeUpdate, CausalEdge lists | entities/edges from R4 enrichment | Tuple[entity_writes, edge_writes] | valid entity_type in VALID_ENTITY_TYPES, valid relationship_type in VALID_RELATIONSHIP_TYPES | O(E + Ed) where E=entities, Ed=edges | O(E + Ed) | yes | no | N/A | VALID_ENTITY_TYPES, VALID_RELATIONSHIP_TYPES, existing_entity_ids for FK validation | empty entity_id/edge_id (returns None), duplicate edge_id in batch | returns None for invalid, dedup via _merge_edge_writes | None for invalid writes | IdempotencyKeyGenerator | Assembles KG entity and edge writes with FK validation and intra-batch edge deduplication |
| 5 | edge_merge_dedup | kg_write_assembler.py (private) | merging | Two StagedWrite with same edge_id | Both writes target st_kg_edges layer | StagedWrite (merged) | INSERT+INSERT -> INSERT with merged data, INSERT+UPDATE -> INSERT, UPDATE+UPDATE -> UPDATE with merged data | O(1) | O(1) | yes | no | N/A | N/A | same operation types, different operation types | returns latest write | keeps first write on unexpected combination | N/A | Deduplicates KG edge writes within a batch where multiple enrichers produce writes for the same edge_id |
| 6 | manifest_validation | manifest_validator.py | validation | R6Output, batch_event_ids | R6Output must have valid cycle_ulid/batch_id | ManifestValidationResult | is_valid=True means all 7 rules pass; DLQ reason set if critical failure | O(W + E) where W=writes, E=events | O(W) for dedup tracking | yes | no | N/A | VERSION_CONFLICT_THRESHOLD=0.10, KEY_PREFIX="p03:" | zero writes, zero outbox events, empty batch_event_ids | collects errors/warnings (never raises) | adds warnings, validation continues | N/A | Validates 7 manifest rules: layer validity, key format, FK integrity, event coverage, outbox minimum, duplicate records, version conflict threshold |
| 7 | outbox_event_assembly | outbox_assembler.py | transformation | ReconciliationSummary, event_states, gaps, phase_durations, insights | summary from SummaryGenerator, event_states with reconciliation_action | AssembledOutbox | deduped by gap_id/insight_id, priority-ordered, idempotency keys per event | O(E + G + I) where E=events, G=gaps, I=insights | O(E + G + I) | yes | no | N/A | 8 TOPIC_*constants, 4 PRIORITY_* constants | empty event_states (returns completion event only), zero gaps/insights | dedup skips duplicates | completion event always emitted | IdempotencyKeyGenerator | Assembles 4 categories of outbox events (completion, decision, gap, insight) with priority ordering for R8 emission |
| 8 | intent_signal_routing | intent_signal_assembler.py | routing | List[IntentSignal] (6 subtypes) | signals from R5 IntentSignalDetector | Dict[str, List[StagedWrite]] | routing matrix: Reminder/Decision->st_prospective, Lesson/Emotional->st_sem, Milestone/QueryBoost->st_kg_dom+st_kg_edges | O(S) where S=signals | O(S) | yes | no | N/A | SOURCE_PHASE="R6" | empty signals list, unknown signal type | unknown types skipped (no error) | empty dict | IntentSignal subclasses, ULID generator | Routes 6 intent signal types from R5 to appropriate truth table layer writes with deduplication and merge logic |
| 9 | reconciliation_recording | reconciliation_recorder.py | transformation | P03EventState with reconciliation fields | Must have reconciliation_action | ReconciliationRecord | valid action, scores clamped to [0,1], timestamp_ms set | O(1) per event | O(1) | yes | no | N/A | MATCH_REQUIRED_ACTIONS, NO_MATCH_ACTIONS frozensets | missing best_match_id for REINFORCE/EXTEND/EVOLVE (adds validation warning) | returns record (never raises) | fills missing fields with defaults | event_state.reconciliation_action | Records complete reconciliation decision history per event with match details for audit trail |
| 10 | summary_generation | summary_generator.py | aggregation | Dict[str, P03EventState] + write counts | event_states with reconciliation_action | GeneratorResult (contains ReconciliationSummary) | counts sum to total_events, warnings for PENDING events | O(E) where E=events | O(1) | yes | no | N/A | ACTION_TO_STATUS mapping (8 actions -> 4 statuses) | all events PENDING (all counted as pending_review), zero events | adds warnings, never raises | empty summary with zeros | event_state.reconciliation_action | Computes ReconciliationSummary with per-action/status counts, layer write counts, and cycle statistics |
| 11 | vector_similarity_search | truth_query_service.py | search | embedding: ndarray, space_id, tenant_id, top_k | embedding must be 768-dim float vector | List[TruthCandidate] | sorted by similarity descending, similarity clamped to [0,1] | O(log N) per layer (HNSW) | O(top_k * layers) | no (HNSW approximate) | no | N/A | embedding_dim=768, top_k default, min_similarity default | wrong embedding dimension (raises ValueError), DB connection failure | silent except (returns empty list) | empty list | pgvector, numpy, struct | Queries truth layers using pgvector HNSW for approximate nearest neighbor search |
| 12 | dedup_metadata_population | dedup_metadata.py | transformation | P03EventState, DuplicationResult or DedupMerge list | event_state with is_duplicate flag and near_duplicate_ids | DedupMetadata | novelty_score clamped to [0,1], near_duplicates_json is valid JSON | O(D) where D=near_duplicate count | O(D) | yes | no | N/A | DEFAULT_NOVELTY_SCORE=1.0 | no duplication result (uses defaults), empty near_duplicate_ids | returns default metadata | DedupMetadata(novelty_score=1.0, near_duplicates_json="[]") | DuplicationResult from R3 | Populates deduplication metadata from DuplicateDetector results for st_hipp_events audit fields |

### 3.2 Algorithm Gaps

| # | Gap Description | Expected Behavior | Current Behavior | Severity | Proposed Approach | Estimated Complexity |
| - | --------------- | ----------------- | ---------------- | -------- | ----------------- | -------------------- |
| 1 | No adaptive version conflict threshold | VERSION_CONFLICT_THRESHOLD should adjust based on batch size and historical conflict rate | Hardcoded at 10% for all batches regardless of size | P2 | Track historical conflict rate per tenant/space, use adaptive threshold with min/max bounds | small |
| 2 | No FK integrity check for R5 intent signal writes | Intent signals routed to st_kg_dom/st_kg_edges should verify entity_id exists | IntentSignalAssembler writes entity references without FK validation | P1 | Add entity_id validation against existing_entity_ids set (same as KGWriteAssembler) | trivial |
| 3 | No write dependency ordering for Stage 5 UPDATE outputs | R5 Stage 5 algorithms produce UPDATE writes (salience, confidence, weight changes). R6 must order these after INSERT writes within same layer | Only INSERT writes are currently assembled by TruthWriteAssembler | P0 | Extend TruthWriteAssembler to handle UPDATE writes from Stage 5 algorithms. Order: INSERT before UPDATE within each layer | medium |
| 4 | TruthQueryService silently swallows DB errors | find_candidates() catches all exceptions and returns empty list. No visibility into failed queries | Silent `except Exception: pass` in _query_layer() | P1 | Add structured logging for query failures, increment error counter metric | trivial |
| 5 | No st_anchors layer support in staged writes | Stage 5 ASU algorithm outputs AnchorUpdate writes targeting st_anchors table | No LAYER_ST_ANCHORS constant, no P03StagedWrites bucket for anchors, no assembler method | P0 (blocks Stage 5) | Add LAYER_ST_ANCHORS to constants, add st_anchors_writes to P03StagedWrites, add assemble_anchor_writes to TruthWriteAssembler | small |
| 6 | No observation context population for R5 algorithm outputs | R5 insights, counterfactuals, routine optimizations need ObservationContext for R7 observation recording | ObservationContext only populated for R2 cluster-derived writes, not R5 outputs | P1 | Wire ObservationContext through R5 algorithm outputs to TruthWriteAssembler | small |
| 7 | MCTS write assembly is dead code | TruthWriteAssembler.assemble_mcts_writes() assembles writes for st_mcts_decisions table that is being deleted in M5C | MCTS writes still assembled and staged | P2 | Delete assemble_mcts_writes() and st_mcts_writes bucket in M5C cleanup | trivial |
| 8 | Duplicate ReconciliationSummary classes | Two ReconciliationSummary dataclasses exist: one in phase_outputs.py (simple action counts) and one in r6_output.py (comprehensive). Consumers must use the correct one | Both exist, r6_output.py version is authoritative but phase_outputs.py version still used by some paths | P2 | Consolidate to single ReconciliationSummary in r6_output.py, deprecate phase_outputs.py version | small |

---

## 4. Data Flow Analysis

### 4.1 Phase-Level Data Flow

```
P03BatchEnvelope
  |
  v
R6Staging.run(envelope, ctx)
  |
  +-- _create_coordinator(envelope, ctx) --> R6Coordinator
  +-- _extract_event_states(envelope)    --> Dict[str, P03EventState]
  +-- _extract_phase_outputs(envelope)   --> P03PhaseOutputs
  +-- _extract_gaps(envelope)            --> List[GapCandidate]
  +-- _extract_batch_event_ids(envelope) --> Set[str]
  +-- _extract_dedup_results(envelope)   --> Dict[str, DuplicationResult]
  +-- _extract_phase_durations(envelope) --> Dict[str, int]
  |
  v
R6Coordinator.execute(event_states, phase_outputs, gaps, batch_event_ids, ...)
  |
  +-- STEP 1: _build_event_updates()
  |   +-- StatusMarker.mark_status(state)      --> StatusResult
  |   +-- DedupPopulator.from_duplication_result() --> DedupMetadata
  |   => List[StagedEventUpdate]
  |
  +-- STEP 2: TruthWriteAssembler.assemble_all(clusters, states, routines, ...)
  |   +-- assemble_epi_writes(clusters, event_states)
  |   +-- assemble_sem_writes(event_states)
  |   +-- assemble_procedural_writes(routines)
  |   +-- assemble_social_writes(social_relationships)
  |   +-- assemble_prospective_writes(intentions)
  |   +-- assemble_learning_queue_writes(event_states, gaps)
  |   +-- assemble_insight_writes(insights)
  |   +-- assemble_counterfactual_writes(counterfactuals)
  |   +-- assemble_routine_optimization_writes(routine_optimizations)
  |   +-- assemble_mcts_writes(mcts_scenarios)
  |   => Dict[str, List[StagedWrite]]
  |   => _flatten_truth_writes() --> List[StagedWrite] (deduplicated)
  |
  +-- STEP 2.5: IntentSignalAssembler.assemble_all(r5_intent_signals)
  |   +-- Routes: Reminder/Decision -> st_prospective
  |   +-- Routes: Lesson/Emotional -> st_sem
  |   +-- Routes: Milestone/QueryBoost -> st_kg_dom + st_kg_edges
  |   => truth_writes += intent_truth_writes
  |   => intent_kg_writes (appended in STEP 3)
  |
  +-- STEP 3: KGWriteAssembler.assemble_all(entities, updates, edges, ...)
  |   +-- assemble_entity_writes(new_entities, updated_entities)
  |   +-- assemble_edge_writes(new_edges, updated_edges, causal_edges)
  |   +-- validate_foreign_keys(entity_writes, edge_writes)
  |   +-- _merge_edge_writes() (intra-batch dedup)
  |   => kg_writes = entity_writes + edge_writes + intent_kg_writes
  |
  +-- STEP 4: SummaryGenerator.compute_with_writes(states, writes, ...)
  |   => GeneratorResult (contains ReconciliationSummary)
  |
  +-- STEP 5: OutboxEventAssembler.assemble_all(summary, states, gaps, ...)
  |   +-- assemble_completion_event(summary, phase_durations)
  |   +-- assemble_decision_events(event_states)
  |   +-- assemble_gap_events(gaps)
  |   +-- assemble_insight_events(insights)
  |   => AssembledOutbox
  |
  +-- STEP 6: Build R6Output (frozen dataclass)
  |   => R6Output(event_updates, truth_writes, kg_writes, outbox_events, summary)
  |
  +-- STEP 7: ManifestValidator.validate(r6_output, batch_event_ids)
  |   => ManifestValidationResult (7 rules)
  |
  v
R6CoordinatorResult(success, r6_output, validation_result, step_durations_ms)
  |
  v
R6Staging._populate_envelope(envelope, result)
  +-- truth_writes --> envelope.staged.add_write(write)    [by layer]
  +-- kg_writes    --> envelope.staged.add_write(write)    [by layer]
  +-- outbox       --> envelope.staged.outbox_events       [direct append]
  +-- event_updates --> envelope.staged.st_hipp_events_updates [converted to StagedWrite]
  +-- summary      --> envelope.phases.r6_summary
  |
  v
P03PhaseResult.done(phase_id=R6_STAGE, duration_ms, outputs_summary, idempotency_key)
```

### 4.2 Input Sources (What R6 Reads)

| # | Source | Data Type | Origin Phase | Access Path | Required? | Notes |
| - | ------ | --------- | ------------ | ----------- | --------- | ----- |
| 1 | Event states | Dict[str, P03EventState] | R0-R5 | envelope.events | yes | Core input: all per-event enrichments from all prior phases |
| 2 | Episode clusters | List[EpisodeCluster] | R2 | envelope.phases.r2_clusters | no | Empty if no episodic clustering performed |
| 3 | Dedup merges | List[DedupMerge] | R3 | envelope.phases.r3_dedup_merges | no | Used for dedup metadata population |
| 4 | Decay updates | List[DecayUpdate] | R3 | envelope.phases.r3_decay_updates | no | Not directly consumed by R6 |
| 5 | Dedup results | Dict[str, DuplicationResult] | R3 | envelope.phases.r3_dedup_results | no | Per-event dedup metadata; optional with fallback |
| 6 | New entities | List[KGEntity] | R4 | envelope.phases.r4_new_entities | no | KG entities for staging |
| 7 | Updated entities | List[KGEntityUpdate] | R4 | envelope.phases.r4_updated_entities | no | KG entity updates for staging |
| 8 | New edges | List[KGEdge] | R4 | envelope.phases.r4_new_edges | no | KG edges for staging |
| 9 | Updated edges | List[KGEdgeUpdate] | R4 | envelope.phases.r4_updated_edges | no | KG edge updates for staging |
| 10 | Causal edges | List[CausalEdge] | R4 | envelope.phases.r4_causal_edges | no | Causal edges for staging |
| 11 | Gap candidates | List[GapCandidate] | R4/R5 | envelope.phases.r5.gaps (fallback: r4_gap_candidates) | no | Gaps for outbox events + learning queue |
| 12 | R5 insights | List[Insight] | R5 | envelope.phases.r5_insights | no | Issue 8.1.12: Insight events for outbox + truth writes |
| 13 | R5 counterfactuals | List | R5 | envelope.phases.r5_counterfactuals | no | Issue 8.1.17 |
| 14 | R5 routine optimizations | List | R5 | envelope.phases.r5_routine_optimizations | no | Issue 8.1.17 |
| 15 | R5 routine candidates | List | R5 | envelope.phases.r5_routine_candidates | no | GAP-003: RoutineDetector output |
| 16 | R5 intent signals | List[IntentSignal] | R5 | envelope.phases.r5_intent_signals | no | GAP-001: 6 signal types |
| 17 | R5 MCTS scenarios | List | R5 | envelope.phases.r5_mcts_scenarios | no | DreamExplorer MCTS decisions |
| 18 | R5 routines | List | R5 | envelope.phases.r5_routines | no | Procedural/routine truth writes |
| 19 | R5 intentions | List | R5 | envelope.phases.r5_intentions | no | Prospective truth writes |
| 20 | Social entities | List | R4 | envelope.phases.r4_social_entities | no | Social relationship truth writes |
| 21 | Phase durations | Dict[str, int] | R0-R5 | Extracted from phase results | no | For completion outbox event |
| 22 | Cycle context | cycle_id, tenant_id, space_id, triggered_at | R0 | envelope.context | yes | Cycle identity for idempotency |

### 4.3 Output Destinations (What R6 Writes)

| # | Output | Data Type | Destination | Access Path | Consumer | Notes |
| - | ------ | --------- | ----------- | ----------- | -------- | ----- |
| 1 | Truth writes | List[StagedWrite] | envelope.staged (by layer) | envelope.staged.add_write(write) | R7 truth writer | Routed to per-layer buckets in P03StagedWrites |
| 2 | KG writes | List[StagedWrite] | envelope.staged (by layer) | envelope.staged.add_write(write) | R7 truth writer | st_kg_dom + st_kg_edges |
| 3 | Event updates | List[StagedWrite] | envelope.staged.st_hipp_events_updates | converted via to_staged_write("R6") | R7 hipp events writer | UPDATE operations on st_hipp_events |
| 4 | Outbox events | List[StagedOutboxEvent] | envelope.staged.outbox_events | direct append | R8 outbox emitter | 4 event categories with priority ordering |
| 5 | Summary | ReconciliationSummary | envelope.phases.r6_summary | direct assignment | R7/R8, metrics | Cycle-level statistics |
| 6 | Phase result | P03PhaseResult | pipeline runner | return value | P03 runner | Contains duration, outputs_summary, idempotency_key |

### 4.4 Data Transformation Map

| Input Data | Transformation | Output | Target Layer | Write Operation |
| ---------- | -------------- | ------ | ------------ | --------------- |
| EpisodeCluster + event_states | _build_epi_record_data() | StagedWrite | st_epi | INSERT (new clusters), UPDATE (existing) |
| P03EventState.enrichments | _generate_pattern_name() + semantic schema | StagedWrite | st_sem | INSERT (new patterns) |
| R5 routines | procedural schema assembly | StagedWrite | st_procedural | INSERT |
| R4 social entities | social relationship schema | StagedWrite | st_social | INSERT |
| R5 intentions | prospective schema assembly | StagedWrite | st_prospective | INSERT |
| R5 intent signals (Reminder/Decision) | IntentSignalAssembler routing | StagedWrite | st_prospective | INSERT |
| R5 intent signals (Lesson/Emotional) | IntentSignalAssembler routing | StagedWrite | st_sem | INSERT |
| R5 intent signals (Milestone/QueryBoost) | IntentSignalAssembler routing | StagedWrite | st_kg_dom + st_kg_edges | INSERT |
| event_states + gaps | learning queue schema | StagedWrite | st_learning_queue | INSERT |
| R5 insights | insight schema assembly | StagedWrite | st_sem | INSERT |
| R5 counterfactuals | counterfactual schema | StagedWrite | st_sem | INSERT |
| R5 routine_optimizations | optimization schema | StagedWrite | st_procedural | INSERT/UPDATE |
| R5 MCTS scenarios | MCTS decision schema | StagedWrite | st_mcts_decisions | INSERT |
| R4 new entities | entity schema | StagedWrite | st_kg_dom | INSERT |
| R4 updated entities | entity update schema | StagedWrite | st_kg_dom | UPDATE |
| R4 new edges + causal edges | edge schema | StagedWrite | st_kg_edges | INSERT |
| R4 updated edges | edge update schema | StagedWrite | st_kg_edges | UPDATE |
| event_states + status + dedup | StagedEventUpdate.to_staged_write() | StagedWrite | st_hipp_events | UPDATE |
| summary + states + gaps + insights | outbox payload builders | StagedOutboxEvent | outbox | EMIT (4 topics) |

---

## 5. Storage & Schema Analysis

### 5.1 Tables Touched by R6 (via Staged Writes for R7)

R6 does not directly touch any database tables. It stages writes that R7 will execute. Below is the complete list of tables that R6 assembles writes for:

| # | Table | Layer Constant | Write Operations | Assembler | FK Dependencies | Notes |
| - | ----- | -------------- | ---------------- | --------- | --------------- | ----- |
| 1 | st_epi | LAYER_ST_EPI | INSERT, UPDATE | TruthWriteAssembler.assemble_epi_writes | None (root table for episodic) | Episode cluster records; 30+ fields per record |
| 2 | st_sem | LAYER_ST_SEM | INSERT | TruthWriteAssembler.assemble_sem_writes, assemble_insight_writes, assemble_counterfactual_writes, IntentSignalAssembler (Lesson/Emotional) | None | Semantic patterns, insights, counterfactuals, emotion signals, lesson signals |
| 3 | st_procedural | LAYER_ST_PROCEDURAL | INSERT, UPDATE | TruthWriteAssembler.assemble_procedural_writes, assemble_routine_optimization_writes | None | Routines, procedures, optimizations |
| 4 | st_social | LAYER_ST_SOCIAL | INSERT | TruthWriteAssembler.assemble_social_writes | None | Social relationship records |
| 5 | st_prospective | LAYER_ST_PROSPECTIVE | INSERT | TruthWriteAssembler.assemble_prospective_writes, IntentSignalAssembler (Reminder/Decision) | None | Intentions, reminders, decisions |
| 6 | st_kg_dom | LAYER_ST_KG_DOM | INSERT, UPDATE | KGWriteAssembler.assemble_entity_writes, IntentSignalAssembler (Milestone/QueryBoost) | None (provides PKs for st_kg_edges) | KG entities; VALID_ENTITY_TYPES={PERSON, LOCATION, ORG, THING, CONCEPT} |
| 7 | st_kg_edges | LAYER_ST_KG_EDGES | INSERT, UPDATE | KGWriteAssembler.assemble_edge_writes, IntentSignalAssembler (QueryBoost) | FK: source_id/target_id -> st_kg_dom.entity_id | KG relationships; VALID_RELATIONSHIP_TYPES (18 types); FK validated by KGWriteAssembler |
| 8 | st_hipp_events | LAYER_ST_HIPP_EVENTS | UPDATE | StagedEventUpdate.to_staged_write() | FK: event_id exists | Per-event consolidation status, dedup metadata, reconciliation record |
| 9 | st_learning_queue | LAYER_ST_LEARNING_QUEUE | INSERT | TruthWriteAssembler.assemble_learning_queue_writes | None | Gap-driven learning items |
| 10 | st_mcts_decisions | LAYER_ST_MCTS | INSERT | TruthWriteAssembler.assemble_mcts_writes | None | MCTS dream exploration decisions (dead code -- table being removed in M5C) |
| 11 | st_vec | LAYER_ST_VEC | (not assembled by R6) | N/A | FK: record_id references truth tables | Vector embeddings; R6 does not stage vec writes -- these are handled by R7 layer writers directly |

### 5.2 FK Dependency Order

R7 must execute writes in this order to satisfy foreign key constraints. This order is defined in `P03StagedWrites.DEPENDENCY_ORDER`:

```
st_vec              (1)  -- no FKs, write vectors first
  |
st_kg_dom           (2)  -- entities referenced by edges
  |
st_kg_edges         (3)  -- FK: source_id/target_id -> st_kg_dom
  |
st_epi              (4)  -- episodic records
  |
st_sem              (5)  -- semantic patterns
  |
st_procedural       (6)  -- routines/procedures
  |
st_social           (7)  -- social relationships
  |
st_prospective      (8)  -- intentions/reminders
  |
st_mcts_decisions   (9)  -- MCTS decisions (dead)
  |
st_learning_queue  (10)  -- learning items (may reference events)
  |
st_hipp_events     (11)  -- event status updates (last: depends on all above)
```

### 5.3 Write Volume Estimates

| Table | Writes per Event (avg) | Writes per Batch (10 events) | Operation Split | Notes |
| ----- | ---------------------: | ---------------------------: | --------------- | ----- |
| st_hipp_events | 1 | 10 | 100% UPDATE | 1:1 with events |
| st_epi | 0.3 | 3 | 80% INSERT, 20% UPDATE | Depends on clustering ratio |
| st_sem | 1.5 | 15 | 95% INSERT, 5% UPDATE | Patterns + insights + counterfactuals + signals |
| st_procedural | 0.1 | 1 | 70% INSERT, 30% UPDATE | Only for routine-related events |
| st_social | 0.2 | 2 | 100% INSERT | Social relationships from NER |
| st_prospective | 0.1 | 1 | 100% INSERT | Intentions + reminder/decision signals |
| st_kg_dom | 0.5 | 5 | 60% INSERT, 40% UPDATE | Entity creation + updates |
| st_kg_edges | 1.0 | 10 | 70% INSERT, 30% UPDATE | Edge creation + merge dedup |
| st_learning_queue | 0.2 | 2 | 100% INSERT | Gap-driven items only |
| outbox | 3+ | 30+ | 100% INSERT | 1 completion + N decisions + gaps + insights |
| **TOTAL** | ~7 | ~79 | | |

---

## 6. Event Bus Integration

### 6.1 Events Consumed by R6

R6 does not consume events from the event bus. All inputs are passed in-memory via the P03BatchEnvelope.

### 6.2 Events Produced by R6 (Staged for R8)

R6 stages outbox events for R8 emission. These are NOT emitted by R6 itself -- they are staged as `StagedOutboxEvent` objects and emitted by R8 after R7 commits.

| # | Topic | Version | Priority | Payload Schema | Trigger Condition | Consumer(s) | Notes |
| - | ----- | ------- | -------: | -------------- | ----------------- | ----------- | ----- |
| 1 | p03.consolidation.complete.v1 | v1 | 10 | {cycle_ulid, batch_id, summary: ReconciliationSummary, phase_durations, tenant_id, space_id} | Always emitted (1 per batch) | P06, monitoring, dashboards | Highest priority; signals cycle completion |
| 2 | p03.truth.created.v1 | v1 | 50 | {event_id, action: "CREATE", record_id, layer, tenant_id, space_id} | Per-event with action=CREATE | P06 (new pattern learning), downstream agents | One per CREATE action |
| 3 | p03.truth.reinforced.v1 | v1 | 50 | {event_id, action: "REINFORCE", record_id, layer, similarity_score, tenant_id, space_id} | Per-event with action=REINFORCE | Monitoring, analytics | Most common decision event |
| 4 | p03.truth.evolved.v1 | v1 | 50 | {event_id, action: "EVOLVE"/"EXTEND", record_id, layer, delta, tenant_id, space_id} | Per-event with action=EVOLVE or EXTEND | P06, downstream agents | Pattern evolution tracking |
| 5 | p03.memory.pruned.v1 | v1 | 50 | {event_id, action: "PRUNE"/"ARCHIVE", record_id, layer, reason, tenant_id, space_id} | Per-event with action=PRUNE or ARCHIVE | Monitoring, audit | Decay/archive decisions |
| 6 | p03.pattern.detected.v1 | v1 | 50 | {event_id, action: "PATTERN", pattern_type, pattern_name, tenant_id, space_id} | Per-event with action=PATTERN | P06, downstream agents | New semantic pattern discovery |
| 7 | p03.gap.detected.v1 | v1 | 30 | {gap_id, gap_type, description, confidence, source_event_ids, tenant_id, space_id} | Per gap candidate from R4/R5 | P06 gap filling | Higher priority than decisions; deduped by gap_id |
| 8 | p03.insight.generated.v1 | v1 | 40 | {insight_id, insight_type, summary, confidence, source_event_ids, tenant_id, space_id} | Per R5 insight | Downstream agents, dashboards | Issue 8.1.12; deduped by insight_id |

### 6.3 Event Topology

```
R6 OutboxEventAssembler
  |
  +--[PRIORITY 10]--> p03.consolidation.complete.v1 ----> P06, monitoring
  +--[PRIORITY 30]--> p03.gap.detected.v1          ----> P06 gap filling
  +--[PRIORITY 40]--> p03.insight.generated.v1      ----> agents, dashboards
  +--[PRIORITY 50]--> p03.truth.created.v1          ----> P06 learning
  +--[PRIORITY 50]--> p03.truth.reinforced.v1       ----> monitoring
  +--[PRIORITY 50]--> p03.truth.evolved.v1          ----> P06 evolution
  +--[PRIORITY 50]--> p03.memory.pruned.v1          ----> audit
  +--[PRIORITY 50]--> p03.pattern.detected.v1       ----> P06 pattern learning
```

### 6.4 Event Issues

| Issue | Severity | Detail |
| ----- | -------- | ------ |
| No outbox event for SKIP actions | LOW | Events with action=SKIP produce no outbox event. May want monitoring visibility for skip rate. |
| No outbox event for PENDING_REVIEW status | MEDIUM | Events classified as PENDING_REVIEW get no outbox event. HITL pipeline (K1 supervision) has no notification channel for these. |
| Decision events have lowest priority | LOW | All per-event decision events share PRIORITY_DECISION=50. No differentiation between CREATE (high importance) and REINFORCE (routine). |
| No outbox event for intent signal staging | MEDIUM | GAP-001 intent signals routed to truth writes produce no outbox notification. Downstream consumers cannot track intent processing. |

---

## 7. Observability Audit

### 7.1 Logging

| # | Component | Log Points | Level | Structured Fields | Gaps |
| - | --------- | ---------- | ----- | ----------------- | ---- |
| 1 | R6Staging (phase) | 3: start, complete, fail | INFO/EXCEPTION | cycle_id, event_count, duration_ms, event_updates, truth_writes, kg_writes, outbox_events, error | Good coverage. Logs both count and timing. |
| 2 | R6Coordinator | 2: validation_failed, exception | ERROR/EXCEPTION | dlq_reason, errors, warnings, stats, error, step_durations, traceback | Only failure paths. No logging for successful step completion. |
| 3 | StatusMarker | 0 | N/A | N/A | No logging at all. Silent status classification. |
| 4 | DedupPopulator | 0 | N/A | N/A | No logging. Dedup metadata population is invisible. |
| 5 | ReconciliationRecorder | 0 | N/A | N/A | No logging. Reconciliation recording is invisible. |
| 6 | IdempotencyKeyGen | 0 | N/A | N/A | No logging. Key generation is invisible. |
| 7 | TruthWriteAssembler | 0 | N/A | N/A | No logging. Largest component (2,034 lines) with zero observability. Per-layer write counts invisible. |
| 8 | KGWriteAssembler | 0 | N/A | N/A | No logging. FK validation results invisible. Edge merge dedup invisible. |
| 9 | OutboxEventAssembler | 0 | N/A | N/A | No logging. Outbox event counts invisible. |
| 10 | ManifestValidator | 0 (uses coordinator logger) | N/A | N/A | Validation rules have no per-rule logging. Only aggregate failure logged by coordinator. |
| 11 | SummaryGenerator | 0 | N/A | N/A | No logging. Summary computation invisible. |
| 12 | IntentSignalAssembler | 0 | N/A | N/A | No logging. Signal routing invisible. |
| 13 | TruthQueryService | 0 (silent except) | N/A | N/A | Silently catches all exceptions. Query performance invisible. |

**Logging Score**: 2 of 13 components have any logging. Only the phase file (r6_staging.py) has structured logging with useful fields. All 10 sub-components within the coordinator are completely silent. This is a critical observability gap.

### 7.2 Metrics

R6 currently emits no formal metrics. Step durations are tracked internally in `R6CoordinatorResult.step_durations_ms` but not emitted to any metrics system.

| # | Metric Name | Type | Labels | Source | Status | Gap |
| - | ----------- | ---- | ------ | ------ | ------ | --- |
| 1 | r6_phase_duration_ms | gauge | cycle_id | R6Staging.run | MISSING | Only in log extra fields, not emitted as metric |
| 2 | r6_step_duration_ms | gauge | step_name | R6Coordinator | MISSING | Tracked in step_durations_ms dict but not emitted |
| 3 | r6_truth_write_count | counter | layer | R6Coordinator | MISSING | Available from R6Output.staged_truth_writes but not counted per-layer |
| 4 | r6_kg_write_count | counter | entity/edge | R6Coordinator | MISSING | Available from R6Output.staged_kg_writes but not split |
| 5 | r6_outbox_event_count | counter | topic | OutboxEventAssembler | MISSING | Available from AssembledOutbox.event_count_by_topic |
| 6 | r6_validation_failure | counter | dlq_reason | ManifestValidator | MISSING | Only logged on failure |
| 7 | r6_version_conflict_rate | gauge | N/A | ManifestValidator | MISSING | Calculated but not exposed |
| 8 | r6_event_status_distribution | histogram | status | ConsolidationStatusMarker | MISSING | Status counts available but not metrified |

**Metrics Score**: 0 of 8 critical metrics implemented. R6 has zero metrics emission despite having `emit_metrics` config flag. The flag exists in R6CoordinatorConfig but is never checked in code.

### 7.3 Tracing

R6 has no distributed tracing integration. No span creation, no trace context propagation, no parent/child span relationships.

| Component | Span Name | Status | Notes |
| --------- | --------- | ------ | ----- |
| R6Staging.run | r6_staging | MISSING | Should be root span for R6 phase |
| R6Coordinator.execute | r6_coordinator | MISSING | Should be child of r6_staging |
| Each sub-step | r6_step_{name} | MISSING | 7 sub-steps should have individual spans |
| ManifestValidator | r6_manifest_validation | MISSING | Should capture validation duration and result |
| TruthQueryService | r6_truth_query | MISSING | Async DB queries should have trace spans |

### 7.4 Health Checks

R6 has no health check endpoints or readiness probes. As a pure transformation phase within the pipeline, it does not run as a standalone service. However:

- No circuit breaker for TruthQueryService DB queries
- No timeout enforcement on R6Coordinator.execute()
- No memory usage monitoring during large batch assembly

### 7.5 Observability Enhancement Priorities

| Priority | Enhancement | Impact | Effort |
| -------- | ----------- | ------ | ------ |
| P0 | Add structured logging to TruthWriteAssembler (per-layer counts) | High: largest component is invisible | trivial |
| P0 | Add structured logging to KGWriteAssembler (entity/edge counts, FK violations) | High: FK validation failures invisible | trivial |
| P1 | Emit step_durations_ms as metrics | High: performance regression detection | small |
| P1 | Add per-rule logging to ManifestValidator | Medium: validation debugging | trivial |
| P1 | Fix TruthQueryService silent exception swallowing | High: query failures completely invisible | trivial |
| P2 | Add distributed tracing spans | Medium: cross-phase correlation | medium |
| P2 | Implement emit_metrics config flag | Medium: metrics pipeline integration | small |
| P3 | Add memory usage tracking for large batch assembly | Low: memory pressure detection | small |

---

## 8. Test Coverage Analysis

### 8.1 Test Inventory

| # | Test File | Lines | Tests | Type | Covers | Key Test Scenarios |
| - | --------- | ----: | ----: | ---- | ------ | ------------------ |
| 1 | test_r6_coordinator.py | 662 | 32 | unit | R6Coordinator.execute(), create(), _build_event_updates(),_flatten_truth_writes() | Full cycle execution, step ordering, dry_run mode, validation toggle, error propagation, empty batch |
| 2 | test_r6_output.py | 845 | 35 | unit | R6Output, StagedEventUpdate, ReconciliationSummary, StagedWritesContainer | Frozen dataclass immutability, to_json/from_json round-trip, StagedWritesContainer finalization guard, event_count/total_writes properties |
| 3 | test_status_marker.py | 360 | 16 | unit | ConsolidationStatusMarker.mark_status(), mark_batch() | CONSOLIDATED/DUPLICATE/PRUNED/PENDING_REVIEW classification, low confidence threshold, SKIP action handling, batch processing |
| 4 | test_dedup_metadata.py | 672 | 38 | unit | DedupMetadataPopulator, DedupMetadata, NearDuplicateEntry | from_duplication_result(), from_event_state(), novelty_score clamping, near_duplicates_json format, default values |
| 5 | test_reconciliation_recorder.py | 506 | 25 | unit | ReconciliationRecorder.record(), record_batch() | REINFORCE/EXTEND/CREATE/EVOLVE/CONTRADICT/PRUNE/SKIP actions, match validation, JSON serialization, timestamp |
| 6 | test_idempotency.py | 542 | 51 | unit | IdempotencyKeyGenerator (4 methods), parse_idempotency_key() | Key format validation (4 patterns), length bounds, determinism, batch hash uniqueness, ULID validation, negative offsets |
| 7 | test_truth_write_assembler.py | 583 | 36 | unit | TruthWriteAssembler.assemble_all() and per-layer methods | Per-layer write assembly (epi, sem, procedural, social, prospective, learning_queue), empty inputs, record_data schema validation |
| 8 | test_truth_write_assembler_r5.py | 483 | 26 | unit | TruthWriteAssembler R5 methods: insights, counterfactuals, routine_optimizations, mcts | Issue 8.1.17: R5 output write assembly, schema validation for insights/counterfactuals/optimizations/mcts |
| 9 | test_kg_write_assembler.py | 575 | 31 | unit | KGWriteAssembler.assemble_all(), FK validation, edge merge dedup | Entity/edge writes, VALID_ENTITY_TYPES/RELATIONSHIP_TYPES validation, FK integrity,_merge_edge_writes(), causal edges |
| 10 | test_outbox_assembler.py | 755 | 50 | unit | OutboxEventAssembler.assemble_all() (4 categories) | Completion event, decision events (per action type), gap events, insight events (8.1.12), priority ordering, dedup by ID, empty inputs |
| 11 | test_manifest_validator.py | 616 | 26 | unit | ManifestValidator.validate() (7 rules) | Layer validity, key format, FK integrity, event coverage, outbox minimum, duplicate records, version conflict threshold, DLQ routing |
| 12 | test_summary_generator.py | 571 | 34 | unit | SummaryGenerator.compute(), compute_with_writes(), merge() | Action-to-status mapping, layer write counts, cycle duration, pending warnings, merge semantics |
| 13 | test_intent_signal_assembler.py | 652 | 30 | unit | IntentSignalAssembler.assemble_all() (6 signal types) | Reminder/Decision->st_prospective, Lesson/Emotional->st_sem, Milestone/QueryBoost->st_kg_dom+st_kg_edges, unknown types |
| 14 | test_r6_integration.py | 632 | 19 | integration | Full R6 cycle with realistic R1-R5 outputs | Mixed event types, duplicate handling, gap staging for P06, validation pass/fail, idempotency determinism, output immutability |
| 15 | test_r6_r5_integration.py | 424 | 19 | integration | R6 with R5 outputs (insights, counterfactuals, optimizations, intent signals) | R5 output staging, intent signal routing, MCTS write assembly, combined R4+R5 workflow |
| 16 | conftest.py | 7 | 0 | fixture | Shared test fixtures | N/A |
| | **TOTAL** | **9,884** | **468** | | | |

### 8.2 Coverage Assessment

| Component | Unit Tests | Integration Tests | Total Tests | Estimated Coverage | Gaps |
| --------- | ---------: | ----------------: | ----------: | -----------------: | ---- |
| R6Coordinator | 32 | 38 (integration + R5) | 70 | ~85% | Missing: step timeout enforcement, concurrent execution, memory pressure |
| R6Output | 35 | 0 | 35 | ~95% | Good coverage. Minor: edge cases in large tuple handling |
| StatusMarker | 16 | 0 | 16 | ~90% | Missing: boundary testing at exactly LOW_CONFIDENCE_THRESHOLD=0.5 |
| DedupMetadata | 38 | 0 | 38 | ~95% | Thorough coverage including edge cases |
| ReconciliationRecorder | 25 | 0 | 25 | ~90% | Missing: large batch performance, concurrent recording |
| IdempotencyKeyGen | 51 | 0 | 51 | ~98% | Best-tested component. Excellent coverage of all key patterns and edge cases |
| TruthWriteAssembler | 62 (36+26) | 19 | 81 | ~80% | Missing: _generate_pattern_name() NER edge cases, very large cluster assembly, cross-layer dedup |
| KGWriteAssembler | 31 | 19 | 50 | ~85% | Missing: large entity set FK validation performance, edge merge with 3+ writes for same edge_id |
| OutboxAssembler | 50 | 19 | 69 | ~90% | Missing: payload size limits, topic name changes |
| ManifestValidator | 26 | 19 | 45 | ~85% | Missing: combination of multiple simultaneous rule violations, adaptive threshold |
| SummaryGenerator | 34 | 0 | 34 | ~90% | Good coverage. Missing: merge() with incompatible summaries |
| IntentSignalAssembler | 30 | 19 | 49 | ~85% | Missing: FK validation for kg_dom writes, high-volume signal batches |
| TruthQueryService | 0 | 0 | 0 | ~0% | NO TESTS. 663 lines of async DB query code with zero test coverage. Critical gap. |

### 8.3 Test Gaps

| # | Gap | Severity | Affected Component | Proposed Test(s) | Est. Effort |
| - | --- | -------- | ------------------ | ---------------- | ----------- |
| 1 | TruthQueryService has zero tests | CRITICAL | truth_query_service.py (663 lines) | Unit tests with mocked DB connection, integration test with real pgvector | large |
| 2 | No performance/load tests | HIGH | R6Coordinator | Batch size scaling tests (10, 100, 1000 events), memory profiling | medium |
| 3 | No end-to-end R6Staging phase test | HIGH | r6_staging.py | Test with real P03BatchEnvelope, verify envelope population | medium |
| 4 | No cross-phase integration test (R5->R6->R7) | HIGH | r6_staging.py + r7 | Verify R6 output is consumable by R7 truth writer | large |
| 5 | No concurrent execution test | MEDIUM | R6Coordinator | Test R6 with multiple concurrent batches | medium |
| 6 | No error recovery test | MEDIUM | R6Coordinator | Test partial failure (e.g., truth assembly fails, KG assembly succeeds) | small |
| 7 | MCTS write assembly tests may be dead | LOW | test_truth_write_assembler_r5.py | Verify MCTS tests can be deleted with M5C cleanup | trivial |

---

## 9. Dependency Map

### 9.1 Internal Dependencies (within K0)

| # | Dependency | Module Path | Usage | Coupling | Notes |
| - | ---------- | ----------- | ----- | -------- | ----- |
| 1 | P03EventState | k0.pipelines.p03.event_state | Core data model for per-event state | TIGHT | R6 reads 15+ fields from P03EventState |
| 2 | P03PhaseOutputs | k0.pipelines.p03.phase_outputs | Container for R1-R5 outputs (clusters, entities, edges, etc.) | TIGHT | R6 accesses via getattr() with fallbacks |
| 3 | P03BatchEnvelope | k0.pipelines.p03.envelope | Pipeline envelope carrying all phase data | TIGHT | R6 reads from and writes to envelope |
| 4 | P03StagedWrites | k0.pipelines.p03.staged_writes | Staged write container for R7 | TIGHT | R6 populates envelope.staged with all writes |
| 5 | StagedWrite | k0.pipelines.p03.staged_writes | Write operation dataclass | TIGHT | Created by all assemblers |
| 6 | StagedOutboxEvent | k0.pipelines.p03.staged_writes | Outbox event dataclass | TIGHT | Created by OutboxEventAssembler |
| 7 | P03PhaseResult | k0.pipelines.p03.phase_interface | Phase execution result | MEDIUM | Return type of R6Staging.run() |
| 8 | P03RunnerContext | k0.pipelines.p03.phase_interface | Runner context with syscalls | LOW | Passed but barely used (only for entity IDs) |
| 9 | P03Error | k0.pipelines.p03.observability | Error dataclass | LOW | Used in failure paths only |
| 10 | ReconciliationAction | k0.pipelines.p03.event_state | Enum for reconciliation actions (CREATE, REINFORCE, etc.) | MEDIUM | Used by StatusMarker and OutboxAssembler |
| 11 | EpisodeCluster | k0.pipelines.p03.phase_outputs | R2 cluster output | MEDIUM | Used by TruthWriteAssembler |
| 12 | GapCandidate | k0.pipelines.p03.phase_outputs | R4/R5 gap output | LOW | Used by OutboxAssembler and TruthWriteAssembler |
| 13 | Insight | k0.pipelines.p03.phase_outputs | R5 insight output | LOW | Used by OutboxAssembler and TruthWriteAssembler |
| 14 | KGEntity/KGEdge/CausalEdge | k0.pipelines.p03.phase_outputs | R4 KG outputs | MEDIUM | Used by KGWriteAssembler |
| 15 | DedupMerge/DuplicationResult | k0.modules.consolidation.staging.dedup_metadata | R3 dedup outputs | MEDIUM | Used by DedupMetadataPopulator |

### 9.2 External Dependencies

| # | Package | Version | Usage | Replaceable? | Notes |
| - | ------- | ------- | ----- | ------------ | ----- |
| 1 | Python stdlib (hashlib) | 3.12+ | SHA-256 for idempotency keys and batch IDs | no | Core stdlib |
| 2 | Python stdlib (time) | 3.12+ | Timestamp generation (_now_ms) | no | Core stdlib |
| 3 | Python stdlib (dataclasses) | 3.12+ | All data structures | no | Core stdlib |
| 4 | numpy | 1.x/2.x | TruthQueryService embedding operations | yes (if pgvector handles vectors natively) | Only used in truth_query_service.py |
| 5 | struct | stdlib | TruthQueryService binary embedding packing | no | For pgvector binary format |
| 6 | pgvector (via psycopg/asyncpg) | implicit | TruthQueryService vector similarity queries | no (ADR-K003 mandates pgvector) | Not directly imported; used via SQL operators |
| 7 | ulid (implicit) | N/A | ULID generation for intent signal writes | yes | Only in IntentSignalAssembler |

### 9.3 Dependency Graph

```text
R6Staging (phase file)
  |
  +-- R6Coordinator (orchestrator)
  |     |
  |     +-- ConsolidationStatusMarker   [stateless, no deps]
  |     +-- DedupMetadataPopulator      [stateless, no deps]
  |     +-- ReconciliationRecorder      [stateless, no deps]
  |     +-- IdempotencyKeyGenerator     [stateless, deps: hashlib]
  |     +-- TruthWriteAssembler         [stateless, deps: IdempotencyKeyGenerator]
  |     +-- KGWriteAssembler            [stateless, deps: IdempotencyKeyGenerator]
  |     +-- OutboxEventAssembler        [stateless, deps: IdempotencyKeyGenerator]
  |     +-- ManifestValidator           [stateless, no deps]
  |     +-- SummaryGenerator            [stateless, no deps]
  |     +-- IntentSignalAssembler       [stateless, deps: IdempotencyKeyGenerator (implicit)]
  |
  +-- P03BatchEnvelope (data carrier)
  |     +-- P03EventState (per-event)
  |     +-- P03PhaseOutputs (per-phase)
  |     +-- P03StagedWrites (write container)
  |
  +-- TruthQueryService (standalone, async, DB-dependent)
        +-- psycopg/asyncpg connection pool
        +-- numpy (embedding ops)
```

### 9.4 Circular Dependencies

None detected. R6 has a clean unidirectional dependency graph. All sub-components depend on shared data models (P03EventState, StagedWrite) but not on each other. The only inter-component dependency is that assemblers use IdempotencyKeyGenerator, which is injected via constructor.

---

## 10. Performance Baseline

### 10.1 Current Performance Characteristics

| Component | Time Complexity | Space Complexity | Estimated Latency (10 events) | Estimated Latency (100 events) | Bottleneck |
| --------- | --------------- | ---------------- | ----------------------------: | -----------------------------: | ---------- |
| StatusMarker.mark_batch | O(E) | O(E) | <1ms | <5ms | None |
| DedupPopulator | O(E * D) | O(E * D) | <1ms | <10ms | D = near-duplicate count |
| ReconciliationRecorder | O(E) | O(E) | <1ms | <5ms | None |
| IdempotencyKeyGenerator | O(E log E) for batch | O(E) | <1ms | <5ms | SHA-256 batch hash sorting |
| TruthWriteAssembler | O(E + C + R + S + I) | O(same) | <5ms | <50ms | Largest: _build_epi_record_data (30+ fields per record) |
| KGWriteAssembler | O(Ent + Ed) | O(Ent + Ed) | <2ms | <20ms | Edge merge dedup (hash map lookup) |
| OutboxEventAssembler | O(E + G + I) | O(E + G + I) | <2ms | <20ms | Payload serialization |
| ManifestValidator | O(W + E) | O(W) | <2ms | <20ms | Dedup tracking (hash set) |
| SummaryGenerator | O(E) | O(1) | <1ms | <5ms | None |
| IntentSignalAssembler | O(S) | O(S) | <1ms | <5ms | None (small signal count) |
| TruthQueryService | O(L * log N) per query | O(top_k * L) | 5-50ms (async) | 50-500ms | DB roundtrip; HNSW index scan; PER-EVENT QUERY |
| R6Coordinator total | O(E * (C + D + W)) | O(E * W) | ~15ms | ~150ms | TruthWriteAssembler + _flatten_truth_writes dedup |

Where: E=events, C=clusters, D=near-duplicates, R=routines, S=signals, Ent=entities, Ed=edges, G=gaps, I=insights, W=total writes, L=layers, N=records per layer.

### 10.2 Known Performance Issues

| # | Issue | Component | Impact | Proposed Fix | Effort |
| - | ----- | --------- | ------ | ------------ | ------ |
| 1 | TruthQueryService issues per-event queries | truth_query_service.py | O(E * L) DB roundtrips per batch. At 100 events x 5 layers = 500 queries | Batch queries: single query per layer with IN clause for multiple embeddings | medium |
| 2 | _flatten_truth_writes scans full write set | r6_coordinator.py | O(W) scan with hash map for dedup. At 100 events with ~7 writes each = 700 entries | Acceptable for current scale but should use sorted merge for 10K+ writes | small (future) |
| 3 | R6Coordinator eagerly creates all sub-components | r6_coordinator.py | All 10 sub-components instantiated even if batch is empty or dry_run | Lazy initialization: create sub-components on first use | small |
| 4 | No batch size limit enforcement | r6_staging.py | No upper bound on event count per batch. Very large batches (1000+) may cause memory pressure | Add configurable max_batch_size with overflow splitting | small |
| 5 | _build_epi_record_data builds 30+ field dicts per cluster | truth_write_assembler.py | Dict construction with string formatting for each field | Consider dataclass or named tuple for fixed schema | trivial |

### 10.3 Performance Budget (from Pipeline Contract)

| Metric | Budget | Source | Current Status |
| ------ | -----: | ------ | -------------- |
| R6 latency (10 events) | 30ms | consolidation.status_updater.v1.yaml latency_budget | LIKELY MET (estimated ~15ms without TruthQueryService) |
| R6 latency (100 events) | 300ms (extrapolated) | 10x linear scaling assumption | AT RISK if TruthQueryService involved |
| Memory per batch | <50MB | unspecified (estimated) | UNKNOWN -- no memory profiling |

---

## 11. Gap Analysis & Enhancement Proposals

### 11.1 Functional Gaps

| # | Gap ID | Title | Description | Current Behavior | Expected Behavior | Priority | Effort | Blocks |
| - | ------ | ----- | ----------- | ---------------- | ----------------- | -------- | ------ | ------ |
| G-R6-01 | GAP-ANCHORS | No st_anchors layer support | Stage 5 ASU algorithm outputs AnchorUpdate writes targeting st_anchors table. No staging infrastructure exists. | st_anchors writes silently dropped | st_anchors writes staged and committed by R7 | P0 | small | Stage 5 ASU |
| G-R6-02 | GAP-WRITE-ORDER | No UPDATE ordering within layers | R5 algorithms produce UPDATE writes that must follow INSERT writes within the same layer | Only INSERT writes assembled. UPDATEs from Stage 5 not handled. | INSERT before UPDATE ordering enforced per layer | P0 | medium | Stage 5 |
| G-R6-03 | GAP-INTENT-FK | No FK validation for intent signal writes | IntentSignalAssembler routes Milestone/QueryBoost to st_kg_dom without entity_id validation | Writes staged with potentially invalid entity references | entity_id validated against existing_entity_ids set | P1 | trivial | None |
| G-R6-04 | GAP-TQSERVICE | TruthQueryService zero test coverage | 663 lines of async DB query code with zero tests and silent exception handling | No visibility into query failures | Unit + integration tests, structured error logging | P1 | large | None |
| G-R6-05 | GAP-OBSERV | 11 of 13 components have zero logging | Sub-components are completely invisible during execution | Only R6Staging phase file logs | All components emit structured logs with per-step counts | P1 | small | None |
| G-R6-06 | GAP-METRICS | Zero metrics emitted despite emit_metrics flag | R6CoordinatorConfig.emit_metrics exists but is never checked | No R6 metrics in monitoring systems | Step durations, write counts, validation results emitted as metrics | P1 | small | None |
| G-R6-07 | GAP-ADAPTIVE | Hardcoded VERSION_CONFLICT_THRESHOLD | Fixed at 10% regardless of batch size or history | Small batches (1-2 events) overly sensitive; large batches may be too lenient | Adaptive threshold based on batch size and historical conflict rate | P2 | small | None |
| G-R6-08 | GAP-RECON-DUP | Duplicate ReconciliationSummary classes | Two competing dataclasses in phase_outputs.py and r6_output.py | Both exist; consumers must know which to import | Single canonical ReconciliationSummary in r6_output.py | P2 | small | None |
| G-R6-09 | GAP-MCTS-DEAD | MCTS write assembly is dead code | st_mcts_decisions table being removed in M5C | assemble_mcts_writes() still called and tested | Remove MCTS assembly + tests in M5C cleanup | P2 | trivial | M5C cleanup |
| G-R6-10 | GAP-CONTRACT | R6 contract severely underdescribes actual scope | Contract names R6 "status_updater" but code is a 12-component staging orchestrator | Contract describes ~10% of actual behavior | New R6 coordinator contract with full I/O schema and latency budget | P1 | medium | None |
| G-R6-11 | GAP-OBS-CTX | No ObservationContext for R5 outputs | R5 insights/counterfactuals/optimizations lack ObservationContext for R7 observation recording | ObservationContext only populated for R2-derived writes | Wire ObservationContext through R5 output paths | P1 | small | None |
| G-R6-12 | GAP-PENDING | No outbox event for PENDING_REVIEW events | HITL supervision pipeline has no notification for events needing human review | PENDING_REVIEW events silently staged without notification | New topic: p03.review.required.v1 with PRIORITY_REVIEW=20 | P2 | small | K1 HITL |

### 11.2 Enhancement Proposals Summary

| # | Enhancement | Category | Priority | Effort | Impact |
| - | ----------- | -------- | -------- | ------ | ------ |
| E-R6-01 | Add st_anchors layer to P03StagedWrites + TruthWriteAssembler | functional | P0 | small | Unblocks Stage 5 ASU |
| E-R6-02 | Implement UPDATE write ordering within layers | functional | P0 | medium | Unblocks Stage 5 algorithms |
| E-R6-03 | Add FK validation to IntentSignalAssembler | correctness | P1 | trivial | Prevents orphan KG references |
| E-R6-04 | Test suite for TruthQueryService | quality | P1 | large | 663 lines untested |
| E-R6-05 | Add structured logging to all 10 sub-components | observability | P1 | small | Visibility into 8,000+ lines of code |
| E-R6-06 | Implement metrics emission (step durations, write counts) | observability | P1 | small | Performance monitoring |
| E-R6-07 | Create R6Coordinator module contract YAML | governance | P1 | medium | Architecture alignment |
| E-R6-08 | Fix TruthQueryService silent exception handling | correctness | P1 | trivial | Query failure visibility |
| E-R6-09 | Add ObservationContext to R5 output staging | functional | P1 | small | R7 observation recording |
| E-R6-10 | Adaptive version conflict threshold | correctness | P2 | small | Better batch sensitivity |
| E-R6-11 | Consolidate ReconciliationSummary to single class | maintenance | P2 | small | Reduce confusion |
| E-R6-12 | Remove MCTS dead code in M5C | maintenance | P2 | trivial | Code cleanup |
| E-R6-13 | Add PENDING_REVIEW outbox notification | functional | P2 | small | HITL pipeline integration |
| E-R6-14 | Batch TruthQueryService queries | performance | P2 | medium | Reduce DB roundtrips |

---

## 12. Security & Privacy Review

### 12.1 Data Classification

| Data Type | Classification | Handled By | Storage Layer | Notes |
| --------- | -------------- | ---------- | ------------- | ----- |
| Event content (body text) | PII-HIGH | TruthWriteAssembler._build_epi_record_data | st_epi.content | Raw user input; may contain names, locations, personal details |
| NER entities (PERSON, LOC) | PII-HIGH | TruthWriteAssembler._generate_pattern_name, KGWriteAssembler | st_sem, st_kg_dom | Extracted named entities from user text |
| Social relationships | PII-HIGH | TruthWriteAssembler.assemble_social_writes | st_social | Family member names, relationship types |
| Emotional signals | PII-MEDIUM | IntentSignalAssembler (Emotional) | st_sem | Emotional state derived from user text |
| Idempotency keys | INTERNAL | IdempotencyKeyGenerator | All staged writes | Contains cycle_ulid + event_id (non-PII) |
| Embedding vectors | PII-LOW | TruthQueryService | st_vec | Numerical vectors; hard to reverse but theoretically reconstructible |
| Reconciliation audit | INTERNAL | ReconciliationRecorder | st_hipp_events | Decision history; no direct PII |
| Outbox event payloads | PII-MEDIUM | OutboxEventAssembler | outbox | Contains event_id, action, record_id; may include pattern names with PII |

### 12.2 Security Concerns

| # | Concern | Severity | Component | Current State | Mitigation |
| - | ------- | -------- | --------- | ------------- | ---------- |
| 1 | No input sanitization on record_data fields | MEDIUM | TruthWriteAssembler | Raw enrichment data passed directly to StagedWrite.record_data | Add input validation/sanitization before staging |
| 2 | TruthQueryService uses raw SQL | HIGH | truth_query_service.py | Raw SQL with string formatting for pgvector queries | Use parameterized queries (verify current implementation) |
| 3 | No tenant isolation enforcement in R6 | MEDIUM | R6Coordinator | tenant_id passed through but not validated against event ownership | Add tenant_id validation: all events in batch must belong to same tenant |
| 4 | Idempotency keys contain event_ids in plaintext | LOW | IdempotencyKeyGenerator | Keys like p03:staging:ULID:event_id expose event structure | Acceptable -- keys are internal, not exposed to users |
| 5 | No capability enforcement | MEDIUM | R6Staging | R6 phase accesses envelope directly without capability checks | Should go through syscall layer for consistent capability enforcement |

### 12.3 Privacy Compliance

| Requirement | Status | Notes |
| ----------- | ------ | ----- |
| Data minimization | PARTIAL | R6 stages all enrichment data; some fields may be unnecessary for downstream consumption |
| Right to deletion | NOT VERIFIED | No mechanism to filter out deleted-event writes during staging |
| Audit logging | PARTIAL | ReconciliationRecorder provides decision audit; no PII access audit |
| Encryption at rest | DELEGATED | R6 stages writes; encryption handled by R7/database layer |

---

## 13. Risk Register

| # | Risk ID | Title | Description | Likelihood | Impact | Severity | Mitigation | Owner |
| - | ------- | ----- | ----------- | ---------- | ------ | -------- | ---------- | ----- |
| 1 | RISK-R6-01 | TruthQueryService query cascade | Per-event queries to pgvector can cascade under high load, causing connection pool exhaustion | MEDIUM | HIGH | HIGH | Batch queries, connection pool limits, circuit breaker | P03 team |
| 2 | RISK-R6-02 | Large batch memory pressure | 1000+ events with 7+ writes each = 7000+ StagedWrite objects in memory simultaneously | LOW | HIGH | MEDIUM | Add batch size limit, streaming assembly, memory monitoring | P03 team |
| 3 | RISK-R6-03 | Manifest validation false positive DLQ | VERSION_CONFLICT_THRESHOLD at 10% is too aggressive for small batches (1 conflict in 5 events = 20%) | HIGH | MEDIUM | HIGH | Adaptive threshold with minimum batch size guard | P03 team |
| 4 | RISK-R6-04 | Silent data loss from TruthQueryService | Silent exception handling (except: pass) masks query failures, leading to missing reconciliation candidates | MEDIUM | HIGH | HIGH | Add error logging, error counters, alerts on failure rate | P03 team |
| 5 | RISK-R6-05 | Contract drift | Pipeline contract describes R6 as "status_updater" but code is full staging orchestrator. New features may be added without contract updates. | HIGH | MEDIUM | HIGH | Create comprehensive R6 contract, add contract-code sync check | P03 team |
| 6 | RISK-R6-06 | MCTS dead code breakage | st_mcts_decisions removal in M5C will break TruthWriteAssembler.assemble_mcts_writes() and related tests | HIGH | LOW | MEDIUM | Delete MCTS code paths before table removal | P03 team |
| 7 | RISK-R6-07 | FK violation in R7 from intent signals | IntentSignalAssembler writes to st_kg_dom without FK validation. R7 may fail with FK constraint violation. | MEDIUM | MEDIUM | MEDIUM | Add FK validation to IntentSignalAssembler | P03 team |
| 8 | RISK-R6-08 | Duplicate ReconciliationSummary confusion | Importing wrong ReconciliationSummary (phase_outputs.py vs r6_output.py) causes silent data loss in summary fields | MEDIUM | LOW | LOW | Consolidate to single class | P03 team |

---

## 14. Open Questions

| # | Question | Context | Impact | Proposed Resolution | Status |
| - | -------- | ------- | ------ | ------------------- | ------ |
| 1 | Should R6 enforce a maximum batch size? | No upper bound on events per batch. Large batches may cause memory pressure and latency spikes. | Performance, reliability | Add configurable max_batch_size (default 500) with overflow splitting to multiple R6 runs | OPEN |
| 2 | Should TruthQueryService be part of R6 or pre-R6? | TruthQueryService does async DB queries for reconciliation candidates, but R6 is meant to be a pure transformation phase with no DB access | Architecture clarity | Move TruthQueryService to R3 (reconciliation) and pass candidates via envelope. R6 should be pure staging. | OPEN |
| 3 | What happens when ManifestValidator DLQs a batch? | validator.validate() returns ManifestValidationResult with is_valid=False and dlq_reason. R6Coordinator returns failure. | Error recovery | Unclear what the pipeline runner does with a DLQ'd batch. Need to verify P03 runner handles R6 DLQ correctly. | OPEN |
| 4 | Should st_anchors use same staging pattern as other layers? | Stage 5 ASU outputs AnchorUpdate writes. No LAYER_ST_ANCHORS constant or P03StagedWrites bucket exists. | Stage 5 integration | Add LAYER_ST_ANCHORS to staged_writes.py following the same pattern as other layers. Need to confirm table schema. | OPEN |
| 5 | Is the 10% VERSION_CONFLICT_THRESHOLD appropriate? | Skeleton Part D flags this as hardcoded. For a batch of 5 events, a single conflict = 20% and triggers DLQ. | False positive DLQ rate | Adaptive threshold: max(10%, 2/batch_size) or min_conflicts_for_dlq=3 | OPEN |
| 6 | Should R6 emit outbox events for PENDING_REVIEW? | PENDING_REVIEW events currently produce no outbox notification. K1 HITL supervision has no trigger for human review. | HITL integration | New topic p03.review.required.v1 with priority 20 (between completion and gaps) | OPEN |
| 7 | Should intent signal FK validation use the same existing_entity_ids set as KGWriteAssembler? | IntentSignalAssembler has no access to existing_entity_ids. KGWriteAssembler validates FKs but intent signals bypass this. | Data integrity | Pass existing_entity_ids to IntentSignalAssembler constructor or validate intent KG writes through KGWriteAssembler | OPEN |
| 8 | When will MCTS code paths be removed? | st_mcts_decisions table deletion planned for M5C. Code and tests exist but will become dead. | Code maintenance | Schedule MCTS cleanup as first task of M5C | OPEN |

---

## 15. Glossary

| Term | Definition |
| ---- | ---------- |
| Staged Write | A `StagedWrite` dataclass representing a pending database mutation (INSERT, UPDATE, ARCHIVE, TOMBSTONE) that has not yet been committed. Created by R6, executed by R7. |
| P03StagedWrites | Container holding all staged writes grouped by truth table layer, with FK dependency ordering for atomic R7 commit. |
| R6Output | Frozen dataclass produced by R6Coordinator containing all staged event updates, truth writes, KG writes, outbox events, and reconciliation summary. |
| StagedEventUpdate | Per-event consolidation result containing status, dedup metadata, reconciliation record, and idempotency key for st_hipp_events UPDATE. |
| ReconciliationSummary | Aggregate statistics for a consolidation cycle: action/status counts, layer write counts, KG/gap/insight/counterfactual counts, cycle duration. |
| ManifestValidator | Component that validates the complete R6Output against 7 rules before allowing R7 commit. Can DLQ the entire batch. |
| DLQ (Dead Letter Queue) | Failed batches that cannot be processed are routed to a dead letter queue for manual investigation. |
| Idempotency Key | Deterministic string key ensuring the same logical operation produces the same key across retries. Format: `p03:{type}:{cycle_ulid}:{entity}`. |
| Truth Table | One of 11 database tables in the memory storage layer (st_epi, st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges, st_vec, st_hipp_events, st_learning_queue, st_mcts_decisions). |
| FK Dependency Order | The order in which truth table writes must be executed to satisfy foreign key constraints: vec -> kg_dom -> kg_edges -> epi -> sem -> ... -> hipp_events. |
| WriteOperation | Enum with 4 values: INSERT (new record), UPDATE (modify existing), ARCHIVE (soft delete), TOMBSTONE (hard delete marker). |
| Intent Signal | One of 6 signal types detected by R5 IntentSignalDetector: Reminder, Decision, Lesson, Emotional, Milestone, QueryBoost. Routed by IntentSignalAssembler to appropriate truth layers. |
| Outbox Event | A `StagedOutboxEvent` representing a message to be emitted to the event bus after R7 commit. Assembled by R6, emitted by R8. |
| ObservationContext | Metadata about the observation that triggered a write (timestamp, location, actors, dimensions). Required by R7 for observation recording. |
| HNSW | Hierarchical Navigable Small World -- pgvector index type for approximate nearest neighbor search. Used by TruthQueryService. |

---

## Appendix A: File Cross-Reference Matrix

| Component | Source File | Test File | Contract | Lines (src) | Lines (test) | Tests |
| --------- | ----------- | --------- | -------- | ----------: | -----------: | ----: |
| R6Staging (phase) | r6_staging.py | (no dedicated test) | p03_consolidation.v1.yaml (stage_60) | 612 | 0 | 0 |
| R6Coordinator | r6_coordinator.py | test_r6_coordinator.py | (none) | 590 | 662 | 32 |
| R6Output | r6_output.py | test_r6_output.py | (none) | 801 | 845 | 35 |
| StatusMarker | status_marker.py | test_status_marker.py | consolidation.status_updater.v1.yaml | 293 | 360 | 16 |
| DedupMetadata | dedup_metadata.py | test_dedup_metadata.py | (none) | 303 | 672 | 38 |
| ReconciliationRecorder | reconciliation_recorder.py | test_reconciliation_recorder.py | (none) | 253 | 506 | 25 |
| IdempotencyKeyGen | idempotency.py | test_idempotency.py | (none) | 279 | 542 | 51 |
| TruthWriteAssembler | truth_write_assembler.py | test_truth_write_assembler.py + test_truth_write_assembler_r5.py | (none) | 2,034 | 1,066 | 62 |
| KGWriteAssembler | kg_write_assembler.py | test_kg_write_assembler.py | (none) | 857 | 575 | 31 |
| OutboxAssembler | outbox_assembler.py | test_outbox_assembler.py | (none) | 572 | 755 | 50 |
| ManifestValidator | manifest_validator.py | test_manifest_validator.py | (none) | 532 | 616 | 26 |
| SummaryGenerator | summary_generator.py | test_summary_generator.py | (none) | 324 | 571 | 34 |
| IntentSignalAssembler | intent_signal_assembler.py | test_intent_signal_assembler.py | (none) | 653 | 652 | 30 |
| TruthQueryService | truth_query_service.py | (none) | (none) | 663 | 0 | 0 |
| Package init | **init**.py | (none) | (none) | 202 | 0 | 0 |
| Staged Writes | staged_writes.py | (shared with R7 tests) | (none) | 629 | N/A | N/A |
| Integration | N/A | test_r6_integration.py | N/A | N/A | 632 | 19 |
| R5 Integration | N/A | test_r6_r5_integration.py | N/A | N/A | 424 | 19 |
| **TOTALS** | | | | **8,968** | **9,884** | **468** |

---

## Appendix B: References

| # | Document | Location | Relevance |
| - | -------- | -------- | --------- |
| 1 | MASTER_IMPLEMENTATION_SKELETON.md | docs/plans/MASTER_IMPLEMENTATION_SKELETON.md (lines 5473-5540) | Epic 5.7: R6 Staging skeleton with execution flow, I/O contract, signal gaps, known issues |
| 2 | P03 Pipeline Contract v1 | k0/contracts/pipelines/p03_consolidation.v1.yaml | Stage_60 definition (lines 338-358) |
| 3 | Status Updater Contract v1 | k0/contracts/modules/consolidation.status_updater.v1.yaml | Module contract for status update component |
| 4 | P03 Consolidation Dossier v2 | docs/pipelines/P03_consolidation_dossier_v2.md | Pipeline dossier with R6 phase description |
| 5 | ADR-K003 (pgvector migration) | docs/architecture/decisions-K0/ | FAISS elimination, pgvector HNSW for all vector search |
| 6 | P03 R5 Dream Exploration Discovery | docs/pipelines/p03_enhancement_discovery/P03_R5_DREAM_EXPLORATION_DISCOVERY.md | Prior phase discovery document (R5 outputs feed into R6) |
| 7 | DISCOVERY_TEMPLATE.md | docs/pipelines/p03_enhancement_discovery/DISCOVERY_TEMPLATE.md | Template this document follows |

---

*End of P03 R6 Staging Discovery Document*
*Total sections: 16 (0-15) + 2 appendices*
*Generated: 2026-03-02*
