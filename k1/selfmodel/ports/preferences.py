"""Narrow reader/writer ports for L3 pattern content (M10.E1.I1).

These split :class:`k1.selfmodel.service.self_model.SelfModelService`
into per-bucket protocols so callers can depend on exactly the
capability they need, not on the whole service. They are pure
protocols -- the production wiring binds them all to the same
``SelfModelService`` instance via thin adapters in
:mod:`k1.selfmodel.adapters.l3_ports`.

Why narrow them at all?

* **Testability** -- unit tests can supply a one-method fake instead
  of a full service double.
* **Reviewability** -- a module that only writes routines no longer
  silently gains the ability to write goals, preferences, etc.
* **Onboarding** -- the new ``onboarding_seed`` script (M10.E2)
  takes the writer ports as constructor args, not the service, so
  its blast radius is visible from the type signature.

All ports follow the same shape: a reader that takes ``actor_id`` and
returns the typed bucket, and a writer that takes ``actor_id`` plus
the new value. None of them perform identity or visibility checks --
those live in the service layer behind the adapter.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.selfmodel.contracts.pattern import Goal, Habit, L3PatternShape

__all__ = [
    "IPreferenceReader",
    "IPreferenceWriter",
    "IHobbyReader",
    "IHobbyWriter",
    "IGoalReader",
    "IGoalWriter",
    "IRoutineReader",
    "IRoutineWriter",
    "IHabitReader",
    "IHabitWriter",
    "ICommunicationStyleReader",
    "ICommunicationStyleWriter",
    "IPatternShapeReader",
]


# ---------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------
@runtime_checkable
class IPreferenceReader(Protocol):
    def read_preferences(self, actor_id: str) -> dict[str, str]: ...


@runtime_checkable
class IPreferenceWriter(Protocol):
    def write_preferences(self, actor_id: str, preferences: dict[str, str]) -> None: ...


# ---------------------------------------------------------------------
# Hobbies / likes / dislikes
# ---------------------------------------------------------------------
@runtime_checkable
class IHobbyReader(Protocol):
    def read_hobbies(self, actor_id: str) -> tuple[str, ...]: ...


@runtime_checkable
class IHobbyWriter(Protocol):
    def write_hobbies(self, actor_id: str, hobbies: tuple[str, ...]) -> None: ...
    def write_likes(self, actor_id: str, likes: tuple[str, ...]) -> None: ...
    def write_dislikes(self, actor_id: str, dislikes: tuple[str, ...]) -> None: ...


# ---------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------
@runtime_checkable
class IGoalReader(Protocol):
    def read_goals(self, actor_id: str) -> tuple[Goal, ...]: ...


@runtime_checkable
class IGoalWriter(Protocol):
    def write_goals(self, actor_id: str, goals: tuple[Goal, ...]) -> None: ...


# ---------------------------------------------------------------------
# Routines
# ---------------------------------------------------------------------
@runtime_checkable
class IRoutineReader(Protocol):
    def read_routines(self, actor_id: str) -> tuple[object, ...]: ...


@runtime_checkable
class IRoutineWriter(Protocol):
    def write_routines(self, actor_id: str, routines: tuple[object, ...]) -> None: ...


# ---------------------------------------------------------------------
# Habits
# ---------------------------------------------------------------------
@runtime_checkable
class IHabitReader(Protocol):
    def read_habits(self, actor_id: str) -> tuple[Habit, ...]: ...


@runtime_checkable
class IHabitWriter(Protocol):
    def write_habits(self, actor_id: str, habits: tuple[Habit, ...]) -> None: ...


# ---------------------------------------------------------------------
# Communication style
# ---------------------------------------------------------------------
@runtime_checkable
class ICommunicationStyleReader(Protocol):
    def read_communication_style(self, actor_id: str) -> str: ...


@runtime_checkable
class ICommunicationStyleWriter(Protocol):
    def set_communication_style(self, actor_id: str, style: str) -> None: ...


# ---------------------------------------------------------------------
# Composite reader (read-only view of the whole shape)
# ---------------------------------------------------------------------
@runtime_checkable
class IPatternShapeReader(Protocol):
    def get_pattern_shape(self, actor_id: str) -> L3PatternShape: ...
