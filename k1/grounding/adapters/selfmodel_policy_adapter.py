"""Policy adapter for grounding projection scope decisions."""

from __future__ import annotations

import inspect
from typing import Any

from k1.grounding.ports import IGroundingPolicyPort
from k1.grounding.types import ConsumerScope, GroundingEnvelope
from k1.spatial.constants import DEFAULT_CONSUMER_PRECISION


class SelfModelPolicyAdapter(IGroundingPolicyPort):
    """Default-deny-aware scope adapter with safe M1.5 defaults."""

    def __init__(self, selfmodel_handle: Any | None = None) -> None:
        self._handle = selfmodel_handle

    async def get_consumer_scope(
        self,
        consumer: str,
        *,
        task_scope: str | None = None,
        privacy_scope: str | None = None,
    ) -> ConsumerScope:
        allowed = ("temporal", "spatial", "identity_refs", "device_surface")
        if consumer in {"front", "planner"}:
            allowed = ("temporal", "spatial", "identity_refs")
        if consumer in {"agent", "tool", "fabric"}:
            allowed = ("temporal", "spatial", "identity_refs", "execution_metadata")
        override = await self._scope_override(
            consumer,
            task_scope=task_scope,
            privacy_scope=privacy_scope,
            allowed=allowed,
        )
        if override is not None:
            return override
        return ConsumerScope(
            consumer=consumer,
            allowed_context_sections=allowed,
            denied_context_sections=(),
            temporal_precision="exact",
            spatial_precision=DEFAULT_CONSUMER_PRECISION.get(consumer, "hidden"),
            privacy_scope=privacy_scope or "standard",
        )

    async def authorize_projection(self, envelope: GroundingEnvelope, scope: ConsumerScope) -> bool:
        return scope.consumer == envelope.consumer or bool(scope.consumer)

    async def _scope_override(
        self,
        consumer: str,
        *,
        task_scope: str | None,
        privacy_scope: str | None,
        allowed: tuple[str, ...],
    ) -> ConsumerScope | None:
        if self._handle is None:
            return None
        method = getattr(self._handle, "get_grounding_consumer_scope", None)
        if not callable(method):
            method = getattr(self._handle, "grounding_consumer_scope", None)
        if not callable(method):
            return None
        result = method(
            consumer,
            task_scope=task_scope,
            privacy_scope=privacy_scope,
        )
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, ConsumerScope):
            return result
        if not isinstance(result, dict):
            return None
        return ConsumerScope(
            consumer=str(result.get("consumer") or consumer),
            allowed_context_sections=tuple(result.get("allowed_context_sections") or allowed),
            denied_context_sections=tuple(result.get("denied_context_sections") or ()),
            temporal_precision=str(result.get("temporal_precision") or "exact"),
            spatial_precision=str(
                result.get("spatial_precision")
                or DEFAULT_CONSUMER_PRECISION.get(consumer, "hidden")
            ),
            privacy_scope=str(result.get("privacy_scope") or privacy_scope or "standard"),
        )


AllowAllGroundingPolicyAdapter = SelfModelPolicyAdapter

__all__ = ["AllowAllGroundingPolicyAdapter", "SelfModelPolicyAdapter"]
