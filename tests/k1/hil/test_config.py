"""Tests for k1.hil.config (E1.M1.10)."""

from __future__ import annotations

from k1.hil.config import HILConfig


def test_defaults_match_design() -> None:
    c = HILConfig()
    assert c.max_clarification_rounds == 2
    assert c.clarification_timeout_ms == 60_000
    assert c.approval_timeout_ms == 120_000
    assert c.needs_human_timeout_ms == 60_000
    assert c.override_timeout_ms == 60_000
    assert c.capability_gate_timeout_ms == 120_000
    assert c.enable_audit_topic is True
    assert c.enable_llm_synthesis is True


def test_frozen_and_slotted() -> None:
    c = HILConfig()
    try:
        c.max_clarification_rounds = 5  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("HILConfig should be frozen")
    assert not hasattr(c, "__dict__")
