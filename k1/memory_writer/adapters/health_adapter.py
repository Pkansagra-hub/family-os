"""HealthAdapter -- bridges MW's IHealthPort to CircuitBreaker + pipeline state.

This adapter does NOT wrap an external dependency -- it composes
MW-internal state into the IHealthPort protocol.

References:
  - E-MW-5.1: Production Adapters
  - k1/memory_writer/ports/health_port.py (IHealthPort)
  - k1/memory_writer/health.py (CircuitBreaker)
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from k1.memory_writer.types import HealthStatus


@runtime_checkable
class _ICircuitBreaker(Protocol):
    """Minimal local Protocol for CircuitBreaker dependency."""

    @property
    def is_open(self) -> bool: ...


class HealthAdapter:
    """Implements IHealthPort by composing CircuitBreaker + pipeline state.

    Constructor Args:
        circuit_breaker: CircuitBreaker instance.
        get_pending_count: Callable returning pending batch count.
        get_started: Callable returning whether service is started.
    """

    __slots__ = ("_circuit_breaker", "_get_pending_count", "_get_started")

    def __init__(
        self,
        circuit_breaker: _ICircuitBreaker,
        get_pending_count: Callable[[], int],
        get_started: Callable[[], bool],
    ) -> None:
        self._circuit_breaker = circuit_breaker
        self._get_pending_count = get_pending_count
        self._get_started = get_started

    async def is_ready(self) -> bool:
        """MW is ready if started and circuit breaker is not open."""
        return self._get_started() and not self._circuit_breaker.is_open

    async def health_check(self) -> HealthStatus:
        """Detailed health status for Fabric probes."""
        started = self._get_started()
        cb_open = self._circuit_breaker.is_open

        return HealthStatus(
            is_healthy=started and not cb_open,
            llm_circuit_open=cb_open,
            pending_batch_count=self._get_pending_count(),
            last_extraction_ms=0.0,
            detail="running" if started else "stopped",
        )
