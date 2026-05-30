"""Temporal projection policy boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ITemporalPolicyPort(Protocol):
    """Authorize routine-sensitive temporal context for a consumer."""

    async def allow_routine(self, routine_id: str, consumer: str) -> bool:
        """Return whether the consumer may see the routine-backed window."""
        ...  # pragma: no cover


__all__ = ["ITemporalPolicyPort"]
