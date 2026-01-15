"""Tests for Quarantine Detector (Issue 6.2.10).

Tests quarantine detection for rate limits and velocity spikes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from k0.pipelines.p03.feedback.quarantine_detector import (
    AUTO_RELEASE_SECONDS,
    REASON_SEVERITY_MAP,
    QuarantineDetector,
    QuarantineReason,
    QuarantineResult,
    QuarantineSeverity,
    create_quarantine_detector,
)


class TestQuarantineReason:
    """Tests for QuarantineReason enum."""

    def test_has_rate_limit(self) -> None:
        """Test RATE_LIMIT reason exists."""
        assert QuarantineReason.RATE_LIMIT.value == "RATE_LIMIT"

    def test_has_velocity_spike(self) -> None:
        """Test VELOCITY_SPIKE reason exists."""
        assert QuarantineReason.VELOCITY_SPIKE.value == "VELOCITY_SPIKE"

    def test_has_anomaly(self) -> None:
        """Test ANOMALY reason exists."""
        assert QuarantineReason.ANOMALY.value == "ANOMALY"

    def test_has_entropy(self) -> None:
        """Test ENTROPY reason exists."""
        assert QuarantineReason.ENTROPY.value == "ENTROPY"


class TestQuarantineSeverity:
    """Tests for QuarantineSeverity enum."""

    def test_has_low(self) -> None:
        """Test LOW severity exists."""
        assert QuarantineSeverity.LOW.value == "LOW"

    def test_has_medium(self) -> None:
        """Test MEDIUM severity exists."""
        assert QuarantineSeverity.MEDIUM.value == "MEDIUM"

    def test_has_high(self) -> None:
        """Test HIGH severity exists."""
        assert QuarantineSeverity.HIGH.value == "HIGH"


class TestReasonSeverityMapping:
    """Tests for reason to severity mapping."""

    def test_rate_limit_is_low(self) -> None:
        """Test RATE_LIMIT defaults to LOW severity."""
        assert REASON_SEVERITY_MAP[QuarantineReason.RATE_LIMIT] == QuarantineSeverity.LOW

    def test_velocity_spike_is_medium(self) -> None:
        """Test VELOCITY_SPIKE defaults to MEDIUM severity."""
        assert REASON_SEVERITY_MAP[QuarantineReason.VELOCITY_SPIKE] == QuarantineSeverity.MEDIUM

    def test_anomaly_is_high(self) -> None:
        """Test ANOMALY defaults to HIGH severity."""
        assert REASON_SEVERITY_MAP[QuarantineReason.ANOMALY] == QuarantineSeverity.HIGH

    def test_entropy_is_high(self) -> None:
        """Test ENTROPY defaults to HIGH severity."""
        assert REASON_SEVERITY_MAP[QuarantineReason.ENTROPY] == QuarantineSeverity.HIGH


class TestQuarantineResult:
    """Tests for QuarantineResult dataclass."""

    def test_not_quarantined(self) -> None:
        """Test creating not-quarantined result."""
        result = QuarantineResult(quarantined=False)
        assert result.quarantined is False
        assert result.quarantine_id is None
        assert result.reason is None

    def test_quarantined(self) -> None:
        """Test creating quarantined result."""
        result = QuarantineResult(
            quarantined=True,
            quarantine_id="q-123",
            reason=QuarantineReason.RATE_LIMIT,
            severity=QuarantineSeverity.LOW,
            auto_release_at=1234567890,
        )
        assert result.quarantined is True
        assert result.quarantine_id == "q-123"
        assert result.reason == QuarantineReason.RATE_LIMIT


class TestQuarantineDetector:
    """Tests for QuarantineDetector class."""

    @pytest.fixture
    def detector(self) -> QuarantineDetector:
        """Create detector with defaults."""
        return QuarantineDetector()

    @pytest.fixture
    def mock_connection(self) -> Mock:
        """Create mock database connection."""
        mock = Mock()
        mock.fetchrow = AsyncMock()
        mock.execute = AsyncMock()
        return mock


class TestDetectorProperties(TestQuarantineDetector):
    """Tests for detector properties."""

    def test_rate_limit_property(self, detector: QuarantineDetector) -> None:
        """Test rate_limit property."""
        assert detector.rate_limit == 100

    def test_velocity_multiplier_property(self, detector: QuarantineDetector) -> None:
        """Test velocity_multiplier property."""
        assert detector.velocity_multiplier == 10.0


class TestCheckAndQuarantine(TestQuarantineDetector):
    """Tests for check_and_quarantine method."""

    @pytest.mark.asyncio
    async def test_no_quarantine_when_under_limit(
        self, detector: QuarantineDetector, mock_connection: Mock
    ) -> None:
        """Test no quarantine when under rate limit."""
        # First call: rate limit check (signal_count < 100)
        # Second call: velocity recent window
        # Third call: velocity baseline window
        mock_connection.fetchrow.side_effect = [
            {"signal_count": 10},  # Rate limit check: 10 < 100 limit
            {"count": 5},  # Recent window: 5 signals
            {"count": 60},  # Baseline: 60 signals (1/min), recent is 1/min - no spike
        ]

        result = await detector.check_and_quarantine(
            signal_id="sig-1",
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert result.quarantined is False

    @pytest.mark.asyncio
    async def test_quarantine_on_rate_limit(
        self, detector: QuarantineDetector, mock_connection: Mock
    ) -> None:
        """Test quarantine triggered by rate limit."""
        # First call is rate limit check
        mock_connection.fetchrow.side_effect = [
            {"signal_count": 100},  # At rate limit
        ]
        mock_connection.execute.return_value = "INSERT 1"

        result = await detector.check_and_quarantine(
            signal_id="sig-1",
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert result.quarantined is True
        assert result.reason == QuarantineReason.RATE_LIMIT
        assert result.severity == QuarantineSeverity.LOW

    @pytest.mark.asyncio
    async def test_quarantine_on_velocity_spike(
        self, detector: QuarantineDetector, mock_connection: Mock
    ) -> None:
        """Test quarantine triggered by velocity spike."""
        mock_connection.fetchrow.side_effect = [
            {"signal_count": 50},  # Under rate limit
            {"count": 100},  # Recent window (20 per minute)
            {"count": 60},  # Baseline (1 per minute) - 20x spike
        ]
        mock_connection.execute.return_value = "INSERT 1"

        result = await detector.check_and_quarantine(
            signal_id="sig-1",
            space_id="space-1",
            user_id="user-1",
            connection=mock_connection,
        )

        assert result.quarantined is True
        assert result.reason == QuarantineReason.VELOCITY_SPIKE
        assert result.severity == QuarantineSeverity.MEDIUM


class TestQuarantineForAnomaly(TestQuarantineDetector):
    """Tests for quarantine_for_anomaly method."""

    @pytest.mark.asyncio
    async def test_quarantine_anomaly(
        self, detector: QuarantineDetector, mock_connection: Mock
    ) -> None:
        """Test manual quarantine for anomaly."""
        mock_connection.execute.return_value = "INSERT 1"

        result = await detector.quarantine_for_anomaly(
            signal_id="sig-1",
            space_id="space-1",
            reason=QuarantineReason.ANOMALY,
            connection=mock_connection,
        )

        assert result.quarantined is True
        assert result.reason == QuarantineReason.ANOMALY
        assert result.severity == QuarantineSeverity.HIGH

    @pytest.mark.asyncio
    async def test_quarantine_entropy(
        self, detector: QuarantineDetector, mock_connection: Mock
    ) -> None:
        """Test manual quarantine for entropy."""
        mock_connection.execute.return_value = "INSERT 1"

        result = await detector.quarantine_for_anomaly(
            signal_id="sig-1",
            space_id="space-1",
            reason=QuarantineReason.ENTROPY,
            connection=mock_connection,
        )

        assert result.quarantined is True
        assert result.reason == QuarantineReason.ENTROPY


class TestReleaseAndDiscard(TestQuarantineDetector):
    """Tests for release and discard methods."""

    @pytest.mark.asyncio
    async def test_release_signal(
        self, detector: QuarantineDetector, mock_connection: Mock
    ) -> None:
        """Test releasing quarantined signal."""
        mock_connection.execute.return_value = "UPDATE 1"

        released = await detector.release_signal(
            quarantine_id="q-123",
            reviewer_id="reviewer-1",
            connection=mock_connection,
        )

        assert released is True
        mock_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_discard_signal(
        self, detector: QuarantineDetector, mock_connection: Mock
    ) -> None:
        """Test discarding quarantined signal."""
        mock_connection.execute.return_value = "UPDATE 1"

        discarded = await detector.discard_signal(
            quarantine_id="q-123",
            reviewer_id="reviewer-1",
            connection=mock_connection,
        )

        assert discarded is True


class TestPendingCount(TestQuarantineDetector):
    """Tests for get_pending_count method."""

    @pytest.mark.asyncio
    async def test_get_pending_count(
        self, detector: QuarantineDetector, mock_connection: Mock
    ) -> None:
        """Test getting pending count."""
        mock_connection.fetchrow.return_value = {"count": 5}

        count = await detector.get_pending_count(
            space_id="space-1",
            connection=mock_connection,
        )

        assert count == 5


class TestAutoRelease(TestQuarantineDetector):
    """Tests for process_auto_releases method."""

    @pytest.mark.asyncio
    async def test_process_auto_releases(
        self, detector: QuarantineDetector, mock_connection: Mock
    ) -> None:
        """Test processing auto-releases."""
        mock_connection.execute.return_value = "UPDATE 3"

        count = await detector.process_auto_releases(connection=mock_connection)

        assert count == 3


class TestAutoReleaseSeconds:
    """Tests for AUTO_RELEASE_SECONDS constant."""

    def test_auto_release_is_48_hours(self) -> None:
        """Test auto-release is 48 hours."""
        assert AUTO_RELEASE_SECONDS == 48 * 60 * 60


class TestCreateQuarantineDetector:
    """Tests for create_quarantine_detector factory."""

    def test_creates_detector(self) -> None:
        """Test factory creates detector."""
        detector = create_quarantine_detector()
        assert isinstance(detector, QuarantineDetector)

    def test_custom_rate_limit(self) -> None:
        """Test factory accepts custom rate limit."""
        detector = create_quarantine_detector(rate_limit_per_minute=50)
        assert detector.rate_limit == 50

    def test_custom_velocity_multiplier(self) -> None:
        """Test factory accepts custom velocity multiplier."""
        detector = create_quarantine_detector(velocity_spike_multiplier=5.0)
        assert detector.velocity_multiplier == 5.0

    def test_accepts_metrics(self) -> None:
        """Test factory accepts metrics."""
        mock_metrics = Mock()
        detector = create_quarantine_detector(metrics=mock_metrics)
        assert detector._metrics is mock_metrics
