---
adr_id: ORCH-009
title: "Workflow Persistence Strategy -- K1 SQLite Local Cold Storage"
status: Accepted
date: 2026-02-11
module: orchestrator
layer: "L2"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "ORCH-001"
  - "ORCH-008"
related_events:
  - "k1.orchestration.workflow.saved.v1"
  - "k1.orchestration.workflow.triggered.v1"
related_contracts:
  - "k1/contracts/schemas/modules/orchestrator/module.contract.yaml"
related_ports:
  - "IWorkflowStoragePort"
implements_issue: "1.1.9"
superseded_by: ""
tags:
  - architecture
  - orchestrator
  - workflow
  - persistence
  - sqlite
  - edge-first
---

# ORCH-009: Workflow Persistence Strategy -- K1 SQLite Local Cold Storage

## Context

### Problem Statement

The Workflow Engine needs persistent storage for saved workflows (frozen plans), trigger schedules, and run manifests. A storage strategy must define:

1. Where data is stored (K0 Bridge vs. K1 local)
2. What storage technology (SQLite, file system, etc.)
3. What availability characteristics (always-available vs. depends on K0)
4. What schema design supports workflow operations

This resolves Open Question Q2 from orchestrator.md Section 26.

### Current Situation

K0 provides a Bridge for cross-kernel persistence, but Bridge writes are fire-and-forget and subject to K0 availability. Workflows need reliable storage that survives restarts and is always accessible for the scheduler to determine next fire times.

### Constraints

- Edge-First principle: K1 must function without K0 connectivity
- Scheduler needs microsecond-precision next_fire_time queries on startup
- WorkflowRegistry needs fast lookup by workflow_id and user context
- Storage must survive K1 process restarts
- Cannot use K0 Bridge as primary store (fire-and-forget, no query API)

### Requirements

- Always-available local persistence for workflow definitions and trigger state
- Schema supports WorkflowSpec, TriggerSpec, and RunManifest storage
- Atomic operations for trigger state updates (next_fire_time advancement)
- Query support: list workflows, lookup by ID, find due triggers
- K0 Bridge used ONLY for audit/backup, not primary store

---

## Decision

### Chosen Approach

**K1 SQLite local cold storage with IWorkflowStoragePort abstraction.**

### Key Design

**Storage Architecture:**

```text
K1 Local (PRIMARY -- always available):
  SQLite database at k1/data/orchestrator_workflows.db
  Tables: workflows, triggers, runs, proactive_gaps
  Used by: WorkflowRegistry, WorkflowScheduler, GapDetector

K0 Bridge (SECONDARY -- audit/backup, fire-and-forget):
  CommittedPlan WAL (write-ahead log)
  Workflow audit records
  Used by: WorkflowSupervisor (audit writes via IBridgeWritePort)
```

**SQLite Schema:**

```sql
-- Frozen workflow definitions
CREATE TABLE workflows (
    workflow_id    TEXT PRIMARY KEY,
    workflow_name  TEXT NOT NULL,
    version        TEXT NOT NULL,  -- semver
    plan_snapshot  TEXT NOT NULL,  -- JSON: serialized WorkflowSpec
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL,
    user_context   TEXT NOT NULL,  -- owner/session context
    active         INTEGER NOT NULL DEFAULT 1,
    UNIQUE(workflow_name, user_context)
);

-- Trigger definitions and state
CREATE TABLE triggers (
    trigger_id     TEXT PRIMARY KEY,
    workflow_id    TEXT NOT NULL REFERENCES workflows(workflow_id),
    trigger_type   TEXT NOT NULL,  -- CRON | EVENT | MANUAL
    schedule       TEXT,           -- cron expression (CRON type)
    timezone       TEXT,           -- IANA timezone (CRON type)
    event_topic    TEXT,           -- K1 event topic (EVENT type)
    next_fire_time REAL,          -- epoch seconds (CRON type)
    last_fire_time REAL,          -- epoch seconds
    active         INTEGER NOT NULL DEFAULT 1
);

-- Execution run history
CREATE TABLE runs (
    run_id         TEXT PRIMARY KEY,
    workflow_id    TEXT NOT NULL REFERENCES workflows(workflow_id),
    version        TEXT NOT NULL,
    trigger_type   TEXT NOT NULL,
    started_at     REAL NOT NULL,
    completed_at   REAL,
    status         TEXT NOT NULL,  -- RUNNING | COMPLETED | FAILED | CANCELLED
    result_summary TEXT,           -- JSON: abbreviated AggregatedResult
    trace_id       TEXT NOT NULL
);

-- Proactive gap tracking
CREATE TABLE proactive_gaps (
    gap_id          TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL REFERENCES workflows(workflow_id),
    detected_at     REAL NOT NULL,
    gap_type        TEXT NOT NULL,
    affected_step_id TEXT NOT NULL,
    capability_name TEXT NOT NULL,
    description     TEXT NOT NULL,
    status          TEXT NOT NULL,  -- PENDING | ASKED | RESOLVED | AUTO_RESOLVED
    resolved_value  TEXT
);

-- Performance indexes
CREATE INDEX idx_triggers_next_fire ON triggers(next_fire_time) WHERE active = 1;
CREATE INDEX idx_triggers_workflow  ON triggers(workflow_id);
CREATE INDEX idx_runs_workflow      ON runs(workflow_id);
CREATE INDEX idx_runs_status        ON runs(status) WHERE status = 'RUNNING';
CREATE INDEX idx_gaps_workflow      ON proactive_gaps(workflow_id);
CREATE INDEX idx_gaps_status        ON proactive_gaps(status) WHERE status = 'PENDING';
```

**IWorkflowStoragePort Protocol:**

```python
class IWorkflowStoragePort(Protocol):
    """Hexagonal port for workflow persistence. No SQLite leakage."""

    async def save_workflow(self, spec: WorkflowSpec) -> None: ...
    async def load_workflow(self, workflow_id: str) -> Optional[WorkflowSpec]: ...
    async def list_workflows(self, user_context: str) -> List[WorkflowSpec]: ...
    async def deactivate_workflow(self, workflow_id: str) -> None: ...

    async def save_trigger(self, trigger: TriggerSpec) -> None: ...
    async def get_due_triggers(self, now: float) -> List[TriggerSpec]: ...
    async def advance_trigger(self, trigger_id: str, next_fire: float, last_fire: float) -> None: ...

    async def create_run(self, manifest: RunManifest) -> None: ...
    async def complete_run(self, run_id: str, status: str, summary: Dict) -> None: ...
    async def get_active_run(self, workflow_id: str) -> Optional[RunManifest]: ...

    async def save_gap(self, gap: ProactiveGap) -> None: ...
    async def resolve_gap(self, gap_id: str, value: str, status: str) -> None: ...
    async def get_pending_gaps(self, workflow_id: str) -> List[ProactiveGap]: ...
```

**Edge-First Guarantees:**

| Scenario | Behavior |
|----------|----------|
| K0 offline | All workflow operations continue normally via SQLite |
| K1 restart | Scheduler rebuilds timer queue from triggers table on startup |
| SQLite corruption | Detected at startup via integrity_check; rebuild from K0 backup if available |
| Disk full | IWorkflowStoragePort raises TERMINAL AdapterError; ErrorRouter reports to Concierge |

### Rationale

- SQLite provides ACID transactions, WAL mode for concurrent reads, and zero-config deployment
- Edge-First: K1 workflows always work, even if K0 is offline for days
- IWorkflowStoragePort abstraction enables SQLite swap (e.g., to K0-backed store in V2 cloud edition)
- Index design optimizes the two hot paths: scheduler polling (get_due_triggers) and active run check
- K0 Bridge for audit only -- non-blocking, fire-and-forget, no availability dependency

---

## Alternatives Considered

### Alternative 1: K0 Bridge as Primary Store

**Rejected because:** Violates Edge-First principle. K0 availability is not guaranteed on edge devices. Scheduler would stall when K0 is unreachable. Bridge has no query API -- only fire-and-forget writes. Workflows need reliable read-back (trigger state, run history).

### Alternative 2: File-Based JSON Persistence

**Rejected because:** No atomic writes (risk of partial file corruption on crash). No indexing (scheduler polling requires full scan). No concurrent reader safety. SQLite solves all of these with minimal overhead.

### Alternative 3: K1-Level PostgreSQL/Redis

**Rejected because:** Adds deployment dependency on edge devices. SQLite is embedded (zero-config), ships with Python stdlib, and handles K1's volume (tens to hundreds of workflows, not millions).

---

## Consequences

### Positive

- Always-available workflow storage independent of K0
- ACID transactions prevent trigger state corruption
- Zero external dependencies (SQLite is Python-native)
- Clean port abstraction enables future backend changes

### Negative

- SQLite single-writer limitation (mitigated: only WorkflowEngine writes)
- No cross-device workflow sync in V1 (SQLite is local-only)
- Backup/restore requires explicit K0 Bridge sync (not automatic)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SQLite file corruption | Very Low | High | WAL mode, integrity_check on startup, K0 backup |
| Disk space exhaustion | Low | Medium | Run table retention policy (keep last N runs per workflow) |
| Schema migration needed in V2 | Medium | Low | Version table + migration scripts pattern |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| SQLiteWorkflowAdapter | `k1/orchestrator/workflows/persistence/sqlite_adapter.py` | New |
| IWorkflowStoragePort | `k1/orchestrator/ports/workflow_storage_port.py` | New |
| TestWorkflowStorageAdapter | `k1/orchestrator/adapters/test/test_workflow_storage_adapter.py` | New |
| Migration scripts | `k1/orchestrator/workflows/persistence/migrations/` | New |

### Success Metrics

- Scheduler startup: rebuild timer queue from triggers table in <50ms (100 workflows)
- get_due_triggers() latency: <1ms for indexed scan
- Zero data loss across K1 restart cycles in integration tests

### Testing Strategy

- [ ] Unit tests: SQLiteWorkflowAdapter CRUD operations
- [ ] Unit tests: trigger advancement atomicity
- [ ] Integration tests: K1 restart -> scheduler recovery from SQLite
- [ ] Chaos tests: kill K1 mid-write -> WAL recovery on restart

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-11 | K1 Architecture Team | Initial decision -- K1 SQLite local cold storage |
