"""
Orchestrator Event Catalog -- Topic string constants for the event bus.

Module-level string constants (not an enum) for event bus compatibility.
Pattern: ORCH_<CATEGORY>_<ACTION> = "k1.orchestration.<category>.<action>.v1"

Each constant MUST match exactly what IEventSubscriptionPort.subscribe() uses.
Typos here mean silent event drops.

Single source of truth -- do NOT hardcode topic strings anywhere else.
Import from k1.orchestrator.events, e.g.:
  from k1.orchestrator.events import ORCH_DAG_STARTED, ORCH_STEP_COMPLETED

V1 removed events (phantom field consumers):
  STEP_QUALITY_RETRY, DAG_BUDGET_WARNING, DAG_BUDGET_EXHAUSTED
  -- no provider populates cost/token/quality metadata.
"""

# ===========================================================================
# Emitted events (17) -- Orchestrator publishes these
# ===========================================================================

# Task lifecycle
ORCH_TASK_ACCEPTED: str = "k1.orchestration.task.accepted.v1"

# Plan lifecycle
ORCH_PLAN_REQUESTED: str = "k1.orchestration.plan.requested.v1"

# DAG lifecycle
ORCH_DAG_STARTED: str = "k1.orchestration.dag.started.v1"
ORCH_DAG_MICRO_REPLAN: str = "k1.orchestration.dag.micro_replan.v1"
# M16.E2.I2: emitted when a DAG node fails after dependents have been cancelled.
# Carries enough context for FailureReplanCheckpoint (and external observers)
# to decide whether to request a planner amend for the failed branch.
ORCH_DAG_NODE_FAILED: str = "k1.orchestration.dag.node_failed.v1"
ORCH_DAG_COMPLETED: str = "k1.orchestration.dag.completed.v1"
# V1 REMOVED: ORCH_DAG_BUDGET_WARNING, ORCH_DAG_BUDGET_EXHAUSTED

# Step lifecycle
ORCH_STEP_STARTED: str = "k1.orchestration.step.started.v1"
ORCH_STEP_COMPLETED: str = "k1.orchestration.step.completed.v1"
ORCH_STEP_FAILED: str = "k1.orchestration.step.failed.v1"
ORCH_STEP_CANCELLED: str = "k1.orchestration.step.cancelled.v1"
ORCH_STEP_SKIPPED: str = "k1.orchestration.step.skipped.v1"
ORCH_STEP_RETRYING: str = "k1.orchestration.step.retrying.v1"
ORCH_STEP_SCHEMA_RETRY: str = "k1.orchestration.step.schema_retry.v1"
# V1 REMOVED: ORCH_STEP_QUALITY_RETRY

# Saga
ORCH_SAGA_COMPENSATING: str = "k1.orchestration.saga.compensating.v1"

# Delta (progress updates to Concierge)
ORCH_DELTA_V1: str = "k1.orchestration.delta.v1"

# Workflow lifecycle
ORCH_WORKFLOW_TRIGGERED: str = "k1.orchestration.workflow.triggered.v1"
ORCH_WORKFLOW_COMPLETED: str = "k1.orchestration.workflow.completed.v1"
ORCH_WORKFLOW_SAVED: str = "k1.orchestration.workflow.saved.v1"

# Error routing diagnostics
ORCH_ERROR_ROUTED: str = "k1.orchestration.error.routed.v1"

# MCP connector
ORCH_MCP_TOOL_REGISTERED: str = "k1.orchestration.mcp.tool_registered.v1"


# ===========================================================================
# Consumed events (12) -- Orchestrator subscribes to these
# ===========================================================================

# Planner responses
PLAN_READY: str = "k1.planner.plan.ready.v1"
PLAN_FAILED: str = "k1.planner.plan.failed.v1"
PLAN_CANCELLED: str = "k1.planner.plan.cancelled.v1"
# NOTE: micro_replan is SYNCHRONOUS (IPlannerPort.micro_replan() returns directly).
# This event is TELEMETRY-ONLY -- emitted by Planner for Learning Loop observability.
# Orchestrator does NOT use this for plan delivery. Retained in ALL_CONSUMED for
# telemetry logging / drift detection metrics only.
MICRO_REPLAN_READY: str = "k1.planner.micro_replan.ready.v1"

# Fabric capability results
CAPABILITY_COMPLETED: str = "k1.capability.completed.v1"
CAPABILITY_FAILED: str = "k1.capability.failed.v1"

# Fabric contract/provider changes
CONTRACT_UPDATED: str = "k1.fabric.contract.updated.v1"

# Fabric agent activity (for ExecutionMonitor substep tracking)
AGENT_TOOL_CALL: str = "k1.fabric.agent.tool_call.v1"
AGENT_LLM_CALL: str = "k1.fabric.agent.llm_call.v1"

# Workflow scheduler (self-emitted by scheduler for cron/event triggers)
WORKFLOW_TRIGGER_DUE: str = "k1.orchestration.workflow.trigger_due.v1"


# ===========================================================================
# Aggregate sets for bulk validation in tests
# ===========================================================================

ALL_EMITTED: frozenset = frozenset(
    {
        ORCH_TASK_ACCEPTED,
        ORCH_PLAN_REQUESTED,
        ORCH_DAG_STARTED,
        ORCH_DAG_MICRO_REPLAN,
        ORCH_DAG_NODE_FAILED,
        ORCH_DAG_COMPLETED,
        ORCH_STEP_STARTED,
        ORCH_STEP_COMPLETED,
        ORCH_STEP_FAILED,
        ORCH_STEP_CANCELLED,
        ORCH_STEP_SKIPPED,
        ORCH_STEP_RETRYING,
        ORCH_STEP_SCHEMA_RETRY,
        ORCH_SAGA_COMPENSATING,
        ORCH_DELTA_V1,
        ORCH_WORKFLOW_TRIGGERED,
        ORCH_WORKFLOW_COMPLETED,
        ORCH_WORKFLOW_SAVED,
        ORCH_ERROR_ROUTED,
        ORCH_MCP_TOOL_REGISTERED,
    }
)

ALL_CONSUMED: frozenset = frozenset(
    {
        PLAN_READY,
        PLAN_FAILED,
        PLAN_CANCELLED,
        MICRO_REPLAN_READY,
        CAPABILITY_COMPLETED,
        CAPABILITY_FAILED,
        CONTRACT_UPDATED,
        AGENT_TOOL_CALL,
        AGENT_LLM_CALL,
        WORKFLOW_TRIGGER_DUE,
    }
)
