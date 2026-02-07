"""
k1.fabric.retrieval -- Semantic Retrieval Engine (Epic 4.1).

Provides intelligent capability discovery for the Planner (Role 1).
Pipeline: Embed -> HardFilter -> SoftRanker -> TopKSelector.

Submodules:
  embedding_index    -- FAISS vector index for semantic search (4.1.1)
  hard_filter        -- Pre-ranking elimination rules (4.1.2)
  soft_ranker        -- Composite scoring (4.1.3)
  top_k_selector     -- Top-K truncation (4.1.4)
  retrieval_engine   -- Full pipeline (4.1.5)

Usage::

    from k1.fabric.retrieval import (
        EmbeddingIndex,
        EmbeddingIndexConfig,
        HardFilter,
        HardFilterConfig,
        FilterCandidate,
        SoftRanker,
        SoftRankerConfig,
        TopKSelector,
        RetrievalEngine,
    )
"""

from k1.fabric.retrieval.embedding_index import (
    DEFAULT_DIMENSION,
    IVF_NLIST,
    IVF_NPROBE,
    IVF_THRESHOLD,
    DimensionMismatchError,
    DuplicateVectorError,
    EmbeddingIndex,
    EmbeddingIndexConfig,
    EmbeddingIndexError,
    SearchHit,
    VectorNotFoundError,
)
from k1.fabric.retrieval.hard_filter import (
    DEFAULT_SATISFIABILITY_THRESHOLD,
    REASON_INPUT_UNSATISFIABLE,
    REASON_OFFLINE,
    REASON_SAFETY_BAND,
    FilterCandidate,
    FilterResult,
    HardFilter,
    HardFilterConfig,
)
from k1.fabric.retrieval.retrieval_engine import (
    EmbeddingUnavailableError,
    RetrievalEngine,
    RetrievalEngineConfig,
    RetrievalEngineError,
)
from k1.fabric.retrieval.soft_ranker import (
    DEFAULT_SUCCESS_RATE,
    DEGRADED_PENALTY,
    W_COST_LATENCY,
    W_DOMAIN,
    W_SEMANTIC,
    W_SUCCESS,
    RankedResult,
    RankerCandidate,
    SoftRanker,
    SoftRankerConfig,
)
from k1.fabric.retrieval.top_k_selector import (
    DEFAULT_K,
    MAX_K,
    MIN_K,
    SelectedCapability,
    TopKSelector,
    TopKSelectorConfig,
)

__all__ = [
    # embedding_index.py (4.1.1)
    "DEFAULT_DIMENSION",
    "DimensionMismatchError",
    "DuplicateVectorError",
    "EmbeddingIndex",
    "EmbeddingIndexConfig",
    "EmbeddingIndexError",
    "IVF_NLIST",
    "IVF_NPROBE",
    "IVF_THRESHOLD",
    "SearchHit",
    "VectorNotFoundError",
    # hard_filter.py (4.1.2)
    "DEFAULT_SATISFIABILITY_THRESHOLD",
    "FilterCandidate",
    "FilterResult",
    "HardFilter",
    "HardFilterConfig",
    "REASON_INPUT_UNSATISFIABLE",
    "REASON_OFFLINE",
    "REASON_SAFETY_BAND",
    # soft_ranker.py (4.1.3)
    "DEFAULT_SUCCESS_RATE",
    "DEGRADED_PENALTY",
    "RankedResult",
    "RankerCandidate",
    "SoftRanker",
    "SoftRankerConfig",
    "W_COST_LATENCY",
    "W_DOMAIN",
    "W_SEMANTIC",
    "W_SUCCESS",
    # top_k_selector.py (4.1.4)
    "DEFAULT_K",
    "MAX_K",
    "MIN_K",
    "SelectedCapability",
    "TopKSelector",
    "TopKSelectorConfig",
    # retrieval_engine.py (4.1.5)
    "EmbeddingUnavailableError",
    "RetrievalEngine",
    "RetrievalEngineConfig",
    "RetrievalEngineError",
]
