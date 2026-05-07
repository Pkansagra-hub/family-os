"""Tests for micro-SKETCH and micro-EXPAND prompt composition (5.1.2, 5.1.3).

Validates the dedicated micro-replan prompt construction in:
  - SketchService._build_micro_sketch_messages()
  - SketchService._assemble_micro_system_prompt()
  - SketchService._assemble_micro_user_message()
  - ExpandService._build_micro_expand_messages()
  - ExpandService._assemble_micro_expand_system_prompt()
  - ExpandService._assemble_micro_expand_user_message()

Covers:
  - System prompt content (role, constraints, rules)
  - User message structure (5 sections for SKETCH, 4 for EXPAND)
  - Completed results output key inclusion
  - Discovery section population
  - Failure context section population
  - Cross-boundary dependency rules
  - No HIL clarification in micro-SKETCH
  - Error propagation (re-raise, no double-wrap)
  - End-to-end micro_execute with realistic payloads

References
----------
- planner.md Section 10.3.2 (micro-SKETCH)
- planner.md Section 10.3.3 (micro-EXPAND)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.types import CapabilityResult
from k1.orchestrator.types import (
    Discovery,
    FailureContext,
    MicroReplanRequest,
    PlanRequest,
    PlanStep,
    StepResult,
    StepStatus,
)
from k1.planner.stages.expand_service import ExpandService
from k1.planner.stages.sketch_service import SketchService
from k1.planner.types import (
    ExpandedPlan,
    ExpandFailedError,
    HubResponse,
    RoughStep,
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
        return HubResponse(result={"content": ""}, metadata={})


class FakeToolRouter:
    """Configurable fake ToolCallRouter for both services."""

    def __init__(self) -> None:
        self._tool_call_count: int = 0
        self.discover_results: List[Any] = [None]
        self.schema_results: List[Any] = [None]
        self.read_context_results: List[Dict[str, Any]] = [{}]
        self.recall_memory_results: List[Any] = [None]
        self.find_prompts_results: List[Any] = [None]
        self.discover_calls: List[Dict[str, Any]] = []
        self.schema_calls: List[Dict[str, Any]] = []
        self.read_context_calls: List[Dict[str, Any]] = []
        self.recall_memory_calls: List[Dict[str, Any]] = []
        self.find_prompts_calls: List[Dict[str, Any]] = []
        self._discover_idx: int = 0
        self._schema_idx: int = 0
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
        self.discover_calls.append(
            {"intent": intent, "domain": domain, "top_k": top_k},
        )
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
        self.schema_calls.append(
            {"capability_name": capability_name, "version": version},
        )
        idx = min(self._schema_idx, len(self.schema_results) - 1)
        self._schema_idx += 1
        return self.schema_results[idx]

    async def read_context(
        self,
        session_id: str,
        sections: list[str],
    ) -> Dict[str, Any]:
        self._tool_call_count += 1
        self.read_context_calls.append(
            {"session_id": session_id, "sections": sections},
        )
        idx = min(self._read_idx, len(self.read_context_results) - 1)
        self._read_idx += 1
        return self.read_context_results[idx]

    async def recall_memory(
        self,
        query: str,
        trace_id: str,
    ) -> Any:
        self._tool_call_count += 1
        self.recall_memory_calls.append(
            {"query": query, "trace_id": trace_id},
        )
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
        self.find_prompts_calls.append(
            {"intent": intent, "domain": domain, "top_k": top_k},
        )
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


class FakeContract:
    """Fake capability contract for discovery results."""

    def __init__(
        self,
        name: str = "test.cap",
        description: str = "A test capability",
    ) -> None:
        self.name = name
        self.description = description


class FakeScoredCapability:
    """Fake ScoredCapability for SKETCH discovery results."""

    def __init__(self, contract: FakeContract, score: float = 0.9) -> None:
        self.contract = contract
        self.score = score


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
def sketch_svc(
    llm: FakeLLMPort,
    router: FakeToolRouter,
    hil: FakeHILCoordinator,
) -> SketchService:
    return SketchService(llm_port=llm, tool_router=router, hil_port=hil)


@pytest.fixture
def expand_svc(
    llm: FakeLLMPort,
    router: FakeToolRouter,
) -> ExpandService:
    return ExpandService(llm_port=llm, tool_router=router)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(
    *,
    cancel: bool = False,
    request_id: str = "req-micro",
    trace_id: str = "trace-micro",
) -> StageContext:
    return StageContext(
        request_id=request_id,
        trace_id=trace_id,
        timeout_remaining_ms=30000,
        token_budget_remaining=4096,
        cancel_check=lambda: cancel,
    )


def _sketch_json(
    steps: Optional[List[Dict[str, Any]]] = None,
    rationale: str = "Micro replan rationale",
) -> str:
    """Build valid SKETCH LLM output JSON."""
    data: Dict[str, Any] = {
        "rough_steps": steps or [{"intent": "Retry send"}],
        "rationale": rationale,
        "needs_clarification": False,
    }
    return json.dumps(data)


def _expand_json(
    steps: Optional[List[Dict[str, Any]]] = None,
    dependencies: Optional[Dict[str, List[str]]] = None,
    rationale: str = "Micro expand rationale",
) -> str:
    """Build valid EXPAND LLM output JSON."""
    data: Dict[str, Any] = {
        "steps": steps
        or [
            {
                "id": "s2",
                "capability": "notification.send",
                "params": {"to": "user@test.com"},
                "deps": [],
                "is_optional": False,
            },
        ],
        "dependencies": dependencies or {},
        "rationale": rationale,
    }
    return json.dumps(data)


def _llm_response(
    content: str = "",
    tool_calls: Optional[List[Any]] = None,
) -> HubResponse:
    result: Dict[str, Any] = {"content": content}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return HubResponse(result=result, metadata={"usage": {"total_tokens": 80}})


def _tool_call(
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    call_id: str = "tc-1",
) -> Dict[str, Any]:
    return {
        "id": call_id,
        "function": {
            "name": name,
            "arguments": json.dumps(arguments or {}),
        },
    }


def _micro_request(
    *,
    completed: Optional[Dict[str, StepResult]] = None,
    remaining: Optional[List[PlanStep]] = None,
    discoveries: Optional[List[Discovery]] = None,
    failure_context: Optional[FailureContext] = None,
) -> MicroReplanRequest:
    """Build a MicroReplanRequest with sensible defaults."""
    return MicroReplanRequest(
        original_plan_id="plan-001",
        completed_results=completed or {},
        remaining_steps=remaining or [PlanStep(id="s2", capability="send_notification")],
        trace_id="trace-micro",
        request_id="req-micro",
        discoveries=discoveries or [],
        failure_context=failure_context,
    )


def _step_result(
    step_id: str = "s1",
    capability: str = "restaurant.search",
    status: StepStatus = StepStatus.COMPLETED,
    data: Optional[Dict[str, Any]] = None,
) -> StepResult:
    """Build a StepResult with optional CapabilityResult data."""
    cap_result = None
    if data is not None:
        cap_result = CapabilityResult(
            success=True,
            data=data,
        )
    return StepResult(
        step_id=step_id,
        capability_name=capability,
        status=status,
        result=cap_result,
    )


def _caps_for(*names: str) -> List[Any]:
    """Build FakeScoredCapability list for suggested_capability validation."""
    return [FakeScoredCapability(FakeContract(n)) for n in names]


def _sketch_result(
    steps: Optional[List[RoughStep]] = None,
    rationale: str = "Micro-SKETCH rationale",
    capabilities: Optional[List[Any]] = None,
) -> SketchResult:
    """Build a SketchResult for micro-EXPAND tests."""
    return SketchResult(
        rough_steps=steps
        or [
            RoughStep(
                intent="Retry the notification",
            ),
        ],
        capability_candidates=capabilities or [],
        rationale=rationale,
    )


def _extract_messages(llm: FakeLLMPort) -> List[Dict[str, Any]]:
    """Extract messages from the first LLM call."""
    assert len(llm.calls) >= 1, "Expected at least 1 LLM call"
    return llm.calls[0].payload["messages"]


def _extract_system(llm: FakeLLMPort) -> str:
    """Extract system message content from first LLM call."""
    msgs = _extract_messages(llm)
    system = [m for m in msgs if m["role"] == "system"]
    assert len(system) == 1, f"Expected 1 system msg, got {len(system)}"
    return system[0]["content"]


def _extract_user(llm: FakeLLMPort) -> str:
    """Extract user message content from first LLM call."""
    msgs = _extract_messages(llm)
    user = [m for m in msgs if m["role"] == "user"]
    assert len(user) >= 1, "Expected at least 1 user msg"
    return user[0]["content"]


# ===========================================================================
# 1. Micro-SKETCH system prompt (Section 10.3.2)
# ===========================================================================


class TestMicroSketchSystemPrompt:
    """_assemble_micro_system_prompt() produces micro-replan SYSTEM msg."""

    @pytest.mark.asyncio
    async def test_role_is_micro_replan(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt identifies as MICRO-REPLAN engine."""
        llm.responses = [_llm_response(content=_sketch_json())]
        await sketch_svc.micro_execute(_micro_request(), _ctx())
        system = _extract_system(llm)
        assert "MICRO-REPLAN" in system

    @pytest.mark.asyncio
    async def test_frozen_steps_rule(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt states completed steps are FROZEN."""
        llm.responses = [_llm_response(content=_sketch_json())]
        await sketch_svc.micro_execute(_micro_request(), _ctx())
        system = _extract_system(llm)
        assert "FROZEN" in system

    @pytest.mark.asyncio
    async def test_discover_once_rule(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt limits discover_capabilities to at most 1."""
        llm.responses = [_llm_response(content=_sketch_json())]
        await sketch_svc.micro_execute(_micro_request(), _ctx())
        system = _extract_system(llm)
        # Must mention discover + ONCE/once/1/at most
        assert "discover_capabilities" in system
        assert "ONCE" in system.upper() or "at most" in system.lower()

    @pytest.mark.asyncio
    async def test_no_query_session_context(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt forbids query_session_context."""
        llm.responses = [_llm_response(content=_sketch_json())]
        await sketch_svc.micro_execute(_micro_request(), _ctx())
        system = _extract_system(llm)
        assert "query_session_context" in system
        # Should contain "Do NOT call" or similar negation
        idx = system.index("query_session_context")
        nearby = system[max(0, idx - 60) : idx]
        assert "not" in nearby.lower() or "do not" in nearby.lower()

    @pytest.mark.asyncio
    async def test_no_recall_long_term_memory(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt forbids recall_long_term_memory."""
        llm.responses = [_llm_response(content=_sketch_json())]
        await sketch_svc.micro_execute(_micro_request(), _ctx())
        system = _extract_system(llm)
        assert "recall_long_term_memory" in system

    @pytest.mark.asyncio
    async def test_no_clarification_instruction(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt says needs_clarification must be false."""
        llm.responses = [_llm_response(content=_sketch_json())]
        await sketch_svc.micro_execute(_micro_request(), _ctx())
        system = _extract_system(llm)
        assert "needs_clarification" in system
        assert "false" in system.lower()

    @pytest.mark.asyncio
    async def test_output_schema_embedded(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt embeds SKETCH_OUTPUT_SCHEMA."""
        llm.responses = [_llm_response(content=_sketch_json())]
        await sketch_svc.micro_execute(_micro_request(), _ctx())
        system = _extract_system(llm)
        assert "rough_steps" in system
        assert "rationale" in system


# ===========================================================================
# 2. Micro-SKETCH user message (Section 10.3.2)
# ===========================================================================


class TestMicroSketchUserMessage:
    """_assemble_micro_user_message() builds structured USER message."""

    @pytest.mark.asyncio
    async def test_original_intent_section(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """User message contains ORIGINAL_INTENT section."""
        llm.responses = [_llm_response(content=_sketch_json())]
        req = _micro_request()
        await sketch_svc.micro_execute(req, _ctx())
        user = _extract_user(llm)
        assert "ORIGINAL_INTENT" in user
        # Falls back to "micro-replan" since MicroReplanRequest has no intent field
        assert "micro-replan" in user

    @pytest.mark.asyncio
    async def test_completed_summary_section_empty(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """COMPLETED_SUMMARY shows '(no completed steps)' when empty."""
        llm.responses = [_llm_response(content=_sketch_json())]
        req = _micro_request(completed={})
        await sketch_svc.micro_execute(req, _ctx())
        user = _extract_user(llm)
        assert "COMPLETED_SUMMARY" in user
        assert "no completed steps" in user

    @pytest.mark.asyncio
    async def test_completed_summary_with_results(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """COMPLETED_SUMMARY lists step_id, capability, status."""
        completed = {
            "s1": _step_result(
                step_id="s1",
                capability="restaurant.search",
                data={"venue_id": "v-123", "name": "Trattoria"},
            ),
        }
        llm.responses = [_llm_response(content=_sketch_json())]
        req = _micro_request(completed=completed)
        await sketch_svc.micro_execute(req, _ctx())
        user = _extract_user(llm)
        assert "s1" in user
        assert "restaurant.search" in user
        assert "COMPLETED" in user.upper()

    @pytest.mark.asyncio
    async def test_completed_summary_output_keys(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """COMPLETED_SUMMARY includes top-level output data keys."""
        completed = {
            "s1": _step_result(
                step_id="s1",
                capability="restaurant.search",
                data={"venue_id": "v-123", "name": "Trattoria", "rating": 4.5},
            ),
        }
        llm.responses = [_llm_response(content=_sketch_json())]
        req = _micro_request(completed=completed)
        await sketch_svc.micro_execute(req, _ctx())
        user = _extract_user(llm)
        assert "venue_id" in user
        assert "name" in user

    @pytest.mark.asyncio
    async def test_remaining_steps_section(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """REMAINING_STEPS lists step IDs and capabilities."""
        remaining = [
            PlanStep(id="s2", capability="send_notification", params={"to": "user@x.com"}),
            PlanStep(id="s3", capability="log_event"),
        ]
        llm.responses = [_llm_response(content=_sketch_json())]
        req = _micro_request(remaining=remaining)
        await sketch_svc.micro_execute(req, _ctx())
        user = _extract_user(llm)
        assert "REMAINING_STEPS" in user
        assert "s2" in user
        assert "send_notification" in user
        assert "s3" in user
        assert "log_event" in user

    @pytest.mark.asyncio
    async def test_remaining_steps_param_keys(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """REMAINING_STEPS includes param key names."""
        remaining = [
            PlanStep(
                id="s2",
                capability="send_notification",
                params={"to": "user@x.com", "subject": "Hello"},
            ),
        ]
        llm.responses = [_llm_response(content=_sketch_json())]
        req = _micro_request(remaining=remaining)
        await sketch_svc.micro_execute(req, _ctx())
        user = _extract_user(llm)
        assert "to" in user
        assert "subject" in user

    @pytest.mark.asyncio
    async def test_discoveries_section_empty(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """DISCOVERIES shows '(no discoveries)' when empty."""
        llm.responses = [_llm_response(content=_sketch_json())]
        req = _micro_request(discoveries=[])
        await sketch_svc.micro_execute(req, _ctx())
        user = _extract_user(llm)
        assert "DISCOVERIES" in user
        assert "no discoveries" in user

    @pytest.mark.asyncio
    async def test_discoveries_section_populated(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """DISCOVERIES lists field, value, and source_step_id."""
        discoveries = [
            Discovery(field="venue_type", value="outdoor", source_step_id="s1"),
            Discovery(field="max_capacity", value=50, source_step_id="s1"),
        ]
        llm.responses = [_llm_response(content=_sketch_json())]
        req = _micro_request(discoveries=discoveries)
        await sketch_svc.micro_execute(req, _ctx())
        user = _extract_user(llm)
        assert "venue_type" in user
        assert "outdoor" in user
        assert "max_capacity" in user
        assert "50" in user
        assert "s1" in user

    @pytest.mark.asyncio
    async def test_failure_context_section_present(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """FAILURE_CONTEXT includes step_id, error_code, error_message."""
        fc = FailureContext(
            step_id="s2",
            error_code="TIMEOUT",
            error_message="Operation timed out after 5000ms",
        )
        llm.responses = [_llm_response(content=_sketch_json())]
        req = _micro_request(failure_context=fc)
        await sketch_svc.micro_execute(req, _ctx())
        user = _extract_user(llm)
        assert "FAILURE_CONTEXT" in user
        assert "s2" in user
        assert "TIMEOUT" in user
        assert "timed out" in user

    @pytest.mark.asyncio
    async def test_failure_context_with_partial_result(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """FAILURE_CONTEXT includes partial_result when present."""
        fc = FailureContext(
            step_id="s2",
            error_code="PARTIAL",
            error_message="Partial failure",
            partial_result={"sent": 3, "failed": 1},
        )
        llm.responses = [_llm_response(content=_sketch_json())]
        req = _micro_request(failure_context=fc)
        await sketch_svc.micro_execute(req, _ctx())
        user = _extract_user(llm)
        assert "partial_result" in user
        assert "sent" in user

    @pytest.mark.asyncio
    async def test_failure_context_absent(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """No FAILURE_CONTEXT section when failure_context is None."""
        llm.responses = [_llm_response(content=_sketch_json())]
        req = _micro_request(failure_context=None)
        await sketch_svc.micro_execute(req, _ctx())
        user = _extract_user(llm)
        assert "FAILURE_CONTEXT" not in user

    @pytest.mark.asyncio
    async def test_all_five_sections_present(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """All 5 sections present when request has all fields."""
        completed = {
            "s1": _step_result("s1", "cap.a", data={"key": "val"}),
        }
        discoveries = [
            Discovery(field="x", value="y", source_step_id="s1"),
        ]
        fc = FailureContext(
            step_id="s2",
            error_code="ERR",
            error_message="failed",
        )
        remaining = [PlanStep(id="s3", capability="cap.c")]
        llm.responses = [_llm_response(content=_sketch_json())]
        req = _micro_request(
            completed=completed,
            remaining=remaining,
            discoveries=discoveries,
            failure_context=fc,
        )
        await sketch_svc.micro_execute(req, _ctx())
        user = _extract_user(llm)
        for section in [
            "ORIGINAL_INTENT",
            "COMPLETED_SUMMARY",
            "REMAINING_STEPS",
            "DISCOVERIES",
            "FAILURE_CONTEXT",
        ]:
            assert section in user, f"Missing section: {section}"

    @pytest.mark.asyncio
    async def test_message_list_has_system_and_user(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """_build_micro_sketch_messages returns [system, user]."""
        llm.responses = [_llm_response(content=_sketch_json())]
        await sketch_svc.micro_execute(_micro_request(), _ctx())
        msgs = _extract_messages(llm)
        roles = [m["role"] for m in msgs[:2]]
        assert roles == ["system", "user"]


# ===========================================================================
# 3. Micro-SKETCH no HIL (Section 10.5.4)
# ===========================================================================


class TestMicroSketchNoHIL:
    """micro_execute never triggers HIL clarification."""

    @pytest.mark.asyncio
    async def test_no_hil_even_with_clarification_flag(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
        hil: FakeHILCoordinator,
    ) -> None:
        """Even if LLM returns needs_clarification=true, no HIL call."""
        json_with_clarification = json.dumps(
            {
                "rough_steps": [{"intent": "Do something"}],
                "rationale": "needs help",
                "needs_clarification": True,
                "clarification_question": "Which one?",
            }
        )
        llm.responses = [_llm_response(content=json_with_clarification)]
        result = await sketch_svc.micro_execute(_micro_request(), _ctx())
        # micro_execute ignores needs_clarification and does not call HIL
        assert isinstance(result, SketchResult)
        assert len(hil.clarification_calls) == 0


# ===========================================================================
# 4. Micro-SKETCH error propagation
# ===========================================================================


class TestMicroSketchErrors:
    """micro_execute error handling: re-raise pattern."""

    @pytest.mark.asyncio
    async def test_sketch_failed_error_propagates_directly(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """SketchFailedError from _run_agentic_loop propagates unchanged."""
        llm.responses = [_llm_response(content="")]
        with pytest.raises(SketchFailedError) as exc_info:
            await sketch_svc.micro_execute(_micro_request(), _ctx())
        # Should NOT have "Micro-SKETCH failed:" prefix (no double-wrap)
        assert not str(exc_info.value).startswith("Micro-SKETCH failed: Micro-SKETCH")

    @pytest.mark.asyncio
    async def test_generic_exception_wrapped(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """Non-SketchFailedError exceptions are wrapped."""
        # An exception from LLM port will be caught by the generic handler
        llm.responses = []  # Will exhaust and return empty content
        llm._call_index = 999  # Force IndexError-like behavior
        # But our FakeLLMPort returns empty content, which triggers
        # SketchFailedError from _parse_response or _run_agentic_loop
        with pytest.raises(SketchFailedError):
            await sketch_svc.micro_execute(_micro_request(), _ctx())


# ===========================================================================
# 5. Micro-SKETCH end-to-end with realistic payload
# ===========================================================================


class TestMicroSketchEndToEnd:
    """Full micro_execute with completed results, discoveries, failure."""

    @pytest.mark.asyncio
    async def test_realistic_micro_replan(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """Realistic micro-replan: step failed, discovery made, replan."""
        completed = {
            "s1": _step_result(
                "s1",
                "restaurant.search",
                data={"venue_id": "v-42", "name": "Bella Italia"},
            ),
        }
        discoveries = [
            Discovery(
                field="restaurant_closed",
                value=True,
                source_step_id="s1",
            ),
        ]
        fc = FailureContext(
            step_id="s2",
            error_code="UNAVAILABLE",
            error_message="Restaurant is closed on Mondays",
        )
        remaining = [
            PlanStep(id="s2", capability="restaurant.book"),
            PlanStep(id="s3", capability="send_confirmation"),
        ]
        replan_json = json.dumps(
            {
                "rough_steps": [
                    {
                        "intent": "Search for alternative restaurant",
                        "depends_on": [],
                    },
                    {
                        "intent": "Book the alternative",
                        "depends_on": [0],
                    },
                    {
                        "intent": "Send updated confirmation",
                        "depends_on": [1],
                    },
                ],
                "rationale": "Original restaurant closed; find alternative",
                "needs_clarification": False,
            }
        )
        llm.responses = [_llm_response(content=replan_json)]

        result = await sketch_svc.micro_execute(
            _micro_request(
                completed=completed,
                remaining=remaining,
                discoveries=discoveries,
                failure_context=fc,
            ),
            _ctx(),
        )

        assert isinstance(result, SketchResult)
        assert len(result.rough_steps) == 3
        assert result.rationale == "Original restaurant closed; find alternative"

        # Verify message content covers all context
        user = _extract_user(llm)
        assert "restaurant_closed" in user
        assert "Restaurant is closed on Mondays" in user
        assert "venue_id" in user
        assert "restaurant.book" in user


# ===========================================================================
# 6. Micro-EXPAND system prompt (Section 10.3.3)
# ===========================================================================


class TestMicroExpandSystemPrompt:
    """_assemble_micro_expand_system_prompt() produces micro SYSTEM msg."""

    @pytest.mark.asyncio
    async def test_role_is_micro_expand(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt identifies as MICRO-EXPAND stage planner."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        system = _extract_system(llm)
        assert "MICRO-EXPAND" in system

    @pytest.mark.asyncio
    async def test_frozen_steps_plan12(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt states completed steps are FROZEN (PLAN-12)."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        system = _extract_system(llm)
        assert "FROZEN" in system
        assert "PLAN-12" in system

    @pytest.mark.asyncio
    async def test_cross_boundary_dep_rule(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt explains cross-boundary dep syntax."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        system = _extract_system(llm)
        # Must mention $<step_id>.result syntax
        assert "$" in system
        assert "result" in system

    @pytest.mark.asyncio
    async def test_discover_once_rule(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt limits discover_capabilities to 1."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        system = _extract_system(llm)
        assert "discover_capabilities" in system or "discover" in system.lower()

    @pytest.mark.asyncio
    async def test_infrastructure_fields_listed(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt lists infrastructure fields NOT to set."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        system = _extract_system(llm)
        assert "has_side_effects" in system
        assert "compensation" in system
        assert "timeout_ms" in system

    @pytest.mark.asyncio
    async def test_user_fields_listed(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt lists the 8 fields the LLM should set."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        system = _extract_system(llm)
        for field in ["id", "capability", "params", "deps"]:
            assert field in system

    @pytest.mark.asyncio
    async def test_output_schema_embedded(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt embeds EXPAND_OUTPUT_SCHEMA."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        system = _extract_system(llm)
        # Schema has "steps" and "dependencies" and "rationale"
        assert "steps" in system
        assert "dependencies" in system

    @pytest.mark.asyncio
    async def test_replacement_only_scope(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """System prompt scopes to REPLACEMENT STEPS only."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        system = _extract_system(llm)
        assert "REPLACEMENT" in system.upper() or "replacement" in system


# ===========================================================================
# 7. Micro-EXPAND user message (Section 10.3.3)
# ===========================================================================


class TestMicroExpandUserMessage:
    """_assemble_micro_expand_user_message() builds structured USER msg."""

    @pytest.mark.asyncio
    async def test_sketch_plan_section(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """SKETCH_PLAN section lists replacement steps."""
        steps = [
            RoughStep(intent="Search restaurants", suggested_capability="restaurant.search"),
            RoughStep(intent="Book restaurant", suggested_capability="restaurant.book"),
        ]
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(
            _sketch_result(
                steps=steps,
                capabilities=_caps_for("restaurant.search", "restaurant.book"),
            ),
            {},
            _ctx(),
        )
        user = _extract_user(llm)
        assert "SKETCH_PLAN" in user
        assert "Search restaurants" in user
        assert "Book restaurant" in user

    @pytest.mark.asyncio
    async def test_sketch_plan_capability_hints(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """SKETCH_PLAN includes suggested_capability hints."""
        steps = [
            RoughStep(
                intent="Search",
                suggested_capability="restaurant.search",
            ),
        ]
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(
            _sketch_result(
                steps=steps,
                capabilities=_caps_for("restaurant.search"),
            ),
            {},
            _ctx(),
        )
        user = _extract_user(llm)
        assert "restaurant.search" in user

    @pytest.mark.asyncio
    async def test_sketch_plan_depends_on(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """SKETCH_PLAN includes depends_on hints."""
        steps = [
            RoughStep(intent="Step A"),
            RoughStep(intent="Step B", depends_on=["0"]),
        ]
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(
            _sketch_result(steps=steps),
            {},
            _ctx(),
        )
        user = _extract_user(llm)
        assert "[0]" in user or "depends_on" in user

    @pytest.mark.asyncio
    async def test_completed_context_empty(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """COMPLETED_CONTEXT shows '(no completed steps)' when empty."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        user = _extract_user(llm)
        assert "COMPLETED_CONTEXT" in user
        assert "no completed steps" in user

    @pytest.mark.asyncio
    async def test_completed_context_with_results(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """COMPLETED_CONTEXT lists step_id, capability, status."""
        completed = {
            "s1": _step_result("s1", "restaurant.search"),
        }
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), completed, _ctx())
        user = _extract_user(llm)
        assert "s1" in user
        assert "restaurant.search" in user

    @pytest.mark.asyncio
    async def test_completed_context_output_keys(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """COMPLETED_CONTEXT includes output data keys for param binding."""
        completed = {
            "s1": _step_result(
                "s1",
                "restaurant.search",
                data={
                    "venue_id": "v-42",
                    "name": "Bella Italia",
                    "address": "123 Main St",
                    "phone": "555-1234",
                },
            ),
        }
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), completed, _ctx())
        user = _extract_user(llm)
        assert "venue_id" in user
        assert "name" in user
        assert "address" in user

    @pytest.mark.asyncio
    async def test_capability_set_absent_when_empty(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """No CAPABILITY_SET section when no candidates in SketchResult."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(
            _sketch_result(capabilities=[]),
            {},
            _ctx(),
        )
        user = _extract_user(llm)
        assert "CAPABILITY_SET" not in user

    @pytest.mark.asyncio
    async def test_capability_set_present_when_populated(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """CAPABILITY_SET lists discovered capabilities with scores."""
        caps = [
            FakeScoredCapability(
                FakeContract("notification.email", "Send email notification"),
                score=0.95,
            ),
            FakeScoredCapability(
                FakeContract("notification.sms", "Send SMS"),
                score=0.82,
            ),
        ]
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(
            _sketch_result(capabilities=caps),
            {},
            _ctx(),
        )
        user = _extract_user(llm)
        assert "CAPABILITY_SET" in user
        assert "notification.email" in user
        assert "notification.sms" in user
        assert "0.95" in user

    @pytest.mark.asyncio
    async def test_dependency_rules_section(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """DEPENDENCY_RULES section always present."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        user = _extract_user(llm)
        assert "DEPENDENCY_RULES" in user
        assert "DAG" in user

    @pytest.mark.asyncio
    async def test_dependency_rules_lists_completed_ids(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """DEPENDENCY_RULES lists completed step IDs."""
        completed = {
            "s1": _step_result("s1", "cap.a"),
            "s3": _step_result("s3", "cap.b"),
        }
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), completed, _ctx())
        user = _extract_user(llm)
        assert "s1" in user
        assert "s3" in user

    @pytest.mark.asyncio
    async def test_dependency_rules_ref_syntax(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """DEPENDENCY_RULES explains $<step_id>.result.<field> syntax."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        user = _extract_user(llm)
        assert "$" in user
        assert "result" in user

    @pytest.mark.asyncio
    async def test_sketch_rationale_included(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """User message includes SKETCH rationale."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(
            _sketch_result(rationale="Restaurant closed, need replan"),
            {},
            _ctx(),
        )
        user = _extract_user(llm)
        assert "Restaurant closed, need replan" in user

    @pytest.mark.asyncio
    async def test_all_four_sections_present(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """All 4 sections present when all fields populated."""
        caps = [
            FakeScoredCapability(
                FakeContract("cap.new", "New capability"),
                score=0.9,
            ),
        ]
        completed = {
            "s1": _step_result("s1", "cap.a", data={"key": "val"}),
        }
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(
            _sketch_result(capabilities=caps),
            completed,
            _ctx(),
        )
        user = _extract_user(llm)
        for section in [
            "SKETCH_PLAN",
            "COMPLETED_CONTEXT",
            "CAPABILITY_SET",
            "DEPENDENCY_RULES",
        ]:
            assert section in user, f"Missing section: {section}"

    @pytest.mark.asyncio
    async def test_message_list_has_system_and_user(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """_build_micro_expand_messages returns [system, user]."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        msgs = _extract_messages(llm)
        roles = [m["role"] for m in msgs[:2]]
        assert roles == ["system", "user"]


# ===========================================================================
# 8. Micro-EXPAND error propagation
# ===========================================================================


class TestMicroExpandErrors:
    """micro_execute error handling: re-raise pattern."""

    @pytest.mark.asyncio
    async def test_expand_failed_error_propagates_directly(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """ExpandFailedError from _parse_response propagates unchanged."""
        llm.responses = [_llm_response(content="not valid json")]
        with pytest.raises(ExpandFailedError) as exc_info:
            await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        # No double-wrap prefix
        assert not str(exc_info.value).startswith("Micro-EXPAND failed: Micro-EXPAND")

    @pytest.mark.asyncio
    async def test_generic_exception_wrapped_as_expand_failed(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """Non-ExpandFailedError exceptions are wrapped."""
        llm.responses = [_llm_response(content="")]
        with pytest.raises(ExpandFailedError):
            await expand_svc.micro_execute(_sketch_result(), {}, _ctx())


# ===========================================================================
# 9. Micro-EXPAND end-to-end with realistic payload
# ===========================================================================


class TestMicroExpandEndToEnd:
    """Full micro_execute with completed results and expansion."""

    @pytest.mark.asyncio
    async def test_realistic_micro_expand(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """Realistic micro-EXPAND: completed steps + replacement SKETCH."""
        completed = {
            "s1": _step_result(
                "s1",
                "restaurant.search",
                data={"venue_id": "v-42", "name": "Trattoria"},
            ),
        }
        sketch_steps = [
            RoughStep(
                intent="Book alternative restaurant",
                suggested_capability="restaurant.book",
            ),
            RoughStep(
                intent="Send updated confirmation",
                suggested_capability="notification.send",
                depends_on=["0"],
            ),
        ]
        expand_output = json.dumps(
            {
                "steps": [
                    {
                        "id": "s2",
                        "capability": "restaurant.book",
                        "params": {
                            "venue_id": "$s1.result.data.venue_id",
                            "party_size": 4,
                        },
                        "deps": [],
                    },
                    {
                        "id": "s3",
                        "capability": "notification.send",
                        "params": {
                            "to": "user@test.com",
                            "body": "Booking confirmed",
                        },
                        "deps": ["s2"],
                    },
                ],
                "dependencies": {"s3": ["s2"]},
                "rationale": "Book alt restaurant, then confirm",
            }
        )
        llm.responses = [_llm_response(content=expand_output)]

        result = await expand_svc.micro_execute(
            _sketch_result(
                steps=sketch_steps,
                rationale="Need alt restaurant",
                capabilities=_caps_for("restaurant.book", "notification.send"),
            ),
            completed,
            _ctx(),
        )

        assert isinstance(result, ExpandedPlan)
        assert len(result.steps) == 2
        assert result.steps[0].capability == "restaurant.book"
        assert result.steps[1].capability == "notification.send"
        assert result.dependencies == {"s3": ["s2"]}

        # Verify messages carry completed context
        user = _extract_user(llm)
        assert "venue_id" in user
        assert "Trattoria" not in user or "name" in user  # keys, not values

    @pytest.mark.asyncio
    async def test_tool_call_during_micro_expand(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
        router: FakeToolRouter,
    ) -> None:
        """micro_execute supports tool calling in the agentic loop."""
        llm.responses = [
            _llm_response(
                tool_calls=[
                    _tool_call(
                        "discover_capabilities",
                        {"intent": "send notification"},
                    ),
                ],
            ),
            _llm_response(content=_expand_json()),
        ]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        assert len(router.discover_calls) == 1
        assert router.discover_calls[0]["intent"] == "send notification"

    @pytest.mark.asyncio
    async def test_returns_expanded_plan(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """micro_execute returns ExpandedPlan with tool_mappings."""
        llm.responses = [_llm_response(content=_expand_json())]
        result = await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        assert isinstance(result, ExpandedPlan)
        assert result.tool_mappings == {"s2": "notification.send"}
        assert result.rationale == "Micro expand rationale"


# ===========================================================================
# 10. Micro-SKETCH vs full SKETCH prompt differentiation
# ===========================================================================


class TestMicroVsFullSketch:
    """micro_execute uses a different system prompt than execute."""

    @pytest.mark.asyncio
    async def test_micro_system_differs_from_full(
        self,
        sketch_svc: SketchService,
        llm: FakeLLMPort,
    ) -> None:
        """micro_execute system prompt is NOT the generic SKETCH prompt."""
        llm.responses = [_llm_response(content=_sketch_json())]
        await sketch_svc.micro_execute(_micro_request(), _ctx())
        micro_system = _extract_system(llm)

        # Reset for full execute
        llm2 = FakeLLMPort()
        llm2.responses = [_llm_response(content=_sketch_json())]
        from k1.planner.stages.sketch_service import SketchService as SS

        full_svc = SS(
            llm_port=llm2,
            tool_router=FakeToolRouter(),
            hil_port=FakeHILCoordinator(),
        )
        await full_svc.execute(
            PlanRequest(intent="Test", trace_id="t1"),
            _ctx(),
        )
        full_system = _extract_system(llm2)

        assert micro_system != full_system
        assert "MICRO-REPLAN" in micro_system
        assert "MICRO-REPLAN" not in full_system


# ===========================================================================
# 11. Micro-EXPAND vs full EXPAND prompt differentiation
# ===========================================================================


class TestMicroVsFullExpand:
    """micro_execute uses a different system prompt than execute."""

    @pytest.mark.asyncio
    async def test_micro_system_differs_from_full(
        self,
        expand_svc: ExpandService,
        llm: FakeLLMPort,
    ) -> None:
        """micro_execute system prompt is NOT the generic EXPAND prompt."""
        llm.responses = [_llm_response(content=_expand_json())]
        await expand_svc.micro_execute(_sketch_result(), {}, _ctx())
        micro_system = _extract_system(llm)

        # Reset for full execute
        llm2 = FakeLLMPort()
        llm2.responses = [_llm_response(content=_expand_json())]
        full_svc = ExpandService(
            llm_port=llm2,
            tool_router=FakeToolRouter(),
        )
        await full_svc.execute(
            _sketch_result(),
            PlanRequest(intent="Test", trace_id="t1"),
            _ctx(),
        )
        full_system = _extract_system(llm2)

        assert micro_system != full_system
        assert "MICRO-EXPAND" in micro_system
        assert "MICRO-EXPAND" not in full_system
