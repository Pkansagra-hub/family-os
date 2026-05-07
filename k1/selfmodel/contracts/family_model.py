"""Family-model snapshot dataclasses (the ``F`` set, projected for actor).

Holds only ``ProjectedSelf`` of related members (NEVER raw ``S``);
Empty-Set Invariant E5 enforced at the projection step (M1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "FamilyMemberRef",
    "RelationshipEdge",
    "RoutineRef",
    "FamilySelfModelSnapshot",
]


@dataclass(frozen=True)
class FamilyMemberRef:
    """Stable reference to a household member."""

    member_id: str
    display_name: str = ""
    role: str = ""  # "guardian" | "child" | "adult" | "guest" | ...
    age_band: str = ""  # "infant" | "child" | "teen" | "adult" | ...


@dataclass(frozen=True)
class RelationshipEdge:
    """One directed edge in the family graph adjacent to the actor."""

    from_member: str
    to_member: str
    kind: str  # "parent_of" | "sibling_of" | "guardian_of" | ...
    weight: float = 1.0


@dataclass(frozen=True)
class RoutineRef:
    """Reference to a known household routine."""

    routine_id: str
    name: str = ""
    schedule: str = ""  # human-readable; full schema in M3+


@dataclass(frozen=True)
class FamilySelfModelSnapshot:
    """Family view projected for a single actor at ``(T, D)``.

    ``members`` contains only members the actor is permitted to see per
    ``C.visibility_rules``; ``relations`` contains only edges adjacent
    to the actor.
    """

    family_space_id: str
    revision: str = ""
    members: tuple[FamilyMemberRef, ...] = field(default_factory=tuple)
    relations: tuple[RelationshipEdge, ...] = field(default_factory=tuple)
    routines: tuple[RoutineRef, ...] = field(default_factory=tuple)
    composed_at_ms: int = 0
