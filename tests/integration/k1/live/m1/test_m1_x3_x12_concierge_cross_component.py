"""M1 cross-component Concierge live wiring probes."""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from k1.concierge.bus.builders import build_user_input
from k1.concierge.bus.topics import (
    TOPIC_DEAD_LETTER,
    TOPIC_FINAL_RESPONSE,
    TOPIC_HIL_RESPONSE,
    TOPIC_INTENT_ARBITRATED,
    TOPIC_RESPONSE_STREAM,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_RESUME,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TURN_COMPLETED,
    TOPIC_TURN_STARTED,
)
from k1.kernel.service import KernelService
from k1.sessionstate.public_types import PrivacyBand
from tests.integration.k1.live.m1.test_m1_l3_low_tier_message_flow import (
    TopicRecorder,
    _active_task_snapshot,
    _cleanup_service,
    _decode_payload,
    _install_test_mcp_transport,
    _recipe_a,
)
from tests.integration.k1.live.m1.test_m1_l6_l9_concierge_lifecycle import (
    _recipe_b,
    _wait_for_count,
    _wait_for_predicate,
)
from tests.k1.integration.concierge.scripted_provider import (
    install_scripted_plugin,
    make_text_response,
    make_tool_call_response,
)

pytestmark = pytest.mark.integration


def _request_text(req: Any) -> str:
    parts: list[str] = []
    if getattr(req, "system_prompt", None):
        parts.append(str(req.system_prompt))
    for message in getattr(req, "messages", []) or []:
        parts.append(str(getattr(message, "content", "")))
    return "\n".join(parts)


def _is_front_request(req: Any) -> bool:
    return getattr(req, "consumer_id", "") == "concierge.front"


def _is_back_request(req: Any) -> bool:
    return getattr(req, "consumer_id", "") == "concierge.back"


def _publish_user_input(session: Any, *, session_id: str, trace_id: str, text: str) -> None:
    session.bus.publish(
        replace(
            build_user_input(
                payload={
                    "text": text,
                    "session_id": session_id,
                    "device_id": f"device-{session_id}",
                }
            ),
            cognitive_trace_id=trace_id,
            session_id=session_id,
            request_id=f"request-{session_id}",
        )
    )


def _first_index(recorder: TopicRecorder, topic: str) -> int:
    return next(i for i, envelope in enumerate(recorder.envelopes) if envelope.topic == topic)


@pytest.mark.asyncio
async def test_m1_x3_low_tier_dispatch_uses_back_direct_session_fabric(
    tmp_path: Path,
) -> None:
    """M1-X3: LOW dispatch goes to Back and exactly one session Fabric call."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))
    original_dispatch_envelope: Any | None = None
    dispatch_port: Any | None = None

    try:
        await svc.startup()
        scripted = await install_scripted_plugin(svc)
        orchestrator_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        async def fail_if_orchestrator_dispatch(*args: Any, **kwargs: Any) -> Any:
            orchestrator_calls.append((args, kwargs))
            raise AssertionError("LOW dispatch must not call orchestrator.dispatch_envelope")

        capability = "tool.read.find_prompts"
        scripted.queue(
            make_tool_call_response(
                (
                    "dispatch_task",
                    {
                        "intents": [
                            {
                                "action": capability,
                                "params": {"intent": "direct family prompt", "top_k": 1},
                                "urgency": "normal",
                            }
                        ],
                        "safety_band": "GREEN",
                    },
                )
            ),
            predicate=lambda req: _is_front_request(req) and "direct LOW" in _request_text(req),
            label="front-dispatch-low-direct",
        )
        scripted.queue(
            make_tool_call_response(
                (
                    "invoke_capability",
                    {
                        "capability_name": capability,
                        "params": {"intent": "direct family prompt", "top_k": 1},
                    },
                )
            ),
            predicate=_is_back_request,
            label="back-low-invoke",
        )
        scripted.queue(
            make_tool_call_response(
                (
                    "submit_result",
                    {
                        "result_type": "complete",
                        "final_answer": "Direct LOW result.",
                        "results": [{"prompt": "direct"}],
                        "artifacts_created": [],
                    },
                )
            ),
            predicate=_is_back_request,
            label="back-low-submit",
        )

        session_id = "m1x3"
        trace_id = "trace-m1-x3"
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        dispatch_port = session.concierge._dispatch_port
        original_dispatch_envelope = dispatch_port.dispatch_envelope
        dispatch_port.dispatch_envelope = fail_if_orchestrator_dispatch

        transport = _install_test_mcp_transport(session.fabric)
        from k1.fabric.providers.mcp_provider import MCPResponse

        transport.add_response(
            capability,
            MCPResponse(
                success=True,
                content=[{"type": "text", "text": "direct prompt"}],
                latency_ms=2,
            ),
        )

        recorder = TopicRecorder(
            session.bus,
            topics=(
                TOPIC_TASK_DISPATCH,
                TOPIC_TASK_COMPLETE,
                TOPIC_TASK_FAILED,
                TOPIC_RESPONSE_STREAM,
                TOPIC_FINAL_RESPONSE,
                TOPIC_TURN_COMPLETED,
                TOPIC_DEAD_LETTER,
            ),
        )
        recorder.start()
        try:
            _publish_user_input(
                session,
                session_id=session_id,
                trace_id=trace_id,
                text="Run this as a direct LOW prompt lookup.",
            )

            await recorder.wait_for_topics(
                {TOPIC_TASK_DISPATCH, TOPIC_TASK_COMPLETE, TOPIC_TURN_COMPLETED},
                timeout_s=30.0,
            )

            topics = [envelope.topic for envelope in recorder.envelopes]
            assert TOPIC_DEAD_LETTER not in topics
            assert TOPIC_TASK_FAILED not in topics
            assert session.concierge.state == "LISTENING"

            assert _first_index(recorder, TOPIC_TASK_DISPATCH) < _first_index(
                recorder, TOPIC_TASK_COMPLETE
            )
            assert _first_index(recorder, TOPIC_TASK_COMPLETE) < _first_index(
                recorder, TOPIC_TURN_COMPLETED
            )

            dispatch_env = recorder.by_topic(TOPIC_TASK_DISPATCH)[0]
            dispatch_payload = _decode_payload(dispatch_env)
            assert dispatch_env.cognitive_trace_id == trace_id
            assert dispatch_env.session_id == session_id
            assert dispatch_payload["tier"] == "LOW"
            assert dispatch_payload["plan"] is False
            assert dispatch_payload["intents"][0]["action"] == capability

            complete_env = recorder.by_topic(TOPIC_TASK_COMPLETE)[0]
            complete_payload = _decode_payload(complete_env)
            assert complete_env.cognitive_trace_id == trace_id
            assert complete_env.session_id == session_id
            assert complete_payload["final_answer"] == "Direct LOW result."
            assert complete_payload.get("source") != "orchestrator"

            captured = transport.drain()
            assert [call.tool_name for call in captured] == [capability]
            assert captured[0].arguments == {"intent": "direct family prompt", "top_k": 1}
            assert captured[0].trace_id == trace_id
            assert orchestrator_calls == []

            fired_labels = [rule.label for rule in scripted.rules if rule.fired]
            assert fired_labels == [
                "front-dispatch-low-direct",
                "back-low-invoke",
                "back-low-submit",
            ]
        finally:
            recorder.stop()
    finally:
        if dispatch_port is not None and original_dispatch_envelope is not None:
            dispatch_port.dispatch_envelope = original_dispatch_envelope
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m1_x8_crisis_turn_short_circuits_llm_and_fabric(tmp_path: Path) -> None:
    """M1-X8: CRISIS safety band emits static response with no LLM/Fabric calls."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        scripted = await install_scripted_plugin(svc)

        session_id = "m1x8"
        trace_id = "trace-m1-x8"
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        recorder = TopicRecorder(
            session.bus,
            topics=(
                TOPIC_TURN_STARTED,
                TOPIC_INTENT_ARBITRATED,
                TOPIC_TASK_DISPATCH,
                TOPIC_TASK_COMPLETE,
                TOPIC_RESPONSE_STREAM,
                TOPIC_FINAL_RESPONSE,
                TOPIC_TURN_COMPLETED,
                TOPIC_DEAD_LETTER,
            ),
        )
        recorder.start()
        try:
            _publish_user_input(
                session,
                session_id=session_id,
                trace_id=trace_id,
                text="I want to die.",
            )

            await recorder.wait_for_topics(
                {TOPIC_TURN_STARTED, TOPIC_FINAL_RESPONSE, TOPIC_TURN_COMPLETED},
                timeout_s=20.0,
            )

            topics = [envelope.topic for envelope in recorder.envelopes]
            assert TOPIC_DEAD_LETTER not in topics
            assert TOPIC_INTENT_ARBITRATED not in topics
            assert TOPIC_TASK_DISPATCH not in topics
            assert TOPIC_TASK_COMPLETE not in topics
            assert TOPIC_RESPONSE_STREAM not in topics
            assert session.concierge.state == "LISTENING"
            assert scripted.calls == []

            final_env = recorder.by_topic(TOPIC_FINAL_RESPONSE)[0]
            final_payload = _decode_payload(final_env)
            assert final_env.cognitive_trace_id == trace_id
            assert final_env.session_id == session_id
            assert final_payload["source"] == "crisis_protocol"
            assert final_payload["safety_band"] == "CRISIS"
            assert "988" in final_payload["text"]

            completed_payload = _decode_payload(recorder.by_topic(TOPIC_TURN_COMPLETED)[0])
            assert completed_payload["cognitive_trace_id"] == trace_id
            assert completed_payload["assistant_response"] == final_payload["text"]

            control = session.session_state.get_section("control")
            assert control.get_safety().band == PrivacyBand.RED
        finally:
            recorder.stop()
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m1_x9_backchannel_write_elision_gate_is_wired(tmp_path: Path) -> None:
    """M1-X9: desired backchannel gate exists and owns low-signal writes."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        scripted = await install_scripted_plugin(svc)
        scripted.queue(
            make_text_response("Okay."),
            predicate=_is_front_request,
            label="front-backchannel-text",
        )

        session_id = "m1x9"
        trace_id = "trace-m1-x9"
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        recorder = TopicRecorder(
            session.bus,
            topics=(TOPIC_FINAL_RESPONSE, TOPIC_TURN_COMPLETED, TOPIC_DEAD_LETTER),
        )
        recorder.start()
        try:
            _publish_user_input(
                session,
                session_id=session_id,
                trace_id=trace_id,
                text="ok",
            )
            await recorder.wait_for_topics(
                {TOPIC_FINAL_RESPONSE, TOPIC_TURN_COMPLETED},
                timeout_s=20.0,
            )
            assert recorder.by_topic(TOPIC_DEAD_LETTER) == []
            assert [rule.label for rule in scripted.rules if rule.fired] == [
                "front-backchannel-text"
            ]

            write_elision = importlib.import_module("k1.concierge.acking.write_elision")
            assert hasattr(write_elision, "WriteElisionGate")
            assert getattr(session.concierge._fsm, "_write_elision_gate", None) is not None
        finally:
            recorder.stop()
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m1_x10_legacy_hitl_resolution_emits_hil_response_before_resume(
    tmp_path: Path,
) -> None:
    """M1-X10: desired protocol event precedes task.resume on legacy HITL."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_b(tmp_path))

    try:
        await svc.startup()
        scripted = await install_scripted_plugin(svc)
        capability = "tool.read.find_prompts"

        scripted.queue(
            make_tool_call_response(
                (
                    "dispatch_task",
                    {
                        "intents": [
                            {
                                "action": capability,
                                "params": {"intent": "travel prompt", "top_k": 1},
                                "urgency": "normal",
                            }
                        ],
                        "safety_band": "GREEN",
                    },
                )
            ),
            predicate=lambda req: _is_front_request(req)
            and "Ask me for a city" in _request_text(req),
            label="front-dispatch-hitl-x10",
        )
        scripted.queue(
            make_tool_call_response(
                (
                    "submit_result",
                    {
                        "result_type": "needs_human",
                        "hil_type": "clarification",
                        "question": "Which city should I use?",
                        "options": [{"label": "Paris", "value": "Paris"}],
                        "side_effects": "",
                    },
                )
            ),
            predicate=_is_back_request,
            label="back-needs-human-x10",
        )
        scripted.queue(
            make_text_response("Which city should I use?"),
            predicate=lambda req: _is_front_request(req) and not getattr(req, "tools", None),
            label="front-hitl-relay-x10",
        )
        scripted.queue(
            make_text_response("Got it."),
            predicate=lambda req: _is_front_request(req) and "Use Paris." in _request_text(req),
            label="front-hitl-resolve-x10",
        )
        scripted.queue(
            make_tool_call_response(
                (
                    "invoke_capability",
                    {
                        "capability_name": capability,
                        "params": {"intent": "travel prompt", "top_k": 1},
                    },
                )
            ),
            predicate=_is_back_request,
            label="back-resume-invoke-x10",
        )
        scripted.queue(
            make_tool_call_response(
                (
                    "submit_result",
                    {
                        "result_type": "complete",
                        "final_answer": "Done with Paris.",
                        "results": [{"city": "Paris"}],
                        "artifacts_created": [],
                    },
                )
            ),
            predicate=_is_back_request,
            label="back-resume-submit-x10",
        )

        session_id = "m1x10"
        trace_id = "trace-m1-x10"
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        transport = _install_test_mcp_transport(session.fabric)
        from k1.fabric.providers.mcp_provider import MCPResponse

        transport.add_response(
            capability,
            MCPResponse(
                success=True,
                content=[{"type": "text", "text": "Paris prompt found"}],
                latency_ms=2,
            ),
        )

        recorder = TopicRecorder(
            session.bus,
            topics=(
                TOPIC_TASK_DISPATCH,
                TOPIC_TASK_SUSPENDED,
                TOPIC_HIL_RESPONSE,
                TOPIC_TASK_RESUME,
                TOPIC_TASK_COMPLETE,
                TOPIC_FINAL_RESPONSE,
                TOPIC_TASK_FAILED,
                TOPIC_DEAD_LETTER,
            ),
        )
        recorder.start()
        try:
            _publish_user_input(
                session,
                session_id=session_id,
                trace_id=trace_id,
                text="Ask me for a city before finding a travel prompt.",
            )
            await recorder.wait_for_topics(
                {TOPIC_TASK_DISPATCH, TOPIC_TASK_SUSPENDED},
                timeout_s=30.0,
            )
            await _wait_for_count(recorder, TOPIC_FINAL_RESPONSE, 2, timeout_s=30.0)

            _publish_user_input(
                session,
                session_id=session_id,
                trace_id=trace_id,
                text="Use Paris.",
            )
            await recorder.wait_for_topics(
                {TOPIC_TASK_RESUME, TOPIC_TASK_COMPLETE},
                timeout_s=30.0,
            )
            await _wait_for_predicate(lambda: session.concierge.state == "LISTENING")

            assert recorder.by_topic(TOPIC_TASK_FAILED) == []
            assert recorder.by_topic(TOPIC_DEAD_LETTER) == []
            assert recorder.by_topic(TOPIC_HIL_RESPONSE)
            assert _first_index(recorder, TOPIC_HIL_RESPONSE) < _first_index(
                recorder, TOPIC_TASK_RESUME
            )
        finally:
            recorder.stop()
    finally:
        await _cleanup_service(svc, baseline_tasks)
