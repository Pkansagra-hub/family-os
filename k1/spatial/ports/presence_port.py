"""Presence source boundary for co-presence signals."""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from k1.spatial.types import PresenceRef


@runtime_checkable
class IPresencePort(Protocol):
    """Read policy-filterable co-presence candidates."""

    async def list_presence(
        self, session_id: str, subject_ref: str | None = None
    ) -> Sequence[PresenceRef]:
        """Return presence candidates for a session or subject."""
        ...  # pragma: no cover


__all__ = ["IPresencePort"]
