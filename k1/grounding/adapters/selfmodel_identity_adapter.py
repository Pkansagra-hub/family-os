"""Identity adapter backed by a per-session selfmodel handle."""

from __future__ import annotations

from typing import Any

from k1.grounding.ports import IGroundingIdentityPort


class SelfModelIdentityAdapter(IGroundingIdentityPort):
    """Expose prompt-safe identity references from SelfModelHandle metadata."""

    def __init__(self, selfmodel_handle: Any | None = None, *, actor_id: str | None = None) -> None:
        self._handle = selfmodel_handle
        self._actor_id = actor_id

    async def get_identity_ref(self, session_id: str) -> str | None:
        actor_id = self._actor_id or getattr(self._handle, "actor_id", None)
        return str(actor_id) if actor_id else None

    async def get_group_refs(self, session_id: str) -> tuple[str, ...]:
        space_id = getattr(getattr(self._handle, "bundle", None), "space_id", None)
        return (str(space_id),) if space_id else ()

    async def get_role_refs(self, session_id: str) -> tuple[str, ...]:
        try:
            frame = self._handle.current_frame() if self._handle is not None else None
            role = getattr(getattr(frame, "actor", None), "role", None)
            return (str(role),) if role else ()
        except Exception:
            return ()


class StaticIdentityAdapter(IGroundingIdentityPort):
    """Small testing adapter for explicit identity/group references."""

    def __init__(
        self,
        *,
        identity_ref: str | None = None,
        group_refs: tuple[str, ...] = (),
        role_refs: tuple[str, ...] = (),
    ) -> None:
        self._identity_ref = identity_ref
        self._group_refs = tuple(group_refs)
        self._role_refs = tuple(role_refs)

    async def get_identity_ref(self, session_id: str) -> str | None:
        return self._identity_ref

    async def get_group_refs(self, session_id: str) -> tuple[str, ...]:
        return self._group_refs

    async def get_role_refs(self, session_id: str) -> tuple[str, ...]:
        return self._role_refs


__all__ = ["SelfModelIdentityAdapter", "StaticIdentityAdapter"]
