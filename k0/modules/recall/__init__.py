"""
Recall Module - GAP-001 Milestone 5

Provides context expansion services for rich LLM context generation.
Combines vector search with entity graph traversal.

Components:
- EntityExtractor: Extracts entity IDs from truth layer records
- EntityGraphExpander: Traverses st_kg_dom → st_kg_edges
- RelatedContextFetcher: Fetches related records from all layers
- ContextExpander: Orchestrates the full expansion flow

Usage:
    from k0.modules.recall import ContextExpander

    expander = ContextExpander()
    expanded = await expander.expand(
        query="Where did Mom and Dad go yesterday?",
        embedding=query_embedding,
        conn=conn,
    )
    llm_context = expanded.to_llm_context()

GAP Reference: GAP_001 Section 6 (Rich LLM Context)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_5_CONTEXT_EXPANDER.md
"""

from k0.modules.recall.context_expander import ContextExpander, ExpandedContext
from k0.modules.recall.entity_extractor import EntityExtractor, ExtractionResult
from k0.modules.recall.entity_graph_expander import (
    EntityGraphExpander,
    ExpandedEntity,
    ExpansionResult,
)
from k0.modules.recall.related_context_fetcher import (
    RelatedContext,
    RelatedContextFetcher,
)

__all__ = [
    # Main orchestrator
    "ContextExpander",
    "ExpandedContext",
    # Entity extraction
    "EntityExtractor",
    "ExtractionResult",
    # Graph expansion
    "EntityGraphExpander",
    "ExpandedEntity",
    "ExpansionResult",
    # Context fetching
    "RelatedContextFetcher",
    "RelatedContext",
]
