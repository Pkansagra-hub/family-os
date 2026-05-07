"""Tests for micro-VALIDATE cross-boundary validation (Issue 5.1.4).

Validates the abbreviated VALIDATE stage for micro-replan:
  - Cross-boundary inter-step references to completed steps pass
  - Cross-boundary dangling deps become warnings (not errors)
  - Deterministic pass when only cross-boundary refs present
  - Real errors (cycle, self-ref, dangling to unknown) still flagged
  - Revise -> approved upgrade
  - Arbiter failure -> auto-approve
  - No HIL in micro-execute
  - Pipeline controller passes completed_step_ids

References
----------
- planner.md Section 10.3.4 (Micro-VALIDATE)
- planner.md Section 10.5.1 (PLAN-12)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from k1.orchestrator.types import PlanStep
from k1.planner.stages.validate_service import ValidateService
from k1.planner.types import (
    CHECK_DAG_CYCLE,
    CHECK_DANGLING_DEPENDENCY,
    CHECK_INTER_STEP_REF,
    CHECK_SELF_REFERENCE,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    VERDICT_APPROVED,
    VERDICT_REJECT,
    ExpandedPlan,
    HubRequest,
    HubResponse,
    StageContext,
    ValidateRejectedError,
)

# ===========================================================================
# Fakes
# ===========================================================================


class FakeLLMPort:
    """Configurable fake ILLMPort."""

    def __init__(self) -> None:
        self.calls: List[HubRequest] = []
        self.response: Optional[HubResponse] = None
        self.error: Optional[Exception] = None

    def set_approved(self, score: float = 0.95) -> None:
        self.response = HubResponse(
            result={
                "content": json.dumps(
                    {
                        "status": "approved",
                        "reasons": ["Plan is coherent"],
                        "suggested_fixes": [],
                        "coherence_score": score,
                        "safety_assessment": "safe",
                        "completeness": True,
                    }
                ),
            },
            metadata={"usage": {"total_tokens": 80}},
        )

    def set_revise(self) -> None:
        self.response = HubResponse(
            result={
                "content": json.dumps(
                    {
                        "status": "revise",
                        "reasons": ["Minor param issue"],
                        "suggested_fixes": ["Fix param X"],
                        "coherence_score": 0.6,
                        "safety_assessment": "safe",
                        "completeness": True,
                    }
                ),
            },
            metadata={"usage": {"total_tokens": 90}},
        )

    def set_reject(self) -> None:
        self.response = HubResponse(
            result={
                "content": json.dumps(
                    {
                        "status": "reject",
                        "reasons": ["Fundamentally flawed"],
                        "suggested_fixes": [],
                        "coherence_score": 0.1,
                        "safety_assessment": "unsafe",
                        "completeness": False,
                    }
                ),
            },
            metadata={"usage": {"total_tokens": 85}},
        )

    async def execute(self, request: HubRequest) -> HubResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        if self.response is not None:
            return self.response
        # Default: approved
        return HubResponse(
            result={
                "content": json.dumps(
                    {
                        "status": "approved",
                        "reasons": ["OK"],
                        "suggested_fixes": [],
                        "coherence_score": 0.9,
                        "safety_assessment": "safe",
                        "completeness": True,
                    }
                ),
            },
            metadata={"usage": {"total_tokens": 50}},
        )


class FakeFabricRetrieval:
    """Minimal fake IFabricRetrievalPort."""

    async def discover_capabilities(self, **kwargs: Any) -> Any:
        return None

    async def find_relevant_prompts(self, **kwargs: Any) -> Any:
        return None


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


def _never_cancel() -> bool:
    return False


def _ctx(
    request_id: str = "req-micro-1",
    trace_id: str = "trace-micro-1",
    timeout_ms: int = 2000,
    token_budget: int = 256,
) -> StageContext:
    return StageContext(
        request_id=request_id,
        trace_id=trace_id,
        timeout_remaining_ms=timeout_ms,
        token_budget_remaining=token_budget,
        cancel_check=_never_cancel,
    )


def _step(
    sid: str = "r1",
    cap: str = "cap.test",
    **params: Any,
) -> PlanStep:
    return PlanStep(id=sid, capability=cap, params=params)


def _plan(
    steps: Optional[List[PlanStep]] = None,
    deps: Optional[Dict[str, List[str]]] = None,
) -> ExpandedPlan:
    if steps is None:
        steps = [_step("r1"), _step("r2")]
    if deps is None:
        deps = {s.id: [] for s in steps}
    return ExpandedPlan(
        steps=steps,
        dependencies=deps,
        tool_mappings={s.id: s.capability for s in steps},
        rationale="micro-replan test",
    )


def _build_svc(
    llm: Optional[FakeLLMPort] = None,
) -> tuple[ValidateService, FakeLLMPort, FakeHILCoordinator]:
    """Build ValidateService with fakes; returns (svc, llm, hil)."""
    llm_port = llm or FakeLLMPort()
    fab = FakeFabricRetrieval()
    hil = FakeHILCoordinator()
    svc = ValidateService(llm_port, fab, hil)
    return svc, llm_port, hil


# ===========================================================================
# A. Cross-boundary inter-step references (5.1.4 core)
# ===========================================================================


class TestCrossBoundaryInterStepRef:
    """Inter-step refs ($completed.result.*) allowed when completed_step_ids provided."""

    def test_ref_to_completed_step_not_error(self):
        """$s1.result.data.venue passes when s1 is in completed_step_ids."""
        svc, _, _ = _build_svc()
        plan = _plan(
            steps=[_step("r1", "cap.test", venue_id="$s1.result.data.venue")],
            deps={"r1": []},
        )
        _, issues = svc._check_dag_acyclicity(
            plan.steps,
            plan.dependencies,
            completed_step_ids={"s1", "s2"},
        )
        error_issues = [i for i in issues if i.severity == SEVERITY_ERROR]
        assert len(error_issues) == 0

    def test_ref_to_completed_no_inter_step_ref_issue(self):
        """No CHECK_INTER_STEP_REF error for ref to completed step."""
        svc, _, _ = _build_svc()
        plan = _plan(
            steps=[_step("r1", "cap.test", data="$s2.result.output")],
            deps={"r1": []},
        )
        _, issues = svc._check_dag_acyclicity(
            plan.steps,
            plan.dependencies,
            completed_step_ids={"s2"},
        )
        ref_errors = [
            i
            for i in issues
            if i.check_name == CHECK_INTER_STEP_REF and i.severity == SEVERITY_ERROR
        ]
        assert len(ref_errors) == 0

    def test_ref_to_unknown_step_still_error(self):
        """$unknown.result.data is error when unknown not in completed or deps."""
        svc, _, _ = _build_svc()
        plan = _plan(
            steps=[_step("r1", "cap.test", data="$unknown.result.data")],
            deps={"r1": []},
        )
        _, issues = svc._check_dag_acyclicity(
            plan.steps,
            plan.dependencies,
            completed_step_ids={"s1"},
        )
        ref_errors = [
            i
            for i in issues
            if i.check_name == CHECK_INTER_STEP_REF and i.severity == SEVERITY_ERROR
        ]
        assert len(ref_errors) == 1
        assert "unknown" in ref_errors[0].detail

    def test_ref_to_intra_plan_dep_still_works(self):
        """$r2.result.data passes with intra-plan dep, no completed_step_ids."""
        svc, _, _ = _build_svc()
        plan = _plan(
            steps=[
                _step("r1", "cap.a"),
                _step("r2", "cap.b", prev="$r1.result.data"),
            ],
            deps={"r1": [], "r2": ["r1"]},
        )
        _, issues = svc._check_dag_acyclicity(
            plan.steps,
            plan.dependencies,
        )
        error_issues = [i for i in issues if i.severity == SEVERITY_ERROR]
        assert len(error_issues) == 0

    def test_ref_to_intra_plan_without_dep_still_error(self):
        """$r1.result.data without dep entry is error even with completed set."""
        svc, _, _ = _build_svc()
        plan = _plan(
            steps=[
                _step("r1", "cap.a"),
                _step("r2", "cap.b", prev="$r1.result.data"),
            ],
            deps={"r1": [], "r2": []},  # Missing dep to r1
        )
        _, issues = svc._check_dag_acyclicity(
            plan.steps,
            plan.dependencies,
            completed_step_ids={"s1"},
        )
        ref_errors = [
            i
            for i in issues
            if i.check_name == CHECK_INTER_STEP_REF and i.severity == SEVERITY_ERROR
        ]
        assert len(ref_errors) == 1

    def test_multiple_refs_to_different_completed_steps(self):
        """Multiple params referencing different completed steps all pass."""
        svc, _, _ = _build_svc()
        plan = _plan(
            steps=[
                _step(
                    "r1",
                    "cap.test",
                    venue="$s1.result.data.venue",
                    date="$s2.result.data.date",
                ),
            ],
            deps={"r1": []},
        )
        _, issues = svc._check_dag_acyclicity(
            plan.steps,
            plan.dependencies,
            completed_step_ids={"s1", "s2"},
        )
        error_issues = [i for i in issues if i.severity == SEVERITY_ERROR]
        assert len(error_issues) == 0


# ===========================================================================
# B. Cross-boundary dangling dependencies (5.1.4)
# ===========================================================================


class TestCrossBoundaryDanglingDeps:
    """Dangling deps to completed step IDs become warnings, not errors."""

    def test_dep_to_completed_step_is_warning(self):
        """Dep to completed step ID: SEVERITY_WARNING, not ERROR."""
        svc, _, _ = _build_svc()
        # NOTE: ExpandedPlan __post_init__ rejects deps not in step_ids,
        # so this tests _check_dag_acyclicity directly.
        steps = [_step("r1")]
        deps = {"r1": ["s1"]}  # s1 is completed, not in plan
        _, issues = svc._check_dag_acyclicity(
            steps,
            deps,
            completed_step_ids={"s1"},
        )
        dangling = [i for i in issues if i.check_name == CHECK_DANGLING_DEPENDENCY]
        assert len(dangling) == 1
        assert dangling[0].severity == SEVERITY_WARNING
        assert "cross-boundary" in dangling[0].detail

    def test_dep_to_unknown_step_is_error(self):
        """Dep to truly unknown step: SEVERITY_ERROR."""
        svc, _, _ = _build_svc()
        steps = [_step("r1")]
        deps = {"r1": ["nonexistent"]}
        _, issues = svc._check_dag_acyclicity(
            steps,
            deps,
            completed_step_ids={"s1"},
        )
        dangling = [i for i in issues if i.check_name == CHECK_DANGLING_DEPENDENCY]
        assert len(dangling) == 1
        assert dangling[0].severity == SEVERITY_ERROR

    def test_dep_to_completed_does_not_block_deterministic_pass(self):
        """Warning-level cross-boundary dep does not block deterministic pass."""
        svc, _, _ = _build_svc()
        steps = [_step("r1")]
        deps = {"r1": ["s1"]}
        passed, issues = svc._check_dag_acyclicity(
            steps,
            deps,
            completed_step_ids={"s1"},
        )
        assert passed is True

    def test_without_completed_ids_dep_is_error(self):
        """Without completed_step_ids, any dangling dep is ERROR (full pipeline)."""
        svc, _, _ = _build_svc()
        steps = [_step("r1")]
        deps = {"r1": ["s1"]}
        passed, issues = svc._check_dag_acyclicity(
            steps,
            deps,
        )
        dangling = [i for i in issues if i.check_name == CHECK_DANGLING_DEPENDENCY]
        assert len(dangling) == 1
        assert dangling[0].severity == SEVERITY_ERROR
        assert passed is False


# ===========================================================================
# C. Structural errors still detected in micro context
# ===========================================================================


class TestStructuralErrorsStillDetected:
    """Real structural errors are not suppressed by completed_step_ids."""

    def test_cycle_still_detected(self):
        """DAG cycle is still an error even with completed_step_ids."""
        svc, _, _ = _build_svc()
        steps = [_step("r1"), _step("r2")]
        deps = {"r1": ["r2"], "r2": ["r1"]}
        passed, issues = svc._check_dag_acyclicity(
            steps,
            deps,
            completed_step_ids={"s1"},
        )
        cycle_errors = [i for i in issues if i.check_name == CHECK_DAG_CYCLE]
        assert len(cycle_errors) == 1
        assert passed is False

    def test_self_reference_still_detected(self):
        """Self-reference is still an error."""
        svc, _, _ = _build_svc()
        steps = [_step("r1")]
        deps = {"r1": ["r1"]}
        passed, issues = svc._check_dag_acyclicity(
            steps,
            deps,
            completed_step_ids={"s1"},
        )
        self_ref = [i for i in issues if i.check_name == CHECK_SELF_REFERENCE]
        assert len(self_ref) == 1
        assert passed is False

    def test_duplicate_step_id_still_detected(self):
        """Duplicate step IDs are still an error."""
        svc, _, _ = _build_svc()
        steps = [_step("r1"), _step("r1")]
        deps = {"r1": []}
        passed, issues = svc._check_dag_acyclicity(
            steps,
            deps,
            completed_step_ids={"s1"},
        )
        dup_errors = [
            i
            for i in issues
            if i.check_name == "step_id_duplicate" and i.severity == SEVERITY_ERROR
        ]
        assert len(dup_errors) >= 1
        assert passed is False


# ===========================================================================
# D. micro_execute end-to-end (5.1.4)
# ===========================================================================


class TestMicroExecuteEndToEnd:
    """End-to-end micro_execute with cross-boundary validation."""

    async def test_approved_with_cross_boundary_ref(self):
        """micro_execute approves plan with $completed.result ref."""
        svc, llm, _ = _build_svc()
        llm.set_approved()
        plan = _plan(
            steps=[_step("r1", "cap.test", venue="$s1.result.data.venue")],
            deps={"r1": []},
        )
        verdict = await svc.micro_execute(
            plan,
            _ctx(),
            completed_step_ids={"s1", "s2"},
        )
        assert verdict.status == VERDICT_APPROVED

    async def test_reject_on_real_structural_error(self):
        """micro_execute rejects plan with real errors (cycle)."""
        svc, llm, _ = _build_svc()
        llm.set_approved()
        plan = _plan(
            steps=[_step("r1"), _step("r2")],
            deps={"r1": ["r2"], "r2": ["r1"]},
        )
        verdict = await svc.micro_execute(
            plan,
            _ctx(),
            completed_step_ids={"s1"},
        )
        assert verdict.status == VERDICT_REJECT
        assert verdict.deterministic_pass is False

    async def test_revise_upgraded_to_approved(self):
        """micro_execute: 'revise' verdict becomes 'approved'."""
        svc, llm, _ = _build_svc()
        llm.set_revise()
        plan = _plan()
        verdict = await svc.micro_execute(plan, _ctx())
        assert verdict.status == VERDICT_APPROVED
        assert "best-effort" in verdict.rationale.lower()

    async def test_reject_from_arbiter_passes_through(self):
        """micro_execute: 'reject' verdict passes through unchanged."""
        svc, llm, _ = _build_svc()
        llm.set_reject()
        plan = _plan()
        verdict = await svc.micro_execute(plan, _ctx())
        assert verdict.status == VERDICT_REJECT

    async def test_arbiter_failure_auto_approves(self):
        """micro_execute: arbiter exception -> auto-approve."""
        svc, llm, _ = _build_svc()
        llm.error = RuntimeError("LLM timeout")
        plan = _plan()
        verdict = await svc.micro_execute(plan, _ctx())
        assert verdict.status == VERDICT_APPROVED
        assert verdict.confidence == 0.0
        assert "arbiter unavailable" in verdict.rationale.lower()

    async def test_no_hil_in_micro_execute(self):
        """micro_execute never calls HIL approval."""
        svc, llm, hil = _build_svc()
        llm.set_approved(score=0.95)
        # Plan with side effects and non-GREEN safety -- would trigger HIL
        # in full execute(), but micro_execute MUST NOT.
        plan = _plan(
            steps=[
                PlanStep(
                    id="r1",
                    capability="cap.dangerous",
                    params={},
                    has_side_effects=True,
                    safety_band_min="AMBER",
                ),
            ],
            deps={"r1": []},
        )
        verdict = await svc.micro_execute(plan, _ctx())
        assert verdict.status == VERDICT_APPROVED
        assert len(hil.approval_calls) == 0

    async def test_completed_step_ids_none_default_behavior(self):
        """micro_execute without completed_step_ids: normal behavior."""
        svc, llm, _ = _build_svc()
        llm.set_approved()
        plan = _plan()
        verdict = await svc.micro_execute(plan, _ctx())
        assert verdict.status == VERDICT_APPROVED

    async def test_arbiter_called_with_is_micro_true(self):
        """micro_execute calls arbiter with micro constraints."""
        svc, llm, _ = _build_svc()
        llm.set_approved()
        plan = _plan()
        await svc.micro_execute(plan, _ctx())
        # Arbiter should have been called
        assert len(llm.calls) == 1
        req = llm.calls[0]
        # Micro constraints: 256 tokens, 2000ms
        assert req.constraints.max_tokens == 256
        assert req.constraints.timeout_ms == 2000

    async def test_validate_rejected_error_reraises(self):
        """ValidateRejectedError propagates (never swallowed)."""
        svc, llm, _ = _build_svc()
        llm.error = ValidateRejectedError(
            "cancelled",
            stage="VALIDATE",
            request_id="req-1",
            trace_id="trace-1",
        )
        plan = _plan()
        with pytest.raises(ValidateRejectedError):
            await svc.micro_execute(plan, _ctx())


# ===========================================================================
# E. Pipeline controller integration: completed_step_ids passed through
# ===========================================================================


class TestPipelineControllerPassesCompletedIds:
    """Verify pipeline_controller passes completed_step_ids to micro_execute."""

    async def test_micro_replan_passes_completed_ids_to_validate(self):
        """Step 11 of micro_replan passes completed_ids to micro_execute."""
        # Use the pipeline controller with fakes from the 5.1 test file.
        # Import here to avoid circular dependency issues.
        from tests.k1.planner.test_planner_micro_replan_5_1 import (
            _approved_verdict,
            _build_controller,
            _committed_plan,
            _expanded_plan,
            _micro_request,
            _no_cancel,
            _sketch_result,
        )

        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        req = _micro_request()
        await ctrl.micro_replan(req, _no_cancel)

        # Verify completed_step_ids was passed
        assert len(fakes["validate"].micro_execute_calls) == 1
        call = fakes["validate"].micro_execute_calls[0]
        assert "completed_step_ids" in call
        # completed_step_ids should contain the keys from completed_results
        assert call["completed_step_ids"] == set(req.completed_results.keys())

    async def test_completed_ids_match_request(self):
        """completed_step_ids matches MicroReplanRequest.completed_results keys."""
        from tests.k1.planner.test_planner_micro_replan_5_1 import (
            _approved_verdict,
            _build_controller,
            _committed_plan,
            _completed_result,
            _expanded_plan,
            _micro_request,
            _no_cancel,
            _sketch_result,
        )

        ctrl, fakes = _build_controller()
        fakes["sketch"].micro_result = _sketch_result()
        fakes["expand"].micro_result = _expanded_plan()
        fakes["validate"].micro_result = _approved_verdict()
        fakes["commit"].result = _committed_plan()

        # Custom completed results with specific IDs
        req = _micro_request(
            completed={
                "step_A": _completed_result("step_A"),
                "step_B": _completed_result("step_B"),
                "step_C": _completed_result("step_C"),
            },
        )
        await ctrl.micro_replan(req, _no_cancel)

        call = fakes["validate"].micro_execute_calls[0]
        assert call["completed_step_ids"] == {"step_A", "step_B", "step_C"}
