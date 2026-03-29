"""P03 Circuit Breaker — Issue 6.2.5.

Circuit breaker state machine for P03 external dependency protection.
Implements CLOSED → OPEN → HALF_OPEN → CLOSED state machine.

References:
- Dossier Section 13.6: Circuit Breaker (External Dependencies)
- M6_EXECUTION.md Issue 6.2.5
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from k0.obs.metrics import MetricsExporter


class P03CircuitBreakerState(Enum):
    """Circuit breaker states.

    CLOSED: Normal operation, requests allowed.
    OPEN: Circuit tripped, requests blocked.
    HALF_OPEN: Testing recovery, limited requests allowed.
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class P03CircuitBreakerConfig:
    """Configuration for circuit breaker behavior.

    Attributes:
        failure_threshold: Consecutive failures before opening circuit.
        reset_timeout_seconds: Time before transitioning from OPEN to HALF_OPEN.
        success_threshold: Consecutive successes in HALF_OPEN before closing.
        half_open_max_requests: Maximum concurrent requests in HALF_OPEN.
    """

    failure_threshold: int = 5
    reset_timeout_seconds: float = 60.0
    success_threshold: int = 3
    half_open_max_requests: int = 1


class P03CircuitBreaker:
    """Circuit breaker for P03's external dependencies.

    Implements CLOSED → OPEN → HALF_OPEN → CLOSED state machine.

    State Transitions:
    - CLOSED → OPEN: After failure_threshold consecutive failures
    - OPEN → HALF_OPEN: After reset_timeout_seconds elapsed
    - HALF_OPEN → CLOSED: After success_threshold consecutive successes
    - HALF_OPEN → OPEN: On any failure

    References:
    - Dossier Section 13.6
    """

    def __init__(
        self,
        name: str,
        config: Optional[P03CircuitBreakerConfig] = None,
        metrics: Optional[MetricsExporter] = None,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            name: Circuit breaker name (e.g., "p08_embedding").
            config: Optional configuration. Uses defaults if not provided.
            metrics: Optional metrics exporter for observability.
        """
        self._name = name
        self._config = config or P03CircuitBreakerConfig()
        self._metrics = metrics

        # State tracking
        self._state = P03CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._state_changed_at: float = time.monotonic()
        self._half_open_requests = 0

    @property
    def name(self) -> str:
        """Get circuit breaker name."""
        return self._name

    @property
    def state(self) -> P03CircuitBreakerState:
        """Get current circuit breaker state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count

    @property
    def success_count(self) -> int:
        """Get current success count (in HALF_OPEN)."""
        return self._success_count

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == P03CircuitBreakerState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        return self._state == P03CircuitBreakerState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self._state == P03CircuitBreakerState.HALF_OPEN

    def should_allow_request(self) -> bool:
        """Check if request should be allowed through circuit.

        Returns:
            True if request should proceed, False if blocked.
        """
        if self._state == P03CircuitBreakerState.CLOSED:
            return True

        if self._state == P03CircuitBreakerState.OPEN:
            # Check if reset timeout elapsed
            if self._time_since_state_change() >= self._config.reset_timeout_seconds:
                self._transition_to(P03CircuitBreakerState.HALF_OPEN)
                self._half_open_requests = 1
                return True
            return False

        if self._state == P03CircuitBreakerState.HALF_OPEN:
            # Allow limited requests in half-open
            if self._half_open_requests < self._config.half_open_max_requests:
                self._half_open_requests += 1
                return True
            return False

        return False

    def record_success(self) -> None:
        """Record successful call.

        In CLOSED: Resets failure count.
        In HALF_OPEN: Increments success count, may transition to CLOSED.
        """
        if self._state == P03CircuitBreakerState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._config.success_threshold:
                self._transition_to(P03CircuitBreakerState.CLOSED)
        elif self._state == P03CircuitBreakerState.CLOSED:
            # Reset failure count on success
            self._failure_count = 0

        self._emit_metric("p03_circuit_breaker_success_total", 1.0)

    def record_failure(self) -> None:
        """Record failed call.

        In CLOSED: Increments failure count, may transition to OPEN.
        In HALF_OPEN: Immediately transitions back to OPEN.
        """
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == P03CircuitBreakerState.HALF_OPEN:
            # Failure in half-open → back to open
            self._transition_to(P03CircuitBreakerState.OPEN)
        elif self._state == P03CircuitBreakerState.CLOSED:
            if self._failure_count >= self._config.failure_threshold:
                self._transition_to(P03CircuitBreakerState.OPEN)

        self._emit_metric("p03_circuit_breaker_failure_total", 1.0)

    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        self._transition_to(P03CircuitBreakerState.CLOSED)
        self._failure_count = 0
        self._success_count = 0
        self._half_open_requests = 0

    def get_state_duration_seconds(self) -> float:
        """Get seconds since last state change.

        Returns:
            Time in seconds since state changed.
        """
        return self._time_since_state_change()

    def _transition_to(self, new_state: P03CircuitBreakerState) -> None:
        """Transition to new state with metrics.

        Args:
            new_state: Target state.
        """
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state
        self._state_changed_at = time.monotonic()

        if new_state == P03CircuitBreakerState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == P03CircuitBreakerState.HALF_OPEN:
            self._success_count = 0
            self._half_open_requests = 0

        self._emit_metric(
            "p03_circuit_breaker_state_transitions_total",
            1.0,
            from_state=old_state.value,
            to_state=new_state.value,
        )

    def _time_since_state_change(self) -> float:
        """Get seconds since last state change."""
        return time.monotonic() - self._state_changed_at

    def _emit_metric(self, name: str, value: float, **labels: str) -> None:
        """Emit metric if exporter available."""
        if self._metrics is not None:
            self._metrics.emit(name, value, circuit=self._name, **labels)


class P03CircuitBreakerRegistry:
    """Registry for P03 circuit breaker instances.

    Manages multiple circuit breakers for different dependencies.
    """

    def __init__(self, metrics: Optional[MetricsExporter] = None) -> None:
        """Initialize registry.

        Args:
            metrics: Optional metrics exporter shared by all circuits.
        """
        self._metrics = metrics
        self._circuits: Dict[str, P03CircuitBreaker] = {}

    def get(self, name: str) -> P03CircuitBreaker:
        """Get or create circuit breaker by name.

        Args:
            name: Circuit breaker name.

        Returns:
            Existing or new circuit breaker instance.
        """
        if name not in self._circuits:
            self._circuits[name] = P03CircuitBreaker(
                name=name,
                metrics=self._metrics,
            )
        return self._circuits[name]

    def register(
        self,
        name: str,
        config: Optional[P03CircuitBreakerConfig] = None,
    ) -> P03CircuitBreaker:
        """Register a circuit breaker with custom config.

        Args:
            name: Circuit breaker name.
            config: Optional custom configuration.

        Returns:
            The registered circuit breaker.
        """
        circuit = P03CircuitBreaker(
            name=name,
            config=config,
            metrics=self._metrics,
        )
        self._circuits[name] = circuit
        return circuit

    def get_all(self) -> Dict[str, P03CircuitBreaker]:
        """Get all registered circuit breakers.

        Returns:
            Dictionary of name → circuit breaker.
        """
        return dict(self._circuits)

    def reset_all(self) -> None:
        """Reset all circuit breakers to CLOSED state."""
        for circuit in self._circuits.values():
            circuit.reset()

    def get_open_circuits(self) -> list[str]:
        """Get names of all OPEN circuit breakers.

        Returns:
            List of circuit breaker names in OPEN state.
        """
        return [name for name, circuit in self._circuits.items() if circuit.is_open]


# =============================================================================
# PRE-CONFIGURED P03 CIRCUIT BREAKERS (from Dossier Section 13.6)
# =============================================================================

# P08 embedding pipeline circuit breaker config
P08_EMBEDDING_CONFIG = P03CircuitBreakerConfig(
    failure_threshold=5,
    reset_timeout_seconds=60.0,
    success_threshold=3,
    half_open_max_requests=1,
)

# Internal event bus circuit breaker config
BUS_DISPATCHER_CONFIG = P03CircuitBreakerConfig(
    failure_threshold=5,
    reset_timeout_seconds=60.0,
    success_threshold=3,
    half_open_max_requests=1,
)

def create_p03_circuit_breakers(
    metrics: Optional[MetricsExporter] = None,
) -> P03CircuitBreakerRegistry:
    """Create pre-configured P03 circuit breakers.

    Creates registry with the following circuits:
    - p08_embedding: P08 embedding pipeline coordination
    - bus_dispatcher: Internal event bus

    Args:
        metrics: Optional metrics exporter.

    Returns:
        Configured P03CircuitBreakerRegistry.
    """
    registry = P03CircuitBreakerRegistry(metrics=metrics)

    # P08 embedding pipeline
    registry.register("p08_embedding", P08_EMBEDDING_CONFIG)

    # Internal event bus
    registry.register("bus_dispatcher", BUS_DISPATCHER_CONFIG)

    return registry


# =============================================================================
# STATE TRANSITION TABLE
# =============================================================================
#
# | Current State | Event                           | Next State | Action          |
# |---------------|---------------------------------|------------|-----------------|
# | CLOSED        | failure_count >= threshold      | OPEN       | Block requests  |
# | CLOSED        | success                         | CLOSED     | Reset failures  |
# | OPEN          | timeout elapsed                 | HALF_OPEN  | Allow 1 request |
# | OPEN          | request                         | OPEN       | Reject          |
# | HALF_OPEN     | success_count >= threshold      | CLOSED     | Resume normal   |
# | HALF_OPEN     | failure                         | OPEN       | Block again     |
#
# =============================================================================
