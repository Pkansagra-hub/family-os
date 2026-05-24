"""
k1.fabric.retrieval.soft_ranker -- Composite scoring for ranked retrieval (4.1.3).

Applies the 4-dimension weighted formula to produce a final relevance score
for each capability that survived HardFilter (4.1.2).

Formula::

    Score = (0.4 * semantic_similarity)
          + (0.3 * domain_match)
          + (0.15 * success_rate)
          + (0.15 * cost_latency_score)

Dimensions:
  - **semantic_similarity**: cosine(query_vector, capability_vector), [0, 1]
  - **domain_match**: Jaccard(query_domains, capability.domain), [0, 1]
  - **success_rate**: contract.success_rate_30d (default 0.5 for new caps)
  - **cost_latency_score**: ``1.0 - normalize(cost + latency / 10000)`` [0, 1]

Post-scoring:
  - DEGRADED penalty: ``score *= 0.7``

Thread safety: Stateless; all data passed per call.  Safe for concurrent use.

References:
  - fabric_discussion.md Section 8 (Retrieval Pipeline, step [3])
  - Epic 4.1.3 spec in fabric-implementation-plan.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Constants -- formula weights
# ---------------------------------------------------------------------------

W_SEMANTIC: float = 0.40
"""Weight for semantic similarity dimension."""

W_DOMAIN: float = 0.30
"""Weight for domain match dimension."""

W_SUCCESS: float = 0.15
"""Weight for success rate dimension."""

W_COST_LATENCY: float = 0.15
"""Weight for cost/latency dimension."""

DEFAULT_SUCCESS_RATE: float = 0.50
"""Default success_rate_30d for newly-registered capabilities (no history)."""

DEGRADED_PENALTY: float = 0.70
"""Multiplicative penalty for DEGRADED capabilities."""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RankerCandidate:
    """
    Input to the SoftRanker -- a capability that survived HardFilter.

    Attributes:
        contract_name: Canonical capability name.
        capability_vector: Embedding vector (float32, same dim as query).
        domains: Domain tags from the capability contract.
        success_rate_30d: Rolling 30-day success rate (0.0 - 1.0).
        cost_per_call: Dollar cost per invocation.
        avg_latency_ms: Average latency in milliseconds.
        availability: Current availability (ONLINE / DEGRADED).
        contract: Optional reference to the full contract object (opaque).
    """

    contract_name: str = ""
    capability_vector: Any = None  # np.ndarray, typed Any to avoid import issues
    domains: FrozenSet[str] = field(default_factory=frozenset)
    success_rate_30d: float = -1.0  # sentinel: <0 means 'no data, use default'
    cost_per_call: float = 0.0
    avg_latency_ms: int = 0
    availability: str = "ONLINE"
    contract: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_name": self.contract_name,
            "domains": sorted(self.domains),
            "success_rate_30d": self.success_rate_30d,
            "cost_per_call": self.cost_per_call,
            "avg_latency_ms": self.avg_latency_ms,
            "availability": self.availability,
        }


@dataclass(frozen=True)
class RankedResult:
    """
    Output of the SoftRanker for a single capability.

    Attributes:
        contract_name: Capability name.
        score: Final composite score in [0, 1].
        semantic_similarity: Raw semantic similarity component.
        domain_match: Raw domain match component.
        success_rate: Raw success rate component.
        cost_latency_score: Raw cost/latency component.
        degraded_penalty_applied: True if DEGRADED penalty was applied.
        contract: Opaque reference to the original contract.
    """

    contract_name: str = ""
    score: float = 0.0
    semantic_similarity: float = 0.0
    domain_match: float = 0.0
    success_rate: float = 0.0
    cost_latency_score: float = 0.0
    degraded_penalty_applied: bool = False
    contract: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_name": self.contract_name,
            "score": round(self.score, 6),
            "semantic_similarity": round(self.semantic_similarity, 6),
            "domain_match": round(self.domain_match, 6),
            "success_rate": round(self.success_rate, 6),
            "cost_latency_score": round(self.cost_latency_score, 6),
            "degraded_penalty_applied": self.degraded_penalty_applied,
        }


@dataclass(frozen=True)
class SoftRankerConfig:
    """
    Configuration for the SoftRanker.

    Attributes:
        w_semantic: Weight for semantic similarity.
        w_domain: Weight for domain match.
        w_success: Weight for success rate.
        w_cost_latency: Weight for cost/latency score.
        default_success_rate: Default rate for new capabilities.
        degraded_penalty: Multiplicative penalty for DEGRADED availability.
    """

    w_semantic: float = W_SEMANTIC
    w_domain: float = W_DOMAIN
    w_success: float = W_SUCCESS
    w_cost_latency: float = W_COST_LATENCY
    default_success_rate: float = DEFAULT_SUCCESS_RATE
    degraded_penalty: float = DEGRADED_PENALTY


# ---------------------------------------------------------------------------
# SoftRanker
# ---------------------------------------------------------------------------


class SoftRanker:
    """
    Composite scoring for post-HardFilter capability ranking.

    Stateless: all data passed per call.  Deterministic: same inputs =>
    same output (no randomness or wall-clock dependencies).

    Constructor Args:
        config: Optional SoftRankerConfig.
    """

    __slots__ = ("_config",)

    def __init__(self, config: Optional[SoftRankerConfig] = None) -> None:
        self._config = config or SoftRankerConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rank(
        self,
        candidates: List[RankerCandidate],
        query_vector: Any,
        query_domains: FrozenSet[str] = frozenset(),
        *,
        max_cost: Optional[float] = None,
        max_latency_ms: Optional[int] = None,
    ) -> List[RankedResult]:
        """
        Score every candidate and return ranked results (descending score).

        Args:
            candidates: Capabilities surviving HardFilter.
            query_vector: Embedding vector for the user query (1-D float32).
            query_domains: Domain tags from the query/request.
            max_cost: Maximum cost across candidates (for normalization).
                      If None, computed from candidates.
            max_latency_ms: Maximum latency across candidates (for norm).
                            If None, computed from candidates.

        Returns:
            List of RankedResult sorted by score (descending).
        """
        if not candidates:
            return []

        qvec = np.asarray(query_vector, dtype=np.float32).ravel()

        # Pre-compute normalization ceilings
        if max_cost is None:
            costs = [c.cost_per_call for c in candidates]
            max_cost = max(costs) if costs else 1.0
        if max_latency_ms is None:
            latencies = [c.avg_latency_ms for c in candidates]
            max_latency_ms = max(latencies) if latencies else 1

        results: List[RankedResult] = []
        for c in candidates:
            result = self._score_candidate(
                c,
                qvec,
                query_domains,
                max_cost,
                max_latency_ms,
            )
            results.append(result)

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    @property
    def config(self) -> SoftRankerConfig:
        return self._config

    def __repr__(self) -> str:
        c = self._config
        return (
            f"SoftRanker(w=[{c.w_semantic},{c.w_domain},"
            f"{c.w_success},{c.w_cost_latency}], "
            f"degraded_penalty={c.degraded_penalty})"
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _score_candidate(
        self,
        candidate: RankerCandidate,
        query_vector: np.ndarray,
        query_domains: FrozenSet[str],
        max_cost: float,
        max_latency_ms: int,
    ) -> RankedResult:
        """Score a single candidate against the 4 dimensions."""

        cfg = self._config

        # Dimension 1: Semantic similarity (cosine)
        sem = self._cosine_similarity(query_vector, candidate.capability_vector)

        # Dimension 2: Domain match (Jaccard)
        dom = self._jaccard(query_domains, candidate.domains)

        # Dimension 3: Success rate
        sr = candidate.success_rate_30d
        if sr < 0.0:
            sr = cfg.default_success_rate
        sr = max(0.0, min(1.0, sr))

        # Dimension 4: Cost/latency score
        cl = self._cost_latency_score(
            candidate.cost_per_call,
            candidate.avg_latency_ms,
            max_cost,
            max_latency_ms,
        )

        # Weighted composite
        score = (
            cfg.w_semantic * sem + cfg.w_domain * dom + cfg.w_success * sr + cfg.w_cost_latency * cl
        )

        # DEGRADED penalty
        degraded = candidate.availability == "DEGRADED"
        if degraded:
            score *= cfg.degraded_penalty

        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))

        return RankedResult(
            contract_name=candidate.contract_name,
            score=score,
            semantic_similarity=sem,
            domain_match=dom,
            success_rate=sr,
            cost_latency_score=cl,
            degraded_penalty_applied=degraded,
            contract=candidate.contract,
        )

    # ------------------------------------------------------------------
    # Dimension calculators
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(
        a: np.ndarray,
        b: Any,
    ) -> float:
        """
        Cosine similarity between two vectors, clamped to [0, 1].

        Returns 0.0 if either vector is zero-length or None.
        """
        if b is None:
            return 0.0
        b = np.asarray(b, dtype=np.float32).ravel()
        if a.shape != b.shape:
            return 0.0
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        cos = float(np.dot(a, b) / (norm_a * norm_b))
        return max(0.0, min(1.0, cos))

    @staticmethod
    def _jaccard(
        set_a: FrozenSet[str],
        set_b: FrozenSet[str],
    ) -> float:
        """
        Jaccard similarity: |A & B| / |A | B|.

        Returns 0.0 if both sets are empty.
        """
        if not set_a and not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        if union == 0:
            return 0.0
        return intersection / union

    @staticmethod
    def _cost_latency_score(
        cost: float,
        latency_ms: int,
        max_cost: float,
        max_latency_ms: int,
    ) -> float:
        """
        Compute ``1.0 - normalize(cost + latency / 10000)``.

        Lower cost and latency = higher score (closer to 1.0).

        Normalization uses the maximum values across the candidate set
        to keep the score in [0, 1].
        """
        # Normalize cost
        norm_cost = cost / max_cost if max_cost > 0.0 else 0.0

        # Convert latency to comparable scale and normalize
        lat_val = latency_ms / 10000.0
        max_lat_val = max_latency_ms / 10000.0
        norm_lat = lat_val / max_lat_val if max_lat_val > 0.0 else 0.0

        # Combined normalized value (average of the two dimensions)
        combined = (norm_cost + norm_lat) / 2.0

        score = 1.0 - combined
        return max(0.0, min(1.0, score))
