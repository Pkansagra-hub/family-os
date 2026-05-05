"""Canonical ``situation_kind`` strings (S1..S13) for V0.

Source: ``docs/whiteboard/whiteboard_k1_user_selfmodel_and_tools.md``
("V0 Family Operating Design — §1 Final V0 Situation Set").

The composer and the policy gate refuse to operate on
``situation_kind`` values that are not in this set — so additions go
through a contract change, not a stringly-typed shortcut.
"""

from __future__ import annotations

from typing import Final

__all__ = ["SITUATION_KINDS", "is_known_situation"]


# Locked V0 set. Adding/renaming any of these is a contract change.
SITUATION_KINDS: Final[frozenset[str]] = frozenset(
    {
        # S1
        "child_daily_read",
        # S2
        "caregiver_child_read",
        # S3
        "shared_hub_unknown_speaker",
        # S4
        "caregiver_high_impact_write",
        # S5
        "child_own_action_write",
        # S6
        "caregiver_pattern_analysis",
        # S7
        "child_sibling_read_attempt",
        # S8
        "system_conflict_detected",
        # S9
        "caregiver_recurring_write",
        # S10
        "memory_scope_decision",
        # S11
        "child_explicit_privacy",
        # S12
        "caregiver_context_briefing",
        # S13
        "child_guardian_approval_request",
    }
)


def is_known_situation(kind: str) -> bool:
    """``True`` iff ``kind`` is a canonical V0 situation string."""
    return kind in SITUATION_KINDS
