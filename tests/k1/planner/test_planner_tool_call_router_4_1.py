"""
Tests for ToolCallRouter (Epic 4.1).

Covers all 7 issues of Epic 4.1:
  4.1.1 -- ToolCallRouter skeleton & constructor
  4.1.2 -- discover_capabilities routing (IFabricRetrievalPort)
  4.1.3 -- find_relevant_prompts routing (IFabricRetrievalPort)
  4.1.4 -- query_planning_context routing (IStateReadPort)
  4.1.5 -- recall_for_planning routing (IBridgePort)
  4.1.6 -- Call count enforcement (PLAN-05, max 6 per plan)
  4.1.7 -- Read-only tool enforcement (PLAN-02)

Test categories (~35 tests target):
  A. Constructor & skeleton          (~5)
  B. Routing correctness             (~8)
  C. Call counting / PLAN-05 budget  (~8)
  D. Degraded paths                  (~5)
  E. Concurrent dispatch             (~3)
  F. Cross-stage reset               (~3)
  G. Structural enforcement          (~5)
  H. get_schema (EXPAND bridge)      (~3)

References
----------
- planner.md Section 11 (Discovery Tools Deep Dive)
- planner.md Section 17.7 (ToolCallRouter ~35 tests)
"""

from __future__ import annotations

import ast
import asyncio
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.ports.state_reader import SessionSnapshot
from k1.fabric.types import RetrievalResult
from k1.planner.config import PlannerConfig
from k1.planner.services.tool_call_router import _RETRY_POLICY, ToolCallRouter
from k1.planner.types import BudgetExhaustedError, RecallResponse, UnknownToolError

# ===========================================================================
# Fakes
# ===========================================================================


class FakeFabricRetrieval:
    """Configurable fake IFabricRetrievalPort for testing."""

    def __init__(self) -> None:
        self.discover_calls: List[Dict[str, Any]] = []
        self.find_prompts_calls: List[Dict[str, Any]] = []
        self.discover_result: RetrievalResult = RetrievalResult()
        self.find_prompts_result: RetrievalResult = RetrievalResult()
        self.discover_error: Optional[Exception] = None
        self.find_prompts_error: Optional[Exception] = None
        self.discover_delay_s: float = 0.0
        self.find_prompts_delay_s: float = 0.0

    async def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = "GREEN",
        session_context: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> RetrievalResult:
        self.discover_calls.append(
            {
                "domain": domain,
                "intent": intent,
                "safety_band": safety_band,
                "session_context": session_context,
                "top_k": top_k,
            }
        )
        if self.discover_delay_s:
            await asyncio.sleep(self.discover_delay_s)
        if self.discover_error:
            raise self.discover_error
        return self.discover_result

    async def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = "GREEN",
        top_k: int = 10,
    ) -> RetrievalResult:
        self.find_prompts_calls.append(
            {
                "intent": intent,
                "domain": domain,
                "safety_band": safety_band,
                "top_k": top_k,
            }
        )
        if self.find_prompts_delay_s:
            await asyncio.sleep(self.find_prompts_delay_s)
        if self.find_prompts_error:
            raise self.find_prompts_error
        return self.find_prompts_result


class FakeStateRead:
    """Configurable fake IStateReadPort for testing."""

    def __init__(self) -> None:
        self.read_calls: List[Dict[str, Any]] = []
        self.read_result: SessionSnapshot = SessionSnapshot()
        self.read_error: Optional[Exception] = None
        self.read_delay_s: float = 0.0

    async def read_sections(
        self,
        sections: List[str],
        trace_id: str = "",
    ) -> SessionSnapshot:
        self.read_calls.append({"sections": sections, "trace_id": trace_id})
        if self.read_delay_s:
            await asyncio.sleep(self.read_delay_s)
        if self.read_error:
            raise self.read_error
        return self.read_result


class FakeBridgePort:
    """Configurable fake IBridgePort for testing."""

    def __init__(self) -> None:
        self.recall_calls: List[Dict[str, Any]] = []
        self.recall_result: RecallResponse = RecallResponse()
        self.recall_error: Optional[Exception] = None
        self.recall_delay_s: float = 0.0
        self.persist_calls: List[Any] = []

    async def recall(
        self,
        query: str,
        selectors: Optional[List[str]] = None,
        *,
        trace_id: str = "",
    ) -> RecallResponse:
        self.recall_calls.append({"query": query, "selectors": selectors, "trace_id": trace_id})
        if self.recall_delay_s:
            await asyncio.sleep(self.recall_delay_s)
        if self.recall_error:
            raise self.recall_error
        return self.recall_result

    async def persist_plan(self, plan: Any, *, trace_id: str = "") -> None:
        self.persist_calls.append(plan)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture()
def fabric() -> FakeFabricRetrieval:
    return FakeFabricRetrieval()


@pytest.fixture()
def state_read() -> FakeStateRead:
    return FakeStateRead()


@pytest.fixture()
def bridge() -> FakeBridgePort:
    return FakeBridgePort()


@pytest.fixture()
def router(
    fabric: FakeFabricRetrieval,
    state_read: FakeStateRead,
    bridge: FakeBridgePort,
) -> ToolCallRouter:
    return ToolCallRouter(fabric, state_read, bridge)


# ===========================================================================
# Category A: Constructor & Skeleton (~5)
# ===========================================================================


class TestConstructorSkeleton:
    """4.1.1 -- ToolCallRouter skeleton & constructor."""

    def test_valid_construction(
        self,
        fabric: FakeFabricRetrieval,
        state_read: FakeStateRead,
        bridge: FakeBridgePort,
    ) -> None:
        """Valid 3-port construction succeeds."""
        router = ToolCallRouter(fabric, state_read, bridge)
        assert router.tool_call_count == 0
        assert router._fabric_retrieval is fabric
        assert router._state_read is state_read
        assert router._bridge_port is bridge

    def test_none_fabric_raises(
        self,
        state_read: FakeStateRead,
        bridge: FakeBridgePort,
    ) -> None:
        """None fabric_retrieval raises TypeError."""
        with pytest.raises(TypeError, match="fabric_retrieval"):
            ToolCallRouter(None, state_read, bridge)  # type: ignore[arg-type]

    def test_none_state_read_raises(
        self,
        fabric: FakeFabricRetrieval,
        bridge: FakeBridgePort,
    ) -> None:
        """None state_read raises TypeError."""
        with pytest.raises(TypeError, match="state_read"):
            ToolCallRouter(fabric, None, bridge)  # type: ignore[arg-type]

    def test_none_bridge_raises(
        self,
        fabric: FakeFabricRetrieval,
        state_read: FakeStateRead,
    ) -> None:
        """None bridge_port raises TypeError."""
        with pytest.raises(TypeError, match="bridge_port"):
            ToolCallRouter(fabric, state_read, None)  # type: ignore[arg-type]

    def test_slots(self, router: ToolCallRouter) -> None:
        """ToolCallRouter uses __slots__ (no __dict__)."""
        assert hasattr(router, "__slots__")
        assert not hasattr(router, "__dict__")

    def test_custom_config(
        self,
        fabric: FakeFabricRetrieval,
        state_read: FakeStateRead,
        bridge: FakeBridgePort,
    ) -> None:
        """Custom PlannerConfig is accepted and stored."""
        cfg = PlannerConfig(max_tool_calls_per_plan=3)
        router = ToolCallRouter(fabric, state_read, bridge, config=cfg)
        assert router._config.max_tool_calls_per_plan == 3


# ===========================================================================
# Category B: Routing Correctness (~8)
# ===========================================================================


class TestRoutingCorrectness:
    """4.1.2-4.1.5 -- Each convenience method delegates correctly."""

    async def test_discover_routes_to_fabric(
        self, router: ToolCallRouter, fabric: FakeFabricRetrieval
    ) -> None:
        """discover() delegates to IFabricRetrievalPort.discover_capabilities."""
        result = await router.discover(intent="find restaurant", domain="food")
        assert result is fabric.discover_result
        assert len(fabric.discover_calls) == 1
        call = fabric.discover_calls[0]
        assert call["intent"] == "find restaurant"
        assert call["domain"] == ["food"]  # str -> [str] wrapping
        assert call["safety_band"] == "GREEN"
        assert call["top_k"] == 10

    async def test_discover_none_domain(
        self, router: ToolCallRouter, fabric: FakeFabricRetrieval
    ) -> None:
        """discover() with domain=None passes None (no wrapping)."""
        await router.discover(intent="test")
        assert fabric.discover_calls[0]["domain"] is None

    async def test_discover_custom_params(
        self, router: ToolCallRouter, fabric: FakeFabricRetrieval
    ) -> None:
        """discover() passes custom safety_band and top_k."""
        await router.discover(intent="test", safety_band="AMBER", top_k=5, domain="medical")
        call = fabric.discover_calls[0]
        assert call["safety_band"] == "AMBER"
        assert call["top_k"] == 5
        assert call["domain"] == ["medical"]

    async def test_find_prompts_routes_to_fabric(
        self, router: ToolCallRouter, fabric: FakeFabricRetrieval
    ) -> None:
        """find_prompts() delegates to IFabricRetrievalPort.find_relevant_prompts."""
        result = await router.find_prompts(intent="invitation template", domain="social")
        assert result is fabric.find_prompts_result
        assert len(fabric.find_prompts_calls) == 1
        call = fabric.find_prompts_calls[0]
        assert call["intent"] == "invitation template"
        assert call["domain"] == ["social"]  # str -> [str] wrapping
        assert call["top_k"] == 5  # default for find_prompts

    async def test_read_context_routes_to_state(
        self, router: ToolCallRouter, state_read: FakeStateRead
    ) -> None:
        """read_context() delegates to IStateReadPort.read_sections."""
        snapshot = SessionSnapshot(
            sections={"beliefs_active": {"entity": "test"}},
        )
        state_read.read_result = snapshot
        result = await router.read_context(
            session_id="sess-1",
            sections=["beliefs_active", "control"],
        )
        assert result is snapshot
        assert len(state_read.read_calls) == 1
        assert state_read.read_calls[0]["sections"] == ["beliefs_active", "control"]

    async def test_recall_memory_routes_to_bridge(
        self, router: ToolCallRouter, bridge: FakeBridgePort
    ) -> None:
        """recall_memory() delegates to IBridgePort.recall."""
        recall = RecallResponse(
            facts=[{"fact": "user prefers Italian"}],
            scores=[0.92],
            trace_id="t-1",
        )
        bridge.recall_result = recall
        result = await router.recall_memory(query="dinner preferences", trace_id="t-1")
        assert result is recall
        assert len(bridge.recall_calls) == 1
        call = bridge.recall_calls[0]
        assert call["query"] == "dinner preferences"
        assert call["trace_id"] == "t-1"

    async def test_recall_returns_recall_response_not_bridge_command(
        self, router: ToolCallRouter, bridge: FakeBridgePort
    ) -> None:
        """Return type is RecallResponse (not BridgeCommandResult)."""
        result = await router.recall_memory(query="test", trace_id="t-2")
        assert isinstance(result, RecallResponse)

    async def test_call_dispatches_raw(
        self, router: ToolCallRouter, fabric: FakeFabricRetrieval
    ) -> None:
        """call() directly dispatches by tool name."""
        result = await router.call("discover_capabilities", intent="raw test", top_k=3)
        assert result is fabric.discover_result
        assert fabric.discover_calls[0]["intent"] == "raw test"
        assert fabric.discover_calls[0]["top_k"] == 3


# ===========================================================================
# Category C: Call Counting / PLAN-05 Budget (~8)
# ===========================================================================


class TestCallCountingBudget:
    """4.1.6 -- Call count enforcement (PLAN-05, max 6 per plan)."""

    async def test_counter_starts_at_zero(self, router: ToolCallRouter) -> None:
        """Counter starts at 0."""
        assert router.tool_call_count == 0

    async def test_counter_increments_per_call(self, router: ToolCallRouter) -> None:
        """Counter increments by 1 per successful call."""
        await router.discover(intent="a")
        assert router.tool_call_count == 1
        await router.find_prompts(intent="b")
        assert router.tool_call_count == 2
        await router.read_context(session_id="s", sections=["beliefs_active"])
        assert router.tool_call_count == 3

    async def test_budget_exhaustion_at_limit(
        self,
        fabric: FakeFabricRetrieval,
        state_read: FakeStateRead,
        bridge: FakeBridgePort,
    ) -> None:
        """BudgetExhaustedError raised when count reaches max (default 6)."""
        router = ToolCallRouter(fabric, state_read, bridge)
        for i in range(6):
            await router.discover(intent=f"call-{i}")
        assert router.tool_call_count == 6
        with pytest.raises(BudgetExhaustedError, match="6/6"):
            await router.discover(intent="overflow")

    async def test_custom_budget_limit(
        self,
        fabric: FakeFabricRetrieval,
        state_read: FakeStateRead,
        bridge: FakeBridgePort,
    ) -> None:
        """Custom max_tool_calls_per_plan is respected."""
        cfg = PlannerConfig(max_tool_calls_per_plan=2)
        router = ToolCallRouter(fabric, state_read, bridge, config=cfg)
        await router.discover(intent="a")
        await router.find_prompts(intent="b")
        with pytest.raises(BudgetExhaustedError, match="2/2"):
            await router.recall_memory(query="c", trace_id="t")

    async def test_reset_clears_counter(self, router: ToolCallRouter) -> None:
        """reset() sets tool_call_count back to 0."""
        await router.discover(intent="a")
        await router.discover(intent="b")
        assert router.tool_call_count == 2
        router.reset()
        assert router.tool_call_count == 0

    async def test_budget_available_after_reset(self, router: ToolCallRouter) -> None:
        """After reset, full budget is available again."""
        for _ in range(6):
            await router.discover(intent="fill")
        router.reset()
        # Should not raise
        await router.discover(intent="after-reset")
        assert router.tool_call_count == 1

    async def test_counter_not_incremented_on_budget_error(self, router: ToolCallRouter) -> None:
        """Counter does NOT increment when BudgetExhaustedError is raised."""
        cfg = PlannerConfig(max_tool_calls_per_plan=1)
        router = ToolCallRouter(
            router._fabric_retrieval,
            router._state_read,
            router._bridge_port,
            config=cfg,
        )
        await router.discover(intent="first")
        assert router.tool_call_count == 1
        with pytest.raises(BudgetExhaustedError):
            await router.discover(intent="second")
        assert router.tool_call_count == 1  # unchanged

    async def test_counter_not_incremented_on_unknown_tool(self, router: ToolCallRouter) -> None:
        """Counter does NOT increment when UnknownToolError is raised."""
        with pytest.raises(UnknownToolError):
            await router.call("nonexistent_tool")
        assert router.tool_call_count == 0


# ===========================================================================
# Category D: Degraded Paths (~5)
# ===========================================================================


class TestDegradedPaths:
    """4.1.5, 4.1.6 -- Degraded paths and error handling."""

    async def test_unknown_tool_raises(self, router: ToolCallRouter) -> None:
        """Unknown tool name raises UnknownToolError."""
        with pytest.raises(UnknownToolError, match="execute_capability"):
            await router.call("execute_capability")

    async def test_unknown_tool_error_message_lists_valid(self, router: ToolCallRouter) -> None:
        """UnknownToolError message includes valid tool names."""
        with pytest.raises(UnknownToolError, match="discover_capabilities"):
            await router.call("bad_tool")

    async def test_discover_port_error_propagates(
        self, router: ToolCallRouter, fabric: FakeFabricRetrieval
    ) -> None:
        """Port exceptions propagate to caller."""
        fabric.discover_error = RuntimeError("fabric down")
        with pytest.raises(RuntimeError, match="fabric down"):
            await router.discover(intent="test")

    async def test_recall_empty_on_offline(
        self, router: ToolCallRouter, bridge: FakeBridgePort
    ) -> None:
        """Empty RecallResponse returned when bridge returns empty (K0 offline)."""
        bridge.recall_result = RecallResponse()
        result = await router.recall_memory(query="test", trace_id="t")
        assert result.facts == []
        assert result.scores == []

    async def test_retry_on_discover_failure(
        self, router: ToolCallRouter, fabric: FakeFabricRetrieval
    ) -> None:
        """discover_capabilities retries once on failure (50ms/1 retry)."""
        call_count = 0
        original_discover = fabric.discover_capabilities

        async def flaky_discover(**kwargs: Any) -> RetrievalResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("flaky network")
            return fabric.discover_result

        fabric.discover_capabilities = flaky_discover  # type: ignore[assignment]
        result = await router.discover(intent="retry-test")
        assert call_count == 2  # 1 failure + 1 retry
        assert result is fabric.discover_result
        assert router.tool_call_count == 1  # only 1 logical call


# ===========================================================================
# Category E: Concurrent Dispatch (~3)
# ===========================================================================


class TestConcurrentDispatch:
    """SS11.5.4/SS24.1 -- Concurrent dispatch safety."""

    async def test_gather_multiple_tools(self, router: ToolCallRouter) -> None:
        """Multiple tools dispatched via asyncio.gather all succeed."""
        results = await asyncio.gather(
            router.discover(intent="a"),
            router.find_prompts(intent="b"),
            router.read_context(session_id="s", sections=["control"]),
        )
        assert len(results) == 3
        assert router.tool_call_count == 3

    async def test_gather_counter_correct(
        self,
        fabric: FakeFabricRetrieval,
        state_read: FakeStateRead,
        bridge: FakeBridgePort,
    ) -> None:
        """Counter is correct after concurrent calls (event loop serializes)."""
        router = ToolCallRouter(fabric, state_read, bridge)
        await asyncio.gather(
            router.discover(intent="1"),
            router.discover(intent="2"),
            router.recall_memory(query="3", trace_id="t"),
        )
        assert router.tool_call_count == 3

    async def test_gather_respects_budget(
        self,
        fabric: FakeFabricRetrieval,
        state_read: FakeStateRead,
        bridge: FakeBridgePort,
    ) -> None:
        """Budget enforced even under concurrent dispatch."""
        cfg = PlannerConfig(max_tool_calls_per_plan=2)
        router = ToolCallRouter(fabric, state_read, bridge, config=cfg)
        # Two calls succeed, third should raise BudgetExhaustedError.
        # However, under asyncio.gather all three start "at once" in the
        # event loop.  Since Python is single-threaded, the first two will
        # acquire budget before the third checks.
        tasks = [
            router.discover(intent="1"),
            router.discover(intent="2"),
            router.discover(intent="3"),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # At least one should be BudgetExhaustedError
        errors = [r for r in results if isinstance(r, BudgetExhaustedError)]
        successes = [r for r in results if isinstance(r, RetrievalResult)]
        assert len(errors) >= 1
        assert len(successes) >= 2 or len(successes) + len(errors) == 3


# ===========================================================================
# Category F: Cross-Stage Reset (~3)
# ===========================================================================


class TestCrossStageReset:
    """SS11.5.2 -- Counter lifecycle across stages."""

    async def test_counter_persists_across_stages(self, router: ToolCallRouter) -> None:
        """Counter is NOT reset between SKETCH and EXPAND (shared budget)."""
        # SKETCH uses 3 calls
        await router.discover(intent="sketch-1")
        await router.read_context(session_id="s", sections=["beliefs_active"])
        await router.recall_memory(query="recall", trace_id="t")
        assert router.tool_call_count == 3
        # EXPAND uses remaining budget
        await router.discover(intent="expand-1")
        await router.find_prompts(intent="expand-2")
        assert router.tool_call_count == 5
        # Still 1 call left
        await router.discover(intent="expand-3")
        assert router.tool_call_count == 6

    async def test_reset_between_plans(self, router: ToolCallRouter) -> None:
        """Reset at LC_PLAN_START allows fresh budget for next plan."""
        # First plan
        for _ in range(4):
            await router.discover(intent="plan1")
        assert router.tool_call_count == 4
        # Plan boundary
        router.reset()
        assert router.tool_call_count == 0
        # Second plan - full budget available
        for _ in range(6):
            await router.discover(intent="plan2")
        assert router.tool_call_count == 6

    async def test_micro_replan_gets_fresh_budget(self, router: ToolCallRouter) -> None:
        """Micro-replan reset provides fresh 6-call budget (SS10.3)."""
        for _ in range(5):
            await router.discover(intent="main")
        router.reset()  # micro-replan start
        assert router.tool_call_count == 0
        await router.discover(intent="micro-1")
        assert router.tool_call_count == 1


# ===========================================================================
# Category G: Structural Enforcement (~5)
# ===========================================================================


class TestStructuralEnforcement:
    """4.1.7 -- PLAN-02, PLAN-06 structural guarantees."""

    def test_routing_table_exactly_four_entries(self) -> None:
        """_ROUTING_TABLE has exactly 4 entries (SS11.5.1)."""
        assert len(ToolCallRouter._ROUTING_TABLE) == 4

    def test_routing_table_is_frozen(self) -> None:
        """_ROUTING_TABLE is immutable (MappingProxyType)."""
        assert isinstance(ToolCallRouter._ROUTING_TABLE, types.MappingProxyType)
        with pytest.raises(TypeError):
            ToolCallRouter._ROUTING_TABLE["new_tool"] = "_new_port"  # type: ignore[index]

    def test_routing_table_contains_only_read_tools(self) -> None:
        """All 4 routed tools are read-only (PLAN-02)."""
        expected_tools = {
            "discover_capabilities",
            "find_relevant_prompts",
            "query_planning_context",
            "recall_for_planning",
        }
        assert set(ToolCallRouter._ROUTING_TABLE.keys()) == expected_tools

    def test_no_execute_route(self) -> None:
        """No execute/invoke/write route in routing table (PLAN-06)."""
        for tool_name in ToolCallRouter._ROUTING_TABLE:
            assert "execute" not in tool_name.lower()
            assert "invoke" not in tool_name.lower()
            assert "write" not in tool_name.lower()
            assert "mutate" not in tool_name.lower()

    def test_no_dynamic_registration_methods(self) -> None:
        """No register_tool() or add_route() methods exist."""
        router_methods = dir(ToolCallRouter)
        assert "register_tool" not in router_methods
        assert "add_route" not in router_methods
        assert "register" not in router_methods
        assert "add_tool" not in router_methods

    def test_retry_policy_is_frozen(self) -> None:
        """_RETRY_POLICY is immutable (MappingProxyType)."""
        assert isinstance(_RETRY_POLICY, types.MappingProxyType)
        with pytest.raises(TypeError):
            _RETRY_POLICY["new"] = (0, 0)  # type: ignore[index]

    def test_retry_policy_matches_spec(self) -> None:
        """Retry policy matches SS11.5.3 specification."""
        assert _RETRY_POLICY["discover_capabilities"] == (50, 1)
        assert _RETRY_POLICY["find_relevant_prompts"] == (50, 1)
        assert _RETRY_POLICY["query_planning_context"] == (10, 0)
        assert _RETRY_POLICY["recall_for_planning"] == (100, 0)


# ===========================================================================
# Category H: get_schema (EXPAND bridge) (~3)
# ===========================================================================


class TestGetSchema:
    """ExpandToolRouterLike.get_schema -- bypasses routing table."""

    async def test_get_schema_does_not_count_budget(self, router: ToolCallRouter) -> None:
        """get_schema() does NOT increment tool_call_count."""
        await router.get_schema(capability_name="my-cap")
        assert router.tool_call_count == 0

    async def test_get_schema_returns_none_for_missing(self, router: ToolCallRouter) -> None:
        """get_schema() returns None when capability not found."""
        result = await router.get_schema(capability_name="nonexistent")
        assert result is None

    async def test_get_schema_returns_first_capability(
        self, router: ToolCallRouter, fabric: FakeFabricRetrieval
    ) -> None:
        """get_schema() returns first ScoredCapability on match."""
        from k1.fabric.types import ScoredCapability

        cap = ScoredCapability(score=0.95)
        fabric.discover_result = RetrievalResult(capabilities=[cap])
        result = await router.get_schema(capability_name="test-cap")
        assert result is cap


# ===========================================================================
# Category I: Protocol compliance (~4)
# ===========================================================================


class TestProtocolCompliance:
    """Verify ToolCallRouter satisfies the Protocol stubs."""

    def test_has_tool_call_count_property(self, router: ToolCallRouter) -> None:
        """tool_call_count is a read-only property."""
        assert isinstance(type(router).__dict__["tool_call_count"], property)

    def test_has_reset_method(self, router: ToolCallRouter) -> None:
        """reset() is a synchronous method."""
        assert callable(router.reset)
        assert not asyncio.iscoroutinefunction(router.reset)

    def test_has_all_convenience_methods(self, router: ToolCallRouter) -> None:
        """All 4 convenience methods + get_schema exist and are async."""
        for method_name in (
            "discover",
            "find_prompts",
            "read_context",
            "recall_memory",
            "get_schema",
        ):
            method = getattr(router, method_name)
            assert asyncio.iscoroutinefunction(method), f"{method_name} is not async"

    def test_layer_2_no_llm_import(self) -> None:
        """ToolCallRouter does NOT import ILLMPort (Layer 2 boundary)."""
        src = Path("k1/planner/services/tool_call_router.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names = [alias.name for alias in node.names]
                assert "ILLMPort" not in names, "ToolCallRouter must not import ILLMPort"


# ===========================================================================
# Category J: Timeout behavior (~2)
# ===========================================================================


class TestTimeoutBehavior:
    """Verify timeout and retry per-tool policy."""

    async def test_discover_retries_once_on_timeout(
        self,
        fabric: FakeFabricRetrieval,
        state_read: FakeStateRead,
        bridge: FakeBridgePort,
    ) -> None:
        """discover_capabilities retries once (policy: 50ms/1 retry)."""
        call_count = 0

        async def slow_discover(**kwargs: Any) -> RetrievalResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Exceed 50ms timeout
                await asyncio.sleep(0.2)
            return RetrievalResult()

        fabric.discover_capabilities = slow_discover  # type: ignore[assignment]
        router = ToolCallRouter(fabric, state_read, bridge)
        result = await router.discover(intent="timeout-test")
        assert call_count == 2  # 1 timeout + 1 success
        assert router.tool_call_count == 1

    async def test_recall_no_retry_on_timeout(
        self,
        fabric: FakeFabricRetrieval,
        state_read: FakeStateRead,
        bridge: FakeBridgePort,
    ) -> None:
        """recall_for_planning does NOT retry (policy: 100ms/0 retries)."""
        call_count = 0

        async def slow_recall(
            query: str,
            selectors: Optional[List[str]] = None,
            *,
            trace_id: str = "",
        ) -> RecallResponse:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.5)  # Exceed 100ms timeout
            return RecallResponse()

        bridge.recall = slow_recall  # type: ignore[assignment]
        router = ToolCallRouter(fabric, state_read, bridge)
        with pytest.raises(asyncio.TimeoutError):
            await router.recall_memory(query="timeout", trace_id="t")
        assert call_count == 1  # no retry
        # Counter should NOT have been incremented (dispatch failed)
        assert router.tool_call_count == 0
