# Schema Whiteboard: Orchestrator Pre-Implementation Artifacts

> **Status**: DRAFT v1
> **Purpose**: Define all schemas, contracts, and configuration that MUST exist before M1 contract registration and M2 implementation begin.
> **Gate**: This document is a GATE 2 (Contract Discovery) prerequisite.

---

## Table of Contents

1. [ProcessingContext Type (P0)](#1-processingcontext-type-p0)
2. [Centralized Configuration Schema (P0)](#2-centralized-configuration-schema-p0)
3. [Event Payload Schemas (P0)](#3-event-payload-schemas-p0)
4. [Contract YAML Format Spec (P0)](#4-contract-yaml-format-spec-p0)
5. [Admin API Surface (P1)](#5-admin-api-surface-p1)
6. [Health Check Spec (P1)](#6-health-check-spec-p1)
7. [Circuit Breaker Configuration (P1)](#7-circuit-breaker-configuration-p1)
8. [Guard Pipeline Ordering (P1)](#8-guard-pipeline-ordering-p1)
9. [Mailbox Message Durability (P1)](#9-mailbox-message-durability-p1)
10. [Planner-Orchestrator Protocol (P0)](#10-planner-orchestrator-protocol-p0)

---

## 1. ProcessingContext Type (P0)

**Gap**: ProcessingContext is referenced by tracing (8.3.1), every service method, every guard, ErrorRouter, and saga compensation -- but is buried in issue 1.2.20 item 16 within a batch of 16 types. It needs a standalone definition and its own issue number.

**Impact**: Blocks M2 -- every service method signature depends on this type.

### 1.1 Type Definition

```python
@dataclass
class ProcessingContext:
    """
    Request-scoped correlation context carried through all service calls.

    Created at OrchestratorService.process() entry point.
    Passed as parameter to every internal method for trace correlation,
    metrics attribution, and structured logging.

    NEVER stored in PendingPlanContext/PendingHILContext directly --
    trace_id is extracted and stored as a field on those types.
    """

    # --- Identity ---
    trace_id: str                          # cognitive_trace_id from inbound message
    request_id: str                        # envelope_id or workflow request_id
    tier: str                              # "MEDIUM" | "HIGH" | "WORKFLOW"

    # --- Timing ---
    created_at: float                      # time.time() at process() entry
    deadline_ms: Optional[int] = None      # absolute deadline (created_at + timeout_ms)

    # --- Execution tracking (populated during DAG) ---
    dag_id: Optional[str] = None           # set when DAGExecutor.execute() starts
    workflow_id: Optional[str] = None      # set when processing WorkflowRunRequest
    parent_trace_id: Optional[str] = None  # set for cross-workflow child executions
    current_wave: Optional[int] = None     # updated at each wave boundary
    current_step_id: Optional[str] = None  # updated at each step start

    # --- Budget snapshots (read from CommittedPlan or config) ---
    # token_budget_max: Optional[int] = None           # **V1 REMOVED** — no upstream data source (Fabric CapabilityResult has no token/cost fields). Re-add in V2 when LLM providers report usage metadata.
    # cost_budget_max_usd: Optional[float] = None      # **V1 REMOVED** — same reason as token_budget_max.
```

### 1.2 Lifecycle

```
OrchestratorService.process(message)
    |
    +-- ctx = ProcessingContext(
    |       trace_id=message.trace_id,
    |       request_id=message.envelope_id or message.request_id,
    |       tier=message.tier or "WORKFLOW",
    |       created_at=time.time(),
    |       deadline_ms=message.timeout_ms
    |   )
    |
    +-- route_task(message, ctx)
    |       |
    |       +-- dispatch_medium(envelope, ctx)
    |       |       +-- StepRunner.execute(step, ctx)
    |       |       +-- aggregate(results, ctx)
    |       |
    |       +-- dispatch_high(envelope, ctx)
    |       |       +-- ctx stored in PendingPlanContext.trace_id
    |       |       +-- (returns to mailbox loop)
    |       |
    |       +-- dispatch_workflow(request, ctx)
    |               +-- WorkflowEngine.execute(spec, ctx)
    |
    +-- receive_plan(committed_plan, ctx_reconstructed)
            +-- ctx.dag_id = new_dag_id
            +-- DAGExecutor.execute(plan, ctx)
                    +-- ctx.current_wave = wave_index (per wave)
                    +-- StepRunner.execute(step, ctx)
                    +-- Guards.evaluate(ctx) (all 8 guards)
                    +-- ErrorRouter.classify(error, ctx)
                    +-- SagaCompensator.compensate(records, ctx)
```

### 1.3 Rules

| Rule | Description |
|------|-------------|
| IMMUTABLE identity | `trace_id`, `request_id`, `tier` never change after creation |
| MUTABLE tracking | `dag_id`, `current_wave`, `current_step_id` updated in-place during execution |
| NOT serialized | ProcessingContext is never persisted to WAL or sent over event bus |
| NOT stored in pending dicts | Only `trace_id` is extracted into `PendingPlanContext.trace_id` |
| Thread-local equivalent | In asyncio, passed explicitly (not via contextvars) to maintain visibility |
| Structured log source | Every structured log entry extracts fields from ctx |

### 1.4 Action Required

- Promote from issue 1.2.20 (batch) to standalone issue **1.2.21** in the implementation plan
- Add `ProcessingContext` as first parameter (after `self`) to all service method signatures in M2 issues

---

## 2. Centralized Configuration Schema (P0)

**Gap**: Configuration values are scattered across 9+ subsystems with no centralized schema, validation, or environment variable mapping.

**Impact**: Blocks M2 -- services need to know where config comes from.

### 2.1 Configuration Dataclass

```python
@dataclass(frozen=True)
class OrchestratorConfig:
    """
    Centralized Orchestrator configuration.

    Loaded once at OrchestratorFactory construction time.
    Immutable after creation -- restart required for changes.

    Source priority: env vars > config file > defaults.
    """

    # --- Mailbox ---
    mailbox_depth: int = 256                        # max messages in priority queue
    mailbox_backpressure: str = "REJECT"            # REJECT | DROP_OLDEST
    mailbox_wal_enabled: bool = False               # V1: False (in-memory), V2: True (durable)

    # --- Concurrency ---
    max_concurrent_dags: int = 1                    # V1: always 1 (ORCH-02)
    max_pending_plans: int = 50                     # hard cap on PendingPlanContext dict
    max_pending_hil: int = 20                       # hard cap on PendingHILContext dict

    # --- Timeouts (ms) ---
    plan_request_timeout_ms: int = 45_000           # CB_PLANNER timeout
    hil_constraint_timeout_ms: int = 60_000         # HIL constraint resolution
    hil_override_timeout_ms: int = 30_000           # HIL user override
    step_default_timeout_ms: int = 30_000           # per-step Fabric call timeout
    context_reap_interval_ms: int = 5_000           # stale context sweep interval
    shutdown_grace_period_ms: int = 30_000          # max wait for active DAG on shutdown

    # --- Retry ---
    step_max_retries: int = 2                       # max retries per step (transient)
    step_retry_base_delay_ms: int = 100             # exponential backoff base
    step_retry_max_delay_ms: int = 5_000            # exponential backoff cap

    # --- Guards ---
    # token_budget_warn_pct: float = 0.80             # **V1 REMOVED** — no upstream data source. Re-add in V2.
    # token_budget_skip_pct: float = 0.95             # **V1 REMOVED** — same.
    # cost_budget_warn_pct: float = 0.80              # **V1 REMOVED** — same.
    # cost_budget_skip_pct: float = 0.95              # **V1 REMOVED** — same.
    # quality_threshold_low: float = 0.3              # **V1 REMOVED** — Fabric CapabilityResult has no quality_score. Re-add in V2.
    # quality_threshold_high: float = 0.7             # **V1 REMOVED** — same.
    max_micro_replans: int = 1                      # ORCH-13
    substep_rate_limit_ms: int = 500                # max 1 sub-step delta per step per interval

    # --- Workflow ---
    max_workflow_depth: int = 3                     # ORCH-12
    workflow_db_path: str = "data/orchestrator_workflows.db"  # SQLite path
    scheduler_tick_interval_ms: int = 1_000         # scheduler loop interval

    # --- MCP Connectors ---
    mcp_config_path: str = "config/mcp_servers.yaml"
    mcp_rediscovery_interval_ms: int = 60_000       # periodic re-scan interval
    mcp_sandbox_cpu_pct: int = 100                  # CPU limit per connector process
    mcp_sandbox_memory_mb: int = 512                # memory limit per connector process
    mcp_sandbox_timeout_ms: int = 30_000            # per-call timeout

    # --- Circuit Breakers (Orchestrator-owned only; see Section 7 for full spec) ---
    # NOTE: CB_FABRIC, CB_PLANNER, CB_MCP are owned by Concierge's FabricOrchestratorAdapter.
    # The Orchestrator only owns CB_BRIDGE for its fire-and-forget audit writes.
    cb_bridge_failure_threshold: int = 5
    cb_bridge_recovery_timeout_ms: int = 30_000

    # --- Observability ---
    metrics_enabled: bool = True
    structured_log_level: str = "INFO"              # DEBUG | INFO | WARN | ERROR
    trace_propagation: bool = True

    # --- Admin ---
    admin_enabled: bool = False                     # V1: disabled by default
    admin_bind: str = "127.0.0.1:9091"              # admin API listen address
```

### 2.2 Environment Variable Mapping

| Config Field | Env Var | Example |
|-------------|---------|---------|
| `mailbox_depth` | `ORCH_MAILBOX_DEPTH` | `512` |
| `plan_request_timeout_ms` | `ORCH_PLAN_TIMEOUT_MS` | `60000` |
| `step_max_retries` | `ORCH_STEP_MAX_RETRIES` | `3` |
| ~~`quality_threshold_high`~~ | ~~`ORCH_QUALITY_THRESHOLD_HIGH`~~ | ~~`0.8`~~ **V1 REMOVED** |
| `max_workflow_depth` | `ORCH_MAX_WORKFLOW_DEPTH` | `3` |
| `workflow_db_path` | `ORCH_WORKFLOW_DB_PATH` | `/data/orch.db` |
| `mcp_config_path` | `ORCH_MCP_CONFIG_PATH` | `/etc/mcp_servers.yaml` |
| `cb_bridge_failure_threshold` | `ORCH_CB_BRIDGE_THRESHOLD` | `5` |
| `metrics_enabled` | `ORCH_METRICS_ENABLED` | `true` |
| `admin_enabled` | `ORCH_ADMIN_ENABLED` | `true` |
| `admin_bind` | `ORCH_ADMIN_BIND` | `0.0.0.0:9091` |

**Convention**: All env vars prefixed with `ORCH_`. Snake_case field -> SCREAMING_SNAKE env var.

### 2.3 Loading Strategy

```python
@classmethod
def from_env(cls, config_path: Optional[str] = None) -> "OrchestratorConfig":
    """
    Load config with priority: env vars > config file > defaults.

    1. Start with dataclass defaults
    2. If config_path provided, overlay from YAML file
    3. Overlay from environment variables (ORCH_* prefix)
    4. Validate all values (ranges, paths, enums)
    5. Return frozen instance
    """
```

### 2.4 Validation Rules

| Field | Constraint | Error |
|-------|-----------|-------|
| `mailbox_depth` | 1 <= x <= 10000 | `ValueError: mailbox_depth must be 1-10000` |
| `max_concurrent_dags` | x == 1 (V1) | `ValueError: V1 supports only single-DAG` |
| `step_max_retries` | 0 <= x <= 10 | `ValueError: step_max_retries must be 0-10` |
| ~~`quality_threshold_low`~~ | ~~0.0 <= x <= 1.0~~ | **V1 REMOVED** |
| ~~`quality_threshold_high`~~ | ~~x > quality_threshold_low~~ | **V1 REMOVED** |
| `max_workflow_depth` | 1 <= x <= 10 | `ValueError: max_workflow_depth must be 1-10` |
| `workflow_db_path` | parent dir exists | `ValueError: DB directory does not exist` |
| `cb_bridge_failure_threshold` | x >= 1 | `ValueError: CB threshold must be >= 1` |
| `cb_bridge_recovery_timeout_ms` | x >= 1000 | `ValueError: CB recovery must be >= 1s` |

### 2.5 File Location

- **Dataclass**: `k1/orchestrator/config.py`
- **Config file format**: `config/orchestrator.yaml` (optional overlay)
- **Loaded by**: `OrchestratorFactory` at construction (step 1 of 15-step sequence)
- **Injected into**: Every service constructor that needs config values

### 2.6 Action Required

- Add new issue **1.2.22** to Epic 1.2: "OrchestratorConfig dataclass"
- Add `config.py` to M1 required_files list
- Update OrchestratorFactory (6.2.1) step 1 to load config

---

## 3. Event Payload Schemas (P0)

**Gap**: 17 emitted events (V1; was 20 pre-phantom-field removal) and 12 consumed events have topic names from 1.2.17 but zero formal JSON Schema definitions. Contract tests (7.4.4) validate "payload schemas match contract definitions" -- those definitions don't exist.

**Impact**: Blocks M1 issue 1.3.1 (contract registration) and M7 issue 7.4.4 (event catalog validation).

### 3.1 Schema File Convention

Following the Fabric pattern from `wiring.contract.yaml`:

```
k1/contracts/schemas/events/orchestration/
    task.accepted.v1.json
    plan.requested.v1.json
    dag.started.v1.json
    dag.completed.v1.json
    dag.micro_replan.v1.json
    # dag.budget_warning.v1.json      # **V1 REMOVED** — no upstream token/cost data
    # dag.budget_exhausted.v1.json     # **V1 REMOVED** — same
    step.started.v1.json
    step.completed.v1.json
    step.failed.v1.json
    step.cancelled.v1.json
    step.skipped.v1.json
    step.retrying.v1.json
    step.schema_retry.v1.json
    # step.quality_retry.v1.json       # **V1 REMOVED** — no upstream quality_score data
    saga.compensating.v1.json
    delta.v1.json
    workflow.triggered.v1.json
    workflow.completed.v1.json
    mcp.tool_registered.v1.json
```

### 3.2 Common Envelope (all events)

Every Orchestrator event payload wraps in a common envelope:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "k1://schemas/events/orchestration/envelope.schema.json",
  "type": "object",
  "required": ["topic", "timestamp", "trace_id", "payload"],
  "properties": {
    "topic": {
      "type": "string",
      "pattern": "^k1\\.orchestration\\..+\\.v[0-9]+$"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "trace_id": {
      "type": "string",
      "format": "uuid",
      "description": "ORCH-09: cognitive_trace_id on ALL events"
    },
    "source": {
      "type": "string",
      "const": "orchestrator"
    },
    "version": {
      "type": "string",
      "pattern": "^v[0-9]+$"
    },
    "payload": {
      "type": "object"
    }
  }
}
```

### 3.3 Emitted Event Payload Schemas (17 events)

#### 3.3.1 task.accepted.v1

```json
{
  "$id": "k1://schemas/events/orchestration/task.accepted.v1.json",
  "type": "object",
  "required": ["envelope_id", "intent", "tier", "trace_id"],
  "properties": {
    "envelope_id": { "type": "string", "format": "uuid" },
    "intent": { "type": "string" },
    "tier": { "type": "string", "enum": ["MEDIUM", "HIGH"] },
    "capabilities": {
      "type": "array",
      "items": { "type": "string" }
    },
    "trace_id": { "type": "string", "format": "uuid" },
    "accepted_at": { "type": "string", "format": "date-time" }
  }
}
```

#### 3.3.2 plan.requested.v1

```json
{
  "$id": "k1://schemas/events/orchestration/plan.requested.v1.json",
  "type": "object",
  "required": ["request_id", "intent", "trace_id"],
  "properties": {
    "request_id": { "type": "string", "format": "uuid" },
    "intent": { "type": "string" },
    "constraints": { "type": "object" },
    "timeout_ms": { "type": "integer", "minimum": 0 },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.3 dag.started.v1

```json
{
  "$id": "k1://schemas/events/orchestration/dag.started.v1.json",
  "type": "object",
  "required": ["dag_id", "plan_id", "total_steps", "total_waves", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "plan_id": { "type": "string", "format": "uuid" },
    "total_steps": { "type": "integer", "minimum": 1 },
    "total_waves": { "type": "integer", "minimum": 1 },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.4 step.started.v1

```json
{
  "$id": "k1://schemas/events/orchestration/step.started.v1.json",
  "type": "object",
  "required": ["dag_id", "step_id", "capability", "wave_index", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "step_id": { "type": "string" },
    "capability": { "type": "string" },
    "wave_index": { "type": "integer", "minimum": 0 },
    "params": { "type": "object" },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.5 step.completed.v1

```json
{
  "$id": "k1://schemas/events/orchestration/step.completed.v1.json",
  "type": "object",
  "required": ["dag_id", "step_id", "capability", "status", "duration_ms", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "step_id": { "type": "string" },
    "capability": { "type": "string" },
    "status": { "type": "string", "const": "COMPLETED" },
    "duration_ms": { "type": "integer", "minimum": 0 },
    "retry_attempts": { "type": "integer", "minimum": 0 },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.6 step.failed.v1

```json
{
  "$id": "k1://schemas/events/orchestration/step.failed.v1.json",
  "type": "object",
  "required": ["dag_id", "step_id", "capability", "error_code", "error_message", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "step_id": { "type": "string" },
    "capability": { "type": "string" },
    "error_code": {
      "type": "string",
      "enum": ["TRANSIENT", "PERMANENT", "CIRCUIT_OPEN", "NOT_FOUND", "INTERNAL", "TIMEOUT", "SCHEMA_VIOLATION"]
    },
    "error_message": { "type": "string" },
    "retry_attempts": { "type": "integer", "minimum": 0 },
    "has_side_effects": { "type": "boolean" },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.7 step.cancelled.v1

```json
{
  "$id": "k1://schemas/events/orchestration/step.cancelled.v1.json",
  "type": "object",
  "required": ["dag_id", "step_id", "reason", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "step_id": { "type": "string" },
    "reason": {
      "type": "string",
      "enum": ["USER_INTERRUPT", "DAG_ABORT", "WORKFLOW_ABORT", "SHUTDOWN"]
    },
    "wave_index": { "type": "integer", "minimum": 0 },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.8 step.skipped.v1

```json
{
  "$id": "k1://schemas/events/orchestration/step.skipped.v1.json",
  "type": "object",
  "required": ["dag_id", "step_id", "skip_reason", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "step_id": { "type": "string" },
    "skip_reason": {
      "type": "string",
      "enum": [
        "CONDITIONAL_EDGE_FALSE",
        "DEPENDENCY_FAILED",
        "GUARD_SKIP"
      ]
    },
    "condition_expr": { "type": ["string", "null"] },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.9 step.retrying.v1

```json
{
  "$id": "k1://schemas/events/orchestration/step.retrying.v1.json",
  "type": "object",
  "required": ["dag_id", "step_id", "attempt", "reason", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "step_id": { "type": "string" },
    "attempt": { "type": "integer", "minimum": 1 },
    "max_attempts": { "type": "integer", "minimum": 1 },
    "reason": {
      "type": "string",
      "enum": ["TRANSIENT_ERROR", "TIMEOUT"]
    },
    "delay_ms": { "type": "integer", "minimum": 0 },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.10 step.schema_retry.v1

```json
{
  "$id": "k1://schemas/events/orchestration/step.schema_retry.v1.json",
  "type": "object",
  "required": ["dag_id", "step_id", "attempt", "schema_errors", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "step_id": { "type": "string" },
    "attempt": { "type": "integer", "minimum": 1 },
    "schema_errors": {
      "type": "array",
      "items": { "type": "string" }
    },
    "schema_hint": { "type": "string" },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### ~~3.3.11 step.quality_retry.v1~~ **V1 REMOVED**

> **V1 REMOVED** — Fabric `CapabilityResult` has no `quality_score` field. No upstream data source exists.
> Re-add in V2 when LLM providers report quality metadata.

<!--
```json
{
  "$id": "k1://schemas/events/orchestration/step.quality_retry.v1.json",
  "type": "object",
  "required": ["dag_id", "step_id", "attempt", "quality_score", "threshold", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "step_id": { "type": "string" },
    "attempt": { "type": "integer", "minimum": 1 },
    "quality_score": { "type": "number", "minimum": 0, "maximum": 1 },
    "threshold": { "type": "number", "minimum": 0, "maximum": 1 },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```
-->

#### 3.3.12 saga.compensating.v1

```json
{
  "$id": "k1://schemas/events/orchestration/saga.compensating.v1.json",
  "type": "object",
  "required": ["dag_id", "compensation_records", "trigger_reason", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "trigger_reason": {
      "type": "string",
      "enum": ["STEP_FAILURE", "INTERRUPT", "SHUTDOWN", "WORKFLOW_ABORT"]
    },
    "compensation_records": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["record_id", "step_id", "compensation_capability", "status"],
        "properties": {
          "record_id": { "type": "string", "format": "uuid" },
          "step_id": { "type": "string" },
          "compensation_capability": { "type": "string" },
          "status": {
            "type": "string",
            "enum": ["PENDING", "EXECUTED", "FAILED", "DEAD_LETTERED"]
          },
          "error_detail": { "type": ["string", "null"] }
        }
      }
    },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.13 dag.micro_replan.v1

```json
{
  "$id": "k1://schemas/events/orchestration/dag.micro_replan.v1.json",
  "type": "object",
  "required": ["dag_id", "original_plan_id", "replan_request_id", "trigger_step_id", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "original_plan_id": { "type": "string", "format": "uuid" },
    "replan_request_id": { "type": "string", "format": "uuid" },
    "trigger_step_id": { "type": "string" },
    "trigger_reason": { "type": "string" },
    "completed_steps": { "type": "integer", "minimum": 0 },
    "remaining_steps": { "type": "integer", "minimum": 0 },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### ~~3.3.14 dag.budget_warning.v1~~ **V1 REMOVED**

> **V1 REMOVED** — No upstream token/cost data from Fabric `CapabilityResult`.
> Re-add in V2 when LLM providers report usage metadata.

<!--
```json
{
  "$id": "k1://schemas/events/orchestration/dag.budget_warning.v1.json",
  "type": "object",
  "required": ["dag_id", "budget_type", "utilization_pct", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "budget_type": { "type": "string", "enum": ["TOKEN", "COST"] },
    "utilization_pct": { "type": "number", "minimum": 0, "maximum": 1 },
    "accumulated": { "type": "number", "minimum": 0 },
    "budget_max": { "type": "number", "minimum": 0 },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```
-->

#### ~~3.3.15 dag.budget_exhausted.v1~~ **V1 REMOVED**

> **V1 REMOVED** — No upstream token/cost data from Fabric `CapabilityResult`.
> Re-add in V2 when LLM providers report usage metadata.

<!--
```json
{
  "$id": "k1://schemas/events/orchestration/dag.budget_exhausted.v1.json",
  "type": "object",
  "required": ["dag_id", "budget_type", "accumulated", "budget_max", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "budget_type": { "type": "string", "enum": ["TOKEN", "COST"] },
    "accumulated": { "type": "number", "minimum": 0 },
    "budget_max": { "type": "number", "minimum": 0 },
    "steps_skipped": { "type": "integer", "minimum": 0 },
    "steps_remaining": { "type": "integer", "minimum": 0 },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```
-->

#### 3.3.16 dag.completed.v1

```json
{
  "$id": "k1://schemas/events/orchestration/dag.completed.v1.json",
  "type": "object",
  "required": ["dag_id", "plan_id", "status", "total_steps", "completed", "failed", "duration_ms", "trace_id"],
  "properties": {
    "dag_id": { "type": "string", "format": "uuid" },
    "plan_id": { "type": ["string", "null"], "format": "uuid" },
    "status": {
      "type": "string",
      "enum": ["COMPLETED", "FAILED", "PARTIAL_SUCCESS", "INTERRUPTED", "DEGRADED"]
    },
    "total_steps": { "type": "integer", "minimum": 0 },
    "completed": { "type": "integer", "minimum": 0 },
    "failed": { "type": "integer", "minimum": 0 },
    "cancelled": { "type": "integer", "minimum": 0 },
    "skipped": { "type": "integer", "minimum": 0 },
    "duration_ms": { "type": "integer", "minimum": 0 },
    "compensation_count": { "type": "integer", "minimum": 0 },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.17 delta.v1

```json
{
  "$id": "k1://schemas/events/orchestration/delta.v1.json",
  "type": "object",
  "required": ["delta_type", "trace_id"],
  "properties": {
    "delta_type": {
      "type": "string",
      "enum": [
        "PROGRESS",
        "SUBSTEP",
        "ERROR_DIAGNOSTIC",
        "HIL_REQUEST",
        "DEGRADATION_NOTICE"
      ]
    },
    "dag_id": { "type": ["string", "null"] },
    "step_id": { "type": ["string", "null"] },
    "progress_pct": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
    "message": { "type": ["string", "null"] },
    "data": { "type": ["object", "null"] },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.18 workflow.triggered.v1

```json
{
  "$id": "k1://schemas/events/orchestration/workflow.triggered.v1.json",
  "type": "object",
  "required": ["workflow_id", "trigger_type", "execution_id", "trace_id"],
  "properties": {
    "workflow_id": { "type": "string" },
    "execution_id": { "type": "string", "format": "uuid" },
    "trigger_type": { "type": "string", "enum": ["CRON", "EVENT", "MANUAL"] },
    "trigger_context": { "type": "object" },
    "depth": { "type": "integer", "minimum": 0, "maximum": 3 },
    "parent_trace_id": { "type": ["string", "null"], "format": "uuid" },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.19 workflow.completed.v1

```json
{
  "$id": "k1://schemas/events/orchestration/workflow.completed.v1.json",
  "type": "object",
  "required": ["workflow_id", "execution_id", "status", "trace_id"],
  "properties": {
    "workflow_id": { "type": "string" },
    "execution_id": { "type": "string", "format": "uuid" },
    "status": {
      "type": "string",
      "enum": ["COMPLETED", "FAILED", "INTERRUPTED", "ABORTED"]
    },
    "step_count": { "type": "integer", "minimum": 0 },
    "duration_ms": { "type": "integer", "minimum": 0 },
    "trigger_type": { "type": "string", "enum": ["CRON", "EVENT", "MANUAL"] },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.3.20 mcp.tool_registered.v1

```json
{
  "$id": "k1://schemas/events/orchestration/mcp.tool_registered.v1.json",
  "type": "object",
  "required": ["connector_id", "tool_name", "server_uri", "trace_id"],
  "properties": {
    "connector_id": { "type": "string" },
    "tool_name": { "type": "string" },
    "server_uri": { "type": "string" },
    "server_type": { "type": "string", "enum": ["LOCAL", "REMOTE", "K0_PROXY"] },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

### 3.4 Consumed Event Payload Schemas (12 events)

The Orchestrator subscribes to these events produced by other modules. Schemas define what payload structure the Orchestrator expects.

#### 3.4.1 k1.planner.plan.ready.v1

```json
{
  "$id": "k1://schemas/events/planner/plan.ready.v1.json",
  "type": "object",
  "required": ["plan_id", "request_id", "steps", "dependencies", "trace_id"],
  "properties": {
    "plan_id": { "type": "string", "format": "uuid" },
    "request_id": { "type": "string", "format": "uuid" },
    "intent": { "type": "string" },
    "steps": {
      "type": "array",
      "items": { "$ref": "#/$defs/PlanStep" },
      "minItems": 1
    },
    "dependencies": {
      "type": "object",
      "additionalProperties": {
        "type": "array",
        "items": { "type": "string" }
      }
    },
    "trace_id": { "type": "string", "format": "uuid" }
  },
  "_V1_REMOVED": "token_budget_max and cost_budget_max_usd fields removed -- no upstream data source. Re-add in V2.",
  "$defs": {
    "PlanStep": {
      "type": "object",
      "required": ["id", "capability"],
      "properties": {
        "id": { "type": "string" },
        "capability": { "type": "string" },
        "params": { "type": "object" },
        "deps": { "type": "array", "items": { "type": "string" } },
        "prompt_template": { "type": ["string", "null"] },
        "tools_granted": { "type": ["array", "null"], "items": { "type": "string" } },
        "output_schema": { "type": ["object", "null"] },
        "condition": { "type": ["object", "null"] },
        "is_optional": { "type": "boolean" },
        "has_side_effects": { "type": "boolean" },
        "compensation": { "type": ["string", "null"] },
        "timeout_ms": { "type": ["integer", "null"], "minimum": 1 },
        "required_context": { "type": ["array", "null"], "items": { "type": "string" } }
      }
    }
  }
}
```

#### 3.4.2 k1.planner.plan.failed.v1

```json
{
  "$id": "k1://schemas/events/planner/plan.failed.v1.json",
  "type": "object",
  "required": ["request_id", "reason", "trace_id"],
  "properties": {
    "request_id": { "type": "string", "format": "uuid" },
    "reason": {
      "type": "string",
      "enum": ["CAPABILITY_NOT_FOUND", "CONSTRAINT_UNSATISFIABLE", "TIMEOUT", "INTERNAL_ERROR"]
    },
    "detail": { "type": "string" },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.3 k1.planner.plan.cancelled.v1

```json
{
  "$id": "k1://schemas/events/planner/plan.cancelled.v1.json",
  "type": "object",
  "required": ["request_id", "reason", "trace_id"],
  "properties": {
    "request_id": { "type": "string", "format": "uuid" },
    "reason": { "type": "string" },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.4 k1.planner.micro_replan.ready.v1

```json
{
  "$id": "k1://schemas/events/planner/micro_replan.ready.v1.json",
  "type": "object",
  "required": ["replan_request_id", "original_plan_id", "revised_steps", "trace_id"],
  "properties": {
    "replan_request_id": { "type": "string", "format": "uuid" },
    "original_plan_id": { "type": "string", "format": "uuid" },
    "revised_steps": {
      "type": "array",
      "items": { "type": "object" },
      "minItems": 1
    },
    "revised_dependencies": {
      "type": "object",
      "additionalProperties": {
        "type": "array",
        "items": { "type": "string" }
      }
    },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.5 k1.capability.completed.v1 (from Fabric)

```json
{
  "$id": "k1://schemas/events/fabric/capability.completed.v1.json",
  "type": "object",
  "required": ["request_id", "capability_name", "status", "trace_id"],
  "properties": {
    "request_id": { "type": "string", "format": "uuid" },
    "capability_name": { "type": "string" },
    "status": { "type": "string", "enum": ["SUCCESS", "FAILURE", "TIMEOUT", "DEGRADED"] },
    "data": { "type": ["object", "null"] },
    "execution_time_ms": { "type": "integer" },
    "discoveries": {
      "type": ["array", "null"],
      "items": {
        "type": "object",
        "properties": {
          "key": { "type": "string", "description": "Discovery identifier (e.g. entity name, preference key)" },
          "value": { "description": "Discovered value (any JSON type)" },
          "source": { "type": "string", "description": "Capability that produced this discovery" }
        },
        "required": ["key", "value"]
      },
      "description": "New facts discovered during execution that Concierge MAY write to SessionState or forward to K0 memory."
    },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.6 k1.capability.failed.v1 (from Fabric)

```json
{
  "$id": "k1://schemas/events/fabric/capability.failed.v1.json",
  "type": "object",
  "required": ["request_id", "capability_name", "error_code", "trace_id"],
  "properties": {
    "request_id": { "type": "string", "format": "uuid" },
    "capability_name": { "type": "string" },
    "error_code": { "type": "string" },
    "error_message": { "type": "string" },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.7 k1.fabric.capability.registered.v1

> **NOTE (MISS-2 fix)**: Fabric emits granular events per change type, not a single combined event.
> The Orchestrator subscribes to each granular topic individually.
> See fabric_new.mmd EVENTS_EMITTED subgraph for the authoritative producer definitions.

```json
{
  "$id": "k1://schemas/events/fabric/capability.registered.v1.json",
  "type": "object",
  "required": ["capability_name", "provider_type", "trace_id"],
  "properties": {
    "capability_name": { "type": "string" },
    "provider_type": { "type": "string" },
    "version": { "type": ["string", "null"] },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.7a k1.fabric.capability.unregistered.v1

```json
{
  "$id": "k1://schemas/events/fabric/capability.unregistered.v1.json",
  "type": "object",
  "required": ["capability_name", "trace_id"],
  "properties": {
    "capability_name": { "type": "string" },
    "last_version": { "type": ["string", "null"] },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.7b k1.fabric.contract.validation.failed.v1

```json
{
  "$id": "k1://schemas/events/fabric/contract.validation.failed.v1.json",
  "type": "object",
  "required": ["capability_name", "error", "trace_id"],
  "properties": {
    "capability_name": { "type": "string" },
    "error": { "type": "string" },
    "schema_path": { "type": ["string", "null"] },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.7c k1.fabric.provider.health.changed.v1

```json
{
  "$id": "k1://schemas/events/fabric/provider.health.changed.v1.json",
  "type": "object",
  "required": ["provider_id", "old_status", "new_status", "trace_id"],
  "properties": {
    "provider_id": { "type": "string" },
    "old_status": { "type": "string", "enum": ["ONLINE", "DEGRADED", "OFFLINE"] },
    "new_status": { "type": "string", "enum": ["ONLINE", "DEGRADED", "OFFLINE"] },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.8 k1.fabric.agent.tool_call.v1

```json
{
  "$id": "k1://schemas/events/fabric/agent.tool_call.v1.json",
  "type": "object",
  "required": ["agent_id", "tool_name", "step_id", "trace_id"],
  "properties": {
    "agent_id": { "type": "string" },
    "tool_name": { "type": "string" },
    "step_id": { "type": "string" },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.9 k1.fabric.agent.llm_call.v1

```json
{
  "$id": "k1://schemas/events/fabric/agent.llm_call.v1.json",
  "type": "object",
  "required": ["agent_id", "model_id", "step_id", "trace_id"],
  "properties": {
    "agent_id": { "type": "string" },
    "model_id": { "type": "string" },
    "step_id": { "type": "string" },
    "tokens_used": { "type": "integer" },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.10 k1.orchestration.workflow.trigger_due.v1 (self-emitted by scheduler)

```json
{
  "$id": "k1://schemas/events/orchestration/workflow.trigger_due.v1.json",
  "type": "object",
  "required": ["workflow_id", "trigger_type", "trace_id"],
  "properties": {
    "workflow_id": { "type": "string" },
    "trigger_type": { "type": "string", "enum": ["CRON", "EVENT"] },
    "scheduled_fire_time": { "type": "string", "format": "date-time" },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.11 k1.hil.override_response.v1

```json
{
  "$id": "k1://schemas/events/hil/override_response.v1.json",
  "type": "object",
  "required": ["request_id", "action", "trace_id"],
  "properties": {
    "request_id": { "type": "string", "format": "uuid" },
    "action": {
      "type": "string",
      "enum": ["CONTINUE", "CANCEL", "MODIFY"]
    },
    "modifications": { "type": ["object", "null"] },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

#### 3.4.12 k1.hil.fallback_response.v1

```json
{
  "$id": "k1://schemas/events/hil/fallback_response.v1.json",
  "type": "object",
  "required": ["request_id", "selected_option", "trace_id"],
  "properties": {
    "request_id": { "type": "string", "format": "uuid" },
    "selected_option": { "type": "string" },
    "context": { "type": "object" },
    "trace_id": { "type": "string", "format": "uuid" }
  }
}
```

### 3.5 Action Required

- Add new Epic **1.5: Event Payload Schemas** to M1 with a single issue to create all 32 JSON Schema files under `k1/contracts/schemas/events/orchestration/`
- Reference these schemas from `wiring.contract.yaml` events section (same pattern as Fabric)
- Contract tests (7.4.4) validate emitted payloads against these schemas at runtime

---

## 4. Contract YAML Format Spec (P0)

**Gap**: Issues 1.3.1 and 1.3.2 create `module.contract.yaml` and `wiring.contract.yaml` but provide no format specification. The Fabric contracts exist and establish a pattern -- the Orchestrator must follow the same schema.

**Impact**: Blocks M1 issues 1.3.1-1.3.2.

### 4.1 module.contract.yaml Structure

Following the Fabric pattern from `k1/contracts/modules/fabric/module.contract.yaml`:

```yaml
$schema: "k1://schemas/module/module.contract.schema.yaml"

metadata:
  module_id: "orchestrator"
  owner: "platform-team"
  band: "GREEN"
  description: >
    Orchestrator module for K1. Blind DAG executor, workflow engine,
    connector host. Pure deterministic actor. Zero LLM calls, zero tools,
    NEVER writes SessionState.
  tags: ["orchestrator", "dag", "workflow", "connectors", "execution"]

contract_version: 1
impl_version: "1.0.0"

exports:
  # --- Facade (entry point) ---
  - symbol: "OrchestratorService"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "OrchestratorFactory"
    from_file: "k1/orchestrator/__init__.py"

  # --- Internal Services ---
  - symbol: "DAGExecutor"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "StepRunner"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "ConstraintResolver"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "WorkflowEngine"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "ConnectorManager"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "ErrorRouter"
    from_file: "k1/orchestrator/__init__.py"

  # --- Port Protocols ---
  - symbol: "IMailboxPort"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "IFabricGatewayPort"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "IPlannerPort"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "IStateReadPort"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "IDeltaEmitPort"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "IBridgeWritePort"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "IEventSubscriptionPort"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "IWorkflowStoragePort"
    from_file: "k1/orchestrator/__init__.py"

  # --- Types (35+) ---
  - symbol: "TaskEnvelope"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "PlanRequest"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "CommittedPlan"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "AggregatedResult"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "StepResult"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "WorkflowRunRequest"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "InterruptRequest"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "WorkflowSaveRequest"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "PlanStep"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "Wave"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "CompensationRecord"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "ProcessingContext"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "OrchestratorConfig"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "StepStatus"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "TriggerType"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "ProcessResult"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "ErrorSeverity"
    from_file: "k1/orchestrator/__init__.py"
  - symbol: "AdapterError"
    from_file: "k1/orchestrator/__init__.py"

dependencies:
  required: ["kernel", "bus", "fabric", "sessionstate"]
  optional: ["bridge"]
```

### 4.2 wiring.contract.yaml Structure

```yaml
$schema: "k1://schemas/wiring/wiring.contract.schema.yaml"

metadata:
  module_id: "orchestrator"
  owner: "platform-team"
  band: "GREEN"

contract_version: 1
impl_version: "1.0.0"

# ---------------------------------------------------------------------------
# Code ownership boundaries
# ---------------------------------------------------------------------------
code:
  roots:
    - "k1/orchestrator"
  required_files:
    - path: "k1/orchestrator/__init__.py"
    - path: "k1/orchestrator/types.py"
    - path: "k1/orchestrator/events.py"
    - path: "k1/orchestrator/config.py"
    - path: "k1/orchestrator/ports.py"
    - path: "k1/orchestrator/orchestration/__init__.py"
    - path: "k1/orchestrator/orchestration/orchestrator_service.py"
    - path: "k1/orchestrator/orchestration/dag_executor.py"
    - path: "k1/orchestrator/orchestration/step_runner.py"
    - path: "k1/orchestrator/orchestration/constraint_resolver.py"
    - path: "k1/orchestrator/orchestration/error_router.py"
    - path: "k1/orchestrator/orchestration/guards/__init__.py"
    - path: "k1/orchestrator/orchestration/guards/output_schema_guard.py"
    - path: "k1/orchestrator/orchestration/guards/conditional_edge_evaluator.py"
    # - path: "k1/orchestrator/orchestration/guards/token_budget_tracker.py"   # **V1 REMOVED**
    # - path: "k1/orchestrator/orchestration/guards/quality_gate.py"            # **V1 REMOVED**
    - path: "k1/orchestrator/orchestration/guards/micro_replan_checkpoint.py"
    - path: "k1/orchestrator/orchestration/guards/execution_monitor.py"
    # - path: "k1/orchestrator/orchestration/guards/cost_budget_guard.py"       # **V1 REMOVED**
    - path: "k1/orchestrator/orchestration/guards/concurrency_guard.py"
    - path: "k1/orchestrator/workflows/__init__.py"
    - path: "k1/orchestrator/workflows/workflow_engine.py"
    - path: "k1/orchestrator/workflows/workflow_registry.py"
    - path: "k1/orchestrator/workflows/workflow_compiler.py"
    - path: "k1/orchestrator/workflows/workflow_scheduler.py"
    - path: "k1/orchestrator/workflows/gap_detector.py"
    - path: "k1/orchestrator/workflows/persistence/__init__.py"
    - path: "k1/orchestrator/workflows/persistence/sqlite_adapter.py"
    - path: "k1/orchestrator/connectors/__init__.py"
    - path: "k1/orchestrator/connectors/connector_manager.py"
    - path: "k1/orchestrator/connectors/connector_sandbox.py"
    - path: "k1/orchestrator/connectors/k0_proxy.py"
    - path: "k1/orchestrator/adapters/__init__.py"
    - path: "k1/orchestrator/adapters/mailbox_adapter.py"
    - path: "k1/orchestrator/adapters/fabric_gateway_adapter.py"
    - path: "k1/orchestrator/adapters/planner_adapter.py"
    - path: "k1/orchestrator/adapters/state_read_adapter.py"
    - path: "k1/orchestrator/adapters/delta_emit_adapter.py"
    - path: "k1/orchestrator/adapters/bridge_write_adapter.py"
    - path: "k1/orchestrator/adapters/event_subscription_adapter.py"
    - path: "k1/orchestrator/factory.py"
    - path: "k1/orchestrator/metrics.py"
    - path: "k1/orchestrator/tracing.py"
  forbidden_patterns: ["*.pyc", "__pycache__"]

# ---------------------------------------------------------------------------
# Import wiring: what Orchestrator imports from other modules
# ---------------------------------------------------------------------------
wiring:
  imports:
    required_modules: ["kernel", "bus", "fabric"]
    required_symbols:
      - from: "fabric"
        import: "CapabilityRequest"
        used_in_files: ["k1/orchestrator/orchestration/step_runner.py"]
      - from: "fabric"
        import: "CapabilityResult"
        used_in_files: ["k1/orchestrator/orchestration/step_runner.py"]
      - from: "bus"
        import: "EventBus"
        used_in_files: ["k1/orchestrator/adapters/event_subscription_adapter.py"]
      - from: "sessionstate"
        import: "SessionStateManager"
        used_in_files: ["k1/orchestrator/adapters/state_read_adapter.py"]
    forbidden:
      - "direct_db_access"
      - "external_http_without_adapter"
      - "sessionstate_writer"
      - "direct_llm_call"
      - "direct_tool_call"

# ---------------------------------------------------------------------------
# Port interfaces (hexagonal architecture) -- 8 ports
# ---------------------------------------------------------------------------
capabilities:
  provides:
    - name: "orchestrator:process:v1"
      interface:
        methods:
          - name: "process"
            parameters:
              - name: "message"
                type: "Union[TaskEnvelope, CommittedPlan, WorkflowRunRequest, InterruptRequest, WorkflowSaveRequest]"
            returns: "ProcessResult"
      version: "1.0.0"
      qos: "INTERACTIVE"
      timeout_ms: 45000

    - name: "orchestrator:health:v1"
      interface:
        methods:
          - name: "health"
            returns: "HealthStatus"
          - name: "ready"
            returns: "bool"
      version: "1.0.0"
      qos: "BACKGROUND"
      timeout_ms: 5000

  consumes:
    - name: "fabric:execute:v1"
      interface:
        methods:
          - name: "execute"
            parameters:
              - name: "request"
                type: "CapabilityRequest"
          - name: "query_registry"
            parameters:
              - name: "capability_name"
                type: "string"
      version: "1.0.0"

    - name: "session:read:v1"
      interface:
        methods:
          - name: "snapshot"
            returns: "ContextSnapshot"
      version: "1.0.0"

    - name: "bus:publish:v1"
      interface:
        methods:
          - name: "publish_event"
          - name: "subscribe"
          - name: "unsubscribe"
      version: "1.0.0"

    - name: "delta-bus:publish:v1"
      interface:
        methods:
          - name: "emit"
            parameters:
              - name: "delta"
                type: "object"
      version: "1.0.0"

    - name: "bridge:write:v1"
      interface:
        methods:
          - name: "write_wal"
          - name: "read_wal"
          - name: "submit_audit"
      version: "1.0.0"
      required: false

    - name: "planner:request:v1"
      interface:
        methods:
          - name: "request_plan"
            parameters:
              - name: "request"
                type: "PlanRequest"
      version: "1.0.0"

# ---------------------------------------------------------------------------
# Events emitted and consumed -- linking to payload schemas from Section 3
# ---------------------------------------------------------------------------
events:
  emits:
    - topic: "k1.orchestration.task.accepted.v1"
      schema: "k1/contracts/schemas/events/orchestration/task.accepted.v1.json"
    - topic: "k1.orchestration.plan.requested.v1"
      schema: "k1/contracts/schemas/events/orchestration/plan.requested.v1.json"
    - topic: "k1.orchestration.dag.started.v1"
      schema: "k1/contracts/schemas/events/orchestration/dag.started.v1.json"
    - topic: "k1.orchestration.step.started.v1"
      schema: "k1/contracts/schemas/events/orchestration/step.started.v1.json"
    - topic: "k1.orchestration.step.completed.v1"
      schema: "k1/contracts/schemas/events/orchestration/step.completed.v1.json"
    - topic: "k1.orchestration.step.failed.v1"
      schema: "k1/contracts/schemas/events/orchestration/step.failed.v1.json"
    - topic: "k1.orchestration.step.cancelled.v1"
      schema: "k1/contracts/schemas/events/orchestration/step.cancelled.v1.json"
    - topic: "k1.orchestration.step.skipped.v1"
      schema: "k1/contracts/schemas/events/orchestration/step.skipped.v1.json"
    - topic: "k1.orchestration.step.retrying.v1"
      schema: "k1/contracts/schemas/events/orchestration/step.retrying.v1.json"
    - topic: "k1.orchestration.step.schema_retry.v1"
      schema: "k1/contracts/schemas/events/orchestration/step.schema_retry.v1.json"
    # - topic: "k1.orchestration.step.quality_retry.v1"       # **V1 REMOVED**
    #   schema: "k1/contracts/schemas/events/orchestration/step.quality_retry.v1.json"
    - topic: "k1.orchestration.saga.compensating.v1"
      schema: "k1/contracts/schemas/events/orchestration/saga.compensating.v1.json"
    - topic: "k1.orchestration.dag.micro_replan.v1"
      schema: "k1/contracts/schemas/events/orchestration/dag.micro_replan.v1.json"
    # - topic: "k1.orchestration.dag.budget_warning.v1"       # **V1 REMOVED**
    #   schema: "k1/contracts/schemas/events/orchestration/dag.budget_warning.v1.json"
    # - topic: "k1.orchestration.dag.budget_exhausted.v1"     # **V1 REMOVED**
    #   schema: "k1/contracts/schemas/events/orchestration/dag.budget_exhausted.v1.json"
    - topic: "k1.orchestration.dag.completed.v1"
      schema: "k1/contracts/schemas/events/orchestration/dag.completed.v1.json"
    - topic: "k1.orchestration.delta.v1"
      schema: "k1/contracts/schemas/events/orchestration/delta.v1.json"
    - topic: "k1.orchestration.workflow.triggered.v1"
      schema: "k1/contracts/schemas/events/orchestration/workflow.triggered.v1.json"
    - topic: "k1.orchestration.workflow.completed.v1"
      schema: "k1/contracts/schemas/events/orchestration/workflow.completed.v1.json"
    - topic: "k1.orchestration.mcp.tool_registered.v1"
      schema: "k1/contracts/schemas/events/orchestration/mcp.tool_registered.v1.json"
  subscribes:
    - topic: "k1.planner.plan.ready.v1"
      schema: "k1/contracts/schemas/events/planner/plan.ready.v1.json"
      handler: "orchestrator.orchestration.orchestrator_service:on_plan_ready"
    - topic: "k1.planner.plan.failed.v1"
      schema: "k1/contracts/schemas/events/planner/plan.failed.v1.json"
      handler: "orchestrator.orchestration.orchestrator_service:on_plan_failed"
    - topic: "k1.planner.plan.cancelled.v1"
      schema: "k1/contracts/schemas/events/planner/plan.cancelled.v1.json"
      handler: "orchestrator.orchestration.orchestrator_service:on_plan_cancelled"
    - topic: "k1.planner.micro_replan.ready.v1"
      schema: "k1/contracts/schemas/events/planner/micro_replan.ready.v1.json"
      handler: "orchestrator.orchestration.orchestrator_service:on_micro_replan_ready"
    - topic: "k1.capability.completed.v1"
      schema: "k1/contracts/schemas/events/fabric/capability.completed.v1.json"
      handler: "orchestrator.orchestration.step_runner:on_capability_completed"
    - topic: "k1.capability.failed.v1"
      schema: "k1/contracts/schemas/events/fabric/capability.failed.v1.json"
      handler: "orchestrator.orchestration.step_runner:on_capability_failed"
    - topic: "k1.fabric.contract.updated.v1"
      schema: "k1/contracts/schemas/events/fabric/contract.updated.v1.json"
      handler: "orchestrator.workflows.gap_detector:on_contract_updated"
    - topic: "k1.fabric.agent.tool_call.v1"
      schema: "k1/contracts/schemas/events/fabric/agent.tool_call.v1.json"
      handler: "orchestrator.orchestration.guards.execution_monitor:on_agent_tool_call"
    - topic: "k1.fabric.agent.llm_call.v1"
      schema: "k1/contracts/schemas/events/fabric/agent.llm_call.v1.json"
      handler: "orchestrator.orchestration.guards.execution_monitor:on_agent_llm_call"
    - topic: "k1.orchestration.workflow.trigger_due.v1"
      schema: "k1/contracts/schemas/events/orchestration/workflow.trigger_due.v1.json"
      handler: "orchestrator.workflows.workflow_scheduler:on_trigger_due"
    - topic: "k1.hil.override_response.v1"
      schema: "k1/contracts/schemas/events/hil/override_response.v1.json"
      handler: "orchestrator.orchestration.orchestrator_service:on_hil_override"
    - topic: "k1.hil.fallback_response.v1"
      schema: "k1/contracts/schemas/events/hil/fallback_response.v1.json"
      handler: "orchestrator.orchestration.orchestrator_service:on_hil_fallback"

# ---------------------------------------------------------------------------
# State: Orchestrator NEVER writes SessionState (ORCH-01)
# Reads SessionState for context, writes workflows to local SQLite
# ---------------------------------------------------------------------------
state:
  reads:
    - path: "session_data.beliefs"
      access: "SHARED"
    - path: "session_data.persona"
      access: "SHARED"
    - path: "session_data.control"
      access: "SHARED"
    - path: "session_data.scoreboard"
      access: "SHARED"
  writes: []
  local_storage:
    - path: "data/orchestrator_workflows.db"
      type: "sqlite"
      purpose: "Workflow registry, trigger state, run manifests, proactive gaps"

# ---------------------------------------------------------------------------
# Runtime assertions for contract compliance
# ---------------------------------------------------------------------------
runtime_assertions:
  on_load:
    - condition: "OrchestratorFactory is instantiable"
      test: "from k1.orchestrator import OrchestratorFactory"
    - condition: "All port Protocols defined"
      test: "from k1.orchestrator import IMailboxPort, IFabricGatewayPort, IPlannerPort, IStateReadPort, IDeltaEmitPort, IBridgeWritePort, IEventSubscriptionPort, IWorkflowStoragePort"
    - condition: "All core types available"
      test: "from k1.orchestrator import TaskEnvelope, PlanRequest, CommittedPlan, AggregatedResult, StepResult, ProcessingContext, OrchestratorConfig"
  invariants:
    - condition: "ORCH-01: Orchestrator never writes SessionState"
      test: "assert 'IStateWritePort' not in dir(k1.orchestrator)"
    - condition: "ORCH-02: Single-DAG concurrency"
      test: "assert OrchestratorConfig().max_concurrent_dags == 1"

# ---------------------------------------------------------------------------
# Validation rules (16 ORCH invariants)
# ---------------------------------------------------------------------------
validation:
  rules:
    - "orch_01_no_sessionstate_write"
    - "orch_02_single_dag_concurrency"
    - "orch_03_kahn_topological_sort"
    - "orch_04_wave_immutability"
    - "orch_05_constraint_validation_before_execution"
    - "orch_06_max_3_constraint_iterations"
    - "orch_07_safety_band_reread_at_wave_boundary"
    - "orch_08_compensation_record_on_side_effects"
    - "orch_09_trace_id_on_all_events"
    - "orch_10_wal_markers_per_dag"
    - "orch_11_workflow_contract_compliance"
    - "orch_12_max_workflow_depth_3"
    - "orch_13_max_1_micro_replan"
    - "orch_14_token_budget_enforcement"    # **V1 DEFERRED** -- no upstream data; re-enable in V2
    - "orch_15_output_schema_enforcement"
    - "orch_16_conditional_edge_evaluation"
```

### 4.3 File Locations

- `k1/contracts/modules/orchestrator/module.contract.yaml` -- issue 1.3.1
- `k1/contracts/modules/orchestrator/wiring.contract.yaml` -- issue 1.3.2

### 4.4 Action Required

- Add these draft YAML structures as the target spec for issues 1.3.1 and 1.3.2
- Create each event schema JSON file as part of new Epic 1.5

---

## 5. Admin API Surface (P1)

**Gap**: Runbook (9.3.3) references admin operations (force CB open/closed, manual workflow trigger, drain mailbox) but no admin API is defined.

**Impact**: Blocks runbook procedures 1, 3, 4, 5, 7, 8.

### 5.1 Admin Interface Protocol

```python
@runtime_checkable
class IAdminPort(Protocol):
    """
    Administrative operations port.

    Exposed via local HTTP (127.0.0.1:9091) when admin_enabled=True.
    NEVER exposed to external network. Local-only for ops tooling.
    """

    # --- Health ---
    async def health(self) -> HealthStatus: ...
    async def ready(self) -> bool: ...

    # --- Mailbox ---
    async def mailbox_depth(self) -> int: ...
    async def drain_mailbox(self, timeout_ms: int = 30_000) -> DrainResult: ...

    # --- DAG ---
    async def active_dag(self) -> Optional[ActiveDAGInfo]: ...
    async def cancel_dag(self, dag_id: str) -> CancelResult: ...

    # --- Circuit Breakers ---
    async def cb_status(self) -> Dict[str, CBState]: ...
    async def cb_force_open(self, cb_name: str) -> None: ...
    async def cb_force_closed(self, cb_name: str) -> None: ...
    async def cb_force_half_open(self, cb_name: str) -> None: ...

    # --- Workflows ---
    async def list_workflows(self) -> List[WorkflowSummary]: ...
    async def trigger_workflow(self, workflow_id: str) -> str: ...
    async def workflow_trigger_state(self, workflow_id: str) -> TriggerState: ...

    # --- MCP ---
    async def mcp_status(self) -> List[ConnectorHealthStatus]: ...
    async def mcp_force_rediscovery(self) -> int: ...

    # --- Pending Contexts ---
    async def pending_plans(self) -> List[PendingPlanSummary]: ...
    async def pending_hil(self) -> List[PendingHILSummary]: ...

    # --- Metrics ---
    async def metrics_snapshot(self) -> Dict[str, Any]: ...
```

### 5.2 Admin HTTP Endpoints

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/health` | `health()` | Liveness probe |
| GET | `/ready` | `ready()` | Readiness probe |
| GET | `/mailbox` | `mailbox_depth()` | Current queue depth |
| POST | `/mailbox/drain` | `drain_mailbox()` | Drain for maintenance |
| GET | `/dag/active` | `active_dag()` | Current DAG info |
| POST | `/dag/cancel` | `cancel_dag()` | Force-cancel active DAG |
| GET | `/cb` | `cb_status()` | All circuit breaker states |
| POST | `/cb/{name}/open` | `cb_force_open()` | Force CB open |
| POST | `/cb/{name}/closed` | `cb_force_closed()` | Force CB closed |
| POST | `/cb/{name}/half-open` | `cb_force_half_open()` | Force CB half-open |
| GET | `/workflows` | `list_workflows()` | List active workflows |
| POST | `/workflows/{id}/trigger` | `trigger_workflow()` | Manual trigger |
| GET | `/workflows/{id}/trigger-state` | `workflow_trigger_state()` | Next/last fire times |
| GET | `/mcp` | `mcp_status()` | MCP connector health |
| POST | `/mcp/rediscovery` | `mcp_force_rediscovery()` | Force re-scan |
| GET | `/pending/plans` | `pending_plans()` | Orphan detection |
| GET | `/pending/hil` | `pending_hil()` | HIL context status |
| GET | `/metrics` | `metrics_snapshot()` | Prometheus-compatible |

### 5.3 Supporting Types

```python
@dataclass(frozen=True)
class HealthStatus:
    status: str             # "HEALTHY" | "DEGRADED" | "UNHEALTHY"
    uptime_s: float
    dag_active: bool
    mailbox_depth: int
    pending_plans: int
    pending_hil: int
    mcp_servers_online: int
    cb_states: Dict[str, str]  # {"CB_FABRIC": "CLOSED", "CB_PLANNER": "CLOSED", ...}
    last_dag_completed_at: Optional[float]

@dataclass(frozen=True)
class ActiveDAGInfo:
    dag_id: str
    plan_id: str
    tier: str
    current_wave: int
    total_waves: int
    started_at: float
    trace_id: str

@dataclass(frozen=True)
class DrainResult:
    drained: int            # messages processed during drain
    remaining: int          # messages still in queue (if timeout hit)
    timed_out: bool
```

### 5.4 Action Required

- Add new Epic **6.3: Admin API** to M6 with issues for `IAdminPort`, HTTP adapter, and admin types
- Update OrchestratorFactory to optionally start admin server (gated by `admin_enabled` config)
- Link runbook procedures (9.3.3) to specific admin endpoints

---

## 6. Health Check Spec (P1)

**Gap**: No liveness or readiness probe defined for production deployment.

**Impact**: Blocks production deployment (M9).

### 6.1 Health Model

```
HEALTHY    = All ports connected, mailbox loop running, no CB open, no orphan contexts
DEGRADED   = One or more CB open OR pending context leak OR MCP servers offline
UNHEALTHY  = Mailbox loop stopped OR init failed OR unrecoverable error
```

### 6.2 Readiness Criteria

The Orchestrator is "ready" when:

1. `OrchestratorService.init()` completed successfully (all 10 steps)
2. All 8 ports are wired and connected
3. Mailbox loop is running (`_mailbox_loop_task` is not None and not done)
4. Scheduler is running (if workflows exist)
5. Event subscriptions active (12 consumed events subscribed)

### 6.3 Liveness Logic

```python
async def health(self) -> HealthStatus:
    status = "HEALTHY"

    # Check for UNHEALTHY conditions
    if not self._initialized:
        status = "UNHEALTHY"
    elif self._mailbox_loop_task is None or self._mailbox_loop_task.done():
        status = "UNHEALTHY"

    # Check for DEGRADED conditions
    # NOTE (MISS-5 fix): Orchestrator only owns CB_BRIDGE. CB_FABRIC, CB_PLANNER,
    # CB_MCP are owned by Concierge's FabricOrchestratorAdapter and not visible here.
    elif self._cb_bridge.state == "OPEN":
        status = "DEGRADED"
    elif len(self.pending_plans) > 0 and any(
        time.time() - ctx.created_at > ctx.timeout_ms / 1000
        for ctx in self.pending_plans.values()
    ):
        status = "DEGRADED"  # orphan pending context

    return HealthStatus(
        status=status,
        uptime_s=time.time() - self._started_at,
        dag_active=self._concurrency_guard.is_active,
        mailbox_depth=self._mailbox.depth(),
        pending_plans=len(self.pending_plans),
        pending_hil=len(self.pending_hil),
        mcp_servers_online=self._connector_manager.online_count(),
        cb_states={"CB_BRIDGE": self._cb_bridge.state},  # only Orchestrator-owned CB
        last_dag_completed_at=self._last_dag_completed_at,
    )
```

### 6.4 Probe Integration

| Probe | Endpoint | Check | Interval |
|-------|----------|-------|----------|
| Liveness | `GET /health` | status != "UNHEALTHY" | 10s |
| Readiness | `GET /ready` | `ready()` returns True | 5s |
| Startup | `GET /ready` | Same as readiness, longer timeout | 30s initial delay |

### 6.5 Action Required

- Add `health()` and `ready()` methods to `OrchestratorService` (issue in M2)
- Expose via admin API endpoints (Section 5)
- Add to production checklist (9.4.1)

---

## 7. Circuit Breaker Configuration (P1)

**Gap**: `CB_FABRIC`, `CB_PLANNER`, `CB_MCP` referenced extensively but trip thresholds, recovery timeouts, and state transitions never defined.

**Impact**: Blocks ErrorRouter implementation (M2) and tier degradation logic.

### 7.1 Circuit Breaker Definitions

**Ownership boundary (MISS-4 fix)**: `CB_FABRIC`, `CB_PLANNER`, `CB_MCP` are owned and configured by Concierge's `FabricOrchestratorAdapter` (see concierge.mmd TP_CIRCUIT_BREAKERS). The Orchestrator does NOT own or configure these CBs. They are listed here for reference only. The Orchestrator owns only `CB_BRIDGE`.

| CB Name | Protected Dependency | Trip Threshold | Recovery Timeout | Half-Open Probes | Owner |
|---------|---------------------|---------------|-----------------|-----------------|-------|
| `CB_FABRIC` | IFabricGatewayPort | 5 consecutive failures | 30s | 1 probe request | **Concierge** (FabricOrchestratorAdapter) |
| `CB_PLANNER` | IPlannerPort | 3 consecutive failures | 45s | 1 probe request | **Concierge** (FabricOrchestratorAdapter) |
| `CB_MCP` | MCP Server (per-server) | 3 consecutive failures | 60s | 1 probe request | **Concierge** (FabricOrchestratorAdapter) |
| `CB_BRIDGE` | IBridgeWritePort (fire-and-forget) | 5 consecutive failures | 30s | 1 probe request | **Orchestrator** (connection-level errors only) |

### 7.2 State Machine

```
CLOSED ---[failure_count >= threshold]---> OPEN
OPEN   ---[recovery_timeout elapsed]----> HALF_OPEN
HALF_OPEN ---[probe succeeds]-----------> CLOSED
HALF_OPEN ---[probe fails]--------------> OPEN (reset recovery timer)
```

### 7.3 Circuit Breaker Dataclass

```python
@dataclass
class CircuitBreakerConfig:
    name: str
    failure_threshold: int
    recovery_timeout_ms: int
    half_open_max_probes: int = 1

@dataclass
class CircuitBreakerState:
    config: CircuitBreakerConfig
    state: str = "CLOSED"              # CLOSED | OPEN | HALF_OPEN
    failure_count: int = 0
    last_failure_at: Optional[float] = None
    opened_at: Optional[float] = None
    half_open_probes: int = 0

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = "CLOSED"
        self.opened_at = None
        self.half_open_probes = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_at = time.time()
        if self.failure_count >= self.config.failure_threshold:
            self.state = "OPEN"
            self.opened_at = time.time()

    def should_allow_request(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.opened_at >= self.config.recovery_timeout_ms / 1000:
                self.state = "HALF_OPEN"
                self.half_open_probes = 0
                return True
            return False
        if self.state == "HALF_OPEN":
            if self.half_open_probes < self.config.half_open_max_probes:
                self.half_open_probes += 1
                return True
            return False
        return False
```

### 7.4 Tier Degradation Mapping

| CB State | Effect on Orchestrator |
|----------|----------------------|
| `CB_PLANNER` OPEN | HIGH tier degrades to MEDIUM (skip planning, direct Fabric calls) |
| `CB_FABRIC` OPEN | All steps get DEGRADED CapabilityResult, saga compensation triggered |
| `CB_MCP` OPEN (per-server) | MCP tools marked UNAVAILABLE, ConstraintResolver substitutes alternatives |
| `CB_BRIDGE` OPEN | WAL writes silently dropped (best-effort audit), recovery skipped on restart |

### 7.5 ErrorRouter Classification with CB

```python
ERROR_CLASSIFICATION = {
    ConnectionError:        ("TRANSIENT", "RETRY"),
    TimeoutError:           ("TRANSIENT", "RETRY"),
    SchemaValidationError:  ("PERMANENT", "ABORT"),
    AccessDeniedError:      ("PERMANENT", "ABORT"),
    CircuitBreakerOpen:     ("CIRCUIT_OPEN", "DEGRADE"),
    CapabilityNotFound:     ("NOT_FOUND", "CONSTRAINT"),
    Exception:              ("INTERNAL", "ABORT"),
}
```

### 7.6 Action Required

- Add CB types to `types.py` (issue 1.2.23)
- Add CB config fields to `OrchestratorConfig` (Section 2 covers this)
- Add CB initialization to OrchestratorFactory (step 2-ish, before service construction)
- ErrorRouter (2.1.7) consumes CB state for classification

---

## 8. Guard Pipeline Ordering (P1)

**Gap**: Five V1 guards exist (was eight pre-phantom-field removal) with execution points (pre-step, post-step, pre-wave, post-wave) but no single canonical ordered table.

**Impact**: Causes ambiguity in M3 implementation -- guards interact and ordering matters.

### 8.1 Canonical Guard Pipeline

```
DAG Execution Flow (V1 — 5 guards):
=====================================

OrchestratorService.process(message)
    |
    +-- ConcurrencyGuard.acquire()          # [G0] WRAPS _process_one()
    |
    +-- For each WAVE:
    |       |
    |       +-- [PRE-WAVE] ConditionalEdgeEvaluator     # [G1] prune edges BEFORE wave construction
    |       |
    |       +-- For each STEP in wave (parallel via asyncio.gather):
    |       |       |
    |       |       +-- StepRunner.execute(step)
    |       |       |       |
    |       |       |       +-- [POST-STEP] OutputSchemaGuard     # [G2] validate result schema, retry with hint
    |       |
    |       +-- [POST-WAVE] ExecutionMonitor              # [G3] emit progress delta, check user override
    |       +-- [POST-WAVE] MicroReplanCheckpoint         # [G4] check discovery heuristic, trigger replan
    |       +-- [POST-WAVE] SafetyBandReRead             # [G5] re-read safety_band from StatePort (ORCH-07)
    |
    +-- ConcurrencyGuard.release()          # [G0] release lock

# V1 REMOVED guards (no upstream data from Fabric CapabilityResult):
#   TokenBudgetTracker  (was G2/G6) — re-add in V2 when LLM providers report token usage
#   CostBudgetGuard     (was G3/G7) — re-add in V2 when LLM providers report cost
#   QualityGate         (was G5)    — re-add in V2 when LLM providers report quality_score
```

### 8.2 Guard Registry Table

| Order | Guard | Hook | Phase | Invariant | Config Dependency |
|-------|-------|------|-------|-----------|-------------------|
| G0 | ConcurrencyGuard | wraps `_process_one()` | pre/post dispatch | ORCH-02 | `max_concurrent_dags` |
| G1 | ConditionalEdgeEvaluator | pre-wave | wave boundary | ORCH-16 | none |
| ~~G2~~ | ~~TokenBudgetTracker~~ | ~~pre-wave + post-step~~ | ~~wave boundary + step end~~ | ~~ORCH-14~~ | **V1 REMOVED** |
| ~~G3~~ | ~~CostBudgetGuard~~ | ~~pre-wave + post-step~~ | ~~wave boundary + step end~~ | ~~ORCH-14 (cost variant)~~ | **V1 REMOVED** |
| G2 | OutputSchemaGuard | post-step | step end | ORCH-15 | none |
| ~~G5~~ | ~~QualityGate~~ | ~~post-step~~ | ~~step end~~ | ~~none~~ | **V1 REMOVED** |
| G3 | ExecutionMonitor | post-wave | wave boundary | ORCH-09 | `substep_rate_limit_ms` |
| G4 | MicroReplanCheckpoint | post-wave | wave boundary | ORCH-13 | `max_micro_replans` |
| G5 | SafetyBandReRead | post-wave | wave boundary | ORCH-07 | none |

### 8.3 Guard Return Values

Each guard returns a `GuardDecision`:

```python
class GuardAction(str, Enum):
    CONTINUE = "CONTINUE"     # proceed normally
    RETRY = "RETRY"           # re-execute the step (OutputSchemaGuard)
    SKIP = "SKIP"             # skip the step (ConditionalEdge)
    HARD_STOP = "HARD_STOP"   # abort remaining waves
    BYPASS = "BYPASS"         # guard not applicable (no schema)

@dataclass(frozen=True)
class GuardDecision:
    action: GuardAction
    reason: str
    guard_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 8.4 Guard Interface

```python
@runtime_checkable
class IPreWaveGuard(Protocol):
    async def evaluate_pre_wave(
        self, wave: Wave, ctx: ProcessingContext
    ) -> List[GuardDecision]: ...

@runtime_checkable
class IPostStepGuard(Protocol):
    async def evaluate_post_step(
        self, step: PlanStep, result: StepResult, ctx: ProcessingContext
    ) -> GuardDecision: ...

@runtime_checkable
class IPostWaveGuard(Protocol):
    async def evaluate_post_wave(
        self, wave_result: WaveResult, ctx: ProcessingContext
    ) -> GuardDecision: ...
```

### 8.5 OrchestratorFactory Guard Wiring (step 12 of 15)

```python
# Factory step 12: Wire guard pipeline in canonical order (V1 — 5 guards)
pre_wave_guards: List[IPreWaveGuard] = [
    ConditionalEdgeEvaluator(),
    # TokenBudgetTracker(config),          # **V1 REMOVED** — no upstream data
    # CostBudgetGuard(config),             # **V1 REMOVED** — no upstream data
]

post_step_guards: List[IPostStepGuard] = [
    OutputSchemaGuard(),                  # schema validation
    # QualityGate(config),                  # **V1 REMOVED** — no upstream data
    # TokenBudgetTracker(config),           # **V1 REMOVED** — no upstream data
    # CostBudgetGuard(config),             # **V1 REMOVED** — no upstream data
]

post_wave_guards: List[IPostWaveGuard] = [
    ExecutionMonitor(config, delta_port), # progress emission
    MicroReplanCheckpoint(planner_port),  # replan check
    SafetyBandReRead(state_port),         # safety re-read LAST
]
```

### 8.6 Action Required

- Add guard types (`GuardAction`, `GuardDecision`, `IPreWaveGuard`, `IPostStepGuard`, `IPostWaveGuard`) to `types.py` (issue 1.2.24)
- Update Epic 3.2 issues to reference this ordering table
- Update OrchestratorFactory (6.2.1) step 12 to use this exact wiring

---

## 9. Mailbox Message Durability (P1)

**Gap**: `MailboxAdapter` uses `asyncio.PriorityQueue` (in-memory). Process crash = all queued messages lost. WAL covers in-flight DAGs but not queued-but-unprocessed messages.

**Impact**: Silent data loss risk in production.

### 9.1 V1 Strategy: Accept-and-Document

In V1, the mailbox is in-memory. This is acceptable for edge deployment because:

1. The Orchestrator processes messages near-instantly (< 18ms overhead) -- queue depth is typically 0-2
2. The primary producer (Concierge) can retry failed dispatches
3. WAL covers the expensive part (in-flight DAG state)
4. Workflow triggers are persisted in SQLite and re-fire on restart

**However**, the risk must be documented and mitigated:

### 9.2 Mitigation: Acknowledgment Protocol

```
Producer (Concierge)                  Orchestrator Mailbox
       |                                      |
       |--- enqueue(TaskEnvelope) ----------->|
       |<-- TaskAck(ACCEPTED) ---------------|  # immediate ACK
       |                                      |
       |  (if no ACK within 1s)               |
       |--- retry enqueue(same envelope) ---->|  # dedup by envelope_id
       |<-- TaskAck(ACCEPTED) ---------------|
       |                                      |
       |  (Orchestrator crash before process) |
       |--- enqueue(same envelope) ---------->|  # re-enqueue on restart
       |<-- TaskAck(ACCEPTED) ---------------|
```

### 9.3 Deduplication

```python
class MailboxAdapter:
    def __init__(self, config: OrchestratorConfig):
        self._queue = asyncio.PriorityQueue(maxsize=config.mailbox_depth)
        self._seen_ids: OrderedDict[str, float] = OrderedDict()  # envelope_id -> timestamp
        self._max_seen: int = 1000  # sliding window

    async def enqueue(self, message: Any, priority: int) -> TaskAck:
        msg_id = getattr(message, 'envelope_id', None) or getattr(message, 'request_id', '')

        # Dedup check
        if msg_id in self._seen_ids:
            return TaskAck(envelope_id=msg_id, status="DUPLICATE")

        # Backpressure check
        if self._queue.full():
            if self._config.mailbox_backpressure == "REJECT":
                return TaskAck(envelope_id=msg_id, status="REJECTED_FULL")
            elif self._config.mailbox_backpressure == "DROP_OLDEST":
                self._queue.get_nowait()  # drop oldest

        await self._queue.put((priority, message))
        self._seen_ids[msg_id] = time.time()

        # Trim dedup window
        while len(self._seen_ids) > self._max_seen:
            self._seen_ids.popitem(last=False)

        return TaskAck(envelope_id=msg_id, status="ACCEPTED")
```

### 9.4 V2 Strategy: WAL-Backed Mailbox (Future)

For V2, the mailbox can be backed by SQLite WAL:

```sql
CREATE TABLE mailbox_wal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    envelope_id TEXT UNIQUE NOT NULL,
    priority INTEGER NOT NULL,
    message_json TEXT NOT NULL,
    enqueued_at REAL NOT NULL,
    processed_at REAL,                -- NULL until dequeued and processed
    status TEXT DEFAULT 'PENDING'     -- PENDING | PROCESSING | DONE | DEAD_LETTERED
);
```

On startup: `SELECT * FROM mailbox_wal WHERE status = 'PENDING' ORDER BY priority, enqueued_at` -> re-enqueue all.

### 9.5 Backpressure Behavior

| Config Value | Behavior When Full | Producer Response |
|-------------|-------------------|-------------------|
| `REJECT` (default) | Return `TaskAck(status="REJECTED_FULL")` | Producer retries after backoff |
| `DROP_OLDEST` | Evict lowest-priority oldest message | Loss risk for background workflows |

### 9.6 Action Required

- Add `mailbox_backpressure` and `mailbox_wal_enabled` to `OrchestratorConfig` (Section 2 covers this)
- Update `MailboxAdapter` (6.1.1) to include dedup and backpressure logic
- Add `TaskAck` as return type from `IMailboxPort.enqueue()` (currently void -- needs port interface update)
- Document V2 WAL-backed strategy in ADR for future implementation
- Add mailbox depth monitoring to health check (Section 6)

---

## 10. Planner-Orchestrator Protocol (P0)

**Gap**: The Planner ↔ Orchestrator boundary is the HIGHEST complexity flow in the system (HIGH tier = full 4-stage planning pipeline + DAG execution). The whiteboard defines individual event schemas (3.4.1-3.4.4) and port interfaces (1.4.3) but does NOT specify:

- The full PlanRequest transport schema (what Orchestrator sends to Planner)
- CommittedPlan field reconciliation (3 divergent POC definitions vs production spec)
- The complete async event-driven protocol sequence
- MicroReplan round-trip contract
- Budget/constraint passthrough from Orchestrator to Planner and back
- PlanStep field mapping between Planner's output and Orchestrator's 14-field PlanStep
- Planner failure modes, degradation paths, and recovery

**Impact**: Blocks M2 issue 2.1.4 (dispatch_high / receive_plan), M3 issue 3.2.5 (MicroReplanCheckpoint), and M6 issue 6.1.3 (PlannerAdapter).

### 10.1 Protocol Sequence: HIGH Tier (dispatch_high → Planner → receive_plan)

This is the PRIMARY flow. Every HIGH-tier task goes through this path.

> **LOW Tier Bypass**: LOW-tier tasks NEVER reach Orchestrator or Planner. Concierge dispatches LOW tasks directly to Fabric via `IDispatchPort` (Concierge tools: `invoke_capability()`, `spawn_via_fabric()`, `execute_workflow()`). This section covers HIGH tier only. MEDIUM tier uses Orchestrator but skips Planner (single-step execution via Fabric).

```
Concierge                  Orchestrator                    Planner                     Fabric
  |                            |                              |                          |
  |-- TaskEnvelope(HIGH) ----->|                              |                          |
  |                            |                              |                          |
  |                            |-- state_port.snapshot() ---->|                          |
  |                            |<--- ContextSnapshot ---------|                          |
  |                            |                              |                          |
  |                            |== BUILD PlanRequest =========|                          |
  |                            |  request_id = uuid4()        |                          |
  |                            |  intent = envelope.intent     |                          |
  |                            |  constraints = envelope.constraints                     |
  |                            |  context = snapshot           |                          |
  |                            |  trace_id = envelope.trace_id |                          |
  |                            |  timeout_ms = 45000           |                          |
  |                            |                              |                          |
  |                            |-- IPlannerPort.request_plan -->|                         |
  |                            |<--- PlanAck(ACCEPTED) --------|                         |
  |                            |                              |                          |
  |                            |== PARK CONTEXT ===============|                          |
  |                            |  pending_plans[request_id] =  |                          |
  |                            |    PendingPlanContext(        |                          |
  |                            |      request_id,              |                          |
  |                            |      task_envelope,           |                          |
  |                            |      snapshot,                |                          |
  |                            |      created_at,              |                          |
  |                            |      timeout_ms=45000)        |                          |
  |                            |                              |                          |
  |                            |-- emit(PLAN_REQUESTED) ------>|  (fire-and-forget delta) |
  |                            |-- return DEFERRED             |                          |
  |                            |                              |                          |
  |                            |  [mailbox loop continues]     |                          |
  |                            |  [can process MEDIUM tasks]   |                          |
  |                            |                              |                          |
  |                            |                              |== 4-STAGE PIPELINE ======|
  |                            |                              |                          |
  |                            |                              |-- Stage 1: SKETCH -------|
  |                            |                              |   discover_capabilities ->| Fabric
  |                            |                              |   <-- top-K capabilities -|
  |                            |                              |   query_planning_context -| SessionState
  |                            |                              |   <-- user context -------|
  |                            |                              |   recall_for_planning --->| K0 Bridge
  |                            |                              |   <-- long-term memory ---|
  |                            |                              |   -> SketchPlan           |
  |                            |                              |                          |
  |                            |                              |-- Stage 2: EXPAND --------|
  |                            |                              |   find_relevant_prompts ->| Fabric
  |                            |                              |   <-- prompt templates ---|
  |                            |                              |   -> ExpandedPlan         |
  |                            |                              |                          |
  |                            |                              |-- Stage 3: VALIDATE ------|
  |                            |                              |   check capabilities exist|
  |                            |                              |   check DAG acyclic       |
  |                            |                              |   check safety bands      |
  |                            |                              |   check budget constraints|
  |                            |                              |   -> ValidatedPlan        |
  |                            |                              |                          |
  |                            |                              |-- Stage 4: COMMIT --------|
  |                            |                              |   serialize to JSON       |
  |                            |                              |   write to K0 WAL         |
  |                            |                              |   -> CommittedPlan        |
  |                            |                              |                          |
  |                            |<== k1.planner.plan.ready.v1 =|  (via event bus)         |
  |                            |                              |                          |
  |                            |== RECEIVE PLAN ===============|                          |
  |                            |  plan arrives in mailbox      |                          |
  |                            |  dedup: plan_id in executed?  |                          |
  |                            |  pop pending_plans[request_id]|                          |
  |                            |  re-snapshot state (RACE-1)   |                          |
  |                            |  constraint_resolver.validate |                          |
  |                            |  dag_executor.execute(plan)   |                          |
  |                            |                              |                          |
  |                            |== DAG EXECUTION ==============|                          |
  |                            |  Wave 0: [s1, s2, s3] ------>|                     Fabric
  |                            |  Wave 1: [s4] (depends s1,s3)|                     Fabric
  |                            |  -> AggregatedResult          |                          |
  |                            |                              |                          |
  |<== AggregatedResult =======|                              |                          |
```

### 10.2 PlanRequest Transport Schema

The full JSON schema for PlanRequest as sent over the event bus / port boundary.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "k1://schemas/orchestrator/plan_request.v1.json",
  "title": "PlanRequest",
  "description": "Orchestrator -> Planner plan request. Sent via IPlannerPort.request_plan().",
  "type": "object",
  "required": ["request_id", "intent", "trace_id"],
  "properties": {
    "request_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique request ID for PendingPlanContext correlation. Planner MUST echo this back in CommittedPlan.request_id."
    },
    "intent": {
      "type": "string",
      "minLength": 1,
      "description": "User intent extracted by Concierge (e.g. 'plan birthday party for Mom')"
    },
    "constraints": {
      "type": "object",
      "description": "Budget, time, safety, and permission constraints for plan construction.",
      "properties": {
        "time_budget_ms": {
          "type": ["integer", "null"],
          "minimum": 0,
          "description": "Max total execution time budget for the plan. Planner uses this for BUDGET-1 time estimation."
        },
        "safety_band": {
          "type": "string",
          "enum": ["GREEN", "AMBER", "RED"],
          "description": "Current safety band from SessionState. Planner must not select capabilities requiring higher band."
        },
        "max_steps": {
          "type": ["integer", "null"],
          "minimum": 1,
          "maximum": 50,
          "description": "Hard cap on plan steps. Null = use system default (50)."
        },
        "allowed_domains": {
          "type": ["array", "null"],
          "items": { "type": "string" },
          "description": "Restrict capabilities to these domains only. Null = all domains allowed."
        },
        "forbidden_capabilities": {
          "type": ["array", "null"],
          "items": { "type": "string" },
          "description": "Capabilities the Planner must NOT include. E.g. user blocked a provider."
        }
      }
    },
    "context": {
      "type": "object",
      "description": "Routing metadata + optional pre-fetched SessionState snapshot. Reconciled per MISS-7: includes tier, family_member_id, session_id (from planner.mmd) plus optional snapshot (from WB original).",
      "required": ["tier", "session_id"],
      "properties": {
        "tier": { "type": "string", "enum": ["HIGH"], "description": "Always HIGH for PlanRequest (Planner only invoked for HIGH tier)." },
        "family_member_id": { "type": "string", "description": "Which family member this plan is for." },
        "session_id": { "type": "string", "description": "Active session identifier." },
        "snapshot": {
          "$ref": "#/$defs/ContextSnapshot",
          "description": "Optional pre-fetched SessionState snapshot. Planner may also independently read via query_planning_context()."
        }
      }
    },
    "trace_id": {
      "type": "string",
      "format": "uuid"
    },
    "timeout_ms": {
      "type": "integer",
      "minimum": 1000,
      "default": 45000,
      "description": "Max time Orchestrator will wait for plan. After this, PendingPlanContext expires and Planner is cancelled."
    }
  },
  "$defs": {
    "ContextSnapshot": {
      "type": "object",
      "description": "Read-only snapshot of SessionState sections. NOTE (MISS-8 fix): temporal_context and safety_band are sub-fields within the 'control' section, NOT standalone top-level sections. Readers access them via control.temporal_context and control.safety_band respectively. The orchestrator.mmd SS_TEMPORAL and SS_SAFETY nodes represent read-aliases for convenience but data lives inside the control section.",
      "properties": {
        "sections": {
          "type": "object",
          "description": "Map of section_name -> section_data.",
          "additionalProperties": {
            "type": "object",
            "properties": {
              "data": { "type": "object" },
              "version": { "type": "integer" }
            }
          }
        },
        "captured_at": {
          "type": "number",
          "description": "Unix timestamp when snapshot was taken."
        }
      }
    }
  }
}
```

### 10.3 CommittedPlan Field Reconciliation

Three POC definitions exist. The production spec must reconcile them.

| Field | POC-1 (concierge_planner_orch) | POC-2 (chat_experience) | Production (1.2.3) | Decision |
|-------|-------------------------------|------------------------|-------------------|----------|
| `plan_id` | uuid | uuid | uuid | KEEP |
| `request_id` | -- | -- | uuid | **ADD** (critical for PendingPlanContext correlation) |
| `intent` | str | str | str | KEEP |
| `steps` | List[PlanStep] (5 fields) | List[PlanStep] (12 fields) | List[PlanStep] (14 fields) | USE 14-field (1.2.18) |
| `dependencies` | -- | -- | Dict[str, List[str]] | **ADD** (required for Kahn's in build_waves) |
| `reasoning` | str | -- | -- | DROP (Planner-internal, not consumed by Orchestrator) |
| `complexity` | -- | PlanComplexity enum | -- | DROP (Planner may include but Orchestrator does not use) |
| `serialized_json` | -- | str | -- | DROP (Planner-internal persistence artifact) |
| `plan_hash` | -- | str | -- | DROP (Planner-internal integrity check) |
| `committed_at` | -- | str (ISO8601) | float (epoch) | KEEP as float (consistent with created_at) |
| `latency_ms` | -- | float | -- | DROP (Planner-internal metric) |
| `token_budget_max` | -- | -- | ~~int~~ | ~~**ADD** (Orchestrator needs for TokenBudgetTracker)~~ **V1 REMOVED** — no upstream data |
| `cost_budget_max_usd` | -- | estimated_cost (float) | ~~Optional[float]~~ | ~~**ADD** (Orchestrator needs for CostBudgetGuard)~~ **V1 REMOVED** — no upstream data |
| `trace_id` | str | str | str | KEEP |
| `execution_status` | -- | str | -- | DROP (Orchestrator tracks this in its own ProcessingContext) |
| `estimated_duration_ms` | -- | int | -- | OPTIONAL (for BUDGET-1 time pressure detection) |
| `estimated_cost` | -- | float | -- | Maps to `cost_budget_max_usd` |

**Production CommittedPlan** (final reconciled):

```python
@dataclass(frozen=True)
class CommittedPlan:
    """
    Planner -> Orchestrator: Validated DAG ready for execution.

    Planner's Stage 4 (COMMIT) produces this. Orchestrator's receive_plan()
    consumes it. The request_id MUST match the original PlanRequest.request_id
    for PendingPlanContext correlation (ADR-1.1.12).

    The Planner may include additional fields (complexity, plan_hash, etc.)
    in its internal representation. The Orchestrator ignores those -- only
    the fields below cross the module boundary.
    """

    # --- Identity ---
    plan_id: str                                    # unique plan ID (uuid)
    request_id: str                                 # echoed from PlanRequest.request_id
    intent: str                                     # echoed from PlanRequest.intent
    trace_id: str                                   # echoed from PlanRequest.trace_id

    # --- Plan structure ---
    steps: List[PlanStep]                           # 14-field PlanStep (1.2.18)
    dependencies: Dict[str, List[str]]              # step_id -> [dep_step_ids]

    # --- Budget (Planner estimates, Orchestrator enforces) ---
    # token_budget_max: int = 0                       # **V1 REMOVED** — no upstream data source. Re-add in V2.
    # cost_budget_max_usd: Optional[float] = None     # **V1 REMOVED** — same.
    estimated_duration_ms: Optional[int] = None     # Planner's estimate of total execution time

    # --- Metadata ---
    created_at: float = 0.0                         # epoch timestamp from Planner Stage 4
```

### 10.4 PlanStep Field Mapping: Planner Output → Orchestrator Input

The Planner produces steps; the Orchestrator consumes them. The mapping must be explicit.

| # | Field | Planner Produces | Orchestrator Consumes | Notes |
|---|-------|-----------------|----------------------|-------|
| 1 | `id` | Generated in Stage 1 (SKETCH) | Used as step_id throughout DAG | e.g. "s1", "s2" |
| 2 | `capability` | Resolved in Stage 2 (EXPAND) via `discover_capabilities()` | Direct input to `CapabilityRequest.capability_name` | e.g. "tool.execute.restaurant_booking" |
| 3 | `params` | Resolved in Stage 2 from user context + tool schemas | May contain `$ref` ("$s1.result.data.venue") resolved by ParamResolver | Planner builds; Orchestrator resolves refs |
| 4 | `deps` | Built in Stage 2 dependency graph | Input to Kahn's topological sort in `build_waves()` | Also redundantly in CommittedPlan.dependencies |
| 5 | `prompt_template` | Resolved in Stage 2 via `find_relevant_prompts()` | Passed through to Fabric `CapabilityRequest` | None for tool-type capabilities |
| 6 | `tools_granted` | Resolved in Stage 2 (FAB-07 scoped tools) | Passed through to Fabric `CapabilityRequest` | None for tool-type capabilities |
| 7 | `token_budget` | Estimated in Stage 2 based on capability metadata | ~~Enforced by TokenBudgetTracker (guard G3)~~ **V1 REMOVED** — no upstream data | 0 = unlimited |
| 8 | `output_schema` | From capability contract (if structured output) | Enforced by OutputSchemaGuard (guard G4) | JSON Schema Draft 2020-12 |
| 9 | `condition` | Built in Stage 2 (conditional edge) | Evaluated by ConditionalEdgeEvaluator (guard G1) | None = always execute |
| 10 | `is_optional` | Set in Stage 2 (budget-skippable steps) | Checked by guards for graceful skip decisions | Default False |
| 11 | `has_side_effects` | Set in Stage 2 from capability contract | Drives saga compensation (2.2.5) | Default False |
| 12 | `compensation` | Pre-resolved in Stage 2 from capability contract | Used by SagaRecovery for rollback | Fallback: query_registry() |
| 13 | `timeout_ms` | Estimated in Stage 2 | Per-step timeout in StepRunner | None = config default (30s) |
| 14 | `required_context` | Set in Stage 2 from capability metadata | Passed to Fabric ContextBuilder | SessionState sections |

**Critical contract**: Fields 7-14 are Orchestrator-specific extensions that the Planner's Stage 2 (EXPAND) must populate. The Planner's `discover_capabilities()` response from Fabric MUST include the metadata needed to fill these fields (output_schema, has_side_effects, compensation capability, estimated latency). If Fabric's capability registry doesn't provide this metadata, the Planner uses defaults.

### 10.5 Planner Discovery Tools → Fabric Contract

The Planner's 4 discovery tools hit Fabric (Role 1: Intelligent Registry). This contract affects the quality of CommittedPlans the Orchestrator receives.

| Planner Tool | Fabric Endpoint / Port | Input | Output | Used to Populate |
|-------------|----------------------|-------|--------|------------------|
| `discover_capabilities(domain?, intent?)` | Fabric CapabilityRegistry semantic search | domain string, intent string | `List[CapabilityDescriptor]` with: name, provider_type, input_schema, output_schema, safety_band_min, has_side_effects, compensation_capability, estimated_duration_ms | PlanStep fields 2, 8, 11, 12, 13 |
| `find_relevant_prompts(intent?, domain?)` | Fabric PromptRegistry semantic search | intent string, domain string | `List[PromptDescriptor]` with: name, template, variables, version | PlanStep field 5 |
| `query_planning_context(sections?)` | SessionState IStateReadPort.snapshot() | section names list | ContextSnapshot | PlanStep field 3 (params enrichment) |
| `recall_for_planning(query)` | K0 Bridge hippocampus recall | query string | `List[MemoryFact]` with: fact, confidence, source | PlanStep field 3 (params enrichment) |

**CapabilityDescriptor schema** (what Fabric returns to Planner):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "k1://schemas/fabric/capability_descriptor.v1.json",
  "title": "CapabilityDescriptor",
  "description": "Capability metadata returned by Fabric.discover_capabilities(). Planner uses this to build PlanStep fields.",
  "type": "object",
  "required": ["name", "provider_type"],
  "properties": {
    "name": {
      "type": "string",
      "description": "Fully qualified capability name (e.g. 'tool.execute.restaurant_booking')"
    },
    "provider_type": {
      "type": "string",
      "enum": ["mcp_local", "mcp_remote", "wasm", "bridge", "agent", "workflow", "concierge"],
      "description": "Type of provider (matches Fabric's 6+1 provider taxonomy from fabric_new.mmd). Determines whether prompt_template is needed and affects timeout estimation."
    },
    "input_schema": {
      "type": ["object", "null"],
      "description": "JSON Schema for capability input parameters. Planner validates params against this."
    },
    "output_schema": {
      "type": ["object", "null"],
      "description": "JSON Schema for capability output. Forwarded to PlanStep.output_schema for OutputSchemaGuard."
    },
    "safety_band_min": {
      "type": "string",
      "enum": ["GREEN", "AMBER", "RED"],
      "default": "GREEN",
      "description": "Minimum safety band required. Planner checks against PlanRequest.constraints.safety_band."
    },
    "has_side_effects": {
      "type": "boolean",
      "default": false,
      "description": "If true, Planner sets PlanStep.has_side_effects=True for saga compensation."
    },
    "compensation_capability": {
      "type": ["string", "null"],
      "description": "Capability to call for rollback. Forwarded to PlanStep.compensation."
    },
    "estimated_duration_ms": {
      "type": ["integer", "null"],
      "minimum": 0,
      "description": "Estimated execution time. Planner uses this for timeout_ms and BUDGET-1 time estimation."
    },
    "domains": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Semantic domains this capability belongs to."
    },
    "description": {
      "type": "string",
      "description": "Human-readable description for Planner LLM context."
    }
  }
}
```

### 10.6 MicroReplan Round-Trip Contract

Full protocol for mid-DAG replanning (ORCH-13). Triggered when a step discovery reveals new information or a step fails with partial results.

```
DAGExecutor                       Orchestrator                      Planner
    |                                  |                               |
    |-- [step s2 completes] ---------> |                               |
    |   discovery detected             |                               |
    |                                  |                               |
    |-- MicroReplanCheckpoint guard -->|                               |
    |   replan_count == 0 (allowed)    |                               |
    |                                  |                               |
    |== BUILD MicroReplanRequest ======|                               |
    |   request_id = uuid4()           |                               |
    |   original_plan_id = plan.plan_id|                               |
    |   completed_results = {s1: OK}   |                               |
    |   discoveries = [{field, value}] |                               |
    |   remaining_steps = [s3, s4, s5] |                               |
    |   failure_context = null         |                               |
    |                                  |                               |
    |-- planner_port.micro_replan() ---|----------------------------->  |
    |   (SYNCHRONOUS, 10s timeout)     |                               |
    |                                  |                               |
    |                                  |   [Planner re-reasons]         |
    |                                  |   [May add/remove/modify steps]|
    |                                  |   [Preserves completed_results]|
    |                                  |                               |
    |<-- Optional[CommittedPlan] ------|<-- revised CommittedPlan ------|
    |                                  |                               |
    |== IF plan returned =============|                               |
    |   Replace remaining_waves        |                               |
    |   Re-run build_waves()           |                               |
    |   Continue DAG execution         |                               |
    |                                  |                               |
    |== IF None (timeout/failure) =====|                               |
    |   Continue with original plan    |                               |
    |   Log micro-replan failure       |                               |
    |                                  |                               |
    |-- replan_count = 1 (no more) ----|                               |
```

**MicroReplanRequest transport schema**:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "k1://schemas/orchestrator/micro_replan_request.v1.json",
  "title": "MicroReplanRequest",
  "description": "DAGExecutor -> Planner mid-execution replan request. SYNCHRONOUS (10s timeout).",
  "type": "object",
  "required": ["request_id", "original_plan_id", "remaining_steps", "trace_id"],
  "properties": {
    "request_id": {
      "type": "string",
      "format": "uuid"
    },
    "original_plan_id": {
      "type": "string",
      "format": "uuid",
      "description": "The plan currently being executed."
    },
    "completed_results": {
      "type": "object",
      "description": "Map of step_id -> StepResult.to_dict() for already-completed steps. Planner uses this to understand current state.",
      "additionalProperties": { "type": "object" }
    },
    "discoveries": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["field", "value", "source_step_id"],
        "properties": {
          "field": { "type": "string", "description": "What was discovered (e.g. 'restaurant_has_event_room')" },
          "value": { "description": "The discovered value" },
          "source_step_id": { "type": "string", "description": "Which step made the discovery" }
        }
      },
      "description": "New information found during execution that may change the plan."
    },
    "remaining_steps": {
      "type": "array",
      "items": { "type": "object" },
      "minItems": 1,
      "description": "Steps from original plan that have NOT yet executed. Planner may modify, add, or remove these."
    },
    "failure_context": {
      "type": ["object", "null"],
      "properties": {
        "step_id": { "type": "string" },
        "error_code": { "type": "string" },
        "error_message": { "type": "string" },
        "partial_result": { "type": ["object", "null"] }
      },
      "description": "If replan was triggered by step failure, includes failure details. Null if triggered by discovery."
    },
    "trace_id": {
      "type": "string",
      "format": "uuid"
    }
  }
}
```

**Key contract differences from request_plan()**:

| Aspect | request_plan() | micro_replan() |
|--------|---------------|----------------|
| **Delivery** | Fire-and-forget (async, event-driven) | Synchronous (blocking, 10s timeout) |
| **Response** | CommittedPlan via event bus (plan.ready.v1) | Optional[CommittedPlan] returned directly |
| **Correlation** | PendingPlanContext via request_id | Direct await (no parking) |
| **Context** | Full ContextSnapshot | completed_results + discoveries + remaining_steps |
| **Max calls** | Unlimited per session | Max 1 per DAG execution (ORCH-13) |
| **Timeout** | 45s (CB_PLANNER) | 10s (PROTOCOL-3) |
| **On failure** | AggregatedResult FAILED | Continue original plan (graceful) |

### 10.7 Planner Failure Modes and Degradation

The Orchestrator must handle every Planner failure mode gracefully.

| Failure Mode | Event/Signal | Orchestrator Response | Degradation Path |
|-------------|-------------|----------------------|------------------|
| Planner REJECTS plan request | PlanAck(status="REJECTED") from request_plan() | Return FAILED immediately | Concierge degrades HIGH -> MEDIUM (ADR-1.1.6) |
| Planner TIMEOUT (45s) | PendingPlanContext expired by reaper | cancel_plan(request_id) + FAILED AggregatedResult | Concierge degrades HIGH -> MEDIUM |
| Planner internal error | plan.failed.v1 event (reason=INTERNAL_ERROR) | Pop PendingPlanContext + FAILED AggregatedResult | Concierge degrades HIGH -> MEDIUM |
| No capabilities found | plan.failed.v1 event (reason=CAPABILITY_NOT_FOUND) | Pop PendingPlanContext + FAILED AggregatedResult | Concierge surfaces error to user |
| Constraints unsatisfiable | plan.failed.v1 event (reason=CONSTRAINT_UNSATISFIABLE) | Pop PendingPlanContext + FAILED AggregatedResult | Concierge asks user to relax constraints (HIL) |
| Planner cancelled externally | plan.cancelled.v1 event | Pop PendingPlanContext + CANCELLED AggregatedResult | Concierge surfaces cancellation |
| CB_PLANNER OPEN | ErrorRouter classifies as DEGRADED | Skip Planner entirely | degrade HIGH -> MEDIUM tier (1-2 direct Fabric calls) |
| Micro-replan timeout (10s) | micro_replan() returns None | Continue with original plan | No degradation (graceful fallback) |
| Micro-replan produces invalid plan | constraint_resolver.validate fails | Discard revised plan, continue original | No degradation (graceful fallback) |

**Circuit breaker integration** (CB_PLANNER):

```
                     +---> CLOSED (normal) ---+
                     |                        |
                     |   failure_count++      | failure_count >= 3
                     |   (plan.failed.v1 or   v
                     |    timeout expiry)   OPEN ----> all request_plan()
                     |                        |        return REJECTED
                     |   recovery_timeout     |
                     |   (45s)                v
                     +---- HALF_OPEN <--------+
                              |
                              | next request_plan()
                              | success -> CLOSED
                              | failure -> OPEN
```

### 10.8 Budget Passthrough Contract

How budget constraints flow from Concierge through Orchestrator to Planner and back.

```
Concierge                   Orchestrator                      Planner
  |                              |                               |
  | TaskEnvelope.constraints:    |                               |
  |   time_budget_ms: 30000     |                               |
  |   safety_band: GREEN        |                               |
  |                              |                               |
  |-- envelope ----------------->| PlanRequest.constraints:      |
  |                              |   time_budget_ms: 30000       |
  |                              |   safety_band: GREEN          |
  |                              |                               |
  |                              |-- plan_request -------------->|
  |                              |                               |
  |                              |   [Planner builds plan within |
  |                              |    these constraints.          |
  |                              |    Stage 3 VALIDATE checks    |
  |                              |    budget feasibility.]        |
  |                              |                               |
  |                              |<-- CommittedPlan:             |
  |                              |   estimated_duration_ms: 25000| (Planner's estimate)
  |                              |                               |
  |                              |== NO TOKEN/COST ENFORCEMENT ==|
  |                              |   V1: Fabric CapabilityResult |
  |                              |   has no token/cost fields.   |
  |                              |   TokenBudgetTracker and      |
  |                              |   CostAccumulator DEFERRED    |
  |                              |   to V2.                      |
  |                              |                               |
```

**Budget fields flow**:

| Field | Concierge Sets | Orchestrator Passes | Planner Echoes | Orchestrator Enforces |
|-------|---------------|--------------------|--------------|-----------------------|
| ~~`token_budget_max`~~ | ~~TaskEnvelope.constraints~~ | ~~PlanRequest.constraints~~ | ~~CommittedPlan.token_budget_max~~ | **V1 REMOVED** — no upstream data |
| ~~`cost_budget_max_usd`~~ | ~~TaskEnvelope.constraints~~ | ~~PlanRequest.constraints~~ | ~~CommittedPlan.cost_budget_max_usd~~ | **V1 REMOVED** — no upstream data |
| `time_budget_ms` | TaskEnvelope.constraints | PlanRequest.constraints | CommittedPlan.estimated_duration_ms | BUDGET-1 time pressure in ConstraintResolver |
| `safety_band` | TaskEnvelope.constraints | PlanRequest.constraints | Validated in Stage 3 | Re-read at wave boundary (state_port) |
| ~~Per-step `token_budget`~~ | ~~--~~ | ~~--~~ | ~~PlanStep.token_budget (allocation)~~ | **V1 REMOVED** — no upstream data |

### 10.9 Planner 4-Stage Pipeline Types (Planner-Internal, Cross-Reference)

These types are Planner-internal (Orchestrator does NOT import them), but the Orchestrator team must understand them to reason about what CommittedPlan contains and how Planner failure modes manifest.

| Stage | Output Type | Key Fields | How It Affects Orchestrator |
|-------|------------|------------|---------------------------|
| Stage 1: SKETCH | `SketchPlan` | intent, steps (basic), complexity, raw_output, latency_ms | If LLM fails here -> plan.failed.v1 with INTERNAL_ERROR |
| Stage 2: EXPAND | `ExpandedPlan` | steps (with tool/agent details), complexity, latency_ms | Populates PlanStep fields 2-6, 7-14. If tool not found -> plan.failed.v1 with CAPABILITY_NOT_FOUND |
| Stage 3: VALIDATE | `ValidatedPlan` | steps, status (PASSED/FAILED/REQUIRES_ARBITER), validation_results | If FAILED -> plan.failed.v1 with CONSTRAINT_UNSATISFIABLE. If REQUIRES_ARBITER -> HIL request before commit |
| Stage 4: COMMIT | `CommittedPlan` | Full production CommittedPlan (Section 10.3) | Success -> plan.ready.v1 event to Orchestrator |

**Planner-internal type definitions** (from POC `data_models.py`, reference only):

```python
# Planner-internal enums
class StepOp(str, Enum):
    TOOL = "Tool"       # Call MCP tool
    MODEL = "Model"     # Call LLM for reasoning
    ASK = "Ask"         # Ask user for input (HIL)

class PlanComplexity(str, Enum):
    SIMPLE = "simple"   # 1-2 steps, <500ms
    MEDIUM = "medium"   # 3-5 steps, <2s
    COMPLEX = "complex" # 6+ steps, <5s

class ValidationStatus(str, Enum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    FAILED = "FAILED"
    REQUIRES_ARBITER = "REQUIRES_ARBITER"

# Planner-internal types (NOT imported by Orchestrator)
@dataclass
class SketchPlan:
    intent: str
    steps: List[PlanStep]   # basic 5-field PlanStep
    complexity: PlanComplexity
    raw_output: str
    latency_ms: float
    trace_id: str = ""

@dataclass
class ExpandedPlan:
    intent: str
    steps: List[PlanStep]   # full PlanStep with tool/agent details
    complexity: PlanComplexity
    latency_ms: float
    trace_id: str = ""

@dataclass
class ValidatedPlan:
    intent: str
    steps: List[PlanStep]
    complexity: PlanComplexity
    status: ValidationStatus
    validation_results: List[ValidationResult]
    latency_ms: float
    requires_arbiter: bool = False
    trace_id: str = ""
```

### 10.10 request_id Correlation Contract

The most critical cross-module contract: how a PlanRequest is correlated with its CommittedPlan.

```
Orchestrator generates:              Planner echoes:                Orchestrator correlates:
  request_id = uuid4()          -->    request_id (in CommittedPlan)  -->  pending_plans.pop(request_id)
                                       request_id (in plan.ready.v1)       PendingPlanContext found
                                       request_id (in plan.failed.v1)      PendingPlanContext found
                                       request_id (in plan.cancelled.v1)   PendingPlanContext found
```

**Rules**:

1. Orchestrator generates `request_id` (uuid4) in `dispatch_high()`
2. `request_id` is set on `PlanRequest` and stored as the key in `pending_plans` dict
3. Planner MUST include `request_id` in ALL response events (ready, failed, cancelled)
4. Orchestrator pops `pending_plans[request_id]` on any response
5. If `request_id` not found in `pending_plans`: either timeout already expired (stale event) or orphan event. Log warning, check WAL for recovery, else discard.
6. `plan_id` is generated by the Planner (different from `request_id`). Orchestrator uses `plan_id` for dedup (`executed_plans` set) and WAL tracking after execution starts.

**Failure scenario - RACE-2 (orphan plan)**:

```
Orchestrator                           Planner
  |-- request_plan(request_id=A) ---->|
  |                                    |
  | [45s timeout expires]              | [Planner still working...]
  | pending_plans.pop(A) -> FAILED     |
  | cancel_plan(A) (best effort) ----->| [may or may not receive]
  |                                    |
  |                                    |-- plan.ready.v1(request_id=A)
  |<-- plan arrives in mailbox --------|
  |                                    |
  | receive_plan(): pending_plans[A]   |
  |   NOT FOUND (already expired)      |
  | -> check WAL: bridge_port.read_wal()
  |   WAL empty (never started DAG)    |
  | -> log orphan, discard plan        |
```

### 10.11 Action Required

| Action | Location | Priority |
|--------|----------|----------|
| Add PlanRequest JSON Schema file | `k1/contracts/schemas/orchestrator/plan_request.v1.json` | P0 |
| Add MicroReplanRequest JSON Schema file | `k1/contracts/schemas/orchestrator/micro_replan_request.v1.json` | P0 |
| Add CapabilityDescriptor JSON Schema file | `k1/contracts/schemas/fabric/capability_descriptor.v1.json` | P0 |
| Update CommittedPlan (1.2.3) to match reconciled spec | Implementation plan issue 1.2.3 | P0 |
| Add PlanStep field mapping table to Planner implementation plan | Planner plan (when created) | P1 |
| Define Planner contract YAML (module.contract.yaml) | `k1/contracts/modules/planner/module.contract.yaml` | P0 |
| Add Planner wiring.contract.yaml with discovery tool dependencies | `k1/contracts/modules/planner/wiring.contract.yaml` | P0 |
| Add IPlannerPort adapter contract test (request_id echo) | M7 issue 7.4.x | P0 |
| Document CB_PLANNER state machine in circuit breaker section (Section 7) | This whiteboard Section 7 | P1 |
| Add RACE-2 orphan plan test to integration tests | M7 issue 7.3A.x | P1 |

---

## Summary: New Issues Required

The following issues should be added to the orchestrator implementation plan to close these gaps:

| New Issue | Epic | Title | Priority |
|-----------|------|-------|----------|
| 1.2.21 | 1.2 | ProcessingContext standalone type definition | P0 |
| 1.2.22 | 1.2 | OrchestratorConfig dataclass | P0 |
| 1.2.23 | 1.2 | CircuitBreakerConfig + CircuitBreakerState types | P1 |
| 1.2.24 | 1.2 | Guard types (GuardAction, GuardDecision, Guard Protocols) | P1 |
| 1.2.25 | 1.2 | Admin types (HealthStatus, ActiveDAGInfo, DrainResult) | P1 |
| 1.2.26 | 1.2 | PlanRequest transport schema + CapabilityDescriptor schema | P0 |
| 1.2.27 | 1.2 | MicroReplanRequest transport schema | P0 |
| 1.5.1 | 1.5 (NEW) | Create 20 emitted event payload JSON Schemas | P0 |
| 1.5.2 | 1.5 (NEW) | Create 12 consumed event payload JSON Schemas | P0 |
| 1.5.3 | 1.5 (NEW) | Planner contract YAML (module + wiring) | P0 |
| 6.3.1 | 6.3 (NEW) | IAdminPort interface + admin types | P1 |
| 6.3.2 | 6.3 (NEW) | Admin HTTP adapter (aiohttp lightweight) | P1 |
| 6.3.3 | 6.3 (NEW) | Wire admin into OrchestratorFactory | P1 |
| 7.4.X | 7.4 | request_id echo contract test (Planner adapter) | P0 |
| 7.3A.X | 7.3A | RACE-2 orphan plan integration test | P1 |

---

## Schema Dependencies Graph

```
OrchestratorConfig (Section 2)
    |
    +-- CB thresholds (Section 7) ---> ErrorRouter (M2)
    +-- Guard thresholds (Section 8) ---> Guard pipeline (M3)
    +-- Mailbox config (Section 9) ---> MailboxAdapter (M6)
    +-- Admin config (Section 5) ---> Admin API (M6)

ProcessingContext (Section 1)
    |
    +-- All M2 service methods
    +-- All M3 guard evaluate() methods
    +-- Tracing (M8)

Event Payload Schemas (Section 3)
    |
    +-- wiring.contract.yaml (Section 4) ---> M1 issue 1.3.2
    +-- Contract tests (M7 Epic 7.4)

Planner-Orchestrator Protocol (Section 10)
    |
    +-- PlanRequest schema (10.2) ---> IPlannerPort.request_plan() (1.4.3)
    +-- CommittedPlan reconciled (10.3) ---> issue 1.2.3 + plan.ready.v1 (3.4.1)
    +-- PlanStep field mapping (10.4) ---> issue 1.2.18 + Planner Stage 2
    +-- CapabilityDescriptor (10.5) ---> Fabric discover_capabilities() contract
    +-- MicroReplan contract (10.6) ---> Guard G5 (3.2.5) + IPlannerPort.micro_replan()
    +-- Planner failure modes (10.7) ---> ErrorRouter (2.1.7) + CB_PLANNER (Section 7)
    +-- Budget passthrough (10.8) ---> **V1 DEFERRED** (TokenBudgetTracker + CostBudgetGuard removed)
    +-- request_id correlation (10.10) ---> PendingPlanContext (1.2.19) + RACE-2 tests

Guard Pipeline (Section 8)
    |
    +-- Guard types (1.2.24) ---> M3 implementation
    +-- Factory step 12 (M6)

Health Check (Section 6)
    |
    +-- Admin API (Section 5)
    +-- Production readiness (M9)
```

All sections in this whiteboard must be reviewed and accepted before M1 implementation begins.
