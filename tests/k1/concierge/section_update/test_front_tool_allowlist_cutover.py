"""M4.I7: Front tool allowlist cutover for cognitive deloading (Post-Tier-2).

After Tier 2 cleanup, cognitive write tools are removed from schemas,
implementations, LEGACY_TOOL_ALLOWLIST, and COGNITIVE_WRITE_TOOL_NAMES.
The single TOOL_ALLOWLIST is the sole authority. These tests verify the
simplified post-migration state.
"""

from __future__ import annotations

from k1.concierge.config import reset_config
from k1.concierge.prompt.affect import AffectBand
from k1.concierge.prompt.builder import DynamicPromptBuilder
from k1.concierge.prompt.mode import PromptMode, get_tool_allowlist
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


# =========================================================================
# Post-Tier-2: allowlist is the single authority
# =========================================================================


def test_tool_allowlist_is_the_only_authority() -> None:
    """After Tier 2, only TOOL_ALLOWLIST exists — no LEGACY or COGNITIVE_WRITE."""
    from k1.concierge.prompt import mode as mode_mod

    assert hasattr(mode_mod, "TOOL_ALLOWLIST")
    assert not hasattr(mode_mod, "LEGACY_TOOL_ALLOWLIST")
    assert not hasattr(mode_mod, "COGNITIVE_WRITE_TOOL_NAMES")
    assert not hasattr(mode_mod, "_front_deload_cognitive_tools_enabled")


def test_standard_allowlist_matches_expected() -> None:
    """STANDARD mode has exactly the 5 read/control/fabric tools."""
    reset_config()
    try:
        assert set(get_tool_allowlist(PromptMode.STANDARD)) == READ_ACTION_TOOLS
    finally:
        reset_config()


def test_interrupt_allowlist_matches_expected() -> None:
    """INTERRUPT mode has exactly the 5 read/control/fabric tools."""
    reset_config()
    try:
        assert set(get_tool_allowlist(PromptMode.INTERRUPT)) == READ_ACTION_TOOLS
    finally:
        reset_config()


def test_clarify_ask_is_recall_only() -> None:
    """CLARIFY_ASK has only recall_memory."""
    reset_config()
    try:
        assert set(get_tool_allowlist(PromptMode.CLARIFY_ASK)) == {"recall_memory"}
    finally:
        reset_config()


def test_clarify_resolve_is_recall_and_dispatch() -> None:
    """CLARIFY_RESOLVE has recall_memory + dispatch_task."""
    reset_config()
    try:
        assert set(get_tool_allowlist(PromptMode.CLARIFY_RESOLVE)) == {
            "recall_memory",
            "dispatch_task",
        }
    finally:
        reset_config()


def test_hitl_relay_is_empty() -> None:
    """HITL_RELAY is strictly text-only — no tools."""
    reset_config()
    try:
        assert get_tool_allowlist(PromptMode.HITL_RELAY) == []
    finally:
        reset_config()


def test_all_modes_have_no_cognitive_write_tools() -> None:
    """No PromptMode includes any cognitive write tool."""
    cognitive = {
        "update_beliefs",
        "update_scoreboard",
        "update_clarifications",
        "update_narrative",
        "refine_affect",
        "promote_belief",
        "update_session_bundle",
    }
    reset_config()
    try:
        for mode in PromptMode:
            names = set(get_tool_allowlist(mode, affect_confidence=0.0, tier="HIGH"))
            assert not names & cognitive, f"{mode} leaked cognitive tools: {names & cognitive}"
    finally:
        reset_config()


# =========================================================================
# Front tool schemas are now 5 tools only
# =========================================================================


def test_front_tool_schemas_has_five_tools() -> None:
    """FRONT_TOOL_SCHEMAS has exactly 5 tools post-migration."""
    schema_names = _tool_names(FRONT_TOOL_SCHEMAS)
    assert len(FRONT_TOOL_SCHEMAS) == 5
    assert schema_names == READ_ACTION_TOOLS


def test_no_cognitive_schemas_in_front_tools() -> None:
    """No cognitive write schemas remain in FRONT_TOOL_SCHEMAS."""
    schema_names = _tool_names(FRONT_TOOL_SCHEMAS)
    cognitive = {
        "update_beliefs",
        "update_scoreboard",
        "update_clarifications",
        "update_narrative",
        "refine_affect",
        "promote_belief",
        "update_session_bundle",
    }
    assert not schema_names & cognitive


# =========================================================================
# Builder still filters correctly (defense-in-depth)
# =========================================================================


def test_builder_only_exposes_allowed_tools() -> None:
    """DynamicPromptBuilder only exposes tools in the allowlist for each mode."""
    reset_config()
    try:
        for mode in PromptMode:
            allowed = set(get_tool_allowlist(mode, affect_confidence=0.0, tier="HIGH"))
            built = DynamicPromptBuilder().build(
                mode=mode,
                affect_band=AffectBand("neutral"),
                history_messages=[],
                all_tool_schemas=FRONT_TOOL_SCHEMAS,
                affect_confidence=0.0,
                tier="HIGH",
            )
            names = _tool_names(built.tools)
            schema_names = _tool_names(FRONT_TOOL_SCHEMAS)
            # Every exposed tool must be from FRONT_TOOL_SCHEMAS
            assert names <= schema_names, f"{mode}: {names - schema_names}"
            # Only allowed tools appear
            extra = names - allowed
            assert not extra, f"{mode} exposed unauthorized tools: {extra}"
    finally:
        reset_config()


# =========================================================================
# No more legacy rollback
# =========================================================================


def test_front_deload_cognitive_tools_config_has_no_effect() -> None:
    """The front_deload_cognitive_tools config flag no longer exists.
    There is no legacy path to restore — the tools are physically removed."""
    reset_config()
    try:
        # Even without any config, the allowlist is the same
        standard = set(get_tool_allowlist(PromptMode.STANDARD, affect_confidence=0.0, tier="HIGH"))
        assert standard == READ_ACTION_TOOLS
    finally:
        reset_config()
