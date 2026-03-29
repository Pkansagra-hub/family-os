"""
Epic 6.3.8 -- Test sub-agent tool scoping (FAB-07).

Covers:
  - ToolScope enforcement: validate() raises AccessDeniedError for denied tools.
  - ToolScope from AgentContract.tools_granted (YAML fixtures).
  - ToolScope from programmatic AgentContract.
  - is_allowed() non-raising check.
  - ToolScope immutability (frozen set after construction).
  - ToolScopeError for empty tools_granted.
  - Integration: ToolScope built from real fixture contracts.
  - Integration: Agent with granted tools executes allowed capability.
  - Integration: Agent with granted tools is denied ungranted capability.

NO MOCKS -- all tests use real adapters and real ToolScope.

References:
  - fabric-implementation-plan.md Epic 6.3.8
  - fabric_discussion.md Section 10 (Security, tool scoping)
  - FAB-07 (Sub-agent tool scoping enforced via tools_granted[])
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.factory import FabricFactory
from k1.fabric.policy.security_context import AccessDeniedError
from k1.fabric.policy.tool_scope import ToolScope, ToolScopeError
from k1.fabric.types import (
    AgentContract,
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    Tier,
)
from tests.k1.fabric.helpers import (
    load_fixture_contract,
    register_contract_with_provider,
)

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_scope(granted: list[str]) -> ToolScope:
    """Create a ToolScope with specific granted tools."""
    return ToolScope(tools_granted=granted)


def _make_agent_contract(
    name: str = "agent.execute.test_agent",
    tools_granted: list[str] | None = None,
) -> AgentContract:
    """Create a minimal AgentContract with tools_granted."""
    return AgentContract(
        name=name,
        version="1.0.0",
        domain=["TEST"],
        description="Test agent for tool scoping",
        capabilities=[name],
        provider_type="AGENT",
        provider_id="agent-scope-test",
        tools_granted=tools_granted or [],
    )


# =========================================================================
# 6.3.8a -- ToolScope validate() and is_allowed()
# =========================================================================


class TestToolScopeValidation:
    """
    Verify ToolScope.validate() and is_allowed() behavior.
    """

    def test_validate_allows_granted_tool(self) -> None:
        """validate() returns True for a tool in the granted set."""
        scope = _make_tool_scope(
            [
                "tool.execute.restaurant_booking",
                "tool.read.weather_api",
            ]
        )
        assert scope.validate("tool.execute.restaurant_booking") is True
        assert scope.validate("tool.read.weather_api") is True

    def test_validate_rejects_ungranted_tool(self) -> None:
        """validate() raises AccessDeniedError for tool NOT in granted set."""
        scope = _make_tool_scope(["tool.execute.restaurant_booking"])

        with pytest.raises(AccessDeniedError) as exc_info:
            scope.validate("tool.execute.payments")

        assert "tool_scope" in str(exc_info.value)

    def test_validate_rejects_empty_capability_name(self) -> None:
        """validate() raises AccessDeniedError for empty capability_name."""
        scope = _make_tool_scope(["tool.execute.restaurant_booking"])

        with pytest.raises(AccessDeniedError):
            scope.validate("")

    def test_is_allowed_returns_true_for_granted(self) -> None:
        """is_allowed() returns True for granted tools (non-raising)."""
        scope = _make_tool_scope(
            [
                "tool.execute.restaurant_booking",
                "tool.read.weather_api",
            ]
        )
        assert scope.is_allowed("tool.execute.restaurant_booking") is True
        assert scope.is_allowed("tool.read.weather_api") is True

    def test_is_allowed_returns_false_for_ungranted(self) -> None:
        """is_allowed() returns False for ungranted tools (non-raising)."""
        scope = _make_tool_scope(["tool.execute.restaurant_booking"])
        assert scope.is_allowed("tool.execute.payments") is False
        assert scope.is_allowed("tool.execute.banking") is False

    def test_is_allowed_returns_false_for_empty(self) -> None:
        """is_allowed() returns False for empty capability_name."""
        scope = _make_tool_scope(["tool.execute.restaurant_booking"])
        assert scope.is_allowed("") is False

    def test_multiple_tools_all_checked(self) -> None:
        """ToolScope with multiple tools checks each individually."""
        tools = [
            "tool.execute.restaurant_booking",
            "tool.read.weather_api",
            "tool.execute.send_message",
        ]
        scope = _make_tool_scope(tools)

        for tool in tools:
            assert scope.is_allowed(tool) is True

        assert scope.is_allowed("tool.execute.unknown") is False


# =========================================================================
# 6.3.8b -- ToolScope construction and properties
# =========================================================================


class TestToolScopeConstruction:
    """
    Verify ToolScope construction, immutability, and properties.
    """

    def test_tools_granted_is_frozenset(self) -> None:
        """tools_granted property returns a frozenset."""
        scope = _make_tool_scope(["tool.a", "tool.b"])
        assert isinstance(scope.tools_granted, frozenset)

    def test_duplicate_tools_deduplicated(self) -> None:
        """Duplicate tools in constructor are deduplicated."""
        scope = _make_tool_scope(["tool.a", "tool.a", "tool.b"])
        assert len(scope.tools_granted) == 2

    def test_empty_tools_raises_error(self) -> None:
        """Empty tools_granted raises ToolScopeError."""
        with pytest.raises(ToolScopeError):
            _make_tool_scope([])

    def test_repr_includes_tools(self) -> None:
        """__repr__ includes the sorted tool names."""
        scope = _make_tool_scope(["tool.b", "tool.a"])
        r = repr(scope)
        assert "tool.a" in r
        assert "tool.b" in r

    def test_tools_granted_immutable(self) -> None:
        """tools_granted frozenset cannot be mutated."""
        scope = _make_tool_scope(["tool.a"])
        # frozenset has no add/remove methods
        assert not hasattr(scope.tools_granted, "add")
        assert not hasattr(scope.tools_granted, "remove")


# =========================================================================
# 6.3.8c -- ToolScope from AgentContract
# =========================================================================


class TestToolScopeFromContract:
    """
    Build ToolScope from AgentContract.tools_granted field.
    """

    def test_scope_from_programmatic_agent_contract(self) -> None:
        """ToolScope built from programmatic AgentContract."""
        contract = _make_agent_contract(
            tools_granted=[
                "tool.execute.restaurant_booking",
                "tool.read.weather_api",
            ],
        )
        scope = ToolScope(tools_granted=contract.tools_granted)

        assert scope.is_allowed("tool.execute.restaurant_booking") is True
        assert scope.is_allowed("tool.read.weather_api") is True
        assert scope.is_allowed("tool.execute.banking") is False

    def test_scope_from_invitation_sender_fixture(self) -> None:
        """ToolScope built from invitation_sender YAML fixture."""
        parsed = load_fixture_contract("invitation_sender")
        tools = getattr(parsed, "tools_granted", [])
        assert len(tools) > 0, "invitation_sender should have tools_granted"

        scope = ToolScope(tools_granted=tools)
        assert scope.is_allowed("tool.execute.restaurant_booking") is True
        assert scope.is_allowed("tool.read.weather_api") is True
        assert scope.is_allowed("tool.execute.payments") is False

    def test_scope_rejects_tools_not_in_contract(self) -> None:
        """ToolScope enforces contract boundary on denied tools."""
        contract = _make_agent_contract(
            tools_granted=["tool.execute.send_message"],
        )
        scope = ToolScope(tools_granted=contract.tools_granted)

        # Allowed
        assert scope.validate("tool.execute.send_message") is True

        # Denied
        with pytest.raises(AccessDeniedError):
            scope.validate("tool.execute.restaurant_booking")

    def test_scope_validates_all_granted_tools(self) -> None:
        """All tools in contract.tools_granted pass validation."""
        tools = [
            "tool.execute.restaurant_booking",
            "tool.read.weather_api",
            "tool.execute.send_message",
            "tool.execute.calendar",
        ]
        contract = _make_agent_contract(tools_granted=tools)
        scope = ToolScope(tools_granted=contract.tools_granted)

        for tool in tools:
            assert scope.validate(tool) is True


# =========================================================================
# 6.3.8d -- ToolScope integration via fabric (FAB-07)
# =========================================================================


class TestToolScopeFabricIntegration:
    """
    Integration: verify tool scoping works with real Fabric setup.
    Agent has tools_granted, and ToolScope enforces the boundary.
    """

    async def test_granted_tool_executes_successfully(self) -> None:
        """Agent with granted tool can execute that tool via fabric."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        # Register the tool capability that the agent is granted
        tool_contract = CapabilityContract(
            name="tool.execute.scoped_tool",
            version="1.0.0",
            domain=["TEST"],
            description="Tool for scoping test",
            capabilities=["tool.execute.scoped_tool"],
            provider_type="MCP",
            provider_id="mcp-scoped",
            required_inputs=[
                InputSpec(name="query", type="STRING", description="Test query input")
            ],
            output={"type": "object"},
        )
        register_contract_with_provider(fabric, tool_contract)

        # Build ToolScope with this tool granted
        scope = ToolScope(tools_granted=["tool.execute.scoped_tool"])
        assert scope.validate("tool.execute.scoped_tool") is True

        # Execute through fabric (default TestMCPTransport returns success)
        request = CapabilityRequest(
            capability_name="tool.execute.scoped_tool",
            params={"query": "test"},
            tier=Tier.LOW.value,
            caller="test-scope",
        )
        result = await fabric.execute(request)
        assert result.success is True

    async def test_ungranted_tool_denied_by_scope(self) -> None:
        """Agent is denied access to tools not in tools_granted."""
        # Agent has only restaurant_booking granted
        scope = ToolScope(tools_granted=["tool.execute.restaurant_booking"])

        # Attempting to invoke weather_api should be denied
        with pytest.raises(AccessDeniedError):
            scope.validate("tool.read.weather_api")

        # Verify is_allowed also returns False
        assert scope.is_allowed("tool.read.weather_api") is False

    async def test_scope_enforced_before_execution(self) -> None:
        """
        ToolScope check happens before provider execution.
        Validate, then execute -- scope blocks the denied tool.
        """
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        granted = ["tool.execute.restaurant_booking"]
        scope = ToolScope(tools_granted=granted)

        # Simulating agent workflow: check scope before calling fabric.execute
        target = "tool.execute.restaurant_booking"
        assert scope.validate(target) is True

        # Default TestMCPTransport returns success for any tool
        request = CapabilityRequest(
            capability_name=target,
            params={"restaurant_name": "Chez Scope"},
            tier=Tier.LOW.value,
            caller="test-scope-agent",
        )
        result = await fabric.execute(request)
        assert result.success is True

        # Now try an ungranted tool -- scope blocks it
        with pytest.raises(AccessDeniedError):
            scope.validate("tool.execute.banking")

    async def test_multiple_agents_different_scopes(self) -> None:
        """
        Two agents with different tool scopes:
        each can only access their granted tools.
        """
        agent_a_scope = ToolScope(
            tools_granted=["tool.execute.restaurant_booking"],
        )
        agent_b_scope = ToolScope(
            tools_granted=["tool.read.weather_api"],
        )

        # Agent A can access restaurant but not weather
        assert agent_a_scope.is_allowed("tool.execute.restaurant_booking") is True
        assert agent_a_scope.is_allowed("tool.read.weather_api") is False

        # Agent B can access weather but not restaurant
        assert agent_b_scope.is_allowed("tool.read.weather_api") is True
        assert agent_b_scope.is_allowed("tool.execute.restaurant_booking") is False


# =========================================================================
# 6.3.8e -- AccessDeniedError details
# =========================================================================


class TestAccessDeniedError:
    """
    Verify AccessDeniedError includes proper check/detail fields.
    """

    def test_error_includes_check_field(self) -> None:
        """AccessDeniedError has check='tool_scope'."""
        scope = _make_tool_scope(["tool.a"])
        try:
            scope.validate("tool.b")
            pytest.fail("Expected AccessDeniedError")
        except AccessDeniedError as e:
            assert e.check == "tool_scope"

    def test_error_includes_detail(self) -> None:
        """AccessDeniedError detail mentions the denied capability."""
        scope = _make_tool_scope(["tool.a"])
        try:
            scope.validate("tool.execute.forbidden")
            pytest.fail("Expected AccessDeniedError")
        except AccessDeniedError as e:
            assert "tool.execute.forbidden" in e.detail
            assert "not in tools_granted" in e.detail

    def test_error_for_empty_capability(self) -> None:
        """AccessDeniedError for empty capability_name."""
        scope = _make_tool_scope(["tool.a"])
        try:
            scope.validate("")
            pytest.fail("Expected AccessDeniedError")
        except AccessDeniedError as e:
            assert e.check == "tool_scope"
            assert "empty" in e.detail.lower()
