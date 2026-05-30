"""Tests for temporal serialization helpers."""

from __future__ import annotations

from k1.temporal.serialization import (
    anchor_to_dict,
    dict_to_anchor,
    dict_to_projection,
    dict_to_resolution,
    projection_to_dict,
    resolution_to_dict,
    turn_snapshot_to_dict,
)
from k1.temporal.types import (
    ResolvedTemporalExpression,
    TemporalProjection,
    TemporalTurnSnapshot,
)
from tests.k1.temporal.helpers import sample_anchor, sample_window


def test_anchor_roundtrip_preserves_canonical_fields() -> None:
    anchor = sample_anchor()
    assert dict_to_anchor(anchor_to_dict(anchor)) == anchor


def test_resolution_projection_and_snapshot_serialization() -> None:
    anchor = sample_anchor()
    window = sample_window()
    resolution = ResolvedTemporalExpression(
        raw_text="today",
        normalized_label="today",
        resolution_kind="window",
        window=window,
        instant_local=None,
        recurrence_rule=None,
        confidence=0.97,
        needs_clarification=False,
        clarification_reason=None,
    )
    assert dict_to_resolution(resolution_to_dict(resolution)) == resolution

    projection = TemporalProjection(
        anchor=anchor,
        windows={"today": window},
        resolved_expressions=(resolution,),
        consumer="front",
        freshness="live",
        precision="full",
    )
    assert dict_to_projection(projection_to_dict(projection)) == projection

    snapshot = TemporalTurnSnapshot(
        session_id="s1",
        turn_id="t1",
        anchor=anchor,
        windows={"today": window},
        resolved_expressions=(resolution,),
        refreshed_at_utc=anchor.now_utc,
        source="test",
    )
    assert turn_snapshot_to_dict(snapshot)["anchor"]["anchor_id"] == "anchor-1"
