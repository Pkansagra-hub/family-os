"""
P03 Learning Anomaly Detector — Issue 6.2.13.

Detects anomalies in feedback signal content including:
- Low entropy content (bot-like repetitive text)
- Duplicate/repetitive feedback patterns
- Statistical outliers in signal characteristics

Dossier Reference: Section 6.21
K0 Integration: Uses k0/obs/metrics.py for emission
"""

from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import asyncpg

    from k0.obs.metrics import MetricsExporter


class AnomalyType(Enum):
    """Types of detected anomalies."""

    LOW_ENTROPY = "LOW_ENTROPY"
    REPETITIVE_CONTENT = "REPETITIVE_CONTENT"
    STATISTICAL_OUTLIER = "STATISTICAL_OUTLIER"
    SUSPICIOUS_PATTERN = "SUSPICIOUS_PATTERN"


@dataclass(slots=True)
class AnomalyResult:
    """
    Result of anomaly detection.

    Attributes:
        is_anomalous: True if any anomaly detected
        anomaly_types: List of detected anomaly types
        entropy_score: Shannon entropy of content (None if not calculated)
        repetition_score: Max similarity to recent content from same user
        z_score: Z-score of content length vs space average
        details: Additional diagnostic details
    """

    is_anomalous: bool
    anomaly_types: list[AnomalyType] = field(default_factory=list)
    entropy_score: Optional[float] = None
    repetition_score: Optional[float] = None
    z_score: Optional[float] = None
    details: dict = field(default_factory=dict)


class P03LearningAnomalyDetector:
    """
    Detect anomalies in feedback signal content.

    Checks for:
    - Low entropy content (bot-like repetitive text)
    - Duplicate/repetitive feedback patterns from same user
    - Statistical outliers in signal characteristics

    Dossier Reference: Section 6.21
    ADR: k010.9-capability-based-security.md
    """

    # Default thresholds from dossier
    DEFAULT_MIN_ENTROPY = 2.0
    DEFAULT_REPETITION_THRESHOLD = 0.8
    DEFAULT_Z_SCORE_THRESHOLD = 3.0
    DEFAULT_MIN_CONTENT_LENGTH = 10
    DEFAULT_REPETITION_LOOKBACK_HOURS = 1
    DEFAULT_Z_SCORE_LOOKBACK_HOURS = 24
    DEFAULT_MAX_RECENT_SIGNALS = 20
    DEFAULT_MIN_SAMPLE_SIZE = 10

    def __init__(
        self,
        *,
        min_entropy_threshold: float = DEFAULT_MIN_ENTROPY,
        repetition_threshold: float = DEFAULT_REPETITION_THRESHOLD,
        z_score_threshold: float = DEFAULT_Z_SCORE_THRESHOLD,
        min_content_length: int = DEFAULT_MIN_CONTENT_LENGTH,
        metrics: Optional[MetricsExporter] = None,
    ) -> None:
        """
        Initialize anomaly detector.

        Args:
            min_entropy_threshold: Minimum Shannon entropy for content
            repetition_threshold: Max allowed Jaccard similarity to recent content
            z_score_threshold: Z-score threshold for statistical outliers
            min_content_length: Minimum content length for entropy check
            metrics: Optional metrics exporter
        """
        self._min_entropy = min_entropy_threshold
        self._repetition_threshold = repetition_threshold
        self._z_score_threshold = z_score_threshold
        self._min_content_length = min_content_length
        self._metrics = metrics

    @property
    def min_entropy_threshold(self) -> float:
        """Get minimum entropy threshold."""
        return self._min_entropy

    @property
    def repetition_threshold(self) -> float:
        """Get repetition threshold."""
        return self._repetition_threshold

    @property
    def z_score_threshold(self) -> float:
        """Get Z-score threshold."""
        return self._z_score_threshold

    async def detect_anomalies(
        self,
        signal_id: str,
        content: str,
        space_id: str,
        user_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> AnomalyResult:
        """
        Detect anomalies in feedback signal.

        Args:
            signal_id: Signal ID for context
            content: Signal content to analyze
            space_id: Space context
            user_id: User who submitted signal
            connection: Database connection

        Returns:
            AnomalyResult with detected anomalies and scores.
        """
        anomaly_types: list[AnomalyType] = []
        details: dict = {}

        # Check entropy
        entropy = self._calculate_entropy(content)
        if entropy < self._min_entropy and len(content) >= self._min_content_length:
            anomaly_types.append(AnomalyType.LOW_ENTROPY)
            details["entropy_reason"] = f"Entropy {entropy:.2f} below threshold {self._min_entropy}"

        # Check for repetitive content from same user
        repetition_score = await self._check_repetition(
            content, space_id, user_id, connection=connection
        )
        if repetition_score >= self._repetition_threshold:
            anomaly_types.append(AnomalyType.REPETITIVE_CONTENT)
            details["repetition_reason"] = (
                f"Similarity {repetition_score:.2f} exceeds threshold {self._repetition_threshold}"
            )

        # Check for statistical outliers
        z_score = await self._calculate_z_score(content, space_id, connection=connection)
        if z_score is not None and abs(z_score) > self._z_score_threshold:
            anomaly_types.append(AnomalyType.STATISTICAL_OUTLIER)
            details["z_score_reason"] = (
                f"Z-score {z_score:.2f} exceeds threshold {self._z_score_threshold}"
            )

        is_anomalous = len(anomaly_types) > 0

        # Emit metrics
        self._emit_metric(
            "p03_anomaly_checks_total",
            1.0,
            is_anomalous=str(is_anomalous).lower(),
        )

        for anomaly_type in anomaly_types:
            self._emit_metric(
                "p03_anomalies_detected_total",
                1.0,
                type=anomaly_type.value,
            )

        return AnomalyResult(
            is_anomalous=is_anomalous,
            anomaly_types=anomaly_types,
            entropy_score=entropy,
            repetition_score=repetition_score,
            z_score=z_score,
            details=details,
        )

    def calculate_entropy(self, text: str) -> float:
        """
        Calculate Shannon entropy of text (public API).

        Args:
            text: Text to analyze

        Returns:
            Shannon entropy value (higher = more random/varied)
        """
        return self._calculate_entropy(text)

    def _calculate_entropy(self, text: str) -> float:
        """Calculate Shannon entropy of text."""
        if not text:
            return 0.0

        # Count character frequencies
        counter = Counter(text.lower())
        length = len(text)

        # Calculate entropy
        entropy = 0.0
        for count in counter.values():
            probability = count / length
            if probability > 0:
                entropy -= probability * math.log2(probability)

        return entropy

    async def _check_repetition(
        self,
        content: str,
        space_id: str,
        user_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> float:
        """Check for repetitive content from same user (last hour)."""
        now = int(time.time())
        window_start = now - (self.DEFAULT_REPETITION_LOOKBACK_HOURS * 3600)

        # Get recent signals from same user
        rows = await connection.fetch(
            """
            SELECT content
            FROM st_feedback_signals
            WHERE space_id = $1
              AND user_id = $2
              AND created_at > $3
              AND content IS NOT NULL
            ORDER BY created_at DESC
            LIMIT $4
            """,
            space_id,
            user_id,
            window_start,
            self.DEFAULT_MAX_RECENT_SIGNALS,
        )

        if not rows:
            return 0.0

        # Calculate max similarity to any recent signal
        max_similarity = 0.0
        content_lower = content.lower()

        for row in rows:
            if row["content"]:
                other_lower = row["content"].lower()
                similarity = self._jaccard_similarity(content_lower, other_lower)
                max_similarity = max(max_similarity, similarity)

        return max_similarity

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate Jaccard similarity between two texts (public API).

        Args:
            text1: First text
            text2: Second text

        Returns:
            Jaccard similarity coefficient (0.0 to 1.0)
        """
        return self._jaccard_similarity(text1, text2)

    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts."""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    async def _calculate_z_score(
        self,
        content: str,
        space_id: str,
        *,
        connection: "asyncpg.Connection",
    ) -> Optional[float]:
        """Calculate Z-score of content length vs space average."""
        now = int(time.time())
        window_start = now - (self.DEFAULT_Z_SCORE_LOOKBACK_HOURS * 3600)

        # Get length statistics for space
        row = await connection.fetchrow(
            """
            SELECT
                AVG(LENGTH(content)) as avg_length,
                STDDEV(LENGTH(content)) as stddev_length,
                COUNT(*) as sample_count
            FROM st_feedback_signals
            WHERE space_id = $1
              AND created_at > $2
              AND content IS NOT NULL
            """,
            space_id,
            window_start,
        )

        if not row or (row["sample_count"] or 0) < self.DEFAULT_MIN_SAMPLE_SIZE:
            return None

        avg_length = row["avg_length"] or 0
        stddev_length = row["stddev_length"] or 0

        if stddev_length == 0:
            return None

        # Calculate Z-score
        content_length = len(content)
        z_score = (content_length - avg_length) / stddev_length

        return float(z_score)

    def _emit_metric(self, name: str, value: float, **labels: str) -> None:
        """Emit metric if exporter available."""
        if self._metrics:
            self._metrics.emit(name, value, **labels)


def create_anomaly_detector(
    *,
    min_entropy_threshold: float = P03LearningAnomalyDetector.DEFAULT_MIN_ENTROPY,
    repetition_threshold: float = P03LearningAnomalyDetector.DEFAULT_REPETITION_THRESHOLD,
    z_score_threshold: float = P03LearningAnomalyDetector.DEFAULT_Z_SCORE_THRESHOLD,
    min_content_length: int = P03LearningAnomalyDetector.DEFAULT_MIN_CONTENT_LENGTH,
    metrics: Optional[MetricsExporter] = None,
) -> P03LearningAnomalyDetector:
    """
    Factory for creating P03LearningAnomalyDetector.

    Args:
        min_entropy_threshold: Minimum Shannon entropy (default: 2.0)
        repetition_threshold: Max Jaccard similarity (default: 0.8)
        z_score_threshold: Z-score threshold (default: 3.0)
        min_content_length: Minimum content length for entropy (default: 10)
        metrics: Optional metrics exporter

    Returns:
        Configured P03LearningAnomalyDetector instance.
    """
    return P03LearningAnomalyDetector(
        min_entropy_threshold=min_entropy_threshold,
        repetition_threshold=repetition_threshold,
        z_score_threshold=z_score_threshold,
        min_content_length=min_content_length,
        metrics=metrics,
    )
