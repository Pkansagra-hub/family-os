# P01 Memory Recall Pipeline — Whiteboard

> **Status**: NOT IMPLEMENTED
> **Dependency**: GAP-001 Milestone 5 components ready (see below)
> **Priority**: TBD

---

## Overview

P01 handles memory retrieval operations via FAISS union index search + entity graph expansion.

**Cognitive Role**: Memory retrieval operations
**Flow**: ← FROM Memory Backbone
**Trigger**: Context Bundle Builder → P01 (optional evented read)

---

## GAP-001 Milestone 5 Components (READY)

The following components are implemented and ready for P01 integration:

| Component | Location | Status |
|-----------|----------|--------|
| EntityExtractor | `k0/modules/recall/entity_extractor.py` | ✅ Complete |
| EntityGraphExpander | `k0/modules/recall/entity_graph_expander.py` | ✅ Complete |
| RelatedContextFetcher | `k0/modules/recall/related_context_fetcher.py` | ✅ Complete |
| ContextExpander | `k0/modules/recall/context_expander.py` | ✅ Complete |
| context_expand syscall | `k0/kernel/syscalls.py` | ✅ Complete |
| Unit Tests | `tests/k0/modules/recall/` | ✅ 62 tests passing |

---

## Integration Requirements (When P01 is Created)

### Recall Phase

```python
# k0/pipelines/p01/phases/recall.py

from k0.modules.recall.context_expander import ContextExpander
from k0.modules.embedding.union_index_manager import UnionIndexManager

# Integration pattern:
manager = UnionIndexManager(config.index_dir)
searcher = manager.get_searcher()
expander = ContextExpander(searcher)

context = await expander.expand(
    query_vector=query_vec,
    query_text=query_text,
    conn=conn,
    k=20,
    tenant_id=tenant_id,
)

return context.to_llm_context()
```

### Events

- Consumes: `cognitive.recall.bundle.assembled`
- Produces: `memory.recall.*` events

---

## References

- GAP: `docs/architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md` Section 6-7
- Milestone: `docs/plans/GAP_001_MILESTONE_5_CONTEXT_EXPANDER.md` Issue 5.5
- Recall Module: `k0/modules/recall/README.md`
