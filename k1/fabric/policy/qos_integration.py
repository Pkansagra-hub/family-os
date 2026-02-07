"""
k1.fabric.policy.qos_integration -- QoSIntegration soft score (3.2.4).

Budget-aware and latency-aware provider selection.  This is a **soft
score** -- it never rejects, only adjusts the composite policy score
to prefer cheaper or faster providers when resources are tight.

Rules (from fabric_discussion.md Section 10 Dimension 4):
  - Tight budget (< 20% remaining):
      Heavily prefer lower cost_per_call (weight 0.8).
  - Tight latency (< 30% remaining):
      Heavily prefer lower avg_latency_ms (weight 0.8).
  - Ample budget and latency:
      Balanced formula (weight 0.3 each).

Score range: 0.0 to 0.2.

Design:
  - Reads budget/latency remaining from ``CapabilityRequest.params``
    (keys: ``budget_remaining_pct``, ``latency_remaining_pct``).
  - Per-provider cost and latency passed explicitly by PolicyEngine.
  - No port dependency (stateless, no SessionState reads).
  - Thread-safe (no mutable internal state).

References:
  - fabric_discussion.md Section 10 (Dimension 4: QoS Integration)
  - Epic 3.2.4 in fabric-implementation-plan.md

Exports:
  QoSIntegration -- Soft-score QoS evaluator
  QoSScore       -- Frozen result dataclass
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from k1.fabric.types import CapabilityRequest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Score result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QoSScore:
    """
    Output of QoSIntegration evaluation.

    Attributes:
        score: Additive soft score (0.0 to 0.2).
        reason: Human-readable explanation.
    """

    score: float = 0.0
    reason: str = "neutral"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Budget thresholds
_TIGHT_BUDGET_THRESHOLD = 0.20  # < 20% remaining = tight
_TIGHT_LATENCY_THRESHOLD = 0.30  # < 30% remaining = tight

# Weights when resources are tight
_TIGHT_WEIGHT = 0.80
# Weights when resources are ample
_AMPLE_WEIGHT = 0.30

# Maximum score this dimension can contribute
_MAX_QOS_SCORE = 0.20


# ---------------------------------------------------------------------------
# QoSIntegration
# ---------------------------------------------------------------------------


class QoSIntegration:
    """
    Soft-score policy dimension for budget/latency-aware selection (3.2.4).

    Computes an additive score (0.0-0.2) that adjusts provider ranking
    based on resource constraints.  When budget or latency is tight, the
    score more aggressively prefers cheaper or faster providers.

    Unlike AffectiveRouting and CognitiveLoadRouting, QoS scoring is
    **per-provider** because different providers have different costs and
    latencies.  The PolicyEngine (3.2.5) calls ``score()`` once per
    candidate with that provider's cost/latency metadata.

    Budget and latency remaining percentages are read from
    ``request.params["budget_remaining_pct"]`` and
    ``request.params["latency_remaining_pct"]``.

    Usage::

        qos = QoSIntegration()
        s = qos.score(request, cost_per_call=0.5, avg_latency_ms=2000)
        # s.score in [0.0 .. 0.2]
    """

    __slots__ = ()

    # ======================================================================
    # Public API
    # ======================================================================

    def score(
        self,
        request: CapabilityRequest,
        *,
        cost_per_call: Optional[float] = None,
        avg_latency_ms: Optional[int] = None,
    ) -> QoSScore:
        """
        Compute QoS-aware score for a given request-provider pair.

        Budget and latency remaining are read from ``request.params``:
          - ``budget_remaining_pct``: float in [0.0, 1.0] (default 1.0)
          - ``latency_remaining_pct``: float in [0.0, 1.0] (default 1.0)

        Provider cost and latency are passed explicitly because they
        vary per provider and come from ProviderConfig or contract
        metadata.

        When cost and latency are both None, returns neutral (0.0).

        Args:
            request: The capability request (params may carry budget info).
            cost_per_call: Provider's cost per invocation (lower is better).
                If None, cost dimension is skipped.
            avg_latency_ms: Provider's average latency in milliseconds
                (lower is better).  If None, latency dimension is skipped.

        Returns:
            QoSScore with score (0.0-0.2) and human-readable reason.
        """
        if cost_per_call is None and avg_latency_ms is None:
            return QoSScore(score=0.0, reason="no_provider_qos_metadata")

        budget_pct = self._read_budget_pct(request)
        latency_pct = self._read_latency_pct(request)

        cost_weight = self._compute_weight(budget_pct, _TIGHT_BUDGET_THRESHOLD)
        latency_weight = self._compute_weight(latency_pct, _TIGHT_LATENCY_THRESHOLD)

        cost_score = 0.0
        latency_score = 0.0
        reasons = []

        if cost_per_call is not None:
            # Normalize: lower cost -> higher score.  Clamp to [0, 1].
            # Use 1/(1+cost) as a simple monotone-decreasing normalizer.
            norm_cost = 1.0 / (1.0 + max(0.0, cost_per_call))
            cost_score = norm_cost * cost_weight
            reasons.append(f"cost={cost_per_call:.4f},norm={norm_cost:.3f},w={cost_weight:.2f}")

        if avg_latency_ms is not None:
            # Normalize: lower latency -> higher score.
            # Use 1/(1 + latency/1000) to normalize ms to a [0,1) range.
            norm_latency = 1.0 / (1.0 + max(0, avg_latency_ms) / 1000.0)
            latency_score = norm_latency * latency_weight
            reasons.append(
                f"latency={avg_latency_ms}ms,norm={norm_latency:.3f},w={latency_weight:.2f}"
            )

        raw = cost_score + latency_score
        # Scale to [0.0, _MAX_QOS_SCORE] range
        final = min(raw * _MAX_QOS_SCORE, _MAX_QOS_SCORE)
        final = round(final, 4)

        reason = "; ".join(reasons) if reasons else "neutral"
        if budget_pct < _TIGHT_BUDGET_THRESHOLD:
            reason = f"tight_budget({budget_pct:.2f}); {reason}"
        if latency_pct < _TIGHT_LATENCY_THRESHOLD:
            reason = f"tight_latency({latency_pct:.2f}); {reason}"

        logger.debug(
            "QoS score for %s: %.4f (budget=%.2f, latency=%.2f)",
            request.capability_name,
            final,
            budget_pct,
            latency_pct,
        )
        return QoSScore(score=final, reason=reason)

    # ======================================================================
    # Internal helpers
    # ======================================================================

    @staticmethod
    def _read_budget_pct(request: CapabilityRequest) -> float:
        """Extract budget_remaining_pct from request.params (default 1.0)."""
        raw = request.params.get("budget_remaining_pct", 1.0)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return 1.0
        return max(0.0, min(1.0, val))

    @staticmethod
    def _read_latency_pct(request: CapabilityRequest) -> float:
        """Extract latency_remaining_pct from request.params (default 1.0)."""
        raw = request.params.get("latency_remaining_pct", 1.0)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return 1.0
        return max(0.0, min(1.0, val))

    @staticmethod
    def _compute_weight(remaining_pct: float, threshold: float) -> float:
        """
        Compute the weight for a resource dimension.

        When remaining percentage is below threshold -> tight (weight 0.8).
        Otherwise -> ample (weight 0.3).
        """
        if remaining_pct < threshold:
            return _TIGHT_WEIGHT
        return _AMPLE_WEIGHT
