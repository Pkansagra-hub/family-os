"""M1-L6..L9 live-kernel Concierge lifecycle and HITL probes."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from k1.concierge.bus.builders import build_user_input
from k1.concierge.bus.topics import (
    TOPIC_DEAD_LETTER,
    TOPIC_FINAL_RESPONSE,
    TOPIC_HITL_REQUESTED,
    TOPIC_HITL_RESOLVED,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_RESUME,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TURN_COMPLETED,
)
from k1.concierge.ledger.recovery import CrashRecoveryOrchestrator
from k1.concierge.protocols.hitl_persistence import TaskStatus
from k1.kernel.service import KernelService
from tests.integration.k1.live.m1.test_m1_l3_low_tier_message_flow import (
    TopicRecorder,
    _active_task_snapshot,
    _cleanup_service,
    _decode_payload,
    _install_test_mcp_transport,
    _recipe_a,
)
from tests.k1.integration.concierge.scripted_provider import (
    install_scripted_plugin,
    make_text_response,
    make_tool_call_response,
)

pytestmark = pytest.mark.integration


def _recipe_b(tmp_path: Path) -> Any:
    config = _recipe_a(tmp_path)
    config.enable_hitl = True
    config.enable_hil_service = True
    return config


async def _wait_for_count(
    recorder: TopicRecorder,
    topic: str,
    count: int,
    *,
    timeout_s: float = 20.0,
) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        if len(recorder.by_topic(topic)) >= count:
            return
        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError(f"missing {count} envelopes for {topic} after {timeout_s}s")
        await asyncio.sleep(0.05)


async def _wait_for_predicate(
    predicate: Callable[[], bool],
    *,
    timeout_s: float = 20.0,
) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        if predicate():
            return
        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError(f"predicate not satisfied after {timeout_s}s")
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_m1_l6_set_self_model_after_start_is_guarded(tmp_path: Path) -> None:
    """M1-L6/M1-X11: post-start SelfModel attachment fails cleanly."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        session_id = "m1l6"
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        concierge = session.concierge

        original_self_model = concierge._self_model
        original_state = concierge.state

        with pytest.raises(RuntimeError, match="before start"):
            concierge.set_self_model(object())

        assert concierge._self_model is original_self_model
        assert concierge.state == original_state
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="ISSUE-C02: ExperienceLayer does not wire EpisodicCompressor yet",
)
async def test_m1_l7_experience_layer_compresses_after_sixteen_turns(
    tmp_path: Path,
) -> None:
    """M1-L7: desired OPP-6 behavior after a 16-turn live session history."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        session_id = "m1l7"
        await svc.create_session(session_id)
        session = svc._sessions[session_id]
        layer = session.experience_layer

        context: dict[str, Any] = {
            "turn_transcript": "",
            "affect_history": [],
            "front_refine_affect_confidence": 0.0,
            "conversation_history": [],
            "memory_recalls": [],
            "task_state": {},
            "user_patterns": {},
            "wait_duration_ms": 0,
            "persona": {},
            "user_cadence": {},
        }
        for turn_number in range(1, 17):
            context["conversation_history"].append(
                {
                    "turn_number": turn_number,
                    "user_message": f"user turn {turn_number}",
                    "response": f"assistant turn {turn_number}",
                    "intent": "m1_l7_probe",
                }
            )
            await layer.tick("LISTENING", context)

        compressor = layer.episodic_compressor
        assert compressor.compression_count > 0
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m1_l8_hitl_relay_external_resolve_reaches_back_resume(
    tmp_path: Path,
) -> None:
    """M1-L8: Back suspension relays through Front and resumes via Back router."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_b(tmp_path))

    try:
        await svc.startup()
        scripted = await install_scripted_plugin(svc)

        capability = "tool.read.find_prompts"

        def request_text(req: Any) -> str:
            parts: list[str] = []
            if getattr(req, "system_prompt", None):
                parts.append(str(req.system_prompt))
            for message in getattr(req, "messages", []) or []:
                parts.append(str(getattr(message, "content", "")))
            return "\n".join(parts)

        def is_front_request(req: Any) -> bool:
            return getattr(req, "consumer_id", "") == "concierge.front"

        def is_front_standard(req: Any) -> bool:
            return is_front_request(req) and "Find a travel prompt" in request_text(req)

        def is_front_hitl_relay(req: Any) -> bool:
            return is_front_request(req) and not getattr(req, "tools", None)

        def is_front_hitl_resolve(req: Any) -> bool:
            return is_front_request(req) and "Use Paris." in request_text(req)

        def is_back_request(req: Any) -> bool:
            return getattr(req, "consumer_id", "") == "concierge.back"

        scripted.queue(
            make_tool_call_response(
                (
                    "dispatch_task",
                    {
                        "intents": [
                            {
                                "action": capability,
                                "params": {"intent": "family travel prompt", "top_k": 1},
                                "urgency": "normal",
                            }
                        ],
                        "safety_band": "GREEN",
                    },
                )
            ),
            predicate=is_front_standard,
            label="front-dispatch-hitl",
        )
        scripted.queue(
            make_tool_call_response(
                (
                    "submit_result",
                    {
                        "result_type": "needs_human",
                        "hil_type": "clarification",
                        "question": "Which city should I use for the travel prompt?",
                        "options": [
                            {"label": "Paris", "value": "Paris"},
                            {"label": "Lyon", "value": "Lyon"},
                        ],
                        "side_effects": "",
                    },
                )
            ),
            predicate=is_back_request,
            label="back-needs-human",
        )
        scripted.queue(
            make_text_response("Which city should I use for the travel prompt?"),
            predicate=is_front_hitl_relay,
            label="front-hitl-relay",
        )
        scripted.queue(
            make_text_response("Got it, I will continue with that answer."),
            predicate=is_front_hitl_resolve,
            label="front-hitl-resolve",
        )
        scripted.queue(
            make_tool_call_response(
                (
                    "invoke_capability",
                    {
                        "capability_name": capability,
                        "params": {"intent": "family travel prompt", "top_k": 1},
                    },
                )
            ),
            predicate=is_back_request,
            label="back-resume-invoke",
        )
        scripted.queue(
            make_tool_call_response(
                (
                    "submit_result",
                    {
                        "result_type": "complete",
                        "final_answer": "Resumed with Paris.",
                        "results": [{"city": "Paris"}],
                        "artifacts_created": [],
                    },
                )
            ),
            predicate=is_back_request,
            label="back-resume-submit",
        )

        session_id = "m1l8"
        trace_id = "trace-m1-l8"
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
                TOPIC_HITL_REQUESTED,
                TOPIC_TASK_RESUME,
                TOPIC_HITL_RESOLVED,
                TOPIC_TASK_COMPLETE,
                TOPIC_TASK_FAILED,
                TOPIC_DEAD_LETTER,
                TOPIC_FINAL_RESPONSE,
                TOPIC_TURN_COMPLETED,
            ),
        )
        recorder.start()
        try:
            session.bus.publish(
                replace(
                    build_user_input(
                        payload={
                            "text": "Find a travel prompt, but ask me if you need a city.",
                            "session_id": session_id,
                            "device_id": "device-m1-l8",
                        }
                    ),
                    cognitive_trace_id=trace_id,
                    session_id=session_id,
                    request_id="request-m1-l8",
                )
            )

            await recorder.wait_for_topics(
                {TOPIC_TASK_DISPATCH, TOPIC_TASK_SUSPENDED, TOPIC_HITL_REQUESTED},
                timeout_s=30.0,
            )
            await _wait_for_count(recorder, TOPIC_FINAL_RESPONSE, 2, timeout_s=30.0)
            assert session.concierge.state == "CLARIFYING_WORKER"

            session.bus.publish(
                replace(
                    build_user_input(
                        payload={
                            "text": "Use Paris.",
                            "session_id": session_id,
                            "device_id": "device-m1-l8",
                        }
                    ),
                    cognitive_trace_id=trace_id,
                    session_id=session_id,
                    request_id="request-m1-l8-answer",
                )
            )

            await recorder.wait_for_topics(
                {TOPIC_TASK_RESUME, TOPIC_HITL_RESOLVED, TOPIC_TASK_COMPLETE},
                timeout_s=30.0,
            )
            await _wait_for_predicate(lambda: session.concierge.state == "LISTENING")

            topics = [envelope.topic for envelope in recorder.envelopes]
            assert TOPIC_DEAD_LETTER not in topics
            assert TOPIC_TASK_FAILED not in topics

            resume_env = recorder.by_topic(TOPIC_TASK_RESUME)[0]
            resume_payload = _decode_payload(resume_env)
            assert resume_env.cognitive_trace_id == trace_id
            assert resume_env.session_id == session_id
            assert resume_payload["resolution"]["additional_info"] == "Use Paris."

            resolved_payload = _decode_payload(recorder.by_topic(TOPIC_HITL_RESOLVED)[0])
            assert resolved_payload["task_id"] == resume_payload["task_id"]

            complete_env = recorder.by_topic(TOPIC_TASK_COMPLETE)[0]
            complete_payload = _decode_payload(complete_env)
            assert complete_env.cognitive_trace_id == trace_id
            assert complete_env.session_id == session_id
            assert complete_payload["task_id"] == resume_payload["task_id"]
            assert complete_payload["final_answer"] == "Resumed with Paris."

            fired_labels = [rule.label for rule in scripted.rules if rule.fired]
            assert fired_labels == [
                "front-dispatch-hitl",
                "back-needs-human",
                "front-hitl-relay",
                "front-hitl-resolve",
                "back-resume-invoke",
                "back-resume-submit",
            ]
            captured = transport.drain()
            assert [call.tool_name for call in captured] == [capability]
        finally:
            recorder.stop()
    finally:
        await _cleanup_service(svc, baseline_tasks)


def test_m1_l9_crash_recovery_priority_order() -> None:
    """M1-L9: crash recovery state derivation honors documented priority."""
    recovery = CrashRecoveryOrchestrator()
    user_input = SimpleNamespace(event_type="conversation.user_input.received")
    delivered = SimpleNamespace(event_type="conversation.response.delivered.v1")

    assert (
        recovery._derive_fsm_state(
            [user_input],
            {
                "suspended": SimpleNamespace(status=TaskStatus.SUSPENDED),
                "active": SimpleNamespace(status=TaskStatus.IN_PROGRESS),
            },
            {"pending": object()},
        )
        == "CLARIFYING_WORKER"
    )
    assert (
        recovery._derive_fsm_state(
            [user_input],
            {"active": SimpleNamespace(status=TaskStatus.DISPATCHED)},
            {"pending": object()},
        )
        == "WEAVING"
    )
    assert (
        recovery._derive_fsm_state(
            [user_input],
            {"active": SimpleNamespace(status=TaskStatus.IN_PROGRESS)},
            {},
        )
        == "COMPANIONING"
    )
    assert recovery._derive_fsm_state([user_input], {}, {}) == "DISPATCHING"
    assert recovery._derive_fsm_state([user_input, delivered], {}, {}) == "LISTENING"
