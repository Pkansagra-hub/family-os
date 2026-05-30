"""Default temporal policy adapter for tests and standalone mode."""

from __future__ import annotations

from k1.temporal.ports import ITemporalPolicyPort


class AllowAllTemporalPolicyAdapter(ITemporalPolicyPort):
    """Allow all routine-backed temporal projections."""

    async def allow_routine(self, routine_id: str, consumer: str) -> bool:
        return True


__all__ = ["AllowAllTemporalPolicyAdapter"]
