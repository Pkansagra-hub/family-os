"""Spatial policy adapter backed by SelfModel when available."""

from __future__ import annotations

from typing import Any, Mapping

from k1.spatial.config import SpatialConfig
from k1.spatial.ports import ISpatialPolicyPort
from k1.spatial.service.precision_selector import clamp_precision


class SelfModelSpatialPolicyAdapter(ISpatialPolicyPort):
    """Map SelfModel/constitution decisions into spatial precision decisions."""

    def __init__(self, self_model: Any | None = None, config: SpatialConfig | None = None) -> None:
        self._self_model = self_model
        self._config = config or SpatialConfig()

    async def allowed_precision(
        self,
        *,
        session_id: str,
        consumer: str,
        subject_ref: str | None = None,
        task_scope: str | None = None,
        capability: str | None = None,
        requested_precision: str | None = None,
    ) -> str:
        method = getattr(self._self_model, "allowed_spatial_precision", None)
        if callable(method):
            allowed = await method(
                session_id=session_id,
                consumer=consumer,
                subject_ref=subject_ref,
                task_scope=task_scope,
                capability=capability,
                requested_precision=requested_precision,
            )
        else:
            allowed = self._config.consumer_precision.get(consumer, self._config.default_precision)
        return clamp_precision(requested_precision or allowed, allowed)

    async def redaction_reasons(
        self,
        *,
        session_id: str,
        consumer: str,
        precision: str,
        context: Mapping[str, Any] | None = None,
    ) -> tuple[str, ...]:
        method = getattr(self._self_model, "spatial_redaction_reasons", None)
        if callable(method):
            return tuple(
                await method(
                    session_id=session_id,
                    consumer=consumer,
                    precision=precision,
                    context=context or {},
                )
            )
        if precision == "hidden":
            return ("policy_hidden",)
        if precision != "raw":
            return ("raw_location_denied",)
        return ()


__all__ = ["SelfModelSpatialPolicyAdapter"]
