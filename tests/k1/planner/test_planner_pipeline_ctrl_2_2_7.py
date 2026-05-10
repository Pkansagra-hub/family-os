"""Tests for PipelineController StageContext construction & propagation (Issue 2.2.7)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, List, Optional

import pytest

from k1.planner.config import PlannerConfig
from k1.planner.pipeline_controller import PipelineController
from k1.planner.tracing import create_stage_context
from k1.planner.types import VERDICT_APPROVED, StageContext, StagePhase, ValidationVerdict


@dataclass
class FakePlanRequest:
    request_id: str = "req-ctx-001"
    trace_id: str = "trace-ctx-001"
    intent: str = "stage context propagation"


class FakeSketchService:
    def __init__(self) -> None:
        self.calls: List[StageContext] = []

    async def execute(self, request: Any, ctx: StageContext) -> Any:
        self.calls.append(ctx)
        return {"rough_steps": [{"intent": "s1"}]}


class FakeExpandService:
    def __init__(self) -> None:
        self.calls: List[StageContext] = []

    async def execute(self, sketch_result: Any, request: Any, ctx: StageContext) -> Any:
        self.calls.append(ctx)
        return {"steps": [{"id": "st1"}]}


class FakeValidateService:
    def __init__(self, verdicts: Optional[List[ValidationVerdict]] = None) -> None:
        self.calls: List[StageContext] = []
        self._verdicts = verdicts or [
            ValidationVerdict(
                status=VERDICT_APPROVED,
                confidence=0.9,
                rationale="ok",
            )
        ]
        self._idx = 0

    async def execute(
        self, expanded_plan: Any, request: Any, ctx: StageContext
    ) -> ValidationVerdict:
        self.calls.append(ctx)
        idx = min(self._idx, len(self._verdicts) - 1)
        self._idx += 1
        return self._verdicts[idx]


class FakeCommitService:
    def __init__(self) -> None:
        self.calls: List[StageContext] = []

    async def execute(
        self, expanded_plan: Any, request: Any, verdict: Any, ctx: StageContext
    ) -> Any:
        self.calls.append(ctx)
        return {
            "plan_id": "plan-ctx-001",
            "request_id": "req-ctx-001",
            "trace_id": ctx.trace_id,
        }


class FakeDeltaPort:
    def __init__(self) -> None:
        self.emitted: List[Any] = []

    def emit(self, delta: Any) -> None:
        self.emitted.append(delta)


class FakeEventPort:
    def __init__(self) -> None:
        self.emitted: List[Any] = []

    def emit(self, topic: str, payload: Any) -> None:
        self.emitted.append((topic, payload))

    def subscribe(self, topic: str, handler: Any) -> Any:
        return f"sub-{topic}"

    def unsubscribe(self, handle: Any) -> Any:
        return None


def _never_cancel() -> bool:
    return False


def _make_controller(
    *,
    sketch: Any = None,
    expand: Any = None,
    validate: Any = None,
    commit: Any = None,
    config: Any = None,
) -> PipelineController:
    return PipelineController(
        sketch=sketch if sketch is not None else FakeSketchService(),
        expand=expand if expand is not None else FakeExpandService(),
        validate=validate if validate is not None else FakeValidateService(),
        commit=commit if commit is not None else FakeCommitService(),
        delta_port=FakeDeltaPort(),
        event_port=FakeEventPort(),
        config=config if config is not None else PlannerConfig(),
    )


class TestCreateStageContextMethod:
    def test_create_stage_context_uses_request_and_trace(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest(request_id="req-a", trace_id="trace-a")
        ctrl._plan_start_time = time.monotonic()
        ctrl._active_cancel_check = _never_cancel

        ctx = ctrl._create_stage_context(StagePhase.SKETCH)

        assert isinstance(ctx, StageContext)
        assert ctx.request_id == "req-a"
        assert ctx.trace_id == "trace-a"

    def test_create_stage_context_shrinks_timeout_and_tokens(self) -> None:
        cfg = PlannerConfig(pipeline_timeout_ms=45_000, total_token_budget=4_000)
        ctrl = _make_controller(config=cfg)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic() - 0.1  # ~100ms elapsed
        ctrl._total_plan_tokens = 700
        ctrl._active_cancel_check = _never_cancel

        ctx = ctrl._create_stage_context(StagePhase.EXPAND)

        assert 1 <= ctx.timeout_remaining_ms < 45_000
        assert ctx.token_budget_remaining == 3_300

    def test_create_stage_context_cancel_check_closure(self) -> None:
        ctrl = _make_controller()
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()

        flag = {"cancelled": False}

        def closure() -> bool:
            return flag["cancelled"]

        ctrl._active_cancel_check = closure
        ctx = ctrl._create_stage_context(StagePhase.VALIDATE)

        assert ctx.cancel_check() is False
        flag["cancelled"] = True
        assert ctx.cancel_check() is True

    def test_create_stage_context_sets_stage_budget(self) -> None:
        cfg = PlannerConfig(sketch_max_tokens=2222, total_token_budget=4500)
        ctrl = _make_controller(config=cfg)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic()
        ctrl._active_cancel_check = _never_cancel

        ctx = ctrl._create_stage_context(StagePhase.SKETCH)

        assert ctx.stage_budget is not None
        assert ctx.stage_budget.max_tokens == 2222


class TestExecutePropagation:
    @pytest.mark.asyncio
    async def test_execute_constructs_context_at_each_stage_boundary(self) -> None:
        stages: List[StagePhase] = []

        class SpyController(PipelineController):
            def _create_stage_context(self, stage: StagePhase) -> StageContext:
                stages.append(stage)
                return super()._create_stage_context(stage)

        sketch = FakeSketchService()
        expand = FakeExpandService()
        validate = FakeValidateService()
        commit = FakeCommitService()

        ctrl = SpyController(
            sketch=sketch,
            expand=expand,
            validate=validate,
            commit=commit,
            delta_port=FakeDeltaPort(),
            event_port=FakeEventPort(),
            config=PlannerConfig(),
        )

        req = FakePlanRequest(trace_id="trace-prop")
        await ctrl.execute(req, _never_cancel)

        assert stages == [
            StagePhase.SKETCH,
            StagePhase.EXPAND,
            StagePhase.VALIDATE,
            StagePhase.COMMIT,
        ]
        assert sketch.calls[0].trace_id == "trace-prop"
        assert expand.calls[0].trace_id == "trace-prop"
        assert validate.calls[0].trace_id == "trace-prop"
        assert commit.calls[0].trace_id == "trace-prop"


class TestTracingHelper:
    def test_create_stage_context_helper_clamps_values(self) -> None:
        cfg = PlannerConfig(pipeline_timeout_ms=5, total_token_budget=3500)
        ctx = create_stage_context(
            request=None,
            config=cfg,
            elapsed_ms=999,
            tokens_used=5000,
            cancel_check=_never_cancel,
        )

        assert ctx.request_id == "unknown"
        assert ctx.trace_id == "unknown"
        assert ctx.timeout_remaining_ms == 1
        assert ctx.token_budget_remaining == 0

    def test_create_stage_context_helper_maps_request_fields(self) -> None:
        req = FakePlanRequest(request_id="req-h", trace_id="trace-h")
        cfg = PlannerConfig()

        ctx = create_stage_context(
            request=req,
            config=cfg,
            elapsed_ms=0,
            tokens_used=0,
            cancel_check=_never_cancel,
        )

        assert ctx.request_id == "req-h"
        assert ctx.trace_id == "trace-h"
