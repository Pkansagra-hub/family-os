"""
Circuit Breaker Failure Recorder.

This module implements detailed failure recording and analysis for circuit breakers.
Records failure history (timestamp, type, exception, latency) to enable debugging,
root cause analysis, and pattern detection.

Use Cases (ADR-0009, ADR-0009c):
    - Debugging circuit breaker behavior
    - Root cause analysis (why did circuit open?)
    - Pattern detection (timeouts vs exceptions vs slow calls)
    - Alerting (failure rate exceeds threshold)
    - Adaptive threshold tuning (learning loop)

Performance:
    - Record failure: <0.5ms (append to deque)
    - Get failure history: <1ms (copy deque)
    - Calculate patterns: <5ms (aggregate failures)
    - Memory: ~500B per failure record (100 failures = 50KB)

Trade-offs:
    ✅ Rich debugging context (exception, latency, trace_id)
    ✅ Pattern detection (identify common failure modes)
    ✅ Fast access (<1ms for recent failures)
    ⚠️ Memory overhead (~50KB per service for 100 failures)
    ⚠️ Retention limited (100 failures, ~10 minutes at 10 failures/min)

Integration Points:
    - Called by CircuitBreakerFSM on failure
    - Exports failure metrics to Prometheus
    - Provides failure history API for debugging
    - Integrated with learning loop (adaptive thresholds)

Related ADRs:
    - ADR-0009: Circuit Breaker Pattern (failure tracking)
    - ADR-0009a: FSM Implementation (failure recording)
    - ADR-0009c: Metrics & Observability (circuit_breaker_failures_total)

Author: @resilience-team
Created: 2025-10-27
Status: STUB (Implementation Required)
"""

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FailureRecord:
    """
    Record of a single failure detected by circuit breaker.

    Attributes:
        timestamp: Unix timestamp when failure occurred (seconds)
        service_name: Name of the service that failed
        failure_type: Type of failure (timeout, exception, slow_call)
        exception_type: Type of exception raised (if applicable)
        exception_message: Exception message (if applicable)
        latency_ms: Operation latency in milliseconds
        cognitive_trace_id: Trace ID for correlation (if available)
        circuit_state: Circuit state when failure occurred (CLOSED, HALF_OPEN)

    Example:
        ```python
        record = FailureRecord(
            timestamp=1698360000.0,
            service_name="tool_runner",
            failure_type="timeout",
            exception_type="asyncio.TimeoutError",
            exception_message="Operation timed out after 5.0s",
            latency_ms=5000.0,
            cognitive_trace_id="trace_abc123",
            circuit_state="CLOSED"
        )
        ```
    """

    timestamp: float
    service_name: str
    failure_type: str  # "timeout" | "exception" | "slow_call"
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    latency_ms: Optional[float] = None
    cognitive_trace_id: Optional[str] = None
    circuit_state: Optional[str] = None


class FailureRecorder:
    """
    Record and Analyze Failures for Circuit Breakers.

    Maintains a sliding window of recent failures for each service, enabling
    debugging, root cause analysis, and pattern detection. Failures are stored
    in-memory using collections.deque for efficient append/rotation.

    Features:
        - Record failure details (timestamp, type, exception, latency)
        - Get recent failure history (last N failures)
        - Calculate failure patterns (rate, common types)
        - Export failure metrics to Prometheus
        - Automatic rotation (FIFO, max 100 failures per service)

    Memory Management:
        - Max 100 failures per service (~50KB)
        - Automatic rotation (oldest failures dropped)
        - Typical usage: 10 failures/min × 10 min = 100 failures

    Example Usage:
        ```python
        from k1.l5_infrastructure.resilience.failure_recorder import FailureRecorder

        recorder = FailureRecorder(max_failures_per_service=100)

        # Record failure
        recorder.record_failure(
            service_name="tool_runner",
            failure_type="timeout",
            exception=asyncio.TimeoutError("Timeout after 5s"),
            latency_ms=5000.0,
            cognitive_trace_id="trace_abc123",
            circuit_state="CLOSED"
        )

        # Get recent failures
        failures = recorder.get_failure_history(service_name="tool_runner", limit=10)
        for failure in failures:
            print(f"{failure.timestamp}: {failure.failure_type} ({failure.latency_ms}ms)")

        # Calculate patterns
        patterns = recorder.calculate_failure_patterns(service_name="tool_runner")
        print(f"Failure rate: {patterns['failure_rate_per_minute']}/min")
        print(f"Common failure type: {patterns['most_common_type']}")
        ```

    ADR References:
        - ADR-0009: "Record failure details for debugging"
        - ADR-0009c: "Export circuit_breaker_failures_total metric"

    WARD Test Example:
        ```python
        from ward import test
        import asyncio
        from k1.l5_infrastructure.resilience.failure_recorder import (
            FailureRecorder,
            FailureRecord
        )

        @test("failure recorder stores failure details")
        def _():
            recorder = FailureRecorder()

            recorder.record_failure(
                service_name="test_service",
                failure_type="timeout",
                exception=asyncio.TimeoutError("Timeout"),
                latency_ms=5000.0
            )

            failures = recorder.get_failure_history("test_service")
            assert len(failures) == 1
            assert failures[0].failure_type == "timeout"
            assert failures[0].latency_ms == 5000.0

        @test("failure recorder rotates old failures")
        def _():
            recorder = FailureRecorder(max_failures_per_service=3)

            # Record 5 failures (max 3)
            for i in range(5):
                recorder.record_failure(
                    service_name="test_service",
                    failure_type="timeout",
                    latency_ms=float(i * 1000)
                )

            # Only last 3 should be retained
            failures = recorder.get_failure_history("test_service")
            assert len(failures) == 3
            assert failures[0].latency_ms == 4000.0  # Most recent

        @test("failure recorder calculates patterns")
        def _():
            recorder = FailureRecorder()

            # Record mix of failures
            for i in range(10):
                recorder.record_failure(
                    service_name="test_service",
                    failure_type="timeout" if i % 2 == 0 else "exception",
                    latency_ms=5000.0
                )

            patterns = recorder.calculate_failure_patterns("test_service")
            assert patterns['total_failures'] == 10
            assert patterns['most_common_type'] == "timeout"
        ```
    """

    def __init__(self, max_failures_per_service: int = 100):
        """
        Initialize failure recorder.

        Args:
            max_failures_per_service: Maximum failures to retain per service
                                     (default: 100, ~50KB per service)

        Performance:
            - Initialization: <0.1ms (no I/O, simple assignment)
        """
        # TODO(@resilience-team): Initialize failure recorder
        # 1. Store max_failures_per_service for rotation
        # 2. Create failures dict: {service_name: deque(maxlen=100)}
        # 3. Create logger for observability
        self.max_failures_per_service = max_failures_per_service
        self.failures: Dict[str, deque] = {}
        self.logger = logger.bind(component="failure_recorder")

    def record_failure(
        self,
        service_name: str,
        failure_type: str,
        exception: Optional[Exception] = None,
        latency_ms: Optional[float] = None,
        cognitive_trace_id: Optional[str] = None,
        circuit_state: Optional[str] = None,
    ) -> None:
        """
        Record failure details.

        Appends failure record to service's failure history deque. Automatically
        rotates old failures when max_failures_per_service reached.

        Execution Flow:
            1. Create FailureRecord with timestamp and details
            2. Get or create deque for service
            3. Append record to deque (automatic rotation)
            4. Log failure (debug level)

        Args:
            service_name: Name of the service that failed
            failure_type: Type of failure (timeout, exception, slow_call)
            exception: Exception raised (if applicable)
            latency_ms: Operation latency in milliseconds
            cognitive_trace_id: Trace ID for correlation (optional)
            circuit_state: Circuit state when failure occurred (optional)

        Performance:
            - Target: <0.5ms (deque append + log)
            - No disk I/O (in-memory only)
            - No locks (thread-safe deque)

        Side Effects:
            - Appends to failures deque (automatic rotation)
            - Emits debug log

        Example:
            ```python
            # Record timeout
            recorder.record_failure(
                service_name="tool_runner",
                failure_type="timeout",
                exception=asyncio.TimeoutError("Timeout after 5s"),
                latency_ms=5000.0,
                cognitive_trace_id="trace_abc123",
                circuit_state="CLOSED"
            )

            # Record exception
            recorder.record_failure(
                service_name="model_hub_local",
                failure_type="exception",
                exception=RuntimeError("Model crashed"),
                latency_ms=1500.0,
                cognitive_trace_id="trace_def456",
                circuit_state="HALF_OPEN"
            )

            # Record slow call
            recorder.record_failure(
                service_name="k0_bridge",
                failure_type="slow_call",
                latency_ms=150.0,  # >100ms threshold
                cognitive_trace_id="trace_ghi789",
                circuit_state="CLOSED"
            )
            ```

        Logging Output:
            ```json
            {
                "event": "failure_recorded",
                "service_name": "tool_runner",
                "failure_type": "timeout",
                "latency_ms": 5000.0,
                "circuit_state": "CLOSED",
                "level": "debug"
            }
            ```

        ADR Reference:
            - ADR-0009: "Record failure details for debugging"
        """
        # TODO(@resilience-team): Implement failure recording
        # 1. Create FailureRecord:
        #    record = FailureRecord(
        #        timestamp=time.time(),
        #        service_name=service_name,
        #        failure_type=failure_type,
        #        exception_type=type(exception).__name__ if exception else None,
        #        exception_message=str(exception) if exception else None,
        #        latency_ms=latency_ms,
        #        cognitive_trace_id=cognitive_trace_id,
        #        circuit_state=circuit_state
        #    )
        # 2. Get or create deque:
        #    if service_name not in self.failures:
        #        self.failures[service_name] = deque(maxlen=self.max_failures_per_service)
        # 3. Append record:
        #    self.failures[service_name].append(record)
        # 4. Log:
        #    self.logger.debug(
        #        "failure_recorded",
        #        service_name=service_name,
        #        failure_type=failure_type,
        #        latency_ms=latency_ms,
        #        circuit_state=circuit_state
        #    )
        pass

    def get_failure_history(
        self, service_name: str, limit: int = 100
    ) -> List[FailureRecord]:
        """
        Get recent failures for service.

        Returns failure history in reverse chronological order (most recent first).

        Args:
            service_name: Name of the service
            limit: Maximum number of failures to return (default: 100)

        Returns:
            List of FailureRecord (most recent first)

        Performance:
            - Target: <1ms (copy deque to list)
            - No disk I/O (in-memory only)

        Example:
            ```python
            # Get last 10 failures
            failures = recorder.get_failure_history("tool_runner", limit=10)
            for failure in failures:
                print(f"{failure.timestamp}: {failure.failure_type}")
            ```

        ADR Reference:
            - ADR-0009: "Provide failure history for debugging"
        """
        # TODO(@resilience-team): Implement failure history retrieval
        # 1. Check if service has failures:
        #    if service_name not in self.failures:
        #        return []
        # 2. Get deque and convert to list:
        #    all_failures = list(self.failures[service_name])
        # 3. Reverse (most recent first):
        #    all_failures.reverse()
        # 4. Limit results:
        #    return all_failures[:limit]
        return []

    def calculate_failure_patterns(
        self, service_name: str, time_window_minutes: int = 10
    ) -> Dict[str, Any]:
        """
        Calculate failure patterns for service.

        Aggregates failure data to identify common failure modes, failure rate,
        and trends. Used for adaptive threshold tuning and alerting.

        Execution Flow:
            1. Get failures within time window
            2. Count failures by type (timeout, exception, slow_call)
            3. Calculate failure rate (failures per minute)
            4. Identify most common failure type
            5. Calculate average latency per type

        Args:
            service_name: Name of the service
            time_window_minutes: Analysis window in minutes (default: 10)

        Returns:
            Dict with keys:
                - total_failures: Total failures in window
                - failure_rate_per_minute: Failures per minute
                - most_common_type: Most frequent failure type
                - failure_counts: Dict of {type: count}
                - average_latency_ms: Dict of {type: avg_latency}

        Performance:
            - Target: <5ms (aggregate 100 failures)
            - No disk I/O (in-memory only)

        Example:
            ```python
            patterns = recorder.calculate_failure_patterns("tool_runner")
            print(f"Failure rate: {patterns['failure_rate_per_minute']}/min")
            print(f"Most common: {patterns['most_common_type']}")
            print(f"Timeouts: {patterns['failure_counts']['timeout']}")
            print(f"Avg timeout latency: {patterns['average_latency_ms']['timeout']}ms")
            ```

        Use Cases:
            - Adaptive threshold tuning (if timeout rate high, increase threshold)
            - Alerting (if failure rate >10/min, send alert)
            - Root cause analysis (identify primary failure mode)

        ADR Reference:
            - ADR-0009: "Calculate failure patterns for adaptive tuning"
        """
        # TODO(@resilience-team): Implement pattern calculation
        # 1. Get failures in time window:
        #    now = time.time()
        #    cutoff = now - (time_window_minutes * 60)
        #    recent_failures = [f for f in self.failures.get(service_name, [])
        #                       if f.timestamp >= cutoff]
        # 2. Count by type:
        #    counts = {}
        #    latencies = {}
        #    for failure in recent_failures:
        #        counts[failure.failure_type] = counts.get(failure.failure_type, 0) + 1
        #        if failure.latency_ms:
        #            if failure.failure_type not in latencies:
        #                latencies[failure.failure_type] = []
        #            latencies[failure.failure_type].append(failure.latency_ms)
        # 3. Calculate patterns:
        #    return {
        #        "total_failures": len(recent_failures),
        #        "failure_rate_per_minute": len(recent_failures) / time_window_minutes,
        #        "most_common_type": max(counts, key=counts.get) if counts else None,
        #        "failure_counts": counts,
        #        "average_latency_ms": {
        #            ftype: sum(lats) / len(lats)
        #            for ftype, lats in latencies.items()
        #        }
        #    }
        return {
            "total_failures": 0,
            "failure_rate_per_minute": 0.0,
            "most_common_type": None,
            "failure_counts": {},
            "average_latency_ms": {},
        }

    def clear_history(self, service_name: str) -> None:
        """
        Clear failure history for service.

        Removes all recorded failures for the specified service. Used for testing
        or manual cleanup.

        Args:
            service_name: Name of the service

        Side Effects:
            - Clears failures deque for service

        Example:
            ```python
            recorder.clear_history("tool_runner")
            assert len(recorder.get_failure_history("tool_runner")) == 0
            ```
        """
        # TODO(@resilience-team): Implement history clearing
        # if service_name in self.failures:
        #     self.failures[service_name].clear()
        #     self.logger.info("failure_history_cleared", service_name=service_name)
        pass


# Expected Lint Errors (Intentional):
# 1. structlog import unused (TODO: use in record_failure logging)
# 2. time import unused (TODO: use in record_failure timestamp and pattern calculations)
# 3. dataclass asdict unused (TODO: use if exporting records to dict format)
# 4. logger parameter missing in structlog.bind (TODO: configure in __init__)
#
# These will be resolved when @resilience-team implements the TODOs.
