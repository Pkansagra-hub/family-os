# Milestone 4: Workflow System -- Work Tickets

> **Module**: Orchestrator (Layer 2 in K1 Cognitive Architecture)
> **Milestone**: M4 -- Workflow System
> **Goal**: Implement the User Workflow System -- saved plans as scheduled/event-driven tasks with SQLite persistence, gap detection, and cross-workflow resolution.
> **Prerequisite**: M2 complete (DAG execution works via OrchestratorService, DAGExecutor, StepRunner). M1 types and ports defined.
> **Estimated Epics**: 2 (4.1 Workflow Registry + Compiler, 4.2 Workflow Scheduler + Supervisor + Cross-Workflow)
> **Estimated Issues**: 13 (6 in Epic 4.1, 7 in Epic 4.2)

---

## How to Use These Tickets

Each ticket is self-contained. Before starting:

1. Read **Context Files** listed in the ticket
2. Check **Blocked By** -- all listed tickets must be complete
3. Follow **Anti-Hallucination Rules** strictly
4. Verify all items in **Done When** checklist upon completion

---

## Global Anti-Hallucination Rules (ALL M4 Tickets)

- WorkflowRegistry is STATELESS -- no in-memory cache in V1. All reads go through IWorkflowStoragePort. Do NOT add caching.
- WorkflowSpec is FROZEN (immutable dataclass) -- `bump_version()` creates NEW instance, never mutates existing.
- RunManifest is FROZEN -- status transitions (RUNNING -> COMPLETED/FAILED/ABORTED) create NEW instances.
- WorkflowCompiler `compile()` is called at EXECUTION time (not save time) -- DynamicExpr resolves to current values at trigger fire.
- ProactiveGapDetector dry-run `compile()` does NOT modify stored WorkflowSpecs -- uses deep copy.
- WorkflowScheduler enqueues at INTERACTIVE priority, NOT REALTIME (per SEM-3: REALTIME reserved for live user utterances).
- CrossWorkflowResolver does NOT acquire a second ConcurrencyGuard lock -- sub-workflows execute inside the parent's guard scope.
- WorkflowDepthGuard max_depth=3 is a HARD gate (ORCH-08) -- do NOT increase without ADR update.
- SystemClock is trivially instantiated (no port, no injection) -- WorkflowFactory creates it directly.
- Do NOT write to SessionState (ORCH-01: read-only). IStateReadPort is used ONLY for user.timezone in DynamicExpr resolution and cron evaluation.
- All datetime stored as float (time.time()) NOT ISO string -- simpler, timezone-agnostic.
- SQLite in WAL mode for concurrent reads during workflow execution.
- Single active run per workflow in V1 (per ADR-1.1.11 Q5) -- abort previous if still RUNNING.

---

## Source Document Cross-References

All specifications in this file are grounded in two authoritative documents:

| Aspect | Source | Location |
|--------|--------|----------|
| Issue specs, constructor signatures, wiring | orchestrator-implementation-plan.md | Lines 528-634 (M4 section) |
| ProcessingContext with workflow_id field | schema_whiteboard.md | S1 (lines 24-100) |
| OrchestratorConfig workflow fields | schema_whiteboard.md | S2 (lines 130-260) |
| workflow.triggered.v1 event schema | schema_whiteboard.md | S3.3.18 (lines 717-735) |
| workflow.completed.v1 event schema | schema_whiteboard.md | S3.3.19 (lines 736-760) |
| Mailbox durability, dedup, backpressure | schema_whiteboard.md | S9 (lines 1967-2068) |
| ADR-1.1.9 Workflow Persistence Strategy | orchestrator-implementation-plan.md | Lines 148 (ADR description) |
| ADR-1.1.11 Q5 concurrent run policy | orchestrator-implementation-plan.md | Lines 152 (single active run per workflow) |
| ADR-1.1.11 Q6 sub-workflow param merge | orchestrator-implementation-plan.md | Lines 152 (parent overrides take precedence) |
| IWorkflowStoragePort (8th port) | orchestrator-implementation-plan.md | Lines 4.1.6 issue details |
| WorkflowRunRequest type | orchestrator-implementation-plan.md | Lines 1.2.6 (priority=INTERACTIVE) |
| WorkflowSaveRequest type | orchestrator-implementation-plan.md | Lines 1.2.11 (trigger_spec validation) |
| ProactiveGap + ProactiveGapStatus types | orchestrator-implementation-plan.md | Lines 1.2.12 (gap lifecycle) |
| Event catalog constants | orchestrator-implementation-plan.md | Lines 1.2.17 (WORKFLOW_TRIGGERED, WORKFLOW_COMPLETED) |

---

## Epic 4.1: Workflow Registry + Compiler

> **File locations**:
>   - Types: `k1/orchestrator/workflows/workflow_types.py` (4.1.2, 4.1.4, 4.2.4)
>   - Registry: `k1/orchestrator/workflows/workflow_registry.py` (4.1.1, 4.1.4)
>   - Compiler: `k1/orchestrator/workflows/workflow_compiler.py` (4.1.3)
>   - SQLite adapter: `k1/orchestrator/workflows/persistence/sqlite_adapter.py` (4.1.5)
>   - Port: `k1/orchestrator/ports/workflow_storage_port.py` (4.1.6)
>
> **Key invariant**: WorkflowRegistry is a thin service layer over IWorkflowStoragePort. ZERO in-memory state.
> **WorkflowSpec lifecycle**:
>   1. User sends WorkflowSaveRequest -> OrchestratorService routes to save_workflow()
>   2. save_workflow() builds WorkflowSpec from request + original CommittedPlan
>   3. WorkflowRegistry.save(spec) validates -> storage.save_workflow(spec)
>   4. On scheduler tick: storage.get_due_triggers(now) -> trigger fires
>   5. WorkflowRunSupervisor.start_run() -> WorkflowCompiler.compile(spec)
>   6. compile() resolves DynamicExpr -> validates capabilities -> builds CommittedPlan
>   7. Compiled CommittedPlan fed to DAGExecutor.execute() for standard wave-by-wave execution

---

### WT-4.1.1: Implement WorkflowRegistry

**Deliverable**: `k1/orchestrator/workflows/workflow_registry.py`

**Blocked By**: WT-4.1.2 (WorkflowSpec, TriggerSpec types), WT-4.1.6 (IWorkflowStoragePort), WT-4.1.4 (WorkflowVersionPointer -- embedded in same file)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 536-544 -- Issue 4.1.1 details)
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 558-571 -- Epic 4.1 wiring section)

**Specification**:

Constructor:
```python
class WorkflowRegistry:
    def __init__(self, storage: IWorkflowStoragePort):
        self.storage = storage
```

Methods:
```python
async def save(self, spec: WorkflowSpec) -> str:
    """Validate WorkflowSpec, persist via storage, return workflow_id.
    Raises ValueError on duplicate name.
    """

async def get(self, workflow_id: str) -> Optional[WorkflowSpec]:
    """Returns None if not found."""

async def list_active(self) -> list[WorkflowSpec]:
    """Filters by active=True via storage.list_workflows(active_only=True)."""

async def delete(self, workflow_id: str) -> None:
    """Soft-delete: sets active=False, preserves for audit.
    Hard-delete requires explicit purge(workflow_id)."""

async def purge(self, workflow_id: str) -> None:
    """Hard-delete. Permanently removes workflow and all associated data."""

async def update_trigger(self, workflow_id: str, trigger: TriggerSpec) -> None:
    """Updates trigger for existing workflow, bumps version."""

async def bump_version(
    self, workflow_id: str, new_steps: list[PlanStep], new_deps: dict
) -> str:
    """Creates new version with updated steps/deps, sets as active version.
    Returns new version string ('1.0.0' -> '2.0.0', monotonic major).
    Uses embedded WorkflowVersionPointer (4.1.4).
    """
```

**Validation in save()**:
- `spec.name` non-empty
- `spec.steps` non-empty
- `spec.trigger` valid (CRON requires schedule, EVENT requires event_topic, MANUAL requires neither)
- Duplicate name check: query storage, raise ValueError if name already exists

**Anti-Hallucination Rules**:
- Registry is STATELESS -- no in-memory cache. All reads go through storage port.
- `save()` and `bump_version()` are NOT idempotent -- calling save() twice with same name raises duplicate error.
- `delete()` is soft-delete (active=False). Only `purge()` is hard-delete.
- Version bumps are monotonic and append-only -- no rollback in V1.

**Done When**:
- [ ] File exists at `k1/orchestrator/workflows/workflow_registry.py`
- [ ] Constructor takes single dep: `IWorkflowStoragePort`
- [ ] `save()` validates spec and raises ValueError on duplicate name
- [ ] `get()` returns None if not found
- [ ] `list_active()` filters by active=True
- [ ] `delete()` is soft-delete (active=False)
- [ ] `purge()` is hard-delete
- [ ] `update_trigger()` updates trigger and bumps version
- [ ] `bump_version()` creates new version (monotonic major semver)
- [ ] No in-memory cache -- all ops go through storage

---

### WT-4.1.2: Implement WorkflowSpec + TriggerSpec + DynamicExpr Types

**Deliverable**: `k1/orchestrator/workflows/workflow_types.py`

**Blocked By**: WT-1.2.18 (PlanStep -- 14-field Orchestrator PlanStep)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 544-549 -- Issue 4.1.2 details)

**Specification**:

```python
@dataclass(frozen=True)
class WorkflowSpec:
    workflow_id: str
    name: str
    source_plan_id: str          # references the CommittedPlan this was saved from
    version: str                 # semver major-only: "1.0.0", "2.0.0", ...
    trigger: TriggerSpec
    steps: list[PlanStep]        # 14-field Orchestrator PlanStep (1.2.18)
    dependencies: dict[str, list[str]]  # step_id -> [dep_step_ids]
    active: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    created_by: str = "system"
```

Validation in `__post_init__`:
- name non-empty
- steps non-empty
- version matches semver pattern (regex: `^\d+\.\d+\.\d+$`)

```python
class TriggerType(str, Enum):
    CRON = "CRON"
    EVENT = "EVENT"
    MANUAL = "MANUAL"

@dataclass(frozen=True)
class TriggerSpec:
    type: TriggerType
    schedule: Optional[str] = None      # cron expression (croniter-parseable)
    timezone: str = "UTC"               # IANA timezone
    event_topic: Optional[str] = None   # K1 event bus topic
    enabled: bool = True
```

TriggerSpec validation:
- CRON requires schedule (non-empty, croniter-parseable)
- EVENT requires event_topic (non-empty)
- MANUAL requires neither (both None)

```python
@dataclass(frozen=True)
class DynamicExpr:
    raw: str            # "${date.today}" or "${date.now + 2d}"
    namespace: str      # "date", "user"
    field: str          # "today", "now", "timezone", "locale"
    offset: Optional[str] = None  # "+2d", "-1h", etc.

    @staticmethod
    def parse(value: str) -> Optional["DynamicExpr"]:
        """Returns None if not a dynamic expression (plain value).
        Regex: \\$\\{(\\w+)\\.(\\w+)(?:\\s*([+-])\\s*(\\d+[dhms]))?\\}
        """
```

V1 namespaces: `date` (today, now), `user` (timezone, locale). Extensible via resolver registry.

**Anti-Hallucination Rules**:
- WorkflowSpec is FROZEN -- bump_version() creates new instance.
- steps[] uses the 14-field Orchestrator PlanStep (1.2.18), NOT Fabric PlanStep.
- DynamicExpr appears inside PlanStep.params values -- WorkflowCompiler resolves before execution.
- Use `zoneinfo` (stdlib Python 3.9+), not `pytz`, for timezone handling.

**Done When**:
- [ ] File exists at `k1/orchestrator/workflows/workflow_types.py`
- [ ] WorkflowSpec frozen dataclass with 11 fields
- [ ] `__post_init__` validates name, steps, version format
- [ ] TriggerType enum with CRON, EVENT, MANUAL
- [ ] TriggerSpec frozen dataclass with validation per trigger type
- [ ] DynamicExpr frozen dataclass with `parse()` static method
- [ ] DynamicExpr.parse() regex matches `${namespace.field [+/- duration]}` syntax
- [ ] DynamicExpr.parse() returns None for non-dynamic values

---

### WT-4.1.3: Implement WorkflowCompiler

**Deliverable**: `k1/orchestrator/workflows/workflow_compiler.py`

**Blocked By**: WT-4.1.2 (WorkflowSpec, TriggerSpec, DynamicExpr), WT-4.1.6 (IWorkflowStoragePort for save_gap), WT-1.4.2 (IFabricGatewayPort for query_registry), WT-1.4.5 (IDeltaEmitPort for HIL notification), WT-1.4.4 (IStateReadPort for user prefs), WT-4.2.2 (SystemClock)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 549-555 -- Issue 4.1.3 details)
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 558-571 -- Epic 4.1 wiring: compiler call chain + gap classification)

**Specification**:

Constructor:
```python
class WorkflowCompiler:
    def __init__(
        self,
        fabric: IFabricGatewayPort,
        delta: IDeltaEmitPort,
        storage: IWorkflowStoragePort,
        state_port: IStateReadPort,
        clock: SystemClock,
    ): ...
```

Primary method:
```python
async def compile(self, spec: WorkflowSpec) -> CompilationResult:
```

```python
@dataclass
class CompilationResult:
    success: bool
    compiled_plan: Optional[CommittedPlan]
    gaps: list[ProactiveGap]
    auto_resolved: list[str]       # capability names that were auto-resolved
    compiled_hash: Optional[str]   # SHA-256 of serialized plan
```

**compile() logic** (6 steps):
1. **Deep-copy** `spec.steps` to avoid mutating frozen WorkflowSpec.
2. **Resolve DynamicExpr**: Walk all step params. For each value where `DynamicExpr.parse(value)` returns non-None:
   - `date.today` -> `clock.utc_today()` (returns "YYYY-MM-DD")
   - `date.now` -> `clock.utc_now()` (returns float timestamp)
   - `user.timezone` -> `await state_port.read("user.preferences")` -> extract timezone
   - `user.locale` -> `await state_port.read("user.preferences")` -> extract locale
   - Apply offset if present: `+2d` = add 2 days, `-1h` = subtract 1 hour, etc.
3. **Validate capabilities**: For each step, `await fabric.query_registry(step.capability)`. If None -> capability unavailable.
4. **Gap detection**: Compare current capability contract against contract at workflow creation time (stored hash in WorkflowSpec).
   - **SMALL gap** (per SPEC-9): new optional field added, field renamed (auto-map by name similarity > 0.8), field type widened (int -> float).
     - Action: auto-fill default + emit notification. Status=AUTO_RESOLVED.
   - **LARGE gap** (per SPEC-9): required field added, field removed, type changed incompatibly, capability removed entirely, safety_band_min changed.
     - Action: `await storage.save_gap(ProactiveGap(..., status="PENDING"))`. Pause workflow (set active=False). Emit HIL notification via delta.
5. **Build CommittedPlan** from resolved steps + dependencies.
6. **Compute compiled_hash**: SHA-256 of serialized plan (for RunManifest dedup).

**Gap classification (SPEC-9)**:

| Gap Type | Classification | Action |
|----------|---------------|--------|
| New optional field added | SMALL | Auto-fill with default value |
| Field renamed (similarity > 0.8) | SMALL | Auto-map to new name |
| Field type widened (int -> float) | SMALL | Auto-coerce |
| Required field added | LARGE | Pause workflow + HIL |
| Field removed | LARGE | Pause workflow + HIL |
| Type changed incompatibly | LARGE | Pause workflow + HIL |
| Capability removed entirely | LARGE | Pause workflow + HIL |
| safety_band_min changed | LARGE | Pause workflow + HIL |

**Anti-Hallucination Rules**:
- compile() is called at EXECUTION time -- DynamicExpr resolves to current values, not save-time values.
- If ALL gaps are SMALL and auto-resolved, execution proceeds. If ANY gap is LARGE, compilation fails.
- DynamicExpr resolution must be idempotent -- calling compile() twice with same clock time produces same result.
- state_port is used ONLY for user.timezone/locale resolution -- no other reads needed during compile.
- Uses deep copy of steps -- never mutates the frozen WorkflowSpec.

**Done When**:
- [ ] File exists at `k1/orchestrator/workflows/workflow_compiler.py`
- [ ] Constructor takes 5 deps (fabric, delta, storage, state_port, clock)
- [ ] `compile()` executes 6 steps in order
- [ ] DynamicExpr resolution handles date.today, date.now, user.timezone, user.locale
- [ ] DynamicExpr offset arithmetic works for d/h/m/s units
- [ ] Capability validation via fabric.query_registry()
- [ ] Gap detection and classification per SPEC-9 table
- [ ] SMALL gaps auto-resolved, LARGE gaps pause workflow + HIL
- [ ] SHA-256 compiled_hash computed
- [ ] Returns CompilationResult with all fields populated
- [ ] Idempotent: same clock time -> same result

---

### WT-4.1.4: Implement WorkflowVersionPointer

**Deliverable**: `k1/orchestrator/workflows/workflow_registry.py` (embedded in WorkflowRegistry, same file as 4.1.1)

**Blocked By**: WT-4.1.2 (WorkflowSpec types)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 555-557 -- Issue 4.1.4 details)

**Specification**:

Types (in `k1/orchestrator/workflows/workflow_types.py`):
```python
@dataclass
class WorkflowVersionPointer:
    workflow_id: str
    active_version: str
    version_history: list[VersionEntry]

@dataclass(frozen=True)
class VersionEntry:
    version: str
    created_at: float
    source_plan_id: str
    step_count: int
    change_summary: str
```

Logic (embedded in WorkflowRegistry):
```python
def bump(
    self,
    pointer: WorkflowVersionPointer,
    new_plan_id: str,
    new_steps: list[PlanStep],
    summary: str
) -> str:
    """Increments major version ('1.0.0' -> '2.0.0').
    Appends VersionEntry to history.
    Returns new version string.
    """
```

**Version format**: Semver major-only (1.0.0, 2.0.0, ...) for simplicity in V1. Minor/patch reserved for future partial updates.

**Storage**: version_history stored as JSON array in WorkflowSpec.metadata or as separate column in SQLite workflows table.

**Audit use**: WorkflowRunSupervisor records which version was executed in RunManifest.version. ProactiveGapDetector can compare current vs. previous version to detect drift.

**Anti-Hallucination Rules**:
- Version bumps are monotonic and append-only -- no rollback in V1.
- If user wants an older version, they re-save the workflow from a new plan execution (creates new version).
- WorkflowVersionPointer is embedded in WorkflowRegistry -- not a separate service.

**Done When**:
- [ ] WorkflowVersionPointer dataclass in workflow_types.py
- [ ] VersionEntry frozen dataclass in workflow_types.py
- [ ] `bump()` method on WorkflowRegistry increments major version
- [ ] VersionEntry appended to history on each bump
- [ ] Monotonic, append-only (no rollback)
- [ ] Persisted via storage.save_workflow() after bump

---

### WT-4.1.5: Implement SQLiteWorkflowAdapter (IWorkflowStoragePort Production Backend)

**Deliverable**: `k1/orchestrator/workflows/persistence/sqlite_adapter.py`

**Blocked By**: WT-4.1.6 (IWorkflowStoragePort protocol), WT-4.1.2 (WorkflowSpec, TriggerSpec types), WT-4.2.4 (RunManifest type), WT-1.2.12 (ProactiveGap type)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 557-558 -- Issue 4.1.5 details)
- ADR-1.1.9 (Workflow Persistence Strategy -- K1 SQLite LOCAL COLD)

**Specification**:

```python
class SQLiteWorkflowAdapter(IWorkflowStoragePort):
    def __init__(self, db_path: str):
        """Opens SQLite in WAL mode. Creates tables if not exist on init."""
```

**SQL Schema** (4 tables):
```sql
CREATE TABLE IF NOT EXISTS workflows (
    workflow_id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    spec_json TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    version TEXT NOT NULL,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS triggers (
    trigger_id TEXT PRIMARY KEY,
    workflow_id TEXT REFERENCES workflows(workflow_id),
    type TEXT NOT NULL,
    schedule TEXT,
    timezone TEXT DEFAULT 'UTC',
    event_topic TEXT,
    enabled INTEGER DEFAULT 1,
    next_fire_time REAL,
    last_fire_time REAL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    workflow_id TEXT REFERENCES workflows(workflow_id),
    version TEXT,
    compiled_hash TEXT,
    trigger_type TEXT,
    status TEXT,
    started_at REAL,
    completed_at REAL,
    result_json TEXT
);

CREATE TABLE IF NOT EXISTS gaps (
    gap_id TEXT PRIMARY KEY,
    workflow_id TEXT REFERENCES workflows(workflow_id),
    capability TEXT,
    gap_type TEXT,
    description TEXT,
    status TEXT DEFAULT 'PENDING',
    detected_at REAL,
    resolved_at REAL
);
```

**Additional setup**:
```sql
PRAGMA journal_mode=WAL;
CREATE INDEX IF NOT EXISTS idx_triggers_next_fire ON triggers(next_fire_time) WHERE enabled = 1;
```

**Migration**: version table (`schema_version INTEGER`). On init: check version, apply migrations sequentially. V1 schema = version 1.

**Serialization**: WorkflowSpec serialized to JSON via `json.dumps(asdict(spec))`, deserialized via `WorkflowSpec(**json.loads(row['spec_json']))`. PlanStep list serialized as nested JSON within spec_json.

**Edge-First**: Always available without K0 (per ADR-1.1.9). SQLite file location configurable via `OrchestratorConfig.workflow_db_path` (default: `data/orchestrator_workflows.db` per WB S2).

**Anti-Hallucination Rules**:
- WAL mode enables concurrent reads during workflow execution.
- Use `with self.conn:` for transaction safety (implicit commit on exit).
- All datetime stored as float (time.time()) -- NOT ISO string.
- `get_due_triggers()` must be efficient -- index on next_fire_time (created above).
- Port does NOT define transaction boundaries -- adapter decides (connection-level transactions).
- Async: use `aiosqlite` or `run_in_executor` wrapping standard sqlite3.

**Done When**:
- [ ] File exists at `k1/orchestrator/workflows/persistence/sqlite_adapter.py`
- [ ] Implements IWorkflowStoragePort protocol
- [ ] 4 tables created (workflows, triggers, runs, gaps)
- [ ] WAL mode enabled (`PRAGMA journal_mode=WAL`)
- [ ] Index on triggers.next_fire_time for efficient get_due_triggers()
- [ ] Migration versioning (schema_version table)
- [ ] JSON serialization/deserialization for WorkflowSpec
- [ ] All datetimes as float
- [ ] Transaction safety via context manager
- [ ] Async via aiosqlite or run_in_executor

---

### WT-4.1.6: Implement IWorkflowStoragePort (8th Port Interface)

**Deliverable**: `k1/orchestrator/ports/workflow_storage_port.py`

**Blocked By**: WT-4.1.2 (WorkflowSpec, TriggerSpec types), WT-4.2.4 (RunManifest type), WT-1.2.12 (ProactiveGap type)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 558 -- Issue 4.1.6 details)
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 286-290 -- Epic 1.4 anti-hallucination: port files contain ZERO implementation logic)

**Specification**:

```python
class IWorkflowStoragePort(Protocol):
    """8th port for Orchestrator hexagonal architecture.
    Workflow-specific persistence. All methods async.
    """

    async def save_workflow(self, spec: WorkflowSpec) -> None:
        """Upsert by workflow_id."""
        ...

    async def get_workflow(self, workflow_id: str) -> Optional[WorkflowSpec]:
        ...

    async def list_workflows(self, active_only: bool = True) -> list[WorkflowSpec]:
        ...

    async def delete_workflow(self, workflow_id: str) -> None:
        """Soft delete (set active=False)."""
        ...

    async def save_trigger(self, workflow_id: str, trigger: TriggerSpec) -> None:
        ...

    async def get_due_triggers(self, now: float) -> list[tuple[str, TriggerSpec]]:
        """Returns (workflow_id, trigger) pairs where next_fire_time <= now AND enabled=True.
        Called every 1s by WorkflowScheduler tick -- must be efficient.
        """
        ...

    async def update_trigger_state(
        self, workflow_id: str, next_fire: float, last_fire: float
    ) -> None:
        ...

    async def save_run(self, manifest: RunManifest) -> None:
        ...

    async def get_runs(
        self, workflow_id: str, limit: int = 10
    ) -> list[RunManifest]:
        """Newest first."""
        ...

    async def save_gap(self, gap: ProactiveGap) -> None:
        ...

    async def get_pending_gaps(self) -> list[ProactiveGap]:
        """Returns gaps with status=PENDING."""
        ...
```

**Test adapter** (created in M6): `InMemoryWorkflowAdapter(IWorkflowStoragePort)` -- dict-based, in-memory.

**Anti-Hallucination Rules**:
- Port file contains ZERO implementation logic. Every method body is `...` (Protocol).
- Do NOT add default implementations or helper methods.
- Do NOT add state (no `__init__` beyond Protocol requirements).
- All methods async (SQLite adapter uses aiosqlite or run_in_executor).
- `get_due_triggers()` is called every 1s -- adapter must ensure O(log n) via index.

**Done When**:
- [ ] File exists at `k1/orchestrator/ports/workflow_storage_port.py`
- [ ] Protocol class with 11 async methods
- [ ] All method bodies are `...` (no implementation)
- [ ] No state, no __init__, no helper methods
- [ ] Package __init__.py re-exports IWorkflowStoragePort
- [ ] Matches method signatures expected by WorkflowRegistry, WorkflowScheduler, WorkflowRunSupervisor, ProactiveGapDetector

---

## Epic 4.2: Workflow Scheduler + Supervisor + Cross-Workflow

> **File locations**:
>   - Scheduler: `k1/orchestrator/workflows/workflow_scheduler.py` (4.2.1)
>   - Clock: `k1/orchestrator/workflows/system_clock.py` (4.2.2)
>   - Supervisor: `k1/orchestrator/workflows/workflow_supervisor.py` (4.2.3)
>   - RunManifest + RunStatus: `k1/orchestrator/workflows/workflow_types.py` (4.2.4)
>   - CrossWorkflowResolver + DepthGuard: `k1/orchestrator/workflows/cross_workflow_resolver.py` (4.2.5, 4.2.6)
>   - GapDetector: `k1/orchestrator/workflows/gap_detector.py` (4.2.7)
>
> **Scheduler tick -> execution call chain**:
>   1. WorkflowScheduler._tick() calls storage.get_due_triggers(clock.utc_now())
>   2. For each due trigger: builds WorkflowRunRequest(workflow_id, trigger_type, triggered_at, trace_id)
>   3. Enqueues to mailbox at INTERACTIVE priority (NOT REALTIME)
>   4. Updates trigger state: storage.update_trigger_state(wf_id, next_fire, last_fire)
>   5. OrchestratorService._mailbox_loop() dequeues -> _process_one() routes to execute_workflow()
>   6. execute_workflow() calls WorkflowRunSupervisor.start_run(request)
>   7. Supervisor: concurrent run check -> compiler.compile(spec) -> build RunManifest -> storage.save_run()
>   8. Returns compiled CommittedPlan -> feeds into DAGExecutor.execute()

---

### WT-4.2.1: Implement WorkflowScheduler

**Deliverable**: `k1/orchestrator/workflows/workflow_scheduler.py`

**Blocked By**: WT-4.1.6 (IWorkflowStoragePort), WT-1.4.1 (IMailboxPort), WT-1.4.4 (IStateReadPort for timezone), WT-4.2.2 (SystemClock), WT-1.2.6 (WorkflowRunRequest type)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 574-580 -- Issue 4.2.1 details)
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 613-634 -- Epic 4.2 wiring: scheduler tick -> execution call chain)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S2 lines 174-177 -- OrchestratorConfig workflow fields: max_workflow_depth=3, workflow_db_path, scheduler_tick_interval_ms=1000)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S9 lines 1967-2068 -- Mailbox durability, MailboxFullError handling)

**Specification**:

Constructor:
```python
class WorkflowScheduler:
    def __init__(
        self,
        storage: IWorkflowStoragePort,
        mailbox: IMailboxPort,
        state_port: IStateReadPort,
        clock: SystemClock,
        tick_interval_s: float = 1.0,
    ): ...
```

Lifecycle:
```python
async def start(self) -> None:
    """Starts periodic tick loop via asyncio.create_task(self._tick_loop())."""

async def stop(self) -> None:
    """Cancels tick task."""
```

Core loop:
```python
async def _tick_loop(self) -> None:
    while True:
        await self._tick()
        await asyncio.sleep(self.tick_interval_s)

async def _tick(self) -> None:
    now = self.clock.utc_now()
    due = await self.storage.get_due_triggers(now)
    for workflow_id, trigger in due:
        request = WorkflowRunRequest(
            workflow_id=workflow_id,
            trigger_type=trigger.type,
            triggered_at=now,
            trace_id=str(uuid4()),
            priority="INTERACTIVE",  # per SEM-3
        )
        try:
            self.mailbox.enqueue(request, priority="INTERACTIVE")
        except MailboxFullError:
            # Log error, retry on next tick (don't lose trigger)
            logger.error(f"Mailbox full, deferring workflow {workflow_id}")
            continue
        await self.storage.update_trigger_state(
            workflow_id,
            next_fire=self._compute_next_fire(trigger, now),
            last_fire=now,
        )
```

**Cron evaluation**:
```python
def _compute_next_fire(self, trigger: TriggerSpec, now: float) -> float:
    if trigger.type == TriggerType.CRON:
        # Use croniter library for next fire time
        cron = croniter(trigger.schedule, datetime.fromtimestamp(now, tz=ZoneInfo(trigger.timezone)))
        return cron.get_next(float)
    elif trigger.type == TriggerType.EVENT:
        return float('inf')  # event-driven, no schedule
    elif trigger.type == TriggerType.MANUAL:
        return float('inf')  # manual, no schedule
```

**User timezone**: Read from `state_port.read("user.preferences")` for timezone-aware cron evaluation. Fallback to UTC if not available.

**Crash recovery** (per ADR-1.1.9): On startup, `_tick()` immediately checks for missed fires (next_fire_time < now). Fires immediately, then computes next. Prevents silent skips after restart.

**Anti-Hallucination Rules**:
- tick_interval=1s means cron precision is +/- 1s (acceptable for V1).
- Enqueues at INTERACTIVE priority, NOT REALTIME (REALTIME reserved for live user utterances).
- If mailbox is full (MailboxFullError), log error and retry on next tick -- do NOT lose the trigger.
- `get_due_triggers()` must be indexed in SQLite for O(log n) query (covered in 4.1.5).

**Done When**:
- [ ] File exists at `k1/orchestrator/workflows/workflow_scheduler.py`
- [ ] Constructor takes 5 deps (storage, mailbox, state_port, clock, tick_interval_s)
- [ ] start()/stop() manage asyncio task lifecycle
- [ ] _tick() queries due triggers and enqueues WorkflowRunRequests
- [ ] Priority is INTERACTIVE (not REALTIME)
- [ ] MailboxFullError caught and logged (retry on next tick)
- [ ] _compute_next_fire() handles CRON (croniter), EVENT (inf), MANUAL (inf)
- [ ] Crash recovery: missed fires (next_fire_time < now) fire immediately on startup
- [ ] User timezone read from state_port for cron evaluation

---

### WT-4.2.2: Implement SystemClock

**Deliverable**: `k1/orchestrator/workflows/system_clock.py`

**Blocked By**: None (standalone utility, no dependencies)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 580-583 -- Issue 4.2.2 details)

**Specification**:

```python
class SystemClock:
    def __init__(self) -> None:
        pass  # no deps -- trivial utility

    def utc_now(self) -> float:
        """return time.time()"""

    def utc_today(self) -> str:
        """return datetime.utcnow().strftime('%Y-%m-%d')"""

    def device_local_time(self, timezone: str = "UTC") -> datetime:
        """Converts UTC to device-local timezone via zoneinfo.ZoneInfo(timezone)."""

    def utc_now_datetime(self) -> datetime:
        """Returns datetime.now(timezone=timezone.utc) for DynamicExpr date math."""
```

**Testability**:
```python
class FrozenClock(SystemClock):
    """For tests: returns fixed timestamps."""
    def __init__(self, frozen_time: float):
        self._frozen = frozen_time

    def utc_now(self) -> float:
        return self._frozen

    def utc_today(self) -> str:
        return datetime.utcfromtimestamp(self._frozen).strftime('%Y-%m-%d')
```

**Independently instantiated** (per SPEC-8): Orchestrator and Concierge each create their own SystemClock instance. Not shared via import or port. If extracting to shared: `k1/shared/system_clock.py`. Otherwise duplicate is acceptable (< 20 lines).

**Anti-Hallucination Rules**:
- Use `zoneinfo` (stdlib Python 3.9+), not `pytz`.
- SystemClock is trivially instantiated -- no port, no injection.
- FrozenClock is for tests only -- inject via constructor wherever SystemClock is used.

**Done When**:
- [ ] File exists at `k1/orchestrator/workflows/system_clock.py`
- [ ] SystemClock with 4 methods (utc_now, utc_today, device_local_time, utc_now_datetime)
- [ ] Uses `zoneinfo.ZoneInfo` (not pytz)
- [ ] FrozenClock subclass for tests (fixed timestamps)
- [ ] No dependencies or constructor args

---

### WT-4.2.3: Implement WorkflowRunSupervisor

**Deliverable**: `k1/orchestrator/workflows/workflow_supervisor.py`

**Blocked By**: WT-4.1.1 (WorkflowRegistry), WT-4.1.3 (WorkflowCompiler), WT-4.1.6 (IWorkflowStoragePort), WT-1.4.5 (IDeltaEmitPort), WT-1.4.6 (IBridgeWritePort), WT-4.2.4 (RunManifest type)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 583-590 -- Issue 4.2.3 details)
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 625-630 -- concurrent run policy + no-session result handling)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S3.3.18 lines 717-735 -- workflow.triggered.v1 event schema: workflow_id, execution_id uuid, trigger_type enum, trigger_context, depth 0-3, parent_trace_id, trace_id)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S3.3.19 lines 736-760 -- workflow.completed.v1 event schema: workflow_id, execution_id uuid, status enum [COMPLETED/FAILED/INTERRUPTED/ABORTED], step_count, duration_ms, trigger_type, trace_id)

**Specification**:

Constructor:
```python
class WorkflowRunSupervisor:
    def __init__(
        self,
        registry: WorkflowRegistry,
        compiler: WorkflowCompiler,
        storage: IWorkflowStoragePort,
        delta: IDeltaEmitPort,
        bridge: IBridgeWritePort,
    ): ...
```

Primary method:
```python
async def start_run(self, request: WorkflowRunRequest) -> RunManifest:
```

**Logic** (7 steps):
1. `spec = await self.registry.get(request.workflow_id)`. If None or not active -> raise WorkflowNotFoundError.
2. **Concurrent run check** (per ADR-1.1.11 Q5): `active_runs = await self.storage.get_runs(request.workflow_id, limit=1)`. If latest run.status == RUNNING:
   - `await self._abort_run(active_run)` -- compensate via saga (2.2.5), emit ABORTED status
   - Then proceed with new run. Single active run per workflow in V1.
3. `compilation = await self.compiler.compile(spec)`. If not compilation.success: store RunManifest(status=FAILED, gaps=compilation.gaps), return.
4. Build RunManifest: `RunManifest(run_id=uuid4(), workflow_id=spec.workflow_id, version=spec.version, compiled_hash=compilation.compiled_hash, trigger_type=request.trigger_type, status=RUNNING, started_at=time.time(), steps_total=len(spec.steps))`.
5. `await self.storage.save_run(manifest)`.
6. Emit workflow.triggered.v1 event (per WB S3.3.18): `await self.delta.emit("k1.orchestration.workflow.triggered.v1", {"workflow_id": spec.workflow_id, "execution_id": manifest.run_id, "trigger_type": request.trigger_type, "trace_id": request.trace_id}, request.trace_id)`.
7. Return manifest + compiled_plan to OrchestratorService for DAG execution.

**Post-DAG completion**:
```python
async def deliver_result(
    self, manifest: RunManifest, result: AggregatedResult
) -> None:
    """Update manifest status and deliver result."""
    updated = manifest.complete(result)  # or manifest.fail(error)
    await self.storage.save_run(updated)

    # Emit workflow.completed.v1 (per WB S3.3.19)
    await self.delta.emit("k1.orchestration.workflow.completed.v1", {
        "workflow_id": manifest.workflow_id,
        "execution_id": manifest.run_id,
        "status": updated.status.value,
        "step_count": result.total_steps,
        "duration_ms": result.duration_ms,
        "trigger_type": manifest.trigger_type,
        "trace_id": result.trace_id,
    }, result.trace_id)

    # No-session handling (PROD-4)
    if await self._is_session_active():
        await self.delta.emit_progress(manifest.workflow_id, "Workflow completed", result.trace_id)
    else:
        await self.bridge.submit_deferred_result(
            result.to_dict(), manifest.workflow_id, result.trace_id
        )
```

**No-session result handling** (per PROD-4): Cron at 3 AM when no user session active -> persist via `bridge.submit_deferred_result()`. Concierge checks for pending results on next session start (documented in cross-component contract 1.3.4).

**Anti-Hallucination Rules**:
- `_abort_run()` must be idempotent -- if DAG already completed between check and abort, abort is a no-op.
- `manifest.compiled_hash` enables dedup optimization (if hash unchanged from previous run, skip compilation) -- optimization, not correctness requirement.
- RunManifest is frozen -- status transitions create new instances (complete(), fail(), abort()).
- Single active run per workflow in V1.

**Done When**:
- [ ] File exists at `k1/orchestrator/workflows/workflow_supervisor.py`
- [ ] Constructor takes 5 deps (registry, compiler, storage, delta, bridge)
- [ ] `start_run()` implements 7-step logic
- [ ] Concurrent run check: abort previous RUNNING run
- [ ] Compilation failure results in FAILED RunManifest
- [ ] Emits workflow.triggered.v1 event per WB S3.3.18 schema
- [ ] `deliver_result()` updates manifest and emits workflow.completed.v1
- [ ] No-session handling: deferred result via bridge when no session
- [ ] `_abort_run()` is idempotent

---

### WT-4.2.4: Implement RunManifest + RunStatus Types

**Deliverable**: `k1/orchestrator/workflows/workflow_types.py` (same file as 4.1.2)

**Blocked By**: WT-1.2.4 (AggregatedResult type -- used by complete() method)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 590-594 -- Issue 4.2.4 details)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S3.3.19 lines 736-760 -- workflow.completed.v1 status enum: COMPLETED, FAILED, INTERRUPTED, ABORTED)

**Specification**:

```python
class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"

@dataclass(frozen=True)
class RunManifest:
    run_id: str
    workflow_id: str
    version: str
    compiled_hash: str
    trigger_type: str
    status: RunStatus
    started_at: float
    completed_at: Optional[float] = None
    result_summary: Optional[dict] = None
    error_message: Optional[str] = None
    steps_completed: int = 0
    steps_total: int = 0
```

**Factory**:
```python
@staticmethod
def create(
    workflow_id: str, version: str, compiled_hash: str,
    trigger_type: str, total_steps: int
) -> RunManifest:
    """Sets run_id=uuid4(), status=RUNNING, started_at=time.time()."""
```

**Status transitions** (terminal states are final):
- RUNNING -> COMPLETED (DAG finished successfully)
- RUNNING -> FAILED (DAG failed or compilation failed)
- RUNNING -> ABORTED (concurrent run policy aborted this run)
- No transitions from COMPLETED, FAILED, ABORTED

**Transition methods** (return new frozen instance):
```python
def complete(self, result: AggregatedResult) -> RunManifest:
    """Returns new instance with status=COMPLETED, completed_at, result_summary."""

def fail(self, error: str) -> RunManifest:
    """Returns new instance with status=FAILED, error_message=error."""

def abort(self) -> RunManifest:
    """Returns new instance with status=ABORTED."""
```

**Anti-Hallucination Rules**:
- RunManifest is FROZEN -- status transitions create new instances. Storage adapter handles upsert by run_id.
- No transition from terminal states -- complete/fail/abort should raise if status is already terminal.

**Done When**:
- [ ] RunStatus enum in workflow_types.py with 4 values
- [ ] RunManifest frozen dataclass with 12 fields
- [ ] `create()` factory method sets defaults
- [ ] `complete()` returns new instance with COMPLETED status
- [ ] `fail()` returns new instance with FAILED status
- [ ] `abort()` returns new instance with ABORTED status
- [ ] Terminal state guard: raise if already in terminal state

---

### WT-4.2.5: Implement CrossWorkflowResolver

**Deliverable**: `k1/orchestrator/workflows/cross_workflow_resolver.py`

**Blocked By**: WT-4.1.1 (WorkflowRegistry), WT-4.1.3 (WorkflowCompiler), WT-4.2.6 (WorkflowDepthGuard)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 594-601 -- Issue 4.2.5 details)
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 619-624 -- CrossWorkflowResolver integration with StepRunner wiring)

**Specification**:

Constructor:
```python
class CrossWorkflowResolver:
    def __init__(
        self,
        registry: WorkflowRegistry,
        compiler: WorkflowCompiler,
        depth_guard: WorkflowDepthGuard,
    ): ...
```

Primary method:
```python
async def resolve(
    self,
    step: PlanStep,
    parent_params: dict,
    current_depth: int,
    ancestor_ids: set[str] = None,
) -> Optional[CommittedPlan]:
```

**Logic** (7 steps):
1. Check if `step.capability` matches pattern `workflow.run.*`. If not -> return None (not a sub-workflow step).
2. Extract workflow_id from capability name: `workflow.run.{workflow_id}`.
3. **Cycle detection**: `self.depth_guard.detect_cycle(workflow_id, ancestor_ids or set())`. Raises WorkflowCycleError if cycle found.
4. **Depth check**: `self.depth_guard.check(current_depth + 1)`. Raises MaxDepthError if > max_depth (3).
5. `spec = await self.registry.get(workflow_id)`. If None -> return None (WorkflowNotFoundError surfaced as step failure).
6. **Parameter override** (per ADR-1.1.11 Q6): `merged = {**spec.default_params(), **step.params, **parent_params.get(step.step_id, {})}`. Parent overrides take precedence, sub-workflow spec defaults fill gaps.
7. `compilation = await self.compiler.compile(spec)`. If gaps -> propagate as step failure.
8. Return compilation.compiled_plan with merged params applied.

**Integration with StepRunner** (2.3.3):
1. StepRunner.run(step) checks if `step.capability` matches pattern `workflow.run.*`
2. If match: delegates to `CrossWorkflowResolver.resolve(step, parent_params, current_depth)`
3. Resolved CommittedPlan is executed recursively by a nested `DAGExecutor.execute()` call
4. Sub-workflow results wrapped as single StepResult for parent DAG

**Ancestor tracking**: CrossWorkflowResolver maintains `visited: set[str]` per resolution chain. Each resolve() adds workflow_id to ancestor_ids before recursive calls.

**Anti-Hallucination Rules**:
- Recursive DAGExecutor calls share the ConcurrencyGuard -- sub-workflow does NOT acquire a second lock (already inside DAG execution context).
- Sub-workflow results are wrapped in a single StepResult for the parent DAG.
- Cycle detection is at resolve time, not at save time.
- Parent overrides take precedence in parameter merge (per ADR-1.1.11 Q6).

**Done When**:
- [ ] File exists at `k1/orchestrator/workflows/cross_workflow_resolver.py`
- [ ] Constructor takes 3 deps (registry, compiler, depth_guard)
- [ ] `resolve()` returns None for non-workflow capabilities
- [ ] Extracts workflow_id from `workflow.run.*` pattern
- [ ] Cycle detection via depth_guard.detect_cycle()
- [ ] Depth check via depth_guard.check()
- [ ] Parameter merge: spec defaults < step.params < parent overrides
- [ ] Registry lookup + compile (gaps -> step failure)
- [ ] ancestor_ids propagated through recursive calls

---

### WT-4.2.6: Implement WorkflowDepthGuard

**Deliverable**: `k1/orchestrator/workflows/cross_workflow_resolver.py` (same file as 4.2.5)

**Blocked By**: None (standalone utility)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 601-607 -- Issue 4.2.6 details)

**Specification**:

```python
class WorkflowDepthGuard:
    def __init__(self, max_depth: int = 3):
        self.max_depth = max_depth

    def check(self, current_depth: int) -> None:
        """Raises MaxDepthError if current_depth > max_depth (ORCH-08).
        Root workflow = depth 1. Max 3 = root -> sub -> sub-sub.
        """
        if current_depth > self.max_depth:
            raise MaxDepthError(
                f"Workflow nesting depth {current_depth} exceeds max {self.max_depth}"
            )

    def detect_cycle(self, workflow_id: str, ancestor_ids: set[str]) -> None:
        """Raises WorkflowCycleError if workflow_id in ancestor_ids."""
        if workflow_id in ancestor_ids:
            raise WorkflowCycleError(
                f"Cycle detected: workflow {workflow_id} already in ancestor chain"
            )
```

**Error types**:
```python
class MaxDepthError(Exception):
    """ORCH-08: Workflow nesting depth exceeded. Non-recoverable."""

class WorkflowCycleError(Exception):
    """ORCH-12: Cycle detected in workflow dependency chain. Non-recoverable."""
```

Both are subclasses of `Exception` (or `AdapterError(TERMINAL)` if following error taxonomy from 1.2.10 -- non-recoverable).

**Token budget isolation** (per BUDGET-2): Each workflow (including sub-workflows) gets its own independent token budget from its CommittedPlan.token_budget_max. No cross-workflow token sharing in V1. TokenBudgetTracker is instantiated per DAGExecutor.execute() call (one per workflow level). Simplifies reasoning, prevents parent starvation from chatty sub-workflow.

**Anti-Hallucination Rules**:
- MaxDepthError and WorkflowCycleError are both non-recoverable (TERMINAL).
- Depth guard is separate from ConcurrencyGuard -- depth limits nesting, concurrency limits parallelism.
- max_depth=3 is a HARD gate (ORCH-08) -- do NOT increase without ADR update.
- Cycle detection requires ancestor_ids propagation through resolve() chain.

**Done When**:
- [ ] WorkflowDepthGuard class in cross_workflow_resolver.py
- [ ] `check()` raises MaxDepthError when depth > max_depth
- [ ] `detect_cycle()` raises WorkflowCycleError when cycle detected
- [ ] MaxDepthError and WorkflowCycleError exception classes defined
- [ ] max_depth defaults to 3 (ORCH-08)
- [ ] Token budget isolation documented (per BUDGET-2)

---

### WT-4.2.7: Implement ProactiveGapDetector

**Deliverable**: `k1/orchestrator/workflows/gap_detector.py`

**Blocked By**: WT-4.1.1 (WorkflowRegistry), WT-4.1.3 (WorkflowCompiler), WT-4.1.6 (IWorkflowStoragePort), WT-1.4.7 (IEventSubscriptionPort), WT-1.4.5 (IDeltaEmitPort), WT-1.2.12 (ProactiveGap type)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 607-613 -- Issue 4.2.7 details)
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 628-630 -- ProactiveGapDetector event-driven lifecycle wiring)

**Specification**:

Constructor:
```python
class ProactiveGapDetector:
    def __init__(
        self,
        registry: WorkflowRegistry,
        compiler: WorkflowCompiler,
        storage: IWorkflowStoragePort,
        events: IEventSubscriptionPort,
        delta: IDeltaEmitPort,
    ): ...
```

Startup:
```python
async def start(self) -> None:
    """Subscribes to k1.fabric.capability.contract_updated.v1 via events port."""
    self._subscription_id = await self.events.subscribe(
        "k1.fabric.capability.contract_updated.v1",
        self._on_contract_updated,
    )
```

Handler:
```python
async def _on_contract_updated(self, event: dict) -> None:
```

**Handler logic** (5 steps):
1. Extract `capability_name` from event payload.
2. **Debounce** (5s window): If same capability was processed within last 5s, skip. Prevents K0 sync flood.
3. Query affected workflows: `affected = [spec for spec in await self.registry.list_active() if any(s.capability == capability_name for s in spec.steps)]`. If none -> early return (fast path).
4. For each affected WorkflowSpec:
   a. **Dry-run compile**: `compilation = await self.compiler.compile(deep_copy(spec))` -- deep copy to avoid mutating stored spec.
   b. Classify gaps per SPEC-9 criteria (same as WorkflowCompiler 4.1.3):
      - **SMALL gaps** -> auto-fill defaults. Emit notification: `await self.delta.emit("k1.orchestration.gap.auto_resolved", {"workflow_id": spec.workflow_id, "capability": capability_name, "change_summary": ...}, trace_id)`. Status=AUTO_RESOLVED.
      - **LARGE gaps** -> Save gap: `await self.storage.save_gap(ProactiveGap(gap_id=uuid4(), workflow_id=spec.workflow_id, capability=capability_name, gap_type="LARGE", description=..., status="PENDING", detected_at=time.time()))`. Pause workflow: update spec active=False, save via storage. Surface to user: `await self.delta.emit("k1.orchestration.gap.detected", {...}, trace_id)`.
5. Follows K0 P06 curiosity pattern: proactive detection, non-blocking, user surfaced at convenient time.

**Debounce implementation**:
```python
def __init__(self, ...):
    ...
    self._last_processed: dict[str, float] = {}  # capability -> timestamp
    self._debounce_window_s: float = 5.0

async def _on_contract_updated(self, event: dict) -> None:
    capability_name = event.get("capability_name", "")
    now = time.time()
    if capability_name in self._last_processed:
        if now - self._last_processed[capability_name] < self._debounce_window_s:
            return  # debounced
    self._last_processed[capability_name] = now
    # ... rest of handler logic
```

**Anti-Hallucination Rules**:
- `_on_contract_updated` may fire frequently during K0 sync -- debounce: same capability within 5s, process only latest.
- Dry-run compilation must NOT modify stored WorkflowSpecs -- use deep copy.
- If no active workflows reference the updated capability, handler is a no-op (fast path).
- Gap classification reuses same SPEC-9 criteria as WorkflowCompiler (4.1.3).

**Done When**:
- [ ] File exists at `k1/orchestrator/workflows/gap_detector.py`
- [ ] Constructor takes 5 deps (registry, compiler, storage, events, delta)
- [ ] `start()` subscribes to k1.fabric.capability.contract_updated.v1
- [ ] `_on_contract_updated()` implements 5-step logic
- [ ] Debounce: same capability within 5s window skipped
- [ ] Dry-run compile uses deep copy (no mutation of stored specs)
- [ ] SMALL gaps: auto-resolve + emit notification
- [ ] LARGE gaps: save ProactiveGap + pause workflow + emit HIL notification
- [ ] Fast path: no-op if no active workflows reference updated capability
- [ ] stop() unsubscribes from event

---

## Dependency Summary

### Epic Build Order (within M4)

```
WT-4.1.6 (IWorkflowStoragePort)      -- port interface, first
    |
WT-4.1.2 (WorkflowSpec + TriggerSpec + DynamicExpr) -- types, second
    |
WT-4.1.4 (WorkflowVersionPointer)    -- types, can parallel with 4.1.2
    |
WT-4.2.4 (RunManifest + RunStatus)   -- types, can parallel with 4.1.2
    |
WT-4.2.2 (SystemClock)               -- standalone utility, no deps
    |
WT-4.1.5 (SQLiteWorkflowAdapter)     -- implements port, needs types
    |
WT-4.1.1 (WorkflowRegistry)          -- needs port + types + version pointer
    |
WT-4.1.3 (WorkflowCompiler)          -- needs port + types + fabric + clock
    |
    +--- WT-4.2.1 (WorkflowScheduler)       -- needs port + mailbox + clock
    +--- WT-4.2.3 (WorkflowRunSupervisor)    -- needs registry + compiler + port
    +--- WT-4.2.7 (ProactiveGapDetector)     -- needs registry + compiler + events
    |
WT-4.2.6 (WorkflowDepthGuard)        -- standalone utility
    |
WT-4.2.5 (CrossWorkflowResolver)     -- needs registry + compiler + depth_guard
```

### Recommended Implementation Order

| Phase | Tickets | Rationale |
|-------|---------|-----------|
| 1 (Types + Port) | WT-4.1.6, WT-4.1.2, WT-4.1.4, WT-4.2.4, WT-4.2.2 | Foundational: port interface, all types, clock |
| 2 (Persistence) | WT-4.1.5 | SQLite adapter implementing the port |
| 3 (Registry + Compiler) | WT-4.1.1, WT-4.1.3 | Core workflow services |
| 4 (Execution) | WT-4.2.1, WT-4.2.3 | Scheduler + supervisor (trigger and run workflows) |
| 5 (Advanced) | WT-4.2.5, WT-4.2.6, WT-4.2.7 | Cross-workflow, depth guard, gap detection |

### Cross-Milestone Dependencies

| M4 Ticket | Depends on M1 | Depends on M2 | Depends on M3 | Notes |
|-----------|---------------|---------------|---------------|-------|
| WT-4.1.1 | WT-4.1.6 (port), WT-4.1.2 (types) | -- | -- | Thin service over storage |
| WT-4.1.2 | WT-1.2.18 (PlanStep 14-field) | -- | -- | Uses Orchestrator PlanStep |
| WT-4.1.3 | WT-1.4.2 (IFabricGatewayPort), WT-1.4.4 (IStateReadPort), WT-1.4.5 (IDeltaEmitPort), WT-1.2.12 (ProactiveGap) | -- | -- | 5 constructor deps |
| WT-4.1.4 | WT-4.1.2 (WorkflowSpec types) | -- | -- | Embedded in registry |
| WT-4.1.5 | WT-4.1.6 (port), WT-4.1.2 (types), WT-4.2.4 (RunManifest), WT-1.2.12 (ProactiveGap) | -- | -- | ADR-1.1.9 SQLite backend |
| WT-4.1.6 | WT-4.1.2 (WorkflowSpec, TriggerSpec), WT-4.2.4 (RunManifest), WT-1.2.12 (ProactiveGap) | -- | -- | 8th hexagonal port |
| WT-4.2.1 | WT-4.1.6, WT-1.4.1 (IMailboxPort), WT-1.4.4 (IStateReadPort), WT-1.2.6 (WorkflowRunRequest) | -- | -- | Uses croniter library |
| WT-4.2.2 | -- | -- | -- | Standalone utility |
| WT-4.2.3 | WT-4.1.1, WT-4.1.3, WT-4.1.6, WT-1.4.5 (IDeltaEmitPort), WT-1.4.6 (IBridgeWritePort) | WT-2.2.5 (saga for _abort_run) | -- | WB S3.3.18/19 event schemas |
| WT-4.2.4 | WT-1.2.4 (AggregatedResult) | -- | -- | Frozen, status transitions |
| WT-4.2.5 | WT-4.1.1, WT-4.1.3, WT-4.2.6 | WT-2.3.3 (StepRunner workflow detection) | -- | ADR-1.1.11 Q6 param merge |
| WT-4.2.6 | -- | -- | -- | ORCH-08 max_depth=3 |
| WT-4.2.7 | WT-4.1.1, WT-4.1.3, WT-4.1.6, WT-1.4.7 (IEventSubscriptionPort), WT-1.4.5 (IDeltaEmitPort), WT-1.2.12 (ProactiveGap) | -- | -- | K0 P06 curiosity pattern |

### OrchestratorFactory Wiring (Step 14 of 15)

Per the plan wiring section, OrchestratorFactory step 14 constructs all workflow components:

```python
# Step 14: Workflow subsystem
clock = SystemClock()
workflow_storage = SQLiteWorkflowAdapter(config.workflow_db_path)
workflow_registry = WorkflowRegistry(storage=workflow_storage)
workflow_compiler = WorkflowCompiler(
    fabric=fabric_port,
    delta=delta_port,
    storage=workflow_storage,
    state_port=state_port,
    clock=clock,
)
workflow_scheduler = WorkflowScheduler(
    storage=workflow_storage,
    mailbox=mailbox_port,
    state_port=state_port,
    clock=clock,
    tick_interval_s=config.scheduler_tick_interval_ms / 1000,
)
workflow_supervisor = WorkflowRunSupervisor(
    registry=workflow_registry,
    compiler=workflow_compiler,
    storage=workflow_storage,
    delta=delta_port,
    bridge=bridge_port,
)
depth_guard = WorkflowDepthGuard(max_depth=config.max_workflow_depth)
cross_workflow = CrossWorkflowResolver(
    registry=workflow_registry,
    compiler=workflow_compiler,
    depth_guard=depth_guard,
)
gap_detector = ProactiveGapDetector(
    registry=workflow_registry,
    compiler=workflow_compiler,
    storage=workflow_storage,
    events=event_port,
    delta=delta_port,
)
```
