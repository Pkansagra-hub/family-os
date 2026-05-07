"""HILConfig -- tuning knobs for HumanInTheLoopService (E1.M1.10)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HILConfig:
    """Service-level config. Defaults match the design table.

    Per-kind timeouts may be overridden by the caller passing
    `timeout_ms` on the request dataclass; these defaults apply
    only when the caller passes `None` / 0 / does not set it.
    """

    # Round budget (PLAN-10) -- shared across clarification kind.
    max_clarification_rounds: int = 2

    # Per-kind timeouts (milliseconds).
    clarification_timeout_ms: int = 60_000
    approval_timeout_ms: int = 120_000
    needs_human_timeout_ms: int = 60_000
    override_timeout_ms: int = 60_000
    capability_gate_timeout_ms: int = 120_000

    # Behavior toggles.
    enable_audit_topic: bool = True
    enable_llm_synthesis: bool = True
