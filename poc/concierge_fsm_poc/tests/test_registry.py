"""Tests for Epic 2.6 Tool Registry: REG-001.

Test classes:
    TestREG001BasicOps               -- register, get, contains, len, not-found
    TestREG001DefaultRegistry        -- build_default_registry wires all 15 tools
    TestREG001TierFiltering          -- LOW=10, MEDIUM=15, tier filtering
    TestREG001LLMDeclarations        -- get_llm_declarations shape and tier filtering
    TestREG001Categories             -- category breakdown (signal, cognitive, read, action, meta)
    TestREG001HandlerCallable        -- every handler is callable
    TestREG001SchemaQuality          -- every schema has name, description (>20 chars), parameters
"""

from __future__ import annotations

import pytest

from k1.sessionstate import SessionStateFactory
from poc.concierge_fsm_poc.tools.cognitive import CognitiveToolSet
from poc.concierge_fsm_poc.tools.registry import (
    ToolDefinition,
    ToolNotFoundError,
    ToolRegistry,
    build_default_registry,
)

# ---------------------------------------------------------------------------
# Expected tool configuration
# ---------------------------------------------------------------------------

ALL_TOOL_NAMES = sorted(
    [
        "update_scoreboard",
        "update_beliefs",
        "update_clarifications",
        "update_narrative",
        "refine_affect",
        "promote_belief",
        "recall_memory",
        "discover_capabilities",
        "summarize_context",
        "read_session_state",
        "invoke_capability",
        "spawn_via_fabric",
        "execute_workflow",
        "get_capability_schema",
    ]
)

LOW_TOOL_NAMES = sorted(
    [
        "update_scoreboard",
        "update_beliefs",
        "update_clarifications",
        "update_narrative",
        "refine_affect",
        "recall_memory",
        "summarize_context",
        "read_session_state",
        "invoke_capability",
    ]
)

MEDIUM_ONLY_NAMES = sorted(
    [
        "promote_belief",
        "discover_capabilities",
        "spawn_via_fabric",
        "execute_workflow",
        "get_capability_schema",
    ]
)

CATEGORY_COUNTS = {
    "signal": 0,
    "cognitive": 6,
    "read": 4,
    "action": 3,
    "meta": 1,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager():
    m = SessionStateFactory.create_for_testing()
    m.start()
    yield m
    m.stop()


@pytest.fixture()
def registry(manager):
    cognitive = CognitiveToolSet(manager)
    return build_default_registry(cognitive, manager)


@pytest.fixture()
def empty_registry():
    return ToolRegistry()


# ===========================================================================
# TestREG001BasicOps
# ===========================================================================


class TestREG001BasicOps:
    """Basic registry operations: register, get, contains, len, not-found."""

    def test_empty_registry_len(self, empty_registry):
        assert len(empty_registry) == 0

    def test_register_increases_len(self, empty_registry):
        td = ToolDefinition(
            name="test_tool",
            category="signal",
            handler=lambda: None,
            schema={
                "name": "test_tool",
                "description": "test",
                "parameters": {"type": "object", "properties": {}},
            },
        )
        empty_registry.register(td)
        assert len(empty_registry) == 1

    def test_contains_after_register(self, empty_registry):
        td = ToolDefinition(
            name="test_tool",
            category="signal",
            handler=lambda: None,
            schema={
                "name": "test_tool",
                "description": "test",
                "parameters": {"type": "object", "properties": {}},
            },
        )
        empty_registry.register(td)
        assert "test_tool" in empty_registry

    def test_contains_returns_false_for_missing(self, empty_registry):
        assert "nonexistent" not in empty_registry

    def test_get_returns_tool_definition(self, empty_registry):
        td = ToolDefinition(
            name="test_tool",
            category="signal",
            handler=lambda: None,
            schema={
                "name": "test_tool",
                "description": "test",
                "parameters": {"type": "object", "properties": {}},
            },
        )
        empty_registry.register(td)
        result = empty_registry.get("test_tool")
        assert result.name == "test_tool"
        assert result.category == "signal"

    def test_get_raises_tool_not_found_error(self, empty_registry):
        with pytest.raises(ToolNotFoundError) as exc_info:
            empty_registry.get("nonexistent")
        assert exc_info.value.name == "nonexistent"

    def test_tool_not_found_error_has_available_list(self, empty_registry):
        td = ToolDefinition(
            name="existing_tool",
            category="signal",
            handler=lambda: None,
            schema={
                "name": "existing_tool",
                "description": "test",
                "parameters": {"type": "object", "properties": {}},
            },
        )
        empty_registry.register(td)
        with pytest.raises(ToolNotFoundError) as exc_info:
            empty_registry.get("missing")
        assert "existing_tool" in exc_info.value.available

    def test_register_replaces_existing(self, empty_registry):
        td1 = ToolDefinition(
            name="tool",
            category="signal",
            handler=lambda: "v1",
            schema={
                "name": "tool",
                "description": "v1",
                "parameters": {"type": "object", "properties": {}},
            },
        )
        td2 = ToolDefinition(
            name="tool",
            category="cognitive",
            handler=lambda: "v2",
            schema={
                "name": "tool",
                "description": "v2",
                "parameters": {"type": "object", "properties": {}},
            },
        )
        empty_registry.register(td1)
        empty_registry.register(td2)
        assert len(empty_registry) == 1
        assert empty_registry.get("tool").category == "cognitive"

    def test_all_tool_names_sorted(self, empty_registry):
        for name in ["z_tool", "a_tool", "m_tool"]:
            td = ToolDefinition(
                name=name,
                category="signal",
                handler=lambda: None,
                schema={
                    "name": name,
                    "description": "test",
                    "parameters": {"type": "object", "properties": {}},
                },
            )
            empty_registry.register(td)
        assert empty_registry.all_tool_names == ["a_tool", "m_tool", "z_tool"]


# ===========================================================================
# TestREG001DefaultRegistry
# ===========================================================================


class TestREG001DefaultRegistry:
    """build_default_registry wires all 14 tools."""

    def test_total_tool_count(self, registry):
        """AC: All 14 tools registered (acknowledge hidden)."""
        assert len(registry) == 14

    def test_all_tool_names_present(self, registry):
        assert registry.all_tool_names == ALL_TOOL_NAMES

    @pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
    def test_each_tool_present(self, registry, tool_name: str):
        assert tool_name in registry

    @pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
    def test_each_tool_has_schema(self, registry, tool_name: str):
        td = registry.get(tool_name)
        assert "name" in td.schema
        assert td.schema["name"] == tool_name


# ===========================================================================
# TestREG001TierFiltering
# ===========================================================================


class TestREG001TierFiltering:
    """AC: get_for_tier('LOW') returns 9, get_for_tier('MEDIUM') returns 14."""

    def test_low_tier_count(self, registry):
        low_tools = registry.get_for_tier("LOW")
        assert len(low_tools) == 9

    def test_low_tier_names(self, registry):
        low_names = sorted(td.name for td in registry.get_for_tier("LOW"))
        assert low_names == LOW_TOOL_NAMES

    def test_medium_tier_count(self, registry):
        med_tools = registry.get_for_tier("MEDIUM")
        assert len(med_tools) == 14

    def test_medium_tier_includes_all(self, registry):
        med_names = sorted(td.name for td in registry.get_for_tier("MEDIUM"))
        assert med_names == ALL_TOOL_NAMES

    def test_medium_only_tools_not_in_low(self, registry):
        low_names = {td.name for td in registry.get_for_tier("LOW")}
        for name in MEDIUM_ONLY_NAMES:
            assert name not in low_names, f"{name} should not be in LOW tier"

    @pytest.mark.parametrize("tool_name", MEDIUM_ONLY_NAMES)
    def test_medium_only_tool_excluded_from_low(self, registry, tool_name: str):
        td = registry.get(tool_name)
        assert "LOW" not in td.tiers

    @pytest.mark.parametrize("tool_name", LOW_TOOL_NAMES)
    def test_low_tool_available_in_both_tiers(self, registry, tool_name: str):
        td = registry.get(tool_name)
        assert "LOW" in td.tiers
        assert "MEDIUM" in td.tiers

    def test_tier_filtering_case_insensitive(self, registry):
        """Tier string is uppercased internally."""
        low_tools = registry.get_for_tier("low")
        assert len(low_tools) == 9

    def test_unknown_tier_returns_empty(self, registry):
        """No tools match a tier that doesn't exist."""
        result = registry.get_for_tier("HIGH")
        assert len(result) == 0

    def test_get_for_tier_returns_sorted(self, registry):
        low_tools = registry.get_for_tier("LOW")
        names = [td.name for td in low_tools]
        assert names == sorted(names)


# ===========================================================================
# TestREG001LLMDeclarations
# ===========================================================================


class TestREG001LLMDeclarations:
    """AC: get_llm_declarations returns Gemini-compatible function declarations."""

    def test_low_declarations_count(self, registry):
        decls = registry.get_llm_declarations("LOW")
        assert len(decls) == 9

    def test_medium_declarations_count(self, registry):
        decls = registry.get_llm_declarations("MEDIUM")
        assert len(decls) == 14

    def test_declarations_are_dicts(self, registry):
        decls = registry.get_llm_declarations("MEDIUM")
        for d in decls:
            assert isinstance(d, dict)

    def test_each_declaration_has_name(self, registry):
        """Gemini requires 'name' field."""
        for d in registry.get_llm_declarations("MEDIUM"):
            assert "name" in d, f"Declaration missing 'name': {d}"

    def test_each_declaration_has_description(self, registry):
        """Gemini requires 'description' field."""
        for d in registry.get_llm_declarations("MEDIUM"):
            assert "description" in d, f"{d['name']} missing 'description'"

    def test_each_declaration_has_parameters(self, registry):
        """Gemini requires 'parameters' field with type=object."""
        for d in registry.get_llm_declarations("MEDIUM"):
            assert "parameters" in d, f"{d['name']} missing 'parameters'"
            assert d["parameters"]["type"] == "object", f"{d['name']} parameters not object"

    def test_low_declarations_exclude_medium_only(self, registry):
        """LOW declarations must not include MEDIUM-only tools."""
        low_decl_names = {d["name"] for d in registry.get_llm_declarations("LOW")}
        for name in MEDIUM_ONLY_NAMES:
            assert name not in low_decl_names, f"{name} leaked into LOW declarations"

    def test_declaration_names_match_tool_names(self, registry):
        """Schema name must match the ToolDefinition name."""
        for td_name in ALL_TOOL_NAMES:
            td = registry.get(td_name)
            assert td.schema["name"] == td_name


# ===========================================================================
# TestREG001Categories
# ===========================================================================


class TestREG001Categories:
    """Category breakdown: signal=0, cognitive=6, read=4, action=3, meta=1."""

    @pytest.mark.parametrize("category,expected_count", list(CATEGORY_COUNTS.items()))
    def test_category_count(self, registry, category: str, expected_count: int):
        tools = registry.get_by_category(category)
        assert len(tools) == expected_count, (
            f"Category '{category}' expected {expected_count} tools, "
            f"got {len(tools)}: {[t.name for t in tools]}"
        )

    def test_signal_category_empty(self, registry):
        tools = registry.get_by_category("signal")
        assert len(tools) == 0

    def test_meta_is_get_capability_schema(self, registry):
        tools = registry.get_by_category("meta")
        assert tools[0].name == "get_capability_schema"

    def test_cognitive_tools(self, registry):
        names = sorted(t.name for t in registry.get_by_category("cognitive"))
        assert names == sorted(
            [
                "update_scoreboard",
                "update_beliefs",
                "update_clarifications",
                "update_narrative",
                "refine_affect",
                "promote_belief",
            ]
        )

    def test_read_tools(self, registry):
        names = sorted(t.name for t in registry.get_by_category("read"))
        assert names == sorted(
            [
                "recall_memory",
                "discover_capabilities",
                "summarize_context",
                "read_session_state",
            ]
        )

    def test_action_tools(self, registry):
        names = sorted(t.name for t in registry.get_by_category("action"))
        assert names == sorted(
            [
                "invoke_capability",
                "spawn_via_fabric",
                "execute_workflow",
            ]
        )

    def test_get_by_category_returns_sorted(self, registry):
        for cat in CATEGORY_COUNTS:
            tools = registry.get_by_category(cat)
            names = [t.name for t in tools]
            assert names == sorted(names), f"Category '{cat}' not sorted"

    def test_all_categories_sum_to_total(self, registry):
        total = sum(len(registry.get_by_category(c)) for c in CATEGORY_COUNTS)
        assert total == 14


# ===========================================================================
# TestREG001HandlerCallable
# ===========================================================================


class TestREG001HandlerCallable:
    """Every registered handler must be callable."""

    @pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
    def test_handler_is_callable(self, registry, tool_name: str):
        td = registry.get(tool_name)
        assert callable(td.handler), f"{tool_name} handler is not callable"


# ===========================================================================
# TestREG001SchemaQuality
# ===========================================================================


class TestREG001SchemaQuality:
    """Schema descriptions must be rich enough for reliable function calling."""

    @pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
    def test_description_is_meaningful(self, registry, tool_name: str):
        """Description must be >20 chars to be useful for the model."""
        td = registry.get(tool_name)
        desc = td.schema.get("description", "")
        assert len(desc) > 20, f"{tool_name} description too short ({len(desc)} chars): '{desc}'"

    @pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
    def test_parameters_has_properties(self, registry, tool_name: str):
        """Gemini needs 'properties' inside 'parameters'."""
        td = registry.get(tool_name)
        params = td.schema.get("parameters", {})
        assert "properties" in params, f"{tool_name} parameters missing 'properties'"

    def test_update_beliefs_description_mentions_beliefs(self, registry):
        td = registry.get("update_beliefs")
        desc = td.schema["description"].lower()
        assert "belief" in desc

    def test_invoke_capability_description_mentions_execute(self, registry):
        td = registry.get("invoke_capability")
        desc = td.schema["description"].lower()
        assert "execute" in desc or "invoke" in desc or "call" in desc

    def test_recall_memory_description_mentions_memory(self, registry):
        td = registry.get("recall_memory")
        desc = td.schema["description"].lower()
        assert "memory" in desc

    def test_get_capability_schema_mentions_schema(self, registry):
        td = registry.get("get_capability_schema")
        desc = td.schema["description"].lower()
        assert "schema" in desc

    def test_read_session_state_mentions_session_state(self, registry):
        td = registry.get("read_session_state")
        desc = td.schema["description"].lower()
        assert "session" in desc or "state" in desc

    def test_discover_capabilities_mentions_discover(self, registry):
        td = registry.get("discover_capabilities")
        desc = td.schema["description"].lower()
        assert "discover" in desc or "list" in desc or "available" in desc
