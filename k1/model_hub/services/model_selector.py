"""Model selection with multi-dimension scoring [F42].

Selects optimal (provider, model) pair from eligible providers using
5-dimension weighted scoring with priority-specific weights, plus
fallback chain construction and placement cascade.

Import graph (Layer 3 -- imports Layer 0 + Layer 1 + Layer 2)
--------------------------------------------------------------
k1.model_hub.services.model_selector
  -> k1.model_hub.types              (Layer 0)
  -> k1.model_hub.manifest           (Layer 0)
  -> k1.model_hub.services.capability_router  (Layer 3, sibling)
  -> k1.model_hub.services.provider_registry  (Layer 3, sibling)
  -> stdlib only

NEVER import from any adapter or runtime module.

References
----------
- model_hub.mmd: ModelSelector service
- Invariant MH-06: Fallback is CAPABILITY-AWARE (top 3)
- Invariant MH-07: Cost from manifest model cost table
- Invariant MH-13: Placement cascade (Local -> Remote -> Cached -> Template)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from k1.model_hub.manifest import ModelSpec
from k1.model_hub.services.capability_router import EligibleProvider
from k1.model_hub.types import (
    CapabilityType,
    HealthStatus,
    HubRequest,
    ModelPreference,
    ModelTier,
    PlacementType,
    Priority,
)

# ===========================================================================
# ModelChoice -- output of selection
# ===========================================================================


@dataclass(frozen=True)
class ModelChoice:
    """Selected (provider, model) pair with fallback chain.

    Invariant MH-06: fallback_chain has up to 3 choices.
    """

    provider_id: str
    model_id: str
    fallback_chain: List["FallbackEntry"] = field(default_factory=list)
    score: float = 0.0

    def __post_init__(self) -> None:
        if not self.provider_id:
            raise ValueError("ModelChoice.provider_id must be non-empty")


@dataclass(frozen=True)
class FallbackEntry:
    """An entry in the fallback chain."""

    provider_id: str
    model_id: str
    score: float = 0.0


# ===========================================================================
# Scoring weights per priority tier
# ===========================================================================

# Weights: (cost, latency, preference, placement, health)
_PRIORITY_WEIGHTS: Dict[Priority, Dict[str, float]] = {
    Priority.REALTIME: {
        "cost": 0.1,
        "latency": 0.5,
        "preference": 0.2,
        "placement": 0.0,
        "health": 0.2,
    },
    Priority.INTERACTIVE: {
        "cost": 0.2,
        "latency": 0.3,
        "preference": 0.3,
        "placement": 0.0,
        "health": 0.2,
    },
    Priority.BACKGROUND: {
        "cost": 0.5,
        "latency": 0.1,
        "preference": 0.1,
        "placement": 0.0,
        "health": 0.3,
    },
}

# Tier-to-latency score mapping (faster = higher)
_TIER_LATENCY_SCORES: Dict[ModelTier, float] = {
    ModelTier.FAST: 1.0,
    ModelTier.STANDARD: 0.6,
    ModelTier.PREMIUM: 0.3,
}

# Placement type scores (local > remote, MH-13)
_PLACEMENT_SCORES: Dict[PlacementType, float] = {
    PlacementType.LOCAL_GPU: 1.0,
    PlacementType.LOCAL_CPU: 0.7,
    PlacementType.REMOTE: 0.4,
}

# Health status scores
_HEALTH_SCORES: Dict[HealthStatus, float] = {
    HealthStatus.HEALTHY: 1.0,
    HealthStatus.DEGRADED: 0.5,
    HealthStatus.UNHEALTHY: 0.0,
}

# Maximum fallback chain depth (MH-06)
_MAX_FALLBACK_DEPTH = 3


# ===========================================================================
# ModelSelector
# ===========================================================================


class ModelSelector:
    """Multi-dimension weighted scoring to select optimal (provider, model).

    5 scoring dimensions:
      1. cost_score:      Cheaper = higher (from manifest cost table, MH-07).
      2. latency_score:   Faster tier = higher.
      3. preference_score: User/consumer preference match.
      4. placement_score: Local > remote (MH-13).
      5. health_score:    HEALTHY > DEGRADED.

    Weighted sum per priority tier:
      REALTIME:    latency 0.5, cost 0.1, pref 0.2, health 0.2
      INTERACTIVE: latency 0.3, cost 0.2, pref 0.3, health 0.2
      BACKGROUND:  cost 0.5, latency 0.1, pref 0.1, health 0.3

    Builds fallback chain of top 3 choices (MH-06).

    Cost optimization rules:
      - BACKGROUND: always cheapest model.
      - Budget > 80%: cheapest for non-REALTIME.
      - Budget > 95%: cheapest for ALL.

    Placement cascade (MH-13):
      (1) Local GPU -> (2) Local CPU -> (3) Remote -> (4) Cached -> (5) Template.
    """

    def __init__(
        self,
        *,
        budget_usage_pct: float = 0.0,
    ) -> None:
        """Initialize ModelSelector.

        Args:
            budget_usage_pct: Current daily budget usage percentage (0-100).
                              Updated externally by BudgetEnforcer.
        """
        self._budget_usage_pct = budget_usage_pct

    @property
    def budget_usage_pct(self) -> float:
        return self._budget_usage_pct

    @budget_usage_pct.setter
    def budget_usage_pct(self, value: float) -> None:
        self._budget_usage_pct = value

    def select(
        self,
        eligible_providers: List[EligibleProvider],
        request: HubRequest,
        *,
        preference: Optional[ModelPreference] = None,
    ) -> Optional[ModelChoice]:
        """Select optimal (provider, model) pair with fallback chain.

        Args:
            eligible_providers: Pre-filtered providers from CapabilityRouter.
            request: Original HubRequest for priority, capability context.
            preference: Optional model preference from SessionState persona.

        Returns:
            ModelChoice with primary selection + fallback chain.
            None if no eligible providers.
        """
        if not eligible_providers:
            return None

        priority = request.constraints.priority
        capability = request.capability

        # Score all (provider, model) candidates
        candidates = self._score_all_candidates(
            eligible_providers, priority, capability, preference
        )

        if not candidates:
            return None

        # Apply cost optimization rules
        candidates = self._apply_cost_rules(candidates, priority, capability)

        # Sort by score descending
        candidates.sort(key=lambda c: c[2], reverse=True)

        # Build primary choice + fallback chain (MH-06: top 3)
        primary = candidates[0]
        fallbacks = [
            FallbackEntry(
                provider_id=c[0],
                model_id=c[1],
                score=c[2],
            )
            for c in candidates[1:_MAX_FALLBACK_DEPTH]
        ]

        return ModelChoice(
            provider_id=primary[0],
            model_id=primary[1],
            fallback_chain=fallbacks,
            score=primary[2],
        )

    # -- Scoring ---------------------------------------------------------------

    def _score_all_candidates(
        self,
        eligible_providers: List[EligibleProvider],
        priority: Priority,
        capability: CapabilityType,
        preference: Optional[ModelPreference],
    ) -> List[tuple]:
        """Score all (provider, model) pairs.

        Returns list of (provider_id, model_id, score, total_cost) tuples.
        """
        weights = _PRIORITY_WEIGHTS[priority]
        candidates: List[tuple] = []

        # Collect max cost for normalization
        all_costs: List[float] = []
        for ep in eligible_providers:
            for model in ep.eligible_models:
                all_costs.append(model.cost_per_1m_input + model.cost_per_1m_output)
        max_cost = max(all_costs) if all_costs else 1.0

        for ep in eligible_providers:
            for model in ep.eligible_models:
                score = self._score_candidate(ep, model, weights, preference, max_cost)
                total_cost = model.cost_per_1m_input + model.cost_per_1m_output
                candidates.append((ep.provider_info.provider_id, model.id, score, total_cost))

            # If no specific models, score provider with empty model
            if not ep.eligible_models:
                score = self._score_provider_only(ep, weights, preference)
                candidates.append((ep.provider_info.provider_id, "", score, 0.0))

        return candidates

    def _score_candidate(
        self,
        ep: EligibleProvider,
        model: ModelSpec,
        weights: Dict[str, float],
        preference: Optional[ModelPreference],
        max_cost: float,
    ) -> float:
        """Score a single (provider, model) candidate across 5 dimensions."""
        # 1. Cost score (cheaper = higher, normalized 0-1)
        total_cost = model.cost_per_1m_input + model.cost_per_1m_output
        cost_score = 1.0 - (total_cost / max_cost) if max_cost > 0 else 1.0

        # 2. Latency score (faster tier = higher)
        latency_score = _TIER_LATENCY_SCORES.get(model.tier, 0.5)

        # 3. Preference score
        preference_score = self._compute_preference_score(
            ep.provider_info.provider_id, model.id, preference
        )

        # 4. Placement score (local > remote, MH-13)
        placement_score = _PLACEMENT_SCORES.get(ep.provider_info.placement_type, 0.4)

        # 5. Health score
        health_score = _HEALTH_SCORES.get(ep.health_status, 0.5)

        return (
            weights["cost"] * cost_score
            + weights["latency"] * latency_score
            + weights["preference"] * preference_score
            + weights["placement"] * placement_score
            + weights["health"] * health_score
        )

    def _score_provider_only(
        self,
        ep: EligibleProvider,
        weights: Dict[str, float],
        preference: Optional[ModelPreference],
    ) -> float:
        """Score a provider with no specific model information."""
        cost_score = 0.5  # Unknown cost, neutral
        latency_score = 0.5  # Unknown tier, neutral
        preference_score = self._compute_preference_score(
            ep.provider_info.provider_id, "", preference
        )
        placement_score = _PLACEMENT_SCORES.get(ep.provider_info.placement_type, 0.4)
        health_score = _HEALTH_SCORES.get(ep.health_status, 0.5)

        return (
            weights["cost"] * cost_score
            + weights["latency"] * latency_score
            + weights["preference"] * preference_score
            + weights["placement"] * placement_score
            + weights["health"] * health_score
        )

    @staticmethod
    def _compute_preference_score(
        provider_id: str,
        model_id: str,
        preference: Optional[ModelPreference],
    ) -> float:
        """Compute preference match score (0-1)."""
        if preference is None:
            return 0.5  # Neutral when no preference

        score = 0.5
        if preference.preferred_provider and preference.preferred_provider == provider_id:
            score += 0.3
        if preference.preferred_model and preference.preferred_model == model_id:
            score += 0.2
        if provider_id in (preference.avoid_providers or []):
            score = 0.0  # Hard avoid

        return min(score, 1.0)

    # -- Cost optimization rules -----------------------------------------------

    def _apply_cost_rules(
        self,
        candidates: List[tuple],
        priority: Priority,
        capability: CapabilityType,
    ) -> List[tuple]:
        """Apply cost optimization rules based on budget and priority.

        Rules:
          - BACKGROUND: always cheapest model.
          - Budget > 80%: cheapest for non-REALTIME.
          - Budget > 95%: cheapest for ALL.
          - BATCH capability: 50% cost discount in scoring.
        """
        if not candidates:
            return candidates

        force_cheapest = False

        # Budget > 95%: cheapest for ALL
        if self._budget_usage_pct > 95.0:
            force_cheapest = True
        # Budget > 80%: cheapest for non-REALTIME
        elif self._budget_usage_pct > 80.0 and priority != Priority.REALTIME:
            force_cheapest = True
        # BACKGROUND: always cheapest
        elif priority == Priority.BACKGROUND:
            force_cheapest = True

        if force_cheapest:
            # Find cheapest candidate by total_cost (index 3)
            cheapest = min(candidates, key=lambda c: c[3])
            best_score = max(c[2] for c in candidates)
            # Boost cheapest to top; leave rest in original order
            return [(cheapest[0], cheapest[1], best_score + 0.1, cheapest[3])] + [
                c for c in candidates if c is not cheapest
            ]

        return candidates


__all__ = [
    "FallbackEntry",
    "ModelChoice",
    "ModelSelector",
]
