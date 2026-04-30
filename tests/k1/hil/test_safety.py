"""Tests for SafetyBandPolicy (E1.M1.5)."""

from __future__ import annotations

import pytest

from k1.hil.safety import SafetyBandPolicy, SafetyDecision
from k1.hil.types import CapabilityContractView


def _view(
    band: str = "GREEN",
    rhc: bool | None = None,
    side_effects: list | None = None,
) -> CapabilityContractView:
    return CapabilityContractView(
        name="cap.x",
        safety_band_min=band,
        requires_human_confirmation=rhc,
        side_effects=side_effects or [],
    )


@pytest.fixture
def policy() -> SafetyBandPolicy:
    return SafetyBandPolicy()


def test_green_no_side_effects_allow(policy: SafetyBandPolicy) -> None:
    assert policy.decide(_view("GREEN"), {}) is SafetyDecision.ALLOW


def test_green_with_side_effects_ask(policy: SafetyBandPolicy) -> None:
    assert policy.decide(_view("GREEN", side_effects=[{"kind": "io"}]), {}) is SafetyDecision.ASK


def test_amber_ask(policy: SafetyBandPolicy) -> None:
    assert policy.decide(_view("AMBER"), {}) is SafetyDecision.ASK


def test_red_ask(policy: SafetyBandPolicy) -> None:
    assert policy.decide(_view("RED"), {}) is SafetyDecision.ASK


def test_crisis_ask(policy: SafetyBandPolicy) -> None:
    assert policy.decide(_view("CRISIS"), {}) is SafetyDecision.ASK


def test_explicit_rhc_true_overrides_green(policy: SafetyBandPolicy) -> None:
    assert policy.decide(_view("GREEN", rhc=True), {}) is SafetyDecision.ASK


def test_explicit_rhc_false_overrides_amber_to_allow(policy: SafetyBandPolicy) -> None:
    assert policy.decide(_view("AMBER", rhc=False), {}) is SafetyDecision.ALLOW


def test_red_cannot_be_overridden_to_allow(policy: SafetyBandPolicy) -> None:
    assert policy.decide(_view("RED", rhc=False), {}) is SafetyDecision.ASK


def test_audit_only_for_red_crisis(policy: SafetyBandPolicy) -> None:
    assert policy.is_audit_only(_view("RED")) is True
    assert policy.is_audit_only(_view("CRISIS")) is True
    assert policy.is_audit_only(_view("GREEN")) is False
    assert policy.is_audit_only(_view("AMBER")) is False
