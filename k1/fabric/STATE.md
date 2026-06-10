# K1 Fabric — STATE

Describes every piece of mutable state held inside K1 Fabric, where it lives,
who owns it, what threading guarantees apply, and what transitions are valid.

---

## 1. State ownership summary

| Owner | State type | Mutability | Thread guard |
|---|---|---|---|
| `CapabilityRegistry` | Capability contracts + metadata + version index | Mutable | `threading.RLock` |
| `ProviderRegistry` | Provider configs + health cache | Mutable | `threading.RLock` |
| `AvailabilityTracker` | Per-provider availability + transition history | Mutable | `threading.RLock` |
| `CircuitBreaker` (per provider) | CB state + failure window | Mutable | `threading.Lock` |
| `FabricDispatcher` | In-flight counters + backpressure level | Mutable | `threading.RLock` + `asyncio.Semaphore` |
| `AgentPool` | Live agent pool (per contract_name) | Mutable | `threading.RLock` |
| `DeltaEmitter` (per agent) | Pending deltas (LWW dict) | Mutable | `threading.Lock` |
| `PromptSystemProdAdapter` | PromptTemplate cache loaded from prompt contracts + markdown | Mutable via `reload()` | `threading.RLock` |
| `ModuleLoader` | File-path→capability map + mtime cache | Mutable | `threading.RLock` |
| `HealthChecker` | Per-provider check state + consecutive failures | Mutable | Async (single task) |
| `FabricMetrics` | Prometheus metric objects (lazy-created) | Mutable | `threading.RLock` (creation only) |
| `FabricLogger` | Module-level singleton reference | Mutable (once) | `logging` (thread-safe) |
| `_schema_cache` (module-level) | JSON schema dict cache | Mutable | None (see OPEN_ISSUES §2) |

All contract types (`CapabilityContract`, `AgentContract`, `PromptContract`, `WorkflowContract`),
all request/result types (`CapabilityRequest`, `CapabilityResult`), and all
execution-path types (`ExecutionContext`, `BudgetResult`, `ResolvedProvider`, `ScoredCandidate`)
are **frozen dataclasses** — immutable once constructed.

Prompt/profile metadata on `CapabilityContract` is immutable registry state. The fields
`prompt_template`, `activity_profile`, `tool_instructions`, and `prompt_variables_schema`
move with the contract through registration, lookup, and discovery. They are not copied into
`ContractMetadata` hot metrics state and do not mutate provider routing, safety band state,
or business `params`.

At runtime, `ContextBuilder` materializes a per-call `context_override` section inside
`ExecutionContext.session_sections`. This section is frozen with the `ExecutionContext`, may
contain request-provided override keys, and may include contract-derived prompt/profile metadata
for provider audit/debug. It is not SessionState and is never written back to SessionState.
MCP/WASM providers mirror selected metadata under reserved `__metadata__`; native family tools
mirror it under `WriteContext.extras["fabric_prompt_metadata"]`. These mirrors are per-call
transport payloads, not Fabric-owned mutable state.

`PromptSystemProdAdapter` owns a separate in-memory template cache keyed by prompt name. Each cached `PromptTemplate.template` contains either external markdown loaded from `template_file` or an inline compatibility template. `template_file` paths resolve from the repository root before falling back to the contract file directory. Failed prompt loads are skipped with a warning and do not mutate the capability registry.

The M8 production prompt inventory includes reviewed family profiles for
calendar, tasks, and reminders plus generic MCP/WASM provider profiles. The
representative MCP tool contracts and the `date_calc` / `unit_convert` WASM
contracts carry explicit `activity_profile` and `prompt_template` metadata;
missing metadata is not inferred from names or free text.

When Fabric is built by `KernelService`, the shared runtime receives a verified
`PromptSystemProdAdapter("k1/contracts/prompts")`; per-session Fabric reuses
that prompt adapter and the shared `CapabilityRegistry`. Session Fabric discovery
therefore sees the same immutable `CapabilityContract.prompt_template` and
`CapabilityContract.activity_profile` values that were registered at Tier 1.

---

## 2. `CapabilityRegistry` state

```
_by_name:      Dict[str, ContractUnion]                     — primary index
_by_domain:    Dict[str, List[ContractUnion]]               — domain → contracts
_by_type:      Dict[str, List[ContractUnion]]               — provider_type → contracts
_by_provider:  Dict[str, List[ContractUnion]]               — provider_id → contracts
_by_version:   Dict[str, Dict[str, ContractUnion]]          — name → {semver → contract}
_metadata_cache: Dict[str, ContractMetadata]                — name → live metadata
_last_reload_at: str                                        — ISO timestamp
_created_agents: Dict[str, CreatedAgentRecord]              — dynamic agents
```

### `ContractMetadata` (mutable dataclass, NOT frozen)

```
name: str
contract_type: Optional[str]
domain_tags: List[str]
provider_id: str
provider_type: str
availability: str               — mutated by update_availability()
safety_band_min: str
avg_latency_ms: int             — mutated by update_metrics() via EMA (α=0.3)
success_rate_30d: float         — mutated by update_metrics() via running average
total_invocations_30d: int      — mutated by update_metrics()
registered_at_ns: int
```

Mutation rules:
- `availability` only via `update_availability(name, availability)` — raises `CapabilityNotFoundError` or `ValueError` on bad state
- `avg_latency_ms` via EMA: `new = int(0.3 * latency_ms + 0.7 * old_latency)`
- `success_rate_30d` via running average: `(old_rate * old_total + (1 if success else 0)) / new_total`

All mutations under `_lock (RLock)`. Events emitted OUTSIDE lock.

### Version resolution (4 branches)

When `register(contract)` is called:
1. No existing contract → insert, emit REGISTERED
2. Exact same version → `DuplicateCapabilityError` (unless skip_validation=True)
3. Higher version (same major, major>0) → replace, emit VERSION_UPGRADED
4. Version regression → `VersionRegressionError`

---

## 3. `ProviderRegistry` state

```
_providers:     Dict[str, ProviderConfig]       — primary index
_by_type:       Dict[str, List[str]]            — type → provider_id list
_health_cache:  Dict[str, ProviderHealth]       — provider_id → last known health
```

Initial health for newly registered provider: `ProviderStatus.UNKNOWN`.

`update_health()` emits `k1.fabric.provider.health.changed.v1` on status change only.

Populated single-threaded at construction. Read-only at runtime (no dynamic provider registration at runtime).

---

## 4. `AvailabilityTracker` state

```
_providers: Dict[str, _ProviderState]
    _ProviderState:
        availability: str             — ONLINE / DEGRADED / OFFLINE
        transitions: List[StateTransition]  — capped at max_history (default 100)
        last_transition_ms: int
```

### Valid transitions

```
ONLINE    → {DEGRADED, OFFLINE}
DEGRADED  → {ONLINE, OFFLINE}
OFFLINE   → {DEGRADED}              ← OFFLINE → ONLINE is BLOCKED
```

`enforce_progressive_recovery=True` (default): if `on_state_change()` receives
OFFLINE→ONLINE from the CB integration, the tracker auto-inserts a DEGRADED intermediate step.

Mutation via `update_state(provider_id, new_state, reason)`:
1. Validate transition
2. Append `StateTransition` to history (trim to max_history)
3. Call `_sync_registry()` OUTSIDE lock
4. Emit `k1.fabric.provider.availability.changed.v1`

---

## 5. `CircuitBreaker` state (per provider)

```
_state: CircuitBreakerState         — CLOSED / OPEN / HALF_OPEN
_failures: List[FailureRecord]      — sliding window (60s)
_opened_at_ms: int                  — epoch ms when OPEN entered
_half_open_permit: bool             — only one probe allowed at HALF_OPEN
_consecutive_successes: int         — cleared on any failure
```

### Transition table

| From | To | Condition |
|---|---|---|
| CLOSED | OPEN | `len(pruned_failures) >= failure_threshold` |
| OPEN | HALF_OPEN | `now_ms - opened_at_ms >= half_open_after_ms` |
| HALF_OPEN | CLOSED | probe call succeeds |
| HALF_OPEN | OPEN | probe call fails |

State-change notifications called OUTSIDE lock.

Failure window pruning: entries with `timestamp_ms < now_ms - failure_window_ms` are removed before every threshold check.

`CircuitBreaker.call()` retries up to `max_retries + 1` total attempts.
Retries only occur when `result.error.retriable == True`. Non-retriable failures exhaust immediately.

---

## 6. `FabricDispatcher` state

```
_semaphore: asyncio.Semaphore(max_concurrent=10)
_in_flight: int                                — current concurrent executions
_total_dispatched: int                         — lifetime counter
_total_rejected: int                           — lifetime counter
_total_completed: int                          — lifetime counter
_last_level: BackpressureLevel                 — last emitted level
_per_priority_in_flight: Dict[str, int]        — per WFQPriority counts
_is_shutdown: bool
```

Under `threading.RLock` (for int counters). Semaphore is asyncio — must be acquired in event loop.

Backpressure levels (recomputed on every dispatch):
```
utilization = in_flight / max_concurrent
NORMAL      → utilization < 0.80
WARNING     → 0.80 <= utilization < 0.95
SHEDDING    → utilization >= 0.95
SATURATED   → in_flight == max_concurrent (semaphore blocks)
```

Events emitted only on level transition (not every call).

---

## 7. `AgentPool` state

```
_pool: Dict[str, List[Agent]]       — contract_name → FIFO list of IDLE agents
_total_reuses: int
_total_evictions: int
```

Pool invariants:
- Max 5 agents per contract_name (`AgentPoolConfig.max_pool_size`)
- IDLE TTL: 60s (`IDLE_TTL_S`)
- Sweep interval: 15s (`AgentPoolConfig.sweep_interval_s`)
- `get()`: FIFO, skips TTL-expired, reactivates IDLE→ACTIVE
- `put()`: Agent transitions ACTIVE→IDLE, oldest evicted on capacity

---

## 8. `Agent` lifecycle state

```
AgentLifecycleState:
    PENDING → WARMING → ACTIVE ↔ IDLE → DRAINING → TERMINATED
```

Valid transitions (in `_VALID_TRANSITIONS`):
```
PENDING   → {WARMING}
WARMING   → {ACTIVE}
ACTIVE    → {IDLE, DRAINING}
IDLE      → {ACTIVE, DRAINING}
DRAINING  → {TERMINATED}
TERMINATED → {}               (terminal state, no transitions)
```

`AgentLifecycleError` raised on invalid transition.

On `TERMINATED`: port references (`llm_handle`, `delta_bus`, `delta_emitter`) cleared to None.

Per-agent accumulators (never reset during lifecycle):
```
_tokens_used: int       — incremented per execute() call (approximated as len(output)//4)
_tool_calls: int        — incremented per tool invocation
```

---

## 9. `DeltaEmitter` state (per agent)

```
_pending: Dict[str, AgentDelta]     — merge key = "section:key", LWW semantics
_last_flush_time: float             — monotonic timestamp
```

LWW rule: if a new delta arrives for the same `(section, key)`, the new value unconditionally
replaces the old one (Last Write Wins).

`flush()` drains `_pending` to zero and calls `IDeltaBusPort.emit_delta()` for each.
`flush_if_ready()` only flushes if `DELTA_BATCH_WINDOW_MS` (500ms) has elapsed.

---

## 10. `ModuleLoader` state

```
_file_map:    Dict[Path, str]       — path → capability name
_mtime_cache: Dict[Path, float]     — path → last mtime seen
_running: bool
```

On validation failure for a modified file:
- Old contract kept in registry
- `_mtime_cache[path]` updated to suppress retry on the same mtime

---

## 11. `HealthChecker` per-provider check state

```
_check_states: Dict[str, _ProviderCheckState]
    _ProviderCheckState:
        last_status: str            — last known ProviderStatus
        consecutive_failures: int   — reset to 0 on any HEALTHY result
        last_check_ms: int          — monotonic epoch ms
```

Force-UNHEALTHY threshold: `consecutive_failures >= failure_threshold` (default 3)
and status is not HEALTHY.

---

## 12. `EmbeddingIndex` state

```
_index: faiss.IndexFlatL2 or faiss.IndexIVFFlat
_vectors: Dict[str, np.ndarray]     — capability_name → embedding vector
_dimension: int = 384               — MiniLM-L6 dimension
```

Index type upgrade: when vector count crosses 10,000 (`IVF_THRESHOLD`), index is rebuilt as
`IndexIVFFlat(nlist=100)` at next registration.

All mutation under `threading.RLock`. Search snapshots the vector dict reference outside lock.

---

## 13. `FabricMetrics` state

All Prometheus metric objects are lazy-created on first access. Module-level singleton
`_default_metrics` is created on first call to `get_default_metrics()`.

```
5 Histograms (Optional, None until first access):
    execution_duration          — labels: capability_name, provider_type, tier
    retrieval_duration          — labels: query_type
    registry_lookup_duration    — labels: none
    context_build_duration      — labels: capability_name
    policy_evaluation_duration  — labels: none

6 Counters:
    executions_total            — labels: result
    retrievals_total
    registrations_total
    circuit_breaker_trips_total — labels: provider_id
    agent_spawns_total
    retries_total               — labels: capability_name

4 Gauges:
    registry_size               — labels: capability_type
    circuit_breaker_state       — labels: provider_id, state
    agent_pool_size             — labels: contract_name
    active_executions
```

Lazy creation is thread-safe via `threading.RLock`. Prometheus client itself is thread-safe.

---

## 14. Module-level singletons (process-scoped)

These are the only truly global mutable states in Fabric:

| Singleton | Module | Guard |
|---|---|---|
| `_default_logger: Optional[FabricLogger]` | `k1.fabric.logging` | None (resets on `configure_logger()`) |
| `_default_metrics: Optional[FabricMetrics]` | `k1.fabric.metrics` | `threading.Lock` (double-checked) |
| `_schema_cache: Dict[str, dict]` | `k1.fabric.core.contract_validator` | None — see OPEN_ISSUES §2 |
| `_TIKTOKEN_ENCODING: Any` | `k1.fabric.core.context_budget` | None (lazy-loaded once, never reset) |

---

## 15. What Fabric does NOT own

Fabric deliberately does NOT hold:

- **SessionState** (FAB-01): session data lives in `SessionStateManager` outside Fabric. Fabric's `ISessionStateReader` is read-only.
- **LLM model weights or inference state**: delegated to `IModelGatewayPort`.
- **K0 memory**: all memory operations are forwarded to K0 via `IFabricK0Port`.
- **Bus routing table**: `IEventPort` and `IDeltaBusPort` hold that.
- **Workflow definitions at rest**: `IWorkflowRegistry` owns them.
- **Plan graph**: `IOrchestrator` owns execution state.
- **Agent mailbox** (MPSC): not yet implemented (see OPEN_ISSUES §4).

---

## 16. Phase 1 Store State (NEW — Epics 1, 7, 8 · GATE-P1 passed)

### 16.1 `GlobalProjectionStore` — Shared SQLite WAL

```
Owned by: KernelService (S2.10), shared across all sessions
DB path:  KernelConfig.global_projection_db_path (default "./data/global_projection.db")
WAL mode: Yes · foreign_keys=ON · check_same_thread=False

Tables (11):
  connectors               — PK: connector_id, 12 columns
  capabilities             — PK: capability_name, 19 columns, FTS5 content table
  capabilities_fts         — FTS5 virtual table on (capability_name, description, resource_kind, connector_id)
  resource_kinds           — PK: kind_id
  connector_constitutions  — PK: connector_id, 17 columns
  concept_aliases          — PK: (alias, canonical_concept, domain)
  concept_resource_edges   — PK: (concept, resource_family, domain)
  resource_connector_edges — PK: (domain, resource_family, connector_id)
  operation_equivalences   — PK: (canonical_operation, equivalent_operation, resource_family, domain)
  operation_aliases        — PK: (alias, operation_family)
  capability_type_index    — PK: (capability_name, resource_family, operation_family, effect)

Concurrency: Single-writer (CapabilityRegistryAPI serializes writes). Lock-free reads (dict atomic + frozen dataclasses).

Lifecycle:
  open()  → WAL mode + _ensure_schema() + foreign_keys=ON
  close() → conn.close()
```

### 16.2 `LocalProjectionStore` — Per-Session `:memory:`

```
Owned by: Per-session Fabric instance (P3 path)
DB path:  ":memory:" (never persisted)
WAL mode: Yes

Tables (4):
  connected_resources            — PK: resource_id. Columns: actor_id, resource_kind, connector_id, label, status, permissions (CHECK: read_write/read_only/restricted/none), freshness_state (CHECK: fresh/stale/unknown)
  household_members              — PK: person_id. Columns: label, role, linked_resource_ids_json
  alias_index                    — (alias, entity_id, entity_type, actor_id). Rebuilt from connected_resources + household_members labels on rebuild_alias_index().
  resource_projection_snapshots  — PK: snapshot_id

Key invariant: NEVER use global store as local. Factory creates LocalProjectionStore(":memory:") when none provided.

Lifecycle:
  open()  → WAL + schema. close() → conn.close() (Fabric.shutdown() or session teardown).
```

### 16.3 `IdempotencyStore` — Shared SQLite WAL

```
Owned by: KernelService (S2.10), shared across all sessions
DB path:  KernelConfig.idempotency_db_path (default "./data/idempotency.db")

State machine (1 table → idempotency_keys):
  not_seen  → in_flight → succeeded  (immutable — cannot transition further)
                         → failed

Enforcement: WHERE state NOT IN ('succeeded') on UPDATE — immutable succeeded.

Key invariants:
  check(key)     → IdempotencyCheckResult(state, prior_observation, error)
  mark_success() → durable, blocks re-execution across ALL sessions
  succeeded      → never overwritten, never evicted by mark_failed

Lifecycle:
  open() → WAL + schema. close() → conn.close() (KernelService shutdown).
```

### 16.4 Phase 1 Store Ownership Summary

| Store | Owner | Scope | Opened | Closed |
|---|---|---|---|---|
| `GlobalProjectionStore` | `KernelService` | Shared | S2.10 | Shutdown (after fabric.close()) |
| `LocalProjectionStore` | Per-session `Fabric` | Session | P3 | Session teardown or Fabric.shutdown() |
| `IdempotencyStore` | `KernelService` | Shared | S2.10 | Shutdown (after fabric.close()) |

### 16.5 Phase 1 Gate

All Phase 1 stores are gated behind `KernelConfig.enable_fabric_stores: bool = False`.
When `False` (default), none of the stores are created, all 8 Fabric Phase 1 fields remain `None`,
and factory STEP 21 is inert — zero behavioral change for existing code paths.
