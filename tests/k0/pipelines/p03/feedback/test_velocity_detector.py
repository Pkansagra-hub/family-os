"""
Tests for VelocityAnomalyDetector — Issue 6.2.12.

Tests velocity spike detection including:
- Baseline and recent rate calculation
- Spike detection with configurable multiplier
- User-specific velocity tracking
- Metrics emission
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.pipelines.p03.feedback.velocity_detector import (
    VelocityAnomalyDetector,
    VelocityResult,
    create_velocity_detector,
)


class TestVelocityResult:
    """Test VelocityResult dataclass."""

    def test_velocity_result_creation(self) -> None:
        """Test VelocityResult can be created."""
        result = VelocityResult(
            is_spike=True,
            recent_rate=50.0,
            baseline_rate=5.0,
            spike_multiplier=10.0,
            threshold_multiplier=10.0,
        )

        assert result.is_spike is True
        assert result.recent_rate == 50.0
        assert result.baseline_rate == 5.0
        assert result.spike_multiplier == 10.0
        assert result.threshold_multiplier == 10.0

    def test_velocity_result_no_spike(self) -> None:
        """Test VelocityResult for non-spike case."""
        result = VelocityResult(
            is_spike=False,
            recent_rate=5.0,
            baseline_rate=5.0,
            spike_multiplier=1.0,
            threshold_multiplier=10.0,
        )

        assert result.is_spike is False
        assert result.spike_multiplier == 1.0

    def test_velocity_result_is_frozen(self) -> None:
        """Test VelocityResult is immutable."""
        result = VelocityResult(
            is_spike=True,
            recent_rate=50.0,
            baseline_rate=5.0,
            spike_multiplier=10.0,
            threshold_multiplier=10.0,
        )

        with pytest.raises(AttributeError):
            result.is_spike = False  # type: ignore[misc]


class TestVelocityAnomalyDetector:
    """Test VelocityAnomalyDetector class."""

    def test_default_configuration(self) -> None:
        """Test detector with default configuration."""
        detector = VelocityAnomalyDetector()

        assert detector.spike_multiplier == 10.0
        assert detector.recent_window_seconds == 300  # 5 minutes
        assert detector.baseline_window_seconds == 3600  # 60 minutes

    def test_custom_configuration(self) -> None:
        """Test detector with custom configuration."""
        detector = VelocityAnomalyDetector(
            spike_multiplier=5.0,
            recent_window_minutes=10,
            baseline_window_minutes=120,
            min_baseline_count=20,
        )

        assert detector.spike_multiplier == 5.0
        assert detector.recent_window_seconds == 600  # 10 minutes
        assert detector.baseline_window_seconds == 7200  # 120 minutes

    @pytest.mark.asyncio
    async def test_detect_no_spike_when_below_threshold(self) -> None:
        """Test no spike detected when recent rate is below threshold."""
        detector = VelocityAnomalyDetector(spike_multiplier=10.0)

        conn = AsyncMock()
        # Recent count: 10 signals in 5 min = 2/min
        # Baseline count: 120 signals in 60 min = 2/min
        # Multiplier: 2/2 = 1.0 (below 10.0 threshold)
        conn.fetchrow = AsyncMock(
            side_effect=[
                {"count": 10},  # recent
                {"count": 120},  # baseline
            ]
        )

        result = await detector.detect_velocity_spike(
            "space_123",
            connection=conn,
        )

        assert result.is_spike is False
        assert result.recent_rate == pytest.approx(2.0, rel=0.01)
        assert result.baseline_rate == pytest.approx(2.0, rel=0.01)
        assert result.spike_multiplier == pytest.approx(1.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_detect_spike_when_above_threshold(self) -> None:
        """Test spike detected when recent rate exceeds threshold."""
        detector = VelocityAnomalyDetector(
            spike_multiplier=10.0,
            min_baseline_count=10,
        )

        conn = AsyncMock()
        # Recent count: 100 signals in 5 min = 20/min
        # Baseline count: 60 signals in 60 min = 1/min
        # Multiplier: 20/1 = 20.0 (above 10.0 threshold)
        conn.fetchrow = AsyncMock(
            side_effect=[
                {"count": 100},  # recent
                {"count": 60},  # baseline
            ]
        )

        result = await detector.detect_velocity_spike(
            "space_123",
            connection=conn,
        )

        assert result.is_spike is True
        assert result.recent_rate == pytest.approx(20.0, rel=0.01)
        assert result.baseline_rate == pytest.approx(1.0, rel=0.01)
        assert result.spike_multiplier == pytest.approx(20.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_no_spike_when_baseline_count_too_low(self) -> None:
        """Test no spike when baseline has insufficient samples."""
        detector = VelocityAnomalyDetector(min_baseline_count=10)

        conn = AsyncMock()
        # Recent: 50 signals, Baseline: 5 signals (below min_baseline_count)
        conn.fetchrow = AsyncMock(
            side_effect=[
                {"count": 50},  # recent
                {"count": 5},  # baseline (below min)
            ]
        )

        result = await detector.detect_velocity_spike(
            "space_123",
            connection=conn,
        )

        assert result.is_spike is False
        assert result.spike_multiplier == 0.0

    @pytest.mark.asyncio
    async def test_no_spike_when_baseline_is_zero(self) -> None:
        """Test no spike when baseline rate is zero."""
        detector = VelocityAnomalyDetector()

        conn = AsyncMock()
        # Baseline is zero
        conn.fetchrow = AsyncMock(
            side_effect=[
                {"count": 50},  # recent
                {"count": 0},  # baseline
            ]
        )

        result = await detector.detect_velocity_spike(
            "space_123",
            connection=conn,
        )

        assert result.is_spike is False
        assert result.baseline_rate == 0.0
        assert result.spike_multiplier == 0.0

    @pytest.mark.asyncio
    async def test_detect_velocity_spike_with_user_filter(self) -> None:
        """Test velocity detection for specific user."""
        detector = VelocityAnomalyDetector(
            spike_multiplier=10.0,
            min_baseline_count=10,
        )

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            side_effect=[
                {"count": 100},  # recent (user-specific)
                {"count": 60},  # baseline (user-specific)
            ]
        )

        result = await detector.detect_velocity_spike(
            "space_123",
            user_id="user_456",
            connection=conn,
        )

        assert result.is_spike is True
        # Verify user-specific queries were made
        assert conn.fetchrow.call_count == 2
        # Check that user_id was passed to queries
        calls = conn.fetchrow.call_args_list
        assert "user_456" in str(calls[0])
        assert "user_456" in str(calls[1])

    @pytest.mark.asyncio
    async def test_get_current_velocity(self) -> None:
        """Test get_current_velocity convenience method."""
        detector = VelocityAnomalyDetector()

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            side_effect=[
                {"count": 25},  # recent: 25/5 = 5/min
                {"count": 300},  # baseline
            ]
        )

        velocity = await detector.get_current_velocity(
            "space_123",
            connection=conn,
        )

        assert velocity == pytest.approx(5.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_get_velocity_trend(self) -> None:
        """Test get_velocity_trend convenience method."""
        detector = VelocityAnomalyDetector(min_baseline_count=10)

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            side_effect=[
                {"count": 50},  # recent: 50/5 = 10/min
                {"count": 120},  # baseline: 120/60 = 2/min
            ]
        )

        recent, baseline, multiplier = await detector.get_velocity_trend(
            "space_123",
            connection=conn,
        )

        assert recent == pytest.approx(10.0, rel=0.01)
        assert baseline == pytest.approx(2.0, rel=0.01)
        assert multiplier == pytest.approx(5.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_metrics_emission_on_spike(self) -> None:
        """Test metrics are emitted when spike detected."""
        metrics = MagicMock()
        detector = VelocityAnomalyDetector(
            spike_multiplier=10.0,
            min_baseline_count=10,
            metrics=metrics,
        )

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            side_effect=[
                {"count": 100},  # recent
                {"count": 60},  # baseline
            ]
        )

        await detector.detect_velocity_spike(
            "space_123",
            connection=conn,
        )

        # Verify metrics were emitted
        assert metrics.emit.call_count >= 2
        emit_calls = [call[0][0] for call in metrics.emit.call_args_list]
        assert "p03_velocity_checks_total" in emit_calls
        assert "p03_velocity_spikes_total" in emit_calls

    @pytest.mark.asyncio
    async def test_metrics_emission_no_spike(self) -> None:
        """Test metrics emitted when no spike."""
        metrics = MagicMock()
        detector = VelocityAnomalyDetector(metrics=metrics)

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            side_effect=[
                {"count": 10},  # recent
                {"count": 120},  # baseline
            ]
        )

        await detector.detect_velocity_spike(
            "space_123",
            connection=conn,
        )

        # Only check counter should be emitted
        assert metrics.emit.call_count == 1
        assert metrics.emit.call_args[0][0] == "p03_velocity_checks_total"

    @pytest.mark.asyncio
    async def test_handles_null_count(self) -> None:
        """Test handling of null count from database."""
        detector = VelocityAnomalyDetector()

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)

        result = await detector.detect_velocity_spike(
            "space_123",
            connection=conn,
        )

        assert result.is_spike is False
        assert result.recent_rate == 0.0

    @pytest.mark.asyncio
    async def test_spike_at_exact_threshold(self) -> None:
        """Test spike detection at exact threshold boundary."""
        detector = VelocityAnomalyDetector(
            spike_multiplier=10.0,
            min_baseline_count=10,
        )

        conn = AsyncMock()
        # Recent: 50/5 = 10/min, Baseline: 60/60 = 1/min
        # Multiplier: 10/1 = 10.0 (exactly at threshold)
        conn.fetchrow = AsyncMock(
            side_effect=[
                {"count": 50},  # recent
                {"count": 60},  # baseline
            ]
        )

        result = await detector.detect_velocity_spike(
            "space_123",
            connection=conn,
        )

        # Exactly at threshold should be spike (>=)
        assert result.is_spike is True
        assert result.spike_multiplier == pytest.approx(10.0, rel=0.01)


class TestCreateVelocityDetector:
    """Test factory function."""

    def test_create_with_defaults(self) -> None:
        """Test factory with default parameters."""
        detector = create_velocity_detector()

        assert isinstance(detector, VelocityAnomalyDetector)
        assert detector.spike_multiplier == 10.0

    def test_create_with_custom_params(self) -> None:
        """Test factory with custom parameters."""
        metrics = MagicMock()
        detector = create_velocity_detector(
            spike_multiplier=5.0,
            recent_window_minutes=10,
            baseline_window_minutes=120,
            min_baseline_count=20,
            metrics=metrics,
        )

        assert detector.spike_multiplier == 5.0
        assert detector.recent_window_seconds == 600
        assert detector.baseline_window_seconds == 7200
