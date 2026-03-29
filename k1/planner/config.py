"""PlannerConfig frozen dataclass [F07].

Holds all tunable Planner parameters.  Loaded from K1 configuration at
boot time via PlannerFactory.  Immutable after construction.

Design decisions
----------------
- Frozen dataclass (immutable after creation).
- All fields have sensible defaults matching planner.md production values.
- ``from_dict()`` class method for override-based construction.
- ``__post_init__`` validates invariants (timeouts > 0, temperatures in
  range, total budget >= sum of per-stage budgets).

Import graph (Layer 0 -- no internal deps)
------------------------------------------
k1.planner.config
  -> stdlib only (dataclasses, typing)

NEVER import from any service, port, or adapter module.

References
----------
- planner.md Section 13.3 (Budget Injection)
- planner.md Section 21 (Performance Targets)
- planner.md Section 24.2 (Cancel)
- planner.md Section 30.5.1 F07
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class PlannerConfig:
    """Planner configuration (Section 30.5.1 F07).

    All timeouts are in milliseconds.  All token budgets are in tokens.
    Temperatures are floats in [0.0, 2.0].

    Attributes
    ----------
    mailbox_max_depth : int
        Maximum pending plan requests in the mailbox queue.
    pipeline_timeout_ms : int
        Overall pipeline timeout (PLAN-04).
    sketch_timeout_ms : int
        Stage 1 SKETCH timeout.
    expand_timeout_ms : int
        Stage 2 EXPAND timeout.
    validate_timeout_ms : int
        Stage 3 VALIDATE timeout.
    commit_timeout_ms : int
        Stage 4 COMMIT timeout.
    sketch_max_tokens : int
        LLM token budget for SKETCH stage (PLAN-11).
    expand_max_tokens : int
        LLM token budget for EXPAND stage (PLAN-11).
    validate_max_tokens : int
        LLM token budget for VALIDATE stage (PLAN-11).
    total_token_budget : int
        Total LLM token budget across all stages (PLAN-11).
    sketch_temperature : float
        LLM temperature for SKETCH stage.
    expand_temperature : float
        LLM temperature for EXPAND stage.
    validate_temperature : float
        LLM temperature for VALIDATE stage.
    max_tool_calls_per_plan : int
        Maximum tool calls per plan (PLAN-05).
    max_hil_rounds : int
        Maximum HIL interaction rounds (PLAN-10).
    hil_clarification_timeout_ms : int
        Timeout for HIL clarification response.
    hil_approval_timeout_ms : int
        Timeout for HIL approval response.
    micro_replan_timeout_ms : int
        Timeout for micro-replan pipeline.
    micro_replan_max_tokens : int
        Total token budget for micro-replan pipeline.
    shutdown_grace_period_ms : int
        Grace period for in-flight plans during shutdown.
    """

    # Mailbox
    mailbox_max_depth: int = 5

    # Pipeline timeouts (PLAN-04)
    pipeline_timeout_ms: int = 45_000
    sketch_timeout_ms: int = 8_000
    expand_timeout_ms: int = 5_000
    validate_timeout_ms: int = 3_000
    commit_timeout_ms: int = 1_000

    # LLM token budgets (PLAN-11)
    sketch_max_tokens: int = 2_000
    expand_max_tokens: int = 1_000
    validate_max_tokens: int = 500
    total_token_budget: int = 3_500

    # LLM temperatures
    sketch_temperature: float = 0.7
    expand_temperature: float = 0.3
    validate_temperature: float = 0.2

    # Tool budgets (PLAN-05)
    max_tool_calls_per_plan: int = 6

    # HIL (PLAN-10)
    max_hil_rounds: int = 2
    hil_clarification_timeout_ms: int = 60_000
    hil_approval_timeout_ms: int = 120_000

    # Micro-replan (overall)
    micro_replan_timeout_ms: int = 10_000
    micro_replan_max_tokens: int = 2_000

    # Micro-replan per-stage budgets (Section 10.3.6, PLAN-11)
    micro_sketch_max_tokens: int = 1_024
    micro_sketch_timeout_ms: int = 5_000
    micro_expand_max_tokens: int = 512
    micro_expand_timeout_ms: int = 3_000
    micro_validate_max_tokens: int = 256
    micro_validate_timeout_ms: int = 2_000

    # Shutdown
    shutdown_grace_period_ms: int = 5_000

    def __post_init__(self) -> None:
        # Validate mailbox depth [1, 20]
        if not 1 <= self.mailbox_max_depth <= 20:
            raise ValueError(
                f"PlannerConfig.mailbox_max_depth must be in [1, 20], "
                f"got {self.mailbox_max_depth}"
            )

        # Validate all timeouts > 0
        timeout_fields = [
            ("pipeline_timeout_ms", self.pipeline_timeout_ms),
            ("sketch_timeout_ms", self.sketch_timeout_ms),
            ("expand_timeout_ms", self.expand_timeout_ms),
            ("validate_timeout_ms", self.validate_timeout_ms),
            ("commit_timeout_ms", self.commit_timeout_ms),
            ("hil_clarification_timeout_ms", self.hil_clarification_timeout_ms),
            ("hil_approval_timeout_ms", self.hil_approval_timeout_ms),
            ("micro_replan_timeout_ms", self.micro_replan_timeout_ms),
            ("micro_sketch_timeout_ms", self.micro_sketch_timeout_ms),
            ("micro_expand_timeout_ms", self.micro_expand_timeout_ms),
            ("micro_validate_timeout_ms", self.micro_validate_timeout_ms),
            ("shutdown_grace_period_ms", self.shutdown_grace_period_ms),
        ]
        for name, value in timeout_fields:
            if value <= 0:
                raise ValueError(f"PlannerConfig.{name} must be > 0, got {value}")

        # Validate token budgets > 0
        token_fields = [
            ("sketch_max_tokens", self.sketch_max_tokens),
            ("expand_max_tokens", self.expand_max_tokens),
            ("validate_max_tokens", self.validate_max_tokens),
            ("total_token_budget", self.total_token_budget),
            ("micro_replan_max_tokens", self.micro_replan_max_tokens),
            ("micro_sketch_max_tokens", self.micro_sketch_max_tokens),
            ("micro_expand_max_tokens", self.micro_expand_max_tokens),
            ("micro_validate_max_tokens", self.micro_validate_max_tokens),
        ]
        for name, value in token_fields:
            if value <= 0:
                raise ValueError(f"PlannerConfig.{name} must be > 0, got {value}")

        # Validate total >= sum of per-stage budgets
        per_stage_sum = self.sketch_max_tokens + self.expand_max_tokens + self.validate_max_tokens
        if self.total_token_budget < per_stage_sum:
            raise ValueError(
                f"PlannerConfig.total_token_budget ({self.total_token_budget}) "
                f"must be >= sum of per-stage budgets ({per_stage_sum})"
            )

        # Validate micro per-stage sum <= micro_replan_max_tokens
        micro_sum = (
            self.micro_sketch_max_tokens
            + self.micro_expand_max_tokens
            + self.micro_validate_max_tokens
        )
        if self.micro_replan_max_tokens < micro_sum:
            raise ValueError(
                f"PlannerConfig.micro_replan_max_tokens ({self.micro_replan_max_tokens}) "
                f"must be >= sum of micro per-stage budgets ({micro_sum})"
            )

        # Validate temperatures in [0.0, 2.0]
        temp_fields = [
            ("sketch_temperature", self.sketch_temperature),
            ("expand_temperature", self.expand_temperature),
            ("validate_temperature", self.validate_temperature),
        ]
        for name, value in temp_fields:
            if not 0.0 <= value <= 2.0:
                raise ValueError(f"PlannerConfig.{name} must be in [0.0, 2.0], got {value}")

        # Validate tool calls [1, 20] and HIL rounds [0, 5]
        if not 1 <= self.max_tool_calls_per_plan <= 20:
            raise ValueError(
                f"PlannerConfig.max_tool_calls_per_plan must be in [1, 20], "
                f"got {self.max_tool_calls_per_plan}"
            )
        if not 0 <= self.max_hil_rounds <= 5:
            raise ValueError(
                f"PlannerConfig.max_hil_rounds must be in [0, 5], " f"got {self.max_hil_rounds}"
            )

    @classmethod
    def from_dict(cls, overrides: Dict[str, Any]) -> PlannerConfig:
        """Create PlannerConfig with overrides applied on top of defaults.

        Unrecognised keys raise ValueError (fail-fast).

        Args:
            overrides: Dictionary of field name -> value overrides.

        Returns:
            New PlannerConfig with overrides applied.

        Raises:
            ValueError: If any key is not a valid PlannerConfig field.
        """
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        unknown = set(overrides.keys()) - valid_fields
        if unknown:
            raise ValueError(f"Unknown PlannerConfig fields: {sorted(unknown)}")
        return cls(**overrides)


__all__ = [
    "PlannerConfig",
]
