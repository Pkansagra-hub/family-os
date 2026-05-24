"""k1.kernel.ports.grounding_port -- IGroundingPort.

Kernel-visible Protocol for the policy-filtered grounding envelope; see
k1.grounding package. Only pure payload types are imported here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.grounding.types import (
    AgentGroundingLease,
    ConsumerScope,
    GroundingEnvelope,
    GroundingFreshness,
    GroundingProjection,
    GroundingSource,
)


@runtime_checkable
class IGroundingPort(Protocol):
    """Kernel boundary for creating and projecting grounding envelopes."""

    async def create_envelope(
        self,
        session_id: str,
        consumer: str,
        *,
        turn_id: str | None = None,
        trace_id: str | None = None,
    ) -> GroundingEnvelope:
        """Create a fresh grounding envelope for a consumer scope."""
        ...  # pragma: no cover

    async def build_projection(
        self,
        envelope: GroundingEnvelope,
        consumer: str,
    ) -> GroundingProjection:
        """Project an envelope according to consumer policy."""
        ...  # pragma: no cover

    async def build_agent_lease(
        self,
        envelope: GroundingEnvelope,
        *,
        task_scope: str,
        ttl_seconds: int,
    ) -> AgentGroundingLease:
        """Grant a TTL-bound grounding lease for a spawned agent."""
        ...  # pragma: no cover

    async def refresh_if_stale(self, envelope: GroundingEnvelope) -> GroundingEnvelope:
        """Return a refreshed envelope when the supplied envelope is stale."""
        ...  # pragma: no cover

    async def shutdown(self) -> None:
        """Release grounding resources owned by this handle or bundle."""
        ...  # pragma: no cover


__all__ = [
    "AgentGroundingLease",
    "ConsumerScope",
    "GroundingEnvelope",
    "GroundingFreshness",
    "GroundingProjection",
    "GroundingSource",
    "IGroundingPort",
]
