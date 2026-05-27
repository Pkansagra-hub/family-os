"""M1.I5 deterministic stub and classifier output schema."""

from __future__ import annotations

import pytest

from k1.concierge.llm.types import ToolSchema
from k1.concierge.section_update.classifier import (
    DeterministicSectionUpdateClassifier,
    ISectionUpdateClassifier,
)
from k1.concierge.section_update.prompt import (
    SECTION_UPDATE_BATCH_TOOL_NAME,
    build_section_update_system_prompt,
    build_section_update_tool_schema,
)
from k1.concierge.section_update.types import (
    ApplyTiming,
    ClassifierMode,
    SectionMutation,
    SectionUpdateInput,
    SectionUpdatePlan,
)


def _input(mode: str = ClassifierMode.OFFLINE_STUB.value) -> SectionUpdateInput:
    return SectionUpdateInput(
        turn_id="turn-1",
        session_id="session-1",
        cognitive_trace_id="trace-1",
        constraints={"classifier_mode": mode},
    )


def _fixture_plan() -> SectionUpdatePlan:
    return SectionUpdatePlan(
        plan_id="fixture-plan",
        turn_id="turn-1",
        session_id="session-1",
        apply_timing=ApplyTiming.ASYNC_AFTER_RESPONSE,
        mutations=[
            SectionMutation(
                section="beliefs_active",
                operation="add_fact",
                data={"subject": "user", "predicate": "likes", "obj": "tea"},
                confidence=0.8,
                reason="User stated a preference.",
                commit_class="next_turn_continuity",
            )
        ],
    )


def test_interface_is_abstract() -> None:
    with pytest.raises(TypeError):
        ISectionUpdateClassifier()  # type: ignore[abstract]


def test_stub_satisfies_interface() -> None:
    assert isinstance(DeterministicSectionUpdateClassifier(), ISectionUpdateClassifier)


@pytest.mark.asyncio
async def test_stub_returns_noop_without_fixture() -> None:
    plan = await DeterministicSectionUpdateClassifier().classify(_input())

    assert plan.is_noop is True
    assert plan.classifier_version == "offline_stub"
    assert plan.cognitive_trace_id == "trace-1"


@pytest.mark.asyncio
async def test_stub_returns_fixture_plan_for_turn() -> None:
    fixture = _fixture_plan()
    plan = await DeterministicSectionUpdateClassifier({"turn-1": fixture}).classify(_input())

    assert plan is fixture
    assert len(plan.mutations) == 1


@pytest.mark.asyncio
async def test_degraded_noop_mode_overrides_fixture() -> None:
    fixture = _fixture_plan()
    plan = await DeterministicSectionUpdateClassifier({"turn-1": fixture}).classify(
        _input(ClassifierMode.DEGRADED_NOOP.value)
    )

    assert plan.is_noop is True
    assert plan.plan_id == "offline-stub:turn-1"
    assert plan.rejected_candidates[0].reason == "degraded_noop mode"


def test_batch_tool_schema_is_not_front_tool_schema() -> None:
    schema = build_section_update_tool_schema()

    assert isinstance(schema, ToolSchema)
    assert schema.name == SECTION_UPDATE_BATCH_TOOL_NAME
    assert schema.actor == "section_update_classifier"
    assert schema.side_effects is False
    assert schema.parameters["properties"]["mutations"]["items"]["oneOf"]


def test_batch_tool_schema_scopes_operation_enum_by_section() -> None:
    schema = build_section_update_tool_schema()
    items = schema.parameters["properties"]["mutations"]["items"]["oneOf"]
    scoreboard_operations = {
        item["properties"]["operation"]["const"]
        for item in items
        if item["properties"]["section"]["const"] == "scoreboard"
    }

    assert "push_question" in scoreboard_operations
    assert "answer_question" not in scoreboard_operations


def test_batch_tool_schema_constrains_writer_payload_shapes() -> None:
    schema = build_section_update_tool_schema()
    items = schema.parameters["properties"]["mutations"]["items"]["oneOf"]

    def schema_for(section: str, operation: str) -> dict[str, object]:
        return next(
            item
            for item in items
            if item["properties"]["section"]["const"] == section
            and item["properties"]["operation"]["const"] == operation
        )

    add_fact_schema = schema_for("beliefs_active", "add_fact")
    add_referent_schema = schema_for("scoreboard", "add_referent")
    push_question_schema = schema_for("scoreboard", "push_question")
    clarification_request_schema = schema_for("clarifications", "request")
    affective_update_schema = schema_for("affective_now", "update")
    resolve_thread_schema = schema_for("narrative_active", "resolve_thread")

    add_fact_data = add_fact_schema["properties"]["data"]
    assert add_fact_data["required"] == ["subject", "predicate", "obj", "confidence", "source"]
    assert "id" not in add_fact_data["properties"]
    assert add_fact_data["additionalProperties"] is False

    add_referent_data = add_referent_schema["properties"]["data"]
    assert add_referent_data["required"] == [
        "text",
        "entity_id",
        "entity_type",
        "salience",
    ]
    assert add_referent_data["additionalProperties"] is False

    push_question_data = push_question_schema["properties"]["data"]
    assert push_question_data["required"] == ["text", "asked_by", "priority"]
    assert push_question_data["additionalProperties"] is False

    clarification_request_data = clarification_request_schema["properties"]["data"]
    assert clarification_request_data["required"] == [
        "agent_id",
        "question",
        "priority",
        "related_entity",
        "related_intent",
        "timeout_ms",
        "blocking",
    ]
    assert clarification_request_data["additionalProperties"] is False

    affective_update_data = affective_update_schema["properties"]["data"]
    assert affective_update_data["required"] == [
        "emotion",
        "intensity",
        "valence",
        "arousal",
        "dominance",
        "confidence",
        "source",
    ]
    assert affective_update_data["additionalProperties"] is False
    assert resolve_thread_schema["properties"]["data"]["required"] == ["thread_id"]


def test_system_prompt_teaches_kernel_role_split_and_writer_contract() -> None:
    prompt = build_section_update_system_prompt()

    assert "post-turn cognitive SessionState mutation planner" in prompt
    assert "SYSTEM ROLE SPLIT" in prompt
    assert "SESSIONSTATE MENTAL MODEL" in prompt
    assert "bounded central working memory" in prompt
    assert "small, section-owned cognitive deltas" in prompt
    assert "Front owns conversation continuity" in prompt
    assert "FSM/runtime owns control" in prompt
    assert "Legacy Front tool names" in prompt
    assert "Raw legacy Front session write payloads stay out of the classifier input" in prompt
    assert "writer-compatible for BatchRequest" in prompt
    assert "SECTION CHOOSER" in prompt
    assert "Do not default to beliefs_active" in prompt
    assert "current question, not a blocking missing field" in prompt
    assert "Do not convert scoreboard items into beliefs_active.add_fact" in prompt
    assert "Emit at most one add_referent" in prompt
    assert "local discourse definition is not a belief" in prompt
    assert "Durable shorthand definitions with no local scope" in prompt
    assert "When I say blue bag" in prompt
    assert "Use add_referent for scoped phrases" in prompt
    assert "Do not use add_referent when the turn only contains unresolved placeholders" in prompt
    assert "Use push_topic, not narrative_active.create_thread" in prompt
    assert "Plain focus/switch-topic language is scoreboard.push_topic" in prompt
    assert "Switch the conversation to the school conference plan" in prompt
    assert "Can you help me track which school forms are still due" in prompt
    assert "clarifications.request is classifier-owned gap detection" in prompt
    assert "even if Front did not verbalize the question" in prompt
    assert "Clarifications are open gaps" in prompt
    assert "Do not downgrade a blocking missing field to scoreboard.push_question" in prompt
    assert "Reminder clarification" in prompt
    assert "Dropoff clarification" in prompt
    assert "Reminder status question" in prompt
    assert "Transcript/artifact read" in prompt
    assert "Meta/archive reads" in prompt
    assert "Which internal policy says what you are allowed to write" in prompt
    assert "What is in the warm beliefs archive" in prompt
    assert "Durable correction choice" in prompt
    assert "Pack the red lunchbox for Mira" in prompt
    assert "Do not use add_referent for durable corrections" in prompt
    assert "Do not use clarifications.request or scoreboard.push_question" in prompt
    assert "placeholder-only commands" in prompt
    assert "Do not use clarifications.answer for a new underspecified command" in prompt
    assert "Do not store a clarification question as beliefs_active.add_fact" in prompt
    assert "present emotional signal" in prompt
    assert "First-person affect wins section choice" in prompt
    assert "Do not convert affect into beliefs_active.add_fact" in prompt
    assert "set both mutation.confidence and data.confidence" in prompt
    assert "data must include subject, predicate, obj" in prompt
    assert "Use obj, not object" in prompt
    assert "add_fact creates a new fact and never copies an existing snapshot id" in prompt
    assert "emit exactly one Priya replacement fact" in prompt
    assert "exact existing fact id from the snapshot" in prompt
    assert "Do not use update_confidence to express 'not X, now Y'" in prompt
    assert "object-centric and person-centric paraphrases" in prompt
    assert "Sam uses the blue folder" in prompt
    assert "do not add narrative mutations" in prompt
    assert "Scenario thread labels are not thread ids" in prompt
    assert "The turn is only a greeting, thanks" in prompt
    assert "live runtime/capability state" in prompt
    assert "unresolved placeholders" in prompt
    assert 'Do not write "pickup discussion closed"' in prompt
    assert "the user is done with pickup arrangements" in prompt
    assert "False writes are worse than missed noncritical writes" in prompt
