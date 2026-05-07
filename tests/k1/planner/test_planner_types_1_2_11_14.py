"""Tests for Epic 1.2 issues 1.2.11-1.2.14.

Coverage:
- 1.2.11: events.py -- topic constants + payload dataclasses
- 1.2.12: types.py  -- RequestConstraints, TokenUsageRecord
- 1.2.13: config.py -- PlannerConfig
- 1.2.14: types.py  -- PlannerError hierarchy
"""

from __future__ import annotations

import dataclasses

import pytest

# ===================================================================
# 1.2.11 -- events.py topic constants + payload dataclasses
# ===================================================================


class TestTopicConstants:
    """Topic constants are plain strings matching k1.* namespace.

    E5 (HIL Unification): TOPIC_HIL_* topics were removed; the planner
    now consumes the unified ``IHILPort`` adapter directly. Only plan
    lifecycle topics remain.
    """

    def test_published_topics_are_strings(self):
        from k1.planner.events import (
            TOPIC_DELTA,
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
            TOPIC_DELTA,
        ]:
            assert isinstance(topic, str)
            assert topic.startswith("k1.")

    def test_subscribed_topics_are_strings(self):
        from k1.planner.events import (
            TOPIC_PLAN_CANCEL,
            TOPIC_PLAN_REQUEST,
        )

        for topic in [
            TOPIC_PLAN_REQUEST,
            TOPIC_PLAN_CANCEL,
        ]:
            assert isinstance(topic, str)
            assert topic.startswith("k1.")

    def test_all_topics_unique(self):
        from k1.planner.events import (
            TOPIC_DELTA,
            TOPIC_MICRO_REPLAN_READY,
            TOPIC_PLAN_CANCEL,
            TOPIC_PLAN_CANCELLED,
            TOPIC_PLAN_FAILED,
            TOPIC_PLAN_READY,
            TOPIC_PLAN_REQUEST,
        )

        topics = [
            TOPIC_PLAN_READY,
            TOPIC_PLAN_FAILED,
            TOPIC_PLAN_CANCELLED,
            TOPIC_MICRO_REPLAN_READY,
            TOPIC_DELTA,
            TOPIC_PLAN_REQUEST,
            TOPIC_PLAN_CANCEL,
        ]
        assert len(topics) == len(set(topics)), "Duplicate topic strings found"

    def test_topic_count(self):
        from k1.planner import events

        topic_attrs = [a for a in dir(events) if a.startswith("TOPIC_")]
        # E5: 5 published + 2 subscribed = 7 (HIL topics removed)
        assert len(topic_attrs) == 7

    def test_no_legacy_hil_topics(self):
        """E5: TOPIC_HIL_* constants must be deleted from planner.events."""
        from k1.planner import events

        for name in (
            "TOPIC_HIL_CLARIFICATION",
            "TOPIC_HIL_APPROVAL_REQ",
            "TOPIC_HIL_CLARIFICATION_RESP",
            "TOPIC_HIL_APPROVAL_RESP",
        ):
            assert not hasattr(events, name), f"{name} should be removed in E5"


class TestPlanFailedPayload:
    def test_valid_construction(self):
        from k1.planner.events import PlanFailedPayload

        p = PlanFailedPayload(
            request_id="r1",
            stage="SKETCH",
            error_code="E001",
            error_message="bad",
            tokens_used=100,
            duration_ms=500,
            trace_id="t1",
        )
        assert p.request_id == "r1"
        assert p.partial_state is None

    def test_frozen(self):
        from k1.planner.events import PlanFailedPayload

        p = PlanFailedPayload(
            request_id="r1",
            stage="SKETCH",
            error_code="E001",
            error_message="bad",
            tokens_used=100,
            duration_ms=500,
            trace_id="t1",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.request_id = "r2"

    def test_empty_request_id_raises(self):
        from k1.planner.events import PlanFailedPayload

        with pytest.raises(ValueError, match="request_id"):
            PlanFailedPayload(
                request_id="",
                stage="SKETCH",
                error_code="E001",
                error_message="bad",
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
                error_code="E001",
                error_message="bad",
                tokens_used=0,
                duration_ms=0,
                trace_id="",
            )


class TestPlanCancelledPayload:
    def test_valid_construction(self):
        from k1.planner.events import PlanCancelledPayload

        p = PlanCancelledPayload(request_id="r1", reason="user", stage="EXPAND", trace_id="t1")
        assert p.reason == "user"

    def test_frozen(self):
        from k1.planner.events import PlanCancelledPayload

        p = PlanCancelledPayload(request_id="r1", reason="user", stage="S", trace_id="t1")
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.reason = "other"

    def test_empty_stage_raises(self):
        from k1.planner.events import PlanCancelledPayload

        with pytest.raises(ValueError, match="stage"):
            PlanCancelledPayload(request_id="r1", reason="user", stage="", trace_id="t1")


class TestNoLegacyHILPayloads:
    """E5: HILClarificationPayload and HILApprovalRequestPayload deleted."""

    def test_clarification_payload_removed(self):
        from k1.planner import events

        assert not hasattr(events, "HILClarificationPayload")

    def test_approval_payload_removed(self):
        from k1.planner import events

        assert not hasattr(events, "HILApprovalRequestPayload")


# ===================================================================
# 1.2.12 -- RequestConstraints + TokenUsageRecord
# ===================================================================


class TestRequestConstraints:
    def test_valid_construction(self):
        from k1.planner.types import RequestConstraints

        rc = RequestConstraints(max_tokens=2000, timeout_ms=8000)
        assert rc.priority == "INTERACTIVE"
        assert rc.consumer_id == "planner"
        assert rc.temperature == 0.7

    def test_frozen(self):
        from k1.planner.types import RequestConstraints

        rc = RequestConstraints(max_tokens=2000, timeout_ms=8000)
        with pytest.raises(dataclasses.FrozenInstanceError):
            rc.max_tokens = 1000

    def test_max_tokens_zero_raises(self):
        from k1.planner.types import RequestConstraints

        with pytest.raises(ValueError, match="max_tokens"):
            RequestConstraints(max_tokens=0, timeout_ms=8000)

    def test_timeout_negative_raises(self):
        from k1.planner.types import RequestConstraints

        with pytest.raises(ValueError, match="timeout_ms"):
            RequestConstraints(max_tokens=100, timeout_ms=-1)

    def test_temperature_above_one_raises(self):
        from k1.planner.types import RequestConstraints

        with pytest.raises(ValueError, match="temperature"):
            RequestConstraints(max_tokens=100, timeout_ms=100, temperature=1.5)

    def test_empty_priority_raises(self):
        from k1.planner.types import RequestConstraints

        with pytest.raises(ValueError, match="priority"):
            RequestConstraints(max_tokens=100, timeout_ms=100, priority="")

    def test_empty_consumer_id_raises(self):
        from k1.planner.types import RequestConstraints

        with pytest.raises(ValueError, match="consumer_id"):
            RequestConstraints(max_tokens=100, timeout_ms=100, consumer_id="")

    def test_five_fields(self):
        from k1.planner.types import RequestConstraints

        fields = {f.name for f in dataclasses.fields(RequestConstraints)}
        assert fields == {"max_tokens", "timeout_ms", "priority", "temperature", "consumer_id"}


class TestTokenUsageRecord:
    def test_valid_construction(self):
        from k1.planner.types import TokenUsageRecord

        t = TokenUsageRecord(stage="SKETCH")
        assert t.prompt_tokens == 0
        assert t.completion_tokens == 0
        assert t.total_tokens == 0

    def test_mutable(self):
        from k1.planner.types import TokenUsageRecord

        t = TokenUsageRecord(stage="SKETCH")
        t.prompt_tokens = 100
        t.completion_tokens = 50
        t.total_tokens = 150
        assert t.total_tokens == 150

    def test_empty_stage_raises(self):
        from k1.planner.types import TokenUsageRecord

        with pytest.raises(ValueError, match="stage"):
            TokenUsageRecord(stage="")

    def test_negative_prompt_tokens_raises(self):
        from k1.planner.types import TokenUsageRecord

        with pytest.raises(ValueError, match="prompt_tokens"):
            TokenUsageRecord(stage="SKETCH", prompt_tokens=-1)

    def test_negative_completion_tokens_raises(self):
        from k1.planner.types import TokenUsageRecord

        with pytest.raises(ValueError, match="completion_tokens"):
            TokenUsageRecord(stage="SKETCH", completion_tokens=-1)

    def test_negative_total_tokens_raises(self):
        from k1.planner.types import TokenUsageRecord

        with pytest.raises(ValueError, match="total_tokens"):
            TokenUsageRecord(stage="SKETCH", total_tokens=-1)


# ===================================================================
# 1.2.13 -- PlannerConfig
# ===================================================================


class TestPlannerConfig:
    def test_defaults_valid(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig()
        assert cfg.mailbox_max_depth == 5
        assert cfg.pipeline_timeout_ms == 45_000
        assert cfg.sketch_timeout_ms == 8_000
        assert cfg.expand_timeout_ms == 5_000
        assert cfg.validate_timeout_ms == 3_000
        assert cfg.commit_timeout_ms == 1_000
        assert cfg.sketch_max_tokens == 2_000
        assert cfg.expand_max_tokens == 1_000
        assert cfg.validate_max_tokens == 500
        assert cfg.total_token_budget == 3_500
        assert cfg.sketch_temperature == 0.7
        assert cfg.expand_temperature == 0.3
        assert cfg.validate_temperature == 0.2
        assert cfg.max_tool_calls_per_plan == 6
        assert cfg.max_hil_rounds == 2
        assert cfg.hil_clarification_timeout_ms == 60_000
        assert cfg.hil_approval_timeout_ms == 120_000
        assert cfg.micro_replan_timeout_ms == 10_000
        assert cfg.micro_replan_max_tokens == 2_000
        assert cfg.shutdown_grace_period_ms == 5_000

    def test_frozen(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.mailbox_max_depth = 10

    def test_field_count(self):
        from k1.planner.config import PlannerConfig

        assert len(dataclasses.fields(PlannerConfig)) == 26

    def test_from_dict_override(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig.from_dict({"mailbox_max_depth": 10})
        assert cfg.mailbox_max_depth == 10
        assert cfg.pipeline_timeout_ms == 45_000  # unchanged

    def test_from_dict_empty(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig.from_dict({})
        assert cfg == PlannerConfig()

    def test_from_dict_unknown_key_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="Unknown"):
            PlannerConfig.from_dict({"nonexistent_field": 42})

    def test_mailbox_zero_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="mailbox_max_depth"):
            PlannerConfig(mailbox_max_depth=0)

    def test_timeout_zero_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="pipeline_timeout_ms"):
            PlannerConfig(pipeline_timeout_ms=0)

    def test_temperature_above_two_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="sketch_temperature"):
            PlannerConfig(sketch_temperature=2.1)

    def test_temperature_below_zero_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="expand_temperature"):
            PlannerConfig(expand_temperature=-0.1)

    def test_total_budget_less_than_per_stage_sum_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="total_token_budget"):
            PlannerConfig(total_token_budget=100)

    def test_max_tool_calls_zero_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="max_tool_calls_per_plan"):
            PlannerConfig(max_tool_calls_per_plan=0)

    def test_hil_rounds_negative_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="max_hil_rounds"):
            PlannerConfig(max_hil_rounds=-1)

    def test_token_budget_zero_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="sketch_max_tokens"):
            PlannerConfig(sketch_max_tokens=0, total_token_budget=500)


# ===================================================================
# 1.2.14 -- PlannerError hierarchy
# ===================================================================


class TestPlannerError:
    def test_base_attributes(self):
        from k1.planner.types import PlannerError

        e = PlannerError("boom", stage="SKETCH", request_id="r1", trace_id="t1")
        assert str(e) == "boom"
        assert e.stage == "SKETCH"
        assert e.request_id == "r1"
        assert e.trace_id == "t1"

    def test_is_exception(self):
        from k1.planner.types import PlannerError

        assert issubclass(PlannerError, Exception)

    def test_defaults(self):
        from k1.planner.types import PlannerError

        e = PlannerError("msg")
        assert e.stage == ""
        assert e.request_id == ""
        assert e.trace_id == ""


class TestPlannerErrorSubclasses:
    @pytest.mark.parametrize(
        "cls_name",
        [
            "SketchFailedError",
            "ExpandFailedError",
            "ValidateRejectedError",
            "CommitFailedError",
            "BudgetExhaustedError",
            "MailboxFullError",
            "PlanCancelledError",
            "HILTimeoutError",
        ],
    )
    def test_subclass_of_planner_error(self, cls_name):
        import k1.planner.types as mod

        cls = getattr(mod, cls_name)
        from k1.planner.types import PlannerError

        assert issubclass(cls, PlannerError)

    @pytest.mark.parametrize(
        "cls_name",
        [
            "SketchFailedError",
            "ExpandFailedError",
            "ValidateRejectedError",
            "CommitFailedError",
            "BudgetExhaustedError",
            "MailboxFullError",
            "PlanCancelledError",
            "HILTimeoutError",
        ],
    )
    def test_subclass_inherits_attributes(self, cls_name):
        import k1.planner.types as mod

        cls = getattr(mod, cls_name)
        e = cls("fail", stage="VALIDATE", request_id="r2", trace_id="t2")
        assert str(e) == "fail"
        assert e.stage == "VALIDATE"
        assert e.request_id == "r2"
        assert e.trace_id == "t2"

    @pytest.mark.parametrize(
        "cls_name",
        [
            "SketchFailedError",
            "ExpandFailedError",
            "ValidateRejectedError",
            "CommitFailedError",
            "BudgetExhaustedError",
            "MailboxFullError",
            "PlanCancelledError",
            "HILTimeoutError",
        ],
    )
    def test_subclass_catchable_as_base(self, cls_name):
        import k1.planner.types as mod

        cls = getattr(mod, cls_name)
        from k1.planner.types import PlannerError

        with pytest.raises(PlannerError):
            raise cls("catchable")

    def test_eight_subclasses_count(self):
        import k1.planner.types as mod
        from k1.planner.types import PlannerError

        subclasses = [
            name
            for name in dir(mod)
            if (
                isinstance(getattr(mod, name), type)
                and issubclass(getattr(mod, name), PlannerError)
                and getattr(mod, name) is not PlannerError
            )
        ]
        assert len(subclasses) == 18


# ===================================================================
# __init__.py re-export validation
# ===================================================================


class TestInitReExports:
    """All public types importable from k1.planner."""

    def test_types_from_init(self):
        from k1.planner import PlannerError, RequestConstraints, TokenUsageRecord

        assert RequestConstraints is not None
        assert TokenUsageRecord is not None
        assert PlannerError is not None

    def test_events_from_init(self):
        from k1.planner import TOPIC_PLAN_READY

        assert TOPIC_PLAN_READY is not None

    def test_config_from_init(self):
        from k1.planner import PlannerConfig

        cfg = PlannerConfig()
        assert cfg.mailbox_max_depth == 5
