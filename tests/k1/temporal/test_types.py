"""Tests for temporal pure payload types."""

from __future__ import annotations

import dataclasses

from k1.temporal.types import CandidateSpan, RoutineRef, TemporalTurnSnapshot
from tests.k1.temporal.helpers import sample_anchor, sample_window


def test_candidate_and_routine_types_are_frozen() -> None:
    for cls in (CandidateSpan, RoutineRef):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True


def test_turn_snapshot_uses_canonical_anchor_and_windows() -> None:
    anchor = sample_anchor()
    window = sample_window()
    snapshot = TemporalTurnSnapshot(
        session_id="session-1",
        turn_id="turn-1",
        anchor=anchor,
        windows={"today": window},
        resolved_expressions=(),
        refreshed_at_utc=anchor.now_utc,
        source="test",
    )
    assert snapshot.anchor is anchor
    assert snapshot.windows["today"] is window
