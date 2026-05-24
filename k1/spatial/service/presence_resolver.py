"""Resolve co-presence candidates through the presence port."""

from __future__ import annotations

from k1.spatial.ports import IPresencePort
from k1.spatial.types import PresenceRef


async def resolve_presence(
    port: IPresencePort | None,
    session_id: str,
    subject_ref: str | None = None,
) -> tuple[PresenceRef, ...]:
    """Return presence candidates, filtering invalid/zero-confidence entries."""
    if port is None:
        return ()
    values = await port.list_presence(session_id, subject_ref=subject_ref)
    return tuple(item for item in values if item.confidence > 0)


__all__ = ["resolve_presence"]
