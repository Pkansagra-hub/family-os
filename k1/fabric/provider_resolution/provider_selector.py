"""
k1.fabric.provider_resolution.provider_selector -- Provider Selector (3.1.3).

Given candidate providers and their policy scores, selects the
highest-scoring provider. Deterministic tie-breaking per FAB-10:
  1. Higher policy score
  2. Lower avg_latency_ms
  3. Alphabetical provider_id

Design:
  - Receives List[ScoredCandidate] from PolicyEngine evaluation
  - Each candidate has: ProviderConfig + PolicyResult + contract
  - Security hard-gate failures are already filtered (allowed=False removed)
  - Returns ResolvedProvider with winner's config + contract + policy

References:
  - fabric_discussion.md Section 9 (Resolution Pipeline step 4)
  - fabric_discussion.md Section 10 (Composite Provider Score)
  - FAB-10: Provider selection is deterministic given same inputs + registry state
  - Epic 3.1.3 in fabric-implementation-plan.md

Exports:
  ProviderSelector -- Deterministic provider selection
  ProviderSelectorError -- Base exception
  AllProvidersRejectedError -- All candidates failed security gate
  ScoredCandidate -- Intermediate scored-candidate dataclass
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Union

from k1.fabric.types import (
    AgentContract,
    CapabilityContract,
    PolicyResult,
    PromptContract,
    ProviderConfig,
    ResolvedProvider,
    WorkflowContract,
)

logger = logging.getLogger(__name__)

# Type alias
ContractUnion = Union[CapabilityContract, AgentContract, PromptContract, WorkflowContract]


# ---------------------------------------------------------------------------
# Scored candidate (intermediate type)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoredCandidate:
    """
    A provider candidate with its policy evaluation result.

    Produced by PolicyEngine (3.2.5), consumed by ProviderSelector.
    If allowed=False, the candidate is filtered before selection.

    Fields:
        provider_config: The provider's configuration.
        contract: The capability contract being fulfilled.
        policy_result: Policy evaluation result for this candidate.
    """

    provider_config: ProviderConfig = field(default_factory=ProviderConfig)
    contract: Optional[ContractUnion] = None
    policy_result: PolicyResult = field(default_factory=PolicyResult)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProviderSelectorError(Exception):
    """Base exception for provider selection operations."""


class AllProvidersRejectedError(ProviderSelectorError):
    """Raised when all candidate providers failed security gate."""

    def __init__(self, capability_name: str, reasons: Optional[List[str]] = None):
        self.capability_name = capability_name
        self.reasons = reasons or []
        super().__init__(
            f"All providers rejected for capability '{capability_name}': "
            f"{'; '.join(self.reasons) if self.reasons else 'security gate failed'}"
        )


class NoCandidatesError(ProviderSelectorError):
    """Raised when no candidates are provided for selection."""

    def __init__(self, capability_name: str = ""):
        self.capability_name = capability_name
        super().__init__(
            f"No candidates provided for selection"
            f"{' (' + capability_name + ')' if capability_name else ''}"
        )


# ---------------------------------------------------------------------------
# 3.1.3 -- ProviderSelector
# ---------------------------------------------------------------------------


class ProviderSelector:
    """
    Deterministic provider selection from scored candidates.

    Given a list of ScoredCandidate objects (each with policy score),
    selects the best provider. Deterministic tie-breaking per FAB-10:
      1. Highest policy score
      2. Lowest avg_latency_ms (from contract metadata)
      3. Alphabetical provider_id (final deterministic tiebreaker)

    Thread Safety:
        Stateless -- safe for concurrent calls.

    References:
        - fabric_discussion.md Section 9 (step 4)
        - FAB-10 (deterministic selection)
        - Epic 3.1.3
    """

    def select(
        self,
        candidates: List[ScoredCandidate],
        *,
        capability_name: str = "",
    ) -> ResolvedProvider:
        """
        Select the best provider from scored candidates.

        Steps:
          1. Filter out candidates with allowed=False (security rejections)
          2. Sort by (score DESC, avg_latency_ms ASC, provider_id ASC)
          3. Return the top candidate as ResolvedProvider

        Args:
            candidates: Scored candidates from policy evaluation.
            capability_name: For error messages.

        Returns:
            ResolvedProvider with the winning provider.

        Raises:
            NoCandidatesError: Empty candidates list.
            AllProvidersRejectedError: All candidates failed security gate.
        """
        if not candidates:
            raise NoCandidatesError(capability_name)

        # Step 1: Filter allowed candidates
        allowed = [c for c in candidates if c.policy_result.allowed]
        if not allowed:
            rejection_reasons = []
            for c in candidates:
                for r in c.policy_result.reasons:
                    if r not in rejection_reasons:
                        rejection_reasons.append(r)
            raise AllProvidersRejectedError(capability_name, rejection_reasons)

        # Step 2: Deterministic sort (FAB-10)
        # Sort key: (-score, +avg_latency_ms, +provider_id)
        winner = self._select_best(allowed)

        # Step 3: Build ResolvedProvider
        return ResolvedProvider(
            provider_config=winner.provider_config,
            contract=winner.contract,
            policy_result=winner.policy_result,
        )

    def select_top_n(
        self,
        candidates: List[ScoredCandidate],
        n: int = 1,
        *,
        capability_name: str = "",
    ) -> List[ResolvedProvider]:
        """
        Select top N providers, deterministically ordered.

        Useful when fallback providers are needed (e.g., circuit breaker opens).

        Args:
            candidates: Scored candidates from policy evaluation.
            n: Number of top providers to return.
            capability_name: For error messages.

        Returns:
            List of ResolvedProviders, ordered best-first.

        Raises:
            NoCandidatesError: Empty candidates list.
            AllProvidersRejectedError: All candidates failed security gate.
        """
        if not candidates:
            raise NoCandidatesError(capability_name)

        allowed = [c for c in candidates if c.policy_result.allowed]
        if not allowed:
            rejection_reasons = []
            for c in candidates:
                for r in c.policy_result.reasons:
                    if r not in rejection_reasons:
                        rejection_reasons.append(r)
            raise AllProvidersRejectedError(capability_name, rejection_reasons)

        ranked = self._rank_all(allowed)
        return [
            ResolvedProvider(
                provider_config=c.provider_config,
                contract=c.contract,
                policy_result=c.policy_result,
            )
            for c in ranked[:n]
        ]

    # ======================================================================
    # Internal: deterministic ranking
    # ======================================================================

    @staticmethod
    def _sort_key(candidate: ScoredCandidate) -> tuple:
        """
        Build a sort key for deterministic ordering (FAB-10).

        Order:
          1. Higher score first (negate for ascending sort)
          2. Lower avg_latency_ms first
          3. Alphabetical provider_id (final tiebreaker)
        """
        score = candidate.policy_result.score
        latency = _get_avg_latency(candidate)
        pid = candidate.provider_config.provider_id
        return (-score, latency, pid)

    @classmethod
    def _select_best(cls, candidates: List[ScoredCandidate]) -> ScoredCandidate:
        """Select the single best candidate using sort key."""
        return min(candidates, key=cls._sort_key)

    @classmethod
    def _rank_all(cls, candidates: List[ScoredCandidate]) -> List[ScoredCandidate]:
        """Rank all candidates using sort key, best first."""
        return sorted(candidates, key=cls._sort_key)


# ===========================================================================
# Module-level helpers
# ===========================================================================


def _get_avg_latency(candidate: ScoredCandidate) -> int:
    """Extract avg_latency_ms from the contract, defaulting to 0."""
    if candidate.contract is not None:
        return getattr(candidate.contract, "avg_latency_ms", 0)
    return 0
