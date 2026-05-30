"""Timezone candidate port."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ITimezonePort(Protocol):
    """Return a candidate IANA timezone for a principal."""

    async def candidate_for_principal(self, principal_id: str) -> str | None:
        """Return an IANA timezone name or None when unavailable."""
        ...  # pragma: no cover


__all__ = ["ITimezonePort"]
