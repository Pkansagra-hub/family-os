"""Tests for feedback envelope models.

Covers Stories: FEEDBACK-001, FEEDBACK-002
Related ADR: K020
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from k0.feedback.envelope import FeedbackEnvelope
from k0.feedback.signals import SignalClass, priority_band_for


def test_feedback_envelope_accepts_plan_alias_fields() -> None:
    envelope_id = uuid4()

    env = FeedbackEnvelope.model_validate(
        {
            "envelope_id": envelope_id,  # alias for feedback_id
            "target_pipeline": "p02",  # alias for pipeline_id
            "signal_class": "CORRECTION",
            "correlation_ids": {
                "wal_position": 7,
                "event_ids": ["evt-1", "evt-1"],
            },
            "payload": {"some": "payload"},
        }
    )

    assert env.feedback_id == envelope_id
    assert env.pipeline_id == "P02"
    assert env.signal_class == SignalClass.CORRECTION
    assert env.correlation.wal_positions == [7]
    assert env.correlation.event_ids == ["evt-1"]


def test_feedback_envelope_accepts_wiring_guide_fields() -> None:
    feedback_id = uuid4()

    env = FeedbackEnvelope.model_validate(
        {
            "feedback_id": feedback_id,
            "pipeline_id": "P08",
            "signal_class": SignalClass.VALIDATION,
            "signal_subtype": "user_memory_validation",
            "correlation": {
                "session_id": "sess-123",
                "message_id": "msg-abc",
                "wal_positions": [1, 2],
                "target_entity_type": "event",
                "target_entity_id": "evt-999",
            },
            "provenance": {"source_message_id": "msg-abc"},
            "payload": {"is_valid": True},
        }
    )

    assert env.feedback_id == feedback_id
    assert env.pipeline_id == "P08"
    assert env.session_id == "sess-123"  # promoted from correlation
    assert env.correlation.target_entity_id == "evt-999"


def test_feedback_envelope_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        FeedbackEnvelope(
            pipeline_id="P02",
            signal_class="OUTCOME",
            payload={},
            not_a_field=123,  # type: ignore[arg-type]
        )


def test_signal_class_priority_band_defined() -> None:
    band = priority_band_for(SignalClass.CORRECTION)
    assert band.tier == "P0"
    assert 0.0 <= band.min_priority <= band.max_priority <= 1.0
