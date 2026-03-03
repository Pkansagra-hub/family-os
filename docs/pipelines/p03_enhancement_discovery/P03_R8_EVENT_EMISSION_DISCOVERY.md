# P03 R8 Event Emission Discovery & Enhancement Plan

> **Standard template for phase discovery.** Every table below includes a COLUMN GUIDE
> from the template. All 15 sections are covered.

---

## 0. Discovery Metadata

| Field | Value |
| ----- | ----- |
| Pipeline ID | P03 |
| Module Scope | consolidation.emission.emitter, consolidation.emission.gap_emitter, pipelines.p03.phases.r8_event_emitter, pipelines.p03.gap_emitter, pipelines.p03.offset_manager |
| Discovery Date | 2026-03-02 |
| Milestone Target | M5 |
| Governing ADRs | ADR-K003 |
| Related Dossier | `docs/pipelines/P03_consolidation_dossier_v2.md` |
| Author | copilot-claude |
| Status | DRAFT |

---

## 1. Current State Audit

### 1.1 Code Inventory

| # | File (relative path) | Lines | Status | Last Modified | Purpose |
| - | -------------------- | ----- | ------ | ------------- | ------- |
| 1 | k0/pipelines/p03/phases/r8_event_emitter.py | 609 | MOD | M5 | Orchestrates R8 phase: builds completion payload, stages events, commits offset, signals drain |
| 2 | k0/modules/consolidation/emission/emitter.py | 507 | MOD | M5 | Emits all 7 event topics via outbox pattern with circuit breaker |
| 3 | k0/modules/consolidation/emission/gap_emitter.py | 373 | MOD | M5 | Extended gap emitter for P06 Active Learning integration with dedup, capping, and priority |
| 4 | k0/modules/consolidation/emission/__init__.py | 50 | MOD | M5 | Module exports for emission package: EventEmitter, GapEmitterModule, factories |
| 5 | k0/pipelines/p03/gap_emitter.py | 480 | MOD | M3 | Pipeline-level gap emitter: GapType enum, P03GapEmitter, priority map, queue persistence |
| 6 | k0/pipelines/p03/offset_manager.py | 674 | LEGACY | M1 | Offset/watermark integration for exactly-once processing semantics |

**Total**: 6 source files, 2,693 lines

### 1.2 Contract Inventory

| # | Contract File | Version | Status | Lines | Governs |
| - | ------------- | ------- | ------ | ----- | ------- |
| 1 | k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | active | 433 | pipeline:p03 (stage_80_event_emitter section) |
| 2 | k0/contracts/modules/core.event_emitter.v1.yaml | v1 | active | 111 | module:core.event_emitter (P02 event emitter, reused for P03 stage config) |

### 1.3 Config Inventory

#### 1.3.1 YAML Config Keys

| Config File | Version | Key (dot-path) | Value | Type | Default | Required | Notes |
| ----------- | ------- | --------------- | ----- | ---- | ------- | -------- | ----- |
| p03_consolidation.v1.yaml | v1 | stages.stage_80.config.enable_telemetry_event | true | bool | true | no | Emit telemetry events for monitoring |
| p03_consolidation.v1.yaml | v1 | stages.stage_80.config.batch_emit_enabled | true | bool | true | no | Batch all events in single st_outbox transaction |
| p03_consolidation.v1.yaml | v1 | stages.stage_80.config.emit_phase_progress | true | bool | true | no | Emit per-phase progress events |

#### 1.3.2 Environment Variables

| Variable | Type | Default | Required | Used By | Purpose |
| -------- | ---- | ------- | -------- | ------- | ------- |
| N/A | | | | | R8 reads no environment variables directly; all config via YAML or constructor args |

#### 1.3.3 Feature Flags

| Flag Name | Source (env / config / DB) | Default | Scope (global / tenant / space) | Controls | Rollback Behavior |
| --------- | ------------------------- | ------- | ------------------------------- | -------- | ----------------- |
| USE_M5_EMITTERS | code (class attr) | False | global | Switches between M5 EventEmitter+GapEmitterModule path and legacy inline emission | Safe -- legacy path preserved, no data loss on toggle |

#### 1.3.4 Constants & Magic Numbers

| Constant | Location (file:line) | Value | Type | Rationale | Externalize? |
| -------- | -------------------- | ----- | ---- | --------- | ------------ |
| COMPLETION_TOPIC | r8_event_emitter.py:91 | "p03.consolidation.complete.v1" | str | Dossier 4.9 topic name | no -- contract-locked |
| GAP_TOPIC | r8_event_emitter.py:92 | "p03.gap.detected.v1" | str | Dossier 9.3.1 topic name | no -- contract-locked |
| USE_M5_EMITTERS | r8_event_emitter.py:96 | False | bool | M5 rollout safety: defaults to legacy path until proven stable | yes -- should be config |
| failure_threshold | r8_event_emitter.py:103 | 5 | int | Circuit breaker: open after 5 consecutive staging failures | yes |
| reset_timeout_ms | r8_event_emitter.py:104 | 60000 | int | Circuit breaker recovery: 60s before retry (1 minute) | yes |
| ttl_hours | r8_event_emitter.py:110 | 168 | int | Gap TTL: 7 days before expiry | yes |
| max_gaps_per_cycle | r8_event_emitter.py:109 | 50 | int | Cap to prevent P06 overload; high-volume batches silently drop excess | yes |
| MAX_GAPS_PER_CYCLE | gap_emitter.py (module):58 | 50 | int | Duplicated cap constant in GapEmitterModule | no -- redundant, use config |
| DEFAULT_TTL_HOURS | gap_emitter.py (module):61 | 168 | int | Duplicated TTL constant in GapEmitterModule | no -- redundant, use config |
| GAP_TOPIC | gap_emitter.py (module):64 | "p03.gap.detected.v1" | str | Duplicated topic constant | no -- redundant |
| dedup_window_ms | gap_emitter.py (module):91 | 3600000 | int | 1-hour dedup window for gap events | yes |
| GAP_PRIORITY_MAP | gap_emitter.py (pipeline):99 | {CONTRADICTION:100, AMBIGUOUS_ENTITY:80, STRUCTURAL_HOLE:70, CONCEPT_DRIFT:60, LOW_CONFIDENCE_EDGE:50, STALE_ANCHOR:40, MISSING_ATTRIBUTE:30} | Dict[GapType, int] | Severity-based priority per dossier 6.11 | no -- domain logic |
| default_expires_ms | gap_emitter.py (pipeline):130 | 604800000 | int | 7 days in ms -- gap expiry window | yes |
| max_attempts | gap_emitter.py (pipeline):131 | 3 | int | P06 max resolution attempts before gap expires | yes |
| dedup_window_ms | gap_emitter.py (pipeline):129 | 3600000 | int | 1-hour dedup window (duplicated in module-level gap_emitter) | yes |
| QUESTION_TEMPLATES | gap_emitter.py (module):136 | dict (7 entries) | Dict[str, str] | Question template strings for P06 prompt generation | no -- domain strings |

### 1.4 Migration Inventory

| # | Migration File | Table(s) | Operation | Columns Affected | Reversible? |
| - | -------------- | -------- | --------- | ---------------- | ----------- |
| N/A | No R8-specific migrations | st_outbox, st_learning_queue, st_offsets | N/A | N/A | N/A |

> R8 writes to tables created by earlier migrations (st_outbox M1, st_learning_queue M3, st_offsets M1).

---

## 2. API Surface

### 2.1 Public Classes

| # | Class | File | Bases | Purpose | Public Methods |
| - | ----- | ---- | ----- | ------- | -------------- |
| 1 | R8EventEmitter | r8_event_emitter.py | none | Phase orchestrator: builds completion, stages events, commits offset | run() |
| 2 | EventEmitter | emitter.py | none | Emits all 7 event topics via outbox with circuit breaker | emit_all(), emit_completion(), emit_insight_events(), reset_circuit_breaker() |
| 3 | GapEmitterModule | gap_emitter.py (module) | none | Extended gap emitter with dedup, capping, priority ordering | emit(), reset_cycle() |
| 4 | P03GapEmitter | gap_emitter.py (pipeline) | none | Base gap emitter: queue persistence + outbox staging | emit_gaps() |
| 5 | EventTopic | emitter.py | Enum | Enum of 7 P03 event topics | (enum values) |
| 6 | GapType | gap_emitter.py (pipeline) | Enum | Enum of 7 gap types with legacy fallback mapping | from_string() |
| 7 | CircuitBreakerConfig | emitter.py | dataclass | Circuit breaker settings: threshold, timeout, queue_on_failure | (fields) |
| 8 | GapEmitterConfig | gap_emitter.py (module) | dataclass | Extended gap config: cap, TTL, dedup, emit_to_outbox, persist_to_queue | (fields) |
| 9 | P03GapEmitterConfig | gap_emitter.py (pipeline) | dataclass (frozen) | Base gap config: topic, dedup, window, expires, max_attempts | (fields) |
| 10 | EmitResult | emitter.py | dataclass | Event emission result: total, by_topic, failed, duration_ms | success (property) |
| 11 | GapEmitStats | gap_emitter.py (module) | dataclass | Gap emission stats: total, emitted, deduplicated, capped, by_type, by_priority | skipped (property) |
| 12 | GapEmitResult | gap_emitter.py (pipeline) | dataclass | Base gap result: total, emitted, deduplicated, by_type | (fields) |
| 13 | OutboxEntry | storage/outbox.py | dataclass | Outbox entry model: id, tenant_id, driver, op_kind, payload, fingerprint, status | (fields) |
| 14 | Offset | storage/offsets.py | dataclass | Offset record: subscriber_id, topic, space_id, tenant_id, offset, updated_ts | (fields) |

### 2.2 Public Functions

| # | Function | File | Signature | Returns | Purpose |
| - | -------- | ---- | --------- | ------- | ------- |
| 1 | create_event_emitter | emitter.py | (circuit_config=None) -> EventEmitter | EventEmitter | Factory for EventEmitter with optional circuit breaker config |
| 2 | create_gap_emitter | gap_emitter.py (module) | (config=None) -> GapEmitterModule | GapEmitterModule | Factory for GapEmitterModule with optional config |

### 2.3 Key Method Signatures

| # | Method | Class | Signature | Returns | Async | Notes |
| - | ------ | ----- | --------- | ------- | ----- | ----- |
| 1 | run | R8EventEmitter | (envelope, ctx) | P03PhaseResult | yes | Main entry point; dispatches to _run_m5 or _run_legacy based on flag |
| 2 | emit_all | EventEmitter | (uow, envelope, summary) | EmitResult | yes | Emits completion + action-based aggregate events |
| 3 | emit_completion | EventEmitter | (uow, envelope, summary) | EmitResult | yes | Emits only completion event |
| 4 | emit_insight_events | EventEmitter | (uow, envelope, insights) | EmitResult | yes | Emits p03.insight.generated.v1 per insight (Issue 8.1.13) |
| 5 | emit | GapEmitterModule | (uow, gaps, envelope) | GapEmitStats | yes | Sort, dedup, cap, persist, stage gap events |
| 6 | emit_gaps | P03GapEmitter | (uow, gaps, envelope) | GapEmitResult | yes | Base gap emission: per-gap dedup check + queue + outbox |

---

## 3. Algorithms & Business Logic

### 3.1 Algorithm Inventory

| # | Algorithm Name | Location (file:line) | Category | Complexity | Description |
| - | -------------- | -------------------- | -------- | ---------- | ----------- |
| 1 | M5/Legacy dispatch | r8_event_emitter.py:145 | routing | O(1) | Feature flag dispatch: USE_M5_EMITTERS selects M5 emitters vs legacy inline path |
| 2 | Completion payload assembly | r8_event_emitter.py:247 | data assembly | O(P) where P=phases | Collects phase durations, errors, summary stats from envelope into completion schema |
| 3 | Status determination | r8_event_emitter.py:285 | classification | O(P) | Scans phase_statuses: all DONE=SUCCESS, mixed=PARTIAL, all FAIL=FAILED |
| 4 | Action-based event emission | emitter.py:275 | aggregate emit | O(A) where A=action types | Converts action_breakdown (REINFORCE/CREATE/EVOLVE/PRUNE) to typed aggregate events |
| 5 | Circuit breaker | emitter.py:475 | fault tolerance | O(1) | Opens after N failures, resets after timeout_ms; blocks event staging while open |
| 6 | Gap priority sorting | gap_emitter.py (module):213 | sorting | O(G log G) | Sorts gaps by GAP_PRIORITY_MAP score descending (CONTRADICTION=100 first) |
| 7 | Gap deduplication (module) | gap_emitter.py (module):219 | filtering | O(G) | MD5 hash of gap_type:entity_id; tracks seen keys per cycle in set |
| 8 | Gap capping | gap_emitter.py (module):231 | truncation | O(1) | Slice sorted+deduped list to max_gaps_per_cycle (default 50) |
| 9 | Gap deduplication (pipeline) | gap_emitter.py (pipeline):288 | DB check | O(G) | Queries st_learning_queue for existing gap within dedup_window_ms |
| 10 | Gap ID generation | gap_emitter.py (pipeline):271 | hashing | O(1) | Pattern: p03:gap:{cycle_id}:{entity_id}:{gap_type} -- deterministic |
| 11 | Offset calculation | r8_event_emitter.py:538 | watermark | O(E) | Takes max(event_id) from batch, parses ULID timestamp prefix as base32 int |
| 12 | Outbox drain signal | r8_event_emitter.py:590 | hook | O(1) | No-op placeholder for future outbox publisher integration |

### 3.2 Algorithm Details

#### 3.2.1 M5/Legacy Dispatch (r8_event_emitter.py:145)

```
IF USE_M5_EMITTERS:
    -> _run_m5():
       1. EventEmitter.emit_all(uow, envelope, r6_summary)
       2. GapEmitterModule.emit(uow, gaps, envelope)
       3. _commit_offset(uow, envelope)
       4. _trigger_outbox_drain(ctx)
ELSE:
    -> _run_legacy():
       1. _build_completion_payload(envelope)
       2. _stage_completion_event(uow, envelope, payload)
       3. _process_gaps(uow, envelope)  [uses P03GapEmitter]
       4. _commit_offset(uow, envelope)
       5. _trigger_outbox_drain(ctx)
```

Both paths execute within a single `async with ctx.syscalls.unit_of_work() as uow:` block.
The offset commit and outbox drain happen at the end of both paths.

#### 3.2.2 Completion Payload Assembly (r8_event_emitter.py:247)

```
Input:  P03BatchEnvelope (completed R0-R7)
Output: dict conforming to p03_consolidation_complete.json schema

Steps:
  1. _determine_status(envelope) -> SUCCESS | PARTIAL | FAILED
  2. _build_summary(envelope) -> aggregate counts:
     - events_processed, clusters_created, duplicates_found
     - entities_created, edges_created, gaps_detected
     - patterns_updated, salience_changes
     - truth_writes (from R7 WriteResult if available)
  3. _collect_phase_durations(envelope) -> {phase_id: duration_ms}
  4. _collect_errors(envelope) -> [{phase, error_type, message}]
  5. Assemble: {cycle_id, tenant_id, space_id, status, summary,
                duration_ms, completed_at, phase_durations, errors}
```

#### 3.2.3 Circuit Breaker (emitter.py:475)

```
State: _failures (int), _last_failure_ms (int)
Config: failure_threshold, reset_timeout_ms

_is_circuit_open():
  IF _failures < failure_threshold:  CLOSED (allow)
  IF now_ms - _last_failure_ms > reset_timeout_ms:  RESET (allow)
  ELSE:  OPEN (block)

On success: _failures = 0
On failure: _failures += 1, _last_failure_ms = now
```

No half-open state. After timeout, circuit resets to 0 failures immediately.
This means a single success after timeout resets fully (no gradual recovery).

#### 3.2.4 Gap Emission Pipeline (GapEmitterModule)

```
Input:  List[GapCandidate] from R4
Output: GapEmitStats

Steps:
  1. SORT by GAP_PRIORITY_MAP[gap_type] descending
  2. DEDUPLICATE: md5(gap_type + ":" + entity_id) tracked per-cycle
  3. CAP: first max_gaps_per_cycle entries
  4. For each gap:
     a. PERSIST to st_learning_queue (ON CONFLICT DO NOTHING)
     b. STAGE to st_outbox (fingerprint = gap:{gap_id})
  5. Return stats (emitted, deduplicated, capped)
```

#### 3.2.5 Offset Calculation (r8_event_emitter.py:538)

```
Input:  envelope.events (list of P03EventState)
Output: int (offset value for st_offsets)

Steps:
  1. max_event_id = max(e.event_id for e in envelope.events)
  2. IF len(max_event_id) >= 10:
       offset = int(max_event_id[:10], 32)  # ULID timestamp prefix
     ELSE:
       offset = hash(max_event_id)  # fallback
  3. Build Offset(subscriber_id="p03", topic="p02.hipp_events", ...)
  4. uow.upsert_offset(offset_record)
```

### 3.3 Decision Points

| # | Decision | Location | Options | Current Choice | Rationale |
| - | -------- | -------- | ------- | -------------- | --------- |
| 1 | M5 vs Legacy emission path | r8_event_emitter.py:145 | USE_M5_EMITTERS True/False | False | Defaults to legacy during rollout; M5 path fully implemented but not exercised |
| 2 | Gap dedup: per-cycle (module) vs per-window (pipeline) | gap_emitter.py (both) | In-memory set vs DB query | Both | Module uses fast in-memory; pipeline does DB check for cross-cycle dedup |
| 3 | Aggregate vs per-record events | emitter.py:275 | One event per action vs one per record | Aggregate | ReconciliationSummary has only counts, not individual decisions |
| 4 | st_outbox driver for gaps | gap_emitter.py module:349 vs pipeline:423 | "p03" vs "p06" | Inconsistent | Module-level uses driver="p06"; pipeline-level uses driver="p03" |

---

## 4. Data Flow

### 4.1 Input Data

| # | Source | Type | Fields Used | Validation | Required |
| - | ------ | ---- | ----------- | ---------- | -------- |
| 1 | P03BatchEnvelope.context | P03CycleContext | cycle_id, tenant_id, space_id | Non-null (set during R0) | yes |
| 2 | P03BatchEnvelope.events | List[P03EventState] | event_id (for offset calc) | Non-empty list | yes |
| 3 | P03BatchEnvelope.phases.r4_gap_candidates | List[GapCandidate] | gap_id, gap_type, related_entity_id, entropy_score, priority, candidate_values, context_json | Type check (GapCandidate) | no (empty = no gaps) |
| 4 | P03BatchEnvelope.phases.r6_summary | ReconciliationSummary | total_events, consolidated_count, duplicate_count, pruned_count, pending_review_count, action_breakdown, layer_write_counts, kg_entity_count, kg_edge_count, gap_count, cycle_duration_ms | Non-null (set by R6) | yes (M5 path) |
| 5 | P03BatchEnvelope.phases.r7_result | WriteResult | total_succeeded, total_failed, by_layer, failed_decision_ids | Optional (None if R7 skipped) | no |
| 6 | P03BatchEnvelope.phase_statuses | Dict[PhaseId, Status] | per-phase DONE/FAIL status | Dict populated by runner | yes |
| 7 | P03BatchEnvelope.observability | P03ObservabilityContext | errors, phase durations, metrics_registry | Non-null | yes |
| 8 | P03RunnerContext.syscalls | SyscallInterface | unit_of_work() factory | Callable returning UoW | yes |

### 4.2 Output Data

| # | Destination | Type | Fields Written | Guarantees |
| - | ----------- | ---- | -------------- | ---------- |
| 1 | st_outbox (completion event) | OutboxEntry | tenant_id, space_id, driver="p03", op_kind=COMPLETION_TOPIC, payload (JSON), fingerprint="complete:{cycle_id}" | Idempotent: ON CONFLICT DO NOTHING on fingerprint |
| 2 | st_outbox (action events) | OutboxEntry | tenant_id, space_id, driver="p03", op_kind={topic}, payload (JSON), fingerprint="{action}_agg:{cycle_id}" | Idempotent: ON CONFLICT DO NOTHING |
| 3 | st_outbox (gap events) | OutboxEntry | tenant_id, space_id, driver="p03"/"p06", op_kind=GAP_TOPIC, payload (JSON), fingerprint="gap:{gap_id}" | Idempotent: ON CONFLICT DO NOTHING |
| 4 | st_learning_queue | row | id=gap_id, tenant_id, space_id, gap_type, entity_id, confidence_score, entropy_score, context_json, status="PENDING", created_at, expires_at, attempts=0, consolidation_cycle_id | Idempotent: ON CONFLICT DO NOTHING |
| 5 | st_offsets | Offset record | subscriber_id="p03", topic="p02.hipp_events", space_id, tenant_id, offset (int), updated_ts | Idempotent: UPSERT |
| 6 | P03PhaseResult | return value | phase_id=R8_EMIT, duration_ms, outputs_summary, idempotency_key | Always returned |

### 4.3 Data Flow Diagram

```text
R0-R7 Complete
      |
      v
+---------------------+
| R8EventEmitter.run() |
+---------------------+
      |
      +--- USE_M5_EMITTERS? ---+
      |                        |
    [False]                  [True]
      |                        |
      v                        v
_run_legacy()            _run_m5()
      |                        |
      v                        v
_build_completion     EventEmitter.emit_all()
_payload()                     |
      |                   +----+----+
      v                   |         |
_stage_completion    _emit_     _emit_action_
_event()             completion  _events()
      |                   |         |
      v                   |    +----+----+----+
_process_gaps()           |    |    |    |    |
  [P03GapEmitter]         | REINFORCE CREATE EVOLVE PRUNE
      |                   |    |    |    |    |
      v                   +----+----+----+----+
      |                        |
      +--------+--------+     v
               |          GapEmitterModule.emit()
               |               |
               v          sort -> dedup -> cap
_commit_offset()               |
      |                   _emit_gap() x N
      v                        |
_trigger_outbox_drain()   +---------+---------+
      |                   |                   |
      v                   v                   v
  (no-op)          _persist_to_queue    _stage_outbox_event
                   (st_learning_queue)  (st_outbox)
```

---

## 5. Storage Interactions

### 5.1 Tables Read

| # | Table | Columns Read | Query Pattern | Index Used | Called By |
| - | ----- | ------------ | ------------- | ---------- | -------- |
| 1 | st_learning_queue | id, created_at | `SELECT id FROM st_learning_queue WHERE id=$1 AND created_at > $2` | PK (id) | P03GapEmitter._is_duplicate() |

### 5.2 Tables Written

| # | Table | Operation | Columns Written | Write Pattern | Idempotency | Called By |
| - | ----- | --------- | --------------- | ------------- | ----------- | -------- |
| 1 | st_outbox | INSERT | id, wal_pos, tenant_id, space_id, driver, op_kind, payload, fingerprint, requeue_seq, retries, status | uow.stage_outbox(OutboxEntry) | ON CONFLICT DO NOTHING (fingerprint) | EventEmitter._stage_event(), R8EventEmitter._stage_completion_event(), _stage_gap_event() |
| 2 | st_learning_queue | INSERT | id, tenant_id, space_id, gap_type, entity_id, confidence_score, entropy_score, context_json, status, created_at, expires_at, attempts, max_attempts, consolidation_cycle_id | `INSERT ... ON CONFLICT (id) DO NOTHING` | Yes (id PK) | GapEmitterModule._persist_to_queue(), P03GapEmitter._persist_to_queue() |
| 3 | st_offsets | UPSERT | subscriber_id, topic, space_id, tenant_id, offset, updated_ts | uow.upsert_offset(Offset) | Yes (UPSERT on PK) | R8EventEmitter._commit_offset() |

### 5.3 Write Volume Estimates

| Table | Writes per Cycle | Basis |
| ----- | ---------------- | ----- |
| st_outbox | 2-7 | 1 completion + 0-4 action aggregates + 0-2 insight events |
| st_outbox (gaps) | 0-50 | Up to max_gaps_per_cycle (capped at 50) |
| st_learning_queue | 0-50 | Same as gap outbox events |
| st_offsets | 1 | Exactly one offset upsert per cycle |

---

## 6. Events & Topics

### 6.1 Events Emitted

| # | Topic | Schema / Payload | When Emitted | Consumers | Fingerprint Pattern |
| - | ----- | ---------------- | ------------ | --------- | ------------------- |
| 1 | p03.consolidation.complete.v1 | {cycle_id, tenant_id, space_id, status, summary, duration_ms, completed_at, phase_durations, errors} | Every successful cycle | Monitoring, P08 trigger | complete:{cycle_id} |
| 2 | p03.truth.reinforced.v1 | {tenant_id, space_id, cycle_id, count, reinforced_at} | When action_breakdown has REINFORCE > 0 | Strength tracker feedback | reinforce_agg:{cycle_id} |
| 3 | p03.truth.created.v1 | {tenant_id, space_id, cycle_id, count, created_at} | When non-st_sem CREATE > 0 | Analytics | create_agg:{cycle_id} |
| 4 | p03.truth.evolved.v1 | {tenant_id, space_id, cycle_id, count, evolved_at} | When EVOLVE > 0 | Analytics | evolve_agg:{cycle_id} |
| 5 | p03.memory.pruned.v1 | {tenant_id, space_id, cycle_id, count, pruned_at} | When PRUNE > 0 | Regret detector feedback | prune_agg:{cycle_id} |
| 6 | p03.pattern.detected.v1 | {tenant_id, space_id, cycle_id, count, detected_at} | When st_sem CREATE > 0 | P06 gap detector, analytics | pattern_agg:{cycle_id} |
| 7 | p03.gap.detected.v1 | {gap_id, cycle_id, tenant_id, space_id, gap_type, related_entity_id, entropy_score, priority, candidate_values, detected_at} | Per gap (after dedup+cap) | P06 gap resolution | gap:{gap_id} |
| 8 | p03.insight.generated.v1 | {tenant_id, space_id, cycle_id, insight_id, insight_type, concept_a_id, concept_b_id, pmi_score, novelty_score, relevance_score, confidence, description, supporting_evidence, generated_at} | Per R5 insight (Issue 8.1.13) | Analytics | {cycle_id}:insight:{insight_id} |

### 6.2 Events Consumed

| # | Topic | Source | How Consumed | Module |
| - | ----- | ------ | ------------ | ------ |
| N/A | R8 consumes no events | N/A | N/A | N/A |

> R8 is a terminal phase that only emits events. All input comes from the P03BatchEnvelope (in-memory).

### 6.3 Event Topic Contract Alignment

| # | Topic | In Code | In Pipeline Contract YAML | In Module Contract YAML | Aligned? | Gap |
| - | ----- | ------- | ------------------------- | ----------------------- | -------- | --- |
| 1 | p03.consolidation.complete.v1 | Yes (emitter.py:61) | Yes (p03 stage_80 description) | No (core.event_emitter.v1.yaml is P02-specific) | partial | Pipeline contract lists it; module contract is for P02 not P03 |
| 2 | p03.pattern.detected.v1 | Yes (emitter.py:62) | Yes (p03 stage_80 "p03.pattern.discovered.v1") | No | partial | Topic name mismatch: contract says "discovered", code says "detected" |
| 3 | p03.truth.reinforced.v1 | Yes (emitter.py:63) | Not explicitly listed | No | missing | Not in contract YAML |
| 4 | p03.truth.created.v1 | Yes (emitter.py:64) | Not explicitly listed | No | missing | Not in contract YAML |
| 5 | p03.truth.evolved.v1 | Yes (emitter.py:65) | Not explicitly listed | No | missing | Not in contract YAML |
| 6 | p03.memory.pruned.v1 | Yes (emitter.py:66) | Not explicitly listed | No | missing | Not in contract YAML |
| 7 | p03.gap.detected.v1 | Yes (gap_emitter.py) | Yes (p03 stage_80 description) | No | partial | In pipeline contract; no dedicated module contract |
| 8 | p03.insight.generated.v1 | Yes (emitter.py:68) | Not in P03 contract | No | missing | Issue 8.1.13 added code but not contract (known issue from skeleton) |

---

## 7. Observability

### 7.1 Logging

| # | Logger | Level | Key Log Points | Structured Fields |
| - | ------ | ----- | -------------- | ----------------- |
| 1 | r8_event_emitter (module logger) | INFO | R8 start, R8 complete (legacy), R8 complete (M5), R8 fail | cycle_id, gaps_count, use_m5_emitters, duration_ms, events_emitted, gaps_emitted |
| 2 | emitter (module logger) | INFO, WARNING, ERROR | emission complete, circuit open (skip), stage failed | cycle_id, total_emitted, failed_count, duration_ms, fingerprint, topic |
| 3 | gap_emitter (module logger) | INFO | emission complete | cycle_id, total_received, emitted, deduplicated, capped, duration_ms |
| 4 | r8_event_emitter legacy | INFO | gaps processed via emitter | cycle_id, total_gaps, emitted, deduplicated, by_type |

### 7.2 Metrics

| # | Metric Name | Type | Labels | Source |
| - | ----------- | ---- | ------ | ------ |
| 1 | p03.r8.gaps.emitted.{gap_type} | counter | gap_type | P03GapEmitter.emit_gaps() via observability.increment() |
| 2 | p03.r8.gaps.deduplicated.{gap_type} | counter | gap_type | P03GapEmitter.emit_gaps() via observability.increment() |
| 3 | p03.r8.gaps.detected | counter | (none) | P03GapEmitter.emit_gaps() via observability.increment() |
| 4 | metrics_registry.emit_gap_detected | counter | tenant_id, gap_type, importance | P03GapEmitter (Issue 6.1.5) |
| 5 | metrics_registry.emit_gap_deduplicated | counter | tenant_id, gap_type | P03GapEmitter (Issue 6.1.5) |

### 7.3 Tracing

| # | Span Name | Location | Attributes | Parent |
| - | --------- | -------- | ---------- | ------ |
| N/A | No OTel spans | N/A | N/A | N/A |

> R8 has zero OTel tracing instrumentation. All observability is via structured logging and counter metrics.

### 7.4 Observability Gaps

| # | Gap | Impact | Recommendation |
| - | --- | ------ | -------------- |
| 1 | No OTel spans for R8 phase or sub-operations | Cannot trace R8 execution in distributed tracing dashboards | Add spans: r8.phase, r8.emit_completion, r8.emit_gaps, r8.commit_offset |
| 2 | No latency histograms for event staging | Cannot measure P95 emission latency per topic | Add histogram: r8.emit.latency_ms with topic label |
| 3 | No circuit breaker state metric | Cannot monitor/alert on circuit breaker open state | Add gauge: r8.circuit_breaker.state (0=closed, 1=open) |
| 4 | No metric for offset commit latency | Cannot track offset write performance | Add histogram: r8.offset.commit_latency_ms |
| 5 | No metric for total events emitted per cycle | Only logged, not exposed as metric | Add counter: r8.events_emitted_total with topic label |

---

## 8. Test Coverage

### 8.1 Test Inventory

| # | Test File | Lines | Tests | Type | What It Tests |
| - | --------- | ----- | ----- | ---- | ------------- |
| 1 | tests/k0/modules/consolidation/emission/test_emitter.py | 360 | 26 | unit | EventEmitter: emit_all, emit_completion, emit_insight_events, circuit breaker, EmitResult, EventTopic enum, factory |
| 2 | tests/k0/modules/consolidation/emission/test_gap_emitter.py | 391 | 31 | unit | GapEmitterModule: emit with dedup/capping/priority, GapEmitStats, GapEmitterConfig, constants, factory |
| 3 | tests/k0/pipelines/p03/test_p03_r8_event_emitter.py | 495 | 22 | unit | R8EventEmitter: run (legacy path), completion payload assembly, status determination, gap processing, offset commit |
| 4 | tests/k0/pipelines/p03/test_p03_gap_emitter.py | 455 | 26 | unit | P03GapEmitter: emit_gaps, dedup check, queue persistence, outbox staging, GapType enum, priority map |
| 5 | tests/k0/pipelines/p03/test_r8_m5_wiring.py | 340 | 11 | integration | R8 M5 wiring: EventEmitter + GapEmitterModule integration via R8EventEmitter with USE_M5_EMITTERS=True |
| 6 | tests/k0/pipelines/p03/test_r8_r7_integration.py | 213 | 8 | integration | R8-R7 WriteResult integration: R7 results in completion payload, partial/failed status handling |
| 7 | tests/k0/pipelines/p03/test_r7_r8_integration.py | 743 | 16 | integration | Full R7-R8 pipeline: truth writes then event emission, outbox entries, offset commits, gap processing |

**Summary**: 7 test files, 2,997 lines, 140 tests (79 unit + 61 integration)

### 8.2 Test Results

| # | Test File | Status | Pass | Fail | Skip | Notes |
| - | --------- | ------ | ---- | ---- | ---- | ----- |
| 1 | test_emitter.py | PASS | 26 | 0 | 0 | |
| 2 | test_gap_emitter.py | PASS | 31 | 0 | 0 | |
| 3 | test_p03_r8_event_emitter.py | PASS | 22 | 0 | 0 | |
| 4 | test_p03_gap_emitter.py | PASS | 26 | 0 | 0 | |
| 5 | test_r8_m5_wiring.py | PASS | 11 | 0 | 0 | |
| 6 | test_r8_r7_integration.py | PASS | 8 | 0 | 0 | |
| 7 | test_r7_r8_integration.py | PASS | 16 | 0 | 0 | |

### 8.3 Coverage Gaps

| # | Gap | Location | What's Missing | Priority |
| - | --- | -------- | -------------- | -------- |
| 1 | M5 path not exercised by default | r8_event_emitter.py:96 | USE_M5_EMITTERS=False means legacy path always runs in production; M5 path only tested via explicit flag override | P1 |
| 2 | Circuit breaker recovery under concurrent load | emitter.py:475 | No test simulates concurrent event staging with circuit breaker transitions | P2 |
| 3 | Offset ULID parsing edge cases | r8_event_emitter.py:548 | No test for short event_id strings (< 10 chars) triggering hash() fallback | P2 |
| 4 | Gap cap overflow logging | gap_emitter.py (module):231 | No test verifies that capped gaps are logged/tracked for alerting | P3 |
| 5 | Empty envelope.events edge case | r8_event_emitter.py:537 | No test for offset commit with empty event list (early return) | P3 |
| 6 | Outbox drain trigger | r8_event_emitter.py:590 | No-op method, no test -- placeholder for future integration | P3 |

---

## 9. Dependencies

### 9.1 Upstream Dependencies (R8 reads from)

| # | Module/Component | What R8 Reads | Failure Impact |
| - | ---------------- | ------------- | -------------- |
| 1 | R0-R7 (P03BatchEnvelope) | cycle context, events, phase outputs, r4_gap_candidates, r6_summary, r7_result, phase_statuses, observability | If envelope incomplete, R8 produces partial/incorrect completion payload |
| 2 | k0.storage.outbox.OutboxEntry | Data model for outbox staging | Import failure = R8 cannot start |
| 3 | k0.storage.offsets.Offset | Data model for offset commit | Import failure = R8 cannot start |
| 4 | k0.uow.unit_of_work.UnitOfWork | Transaction wrapper (stage_outbox, upsert_offset, connection) | If UoW unavailable, R8 fails entirely |
| 5 | k0.pipelines.p03.runner_contract | P03PhaseId.R8_EMIT, P03PhaseStatus | Import failure = R8 cannot register |
| 6 | k0.pipelines.p03.phase_interface | P03PhaseResult, P03RunnerContext | Import failure = R8 cannot return results |
| 7 | k0.pipelines.p03.observability | P03Error | Import failure = R8 cannot report errors |

### 9.2 Downstream Dependencies (R8 feeds into)

| # | Consumer | What It Receives | How |
| - | -------- | ---------------- | --- |
| 1 | Outbox Publisher (background) | OutboxEntry rows in st_outbox | Polls st_outbox for PENDING entries, routes by op_kind topic |
| 2 | P06 Active Learning | Gap rows in st_learning_queue | Queries PENDING gaps by priority, resolves via user interaction |
| 3 | P08 Embedding Management | p03.consolidation.complete.v1 event | Triggers P08 integrity check on cycle completion |
| 4 | Monitoring/Analytics | All event topics | Consumed for dashboards, SLO tracking, anomaly detection |
| 5 | Offset Store | st_offsets row | Used by R0 to determine next batch start position |

### 9.3 Internal Dependencies (within R8 scope)

| # | Dependency | Depender | Type | Notes |
| - | ---------- | -------- | ---- | ----- |
| 1 | P03GapEmitter | GapEmitterModule | composition | Module-level gap_emitter wraps P03GapEmitter via delegation |
| 2 | P03GapEmitter | R8EventEmitter (legacy path) | direct call | Legacy _process_gaps() creates P03GapEmitter inline |
| 3 | EventEmitter | R8EventEmitter (M5 path) | composition | Initialized in __init__, called in _run_m5 |
| 4 | GapEmitterModule | R8EventEmitter (M5 path) | composition | Initialized in __init__, called in _run_m5 |
| 5 | CircuitBreakerConfig | EventEmitter | constructor arg | Hardcoded defaults in R8EventEmitter.__init__ |
| 6 | GapEmitterConfig | GapEmitterModule | constructor arg | Hardcoded defaults in R8EventEmitter.__init__ |
| 7 | GapType + GAP_PRIORITY_MAP | GapEmitterModule | import | Gap sorting and priority rely on pipeline-level definitions |

---

## 10. Performance Characteristics

### 10.1 Performance Budget

| # | Operation | Budget | Measured | Method | Notes |
| - | --------- | ------ | -------- | ------ | ----- |
| 1 | R8 total phase | 30s (contract timeout) | not measured | PhaseContract.timeout_seconds | 30s is generous; typical R8 should be < 1s |
| 2 | Single outbox stage | < 1ms | not measured | In-memory UoW buffering | Actual DB write happens at UoW commit |
| 3 | Gap dedup query | < 5ms per gap | not measured | `SELECT id FROM st_learning_queue WHERE id=$1 AND created_at > $2` | PK lookup, should be fast |
| 4 | Offset upsert | < 5ms | not measured | `uow.upsert_offset()` | Single-row upsert |
| 5 | UoW commit (all R8 writes) | < 100ms | not measured | Batch commit of outbox + gaps + offset | All writes committed atomically |

### 10.2 Bottleneck Analysis

| # | Bottleneck | Location | Impact | Mitigation |
| - | ---------- | -------- | ------ | ---------- |
| 1 | Sequential gap dedup queries | P03GapEmitter._is_duplicate() | O(G) DB queries -- 50 gaps = 50 round-trips | Batch dedup check with `WHERE id IN ($1, $2, ..., $N)` |
| 2 | JSON serialization per event | EventEmitter._stage_event(), R8._stage_gap_event() | json.dumps per event; 57 events max = 57 serializations | Negligible cost; json.dumps is fast for small payloads |
| 3 | Gap priority sorting | GapEmitterModule._sort_by_priority() | O(G log G) sort; G max 50 | Negligible for small lists |
| 4 | Completion payload assembly | R8._build_completion_payload() | Iterates phase_statuses, errors, durations | O(P) where P = 9 phases; negligible |

### 10.3 Scalability Concerns

| # | Concern | Trigger | Impact | Recommendation |
| - | ------- | ------- | ------ | -------------- |
| 1 | Gap dedup DB queries scale linearly | > 50 raw gaps from R4 | 50+ sequential queries before cap is applied | Move dedup to in-memory only (as GapEmitterModule does); or batch query |
| 2 | st_learning_queue growth | High gap detection rate | Table grows unbounded if P06 resolution is slow | Add expiry cleanup job or retention policy |
| 3 | st_outbox growth | High emission rate + slow drain | Outbox entries accumulate if background publisher is behind | Monitor outbox depth; add back-pressure mechanism |

---

## 11. Gap Analysis

### 11.1 Functional Gaps

| # | ID | Gap | Severity | Location | Evidence | Recommendation |
| - | -- | --- | -------- | -------- | -------- | -------------- |
| 1 | FG-001 | USE_M5_EMITTERS defaults to False -- M5 emitters never exercised in production | P1 | r8_event_emitter.py:96 | Class attribute `USE_M5_EMITTERS = False`; legacy path is always used | Set True as default; add integration test proving M5 path works end-to-end |
| 2 | FG-002 | p03.insight.generated.v1 topic exists in EventEmitter code but NOT in P03 pipeline contract YAML | P2 | emitter.py:68 vs p03_consolidation.v1.yaml | EventTopic.INSIGHT_GENERATED defined; topic absent from contract | Add topic to pipeline contract YAML (Issue 8.1.13 drift) |
| 3 | FG-003 | Topic name mismatch: contract says "p03.pattern.discovered.v1", code uses "p03.pattern.detected.v1" | P2 | emitter.py:62 vs p03_consolidation.v1.yaml:384 | Contract description references "discovered"; code emits "detected" | Align contract and code on one name |
| 4 | FG-004 | Outbox drain trigger is a no-op | P3 | r8_event_emitter.py:590 | `_trigger_outbox_drain()` is `pass` | Implement or document as intentional (rely on background publisher) |
| 5 | FG-005 | OffsetManager (674 lines) exists but R8 uses direct uow.upsert_offset() instead | P2 | r8_event_emitter.py:538 vs offset_manager.py | R8 bypasses OffsetManager.decide()/commit() -- loses idempotency checks, DLQ routing, checkpoint logic | Wire R8 to OffsetManager for consistent offset handling |
| 6 | FG-006 | Legacy gap methods (_persist_gap_to_queue, _stage_gap_event) still present even though P03GapEmitter exists | P3 | r8_event_emitter.py:377-440 | ~60 lines of dead legacy code alongside P03GapEmitter delegation | Delete after M5 path is proven stable |
| 7 | FG-007 | Action events are aggregate (count-based) not per-record | P3 | emitter.py:275 | ReconciliationSummary only has counts; individual decisions not forwarded | Document as intentional or add per-record emission for fine-grained downstream analytics |

### 11.2 Contract Gaps

| # | Contract | Gap | Impact | Recommendation |
| - | -------- | --- | ------ | -------------- |
| 1 | p03_consolidation.v1.yaml | Missing 4 event topics: truth.reinforced, truth.created, truth.evolved, memory.pruned | Consumers cannot validate emitted topics against contract | Add all 7 P03 event topics to stage_80 section |
| 2 | p03_consolidation.v1.yaml | Missing failure mode for BUS_UNAVAILABLE | R8 has circuit breaker but no contract-defined recovery | Add BUS_UNAVAILABLE failure mode with retry policy |
| 3 | core.event_emitter.v1.yaml | Module contract is P02-specific; no P03-specific emitter contract | P03 EventEmitter has different topics and behavior than P02 | Create consolidation.emission.v1.yaml module contract for P03 R8 |
| 4 | p03_consolidation.v1.yaml | Missing side_effects for st_learning_queue and st_offsets | R8 writes to 3 tables but contract only mentions st_outbox | Add st_learning_queue.write and st_offsets.write to side_effects |
| 5 | No contract | No dedicated P03 event schema contracts | Event payloads defined only in code; no validation schemas | Create JSON schemas for each P03 event topic payload |

### 11.3 Algorithm Gaps

| # | Gap | Location | Impact | Recommendation |
| - | --- | -------- | ------ | -------------- |
| 1 | Circuit breaker has no half-open state | emitter.py:475 | After timeout, circuit resets fully -- single success resets to 0 failures (no gradual recovery) | Add half-open state: allow one probe request, then decide based on result |
| 2 | Gap driver inconsistency | gap_emitter.py module:349 vs pipeline:423 | Module uses driver="p06", pipeline uses driver="p03" -- downstream routing may differ | Align to single driver value (likely "p03" since P03 owns emission) |
| 3 | Duplicate dedup logic | gap_emitter.py (both levels) | Module does in-memory MD5 dedup; P03GapEmitter does DB dedup -- both run for each gap | Consolidate: use in-memory for cycle-local, DB for cross-cycle, not both sequentially |
| 4 | Offset calculation fragile | r8_event_emitter.py:548 | ULID base32 parsing via int(max_event_id[:10], 32) may fail on non-ULID IDs | Add explicit ULID validation; consider using the OffsetManager pattern |
| 5 | No per-topic circuit breaker | emitter.py:475 | Single circuit breaker for all topics -- one failing topic blocks all | Consider per-topic circuit breakers or per-topic error tracking |

### 11.4 Architecture Gaps

| # | Gap | Impact | Recommendation |
| - | --- | ------ | -------------- |
| 1 | Dual emission paths (M5 + legacy) add maintenance burden | 609-line file has ~200 lines of legacy code that should be deleted | Remove legacy path once USE_M5_EMITTERS=True is validated in production |
| 2 | No observability for R8 (zero OTel spans) | Cannot trace R8 in distributed tracing | Add OTel spans for r8.phase, r8.emit, r8.gaps, r8.offset |
| 3 | OffsetManager bypassed | R8 loses idempotency checks, DLQ routing, checkpoint coordination | Wire R8._commit_offset to OffsetManager.decide() + commit() |
| 4 | st_learning_queue column mismatch between pipeline and module emitters | Module writes different column set than pipeline emitter | Consolidate to single queue write method |
| 5 | No back-pressure on st_outbox | If outbox publisher falls behind, R8 keeps adding entries without throttle | Add outbox depth check before emission; defer if depth > threshold |

---

## 12. Security & Privacy Audit

### 12.1 Data Classification

| # | Field / Column | Classification | Handling | Retention Policy | Notes |
| - | -------------- | -------------- | -------- | ---------------- | ----- |
| 1 | st_outbox.payload (completion event) | internal | plain | until drained (publisher deletes after delivery) | Contains cycle_id, counts, status -- no PII |
| 2 | st_outbox.payload (action events) | internal | plain | until drained | Contains aggregate counts per action type -- no PII |
| 3 | st_outbox.payload (gap event) | PII-adjacent | plain | until drained | Contains entity_id, candidate_values -- may reference PII entities |
| 4 | st_outbox.payload (insight event) | PII-adjacent | plain | until drained | Contains concept IDs, PMI scores, natural_language description -- may reference PII |
| 5 | st_learning_queue.context_json | PII-adjacent | plain | until gap expires (7 days default) | Contains candidate_values, original_context -- may contain entity names |
| 6 | st_learning_queue.entity_id | PII-adjacent | plain | until gap expires | Entity ID may map to person name in st_kg_dom |
| 7 | st_offsets.subscriber_id | internal | plain | indefinite | Fixed string "p03" -- no PII |
| 8 | st_offsets.offset | internal | plain | indefinite | Integer watermark -- no PII |

### 12.2 Capability Boundaries

| # | Operation | Required Capability | Enforced? | Enforcement Location | Gap |
| - | --------- | ------------------- | --------- | -------------------- | --- |
| 1 | Write to st_outbox | st_outbox.write (per contract) | no | N/A | No capability check; any module with UoW can stage outbox entries |
| 2 | Write to st_learning_queue | st_learning_queue.write | no | N/A | No capability check on gap persistence |
| 3 | Write to st_offsets | st_offsets.write | no | N/A | No capability check on offset commit |
| 4 | Read st_learning_queue (dedup) | st_learning_queue.read | no | N/A | No capability check on dedup query |

> R8 has zero capability enforcement. All operations rely on UoW access control only.
> Capability checks will be added when K0 capability system is implemented.

### 12.3 Input Validation & Sanitization

| # | Input Source | Validation Applied | Sanitization Applied | Injection Risk | Notes |
| - | ----------- | ------------------ | -------------------- | -------------- | ----- |
| 1 | P03BatchEnvelope (from runner) | Type check (dataclass fields) | none | none | Structured data from trusted P03 runner, not user input |
| 2 | GapCandidate fields | GapType.from_string() validates gap_type | none | none | Invalid types fall back to AMBIGUOUS_ENTITY |
| 3 | Gap context_json | json.loads with try/except JSONDecodeError | Falls back to {} on parse error | none | Already-serialized JSON from R4 |
| 4 | Event payloads | json.dumps serialization | none | none | All payloads are Python dicts serialized to JSON bytes |
| 5 | Offset value | ULID base32 parse with ValueError try/except | Falls back to hash() | none | Non-ULID IDs handled gracefully |

> Overall injection risk: None. R8 writes only to st_outbox (via UoW staging API), st_learning_queue
> (parameterized SQL), and st_offsets (via UoW API). No user input reaches R8 directly.

---

## 13. Enhancement Proposals

### 13.1 Proposed Epics

| Epic ID | Title | Scope Summary | Estimated Files | Priority | Dependencies | Issue Count |
| ------- | ----- | ------------- | --------------- | -------- | ------------ | ----------- |
| 5.09.1 | R8 M5 Emitter Activation | Set USE_M5_EMITTERS=True, remove legacy path, wire to OffsetManager | 0 NEW, 3 MOD, 1 DELETE | P1 | none | 3 |
| 5.09.2 | R8 Contract Alignment | Add missing event topics, failure modes, side_effects to contracts; create P03 event schemas | 5 NEW, 2 MOD | P1 | none | 3 |
| 5.09.3 | R8 Observability Instrumentation | Add OTel spans, emission latency histograms, circuit breaker gauge, offset commit metrics | 0 NEW, 4 MOD | P2 | none | 4 |
| 5.09.4 | R8 Gap Emitter Consolidation | Merge duplicated constants, align driver field, consolidate dedup logic, batch dedup queries | 0 NEW, 3 MOD | P2 | none | 3 |
| 5.09.5 | R8 Circuit Breaker Enhancement | Add half-open state, per-topic error tracking, circuit state metric | 0 NEW, 1 MOD | P2 | 5.09.3 | 2 |

### 13.2 Epic Detail

---

#### Epic 5.09.1 -- R8 M5 Emitter Activation

**Summary**: Activate M5 emitters as default path, remove legacy inline emission, wire offset commit to OffsetManager.

**Problem**: USE_M5_EMITTERS=False means the M5 EventEmitter and GapEmitterModule are never exercised in production. ~200 lines of legacy code remain. R8 bypasses OffsetManager, losing idempotency checks and DLQ routing.

**Solution**: Set USE_M5_EMITTERS=True, validate via integration tests, delete legacy methods, wire _commit_offset to OffsetManager.

##### Inputs

| # | Input | Type | Source | Validation |
| - | ----- | ---- | ------ | ---------- |
| 1 | P03BatchEnvelope | dataclass | P03 runner | Non-null, all phases complete |

##### Outputs

| # | Output | Type | Consumer | Guarantees |
| - | ------ | ---- | -------- | ---------- |
| 1 | Events in st_outbox | OutboxEntry rows | Outbox publisher | Same topics as before, using M5 emitter path |
| 2 | Offset in st_offsets | Offset row | R0 batch selector | Committed via OffsetManager with idempotency check |

##### Algorithm Changes

| # | Algorithm | Change Type | Before | After | Rationale |
| - | --------- | ----------- | ------ | ----- | --------- |
| 1 | M5/Legacy dispatch | remove | Branch on USE_M5_EMITTERS | Always use M5 path | Legacy path adds maintenance burden |
| 2 | Offset commit | modify | Direct uow.upsert_offset() | OffsetManager.decide() + commit() | Gains idempotency checks and DLQ routing |

##### Config Changes

| # | Key / Variable / Flag | Change | Old Value | New Value | Type | Notes |
| - | --------------------- | ------ | --------- | --------- | ---- | ----- |
| 1 | USE_M5_EMITTERS | remove | False | N/A (always True) | bool | Flag no longer needed |

##### Contract Changes

| # | Contract File | Change | Section | Details |
| - | ------------- | ------ | ------- | ------- |
| N/A | No contract changes | N/A | N/A | Internal implementation change |

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
| N/A | No topic changes | N/A | N/A | Same events emitted via different code path |

##### Test Plan

| # | Test File | Test Name | Type | What It Proves | Priority |
| - | --------- | --------- | ---- | -------------- | -------- |
| 1 | test_r8_m5_wiring.py | test_m5_path_default | integration | M5 path runs by default without explicit flag override | P0 |
| 2 | test_r8_m5_wiring.py | test_offset_via_offset_manager | integration | Offset committed via OffsetManager with idempotency check | P0 |
| 3 | test_p03_r8_event_emitter.py | (remove legacy tests) | cleanup | Legacy test cases removed or migrated to M5 path | P1 |

##### Risks

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | M5 emitters have untested edge cases in production | low | med | Run parallel with legacy (both paths emit to separate topics) for 1 cycle before cutover |
| 2 | OffsetManager integration introduces new failure modes | low | med | OffsetManager has extensive tests (test_p03_offset_manager.py, 850+ lines) |

##### Acceptance Criteria

- [ ] Given default R8 configuration, when R8 runs, then M5 emitters are used (no legacy code path)
- [ ] Given successful R8 cycle, when offset is committed, then OffsetManager.decide() returns COMMIT action
- [ ] Given all legacy tests, when migrated to M5 path, then all 140 tests pass

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.09.1.1 | Set USE_M5_EMITTERS=True as default | Flip flag, verify all tests pass | S | none | All 140 R8 tests pass with M5 path |
| 5.09.1.2 | Wire offset to OffsetManager | Replace direct upsert with OffsetManager.decide()+commit() | M | 5.09.1.1 | Offset committed with idempotency and DLQ routing |
| 5.09.1.3 | Delete legacy emission methods | Remove _run_legacy, _build_completion_payload, _stage_completion_event, _process_gaps, legacy gap methods | M | 5.09.1.1 | r8_event_emitter.py reduced by ~200 lines |

---

#### Epic 5.09.2 -- R8 Contract Alignment

**Summary**: Fix contract drift between code and YAML contracts. Add missing event topics, failure modes, side_effects, and create event payload schemas.

**Problem**: 4 of 8 event topics emitted by R8 are not in the pipeline contract. No dedicated P03 emitter module contract exists. No JSON schemas validate event payloads. Side_effects list is incomplete.

**Solution**: Update p03_consolidation.v1.yaml stage_80 section, create consolidation.emission.v1.yaml module contract, create JSON schemas for all P03 event payloads.

##### Inputs

| # | Input | Type | Source | Validation |
| - | ----- | ---- | ------ | ---------- |
| 1 | Current event payloads | code analysis | emitter.py, gap_emitter.py | Compare code to contract |

##### Outputs

| # | Output | Type | Consumer | Guarantees |
| - | ------ | ---- | -------- | ---------- |
| 1 | Updated pipeline contract | YAML | All P03 consumers | All 8 topics listed with schemas |
| 2 | New module contract | YAML | P03 governance | Accurate side_effects and failure_modes |
| 3 | Event payload schemas | JSON Schema | Runtime validation (future) | Formal schema for each topic |

##### Algorithm Changes

| # | Algorithm | Change Type | Before | After | Rationale |
| - | --------- | ----------- | ------ | ----- | --------- |
| N/A | No algorithm changes | N/A | N/A | N/A | Contract-only epic |

##### Config Changes

| # | Key / Variable / Flag | Change | Old Value | New Value | Type | Notes |
| - | --------------------- | ------ | --------- | --------- | ---- | ----- |
| N/A | No config changes | N/A | N/A | N/A | N/A | N/A |

##### Contract Changes

| # | Contract File | Change | Section | Details |
| - | ------------- | ------ | ------- | ------- |
| 1 | p03_consolidation.v1.yaml | modify | stage_80_event_emitter | Add all 8 event topics; fix "discovered" to "detected"; add BUS_UNAVAILABLE failure mode |
| 2 | p03_consolidation.v1.yaml | modify | side_effects | Add st_learning_queue.write, st_offsets.write |
| 3 | consolidation.emission.v1.yaml | create | (new file) | P03-specific emitter module contract with 8 output topics, 3 side_effects, 4 failure_modes |

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
| 1 | p03.truth.reinforced.v1 | add to contract | New JSON schema | Consumers can validate payload |
| 2 | p03.truth.created.v1 | add to contract | New JSON schema | Consumers can validate payload |
| 3 | p03.truth.evolved.v1 | add to contract | New JSON schema | Consumers can validate payload |
| 4 | p03.memory.pruned.v1 | add to contract | New JSON schema | Consumers can validate payload |
| 5 | p03.insight.generated.v1 | add to contract | New JSON schema | Consumers can validate payload |

##### Test Plan

| # | Test File | Test Name | Type | What It Proves | Priority |
| - | --------- | --------- | ---- | -------------- | -------- |
| 1 | tests/k0/contracts/test_p03_contract_topics.py | test_all_emitted_topics_in_contract | unit | Every EventTopic enum value appears in pipeline contract | P0 |
| 2 | tests/k0/contracts/test_p03_event_schemas.py | test_completion_payload_matches_schema | unit | Completion payload validates against JSON schema | P1 |

##### Risks

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | Downstream consumers may not expect newly-documented topics | low | low | Topics already emitted; contract is catching up to code |

##### Acceptance Criteria

- [ ] Given the pipeline contract, when all 8 event topics are listed, then contract matches code exactly
- [ ] Given a completion payload, when validated against schema, then validation passes
- [ ] Given the module contract, when side_effects are checked, then st_outbox, st_learning_queue, st_offsets all listed

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.09.2.1 | Update pipeline contract stage_80 topics and failure modes | Modify p03_consolidation.v1.yaml | S | none | All 8 topics listed; BUS_UNAVAILABLE added |
| 5.09.2.2 | Create P03 emitter module contract | Create consolidation.emission.v1.yaml | M | none | Module contract with correct I/O, side_effects, failure_modes |
| 5.09.2.3 | Create event payload JSON schemas | Create 8 JSON schema files in k0/contracts/schemas/ | M | none | Each P03 event topic has a corresponding schema file |

---

## 14. Risk Register

| # | Risk ID | Risk | Category | Likelihood | Impact | Risk Score | Mitigation | Owner | Status |
| - | ------- | ---- | -------- | ---------- | ------ | ---------- | ---------- | ----- | ------ |
| 1 | R-001 | Legacy emission path diverges from M5 path over time | technical | high | med | high | Activate M5 path (Epic 5.09.1), delete legacy code | dev-lead | open |
| 2 | R-002 | Contract drift: 4+ topics emitted but undocumented in YAML | compliance | high | med | high | Epic 5.09.2: add all topics to contract | dev-lead | open |
| 3 | R-003 | OffsetManager bypass loses idempotency and DLQ routing | technical | med | high | high | Wire R8 to OffsetManager (Epic 5.09.1.2) | dev-lead | open |
| 4 | R-004 | Circuit breaker blocks all events when one topic fails | technical | low | high | medium | Add per-topic error tracking (Epic 5.09.5) | dev-lead | open |
| 5 | R-005 | Gap dedup DB queries create sequential bottleneck | performance | med | low | low | Batch dedup or use in-memory only (Epic 5.09.4) | dev-lead | open |
| 6 | R-006 | st_learning_queue grows unbounded if P06 is slow | performance | med | med | medium | Add expiry cleanup job or retention policy | dev-lead | open |
| 7 | R-007 | st_outbox accumulates if background publisher is behind | performance | low | med | low | Monitor outbox depth; add back-pressure mechanism | dev-lead | open |
| 8 | R-008 | Gap driver inconsistency (p03 vs p06) causes routing errors | technical | med | med | medium | Align to single driver value (Epic 5.09.4) | dev-lead | open |
| 9 | R-009 | Offset ULID parsing fails on non-ULID event IDs | technical | low | med | low | Add ULID validation with graceful fallback | dev-lead | accepted |

---

## 15. Open Questions

| # | Question | Context | Blocking? | Answer | Status | Answered By | Date |
| - | -------- | ------- | --------- | ------ | ------ | ----------- | ---- |
| 1 | Should USE_M5_EMITTERS be flipped to True immediately or run a parallel emission period? | M5 emitters are fully tested but never exercised in production. Risk of unknown edge cases. | yes | | open | | |
| 2 | Should the gap outbox driver be "p03" or "p06"? | Module-level gap_emitter uses driver="p06" (target pipeline); pipeline-level uses driver="p03" (source pipeline). Both work but route differently. | yes | | open | | |
| 3 | Should R8 use OffsetManager or continue with direct upsert? | OffsetManager (674 lines) provides idempotency checks, DLQ routing, checkpoint coordination. R8 currently bypasses all of this. | no | | open | | |
| 4 | Should p03.insight.generated.v1 be added to the pipeline contract or removed from code? | Issue 8.1.13 added the topic to EventEmitter but not to the contract. Is this topic officially part of P03? | yes | | open | | |
| 5 | What is the correct topic name: "detected" or "discovered"? | Contract says p03.pattern.discovered.v1; code says p03.pattern.detected.v1. One must change. | yes | | open | | |
| 6 | Should action events be per-record (fine-grained) or aggregate (current)? | Current: one event with count=N. Alternative: N events with individual record details. Aggregate is simpler but limits downstream analytics. | no | | open | | |
| 7 | What is the retention policy for st_learning_queue? | Gaps have ttl_hours=168 (7 days) but no cleanup job exists. expired gaps accumulate indefinitely. | no | | open | | |

---

## Appendix A: Glossary

| Term | Definition |
| ---- | ---------- |
| Outbox Pattern | Transactional outbox: events staged in st_outbox within the same DB transaction, then published asynchronously by background publisher |
| Circuit Breaker | Fault tolerance pattern: after N failures, block requests for timeout period to prevent cascade |
| Half-Open State | Circuit breaker state where a single probe request is allowed to determine if the fault has cleared |
| Fingerprint | Idempotency key stored in st_outbox to prevent duplicate event emission (ON CONFLICT DO NOTHING) |
| GAP_PRIORITY_MAP | Severity-based priority scoring: CONTRADICTION=100, AMBIGUOUS_ENTITY=80, STRUCTURAL_HOLE=70, CONCEPT_DRIFT=60, LOW_CONFIDENCE_EDGE=50, STALE_ANCHOR=40, MISSING_ATTRIBUTE=30 |
| DLQ | Dead Letter Queue -- destination for unprocessable messages that cannot be retried |
| Offset | High watermark integer tracking the latest processed event; used for exactly-once semantics |
| ULID | Universally Unique Lexicographically Sortable Identifier -- first 10 chars encode timestamp in base32 |
| UoW | Unit of Work -- transaction pattern grouping all DB writes into a single atomic commit |
| Action Breakdown | Aggregate counts of reconciliation decisions: CREATE, REINFORCE, EVOLVE, PRUNE |
| ReconciliationSummary | R6 output summarizing all staging decisions: event counts, action breakdown, layer write counts |
| P06 | Pipeline 06: Active Learning -- consumes gaps from st_learning_queue, generates clarification questions |
| P08 | Pipeline 08: Embedding Management -- triggered by p03.consolidation.complete.v1 for integrity checks |

## Appendix B: References

| # | Document | Path / URL | Relevance |
| - | -------- | ---------- | --------- |
| 1 | P03 Consolidation Dossier v2 | docs/pipelines/P03_consolidation_dossier_v2.md | Pipeline scope, phase specs, R8 event emission (section 4.9) |
| 2 | ADR-K003 pgvector Migration | docs/architecture/decisions-K0/adr-k003-v2-pgvector-migration.md | FAISS eliminated; all vectors via pgvector |
| 3 | M5 Master Implementation Skeleton (Epic 5.9) | docs/plans/MASTER_IMPLEMENTATION_SKELETON.md (lines 5616-5680) | R8 component inventory, I/O contract, known issues |
| 4 | P03 Pipeline Contract v1 | k0/contracts/pipelines/p03_consolidation.v1.yaml (stage_80) | R8 stage definition, config, topics |
| 5 | Core Event Emitter Module Contract v1 | k0/contracts/modules/core.event_emitter.v1.yaml | P02 event emitter contract (reused for stage config reference) |
| 6 | R8 Event Emitter Deep Dive | docs/pipelines/R8_EVENT_EMITTER_DEEP_DIVE.md | Detailed R8 architecture analysis |
| 7 | R7 Truth Writer Discovery | docs/pipelines/p03_enhancement_discovery/P03_R7_TRUTH_WRITER_DISCOVERY.md | Upstream R7 produces WriteResult consumed by R8 completion payload |
| 8 | R6 Staging Discovery | docs/pipelines/p03_enhancement_discovery/P03_R6_STAGING_DISCOVERY.md | Upstream R6 produces ReconciliationSummary consumed by R8 |
| 9 | Discovery Template | docs/pipelines/p03_enhancement_discovery/DISCOVERY_TEMPLATE.md | 15-section template governing this document format |
