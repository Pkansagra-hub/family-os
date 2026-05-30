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

    # ------------------------------------------------------------------
    # GAP-HIL-009 / GAP-HIL-003 -- presentation-aware lifecycle.
    # ------------------------------------------------------------------
    # When ``require_presentation_ack`` is True the service treats each
    # request as a two-phase wait:
    #   1. Wait up to ``presentation_timeout_ms`` for a
    #      ``TOPIC_HIL_PRESENTED`` envelope keyed by ``hil_request_id``.
    #   2. After ack, arm the per-kind human-response timer for the full
    #      caller-supplied ``timeout_ms``.
    # When False the legacy single-timer behaviour is preserved (timer
    # starts at request publish). All existing tests pass with the legacy
    # default; production wiring opts in via the factory.
    require_presentation_ack: bool = False
    presentation_timeout_ms: int = 5_000

    # GAP-HIL-007 -- Front fast-path. When True the Front actor renders
    # simple ``needs_human`` / ``clarification`` HIL questions deterministically
    # and skips the LLM rewrite. Sensitive kinds (approval, capability_gate,
    # override) always render via their widget lane and are unaffected.
    enable_front_fast_path: bool = True
    # Override for forensic / red-team work that wants the LLM rewrite back.
    enable_llm_relay_rewrite: bool = False
