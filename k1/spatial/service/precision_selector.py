"""Select spatial precision by consumer and policy."""

from __future__ import annotations

from k1.spatial.constants import DEFAULT_CONSUMER_PRECISION, SPATIAL_PRECISIONS
from k1.spatial.ports import ISpatialPolicyPort

_ORDER = {name: index for index, name in enumerate(SPATIAL_PRECISIONS)}


def clamp_precision(requested: str | None, allowed: str | None) -> str:
    """Return the strongest precision no stronger than allowed."""
    requested_name = requested if requested in _ORDER else "hidden"
    allowed_name = allowed if allowed in _ORDER else "hidden"
    return requested_name if _ORDER[requested_name] <= _ORDER[allowed_name] else allowed_name


def default_precision_for_consumer(consumer: str) -> str:
    """Return default precision for a consumer family."""
    return DEFAULT_CONSUMER_PRECISION.get(consumer, "semantic")


async def select_consumer_precision(
    *,
    policy_port: ISpatialPolicyPort | None,
    session_id: str,
    consumer: str,
    subject_ref: str | None = None,
    task_scope: str | None = None,
    capability: str | None = None,
    requested_precision: str | None = None,
) -> str:
    """Select precision with policy as source of truth."""
    requested = requested_precision or default_precision_for_consumer(consumer)
    if policy_port is None:
        return clamp_precision(requested, default_precision_for_consumer(consumer))
    allowed = await policy_port.allowed_precision(
        session_id=session_id,
        consumer=consumer,
        subject_ref=subject_ref,
        task_scope=task_scope,
        capability=capability,
        requested_precision=requested,
    )
    return clamp_precision(requested, allowed)


__all__ = ["clamp_precision", "default_precision_for_consumer", "select_consumer_precision"]
