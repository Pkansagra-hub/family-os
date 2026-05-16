# K1 SessionState — WIRING

---

## 1. Construction entry points

`SessionStateFactory` is a pure static factory — three static methods:

| Method | Storage | Events | Writer | Lifecycle | When used |
|---|---|---|---|---|---|
| `create_standalone(session_id?, db_path?, checkpoint_interval_s?)` | `SQLiteStorageAdapter` | `LocalEventAdapter(capture=False)` | `DirectWriterAdapter("direct")` | `StandaloneLifecycle(30s)` | CLI, dev, single-process prod |
| `create_for_testing(session_id?)` | `InMemoryStorageAdapter` | `LocalEventAdapter(capture=True)` | `DirectWriterAdapter("test")` | `StandaloneLifecycle(no checkpoint)` | Unit/integration tests |
| `create_with_ports(session_id, storage, events, writer, lifecycle, k0_sync?)` | caller-supplied | caller-supplied | caller-supplied | caller-supplied | Production (Kernel-wired) |

---

## 2. Two-phase bind pattern

`SessionStateManager` and `DirectWriterAdapter`/`StandaloneLifecycle` have a circular
dependency (writer needs the manager to apply mutations; manager needs the writer as
its write port). This is resolved by a two-phase bind:

```
Phase 1: Construct all components (manager gets all ports as non-None)

    storage   = SQLiteStorageAdapter(db_path)
    events    = LocalEventAdapter()
    guard     = MutationGuard(size_tracker)        ← constructed inside manager.__init__
    writer    = DirectWriterAdapter()              ← no manager yet
    lifecycle = StandaloneLifecycle()              ← no manager yet

    manager = SessionStateManager(
        session_id=session_id,
        storage_port=storage,
        event_port=events,
        writer_port=writer,
        lifecycle_port=lifecycle,
        local_cold_archive=LocalColdArchive(db_path),
        config=config,
    )
    # At this point writer._manager is None, lifecycle._manager is None

Phase 2: Bind back-references

    writer.bind_manager(manager, manager.mutation_guard)
    lifecycle.bind_manager(manager)
```

`create_with_ports()` validates port types via `PortProtocolError` (isinstance check against ABC).

`DirectWriterAdapter.request_mutation()` is only valid after Phase 2 binding and
after `SessionStateManager.start()` has moved the manager to RUNNING. Calls made
while the writer is unbound or while the manager is pre-start/stopped raise
`LifecycleError` instead of falling through to guard or mutation logic.

---

## 3. `SessionStateManager.__init__` — internal construction

```
1. self._session_id = session_id
2. self._config = config or SessionStateConfig()
3. self._size_tracker = SizeTracker(config)
4. self._mutation_guard = MutationGuard(size_tracker, config)
5. self._hot = HotTier(config)               ← constructs 10 section objects
6. self._warm = WarmTier(config)             ← constructs 5 section objects
7. self._local_cold = LocalColdArchive(local_cold_archive)
8. self._eviction_engine = EvictionEngine(
       size_tracker, mutation_guard, local_cold_archive,
       SectionDataAdapter(hot, warm),   ← eviction data provider
       config
   )
9. self._migration_engine = MigrationEngine(
       size_tracker, mutation_guard,
       SectionDataAdapter(hot, warm),   ← migration data provider
       config
   )
10. self._reconstruction = ReconstructionSLA(
        local_cold_archive, k0_sync_port, hot, warm,
        deserializer=self._deserialize_section, config
    )
11. self._write_lock = threading.RLock()
12. self._state = ManagerState.CREATED
13. Store storage_port, event_port, writer_port, lifecycle_port
```

`SectionDataAdapter` implements both `IEvictionSectionProvider` and
`IMigrationSectionProvider` — it routes get/set calls to the correct tier.

---

## 4. Port → adapter mapping (production)

| Port | Adapter class | Wraps | Status |
|---|---|---|---|
| `IStoragePort` | `SQLiteStorageAdapter` | SQLite WAL file | LIVE |
| `IEventPort` | `LocalEventAdapter` | In-process queue + thread | LIVE |
| `IWriterPort` | `DirectWriterAdapter` | `SessionStateManager.mutate()` | LIVE |
| `ILifecyclePort` | `StandaloneLifecycle` | Threading.Timer checkpoint | LIVE |
| `IStoragePort` | `BridgeStorageAdapter` | Bridge + K0 | STUB (MS-2+) |
| `IEventPort` | `DeltaBusAdapter` | K1 DeltaBus | STUB (MS-2+) |
| `IWriterPort` | `ConciergeWriterAdapter` | Concierge factory | STUB (MS-2+) |
| `ILifecyclePort` | `FabricLifecycleAdapter` | Fabric lifecycle | STUB (MS-2+) |
| `IK0SyncPort` | `BridgeSyncAdapter` | K0 cloud | STUB (MS-2+) |
| `IStoragePort` | `InMemoryStorageAdapter` | `Dict` | Test only |

---

## 5. `KernelService` wiring (Issue 2.3.2)

The kernel creates and wires sessionstate per-session:

```python
# k1/kernel/service.py (Issue 2.3.2 wiring)

# 1. Create per-session SSM
manager = SessionStateFactory.create_with_ports(
    session_id=session_id,
    storage=SQLiteStorageAdapter(config.sessionstate_db_path),
    events=LocalEventAdapter(),
    writer=DirectWriterAdapter(writer_id="kernel"),
    lifecycle=StandaloneLifecycle(checkpoint_interval_s=30),
)

# 2. Create async bridge for kernel async call paths
bridge = AsyncSSMBridge(manager)

# 3. Expose to Fabric (read-only)
fabric_reader = SessionStateReaderAdapter(manager)       # k1.fabric.adapters.sessionstate_reader
fabric.set_state_reader(fabric_reader)

# 4. Expose to Model Hub (read-only)
hub_state = SessionStateProdAdapter(manager)             # k1.model_hub.adapters.session_state_prod

# 5. Expose to Planner (read-only)
planner_state = PlannerStateAdapter(manager, session_id) # k1.planner.adapters.session_state_adapter

# 6. Start session
await bridge.start(restore_if_exists=True)
```

`SessionStateProdAdapter` and `PlannerStateAdapter` implement
`IStateReadPort` (model hub) and `IStateReadPort` (planner) respectively — both read-only.
They use a local `_ISessionStateManager` Protocol (duck-typed) to avoid circular imports.

---

## 6. `SQLiteStorageAdapter` schema

File: `~/.familyos/k1/sessionstate.db` (configurable via `SessionStateConfig.storage.default_db_path`)
PRAGMAs: `journal_mode=WAL`, `synchronous=NORMAL`

```sql
CREATE TABLE st_session_checkpoints (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    section     TEXT NOT NULL DEFAULT 'checkpoint',
    data        BLOB NOT NULL,           -- FlatBuffer bytes (or JSON for task_state/task_artifacts)
    size_bytes  INTEGER NOT NULL,
    created_at_ms INTEGER NOT NULL,
    metadata    TEXT                     -- JSON
);
CREATE INDEX idx_checkpoints_session  ON st_session_checkpoints (session_id);
CREATE INDEX idx_checkpoints_created  ON st_session_checkpoints (session_id, created_at_ms);

CREATE TABLE st_beliefs_archive   (id, session_id, section, data, size_bytes, created_at_ms, turn_id, metadata);
CREATE TABLE st_history_archive   (id, session_id, section, data, size_bytes, created_at_ms, turn_id, metadata);
CREATE TABLE st_narrative_archive (id, session_id, section, data, size_bytes, created_at_ms, metadata);
CREATE TABLE st_telemetry_archive (id, session_id, section, data, size_bytes, created_at_ms, metadata);
CREATE TABLE st_persona_archive   (id, session_id, section, data, size_bytes, created_at_ms, metadata);
CREATE TABLE st_artifacts_archive (id, session_id, section, data, size_bytes, created_at_ms, metadata);
```

**Table routing** (`SECTION_TABLE_MAP` in `local_cold.py`):

| Section(s) | Table |
|---|---|
| `beliefs_active`, `beliefs_history` | `st_beliefs_archive` |
| `history_active`, `history_recent` | `st_history_archive` |
| `narrative_active` | `st_narrative_archive` |
| `telemetry` | `st_telemetry_archive` |
| `persona` | `st_persona_archive` |
| `artifacts_warm` | `st_artifacts_archive` |
| checkpoint (all sections serialized together) | `st_session_checkpoints` |

---

## 7. `LocalEventAdapter` internal dispatch

```
emit(event_type, payload):
    if capture_mode: _captured.append((event_type, payload, time.time()))
    _queue.put_nowait((event_type, payload))

Background thread "LocalEventAdapter-Dispatch":
    while running:
        event_type, payload = _queue.get()
        for sub_id, handler in _handlers[event_type]:
            try: handler(payload)
            except: pass   # never propagates to emitter
```

Subscribe returns a `subscription_id: str` (UUID). Unsubscribe removes from `_handlers`.
Thread-safe via `_lock: threading.RLock` on handler registration.

---

## 8. `StandaloneLifecycle` — periodic checkpoint

```
start(restore_if_exists):
    if state != CREATED: raise LifecycleError
    state = STARTING
    if restore_if_exists: manager.restore(session_id)
    _start_periodic_checkpoint()   ← schedules threading.Timer(interval_s)
    state = RUNNING

_start_periodic_checkpoint():
    if interval_s > 0:
        _timer = threading.Timer(interval_s, _on_timer_tick)
        _timer.daemon = True
        _timer.start()

_on_timer_tick():
    manager.checkpoint(...)       ← sync write (acquires _write_lock)
    _start_periodic_checkpoint()  ← reschedule

stop(checkpoint_before_stop):
    if checkpoint_before_stop: manager.checkpoint(...)
    _timer.cancel()
    state = STOPPED
```

Default `checkpoint_interval_s=30`. Testing mode: `checkpoint_interval_s=0` (disabled).

---

## 9. `SectionDataAdapter` — dual-interface provider

`SectionDataAdapter(hot: HotTier, warm: WarmTier)` implements both:
- `IEvictionSectionProvider` — used by `EvictionEngine`
- `IMigrationSectionProvider` — used by `MigrationEngine`

Resolution:
```python
def _resolve(self, section: str) -> Optional[Any]:
    obj = self._hot.get_section(section)
    if obj is None:
        obj = self._warm.get_section(section)
    return obj
```

`_overflow: Dict[str, List[MigrationItem]]` — buffer used by `add_items()` during
migration before the target section's `accept_demoted()` is called.

---

## 10. FlatBuffer serialization

Most sections serialize via `to_flatbuffer() -> bytes` and deserialize via
`from_flatbuffer(data: bytes) -> None`.

**Exception — POC JSON encoding:**
`task_state` and `task_artifacts` use `json.dumps()` instead of FlatBuffer:
```python
def to_flatbuffer(self) -> bytes:
    """Serialize to JSON bytes (POC -- no FlatBuffer schema for task_state)."""
    return json.dumps(self.to_dict()).encode()
```

Generated FlatBuffer bindings are in `k1/sessionstate/generated/flatbuffers/`.
`scripts/compile_flatbuffers.py` regenerates them.

---

## 11. `AsyncSSMBridge` call routing

| Operation | Path | Notes |
|---|---|---|
| `get_section(name)` | Direct pass-through | Lock-free, no thread hop |
| `get_hot()` | Direct pass-through | Lock-free |
| `get_warm()` | Direct pass-through | Lock-free |
| `get_snapshot()` | Direct pass-through | Lock-free; snapshot is frozen |
| `get_all_section_sizes()` | Direct pass-through | Lock-free |
| `mutate(...)` | `await asyncio.to_thread(manager.mutate, ...)` | Offloads blocking RLock |
| `start(...)` | `await asyncio.to_thread(manager.start, ...)` | Offloads blocking |
| `stop(...)` | `await asyncio.to_thread(manager.stop, ...)` | Offloads blocking |
| `checkpoint(...)` | `await asyncio.to_thread(manager.checkpoint, ...)` | Offloads blocking |
| `restore(...)` | `await asyncio.to_thread(manager.restore, ...)` | Offloads blocking |

---

## 12. K1 inter-component dependencies (imports)

| What | Imported by | From |
|---|---|---|
| `SessionStateFactory` | `k1.kernel.service` | `k1.sessionstate.factory` |
| `AsyncSSMBridge` | `k1.kernel.service` | `k1.sessionstate.async_bridge` |
| `SQLiteStorageAdapter`, `LocalEventAdapter`, `DirectWriterAdapter`, `StandaloneLifecycle` | `k1.kernel.service` | `k1.sessionstate.adapters.*` |
| `SessionStateReaderAdapter` | `k1.kernel.service` | `k1.fabric.adapters.sessionstate_reader` |
| `SessionStateProdAdapter` | `k1.kernel.service` | `k1.model_hub.adapters.session_state_prod` |
| `SessionStateReadAdapter` (as PlannerStateAdapter) | `k1.kernel.service` | `k1.planner.adapters.session_state_adapter` |
| `public_types.*` (MutationRequest, BatchRequest, IntentClassification, PrivacyBand, TaskStateEntry, TaskArtifactEntry, TemporalAnchor, MetaSection, etc.) | `k1.concierge` | `k1.sessionstate.public_types` |
| `ISessionStateReader`, `SessionSnapshot` | Fabric components | `k1.fabric.ports.state_reader` |

SessionState does NOT import from: `k1.concierge`, `k1.planner`, `k1.orchestrator`,
`k1.model_hub`, `k1.fabric` (dependency direction is always inward toward sessionstate).
`k1.fabric.adapters.sessionstate_reader` imports from sessionstate, not the other way.

---

## 13. `MutationGuard` valid operations

`VALID_OPERATIONS` is a `frozenset` of ~35 named operation strings. Examples:

```
"add_fact", "update_fact", "remove_fact", "pin_fact",
"push_turn", "update_turn", "set_session_start",
"set_agent_lease", "update_flow_state", "update_turn_lock", "set_privacy_band",
"add_question", "answer_question", "push_topic", "pop_topic", "update_salience",
"add_clarification", "resolve_clarification", "set_blocked",
"set_emotion", "update_intensity", "push_emotion_snapshot",
"set_primary_thread", "archive_thread", "resume_thread",
"add_task", "update_task_status", "prune_task",
"add_artifact", "demote_artifact", "update_artifact_presented",
"add_archived_fact", "evict_fact",
"checkpoint", "restore",
```

Any operation string not in this frozenset → `Approval(approved=False, reason_code=INVALID_OPERATION)`.

---

## 14. `SessionStateConfig` hierarchy

```
SessionStateConfig
├── tiers: TiersConfig
│     hot_budget_bytes=53248, warm_budget_bytes=49152, total=106496
│     per-section budgets (10 HOT + 5 WARM), pressure thresholds
├── eviction: EvictionConfig
│     target_utilization=0.70, min=1024B, max_iterations=10
├── migration: MigrationConfig
│     max_history_active_turns=10, compression_threshold=30
│     target_hot_utilization=0.70
├── thrash: ThrashConfig
│     window_ms=60000, mild/moderate/severe migration+eviction thresholds
├── reconstruction: ReconstructionConfig
│     sla_local_cold_ms=50, sla_k0_ms=100, k0_timeout_ms=80
├── cold: ColdConfig
│     default_max_age_days=30, restore_sla_ms=50
├── storage: StorageConfig
│     default_db_path="~/.familyos/k1/sessionstate.db"
│     checkpoint_interval_s=30, sla_restore_ms=50
└── flatbuffer_overhead_factor: float = 1.1
```
