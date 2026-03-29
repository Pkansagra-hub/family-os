"""Tests for Epic 1.5 issues 1.5.1-1.5.4 -- Event Schemas (plan.ready, plan.failed,
plan.cancelled, micro_replan.ready).

Coverage:
- 1.5.1: plan.ready topic + CommittedPlan as payload
- 1.5.2: plan.failed topic + PlanFailedPayload (fields, stage values, error_code values)
- 1.5.3: plan.cancelled topic + PlanCancelledPayload (fields, reason values)
- 1.5.4: micro_replan.ready topic + CommittedPlan as payload (distinct from plan.ready)

Validates against planner.md SS26.2, SS28.1, SS30.5.1 F06.
"""

from __future__ import annotations

import dataclasses

import pytest

# ===================================================================
# 1.5.1 -- plan.ready event schema
# ===================================================================


class TestPlanReadyTopicConstant:
    """TOPIC_PLAN_READY matches SS28.1 exactly."""

    def test_topic_string_exact_value(self):
        from k1.planner.events import TOPIC_PLAN_READY

        assert TOPIC_PLAN_READY == "k1.planner.plan.ready.v1"

    def test_topic_is_str_not_enum(self):
        from k1.planner.events import TOPIC_PLAN_READY

        assert type(TOPIC_PLAN_READY) is str

    def test_topic_importable_from_package_init(self):
        from k1.planner import TOPIC_PLAN_READY

        assert TOPIC_PLAN_READY == "k1.planner.plan.ready.v1"


class TestPlanReadyPayload:
    """plan.ready uses CommittedPlan directly -- no wrapper (SS30.5.1 F06)."""

    def test_committed_plan_is_payload(self):
        """CommittedPlan is the payload type -- verify it exists and is a dataclass."""
        from k1.orchestrator.types import CommittedPlan

        assert dataclasses.is_dataclass(CommittedPlan)

    def test_committed_plan_is_frozen(self):
        from k1.orchestrator.types import CommittedPlan, PlanStep

        plan = CommittedPlan(
            plan_id="p1",
            request_id="r1",
            intent="test",
            steps=[PlanStep(id="s1", capability="search")],
            trace_id="t1",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.plan_id = "p2"

    def test_committed_plan_has_required_fields(self):
        """SS28.1: CommittedPlan carries plan_id, request_id, intent, steps,
        trace_id, dependencies, estimated_duration_ms, created_at."""
        from k1.orchestrator.types import CommittedPlan

        field_names = {f.name for f in dataclasses.fields(CommittedPlan)}
        required = {
            "plan_id",
            "request_id",
            "intent",
            "steps",
            "trace_id",
            "dependencies",
            "estimated_duration_ms",
            "created_at",
        }
        assert required.issubset(field_names), f"Missing fields: {required - field_names}"

    def test_committed_plan_steps_is_list(self):
        from k1.orchestrator.types import CommittedPlan, PlanStep

        plan = CommittedPlan(
            plan_id="p1",
            request_id="r1",
            intent="test",
            steps=[PlanStep(id="s1", capability="search")],
            trace_id="t1",
        )
        assert isinstance(plan.steps, list)
        assert len(plan.steps) == 1

    def test_no_wrapper_dataclass_exists(self):
        """F06 note: CommittedPlan is the payload -- no PlanReadyPayload wrapper."""
        import k1.planner.events as events_mod

        names = [n for n in dir(events_mod) if "PlanReady" in n and "Payload" in n]
        assert names == [], f"Unexpected PlanReadyPayload wrapper found: {names}"

    def test_committed_plan_correlation_field(self):
        """SS28.1: Orchestrator correlates via request_id to PendingPlanContext."""
        from k1.orchestrator.types import CommittedPlan, PlanStep

        plan = CommittedPlan(
            plan_id="p1",
            request_id="r-corr",
            intent="test",
            steps=[PlanStep(id="s1", capability="search")],
            trace_id="t1",
        )
        assert plan.request_id == "r-corr"


# ===================================================================
# 1.5.2 -- plan.failed event schema
# ===================================================================


class TestPlanFailedTopicConstant:
    """TOPIC_PLAN_FAILED matches SS28.1 exactly."""

    def test_topic_string_exact_value(self):
        from k1.planner.events import TOPIC_PLAN_FAILED

        assert TOPIC_PLAN_FAILED == "k1.planner.plan.failed.v1"

    def test_topic_is_str_not_enum(self):
        from k1.planner.events import TOPIC_PLAN_FAILED

        assert type(TOPIC_PLAN_FAILED) is str

    def test_topic_importable_from_package_init(self):
        from k1.planner import TOPIC_PLAN_FAILED

        assert TOPIC_PLAN_FAILED == "k1.planner.plan.failed.v1"


class TestPlanFailedPayloadFields:
    """PlanFailedPayload fields match SS28.1 and F06 spec."""

    def test_has_all_spec_fields(self):
        """SS28.1: {request_id, stage, error_code, error_message,
        partial_state, tokens_used, duration_ms, trace_id}."""
        from k1.planner.events import PlanFailedPayload

        field_names = {f.name for f in dataclasses.fields(PlanFailedPayload)}
        expected = {
            "request_id",
            "stage",
            "error_code",
            "error_message",
            "partial_state",
            "tokens_used",
            "duration_ms",
            "trace_id",
        }
        assert field_names == expected, f"Field mismatch: {field_names ^ expected}"

    def test_field_count_is_8(self):
        from k1.planner.events import PlanFailedPayload

        assert len(dataclasses.fields(PlanFailedPayload)) == 8

    def test_is_frozen_dataclass(self):
        from k1.planner.events import PlanFailedPayload

        assert dataclasses.is_dataclass(PlanFailedPayload)
        # Verify frozen via construction + mutation attempt
        p = PlanFailedPayload(
            request_id="r1",
            stage="SKETCH",
            error_code="ERR_SKETCH_FAIL",
            error_message="LLM failed",
            tokens_used=100,
            duration_ms=500,
            trace_id="t1",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.stage = "EXPAND"

    def test_partial_state_optional_with_none_default(self):
        """partial_state is Optional[Dict] with default None (ergonomic ordering)."""
        from k1.planner.events import PlanFailedPayload

        p = PlanFailedPayload(
            request_id="r1",
            stage="SKETCH",
            error_code="ERR_SKETCH_FAIL",
            error_message="msg",
            tokens_used=0,
            duration_ms=0,
            trace_id="t1",
        )
        assert p.partial_state is None

    def test_partial_state_accepts_dict(self):
        from k1.planner.events import PlanFailedPayload

        state = {"rough_steps": [{"action": "search"}]}
        p = PlanFailedPayload(
            request_id="r1",
            stage="EXPAND",
            error_code="ERR_EXPAND_FAIL",
            error_message="expand failed",
            tokens_used=500,
            duration_ms=3000,
            trace_id="t1",
            partial_state=state,
        )
        assert p.partial_state == state


class TestPlanFailedStageValues:
    """SS28.1: stage values are SKETCH, EXPAND, VALIDATE, COMMIT."""

    @pytest.mark.parametrize("stage", ["SKETCH", "EXPAND", "VALIDATE", "COMMIT"])
    def test_valid_stage_construction(self, stage):
        from k1.planner.events import PlanFailedPayload

        p = PlanFailedPayload(
            request_id="r1",
            stage=stage,
            error_code="ERR_TIMEOUT",
            error_message="timeout",
            tokens_used=0,
            duration_ms=45000,
            trace_id="t1",
        )
        assert p.stage == stage


class TestPlanFailedErrorCodes:
    """SS28.1 error_code values: ERR_SKETCH_FAIL, ERR_EXPAND_FAIL,
    ERR_VALIDATE_FAIL, ERR_COMMIT_FAIL, ERR_TIMEOUT, ERR_BUDGET_EXCEEDED."""

    @pytest.mark.parametrize(
        "error_code",
        [
            "ERR_SKETCH_FAIL",
            "ERR_EXPAND_FAIL",
            "ERR_VALIDATE_FAIL",
            "ERR_COMMIT_FAIL",
            "ERR_TIMEOUT",
            "ERR_BUDGET_EXCEEDED",
        ],
    )
    def test_valid_error_code_construction(self, error_code):
        from k1.planner.events import PlanFailedPayload

        p = PlanFailedPayload(
            request_id="r1",
            stage="SKETCH",
            error_code=error_code,
            error_message="fail",
            tokens_used=0,
            duration_ms=0,
            trace_id="t1",
        )
        assert p.error_code == error_code


class TestPlanFailedValidation:
    """PlanFailedPayload __post_init__ validation."""

    def test_empty_request_id_raises(self):
        from k1.planner.events import PlanFailedPayload

        with pytest.raises(ValueError, match="request_id"):
            PlanFailedPayload(
                request_id="",
                stage="SKETCH",
                error_code="ERR_SKETCH_FAIL",
                error_message="msg",
                tokens_used=0,
                duration_ms=0,
                trace_id="t1",
            )

    def test_empty_stage_raises(self):
        from k1.planner.events import PlanFailedPayload

        with pytest.raises(ValueError, match="stage"):
            PlanFailedPayload(
                request_id="r1",
                stage="",
                error_code="ERR_SKETCH_FAIL",
                error_message="msg",
                tokens_used=0,
                duration_ms=0,
                trace_id="t1",
            )

    def test_empty_error_code_raises(self):
        from k1.planner.events import PlanFailedPayload

        with pytest.raises(ValueError, match="error_code"):
            PlanFailedPayload(
                request_id="r1",
                stage="SKETCH",
                error_code="",
                error_message="msg",
                tokens_used=0,
                duration_ms=0,
                trace_id="t1",
            )

    def test_empty_trace_id_raises(self):
        from k1.planner.events import PlanFailedPayload

        with pytest.raises(ValueError, match="trace_id"):
            PlanFailedPayload(
                request_id="r1",
                stage="SKETCH",
                error_code="ERR_SKETCH_FAIL",
                error_message="msg",
                tokens_used=0,
                duration_ms=0,
                trace_id="",
            )

    def test_error_message_can_be_empty(self):
        """error_message has no non-empty validation -- free-form text."""
        from k1.planner.events import PlanFailedPayload

        p = PlanFailedPayload(
            request_id="r1",
            stage="SKETCH",
            error_code="ERR_SKETCH_FAIL",
            error_message="",
            tokens_used=0,
            duration_ms=0,
            trace_id="t1",
        )
        assert p.error_message == ""


class TestPlanFailedPayloadInAll:
    """PlanFailedPayload is in events.py __all__."""

    def test_in_module_all(self):
        from k1.planner import events

        assert "PlanFailedPayload" in events.__all__

    def test_in_package_all(self):
        import k1.planner

        assert "PlanFailedPayload" in k1.planner.__all__


# ===================================================================
# 1.5.3 -- plan.cancelled event schema
# ===================================================================


class TestPlanCancelledTopicConstant:
    """TOPIC_PLAN_CANCELLED matches SS28.1 exactly."""

    def test_topic_string_exact_value(self):
        from k1.planner.events import TOPIC_PLAN_CANCELLED

        assert TOPIC_PLAN_CANCELLED == "k1.planner.plan.cancelled.v1"

    def test_topic_is_str_not_enum(self):
        from k1.planner.events import TOPIC_PLAN_CANCELLED

        assert type(TOPIC_PLAN_CANCELLED) is str

    def test_topic_importable_from_package_init(self):
        from k1.planner import TOPIC_PLAN_CANCELLED

        assert TOPIC_PLAN_CANCELLED == "k1.planner.plan.cancelled.v1"


class TestPlanCancelledPayloadFields:
    """PlanCancelledPayload fields match SS28.1 and F06 spec."""

    def test_has_all_spec_fields(self):
        """SS28.1: {request_id, reason, stage, trace_id}."""
        from k1.planner.events import PlanCancelledPayload

        field_names = {f.name for f in dataclasses.fields(PlanCancelledPayload)}
        expected = {"request_id", "reason", "stage", "trace_id"}
        assert field_names == expected, f"Field mismatch: {field_names ^ expected}"

    def test_field_count_is_4(self):
        from k1.planner.events import PlanCancelledPayload

        assert len(dataclasses.fields(PlanCancelledPayload)) == 4

    def test_is_frozen_dataclass(self):
        from k1.planner.events import PlanCancelledPayload

        assert dataclasses.is_dataclass(PlanCancelledPayload)
        p = PlanCancelledPayload(
            request_id="r1",
            reason="cancelled_before_start",
            stage="SKETCH",
            trace_id="t1",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.reason = "other"


class TestPlanCancelledReasonValues:
    """SS28.1 reason values: cancelled_before_start, cancelled_between_stages,
    shutdown."""

    @pytest.mark.parametrize(
        "reason",
        ["cancelled_before_start", "cancelled_between_stages", "shutdown"],
    )
    def test_valid_reason_construction(self, reason):
        from k1.planner.events import PlanCancelledPayload

        p = PlanCancelledPayload(
            request_id="r1",
            reason=reason,
            stage="SKETCH",
            trace_id="t1",
        )
        assert p.reason == reason


class TestPlanCancelledValidation:
    """PlanCancelledPayload __post_init__ validation."""

    def test_empty_request_id_raises(self):
        from k1.planner.events import PlanCancelledPayload

        with pytest.raises(ValueError, match="request_id"):
            PlanCancelledPayload(
                request_id="",
                reason="shutdown",
                stage="SKETCH",
                trace_id="t1",
            )

    def test_empty_stage_raises(self):
        from k1.planner.events import PlanCancelledPayload

        with pytest.raises(ValueError, match="stage"):
            PlanCancelledPayload(
                request_id="r1",
                reason="shutdown",
                stage="",
                trace_id="t1",
            )

    def test_empty_trace_id_raises(self):
        from k1.planner.events import PlanCancelledPayload

        with pytest.raises(ValueError, match="trace_id"):
            PlanCancelledPayload(
                request_id="r1",
                reason="shutdown",
                stage="SKETCH",
                trace_id="",
            )

    def test_reason_can_be_any_nonempty_string(self):
        """Reason is free-form -- no enum validation at dataclass level."""
        from k1.planner.events import PlanCancelledPayload

        p = PlanCancelledPayload(
            request_id="r1",
            reason="custom_reason",
            stage="EXPAND",
            trace_id="t1",
        )
        assert p.reason == "custom_reason"


class TestPlanCancelledPayloadInAll:
    """PlanCancelledPayload is in events.py __all__."""

    def test_in_module_all(self):
        from k1.planner import events

        assert "PlanCancelledPayload" in events.__all__

    def test_in_package_all(self):
        import k1.planner

        assert "PlanCancelledPayload" in k1.planner.__all__


# ===================================================================
# 1.5.4 -- micro_replan.ready event schema
# ===================================================================


class TestMicroReplanReadyTopicConstant:
    """TOPIC_MICRO_REPLAN_READY matches SS28.1 exactly."""

    def test_topic_string_exact_value(self):
        from k1.planner.events import TOPIC_MICRO_REPLAN_READY

        assert TOPIC_MICRO_REPLAN_READY == "k1.planner.micro_replan.ready.v1"

    def test_topic_is_str_not_enum(self):
        from k1.planner.events import TOPIC_MICRO_REPLAN_READY

        assert type(TOPIC_MICRO_REPLAN_READY) is str

    def test_topic_importable_from_package_init(self):
        from k1.planner import TOPIC_MICRO_REPLAN_READY

        assert TOPIC_MICRO_REPLAN_READY == "k1.planner.micro_replan.ready.v1"


class TestMicroReplanReadyPayload:
    """micro_replan.ready uses CommittedPlan directly -- same type as plan.ready
    but on a distinct topic (SS28.1)."""

    def test_payload_is_committed_plan(self):
        """Same payload type as plan.ready -- no separate wrapper."""
        from k1.orchestrator.types import CommittedPlan

        assert dataclasses.is_dataclass(CommittedPlan)

    def test_no_micro_replan_wrapper_dataclass(self):
        """No MicroReplanReadyPayload wrapper exists in events.py."""
        import k1.planner.events as events_mod

        names = [n for n in dir(events_mod) if "MicroReplan" in n and "Payload" in n]
        assert names == [], f"Unexpected wrapper found: {names}"

    def test_topic_distinct_from_plan_ready(self):
        from k1.planner.events import TOPIC_MICRO_REPLAN_READY, TOPIC_PLAN_READY

        assert TOPIC_MICRO_REPLAN_READY != TOPIC_PLAN_READY

    def test_micro_replan_topic_starts_with_k1_planner(self):
        from k1.planner.events import TOPIC_MICRO_REPLAN_READY

        assert TOPIC_MICRO_REPLAN_READY.startswith("k1.planner.")

    def test_committed_plan_usable_as_micro_replan_payload(self):
        """CommittedPlan can carry replacement steps for micro-replan.
        SS28.1: 'Partial CommittedPlan (replacement steps only)'
        -- same type, just fewer steps."""
        from k1.orchestrator.types import CommittedPlan, PlanStep

        replacement = PlanStep(id="s-new", capability="search_web")
        plan = CommittedPlan(
            plan_id="mp1",
            request_id="r-micro",
            intent="fix step 3",
            steps=[replacement],
            trace_id="t-micro",
        )
        assert len(plan.steps) == 1
        assert plan.steps[0].id == "s-new"


class TestMicroReplanReadyTopicInAll:
    """TOPIC_MICRO_REPLAN_READY is in events.py __all__."""

    def test_in_module_all(self):
        from k1.planner import events

        assert "TOPIC_MICRO_REPLAN_READY" in events.__all__

    def test_in_package_all(self):
        import k1.planner

        assert "TOPIC_MICRO_REPLAN_READY" in k1.planner.__all__


# ===================================================================
# Cross-cutting: topic string exact matches (SS28.1 completeness)
# ===================================================================


class TestTopicStringsMatchSS28:
    """All 4 topics in scope (1.5.1-1.5.4) match SS28.1 table exactly."""

    def test_plan_ready_exact(self):
        from k1.planner.events import TOPIC_PLAN_READY

        assert TOPIC_PLAN_READY == "k1.planner.plan.ready.v1"

    def test_plan_failed_exact(self):
        from k1.planner.events import TOPIC_PLAN_FAILED

        assert TOPIC_PLAN_FAILED == "k1.planner.plan.failed.v1"

    def test_plan_cancelled_exact(self):
        from k1.planner.events import TOPIC_PLAN_CANCELLED

        assert TOPIC_PLAN_CANCELLED == "k1.planner.plan.cancelled.v1"

    def test_micro_replan_ready_exact(self):
        from k1.planner.events import TOPIC_MICRO_REPLAN_READY

        assert TOPIC_MICRO_REPLAN_READY == "k1.planner.micro_replan.ready.v1"

    def test_four_topics_unique(self):
        from k1.planner.events import (
            TOPIC_MICRO_REPLAN_READY,
            TOPIC_PLAN_CANCELLED,
            TOPIC_PLAN_FAILED,
            TOPIC_PLAN_READY,
        )

        topics = [
            TOPIC_PLAN_READY,
            TOPIC_PLAN_FAILED,
            TOPIC_PLAN_CANCELLED,
            TOPIC_MICRO_REPLAN_READY,
        ]
        assert len(topics) == len(set(topics))

    def test_all_follow_versioned_namespace(self):
        """All Planner lifecycle topics follow k1.planner.*.v1 pattern."""
        from k1.planner.events import (
            TOPIC_MICRO_REPLAN_READY,
            TOPIC_PLAN_CANCELLED,
            TOPIC_PLAN_FAILED,
            TOPIC_PLAN_READY,
        )

        for topic in [
            TOPIC_PLAN_READY,
            TOPIC_PLAN_FAILED,
            TOPIC_PLAN_CANCELLED,
            TOPIC_MICRO_REPLAN_READY,
        ]:
            assert topic.startswith("k1.planner."), f"Bad prefix: {topic}"
            assert topic.endswith(".v1"), f"Missing version suffix: {topic}"


# ===================================================================
# Cross-cutting: events.py Layer 0 import rule
# ===================================================================


class TestEventsLayer0ImportRule:
    """events.py imports ONLY from stdlib -- Layer 0 (SS30.6)."""

    def test_no_port_imports(self):
        """events.py must not import from any port module."""
        import ast
        import pathlib

        src = pathlib.Path("k1/planner/events.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert (
                        "ports" not in node.module
                    ), f"events.py imports from ports: {node.module}"
                    assert (
                        "service" not in node.module.lower()
                    ), f"events.py imports from service: {node.module}"
                    assert (
                        "adapter" not in node.module.lower()
                    ), f"events.py imports from adapter: {node.module}"

    def test_no_io_in_module(self):
        """events.py must have no I/O, subscriptions, or emission logic."""
        import pathlib

        src = pathlib.Path("k1/planner/events.py").read_text()
        for forbidden in ["async def", "await ", "socket", "open("]:
            assert forbidden not in src, f"events.py contains forbidden pattern: {forbidden}"
