"""
tests.poc.test_m01_builders -- Envelope builder validation.

Validates all 28 builder functions:
    - Each builder produces an Envelope with the correct topic
    - Priority matches V2 Section 3 table
    - Payload is valid JSON bytes
    - parent_id propagates correctly
    - PayloadFormat is JSON
    - BUILDERS registry has 28 entries (one per topic)
"""

from __future__ import annotations

import json

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.bus.builders import (
    BUILDERS,
    build_affect_update,
    build_artifact_created,
    build_clarification_out,
    build_clarification_request,
    build_clarification_response,
    build_dag_completed,
    build_final_response,
    build_findings_ready,
    build_hil_request,
    build_hil_response,
    build_orchestration_delta,
    build_plan_ready,
    build_proactive_fill,
    build_state_updated,
    build_task_accepted,
    build_task_cancel,
    build_task_complete,
    build_task_dispatch,
    build_task_failed,
    build_task_resume,
    build_task_suspended,
    build_tool_completed,
    build_tool_started,
    build_turn_completed,
    build_turn_started,
    build_user_input,
    build_weave_batch,
)
from k1.concierge.bus.topics import ALL_TOPICS


class TestBuildersRegistry:
    """Verify BUILDERS dict covers all topics."""

    def test_registry_count(self) -> None:
        assert len(BUILDERS) == 47

    def test_registry_keys_match_all_topics(self) -> None:
        assert set(BUILDERS.keys()) == ALL_TOPICS

    def test_all_builders_callable(self) -> None:
        for topic, builder in BUILDERS.items():
            assert callable(builder), f"Builder for {topic} is not callable"


class TestBuilderOutput:
    """Verify each builder produces a well-formed Envelope."""

    _SAMPLE_PAYLOAD = {"key": "value", "number": 42}

    @pytest.mark.parametrize(
        "builder_fn,expected_topic,expected_priority",
        [
            # URGENT topics
            (build_user_input, "k1.session.user.input.v1", Priority.URGENT),
            (build_final_response, "k1.response.final.v1", Priority.URGENT),
            (build_clarification_out, "k1.response.clarification.v1", Priority.URGENT),
            (build_task_cancel, "k1.orchestration.task.cancel.v1", Priority.URGENT),
            (build_hil_response, "k1.hil.response.v1", Priority.URGENT),
            # INTERACTIVE topics
            (build_task_dispatch, "k1.orchestration.task.dispatch.v1", Priority.INTERACTIVE),
            (build_task_complete, "k1.orchestration.task.complete.v1", Priority.INTERACTIVE),
            (build_task_failed, "k1.orchestration.task.failed.v1", Priority.INTERACTIVE),
            (build_task_suspended, "k1.orchestration.task.suspended.v1", Priority.INTERACTIVE),
            (build_task_resume, "k1.orchestration.task.resume.v1", Priority.INTERACTIVE),
            (build_task_accepted, "k1.orchestration.task.accepted.v1", Priority.INTERACTIVE),
            (build_findings_ready, "k1.orchestration.findings.ready.v1", Priority.INTERACTIVE),
            (
                build_clarification_request,
                "k1.orchestration.clarification.request.v1",
                Priority.INTERACTIVE,
            ),
            (
                build_clarification_response,
                "k1.orchestration.clarification.response.v1",
                Priority.INTERACTIVE,
            ),
            (build_orchestration_delta, "k1.orchestration.delta.v1", Priority.INTERACTIVE),
            (build_dag_completed, "k1.orchestration.dag.completed.v1", Priority.INTERACTIVE),
            (build_tool_started, "k1.tool.started.v1", Priority.INTERACTIVE),
            (build_tool_completed, "k1.tool.completed.v1", Priority.INTERACTIVE),
            (build_artifact_created, "k1.session.artifact.created.v1", Priority.INTERACTIVE),
            (build_turn_started, "k1.session.turn.started.v1", Priority.INTERACTIVE),
            (build_turn_completed, "k1.session.turn.completed.v1", Priority.INTERACTIVE),
            (build_hil_request, "k1.hil.request.v1", Priority.INTERACTIVE),
            (build_plan_ready, "k1.planner.plan.ready.v1", Priority.INTERACTIVE),
            (build_weave_batch, "k1.internal.weave.batch.v1", Priority.INTERACTIVE),
            # BACKGROUND topics
            (build_state_updated, "k1.session.state.updated.v1", Priority.BACKGROUND),
            (build_affect_update, "k1.affect.update.v1", Priority.BACKGROUND),
            (build_proactive_fill, "k1.proactive.fill.v1", Priority.BACKGROUND),
        ],
    )
    def test_builder_topic_and_priority(
        self, builder_fn, expected_topic: str, expected_priority: Priority
    ) -> None:
        env = builder_fn(self._SAMPLE_PAYLOAD, parent_id=99)
        assert env.topic == expected_topic
        assert env.priority == expected_priority

    def test_payload_is_json(self) -> None:
        env = build_user_input({"text": "hello"})
        data = json.loads(env.payload)
        assert data["text"] == "hello"
        # M1 E1.4.5: Auto-enriched fields are also present
        assert "event_id" in data
        assert "ts_utc" in data
        assert "payload_schema_version" in data

    def test_payload_format_is_json(self) -> None:
        env = build_user_input({"text": "hello"})
        assert env.payload_format == PayloadFormat.JSON

    def test_parent_id_propagates(self) -> None:
        env = build_task_dispatch({"task_id": "t1"}, parent_id=42)
        assert env.parent_id == 42

    def test_parent_id_default_zero(self) -> None:
        env = build_user_input({"text": "hello"})
        assert env.parent_id == 0

    def test_envelope_is_frozen(self) -> None:
        env = build_user_input({"text": "hello"})
        assert isinstance(env, Envelope)
        with pytest.raises(AttributeError):
            env.topic = "changed"  # type: ignore[misc]
