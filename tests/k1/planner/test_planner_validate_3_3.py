"""
Tests for ValidateService (Epic 3.3).

Covers all 8 issues of Epic 3.3:
  3.3.1 -- ValidateService skeleton & constructor
  3.3.2 -- DAG cycle detection (Kahn's topological sort, PLAN-09)
  3.3.3 -- Capability existence check (PLAN-08)
  3.3.4 -- Max tool call count / constraint validation (PLAN-05)
  3.3.5 -- LLM arbiter (coherence check, ~500 tokens)
  3.3.6 -- Optional HIL approval flow
  3.3.7 -- ValidationVerdict assembly
  3.3.8 -- Error recovery (ERR_VALIDATE_FAIL)

Test categories (~45 tests target):
  - DAG cycle detection (~8)
  - Capability existence (~8)
  - Constraint / param validation (~5)
  - LLM arbiter call (~8)
  - HIL approval flow (~6)
  - Error recovery (~5)
  - Constructor & skeleton (~5)

References
----------
- planner.md Section 8 (Stage 3 VALIDATE Deep Dive)
- planner.md Section 17.5 (ValidateService ~45 tests)
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.types import CapabilityContract, InputSpec, ScoredCapability
from k1.orchestrator.types import PlanRequest, PlanStep
from k1.planner.stages.validate_service import (
    _ARBITER_MAX_TOKENS,
    _ARBITER_TEMPERATURE,
    _ARBITER_TIMEOUT_MS,
    _META_CAPABILITY_BUILD_AGENT,
    _MICRO_ARBITER_MAX_TOKENS,
    _MICRO_ARBITER_TIMEOUT_MS,
    VALIDATE_VERDICT_SCHEMA,
    ValidateService,
)
from k1.planner.types import (
    CHECK_CAPABILITY_MISSING,
    CHECK_DAG_CYCLE,
    CHECK_DANGLING_DEPENDENCY,
    CHECK_INTER_STEP_REF,
    CHECK_PARAM_TYPE_MISMATCH,
    CHECK_SELF_REFERENCE,
    CHECK_STEP_ID_DUPLICATE,
    CHECK_UNSAFE_CAPABILITY,
    SAFETY_SAFE,
    SAFETY_UNKNOWN,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    VERDICT_APPROVED,
    VERDICT_REJECT,
    VERDICT_REVISE,
    ExpandedPlan,
    HubRequest,
    HubResponse,
    StageContext,
    ValidateRejectedError,
    ValidationIssue,
    ValidationVerdict,
)

# ===========================================================================
# Fakes
# ===========================================================================


class FakeLLMPort:
    """Configurable fake ILLMPort for testing."""

    def __init__(self) -> None:
        self.calls: List[HubRequest] = []
        self.response: Optional[HubResponse] = None
        self.error: Optional[Exception] = None

    def set_response(self, content: Any, tokens: int = 100) -> None:
        if isinstance(content, dict):
            content = json.dumps(content)
        self.response = HubResponse(
            result={"content": content},
            metadata={"usage": {"total_tokens": tokens}},
        )

    async def execute(self, request: HubRequest) -> HubResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        if self.response is not None:
            return self.response
        # Default: approved verdict.
        return HubResponse(
            result={
                "content": json.dumps(
                    {
                        "status": "approved",
                        "reasons": ["Plan is coherent and complete"],
                        "suggested_fixes": [],
                        "coherence_score": 0.95,
                        "safety_assessment": "safe",
                        "completeness": True,
                    }
                ),
            },
            metadata={"usage": {"total_tokens": 100}},
        )


class FakeFabricRetrieval:
    """Configurable fake IFabricRetrievalPort."""

    def __init__(self) -> None:
        self.discover_calls: List[Dict[str, Any]] = []
        self.find_prompts_calls: List[Dict[str, Any]] = []

    async def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = "GREEN",
        session_context: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> Any:
        self.discover_calls.append(
            {
                "domain": domain,
                "intent": intent,
                "safety_band": safety_band,
                "top_k": top_k,
            }
        )
        return None

    async def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = "GREEN",
        top_k: int = 10,
    ) -> Any:
        self.find_prompts_calls.append(
            {
                "intent": intent,
                "domain": domain,
                "safety_band": safety_band,
                "top_k": top_k,
            }
        )
        return None


class FakeHILPort:
    """E5: minimal IHILPort fake (renamed from FakeHILPort).

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


def _never_cancel() -> bool:
    return False


def _ctx(
    request_id: str = "req-1",
    trace_id: str = "trace-1",
    timeout_ms: int = 5000,
    token_budget: int = 2000,
) -> StageContext:
    return StageContext(
        request_id=request_id,
        trace_id=trace_id,
        timeout_remaining_ms=timeout_ms,
        token_budget_remaining=token_budget,
        cancel_check=_never_cancel,
    )


def _step(
    step_id: str = "s1",
    capability: str = "tool.demo",
    *,
    params: Optional[Dict[str, Any]] = None,
    has_side_effects: bool = False,
    safety_band_min: Optional[str] = None,
    is_optional: bool = False,
    timeout_ms: int = 1000,
) -> PlanStep:
    return PlanStep(
        id=step_id,
        capability=capability,
        params=params or {},
        has_side_effects=has_side_effects,
        safety_band_min=safety_band_min,
        is_optional=is_optional,
        timeout_ms=timeout_ms,
    )


def _plan(
    steps: Optional[List[PlanStep]] = None,
    dependencies: Optional[Dict[str, List[str]]] = None,
    rationale: str = "test plan",
) -> ExpandedPlan:
    if steps is None:
        steps = [_step("s1")]
    tool_mappings = {s.id: s.capability for s in steps}
    return ExpandedPlan(
        steps=steps,
        dependencies=dependencies or {},
        tool_mappings=tool_mappings,
        rationale=rationale,
    )


def _request(intent: str = "test intent") -> PlanRequest:
    return PlanRequest(
        intent=intent,
        request_id="req-1",
        trace_id="trace-1",
    )


def _scored_cap(name: str, **kwargs: Any) -> ScoredCapability:
    return ScoredCapability(
        contract=CapabilityContract(name=name, **kwargs),
        score=0.9,
    )


# ===========================================================================
# 1. Constructor & Skeleton (Issue 3.3.1)
# ===========================================================================


class TestConstructor:
    """ValidateService constructor and basic properties."""

    def test_constructor_stores_dependencies(self) -> None:
        llm = FakeLLMPort()
        fab = FakeFabricRetrieval()
        hil = FakeHILPort()
        svc = ValidateService(llm, fab, hil)
        assert svc.llm_port is llm
        assert svc.fabric_retrieval is fab
        assert svc.hil_port is hil

    def test_constructor_rejects_none_llm(self) -> None:
        with pytest.raises(TypeError, match="llm_port"):
            ValidateService(None, FakeFabricRetrieval(), FakeHILPort())  # type: ignore[arg-type]

    def test_constructor_rejects_none_fabric(self) -> None:
        with pytest.raises(TypeError, match="fabric_retrieval"):
            ValidateService(FakeLLMPort(), None, FakeHILPort())  # type: ignore[arg-type]

    def test_constructor_rejects_none_hil(self) -> None:
        with pytest.raises(TypeError, match="hil_port"):
            ValidateService(FakeLLMPort(), FakeFabricRetrieval(), None)  # type: ignore[arg-type]

    def test_uses_slots(self) -> None:
        assert "__slots__" in dir(ValidateService)
        assert "_llm_port" in ValidateService.__slots__
        assert "_fabric_retrieval" in ValidateService.__slots__
        assert "_hil_port" in ValidateService.__slots__


# ===========================================================================
# 2. DAG Cycle Detection (Issue 3.3.2) ~8 tests
# ===========================================================================


class TestDAGCycleDetection:
    """DAG acyclicity via Kahn's topological sort (PLAN-09)."""

    async def test_acyclic_dag_passes(self) -> None:
        """Linear DAG: s1 -> s2 -> s3."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1"), _step("s2"), _step("s3")]
        deps = {"s2": ["s1"], "s3": ["s2"]}
        passed, issues = svc._check_dag_acyclicity(steps, deps)
        assert passed is True
        assert len([i for i in issues if i.severity == SEVERITY_ERROR]) == 0

    async def test_simple_cycle_detected(self) -> None:
        """s1 -> s2 -> s1 cycle."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1"), _step("s2")]
        deps = {"s1": ["s2"], "s2": ["s1"]}
        passed, issues = svc._check_dag_acyclicity(steps, deps)
        assert passed is False
        cycle_issues = [i for i in issues if i.check_name == CHECK_DAG_CYCLE]
        assert len(cycle_issues) >= 1

    async def test_three_node_cycle(self) -> None:
        """s1 -> s2 -> s3 -> s1 cycle."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1"), _step("s2"), _step("s3")]
        deps = {"s1": ["s3"], "s2": ["s1"], "s3": ["s2"]}
        passed, issues = svc._check_dag_acyclicity(steps, deps)
        assert passed is False

    async def test_self_reference_detected(self) -> None:
        """Step depends on itself."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1")]
        deps = {"s1": ["s1"]}
        passed, issues = svc._check_dag_acyclicity(steps, deps)
        assert passed is False
        self_refs = [i for i in issues if i.check_name == CHECK_SELF_REFERENCE]
        assert len(self_refs) == 1

    async def test_dangling_dependency(self) -> None:
        """Dependency references non-existent step."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1"), _step("s2")]
        deps = {"s2": ["s99"]}
        passed, issues = svc._check_dag_acyclicity(steps, deps)
        assert passed is False
        dangling = [i for i in issues if i.check_name == CHECK_DANGLING_DEPENDENCY]
        assert len(dangling) == 1
        assert "s99" in dangling[0].detail

    async def test_duplicate_step_ids(self) -> None:
        """Duplicate step IDs detected."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1"), _step("s1", capability="tool.other")]
        deps = {}
        passed, issues = svc._check_dag_acyclicity(steps, deps)
        assert passed is False
        dups = [i for i in issues if i.check_name == CHECK_STEP_ID_DUPLICATE]
        assert len(dups) >= 1

    async def test_inter_step_ref_without_dep(self) -> None:
        """Param references $s1.result.x but s1 not in deps."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [
            _step("s1"),
            _step("s2", params={"input": "$s1.result.output"}),
        ]
        deps = {}  # s2 does NOT declare s1 as dependency.
        passed, issues = svc._check_dag_acyclicity(steps, deps)
        assert passed is False
        ref_issues = [i for i in issues if i.check_name == CHECK_INTER_STEP_REF]
        assert len(ref_issues) == 1

    async def test_inter_step_ref_with_dep_passes(self) -> None:
        """Param references $s1.result.x AND s1 is in deps -- valid."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [
            _step("s1"),
            _step("s2", params={"input": "$s1.result.output"}),
        ]
        deps = {"s2": ["s1"]}
        passed, issues = svc._check_dag_acyclicity(steps, deps)
        assert passed is True
        ref_issues = [i for i in issues if i.check_name == CHECK_INTER_STEP_REF]
        assert len(ref_issues) == 0


# ===========================================================================
# 3. Capability Existence (Issue 3.3.3) ~8 tests
# ===========================================================================


class TestCapabilityExistence:
    """Capability existence check (PLAN-08)."""

    async def test_known_capability_passes(self) -> None:
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1", capability="tool.demo")]
        cached = [_scored_cap("tool.demo")]
        passed, issues = svc._check_capability_existence(steps, cached)
        assert passed is True
        assert len([i for i in issues if i.severity == SEVERITY_ERROR]) == 0

    async def test_unknown_capability_fails(self) -> None:
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1", capability="tool.nonexistent")]
        cached = [_scored_cap("tool.demo")]
        passed, issues = svc._check_capability_existence(steps, cached)
        assert passed is False
        missing = [i for i in issues if i.check_name == CHECK_CAPABILITY_MISSING]
        assert len(missing) == 1
        assert "tool.nonexistent" in missing[0].detail

    async def test_dollar_prefix_skipped(self) -> None:
        """Inter-step reference capabilities ($s1.result.cap) are skipped."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1", capability="$s2.result.agent_name")]
        cached = [_scored_cap("tool.demo")]
        passed, issues = svc._check_capability_existence(steps, cached)
        assert passed is True

    async def test_meta_build_agent_skipped(self) -> None:
        """Reserved meta-capability is always valid."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1", capability=_META_CAPABILITY_BUILD_AGENT)]
        cached = []
        passed, issues = svc._check_capability_existence(steps, cached)
        assert passed is True

    async def test_empty_capability_fails(self) -> None:
        """Step with empty capability is caught.

        This can't happen due to PlanStep.__post_init__ validation,
        but we test the method directly.
        """
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        # Create step with non-empty cap for PlanStep, then test method directly.
        # The method checks steps directly, so we simulate.
        step = PlanStep(id="s1", capability="x")
        # Override via object.__setattr__ on frozen dataclass for test purposes.
        object.__setattr__(step, "capability", "")
        passed, issues = svc._check_capability_existence([step], [])
        assert passed is False

    async def test_no_cache_skips_check(self) -> None:
        """Without cached capabilities, check is skipped (cannot verify)."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1", capability="tool.unknown")]
        passed, issues = svc._check_capability_existence(steps, None)
        assert passed is True  # No errors when no cache.

    async def test_unresolved_capability_warning(self) -> None:
        """UNRESOLVED capability from degraded EXPAND gets warning."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1", capability="UNRESOLVED")]
        cached = [_scored_cap("tool.demo")]
        passed, issues = svc._check_capability_existence(steps, cached)
        assert passed is True  # Warning, not error.
        warnings = [i for i in issues if i.severity == SEVERITY_WARNING]
        assert len(warnings) == 1
        assert "unresolved" in warnings[0].detail.lower()

    async def test_multiple_capabilities_checked(self) -> None:
        """Multiple steps, mix of known and unknown."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [
            _step("s1", capability="tool.known"),
            _step("s2", capability="tool.unknown"),
            _step("s3", capability="tool.known"),
        ]
        cached = [_scored_cap("tool.known")]
        passed, issues = svc._check_capability_existence(steps, cached)
        assert passed is False
        errors = [i for i in issues if i.severity == SEVERITY_ERROR]
        assert len(errors) == 1
        assert errors[0].step_id == "s2"


# ===========================================================================
# 4. Constraint Validation (Issue 3.3.4) ~5 tests
# ===========================================================================


class TestConstraintValidation:
    """Constraint and param type validation."""

    async def test_missing_required_param_error(self) -> None:
        """Step missing a required param from contract."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        cap = CapabilityContract(
            name="tool.demo",
            required_inputs=[
                InputSpec(name="query", type="string"),
            ],
        )
        cached = [ScoredCapability(contract=cap, score=0.9)]
        steps = [_step("s1", capability="tool.demo", params={})]
        issues = svc._validate_plan_constraints(steps, _ctx(), cached)
        param_errors = [i for i in issues if i.check_name == CHECK_PARAM_TYPE_MISMATCH]
        assert len(param_errors) == 1
        assert "query" in param_errors[0].detail

    async def test_provided_required_param_passes(self) -> None:
        """Step has required param -- no error."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        cap = CapabilityContract(
            name="tool.demo",
            required_inputs=[
                InputSpec(name="query", type="string"),
            ],
        )
        cached = [ScoredCapability(contract=cap, score=0.9)]
        steps = [_step("s1", capability="tool.demo", params={"query": "test"})]
        issues = svc._validate_plan_constraints(steps, _ctx(), cached)
        param_errors = [i for i in issues if i.check_name == CHECK_PARAM_TYPE_MISMATCH]
        assert len(param_errors) == 0

    async def test_inter_step_ref_param_skipped(self) -> None:
        """Inter-step reference params ($s1.result.x) skip required check."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        cap = CapabilityContract(
            name="tool.demo",
            required_inputs=[
                InputSpec(name="query", type="string"),
            ],
        )
        cached = [ScoredCapability(contract=cap, score=0.9)]
        steps = [_step("s1", capability="tool.demo", params={"query": "$s0.result.text"})]
        issues = svc._validate_plan_constraints(steps, _ctx(), cached)
        param_errors = [i for i in issues if i.check_name == CHECK_PARAM_TYPE_MISMATCH]
        assert len(param_errors) == 0

    async def test_unsafe_capability_warning(self) -> None:
        """Capability with non-GREEN safety_band_min gets warning."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        cap = CapabilityContract(name="tool.risky", safety_band_min="AMBER")
        cached = [ScoredCapability(contract=cap, score=0.9)]
        steps = [_step("s1", capability="tool.risky")]
        issues = svc._validate_plan_constraints(steps, _ctx(), cached)
        unsafe = [i for i in issues if i.check_name == CHECK_UNSAFE_CAPABILITY]
        assert len(unsafe) == 1
        assert "AMBER" in unsafe[0].detail

    async def test_no_contract_skips_validation(self) -> None:
        """Steps without matching contract are skipped."""
        svc = ValidateService(FakeLLMPort(), FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1", capability="tool.unknown", params={})]
        issues = svc._validate_plan_constraints(steps, _ctx(), [])
        assert len(issues) == 0


# ===========================================================================
# 5. LLM Arbiter (Issue 3.3.5) ~8 tests
# ===========================================================================


class TestLLMArbiter:
    """LLM arbiter call and verdict parsing."""

    async def test_approved_verdict_parsed(self) -> None:
        """Arbiter returns 'approved' -- parsed correctly."""
        llm = FakeLLMPort()
        llm.set_response(
            {
                "status": "approved",
                "reasons": ["Plan looks good"],
                "suggested_fixes": [],
                "coherence_score": 0.95,
                "safety_assessment": "safe",
                "completeness": True,
            }
        )
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        result = await svc.execute(_plan(), _request(), _ctx())
        assert result.status == VERDICT_APPROVED
        assert result.confidence == pytest.approx(0.95)
        assert result.safety_assessment == SAFETY_SAFE
        assert result.deterministic_pass is True

    async def test_revise_verdict_parsed(self) -> None:
        """Arbiter returns 'revise' -- issues created from reasons."""
        llm = FakeLLMPort()
        llm.set_response(
            {
                "status": "revise",
                "reasons": ["Missing step for notification"],
                "suggested_fixes": ["Add notification step after booking"],
                "coherence_score": 0.6,
                "safety_assessment": "caution",
                "completeness": False,
            }
        )
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        result = await svc.execute(_plan(), _request(), _ctx())
        assert result.status == VERDICT_REVISE
        assert len(result.issues) >= 1
        assert result.suggested_fixes == ["Add notification step after booking"]

    async def test_reject_verdict_parsed(self) -> None:
        """Arbiter returns 'reject' -- error-level issues."""
        llm = FakeLLMPort()
        llm.set_response(
            {
                "status": "reject",
                "reasons": ["Plan is fundamentally unsafe"],
                "suggested_fixes": [],
                "coherence_score": 0.2,
                "safety_assessment": "unsafe",
                "completeness": False,
            }
        )
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        result = await svc.execute(_plan(), _request(), _ctx())
        assert result.status == VERDICT_REJECT
        error_issues = [i for i in result.issues if i.severity == SEVERITY_ERROR]
        assert len(error_issues) >= 1

    async def test_structured_capability_used(self) -> None:
        """Arbiter uses STRUCTURED capability (not CHAT)."""
        llm = FakeLLMPort()
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        await svc.execute(_plan(), _request(), _ctx())
        assert len(llm.calls) == 1
        assert llm.calls[0].capability == "STRUCTURED"

    async def test_temperature_is_0_1(self) -> None:
        """Arbiter uses temperature=0.1 (lowest of all stages)."""
        llm = FakeLLMPort()
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        await svc.execute(_plan(), _request(), _ctx())
        assert llm.calls[0].constraints.temperature == pytest.approx(0.1)

    async def test_max_tokens_512(self) -> None:
        """Arbiter uses max_tokens=512."""
        llm = FakeLLMPort()
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        await svc.execute(_plan(), _request(), _ctx())
        assert llm.calls[0].constraints.max_tokens == _ARBITER_MAX_TOKENS

    async def test_prompt_contains_intent(self) -> None:
        """Arbiter prompt contains the user's intent."""
        llm = FakeLLMPort()
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        await svc.execute(_plan(), _request("book a restaurant"), _ctx())
        user_msg = llm.calls[0].payload["messages"][1]["content"]
        assert "book a restaurant" in user_msg

    async def test_prompt_contains_step_details(self) -> None:
        """Arbiter prompt includes step details."""
        llm = FakeLLMPort()
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1", capability="tool.search"), _step("s2", capability="tool.book")]
        plan = _plan(steps=steps, dependencies={"s2": ["s1"]})
        await svc.execute(plan, _request(), _ctx())
        user_msg = llm.calls[0].payload["messages"][1]["content"]
        assert "tool.search" in user_msg
        assert "tool.book" in user_msg


# ===========================================================================
# 6. HIL Approval Flow (Issue 3.3.6) ~6 tests
# ===========================================================================


class TestHILApproval:
    """Optional HIL approval for high-impact plans."""

    async def test_no_side_effects_auto_approves(self) -> None:
        """No side-effect steps -- no HIL triggered."""
        llm = FakeLLMPort()
        hil = FakeHILPort()
        svc = ValidateService(llm, FakeFabricRetrieval(), hil)
        result = await svc.execute(
            _plan(steps=[_step("s1", has_side_effects=False)]),
            _request(),
            _ctx(),
        )
        assert result.status == VERDICT_APPROVED
        assert len(hil.approval_calls) == 0

    async def test_side_effects_green_safe_auto_approves(self) -> None:
        """Side effects with GREEN band + safe assessment -- auto-approve."""
        llm = FakeLLMPort()
        llm.set_response(
            {
                "status": "approved",
                "reasons": ["Looks good"],
                "suggested_fixes": [],
                "coherence_score": 0.9,
                "safety_assessment": "safe",
                "completeness": True,
            }
        )
        hil = FakeHILPort()
        svc = ValidateService(llm, FakeFabricRetrieval(), hil)
        result = await svc.execute(
            _plan(steps=[_step("s1", has_side_effects=True, safety_band_min="GREEN")]),
            _request(),
            _ctx(),
        )
        assert result.status == VERDICT_APPROVED
        assert len(hil.approval_calls) == 0  # No HIL needed.

    async def test_side_effects_amber_triggers_hil(self) -> None:
        """Side effects with AMBER band -- HIL triggered."""
        llm = FakeLLMPort()
        llm.set_response(
            {
                "status": "approved",
                "reasons": ["Plan approved with caution"],
                "suggested_fixes": [],
                "coherence_score": 0.8,
                "safety_assessment": "caution",
                "completeness": True,
            }
        )
        hil = FakeHILPort()
        hil.approval_response = "approve"
        svc = ValidateService(llm, FakeFabricRetrieval(), hil)
        result = await svc.execute(
            _plan(steps=[_step("s1", has_side_effects=True, safety_band_min="AMBER")]),
            _request(),
            _ctx(),
        )
        assert result.status == VERDICT_APPROVED
        assert len(hil.approval_calls) == 1

    async def test_hil_reject_overrides_verdict(self) -> None:
        """User rejects via HIL -- verdict becomes reject."""
        llm = FakeLLMPort()
        llm.set_response(
            {
                "status": "approved",
                "reasons": ["Plan approved"],
                "suggested_fixes": [],
                "coherence_score": 0.9,
                "safety_assessment": "caution",
                "completeness": True,
            }
        )
        hil = FakeHILPort()
        from k1.hil.types import ApprovalResponse

        hil._approval_response = ApprovalResponse(
            hil_request_id="fake",
            decision="reject",
            modifications=None,
            timed_out=False,
        )
        svc = ValidateService(llm, FakeFabricRetrieval(), hil)
        result = await svc.execute(
            _plan(steps=[_step("s1", has_side_effects=True, safety_band_min="AMBER")]),
            _request(),
            _ctx(),
        )
        assert result.status == VERDICT_REJECT
        rejection_issues = [i for i in result.issues if i.check_name == "hil_rejection"]
        assert len(rejection_issues) == 1

    async def test_hil_timeout_green_auto_approves(self) -> None:
        """HIL timeout with all GREEN steps -- auto-approve."""
        llm = FakeLLMPort()
        llm.set_response(
            {
                "status": "approved",
                "reasons": ["OK"],
                "suggested_fixes": [],
                "coherence_score": 0.9,
                "safety_assessment": "caution",
                "completeness": True,
            }
        )
        hil = FakeHILPort()
        from k1.hil.types import ApprovalResponse

        hil._approval_response = ApprovalResponse(
            hil_request_id="fake",
            decision="approve",
            modifications=None,
            timed_out=True,
        )
        svc = ValidateService(llm, FakeFabricRetrieval(), hil)
        result = await svc.execute(
            _plan(steps=[_step("s1", has_side_effects=True, safety_band_min="GREEN")]),
            _request(),
            _ctx(),
        )
        assert result.status == VERDICT_APPROVED

    async def test_hil_timeout_non_green_rejects(self) -> None:
        """HIL timeout with non-GREEN steps -- reject."""
        llm = FakeLLMPort()
        llm.set_response(
            {
                "status": "approved",
                "reasons": ["OK"],
                "suggested_fixes": [],
                "coherence_score": 0.9,
                "safety_assessment": "caution",
                "completeness": True,
            }
        )
        hil = FakeHILPort()
        from k1.hil.types import ApprovalResponse

        hil._approval_response = ApprovalResponse(
            hil_request_id="fake",
            decision="approve",
            modifications=None,
            timed_out=True,
        )
        svc = ValidateService(llm, FakeFabricRetrieval(), hil)
        result = await svc.execute(
            _plan(steps=[_step("s1", has_side_effects=True, safety_band_min="AMBER")]),
            _request(),
            _ctx(),
        )
        assert result.status == VERDICT_REJECT


# ===========================================================================
# 7. Error Recovery (Issue 3.3.8) ~5 tests
# ===========================================================================


class TestErrorRecovery:
    """ERR_VALIDATE_FAIL error recovery paths."""

    async def test_arbiter_timeout_deterministic_pass_auto_approves(self) -> None:
        """Path 2: arbiter fails but deterministic checks passed -- auto-approve."""
        llm = FakeLLMPort()
        llm.error = TimeoutError("LLM timeout")
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        result = await svc.execute(_plan(), _request(), _ctx())
        assert result.status == VERDICT_APPROVED
        assert result.deterministic_pass is True
        assert result.safety_assessment == SAFETY_UNKNOWN
        assert "auto-approved" in result.rationale.lower()

    async def test_arbiter_error_deterministic_fail_rejects(self) -> None:
        """Path 3: arbiter fails AND deterministic checks failed -- reject."""
        llm = FakeLLMPort()
        llm.error = TimeoutError("LLM timeout")
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        # Create a plan with a cycle to fail deterministic checks.
        steps = [_step("s1"), _step("s2")]
        deps = {"s1": ["s2"], "s2": ["s1"]}
        plan = _plan(steps=steps, dependencies=deps)
        result = await svc.execute(plan, _request(), _ctx())
        assert result.status == VERDICT_REJECT
        assert result.deterministic_pass is False

    async def test_cancel_during_validate_raises(self) -> None:
        """Cancellation check raises ValidateRejectedError."""
        llm = FakeLLMPort()
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        ctx = StageContext(
            request_id="req-1",
            trace_id="trace-1",
            timeout_remaining_ms=5000,
            token_budget_remaining=2000,
            cancel_check=lambda: True,  # Always cancelled.
        )
        with pytest.raises(ValidateRejectedError):
            await svc.execute(_plan(), _request(), ctx)

    async def test_unparseable_arbiter_response_auto_approves(self) -> None:
        """Arbiter returns garbage -- auto-approve on deterministic pass."""
        llm = FakeLLMPort()
        llm.set_response("this is not json at all!!")
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        result = await svc.execute(_plan(), _request(), _ctx())
        assert result.status == VERDICT_APPROVED
        assert "unparseable" in result.rationale.lower()

    async def test_arbiter_invalid_status_defaults_to_approved(self) -> None:
        """Arbiter returns unknown status -- defaults to approved."""
        llm = FakeLLMPort()
        llm.set_response(
            {
                "status": "maybe",
                "reasons": ["Unsure"],
                "coherence_score": 0.5,
                "safety_assessment": "safe",
                "completeness": True,
            }
        )
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        result = await svc.execute(_plan(), _request(), _ctx())
        assert result.status == VERDICT_APPROVED


# ===========================================================================
# 8. Micro-validate (execute vs micro_execute)
# ===========================================================================


class TestMicroValidate:
    """micro_execute -- abbreviated validation."""

    async def test_micro_revise_upgraded_to_approved(self) -> None:
        """Micro-validate: 'revise' verdict treated as 'approved'."""
        llm = FakeLLMPort()
        llm.set_response(
            {
                "status": "revise",
                "reasons": ["Minor issues"],
                "suggested_fixes": ["Fix X"],
                "coherence_score": 0.7,
                "safety_assessment": "safe",
                "completeness": True,
            }
        )
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        result = await svc.micro_execute(_plan(), _ctx())
        assert result.status == VERDICT_APPROVED
        assert "best-effort" in result.rationale.lower()

    async def test_micro_reject_stays_reject(self) -> None:
        """Micro-validate: 'reject' verdict stays as 'reject'."""
        llm = FakeLLMPort()
        llm.set_response(
            {
                "status": "reject",
                "reasons": ["Completely wrong"],
                "suggested_fixes": [],
                "coherence_score": 0.1,
                "safety_assessment": "unsafe",
                "completeness": False,
            }
        )
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        result = await svc.micro_execute(_plan(), _ctx())
        assert result.status == VERDICT_REJECT

    async def test_micro_no_hil(self) -> None:
        """Micro-validate never triggers HIL."""
        llm = FakeLLMPort()
        llm.set_response(
            {
                "status": "approved",
                "reasons": ["OK"],
                "suggested_fixes": [],
                "coherence_score": 0.9,
                "safety_assessment": "caution",
                "completeness": True,
            }
        )
        hil = FakeHILPort()
        svc = ValidateService(llm, FakeFabricRetrieval(), hil)
        result = await svc.micro_execute(
            _plan(steps=[_step("s1", has_side_effects=True, safety_band_min="AMBER")]),
            _ctx(),
        )
        assert result.status == VERDICT_APPROVED
        assert len(hil.approval_calls) == 0

    async def test_micro_uses_reduced_budget(self) -> None:
        """Micro-validate uses reduced token budget."""
        llm = FakeLLMPort()
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        await svc.micro_execute(_plan(), _ctx())
        assert llm.calls[0].constraints.max_tokens == _MICRO_ARBITER_MAX_TOKENS

    async def test_micro_deterministic_fail_rejects(self) -> None:
        """Micro-validate with DAG cycle rejects without LLM call."""
        llm = FakeLLMPort()
        svc = ValidateService(llm, FakeFabricRetrieval(), FakeHILPort())
        steps = [_step("s1"), _step("s2")]
        deps = {"s1": ["s2"], "s2": ["s1"]}
        plan = _plan(steps=steps, dependencies=deps)
        result = await svc.micro_execute(plan, _ctx())
        assert result.status == VERDICT_REJECT
        assert result.deterministic_pass is False
        assert len(llm.calls) == 0  # No LLM call made.


# ===========================================================================
# 9. ValidationVerdict Type Extension Tests
# ===========================================================================


class TestValidationVerdictExtension:
    """Tests for the extended ValidationVerdict fields."""

    def test_deterministic_pass_default_true(self) -> None:
        v = ValidationVerdict(
            status=VERDICT_APPROVED,
            rationale="ok",
            confidence=0.9,
        )
        assert v.deterministic_pass is True

    def test_safety_assessment_default_unknown(self) -> None:
        v = ValidationVerdict(
            status=VERDICT_APPROVED,
            rationale="ok",
            confidence=0.9,
        )
        assert v.safety_assessment == SAFETY_UNKNOWN

    def test_suggested_fixes_default_empty(self) -> None:
        v = ValidationVerdict(
            status=VERDICT_APPROVED,
            rationale="ok",
            confidence=0.9,
        )
        assert v.suggested_fixes == []

    def test_approved_requires_deterministic_pass(self) -> None:
        """Cannot approve with deterministic_pass=False."""
        with pytest.raises(ValueError, match="deterministic_pass"):
            ValidationVerdict(
                status=VERDICT_APPROVED,
                rationale="ok",
                confidence=0.9,
                deterministic_pass=False,
            )

    def test_invalid_safety_assessment_rejected(self) -> None:
        with pytest.raises(ValueError, match="safety_assessment"):
            ValidationVerdict(
                status=VERDICT_APPROVED,
                rationale="ok",
                confidence=0.9,
                safety_assessment="invalid",
            )

    def test_revise_with_suggested_fixes(self) -> None:
        v = ValidationVerdict(
            status=VERDICT_REVISE,
            rationale="needs fix",
            confidence=0.5,
            issues=[
                ValidationIssue(
                    check_name="test",
                    severity=SEVERITY_WARNING,
                    detail="test",
                )
            ],
            suggested_fixes=["Fix A", "Fix B"],
        )
        assert v.suggested_fixes == ["Fix A", "Fix B"]


# ===========================================================================
# 10. Module Constants & Schema
# ===========================================================================


class TestModuleConstants:
    """Module-level constants are correctly defined."""

    def test_verdict_schema_has_required_fields(self) -> None:
        required = VALIDATE_VERDICT_SCHEMA["required"]
        assert "status" in required
        assert "reasons" in required
        assert "coherence_score" in required
        assert "safety_assessment" in required
        assert "completeness" in required

    def test_verdict_schema_status_enum(self) -> None:
        props = VALIDATE_VERDICT_SCHEMA["properties"]
        assert set(props["status"]["enum"]) == {"approved", "revise", "reject"}

    def test_arbiter_constants(self) -> None:
        assert _ARBITER_MAX_TOKENS == 512
        assert _ARBITER_TIMEOUT_MS == 3000
        assert _ARBITER_TEMPERATURE == pytest.approx(0.1)

    def test_micro_constants(self) -> None:
        assert _MICRO_ARBITER_MAX_TOKENS == 256
        assert _MICRO_ARBITER_TIMEOUT_MS == 2000


# ===========================================================================
# 11. Dependency Layer Validation
# ===========================================================================


class TestDependencyLayer:
    """ValidateService is Layer 2 -- correct import boundaries."""

    def test_imports_ilmport_from_layer1(self) -> None:
        source = Path(inspect.getfile(ValidateService)).read_text(encoding="utf-8")
        assert "from k1.planner.ports.llm_port import ILLMPort" in source

    def test_imports_fabric_port_from_layer1(self) -> None:
        source = Path(inspect.getfile(ValidateService)).read_text(encoding="utf-8")
        assert "from k1.planner.ports.fabric_retrieval_port import IFabricRetrievalPort" in source

    def test_imports_types_from_layer0(self) -> None:
        source = Path(inspect.getfile(ValidateService)).read_text(encoding="utf-8")
        assert "from k1.planner.types import" in source

    def test_no_tool_call_router_import(self) -> None:
        """ValidateService must NOT import ToolCallRouter."""
        source = Path(inspect.getfile(ValidateService)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_names = [alias.name for alias in (node.names or [])]
                assert (
                    "ToolCallRouter" not in imported_names
                ), f"Found 'ToolCallRouter' import in {node.module}"

    def test_no_layer3_imports(self) -> None:
        """Layer 2 must NOT import Layer 3 (PlannerAgent)."""
        source = Path(inspect.getfile(ValidateService)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "planner_agent" not in node.module
                assert "pipeline_controller" not in node.module

    def test_no_circular_stage_imports(self) -> None:
        """ValidateService must NOT import other stage services."""
        source = Path(inspect.getfile(ValidateService)).read_text(encoding="utf-8")
        assert "sketch_service" not in source
        assert "expand_service" not in source
        assert "commit_service" not in source
