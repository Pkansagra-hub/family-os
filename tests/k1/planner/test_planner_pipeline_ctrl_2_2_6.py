"""Tests for PipelineController timeout enforcement (Issue 2.2.6).

Covers:
  - _check_timeout emits PIPELINE_TIMEOUT plan.failed.v1 payload
  - PlannerError raised on timeout with stage attribution
  - execute() emits exactly one timeout failure event (no duplicates)
  - timeout checks invoked at each cancel checkpoint in full pipeline path
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import pytest

from k1.planner.config import PlannerConfig
from k1.planner.events import TOPIC_PLAN_FAILED, PlanFailedPayload
from k1.planner.pipeline_controller import PipelineController
from k1.planner.plan_fsm import PlanState
from k1.planner.types import (
    VERDICT_APPROVED,
    VERDICT_REVISE,
    DeltaPayload,
    PlannerError,
    StageContext,
    ValidationIssue,
    ValidationVerdict,
)


@dataclass
class FakePlanRequest:
    request_id: str = "req-timeout-001"
    trace_id: str = "trace-timeout-001"
    intent: str = "timeout test"


class FakeSketchService:
    def __init__(self, *, delay_s: float = 0.0) -> None:
        self._delay_s = delay_s
        self.call_count = 0

    async def execute(self, request: Any, ctx: StageContext) -> Any:
        self.call_count += 1
        if self._delay_s > 0:
            await asyncio.sleep(self._delay_s)
        return {"rough_steps": ["s1"]}


class FakeExpandService:
    def __init__(self) -> None:
        self.call_count = 0

    async def execute(self, sketch_result: Any, ctx: StageContext) -> Any:
        self.call_count += 1
        return {"steps": ["e1"]}


class FakeValidateService:
    def __init__(self, verdicts: Optional[List[ValidationVerdict]] = None) -> None:
        self._verdicts = verdicts or [_approved()]
        self.call_count = 0

    async def execute(self, expanded_plan: Any, ctx: StageContext) -> ValidationVerdict:
        self.call_count += 1
        idx = min(self.call_count - 1, len(self._verdicts) - 1)
        return self._verdicts[idx]


class FakeCommitService:
    def __init__(self) -> None:
        self.call_count = 0

    async def execute(self, expanded_plan: Any, verdict: Any, ctx: StageContext) -> Any:
        self.call_count += 1
        return {"plan_id": "p1", "request_id": "req-timeout-001"}


class FakeDeltaPort:
    def __init__(self) -> None:
        self.emitted: List[DeltaPayload] = []

    def emit(self, delta: DeltaPayload) -> None:
        self.emitted.append(delta)


class FakeEventPort:
    def __init__(self, *, fail: bool = False) -> None:
        self.emitted: List[Tuple[str, Any]] = []
        self._fail = fail

    def emit(self, topic: str, payload: Any) -> None:
        if self._fail:
            raise RuntimeError("event down")
        self.emitted.append((topic, payload))

    def subscribe(self, topic: str, handler: Any) -> Any:
        return f"sub-{topic}"

    def unsubscribe(self, handle: Any) -> bool:
        return True


def _approved() -> ValidationVerdict:
    return ValidationVerdict(
        status=VERDICT_APPROVED,
        confidence=0.9,
        rationale="ok",
    )


def _revise() -> ValidationVerdict:
    return ValidationVerdict(
        status=VERDICT_REVISE,
        confidence=0.8,
        rationale="needs revise",
        issues=[
            ValidationIssue(
                check_name="check",
                severity="warning",
                detail="revise",
            )
        ],
    )


def _make_controller(
    *,
    sketch: Any = None,
    expand: Any = None,
    validate: Any = None,
    commit: Any = None,
    event_port: Any = None,
    config: Any = None,
) -> PipelineController:
    return PipelineController(
        sketch=sketch if sketch is not None else FakeSketchService(),
        expand=expand if expand is not None else FakeExpandService(),
        validate=validate if validate is not None else FakeValidateService(),
        commit=commit if commit is not None else FakeCommitService(),
        delta_port=FakeDeltaPort(),
        event_port=event_port if event_port is not None else FakeEventPort(),
        config=config if config is not None else PlannerConfig(),
    )


def _never_cancel() -> bool:
    return False


class TestCheckTimeoutEnhanced:
    def test_timeout_emits_pipeline_timeout_payload(self) -> None:
        ep = FakeEventPort()
        cfg = PlannerConfig(pipeline_timeout_ms=1)
        ctrl = _make_controller(config=cfg, event_port=ep)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic() - 1.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")

        with pytest.raises(PlannerError):
            ctrl._check_timeout("SKETCH")

        failed = [p for t, p in ep.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed) == 1
        payload = failed[0]
        assert isinstance(payload, PlanFailedPayload)
        assert payload.error_code == "PIPELINE_TIMEOUT"
        assert payload.stage == "SKETCH"
        assert payload.request_id == "req-timeout-001"
        assert payload.trace_id == "trace-timeout-001"
        assert "Pipeline exceeded 1ms" in payload.error_message

    def test_timeout_marks_fsm_failed(self) -> None:
        cfg = PlannerConfig(pipeline_timeout_ms=1)
        ctrl = _make_controller(config=cfg)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic() - 1.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")

        with pytest.raises(PlannerError):
            ctrl._check_timeout("SKETCH")

        assert ctrl.current_state == PlanState.FAILED

    def test_timeout_event_port_failure_does_not_block_raise(self) -> None:
        ep = FakeEventPort(fail=True)
        cfg = PlannerConfig(pipeline_timeout_ms=1)
        ctrl = _make_controller(config=cfg, event_port=ep)
        ctrl._current_request = FakePlanRequest()
        ctrl._plan_start_time = time.monotonic() - 1.0
        ctrl._fsm.transition(PlanState.SKETCHING, trigger="test")

        with pytest.raises(PlannerError, match="Pipeline exceeded"):
            ctrl._check_timeout("SKETCH")


class TestExecuteTimeoutIntegration:
    @pytest.mark.asyncio
    async def test_execute_timeout_emits_single_failed_event(self) -> None:
        ep = FakeEventPort()
        cfg = PlannerConfig(pipeline_timeout_ms=1)
        sketch = FakeSketchService(delay_s=0.01)
        ctrl = _make_controller(config=cfg, event_port=ep, sketch=sketch)

        with pytest.raises(PlannerError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)

        failed = [p for t, p in ep.emitted if t == TOPIC_PLAN_FAILED]
        assert len(failed) == 1
        assert failed[0].error_code == "PIPELINE_TIMEOUT"

    @pytest.mark.asyncio
    async def test_execute_timeout_payload_duration_positive(self) -> None:
        ep = FakeEventPort()
        cfg = PlannerConfig(pipeline_timeout_ms=1)
        sketch = FakeSketchService(delay_s=0.01)
        ctrl = _make_controller(config=cfg, event_port=ep, sketch=sketch)

        with pytest.raises(PlannerError):
            await ctrl.execute(FakePlanRequest(), _never_cancel)

        payload = [p for t, p in ep.emitted if t == TOPIC_PLAN_FAILED][0]
        assert payload.duration_ms > 0

    @pytest.mark.asyncio
    async def test_execute_timeout_raises_with_stage(self) -> None:
        cfg = PlannerConfig(pipeline_timeout_ms=1)
        sketch = FakeSketchService(delay_s=0.01)
        ctrl = _make_controller(config=cfg, sketch=sketch)

        with pytest.raises(PlannerError) as exc_info:
            await ctrl.execute(FakePlanRequest(), _never_cancel)

        assert exc_info.value.stage == "SKETCH"


class TestTimeoutCheckpointCoverage:
    @pytest.mark.asyncio
    async def test_timeout_called_three_times_on_happy_path(self) -> None:
        calls: List[str] = []

        class SpyController(PipelineController):
            def _check_timeout(self, stage: str) -> None:
                calls.append(stage)
                super()._check_timeout(stage)

        ctrl = SpyController(
            sketch=FakeSketchService(),
            expand=FakeExpandService(),
            validate=FakeValidateService(),
            commit=FakeCommitService(),
            delta_port=FakeDeltaPort(),
            event_port=FakeEventPort(),
            config=PlannerConfig(),
        )

        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert calls == ["SKETCH", "EXPAND", "VALIDATE"]

    @pytest.mark.asyncio
    async def test_timeout_called_four_times_with_revise_loop(self) -> None:
        validate = FakeValidateService(verdicts=[_revise(), _approved()])
        calls: List[str] = []

        class SpyController(PipelineController):
            def _check_timeout(self, stage: str) -> None:
                calls.append(stage)
                super()._check_timeout(stage)

        ctrl = SpyController(
            sketch=FakeSketchService(),
            expand=FakeExpandService(),
            validate=validate,
            commit=FakeCommitService(),
            delta_port=FakeDeltaPort(),
            event_port=FakeEventPort(),
            config=PlannerConfig(),
        )

        await ctrl.execute(FakePlanRequest(), _never_cancel)
        assert calls == ["SKETCH", "EXPAND", "EXPAND", "VALIDATE"]
