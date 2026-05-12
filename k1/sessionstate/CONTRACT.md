# K1 SessionState — CONTRACT

---

## 1. Purpose

`k1/sessionstate/` is the **single source of truth for all per-session cognitive state**
in the K1 system. It provides:

- A structured, tiered in-memory store (HOT + WARM) for 15 named sections
- Persistent cold archiving to SQLite (LOCAL COLD tier)
- Eviction (WARM → LOCAL COLD) and migration (HOT → WARM) under memory pressure
- Checkpoint and reconstruction (restore on session resume)
- A mutation guard that enforces capacity and authorization invariants
- A write port (Concierge-only in production) and a read port (Fabric, read-only)

SessionState does **not**:
- Execute capabilities or dispatch tasks (that is Fabric + Orchestrator)
- Call LLMs (that is Model Hub)
- Subscribe to bus topics (passive — it receives mutations via `IWriterPort`)

---

## 2. Core invariants

| ID | Invariant |
|---|---|
| SS-01 | Only one writer in production: Concierge writes via `IWriterPort`. Sub-agents propose deltas to Concierge; they never call `IWriterPort` directly. |
| SS-02 | Fabric reads SessionState via `ISessionStateReader` (read-only). FAB-01: Fabric never writes. |
| SS-03 | `control`, `meta`, and `task_state` are NEVER evicted. `can_evict=False`, `eviction_priority=None`. |
| SS-04 | Total HOT budget: 53,248 bytes (52 KB). Total WARM budget: 49,152 bytes (48 KB). Total: 106,496 bytes (104 KB). |
| SS-05 | `MutationGuard.preflight()` enforces 3-tier capacity: section budget → tier budget → total budget. Every write attempt passes through this check before any mutation is applied. |
| SS-06 | Emergency mode blocks ALL writes to any section. Set via `MutationGuard.set_emergency_mode(True)`. |
| SS-07 | Eviction order is deterministic by `EvictionPriority`: telemetry(1) → artifacts_warm(2) → beliefs_history(3) → history_recent(4) → persona(10). Only WARM sections are evicted. |
| SS-08 | Demotion (HOT → WARM) order: history_active(1) → beliefs_active(2) → narrative_active(3) → task_artifacts(4). |
| SS-09 | Reconstruction SLA: < 50ms P95 from LOCAL COLD. K0 fallback SLA: < 100ms. |
| SS-10 | `SessionStateManager._write_lock` is a `threading.RLock` that serializes all mutations and lifecycle operations. Lock-free reads are explicitly documented as safe. |
| SS-11 | All writes go through `SessionStateManager.mutate(section, operation, data, estimated_bytes)`. Sections never mutated directly from outside the manager. |
| SS-12 | `task_state` entries are pruned (not demoted) 10 turns after `presented_at_turn > 0`. Unpresented tasks are never pruned. |
| SS-13 | `history_active` holds at most 10 full-fidelity turns. On overflow, oldest turns are compressed and demoted to `history_recent` (WARM). |
| SS-14 | `k1/coordination/` is a namespace stub only — no distributed locks, consensus, or leader election are implemented. All concurrency is in-process threading. |
| SS-15 | K0 cloud sync (`BridgeSyncAdapter`, `BridgeStorageAdapter`) are stubs, blocked until MS-2+. Is_available=False. All production persistence is LOCAL COLD SQLite only. |

---

## 3. Memory tier structure

### HOT tier — 53,248 bytes (52 KB)

10 sections, always in-process memory. Access is lock-free for reads.

| Section | Budget | Evict | Description |
|---|---|---|---|
| `control` | 8 KB | NEVER | FlowState, TurnLock, AgentLease[], DomainContext, SafetyContext, IntentClassification, PrivacyBand |
| `beliefs_active` | 8 KB | Demotes → `beliefs_history` | Active facts (SVO, max ~50), EntityRef[], pinned_fact_ids |
| `scoreboard` | 6 KB | Demotes → WARM | Referent[], QUD stack (Question[]), Topic stack, SalienceEntry[], Commitment[], current_turn |
| `history_active` | 8 KB | Demotes → `history_recent` | Full-fidelity turns (max 10), TypedHistoryEntry[], token counts |
| `clarifications` | 4 KB | Cannot evict | Pending clarifications (max ~20), is_blocked, blocking_clarification_id |
| `affective_now` | 4 KB | Demotes → WARM | current_emotion, intensity, EmotionDimensions (VAD), EmotionTrajectory, last 5 snapshots |
| `narrative_active` | 4 KB | Demotes → WARM | primary ConversationThread, paused_threads (max 5), NarrativeArc |
| `meta` | 2 KB | NEVER | SessionIdentity, SessionLifecycle, MemoryUsage, VersionInfo, privacy_band, turn_count |
| `task_state` | 4 KB | NEVER | TaskStateEntry[] (max 20), last_updated_ms |
| `task_artifacts` | 4 KB | Demotes → `artifacts_warm` | TaskArtifactEntry[] (max 30) |

### WARM tier — 49,152 bytes (48 KB)

5 sections. Eviction candidates in priority order.

| Section | Budget | Evict Priority | Description |
|---|---|---|---|
| `telemetry` | 8 KB | 1 (first) | TokenData, CostData, LatencyData, ErrorData, TurnTiming[], PerformanceSummary |
| `artifacts_warm` | 8 KB | 2 | Demoted task artifacts (max 50, LRU) |
| `beliefs_history` | 12 KB | 3 | ArchivedFact[] (max 100, LRU-scored), EntityFactIndex[] |
| `history_recent` | 20 KB | 4 | CompressedTurn[] (turns 11–30), SummarizedTurn[] (turns 31–40), session_summary |
| `persona` | 8 KB | 5 (last) | PersonalityProfile, VoicePreferences, VocabularyEntry[], InteractionStyle |

### LOCAL COLD — SQLite

`~/.familyos/k1/sessionstate.db`. WAL mode, synchronous=NORMAL. 7 tables.
Populated by eviction and checkpoint. Read by reconstruction.

---

## 4. Public API

### `SessionStateManager` — central facade

```python
# Read API (lock-free)
def get_section(name: str) -> Any
def get_hot() -> HotTier
def get_warm() -> WarmTier
def get_all_section_sizes() -> Dict[str, int]
def get_snapshot() -> SessionSnapshot

# Write API (acquires _write_lock: RLock)
def mutate(
    section: str,
    operation: str,
    data: Any,
    estimated_bytes: Optional[int] = None,
    cognitive_trace_id: Optional[str] = None,
) -> MutationResult

# Lifecycle API
def start(restore_if_exists: bool = True, ...) -> StartResult
def stop(checkpoint_before_stop: bool = True, ...) -> StopResult
def checkpoint(...) -> CheckpointResult
def restore(session_id: str, ...) -> RestoreResult
```

### `AsyncSSMBridge` — async wrapper

Wraps `SessionStateManager`. Reads are direct pass-through (lock-free, <1ms).
Writes use `asyncio.to_thread()`. All method signatures mirror the sync manager.

---

## 5. Mutation pipeline

```
Caller (Concierge or DirectWriterAdapter)
    │
    ▼ manager.mutate(section, operation, data, estimated_bytes)
    │
    ├── acquire _write_lock (RLock)
    │
    ├── guard.preflight(section, operation, estimated_bytes)
    │     ├── check VALID_OPERATIONS set (35+ named ops)
    │     ├── section budget: budget - current - (estimated * 1.10) > 0
    │     ├── tier budget: tier_limit - tier_total - (estimated * 1.10) > 0
    │     ├── total budget: TOTAL_LIMIT - total - (estimated * 1.10) > 0
    │     ├── emergency mode check
    │     ├── section locked check
    │     └── → Approval(approved, reason, available_kb)
    │
    ├── if rejected: emit MutationRejectedEvent → return MutationResult.rejected(...)
    │
    ├── apply section mutation (section-specific method)
    │
    ├── size_tracker.update(section, delta_bytes)
    │
    ├── emit MutationApprovedEvent via event_port
    │
    ├── pressure check:
    │     if HOT pressure >= ELEVATED: consider migration
    │     if WARM pressure >= CRITICAL: trigger eviction
    │
    └── release _write_lock → return MutationResult(success=True, ...)
```

`estimated_bytes` is multiplied by `FLATBUFFER_OVERHEAD_FACTOR=1.10` during preflight.
If caller provides `None`, the guard estimates from operation type.

---

## 6. Eviction pipeline (WARM → LOCAL COLD)

**Trigger:** WARM pressure exceeds threshold (ELEVATED≥80%, CRITICAL≥90%, EMERGENCY≥95%)
or `EvictionEngine.evict()` called explicitly.

```
EvictionEngine.evict(reason, target_bytes):
    candidates = get_eviction_candidates()   # ordered by EvictionPriority
    for candidate in candidates:
        guard.lock_section(candidate.section)
        data, bytes_est = section_provider.get_evictable_data(section, target_bytes)
        local_cold.archive(session_id, section, data)
        section_provider.remove_evicted_data(section, bytes_freed)
        size_tracker.update(section, -bytes_freed)
        guard.unlock_section(section)
        if warm_utilization <= TARGET=0.70: break
        if iterations >= MAX=10: break
```

Sections evicted to LOCAL COLD can be reconstructed on next session start.
`control`, `meta`, `task_state` are never candidates.

---

## 7. Migration pipeline (HOT → WARM demotion)

**Trigger:** HOT pressure > 90%, or turn completion overflow (history_active > 10 turns),
or narrative thread archiving.

Migration pairs (one-to-one):
- `history_active` → `history_recent` (WARM)
- `beliefs_active` → `beliefs_history` (WARM)

Turn compression during history migration:
- Turns 1–10: Full fidelity in `history_active` (HOT)
- Turns 11–30: `CompressedTurn` (entities + intents + key phrases) in `history_recent`
- Turns 31–40: `SummarizedTurn` (single sentence ~100 chars) in `history_recent`
- Turns 41+: Evicted to LOCAL COLD

Promotion (WARM → HOT) is triggered on context switch or thread resumption.

---

## 8. Reconstruction pipeline (session resume)

Called during `manager.start(restore_if_exists=True)`.

```
ReconstructionSLA.reconstruct(session_id):
    source = FRESH
    try:
        data = local_cold.restore(session_id, ...)
        source = LOCAL_COLD
        if time > SLA_LOCAL_COLD_MS=50ms: sla_breach++
    except:
        if k0_sync_port.is_available:
            data = await k0_sync_port.restore_from_k0(session_id, timeout=K0_TIMEOUT_MS=80ms)
            source = K0
            if time > SLA_K0_FALLBACK_MS=100ms: sla_breach++

    # Hydrate HOT first (priority order):
    #   control → meta → beliefs_active → scoreboard → history_active →
    #   clarifications → affective_now → narrative_active

    # Then WARM:
    #   persona → beliefs_history → history_recent → telemetry

    return ReconstructionResult(source=source, sla_met=...)
```

---

## 9. Write port contract (`IWriterPort`)

```python
@abstractmethod
def request_mutation(request: MutationRequest) -> MutationResponse
@abstractmethod
def batch_mutations(batch: BatchRequest) -> BatchResult
@abstractmethod
def validate_writer(writer_id: str) -> WriterAuthorization
```

`MutationRequest` fields:
- `section: str`, `operation: str`, `data: Any`, `estimated_bytes: int`
- `writer_id: str`, `cognitive_trace_id: str`
- `priority: MutationPriority` (CRITICAL/HIGH/NORMAL/LOW/DEFERRED)
- `delegation_chain: List[str]`, `timeout_ms: int`

`MutationStatus` lifecycle: `PENDING → VALIDATING → APPROVED/REJECTED → APPLIED/FAILED`

---

## 10. Read port contract (`ISessionStateReader`)

Returns `SessionSnapshot` (frozen dataclass):
```python
@dataclass(frozen=True)
class SessionSnapshot:
    session_id: str
    sections: Dict[str, Dict[str, Any]]
    timestamp_ms: int
    section_names: List[str]   # auto-derived from sections keys
```

`has_section(name)`, `get_section(name)`, `to_dict()` methods.
Multi-reader, lock-free. Fabric always uses snapshots — never live section objects.

---

## 11. Pressure levels and thresholds

| Level | Threshold (% of budget) | Action triggered |
|---|---|---|
| NORMAL | < 80% | None |
| ELEVATED | 80–89% | Consider migration (HOT) or preemptive eviction (WARM) |
| CRITICAL | 90–94% | Trigger migration (HOT) or eviction (WARM) |
| EMERGENCY | ≥ 95% | Emergency mode activation, block writes, force eviction |

Pressure is computed independently for HOT and WARM tiers. Overall pressure = max of the two.

---

## 12. Bus events emitted

All events emitted via `IEventPort.emit()`. In standalone mode: local fan-out via `LocalEventAdapter`. In production: would go to K1 DeltaBus via `DeltaBusAdapter` (currently stub).

| Event topic | Payload type | When |
|---|---|---|
| `sessionstate.mutation.requested` | `MutationRequestedEvent` | Before preflight |
| `sessionstate.mutation.approved` | `MutationApprovedEvent` | After successful apply |
| `sessionstate.mutation.rejected` | `MutationRejectedEvent` | Preflight failure |
| `sessionstate.eviction.triggered` | `EvictionTriggeredEvent` | Eviction starts |
| `sessionstate.eviction.completed` | `EvictionCompletedEvent` | Eviction done |
| `sessionstate.emergency.activated` | `EmergencyActivatedEvent` | Emergency mode on |
| `sessionstate.emergency.resolved` | `EmergencyResolvedEvent` | Emergency mode off |
| `sessionstate.reconstruction.started` | `ReconstructionStartedEvent` | Session reconstruct starts |

---

## 13. Error surface

| Exception | Location | When raised |
|---|---|---|
| `SectionNotFoundError(KeyError)` | `manager.py` | `get_section(name)` for unknown section name |
| `MutationRejectedError` | `manager.py` | `mutate()` when preflight returns `approved=False` |
| `LifecycleError` | `manager.py` | Invalid lifecycle state transition |
| `PortProtocolError` | `factory.py` | `create_with_ports()` given port that doesn't match protocol |

---

## 14. `k1/coordination/` status

`k1/coordination/` is a **namespace stub only**. Three sub-packages are empty `__init__.py` files:
- `coordination/llm_model_hub/`
- `coordination/observability/`
- `coordination/sessionstate_concurrency/`

No distributed locks, consensus, or leader election exist. All concurrency is in-process threading inside `k1/sessionstate/`.

---

## 15. Blocked stubs (MS-2+ milestones)

| Adapter | Status | Blocks |
|---|---|---|
| `BridgeStorageAdapter` | Stub — `is_available=False` | K0 cloud archive |
| `BridgeSyncAdapter` | Stub — `is_available=False` | K0 cloud sync |
| `ConciergeWriterAdapter` | Stub | Production write path from Concierge |
| `DeltaBusAdapter` | Stub | Session events on K1 DeltaBus |
| `FabricLifecycleAdapter` | Stub | Fabric lifecycle coordination |

All production paths currently use: `SQLiteStorageAdapter` + `LocalEventAdapter` + `DirectWriterAdapter` + `StandaloneLifecycle`.
