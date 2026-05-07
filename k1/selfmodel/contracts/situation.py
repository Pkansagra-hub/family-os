"""SituationFrame dataclasses (the triple intersection ``S ∩ F ∩ C``).

The SituationFrame is the only object that the rest of K1 consumes from
``k1.selfmodel``. Composer logic lives in
``k1.selfmodel.service.situation_composer`` (M1).

M6/M7 additions:
    * ``SelfView``         — typed actor-self view with L3 pattern fields
                             (preferences/hobbies/goals/routines/...).
    * ``SituationFrame.self_view`` — populated by composer alongside
                                     legacy ``projected_self`` dict.
    * ``SituationFrame.conscience`` — composed ``ConscienceDigest``;
                                      replaces ``Capabilities`` in M8/M9.
    * ``Capabilities`` is marked DEPRECATED and will be removed in M9.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from k1.selfmodel.contracts.conscience import ConscienceDigest
from k1.selfmodel.contracts.family_model import RelationshipEdge, RoutineRef
from k1.selfmodel.contracts.pattern import Goal, Habit

__all__ = [
    "ProjectedSelf",
    "SelfView",
    "RelationsSubset",
    "ApplicableRules",
    "Capabilities",
    "Visibility",
    "SituationFrame",
]


@dataclass(frozen=True)
class ProjectedSelf:
    """A redacted view of another actor's self, safe for ``actor`` to see.

    NEVER carries raw ``S`` of the other actor. Built by the composer
    after consulting ``C.visibility_rules`` (Empty-Set Invariant E2 +
    E5).
    """

    member_id: str
    display_name: str = ""
    role: str = ""
    visible_attributes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RelationsSubset:
    """Subset of the family graph adjacent to the actor."""

    edges: tuple[RelationshipEdge, ...] = field(default_factory=tuple)
    projected_others: tuple[ProjectedSelf, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ApplicableRules:
    """Rules from ``C`` that apply to this ``(actor, T, D, situation)``."""

    rule_ids: tuple[str, ...] = field(default_factory=tuple)
    constitution_version: str = ""


@dataclass(frozen=True)
class SelfView:
    """Typed actor-self view (M7).

    The composer populates this from ``S(actor)``'s L1/L2/L3 layers
    after visibility filtering. The capsule renderer surfaces these
    fields directly under ``[self]/[preferences]/[hobbies]/[goals]/
    [routines]/[context]`` blocks so the LLM grounds in **who the
    user is**.

    Defaults are empty so this dataclass is safe even when the actor
    has no L3 content yet.
    """

    actor_id: str = ""
    display_name: str = ""
    role: str = ""
    age_band: str = ""
    language: str = ""
    pronouns: str = ""
    communication_style: str = ""
    preferences: dict[str, str] = field(default_factory=dict)
    hobbies: tuple[str, ...] = ()
    likes: tuple[str, ...] = ()
    dislikes: tuple[str, ...] = ()
    goals: tuple[Goal, ...] = ()
    routines: tuple[RoutineRef, ...] = ()
    habits: tuple[Habit, ...] = ()


@dataclass(frozen=True)
class Capabilities:
    """DEPRECATED (M6) — replaced by ``ConscienceDigest`` in M8/M9.

    Original semantics (M2): authoritative tool/action set the actor
    may invoke right now; E6 was "any tool dispatch outside ``can_do``
    is a DENY". The Part B inversion makes this wrong — see
    ``IMPLEMENTATION_PLAN_SELF_MODEL.md`` Part B §A.

    Kept as a back-compat shim during M6–M8 so existing tests and the
    legacy v0 YAML path continue to function. New code must read
    ``SituationFrame.conscience`` instead. Removed in M9.
    """

    can_do: tuple[str, ...] = field(default_factory=tuple)
    requires_confirmation: tuple[str, ...] = field(default_factory=tuple)
    requires_identity_tier: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Visibility:
    """What the actor is permitted to see in the current frame."""

    can_see_members: tuple[str, ...] = field(default_factory=tuple)
    can_see_attributes: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class SituationFrame:
    """The triple intersection ``S(actor) ∩ F ∩ C`` at ``(T, D)``."""

    actor_id: str
    situation_kind: str  # one of S1..S13 (whiteboard V0 Family Operating Design)
    composed_at_ms: int = 0
    device_id: str = ""
    projected_self: dict[str, object] = field(default_factory=dict)
    self_view: SelfView | None = None  # M7 — typed actor view (preferred by capsule)
    relations: RelationsSubset = field(default_factory=RelationsSubset)
    rules: ApplicableRules = field(default_factory=ApplicableRules)
    capabilities: Capabilities = field(default_factory=Capabilities)  # DEPRECATED M6, removed M9
    conscience: ConscienceDigest | None = None  # M6 — preferred by gate when set
    visibility: Visibility = field(default_factory=Visibility)
    transient: dict[str, object] = field(default_factory=dict)  # L4/L5 RAM-only block
    freshness: dict[str, str] = field(default_factory=dict)  # per-projection state
