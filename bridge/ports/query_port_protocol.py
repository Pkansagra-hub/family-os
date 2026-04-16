"""IKernelQueryPort — K1→K0→K1 request/response recall.

Multi-selector query bundles for long-term memory recall.
Selector types: episodic, semantic, session, device, belief, graph.

Offline behaviour:
    Returns empty RecallBundle when K0 is unreachable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecallSelector:
    """A single recall query selector.

    Attributes:
        type: Selector kind — one of: episodic, semantic, session,
              device, belief, graph.
        topic: Optional topic filter within the selector type.
        limit: Max results for this selector (default 10).
        cursor: Pagination cursor for continuation.
        after: ISO-8601 timestamp — only return items after this time.
        query: Free-text query for semantic/graph selectors.
    """

    type: str
    topic: str = ""
    limit: int = 10
    cursor: str = ""
    after: str = ""
    query: str = ""


@dataclass(frozen=True, slots=True)
class QueryEnvelope:
    """A complete query request to K0.

    Attributes:
        selectors: One or more RecallSelectors.
        space_id: Tenant space (from BridgeConfig).
        tenant_id: Tenant identifier (from BridgeConfig).
        max_latency_ms: Maximum acceptable round-trip latency.
                        0 = no limit.
        fail_fast: If True, return partial results on timeout
                   rather than waiting for all selectors.
        trace_id: Cognitive trace ID for distributed tracing.
    """

    selectors: list[RecallSelector]
    space_id: str = ""
    tenant_id: str = ""
    max_latency_ms: int = 0
    fail_fast: bool = False
    trace_id: str = ""


@dataclass(frozen=True, slots=True)
class RecallItem:
    """A single recalled memory item from K0.

    Attributes:
        selector_type: Which selector produced this item.
        content: The recalled content (structure depends on type).
        score: Relevance/similarity score (0.0–1.0).
        source: K0 storage layer that served this item.
        cursor: Pagination cursor for fetching more from this point.
    """

    selector_type: str
    content: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    source: str = ""
    cursor: str = ""


@dataclass(frozen=True, slots=True)
class RecallBundle:
    """Aggregated results from a multi-selector query.

    Attributes:
        items: All recalled items across all selectors.
        total_count: Total matching items (may exceed len(items)
                     due to per-selector limits).
        latency_ms: K0 round-trip latency for this bundle.
        partial: True if fail_fast returned before all selectors completed.
        trace_id: Echoed trace ID for correlation.
    """

    items: list[RecallItem] = field(default_factory=list)
    total_count: int = 0
    latency_ms: int = 0
    partial: bool = False
    trace_id: str = ""

    @classmethod
    def empty(cls, *, trace_id: str = "") -> RecallBundle:
        """Create an empty bundle (offline fallback)."""
        return cls(trace_id=trace_id)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IKernelQueryPort(Protocol):
    """K1→K0→K1 request/response recall queries.

    Aggregates multiple recall selectors into a single round-trip.
    Supports episodic (WAL), semantic (pgvector), session, device,
    belief, and graph (KG traversal) selectors.

    Offline behaviour:
        Returns ``RecallBundle.empty()`` when K0 is unreachable.
        K1 continues with local-only context.
    """

    async def query(self, envelope: QueryEnvelope) -> RecallBundle:
        """Execute a multi-selector recall query against K0.

        Args:
            envelope: Query envelope with selectors and constraints.

        Returns:
            RecallBundle with all matched items.
            Empty bundle if K0 is offline.
        """
        ...  # pragma: no cover

    async def query_single(
        self,
        selector: RecallSelector,
        *,
        trace_id: str = "",
    ) -> RecallBundle:
        """Convenience: query with a single selector.

        Args:
            selector: Single RecallSelector.
            trace_id: Cognitive trace ID.

        Returns:
            RecallBundle with matched items for this selector.
        """
        ...  # pragma: no cover
