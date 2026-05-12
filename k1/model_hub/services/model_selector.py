"""Model selection: tier-based routing with health-gated fallback [F42].

Two routing paths, driven by request Priority:

  REALTIME / INTERACTIVE  → FAST-tier model (chat + tooling)
  BACKGROUND              → PREMIUM-tier model (planning)

Within a tier, UNHEALTHY providers are excluded entirely.
DEGRADED providers are only used as last-resort fallback.
Fallback chain is capped at 3 entries (MH-06).

Import graph (Layer 3 -- imports Layer 0 + Layer 2)
----------------------------------------------------
k1.model_hub.services.model_selector
  -> k1.model_hub.types              (Layer 0)
  -> k1.model_hub.services.capability_router  (Layer 3, sibling)
  -> stdlib only

NEVER import from any adapter or runtime module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from k1.model_hub.services.capability_router import EligibleProvider
from k1.model_hub.types import (
    HealthStatus,
    HubRequest,
    ModelPreference,
    ModelTier,
    PlacementType,
    Priority,
)

# Maximum fallback chain depth (MH-06)
_MAX_FALLBACK_DEPTH = 3

# Map request priority → required model tier
_PRIORITY_TO_TIER: dict[Priority, ModelTier] = {
    Priority.REALTIME: ModelTier.FAST,
    Priority.INTERACTIVE: ModelTier.FAST,
    Priority.BACKGROUND: ModelTier.PREMIUM,
}

# Placement scoring: local inference preferred over remote (MH-13).
_PLACEMENT_SCORES: dict[PlacementType, int] = {
    PlacementType.LOCAL_GPU: 3,
    PlacementType.LOCAL_CPU: 2,
    PlacementType.REMOTE: 1,
}


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
# ModelSelector
# ===========================================================================


class ModelSelector:
    """Tier-based model routing with health-gated fallback.

    Selection rules:
      1. Determine target tier from request priority:
           REALTIME / INTERACTIVE → FAST (chat + tooling)
           BACKGROUND             → PREMIUM (planning)
      2. Build candidate list from eligible providers:
           - Exclude UNHEALTHY providers entirely.
           - HEALTHY providers go first; DEGRADED last-resort only.
      3. Within HEALTHY candidates, tier-matched models listed before
         non-matching models. Same ordering within DEGRADED bucket.
      4. Return primary + up to 3 fallbacks (MH-06).
    """

    def __init__(self) -> None:
        pass

    def select(
        self,
        eligible_providers: List[EligibleProvider],
        request: HubRequest,
        *,
        preference: Optional[ModelPreference] = None,
    ) -> Optional[ModelChoice]:
        """Select primary model and fallback chain for request.

        Args:
            eligible_providers: Pre-filtered providers from CapabilityRouter.
            request: HubRequest — priority used for tier routing.
            preference: Optional ModelPreference — avoid_providers applied.

        Returns:
            ModelChoice with primary + fallback chain, or None.
        """
        if not eligible_providers:
            return None

        avoid: set[str] = set(preference.avoid_providers) if preference else set()
        target_tier = _PRIORITY_TO_TIER.get(request.constraints.priority, ModelTier.FAST)

        # Partition by health: healthy first, degraded last-resort
        healthy: list[tuple[str, str]] = []
        degraded: list[tuple[str, str]] = []

        for ep in eligible_providers:
            if ep.health_status == HealthStatus.UNHEALTHY:
                continue  # hard exclude
            if ep.provider_info.provider_id in avoid:
                continue  # preference-avoided: skip entirely
            bucket = healthy if ep.health_status == HealthStatus.HEALTHY else degraded
            _add_candidates(ep, target_tier, bucket)

        all_candidates = healthy + degraded
        if not all_candidates:
            return None

        primary = all_candidates[0]
        fallbacks = [
            FallbackEntry(provider_id=p, model_id=m, score=0.0)
            for p, m in all_candidates[1 : _MAX_FALLBACK_DEPTH + 1]
        ]
        primary_score = 1.0 if primary in healthy else 0.5
        return ModelChoice(
            provider_id=primary[0],
            model_id=primary[1],
            fallback_chain=fallbacks,
            score=primary_score,
        )


def _add_candidates(
    ep: EligibleProvider,
    target_tier: ModelTier,
    bucket: list[tuple[str, str]],
) -> None:
    """Append (provider_id, model_id) pairs to bucket.

    Tier-matched models go first within the bucket; unmatched after.
    """
    provider_id = ep.provider_info.provider_id
    if not ep.eligible_models:
        bucket.append((provider_id, ""))
        return

    matched = [m for m in ep.eligible_models if m.tier == target_tier]
    unmatched = [m for m in ep.eligible_models if m.tier != target_tier]
    for m in matched + unmatched:
        bucket.append((provider_id, m.id))


__all__ = [
    "FallbackEntry",
    "ModelChoice",
    "ModelSelector",
]
