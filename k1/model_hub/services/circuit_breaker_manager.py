"""Per-provider circuit breaker with state machine [F48].

Manages CLOSED -> OPEN -> HALF_OPEN -> CLOSED state transitions per
provider, using sliding window failure counting and manifest-driven config.

Import graph (Layer 3 -- imports Layer 0 + Layer 1 + Layer 2)
--------------------------------------------------------------
k1.model_hub.services.circuit_breaker_manager
  -> k1.model_hub.types       (Layer 0: CircuitState)
  -> k1.model_hub.manifest    (Layer 0: CircuitBreakerConfig)
  -> stdlib only

NEVER import from any adapter or runtime module.

References
----------
- model_hub.mmd: CircuitBreakerManager service
- Invariant MH-05: Circuit breaker per provider
- Default: 3 failures in 60s -> OPEN for 30s
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from k1.model_hub.events import TOPIC_CIRCUIT_STATE
from k1.model_hub.manifest import CircuitBreakerConfig
from k1.model_hub.types import CircuitState

logger = logging.getLogger(__name__)

# ===========================================================================
# Per-provider circuit breaker state
# ===========================================================================


@dataclass
class _ProviderCircuit:
    """Mutable per-provider circuit breaker state."""

    state: CircuitState = CircuitState.CLOSED
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    failure_timestamps: List[float] = field(default_factory=list)
    opened_at: float = 0.0
    half_open_in_flight: bool = False


@dataclass(frozen=True)
class CircuitTransition:
    """Record of a circuit breaker state transition."""

    provider_id: str
    old_state: CircuitState
    new_state: CircuitState
    failure_count: int = 0
    timestamp: float = 0.0


# ===========================================================================
# CircuitBreakerManager
# ===========================================================================


class CircuitBreakerManager:
    """Per-provider circuit breaker with sliding window failure detection.

    State machine (MH-05):
      CLOSED:    All requests pass. Failures counted in sliding window.
                 failure_threshold breached in failure_window_s -> OPEN.
      OPEN:      All requests rejected immediately. Cooldown timer runs.
                 After cooldown_s elapsed -> HALF_OPEN.
      HALF_OPEN: Single probe request allowed. Success -> CLOSED.
                 Failure -> OPEN (restart cooldown).

    Config from manifest per provider (MH-05):
      failure_threshold: 3 (default)
      failure_window_s:  60 (default)
      cooldown_s:        30 (default)

    Implements ICircuitBreakerQuery protocol from capability_router.
    """

    def __init__(self, event_port: Any | None = None) -> None:
        self._circuits: Dict[str, _ProviderCircuit] = {}
        self._transitions: List[CircuitTransition] = []
        self._lock = threading.RLock()
        self._event_port = event_port

    # -- Registration ----------------------------------------------------------

    def register_provider(
        self,
        provider_id: str,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> None:
        """Register a provider with optional circuit breaker config.

        Args:
            provider_id: Provider identifier.
            config: Circuit breaker config from manifest. Uses defaults if None.
        """
        if provider_id not in self._circuits:
            self._circuits[provider_id] = _ProviderCircuit(
                config=config or CircuitBreakerConfig(),
            )

    def unregister_provider(self, provider_id: str) -> None:
        """Remove a provider's circuit breaker state."""
        self._circuits.pop(provider_id, None)

    # -- ICircuitBreakerQuery protocol -----------------------------------------

    def get_state(self, provider_id: str) -> CircuitState:
        """Get current circuit state for a provider.

        Implements ICircuitBreakerQuery.get_state().
        Auto-transitions OPEN -> HALF_OPEN when cooldown expires.
        Returns CLOSED for unknown providers.
        """
        circuit = self._circuits.get(provider_id)
        if circuit is None:
            return CircuitState.CLOSED

        with self._lock:
            # Check OPEN -> HALF_OPEN transition on cooldown expiry
            if circuit.state == CircuitState.OPEN:
                elapsed = time.monotonic() - circuit.opened_at
                if elapsed >= circuit.config.cooldown_s:
                    self._transition(circuit, provider_id, CircuitState.HALF_OPEN)

            return circuit.state

    # -- Acquire / Record ------------------------------------------------------

    def acquire(self, provider_id: str) -> CircuitState:
        """Acquire the circuit breaker for a request.

        Returns the current state. Caller should reject if OPEN.
        For HALF_OPEN, marks the probe in-flight.

        Returns:
            Current CircuitState after any auto-transitions.
        """
        with self._lock:
            state = self.get_state(provider_id)
            circuit = self._circuits.get(provider_id)

            if circuit and state == CircuitState.HALF_OPEN:
                if circuit.half_open_in_flight:
                    # Only one probe at a time; treat as OPEN
                    return CircuitState.OPEN
                circuit.half_open_in_flight = True

            return state

    def record_success(self, provider_id: str) -> None:
        """Record a successful request.

        HALF_OPEN + success -> CLOSED (reset failures).
        CLOSED: no-op (already healthy).
        """
        circuit = self._circuits.get(provider_id)
        if circuit is None:
            return

        with self._lock:
            if circuit.state == CircuitState.HALF_OPEN:
                circuit.failure_timestamps.clear()
                circuit.half_open_in_flight = False
                self._transition(circuit, provider_id, CircuitState.CLOSED)
            elif circuit.state == CircuitState.CLOSED:
                # Optionally clear old failures on success
                pass

    def record_failure(self, provider_id: str, error: Optional[str] = None) -> None:
        """Record a failed request.

        CLOSED: Add failure to sliding window. If threshold breached -> OPEN.
        HALF_OPEN: Probe failed -> OPEN (restart cooldown).
        """
        circuit = self._circuits.get(provider_id)
        if circuit is None:
            return

        now = time.monotonic()

        with self._lock:
            if circuit.state == CircuitState.HALF_OPEN:
                circuit.half_open_in_flight = False
                circuit.opened_at = now
                self._transition(circuit, provider_id, CircuitState.OPEN)

            elif circuit.state == CircuitState.CLOSED:
                circuit.failure_timestamps.append(now)

                # Prune failures outside the window
                window_start = now - circuit.config.failure_window_s
                circuit.failure_timestamps = [
                    t for t in circuit.failure_timestamps if t >= window_start
                ]

                # Check threshold
                if len(circuit.failure_timestamps) >= circuit.config.failure_threshold:
                    circuit.opened_at = now
                    self._transition(circuit, provider_id, CircuitState.OPEN)

    # -- Query -----------------------------------------------------------------

    @property
    def transitions(self) -> List[CircuitTransition]:
        """List of all state transitions (for testing/auditing)."""
        return list(self._transitions)

    def failure_count(self, provider_id: str) -> int:
        """Current failure count in the sliding window."""
        circuit = self._circuits.get(provider_id)
        if circuit is None:
            return 0
        now = time.monotonic()
        window_start = now - circuit.config.failure_window_s
        return sum(1 for t in circuit.failure_timestamps if t >= window_start)

    def is_registered(self, provider_id: str) -> bool:
        """Check if a provider has a circuit breaker."""
        return provider_id in self._circuits

    # -- Internal --------------------------------------------------------------

    def _transition(
        self,
        circuit: _ProviderCircuit,
        provider_id: str,
        new_state: CircuitState,
    ) -> None:
        """Record a state transition."""
        old_state = circuit.state
        circuit.state = new_state
        transition = CircuitTransition(
            provider_id=provider_id,
            old_state=old_state,
            new_state=new_state,
            failure_count=len(circuit.failure_timestamps),
            timestamp=time.monotonic(),
        )
        self._transitions.append(transition)
        self._publish_transition(transition)

    def _publish_transition(self, transition: CircuitTransition) -> None:
        """Publish transition events from sync CB methods without blocking callers."""
        if self._event_port is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        payload = {
            "provider_id": transition.provider_id,
            "old_state": transition.old_state.value,
            "new_state": transition.new_state.value,
            "failure_count": transition.failure_count,
        }
        task = loop.create_task(self._event_port.publish(TOPIC_CIRCUIT_STATE, payload))
        task.add_done_callback(self._log_publish_failure)

    @staticmethod
    def _log_publish_failure(task: asyncio.Task[Any]) -> None:
        try:
            task.result()
        except Exception:  # noqa: BLE001
            logger.debug("Circuit state event publish failed", exc_info=True)


__all__ = [
    "CircuitBreakerManager",
    "CircuitTransition",
]
