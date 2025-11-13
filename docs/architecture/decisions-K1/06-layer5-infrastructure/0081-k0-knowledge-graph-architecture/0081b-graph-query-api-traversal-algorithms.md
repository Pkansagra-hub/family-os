---
adr_number: '0081b'
title: Graph Query API & Traversal Algorithms
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k0.query.graph_api
- k0.kernel.knowledge_graph.traversal
- k0.kernel.knowledge_graph.query
- k1.l2_orchestration.retrieval
concerns:
- architecture
- performance
- privacy
- reliability
- testing
implementation_status: PLANNED
implementation_phase: Phase 2 (Query Infrastructure)
implementation_date: '2025-11-03'
propagation:
  affected_adrs:
  - ADR-0001
  - ADR-0081
  - ADR-0081a
  - ADR-0081b
  - ADR-0081c
  affected_contracts:
  - k0/contracts/api/graph/query_api.yml
  - k0/contracts/api/graph/traversal_spec.yml
  - k0/contracts/api/graph/temporal_query.yml
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  affected_tests:
  - tests/k0/query/test_graph_api.py
  - tests/k0/kernel/test_traversal_algorithms.py
  - tests/k0/query/test_temporal_queries.py
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
related_adrs:
- ADR-0001
- ADR-0081
- ADR-0081a
- ADR-0081b
- ADR-0081c
- ADR-0081d
related_contracts: []
related_diagrams:
- architecture_diagrams/k0/project_architecture_part2.mmd
- architecture_diagrams/k0/project_architecture_part4.mmd
research_citations:
- "Graph Query Languages (Angles et al., 2017)"
- "Efficient Graph Algorithms (Cormen et al., 2009)"
- "Temporal Graph Queries (Kostakos, 2009)"
---

﻿# ADR-0081b: Graph Query API & Traversal Algorithms

**Status:** Proposed
**Date:** 2025-10-22
**Parent ADR:** ADR-0081 (K0 Knowledge Graph Architecture)
**Implements:** Query API for K0::st_kg with temporal queries, entity lookup, relationship traversal

## Context

From **ADR-0081**, LLMs need **structured query API** to:

1. **Entity Lookup:** "Who is Alice?" â†’ retrieve entity with relationships + attributes
2. **Temporal Queries:** "Who got married in 2024?" â†’ event-based queries with timestamps
3. **Relationship Traversal:** "How is Bob related to Eve?" â†’ graph path algorithms (BFS/DFS)
4. **Performance:** <10ms P95 entity lookup, <50ms P95 graph queries

**From K0 Architecture Diagrams:**

- **D2 (project_architecture_part2.mmd):** `ret_kg_adapter` routes to K0::st_kg for knowledge graph queries
- **D4 (project_architecture_part4.mmd):** `KG_TEMPORAL_ENGINE` for temporal reasoning, `KG_CAUSAL_GRAPH` for relationship discovery
- **Query Port:** All KG queries go through K0 Query Port (ADR-0001), never direct access

**Key Requirements:**

- **Temporal Reasoning:** Query graph state at specific time (as_of parameter)
- **Relationship Evolution:** Track how relationships changed ("Who was Alice's employer in 2020?")
- **Path Finding:** Find shortest path between entities (max depth 6 hops)
- **Performance:** <50ms P95 for graph traversal (depth 6, 1000 nodes)

## Decision

Implement **k0/query/kg_temporal.py** with 4 query categories:

### 1. Entity Lookup API

```python
# k0/query/kg_temporal.py
from typing import Optional, List, Dict
from dataclasses import dataclass
import asyncio

@dataclass
class Entity:
    """Entity with relationships and properties."""
    node_id: str
    entity_type: str
    label: str
    properties: Dict
    relationships: List["Relationship"]
    created_at: int
    updated_at: int

@dataclass
class Relationship:
    """Relationship between entities."""
    edge_id: str
    source_id: str
    target_id: str
    rel_type: str
    valid_from: Optional[int]
    valid_to: Optional[int]
    confidence: float
    properties: Dict

async def get_entity(
    entity_id: str,
    as_of: Optional[int] = None,
    include_relationships: bool = True,
    max_relationship_depth: int = 1
) -> Optional[Entity]:
    """Retrieve entity by ID with optional temporal snapshot.

    Args:
        entity_id: Node ID to retrieve
        as_of: Unix timestamp (ms) for temporal snapshot (None = current)
        include_relationships: Include outgoing/incoming relationships
        max_relationship_depth: Depth of relationship traversal (1 = immediate neighbors)

    Returns:
        Entity with relationships or None if not found

    Performance: <10ms P95

    Example:
        # Get current state
        alice = await get_entity("node-alice")
        print(alice.label)  # "Alice"
        print(alice.relationships)  # [sister_of, married_to, employed_by, ...]

        # Get historical state (2020)
        alice_2020 = await get_entity("node-alice", as_of=1577836800000)
        print(alice_2020.relationships)  # [sister_of, employed_by] (not married yet)
    """
    # Implementation uses SQLiteKGDriver
    pass

async def find_entities(
    entity_type: Optional[str] = None,
    label_pattern: Optional[str] = None,
    properties: Optional[Dict] = None,
    limit: int = 100
) -> List[Entity]:
    """Find entities by type, label pattern, or properties.

    Args:
        entity_type: Filter by entity type (Person, Location, Event, Organization, Thing)
        label_pattern: SQL LIKE pattern (e.g., "Alice%", "%Smith")
        properties: JSON property filters (e.g., {"diet": "vegetarian", "city": "Seattle"})
        limit: Maximum number of results

    Returns:
        List of matching entities

    Performance: <50ms P95

    Example:
        # Find all vegetarians in Seattle
        vegetarians = await find_entities(
            entity_type="Person",
            properties={"diet": "vegetarian", "city": "Seattle"}
        )
    """
    pass

async def get_entity_by_label(
    label: str,
    entity_type: Optional[str] = None
) -> Optional[Entity]:
    """Retrieve entity by label (case-insensitive).

    Args:
        label: Display name (e.g., "Alice", "Mom", "Seattle")
        entity_type: Optional type filter

    Returns:
        Entity or None if not found (raises if multiple matches)

    Performance: <10ms P95

    Example:
        alice = await get_entity_by_label("Alice", entity_type="Person")
    """
    pass
```

### 2. Relationship Query API

```python
async def get_relationships(
    source_id: str,
    rel_type: Optional[str] = None,
    direction: str = "outgoing",  # outgoing, incoming, both
    as_of: Optional[int] = None,
    include_properties: bool = True
) -> List[Relationship]:
    """Get relationships for an entity.

    Args:
        source_id: Node ID
        rel_type: Filter by relationship type (None = all types)
        direction: outgoing (source â†’ target), incoming (target â†’ source), both
        as_of: Unix timestamp (ms) for temporal snapshot (None = current)
        include_properties: Include relationship properties

    Returns:
        List of relationships

    Performance: <30ms P95 (1 hop), <80ms P95 (3 hops)

    Example:
        # Get all of Alice's family relationships
        family = await get_relationships(
            "node-alice",
            rel_type="sister_of|parent|child",
            direction="both"
        )
    """
    pass

async def find_path(
    source_id: str,
    target_id: str,
    max_depth: int = 6,
    rel_types: Optional[List[str]] = None,
    as_of: Optional[int] = None
) -> List[List[Relationship]]:
    """Find shortest paths between entities (BFS).

    Args:
        source_id: Starting node ID
        target_id: Destination node ID
        max_depth: Maximum path length (default 6 hops)
        rel_types: Filter by relationship types (None = all types)
        as_of: Unix timestamp (ms) for temporal snapshot

    Returns:
        List of paths (each path is list of relationships), sorted by length

    Performance: <100ms P95 (depth 6, 1000 nodes)

    Example:
        # How is Bob related to Eve?
        paths = await find_path("node-bob", "node-eve", max_depth=6)
        if paths:
            shortest = paths[0]
            print(" â†’ ".join(rel.rel_type for rel in shortest))
            # Output: brother_of â†’ parent â†’ married_to
    """
    # BFS algorithm (see implementation below)
    pass

async def get_relationship_history(
    source_id: str,
    target_id: str,
    rel_type: str
) -> List[TemporalRelationship]:
    """Get version history of a relationship.

    Args:
        source_id: Source node ID
        target_id: Target node ID
        rel_type: Relationship type

    Returns:
        List of temporal relationships (all versions), sorted by valid_from DESC

    Performance: <30ms P95

    Example:
        # Get Alice's employment history
        history = await get_relationship_history(
            "node-alice",
            "node-microsoft",
            "employed_by"
        )
        for rel in history:
            print(f"{rel.valid_from} â†’ {rel.valid_to}: {rel.rel_type}")
        # Output:
        # 2018-01-01 â†’ 2023-01-01: employed_by
        # 2023-01-01 â†’ None: employed_by (Google)
    """
    pass
```

### 3. Temporal Query API

```python
async def get_events(
    event_type: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    entity_id: Optional[str] = None,
    limit: int = 100
) -> List[Event]:
    """Query events by type and time range.

    Args:
        event_type: Relationship type (married_to, employed_by, lives_in, etc.)
        start_time: Unix timestamp (ms) for range start (None = no lower bound)
        end_time: Unix timestamp (ms) for range end (None = no upper bound)
        entity_id: Filter by entity involvement (None = all entities)
        limit: Maximum number of results

    Returns:
        List of events (relationships that changed in time range)

    Performance: <50ms P95

    Example:
        # Who got married in 2024?
        marriages = await get_events(
            event_type="married_to",
            start_time=1704067200000,  # 2024-01-01
            end_time=1735689600000     # 2025-01-01
        )
        for marriage in marriages:
            print(f"{marriage.source_label} married {marriage.target_label} on {marriage.valid_from}")
    """
    pass

async def temporal_reachability(
    source_id: str,
    target_id: str,
    at_time: int,
    max_depth: int = 6
) -> bool:
    """Check if target was reachable from source at specific time.

    Args:
        source_id: Starting node ID
        target_id: Destination node ID
        at_time: Unix timestamp (ms) to check
        max_depth: Maximum path length

    Returns:
        True if reachable, False otherwise

    Performance: <100ms P95 (depth 6)

    Example:
        # Was Bob connected to Eve in 2020?
        connected = await temporal_reachability(
            "node-bob",
            "node-eve",
            at_time=1577836800000,  # 2020-01-01
            max_depth=6
        )
    """
    # Uses find_path with as_of parameter
    pass

async def get_timeline(
    entity_id: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    event_types: Optional[List[str]] = None
) -> List[TimelineEvent]:
    """Get entity's timeline (all relationship changes).

    Args:
        entity_id: Node ID
        start_time: Unix timestamp (ms) for range start (None = all history)
        end_time: Unix timestamp (ms) for range end (None = present)
        event_types: Filter by relationship types (None = all types)

    Returns:
        List of timeline events, sorted by timestamp DESC

    Performance: <50ms P95

    Example:
        # Get Alice's life timeline
        timeline = await get_timeline("node-alice")
        for event in timeline:
            print(f"{event.timestamp}: {event.rel_type} {event.target_label}")
        # Output:
        # 2023-01-01: employed_by Google
        # 2020-06-15: married_to Bob
        # 2018-01-01: employed_by Microsoft
    """
    pass
```

### 4. Graph Traversal API

```python
@dataclass
class TraversalSpec:
    """Specification for graph traversal."""
    max_depth: int = 6
    rel_types: Optional[List[str]] = None
    direction: str = "outgoing"  # outgoing, incoming, both
    stop_condition: Optional[callable] = None
    as_of: Optional[int] = None

async def traverse(
    start_id: str,
    traversal_spec: TraversalSpec
) -> List[Entity]:
    """Generic graph traversal with filters and limits.

    Args:
        start_id: Starting node ID
        traversal_spec: Traversal configuration

    Returns:
        List of reachable entities

    Performance: <100ms P95 (depth 6, 1000 nodes)

    Example:
        # Get all family members (depth 3)
        spec = TraversalSpec(
            max_depth=3,
            rel_types=["parent", "child", "sibling", "spouse"],
            direction="both"
        )
        family = await traverse("node-user", spec)
    """
    # BFS traversal (see implementation below)
    pass

async def get_neighbors(
    entity_id: str,
    depth: int = 1,
    rel_types: Optional[List[str]] = None,
    direction: str = "outgoing",
    as_of: Optional[int] = None
) -> Dict[int, List[Entity]]:
    """Get neighbors at specified depth.

    Args:
        entity_id: Starting node ID
        depth: Depth of traversal (1 = immediate neighbors, 2 = neighbors of neighbors)
        rel_types: Filter by relationship types (None = all types)
        direction: outgoing, incoming, both
        as_of: Unix timestamp (ms) for temporal snapshot

    Returns:
        Dict mapping depth â†’ list of entities at that depth

    Performance: <50ms P95 (depth 3)

    Example:
        # Get Alice's immediate family and extended family
        neighbors = await get_neighbors(
            "node-alice",
            depth=2,
            rel_types=["parent", "child", "sibling"],
            direction="both"
        )
        print(neighbors[1])  # Immediate family
        print(neighbors[2])  # Extended family (parents' siblings, siblings' children)
    """
    pass

async def get_subgraph(
    entity_ids: List[str],
    include_edges: bool = True,
    as_of: Optional[int] = None
) -> Dict:
    """Get subgraph containing specified entities and their relationships.

    Args:
        entity_ids: List of node IDs to include
        include_edges: Include edges between entities
        as_of: Unix timestamp (ms) for temporal snapshot

    Returns:
        Dict with "nodes" and "edges" keys (graph structure)

    Performance: <80ms P95 (100 entities)

    Example:
        # Get family subgraph
        family_ids = ["node-alice", "node-bob", "node-mom", "node-dad"]
        subgraph = await get_subgraph(family_ids, include_edges=True)
        # Export to Mermaid
        mermaid = export_to_mermaid(subgraph)
    """
    pass
```

## Graph Algorithms

### BFS (Breadth-First Search) for Shortest Path

```python
async def find_path_bfs(
    source_id: str,
    target_id: str,
    max_depth: int,
    rel_types: Optional[List[str]],
    as_of: Optional[int],
    kg_driver: SQLiteKGDriver
) -> List[List[Relationship]]:
    """BFS algorithm for shortest path.

    Time Complexity: O(V + E) where V = vertices, E = edges
    Space Complexity: O(V) for visited set + queue

    Performance: <100ms P95 (depth 6, 1000 nodes)
    """
    from collections import deque

    # Queue: (current_node, path, depth)
    queue = deque([(source_id, [], 0)])
    visited = {source_id}
    paths = []

    while queue:
        current, path, depth = queue.popleft()

        # Found target
        if current == target_id:
            paths.append(path)
            if len(paths) >= 5:  # Limit to 5 paths
                break
            continue

        # Max depth reached
        if depth >= max_depth:
            continue

        # Get neighbors
        relationships = await kg_driver.get_relationships(
            source_id=current,
            rel_types=rel_types,
            direction="outgoing",
            as_of=as_of
        )

        for rel in relationships:
            if rel.target_id not in visited:
                visited.add(rel.target_id)
                queue.append((rel.target_id, path + [rel], depth + 1))

    return paths

# Performance optimization: Bidirectional BFS for long paths
async def find_path_bidirectional_bfs(
    source_id: str,
    target_id: str,
    max_depth: int,
    rel_types: Optional[List[str]],
    as_of: Optional[int],
    kg_driver: SQLiteKGDriver
) -> List[List[Relationship]]:
    """Bidirectional BFS for faster long-path queries.

    Searches from both source and target simultaneously, meeting in the middle.

    Time Complexity: O(2 * b^(d/2)) vs O(b^d) for standard BFS
    where b = branching factor, d = depth

    Performance: ~2Ã— faster for depth > 4
    """
    # Implementation: Two BFS queues (forward + backward)
    pass
```

### DFS (Depth-First Search) for All Paths

```python
async def find_all_paths_dfs(
    source_id: str,
    target_id: str,
    max_depth: int,
    rel_types: Optional[List[str]],
    as_of: Optional[int],
    kg_driver: SQLiteKGDriver
) -> List[List[Relationship]]:
    """DFS algorithm for finding all paths (not just shortest).

    Use case: "Show me ALL ways Bob is related to Eve"

    Time Complexity: O(V + E) with cycle detection
    Performance: <200ms P95 (depth 6, 1000 nodes, up to 100 paths)
    """
    async def dfs(current: str, target: str, path: List[Relationship], visited: set, depth: int):
        if current == target:
            return [path]

        if depth >= max_depth:
            return []

        paths = []
        relationships = await kg_driver.get_relationships(
            source_id=current,
            rel_types=rel_types,
            direction="outgoing",
            as_of=as_of
        )

        for rel in relationships:
            if rel.target_id not in visited:
                visited.add(rel.target_id)
                found_paths = await dfs(rel.target_id, target, path + [rel], visited, depth + 1)
                paths.extend(found_paths)
                visited.remove(rel.target_id)

        return paths

    return await dfs(source_id, target_id, [], {source_id}, 0)
```

### Temporal Reachability (Time-Aware BFS)

```python
async def temporal_reachability_bfs(
    source_id: str,
    target_id: str,
    at_time: int,
    max_depth: int,
    kg_driver: SQLiteKGDriver
) -> bool:
    """Check if target was reachable from source at specific time.

    Key difference from standard BFS: Filters edges by valid_from/valid_to

    Performance: <100ms P95 (depth 6)
    """
    from collections import deque

    queue = deque([(source_id, 0)])
    visited = {source_id}

    while queue:
        current, depth = queue.popleft()

        if current == target_id:
            return True

        if depth >= max_depth:
            continue

        # Get relationships valid at at_time
        relationships = await kg_driver.get_relationships(
            source_id=current,
            as_of=at_time  # Key: temporal filter
        )

        for rel in relationships:
            if rel.target_id not in visited:
                visited.add(rel.target_id)
                queue.append((rel.target_id, depth + 1))

    return False
```

## Performance Optimization

### 1. Caching Strategy

```python
from functools import lru_cache
import asyncio

# LRU cache for entity lookup (1000 entities, ~10 MB)
@lru_cache(maxsize=1000)
async def cached_get_entity(entity_id: str) -> Optional[Entity]:
    """Cached entity lookup (TTL: 60 seconds)."""
    return await get_entity(entity_id)

# Cache invalidation on entity update
async def update_entity(entity_id: str, properties: Dict):
    await kg_driver.update_node(entity_id, properties)
    cached_get_entity.cache_clear()  # Invalidate cache
```

### 2. Batch Queries

```python
async def get_entities_batch(entity_ids: List[str]) -> Dict[str, Entity]:
    """Batch entity lookup (single query).

    Performance: 10Ã— faster than N individual queries
    """
    query = f"""
        SELECT node_id, entity_type, label, properties, created_at, updated_at
        FROM kg_nodes
        WHERE node_id IN ({','.join('?' * len(entity_ids))})
    """
    rows = await kg_driver.execute_query(query, entity_ids)
    return {row['node_id']: Entity(**row) for row in rows}
```

### 3. Index Optimization

```sql
-- Covering index for relationship traversal (avoids table lookup)
CREATE INDEX idx_kg_edges_traversal ON kg_edges(
    source_id, rel_type, target_id, valid_from, valid_to
);

-- Covering index for temporal queries
CREATE INDEX idx_kg_edges_temporal ON kg_edges(
    valid_from, valid_to, rel_type
) WHERE valid_from IS NOT NULL;
```

### 4. Query Planner Hints

```python
# Use SQLite query planner hints for complex queries
query = f"""
    SELECT * FROM kg_edges
    INDEXED BY idx_kg_edges_traversal
    WHERE source_id = ? AND rel_type IN (?, ?, ?)
"""
```

## Integration with K0 Query Port

```python
# k0/ports/query.py
class QueryPort:
    """K0 Query Port (ADR-0001)."""

    async def recall(
        self,
        query_type: str,
        **params
    ) -> Any:
        """Query K0 storage via ports."""

        if query_type == "kg_entity":
            return await kg_temporal.get_entity(params["entity_id"])

        elif query_type == "kg_relationship":
            return await kg_temporal.get_relationships(
                source_id=params["source_id"],
                rel_type=params.get("rel_type"),
                direction=params.get("direction", "outgoing")
            )

        elif query_type == "kg_path":
            return await kg_temporal.find_path(
                source_id=params["source_id"],
                target_id=params["target_id"],
                max_depth=params.get("max_depth", 6)
            )

        elif query_type == "kg_events":
            return await kg_temporal.get_events(
                event_type=params["event_type"],
                start_time=params.get("start_time"),
                end_time=params.get("end_time")
            )

        else:
            raise ValueError(f"Unknown query_type: {query_type}")
```

## Consequences

### Positive

1. **âœ… Fast Entity Lookup:** <10ms P95 (indexed queries)
2. **âœ… Fast Relationship Queries:** <30ms P95 (1 hop), <80ms P95 (3 hops)
3. **âœ… Shortest Path:** <100ms P95 (BFS, depth 6, 1000 nodes)
4. **âœ… Temporal Reasoning:** Query graph state at any point in time
5. **âœ… Flexible Traversal:** Generic traversal API with filters
6. **âœ… Batch Queries:** 10Ã— faster for multiple entity lookups
7. **âœ… Caching:** LRU cache reduces repeated queries

### Negative

1. **âŒ Graph Complexity:** Large graphs (10000+ edges) may exceed P95 targets
2. **âŒ Deep Traversal:** Depth > 6 hops can be slow (exponential growth)
3. **âŒ Cache Invalidation:** Complex invalidation logic for entity updates
4. **âŒ Memory Usage:** LRU cache uses ~10 MB for 1000 entities

### Mitigations

1. **Graph Complexity:** Use bidirectional BFS for long paths (2Ã— speedup)
2. **Deep Traversal:** Limit max_depth to 6 hops (reasonable for family graphs)
3. **Cache Invalidation:** TTL-based expiration (60 seconds) + manual invalidation
4. **Memory Usage:** Configurable cache size (default 1000 entities)

## Implementation Notes

### SQLiteKGDriver Integration

```python
# k0/drivers/sqlite_kg.py
class SQLiteKGDriver:
    """SQLite-backed knowledge graph driver."""

    async def get_relationships(
        self,
        source_id: str,
        rel_types: Optional[List[str]] = None,
        direction: str = "outgoing",
        as_of: Optional[int] = None
    ) -> List[Relationship]:
        """Get relationships for entity (optimized query)."""

        # Build query with temporal filtering
        query = """
            SELECT edge_id, source_id, target_id, rel_type, valid_from, valid_to, confidence, properties
            FROM kg_edges
            WHERE {direction_filter}
        """

        if direction == "outgoing":
            query = query.format(direction_filter="source_id = ?")
            params = [source_id]
        elif direction == "incoming":
            query = query.format(direction_filter="target_id = ?")
            params = [source_id]
        else:  # both
            query = query.format(direction_filter="(source_id = ? OR target_id = ?)")
            params = [source_id, source_id]

        # Add rel_type filter
        if rel_types:
            placeholders = ','.join('?' * len(rel_types))
            query += f" AND rel_type IN ({placeholders})"
            params.extend(rel_types)

        # Add temporal filter
        if as_of is not None:
            query += " AND (valid_from IS NULL OR valid_from <= ?) AND (valid_to IS NULL OR valid_to >= ?)"
            params.extend([as_of, as_of])

        # Execute query
        rows = await self.execute_query(query, params)
        return [Relationship(**row) for row in rows]
```

## Validation & Testing

### Query API Tests

```python
# tests/k0/query/test_kg_temporal.py
import ward
from k0.query.kg_temporal import get_entity, find_path, get_events

async def test_get_entity():
    alice = await get_entity("node-alice")
    assert alice.label == "Alice"
    assert alice.entity_type == "Person"
    assert len(alice.relationships) > 0

async def test_find_path_shortest():
    paths = await find_path("node-bob", "node-eve", max_depth=6)
    assert len(paths) > 0
    assert len(paths[0]) <= 6  # Shortest path within depth limit

async def test_temporal_query():
    marriages_2024 = await get_events(
        event_type="married_to",
        start_time=1704067200000,  # 2024-01-01
        end_time=1735689600000     # 2025-01-01
    )
    assert all(m.rel_type == "married_to" for m in marriages_2024)
```

### Performance Tests

```python
# tests/k0/query/test_kg_temporal_performance.py
import ward
import time

async def test_entity_lookup_performance():
    # Setup: 1000 entities
    # ...

    start = time.perf_counter()
    for i in range(100):
        await get_entity(f"node-person{i}")
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Verify <10ms P95
    assert elapsed_ms / 100 < 10, f"Entity lookup too slow: {elapsed_ms/100:.2f}ms"

async def test_find_path_performance():
    # Setup: 1000 entities, 10000 edges
    # ...

    start = time.perf_counter()
    paths = await find_path("node-person0", "node-person999", max_depth=6)
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Verify <100ms P95
    assert elapsed_ms < 100, f"Path finding too slow: {elapsed_ms:.2f}ms"
```

## References

**Research:**
- [1] Graph Algorithms: BFS, DFS, Dijkstra (MIT OpenCourseWare)
- [2] Temporal Graph Databases: Survey (ACM Computing Surveys)
- [3] SQLite Query Optimization (SQLite Documentation)
- [4] Neo4j Cypher Query Language (graph query patterns)

**Related ADRs:**
- ADR-0081: K0 Knowledge Graph Architecture (parent)
- ADR-0081a: Temporal Graph Schema Design
- ADR-0081c: Episodic Memory â†’ KG Integration
- ADR-0001: K0/K1 Kernel Split (Query Port)

**Implementation Files:**
- `k0/query/kg_temporal.py`: Query API implementation
- `k0/kg/traversal.py`: Graph traversal algorithms
- `k0/drivers/sqlite_kg.py`: SQLiteKGDriver with query methods

---

**Status:** Proposed (2025-10-22)
**Next Steps:**
1. Implement query API in k0/query/kg_temporal.py
2. Implement BFS/DFS algorithms in k0/kg/traversal.py
3. Write query API tests
4. Write performance tests
5. Integrate with K0 Query Port
