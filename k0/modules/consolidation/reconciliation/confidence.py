"""ConfidenceModel -- pure-function confidence computation (M9.4).

Computes a [0.0, 1.0] confidence score for each reconciliation decision
using an explicit, testable formula:

    confidence = base + evidence + identity_boost + count_boost

Per-action base confidence and evidence weights are fixed constants
documented in the UNIVERSAL_RECONCILIATION_ENGINE design doc (M9.4.8).
"""

from __future__ import annotations

from k0.pipelines.p03.event_state import ReconciliationAction

# Per-action base confidence
_BASE: dict[ReconciliationAction, float] = {
    ReconciliationAction.REINFORCE: 0.50,
    ReconciliationAction.EXTEND: 0.45,
    ReconciliationAction.EVOLVE: 0.40,
    ReconciliationAction.CREATE: 0.35,
    ReconciliationAction.CONTRADICT: 0.90,
    ReconciliationAction.SKIP: 1.00,
    ReconciliationAction.PRUNE: 1.00,
}

# Evidence weight: how much similarity contributes above the base
_EVIDENCE_WEIGHT: dict[ReconciliationAction, float] = {
    ReconciliationAction.REINFORCE: 0.40,
    ReconciliationAction.EXTEND: 0.35,
    ReconciliationAction.EVOLVE: 0.25,
    ReconciliationAction.CREATE: 0.15,
}


class ConfidenceModel:
    """Pure-function confidence computation.

    All values are clamped to [0.0, 1.0].
    """

    @staticmethod
    def compute(
        action: ReconciliationAction,
        similarity: float,
        compatible_count: int,
        total_candidates: int,
        identity_match: bool,
    ) -> float:
        """Compute confidence for a single decision.

        Args:
            action: The reconciliation action chosen.
            similarity: Best cosine similarity [0.0, 1.0].
            compatible_count: Number of identity-compatible records.
            total_candidates: Total pre-fetched records before filtering.
            identity_match: Whether identity keys matched.

        Returns:
            Confidence score clamped to [0.0, 1.0].
        """
        base = _BASE.get(action, 0.5)
        weight = _EVIDENCE_WEIGHT.get(action, 0.0)

        # Evidence from similarity (Tier 2 actions only)
        evidence = 0.0
        if action == ReconciliationAction.REINFORCE:
            evidence = weight * min(1.0, max(0.0, (similarity - 0.85) / 0.15))
        elif action == ReconciliationAction.EXTEND:
            evidence = weight * min(1.0, max(0.0, (similarity - 0.60) / 0.25))
        elif action == ReconciliationAction.EVOLVE:
            evidence = weight * min(1.0, max(0.0, (similarity - 0.40) / 0.20))
        elif action == ReconciliationAction.CREATE:
            evidence = weight  # flat: no similarity signal

        # Identity boost
        identity_boost = 0.05 if identity_match else 0.0

        # Count boost: more candidates evaluated = more confidence in the winner
        count_boost = 0.0
        if compatible_count >= 5:
            count_boost = 0.05
        elif compatible_count >= 3:
            count_boost = 0.02

        return max(0.0, min(1.0, base + evidence + identity_boost + count_boost))
