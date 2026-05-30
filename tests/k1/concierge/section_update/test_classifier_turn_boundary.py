"""M2.I2 section-update request/completion boundary."""

from __future__ import annotations

import json

import pytest

from k1.concierge.bus.builders import (
    BUILDERS,
    build_section_update_completed,
    build_section_update_requested,
    get_builder_registry,
)
from k1.concierge.bus.topics import (
    ALL_TOPICS,
    TOPIC_SECTION_UPDATE_COMPLETED,
    TOPIC_SECTION_UPDATE_REQUESTED,
)
from k1.concierge.section_update.classifier import DeterministicSectionUpdateClassifier
from k1.concierge.section_update.events import (
    SectionUpdateCompletionStatus,
    build_section_update_completed_payload,
    build_section_update_requested_payload,
)
from k1.concierge.section_update.lifecycle import run_shadow_section_update
from k1.concierge.section_update.types import (
    ApplyTiming,
    SectionMutation,
    SectionUpdateInput,
    SectionUpdatePlan,
)


def _input() -> SectionUpdateInput:
    return SectionUpdateInput(
        turn_id="session-1:7",
        session_id="session-1",
        cognitive_trace_id="trace-1",
        prompt_mode="STANDARD",
        fsm_state="LISTENING",
        bus_topic="k1.response.final.v1",
        user_turn={"text": "I prefer quiet rooms"},
        assistant_turn={"final_text": "Got it."},
        prompt_context={"system_prompt_summary": {"sha256": "abc", "chars": 123}},
        session_snapshot={
            "snapshot_version": "snap-1",
            "snapshot_source_epoch": "epoch-1",
        },
    )


def _plan() -> SectionUpdatePlan:
    return SectionUpdatePlan(
        plan_id="plan-1",
        turn_id="session-1:7",
        session_id="session-1",
        snapshot_version="snap-1",
        classifier_version="fixture-classifier",
        apply_timing=ApplyTiming.ASYNC_AFTER_RESPONSE,
        mutations=[
            SectionMutation(
                section="beliefs_active",
                operation="add_fact",
                data={"subject": "user", "predicate": "prefers", "obj": "quiet rooms"},
                confidence=0.9,
                reason="User stated a durable preference.",
                commit_class="next_turn_continuity",
            )
        ],
        cognitive_trace_id="trace-1",
    )


class _Bus:
    def __init__(self) -> None:
        self.published = []

    def publish(self, envelope) -> None:
        self.published.append(envelope)


class _FailingClassifier:
    async def classify(self, _input_data):
        raise RuntimeError("provider unavailable")


def _payload(envelope) -> dict:
    return json.loads(envelope.payload)


def test_section_update_topics_and_builders_are_registered() -> None:
    assert TOPIC_SECTION_UPDATE_REQUESTED in ALL_TOPICS
    assert TOPIC_SECTION_UPDATE_COMPLETED in ALL_TOPICS
    assert TOPIC_SECTION_UPDATE_REQUESTED in BUILDERS
    assert TOPIC_SECTION_UPDATE_COMPLETED in BUILDERS
    assert build_section_update_requested({"turn_id": "t"}).topic == TOPIC_SECTION_UPDATE_REQUESTED
    assert build_section_update_completed({"turn_id": "t"}).topic == TOPIC_SECTION_UPDATE_COMPLETED

    registry = get_builder_registry()
    assert registry[TOPIC_SECTION_UPDATE_REQUESTED].builder_fn is build_section_update_requested
    assert registry[TOPIC_SECTION_UPDATE_COMPLETED].builder_fn is build_section_update_completed


def test_request_payload_has_boundary_metadata_without_prompt_dumps() -> None:
    payload = build_section_update_requested_payload(
        _input(),
        mode="shadow",
        classifier_version="classifier-v1",
    )

    assert payload["turn_id"] == "session-1:7"
    assert payload["snapshot_version"] == "snap-1"
    assert payload["snapshot_source_epoch"] == "epoch-1"
    assert payload["mode"] == "shadow"
    assert payload["plan_idempotency_key"] == "session-1:session-1:7:snap-1:classifier-v1"
    serialized = json.dumps(payload)
    assert "system_prompt" not in serialized
    assert "quiet rooms" not in serialized


@pytest.mark.asyncio
async def test_shadow_lifecycle_publishes_request_and_completion_without_writer() -> None:
    bus = _Bus()
    classifier = DeterministicSectionUpdateClassifier({"session-1:7": _plan()})

    result = await run_shadow_section_update(
        input_data=_input(),
        classifier=classifier,
        bus=bus,
        parent_id=99,
        classifier_version="fixture-classifier",
    )

    assert result.status == SectionUpdateCompletionStatus.SHADOW_PLAN
    assert [event.topic for event in bus.published] == [
        TOPIC_SECTION_UPDATE_REQUESTED,
        TOPIC_SECTION_UPDATE_COMPLETED,
    ]
    assert all(event.parent_id == 99 for event in bus.published)
    completed_payload = _payload(bus.published[-1])
    assert completed_payload["status"] == "shadow_plan"
    assert completed_payload["plan_id"] == "plan-1"
    assert completed_payload["mutation_count"] == 1
    assert "data" not in completed_payload


@pytest.mark.asyncio
async def test_shadow_provider_failure_degrades_to_completion_diagnostic() -> None:
    bus = _Bus()

    result = await run_shadow_section_update(
        input_data=_input(),
        classifier=_FailingClassifier(),
        bus=bus,
        parent_id=100,
    )

    assert result.status == SectionUpdateCompletionStatus.PROVIDER_FAILED
    assert [event.topic for event in bus.published] == [
        TOPIC_SECTION_UPDATE_REQUESTED,
        TOPIC_SECTION_UPDATE_COMPLETED,
    ]
    completed_payload = _payload(bus.published[-1])
    assert completed_payload["status"] == "provider_failed"
    assert completed_payload["diagnostics"][0]["code"] == "provider_failed"


def test_completed_payload_summarizes_plan_without_mutation_bodies() -> None:
    payload = build_section_update_completed_payload(
        _input(),
        status=SectionUpdateCompletionStatus.SHADOW_PLAN,
        mode="shadow",
        classifier_version="fixture-classifier",
        plan=_plan(),
        elapsed_ms=12,
    )

    assert payload["status"] == "shadow_plan"
    assert payload["mutation_count"] == 1
    assert payload["apply_timing"] == "async_after_response"
    assert payload["elapsed_ms"] == 12
    serialized = json.dumps(payload)
    assert "quiet rooms" not in serialized
    assert "add_fact" not in serialized
