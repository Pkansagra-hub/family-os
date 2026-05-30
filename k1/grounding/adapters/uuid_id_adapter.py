"""UUID-backed grounding ID adapter."""

from __future__ import annotations

import uuid

from k1.grounding.ports import IGroundingIdPort


class UuidIdAdapter(IGroundingIdPort):
    """Generate opaque hexadecimal IDs for grounding payloads."""

    def new_envelope_id(self) -> str:
        return uuid.uuid4().hex

    def new_projection_id(self) -> str:
        return uuid.uuid4().hex

    def new_lease_id(self) -> str:
        return uuid.uuid4().hex


__all__ = ["UuidIdAdapter"]
