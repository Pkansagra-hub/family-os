"""Explicit serialization helpers for temporal payload dataclasses."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from k1.temporal.types import (
    CandidateSpan,
    ResolvedTemporalExpression,
    RoutineRef,
    TemporalAnchor,
    TemporalProjection,
    TemporalTurnSnapshot,
    TemporalWindow,
)


def _plain(value: Any) -> Any:
    """Convert nested dataclasses/mappings/tuples into JSON-safe values."""

    if is_dataclass(value):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _dict(value: Mapping[str, Any]) -> dict[str, Any]:
    return dict(value)


def anchor_to_dict(anchor: TemporalAnchor) -> dict[str, Any]:
    return _plain(anchor)


def dict_to_anchor(payload: Mapping[str, Any]) -> TemporalAnchor:
    return TemporalAnchor(**_dict(payload))


def window_to_dict(window: TemporalWindow) -> dict[str, Any]:
    return _plain(window)


def dict_to_window(payload: Mapping[str, Any]) -> TemporalWindow:
    return TemporalWindow(**_dict(payload))


def resolution_to_dict(resolution: ResolvedTemporalExpression) -> dict[str, Any]:
    data = _plain(resolution)
    if resolution.window is not None:
        data["window"] = window_to_dict(resolution.window)
    return data


def dict_to_resolution(payload: Mapping[str, Any]) -> ResolvedTemporalExpression:
    data = _dict(payload)
    if data.get("window") is not None:
        data["window"] = dict_to_window(data["window"])
    return ResolvedTemporalExpression(**data)


def projection_to_dict(projection: TemporalProjection) -> dict[str, Any]:
    return {
        "anchor": anchor_to_dict(projection.anchor),
        "windows": {key: window_to_dict(value) for key, value in projection.windows.items()},
        "resolved_expressions": [
            resolution_to_dict(item) for item in projection.resolved_expressions
        ],
        "consumer": projection.consumer,
        "freshness": projection.freshness,
        "precision": projection.precision,
    }


def dict_to_projection(payload: Mapping[str, Any]) -> TemporalProjection:
    data = _dict(payload)
    return TemporalProjection(
        anchor=dict_to_anchor(data["anchor"]),
        windows={key: dict_to_window(value) for key, value in data.get("windows", {}).items()},
        resolved_expressions=tuple(
            dict_to_resolution(item) for item in data.get("resolved_expressions", ())
        ),
        consumer=str(data["consumer"]),
        freshness=data["freshness"],
        precision=str(data["precision"]),
    )


def candidate_to_dict(candidate: CandidateSpan) -> dict[str, Any]:
    return _plain(candidate)


def dict_to_candidate(payload: Mapping[str, Any]) -> CandidateSpan:
    return CandidateSpan(**_dict(payload))


def routine_ref_to_dict(routine: RoutineRef) -> dict[str, Any]:
    return _plain(routine)


def dict_to_routine_ref(payload: Mapping[str, Any]) -> RoutineRef:
    return RoutineRef(**_dict(payload))


def turn_snapshot_to_dict(snapshot: TemporalTurnSnapshot) -> dict[str, Any]:
    return {
        "session_id": snapshot.session_id,
        "turn_id": snapshot.turn_id,
        "anchor": anchor_to_dict(snapshot.anchor),
        "windows": {key: window_to_dict(value) for key, value in snapshot.windows.items()},
        "resolved_expressions": [
            resolution_to_dict(item) for item in snapshot.resolved_expressions
        ],
        "refreshed_at_utc": snapshot.refreshed_at_utc,
        "source": snapshot.source,
    }


__all__ = [
    "anchor_to_dict",
    "candidate_to_dict",
    "dict_to_anchor",
    "dict_to_candidate",
    "dict_to_projection",
    "dict_to_resolution",
    "dict_to_routine_ref",
    "dict_to_window",
    "projection_to_dict",
    "resolution_to_dict",
    "routine_ref_to_dict",
    "turn_snapshot_to_dict",
    "window_to_dict",
]
