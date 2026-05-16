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
        "Query the K0 capability registry to find services, agents, or workflows "
        "that can handle a given intent. Returns ranked matches with confidence "
        "scores plus each capability's required and optional input schema. Call "
        "BEFORE invoke_capability or spawn_via_fabric to find available options "
        "and verify required inputs. Available in ALL tiers."
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
                        "domain": {"type": "string"},
                        "score": {"type": "number"},
                        "schema": {
                            "type": "object",
                            "properties": {
                                "required_inputs": {"type": "array"},
                                "optional_inputs": {"type": "array"},
                                "safety_band_min": {"type": "string"},
                            },
                        },
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


# ===================================================================
# INVOKE -- execute a known capability by name
# ===================================================================

INVOKE_CAPABILITY_SCHEMA = ToolSchema(
    name="invoke_capability",
    description=(
        "Invoke a known K0 capability by name with parameters. "
        "Use after discover_capabilities identifies the right service, "
        "or when you already know the capability name and its input schema from prior tasks. "
        "If required inputs are missing, this tool returns a structured needs_human "
        "recovery contract instead of invoking the side effect. "
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
                    "(e.g. {'destination': 'Napa', "
                    "'dates': {'start': '2025-06-15', 'end': '2025-06-17'}})"
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


__all__ = ["DISCOVER_CAPABILITIES_SCHEMA", "INVOKE_CAPABILITY_SCHEMA"]
