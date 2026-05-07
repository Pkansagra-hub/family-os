# SessionState — Formal API Mapping

> Generated: 2026-04-12 · Scope: Inputs, Outputs, Processing for every SessionState boundary

---

## 1. Entry Points (What Goes IN)

### 1.1 Write API — SessionStateManager.mutate()

Central mutation entry point. All writes flow through this single method.

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `mutate(section, operation, data, estimated_bytes, cognitive_trace_id)` | `section: str`, `operation: str`, `data: Any`, `estimated_bytes: Optional[int]`, `cognitive_trace_id: Optional[str]` | `MutationResult` | DirectWriterAdapter (via IWriterPort) |

**MutationResult** (dataclass):

| Field | Type | Default |
| --- | --- | --- |
| `success` | `bool` | — |
| `section` | `str` | — |
| `operation` | `str` | — |
| `bytes_delta` | `int` | `0` |
| `new_size_bytes` | `int` | `0` |
| `available_bytes` | `int` | `0` |
| `pressure` | `str` | `"NORMAL"` |
| `error` | `Optional[str]` | `None` |
| `reason` | `Optional[str]` | `None` |
| `cognitive_trace_id` | `Optional[str]` | `None` |

Factory methods: `rejected(...)`, `failure(...)`.

**Valid operations** (30 total):

`set`, `append`, `add_turn`, `add_fact`, `create_thread`, `switch_to`, `pause_thread`, `resolve_thread`, `archive_thread`, `update_thread`, `update`, `update_confidence`, `register_agent`, `add_referent`, `push_question`, `pop_question`, `push_topic`, `add_commitment`, `fulfill_commitment`, `cancel_commitment`, `answer`, `request`, `add_compressed`, `add_summarized`, `set_session_summary`, `add_vocabulary`, `clear`, `delete`, `record_turn`, `record_error`, `accept_demoted`

### 1.2 Writer Port — IWriterPort (Mutation Authorization)

External callers go through IWriterPort, not the manager directly.

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `request_mutation(request)` | `MutationRequest` | `MutationResponse` | Concierge (prod), Direct (standalone) |
| `batch_mutations(batch)` | `BatchRequest` | `BatchResult` | Concierge batch writes |
| `validate_writer(writer_id)` | `str` | `WriterAuthorization` | Pre-check |

**MutationRequest** (14 fields):

| Field | Type | Default |
| --- | --- | --- |
| `request_id` | `str` | uuid4() |
| `section` | `str` | — |
| `operation` | `str` | — |
| `data` | `Any` | — |
| `estimated_bytes` | `int` | `0` |
| `writer_id` | `str` | — |
| `cognitive_trace_id` | `str` | — |
| `priority` | `MutationPriority` | `NORMAL` |
| `delegation_chain` | `List[str]` | `[]` |
| `created_at_ms` | `int` | now |
| `timeout_ms` | `int` | `0` |
| `metadata` | `Dict[str, Any]` | `{}` |

**MutationResponse** (13 fields):

| Field | Type | Default |
| --- | --- | --- |
| `request_id` | `str` | — |
| `status` | `MutationStatus` | — |
| `approved` | `bool` | — |
| `new_size_bytes` | `int` | `0` |
| `bytes_delta` | `int` | `0` |
| `available_bytes` | `int` | `0` |
| `section` | `str` | `""` |
| `operation` | `str` | `""` |
| `reason` | `str` | `""` |
| `rejection_category` | `Optional[RejectionCategory]` | `None` |
| `error` | `Optional[str]` | `None` |
| `duration_ms` | `float` | `0.0` |
| `timestamp_ms` | `int` | now |

Factory methods: `approved(...)`, `rejected(...)`, `failed(...)`, `cancelled(...)`.

### 1.3 Read API — SessionStateManager (Lock-Free, <1ms)

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `get_section(name)` | `str` | Section instance | Any component via adapter |
| `get_hot()` | — | `HotTier` (10 sections, 52KB) | Context readers |
| `get_warm()` | — | `WarmTier` (5 sections, 52KB) | Context readers |
| `get_all_section_sizes()` | — | `Dict[str, int]` | Diagnostics |
| `get_local_cold()` | — | `LocalColdTier` | Archive access |
| `get_snapshot()` | — | `SessionSnapshot` | Health, diagnostics |

### 1.4 Lifecycle API — SessionStateManager

| Method | Input | Output | When Called |
| --- | --- | --- | --- |
| `start(restore_if_exists, cognitive_trace_id)` | `bool`, `Optional[str]` | `StartResult` | Kernel P2, session creation |
| `stop(checkpoint_before_stop, cognitive_trace_id)` | `bool`, `Optional[str]` | `StopResult` | Session destruction |
| `checkpoint(cognitive_trace_id)` | `Optional[str]` | `CheckpointResult` | Periodic (30s), manual, pressure |
| `restore(session_id, cognitive_trace_id)` | `str`, `Optional[str]` | `RestoreResult` | Session resume |

### 1.5 Async Wrapper — AsyncSSMBridge

All write/lifecycle methods wrapped via `asyncio.to_thread()`. Reads are synchronous pass-through (lock-free).

| Method | Async? | Delegates To |
| --- | --- | --- |
| `mutate(...)` | ✅ `await asyncio.to_thread` | `_sync.mutate(...)` |
| `start(...)` | ✅ `await asyncio.to_thread` | `_sync.start(...)` |
| `stop(...)` | ✅ `await asyncio.to_thread` | `_sync.stop(...)` |
| `checkpoint(...)` | ✅ `await asyncio.to_thread` | `_sync.checkpoint(...)` |
| `restore(...)` | ✅ `await asyncio.to_thread` | `_sync.restore(...)` |
| `get_section(name)` | ❌ sync | `_sync.get_section(name)` |
| `get_hot()` | ❌ sync | `_sync.get_hot()` |
| `get_snapshot()` | ❌ sync | `_sync.get_snapshot()` |

---

## 2. Exit Points (What Goes OUT)

### 2.1 Port Calls — What SessionState Sends

#### IStoragePort (→ SQLite LOCAL COLD)

| Method | When Called | Input | Output |
| --- | --- | --- | --- |
| `archive(section, data, metadata)` | Eviction, checkpoint | `str`, `bytes` (FlatBuffer), `Dict` (must include session_id) | `ArchiveResult(success, archive_id, size_bytes, duration_ms)` |
| `restore(section, filters)` | Session start, reconstruction | `str`, `Dict` (must include session_id) | `RestoreResult(success, data, archive_id, size_bytes, duration_ms)` |
| `list_archives(session_id)` | Diagnostics | `str` | `List[ArchiveEntry]` |
| `delete(archive_id)` | Pruning | `str` | `bool` |

**Adapters:** `SQLiteStorageAdapter` (prod — WAL mode, 4 tables), `InMemoryStorageAdapter` (test), `BridgeStorageAdapter` (STUB — K0 future).

#### IEventPort (→ Event Bus / Delta Bus)

| Method | When Called | Input | Output |
| --- | --- | --- | --- |
| `emit(event_type, payload)` | Mutation approval/rejection, eviction, emergency, reconstruction | `str` (topic), `Any` (event payload) | `None` (fire-and-forget) |
| `subscribe(event_type, handler)` | Startup | `str`, `Callable` | `str` (subscription_id) |
| `unsubscribe(subscription_id)` | Shutdown | `str` | `bool` |

**Adapters:** `LocalEventAdapter` (prod — in-process dispatch thread, capture mode for tests), `DeltaBusAdapter` (STUB — K1 bus future).

#### ILifecyclePort (→ Lifecycle Management)

| Method | When Called | Input | Output |
| --- | --- | --- | --- |
| `start(restore_if_exists)` | Session creation | `bool` | `StartResult` |
| `stop(checkpoint_before_stop)` | Session destruction | `bool` | `StopResult` |
| `health()` | Health check | — | `HealthStatus` |
| `checkpoint(trigger)` | Periodic, manual, pressure | `CheckpointTrigger` | `CheckpointResult` |

**Adapters:** `StandaloneLifecycle` (prod — self-managed, periodic checkpoint timer), `FabricLifecycleAdapter` (STUB — future).

#### IK0SyncPort (→ K0 Cloud Sync) — OPTIONAL

| Method | When Called | Input | Output |
| --- | --- | --- | --- |
| `sync_to_k0(session_id)` | Post-checkpoint (future) | `str` | `SyncResult` |
| `restore_from_k0(session_id)` | Reconstruction fallback | `str` | `RestoreFromK0Result` |
| `get_sync_status(session_id)` | Diagnostics | `str` | `SyncStatus` |
| `cancel_sync(session_id)` | Shutdown | `str` | `bool` |

**Adapters:** `NullSyncPort` (current — always offline), `BridgeSyncAdapter` (STUB — K0 future).

---

## 3. Processing Pipelines (What Gets Processed and How)

### 3.1 Mutation Pipeline — mutate() (7 Steps)

```text
MutationRequest (via IWriterPort)
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 1: WRITER AUTHORIZATION                        │
│  DirectWriterAdapter.validate_writer(writer_id)      │
│  M4 E4.2.4: Block tool:* writers from system sections│
│  Check llm_writable_sections allowlist               │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 2: ESTIMATE BYTES                              │
│  _estimate_bytes(data) → JSON-serialized size        │
│  Fallback: 1024 bytes                                │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 3: PREFLIGHT CHECK (MutationGuard — 5 checks)  │
│  3a. Valid section name (in ALL_SECTIONS)             │
│  3b. Valid operation (in VALID_OPERATIONS)            │
│  3c. Section not locked (eviction/migration)         │
│  3d. Not in emergency mode                           │
│  3e. Capacity: section budget, tier budget, total    │
│      Negative deltas bypass capacity checks          │
│  → Approval(approved, reason, available_kb, tier)    │
└─────────────────────────────────────────────────────┘
  │ (rejected → MutationResult.rejected())
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 4: APPLY MUTATION (RLock guarded)              │
│  _apply_mutation(section, operation, data)            │
│  Dispatches to section via duck-typing:              │
│  set_data, append, add_fact, update, record_turn,    │
│  record_error, accept_demoted, clear, delete, apply  │
│  → actual bytes_delta                                │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 5: UPDATE SIZE TRACKING                        │
│  SizeTracker.update(section, actual_bytes)            │
│  Recalculates tier totals + pressure levels          │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 6: PRESSURE RESPONSE (conditional)             │
│  If WARM pressure ≥ CRITICAL:                        │
│    → EvictionEngine.evict() target 70% utilization   │
│  If HOT pressure ≥ CRITICAL:                         │
│    → MigrationEngine.demote_on_pressure()            │
│      (HOT → WARM, priority-ordered)                  │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 7: RETURN RESULT                               │
│  MutationResult(success, section, operation,         │
│    bytes_delta, new_size_bytes, available_bytes,     │
│    pressure, cognitive_trace_id)                     │
└─────────────────────────────────────────────────────┘
```

### 3.2 Reconstruction Pipeline — ReconstructionSLA.reconstruct()

```text
Session Start / Restore
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 1: TRY LOCAL COLD (SQLite)                     │
│  Per-section restore from st_*_archive tables        │
│  SLA target: <50ms P95                               │
└─────────────────────────────────────────────────────┘
  │ (success → hydrate)
  │ (failure → fallback)
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 2: TRY K0 FALLBACK (optional)                  │
│  IK0SyncPort.restore_from_k0(session_id)             │
│  Timeout: 80ms hard limit                            │
│  SLA target: <100ms P95                              │
│  ⚠ NOT WIRED — NullSyncPort returns failure          │
└─────────────────────────────────────────────────────┘
  │ (success → hydrate)
  │ (failure → fresh start)
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 3: HYDRATE HOT (priority order)                │
│  control → meta → beliefs_active → scoreboard →      │
│  history_active → clarifications → affective_now →   │
│  narrative_active                                     │
│  FlatBuffer deserialization per section               │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 4: HYDRATE WARM (priority order)               │
│  persona → beliefs_history → history_recent →        │
│  telemetry                                            │
│  FlatBuffer deserialization per section               │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 5: SYNC SIZE TRACKER                           │
│  _sync_size_tracker() — read actual get_size_bytes() │
│  from each section, update SizeTracker accounting    │
└─────────────────────────────────────────────────────┘
  │
  ▼
Return ReconstructionResult(source, sections_restored, duration_ms, sla_met)
```

### 3.3 Eviction Pipeline — EvictionEngine.evict()

```text
WARM pressure ≥ CRITICAL
  │
  ▼
Get candidates sorted by eviction priority:
  1. telemetry (prio 1)
  2. artifacts_warm (prio 2)
  3. beliefs_history (prio 2)
  4. history_recent (prio 3)
  5. persona (prio 5)
  │
  ▼
For each candidate (max 10 iterations):
  │
  ├─ Lock section (MutationGuard.lock_section)
  ├─ Get evictable data from section
  ├─ Archive to LOCAL COLD FIRST (must succeed)
  ├─ Remove data from section
  ├─ Update SizeTracker (negative delta)
  ├─ Unlock section
  │
  └─ Check: WARM utilization ≤ 70% target?
       Yes → stop
       No → continue to next candidate
  │
  ▼
Return EvictionResult(sections_evicted, bytes_freed, bytes_archived)
```

### 3.4 Migration Pipeline — MigrationEngine.demote()

```text
HOT pressure ≥ CRITICAL
  │
  ▼
Get demotion candidates by priority:
  1. history_active → history_recent
  2. beliefs_active → beliefs_history
  3. narrative_active → (no target — skipped)
  4. task_artifacts → artifacts_warm
  │
  ▼
For each candidate:
  │
  ├─ Lock source + target sections
  ├─ Get items from source section
  ├─ Transform items:
  │    history turns 11-30: compress (entities/intents/key_phrases only)
  │    history turns 31+: summarize (single sentence, 200 char)
  │    beliefs: direct transfer
  │    artifacts: direct transfer
  ├─ Add items to WARM target section
  ├─ Remove items from HOT source section
  ├─ Update SizeTracker (both sections)
  ├─ Unlock sections
  │
  └─ Check: HOT utilization ≤ 70% target?
       Yes → stop
       No → continue
  │
  ▼
Return MigrationResult(source, target, items_migrated, bytes_freed)
```

### 3.5 Checkpoint Pipeline — SessionStateManager.checkpoint()

```text
Manual / Periodic / Stop trigger
  │
  ▼
Serialize all sections:
  HOT: 10 sections → to_flatbuffer() → base64
  WARM: 5 sections → to_flatbuffer() → base64
  │
  ▼
Build checkpoint payload (V2):
  {
    metadata: SessionSnapshot.to_dict(),
    section_data: { name: base64(flatbuffer_bytes) },
    version: 2
  }
  │
  ▼
Write to LOCAL COLD:
  IStoragePort.archive("checkpoint", json_bytes, {session_id})
  │
  ▼
SLA check: duration_ms < 50ms?
  │
  ▼
Return CheckpointResult(checkpoint_id, size_bytes, duration_ms, sla_met)
```

---

## 4. Section Registry — 15 Sections Across 3 Tiers

### 4.1 HOT Tier (10 sections, 52KB total budget)

| Section | Budget | Evictable | Demotes To | Primary Content |
| --- | --- | --- | --- | --- |
| `control` | 8 KB | NEVER | — | Agent leases, flow state, turn lock, intent, domain, safety band |
| `beliefs_active` | 8 KB | Items demote | `beliefs_history` | SVO facts (50 max), entity refs, mentioned times/locations |
| `scoreboard` | 6 KB | No | — | Referents, QUD stack, salience, topics, commitments |
| `history_active` | 8 KB | Items demote | `history_recent` | Full turns (10 max), typed entries, token tracking |
| `clarifications` | 4 KB | HOT core | — | Pending clarifications (20 max), recent resolved (5) |
| `affective_now` | 4 KB | HOT core | — | Emotion (Russell circumplex), trajectory, recent emotions (5) |
| `narrative_active` | 4 KB | HOT core | — | Thread FSM (1 active + 5 paused), narrative arc position |
| `meta` | 2 KB | NEVER | — | Session identity, lifecycle, memory usage, version |
| `task_state` | 4 KB | NEVER | — | Active tasks (20 max), HIL recovery data, progress tracking |
| `task_artifacts` | 4 KB | Demotes | `artifacts_warm` | Task outputs (30 max), presented-at tracking |

### 4.2 WARM Tier (5 sections, 52KB actual / 48KB config budget)

| Section | Budget | Eviction Prio | Accepts From | Primary Content |
| --- | --- | --- | --- | --- |
| `telemetry` | 8 KB | 1 (first) | — | Token/cost/latency/error metrics, turn timings (20 rolling) |
| `artifacts_warm` | 8 KB | 2 | `task_artifacts` | Demoted artifacts (50 max), LRU eviction |
| `beliefs_history` | 12 KB | 2 | `beliefs_active` | Archived facts (100 max), LRU scoring, promotion candidates |
| `history_recent` | 16 KB | 3 | `history_active` | Compressed turns (20), summarized turns (10), session summary |
| `persona` | 8 KB | 5 (last) | — | Personality profile, prosody, vocabulary, response preferences |

### 4.3 LOCAL COLD Tier (SQLite — unbounded)

| Table | Archives From | Extra Columns |
| --- | --- | --- |
| `st_session_checkpoints` | Full session snapshots | — |
| `st_beliefs_archive` | beliefs_history eviction | `turn_id` |
| `st_history_archive` | history_recent eviction | `turn_range` |
| `st_narrative_archive` | narrative_active eviction | `thread_id` |
| `st_telemetry_archive` | telemetry eviction | — |
| `st_persona_archive` | persona eviction | — |

---

## 5. Events Published (What Gets Emitted)

### 5.1 Event Types (8)

| Topic | When | Payload Key Fields |
| --- | --- | --- |
| `sessionstate.mutation.requested` | Mutation start | `section, operation, estimated_bytes, writer_id` |
| `sessionstate.mutation.approved` | Mutation success | `section, operation, previous_size_bytes, new_size_bytes, tier_utilization_pct, total_utilization_pct` |
| `sessionstate.mutation.rejected` | Mutation rejected | `section, operation, reason, section_available_bytes, tier_available_bytes, total_available_bytes` |
| `sessionstate.eviction.triggered` | Eviction start | `tier="warm", target_reduction_bytes, pressure_level, candidates` |
| `sessionstate.eviction.completed` | Eviction done | `tier="warm", sections_evicted, bytes_freed, bytes_archived, new_pressure_level, duration_ms` |
| `sessionstate.emergency.activated` | Emergency mode on | `level, total_size_bytes, hot_size_bytes, warm_size_bytes, utilization_pct, writes_blocked` |
| `sessionstate.emergency.resolved` | Emergency mode off | `previous_level, resolution_method, new_utilization_pct, duration_ms` |
| `sessionstate.reconstruction.started` | Session restore start | `source, sections_requested, expected_duration_ms` |

All events include base: `event_id`, `event_type`, `session_id`, `cognitive_trace_id`, `timestamp_ms`.

**Note:** Events emitted via adapter layer (`DirectWriterAdapter` / `LocalEventAdapter`), not directly from manager.mutate().

---

## 6. Consumer Map — Who Reads Which Sections

### 6.1 Fabric Reads (via ISessionStateReader → SessionStateReaderAdapter)

| Section | Read By | Purpose |
| --- | --- | --- |
| `control` | PolicyEngine (SecurityContext) | Safety band check for capability requests |
| `affective_now` | PolicyEngine (AffectiveRouting) | Emotion-aware provider scoring (+0.0–0.2) |
| `meta` | PolicyEngine (CognitiveLoadRouting) | Session context for cognitive scoring (+0.0–0.15) |
| `beliefs_active` | ContextBuilder | Inject active beliefs into ExecutionContext |
| `history_active` | ContextBuilder | Inject conversation history into ExecutionContext |
| `task_state` | ContextBuilder | Inject active tasks into ExecutionContext |
| All HOT+WARM | ContextBuilder.get_snapshot() | Full context for agent prompts |

### 6.2 Planner Reads (via IStateReadPort → PlannerStateAdapter)

| Section | Read By | Purpose |
| --- | --- | --- |
| `control` | ToolCallRouter (state_read tool) | Safety band, active domains for planning context |
| `beliefs_active` | ToolCallRouter (state_read tool) | Known facts for plan constraint derivation |
| `history_active` | ToolCallRouter (state_read tool) | Recent turns for intent understanding |
| `task_state` | ToolCallRouter (state_read tool) | Active tasks for dependency planning |
| `scoreboard` | ToolCallRouter (state_read tool) | Open questions, commitments for plan goals |

### 6.3 Orchestrator Reads (via IStateReadPort → MockStateReadAdapter ⚠)

| Section | Read By | Purpose |
| --- | --- | --- |
| `control` | `_check_safety_band()` | Safety band for pre-execution gate |
| All sections | `get_snapshot()` | Full snapshot sent to Planner as PlanRequest.context |

**⚠ Currently wired to MockStateReadAdapter — always returns empty.**

### 6.4 Concierge Reads (via SSMStateAdapter)

| Section | Read By | Purpose |
| --- | --- | --- |
| `control` | FSM, Turn Engine | Current flow state, agent leases, turn lock, intent, safety |
| `affective_now` | Front LLM prompt | Emotion-aware response generation |
| `scoreboard` | Front LLM prompt | Discourse state, open questions |
| `history_active` | Front LLM prompt | Recent conversation for response context |
| `beliefs_active` | Front LLM prompt | Known facts for grounding |
| `narrative_active` | Front LLM prompt | Thread context for coherent responses |
| `task_state` | Front LLM, HIL coordinator | Active tasks, HIL state |
| `task_artifacts` | Front LLM | Task outputs to present to user |
| `persona` | Front LLM prompt | Personality, vocabulary, response style |
| `meta` | Session management | Session identity, lifecycle |
| `clarifications` | Front LLM, HIL coordinator | Pending clarification requests |
| `telemetry` | Telemetry observer | Performance metrics |

### 6.5 MemoryWriter Reads (via SessionReadAdapter)

| Section | Read By | Purpose |
| --- | --- | --- |
| `beliefs_active` | End-of-turn processing | Facts to persist to K0 long-term memory |
| `history_active` | End-of-turn processing | Turns to compress and archive |

### 6.6 ModelHub Reads (via SessionStateReadAdapter)

| Section | Read By | Purpose |
| --- | --- | --- |
| `meta` | Token budget allocation | Session context for model selection |
| `telemetry` | Cost tracking | Token usage for budget management |

---

## 7. Factory & Initialization

### 7.1 Factory Modes

| Mode | Method | Use | Key Difference |
| --- | --- | --- | --- |
| `create_standalone()` | SQLite + LocalEvent + DirectWriter + StandaloneLifecycle | Local dev, CLI | `db_path=~/.familyos/k1/sessionstate.db`, 30s checkpoint |
| `create_for_testing()` | InMemory + LocalEvent(capture) + DirectWriter("test") + StandaloneLifecycle(testing) | Unit tests | No disk I/O, event capture, no periodic checkpoint |
| `create_with_ports()` | Full port injection | Kernel P2, integration | Validates ports with isinstance, NO auto bind_manager |

### 7.2 Two-Phase Construction Pattern

```text
Phase 1: Create SSM with unbound adapters
  SessionStateManager(session_id, storage, events, writer, lifecycle)

Phase 2: Post-bind adapters to manager
  writer_adapter.bind_manager(ssm, ssm.mutation_guard)
  lifecycle_adapter.bind_manager(ssm)
```

Breaks circular dependency: adapter needs manager, manager needs adapter.

### 7.3 Kernel P2 Wiring (from kernel/service.py)

```python
ss_storage   = SQLiteStorageAdapter(db_path=config.sessionstate_db_path)
ss_events    = LocalEventAdapter(capture_mode=False)
ss_writer    = DirectWriterAdapter(writer_id="direct")
ss_lifecycle = StandaloneLifecycle()

ssm = SessionStateFactory.create_with_ports(
    session_id=session_id,
    storage=ss_storage,
    events=ss_events,
    writer=ss_writer,
    lifecycle=ss_lifecycle,
    k0_sync=None,
)

ss_writer.bind_manager(ssm, ssm.mutation_guard)
ss_lifecycle.bind_manager(ssm)
ssm.start()
async_ssm = AsyncSSMBridge(ssm)
```

### 7.4 Internal Construction Order (inside SessionStateManager.**init**)

```text
Step 1: Store ports, init state (ManagerState.CREATED), RLock, counters
Step 2: SizeTracker() → MutationGuard(size_tracker)
Step 3: LocalColdArchive() (or injected)
Step 4: HotTier(session_id) → WarmTier(session_id, local_cold) → LocalColdTier(storage)
Step 5: EvictionEngine(size_tracker, local_cold, mutation_guard, session_id)
Step 6: MigrationEngine(size_tracker, mutation_guard, session_id)
```

### 7.5 Shutdown Sequence

```text
SessionState.stop():
  1. Transition RUNNING → STOPPING
  2. Cancel periodic checkpoint timer (if StandaloneLifecycle)
  3. Final checkpoint to LOCAL COLD (if checkpoint_before_stop=True)
  4. Transition STOPPING → STOPPED
```

---

## 8. Adapter Translations (Port ↔ Infrastructure)

| Adapter | Port | Wraps | Key Translation |
| --- | --- | --- | --- |
| `DirectWriterAdapter` | `IWriterPort` | SSM (post-bound) | `request_mutation(MutationRequest)` → check auth → check tool:* block → `MutationGuard.preflight()` → `manager.mutate()` → `MutationResponse`. Tracks stats. |
| `LocalEventAdapter` | `IEventPort` | In-process queue | `emit(type, payload)` → queue → background daemon dispatch thread → registered handlers. Capture mode for test assertions. |
| `SQLiteStorageAdapter` | `IStoragePort` | SQLite (WAL) | Section → table mapping. `archive()` → INSERT. `restore()` → SELECT (most recent by session_id). 4 tables + indexes. SLA ≤50ms. |
| `InMemoryStorageAdapter` | `IStoragePort` | Dict | Dict-based. UUID keys. Sorted by created_at for restore. Test-only. |
| `StandaloneLifecycle` | `ILifecyclePort` | SSM (post-bound) | FSM state machine (CREATED→RUNNING→STOPPED). Periodic checkpoint on daemon thread. `health()` reads SizeTracker pressure. |
| `NullSyncPort` | `IK0SyncPort` | Nothing | All methods return offline/failure. `is_available=False`. |
| `SessionStateReaderAdapter` | `ISessionStateReader` (Fabric port) | SSM | `read_section(session_id, section)` → `ssm.get_section(name)`. Pre-bound to session_id. |
| `SSMStateAdapter` | Concierge state port | SSM | Full section access. Reads HOT+WARM sections for Concierge FSM and LLM prompts. |
| `SessionReadAdapter` | MemoryWriter read port | SSM | `read_section()` → `ssm.get_section()`. End-of-turn fact/history extraction. |
| `PlannerStateAdapter` | `IStateReadPort` (Planner port) | SSM (⚠ reader=None in S6) | `read_sections(sections, trace_id)` → iterate `reader.read_section()`. ⚠ Placeholder. |
| `MHStateReadAdapter` | ModelHub state port | SSM | Session context for token budget + model selection. |

---

## 9. Configuration

| Field | Source | Default | Effect |
| --- | --- | --- | --- |
| `sessionstate_db_path` | Config | `~/.familyos/k1/sessionstate.db` | SQLite LOCAL COLD path |
| `checkpoint_interval_s` | StandaloneLifecycle | `30.0` | Periodic checkpoint interval |
| `HOT_SIZE_LIMIT_BYTES` | Config/SizeTracker | `53248` (52KB) | HOT tier total budget |
| `WARM_SIZE_LIMIT_BYTES` | Config/SizeTracker | `49152` (48KB) | WARM tier total budget — ⚠ sections sum to 52KB |
| `eviction.target_utilization` | Config | `0.70` | Post-eviction target |
| `MAX_HISTORY_ACTIVE_TURNS` | MigrationEngine | `10` | Turns before demotion |
| `COMPRESSION_TURN_THRESHOLD` | MigrationEngine | `30` | Turns before summarization |
| `SLA_LOCAL_COLD_MS` | ReconstructionSLA | `50.0` | Local restore SLA |
| `SLA_K0_FALLBACK_MS` | ReconstructionSLA | `100.0` | K0 fallback restore SLA |
| `K0_TIMEOUT_MS` | ReconstructionSLA | `80.0` | K0 hard timeout |
| `llm_writable_sections` | Config | allowlist | Sections tool:* writers can access |

---

## 10. Thread Safety & Performance

### 10.1 Concurrency Model

| Operation | Guard | Target Latency |
| --- | --- | --- |
| Read (get_section, get_hot, get_warm) | Lock-free | <1ms (HOT <100μs P95, WARM <200μs P95) |
| Write (mutate) | `threading.RLock` | <5ms single, <10ms batch of 5 |
| Preflight check | `MutationGuard._lock` | <50μs P95 |
| Checkpoint | Via mutate lock | <50ms SLA |
| Eviction | `_eviction_in_progress` flag (⚠ not thread-safe) | <50ms per section |
| Migration | `_migration_in_progress` flag (⚠ not thread-safe) | <10ms per section |

### 10.2 AsyncSSMBridge Strategy

Reads: synchronous (lock-free, no thread hop needed).
Writes/lifecycle: `asyncio.to_thread()` (avoids blocking event loop on RLock).

---

## 11. Flags & Known Gaps

| ID | Description | Severity | Impact |
| --- | --- | --- | --- |
| **SS-GAP-01** | WARM sections sum to 52KB but config budget is 48KB | LOW | Per-section budgets overallocated. Sections individually valid but collectively exceed tier. Eviction triggers may be imprecise. |
| **SS-GAP-02** | `narrative_active` in demotion priority but no WARM target | LOW | Demotion candidate list includes it but `get_demotable_sections()` correctly filters it out. Wastes a priority slot. |
| **SS-GAP-03** | 5 production adapters are STUBS (BridgeStorage, BridgeSync, ConciergeWriter, DeltaBus, FabricLifecycle) | MEDIUM | System works with stand-in adapters. Production features (K0 sync, Concierge single-writer, bus-based events, Fabric lifecycle coordination) deferred. |
| **SS-GAP-04** | `_eviction_in_progress` and `_migration_in_progress` are boolean flags, not thread locks | LOW | Potential race under extreme concurrent eviction triggers. Manager serializes calls, so unlikely in practice. |
| **SS-GAP-05** | Events emitted via adapter layer, not directly from manager.mutate() | LOW | Architecturally intentional. But raw manager usage (testing, debugging) bypasses event emission. |
| **SS-GAP-06** | `K0SyncPort` not wired (`k0_sync=None`) | MEDIUM | Edge-first design is offline-only. No cloud backup/restore. |
| **SS-GAP-07** | HOT docstring says "48KB" but actual budget is 52KB (53,248 bytes) | LOW | Documentation drift. Code is correct. |
