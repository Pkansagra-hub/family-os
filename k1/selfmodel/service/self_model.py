"""``SelfModelService`` — the read surface for ``S(actor)``.

Issue M1.E1.I1.

Owns the composition of ``K1SelfModelSnapshot`` for one actor by:

1. Reading the persisted L1/L2/L3 layers from ``IProjectionStorePort``.
2. Optionally seeding L1/L2 from ``MetaSection.identity`` on first
   touch (so a brand-new actor has a non-empty Core/Identity block from
   the moment a session is created).
3. Maintaining a per-actor RAM-only L4/L5 dict the higher-level
   composer can stitch into ``SituationFrame.transient``. ``L4_context``
   and ``L5_state`` are NEVER persisted; the projection store strips
   them on write as defense-in-depth.

Empty-Set Invariants this service is responsible for:

- **E0 (no L4/L5 persisted):** ``write`` always passes a snapshot with
  empty ``L4_context``/``L5_state`` to the store; the in-RAM table is
  the only place those layers live.
- **E5 partial:** the service NEVER returns a different actor's
  snapshot from a request for ``actor_id`` — it returns ``None`` or
  raises ``UnknownActorError``. The composer is responsible for never
  putting another actor's raw snapshot into a SituationFrame.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from typing import TYPE_CHECKING

from k1.selfmodel.contracts.pattern import Goal, Habit, L3PatternShape, coerce_l3
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot, LayerObservation
from k1.selfmodel.ports.projection_store import (
    IProjectionStorePort,
    ProjectionFreshness,
    StoreReadResult,
)
from k1.selfmodel.service.errors import UnknownActorError

if TYPE_CHECKING:
    from k1.sessionstate.sections.meta import SessionIdentity

__all__ = [
    "SelfModelService",
    "SELF_MODEL_WRITER_ID",
    "SelfModelReadResult",
]


logger = logging.getLogger(__name__)

#: Single, stable writer id used by this service when calling the store.
#: The projection store's ``allowed_writers`` allowlist (when set) MUST
#: include this id.
SELF_MODEL_WRITER_ID = "selfmodel:self_model_service"


class SelfModelReadResult:
    """Composite read result: snapshot + freshness, plus a "first-seen" flag."""

    __slots__ = ("snapshot", "freshness", "first_seen")

    def __init__(
        self,
        snapshot: K1SelfModelSnapshot,
        *,
        freshness: ProjectionFreshness,
        first_seen: bool,
    ) -> None:
        self.snapshot = snapshot
        self.freshness = freshness
        self.first_seen = first_seen

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"SelfModelReadResult(actor_id={self.snapshot.actor_id!r}, "
            f"freshness={self.freshness.value}, first_seen={self.first_seen})"
        )


class SelfModelService:
    """Service-layer reader/writer for the actor-side of the algebra.

    Thread-safe. Designed to be constructed once per kernel and shared
    across all sessions (per actor isolation comes from ``actor_id``).
    """

    def __init__(self, store: IProjectionStorePort) -> None:
        self._store = store
        self._lock = threading.RLock()
        # actor_id -> {"L4": {...}, "L5": {...}}
        self._transient: dict[str, dict[str, dict[str, object]]] = {}

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def get(self, actor_id: str) -> SelfModelReadResult | None:
        """Return the actor's snapshot + freshness or ``None`` if unknown.

        Idempotent. Does NOT mutate the store. The L4/L5 transient
        block is stitched in from the in-RAM table; if no observation
        has been recorded yet, those blocks are empty dicts.
        """
        if not actor_id:
            raise ValueError("actor_id must be non-empty")

        snapshot, result = self._store.read_self(actor_id)
        if snapshot is None:
            logger.debug("self_model.get: unknown actor_id=%s", actor_id)
            return None

        composed = self._stitch_transient(snapshot)
        return SelfModelReadResult(composed, freshness=result.freshness, first_seen=False)

    def get_or_seed_from_identity(
        self,
        actor_id: str,
        identity: SessionIdentity,
    ) -> SelfModelReadResult:
        """Read; if missing, seed L1/L2 from ``MetaSection.identity`` and write.

        The seed pulls only fields that are stable across sessions:
        ``user_id``/``device_id``/``privacy_band``/``is_anonymous``/
        ``is_demo_mode``. Onboarding-supplied fields (name, age_band,
        consent_posture, role_in_family, ...) come from the projection
        store; they cannot be inferred from the session identity alone.

        Raises ``UnknownActorError`` if both the store AND the identity
        are insufficient (no ``user_id``).
        """
        existing = self.get(actor_id)
        if existing is not None:
            return existing

        if not identity or not getattr(identity, "user_id", ""):
            raise UnknownActorError(
                f"actor_id={actor_id!r} not in store and identity has no user_id"
            )

        seeded = self._build_seed_from_identity(actor_id, identity)
        write_res = self._store.write_self(seeded, writer_id=SELF_MODEL_WRITER_ID)
        if not write_res.accepted:
            # Store rejected our writer id (allowlist mismatch). This is
            # a configuration bug, not a runtime condition; surface it.
            raise RuntimeError(
                f"projection store rejected SelfModelService write: {write_res.reason!r}"
            )
        logger.info(
            "self_model.get_or_seed_from_identity: seeded actor_id=%s revision=%s",
            actor_id,
            write_res.revision.revision,
        )
        # Re-read to pick up the freshness & revision the store assigned.
        snap, read = self._store.read_self(actor_id)
        if snap is None:  # pragma: no cover - defensive
            raise RuntimeError("seed write succeeded but read_self returned None")
        composed = self._stitch_transient(snap)
        return SelfModelReadResult(composed, freshness=read.freshness, first_seen=True)

    # ------------------------------------------------------------------
    # Layer observations
    # ------------------------------------------------------------------
    def update_layer(self, layer: str, observation: LayerObservation) -> None:
        """Apply a layer observation.

        - **L3** observations persist to the store (re-reads the
          existing snapshot, merges the payload into ``L3_pattern``,
          re-writes).
        - **L4 / L5** observations stay in RAM only (per actor).
        - Any other layer string is rejected.
        """
        if layer not in ("L3", "L4", "L5"):
            raise ValueError(f"unsupported layer for observation: {layer!r} (expected L3|L4|L5)")
        if observation.layer != layer:
            raise ValueError(f"observation.layer={observation.layer!r} != layer={layer!r}")
        if not observation.actor_id:
            raise ValueError("observation.actor_id must be non-empty")

        if layer == "L3":
            self._apply_l3(observation)
            return

        # L4 / L5 — RAM only.
        with self._lock:
            actor_table = self._transient.setdefault(observation.actor_id, {})
            block = actor_table.setdefault(layer, {})
            block[observation.kind] = dict(observation.payload)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _stitch_transient(self, snapshot: K1SelfModelSnapshot) -> K1SelfModelSnapshot:
        """Replace the (always-empty-from-store) L4/L5 blocks with RAM state."""
        with self._lock:
            actor_table = self._transient.get(snapshot.actor_id, {})
            l4 = dict(actor_table.get("L4", {}))
            l5 = dict(actor_table.get("L5", {}))
        return replace(snapshot, L4_context=l4, L5_state=l5)

    def _apply_l3(self, observation: LayerObservation) -> None:
        with self._lock:
            current, _ = self._store.read_self(observation.actor_id)
            if current is None:
                # L3 observation for an actor we have never seeded — refuse.
                # The session bootstrapper is responsible for calling
                # ``get_or_seed_from_identity`` first.
                raise UnknownActorError(
                    f"cannot record L3 observation for unknown actor {observation.actor_id!r}"
                )
            # Use typed L3PatternShape merge when the observation kind
            # matches one of the typed buckets; otherwise fall back to
            # the legacy "kind → dict" sub-key behaviour for back-compat.
            current_shape = coerce_l3(current.L3_pattern)
            merged_shape = current_shape.merged_with(observation.kind, observation.payload)
            if merged_shape is not current_shape:
                # Typed bucket path: rebuild dict from typed shape, but
                # preserve any legacy/non-typed sibling keys that were
                # already present (e.g., raw_* observation kinds).
                merged = dict(current.L3_pattern)
                merged.update(merged_shape.to_json())
            else:
                merged = dict(current.L3_pattern)
                merged[observation.kind] = dict(observation.payload)
            updated = replace(
                current,
                L3_pattern=merged,
                composed_at_ms=observation.observed_at_ms or _now_ms(),
            )
            res = self._store.write_self(updated, writer_id=SELF_MODEL_WRITER_ID)
            if not res.accepted:  # pragma: no cover - allowlist misconfig
                raise RuntimeError(f"projection store rejected L3 write: {res.reason!r}")

    # ------------------------------------------------------------------
    # Typed L3 writers (M7.E2.I2). Each helper composes a typed payload
    # and delegates to ``_apply_l3``.
    # ------------------------------------------------------------------
    def write_preferences(self, actor_id: str, preferences: dict[str, str]) -> None:
        """Merge ``preferences`` into ``L3_pattern.preferences``."""
        self._record_typed_l3(actor_id, "preferences", dict(preferences))

    def write_hobbies(self, actor_id: str, hobbies: tuple[str, ...]) -> None:
        """Replace ``L3_pattern.hobbies`` with ``hobbies``."""
        self._record_typed_l3(actor_id, "hobbies", {"items": list(hobbies)})

    def write_likes(self, actor_id: str, likes: tuple[str, ...]) -> None:
        self._record_typed_l3(actor_id, "likes", {"items": list(likes)})

    def write_dislikes(self, actor_id: str, dislikes: tuple[str, ...]) -> None:
        self._record_typed_l3(actor_id, "dislikes", {"items": list(dislikes)})

    def write_goals(self, actor_id: str, goals: tuple[Goal, ...]) -> None:
        items = [
            {
                "goal_id": g.goal_id,
                "summary": g.summary,
                "horizon": g.horizon,
                "status": g.status,
            }
            for g in goals
        ]
        self._record_typed_l3(actor_id, "goals", {"items": items})

    def write_routines(self, actor_id: str, routines: tuple[object, ...]) -> None:
        # ``routines`` items may be RoutineRef OR mappings.
        from k1.selfmodel.contracts.family_model import RoutineRef

        items: list[dict[str, str]] = []
        for r in routines:
            if isinstance(r, RoutineRef):
                items.append({"routine_id": r.routine_id, "name": r.name, "schedule": r.schedule})
            elif isinstance(r, dict):
                items.append(
                    {
                        "routine_id": str(r.get("routine_id", "")),
                        "name": str(r.get("name", "")),
                        "schedule": str(r.get("schedule", "")),
                    }
                )
        self._record_typed_l3(actor_id, "routines", {"items": items})

    def write_habits(self, actor_id: str, habits: tuple[Habit, ...]) -> None:
        items = [
            {"habit_id": h.habit_id, "summary": h.summary, "cadence": h.cadence} for h in habits
        ]
        self._record_typed_l3(actor_id, "habits", {"items": items})

    def set_communication_style(self, actor_id: str, style: str) -> None:
        self._record_typed_l3(actor_id, "communication_style", {"value": str(style)})

    def get_pattern_shape(self, actor_id: str) -> L3PatternShape:
        """Return the actor's typed ``L3PatternShape``.

        Reads via :meth:`get` and coerces ``L3_pattern`` (which is still
        a ``dict[str, object]`` on disk for storage compat). Returns an
        empty shape when the actor is unseeded.
        """
        result = self.get(actor_id)
        if result is None:
            return L3PatternShape()
        return coerce_l3(result.snapshot.L3_pattern)

    def _record_typed_l3(self, actor_id: str, kind: str, payload: dict[str, object]) -> None:
        if not actor_id:
            raise ValueError("actor_id must be non-empty")
        observation = LayerObservation(
            actor_id=actor_id,
            layer="L3",
            kind=kind,
            payload=payload,
            observed_at_ms=_now_ms(),
        )
        self._apply_l3(observation)

    @staticmethod
    def _build_seed_from_identity(actor_id: str, identity: SessionIdentity) -> K1SelfModelSnapshot:
        # Only seed fields that are stable across sessions. Onboarding
        # data lives in the projection store, not in MetaSection.
        l1: dict[str, object] = {
            "actor_id": actor_id,
            "device_id": identity.device_id,
            "privacy_band": int(identity.privacy_band),
            "is_anonymous": bool(identity.is_anonymous),
            "is_demo_mode": bool(identity.is_demo_mode),
        }
        return K1SelfModelSnapshot(
            actor_id=actor_id,
            L1_core=l1,
            L2_identity={},
            L3_pattern={},
            # L4/L5 always empty in stored snapshots; the store would
            # strip them anyway.
            L4_context={},
            L5_state={},
            composed_at_ms=_now_ms(),
        )

    # Convenience for the composer
    def freshness(self, actor_id: str) -> ProjectionFreshness:
        """Freshness of the actor's stored projection."""
        return self._store.freshness(f"self:{actor_id}")

    # Public for tests; callers should not depend on it.
    def _peek_store_result(self, actor_id: str) -> StoreReadResult:  # pragma: no cover
        _, res = self._store.read_self(actor_id)
        return res


def _now_ms() -> int:
    return int(time.time() * 1000)
