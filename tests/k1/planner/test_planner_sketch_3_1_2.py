"""Tests for SketchService agentic implementation (Issues 3.1.2-3.1.7).

Tests cover:
  - System prompt: role definition, output schema embedding
  - Initial messages: intent, constraints, HIL addendum
  - Tool definitions: 3 tools, correct structure
  - HubRequest construction: capability, payload, constraints
  - Tool call dispatch: routing to ToolCallRouter methods
  - Agentic loop: tool-calling rounds, final answer extraction
  - Response parsing: JSON -> SketchResult, edge cases
  - execute(): full pipeline with agentic loop
  - micro_execute(): abbreviated pipeline
  - HIL clarification: needs_clarification -> HIL flow -> re-run
  - Error recovery: retry with simplified prompt
  - SKETCH_OUTPUT_SCHEMA: valid JSON Schema structure

References
----------
- planner.md Section 6 (Stage 1 SKETCH Deep Dive)
- planner.md Section 11 (Discovery Tools)
- planner.md Section 12 (HIL Clarification)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from k1.orchestrator.types import MicroReplanRequest, PlanRequest
from k1.planner.stages.sketch_service import (
    _MAX_TOOL_ROUNDS,
    SKETCH_OUTPUT_SCHEMA,
    SKETCH_TOOL_DEFINITIONS,
    SketchService,
)
from k1.planner.types import (
    HubResponse,
    RequestConstraints,
    SketchFailedError,
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
        # Default: return empty content, no tool calls.
        return HubResponse(result={"content": ""}, metadata={})


class FakeToolRouter:
    """Configurable fake ToolCallRouter."""

    def __init__(self) -> None:
        self._tool_call_count: int = 0
        self.discover_results: List[Any] = [None]
        self.read_context_results: List[Dict[str, Any]] = [{}]
        self.recall_memory_results: List[Any] = [None]
        self.find_prompts_results: List[Any] = [None]
        self.discover_calls: List[Dict[str, Any]] = []
        self.read_context_calls: List[Dict[str, Any]] = []
        self.recall_memory_calls: List[Dict[str, Any]] = []
        self.find_prompts_calls: List[Dict[str, Any]] = []
        self._discover_idx: int = 0
        self._read_idx: int = 0
        self._recall_idx: int = 0
        self._find_prompts_idx: int = 0

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

    async def recall_memory(
        self,
        query: str,
        trace_id: str,
    ) -> Any:
        self._tool_call_count += 1
        self.recall_memory_calls.append({"query": query, "trace_id": trace_id})
        idx = min(self._recall_idx, len(self.recall_memory_results) - 1)
        self._recall_idx += 1
        return self.recall_memory_results[idx]

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


class FakeHILCoordinator:
    """E5: minimal IHILPort fake (renamed from FakeHILCoordinator).

    Exposes the unified k1.kernel.ports.hil_port.IHILPort surface.
    Default behaviour: ask_clarification times out; request_approval
    auto-approves. Tests that need other behaviour replace the
    `_clar_response` / `_approval_response` attributes.
    """

    def __init__(self) -> None:
        from k1.hil.types import ApprovalResponse, ClarificationResponse

        self._budget: dict[str, int] = {}
        self.clarification_calls: list = []
        self.approval_calls: list = []
        self.reset_calls: list[str] = []
        self._clar_response = ClarificationResponse(
            hil_request_id="fake",
            answer=None,
            timed_out=True,
            round_budget_exhausted=False,
        )
        self._approval_response = ApprovalResponse(
            hil_request_id="fake",
            decision="approve",
            modifications=None,
            timed_out=False,
        )

    async def ask_clarification(self, req):  # type: ignore[no-untyped-def]
        from k1.hil.types import ClarificationResponse

        self.clarification_calls.append(req)
        used = self._budget.get(req.caller_key, 0)
        if used >= 2:
            return ClarificationResponse(
                hil_request_id="",
                answer=None,
                timed_out=False,
                round_budget_exhausted=True,
            )
        self._budget[req.caller_key] = used + 1
        return self._clar_response

    async def request_approval(self, req):  # type: ignore[no-untyped-def]
        self.approval_calls.append(req)
        return self._approval_response

    async def needs_human(self, req):  # type: ignore[no-untyped-def]
        from k1.hil.types import NeedsHumanResponse

        return NeedsHumanResponse(
            hil_request_id="fake",
            decision="timeout",
            resolution={},
            raw_user_text=None,
            timed_out=True,
        )

    async def request_override(self, req):  # type: ignore[no-untyped-def]
        from k1.hil.types import OverrideResponse

        return OverrideResponse(
            hil_request_id="fake",
            choice="abort",
            selected_alternative=None,
            fallback_action=None,
            timed_out=True,
        )

    async def gate_capability(self, req):  # type: ignore[no-untyped-def]
        from k1.hil.types import GateDecision, GateOutcome

        return GateDecision(
            outcome=GateOutcome.ALLOW,
            hil_request_id=None,
            reason="fake_allow",
            user_approved=None,
            audit_only=False,
        )

    def reset_round_budget(self, caller_key: str) -> None:
        self.reset_calls.append(caller_key)
        self._budget.pop(caller_key, None)

    async def shutdown(self) -> None:
        return None


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
def hil() -> FakeHILCoordinator:
    return FakeHILCoordinator()


@pytest.fixture
def svc(llm: FakeLLMPort, router: FakeToolRouter, hil: FakeHILCoordinator) -> SketchService:
    return SketchService(llm_port=llm, tool_router=router, hil_port=hil)


def _ctx(*, cancel: bool = False) -> StageContext:
    return StageContext(
        request_id="req-001",
        trace_id="trace-001",
        timeout_remaining_ms=30000,
        token_budget_remaining=4096,
        cancel_check=lambda: cancel,
    )


def _plan_request(intent: str = "Book dinner for 4", **kwargs: Any) -> PlanRequest:
    return PlanRequest(intent=intent, trace_id="trace-001", **kwargs)


def _plan_json(
    steps: Optional[List[Dict[str, Any]]] = None,
    rationale: str = "Simple plan",
    needs_clarification: bool = False,
    clarification_question: str = "",
) -> str:
    """Build a valid SKETCH LLM output JSON."""
    data: Dict[str, Any] = {
        "rough_steps": steps or [{"intent": "Find restaurant"}],
        "rationale": rationale,
        "needs_clarification": needs_clarification,
    }
    if clarification_question:
        data["clarification_question"] = clarification_question
    return json.dumps(data)


def _llm_response(content: str = "", tool_calls: Optional[List[Any]] = None) -> HubResponse:
    """Build a HubResponse from content and optional tool_calls."""
    result: Dict[str, Any] = {"content": content}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return HubResponse(result=result, metadata={"usage": {"total_tokens": 100}})


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
# 1. SKETCH_OUTPUT_SCHEMA
# ===========================================================================


class TestSketchOutputSchema:
    """SKETCH_OUTPUT_SCHEMA is a valid JSON Schema with required fields."""

    def test_is_dict(self) -> None:
        assert isinstance(SKETCH_OUTPUT_SCHEMA, dict)

    def test_type_is_object(self) -> None:
        assert SKETCH_OUTPUT_SCHEMA["type"] == "object"

    def test_required_fields(self) -> None:
        required = SKETCH_OUTPUT_SCHEMA["required"]
        assert "rough_steps" in required
        assert "rationale" in required
        assert "needs_clarification" in required

    def test_additional_properties_false(self) -> None:
        assert SKETCH_OUTPUT_SCHEMA.get("additionalProperties") is False

    def test_rough_steps_is_array(self) -> None:
        assert SKETCH_OUTPUT_SCHEMA["properties"]["rough_steps"]["type"] == "array"

    def test_rough_steps_has_min_items(self) -> None:
        assert SKETCH_OUTPUT_SCHEMA["properties"]["rough_steps"]["minItems"] == 1

    def test_serializable_to_json(self) -> None:
        text = json.dumps(SKETCH_OUTPUT_SCHEMA)
        assert len(text) > 100


# ===========================================================================
# 2. SKETCH_TOOL_DEFINITIONS
# ===========================================================================


class TestSketchToolDefinitions:
    """SKETCH_TOOL_DEFINITIONS contains 4 properly structured tools."""

    def test_is_tuple(self) -> None:
        assert isinstance(SKETCH_TOOL_DEFINITIONS, tuple)

    def test_has_four_tools(self) -> None:
        assert len(SKETCH_TOOL_DEFINITIONS) == 4

    def test_all_are_function_type(self) -> None:
        for td in SKETCH_TOOL_DEFINITIONS:
            assert td["type"] == "function"

    def test_tool_names(self) -> None:
        names = {td["function"]["name"] for td in SKETCH_TOOL_DEFINITIONS}
        assert names == {
            "discover_capabilities",
            "query_session_context",
            "recall_long_term_memory",
            "find_prompts",
        }

    def test_discover_has_intent_param(self) -> None:
        discover = [
            t for t in SKETCH_TOOL_DEFINITIONS if t["function"]["name"] == "discover_capabilities"
        ][0]
        params = discover["function"]["parameters"]
        assert "intent" in params["properties"]
        assert "intent" in params["required"]

    def test_query_session_has_sections_param(self) -> None:
        query = [
            t for t in SKETCH_TOOL_DEFINITIONS if t["function"]["name"] == "query_session_context"
        ][0]
        params = query["function"]["parameters"]
        assert "sections" in params["properties"]

    def test_recall_has_query_param(self) -> None:
        recall = [
            t for t in SKETCH_TOOL_DEFINITIONS if t["function"]["name"] == "recall_long_term_memory"
        ][0]
        params = recall["function"]["parameters"]
        assert "query" in params["properties"]
        assert "query" in params["required"]

    def test_find_prompts_has_intent_param(self) -> None:
        fp = [t for t in SKETCH_TOOL_DEFINITIONS if t["function"]["name"] == "find_prompts"][0]
        params = fp["function"]["parameters"]
        assert "intent" in params["properties"]
        assert "intent" in params["required"]

    def test_find_prompts_has_optional_domain(self) -> None:
        fp = [t for t in SKETCH_TOOL_DEFINITIONS if t["function"]["name"] == "find_prompts"][0]
        params = fp["function"]["parameters"]
        assert "domain" in params["properties"]
        assert "domain" not in params["required"]

    def test_find_prompts_has_optional_top_k(self) -> None:
        fp = [t for t in SKETCH_TOOL_DEFINITIONS if t["function"]["name"] == "find_prompts"][0]
        params = fp["function"]["parameters"]
        assert "top_k" in params["properties"]
        assert "top_k" not in params["required"]


# ===========================================================================
# 3. System prompt
# ===========================================================================


class TestSystemPrompt:
    """_assemble_system_prompt builds a universal planning prompt."""

    def test_contains_planning_engine_role(self, svc: SketchService) -> None:
        prompt = svc._assemble_system_prompt()
        assert "planning engine" in prompt

    def test_contains_output_schema(self, svc: SketchService) -> None:
        prompt = svc._assemble_system_prompt()
        assert "rough_steps" in prompt
        assert "rationale" in prompt

    def test_mentions_discover_capabilities(self, svc: SketchService) -> None:
        prompt = svc._assemble_system_prompt()
        assert "discover_capabilities" in prompt

    def test_mentions_query_session_context(self, svc: SketchService) -> None:
        prompt = svc._assemble_system_prompt()
        assert "query_session_context" in prompt

    def test_mentions_recall_long_term_memory(self, svc: SketchService) -> None:
        prompt = svc._assemble_system_prompt()
        assert "recall_long_term_memory" in prompt

    def test_mentions_find_prompts(self, svc: SketchService) -> None:
        prompt = svc._assemble_system_prompt()
        assert "find_prompts" in prompt

    def test_mentions_json(self, svc: SketchService) -> None:
        prompt = svc._assemble_system_prompt()
        assert "JSON" in prompt

    def test_returns_string(self, svc: SketchService) -> None:
        assert isinstance(svc._assemble_system_prompt(), str)

    def test_not_empty(self, svc: SketchService) -> None:
        assert len(svc._assemble_system_prompt()) > 100


# ===========================================================================
# 4. Initial messages
# ===========================================================================


class TestBuildInitialMessages:
    """_build_initial_messages constructs system + user messages."""

    def test_returns_list_of_two(self, svc: SketchService) -> None:
        msgs = svc._build_initial_messages(intent="Test")
        assert len(msgs) == 2

    def test_first_is_system(self, svc: SketchService) -> None:
        msgs = svc._build_initial_messages(intent="Test")
        assert msgs[0]["role"] == "system"

    def test_second_is_user(self, svc: SketchService) -> None:
        msgs = svc._build_initial_messages(intent="Test")
        assert msgs[1]["role"] == "user"

    def test_user_contains_intent(self, svc: SketchService) -> None:
        msgs = svc._build_initial_messages(intent="Book a flight")
        assert "Book a flight" in msgs[1]["content"]

    def test_no_constraints_no_context_line(self, svc: SketchService) -> None:
        msgs = svc._build_initial_messages(intent="Test")
        assert "[Context:" not in msgs[1]["content"]

    def test_safety_band_included(self, svc: SketchService) -> None:
        msgs = svc._build_initial_messages(
            intent="Test",
            constraints={"safety_band": "YELLOW"},
        )
        assert "YELLOW" in msgs[1]["content"]

    def test_green_safety_band_omitted(self, svc: SketchService) -> None:
        msgs = svc._build_initial_messages(
            intent="Test",
            constraints={"safety_band": "GREEN"},
        )
        assert "[Context:" not in msgs[1]["content"]

    def test_temporal_now_included(self, svc: SketchService) -> None:
        msgs = svc._build_initial_messages(
            intent="Test",
            constraints={"temporal": {"now": "2025-01-15T10:00:00Z"}},
        )
        assert "2025-01-15" in msgs[1]["content"]

    def test_timezone_included(self, svc: SketchService) -> None:
        msgs = svc._build_initial_messages(
            intent="Test",
            constraints={"temporal": {"device_tz": "US/Eastern"}},
        )
        assert "US/Eastern" in msgs[1]["content"]

    def test_hil_addendum_appended(self, svc: SketchService) -> None:
        msgs = svc._build_initial_messages(
            intent="Test",
            hil_addendum="4 people, Saturday night",
        )
        assert "4 people, Saturday night" in msgs[1]["content"]
        assert "[User clarification:" in msgs[1]["content"]

    def test_hil_addendum_none_not_appended(self, svc: SketchService) -> None:
        msgs = svc._build_initial_messages(intent="Test", hil_addendum=None)
        assert "[User clarification:" not in msgs[1]["content"]


# ===========================================================================
# 5. Tool definitions getter
# ===========================================================================


class TestGetToolDefinitions:
    """_get_tool_definitions returns SKETCH_TOOL_DEFINITIONS."""

    def test_returns_same_as_module_constant(self, svc: SketchService) -> None:
        assert svc._get_tool_definitions() is SKETCH_TOOL_DEFINITIONS

    def test_not_static_method(self) -> None:
        """_get_tool_definitions is a regular method, not @staticmethod."""
        assert not isinstance(
            SketchService.__dict__.get("_get_tool_definitions"),
            staticmethod,
        )


# ===========================================================================
# 6. HubRequest construction
# ===========================================================================


class TestBuildHubRequest:
    """_build_hub_request creates a properly structured HubRequest."""

    def test_capability_is_chat(self, svc: SketchService) -> None:
        msgs = [{"role": "system", "content": "test"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.capability == "CHAT"

    def test_payload_contains_messages(self, svc: SketchService) -> None:
        msgs = [{"role": "system", "content": "test"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.payload["messages"] is msgs

    def test_payload_contains_temperature(self, svc: SketchService) -> None:
        msgs = [{"role": "system", "content": "test"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.payload["temperature"] == 0.7

    def test_tools_included_when_provided(self, svc: SketchService) -> None:
        msgs = [{"role": "system", "content": "test"}]
        tools = SKETCH_TOOL_DEFINITIONS
        req = svc._build_hub_request(msgs, _ctx(), tools=tools)
        assert "tools" in req.payload
        assert len(req.payload["tools"]) == 4

    def test_no_tools_when_none(self, svc: SketchService) -> None:
        msgs = [{"role": "system", "content": "test"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert "tools" not in req.payload

    def test_trace_id_propagated(self, svc: SketchService) -> None:
        msgs = [{"role": "system", "content": "test"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.trace_id == "trace-001"

    def test_constraints_have_max_tokens(self, svc: SketchService) -> None:
        msgs = [{"role": "system", "content": "test"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.constraints.max_tokens > 0

    def test_constraints_consumer_is_planner(self, svc: SketchService) -> None:
        msgs = [{"role": "system", "content": "test"}]
        req = svc._build_hub_request(msgs, _ctx())
        assert req.constraints.consumer_id == "planner"

    def test_stage_budget_used_when_present(self, svc: SketchService) -> None:
        budget = RequestConstraints(max_tokens=1024, timeout_ms=5000)
        ctx = StageContext(
            request_id="req-001",
            trace_id="trace-001",
            timeout_remaining_ms=30000,
            token_budget_remaining=4096,
            cancel_check=lambda: False,
            stage_budget=budget,
        )
        msgs = [{"role": "system", "content": "test"}]
        req = svc._build_hub_request(msgs, ctx)
        assert req.constraints.max_tokens == 1024
        assert req.constraints.timeout_ms == 5000


# ===========================================================================
# 7. Tool call dispatch
# ===========================================================================


class TestDispatchToolCall:
    """_dispatch_tool_call routes tool names to ToolCallRouter methods."""

    @pytest.mark.asyncio
    async def test_dispatch_discover(self, svc: SketchService, router: FakeToolRouter) -> None:
        tc = _tool_call("discover_capabilities", {"intent": "find food"})
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert len(router.discover_calls) == 1
        assert router.discover_calls[0]["intent"] == "find food"

    @pytest.mark.asyncio
    async def test_dispatch_discover_with_domain(
        self, svc: SketchService, router: FakeToolRouter
    ) -> None:
        tc = _tool_call("discover_capabilities", {"intent": "book", "domain": "dining"})
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert router.discover_calls[0]["domain"] == "dining"

    @pytest.mark.asyncio
    async def test_dispatch_query_session(self, svc: SketchService, router: FakeToolRouter) -> None:
        tc = _tool_call("query_session_context", {"sections": ["persona", "temporal"]})
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert len(router.read_context_calls) == 1
        assert router.read_context_calls[0]["sections"] == ["persona", "temporal"]

    @pytest.mark.asyncio
    async def test_dispatch_recall_memory(self, svc: SketchService, router: FakeToolRouter) -> None:
        tc = _tool_call("recall_long_term_memory", {"query": "dinner preferences"})
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert len(router.recall_memory_calls) == 1
        assert router.recall_memory_calls[0]["query"] == "dinner preferences"

    @pytest.mark.asyncio
    async def test_dispatch_find_prompts(self, svc: SketchService, router: FakeToolRouter) -> None:
        tc = _tool_call("find_prompts", {"intent": "summarise email"})
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert len(router.find_prompts_calls) == 1
        assert router.find_prompts_calls[0]["intent"] == "summarise email"

    @pytest.mark.asyncio
    async def test_dispatch_find_prompts_with_domain(
        self, svc: SketchService, router: FakeToolRouter
    ) -> None:
        tc = _tool_call(
            "find_prompts", {"intent": "draft reply", "domain": "messaging", "top_k": 3}
        )
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert router.find_prompts_calls[0]["domain"] == "messaging"
        assert router.find_prompts_calls[0]["top_k"] == 3

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool_returns_error(self, svc: SketchService) -> None:
        tc = _tool_call("unknown_tool", {})
        result = await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert isinstance(result, dict)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_dispatch_handles_exception(self, svc: SketchService) -> None:
        """Tool router exceptions are caught and returned as error dicts."""

        class FailingRouter(FakeToolRouter):
            async def discover(self, intent: str, **kwargs: Any) -> Any:
                raise RuntimeError("connection lost")

        fail_svc = SketchService(
            llm_port=FakeLLMPort(),
            tool_router=FailingRouter(),
            hil_port=FakeHILCoordinator(),
        )
        tc = _tool_call("discover_capabilities", {"intent": "test"})
        result = await fail_svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        assert "error" in result
        assert "connection lost" in result["error"]

    @pytest.mark.asyncio
    async def test_dispatch_handles_bad_json_args(self, svc: SketchService) -> None:
        """Malformed arguments JSON is handled gracefully (no exception)."""
        tc = {
            "id": "tc-1",
            "function": {
                "name": "discover_capabilities",
                "arguments": "not valid json {{",
            },
        }
        # Should not raise -- falls back to empty args and calls discover.
        await svc._dispatch_tool_call(tc, _plan_request(), _ctx())
        # Reaching here means no exception was raised despite the bad JSON.


# ===========================================================================
# 8. Response parsing
# ===========================================================================


class TestParseResponse:
    """_parse_response converts LLM JSON to (SketchResult, bool, str)."""

    def test_parses_valid_json(self, svc: SketchService) -> None:
        content = _plan_json()
        result, needs_hil, question = svc._parse_response(content, [])
        assert isinstance(result, SketchResult)
        assert not needs_hil
        assert question == ""

    def test_extracts_rough_steps(self, svc: SketchService) -> None:
        content = _plan_json(
            steps=[
                {"intent": "Step 1"},
                {"intent": "Step 2"},
            ]
        )
        result, _, _ = svc._parse_response(content, [])
        assert len(result.rough_steps) == 2
        assert result.rough_steps[0].intent == "Step 1"

    def test_extracts_rationale(self, svc: SketchService) -> None:
        content = _plan_json(rationale="Because reasons")
        result, _, _ = svc._parse_response(content, [])
        assert result.rationale == "Because reasons"

    def test_needs_clarification_flag(self, svc: SketchService) -> None:
        content = _plan_json(
            needs_clarification=True,
            clarification_question="How many people?",
        )
        _, needs_hil, question = svc._parse_response(content, [])
        assert needs_hil is True
        assert question == "How many people?"

    def test_strips_markdown_fences(self, svc: SketchService) -> None:
        raw = "```json\n" + _plan_json() + "\n```"
        result, _, _ = svc._parse_response(raw, [])
        assert isinstance(result, SketchResult)

    def test_invalid_json_raises(self, svc: SketchService) -> None:
        with pytest.raises(SketchFailedError, match="not valid JSON"):
            svc._parse_response("not json at all", [])

    def test_empty_steps_raises(self, svc: SketchService) -> None:
        content = json.dumps({"rough_steps": [], "rationale": "x", "needs_clarification": False})
        with pytest.raises(SketchFailedError, match="empty rough_steps"):
            svc._parse_response(content, [])

    def test_missing_rationale_raises(self, svc: SketchService) -> None:
        content = json.dumps(
            {
                "rough_steps": [{"intent": "do something"}],
                "rationale": "",
                "needs_clarification": False,
            }
        )
        with pytest.raises(SketchFailedError, match="missing rationale"):
            svc._parse_response(content, [])

    def test_non_object_raises(self, svc: SketchService) -> None:
        with pytest.raises(SketchFailedError, match="JSON object"):
            svc._parse_response("[1, 2, 3]", [])

    def test_depends_on_resolved_to_intents(self, svc: SketchService) -> None:
        content = _plan_json(
            steps=[
                {"intent": "First"},
                {"intent": "Second", "depends_on": [0]},
            ]
        )
        result, _, _ = svc._parse_response(content, [])
        assert result.rough_steps[1].depends_on == ["First"]

    def test_out_of_range_depends_on_ignored(self, svc: SketchService) -> None:
        content = _plan_json(
            steps=[
                {"intent": "Only step", "depends_on": [99]},
            ]
        )
        result, _, _ = svc._parse_response(content, [])
        assert result.rough_steps[0].depends_on == []


# ===========================================================================
# 9. Agentic loop
# ===========================================================================


class TestAgenticLoop:
    """_run_agentic_loop manages the LLM <-> tool calling conversation."""

    @pytest.mark.asyncio
    async def test_direct_answer_no_tools(self, svc: SketchService, llm: FakeLLMPort) -> None:
        """LLM immediately returns JSON without calling tools."""
        llm.responses = [_llm_response(content=_plan_json())]
        msgs = svc._build_initial_messages(intent="Test")
        content, discoveries = await svc._run_agentic_loop(msgs, _plan_request(), _ctx())
        assert "rough_steps" in content
        assert discoveries == []

    @pytest.mark.asyncio
    async def test_one_tool_round_then_answer(self, svc: SketchService, llm: FakeLLMPort) -> None:
        """LLM calls one tool, then produces final answer."""
        llm.responses = [
            # Round 1: LLM calls discover_capabilities.
            _llm_response(
                content="",
                tool_calls=[_tool_call("discover_capabilities", {"intent": "food"})],
            ),
            # Round 2: LLM produces final JSON.
            _llm_response(content=_plan_json()),
        ]
        msgs = svc._build_initial_messages(intent="Test")
        content, discoveries = await svc._run_agentic_loop(msgs, _plan_request(), _ctx())
        assert "rough_steps" in content
        assert len(llm.calls) == 2

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_per_round(
        self, svc: SketchService, llm: FakeLLMPort
    ) -> None:
        """LLM calls multiple tools in a single round."""
        llm.responses = [
            _llm_response(
                content="",
                tool_calls=[
                    _tool_call("discover_capabilities", {"intent": "food"}, "tc-1"),
                    _tool_call("query_session_context", {"sections": ["persona"]}, "tc-2"),
                ],
            ),
            _llm_response(content=_plan_json()),
        ]
        msgs = svc._build_initial_messages(intent="Test")
        content, _ = await svc._run_agentic_loop(msgs, _plan_request(), _ctx())
        assert "rough_steps" in content

    @pytest.mark.asyncio
    async def test_discovery_results_accumulated(
        self, svc: SketchService, llm: FakeLLMPort, router: FakeToolRouter
    ) -> None:
        """Discovery tool results are accumulated and returned."""
        router.discover_results = ["discovery-result-1"]
        llm.responses = [
            _llm_response(
                content="",
                tool_calls=[_tool_call("discover_capabilities", {"intent": "food"})],
            ),
            _llm_response(content=_plan_json()),
        ]
        msgs = svc._build_initial_messages(intent="Test")
        _, discoveries = await svc._run_agentic_loop(msgs, _plan_request(), _ctx())
        assert len(discoveries) == 1

    @pytest.mark.asyncio
    async def test_cancellation_check(self, svc: SketchService, llm: FakeLLMPort) -> None:
        """Cancelled context raises SketchFailedError."""
        llm.responses = [_llm_response(content=_plan_json())]
        msgs = svc._build_initial_messages(intent="Test")
        ctx = _ctx(cancel=True)
        with pytest.raises(SketchFailedError, match="cancelled"):
            await svc._run_agentic_loop(msgs, _plan_request(), ctx)

    @pytest.mark.asyncio
    async def test_empty_content_no_tools_raises(
        self, svc: SketchService, llm: FakeLLMPort
    ) -> None:
        """Empty content with no tool calls raises SketchFailedError."""
        llm.responses = [_llm_response(content="", tool_calls=None)]
        msgs = svc._build_initial_messages(intent="Test")
        with pytest.raises(SketchFailedError, match="empty response"):
            await svc._run_agentic_loop(msgs, _plan_request(), _ctx())

    @pytest.mark.asyncio
    async def test_round_limit_exhausted_raises(self, svc: SketchService, llm: FakeLLMPort) -> None:
        """Hitting the max tool rounds without a final answer raises."""
        # Return tool calls every time.
        llm.responses = [
            _llm_response(
                content="",
                tool_calls=[_tool_call("discover_capabilities", {"intent": "x"})],
            )
        ] * (_MAX_TOOL_ROUNDS + 1)
        msgs = svc._build_initial_messages(intent="Test")
        with pytest.raises(SketchFailedError, match="tool-calling rounds"):
            await svc._run_agentic_loop(msgs, _plan_request(), _ctx())

    @pytest.mark.asyncio
    async def test_tool_results_added_to_messages(
        self, svc: SketchService, llm: FakeLLMPort
    ) -> None:
        """Tool results are appended as 'tool' role messages."""
        llm.responses = [
            _llm_response(
                content="",
                tool_calls=[_tool_call("discover_capabilities", {"intent": "x"}, "tc-1")],
            ),
            _llm_response(content=_plan_json()),
        ]
        msgs = svc._build_initial_messages(intent="Test")
        await svc._run_agentic_loop(msgs, _plan_request(), _ctx())
        # After loop, messages should have assistant + tool entries.
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "tc-1"

    @pytest.mark.asyncio
    async def test_no_tools_mode(self, svc: SketchService, llm: FakeLLMPort) -> None:
        """use_tools=False sends no tool definitions."""
        llm.responses = [_llm_response(content=_plan_json())]
        msgs = svc._build_initial_messages(intent="Test")
        await svc._run_agentic_loop(msgs, _plan_request(), _ctx(), use_tools=False)
        # The HubRequest should not have tools in payload.
        assert "tools" not in llm.calls[0].payload


# ===========================================================================
# 10. execute() -- full pipeline
# ===========================================================================


class TestExecute:
    """execute() runs the complete SKETCH pipeline."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_sketch_result(
        self, svc: SketchService, llm: FakeLLMPort
    ) -> None:
        llm.responses = [_llm_response(content=_plan_json())]
        result = await svc.execute(_plan_request(), _ctx())
        assert isinstance(result, SketchResult)
        assert len(result.rough_steps) == 1

    @pytest.mark.asyncio
    async def test_rationale_preserved(self, svc: SketchService, llm: FakeLLMPort) -> None:
        llm.responses = [_llm_response(content=_plan_json(rationale="My reasoning"))]
        result = await svc.execute(_plan_request(), _ctx())
        assert result.rationale == "My reasoning"

    @pytest.mark.asyncio
    async def test_multi_step_plan(self, svc: SketchService, llm: FakeLLMPort) -> None:
        llm.responses = [
            _llm_response(
                content=_plan_json(
                    steps=[
                        {"intent": "Search restaurants"},
                        {"intent": "Book table", "depends_on": [0]},
                        {"intent": "Send confirmation"},
                    ]
                )
            )
        ]
        result = await svc.execute(_plan_request(), _ctx())
        assert len(result.rough_steps) == 3

    @pytest.mark.asyncio
    async def test_execute_with_tool_round(
        self, svc: SketchService, llm: FakeLLMPort, router: FakeToolRouter
    ) -> None:
        """LLM calls discover, then produces plan."""
        llm.responses = [
            _llm_response(
                content="",
                tool_calls=[_tool_call("discover_capabilities", {"intent": "dining"})],
            ),
            _llm_response(content=_plan_json()),
        ]
        result = await svc.execute(_plan_request(), _ctx())
        assert isinstance(result, SketchResult)
        assert len(router.discover_calls) == 1


# ===========================================================================
# 11. Error recovery
# ===========================================================================


class TestErrorRecovery:
    """execute() retries with simplified prompt on failure."""

    @pytest.mark.asyncio
    async def test_retry_on_first_failure(self, svc: SketchService, llm: FakeLLMPort) -> None:
        """First attempt fails, retry succeeds."""
        llm.responses = [
            # First attempt: LLM returns empty (will raise).
            _llm_response(content=""),
            # Retry (simplified): LLM returns valid plan.
            _llm_response(content=_plan_json()),
        ]
        result = await svc.execute(_plan_request(), _ctx())
        assert isinstance(result, SketchResult)

    @pytest.mark.asyncio
    async def test_both_attempts_fail_raises(self, svc: SketchService, llm: FakeLLMPort) -> None:
        """Both attempts fail -> SketchFailedError."""
        llm.responses = [
            _llm_response(content=""),
            _llm_response(content=""),
        ]
        with pytest.raises(SketchFailedError, match="failed after retry"):
            await svc.execute(_plan_request(), _ctx())

    @pytest.mark.asyncio
    async def test_retry_uses_simplified_mode(self, svc: SketchService, llm: FakeLLMPort) -> None:
        """Retry attempt should not include tool definitions."""
        llm.responses = [
            _llm_response(content=""),
            _llm_response(content=_plan_json()),
        ]
        await svc.execute(_plan_request(), _ctx())
        # First call has tools, second (retry) should not.
        assert "tools" in llm.calls[0].payload
        assert "tools" not in llm.calls[1].payload


# ===========================================================================
# 12. HIL clarification
# ===========================================================================


class TestHILClarification:
    """HIL clarification flow when LLM sets needs_clarification=True."""

    @pytest.mark.asyncio
    async def test_hil_triggered_on_needs_clarification(
        self, svc: SketchService, llm: FakeLLMPort, hil: FakeHILCoordinator
    ) -> None:
        """When LLM says needs_clarification, HIL is invoked."""
        hil.response = "4 people on Saturday"
        llm.responses = [
            # First: needs clarification.
            _llm_response(
                content=_plan_json(
                    needs_clarification=True,
                    clarification_question="How many people?",
                )
            ),
            # After clarification: valid plan.
            _llm_response(content=_plan_json()),
        ]
        result = await svc.execute(_plan_request(), _ctx())
        assert isinstance(result, SketchResult)
        assert len(hil.clarification_calls) == 1
        # E5: round-budget reset moved to PipelineController.execute(); no
        # longer triggered by SketchService.

    @pytest.mark.asyncio
    async def test_hil_response_included_in_retry(
        self, svc: SketchService, llm: FakeLLMPort, hil: FakeHILCoordinator
    ) -> None:
        """User clarification text is included in the re-run messages."""
        from k1.hil.types import ClarificationResponse

        hil._clar_response = ClarificationResponse(
            hil_request_id="fake",
            answer="Italian restaurant",
            timed_out=False,
            round_budget_exhausted=False,
        )
        llm.responses = [
            _llm_response(
                content=_plan_json(
                    needs_clarification=True,
                    clarification_question="What cuisine?",
                )
            ),
            _llm_response(content=_plan_json()),
        ]
        await svc.execute(_plan_request(), _ctx())
        # Second LLM call should have the clarification in messages.
        second_call = llm.calls[1]
        user_msgs = [m for m in second_call.payload["messages"] if m["role"] == "user"]
        assert any("Italian restaurant" in m["content"] for m in user_msgs)

    @pytest.mark.asyncio
    async def test_hil_none_response_skips_rerun(
        self, svc: SketchService, llm: FakeLLMPort, hil: FakeHILCoordinator
    ) -> None:
        """If HIL returns None (timeout), proceed with original result."""
        hil.response = None
        llm.responses = [
            _llm_response(
                content=_plan_json(
                    needs_clarification=True,
                    clarification_question="How many?",
                )
            ),
        ]
        result = await svc.execute(_plan_request(), _ctx())
        assert isinstance(result, SketchResult)
        assert len(llm.calls) == 1  # No re-run.

    @pytest.mark.asyncio
    async def test_no_hil_when_not_needed(
        self, svc: SketchService, llm: FakeLLMPort, hil: FakeHILCoordinator
    ) -> None:
        """No HIL call when needs_clarification is False."""
        llm.responses = [_llm_response(content=_plan_json())]
        await svc.execute(_plan_request(), _ctx())
        assert len(hil.clarification_calls) == 0


# ===========================================================================
# 13. micro_execute()
# ===========================================================================


class TestMicroExecute:
    """micro_execute() runs abbreviated SKETCH for micro-replan."""

    def _micro_request(self) -> MicroReplanRequest:
        from k1.orchestrator.types import PlanStep

        return MicroReplanRequest(
            original_plan_id="plan-001",
            completed_results={},
            remaining_steps=[
                PlanStep(
                    id="step-2",
                    capability="send_notification",
                ),
            ],
            trace_id="trace-micro",
        )

    @pytest.mark.asyncio
    async def test_returns_sketch_result(self, svc: SketchService, llm: FakeLLMPort) -> None:
        llm.responses = [_llm_response(content=_plan_json())]
        result = await svc.micro_execute(self._micro_request(), _ctx())
        assert isinstance(result, SketchResult)

    @pytest.mark.asyncio
    async def test_failure_raises_sketch_failed(self, svc: SketchService, llm: FakeLLMPort) -> None:
        llm.responses = [_llm_response(content="")]
        with pytest.raises(SketchFailedError):
            await svc.micro_execute(self._micro_request(), _ctx())

    @pytest.mark.asyncio
    async def test_intent_includes_remaining_steps(
        self, svc: SketchService, llm: FakeLLMPort
    ) -> None:
        llm.responses = [_llm_response(content=_plan_json())]
        await svc.micro_execute(self._micro_request(), _ctx())
        # Check that the LLM was called with intent mentioning remaining steps.
        call = llm.calls[0]
        user_msg = [m for m in call.payload["messages"] if m["role"] == "user"][0]
        assert "send_notification" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_micro_includes_failure_context(
        self, svc: SketchService, llm: FakeLLMPort
    ) -> None:
        from k1.orchestrator.types import FailureContext, PlanStep

        req = MicroReplanRequest(
            original_plan_id="plan-001",
            completed_results={},
            remaining_steps=[
                PlanStep(id="step-2", capability="retry_op"),
            ],
            trace_id="trace-micro",
            failure_context=FailureContext(
                step_id="step-1",
                error_code="TIMEOUT",
                error_message="Operation timed out",
            ),
        )
        llm.responses = [_llm_response(content=_plan_json())]
        await svc.micro_execute(req, _ctx())
        user_msg = [m for m in llm.calls[0].payload["messages"] if m["role"] == "user"][0]
        assert "timed out" in user_msg["content"]


# ===========================================================================
# 14. No static methods
# ===========================================================================


class TestNoStaticMethods:
    """SketchService should have no @staticmethod decorators."""

    def test_no_static_methods(self) -> None:
        import inspect as insp

        for name, method in insp.getmembers(SketchService):
            if name.startswith("_") and not name.startswith("__"):
                cls_attr = SketchService.__dict__.get(name)
                assert not isinstance(
                    cls_attr, staticmethod
                ), f"SketchService.{name} should not be @staticmethod"


# ===========================================================================
# 15. Module-level constants
# ===========================================================================


class TestModuleConstants:
    """Module-level constants are accessible and correct."""

    def test_max_tool_rounds_is_positive(self) -> None:
        assert _MAX_TOOL_ROUNDS > 0

    def test_max_tool_rounds_reasonable(self) -> None:
        assert _MAX_TOOL_ROUNDS <= 10

    def test_sketch_output_schema_importable(self) -> None:
        from k1.planner.stages.sketch_service import SKETCH_OUTPUT_SCHEMA as _S

        assert _S is SKETCH_OUTPUT_SCHEMA

    def test_sketch_tool_definitions_importable(self) -> None:
        from k1.planner.stages.sketch_service import SKETCH_TOOL_DEFINITIONS as _T

        assert _T is SKETCH_TOOL_DEFINITIONS
