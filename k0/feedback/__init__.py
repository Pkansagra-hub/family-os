"""Feedback subsystem types.

Related ADR: K020 (Feedback Signals Subsystem)
"""

from .envelope import FeedbackCorrelation, FeedbackEnvelope
from .payloads import P02FeedbackPayload, P08FeedbackPayload
from .schema_registry import FeedbackSchemaRegistry
from .signals import SignalClass, SignalPriorityBand, SignalSource
from .topics import (
    FEEDBACK_PIPELINES_V1,
    FEEDBACK_SIGNAL_ALL_V1,
    FEEDBACK_SIGNAL_P02_V1,
    FEEDBACK_SIGNAL_P08_V1,
    FEEDBACK_SIGNAL_TOPICS_V1,
    feedback_signal_topic,
    registered_feedback_signal_topics_v1,
)

__all__ = [
    "FeedbackCorrelation",
    "FeedbackEnvelope",
    "FeedbackSchemaRegistry",
    "P02FeedbackPayload",
    "P08FeedbackPayload",
    "SignalClass",
    "SignalPriorityBand",
    "SignalSource",
    "FEEDBACK_PIPELINES_V1",
    "FEEDBACK_SIGNAL_ALL_V1",
    "FEEDBACK_SIGNAL_P02_V1",
    "FEEDBACK_SIGNAL_P08_V1",
    "FEEDBACK_SIGNAL_TOPICS_V1",
    "feedback_signal_topic",
    "registered_feedback_signal_topics_v1",
]
