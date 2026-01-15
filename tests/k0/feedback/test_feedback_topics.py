"""Tests for feedback topic helpers.

Epic 1.2: Feedback Bus Topics
Issue: FEEDBACK-007
Related ADR: K020
"""

from __future__ import annotations

import pytest

from k0.feedback.topics import (
    FEEDBACK_PIPELINES_V1,
    FEEDBACK_SIGNAL_ALL_V1,
    FEEDBACK_SIGNAL_P02_V1,
    FEEDBACK_SIGNAL_P08_V1,
    FEEDBACK_SIGNAL_TOPICS_V1,
    feedback_signal_topic,
    registered_feedback_signal_topics_v1,
)


def test_feedback_signal_topic_formats_pipeline_and_version() -> None:
    assert feedback_signal_topic("P02") == "feedback.signal.p02.v1"
    assert feedback_signal_topic("p08", version="V1") == "feedback.signal.p08.v1"


def test_registered_feedback_signal_topics_v1_are_only_implemented_pipelines() -> None:
    assert FEEDBACK_PIPELINES_V1 == ("P02", "P08")
    assert registered_feedback_signal_topics_v1() == (
        FEEDBACK_SIGNAL_P02_V1,
        FEEDBACK_SIGNAL_P08_V1,
    )


def test_feedback_signal_topics_v1_constants() -> None:
    assert FEEDBACK_SIGNAL_ALL_V1 == "feedback.signal.all.v1"
    assert FEEDBACK_SIGNAL_TOPICS_V1 == (
        FEEDBACK_SIGNAL_ALL_V1,
        FEEDBACK_SIGNAL_P02_V1,
        FEEDBACK_SIGNAL_P08_V1,
    )


def test_feedback_signal_topic_rejects_invalid_pipeline_id() -> None:
    with pytest.raises(ValueError):
        feedback_signal_topic("")

    with pytest.raises(ValueError):
        feedback_signal_topic("not-a-pipeline")


def test_feedback_signal_topic_rejects_empty_version() -> None:
    with pytest.raises(ValueError):
        feedback_signal_topic("P02", version="")
