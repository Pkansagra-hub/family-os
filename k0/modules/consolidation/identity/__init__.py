"""Identity strategy protocol and re-exports (M9.2).

Defines the ``IdentityStrategy`` protocol that all per-layer identity
implementations must satisfy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from k0.modules.consolidation.types import IdentityResult, ReconciliationCandidate, TruthRecord


@runtime_checkable
class IdentityStrategy(Protocol):
    """Per-layer identity matching logic.

    Determines whether a candidate and an existing truth record
    represent the 'same thing'.  Each truth layer implements this
    differently based on its identity semantics.
    """

    @property
    def layer_name(self) -> str:
        """Which truth layer this strategy serves."""
        ...

    def score_identity(
        self,
        candidate: ReconciliationCandidate,
        existing: TruthRecord,
        cosine_sim: float,
    ) -> IdentityResult:
        """Score how likely *candidate* and *existing* are the same entity."""
        ...

    def match_key(
        self,
        candidate: ReconciliationCandidate,
        existing: TruthRecord,
    ) -> bool | None:
        """Fast key-based identity check (optional).

        Returns ``True`` for a definite key match, ``False`` for a
        definite mismatch, or ``None`` if inconclusive.
        """
        ...
