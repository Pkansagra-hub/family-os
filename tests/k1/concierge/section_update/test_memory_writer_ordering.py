"""M4.I3 MemoryWriter ordering against section-update turn completion."""

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
from k1.memory_writer.pipeline.session_batch_dispatcher import SessionBatchDispatcher
from k1.memory_writer.pipeline.turn_dispatcher import TurnDispatcher
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
        return {"session_id": "session-1", "last_mutation_ms": 11, "sections": {}}

    def get_section(self, _name: str):
        return None


class _Classifier:
    async def classify(self, input_data: SectionUpdateInput) -> SectionUpdatePlan:
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


def _payload(envelope: Envelope) -> dict:
    return json.loads(envelope.payload.decode())


def _captured_by_topic(bus, topic: str) -> list[Envelope]:
    return [item for item in bus.captured if item.topic == topic]


def test_memory_writer_consumes_after_sync_overlay_section_update_apply() -> None:
    assert SessionBatchDispatcher.TOPIC == TOPIC_TURN_COMPLETED
    ctrl, bus = _controller()
    writer = _Writer()
    ctrl._ss = _SessionState(writer)
    ctrl._turn_number = 9
    ctrl._current_turn_user_text = "I like quiet rooms."
    ctrl._current_turn_assistant_response = "done"
    ctrl.set_section_update_classifier(
        _Classifier(),
        mode="sync_overlay",
        timeout_ms=100,
        classifier_version="classifier-v1",
    )

    ctrl._finalize_turn(_final_response_env())

    topics = [item.topic for item in bus.captured]
    assert topics[:3] == [
        TOPIC_SECTION_UPDATE_REQUESTED,
        TOPIC_SECTION_UPDATE_COMPLETED,
        TOPIC_TURN_COMPLETED,
    ]
    assert len(writer.calls) == 1
    typed_payload = TurnDispatcher._deserialize(
        _payload(_captured_by_topic(bus, TOPIC_TURN_COMPLETED)[0])
    )
    assert typed_payload.section_update["status"] == SectionUpdateCompletionStatus.APPLIED.value
    assert typed_payload.section_update["mutation_count"] == 1


def test_worker_owned_modes_memory_writer_ordering_remains_unchanged() -> None:
    for mode in ("shadow", "background_apply", "degraded_noop"):
        ctrl, bus = _controller()
        writer = _Writer()
        ctrl._ss = _SessionState(writer)
        ctrl._turn_number = 1
        ctrl._current_turn_assistant_response = "done"
        ctrl.set_section_update_classifier(_Classifier(), mode=mode, timeout_ms=100)

        ctrl._finalize_turn(_final_response_env())

        assert writer.calls == []
        typed_payload = TurnDispatcher._deserialize(
            _payload(_captured_by_topic(bus, TOPIC_TURN_COMPLETED)[0])
        )
        assert typed_payload.section_update is None
        assert [item.topic for item in bus.captured] == [TOPIC_TURN_COMPLETED]


def test_classifier_timeout_does_not_block_memory_writer_consumption() -> None:
    ctrl, bus = _controller()
    writer = _Writer()
    ctrl._ss = _SessionState(writer)
    ctrl._turn_number = 2
    ctrl._current_turn_assistant_response = "done"
    ctrl.set_section_update_classifier(_SlowClassifier(), mode="sync_overlay", timeout_ms=1)

    ctrl._finalize_turn(_final_response_env())

    assert len(writer.calls) == 0
    typed_payload = TurnDispatcher._deserialize(
        _payload(_captured_by_topic(bus, TOPIC_TURN_COMPLETED)[0])
    )
    assert typed_payload.section_update["status"] == SectionUpdateCompletionStatus.TIMED_OUT.value
    assert any(item.topic == TOPIC_TURN_COMPLETED for item in bus.captured)
