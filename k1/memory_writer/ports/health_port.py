"""
k1.memory_writer.ports.health_port -- IHealthPort protocol.

Readiness and liveness probes for Memory Writer v2.

Used by Fabric agent lifecycle to determine MW readiness.
Reports LLM circuit breaker state, pending batch count, and
last extraction latency.

Production adapter: HealthAdapter in adapters/health_adapter.py
Test adapter: In adapters/test_adapters.py

References:
  - Epic 1.17 (Circuit breaker)
  - k1/orchestrator module.contract.yaml health capability
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.memory_writer.types import HealthStatus


@runtime_checkable
class IHealthPort(Protocol):
    """
    Readiness and liveness probes for Fabric agent lifecycle.

    Reports:
      - Overall health (is_healthy)
      - LLM circuit breaker state
      - Pending batch count
      - Last extraction latency
    """

    async def is_ready(self) -> bool:
        """
        Check if Memory Writer is ready to process turns.

        Returns:
            True if MW pipeline is initialized and LLM circuit is not open.
        """
        ...  # pragma: no cover

    async def health_check(self) -> HealthStatus:
        """
        Detailed health check for observability and diagnostics.

        Returns:
            HealthStatus with is_healthy flag, circuit state,
            pending batch count, and last extraction latency.
        """
        ...  # pragma: no cover
