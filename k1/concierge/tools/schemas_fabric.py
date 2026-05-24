"""
Fabric Tool Schemas -- shared between Front and Back actors.
============================================================

P1.1: `discover_capabilities` and `invoke_capability` are exposed to BOTH
Front (LOW-tier direct lookups) and Back (workflow execution). Defining
them in a neutral module avoids the schemas_front <-> schemas_back
circular import that arises if either one tries to re-export from the
other.

Both schemas keep `actor="both"` so prompt-builder gating is governed by
the per-mode TOOL_ALLOWLIST, not by the schema's actor field.
"""

from __future__ import annotations

from k1.concierge.llm.types import ToolSchema

# ===================================================================
# DISCOVER -- read-only capability lookup
# ===================================================================

DISCOVER_CAPABILITIES_SCHEMA = ToolSchema(
    name="discover_capabilities",
    description=(
        "Find the external capabilities this LLM can use to read from or act through "
        "family apps, adapters, tools, agents, and workflows. Returns a SLIM candidate "
        "list (name, brief, domain, side-effect flag, safety band) so you can pick "
        "which capabilities matter. Use it when the user's goal needs information or "
        "action outside the chat and you do not already know the exact executable "
        "handle. Search by the user's real-world intent, not by architecture labels. "
        "Returned `name` values are executable handles. "
        "WORKFLOW: discover_capabilities -> get_capability_schemas([selected_names]) "
        "-> invoke_capability or batch_invoke_capabilities. Do not invoke before "
        "fetching the schema unless the capability has no required inputs. "
        "For family source-of-record reads, prefer concrete adapter domains such as "
        "calendar, reminders, tasks, chores, shopping, contacts, household, "
        "coordination, scheduling, or alerting. Avoid broad labels such as "
        "productivity; omit domain when unsure. Never ask the user for internal "
        "capability names."
    ),
    parameters={
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "description": (
                    "Single real-world information need or action to perform through external "
                    "tools, apps, agents, or workflows. Use the user's goal in plain language, "
                    "e.g. 'list upcoming calendar events', 'read active reminders', or "
                    "'create a task for tomorrow'. For multi-intent tasks (the dispatch_task "
                    "payload carries more than one intent), PREFER the `intents` array field "
                    "below and pass ALL intents in a single discover_capabilities call instead "
                    "of fanning out N separate calls."
                ),
            },
            "intents": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Multi-intent batched discovery. Pass the full list of real-world goals "
                    "from the dispatch_task payload in ONE call (e.g. ['list reminders', "
                    "'list calendar events', 'list tasks', 'list chores']). The kernel will "
                    "fan out internally and return a single merged capabilities list, "
                    "deduplicated by capability name. This is the preferred shape whenever "
                    "the task has 2+ intents -- it costs 1 tool call instead of N."
                ),
            },
            "domain": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional concrete app/tool domain hints to focus discovery. Use labels such "
                    "as calendar, reminders, tasks, chores, shopping, contacts, household, "
                    "coordination, scheduling, alerting, finance, travel, health, or "
                    "education. Do not use broad umbrella labels such as productivity; "
                    "omit this field when unsure. Applied uniformly across all intents when "
                    "the `intents` array is used."
                ),
            },
            "constraints": {
                "type": "object",
                "description": (
                    "Requirements for the external execution surface, such as read-only, "
                    "requires_confirmation, real_time, max_latency_ms, or allowed side effects."
                ),
            },
        },
    },
    returns={
        "type": "object",
        "properties": {
            "capabilities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Exact executable capability name. Copy verbatim into get_capability_schemas.capability_names or invoke_capability.capability_name.",
                        },
                        "brief": {
                            "type": "string",
                            "description": "One-line summary (<=140 chars). For full description + input schema, call get_capability_schemas with this name.",
                        },
                        "domain": {"type": "string"},
                        "has_side_effects": {"type": "boolean"},
                        "safety_band_min": {"type": "string"},
                        "requires_human_confirmation": {
                            "type": "boolean",
                            "description": "Present only when explicitly required by the capability.",
                        },
                    },
                },
            },
            "count": {"type": "integer"},
            "intent_results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string"},
                        "count": {"type": "integer"},
                    },
                },
                "description": "Per-intent retrieval health when called with intents[] batch shape.",
            },
        },
    },
    actor="both",
    category="read",
    side_effects=False,
)


# ===================================================================
# GET_CAPABILITY_SCHEMAS -- fetch full contract for discovered names
# ===================================================================

GET_CAPABILITY_SCHEMAS_SCHEMA = ToolSchema(
    name="get_capability_schemas",
    description=(
        "Fetch the FULL schema for capabilities you have already discovered. "
        "Workflow: 1) discover_capabilities -> slim list of candidates, "
        "2) get_capability_schemas([names]) -> required/optional inputs, "
        "output shape, side effects, safety band, HIL requirements, "
        "3) invoke_capability or batch_invoke_capabilities to execute. "
        "Pass exact name strings from discover_capabilities.capabilities[].name. "
        "Batch ALL needed schemas in ONE call -- costs only 1 tool slot regardless "
        "of how many schemas you fetch. Do NOT call invoke_capability before you "
        "have the schema unless the capability has no required inputs."
    ),
    parameters={
        "type": "object",
        "properties": {
            "capability_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Exact capability names from discover_capabilities. "
                    "Pass ALL the names you need to know how to call in one batch."
                ),
                "minItems": 1,
                "maxItems": 12,
            },
        },
        "required": ["capability_names"],
    },
    returns={
        "type": "object",
        "properties": {
            "schemas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "required_inputs": {"type": "array", "items": {"type": "object"}},
                        "optional_inputs": {"type": "array", "items": {"type": "object"}},
                        "has_side_effects": {"type": "boolean"},
                        "side_effects": {"type": "array", "items": {"type": "object"}},
                        "safety_band_min": {"type": "string"},
                        "requires_human_confirmation": {"type": "boolean"},
                        "output": {"type": "object"},
                        "limitations": {"type": "array"},
                        "prompt_template": {"type": "string"},
                        "tool_instructions": {"type": "string"},
                    },
                },
            },
            "count": {"type": "integer"},
            "missing": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names that could not be resolved to a contract.",
            },
        },
    },
    actor="back",
    category="read",
    side_effects=False,
)


# ===================================================================
# INVOKE -- execute a known capability by name
# ===================================================================

INVOKE_CAPABILITY_SCHEMA = ToolSchema(
    name="invoke_capability",
    description=(
        "Use one known external capability to project the LLM into the outside world: "
        "read source-of-record app data, create or update records, call integrations, "
        "delegate to an agent, or run a workflow. This is the LLM's read/write/action "
        "bridge, not a chat-only reasoning step. Invoke only with an exact executable "
        "handle copied from discover_capabilities.name or from an allowlisted capability. "
        "Do not pass prompt_template, activity_profile, tool_instructions, domain names, "
        "or a natural-language label as capability_name. Build params from the returned "
        "required_inputs/optional_inputs schema; for read/list capabilities with no "
        "required inputs, pass an empty params object rather than asking the user for "
        "internal details. If required inputs are missing, this tool returns a structured "
        "needs_human recovery contract instead of invoking the side effect. Available at "
        "all tiers. For family-tool person fields such as assigned_to, assignee, "
        "recipient, requested_by, attendees, member_filter, or visible_to, pass the "
        "display name or lowercase slug from the user's request, e.g. Riley -> riley; "
        "never ask the user for member IDs. For invoking MULTIPLE independent capabilities, prefer "
        "batch_invoke_capabilities to save budget."
    ),
    parameters={
        "type": "object",
        "properties": {
            "capability_name": {
                "type": "string",
                "description": (
                    "Exact executable handle, copied verbatim from discover_capabilities.name "
                    "or a static allowlist entry, e.g. tool.read.calendar.list_events, "
                    "tool.execute.tasks.create_task, agent.researcher, or workflow.morning_briefing."
                ),
            },
            "params": {
                "type": "object",
                "description": (
                    "Parameters for the external capability, matching its discovered input "
                    "schema. Use {} for read/list capabilities that have no required inputs. "
                    "For family member references, use display names or lowercase slugs "
                    "from context, not internal member IDs. Never invent internal fields "
                    "that were not requested by the schema."
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
                "enum": ["success", "partial", "error", "needs_human"],
            },
            "recovery": {"type": "object"},
        },
    },
    actor="both",
    category="action",
    side_effects=True,
)


__all__ = [
    "DISCOVER_CAPABILITIES_SCHEMA",
    "GET_CAPABILITY_SCHEMAS_SCHEMA",
    "INVOKE_CAPABILITY_SCHEMA",
]
