"""Grounding projection policy helpers."""

from __future__ import annotations

from k1.grounding.config import GroundingConfig
from k1.grounding.errors import ProjectionDeniedError
from k1.grounding.types import ConsumerScope, GroundingEnvelope
from k1.spatial.constants import DEFAULT_CONSUMER_PRECISION


def default_consumer_scope(
    consumer: str,
    *,
    config: GroundingConfig | None = None,
    task_scope: str | None = None,
    privacy_scope: str | None = None,
) -> ConsumerScope:
    """Return conservative default scope for a grounding consumer."""
    effective_config = config or GroundingConfig()
    allowed = ("temporal", "spatial", "identity_refs")
    if consumer in {"agent", "tool", "fabric"}:
        allowed = ("temporal", "spatial", "identity_refs", "execution_metadata")
    spatial_precision = DEFAULT_CONSUMER_PRECISION.get(consumer, "hidden")
    if effective_config.raw_spatial_allowed_by_default:
        spatial_precision = "raw"
    return ConsumerScope(
        consumer=consumer,
        allowed_context_sections=allowed,
        denied_context_sections=(),
        temporal_precision="exact",
        spatial_precision=spatial_precision,
        privacy_scope=privacy_scope or "standard",
    )


def assert_projection_allowed(envelope: GroundingEnvelope, scope: ConsumerScope) -> None:
    """Raise when a consumer scope cannot receive the envelope."""
    if not scope.consumer:
        raise ProjectionDeniedError("consumer scope is missing")
    if envelope.consumer and envelope.consumer != scope.consumer:
        raise ProjectionDeniedError(
            f"envelope built for {envelope.consumer!r}, not {scope.consumer!r}"
        )


__all__ = ["assert_projection_allowed", "default_consumer_scope"]
