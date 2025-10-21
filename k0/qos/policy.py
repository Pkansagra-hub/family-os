"""Helpers for applying policy obligations to QoS contexts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, cast

from .context import QoSContext


@dataclass(slots=True)
class QoSTightening:
    """Represents tightening directives emitted by policy obligations."""

    fanout: int | None = None
    top_k: int | None = None
    time_slice_ms: int | None = None


def apply_qos_obligations(
    qos: QoSContext,
    obligations: Sequence[Any],
) -> QoSTightening:
    """Apply QoS tightening obligations and return the resulting schedule."""

    schedule = QoSTightening()

    for obligation in obligations:
        if getattr(obligation, "name", "") != "kernel.qos.tighten":
            continue

        details = cast(Mapping[str, Any], getattr(obligation, "details", {}) or {})

        fanout_limit = _extract_limit(details, ("fanout", "fanout_max", "max_fanout"))
        if fanout_limit is not None:
            qos.tighten(fanout=fanout_limit)
            schedule.fanout = (
                fanout_limit
                if schedule.fanout is None
                else min(schedule.fanout, fanout_limit)
            )

        top_k_limit = _extract_limit(details, ("top_k", "top_k_max"))
        if top_k_limit is not None:
            qos.tighten(top_k=top_k_limit)
            schedule.top_k = (
                top_k_limit
                if schedule.top_k is None
                else min(schedule.top_k, top_k_limit)
            )

        time_slice_limit = _extract_limit(
            details,
            (
                "time_slice",
                "time_slice_ms",
                "latency_ms",
                "target_latency_ms",
                "max_latency_ms",
            ),
        )
        if time_slice_limit is not None:
            schedule.time_slice_ms = (
                time_slice_limit
                if schedule.time_slice_ms is None
                else min(schedule.time_slice_ms, time_slice_limit)
            )

    return schedule


def _extract_limit(details: Mapping[str, Any], keys: Sequence[str]) -> int | None:
    for key in keys:
        if key not in details:
            continue
        value = coerce_positive_int(details[key])
        if value is not None:
            return value
    return None


def coerce_positive_int(value: Any) -> int | None:
    """Best-effort coercion of a value to a positive integer."""

    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        numeric = float(value)
        integer_value = int(numeric)
        return integer_value if integer_value > 0 else None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            numeric = float(text)
        except ValueError:
            return None
        integer_value = int(numeric)
        return integer_value if integer_value > 0 else None

    if isinstance(value, Mapping):
        mapping_value = cast(Mapping[str, Any], value)
        for candidate_key in ("requested", "value", "current", "max", "limit"):
            candidate = mapping_value.get(candidate_key)
            coerced = coerce_positive_int(candidate)
            if coerced is not None:
                return coerced
        return None

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in cast(Sequence[Any], value):
            coerced = coerce_positive_int(item)
            if coerced is not None:
                return coerced
        return None

    return None


__all__ = ["QoSTightening", "apply_qos_obligations", "coerce_positive_int"]
