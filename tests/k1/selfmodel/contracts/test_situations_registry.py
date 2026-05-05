"""Tests for the canonical S1..S13 situation_kind registry."""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.situations import (
    SITUATION_KINDS,
    is_known_situation,
)


def test_thirteen_situations() -> None:
    assert len(SITUATION_KINDS) == 13


def test_registry_is_frozen() -> None:
    assert isinstance(SITUATION_KINDS, frozenset)


@pytest.mark.parametrize(
    "kind",
    [
        "child_daily_read",
        "caregiver_child_read",
        "shared_hub_unknown_speaker",
        "caregiver_high_impact_write",
        "child_own_action_write",
        "caregiver_pattern_analysis",
        "child_sibling_read_attempt",
        "system_conflict_detected",
        "caregiver_recurring_write",
        "memory_scope_decision",
        "child_explicit_privacy",
        "caregiver_context_briefing",
        "child_guardian_approval_request",
    ],
)
def test_known_kinds(kind: str) -> None:
    assert is_known_situation(kind)


def test_unknown_kinds_rejected() -> None:
    assert not is_known_situation("nope")
    assert not is_known_situation("")
    assert not is_known_situation("CHILD_DAILY_READ")  # case-sensitive
