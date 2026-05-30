"""Build consumer spatial projections."""

from __future__ import annotations

from k1.spatial.config import SpatialConfig
from k1.spatial.ports import ISpatialPolicyPort
from k1.spatial.service.precision_selector import select_consumer_precision
from k1.spatial.service.privacy_projector import project_context
from k1.spatial.types import SpatialContext, SpatialProjection


def build_spatial_projection(
    *,
    context: SpatialContext,
    consumer: str,
    projection_id: str,
    precision: str,
    config: SpatialConfig | None = None,
    redactions: tuple[str, ...] = (),
) -> SpatialProjection:
    """Synchronous projection builder for already-selected precision."""
    return project_context(
        context,
        consumer=consumer,
        projection_id=projection_id,
        precision=precision,
        config=config,
        redactions=redactions,
    )


class SpatialProjectionBuilder:
    """Policy-aware projection builder."""

    def __init__(
        self,
        *,
        policy_port: ISpatialPolicyPort | None = None,
        config: SpatialConfig | None = None,
    ) -> None:
        self._policy = policy_port
        self._config = config or SpatialConfig()

    async def build(
        self,
        *,
        context: SpatialContext,
        consumer: str,
        projection_id: str,
        subject_ref: str | None = None,
        task_scope: str | None = None,
        capability: str | None = None,
        requested_precision: str | None = None,
    ) -> SpatialProjection:
        precision = await select_consumer_precision(
            policy_port=self._policy,
            session_id=context.session_id,
            consumer=consumer,
            subject_ref=subject_ref,
            task_scope=task_scope,
            capability=capability,
            requested_precision=requested_precision,
        )
        redactions = ()
        if self._policy is not None:
            redactions = await self._policy.redaction_reasons(
                session_id=context.session_id,
                consumer=consumer,
                precision=precision,
                context={"context_id": context.context_id},
            )
        return build_spatial_projection(
            context=context,
            consumer=consumer,
            projection_id=projection_id,
            precision=precision,
            config=self._config,
            redactions=redactions,
        )


__all__ = ["SpatialProjectionBuilder", "build_spatial_projection"]
