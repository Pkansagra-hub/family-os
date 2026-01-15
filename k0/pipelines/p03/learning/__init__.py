"""P03 Learning package for anomaly detection and parameter management."""

from __future__ import annotations

__all__ = [
    # learning_anomaly_detector.py - Issue 6.2.17
    "LearningAnomalyResult",
    "LearningAnomalyType",
    "P03LearningAnomalyDetector",
    "create_learning_anomaly_detector",
    # feedback_queue.py - Issue 6.4.14
    "FeedbackQueue",
    "FeedbackSignal",
    "QUEUE_MAX_DEPTH",
    "OVERFLOW_SAMPLE_RATE",
    # async_audit.py - Issue 6.4.15
    "AsyncAuditLogger",
    "AuditRecord",
]

from k0.pipelines.p03.learning.async_audit import AsyncAuditLogger, AuditRecord
from k0.pipelines.p03.learning.feedback_queue import (
    OVERFLOW_SAMPLE_RATE,
    QUEUE_MAX_DEPTH,
    FeedbackQueue,
    FeedbackSignal,
)
from k0.pipelines.p03.learning.learning_anomaly_detector import (
    LearningAnomalyResult,
    LearningAnomalyType,
    P03LearningAnomalyDetector,
    create_learning_anomaly_detector,
)
