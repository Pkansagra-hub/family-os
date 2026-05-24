"""Kernel-grade discovery payload slimming for model context.

Discovery returns rich per-capability contracts (full JSON schema,
prompt templates, tool instructions, optional/required input specs,
limitations, diagnostics).  Injecting these verbatim into the model
context inflates a 4-intent fan-out by ~4x and has been observed to
push Vertex/Gemini past the input-budget cliff on the next iteration.

The slim projection keeps the executable identity (`name`) plus the
metadata needed for selection (description, score, side-effect
flags, required-input names), and drops the verbose schema bodies.
Full contracts remain in ``ctx.capability_cache`` server-side for
invoke-time use, so no information is lost -- only echoed-back
context is reduced.

This is a pure representation change.  No English, no domain code.
"""

from __future__ import annotations

from k1.concierge.react.loop import (
    _slim_capability_for_context,
    _slim_discovery_data_for_context,
)


def _fat_capability() -> dict:
    return {
        "name": "tool.read.tasks.list_tasks",
        "type": "tool.read",
        "description": "List family tasks",
        "domain": "tasks",
        "domains": ["tasks", "household"],
        "score": 0.92,
        "has_side_effects": False,
        "requires_human_confirmation": False,
        "provider_type": "adapter",
        "safety_band_min": "GREEN",
        "side_effects": [],
        "required_inputs": {
            "family_id": {"type": "string", "description": "..."},
        },
        "optional_inputs": {
            "limit": {"type": "integer"},
            "status_filter": {"type": "string"},
        },
        "prompt_template": "A very long prompt template " * 50,
        "tool_instructions": "Detailed instructions " * 50,
        "activity_profile": "household_management",
        "limitations": ["only owner can write", "rate-limited"],
        "schema": {
            "type": "object",
            "properties": {"family_id": {"type": "string"}},
            "required": ["family_id"],
        },
        "diagnostics": {"why_matched": "domain hit"},
    }


def test_slim_capability_keeps_executable_identity_and_selection_metadata() -> None:
    slim = _slim_capability_for_context(_fat_capability())

    assert slim["name"] == "tool.read.tasks.list_tasks"
    assert slim["description"] == "List family tasks"
    assert slim["score"] == 0.92
    assert slim["has_side_effects"] is False
    assert slim["requires_human_confirmation"] is False
    assert slim["safety_band_min"] == "GREEN"
    assert slim["domains"] == ["tasks", "household"]


def test_slim_capability_drops_verbose_fields() -> None:
    slim = _slim_capability_for_context(_fat_capability())

    # Verbose schema/template fields must NOT appear in the context.
    for forbidden in (
        "schema",
        "prompt_template",
        "tool_instructions",
        "activity_profile",
        "limitations",
        "diagnostics",
        "required_inputs",  # full spec replaced by names below
        "optional_inputs",
    ):
        assert forbidden not in slim, f"slim payload must not carry {forbidden!r}"


def test_slim_capability_projects_required_input_names_only() -> None:
    slim = _slim_capability_for_context(_fat_capability())

    assert slim["required_input_names"] == ["family_id"]
    assert set(slim["optional_input_names"]) == {"limit", "status_filter"}


def test_slim_discovery_data_projects_each_capability_and_drops_diagnostics() -> None:
    data = {
        "capabilities": [_fat_capability(), _fat_capability()],
        "count": 2,
        "diagnostics": {"queries": [{"domain": "tasks"}]},
    }

    slim = _slim_discovery_data_for_context(data)

    assert slim["count"] == 2
    assert len(slim["capabilities"]) == 2
    assert "diagnostics" not in slim
    # Original input must not be mutated.
    assert "diagnostics" in data
    assert "schema" in data["capabilities"][0]
    # Slim copy must not carry the heavy field.
    assert "schema" not in slim["capabilities"][0]


def test_slim_discovery_passes_through_non_dict_and_non_capability_shapes() -> None:
    # Errors / non-dict payloads pass through unchanged so we can apply
    # the helper unconditionally before tool-result message construction.
    assert _slim_discovery_data_for_context(None) is None
    assert _slim_discovery_data_for_context("error string") == "error string"
    no_caps = {"error": "intent is required"}
    assert _slim_discovery_data_for_context(no_caps) == no_caps
