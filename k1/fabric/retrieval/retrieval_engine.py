"""
k1.fabric.retrieval.retrieval_engine -- Full retrieval pipeline (4.1.5).

Chains the 4-step pipeline: Embed -> HardFilter -> SoftRanker -> TopKSelector.

Public API:
  - ``discover_capabilities(domain, intent, safety_band, session_context, top_k)``
    -> RetrievalResult
  - ``find_relevant_prompts(intent, domain, safety_band, top_k)``
    -> RetrievalResult

Performance targets: <20 ms for 10K caps, <50 ms for 100K caps.

Thread safety: The engine itself is stateless across calls.  Internal components
(EmbeddingIndex, HardFilter, SoftRanker, TopKSelector) are all read-only or
internally thread-safe.

References:
  - fabric_discussion.md Section 8 (Retrieval Pipeline)
  - Epic 4.1.5 spec in fabric-implementation-plan.md
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Protocol, Sequence

import numpy as np

# ---------------------------------------------------------------------------
# Protocols -- declared locally to avoid circular imports
# ---------------------------------------------------------------------------


class IEmbeddingPort(Protocol):
    """Port for computing text embeddings."""

    def embed(self, text: str) -> np.ndarray:
        """Return a 1-D float32 embedding vector for *text*."""
        ...  # pragma: no cover


class IRegistryPort(Protocol):
    """
    Minimal registry read surface needed by the retrieval engine.

    Production: CapabilityRegistry (2.2.1).
    Test: any object with matching methods.
    """

    def list_all(self) -> Sequence[Any]:
        """Return all registered contracts."""
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalEngineConfig:
    """
    Configuration for the RetrievalEngine.

    Attributes:
        default_top_k: Default K when caller doesn't specify.
        max_top_k: Hard ceiling on K.
        embedding_model: Model name reported in RetrievalResult metadata.
    """

    default_top_k: int = 10
    max_top_k: int = 25
    embedding_model: str = "ultrabert-v4.0.0"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RetrievalEngineError(Exception):
    """Base exception for retrieval engine operations."""


class EmbeddingUnavailableError(RetrievalEngineError):
    """Raised when the embedding port is not available."""


# ---------------------------------------------------------------------------
# RetrievalEngine
# ---------------------------------------------------------------------------


class RetrievalEngine:
    """
    Full 4-step semantic retrieval pipeline.

    Pipeline::

        1. Embed query text -> query_vector
        2. HardFilter -> eliminate unsafe / offline / unsatisfiable
        3. SoftRanker -> composite scoring
        4. TopKSelector -> truncate to top K

    Constructor Args:
        embedding_index: EmbeddingIndex (4.1.1) for vector search.
        hard_filter: HardFilter (4.1.2) for elimination.
        soft_ranker: SoftRanker (4.1.3) for scoring.
        top_k_selector: TopKSelector (4.1.4) for truncation.
        embedding_port: IEmbeddingPort for text -> vector.
        registry_port: IRegistryPort for listing contracts.
        config: Optional RetrievalEngineConfig.
    """

    __slots__ = (
        "_index",
        "_hard_filter",
        "_soft_ranker",
        "_top_k_selector",
        "_embedding_port",
        "_registry_port",
        "_config",
    )

    def __init__(
        self,
        embedding_index: Any,
        hard_filter: Any,
        soft_ranker: Any,
        top_k_selector: Any,
        embedding_port: IEmbeddingPort,
        registry_port: IRegistryPort,
        config: Optional[RetrievalEngineConfig] = None,
    ) -> None:
        self._index = embedding_index
        self._hard_filter = hard_filter
        self._soft_ranker = soft_ranker
        self._top_k_selector = top_k_selector
        self._embedding_port = embedding_port
        self._registry_port = registry_port
        self._config = config or RetrievalEngineConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = "GREEN",
        session_context: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
    ) -> Any:
        """
        Discover capabilities matching *intent* within *domain*.

        Full pipeline: embed -> hard filter -> soft rank -> top-K.

        Args:
            domain: Domain tag filter (optional).
            intent: Natural-language description of desired capability.
            safety_band: Caller's safety band (default GREEN).
            session_context: Dict of available session keys + param names.
            top_k: Number of results (default from config).

        Returns:
            RetrievalResult (from k1.fabric.types).
        """
        return self._run_pipeline(
            query_text=intent,
            query_domains=frozenset(domain) if domain else frozenset(),
            safety_band=safety_band,
            session_context=session_context or {},
            top_k=top_k,
            filter_prompt_type=False,
        )

    def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = "GREEN",
        top_k: Optional[int] = None,
    ) -> Any:
        """
        Find prompt-type capabilities matching *intent*.

        Same pipeline as discover_capabilities but filters to prompt-type
        contracts only (provider_type starts with 'prompt' or name starts
        with 'prompt.').

        Args:
            intent: Natural-language description.
            domain: Domain tag filter.
            safety_band: Caller's safety band.
            top_k: Number of results.

        Returns:
            RetrievalResult.
        """
        return self._run_pipeline(
            query_text=intent,
            query_domains=frozenset(domain) if domain else frozenset(),
            safety_band=safety_band,
            session_context={},
            top_k=top_k,
            filter_prompt_type=True,
        )

    @property
    def config(self) -> RetrievalEngineConfig:
        return self._config

    def __repr__(self) -> str:
        return (
            f"RetrievalEngine(index_size={self._index.size}, "
            f"model={self._config.embedding_model!r})"
        )

    # ------------------------------------------------------------------
    # Pipeline implementation
    # ------------------------------------------------------------------

    def _run_pipeline(
        self,
        query_text: str,
        query_domains: FrozenSet[str],
        safety_band: str,
        session_context: Dict[str, Any],
        top_k: Optional[int],
        filter_prompt_type: bool,
    ) -> Any:
        """Execute the 4-step retrieval pipeline."""
        # Avoid importing types at module-level to prevent circular imports.
        # These are lightweight stdlib-based frozen dataclasses.
        from k1.fabric.retrieval.hard_filter import FilterCandidate
        from k1.fabric.retrieval.soft_ranker import RankerCandidate
        from k1.fabric.types import RetrievalResult, ScoredCapability

        start = time.monotonic()

        effective_k = top_k if top_k is not None else self._config.default_top_k
        effective_k = max(1, min(effective_k, self._config.max_top_k))

        # -- Step 0: Gather contracts -----------------------------------
        all_contracts = list(self._registry_port.list_all())

        if filter_prompt_type:
            all_contracts = [
                c
                for c in all_contracts
                if (getattr(c, "provider_type", "") or "").lower().startswith("prompt")
                or (getattr(c, "name", "") or "").lower().startswith("prompt.")
            ]

        if not all_contracts:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return RetrievalResult(
                capabilities=[],
                total_matched=0,
                query_latency_ms=elapsed_ms,
                query_intent=query_text,
                index_size=self._index.size,
                embedding_model=self._config.embedding_model,
            )

        # -- Step 1: Embed query ----------------------------------------
        query_vector = self._embedding_port.embed(query_text)
        query_vector = np.asarray(query_vector, dtype=np.float32).ravel()

        # -- Step 2: Hard filter ----------------------------------------
        session_keys = frozenset(session_context.keys()) if session_context else frozenset()
        # Build param names from contracts that have required_inputs
        param_names = frozenset(session_context.get("_param_names", []))

        filter_candidates = []
        contract_lookup: Dict[str, Any] = {}
        for c in all_contracts:
            name = getattr(c, "name", "")
            if not name:
                continue
            contract_lookup[name] = c
            req_inputs = frozenset(
                getattr(inp, "name", inp) if not isinstance(inp, str) else inp
                for inp in getattr(c, "required_inputs", [])
            )
            filter_candidates.append(
                FilterCandidate(
                    contract_name=name,
                    safety_band_min=getattr(c, "safety_band_min", "GREEN"),
                    availability=getattr(c, "availability", "ONLINE"),
                    required_input_names=req_inputs,
                    contract=c,
                )
            )

        survivors = self._hard_filter.filter_passed(
            filter_candidates,
            user_band=safety_band,
            available_param_names=param_names,
            session_keys=session_keys,
        )

        total_matched = len(survivors)

        if not survivors:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return RetrievalResult(
                capabilities=[],
                total_matched=0,
                query_latency_ms=elapsed_ms,
                query_intent=query_text,
                index_size=self._index.size,
                embedding_model=self._config.embedding_model,
            )

        # -- Step 3: Soft rank ------------------------------------------
        ranker_candidates = []
        for s in survivors:
            contract = s.contract
            name = s.contract_name

            # Get capability vector from the index
            cap_vector = None
            if self._index.contains(name):
                # Need to get the stored vector -- access internal _vectors
                cap_vector = getattr(self._index, "_vectors", {}).get(name)

            ranker_candidates.append(
                RankerCandidate(
                    contract_name=name,
                    capability_vector=cap_vector,
                    domains=frozenset(getattr(contract, "domain", [])),
                    success_rate_30d=getattr(contract, "success_rate_30d", -1.0),
                    cost_per_call=getattr(contract, "cost_per_call", 0.0),
                    avg_latency_ms=getattr(contract, "avg_latency_ms", 0),
                    availability=s.availability,
                    contract=contract,
                )
            )

        ranked = self._soft_ranker.rank(
            ranker_candidates,
            query_vector,
            query_domains,
        )

        # -- Step 4: Top-K select ---------------------------------------
        selected = self._top_k_selector.select(ranked, k=effective_k)

        # Convert to ScoredCapability for the final result
        capabilities = []
        for sel in selected:
            capabilities.append(
                ScoredCapability(
                    contract=sel.contract,
                    score=sel.score,
                )
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)

        return RetrievalResult(
            capabilities=capabilities,
            total_matched=total_matched,
            query_latency_ms=elapsed_ms,
            query_intent=query_text,
            index_size=self._index.size,
            embedding_model=self._config.embedding_model,
        )
