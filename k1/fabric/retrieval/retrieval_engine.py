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

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Protocol, Sequence

import numpy as np

from k1.fabric.metrics import get_default_metrics
from k1.fabric.retrieval.embedding_index import IEmbeddingPort

logger = logging.getLogger(__name__)

_BROAD_DOMAIN_HINTS = frozenset({"family", "household", "coordination"})


def _is_prompt_contract(contract: Any) -> bool:
    """Return True for prompt/profile contracts that are not directly executable."""
    name = str(getattr(contract, "name", "") or "").lower()
    provider_type = str(getattr(contract, "provider_type", "") or "").lower()
    contract_type = contract.__class__.__name__.lower()
    return (
        name.startswith("prompt.")
        or provider_type.startswith("prompt")
        or contract_type == "promptcontract"
    )


# ---------------------------------------------------------------------------
# Protocols -- declared locally to avoid circular imports
# (IEmbeddingPort is the canonical declaration in embedding_index.py;
#  re-exported here for backward-compatible imports.)
# ---------------------------------------------------------------------------


class IRegistryPort(Protocol):
    """
    Minimal registry read surface needed by the retrieval engine.

    Production: CapabilityRegistry (2.2.1).
    Test: any object with matching methods.
    """

    def list_all(self) -> Sequence[Any]:
        """Return all registered contracts."""
        ...  # pragma: no cover

    def list_by_domain(self, domain: str) -> Sequence[Any]:
        """Return contracts matching the given domain tag (O(1) index lookup)."""
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
            query_type="capabilities",
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
            query_type="prompts",
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
        query_type: str,
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
        # Domain hints are ranking hints. For exact domains, start from the
        # O(1) domain index; if the hint is broad or misses completely, fall
        # back to the full registry so a broad label like household cannot
        # hide concrete task/calendar contracts.
        domain_exact_names: set[str] = set()
        domain_fallback_used = False
        if query_domains:
            seen_names: set[str] = set()
            all_contracts = []
            broad_domain_query = any(str(d).lower() in _BROAD_DOMAIN_HINTS for d in query_domains)
            for d in query_domains:
                if str(d).lower() in _BROAD_DOMAIN_HINTS:
                    continue
                for c in self._registry_port.list_by_domain(d):
                    name = getattr(c, "name", "")
                    if name and name not in seen_names:
                        seen_names.add(name)
                        domain_exact_names.add(name)
                        all_contracts.append(c)
            if broad_domain_query or not all_contracts:
                domain_fallback_used = True
                all_contracts = []
                seen_names.clear()
                for c in self._registry_port.list_all():
                    name = getattr(c, "name", "")
                    if name and name not in seen_names:
                        seen_names.add(name)
                        all_contracts.append(c)
        else:
            all_contracts = list(self._registry_port.list_all())

        if filter_prompt_type:
            all_contracts = [c for c in all_contracts if _is_prompt_contract(c)]
        else:
            all_contracts = [c for c in all_contracts if not _is_prompt_contract(c)]

        logger.debug(
            "_run_pipeline: step0 all_contracts=%d query_domains=%s safety_band=%s",
            len(all_contracts),
            query_domains,
            safety_band,
        )

        if not all_contracts:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            result = RetrievalResult(
                capabilities=[],
                total_matched=0,
                query_latency_ms=elapsed_ms,
                query_intent=query_text,
                index_size=self._index.size,
                embedding_model=self._config.embedding_model,
                diagnostics={
                    "query_domains": sorted(query_domains),
                    "candidate_count": 0,
                    "survivor_count": 0,
                    "rejection_counts": {},
                    "domain_fallback_used": domain_fallback_used,
                },
            )
            return self._finalize_metrics(result, start, query_type)

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

        filter_results = self._hard_filter.filter(
            filter_candidates,
            user_band=safety_band,
            available_param_names=param_names,
            session_keys=session_keys,
        )
        passed_names = {result.contract_name for result in filter_results if result.passed}
        survivors = [
            candidate for candidate in filter_candidates if candidate.contract_name in passed_names
        ]
        rejection_counts: dict[str, int] = {}
        for result in filter_results:
            if result.passed or not result.rejection_reason:
                continue
            rejection_counts[result.rejection_reason] = (
                rejection_counts.get(result.rejection_reason, 0) + 1
            )

        total_matched = len(survivors)

        logger.debug(
            "_run_pipeline: step2 filter_candidates=%d survivors=%d",
            len(filter_candidates),
            total_matched,
        )

        if not survivors:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            result = RetrievalResult(
                capabilities=[],
                total_matched=0,
                query_latency_ms=elapsed_ms,
                query_intent=query_text,
                index_size=self._index.size,
                embedding_model=self._config.embedding_model,
                diagnostics={
                    "query_domains": sorted(query_domains),
                    "candidate_count": len(filter_candidates),
                    "survivor_count": 0,
                    "rejection_counts": rejection_counts,
                    "domain_fallback_used": domain_fallback_used,
                },
            )
            return self._finalize_metrics(result, start, query_type)

        # -- Step 3: Soft rank ------------------------------------------
        ranker_candidates = []
        for s in survivors:
            contract = s.contract
            name = s.contract_name

            # Get capability vector from the index
            cap_vector = None
            if self._index.contains(name):
                # Use the public thread-safe snapshot method (Issue 3 fix)
                cap_vector = self._index.get_vectors_snapshot().get(name)

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
            query_text=query_text,
        )

        # -- Step 4: Top-K select ---------------------------------------
        selected = self._top_k_selector.select(ranked, k=effective_k)
        ranked_by_name = {item.contract_name: item for item in ranked}

        # Convert to ScoredCapability for the final result
        capabilities = []
        for sel in selected:
            diagnostic_source = ranked_by_name.get(sel.contract_name)
            capabilities.append(
                ScoredCapability(
                    contract=sel.contract,
                    score=sel.score,
                    diagnostics={
                        "semantic_similarity": getattr(
                            diagnostic_source,
                            "semantic_similarity",
                            0.0,
                        ),
                        "domain_match": getattr(diagnostic_source, "domain_match", 0.0),
                        "contract_evidence_score": getattr(
                            diagnostic_source,
                            "contract_evidence_score",
                            0.0,
                        ),
                        "domain_hint_exact": sel.contract_name in domain_exact_names,
                    },
                )
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)

        result = RetrievalResult(
            capabilities=capabilities,
            total_matched=total_matched,
            query_latency_ms=elapsed_ms,
            query_intent=query_text,
            index_size=self._index.size,
            embedding_model=self._config.embedding_model,
            diagnostics={
                "query_domains": sorted(query_domains),
                "candidate_count": len(filter_candidates),
                "survivor_count": total_matched,
                "rejection_counts": rejection_counts,
                "domain_fallback_used": domain_fallback_used,
            },
        )
        return self._finalize_metrics(result, start, query_type)

    def _finalize_metrics(self, result: Any, start: float, query_type: str) -> Any:
        """Record retrieval metrics and return the result."""
        metrics = get_default_metrics()
        try:
            duration_s = time.monotonic() - start
            metrics.observe_retrieval_duration(query_type, duration_s)
            metrics.inc_retrievals()
        except Exception:
            logger.warning("Failed to record retrieval metrics", exc_info=True)
        return result
