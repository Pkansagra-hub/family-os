"""Self-model snapshot dataclasses (the ``S`` set).

Five-layer projection per
``docs/whiteboard/whiteboard_k1_user_selfmodel_and_tools.md`` (L1 Core,
L2 Identity, L3 Pattern, L4 Context, L5 State).

Frozen dataclasses; no behavior. Composition logic lives in
``k1.selfmodel.service.self_model`` (M1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "LayerObservation",
    "K1SelfModelSnapshot",
]


@dataclass(frozen=True)
class LayerObservation:
    """A single observation that updates a layer (L3/L4/L5).

    Layer-specific semantics are enforced by the writing service; this
    type is the inert payload shape.
    """

    actor_id: str
    layer: str  # "L3" | "L4" | "L5"
    kind: str
    payload: dict[str, object] = field(default_factory=dict)
    observed_at_ms: int = 0


@dataclass(frozen=True)
class K1SelfModelSnapshot:
    """Composed snapshot of an actor's self model at ``(T, D)``.

    ``L4_context`` and ``L5_state`` are RAM-only and are never persisted
    by the projection store.
    """

    actor_id: str
    revision: str = ""
    L1_core: dict[str, object] = field(default_factory=dict)
    L2_identity: dict[str, object] = field(default_factory=dict)
    L3_pattern: dict[str, object] = field(default_factory=dict)
    L4_context: dict[str, object] = field(default_factory=dict)
    L5_state: dict[str, object] = field(default_factory=dict)
    composed_at_ms: int = 0
