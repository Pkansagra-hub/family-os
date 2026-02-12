"""
Tests for Workflow Types (Issue 4.1.2).

WorkflowSpec, TriggerSpec, TriggerType, DynamicExpr -- frozen domain types
for the workflow subsystem.

Test classes:
  TestTriggerType                   -- Enum values and membership.
  TestTriggerSpecValidation         -- CRON/EVENT/MANUAL validation rules.
  TestTriggerSpecDefaults           -- Default values (timezone, enabled).
  TestTriggerSpecFrozen             -- Immutability.
  TestWorkflowSpecFields            -- 11-field frozen dataclass.
  TestWorkflowSpecValidation        -- __post_init__ validators.
  TestWorkflowSpecFrozen            -- Immutability + identity.
  TestDynamicExprParse              -- Regex matching and edge cases.
  TestDynamicExprStructure          -- Field access and frozen.
  TestDynamicExprV1Namespaces       -- date (today, now) + user (timezone, locale).
  TestDynamicExprOffsetVariants     -- d/h/m/s offset units.
  TestReExports                     -- workflow_types exports and __init__ re-exports.
  TestVersionEntry                  -- VersionEntry frozen dataclass.
  TestWorkflowVersionPointer        -- Mutable pointer for version tracking.
"""

from __future__ import annotations

import time
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from k1.orchestrator.types import PlanStep, TriggerSpec, TriggerType
from k1.orchestrator.workflows.workflow_types import (
    DynamicExpr,
    VersionEntry,
    WorkflowSpec,
    WorkflowVersionPointer,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _step(step_id: str = "s1", capability: str = "cap.test") -> PlanStep:
    return PlanStep(id=step_id, capability=capability)


def _manual_trigger() -> TriggerSpec:
    return TriggerSpec(type=TriggerType.MANUAL)


def _cron_trigger(schedule: str = "0 9 * * MON") -> TriggerSpec:
    return TriggerSpec(type=TriggerType.CRON, schedule=schedule)


def _event_trigger(topic: str = "k1.user.hello.v1") -> TriggerSpec:
    return TriggerSpec(type=TriggerType.EVENT, event_topic=topic)


def _spec(
    workflow_id: str = "wf-001",
    name: str = "Test WF",
    version: str = "1.0.0",
    trigger: TriggerSpec | None = None,
    steps: list[PlanStep] | None = None,
    active: bool = True,
) -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=workflow_id,
        name=name,
        source_plan_id="plan-001",
        version=version,
        trigger=trigger or _manual_trigger(),
        steps=[_step()] if steps is None else steps,
        dependencies={},
        active=active,
    )


# ===========================================================================
# TestTriggerType
# ===========================================================================


class TestTriggerType:
    """Enum values and membership."""

    def test_cron_value(self) -> None:
        assert TriggerType.CRON == "CRON"
        assert TriggerType.CRON.value == "CRON"

    def test_event_value(self) -> None:
        assert TriggerType.EVENT == "EVENT"

    def test_manual_value(self) -> None:
        assert TriggerType.MANUAL == "MANUAL"

    def test_three_members(self) -> None:
        assert len(TriggerType) == 3

    def test_is_str_enum(self) -> None:
        assert isinstance(TriggerType.CRON, str)

    def test_invalid_member_raises(self) -> None:
        with pytest.raises(ValueError):
            TriggerType("DAILY")


# ===========================================================================
# TestTriggerSpecValidation
# ===========================================================================


class TestTriggerSpecValidation:
    """CRON/EVENT/MANUAL validation rules per 4.1.2 spec."""

    def test_cron_requires_schedule(self) -> None:
        with pytest.raises(ValueError, match="schedule"):
            TriggerSpec(type=TriggerType.CRON)

    def test_cron_empty_schedule_raises(self) -> None:
        with pytest.raises(ValueError, match="schedule"):
            TriggerSpec(type=TriggerType.CRON, schedule="")

    def test_cron_with_schedule_ok(self) -> None:
        t = _cron_trigger("0 9 * * MON")
        assert t.schedule == "0 9 * * MON"

    def test_event_requires_topic(self) -> None:
        with pytest.raises(ValueError, match="event_topic"):
            TriggerSpec(type=TriggerType.EVENT)

    def test_event_empty_topic_raises(self) -> None:
        with pytest.raises(ValueError, match="event_topic"):
            TriggerSpec(type=TriggerType.EVENT, event_topic="")

    def test_event_with_topic_ok(self) -> None:
        t = _event_trigger("user.hello")
        assert t.event_topic == "user.hello"

    def test_manual_ok(self) -> None:
        t = _manual_trigger()
        assert t.type == TriggerType.MANUAL

    def test_manual_with_schedule_raises(self) -> None:
        with pytest.raises(ValueError, match="MANUAL"):
            TriggerSpec(type=TriggerType.MANUAL, schedule="0 8 * * *")

    def test_manual_with_event_topic_raises(self) -> None:
        with pytest.raises(ValueError, match="MANUAL"):
            TriggerSpec(type=TriggerType.MANUAL, event_topic="some.topic")

    def test_manual_with_both_raises(self) -> None:
        with pytest.raises(ValueError, match="MANUAL"):
            TriggerSpec(
                type=TriggerType.MANUAL,
                schedule="0 9 * * *",
                event_topic="some.topic",
            )


# ===========================================================================
# TestTriggerSpecDefaults
# ===========================================================================


class TestTriggerSpecDefaults:
    """Default values: timezone='UTC', enabled=True per 4.1.2."""

    def test_timezone_default_utc(self) -> None:
        t = _manual_trigger()
        assert t.timezone == "UTC"

    def test_timezone_custom(self) -> None:
        t = TriggerSpec(
            type=TriggerType.CRON,
            schedule="0 9 * * MON",
            timezone="America/New_York",
        )
        assert t.timezone == "America/New_York"

    def test_enabled_default_true(self) -> None:
        t = _manual_trigger()
        assert t.enabled is True

    def test_enabled_explicit_false(self) -> None:
        t = TriggerSpec(type=TriggerType.MANUAL, enabled=False)
        assert t.enabled is False

    def test_schedule_default_none(self) -> None:
        t = _manual_trigger()
        assert t.schedule is None

    def test_event_topic_default_none(self) -> None:
        t = _manual_trigger()
        assert t.event_topic is None

    def test_cron_trigger_all_fields(self) -> None:
        t = TriggerSpec(
            type=TriggerType.CRON,
            schedule="0 9 * * MON",
            timezone="Europe/London",
            event_topic=None,
            enabled=True,
        )
        assert t.type == TriggerType.CRON
        assert t.schedule == "0 9 * * MON"
        assert t.timezone == "Europe/London"
        assert t.event_topic is None
        assert t.enabled is True

    def test_triggerspec_field_count(self) -> None:
        """TriggerSpec has 5 fields per 4.1.2 spec."""
        assert len(fields(TriggerSpec)) == 5


# ===========================================================================
# TestTriggerSpecFrozen
# ===========================================================================


class TestTriggerSpecFrozen:
    """TriggerSpec is frozen (immutable)."""

    def test_cannot_mutate_type(self) -> None:
        t = _manual_trigger()
        with pytest.raises(FrozenInstanceError):
            t.type = TriggerType.CRON  # type: ignore[misc]

    def test_cannot_mutate_schedule(self) -> None:
        t = _cron_trigger()
        with pytest.raises(FrozenInstanceError):
            t.schedule = "0 0 * * *"  # type: ignore[misc]

    def test_cannot_mutate_timezone(self) -> None:
        t = _manual_trigger()
        with pytest.raises(FrozenInstanceError):
            t.timezone = "Asia/Tokyo"  # type: ignore[misc]

    def test_cannot_mutate_enabled(self) -> None:
        t = _manual_trigger()
        with pytest.raises(FrozenInstanceError):
            t.enabled = False  # type: ignore[misc]


# ===========================================================================
# TestWorkflowSpecFields
# ===========================================================================


class TestWorkflowSpecFields:
    """WorkflowSpec frozen dataclass with 11 fields."""

    def test_field_count(self) -> None:
        assert len(fields(WorkflowSpec)) == 11

    def test_required_fields(self) -> None:
        spec = _spec()
        assert spec.workflow_id == "wf-001"
        assert spec.name == "Test WF"
        assert spec.source_plan_id == "plan-001"
        assert spec.version == "1.0.0"
        assert spec.trigger.type == TriggerType.MANUAL

    def test_steps_are_plan_steps(self) -> None:
        spec = _spec()
        assert len(spec.steps) == 1
        assert isinstance(spec.steps[0], PlanStep)

    def test_dependencies_dict(self) -> None:
        spec = _spec()
        assert spec.dependencies == {}

    def test_default_active(self) -> None:
        spec = _spec()
        assert spec.active is True

    def test_default_created_by(self) -> None:
        spec = _spec()
        assert spec.created_by == "system"

    def test_created_at_is_float(self) -> None:
        before = time.time()
        spec = _spec()
        after = time.time()
        assert before <= spec.created_at <= after

    def test_updated_at_is_float(self) -> None:
        before = time.time()
        spec = _spec()
        after = time.time()
        assert before <= spec.updated_at <= after

    def test_custom_created_by(self) -> None:
        spec = WorkflowSpec(
            workflow_id="wf-1",
            name="Test",
            source_plan_id="p-1",
            version="1.0.0",
            trigger=_manual_trigger(),
            steps=[_step()],
            dependencies={},
            created_by="user-42",
        )
        assert spec.created_by == "user-42"

    def test_steps_use_orchestrator_planstep(self) -> None:
        """Steps use 14-field Orchestrator PlanStep, not Fabric PlanStep."""
        step = _step()
        # Orchestrator PlanStep has output_schema, condition, is_optional, etc.
        assert hasattr(step, "output_schema")
        assert hasattr(step, "condition")
        assert hasattr(step, "is_optional")
        assert hasattr(step, "has_side_effects")
        assert hasattr(step, "compensation")
        assert hasattr(step, "timeout_ms")
        assert hasattr(step, "required_context")
        assert hasattr(step, "safety_band_min")


# ===========================================================================
# TestWorkflowSpecValidation
# ===========================================================================


class TestWorkflowSpecValidation:
    """__post_init__ validates name, steps, version."""

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="name"):
            _spec(name="")

    def test_empty_steps_raises(self) -> None:
        with pytest.raises(ValueError, match="steps"):
            _spec(steps=[])

    def test_invalid_version_no_dots(self) -> None:
        with pytest.raises(ValueError, match="semver"):
            _spec(version="1")

    def test_invalid_version_two_parts(self) -> None:
        with pytest.raises(ValueError, match="semver"):
            _spec(version="1.0")

    def test_invalid_version_prefix_v(self) -> None:
        with pytest.raises(ValueError, match="semver"):
            _spec(version="v1.0.0")

    def test_invalid_version_alpha(self) -> None:
        with pytest.raises(ValueError, match="semver"):
            _spec(version="1.0.0-beta")

    def test_valid_version_1_0_0(self) -> None:
        spec = _spec(version="1.0.0")
        assert spec.version == "1.0.0"

    def test_valid_version_0_0_0(self) -> None:
        spec = _spec(version="0.0.0")
        assert spec.version == "0.0.0"

    def test_valid_version_100_0_0(self) -> None:
        spec = _spec(version="100.0.0")
        assert spec.version == "100.0.0"

    def test_valid_version_2_0_0(self) -> None:
        spec = _spec(version="2.0.0")
        assert spec.version == "2.0.0"


# ===========================================================================
# TestWorkflowSpecFrozen
# ===========================================================================


class TestWorkflowSpecFrozen:
    """WorkflowSpec is FROZEN -- bump_version() creates NEW instance."""

    def test_cannot_mutate_name(self) -> None:
        spec = _spec()
        with pytest.raises(FrozenInstanceError):
            spec.name = "mutated"  # type: ignore[misc]

    def test_cannot_mutate_version(self) -> None:
        spec = _spec()
        with pytest.raises(FrozenInstanceError):
            spec.version = "2.0.0"  # type: ignore[misc]

    def test_cannot_mutate_active(self) -> None:
        spec = _spec()
        with pytest.raises(FrozenInstanceError):
            spec.active = False  # type: ignore[misc]

    def test_replace_creates_new_instance(self) -> None:
        spec = _spec()
        new_spec = replace(spec, version="2.0.0")
        assert new_spec is not spec
        assert new_spec.version == "2.0.0"
        assert spec.version == "1.0.0"

    def test_replace_preserves_other_fields(self) -> None:
        spec = _spec()
        new_spec = replace(spec, version="2.0.0")
        assert new_spec.name == spec.name
        assert new_spec.workflow_id == spec.workflow_id
        assert new_spec.trigger == spec.trigger


# ===========================================================================
# TestDynamicExprStructure
# ===========================================================================


class TestDynamicExprStructure:
    """DynamicExpr field access and frozen."""

    def test_basic_fields(self) -> None:
        expr = DynamicExpr(raw="${date.today}", namespace="date", field="today")
        assert expr.raw == "${date.today}"
        assert expr.namespace == "date"
        assert expr.field == "today"
        assert expr.offset is None

    def test_with_offset(self) -> None:
        expr = DynamicExpr(raw="${date.today +2d}", namespace="date", field="today", offset="+2d")
        assert expr.offset == "+2d"

    def test_is_frozen(self) -> None:
        expr = DynamicExpr(raw="${date.today}", namespace="date", field="today")
        with pytest.raises(FrozenInstanceError):
            expr.namespace = "user"  # type: ignore[misc]

    def test_field_count(self) -> None:
        assert len(fields(DynamicExpr)) == 4


# ===========================================================================
# TestDynamicExprParse
# ===========================================================================


class TestDynamicExprParse:
    """DynamicExpr.parse() regex matching and static method."""

    # -- Successful parsing --

    def test_parse_simple(self) -> None:
        result = DynamicExpr.parse("${date.today}")
        assert result is not None
        assert result.namespace == "date"
        assert result.field == "today"
        assert result.offset is None

    def test_parse_preserves_raw(self) -> None:
        raw = "${date.today +2d}"
        result = DynamicExpr.parse(raw)
        assert result is not None
        assert result.raw == raw

    def test_parse_positive_offset(self) -> None:
        result = DynamicExpr.parse("${date.today +2d}")
        assert result is not None
        assert result.offset == "+2d"

    def test_parse_negative_offset(self) -> None:
        result = DynamicExpr.parse("${date.now -1h}")
        assert result is not None
        assert result.offset == "-1h"

    # -- Returns None for non-dynamic values --

    def test_parse_plain_text(self) -> None:
        assert DynamicExpr.parse("hello world") is None

    def test_parse_number_string(self) -> None:
        assert DynamicExpr.parse("42") is None

    def test_parse_empty_string(self) -> None:
        assert DynamicExpr.parse("") is None

    def test_parse_non_string(self) -> None:
        assert DynamicExpr.parse(42) is None  # type: ignore[arg-type]

    def test_parse_none(self) -> None:
        assert DynamicExpr.parse(None) is None  # type: ignore[arg-type]

    def test_parse_bool(self) -> None:
        assert DynamicExpr.parse(True) is None  # type: ignore[arg-type]

    def test_parse_partial_match(self) -> None:
        assert DynamicExpr.parse("prefix ${date.today} suffix") is None

    def test_parse_no_namespace(self) -> None:
        assert DynamicExpr.parse("${today}") is None

    def test_parse_triple_dot(self) -> None:
        assert DynamicExpr.parse("${a.b.c}") is None

    def test_parse_missing_braces(self) -> None:
        assert DynamicExpr.parse("$date.today") is None

    def test_parse_missing_dollar(self) -> None:
        assert DynamicExpr.parse("{date.today}") is None


# ===========================================================================
# TestDynamicExprV1Namespaces
# ===========================================================================


class TestDynamicExprV1Namespaces:
    """V1 namespaces: date (today, now) + user (timezone, locale)."""

    def test_date_today(self) -> None:
        result = DynamicExpr.parse("${date.today}")
        assert result is not None
        assert result.namespace == "date"
        assert result.field == "today"

    def test_date_now(self) -> None:
        result = DynamicExpr.parse("${date.now}")
        assert result is not None
        assert result.namespace == "date"
        assert result.field == "now"

    def test_user_timezone(self) -> None:
        result = DynamicExpr.parse("${user.timezone}")
        assert result is not None
        assert result.namespace == "user"
        assert result.field == "timezone"

    def test_user_locale(self) -> None:
        result = DynamicExpr.parse("${user.locale}")
        assert result is not None
        assert result.namespace == "user"
        assert result.field == "locale"

    def test_custom_namespace_parses(self) -> None:
        """Regex accepts any namespace -- extensible via resolver registry."""
        result = DynamicExpr.parse("${custom.thing}")
        assert result is not None
        assert result.namespace == "custom"


# ===========================================================================
# TestDynamicExprOffsetVariants
# ===========================================================================


class TestDynamicExprOffsetVariants:
    """d/h/m/s offset units."""

    def test_days(self) -> None:
        result = DynamicExpr.parse("${date.today +2d}")
        assert result is not None
        assert result.offset == "+2d"

    def test_hours(self) -> None:
        result = DynamicExpr.parse("${date.now +24h}")
        assert result is not None
        assert result.offset == "+24h"

    def test_minutes(self) -> None:
        result = DynamicExpr.parse("${date.now +30m}")
        assert result is not None
        assert result.offset == "+30m"

    def test_seconds(self) -> None:
        result = DynamicExpr.parse("${date.now -120s}")
        assert result is not None
        assert result.offset == "-120s"

    def test_large_offset(self) -> None:
        result = DynamicExpr.parse("${date.now +999d}")
        assert result is not None
        assert result.offset == "+999d"

    def test_single_digit_offset(self) -> None:
        result = DynamicExpr.parse("${date.now -1h}")
        assert result is not None
        assert result.offset == "-1h"


# ===========================================================================
# TestReExports
# ===========================================================================


class TestReExports:
    """workflow_types exports and workflows __init__ re-exports."""

    def test_workflow_types_exports_triggertype(self) -> None:
        from k1.orchestrator.workflows.workflow_types import TriggerType as TT

        assert TT is TriggerType

    def test_workflow_types_exports_triggerspec(self) -> None:
        from k1.orchestrator.workflows.workflow_types import TriggerSpec as TS

        assert TS is TriggerSpec

    def test_workflows_init_exports_triggertype(self) -> None:
        from k1.orchestrator.workflows import TriggerType as TT

        assert TT is TriggerType

    def test_workflows_init_exports_triggerspec(self) -> None:
        from k1.orchestrator.workflows import TriggerSpec as TS

        assert TS is TriggerSpec

    def test_workflows_init_exports_workflowspec(self) -> None:
        from k1.orchestrator.workflows import WorkflowSpec as WS

        assert WS is WorkflowSpec

    def test_workflows_init_exports_dynamicexpr(self) -> None:
        from k1.orchestrator.workflows import DynamicExpr as DE

        assert DE is DynamicExpr

    def test_workflow_types_all_has_9_entries(self) -> None:
        import k1.orchestrator.workflows.workflow_types as wt

        assert len(wt.__all__) == 9  # +2: RunManifest, RunStatus (4.2.4)


# ===========================================================================
# TestVersionEntry
# ===========================================================================


class TestVersionEntry:
    """VersionEntry frozen dataclass (4.1.4 types in workflow_types.py)."""

    def test_all_fields(self) -> None:
        entry = VersionEntry(
            version="2.0.0",
            created_at=1000.0,
            source_plan_id="p-1",
            step_count=3,
            change_summary="Added step",
        )
        assert entry.version == "2.0.0"
        assert entry.step_count == 3

    def test_is_frozen(self) -> None:
        entry = VersionEntry(
            version="1.0.0",
            created_at=0.0,
            source_plan_id="p",
            step_count=1,
            change_summary="init",
        )
        with pytest.raises(FrozenInstanceError):
            entry.version = "2.0.0"  # type: ignore[misc]


# ===========================================================================
# TestWorkflowVersionPointer
# ===========================================================================


class TestWorkflowVersionPointer:
    """Mutable pointer for version tracking."""

    def test_initial_state(self) -> None:
        ptr = WorkflowVersionPointer(workflow_id="wf-1", active_version="1.0.0")
        assert ptr.active_version == "1.0.0"
        assert ptr.version_history == []

    def test_is_mutable(self) -> None:
        ptr = WorkflowVersionPointer(workflow_id="wf-1", active_version="1.0.0")
        ptr.active_version = "2.0.0"
        assert ptr.active_version == "2.0.0"

    def test_append_history(self) -> None:
        ptr = WorkflowVersionPointer(workflow_id="wf-1", active_version="1.0.0")
        entry = VersionEntry(
            version="2.0.0",
            created_at=time.time(),
            source_plan_id="p-2",
            step_count=5,
            change_summary="bump",
        )
        ptr.version_history.append(entry)
        assert len(ptr.version_history) == 1
