"""
Front Tool Schemas -- 5 Tools for the Concierge Voice
======================================================

V2 Design Ref: Section 6.1 (Front LLM tool schemas)

Tool categories:
  Read (2):      recall_memory, summarize_context
  Control (1):   dispatch_task
  Fabric (2):    discover_capabilities, invoke_capability

Note: Cognitive write tools (update_beliefs, update_scoreboard,
update_clarifications, update_narrative, refine_affect, promote_belief)
and the session bundle tool (update_session_bundle) were migrated to
``k1.concierge.section_update`` (M4 front deloading).

All schemas use the provider-agnostic ToolSchema from M03.
The Gemini adapter converts these to FunctionDeclaration format.
"""

from __future__ import annotations

from k1.concierge.llm.types import ToolSchema

# P1.1 -- Front gains direct Fabric access for LOW-tier single-step lookups.
# Both schemas live in schemas_fabric to avoid a cycle with schemas_back
# (which imports RECALL_MEMORY_SCHEMA from this module).
from k1.concierge.tools.schemas_fabric import (
    DISCOVER_CAPABILITIES_SCHEMA,
    INVOKE_CAPABILITY_SCHEMA,
)

# ===================================================================
# READ (2)
# ===================================================================

RECALL_MEMORY_SCHEMA = ToolSchema(
    name="recall_memory",
    description=(
        "Query K0 long-term memory for relevant context. Returns past experiences, "
        "preferences, facts, schedules, agendas, routines, and stored knowledge "
        "from previous sessions. Use for historical/context lookups: routines, "
        "preferences, past events, background rules, contacts, allergies, "
        "habits, and background facts. Do NOT use as the source of truth for live "
        "records owned by capabilities, connectors, databases, workflows, or external "
        "services; route those through dispatch_task or safe read capabilities. "
        "Examples: prior preference, remembered routine, historical incident, "
        "or stored background fact. "
        "Front uses for conversational context. Back uses for task-specific data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language memory query",
            },
            "memory_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["episodic", "semantic", "procedural"],
                },
                "description": "Which memory stores to search. Default: all.",
            },
            "max_results": {
                "type": "integer",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": ["query"],
    },
    returns={
        "type": "object",
        "properties": {
            "memories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "type": {"type": "string"},
                        "relevance": {"type": "number"},
                        "timestamp": {"type": "string"},
                    },
                },
            },
            "count": {"type": "integer"},
        },
    },
    actor="both",
    category="read",
    side_effects=False,
)

SUMMARIZE_CONTEXT_SCHEMA = ToolSchema(
    name="summarize_context",
    description=(
        "Compress Session State sections to fit within token budget. "
        "Call when the system prompt is too large. Returns compressed version "
        "of specified sections. This is a token management tool, not a user-facing tool."
    ),
    parameters={
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "SS section names to compress " "(e.g. ['beliefs_active', 'history_active'])"
                ),
            },
            "target_tokens": {
                "type": "integer",
                "description": "Target token count for compressed output",
            },
        },
        "required": ["sections", "target_tokens"],
    },
    returns={
        "type": "object",
        "properties": {
            "compressed": {
                "type": "string",
                "description": "Compressed text representation",
            },
            "original_tokens": {"type": "integer"},
            "compressed_tokens": {"type": "integer"},
        },
    },
    actor="front",
    category="read",
    side_effects=False,
)

# ===================================================================
# CONTROL (1)
# ===================================================================

DISPATCH_TASK_SCHEMA = ToolSchema(
    name="dispatch_task",
    description=(
        "Dispatch a task to the background worker for execution. Use when the user "
        "wants something DONE (search, book, create, schedule, send, draft, etc.). "
        "Also use for live system-of-record reads or writes that must be handled "
        "through capabilities rather than memory/context. "
        "Do NOT call for pure conversation, emotional support, or clarification. "
        "The FSM intercepts this tool call and emits k1.orchestration.task.dispatch.v1 "
        "on the bus. The tool itself returns immediately with {queued: true}. "
        "For multi-intent messages (including sequential ones), call dispatch_task "
        "ONCE with all intents in the intents array ordered logically. "
        "Only use depends_on with a task-ID from a previous dispatch_task result."
    ),
    parameters={
        "type": "object",
        "properties": {
            "intents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "What to do (natural language or capability name)",
                        },
                        "params": {
                            "type": "object",
                            "description": (
                                "Structured parameters extracted from " "conversation and beliefs"
                            ),
                        },
                        "resource_family": {
                            "type": "string",
                            "description": (
                                "Optional taxonomy family hint (e.g. 'item', 'event', 'task'). "
                                "Use the registered family_id from the context if known."
                            ),
                        },
                        "operation_hint": {
                            "type": "string",
                            "description": (
                                "Optional operation hint: 'create', 'read', 'update', 'delete'."
                            ),
                        },
                    },
                    "required": ["action"],
                },
                "minItems": 1,
                "description": (
                    "One or more intents to execute. Independent intents are "
                    "bundled. Sequential intents use depends_on."
                ),
            },
            "urgency": {
                "type": "string",
                "enum": ["normal", "urgent", "background"],
                "default": "normal",
            },
            "reference_context": {
                "type": "object",
                "description": (
                    "Resolved references for the Back worker. Front resolves pronouns and "
                    "references using its 20-entry history view and passes resolved values "
                    "here. E.g. {'the hotel': 'Vineyard Inn', 'it': 'restaurant search'}. "
                    "For follow-up updates to recent artifacts, include the target artifact "
                    "or record plus any general_context_to_add and authority/provenance notes."
                ),
                "additionalProperties": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "number"},
                        {"type": "boolean"},
                        {"type": "object"},
                        {"type": "array"},
                        {"type": "null"},
                    ]
                },
            },
            "depends_on": {
                "type": "string",
                "description": (
                    "Task ID (e.g. 'task-a1b2c3d4') returned by a PREVIOUS "
                    "dispatch_task call. Use ONLY when this dispatch must wait "
                    "for a prior task's result. Must start with 'task-'. "
                    "For multiple intents in one request, bundle them in the "
                    "intents array instead -- do NOT use depends_on."
                ),
            },
            "plan": {
                "type": "boolean",
                "default": False,
                "description": (
                    "P3.4c: Set true when the task requires a planner, specialist, "
                    "or nontrivial multi-step workflow. Simple multi-intent bundles "
                    "do not need this flag; depends_on still escalates to plan tier."
                ),
            },
        },
        "required": ["intents"],
    },
    returns={
        "type": "object",
        "properties": {
            "queued": {"type": "boolean"},
            "task_id": {"type": "string"},
        },
    },
    actor="front",
    category="control",
    side_effects=False,  # Tool itself does not mutate -- FSM emits the event
)

# ===================================================================
# Aggregated list -- 5 Front tools (cognitive + bundle migrated to section_update)

FRONT_TOOL_SCHEMAS: list[ToolSchema] = [
    # Read
    RECALL_MEMORY_SCHEMA,
    SUMMARIZE_CONTEXT_SCHEMA,
    # Control
    DISPATCH_TASK_SCHEMA,
    # Fabric (P1.1) -- Front direct capability access for LOW-tier lookups
    DISCOVER_CAPABILITIES_SCHEMA,
    INVOKE_CAPABILITY_SCHEMA,
]


# ===================================================================
# M13.E1 -- Front-allowed read-only / safe capability whitelist
# ===================================================================
#
# Front is the user-facing voice and MUST NOT execute side-effecting,
# safety-sensitive, or AMBER+/RED storyline acts directly. The Back
# actor is the only path for those (via dispatch_task -> ReAct loop).
#
# This whitelist is the authoritative source for both:
#   * the policy gate (k1.selfmodel.adapters.concierge_policy_gate),
#     which DENIES `invoke_capability` from Front with an inner
#     capability outside this set, and
#   * the dispatcher handler defense-in-depth in
#     k1.concierge.tools.implementations.execute_invoke_capability.
#
# Add ONLY genuinely read-only or low-risk discovery capabilities here.
# When in doubt, route through Back via dispatch_task.
FRONT_READ_CAPABILITY_WHITELIST: frozenset[str] = frozenset(
    {
        # Read-only lookups (LOW risk per k1/contracts/tools/*.yaml)
        "tool.execute.weather_current",
        "tool.execute.weather_forecast",
        "tool.execute.unit_convert",
        "tool.execute.recipe_search",
        "tool.execute.notes_search",
        "tool.execute.notes_list",
        "tool.execute.find_prompts",
        "tool.execute.discover_capabilities",
        "tool.execute.date_calc",
        "tool.execute.calendar_list_events",
        "tool.read.calendar.list_events",
        "tool.read.calendar.get_event",
        "tool.read.tasks.list_tasks",
        "tool.read.tasks.get_task",
        "tool.read.reminders.list_reminders",
        "tool.read.reminders.get_reminder",
        "tool.read.chores.list_chores",
        "tool.read.chores.chore_summary",
        "tool.read.family_settings.get_visibility_policy",
        "tool.read.family_settings.list_feature_flags",
    }
)


__all__ = [
    "FRONT_TOOL_SCHEMAS",
    "FRONT_READ_CAPABILITY_WHITELIST",
    "RECALL_MEMORY_SCHEMA",
    "SUMMARIZE_CONTEXT_SCHEMA",
    "DISPATCH_TASK_SCHEMA",
    "DISCOVER_CAPABILITIES_SCHEMA",
    "INVOKE_CAPABILITY_SCHEMA",
]
