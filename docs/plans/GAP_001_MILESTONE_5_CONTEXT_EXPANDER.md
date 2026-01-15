# Milestone 5: P01 Context Expander — Entity Graph Traversal for Rich LLM Context

> **GAP Reference**: [GAP_001_CROSS_LAYER_VECTOR_LINKING.md](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md) Section 5.6, 6
> **Effort**: 2 days
> **Priority**: P1 (Important)
> **Dependencies**: Milestone 4 (FAISS Union Index)

---

## Overview

After vector search returns matches from FAISS union index, **expand context** via entity graph:

1. **Extract entity IDs** from matched records (participants_json, actor_id)
2. **Traverse entity graph** (st_kg_dom → st_kg_edges) for related entities
3. **Fetch related truth records** across all layers
4. **Return structured context** for LLM with proper attribution

---

## Epic: Entity Graph Context Expansion for P01 Recall

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    CONTEXT EXPANSION FLOW                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   User Query: "What did I do with Mom last week?"                               │
│                          │                                                       │
│                          ▼                                                       │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                   STEP 1: Vector Search                                │     │
│   │                                                                        │     │
│   │   query_vec = ultrabert.embed("What did I do with Mom last week?")    │     │
│   │   matches = union_index.search(query_vec, k=20)                        │     │
│   │                                                                        │     │
│   │   Returns: [                                                           │     │
│   │     ("st_epi", "ep_123", 0.92),  // "Dinner with Mom at Thai Palace"  │     │
│   │     ("st_sem", "pat_456", 0.85), // "Weekly Thai dinner routine"      │     │
│   │   ]                                                                    │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│                          │                                                       │
│                          ▼                                                       │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                   STEP 2: Entity Extraction                            │     │
│   │                                                                        │     │
│   │   For ep_123: participants_json = ["Mom", "User"]                     │     │
│   │   For pat_456: actor_id = "Mom"                                       │     │
│   │                                                                        │     │
│   │   Extracted entities: {"Mom", "User"}                                 │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│                          │                                                       │
│                          ▼                                                       │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                   STEP 3: Entity Graph Expansion                       │     │
│   │                                                                        │     │
│   │   Traverse st_kg_edges WHERE source_entity_id IN ("Mom", "User")      │     │
│   │   → Find: "Mom" → WORKS_AT → "Hospital"                               │     │
│   │   → Find: "Mom" → LIVES_IN → "San Francisco"                          │     │
│   │                                                                        │     │
│   │   Expanded entities: {"Mom", "User", "Hospital", "San Francisco"}     │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│                          │                                                       │
│                          ▼                                                       │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                   STEP 4: Fetch Related Context                        │     │
│   │                                                                        │     │
│   │   st_epi: WHERE participants_json ?| ["Mom", "User"]                  │     │
│   │   st_sem: WHERE actor_id IN ("Mom", "User")                           │     │
│   │   st_social: WHERE actor_a_id IN (...) OR actor_b_id IN (...)         │     │
│   │   st_prospective: WHERE actor_id IN (...)                             │     │
│   │                                                                        │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│                          │                                                       │
│                          ▼                                                       │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                   STEP 5: Return Rich Context                          │     │
│   │                                                                        │     │
│   │   {                                                                    │     │
│   │     "direct_matches": [...],      // Vector search results            │     │
│   │     "related_episodes": [...],    // From entity expansion            │     │
│   │     "actor_patterns": [...],      // Patterns for same actors         │     │
│   │     "relationships": [...],       // Social graph context             │     │
│   │     "active_intentions": [...]    // Goals involving same entities    │     │
│   │   }                                                                    │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Issues

### Issue 5.1: Create EntityExtractor Service

**Priority**: P0
**Effort**: 2 hours

**Description**:
Create service that extracts entity IDs from matched truth records.

**Files to Create**:

- `k0/modules/recall/entity_extractor.py` (NEW)

**Code Structure**:

```python
"""
EntityExtractor — GAP-001 Implementation

Extracts entity IDs from truth layer records.
Handles different column patterns per layer.

GAP Reference: GAP_001 Section 5.6 (Entity Graph as Universal Linker)
"""

import json
from dataclasses import dataclass
from typing import Dict, List, Set


# Entity columns per layer
ENTITY_COLUMNS = {
    "st_epi": {
        "array": ["participants_json"],  # JSON array of entity IDs
        "scalar": [],
    },
    "st_sem": {
        "array": [],
        "scalar": ["actor_id"],  # Single entity ID
    },
    "st_procedural": {
        "array": [],
        "scalar": ["actor_id"],
    },
    "st_social": {
        "array": [],
        "scalar": ["actor_a_id", "actor_b_id"],  # Two entity IDs
    },
    "st_prospective": {
        "array": ["related_entities_json"],
        "scalar": ["actor_id"],
    },
    "st_kg_dom": {
        "array": [],
        "scalar": [],  # Record IS the entity (entity_id)
    },
    "st_kg_edges": {
        "array": [],
        "scalar": ["source_entity_id", "target_entity_id"],
    },
}


@dataclass
class ExtractionResult:
    """Result of entity extraction."""
    entity_ids: Set[str]
    by_layer: Dict[str, Set[str]]
    record_count: int


class EntityExtractor:
    """Extracts entity IDs from truth layer records."""

    def extract_from_records(
        self,
        records: List[Dict],
        layer: str,
    ) -> ExtractionResult:
        """
        Extract entity IDs from records of a specific layer.

        Args:
            records: List of record dictionaries
            layer: Source layer name

        Returns:
            ExtractionResult with unique entity IDs
        """
        entities = set()
        config = ENTITY_COLUMNS.get(layer, {"array": [], "scalar": []})

        for record in records:
            # Handle array columns (JSON arrays)
            for col in config["array"]:
                if col in record and record[col]:
                    try:
                        arr = json.loads(record[col]) if isinstance(record[col], str) else record[col]
                        entities.update(arr)
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Handle scalar columns
            for col in config["scalar"]:
                if col in record and record[col]:
                    entities.add(record[col])

            # Special case: st_kg_dom record IS the entity
            if layer == "st_kg_dom" and "entity_id" in record:
                entities.add(record["entity_id"])

        return ExtractionResult(
            entity_ids=entities,
            by_layer={layer: entities},
            record_count=len(records),
        )

    def extract_from_search_results(
        self,
        results: List[tuple],  # [(layer, record_id, score), ...]
        records_by_id: Dict[str, Dict],  # {record_id: record_data}
    ) -> ExtractionResult:
        """
        Extract entities from vector search results.

        Args:
            results: Search results with (layer, record_id, score)
            records_by_id: Pre-fetched records keyed by ID

        Returns:
            ExtractionResult with all unique entities
        """
        all_entities = set()
        by_layer = {}

        for layer, record_id, score in results:
            if record_id not in records_by_id:
                continue

            record = records_by_id[record_id]
            result = self.extract_from_records([record], layer)

            all_entities.update(result.entity_ids)
            if layer not in by_layer:
                by_layer[layer] = set()
            by_layer[layer].update(result.entity_ids)

        return ExtractionResult(
            entity_ids=all_entities,
            by_layer=by_layer,
            record_count=len(results),
        )
```

**References**:

- GAP Section 5.6: [Entity Graph as Cross-Layer Linking](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#56-cross-layer-linking-entity-graph-st_kg_dom)
- Schema columns: participants_json, actor_id, actor_a_id, actor_b_id

**Acceptance Criteria**:

- [ ] Extracts from JSON array columns
- [ ] Extracts from scalar columns
- [ ] Handles st_kg_dom special case
- [ ] Deduplicates entity IDs
- [ ] Unit tests

---

### Issue 5.2: Create EntityGraphExpander Service

**Priority**: P0
**Effort**: 3 hours

**Description**:
Create service that traverses entity graph to find related entities.

**Files to Create**:

- `k0/modules/recall/entity_graph_expander.py` (NEW)

**Code Structure**:

```python
"""
EntityGraphExpander — GAP-001 Implementation

Traverses st_kg_dom → st_kg_edges to expand entity set.
Returns 1-hop neighbors with edge weights.

GAP Reference: GAP_001 Section 6 (Entity Graph Expansion)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class ExpandedEntity:
    """An entity with its expansion path."""
    entity_id: str
    canonical_name: str
    entity_type: Optional[str] = None
    hop_distance: int = 0  # 0 = seed, 1 = neighbor
    via_edge_type: Optional[str] = None
    edge_weight: float = 1.0


@dataclass
class ExpansionResult:
    """Result of entity graph expansion."""
    entities: List[ExpandedEntity]
    seed_count: int
    expanded_count: int
    edge_types_traversed: Set[str] = field(default_factory=set)


class EntityGraphExpander:
    """Expands entity set via graph traversal."""

    def __init__(
        self,
        max_hops: int = 1,
        min_edge_weight: float = 0.5,
        max_neighbors: int = 20,
    ):
        """
        Initialize expander.

        Args:
            max_hops: Maximum traversal depth (default 1)
            min_edge_weight: Minimum edge weight to traverse
            max_neighbors: Maximum neighbors per entity
        """
        self.max_hops = max_hops
        self.min_edge_weight = min_edge_weight
        self.max_neighbors = max_neighbors

    async def expand(
        self,
        entity_ids: Set[str],
        conn,
        tenant_id: Optional[str] = None,
    ) -> ExpansionResult:
        """
        Expand entity set via graph traversal.

        Args:
            entity_ids: Seed entity IDs
            conn: Database connection
            tenant_id: Optional tenant filter

        Returns:
            ExpansionResult with expanded entities
        """
        if not entity_ids:
            return ExpansionResult([], 0, 0)

        # Fetch seed entities
        seed_entities = await self._fetch_entities(
            list(entity_ids), conn, tenant_id
        )

        result_entities = []
        for e in seed_entities:
            result_entities.append(ExpandedEntity(
                entity_id=e["entity_id"],
                canonical_name=e.get("canonical_name", e["entity_id"]),
                entity_type=e.get("entity_type"),
                hop_distance=0,
            ))

        if self.max_hops == 0:
            return ExpansionResult(
                entities=result_entities,
                seed_count=len(entity_ids),
                expanded_count=0,
            )

        # Traverse edges to find neighbors
        neighbors, edge_types = await self._find_neighbors(
            entity_ids, conn, tenant_id
        )

        for n in neighbors:
            result_entities.append(ExpandedEntity(
                entity_id=n["entity_id"],
                canonical_name=n.get("canonical_name", n["entity_id"]),
                entity_type=n.get("entity_type"),
                hop_distance=1,
                via_edge_type=n.get("edge_type"),
                edge_weight=n.get("edge_weight", 1.0),
            ))

        return ExpansionResult(
            entities=result_entities,
            seed_count=len(entity_ids),
            expanded_count=len(neighbors),
            edge_types_traversed=edge_types,
        )

    async def _fetch_entities(
        self,
        entity_ids: List[str],
        conn,
        tenant_id: Optional[str],
    ) -> List[Dict]:
        """Fetch entity records from st_kg_dom."""
        query = """
            SELECT entity_id, canonical_name, entity_type
            FROM st_kg_dom
            WHERE entity_id = ANY($1)
        """
        params = [entity_ids]

        if tenant_id:
            query += " AND tenant_id = $2"
            params.append(tenant_id)

        return await conn.fetch(query, *params)

    async def _find_neighbors(
        self,
        entity_ids: Set[str],
        conn,
        tenant_id: Optional[str],
    ) -> tuple:
        """Find 1-hop neighbors via st_kg_edges."""
        entity_list = list(entity_ids)

        # Query edges in both directions
        query = """
            SELECT
                e.edge_type,
                e.edge_weight,
                CASE
                    WHEN e.source_entity_id = ANY($1) THEN e.target_entity_id
                    ELSE e.source_entity_id
                END AS neighbor_id
            FROM st_kg_edges e
            WHERE (e.source_entity_id = ANY($1) OR e.target_entity_id = ANY($1))
              AND e.edge_weight >= $2
              AND e.archival_status IS NULL
        """
        params = [entity_list, self.min_edge_weight]

        if tenant_id:
            query += " AND e.tenant_id = $3"
            params.append(tenant_id)

        query += f" LIMIT {self.max_neighbors * len(entity_ids)}"

        edge_rows = await conn.fetch(query, *params)

        # Get unique neighbor IDs (excluding seeds)
        neighbor_ids = set()
        edge_types = set()
        for row in edge_rows:
            neighbor_id = row["neighbor_id"]
            if neighbor_id not in entity_ids:
                neighbor_ids.add(neighbor_id)
                edge_types.add(row["edge_type"])

        if not neighbor_ids:
            return [], edge_types

        # Fetch neighbor entities
        neighbor_entities = await self._fetch_entities(
            list(neighbor_ids)[:self.max_neighbors],
            conn,
            tenant_id,
        )

        # Attach edge info
        edge_info = {row["neighbor_id"]: row for row in edge_rows}
        for n in neighbor_entities:
            if n["entity_id"] in edge_info:
                info = edge_info[n["entity_id"]]
                n["edge_type"] = info["edge_type"]
                n["edge_weight"] = info["edge_weight"]

        return neighbor_entities, edge_types
```

**References**:

- GAP Section 6: [Entity Graph Expansion](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#6-recommended-architecture-inline-vectors--entity-graph)
- Schema: st_kg_dom, st_kg_edges

**Acceptance Criteria**:

- [ ] Fetches seed entities from st_kg_dom
- [ ] Traverses st_kg_edges for neighbors
- [ ] Respects min_edge_weight threshold
- [ ] Limits neighbor count
- [ ] Supports bidirectional edges
- [ ] Integration tests

---

### Issue 5.3: Create RelatedContextFetcher Service

**Priority**: P0
**Effort**: 3 hours

**Description**:
Create service that fetches related truth records for expanded entities.

**Files to Create**:

- `k0/modules/recall/related_context_fetcher.py` (NEW)

**Code Structure**:

```python
"""
RelatedContextFetcher — GAP-001 Implementation

Fetches related truth records across all layers for given entities.
Returns structured context for LLM consumption.

GAP Reference: GAP_001 Section 6 (Rich LLM Context)
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class RelatedContext:
    """Structured context from related records."""
    episodes: List[Dict] = field(default_factory=list)
    patterns: List[Dict] = field(default_factory=list)
    routines: List[Dict] = field(default_factory=list)
    relationships: List[Dict] = field(default_factory=list)
    intentions: List[Dict] = field(default_factory=list)
    entities: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for LLM."""
        return {
            "related_episodes": self.episodes,
            "actor_patterns": self.patterns,
            "routines": self.routines,
            "relationships": self.relationships,
            "active_intentions": self.intentions,
            "related_entities": self.entities,
        }


class RelatedContextFetcher:
    """Fetches related context for entities."""

    def __init__(
        self,
        max_per_layer: int = 10,
        recency_days: int = 30,
    ):
        """
        Initialize fetcher.

        Args:
            max_per_layer: Maximum records per layer
            recency_days: Filter by recency (0 = no filter)
        """
        self.max_per_layer = max_per_layer
        self.recency_days = recency_days

    async def fetch(
        self,
        entity_ids: Set[str],
        conn,
        tenant_id: Optional[str] = None,
        exclude_record_ids: Optional[Set[str]] = None,
    ) -> RelatedContext:
        """
        Fetch related context for entities.

        Args:
            entity_ids: Entity IDs to search for
            conn: Database connection
            tenant_id: Optional tenant filter
            exclude_record_ids: IDs to exclude (already in direct matches)

        Returns:
            RelatedContext with records from all layers
        """
        if not entity_ids:
            return RelatedContext()

        context = RelatedContext()
        entity_list = list(entity_ids)
        exclude = exclude_record_ids or set()

        # Fetch from each layer in parallel
        context.episodes = await self._fetch_episodes(
            entity_list, conn, tenant_id, exclude
        )
        context.patterns = await self._fetch_patterns(
            entity_list, conn, tenant_id, exclude
        )
        context.routines = await self._fetch_routines(
            entity_list, conn, tenant_id, exclude
        )
        context.relationships = await self._fetch_relationships(
            entity_list, conn, tenant_id, exclude
        )
        context.intentions = await self._fetch_intentions(
            entity_list, conn, tenant_id, exclude
        )

        return context

    async def _fetch_episodes(
        self,
        entity_ids: List[str],
        conn,
        tenant_id: Optional[str],
        exclude: Set[str],
    ) -> List[Dict]:
        """Fetch episodes involving these entities."""
        # Use JSON containment operator for participants_json
        query = """
            SELECT episode_id, embedding_text, started_at, ended_at,
                   participants_json, primary_location, confidence
            FROM st_epi
            WHERE participants_json::jsonb ?| $1
              AND archival_status IS NULL
        """
        params = [entity_ids]

        if tenant_id:
            query += " AND tenant_id = $2"
            params.append(tenant_id)

        query += f" ORDER BY started_at DESC LIMIT {self.max_per_layer}"

        rows = await conn.fetch(query, *params)
        return [
            dict(r) for r in rows
            if r["episode_id"] not in exclude
        ]

    async def _fetch_patterns(
        self,
        entity_ids: List[str],
        conn,
        tenant_id: Optional[str],
        exclude: Set[str],
    ) -> List[Dict]:
        """Fetch semantic patterns for these actors."""
        query = """
            SELECT pattern_id, pattern_type, pattern_name, embedding_text,
                   actor_id, observation_count, confidence
            FROM st_sem
            WHERE actor_id = ANY($1)
              AND archival_status IS NULL
        """
        params = [entity_ids]

        if tenant_id:
            query += " AND tenant_id = $2"
            params.append(tenant_id)

        query += f" ORDER BY observation_count DESC LIMIT {self.max_per_layer}"

        rows = await conn.fetch(query, *params)
        return [
            dict(r) for r in rows
            if r["pattern_id"] not in exclude
        ]

    async def _fetch_routines(
        self,
        entity_ids: List[str],
        conn,
        tenant_id: Optional[str],
        exclude: Set[str],
    ) -> List[Dict]:
        """Fetch procedural routines for these actors."""
        query = """
            SELECT routine_id, routine_name, embedding_text,
                   actor_id, execution_count, avg_duration_ms
            FROM st_procedural
            WHERE actor_id = ANY($1)
              AND archival_status IS NULL
        """
        params = [entity_ids]

        if tenant_id:
            query += " AND tenant_id = $2"
            params.append(tenant_id)

        query += f" ORDER BY execution_count DESC LIMIT {self.max_per_layer}"

        rows = await conn.fetch(query, *params)
        return [
            dict(r) for r in rows
            if r["routine_id"] not in exclude
        ]

    async def _fetch_relationships(
        self,
        entity_ids: List[str],
        conn,
        tenant_id: Optional[str],
        exclude: Set[str],
    ) -> List[Dict]:
        """Fetch social relationships involving these entities."""
        query = """
            SELECT relationship_id, actor_a_id, actor_b_id,
                   relationship_type, embedding_text, strength, sentiment
            FROM st_social
            WHERE (actor_a_id = ANY($1) OR actor_b_id = ANY($1))
              AND archival_status IS NULL
        """
        params = [entity_ids]

        if tenant_id:
            query += " AND tenant_id = $2"
            params.append(tenant_id)

        query += f" ORDER BY strength DESC LIMIT {self.max_per_layer}"

        rows = await conn.fetch(query, *params)
        return [
            dict(r) for r in rows
            if r["relationship_id"] not in exclude
        ]

    async def _fetch_intentions(
        self,
        entity_ids: List[str],
        conn,
        tenant_id: Optional[str],
        exclude: Set[str],
    ) -> List[Dict]:
        """Fetch active intentions for these actors."""
        query = """
            SELECT intention_id, intention_description, embedding_text,
                   actor_id, status, target_date, priority
            FROM st_prospective
            WHERE actor_id = ANY($1)
              AND archival_status IS NULL
              AND status IN ('ACTIVE', 'PENDING')
        """
        params = [entity_ids]

        if tenant_id:
            query += " AND tenant_id = $2"
            params.append(tenant_id)

        query += f" ORDER BY priority DESC, target_date ASC LIMIT {self.max_per_layer}"

        rows = await conn.fetch(query, *params)
        return [
            dict(r) for r in rows
            if r["intention_id"] not in exclude
        ]
```

**References**:

- GAP Section 6: [Rich LLM Context](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#6-recommended-architecture-inline-vectors--entity-graph)

**Acceptance Criteria**:

- [ ] Fetches from all 5 relevant layers
- [ ] Uses JSON containment for participants_json
- [ ] Excludes already-matched records
- [ ] Limits records per layer
- [ ] Returns structured RelatedContext
- [ ] Integration tests

---

### Issue 5.4: Create ContextExpander Orchestrator

**Priority**: P0
**Effort**: 2 hours

**Description**:
Create orchestrator that coordinates the full context expansion flow.

**Files to Create**:

- `k0/modules/recall/context_expander.py` (NEW)

**Code Structure**:

```python
"""
ContextExpander — GAP-001 Implementation

Orchestrates the full context expansion flow:
1. Vector search → direct matches
2. Entity extraction from matches
3. Entity graph expansion
4. Related context fetching
5. Structured response assembly

GAP Reference: GAP_001 Section 6 (P01 Recall Flow)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
import numpy as np

from .entity_extractor import EntityExtractor
from .entity_graph_expander import EntityGraphExpander, ExpansionResult
from .related_context_fetcher import RelatedContextFetcher, RelatedContext
from k0.modules.embedding.union_index_searcher import SearchResult


@dataclass
class ExpandedContext:
    """Full context for LLM consumption."""
    direct_matches: List[Dict] = field(default_factory=list)
    related_context: Optional[RelatedContext] = None
    entity_expansion: Optional[ExpansionResult] = None
    query_text: str = ""
    total_records: int = 0

    def to_llm_context(self) -> Dict:
        """Format for LLM prompt."""
        result = {
            "query": self.query_text,
            "direct_matches": self.direct_matches,
            "total_context_records": self.total_records,
        }

        if self.related_context:
            result.update(self.related_context.to_dict())

        if self.entity_expansion:
            result["expanded_entities"] = [
                {
                    "id": e.entity_id,
                    "name": e.canonical_name,
                    "type": e.entity_type,
                    "hop": e.hop_distance,
                }
                for e in self.entity_expansion.entities
            ]

        return result


class ContextExpander:
    """Orchestrates context expansion for P01 recall."""

    def __init__(
        self,
        searcher,  # UnionIndexSearcher
        max_hops: int = 1,
        min_edge_weight: float = 0.5,
        max_related_per_layer: int = 10,
    ):
        """
        Initialize expander.

        Args:
            searcher: FAISS union index searcher
            max_hops: Graph traversal depth
            min_edge_weight: Minimum edge weight
            max_related_per_layer: Related records limit
        """
        self._searcher = searcher
        self._entity_extractor = EntityExtractor()
        self._graph_expander = EntityGraphExpander(
            max_hops=max_hops,
            min_edge_weight=min_edge_weight,
        )
        self._context_fetcher = RelatedContextFetcher(
            max_per_layer=max_related_per_layer,
        )

    async def expand(
        self,
        query_vector: np.ndarray,
        query_text: str,
        conn,
        k: int = 20,
        tenant_id: Optional[str] = None,
        space_id: Optional[str] = None,
    ) -> ExpandedContext:
        """
        Full context expansion flow.

        Args:
            query_vector: 768-dim query embedding
            query_text: Original query text
            conn: Database connection
            k: Number of vector search results
            tenant_id: Tenant filter
            space_id: Space filter

        Returns:
            ExpandedContext with full LLM context
        """
        # Step 1: Vector search
        search_results = self._searcher.search(
            query_vector,
            k=k,
            tenant_id=tenant_id,
            space_id=space_id,
        )

        if not search_results:
            return ExpandedContext(query_text=query_text)

        # Step 2: Fetch direct match records
        direct_matches = await self._fetch_direct_matches(
            search_results, conn
        )

        # Step 3: Extract entities from direct matches
        records_by_id = {m["record_id"]: m for m in direct_matches}
        extraction = self._entity_extractor.extract_from_search_results(
            [(r.layer, r.record_id, r.score) for r in search_results],
            records_by_id,
        )

        # Step 4: Expand via entity graph
        expansion = await self._graph_expander.expand(
            extraction.entity_ids,
            conn,
            tenant_id,
        )

        # Step 5: Fetch related context
        all_entity_ids = {e.entity_id for e in expansion.entities}
        exclude_ids = {r.record_id for r in search_results}

        related = await self._context_fetcher.fetch(
            all_entity_ids,
            conn,
            tenant_id,
            exclude_record_ids=exclude_ids,
        )

        # Calculate total
        total = len(direct_matches)
        total += len(related.episodes)
        total += len(related.patterns)
        total += len(related.routines)
        total += len(related.relationships)
        total += len(related.intentions)

        return ExpandedContext(
            direct_matches=direct_matches,
            related_context=related,
            entity_expansion=expansion,
            query_text=query_text,
            total_records=total,
        )

    async def _fetch_direct_matches(
        self,
        results: List[SearchResult],
        conn,
    ) -> List[Dict]:
        """Fetch full records for direct vector matches."""
        matches = []

        # Group by layer for efficient queries
        by_layer: Dict[str, List[str]] = {}
        for r in results:
            if r.layer not in by_layer:
                by_layer[r.layer] = []
            by_layer[r.layer].append(r.record_id)

        # Fetch from each layer
        pk_columns = {
            "st_epi": "episode_id",
            "st_sem": "pattern_id",
            "st_procedural": "routine_id",
            "st_social": "relationship_id",
            "st_prospective": "intention_id",
            "st_kg_dom": "entity_id",
        }

        for layer, record_ids in by_layer.items():
            pk = pk_columns.get(layer, "id")
            rows = await conn.fetch(
                f"""
                SELECT *, '{layer}' as source_layer
                FROM {layer}
                WHERE {pk} = ANY($1)
                """,
                record_ids,
            )
            for row in rows:
                match = dict(row)
                match["record_id"] = match[pk]
                # Find score from results
                for r in results:
                    if r.layer == layer and r.record_id == match[pk]:
                        match["similarity_score"] = r.score
                        break
                matches.append(match)

        # Sort by similarity score
        matches.sort(key=lambda m: m.get("similarity_score", 0), reverse=True)

        return matches
```

**References**:

- GAP Section 6: [P01 Recall Flow](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#p01-recall--major-update)

**Acceptance Criteria**:

- [ ] Coordinates full expansion flow
- [ ] Returns ExpandedContext with all components
- [ ] Formats for LLM consumption
- [ ] Handles empty results
- [ ] Integration tests

---

### Issue 5.5: Update P01 Recall Phase

**Priority**: P0
**Effort**: 2 hours

**Description**:
Update P01 recall phase to use ContextExpander for rich context retrieval.

**Files to Modify**:

- `k0/pipelines/p01/phases/recall.py` (MODIFY)

**Changes Required**:

1. Import ContextExpander
2. Use union index search instead of st_vec search
3. Call ContextExpander for entity graph expansion
4. Return ExpandedContext to orchestrator

**Integration Point**:

```python
# Before (st_vec only):
results = await syscalls.vec_search(query_vec, k=20)

# After (union index + expansion):
from k0.modules.recall.context_expander import ContextExpander
from k0.modules.embedding.union_index_manager import UnionIndexManager

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

**References**:

- GAP Section 7: [P01 Recall Major Update](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#p01-recall--major-update)
- Existing: `k0/pipelines/p01/phases/recall.py`

**Acceptance Criteria**:

- [ ] Uses union index for vector search
- [ ] Integrates ContextExpander
- [ ] Returns rich context to orchestrator
- [ ] Backwards compatible with old interface
- [ ] Integration tests

---

### Issue 5.6: Register Context Expansion Syscalls

**Priority**: P1
**Effort**: 1 hour

**Description**:
Register syscalls for context expansion operations.

**Files to Modify**:

- `k0/kernel/syscalls.py` (MODIFY)

**New Syscalls**:

```python
async def context_expand(
    self,
    query_vector: list,
    query_text: str,
    k: int = 20,
    max_hops: int = 1,
    tenant_id: str = None,
    space_id: str = None,
) -> dict:
    """
    Expand context via vector search + entity graph.

    Returns:
        {
            "direct_matches": [...],
            "related_episodes": [...],
            "actor_patterns": [...],
            ...
        }
    """
```

**References**:

- Existing syscalls: [syscalls.py](../../k0/kernel/syscalls.py)

**Acceptance Criteria**:

- [ ] `context_expand` syscall registered
- [ ] Capability checks in place
- [ ] Unit tests

---

### Issue 5.7: Unit Tests for Context Expansion

**Priority**: P1
**Effort**: 3 hours

**Description**:
Create unit tests for all context expansion components.

**Files to Create**:

- `tests/k0/modules/recall/test_entity_extractor.py` (NEW)
- `tests/k0/modules/recall/test_entity_graph_expander.py` (NEW)
- `tests/k0/modules/recall/test_related_context_fetcher.py` (NEW)
- `tests/k0/modules/recall/test_context_expander.py` (NEW)

**Test Cases**:

1. EntityExtractor handles all column patterns
2. EntityExtractor deduplicates correctly
3. EntityGraphExpander traverses edges
4. EntityGraphExpander respects min_edge_weight
5. RelatedContextFetcher excludes direct matches
6. ContextExpander full flow
7. Empty results handling
8. Performance: <200ms for typical query

**Acceptance Criteria**:

- [ ] All test cases pass
- [ ] 80%+ code coverage
- [ ] Performance assertions included

---

## Dependency Graph

```
┌──────────────────────────────────────────────────────────────┐
│                    ISSUE DEPENDENCIES                         │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  5.1 EntityExtractor ──────────┐                              │
│                                │                              │
│  5.2 EntityGraphExpander ──────┼──▶ 5.4 ContextExpander       │
│                                │              │               │
│  5.3 RelatedContextFetcher ────┘              │               │
│                                               │               │
│  Milestone 4 (UnionIndexSearcher) ───────────┘               │
│                                               │               │
│                                               ▼               │
│                                   5.5 P01 Recall Update       │
│                                               │               │
│                                               ▼               │
│                                   5.6 Syscalls                │
│                                               │               │
│                                               ▼               │
│                                   5.7 Unit Tests              │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Verification Checklist

After completing all issues:

- [ ] EntityExtractor handles all layer column patterns
- [ ] EntityGraphExpander traverses st_kg_edges
- [ ] RelatedContextFetcher queries all 5 layers
- [ ] ContextExpander returns complete LLM context
- [ ] P01 recall integrates with new flow
- [ ] All tests pass
- [ ] Performance: <200ms for typical query

---

## Files Created/Modified Summary

| File | Action | Issue |
|------|--------|-------|
| `k0/modules/recall/entity_extractor.py` | CREATE | 5.1 |
| `k0/modules/recall/entity_graph_expander.py` | CREATE | 5.2 |
| `k0/modules/recall/related_context_fetcher.py` | CREATE | 5.3 |
| `k0/modules/recall/context_expander.py` | CREATE | 5.4 |
| `k0/pipelines/p01/phases/recall.py` | MODIFY | 5.5 |
| `k0/kernel/syscalls.py` | MODIFY | 5.6 |
| `tests/k0/modules/recall/test_*.py` | CREATE | 5.7 |

---

## Next Milestone

After Milestone 5 is complete, proceed to:

- **Milestone 6: Backfill Existing Records** — Generate embeddings for NULL embedding_vector rows
