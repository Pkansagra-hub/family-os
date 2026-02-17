"""Tests for ExpandService agentic implementation (Issues 3.2.1-3.2.6).

Tests cover:
  - EXPAND_OUTPUT_SCHEMA: valid JSON Schema structure
  - EXPAND_TOOL_DEFINITIONS: 4 tools, correct structure
  - ExpandToolRouterLike protocol: runtime checkable
  - System prompt: role definition, output schema embedding
  - Initial messages: intent, rough steps, candidates, arbiter feedback
  - HubRequest construction: capability, payload, temperature=0.3
  - Tool call dispatch: routing to 4 ToolCallRouter methods
  - Agentic loop: tool-calling rounds, final answer extraction
  - Response parsing: JSON -> validated dict, edge cases
  - Post-LLM enrichment: infrastructure fields from contracts
  - execute(): full pipeline with try/retry/fallback
  - micro_execute(): abbreviated pipeline, raises on failure
  - Degraded plan: RoughSteps -> minimal PlanSteps
  - Cycle removal: circular dependency detection and removal

References
----------
- planner.md Section 7 (Stage 2 EXPAND Deep Dive)
- planner.md Section 11 (Discovery Tools)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from k1.orchestrator.types import PlanRequest, StepResult, StepStatus
from k1.planner.stages.expand_service import (
    _MAX_TOOL_ROUNDS,
    EXPAND_OUTPUT_SCHEMA,
    EXPAND_TOOL_DEFINITIONS,
    ExpandService,
    ExpandToolRouterLike,
)
from k1.planner.types import (
    ExpandedPlan,
    ExpandFailedError,
    HubResponse,
    RequestConstraints,
    RoughStep,
    SketchResult,
    StageContext,
)

# ---------------------------------------------------------------------------
# Fake collaborators
# ---------------------------------------------------------------------------


class FakeLLMPort:
    """Configurable fake LLM that returns preset responses."""

    def __init__(self) -> None:
        self.responses: List[HubResponse] = []
        self.calls: List[Any] = []
        self._call_index: int = 0

    async def execute(self, request: Any) -> Any:
        self.calls.append(request)
        if self._call_index < len(self.responses):
            resp = self.responses[self._call_index]
            self._call_index += 1
            return resp
        return HubResponse(result={"content": ""}, metadata={})


class FakeContract:
    """Fake capability contract for enrichment tests."""

    def __init__(
        self,
        name: str = "test.cap",
        has_side_effects: bool = False,
        compensation: Optional[str] = None,
        avg_latency_ms: int = 0,
        required_context: Optional[List[str]] = None,
        safety_band_min: Optional[str] = None,
        output: Optional[Dict[str, Any]] = None,
        description: str = "A test capability",
    ) -> None:
        self.name = name
        self.has_side_effects = has_side_effects
        self.compensation = compensation
        self.avg_latency_ms = avg_latency_ms
        self.required_context = required_context
        self.safety_band_min = safety_band_min
        self.output = output
        self.description = description


class FakeScoredCapability:
    """Fake ScoredCapability for discovery results."""

    def __init__(self, contract: FakeContract, score: float = 0.9) -> None:
        self.contract = contract
        self.score = score


class FakeDiscoveryResult:
    """Fake RetrievalResult from discover()."""

    def __init__(self, capabilities: Optional[List[Any]] = None) -> None:
        self.capabilities = capabilities or []


class FakeToolRouter:
    """Configurable fake ToolCallRouter for ExpandService."""

    def __init__(self) -> None:
        self._tool_call_count: int = 0
        self.discover_results: List[Any] = [None]
        self.schema_results: List[Any] = [None]
        self.find_prompts_results: List[Any] = [None]
        self.read_context_results: List[Dict[str, Any]] = [{}]
        self.discover_calls: List[Dict[str, Any]] = []
        self.schema_calls: List[Dict[str, Any]] = []
        self.find_prompts_calls: List[Dict[str, Any]] = []
        self.read_context_calls: List[Dict[str, Any]] = []
        self._discover_idx: int = 0
        self._schema_idx: int = 0
        self._find_prompts_idx: int = 0
        self._read_idx: int = 0

    @property
    def tool_call_count(self) -> int:
        return self._tool_call_count

    def reset(self) -> None:
        self._tool_call_count = 0

    async def discover(
        self,
        intent: str,
        *,
        domain: Optional[str] = None,
        safety_band: str = "GREEN",
        top_k: int = 10,
    ) -> Any:
        self._tool_call_count += 1
        self.discover_calls.append({"intent": intent, "domain": domain, "top_k": top_k})
        idx = min(self._discover_idx, len(self.discover_results) - 1)
        self._discover_idx += 1
        return self.discover_results[idx]

    async def get_schema(
        self,
        capability_name: str,
        *,
        version: Optional[str] = None,
    ) -> Any:
        self._tool_call_count += 1
        self.schema_calls.append({"capability_name": capability_name, "version": version})
        idx = min(self._schema_idx, len(self.schema_results) - 1)
        self._schema_idx += 1
        return self.schema_results[idx]

    async def find_prompts(
        self,
        intent: str,
        *,
        domain: Optional[str] = None,
        top_k: int = 5,
    ) -> Any:
        self._tool_call_count += 1
        self.find_prompts_calls.append({"intent": intent, "domain": domain, "top_k": top_k})
        idx = min(self._find_prompts_idx, len(self.find_prompts_results) - 1)
        self._find_prompts_idx += 1
        return self.find_prompts_results[idx]

    async def read_context(
        self,
        session_id: str,
        sections: list[str],
    ) -> Dict[str, Any]:
        self._tool_call_count += 1
        self.read_context_calls.append({"session_id": session_id, "sections": sections})
        idx = min(self._read_idx, len(self.read_context_results) - 1)
        self._read_idx += 1
        return self.read_context_results[idx]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def llm() -> FakeLLMPort:
    return FakeLLMPort()


@pytest.fixture
def router() -> FakeToolRouter:
    return FakeToolRouter()


@pytest.fixture
def svc(llm: FakeLLMPort, router: FakeToolRouter) -> ExpandService:
    return ExpandService(llm_port=llm, tool_router=router)


def _ctx(*, cancel: bool = False, budget: Optional[RequestConstraints] = None) -> StageContext:
    return StageContext(
        request_id="req-001",
        trace_id="trace-001",
        timeout_remaining_ms=30000,
        token_budget_remaining=4096,
        cancel_check=lambda: cancel,
        stage_budget=budget,
    )


def _plan_request(intent: str = "Book dinner for 4", **kwargs: Any) -> PlanRequest:
    return PlanRequest(intent=intent, trace_id="trace-001", **kwargs)


def _sketch_result(
    steps: Optional[List[RoughStep]] = None,
    rationale: str = "SKETCH rationale",
) -> SketchResult:
    """Build a valid SketchResult for testing."""
    return SketchResult(
        rough_steps=steps or [RoughStep(intent="Find restaurant", suggested_capability=None)],
        capability_candidates=[],
        rationale=rationale,
    )


def _expand_json(
    steps: Optional[List[Dict[str, Any]]] = None,
    dependencies: Optional[Dict[str, List[str]]] = None,
    rationale: str = "Expanded plan rationale",
) -> str:
    """Build a valid EXPAND LLM output JSON."""
    data: Dict[str, Any] = {
        "steps": steps
        or [
            {
                "id": "s1",
                "capability": "restaurant.search",
                "params": {"cuisine": "italian", "party_size": 4},
                "deps": [],
                "is_optional": False,
            },
        ],
        "dependencies": dependencies or {},
        "rationale": rationale,
    }
    return json.dumps(data)


def _llm_response(content: str = "", tool_calls: Optional[List[Any]] = None) -> HubResponse:
    """Build a HubResponse from content and optional tool_calls."""
    result: Dict[str, Any] = {"content": content}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return HubResponse(result=result, metadata={"usage": {"total_tokens": 200}})


def _tool_call(
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    call_id: str = "tc-1",
) -> Dict[str, Any]:
    """Build a tool call dict matching OpenAI function-calling format."""
    return {
        "id": call_id,
        "function": {
            "name": name,
            "arguments": json.dumps(arguments or {}),
        },
    }


# ===========================================================================
# 1. EXPAND_OUTPUT_SCHEMA
# ===========================================================================


class TestExpandOutputSchema:
    """EXPAND_OUTPUT_SCHEMA is a valid JSON Schema with required fields."""

    def test_is_dict(self) -> None:
        assert isinstance(EXPAND_OUTPUT_SCHEMA, dict)

    def test_type_is_object(self) -> None:
        assert EXPAND_OUTPUT_SCHEMA["type"] == "object"

    def test_required_fields(self) -> None:
        required = EXPAND_OUTPUT_SCHEMA["required"]
        assert "steps" in required
        assert "dependencies" in required
        assert "rationale" in required

    def test_additional_properties_false(self) -> None:
        assert EXPAND_OUTPUT_SCHEMA.get("additionalProperties") is False

    def test_steps_is_array(self) -> None:
        assert EXPAND_OUTPUT_SCHEMA["properties"]["steps"]["type"] == "array"

    def test_steps_has_min_items(self) -> None:
        assert EXPAND_OUTPUT_SCHEMA["properties"]["steps"]["minItems"] == 1

    def test_step_required_fields(self) -> None:
        step_schema = EXPAND_OUTPUT_SCHEMA["properties"]["steps"]["items"]
        assert "id" in step_schema["required"]
        assert "capability" in step_schema["required"]
        assert "params" in step_schema["required"]

    def test_step_has_all_llm_fields(self) -> None:
        step_props = EXPAND_OUTPUT_SCHEMA["properties"]["steps"]["items"]["properties"]
        expected = {
            "id",
            "capability",
            "params",
            "deps",
            "prompt_template",
            "tools_granted",
            "output_schema",
            "is_optional",
        }
        assert expected == set(step_props.keys())

    def test_dependencies_is_object(self) -> None:
        assert EXPAND_OUTPUT_SCHEMA["properties"]["dependencies"]["type"] == "object"

    def test_serializable_to_json(self) -> None:
        text = json.dumps(EXPAND_OUTPUT_SCHEMA)
        assert len(text) > 100


# ===========================================================================
# 2. EXPAND_TOOL_DEFINITIONS
# ===========================================================================


class TestExpandToolDefinitions:
    """EXPAND_TOOL_DEFINITIONS contains 4 properly structured tools."""

    def test_is_tuple(self) -> None:
        assert isinstance(EXPAND_TOOL_DEFINITIONS, tuple)

    def test_has_four_tools(self) -> None:
        assert len(EXPAND_TOOL_DEFINITIONS) == 4

    def test_all_are_function_type(self) -> None:
        for td in EXPAND_TOOL_DEFINITIONS:
            assert td["type"] == "function"

    def test_tool_names(self) -> None:
        names = {td["function"]["name"] for td in EXPAND_TOOL_DEFINITIONS}
        assert names == {
            "discover_capabilities",
            "get_capability_schema",
            "find_prompts",
            "query_session_context",
        }

    def test_all_have_parameters(self) -> None:
        for td in EXPAND_TOOL_DEFINITIONS:
            assert "parameters" in td["function"]

    def test_all_have_descriptions(self) -> None:
        for td in EXPAND_TOOL_DEFINITIONS:
            assert len(td["function"]["description"]) > 20

    def test_discover_has_intent_required(self) -> None:
        disc = [
            t for t in EXPAND_TOOL_DEFINITIONS if t["function"]["name"] == "discover_capabilities"
        ][0]
        assert "intent" in disc["function"]["parameters"]["required"]

    def test_get_capability_schema_has_capability_name_required(self) -> None:
        schema_tool = [
            t for t in EXPAND_TOOL_DEFINITIONS if t["function"]["name"] == "get_capability_schema"
        ][0]
        assert "capability_name" in schema_tool["function"]["parameters"]["required"]

    def test_get_capability_schema_has_optional_version(self) -> None:
        schema_tool = [
            t for t in EXPAND_TOOL_DEFINITIONS if t["function"]["name"] == "get_capability_schema"
        ][0]
        assert "version" in schema_tool["function"]["parameters"]["properties"]

    def test_find_prompts_has_intent_required(self) -> None:
        fp = [t for t in EXPAND_TOOL_DEFINITIONS if t["function"]["name"] == "find_prompts"][0]
        assert "intent" in fp["function"]["parameters"]["required"]

    def test_find_prompts_has_domain_param(self) -> None:
        fp = [t for t in EXPAND_TOOL_DEFINITIONS if t["function"]["name"] == "find_prompts"][0]
        assert "domain" in fp["function"]["parameters"]["properties"]

    def test_find_prompts_has_top_k_param(self) -> None:
        fp = [t for t in EXPAND_TOOL_DEFINITIONS if t["function"]["name"] == "find_prompts"][0]
        assert "top_k" in fp["function"]["parameters"]["properties"]

    def test_query_session_context_has_sections_required(self) -> None:
        qsc = [
            t for t in EXPAND_TOOL_DEFINITIONS if t["function"]["name"] == "query_session_context"
        ][0]
        assert "sections" in qsc["function"]["parameters"]["required"]

    def test_no_recall_long_term_memory(self) -> None:
        """EXPAND does NOT have recall_long_term_memory (SKETCH-only)."""
        names = {td["function"]["name"] for td in EXPAND_TOOL_DEFINITIONS}
        assert "recall_long_term_memory" not in names


# ===========================================================================
# 3. ExpandToolRouterLike Protocol
# ===========================================================================


class TestExpandToolRouterLike:
    """ExpandToolRouterLike is runtime_checkable and matches FakeToolRouter."""

    def test_fake_router_satisfies_protocol(self, router: FakeToolRouter) -> None:
        assert isinstance(router, ExpandToolRouterLike)

    def test_object_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(object(), ExpandToolRouterLike)

    def test_protocol_requires_get_schema(self) -> None:
        """An object missing get_schema() does NOT satisfy the protocol."""

        class PartialRouter:
            @property
            def tool_call_count(self) -> int:
                return 0

            def reset(self) -> None:
                pass

            async def discover(self, intent, **kw):
                pass

            async def find_prompts(self, intent, **kw):
                pass

            async def read_context(self, session_id, sections):
                pass

        assert not isinstance(PartialRouter(), ExpandToolRouterLike)


# ===========================================================================
# 4. ExpandService construction
# ===========================================================================


class TestExpandServiceConstruction:
    """ExpandService requires llm_port and tool_router."""

    def test_create_succeeds(self, llm: FakeLLMPort, router: FakeToolRouter) -> None:
        svc = ExpandService(llm_port=llm, tool_router=router)
        assert svc.llm_port is llm
        assert svc.tool_router is router

    def test_llm_port_none_raises(self, router: FakeToolRouter) -> None:
        with pytest.raises(TypeError, match="llm_port must not be None"):
            ExpandService(llm_port=None, tool_router=router)

    def test_tool_router_none_raises(self, llm: FakeLLMPort) -> None:
        with pytest.raises(TypeError, match="tool_router must not be None"):
            ExpandService(llm_port=llm, tool_router=None)

    def test_no_hil_parameter(self, llm: FakeLLMPort, router: FakeToolRouter) -> None:
        """ExpandService does NOT accept hil_coord (EXPAND has no HIL)."""
        import inspect

        sig = inspect.signature(ExpandService.__init__)
        assert "hil_coord" not in sig.parameters


# ===========================================================================
# 5. System prompt
# ===========================================================================


class TestSystemPrompt:
    """System prompt contains EXPAND-specific role and schema."""

    def test_contains_expand_role(self, svc: ExpandService) -> None:
        prompt = svc._assemble_system_prompt()
        assert "EXPAND" in prompt

    def test_contains_output_schema(self, svc: ExpandService) -> None:
        prompt = svc._assemble_system_prompt()
        schema_text = json.dumps(EXPAND_OUTPUT_SCHEMA, indent=2)
        assert schema_text in prompt

    def test_mentions_infrastructure_fields(self, svc: ExpandService) -> None:
        prompt = svc._assemble_system_prompt()
        for f in [
            "has_side_effects",
            "compensation",
            "timeout_ms",
            "required_context",
            "safety_band_min",
            "condition",
        ]:
            assert f in prompt

    def test_mentions_inter_step_references(self, svc: ExpandService) -> None:
        prompt = svc._assemble_system_prompt()
        assert "$<step_id>" in prompt

    def test_mentions_tool_guidance(self, svc: ExpandService) -> None:
        prompt = svc._assemble_system_prompt()
        assert "discover_capabilities" in prompt
        assert "get_capability_schema" in prompt
        assert "find_prompts" in prompt
        assert "query_session_context" in prompt


# ===========================================================================
# 6. Initial messages
# ===========================================================================


class TestInitialMessages:
    """Initial messages contain system prompt and user context."""

    def test_two_messages(self, svc: ExpandService) -> None:
        msgs = svc._build_initial_messages(_sketch_result(), _plan_request())
        assert len(msgs) == 2

    def test_system_message_first(self, svc: ExpandService) -> None:
        msgs = svc._build_initial_messages(_sketch_result(), _plan_request())
        assert msgs[0]["role"] == "system"

    def test_user_message_second(self, svc: ExpandService) -> None:
        msgs = svc._build_initial_messages(_sketch_result(), _plan_request())
        assert msgs[1]["role"] == "user"

    def test_user_message_contains_intent(self, svc: ExpandService) -> None:
        req = _plan_request(intent="Order pizza")
        msgs = svc._build_initial_messages(_sketch_result(), req)
        assert "Order pizza" in msgs[1]["content"]

    def test_user_message_contains_rough_steps(self, svc: ExpandService) -> None:
        sketch = _sketch_result(
            steps=[
                RoughStep(intent="Find pizza place"),
                RoughStep(intent="Place order"),
            ]
        )
        msgs = svc._build_initial_messages(sketch, _plan_request())
        assert "Find pizza place" in msgs[1]["content"]
        assert "Place order" in msgs[1]["content"]

    def test_user_message_contains_rationale(self, svc: ExpandService) -> None:
        sketch = _sketch_result(rationale="Sequential pizza workflow")
        msgs = svc._build_initial_messages(sketch, _plan_request())
        assert "Sequential pizza workflow" in msgs[1]["content"]

    def test_user_message_contains_suggested_capability(self, svc: ExpandService) -> None:
        sketch = SketchResult(
            rough_steps=[RoughStep(intent="Search", suggested_capability="cap.search")],
            capability_candidates=[FakeScoredCapability(FakeContract(name="cap.search"))],
            rationale="search plan",
        )
        msgs = svc._build_initial_messages(sketch, _plan_request())
        assert "cap.search" in msgs[1]["content"]

    def test_user_message_contains_depends_on(self, svc: ExpandService) -> None:
        sketch = _sketch_result(
            steps=[
                RoughStep(intent="Step A"),
                RoughStep(intent="Step B", depends_on=["Step A"]),
            ]
        )
        msgs = svc._build_initial_messages(sketch, _plan_request())
        assert "depends_on" in msgs[1]["content"]

    def test_arbiter_feedback_included(self, svc: ExpandService) -> None:
        msgs = svc._build_initial_messages(
            _sketch_result(),
            _plan_request(),
            arbiter_feedback=["Fix step s1 params", "Add dependency"],
        )
        content = msgs[1]["content"]
        assert "ARBITER FEEDBACK" in content
        assert "Fix step s1 params" in content
        assert "Add dependency" in content

    def test_no_arbiter_feedback_when_none(self, svc: ExpandService) -> None:
        msgs = svc._build_initial_messages(_sketch_result(), _plan_request())
        assert "ARBITER FEEDBACK" not in msgs[1]["content"]

    def test_constraints_included(self, svc: ExpandService) -> None:
        req = _plan_request(constraints={"safety_band": "AMBER"})
        msgs = svc._build_initial_messages(_sketch_result(), req)
        assert "AMBER" in msgs[1]["content"]


# ===========================================================================
# 7. Tool definitions
# ===========================================================================


class TestGetToolDefinitions:
    """_get_tool_definitions returns EXPAND_TOOL_DEFINITIONS."""

    def test_returns_expand_tools(self, svc: ExpandService) -> None:
        assert svc._get_tool_definitions() is EXPAND_TOOL_DEFINITIONS

    def test_returns_tuple(self, svc: ExpandService) -> None:
        assert isinstance(svc._get_tool_definitions(), tuple)


# ===========================================================================
# 8. HubRequest construction
# ===========================================================================


class TestBuildHubRequest:
    """HubRequest built with EXPAND-specific parameters."""

    def test_capability_is_chat(self, svc: ExpandService) -> None:
        msgs = [{"role": "system", "content": "hello"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.capability == "CHAT"

    def test_temperature_is_0_3(self, svc: ExpandService) -> None:
        msgs = [{"role": "system", "content": "hello"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.payload["temperature"] == 0.3

    def test_consumer_id_is_planner_expand(self, svc: ExpandService) -> None:
        msgs = [{"role": "system", "content": "hello"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.constraints.consumer_id == "planner.expand"

    def test_constraint_temperature_is_0_3(self, svc: ExpandService) -> None:
        msgs = [{"role": "system", "content": "hello"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.constraints.temperature == 0.3

    def test_trace_id_from_ctx(self, svc: ExpandService) -> None:
        msgs = [{"role": "system", "content": "hello"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.trace_id == "trace-001"

    def test_tools_included_when_provided(self, svc: ExpandService) -> None:
        msgs = [{"role": "system", "content": "hello"}]
        req = svc._build_hub_request(msgs, _ctx(), tools=EXPAND_TOOL_DEFINITIONS)
        assert len(req.payload["tools"]) == 4

    def test_no_tools_when_none(self, svc: ExpandService) -> None:
        msgs = [{"role": "system", "content": "hello"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert "tools" not in req.payload

    def test_stage_budget_used_for_max_tokens(self, svc: ExpandService) -> None:
        budget = RequestConstraints(
            max_tokens=2048, timeout_ms=10000, temperature=0.3, consumer_id="planner.expand"
        )
        ctx = _ctx(budget=budget)
        msgs = [{"role": "system", "content": "hello"}]
        req = svc._build_hub_request(msgs, ctx)
        assert req.constraints.max_tokens == 2048

    def test_default_max_tokens_1024(self, svc: ExpandService) -> None:
        msgs = [{"role": "system", "content": "hello"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.constraints.max_tokens == 1024

    def test_default_timeout_ms_5000(self, svc: ExpandService) -> None:
        msgs = [{"role": "system", "content": "hello"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.constraints.timeout_ms == 5000

    def test_messages_in_payload(self, svc: ExpandService) -> None:
        msgs = [{"role": "system", "content": "hello"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.payload["messages"] == msgs


# ===========================================================================
# 9. Tool call dispatch
# ===========================================================================


class TestDispatchToolCall:
    """Tool calls are routed to the correct ToolCallRouter method."""

    async def test_discover_capabilities(self, svc: ExpandService, router: FakeToolRouter) -> None:
        tc = _tool_call("discover_capabilities", {"intent": "find restaurant"})
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert len(router.discover_calls) == 1
        assert router.discover_calls[0]["intent"] == "find restaurant"

    async def test_discover_with_domain(self, svc: ExpandService, router: FakeToolRouter) -> None:
        tc = _tool_call("discover_capabilities", {"intent": "find", "domain": "food", "top_k": 3})
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert router.discover_calls[0]["domain"] == "food"
        assert router.discover_calls[0]["top_k"] == 3

    async def test_get_capability_schema(self, svc: ExpandService, router: FakeToolRouter) -> None:
        tc = _tool_call("get_capability_schema", {"capability_name": "restaurant.search"})
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert len(router.schema_calls) == 1
        assert router.schema_calls[0]["capability_name"] == "restaurant.search"

    async def test_get_capability_schema_with_version(
        self, svc: ExpandService, router: FakeToolRouter
    ) -> None:
        tc = _tool_call("get_capability_schema", {"capability_name": "cap.x", "version": ">=2.0"})
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert router.schema_calls[0]["version"] == ">=2.0"

    async def test_find_prompts(self, svc: ExpandService, router: FakeToolRouter) -> None:
        tc = _tool_call("find_prompts", {"intent": "agent for scheduling"})
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert len(router.find_prompts_calls) == 1
        assert router.find_prompts_calls[0]["intent"] == "agent for scheduling"

    async def test_find_prompts_with_domain_and_top_k(
        self, svc: ExpandService, router: FakeToolRouter
    ) -> None:
        tc = _tool_call("find_prompts", {"intent": "greeting", "domain": "social", "top_k": 3})
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert router.find_prompts_calls[0]["domain"] == "social"
        assert router.find_prompts_calls[0]["top_k"] == 3

    async def test_query_session_context(self, svc: ExpandService, router: FakeToolRouter) -> None:
        tc = _tool_call("query_session_context", {"sections": ["persona", "temporal"]})
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert len(router.read_context_calls) == 1
        assert router.read_context_calls[0]["sections"] == ["persona", "temporal"]

    async def test_unknown_tool_returns_error(self, svc: ExpandService) -> None:
        tc = _tool_call("nonexistent_tool", {"foo": "bar"})
        result = await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert "error" in result
        assert "Unknown tool" in result["error"]

    async def test_tool_exception_returns_error(
        self, svc: ExpandService, router: FakeToolRouter
    ) -> None:
        """If the router method raises, dispatch returns error dict."""

        async def failing_discover(**kw):
            raise RuntimeError("discovery down")

        router.discover = failing_discover
        tc = _tool_call("discover_capabilities", {"intent": "test"})
        result = await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert "error" in result

    async def test_malformed_arguments_handled(
        self, svc: ExpandService, router: FakeToolRouter
    ) -> None:
        tc = {
            "id": "tc-1",
            "function": {"name": "discover_capabilities", "arguments": "not-json{{{"},
        }
        result = await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert len(router.discover_calls) == 1


# ===========================================================================
# 10. Response parsing
# ===========================================================================


class TestParseResponse:
    """_parse_response validates and extracts EXPAND LLM output."""

    def test_valid_json(self, svc: ExpandService) -> None:
        content = _expand_json()
        result = svc._parse_response(content)
        assert "steps" in result
        assert "dependencies" in result
        assert "rationale" in result

    def test_strips_markdown_fences(self, svc: ExpandService) -> None:
        content = "```json\n" + _expand_json() + "\n```"
        result = svc._parse_response(content)
        assert result["steps"][0]["id"] == "s1"

    def test_invalid_json_raises(self, svc: ExpandService) -> None:
        with pytest.raises(ExpandFailedError, match="not valid JSON"):
            svc._parse_response("not json at all")

    def test_non_object_raises(self, svc: ExpandService) -> None:
        with pytest.raises(ExpandFailedError, match="must be a JSON object"):
            svc._parse_response("[1, 2, 3]")

    def test_empty_steps_raises(self, svc: ExpandService) -> None:
        with pytest.raises(ExpandFailedError, match="missing or empty steps"):
            svc._parse_response(json.dumps({"steps": [], "dependencies": {}, "rationale": "r"}))

    def test_missing_steps_raises(self, svc: ExpandService) -> None:
        with pytest.raises(ExpandFailedError, match="missing or empty steps"):
            svc._parse_response(json.dumps({"dependencies": {}, "rationale": "r"}))

    def test_invalid_step_id_raises(self, svc: ExpandService) -> None:
        with pytest.raises(ExpandFailedError, match="invalid id"):
            svc._parse_response(
                json.dumps(
                    {
                        "steps": [{"id": "bad!", "capability": "x", "params": {}}],
                        "dependencies": {},
                        "rationale": "r",
                    }
                )
            )

    def test_empty_capability_raises(self, svc: ExpandService) -> None:
        with pytest.raises(ExpandFailedError, match="missing capability"):
            svc._parse_response(
                json.dumps(
                    {
                        "steps": [{"id": "s1", "capability": "", "params": {}}],
                        "dependencies": {},
                        "rationale": "r",
                    }
                )
            )

    def test_params_not_dict_raises(self, svc: ExpandService) -> None:
        with pytest.raises(ExpandFailedError, match="params must be an object"):
            svc._parse_response(
                json.dumps(
                    {
                        "steps": [{"id": "s1", "capability": "x", "params": "wrong"}],
                        "dependencies": {},
                        "rationale": "r",
                    }
                )
            )

    def test_missing_rationale_raises(self, svc: ExpandService) -> None:
        with pytest.raises(ExpandFailedError, match="missing rationale"):
            svc._parse_response(
                json.dumps(
                    {
                        "steps": [{"id": "s1", "capability": "x", "params": {}}],
                        "dependencies": {},
                        "rationale": "",
                    }
                )
            )

    def test_missing_dependencies_key_added(self, svc: ExpandService) -> None:
        """If dependencies key missing, it's added as empty dict."""
        content = json.dumps(
            {
                "steps": [{"id": "s1", "capability": "x", "params": {}}],
                "rationale": "r",
            }
        )
        result = svc._parse_response(content)
        assert result["dependencies"] == {}

    def test_multi_step_valid(self, svc: ExpandService) -> None:
        steps = [
            {"id": "s1", "capability": "cap.a", "params": {"x": 1}},
            {"id": "s2", "capability": "cap.b", "params": {"y": "$s1.result.z"}, "deps": ["s1"]},
        ]
        result = svc._parse_response(_expand_json(steps=steps, dependencies={"s2": ["s1"]}))
        assert len(result["steps"]) == 2

    def test_whitespace_tolerance(self, svc: ExpandService) -> None:
        content = "  \n  " + _expand_json() + "  \n  "
        result = svc._parse_response(content)
        assert result["steps"][0]["id"] == "s1"


# ===========================================================================
# 11. Post-LLM enrichment
# ===========================================================================


class TestEnrichSteps:
    """_enrich_steps fills infrastructure fields from contracts."""

    def test_basic_enrichment_no_contract(self, svc: ExpandService) -> None:
        """When no contract found, defaults are used."""
        llm_steps = [{"id": "s1", "capability": "unknown.cap", "params": {}}]
        steps = svc._enrich_steps(llm_steps, {})
        assert len(steps) == 1
        s = steps[0]
        assert s.id == "s1"
        assert s.capability == "unknown.cap"
        assert s.has_side_effects is False
        assert s.compensation is None
        assert s.timeout_ms == 10000  # _DEFAULT_TIMEOUT_MS
        assert s.required_context is None
        assert s.safety_band_min is None
        assert s.condition is None  # V1 always None

    def test_enrichment_from_schema_results(self, svc: ExpandService) -> None:
        """Contract from get_schema() used for enrichment."""
        contract = FakeContract(
            name="cap.a",
            has_side_effects=True,
            compensation="undo_cap_a",
            avg_latency_ms=500,
            required_context=["persona"],
            safety_band_min="AMBER",
            output={"type": "object"},
        )
        llm_steps = [{"id": "s1", "capability": "cap.a", "params": {}}]
        accumulated = {"discover": [], "schema": [contract], "prompts": [], "context": []}
        steps = svc._enrich_steps(llm_steps, accumulated)
        s = steps[0]
        assert s.has_side_effects is True
        assert s.compensation == "undo_cap_a"
        assert s.timeout_ms == 1000  # avg_latency_ms * 2
        assert s.required_context == ["persona"]
        assert s.safety_band_min == "AMBER"

    def test_enrichment_from_discover_results(self, svc: ExpandService) -> None:
        """Contract from discover() results used for enrichment."""
        contract = FakeContract(name="cap.b", avg_latency_ms=200)
        discovery = FakeDiscoveryResult(capabilities=[FakeScoredCapability(contract)])
        llm_steps = [{"id": "s1", "capability": "cap.b", "params": {}}]
        accumulated = {"discover": [discovery], "schema": [], "prompts": [], "context": []}
        steps = svc._enrich_steps(llm_steps, accumulated)
        assert steps[0].timeout_ms == 400  # 200 * 2

    def test_output_schema_from_contract_when_llm_omits(self, svc: ExpandService) -> None:
        contract = FakeContract(name="cap.c", output={"type": "string"})
        llm_steps = [{"id": "s1", "capability": "cap.c", "params": {}}]
        accumulated = {"discover": [], "schema": [contract], "prompts": [], "context": []}
        steps = svc._enrich_steps(llm_steps, accumulated)
        assert steps[0].output_schema == {"type": "string"}

    def test_output_schema_from_llm_takes_precedence(self, svc: ExpandService) -> None:
        contract = FakeContract(name="cap.c", output={"type": "string"})
        llm_steps = [
            {"id": "s1", "capability": "cap.c", "params": {}, "output_schema": {"type": "number"}}
        ]
        accumulated = {"discover": [], "schema": [contract], "prompts": [], "context": []}
        steps = svc._enrich_steps(llm_steps, accumulated)
        assert steps[0].output_schema == {"type": "number"}

    def test_meta_agent_has_side_effects(self, svc: ExpandService) -> None:
        """tool.meta.build_agent always has has_side_effects=True."""
        llm_steps = [{"id": "s1", "capability": "tool.meta.build_agent", "params": {}}]
        steps = svc._enrich_steps(llm_steps, {})
        assert steps[0].has_side_effects is True

    def test_condition_always_none_v1(self, svc: ExpandService) -> None:
        llm_steps = [{"id": "s1", "capability": "cap.x", "params": {}}]
        steps = svc._enrich_steps(llm_steps, {})
        assert steps[0].condition is None

    def test_deps_preserved(self, svc: ExpandService) -> None:
        llm_steps = [
            {"id": "s1", "capability": "cap.a", "params": {}},
            {"id": "s2", "capability": "cap.b", "params": {}, "deps": ["s1"]},
        ]
        steps = svc._enrich_steps(llm_steps, {})
        assert steps[1].deps == ["s1"]

    def test_prompt_template_preserved(self, svc: ExpandService) -> None:
        llm_steps = [
            {"id": "s1", "capability": "cap.a", "params": {}, "prompt_template": "tmpl_booking"}
        ]
        steps = svc._enrich_steps(llm_steps, {})
        assert steps[0].prompt_template == "tmpl_booking"

    def test_tools_granted_preserved(self, svc: ExpandService) -> None:
        llm_steps = [
            {"id": "s1", "capability": "cap.a", "params": {}, "tools_granted": ["tool_a", "tool_b"]}
        ]
        steps = svc._enrich_steps(llm_steps, {})
        assert steps[0].tools_granted == ["tool_a", "tool_b"]

    def test_is_optional_preserved(self, svc: ExpandService) -> None:
        llm_steps = [{"id": "s1", "capability": "cap.a", "params": {}, "is_optional": True}]
        steps = svc._enrich_steps(llm_steps, {})
        assert steps[0].is_optional is True

    def test_zero_avg_latency_uses_default(self, svc: ExpandService) -> None:
        """If contract has avg_latency_ms=0, use default timeout."""
        contract = FakeContract(name="cap.z", avg_latency_ms=0)
        llm_steps = [{"id": "s1", "capability": "cap.z", "params": {}}]
        accumulated = {"discover": [], "schema": [contract], "prompts": [], "context": []}
        steps = svc._enrich_steps(llm_steps, accumulated)
        assert steps[0].timeout_ms == 10000

    def test_schema_result_overrides_discover(self, svc: ExpandService) -> None:
        """get_schema result takes precedence over discover result."""
        disc_contract = FakeContract(name="cap.a", avg_latency_ms=100)
        schema_contract = FakeContract(name="cap.a", avg_latency_ms=300)
        discovery = FakeDiscoveryResult(capabilities=[FakeScoredCapability(disc_contract)])
        llm_steps = [{"id": "s1", "capability": "cap.a", "params": {}}]
        accumulated = {
            "discover": [discovery],
            "schema": [schema_contract],
            "prompts": [],
            "context": [],
        }
        steps = svc._enrich_steps(llm_steps, accumulated)
        # schema overwrites discover in the contract lookup
        assert steps[0].timeout_ms == 600  # 300 * 2


# ===========================================================================
# 12. Degraded plan construction
# ===========================================================================


class TestBuildDegradedPlan:
    """_build_degraded_plan produces minimal PlanSteps from SKETCH."""

    def test_single_step(self, svc: ExpandService) -> None:
        sketch = SketchResult(
            rough_steps=[RoughStep(intent="Do thing", suggested_capability="cap.thing")],
            capability_candidates=[FakeScoredCapability(FakeContract(name="cap.thing"))],
            rationale="test",
        )
        plan = svc._build_degraded_plan(sketch)
        assert len(plan.steps) == 1
        s = plan.steps[0]
        assert s.id == "s1"
        assert s.capability == "cap.thing"
        assert s.params == {}
        assert s.timeout_ms == 10000

    def test_unresolved_capability(self, svc: ExpandService) -> None:
        sketch = _sketch_result(
            steps=[
                RoughStep(intent="Do thing"),
            ]
        )
        plan = svc._build_degraded_plan(sketch)
        assert plan.steps[0].capability == "UNRESOLVED"

    def test_rationale_mentions_degraded(self, svc: ExpandService) -> None:
        sketch = _sketch_result()
        plan = svc._build_degraded_plan(sketch)
        assert "Degraded" in plan.rationale
        assert "fallback" in plan.rationale.lower()

    def test_tool_mappings_populated(self, svc: ExpandService) -> None:
        sketch = SketchResult(
            rough_steps=[
                RoughStep(intent="A", suggested_capability="cap.a"),
                RoughStep(intent="B", suggested_capability="cap.b"),
            ],
            capability_candidates=[
                FakeScoredCapability(FakeContract(name="cap.a")),
                FakeScoredCapability(FakeContract(name="cap.b")),
            ],
            rationale="test",
        )
        plan = svc._build_degraded_plan(sketch)
        assert plan.tool_mappings == {"s1": "cap.a", "s2": "cap.b"}

    def test_dependencies_from_depends_on(self, svc: ExpandService) -> None:
        sketch = _sketch_result(
            steps=[
                RoughStep(intent="First"),
                RoughStep(intent="Second", depends_on=["First"]),
            ]
        )
        plan = svc._build_degraded_plan(sketch)
        assert "s2" in plan.dependencies
        assert "s1" in plan.dependencies["s2"]

    def test_multi_step_sequential_ids(self, svc: ExpandService) -> None:
        sketch = _sketch_result(
            steps=[
                RoughStep(intent="A"),
                RoughStep(intent="B"),
                RoughStep(intent="C"),
            ]
        )
        plan = svc._build_degraded_plan(sketch)
        ids = [s.id for s in plan.steps]
        assert ids == ["s1", "s2", "s3"]


# ===========================================================================
# 13. Cycle removal
# ===========================================================================


class TestRemoveCycles:
    """_remove_cycles detects and removes back edges."""

    def test_no_cycles_unchanged(self, svc: ExpandService) -> None:
        deps = {"s2": ["s1"], "s3": ["s2"]}
        result = svc._remove_cycles(deps)
        assert result == deps

    def test_simple_cycle_removed(self, svc: ExpandService) -> None:
        deps = {"s1": ["s2"], "s2": ["s1"]}
        result = svc._remove_cycles(deps)
        # At least one back edge removed
        has_s1_s2 = "s2" in result.get("s1", [])
        has_s2_s1 = "s1" in result.get("s2", [])
        assert not (has_s1_s2 and has_s2_s1)  # cycle broken

    def test_empty_deps(self, svc: ExpandService) -> None:
        result = svc._remove_cycles({})
        assert result == {}

    def test_acyclic_three_node(self, svc: ExpandService) -> None:
        deps = {"s2": ["s1"], "s3": ["s1", "s2"]}
        result = svc._remove_cycles(deps)
        assert result == deps


# ===========================================================================
# 14. Agentic loop
# ===========================================================================


class TestAgenticLoop:
    """_run_agentic_loop handles tool-calling rounds."""

    async def test_direct_answer_no_tools(self, svc: ExpandService, llm: FakeLLMPort) -> None:
        """LLM returns final answer immediately."""
        llm.responses = [_llm_response(content=_expand_json())]
        msgs = [{"role": "system", "content": "hello"}]
        content, acc = await svc._run_agentic_loop(msgs, _plan_request(), _ctx())
        assert "steps" in content

    async def test_one_tool_round_then_answer(
        self, svc: ExpandService, llm: FakeLLMPort, router: FakeToolRouter
    ) -> None:
        """LLM calls a tool, then produces final answer."""
        llm.responses = [
            _llm_response(
                tool_calls=[_tool_call("discover_capabilities", {"intent": "restaurant"})]
            ),
            _llm_response(content=_expand_json()),
        ]
        msgs = [{"role": "system", "content": "hello"}]
        content, acc = await svc._run_agentic_loop(msgs, _plan_request(), _ctx())
        assert "steps" in content
        assert len(router.discover_calls) == 1

    async def test_accumulated_results_tracked(
        self, svc: ExpandService, llm: FakeLLMPort, router: FakeToolRouter
    ) -> None:
        """Tool results are tracked by tool type."""
        contract = FakeContract(name="cap.a")
        router.schema_results = [contract]
        llm.responses = [
            _llm_response(
                tool_calls=[
                    _tool_call(
                        "get_capability_schema", {"capability_name": "cap.a"}, call_id="tc-1"
                    ),
                    _tool_call("discover_capabilities", {"intent": "food"}, call_id="tc-2"),
                ]
            ),
            _llm_response(content=_expand_json()),
        ]
        msgs = [{"role": "system", "content": "hello"}]
        _, acc = await svc._run_agentic_loop(msgs, _plan_request(), _ctx())
        assert len(acc["schema"]) == 1
        assert len(acc["discover"]) == 1

    async def test_max_rounds_exceeded_raises(self, svc: ExpandService, llm: FakeLLMPort) -> None:
        """If LLM keeps calling tools beyond _MAX_TOOL_ROUNDS, raises."""
        llm.responses = [
            _llm_response(tool_calls=[_tool_call("discover_capabilities", {"intent": "loop"})])
        ] * (_MAX_TOOL_ROUNDS + 1)
        msgs = [{"role": "system", "content": "hello"}]
        with pytest.raises(ExpandFailedError, match="did not produce a plan"):
            await svc._run_agentic_loop(msgs, _plan_request(), _ctx())

    async def test_empty_response_raises(self, svc: ExpandService, llm: FakeLLMPort) -> None:
        """Empty content with no tool calls raises."""
        llm.responses = [_llm_response(content="")]
        msgs = [{"role": "system", "content": "hello"}]
        with pytest.raises(ExpandFailedError, match="empty response"):
            await svc._run_agentic_loop(msgs, _plan_request(), _ctx())

    async def test_cancel_check_raises(self, svc: ExpandService, llm: FakeLLMPort) -> None:
        """If cancel_check returns True, raises."""
        msgs = [{"role": "system", "content": "hello"}]
        with pytest.raises(ExpandFailedError, match="cancelled"):
            await svc._run_agentic_loop(msgs, _plan_request(), _ctx(cancel=True))

    async def test_tools_disabled_when_use_tools_false(
        self, svc: ExpandService, llm: FakeLLMPort
    ) -> None:
        """When use_tools=False, no tools in HubRequest."""
        llm.responses = [_llm_response(content=_expand_json())]
        msgs = [{"role": "system", "content": "hello"}]
        await svc._run_agentic_loop(msgs, _plan_request(), _ctx(), use_tools=False)
        assert "tools" not in llm.calls[0].payload

    async def test_tool_messages_added_to_conversation(
        self, svc: ExpandService, llm: FakeLLMPort, router: FakeToolRouter
    ) -> None:
        """Tool call results are added as tool messages."""
        llm.responses = [
            _llm_response(tool_calls=[_tool_call("discover_capabilities", {"intent": "x"})]),
            _llm_response(content=_expand_json()),
        ]
        msgs = [{"role": "system", "content": "hello"}]
        await svc._run_agentic_loop(msgs, _plan_request(), _ctx())
        # msgs should have been mutated with assistant+tool messages
        roles = [m["role"] for m in msgs]
        assert "assistant" in roles
        assert "tool" in roles


# ===========================================================================
# 15. execute() - full pipeline
# ===========================================================================


class TestExecute:
    """execute() runs full EXPAND pipeline with error recovery."""

    async def test_happy_path(self, svc: ExpandService, llm: FakeLLMPort) -> None:
        """Successful first attempt returns ExpandedPlan."""
        plan_json = _expand_json(
            steps=[{"id": "s1", "capability": "cap.a", "params": {"x": 1}, "is_optional": False}],
            rationale="Good plan",
        )
        llm.responses = [_llm_response(content=plan_json)]
        result = await svc.execute(_sketch_result(), _plan_request(), _ctx())
        assert isinstance(result, ExpandedPlan)
        assert len(result.steps) == 1
        assert result.steps[0].capability == "cap.a"
        assert result.rationale == "Good plan"

    async def test_retry_on_first_failure(self, svc: ExpandService, llm: FakeLLMPort) -> None:
        """If first attempt fails, retries simplified (no tools)."""
        llm.responses = [
            _llm_response(content="invalid json"),  # first attempt fails
            _llm_response(content=_expand_json()),  # retry succeeds
        ]
        result = await svc.execute(_sketch_result(), _plan_request(), _ctx())
        assert isinstance(result, ExpandedPlan)
        # Second call should NOT have tools
        assert "tools" not in llm.calls[1].payload

    async def test_fallback_on_double_failure(self, svc: ExpandService, llm: FakeLLMPort) -> None:
        """If both attempts fail, returns degraded plan."""
        llm.responses = [
            _llm_response(content="invalid json"),
            _llm_response(content="still invalid"),
        ]
        result = await svc.execute(
            SketchResult(
                rough_steps=[RoughStep(intent="Do something", suggested_capability="cap.x")],
                capability_candidates=[FakeScoredCapability(FakeContract(name="cap.x"))],
                rationale="test",
            ),
            _plan_request(),
            _ctx(),
        )
        assert isinstance(result, ExpandedPlan)
        assert "Degraded" in result.rationale

    async def test_arbiter_feedback_passed_to_attempt(
        self, svc: ExpandService, llm: FakeLLMPort
    ) -> None:
        """Arbiter feedback appears in LLM messages."""
        llm.responses = [_llm_response(content=_expand_json())]
        await svc.execute(
            _sketch_result(),
            _plan_request(),
            _ctx(),
            arbiter_feedback=["Fix param types"],
        )
        msgs = llm.calls[0].payload["messages"]
        user_content = msgs[1]["content"]
        assert "Fix param types" in user_content

    async def test_multi_step_plan(self, svc: ExpandService, llm: FakeLLMPort) -> None:
        """Multi-step plan with dependencies."""
        plan_json = _expand_json(
            steps=[
                {"id": "s1", "capability": "cap.a", "params": {"x": 1}},
                {
                    "id": "s2",
                    "capability": "cap.b",
                    "params": {"input": "$s1.result.output"},
                    "deps": ["s1"],
                },
            ],
            dependencies={"s2": ["s1"]},
        )
        llm.responses = [_llm_response(content=plan_json)]
        result = await svc.execute(_sketch_result(), _plan_request(), _ctx())
        assert len(result.steps) == 2
        assert result.dependencies == {"s2": ["s1"]}

    async def test_tool_mappings_built(self, svc: ExpandService, llm: FakeLLMPort) -> None:
        """tool_mappings maps step_id -> capability."""
        plan_json = _expand_json(
            steps=[
                {"id": "s1", "capability": "cap.a", "params": {}},
                {"id": "s2", "capability": "cap.b", "params": {}},
            ]
        )
        llm.responses = [_llm_response(content=plan_json)]
        result = await svc.execute(_sketch_result(), _plan_request(), _ctx())
        assert result.tool_mappings == {"s1": "cap.a", "s2": "cap.b"}

    async def test_enrichment_applied_during_execute(
        self, svc: ExpandService, llm: FakeLLMPort, router: FakeToolRouter
    ) -> None:
        """Contract info from tools is used for enrichment."""
        contract = FakeContract(
            name="cap.a",
            has_side_effects=True,
            avg_latency_ms=250,
        )
        router.schema_results = [contract]
        llm.responses = [
            _llm_response(
                tool_calls=[_tool_call("get_capability_schema", {"capability_name": "cap.a"})]
            ),
            _llm_response(
                content=_expand_json(steps=[{"id": "s1", "capability": "cap.a", "params": {}}])
            ),
        ]
        result = await svc.execute(_sketch_result(), _plan_request(), _ctx())
        assert result.steps[0].has_side_effects is True
        assert result.steps[0].timeout_ms == 500


# ===========================================================================
# 16. micro_execute()
# ===========================================================================


class TestMicroExecute:
    """micro_execute() runs abbreviated EXPAND for micro-replan."""

    async def test_happy_path(self, svc: ExpandService, llm: FakeLLMPort) -> None:
        llm.responses = [_llm_response(content=_expand_json())]
        result = await svc.micro_execute(_sketch_result(), {}, _ctx())
        assert isinstance(result, ExpandedPlan)

    async def test_failure_raises_expand_failed(self, svc: ExpandService, llm: FakeLLMPort) -> None:
        """micro_execute raises on failure (no fallback)."""
        llm.responses = [_llm_response(content="invalid json")]
        with pytest.raises(ExpandFailedError):
            await svc.micro_execute(_sketch_result(), {}, _ctx())

    async def test_completed_results_context_added(
        self, svc: ExpandService, llm: FakeLLMPort
    ) -> None:
        """Completed results are included in messages."""
        completed = {
            "s1": StepResult(
                step_id="s1",
                capability_name="cap.prev",
                status=StepStatus.COMPLETED,
            ),
        }
        llm.responses = [_llm_response(content=_expand_json())]
        await svc.micro_execute(_sketch_result(), completed, _ctx())
        # Check that completed results appear in messages
        msgs = llm.calls[0].payload["messages"]
        all_content = " ".join(m.get("content", "") for m in msgs)
        assert "cap.prev" in all_content

    async def test_uses_agentic_loop_with_tools(
        self, svc: ExpandService, llm: FakeLLMPort, router: FakeToolRouter
    ) -> None:
        """micro_execute uses the full agentic loop with tools."""
        llm.responses = [
            _llm_response(tool_calls=[_tool_call("discover_capabilities", {"intent": "replan"})]),
            _llm_response(content=_expand_json()),
        ]
        await svc.micro_execute(_sketch_result(), {}, _ctx())
        assert len(router.discover_calls) == 1
        # HubRequest should include tools
        assert "tools" in llm.calls[0].payload
