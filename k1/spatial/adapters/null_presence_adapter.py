"""Null presence adapter for privacy-safe default behavior."""

from __future__ import annotations

from typing import Sequence

from k1.spatial.ports import IPresencePort
from k1.spatial.types import PresenceRef


class NullPresenceAdapter(IPresencePort):
    """Return no co-presence signals."""

    async def list_presence(
        self, session_id: str, subject_ref: str | None = None
    ) -> Sequence[PresenceRef]:
        return ()


__all__ = ["NullPresenceAdapter"]
