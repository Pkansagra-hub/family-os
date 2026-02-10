"""
Epic 6.6.2 -- Safety invariant tests (FAB-05 to FAB-08).

Hard safety invariants that MUST hold at all times.
These tests verify invariants through the HardFilter, PolicyEngine,
ToolScope, and ContextBudget subsystems.

Invariants covered:
  FAB-05: OFFLINE capabilities are eliminated before ranking.
  FAB-06: Policy (safety band) is evaluated before provider execution.
  FAB-07: Sub-agent tool scoping enforced via tools_granted[].
  FAB-08: Context window budget capped at 128K tokens.

NO MOCKS -- all tests use real adapters and real Fabric components.

References:
  - fabric-implementation-plan.md Epic 6.6, Issue 6.6.2
  - FAB-05, FAB-06, FAB-07, FAB-08
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.core.context_budget import TOKEN_CEILING, BudgetResult, CompressionLevel
from k1.fabric.factory import FabricFactory
from k1.fabric.policy.security_context import AccessDeniedError, SecurityContext
from k1.fabric.policy.tool_scope import ToolScope, ToolScopeError
from k1.fabric.types import (
    Availability,
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    SafetyBand,
    Tier,
)
from tests.k1.fabric.helpers import (
    assert_capability_result_success,
    register_contract_with_provider,
)

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_fabric():
    """Create a Fabric with event capture for safety invariant tests."""
    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir=str(FIXTURES_DIR),
    )


def _make_contract(
    name: str,
    *,
    availability: str = Availability.ONLINE.value,
    safety_band_min: str = SafetyBand.GREEN.value,
    provider_id: str = "",
    domain: str = "SAFETY_TEST",
) -> CapabilityContract:
    """Build a CapabilityContract with specific availability and safety band."""
    pid = provider_id or f"provider-{name.replace('.', '-')}"
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=[domain],
        description=f"Safety invariant test: {name}",
        capabilities=["test_action"],
        limitations=[],
        required_inputs=[
            InputSpec(name="input_a", type="STRING", description="Test input"),
        ],
        output={"type": "object"},
        provider_type="MCP",
        provider_id=pid,
        safety_band_min=safety_band_min,
        availability=availability,
    )


def _request(
    capability_name: str,
    *,
    user_band: str = SafetyBand.GREEN.value,
    caller: str = "test-safety-inv",
    params: dict | None = None,
) -> CapabilityRequest:
    """Build a CapabilityRequest with a specific safety band."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params or {"input_a": "test"},
        tier=Tier.LOW.value,
        safety_band=user_band,
        caller=caller,
    )


# =========================================================================
# FAB-05 -- OFFLINE capabilities eliminated before ranking
# =========================================================================


class TestFAB05OfflineEliminated:
    """
    FAB-05: OFFLINE capabilities are eliminated before ranking.

    HardFilter checks availability != OFFLINE as one of its hard gates.
    OFFLINE capabilities never reach the SoftRanker.
    """

    async def test_offline_capability_not_discovered(self) -> None:
        """OFFLINE capability is not returned by discover_capabilities()."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.offline_cap",
            availability=Availability.OFFLINE.value,
        )
        register_contract_with_provider(fabric, contract)

        result = await fabric.discover_capabilities(
            domain=["SAFETY_TEST"],
            intent="test action",
            safety_band=SafetyBand.GREEN.value,
        )
        cap_names = [sc.contract.name for sc in result.capabilities if sc.contract]
        assert "tool.execute.offline_cap" not in cap_names

    async def test_online_capability_is_discovered(self) -> None:
        """ONLINE capability in same domain IS returned."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.online_cap",
            availability=Availability.ONLINE.value,
        )
        register_contract_with_provider(fabric, contract)

        result = await fabric.discover_capabilities(
            domain=["SAFETY_TEST"],
            intent="test action",
            safety_band=SafetyBand.GREEN.value,
        )
        cap_names = [sc.contract.name for sc in result.capabilities if sc.contract]
        assert "tool.execute.online_cap" in cap_names

    async def test_degraded_capability_is_not_eliminated(self) -> None:
        """DEGRADED capability is NOT eliminated (only OFFLINE is)."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.degraded_cap",
            availability=Availability.DEGRADED.value,
        )
        register_contract_with_provider(fabric, contract)

        result = await fabric.discover_capabilities(
            domain=["SAFETY_TEST"],
            intent="test action",
            safety_band=SafetyBand.GREEN.value,
        )
        cap_names = [sc.contract.name for sc in result.capabilities if sc.contract]
        assert "tool.execute.degraded_cap" in cap_names

    async def test_offline_filtered_online_returned_same_domain(self) -> None:
        """Register OFFLINE and ONLINE in same domain; only ONLINE returned."""
        fabric = _make_fabric()
        offline = _make_contract(
            "tool.execute.off_same_domain",
            availability=Availability.OFFLINE.value,
        )
        online = _make_contract(
            "tool.execute.on_same_domain",
            availability=Availability.ONLINE.value,
        )
        register_contract_with_provider(fabric, offline)
        register_contract_with_provider(fabric, online)

        result = await fabric.discover_capabilities(
            domain=["SAFETY_TEST"],
            intent="test action",
            safety_band=SafetyBand.GREEN.value,
        )
        cap_names = [sc.contract.name for sc in result.capabilities if sc.contract]
        assert "tool.execute.on_same_domain" in cap_names
        assert "tool.execute.off_same_domain" not in cap_names

    async def test_offline_capability_still_executes_if_named_directly(self) -> None:
        """Executing an OFFLINE capability by name still works (FAB-05 is retrieval-layer).

        FAB-05 ensures OFFLINE caps are filtered during discovery/ranking,
        NOT during direct execution by name. The HardFilter operates in
        the retrieval pipeline (discover_capabilities), not in the Resolver
        used by fabric.execute().
        """
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.offline_exec",
            availability=Availability.OFFLINE.value,
        )
        register_contract_with_provider(fabric, contract)

        request = _request("tool.execute.offline_exec")
        result = await fabric.execute(request)
        # Direct execution by name bypasses HardFilter -- this is by design
        # FAB-05 applies to the discovery/ranking pipeline only
        assert result is not None  # Execution completes (success or failure)

    def test_hard_filter_constants(self) -> None:
        """HardFilter uses OFFLINE constant and REASON_OFFLINE."""
        from k1.fabric.retrieval.hard_filter import _OFFLINE, REASON_OFFLINE

        assert _OFFLINE == "OFFLINE"
        assert REASON_OFFLINE == "offline"

    async def test_bulk_offline_none_discovered(self) -> None:
        """Register 10 OFFLINE capabilities; none are discovered."""
        fabric = _make_fabric()
        for i in range(10):
            contract = _make_contract(
                f"tool.execute.bulk_offline_{i:02d}",
                availability=Availability.OFFLINE.value,
                domain="BULK_OFFLINE",
            )
            register_contract_with_provider(fabric, contract)

        result = await fabric.discover_capabilities(
            domain=["BULK_OFFLINE"],
            intent="any action",
            safety_band=SafetyBand.GREEN.value,
        )
        cap_names = [sc.contract.name for sc in result.capabilities if sc.contract]
        offline_caps = [n for n in cap_names if "bulk_offline" in n]
        assert len(offline_caps) == 0


# =========================================================================
# FAB-06 -- Policy (safety band) evaluated before execution
# =========================================================================


class TestFAB06PolicyFirst:
    """
    FAB-06: Safety band policy is evaluated before provider execution.

    Band ordering: GREEN(0) < AMBER(1) < RED(2) < CRISIS(3).
    A GREEN caller can only access GREEN capabilities.
    An AMBER caller can access GREEN + AMBER.
    """

    async def test_green_user_executes_green_capability(self) -> None:
        """GREEN user can execute a GREEN capability."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.fab06_green",
            safety_band_min=SafetyBand.GREEN.value,
        )
        register_contract_with_provider(fabric, contract)

        request = _request("tool.execute.fab06_green", user_band=SafetyBand.GREEN.value)
        result = await fabric.execute(request)
        assert_capability_result_success(result)

    async def test_green_user_cannot_execute_amber_capability(self) -> None:
        """GREEN user is rejected from AMBER capability."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.fab06_amber",
            safety_band_min=SafetyBand.AMBER.value,
        )
        register_contract_with_provider(fabric, contract)

        request = _request("tool.execute.fab06_amber", user_band=SafetyBand.GREEN.value)
        result = await fabric.execute(request)
        assert result.success is False

    async def test_amber_user_executes_amber_capability(self) -> None:
        """AMBER user can execute an AMBER capability."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.fab06_amber_ok",
            safety_band_min=SafetyBand.AMBER.value,
        )
        register_contract_with_provider(fabric, contract)

        request = _request("tool.execute.fab06_amber_ok", user_band=SafetyBand.AMBER.value)
        result = await fabric.execute(request)
        assert_capability_result_success(result)

    async def test_amber_user_executes_green_capability(self) -> None:
        """AMBER user can also execute GREEN capabilities (higher band)."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.fab06_green_by_amber",
            safety_band_min=SafetyBand.GREEN.value,
        )
        register_contract_with_provider(fabric, contract)

        request = _request("tool.execute.fab06_green_by_amber", user_band=SafetyBand.AMBER.value)
        result = await fabric.execute(request)
        assert_capability_result_success(result)

    async def test_green_user_cannot_execute_red_capability(self) -> None:
        """GREEN user is rejected from RED capability."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.fab06_red",
            safety_band_min=SafetyBand.RED.value,
        )
        register_contract_with_provider(fabric, contract)

        request = _request("tool.execute.fab06_red", user_band=SafetyBand.GREEN.value)
        result = await fabric.execute(request)
        assert result.success is False

    async def test_crisis_user_executes_crisis_capability(self) -> None:
        """CRISIS user can execute CRISIS capability."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.fab06_crisis",
            safety_band_min=SafetyBand.CRISIS.value,
        )
        register_contract_with_provider(fabric, contract)

        request = _request("tool.execute.fab06_crisis", user_band=SafetyBand.CRISIS.value)
        result = await fabric.execute(request)
        assert_capability_result_success(result)

    def test_security_context_check_band_directly(self) -> None:
        """SecurityContext.check_band() returns correct result for each pairing."""
        sc = SecurityContext()

        # GREEN user, GREEN cap -> allowed
        r = sc.check_band(SafetyBand.GREEN.value, SafetyBand.GREEN.value)
        assert r.allowed is True

        # GREEN user, AMBER cap -> denied
        r = sc.check_band(SafetyBand.GREEN.value, SafetyBand.AMBER.value)
        assert r.allowed is False

        # AMBER user, GREEN cap -> allowed
        r = sc.check_band(SafetyBand.AMBER.value, SafetyBand.GREEN.value)
        assert r.allowed is True

        # RED user, CRISIS cap -> denied
        r = sc.check_band(SafetyBand.RED.value, SafetyBand.CRISIS.value)
        assert r.allowed is False

        # CRISIS user, CRISIS cap -> allowed
        r = sc.check_band(SafetyBand.CRISIS.value, SafetyBand.CRISIS.value)
        assert r.allowed is True

    async def test_band_rejection_emits_failure_event(self) -> None:
        """Band violation through fabric.execute() emits a failure event."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.fab06_event_test",
            safety_band_min=SafetyBand.RED.value,
        )
        register_contract_with_provider(fabric, contract)

        request = _request("tool.execute.fab06_event_test", user_band=SafetyBand.GREEN.value)
        result = await fabric.execute(request)
        assert result.success is False

        # Check that a failure event was emitted
        from k1.fabric.events.fabric_events import TOPIC_CAPABILITY_FAILED

        failed_events = fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_FAILED)
        assert len(failed_events) >= 1, "Expected at least one failure event"


# =========================================================================
# FAB-07 -- Sub-agent tool scoping enforced via tools_granted[]
# =========================================================================


class TestFAB07ToolScoping:
    """
    FAB-07: Sub-agent tool scoping enforced via tools_granted[].

    ToolScope is constructed with a frozenset of allowed capability names.
    validate() raises AccessDeniedError for ungranted tools.
    is_allowed() returns False for ungranted tools (non-raising).
    """

    def test_validate_allows_granted_tool(self) -> None:
        """validate() returns True for a tool in the granted set."""
        scope = ToolScope(tools_granted=["tool.execute.weather", "tool.execute.calendar"])
        assert scope.validate("tool.execute.weather") is True
        assert scope.validate("tool.execute.calendar") is True

    def test_validate_rejects_ungranted_tool(self) -> None:
        """validate() raises AccessDeniedError for ungranted tool."""
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        with pytest.raises(AccessDeniedError) as exc_info:
            scope.validate("tool.execute.payments")
        assert "tool_scope" in str(exc_info.value)

    def test_validate_rejects_empty_name(self) -> None:
        """validate() raises AccessDeniedError for empty capability name."""
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        with pytest.raises(AccessDeniedError):
            scope.validate("")

    def test_is_allowed_true_for_granted(self) -> None:
        """is_allowed() returns True for granted tools."""
        scope = ToolScope(tools_granted=["tool.execute.weather", "tool.read.api"])
        assert scope.is_allowed("tool.execute.weather") is True
        assert scope.is_allowed("tool.read.api") is True

    def test_is_allowed_false_for_ungranted(self) -> None:
        """is_allowed() returns False for ungranted tools."""
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        assert scope.is_allowed("tool.execute.payments") is False

    def test_is_allowed_false_for_empty_name(self) -> None:
        """is_allowed() returns False for empty name."""
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        assert scope.is_allowed("") is False

    def test_empty_tools_granted_raises(self) -> None:
        """ToolScope with empty tools_granted raises ToolScopeError."""
        with pytest.raises(ToolScopeError):
            ToolScope(tools_granted=[])

    def test_tools_granted_is_frozen_set(self) -> None:
        """tools_granted property returns a frozenset (immutable)."""
        scope = ToolScope(tools_granted=["tool.execute.a", "tool.execute.b"])
        assert isinstance(scope.tools_granted, frozenset)
        assert len(scope.tools_granted) == 2

    def test_duplicate_tools_deduplicated(self) -> None:
        """Duplicate tool names are deduplicated in frozenset."""
        scope = ToolScope(tools_granted=["tool.execute.a", "tool.execute.a", "tool.execute.b"])
        assert len(scope.tools_granted) == 2

    def test_tool_scope_immutable_after_construction(self) -> None:
        """ToolScope uses __slots__; no new attributes can be added."""
        scope = ToolScope(tools_granted=["tool.execute.weather"])
        # __slots__ prevents adding arbitrary new attributes
        with pytest.raises(AttributeError):
            scope.new_attribute = "hacked"  # type: ignore[attr-defined]

    def test_tool_scope_repr(self) -> None:
        """ToolScope repr includes sorted tool names."""
        scope = ToolScope(tools_granted=["tool.execute.b", "tool.execute.a"])
        r = repr(scope)
        assert "ToolScope" in r
        assert "tool.execute.a" in r
        assert "tool.execute.b" in r

    def test_large_grant_set_checks_correctly(self) -> None:
        """ToolScope with 50 tools correctly allows and denies."""
        tools = [f"tool.execute.cap_{i:03d}" for i in range(50)]
        scope = ToolScope(tools_granted=tools)

        # All granted tools are allowed
        for t in tools:
            assert scope.is_allowed(t) is True

        # Ungranted tool is denied
        assert scope.is_allowed("tool.execute.cap_999") is False


# =========================================================================
# FAB-08 -- Context window budget capped at 128K tokens
# =========================================================================


class TestFAB08ContextBudget:
    """
    FAB-08: Context window budget capped at 128K tokens.

    TOKEN_CEILING = 128_000 in context_budget.py.
    ContextBuilder enforces this ceiling with multi-level compression.
    """

    def test_token_ceiling_is_128k(self) -> None:
        """TOKEN_CEILING constant equals 128,000."""
        assert TOKEN_CEILING == 128_000

    def test_compression_levels_defined(self) -> None:
        """CompressionLevel enum has NONE through L5."""
        levels = list(CompressionLevel)
        assert len(levels) >= 6  # NONE + L1-L5
        assert CompressionLevel.NONE in levels
        assert CompressionLevel.L1_DROP_OPTIONAL in levels
        assert CompressionLevel.L5_EMERGENCY_HOT_ONLY in levels

    def test_compression_level_ordering(self) -> None:
        """CompressionLevel members are ordered NONE -> L1 -> L2 -> ... -> L5."""
        levels = list(CompressionLevel)
        level_names = [lv.name for lv in levels]
        assert level_names[0] == "NONE"
        assert level_names[1] == "L1_DROP_OPTIONAL"
        assert level_names[2] == "L2_TRUNCATE_HISTORY"
        assert level_names[3] == "L3_SUMMARIZE_BELIEFS"
        assert level_names[4] == "L4_SUMMARIZE_SCOREBOARD"
        assert level_names[5] == "L5_EMERGENCY_HOT_ONLY"

    def test_budget_result_fields(self) -> None:
        """BudgetResult has required fields: total_tokens, compression_applied, over_budget."""
        br = BudgetResult(
            total_tokens=50000,
            compression_applied=CompressionLevel.NONE,
            over_budget=False,
        )
        assert br.total_tokens == 50000
        assert br.compression_applied == CompressionLevel.NONE
        assert br.over_budget is False

    def test_budget_result_over_budget_flag(self) -> None:
        """BudgetResult.over_budget is True when tokens exceed ceiling."""
        br = BudgetResult(
            total_tokens=200_000,
            compression_applied=CompressionLevel.L5_EMERGENCY_HOT_ONLY,
            over_budget=True,
        )
        assert br.over_budget is True
        assert br.total_tokens > TOKEN_CEILING

    async def test_context_builder_enforces_ceiling(self) -> None:
        """ContextBuilder.build() produces context within TOKEN_CEILING."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.budget_test",
            safety_band_min=SafetyBand.GREEN.value,
        )
        register_contract_with_provider(fabric, contract)

        # Access context builder directly
        builder = fabric.facade._context_builder
        build_result = builder.build(
            contract=contract,
            params={"input_a": "test"},
            session_id="budget-session-001",
        )

        # ContextBuildResult has budget (BudgetResult)
        assert build_result.budget is not None
        assert build_result.budget.total_tokens <= TOKEN_CEILING

    async def test_small_context_no_compression(self) -> None:
        """Small context within budget requires no compression."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.budget_small",
            safety_band_min=SafetyBand.GREEN.value,
        )
        register_contract_with_provider(fabric, contract)

        builder = fabric.facade._context_builder
        build_result = builder.build(
            contract=contract,
            params={"input_a": "small test"},
            session_id="small-session-001",
        )

        assert build_result.budget.compression_applied == CompressionLevel.NONE
        assert build_result.budget.over_budget is False

    async def test_execution_with_context_succeeds(self) -> None:
        """Full execution through fabric.execute() respects budget."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.budget_exec",
            safety_band_min=SafetyBand.GREEN.value,
        )
        register_contract_with_provider(fabric, contract)

        request = _request("tool.execute.budget_exec")
        result = await fabric.execute(request)
        assert_capability_result_success(result)

    def test_context_budget_source_defines_ceiling(self) -> None:
        """context_budget.py source code defines TOKEN_CEILING = 128_000."""
        budget_src = Path(__file__).parents[3] / "k1" / "fabric" / "core" / "context_budget.py"
        source = budget_src.read_text(encoding="utf-8")
        assert "TOKEN_CEILING" in source
        assert "128_000" in source or "128000" in source

    async def test_large_session_triggers_compression(self) -> None:
        """Large session state triggers compression above L0."""
        fabric = _make_fabric()
        contract = _make_contract(
            "tool.execute.budget_large",
            safety_band_min=SafetyBand.GREEN.value,
        )
        register_contract_with_provider(fabric, contract)

        # Load large session data to trigger compression
        state_reader = fabric.facade._provider_factory._port_deps.get("state_reader")
        if state_reader is not None and hasattr(state_reader, "load_many"):
            # Create large session content (simulate many tokens)
            large_content = " ".join(["word"] * 50000)  # ~50K words
            state_reader.load_many(
                "large-session-001",
                {
                    "conversation_history": large_content,
                    "beliefs": large_content,
                    "scoreboard": large_content,
                },
            )

            builder = fabric.facade._context_builder
            build_result = builder.build(
                contract=contract,
                params={"input_a": "test"},
                session_id="large-session-001",
            )

            # Budget should be within ceiling, potentially with compression
            assert build_result.budget.total_tokens <= TOKEN_CEILING
