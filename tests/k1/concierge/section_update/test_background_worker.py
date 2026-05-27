"""Tests for the M4 section-update background worker."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import SubscriptionHandle
from k1.concierge.bus.builders import build_turn_completed
from k1.concierge.bus.topics import (
    TOPIC_SECTION_UPDATE_COMPLETED,
    TOPIC_SECTION_UPDATE_REQUESTED,
    TOPIC_TURN_COMPLETED,
)
from k1.concierge.section_update.classifier import DeterministicSectionUpdateClassifier
from k1.concierge.section_update.types import (
    ApplyTiming,
    CommitClass,
    SectionMutation,
    SectionUpdatePlan,
)
from k1.concierge.section_update.worker import (
    SectionUpdateBackgroundWorker,
    SectionUpdateWorkerConfig,
)


class _MalformedClassifier:
    async def classify(self, _input_data: Any) -> dict[str, str]:
        return {"not": "a section update plan"}


@dataclass
class _FakeBus:
    published: list[Envelope] = field(default_factory=list)
    subscriptions: dict[str, tuple[str, Any]] = field(default_factory=dict)
    unsubscribed: list[SubscriptionHandle] = field(default_factory=list)

    def publish(self, envelope: Envelope) -> None:
        self.published.append(envelope)
        for pattern, handler in list(self.subscriptions.values()):
            if pattern == envelope.topic:
                handler(envelope)

    def subscribe(self, pattern: str, handler: Any) -> SubscriptionHandle:
        handle = SubscriptionHandle(subscription_id=f"sub-{len(self.subscriptions) + 1}", pattern=pattern)
        self.subscriptions[handle.subscription_id] = (pattern, handler)
        return handle

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        self.unsubscribed.append(handle)
        return self.subscriptions.pop(handle.subscription_id, None) is not None


def _payload(envelope: Envelope) -> dict[str, Any]:
    return json.loads(envelope.payload.decode("utf-8"))


def _turn(turn_id: str = "turn-1") -> Envelope:
    return build_turn_completed(
        {
            "session_id": "session-1",
            "turn_id": turn_id,
            "turn_number": 1,
            "user_message": "Remember that Eli likes soccer.",
            "assistant_response": "Got it.",
            "prompt_mode": "front_react",
            "fsm_state": "responded",
        }
    )


def test_worker_start_stop_subscribes_and_unsubscribes() -> None:
    bus = _FakeBus()
    worker = SectionUpdateBackgroundWorker(
        session_id="session-1",
        bus=bus,
        state_manager=MagicMock(),
        writer_port=None,
        classifier=DeterministicSectionUpdateClassifier(),
        config=SectionUpdateWorkerConfig(mode="shadow"),
    )

    worker.start()
    assert len(bus.subscriptions) == 1
    assert next(iter(bus.subscriptions.values()))[0] == TOPIC_TURN_COMPLETED

    worker.stop()
    assert bus.subscriptions == {}
    assert len(bus.unsubscribed) == 1
    assert worker.is_running is False


def test_shadow_worker_publishes_diagnostics_without_writer_call() -> None:
    bus = _FakeBus()
    writer = MagicMock()
    worker = SectionUpdateBackgroundWorker(
        session_id="session-1",
        bus=bus,
        state_manager=None,
        writer_port=writer,
        classifier=DeterministicSectionUpdateClassifier(),
        config=SectionUpdateWorkerConfig(mode="shadow", timeout_ms=1000),
    )
    worker.start()
    try:
        bus.publish(_turn())
        assert worker.drain(timeout_s=2.0) is True
    finally:
        worker.stop()

    topics = [item.topic for item in bus.published]
    assert TOPIC_SECTION_UPDATE_REQUESTED in topics
    assert TOPIC_SECTION_UPDATE_COMPLETED in topics
    completed = [_payload(item) for item in bus.published if item.topic == TOPIC_SECTION_UPDATE_COMPLETED]
    assert completed[-1]["status"] == "shadow_noop"
    writer.batch_mutations.assert_not_called()


def test_background_apply_calls_writer_through_apply_boundary() -> None:
    bus = _FakeBus()
    writer = MagicMock()
    writer.batch_mutations.return_value = type(
        "WriterResult",
        (),
        {
            "responses": [],
            "batch_id": "batch-1",
            "total_requests": 1,
            "applied_count": 1,
            "rejected_count": 0,
            "failed_count": 0,
            "cancelled_count": 0,
            "total_bytes_delta": 12,
            "stopped_early": False,
        },
    )()
    plan = SectionUpdatePlan(
        plan_id="plan-1",
        turn_id="turn-1",
        session_id="session-1",
        snapshot_version="",
        snapshot_source_epoch="",
        classifier_version="test-classifier",
        apply_timing=ApplyTiming.ASYNC_AFTER_RESPONSE,
        mutations=[
            SectionMutation(
                section="beliefs_active",
                operation="add_fact",
                data={"text": "Eli likes soccer."},
                confidence=0.95,
                reason="durable user preference",
                commit_class=CommitClass.NEXT_TURN_CONTINUITY,
            )
        ],
    )
    worker = SectionUpdateBackgroundWorker(
        session_id="session-1",
        bus=bus,
        state_manager=None,
        writer_port=writer,
        classifier=DeterministicSectionUpdateClassifier({"turn-1": plan}),
        config=SectionUpdateWorkerConfig(
            mode="background_apply",
            timeout_ms=1000,
            provider_id="vertex",
            model_id="gemini-2.5-flash-lite",
        ),
    )
    worker.start()
    try:
        bus.publish(_turn())
        assert worker.drain(timeout_s=2.0) is True
    finally:
        worker.stop()

    writer.batch_mutations.assert_called_once()
    completed = [_payload(item) for item in bus.published if item.topic == TOPIC_SECTION_UPDATE_COMPLETED]
    assert completed[-1]["status"] == "applied"
    assert completed[-1]["provider_id"] == "vertex"
    assert completed[-1]["model_id"] == "gemini-2.5-flash-lite"
    assert completed[-1]["writer"]["applied_count"] == 1


def test_background_apply_rejects_invalid_schema_without_writer_call() -> None:
    bus = _FakeBus()
    writer = MagicMock()
    worker = SectionUpdateBackgroundWorker(
        session_id="session-1",
        bus=bus,
        state_manager=None,
        writer_port=writer,
        classifier=_MalformedClassifier(),
        config=SectionUpdateWorkerConfig(mode="background_apply", timeout_ms=1000),
    )
    worker.start()
    try:
        bus.publish(_turn())
        assert worker.drain(timeout_s=2.0) is True
    finally:
        worker.stop()

    writer.batch_mutations.assert_not_called()
    completed = [_payload(item) for item in bus.published if item.topic == TOPIC_SECTION_UPDATE_COMPLETED]
    assert completed[-1]["status"] == "rejected"
    assert completed[-1]["diagnostics"][0]["code"] == "invalid_schema"


def test_queue_full_publishes_fail_closed_diagnostics_without_writer_call() -> None:
    bus = _FakeBus()
    writer = MagicMock()
    worker = SectionUpdateBackgroundWorker(
        session_id="session-1",
        bus=bus,
        state_manager=None,
        writer_port=writer,
        classifier=DeterministicSectionUpdateClassifier(),
        config=SectionUpdateWorkerConfig(mode="shadow", queue_max=1),
    )
    worker._queue.put_nowait(None)

    worker._on_turn_completed(_turn("overflow-turn"))

    writer.batch_mutations.assert_not_called()
    completed = [_payload(item) for item in bus.published if item.topic == TOPIC_SECTION_UPDATE_COMPLETED]
    assert completed[-1]["turn_id"] == "overflow-turn"
    assert completed[-1]["status"] == "degraded_noop"
    assert completed[-1]["diagnostics"][0]["code"] == "queue_full"
