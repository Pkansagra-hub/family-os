"""
ContextExpander - GAP-001 Milestone 5 (Issue 5.4)

Orchestrates the full context expansion flow:
Vector Search → Entity Extraction → Graph Expansion → Context Fetch

This is the main entry point for rich LLM context generation.

GAP Reference: GAP_001 Section 6 (Rich LLM Context)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_5_CONTEXT_EXPANDER.md
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import numpy as np

from k0.modules.embedding.union_index_searcher import SearchResult, UnionIndexSearcher
from k0.modules.recall.entity_extractor import EntityExtractor
from k0.modules.recall.entity_graph_expander import EntityGraphExpander
from k0.modules.recall.related_context_fetcher import (
    RelatedContext,
    RelatedContextFetcher,
)

logger = logging.getLogger(__name__)


@dataclass
class ExpandedContext:
    """
    Full expanded context for LLM consumption.

    Combines direct search results with graph-expanded
    related context for comprehensive memory recall.

    Attributes:
        query: Original query text
        direct_results: Direct vector search matches
        expanded_entities: Entities found via graph traversal
        related_context: Related records from all truth layers
        timing_ms: Timing breakdown for each phase
    """

    query: str
    direct_results: List[SearchResult] = field(default_factory=list)
    expanded_entities: Set[str] = field(default_factory=set)
    related_context: Optional[RelatedContext] = None
    timing_ms: Dict[str, float] = field(default_factory=dict)

    def to_llm_context(self) -> Dict:
        """
        Convert to LLM-friendly dictionary.

        Returns:
            Dict with structured context for LLM prompt injection
        """
        # Format direct results
        direct_matches = []
        for result in self.direct_results:
            direct_matches.append(
                {
                    "layer": result.layer,
                    "record_id": result.record_id,
                    "score": result.score,
                    "tenant_id": result.tenant_id,
                    "space_id": result.space_id,
                }
            )

        # Build context structure
        context = {
            "query": self.query,
            "direct_matches": direct_matches,
            "match_count": len(self.direct_results),
        }

        # Add related context if available
        if self.related_context:
            context.update(self.related_context.to_dict())
            context["related_count"] = self.related_context.total_records

        return context

    def summary(self) -> Dict:
        """Summary for logging."""
        return {
            "query_len": len(self.query),
            "direct_results": len(self.direct_results),
            "expanded_entities": len(self.expanded_entities),
            "related_records": (self.related_context.total_records if self.related_context else 0),
            "timing_ms": self.timing_ms,
        }


class ContextExpander:
    """
    Main orchestrator for context expansion.

    Coordinates the full flow:
    1. Vector search across union index
    2. Entity extraction from results
    3. Graph expansion for related entities
    4. Related context fetch from all layers

    Usage:
        expander = ContextExpander()
        expanded = await expander.expand(
            query="Where did Mom and Dad go yesterday?",
            embedding=query_embedding,
            conn=conn,
        )
        llm_context = expanded.to_llm_context()
    """

    def __init__(
        self,
        top_k: int = 10,
        max_hops: int = 1,
        min_edge_weight: float = 0.5,
        max_per_layer: int = 10,
        max_neighbors: int = 20,
    ):
        """
        Initialize expander with configuration.

        Args:
            top_k: Number of vector search results
            max_hops: Graph traversal depth
            min_edge_weight: Minimum edge weight for graph traversal
            max_per_layer: Maximum related records per layer
            max_neighbors: Maximum neighbors per entity
        """
        self.top_k = top_k
        self.max_hops = max_hops
        self.min_edge_weight = min_edge_weight
        self.max_per_layer = max_per_layer
        self.max_neighbors = max_neighbors

        # Initialize sub-components
        self.entity_extractor = EntityExtractor()
        self.graph_expander = EntityGraphExpander(
            max_hops=max_hops,
            min_edge_weight=min_edge_weight,
            max_neighbors=max_neighbors,
        )
        self.context_fetcher = RelatedContextFetcher(
            max_per_layer=max_per_layer,
        )

    async def expand(
        self,
        query: str,
        embedding: List[float],
        conn: Any,
        tenant_id: Optional[str] = None,
        layers: Optional[List[str]] = None,
        searcher: Optional[UnionIndexSearcher] = None,
        records_by_id: Optional[Dict[str, Dict]] = None,
    ) -> ExpandedContext:
        """
        Expand context for a query.

        Args:
            query: Query text
            embedding: Query embedding vector (768-dim)
            conn: asyncpg database connection
            tenant_id: Optional tenant filter
            layers: Layers to search (None = all)
            searcher: Pre-configured UnionIndexSearcher (required)
            records_by_id: Pre-fetched records keyed by record_id (required for entity extraction)

        Returns:
            ExpandedContext with full context
        """
        timing: Dict[str, float] = {}
        start_total = time.perf_counter()

        # Phase 1: Vector search
        start_phase = time.perf_counter()

        if searcher is None:
            logger.warning("ContextExpander: no searcher provided, returning empty context")
            return ExpandedContext(query=query)

        query_vector = np.array(embedding, dtype=np.float32)
        search_results = searcher.search(
            query_vector=query_vector,
            k=self.top_k,
            layer_filter=layers,
            tenant_id=tenant_id,
        )
        timing["vector_search_ms"] = (time.perf_counter() - start_phase) * 1000

        logger.debug(
            "ContextExpander: vector search complete",
            extra={
                "result_count": len(search_results),
                "time_ms": timing["vector_search_ms"],
            },
        )

        if not search_results:
            return ExpandedContext(
                query=query,
                direct_results=[],
                timing_ms={"total_ms": (time.perf_counter() - start_total) * 1000},
            )

        # Phase 2: Entity extraction
        start_phase = time.perf_counter()

        # Convert SearchResult list to the format expected by entity extractor
        # Entity extractor expects: List[(layer, record_id, score)]
        result_tuples = [(r.layer, r.record_id, r.score) for r in search_results]

        # If no records provided, extract entities from search results only
        if records_by_id is None:
            records_by_id = {}

        extraction = self.entity_extractor.extract_from_search_results(result_tuples, records_by_id)
        timing["entity_extraction_ms"] = (time.perf_counter() - start_phase) * 1000

        logger.debug(
            "ContextExpander: entity extraction complete",
            extra={
                "entity_count": len(extraction.entity_ids),
                "time_ms": timing["entity_extraction_ms"],
            },
        )

        # Phase 3: Graph expansion
        start_phase = time.perf_counter()
        expansion = await self.graph_expander.expand(extraction.entity_ids, conn)
        timing["graph_expansion_ms"] = (time.perf_counter() - start_phase) * 1000

        # Combine seed + expanded entities
        all_entities = extraction.entity_ids | expansion.get_all_entity_ids()

        logger.debug(
            "ContextExpander: graph expansion complete",
            extra={
                "seed_entities": len(extraction.entity_ids),
                "expanded_count": expansion.expanded_count,
                "total_entities": len(all_entities),
                "time_ms": timing["graph_expansion_ms"],
            },
        )

        # Phase 4: Related context fetch
        start_phase = time.perf_counter()

        # Exclude direct match record IDs to avoid duplicates
        exclude_ids = {r.record_id for r in search_results}

        related_context = await self.context_fetcher.fetch(
            entity_ids=all_entities,
            conn=conn,
            tenant_id=tenant_id,
            exclude_record_ids=exclude_ids,
        )
        timing["context_fetch_ms"] = (time.perf_counter() - start_phase) * 1000

        logger.debug(
            "ContextExpander: context fetch complete",
            extra={
                "related_records": related_context.total_records,
                "time_ms": timing["context_fetch_ms"],
            },
        )

        timing["total_ms"] = (time.perf_counter() - start_total) * 1000

        expanded = ExpandedContext(
            query=query,
            direct_results=search_results,
            expanded_entities=all_entities,
            related_context=related_context,
            timing_ms=timing,
        )

        logger.info(
            "ContextExpander: expansion complete",
            extra=expanded.summary(),
        )

        return expanded

    async def expand_from_records(
        self,
        query: str,
        records: List[Dict],
        conn: Any,
        tenant_id: Optional[str] = None,
    ) -> ExpandedContext:
        """
        Expand context from pre-fetched records.

        Use this when you already have search results and just
        want to expand context.

        Args:
            query: Query text
            records: Pre-fetched records with layer and id fields
            conn: asyncpg database connection
            tenant_id: Optional tenant filter

        Returns:
            ExpandedContext with expanded context
        """
        timing: Dict[str, float] = {}
        start_total = time.perf_counter()

        # Build records_by_id for entity extraction
        records_by_id: Dict[str, Dict] = {}
        for record in records:
            record_id = record.get("id", record.get("record_id", ""))
            if record_id:
                records_by_id[record_id] = record

        # Convert to SearchResult format
        search_results: List[SearchResult] = []
        for record in records:
            record_id = record.get("id", record.get("record_id", ""))
            search_results.append(
                SearchResult(
                    layer=record.get("layer", "unknown"),
                    record_id=record_id,
                    score=record.get("score", 0.0),
                    tenant_id=record.get("tenant_id", ""),
                    space_id=record.get("space_id", ""),
                )
            )

        # Phase 1: Entity extraction
        start_phase = time.perf_counter()
        result_tuples = [(r.layer, r.record_id, r.score) for r in search_results]
        extraction = self.entity_extractor.extract_from_search_results(result_tuples, records_by_id)
        timing["entity_extraction_ms"] = (time.perf_counter() - start_phase) * 1000

        # Phase 2: Graph expansion
        start_phase = time.perf_counter()
        expansion = await self.graph_expander.expand(extraction.entity_ids, conn)
        timing["graph_expansion_ms"] = (time.perf_counter() - start_phase) * 1000

        all_entities = extraction.entity_ids | expansion.get_all_entity_ids()

        # Phase 3: Related context fetch
        start_phase = time.perf_counter()
        exclude_ids = {r.record_id for r in search_results}
        related_context = await self.context_fetcher.fetch(
            entity_ids=all_entities,
            conn=conn,
            tenant_id=tenant_id,
            exclude_record_ids=exclude_ids,
        )
        timing["context_fetch_ms"] = (time.perf_counter() - start_phase) * 1000

        timing["total_ms"] = (time.perf_counter() - start_total) * 1000

        return ExpandedContext(
            query=query,
            direct_results=search_results,
            expanded_entities=all_entities,
            related_context=related_context,
            timing_ms=timing,
        )
