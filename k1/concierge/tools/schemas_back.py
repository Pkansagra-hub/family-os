"""
Back Tool Schemas -- 6 Tools for the Background Worker
======================================================

V2 Design Ref: Section 6.2 (Back LLM tool schemas)

Tool categories:
  Read (2):    recall_memory (shared from Front), discover_capabilities
  Action (3):  invoke_capability, spawn_via_fabric, execute_workflow
  Control (1): submit_result

Tier-based allowlists:
  LOW  (4): recall_memory, discover_capabilities, invoke_capability, submit_result
  MEDIUM/HIGH (6): all
"""

from __future__ import annotations

from k1.concierge.llm.types import ToolSchema

# P1.1: discover_capabilities + invoke_capability live in schemas_fabric
# so they can be shared with Front without a schemas_front <-> schemas_back
# import cycle. Re-exported here to preserve the historical public surface
# (`from k1.concierge.tools.schemas_back import DISCOVER_CAPABILITIES_SCHEMA`).
from k1.concierge.tools.schemas_fabric import DISCOVER_CAPABILITIES_SCHEMA, INVOKE_CAPABILITY_SCHEMA

# Import shared schema -- recall_memory is actor="both"
from k1.concierge.tools.schemas_front import RECALL_MEMORY_SCHEMA

# ===================================================================
# ACTION (continued -- batch invocation)
# ===================================================================

BATCH_INVOKE_CAPABILITIES_SCHEMA = ToolSchema(
    name="batch_invoke_capabilities",
    description=(
        "Invoke MULTIPLE capabilities in a single tool call. Each invocation "
        "in the batch runs independently. Use when you need to execute 2+ "
        "capabilities (e.g. set_reminder + send_message + set_alarm) to save "
        "tool budget. Costs only 1 tool call regardless of batch size. "
        "Available at all tiers."
    ),
    parameters={
        "type": "object",
        "properties": {
            "invocations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "capability_name": {
                            "type": "string",
                            "description": "Exact name of the capability to invoke",
                        },
                        "params": {
                            "type": "object",
                            "description": "Parameters for the capability",
                        },
                    },
                    "required": ["capability_name", "params"],
                },
                "description": (
                    "Array of capability invocations to execute. "
                    "Each has capability_name and params."
                ),
                "minItems": 1,
                "maxItems": 8,
            },
        },
        "required": ["invocations"],
    },
    returns={
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "capability_name": {"type": "string"},
                        "result": {"type": "object"},
                        "status": {
                            "type": "string",
                            "enum": ["success", "error"],
                        },
                    },
                },
            },
            "total": {"type": "integer"},
            "succeeded": {"type": "integer"},
            "failed": {"type": "integer"},
        },
    },
    actor="back",
    category="action",
    side_effects=True,
)

SPAWN_VIA_FABRIC_SCHEMA = ToolSchema(
    name="spawn_via_fabric",
    description=(
        "Spawn a specialized agent via the K0 Agent Fabric to handle a complex "
        "sub-task. Use when invoke_capability is insufficient and a full agent "
        "lifecycle is needed (multi-step reasoning, long-running operations). "
        "MEDIUM and HIGH tier only."
    ),
    parameters={
        "type": "object",
        "properties": {
            "agent_type": {
                "type": "string",
                "description": (
                    "Type of agent to spawn " "(e.g. 'research', 'booking', 'planning', 'creative')"
                ),
            },
            "task": {
                "type": "string",
                "description": "Natural language description of the task for the agent",
            },
            "constraints": {
                "type": "object",
                "description": (
                    "Agent constraints "
                    "(e.g. {'max_steps': 10, 'timeout_ms': 30000, 'budget_usd': 0.50})"
                ),
            },
            "capabilities_needed": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Capabilities the agent needs " "(e.g. ['web_search', 'booking_api'])"
                ),
            },
        },
        "required": ["agent_type", "task"],
    },
    returns={
        "type": "object",
        "properties": {
            "agent_id": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["spawned", "queued", "rejected"],
            },
            "estimated_duration_ms": {"type": "integer"},
        },
    },
    actor="back",
    category="action",
    side_effects=True,
)

EXECUTE_WORKFLOW_SCHEMA = ToolSchema(
    name="execute_workflow",
    description=(
        "Execute a predefined workflow by ID. Workflows are multi-step "
        "orchestration plans stored in K0. Use for recurring tasks with "
        "known steps (e.g. 'book_hotel_workflow', 'weekly_meal_plan_workflow'). "
        "MEDIUM and HIGH tier only."
    ),
    parameters={
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "ID of the workflow to execute",
            },
            "params": {
                "type": "object",
                "description": "Input parameters for the workflow",
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Max execution time in milliseconds",
                "default": 30000,
            },
        },
        "required": ["workflow_id", "params"],
    },
    returns={
        "type": "object",
        "properties": {
            "execution_id": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["completed", "running", "failed"],
            },
            "result": {"type": "object"},
        },
    },
    actor="back",
    category="action",
    side_effects=True,
)

# ===================================================================
# CONTROL (1)
# ===================================================================

SUBMIT_RESULT_SCHEMA = ToolSchema(
    name="submit_result",
    description=(
        "Submit the task result back to the Front LLM via the orchestrator. "
        "Call EXACTLY ONCE as the final tool call in every Back execution. "
        "result_type='complete' when task is done; "
        "result_type='needs_human' when human-in-the-loop is required "
        "(confirmation, choice, escalation). Available at all tiers."
    ),
    parameters={
        "type": "object",
        "properties": {
            "result_type": {
                "type": "string",
                "enum": ["complete", "needs_human"],
            },
            # -- Fields for result_type="complete" --
            "final_answer": {
                "type": "string",
                "description": "Natural language summary of what was done (for complete)",
            },
            "results": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Structured results array (for complete)",
            },
            "artifacts_created": {
                "type": "array",
                "items": {"type": "string"},
                "description": "IDs of artifacts created (for complete)",
            },
            # -- Fields for result_type="needs_human" --
            "hil_type": {
                "type": "string",
                "enum": ["confirm", "choose", "provide_info", "clarification", "escalate"],
                "description": "Type of human-in-the-loop needed (for needs_human)",
            },
            "question": {
                "type": "string",
                "description": "Question to present to user (for needs_human)",
            },
            "options": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Options for user to choose from (for needs_human choose)",
            },
            "side_effects": {
                "type": "string",
                "description": "What will happen if confirmed (for needs_human confirm)",
            },
        },
        "required": ["result_type"],
    },
    returns={
        "type": "object",
        "properties": {
            "delivered": {"type": "boolean"},
            "weave_event_id": {"type": "string"},
        },
    },
    actor="back",
    category="control",
    side_effects=False,  # Tool itself doesn't mutate -- FSM handles routing
)

# ===================================================================
# Aggregated list -- all 6 Back tools
# ===================================================================

BACK_TOOL_SCHEMAS: list[ToolSchema] = [
    # Read
    RECALL_MEMORY_SCHEMA,
    DISCOVER_CAPABILITIES_SCHEMA,
    # Action
    INVOKE_CAPABILITY_SCHEMA,
    BATCH_INVOKE_CAPABILITIES_SCHEMA,
    SPAWN_VIA_FABRIC_SCHEMA,
    EXECUTE_WORKFLOW_SCHEMA,
    # Control
    SUBMIT_RESULT_SCHEMA,
]

# ===================================================================
# Tier-based allowlists (P3.4b: collapsed to {simple, plan} with legacy aliases)
# ===================================================================

_BACK_SIMPLE_LIST: list[str] = [
    "recall_memory",
    "discover_capabilities",
    "invoke_capability",
    "batch_invoke_capabilities",
    "submit_result",
]

_BACK_PLAN_EXTRA: list[str] = ["spawn_via_fabric", "execute_workflow"]

BACK_TIER_ALLOWLISTS: dict[str, list[str]] = {
    "simple": _BACK_SIMPLE_LIST,
    "plan": _BACK_SIMPLE_LIST + _BACK_PLAN_EXTRA,
    # Legacy aliases:
    "LOW": _BACK_SIMPLE_LIST,
    "MEDIUM": _BACK_SIMPLE_LIST + _BACK_PLAN_EXTRA,
    "HIGH": _BACK_SIMPLE_LIST + _BACK_PLAN_EXTRA,
}
