"""Grounding identity reference boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IGroundingIdentityPort(Protocol):
    """Expose stable subject and group references without raw identity data."""

    async def get_identity_ref(self, session_id: str) -> str | None:
        """Return the subject reference for a session, if known."""
        ...  # pragma: no cover

    async def get_group_refs(self, session_id: str) -> tuple[str, ...]:
        """Return group references visible to this session."""
        ...  # pragma: no cover

    async def get_role_refs(self, session_id: str) -> tuple[str, ...]:
        """Return role references visible to this session."""
        ...  # pragma: no cover


__all__ = ["IGroundingIdentityPort"]
