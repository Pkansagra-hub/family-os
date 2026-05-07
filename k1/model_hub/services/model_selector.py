"""Model selection (capability + preference + placement + health) [F42].

Selects optimal (provider, model) pair from eligible providers using
4 dimensions: preference, placement, health, plus an explicit fallback
chain. Cost/latency/budget scoring removed (family-os: provider cost
tables are not enforced; capability routing is enough).

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
- Invariant MH-13: Placement cascade (Local -> Remote -> Cached -> Template)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from k1.model_hub.manifest import ModelSpec
from k1.model_hub.services.capability_router import EligibleProvider
from k1.model_hub.types import (
    HealthStatus,
    HubRequest,
    ModelPreference,
    PlacementType,
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
# Scoring weights (family-os: simple, capability-first)
# ===========================================================================

# Preference + placement + health, weights sum to 1.0
_WEIGHTS: Dict[str, float] = {
    "preference": 0.5,
    "placement": 0.2,
    "health": 0.3,
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
    """Capability-first selection: preference + placement + health.

    3 scoring dimensions:
      1. preference_score: User/consumer preferred provider/model match.
      2. placement_score:  Local > remote (MH-13).
      3. health_score:     HEALTHY > DEGRADED > UNHEALTHY.

    Builds fallback chain of top 3 choices (MH-06).

    Cost-based ranking and budget pressure removed -- family-os runs
    on provider-supplied cost (recorded passively elsewhere) and does
    not need to outsmart the provider's own pricing.
    """

    def __init__(self) -> None:
        """Initialize ModelSelector. No state."""

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
            request: Original HubRequest (currently unused beyond context).
            preference: Optional model preference from SessionState persona.

        Returns:
            ModelChoice with primary selection + fallback chain.
            None if no eligible providers.
        """
        if not eligible_providers:
            return None

        # If caller did not pass an explicit preference, fall back to the
        # constraints-bound preference from the request envelope.
        if preference is None:
            preference = request.constraints.model_preference

        # Score all (provider, model) candidates
        candidates = self._score_all_candidates(eligible_providers, preference)

        if not candidates:
            return None

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
        preference: Optional[ModelPreference],
    ) -> List[tuple]:
        """Score all (provider, model) pairs.

        Returns list of (provider_id, model_id, score) tuples.
        """
        candidates: List[tuple] = []

        for ep in eligible_providers:
            for model in ep.eligible_models:
                score = self._score_candidate(ep, model, preference)
                candidates.append((ep.provider_info.provider_id, model.id, score))

            # If no specific models, score provider with empty model
            if not ep.eligible_models:
                score = self._score_provider_only(ep, preference)
                candidates.append((ep.provider_info.provider_id, "", score))

        return candidates

    def _score_candidate(
        self,
        ep: EligibleProvider,
        model: ModelSpec,
        preference: Optional[ModelPreference],
    ) -> float:
        """Score a single (provider, model) candidate across 3 dimensions."""
        preference_score = self._compute_preference_score(
            ep.provider_info.provider_id, model.id, preference
        )
        placement_score = _PLACEMENT_SCORES.get(ep.provider_info.placement_type, 0.4)
        health_score = _HEALTH_SCORES.get(ep.health_status, 0.5)

        return (
            _WEIGHTS["preference"] * preference_score
            + _WEIGHTS["placement"] * placement_score
            + _WEIGHTS["health"] * health_score
        )

    def _score_provider_only(
        self,
        ep: EligibleProvider,
        preference: Optional[ModelPreference],
    ) -> float:
        """Score a provider with no specific model information."""
        preference_score = self._compute_preference_score(
            ep.provider_info.provider_id, "", preference
        )
        placement_score = _PLACEMENT_SCORES.get(ep.provider_info.placement_type, 0.4)
        health_score = _HEALTH_SCORES.get(ep.health_status, 0.5)

        return (
            _WEIGHTS["preference"] * preference_score
            + _WEIGHTS["placement"] * placement_score
            + _WEIGHTS["health"] * health_score
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


__all__ = [
    "FallbackEntry",
    "ModelChoice",
    "ModelSelector",
]
