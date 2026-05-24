from __future__ import annotations

import logging
from typing import Any

import pytest

import k1.concierge.actors.back as back_mod
from k1.concierge.bus.builders import build_task_dispatch, build_task_resume
from k1.concierge.bus.setup import create_poc_bus
from k1.concierge.llm.test_model_hub_bridge import TestModelHubBridge
from k1.concierge.llm.types import ConciergeModelResponse, FinishReason, ToolCallResult
from k1.concierge.tools.dispatcher import create_back_dispatcher
from k1.concierge.tools.implementations import ToolContext
from k1.hil.types import NeedsHumanResponse
from k1.sessionstate.factory import SessionStateFactory


def _dispatcher(bus: Any, session_state: Any):
    ctx = ToolContext(session_manager=session_state, actor="back")
    return create_back_dispatcher(tier="simple", ctx=ctx, bus=bus)


def _model_for_scenario(scenario: str) -> TestModelHubBridge:
    model = TestModelHubBridge()
    model.set_response_sequence(
        "back",
        "",
        [
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id=f"call-recall-{scenario}",
                        name="recall_memory",
                        arguments={
                            "query": f"profile wiring {scenario}",
                            "memory_types": ["semantic"],
                            "max_results": 1,
                        },
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                model_id="test-model",
            ),
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id=f"call-invoke-{scenario}",
                        name="invoke_capability",
                        arguments={
                            "capability_name": "tool.execute.calendar.create_event",
                            "params": {"title": "profile wiring probe"},
                        },
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                model_id="test-model",
            ),
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id=f"call-submit-{scenario}",
                        name="submit_result",
                        arguments={
                            "result_type": "complete",
                            "final_answer": "done",
                            "results": [],
                            "artifacts_created": [],
                        },
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                model_id="test-model",
            ),
        ],
    )
    return model


class _RecordingHILPort:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def needs_human(self, req: Any) -> NeedsHumanResponse:
        self.requests.append(req)
        return NeedsHumanResponse(
            hil_request_id="hil-back-handler-1",
            decision="answered",
            resolution={"additional_info": "Use the 6 PM slot."},
            raw_user_text="Use the 6 PM slot.",
            timed_out=False,
        )


def _model_for_unified_hil() -> TestModelHubBridge:
    model = TestModelHubBridge()
    model.set_response_sequence(
        "back",
        "",
        [
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id="call-hil",
                        name="submit_result",
                        arguments={
                            "result_type": "needs_human",
                            "hil_type": "clarification",
                            "question": "Which time should I use?",
                        },
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                model_id="test-model",
            ),
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id="call-submit-after-hil",
                        name="invoke_capability",
                        arguments={
                            "capability_name": "tool.execute.reminders.create_reminder",
                            "params": {"title": "profile wiring probe"},
                        },
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                model_id="test-model",
            ),
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id="call-submit-after-hil-complete",
                        name="submit_result",
                        arguments={
                            "result_type": "complete",
                            "final_answer": "Scheduled it for 6 PM.",
                            "results": [],
                            "artifacts_created": [],
                        },
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                model_id="test-model",
            ),
        ],
    )
    return model


@pytest.mark.asyncio
async def test_back_handler_injects_profile_block_and_persists_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="k1.concierge.actors.back")
    bus = create_poc_bus(capture=True)
    session_state = SessionStateFactory.create_for_testing()
    session_state.start()
    model = _model_for_scenario("task_execution")
    envelope = build_task_dispatch(
        {
            "task_id": "task-profile-1",
            "tier": "LOW",
            "safety_band": "AMBER",
            "intents": [
                {
                    "action": "create a calendar event for Riley soccer practice",
                    "domain": "calendar",
                    "params": {"start": "2026-06-01T17:00:00"},
                }
            ],
        }
    )

    try:
        result = await back_mod.back_handler(
            envelope=envelope,
            model=model,
            ss=session_state,
            bus=bus,
            tool_dispatcher=_dispatcher(bus, session_state),
        )
    finally:
        session_state.stop()

    assert result.status == "complete"
    model.inner.assert_called("back", "")
    request = model.inner.calls_for("back", "")[0]
    assert request is not None
    system_prompt = request.system_prompt
    assert "== EXECUTION PROFILES ==" in system_prompt
    assert "calendar.v1" in system_prompt
    assert system_prompt.index("== EXECUTION PROFILES ==") < system_prompt.index("STEP 1 -- ORIENT")
    task_message = request.messages[-1].content
    assert '"execution_profiles"' in task_message
    assert "calendar.v1" in task_message
    assert any(
        "execution profile selection" in record.message
        and "task-profile-1" in record.message
        and "calendar.v1" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_back_handler_resolves_needs_human_through_unified_hil() -> None:
    bus = create_poc_bus(capture=True)
    session_state = SessionStateFactory.create_for_testing()
    session_state.start()
    model = _model_for_unified_hil()
    hil_port = _RecordingHILPort()
    envelope = build_task_dispatch(
        {
            "task_id": "task-unified-hil-1",
            "tier": "LOW",
            "safety_band": "GREEN",
            "intents": [
                {
                    "action": "schedule the reminder",
                    "domain": "reminders",
                    "params": {},
                }
            ],
        }
    )

    try:
        result = await back_mod.back_handler(
            envelope=envelope,
            model=model,
            ss=session_state,
            bus=bus,
            tool_dispatcher=_dispatcher(bus, session_state),
            hil_port=hil_port,
        )
    finally:
        session_state.stop()

    topics = [event.topic for event in bus.published]
    assert result.status == "complete"
    assert len(hil_port.requests) == 1
    assert hil_port.requests[0].task_id == "task-unified-hil-1"
    assert hil_port.requests[0].question == "Which time should I use?"
    assert "k1.orchestration.task.suspended.v1" not in topics
    assert "k1.orchestration.task.complete.v1" in topics


@pytest.mark.asyncio
async def test_back_resume_handler_reuses_profile_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="k1.concierge.actors.back")
    bus = create_poc_bus(capture=True)
    session_state = SessionStateFactory.create_for_testing()
    session_state.start()
    model = _model_for_scenario("task_resume")
    envelope = build_task_resume(
        {
            "task_id": "task-profile-2",
            "resolution": {"additional_info": "Use the reminder path."},
            "resume_context": {
                "hil_type": "clarification",
                "original_task": {
                    "task_id": "task-profile-2",
                    "tier": "LOW",
                    "safety_band": "AMBER",
                    "execution_profiles": [
                        {
                            "profile_id": "reminders.v1",
                            "score": 123,
                            "evidence": ["preselected"],
                        }
                    ],
                    "intents": [
                        {
                            "action": "create a calendar event",
                            "domain": "calendar",
                        }
                    ],
                },
                "react_history": [{"role": "assistant", "content": "Need clarification."}],
                "remaining_budget": 4,
            },
        }
    )

    try:
        result = await back_mod.back_resume_handler(
            envelope=envelope,
            model=model,
            ss=session_state,
            bus=bus,
            tool_dispatcher=_dispatcher(bus, session_state),
        )
    finally:
        session_state.stop()

    assert result.status == "complete"
    model.inner.assert_called("back", "")
    request = model.inner.calls_for("back", "")[0]
    assert request is not None
    system_prompt = request.system_prompt
    assert "reminders.v1" in system_prompt
    assert "score=123; preselected" in system_prompt
    assert "calendar.v1" not in system_prompt
    assert any(
        "execution profile selection" in record.message
        and "task-profile-2" in record.message
        and "task_metadata" in record.message
        for record in caplog.records
    )
