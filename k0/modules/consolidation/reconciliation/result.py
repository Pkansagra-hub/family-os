"""ReconciliationResult -- immutable decision output (M9.4).

Frozen dataclass with 14 fields carrying everything downstream
consumers need: action, match, confidence, reason trace, and hooks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from k0.pipelines.p03.event_state import ReconciliationAction


@dataclass(frozen=True)
class ReconciliationResult:
    """Immutable decision output from ReconciliationFramework.decide()."""

    # -- Decision --
    action: ReconciliationAction
    tier: int  # 1 = K1 signal override, 2 = identity+similarity cascade

    # -- Match --
    match_id: str | None
    match_layer: str
    similarity: float  # [0.0, 1.0]
    identity_match: bool

    # -- Confidence --
    confidence: float  # [0.0, 1.0]

    # -- Trace --
    reason: str
    candidate_id: str
    layer: str
    cycle_id: str

    # -- Hooks --
    hooks_required: list[str] = field(default_factory=list)

    # -- Contradiction detail (Tier 1 only) --
    contradiction_details: dict[str, Any] | None = None

    # -- Timing --
    decision_time_ms: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "similarity", max(0.0, min(1.0, self.similarity)))
        object.__setattr__(self, "confidence", max(0.0, min(1.0, self.confidence)))

    @property
    def has_match(self) -> bool:
        return self.match_id is not None

    @property
    def is_k1_override(self) -> bool:
        return self.tier == 1
