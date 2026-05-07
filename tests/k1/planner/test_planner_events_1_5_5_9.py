"""Tests for Epic 1.5 issue 1.5.9 -- PlannerConfig.from_dict() + validation.

E5 (HIL Unification): tests for issues 1.5.5-1.5.8 (HIL event schemas) were
removed; the planner no longer publishes/subscribes HIL topics. The unified
``IHILPort`` adapter handles all HIL coordination.
"""

from __future__ import annotations

import dataclasses

import pytest

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
