# Milestone 4: P08 FAISS Union Index — Build Composite Index from Truth Layers

> **GAP Reference**: [GAP_001_CROSS_LAYER_VECTOR_LINKING.md](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md) Section 6, 7
> **Effort**: 1 day
> **Priority**: P0 (Critical)
> **Dependencies**: Milestone 3 (R7 Writer Updates)

---

## Overview

Build a **unified FAISS index** from all 6 truth layers with inline vectors:

1. **Query all layers** for `embedding_vector IS NOT NULL`
2. **Build composite index** with metadata (layer, record_id, tenant_id, space_id)
3. **Enable cross-layer similarity search** returning [(layer, id, score), ...]
4. **Schedule periodic rebuild** (every 6 hours)

---

## Epic: FAISS Union Index for Cross-Layer Vector Search

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    FAISS UNION INDEX                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Build Process                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│   st_epi ──────┐                                                 │
│   st_sem ──────┤                                                 │
│   st_procedural┼──▶ UNION SELECT ──▶ FAISS IndexFlatIP(768) ──▶ │
│   st_social ───┤       │                    │                    │
│   st_prospective       │                    ▼                    │
│   st_kg_dom ───┘       │           ┌─────────────────┐          │
│                        │           │  Metadata Store  │          │
│                        │           │ (layer, id, etc) │          │
│                        ▼           └─────────────────┘          │
│               ┌─────────────┐                                    │
│               │ Vectors DB  │                                    │
│               │  (in-memory)│                                    │
│               └─────────────┘                                    │
│                                                                  │
│  Query Flow:                                                     │
│  1. Embed query → 768-dim vector                                │
│  2. index.search(query_vec, k=20)                               │
│  3. Return [(layer, id, score), ...]                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Issues

### Issue 4.1: Create UnionIndexMetadata Data Model

**Priority**: P0
**Effort**: 1 hour

**Description**:
Create data model for FAISS index metadata that tracks source layer and record ID.

**Files to Create**:

- `k0/modules/embedding/union_index_metadata.py` (NEW)

**Code Structure**:

```python
"""
UnionIndexMetadata — GAP-001 Implementation

Tracks source layer and record ID for each vector in FAISS union index.
Enables cross-layer vector search with proper result attribution.

GAP Reference: GAP_001 Section 6 (FAISS Union Index)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import json


@dataclass
class VectorMetadata:
    """Metadata for a single vector in the union index."""
    layer: str              # st_epi, st_sem, etc.
    record_id: str          # Primary key in source layer
    tenant_id: str          # Multi-tenancy support
    space_id: str           # ACL filtering
    faiss_idx: int = -1     # Position in FAISS index


@dataclass
class UnionIndexMetadata:
    """Metadata store for FAISS union index."""
    entries: List[VectorMetadata] = field(default_factory=list)
    layer_counts: Dict[str, int] = field(default_factory=dict)
    total_vectors: int = 0
    build_timestamp: int = 0  # Unix ms
    model_version: str = "ultrabert-v2.1.0"

    def add(self, meta: VectorMetadata) -> int:
        """Add metadata entry, return FAISS index position."""
        meta.faiss_idx = len(self.entries)
        self.entries.append(meta)
        self.layer_counts[meta.layer] = self.layer_counts.get(meta.layer, 0) + 1
        self.total_vectors += 1
        return meta.faiss_idx

    def get(self, faiss_idx: int) -> Optional[VectorMetadata]:
        """Get metadata by FAISS index position."""
        if 0 <= faiss_idx < len(self.entries):
            return self.entries[faiss_idx]
        return None

    def search_results_to_layer_ids(
        self,
        faiss_indices: List[int],
        scores: List[float],
    ) -> List[Tuple[str, str, float]]:
        """Convert FAISS indices to (layer, record_id, score) tuples."""
        results = []
        for idx, score in zip(faiss_indices, scores):
            meta = self.get(idx)
            if meta:
                results.append((meta.layer, meta.record_id, score))
        return results

    def to_json(self) -> str:
        """Serialize to JSON for persistence."""
        return json.dumps({
            "entries": [
                {
                    "layer": e.layer,
                    "record_id": e.record_id,
                    "tenant_id": e.tenant_id,
                    "space_id": e.space_id,
                    "faiss_idx": e.faiss_idx,
                }
                for e in self.entries
            ],
            "layer_counts": self.layer_counts,
            "total_vectors": self.total_vectors,
            "build_timestamp": self.build_timestamp,
            "model_version": self.model_version,
        })

    @classmethod
    def from_json(cls, data: str) -> "UnionIndexMetadata":
        """Deserialize from JSON."""
        obj = json.loads(data)
        meta = cls(
            layer_counts=obj["layer_counts"],
            total_vectors=obj["total_vectors"],
            build_timestamp=obj["build_timestamp"],
            model_version=obj["model_version"],
        )
        for e in obj["entries"]:
            meta.entries.append(VectorMetadata(**e))
        return meta
```

**References**:

- GAP Section 6: [FAISS Union Index](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#6-recommended-architecture-inline-vectors--entity-graph)
- Existing: [faiss_indexer.py](../../k0/modules/embedding/faiss_indexer.py)

**Acceptance Criteria**:

- [ ] VectorMetadata tracks layer + record_id
- [ ] UnionIndexMetadata supports add/get operations
- [ ] JSON serialization for persistence
- [ ] Unit tests

---

### Issue 4.2: Create UnionIndexBuilder Service

**Priority**: P0
**Effort**: 3 hours

**Description**:
Create service that queries all 6 truth layers and builds composite FAISS index.

**Files to Create**:

- `k0/modules/embedding/union_index_builder.py` (NEW)

**Code Structure**:

```python
"""
UnionIndexBuilder — GAP-001 Implementation

Builds composite FAISS index from all 6 truth layers.
Queries embedding_vector BYTEA columns and adds to unified index.

GAP Reference: GAP_001 Section 7 (P08 FAISS Union Build)
"""

import struct
import time
from typing import List, Optional
import numpy as np

from .union_index_metadata import UnionIndexMetadata, VectorMetadata


# Truth layers with inline vectors
TRUTH_LAYERS = [
    ("st_epi", "episode_id"),
    ("st_sem", "pattern_id"),
    ("st_procedural", "routine_id"),
    ("st_social", "relationship_id"),
    ("st_prospective", "intention_id"),
    ("st_kg_dom", "entity_id"),
]

VECTOR_DIMENSION = 768
VECTOR_BYTES = VECTOR_DIMENSION * 4  # float32


class UnionIndexBuilder:
    """Builds FAISS union index from truth layers."""

    def __init__(self, batch_size: int = 1000):
        self.batch_size = batch_size
        self._faiss = None

    async def build(
        self,
        conn,
        tenant_id: Optional[str] = None,
        space_id: Optional[str] = None,
    ) -> tuple:
        """
        Build FAISS index from all truth layers.

        Args:
            conn: asyncpg connection
            tenant_id: Optional filter
            space_id: Optional filter

        Returns:
            Tuple of (faiss_index, UnionIndexMetadata)
        """
        import faiss

        # Initialize index (Inner Product for normalized vectors)
        index = faiss.IndexFlatIP(VECTOR_DIMENSION)
        metadata = UnionIndexMetadata(
            build_timestamp=int(time.time() * 1000),
        )

        all_vectors = []

        for layer, pk_column in TRUTH_LAYERS:
            vectors, metas = await self._fetch_layer_vectors(
                conn, layer, pk_column, tenant_id, space_id
            )

            for vec, meta in zip(vectors, metas):
                idx = metadata.add(meta)
                all_vectors.append(vec)

        if all_vectors:
            # Stack and add to FAISS
            vectors_np = np.array(all_vectors, dtype=np.float32)
            # Normalize for cosine similarity via inner product
            faiss.normalize_L2(vectors_np)
            index.add(vectors_np)

        return index, metadata

    async def _fetch_layer_vectors(
        self,
        conn,
        layer: str,
        pk_column: str,
        tenant_id: Optional[str],
        space_id: Optional[str],
    ) -> tuple:
        """Fetch vectors from a single truth layer."""
        # Build WHERE clause
        conditions = ["embedding_vector IS NOT NULL"]
        params = []

        if tenant_id:
            params.append(tenant_id)
            conditions.append(f"tenant_id = ${len(params)}")

        if space_id:
            params.append(space_id)
            conditions.append(f"space_id = ${len(params)}")

        # Add lifecycle filter (skip archived/tombstoned)
        conditions.append("(archival_status IS NULL OR archival_status = 'ACTIVE')")

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT {pk_column}, tenant_id, space_id, embedding_vector
            FROM {layer}
            WHERE {where_clause}
        """

        rows = await conn.fetch(query, *params)

        vectors = []
        metas = []

        for row in rows:
            # Unpack BYTEA to float32 array
            vec_bytes = row["embedding_vector"]
            if len(vec_bytes) != VECTOR_BYTES:
                continue

            vec = np.frombuffer(vec_bytes, dtype=np.float32)
            vectors.append(vec)

            metas.append(VectorMetadata(
                layer=layer,
                record_id=row[pk_column],
                tenant_id=row["tenant_id"],
                space_id=row["space_id"],
            ))

        return vectors, metas
```

**References**:

- GAP Section 7: [P08 FAISS Union Build](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#p08-embeddingindexing--major-update)
- Existing: [faiss_indexer.py](../../k0/modules/embedding/faiss_indexer.py)

**Acceptance Criteria**:

- [ ] Queries all 6 truth layers
- [ ] Handles BYTEA → numpy conversion
- [ ] Supports tenant/space filtering
- [ ] Returns (index, metadata) tuple
- [ ] Integration tests

---

### Issue 4.3: Create UnionIndexSearcher Service

**Priority**: P0
**Effort**: 2 hours

**Description**:
Create service that searches the union index and returns cross-layer results.

**Files to Create**:

- `k0/modules/embedding/union_index_searcher.py` (NEW)

**Code Structure**:

```python
"""
UnionIndexSearcher — GAP-001 Implementation

Searches FAISS union index and returns cross-layer results.
Translates FAISS indices back to (layer, record_id, score).

GAP Reference: GAP_001 Section 6 (Query Flow)
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np

from .union_index_metadata import UnionIndexMetadata


@dataclass
class SearchResult:
    """Single search result with layer attribution."""
    layer: str
    record_id: str
    score: float
    tenant_id: str
    space_id: str


class UnionIndexSearcher:
    """Searches FAISS union index."""

    def __init__(self, index, metadata: UnionIndexMetadata):
        """
        Initialize searcher with index and metadata.

        Args:
            index: FAISS index
            metadata: UnionIndexMetadata with layer/id mappings
        """
        self._index = index
        self._metadata = metadata

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 20,
        layer_filter: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
        space_id: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search for similar vectors.

        Args:
            query_vector: 768-dim query embedding
            k: Number of results
            layer_filter: Optional list of layers to search
            tenant_id: Optional tenant filter
            space_id: Optional space filter

        Returns:
            List of SearchResult sorted by score descending
        """
        import faiss

        # Normalize query vector
        query = query_vector.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(query)

        # Search with extra results for post-filtering
        search_k = k * 3 if (layer_filter or tenant_id or space_id) else k
        scores, indices = self._index.search(query, search_k)

        # Convert to SearchResults with filtering
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:  # FAISS returns -1 for empty slots
                continue

            meta = self._metadata.get(idx)
            if not meta:
                continue

            # Apply filters
            if layer_filter and meta.layer not in layer_filter:
                continue
            if tenant_id and meta.tenant_id != tenant_id:
                continue
            if space_id and meta.space_id != space_id:
                continue

            results.append(SearchResult(
                layer=meta.layer,
                record_id=meta.record_id,
                score=float(score),
                tenant_id=meta.tenant_id,
                space_id=meta.space_id,
            ))

            if len(results) >= k:
                break

        return results

    @property
    def total_vectors(self) -> int:
        """Total vectors in index."""
        return self._metadata.total_vectors

    @property
    def layer_counts(self) -> dict:
        """Vector counts per layer."""
        return self._metadata.layer_counts
```

**References**:

- GAP Section 6: [Query Flow](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#6-recommended-architecture-inline-vectors--entity-graph)

**Acceptance Criteria**:

- [ ] Returns SearchResult with layer attribution
- [ ] Supports layer filtering
- [ ] Supports tenant/space filtering
- [ ] Handles empty results
- [ ] Unit tests

---

### Issue 4.4: Create UnionIndexManager (Lifecycle)

**Priority**: P0
**Effort**: 2 hours

**Description**:
Create manager that handles index lifecycle: build, persist, load, and rebuild.

**Files to Create**:

- `k0/modules/embedding/union_index_manager.py` (NEW)

**Code Structure**:

```python
"""
UnionIndexManager — GAP-001 Implementation

Manages FAISS union index lifecycle:
- Build from database
- Persist to disk
- Load from disk
- Scheduled rebuild

GAP Reference: GAP_001 Section 7 (Batch rebuild every 6 hours)
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

from .union_index_builder import UnionIndexBuilder
from .union_index_metadata import UnionIndexMetadata
from .union_index_searcher import UnionIndexSearcher

logger = logging.getLogger(__name__)


class UnionIndexManager:
    """Manages FAISS union index lifecycle."""

    INDEX_FILENAME = "union_index.faiss"
    METADATA_FILENAME = "union_index_metadata.json"

    def __init__(
        self,
        index_dir: str,
        rebuild_interval_hours: int = 6,
    ):
        """
        Initialize manager.

        Args:
            index_dir: Directory to store index files
            rebuild_interval_hours: Rebuild interval (default 6)
        """
        self.index_dir = Path(index_dir)
        self.rebuild_interval_ms = rebuild_interval_hours * 60 * 60 * 1000
        self._index = None
        self._metadata: Optional[UnionIndexMetadata] = None
        self._searcher: Optional[UnionIndexSearcher] = None
        self._builder = UnionIndexBuilder()

    @property
    def is_loaded(self) -> bool:
        """Check if index is loaded."""
        return self._index is not None and self._metadata is not None

    @property
    def needs_rebuild(self) -> bool:
        """Check if index needs rebuild based on age."""
        if not self._metadata:
            return True
        age_ms = int(time.time() * 1000) - self._metadata.build_timestamp
        return age_ms > self.rebuild_interval_ms

    async def build_and_save(self, conn) -> UnionIndexSearcher:
        """Build index from database and persist."""
        import faiss

        logger.info("Building FAISS union index...")
        start = time.time()

        self._index, self._metadata = await self._builder.build(conn)

        # Persist to disk
        self.index_dir.mkdir(parents=True, exist_ok=True)
        index_path = self.index_dir / self.INDEX_FILENAME
        metadata_path = self.index_dir / self.METADATA_FILENAME

        faiss.write_index(self._index, str(index_path))
        metadata_path.write_text(self._metadata.to_json())

        duration_ms = int((time.time() - start) * 1000)
        logger.info(
            "FAISS union index built",
            extra={
                "total_vectors": self._metadata.total_vectors,
                "layer_counts": self._metadata.layer_counts,
                "duration_ms": duration_ms,
            },
        )

        self._searcher = UnionIndexSearcher(self._index, self._metadata)
        return self._searcher

    def load(self) -> Optional[UnionIndexSearcher]:
        """Load index from disk."""
        import faiss

        index_path = self.index_dir / self.INDEX_FILENAME
        metadata_path = self.index_dir / self.METADATA_FILENAME

        if not index_path.exists() or not metadata_path.exists():
            logger.warning("No FAISS union index found on disk")
            return None

        self._index = faiss.read_index(str(index_path))
        self._metadata = UnionIndexMetadata.from_json(metadata_path.read_text())
        self._searcher = UnionIndexSearcher(self._index, self._metadata)

        logger.info(
            "FAISS union index loaded",
            extra={
                "total_vectors": self._metadata.total_vectors,
                "build_timestamp": self._metadata.build_timestamp,
            },
        )

        return self._searcher

    def get_searcher(self) -> Optional[UnionIndexSearcher]:
        """Get searcher (load if needed)."""
        if not self._searcher:
            self.load()
        return self._searcher
```

**References**:

- GAP Section 7: [Batch rebuild every 6 hours](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#p08-embeddingindexing--major-update)
- Existing: [faiss_manager.py](../../k0/runtime/faiss_manager.py)

**Acceptance Criteria**:

- [ ] Builds and persists index
- [ ] Loads from disk
- [ ] Tracks rebuild interval
- [ ] Returns UnionIndexSearcher
- [ ] Integration tests

---

### Issue 4.5: Create P08 UnionIndex Rebuild Job

**Priority**: P0
**Effort**: 2 hours

**Description**:
Create scheduled job that rebuilds the union index periodically.

**Files to Create**:

- `k0/pipelines/p08/union_index_rebuild_job.py` (NEW)

**Code Structure**:

```python
"""
P08 UnionIndex Rebuild Job — GAP-001 Implementation

Scheduled job that rebuilds FAISS union index from truth layers.
Runs every 6 hours (configurable).

GAP Reference: GAP_001 Section 7 (Phase 4)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def run(message: Any, context: Any, **config: Any) -> dict:
    """
    Rebuild FAISS union index from all truth layers.

    Args:
        message: BusMessage (trigger event)
        context: PipelineContext with syscalls
        **config: Configuration:
            - index_dir: Directory for index files
            - force: Force rebuild regardless of age

    Returns:
        Dictionary with rebuild statistics
    """
    from k0.modules.embedding.union_index_manager import UnionIndexManager
    from k0.db.connection import connection_scope

    index_dir = config.get("index_dir", "/data/faiss_union")
    force = config.get("force", False)

    manager = UnionIndexManager(index_dir)

    # Check if rebuild needed
    if not force and not manager.needs_rebuild:
        logger.info("FAISS union index is fresh, skipping rebuild")
        return {
            "action": "skipped",
            "reason": "index_fresh",
        }

    # Rebuild
    async with connection_scope() as conn:
        searcher = await manager.build_and_save(conn)

    return {
        "action": "rebuilt",
        "total_vectors": searcher.total_vectors,
        "layer_counts": searcher.layer_counts,
    }
```

**References**:

- GAP Section 7: [P08 Update](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#p08-embeddingindexing--major-update)
- Existing: [faiss_indexer.py](../../k0/modules/embedding/faiss_indexer.py)

**Acceptance Criteria**:

- [ ] Rebuilds index from all layers
- [ ] Respects rebuild interval
- [ ] Supports force rebuild
- [ ] Returns statistics
- [ ] Integration tests

---

### Issue 4.6: Register UnionIndex Syscalls

**Priority**: P1
**Effort**: 1 hour

**Description**:
Register syscalls for union index operations.

**Files to Modify**:

- `k0/kernel/syscalls.py` (MODIFY)

**New Syscalls**:

```python
async def union_index_search(
    self,
    query_vector: list,
    k: int = 20,
    layer_filter: list = None,
    tenant_id: str = None,
    space_id: str = None,
) -> dict:
    """
    Search FAISS union index.

    Returns:
        {"results": [{"layer": "st_epi", "record_id": "...", "score": 0.92}, ...]}
    """

async def union_index_rebuild(self, force: bool = False) -> dict:
    """
    Trigger union index rebuild.

    Returns:
        {"action": "rebuilt", "total_vectors": 50000, ...}
    """
```

**References**:

- Existing syscalls: [syscalls.py](../../k0/kernel/syscalls.py)

**Acceptance Criteria**:

- [ ] `union_index_search` syscall registered
- [ ] `union_index_rebuild` syscall registered
- [ ] Capability checks in place
- [ ] Unit tests

---

### Issue 4.7: Unit Tests for UnionIndex

**Priority**: P1
**Effort**: 2 hours

**Description**:
Create unit tests for all union index components.

**Files to Create**:

- `tests/k0/modules/embedding/test_union_index_metadata.py` (NEW)
- `tests/k0/modules/embedding/test_union_index_builder.py` (NEW)
- `tests/k0/modules/embedding/test_union_index_searcher.py` (NEW)

**Test Cases**:

1. Metadata add/get operations
2. JSON serialization round-trip
3. Builder queries all 6 layers
4. Searcher filters by layer
5. Searcher filters by tenant/space
6. Empty index handling
7. Manager load/save lifecycle

**References**:

- Existing tests: `tests/k0/modules/embedding/test_faiss_indexer.py`

**Acceptance Criteria**:

- [ ] All test cases pass
- [ ] 80%+ code coverage
- [ ] No mocks for FAISS (use real index)

---

## Dependency Graph

```
┌──────────────────────────────────────────────────────────────┐
│                    ISSUE DEPENDENCIES                         │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  4.1 UnionIndexMetadata ──┐                                   │
│                           ├──▶ 4.2 UnionIndexBuilder          │
│                           │              │                    │
│                           │              ▼                    │
│                           └──▶ 4.3 UnionIndexSearcher         │
│                                          │                    │
│                                          ▼                    │
│                           4.4 UnionIndexManager               │
│                                          │                    │
│                                          ▼                    │
│                           4.5 P08 Rebuild Job                 │
│                                          │                    │
│                                          ▼                    │
│                           4.6 Syscalls Registration           │
│                                          │                    │
│                                          ▼                    │
│                           4.7 Unit Tests                      │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Verification Checklist

After completing all issues:

- [ ] UnionIndexBuilder queries all 6 truth layers
- [ ] Index persists to disk and loads correctly
- [ ] Search returns (layer, record_id, score) tuples
- [ ] Tenant/space filtering works
- [ ] Scheduled rebuild respects interval
- [ ] All tests pass

---

## Files Created/Modified Summary

| File | Action | Issue |
|------|--------|-------|
| `k0/modules/embedding/union_index_metadata.py` | CREATE | 4.1 |
| `k0/modules/embedding/union_index_builder.py` | CREATE | 4.2 |
| `k0/modules/embedding/union_index_searcher.py` | CREATE | 4.3 |
| `k0/modules/embedding/union_index_manager.py` | CREATE | 4.4 |
| `k0/pipelines/p08/union_index_rebuild_job.py` | CREATE | 4.5 |
| `k0/kernel/syscalls.py` | MODIFY | 4.6 |
| `tests/k0/modules/embedding/test_union_index_*.py` | CREATE | 4.7 |

---

## Next Milestone

After Milestone 4 is complete, proceed to:

- **Milestone 5: P01 Context Expander** — Entity graph traversal for rich LLM context
