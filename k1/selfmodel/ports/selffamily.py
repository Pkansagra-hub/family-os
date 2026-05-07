"""``ISelfFamilyPort`` — read self / family snapshots and apply observations.

Reads return ``ProjectedSelf`` views for non-actor members (NEVER raw
``S``); Empty-Set Invariant E5. Implementations land in M1
(``service/self_model.py`` + ``service/family_model.py``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.selfmodel.contracts.family_model import FamilySelfModelSnapshot
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot, LayerObservation

__all__ = ["ISelfFamilyPort"]


@runtime_checkable
class ISelfFamilyPort(Protocol):
    """Read the actor's self model and the family view projected for them."""

    def get_self(self, actor_id: str, T_ms: int, device_id: str) -> K1SelfModelSnapshot | None:
        """Composed self snapshot at ``(T, D)``; ``None`` if unknown actor."""
        ...

    def get_family_view(self, actor_id: str, T_ms: int, device_id: str) -> FamilySelfModelSnapshot:
        """Family view PROJECTED for ``actor_id``.

        Edges are filtered to those adjacent to the actor; member
        attributes are filtered through ``C.visibility_rules``. Always
        returns a snapshot (possibly empty); never ``None``.
        """
        ...

    def update_layer(self, layer: str, observation: LayerObservation) -> None:
        """Record an observation for L3/L4/L5.

        Persistence vs RAM-only behavior is layer-dependent and enforced
        by the implementing service. L4/L5 are RAM-only.
        """
        ...
