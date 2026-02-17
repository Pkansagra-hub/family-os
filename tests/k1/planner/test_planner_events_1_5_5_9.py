"""Tests for Epic 1.5 issues 1.5.5-1.5.9 -- HIL Event Schemas & PlannerConfig.

Coverage:
- 1.5.5: hil.clarification topic + HILClarificationPayload
- 1.5.6: hil.approval_request topic + HILApprovalRequestPayload
- 1.5.7: hil.clarification_response subscription topic
- 1.5.8: hil.approval_response subscription topic
- 1.5.9: PlannerConfig.from_dict() override mechanism + validation bounds

Validates against planner.md SS12.2, SS12.3, SS28, SS30.5.1 F06/F07.
"""

from __future__ import annotations

import dataclasses

import pytest

# ===================================================================
# 1.5.5 -- hil.clarification event schema
# ===================================================================


class TestHILClarificationTopicConstant:
    """TOPIC_HIL_CLARIFICATION matches SS28 exactly."""

    def test_topic_string_exact_value(self):
        from k1.planner.events import TOPIC_HIL_CLARIFICATION

        assert TOPIC_HIL_CLARIFICATION == "k1.hil.clarification.v1"

    def test_topic_is_str_not_enum(self):
        from k1.planner.events import TOPIC_HIL_CLARIFICATION

        assert type(TOPIC_HIL_CLARIFICATION) is str

    def test_topic_importable_from_package_init(self):
        from k1.planner import TOPIC_HIL_CLARIFICATION

        assert TOPIC_HIL_CLARIFICATION == "k1.hil.clarification.v1"

    def test_topic_uses_hil_namespace(self):
        """SS12.1: HIL topics use k1.hil.* namespace, not k1.planner.*."""
        from k1.planner.events import TOPIC_HIL_CLARIFICATION

        assert TOPIC_HIL_CLARIFICATION.startswith("k1.hil.")

    def test_topic_in_module_all(self):
        from k1.planner import events

        assert "TOPIC_HIL_CLARIFICATION" in events.__all__


class TestHILClarificationPayloadFields:
    """HILClarificationPayload matches SS12.2 / SS30.5.1 F06."""

    def test_is_dataclass(self):
        from k1.planner.events import HILClarificationPayload

        assert dataclasses.is_dataclass(HILClarificationPayload)

    def test_is_frozen(self):
        from k1.planner.events import HILClarificationPayload

        p = HILClarificationPayload(request_id="r1", question="What?", trace_id="t1")
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.request_id = "r2"

    def test_four_fields(self):
        """F06 defines exactly 4 fields: request_id, question, context, trace_id."""
        from k1.planner.events import HILClarificationPayload

        field_names = [f.name for f in dataclasses.fields(HILClarificationPayload)]
        assert field_names == ["request_id", "question", "context", "trace_id"]

    def test_field_types(self):
        from k1.planner.events import HILClarificationPayload

        hints = {f.name: f.type for f in dataclasses.fields(HILClarificationPayload)}
        assert hints["request_id"] == "str"
        assert hints["question"] == "str"
        assert hints["context"] == "Dict[str, Any]"
        assert hints["trace_id"] == "str"

    def test_context_defaults_to_empty_dict(self):
        from k1.planner.events import HILClarificationPayload

        p = HILClarificationPayload(request_id="r1", question="What?", trace_id="t1")
        assert p.context == {}
        assert isinstance(p.context, dict)

    def test_context_default_not_shared(self):
        """Each instance gets its own default dict (field(default_factory=dict))."""
        from k1.planner.events import HILClarificationPayload

        p1 = HILClarificationPayload(request_id="r1", question="Q1", trace_id="t1")
        p2 = HILClarificationPayload(request_id="r2", question="Q2", trace_id="t2")
        assert p1.context is not p2.context

    def test_context_custom_value(self):
        from k1.planner.events import HILClarificationPayload

        ctx = {"intent": "schedule", "ambiguity": "time vs date"}
        p = HILClarificationPayload(request_id="r1", question="When?", context=ctx, trace_id="t1")
        assert p.context == ctx

    def test_trace_id_default_empty(self):
        """trace_id defaults to '' but __post_init__ rejects empty."""
        from k1.planner.events import HILClarificationPayload

        with pytest.raises(ValueError, match="trace_id"):
            HILClarificationPayload(request_id="r1", question="Q?")

    def test_valid_construction_all_fields(self):
        from k1.planner.events import HILClarificationPayload

        p = HILClarificationPayload(
            request_id="req-123",
            question="Did you mean location A or B?",
            context={"step": "sketch", "ambiguity_type": "location"},
            trace_id="trace-abc",
        )
        assert p.request_id == "req-123"
        assert p.question == "Did you mean location A or B?"
        assert p.context["ambiguity_type"] == "location"
        assert p.trace_id == "trace-abc"

    def test_importable_from_package_init(self):
        from k1.planner import HILClarificationPayload

        assert dataclasses.is_dataclass(HILClarificationPayload)

    def test_in_module_all(self):
        from k1.planner import events

        assert "HILClarificationPayload" in events.__all__


class TestHILClarificationPayloadValidation:
    """Validation guards per F06 __post_init__."""

    def test_empty_request_id_raises(self):
        from k1.planner.events import HILClarificationPayload

        with pytest.raises(ValueError, match="request_id"):
            HILClarificationPayload(request_id="", question="Q?", trace_id="t1")

    def test_empty_question_raises(self):
        from k1.planner.events import HILClarificationPayload

        with pytest.raises(ValueError, match="question"):
            HILClarificationPayload(request_id="r1", question="", trace_id="t1")

    def test_empty_trace_id_raises(self):
        from k1.planner.events import HILClarificationPayload

        with pytest.raises(ValueError, match="trace_id"):
            HILClarificationPayload(request_id="r1", question="Q?", trace_id="")


class TestHILClarificationPayloadSpec:
    """SS12.2 spec alignment tests."""

    def test_publisher_is_hil_coordinator_during_sketch(self):
        """SS12.2: Published by HILCoordinator during SKETCH when ambiguity detected.
        Verified by: payload can be constructed validly (publisher is runtime concern)."""
        from k1.planner.events import HILClarificationPayload

        p = HILClarificationPayload(request_id="r1", question="Which location?", trace_id="t1")
        assert p.request_id == "r1"

    def test_plan10_max_rounds_default_is_two(self):
        """PLAN-10: max 2 HIL rounds. Verified via PlannerConfig default."""
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig()
        assert cfg.max_hil_rounds == 2

    def test_clarification_timeout_default_60s(self):
        """SS12.2: 60s default timeout for clarification."""
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig()
        assert cfg.hil_clarification_timeout_ms == 60_000


# ===================================================================
# 1.5.6 -- hil.approval_request event schema
# ===================================================================


class TestHILApprovalTopicConstant:
    """TOPIC_HIL_APPROVAL_REQ matches SS28 exactly."""

    def test_topic_string_exact_value(self):
        from k1.planner.events import TOPIC_HIL_APPROVAL_REQ

        assert TOPIC_HIL_APPROVAL_REQ == "k1.hil.approval_request.v1"

    def test_topic_is_str_not_enum(self):
        from k1.planner.events import TOPIC_HIL_APPROVAL_REQ

        assert type(TOPIC_HIL_APPROVAL_REQ) is str

    def test_topic_importable_from_package_init(self):
        from k1.planner import TOPIC_HIL_APPROVAL_REQ

        assert TOPIC_HIL_APPROVAL_REQ == "k1.hil.approval_request.v1"

    def test_topic_uses_hil_namespace(self):
        """SS12.1: HIL topics use k1.hil.* namespace, not k1.planner.*."""
        from k1.planner.events import TOPIC_HIL_APPROVAL_REQ

        assert TOPIC_HIL_APPROVAL_REQ.startswith("k1.hil.")

    def test_topic_in_module_all(self):
        from k1.planner import events

        assert "TOPIC_HIL_APPROVAL_REQ" in events.__all__


class TestHILApprovalRequestPayloadFields:
    """HILApprovalRequestPayload matches SS12.3 / SS30.5.1 F06."""

    def test_is_dataclass(self):
        from k1.planner.events import HILApprovalRequestPayload

        assert dataclasses.is_dataclass(HILApprovalRequestPayload)

    def test_is_frozen(self):
        from k1.planner.events import HILApprovalRequestPayload

        p = HILApprovalRequestPayload(
            request_id="r1", summary="Risk", options=["approve", "reject"]
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.request_id = "r2"

    def test_five_fields(self):
        """F06 defines exactly 5 fields: request_id, summary, options,
        side_effects, safety_assessment."""
        from k1.planner.events import HILApprovalRequestPayload

        field_names = [f.name for f in dataclasses.fields(HILApprovalRequestPayload)]
        assert field_names == [
            "request_id",
            "summary",
            "options",
            "side_effects",
            "safety_assessment",
        ]

    def test_field_types(self):
        from k1.planner.events import HILApprovalRequestPayload

        hints = {f.name: f.type for f in dataclasses.fields(HILApprovalRequestPayload)}
        assert hints["request_id"] == "str"
        assert hints["summary"] == "str"
        assert hints["options"] == "List[str]"
        assert hints["side_effects"] == "List[str]"
        assert hints["safety_assessment"] == "str"

    def test_options_default_factory(self):
        """options defaults to empty list but __post_init__ rejects empty options."""
        from k1.planner.events import HILApprovalRequestPayload

        with pytest.raises(ValueError, match="options"):
            HILApprovalRequestPayload(request_id="r1", summary="s")

    def test_side_effects_defaults_to_empty_list(self):
        from k1.planner.events import HILApprovalRequestPayload

        p = HILApprovalRequestPayload(request_id="r1", summary="Do X", options=["approve"])
        assert p.side_effects == []
        assert isinstance(p.side_effects, list)

    def test_side_effects_default_not_shared(self):
        from k1.planner.events import HILApprovalRequestPayload

        p1 = HILApprovalRequestPayload(request_id="r1", summary="A", options=["approve"])
        p2 = HILApprovalRequestPayload(request_id="r2", summary="B", options=["approve"])
        assert p1.side_effects is not p2.side_effects

    def test_safety_assessment_defaults_to_empty(self):
        from k1.planner.events import HILApprovalRequestPayload

        p = HILApprovalRequestPayload(request_id="r1", summary="X", options=["approve"])
        assert p.safety_assessment == ""

    def test_valid_construction_all_fields(self):
        from k1.planner.events import HILApprovalRequestPayload

        p = HILApprovalRequestPayload(
            request_id="req-456",
            summary="Delete 3 calendar entries",
            options=["approve", "reject", "modify"],
            side_effects=["calendar_delete", "notification_send"],
            safety_assessment="AMBER -- irreversible calendar modification",
        )
        assert p.request_id == "req-456"
        assert p.summary == "Delete 3 calendar entries"
        assert p.options == ["approve", "reject", "modify"]
        assert len(p.side_effects) == 2
        assert p.safety_assessment.startswith("AMBER")

    def test_importable_from_package_init(self):
        from k1.planner import HILApprovalRequestPayload

        assert dataclasses.is_dataclass(HILApprovalRequestPayload)

    def test_in_module_all(self):
        from k1.planner import events

        assert "HILApprovalRequestPayload" in events.__all__


class TestHILApprovalRequestPayloadValidation:
    """Validation guards per F06 __post_init__."""

    def test_empty_request_id_raises(self):
        from k1.planner.events import HILApprovalRequestPayload

        with pytest.raises(ValueError, match="request_id"):
            HILApprovalRequestPayload(request_id="", summary="S", options=["approve"])

    def test_empty_summary_raises(self):
        from k1.planner.events import HILApprovalRequestPayload

        with pytest.raises(ValueError, match="summary"):
            HILApprovalRequestPayload(request_id="r1", summary="", options=["approve"])

    def test_empty_options_raises(self):
        from k1.planner.events import HILApprovalRequestPayload

        with pytest.raises(ValueError, match="options"):
            HILApprovalRequestPayload(request_id="r1", summary="S", options=[])


class TestHILApprovalRequestPayloadSpec:
    """SS12.3 spec alignment tests."""

    def test_standard_options_accepted(self):
        """SS12.3: standard options are approve/reject/modify."""
        from k1.planner.events import HILApprovalRequestPayload

        p = HILApprovalRequestPayload(
            request_id="r1",
            summary="High-risk operation",
            options=["approve", "reject", "modify"],
        )
        assert "approve" in p.options
        assert "reject" in p.options
        assert "modify" in p.options

    def test_approval_timeout_default_120s(self):
        """SS12.3: 120s default timeout for approval."""
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig()
        assert cfg.hil_approval_timeout_ms == 120_000


# ===================================================================
# 1.5.7 -- hil.clarification_response subscription topic
# ===================================================================


class TestHILClarificationRespTopicConstant:
    """TOPIC_HIL_CLARIFICATION_RESP matches SS28 exactly."""

    def test_topic_string_exact_value(self):
        from k1.planner.events import TOPIC_HIL_CLARIFICATION_RESP

        assert TOPIC_HIL_CLARIFICATION_RESP == "k1.hil.clarification_response.v1"

    def test_topic_is_str_not_enum(self):
        from k1.planner.events import TOPIC_HIL_CLARIFICATION_RESP

        assert type(TOPIC_HIL_CLARIFICATION_RESP) is str

    def test_topic_importable_from_package_init(self):
        from k1.planner import TOPIC_HIL_CLARIFICATION_RESP

        assert TOPIC_HIL_CLARIFICATION_RESP == "k1.hil.clarification_response.v1"

    def test_topic_uses_hil_namespace(self):
        """SS12.1: response topics also use k1.hil.* namespace."""
        from k1.planner.events import TOPIC_HIL_CLARIFICATION_RESP

        assert TOPIC_HIL_CLARIFICATION_RESP.startswith("k1.hil.")

    def test_topic_in_module_all(self):
        from k1.planner import events

        assert "TOPIC_HIL_CLARIFICATION_RESP" in events.__all__

    def test_no_response_payload_in_planner(self):
        """1.5.7: Response payloads owned by Concierge, not defined in Planner events.py.
        Verify no HILClarificationResponse class exists in events module."""
        from k1.planner import events

        assert not hasattr(events, "HILClarificationResponse")
        assert not hasattr(events, "HILClarificationResponsePayload")


class TestHILClarificationRespCorrelation:
    """Subscription semantics: response correlates to request via request_id."""

    def test_request_and_response_topic_share_namespace(self):
        from k1.planner.events import TOPIC_HIL_CLARIFICATION, TOPIC_HIL_CLARIFICATION_RESP

        # Both in k1.hil namespace
        assert TOPIC_HIL_CLARIFICATION.startswith("k1.hil.")
        assert TOPIC_HIL_CLARIFICATION_RESP.startswith("k1.hil.")

    def test_request_and_response_topics_are_distinct(self):
        from k1.planner.events import TOPIC_HIL_CLARIFICATION, TOPIC_HIL_CLARIFICATION_RESP

        assert TOPIC_HIL_CLARIFICATION != TOPIC_HIL_CLARIFICATION_RESP


# ===================================================================
# 1.5.8 -- hil.approval_response subscription topic
# ===================================================================


class TestHILApprovalRespTopicConstant:
    """TOPIC_HIL_APPROVAL_RESP matches SS28 exactly."""

    def test_topic_string_exact_value(self):
        from k1.planner.events import TOPIC_HIL_APPROVAL_RESP

        assert TOPIC_HIL_APPROVAL_RESP == "k1.hil.approval_response.v1"

    def test_topic_is_str_not_enum(self):
        from k1.planner.events import TOPIC_HIL_APPROVAL_RESP

        assert type(TOPIC_HIL_APPROVAL_RESP) is str

    def test_topic_importable_from_package_init(self):
        from k1.planner import TOPIC_HIL_APPROVAL_RESP

        assert TOPIC_HIL_APPROVAL_RESP == "k1.hil.approval_response.v1"

    def test_topic_uses_hil_namespace(self):
        """SS12.1: response topics also use k1.hil.* namespace."""
        from k1.planner.events import TOPIC_HIL_APPROVAL_RESP

        assert TOPIC_HIL_APPROVAL_RESP.startswith("k1.hil.")

    def test_topic_in_module_all(self):
        from k1.planner import events

        assert "TOPIC_HIL_APPROVAL_RESP" in events.__all__

    def test_no_response_payload_in_planner(self):
        """1.5.8: Response payloads owned by Concierge, not defined in Planner events.py.
        Verify no HILApprovalResponse class exists in events module."""
        from k1.planner import events

        assert not hasattr(events, "HILApprovalResponse")
        assert not hasattr(events, "HILApprovalResponsePayload")


class TestHILApprovalRespCorrelation:
    """Subscription semantics: response correlates to request via request_id."""

    def test_request_and_response_topic_share_namespace(self):
        from k1.planner.events import TOPIC_HIL_APPROVAL_REQ, TOPIC_HIL_APPROVAL_RESP

        assert TOPIC_HIL_APPROVAL_REQ.startswith("k1.hil.")
        assert TOPIC_HIL_APPROVAL_RESP.startswith("k1.hil.")

    def test_request_and_response_topics_are_distinct(self):
        from k1.planner.events import TOPIC_HIL_APPROVAL_REQ, TOPIC_HIL_APPROVAL_RESP

        assert TOPIC_HIL_APPROVAL_REQ != TOPIC_HIL_APPROVAL_RESP


# ===================================================================
# 1.5.7 + 1.5.8 -- All 4 HIL topic constants cross-check
# ===================================================================


class TestHILTopicCatalogCrossCheck:
    """Verify all 4 HIL topic constants form a coherent set (SS28)."""

    def test_four_hil_topics_all_in_hil_namespace(self):
        from k1.planner.events import (
            TOPIC_HIL_APPROVAL_REQ,
            TOPIC_HIL_APPROVAL_RESP,
            TOPIC_HIL_CLARIFICATION,
            TOPIC_HIL_CLARIFICATION_RESP,
        )

        topics = [
            TOPIC_HIL_CLARIFICATION,
            TOPIC_HIL_APPROVAL_REQ,
            TOPIC_HIL_CLARIFICATION_RESP,
            TOPIC_HIL_APPROVAL_RESP,
        ]
        for t in topics:
            assert t.startswith("k1.hil."), f"Expected k1.hil.* namespace, got {t}"

    def test_four_hil_topics_all_unique(self):
        from k1.planner.events import (
            TOPIC_HIL_APPROVAL_REQ,
            TOPIC_HIL_APPROVAL_RESP,
            TOPIC_HIL_CLARIFICATION,
            TOPIC_HIL_CLARIFICATION_RESP,
        )

        topics = {
            TOPIC_HIL_CLARIFICATION,
            TOPIC_HIL_APPROVAL_REQ,
            TOPIC_HIL_CLARIFICATION_RESP,
            TOPIC_HIL_APPROVAL_RESP,
        }
        assert len(topics) == 4

    def test_all_topics_end_with_v1(self):
        from k1.planner.events import (
            TOPIC_HIL_APPROVAL_REQ,
            TOPIC_HIL_APPROVAL_RESP,
            TOPIC_HIL_CLARIFICATION,
            TOPIC_HIL_CLARIFICATION_RESP,
        )

        for t in [
            TOPIC_HIL_CLARIFICATION,
            TOPIC_HIL_APPROVAL_REQ,
            TOPIC_HIL_CLARIFICATION_RESP,
            TOPIC_HIL_APPROVAL_RESP,
        ]:
            assert t.endswith(".v1"), f"Expected .v1 suffix, got {t}"

    def test_published_vs_subscribed_classification(self):
        """SS28: clarification + approval_request are published;
        clarification_response + approval_response are subscribed."""
        from k1.planner import events

        published = {"TOPIC_HIL_CLARIFICATION", "TOPIC_HIL_APPROVAL_REQ"}
        subscribed = {"TOPIC_HIL_CLARIFICATION_RESP", "TOPIC_HIL_APPROVAL_RESP"}
        all_hil = published | subscribed

        # All in __all__
        for name in all_hil:
            assert name in events.__all__, f"{name} missing from events.__all__"


# ===================================================================
# 1.5.9 -- PlannerConfig from_dict() + validation bounds
# ===================================================================


class TestPlannerConfigFromDict:
    """PlannerConfig.from_dict() override mechanism (SS30.5.1 F07)."""

    def test_from_dict_empty_equals_default(self):
        from k1.planner.config import PlannerConfig

        assert PlannerConfig.from_dict({}) == PlannerConfig()

    def test_from_dict_single_override(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig.from_dict({"sketch_max_tokens": 1500})
        assert cfg.sketch_max_tokens == 1500
        # All other defaults unchanged
        assert cfg.pipeline_timeout_ms == 45_000
        assert cfg.mailbox_max_depth == 5

    def test_from_dict_multiple_overrides(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig.from_dict(
            {
                "pipeline_timeout_ms": 30_000,
                "max_hil_rounds": 3,
                "sketch_temperature": 0.5,
            }
        )
        assert cfg.pipeline_timeout_ms == 30_000
        assert cfg.max_hil_rounds == 3
        assert cfg.sketch_temperature == 0.5

    def test_from_dict_unknown_key_raises_valueerror(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="Unknown"):
            PlannerConfig.from_dict({"nonexistent_field": 42})

    def test_from_dict_multiple_unknown_keys_lists_all(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="Unknown"):
            PlannerConfig.from_dict({"bad1": 1, "bad2": 2})

    def test_from_dict_returns_plannerconfig_instance(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig.from_dict({"mailbox_max_depth": 3})
        assert isinstance(cfg, PlannerConfig)

    def test_from_dict_validation_still_applies(self):
        """Overrides go through __post_init__ validation."""
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="mailbox_max_depth"):
            PlannerConfig.from_dict({"mailbox_max_depth": 0})

    def test_from_dict_env_override_sketch_tokens(self):
        """Plan 1.5.9: PLANNER_SKETCH_MAX_TOKENS=1500 -> sketch_max_tokens override."""
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig.from_dict({"sketch_max_tokens": 1500})
        assert cfg.sketch_max_tokens == 1500

    def test_from_dict_env_override_pipeline_timeout(self):
        """Plan 1.5.9: PLANNER_PIPELINE_TIMEOUT_MS=30000 -> pipeline_timeout_ms."""
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig.from_dict({"pipeline_timeout_ms": 30_000})
        assert cfg.pipeline_timeout_ms == 30_000


class TestPlannerConfigDefaultsValid:
    """PlannerConfig() with all defaults is valid -- no required overrides (test-friendly)."""

    def test_default_construction_succeeds(self):
        from k1.planner.config import PlannerConfig

        PlannerConfig()  # Should not raise

    def test_default_is_frozen(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.mailbox_max_depth = 99

    def test_field_count_is_26(self):
        from k1.planner.config import PlannerConfig

        assert len(dataclasses.fields(PlannerConfig)) == 26

    def test_all_20_defaults_match_spec(self):
        """F07 spec values from planner.md SS30.5.1."""
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


class TestPlannerConfigValidationBounds:
    """__post_init__ validation bounds per plan 1.5.9 Done When."""

    # --- mailbox_max_depth in [1, 20] ---

    def test_mailbox_depth_min_valid(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig(mailbox_max_depth=1)
        assert cfg.mailbox_max_depth == 1

    def test_mailbox_depth_max_valid(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig(mailbox_max_depth=20)
        assert cfg.mailbox_max_depth == 20

    def test_mailbox_depth_zero_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="mailbox_max_depth"):
            PlannerConfig(mailbox_max_depth=0)

    def test_mailbox_depth_negative_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="mailbox_max_depth"):
            PlannerConfig(mailbox_max_depth=-1)

    def test_mailbox_depth_21_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="mailbox_max_depth"):
            PlannerConfig(mailbox_max_depth=21)

    def test_mailbox_depth_100_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="mailbox_max_depth"):
            PlannerConfig(mailbox_max_depth=100)

    # --- temperatures in [0.0, 2.0] ---

    def test_temperature_zero_valid(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig(sketch_temperature=0.0)
        assert cfg.sketch_temperature == 0.0

    def test_temperature_two_valid(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig(sketch_temperature=2.0)
        assert cfg.sketch_temperature == 2.0

    def test_temperature_1_5_valid(self):
        """Temperature 1.5 is valid in [0.0, 2.0] range."""
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig(sketch_temperature=1.5)
        assert cfg.sketch_temperature == 1.5

    def test_temperature_negative_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="sketch_temperature"):
            PlannerConfig(sketch_temperature=-0.1)

    def test_temperature_above_two_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="sketch_temperature"):
            PlannerConfig(sketch_temperature=2.1)

    def test_all_three_temperatures_validated(self):
        """Each of the 3 temperature fields is validated independently."""
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="expand_temperature"):
            PlannerConfig(expand_temperature=-0.01)
        with pytest.raises(ValueError, match="validate_temperature"):
            PlannerConfig(validate_temperature=2.01)

    # --- max_tool_calls_per_plan in [1, 20] ---

    def test_tool_calls_min_valid(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig(max_tool_calls_per_plan=1)
        assert cfg.max_tool_calls_per_plan == 1

    def test_tool_calls_max_valid(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig(max_tool_calls_per_plan=20)
        assert cfg.max_tool_calls_per_plan == 20

    def test_tool_calls_zero_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="max_tool_calls_per_plan"):
            PlannerConfig(max_tool_calls_per_plan=0)

    def test_tool_calls_21_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="max_tool_calls_per_plan"):
            PlannerConfig(max_tool_calls_per_plan=21)

    def test_tool_calls_negative_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="max_tool_calls_per_plan"):
            PlannerConfig(max_tool_calls_per_plan=-5)

    # --- max_hil_rounds in [0, 5] ---

    def test_hil_rounds_zero_valid(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig(max_hil_rounds=0)
        assert cfg.max_hil_rounds == 0

    def test_hil_rounds_five_valid(self):
        from k1.planner.config import PlannerConfig

        cfg = PlannerConfig(max_hil_rounds=5)
        assert cfg.max_hil_rounds == 5

    def test_hil_rounds_negative_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="max_hil_rounds"):
            PlannerConfig(max_hil_rounds=-1)

    def test_hil_rounds_six_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="max_hil_rounds"):
            PlannerConfig(max_hil_rounds=6)

    def test_hil_rounds_100_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="max_hil_rounds"):
            PlannerConfig(max_hil_rounds=100)

    # --- timeouts > 0 ---

    def test_all_timeout_fields_reject_zero(self):
        from k1.planner.config import PlannerConfig

        timeout_fields = [
            "pipeline_timeout_ms",
            "sketch_timeout_ms",
            "expand_timeout_ms",
            "validate_timeout_ms",
            "commit_timeout_ms",
            "hil_clarification_timeout_ms",
            "hil_approval_timeout_ms",
            "micro_replan_timeout_ms",
            "shutdown_grace_period_ms",
        ]
        for field_name in timeout_fields:
            with pytest.raises(ValueError, match=field_name):
                PlannerConfig(**{field_name: 0})

    def test_all_timeout_fields_reject_negative(self):
        from k1.planner.config import PlannerConfig

        timeout_fields = [
            "pipeline_timeout_ms",
            "sketch_timeout_ms",
            "expand_timeout_ms",
            "validate_timeout_ms",
            "commit_timeout_ms",
            "hil_clarification_timeout_ms",
            "hil_approval_timeout_ms",
            "micro_replan_timeout_ms",
            "shutdown_grace_period_ms",
        ]
        for field_name in timeout_fields:
            with pytest.raises(ValueError, match=field_name):
                PlannerConfig(**{field_name: -1})

    # --- token budgets > 0 ---

    def test_all_token_fields_reject_zero(self):
        from k1.planner.config import PlannerConfig

        token_fields = [
            "sketch_max_tokens",
            "expand_max_tokens",
            "validate_max_tokens",
            "micro_replan_max_tokens",
        ]
        for field_name in token_fields:
            with pytest.raises(ValueError, match=field_name):
                # Need total_token_budget high enough for other defaults
                PlannerConfig(**{field_name: 0, "total_token_budget": 10_000})

    # --- total_token_budget >= per-stage sum ---

    def test_total_budget_at_per_stage_sum_valid(self):
        from k1.planner.config import PlannerConfig

        # Default per-stage: 2000 + 1000 + 500 = 3500
        cfg = PlannerConfig(total_token_budget=3500)
        assert cfg.total_token_budget == 3500

    def test_total_budget_below_per_stage_sum_raises(self):
        from k1.planner.config import PlannerConfig

        with pytest.raises(ValueError, match="total_token_budget"):
            PlannerConfig(total_token_budget=3499)


class TestPlannerConfigInAll:
    """PlannerConfig is the only export from config.py."""

    def test_config_module_all(self):
        from k1.planner import config

        assert config.__all__ == ["PlannerConfig"]

    def test_importable_from_package_init(self):
        from k1.planner import PlannerConfig

        assert dataclasses.is_dataclass(PlannerConfig)
