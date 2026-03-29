# Recall Module - GAP-001 Milestone 5

This module provides context expansion services for P01 recall pipeline.

## Components

- `entity_extractor.py` - Extracts entity IDs from truth layer records
- `entity_graph_expander.py` - Traverses entity graph (st_kg_dom → st_kg_edges)
- `related_context_fetcher.py` - Fetches related context from all truth layers
- `context_expander.py` - Orchestrates full context expansion flow

## Usage

```python
from k0.modules.recall.context_expander import ContextExpander
from k0.modules.embedding.union_index_manager import get_manager

# Get union index searcher
manager = get_manager()
searcher = manager.get_searcher()

# Create context expander
expander = ContextExpander(searcher)

# Expand context for a query
context = await expander.expand(
    query_vector=query_vec,
    query_text="What did I do with Mom?",
    conn=db_connection,
    k=20,
)

# Format for LLM
llm_context = context.to_llm_context()
```

## GAP Reference

- [GAP_001_CROSS_LAYER_VECTOR_LINKING.md](../../../docs/architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md) Section 5.6, 6
