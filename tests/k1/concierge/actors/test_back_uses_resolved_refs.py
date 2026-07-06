"""M2-E2: Back receives resolved temporal refs and does not route to date_calc."""

from __future__ import annotations

from typing import Any

import pytest

import k1.concierge.actors.back as back_mod
from k1.concierge.bus.builders import build_task_dispatch
from k1.concierge.bus.setup import create_poc_bus
from k1.concierge.llm.test_model_hub_bridge import TestModelHubBridge
from k1.concierge.llm.types import ConciergeModelResponse, FinishReason, ToolCallResult
from k1.concierge.tools.dispatcher import create_back_dispatcher
from k1.concierge.tools.implementations import ToolContext
from k1.sessionstate.factory import SessionStateFactory


class _RecordingDispatch:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def dispatch_direct(self, request: Any) -> Any:
        self.requests.append(request)
        raise AssertionError("date_calc should not be invoked when dispatch refs answer the date")


def _tomorrow_ref() -> dict[str, object]:
    return {
        "raw_text": "tomorrow",
        "normalized_label": "tomorrow",
        "resolution_kind": "window",
        "window": {
            "label": "tomorrow",
            "start_local": "2025-01-16T00:00:00+00:00",
            "end_local": "2025-01-17T00:00:00+00:00",
            "start_utc": "2025-01-16T00:00:00+00:00",
            "end_utc": "2025-01-17T00:00:00+00:00",
            "timezone": "UTC",
            "granularity": "day",
        },
        "instant_local": None,
        "recurrence_rule": None,
        "confidence": 1.0,
        "needs_clarification": False,
        "clarification_reason": None,
    }


def _model() -> TestModelHubBridge:
    model = TestModelHubBridge()
    model.set_response_sequence(
        "back",
        "",
        [
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id="call-recall-m2",
                        name="recall_memory",
                        arguments={
                            "query": "calendar context for subject_ref tomorrow",
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
                        id="call-submit-m2",
                        name="submit_result",
                        arguments={
                            "result_type": "complete",
                            "final_answer": "Used resolved tomorrow window from dispatch.",
                            "results": [
                                {
                                    "date_window": {
                                        "start_local": "2025-01-16T00:00:00+00:00",
                                        "end_local": "2025-01-17T00:00:00+00:00",
                                    }
                                }
                            ],
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
async def test_back_prompt_gets_resolved_refs_and_no_date_calc_invocation() -> None:
    bus = create_poc_bus(capture=True)
    session_state = SessionStateFactory.create_for_testing()
    session_state.start()
    dispatch = _RecordingDispatch()
    dispatcher = create_back_dispatcher(
        tier="simple",
        ctx=ToolContext(session_manager=session_state, actor="back", dispatch=dispatch),
        bus=bus,
    )
    model = _model()
    envelope = build_task_dispatch(
        {
            "task_id": "task-m2-back",
            "tier": "LOW",
            "safety_band": "GREEN",
            "intents": [
                {
                    "action": "check calendar",
                    "domain": "calendar",
                    "params": {"subject_ref": "subject_ref", "date": "tomorrow"},
                }
            ],
            "resolved_temporal_refs": {"tomorrow": _tomorrow_ref()},
        }
    )

    try:
        result = await back_mod.back_handler(
            envelope=envelope,
            model=model,
            ss=session_state,
            bus=bus,
            tool_dispatcher=dispatcher,
        )
    finally:
        session_state.stop()

    request = model.inner.calls_for("back", "")[0]
    system_prompt = request.system_prompt

    assert result.status == "complete"
    assert dispatch.requests == []
    # Epic 17: resolved refs are woven into prose, not a raw typed block.
    assert "already resolved these time expressions" in system_prompt
    assert "tomorrow (window)" in system_prompt
