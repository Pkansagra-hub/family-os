"""``FamilyModelService`` — projects ``F`` for a single actor.

Issue M1.E1.I2.

Returns a ``FamilySelfModelSnapshot`` containing:

- ``members``: only those the actor is permitted to see per
  ``C.visibility_rules`` (Empty-Set Invariant E2 enforced upstream by
  the composer; this service surfaces the *raw* family snapshot so the
  composer can apply per-attribute filtering).
- ``relations``: only edges adjacent to the actor (``from_member ==
  actor_id`` or ``to_member == actor_id``).
- ``routines``: full set (routine references are family-public by
  construction; per-attribute filtering of routine details is the
  composer's job).

This service does NOT touch the constitution. The "filter by
visibility_rules" step is split between this service (subset of edges)
and the composer (per-attribute redaction of ``ProjectedSelf``). The
single source of truth for per-attribute filtering is
``situation_composer`` so it cannot drift.
"""

from __future__ import annotations

import logging
import time

from k1.selfmodel.contracts.family_model import (
    FamilyMemberRef,
    FamilySelfModelSnapshot,
    RelationshipEdge,
    RoutineRef,
)
from k1.selfmodel.ports.projection_store import (
    IProjectionStorePort,
    ProjectionFreshness,
)

__all__ = [
    "FamilyModelService",
    "FAMILY_MODEL_WRITER_ID",
    "FamilyViewResult",
]


logger = logging.getLogger(__name__)


FAMILY_MODEL_WRITER_ID = "selfmodel:family_model_service"


class FamilyViewResult:
    """Composite result: family snapshot + freshness for the family row."""

    __slots__ = ("snapshot", "freshness")

    def __init__(
        self,
        snapshot: FamilySelfModelSnapshot,
        *,
        freshness: ProjectionFreshness,
    ) -> None:
        self.snapshot = snapshot
        self.freshness = freshness

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"FamilyViewResult(family_space_id={self.snapshot.family_space_id!r}, "
            f"members={len(self.snapshot.members)}, "
            f"relations={len(self.snapshot.relations)}, "
            f"freshness={self.freshness.value})"
        )


class FamilyModelService:
    """Project the family snapshot for a viewing actor.

    Stateless beyond the injected store. Safe to share across sessions.
    """

    def __init__(self, store: IProjectionStorePort) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def get_view(self, actor_id: str, family_space_id: str) -> FamilyViewResult:
        """Return the family view projected for ``actor_id``.

        If the family space has no row in the projection store, returns
        an empty snapshot (the protocol contract for
        ``ISelfFamilyPort.get_family_view`` is "always returns a
        snapshot, never None"). Single-actor households therefore
        return an empty ``relations`` tuple.
        """
        if not actor_id:
            raise ValueError("actor_id must be non-empty")
        if not family_space_id:
            raise ValueError("family_space_id must be non-empty")

        raw, result = self._store.read_family(family_space_id)
        if raw is None:
            empty = FamilySelfModelSnapshot(
                family_space_id=family_space_id,
                composed_at_ms=_now_ms(),
            )
            logger.debug(
                "family_model.get_view: no family row for %s, returning empty snapshot",
                family_space_id,
            )
            return FamilyViewResult(empty, freshness=result.freshness)

        adjacent_edges = _filter_adjacent_edges(raw.relations, actor_id)
        # The members tuple is left intact (visibility filtering of which
        # members are even named is per-attribute and lives in the
        # composer). This service only enforces the structural rule that
        # F.relations holds adjacency-only edges.
        projected = FamilySelfModelSnapshot(
            family_space_id=raw.family_space_id,
            revision=raw.revision,
            members=tuple(raw.members),
            relations=adjacent_edges,
            routines=tuple(raw.routines),
            composed_at_ms=_now_ms(),
        )
        return FamilyViewResult(projected, freshness=result.freshness)

    def get_member(self, family_space_id: str, member_id: str) -> FamilyMemberRef | None:
        """Helper for the composer: look up a single member ref."""
        raw, _ = self._store.read_family(family_space_id)
        if raw is None:
            return None
        for m in raw.members:
            if m.member_id == member_id:
                return m
        return None

    def freshness(self, family_space_id: str) -> ProjectionFreshness:
        return self._store.freshness(f"family:{family_space_id}")

    # ------------------------------------------------------------------
    # Write (M7.E2.I3) — typed family routine writer.
    # ------------------------------------------------------------------
    def update_routines(
        self,
        family_space_id: str,
        routines: tuple[RoutineRef, ...],
    ) -> None:
        """Replace the family's routines with ``routines``.

        Members and relationships are preserved. Used by onboarding and
        scheduler-side updates so the household block in the capsule
        reflects current shared routines.
        """
        if not family_space_id:
            raise ValueError("family_space_id must be non-empty")
        from dataclasses import replace as _replace

        raw, _result = self._store.read_family(family_space_id)
        if raw is None:
            raw = FamilySelfModelSnapshot(
                family_space_id=family_space_id,
                composed_at_ms=_now_ms(),
            )
        updated = _replace(
            raw,
            routines=tuple(routines),
            composed_at_ms=_now_ms(),
        )
        write_res = self._store.write_family(updated, writer_id=FAMILY_MODEL_WRITER_ID)
        if not write_res.accepted:  # pragma: no cover - allowlist misconfig
            raise RuntimeError(
                f"projection store rejected family routines write: {write_res.reason!r}"
            )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _filter_adjacent_edges(
    edges: tuple[RelationshipEdge, ...] | tuple[()],
    actor_id: str,
) -> tuple[RelationshipEdge, ...]:
    """Edges where the actor is the source OR the target."""
    return tuple(e for e in edges if e.from_member == actor_id or e.to_member == actor_id)


def _adjacent_member_ids(
    edges: tuple[RelationshipEdge, ...] | tuple[()],
    actor_id: str,
) -> tuple[str, ...]:
    """Return the set of *other* member ids reachable in one hop."""
    seen: set[str] = set()
    for e in edges:
        if e.from_member == actor_id and e.to_member != actor_id:
            seen.add(e.to_member)
        elif e.to_member == actor_id and e.from_member != actor_id:
            seen.add(e.from_member)
    return tuple(sorted(seen))


# Re-exported for the composer (kept module-private otherwise).
__all__ += ["_adjacent_member_ids"]


def _now_ms() -> int:
    return int(time.time() * 1000)


# Suppress unused-import warning when projecting routines through.
_ = RoutineRef
