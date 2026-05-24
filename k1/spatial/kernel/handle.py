"""Per-session Spatial handle exposed to kernel consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from k1.spatial.adapters import SelfModelSpatialPolicyAdapter, SpatialStateAdapter
from k1.spatial.kernel.bootstrap import SpatialServiceBundle
from k1.spatial.kernel.session_binding import SpatialSessionBinding
from k1.spatial.types import (
    PlaceRef,
    SpatialContext,
    SpatialProjection,
    SpatialTurnSnapshot,
)


@dataclass
class SpatialHandle:
    """Session-scoped facade that structurally satisfies ISpatialPort."""

    bundle: SpatialServiceBundle
    binding: SpatialSessionBinding
    state_adapter: Any
    service: Any
    installed: bool = False

    @property
    def session_id(self) -> str:
        return self.binding.session_id

    @property
    def principal_id(self) -> str | None:
        return self.binding.principal_id

    @property
    def actor_id(self) -> str | None:
        return self.binding.actor_id

    @property
    def device_id(self) -> str | None:
        return self.binding.device_id

    @property
    def installation_id(self) -> str | None:
        return self.binding.installation_id

    def install_into_session(self) -> None:
        """Mark the handle installed; safe to call repeatedly."""
        self.installed = True

    def uninstall_from_session(self) -> None:
        """Mark the handle uninstalled; safe to call repeatedly."""
        self.installed = False

    async def refresh_turn(
        self,
        session_id: str | None = None,
        *,
        turn_id: str | None = None,
        trace_id: str | None = None,
        consumer: str = "front",
        device_id: str | None = None,
        installation_id: str | None = None,
    ) -> SpatialTurnSnapshot:
        effective_device = device_id or self.device_id or "device:unknown"
        effective_installation = installation_id or self.installation_id or effective_device
        return await self.service.refresh_turn(
            self._session(session_id),
            device_id=effective_device,
            installation_id=effective_installation,
            turn_id=turn_id,
            trace_id=trace_id,
            consumer=consumer,
        )

    async def get_context(self, session_id: str | None = None) -> SpatialContext:
        return await self.service.get_context(self._session(session_id))

    async def resolve_place(
        self,
        session_id: str | None,
        text: str,
        *,
        subject_ref: str | None = None,
    ) -> PlaceRef | None:
        return await self.service.resolve_place(
            self._session(session_id), text, subject_ref=subject_ref
        )

    async def build_projection(
        self,
        session_id: str | None = None,
        consumer: str = "front",
        *,
        requested_precision: str | None = None,
        device_id: str | None = None,
        installation_id: str | None = None,
    ) -> SpatialProjection:
        effective_session = self._session(session_id)
        try:
            return await self.service.build_projection(
                effective_session,
                consumer,
                requested_precision=requested_precision,
            )
        except KeyError:
            snapshot = await self.refresh_turn(
                effective_session,
                consumer=consumer,
                device_id=device_id,
                installation_id=installation_id,
            )
            if requested_precision is None:
                return snapshot.projection
            return await self.service.build_projection(
                effective_session,
                consumer,
                requested_precision=requested_precision,
            )

    async def get_projection(self, consumer: str = "front") -> SpatialProjection:
        """Convenience wrapper for callers already bound to this session."""
        return await self.build_projection(self.session_id, consumer=consumer)

    async def shutdown(self) -> None:
        await self.service.shutdown()

    def _session(self, session_id: str | None) -> str:
        if not session_id:
            return self.session_id
        if session_id != self.session_id:
            raise ValueError(
                f"SpatialHandle bound to session {self.session_id!r}, got {session_id!r}"
            )
        return session_id


def build_spatial_handle(
    bundle: SpatialServiceBundle,
    *,
    session_id: str,
    principal_id: str | None = None,
    actor_id: str | None = None,
    device_id: str | None = None,
    installation_id: str | None = None,
    state_manager: Any | None = None,
    state_adapter: Any | None = None,
    selfmodel_handle: Any | None = None,
) -> SpatialHandle:
    """Build a per-session spatial handle from a Tier-1 bundle."""
    adapter = state_adapter
    if adapter is None:
        adapter = SpatialStateAdapter(state_manager)
    policy = SelfModelSpatialPolicyAdapter(selfmodel_handle, config=bundle.config)
    service = bundle.build_service(state_port=adapter, policy_port=policy)
    binding = SpatialSessionBinding(
        session_id=session_id,
        principal_id=principal_id,
        actor_id=actor_id,
        device_id=device_id,
        installation_id=installation_id,
    )
    return SpatialHandle(bundle=bundle, binding=binding, state_adapter=adapter, service=service)


__all__ = ["SpatialHandle", "build_spatial_handle"]
