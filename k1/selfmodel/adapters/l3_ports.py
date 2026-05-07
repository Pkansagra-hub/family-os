"""Thin adapters wrapping ``SelfModelService`` as L3 ports (M10.E1.I1).

Each adapter exposes exactly one bucket of the pattern shape. They
all share the same backing service instance -- the split exists for
typing/review hygiene, not for functional separation.

The reader-side adapters call ``service.get_pattern_shape(actor_id)``
and project the bucket they care about. This is O(1) shape-coerce per
call; persistence-level reads are batched inside the service.
"""

from __future__ import annotations

from typing import Any

from k1.selfmodel.contracts.pattern import Goal, Habit, L3PatternShape
from k1.selfmodel.ports.preferences import (
    ICommunicationStyleReader,
    ICommunicationStyleWriter,
    IGoalReader,
    IGoalWriter,
    IHabitReader,
    IHabitWriter,
    IHobbyReader,
    IHobbyWriter,
    IPatternShapeReader,
    IPreferenceReader,
    IPreferenceWriter,
    IRoutineReader,
    IRoutineWriter,
)
from k1.selfmodel.service.self_model import SelfModelService

__all__ = [
    "L3PortBundle",
    "L3PreferenceAdapter",
    "L3HobbyAdapter",
    "L3GoalAdapter",
    "L3RoutineAdapter",
    "L3HabitAdapter",
    "L3CommunicationStyleAdapter",
    "L3PatternShapeReaderAdapter",
    "build_l3_ports",
]


class _BaseL3Adapter:
    __slots__ = ("_service",)

    def __init__(self, service: SelfModelService) -> None:
        if service is None:
            raise ValueError("service is required")
        self._service = service

    def _shape(self, actor_id: str) -> L3PatternShape:
        return self._service.get_pattern_shape(actor_id)


class L3PreferenceAdapter(_BaseL3Adapter, IPreferenceReader, IPreferenceWriter):
    def read_preferences(self, actor_id: str) -> dict[str, str]:
        return dict(self._shape(actor_id).preferences)

    def write_preferences(self, actor_id: str, preferences: dict[str, str]) -> None:
        self._service.write_preferences(actor_id, preferences)


class L3HobbyAdapter(_BaseL3Adapter, IHobbyReader, IHobbyWriter):
    def read_hobbies(self, actor_id: str) -> tuple[str, ...]:
        return tuple(self._shape(actor_id).hobbies)

    def write_hobbies(self, actor_id: str, hobbies: tuple[str, ...]) -> None:
        self._service.write_hobbies(actor_id, hobbies)

    def write_likes(self, actor_id: str, likes: tuple[str, ...]) -> None:
        self._service.write_likes(actor_id, likes)

    def write_dislikes(self, actor_id: str, dislikes: tuple[str, ...]) -> None:
        self._service.write_dislikes(actor_id, dislikes)


class L3GoalAdapter(_BaseL3Adapter, IGoalReader, IGoalWriter):
    def read_goals(self, actor_id: str) -> tuple[Goal, ...]:
        return tuple(self._shape(actor_id).goals)

    def write_goals(self, actor_id: str, goals: tuple[Goal, ...]) -> None:
        self._service.write_goals(actor_id, goals)


class L3RoutineAdapter(_BaseL3Adapter, IRoutineReader, IRoutineWriter):
    def read_routines(self, actor_id: str) -> tuple[object, ...]:
        return tuple(self._shape(actor_id).routines)

    def write_routines(self, actor_id: str, routines: tuple[object, ...]) -> None:
        self._service.write_routines(actor_id, routines)


class L3HabitAdapter(_BaseL3Adapter, IHabitReader, IHabitWriter):
    def read_habits(self, actor_id: str) -> tuple[Habit, ...]:
        return tuple(self._shape(actor_id).habits)

    def write_habits(self, actor_id: str, habits: tuple[Habit, ...]) -> None:
        self._service.write_habits(actor_id, habits)


class L3CommunicationStyleAdapter(
    _BaseL3Adapter, ICommunicationStyleReader, ICommunicationStyleWriter
):
    def read_communication_style(self, actor_id: str) -> str:
        return self._shape(actor_id).communication_style or ""

    def set_communication_style(self, actor_id: str, style: str) -> None:
        self._service.set_communication_style(actor_id, style)


class L3PatternShapeReaderAdapter(_BaseL3Adapter, IPatternShapeReader):
    def get_pattern_shape(self, actor_id: str) -> L3PatternShape:
        return self._shape(actor_id)


class L3PortBundle:
    """Pre-bound bundle of all L3 ports backed by a single service.

    Convenience for callers (e.g. the kernel wiring, the onboarding
    script) that need every port at once. Individual adapters can
    still be constructed standalone when only one bucket is needed.
    """

    __slots__ = (
        "preferences",
        "hobbies",
        "goals",
        "routines",
        "habits",
        "communication_style",
        "shape",
    )

    def __init__(self, service: SelfModelService) -> None:
        self.preferences = L3PreferenceAdapter(service)
        self.hobbies = L3HobbyAdapter(service)
        self.goals = L3GoalAdapter(service)
        self.routines = L3RoutineAdapter(service)
        self.habits = L3HabitAdapter(service)
        self.communication_style = L3CommunicationStyleAdapter(service)
        self.shape = L3PatternShapeReaderAdapter(service)


def build_l3_ports(service: SelfModelService) -> L3PortBundle:
    """Factory mirror of :class:`L3PortBundle.__init__` for parity with
    other ``build_*`` helpers in the wiring graph."""
    return L3PortBundle(service)


# ---------------------------------------------------------------------
# Public re-export for "give me anything pattern-shaped" callers.
# ---------------------------------------------------------------------
def adapt_service(service: SelfModelService) -> Any:  # pragma: no cover - convenience
    return L3PortBundle(service)
