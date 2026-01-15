"""
Tests for P03LearningAnomalyDetector — Issue 6.2.13.

Tests anomaly detection including:
- Shannon entropy calculation
- Jaccard similarity for repetition detection
- Z-score statistical outlier detection
- Metrics emission
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.pipelines.p03.feedback.anomaly_detector import (
    AnomalyResult,
    AnomalyType,
    P03LearningAnomalyDetector,
    create_anomaly_detector,
)


class TestAnomalyType:
    """Test AnomalyType enum."""

    def test_anomaly_types_defined(self) -> None:
        """Test all anomaly types are defined."""
        assert AnomalyType.LOW_ENTROPY.value == "LOW_ENTROPY"
        assert AnomalyType.REPETITIVE_CONTENT.value == "REPETITIVE_CONTENT"
        assert AnomalyType.STATISTICAL_OUTLIER.value == "STATISTICAL_OUTLIER"
        assert AnomalyType.SUSPICIOUS_PATTERN.value == "SUSPICIOUS_PATTERN"


class TestAnomalyResult:
    """Test AnomalyResult dataclass."""

    def test_anomaly_result_creation(self) -> None:
        """Test AnomalyResult can be created."""
        result = AnomalyResult(
            is_anomalous=True,
            anomaly_types=[AnomalyType.LOW_ENTROPY],
            entropy_score=1.5,
            repetition_score=0.3,
            z_score=2.0,
            details={"reason": "test"},
        )

        assert result.is_anomalous is True
        assert len(result.anomaly_types) == 1
        assert result.entropy_score == 1.5
        assert result.repetition_score == 0.3
        assert result.z_score == 2.0

    def test_anomaly_result_defaults(self) -> None:
        """Test AnomalyResult default values."""
        result = AnomalyResult(is_anomalous=False)

        assert result.is_anomalous is False
        assert result.anomaly_types == []
        assert result.entropy_score is None
        assert result.details == {}


class TestP03LearningAnomalyDetector:
    """Test P03LearningAnomalyDetector class."""

    def test_default_configuration(self) -> None:
        """Test detector with default configuration."""
        detector = P03LearningAnomalyDetector()

        assert detector.min_entropy_threshold == 2.0
        assert detector.repetition_threshold == 0.8
        assert detector.z_score_threshold == 3.0

    def test_custom_configuration(self) -> None:
        """Test detector with custom configuration."""
        detector = P03LearningAnomalyDetector(
            min_entropy_threshold=1.5,
            repetition_threshold=0.5,
            z_score_threshold=2.0,
            min_content_length=5,
        )

        assert detector.min_entropy_threshold == 1.5
        assert detector.repetition_threshold == 0.5
        assert detector.z_score_threshold == 2.0


class TestEntropyCalculation:
    """Test Shannon entropy calculation."""

    def test_entropy_of_empty_string(self) -> None:
        """Test entropy of empty string is zero."""
        detector = P03LearningAnomalyDetector()
        entropy = detector.calculate_entropy("")
        assert entropy == 0.0

    def test_entropy_of_single_char(self) -> None:
        """Test entropy of repeated single character."""
        detector = P03LearningAnomalyDetector()
        # "aaaaaaaaaa" - all same char = 0 entropy
        entropy = detector.calculate_entropy("aaaaaaaaaa")
        assert entropy == 0.0

    def test_entropy_of_varied_text(self) -> None:
        """Test entropy of varied text is higher."""
        detector = P03LearningAnomalyDetector()
        # Natural text has higher entropy
        entropy = detector.calculate_entropy("The quick brown fox jumps over the lazy dog")
        assert entropy > 3.0  # Natural English has ~4+ bits entropy

    def test_entropy_of_low_variety_text(self) -> None:
        """Test entropy of low variety text."""
        detector = P03LearningAnomalyDetector()
        # "abababab" - only 2 chars
        entropy = detector.calculate_entropy("abababab")
        assert entropy == pytest.approx(1.0, rel=0.01)

    def test_entropy_case_insensitive(self) -> None:
        """Test entropy calculation is case insensitive."""
        detector = P03LearningAnomalyDetector()
        entropy1 = detector.calculate_entropy("ABCD")
        entropy2 = detector.calculate_entropy("abcd")
        assert entropy1 == entropy2


class TestJaccardSimilarity:
    """Test Jaccard similarity calculation."""

    def test_similarity_identical_texts(self) -> None:
        """Test similarity of identical texts is 1.0."""
        detector = P03LearningAnomalyDetector()
        sim = detector.calculate_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_similarity_no_overlap(self) -> None:
        """Test similarity of non-overlapping texts is 0.0."""
        detector = P03LearningAnomalyDetector()
        sim = detector.calculate_similarity("hello world", "foo bar baz")
        assert sim == 0.0

    def test_similarity_partial_overlap(self) -> None:
        """Test similarity of partially overlapping texts."""
        detector = P03LearningAnomalyDetector()
        # "hello world" vs "hello there"
        # words1 = {hello, world}, words2 = {hello, there}
        # intersection = {hello} = 1
        # union = {hello, world, there} = 3
        # similarity = 1/3
        sim = detector.calculate_similarity("hello world", "hello there")
        assert sim == pytest.approx(1 / 3, rel=0.01)

    def test_similarity_empty_strings(self) -> None:
        """Test similarity of empty strings is 0.0."""
        detector = P03LearningAnomalyDetector()
        sim = detector.calculate_similarity("", "")
        assert sim == 0.0

    def test_similarity_one_empty(self) -> None:
        """Test similarity with one empty string is 0.0."""
        detector = P03LearningAnomalyDetector()
        sim = detector.calculate_similarity("hello", "")
        assert sim == 0.0


class TestDetectAnomalies:
    """Test full anomaly detection."""

    @pytest.mark.asyncio
    async def test_detect_low_entropy_anomaly(self) -> None:
        """Test detection of low entropy content."""
        detector = P03LearningAnomalyDetector(min_entropy_threshold=2.0)

        conn = AsyncMock()
        # No recent signals for repetition check
        conn.fetch = AsyncMock(return_value=[])
        # Not enough data for z-score
        conn.fetchrow = AsyncMock(return_value={"sample_count": 5})

        result = await detector.detect_anomalies(
            signal_id="sig_123",
            content="aaaaaaaaaaaaaaaaaaaaaa",  # Low entropy
            space_id="space_123",
            user_id="user_456",
            connection=conn,
        )

        assert result.is_anomalous is True
        assert AnomalyType.LOW_ENTROPY in result.anomaly_types
        assert result.entropy_score == pytest.approx(0.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_no_anomaly_for_short_low_entropy(self) -> None:
        """Test low entropy not flagged for short content."""
        detector = P03LearningAnomalyDetector(min_content_length=10)

        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.fetchrow = AsyncMock(return_value={"sample_count": 5})

        result = await detector.detect_anomalies(
            signal_id="sig_123",
            content="aaaa",  # Short + low entropy
            space_id="space_123",
            user_id="user_456",
            connection=conn,
        )

        assert AnomalyType.LOW_ENTROPY not in result.anomaly_types

    @pytest.mark.asyncio
    async def test_detect_repetitive_content(self) -> None:
        """Test detection of repetitive content from same user."""
        detector = P03LearningAnomalyDetector(repetition_threshold=0.8)

        conn = AsyncMock()
        # Recent signals with similar content
        conn.fetch = AsyncMock(
            return_value=[
                {"content": "this is a test message"},
                {"content": "something different"},
            ]
        )
        conn.fetchrow = AsyncMock(return_value={"sample_count": 5})

        result = await detector.detect_anomalies(
            signal_id="sig_123",
            content="this is a test message",  # Exact match with recent
            space_id="space_123",
            user_id="user_456",
            connection=conn,
        )

        assert result.is_anomalous is True
        assert AnomalyType.REPETITIVE_CONTENT in result.anomaly_types
        assert result.repetition_score == 1.0

    @pytest.mark.asyncio
    async def test_detect_statistical_outlier(self) -> None:
        """Test detection of statistical outlier by content length."""
        detector = P03LearningAnomalyDetector(z_score_threshold=3.0)

        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        # Average length 50, stddev 10, so 200 chars is outlier
        conn.fetchrow = AsyncMock(
            return_value={
                "avg_length": 50.0,
                "stddev_length": 10.0,
                "sample_count": 100,
            }
        )

        result = await detector.detect_anomalies(
            signal_id="sig_123",
            content="x" * 200,  # Way above average
            space_id="space_123",
            user_id="user_456",
            connection=conn,
        )

        assert result.is_anomalous is True
        assert AnomalyType.STATISTICAL_OUTLIER in result.anomaly_types
        # z-score = (200 - 50) / 10 = 15.0
        assert result.z_score == pytest.approx(15.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_no_outlier_when_insufficient_samples(self) -> None:
        """Test no outlier detection when sample count too low."""
        detector = P03LearningAnomalyDetector()

        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.fetchrow = AsyncMock(
            return_value={
                "avg_length": 50.0,
                "stddev_length": 10.0,
                "sample_count": 5,  # Below minimum
            }
        )

        result = await detector.detect_anomalies(
            signal_id="sig_123",
            content="x" * 200,
            space_id="space_123",
            user_id="user_456",
            connection=conn,
        )

        assert AnomalyType.STATISTICAL_OUTLIER not in result.anomaly_types
        assert result.z_score is None

    @pytest.mark.asyncio
    async def test_no_outlier_when_stddev_zero(self) -> None:
        """Test no outlier detection when standard deviation is zero."""
        detector = P03LearningAnomalyDetector()

        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.fetchrow = AsyncMock(
            return_value={
                "avg_length": 50.0,
                "stddev_length": 0.0,  # Zero stddev
                "sample_count": 100,
            }
        )

        result = await detector.detect_anomalies(
            signal_id="sig_123",
            content="normal content here",
            space_id="space_123",
            user_id="user_456",
            connection=conn,
        )

        assert AnomalyType.STATISTICAL_OUTLIER not in result.anomaly_types
        assert result.z_score is None

    @pytest.mark.asyncio
    async def test_multiple_anomalies_detected(self) -> None:
        """Test detection of multiple anomaly types simultaneously."""
        detector = P03LearningAnomalyDetector(
            min_entropy_threshold=2.0,
            repetition_threshold=0.8,
        )

        conn = AsyncMock()
        # Same low-entropy content as recent
        conn.fetch = AsyncMock(
            return_value=[
                {"content": "aaaaaaaaaaaaaaaa"},
            ]
        )
        conn.fetchrow = AsyncMock(return_value={"sample_count": 5})

        result = await detector.detect_anomalies(
            signal_id="sig_123",
            content="aaaaaaaaaaaaaaaa",  # Low entropy + repetitive
            space_id="space_123",
            user_id="user_456",
            connection=conn,
        )

        assert result.is_anomalous is True
        assert AnomalyType.LOW_ENTROPY in result.anomaly_types
        assert AnomalyType.REPETITIVE_CONTENT in result.anomaly_types

    @pytest.mark.asyncio
    async def test_no_anomalies_for_normal_content(self) -> None:
        """Test no anomalies for normal, varied content."""
        detector = P03LearningAnomalyDetector()

        conn = AsyncMock()
        conn.fetch = AsyncMock(
            return_value=[
                {"content": "something completely different"},
            ]
        )
        conn.fetchrow = AsyncMock(
            return_value={
                "avg_length": 30.0,
                "stddev_length": 10.0,
                "sample_count": 100,
            }
        )

        result = await detector.detect_anomalies(
            signal_id="sig_123",
            content="The quick brown fox jumps over the lazy dog",
            space_id="space_123",
            user_id="user_456",
            connection=conn,
        )

        assert result.is_anomalous is False
        assert len(result.anomaly_types) == 0

    @pytest.mark.asyncio
    async def test_metrics_emission_on_anomaly(self) -> None:
        """Test metrics are emitted when anomaly detected."""
        metrics = MagicMock()
        detector = P03LearningAnomalyDetector(metrics=metrics)

        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.fetchrow = AsyncMock(return_value={"sample_count": 5})

        await detector.detect_anomalies(
            signal_id="sig_123",
            content="aaaaaaaaaaaaaaaaaaa",  # Low entropy
            space_id="space_123",
            user_id="user_456",
            connection=conn,
        )

        assert metrics.emit.call_count >= 2
        emit_calls = [call[0][0] for call in metrics.emit.call_args_list]
        assert "p03_anomaly_checks_total" in emit_calls
        assert "p03_anomalies_detected_total" in emit_calls

    @pytest.mark.asyncio
    async def test_handles_null_recent_content(self) -> None:
        """Test handling of null content in recent signals."""
        detector = P03LearningAnomalyDetector()

        conn = AsyncMock()
        conn.fetch = AsyncMock(
            return_value=[
                {"content": None},
                {"content": "valid content"},
            ]
        )
        conn.fetchrow = AsyncMock(return_value={"sample_count": 5})

        result = await detector.detect_anomalies(
            signal_id="sig_123",
            content="some test content",
            space_id="space_123",
            user_id="user_456",
            connection=conn,
        )

        # Should complete without error
        assert result is not None

    @pytest.mark.asyncio
    async def test_handles_null_stats(self) -> None:
        """Test handling of null stats from database."""
        detector = P03LearningAnomalyDetector()

        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.fetchrow = AsyncMock(
            return_value={
                "avg_length": None,
                "stddev_length": None,
                "sample_count": 0,
            }
        )

        result = await detector.detect_anomalies(
            signal_id="sig_123",
            content="some test content",
            space_id="space_123",
            user_id="user_456",
            connection=conn,
        )

        # Should complete without error
        assert result.z_score is None


class TestCreateAnomalyDetector:
    """Test factory function."""

    def test_create_with_defaults(self) -> None:
        """Test factory with default parameters."""
        detector = create_anomaly_detector()

        assert isinstance(detector, P03LearningAnomalyDetector)
        assert detector.min_entropy_threshold == 2.0

    def test_create_with_custom_params(self) -> None:
        """Test factory with custom parameters."""
        metrics = MagicMock()
        detector = create_anomaly_detector(
            min_entropy_threshold=1.5,
            repetition_threshold=0.5,
            z_score_threshold=2.0,
            min_content_length=5,
            metrics=metrics,
        )

        assert detector.min_entropy_threshold == 1.5
        assert detector.repetition_threshold == 0.5
        assert detector.z_score_threshold == 2.0
