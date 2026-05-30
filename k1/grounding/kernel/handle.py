"""Per-session Grounding handle exposed to kernel consumers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from k1.grounding.adapters import (
    GroundingStateAdapter,
    SelfModelIdentityAdapter,
    SelfModelPolicyAdapter,
    SpatialHandleAdapter,
    TemporalHandleAdapter,
)
from k1.grounding.kernel.bootstrap import GroundingServiceBundle
from k1.grounding.kernel.session_binding import GroundingSessionBinding
from k1.grounding.types import (
    AgentGroundingLease,
    GroundingEnvelope,
    GroundingProjection,
)
from k1.temporal.types import CandidateSpan


@dataclass
class GroundingHandle:
    """Session-scoped facade for grounding projections and leases."""

    bundle: GroundingServiceBundle
    binding: GroundingSessionBinding
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
        consumer: str | None = None,
        turn_id: str | None = None,
        trace_id: str | None = None,
        candidates: Iterable[str | CandidateSpan] = (),
        user_text_candidates: Iterable[str | CandidateSpan] | None = None,
        device_id: str | None = None,
        installation_id: str | None = None,
    ) -> GroundingEnvelope:
        effective_candidates = (
            tuple(user_text_candidates) if user_text_candidates is not None else candidates
        )
        return await self.service.refresh_turn(
            self._session(session_id),
            consumer=consumer,
            turn_id=turn_id,
            trace_id=trace_id,
            candidates=effective_candidates,
            device_id=device_id or self.device_id,
            installation_id=installation_id or self.installation_id,
        )

    async def build_envelope(
        self,
        session_id: str | None = None,
        *,
        consumer: str | None = None,
        turn_id: str | None = None,
        trace_id: str | None = None,
        device_id: str | None = None,
        installation_id: str | None = None,
    ) -> GroundingEnvelope:
        return await self.service.build_envelope(
            self._session(session_id),
            consumer=consumer,
            turn_id=turn_id,
            trace_id=trace_id,
            device_id=device_id or self.device_id,
            installation_id=installation_id or self.installation_id,
        )

    async def create_envelope(
        self,
        session_id: str | None = None,
        consumer: str = "front",
        *,
        turn_id: str | None = None,
        trace_id: str | None = None,
    ) -> GroundingEnvelope:
        """Kernel IGroundingPort alias for building an envelope."""
        return await self.build_envelope(
            session_id,
            consumer=consumer,
            turn_id=turn_id,
            trace_id=trace_id,
        )

    async def build_projection(
        self,
        session_id: str | GroundingEnvelope | None = None,
        consumer: str | None = None,
        **kwargs: Any,
    ) -> GroundingProjection:
        if isinstance(session_id, GroundingEnvelope):
            kwargs.pop("consumer", None)
            return await self.service.project_envelope(session_id, **kwargs)
        return await self.service.build_projection(
            self._session(session_id), consumer=consumer, **kwargs
        )

    async def project_envelope(
        self,
        envelope: GroundingEnvelope,
        *,
        require_fresh: bool = False,
    ) -> GroundingProjection:
        return await self.service.project_envelope(envelope, require_fresh=require_fresh)

    async def get_projection(self, consumer: str = "front") -> GroundingProjection:
        """Convenience wrapper for callers already bound to this session."""
        return await self.build_projection(self.session_id, consumer=consumer)

    async def issue_agent_lease(
        self,
        session_id: str | None = None,
        *,
        task_scope: str = "default",
        privacy_scope: str = "standard",
        consumer: str = "agent",
        **kwargs: Any,
    ) -> AgentGroundingLease:
        return await self.service.issue_agent_lease(
            self._session(session_id),
            task_scope=task_scope,
            privacy_scope=privacy_scope,
            consumer=consumer,
            **kwargs,
        )

    async def build_agent_lease(
        self,
        envelope: GroundingEnvelope,
        *,
        task_scope: str,
        ttl_seconds: int,
    ) -> AgentGroundingLease:
        """Kernel IGroundingPort alias for issuing an agent lease."""
        projection = await self.service.project_envelope(envelope)
        scope = await self.service._consumer_scope(
            "agent",
            task_scope=task_scope,
            privacy_scope="standard",
        )
        role_refs = tuple(await self.service._role_refs(envelope.session_id))
        from k1.grounding.serialization import lease_to_dict, projection_to_dict
        from k1.grounding.service.lease_builder import (
            build_agent_lease as _build_agent_lease,
        )

        lease = _build_agent_lease(
            lease_id=self.service._id_port.new_lease_id(),
            projection=projection,
            scope=scope,
            config=self.bundle.config,
            subject_ref=projection.metadata.get("identity_ref"),
            role_refs=role_refs,
            task_scope=task_scope,
            privacy_scope="standard",
            metadata={"requested_ttl_seconds": int(ttl_seconds)},
            ttl_seconds=ttl_seconds,
        )
        await self.service._write_state_merge(
            envelope.session_id,
            {"last_projection": projection_to_dict(projection), "last_lease": lease_to_dict(lease)},
        )
        return lease

    async def refresh_if_stale(self, envelope: GroundingEnvelope) -> GroundingEnvelope:
        """Return a refreshed envelope only when stale under bundle policy."""
        from k1.grounding.service.stale_envelope_checker import is_stale

        if not is_stale(envelope, config=self.bundle.config):
            return envelope
        return await self.build_envelope(
            envelope.session_id,
            consumer=envelope.consumer,
            turn_id=envelope.turn_id,
            trace_id=envelope.trace_id,
        )

    async def shutdown(self) -> None:
        await self.service.shutdown()

    def _session(self, session_id: str | None) -> str:
        if not session_id:
            return self.session_id
        if session_id != self.session_id:
            raise ValueError(
                f"GroundingHandle bound to session {self.session_id!r}, got {session_id!r}"
            )
        return session_id


def build_grounding_handle(
    bundle: GroundingServiceBundle,
    *,
    session_id: str,
    principal_id: str | None = None,
    actor_id: str | None = None,
    device_id: str | None = None,
    installation_id: str | None = None,
    state_manager: Any | None = None,
    state_adapter: Any | None = None,
    temporal_handle: Any | None = None,
    spatial_handle: Any | None = None,
    selfmodel_handle: Any | None = None,
) -> GroundingHandle:
    """Build a per-session grounding handle from a Tier-1 bundle."""
    adapter = state_adapter
    if adapter is None:
        adapter = GroundingStateAdapter(
            state_manager,
            allow_memory_fallback=state_manager is None,
        )

    temporal_port = TemporalHandleAdapter(temporal_handle) if temporal_handle is not None else None
    spatial_port = SpatialHandleAdapter(spatial_handle)
    identity_port = SelfModelIdentityAdapter(selfmodel_handle, actor_id=actor_id)
    policy_port = SelfModelPolicyAdapter(selfmodel_handle)
    service = bundle.build_service(
        state_port=adapter,
        temporal_port=temporal_port,
        spatial_port=spatial_port,
        identity_port=identity_port,
        policy_port=policy_port,
    )
    binding = GroundingSessionBinding(
        session_id=session_id,
        principal_id=principal_id,
        actor_id=actor_id,
        device_id=device_id,
        installation_id=installation_id,
    )
    return GroundingHandle(bundle=bundle, binding=binding, state_adapter=adapter, service=service)


__all__ = ["GroundingHandle", "build_grounding_handle"]
