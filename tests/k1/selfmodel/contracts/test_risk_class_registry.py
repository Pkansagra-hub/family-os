"""M2.E1.I3 — ``RISK_CLASS_BY_TOOL`` registry tests."""

from __future__ import annotations

import logging

import pytest

from k1.selfmodel.contracts.policy import RiskClass
from k1.selfmodel.contracts.risk_class_registry import (
    RISK_CLASS_BY_TOOL,
    get_risk_class,
    register_tool_risk,
    reset_unknown_warnings,
)


def test_known_concierge_tools_have_declared_risk() -> None:
    # Spot-check each band has at least one canonical tool.
    assert RISK_CLASS_BY_TOOL["recall_memory"] == RiskClass.LOW
    assert RISK_CLASS_BY_TOOL["update_persona"] == RiskClass.MEDIUM
    assert RISK_CLASS_BY_TOOL["send_message"] == RiskClass.HIGH
    assert RISK_CLASS_BY_TOOL["set_medication"] == RiskClass.SAFETY_SENSITIVE


@pytest.mark.parametrize("name", sorted(RISK_CLASS_BY_TOOL))
def test_get_risk_class_returns_declared_value(name: str) -> None:
    assert get_risk_class(name) == RISK_CLASS_BY_TOOL[name]


def test_unknown_tool_defaults_fail_open_with_one_warning(caplog) -> None:
    """M12.E2.I1 — unknown tools fail open to LOW. Conscience risk_overrides
    + Fabric-level conscience gate (M12.E4) provide escalation; the
    declaration-missing case still emits a one-shot warning."""
    reset_unknown_warnings()
    with caplog.at_level(logging.WARNING, logger="k1.selfmodel.contracts.risk_class_registry"):
        assert get_risk_class("never_seen_before_tool") == RiskClass.LOW
        assert get_risk_class("never_seen_before_tool") == RiskClass.LOW
    warns = [r for r in caplog.records if "never_seen_before_tool" in r.getMessage()]
    assert len(warns) == 1, "expected exactly one warning per unknown tool"


def test_unknown_tool_legacy_default_safety_sensitive() -> None:
    """Back-compat — callers may opt into the historical fail-closed default."""
    reset_unknown_warnings()
    assert (
        get_risk_class("legacy_unknown_tool", default=RiskClass.SAFETY_SENSITIVE)
        == RiskClass.SAFETY_SENSITIVE
    )


def test_register_tool_risk_overrides() -> None:
    reset_unknown_warnings()
    register_tool_risk("custom_tool", RiskClass.HIGH)
    try:
        assert get_risk_class("custom_tool") == RiskClass.HIGH
        # Re-register should override.
        register_tool_risk("custom_tool", RiskClass.MEDIUM)
        assert get_risk_class("custom_tool") == RiskClass.MEDIUM
    finally:
        RISK_CLASS_BY_TOOL.pop("custom_tool", None)


def test_register_tool_risk_validates_inputs() -> None:
    with pytest.raises(ValueError):
        register_tool_risk("", RiskClass.LOW)
    with pytest.raises(TypeError):
        register_tool_risk("x", "not_a_riskclass")  # type: ignore[arg-type]


def test_get_risk_class_handles_empty_string() -> None:
    """Empty/None tool name returns the fail-open default (M12.E2.I1)."""
    assert get_risk_class("") == RiskClass.LOW
    assert get_risk_class(None) == RiskClass.LOW  # type: ignore[arg-type]
