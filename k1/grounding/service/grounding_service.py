"""Top-level grounding service facade."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from k1.grounding.config import GroundingConfig
from k1.grounding.errors import ProjectionDeniedError, StaleEnvelopeError
from k1.grounding.events import (
    GroundingEnvelopeCreatedPayload,
    GroundingEnvelopeStalePayload,
    GroundingLeaseCreatedPayload,
    GroundingProjectionCreatedPayload,
    GroundingProjectionDeniedPayload,
)
from k1.grounding.ports import (
    IGroundingEventPort,
    IGroundingIdentityPort,
    IGroundingIdPort,
    IGroundingMetricsPort,
    IGroundingPolicyPort,
    IGroundingSpatialPort,
    IGroundingStatePort,
    IGroundingTemporalPort,
)
from k1.grounding.serialization import (
    envelope_to_dict,
    lease_to_dict,
    projection_to_dict,
)
from k1.grounding.service.envelope_builder import (
    build_envelope as build_envelope_payload,
)
from k1.grounding.service.event_emitter import GroundingEventEmitter
from k1.grounding.service.health import GroundingHealthStatus
from k1.grounding.service.lease_builder import build_agent_lease
from k1.grounding.service.projection_builder import (
    build_projection as build_projection_payload,
)
from k1.grounding.service.projection_policy import (
    assert_projection_allowed,
    default_consumer_scope,
)
from k1.grounding.service.stale_envelope_checker import envelope_age_ms, is_stale
from k1.grounding.types import (
    AgentGroundingLease,
    GroundingEnvelope,
    GroundingProjection,
)
from k1.temporal.types import CandidateSpan


class GroundingService:
    """Authoritative per-session grounding envelope/projection service."""

    def __init__(
        self,
        *,
        temporal_port: IGroundingTemporalPort,
        spatial_port: IGroundingSpatialPort,
        id_port: IGroundingIdPort,
        state_port: IGroundingStatePort,
        identity_port: IGroundingIdentityPort | None = None,
        policy_port: IGroundingPolicyPort | None = None,
        event_port: IGroundingEventPort | None = None,
        metrics_port: IGroundingMetricsPort | None = None,
        config: GroundingConfig | None = None,
    ) -> None:
        self._temporal_port = temporal_port
        self._spatial_port = spatial_port
        self._id_port = id_port
        self._state_port = state_port
        self._identity_port = identity_port
        self._policy_port = policy_port
        self._event_port = event_port
        self._event_emitter = GroundingEventEmitter(event_port)
        self._metrics_port = metrics_port
        self._config = config or GroundingConfig()
        self._closed = False

    async def refresh_turn(
        self,
        session_id: str,
        *,
        consumer: str | None = None,
        turn_id: str | None = None,
        trace_id: str | None = None,
        candidates: Iterable[str | CandidateSpan] = (),
        device_id: str | None = None,
        installation_id: str | None = None,
    ) -> GroundingEnvelope:
        """Refresh temporal and spatial state, then build a fresh grounding envelope."""
        effective_consumer = consumer or self._config.default_consumer
        scope = await self._consumer_scope(effective_consumer)
        await self._temporal_port.refresh_turn(
            session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            candidates=candidates,
            device_id=device_id,
            installation_id=installation_id,
        )
        await self._spatial_port.refresh_turn(
            session_id,
            effective_consumer,
            device_id=device_id,
            installation_id=installation_id,
            requested_precision=scope.spatial_precision,
        )
        return await self.build_envelope(
            session_id,
            consumer=effective_consumer,
            turn_id=turn_id,
            trace_id=trace_id,
            device_id=device_id,
            installation_id=installation_id,
        )

    async def build_envelope(
        self,
        session_id: str,
        *,
        consumer: str | None = None,
        turn_id: str | None = None,
        trace_id: str | None = None,
        device_id: str | None = None,
        installation_id: str | None = None,
    ) -> GroundingEnvelope:
        """Build and persist a canonical grounding envelope for one consumer."""
        effective_consumer = consumer or self._config.default_consumer
        scope = await self._consumer_scope(effective_consumer)
        temporal = await self._temporal_port.build_projection(session_id, effective_consumer)
        spatial = await self._spatial_port.build_projection(
            session_id,
            effective_consumer,
            device_id=device_id,
            installation_id=installation_id,
            requested_precision=scope.spatial_precision,
        )
        identity_ref = await self._identity_ref(session_id)
        group_refs = await self._group_refs(session_id)
        envelope = build_envelope_payload(
            envelope_id=self._id_port.new_envelope_id(),
            session_id=session_id,
            consumer=effective_consumer,
            temporal=temporal,
            spatial=spatial,
            identity_ref=identity_ref,
            group_refs=group_refs,
            device_surface=spatial.active_device_surface,
            policy_scope=scope.consumer,
            turn_id=turn_id,
            trace_id=trace_id,
            metadata={"allowed_context_sections": list(scope.allowed_context_sections)},
        )
        await self._write_state_merge(session_id, {"last_envelope": envelope_to_dict(envelope)})
        await self._event_emitter.publish_envelope_created(
            GroundingEnvelopeCreatedPayload(
                envelope_id=envelope.envelope_id,
                session_id=session_id,
                created_at_utc=envelope.created_at_utc,
                temporal_anchor_id=envelope.temporal.anchor.anchor_id,
                spatial_context_id=envelope.spatial.context_id,
                trace_id=trace_id,
            )
        )
        if self._metrics_port is not None:
            self._metrics_port.incr("grounding.build_envelope")
        return envelope

    async def build_projection(
        self,
        session_id: str,
        *,
        consumer: str | None = None,
        turn_id: str | None = None,
        trace_id: str | None = None,
        device_id: str | None = None,
        installation_id: str | None = None,
        require_fresh: bool = False,
    ) -> GroundingProjection:
        """Build a consumer projection from a fresh grounding envelope."""
        envelope = await self.build_envelope(
            session_id,
            consumer=consumer,
            turn_id=turn_id,
            trace_id=trace_id,
            device_id=device_id,
            installation_id=installation_id,
        )
        return await self.project_envelope(envelope, require_fresh=require_fresh)

    async def get_projection(
        self,
        session_id: str,
        consumer: str | None = None,
        **kwargs: Any,
    ) -> GroundingProjection:
        """Convenience alias for callers that ask for a projection directly."""
        return await self.build_projection(session_id, consumer=consumer, **kwargs)

    async def project_envelope(
        self,
        envelope: GroundingEnvelope,
        *,
        require_fresh: bool = False,
    ) -> GroundingProjection:
        """Project an existing envelope through consumer policy."""
        scope = await self._consumer_scope(envelope.consumer)
        allowed = True
        if self._policy_port is not None:
            allowed = await self._policy_port.authorize_projection(envelope, scope)
        if not allowed:
            await self._event_emitter.publish_projection_denied(
                GroundingProjectionDeniedPayload(
                    envelope_id=envelope.envelope_id,
                    session_id=envelope.session_id,
                    consumer=scope.consumer,
                    reason="policy_denied",
                    denied_at_utc=envelope.created_at_utc,
                )
            )
            raise ProjectionDeniedError("grounding projection denied by policy")
        assert_projection_allowed(envelope, scope)
        if require_fresh and is_stale(envelope, config=self._config):
            age_ms = envelope_age_ms(envelope)
            await self._event_emitter.publish_envelope_stale(
                GroundingEnvelopeStalePayload(
                    envelope_id=envelope.envelope_id,
                    session_id=envelope.session_id,
                    stale_since_utc=envelope.created_at_utc,
                    age_ms=age_ms,
                    freshness_state=envelope.freshness.status,
                )
            )
            raise StaleEnvelopeError("grounding envelope is stale")
        projection = build_projection_payload(
            projection_id=self._id_port.new_projection_id(),
            envelope=envelope,
            scope=scope,
        )
        await self._write_state_merge(
            envelope.session_id,
            {
                "last_envelope": envelope_to_dict(envelope),
                "last_projection": projection_to_dict(projection),
            },
        )
        await self._event_emitter.publish_projection_created(
            GroundingProjectionCreatedPayload(
                projection_id=projection.projection_id,
                envelope_id=projection.envelope_id,
                session_id=envelope.session_id,
                consumer=projection.consumer,
                created_at_utc=envelope.created_at_utc,
                redactions=tuple(projection.redactions),
            )
        )
        if self._metrics_port is not None:
            self._metrics_port.incr("grounding.build_projection")
        return projection

    async def issue_agent_lease(
        self,
        session_id: str,
        *,
        task_scope: str = "default",
        privacy_scope: str = "standard",
        consumer: str = "agent",
        role_refs: tuple[str, ...] | None = None,
        refresh_allowed: bool = True,
        ttl_seconds: int | None = None,
        **projection_kwargs: Any,
    ) -> AgentGroundingLease:
        """Build a projection and issue an agent grounding lease."""
        projection = await self.build_projection(session_id, consumer=consumer, **projection_kwargs)
        scope = await self._consumer_scope(
            consumer, task_scope=task_scope, privacy_scope=privacy_scope
        )
        group_refs = tuple(projection.metadata.get("group_refs", ()))
        roles = tuple(role_refs or await self._role_refs(session_id))
        lease = build_agent_lease(
            lease_id=self._id_port.new_lease_id(),
            projection=projection,
            scope=scope,
            config=self._config,
            subject_ref=projection.metadata.get("identity_ref"),
            group_refs=group_refs,
            role_refs=roles,
            task_scope=task_scope,
            privacy_scope=privacy_scope,
            refresh_allowed=refresh_allowed,
            ttl_seconds=ttl_seconds,
            metadata={"requested_ttl_seconds": int(ttl_seconds)} if ttl_seconds else None,
        )
        await self._write_state_merge(
            session_id,
            {"last_projection": projection_to_dict(projection), "last_lease": lease_to_dict(lease)},
        )
        await self._event_emitter.publish_lease_created(
            GroundingLeaseCreatedPayload(
                lease_id=lease.lease_id,
                envelope_id=lease.envelope_id,
                issued_at_utc=lease.issued_at_utc,
                expires_at_utc=lease.expires_at_utc,
                task_scope=lease.task_scope,
                subject_ref=lease.subject_ref,
            )
        )
        if self._metrics_port is not None:
            self._metrics_port.incr("grounding.issue_agent_lease")
        return lease

    async def shutdown(self) -> None:
        self._closed = True

    def health(self) -> GroundingHealthStatus:
        return GroundingHealthStatus(
            ready=not self._closed,
            temporal_connected=self._temporal_port is not None,
            spatial_connected=self._spatial_port is not None,
            state_connected=self._state_port is not None,
            identity_connected=self._identity_port is not None,
            policy_connected=self._policy_port is not None,
            event_connected=self._event_port is not None,
        )

    async def _identity_ref(self, session_id: str) -> str | None:
        if self._identity_port is None:
            return None
        return await self._identity_port.get_identity_ref(session_id)

    async def _group_refs(self, session_id: str) -> tuple[str, ...]:
        if self._identity_port is None:
            return ()
        return tuple(await self._identity_port.get_group_refs(session_id))

    async def _role_refs(self, session_id: str) -> tuple[str, ...]:
        if self._identity_port is None:
            return ()
        return tuple(await self._identity_port.get_role_refs(session_id))

    async def _consumer_scope(
        self,
        consumer: str,
        *,
        task_scope: str | None = None,
        privacy_scope: str | None = None,
    ):
        if self._policy_port is not None:
            return await self._policy_port.get_consumer_scope(
                consumer,
                task_scope=task_scope,
                privacy_scope=privacy_scope,
            )
        return default_consumer_scope(
            consumer,
            config=self._config,
            task_scope=task_scope,
            privacy_scope=privacy_scope,
        )

    async def _write_state_merge(self, session_id: str, payload: dict[str, Any]) -> None:
        current = await self._state_port.read_section(session_id)
        merged = dict(current or {})
        merged.update(payload)
        await self._state_port.write_section(session_id, merged)


__all__ = ["GroundingService"]
