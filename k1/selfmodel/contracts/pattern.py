"""Typed L3 pattern sub-shapes (M7.E1).

The whiteboard's ``S.pattern`` layer is the richest part of the self
model — preferences, hobbies, likes, dislikes, goals, routines,
habits, rhythms, communication style. This is what makes the LLM
*know who it's talking to*.

Contract-only. Writers live in ``k1.selfmodel.service.self_model``
(typed wrappers); the capsule renderer surfaces these fields under
``[self]/[preferences]/[hobbies]/[goals]/[routines]/[context]``
blocks.

Back-compat: ``coerce_l3()`` turns the legacy
``dict[str, object]`` payload (from pre-M7 stored snapshots) into a
typed ``L3PatternShape`` so existing data loads without migration.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from k1.selfmodel.contracts.family_model import RoutineRef

__all__ = [
    "Goal",
    "Habit",
    "L3PatternShape",
    "coerce_l3",
]


@dataclass(frozen=True)
class Goal:
    """A user-declared goal."""

    goal_id: str
    summary: str = ""
    horizon: str = (
        "this_week"  # "this_week" | "this_month" | "this_quarter" | "this_year" | "lifelong"
    )
    status: str = "active"  # "active" | "paused" | "achieved" | "abandoned"


@dataclass(frozen=True)
class Habit:
    """A recurring user habit."""

    habit_id: str
    summary: str = ""
    cadence: str = "daily"  # "daily" | "weekdays" | "weekly:mon,wed,fri" | ...


@dataclass(frozen=True)
class L3PatternShape:
    """Typed L3 pattern layer.

    Every field defaults to empty so a brand-new actor has a valid
    snapshot without any onboarding writes.
    """

    preferences: dict[str, str] = field(default_factory=dict)
    hobbies: tuple[str, ...] = ()
    likes: tuple[str, ...] = ()
    dislikes: tuple[str, ...] = ()
    goals: tuple[Goal, ...] = ()
    routines: tuple[RoutineRef, ...] = ()
    habits: tuple[Habit, ...] = ()
    rhythms: dict[str, str] = field(default_factory=dict)
    communication_style: str = ""

    def is_empty(self) -> bool:
        return not (
            self.preferences
            or self.hobbies
            or self.likes
            or self.dislikes
            or self.goals
            or self.routines
            or self.habits
            or self.rhythms
            or self.communication_style
        )

    def to_json(self) -> dict[str, object]:
        return {
            "preferences": dict(self.preferences),
            "hobbies": list(self.hobbies),
            "likes": list(self.likes),
            "dislikes": list(self.dislikes),
            "goals": [
                {
                    "goal_id": g.goal_id,
                    "summary": g.summary,
                    "horizon": g.horizon,
                    "status": g.status,
                }
                for g in self.goals
            ],
            "routines": [
                {"routine_id": r.routine_id, "name": r.name, "schedule": r.schedule}
                for r in self.routines
            ],
            "habits": [
                {"habit_id": h.habit_id, "summary": h.summary, "cadence": h.cadence}
                for h in self.habits
            ],
            "rhythms": dict(self.rhythms),
            "communication_style": self.communication_style,
        }

    def merged_with(self, observation_kind: str, payload: Mapping[str, Any]) -> "L3PatternShape":
        """Return a new shape with ``payload`` merged into the named bucket.

        Used by the L3 writer to apply a single observation. Unknown
        bucket names are ignored (caller already validated).
        """
        if observation_kind == "preferences":
            new_prefs = dict(self.preferences)
            new_prefs.update({str(k): str(v) for k, v in payload.items()})
            return replace(self, preferences=new_prefs)
        if observation_kind == "hobbies":
            return replace(self, hobbies=_coerce_str_tuple(payload.get("items")))
        if observation_kind == "likes":
            return replace(self, likes=_coerce_str_tuple(payload.get("items")))
        if observation_kind == "dislikes":
            return replace(self, dislikes=_coerce_str_tuple(payload.get("items")))
        if observation_kind == "goals":
            return replace(self, goals=_coerce_goals(payload.get("items")))
        if observation_kind == "routines":
            return replace(self, routines=_coerce_routines(payload.get("items")))
        if observation_kind == "habits":
            return replace(self, habits=_coerce_habits(payload.get("items")))
        if observation_kind == "rhythms":
            new_rhythms = dict(self.rhythms)
            new_rhythms.update({str(k): str(v) for k, v in payload.items()})
            return replace(self, rhythms=new_rhythms)
        if observation_kind == "communication_style":
            return replace(self, communication_style=str(payload.get("value", "")))
        return self


# ----------------------------------------------------------------------
# Coercion / migration helpers
# ----------------------------------------------------------------------
def coerce_l3(value: Any) -> L3PatternShape:
    """Coerce any of (None, dict, L3PatternShape) → ``L3PatternShape``.

    Used during snapshot reads so legacy ``dict[str, object]`` rows
    written before M7.E1.I2 still load correctly. Unknown keys are
    silently dropped.
    """
    if value is None:
        return L3PatternShape()
    if isinstance(value, L3PatternShape):
        return value
    if not isinstance(value, Mapping):
        return L3PatternShape()
    return L3PatternShape(
        preferences={str(k): str(v) for k, v in (value.get("preferences") or {}).items()},
        hobbies=_coerce_str_tuple(value.get("hobbies")),
        likes=_coerce_str_tuple(value.get("likes")),
        dislikes=_coerce_str_tuple(value.get("dislikes")),
        goals=_coerce_goals(value.get("goals")),
        routines=_coerce_routines(value.get("routines")),
        habits=_coerce_habits(value.get("habits")),
        rhythms={str(k): str(v) for k, v in (value.get("rhythms") or {}).items()},
        communication_style=str(value.get("communication_style") or ""),
    )


def _coerce_str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(v) for v in value if v is not None)


def _coerce_goals(value: Any) -> tuple[Goal, ...]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return ()
    out: list[Goal] = []
    for item in value:
        if isinstance(item, Goal):
            out.append(item)
        elif isinstance(item, Mapping):
            out.append(
                Goal(
                    goal_id=str(item.get("goal_id") or ""),
                    summary=str(item.get("summary") or ""),
                    horizon=str(item.get("horizon") or "this_week"),
                    status=str(item.get("status") or "active"),
                )
            )
    return tuple(g for g in out if g.goal_id)


def _coerce_routines(value: Any) -> tuple[RoutineRef, ...]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return ()
    out: list[RoutineRef] = []
    for item in value:
        if isinstance(item, RoutineRef):
            out.append(item)
        elif isinstance(item, Mapping):
            out.append(
                RoutineRef(
                    routine_id=str(item.get("routine_id") or ""),
                    name=str(item.get("name") or ""),
                    schedule=str(item.get("schedule") or ""),
                )
            )
    return tuple(r for r in out if r.routine_id)


def _coerce_habits(value: Any) -> tuple[Habit, ...]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return ()
    out: list[Habit] = []
    for item in value:
        if isinstance(item, Habit):
            out.append(item)
        elif isinstance(item, Mapping):
            out.append(
                Habit(
                    habit_id=str(item.get("habit_id") or ""),
                    summary=str(item.get("summary") or ""),
                    cadence=str(item.get("cadence") or "daily"),
                )
            )
    return tuple(h for h in out if h.habit_id)
