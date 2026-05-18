"""Tests for ``ToolDefinition`` / ``ActionSpec`` / ``FieldSpec`` (§E15.0.2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from k1.tools.family.definition import (
    ActionSpec,
    FieldSpec,
    LLMHints,
    SSESpec,
    ToolDefinition,
)

_TABLES = "CREATE TABLE IF NOT EXISTS demo_schema_version (version INTEGER PRIMARY KEY);"


def _action(name: str = "do", kind: str = "compute") -> ActionSpec:
    return ActionSpec(
        name=name,
        kind=kind,  # type: ignore[arg-type]
        summary="do something",
        params=[FieldSpec(name="msg", type="string", required=True)],
        result=[FieldSpec(name="ok", type="boolean", required=True)],
        llm=LLMHints(use_when=["use when foo"], examples=["foo it"]),
        sse=SSESpec(emits=[f"family.demo.{name}.{kind}.v1"]),
    )


class TestToolDefinition:
    def test_minimal_valid(self) -> None:
        d = ToolDefinition(
            adapter_id="demo",
            summary="demo adapter",
            tables_sql=_TABLES,
            actions=[_action()],
        )
        assert d.adapter_id == "demo"
        assert d.version == "1.0.0"
        assert d.category == "family"
        assert d.find_action("do") is not None
        assert d.find_action("nope") is None

    def test_tables_sql_must_include_schema_version_table(self) -> None:
        with pytest.raises(ValidationError):
            ToolDefinition(
                adapter_id="demo",
                summary="demo",
                tables_sql="CREATE TABLE foo (id INT);",  # missing demo_schema_version
                actions=[_action()],
            )

    def test_duplicate_action_names_rejected(self) -> None:
        a1 = _action("dup")
        a2 = _action("dup")
        with pytest.raises(ValidationError):
            ToolDefinition(
                adapter_id="demo",
                summary="demo",
                tables_sql=_TABLES,
                actions=[a1, a2],
            )

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ToolDefinition(
                adapter_id="demo",
                summary="demo",
                tables_sql=_TABLES,
                actions=[_action()],
                extra="bad",  # type: ignore[call-arg]
            )

    def test_optional_descriptive_fields(self) -> None:
        d = ToolDefinition(
            adapter_id="demo",
            summary="demo",
            tables_sql=_TABLES,
            actions=[_action()],
            title="Demo",
            icon="📋",
            description="Long form description.",
            entity_type="demo_item",
            views=["list", "calendar"],
            can_reference=["calendar_event"],
            feature_flags=["beta"],
        )
        assert d.title == "Demo"
        assert d.views == ["list", "calendar"]

    def test_prompt_profile_defaults_are_backward_compatible(self) -> None:
        d = ToolDefinition(
            adapter_id="demo",
            summary="demo",
            tables_sql=_TABLES,
            actions=[_action()],
        )

        assert d.activity_profile is None
        assert d.domain_tags == []

    def test_prompt_profile_fields_can_be_declared(self) -> None:
        d = ToolDefinition(
            adapter_id="demo",
            summary="demo",
            tables_sql=_TABLES,
            actions=[_action()],
            activity_profile="demo.default.v1",
            domain_tags=["coordination", "diagnostic"],
        )

        assert d.activity_profile == "demo.default.v1"
        assert d.domain_tags == ["coordination", "diagnostic"]


class TestActionSpec:
    def test_allowed_roles_default(self) -> None:
        a = _action()
        assert "parent" in a.allowed_roles

    def test_allowed_roles_must_be_nonempty(self) -> None:
        with pytest.raises(ValidationError):
            ActionSpec(name="x", kind="read", summary="x", allowed_roles=[])

    def test_min_role_optional(self) -> None:
        a = ActionSpec(name="x", kind="write", summary="x", min_role="guardian")
        assert a.min_role == "guardian"

    def test_name_pattern_enforced(self) -> None:
        with pytest.raises(ValidationError):
            ActionSpec(name="BadName", kind="read", summary="x")

    def test_prompt_profile_defaults_are_backward_compatible(self) -> None:
        a = ActionSpec(name="x", kind="read", summary="x")

        assert a.prompt_template is None
        assert a.activity_profile is None
        assert a.tool_instructions is None
        assert a.social_act is None
        assert a.side_effects == []

    def test_prompt_profile_fields_can_be_declared(self) -> None:
        a = ActionSpec(
            name="create_item",
            kind="write",
            summary="Create item",
            prompt_template="demo_activity_v1",
            activity_profile="demo.action.v1",
            tool_instructions="Copy the returned id into the final result.",
            social_act="create_record",
            side_effects=[{"kind": "data_write", "target": "demo.item"}],
        )

        assert a.prompt_template == "demo_activity_v1"
        assert a.activity_profile == "demo.action.v1"
        assert a.tool_instructions == "Copy the returned id into the final result."
        assert a.social_act == "create_record"
        assert a.side_effects == [{"kind": "data_write", "target": "demo.item"}]


class TestFieldSpec:
    def test_basic(self) -> None:
        f = FieldSpec(name="x", type="integer", required=True, description="d", example=1)
        assert f.required is True
        assert f.example == 1

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            FieldSpec(name="x", type="string", x=1)  # type: ignore[call-arg]
