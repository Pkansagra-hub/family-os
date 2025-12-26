"""Feedback bus topic names.

Epic 1.2: Feedback Bus Topics
Issue: FEEDBACK-007
Related ADR: K020

K0 uses the BusDispatcher for post-commit fan-out (drivers, SSE, observability).
Feedback signals are routed by pipeline via topic names.

Note: For now, we only register topics for implemented pipelines (P02, P08).
"""

from __future__ import annotations

import re

_PIPELINE_ID_PATTERN = r"^P\d{2,3}$"
_PIPELINE_ID_RE = re.compile(_PIPELINE_ID_PATTERN)

# Implemented pipelines only (per FEEDBACK-issues-tracker.md)
FEEDBACK_PIPELINES_V1: tuple[str, ...] = ("P02", "P08")

FEEDBACK_SIGNAL_ALL_V1 = "feedback.signal.all.v1"

FEEDBACK_SIGNAL_P02_V1 = "feedback.signal.p02.v1"
FEEDBACK_SIGNAL_P08_V1 = "feedback.signal.p08.v1"

FEEDBACK_SIGNAL_TOPICS_V1: tuple[str, ...] = (
    FEEDBACK_SIGNAL_ALL_V1,
    FEEDBACK_SIGNAL_P02_V1,
    FEEDBACK_SIGNAL_P08_V1,
)


def feedback_signal_topic(pipeline_id: str, *, version: str = "v1") -> str:
    """Return the feedback signal topic for a pipeline.

    Example:
        P02 -> feedback.signal.p02.v1

    This function is generic (supports future pipelines), but only P02/P08 are
    considered "registered" today.
    """

    normalized = pipeline_id.strip().upper()
    if not normalized:
        raise ValueError("pipeline_id must not be empty")
    if _PIPELINE_ID_RE.fullmatch(normalized) is None:
        raise ValueError(f"pipeline_id must match {_PIPELINE_ID_PATTERN}")

    suffix = str(version).strip().lower()
    if not suffix:
        raise ValueError("version must not be empty")

    return f"feedback.signal.{normalized.lower()}.{suffix}"


def registered_feedback_signal_topics_v1() -> tuple[str, ...]:
    """Return registered feedback.signal.* topics for implemented pipelines."""

    return tuple(feedback_signal_topic(pid, version="v1") for pid in FEEDBACK_PIPELINES_V1)


__all__ = [
    "FEEDBACK_PIPELINES_V1",
    "FEEDBACK_SIGNAL_ALL_V1",
    "FEEDBACK_SIGNAL_P02_V1",
    "FEEDBACK_SIGNAL_P08_V1",
    "FEEDBACK_SIGNAL_TOPICS_V1",
    "feedback_signal_topic",
    "registered_feedback_signal_topics_v1",
]
