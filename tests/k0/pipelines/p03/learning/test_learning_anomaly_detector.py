"""
Tests for P03LearningAnomalyDetector.

Issue 6.2.17: P03LearningAnomalyDetector
"""

from __future__ import annotations

from typing import Any, List, Optional
from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03.learning.learning_anomaly_detector import (
    FeedbackSignal,
    LearningAnomalyResult,
    LearningAnomalyType,
    P03LearningAnomalyDetector,
    create_learning_anomaly_detector,
)

# ============================================================================
# Mock database connection
# ============================================================================


class MockRow:
    """Mock database row."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


class MockConnection:
    """Mock asyncpg connection for testing."""

    def __init__(self) -> None:
        self.executed: List[tuple] = []
        self._fetchrow_results: List[Optional[MockRow]] = []
        self._execute_results: List[str] = []

    def set_fetchrow_results(self, results: List[Optional[dict]]) -> None:
        """Set results for fetchrow() calls."""
        self._fetchrow_results = [MockRow(r) if r else None for r in results]

    def set_execute_results(self, results: List[str]) -> None:
        """Set results for execute() calls."""
        self._execute_results = results

    async def fetchrow(self, query: str, *args: Any) -> Optional[MockRow]:
        if self._fetchrow_results:
            return self._fetchrow_results.pop(0)
        return None

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        if self._execute_results:
            return self._execute_results.pop(0)
        return "UPDATE 1"


# ============================================================================
# Factory tests
# ============================================================================


class TestFactory:
    """Tests for create_learning_anomaly_detector factory."""

    def test_create_default(self) -> None:
        """Test factory with defaults."""
        detector = create_learning_anomaly_detector()
        assert detector is not None
        assert detector.drift_threshold == 0.20
        assert detector.quality_drop_threshold == 0.10

    def test_create_custom_thresholds(self) -> None:
        """Test factory with custom thresholds."""
        detector = create_learning_anomaly_detector(
            drift_threshold=0.30,
            quality_drop_threshold=0.15,
        )
        assert detector.drift_threshold == 0.30
        assert detector.quality_drop_threshold == 0.15

    def test_create_with_metrics(self) -> None:
        """Test factory with metrics exporter."""
        metrics = MagicMock()
        detector = create_learning_anomaly_detector(metrics=metrics)
        assert detector._metrics is metrics


# ============================================================================
# LearningAnomalyType tests
# ============================================================================


class TestLearningAnomalyType:
    """Tests for LearningAnomalyType enum."""

    def test_parameter_drift_value(self) -> None:
        """Test PARAMETER_DRIFT value."""
        assert LearningAnomalyType.PARAMETER_DRIFT.value == "PARAMETER_DRIFT"

    def test_contradictory_signals_value(self) -> None:
        """Test CONTRADICTORY_SIGNALS value."""
        assert LearningAnomalyType.CONTRADICTORY_SIGNALS.value == "CONTRADICTORY_SIGNALS"

    def test_formula_regression_value(self) -> None:
        """Test FORMULA_REGRESSION value."""
        assert LearningAnomalyType.FORMULA_REGRESSION.value == "FORMULA_REGRESSION"

    def test_quality_degradation_value(self) -> None:
        """Test QUALITY_DEGRADATION value."""
        assert LearningAnomalyType.QUALITY_DEGRADATION.value == "QUALITY_DEGRADATION"


# ============================================================================
# FeedbackSignal tests
# ============================================================================


class TestFeedbackSignal:
    """Tests for FeedbackSignal dataclass."""

    def test_create_minimal(self) -> None:
        """Test creating minimal signal."""
        signal = FeedbackSignal(
            signal_id="s1",
            entity_id="e1",
            feedback_type="BOOST",
        )
        assert signal.signal_id == "s1"
        assert signal.salience_delta is None
        assert signal.created_at == 0

    def test_create_with_delta(self) -> None:
        """Test creating signal with salience delta."""
        signal = FeedbackSignal(
            signal_id="s1",
            entity_id="e1",
            feedback_type="BOOST",
            salience_delta=0.5,
            created_at=1000,
        )
        assert signal.salience_delta == 0.5
        assert signal.created_at == 1000


# ============================================================================
# LearningAnomalyResult tests
# ============================================================================


class TestLearningAnomalyResult:
    """Tests for LearningAnomalyResult dataclass."""

    def test_not_anomalous(self) -> None:
        """Test non-anomalous result."""
        result = LearningAnomalyResult(is_anomalous=False)
        assert result.is_anomalous is False
        assert result.requires_review is False

    def test_anomalous_requires_review(self) -> None:
        """Test anomalous result that requires review."""
        result = LearningAnomalyResult(
            is_anomalous=True,
            anomaly_type=LearningAnomalyType.PARAMETER_DRIFT,
            action_taken="LEARNING_PAUSED",
        )
        assert result.requires_review is True

    def test_anomalous_auto_rollback(self) -> None:
        """Test anomalous result with auto-rollback."""
        result = LearningAnomalyResult(
            is_anomalous=True,
            anomaly_type=LearningAnomalyType.FORMULA_REGRESSION,
            action_taken="AUTO_ROLLBACK",
        )
        assert result.requires_review is False


# ============================================================================
# check_parameter_drift tests
# ============================================================================


class TestCheckParameterDrift:
    """Tests for check_parameter_drift method."""

    @pytest.mark.asyncio
    async def test_no_previous_value(self) -> None:
        """Test no drift when no previous value exists."""
        detector = P03LearningAnomalyDetector()
        conn = MockConnection()
        conn.set_fetchrow_results([None])

        result = await detector.check_parameter_drift(
            "decay_rate",
            "space1",
            0.5,
            connection=conn,
        )

        assert result.is_anomalous is False

    @pytest.mark.asyncio
    async def test_zero_previous_value(self) -> None:
        """Test no drift when previous value is zero."""
        detector = P03LearningAnomalyDetector()
        conn = MockConnection()
        conn.set_fetchrow_results([{"current_value": 0}])

        result = await detector.check_parameter_drift(
            "decay_rate",
            "space1",
            0.5,
            connection=conn,
        )

        assert result.is_anomalous is False

    @pytest.mark.asyncio
    async def test_drift_below_threshold(self) -> None:
        """Test no anomaly when drift is below threshold."""
        detector = P03LearningAnomalyDetector(drift_threshold=0.20)
        conn = MockConnection()
        conn.set_fetchrow_results([{"current_value": 1.0}])

        # 15% change: 1.0 -> 1.15
        result = await detector.check_parameter_drift(
            "decay_rate",
            "space1",
            1.15,
            connection=conn,
        )

        assert result.is_anomalous is False

    @pytest.mark.asyncio
    async def test_drift_above_threshold(self) -> None:
        """Test anomaly detected when drift exceeds threshold."""
        detector = P03LearningAnomalyDetector(drift_threshold=0.20)
        conn = MockConnection()
        conn.set_fetchrow_results([{"current_value": 1.0}])
        conn.set_execute_results(["UPDATE 1"])

        # 30% change: 1.0 -> 1.30
        result = await detector.check_parameter_drift(
            "decay_rate",
            "space1",
            1.30,
            connection=conn,
        )

        assert result.is_anomalous is True
        assert result.anomaly_type == LearningAnomalyType.PARAMETER_DRIFT
        assert result.action_taken == "LEARNING_PAUSED"
        assert result.details["drift_pct"] == pytest.approx(0.30)

    @pytest.mark.asyncio
    async def test_drift_negative_change(self) -> None:
        """Test drift detection for negative changes."""
        detector = P03LearningAnomalyDetector(drift_threshold=0.20)
        conn = MockConnection()
        conn.set_fetchrow_results([{"current_value": 1.0}])
        conn.set_execute_results(["UPDATE 1"])

        # -30% change: 1.0 -> 0.70
        result = await detector.check_parameter_drift(
            "decay_rate",
            "space1",
            0.70,
            connection=conn,
        )

        assert result.is_anomalous is True
        assert result.details["drift_pct"] == pytest.approx(0.30)

    @pytest.mark.asyncio
    async def test_drift_emits_metric(self) -> None:
        """Test that drift detection emits metric."""
        metrics = MagicMock()
        detector = P03LearningAnomalyDetector(metrics=metrics)
        conn = MockConnection()
        conn.set_fetchrow_results([{"current_value": 1.0}])
        conn.set_execute_results(["UPDATE 1"])

        await detector.check_parameter_drift(
            "decay_rate",
            "space1",
            1.50,  # 50% change
            connection=conn,
        )

        metrics.emit.assert_called()


# ============================================================================
# check_contradictory_signals tests
# ============================================================================


class TestCheckContradictorySignals:
    """Tests for check_contradictory_signals method."""

    @pytest.mark.asyncio
    async def test_too_few_signals(self) -> None:
        """Test no detection with insufficient signals."""
        detector = P03LearningAnomalyDetector(min_signals_for_contradiction=2)

        signals = [
            FeedbackSignal("s1", "e1", "BOOST", salience_delta=0.5),
        ]

        result = await detector.check_contradictory_signals("e1", signals)

        assert result.is_anomalous is False

    @pytest.mark.asyncio
    async def test_no_contradiction_all_positive(self) -> None:
        """Test no contradiction when all deltas positive."""
        detector = P03LearningAnomalyDetector()

        signals = [
            FeedbackSignal("s1", "e1", "BOOST", salience_delta=0.5),
            FeedbackSignal("s2", "e1", "BOOST", salience_delta=0.3),
            FeedbackSignal("s3", "e1", "BOOST", salience_delta=0.2),
        ]

        result = await detector.check_contradictory_signals("e1", signals)

        assert result.is_anomalous is False

    @pytest.mark.asyncio
    async def test_no_contradiction_all_negative(self) -> None:
        """Test no contradiction when all deltas negative."""
        detector = P03LearningAnomalyDetector()

        signals = [
            FeedbackSignal("s1", "e1", "DECAY", salience_delta=-0.5),
            FeedbackSignal("s2", "e1", "DECAY", salience_delta=-0.3),
        ]

        result = await detector.check_contradictory_signals("e1", signals)

        assert result.is_anomalous is False

    @pytest.mark.asyncio
    async def test_contradiction_detected(self) -> None:
        """Test contradiction detected with opposing deltas."""
        detector = P03LearningAnomalyDetector()

        signals = [
            FeedbackSignal("s1", "e1", "BOOST", salience_delta=0.5),
            FeedbackSignal("s2", "e1", "BOOST", salience_delta=-0.3),
        ]

        result = await detector.check_contradictory_signals("e1", signals)

        assert result.is_anomalous is True
        assert result.anomaly_type == LearningAnomalyType.CONTRADICTORY_SIGNALS
        assert result.action_taken == "FLAGGED_FOR_REVIEW"

    @pytest.mark.asyncio
    async def test_contradiction_different_types_no_detect(self) -> None:
        """Test no contradiction for different feedback types."""
        detector = P03LearningAnomalyDetector()

        signals = [
            FeedbackSignal("s1", "e1", "BOOST", salience_delta=0.5),
            FeedbackSignal("s2", "e1", "DECAY", salience_delta=-0.3),  # Different type
        ]

        result = await detector.check_contradictory_signals("e1", signals)

        # No contradiction because types are different
        assert result.is_anomalous is False

    @pytest.mark.asyncio
    async def test_contradiction_none_deltas_ignored(self) -> None:
        """Test signals with None deltas are ignored."""
        detector = P03LearningAnomalyDetector()

        signals = [
            FeedbackSignal("s1", "e1", "BOOST", salience_delta=0.5),
            FeedbackSignal("s2", "e1", "BOOST", salience_delta=None),
        ]

        result = await detector.check_contradictory_signals("e1", signals)

        # Only one valid delta, not enough for contradiction
        assert result.is_anomalous is False


# ============================================================================
# check_formula_regression tests
# ============================================================================


class TestCheckFormulaRegression:
    """Tests for check_formula_regression method."""

    @pytest.mark.asyncio
    async def test_no_history(self) -> None:
        """Test no regression when no history exists."""
        detector = P03LearningAnomalyDetector()
        conn = MockConnection()
        conn.set_fetchrow_results([None])

        result = await detector.check_formula_regression(
            "decay_formula",
            "space1",
            0.8,
            connection=conn,
        )

        assert result.is_anomalous is False

    @pytest.mark.asyncio
    async def test_no_avg_quality(self) -> None:
        """Test no regression when avg_quality is None."""
        detector = P03LearningAnomalyDetector()
        conn = MockConnection()
        conn.set_fetchrow_results([{"avg_quality": None}])

        result = await detector.check_formula_regression(
            "decay_formula",
            "space1",
            0.8,
            connection=conn,
        )

        assert result.is_anomalous is False

    @pytest.mark.asyncio
    async def test_quality_improved(self) -> None:
        """Test no regression when quality improved."""
        detector = P03LearningAnomalyDetector(quality_drop_threshold=0.10)
        conn = MockConnection()
        conn.set_fetchrow_results([{"avg_quality": 0.7}])

        # Quality went from 0.7 to 0.8 (improvement)
        result = await detector.check_formula_regression(
            "decay_formula",
            "space1",
            0.8,
            connection=conn,
        )

        assert result.is_anomalous is False

    @pytest.mark.asyncio
    async def test_quality_drop_below_threshold(self) -> None:
        """Test no regression when drop is below threshold."""
        detector = P03LearningAnomalyDetector(quality_drop_threshold=0.10)
        conn = MockConnection()
        conn.set_fetchrow_results([{"avg_quality": 0.8}])

        # 5% drop: 0.8 -> 0.76
        result = await detector.check_formula_regression(
            "decay_formula",
            "space1",
            0.76,
            connection=conn,
        )

        assert result.is_anomalous is False

    @pytest.mark.asyncio
    async def test_quality_drop_above_threshold(self) -> None:
        """Test regression detected when drop exceeds threshold."""
        detector = P03LearningAnomalyDetector(quality_drop_threshold=0.10)
        conn = MockConnection()
        conn.set_fetchrow_results([{"avg_quality": 0.8}])
        conn.set_execute_results(["INSERT 1", "UPDATE 1"])

        # 15% drop: 0.8 -> 0.68
        result = await detector.check_formula_regression(
            "decay_formula",
            "space1",
            0.68,
            connection=conn,
        )

        assert result.is_anomalous is True
        assert result.anomaly_type == LearningAnomalyType.FORMULA_REGRESSION
        assert result.action_taken == "AUTO_ROLLBACK"
        assert result.details["quality_drop"] == pytest.approx(0.15)


# ============================================================================
# check_all tests
# ============================================================================


class TestCheckAll:
    """Tests for check_all method."""

    @pytest.mark.asyncio
    async def test_no_anomalies(self) -> None:
        """Test when no anomalies are detected."""
        detector = P03LearningAnomalyDetector()
        conn = MockConnection()
        conn.set_fetchrow_results(
            [
                {"current_value": 1.0},  # For drift check
                {"avg_quality": 0.9},  # For regression check
            ]
        )

        signals = [
            FeedbackSignal("s1", "e1", "BOOST", salience_delta=0.5),
        ]

        results = await detector.check_all(
            param_key="decay_rate",
            space_id="space1",
            current_value=1.05,  # 5% change - below threshold
            entity_id="e1",
            signals=signals,
            formula_name="decay_formula",
            current_quality=0.85,  # 5% drop - below threshold
            connection=conn,
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_multiple_anomalies(self) -> None:
        """Test when multiple anomalies are detected."""
        detector = P03LearningAnomalyDetector()
        conn = MockConnection()
        conn.set_fetchrow_results(
            [
                {"current_value": 1.0},  # For drift check - will trigger
                {"avg_quality": 0.9},  # For regression check - will trigger
            ]
        )
        conn.set_execute_results(["UPDATE 1", "INSERT 1", "UPDATE 1"])

        signals = [
            FeedbackSignal("s1", "e1", "BOOST", salience_delta=0.5),
            FeedbackSignal("s2", "e1", "BOOST", salience_delta=-0.3),  # Contradiction
        ]

        results = await detector.check_all(
            param_key="decay_rate",
            space_id="space1",
            current_value=1.50,  # 50% change - above threshold
            entity_id="e1",
            signals=signals,
            formula_name="decay_formula",
            current_quality=0.70,  # 22% drop - above threshold
            connection=conn,
        )

        assert len(results) == 3
        types = [r.anomaly_type for r in results]
        assert LearningAnomalyType.PARAMETER_DRIFT in types
        assert LearningAnomalyType.CONTRADICTORY_SIGNALS in types
        assert LearningAnomalyType.FORMULA_REGRESSION in types


# ============================================================================
# Learning pause/resume tests
# ============================================================================


class TestLearningPauseResume:
    """Tests for learning pause and resume functionality."""

    @pytest.mark.asyncio
    async def test_is_learning_paused_initially_false(self) -> None:
        """Test learning is not paused initially."""
        detector = P03LearningAnomalyDetector()

        assert detector.is_learning_paused("decay_rate", "space1") is False

    @pytest.mark.asyncio
    async def test_pause_learning_updates_state(self) -> None:
        """Test _pause_learning updates internal state."""
        detector = P03LearningAnomalyDetector()
        conn = MockConnection()

        await detector._pause_learning("decay_rate", "space1", connection=conn)

        assert detector.is_learning_paused("decay_rate", "space1") is True

    @pytest.mark.asyncio
    async def test_resume_learning_clears_state(self) -> None:
        """Test resume_learning clears paused state."""
        detector = P03LearningAnomalyDetector()
        conn = MockConnection()

        # Pause first
        await detector._pause_learning("decay_rate", "space1", connection=conn)
        assert detector.is_learning_paused("decay_rate", "space1") is True

        # Resume
        result = await detector.resume_learning(
            "decay_rate",
            "space1",
            "reviewer1",
            connection=conn,
        )

        assert result is True
        assert detector.is_learning_paused("decay_rate", "space1") is False

    @pytest.mark.asyncio
    async def test_resume_learning_not_paused(self) -> None:
        """Test resume_learning returns False when not paused."""
        detector = P03LearningAnomalyDetector()
        conn = MockConnection()
        conn.set_execute_results(["UPDATE 0"])  # No rows updated

        result = await detector.resume_learning(
            "decay_rate",
            "space1",
            "reviewer1",
            connection=conn,
        )

        assert result is False

    def test_get_paused_params(self) -> None:
        """Test get_paused_params returns copy of paused set."""
        detector = P03LearningAnomalyDetector()
        detector._paused_params.add("space1:decay_rate")

        paused = detector.get_paused_params()

        assert "space1:decay_rate" in paused
        # Verify it's a copy
        paused.add("space2:other_param")
        assert "space2:other_param" not in detector._paused_params


# ============================================================================
# Metrics emission tests
# ============================================================================


class TestMetricsEmission:
    """Tests for metrics emission."""

    @pytest.mark.asyncio
    async def test_drift_emits_anomaly_metric(self) -> None:
        """Test drift detection emits anomaly metric."""
        metrics = MagicMock()
        detector = P03LearningAnomalyDetector(metrics=metrics)
        conn = MockConnection()
        conn.set_fetchrow_results([{"current_value": 1.0}])
        conn.set_execute_results(["UPDATE 1"])

        await detector.check_parameter_drift(
            "decay_rate",
            "space1",
            1.50,  # 50% drift
            connection=conn,
        )

        # Should emit anomaly detected metric
        calls = [call for call in metrics.emit.call_args_list]
        anomaly_calls = [c for c in calls if "anomaly_detected" in str(c)]
        assert len(anomaly_calls) >= 1

    @pytest.mark.asyncio
    async def test_pause_emits_metric(self) -> None:
        """Test pause learning emits metric."""
        metrics = MagicMock()
        detector = P03LearningAnomalyDetector(metrics=metrics)
        conn = MockConnection()

        await detector._pause_learning("decay_rate", "space1", connection=conn)

        metrics.emit.assert_called_with(
            "p03_learning_paused_total",
            1.0,
            param_key="decay_rate",
        )

    @pytest.mark.asyncio
    async def test_resume_emits_metric(self) -> None:
        """Test resume learning emits metric."""
        metrics = MagicMock()
        detector = P03LearningAnomalyDetector(metrics=metrics)
        conn = MockConnection()

        detector._paused_params.add("space1:decay_rate")

        await detector.resume_learning(
            "decay_rate",
            "space1",
            "reviewer1",
            connection=conn,
        )

        metrics.emit.assert_called_with(
            "p03_learning_resumed_total",
            1.0,
            param_key="decay_rate",
        )
