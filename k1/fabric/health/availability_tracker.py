"""
k1.fabric.health.availability_tracker -- Availability Tracker (3.6.2).

Tracks ONLINE/DEGRADED/OFFLINE state per provider with full transition
history.  Integrates with CapabilityRegistry.update_availability() to
keep contract availability in sync with actual provider state.

State Transitions (recovery requires progressive path):
  OFFLINE  -> DEGRADED -> ONLINE   (recovery: must pass through DEGRADED)
  ONLINE   -> DEGRADED -> OFFLINE  (failure:  may skip DEGRADED for hard fail)
  ONLINE   -> OFFLINE              (hard failure:  allowed)
  DEGRADED -> ONLINE              (recovery confirmation)
  DEGRADED -> OFFLINE             (continued degradation)

Thread Safety:
  All mutations guarded by RLock.  Read-only methods are safe for
  concurrent access due to Python dict read atomicity.

Design Decisions:
  - Transition history is bounded (max_history per provider) to prevent
    unbounded memory growth.
  - AvailabilityTracker is the single source of truth for provider
    availability.  HealthChecker and CircuitBreaker both call
    update_state() when they detect changes.
  - Optional registry_updater callback allows decoupled sync with
    CapabilityRegistry.update_availability() (2.2.5).

References:
  - fabric_discussion.md Section 19 (Error Handling, Availability)
  - Epic 3.6.2 in fabric-implementation-plan.md

Exports:
  AvailabilityTracker  -- Per-provider state + transition history
  StateTransition      -- Timestamped state transition record
  AvailabilityTrackerError -- Base exception
  ProviderNotTrackedError  -- provider_id not tracked
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from k1.fabric.types import Availability

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event port protocol (duck-typed)
# ---------------------------------------------------------------------------


class EventPort(Protocol):
    """Minimal event bus interface."""

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# Registry updater callback protocol
# ---------------------------------------------------------------------------


class IRegistryUpdater(Protocol):
    """
    Callback to propagate availability changes to CapabilityRegistry.

    In production, wired to registry.update_availability(name, availability).
    """

    def __call__(self, provider_id: str, availability: str) -> None: ...


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVENT_AVAILABILITY_CHANGED = "k1.fabric.provider.availability.changed.v1"

DEFAULT_MAX_HISTORY = 100

# Recovery requires progressive path: OFFLINE -> DEGRADED -> ONLINE
# Direct jump from OFFLINE -> ONLINE is blocked.
VALID_TRANSITIONS = {
    Availability.ONLINE.value: {
        Availability.DEGRADED.value,
        Availability.OFFLINE.value,
    },
    Availability.DEGRADED.value: {
        Availability.ONLINE.value,
        Availability.OFFLINE.value,
    },
    Availability.OFFLINE.value: {
        Availability.DEGRADED.value,
        # OFFLINE -> ONLINE blocked (must go through DEGRADED)
    },
}


# ---------------------------------------------------------------------------
# State transition record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StateTransition:
    """
    Timestamped record of a provider state transition.

    Attributes:
        provider_id: Provider that transitioned.
        old_state: Previous availability state.
        new_state: New availability state.
        timestamp_ms: Monotonic time of transition (ms).
        reason: Human-readable reason for the transition.
    """

    provider_id: str = ""
    old_state: str = Availability.ONLINE.value
    new_state: str = Availability.ONLINE.value
    timestamp_ms: int = 0
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "provider_id": self.provider_id,
            "old_state": self.old_state,
            "new_state": self.new_state,
            "timestamp_ms": self.timestamp_ms,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AvailabilityTrackerError(Exception):
    """Base exception for availability tracker operations."""


class ProviderNotTrackedError(AvailabilityTrackerError):
    """Raised when a provider_id is not being tracked."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        super().__init__(f"Provider not tracked: {provider_id}")


class InvalidTransitionError(AvailabilityTrackerError):
    """Raised when a state transition is not valid."""

    def __init__(
        self,
        provider_id: str,
        old_state: str,
        new_state: str,
    ) -> None:
        self.provider_id = provider_id
        self.old_state = old_state
        self.new_state = new_state
        super().__init__(f"Invalid transition for {provider_id}: " f"{old_state} -> {new_state}")


# ---------------------------------------------------------------------------
# Internal per-provider state
# ---------------------------------------------------------------------------


@dataclass
class _ProviderState:
    """Mutable internal state for a tracked provider."""

    availability: str = Availability.ONLINE.value
    transitions: List[StateTransition] = field(default_factory=list)
    last_transition_ms: int = 0


# ---------------------------------------------------------------------------
# 3.6.2 -- AvailabilityTracker
# ---------------------------------------------------------------------------


class AvailabilityTracker:
    """
    Tracks ONLINE/DEGRADED/OFFLINE state per provider with transition history.

    Provides:
      - ``update_state()`` -- Transition a provider to a new state.
      - ``get_state()`` -- Read current availability.
      - ``get_transitions()`` -- Read transition history.
      - ``register()`` / ``unregister()`` -- Manage tracked providers.
      - ``summary()`` -- Aggregate counts by state.

    AvailabilityTracker enforces valid state transitions:
      - OFFLINE -> ONLINE is **blocked** (must recover through DEGRADED).
      - Same-state no-ops are silently ignored.

    Constructor Args:
        event_port: Optional event bus for availability change events.
        registry_updater: Optional callback to sync CapabilityRegistry.
        max_history: Maximum transition records kept per provider.
        enforce_progressive_recovery: If True (default), OFFLINE->ONLINE
            is blocked.  If False, any transition is allowed.

    Thread Safety:
        All mutations acquire self._lock (RLock).
    """

    __slots__ = (
        "_lock",
        "_event_port",
        "_registry_updater",
        "_max_history",
        "_enforce_progressive_recovery",
        "_providers",
    )

    def __init__(
        self,
        *,
        event_port: Optional[EventPort] = None,
        registry_updater: Optional[IRegistryUpdater] = None,
        max_history: int = DEFAULT_MAX_HISTORY,
        enforce_progressive_recovery: bool = True,
    ) -> None:
        self._lock = threading.RLock()
        self._event_port = event_port
        self._registry_updater = registry_updater
        self._max_history = max(1, max_history)
        self._enforce_progressive_recovery = enforce_progressive_recovery
        self._providers: Dict[str, _ProviderState] = {}

    # ==================================================================
    # Provider registration
    # ==================================================================

    def register(
        self,
        provider_id: str,
        initial_state: str = Availability.ONLINE.value,
    ) -> None:
        """
        Start tracking a provider.

        Args:
            provider_id: Provider identifier.
            initial_state: Starting availability (default ONLINE).

        Raises:
            ValueError: Empty provider_id or invalid state.
        """
        if not provider_id:
            raise ValueError("provider_id must not be empty")
        self._validate_state(initial_state)

        with self._lock:
            if provider_id in self._providers:
                return  # Already tracked -- idempotent
            self._providers[provider_id] = _ProviderState(
                availability=initial_state,
                last_transition_ms=self._now_ms(),
            )

    def unregister(self, provider_id: str) -> bool:
        """
        Stop tracking a provider.

        Returns:
            True if found and removed, False if not tracked.
        """
        with self._lock:
            return self._providers.pop(provider_id, None) is not None

    # ==================================================================
    # State mutation
    # ==================================================================

    def update_state(
        self,
        provider_id: str,
        new_state: str,
        reason: str = "",
    ) -> Optional[StateTransition]:
        """
        Transition a provider to a new availability state.

        Args:
            provider_id: Provider identifier.
            new_state: Target availability (ONLINE, DEGRADED, OFFLINE).
            reason: Human-readable reason for the change.

        Returns:
            StateTransition if the state changed, None if no-op.

        Raises:
            ProviderNotTrackedError: provider_id not registered.
            InvalidTransitionError: Transition is not valid.
            ValueError: Invalid state value.
        """
        self._validate_state(new_state)

        with self._lock:
            ps = self._providers.get(provider_id)
            if ps is None:
                raise ProviderNotTrackedError(provider_id)

            old_state = ps.availability

            # Same state -- no-op
            if old_state == new_state:
                return None

            # Validate transition
            if self._enforce_progressive_recovery:
                allowed = VALID_TRANSITIONS.get(old_state, set())
                if new_state not in allowed:
                    raise InvalidTransitionError(provider_id, old_state, new_state)

            now = self._now_ms()
            transition = StateTransition(
                provider_id=provider_id,
                old_state=old_state,
                new_state=new_state,
                timestamp_ms=now,
                reason=reason,
            )

            ps.availability = new_state
            ps.transitions.append(transition)
            ps.last_transition_ms = now

            # Trim history
            if len(ps.transitions) > self._max_history:
                ps.transitions = ps.transitions[-self._max_history :]

        # Propagate to CapabilityRegistry (outside lock)
        self._sync_registry(provider_id, new_state)

        # Emit event
        self._emit(
            EVENT_AVAILABILITY_CHANGED,
            {
                "provider_id": provider_id,
                "old_state": old_state,
                "new_state": new_state,
                "reason": reason,
            },
        )

        logger.info(
            "Availability %s: %s -> %s (%s)",
            provider_id,
            old_state,
            new_state,
            reason or "no reason",
        )
        return transition

    # ==================================================================
    # State queries
    # ==================================================================

    def get_state(self, provider_id: str) -> str:
        """
        Return the current availability for a provider.

        Args:
            provider_id: Provider identifier.

        Returns:
            Availability string (ONLINE, DEGRADED, OFFLINE).

        Raises:
            ProviderNotTrackedError: provider_id not registered.
        """
        ps = self._providers.get(provider_id)
        if ps is None:
            raise ProviderNotTrackedError(provider_id)
        return ps.availability

    def get_transitions(
        self,
        provider_id: str,
        limit: Optional[int] = None,
    ) -> List[StateTransition]:
        """
        Return the transition history for a provider.

        Args:
            provider_id: Provider identifier.
            limit: Optional max number of recent transitions.

        Returns:
            List of StateTransition (oldest first).

        Raises:
            ProviderNotTrackedError: provider_id not registered.
        """
        ps = self._providers.get(provider_id)
        if ps is None:
            raise ProviderNotTrackedError(provider_id)
        if limit is not None and limit > 0:
            return list(ps.transitions[-limit:])
        return list(ps.transitions)

    def is_tracked(self, provider_id: str) -> bool:
        """Check if a provider is being tracked."""
        return provider_id in self._providers

    @property
    def tracked_count(self) -> int:
        """Number of tracked providers."""
        return len(self._providers)

    def list_by_state(self, state: str) -> List[str]:
        """
        Return provider_ids currently in the given state.

        Args:
            state: Availability value to filter by.

        Returns:
            List of provider_ids.
        """
        return [pid for pid, ps in self._providers.items() if ps.availability == state]

    def summary(self) -> Dict[str, int]:
        """
        Return aggregate counts by state.

        Returns:
            Dict mapping state string to count of providers in that state.
        """
        counts: Dict[str, int] = {
            Availability.ONLINE.value: 0,
            Availability.DEGRADED.value: 0,
            Availability.OFFLINE.value: 0,
        }
        for ps in self._providers.values():
            counts[ps.availability] = counts.get(ps.availability, 0) + 1
        return counts

    # ==================================================================
    # IStateChangeListener interface (for CircuitBreaker callback)
    # ==================================================================

    def on_state_change(
        self,
        provider_id: str,
        old_state: Any,
        new_state: Any,
    ) -> None:
        """
        Handle circuit breaker state change notification.

        Maps CB states to availability:
          CLOSED    -> ONLINE
          HALF_OPEN -> DEGRADED
          OPEN      -> OFFLINE

        This method is designed to be passed as the
        ``on_state_change`` callback to CircuitBreaker.

        Auto-registers providers that aren't yet tracked.
        """
        # Import locally to avoid circular dependency
        from k1.fabric.circuit_breaker.breaker import CircuitBreakerState

        _CB_TO_AVAILABILITY = {
            CircuitBreakerState.CLOSED: Availability.ONLINE.value,
            CircuitBreakerState.HALF_OPEN: Availability.DEGRADED.value,
            CircuitBreakerState.OPEN: Availability.OFFLINE.value,
        }

        # Convert string or enum to CircuitBreakerState
        if isinstance(new_state, str):
            try:
                new_state = CircuitBreakerState(new_state)
            except ValueError:
                return
        if isinstance(old_state, str):
            try:
                old_state = CircuitBreakerState(old_state)
            except ValueError:
                pass

        new_avail = _CB_TO_AVAILABILITY.get(new_state)
        if new_avail is None:
            return

        # Auto-register if not tracked
        if not self.is_tracked(provider_id):
            old_avail = _CB_TO_AVAILABILITY.get(old_state, Availability.ONLINE.value)  # type: ignore
            self.register(provider_id, initial_state=old_avail)

        try:
            self.update_state(
                provider_id,
                new_avail,
                reason=f"circuit_breaker:{old_state.value if hasattr(old_state, 'value') else old_state}->{new_state.value}",
            )
        except (InvalidTransitionError, ProviderNotTrackedError):
            # If progressive recovery blocks the jump, try the
            # intermediate step: e.g. OFFLINE -> DEGRADED first.
            if new_avail == Availability.ONLINE.value:
                try:
                    self.update_state(
                        provider_id,
                        Availability.DEGRADED.value,
                        reason="circuit_breaker:recovery_intermediate",
                    )
                    self.update_state(
                        provider_id,
                        Availability.ONLINE.value,
                        reason="circuit_breaker:recovery_confirmed",
                    )
                except (InvalidTransitionError, ProviderNotTrackedError):
                    pass

    # ==================================================================
    # Internal helpers
    # ==================================================================

    @staticmethod
    def _validate_state(state: str) -> None:
        """Validate that state is a valid Availability value."""
        valid = {a.value for a in Availability}
        if state not in valid:
            raise ValueError(f"Invalid availability '{state}'. Must be one of: {sorted(valid)}")

    def _sync_registry(self, provider_id: str, availability: str) -> None:
        """Propagate availability to CapabilityRegistry via callback."""
        if self._registry_updater is not None:
            try:
                self._registry_updater(provider_id, availability)
            except Exception:
                logger.warning(
                    "Failed to sync registry for %s -> %s",
                    provider_id,
                    availability,
                    exc_info=True,
                )

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emit an event via event_port, if available."""
        if self._event_port is not None:
            try:
                self._event_port.emit(event_type, payload)
            except Exception:
                logger.warning(
                    "Failed to emit %s for %s",
                    event_type,
                    payload.get("provider_id", "unknown"),
                    exc_info=True,
                )

    @staticmethod
    def _now_ms() -> int:
        """Current monotonic time in milliseconds."""
        return int(time.monotonic() * 1000)

    def __repr__(self) -> str:
        counts = self.summary()
        return (
            f"AvailabilityTracker("
            f"tracked={self.tracked_count}, "
            f"online={counts.get('ONLINE', 0)}, "
            f"degraded={counts.get('DEGRADED', 0)}, "
            f"offline={counts.get('OFFLINE', 0)})"
        )
