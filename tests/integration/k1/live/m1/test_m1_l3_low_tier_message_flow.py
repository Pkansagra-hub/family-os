"""M1-L3 live-kernel LOW-tier Concierge message-flow probe."""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

import pytest

from k1.bus.envelope import Envelope
from k1.concierge.bus.builders import build_user_input
from k1.concierge.bus.topics import (
    TOPIC_DEAD_LETTER,
    TOPIC_FINAL_RESPONSE,
    TOPIC_INTENT_ARBITRATED,
    TOPIC_RESPONSE_STREAM,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TURN_COMPLETED,
    TOPIC_TURN_STARTED,
)
from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService
from tests.k1.integration.concierge.scripted_provider import (
    install_scripted_plugin,
    make_text_response,
    make_tool_call_response,
)

pytestmark = pytest.mark.integration


def _active_task_snapshot() -> set[asyncio.Task[object]]:
    current = asyncio.current_task()
    return {task for task in asyncio.all_tasks() if task is not current and not task.done()}


def _recipe_a(tmp_path: Path) -> KernelConfig:
    return KernelConfig(
        test_mode=True,
        model_mode="test",
        ordered_bus=True,
        session_mode="standalone",
        bridge_enabled=False,
        bridge_offline_ok=True,
        otel_enabled=False,
        enable_hitl=False,
        enable_hil_service=False,
        enable_self_model=False,
        enable_family_tools=False,
        sessionstate_db_path=str(tmp_path / "ssm.db"),
        workflow_db_path=str(tmp_path / "workflows.db"),
        bridge_outbox_path=str(tmp_path / "bridge.db"),
    )


async def _assert_no_task_leaks(baseline_tasks: set[asyncio.Task[object]]) -> None:
    await asyncio.sleep(0)
    leaked = _active_task_snapshot() - baseline_tasks
    assert leaked == set(), f"Leaked tasks: {[task.get_name() for task in leaked]}"


async def _cleanup_service(
    svc: KernelService,
    baseline_tasks: set[asyncio.Task[object]],
) -> None:
    if svc.is_running:
        await svc.shutdown()
    await _assert_no_task_leaks(baseline_tasks)


def _decode_payload(envelope: Envelope) -> dict[str, Any]:
    return json.loads(envelope.payload.decode("utf-8"))


def _install_test_mcp_transport(fabric: Any) -> Any:
    from k1.fabric.adapters.test_mcp_transport import TestMCPTransport

    facade = getattr(fabric, "facade", None) or fabric
    provider_factory = getattr(facade, "_provider_factory", None)
    assert provider_factory is not None
    port_deps = getattr(provider_factory, "_port_deps", None)
    assert port_deps is not None
    transport = TestMCPTransport(connected=True)
    port_deps["mcp_transport"] = transport
    provider_factory._port_deps = port_deps
    return transport


class TopicRecorder:
    """Record envelopes from a fixed set of live bus topics."""

    def __init__(self, bus: Any, topics: Iterable[str]) -> None:
        self._bus = bus
        self._topics = tuple(topics)
        self._handles: list[Any] = []
        self._lock = threading.RLock()
        self.envelopes: list[Envelope] = []

    def start(self) -> None:
        for topic in self._topics:
            self._handles.append(self._bus.subscribe(topic, self._on_envelope))

    def stop(self) -> None:
        for handle in self._handles:
            try:
                self._bus.unsubscribe(handle)
            except Exception:
                pass
        self._handles.clear()

    def _on_envelope(self, envelope: Envelope) -> None:
        with self._lock:
            self.envelopes.append(envelope)

    def by_topic(self, topic: str) -> list[Envelope]:
        with self._lock:
            return [envelope for envelope in self.envelopes if envelope.topic == topic]

    async def wait_for_topics(
        self,
        required: set[str],
        *,
        timeout_s: float = 20.0,
    ) -> None:
        deadline = asyncio.get_event_loop().time() + timeout_s
        while True:
            with self._lock:
                seen = {envelope.topic for envelope in self.envelopes}
            if required.issubset(seen):
                return
            if asyncio.get_event_loop().time() >= deadline:
                missing = sorted(required - seen)
                raise TimeoutError(f"missing topics after {timeout_s}s: {missing}")
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_m1_l3_low_tier_user_message_reaches_final_turn_completed(
    tmp_path: Path,
) -> None:
    """M1-L3: real user input drives Front-only LOW flow to final + turn.completed."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        scripted = await install_scripted_plugin(svc)
        scripted.queue(
            make_text_response("Hello from the live M1 LOW path."),
            predicate=lambda req: getattr(req, "consumer_id", "") == "concierge.front",
            label="front-low-text",
        )

        session_id = "m1l3"
        trace_id = "trace-m1-l3"
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        recorder = TopicRecorder(
            session.bus,
            topics=(
                TOPIC_TURN_STARTED,
                TOPIC_INTENT_ARBITRATED,
                TOPIC_RESPONSE_STREAM,
                TOPIC_FINAL_RESPONSE,
                TOPIC_TURN_COMPLETED,
                TOPIC_TASK_DISPATCH,
                TOPIC_DEAD_LETTER,
            ),
        )
        recorder.start()
        try:
            user_text = "Hello Concierge, just say hi."
            session.bus.publish(
                replace(
                    build_user_input(
                        payload={
                            "text": user_text,
                            "session_id": session_id,
                            "device_id": "device-m1-l3",
                        }
                    ),
                    cognitive_trace_id=trace_id,
                    session_id=session_id,
                    request_id="request-m1-l3",
                )
            )

            await recorder.wait_for_topics(
                {
                    TOPIC_TURN_STARTED,
                    TOPIC_INTENT_ARBITRATED,
                    TOPIC_RESPONSE_STREAM,
                    TOPIC_FINAL_RESPONSE,
                    TOPIC_TURN_COMPLETED,
                }
            )

            topics = [envelope.topic for envelope in recorder.envelopes]
            assert TOPIC_TASK_DISPATCH not in topics
            assert TOPIC_DEAD_LETTER not in topics
            assert session.concierge.state == "LISTENING"

            def first_index(topic: str) -> int:
                return next(
                    i for i, envelope in enumerate(recorder.envelopes) if envelope.topic == topic
                )

            assert first_index(TOPIC_TURN_STARTED) < first_index(TOPIC_INTENT_ARBITRATED)
            assert first_index(TOPIC_INTENT_ARBITRATED) < first_index(TOPIC_RESPONSE_STREAM)
            assert first_index(TOPIC_RESPONSE_STREAM) < first_index(TOPIC_FINAL_RESPONSE)
            assert first_index(TOPIC_FINAL_RESPONSE) < first_index(TOPIC_TURN_COMPLETED)

            final_env = recorder.by_topic(TOPIC_FINAL_RESPONSE)[0]
            final_payload = _decode_payload(final_env)
            assert final_env.cognitive_trace_id == trace_id
            assert final_env.session_id == session_id
            assert final_payload["text"] == "Hello from the live M1 LOW path."
            assert final_payload["trace_id"] == trace_id

            completed_env = recorder.by_topic(TOPIC_TURN_COMPLETED)[0]
            completed_payload = _decode_payload(completed_env)
            assert completed_payload["session_id"] == session.concierge._ledger.session_id
            assert completed_payload["cognitive_trace_id"] == trace_id
            assert completed_payload["user_message"] == user_text
            assert completed_payload["assistant_response"] == final_payload["text"]
            assert completed_payload["turn_number"] == 1

            assert scripted.rules[0].fired == 1
        finally:
            recorder.stop()
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m1_l4_medium_dispatch_reaches_orchestrator_fabric_result(
    tmp_path: Path,
) -> None:
    """M1-L4: MED-tier Front dispatch reaches orchestrator and live Fabric edge."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        transport = _install_test_mcp_transport(svc._shared_fabric)
        scripted = await install_scripted_plugin(svc)

        def is_front_request(req: Any) -> bool:
            return getattr(req, "consumer_id", "") == "concierge.front"

        capability = "tool.read.find_prompts"
        from k1.fabric.providers.mcp_provider import MCPResponse

        transport.add_response(
            capability,
            MCPResponse(
                success=True,
                content=[{"type": "text", "text": "[]"}],
                latency_ms=2,
            ),
        )
        scripted.queue(
            make_tool_call_response(
                (
                    "dispatch_task",
                    {
                        "intents": [
                            {
                                "action": capability,
                                "params": {"intent": "family planning prompt", "top_k": 1},
                                "urgency": "normal",
                            }
                        ],
                        "safety_band": "GREEN",
                        "plan": True,
                    },
                )
            ),
            predicate=is_front_request,
            label="front-dispatch-medium",
        )
        session_id = "m1l4"
        trace_id = "trace-m1-l4"
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        recorder = TopicRecorder(
            session.bus,
            topics=(
                TOPIC_TURN_STARTED,
                TOPIC_INTENT_ARBITRATED,
                TOPIC_TASK_DISPATCH,
                TOPIC_TASK_COMPLETE,
                TOPIC_TASK_FAILED,
                TOPIC_RESPONSE_STREAM,
                TOPIC_FINAL_RESPONSE,
                TOPIC_TURN_COMPLETED,
                TOPIC_DEAD_LETTER,
            ),
        )
        state_at_complete: list[str] = []

        def record_complete_state(_envelope: Envelope) -> None:
            state_at_complete.append(session.concierge.state)

        state_handle = session.bus.subscribe(TOPIC_TASK_COMPLETE, record_complete_state)
        recorder.start()
        try:
            user_text = "Plan and list my notes."
            session.bus.publish(
                replace(
                    build_user_input(
                        payload={
                            "text": user_text,
                            "session_id": session_id,
                            "device_id": "device-m1-l4",
                        }
                    ),
                    cognitive_trace_id=trace_id,
                    session_id=session_id,
                    request_id="request-m1-l4",
                )
            )

            await recorder.wait_for_topics(
                {
                    TOPIC_TURN_STARTED,
                    TOPIC_INTENT_ARBITRATED,
                    TOPIC_TASK_DISPATCH,
                    TOPIC_TASK_COMPLETE,
                    TOPIC_RESPONSE_STREAM,
                    TOPIC_FINAL_RESPONSE,
                    TOPIC_TURN_COMPLETED,
                },
                timeout_s=30.0,
            )

            topics = [envelope.topic for envelope in recorder.envelopes]
            assert TOPIC_DEAD_LETTER not in topics
            assert TOPIC_TASK_FAILED not in topics
            assert session.concierge.state == "LISTENING"

            def first_index(topic: str) -> int:
                return next(
                    i for i, envelope in enumerate(recorder.envelopes) if envelope.topic == topic
                )

            assert first_index(TOPIC_TURN_STARTED) < first_index(TOPIC_INTENT_ARBITRATED)
            assert first_index(TOPIC_INTENT_ARBITRATED) < first_index(TOPIC_TASK_DISPATCH)
            dispatch_index = first_index(TOPIC_TASK_DISPATCH)
            complete_index = first_index(TOPIC_TASK_COMPLETE)
            completed_index = first_index(TOPIC_TURN_COMPLETED)
            response_stream_indexes = [
                i
                for i, envelope in enumerate(recorder.envelopes)
                if envelope.topic == TOPIC_RESPONSE_STREAM
            ]
            final_indexes = [
                i
                for i, envelope in enumerate(recorder.envelopes)
                if envelope.topic == TOPIC_FINAL_RESPONSE
            ]
            assert dispatch_index < complete_index
            assert any(dispatch_index < i < complete_index for i in response_stream_indexes)
            assert any(dispatch_index < i < complete_index for i in final_indexes)
            assert first_index(TOPIC_FINAL_RESPONSE) < completed_index

            dispatch_env = recorder.by_topic(TOPIC_TASK_DISPATCH)[0]
            dispatch_payload = _decode_payload(dispatch_env)
            assert dispatch_env.cognitive_trace_id == trace_id
            assert dispatch_env.session_id == session_id
            assert dispatch_payload["tier"] == "MEDIUM"
            assert dispatch_payload["plan"] is True
            assert dispatch_payload["trace_id"] == trace_id
            assert dispatch_payload["intents"][0]["action"] == capability

            complete_env = recorder.by_topic(TOPIC_TASK_COMPLETE)[0]
            complete_payload = _decode_payload(complete_env)
            assert complete_env.cognitive_trace_id == trace_id
            assert complete_env.session_id == session_id
            assert complete_payload["source"] == "orchestrator"
            assert complete_payload["process_result"] in {"COMPLETED", "DEGRADED"}
            assert complete_payload["trace_id"] == trace_id
            assert complete_payload["session_id"] == session_id

            # M1-X4/X6: same-turn task.complete is suppressed from a second
            # Front final and closes the turn from LISTENING.
            assert state_at_complete == ["LISTENING"]

            final_env = recorder.by_topic(TOPIC_FINAL_RESPONSE)[0]
            final_payload = _decode_payload(final_env)
            assert final_env.cognitive_trace_id == trace_id
            assert final_env.session_id == session_id
            # KERNEL CONTRACT: when the LLM returns no post-dispatch text,
            # Front does NOT synthesize an English fallback.  The structured
            # task.dispatch.v1 envelope is the ack signal.  Final text is
            # therefore the empty string (presentation layers render their
            # own affordance from the dispatch envelope).
            assert final_payload["text"] == ""
            assert final_payload["trace_id"] == trace_id

            completed_env = recorder.by_topic(TOPIC_TURN_COMPLETED)[0]
            completed_payload = _decode_payload(completed_env)
            assert completed_payload["session_id"] == session.concierge._ledger.session_id
            assert completed_payload["cognitive_trace_id"] == trace_id
            assert completed_payload["user_message"] == user_text
            assert completed_payload["assistant_response"] == final_payload["text"]
            assert completed_payload["turn_number"] == 1

            session.concierge._fsm._emit_turn_completed(final_env)
            assert len(recorder.by_topic(TOPIC_TURN_COMPLETED)) == 1

            fired_labels = [rule.label for rule in scripted.rules if rule.fired]
            assert fired_labels == ["front-dispatch-medium"]

            captured = transport.drain()
            assert [call.tool_name for call in captured] == [capability]
            assert captured[0].arguments == {"intent": "family planning prompt", "top_k": 1}
            assert captured[0].trace_id == trace_id
        finally:
            session.bus.unsubscribe(state_handle)
            recorder.stop()
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m1_l5_high_dispatch_runs_planner_orchestrator_fabric(
    tmp_path: Path,
) -> None:
    """M1-L5: HIGH-tier dispatch is wired through planner and orchestrator today."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        transport = _install_test_mcp_transport(svc._shared_fabric)
        scripted = await install_scripted_plugin(svc)

        capability = "tool.read.find_prompts"
        from k1.fabric.providers.mcp_provider import MCPResponse

        transport.add_response(
            capability,
            MCPResponse(
                success=True,
                content=[{"type": "text", "text": "[]"}],
                latency_ms=2,
            ),
        )

        def is_front_request(req: Any) -> bool:
            return getattr(req, "consumer_id", "") == "concierge.front"

        def is_planner_request(req: Any) -> bool:
            return getattr(req, "consumer_id", "") == "planner"

        scripted.queue(
            make_tool_call_response(
                (
                    "dispatch_task",
                    {
                        "intents": [
                            {
                                "action": capability,
                                "params": {"intent": "family planning prompt", "top_k": 1},
                                "urgency": "normal",
                            }
                        ],
                        "safety_band": "GREEN",
                        "plan": True,
                        "complexity": "HIGH",
                    },
                )
            ),
            predicate=is_front_request,
            label="front-dispatch-high",
        )

        scripted.queue(
            make_text_response(
                json.dumps(
                    {
                        "rough_steps": [
                            {
                                "intent": "Find a family planning prompt template.",
                                "depends_on": [],
                            }
                        ],
                        "rationale": "Single registered capability fulfils the request.",
                        "needs_clarification": False,
                    }
                )
            ),
            predicate=is_planner_request,
            label="planner-sketch",
        )
        scripted.queue(
            make_text_response(
                json.dumps(
                    {
                        "steps": [
                            {
                                "id": "s1",
                                "capability": capability,
                                "params": {"intent": "family planning prompt", "top_k": 1},
                                "deps": [],
                                "output_schema": {"type": "object"},
                                "timeout_ms": 5000,
                            }
                        ],
                        "dependencies": {"s1": []},
                        "rationale": "One safe read-only prompt lookup.",
                    }
                )
            ),
            predicate=is_planner_request,
            label="planner-expand",
        )
        scripted.queue(
            make_text_response(
                json.dumps(
                    {
                        "status": "approved",
                        "reasons": ["Plan is coherent, safe, and complete."],
                        "coherence_score": 1.0,
                        "safety_assessment": "safe",
                        "completeness": True,
                    }
                )
            ),
            predicate=is_planner_request,
            label="planner-validate",
        )

        session_id = "m1l5"
        trace_id = "trace-m1-l5"
        await svc.create_session(session_id)
        session = svc._sessions[session_id]

        recorder = TopicRecorder(
            session.bus,
            topics=(
                TOPIC_TURN_STARTED,
                TOPIC_INTENT_ARBITRATED,
                TOPIC_TASK_DISPATCH,
                TOPIC_TASK_COMPLETE,
                TOPIC_TASK_FAILED,
                TOPIC_FINAL_RESPONSE,
                TOPIC_TURN_COMPLETED,
                TOPIC_DEAD_LETTER,
            ),
        )
        recorder.start()
        try:
            user_text = "Plan the prompt lookup with the high-tier planner."
            session.bus.publish(
                replace(
                    build_user_input(
                        payload={
                            "text": user_text,
                            "session_id": session_id,
                            "device_id": "device-m1-l5",
                        }
                    ),
                    cognitive_trace_id=trace_id,
                    session_id=session_id,
                    request_id="request-m1-l5",
                )
            )

            await recorder.wait_for_topics(
                {
                    TOPIC_TURN_STARTED,
                    TOPIC_INTENT_ARBITRATED,
                    TOPIC_TASK_DISPATCH,
                    TOPIC_FINAL_RESPONSE,
                    TOPIC_TURN_COMPLETED,
                    TOPIC_TASK_COMPLETE,
                },
                timeout_s=60.0,
            )

            topics = [envelope.topic for envelope in recorder.envelopes]
            assert TOPIC_TASK_FAILED not in topics
            assert TOPIC_DEAD_LETTER not in topics
            assert session.concierge.state == "LISTENING"

            dispatch_env = recorder.by_topic(TOPIC_TASK_DISPATCH)[0]
            dispatch_payload = _decode_payload(dispatch_env)
            assert dispatch_env.cognitive_trace_id == trace_id
            assert dispatch_env.session_id == session_id
            assert dispatch_payload["tier"] == "HIGH"
            assert dispatch_payload["plan"] is True
            assert dispatch_payload["complexity"] == "HIGH"
            assert dispatch_payload["trace_id"] == trace_id
            assert dispatch_payload["intents"][0]["action"] == capability

            complete_env = recorder.by_topic(TOPIC_TASK_COMPLETE)[0]
            complete_payload = _decode_payload(complete_env)
            assert complete_env.cognitive_trace_id == trace_id
            assert complete_env.session_id == session_id
            assert complete_payload["source"] == "orchestrator"
            assert complete_payload["process_result"] in {"COMPLETED", "DEGRADED"}
            assert complete_payload["trace_id"] == trace_id
            assert complete_payload["session_id"] == session_id

            completed_payload = _decode_payload(recorder.by_topic(TOPIC_TURN_COMPLETED)[0])
            assert completed_payload["session_id"] == session.concierge._ledger.session_id
            assert completed_payload["cognitive_trace_id"] == trace_id
            assert completed_payload["user_message"] == user_text
            assert completed_payload["assistant_response"] == ""

            fired_labels = [rule.label for rule in scripted.rules if rule.fired]
            assert "front-dispatch-high" in fired_labels
            assert "planner-sketch" in fired_labels
            assert "planner-expand" in fired_labels
            assert "planner-validate" in fired_labels

            captured = transport.drain()
            assert [call.tool_name for call in captured] == [capability]
            assert captured[0].arguments == {"intent": "family planning prompt", "top_k": 1}
            assert captured[0].trace_id == trace_id
        finally:
            recorder.stop()
    finally:
        await _cleanup_service(svc, baseline_tasks)
