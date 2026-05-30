"""Tests for temporal event contracts."""

from __future__ import annotations

from dataclasses import asdict

from k1.temporal.events import (
    TEMPORAL_ANCHOR_CREATED,
    TEMPORAL_ANCHOR_REFRESHED,
    TEMPORAL_ANCHOR_STALE,
    TEMPORAL_EXPRESSION_AMBIGUOUS,
    TEMPORAL_EXPRESSION_RESOLVED,
    AnchorCreatedPayload,
)


def test_event_topics_are_versioned() -> None:
    topics = {
        TEMPORAL_ANCHOR_CREATED,
        TEMPORAL_ANCHOR_REFRESHED,
        TEMPORAL_ANCHOR_STALE,
        TEMPORAL_EXPRESSION_AMBIGUOUS,
        TEMPORAL_EXPRESSION_RESOLVED,
    }
    assert topics == {
        "k1.temporal.anchor.created.v1",
        "k1.temporal.anchor.refreshed.v1",
        "k1.temporal.anchor.stale.v1",
        "k1.temporal.expression.ambiguous.v1",
        "k1.temporal.expression.resolved.v1",
    }


def test_anchor_created_payload_serializes_cleanly() -> None:
    payload = AnchorCreatedPayload(
        anchor_id="a1",
        session_id="s1",
        anchor={"timezone": "UTC"},
        created_at_utc="2025-01-01T00:00:00+00:00",
    )
    assert asdict(payload)["anchor"] == {"timezone": "UTC"}
