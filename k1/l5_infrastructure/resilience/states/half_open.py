"""
Circuit Breaker HALF_OPEN State Handler.

This module implements the HALF_OPEN state handler for the circuit breaker pattern.
HALF_OPEN is the recovery testing state where a single probe request is allowed to
test if the protected service has recovered. Success transitions to CLOSED (recovered),
failure transitions back to OPEN (still broken).

State Behavior (ADR-0009a):
    - Allow single probe request to test service recovery
    - Only 1 concurrent probe allowed (first caller wins)
    - Success → CLOSED: Service recovered, resume normal operation
    - Failure → OPEN: Service still broken, retry timeout

Performance:
    - Probe check: <0.1ms (flag check + atomic set)
    - Success handling: <0.5ms (counter + transition)
    - Failure handling: <1ms (reopen circuit)
    - Memory: ~100B (success_count + probe_in_progress flag)

Integration Points:
    - Called by CircuitBreakerFSM in circuit_fsm.py
    - Exports metrics via CircuitBreakerManager
    - Logs state transitions via structlog
    - Controls probe concurrency to avoid thundering herd

Related ADRs:
    - ADR-0009: Circuit Breaker Pattern (recovery testing)
    - ADR-0009a: FSM Implementation (state handlers, transitions)
    - ADR-0009b: Per-Service Configuration (success_threshold)
    - ADR-0009c: Metrics & Observability (probe success/failure)

Author: @resilience-team
Created: 2025-10-27
Status: STUB (Implementation Required)
"""

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from k1.l5_infrastructure.resilience.circuit_fsm import CircuitBreakerFSM

logger = structlog.get_logger(__name__)


class HalfOpenStateHandler:
    """
    HALF_OPEN State Handler for Circuit Breaker.

    The HALF_OPEN state represents recovery testing mode where a single probe
    request is allowed to test if the protected service has recovered. This
    prevents thundering herd problems where all waiting requests hit a degraded
    service simultaneously.

    Responsibilities:
        1. Allow single probe request (first caller wins)
        2. Reject concurrent probes (fail-fast)
        3. Track success_count toward success_threshold
        4. Transition to CLOSED on success (recovered)
        5. Transition back to OPEN on failure (still broken)

    State Transitions:
        - HALF_OPEN → CLOSED: success_count >= success_threshold (recovered!)
        - HALF_OPEN → OPEN: Any failure (service still broken)
        - HALF_OPEN → HALF_OPEN: Concurrent probe rejected (first caller wins)

    Performance Targets:
        - can_attempt_request(): <0.1ms (flag check + atomic set)
        - handle_probe_success(): <0.5ms (counter + transition)
        - handle_probe_failure(): <1ms (transition to OPEN)
        - Memory: ~100B (success_count + probe_in_progress flag)

    Thread Safety:
        - All methods called within CircuitBreakerFSM's asyncio.Lock
        - probe_in_progress flag prevents concurrent probes
        - No additional locking required (FSM lock sufficient)

    Thundering Herd Prevention:
        - Only 1 probe allowed at a time (probe_in_progress flag)
        - Other requests fail-fast while probe in progress
        - Prevents 100s of requests hitting degraded service

    Example Usage:
        ```python
        from k1.l5_infrastructure.resilience.circuit_fsm import CircuitBreakerFSM
        from k1.l5_infrastructure.resilience.states.half_open import HalfOpenStateHandler

        # Create FSM, open circuit, wait for timeout
        config = CircuitBreakerConfig(
            failure_threshold=5,
            timeout_duration_ms=30000,
            success_threshold=2  # Need 2 successes to close
        )
        fsm = CircuitBreakerFSM(service_name="tool_runner", config=config)

        # Open circuit
        for i in range(5):
            await fsm.record_failure(failure_type="timeout")
        assert fsm.get_state() == CircuitBreakerState.OPEN

        # Wait for timeout → HALF_OPEN
        await asyncio.sleep(30)
        can_attempt = await fsm.can_attempt_request()
        assert fsm.get_state() == CircuitBreakerState.HALF_OPEN

        # First probe succeeds
        await fsm.record_success()
        assert fsm.success_count == 1

        # Second probe succeeds → CLOSED
        await fsm.record_success()
        assert fsm.get_state() == CircuitBreakerState.CLOSED
        ```

    ADR References:
        - ADR-0009a Section "State Definitions - HALF_OPEN"
        - ADR-0009a Section "State Transition Rules"
        - ADR-0009a Section "Concurrency & Thread Safety"

    WARD Test Example:
        ```python
        from ward import test, fixture
        import asyncio
        from k1.l5_infrastructure.resilience.circuit_fsm import (
            CircuitBreakerFSM,
            CircuitBreakerState,
            CircuitBreakerConfig
        )

        @fixture
        async def fsm():
            config = CircuitBreakerConfig(
                failure_threshold=3,
                timeout_duration_ms=1000,
                success_threshold=2
            )
            return CircuitBreakerFSM(service_name="test_service", config=config)

        @test("HALF_OPEN: success increments counter")
        async def _(fsm=fsm):
            # Open → HALF_OPEN
            for i in range(3):
                await fsm.record_failure(failure_type="timeout")
            await asyncio.sleep(1.1)
            await fsm.can_attempt_request()

            # Success increments
            await fsm.record_success()
            assert fsm.success_count == 1
            assert fsm.get_state() == CircuitBreakerState.HALF_OPEN

        @test("HALF_OPEN: transitions to CLOSED after success_threshold")
        async def _(fsm=fsm):
            # Open → HALF_OPEN
            for i in range(3):
                await fsm.record_failure(failure_type="timeout")
            await asyncio.sleep(1.1)
            await fsm.can_attempt_request()

            # 2 successes → CLOSED
            await fsm.record_success()
            await fsm.record_success()
            assert fsm.get_state() == CircuitBreakerState.CLOSED

        @test("HALF_OPEN: failure reopens circuit")
        async def _(fsm=fsm):
            # Open → HALF_OPEN
            for i in range(3):
                await fsm.record_failure(failure_type="timeout")
            await asyncio.sleep(1.1)
            await fsm.can_attempt_request()

            # One success, then failure
            await fsm.record_success()
            await fsm.record_failure(failure_type="timeout")

            # Back to OPEN
            assert fsm.get_state() == CircuitBreakerState.OPEN

        @test("HALF_OPEN: only one probe allowed at a time")
        async def _(fsm=fsm):
            # Open → HALF_OPEN
            for i in range(3):
                await fsm.record_failure(failure_type="timeout")
            await asyncio.sleep(1.1)

            # First request allowed
            can_attempt_1 = await fsm.can_attempt_request()
            assert can_attempt_1 == True

            # Second request rejected (probe in progress)
            can_attempt_2 = await fsm.can_attempt_request()
            assert can_attempt_2 == False
        ```
    """

    def __init__(self, service_name: str):
        """
        Initialize HALF_OPEN state handler.

        Args:
            service_name: Name of the protected service (for logging)

        Performance:
            - Initialization: <0.1ms (no I/O, simple assignment)
        """
        # TODO(@resilience-team): Initialize state handler
        # 1. Store service_name for logging
        # 2. Create logger with service context
        self.service_name = service_name
        self.logger = logger.bind(service=service_name, state="HALF_OPEN")

    async def can_attempt_request(self, fsm: "CircuitBreakerFSM") -> bool:
        """
        Check if probe request should be allowed in HALF_OPEN state.

        In HALF_OPEN state, only 1 concurrent probe is allowed. The first
        caller wins and gets to attempt the request. Other callers fail-fast
        to prevent thundering herd.

        Execution Flow:
            1. Check fsm.probe_in_progress flag
               - If False: Set flag True, return True (allow probe)
               - If True: Return False (probe already in progress)

        Args:
            fsm: CircuitBreakerFSM instance

        Returns:
            bool: True if probe allowed (first caller),
                  False if probe already in progress (fail-fast)

        Performance:
            - Target: <0.1ms (flag check + atomic set)
            - No network/disk I/O
            - Called within FSM's asyncio.Lock (thread-safe)

        Side Effects:
            - Sets fsm.probe_in_progress = True (first caller only)

        Thundering Herd Prevention:
            - 100 requests waiting in HALF_OPEN
            - Only 1st request allowed through
            - 99 requests fail-fast immediately
            - Service not overwhelmed during recovery

        Example:
            ```python
            # Circuit in HALF_OPEN, probe_in_progress = False
            assert fsm.get_state() == CircuitBreakerState.HALF_OPEN

            # First caller gets probe
            can_attempt_1 = await fsm.can_attempt_request()
            assert can_attempt_1 == True
            assert fsm.probe_in_progress == True

            # Second caller rejected
            can_attempt_2 = await fsm.can_attempt_request()
            assert can_attempt_2 == False

            # After probe completes, flag reset
            await fsm.record_success()
            assert fsm.probe_in_progress == False
            ```

        ADR References:
            - ADR-0009a: "HALF_OPEN allows single probe"
            - ADR-0009a: "Prevent concurrent probes (first caller wins)"
        """
        # TODO(@resilience-team): Implement probe check
        # 1. Check probe_in_progress flag:
        #    if not fsm.probe_in_progress:
        #        fsm.probe_in_progress = True
        #        self.logger.info("probe_allowed", service=self.service_name)
        #        return True
        #    else:
        #        self.logger.debug("probe_in_progress", service=self.service_name)
        #        return False
        return False

    async def handle_probe_success(self, fsm: "CircuitBreakerFSM") -> None:
        """
        Handle successful probe request in HALF_OPEN state.

        A successful probe indicates the service is recovering. Track success
        count and transition to CLOSED when success_threshold is reached.

        Execution Flow:
            1. Increment fsm.success_count
            2. Reset fsm.probe_in_progress = False
            3. Check if success_count >= success_threshold
               - If yes: Transition to CLOSED (service recovered!)
               - If no: Remain HALF_OPEN, allow next probe

        Args:
            fsm: CircuitBreakerFSM instance

        Performance:
            - Target: <0.5ms (counter + possible transition)
            - No network/disk I/O
            - Called within FSM's asyncio.Lock (thread-safe)

        Side Effects:
            - Updates fsm.success_count (incremented)
            - Resets fsm.probe_in_progress = False
            - May trigger fsm._transition_to_closed() (state change)
            - Emits info log

        Success Threshold Example:
            - success_threshold = 2 (need 2 successes to close)
            - Probe 1 succeeds: success_count = 1 (remain HALF_OPEN)
            - Probe 2 succeeds: success_count = 2 (transition CLOSED)

        Example:
            ```python
            # Circuit in HALF_OPEN, success_threshold = 2
            assert fsm.get_state() == CircuitBreakerState.HALF_OPEN

            # First probe succeeds
            await fsm.record_success()
            assert fsm.success_count == 1
            assert fsm.get_state() == CircuitBreakerState.HALF_OPEN

            # Second probe succeeds → CLOSED
            await fsm.record_success()
            assert fsm.success_count == 2
            assert fsm.get_state() == CircuitBreakerState.CLOSED
            ```

        ADR References:
            - ADR-0009a: "Success in HALF_OPEN increments success_count"
            - ADR-0009a: "Transition HALF_OPEN → CLOSED after threshold"
        """
        # TODO(@resilience-team): Implement probe success handling
        # 1. Increment fsm.success_count += 1
        # 2. Reset fsm.probe_in_progress = False (allow next probe)
        # 3. Log success:
        #    self.logger.info(
        #        "probe_success",
        #        success_count=fsm.success_count,
        #        threshold=fsm.config.success_threshold
        #    )
        # 4. Check threshold:
        #    if fsm.success_count >= fsm.config.success_threshold:
        #        await fsm._transition_to_closed()
        pass

    async def handle_probe_failure(
        self, fsm: "CircuitBreakerFSM", failure_type: str, latency_ms: float
    ) -> None:
        """
        Handle failed probe request in HALF_OPEN state.

        A failed probe indicates the service is still broken. Immediately
        reopen the circuit (transition back to OPEN) and restart timeout.

        Execution Flow:
            1. Reset fsm.probe_in_progress = False
            2. Reset fsm.success_count = 0
            3. Transition to OPEN via fsm._transition_to_open()
            4. Log warning

        Args:
            fsm: CircuitBreakerFSM instance
            failure_type: Type of failure (timeout, exception, slow_call)
            latency_ms: Request latency in milliseconds

        Performance:
            - Target: <1ms (transition to OPEN)
            - No network/disk I/O
            - Called within FSM's asyncio.Lock (thread-safe)

        Side Effects:
            - Resets fsm.probe_in_progress = False
            - Resets fsm.success_count = 0
            - Triggers fsm._transition_to_open() (state change)
            - Updates fsm.opened_at (new timeout starts)
            - Emits warning log

        Fast Failure Response:
            - Any failure in HALF_OPEN reopens circuit immediately
            - No gradual degradation (fail-fast principle)
            - Prevents cascading failures during recovery testing

        Example:
            ```python
            # Circuit in HALF_OPEN, had 1 success
            assert fsm.get_state() == CircuitBreakerState.HALF_OPEN
            assert fsm.success_count == 1

            # Probe fails → back to OPEN
            await fsm.record_failure(failure_type="timeout")

            assert fsm.get_state() == CircuitBreakerState.OPEN
            assert fsm.success_count == 0  # Reset
            assert fsm.opened_at is not None  # New timeout started
            ```

        ADR References:
            - ADR-0009a: "Any failure in HALF_OPEN reopens circuit"
            - ADR-0009a: "Transition HALF_OPEN → OPEN immediately"
        """
        # TODO(@resilience-team): Implement probe failure handling
        # 1. Reset fsm.probe_in_progress = False
        # 2. Reset fsm.success_count = 0
        # 3. Log failure:
        #    self.logger.warning(
        #        "probe_failure",
        #        failure_type=failure_type,
        #        latency_ms=latency_ms,
        #        reopening_circuit=True
        #    )
        # 4. Transition to OPEN:
        #    await fsm._transition_to_open()
        pass

    def allow_probe(self, fsm: "CircuitBreakerFSM") -> bool:
        """
        Check if probe is allowed (no probe in progress).

        Helper method to check probe_in_progress flag without side effects.
        Used for metrics and observability.

        Args:
            fsm: CircuitBreakerFSM instance

        Returns:
            bool: True if no probe in progress, False otherwise

        Performance:
            - Target: <0.01ms (flag read only)
            - No state changes (read-only)

        Example:
            ```python
            # Check probe status
            if handler.allow_probe(fsm):
                print("Probe allowed")
            else:
                print("Probe in progress, wait")
            ```

        ADR Reference:
            - ADR-0009a: "Probe concurrency control"
        """
        # TODO(@resilience-team): Implement probe check
        # Return: not fsm.probe_in_progress
        return True

    def get_state_name(self) -> str:
        """
        Get human-readable state name.

        Returns:
            "HALF_OPEN"

        Performance:
            - <0.001ms (constant return)
        """
        return "HALF_OPEN"


# Expected Lint Errors (Intentional):
# 1. structlog import unused (TODO: use in can_attempt_request/handle_* logging)
# 2. TYPE_CHECKING unused (TODO: use when implementing methods)
# 3. logger parameter missing in structlog.bind (TODO: configure in __init__)
#
# These will be resolved when @resilience-team implements the TODOs.
