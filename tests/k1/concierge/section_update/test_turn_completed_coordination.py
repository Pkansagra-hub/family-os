"""M2.I4 controller coordination for section-update turn boundary."""

from __future__ import annotations

import asyncio
import json

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.bus.setup import create_poc_bus, create_poc_router
from k1.concierge.bus.topics import (
    TOPIC_FINAL_RESPONSE,
    TOPIC_SECTION_UPDATE_COMPLETED,
    TOPIC_SECTION_UPDATE_REQUESTED,
    TOPIC_TURN_COMPLETED,
)
from k1.concierge.fsm.controller import ConciergeController
from k1.concierge.section_update.events import SectionUpdateCompletionStatus
from k1.concierge.section_update.types import (
    SectionMutation,
    SectionUpdateInput,
    SectionUpdatePlan,
)
from k1.sessionstate.ports.writer import BatchResult, MutationResponse


class _Writer:
    def __init__(self) -> None:
        self.calls = []

    def batch_mutations(self, batch):
        self.calls.append(batch)
        responses = [
            MutationResponse.approved(
                request_id=request.request_id,
                section=request.section,
                operation=request.operation,
                new_size_bytes=128,
                bytes_delta=16,
                available_bytes=4096,
            )
            for request in batch.requests
        ]
        return BatchResult.from_responses(batch.batch_id, responses)


class _SessionState:
    def __init__(self, writer: _Writer) -> None:
        self._writer_port = writer

    def get_snapshot(self):
        return {
            "session_id": "session-1",
            "last_mutation_ms": 123,
            "sections": {},
        }

    def get_section(self, _name: str):
        return None


class _Classifier:
    def __init__(self) -> None:
        self.calls = 0

    async def classify(self, input_data: SectionUpdateInput) -> SectionUpdatePlan:
        self.calls += 1
        return SectionUpdatePlan(
            plan_id="plan-1",
            turn_id=input_data.turn_id,
            session_id=input_data.session_id,
            snapshot_version=input_data.session_snapshot["snapshot_version"],
            snapshot_source_epoch=input_data.session_snapshot["snapshot_source_epoch"],
            classifier_version="classifier-v1",
            cognitive_trace_id=input_data.cognitive_trace_id,
            mutations=[
                SectionMutation(
                    section="beliefs_active",
                    operation="add_fact",
                    data={"subject": "user", "predicate": "prefers", "obj": "quiet"},
                    confidence=0.9,
                    reason="User stated a durable preference.",
                )
            ],
        )


class _SlowClassifier:
    async def classify(self, input_data: SectionUpdateInput) -> SectionUpdatePlan:
        await asyncio.sleep(0.2)
        return SectionUpdatePlan.noop(
            plan_id="slow-plan",
            turn_id=input_data.turn_id,
            session_id=input_data.session_id,
        )


class _MalformedClassifier:
    async def classify(self, _input_data: SectionUpdateInput):
        return {"not": "a valid section update plan"}


def _controller() -> tuple[ConciergeController, object]:
    bus = create_poc_bus(capture=True)
    router = create_poc_router()
    return ConciergeController(bus=bus, router=router), bus


def _final_response_env() -> Envelope:
    return Envelope(
        topic=TOPIC_FINAL_RESPONSE,
        payload=json.dumps({"text": "done"}).encode(),
        payload_format=PayloadFormat.JSON,
        priority=Priority.INTERACTIVE,
        envelope_id=100,
        session_id="session-1",
        cognitive_trace_id="trace-1",
    )


def _captured_topics(bus) -> list[str]:
    return [item.topic for item in bus.captured]


def test_active_section_update_applies_before_turn_completed() -> None:
    ctrl, bus = _controller()
    writer = _Writer()
    ctrl._ss = _SessionState(writer)
    ctrl._turn_number = 7
    ctrl._current_turn_user_text = "I like quiet rooms."
    ctrl._current_turn_assistant_response = "done"
    ctrl.set_section_update_classifier(
        _Classifier(),
        mode="active",
        timeout_ms=100,
        classifier_version="classifier-v1",
    )

    ctrl._finalize_turn(_final_response_env())

    topics = _captured_topics(bus)
    assert topics[:3] == [
        TOPIC_SECTION_UPDATE_REQUESTED,
        TOPIC_SECTION_UPDATE_COMPLETED,
        TOPIC_TURN_COMPLETED,
    ]
    assert len(writer.calls) == 1
    completed = bus.captured[1]
    payload = json.loads(completed.payload.decode())
    assert payload["status"] == SectionUpdateCompletionStatus.APPLIED.value
    assert payload["mutation_count"] == 1
    assert payload["writer"]["applied_count"] == 1


def test_disabled_and_shadow_do_not_gate_turn_completed() -> None:
    for mode in ("disabled", "shadow"):
        ctrl, bus = _controller()
        writer = _Writer()
        ctrl._ss = _SessionState(writer)
        ctrl._turn_number = 1
        ctrl._current_turn_assistant_response = "done"
        ctrl.set_section_update_classifier(_Classifier(), mode=mode, timeout_ms=100)

        ctrl._finalize_turn(_final_response_env())

        topics = _captured_topics(bus)
        assert TOPIC_SECTION_UPDATE_REQUESTED not in topics
        assert TOPIC_SECTION_UPDATE_COMPLETED not in topics
        assert topics[0] == TOPIC_TURN_COMPLETED
        assert writer.calls == []


def test_active_timeout_degrades_before_turn_completed_without_writer_call() -> None:
    ctrl, bus = _controller()
    writer = _Writer()
    ctrl._ss = _SessionState(writer)
    ctrl._turn_number = 2
    ctrl._current_turn_assistant_response = "done"
    ctrl.set_section_update_classifier(_SlowClassifier(), mode="active", timeout_ms=1)

    ctrl._finalize_turn(_final_response_env())

    topics = _captured_topics(bus)
    assert topics[:3] == [
        TOPIC_SECTION_UPDATE_REQUESTED,
        TOPIC_SECTION_UPDATE_COMPLETED,
        TOPIC_TURN_COMPLETED,
    ]
    assert writer.calls == []
    completed = json.loads(bus.captured[1].payload.decode())
    assert completed["status"] == SectionUpdateCompletionStatus.TIMED_OUT.value
    assert completed["diagnostics"][0]["code"] == "classifier_timeout"


def test_active_boundary_does_not_retry_same_turn() -> None:
    ctrl, bus = _controller()
    writer = _Writer()
    classifier = _Classifier()
    ctrl._ss = _SessionState(writer)
    ctrl._turn_number = 3
    ctrl._current_turn_assistant_response = "done"
    ctrl.set_section_update_classifier(
        classifier,
        mode="active",
        timeout_ms=100,
        classifier_version="classifier-v1",
    )

    env = _final_response_env()
    ctrl._finalize_turn(env)
    ctrl._finalize_turn(env)

    topics = _captured_topics(bus)
    assert topics.count(TOPIC_SECTION_UPDATE_REQUESTED) == 1
    assert topics.count(TOPIC_SECTION_UPDATE_COMPLETED) == 1
    assert classifier.calls == 1
    assert len(writer.calls) == 1


def test_active_boundary_degrades_malformed_plan_before_turn_completed() -> None:
    ctrl, bus = _controller()
    writer = _Writer()
    ctrl._ss = _SessionState(writer)
    ctrl._turn_number = 4
    ctrl._current_turn_assistant_response = "done"
    ctrl.set_section_update_classifier(_MalformedClassifier(), mode="active", timeout_ms=100)

    ctrl._finalize_turn(_final_response_env())

    topics = _captured_topics(bus)
    assert topics[:3] == [
        TOPIC_SECTION_UPDATE_REQUESTED,
        TOPIC_SECTION_UPDATE_COMPLETED,
        TOPIC_TURN_COMPLETED,
    ]
    assert writer.calls == []
    completed = json.loads(bus.captured[1].payload.decode())
    assert completed["status"] == SectionUpdateCompletionStatus.DEGRADED_NOOP.value
    assert completed["diagnostics"][0]["code"] == "active_boundary_failed"


def test_active_boundary_closes_before_front_lock_drain() -> None:
    ctrl, _bus = _controller()
    order: list[str] = []
    ctrl._section_update_mode = "active"
    ctrl._section_update_classifier = object()
    ctrl._run_active_section_update_boundary = lambda _env: order.append("section_update")
    ctrl._emit_turn_completed = lambda _env: order.append("turn_completed")
    ctrl._drain_front_lock_queue = lambda: order.append("drain")

    ctrl._finalize_turn(_final_response_env())

    assert order == ["section_update", "turn_completed", "drain"]
