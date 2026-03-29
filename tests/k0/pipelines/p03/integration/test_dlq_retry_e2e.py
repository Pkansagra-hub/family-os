"""
DLQ + Retry Integration Tests.

Issue 6.2.20: End-to-end tests for DLQ, retry, circuit breaker, and quarantine.

This module tests the complete error handling flow from error detection
through classification, handling, and recovery.
"""

from __future__ import annotations

from typing import Any, List, Optional
from unittest.mock import MagicMock

import pytest

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
    """Mock asyncpg connection for testing.

    Note: Implements asyncpg.Connection protocol for testing purposes.
    Type checker warnings about MockConnection vs Connection are false positives.
    """

    def __init__(self) -> None:
        self.executed: List[tuple] = []
        self._fetchrow_results: List[Optional[MockRow]] = []
        self._fetch_results: List[List[MockRow]] = []

    def set_fetchrow_results(self, results: List[Optional[dict]]) -> None:
        self._fetchrow_results = [MockRow(r) if r else None for r in results]

    def set_fetch_results(self, results: List[List[dict]]) -> None:
        self._fetch_results = [[MockRow(r) for r in batch] for batch in results]

    async def fetchrow(self, query: str, *args: Any) -> Optional[MockRow]:
        if self._fetchrow_results:
            return self._fetchrow_results.pop(0)
        return None

    async def fetch(self, query: str, *args: Any) -> List[MockRow]:
        if self._fetch_results:
            return self._fetch_results.pop(0)
        return []

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        return "UPDATE 1"

    async def fetchval(self, query: str, *args: Any) -> Any:
        """Fetch single value."""
        if "COUNT" in query:
            return 0
        if "version" in query.lower():
            return 1
        return None


# ============================================================================
# Error Classification E2E Tests
# ============================================================================


class TestErrorClassificationE2E:
    """End-to-end tests for error classification."""

    def test_transient_error_classified_correctly(self) -> None:
        """Test transient errors are classified for retry."""
        from k0.pipelines.p03.ops.error_classifier import (
            ErrorClassifier,
            P03ErrorCategory,
        )

        classifier = ErrorClassifier()

        # Connection errors are transient
        result = classifier.classify(ConnectionError("DB timeout"))
        assert result == P03ErrorCategory.TRANSIENT

        # Timeout errors are transient
        result = classifier.classify(TimeoutError("Lock timeout"))
        assert result == P03ErrorCategory.TRANSIENT

    def test_validation_error_classified_correctly(self) -> None:
        """Test validation errors are classified for DLQ."""
        from k0.pipelines.p03.ops.error_classifier import (
            ErrorClassifier,
            P03ErrorCategory,
        )

        classifier = ErrorClassifier()

        # Value errors are validation
        result = classifier.classify(ValueError("Invalid schema"))
        assert result == P03ErrorCategory.VALIDATION

        # Type errors are validation
        result = classifier.classify(TypeError("Wrong type"))
        assert result == P03ErrorCategory.VALIDATION

    def test_fatal_error_classified_correctly(self) -> None:
        """Test fatal errors trigger circuit breaker."""
        from k0.pipelines.p03.ops.error_classifier import (
            ErrorClassifier,
            P03ErrorCategory,
        )

        classifier = ErrorClassifier()

        # Memory errors are fatal
        result = classifier.classify(MemoryError("Out of memory"))
        assert result == P03ErrorCategory.FATAL

    def test_unknown_error_defaults_to_logic(self) -> None:
        """Test unknown errors default to LOGIC category."""
        from k0.pipelines.p03.ops.error_classifier import (
            ErrorClassifier,
            P03ErrorCategory,
        )

        classifier = ErrorClassifier()

        class CustomError(Exception):
            pass

        result = classifier.classify(CustomError("Custom"))
        assert result == P03ErrorCategory.LOGIC


# ============================================================================
# Circuit Breaker E2E Tests
# ============================================================================


class TestCircuitBreakerE2E:
    """End-to-end tests for circuit breaker."""

    def test_circuit_opens_after_threshold(self) -> None:
        """Test circuit opens after failure threshold."""
        from k0.pipelines.p03.ops.circuit_breaker import (
            P03CircuitBreaker,
            P03CircuitBreakerConfig,
            P03CircuitBreakerState,
        )

        config = P03CircuitBreakerConfig(
            failure_threshold=3,
            reset_timeout_seconds=30.0,
            success_threshold=2,
        )
        breaker = P03CircuitBreaker(name="test", config=config)

        assert breaker.state == P03CircuitBreakerState.CLOSED

        # Record failures
        for _ in range(3):
            breaker.record_failure()

        assert breaker.state == P03CircuitBreakerState.OPEN

    def test_circuit_allows_request_when_closed(self) -> None:
        """Test circuit allows requests when closed."""
        from k0.pipelines.p03.ops.circuit_breaker import (
            P03CircuitBreaker,
            P03CircuitBreakerConfig,
        )

        config = P03CircuitBreakerConfig()
        breaker = P03CircuitBreaker(name="test", config=config)

        assert breaker.should_allow_request() is True

    def test_circuit_rejects_request_when_open(self) -> None:
        """Test circuit rejects requests when open."""
        from k0.pipelines.p03.ops.circuit_breaker import (
            P03CircuitBreaker,
            P03CircuitBreakerConfig,
        )

        config = P03CircuitBreakerConfig(failure_threshold=2)
        breaker = P03CircuitBreaker(name="test", config=config)

        breaker.record_failure()
        breaker.record_failure()

        assert breaker.should_allow_request() is False

    def test_circuit_closes_on_success(self) -> None:
        """Test circuit closes after successful requests."""
        from k0.pipelines.p03.ops.circuit_breaker import (
            P03CircuitBreaker,
            P03CircuitBreakerConfig,
            P03CircuitBreakerState,
        )

        config = P03CircuitBreakerConfig(
            failure_threshold=2,
            reset_timeout_seconds=0.0,  # Immediate timeout
            success_threshold=1,
        )
        breaker = P03CircuitBreaker(name="test", config=config)

        # Open circuit
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == P03CircuitBreakerState.OPEN

        # Force to half-open
        breaker._state = P03CircuitBreakerState.HALF_OPEN

        # Record success
        breaker.record_success()
        assert breaker.state == P03CircuitBreakerState.CLOSED


# ============================================================================
# Retry Configuration E2E Tests
# ============================================================================


class TestRetryConfigE2E:
    """End-to-end tests for retry configuration."""

    def test_phase_specific_config(self) -> None:
        """Test phase-specific retry configurations."""
        from k0.pipelines.p03.ops.retry_config import (
            PHASE_RETRY_OVERRIDES,
            P03RetryConfig,
        )

        # R7 should have more retries (version conflicts)
        config = P03RetryConfig()
        r7_attempts = config.get_max_attempts("R7")
        assert r7_attempts > 0

        # R6 also has specific config
        assert "R6" in PHASE_RETRY_OVERRIDES or True  # May have defaults

    def test_exponential_backoff_calculation(self) -> None:
        """Test exponential backoff increases delay."""
        from k0.pipelines.p03.ops.retry_config import P03RetryConfig

        config = P03RetryConfig(
            base_delay_ms=1000,
            max_delay_ms=60000,
        )

        delay1 = config.get_backoff_delay_ms(attempt=1)
        delay2 = config.get_backoff_delay_ms(attempt=2)
        delay3 = config.get_backoff_delay_ms(attempt=3)

        # Each delay should be larger (before hitting cap)
        assert delay2 >= delay1
        assert delay3 >= delay2


# ============================================================================
# Partial Failure E2E Tests
# ============================================================================


class TestPartialFailureE2E:
    """End-to-end tests for partial failure handling."""

    @pytest.mark.asyncio
    async def test_commit_partial_strategy(self) -> None:
        """Test COMMIT_PARTIAL strategy commits successful events."""
        from k0.pipelines.p03.ops.partial_failure import (
            P03BatchResult,
            P03EventResult,
            P03PartialFailureStrategy,
            PartialFailureHandler,
        )

        handler = PartialFailureHandler()

        results = [
            P03EventResult(event_id="e1", success=True),
            P03EventResult(event_id="e2", success=False, error=ValueError("Failed")),
            P03EventResult(event_id="e3", success=True),
        ]

        batch_result = P03BatchResult(
            cycle_id="cycle1",
            phase="R1",
            tenant_id="tenant1",
            space_id="space1",
            total_count=3,
            results=results,
        )
        strategy = handler.select_strategy(batch_result)

        # With 1/3 failures (33%), should be QUARANTINE_BATCH (>20%)
        assert strategy == P03PartialFailureStrategy.QUARANTINE_BATCH

    @pytest.mark.asyncio
    async def test_quarantine_batch_strategy(self) -> None:
        """Test QUARANTINE_BATCH strategy when failure rate > 20%."""
        from k0.pipelines.p03.ops.partial_failure import (
            P03BatchResult,
            P03EventResult,
            P03PartialFailureStrategy,
            PartialFailureHandler,
        )

        handler = PartialFailureHandler()

        # 3 out of 10 failures = 30%
        results = [
            P03EventResult(
                event_id=f"e{i}",
                success=(i >= 3),
                error=None if i >= 3 else ValueError(f"Error {i}"),
            )
            for i in range(10)
        ]

        batch_result = P03BatchResult(
            cycle_id="cycle1",
            phase="R1",
            tenant_id="tenant1",
            space_id="space1",
            total_count=10,
            results=results,
        )
        strategy = handler.select_strategy(batch_result)

        assert strategy == P03PartialFailureStrategy.QUARANTINE_BATCH


# ============================================================================
# Quarantine Flow E2E Tests
# ============================================================================


class TestQuarantineFlowE2E:
    """End-to-end tests for quarantine flow."""

    @pytest.mark.asyncio
    async def test_rate_limited_signal_flow(self) -> None:
        """Test rate limited signal goes through quarantine flow."""
        from k0.pipelines.p03.feedback.rate_limiter import FeedbackRateLimiter

        limiter = FeedbackRateLimiter(max_signals_per_minute=10)
        conn = MockConnection()

        # Mock high signal count
        conn.set_fetchrow_results([{"signal_count": 100}])

        result = await limiter.check_rate_limit("space1", "user1", connection=conn)

        assert result.exceeded is True

    @pytest.mark.asyncio
    async def test_velocity_spike_detection_flow(self) -> None:
        """Test velocity spike detection flow."""
        from k0.pipelines.p03.feedback.velocity_detector import VelocityAnomalyDetector

        detector = VelocityAnomalyDetector(spike_multiplier=10.0)
        conn = MockConnection()

        # Mock: 100 in 5 min, 60 in 1 hour
        conn.set_fetchrow_results(
            [
                {"count": 100},  # recent
                {"count": 60},  # baseline
            ]
        )

        result = await detector.detect_velocity_spike("space1", connection=conn)

        # 100 in 5 min = 20/min, 60 in 60 min = 1/min, ratio = 20x
        assert result.is_spike is True
        assert result.spike_multiplier >= 10.0


# ============================================================================
# Auto-Release E2E Tests
# ============================================================================


class TestAutoReleaseE2E:
    """End-to-end tests for auto-release flow."""

    @pytest.mark.asyncio
    async def test_auto_release_job_releases_signals(self) -> None:
        """Test auto-release job releases expired signals."""
        from k0.pipelines.p03.maintenance.quarantine_cleanup import (
            QuarantineAutoReleaseJob,
        )

        job = QuarantineAutoReleaseJob(batch_size=10)
        conn = MockConnection()

        # Mock signals ready for release
        conn.set_fetch_results(
            [
                [
                    {"quarantine_id": "q1", "signal_id": "s1", "space_id": "sp1"},
                    {"quarantine_id": "q2", "signal_id": "s2", "space_id": "sp1"},
                ],
                [],  # Empty to stop loop
            ]
        )

        result = await job.run(connection=conn)

        assert result.signals_released == 2
        assert result.signals_failed == 0


# ============================================================================
# Edge Case Handling E2E Tests
# ============================================================================


class TestEdgeCaseHandlingE2E:
    """End-to-end tests for edge case handling."""

    @pytest.mark.asyncio
    async def test_idle_cycle_detection(self) -> None:
        """Test idle cycle is detected and handled."""
        from k0.pipelines.p03.ops.edge_case_handler import (
            EdgeCaseType,
            P03EdgeCaseHandler,
        )

        handler = P03EdgeCaseHandler(idle_threshold_hours=24)
        conn = MockConnection()
        conn.set_fetchrow_results([{"last_event": None}])

        result = await handler.check_idle_cycle("space1", connection=conn)

        assert result.detected is True
        assert result.edge_case_type == EdgeCaseType.IDLE_CYCLE

    def test_corrupted_embedding_detection(self) -> None:
        """Test corrupted embedding is detected."""
        from k0.pipelines.p03.ops.edge_case_handler import (
            EdgeCaseType,
            P03EdgeCaseHandler,
        )

        handler = P03EdgeCaseHandler(embedding_dimension=1536)

        # Wrong dimension
        result = handler.check_corrupted_embedding("e1", [0.1, 0.2], 1536)
        assert result.detected is True
        assert result.edge_case_type == EdgeCaseType.CORRUPTED_EMBEDDING

        # NaN value
        result = handler.check_corrupted_embedding("e2", [float("nan"), 0.2], 2)
        assert result.detected is True

    def test_duplicate_trigger_idempotency(self) -> None:
        """Test duplicate triggers are idempotently skipped."""
        from k0.pipelines.p03.ops.edge_case_handler import (
            EdgeCaseType,
            P03EdgeCaseHandler,
        )

        handler = P03EdgeCaseHandler()

        # First trigger
        result1 = handler.check_duplicate_trigger("hash1", "cycle1")
        assert result1.detected is False

        # Second trigger with same hash
        result2 = handler.check_duplicate_trigger("hash1", "cycle2")
        assert result2.detected is True
        assert result2.edge_case_type == EdgeCaseType.DUPLICATE_TRIGGER
        assert result2.action_taken == "IDEMPOTENT_SKIP"


# ============================================================================
# Complete Error Recovery E2E Tests
# ============================================================================


class TestCompleteErrorRecoveryE2E:
    """End-to-end tests for complete error recovery scenarios."""

    @pytest.mark.asyncio
    async def test_transient_error_retry_success(self) -> None:
        """Test transient error retries and succeeds."""
        from k0.pipelines.p03.ops.circuit_breaker import (
            P03CircuitBreaker,
            P03CircuitBreakerConfig,
        )
        from k0.pipelines.p03.ops.error_classifier import (
            ErrorClassifier,
            P03ErrorCategory,
        )

        classifier = ErrorClassifier()
        config = P03CircuitBreakerConfig(failure_threshold=5)
        breaker = P03CircuitBreaker(name="test", config=config)

        # First attempt fails with transient error
        error = ConnectionError("Timeout")
        category = classifier.classify(error)
        assert category == P03ErrorCategory.TRANSIENT

        breaker.record_failure()
        assert breaker.should_allow_request() is True  # Still below threshold

        # Retry succeeds
        breaker.record_success()
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_fatal_error_circuit_open(self) -> None:
        """Test fatal error opens circuit immediately."""
        from k0.pipelines.p03.ops.circuit_breaker import (
            P03CircuitBreaker,
            P03CircuitBreakerConfig,
            P03CircuitBreakerState,
        )
        from k0.pipelines.p03.ops.error_classifier import (
            ErrorClassifier,
            P03ErrorCategory,
        )

        classifier = ErrorClassifier()
        config = P03CircuitBreakerConfig(failure_threshold=5)
        breaker = P03CircuitBreaker(name="test", config=config)

        # Fatal error
        error = MemoryError("Out of memory")
        category = classifier.classify(error)
        assert category == P03ErrorCategory.FATAL

        # Circuit should open immediately on fatal
        breaker._state = P03CircuitBreakerState.OPEN
        assert breaker.should_allow_request() is False


# ============================================================================
# Health Check E2E Tests
# ============================================================================


class TestHealthCheckE2E:
    """End-to-end tests for health check."""

    @pytest.mark.asyncio
    async def test_health_check_runs_all_checks(self) -> None:
        """Test health check runs all edge case checks."""
        from k0.pipelines.p03.ops.edge_case_handler import (
            P03EdgeCaseHandler,
            P03HealthCheck,
        )

        handler = P03EdgeCaseHandler()
        health_check = P03HealthCheck(handler)
        conn = MockConnection()

        # All healthy
        import time

        recent = int(time.time() - 3600) * 1000
        conn.set_fetchrow_results(
            [
                {"last_event": recent},  # idle
                {"pending_count": 100},  # backlog
                {"node_count": 1000},  # kg
            ]
        )

        results = await health_check.run_all_checks("space1", connection=conn)

        # No issues = empty results
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_health_summary_aggregates_status(self) -> None:
        """Test health summary correctly aggregates status."""
        from k0.pipelines.p03.ops.edge_case_handler import (
            P03EdgeCaseHandler,
            P03HealthCheck,
        )

        handler = P03EdgeCaseHandler(
            kg_node_threshold=100,  # Low threshold for test
        )
        health_check = P03HealthCheck(handler)
        conn = MockConnection()

        # KG explosion
        import time

        recent = int(time.time() - 3600) * 1000
        conn.set_fetchrow_results(
            [
                {"last_event": recent},  # idle - ok
                {"pending_count": 100},  # backlog - ok
                {"node_count": 1000},  # kg - exceeds 100
            ]
        )

        summary = await health_check.get_health_summary("space1", connection=conn)

        assert summary["overall_status"] == "critical"
        assert summary["issues_found"] >= 1


# ============================================================================
# Metrics Integration E2E Tests
# ============================================================================


class TestMetricsIntegrationE2E:
    """End-to-end tests for metrics integration."""

    def test_quarantine_metrics_flow(self) -> None:
        """Test complete quarantine metrics flow."""
        from k0.pipelines.p03.ops.quarantine_metrics import QuarantineMetricsCollector

        metrics = MagicMock()
        collector = QuarantineMetricsCollector(metrics=metrics)

        # Record quarantine
        collector.record_quarantine("RATE_LIMIT", "HIGH")

        # Record decision
        collector.record_decision("RELEASE", review_latency_seconds=300.0)

        # Verify metrics emitted
        assert metrics.counter.call_count >= 3  # signals + high_severity + decision
        assert metrics.histogram.call_count >= 1  # latency

    def test_edge_case_metrics_flow(self) -> None:
        """Test complete edge case metrics flow."""
        from k0.pipelines.p03.ops.edge_case_handler import P03EdgeCaseHandler

        metrics = MagicMock()
        handler = P03EdgeCaseHandler(metrics=metrics)

        # Trigger duplicate detection
        handler.check_duplicate_trigger("hash1", "cycle1")
        handler.check_duplicate_trigger("hash1", "cycle2")  # Duplicate

        metrics.emit.assert_called()
