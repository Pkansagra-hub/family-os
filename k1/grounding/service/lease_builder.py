"""Build agent grounding leases from grounding projections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from k1.grounding.config import GroundingConfig
from k1.grounding.types import AgentGroundingLease, ConsumerScope, GroundingProjection


def build_agent_lease(
    *,
    lease_id: str,
    projection: GroundingProjection,
    scope: ConsumerScope,
    config: GroundingConfig,
    subject_ref: str | None = None,
    group_refs: tuple[str, ...] = (),
    role_refs: tuple[str, ...] = (),
    task_scope: str = "default",
    privacy_scope: str = "standard",
    refresh_allowed: bool = True,
    ttl_seconds: int | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AgentGroundingLease:
    """Issue an agent lease; spatial is always present, even when unknown."""
    issued = datetime.now(UTC)
    effective_ttl = int(ttl_seconds or config.agent_lease_ttl_seconds)
    expires = issued + timedelta(seconds=max(effective_ttl, 1))
    return AgentGroundingLease(
        lease_id=lease_id,
        envelope_id=projection.envelope_id,
        issued_at_utc=issued.isoformat(),
        expires_at_utc=expires.isoformat(),
        temporal=projection.temporal,
        spatial=projection.spatial,
        subject_ref=subject_ref or projection.metadata.get("identity_ref"),
        group_refs=tuple(group_refs or tuple(projection.metadata.get("group_refs", ()))),
        role_refs=tuple(role_refs),
        task_scope=task_scope,
        privacy_scope=privacy_scope,
        allowed_context_sections=tuple(scope.allowed_context_sections),
        denied_context_sections=tuple(scope.denied_context_sections),
        redactions=tuple(projection.redactions),
        refresh_allowed=refresh_allowed,
        status="active",
        metadata=dict(metadata or {}),
    )


__all__ = ["build_agent_lease"]
