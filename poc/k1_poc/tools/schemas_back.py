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

from poc.k1_poc.llm.types import ToolSchema

# Import shared schema -- recall_memory is actor="both"
from poc.k1_poc.tools.schemas_front import RECALL_MEMORY_SCHEMA

# ===================================================================
# READ (1 exclusive + 1 shared = 2)
# ===================================================================

DISCOVER_CAPABILITIES_SCHEMA = ToolSchema(
    name="discover_capabilities",
    description=(
        "Query the K0 capability registry to find services, agents, or workflows "
        "that can handle a given intent. Returns ranked matches with confidence "
        "scores. Call BEFORE invoke_capability or spawn_via_fabric to find "
        "available options. Available in ALL tiers."
    ),
    parameters={
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "description": (
                    "What you need to accomplish "
                    "(e.g. 'search hotels', 'book flight', 'create workout plan')"
                ),
            },
            "domain": {
                "type": "string",
                "description": "Domain hint to narrow search (travel, health, etc.)",
            },
            "constraints": {
                "type": "object",
                "description": (
                    "Capability requirements " "(e.g. {'real_time': true, 'max_latency_ms': 5000})"
                ),
            },
        },
        "required": ["intent"],
    },
    returns={
        "type": "object",
        "properties": {
            "capabilities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "confidence": {"type": "number"},
                        "provider": {"type": "string"},
                    },
                },
            },
            "count": {"type": "integer"},
        },
    },
    actor="back",
    category="read",
    side_effects=False,
)

# ===================================================================
# ACTION (3)
# ===================================================================

INVOKE_CAPABILITY_SCHEMA = ToolSchema(
    name="invoke_capability",
    description=(
        "Invoke a known K0 capability by name with parameters. "
        "Use after discover_capabilities identifies the right service, "
        "or when you already know the capability name from prior tasks. "
        "Available at all tiers. For invoking MULTIPLE independent "
        "capabilities, prefer batch_invoke_capabilities to save budget."
    ),
    parameters={
        "type": "object",
        "properties": {
            "capability_name": {
                "type": "string",
                "description": "Exact name of the capability to invoke",
            },
            "params": {
                "type": "object",
                "description": (
                    "Parameters for the capability, matching its schema "
                    "(e.g. {'destination': 'Napa', 'dates': {'start': '2025-06-15', 'end': '2025-06-17'}})"
                ),
            },
            "session_id": {
                "type": "string",
                "description": "Session ID for stateful capabilities. Optional.",
            },
        },
        "required": ["capability_name", "params"],
    },
    returns={
        "type": "object",
        "properties": {
            "result": {"type": "object", "description": "Capability output"},
            "duration_ms": {"type": "integer"},
            "status": {
                "type": "string",
                "enum": ["success", "partial", "error"],
            },
        },
    },
    actor="back",
    category="action",
    side_effects=True,
)

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
# Tier-based allowlists (V2 Section 6.2)
# ===================================================================

BACK_TIER_ALLOWLISTS: dict[str, list[str]] = {
    "LOW": [
        "recall_memory",
        "discover_capabilities",
        "invoke_capability",
        "batch_invoke_capabilities",
        "submit_result",
    ],
    "MEDIUM": [
        "recall_memory",
        "discover_capabilities",
        "invoke_capability",
        "batch_invoke_capabilities",
        "spawn_via_fabric",
        "execute_workflow",
        "submit_result",
    ],
    "HIGH": [
        "recall_memory",
        "discover_capabilities",
        "invoke_capability",
        "batch_invoke_capabilities",
        "spawn_via_fabric",
        "execute_workflow",
        "submit_result",
    ],
}
