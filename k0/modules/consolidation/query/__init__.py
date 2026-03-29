"""Truth Candidates Query types -- M9.3 (Universal Reconciliation Engine).

Defines the request/response types and query modes for the unified
truth_candidates_query syscall that replaces 8+ bespoke query paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field  # noqa: F811
from enum import Enum
from typing import Any  # noqa: F401


class QueryMode(Enum):
    """How the syscall searches for truth candidates."""

    EMBEDDING = "embedding"  # pgvector ANN cosine search (ORDER BY <=>)
    KEY = "key"  # Exact/fuzzy WHERE clause match
    HYBRID = "hybrid"  # Key pre-filter + embedding re-rank


@dataclass(frozen=True)
class TruthCandidateRequest:
    """Input to truth_candidates_query syscall.

    Caller specifies which layer(s) to query, with what embedding
    and/or key filters.  The syscall uses TruthLayerSpec to build SQL.
    """

    # Scope (always required)
    tenant_id: str
    space_id: str

    # Target layer(s)
    layers: tuple[str, ...]

    # Embedding search (required for EMBEDDING/HYBRID modes)
    query_embedding: list[float] | None = None

    # Key filters (required for KEY/HYBRID modes, per-layer)
    key_filters: dict[str, Any] = field(default_factory=dict)

    # Pagination
    top_k: int = 10
    min_similarity: float = 0.0

    # Query mode override (None = auto-detect from TruthLayerSpec)
    mode: QueryMode | None = None

    # Performance
    timeout_ms: int = 5000


@dataclass(frozen=True)
class TruthCandidateResponse:
    """Output from truth_candidates_query syscall.

    Contains TruthRecord instances grouped by layer, plus query metadata.
    """

    # Results per layer
    candidates: dict[str, list[Any]]  # layer -> [TruthRecord, ...]
    total_count: int

    # Query metadata (observability)
    layers_queried: tuple[str, ...]
    modes_used: dict[str, str]  # layer -> "embedding"|"key"|"hybrid"
    elapsed_ms: float
    query_id: str  # For trace correlation

    # Error tracking (partial success)
    errors: dict[str, str] = field(default_factory=dict)


def resolve_query_mode(
    supports_embedding: bool,
    supports_key: bool,
    override: QueryMode | None = None,
) -> QueryMode:
    """Derive the query mode from TruthLayerSpec flags.

    If *override* is provided it takes precedence.

    Rules:
        embedding=True  + key=False  -> EMBEDDING
        embedding=False + key=True   -> KEY
        embedding=True  + key=True   -> HYBRID
        embedding=False + key=False  -> KEY (fallback)
    """
    if override is not None:
        return override
    if supports_embedding and supports_key:
        return QueryMode.HYBRID
    if supports_embedding:
        return QueryMode.EMBEDDING
    return QueryMode.KEY
