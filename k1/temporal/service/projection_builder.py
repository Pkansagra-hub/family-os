"""Build policy-shaped temporal projections."""

from __future__ import annotations

from typing import Any, Mapping

from k1.temporal.config import TemporalConfig
from k1.temporal.serialization import dict_to_anchor, dict_to_resolution, dict_to_window
from k1.temporal.service.freshness_evaluator import evaluate_freshness
from k1.temporal.types import TemporalProjection


def build_projection(
    payload: Mapping[str, Any],
    *,
    consumer: str,
    now_utc: str,
    config: TemporalConfig | None = None,
    precision: str = "full",
) -> TemporalProjection:
    """Build a TemporalProjection from serialized temporal state."""

    anchor = dict_to_anchor(payload["anchor"])
    windows = {
        key: dict_to_window(value) for key, value in dict(payload.get("windows", {})).items()
    }
    resolutions = tuple(
        dict_to_resolution(item) for item in payload.get("resolved_expressions", ())
    )
    return TemporalProjection(
        anchor=anchor,
        windows=windows,
        resolved_expressions=resolutions,
        consumer=consumer,
        freshness=evaluate_freshness(anchor, now_utc, config=config),
        precision=precision,
    )


__all__ = ["build_projection"]
