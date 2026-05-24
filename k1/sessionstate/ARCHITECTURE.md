# SessionState — Architecture Document

> **Epic**: E-0.2 · SessionState Full Code Scan
> **Generated**: 2025-07-14 · MS-0 Phase A
> **Source files**: ~100+ Python modules · 76 test files · 77 FlatBuffer generated types
> **Diagrams**: `architecture_diagrams/k1/sessionstate.mmd`, `sessionstate_internal.mmd`

---

## §1 Port Surface

### 1.1 Port Inventory

SessionState exposes **5 ports**, all implemented as **ABC** (Abstract Base Class) — unlike Bus which uses `Protocol`. ABC choice enforces nominal subtyping; adapters must explicitly inherit.

| # | Port | ABC | File | Abstract Methods | Properties |
|---|------|-----|------|-----------------|------------|
| 1 | `IStoragePort` | `ABC` | `ports/storage.py` | `archive()`, `restore()`, `list_archives()`, `delete()` | `is_available`, `storage_type` |
| 2 | `IEventPort` | `ABC` | `ports/events.py` | `emit()`, `subscribe()`, `unsubscribe()` | `is_connected` |
| 3 | `IWriterPort` | `ABC` | `ports/writer.py` | `request_mutation()`, `batch_mutations()`, `validate_writer()` | `writer_id`, `is_connected` |
| 4 | `ILifecyclePort` | `ABC` | `ports/lifecycle.py` | `start()`, `stop()`, `health()`, `checkpoint()` | `state`, `session_id`, `config`, `started_at_ms`, `checkpoint_count`, `last_checkpoint_ms` |
| 5 | `IK0SyncPort` | `ABC` | `ports/k0_sync.py` | `sync_to_k0()`, `restore_from_k0()`, `get_sync_status()`, `cancel_sync()` | `is_available` |

### 1.2 Port Co-Defined Types

Each port co-defines supporting types used in its method signatures.

**IStoragePort** (`ports/storage.py`):

- `ArchiveResult(success, archive_id, size_bytes, error)`
- `RestoreResult(success, section_data, size_bytes, error)`
- `ArchiveEntry(archive_id, section, archived_at, size_bytes)`

**IEventPort** (`ports/events.py`):

- Default `emit_batch(events: list[tuple[str, Any]]) → None` — loops `emit()` (concrete, overridable)

**IWriterPort** (`ports/writer.py`):

- `MutationRequest(section, operation, data, writer_id, priority, trace_id, expires_at_ms)`
- `MutationResponse(approved, request_id, rejection_reason, rejection_category, applied_at_ms)`
- `BatchRequest(requests: list[MutationRequest], atomic)`
- `BatchResult(success, results: list[MutationResponse], partial_count, error)`
- `WriterAuthorization(writer_id, authorized, scopes: list[str])`
- `MutationPriority` enum: `LOW, NORMAL, HIGH, CRITICAL, EMERGENCY` (5 levels)
- `MutationStatus` enum: `PENDING, APPROVED, REJECTED, EXPIRED, CANCELLED, PARTIAL, ERROR` (7 states)
- `RejectionCategory` enum: `CAPACITY, EMERGENCY, LOCKED, INVALID_SECTION, INVALID_OPERATION, UNAUTHORIZED` (6 reasons)
- Default `cancel_request()`, `get_pending_count()`, `get_stats()` (concrete, overridable)

**ILifecyclePort** (`ports/lifecycle.py`):

- `LifecycleState` enum: `CREATED, STARTING, RUNNING, STOPPING, STOPPED, ERROR` (6 states)
- `CheckpointTrigger` enum: `PERIODIC, MANUAL, PRESSURE, MIGRATION, EVICTION, SHUTDOWN, EMERGENCY` (7 triggers)
- `RestoreSource` enum: `LOCAL_COLD, K0, FRESH, CHECKPOINT` (4 sources)
- `PressureLevel` enum: `NORMAL, ELEVATED, CRITICAL, EMERGENCY` (4 levels)
- `StartResult(success, session_id, restored_from, sections_restored, error)`
- `StopResult(success, checkpointed, sections_archived, error)`
- `HealthStatus(healthy, state, uptime_ms, pressure_level, hot_utilization, warm_utilization, …)`
- `CheckpointResult(success, checkpoint_id, size_bytes, sections_checkpointed, trigger, error)`
- `LifecycleConfig(session_id, db_path, checkpoint_interval_s, max_checkpoint_size, …)`
- `InvalidStateError(Exception)` — raised on illegal state transitions
- Default `request_shutdown()`, `get_uptime_ms()`, `is_running()`, `can_checkpoint()` (concrete)

**IK0SyncPort** (`ports/k0_sync.py`):

- `SyncStatus(is_synced, last_sync_ms, pending_changes, sync_state)`
- `SyncResult(success, synced_sections, bytes_synced, error)`
- `RestoreFromK0Result(success, sections_restored, bytes_restored, error)`
- Also contains `NullSyncPort` implementation (always offline — architectural note: lives in ports/, not adapters/)

### 1.3 Adapter Inventory

| # | Adapter | Port | File | Threading | Notes |
|---|---------|------|------|-----------|-------|
| 1 | `SQLiteStorageAdapter` | `IStoragePort` | `adapters/sqlite_storage.py` | Thread-safe (SQLite WAL) | 4 tables: checkpoints, beliefs_archive, history_archive, narrative_archive. SLA breach warnings at >50ms |
| 2 | `InMemoryStorageAdapter` | `IStoragePort` | `adapters/memory_storage.py` | No locking (test-only) | Dict-based, test-only utilities |
| 3 | `LocalEventAdapter` | `IEventPort` | `adapters/local_events.py` | `RLock` + daemon thread | Queue-based async dispatch. Capture mode for testing (`enable_capture()`, `get_captured_events()`, `drain()`) |
| 4 | `DirectWriterAdapter` | `IWriterPort` | `adapters/direct_writer.py` | `RLock` | Lifecycle guard for bound+RUNNING manager, then expiration→auth→preflight→mutate→stats. Per-turn audit trail. Authorized writer set |
| 5 | `StandaloneLifecycle` | `ILifecyclePort` | `adapters/standalone_lifecycle.py` | Daemon thread (checkpoint timer) | State machine: CREATED→STARTING→RUNNING→STOPPING→STOPPED→ERROR. Context manager support |
| 6 | `NullSyncPort` | `IK0SyncPort` | `ports/k0_sync.py` | None | Always offline, all ops return failure. Lives in ports/ (not adapters/) |

### 1.4 Port Conformance Matrix

| Adapter | Port | Subclass? | All abstracts? | Tested? |
|---------|------|-----------|-----------------|---------|
| `SQLiteStorageAdapter` | `IStoragePort` | ✅ ABC subclass | ✅ 4 methods + 2 properties | ✅ `test_ports.py`, `test_all_ports.py` |
| `InMemoryStorageAdapter` | `IStoragePort` | ✅ ABC subclass | ✅ 4 methods + 2 properties | ✅ `test_ports.py`, `test_adapter_swap.py` |
| `LocalEventAdapter` | `IEventPort` | ✅ ABC subclass | ✅ 3 methods + 1 property | ✅ `test_ports.py`, `test_event_capture.py` |
| `DirectWriterAdapter` | `IWriterPort` | ✅ ABC subclass | ✅ 3 methods + 2 properties | ✅ `test_ports.py` |
| `StandaloneLifecycle` | `ILifecyclePort` | ✅ ABC subclass | ✅ 4 methods + 6 properties | ✅ `test_ports.py`, `test_lifecycle_flow.py` |
| `NullSyncPort` | `IK0SyncPort` | ✅ ABC subclass | ✅ 4 methods + 1 property | ✅ `test_null_sync.py` |

### 1.5 Missing Production Adapters

The following adapters are referenced in architecture diagrams but **do not exist yet**:

| Planned Adapter | Port | Purpose | Blocked By |
|----------------|------|---------|------------|
| `BridgeStorageAdapter` | `IStoragePort` | K0 cloud storage via Bridge | Bridge integration |
| `DeltaBusAdapter` | `IEventPort` | K1 DeltaBus event dispatch | Bus wiring |
| `ConciergeWriterAdapter` | `IWriterPort` | Concierge mutation routing | Concierge wiring |
| `FabricLifecycleAdapter` | `ILifecyclePort` | Fabric-managed lifecycle | Fabric wiring |
| `BridgeSyncAdapter` | `IK0SyncPort` | K0 cloud sync via Bridge | Bridge integration |

---

## §2 Internal Architecture

### 2.1 Tiered Memory Model

SessionState implements a **three-tier memory hierarchy** with strict budget enforcement:

```
┌───────────────────────────────────────────────┐
│           SessionKernel (96KB total)           │
│                                                │
│  ┌──────────────────────────────────────────┐  │
│  │  HOT TIER (52KB budget, 10 sections)     │  │
│  │  ┌────────┐ ┌───────────────┐ ┌────────┐│  │
│  │  │control │ │beliefs_active │ │score-  ││  │
│  │  │ 8KB NE │ │     8KB       │ │board   ││  │
│  │  │        │ │               │ │  6KB   ││  │
│  │  └────────┘ └───────────────┘ └────────┘│  │
│  │  ┌───────────────┐ ┌─────────────┐      │  │
│  │  │history_active │ │clarifications│      │  │
│  │  │     8KB       │ │     4KB      │      │  │
│  │  └───────────────┘ └─────────────┘      │  │
│  │  ┌───────────────┐ ┌──────────────┐┌───┐│  │
│  │  │affective_now  │ │narrative_act ││meta││  │
│  │  │     4KB       │ │     4KB      ││2KB││  │
│  │  │               │ │              ││ NE ││  │
│  │  └───────────────┘ └──────────────┘└───┘│  │
│  │  ┌───────────┐ ┌──────────────┐         │  │
│  │  │task_state │ │task_artifacts│         │  │
│  │  │  4KB NE   │ │     4KB      │         │  │
│  │  └───────────┘ └──────────────┘         │  │
│  └──────────────────────────────────────────┘  │
│                                                │
│  ┌──────────────────────────────────────────┐  │
│  │  WARM TIER (48KB budget, 5 sections)     │  │
│  │  ┌───────────────┐ ┌───────────────┐    │  │
│  │  │beliefs_history│ │history_recent │    │  │
│  │  │    12KB       │ │    20KB       │    │  │
│  │  └───────────────┘ └───────────────┘    │  │
│  │  ┌────────┐ ┌──────────┐ ┌────────────┐│  │
│  │  │persona │ │telemetry │ │artifacts_  ││  │
│  │  │  8KB   │ │ 8KB      │ │warm  8KB   ││  │
│  │  │(hi-pri)│ │(1st evict)│ │           ││  │
│  │  └────────┘ └──────────┘ └────────────┘│  │
│  └──────────────────────────────────────────┘  │
│                                                │
│  ┌──────────────────────────────────────────┐  │
│  │  LOCAL COLD (unbounded, SQLite)          │  │
│  │  Archived data + checkpoints + snapshots │  │
│  │  SLA: P95 < 50ms restore                │  │
│  └──────────────────────────────────────────┘  │
└───────────────────────────────────────────────┘
```

**NE** = NEVER EVICT

### 2.2 Section Inventory

#### HOT Tier — 10 Sections (52KB budget)

| Section | Budget | Eviction | Key Data | Operations |
|---------|--------|----------|----------|------------|
| `control` | 8KB | NEVER EVICT | Agent leases, flow state, turn lock, intents, domains, safety | set/update flow, acquire/release lease |
| `beliefs_active` | 8KB | Demotable | Current-turn facts, entities, temporal/spatial context, pinned facts | add_fact, pin, update, demote |
| `scoreboard` | 6KB | Demotable | Discourse referents, QUD stack, salience map, topics, last intent | track referent, push QUD, update salience |
| `history_active` | 8KB | Demotable | Last 10 turns (full fidelity), turn metadata | add_turn (max 10), search, statistics |
| `clarifications` | 4KB | Demotable | Open clarification requests, options, priority, blocking state | request, answer, cancel, expire |
| `affective_now` | 4KB | Demotable | Current emotion, intensity, VAD dimensions, trajectory, empathy | update emotion, track trajectory |
| `narrative_active` | 4KB | Demotable | Active thread, paused threads, narrative arc, thread state | create thread, pause/resume, update arc |
| `meta` | 2KB | NEVER EVICT | Session identity, lifecycle, memory usage, versions, integrity hash | update lifecycle, record usage |
| `task_state` | 4KB | NEVER EVICT | Task FSM state entries | update task state |
| `task_artifacts` | 4KB | Demotable | Task output artifacts | store artifact |

**Note**: Diagram shows 8 HOT sections (48KB). Code has 10 (52KB) — `task_state` and `task_artifacts` were added as M4/M6 extensions.

**Demotion order** (first to demote → last): `history_active` → `beliefs_active` → `narrative_active` → `task_artifacts`

**NEVER_DEMOTE set**: `{control, meta, task_state}` — losing these crashes orchestration.

#### WARM Tier — 5 Sections (48KB budget)

| Section | Budget | Eviction Priority | Key Data |
|---------|--------|--------------------|----------|
| `beliefs_history` | 12KB | 3 | LRU fact archive (max 100 facts), entity index |
| `history_recent` | 20KB | 4 | Turns 11-30 (compressed), turns 31-40 (summarized) |
| `persona` | 8KB | 5 (last evicted) | Personality, voice, vocabulary, response prefs, calibration |
| `telemetry` | 8KB | 1 (first evicted) | Token counts, cost, latency, turn timing, errors |
| `artifacts_warm` | 8KB | 2 | Warm-tier task artifacts |

**Eviction priority order** (first → last): `telemetry(1)` → `artifacts_warm(2)` → `beliefs_history(3)` → `history_recent(4)` → `persona(5)`

#### LOCAL COLD Tier — Unbounded SQLite

- `LocalColdArchive` wraps SQLite with WAL mode
- 4 tables: `checkpoints`, `beliefs_archive`, `history_archive`, `narrative_archive`
- SLA target: P95 < 50ms restore
- Always available (edge-first design — no K0 required)

#### Temporal Grounding

Authoritative temporal grounding lives in `k1.temporal` and persists through the HOT `temporal` section. Control no longer mirrors temporal anchor state.

### 2.3 Kernel Services

#### SessionStateManager (Coordinator)

**File**: `manager.py`
**Constructor**: Takes 4 ports (`IStoragePort`, `IEventPort`, `IWriterPort`, `ILifecyclePort`) + optional `LocalColdArchive`
**Internal wiring**: Creates `SizeTracker` → `MutationGuard` → `LocalColdArchive` → `HotTier` → `WarmTier` → `LocalColdTier` → `EvictionEngine` → `MigrationEngine`

**Concurrency**: `threading.RLock` — single-writer, multi-reader pattern

- Writes acquire lock → estimate size → preflight → apply → update size → check pressure → release
- Reads are lock-free via SizeTracker cached tier totals

**Lifecycle**: `start()` → `stop()` → `checkpoint()` → `restore()`

#### MutationGuard

**File**: `guard.py`
**5-check preflight pipeline**:

1. Valid section? (15 known sections)
2. Valid operation? (37 allowed operations)
3. Section locked? (emergency/per-section locks)
4. Emergency mode? (blocks ALL writes when active)
5. Capacity available? (section budget + tier budget + total budget)

**Constants**: `FLATBUFFER_OVERHEAD_FACTOR = 1.10` (10% overhead for serialization)

#### SizeTracker

**File**: `sizetracker.py`
**Tracks**: 15 sections with per-section size, cached tier totals
**Pressure thresholds**:

| Level | Utilization | Action |
|-------|------------|--------|
| NORMAL | < 80% | None |
| ELEVATED | 80–90% | Advisory logging |
| CRITICAL | 90–95% | Trigger eviction |
| EMERGENCY | > 95% | Block writes |

**NEVER_EVICT sections**: `{control, meta, task_state}` — excluded from eviction calculations

#### EvictionEngine

**File**: `eviction.py`
**Scope**: WARM-only eviction (HOT uses demotion, not eviction)
**Algorithm**: Priority-ordered section eviction
**Invariant**: Always archive to LOCAL COLD before evicting from WARM
**Target**: `TARGET_UTILIZATION_AFTER_EVICTION = 0.70` (evict until 70% utilization)
**Priority order**: telemetry(1) → artifacts_warm(2) → beliefs_history(3) → history_recent(4) → persona(5)

#### MigrationEngine

**File**: `migration.py`
**Scope**: HOT ↔ WARM bidirectional migration
**Pairs**: `beliefs_active` ↔ `beliefs_history`, `history_active` ↔ `history_recent`
**Compression**: Two-stage lossy:

- Turns 11-30: Compressed (key fields retained, details dropped)
- Turns 31+: Summarized (single-sentence summary per turn)

**NEVER demote**: `{control, meta, task_state}`

#### SnapshotAPI

**File**: `snapshot.py`
**Provides**: Health metrics, session/pressure/section/tier snapshots
**Thrash detection**: Rolling 60-second window:

| Severity | Threshold |
|----------|-----------|
| Mild | > 5 migrations |
| Moderate | > 10 migrations |
| Severe | > 20 migrations |

#### ReconstructionSLA

**File**: `reconstruction.py`
**Restore cascade**: LOCAL COLD first → K0 fallback → FRESH (empty state)
**SLA targets**:

| Source | Target |
|--------|--------|
| LOCAL COLD | < 50ms |
| K0 | < 100ms |
| FRESH | < 1ms |

**Hydration priority**: HOT sections first (control → meta → beliefs_active → history_active → ...), then WARM

### 2.4 Event System

#### 8 Event Types

| # | Event | Topic | Emitter |
|---|-------|-------|---------|
| 1 | `MutationRequestedEvent` | `sessionstate.mutation.requested` | Manager (before preflight) |
| 2 | `MutationApprovedEvent` | `sessionstate.mutation.approved` | Manager (after success) |
| 3 | `MutationRejectedEvent` | `sessionstate.mutation.rejected` | Guard (via manager) |
| 4 | `EvictionTriggeredEvent` | `sessionstate.eviction.triggered` | EvictionEngine (via manager) |
| 5 | `EvictionCompletedEvent` | `sessionstate.eviction.completed` | EvictionEngine (via manager) |
| 6 | `EmergencyActivatedEvent` | `sessionstate.emergency.activated` | Manager (>90% utilization) |
| 7 | `EmergencyResolvedEvent` | `sessionstate.emergency.resolved` | Manager (utilization drops) |
| 8 | `ReconstructionStartedEvent` | `sessionstate.reconstruction.started` | ReconstructionSLA (via manager) |

**All events inherit** `BaseEvent(event_id, event_type, session_id, cognitive_trace_id, timestamp_ms)`.

**Factory**: `SessionStateEvents` — static methods constructing events with proper defaults.

**Emission order (mutation flow)**:

```
MutationRequested → MutationApproved | MutationRejected
                  → [EvictionTriggered → EvictionCompleted]  (if pressure)
                  → [EmergencyActivated]                      (if >90%)
```

#### Extended Log Events (8 additional)

The logging layer defines 16 `LogEventType` values — the 8 bus events plus:
`RECONSTRUCTION_COMPLETED`, `LIFECYCLE_STARTED`, `LIFECYCLE_STOPPED`, `CHECKPOINT_CREATED`, `CHECKPOINT_RESTORED`, `MIGRATION_STARTED`, `MIGRATION_COMPLETED`, `PRESSURE_CHANGED`

### 2.5 FlatBuffers Serialization

**Schema source**: 14 `.fbs` files at `k1/contracts/flatbuffers/sessionstate/`
**Generated code**: 77 Python classes at `k1/sessionstate/generated/flatbuffers/K1/SessionState/`
**Namespace**: `K1.SessionState`

**Root type**: `SessionKernel` — 15 fields: `version`, `session_id`, `user_id`, `privacy_band`, `hot` (HotCore), `warm` (WarmTier), `cold` (ColdShadow), `health` (KernelHealth), `created_at`, `last_modified`, `turn_count`, `is_active`, `is_locked`, `is_readonly`, `checksum`

**Key generated types**:

| Category | Types |
|----------|-------|
| **Tier containers** | `HotCore` (8 section refs + budget), `WarmTier` (4 section refs + eviction), `ColdShadow` (archive pointers) |
| **Health** | `KernelHealth` (pressure, size, latency, emergency state) |
| **HOT sections** | `ControlSection`, `BeliefsActiveSection`, `ScoreboardSection`, `HistoryActiveSection`, `ClarificationsSection`, `AffectiveNowSection`, `NarrativeActiveSection`, `MetaSection` |
| **WARM sections** | `BeliefsHistorySection`, `HistoryRecentSection`, `PersonaSection`, `TelemetrySection` |
| **Supporting** | `AgentLease`, `FlowState`, `TurnLock`, `TurnFull`, `CompressedTurn`, `SummarizedTurn`, `ArchivedFact`, `Referent`, `Clarification`, `ConversationThread`, `NarrativeArc`, … (30+ types) |
| **Enums** | `PrivacyBand`, `AgentState`, `FlowPhase`, `QuestionStatus`, `EvictionReason`, `EmergencyMode`, `PressureLevel`, `ArcPosition`, `EmotionTrajectory`, `ThreadState`, … (12+ enums) |
| **Structs** | `Timestamp` (int64 ms), `SizeInfo` (current/max/pressure), `FloatRange` (value/min/max) |

**Serialization flow**:

1. **HOT reads** (<100μs) — zero-copy FlatBuffers; accessors read directly from underlying byte buffer via `__slots__ = ['_tab']`
2. **WARM eviction** — serialize section to FlatBuffers binary → write to `LocalColdArchive` (SQLite) → replace in-memory with `ColdPointer`
3. **Reconstruction** — read FlatBuffers binary from SQLite or K0 → `GetRootAs*` deserialization → hydrate HOT first, then WARM
4. **Checkpoints** — serialize entire `SessionKernel` to binary blob for persistence

**Code vs diagram discrepancy**: Generated FlatBuffers have 8 HOT + 4 WARM section types (12 total). Python code has 10 HOT + 5 WARM sections (15 total). The 3 additions (`task_state`, `task_artifacts`, `artifacts_warm`) were M4/M6 extensions without FlatBuffer schema updates.

### 2.6 Alerting & Observability

**File**: `alerts.yaml`

- 6 alert rules (emergency, high pressure, eviction rate, reconstruction failures, checkpoint overdue, high latency)
- 10 recording rules (aggregated metrics)
- Inhibit chains (emergency suppresses pressure alerts)
- Silence templates

**File**: `metrics.py`

- Prometheus histograms, gauges, counters
- Timing context managers
- Bulk update, thread-safe

**File**: `logging.py`

- `StructuredLogRecord` with JSON formatter
- 16 log event types (8 domain + 8 operational)
- `cognitive_trace_id` propagation across all results

---

## §3 Factory & Configuration

### 3.1 SessionStateFactory

**File**: `factory.py`
Three factory methods:

| Method | Ports Created | Use Case |
|--------|--------------|----------|
| `create_standalone(session_id, db_path, checkpoint_interval_s)` | SQLiteStorage + LocalEvent + DirectWriter + StandaloneLifecycle + LocalColdArchive | Edge/development |
| `create_for_testing(session_id)` | InMemoryStorage + LocalEvent(capture=True) + DirectWriter + StandaloneLifecycle(test config) | Unit tests |
| `create_with_ports(session_id, storage, events, writer, lifecycle, k0_sync)` | All injected externally | Full DI / production |

**Construction pattern**: `create_standalone()` and `create_for_testing()` use **two-phase construction** — manager is created with `None` ports, then private attributes (`_storage_port`, `_event_port`, etc.) are mutated. This is fragile and documented as a known smell.

**Port validation**: `create_with_ports()` validates all ports via `isinstance()` against ABC bases.

### 3.2 Configuration Gaps

| Gap | Impact |
|-----|--------|
| No `create_production()` factory method | Production wiring must use `create_with_ports()` manually |
| No `k1/config/sessionstate.yaml` or env-var config | Hard-coded constants scattered across modules |
| Two-phase construction in standalone/testing factories | Manager created with None ports then mutated — brittle |
| Production adapters don't exist yet | `BridgeStorageAdapter`, `DeltaBusAdapter`, `ConciergeWriterAdapter`, `FabricLifecycleAdapter`, `BridgeSyncAdapter` all unimplemented |
| CLI recreates manager per command | No persistent daemon — each CLI invocation builds from scratch |

### 3.3 CLI Interface

**File**: `cli.py`
10 commands: `start`, `stop`, `status`, `snapshot`, `mutate`, `restore`, `sections`, `checkpoint`, `pressure`, `demo`

---

## §4 Cross-Component Connections

### 4.1 Connection Inventory

| # | Connection | Direction | Mechanism | Adapter File | Status |
|---|-----------|-----------|-----------|-------------|--------|
| 1 | Bus → SessionState | `SessionBusAdapter` → `IEventPort` | ABC subclass (nominal) | `k1/bus/adapters/session_adapter.py` | 🟢 SAFE |
| 2 | SS → Fabric | `SessionStateReaderAdapter` → `ISessionStateReader` | Protocol (structural) | `k1/fabric/adapters/sessionstate_reader.py` | 🟢 SAFE |
| 3 | SS → Concierge | `SSMStateAdapter` → `IStatePort` | Protocol (structural) | `k1/concierge/adapters/ssm_state.py` | 🟢 SAFE |
| 4 | SS → MemoryWriter | `?` → `ISessionReadPort` | Adapter NOT implemented | `k1/memory_writer/adapters/` (missing) | 🟡 CAUTION |
| 5 | SS → Orchestrator | `StateReadAdapter` wraps `ISessionStateReader` | Protocol delegation | `k1/orchestrator/adapters/state_read_adapter.py` | 🟢 SAFE |
| 6 | SS → Planner | `SessionStateReadAdapter` wraps `ISessionStateReader` | Protocol delegation | `k1/planner/adapters/session_state_adapter.py` | 🟢 SAFE |

### 4.2 Connection Details

**Connection 1: Bus → SessionState**

- `SessionBusAdapter(IEventPort)` — explicit ABC subclass
- All 4 abstract methods + 1 property match exactly
- Serialization: `Any → JSON bytes` on emit, reverse on callback
- `import from k1.sessionstate.ports.events import IEventPort` — direct coupling, correct

**Connection 2: SS → Fabric**

- `SessionStateReaderAdapter` duck-types to `ISessionStateReader(Protocol, runtime_checkable)`
- 3 methods match exactly: `read_section()`, `read_sections()`, `get_snapshot()`
- Adapter converts section objects via `.to_dict()` to `Dict[str, Any]`
- Session-bound: `__init__(manager, session_id)` — mismatch returns None/empty

**Connection 3: SS → Concierge**

- `SSMStateAdapter` duck-types to `IStatePort(Protocol, runtime_checkable)`
- 2 methods match: `get_section(name) → Any`, `get_snapshot() → dict[str, Any]`
- Read-only — writes go through `ctx.writer_port` (separate concern)
- **Minor concern**: `get_snapshot()` accesses `_sections` (private attr) as fallback — brittle

**Connection 4: SS → MemoryWriter** (INCOMPLETE)

- Port defined: `ISessionReadPort(Protocol, runtime_checkable)` with **async** methods
- `async snapshot(sections: List[str]) → Dict[str, Any]`
- `async read_section(name: str) → Optional[Dict[str, Any]]`
- Adapter `adapters/session_read_adapter.py` referenced in docs but directory doesn't exist
- **Blocks MemoryWriter wiring**

**Connection 5: SS → Orchestrator** (transitive via Fabric)

- `StateReadAdapter` wraps `ISessionStateReader` with async pass-through
- Error translation: exceptions → `AdapterException(DEGRADED)`
- `__init__(state_reader: ISessionStateReader)` — explicitly typed

**Connection 6: SS → Planner** (transitive via Fabric)

- `SessionStateReadAdapter` wraps `ISessionStateReader` with bound session_id
- Single protocol method: `async read_sections(sections, trace_id) → SessionSnapshot`
- Returns canonical `SessionSnapshot` from `k1.fabric.ports.state_reader`

### 4.3 Direct Import Coupling (Architectural Leakage)

Concierge bypasses the `IStatePort` boundary with direct SS imports:

| Import | File |
|--------|------|
| `from k1.sessionstate.ports.writer import BatchRequest, MutationRequest` | `k1/concierge/tools/implementations.py` |
| `from k1.sessionstate.sections.task_artifacts import …` | `k1/concierge/fsm/task_bridge.py` |
| `from k1.sessionstate.sections.task_state import TaskStateEntry, …` | `k1/concierge/fsm/task_bridge.py` |
| `from k1.sessionstate.sections.control import IntentClassification, PrivacyBand` | `k1/concierge/fsm/controller.py` |
| `from k1.sessionstate.factory import SessionStateFactory` | `k1/concierge/kernel/bootstrap.py` |

**Risk**: If SS section schemas change, these imports break Concierge directly.

### 4.4 Risk Summary

| Risk | Severity | Impact |
|------|----------|--------|
| MemoryWriter adapter missing | 🟡 Medium | Blocks MW wiring (MS-2+) |
| Concierge direct imports (6 sites) | 🟡 Medium | Schema changes propagate |
| `get_snapshot()` accesses `_sections` private attr | 🟡 Low | Brittle if SSM internals change |
| No Bus integration tests | 🟡 Medium | Event emission to DeltaBus untested |

---

## §5 Test Surface

### 5.1 Aggregate Statistics

| Metric | Value |
|--------|------:|
| **Total test files** | 73 |
| **Total test functions** | **3,933** |
| **Total test code lines** | **63,094** |
| **conftest.py lines** | 938 |
| **Grand total lines** | **64,032** |
| **Average tests per file** | 53.9 |
| **Largest file (lines)** | `test_ports.py` (2,290 lines, 146 tests) |
| **Largest file (tests)** | `test_ports.py` (146 tests) |

### 5.2 Coverage by Area

| Area | Files | Tests | % |
|------|------:|------:|--:|
| Sections (individual) | 12 | 1,193 | 30.3% |
| Contract Compliance | 5 | 373 | 9.5% |
| Ports & Adapters | 5 | 367 | 9.3% |
| Integration (E2E flows) | 14 | 350 | 8.9% |
| Services (SizeTracker, Guard, Engines) | 5 | 295 | 7.5% |
| Tiers (unit tests) | 4 | 240 | 6.1% |
| Events (schemas + capture + emission) | 3 | 175 | 4.4% |
| Cross-Section Dependencies | 5 | 152 | 3.9% |
| Metrics/Observability | 2 | 125 | 3.2% |
| Migration (unit + flow) | 2 | 120 | 3.1% |
| Snapshot & Health | 3 | 108 | 2.7% |
| Reconstruction (unit + flow) | 2 | 106 | 2.7% |
| SLI/SLO Validation | 7 | 96 | 2.4% |
| Eviction (unit + flow) | 2 | 82 | 2.1% |
| Tracing (cognitive_trace_id, logging) | 2 | 81 | 2.1% |
| Manager | 1 | 64 | 1.6% |
| Chaos/Load/Benchmark | 3 | 56 | 1.4% |
| Lifecycle | 2 | 52 | 1.3% |
| Concurrency (single-writer, multi-reader) | 2 | 45 | 1.1% |
| Factory | 1 | 36 | 0.9% |
| Crash Recovery | 1 | 18 | 0.5% |

### 5.3 Cross-Component Test Imports

**ZERO cross-component imports.** All 73 test files import exclusively from `k1.sessionstate.*`. The test suite is **completely self-contained** — no imports from `k1.bus`, `k1.kernel`, `k1.concierge`, `k1.fabric`, `k1.memory_writer`, `k1.planner`, `k1.orchestrator`, etc.

### 5.4 Test Coverage Gaps

| Gap | Severity | Details |
|-----|----------|---------|
| `test_cross_section_cascade.py` — 1 test only | Medium | Full HOT→WARM→COLD cascade barely tested; other cross-section files have 10-58 tests |
| No Bus integration tests | Medium | Zero tests verify event emission reaches K1 bus; all use `LocalEventAdapter` |
| No kernel wiring tests | Medium | No tests verify `k1.kernel` can instantiate/wire SessionState |
| No consumer integration tests | Medium | No tests from concierge/planner/orchestrator perspective |
| Checkpoint restores size metadata only | High | Checkpoint/restore only persists SizeTracker state, not actual section data — documented limitation |
| No K0 sync integration tests | Low | Only tested via `NullSyncPort` (expected — K0 sync not implemented) |
| No periodic checkpoint timer tests | Low | `checkpoint_interval_s` parameter untested for timer firing |
| No FlatBuffer schema drift detection | Low | Round-trip tested but not compared against `.fbs` source schemas |

### 5.5 Key Test Files

| File | Tests | Role |
|------|------:|------|
| `test_wiring_contract.py` | 80 | Validates required files, port interfaces, adapter implementations |
| `test_ports.py` | 146 | All 5 ports + all adapters, comprehensive |
| `test_sections.py` | 145 | All 12 original sections: properties, ops, serialization |
| `test_sizetracker.py` | 81 | SizeTracker: init, get/set, tier totals, pressure, thread safety |
| `test_reconstruction.py` | 85 | ReconstructionSLA: LOCAL COLD/K0 fallback, SLA enforcement |
| `test_migration.py` | 102 | MigrationEngine: demote/promote, compression, concurrent prevention |
| `test_policies_contract.py` | 97 | SLI/SLO contract: latency, capacity, availability, pressure thresholds |
| `test_flatbuffers.py` | 45 | FlatBuffer round-trip for all 12 sections |
| `test_40_turn.py` | 29 | 40-turn conversation: tier distribution, migration |
| `test_benchmark_limits.py` | 26 | Real-world perf: add_turn, add_fact, FlatBuffer serialize/deserialize |

---

## §6 Spec vs Code Delta

### 6.1 Diagram vs Code Discrepancies

| Item | Diagram (`sessionstate.mmd`) | Code | Impact |
|------|------------------------------|------|--------|
| **HOT section count** | 8 sections | **10 sections** (added `task_state`, `task_artifacts`) | HOT budget increased 48KB → 52KB |
| **HOT budget** | 48KB | **52KB** | Total budget at risk of exceeding 96KB |
| **WARM section count** | 4 sections | **5 sections** (added `artifacts_warm`) | WARM budget unchanged (48KB) |
| **Total sections** | 12 | **15** | 3 extensions undocumented in diagram |
| **FlatBuffer HOT types** | — | 8 section types | `task_state`, `task_artifacts` have NO FlatBuffer schemas |
| **FlatBuffer WARM types** | — | 4 section types | `artifacts_warm` has NO FlatBuffer schema |
| **Emergency thresholds** | WARNING=90%, CRITICAL=95% | SizeTracker: ELEVATED=80%, CRITICAL=90%, EMERGENCY=95% | Different naming/threshold mapping |
| **Port style** | Not specified | All ABC (not Protocol) | Differs from Bus (Protocol) — inconsistent across K1 |

### 6.2 Architecture Gaps

| Gap | Severity | Details |
|-----|----------|---------|
| **No production adapters** | 🔴 High | 5 planned production adapters don't exist. Only standalone/test adapters available |
| **Two-phase factory construction** | 🟡 Medium | `create_standalone()` / `create_for_testing()` create manager with None ports then mutate privates |
| **NullSyncPort location** | 🟡 Low | Lives in `ports/k0_sync.py` not `adapters/` — breaks hexagonal convention |
| **MemoryWriter adapter missing** | 🟡 Medium | Port defined, adapter not implemented, `adapters/` directory doesn't exist |
| **3 FlatBuffer schemas missing** | 🟡 Medium | `task_state`, `task_artifacts`, `artifacts_warm` have no `.fbs` definitions |
| **CLI recreation** | 🟡 Low | CLI recreates SessionStateManager per command — no daemon mode |
| **Concierge direct imports** | 🟡 Medium | 6 import sites bypass hexagonal port boundary |
| **HOT budget overrun risk** | 🟡 Medium | 52KB HOT + 48KB WARM = 100KB potential, exceeds 96KB total budget |
| **ABC vs Protocol inconsistency** | 🟡 Low | SS uses ABC, Bus uses Protocol — should be standardized across K1 |

### 6.3 Performance Benchmarks (from diagram)

| Metric | Target (SLO) | Actual (Benchmark) | Margin |
|--------|-------------|-------------------|--------|
| HOT Read P99 | < 150μs | **0.20μs** | 750× |
| HOT Write P99 | < 500μs | **18.8μs** | 26× |
| WARM Read P99 | < 300μs | — | Not benchmarked separately |
| Reconstruction | < 50ms | **2.60ms** | 19× |
| FlatBuffer Serialize | — | **~50μs** (full kernel) | — |

### 6.4 Strengths

- **Comprehensive test suite**: 3,933 tests / 63K lines — exceptional coverage
- **Clean hexagonal architecture**: 5 ports, 6 adapters, factory DI
- **FlatBuffers zero-copy**: 77 generated types, <1μs HOT reads
- **Three-tier memory**: Elegant HOT/WARM/COLD with automatic pressure management
- **Edge-first design**: LOCAL COLD always available, K0 optional
- **Production alerting**: 6 alert rules, 10 recording rules, inhibit chains ready
- **Complete event taxonomy**: 8 domain events + 8 operational log events
- **Self-contained tests**: Zero cross-component test imports

---

## Appendix A: File Inventory

### Source Files (~100+)

```
k1/sessionstate/
├── __init__.py
├── manager.py                  # SessionStateManager (coordinator)
├── guard.py                    # MutationGuard (5-check preflight)
├── sizetracker.py              # SizeTracker (pressure monitoring)
├── eviction.py                 # EvictionEngine (WARM→COLD)
├── migration.py                # MigrationEngine (HOT↔WARM)
├── snapshot.py                 # SnapshotAPI (health, thrash detection)
├── reconstruction.py           # ReconstructionSLA (restore cascade)
├── factory.py                  # SessionStateFactory (3 methods)
├── events.py                   # 8 event types + factory
├── local_cold.py               # LocalColdArchive (SQLite wrapper)
├── metrics.py                  # Prometheus metrics
├── logging.py                  # Structured logging (16 event types)
├── cli.py                      # 10 CLI commands
├── ports/
│   ├── __init__.py
│   ├── storage.py              # IStoragePort (ABC)
│   ├── events.py               # IEventPort (ABC)
│   ├── writer.py               # IWriterPort (ABC)
│   ├── lifecycle.py            # ILifecyclePort (ABC)
│   └── k0_sync.py              # IK0SyncPort (ABC) + NullSyncPort
├── adapters/
│   ├── __init__.py
│   ├── sqlite_storage.py       # SQLiteStorageAdapter
│   ├── memory_storage.py       # InMemoryStorageAdapter
│   ├── local_events.py         # LocalEventAdapter
│   ├── direct_writer.py        # DirectWriterAdapter
│   └── standalone_lifecycle.py # StandaloneLifecycle
├── sections/                   # 15 sections + 1 utility
│   ├── __init__.py
│   ├── control.py              # HOT 8KB NEVER EVICT
│   ├── beliefs_active.py       # HOT 8KB
│   ├── scoreboard.py           # HOT 6KB
│   ├── history_active.py       # HOT 8KB
│   ├── clarifications.py       # HOT 4KB
│   ├── affective_now.py        # HOT 4KB
│   ├── narrative_active.py     # HOT 4KB
│   ├── meta.py                 # HOT 2KB NEVER EVICT
│   ├── task_state.py           # HOT 4KB NEVER EVICT (M4 extension)
│   ├── task_artifacts.py       # HOT 4KB (M6 extension)
│   ├── beliefs_history.py      # WARM 12KB
│   ├── history_recent.py       # WARM 20KB
│   ├── persona.py              # WARM 8KB
│   ├── telemetry.py            # WARM 8KB (first evicted)
│   ├── artifacts_warm.py       # WARM 8KB (M6 extension)
│   └── temporal_context.py     # Utility (not a section)
├── tiers/
│   ├── __init__.py
│   ├── hot.py                  # HotTier (52KB, 10 sections)
│   ├── warm.py                 # WarmTier (48KB, 5 sections)
│   └── local_cold.py           # LocalColdTier (unbounded SQLite)
└── generated/flatbuffers/      # 77 generated FlatBuffer types
    └── K1/SessionState/
```

### Test Files (73)

```
tests/k1/sessionstate/
├── conftest.py                 # 938 lines, shared fixtures
├── test_*.py                   # 58 root-level test files
├── sections/
│   └── test_*.py               # 12 per-section test files
└── tiers/
    └── test_*.py               # 3 per-tier test files
```
