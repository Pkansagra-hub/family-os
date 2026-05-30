"""M4.I7: Front tool allowlist cutover for cognitive deloading."""

from __future__ import annotations

from k1.concierge.config import load_config, reset_config
from k1.concierge.prompt.affect import AffectBand
from k1.concierge.prompt.builder import DynamicPromptBuilder
from k1.concierge.prompt.mode import (
    COGNITIVE_WRITE_TOOL_NAMES,
    PromptMode,
    get_tool_allowlist,
)
from k1.concierge.tools.schemas_front import FRONT_TOOL_SCHEMAS

READ_ACTION_TOOLS = {
    "recall_memory",
    "summarize_context",
    "dispatch_task",
    "discover_capabilities",
    "invoke_capability",
}


def _tool_names(tools: list[object]) -> set[str]:
    return {str(getattr(tool, "name")) for tool in tools}


def test_default_front_allowlists_hide_cognitive_write_tools() -> None:
    reset_config()
    try:
        for mode in PromptMode:
            names = set(get_tool_allowlist(mode, affect_confidence=0.0, tier="HIGH"))
            assert not names & COGNITIVE_WRITE_TOOL_NAMES, mode

        assert set(get_tool_allowlist(PromptMode.STANDARD)) == READ_ACTION_TOOLS
        assert set(get_tool_allowlist(PromptMode.INTERRUPT)) == READ_ACTION_TOOLS
        assert set(get_tool_allowlist(PromptMode.CLARIFY_ASK)) == {"recall_memory"}
        assert set(get_tool_allowlist(PromptMode.CLARIFY_RESOLVE)) == {
            "recall_memory",
            "dispatch_task",
        }
        assert get_tool_allowlist(PromptMode.HITL_RELAY) == []
    finally:
        reset_config()


def test_builder_filters_registered_cognitive_schemas_from_front_tools() -> None:
    schema_names = _tool_names(FRONT_TOOL_SCHEMAS)
    assert COGNITIVE_WRITE_TOOL_NAMES <= schema_names

    reset_config()
    try:
        for mode in PromptMode:
            built = DynamicPromptBuilder().build(
                mode=mode,
                affect_band=AffectBand("neutral"),
                history_messages=[],
                all_tool_schemas=FRONT_TOOL_SCHEMAS,
                affect_confidence=0.0,
                tier="HIGH",
            )
            names = _tool_names(built.tools)
            assert not names & COGNITIVE_WRITE_TOOL_NAMES, mode
    finally:
        reset_config()


def test_legacy_allowlist_can_be_restored_by_config(tmp_path) -> None:
    override = tmp_path / "config.yaml"
    override.write_text(
        "prompt:\n" "  front_deload_cognitive_tools: false\n",
        encoding="utf-8",
    )
    load_config(override)
    try:
        standard = set(get_tool_allowlist(PromptMode.STANDARD, affect_confidence=0.0, tier="HIGH"))
        interrupt = set(
            get_tool_allowlist(PromptMode.INTERRUPT, affect_confidence=0.0, tier="HIGH")
        )

        assert {
            "update_beliefs",
            "update_scoreboard",
            "update_clarifications",
            "update_narrative",
            "refine_affect",
            "promote_belief",
        } <= standard
        assert {
            "update_beliefs",
            "update_scoreboard",
            "update_clarifications",
            "update_narrative",
            "refine_affect",
            "promote_belief",
        } <= interrupt
    finally:
        reset_config()
