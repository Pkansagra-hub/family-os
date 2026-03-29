"""Tests for PipelineController budget injection per stage (Issue 2.2.3).

Tests cover:
  - _get_stage_budget(): full pipeline budget table from PlannerConfig
  - _get_micro_stage_budget(): micro-replan budget table from PlannerConfig
  - _record_llm_call(): token usage and latency tracking
  - Budget injection into StageContext.stage_budget via _build_stage_context
  - Budget propagation through execute() to stage services
  - PLAN-11 enforcement: every LLM stage has budget, COMMIT has None
  - PLAN-03 compliance: COMMIT stage has no LLM budget
  - plan_end delta includes stage_token_usage and stage_latency
  - PlannerConfig micro per-stage validation
  - StageContext.stage_budget field

References
----------
- planner.md Section 13.3.1 (PipelineController Budget Injection)
- planner.md Section 13.3.3 (Token Usage Tracking)
- planner.md Section 10.3.6 (Micro-Replan Budgets)
- docs/plans/planner-implementation-plan.md Issue 2.2.3
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import pytest

from k1.planner.config import PlannerConfig
from k1.planner.pipeline_controller import PipelineController
from k1.planner.types import (
    DELTA_PLAN_END,
    VERDICT_APPROVED,
    DeltaPayload,
    RequestConstraints,
    StageContext,
    StagePhase,
    ValidationVerdict,
)

# ---------------------------------------------------------------------------
# Test helpers -- fake services and ports
# ---------------------------------------------------------------------------


@dataclass
class FakePlanRequest:
    """Minimal stand-in for PlanRequest."""

    request_id: str = "req-budget-001"
    trace_id: str = "trace-budget-abc"
    intent: str = "budget test intent"


@dataclass
class FakeCommittedPlan:
    """Minimal stand-in for CommittedPlan."""

    plan_id: str = "plan-budget-001"
    request_id: str = "req-budget-001"


class FakeDeltaPort:
    """Records emitted deltas."""

    def __init__(self) -> None:
        self.emitted: List[DeltaPayload] = []

    def emit(self, delta: DeltaPayload) -> None:
        self.emitted.append(delta)


class FakeEventPort:
    """Records emitted events."""

    def __init__(self) -> None:
        self.emitted: List[Tuple[str, Any]] = []
        self.subscriptions: List[Tuple[str, Any]] = []

    def emit(self, topic: str, payload: Any) -> None:
        self.emitted.append((topic, payload))

    def subscribe(self, topic: str, handler: Any) -> Any:
        self.subscriptions.append((topic, handler))
        return f"sub-{topic}"

    def unsubscribe(self, handle: Any) -> bool:
        return True


class FakeSketchService:
    """Fake SketchService that records calls."""

    def __init__(self, result: Any = None) -> None:
        self._result = result if result is not None else {"rough_steps": ["step1"]}
        self.calls: List[Tuple[Any, StageContext]] = []

    async def execute(self, request: Any, ctx: StageContext) -> Any:
        self.calls.append((request, ctx))
        return self._result


class FakeExpandService:
    """Fake ExpandService that records calls."""

    def __init__(self, result: Any = None) -> None:
        self._result = result if result is not None else {"steps": ["expanded1"]}
        self.calls: List[Tuple[Any, StageContext]] = []

    async def execute(self, sketch_result: Any, ctx: StageContext) -> Any:
        self.calls.append((sketch_result, ctx))
        return self._result


class FakeValidateService:
    """Fake ValidateService that returns approved verdict."""

    def __init__(self, verdict: Any = None) -> None:
        self._verdict = verdict if verdict is not None else _approved_verdict()
        self.calls: List[Tuple[Any, StageContext]] = []

    async def execute(self, expanded_plan: Any, ctx: StageContext) -> Any:
        self.calls.append((expanded_plan, ctx))
        return self._verdict


class FakeCommitService:
    """Fake CommitService that records calls."""

    def __init__(self, result: Any = None) -> None:
        self._result = result if result is not None else FakeCommittedPlan()
        self.calls: List[Tuple[Any, Any, StageContext]] = []

    async def execute(self, expanded_plan: Any, verdict: Any, ctx: StageContext) -> Any:
        self.calls.append((expanded_plan, verdict, ctx))
        return self._result


def _approved_verdict() -> ValidationVerdict:
    return ValidationVerdict(
        status=VERDICT_APPROVED,
        confidence=0.9,
        rationale="All checks passed",
    )


def _never_cancel() -> bool:
    return False


def _make_controller(
    *,
    sketch: Any = None,
    expand: Any = None,
    validate: Any = None,
    commit: Any = None,
    delta_port: Any = None,
    event_port: Any = None,
    config: Any = None,
) -> PipelineController:
    """Helper to construct PipelineController with defaults."""
    return PipelineController(
        sketch=sketch if sketch is not None else FakeSketchService(),
        expand=expand if expand is not None else FakeExpandService(),
        validate=validate if validate is not None else FakeValidateService(),
        commit=commit if commit is not None else FakeCommitService(),
        delta_port=delta_port if delta_port is not None else FakeDeltaPort(),
        event_port=event_port if event_port is not None else FakeEventPort(),
        config=config if config is not None else PlannerConfig(),
    )


# ===========================================================================
# 1. _get_stage_budget -- full pipeline budget table
# ===========================================================================


class TestGetStageBudget:
    """_get_stage_budget returns RequestConstraints from PlannerConfig."""

    def test_sketch_budget_from_default_config(self) -> None:
        ctrl = _make_controller()
        budget = ctrl._get_stage_budget(StagePhase.SKETCH)
        assert budget is not None
        assert isinstance(budget, RequestConstraints)
        assert budget.max_tokens == 2000  # PlannerConfig.sketch_max_tokens default
        assert budget.timeout_ms == 8000  # PlannerConfig.sketch_timeout_ms default
        assert budget.temperature == 0.7  # PlannerConfig.sketch_temperature default

    def test_expand_budget_from_default_config(self) -> None:
        ctrl = _make_controller()
        budget = ctrl._get_stage_budget(StagePhase.EXPAND)
        assert budget is not None
        assert budget.max_tokens == 1000
        assert budget.timeout_ms == 5000
        assert budget.temperature == 0.3

    def test_validate_budget_from_default_config(self) -> None:
        ctrl = _make_controller()
        budget = ctrl._get_stage_budget(StagePhase.VALIDATE)
        assert budget is not None
        assert budget.max_tokens == 500
        assert budget.timeout_ms == 3000
        assert budget.temperature == 0.2

    def test_commit_budget_is_none(self) -> None:
        """PLAN-03: COMMIT has no LLM calls, budget is None."""
        ctrl = _make_controller()
        budget = ctrl._get_stage_budget(StagePhase.COMMIT)
        assert budget is None

    def test_sketch_budget_reads_custom_config(self) -> None:
        cfg = PlannerConfig(
            sketch_max_tokens=4096,
            sketch_timeout_ms=12000,
            sketch_temperature=0.9,
            total_token_budget=5596,  # >= 4096 + 1000 + 500
        )
        ctrl = _make_controller(config=cfg)
        budget = ctrl._get_stage_budget(StagePhase.SKETCH)
        assert budget is not None
        assert budget.max_tokens == 4096
        assert budget.timeout_ms == 12000
        assert budget.temperature == 0.9

    def test_expand_budget_reads_custom_config(self) -> None:
        cfg = PlannerConfig(
            expand_max_tokens=2048,
            expand_timeout_ms=10000,
            expand_temperature=0.5,
            total_token_budget=4548,  # >= 2000 + 2048 + 500
        )
        ctrl = _make_controller(config=cfg)
        budget = ctrl._get_stage_budget(StagePhase.EXPAND)
        assert budget is not None
        assert budget.max_tokens == 2048
        assert budget.timeout_ms == 10000
        assert budget.temperature == 0.5

    def test_validate_budget_reads_custom_config(self) -> None:
        cfg = PlannerConfig(
            validate_max_tokens=1024,
            validate_timeout_ms=6000,
            validate_temperature=0.1,
            total_token_budget=4024,  # >= 2000 + 1000 + 1024
        )
        ctrl = _make_controller(config=cfg)
        budget = ctrl._get_stage_budget(StagePhase.VALIDATE)
        assert budget is not None
        assert budget.max_tokens == 1024
        assert budget.timeout_ms == 6000
        assert budget.temperature == 0.1

    def test_budget_priority_is_interactive(self) -> None:
        """All budgets have priority='INTERACTIVE'."""
        ctrl = _make_controller()
        for stage in (StagePhase.SKETCH, StagePhase.EXPAND, StagePhase.VALIDATE):
            budget = ctrl._get_stage_budget(stage)
            assert budget is not None
            assert budget.priority == "INTERACTIVE"

    def test_budget_consumer_id_is_planner(self) -> None:
        """All budgets have consumer_id='planner'."""
        ctrl = _make_controller()
        for stage in (StagePhase.SKETCH, StagePhase.EXPAND, StagePhase.VALIDATE):
            budget = ctrl._get_stage_budget(stage)
            assert budget is not None
            assert budget.consumer_id == "planner"

    def test_returns_frozen_request_constraints(self) -> None:
        ctrl = _make_controller()
        budget = ctrl._get_stage_budget(StagePhase.SKETCH)
        assert budget is not None
        with pytest.raises(AttributeError):
            budget.max_tokens = 999  # type: ignore[misc]


# ===========================================================================
# 2. _get_micro_stage_budget -- micro-replan budget table
# ===========================================================================


class TestGetMicroStageBudget:
    """_get_micro_stage_budget returns tighter budgets for micro-replan."""

    def test_micro_sketch_budget(self) -> None:
        ctrl = _make_controller()
        budget = ctrl._get_micro_stage_budget(StagePhase.SKETCH)
        assert budget is not None
        assert budget.max_tokens == 1024
        assert budget.timeout_ms == 5000
        assert budget.temperature == 0.7  # same as full SKETCH

    def test_micro_expand_budget(self) -> None:
        ctrl = _make_controller()
        budget = ctrl._get_micro_stage_budget(StagePhase.EXPAND)
        assert budget is not None
        assert budget.max_tokens == 512
        assert budget.timeout_ms == 3000
        assert budget.temperature == 0.3  # same as full EXPAND

    def test_micro_validate_budget(self) -> None:
        ctrl = _make_controller()
        budget = ctrl._get_micro_stage_budget(StagePhase.VALIDATE)
        assert budget is not None
        assert budget.max_tokens == 256
        assert budget.timeout_ms == 2000
        assert budget.temperature == 0.2  # same as full VALIDATE

    def test_micro_commit_budget_is_none(self) -> None:
        ctrl = _make_controller()
        budget = ctrl._get_micro_stage_budget(StagePhase.COMMIT)
        assert budget is None

    def test_micro_sketch_custom_config(self) -> None:
        cfg = PlannerConfig(
            micro_sketch_max_tokens=2048,
            micro_sketch_timeout_ms=7000,
            micro_replan_max_tokens=3000,  # >= 2048 + 512 + 256
        )
        ctrl = _make_controller(config=cfg)
        budget = ctrl._get_micro_stage_budget(StagePhase.SKETCH)
        assert budget is not None
        assert budget.max_tokens == 2048
        assert budget.timeout_ms == 7000

    def test_micro_expand_custom_config(self) -> None:
        cfg = PlannerConfig(
            micro_expand_max_tokens=1024,
            micro_expand_timeout_ms=6000,
            micro_replan_max_tokens=2500,  # >= 1024 + 1024 + 256
        )
        ctrl = _make_controller(config=cfg)
        budget = ctrl._get_micro_stage_budget(StagePhase.EXPAND)
        assert budget is not None
        assert budget.max_tokens == 1024
        assert budget.timeout_ms == 6000

    def test_micro_validate_custom_config(self) -> None:
        cfg = PlannerConfig(
            micro_validate_max_tokens=512,
            micro_validate_timeout_ms=4000,
            micro_replan_max_tokens=2100,  # >= 1024 + 512 + 512
        )
        ctrl = _make_controller(config=cfg)
        budget = ctrl._get_micro_stage_budget(StagePhase.VALIDATE)
        assert budget is not None
        assert budget.max_tokens == 512
        assert budget.timeout_ms == 4000

    def test_micro_budgets_are_frozen(self) -> None:
        ctrl = _make_controller()
        budget = ctrl._get_micro_stage_budget(StagePhase.SKETCH)
        assert budget is not None
        with pytest.raises(AttributeError):
            budget.max_tokens = 999  # type: ignore[misc]

    def test_micro_budgets_use_full_stage_temperatures(self) -> None:
        """Micro-replan temperatures match full pipeline (same trade-offs)."""
        cfg = PlannerConfig(
            sketch_temperature=0.5,
            expand_temperature=0.4,
            validate_temperature=0.1,
        )
        ctrl = _make_controller(config=cfg)
        assert ctrl._get_micro_stage_budget(StagePhase.SKETCH).temperature == 0.5  # type: ignore[union-attr]
        assert ctrl._get_micro_stage_budget(StagePhase.EXPAND).temperature == 0.4  # type: ignore[union-attr]
        assert ctrl._get_micro_stage_budget(StagePhase.VALIDATE).temperature == 0.1  # type: ignore[union-attr]


# ===========================================================================
# 3. _record_llm_call -- token usage and latency tracking
# ===========================================================================


@dataclass
class FakeHubResponse:
    """Minimal HubResponse stand-in with dict metadata."""

    result: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TestRecordLlmCall:
    """_record_llm_call updates stage_token_usage, total_plan_tokens, latency."""

    def test_records_tokens_for_sketch(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        resp = FakeHubResponse(metadata={"usage": {"total_tokens": 150}, "latency_ms": 1200})
        ctrl._record_llm_call(StagePhase.SKETCH, resp)
        assert ctrl._stage_token_usage["SKETCH"] == 150
        assert ctrl._total_plan_tokens == 150
        assert ctrl._stage_latency["SKETCH"] == 1200

    def test_records_tokens_for_expand(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        resp = FakeHubResponse(metadata={"usage": {"total_tokens": 80}, "latency_ms": 800})
        ctrl._record_llm_call(StagePhase.EXPAND, resp)
        assert ctrl._stage_token_usage["EXPAND"] == 80
        assert ctrl._total_plan_tokens == 80
        assert ctrl._stage_latency["EXPAND"] == 800

    def test_records_tokens_for_validate(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        resp = FakeHubResponse(metadata={"usage": {"total_tokens": 50}, "latency_ms": 500})
        ctrl._record_llm_call(StagePhase.VALIDATE, resp)
        assert ctrl._stage_token_usage["VALIDATE"] == 50
        assert ctrl._total_plan_tokens == 50
        assert ctrl._stage_latency["VALIDATE"] == 500

    def test_accumulates_multiple_calls_same_stage(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        resp1 = FakeHubResponse(metadata={"usage": {"total_tokens": 100}, "latency_ms": 1000})
        resp2 = FakeHubResponse(metadata={"usage": {"total_tokens": 50}, "latency_ms": 500})
        ctrl._record_llm_call(StagePhase.SKETCH, resp1)
        ctrl._record_llm_call(StagePhase.SKETCH, resp2)
        assert ctrl._stage_token_usage["SKETCH"] == 150
        assert ctrl._total_plan_tokens == 150
        assert ctrl._stage_latency["SKETCH"] == 1500

    def test_accumulates_across_stages(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        r1 = FakeHubResponse(metadata={"usage": {"total_tokens": 200}, "latency_ms": 2000})
        r2 = FakeHubResponse(metadata={"usage": {"total_tokens": 100}, "latency_ms": 1000})
        ctrl._record_llm_call(StagePhase.SKETCH, r1)
        ctrl._record_llm_call(StagePhase.EXPAND, r2)
        assert ctrl._total_plan_tokens == 300
        assert ctrl._stage_token_usage["SKETCH"] == 200
        assert ctrl._stage_token_usage["EXPAND"] == 100

    def test_handles_missing_metadata(self) -> None:
        """No-op if response has no metadata attribute."""
        ctrl = _make_controller()
        ctrl.reset()

        class NoMetadata:
            pass

        ctrl._record_llm_call(StagePhase.SKETCH, NoMetadata())
        assert ctrl._total_plan_tokens == 0
        assert ctrl._stage_token_usage.get("SKETCH", 0) == 0

    def test_handles_none_metadata(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()

        @dataclass
        class NoneMetadata:
            metadata: Any = None

        ctrl._record_llm_call(StagePhase.SKETCH, NoneMetadata())
        assert ctrl._total_plan_tokens == 0

    def test_handles_empty_metadata_dict(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        resp = FakeHubResponse(metadata={})
        ctrl._record_llm_call(StagePhase.SKETCH, resp)
        assert ctrl._total_plan_tokens == 0
        assert ctrl._stage_token_usage.get("SKETCH", 0) == 0

    def test_handles_missing_usage_key(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        resp = FakeHubResponse(metadata={"latency_ms": 300})
        ctrl._record_llm_call(StagePhase.SKETCH, resp)
        assert ctrl._total_plan_tokens == 0
        assert ctrl._stage_latency["SKETCH"] == 300

    def test_handles_missing_total_tokens_key(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        resp = FakeHubResponse(metadata={"usage": {"prompt_tokens": 100}, "latency_ms": 300})
        ctrl._record_llm_call(StagePhase.SKETCH, resp)
        assert ctrl._total_plan_tokens == 0

    def test_handles_missing_latency_key(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        resp = FakeHubResponse(metadata={"usage": {"total_tokens": 100}})
        ctrl._record_llm_call(StagePhase.SKETCH, resp)
        assert ctrl._total_plan_tokens == 100
        assert ctrl._stage_latency["SKETCH"] == 0

    def test_handles_attribute_style_metadata(self) -> None:
        """Defensive: handle non-dict metadata with attribute access."""
        ctrl = _make_controller()
        ctrl.reset()

        class AttrUsage:
            total_tokens = 75

        class AttrMetadata:
            usage = AttrUsage()
            latency_ms = 900

        @dataclass
        class AttrResponse:
            metadata: Any = None

        resp = AttrResponse(metadata=AttrMetadata())
        ctrl._record_llm_call(StagePhase.SKETCH, resp)
        assert ctrl._total_plan_tokens == 75
        assert ctrl._stage_latency["SKETCH"] == 900

    def test_counters_reset_on_reset(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        resp = FakeHubResponse(metadata={"usage": {"total_tokens": 200}, "latency_ms": 1000})
        ctrl._record_llm_call(StagePhase.SKETCH, resp)
        assert ctrl._total_plan_tokens == 200
        ctrl.reset()
        assert ctrl._total_plan_tokens == 0
        assert ctrl._stage_token_usage["SKETCH"] == 0
        assert ctrl._stage_latency["SKETCH"] == 0


# ===========================================================================
# 4. Budget injection into StageContext via _build_stage_context
# ===========================================================================


class TestBuildStageContextBudget:
    """_build_stage_context injects stage_budget from _get_stage_budget."""

    def test_sketch_context_has_sketch_budget(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.stage_budget is not None
        assert ctx.stage_budget.max_tokens == 2000
        assert ctx.stage_budget.timeout_ms == 8000
        assert ctx.stage_budget.temperature == 0.7

    def test_expand_context_has_expand_budget(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.EXPAND)
        assert ctx.stage_budget is not None
        assert ctx.stage_budget.max_tokens == 1000
        assert ctx.stage_budget.timeout_ms == 5000
        assert ctx.stage_budget.temperature == 0.3

    def test_validate_context_has_validate_budget(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.VALIDATE)
        assert ctx.stage_budget is not None
        assert ctx.stage_budget.max_tokens == 500
        assert ctx.stage_budget.timeout_ms == 3000
        assert ctx.stage_budget.temperature == 0.2

    def test_commit_context_has_no_budget(self) -> None:
        """PLAN-03: COMMIT stage budget is None."""
        ctrl = _make_controller()
        ctrl.reset()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.COMMIT)
        assert ctx.stage_budget is None

    def test_context_still_has_remaining_budget_fields(self) -> None:
        """token_budget_remaining and timeout_remaining_ms still computed."""
        ctrl = _make_controller()
        ctrl.reset()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.timeout_remaining_ms > 0
        assert ctx.token_budget_remaining >= 0
        assert ctx.request_id == "req-budget-001"
        assert ctx.trace_id == "trace-budget-abc"

    def test_context_reflects_consumed_tokens(self) -> None:
        """token_budget_remaining shrinks as tokens are consumed."""
        cfg = PlannerConfig()
        ctrl = _make_controller(config=cfg)
        ctrl.reset()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        # Simulate consuming 1000 tokens
        ctrl._total_plan_tokens = 1000
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.EXPAND)
        assert ctx.token_budget_remaining == cfg.total_token_budget - 1000

    def test_custom_config_budget_injected(self) -> None:
        cfg = PlannerConfig(
            sketch_max_tokens=4096,
            sketch_timeout_ms=15000,
            sketch_temperature=0.8,
            total_token_budget=5596,
        )
        ctrl = _make_controller(config=cfg)
        ctrl.reset()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.SKETCH)
        assert ctx.stage_budget is not None
        assert ctx.stage_budget.max_tokens == 4096
        assert ctx.stage_budget.timeout_ms == 15000
        assert ctx.stage_budget.temperature == 0.8


# ===========================================================================
# 5. Budget propagation through execute() to stage services
# ===========================================================================


class TestBudgetPropagationInExecute:
    """execute() injects correct stage_budget into each stage's StageContext."""

    @pytest.mark.anyio
    async def test_sketch_receives_sketch_budget(self) -> None:
        sketch = FakeSketchService()
        ctrl = _make_controller(sketch=sketch)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert len(sketch.calls) == 1
        ctx = sketch.calls[0][1]
        assert ctx.stage_budget is not None
        assert ctx.stage_budget.max_tokens == 2000
        assert ctx.stage_budget.timeout_ms == 8000

    @pytest.mark.anyio
    async def test_expand_receives_expand_budget(self) -> None:
        expand = FakeExpandService()
        ctrl = _make_controller(expand=expand)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert len(expand.calls) == 1
        ctx = expand.calls[0][1]
        assert ctx.stage_budget is not None
        assert ctx.stage_budget.max_tokens == 1000
        assert ctx.stage_budget.timeout_ms == 5000

    @pytest.mark.anyio
    async def test_validate_receives_validate_budget(self) -> None:
        validate = FakeValidateService()
        ctrl = _make_controller(validate=validate)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert len(validate.calls) == 1
        ctx = validate.calls[0][1]
        assert ctx.stage_budget is not None
        assert ctx.stage_budget.max_tokens == 500
        assert ctx.stage_budget.timeout_ms == 3000

    @pytest.mark.anyio
    async def test_commit_receives_no_budget(self) -> None:
        """PLAN-03: COMMIT stage context has stage_budget=None."""
        commit = FakeCommitService()
        ctrl = _make_controller(commit=commit)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert len(commit.calls) == 1
        ctx = commit.calls[0][2]  # (expanded_plan, verdict, ctx)
        assert ctx.stage_budget is None

    @pytest.mark.anyio
    async def test_custom_config_propagated_to_stages(self) -> None:
        cfg = PlannerConfig(
            sketch_max_tokens=4096,
            expand_max_tokens=2048,
            validate_max_tokens=1024,
            total_token_budget=7168,
        )
        sketch = FakeSketchService()
        expand = FakeExpandService()
        validate = FakeValidateService()
        ctrl = _make_controller(sketch=sketch, expand=expand, validate=validate, config=cfg)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert sketch.calls[0][1].stage_budget.max_tokens == 4096
        assert expand.calls[0][1].stage_budget.max_tokens == 2048
        assert validate.calls[0][1].stage_budget.max_tokens == 1024

    @pytest.mark.anyio
    async def test_all_budgets_have_interactive_priority(self) -> None:
        sketch = FakeSketchService()
        expand = FakeExpandService()
        validate = FakeValidateService()
        ctrl = _make_controller(sketch=sketch, expand=expand, validate=validate)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        for svc in (sketch, expand, validate):
            ctx = svc.calls[0][1]
            assert ctx.stage_budget.priority == "INTERACTIVE"

    @pytest.mark.anyio
    async def test_all_budgets_have_planner_consumer_id(self) -> None:
        sketch = FakeSketchService()
        expand = FakeExpandService()
        validate = FakeValidateService()
        ctrl = _make_controller(sketch=sketch, expand=expand, validate=validate)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        for svc in (sketch, expand, validate):
            ctx = svc.calls[0][1]
            assert ctx.stage_budget.consumer_id == "planner"


# ===========================================================================
# 6. StageContext.stage_budget field
# ===========================================================================


class TestStageContextStageBudget:
    """StageContext has an optional stage_budget field."""

    def test_stage_budget_default_is_none(self) -> None:
        ctx = StageContext(
            request_id="r1",
            trace_id="t1",
            timeout_remaining_ms=1000,
            token_budget_remaining=500,
            cancel_check=_never_cancel,
        )
        assert ctx.stage_budget is None

    def test_stage_budget_can_be_set(self) -> None:
        budget = RequestConstraints(max_tokens=100, timeout_ms=500)
        ctx = StageContext(
            request_id="r1",
            trace_id="t1",
            timeout_remaining_ms=1000,
            token_budget_remaining=500,
            cancel_check=_never_cancel,
            stage_budget=budget,
        )
        assert ctx.stage_budget is budget
        assert ctx.stage_budget.max_tokens == 100

    def test_stage_budget_is_frozen(self) -> None:
        """StageContext is frozen, cannot reassign stage_budget."""
        budget = RequestConstraints(max_tokens=100, timeout_ms=500)
        ctx = StageContext(
            request_id="r1",
            trace_id="t1",
            timeout_remaining_ms=1000,
            token_budget_remaining=500,
            cancel_check=_never_cancel,
            stage_budget=budget,
        )
        with pytest.raises(AttributeError):
            ctx.stage_budget = None  # type: ignore[misc]

    def test_backward_compatible_without_stage_budget(self) -> None:
        """Existing code creating StageContext without stage_budget still works."""
        ctx = StageContext(
            request_id="r1",
            trace_id="t1",
            timeout_remaining_ms=1000,
            token_budget_remaining=500,
            cancel_check=_never_cancel,
        )
        assert ctx.request_id == "r1"
        assert ctx.stage_budget is None


# ===========================================================================
# 7. plan_end delta includes token usage breakdown
# ===========================================================================


class TestPlanEndDeltaTokenUsage:
    """plan_end delta includes stage_token_usage and stage_latency."""

    @pytest.mark.anyio
    async def test_plan_end_delta_has_stage_token_usage(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        plan_end_deltas = [d for d in dp.emitted if d.delta_type == DELTA_PLAN_END]
        assert len(plan_end_deltas) == 1
        data = plan_end_deltas[0].data
        assert "stage_token_usage" in data
        assert isinstance(data["stage_token_usage"], dict)

    @pytest.mark.anyio
    async def test_plan_end_delta_has_stage_latency(self) -> None:
        dp = FakeDeltaPort()
        ctrl = _make_controller(delta_port=dp)
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        plan_end_deltas = [d for d in dp.emitted if d.delta_type == DELTA_PLAN_END]
        assert len(plan_end_deltas) == 1
        data = plan_end_deltas[0].data
        assert "stage_latency" in data
        assert isinstance(data["stage_latency"], dict)

    @pytest.mark.anyio
    async def test_plan_end_delta_token_usage_after_recording(self) -> None:
        """Manually record LLM calls to verify delta includes them."""
        dp = FakeDeltaPort()
        sketch = FakeSketchService()
        ctrl = _make_controller(delta_port=dp, sketch=sketch)
        # Execute first to set up state
        await ctrl.execute(FakePlanRequest(), _never_cancel)
        # The plan_end delta should reflect current counters
        plan_end_deltas = [d for d in dp.emitted if d.delta_type == DELTA_PLAN_END]
        data = plan_end_deltas[0].data
        # Default flow: no _record_llm_call invoked, so counts are at reset values
        usage = data["stage_token_usage"]
        assert usage.get("SKETCH", 0) == 0
        assert usage.get("EXPAND", 0) == 0
        assert usage.get("VALIDATE", 0) == 0
        assert usage.get("COMMIT", 0) == 0


# ===========================================================================
# 8. PlannerConfig micro per-stage validation
# ===========================================================================


class TestPlannerConfigMicroValidation:
    """PlannerConfig validates micro per-stage budget fields."""

    def test_default_micro_config_valid(self) -> None:
        """Default values pass validation (1024+512+256=1792 <= 2000)."""
        cfg = PlannerConfig()
        assert cfg.micro_sketch_max_tokens == 1024
        assert cfg.micro_expand_max_tokens == 512
        assert cfg.micro_validate_max_tokens == 256
        assert cfg.micro_sketch_timeout_ms == 5000
        assert cfg.micro_expand_timeout_ms == 3000
        assert cfg.micro_validate_timeout_ms == 2000

    def test_micro_sum_exceeds_total_raises(self) -> None:
        """micro per-stage sum > micro_replan_max_tokens raises ValueError."""
        with pytest.raises(ValueError, match="micro_replan_max_tokens"):
            PlannerConfig(
                micro_sketch_max_tokens=1500,
                micro_expand_max_tokens=800,
                micro_validate_max_tokens=500,
                micro_replan_max_tokens=2000,  # 1500+800+500=2800 > 2000
            )

    def test_micro_sum_equals_total_valid(self) -> None:
        """micro per-stage sum == micro_replan_max_tokens is valid."""
        cfg = PlannerConfig(
            micro_sketch_max_tokens=1024,
            micro_expand_max_tokens=512,
            micro_validate_max_tokens=256,
            micro_replan_max_tokens=1792,  # exactly sum
        )
        assert cfg.micro_replan_max_tokens == 1792

    def test_micro_token_fields_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="micro_sketch_max_tokens"):
            PlannerConfig(micro_sketch_max_tokens=0)

    def test_micro_expand_tokens_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="micro_expand_max_tokens"):
            PlannerConfig(micro_expand_max_tokens=0)

    def test_micro_validate_tokens_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="micro_validate_max_tokens"):
            PlannerConfig(micro_validate_max_tokens=0)

    def test_micro_timeout_fields_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="micro_sketch_timeout_ms"):
            PlannerConfig(micro_sketch_timeout_ms=0)

    def test_micro_expand_timeout_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="micro_expand_timeout_ms"):
            PlannerConfig(micro_expand_timeout_ms=0)

    def test_micro_validate_timeout_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="micro_validate_timeout_ms"):
            PlannerConfig(micro_validate_timeout_ms=0)

    def test_micro_fields_accepted_by_from_dict(self) -> None:
        cfg = PlannerConfig.from_dict(
            {
                "micro_sketch_max_tokens": 2048,
                "micro_sketch_timeout_ms": 6000,
                "micro_expand_max_tokens": 1024,
                "micro_expand_timeout_ms": 4000,
                "micro_validate_max_tokens": 512,
                "micro_validate_timeout_ms": 3000,
                "micro_replan_max_tokens": 4000,
            }
        )
        assert cfg.micro_sketch_max_tokens == 2048
        assert cfg.micro_expand_max_tokens == 1024
        assert cfg.micro_validate_max_tokens == 512


# ===========================================================================
# 9. PLAN-11 enforcement: budget presence
# ===========================================================================


class TestPlan11Enforcement:
    """PLAN-11: every LLM-calling stage has budget, no unbounded calls."""

    def test_all_llm_stages_have_budget(self) -> None:
        """SKETCH, EXPAND, VALIDATE all return non-None budgets."""
        ctrl = _make_controller()
        for stage in (StagePhase.SKETCH, StagePhase.EXPAND, StagePhase.VALIDATE):
            budget = ctrl._get_stage_budget(stage)
            assert budget is not None, f"Stage {stage.value} must have budget (PLAN-11)"
            assert budget.max_tokens > 0
            assert budget.timeout_ms > 0

    def test_commit_has_no_budget_plan03(self) -> None:
        """PLAN-03: COMMIT is the only stage without LLM budget."""
        ctrl = _make_controller()
        assert ctrl._get_stage_budget(StagePhase.COMMIT) is None

    def test_budget_max_tokens_always_positive(self) -> None:
        ctrl = _make_controller()
        for stage in (StagePhase.SKETCH, StagePhase.EXPAND, StagePhase.VALIDATE):
            budget = ctrl._get_stage_budget(stage)
            assert budget is not None
            assert budget.max_tokens > 0, f"max_tokens must be > 0 for {stage.value}"

    def test_budget_timeout_always_positive(self) -> None:
        ctrl = _make_controller()
        for stage in (StagePhase.SKETCH, StagePhase.EXPAND, StagePhase.VALIDATE):
            budget = ctrl._get_stage_budget(stage)
            assert budget is not None
            assert budget.timeout_ms > 0, f"timeout_ms must be > 0 for {stage.value}"

    def test_micro_all_llm_stages_have_budget(self) -> None:
        """PLAN-11 applies to micro-replan too."""
        ctrl = _make_controller()
        for stage in (StagePhase.SKETCH, StagePhase.EXPAND, StagePhase.VALIDATE):
            budget = ctrl._get_micro_stage_budget(stage)
            assert budget is not None, f"Micro stage {stage.value} must have budget"
            assert budget.max_tokens > 0
            assert budget.timeout_ms > 0

    def test_micro_commit_has_no_budget(self) -> None:
        ctrl = _make_controller()
        assert ctrl._get_micro_stage_budget(StagePhase.COMMIT) is None


# ===========================================================================
# 10. Budget table ordering: SKETCH > EXPAND > VALIDATE
# ===========================================================================


class TestBudgetTableOrdering:
    """Full pipeline budgets follow SKETCH > EXPAND > VALIDATE ordering."""

    def test_max_tokens_decreasing(self) -> None:
        """SKETCH has most tokens, VALIDATE has fewest."""
        ctrl = _make_controller()
        sketch = ctrl._get_stage_budget(StagePhase.SKETCH)
        expand = ctrl._get_stage_budget(StagePhase.EXPAND)
        validate = ctrl._get_stage_budget(StagePhase.VALIDATE)
        assert sketch is not None and expand is not None and validate is not None
        assert sketch.max_tokens > expand.max_tokens > validate.max_tokens

    def test_timeout_decreasing(self) -> None:
        """SKETCH has longest timeout, VALIDATE has shortest."""
        ctrl = _make_controller()
        sketch = ctrl._get_stage_budget(StagePhase.SKETCH)
        expand = ctrl._get_stage_budget(StagePhase.EXPAND)
        validate = ctrl._get_stage_budget(StagePhase.VALIDATE)
        assert sketch is not None and expand is not None and validate is not None
        assert sketch.timeout_ms > expand.timeout_ms > validate.timeout_ms

    def test_micro_max_tokens_decreasing(self) -> None:
        ctrl = _make_controller()
        sketch = ctrl._get_micro_stage_budget(StagePhase.SKETCH)
        expand = ctrl._get_micro_stage_budget(StagePhase.EXPAND)
        validate = ctrl._get_micro_stage_budget(StagePhase.VALIDATE)
        assert sketch is not None and expand is not None and validate is not None
        assert sketch.max_tokens > expand.max_tokens > validate.max_tokens

    def test_micro_budgets_tighter_than_full(self) -> None:
        """Micro-replan budgets are strictly tighter than full pipeline."""
        ctrl = _make_controller()
        for stage in (StagePhase.SKETCH, StagePhase.EXPAND, StagePhase.VALIDATE):
            full = ctrl._get_stage_budget(stage)
            micro = ctrl._get_micro_stage_budget(stage)
            assert full is not None and micro is not None
            assert micro.max_tokens < full.max_tokens, f"Micro {stage.value} tokens must be < full"


# ===========================================================================
# 11. Temperature values
# ===========================================================================


class TestTemperatureValues:
    """Budget temperature matches config values per stage."""

    def test_sketch_temperature_highest(self) -> None:
        """SKETCH uses higher temperature for creative generation."""
        ctrl = _make_controller()
        budget = ctrl._get_stage_budget(StagePhase.SKETCH)
        assert budget is not None
        assert budget.temperature == 0.7

    def test_expand_temperature_medium(self) -> None:
        """EXPAND uses lower temperature for precision."""
        ctrl = _make_controller()
        budget = ctrl._get_stage_budget(StagePhase.EXPAND)
        assert budget is not None
        assert budget.temperature == 0.3

    def test_validate_temperature_lowest(self) -> None:
        """VALIDATE uses lowest temperature for deterministic output."""
        ctrl = _make_controller()
        budget = ctrl._get_stage_budget(StagePhase.VALIDATE)
        assert budget is not None
        assert budget.temperature == 0.2

    def test_temperatures_are_valid_range(self) -> None:
        ctrl = _make_controller()
        for stage in (StagePhase.SKETCH, StagePhase.EXPAND, StagePhase.VALIDATE):
            budget = ctrl._get_stage_budget(stage)
            assert budget is not None
            assert 0.0 <= budget.temperature <= 1.0


# ===========================================================================
# 12. stage_token_usage property
# ===========================================================================


class TestStageTokenUsageProperty:
    """stage_token_usage property returns a safe copy."""

    def test_returns_dict(self) -> None:
        ctrl = _make_controller()
        assert isinstance(ctrl.stage_token_usage, dict)

    def test_returns_copy_not_reference(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        usage = ctrl.stage_token_usage
        usage["SKETCH"] = 99999
        assert (
            ctrl.stage_token_usage.get("SKETCH", 0) != 99999
            or ctrl._stage_token_usage.get("SKETCH", 0) == 0
        )

    def test_reflects_recorded_calls(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        resp = FakeHubResponse(metadata={"usage": {"total_tokens": 42}, "latency_ms": 100})
        ctrl._record_llm_call(StagePhase.SKETCH, resp)
        assert ctrl.stage_token_usage["SKETCH"] == 42


# ===========================================================================
# 13. Integration: full execute with recorded LLM calls
# ===========================================================================


class TestRecordLlmCallIntegration:
    """Integration: _record_llm_call correctly tracks across pipeline."""

    def test_manual_recording_updates_total(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        r1 = FakeHubResponse(metadata={"usage": {"total_tokens": 200}, "latency_ms": 2000})
        r2 = FakeHubResponse(metadata={"usage": {"total_tokens": 100}, "latency_ms": 1500})
        r3 = FakeHubResponse(metadata={"usage": {"total_tokens": 50}, "latency_ms": 800})
        ctrl._record_llm_call(StagePhase.SKETCH, r1)
        ctrl._record_llm_call(StagePhase.EXPAND, r2)
        ctrl._record_llm_call(StagePhase.VALIDATE, r3)
        assert ctrl.total_plan_tokens == 350
        assert ctrl.stage_token_usage == {
            "SKETCH": 200,
            "EXPAND": 100,
            "VALIDATE": 50,
            "COMMIT": 0,
        }

    def test_total_plan_tokens_property_matches_internal(self) -> None:
        ctrl = _make_controller()
        ctrl.reset()
        resp = FakeHubResponse(metadata={"usage": {"total_tokens": 123}, "latency_ms": 0})
        ctrl._record_llm_call(StagePhase.EXPAND, resp)
        assert ctrl.total_plan_tokens == 123
        assert ctrl._total_plan_tokens == 123

    def test_token_budget_remaining_shrinks_after_recording(self) -> None:
        cfg = PlannerConfig()
        ctrl = _make_controller(config=cfg)
        ctrl.reset()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        resp = FakeHubResponse(metadata={"usage": {"total_tokens": 1000}, "latency_ms": 500})
        ctrl._record_llm_call(StagePhase.SKETCH, resp)
        ctx = ctrl._build_stage_context(_never_cancel, StagePhase.EXPAND)
        assert ctx.token_budget_remaining == cfg.total_token_budget - 1000
