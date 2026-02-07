"""
k1.fabric.retrieval.top_k_selector -- Top-K selection from scored set (4.1.4).

Stateless selector that truncates a ranked list of capabilities to the top K
results, attaching the full contract, score, and provider_type to each entry.

Constraints:
  - Default K = 10, max K = 25.
  - Returns ``list[ScoredCapability]`` (from k1.fabric.types).
  - Input must already be sorted by descending score (SoftRanker output).

Thread safety: Stateless; safe for concurrent use.

References:
  - fabric_discussion.md Section 8 (Retrieval Pipeline, step [4])
  - Epic 4.1.4 spec in fabric-implementation-plan.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_K: int = 10
"""Default number of results to return."""

MAX_K: int = 25
"""Hard ceiling on K (prevents excessive result sets)."""

MIN_K: int = 1
"""Minimum K (always return at least 1 if any results exist)."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TopKSelectorConfig:
    """
    Configuration for the TopKSelector.

    Attributes:
        default_k: Default number of results if caller does not specify.
        max_k: Hard ceiling (clamped).
    """

    default_k: int = DEFAULT_K
    max_k: int = MAX_K


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectedCapability:
    """
    A capability selected for the final result set.

    Carries the full contract (opaque), score, and provider_type so the
    caller does not need to look them up again.

    Attributes:
        contract_name: Canonical capability name.
        score: Final composite score from SoftRanker.
        provider_type: Provider type string (MCP / WASM / BRIDGE / etc.).
        contract: Full CapabilityContract reference (opaque).
    """

    contract_name: str = ""
    score: float = 0.0
    provider_type: str = ""
    contract: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_name": self.contract_name,
            "score": round(self.score, 6),
            "provider_type": self.provider_type,
        }


# ---------------------------------------------------------------------------
# TopKSelector
# ---------------------------------------------------------------------------


class TopKSelector:
    """
    Select the top K capabilities from a scored and sorted list.

    Pure function wrapper -- stateless.  Validates and clamps K,
    then slices the pre-sorted input.

    Constructor Args:
        config: Optional TopKSelectorConfig.
    """

    __slots__ = ("_config",)

    def __init__(self, config: Optional[TopKSelectorConfig] = None) -> None:
        self._config = config or TopKSelectorConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select(
        self,
        ranked: List[Any],
        k: Optional[int] = None,
        *,
        extract_name: Optional[Any] = None,
        extract_score: Optional[Any] = None,
        extract_provider_type: Optional[Any] = None,
        extract_contract: Optional[Any] = None,
    ) -> List[SelectedCapability]:
        """
        Select top K from a pre-sorted ranked list.

        The input items can be any type.  By default, items are expected to
        have ``.contract_name``, ``.score``, ``.contract`` attributes
        (matching ``RankedResult`` from SoftRanker).  Provide ``extract_*``
        callables to override how fields are read.

        Args:
            ranked: Pre-sorted list (descending score).
            k: Number of results.  If None, uses config default.
                Clamped to [1, max_k].
            extract_name: callable(item) -> str
            extract_score: callable(item) -> float
            extract_provider_type: callable(item) -> str
            extract_contract: callable(item) -> Any

        Returns:
            List of SelectedCapability (length = min(k, len(ranked))).
        """
        if not ranked:
            return []

        effective_k = self._clamp_k(k)
        top = ranked[:effective_k]

        results: List[SelectedCapability] = []
        for item in top:
            name = extract_name(item) if extract_name else getattr(item, "contract_name", "")
            score = extract_score(item) if extract_score else getattr(item, "score", 0.0)
            ptype = (
                extract_provider_type(item)
                if extract_provider_type
                else self._get_provider_type(item)
            )
            contract = (
                extract_contract(item) if extract_contract else getattr(item, "contract", None)
            )

            results.append(
                SelectedCapability(
                    contract_name=name,
                    score=score,
                    provider_type=ptype,
                    contract=contract,
                )
            )
        return results

    @property
    def config(self) -> TopKSelectorConfig:
        return self._config

    def __repr__(self) -> str:
        return f"TopKSelector(default_k={self._config.default_k}, " f"max_k={self._config.max_k})"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _clamp_k(self, k: Optional[int]) -> int:
        """Resolve and clamp K to valid range."""
        if k is None:
            k = self._config.default_k
        return max(MIN_K, min(k, self._config.max_k))

    @staticmethod
    def _get_provider_type(item: Any) -> str:
        """
        Extract provider_type from an item.

        Tries item.contract.provider_type, then item.provider_type, else ''.
        """
        contract = getattr(item, "contract", None)
        if contract is not None:
            pt = getattr(contract, "provider_type", None)
            if pt:
                return str(pt)
        pt = getattr(item, "provider_type", None)
        if pt:
            return str(pt)
        return ""
