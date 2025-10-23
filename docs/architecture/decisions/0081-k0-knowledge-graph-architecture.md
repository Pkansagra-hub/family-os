# ADR-0081: K0 Knowledge Graph Architecture

**Status:** Proposed
**Date:** 2025-10-22
**Priority:** P1 - CRITICAL GAP (Blocks 2 capabilities: #21 Family Identity Graph, #38 Temporal KG Queries)
**Blocks:** #21 (Family Identity Graph), #38 (Temporal KG Queries)
**Effort:** 10-12 weeks implementation
**Related ADRs:** ADR-0001 (K0/K1 Kernel Split), ADR-0004 (56-Module Architecture), ADR-00XX (P03 Consolidation), ADR-00XX (P06 Learning), ADR-00XX (P19 Personalization)
**Sub-ADRs:** ADR-0081a (Temporal Graph Schema), ADR-0081b (Query API & Traversal), ADR-0081c (Episodic Integration), ADR-0081d (Visualization & Debugging)

## Context

### The Problem

**Current State:** K0 Memory (FTS5 + FAISS) stores **unstructured text** ("Alice visited last Tuesday").
**Missing:** **Structured relationships** (Alice --[sister_of]--> Mom, Alice --[lives_in]--> Seattle).

LLMs need **explicit graph structure** for:
1. **Relationship Queries:** "Who is Alice?" → structured response, not fuzzy text matching
2. **Temporal Queries:** "Who got married last year?" → event-based queries with timestamps
3. **Relationship Traversal:** "How is Bob related to Eve?" → graph path algorithms, not text inference

**From K0 Architecture Diagrams Analysis:**

**Diagram 1 (project_architecture_part1.mmd):**
- **Current:** 7 memory types (episodic, semantic, procedural, snapshots, affect, self-model, social)
- **Missing:** 8th memory type: **knowledge_graph** for structured family relationships
- **Storage:** K0_DRIVERS defines `st_kg["Knowledge Graph"]:::storage` but **placeholder only** (9 lines, NotImplementedError)
- **Integration:** K0 Bus → Pipelines P01-P20, but **no KG-specific pipeline handlers**

**Diagram 2 (project_architecture_part2.mmd):**
- **K0::st_kg references:** Used in cognitive retrieval but **no driver implementation**
- **Storage mapping:** `ret_kg_adapter-->st_kg_dom` but backend is **NotImplementedError**

**Diagram 3 (project_architecture_part3.mmd):**
- **Social Cognition:** `SOC_RELATIONS-->ST_SOCIAL` → should be `K0::st_kg[relationships]`
- **TOM_BELIEFS** (Theory of Mind) → should query `K0::st_kg[social_beliefs]`
- **Missing:** Structured family relationship graph for social intelligence

**Diagram 4 (project_architecture_part4.mmd):**
- **K0_KG_INFRASTRUCTURE** defined with:
  - `KG_TEMPORAL_ENGINE` (temporal reasoning)
  - `KG_CAUSAL_GRAPH` (causal relationships)
  - `KG_RELATION_DISCOVERY` (relationship discovery)
  - `KG_VERSION_CONTROL` (knowledge versioning)
  - `KG_CONCEPT_EVOLUTION` (concept evolution tracking)
  - **But:** All reference `K0::st_kg` which is **NotImplementedError placeholder**

**Architecture Gap:** K0 has **scaffolding** for KG (diagram references, driver placeholder, infrastructure modules), but **no implementation**. This is the **BIGGEST ARCHITECTURAL GAP** blocking family personalization.

### Why LLMs Need Knowledge Graphs

**Scenario 1: Relationship Queries**
```
User: "Remind me who Alice is?"

WITHOUT Knowledge Graph:
LLM → searches K0 memory for "Alice" → finds 50 mentions → summarizes "Alice visited, likes coffee, vegetarian"
Problem: No structured relationship data, must infer from text

WITH Knowledge Graph:
LLM → queries KG: GET_ENTITY("Alice") → returns structured data:
{
  "name": "Alice",
  "relationships": [
    {"type": "sister_of", "target": "Mom", "confidence": 1.0},
    {"type": "lives_in", "target": "Seattle", "since": "2018"},
    {"type": "employed_by", "target": "Microsoft", "from": "2020", "to": "2023"}
  ],
  "attributes": {
    "diet": "vegetarian",
    "visit_frequency": "quarterly"
  }
}
LLM generates: "Alice is Mom's sister. She lives in Seattle and works at Microsoft. She's vegetarian and visits about once per quarter."
```

**Scenario 2: Temporal Queries**
```
User: "Who got married last year?"

WITHOUT Knowledge Graph:
LLM → searches memory for "married" + "2024" → finds partial mentions → may miss some events

WITH Knowledge Graph:
LLM → queries KG: GET_EVENTS(type="marriage", year=2024) → returns:
[
  {"person": "Bob", "spouse": "Carol", "date": "2024-06-15"},
  {"person": "Dave", "spouse": "Eve", "date": "2024-09-20"}
]
LLM generates: "Bob married Carol in June, and Dave married Eve in September."
```

**Scenario 3: Relationship Traversal**
```
User: "How is Bob related to Eve?"

WITHOUT Knowledge Graph:
LLM → searches memory → must infer from conversation text → error-prone

WITH Knowledge Graph:
LLM → queries KG: FIND_PATH("Bob", "Eve") → returns:
Bob --[brother_of]--> Alice --[sister_of]--> Mom --[parent_of]--> User --[married_to]--> Dave --[married_to]--> Eve
LLM generates: "Bob is your uncle (Mom's brother-in-law through Alice), and Eve is your spouse's new wife."
```

## Decision

Implement **K0 Knowledge Graph Architecture** as the **8th memory type** in K0, providing:

1. **Temporal Graph Schema:** Nodes (entities), Edges (relationships with timestamps), Properties (attributes with version history)
2. **SQLite Graph Storage:** K0::st_kg driver with nodes table, edges table, temporal_edges table
3. **Query API:** k0/query/kg_temporal.py with timeline queries, entity lookup, relationship traversal
4. **Integration:** Convert conversations to KG entities (episodic memory → KG via P03 Consolidation)
5. **Algorithms:** Shortest path, temporal reachability, relationship evolution tracking
6. **Visualization:** Export to Mermaid/GraphML for debugging

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  K0 Knowledge Graph Architecture                                │
│  (8th Memory Type: knowledge_graph)                             │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│  User Query          │ "Who is Alice?"
└──────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  K1 Planner (D3 Intelligence)                                │
│  - Decides: Need family context                              │
│  - Generates query: GET_ENTITY("Alice")                      │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  K0 Query Port (ADR-0001)                                    │
│  - Receives: recall(query_type="kg_entity", entity="Alice") │
│  - Routes to: k0/query/kg_temporal.py                       │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  k0/query/kg_temporal.py (Query API - ADR-0081b)            │
│  - Entity lookup: <10ms P95                                  │
│  - Relationship queries: <50ms P95                           │
│  - Temporal queries: <50ms P95                               │
│  - Graph traversal: <100ms P95                               │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  K0::st_kg Driver (k0/drivers/sqlite_kg.py)                 │
│  - Storage: SQLite graph schema                              │
│  - Tables: nodes, edges, temporal_edges, properties          │
│  - Indexes: entity_id, relationship_type, timestamp          │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  SQLite Database (K0::st_kg)                                 │
│  - nodes:   entity_id, entity_type, label, properties        │
│  - edges:   source_id, target_id, rel_type, valid_from/to   │
│  - temporal_edges: edge history, version tracking            │
│  - properties: attribute key/value pairs, version history    │
└──────────────────────────────────────────────────────────────┘
           │
           ▼ (Returns structured data)
┌──────────────────────────────────────────────────────────────┐
│  K1 LLM Response Generation                                  │
│  - Input: Structured KG data                                 │
│  - Output: Natural language response                         │
│  - "Alice is Mom's sister. She lives in Seattle..."          │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  Knowledge Graph Population (ADR-0081c)                      │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Episodic Memory (K0::st_sqlite[episodic_memories])    │ │
│  │  - "Alice visited last Tuesday"                         │ │
│  └─────────────────────────────────────────────────────────┘ │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  K0 P03 Consolidation Pipeline (D4)                    │ │
│  │  - Triggers: Episodic → KG transformation               │ │
│  │  - Handlers: k0/kg/episodic_integration.py             │ │
│  └─────────────────────────────────────────────────────────┘ │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Entity Extraction (k0/kg/entity_extractor.py)         │ │
│  │  - NER (Named Entity Recognition)                       │ │
│  │  - Entity resolution & disambiguation                   │ │
│  │  - Confidence scoring                                    │ │
│  └─────────────────────────────────────────────────────────┘ │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Relationship Extraction                                │ │
│  │  - Relationship detection (sister_of, lives_in, etc.)  │ │
│  │  - Temporal extraction (since, from, to timestamps)    │ │
│  │  - Confidence scoring                                    │ │
│  └─────────────────────────────────────────────────────────┘ │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  K0 Command Port → K0::st_kg                           │ │
│  │  - Insert/update entities                               │ │
│  │  - Create relationships                                  │ │
│  │  - Version tracking                                      │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Graph Schema (ADR-0081a)

**Temporal Graph Design:**

1. **Nodes (Entities):**
   ```sql
   CREATE TABLE kg_nodes (
       node_id TEXT PRIMARY KEY,           -- UUID
       entity_type TEXT NOT NULL,          -- Person, Location, Event, Organization, Thing
       label TEXT NOT NULL,                -- Display name
       created_at INTEGER NOT NULL,        -- Unix timestamp
       updated_at INTEGER NOT NULL,        -- Unix timestamp
       properties BLOB                     -- JSON properties
   );

   CREATE INDEX idx_kg_nodes_type ON kg_nodes(entity_type);
   CREATE INDEX idx_kg_nodes_label ON kg_nodes(label);
   ```

2. **Edges (Relationships):**
   ```sql
   CREATE TABLE kg_edges (
       edge_id TEXT PRIMARY KEY,           -- UUID
       source_id TEXT NOT NULL,            -- References kg_nodes(node_id)
       target_id TEXT NOT NULL,            -- References kg_nodes(node_id)
       rel_type TEXT NOT NULL,             -- Relationship type
       valid_from INTEGER,                 -- Unix timestamp (null = always valid)
       valid_to INTEGER,                   -- Unix timestamp (null = still valid)
       confidence REAL DEFAULT 1.0,        -- 0.0 to 1.0
       properties BLOB,                    -- JSON properties
       created_at INTEGER NOT NULL,
       FOREIGN KEY(source_id) REFERENCES kg_nodes(node_id) ON DELETE CASCADE,
       FOREIGN KEY(target_id) REFERENCES kg_nodes(node_id) ON DELETE CASCADE
   );

   CREATE INDEX idx_kg_edges_source ON kg_edges(source_id);
   CREATE INDEX idx_kg_edges_target ON kg_edges(target_id);
   CREATE INDEX idx_kg_edges_rel_type ON kg_edges(rel_type);
   CREATE INDEX idx_kg_edges_valid_from ON kg_edges(valid_from);
   CREATE INDEX idx_kg_edges_valid_to ON kg_edges(valid_to);
   ```

3. **Temporal Edges (Version History):**
   ```sql
   CREATE TABLE kg_temporal_edges (
       version_id TEXT PRIMARY KEY,        -- UUID
       edge_id TEXT NOT NULL,              -- References kg_edges(edge_id)
       version INTEGER NOT NULL,           -- Version number
       valid_from INTEGER NOT NULL,        -- Timestamp when this version became valid
       valid_to INTEGER,                   -- Timestamp when superseded (null = current)
       rel_type TEXT NOT NULL,             -- Relationship type at this version
       properties BLOB,                    -- JSON properties at this version
       confidence REAL DEFAULT 1.0,
       created_at INTEGER NOT NULL,
       FOREIGN KEY(edge_id) REFERENCES kg_edges(edge_id) ON DELETE CASCADE
   );

   CREATE INDEX idx_kg_temporal_edges_edge ON kg_temporal_edges(edge_id);
   CREATE INDEX idx_kg_temporal_edges_valid FROM kg_temporal_edges(valid_from);
   ```

**Entity Types:**

- **Person:** Family members, friends, colleagues, contacts
- **Location:** Home, work, cities, places visited, landmarks
- **Event:** Weddings, births, graduations, trips, milestones
- **Organization:** Employers, schools, clubs, institutions
- **Thing:** Pets, cars, devices, possessions

**Relationship Types (Extensible):**

| Category | Relationship Types |
|----------|-------------------|
| **Family** | parent, child, sibling, spouse, grandparent, grandchild, aunt, uncle, cousin, in_law |
| **Social** | friend, colleague, acquaintance, neighbor, mentor, mentee |
| **Employment** | employed_by, manages, reports_to, colleague_at |
| **Location** | lives_in, works_at, visits, born_in, studied_at |
| **Temporal** | married_to, divorced_from, dated, transitioned_to |
| **Affiliation** | member_of, attends, affiliated_with, graduated_from |
| **Ownership** | owns, possesses, responsible_for |
| **Event** | participated_in, attended, organized, hosted |

**Properties (JSON Schema):**

```json
{
  "properties": {
    "name": {"type": "string"},
    "age": {"type": "integer"},
    "birthday": {"type": "string", "format": "date"},
    "email": {"type": "string", "format": "email"},
    "phone": {"type": "string"},
    "address": {"type": "string"},
    "occupation": {"type": "string"},
    "diet": {"type": "string", "enum": ["omnivore", "vegetarian", "vegan", "pescatarian", "gluten_free"]},
    "allergies": {"type": "array", "items": {"type": "string"}},
    "preferences": {"type": "object"},
    "notes": {"type": "string"}
  }
}
```

### Query API (ADR-0081b)

**k0/query/kg_temporal.py** provides:

1. **Entity Lookup:**
   ```python
   async def get_entity(entity_id: str, as_of: Optional[int] = None) -> Optional[Entity]:
       """Retrieve entity by ID with optional temporal snapshot.

       Performance: <10ms P95
       """

   async def find_entities(
       entity_type: Optional[str] = None,
       label_pattern: Optional[str] = None,
       properties: Optional[Dict] = None,
       limit: int = 100
   ) -> List[Entity]:
       """Find entities by type, label pattern, or properties.

       Performance: <50ms P95
       """
   ```

2. **Relationship Queries:**
   ```python
   async def get_relationships(
       source_id: str,
       rel_type: Optional[str] = None,
       direction: str = "outgoing",  # outgoing, incoming, both
       as_of: Optional[int] = None
   ) -> List[Relationship]:
       """Get relationships for an entity.

       Performance: <50ms P95
       """

   async def find_path(
       source_id: str,
       target_id: str,
       max_depth: int = 6,
       rel_types: Optional[List[str]] = None
   ) -> List[List[Relationship]]:
       """Find shortest paths between entities (BFS).

       Performance: <100ms P95 (depth 6)
       """
   ```

3. **Temporal Queries:**
   ```python
   async def get_events(
       event_type: str,
       start_time: Optional[int] = None,
       end_time: Optional[int] = None,
       entity_id: Optional[str] = None,
       limit: int = 100
   ) -> List[Event]:
       """Query events by type and time range.

       Performance: <50ms P95
       """

   async def get_relationship_history(
       source_id: str,
       target_id: str,
       rel_type: str
   ) -> List[TemporalRelationship]:
       """Get version history of a relationship.

       Performance: <30ms P95
       """
   ```

4. **Graph Traversal:**
   ```python
   async def traverse(
       start_id: str,
       traversal_spec: TraversalSpec
   ) -> List[Entity]:
       """Generic graph traversal with filters and limits.

       Performance: <100ms P95 (depth 6, 1000 nodes)
       """

   async def get_neighbors(
       entity_id: str,
       depth: int = 1,
       rel_types: Optional[List[str]] = None
   ) -> Dict[int, List[Entity]]:
       """Get neighbors at specified depth.

       Performance: <50ms P95 (depth 3)
       """
   ```

### Integration with K0 Pipelines

**1. K0 P03 Consolidation (Episodic → KG):**

```python
# k0/kg/episodic_integration.py
from k0.drivers.sqlite_kg import SQLiteKGDriver
from k0.kg.entity_extractor import EntityExtractor
from k0.kg.relationship_extractor import RelationshipExtractor

async def consolidate_episodic_to_kg(
    episodic_memory: EpisodicMemory,
    kg_driver: SQLiteKGDriver
) -> KGUpdateResult:
    """Convert episodic memory to KG entities and relationships.

    Triggered by K0 P03 Consolidation pipeline (D4).
    """
    # Extract entities
    extractor = EntityExtractor()
    entities = await extractor.extract(episodic_memory.text)

    # Extract relationships
    rel_extractor = RelationshipExtractor()
    relationships = await rel_extractor.extract(
        episodic_memory.text,
        entities
    )

    # Insert/update in KG
    result = await kg_driver.upsert_entities_and_relationships(
        entities,
        relationships,
        source="episodic_consolidation",
        timestamp=episodic_memory.timestamp
    )

    return result
```

**2. K0 P06 Learning (Relationship Confidence Adjustment):**

```python
# k0/kg/learning_feedback.py
async def adjust_relationship_confidence(
    relationship_id: str,
    feedback_signal: float,  # -1.0 to 1.0
    kg_driver: SQLiteKGDriver
) -> None:
    """Adjust relationship confidence based on user feedback.

    Triggered by K0 P06 Learning pipeline (D3).
    """
    relationship = await kg_driver.get_relationship(relationship_id)

    # Bayesian confidence update
    new_confidence = update_confidence(
        relationship.confidence,
        feedback_signal
    )

    await kg_driver.update_relationship_confidence(
        relationship_id,
        new_confidence
    )
```

**3. K0 P19 Personalization (Family Context Enrichment):**

```python
# k0/kg/personalization.py
async def enrich_with_family_context(
    query: str,
    user_id: str,
    kg_driver: SQLiteKGDriver
) -> EnrichedContext:
    """Enrich query with family relationship context.

    Triggered by K0 P19 Personalization pipeline (D3).
    """
    # Get user's family graph
    family_members = await kg_driver.find_path(
        source_id=user_id,
        rel_types=["parent", "child", "sibling", "spouse"],
        max_depth=3
    )

    # Build context for LLM
    context = {
        "family_members": family_members,
        "relationships": await get_key_relationships(user_id, kg_driver),
        "recent_events": await get_recent_family_events(user_id, kg_driver)
    }

    return EnrichedContext(query, context)
```

### Performance Targets

| Operation | P50 | P95 | P99 | Budget |
|-----------|-----|-----|-----|--------|
| Entity lookup (by ID) | 3ms | 10ms | 20ms | 10ms |
| Entity search (by pattern) | 20ms | 50ms | 100ms | 50ms |
| Relationship query (1 hop) | 10ms | 30ms | 60ms | 30ms |
| Relationship query (3 hops) | 30ms | 80ms | 150ms | 100ms |
| Shortest path (depth 6) | 40ms | 100ms | 200ms | 100ms |
| Temporal query (1 year range) | 20ms | 50ms | 100ms | 50ms |
| Graph traversal (depth 6, 1000 nodes) | 50ms | 120ms | 250ms | 150ms |
| Insert entity | 5ms | 15ms | 30ms | 20ms |
| Insert relationship | 5ms | 15ms | 30ms | 20ms |

**Optimization Strategies:**

1. **Indexes:** Entity type, label, relationship type, timestamps
2. **Caching:** LRU cache for frequently queried entities (1000 entries, 10MB)
3. **Batch Operations:** Bulk insert/update for consolidation
4. **Query Optimization:** SQLite query planner hints, covering indexes
5. **Lazy Loading:** Load properties on-demand, not eagerly

### Visualization & Debugging (ADR-0081d)

**Mermaid Export:**

```python
# k0/kg/visualization.py
async def export_to_mermaid(
    entity_id: str,
    depth: int = 2,
    kg_driver: SQLiteKGDriver
) -> str:
    """Export subgraph to Mermaid diagram.

    Example output:
    graph TD
        Alice[Alice<br/>Person]
        Mom[Mom<br/>Person]
        Seattle[Seattle<br/>Location]
        Microsoft[Microsoft<br/>Organization]
        Alice -->|sister_of| Mom
        Alice -->|lives_in| Seattle
        Alice -->|employed_by| Microsoft
    """
```

**GraphML Export (for external tools):**

```python
async def export_to_graphml(
    entity_ids: List[str],
    kg_driver: SQLiteKGDriver
) -> str:
    """Export subgraph to GraphML format for Gephi, Cytoscape."""
```

**Debugging UI (Development Only):**

```python
# k0/kg/debug_ui.py
async def launch_debug_ui(kg_driver: SQLiteKGDriver, port: int = 8765):
    """Launch web UI for KG debugging (D3.js visualization)."""
```

## Consequences

### Positive

1. **✅ Structured Family Relationships:** LLMs can accurately answer "Who is X?" with explicit family graph data
2. **✅ Temporal Reasoning:** "Who got married last year?" with event-based queries
3. **✅ Relationship Intelligence:** "How is Bob related to Eve?" with graph traversal algorithms
4. **✅ Knowledge Evolution:** Track relationship changes over time (Alice: single → married in 2020)
5. **✅ Social Intelligence:** Theory of Mind (TOM) can query structured social beliefs
6. **✅ Personalization:** K0 P19 can enrich queries with family context
7. **✅ Learning Feedback:** K0 P06 can adjust relationship confidence based on user corrections
8. **✅ Performance:** <50ms P95 graph queries, <10ms P95 entity lookup

### Negative

1. **❌ Complexity:** Additional storage layer (SQLite graph schema) + query API + integration logic
2. **❌ Maintenance:** Schema migrations, index optimization, query performance tuning
3. **❌ Entity Resolution:** Ambiguous entities (multiple "Alice" → which one?), requires disambiguation logic
4. **❌ Relationship Extraction:** NER (Named Entity Recognition) ML models, accuracy challenges
5. **❌ Privacy:** Graph contains sensitive family data, requires RED band privacy enforcement
6. **❌ Storage Cost:** Graph grows with family size (100 family members × 10 relationships each = 1000 edges)

### Mitigations

1. **Entity Disambiguation:** Confidence scoring, user confirmation for ambiguous entities
2. **Incremental Adoption:** Start with simple relationships (family tree), expand to events/locations
3. **Privacy Enforcement:** K0 P10 (PII/Minimization) redaction for RED band data
4. **Performance Monitoring:** K0 Observability metrics for query latency, cache hit rate
5. **Rollback Plan:** K0::st_kg is optional, system works without KG (degraded experience)

## Implementation Plan

### Phase 1: Foundation (Weeks 1-3)

1. **Week 1: SQLite Graph Schema**
   - [ ] Create k0/drivers/sqlite_kg.py with full implementation
   - [ ] Define nodes, edges, temporal_edges tables
   - [ ] Create indexes (entity_type, rel_type, timestamps)
   - [ ] Unit tests for CRUD operations

2. **Week 2: Query API**
   - [ ] Create k0/query/kg_temporal.py
   - [ ] Implement entity lookup (<10ms P95)
   - [ ] Implement relationship queries (<50ms P95)
   - [ ] Implement shortest path algorithm (BFS)
   - [ ] Unit tests for query operations

3. **Week 3: Temporal Reasoning**
   - [ ] Implement temporal_edges versioning
   - [ ] Implement temporal queries (valid_from/valid_to)
   - [ ] Implement relationship history tracking
   - [ ] Unit tests for temporal operations

### Phase 2: Integration (Weeks 4-6)

4. **Week 4: Episodic → KG Pipeline (P03)**
   - [ ] Create k0/kg/episodic_integration.py
   - [ ] Implement entity extraction (NER)
   - [ ] Implement relationship extraction
   - [ ] Integration with K0 P03 Consolidation handlers (D4)
   - [ ] Unit tests for extraction

5. **Week 5: Learning Feedback (P06)**
   - [ ] Create k0/kg/learning_feedback.py
   - [ ] Implement confidence adjustment
   - [ ] Integration with K0 P06 Learning pipeline (D3)
   - [ ] Unit tests for learning

6. **Week 6: Personalization (P19)**
   - [ ] Create k0/kg/personalization.py
   - [ ] Implement family context enrichment
   - [ ] Integration with K0 P19 Personalization pipeline (D3)
   - [ ] Unit tests for personalization

### Phase 3: Advanced Features (Weeks 7-9)

7. **Week 7: Visualization & Debugging**
   - [ ] Create k0/kg/visualization.py
   - [ ] Implement Mermaid export
   - [ ] Implement GraphML export
   - [ ] Create debug UI (optional)
   - [ ] Documentation for debugging

8. **Week 8: Performance Optimization**
   - [ ] Implement LRU caching (1000 entities, 10MB)
   - [ ] Query optimization (covering indexes)
   - [ ] Batch operations for bulk insert/update
   - [ ] Load testing (1000 entities, 10000 edges)
   - [ ] Performance benchmarks

9. **Week 9: Privacy & Security**
   - [ ] Integration with K0 P10 (PII redaction)
   - [ ] Privacy band enforcement (RED band data)
   - [ ] Audit logging for KG access
   - [ ] Security review

### Phase 4: Documentation & Deployment (Weeks 10-12)

10. **Week 10: Sub-ADRs & Documentation**
    - [ ] Create ADR-0081a (Temporal Graph Schema)
    - [ ] Create ADR-0081b (Query API & Traversal)
    - [ ] Create ADR-0081c (Episodic Integration)
    - [ ] Create ADR-0081d (Visualization & Debugging)
    - [ ] Update ADR-0001 (8 memory types)
    - [ ] Update ADR Family Map (8 entries)

11. **Week 11: Contract Development**
    - [ ] Create Epic 3.X in k1/contracts/contract_development_plan.md
    - [ ] Graph Schema Contracts (10 files)
    - [ ] Query API Contracts (12 files)
    - [ ] Episodic Integration Contracts (8 files)
    - [ ] Contract validation tests

12. **Week 12: Integration Testing & Deployment**
    - [ ] End-to-end testing (Episodic → KG → Query → LLM)
    - [ ] Performance testing (P95 targets)
    - [ ] Load testing (1000 users, 10000 queries/sec)
    - [ ] Production deployment plan
    - [ ] Monitoring & alerting setup

## Acceptance Criteria

- [ ] **ADR-0081 created** with full KG architecture
- [ ] **4 sub-ADRs created** (schema, query, integration, visualization)
- [ ] **ADR-0001 updated** (7→8 memory types)
- [ ] **ADR family map updated** with 8 entries
- [ ] **Contract plan updated** with Epic 3.X (~30 files)
- [ ] **Implementation complete** (10-12 weeks):
  - [ ] K0::st_kg driver with SQLite graph schema
  - [ ] k0/query/kg_temporal.py with query API
  - [ ] k0/kg/episodic_integration.py with entity extraction
  - [ ] k0/kg/visualization.py with Mermaid/GraphML export
  - [ ] Integration with K0 P03/P06/P19 pipelines
  - [ ] Performance: <50ms P95 graph query, <10ms P95 entity lookup
  - [ ] Privacy: K0 P10 redaction for RED band data
  - [ ] Tests: Unit, integration, performance, security

## References

**Research:**
- [1] Neo4j Graph Database Architecture (graph storage patterns)
- [2] SQLite Full-Text Search (FTS5) and JSON1 extension (temporal data)
- [3] Knowledge Graph Reasoning: Survey (graph algorithms)
- [4] Temporal Knowledge Graphs: A Survey (temporal reasoning)
- [5] Entity Resolution: Survey (entity disambiguation)

**Related ADRs:**
- ADR-0001: K0/K1 Kernel Split (8th memory type)
- ADR-0004: 56-Module Architecture (K0 storage modules)
- ADR-00XX: P03 Consolidation (Episodic → KG pipeline)
- ADR-00XX: P06 Learning (confidence adjustment)
- ADR-00XX: P19 Personalization (family context enrichment)

**Architecture Diagrams:**
- D1: project_architecture_part1.mmd (K0_DRIVERS: st_kg placeholder)
- D2: project_architecture_part2.mmd (Cognitive retrieval → K0::st_kg)
- D3: project_architecture_part3.mmd (Social cognition → K0::st_kg[relationships])
- D4: project_architecture_part4.mmd (K0_KG_INFRASTRUCTURE: temporal engine, causal graph)

---

**Status:** Proposed (2025-10-22)
**Next Steps:**
1. Create 4 sub-ADRs (ADR-0081a/b/c/d)
2. Update ADR-0001 (8 memory types)
3. Update ADR Family Map (8 entries)
4. Create Contract Epic 3.X (~30 files)
5. Begin Phase 1 implementation (SQLite graph schema + query API)
