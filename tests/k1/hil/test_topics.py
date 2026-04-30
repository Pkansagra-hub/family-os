"""Tests for k1.hil.topics (E1.M1.4)."""

from __future__ import annotations

from k1.hil import topics


def test_topic_strings() -> None:
    assert topics.TOPIC_HIL_REQUEST == "k1.hil.request.v1"
    assert topics.TOPIC_HIL_RESPONSE == "k1.hil.response.v1"
    assert topics.TOPIC_HIL_AUDIT == "k1.hil.audit.v1"


def test_topics_are_distinct() -> None:
    vals = {topics.TOPIC_HIL_REQUEST, topics.TOPIC_HIL_RESPONSE, topics.TOPIC_HIL_AUDIT}
    assert len(vals) == 3
