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
    add_fact_schema = next(
        item
        for item in items
        if item["properties"]["section"]["const"] == "beliefs_active"
        and item["properties"]["operation"]["const"] == "add_fact"
    )
    resolve_thread_schema = next(
        item
        for item in items
        if item["properties"]["section"]["const"] == "narrative_active"
        and item["properties"]["operation"]["const"] == "resolve_thread"
    )

    add_fact_data = add_fact_schema["properties"]["data"]
    assert add_fact_data["required"] == ["subject", "predicate", "obj", "confidence", "source"]
    assert "id" not in add_fact_data["properties"]
    assert add_fact_data["additionalProperties"] is False
    assert resolve_thread_schema["properties"]["data"]["required"] == ["thread_id"]


def test_system_prompt_teaches_kernel_role_split_and_writer_contract() -> None:
    prompt = build_section_update_system_prompt()

    assert "post-turn cognitive SessionState mutation planner" in prompt
    assert "SYSTEM ROLE SPLIT" in prompt
    assert "Front owns conversation continuity" in prompt
    assert "FSM/runtime owns control" in prompt
    assert "Legacy Front tool names" in prompt
    assert "Raw legacy Front session write payloads stay out of the classifier input" in prompt
    assert "writer-compatible for BatchRequest" in prompt
    assert "set both mutation.confidence and data.confidence" in prompt
    assert "data must include subject, predicate, obj" in prompt
    assert "Use obj, not object" in prompt
    assert "add_fact creates a new fact and never copies an existing snapshot id" in prompt
    assert "emit exactly one Priya replacement fact" in prompt
    assert "exact existing fact id from the snapshot" in prompt
    assert "Do not use update_confidence to express 'not X, now Y'" in prompt
    assert "do not add narrative mutations" in prompt
    assert "Scenario thread labels are not thread ids" in prompt
    assert "The turn is only a greeting, thanks" in prompt
    assert 'Do not write "pickup discussion closed"' in prompt
    assert "the user is done with pickup arrangements" in prompt
    assert "False writes are worse than missed noncritical writes" in prompt
