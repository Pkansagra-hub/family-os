"""Grounding projection policy boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.grounding.types import ConsumerScope, GroundingEnvelope


@runtime_checkable
class IGroundingPolicyPort(Protocol):
    """Authorize envelope projection and lease creation."""

    async def get_consumer_scope(
        self,
        consumer: str,
        *,
        task_scope: str | None = None,
        privacy_scope: str | None = None,
    ) -> ConsumerScope:
        """Return the context scope allowed for a consumer."""
        ...  # pragma: no cover

    async def authorize_projection(self, envelope: GroundingEnvelope, scope: ConsumerScope) -> bool:
        """Return True when a projection may be built for the scope."""
        ...  # pragma: no cover


__all__ = ["IGroundingPolicyPort"]
