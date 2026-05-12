"""Space-graph snapshot dataclasses (the ``F`` set, projected for actor).

Holds only ``ProjectedSelf`` of related members (NEVER raw ``S``);
Empty-Set Invariant E5 enforced at the projection step (M1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "ActorRef",
    "SpaceEdge",
    "RoutineRef",
    "SpaceGraphSnapshot",
]


@dataclass(frozen=True)
class ActorRef:
    """Stable reference to an actor in a space."""

    member_id: str
    display_name: str = ""
    role: str = ""  # "guardian" | "child" | "adult" | "guest" | ...
    age_band: str = ""  # "infant" | "child" | "teen" | "adult" | ...


@dataclass(frozen=True)
class SpaceEdge:
    """One directed edge in the space graph adjacent to the actor."""

    from_member: str
    to_member: str
    kind: str  # "parent_of" | "sibling_of" | "guardian_of" | ...
    weight: float = 1.0


@dataclass(frozen=True)
class RoutineRef:
    """Reference to a known routine in a space."""

    routine_id: str
    name: str = ""
    schedule: str = ""  # human-readable; full schema in M3+


@dataclass(frozen=True)
class SpaceGraphSnapshot:
    """Space graph projected for a single actor at ``(T, D)``.

    ``members`` contains only members the actor is permitted to see per
    ``C.visibility_rules``; ``relations`` contains only edges adjacent
    to the actor.
    """

    space_id: str
    revision: str = ""
    members: tuple[ActorRef, ...] = field(default_factory=tuple)
    relations: tuple[SpaceEdge, ...] = field(default_factory=tuple)
    routines: tuple[RoutineRef, ...] = field(default_factory=tuple)
    composed_at_ms: int = 0


# --- Deprecated aliases (kept for one release; remove in next major) ---
# Existing call sites outside k1/selfmodel/ are zero (verified May 2026), but the
# YAML constitution bodies and external integrations may still reference the old
# names. Removing them is a follow-up task tracked separately.
FamilyMemberRef = ActorRef  # noqa: PYI042
RelationshipEdge = SpaceEdge  # noqa: PYI042
FamilySelfModelSnapshot = SpaceGraphSnapshot  # noqa: PYI042
