# Workflow Authoring Guide

How to create, trigger, and manage workflows in the K1 Orchestrator.

**Source files**: All code locations referenced in this guide are relative to `k1/orchestrator/`.

---

## Table of Contents

1. [WorkflowSpec Format](#1-workflowspec-format)
2. [Trigger Types](#2-trigger-types)
3. [Step Definition](#3-step-definition)
4. [Cross-Workflow Patterns](#4-cross-workflow-patterns)
5. [Proactive Gap Handling](#5-proactive-gap-handling)
6. [Concurrent Run Policy](#6-concurrent-run-policy)
7. [Examples](#7-examples)

---

## 1. WorkflowSpec Format

**Source**: `workflows/workflow_types.py` class `WorkflowSpec` (line 113).

A `WorkflowSpec` is a frozen (immutable) dataclass that defines a saved workflow. When a user says "save this as a workflow" or "do this every Monday", the Orchestrator converts a `CommittedPlan` into a `WorkflowSpec` and persists it via `IWorkflowStoragePort`.

### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `workflow_id` | `str` | Yes | -- | Unique identifier (format: `wf-<uuid>`). Generated at save time. |
| `name` | `str` | Yes | -- | Human-readable workflow name. Must be non-empty. Must be unique across all workflows (enforced by `WorkflowRegistry.save()`). |
| `source_plan_id` | `str` | Yes | -- | ID of the `CommittedPlan` this workflow was derived from. Links back to the original plan for audit. |
| `version` | `str` | Yes | -- | Semver string (`^\d+\.\d+\.\d+$`). Initial version is `1.0.0`. Incremented by `WorkflowRegistry.bump_version()` (major-only: `1.0.0` -> `2.0.0` -> `3.0.0`). |
| `trigger` | `TriggerSpec` | Yes | -- | Defines when and how the workflow fires. See [Section 2](#2-trigger-types). |
| `steps` | `List[PlanStep]` | Yes | `[]` | Ordered list of execution steps. Must be non-empty. Uses the Orchestrator's 14-field `PlanStep` (not Fabric's 6-field version). See [Section 3](#3-step-definition). |
| `dependencies` | `Dict[str, List[str]]` | No | `{}` | DAG dependency graph: `{step_id: [dependency_step_ids]}`. Keys and values must reference valid step IDs. Graph must be acyclic. |
| `active` | `bool` | No | `True` | Whether the workflow is eligible for scheduling and execution. Set to `False` by soft-delete or when `ProactiveGapDetector` deactivates due to LARGE gaps. |
| `created_at` | `float` | No | `time.time()` | Creation timestamp (UTC, seconds since epoch). |
| `updated_at` | `float` | No | `time.time()` | Last modification timestamp (UTC, seconds since epoch). |
| `created_by` | `str` | No | `"system"` | Creator identifier. |

### Validation Rules (enforced in `__post_init__`)

- `name` must be non-empty.
- `steps` must be non-empty.
- `version` must match semver pattern `^\d+\.\d+\.\d+$`.

### Immutability

`WorkflowSpec` is a frozen dataclass. To update a workflow, create a new `WorkflowSpec` instance with modified fields (via `dataclasses.replace()`). Version bumps produce new instances -- the original is never mutated.

### YAML-Equivalent Structure

```yaml
workflow_id: "wf-a1b2c3d4-e5f6-7890-abcd-ef1234567890"
name: "Daily Health Check"
source_plan_id: "plan-xyz-123"
version: "1.0.0"
active: true
created_by: "system"

trigger:
  type: "CRON"
  schedule: "0 8 * * *"
  timezone: "America/New_York"
  enabled: true

steps:
  - id: "s1"
    capability: "health.check.system"
    params:
      target: "all"
      date: "${date.today}"
    deps: []
    is_optional: false
    has_side_effects: false
    timeout_ms: 30000
  - id: "s2"
    capability: "notification.send"
    params:
      channel: "email"
      template: "health_report"
    deps: ["s1"]
    is_optional: false
    has_side_effects: true

dependencies:
  s2: ["s1"]
```

### Save Flow

**Source**: `workflows/workflow_engine.py` method `save_workflow()` (line 290).

1. User says "save this as a workflow" -> Concierge creates `WorkflowSaveRequest`.
2. `OrchestratorService.process()` routes to `WorkflowEngine.save_workflow()`.
3. Engine reads the `CommittedPlan` from Bridge WAL (`PLAN_START` entry).
4. Builds `WorkflowSpec` from plan steps + trigger from the request.
5. Persists via `WorkflowRegistry.save()` (duplicate name check included).
6. Registers trigger state via `IWorkflowStoragePort.save_trigger()`.

**WorkflowSaveRequest fields** (source: `types.py` line 1137):

| Field | Type | Description |
|-------|------|-------------|
| `committed_plan_id` | `str` | ID of the plan to save as workflow. Non-empty. |
| `workflow_name` | `str` | Human-readable name. Non-empty. |
| `trigger_spec` | `TriggerSpec` | How the workflow should be triggered. |
| `trace_id` | `str` | Trace correlation ID. |
| `request_id` | `str` | Auto-generated UUID. |

---

## 2. Trigger Types

**Source**: `types.py` enum `TriggerType` (line 68), dataclass `TriggerSpec` (line 301).

Every workflow has exactly one `TriggerSpec` that determines when and how it fires.

### TriggerType Enum

| Value | Description |
|-------|-------------|
| `CRON` | Time-based schedule using cron expressions. Evaluated by `WorkflowScheduler` on every tick. |
| `EVENT` | Fires when a specific K1 event bus topic receives a message. |
| `MANUAL` | Fires only on explicit user request (Concierge submits `WorkflowRunRequest`). |

### TriggerSpec Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | `TriggerType` | Yes | -- | One of `CRON`, `EVENT`, `MANUAL`. |
| `schedule` | `Optional[str]` | CRON only | `None` | Cron expression (croniter-parseable). Required for `CRON`. Must be `None` for `MANUAL`. |
| `timezone` | `str` | No | `"UTC"` | IANA timezone string (e.g., `"America/New_York"`, `"Europe/London"`). Uses `zoneinfo` (stdlib Python 3.9+). |
| `event_topic` | `Optional[str]` | EVENT only | `None` | K1 event bus topic to subscribe to. Required for `EVENT`. Must be `None` for `MANUAL`. |
| `enabled` | `bool` | No | `True` | Whether the scheduler should evaluate this trigger. Set to `False` to pause without deleting. |

### Validation Rules (enforced in `TriggerSpec.__post_init__` and `WorkflowRegistry._validate_trigger`)

| Trigger Type | Rules |
|-------------|-------|
| `CRON` | `schedule` must be non-empty. |
| `EVENT` | `event_topic` must be non-empty. |
| `MANUAL` | `schedule` must be `None` AND `event_topic` must be `None`. |

### CRON Trigger Details

**Source**: `workflows/workflow_scheduler.py` function `compute_next_fire()` (line 69).

- Uses `croniter` library for next-fire computation.
- Timezone-aware: builds `datetime` from the `timezone` field using `zoneinfo.ZoneInfo`.
- Tick interval is 1 second (cron precision +/- 1 second, acceptable for V1).
- Priority: enqueued at `INTERACTIVE` priority (per SEM-3), never `REALTIME`.

**Cron expression examples**:

| Expression | Meaning |
|-----------|---------|
| `0 8 * * *` | Daily at 08:00 |
| `0 9 * * 1` | Every Monday at 09:00 |
| `0 0 1 * *` | First day of every month at midnight |
| `*/15 * * * *` | Every 15 minutes |
| `0 8,12,18 * * *` | Three times daily at 08:00, 12:00, 18:00 |

**Crash recovery** (ADR-1.1.9): On the first tick after a restart, any trigger whose `next_fire_time < now` is immediately fired. This prevents silent skips after downtime.

### EVENT Trigger Details

- EVENT triggers set `next_fire = MAX_FLOAT` (no time-based schedule).
- The scheduler does not fire EVENT triggers -- they are fired by the K1 event bus subscription layer.
- `event_topic` specifies the K1 event bus topic to listen to (e.g., `"k1.data.import.completed.v1"`).

### MANUAL Trigger Details

- MANUAL triggers set `next_fire = MAX_FLOAT` (no schedule).
- Triggered only when a user explicitly requests execution via Concierge.
- Concierge creates a `WorkflowRunRequest` with `trigger_type=TriggerType.MANUAL` and submits it to the Orchestrator mailbox.

### Scheduler Tick Loop

**Source**: `workflows/workflow_scheduler.py` class `WorkflowScheduler` (line 108).

The scheduler runs a periodic tick loop (default 1 second):

1. `now = clock.utc_now()`.
2. Query due triggers: `storage.get_due_triggers(now)` returns `(workflow_id, TriggerSpec)` pairs where `next_fire_time <= now` and `enabled = True`.
3. For each due trigger:
   a. Look up `WorkflowSpec` from storage (to get `version`).
   b. Skip if workflow not found or inactive.
   c. Build `WorkflowRunRequest` (workflow_id, version, trigger_type, priority=`INTERACTIVE`).
   d. Enqueue to `IMailboxPort` at `INTERACTIVE` priority.
   e. Compute `next_fire` using `compute_next_fire()`.
   f. Update trigger state: `storage.update_trigger_state(workflow_id, next_fire, last_fire=now)`.
4. Per-trigger errors are caught and logged -- one bad trigger does not block others.
5. `MailboxFullError` is caught but trigger state is NOT updated -- the trigger remains "due" and retries on the next tick.

**Lifecycle**:

```
scheduler.start()   # Creates asyncio.Task for tick loop
...
scheduler.stop()    # Cancels tick task
```

### Updating a Trigger

**Source**: `workflows/workflow_registry.py` method `update_trigger()` (line 81).

To change a workflow's trigger (e.g., change schedule from daily to weekly):

1. Call `WorkflowRegistry.update_trigger(workflow_id, new_trigger_spec)`.
2. The registry validates the new trigger spec.
3. A version bump is applied (e.g., `1.0.0` -> `2.0.0`).
4. Updated spec is saved and trigger state is re-registered.

---

## 3. Step Definition

**Source**: `types.py` class `PlanStep` (line 632).

Each step in a workflow represents a single capability invocation within the DAG. The Orchestrator uses a 14-field `PlanStep` (not Fabric's 6-field version) to support DAG execution features.

### PlanStep Fields

| # | Field | Type | Required | Default | Description |
|---|-------|------|----------|---------|-------------|
| 1 | `id` | `str` | Yes | `""` | Unique step identifier within the workflow (e.g., `"s1"`, `"s2"`). Must be non-empty. Referenced in `dependencies` and `deps`. |
| 2 | `capability` | `str` | Yes | `""` | Name of the Fabric-registered capability to invoke (e.g., `"health.check.system"`, `"notification.send"`). Must be non-empty. Validated against Fabric registry at compile time. For sub-workflows, use `workflow.run.<workflow_id>` pattern (see [Section 4](#4-cross-workflow-patterns)). |
| 3 | `params` | `Dict[str, Any]` | No | `{}` | Key-value parameters passed to the capability. Supports `DynamicExpr` placeholders (see below). |
| 4 | `deps` | `List[str]` | No | `[]` | Step IDs this step depends on. Step executes only after all deps complete. |
| 5 | `prompt_template` | `Optional[str]` | No | `None` | Optional prompt template for LLM-backed capabilities. |
| 6 | `tools_granted` | `Optional[List[str]]` | No | `None` | Optional list of tools the capability is allowed to use. |
| 7 | `output_schema` | `Optional[Dict[str, Any]]` | No | `None` | JSON Schema for output validation (ORCH-15). If set, step output is validated against this schema. |
| 8 | `condition` | `Optional[ConditionExpr]` | No | `None` | Conditional execution expression (ORCH-16). Step is skipped if condition evaluates to `False`. Supports `AND`, `OR`, `NOT`, `EQ`, `NEQ`, `GT`, `LT` operators. Path references prior step results (e.g., `"s1.status"`, `"s1.result.data.count"`). V1: simple comparisons only (no function calls, per ADR-1.1.11 Q10). |
| 9 | `is_optional` | `bool` | No | `False` | If `True`, step failure does not fail the overall DAG. Independent steps continue. |
| 10 | `has_side_effects` | `bool` | No | `False` | If `True`, the step modifies external state (e.g., sends email, writes to database). Affects saga compensation decisions. |
| 11 | `compensation` | `Optional[str]` | No | `None` | Capability name for the compensation (undo) action. Invoked during saga rollback if this step succeeded but a downstream step failed. Only meaningful when `has_side_effects=True`. |
| 12 | `timeout_ms` | `Optional[int]` | No | `None` | Maximum execution time in milliseconds. Must be > 0 if set. |
| 13 | `required_context` | `Optional[List[str]]` | No | `None` | List of context keys this step requires from prior step outputs. |
| 14 | `safety_band_min` | `Optional[str]` | No | `None` | Minimum safety band level required for execution. Compared against the Fabric registry entry at compile time. Mismatches create a `PERMISSION_CHANGE` gap (see [Section 5](#5-proactive-gap-handling)). |

### Validation Rules

- `id` must be non-empty.
- `capability` must be non-empty.
- `timeout_ms` must be > 0 if set.
- Dependency validation (cross-step) is done at the `CommittedPlan` level: all `deps` values must reference valid step IDs, and the dependency graph must be acyclic (checked via Kahn's algorithm).

### DynamicExpr in Step Params

**Source**: `workflows/workflow_types.py` class `DynamicExpr` (line 70).

Step `params` values support dynamic expression placeholders that are resolved at **execution time** (not save time). This allows workflows to use current dates, times, and user preferences on each run.

**Syntax**: `${<namespace>.<field> [+/- <duration>]}`

**Regex**: `\$\{(\w+)\.(\w+)(?:\s*([+-])\s*(\d+[dhms]))?\}`

**V1 Namespaces**:

| Namespace | Field | Resolves To |
|-----------|-------|-------------|
| `date` | `today` | Current UTC date as `"YYYY-MM-DD"` string (via `SystemClock.utc_today()`). |
| `date` | `now` | Current UTC timestamp as `float` (via `SystemClock.utc_now()`). |
| `user` | `timezone` | User's timezone from `IStateReadPort` session persona (default: `"UTC"`). |
| `user` | `locale` | User's locale from `IStateReadPort` session persona (default: `"en-US"`). |

**Offset Arithmetic**:

Append `+` or `-` followed by a duration to shift the resolved value:

| Unit | Meaning | Seconds |
|------|---------|---------|
| `d` | Days | 86400 |
| `h` | Hours | 3600 |
| `m` | Minutes | 60 |
| `s` | Seconds | 1 |

**Examples**:

| Expression | Resolves To |
|-----------|-------------|
| `${date.today}` | `"2025-01-15"` (current UTC date) |
| `${date.today-7d}` | `"2025-01-08"` (7 days ago) |
| `${date.now}` | `1736956800.0` (current UTC timestamp) |
| `${date.now+1h}` | `1736960400.0` (timestamp + 3600 seconds) |
| `${user.timezone}` | `"America/New_York"` (from session state) |
| `${user.locale}` | `"en-US"` (from session state) |

**Resolution**: `WorkflowCompiler._resolve_steps()` (source: `workflows/workflow_compiler.py` line 260) walks each step's `params` dict and replaces any string value matching the `DynamicExpr` regex with the resolved value. Unknown namespaces or fields pass through unchanged.

### Dependency Graph (DAG)

Steps are organized as a Directed Acyclic Graph (DAG) via the `dependencies` field on `WorkflowSpec` and the `deps` field on each `PlanStep`.

- Steps with no dependencies execute in the first wave.
- Steps execute as soon as all their dependencies are satisfied.
- The DAGExecutor processes steps in waves: each wave contains all steps whose deps are satisfied.
- If a non-optional step fails, its dependents are skipped (unless `is_optional=True`).

```
s1 (no deps)  ──┐
                 ├──> s3 (deps: [s1, s2])
s2 (no deps)  ──┘
                      │
                      v
                 s4 (deps: [s3])
```

---

## 4. Cross-Workflow Patterns

**Source**: `workflows/cross_workflow_resolver.py` class `CrossWorkflowResolver` (line 159), class `WorkflowDepthGuard` (line 107).

A workflow step can invoke another workflow as a sub-workflow, enabling composable workflow hierarchies.

### Capability Pattern

To reference a sub-workflow, set the step's `capability` to:

```
workflow.run.<workflow_id>
```

**Regex**: `^workflow\.run\.(.+)$`

**Example**:

```yaml
steps:
  - id: "s3"
    capability: "workflow.run.wf-sub-report-generator"
    params:
      report_type: "weekly"
    deps: ["s1", "s2"]
```

### Detection

`CrossWorkflowResolver.is_workflow_step(step)` returns `True` when a step's capability matches `workflow.run.*`. The `DAGExecutor`'s `StepRunner` checks this before dispatching -- sub-workflow steps go to `CrossWorkflowResolver.resolve()` instead of `IFabricGatewayPort`.

### Resolution Flow

**Source**: `CrossWorkflowResolver.resolve()` (line 199).

1. **Extract workflow_id** from capability string (`workflow.run.<id>` -> `<id>`).
2. **Cycle detection**: Check if `workflow_id` is already in the `ancestor_ids` set. If yes, raise `WorkflowCycleError` (TERMINAL, non-recoverable).
3. **Depth check**: Verify `current_depth + 1 <= max_depth`. If exceeded, raise `MaxDepthError` (TERMINAL, non-recoverable).
4. **Lookup**: Fetch `WorkflowSpec` from `WorkflowRegistry`. If not found or inactive, return `None` (step fails upstream).
5. **Parameter merge** (ADR-1.1.11 Q6): Merge precedence is `parent_params[step.id]` > `step.params` > spec step params as-is.
6. **Compile**: Call `WorkflowCompiler.compile(spec)` to produce a `CommittedPlan`. Compilation resolves `DynamicExpr` values for the sub-workflow.
7. **Return**: The `CommittedPlan` is executed by a nested `DAGExecutor.execute()` call.

### Depth Limit

**Source**: `WorkflowDepthGuard` (line 107), configured via `max_workflow_depth` in `OrchestratorConfig`.

| Depth | Level | Description |
|-------|-------|-------------|
| 1 | Root | The top-level workflow triggered by scheduler or user. |
| 2 | Sub | First-level sub-workflow invoked by root. |
| 3 | Sub-sub | Second-level sub-workflow (deepest allowed). |

**Default maximum depth**: 3 levels. Configurable via `OrchestratorConfig.max_workflow_depth`.

Exceeding the limit raises `MaxDepthError`:

```
MaxDepthError: Workflow nesting depth 4 exceeds max 3
```

### Cycle Detection

The `WorkflowDepthGuard.detect_cycle()` method checks if a workflow_id already appears in the current resolution chain's `ancestor_ids` set.

Cycle detection happens at **resolve time** (not save time). This means:

- You CAN save a workflow that references another workflow that references the first.
- The cycle will be detected and raise `WorkflowCycleError` at execution time.

```
WorkflowCycleError: Workflow cycle detected: 'wf-abc' is already
an ancestor in the current resolution chain
```

### Parameter Override

When a parent step invokes a sub-workflow, parameters are merged with this precedence:

1. **Runtime overrides** (`parent_params[step.id]`) -- highest priority.
2. **Step params** (set at parent workflow save time) -- middle priority.
3. **Sub-workflow's own step params** -- lowest priority (base values).

### Sub-Workflow Results

The sub-workflow's `AggregatedResult` is wrapped in a single `StepResult` from the parent's perspective. The parent step succeeds if the sub-workflow completes, and fails if the sub-workflow fails.

### Concurrency Note

`CrossWorkflowResolver` does NOT acquire the `ConcurrencyGuard` -- it is already inside the parent DAG's execution context. The single-DAG lock (ORCH-02) covers the entire execution tree.

---

## 5. Proactive Gap Handling

**Source**: `workflows/gap_detector.py` class `ProactiveGapDetector` (line 82), `workflows/workflow_compiler.py` method `_detect_gaps()` (line 378).

The Orchestrator proactively detects when capability changes break saved workflows -- **before** the next scheduled run.

### How It Works

1. `ProactiveGapDetector` subscribes to `k1.fabric.capability.contract_updated.v1` events.
2. When a capability contract changes, the detector finds all active workflows that reference that capability.
3. Each affected workflow is re-compiled (via `WorkflowCompiler.compile()`) to detect gaps.
4. Gaps are classified (SPEC-9) and handled based on severity.

### Gap Types (V1)

| Gap Type | Severity | Description | Action |
|----------|----------|-------------|--------|
| `CAPABILITY_REMOVED` | LARGE | Capability no longer exists in the Fabric registry. | Save gap (PENDING), deactivate workflow, emit HIL notification. |
| `PERMISSION_CHANGE` | LARGE | `safety_band_min` value changed between step expectation and current registry entry. | Save gap (PENDING), deactivate workflow, emit HIL notification. |
| Auto-resolved params | SMALL | Parameters auto-resolved without conflict. | Emit auto-resolved notification. No workflow deactivation. |

Schema-level gap detection (field added/removed/renamed) is deferred to V2.

### Gap Lifecycle

**Source**: `types.py` class `ProactiveGap` (line 1168), enum `ProactiveGapStatus` (line 113).

```
PENDING  ->  ASKED  ->  RESOLVED       (human resolves)
PENDING  ->  AUTO_RESOLVED             (system auto-resolves)
```

**ProactiveGap fields**:

| Field | Type | Description |
|-------|------|-------------|
| `workflow_id` | `str` | Which workflow is affected. |
| `gap_type` | `str` | `"CAPABILITY_REMOVED"`, `"PERMISSION_CHANGE"`, or `"SCHEMA_DRIFT"` (V2). |
| `affected_step_id` | `str` | Which step in the workflow is affected. |
| `capability_name` | `str` | The capability that changed. |
| `old_contract_version` | `str` | Value from the saved WorkflowSpec. |
| `new_contract_version` | `str` | Current value in the Fabric registry (or `"N/A"` if removed). |
| `description` | `str` | Human-readable explanation. |
| `justification` | `str` | Why this gap matters. |
| `gap_id` | `str` | Auto-generated UUID. |
| `detected_at` | `float` | Detection timestamp. |
| `status` | `ProactiveGapStatus` | Current lifecycle state. |
| `question` | `Optional[str]` | Question to present to user (for ASKED state). |
| `resolved_value` | `Optional[str]` | Value provided by user or system upon resolution. |

### LARGE Gap Actions (ProactiveGapDetector)

**Source**: `workflows/gap_detector.py` method `_check_workflow()` (line 228).

When the compiler detects LARGE (PENDING) gaps for a workflow:

1. **Save each gap**: Persisted via `IWorkflowStoragePort.save_gap()`.
2. **Deactivate workflow**: `WorkflowSpec.active` set to `False` via `storage.save_workflow()`. This prevents the scheduler from firing the workflow.
3. **Emit HIL notification**: Delta event `k1.orchestration.gap.detected` with payload:

   ```json
   {
     "workflow_id": "wf-abc",
     "workflow_name": "Daily Health Check",
     "capability": "health.check.system",
     "gap_count": 1,
     "gap_types": ["CAPABILITY_REMOVED"],
     "action": "workflow_deactivated"
   }
   ```

### SMALL Gap Actions

When all gaps are auto-resolved:

1. **Emit notification**: Delta event `k1.orchestration.gap.auto_resolved` with payload:

   ```json
   {
     "workflow_id": "wf-abc",
     "capability": "health.check.system",
     "change_summary": "2 param(s) auto-resolved",
     "auto_resolved": ["param1", "param2"]
   }
   ```

2. Workflow remains active. No deactivation.

### Compile-Time Gap Detection (during execution)

**Source**: `workflows/workflow_compiler.py` method `compile()` (line 120).

Gap detection also runs at execution time (not just proactively). When `WorkflowRunSupervisor.start_run()` compiles a workflow:

- If LARGE gaps exist: compilation returns `CompilationResult(success=False)`. The run manifest is saved as `FAILED`. Gaps are persisted. HIL notification is emitted via `k1.orchestration.gap.detected`.
- If only SMALL gaps: compilation succeeds. Auto-resolved info is included in the `CompilationResult`.

### Debounce

**Source**: `gap_detector.py` constant `_DEBOUNCE_SECONDS = 5.0` (line 74).

If the same capability fires multiple contract update events within 5 seconds, only the first is processed. This prevents K0 sync floods from overwhelming the gap detector.

### Event Handler Architecture

The `ProactiveGapDetector`'s event handler (`_on_contract_updated`) is **synchronous** (IEventSubscriptionPort handlers are sync per 1.4.7). It enqueues the capability name into an `asyncio.Queue`. A separate `_process_loop()` task drains the queue asynchronously.

---

## 6. Concurrent Run Policy

**Source**: `workflows/workflow_supervisor.py` class `WorkflowRunSupervisor` (line 82), method `_enforce_single_active_run()` (line 327).

### Policy: Single Active Run Per Workflow (ADR-1.1.11 Q5)

In V1, each workflow can have at most **one** RUNNING execution at any time. If a workflow is re-triggered while a previous run is still RUNNING, the old run is **aborted**.

### Enforcement Mechanism

When `WorkflowRunSupervisor.start_run()` is called:

1. Query the latest run for this workflow: `storage.get_runs(workflow_id, limit=1)`.
2. If the latest run has `status == RUNNING`:
   a. Call `_abort_run(latest_run, trace_id)`.
   b. The old manifest transitions `RUNNING -> ABORTED`.
   c. An event `k1.orchestration.workflow.run_aborted` is emitted.
3. Proceed with the new run.

### Abort Idempotency

`_abort_run()` is idempotent:

- If the run is already in a terminal state (`COMPLETED`, `FAILED`, `ABORTED`), the abort is a no-op.
- Safe even if the DAG finishes between the check and the abort attempt.

### RunManifest Status Transitions

**Source**: `workflows/workflow_types.py` class `RunManifest` (line 233), enum `RunStatus` (line 214).

```
RUNNING  -->  COMPLETED   (DAG finished successfully)
RUNNING  -->  FAILED      (DAG failed or compilation failed)
RUNNING  -->  ABORTED     (concurrent run policy aborted this run)
```

Terminal states: `COMPLETED`, `FAILED`, `ABORTED`. No transition from terminal states.

**RunManifest is frozen** -- status transitions create NEW instances:

| Method | Transition | Additional Fields Set |
|--------|----------|----------------------|
| `RunManifest.create(...)` | -> `RUNNING` | `run_id` (UUID), `started_at` (now), `steps_total` |
| `manifest.complete(result_summary)` | `RUNNING -> COMPLETED` | `completed_at` (now), `result_summary`, `steps_completed = steps_total` |
| `manifest.fail(error)` | `RUNNING -> FAILED` | `completed_at` (now), `error_message` |
| `manifest.abort()` | `RUNNING -> ABORTED` | `completed_at` (now) |

### RunManifest Fields

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `str` | Unique execution identifier (UUID). |
| `workflow_id` | `str` | Which workflow was executed. |
| `version` | `str` | `WorkflowSpec.version` at execution time. |
| `compiled_hash` | `str` | SHA-256 of the compiled `CommittedPlan` (dedup key). |
| `trigger_type` | `str` | What triggered the run (`CRON` / `EVENT` / `MANUAL`). |
| `status` | `RunStatus` | Current status. |
| `started_at` | `float` | Execution start timestamp. |
| `completed_at` | `Optional[float]` | Execution end timestamp (`None` while `RUNNING`). |
| `result_summary` | `Optional[Dict]` | Serialized `AggregatedResult` summary (on `COMPLETED`). |
| `error_message` | `Optional[str]` | Error details (on `FAILED`). |
| `steps_completed` | `int` | Progress counter. |
| `steps_total` | `int` | Total steps in the `CommittedPlan`. |

### Result Delivery (PROD-4)

**Source**: `workflow_supervisor.py` method `deliver_result()` (line 242).

After a workflow completes, result delivery depends on session state:

| Scenario | Action |
|--------|--------|
| Session active | Emit result via `IDeltaEmitPort` (`k1.orchestration.workflow.result`). User sees the result immediately. |
| No session (e.g., cron at 3 AM) | Persist as deferred result via `IBridgeWritePort.submit_deferred_result()`. Concierge checks for pending results on next session start. |

---

## 7. Examples

### Example 1: Daily Health Check Workflow

A workflow that checks system health every morning and sends a notification.

```yaml
workflow_id: "wf-daily-health"
name: "Daily Health Check"
source_plan_id: "plan-health-001"
version: "1.0.0"
active: true

trigger:
  type: "CRON"
  schedule: "0 8 * * *"          # Every day at 08:00
  timezone: "America/New_York"
  enabled: true

steps:
  - id: "s1"
    capability: "health.check.system"
    params:
      target: "all"
      check_date: "${date.today}"   # Resolves to current date at runtime
    deps: []
    is_optional: false
    has_side_effects: false
    timeout_ms: 30000

  - id: "s2"
    capability: "health.analyze.results"
    params:
      severity_threshold: "warning"
    deps: ["s1"]
    is_optional: false
    has_side_effects: false

  - id: "s3"
    capability: "notification.send"
    params:
      channel: "email"
      template: "health_report"
      timezone: "${user.timezone}"   # Resolves to user's timezone
    deps: ["s2"]
    is_optional: true               # Notification failure doesn't fail the workflow
    has_side_effects: true           # Sending email is a side effect
    compensation: "notification.cancel"

dependencies:
  s2: ["s1"]
  s3: ["s2"]
```

**Execution flow**:

1. Every day at 08:00 Eastern, the scheduler fires this workflow.
2. Step `s1` checks system health (params include today's date via `${date.today}`).
3. Step `s2` analyzes results from `s1`.
4. Step `s3` sends an email notification. Even if it fails, the workflow is `DEGRADED` (not `FAILED`) because `is_optional=true`.
5. If the user is offline (running at 3 AM), results are deferred to the next session.

### Example 2: Weekly Report Workflow (with sub-workflow)

A workflow that generates a weekly report by composing data from multiple sub-workflows.

```yaml
workflow_id: "wf-weekly-report"
name: "Weekly Summary Report"
source_plan_id: "plan-report-007"
version: "1.0.0"
active: true

trigger:
  type: "CRON"
  schedule: "0 9 * * 1"             # Every Monday at 09:00
  timezone: "UTC"
  enabled: true

steps:
  - id: "s1"
    capability: "data.aggregate.usage"
    params:
      start_date: "${date.today-7d}"  # 7 days ago
      end_date: "${date.today}"       # Today
    deps: []
    is_optional: false
    has_side_effects: false
    timeout_ms: 60000

  - id: "s2"
    capability: "workflow.run.wf-daily-health"   # Sub-workflow invocation!
    params:
      target: "summary-only"
    deps: []
    is_optional: true                 # Report continues even if health sub-workflow fails
    has_side_effects: false

  - id: "s3"
    capability: "report.generate"
    params:
      format: "pdf"
      title: "Weekly Summary"
    deps: ["s1", "s2"]               # Waits for both data + health sub-workflow
    is_optional: false
    has_side_effects: true
    compensation: "report.delete"
    timeout_ms: 120000

dependencies:
  s3: ["s1", "s2"]
```

**Key points**:

- Step `s2` invokes the `wf-daily-health` workflow as a sub-workflow (depth 2).
- Steps `s1` and `s2` execute in parallel (wave 1) since they have no deps.
- Step `s3` waits for both to complete before generating the report.
- If `wf-daily-health` itself had a sub-workflow, that would be depth 3 (maximum allowed).
- `${date.today-7d}` resolves to 7 days before the current date.

### Example 3: Event-Driven Notification Workflow

A workflow triggered by an external event (e.g., data import completion).

```yaml
workflow_id: "wf-import-notify"
name: "Import Completion Notifier"
source_plan_id: "plan-notify-042"
version: "1.0.0"
active: true

trigger:
  type: "EVENT"
  event_topic: "k1.data.import.completed.v1"
  enabled: true

steps:
  - id: "s1"
    capability: "data.validate.import"
    params:
      validation_level: "full"
    deps: []
    is_optional: false
    has_side_effects: false
    timeout_ms: 15000
    output_schema:
      type: "object"
      required: ["valid", "record_count"]
      properties:
        valid:
          type: "boolean"
        record_count:
          type: "integer"

  - id: "s2"
    capability: "notification.send"
    params:
      channel: "slack"
      template: "import_complete"
    deps: ["s1"]
    condition:
      type: "EQ"
      path: "s1.result.valid"
      literal: true
    is_optional: false
    has_side_effects: true
    compensation: "notification.cancel"

  - id: "s3"
    capability: "notification.send"
    params:
      channel: "email"
      template: "import_failed"
      priority: "high"
    deps: ["s1"]
    condition:
      type: "EQ"
      path: "s1.result.valid"
      literal: false
    is_optional: false
    has_side_effects: true
    compensation: "notification.cancel"

dependencies:
  s2: ["s1"]
  s3: ["s1"]
```

**Key points**:

- Fires when `k1.data.import.completed.v1` event arrives on the K1 event bus.
- No time schedule -- purely event-driven.
- Step `s1` validates the import and produces structured output (validated against `output_schema`).
- Steps `s2` and `s3` use conditional execution (ORCH-16): `s2` fires on success, `s3` fires on failure.
- Both notification steps declare `compensation: "notification.cancel"` for saga rollback.
- `ConditionExpr` in V1 supports simple comparisons only (`EQ`, `NEQ`, `GT`, `LT`, `AND`, `OR`, `NOT`).

---

## Appendix: Compilation Pipeline

**Source**: `workflows/workflow_compiler.py` class `WorkflowCompiler` (line 85).

When a workflow is executed, the `WorkflowCompiler` transforms the frozen `WorkflowSpec` into a live `CommittedPlan`. Compilation happens at **execution time** (not save time) to ensure dynamic values reflect the current moment.

### Six-Step Compile Process

| Step | Operation | Details |
|------|-----------|---------|
| 1 | Deep-copy steps | Creates new `PlanStep` instances from the frozen spec (never mutates the original). |
| 2 | Resolve `DynamicExpr` | Walks each step's `params` dict and replaces `${...}` expressions with resolved values. User preferences loaded via `IStateReadPort` session persona. |
| 3 | Validate capabilities | Queries `IFabricGatewayPort.query_registry(step.capability)` for each step. |
| 4 | Detect gaps | Compares step expectations against current registry entries (SPEC-9 classification). |
| 5 | Build `CommittedPlan` | Constructs `CommittedPlan(plan_id="compiled-{wf_id}-{version}", ...)` from resolved steps and dependencies. |
| 6 | Compute hash | SHA-256 of serialized plan for `RunManifest` dedup. |

### CompilationResult

**Source**: `workflows/workflow_types.py` class `CompilationResult` (line 188).

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | `True` if no LARGE gaps; `False` if any `PENDING` gap exists. |
| `compiled_plan` | `Optional[CommittedPlan]` | The executable plan (only set when `success=True`). |
| `gaps` | `List[ProactiveGap]` | All detected gaps (both LARGE and SMALL). |
| `auto_resolved` | `List[str]` | Names of auto-resolved parameters. |
| `compiled_hash` | `Optional[str]` | SHA-256 hash (only set when `success=True`). |

---

## Appendix: Version Management

**Source**: `workflows/workflow_registry.py` class `WorkflowRegistry` (line 43), `workflows/workflow_types.py` class `WorkflowVersionPointer` (line 169).

### Version Scheme

- Semver format with major-only increments: `1.0.0` -> `2.0.0` -> `3.0.0`.
- Minor and patch reserved for future partial updates.
- Monotonic and append-only -- no rollback in V1.

### Version Bumps

`WorkflowRegistry.bump_version()` creates a new `WorkflowSpec` version with updated steps and dependencies:

1. Look up existing spec.
2. Create `WorkflowVersionPointer` from current state.
3. Increment major version.
4. Append `VersionEntry` to history.
5. Save updated spec with new version, steps, and dependencies.

### VersionEntry

| Field | Type | Description |
|-------|------|-------------|
| `version` | `str` | The new version string. |
| `created_at` | `float` | When this version was created. |
| `source_plan_id` | `str` | Plan ID this version was derived from. |
| `step_count` | `int` | Number of steps in this version. |
| `change_summary` | `str` | Human-readable description of what changed. |

---

## Appendix: Workflow Subsystem Component Map

All components in `k1/orchestrator/workflows/`:

| Component | File | Responsibility |
|-----------|------|----------------|
| `WorkflowSpec` | `workflow_types.py` | Frozen workflow definition (data). |
| `DynamicExpr` | `workflow_types.py` | Dynamic parameter placeholder (data). |
| `RunManifest` | `workflow_types.py` | Execution audit record (data). |
| `RunStatus` | `workflow_types.py` | Execution status enum (data). |
| `CompilationResult` | `workflow_types.py` | Compiler output (data). |
| `WorkflowVersionPointer` | `workflow_types.py` | Version tracking (data). |
| `VersionEntry` | `workflow_types.py` | Single version history record (data). |
| `WorkflowRegistry` | `workflow_registry.py` | CRUD operations (stateless, delegates to storage port). |
| `WorkflowCompiler` | `workflow_compiler.py` | Spec -> CommittedPlan transformation at execution time. |
| `WorkflowScheduler` | `workflow_scheduler.py` | Tick-based trigger evaluation and firing. |
| `WorkflowRunSupervisor` | `workflow_supervisor.py` | Execution lifecycle (start/complete/fail/abort/deliver). |
| `CrossWorkflowResolver` | `cross_workflow_resolver.py` | Sub-workflow resolution with depth + cycle guards. |
| `WorkflowDepthGuard` | `cross_workflow_resolver.py` | Nesting depth enforcement (max 3). |
| `ProactiveGapDetector` | `gap_detector.py` | Proactive gap detection on contract changes. |
| `SystemClock` | `system_clock.py` | UTC clock utility. |
| `FrozenClock` | `system_clock.py` | Test double for deterministic tests. |
| `WorkflowEngine` | `workflow_engine.py` | Facade composing all components into `WorkflowEngineLike`. |

### Factory Wiring (Step 14b)

**Source**: `factory.py` step 14b (line ~530).

Construction order:

```
SystemClock
    |
    v
WorkflowRegistry(storage_port)
    |
    v
WorkflowCompiler(fabric, delta, storage, state, clock)
    |
    v
WorkflowScheduler(storage, mailbox, state, clock, tick_interval)
    |
    v
WorkflowDepthGuard(max_depth=config.max_workflow_depth)
    |
    v
CrossWorkflowResolver(registry, compiler, depth_guard)
    |
    v
WorkflowRunSupervisor(registry, compiler, storage, delta, bridge)
    |
    v
ProactiveGapDetector(registry, compiler, storage, event, delta)
    |
    v
WorkflowEngine(supervisor, dag_executor, constraint_resolver,
               registry, compiler, scheduler, cross_resolver,
               gap_detector, delta, bridge)
```

### Events Emitted by Workflow Subsystem

| Event Topic | Producer | Description |
|------------|----------|-------------|
| `k1.orchestration.workflow.run_started` | `WorkflowRunSupervisor` | New run started. |
| `k1.orchestration.workflow.run_completed` | `WorkflowRunSupervisor` | Run completed successfully. |
| `k1.orchestration.workflow.run_failed` | `WorkflowRunSupervisor` | Run failed. |
| `k1.orchestration.workflow.run_aborted` | `WorkflowRunSupervisor` | Run aborted by concurrent policy. |
| `k1.orchestration.workflow.result` | `WorkflowRunSupervisor` | Result delivered to active session. |
| `k1.orchestration.gap.detected` | `WorkflowCompiler` / `ProactiveGapDetector` | LARGE gap detected -- workflow deactivated. |
| `k1.orchestration.gap.auto_resolved` | `ProactiveGapDetector` | SMALL gap auto-resolved. |

### Events Consumed by Workflow Subsystem

| Event Topic | Consumer | Action |
|------------|----------|--------|
| `k1.fabric.capability.contract_updated.v1` | `ProactiveGapDetector` | Re-compile affected workflows for gap detection. |
