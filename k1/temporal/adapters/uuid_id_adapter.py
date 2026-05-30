"""UUID-backed temporal ID adapter."""

from __future__ import annotations

import uuid

from k1.temporal.ports import ITemporalIdPort


class UuidIdAdapter(ITemporalIdPort):
    """Generate opaque hexadecimal IDs for temporal payloads."""

    def new_anchor_id(self) -> str:
        return uuid.uuid4().hex

    def new_window_id(self) -> str:
        return uuid.uuid4().hex

    def new_resolution_id(self) -> str:
        return uuid.uuid4().hex


__all__ = ["UuidIdAdapter"]
